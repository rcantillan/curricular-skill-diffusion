"""Stage 1: annual transition and coverage audit, without diffusion models.

Run from any directory. Reads public aggregated Atlas scores; never overwrites
legacy events or manuscript tables. Uses all DWAs and reports the historical
100-skill selection separately. A fixed 2000--2001 benchmark is evaluated only
for outcomes from 2002 onward. Zero scores remain observed zeros; missing
profiles are excluded. Scores are clipped at zero to match legacy script 03a.
"""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/derived/pilot'
OUT = ROOT / 'outputs/pilot'
THRESHOLDS = (1, 3, 5, 9)


def load_scores(meta, skills):
    """Disk-backed double precision cache; publish only after a complete read."""
    raw = ROOT / 'data/raw/detailed_work_activities_scores.gzip'
    path = DATA / 'measurement_scores_float64.npy'
    stamp_path = DATA / 'measurement_scores_manifest.json'
    signature = {
        'shape': [len(meta), len(skills)], 'dtype': 'float64',
        'ids_sha256': hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest(),
        'skills_sha256': hashlib.sha256('\n'.join(skills).encode()).hexdigest(),
        'source_bytes': raw.stat().st_size, 'source_mtime_ns': raw.stat().st_mtime_ns,
    }
    if path.exists() and stamp_path.exists():
        cached = json.loads(stamp_path.read_text())
        if all(cached.get(k) == v for k, v in signature.items()):
            print('Reutilizando cache completo de scores.', flush=True)
            return np.load(path, mmap_mode='r'), cached
    temp = DATA / 'measurement_scores_float64.building.npy'
    scores = np.lib.format.open_memmap(temp, mode='w+', dtype='float64',
                                      shape=(len(meta), len(skills)))
    scores[:] = np.nan
    positions = pd.Series(np.arange(len(meta)), index=meta.id)
    seen = np.zeros(len(meta), dtype=bool)
    clipped = 0
    for batch, chunk in enumerate(pd.read_csv(raw, compression='gzip', chunksize=1000), 1):
        if list(chunk.columns[1:]) != skills:
            raise ValueError('El orden de skills del archivo fuente cambió.')
        loc = positions.reindex(chunk.iloc[:, 0]).to_numpy()
        keep = np.flatnonzero(~pd.isna(loc))
        ix = loc[keep].astype(np.int64)
        if len(np.unique(ix)) != len(ix) or seen[ix].any():
            raise ValueError('ID duplicado en la matriz fuente.')
        values = chunk.iloc[keep, 1:].to_numpy(dtype=np.float64)
        if not np.isfinite(values).all():
            raise ValueError('Scores faltantes o no finitos: no se imputan como cero.')
        clipped += int((values < 0).sum())
        scores[ix] = np.maximum(values, 0)
        seen[ix] = True
        if batch % 25 == 0:
            print(f'Lectura: {batch * 1000:,} perfiles fuente; {seen.sum():,} vinculados.', flush=True)
    if not seen.all():
        raise ValueError(f'Faltan scores de {int((~seen).sum())} perfiles analíticos.')
    scores.flush()
    del scores
    temp.replace(path)
    signature['negative_scores_clipped'] = clipped
    stamp_path.write_text(json.dumps(signature, indent=2))
    return np.load(path, mmap_mode='r'), signature


