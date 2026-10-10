"""RCA-free pilot of continuous curricular change and lagged content channels.

Uses a fixed random sample of DWAs, baseline-only score scales, consecutive
profiles, and an optional two-year outcome. Faculty edges are structural
connections, not observed conversations or dated transmission events.
"""
from pathlib import Path
import argparse
import csv
import gzip
import hashlib
import json
import re
import unicodedata
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

ROOT = Path(__file__).resolve().parents[2]


def normalize(name):
    text = unicodedata.normalize('NFKD', str(name)).encode('ascii', 'ignore').decode().lower()
    text = text.replace('&', ' and ')
    text = re.sub(r'\buc\b', 'university of california', text)
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    text = ' '.join(x for x in text.split() if x not in ('the', 'at'))
    return re.sub(r' main campus$', '', text)


def match_names(meta, out):
    """Exact names and explicit institutional aliases; no fuzzy assignment."""
    carnegie = pd.read_csv(ROOT / 'data/interim/carnegie_prestige_panel_2000_2017.csv',
                           usecols=['unitid', 'institution_name'])
    names = pd.concat([meta[['unitid', 'institution_name']], carnegie]).dropna().drop_duplicates()
    if 'i.institution_name' in meta:
        extra = meta[['unitid', 'i.institution_name']].rename(columns={'i.institution_name': 'institution_name'})
        names = pd.concat([names, extra.dropna()]).drop_duplicates()
    names['normalized'] = names.institution_name.map(normalize)
    groups = names.groupby('normalized').unitid.agg(lambda x: sorted(set(map(int, x))))
    mapping = {name: ids[0] for name, ids in groups.items() if len(ids) == 1}
    rules = {name: 'exact_normalized_name' for name in mapping}
    aliases = pd.read_csv(Path(__file__).with_name('institution_aliases.csv'))
    known_ids = set(map(int, names.unitid))
    for row in aliases.itertuples():
        if row.unitid not in known_ids:
            raise ValueError(f'Alias points to an unknown local institution: {row}')
        key = normalize(row.network_name)
        if key in mapping and mapping[key] != row.unitid:
            raise ValueError(f'Alias conflicts with existing exact match: {row}')
        mapping[key] = int(row.unitid)
        rules[key] = 'explicit_alias_review_institution_aliases_csv'
    # An abbreviated name may omit only the final word "University". Require
    # a single local institution and no competing college/campus with that name.
    additions = {}
    for name, unitid in mapping.items():
        if name.endswith(' university'):
            short = name[:-len(' university')]
            if short not in groups.index and short not in mapping:
                additions.setdefault(short, set()).add(unitid)
    for name, ids in additions.items():
        if len(ids) == 1:
            mapping[name] = next(iter(ids))
            rules[name] = 'exact_unique_name_omitting_final_university'
    pd.DataFrame([{'normalized': name, 'unitid': unitid, 'match_rule': rules[name]}
                  for name, unitid in mapping.items()]).to_csv(out / 'name_lookup.csv', index=False)
    pd.DataFrame([{'normalized': name, 'unitids': ';'.join(map(str, ids))}
                  for name, ids in groups.items() if len(ids) > 1]).to_csv(out / 'ambiguous_names.csv', index=False)
    return mapping


