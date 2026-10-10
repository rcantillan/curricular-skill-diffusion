"""Reproducible pilot from public aggregated Atlas scores.

All-skill measurements are exact. Hazard opportunities use a reproducible
uniform sample of 64 skill columns each year, independent of events/status.
Missing profiles are never coded as skill absence. Existing results stay intact.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '4')
os.environ.setdefault('OMP_NUM_THREADS', '4')
from pathlib import Path
import gzip, csv, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / 'data/derived/pilot'
OUT = ROOT / 'outputs/pilot'
DATA.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
SEED = 20261004
COVERAGES = (1, 3, 5, 9)

def proximity(m):
    """min[P(s|k),P(k|s)], diagonal excluded; zero-degree nodes stay zero."""
    m = m.astype(np.float32)
    degrees = m.sum(axis=0)
    co = m.T @ m
    denom = np.maximum(degrees[:, None], degrees[None, :])
    phi = np.divide(co, denom, out=np.zeros_like(co), where=denom > 0)
    np.fill_diagonal(phi, 0)
    return phi

def distance_matrix(profiles):
    profiles = profiles.astype(np.float64)
    norm = np.linalg.norm(profiles, axis=1)
    normalized = np.divide(profiles, norm[:, None], out=np.zeros_like(profiles), where=norm[:, None] > 0)
    d = 1 - normalized @ normalized.T
    return np.clip(d, 0, 2)

def mean_pair_distance(profiles):
    if len(profiles) < 2:
        return np.nan
    d = distance_matrix(profiles)
    return float(d[np.triu_indices(len(d), 1)].mean())

def grouped_means(values, codes, n_groups):
    sums = np.zeros((n_groups, values.shape[1]), dtype=np.float32)
    np.add.at(sums, codes, values)
    n = np.bincount(codes, minlength=n_groups)
    return np.divide(sums, n[:, None], out=np.zeros_like(sums), where=n[:, None] > 0), n

def main():
    meta = pd.read_csv(DATA / 'master_metadata.csv')
    meta = meta.sort_values(['unitid', 'fos', 'year']).reset_index(drop=True)
    assert not meta.duplicated(['unitid', 'fos', 'year']).any()
    assert not meta.id.duplicated().any()
    fields = sorted(meta.fos.unique())
    meta['field_id'] = pd.Categorical(meta.fos, categories=fields).codes
    meta['cell_id'] = pd.factorize(pd.MultiIndex.from_frame(meta[['unitid', 'fos']]))[0]
    with gzip.open(ROOT / 'data/raw/detailed_work_activities_scores.gzip', 'rt') as f:
        skills = next(csv.reader(f))[1:]
    pd.DataFrame({'skill_id': range(len(skills)), 'skill': skills}).to_csv(OUT / 'skill_dictionary.csv', index=False)
    cache = DATA / 'scores.npy'
    if not cache.exists():
        scores = np.lib.format.open_memmap(cache, mode='w+', dtype='float32', shape=(len(meta), len(skills)))
        scores[:] = np.nan
        positions = pd.Series(meta.index, index=meta.id)
        for chunk in pd.read_csv(ROOT / 'data/raw/detailed_work_activities_scores.gzip', compression='gzip', chunksize=1500):
            loc = positions.reindex(chunk.iloc[:, 0]).to_numpy()
            keep = ~pd.isna(loc)
            scores[loc[keep].astype(int)] = chunk.iloc[np.flatnonzero(keep), 1:].to_numpy(dtype=np.float32)
        scores.flush()
    scores = np.load(cache, mmap_mode='r')
    assert scores.shape == (len(meta), len(skills))
    assert np.isfinite(scores).all() and (scores >= 0).all()
    row_totals = scores.sum(axis=1, dtype=np.float64)
    shares = np.asarray(scores / row_totals[:, None], dtype=np.float32)
    years = sorted(meta.year.unique())
    year_idx = {int(y): np.flatnonzero(meta.year.to_numpy() == y) for y in years}
    rca = np.empty_like(shares)
    for y, idx in year_idx.items():
        benchmark = scores[idx].sum(axis=0, dtype=np.float64) / row_totals[idx].sum()
        rca[idx] = shares[idx] / benchmark
    # Fixed equal-cell benchmark from all pre-crisis profiles, 2000--2007.
    pre = meta.year.to_numpy() <= 2007
    fixed_benchmark = scores[pre].sum(axis=0, dtype=np.float64) / row_totals[pre].sum()
    fixed_rca = np.asarray(shares / fixed_benchmark, dtype=np.float32)
    # Baseline cell portfolios pool public means weighted by underlying syllabi.
    n_cells = int(meta.cell_id.max()) + 1
    base_sum = np.zeros((n_cells, len(skills)), dtype=np.float32)
    base_n = np.zeros(n_cells, dtype=np.float32)
    np.add.at(base_sum, meta.cell_id.to_numpy()[pre], scores[pre] * meta.syllabi_cnt.to_numpy()[pre, None])
    np.add.at(base_n, meta.cell_id.to_numpy()[pre], meta.syllabi_cnt.to_numpy()[pre])
    base_score = np.divide(base_sum, base_n[:, None], out=np.zeros_like(base_sum), where=base_n[:, None] > 0)
    base_total = base_score.sum(axis=1)
    base_share = np.divide(base_score, base_total[:, None], out=np.zeros_like(base_score), where=base_total[:, None] > 0)
    base_portfolio = base_share / fixed_benchmark >= 1
    phi_base = proximity(base_portfolio[base_n >= 9])
    np.save(DATA / 'proximity_pre2008.npy', phi_base)
    # Baseline disciplinary origin: prevalence across programs in each field.
    cell_field = meta.drop_duplicates('cell_id').sort_values('cell_id').field_id.to_numpy()
    eligible_base = base_n >= 9
    field_prev, field_n = grouped_means(base_portfolio[eligible_base].astype(np.float32), cell_field[eligible_base], len(fields))
    field_distance = distance_matrix(field_prev)
    origin_mass = field_prev / np.maximum(field_prev.sum(axis=0), 1e-12)
    disciplinary_distance = field_distance @ origin_mass
    np.save(DATA / 'baseline_field_distance.npy', field_distance)
    pd.DataFrame(field_distance, index=fields, columns=fields).to_csv(OUT / 'baseline_field_distances.csv')
    previous = meta.groupby('cell_id', sort=False).year.shift().to_numpy()
    gaps = meta.year.to_numpy() - previous
    consecutive = gaps == 1
    prev_index = np.arange(len(meta)) - 1
    transitions = []
    summaries = []
    structural = []
    old_frontier = set(pd.read_csv(ROOT / 'data/interim/top_skills_baseline.csv').iloc[:, 0])
    frontier_cols = np.array([s in old_frontier for s in skills])
    frontier_counts = {'adoption_opportunities': 0, 'abandonment_opportunities': 0, 'adoptions': 0, 'abandonments': 0}
    rng = np.random.default_rng(SEED)
    # Strict balanced composition across all 18 years; show its coverage explicitly.
    observed_years = meta.groupby('cell_id').year.nunique()
    balanced_cells = observed_years.index[observed_years == len(years)].to_numpy()
    meta['balanced'] = meta.cell_id.isin(balanced_cells)
    for y, idx in year_idx.items():
        print('Year', y, flush=True)
        current_rca = rca[idx]
        current_m = current_rca >= 1
        for k in COVERAGES:
            keep = meta.syllabi_cnt.to_numpy()[idx] >= k
            prof, cnt = grouped_means(shares[idx][keep], meta.field_id.to_numpy()[idx][keep], len(fields))
            structural.append({'year': y, 'coverage': k, 'composition': 'available', 'fields': int((cnt > 0).sum()),
                               'profiles': int(keep.sum()), 'mean_between_field_distance': mean_pair_distance(prof[cnt > 0])})
            keep = keep & meta.balanced.to_numpy()[idx]
            prof, cnt = grouped_means(shares[idx][keep], meta.field_id.to_numpy()[idx][keep], len(fields))
            structural.append({'year': y, 'coverage': k, 'composition': 'balanced_cells_variable_coverage', 'fields': int((cnt > 0).sum()),
                               'profiles': int(keep.sum()), 'mean_between_field_distance': mean_pair_distance(prof[cnt > 0])})
        if y == years[0]:
            continue
        tgt = idx[consecutive[idx]]
        lag = prev_index[tgt]
        if not len(tgt):
            continue
        m0, m1 = rca[lag] >= 1, rca[tgt] >= 1
        adoption = ~m0 & m1
        abandonment = m0 & ~m1
        fix0, fix1 = fixed_rca[lag] >= 1, fixed_rca[tgt] >= 1
        for k in COVERAGES:
            keep = (meta.syllabi_cnt.to_numpy()[tgt] >= k) & (meta.syllabi_cnt.to_numpy()[lag] >= k)
            a, b = int(adoption[keep].sum()), int(abandonment[keep].sum())
            risk_a, risk_b = int((~m0[keep]).sum()), int(m0[keep].sum())
            summaries.append({'year': y, 'coverage': k, 'profiles': int(keep.sum()), 'adoption_risk': risk_a,
                'abandonment_risk': risk_b, 'adoptions': a, 'abandonments': b,
                'adoption_rate': a / risk_a if risk_a else np.nan, 'abandonment_rate': b / risk_b if risk_b else np.nan,
                'mean_abs_delta_rca': float(np.abs(rca[tgt[keep]]-rca[lag[keep]]).mean()) if keep.any() else np.nan,
                'mean_abs_delta_score': float(np.abs(scores[tgt[keep]]-scores[lag[keep]]).mean()) if keep.any() else np.nan,
                'fixed_adoptions': int((~fix0[keep] & fix1[keep]).sum()),
                'fixed_abandonments': int((fix0[keep] & ~fix1[keep]).sum())})
            # Matched programs and fields in each adjacent year pair.
            p0, cnt = grouped_means(shares[lag[keep]], meta.field_id.to_numpy()[tgt[keep]], len(fields))
            p1, _ = grouped_means(shares[tgt[keep]], meta.field_id.to_numpy()[tgt[keep]], len(fields))
            valid = cnt >= 5
            transitions.append({'year': y, 'coverage': k, 'profiles': int(keep.sum()), 'fields_min5': int(valid.sum()),
                'between_before': mean_pair_distance(p0[valid]), 'between_after': mean_pair_distance(p1[valid]),
                'within_field_cosine_change': float(np.diag(distance_matrix(np.concatenate([p0[valid],p1[valid]]))[:valid.sum(),valid.sum():]).mean()) if valid.any() else np.nan})
        for name, val in [('adoption_opportunities', (~m0[:,frontier_cols]).sum()), ('abandonment_opportunities',m0[:,frontier_cols].sum()),
                          ('adoptions',adoption[:,frontier_cols].sum()), ('abandonments',abandonment[:,frontier_cols].sum())]:
            frontier_counts[name] += int(val)
        # Annual network only uses observed profiles from t-1, with >=3 syllabi.
        src = year_idx[y-1]
        src_valid = meta.syllabi_cnt.to_numpy()[src] >= 3
        phi = proximity((rca[src[src_valid]] >= 1))
        chosen = np.sort(rng.choice(len(skills), size=min(64,len(skills)), replace=False))
        density_denom = phi[:,chosen].sum(axis=0)
        density = np.divide(m0.astype(np.float32) @ phi[:,chosen], density_denom,
                            out=np.full((len(tgt),len(chosen)),np.nan,dtype=np.float32),where=density_denom > 0)
        base_denom = phi_base[:,chosen].sum(axis=0)
        base_density = np.divide(base_portfolio[meta.cell_id.to_numpy()[tgt]].astype(np.float32) @ phi_base[:,chosen], base_denom,
                            out=np.full((len(tgt),len(chosen)),np.nan,dtype=np.float32),where=base_denom > 0)
        base_density[base_n[meta.cell_id.to_numpy()[tgt]] < 9] = np.nan
        # Exposure denominators are observed source programs, never unobserved zeros.
        source_meta = meta.iloc[src]
        source_m = (rca[src][:,chosen] >= 1).astype(np.float32)
        inst_codes, inst_labels = pd.factorize(source_meta.unitid)
        inst_mean, inst_n = grouped_means(source_m, inst_codes, len(inst_labels))
        inst_pos = pd.Index(inst_labels).get_indexer(meta.unitid.to_numpy()[tgt])
        field_mean, field_counts = grouped_means(source_m, source_meta.field_id.to_numpy(), len(fields))
        own = m0[:,chosen].astype(np.float32)
        inst_count = inst_n[inst_pos] - 1
        field_count = field_counts[meta.field_id.to_numpy()[tgt]] - 1
        within_inst = np.divide(inst_mean[inst_pos] * inst_n[inst_pos,None] - own, inst_count[:,None],
                    out=np.full_like(own,np.nan),where=inst_count[:,None]>0)
        same_field = np.divide(field_mean[meta.field_id.to_numpy()[tgt]]*field_counts[meta.field_id.to_numpy()[tgt],None]-own,field_count[:,None],
                    out=np.full_like(own,np.nan),where=field_count[:,None]>0)
        other_count = len(src) - inst_n[inst_pos] - field_counts[meta.field_id.to_numpy()[tgt]] + 1
        other_sum = source_m.sum(axis=0) - inst_mean[inst_pos]*inst_n[inst_pos,None] - field_mean[meta.field_id.to_numpy()[tgt]]*field_counts[meta.field_id.to_numpy()[tgt],None] + own
        other = np.divide(other_sum,other_count[:,None],out=np.full_like(own,np.nan),where=other_count[:,None]>0)
        rr, cc = np.nonzero(~m0[:,chosen])
        record = pd.DataFrame({'unitid':meta.unitid.to_numpy()[tgt[rr]],'field_id':meta.field_id.to_numpy()[tgt[rr]],
            'cell_id':meta.cell_id.to_numpy()[tgt[rr]],'year':y,'skill_id':chosen[cc],
            'adopt':adoption[:,chosen][rr,cc].astype(int),'rd':density[rr,cc],
            'distance_pre2008':1-base_density[rr,cc],
            'disciplinary_distance':disciplinary_distance[meta.field_id.to_numpy()[tgt[rr]],chosen[cc]],
            'exposure_same_inst':within_inst[rr,cc],'exposure_same_field':same_field[rr,cc],
            'exposure_other':other[rr,cc], 'n_same_inst':inst_count[rr],'n_same_field':field_count[rr],
            'coverage_min':np.minimum(meta.syllabi_cnt.to_numpy()[tgt[rr]],meta.syllabi_cnt.to_numpy()[lag[rr]]),
            'n_lag':meta.syllabi_cnt.to_numpy()[lag[rr]],'n_current':meta.syllabi_cnt.to_numpy()[tgt[rr]],
            'delta_rca':rca[tgt][:,chosen][rr,cc]-rca[lag][:,chosen][rr,cc],
            'delta_score':scores[tgt][:,chosen][rr,cc]-scores[lag][:,chosen][rr,cc],
            'fixed_score_delta':(shares[tgt][:,chosen][rr,cc]-shares[lag][:,chosen][rr,cc])/fixed_benchmark[chosen[cc]],
            'fixed_crossing':((fixed_rca[lag][:,chosen]<1)&(fixed_rca[tgt][:,chosen]>=1))[rr,cc].astype(int)})
        assert (inst_pos >= 0).all()
        assert (record[['exposure_same_inst','exposure_same_field','exposure_other']].min() >= -1e-5).all()
        assert (record[['exposure_same_inst','exposure_same_field','exposure_other']].max() <= 1.00001).all()
        record.to_csv(DATA / f'opportunities_{y}.csv.gz',index=False,compression='gzip')
    pd.DataFrame(summaries).to_csv(OUT / 'measurement_by_year_coverage.csv',index=False)
    pd.DataFrame(transitions).to_csv(OUT / 'matched_structural_change.csv',index=False)
    pd.DataFrame(structural).to_csv(OUT / 'annual_between_field_distance.csv',index=False)
    # Genuine balanced panel with the same coverage eligibility in every year.
    balanced_results=[]
    for k in COVERAGES:
        mins=meta.groupby('cell_id').syllabi_cnt.min()
        allowed=np.intersect1d(balanced_cells,mins.index[mins>=k])
        counts=np.bincount(cell_field[allowed],minlength=len(fields))
        valid_fields=counts>=5
        for y,idx in year_idx.items():
            keep=meta.cell_id.to_numpy()[idx]
            selected=np.isin(keep,allowed)
            prof,_=grouped_means(shares[idx[selected]],meta.field_id.to_numpy()[idx[selected]],len(fields))
            balanced_results.append({'year':y,'coverage':k,'cells':len(allowed),'fields_min5':int(valid_fields.sum()),
                 'mean_distance':mean_pair_distance(prof[valid_fields])})
    pd.DataFrame(balanced_results).to_csv(OUT/'strict_balanced_distance.csv',index=False)
    audit={'seed':SEED,'public_score_unit':'institution-field-year mean','analytic_profiles':len(meta),
        'analytic_institutions':int(meta.unitid.nunique()),'analytic_fields':len(fields),'dwas':len(skills),
        'represented_syllabi':int(meta.syllabi_cnt.sum()),'median_syllabi':float(meta.syllabi_cnt.median()),
        'single_syllabus_fraction':float((meta.syllabi_cnt==1).mean()),'under10_fraction':float((meta.syllabi_cnt<10).mean()),
        'observed_transitions':int(np.isfinite(gaps).sum()),'nonannual_transitions':int((gaps>1).sum()),
        'consecutive_transitions':int(consecutive.sum()),'frontier_annual_counts':frontier_counts,
        'fixed_benchmark_years':[2000,2007],'fixed_benchmark_weighting':'equal profiles',
        'baseline_portfolio_weighting':'syllabi-weighted means within institution-field',
        'annual_skill_space_min_syllabi':3,'hazard_sampling':'64 uniform DWA columns independently each year; all annual eligible cells',
        'balanced_cells_all18years':len(balanced_cells),
        'warning':'Existing interim RDS and manuscript tables are legacy; not regenerated by this pilot.'}
    (OUT/'measurement_audit.json').write_text(json.dumps(audit,indent=2))
    summary=pd.DataFrame(summaries)
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    for k in COVERAGES:
        d=summary[summary.coverage==k]
        axes[0].plot(d.year,d.adoption_rate,label=f'≥{k} syllabi')
        axes[1].plot(d.year,d.abandonment_rate,label=f'≥{k} syllabi')
    for ax,title in zip(axes,['Annual specialization entry','Annual specialization exit']):
        ax.set(title=title,xlabel='Year',ylabel='Transitions / opportunities'); ax.legend(fontsize=8); ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(OUT/'measurement_coverage.png',dpi=160);plt.close(fig)
    print(json.dumps(audit,indent=2),flush=True)

if __name__=='__main__':
    main()
