"""Initial curricular-similarity communities and later content transformation.

All DWA columns, no RCA. Frozen initial graph; subsequent change is evaluated
at program-year level. Communities are not evidence of causal transmission.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import subprocess

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, diags
from scipy.sparse.csgraph import connected_components
from scipy.sparse.linalg import eigsh
from scipy.cluster.vq import kmeans2
from scipy.special import rel_entr

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scaled_baseline(scores, eligible):
    mu = np.empty(scores.shape[1]); sd = mu.copy()
    for start in range(0, scores.shape[1], 32):
        x = np.asarray(scores[:, start:start+32])[eligible]
        if not np.isfinite(x).all():
            raise ValueError('Nonfinite baseline scores')
        mu[start:start+32] = x.mean(axis=0)
        sd[start:start+32] = x.std(axis=0)
    if (~np.isfinite(sd) | (sd <= 1e-10)).any():
        raise ValueError('Unusable baseline variance; do not silently discard activities')
    return mu, sd


def similarity_graph(profiles, neighbors):
    norms = np.linalg.norm(profiles, axis=1)
    zero = norms <= 1e-12
    normalized = profiles / np.maximum(norms[:, None],1e-12)
    similarity = normalized @ normalized.T
    similarity[zero,:] = -np.inf; similarity[:,zero] = -np.inf
    np.fill_diagonal(similarity, -np.inf)
    k = min(neighbors, len(profiles)-1)
    columns = np.argpartition(-similarity, k-1, axis=1)[:, :k]
    rows = np.repeat(np.arange(len(profiles)), k)
    weights = similarity[rows, columns.ravel()]
    valid = weights > 0
    graph = csr_matrix((weights[valid], (rows[valid], columns.ravel()[valid])), shape=similarity.shape)
    # An edge exists if either endpoint selected the other. Negative similarity
    # is not recoded to a positive relationship; no self edges.
    return graph.maximum(graph.T)


def field_residual_profiles(profiles, fields):
    """Leave-own-node-out initial field mean; no future data or zero imputation."""
    result = np.zeros_like(profiles)
    rows = []
    for field in np.unique(fields):
        members = np.where(fields==field)[0]; n = len(members)
        if n >= 3:
            result[members] = (profiles[members]-profiles[members].mean(axis=0))*n/(n-1)
        # One/two-node fields cannot support a credible institutional comparison.
        rows.append(dict(field=field,initial_nodes=n,usable_for_residual_graph=n>=3))
    return result,pd.DataFrame(rows)


def partition(graph, desired, seed):
    ncomp, component = connected_components(graph, directed=False)
    degree = np.asarray(graph.sum(axis=1)).ravel()
    pieces = [np.where(component == c)[0] for c in range(ncomp)
              if degree[component == c].sum() > 0]
    if not pieces:
        raise ValueError('No positive similarity edges')
    desired = min(max(desired, len(pieces)), sum(len(p) for p in pieces))
    allocation = np.ones(len(pieces), dtype=int)
    while allocation.sum() < desired:
        capacity = np.array([len(p) for p in pieces])/allocation
        capacity[allocation >= np.array([len(p) for p in pieces])] = -1
        allocation[np.argmax(capacity)] += 1
    labels = np.full(graph.shape[0], -1, dtype=int); offset = 0
    for index, (nodes, k) in enumerate(zip(pieces, allocation)):
        if k == 1:
            assignment = np.zeros(len(nodes), dtype=int)
        elif k >= len(nodes):
            assignment = np.arange(len(nodes))
        else:
            sub = graph[nodes][:, nodes]
            deg = np.asarray(sub.sum(axis=1)).ravel()
            lap = diags(1/np.sqrt(deg)) @ sub @ diags(1/np.sqrt(deg))
            rng = np.random.default_rng(seed+index)
            _, vectors = eigsh(lap, k=k, which='LA', v0=rng.normal(size=len(nodes)), tol=1e-7)
            embedding = vectors / np.maximum(np.linalg.norm(vectors, axis=1)[:, None], 1e-12)
            best = None
            for trial in range(10):
                centers, a = kmeans2(embedding, k, iter=80, minit='++', seed=seed+index*100+trial)
                if len(np.unique(a)) < k:
                    continue
                objective = np.square(embedding-centers[a]).sum()
                if best is None or objective < best[0]:
                    best = (objective, a)
            if best is None:
                raise ValueError('Degenerate spectral partition')
            assignment = best[1]
        labels[nodes] = assignment + offset; offset += len(np.unique(assignment))
    return labels, dict(connected_components=ncomp, nonisolated_components=len(pieces),
                        isolated_nodes=int((degree == 0).sum()), effective_communities=offset)


def adjusted_rand(a, b):
    table = pd.crosstab(a, b).to_numpy(dtype=float)
    choose = lambda x: x*(x-1)/2
    n = table.sum(); total = choose(n)
    observed = choose(table).sum(); left = choose(table.sum(axis=0)).sum(); right = choose(table.sum(axis=1)).sum()
    expected = left*right/total
    denominator = .5*(left+right)-expected
    return (observed-expected)/denominator if denominator else 1.0


def secondary(args, meta, skills, scores, baseline, out):
    audit = dict(status='missing', message='No 161-category crosswalk or separate score file supplied')
    matrix = None; mapping = None; names = None
    if args.category_crosswalk:
        crosswalk = pd.read_csv(args.category_crosswalk)
        required = {'skill_id', 'category_id'}
        if not required <= set(crosswalk):
            raise ValueError('Crosswalk requires skill_id, category_id, optional weight/category_label')
        if crosswalk[list(required)].isna().any().any():
            raise ValueError('Missing crosswalk keys')
        ids = crosswalk.skill_id.to_numpy()
        if not np.equal(ids, ids.astype(int)).all() or ids.min()<0 or ids.max()>=len(skills):
            raise ValueError('Crosswalk skill_id must match 0-based source DWA order')
        crosswalk['skill_id'] = ids.astype(int)
        if crosswalk.duplicated(['skill_id','category_id']).any():
            raise ValueError('Duplicate activity-category mapping')
        if 'skill' in crosswalk and not all(crosswalk.skill == crosswalk.skill_id.map(dict(enumerate(skills)))):
            raise ValueError('Crosswalk titles do not match source order')
        if 'weight' not in crosswalk:
            crosswalk['weight'] = 1.
        if (~np.isfinite(crosswalk.weight) | (crosswalk.weight<=0)).any():
            raise ValueError('Crosswalk weights must be finite and positive')
        categories = sorted(crosswalk.category_id.astype(str).unique())
        if len(categories) != 161:
            raise ValueError(f'Expected exactly 161 categories; found {len(categories)}')
        lookup = dict(zip(categories, range(161)))
        codes = crosswalk.category_id.astype(str).map(lookup)
        mapping = csr_matrix((crosswalk.weight, (crosswalk.skill_id, codes)), shape=(len(skills),161))
        mapping = mapping @ diags(1/np.asarray(mapping.sum(axis=0)).ravel())
        names = categories
        crosswalk.to_csv(out/'category_crosswalk_used.csv', index=False)
        # Aggregate raw clipped activity scores first; then scale categories.
        matrix = np.asarray(scores[baseline]) @ mapping
        audit = dict(status='crosswalk', mapped_activities=int(crosswalk.skill_id.nunique()),
                     unmapped_activities=len(skills)-int(crosswalk.skill_id.nunique()), categories=161,
                     aggregation='weighted mean of raw clipped activity scores per category')
    elif args.category_scores:
        frame = pd.read_csv(args.category_scores)
        if 'id' not in frame or frame.id.duplicated().any():
            raise ValueError('Category score CSV needs unique profile id')
        names = [c for c in frame if c!='id']
        if len(names)!=161:
            raise ValueError(f'Expected id + 161 score columns; found {len(names)}')
        frame = frame.set_index('id').reindex(meta.id)
        matrix = frame[names].to_numpy(dtype=float)
        if not np.isfinite(matrix).all():
            raise ValueError('Category scores must cover every metadata profile, with finite scores')
        negative = int((matrix<0).sum()); matrix = np.maximum(matrix, 0)
        audit = dict(status='separate_scores', categories=161, negative_scores_clipped=negative,
                     aggregation='separate profile scores; no DWA aggregation assumed')
        matrix_baseline = matrix[baseline]
    else:
        (out/'secondary_layer_status.json').write_text(json.dumps(audit, indent=2)+'\n')
        return None
    matrix_baseline = matrix if mapping is not None else matrix_baseline
    mu, sd = matrix_baseline.mean(axis=0), matrix_baseline.std(axis=0)
    if (~np.isfinite(sd) | (sd<=1e-10)).any():
        raise ValueError('Category without usable initial variance')
    pd.DataFrame({'category':names,'baseline_mean':mu,'baseline_sd':sd}).to_csv(out/'category_scales.csv',index=False)
    (out/'secondary_layer_status.json').write_text(json.dumps(audit, indent=2)+'\n')
    return dict(matrix=matrix if mapping is None else None, mapping=mapping, mu=mu, sd=sd)


def category_values(layer, raw, indices):
    return raw @ layer['mapping'] if layer['mapping'] is not None else layer['matrix'][indices]


def evaluate(meta, scores, nodes, graph, labels, mu, sd, layer, out, seed):
    index_by_key = {(int(r.unitid),r.fos,int(r.year)):i for i,r in enumerate(meta.itertuples())}
    unitids = nodes.unitid.to_numpy(); fields = nodes.fos.to_numpy(); n = len(nodes)
    # Source-only permutations within discipline retain disciplinary source mix.
    rng = np.random.default_rng(seed); permutation = np.arange(n)
    for field in np.unique(fields):
        members = np.where(fields==field)[0]; permutation[members] = rng.permutation(members)
    placebo = graph[:, permutation].tocsr(); placebo.setdiag(0); placebo.eliminate_zeros()
    sameinst = csr_matrix((np.ones(n), (np.arange(n), pd.factorize(unitids)[0])))
    rows = []
    for year in range(2008,2018):
        print(f'Evaluating {year}', flush=True)
        indices = [[index_by_key.get((int(u),f,y),-1) for u,f in zip(unitids,fields)]
                   for y in (year-1,year,year+1)]
        arrays=[]; counts=[]; raws=[]
        for ix in indices:
            valid = np.array(ix)>=0; raw = np.zeros((n,scores.shape[1]))
            raw[valid] = scores[np.array(ix)[valid]]
            arrays.append((raw-mu)/sd); raws.append(raw)
            count = np.zeros(n); count[valid] = meta.syllabi_cnt.to_numpy()[np.array(ix)[valid]]
            counts.append(count)
        previous,current,future = arrays; delta = current-previous
        # Exposures use prior observed sources with >=9 syllabi; missing sources
        # are removed from the denominator, not imputed as zero score.
        available = counts[0]>=9
        exposures = {}
        for name,network in [('neighbors',graph),('field_matched_placebo',placebo)]:
            weight = np.asarray(network @ available.astype(float)).ravel()
            source_count = np.asarray((network>0) @ available.astype(float)).ravel()
            exposure = network @ (previous*available[:,None]) / np.maximum(weight[:,None],1e-12)
            exposures[name] = (exposure,source_count)
        inst_sum = sameinst @ (sameinst.T @ (previous*available[:,None]))
        inst_count = np.asarray(sameinst @ (sameinst.T @ available.astype(float))).ravel()-available
        inst_mean = (inst_sum-previous*available[:,None])/np.maximum(inst_count[:,None],1)
        exposures['same_institution'] = (inst_mean,inst_count)
        category = None
        if layer is not None:
            category = [category_values(layer,raw,np.maximum(ix,0)) for raw,ix in zip(raws,indices)]
        for floor in (3,9,20):
            valid = (counts[0]>=floor)&(counts[1]>=floor)
            for j in np.where(valid)[0]:
                d = delta[j]; followed = counts[2][j]>=floor
                record = dict(node_id=j,unitid=int(unitids[j]),field=fields[j],community=int(labels[j]),
                              year=year,min_syllabi=floor,n_previous=int(counts[0][j]),n_current=int(counts[1][j]),
                              baseline_years=int(nodes.baseline_years.iloc[j]),
                              change_abs=float(np.abs(d).mean()),change_rms=float(np.sqrt(np.square(d).mean())),
                              two_year_abs=float(np.abs((future[j]-previous[j])/2).mean()) if followed else np.nan,
                              has_followup=int(followed))
                for threshold in (.1,.25,.5):
                    suffix=str(threshold).replace('.','p'); increased=d>=threshold
                    record['increase_fraction_'+suffix]=float(increased.mean())
                    record['retention_fraction_'+suffix]=(float(((future[j]-previous[j])>=threshold)[increased].mean())
                                                          if followed and increased.any() else np.nan)
                for name,(exposure,source_count) in exposures.items():
                    direction = exposure[j]-previous[j]
                    norm = np.linalg.norm(d)*np.linalg.norm(direction)
                    record[name+'_sources'] = int(source_count[j])
                    record[name+'_alignment'] = float(d@direction/norm) if source_count[j]>=2 and norm>1e-12 else np.nan
                if category is not None:
                    a,b,c = [v[j] for v in category]
                    record['category_change_abs'] = float(np.abs((b-a)/layer['sd']).mean())
                    record['category_two_year_abs'] = float(np.abs((c-a)/(2*layer['sd'])).mean()) if followed else np.nan
                    if a.sum()>0 and b.sum()>0:
                        a=a/a.sum(); b=b/b.sum(); mixture=(a+b)/2
                        record['category_js_divergence']=float(.5*(rel_entr(a,mixture).sum()+rel_entr(b,mixture).sum()))
                    else:
                        record['category_js_divergence']=np.nan
                rows.append(record)
    frame=pd.DataFrame(rows); frame.to_csv(out/'program_year_changes.csv.gz',index=False)
    return frame


def summarize(frame,nodes,labels,out,seed):
    composition=nodes.assign(community=labels)
    composition.groupby(['community','fos']).size().rename('programs').reset_index().to_csv(out/'community_field_composition.csv',index=False)
    composition.groupby(['unitid','institution_name','community']).size().rename('programs').reset_index().to_csv(out/'institution_community_membership.csv',index=False)
    columns=['change_abs','change_rms','two_year_abs','increase_fraction_0p1','retention_fraction_0p1',
             'neighbors_alignment','field_matched_placebo_alignment','same_institution_alignment']
    columns += [c for c in ('category_change_abs','category_two_year_abs','category_js_divergence') if c in frame]
    groups=[]; rng=np.random.default_rng(seed)
    for (community,floor),group in frame[frame.community>=0].groupby(['community','min_syllabi']):
        for metric in columns:
            eligible=group[np.isfinite(group[metric])]
            by_inst=eligible.groupby('unitid')[metric].agg(['sum','count'])
            if not len(by_inst): continue
            ix=rng.integers(0,len(by_inst),size=(300,len(by_inst)))
            draws=by_inst['sum'].to_numpy()[ix].sum(axis=1)/by_inst['count'].to_numpy()[ix].sum(axis=1)
            groups.append(dict(community=int(community),min_syllabi=int(floor),metric=metric,
                               mean=float(eligible[metric].mean()),ci_low=float(np.quantile(draws,.025)),
                               ci_high=float(np.quantile(draws,.975)),program_years=len(eligible),
                               institutions=len(by_inst),small_support=len(by_inst)<20))
    summary=pd.DataFrame(groups)
    summary.to_csv(out/'community_change_summary.csv',index=False)
    frame.groupby(['community','year','min_syllabi'])[columns].mean().reset_index().to_csv(out/'community_changes_by_year.csv',index=False)
    # A static research artifact. Plot availability does not affect estimation.
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
        for ax,metric,title in zip(axes,['change_abs','two_year_abs'],['Annual change','Two-year change, annualized']):
            sub=summary[(summary.min_syllabi==9)&(summary.metric==metric)].sort_values('community')
            ax.errorbar(sub.community,sub['mean'],yerr=np.maximum(0,np.array([sub['mean']-sub.ci_low,sub.ci_high-sub['mean']])),fmt='o',capsize=3)
            ax.set(xlabel='Initial similarity community',ylabel='Mean absolute change / baseline activity SD',title=title)
            ax.grid(axis='y',alpha=.2)
        fig.savefig(out/'community_changes.png',dpi=180);plt.close(fig)
        if 'category_change_abs' in frame:
            group=frame[(frame.min_syllabi==9)&(frame.community>=0)].groupby('community')[['change_abs','category_change_abs']].mean()
            fig,ax=plt.subplots(figsize=(6,4),layout='constrained')
            ax.scatter(group.change_abs,group.category_change_abs)
            for community,row in group.iterrows():
                ax.annotate(str(community),(row.change_abs,row.category_change_abs))
            ax.set(xlabel='Mean detailed-activity change / initial SD',ylabel='Mean 161-category change / initial SD',
                   title='Activity renewal and broader curricular reorientation')
            fig.savefig(out/'fine_vs_category_change.png',dpi=180);plt.close(fig)
    except ImportError:
        print('matplotlib unavailable: skipped optional plots',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='communities1')
    parser.add_argument('--neighbors',type=int,default=20)
    parser.add_argument('--communities',type=int,default=8)
    parser.add_argument('--seed',type=int,default=20261010)
    parser.add_argument('--profile-mode',choices=['raw','field_residual'],default='raw',
                        help='Initial profiles or deviations from their initial field mean')
    parser.add_argument('--smoke',action='store_true',help='100 initial nodes; ALL activities; software test only')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--category-crosswalk',type=Path)
    group.add_argument('--category-scores',type=Path)
    args=parser.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.tag) or args.neighbors<2 or args.communities<2:
        parser.error('Invalid tag / neighbors / communities')
    if args.smoke and not args.tag.endswith('_smoke'):
        parser.error('Smoke output tag must end in _smoke')
    out=ROOT/'outputs/relational_communities'/args.tag; out.mkdir(parents=True,exist_ok=True)
    paths=[HERE/'run_communities.py',HERE/'fit_communities.R',
           ROOT/'data/derived/pilot/master_metadata.csv',ROOT/'data/derived/pilot/measurement_scores_manifest.json']
    paths += [p.resolve() for p in (args.category_crosswalk,args.category_scores) if p]
    config=dict(tag=args.tag,neighbors=args.neighbors,communities=args.communities,seed=args.seed,smoke=args.smoke,
                profile_mode=args.profile_mode,
                baseline=[2002,2007],evaluation=[2008,2017],baseline_min_syllabi=9,baseline_min_observed_years=2,
                hashes={str(p):digest(p) for p in paths},rca=False,
                community_definition='positive cosine kNN on initial standardized 2070-DWA profiles; spectral partition',
                secondary_layer='explicit crosswalk or separate scores only; never inferred from DWA titles')
    manifest=out/'design.json'
    if manifest.exists() and json.loads(manifest.read_text())!=config:
        raise ValueError('Code/input/configuration changed; choose a new output tag')
    if (out/'complete.json').exists():
        print(f'Already complete: {out}'); return
    manifest.write_text(json.dumps(config,indent=2)+'\n')
    (out/'category_crosswalk_template.csv').write_text('skill_id,skill,category_id,category_label,weight\n')
    meta=pd.read_csv(ROOT/'data/derived/pilot/master_metadata.csv').sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.id.duplicated().any() or meta.duplicated(['unitid','fos','year']).any():
        raise ValueError('Duplicate profile keys')
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:
        skills=next(csv.reader(f))[1:]
    cache=ROOT/'data/derived/pilot/measurement_scores_float64.npy'
    stamp=json.loads(cache.with_name('measurement_scores_manifest.json').read_text())
    source=(ROOT/'data/raw/detailed_work_activities_scores.gzip').stat()
    if (source.st_size!=stamp['source_bytes'] or source.st_mtime_ns!=stamp['source_mtime_ns'] or
        hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest()!=stamp['ids_sha256'] or
        hashlib.sha256('\n'.join(skills).encode()).hexdigest()!=stamp['skills_sha256']):
        raise ValueError('Cache/source/order audit failed')
    scores=np.load(cache,mmap_mode='r')
    if scores.shape!=(len(meta),len(skills)) or len(skills)!=2070:
        raise ValueError('Expected audited 2070-activity score matrix')
    baseline=(meta.year.between(2002,2007)&(meta.syllabi_cnt>=9)).to_numpy()
    mu,sd=scaled_baseline(scores,baseline)
    pd.DataFrame({'skill_id':range(len(skills)),'skill':skills,'baseline_mean':mu,'baseline_sd':sd}).to_csv(out/'activity_dictionary.csv',index=False)
    nodes=meta[baseline].groupby(['unitid','fos']).agg(baseline_years=('year','nunique'),baseline_syllabi=('syllabi_cnt','sum'),
                                                       institution_name=('institution_name','first')).reset_index()
    nodes=nodes[nodes.baseline_years>=2].reset_index(drop=True)
    if args.smoke:
        nodes=nodes.sample(min(100,len(nodes)),random_state=args.seed).reset_index(drop=True)
    profiles=np.empty((len(nodes),len(skills)))
    for j,row in enumerate(nodes.itertuples()):
        ix=np.where(baseline&(meta.unitid.to_numpy()==row.unitid)&(meta.fos.to_numpy()==row.fos))[0]
        profiles[j]=(scores[ix].mean(axis=0)-mu)/sd
    print(f'{len(nodes)} initial program nodes, {nodes.unitid.nunique()} institutions, ALL {len(skills)} activities',flush=True)
    if args.profile_mode=='field_residual':
        profiles,field_audit=field_residual_profiles(profiles,nodes.fos.to_numpy())
        field_audit.to_csv(out/'field_residual_support.csv',index=False)
    np.save(out/'initial_graph_profiles.npy',profiles)
    graph=similarity_graph(profiles,args.neighbors)
    labels,audit=partition(graph,args.communities,args.seed)
    nodes['node_id']=np.arange(len(nodes)); nodes['community']=labels
    nodes.to_csv(out/'nodes.csv',index=False)
    coo=graph.tocoo(); mask=coo.row<coo.col
    pd.DataFrame({'source_node':coo.row[mask],'target_node':coo.col[mask],'similarity':coo.data[mask]}).to_csv(out/'initial_similarity_edges.csv.gz',index=False)
    stability=[]
    settings=[(args.neighbors,args.communities,args.seed+1),
              (max(2,args.neighbors//2),args.communities,args.seed),
              (args.neighbors*2,args.communities,args.seed),
              (args.neighbors,max(2,args.communities//2),args.seed),
              (args.neighbors,args.communities+4,args.seed)]
    for knn,k,seed in settings:
        other_graph=graph if knn==args.neighbors else similarity_graph(profiles,knn)
        other,diag=partition(other_graph,k,seed)
        stability.append(dict(neighbors=knn,requested_communities=k,seed=seed,
                              adjusted_rand_vs_main=adjusted_rand(labels,other),**diag))
        pd.DataFrame({'node_id':nodes.node_id,'community':other}).to_csv(out/f'partition_k{k}_n{knn}_seed{seed}.csv',index=False)
    pd.DataFrame(stability).to_csv(out/'partition_stability.csv',index=False)
    audit.update(dict(initial_nodes=len(nodes),institutions=int(nodes.unitid.nunique()),fields=int(nodes.fos.nunique()),
                      initial_profiles=int(baseline.sum()),cohort_rule='at least two observed initial years with >=9 syllabi'))
    (out/'graph_audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    layer=secondary(args,meta,skills,scores,baseline,out)
    frame=evaluate(meta,scores,nodes,graph,labels,mu,sd,layer,out,args.seed)
    summarize(frame,nodes,labels,out,args.seed)
    with (out/'models.log').open('w') as log:
        result=subprocess.run(['Rscript',str(HERE/'fit_communities.R'),str(out)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Adjusted comparisons failed: inspect {out / "models.log"}')
    (out/'complete.json').write_text(json.dumps(dict(complete=True,smoke=args.smoke,activities=2070,
                                                  secondary_available=layer is not None,program_year_rows=len(frame)))+'\n')
    print(f'Finished: {out}',flush=True)


if __name__=='__main__':
    main()
