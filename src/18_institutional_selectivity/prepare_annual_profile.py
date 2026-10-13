"""Measure selectivity and resources in each historical year, never from later years."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from prepare_profile import ROOT, URL, download, numeric, read_zip, standardized


def admission_total(d, total, male, female):
    if total in d:
        return numeric(d,total)
    parts = pd.concat([numeric(d,male),numeric(d,female)],axis=1)
    return parts.where(parts>=0).sum(axis=1,min_count=2)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    directory=ROOT/'data/raw/ipeds_selectivity'
    paths=[];profiles=[];bridges=[];scales=[];missing=[]
    for year in range(2002,2016):
        hp=download(f'HD{year}',directory,not args.offline)
        ap=download(f'IC{year}' if year<2014 else f'ADM{year}',directory,not args.offline)
        paths.extend([hp,ap]);hd=read_zip(hp).set_index('UNITID')
        universe=hd.index[numeric(hd,'ICLEVEL')==1]
        d=read_zip(ap).set_index('UNITID').reindex(universe)
        columns=['SATVR25','SATVR75','SATMT25','SATMT75']
        sat=pd.DataFrame({c:numeric(d,c) for c in columns})
        valid=sat.ge(200).all(axis=1)&sat.le(800).all(axis=1)
        valid&=(sat.SATVR25<=sat.SATVR75)&(sat.SATMT25<=sat.SATMT75)
        valid&=numeric(d,'SATPCT').between(20,100)
        sat_mid=(sat.sum(axis=1)/2).where(valid)
        a25,a75=numeric(d,'ACTCM25'),numeric(d,'ACTCM75')
        valid=a25.between(1,36)&a75.between(1,36)&(a25<=a75)&numeric(d,'ACTPCT').between(20,100)
        act_mid=((a25+a75)/2).where(valid)
        both=sat_mid.notna()&act_mid.notna()
        if both.sum()<30:raise ValueError(f'Insufficient dual-test reporting in {year}')
        x=np.column_stack([np.ones(both.sum()),act_mid[both]]);y=sat_mid[both].to_numpy()
        beta=np.linalg.lstsq(x,y,rcond=None)[0];residual=y-x@beta
        h=np.sum((x@np.linalg.inv(x.T@x))*x,axis=1)
        if beta[1]<=0:raise ValueError('Nonpositive test bridge slope')
        bridges.append(dict(year=year,institutions=int(both.sum()),intercept=beta[0],slope=beta[1],
            r2=1-np.sum(residual**2)/np.sum((y-y.mean())**2),
            leave_one_out_rmse_sat=float(np.sqrt(np.mean((residual/(1-h))**2)))))
        use_act=act_mid.notna()&(sat_mid.isna()|(numeric(d,'ACTPCT')>numeric(d,'SATPCT')))
        combined=sat_mid.copy();combined[use_act]=beta[0]+beta[1]*act_mid[use_act]
        applications=admission_total(d,'APPLCN','APPLCNM','APPLCNW')
        admissions=admission_total(d,'ADMSSN','ADMSSNM','ADMSSNW')
        # ADM2014+ is restricted to institutions required to report admissions.
        closed=(numeric(d,'OPENADMP')==2) if 'OPENADMP' in d else pd.Series(True,index=d.index)
        good=(applications>0)&admissions.between(0,applications)&closed
        rejection=(1-admissions/applications).where(good)
        p=pd.DataFrame(index=universe);p.index.name='unitid'
        for name,values in [('selectivity',combined),('sat_selectivity',sat_mid),('act_selectivity',act_mid),('rejection_selectivity',rejection)]:
            p[name],scale=standardized(values);scales.append(dict(year=year,measure=name,**scale))
        p['sat_mid']=sat_mid;p['act_mid']=act_mid;p['admission_rate']=1-rejection
        p['test_type']=np.where(combined.isna(),'missing',np.where(use_act,'ACT_calibrated','SAT'))
        p['institution_control']=numeric(hd,'CONTROL').reindex(p.index).where(lambda v:v.isin([1,2,3]))
        cc='CCBASIC' if 'CCBASIC' in hd else 'CARNEGIE'
        rawcc=numeric(hd,cc).reindex(p.index).where(lambda v:v>0)
        p['carnegie_code']=rawcc
        p['carnegie_classification']=rawcc.map(lambda v:cc+':'+str(int(v)) if pd.notna(v) else None)
        # Use totals as distinct capacity controls, without calling them status.
        finance=[]
        for form,instruction,research in [('F1A','F1C011','F1C021'),('F2','F2E011','F2E021')]:
            name=f'F{year-2001:02d}{year-2000:02d}_{form}'
            fp=download(name,ROOT/'data/raw/ipeds_finance',not args.offline);paths.append(fp)
            f=read_zip(fp)
            finance.append(pd.DataFrame(dict(unitid=f.UNITID,
                instruction=numeric(f,instruction).where(lambda v:v>=0),
                research=numeric(f,research).where(lambda v:v>=0))))
        f=pd.concat(finance).set_index('unitid')
        if f.index.duplicated().any():raise ValueError('Multiple finance forms in '+str(year))
        for name in ('instruction','research'):p[name+'_log']=np.log1p(f[name]).reindex(p.index)
        p['year']=year;profiles.append(p.reset_index())
        print(f'Prepared annual profile {year}: {p.selectivity.notna().sum()} institutions with selectivity',flush=True)
    p=pd.concat(profiles,ignore_index=True)
    if p.duplicated(['unitid','year']).any():raise ValueError('Duplicate annual profiles')
    out=ROOT/'data/derived/institutional_selectivity';audit=ROOT/'outputs/institutional_selectivity/annual2002_2015'
    out.mkdir(parents=True,exist_ok=True);audit.mkdir(parents=True,exist_ok=True)
    p.to_csv(out/'annual_institution_profile.csv',index=False)
    pd.DataFrame(bridges).to_csv(audit/'test_bridge.csv',index=False)
    pd.DataFrame(scales).to_csv(audit/'annual_scales.csv',index=False)
    meta=pd.read_csv(ROOT/'data/derived/pilot/master_metadata.csv')
    ids=meta.unitid.unique();coverage=[]
    for year,g in p.groupby('year'):
        g=g.set_index('unitid').reindex(ids)
        for name in ('selectivity','sat_selectivity','act_selectivity','rejection_selectivity','instruction_log','research_log','carnegie_classification'):
            coverage.append(dict(year=int(year),measure=name,metadata_institutions=len(ids),
                                 covered=int(g[name].notna().sum())))
    pd.DataFrame(coverage).to_csv(audit/'coverage.csv',index=False)
    design=dict(years=[2002,2015],minimum_test_reporting_percent=20,
        temporal_policy='exact origin year only; no future substitution, carry-forward or retrospective baseline average',
        unsupported_origin_years=[2000,2001],standardization='four-year institutions in each annual directory, before local matching',
        proxy='selectivity, not direct prestige',bridge='within-year institution-level OLS ACT-to-SAT; prefer dominant valid test',
        resources='same-year log1p nominal totals; F1A/F2 only, no per-student claim; F3 research/public-service not conflated',
        classification='exact Carnegie categories recorded in each historical HD file; not ordinal status',
        source=URL,hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in paths})
    (out/'annual_design.json').write_text(json.dumps(design,indent=2)+'\n')
    (audit/'design.json').write_text(json.dumps(design,indent=2)+'\n')
    print(f'Finished: {out}/annual_institution_profile.csv')


if __name__=='__main__':main()