def summarize(year, coverage, universe, pair_type, keep, mask, r0, r1,
              x0, x1, share0, share1, fixed_benchmark, raw_baseline,
              next_state, next_counts):
    n_pairs = int(keep.sum())
    n_skills = int(mask.sum())
    if not n_pairs or not n_skills:
        return None
    select = np.ix_(keep, mask)
    a0, a1 = r0[select], r1[select]
    m0, m1 = a0 >= 1, a1 >= 1
    entry, exit_ = ~m0 & m1, m0 & ~m1
    n_entry, n_exit = int(entry.sum()), int(exit_.sum())
    risk_entry, risk_exit = int((~m0).sum()), int(m0.sum())
    dx = x1[select] - x0[select]
    ds = share1[select] - share0[select]
    dr = a1 - a0
    row = {
        'year': year, 'coverage': coverage, 'universe': universe, 'pair_type': pair_type,
        'profile_pairs': n_pairs, 'skills': n_skills, 'opportunities': n_pairs * n_skills,
        'adoption_risk': risk_entry, 'abandonment_risk': risk_exit,
        'adoptions': n_entry, 'abandonments': n_exit,
        'sum_delta_rca': float(dr.sum()), 'sum_abs_delta_rca': float(np.abs(dr).sum()),
        'sum_delta_score': float(dx.sum()), 'sum_abs_delta_score': float(np.abs(dx).sum()),
        'adoptions_score_increases': int((entry & (dx > 0)).sum()),
        'adoptions_share_increases': int((entry & (ds > 0)).sum()),
        'abandonments_score_decreases': int((exit_ & (dx < 0)).sum()),
        'fixed_adoption_risk': 0, 'fixed_abandonment_risk': 0,
        'fixed_adoptions': 0, 'fixed_abandonments': 0, 'fixed_opportunities': 0,
        'sum_delta_fixed_rca': 0., 'sum_abs_delta_fixed_rca': 0.,
        'sum_delta_score_baseline_units': 0.,
        'persistent_entry_evaluable': 0, 'persistent_entries': 0,
        'persistent_exit_evaluable': 0, 'persistent_exits': 0,
    }
    if year >= 2002:
        f0 = share0[select] / fixed_benchmark[mask]
        f1 = share1[select] / fixed_benchmark[mask]
        fm0, fm1 = f0 >= 1, f1 >= 1
        row.update({
            'fixed_opportunities': n_pairs * n_skills,
            'fixed_adoption_risk': int((~fm0).sum()), 'fixed_abandonment_risk': int(fm0.sum()),
            'fixed_adoptions': int((~fm0 & fm1).sum()), 'fixed_abandonments': int((fm0 & ~fm1).sum()),
            'sum_delta_fixed_rca': float((f1-f0).sum()),
            'sum_abs_delta_fixed_rca': float(np.abs(f1-f0).sum()),
            'sum_delta_score_baseline_units': float((dx / raw_baseline[mask]).sum()),
        })
    # Persistence is only judged when t+1 is observed and passes the same k.
    # It is a sensitivity, not a way to condition the main sample on the future.
    valid_next = keep & (next_counts >= coverage)
    local_next = valid_next[keep]
    if local_next.any():
        m2 = next_state[np.ix_(valid_next, mask)]
        entry_eval, exit_eval = entry[local_next], exit_[local_next]
        row.update({
            'persistent_entry_evaluable': int(entry_eval.sum()),
            'persistent_entries': int((entry_eval & m2).sum()),
            'persistent_exit_evaluable': int(exit_eval.sum()),
            'persistent_exits': int((exit_eval & ~m2).sum()),
        })
    return row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    metadata_path = DATA / 'master_metadata.csv'
    if not metadata_path.exists():
        raise FileNotFoundError('Ejecuta primero Rscript src/08_pilot/00_audit_panel.R')
    meta = pd.read_csv(metadata_path).sort_values(['unitid', 'fos', 'year']).reset_index(drop=True)
    if meta.duplicated('id').any() or meta.duplicated(['unitid','fos','year']).any():
        raise ValueError('Llaves duplicadas en metadata.')
    meta['cell_id'] = pd.factorize(pd.MultiIndex.from_frame(meta[['unitid','fos']]))[0]
    with gzip.open(ROOT / 'data/raw/detailed_work_activities_scores.gzip', 'rt') as f:
        skills = next(csv.reader(f))[1:]
    scores, cache_manifest = load_scores(meta, skills)
    totals = np.empty(len(meta))
    years = meta.year.to_numpy()
    counts = meta.syllabi_cnt.to_numpy()
    year_idx = {int(y): np.flatnonzero(years == y) for y in sorted(np.unique(years))}
    benchmarks = {}
    baseline_sum = np.zeros(len(skills))
    baseline_profile_count = 0
    baseline_total = 0.
    for y, idx in year_idx.items():
        x = np.asarray(scores[idx])
        totals[idx] = x.sum(axis=1)
        if (totals[idx] <= 0).any():
            raise ValueError('Perfil sin masa positiva de scores.')
        colsum = x.sum(axis=0)
        if (colsum <= 0).any():
            raise ValueError(f'Skill sin benchmark positivo en {y}; requiere universo explícito.')
        benchmarks[y] = colsum / totals[idx].sum()
        if y in (2000,2001):
            baseline_sum += colsum
            baseline_total += totals[idx].sum()
            baseline_profile_count += len(idx)
    fixed_benchmark = baseline_sum / baseline_total
    raw_baseline = baseline_sum / baseline_profile_count
    if (raw_baseline <= 0).any():
        raise ValueError('Skill sin score positivo en baseline 2000--2001.')
    previous_year = meta.groupby('cell_id', sort=False).year.shift().to_numpy()
    gap = years - previous_year
    next_year = meta.groupby('cell_id', sort=False).year.shift(-1).to_numpy()
    next_idx = np.arange(len(meta)) + 1
    has_next = next_year - years == 1
    frontier = set(pd.read_csv(ROOT / 'data/interim/top_skills_baseline.csv')['skill'])
    if not frontier.issubset(set(skills)):
        raise ValueError('La selección histórica contiene skills ajenas al archivo fuente.')
    universes = {'all_dwas': np.ones(len(skills),dtype=bool),
                 'legacy_top100': np.array([s in frontier for s in skills])}
    rows = []
    for y, idx in year_idx.items():
        target = idx[np.isfinite(gap[idx])]
        if not len(target):
            continue
        previous = target - 1
        assert (meta.cell_id.to_numpy()[previous] == meta.cell_id.to_numpy()[target]).all()
        x0, x1 = np.asarray(scores[previous]), np.asarray(scores[target])
        s0, s1 = x0/totals[previous,None], x1/totals[target,None]
        # Previous-observation sensitivity uses that observation's own year.
        b0 = np.stack([benchmarks[int(v)] for v in years[previous]])
        r0, r1 = s0/b0, s1/benchmarks[y]
        followup_counts = np.zeros(len(target),dtype=int)
        followup_state = np.zeros(r1.shape,dtype=bool)
        followup = has_next[target]
        ni = next_idx[target[followup]]
        if followup.any():
            followup_counts[followup] = counts[ni]
            followup_state[followup] = scores[ni]/totals[ni,None]/benchmarks[y+1] >= 1
        for k in THRESHOLDS:
            coverage = (counts[target] >= k) & (counts[previous] >= k)
            for pair_type, eligible in [('annual', gap[target]==1),
                                        ('gap_interval_not_annual', gap[target]>1)]:
                keep = coverage & eligible
                for universe, mask in universes.items():
                    row = summarize(y,k,universe,pair_type,keep,mask,r0,r1,x0,x1,s0,s1,
                                    fixed_benchmark,raw_baseline,followup_state,followup_counts)
                    if row is not None:
                        rows.append(row)
        print(f'Procesado {y}: {(gap[target]==1).sum():,} pares anuales; '
              f'{(gap[target]>1).sum():,} intervalos con gaps.',flush=True)
    by_year = pd.DataFrame(rows)
    by_year.to_csv(OUT/'measurement_by_year.csv',index=False)
    keys = ['coverage','universe','pair_type']
    # Skill count is fixed within universe; only additive quantities are summed.
    additive = [c for c in by_year.columns if c not in keys+['year','skills']]
    # Compare moving and fixed benchmarks over the SAME outcome window.
    # 2001 remains in by_year for reconciliation with legacy risk counts.
    summary = by_year[by_year.year >= 2002].groupby(keys,as_index=False)[additive].sum()
    ratios = {
        'adoption_rate': ('adoptions','adoption_risk'),
        'abandonment_rate': ('abandonments','abandonment_risk'),
        'fixed_adoption_rate': ('fixed_adoptions','fixed_adoption_risk'),
        'fixed_abandonment_rate': ('fixed_abandonments','fixed_abandonment_risk'),
        'mean_delta_rca': ('sum_delta_rca','opportunities'),
        'mean_abs_delta_rca': ('sum_abs_delta_rca','opportunities'),
        'mean_delta_score': ('sum_delta_score','opportunities'),
        'mean_abs_delta_score': ('sum_abs_delta_score','opportunities'),
        'mean_delta_fixed_rca': ('sum_delta_fixed_rca','fixed_opportunities'),
        'mean_abs_delta_fixed_rca': ('sum_abs_delta_fixed_rca','fixed_opportunities'),
        'mean_delta_score_baseline_units': ('sum_delta_score_baseline_units','fixed_opportunities'),
        'fraction_entries_increasing_score': ('adoptions_score_increases','adoptions'),
        'fraction_entries_increasing_share': ('adoptions_share_increases','adoptions'),
        'fraction_exits_decreasing_score': ('abandonments_score_decreases','abandonments'),
        'entry_survival_next_year': ('persistent_entries','persistent_entry_evaluable'),
        'exit_survival_next_year': ('persistent_exits','persistent_exit_evaluable'),
    }
    for name,(num,den) in ratios.items():
        summary[name] = summary[num]/summary[den].replace(0,np.nan)
    summary.to_csv(OUT/'measurement_summary.csv',index=False)
    config = {'source_unit':'public institution-field-year mean','source_dwas':len(skills),
              'fixed_benchmark_years':[2000,2001], 'fixed_outcome_years':[2002,2017],
              'benchmark_weighting':'sum of profile mean scores, matching legacy RCA; not syllabus weighted',
              'coverage_applied_to':'both observed endpoints',
              'persistence':'sensitivity conditional on observed t+1 with same coverage; 2017 unevaluable',
              'missing_profiles':'excluded, never coded as zeros', 'negative_scores_clipped':cache_manifest['negative_scores_clipped'],
              'all_skill_universe':'all source DWAs; no selection on prestige or outcome',
              'not_estimated':['diffusion','fiscal effects','reliability weights']}
    (OUT/'measurement_config.json').write_text(json.dumps(config,indent=2))
    annual = summary[summary.pair_type=='annual'].copy()
    display_cols=['coverage','universe','profile_pairs','adoption_risk','abandonment_risk',
                  'adoption_rate','abandonment_rate','fixed_adoption_rate','fixed_abandonment_rate',
                  'fraction_entries_increasing_score','fraction_entries_increasing_share',
                  'entry_survival_next_year','exit_survival_next_year']
    text = 'VALIDACION DE MEDICION -- sin modelos de difusion ni efectos fiscales\n\n'
    text += f'DWAs fuente: {len(skills)}\n'
    text += 'Tabla comparativa: outcomes 2002--2017 para ambos benchmarks.\n'
    text += 'Benchmark fijo: 2000--2001. CSV por año incluye 2001 para reconciliar legacy.\n\n'
    text += annual[display_cols].to_string(index=False,float_format=lambda v:f'{v:.5f}')
    text += '\n\nLos intervalos con gaps se guardaron por separado; sus tasas NO son hazards anuales.\n'
    text += 'Los archivos legacy y manuscript permanecen sin sobrescritura.\n'
    (OUT/'measurement_summary.txt').write_text(text)
    print('\n'+text,flush=True)


if __name__ == '__main__':
    main()
