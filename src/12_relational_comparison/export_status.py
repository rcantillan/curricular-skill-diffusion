"""Audited continuous hiring-rank proxy; field specific, not university-wide."""
from pathlib import Path
import argparse
import json
import hashlib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-tag',default='allskills_b000')
    p.add_argument('--out-tag',default='status2015')
    a=p.parse_args()
    import re
    for tag in [a.source_tag,a.out_tag]:
        if not re.fullmatch('[A-Za-z0-9_-]+',tag):p.error('Invalid tag')
    folder=ROOT/'outputs/content_channels'/a.source_tag
    out=ROOT/'outputs/relational_comparison'/a.out_tag;out.mkdir(parents=True,exist_ok=True)
    frames=[];audit=[]
    for field in ['cs','biz','hist']:
        path=folder/f'match_2015_{field}.csv'
        frame=pd.read_csv(path)
        matched=frame.dropna(subset=['unitid','prestige']).copy()
        if matched.duplicated(['unitid','fos']).any():raise ValueError('Ambiguous institution-field rank')
        matched['unitid']=matched.unitid.astype(int)
        # Rank is oriented so larger status values mean higher position.
        # Scaling uses all published vertices, before local matching.
        sd=frame.prestige.std(ddof=0)
        if not np.isfinite(sd) or sd<=0:raise ValueError('Invalid rank scale')
        matched['status']=(-matched.prestige+frame.prestige.mean())/sd
        matched['available_year']=2013
        matched['outcome_start_year']=2014
        matched['measure']='negative_2015_hiring_rank_standardized_within_network_field'
        matched=matched.rename(columns={'fos':'field','prestige':'raw_hiring_rank','name':'network_name'})
        frames.append(matched[['unitid','field','network_name','raw_hiring_rank','status','available_year','outcome_start_year','measure']])
        audit.append(dict(file=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                          published_vertices=len(frame),matched_vertices=len(matched)))
    pd.concat(frames).to_csv(out/'status_2015_by_field.csv',index=False)
    (out/'status_design.json').write_text(json.dumps(dict(inputs=audit,
        limitations=['Proxy is field-specific, not a university-wide status score.',
                     'Differences in standardized rank are operational proxies, not known cardinal status distances.',
                     'Use only outcomes from 2014 onward; no rank assignment to unmapped fields.',
                     'Faculty hiring connections do not identify curricular transmission.']),indent=2)+'\n')
    print(f'Finished: {out}')


if __name__=='__main__':main()
