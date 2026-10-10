"""Receiver-level temporal signals and signed hiring-status gaps. No RCA."""
import argparse,csv,gzip,hashlib,json,subprocess,re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent


def moments(target_status,source_status,positive_changes,self_mask):
    """G=receiver-source; sources above receiver have negative G."""
    gap=target_status[:,None]-source_status[None,:]
    mask=(~self_mask).astype(float); count=mask.sum(axis=1)
    weights=mask/np.maximum(count[:,None],1)
    return {'source_mean':weights@positive_changes,
            'direction_flow':(weights*np.sign(gap))@positive_changes,
            'signed_gap_flow':(weights*gap)@positive_changes,
            'absolute_gap_flow':(weights*np.abs(gap))@positive_changes},count


def build(meta,scores,skills,chosen,status,folder,seed):
    x=np.asarray(scores[:,chosen])
    baseline=(meta.year.between(2002,2007)&(meta.syllabi_cnt>=9)).to_numpy()
    mu=x[baseline].mean(axis=0);sd=x[baseline].std(axis=0)
    if (~np.isfinite(x)).any() or (sd<=1e-10).any():raise ValueError('Invalid activity scores/scales')
    z=(x-mu)/sd
    pd.DataFrame({'skill_id':chosen,'skill':[skills[j] for j in chosen],'baseline_mean':mu,'baseline_sd':sd}).to_csv(folder/'skills.csv',index=False)
    local=meta.reset_index(names='score_row').merge(status[['unitid','field','status']],left_on=['unitid','fos'],right_on=['unitid','field'],validate='many_to_one')
    local['node_id']=pd.factorize(pd.MultiIndex.from_frame(local[['unitid','field']]))[0]
    local['field_id']=pd.Categorical(local.field,categories=sorted(status.field.unique())).codes
    keys={(r.node_id,r.year):r.score_row for r in local.itertuples()}
    status_by_node=local.groupby('node_id').status.first().to_dict()
    fields_by_node=local.groupby('node_id').field.first().to_dict()
    rng=np.random.default_rng(seed);placebo={}
    for field in sorted(status.field.unique()):
        nodes=sorted(n for n in status_by_node if fields_by_node[n]==field)
        values=[status_by_node[n] for n in nodes]
        placebo.update(zip(nodes,rng.permutation(values)))
    counts=meta.syllabi_cnt.to_numpy();rows=[];support=[]
    for year in range(2014,2018):
        for floor in (9,20):
            for field,g in local[local.year==year].groupby('field'):
                # Targets and sources require actual consecutive observations.
                targets=[r for r in g.itertuples() if (r.node_id,year-1) in keys and (r.node_id,year-2) in keys
                         and min(counts[r.score_row],counts[keys[(r.node_id,year-1)]],counts[keys[(r.node_id,year-2)]])>=floor]
                sources=[n for n in status_by_node if fields_by_node[n]==field and (n,year-1) in keys and (n,year-2) in keys
                         and min(counts[keys[(n,year-1)]],counts[keys[(n,year-2)]])>=floor]
                support.append(dict(field=field,year=year,min_syllabi=floor,targets=len(targets),sources=len(sources)))
                if not targets or len(sources)<3:continue
                src_prev=np.array([keys[(n,year-1)] for n in sources]);src_old=np.array([keys[(n,year-2)] for n in sources])
                source_increase=np.maximum(z[src_prev]-z[src_old],0)
                tar=np.array([r.score_row for r in targets]);prev=np.array([keys[(r.node_id,year-1)] for r in targets]);old=np.array([keys[(r.node_id,year-2)] for r in targets])
                self_mask=np.array([r.node_id for r in targets])[:,None]==np.array(sources)[None,:]
                actual,n=moments(np.array([r.status for r in targets]),np.array([status_by_node[s] for s in sources]),source_increase,self_mask)
                shuffled,_=moments(np.array([r.status for r in targets]),np.array([placebo[s] for s in sources]),source_increase,self_mask)
                future=np.array([keys.get((r.node_id,year+1),-1) for r in targets]);valid=(future>=0)&(counts[np.maximum(future,0)]>=floor)
                delta2=np.full((len(targets),len(chosen)),np.nan);delta2[valid]=(z[future[valid]]-z[prev[valid]])/2
                previous_change=z[prev]-z[old];positive=np.maximum(previous_change,0)
                frame=pd.DataFrame(dict(unitid=np.repeat([r.unitid for r in targets],len(chosen)),
                    node_id=np.repeat([r.node_id for r in targets],len(chosen)),field_id=np.repeat([r.field_id for r in targets],len(chosen)),
                    skill_id=np.tile(chosen,len(targets)),year=year,min_syllabi=floor,
                    status=np.repeat([r.status for r in targets],len(chosen)),
                    delta1=(z[tar]-z[prev]).ravel(),delta2=delta2.ravel(),lag_score=z[prev].ravel(),
                    previous_change=previous_change.ravel(),previous_positive=positive.ravel(),
                    previous_positive_over_peers=(positive/n[:,None]).ravel(),
                    n_previous=np.repeat(counts[prev],len(chosen)),n_current=np.repeat(counts[tar],len(chosen)),
                    n_sources=np.repeat(n,len(chosen))))
                for name,values in actual.items():frame[name]=values.ravel()
                for name in ('direction_flow','signed_gap_flow','absolute_gap_flow'):frame['placebo_'+name]=shuffled[name].ravel()
                rows.append(frame)
    if not rows:raise ValueError('No eligible temporal targets')
    panel=pd.concat(rows,ignore_index=True)
    if panel.duplicated(['unitid','field_id','skill_id','year','min_syllabi']).any():raise ValueError('Duplicated receiver outcome')
    panel.to_csv(folder/'panel.csv.gz',index=False)
    pd.DataFrame(support).to_csv(folder/'source_support.csv',index=False)
    pd.DataFrame({'field_id':range(status.field.nunique()),'field':sorted(status.field.unique())}).to_csv(folder/'fields.csv',index=False)


