"""Historical institutional selectivity, resources and Carnegie; public IPEDS only."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
URL = 'https://nces.ed.gov/ipeds/datacenter/data/'


def read_zip(path):
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith('.csv')]
        revised = [n for n in names if n.lower().endswith('_rv.csv')]
        if len(revised) == 1:
            names = revised
        if len(names) != 1:
            raise ValueError(f'Expected one data CSV: {path}')
        d = pd.read_csv(archive.open(names[0]), encoding='cp1252', low_memory=False)
    d.columns = d.columns.str.strip().str.upper()
    d['UNITID'] = pd.to_numeric(d.UNITID, errors='raise').astype(int)
    if d.UNITID.duplicated().any():
        raise ValueError(f'Duplicate institutional records: {path}')
    return d


def numeric(d, name):
    if name not in d:
        raise ValueError(f'Missing documented column {name}')
    return pd.to_numeric(d[name], errors='coerce')


def download(name, directory, allow):
    path = directory/f'{name}.zip'
    if not path.exists():
        if not allow:
            raise FileNotFoundError(f'{path}; run without --offline to download public data')
        directory.mkdir(parents=True, exist_ok=True)
        r = requests.get(URL+name+'.zip', timeout=60)
        r.raise_for_status()
        if r.content[:2] != b'PK':
            raise ValueError('Response is not an IPEDS zip: '+name)
        tmp = path.with_suffix('.tmp')
        tmp.write_bytes(r.content)
        if not zipfile.is_zipfile(tmp):
            raise ValueError('Corrupt ZIP '+name)
        tmp.replace(path)
    return path


def standardized(series):
    valid = series.dropna()
    if len(valid) < 30 or valid.std(ddof=0) <= 0:
        raise ValueError('Insufficient national baseline to standardize selectivity')
    return (series-valid.mean())/valid.std(ddof=0), dict(n=len(valid), mean=float(valid.mean()), sd=float(valid.std(ddof=0)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    directory = ROOT/'data/raw/ipeds_selectivity'
    paths = [download('HD2006', directory, not args.offline)]
    hd = read_zip(paths[0]).set_index('UNITID')
    # Comparable institutional scale: four-year institutions in the historical
    # directory, independently of matching to our curriculum sample.
    universe = hd.index[numeric(hd, 'ICLEVEL') == 1]
    annual, bridge = [], []
    for year in (2004, 2005, 2006):
        path = download(f'IC{year}', directory, not args.offline)
        paths.append(path)
        d = read_zip(path).set_index('UNITID').reindex(universe)
        sat_cols = ['SATVR25', 'SATVR75', 'SATMT25', 'SATMT75']
        sat = pd.DataFrame({c: numeric(d, c) for c in sat_cols})
        sat_ok = sat.ge(200).all(axis=1) & sat.le(800).all(axis=1)
        sat_ok &= (sat.SATVR25 <= sat.SATVR75) & (sat.SATMT25 <= sat.SATMT75)
        sat_ok &= numeric(d, 'SATPCT').between(20, 100)
        sat_mid = (sat.sum(axis=1)/2).where(sat_ok)
        a25, a75 = numeric(d, 'ACTCM25'), numeric(d, 'ACTCM75')
        act_ok = a25.between(1,36) & a75.between(1,36) & (a25 <= a75)
        act_ok &= numeric(d, 'ACTPCT').between(20,100)
        act_mid = ((a25+a75)/2).where(act_ok)
        both = sat_mid.notna() & act_mid.notna()
        if both.sum() < 30:
            raise ValueError(f'Insufficient dual-test reporting to bridge tests: {year}')
        xx = np.column_stack([np.ones(both.sum()), act_mid[both]])
        yy = sat_mid[both].to_numpy()
        beta = np.linalg.lstsq(xx, yy, rcond=None)[0]
        residual = yy-xx@beta
        leverage = np.sum((xx@np.linalg.inv(xx.T@xx))*xx, axis=1)
        if beta[1] <= 0:
            raise ValueError('Invalid ACT-to-SAT bridge')
        bridge.append(dict(year=year, institutions=int(both.sum()), intercept=beta[0], slope=beta[1],
                           r2=1-np.sum(residual**2)/np.sum((yy-yy.mean())**2),
                           leave_one_out_rmse_sat=float(np.sqrt(np.mean((residual/(1-leverage))**2)))))
        # Institution-level empirical calibration, not individual concordance.
        # Prefer the test taken by the larger proportion of entrants.
        use_act = act_mid.notna() & (sat_mid.isna() | (numeric(d,'ACTPCT') > numeric(d,'SATPCT')))
        combined = sat_mid.copy()
        combined[use_act] = beta[0]+beta[1]*act_mid[use_act]
        applicants, admitted = numeric(d,'APPLCN'), numeric(d,'ADMSSN')
        valid_admission = (applicants > 0) & admitted.between(0, applicants) & (numeric(d,'OPENADMP') == 2)
        rejection = (1-admitted/applicants).where(valid_admission)
        annual.append(pd.DataFrame(dict(unitid=universe, year=year, test_mid=combined.to_numpy(),
            sat_mid=sat_mid.to_numpy(), act_mid=act_mid.to_numpy(), rejection=rejection.to_numpy(),
            test_type=np.where(combined.isna(),'missing',np.where(use_act,'ACT_calibrated','SAT')))))
    annual = pd.concat(annual, ignore_index=True)
    g = annual.groupby('unitid')
    profile = g[['test_mid','sat_mid','act_mid','rejection']].mean()
    for measure in ('test_mid','sat_mid','act_mid','rejection'):
        n = g[measure].count()
        profile['n_'+measure] = n
        profile.loc[n < 2,measure] = np.nan
    scales = {}
    for name, value in [('selectivity','test_mid'),('sat_selectivity','sat_mid'),
                         ('act_selectivity','act_mid'),('rejection_selectivity','rejection')]:
        profile[name], scales[name] = standardized(profile[value])
    profile['carnegie_basic_2005'] = numeric(hd,'CCBASIC').reindex(profile.index).where(lambda x:x>0)
    profile['institution_control'] = numeric(hd,'CONTROL').reindex(profile.index).where(lambda x:x.isin([1,2,3]))
    # Preserve actual 2005 categories instead of imposing an ordinal prestige scale.
    profile['carnegie_group'] = profile.carnegie_basic_2005.map(
        lambda c: 'doctoral' if 15 <= c <= 17 else 'masters' if 18 <= c <= 20 else
        'bachelors' if 21 <= c <= 23 else 'other' if pd.notna(c) else None)
    finance = []
    for year in (2004,2005,2006):
        for form, instruction, research in [('F1A','F1C011','F1C021'),('F2','F2E011','F2E021')]:
            name = f'F{year-2001:02d}{year-2000:02d}_{form}'
            path = download(name, ROOT/'data/raw/ipeds_finance', not args.offline)
            paths.append(path)
            f = read_zip(path)
            v1, v2 = numeric(f,instruction), numeric(f,research)
            finance.append(pd.DataFrame(dict(unitid=f.UNITID, year=year,
                instruction=v1.where(v1>=0),research=v2.where(v2>=0))))
    finance = pd.concat(finance,ignore_index=True)
    if finance.duplicated(['unitid','year']).any():
        raise ValueError('Institution reports multiple finance forms in same year; audit required')
    fg = finance.groupby('unitid')
    for name in ('instruction','research'):
        avg = fg[name].mean().where(fg[name].count()>=2)
        profile[name+'_log'] = np.log1p(avg).reindex(profile.index)
    profile['baseline_last_year'] = 2006
    out = ROOT/'data/derived/institutional_selectivity'
    audit = ROOT/'outputs/institutional_selectivity/baseline2004_2006'
    out.mkdir(parents=True,exist_ok=True);audit.mkdir(parents=True,exist_ok=True)
    profile.reset_index().to_csv(out/'institution_profile.csv',index=False)
    annual.to_csv(out/'annual_measurements.csv',index=False)
    pd.DataFrame(bridge).to_csv(audit/'test_bridge.csv',index=False)
    meta = pd.read_csv(ROOT/'data/derived/pilot/master_metadata.csv')
    cohorts = dict(all_metadata=meta, consecutive_history=meta[meta.syllabi_cnt>=9])
    # Exact endpoint coverage cohort for the prospective incorporation analysis.
    keys = set(map(tuple,meta.loc[meta.syllabi_cnt>=9,['unitid','fos','year']].to_numpy()))
    eligible = meta[(meta.syllabi_cnt>=9) & meta.year.between(2008,2016)].copy()
    keep = [all((r.unitid,r.fos,y) in keys for y in (r.year-2,r.year-1,r.year+1)) for r in eligible.itertuples()]
    cohorts['four_year_receivers'] = eligible[keep]
    coverage=[]
    for label,m in cohorts.items():
        ids = pd.Index(m.unitid.unique());matched=profile.reindex(ids)
        for col in ('selectivity','sat_selectivity','act_selectivity','rejection_selectivity','instruction_log','research_log','carnegie_basic_2005'):
            n=int(matched[col].notna().sum());coverage.append(dict(cohort=label,measure=col,institutions=len(ids),covered=n,fraction=n/len(ids)))
        complete=matched[['selectivity','instruction_log','research_log','carnegie_basic_2005','institution_control']].notna().all(axis=1)
        coverage.append(dict(cohort=label,measure='adjusted_complete',institutions=len(ids),covered=int(complete.sum()),fraction=float(complete.mean())))
    pd.DataFrame(coverage).to_csv(audit/'coverage.csv',index=False)
    design=dict(baseline=[2004,2006],minimum_observed_years=2,minimum_test_reporting_percent=20,
        source=URL,scale_population='HD2006 four-year institutions; independent of curriculum matching',
        hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        scales=scales,proxy='selectivity, not direct prestige',
        resources='log1p nominal total spending averaged 2004-2006; not per-student; no F3 research/public-service conflation',
        bridge='OLS institutional ACT midpoint to SAT reading+math IQR midpoint; prefer dominant test; ecological calibration')
    (out/'design.json').write_text(json.dumps(design,indent=2)+'\n')
    (audit/'design.json').write_text(json.dumps(design,indent=2)+'\n')
    print(pd.DataFrame(coverage).query("cohort=='four_year_receivers'").to_string(index=False))
    print(f'Prepared: {out}/institution_profile.csv')


if __name__ == '__main__':
    main()
