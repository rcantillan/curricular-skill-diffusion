"""Origin-dated institutional contrasts; receiver and emitter use the SAME year."""
import numpy as np
import pandas as pd


def first_origins(meta,z,cutoff,margin,keys):
    """First DOCUMENTED pair of high years; not a claim of true first adoption."""
    origins=np.full((meta.cell_id.max()+1,z.shape[1]),-1,dtype=np.int16)
    counts=meta.syllabi_cnt.to_numpy();years=meta.year.to_numpy();cells=meta.cell_id.to_numpy()
    for year in range(int(years.min()),int(years.max())):
        ix=np.flatnonzero((years==year)&(counts>=9))
        follow=np.array([keys.get((cells[i],year+1),-1) for i in ix],dtype=int)
        good=(follow>=0)&(counts[np.maximum(follow,0)]>=9)
        ix,follow=ix[good],follow[good]
        if not len(ix):continue
        high=(z[ix]>=cutoff+margin)&(z[follow]>=cutoff+margin)
        available=origins[cells[ix]]<0
        rr,kk=np.where(high&available)
        origins[cells[ix[rr]],kk]=year
    return origins


def moments(source_value,weights,target_value):
    """Cumulative sums avoid allocating all receiver×source×activity dyads."""
    m=weights.shape[1];n=len(target_value)
    if not len(source_value):return np.zeros((n,m)),np.zeros((n,m))
    order=np.argsort(source_value);v=source_value[order];w=weights[order]
    count=np.vstack([np.zeros((1,m)),np.cumsum(w,axis=0)])
    total=np.vstack([np.zeros((1,m)),np.cumsum(w*v[:,None],axis=0)])
    at=np.searchsorted(v,target_value,side='right')
    below=target_value[:,None]*count[at]-total[at]
    above=total[-1]-total[at]-target_value[:,None]*(count[-1]-count[at])
    return np.maximum(above,0),np.maximum(below,0)


def exposures(meta,target,source,present,origins,profiles,measure,rule,year,n_same,n_other):
    """All denominators remain the covered source pool, not just ranked emitters.

    Matching shares among active holders are exported separately. Full common
    matching requires selectivity, two resource measures, Carnegie and control
    for both institutions at each origin year. This permits nested models on
    the same set of usable relational information.
    """
    ns,m=present.shape;nt=len(target)
    si=meta.unitid.to_numpy()[source];sf=meta.field_id.to_numpy(dtype=np.int64)[source]
    ti=meta.unitid.to_numpy()[target];tf=meta.field_id.to_numpy(dtype=np.int64)[target]
    ic,ilabels=pd.factorize(si);target_ic=pd.Index(ilabels).get_indexer(ti)
    source_positions=pd.Index(meta.cell_id.to_numpy()[source]).get_indexer(meta.cell_id.to_numpy()[target])
    if (source_positions<0).any():raise ValueError('Receiver missing from source population')
    nf=meta.field_id.nunique()
    def aggregate(values,codes,size):
        a=np.zeros((size,m));np.add.at(a,codes,values);return a
    def pools(values):
        own=values[source_positions]
        field=aggregate(values,sf,nf)[tf]
        institution=aggregate(values,ic,len(ilabels))[target_ic]
        return dict(same=field-own,other=values.sum(0)-institution-field+own)
    def matching_category(weights,source_category,target_category):
        # Compress observed joint groups; avoid receiver×source comparisons.
        category,labels=pd.factorize(source_category)
        target_category=pd.Index(labels).get_indexer(target_category)
        width=len(labels)+1;category=category+1;target_category=target_category+1
        def lookup(a,b):
            source_joint=a*width+category;target_joint=b*width+target_category
            codes,groups=pd.factorize(source_joint);pos=pd.Index(groups).get_indexer(target_joint)
            totals=aggregate(weights,codes,len(groups));v=np.zeros((nt,m))
            valid=pos>=0;v[valid]=totals[pos[valid]];return v
        field=lookup(sf,tf);institution=lookup(ic,target_ic)
        total=lookup(np.zeros(ns,dtype=int),np.zeros(nt,dtype=int))
        own=weights[source_positions]*(category[source_positions]==target_category)[:,None]
        return dict(same=field-own,other=total-institution-field+own)
    cols=['sel_above','sel_below','matched','instruction_gap','research_gap','same_type','same_control','age']
    results={c+'_'+p:np.zeros((nt,m)) for c in cols for p in ['same','other']}
    if rule=='lag':origin=np.full((ns,m),year-1,dtype=int)
    else:
        origin=origins[meta.cell_id.to_numpy()[source]]
        if ((origin<0)&(present>0)).any() or ((origin>year-2)&(present>0)).any():
            raise ValueError('Source origin is not observable before receiver entry')
    needed=[measure,'instruction_log','research_log','carnegie_classification','institution_control']
    for o in np.unique(origin[present>0]):
        p=profiles[profiles.year==o].set_index('unitid')
        if p.empty:continue # Unsupported early years are missing, never backfilled.
        s=p.reindex(si);t=p.reindex(ti)
        sv=s[needed].notna().all(axis=1).to_numpy();tv=t[needed].notna().all(axis=1).to_numpy()
        if not sv.any() or not tv.any():continue
        w=present*(origin==o)*sv[:,None]
        svalue=s[measure].to_numpy(dtype=float);tvalue=t[measure].fillna(0).to_numpy(dtype=float)
        all_up,all_down=moments(svalue[sv],w[sv],tvalue)
        # Aggregate known origins and characteristics in the same three pools.
        arrays=dict(matched=w, instruction_gap=w*s.instruction_log.fillna(0).to_numpy()[:,None],
            research_gap=w*s.research_log.fillna(0).to_numpy()[:,None],age=w*(year-int(o)))
        for f in np.unique(tf):
            r=np.flatnonzero(tf==f);same=sf==f
            up,down=moments(svalue[sv&same],w[sv&same],tvalue[r])
            results['sel_above_same'][r]+=up*tv[r,None]
            results['sel_below_same'][r]+=down*tv[r,None]
            # Within-institution gaps are exactly zero. Subtracting the field
            # from all sources therefore excludes the receiver's institution
            # automatically for directional selectivity moments.
            results['sel_above_other'][r]+=(all_up[r]-up)*tv[r,None]
            results['sel_below_other'][r]+=(all_down[r]-down)*tv[r,None]
        counts=pools(w)
        for c in ['matched','age']:
            v=pools(arrays[c])
            for pool in ['same','other']:results[c+'_'+pool]+=v[pool]*tv[:,None]
        for c in ['instruction','research']:
            v=pools(arrays[c+'_gap']);value=t[c+'_log'].fillna(0).to_numpy()
            for pool in ['same','other']:
                results[c+'_gap_'+pool]+=(v[pool]-value[:,None]*counts[pool])*tv[:,None]
        for c,column in [('same_type','carnegie_classification'),('same_control','institution_control')]:
            v=matching_category(w,s[column].to_numpy(),t[column].to_numpy())
            for pool in ['same','other']:results[c+'_'+pool]+=v[pool]*tv[:,None]
    for key in results:
        n=n_same if key.endswith('_same') else n_other
        results[key]=np.divide(results[key],n[:,None],out=np.full((nt,m),np.nan),where=n[:,None]>0)
    # No holder is not the same as a holder with missing selectivity. Include
    # no-holder opportunities as valid zero exposure when target data exist.
    reference=profiles[profiles.year==year-1].set_index('unitid').reindex(ti)
    target_supported=reference[needed].notna().all(axis=1).to_numpy()
    for key in results:results[key][~target_supported]=np.nan
    return results
