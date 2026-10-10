"""Frozen baseline candidate relations and subsequent curricular change. No RCA."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import argparse, csv, gzip, hashlib, json, re, subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CHANNELS = ('internal', 'external_same', 'external_other')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def average(matrix, values, available):
    """Missing profiles do not become zero; normalize only observed edge weights."""
    weight = np.asarray(matrix @ available.astype(float)).ravel()
    count = np.asarray((matrix > 0) @ available.astype(float)).ravel()
    result = np.divide(matrix @ np.where(available[:, None], values, 0), weight[:, None],
                       out=np.full((matrix.shape[0], values.shape[1]), np.nan),
                       where=weight[:, None] > 0)
    return result, weight, count


def graph(nodes, profiles, neighbors, seed, out):
    norm = np.linalg.norm(profiles, axis=1)
    unit = profiles / np.maximum(norm[:, None], 1e-12)
    similarity = unit @ unit.T
    rng = np.random.default_rng(seed)
    matrices = {}; edges = []; audit = []
    institution = nodes.unitid.to_numpy(); field = nodes.field_id.to_numpy()
    for channel in CHANNELS:
        rows = []; cols = []; weights = []; rr = []; cc = []; ww = []
        for i in range(len(nodes)):
            same_i = institution == institution[i]; same_f = field == field[i]
            eligible = (same_i & ~same_f if channel == 'internal' else
                        ~same_i & same_f if channel == 'external_same' else ~same_i & ~same_f)
            candidates = np.flatnonzero(eligible & (norm > 1e-12))
            chosen = candidates[np.argsort(-similarity[i, candidates], kind='stable')]
            chosen = chosen[similarity[i, chosen] > 0][:neighbors] if norm[i] > 1e-12 else chosen[:0]
            if len(chosen) < 2:
                audit.append(dict(node_id=i,channel=channel,edges=0,random_overlap=np.nan)); continue
            weight = similarity[i, chosen]; weight = weight / weight.sum()
            # One fixed random candidate graph; same receiver/channel degree and
            # weight distribution, but not a formal permutation significance test.
            random = rng.choice(candidates, len(chosen), replace=False)
            rows.extend([i]*len(chosen)); cols.extend(chosen); weights.extend(weight)
            rr.extend([i]*len(chosen)); cc.extend(random); ww.extend(weight)
            audit.append(dict(node_id=i,channel=channel,edges=len(chosen),
                              random_overlap=len(set(chosen)&set(random))/len(chosen)))
            for kind, sources in [('related', chosen), ('random', random)]:
                edges.extend(dict(receiver=i,source=int(j),channel=channel,kind=kind,weight=float(w))
                             for j,w in zip(sources,weight))
        matrices[channel] = csr_matrix((weights,(rows,cols)),shape=(len(nodes),len(nodes)))
        matrices['random_'+channel] = csr_matrix((ww,(rr,cc)),shape=(len(nodes),len(nodes)))
    pd.DataFrame(edges).to_csv(out/'candidate_edges.csv.gz',index=False)
    pd.DataFrame(audit).to_csv(out/'graph_support.csv',index=False)
    return matrices


def build(meta, scores, chosen, skills, nodes, matrices, scales, floor, min_weight, folder):
    x = np.asarray(scores[:,chosen]); z = (x-scales[0][chosen])/scales[1][chosen]
    if not np.isfinite(z).all(): raise ValueError('Nonfinite activity scores')
    local = meta.reset_index(names='score_row').merge(nodes[['unitid','fos','node_id','field_id']],
                                                    on=['unitid','fos'],validate='many_to_one')
    lookup = {(r.node_id,r.year):r.score_row for r in local.itertuples()}
    counts = meta.syllabi_cnt.to_numpy(); size = len(nodes); rows = []; support = []
    inst = nodes.unitid.to_numpy(); fields = nodes.field_id.to_numpy(); receiver_support=[]
    # Uniform source means control broad institutional/disciplinary content.
    generic = {}
    for name in ('internal','external_same'):
        mask = ((inst[:,None]==inst[None,:]) & (fields[:,None]!=fields[None,:]) if name=='internal'
                else (inst[:,None]!=inst[None,:]) & (fields[:,None]==fields[None,:]))
        generic[name] = csr_matrix(mask.astype(float))
    for year in range(2008,2018):
        indexes = {t:np.array([lookup.get((n,t),-1) for n in range(size)]) for t in (year-2,year-1,year,year+1)}
        eligible = {t:(v>=0)&(counts[np.maximum(v,0)]>=floor) for t,v in indexes.items()}
        available = eligible[year-2]&eligible[year-1]
        valid = available&eligible[year]
        old = z[np.maximum(indexes[year-2],0)]; prev = z[np.maximum(indexes[year-1],0)]
        prior = np.maximum(prev-old,0)
        values = {}; coverage = {}
        for name,m in matrices.items():
            stock,w,n = average(m,prev,available); growth,_,_ = average(m,prior,available)
            values[name+'_stock'] = stock; values[name+'_increase'] = growth
            coverage[name] = (w,n)
            valid &= (w>=min_weight)&(n>=2)
        target = np.flatnonzero(valid)
        support.append(dict(year=year,candidate_targets=int((available&eligible[year]).sum()),
                            common_targets=len(target),source_programs=int(available.sum())))
        if not len(target): continue
        for field_id in np.unique(fields[target]):
            selected=target[fields[target]==field_id]
            for name,(w,n) in coverage.items():
                receiver_support.append(dict(year=year,field_id=int(field_id),channel=name,
                    programs=len(selected),institutions=len(np.unique(inst[selected])),
                    median_observed_weight=float(np.median(w[selected])),minimum_observed_weight=float(w[selected].min()),
                    median_observed_sources=float(np.median(n[selected]))))
        current = z[np.maximum(indexes[year],0)]
        frame = pd.DataFrame(dict(unitid=np.repeat(inst[target],len(chosen)),
            node_id=np.repeat(target,len(chosen)),field_id=np.repeat(fields[target],len(chosen)),
            skill_id=np.tile(chosen,len(target)),year=year,min_syllabi=floor,
            delta1=(current[target]-prev[target]).ravel(),lag_score=prev[target].ravel(),
            previous_change=(prev[target]-old[target]).ravel(),
            n_previous=np.repeat(counts[indexes[year-1][target]],len(chosen)),
            n_current=np.repeat(counts[indexes[year][target]],len(chosen))))
        for name,value in values.items():frame[name]=value[target].ravel()
        for name,(w,n) in coverage.items():
            frame[name+'_coverage']=np.repeat(w[target],len(chosen))
            frame[name+'_count']=np.repeat(n[target],len(chosen))
        for name,m in generic.items():
            for label,v in [('stock',prev),('increase',prior)]:
                value,_,n=average(m,v,available)
                if not np.isfinite(value[target]).all():raise ValueError('Missing generic controls')
                frame['generic_'+name+'_'+label]=value[target].ravel()
        # Future-source diagnostic: t -> t+1, strictly AFTER receiver t-1 -> t.
        # Restrict every comparison to the same evaluable future-source sample.
        future_available=eligible[year]&eligible[year+1]
        future_growth=np.maximum(z[np.maximum(indexes[year+1],0)]-current,0)
        lead_ok=np.ones(len(target),dtype=bool)
        for name in CHANNELS:
            value,w,n=average(matrices[name],future_growth,future_available)
            ok=(w[target]>=min_weight)&(n[target]>=2)&(year<=2016)
            lead_ok &= ok
            lead=value[target].copy();lead[~ok]=np.nan
            frame[name+'_future_increase']=lead.ravel()
        frame['lead_evaluable']=np.repeat(lead_ok,len(chosen))
        rows.append(frame)
    if not rows:raise ValueError('No common targets across three channels')
    panel=pd.concat(rows,ignore_index=True)
    if panel.duplicated(['node_id','skill_id','year']).any():raise ValueError('Duplicated outcome')
    panel.to_csv(folder/'panel.csv.gz',index=False)
    pd.DataFrame(support).to_csv(folder/'support.csv',index=False)
    pd.DataFrame(receiver_support).to_csv(folder/'receiver_support.csv',index=False)
    pd.DataFrame({'skill_id':chosen,'skill':[skills[i] for i in chosen]}).to_csv(folder/'skills.csv',index=False)


def summarize(out, folders):
    collections={name:[] for name in ('coefficients','influences','losses','failures')}
    for folder in folders:
        for name,frames in collections.items():
            path=folder/(name+('.csv.gz' if name in ('influences','losses') else '.csv'))
            if path.exists():
                f=pd.read_csv(path);f['block']=folder.name;frames.append(f)
    if not collections['coefficients']:raise ValueError('No association estimates')
    c=pd.concat(collections['coefficients']);s=pd.concat(collections['influences'])
    c.to_csv(out/'coefficients_by_block.csv',index=False)
    records=[];combined=[];keys=['model','term']
    for key,g in c.groupby(keys):
        w=g.set_index('block').rows;w=w/w.sum()
        use=s[(s.model==key[0])&(s.term==key[1])].copy()
        use['weighted']=use.influence*use.block.map(w)
        v=use.groupby('unitid').weighted.sum();e=np.dot(g.estimate,g.block.map(w))
        se=np.sqrt(np.square(v).sum());df=max(1,len(v)-1);margin=student_t.ppf(.975,df)*se
        records.append(dict(zip(keys,key),estimate=e,se=se,p=2*student_t.sf(abs(e/se),df) if se>0 else np.nan,
                            ci_low=e-margin,ci_high=e+margin,blocks=len(g),rows=int(g.rows.sum()),institutions=len(v)))
        f=v.rename('influence').reset_index();f['model']=key[0];f['term']=key[1];combined.append(f)
    summary=pd.DataFrame(records);summary['q_bh']=np.nan
    for _,g in summary.groupby('model'):
        p=g.p.dropna().sort_values();q=np.minimum.accumulate((p.to_numpy()*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
        summary.loc[p.index,'q_bh']=np.minimum(q,1)
    summary.to_csv(out/'channel_associations.csv',index=False)
    # Explicit coefficient contrasts, rather than comparing significance labels.
    influence=pd.concat(combined);contrasts=[]
    for signal in ('stock','increase'):
        for a,b in [('internal','external_same'),('internal','external_other'),('external_same','external_other')]:
            terms=[a+'_'+signal,b+'_'+signal];sub=summary[(summary.model=='related')&summary.term.isin(terms)].set_index('term')
            if len(sub)!=2:continue
            u=influence[influence.model=='related'].pivot(index='unitid',columns='term',values='influence').fillna(0)
            v=u[terms[0]]-u[terms[1]];se=np.sqrt(np.square(v).sum());e=sub.loc[terms[0],'estimate']-sub.loc[terms[1],'estimate']
            df=len(v)-1;margin=student_t.ppf(.975,df)*se
            contrasts.append(dict(signal=signal,first=a,second=b,difference=e,se=se,
                                  p=2*student_t.sf(abs(e/se),df),ci_low=e-margin,ci_high=e+margin))
    contrast_frame=pd.DataFrame(contrasts)
    if len(contrast_frame):
        p=contrast_frame.p.dropna().sort_values();q=np.minimum.accumulate((p.to_numpy()*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
        contrast_frame.loc[p.index,'q_bh']=np.minimum(q,1)
    contrast_frame.to_csv(out/'channel_contrasts.csv',index=False)
    if collections['losses']:
        l=pd.concat(collections['losses']).groupby(['field','model','unitid'])[['n','sse','zero_sse','base_sse']].sum().reset_index()
        l.to_csv(out/'forecast_losses_by_institution.csv.gz',index=False)
        rng=np.random.default_rng(20261010);records=[];comparisons=[]
        for key,g in l.groupby(['field','model']):
            ix=rng.integers(0,len(g),size=(1000,len(g)))
            draws=1-g.sse.to_numpy()[ix].sum(axis=1)/g.base_sse.to_numpy()[ix].sum(axis=1)
            records.append(dict(field=key[0],model=key[1],rows=int(g.n.sum()),institutions=len(g),small_support=len(g)<20,
                rmse=np.sqrt(g.sse.sum()/g.n.sum()),gain_vs_baseline=1-g.sse.sum()/g.base_sse.sum(),
                r2_vs_no_change=1-g.sse.sum()/g.zero_sse.sum(),ci_low=np.quantile(draws,.025),ci_high=np.quantile(draws,.975)))
        for field,g in l.groupby('field'):
            tab=g.pivot(index='unitid',columns='model',values='sse')
            for ref in ('baseline','internal','external_same','external_other','random'):
                if not {'all',ref}<=set(tab):continue
                ix=rng.integers(0,len(tab),size=(1000,len(tab)))
                draws=1-tab['all'].to_numpy()[ix].sum(axis=1)/tab[ref].to_numpy()[ix].sum(axis=1)
                comparisons.append(dict(field=field,model='all',reference=ref,institutions=len(tab),small_support=len(tab)<20,gain=1-tab['all'].sum()/tab[ref].sum(),
                                        ci_low=np.quantile(draws,.025),ci_high=np.quantile(draws,.975)))
        pd.DataFrame(records).to_csv(out/'forecast_2014_2017.csv',index=False)
        pd.DataFrame(comparisons).to_csv(out/'forecast_comparisons.csv',index=False)
    if collections['failures']:
        pd.concat(collections['failures']).to_csv(out/'skipped_models.csv',index=False)
        print('Inspect skipped_models.csv: some models/terms were unavailable.',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tag',default='boundaries1');p.add_argument('--block-size',type=int,default=32)
    p.add_argument('--seed',type=int,default=20261010);p.add_argument('--neighbors',type=int,default=10)
    p.add_argument('--min-syllabi',type=int,default=9);p.add_argument('--smoke',action='store_true')
    p.add_argument('--min-observed-weight',type=float,default=.3)
    p.add_argument('--keep-panels',action='store_true');a=p.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]+',a.tag) or not 1<=a.block_size<=128 or a.neighbors<2 or a.min_syllabi<3:p.error('Invalid options')
    if not 0<a.min_observed_weight<=1:p.error('Observed weight must lie in (0,1]')
    if a.smoke and not a.tag.endswith('_smoke'):p.error('Smoke tag must end in _smoke')
    meta_path=ROOT/'data/derived/pilot/master_metadata.csv'
    cache_manifest=ROOT/'data/derived/pilot/measurement_scores_manifest.json'
    meta=pd.read_csv(meta_path).sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.id.duplicated().any() or meta.duplicated(['unitid','fos','year']).any():raise ValueError('Duplicate metadata keys')
    raw=ROOT/'data/raw/detailed_work_activities_scores.gzip'
    with gzip.open(raw,'rt') as f:skills=next(csv.reader(f))[1:]
    stamp=json.loads(cache_manifest.read_text());stat=raw.stat()
    if (hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest()!=stamp['ids_sha256'] or
        hashlib.sha256('\n'.join(skills).encode()).hexdigest()!=stamp['skills_sha256'] or
        stat.st_size!=stamp['source_bytes'] or stat.st_mtime_ns!=stamp['source_mtime_ns']):raise ValueError('Score-cache audit mismatch')
    scores=np.load(ROOT/'data/derived/pilot/measurement_scores_float64.npy',mmap_mode='r')
    if scores.shape!=(len(meta),2070):raise ValueError('Expected all 2070 activities')
    out=ROOT/'outputs/boundary_channels'/a.tag;out.mkdir(parents=True,exist_ok=True)
    config=dict(vars(a),baseline=[2002,2007],outcomes=[2008,2017],holdout=[2014,2017],rca=False,causal_claim=False,
                hashes={str(f):digest(f) for f in (HERE/'run_channels.py',HERE/'fit_channels.R',meta_path,cache_manifest)})
    manifest=out/'design.json'
    if manifest.exists() and json.loads(manifest.read_text())!=config:raise ValueError('Changed code/config/input: use a new tag')
    manifest.write_text(json.dumps(config,indent=2)+'\n')
    print('Building relations from 2002–2007 profiles using ALL 2070 activities.',flush=True)
    baseline=(meta.year.between(2002,2007)&(meta.syllabi_cnt>=9)).to_numpy()
    initial=meta[baseline].groupby(['unitid','fos']).size();initial=initial[initial>=2].reset_index(name='baseline_years')
    nodes=initial.sort_values(['unitid','fos']).reset_index(drop=True);nodes['node_id']=np.arange(len(nodes))
    field_names=sorted(nodes.fos.unique());nodes['field_id']=pd.Categorical(nodes.fos,categories=field_names).codes
    nodes.to_csv(out/'nodes.csv',index=False)
    pd.DataFrame({'field_id':range(len(field_names)),'field':field_names}).to_csv(out/'fields.csv',index=False)
    base=meta[baseline].reset_index(names='row').merge(nodes,on=['unitid','fos'],validate='many_to_one')
    mu=np.empty(2070);sd=np.empty(2070);profiles=np.zeros((len(nodes),2070));n=np.bincount(base.node_id,minlength=len(nodes))
    for start in range(0,2070,32):
        x=np.asarray(scores[:,start:start+32]);mu[start:start+32]=x[baseline].mean(0);sd[start:start+32]=x[baseline].std(0)
        np.add.at(profiles[:,start:start+32],base.node_id.to_numpy(),(x[base.row]-mu[start:start+32])/sd[start:start+32])
    if not np.isfinite(sd).all() or (sd<=1e-10).any() or not np.isfinite(profiles).all():raise ValueError('Invalid initial scales/profiles')
    profiles/=n[:,None]
    pd.DataFrame({'skill_id':range(2070),'skill':skills,'baseline_mean':mu,'baseline_sd':sd}).to_csv(out/'baseline_scales.csv',index=False)
    matrices=graph(nodes,profiles,a.neighbors,a.seed,out)
    ids=np.random.default_rng(a.seed).permutation(2070);ids=ids[:8] if a.smoke else ids
    pd.DataFrame({'skill_id':ids,'skill':[skills[i] for i in ids]}).to_csv(out/'skills_included.csv',index=False)
    folders=[];total=(len(ids)+a.block_size-1)//a.block_size
    for b,start in enumerate(range(0,len(ids),a.block_size)):
        folder=out/f'block_{b:03d}';folder.mkdir(exist_ok=True);folders.append(folder)
        if (folder/'complete.json').exists():continue
        print(f'Block {b+1}/{total}',flush=True)
        build(meta,scores,np.sort(ids[start:start+a.block_size]),skills,nodes,matrices,(mu,sd),a.min_syllabi,a.min_observed_weight,folder)
        with (folder/'models.log').open('w') as log:
            result=subprocess.run(['Rscript',str(HERE/'fit_channels.R'),str(folder),str(out/'fields.csv')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'Model failed: inspect {folder / "models.log"}')
        if not a.keep_panels:(folder/'panel.csv.gz').unlink()
    summarize(out,folders)
    (out/'complete.json').write_text(json.dumps(dict(activities=len(ids),blocks=len(folders),smoke=a.smoke,nodes=len(nodes),fields=len(field_names),
        skipped_models=(out/'skipped_models.csv').exists()))+'\n')
    print(f'Finished: {out}',flush=True)


if __name__=='__main__':main()
