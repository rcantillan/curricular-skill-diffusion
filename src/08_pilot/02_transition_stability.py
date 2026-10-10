"""Stage 1b: margins, two-year persistence, and program-level volatility.

No diffusion/fiscal models. Reuses the validated double-precision score cache.
Entrants' persistence is compared with skills specialized at BOTH t-1 and t.
Future coverage is used only for follow-up diagnostics, not main risk sets.
"""
from pathlib import Path
import csv
import gzip
import importlib.util
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/pilot'
DATA = ROOT / 'data/derived/pilot'
COVERAGE = (1, 3, 5, 9, 20, 50)
MARGINS = ((1.,1.), (.9,1.1), (.8,1.2))


def main():
    helper_path = Path(__file__).with_name('01_validate_measurement.py')
    spec = importlib.util.spec_from_file_location('measurement_helper', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    meta = pd.read_csv(DATA/'master_metadata.csv').sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.duplicated('id').any() or meta.duplicated(['unitid','fos','year']).any():
        raise ValueError('Metadata duplicada.')
    meta['cell_id'] = pd.factorize(pd.MultiIndex.from_frame(meta[['unitid','fos']]))[0]
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:
        skills = next(csv.reader(f))[1:]
    scores, _ = helper.load_scores(meta,skills)
    yy = meta.year.to_numpy()
    counts = meta.syllabi_cnt.to_numpy()
    cells = meta.cell_id.to_numpy()
    idx_year = {int(y):np.flatnonzero(yy==y) for y in sorted(np.unique(yy))}
    totals = np.empty(len(meta))
    benchmark = {}
    baseline_sum = np.zeros(len(skills))
    baseline_total = 0.
    for y,idx in idx_year.items():
        x = np.asarray(scores[idx])
        totals[idx] = x.sum(axis=1)
        if (totals[idx]<=0).any():
            raise ValueError(f'Perfil sin masa positiva en {y}.')
        col = x.sum(axis=0)
        if (col<=0).any():
            raise ValueError(f'Skill sin benchmark positivo en {y}.')
        benchmark[y] = col/totals[idx].sum()
        if y in (2000,2001):
            baseline_sum += col
            baseline_total += totals[idx].sum()
    fixed = baseline_sum/baseline_total
    previous_year = meta.groupby('cell_id',sort=False).year.shift().to_numpy()
    next_year = meta.groupby('cell_id',sort=False).year.shift(-1).to_numpy()
    second_year = meta.groupby('cell_id',sort=False).year.shift(-2).to_numpy()
    rows=[]
    program_rows=[]
    for y,idx in idx_year.items():
        if y<2002:
            continue
        target=idx[yy[idx]-previous_year[idx]==1]
        if not len(target):
            continue
        lag=target-1
        if not (cells[lag]==cells[target]).all():
            raise ValueError('La observación previa no corresponde al mismo programa.')
        x0,x1=np.asarray(scores[lag]),np.asarray(scores[target])
        share0,share1=x0/totals[lag,None],x1/totals[target,None]
        n_pairs=len(target)
        n1=np.zeros(n_pairs,dtype=int)
        n2=np.zeros(n_pairs,dtype=int)
        available1=next_year[target]==y+1
        available2=available1 & (second_year[target]==y+2)
        n1[available1]=counts[target[available1]+1]
        n2[available2]=counts[target[available2]+2]
        rc0,rc1=share0/benchmark[y-1],share1/benchmark[y]
        m0,m1=rc0>=1,rc1>=1
        entry,exit_=~m0&m1,m0&~m1
        norm0=np.linalg.norm(x0,axis=1)
        norm1=np.linalg.norm(x1,axis=1)
        cosine=1-(x0*x1).sum(axis=1)/(norm0*norm1)
        # Full-program continuous changes and rates, enabling within-cell checks.
        for j in range(n_pairs):
            a_risk=int((~m0[j]).sum()); b_risk=int(m0[j].sum())
            program_rows.append({
                'unitid':int(meta.unitid.iloc[target[j]]),'fos':meta.fos.iloc[target[j]],
                'cell_id':int(cells[target[j]]),'year':y,'sector':meta.sector.iloc[target[j]],
                'n_previous':int(counts[lag[j]]),'n_current':int(counts[target[j]]),
                'coverage_min':int(min(counts[lag[j]],counts[target[j]])),
                'adoption_risk':a_risk,'abandonment_risk':b_risk,
                'adoptions':int(entry[j].sum()),'abandonments':int(exit_[j].sum()),
                'adoption_rate':float(entry[j].sum()/a_risk) if a_risk else np.nan,
                'abandonment_rate':float(exit_[j].sum()/b_risk) if b_risk else np.nan,
                'mean_abs_delta_rca':float(np.abs(rc1[j]-rc0[j]).mean()),
                'mean_abs_delta_score':float(np.abs(x1[j]-x0[j]).mean()),
                'profile_cosine_change':float(np.clip(cosine[j],0,2))})
        for name,b in [('annual',None),('fixed_2000_2001',fixed)]:
            r0,r1=(rc0,rc1) if b is None else (share0/b,share1/b)
            f1=np.zeros((n_pairs,len(skills)),dtype=bool)
            f2=np.zeros_like(f1)
            ni=target[available1]+1
            if len(ni):
                f1[available1]=scores[ni]/totals[ni,None]/(benchmark[y+1] if b is None else b)>=1
            ni=target[available2]+2
            if len(ni):
                f2[available2]=scores[ni]/totals[ni,None]/(benchmark[y+2] if b is None else b)>=1
            for k in COVERAGE:
                eligible=(counts[lag]>=k)&(counts[target]>=k)
                if not eligible.any():
                    continue
                follow1=eligible&(n1>=k)
                follow2=follow1&(n2>=k)
                for low,high in MARGINS:
                    risk_a=r0<low
                    risk_b=r0>=high
                    a=risk_a&(r1>=high)
                    b_exit=risk_b&(r1<low)
                    # Stable-holder controls always use RCA >=1, not the margin.
                    stable=(r0>=1)&(r1>=1)
                    row={
                        'year':y,'coverage':k,'benchmark':name,'low':low,'high':high,
                        'profile_pairs':int(eligible.sum()),
                        'adoption_risk':int(risk_a[eligible].sum()),
                        'abandonment_risk':int(risk_b[eligible].sum()),
                        'adoptions':int(a[eligible].sum()),'abandonments':int(b_exit[eligible].sum()),
                        'entry_evaluable1':int(a[follow1].sum()),
                        'entry_retained1':int((a[follow1]&f1[follow1]).sum()),
                        'exit_evaluable1':int(b_exit[follow1].sum()),
                        'exit_retained1':int((b_exit[follow1]&~f1[follow1]).sum()),
                        'entry_evaluable2':int(a[follow2].sum()),
                        'entry_retained1_matched2':int((a[follow2]&f1[follow2]).sum()),
                        'entry_retained_both2':int((a[follow2]&f1[follow2]&f2[follow2]).sum()),
                        'exit_evaluable2':int(b_exit[follow2].sum()),
                        'exit_retained_both2':int((b_exit[follow2]&~f1[follow2]&~f2[follow2]).sum()),
                        'stable_evaluable1':int(stable[follow1].sum()),
                        'stable_retained1':int((stable[follow1]&f1[follow1]).sum()),
                        'stable_evaluable2':int(stable[follow2].sum()),
                        'stable_retained_both2':int((stable[follow2]&f1[follow2]&f2[follow2]).sum()),
                        'followup_profile_pairs1':int(follow1.sum()),
                        'followup_profile_pairs2':int(follow2.sum())}
                    rows.append(row)
        print(f'Procesado {y}: {n_pairs:,} pares consecutivos.',flush=True)
    detail=pd.DataFrame(rows)
    detail.to_csv(OUT/'stability_by_year.csv',index=False)
    programs=pd.DataFrame(program_rows)
    programs.to_csv(OUT/'program_transition_diagnostics.csv',index=False)
    keys=['coverage','benchmark','low','high']
    sums=[c for c in detail.columns if c not in keys+['year']]
    summary=detail.groupby(keys,as_index=False)[sums].sum()
    ratios={
        'entry_rate':('adoptions','adoption_risk'),
        'exit_rate':('abandonments','abandonment_risk'),
        'entry_survival1':('entry_retained1','entry_evaluable1'),
        'exit_survival1':('exit_retained1','exit_evaluable1'),
        'entry_survival1_matched2':('entry_retained1_matched2','entry_evaluable2'),
        'entry_survival_both2':('entry_retained_both2','entry_evaluable2'),
        'exit_survival_both2':('exit_retained_both2','exit_evaluable2'),
        'stable_survival1':('stable_retained1','stable_evaluable1'),
        'stable_survival_both2':('stable_retained_both2','stable_evaluable2')}
    for label,(num,den) in ratios.items():
        summary[label]=summary[num]/summary[den].replace(0,np.nan)
    # Numerical reconciliation: exact same annual, all-DWA sample as Stage 1.
    old=pd.read_csv(OUT/'measurement_summary.csv')
    old=old[(old.universe=='all_dwas')&(old.pair_type=='annual')]
    new=summary[(summary.benchmark=='annual')&(summary.low==1)&(summary.high==1)]
    check=old.merge(new,on='coverage',suffixes=('_old','_new'),validate='one_to_one')
    if len(check)!=4:
        raise ValueError('No se pudieron reconciliar los cuatro cortes de Stage 1.')
    for col in ['profile_pairs','adoptions','abandonments','adoption_risk','abandonment_risk']:
        if not np.array_equal(check[f'{col}_old'],check[f'{col}_new']):
            raise ValueError(f'Conteos Stage 1/1b inconsistentes: {col}')
    summary.to_csv(OUT/'stability_summary.csv',index=False)
    output=['ESTABILIDAD DE TRANSICIONES -- sin modelos de difusion o recursos',
            'Ventana principal: 2002--2017; todas las DWAs.',
            'Conteos anuales estándar reconciliados exactamente con Stage 1.',
            'Persistencia a dos años exige conservar el estado en t+1 Y t+2.',
            'Las columnas de seguimiento se condicionan a observación y cobertura futuras.',
            'No representan probabilidades de persistencia de toda la muestra.','']
    cols=['coverage','profile_pairs','low','high','entry_rate','exit_rate',
          'entry_survival1','entry_survival_both2','stable_survival1','stable_survival_both2',
          'entry_evaluable1','entry_evaluable2']
    for benchmark_name in ['annual','fixed_2000_2001']:
        output.append('BENCHMARK: '+benchmark_name)
        output.append(summary[summary.benchmark==benchmark_name][cols].to_string(index=False,float_format=lambda v:f'{v:.4f}'))
        output.append('')
    output.append('Los márgenes modifican también el conjunto en riesgo: no comparar las tasas como si los denominadores fueran iguales.')
    output.append('Stable = skills especializadas tanto en t-1 como en t; es un contraste descriptivo, no un contrafactual causal.')
    text='\n'.join(output)+'\n'
    (OUT/'stability_summary.txt').write_text(text)
    (OUT/'stability_config.json').write_text(json.dumps({
        'outcome_window':[2002,2017],'coverage':list(COVERAGE),
        'margin_rules':[{'previous_below':lo,'current_at_least':hi} for lo,hi in MARGINS],
        'followup_diagnostics':'future observation and same coverage required; attrition not assumed random',
        'stable_controls':'specialized at t-1 and t',
        'interpretation':'descriptive stability, not measurement error identification'},indent=2))
    print('\n'+text,flush=True)


if __name__=='__main__':
    main()
