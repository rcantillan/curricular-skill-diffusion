"""Explore high inferred score versus relative specialization.

Percentile thresholds are descriptive sensitivities, NOT validated presence.
Train thresholds and fixed RCA reference using >=9-syllabus profiles from
2002--2007 only; evaluate 2008--2017. Treat two binary measurements as four
joint states; do not force them into an ordered three-state sequence.
No models, maturation lags, or causal claims are estimated.
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
QUANTILES = (.50,.75,.90,.95)
COVERAGE = (1,3,5,9)
STATE_LABELS = (
    'low_score_not_specialized', 'high_score_not_specialized',
    'low_score_specialized', 'high_score_specialized')


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('measurement_helper',Path(__file__).with_name('01_validate_measurement.py'))
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    meta=pd.read_csv(DATA/'master_metadata.csv').sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.duplicated('id').any() or meta.duplicated(['unitid','fos','year']).any():
        raise ValueError('Metadata duplicada.')
    meta['cell_id']=pd.factorize(pd.MultiIndex.from_frame(meta[['unitid','fos']]))[0]
    with gzip.open(ROOT/'data/raw/detailed_work_activities_scores.gzip','rt') as f:
        skills=next(csv.reader(f))[1:]
    scores,_=helper.load_scores(meta,skills)
    years=meta.year.to_numpy()
    counts=meta.syllabi_cnt.to_numpy()
    base=(years>=2002)&(years<=2007)&(counts>=9)
    base_idx=np.flatnonzero(base)
    if not len(base_idx):
        raise ValueError('No hay perfiles elegibles para calibración descriptiva.')
    baseline=np.asarray(scores[base_idx])
    threshold=np.quantile(baseline,QUANTILES,axis=0)
    fixed=baseline.sum(axis=0)/baseline.sum()
    if (fixed<=0).any():
        raise ValueError('Alguna DWA no tiene referencia positiva.')
    distribution=pd.DataFrame({'skill_id':range(len(skills)),'skill':skills,
                               'baseline_mean':baseline.mean(axis=0),
                               'baseline_sd':baseline.std(axis=0),
                               'baseline_min':baseline.min(axis=0),
                               'baseline_max':baseline.max(axis=0),
                               'baseline_zero_fraction':(baseline==0).mean(axis=0)})
    for j,q in enumerate(QUANTILES):
        distribution[f'threshold_q{int(q*100)}']=threshold[j]
        # Ties can make prevalence differ from 1-q; report actual baseline rate.
        distribution[f'baseline_high_fraction_q{int(q*100)}']=(baseline>=threshold[j]).mean(axis=0)
    distribution.to_csv(OUT/'score_thresholds_exploratory.csv',index=False)
    del baseline
    previous=meta.groupby('cell_id',sort=False).year.shift().to_numpy()
    future=meta.groupby('cell_id',sort=False).year.shift(-1).to_numpy()
    state_rows=[]
    flow_rows=[]
    event_rows=[]
    for y in range(2008,2018):
        current_idx=np.flatnonzero(years==y)
        if not len(current_idx):
            continue
        current=np.asarray(scores[current_idx])
        totals=current.sum(axis=1)
        if (totals<=0).any():
            raise ValueError(f'Perfil sin masa positiva en {y}.')
        specialized=current/totals[:,None]/fixed>=1
        annual=(years[current_idx]-previous[current_idx])==1
        target=current_idx[annual]
        lag=target-1
        old=np.asarray(scores[lag])
        old_specialized=old/old.sum(axis=1)[:,None]/fixed>=1
        new=current[annual]
        new_specialized=specialized[annual]
        next_observed=future[target]==y+1
        next_coverage=np.zeros(len(target),dtype=int)
        next_coverage[next_observed]=counts[target[next_observed]+1]
        next_scores=np.zeros((len(target),len(skills)))
        if next_observed.any():
            next_scores[next_observed]=scores[target[next_observed]+1]
        for j,q in enumerate(QUANTILES):
            high=current>=threshold[j]
            state=high.astype(np.uint8)+2*specialized.astype(np.uint8)
            old_high=old>=threshold[j]
            new_high=new>=threshold[j]
            old_state=old_high.astype(np.uint8)+2*old_specialized.astype(np.uint8)
            new_state=new_high.astype(np.uint8)+2*new_specialized.astype(np.uint8)
            for k in COVERAGE:
                eligible=counts[current_idx]>=k
                if eligible.any():
                    n=int(eligible.sum())
                    for code,label in enumerate(STATE_LABELS):
                        state_rows.append({'year':y,'quantile':q,'coverage':k,'profiles':n,
                            'state':label,'state_code':code,'count':int((state[eligible]==code).sum()),
                            'opportunities':n*len(skills)})
                pairs=(counts[lag]>=k)&(counts[target]>=k)
                if not pairs.any():
                    continue
                encoded=(4*old_state[pairs]+new_state[pairs]).ravel()
                matrix=np.bincount(encoded,minlength=16).reshape(4,4)
                if int(matrix.sum()) != int(pairs.sum())*len(skills):
                    raise ValueError('Las transiciones no agotan el universo observado.')
                for source in range(4):
                    for destination in range(4):
                        flow_rows.append({'year':y,'quantile':q,'coverage':k,
                            'from_state':STATE_LABELS[source],'to_state':STATE_LABELS[destination],
                            'count':int(matrix[source,destination]),
                            'source_opportunities':int(matrix[source].sum())})
                entry=(~old_high)&new_high
                exit_=old_high&(~new_high)
                follow=pairs&next_observed&(next_coverage>=k)
                remains_high=next_scores>=threshold[j]
                # Consolidation candidate requires high score in both endpoints.
                present_not_special=old_high&(~old_specialized)
                consolidated=present_not_special&new_high&new_specialized
                event_rows.append({'year':y,'quantile':q,'coverage':k,
                    'profile_pairs':int(pairs.sum()),
                    'high_score_entry_risk':int((~old_high[pairs]).sum()),
                    'high_score_entries':int(entry[pairs].sum()),
                    'high_score_exit_risk':int(old_high[pairs].sum()),
                    'high_score_exits':int(exit_[pairs].sum()),
                    'high_score_entries_followup':int(entry[follow].sum()),
                    'high_score_entries_retained':int((entry[follow]&remains_high[follow]).sum()),
                    'high_score_specialization_risk':int(present_not_special[pairs].sum()),
                    'high_score_specializations':int(consolidated[pairs].sum()),
                    'low_to_high_specialized':int(((old_state[pairs]==0)&(new_state[pairs]==3)).sum())})
        print(f'Procesado {y}: {len(current_idx):,} perfiles; {len(target):,} pares anuales.',flush=True)
    states=pd.DataFrame(state_rows)
    flows=pd.DataFrame(flow_rows)
    events=pd.DataFrame(event_rows)
    states.to_csv(OUT/'score_joint_states_by_year.csv',index=False)
    flows.to_csv(OUT/'score_joint_transitions_by_year.csv',index=False)
    events.to_csv(OUT/'score_entries_by_year.csv',index=False)
    state_summary=states.groupby(['quantile','coverage','state','state_code'],as_index=False)[['count','opportunities']].sum()
    state_summary['fraction']=state_summary['count']/state_summary['opportunities']
    fractions=state_summary.groupby(['quantile','coverage'])['fraction'].sum()
    if not np.allclose(fractions.to_numpy(),1.,rtol=0,atol=1e-12):
        raise ValueError('Los cuatro estados no suman uno.')
    state_summary.to_csv(OUT/'score_joint_states_summary.csv',index=False)
    transition_summary=flows.groupby(['quantile','coverage','from_state','to_state'],as_index=False)[['count','source_opportunities']].sum()
    transition_summary['transition_fraction']=transition_summary['count']/transition_summary['source_opportunities'].replace(0,np.nan)
    transition_summary.to_csv(OUT/'score_joint_transitions_summary.csv',index=False)
    event_numeric=[c for c in events.columns if c not in ['year','quantile','coverage']]
    event_summary=events.groupby(['quantile','coverage'],as_index=False)[event_numeric].sum()
    for label,(a,b) in {
        'high_score_entry_rate':('high_score_entries','high_score_entry_risk'),
        'high_score_exit_rate':('high_score_exits','high_score_exit_risk'),
        'high_score_entry_survival1':('high_score_entries_retained','high_score_entries_followup'),
        'specialization_given_high_score_rate':('high_score_specializations','high_score_specialization_risk')}.items():
        event_summary[label]=event_summary[a]/event_summary[b].replace(0,np.nan)
    event_summary.to_csv(OUT/'score_entries_summary.csv',index=False)
    wide=state_summary.pivot(index=['quantile','coverage'],columns='state',values='fraction').reset_index()
    wide['low_score_share_of_specialized']=wide.low_score_specialized/(wide.low_score_specialized+wide.high_score_specialized)
    joint=wide.merge(event_summary,on=['quantile','coverage'],validate='one_to_one')
    selected_columns=['quantile','coverage','low_score_not_specialized','high_score_not_specialized',
        'low_score_specialized','high_score_specialized','low_score_share_of_specialized',
        'high_score_entry_rate','high_score_entry_survival1','specialization_given_high_score_rate',
        'high_score_entries_followup','low_to_high_specialized']
    text='SCORES Y ESPECIALIZACION -- umbrales exploratorios, NO presencia validada\n\n'
    text+=f'Baseline: 2002--2007, >=9 syllabi; {len(base_idx):,} perfiles.\n'
    text+='Evaluación: 2008--2017; benchmark RCA y umbrales fijos entrenados solo en baseline.\n'
    text+='Cuatro estados conjuntos: score bajo/alto × RCA bajo/alto.\n'
    text+='Los percentiles NO acreditan aparición, enseñanza efectiva ni aprendizaje.\n\n'
    text+=joint[selected_columns].to_string(index=False,float_format=lambda v:f'{v:.5f}')+'\n\n'
    text+='La persistencia requiere observación t+1 con la misma cobertura; 2017 no es evaluable.\n'
    text+='low_to_high_specialized cuenta saltos directos desde bajo score/no especializado hacia alto score/especializado.\n'
    text+='La proporción low_score_share_of_specialized diagnostica si los estados de tres niveles serían anidados.\n'
    text+='No se estiman maturation lags: primero requieren validar estados, censura y episodios.\n'
    (OUT/'score_joint_summary.txt').write_text(text)
    (OUT/'score_threshold_config.json').write_text(json.dumps({
        'baseline_years':[2002,2007],'baseline_min_syllabi':9,'baseline_profiles':int(len(base_idx)),
        'evaluation_years':[2008,2017],'quantiles':list(QUANTILES),'threshold_rule':'score >= fixed baseline quantile per DWA',
        'reference_weighting':'equal public profiles; longitudinal repeats included',
        'specialization':'fixed pooled baseline RCA >=1',
        'interpretation':'high inferred semantic score, not validated curricular presence',
        'joint_states':list(STATE_LABELS),'future_observation':'required only for persistence sensitivity',
        'left_censoring':'baseline high states are not dated first appearances'},indent=2))
    print('\n'+text,flush=True)


if __name__=='__main__':
    main()
