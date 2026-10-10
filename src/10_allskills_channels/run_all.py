"""Exhaustive DWA analysis, with resumable disjoint blocks (no RCA)."""
import argparse
import csv
import gzip
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def run(command, log):
    with log.open('w') as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed; inspect {log}')


def taxonomy(skills):
    reference = ROOT / 'data/raw/onet_reference'
    dwa = pd.read_csv(reference / 'dwa_reference.txt', sep='\t', dtype=str)
    content = pd.read_csv(reference / 'content_model_reference.txt', sep='\t', dtype=str)
    labels = content.set_index('Element ID')['Element Name'].to_dict()
    by_title = {title: list(group['Element ID'].unique())
                for title, group in dwa.groupby('DWA Title')}
    rows = []
    for skill_id, title in enumerate(skills):
        elements = by_title.get(title, [])
        branches = sorted({x[:5] for x in elements})
        branch = branches[0] if len(branches) == 1 else 'unmapped'
        rows.append(dict(skill_id=skill_id, skill=title, onet_branch_id=branch,
                         onet_branch=labels.get(branch, 'Unmapped / ambiguous'),
                         match_status='exact' if len(elements) == 1 else
                         ('same_branch_multiple_elements' if len(branches) == 1 else 'unmapped_or_ambiguous'),
                         element_ids=';'.join(sorted(elements))))
    return pd.DataFrame(rows)