def load_edges(meta, out, mapping):
    raw = ROOT / 'data/raw/faculty_hiring_2022_v2026_08'
    manifest = json.loads((raw / 'manifest.json').read_text())
    for record in manifest['files']:
        path = raw / record['file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
            raise ValueError(f'Raw download checksum mismatch: {path}')
    recent = pd.read_csv(raw / 'edge-lists.csv')
    recent = recent[recent.TaxonomyLevel == 'Field'].copy()
    names = pd.concat([recent.InstitutionName, recent.DegreeInstitutionName]).dropna().unique()
    audit = pd.DataFrame({'network_name': sorted(names)})
    audit['normalized'] = audit.network_name.map(normalize)
    audit['unitid'] = audit.normalized.map(mapping)
    audit['matched'] = audit.unitid.notna()
    lookup = pd.read_csv(out / 'name_lookup.csv').set_index('normalized').match_rule
    audit['match_rule'] = audit.normalized.map(lookup)
    audit.to_csv(out / 'institution_match_audit.csv', index=False)
    recent['target_unitid'] = recent.InstitutionName.map(normalize).map(mapping)
    recent['source_unitid'] = recent.DegreeInstitutionName.map(normalize).map(mapping)
    # Only exact field labels. Broader domains and guessed field aliases are not
    # pooled into apparently discipline-specific hiring connections.
    fields = sorted(meta.fos.unique())
    available = set(recent.TaxonomyValue)
    pd.DataFrame({'atlas_field': fields, 'exact_network_field':
                  [f if f in available else '' for f in fields]}).to_csv(out / 'field_match_audit.csv', index=False)
    edges22 = recent[recent.TaxonomyValue.isin(fields)].rename(columns={
        'TaxonomyValue': 'fos', 'Total': 'weight'})[
        ['fos', 'target_unitid', 'source_unitid', 'weight']].copy()
    old = ROOT / 'data/raw/clauset_hiring_networks'
    pieces = []
    for prefix, field in [('cs', 'Computer Science'), ('biz', 'Business'), ('hist', 'History')]:
        vertices = pd.read_csv(old / f'{prefix}_vertex.txt', sep='\t', comment='#', header=None)
        vertices.columns = ['node', 'prestige', 'usn', 'nrc', 'region', 'name']
        id_map = dict(zip(vertices.node, vertices.name.map(normalize).map(mapping)))
        edges = pd.read_csv(old / f'{prefix}_edge.txt', sep='\t', comment='#',
                            names=['u', 'v', 'rank', 'gender'])
        edges['source_unitid'] = edges.u.map(id_map)
        edges['target_unitid'] = edges.v.map(id_map)
        edges['fos'] = field
        pieces.append(edges.groupby(['fos', 'target_unitid', 'source_unitid'], dropna=False)
                      .size().reset_index(name='weight'))
        vertices['unitid'] = vertices.node.map(id_map)
        vertices['fos'] = field
        vertices.to_csv(out / f'match_2015_{prefix}.csv', index=False)
    edges15 = pd.concat(pieces, ignore_index=True)
    for label, frame in [('2015', edges15), ('2022_retrospective', edges22)]:
        frame.to_csv(out / f'matched_edges_{label}.csv', index=False)
    return edges15, edges22


def hiring_channel(edges, meta, source, target, x_source, out, label, year):
    """Weighted incoming doctoral-origin exposure; self-hires excluded."""
    source_keys = pd.MultiIndex.from_frame(meta.iloc[source][['unitid', 'fos']])
    target_keys = pd.MultiIndex.from_frame(meta.iloc[target][['unitid', 'fos']])
    edges = edges.dropna(subset=['target_unitid', 'weight']).copy()
    edges = edges[(edges.weight > 0) & (edges.target_unitid != edges.source_unitid)]
    original = edges.groupby(['target_unitid', 'fos']).weight.sum()
    edges = edges.dropna(subset=['source_unitid'])
    cols = source_keys.get_indexer(pd.MultiIndex.from_arrays([edges.source_unitid, edges.fos]))
    rows = target_keys.get_indexer(pd.MultiIndex.from_arrays([edges.target_unitid, edges.fos]))
    keep = (cols >= 0) & (rows >= 0)
    matrix = csr_matrix((edges.loc[keep, 'weight'].to_numpy(), (rows[keep], cols[keep])),
                        shape=(len(target), len(source)))
    observed_weight = np.asarray(matrix.sum(axis=1)).ravel()
    sums = matrix @ x_source
    avg = np.divide(sums, observed_weight[:, None], out=np.full_like(sums, np.nan),
                    where=observed_weight[:, None] > 0)
    n_sources = np.diff(matrix.indptr)
    # Denominator includes all published non-self edge weights for that target
    # with an exactly mapped institution and field, including unmatched origins.
    total_weight = original.reindex(target_keys).to_numpy()
    share = np.divide(observed_weight, total_weight, out=np.full(len(target), np.nan),
                      where=np.isfinite(total_weight) & (total_weight > 0))
    audit = meta.iloc[target][['unitid', 'fos']].copy()
    audit['year'] = year
    audit['observed_sources'] = n_sources
    audit['observed_edge_weight'] = observed_weight
    audit['published_nonself_weight'] = total_weight
    audit['observed_weight_share'] = share
    # Preserve unmatched-origin weights separately in aggregate audit below.
    audit.to_csv(out / f'network_coverage_{label}_{year}.csv', index=False)
    return avg, n_sources, share


def sum_groups(x, codes, size):
    total = np.zeros((size, x.shape[1]))
    np.add.at(total, codes, x)
    return total, np.bincount(codes, minlength=size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261009)
    parser.add_argument('--skills', type=int, default=64)
    parser.add_argument('--skill-ids-file', type=Path,
                        help='Explicit skill_id CSV for exhaustive block processing; no random sampling.')
    parser.add_argument('--tag', default='seed1')
    parser.add_argument('--smoke', action='store_true', help='Four skills; separate validation output.')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.tag):
        parser.error('Invalid tag')
    data = ROOT / 'data/derived/content_channels' / args.tag
    out = ROOT / 'outputs/content_channels' / args.tag
    data.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)
    marker = data / 'complete.json'
    marker.unlink(missing_ok=True)
    meta = pd.read_csv(ROOT / 'data/derived/pilot/master_metadata.csv').sort_values(
        ['unitid', 'fos', 'year']).reset_index(drop=True)
    if meta.duplicated('id').any() or meta.duplicated(['unitid', 'fos', 'year']).any():
        raise ValueError('Duplicate profile keys')
    meta['cell_id'] = pd.factorize(pd.MultiIndex.from_frame(meta[['unitid', 'fos']]))[0]
    meta['field_id'] = pd.Categorical(meta.fos, categories=sorted(meta.fos.unique())).codes
    with gzip.open(ROOT / 'data/raw/detailed_work_activities_scores.gzip', 'rt') as f:
        skills = next(csv.reader(f))[1:]
    cache = ROOT / 'data/derived/pilot/measurement_scores_float64.npy'
    stamp = json.loads(cache.with_name('measurement_scores_manifest.json').read_text())
    source_stat = (ROOT / 'data/raw/detailed_work_activities_scores.gzip').stat()
    if stamp['source_bytes'] != source_stat.st_size or stamp['source_mtime_ns'] != source_stat.st_mtime_ns:
        raise ValueError('Source score file changed since the audited cache was built')
    ids_hash = hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest()
    skills_hash = hashlib.sha256('\n'.join(skills).encode()).hexdigest()
    if stamp['ids_sha256'] != ids_hash or stamp['skills_sha256'] != skills_hash:
        raise ValueError('Existing score cache does not match sorted metadata and source skill order')
    scores = np.load(cache, mmap_mode='r')
    if scores.shape != (len(meta), len(skills)):
        raise ValueError('Wrong score cache shape')
    n_skills = 4 if args.smoke else args.skills
    if not 1 <= n_skills <= len(skills):
        parser.error('Invalid skill count')
    if args.skill_ids_file:
        if args.smoke:
            parser.error('Explicit skill IDs cannot be combined with --smoke')
        requested = pd.read_csv(args.skill_ids_file)['skill_id'].to_numpy()
        if not np.equal(requested, requested.astype(int)).all():
            raise ValueError('Skill IDs must be integers')
        chosen = np.sort(requested.astype(int))
        if not len(chosen) or len(set(chosen)) != len(chosen) or chosen.min() < 0 or chosen.max() >= len(skills):
            raise ValueError('Invalid or duplicated explicit skill IDs')
        n_skills = len(chosen)
    else:
        chosen = np.sort(np.random.default_rng(args.seed).choice(len(skills), n_skills, replace=False))
    x = np.asarray(scores[:, chosen])
    if not np.isfinite(x).all() or (x < 0).any():
        raise ValueError('Nonfinite or negative cached scores')
    years = meta.year.to_numpy()
    counts = meta.syllabi_cnt.to_numpy()
    baseline = (years >= 2002) & (years <= 2007) & (counts >= 9)
    mu, sd = x[baseline].mean(axis=0), x[baseline].std(axis=0)
    if not np.isfinite(sd).all() or (sd <= 1e-10).any():
        raise ValueError('Skill without usable baseline variance')
    z = (x - mu) / sd
    pd.DataFrame({'skill_id': chosen, 'skill': [skills[s] for s in chosen],
                  'baseline_mean': mu, 'baseline_sd': sd}).to_csv(out / 'skill_dictionary.csv', index=False)
    pd.DataFrame({'field_id': range(meta.field_id.nunique()), 'field': sorted(meta.fos.unique())}
                 ).to_csv(out / 'field_dictionary.csv', index=False)
    mapping = match_names(meta, out)
    edges15, edges22 = load_edges(meta, out, mapping)
    previous_year = meta.groupby('cell_id', sort=False).year.shift().to_numpy()
    next_year = meta.groupby('cell_id', sort=False).year.shift(-1).to_numpy()
    unitids = meta.unitid.to_numpy()
    field_ids = meta.field_id.to_numpy()
    # Fixed institution descriptors selected before evaluation, not current resources.
    baseline_meta = meta[meta.year <= 2007].sort_values('year').drop_duplicates('unitid', keep='last')
    baseline_meta = baseline_meta.set_index('unitid')
    finance = pd.read_csv(ROOT / 'data/interim/ipeds_finance_state_approp_panel.csv')
    finance = finance[finance.year.between(2005, 2007)].groupby('unitid').state_approp_share.mean()
    diagnostics = []
    field_diagnostics = []
    moments = []
    for year in range(2008, 2018):
        source = np.flatnonzero((years == year - 1) & (counts >= 3))
        target = np.flatnonzero((years == year) & (years - previous_year == 1) & (counts >= 3))
        target = target[counts[target - 1] >= 3]
        lag = target - 1
        src = z[source]
        own = z[lag]
        inst_codes, inst_labels = pd.factorize(unitids[source])
        sums_i, ns_i = sum_groups(src, inst_codes, len(inst_labels))
        ipos = pd.Index(inst_labels).get_indexer(unitids[target])
        sums_f, ns_f = sum_groups(src, field_ids[source], meta.field_id.nunique())
        fi = field_ids[target]
        ni = ns_i[ipos] - 1
        nf = ns_f[fi] - 1
        no = len(source) - ns_i[ipos] - ns_f[fi] + 1
        wi = np.divide(sums_i[ipos] - own, ni[:, None], out=np.full_like(own, np.nan), where=ni[:, None] > 0)
        wf = np.divide(sums_f[fi] - own, nf[:, None], out=np.full_like(own, np.nan), where=nf[:, None] > 0)
        other_sum = src.sum(axis=0) - sums_i[ipos] - sums_f[fi] + own
        wo = np.divide(other_sum, no[:, None], out=np.full_like(own, np.nan), where=no[:, None] > 0)
        reconstructed = np.nan_to_num(wi) * ni[:, None] + np.nan_to_num(wf) * nf[:, None] + np.nan_to_num(wo) * no[:, None] + own
        if (ipos < 0).any() or not np.all(ni + nf + no == len(source) - 1):
            raise ValueError('Invalid source partition')
        if not np.allclose(reconstructed, src.sum(axis=0), atol=1e-8):
            raise ValueError('Source partition failed to reconstruct content')
        hiring15, n15, share15 = hiring_channel(edges15, meta, source, target, src, out, '2015', year)
        hiring22, n22, share22 = hiring_channel(edges22, meta, source, target, src, out, '2022_retrospective', year)
        follow = (next_year[target] - years[target] == 1)
        follow_index = np.minimum(target + 1, len(meta) - 1)
        follow &= counts[follow_index] >= 3
        delta2 = np.full_like(own, np.nan)
        delta2[follow] = (z[follow_index[follow]] - own[follow]) / 2
        k2 = np.where(follow, np.minimum(np.minimum(counts[lag], counts[target]), counts[follow_index]), 0)
        repetitions = n_skills
        base = baseline_meta.reindex(unitids[target])
        sector = base.sector.fillna('baseline_missing').to_numpy()
        state = base.state_code.fillna('baseline_missing').to_numpy()
        carnegie = base.carnegie_group_label.fillna('baseline_missing').to_numpy()
        fiscal = finance.reindex(unitids[target]).to_numpy()
        frame = pd.DataFrame({
            'unitid': np.repeat(unitids[target], repetitions),
            'cell_id': np.repeat(meta.cell_id.to_numpy()[target], repetitions),
            'field_id': np.repeat(fi, repetitions), 'year': year,
            'skill_id': np.tile(chosen, len(target)),
            'delta1': (z[target] - own).ravel(), 'delta2': delta2.ravel(),
            'lag_score': own.ravel(), 'same_inst': wi.ravel(), 'same_field': wf.ravel(),
            'other': wo.ravel(), 'hiring2015': hiring15.ravel(), 'hiring2022': hiring22.ravel(),
            'coverage1': np.repeat(np.minimum(counts[lag], counts[target]), repetitions),
            'coverage2': np.repeat(k2, repetitions),
            'n_previous': np.repeat(counts[lag], repetitions),
            'n_current': np.repeat(counts[target], repetitions),
            'n_inst': np.repeat(ni, repetitions), 'n_field': np.repeat(nf, repetitions),
            'n_other': np.repeat(no, repetitions), 'n_hiring2015': np.repeat(n15, repetitions),
            'n_hiring2022': np.repeat(n22, repetitions),
            'share_hiring2015': np.repeat(share15, repetitions),
            'share_hiring2022': np.repeat(share22, repetitions),
            'baseline_sector': np.repeat(sector, repetitions),
            'baseline_state': np.repeat(state, repetitions),
            'baseline_carnegie': np.repeat(carnegie, repetitions),
            'baseline_fiscal': np.repeat(fiscal, repetitions)})
        # 2015 network collected by August 2013: use only outcomes from 2014.
        # 2022 network is retrospective throughout the Atlas observation window.
        if year < 2014:
            frame['hiring2015'] = np.nan
        frame.to_csv(data / f'panel_{year}.csv.gz', index=False, compression='gzip')
        if args.skill_ids_file:
            for channel in ['same_inst', 'same_field', 'hiring2015', 'hiring2022']:
                end = 2015 if channel == 'hiring2015' else 2013
                if year <= end:
                    values = frame.loc[(frame.coverage1 >= 9) & np.isfinite(frame[channel]), channel]
                    moments.append({'channel': channel, 'n': len(values),
                                    'sum': values.sum(), 'sum_sq': np.square(values).sum()})
            for field_id, group in frame.groupby('field_id'):
                for coverage in (3, 9, 20):
                    sub = group[group.coverage1 >= coverage]
                    evaluated = sub[sub.coverage2 >= coverage]
                    increased = evaluated[evaluated.delta1 >= 0.1]
                    field_diagnostics.append({'field_id': field_id, 'year': year,
                        'min_syllabi': coverage, 'skills': n_skills,
                        'annual_rows': len(sub), 'two_year_rows': len(evaluated),
                        'annual_profile_pairs': len(sub) // n_skills,
                        'two_year_profile_pairs': len(evaluated) // n_skills,
                        'annual_abs_change_sum': sub.delta1.abs().sum(),
                        'two_year_abs_change_sum': evaluated.delta2.abs().sum(),
                        'evaluable_initial_increases': len(increased),
                        'retained_initial_increases': int((2 * increased.delta2 >= 0.1).sum())})
        for coverage in (3, 9, 20):
            sub = frame[frame.coverage1 >= coverage]
            evaluated = sub[sub.coverage2 >= coverage]
            increases = evaluated[evaluated.delta1 >= 0.1]
            diagnostics.append({'year': year, 'min_syllabi': coverage,
                'annual_profile_pairs': len(sub) // repetitions,
                'two_year_profile_pairs': len(evaluated) // repetitions,
                'institutions': sub.unitid.nunique(),
                'mean_abs_annual_change': sub.delta1.abs().mean(),
                'mean_abs_two_year_annualized_change': evaluated.delta2.abs().mean(),
                'initial_increases_ge_01sd_evaluable': len(increases),
                'fraction_still_ge_01sd_next_year': (2 * increases.delta2 >= 0.1).mean() if len(increases) else np.nan})
        print(f'{year}: {len(target):,} consecutive program pairs × {repetitions} skills', flush=True)
    pd.DataFrame(diagnostics).to_csv(out / 'measurement_diagnostics.csv', index=False)
    if args.skill_ids_file:
        pd.DataFrame(moments).to_csv(out / 'channel_moments.csv', index=False)
        pd.DataFrame(field_diagnostics).to_csv(out / 'measurement_by_field.csv', index=False)
    config = {'seed': args.seed, 'sampled_skills': n_skills, 'smoke': args.smoke,
        'selection': 'explicit block of exhaustive universe' if args.skill_ids_file else 'fixed random sample',
        'skill_ids': chosen.tolist(),
        'baseline': [2002, 2007], 'evaluation': [2008, 2017], 'source_min_syllabi': 3,
        'rca_used': False, 'outcome1': 'annual change in inferred score / baseline skill SD',
        'outcome2': 'change from t-1 to t+1 / (2 × baseline skill SD); all three profiles observed',
        'source_channels': 'prior-year equal-program mean; own program excluded; disjoint generic channels',
        'hiring2015': 'doctoral origin → employer; self-hires excluded; outcomes 2014 onward only',
        'hiring2022': 'retrospective structural sensitivity only; underlying sample 2011–2020',
        'institution_matching': 'exact normalized names and explicit aliases; no fuzzy matches',
        'field_matching': 'exact Atlas/network field labels only',
        'negative_source_scores_clipped_in_audited_cache': stamp['negative_scores_clipped'],
        'limitations': ['Inferred syllabus content is not measured student learning.',
            'A two-year outcome is not proof that all underlying courses maintained content.',
            'Source coverage and composition change over time.',
            'Hiring connections do not identify imitation, contact, or causal transmission.',
            'No dated hiring events or labor-demand outcomes are included in this first pilot.']}
    (out / 'design.json').write_text(json.dumps(config, indent=2) + '\n')
    marker.write_text(json.dumps(config, indent=2) + '\n')


if __name__ == '__main__':
    main()
