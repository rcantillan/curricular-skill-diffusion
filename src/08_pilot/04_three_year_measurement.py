"""Temporal aggregation sensitivity; not annual adoption and not fiscal DiD.

Five nonoverlapping three-year periods: 2002--04, 2005--07, 2008--10,
2011--13, 2014--16. Public profile means are pooled using syllabi_cnt.
Require observations in >=2 or all 3 distinct years per period. Coverage
thresholds apply to TOTAL syllabi per period, unlike the previous annual k.
No assumption of independent syllabi: raw course identities are unavailable.
"""
from pathlib import Path
import csv
import gzip
import importlib.util
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'data/derived/pilot'
OUT = ROOT/'outputs/pilot'
PERIODS = ('2002–2004','2005–2007','2008–2010','2011–2013','2014–2016')
COVERAGE = (9,20,50)
YEAR_COUNTS = (2,3)


def pair_stats(p0,p1,valid,rca,raw,totals,follow,follow_ok):
    i0,i1=p0[valid],p1[valid]
    x0,x1=rca[i0],rca[i1]
    m0,m1=x0>=1,x1>=1
    entry,exit_=~m0&m1,m0&~m1
    stable=m0&m1
    count=int(valid.sum())
    has_follow=follow_ok[valid]
    i2=follow[valid][has_follow]
    f=rca[i2]>=1
    raw0,raw1=raw[i0],raw[i1]
    denom=np.linalg.norm(raw0,axis=1)*np.linalg.norm(raw1,axis=1)
    cosine=1-(raw0*raw1).sum(axis=1)/denom
    return {
        'program_pairs':count,'skill_opportunities':int(count*rca.shape[1]),
        'entry_risk':int((~m0).sum()),'exit_risk':int(m0.sum()),
        'entries':int(entry.sum()),'exits':int(exit_.sum()),
        'sum_abs_delta_fixed_rca':float(np.abs(x1-x0).sum()),
        'sum_abs_delta_score':float(np.abs(raw1-raw0).sum()),
        'sum_profile_cosine_change':float(np.clip(cosine,0,2).sum()),
        'followup_program_pairs':int(has_follow.sum()),
        'entry_followup_evaluable':int(entry[has_follow].sum()),
        'entry_followup_retained':int((entry[has_follow]&f).sum()),
        'stable_followup_evaluable':int(stable[has_follow].sum()),
        'stable_followup_retained':int((stable[has_follow]&f).sum())}


