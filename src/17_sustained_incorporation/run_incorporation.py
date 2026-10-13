"""Exploratory sustained entries and exposure to previously present content; no RCA."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
import argparse
import csv
import gzip
import hashlib
import json
import re
import subprocess
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import t as student_t
from institutional_exposures import first_origins, exposures as institutional_exposures

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
CHANNELS = ['within', 'same_field', 'other_field', 'within_distinct', 'other_distinct']


def sums(x, codes, n):
    a = np.zeros((n, x.shape[1]), dtype=float)
    np.add.at(a, codes, x)
    return a, np.bincount(codes, minlength=n)


def divide(a, n):
    return np.divide(a, n[:, None], out=np.full(a.shape, np.nan), where=n[:, None] > 0)


def build(meta, scores, chosen, skills, q, margin, folder, statuses, profiles=None, measure='selectivity', origin_rule='lag'):
    x = np.asarray(scores[:, chosen])
    baseline = (meta.year.between(2002, 2007) & (meta.syllabi_cnt >= 9)).to_numpy()
    mu, sd = x[baseline].mean(0), x[baseline].std(0)
    if not np.isfinite(x).all() or (x < 0).any() or (sd <= 1e-10).any():
        raise ValueError('Invalid scores or baseline scales')
    z = (x - mu) / sd
    cutoff = np.quantile(z[baseline], q, axis=0)
    # Characteristic content: equal-program baseline field means relative to
    # the mean of other fields, measured before any analysed entry.
    program_means = pd.DataFrame(z[baseline]).groupby(meta.loc[baseline, 'cell_id'].to_numpy()).mean()
    program_fields = meta.drop_duplicates('cell_id').set_index('cell_id').field_id
    field_means = program_means.groupby(program_fields.reindex(program_means.index).to_numpy()).mean()
    nf = meta.field_id.nunique()
    distinctive = np.zeros((nf, len(chosen)), dtype=bool)
    contrasts = np.full((nf, len(chosen)), np.nan)
    if len(field_means) > 1:
        contrast = field_means.to_numpy() - (field_means.sum().to_numpy() - field_means.to_numpy()) / (len(field_means) - 1)
        contrasts[field_means.index] = contrast
        distinctive[field_means.index] = contrast >= .25
    pd.DataFrame(dict(skill_id=chosen, skill=[skills[i] for i in chosen], baseline_mean=mu,
                      baseline_sd=sd, presence_cutoff_z=cutoff)).to_csv(folder/'thresholds.csv', index=False)
    pd.DataFrame(contrasts, index=range(nf), columns=chosen).rename_axis('field_id').to_csv(folder/'field_distinctiveness.csv')
    years, counts = meta.year.to_numpy(), meta.syllabi_cnt.to_numpy()
    cells, inst, fields = meta.cell_id.to_numpy(), meta.unitid.to_numpy(), meta.field_id.to_numpy()
    keys = {(r.cell_id, r.year): i for i, r in enumerate(meta.itertuples())}
    origins = first_origins(meta,z,cutoff,margin,keys) if profiles is not None and origin_rule=='first_sustained' else None
    frames, support, origin_support = [], [], []
    for year in range(2008, 2017):
        current = np.flatnonzero((years == year) & (counts >= 9))
        indices = {y: np.array([keys.get((cells[i], y), -1) for i in current], dtype=int)
                   for y in (year-2, year-1, year+1)}
        prior_ok = np.ones(len(current), dtype=bool)
        for y in (year-2, year-1):
            ix = indices[y]
            prior_ok &= (ix >= 0) & (counts[np.maximum(ix, 0)] >= 9)
        future = indices[year+1]
        follow_ok = (future >= 0) & (counts[np.maximum(future, 0)] >= 9)
        risk_without_follow = np.zeros((len(current), len(chosen)), dtype=bool)
        risk_without_follow[prior_ok] = ((z[indices[year-2][prior_ok]] <= cutoff-margin) &
                                        (z[indices[year-1][prior_ok]] <= cutoff-margin))
        support.append(dict(year=year, annual_programs=len(current), prior_covered_programs=int(prior_ok.sum()),
                            followed_programs=int((prior_ok & follow_ok).sum()),
                            risk_without_follow=int(risk_without_follow.sum()),
                            risk_with_follow=int(risk_without_follow[follow_ok].sum())))
        keep = prior_ok & follow_ok
        target = current[keep]
        if not len(target):
            continue
        lag, old, future = indices[year-1][keep], indices[year-2][keep], future[keep]
        risk = risk_without_follow[keep]
        # Sources use only t-2 and t-1. Future source information is never used.
        source_lag = np.flatnonzero((years == year-1) & (counts >= 9))
        source_old = np.array([keys.get((cells[i], year-2), -1) for i in source_lag])
        good = (source_old >= 0) & (counts[np.maximum(source_old, 0)] >= 9)
        source_lag, source_old = source_lag[good], source_old[good]
        present = ((z[source_lag] >= cutoff+margin) & (z[source_old] >= cutoff+margin)).astype(float)
        if profiles is not None:
            oo=origins[cells[source_lag]] if origin_rule=='first_sustained' else np.full(present.shape,year-1)
            sr,sk=np.where(present>0)
            audit=pd.DataFrame(dict(unitid=inst[source_lag][sr],origin_year=oo[sr,sk]))
            needed=[measure,'instruction_log','research_log','carnegie_classification','institution_control']
            audit=audit.merge(profiles[['unitid','year']+needed],left_on=['unitid','origin_year'],right_on=['unitid','year'],how='left',validate='many_to_one')
            audit['selectivity_known']=audit[measure].notna()
            audit['complete_profile']=audit[needed].notna().all(axis=1)
            g=audit.groupby('origin_year').agg(source_skill_states=('unitid','size'),selectivity_known=('selectivity_known','sum'),complete_profile=('complete_profile','sum')).reset_index()
            g['entry_year']=year;origin_support.append(g)
        ci, labels = pd.factorize(inst[source_lag])
        ti = pd.Index(labels).get_indexer(inst[target])
        if (ti < 0).any():
            raise ValueError('Missing target in covered source population')
        si, ni_all = sums(present, ci, len(labels))
        sf, nfield_all = sums(present, fields[source_lag], nf)
        total = present.sum(0)
        # Eligible receivers are below the cutoff: their own present indicator is zero.
        # Explicit subtraction also makes the source exclusion correct off the risk set.
        own_present = ((z[lag] >= cutoff+margin) & (z[old] >= cutoff+margin)).astype(float)
        ni, nfield = ni_all[ti]-1, nfield_all[fields[target]]-1
        no = len(source_lag)-ni_all[ti]-nfield_all[fields[target]]+1
        within_count, field_count = si[ti]-own_present, sf[fields[target]]-own_present
        other_count = total-si[ti]-sf[fields[target]]+own_present
        distinctive_present = present*distinctive[fields[source_lag]]
        di, _ = sums(distinctive_present, ci, len(labels))
        df, _ = sums(distinctive_present, fields[source_lag], nf)
        dt = distinctive_present.sum(0)
        own_distinct = own_present*distinctive[fields[target]]
        # Foreign-field content must not also be characteristic of the receiver field.
        foreign = ~distinctive[fields[target]]
        exposure = dict(within=divide(within_count, ni), same_field=divide(field_count, nfield),
                        other_field=divide(other_count, no),
                        within_distinct=divide((di[ti]-own_distinct)*foreign, ni),
                        other_distinct=divide((dt-di[ti]-df[fields[target]]+own_distinct)*foreign, no))
        adoption = ((z[target] >= cutoff+margin) & (z[future] >= cutoff+margin)).astype(int)
        rr, kk = np.where(risk)
        data = dict(unitid=inst[target][rr], cell_id=cells[target][rr], field_id=fields[target][rr],
                    skill_id=chosen[kk], year=year, incorporation=adoption[rr, kk],
                    lag_score=z[lag][rr, kk], previous_change=(z[lag]-z[old])[rr, kk],
                    n_old=counts[old][rr], n_lag=counts[lag][rr], n_current=counts[target][rr],
                    n_future=counts[future][rr], n_within=ni[rr], n_same_field=nfield[rr], n_other_field=no[rr])
        for name, values in exposure.items():
            data[name] = values[rr, kk]
        if profiles is not None:
            moments = institutional_exposures(meta,target,source_lag,present,origins,profiles,
                                               measure,origin_rule,year,nfield,no)
            for name,values in moments.items():data[name]=values[rr,kk]
            for pool,base in [('same','same_field'),('other','other_field')]:
                matched=moments['matched_'+pool];actual=exposure[base]
                fraction=np.divide(matched,actual,out=np.ones_like(matched),where=actual>0)
                fraction[~np.isfinite(matched)]=np.nan
                data['profile_fraction_'+pool]=fraction[rr,kk]
        # Optional legacy hiring-rank sensitivity, not the default IPEDS analysis.
        # Rankings are field-specific; never compare their scales across fields.
        above = np.full((len(target), len(chosen)), np.nan)
        below = above.copy()
        n_status = np.zeros(len(target), dtype=int)
        for f in np.unique(fields[target]) if statuses is not None else []:
            ranks = statuses[(statuses.field_id == f) & (statuses.outcome_start_year <= year)]
            if ranks.empty:
                continue
            rank_map = ranks.set_index('unitid').status
            js = np.flatnonzero(fields[source_lag] == f)
            source_status = rank_map.reindex(inst[source_lag][js]).to_numpy()
            available = np.isfinite(source_status)
            js, source_status = js[available], source_status[available]
            for i in np.flatnonzero(fields[target] == f):
                target_status = rank_map.get(inst[target][i], np.nan)
                if not np.isfinite(target_status):
                    continue
                use = cells[source_lag][js] != cells[target][i]
                gap = source_status[use]-target_status
                n_status[i] = int(use.sum())
                if use.any():
                    above[i] = np.maximum(gap, 0) @ present[js[use]] / use.sum()
                    below[i] = np.maximum(-gap, 0) @ present[js[use]] / use.sum()
        data.update(status_above=above[rr, kk], status_below=below[rr, kk], n_status=n_status[rr])
        frame = pd.DataFrame(data)
        if frame.duplicated(['cell_id', 'skill_id', 'year']).any():
            raise ValueError('Duplicated receiver events')
        # A positive entry with zero source exposure is allowed: spontaneous or
        # unobserved origins are not discarded to manufacture diffusion.
        frames.append(frame)
    if not frames:
        raise ValueError('No eligible receivers')
    panel = pd.concat(frames, ignore_index=True)
    panel.to_csv(folder/'panel.csv.gz', index=False)
    summaries = panel.groupby(['year', 'field_id']).agg(risk_rows=('incorporation', 'size'),
        entries=('incorporation', 'sum'), programs=('cell_id', 'nunique'), institutions=('unitid', 'nunique')).reset_index()
    summaries.to_csv(folder/'entry_support.csv', index=False)
    pd.DataFrame(support).to_csv(folder/'followup_support.csv', index=False)
    if origin_support:pd.concat(origin_support).to_csv(folder/'origin_support.csv',index=False)
    # Program-year summaries are descriptive and are not source-attributed edges.
    pg = panel.groupby(['unitid', 'field_id', 'year']).agg(eligible_skills=('incorporation', 'size'),
                                                        entries=('incorporation', 'sum')).reset_index()
    pg.to_csv(folder/'program_entries.csv.gz', index=False)


def summarize(out, folders):
    cs, us, es, fs, ps, failures, diagnostics, origin_support = [], [], [], [], [], [], [], []
    for q, block, folder in folders:
        for name, collection in [('coefficients.csv', cs), ('influences.csv.gz', us),
                                 ('entry_support.csv', es), ('followup_support.csv', fs),
                                 ('program_entries.csv.gz', ps), ('failures.csv', failures),
                                 ('model_support.csv', diagnostics),('origin_support.csv',origin_support)]:
            if (folder/name).exists():
                d = pd.read_csv(folder/name)
                d['quantile'], d['block'] = q, block
                collection.append(d)
    if not cs:
        raise ValueError('No models succeeded; inspect block logs and failures')
    c, u = pd.concat(cs), pd.concat(us)
    c.to_csv(out/'coefficients_by_block.csv', index=False)
    results = []
    for key, g in c.groupby(['quantile', 'model', 'term']):
        subset = u[(u['quantile'] == key[0]) & (u.model == key[1]) & (u.term == key[2])].copy()
        weights = g.set_index('block').rows
        weights = weights/weights.sum()
        subset['weighted'] = subset.influence*subset.block.map(weights)
        influence = subset.groupby('unitid').weighted.sum()
        estimate = np.dot(g.estimate, g.block.map(weights))
        se = np.sqrt(np.square(influence).sum())
        df = max(1, len(influence)-1)
        radius = student_t.ppf(.975, df)*se
        results.append(dict(quantile=key[0], model=key[1], term=key[2], estimate=estimate, se=se,
            ci_low=estimate-radius, ci_high=estimate+radius,
            p=2*student_t.sf(abs(estimate/se), df) if se else np.nan,
            blocks=len(g), rows=int(g.rows.sum()), institutions=len(influence),
            probability_points_per_10pp=10*estimate if key[2] in CHANNELS else np.nan))
    result = pd.DataFrame(results)
    result.to_csv(out/'incorporation_summary.csv', index=False)
    comparisons = []
    for (q, model), g in result.groupby(['quantile', 'model']):
        for a, b in [('within', 'same_field'), ('within', 'other_field'), ('within_distinct', 'other_distinct'),
                     ('sel_above_same','sel_below_same'),('sel_above_other','sel_below_other'),
                     ('sel_above_same','sel_above_other'),('sel_below_same','sel_below_other')]:
            if not {a, b} <= set(g.term):
                continue
            ga = c[(c['quantile'] == q) & (c.model == model) & (c.term == a)]
            gb = c[(c['quantile'] == q) & (c.model == model) & (c.term == b)]
            if set(ga.block) != set(gb.block):
                continue
            w = ga.set_index('block').rows
            w = w/w.sum()
            uu = u[(u['quantile'] == q) & (u.model == model) & u.term.isin([a,b])].copy()
            uu['value'] = uu.influence*uu.block.map(w)*np.where(uu.term == a, 1, -1)
            inf = uu.groupby('unitid').value.sum()
            est = g.set_index('term').estimate[a]-g.set_index('term').estimate[b]
            se = np.sqrt(np.square(inf).sum()); df = max(1,len(inf)-1)
            radius = student_t.ppf(.975,df)*se
            comparisons.append(dict(quantile=q,model=model,contrast=a+' - '+b,estimate=est,se=se,
                ci_low=est-radius,ci_high=est+radius,p=2*student_t.sf(abs(est/se),df) if se else np.nan))
    pd.DataFrame(comparisons).to_csv(out/'channel_contrasts.csv',index=False)
    pd.concat(diagnostics).to_csv(out/'model_support_by_block.csv',index=False)
    if origin_support:
        pd.concat(origin_support).groupby(['quantile','entry_year','origin_year'])[['source_skill_states','selectivity_known','complete_profile']].sum().reset_index().to_csv(out/'origin_support.csv',index=False)
    e = pd.concat(es).groupby(['quantile', 'year', 'field_id'])[['risk_rows', 'entries']].sum().reset_index()
    e['entry_rate'] = e.entries/e.risk_rows
    e.to_csv(out/'entry_rates.csv', index=False)
    p = pd.concat(ps).groupby(['quantile', 'unitid', 'field_id', 'year'])[['eligible_skills', 'entries']].sum().reset_index()
    p['entry_rate'] = p.entries/p.eligible_skills
    p.to_csv(out/'program_entry_rates.csv', index=False)
    f = pd.concat(fs).groupby(['quantile', 'year'])[['risk_without_follow', 'risk_with_follow']].sum().reset_index()
    f['followup_fraction'] = f.risk_with_follow/f.risk_without_follow
    f.to_csv(out/'followup_selection.csv', index=False)
    if failures:
        pd.concat(failures).to_csv(out/'skipped_models.csv', index=False)
    return len(failures)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='incorporation1')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--keep-panels', action='store_true')
    parser.add_argument('--margin', type=float, default=.1)
    parser.add_argument('--status-source',choices=['ipeds','clauset'],default='ipeds')
    parser.add_argument('--origin-rule',choices=['lag','first_sustained'],
                        help='Required for IPEDS: lag=t-1; first_sustained=first documented high-year pair')
    parser.add_argument('--selectivity-measure',choices=['selectivity','sat_selectivity','act_selectivity','rejection_selectivity'],default='selectivity')
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_-]+', args.tag) or (args.smoke and not args.tag.endswith('_smoke')):
        parser.error('Use a simple tag; smoke tags must end in _smoke')
    if args.margin <= 0:
        parser.error('Margin must be positive')
    if args.status_source=='ipeds' and args.origin_rule is None:
        parser.error('Specify --origin-rule lag or first_sustained; origin timing must be explicit')
    meta_path = ROOT/'data/derived/pilot/master_metadata.csv'
    manifest_path = ROOT/'data/derived/pilot/measurement_scores_manifest.json'
    raw = ROOT/'data/raw/detailed_work_activities_scores.gzip'
    meta = pd.read_csv(meta_path).sort_values(['unitid', 'fos', 'year']).reset_index(drop=True)
    if meta.id.duplicated().any() or meta.duplicated(['unitid', 'fos', 'year']).any():
        raise ValueError('Duplicate metadata')
    meta['cell_id'] = pd.factorize(pd.MultiIndex.from_frame(meta[['unitid', 'fos']]))[0]
    names = sorted(meta.fos.unique())
    meta['field_id'] = pd.Categorical(meta.fos, categories=names).codes
    with gzip.open(raw, 'rt') as f:
        skills = next(csv.reader(f))[1:]
    stamp = json.loads(manifest_path.read_text())
    if (hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest() != stamp['ids_sha256'] or
        hashlib.sha256('\n'.join(skills).encode()).hexdigest() != stamp['skills_sha256'] or
        raw.stat().st_size != stamp['source_bytes'] or raw.stat().st_mtime_ns != stamp['source_mtime_ns']):
        raise ValueError('Score cache audit mismatch')
    scores = np.load(ROOT/'data/derived/pilot/measurement_scores_float64.npy', mmap_mode='r')
    if scores.shape != (len(meta), 2070):
        raise ValueError('Expected all 2070 activities')
    partitions = sorted((ROOT/'outputs/allskills_channels/allskills').glob('block_*_skills.csv'))
    blocks = [np.sort(pd.read_csv(f).skill_id.to_numpy(dtype=int)) for f in partitions]
    if sorted(np.concatenate(blocks).tolist()) != list(range(2070)):
        raise ValueError('Incomplete activity partition')
    if args.smoke:
        blocks = [b[:4] for b in blocks[:2]]
    profiles=None;statuses=None
    if args.status_source=='ipeds':
        status_path=ROOT/'data/derived/institutional_selectivity/annual_institution_profile.csv'
        if not status_path.exists():
            raise FileNotFoundError('First run: python3 src/18_institutional_selectivity/prepare_annual_profile.py')
        profiles=pd.read_csv(status_path)
        if profiles.duplicated(['unitid','year']).any():raise ValueError('Duplicate institutional-year profiles')
    else:
        status_path = ROOT/'outputs/relational_comparison/status2015/status_2015_by_field.csv'
        statuses = pd.read_csv(status_path)
        statuses['field_id'] = statuses.field.map({name: i for i, name in enumerate(names)})
        if statuses.duplicated(['unitid', 'field']).any():raise ValueError('Duplicate status ranks')
    out = ROOT/'outputs/sustained_incorporation'/args.tag
    out.mkdir(parents=True, exist_ok=True)
    inputs = [HERE/'run_incorporation.py', HERE/'fit_incorporation.R',HERE/'institutional_exposures.py', meta_path, manifest_path, status_path]+partitions
    if profiles is not None:inputs.append(ROOT/'data/derived/institutional_selectivity/annual_design.json')
    config = dict(smoke=args.smoke, margin_sd=args.margin, quantiles=[.75, .9], baseline=[2002, 2007],
        years=[2008, 2016], floor=9, characteristic_margin_sd=.25,status_source=args.status_source,
        origin_rule=args.origin_rule,selectivity_measure=args.selectivity_measure,
        status_channels='same and different disciplines between institutions' if profiles is not None else 'same-field only; 2014 onward',
        minimum_profile_fraction=.5,
        hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
        outcome='two low prior years followed by two high years; recurrent entry allowed',
        temporal_transmission_identified=False, thresholds_validated=False, forecasts=False, rca=False)
    if (out/'design.json').exists() and json.loads((out/'design.json').read_text()) != config:
        raise ValueError('Changed code/input/design: use a new tag')
    (out/'design.json').write_text(json.dumps(config, indent=2)+'\n')
    pd.DataFrame(dict(field_id=range(len(names)), field=names)).to_csv(out/'fields.csv', index=False)
    folders = []
    for q in config['quantiles']:
        for block, chosen in enumerate(blocks):
            folder = out/f'q{int(q*100):02d}_block_{block:03d}'
            folder.mkdir(exist_ok=True)
            folders.append((q, block, folder))
            if (folder/'complete.json').exists():
                continue
            print(f'Presence percentile {int(q*100)}; block {block+1}/{len(blocks)}: build risk set and fit', flush=True)
            build(meta, scores, chosen, skills, q, args.margin, folder, statuses,profiles,args.selectivity_measure,args.origin_rule)
            with (folder/'models.log').open('w') as log:
                result = subprocess.run(['Rscript', str(HERE/'fit_incorporation.R'), str(folder)],
                    stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
            if result.returncode:
                raise RuntimeError(f'Model failed: inspect {folder}/models.log')
            if not args.keep_panels:
                (folder/'panel.csv.gz').unlink()
    failures = summarize(out, folders)
    (out/'complete.json').write_text(json.dumps(dict(activities=sum(map(len, blocks)), blocks=len(blocks),
        quantiles=config['quantiles'], smoke=args.smoke, folders_with_skipped_models=failures))+'\n')
    print(f'Finished: {out}. Inspect skipped_models.csv if present.', flush=True)


if __name__ == '__main__':
    main()