def summarize(out, tags):
    coefficients = []; influences = []; measurements = []; losses = []; failures = []
    for tag in tags:
        folder = ROOT / 'outputs/content_channels' / tag
        for name, collection in [('block_coefficients.csv', coefficients),
                                 ('cluster_influences.csv.gz', influences),
                                 ('measurement_by_field.csv', measurements),
                                 ('forecast_losses.csv.gz', losses),
                                 ('block_failures.csv', failures)]:
            path = folder / name
            if path.exists():
                frame = pd.read_csv(path); frame['block'] = tag; collection.append(frame)
    keys = ['outcome', 'scope', 'model', 'term']
    if coefficients:
        coefs = pd.concat(coefficients, ignore_index=True)
        coefs.to_csv(out / 'coefficients_by_block.csv', index=False)
        scores = pd.concat(influences, ignore_index=True)
        score_groups = scores.groupby(keys, sort=False)
        results = []; combined_influences = []
        from scipy.stats import t as student_t
        for key, group in coefs.groupby(keys):
            weights = group.set_index('block')['rows']; weights = weights / weights.sum()
            use = score_groups.get_group(key).copy()
            use['weighted'] = use.influence * use.block.map(weights)
            clustered = use.groupby('unitid').weighted.sum()
            combined = clustered.rename('influence').reset_index()
            for col,val in zip(keys,key):
                combined[col] = val
            combined_influences.append(combined)
            se = np.sqrt(np.square(clustered).sum())
            estimate = np.dot(group.estimate, group.block.map(weights))
            df = max(1, len(clustered) - 1)
            p = 2 * student_t.sf(abs(estimate / se), df) if se > 0 else np.nan
            margin = student_t.ppf(.975, df) * se
            results.append(dict(zip(keys, key), estimate=estimate, se=se, p=p,
                                ci_low=estimate-margin, ci_high=estimate+margin,
                                blocks=len(group), rows=int(group.rows.sum()),
                                institutions=len(clustered)))
        summary = pd.DataFrame(results)
        support = coefs.groupby(keys).supporting_institutions.min().rename('min_supporting_institutions').reset_index()
        summary = summary.merge(support, on=keys)
        summary['small_support'] = summary.min_supporting_institutions < 20
        field_labels = pd.read_csv(ROOT / 'outputs/content_channels' / tags[0] / 'field_dictionary.csv').set_index('field_id').field
        tax_labels = pd.read_csv(out / 'skill_taxonomy.csv').drop_duplicates('onet_branch_id').set_index('onet_branch_id').onet_branch
        summary['category_label'] = summary.term.str.extract(r'field_id::(\d+):')[0].astype(float).map(field_labels)
        onet_keys = summary.term.str.extract(r'onet_branch_id::([^:]+):')[0]
        summary['category_label'] = summary.category_label.fillna(onet_keys.map(tax_labels))
        # BH within each outcome/scope/model across all reported terms.
        summary['q_bh'] = np.nan
        for _, group in summary.groupby(['outcome', 'scope', 'model']):
            valid = group.p.dropna().sort_values(); n = len(valid)
            if n:
                q = np.minimum.accumulate((valid.to_numpy()*n/np.arange(1,n+1))[::-1])[::-1]
                summary.loc[valid.index, 'q_bh'] = np.minimum(q, 1)
        summary.to_csv(out / 'channel_summary.csv', index=False)
        # A difference in significance is not a significant difference. Test
        # equality of category slopes using the shared-institution covariance.
        from scipy.stats import chi2
        combined = pd.concat(combined_influences, ignore_index=True)
        joint = []
        for key, group in summary[summary.scope.isin(['discipline','onet']) & ~summary.small_support].groupby(['outcome','scope','model']):
            for channel in ['same_inst_std','same_field_std']:
                sub = group[group.term.str.endswith(':'+channel)].sort_values('term')
                if len(sub)<2:
                    continue
                use = combined
                for col,val in zip(['outcome','scope','model'],key):
                    use = use[use[col]==val]
                matrix = use.pivot(index='unitid',columns='term',values='influence').reindex(columns=sub.term).fillna(0).to_numpy()
                contrast = matrix[:,1:]-matrix[:,[0]]
                covariance = contrast.T @ contrast
                difference = sub.estimate.to_numpy()[1:]-sub.estimate.iloc[0]
                rank = np.linalg.matrix_rank(covariance)
                statistic = float(difference @ np.linalg.pinv(covariance) @ difference)
                joint.append(dict(zip(['outcome','scope','model'],key),channel=channel,
                                  categories=len(sub),df=rank,wald=statistic,
                                  p=chi2.sf(statistic,rank) if rank else np.nan))
        pd.DataFrame(joint).to_csv(out / 'heterogeneity_tests.csv', index=False)
    if measurements:
        measurement = pd.concat(measurements, ignore_index=True)
        sums = ['annual_rows', 'two_year_rows', 'annual_abs_change_sum',
                'two_year_abs_change_sum', 'evaluable_initial_increases', 'retained_initial_increases']
        agg = measurement.groupby(['field_id','year','min_syllabi'])[sums].sum().reset_index()
        agg['mean_abs_annual_change'] = agg.annual_abs_change_sum / agg.annual_rows
        agg['mean_abs_two_year_change'] = agg.two_year_abs_change_sum / agg.two_year_rows
        agg['retention_fraction'] = agg.retained_initial_increases / agg.evaluable_initial_increases
        fields = pd.read_csv(ROOT / 'outputs/content_channels' / tags[0] / 'field_dictionary.csv')
        agg.merge(fields).to_csv(out / 'measurement_by_discipline.csv', index=False)
    if losses:
        loss = pd.concat(losses, ignore_index=True)
        groupcols = ['outcome', 'dimension', 'category', 'model']
        agg = loss.groupby(groupcols)[['n', 'sse', 'sae', 'zero_sse', 'base_sse']].sum().reset_index()
        agg['rmse'] = np.sqrt(agg.sse / agg.n); agg['mae'] = agg.sae / agg.n
        agg['mse_gain_vs_baseline'] = 1 - agg.sse / agg.base_sse
        agg['r2_vs_no_change'] = 1 - agg.sse / agg.zero_sse
        fields = pd.read_csv(ROOT / 'outputs/content_channels' / tags[0] / 'field_dictionary.csv')
        field_labels = dict(zip(fields.field_id.astype(str), fields.field))
        tax = pd.read_csv(out / 'skill_taxonomy.csv').drop_duplicates('onet_branch_id')
        tax_labels = dict(zip(tax.onet_branch_id, tax.onet_branch))
        agg['category_label'] = [field_labels.get(str(c), str(c)) if d=='field_id' else
                                 tax_labels.get(str(c), str(c)) if d=='onet_branch_id' else 'All skills'
                                 for d,c in zip(agg.dimension,agg.category)]
        clustered = loss.groupby(groupcols + ['unitid'])[['n','sse','zero_sse','base_sse']].sum().reset_index()
        clustered.to_csv(out / 'forecast_losses_by_institution.csv.gz', index=False)
        rng = np.random.default_rng(20261009); uncertainty = []
        for key, group in clustered.groupby(groupcols):
            ix = rng.integers(0,len(group),size=(300,len(group)))
            numerator = group.sse.to_numpy()[ix].sum(axis=1)
            denominator = group.base_sse.to_numpy()[ix].sum(axis=1)
            draws = 1 - numerator/denominator
            uncertainty.append(dict(zip(groupcols,key),institutions=len(group),
                                    gain_ci_low=np.quantile(draws,.025),gain_ci_high=np.quantile(draws,.975)))
        agg = agg.merge(pd.DataFrame(uncertainty),on=groupcols)
        agg.to_csv(out / 'forecast_by_discipline_and_taxonomy.csv', index=False)
    if failures:
        pd.concat(failures).to_csv(out / 'skipped_or_failed_models.csv', index=False)
        print(f'NOTE: {sum(len(x) for x in failures)} skipped/failed models; inspect skipped_or_failed_models.csv.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='allskills')
    parser.add_argument('--block-size', type=int, default=32)
    parser.add_argument('--seed', type=int, default=20261009, help='Partition order only; every skill is included.')
    parser.add_argument('--smoke', action='store_true', help='Eight skills for software validation only.')
    parser.add_argument('--keep-panels', action='store_true', help='Keep large intermediate compressed panels.')
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.tag) or not 1 <= args.block_size <= 128:
        parser.error('Invalid tag or block size (1–128)')
    if args.smoke and not args.tag.endswith('_smoke'):
        parser.error('Use a tag ending in _smoke for software validation')
    out = ROOT / 'outputs/allskills_channels' / args.tag; out.mkdir(parents=True, exist_ok=True)
    with gzip.open(ROOT / 'data/raw/detailed_work_activities_scores.gzip', 'rt') as stream:
        skills = next(csv.reader(stream))[1:]
    tax = taxonomy(skills); tax.to_csv(out / 'skill_taxonomy.csv', index=False)
    files = [HERE / 'run_all.py', HERE / 'fit_block.R',
             ROOT / 'src/09_content_channels/build_panel.py',
             ROOT / 'data/derived/pilot/measurement_scores_manifest.json',
             ROOT / 'data/derived/pilot/master_metadata.csv',
             ROOT / 'src/09_content_channels/institution_aliases.csv']
    files += list((ROOT / 'data/raw/onet_reference').glob('*.txt'))
    fingerprints = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    config = dict(tag=args.tag, block_size=args.block_size, seed=args.seed, smoke=args.smoke,
                  skills_total=len(skills), fingerprints=fingerprints,
                  taxonomy_version='Local reference previously documented as O*NET 29.1; hashes recorded',
                  estimator='row-weighted mean of block estimates, shared institution cluster influences')
    manifest = out / 'design.json'
    if manifest.exists() and json.loads(manifest.read_text()) != config:
        raise ValueError('Configuration/code/input changed: choose a new tag to avoid mixing runs.')
    manifest.write_text(json.dumps(config, indent=2)+'\n')
    order = np.random.default_rng(args.seed).permutation(len(skills))
    if args.smoke:
        # Include each official branch in the small validation sample.
        first = tax.groupby('onet_branch_id').skill_id.first().to_numpy()
        order = np.array(list(dict.fromkeys(list(first)+list(order))))[:8]
    tags = []; all_ids = []
    for block, start in enumerate(range(0, len(order), args.block_size)):
        tag = f'{args.tag}_b{block:03d}'; tags.append(tag)
        ids = order[start:start+args.block_size]; all_ids.extend(ids.tolist())
        ids_file = out / f'block_{block:03d}_skills.csv'
        pd.DataFrame({'skill_id': ids}).to_csv(ids_file, index=False)
        folder = ROOT / 'outputs/content_channels' / tag
        folder.mkdir(parents=True, exist_ok=True)
        panel_marker = ROOT / 'data/derived/content_channels' / tag / 'complete.json'
        if not (folder / 'channel_moments.csv').exists() or not panel_marker.exists():
            print(f'Building {block+1}/{(len(order)+args.block_size-1)//args.block_size}: {len(ids)} skills', flush=True)
            run(['python3','src/09_content_channels/build_panel.py','--tag',tag,
                 '--skill-ids-file',str(ids_file)], folder / 'build.log')
    assert len(all_ids) == len(set(all_ids))
    if not args.smoke:
        assert sorted(all_ids) == list(range(len(skills)))
    pd.DataFrame({'skill_id': all_ids}).merge(tax).to_csv(out / 'skills_included.csv', index=False)
    moments = pd.concat([pd.read_csv(ROOT / 'outputs/content_channels' / tag / 'channel_moments.csv') for tag in tags])
    moments = moments.groupby('channel')[['n','sum','sum_sq']].sum().reset_index()
    moments['mean'] = moments['sum'] / moments.n
    moments['sd'] = np.sqrt((moments.sum_sq-moments['sum']**2/moments.n)/(moments.n-1))
    moments.to_csv(out / 'global_scales.csv', index=False)
    for index, tag in enumerate(tags):
        folder = ROOT / 'outputs/content_channels' / tag
        if not (folder / 'block_complete.json').exists():
            print(f'Estimating {index+1}/{len(tags)}: {tag}', flush=True)
            run(['Rscript',str(HERE / 'fit_block.R'),tag,str(out)], folder / 'models.log')
        if not args.keep_panels:
            for path in (ROOT / 'data/derived/content_channels' / tag).glob('panel_*.csv.gz'):
                path.unlink()
    summarize(out, tags)
    (out / 'complete.json').write_text(json.dumps(dict(blocks=len(tags), skills=len(all_ids), smoke=args.smoke)))
    print(f'Finished: {out}', flush=True)


if __name__ == '__main__':
    main()