def main():
    spec=importlib.util.spec_from_file_location('measurement_helper',Path(__file__).with_name('01_validate_measurement.py'))
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    meta=pd.read_csv(DATA/'master_metadata.csv').sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.duplicated('id').any() or meta.duplicated(['unitid','fos','year']).any():
        raise ValueError('Metadata duplicada.')
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:
        skills=next(csv.reader(f))[1:]
    scores,_=helper.load_scores(meta,skills)
    meta['cell_id']=pd.factorize(pd.MultiIndex.from_frame(meta[['unitid','fos']]))[0]
    sel=(meta.year>=2002)&(meta.year<=2016)
    selected=np.flatnonzero(sel.to_numpy())
    sub=meta.iloc[selected].copy()
    sub['period_id']=((sub.year-2002)//3).astype(int)
    sub['period_profile']=pd.factorize(pd.MultiIndex.from_frame(sub[['cell_id','period_id']]))[0]
    groups=sub.groupby('period_profile',sort=True).agg(
        unitid=('unitid','first'),fos=('fos','first'),cell_id=('cell_id','first'),
        period_id=('period_id','first'),syllabi_total=('syllabi_cnt','sum'),
        observed_years=('year','nunique'),min_annual_syllabi=('syllabi_cnt','min')).reset_index()
    group_ids=sub.period_profile.to_numpy()
    pooled=np.zeros((len(groups),len(skills)),dtype=np.float64)
    for y in sorted(sub.year.unique()):
        take=sub.year.to_numpy()==y
        weights=sub.syllabi_cnt.to_numpy()[take]
        np.add.at(pooled,group_ids[take],scores[selected[take]]*weights[:,None])
        print(f'Agregado {y}.',flush=True)
    pooled/=groups.syllabi_total.to_numpy()[:,None]
    totals=pooled.sum(axis=1)
    if (totals<=0).any():
        raise ValueError('Perfil agregado sin masa positiva.')
    share=pooled/totals[:,None]
    groups['period']=groups.period_id.map(dict(enumerate(PERIODS)))
    # Index lookup encodes only observed program-period combinations.
    lookup={(int(c),int(p)):i for i,(c,p) in enumerate(zip(groups.cell_id,groups.period_id))}
    coverage_rows=[]
    detail=[]
    benchmark_rows=[]
    for n_years in YEAR_COUNTS:
        baseline=(groups.period_id.to_numpy()==0)&(groups.observed_years.to_numpy()>=n_years)&(groups.syllabi_total.to_numpy()>=9)
        if not baseline.any():
            raise ValueError('Baseline sin perfiles elegibles.')
        # Equal weight per pooled program; no changing system reference over time.
        bench=pooled[baseline].sum(axis=0)/totals[baseline].sum()
        if (bench<=0).any():
            raise ValueError('Skill sin benchmark positivo.')
        rca=share/bench
        benchmark_rows.append({'min_observed_years':n_years,'baseline_programs':int(baseline.sum()),
                               'baseline_fields':int(groups.loc[baseline,'fos'].nunique())})
        for k in COVERAGE:
            eligible=(groups.observed_years.to_numpy()>=n_years)&(groups.syllabi_total.to_numpy()>=k)
            for p in range(5):
                keep=eligible&(groups.period_id.to_numpy()==p)
                coverage_rows.append({'min_observed_years':n_years,'min_total_syllabi':k,'period':PERIODS[p],
                                      'programs':int(keep.sum()),'institutions':int(groups.loc[keep,'unitid'].nunique()),
                                      'fields':int(groups.loc[keep,'fos'].nunique())})
            for p in range(1,5):
                idx=np.flatnonzero(groups.period_id.to_numpy()==p)
                prior=np.array([lookup.get((int(groups.cell_id.iloc[i]),p-1),-1) for i in idx])
                follow=np.array([lookup.get((int(groups.cell_id.iloc[i]),p+1),-1) for i in idx])
                valid=(prior>=0)&eligible[idx]
                valid&=eligible[np.maximum(prior,0)]
                follow_ok=(follow>=0)&eligible[np.maximum(follow,0)]
                if not valid.any():
                    continue
                row=pair_stats(prior,idx,valid,rca,pooled,totals,follow,follow_ok)
                row.update({'min_observed_years':n_years,'min_total_syllabi':k,
                            'previous_period':PERIODS[p-1],'current_period':PERIODS[p]})
                detail.append(row)
                # Exact same samples for continuous program-level outcomes.
                if n_years==2 and k==9:
                    before,after=prior[valid],idx[valid]
                    subprogram=pd.DataFrame({
                        'unitid':groups.unitid.to_numpy()[after],'fos':groups.fos.to_numpy()[after],
                        'cell_id':groups.cell_id.to_numpy()[after],'period_id':p,
                        'previous_syllabi_total':groups.syllabi_total.to_numpy()[before],
                        'current_syllabi_total':groups.syllabi_total.to_numpy()[after],
                        'mean_abs_delta_fixed_rca':np.abs(rca[after]-rca[before]).mean(axis=1),
                        'mean_abs_delta_score':np.abs(pooled[after]-pooled[before]).mean(axis=1)})
                    subprogram.to_csv(OUT/f'block_program_changes_{p}.csv',index=False)
    details=pd.DataFrame(detail)
    details.to_csv(OUT/'block_measurement_by_period.csv',index=False)
    pd.DataFrame(coverage_rows).to_csv(OUT/'block_coverage.csv',index=False)
    pd.DataFrame(benchmark_rows).to_csv(OUT/'block_benchmark_coverage.csv',index=False)
    groups.to_csv(OUT/'block_profile_metadata.csv',index=False)
    keys=['min_observed_years','min_total_syllabi']
    numeric=[c for c in details.columns if c not in keys+['previous_period','current_period']]
    result=details.groupby(keys,as_index=False)[numeric].sum()
    ratios={
        'entry_rate_per_period':('entries','entry_risk'),
        'exit_rate_per_period':('exits','exit_risk'),
        'entry_survival_next_period':('entry_followup_retained','entry_followup_evaluable'),
        'stable_survival_next_period':('stable_followup_retained','stable_followup_evaluable'),
        'mean_abs_delta_fixed_rca':('sum_abs_delta_fixed_rca','skill_opportunities'),
        'mean_abs_delta_score':('sum_abs_delta_score','skill_opportunities'),
        'mean_profile_cosine_change':('sum_profile_cosine_change','program_pairs')}
    for col,(a,b) in ratios.items():
        result[col]=result[a]/result[b].replace(0,np.nan)
    result.to_csv(OUT/'block_measurement_summary.csv',index=False)
    cols=keys+['program_pairs','entries','entry_rate_per_period','exit_rate_per_period',
               'entry_survival_next_period','stable_survival_next_period',
               'entry_followup_evaluable','mean_abs_delta_fixed_rca','mean_profile_cosine_change']
    text='SENSIBILIDAD A PERIODOS DE TRES AÑOS -- no tasas anuales\n\n'
    text+='Periodos: '+', '.join(PERIODS)+'.\n2017 queda fuera para evitar un periodo incompleto.\n'
    text+='Cobertura = total de syllabi del periodo; no equivale a k syllabi cada año.\n'
    text+='Benchmark fijo 2002--2004, construido con >=9 syllabi y el mínimo de años de cada especificación.\n'
    text+='Seguimiento = especialización en el siguiente periodo observado consecutivo y elegible.\n\n'
    text+=result[cols].to_string(index=False,float_format=lambda x:f'{x:.5f}')+'\n\n'
    text+='La agregación puede suavizar variación y cambios reales. No identifica por sí sola error de muestreo.\n'
    text+='Los millones de skill-events no son observaciones independientes.\n'
    (OUT/'block_measurement_summary.txt').write_text(text)
    (OUT/'block_measurement_config.json').write_text(json.dumps({
        'periods':list(PERIODS),'pooling':'syllabi_cnt-weighted public means',
        'coverage':'total syllabi per period, required at both endpoints',
        'min_observed_years':list(YEAR_COUNTS),'min_total_syllabi':list(COVERAGE),
        'baseline':'2002--2004, >=9 syllabi, year-count requirement specific to specification',
        'no_independence_assumption':'unknown course identities and overlap across years',
        'no_models_estimated':['diffusion','resources']},indent=2))
    print('\n'+text,flush=True)


if __name__=='__main__':
    main()
