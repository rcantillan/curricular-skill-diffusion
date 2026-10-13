"""Opportunity-weighted, model-standardized direction rates; not transmitted flows."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import argparse,hashlib,importlib.util,json,re,subprocess,sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src/17_sustained_incorporation'))
from run_incorporation import build
from institutional_exposures import first_origins
spec=importlib.util.spec_from_file_location('visuals',ROOT/'src/19_diffusion_visuals/build_visuals.py')
visuals=importlib.util.module_from_spec(spec);spec.loader.exec_module(visuals)


def add_weights(meta,scores,status,valid,chosen,margin,folder):
    panel=pd.read_csv(folder/'panel.csv.gz')
    cuts=pd.read_csv(folder/'thresholds.csv')
    z=(np.asarray(scores[:,chosen])-cuts.baseline_mean.to_numpy())/cuts.baseline_sd.to_numpy()
    cutoff=cuts.presence_cutoff_z.to_numpy()
    keys={(r.cell_id,r.year):i for i,r in enumerate(meta.itertuples())}
    origins=first_origins(meta,z,cutoff,margin,keys)
    kmap={int(skill):k for k,skill in enumerate(chosen)}
    pk=panel.skill_id.map(kmap).to_numpy()
    origin=origins[panel.cell_id.to_numpy(),pk]
    panel=panel[(origin<0)|(origin>=panel.year.to_numpy())].copy().reset_index(drop=True)
    if panel.empty:raise ValueError('No first-entry risk rows')
    for channel in ['same','other']:
        for b in range(5):panel[f'w_{channel}_{b}']=0.
    counts=meta.syllabi_cnt.to_numpy();cells=meta.cell_id.to_numpy()
    inst=meta.inst_id.to_numpy();fields=meta.field_id.to_numpy()
    for year,g in panel.groupby('year'):
        source=np.flatnonzero((meta.year.to_numpy()==year-1)&(counts>=9))
        prev=np.array([keys.get((cells[i],year-2),-1) for i in source])
        keep=(prev>=0)&(counts[np.maximum(prev,0)]>=9);source,prev=source[keep],prev[keep]
        present=(z[source]>=cutoff+margin)&(z[prev]>=cutoff+margin)
        for skill,gg in g.groupby('skill_id'):
            k=kmap[int(skill)];s=source[present[:,k]]
            if not len(s):continue
            rows=np.array([keys[(int(c),int(year))] for c in gg.cell_id])
            sid=inst[s];tid=inst[rows];o=origins[cells[s],k]
            if ((o<0)|(o>year-2)).any():raise ValueError('Invalid emitter origin')
            safe=np.clip(o-2002,0,13)
            matched=(o>=2002)[None,:]&(o<=2015)[None,:]&valid[safe,sid][None,:]&valid[safe[None,:],tid[:,None]]
            matched&=valid[year-1-2002,tid][:,None]
            gap=status[safe[None,:],tid[:,None]]-status[safe,sid][None,:]
            outside=tid[:,None]!=sid[None,:];same=fields[rows,None]==fields[s][None,:]
            for channel,pool in [('same',same&outside),('other',~same&outside)]:
                available=pool&matched;known=available.sum(1);eligible=(known>0)&(known>=.5*pool.sum(1))
                for b in range(5):
                    weight=((gap>=visuals.EDGES[b])&(gap<visuals.EDGES[b+1])&available).sum(1)/np.maximum(known,1)
                    weight[~eligible]=0;panel.loc[gg.index,f'w_{channel}_{b}']=weight
    assert not panel.duplicated(['cell_id','skill_id','year']).any()
    for channel in ['same','other']:
        total=panel[[f'w_{channel}_{b}' for b in range(5)]].sum(axis=1)
        assert np.all(np.isclose(total,0)|np.isclose(total,1))
    panel.to_csv(folder/'panel.csv.gz',index=False)
    pd.DataFrame([dict(risk_rows=len(panel),first_entries=int(panel.incorporation.sum()))]).to_csv(folder/'first_entry_support.csv',index=False)


def summarize(out,folders,smoke):
    rates=[];infs=[];support=[]
    for q,block,folder in folders:
        for name,collection in [('rates.csv',rates),('influences.csv.gz',infs),('model_support.csv',support)]:
            d=pd.read_csv(folder/name);d['quantile']=q;d['block']=block;collection.append(d)
    r=pd.concat(rates);u=pd.concat(infs);r.to_csv(out/'rates_by_block.csv',index=False)
    records=[];contrasts=[]
    for (q,channel,model),g in r.groupby(['quantile','channel','model']):
        weights=g.drop_duplicates('block').set_index('block').receivers
        weights=weights/weights.sum()
        uu=u[(u['quantile']==q)&(u.channel==channel)&(u.model==model)].copy()
        uu['weighted']=uu.influence*uu.block.map(weights)
        influence=uu.groupby(['unitid','bin']).weighted.sum().unstack(fill_value=0)
        estimates=g.assign(weight=g.block.map(weights)).groupby('bin').apply(lambda x:np.dot(x.rate,x.weight),include_groups=False)
        for b in range(5):
            se=float(np.sqrt(np.square(influence[b]).sum()));radius=t.ppf(.975,len(influence)-1)*se
            records.append(dict(quantile=q,channel=channel,model=model,bin=b,rate=estimates[b],se=se,
                ci_low=estimates[b]-radius,ci_high=estimates[b]+radius,blocks=len(weights),
                receivers=int(g.drop_duplicates('block').receivers.sum()),institutions=len(influence)))
        delta=float(estimates[0]-estimates[4]);se=float(np.sqrt(np.square(influence[0]-influence[4]).sum()))
        radius=t.ppf(.975,len(influence)-1)*se
        contrasts.append(dict(quantile=q,channel=channel,model=model,contrast='descending_far - ascending_far',
            estimate=delta,se=se,ci_low=delta-radius,ci_high=delta+radius,p=float(2*t.sf(abs(delta/se),len(influence)-1)),institutions=len(influence)))
    result=pd.DataFrame(records);result.to_csv(out/'adjusted_rates.csv',index=False)
    pd.DataFrame(contrasts).to_csv(out/'direction_contrasts.csv',index=False)
    pd.concat(support).to_csv(out/'model_support_by_block.csv',index=False)
    fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
    for row,q in enumerate([.75,.9]):
        for col,channel in enumerate(['same','other']):
            ax=axes[row,col]
            for model,color,label in [('strict_history','#b17d39','Historial y efectos fijos'),('institutional_adjusted','#225e91','También recursos y exposiciones')]:
                gg=result[(result['quantile']==q)&(result.channel==channel)&(result.model==model)].sort_values('bin')
                ax.errorbar(gg.bin,gg.rate*100,yerr=1.96*gg.se*100,fmt='o-',color=color,capsize=3,label=label)
            ax.set_title(('Misma disciplina' if channel=='same' else 'Disciplinas distintas')+f' · P{int(q*100)}')
            ax.set_xticks(range(5),visuals.LABELS,fontsize=8);ax.set_ylabel('Tasa ajustada de incorporación (%)');ax.grid(axis='y',alpha=.2)
            ax.spines[['top','right']].set_visible(False)
    axes[0,0].legend(fontsize=8)
    fig.suptitle(('PRUEBA DE CÓDIGO · ' if smoke else '')+'Dirección de primeras incorporaciones documentadas',fontsize=14)
    fig.text(.5,.025,'Misma población de receptores dentro de cada canal y bloque; peso total 1 por oportunidad.\nEfectos fijos programa×habilidad, disciplina×habilidad×año y universidad×año. No identifica transmisiones.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.08,1,.94])
    for ext in ['png','pdf','svg']:fig.savefig(out/f'adjusted_direction.{ext}',dpi=180)
    plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tag',default='adjusted_direction1')
    p.add_argument('--parent',default='incorporation_ipeds_origin1');p.add_argument('--smoke',action='store_true');p.add_argument('--keep-panels',action='store_true')
    args=p.parse_args()
    if not all(re.fullmatch('[A-Za-z0-9_-]+',v) for v in [args.tag,args.parent]) or (args.smoke and not args.tag.endswith('_smoke')):p.error('Simple tags; smoke tag must end in _smoke')
    parent=ROOT/'outputs/sustained_incorporation'/args.parent
    meta,scores,status,valid,skills,design=visuals.load(parent)
    for name in ['src/17_sustained_incorporation/run_incorporation.py','src/17_sustained_incorporation/institutional_exposures.py']:
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=design['hashes'][name]:raise ValueError('Parent builder changed')
    profiles=pd.read_csv(ROOT/'data/derived/institutional_selectivity/annual_institution_profile.csv')
    out=ROOT/'outputs/adjusted_direction'/args.tag;out.mkdir(parents=True,exist_ok=True)
    cache=ROOT/'data/derived/adjusted_direction'/args.tag;cache.mkdir(parents=True,exist_ok=True)
    inputs=[Path(__file__),HERE/'fit_adjusted_rates.R',ROOT/'src/19_diffusion_visuals/build_visuals.py',parent/'design.json',parent/'complete.json']
    config=dict(parent=args.parent,smoke=args.smoke,activities=64 if args.smoke else 2070,quantiles=[.75,.9],
        first_entries_only=True,source_origin='first_sustained',bins=[-1,-.25,.25,1],
        common_support='field×year: >=10 weighted opportunities in every bin',causal=False,
        hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs})
    if (out/'design.json').exists() and json.loads((out/'design.json').read_text())!=config:raise ValueError('Changed design: use a new tag')
    (out/'design.json').write_text(json.dumps(config,indent=2)+'\n')
    folders=[]
    for q in [.75,.9]:
        files=sorted(parent.glob(f'q{int(q*100)}_block_*/thresholds.csv'))
        if sorted(np.concatenate([pd.read_csv(f).skill_id for f in files]).tolist())!=list(range(2070)):raise ValueError('Incomplete parent skills')
        if args.smoke:files=files[:2]
        for block,f in enumerate(files):
            folder=cache/f'q{int(q*100)}_block_{block:03d}';folder.mkdir(exist_ok=True);folders.append((q,block,folder))
            if (folder/'complete.json').exists():continue
            chosen=pd.read_csv(f).skill_id.to_numpy(dtype=int)
            print(f'P{int(q*100)} block {block+1}/{len(files)}: risk set, directional weights, adjusted models',flush=True)
            build(meta,scores,chosen,skills,q,design['margin_sd'],folder,None,profiles,design['selectivity_measure'],'first_sustained')
            actual=pd.read_csv(folder/'thresholds.csv');expected=pd.read_csv(f).set_index('skill_id').loc[chosen]
            for column in ['baseline_mean','baseline_sd','presence_cutoff_z']:
                if not np.allclose(actual[column],expected[column],rtol=1e-12,atol=1e-12):raise ValueError('Thresholds differ from parent')
            add_weights(meta,scores,status,valid,chosen,design['margin_sd'],folder)
            with (folder/'models.log').open('w') as log:
                r=subprocess.run(['Rscript',str(HERE/'fit_adjusted_rates.R'),str(folder)],stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
            if r.returncode:raise RuntimeError(f'Model failed: {folder}/models.log')
            if not args.keep_panels:(folder/'panel.csv.gz').unlink()
    summarize(out,folders,args.smoke)
    (out/'complete.json').write_text(json.dumps(dict(complete=True,smoke=args.smoke,activities=config['activities'],blocks_per_threshold=2 if args.smoke else 65))+'\n')
    print(f'Finished: {out}',flush=True)


if __name__=='__main__':main()