def summarize(out,folders):
    coefs=[];scores=[];losses=[];failures=[]
    for folder in folders:
        for name,collection in [('coefficients.csv',coefs),('influences.csv.gz',scores),('losses.csv.gz',losses),('failures.csv',failures)]:
            if (folder/name).exists():
                f=pd.read_csv(folder/name);f['block']=folder.name;collection.append(f)
    if coefs:
        c=pd.concat(coefs,ignore_index=True);s=pd.concat(scores,ignore_index=True)
        keys=['outcome','min_syllabi','model','term'];sg=s.groupby(keys);records=[]
        for key,g in c.groupby(keys):
            w=g.set_index('block').rows;w=w/w.sum();e=np.dot(g.estimate,g.block.map(w))
            u=sg.get_group(key).copy();u['weighted']=u.influence*u.block.map(w);v=u.groupby('unitid').weighted.sum()
            se=np.sqrt(np.square(v).sum());df=max(1,len(v)-1);margin=student_t.ppf(.975,df)*se
            records.append(dict(zip(keys,key),estimate=e,se=se,p=2*student_t.sf(abs(e/se),df) if se>0 else np.nan,
                                ci_low=e-margin,ci_high=e+margin,blocks=len(g),rows=int(g.rows.sum()),institutions=len(v)))
        summary=pd.DataFrame(records);summary['q_bh']=np.nan
        for _,g in summary.groupby(['outcome','min_syllabi','model']):
            p=g.p.dropna().sort_values();q=np.minimum.accumulate((p.to_numpy()*len(p)/np.arange(1,len(p)+1))[::-1])[::-1]
            summary.loc[p.index,'q_bh']=np.minimum(q,1)
        c.to_csv(out/'coefficients_by_block.csv',index=False);summary.to_csv(out/'status_associations.csv',index=False)
    if losses:
        l=pd.concat(losses,ignore_index=True)
        keys=['min_syllabi','field','model','unitid']
        l=l.groupby(keys)[['n','sse','zero_sse','base_sse']].sum().reset_index()
        l.to_csv(out/'forecast_losses_by_institution.csv.gz',index=False)
        rec=[];rng=np.random.default_rng(20261010)
        for key,g in l.groupby(['min_syllabi','field','model']):
            ix=rng.integers(0,len(g),size=(1000,len(g)))
            draws=1-g.sse.to_numpy()[ix].sum(axis=1)/g.base_sse.to_numpy()[ix].sum(axis=1)
            rec.append(dict(zip(['min_syllabi','field','model'],key),rows=int(g.n.sum()),institutions=len(g),
                            rmse=np.sqrt(g.sse.sum()/g.n.sum()),gain_vs_baseline=1-g.sse.sum()/g.base_sse.sum(),
                            r2_vs_no_change=1-g.sse.sum()/g.zero_sse.sum(),
                            gain_ci_low=np.quantile(draws,.025),gain_ci_high=np.quantile(draws,.975)))
        pd.DataFrame(rec).to_csv(out/'forecast_2016_2017.csv',index=False)
        comparisons=[]
        for (floor,field),group in l.groupby(['min_syllabi','field']):
            table=group.pivot(index='unitid',columns='model',values='sse')
            for reference in ('baseline','direction','placebo'):
                if not {'status',reference}<=set(table):continue
                ix=rng.integers(0,len(table),size=(1000,len(table)))
                draws=1-table.status.to_numpy()[ix].sum(axis=1)/table[reference].to_numpy()[ix].sum(axis=1)
                comparisons.append(dict(min_syllabi=floor,field=field,model='status',reference=reference,
                                        institutions=len(table),gain=1-table.status.sum()/table[reference].sum(),
                                        ci_low=np.quantile(draws,.025),ci_high=np.quantile(draws,.975)))
        pd.DataFrame(comparisons).to_csv(out/'forecast_pairwise_comparisons.csv',index=False)
    if failures:
        pd.concat(failures).to_csv(out/'skipped_models.csv',index=False)
        print('Some models were skipped/failed; inspect skipped_models.csv before interpreting.',flush=True)
    if not coefs:raise ValueError('No status association model succeeded')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tag',default='statusdiffusion1');p.add_argument('--block-size',type=int,default=32)
    p.add_argument('--seed',type=int,default=20261010);p.add_argument('--smoke',action='store_true')
    p.add_argument('--keep-panels',action='store_true')
    a=p.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]+',a.tag) or not 1<=a.block_size<=128:p.error('Invalid tag/block size')
    if a.smoke and not a.tag.endswith('_smoke'):p.error('Software test tag must end in _smoke')
    statusfile=ROOT/'outputs/relational_comparison/status2015/status_2015_by_field.csv'
    if not statusfile.exists():raise ValueError('Run src/12_relational_comparison/export_status.py first')
    status=pd.read_csv(statusfile)
    if status.duplicated(['unitid','field']).any() or not np.isfinite(status.status).all():raise ValueError('Invalid status keys/values')
    if not (status.outcome_start_year<=2014).all() or not (status.available_year<=2013).all():
        raise ValueError('Status not available at first outcome year')
    paths=[HERE/'run_diffusion.py',HERE/'fit_diffusion.R',statusfile,
           ROOT/'outputs/relational_comparison/status2015/status_design.json',
           ROOT/'data/derived/pilot/master_metadata.csv',ROOT/'data/derived/pilot/measurement_scores_manifest.json']
    for record in json.loads(paths[3].read_text())['inputs']:
        if hashlib.sha256(Path(record['file']).read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Status match audit changed')
    out=ROOT/'outputs/status_diffusion'/a.tag;out.mkdir(parents=True,exist_ok=True)
    config=dict(tag=a.tag,block_size=a.block_size,seed=a.seed,smoke=a.smoke,
                hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                baseline=[2002,2007],outcomes=[2014,2017],source_signal='positive score change t-2 to t-1',
                receiver_unit='university-field-activity-year',status_gap='receiver minus source, larger status is higher',
                causal_claim=False,rca=False)
    manifest=out/'design.json'
    if manifest.exists() and json.loads(manifest.read_text())!=config:raise ValueError('Changed code/input/config: choose a new tag')
    manifest.write_text(json.dumps(config,indent=2)+'\n')
    meta=pd.read_csv(paths[4]).sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.id.duplicated().any() or meta.duplicated(['unitid','fos','year']).any():raise ValueError('Duplicate profile keys')
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:skills=next(csv.reader(f))[1:]
    stamp=json.loads(paths[5].read_text());raw=(ROOT/'data/raw/detailed_work_activities_scores.gzip').stat()
    if (hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest()!=stamp['ids_sha256'] or
        hashlib.sha256('\n'.join(skills).encode()).hexdigest()!=stamp['skills_sha256'] or
        raw.st_size!=stamp['source_bytes'] or raw.st_mtime_ns!=stamp['source_mtime_ns']):raise ValueError('Score cache audit failed')
    scores=np.load(ROOT/'data/derived/pilot/measurement_scores_float64.npy',mmap_mode='r')
    if scores.shape!=(len(meta),2070) or len(skills)!=2070:raise ValueError('Expected all 2070 activity scores')
    ids=np.random.default_rng(a.seed).permutation(len(skills));ids=ids[:8] if a.smoke else ids
    pd.DataFrame({'skill_id':ids,'skill':[skills[i] for i in ids]}).to_csv(out/'skills_included.csv',index=False)
    folders=[]
    for b,start in enumerate(range(0,len(ids),a.block_size)):
        folder=out/f'block_{b:03d}';folder.mkdir(exist_ok=True);folders.append(folder)
        if (folder/'complete.json').exists():continue
        print(f'Block {b+1}/{(len(ids)+a.block_size-1)//a.block_size}',flush=True)
        build(meta,scores,skills,np.sort(ids[start:start+a.block_size]),status,folder,a.seed)
        with (folder/'models.log').open('w') as log:
            result=subprocess.run(['Rscript',str(HERE/'fit_diffusion.R'),str(folder)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:raise RuntimeError(f'Model failed: inspect {folder / "models.log"}')
        if not a.keep_panels:(folder/'panel.csv.gz').unlink()
    summarize(out,folders)
    (out/'complete.json').write_text(json.dumps(dict(activities=len(ids),blocks=len(folders),smoke=a.smoke,fields=sorted(status.field.unique())))+'\n')
    print(f'Finished: {out}',flush=True)


if __name__=='__main__':main()
