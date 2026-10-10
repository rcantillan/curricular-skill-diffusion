"""Compare initial raw and field-residual curricular communities."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]


def describe(folder,label):
    nodes=pd.read_csv(folder/'nodes.csv')
    edges=pd.read_csv(folder/'initial_similarity_edges.csv.gz')
    valid=nodes[nodes.community>=0]
    table=pd.crosstab(valid.fos,valid.community)
    by_id=nodes.set_index('node_id')
    a=by_id.loc[edges.source_node];b=by_id.loc[edges.target_node]
    same_field=a.fos.to_numpy()==b.fos.to_numpy()
    same_inst=a.unitid.to_numpy()==b.unitid.to_numpy()
    report=dict(network=label,nodes=len(nodes),nonisolated_nodes=len(valid),institutions=valid.unitid.nunique(),
                communities=valid.community.nunique(),edges=len(edges),
                field_majority_assignment_accuracy=table.max(axis=1).sum()/len(valid),
                same_field_edge_share=float(np.mean(same_field)),same_institution_edge_share=float(np.mean(same_inst)),
                weighted_same_field_edge_share=float(np.average(same_field,weights=edges.similarity)))
    d=pd.read_csv(folder/'program_year_changes.csv.gz')
    return report,nodes,d


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--raw-tag',default='communities1')
    p.add_argument('--residual-tag',default='communities_residual1')
    p.add_argument('--out-tag',default='comparison1')
    a=p.parse_args()
    import re
    for tag in (a.raw_tag,a.residual_tag,a.out_tag):
        if not re.fullmatch('[A-Za-z0-9_-]+',tag):p.error('Invalid tag')
    folders=[ROOT/'outputs/relational_communities'/a.raw_tag,ROOT/'outputs/relational_communities'/a.residual_tag]
    for folder in folders:
        if not (folder/'complete.json').exists():raise ValueError(f'Incomplete analysis: {folder}')
    mode=json.loads((folders[1]/'design.json').read_text()).get('profile_mode')
    if mode!='field_residual':raise ValueError('Second analysis must use field_residual')
    out=ROOT/'outputs/relational_comparison'/a.out_tag;out.mkdir(parents=True,exist_ok=True)
    reports=[];models=[];changes=[];members=[]
    datasets=[]
    for folder,label in zip(folders,['raw','field_residual']):
        report,nodes,d=describe(folder,label);reports.append(report);datasets.append(d)
        models.append(pd.read_csv(folder/'adjusted_community_tests.csv').assign(network=label))
        changes.append(pd.read_csv(folder/'community_change_summary.csv').assign(network=label))
        members.append(nodes[['unitid','fos','community']].rename(columns={'community':label}))
    # Compare assignments by actual program keys, not arbitrary numeric IDs.
    membership=members[0].merge(members[1],on=['unitid','fos'],validate='one_to_one')
    raw_nodes=pd.read_csv(folders[0]/'nodes.csv')[['node_id','unitid','fos']]
    residual_nodes=pd.read_csv(folders[1]/'nodes.csv')[['node_id','unitid','fos']]
    left=datasets[0].merge(raw_nodes,on=['node_id','unitid'],validate='many_to_one')
    right=datasets[1].merge(residual_nodes,on=['node_id','unitid'],validate='many_to_one')
    paired=left.merge(right,on=['unitid','fos','year','min_syllabi'],suffixes=('_raw','_residual'),validate='one_to_one')
    # Exclusions from the residual graph may change the comparison cohort.
    paired=paired[(paired.community_raw>=0)&(paired.community_residual>=0)]
    comparison=[];rng=np.random.default_rng(20261010)
    for floor,g in paired.groupby('min_syllabi'):
        for metric in ['neighbors_alignment','field_matched_placebo_alignment']:
            delta=g[metric+'_residual']-g[metric+'_raw']
            data=pd.DataFrame({'unitid':g.unitid,'difference':delta}).dropna()
            clustered=data.groupby('unitid').difference.agg(['sum','count'])
            if not len(clustered):continue
            ix=rng.integers(0,len(clustered),size=(1000,len(clustered)))
            draws=clustered['sum'].to_numpy()[ix].sum(axis=1)/clustered['count'].to_numpy()[ix].sum(axis=1)
            comparison.append(dict(min_syllabi=int(floor),metric=metric,mean_difference=delta.mean(),
                                   ci_low=np.quantile(draws,.025),ci_high=np.quantile(draws,.975),
                                   institutions=len(clustered),paired_rows=len(data)))
    pd.DataFrame(reports).to_csv(out/'network_structure_comparison.csv',index=False)
    pd.concat(models).to_csv(out/'adjusted_change_tests.csv',index=False)
    pd.concat(changes).to_csv(out/'community_changes.csv',index=False)
    membership.to_csv(out/'paired_program_membership.csv',index=False)
    pd.DataFrame(comparison).to_csv(out/'paired_alignment_comparison.csv',index=False)
    (out/'complete.json').write_text(json.dumps(dict(raw_tag=a.raw_tag,residual_tag=a.residual_tag,paired_programs=len(membership)))+'\n')
    print(pd.DataFrame(reports).to_string(index=False));print(f'Finished: {out}')


if __name__=='__main__':main()
