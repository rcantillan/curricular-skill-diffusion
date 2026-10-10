"""Separate sample changes from historical controls in the broad channel pilot."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import argparse,csv,gzip,hashlib,json,re,subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.stats import t as student_t

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grouped(values,codes,size):
    total=np.zeros((size,values.shape[1]));np.add.at(total,codes,values)
    return total,np.bincount(codes,minlength=size)


def boundary_membership(meta,path):
    """Reconstruct receiver selection only; retain original broad exposures."""
    nodes=pd.read_csv(path/'nodes.csv');edges=pd.read_csv(path/'candidate_edges.csv.gz')
    config=json.loads((path/'design.json').read_text());floor=config['min_syllabi'];threshold=config['min_observed_weight']
    local=meta.reset_index(names='row').merge(nodes[['unitid','fos','node_id']],on=['unitid','fos'],validate='many_to_one')
    keys={(r.node_id,r.year):r.row for r in local.itertuples()};counts=meta.syllabi_cnt.to_numpy();n=len(nodes)
    matrices=[csr_matrix((g.weight,(g.receiver,g.source)),shape=(n,n)) for _,g in edges.groupby(['kind','channel'])]
    if len(matrices)!=6:raise ValueError('Expected three actual and three random boundary channels')
    selected=np.zeros(len(meta),dtype=bool);support=[]
    for year in range(2008,2018):
        ix={y:np.array([keys.get((i,y),-1) for i in range(n)]) for y in (year-2,year-1,year)}
        good={y:(v>=0)&(counts[np.maximum(v,0)]>=floor) for y,v in ix.items()}
        sources=good[year-2]&good[year-1];keep=sources&good[year]
        for matrix in matrices:
            weight=matrix@sources.astype(float);number=(matrix>0)@sources.astype(float)
            keep&=(weight>=threshold)&(number>=2)
        selected[ix[year][keep]]=True;support.append(dict(year=year,common_targets=int(keep.sum())))
    expected=pd.read_csv(path/'block_000/support.csv')[['year','common_targets']]
    actual=pd.DataFrame(support)
    if not actual.equals(expected):raise ValueError('Boundary sample reconstruction does not match completed run')
    return selected


def build(meta,scores,chosen,skills,boundary,folder):
    x=np.asarray(scores[:,chosen]);base=(meta.year.between(2002,2007)&(meta.syllabi_cnt>=9)).to_numpy()
    mu=x[base].mean(0);sd=x[base].std(0)
    if not np.isfinite(x).all() or (x<0).any() or (sd<=1e-10).any():raise ValueError('Invalid scores/scales')
    z=(x-mu)/sd;years=meta.year.to_numpy();counts=meta.syllabi_cnt.to_numpy()
    inst=meta.unitid.to_numpy();field=meta.field_id.to_numpy();cells=meta.cell_id.to_numpy()
    keys={(r.cell_id,r.year):i for i,r in enumerate(meta.itertuples())}
    frames=[];measurements=[]
    for year in range(2008,2018):
        sources=np.flatnonzero((years==year-1)&(counts>=3))
        targets=np.array([i for i in np.flatnonzero((years==year)&(counts>=9))
                          if (cells[i],year-1) in keys and counts[keys[(cells[i],year-1)]]>=9],dtype=int)
        if not len(targets):continue
        lag=np.array([keys[(cells[i],year-1)] for i in targets]);old=np.array([keys.get((cells[i],year-2),-1) for i in targets])
        future=np.array([keys.get((cells[i],year+1),-1) for i in targets])
        ci,labels=pd.factorize(inst[sources]);sumi,ni=grouped(z[sources],ci,len(labels))
        ipos=pd.Index(labels).get_indexer(inst[targets]);sumf,nf=grouped(z[sources],field[sources],meta.field_id.nunique())
        if (ipos<0).any():raise ValueError('Target lag missing from source pool')
        ni=ni[ipos]-1;nf=nf[field[targets]]-1
        own=z[lag];wi=np.divide(sumi[ipos]-own,ni[:,None],out=np.full_like(own,np.nan),where=ni[:,None]>0)
        wf=np.divide(sumf[field[targets]]-own,nf[:,None],out=np.full_like(own,np.nan),where=nf[:,None]>0)
        previous=np.full_like(own,np.nan);hasold=old>=0;previous[hasold]=own[hasold]-z[old[hasold]]
        follow=np.full_like(own,np.nan);hasfuture=(future>=0)&(counts[np.maximum(future,0)]>=9)
        follow[hasfuture]=z[future[hasfuture]]-own[hasfuture]
        delta=z[targets]-own
        frame=pd.DataFrame(dict(unitid=np.repeat(inst[targets],len(chosen)),cell_id=np.repeat(cells[targets],len(chosen)),
            field_id=np.repeat(field[targets],len(chosen)),year=year,skill_id=np.tile(chosen,len(targets)),
            delta1=delta.ravel(),lag_score=own.ravel(),same_inst=wi.ravel(),same_field=wf.ravel(),
            previous_change=previous.ravel(),n_old=np.repeat(np.where(hasold,counts[np.maximum(old,0)],0),len(chosen)),
            n_previous=np.repeat(counts[lag],len(chosen)),n_current=np.repeat(counts[targets],len(chosen)),
            n_inst=np.repeat(ni,len(chosen)),n_field=np.repeat(nf,len(chosen)),
            boundary_selected=np.repeat(boundary[targets],len(chosen))))
        frames.append(frame)
        # Descriptive durability: not a noise-calibrated adoption definition.
        for f in np.unique(field[targets]):
            use=(field[targets]==f);observed=use&hasfuture
            for threshold in (.05,.1,.2):
                initial=(delta[use]>=threshold)
                initial_obs=(delta[observed]>=threshold)
                retained=initial_obs&(follow[observed]>=threshold)
                measurements.append(dict(year=year,field_id=int(f),threshold_sd=threshold,
                    annual_programs=int(use.sum()),followup_programs=int(observed.sum()),
                    activities=len(chosen),initial_increases=int(initial.sum()),
                    evaluable_initial_increases=int(initial_obs.sum()),retained_increases=int(retained.sum()),
                    positive_retained_amount=float(np.maximum(0,np.minimum(delta[observed],follow[observed])).sum())))
    panel=pd.concat(frames,ignore_index=True)
    if panel.duplicated(['cell_id','skill_id','year']).any():raise ValueError('Duplicate receiver outcomes')
    panel.to_csv(folder/'panel.csv.gz',index=False)
    pd.DataFrame(measurements).to_csv(folder/'retention.csv',index=False)
    pd.DataFrame({'skill_id':chosen,'skill':[skills[i] for i in chosen]}).to_csv(folder/'skills.csv',index=False)


def summarize(out,folders,legacy,smoke):
    coefficients=[];influences=[];diagnostics=[];supports=[];retention=[];failures=[];references=[]
    for i,folder in enumerate(folders):
        for file,collection in [('coefficients.csv',coefficients),('influences.csv.gz',influences),
                ('diagnostics.csv',diagnostics),('support.csv',supports),('retention.csv',retention),('failures.csv',failures)]:
            if (folder/file).exists():
                d=pd.read_csv(folder/file);d['block']=i;collection.append(d)
        if not smoke:
            r=pd.read_csv(ROOT/f'outputs/content_channels/{legacy.name}_b{i:03d}/block_coefficients.csv')
            r=r[(r.outcome=='delta1')&(r.scope=='pooled')&r.model.isin(['both','strict_internal'])].copy()
            r['block']=i;references.append(r)
    if not coefficients:raise ValueError('No estimable channel models')
    c=pd.concat(coefficients,ignore_index=True);u=pd.concat(influences,ignore_index=True)
    c.to_csv(out/'coefficients_by_block.csv',index=False)
    keys=['sample','specification','effects','term'];records=[];pooled=[]
    for key,g in c.groupby(keys):
        w=g.set_index('block').rows;w=w/w.sum();v=u
        for name,val in zip(keys,key):v=v[v[name]==val]
        v=v.copy();v['weighted']=v.influence*v.block.map(w);v=v.groupby('unitid').weighted.sum()
        estimate=np.dot(g.estimate,g.block.map(w));se=np.sqrt(np.square(v).sum());df=max(1,len(v)-1);margin=student_t.ppf(.975,df)*se
        records.append(dict(zip(keys,key),estimate=estimate,se=se,ci_low=estimate-margin,ci_high=estimate+margin,
                p=2*student_t.sf(abs(estimate/se),df) if se>0 else np.nan,blocks=len(g),rows=int(g.rows.sum()),institutions=len(v)))
        frame=v.rename('influence').reset_index()
        for name,val in zip(keys,key):frame[name]=val
        pooled.append(frame)
    result=pd.DataFrame(records);result.to_csv(out/'reconciliation_summary.csv',index=False)
    # Differences between historical-control steps, retaining shared institutions.
    pooled=pd.concat(pooled);comparisons=[]
    for (sample,effects,term),g in result.groupby(['sample','effects','term']):
        estimates=g.set_index('specification').estimate
        use=pooled[(pooled['sample']==sample)&(pooled.effects==effects)&(pooled.term==term)]
        scores=use.pivot(index='unitid',columns='specification',values='influence').fillna(0)
        for a,b in [('own_trend','legacy'),('nonlinear_trend','own_trend'),('source_support','nonlinear_trend'),('source_support','legacy')]:
            if not {a,b}<=set(estimates.index):continue
            value=estimates[a]-estimates[b];v=scores[a]-scores[b];se=np.sqrt(np.square(v).sum());df=max(1,len(v)-1);margin=student_t.ppf(.975,df)*se
            comparisons.append(dict(sample=sample,effects=effects,term=term,first=a,reference=b,difference=value,se=se,
                ci_low=value-margin,ci_high=value+margin,p=2*student_t.sf(abs(value/se),df) if se>0 else np.nan))
    pd.DataFrame(comparisons).to_csv(out/'control_step_comparisons.csv',index=False)
    # Keep control changes separate from changes in the target population.
    comparisons=[]
    for (effect,term),g in result[result.specification=='legacy'].groupby(['effects','term']):
        estimates=g.set_index('sample').estimate;clusters=g.set_index('sample').institutions
        use=pooled[(pooled.specification=='legacy')&(pooled.effects==effect)&(pooled.term==term)]
        scores=use.pivot(index='unitid',columns='sample',values='influence').fillna(0)
        for sample in ('history3','history9','boundary_receivers'):
            if not {sample,'legacy_full'}<=set(estimates.index):continue
            value=estimates[sample]-estimates['legacy_full'];v=scores[sample]-scores.legacy_full
            se=np.sqrt(np.square(v).sum());df=max(1,min(clusters[sample],clusters['legacy_full'])-1);margin=student_t.ppf(.975,df)*se
            comparisons.append(dict(effects=effect,term=term,sample=sample,reference='legacy_full',difference=value,se=se,
                ci_low=value-margin,ci_high=value+margin,p=2*student_t.sf(abs(value/se),df) if se>0 else np.nan))
    pd.DataFrame(comparisons).to_csv(out/'sample_bridge_comparisons.csv',index=False)
    pd.concat(diagnostics).to_csv(out/'model_diagnostics.csv',index=False)
    # Cohorts repeat across activity blocks; report the first, not summed populations.
    pd.concat(supports).query('block==0').drop(columns='block').to_csv(out/'sample_support.csv',index=False)
    r=pd.concat(retention).groupby(['year','field_id','threshold_sd'])[['activities','initial_increases','evaluable_initial_increases','retained_increases','positive_retained_amount']].sum().reset_index()
    r['retention_fraction']=r.retained_increases/r.evaluable_initial_increases.replace(0,np.nan)
    r['followup_fraction_of_initial_increases']=r.evaluable_initial_increases/r.initial_increases.replace(0,np.nan)
    cohorts=retention[0][['year','field_id','annual_programs','followup_programs']].drop_duplicates()
    r=r.merge(cohorts,on=['year','field_id'],validate='many_to_one')
    r=r.merge(pd.read_csv(out/'fields.csv'),on='field_id');r.to_csv(out/'descriptive_retention.csv',index=False)
    if references:
        ref=pd.concat(references);actual=c[(c['sample']=='legacy_full')&(c.specification=='legacy')].copy()
        actual['model']=actual.effects.map({'pooled':'both','strict':'strict_internal'})
        check=actual.merge(ref[['block','model','term','estimate','rows']],on=['block','model','term'],suffixes=('_new','_old'),validate='one_to_one')
        check['absolute_difference']=abs(check.estimate_new-check.estimate_old)
        check.to_csv(out/'legacy_replication_check.csv',index=False)
        if len(check)!=len(ref) or not (check.rows_new==check.rows_old).all() or check.absolute_difference.max()>1e-6:
            raise ValueError('Legacy replication mismatch: inspect legacy_replication_check.csv; do not interpret new results yet')
    if failures:
        pd.concat(failures).to_csv(out/'skipped_models.csv',index=False)
        print('Some samples/models could not be estimated: inspect skipped_models.csv.',flush=True)
    return bool(failures)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='reconcile1');parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--keep-panels',action='store_true');args=parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]+',args.tag):parser.error('Invalid tag')
    if args.smoke and not args.tag.endswith('_smoke'):parser.error('Smoke tag must end in _smoke')
    legacy=ROOT/'outputs/allskills_channels/allskills';boundary=ROOT/'outputs/boundary_channels/boundaries1'
    meta_path=ROOT/'data/derived/pilot/master_metadata.csv';stamp_path=ROOT/'data/derived/pilot/measurement_scores_manifest.json'
    meta=pd.read_csv(meta_path).sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.id.duplicated().any() or meta.duplicated(['unitid','fos','year']).any():raise ValueError('Duplicate metadata keys')
    meta['cell_id']=pd.factorize(pd.MultiIndex.from_frame(meta[['unitid','fos']]))[0]
    names=sorted(meta.fos.unique());meta['field_id']=pd.Categorical(meta.fos,categories=names).codes
    raw=ROOT/'data/raw/detailed_work_activities_scores.gzip'
    with gzip.open(raw,'rt') as f:skills=next(csv.reader(f))[1:]
    stamp=json.loads(stamp_path.read_text());stat=raw.stat()
    if (hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest()!=stamp['ids_sha256'] or
        hashlib.sha256('\n'.join(skills).encode()).hexdigest()!=stamp['skills_sha256'] or
        stat.st_size!=stamp['source_bytes'] or stat.st_mtime_ns!=stamp['source_mtime_ns']):raise ValueError('Score cache audit mismatch')
    scores=np.load(ROOT/'data/derived/pilot/measurement_scores_float64.npy',mmap_mode='r')
    if scores.shape!=(len(meta),2070):raise ValueError('Expected all 2070 activities')
    blocks=[pd.read_csv(p).skill_id.to_numpy(dtype=int) for p in sorted(legacy.glob('block_*_skills.csv'))]
    if sorted(np.concatenate(blocks).tolist())!=list(range(2070)):raise ValueError('Incomplete/duplicated legacy skill partition')
    if args.smoke:blocks=[b[:4] for b in blocks[:2]]
    paths=[HERE/'run_reconciliation.py',HERE/'fit_reconciliation.R',meta_path,stamp_path,legacy/'global_scales.csv',legacy/'design.json',
        boundary/'design.json',boundary/'nodes.csv',boundary/'candidate_edges.csv.gz',boundary/'block_000/support.csv']
    paths+=sorted(legacy.glob('block_*_skills.csv'))
    paths+=[ROOT/f'outputs/content_channels/allskills_b{i:03d}/block_coefficients.csv' for i in range(65)]
    out=ROOT/'outputs/signal_reconciliation'/args.tag;out.mkdir(parents=True,exist_ok=True)
    config=dict(tag=args.tag,smoke=args.smoke,hashes={str(p.relative_to(ROOT)):digest(p) for p in paths},
        source_floor=3,target_floor=9,baseline=[2002,2007],outcomes=[2008,2017],rca=False,
        estimator='Original disjoint blocks, row-weighted coefficients, shared receiver-institution influences',
        causal_claim=False,forecasts=False)
    if (out/'design.json').exists() and json.loads((out/'design.json').read_text())!=config:raise ValueError('Changed input/code/config: use a new tag')
    (out/'design.json').write_text(json.dumps(config,indent=2)+'\n')
    pd.DataFrame({'field_id':range(len(names)),'field':names}).to_csv(out/'fields.csv',index=False)
    pd.read_csv(legacy/'global_scales.csv').to_csv(out/'global_scales.csv',index=False)
    membership=boundary_membership(meta,boundary)
    pd.DataFrame({'skill_id':np.concatenate(blocks)}).to_csv(out/'skills_included.csv',index=False)
    folders=[]
    for i,chosen in enumerate(blocks):
        folder=out/f'block_{i:03d}';folder.mkdir(exist_ok=True);folders.append(folder)
        if (folder/'complete.json').exists():continue
        print(f'Block {i+1}/{len(blocks)}: reproduce broad channels, nested controls and sample bridge',flush=True)
        build(meta,scores,np.sort(chosen),skills,membership,folder)
        with (folder/'models.log').open('w') as log:
            result=subprocess.run(['Rscript',str(HERE/'fit_reconciliation.R'),str(folder),str(out/'global_scales.csv')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'Model failed: inspect {folder / "models.log"}')
        if not args.keep_panels:(folder/'panel.csv.gz').unlink()
    skipped=summarize(out,folders,legacy,args.smoke)
    (out/'complete.json').write_text(json.dumps(dict(activities=sum(map(len,blocks)),blocks=len(blocks),smoke=args.smoke,
        legacy_replication='checked' if not args.smoke else 'not checked: smaller activity blocks',skipped_models=skipped))+'\n')
    print(f'Finished: {out}',flush=True)


if __name__=='__main__':main()
