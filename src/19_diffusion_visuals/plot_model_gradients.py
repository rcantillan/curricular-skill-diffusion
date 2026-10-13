"""Continuous contrasts of completed exposure models, not dyadic hazards."""
import argparse,csv,gzip,hashlib,json,re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import t
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[2]


def activity_map():
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:
        titles=next(csv.reader(f))[1:]
    dwa=pd.read_csv(ROOT/'data/raw/onet_reference/dwa_reference.txt',sep='\t')
    content=pd.read_csv(ROOT/'data/raw/onet_reference/content_model_reference.txt',sep='\t')
    counts=dwa.groupby('DWA Title').size()
    unique=dwa[dwa['DWA Title'].map(counts)==1]
    mapping=pd.DataFrame(dict(skill_id=range(len(titles)),skill=titles)).merge(unique,left_on='skill',right_on='DWA Title',how='left',validate='many_to_one')
    names=content.set_index('Element ID')['Element Name']
    mapping['activity_family_id']=mapping['Element ID'].str.slice(0,5)
    mapping['activity_family']=mapping.activity_family_id.map(names)
    mapping['general_activity']=mapping['Element ID'].map(names)
    mapping['matching']='unmatched'
    mapping.loc[mapping['DWA ID'].notna(),'matching']='exact_unique_title'
    target=ROOT/'data/derived/onet_reference';target.mkdir(parents=True,exist_ok=True)
    mapping.to_csv(target/'activity_family_mapping.csv',index=False)
    return mapping


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',default='incorporation_ipeds_origin1')
    p.add_argument('--tag',default='model_gradients1')
    p.add_argument('--exposure',type=float,default=.1)
    p.add_argument('--max-gap',type=float,default=1.)
    args=p.parse_args()
    if not all(re.fullmatch('[A-Za-z0-9_-]+',s) for s in [args.parent,args.tag]):p.error('Invalid tags')
    if not 0<args.exposure<=1 or not 0<args.max_gap<=2:p.error('Exposure in (0,1]; illustrative gap in (0,2]')
    parent=ROOT/'outputs/sustained_incorporation'/args.parent
    complete=json.loads((parent/'complete.json').read_text());design=json.loads((parent/'design.json').read_text())
    if complete['activities']!=2070 or complete['smoke'] or complete['folders_with_skipped_models']:
        raise ValueError('Requires completed exhaustive models')
    if design['status_source']!='ipeds' or design['origin_rule']!='first_sustained':raise ValueError('Expected origin-dated IPEDS')
    table=pd.read_csv(parent/'incorporation_summary.csv')
    out=ROOT/'outputs/diffusion_visuals'/args.tag;out.mkdir(parents=True,exist_ok=True)
    gap=np.linspace(-args.max_gap,args.max_gap,201)
    fig,axes=plt.subplots(2,2,figsize=(11,8),sharex=True,sharey=True)
    records=[]
    for row,q in enumerate([.75,.9]):
        for col,pool in enumerate(['same','other']):
            ax=axes[row,col]
            for model,color,style,label in [
                ('selectivity_direction','#c18033','--','Historial, exposiciones y efectos fijos'),
                ('selectivity_adjusted','#225e91','-','También recursos y tipo institucional')]:
                d=table[(table['quantile']==q)&(table.model==model)].set_index('term')
                a=d.loc['sel_above_'+pool];b=d.loc['sel_below_'+pool]
                if a.blocks!=65 or b.blocks!=65:raise ValueError('Incomplete gradient')
                multiplier=args.exposure*100
                estimate=multiplier*(a.estimate*np.maximum(-gap,0)+b.estimate*np.maximum(gap,0))
                se=multiplier*(a.se*np.maximum(-gap,0)+b.se*np.maximum(gap,0))
                # At each gap only one branch is nonzero; no covariance term is missing.
                radius=t.ppf(.975,min(a.institutions,b.institutions)-1)*se
                ax.plot(gap,estimate,color=color,ls=style,label=label,lw=1.8)
                ax.fill_between(gap,estimate-radius,estimate+radius,color=color,alpha=.10)
                records.append(pd.DataFrame(dict(quantile=q,channel=pool,model=model,gap=gap,
                    exposure=args.exposure,contrast_pp=estimate,ci_low=estimate-radius,ci_high=estimate+radius)))
            ax.axhline(0,color='#7a8791',ls=':',lw=.9);ax.axvline(0,color='#7a8791',lw=.8)
            ax.set_title(('Misma disciplina' if pool=='same' else 'Disciplinas distintas')+f' · P{int(q*100)}',fontsize=11)
            ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)
            if col==0:ax.set_ylabel('Contraste de incorporación\n(puntos porcentuales)')
            if row==1:ax.set_xlabel('Selectividad receptor − emisor (DE)\nDescendente ←                      → Ascendente')
    axes[0,0].legend(fontsize=8,loc='best')
    fig.suptitle('Gradientes continuos en los modelos de exposición\nPosiciones fijadas al primer año sostenido del emisor',fontsize=14)
    fig.text(.5,.02,f'Referencia: gap = 0. Contraste ilustrativo: {args.exposure*100:g}% del conjunto cubierto son emisores comparables, todos con el gap indicado.\nOtras covariables constantes. Bandas: IC 95%. Rango fijado para ilustración; no son percentiles de soporte.\nModelos de la etapa 17: permiten reentradas. No son tasas de transmisión ni los resultados pendientes de la etapa 20.',ha='center',fontsize=8.5)
    fig.tight_layout(rect=[0,.105,1,.92])
    for ext in ['png','pdf','svg']:fig.savefig(out/f'continuous_gradients.{ext}',dpi=180)
    plt.close(fig)
    pd.concat(records).to_csv(out/'continuous_contrasts.csv',index=False)
    mapping=activity_map()
    audit=mapping.groupby(['activity_family_id','activity_family'],dropna=False).size().rename('activities').reset_index()
    audit.to_csv(out/'activity_family_counts.csv',index=False)
    inputs=[Path(__file__),parent/'incorporation_summary.csv',parent/'design.json']+[ROOT/'data/raw/onet_reference'/f for f in ['dwa_reference.txt','content_model_reference.txt']]
    config=dict(parent=args.parent,selectivity_not_prestige=True,exposure=args.exposure,illustrative_gap_range=[-args.max_gap,args.max_gap],
        interpretation='Exposure-model contrast against all comparable holders at gap zero; no dyadic hazard or causal flow',
        formula='100*exposure*(beta_above*max(-gap,0)+beta_below*max(gap,0))',
        families_not_estimated=True,exact_activity_matches=int(mapping['DWA ID'].notna().sum()),
        hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in inputs})
    (out/'design.json').write_text(json.dumps(config,indent=2)+'\n')
    print(audit.to_string(index=False));print(f'Finished: {out}')


if __name__=='__main__':main()
