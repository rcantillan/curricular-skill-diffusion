"""Exploratory continuous-change pilot; no inferred presence/adoption.

Train a fixed skill space on 2002--2007 programs with >=2 observed baseline
profiles having >=9 syllabi each. Outcome is annual change in the positive
Atlas score in baseline SD units. Exposures are prior-year mean scores of
other observed programs, NOT contact networks or transmission sources.
Uniformly sample 64 DWAs each year, before inspecting outcomes. Space uses
all source DWAs. Primary coverage >=9; >=3 is a separate sensitivity.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','4')
os.environ.setdefault('OMP_NUM_THREADS','4')
from pathlib import Path
import csv
import gzip
import importlib.util
import json
import argparse
import re
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'data/derived/pilot'
OUT=ROOT/'outputs/pilot'
SEED=20261004
SKILLS_PER_YEAR=64


def means(values,codes,n_groups):
    summed=np.zeros((n_groups,values.shape[1]))
    np.add.at(summed,codes,values)
    n=np.bincount(codes,minlength=n_groups)
    avg=np.divide(summed,n[:,None],out=np.full_like(summed,np.nan),where=n[:,None]>0)
    return avg,n


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sampling',choices=['annual','fixed'],default='annual')
    parser.add_argument('--seed',type=int,default=SEED)
    parser.add_argument('--skills-per-year',type=int,default=SKILLS_PER_YEAR)
    parser.add_argument('--tag',default='')
    args=parser.parse_args()
    if args.tag and not re.fullmatch(r'[A-Za-z0-9_-]+',args.tag):
        parser.error('tag solo puede contener letras, números, guiones o underscores.')
    if (args.sampling!='annual' or args.seed!=SEED or args.skills_per_year!=SKILLS_PER_YEAR) and not args.tag:
        parser.error('Usa --tag para preservar el piloto original al cambiar el diseño.')
    if args.tag:
        OUT=OUT/args.tag
    OUT.mkdir(parents=True,exist_ok=True)
    dest=DATA/('continuous_diffusion_'+args.tag if args.tag else 'continuous_diffusion')
    dest.mkdir(parents=True,exist_ok=True)
    # Incomplete runs cannot leave an old success marker for the model script.
    (dest/'complete.json').unlink(missing_ok=True)
    spec=importlib.util.spec_from_file_location('measurement_helper',Path(__file__).with_name('01_validate_measurement.py'))
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    meta=pd.read_csv(DATA/'master_metadata.csv').sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.duplicated('id').any() or meta.duplicated(['unitid','fos','year']).any():
        raise ValueError('Metadata duplicada.')
    meta['cell_id']=pd.factorize(pd.MultiIndex.from_frame(meta[['unitid','fos']]))[0]
    fields=sorted(meta.fos.unique())
    meta['field_id']=pd.Categorical(meta.fos,categories=fields).codes
    pd.DataFrame({'field_id':range(len(fields)),'field':fields}).to_csv(OUT/'continuous_field_dictionary.csv',index=False)
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:
        skills=next(csv.reader(f))[1:]
    pd.DataFrame({'skill_id':range(len(skills)),'skill':skills}).to_csv(OUT/'continuous_skill_dictionary.csv',index=False)
    scores,cache_manifest=helper.load_scores(meta,skills)
    years=meta.year.to_numpy()
    counts=meta.syllabi_cnt.to_numpy()
    cells=meta.cell_id.to_numpy()
    field_ids=meta.field_id.to_numpy()
    unitids=meta.unitid.to_numpy()
    baseline=(years>=2002)&(years<=2007)&(counts>=9)
    bx=np.asarray(scores[np.flatnonzero(baseline)])
    mu=bx.mean(axis=0)
    sd=bx.std(axis=0)
    valid_sd=np.isfinite(sd)&(sd>1e-10)
    benchmark=bx.sum(axis=0)/bx.sum()
    if (benchmark<=0).any():
        raise ValueError('Referencia baseline sin masa positiva.')
    # Pool only well-covered baseline years, giving each program one network row.
    codes,labels=pd.factorize(cells[baseline])
    summed=np.zeros((len(labels),len(skills)))
    weights=counts[baseline]
    np.add.at(summed,codes,bx*weights[:,None])
    weight_totals=np.bincount(codes,weights=weights,minlength=len(labels))
    observed=np.bincount(codes,minlength=len(labels))
    pooled=summed/weight_totals[:,None]
    baseline_programs=observed>=2
    network_profiles=pooled[baseline_programs]
    network_share=network_profiles/network_profiles.sum(axis=1)[:,None]
    m=(network_share/benchmark>=1).astype(np.float64)
    degree=m.sum(axis=0)
    denom=np.maximum(degree[:,None],degree[None,:])
    phi=np.divide(m.T@m,denom,out=np.zeros((len(skills),len(skills))),where=denom>0)
    np.fill_diagonal(phi,0)
    if not len(network_profiles):
        raise ValueError('Sin programas baseline con dos años de cobertura >=9.')
    pd.DataFrame({'skill_id':range(len(skills)),'baseline_mean':mu,'baseline_sd':sd,
                  'network_degree':degree,'network_weight_sum':phi.sum(axis=0)}).to_csv(OUT/'continuous_skill_space_audit.csv',index=False)
    np.save(dest/'phi_pre2008.npy',phi)
    previous=meta.groupby('cell_id',sort=False).year.shift().to_numpy()
    if not 1<=args.skills_per_year<=len(skills):
        parser.error('skills-per-year debe estar entre 1 y el número de DWAs fuente.')
    rng=np.random.default_rng(args.seed)
    fixed_choice=np.sort(rng.choice(len(skills),size=args.skills_per_year,replace=False)) if args.sampling=='fixed' else None
    diagnostics=[]
    sampled=[]
    for y in range(2008,2018):
        source=np.flatnonzero((years==y-1)&(counts>=3))
        target=np.flatnonzero((years==y)&(years-previous==1)&(counts>=3))
        target=target[counts[target-1]>=3]
        lag=target-1
        if not len(target):
            raise ValueError(f'Sin pares elegibles en {y}.')
        chosen=fixed_choice if fixed_choice is not None else np.sort(rng.choice(len(skills),size=args.skills_per_year,replace=False))
        sampled.extend({'year':y,'skill_id':int(s),'skill':skills[s]} for s in chosen)
        src_x=np.asarray(scores[source][:,chosen])
        x0=np.asarray(scores[lag][:,chosen])
        x1=np.asarray(scores[target][:,chosen])
        safe_sd=np.where(valid_sd[chosen],sd[chosen],np.nan)
        lag_z=(x0-mu[chosen])/safe_sd
        outcome=(x1-x0)/safe_sd
        # Portfolio excludes the candidate skill's self-link via zero diagonal.
        portfolio_scores=np.asarray(scores[lag])
        portfolio=(portfolio_scores/portfolio_scores.sum(axis=1)[:,None]/benchmark>=1).astype(np.float64)
        phi_sum=phi[:,chosen].sum(axis=0)
        rd=np.divide(portfolio@phi[:,chosen],phi_sum,
                     out=np.full((len(target),len(chosen)),np.nan),where=phi_sum>0)
        inst_codes,inst_labels=pd.factorize(unitids[source])
        inst_avg,inst_n=means(src_x,inst_codes,len(inst_labels))
        inst_pos=pd.Index(inst_labels).get_indexer(unitids[target])
        if (inst_pos<0).any():
            raise ValueError('El programa target no está incluido en los sources de t-1.')
        field_avg,field_n=means(src_x,field_ids[source],len(fields))
        n_inst=inst_n[inst_pos]-1
        n_field=field_n[field_ids[target]]-1
        n_other=len(source)-inst_n[inst_pos]-field_n[field_ids[target]]+1
        if (n_other<0).any() or not np.all(n_inst+n_field+n_other==len(source)-1):
            raise ValueError('Los denominadores de exposición no particionan los sources.')
        within_inst=np.divide(inst_avg[inst_pos]*inst_n[inst_pos,None]-x0,n_inst[:,None],
                    out=np.full_like(x0,np.nan),where=n_inst[:,None]>0)
        within_field=np.divide(field_avg[field_ids[target]]*field_n[field_ids[target],None]-x0,n_field[:,None],
                    out=np.full_like(x0,np.nan),where=n_field[:,None]>0)
        other_sum=src_x.sum(axis=0)-inst_avg[inst_pos]*inst_n[inst_pos,None]-field_avg[field_ids[target]]*field_n[field_ids[target],None]+x0
        other=np.divide(other_sum,n_other[:,None],out=np.full_like(x0,np.nan),where=n_other[:,None]>0)
        # The three disjoint channels must reconstruct total source score mass,
        # after adding the receiver's own previous profile exactly once.
        reconstructed=(np.nan_to_num(within_inst)*n_inst[:,None]+
                       np.nan_to_num(within_field)*n_field[:,None]+
                       np.nan_to_num(other)*n_other[:,None]+x0)
        if not np.allclose(reconstructed,src_x.sum(axis=0),rtol=1e-9,atol=1e-8):
            raise ValueError('Los canales de exposición no particionan los sources correctamente.')
        cols=len(chosen)
        frame=pd.DataFrame({
            'unitid':np.repeat(unitids[target],cols),'cell_id':np.repeat(cells[target],cols),
            'field_id':np.repeat(field_ids[target],cols),'year':y,
            'skill_id':np.tile(chosen,len(target)),
            'coverage_min':np.repeat(np.minimum(counts[lag],counts[target]),cols),
            'n_previous':np.repeat(counts[lag],cols),'n_current':np.repeat(counts[target],cols),
            'delta_score_z':outcome.ravel(),'lag_score_z':lag_z.ravel(),'rd':rd.ravel(),
            'same_inst_score_z':((within_inst-mu[chosen])/safe_sd).ravel(),
            'same_field_score_z':((within_field-mu[chosen])/safe_sd).ravel(),
            'other_score_z':((other-mu[chosen])/safe_sd).ravel(),
            'n_same_inst':np.repeat(n_inst,cols),'n_same_field':np.repeat(n_field,cols),
            'n_other':np.repeat(n_other,cols)})
        # Undefined channels stay missing and are reported, not imputed to zero.
        frame.to_csv(dest/f'continuous_{y}.csv.gz',index=False,compression='gzip')
        for k in (3,9):
            sub=frame[frame.coverage_min>=k]
            complete=sub.dropna(subset=['delta_score_z','lag_score_z','rd',
                'same_inst_score_z','same_field_score_z','other_score_z'])
            diagnostics.append({'year':y,'coverage':k,'observed_profile_pairs':int((np.minimum(counts[lag],counts[target])>=k).sum()),
                'sampled_skill_rows':len(sub),'complete_channel_rows':len(complete),
                'complete_program_pairs':int(complete.cell_id.nunique()),
                'complete_institutions':int(complete.unitid.nunique()),
                'complete_fields':int(complete.field_id.nunique()),
                'sampled_skills':int(sub.skill_id.nunique()),
                'mean_delta_score_z':float(sub.delta_score_z.mean())})
        print(f'Preparado {y}: {len(target):,} programas × {cols} DWAs muestreadas.',flush=True)
    pd.DataFrame(sampled).to_csv(OUT/'continuous_sampled_skills.csv',index=False)
    report=pd.DataFrame(diagnostics)
    report.to_csv(OUT/'continuous_design_coverage.csv',index=False)
    config={'seed':args.seed,'skills_per_year':args.skills_per_year,'sampling_mode':args.sampling,'evaluation_years':[2008,2017],
        'baseline_years':[2002,2007],'baseline_high_coverage_profiles':int(baseline.sum()),
        'network_programs':len(network_profiles),'network_eligibility':'>=2 baseline years, each >=9 syllabi',
        'network':'all-DWA co-specialization, min conditional probabilities, zero diagonal',
        'outcome':'change in zero-clipped inferred score / skill-specific baseline SD',
        'negative_source_scores_clipped':cache_manifest['negative_scores_clipped'],
        'exposure':'lagged average score across observed sources with >=3 syllabi, disjoint channels, self excluded',
        'sampling':f'uniform {args.skills_per_year} DWAs; {args.sampling} across years, shared across targets, independent of outcome and status',
        'primary_coverage':9,'sensitivity_coverage':3,
        'interpretation':'exploratory associations; no observed contact, adoption, transmission, or causal identification',
        'model_files':[f'continuous_{y}.csv.gz' for y in range(2008,2018)]}
    (OUT/'continuous_design.json').write_text(json.dumps(config,indent=2))
    (dest/'complete.json').write_text(json.dumps(config,indent=2))
    text='DISEÑO DEL PILOTO CONTINUO -- todavía sin estimar modelos\n\n'
    text+=f'Perfiles baseline >=9: {int(baseline.sum()):,}; programas en skill space: {len(network_profiles):,}.\n'
    text+='Espacio construido antes de 2008 con todas las DWAs; outcomes 2008--2017.\n'
    text+=f'Modelos: {args.skills_per_year} DWAs uniformemente muestreadas, modo {args.sampling}, semilla {args.seed}.\n'
    text+='Exposición = score medio previo de otros programas observados, no presencia ni transmisión.\n\n'
    text+=report.to_string(index=False,float_format=lambda v:f'{v:.5f}')+'\n'
    (OUT/'continuous_design_coverage.txt').write_text(text)
    print('\n'+text,flush=True)


if __name__=='__main__':
    main()
