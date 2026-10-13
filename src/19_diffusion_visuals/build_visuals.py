"""First sustained appearances and origin-dated potential-source gradients."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','2')
import argparse,csv,gzip,hashlib,json,re,sys,textwrap
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from scipy.stats import t as student_t

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src/17_sustained_incorporation'))
from institutional_exposures import first_origins
EDGES=np.array([-np.inf,-1,-.25,.25,1,np.inf])
LABELS=['Descendente\n>1 DE','Descendente\n0,25–1 DE','Horizontal\n±0,25 DE','Ascendente\n0,25–1 DE','Ascendente\n>1 DE']


def load(parent):
    meta_path=ROOT/'data/derived/pilot/master_metadata.csv'
    meta=pd.read_csv(meta_path).sort_values(['unitid','fos','year']).reset_index(drop=True)
    if meta.duplicated(['unitid','fos','year']).any():raise ValueError('Duplicate profiles')
    meta['cell_id']=pd.factorize(pd.MultiIndex.from_frame(meta[['unitid','fos']]))[0]
    meta['field_id']=pd.Categorical(meta.fos,categories=sorted(meta.fos.unique())).codes
    meta['inst_id']=pd.factorize(meta.unitid)[0]
    scores=np.load(ROOT/'data/derived/pilot/measurement_scores_float64.npy',mmap_mode='r')
    raw=ROOT/'data/raw/detailed_work_activities_scores.gzip'
    stamp=json.loads((ROOT/'data/derived/pilot/measurement_scores_manifest.json').read_text())
    with gzip.open(raw,'rt') as f:skills=next(csv.reader(f))[1:]
    if (scores.shape!=(len(meta),2070) or
        hashlib.sha256(meta.id.to_numpy(dtype=np.int64).tobytes()).hexdigest()!=stamp['ids_sha256'] or
        hashlib.sha256('\n'.join(skills).encode()).hexdigest()!=stamp['skills_sha256'] or
        raw.stat().st_size!=stamp['source_bytes'] or raw.stat().st_mtime_ns!=stamp['source_mtime_ns']):
        raise ValueError('Score cache audit mismatch')
    complete=json.loads((parent/'complete.json').read_text());design=json.loads((parent/'design.json').read_text())
    if complete['activities']!=2070 or complete['smoke'] or complete['folders_with_skipped_models']:
        raise ValueError('Expected completed exhaustive parent analysis')
    if design['origin_rule']!='first_sustained' or design['status_source']!='ipeds':
        raise ValueError('Expected first-sustained IPEDS parent design')
    path=ROOT/'data/derived/institutional_selectivity/annual_institution_profile.csv'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=design['hashes'][str(path.relative_to(ROOT))]:
        raise ValueError('Institutional profiles changed since parent run')
    profile=pd.read_csv(path)
    names=meta.drop_duplicates('inst_id').sort_values('inst_id').unitid.to_numpy()
    status=np.full((14,len(names)),np.nan);valid=np.zeros((14,len(names)),dtype=bool)
    columns=[design['selectivity_measure'],'instruction_log','research_log','carnegie_classification','institution_control']
    for year in range(2002,2016):
        p=profile[profile.year==year].set_index('unitid').reindex(names)
        status[year-2002]=p[columns[0]].to_numpy();valid[year-2002]=p[columns].notna().all(axis=1)
    return meta,scores,status,valid,skills,design


def process(meta,scores,status,valid,thresholds,margin,folder):
    chosen=thresholds.skill_id.to_numpy(dtype=int)
    z=(np.asarray(scores[:,chosen])-thresholds.baseline_mean.to_numpy())/thresholds.baseline_sd.to_numpy()
    cutoff=thresholds.presence_cutoff_z.to_numpy()
    years=meta.year.to_numpy();counts=meta.syllabi_cnt.to_numpy()
    cells=meta.cell_id.to_numpy();inst=meta.inst_id.to_numpy();fields=meta.field_id.to_numpy()
    keys={(r.cell_id,r.year):i for i,r in enumerate(meta.itertuples())}
    origins=first_origins(meta,z,cutoff,margin,keys)
    contributions=[];events=[];supports=[]
    for year in range(2008,2017):
        target=np.flatnonzero((years==year)&(counts>=9))
        ix={y:np.array([keys.get((cells[i],y),-1) for i in target]) for y in [year-2,year-1,year+1]}
        keep=np.ones(len(target),dtype=bool)
        for a in ix.values():keep&=(a>=0)&(counts[np.maximum(a,0)]>=9)
        target=target[keep];old,lag,future=[ix[y][keep] for y in [year-2,year-1,year+1]]
        if not len(target):continue
        # First documented sustained entry, excluding re-entries present in stage 17.
        risk=(z[old]<=cutoff-margin)&(z[lag]<=cutoff-margin)
        risk&=(origins[cells[target]]<0)|(origins[cells[target]]>=year)
        outcome=(z[target]>=cutoff+margin)&(z[future]>=cutoff+margin)
        outcome&=origins[cells[target]]==year
        rr,kk=np.where(risk&outcome)
        events.append(pd.DataFrame(dict(row=target[rr],cell_id=cells[target][rr],unitid=meta.unitid.to_numpy()[target][rr],
            field_id=fields[target][rr],skill_id=chosen[kk],year=year)))
        source=np.flatnonzero((years==year-1)&(counts>=9))
        prev=np.array([keys.get((cells[i],year-2),-1) for i in source]);keep=(prev>=0)&(counts[np.maximum(prev,0)]>=9)
        source,prev=source[keep],prev[keep]
        present=(z[source]>=cutoff+margin)&(z[prev]>=cutoff+margin)
        for k,skill in enumerate(chosen):
            r=np.flatnonzero(risk[:,k]);active=np.flatnonzero(present[:,k])
            if not len(r):continue
            tid=inst[target[r]];tf=fields[target[r]];y=outcome[r,k].astype(float)
            if not len(active):
                supports.append(dict(year=year,skill_id=int(skill),risk=len(r),entries=int(y.sum()),
                    risks_with_matched_sources=0,entries_with_matched_sources=0))
                continue
            s=source[active];sid=inst[s];sf=fields[s];o=origins[cells[s],k]
            if ((o<0)|(o>year-2)).any():raise ValueError('Source has future/unconfirmed origin')
            # Pair comparisons use the emitter's own first origin year for BOTH.
            supported=(o>=2002)&(o<=2015);safe=np.clip(o-2002,0,13)
            sv=status[safe,sid];tv=status[safe[None,:],tid[:,None]]
            matched=supported[None,:]&valid[safe,sid][None,:]&valid[safe[None,:],tid[:,None]]
            matched&=valid[year-1-2002,tid][:,None]
            outside=tid[:,None]!=sid[None,:]
            same=(tf[:,None]==sf[None,:])&outside;other=(tf[:,None]!=sf[None,:])&outside
            gap=tv-sv[None,:]
            any_known=np.zeros(len(r),dtype=bool)
            for channel,pool in [('same_field',same),('other_field',other)]:
                available=pool&matched
                total=pool.sum(1);known=available.sum(1)
                eligible=(known>0)&(known>=.5*total)
                any_known|=eligible
                denominator=np.maximum(known,1)
                for b in range(5):
                    in_bin=(gap>=EDGES[b])&(gap<EDGES[b+1])&available
                    weight=in_bin.sum(1)/denominator
                    weight[~eligible]=0
                    use=weight>0
                    if use.any():
                        d=pd.DataFrame(dict(unitid=meta.unitid.to_numpy()[target[r]][use],field_id=tf[use],year=year,
                            channel=channel,bin=b,opportunities=weight[use],entries=weight[use]*y[use]))
                        contributions.append(d.groupby(['unitid','field_id','year','channel','bin'],as_index=False)[['opportunities','entries']].sum())
            supports.append(dict(year=year,skill_id=int(skill),risk=len(r),entries=int(y.sum()),
                risks_with_matched_sources=int(any_known.sum()),entries_with_matched_sources=int(y[any_known].sum())))
    if contributions:
        d=pd.concat(contributions).groupby(['unitid','field_id','year','channel','bin'],as_index=False)[['opportunities','entries']].sum()
        d.to_csv(folder/'contributions.csv.gz',index=False)
    else:raise ValueError('No comparable source opportunities')
    pd.concat(events).to_csv(folder/'first_entries.csv.gz',index=False)
    pd.DataFrame(supports).to_csv(folder/'support.csv',index=False)
    (folder/'complete.json').write_text('{"complete":true}\n')


def summarize(folders,out):
    cs=[];events=[];supports=[]
    for q,folder in folders:
        for name,collection in [('contributions.csv.gz',cs),('first_entries.csv.gz',events),('support.csv',supports)]:
            d=pd.read_csv(folder/name);d['quantile']=q;collection.append(d)
    c=pd.concat(cs).groupby(['quantile','unitid','field_id','year','channel','bin'],as_index=False)[['opportunities','entries']].sum()
    records=[]
    for (q,channel),group in c.groupby(['quantile','channel']):
        strata=group.groupby(['field_id','year','bin'])[['opportunities','entries']].sum().reset_index()
        tab=strata.pivot(index=['field_id','year'],columns='bin',values='opportunities').fillna(0)
        for b in range(5):
            if b not in tab:tab[b]=0
        # Compare exactly the same field×year strata in all five bins.
        common=tab.index[(tab[list(range(5))]>=10).all(axis=1)]
        selected=strata.set_index(['field_id','year']).loc[common].reset_index()
        total=selected.groupby(['field_id','year']).opportunities.sum();weights=total/total.sum()
        for b in range(5):
            raw=group[group.bin==b];n=raw.opportunities.sum();a=raw.entries.sum()
            if not len(common):continue
            s=selected[selected.bin==b].set_index(['field_id','year'])
            rates=s.entries/s.opportunities;estimate=float((rates*weights).sum())
            gg=raw.set_index(['field_id','year']).loc[common].reset_index()
            gg=gg.merge(pd.DataFrame(dict(stratum_rate=rates,denominator=s.opportunities,stratum_weight=weights)).reset_index(),on=['field_id','year'])
            gg['influence']=gg.stratum_weight*(gg.entries-gg.stratum_rate*gg.opportunities)/gg.denominator
            influence=gg.groupby('unitid').influence.sum();se=float(np.sqrt(np.square(influence).sum()))
            radius=student_t.ppf(.975,max(1,len(influence)-1))*se
            records.append(dict(quantile=q,channel=channel,bin=b,raw_rate=a/n,weighted_opportunities=n,weighted_entries=a,
                standardized_rate=estimate,se=se,ci_low=estimate-radius,ci_high=estimate+radius,
                common_field_year_strata=len(common),standardized_weighted_opportunities=float(s.opportunities.sum()),
                common_strata_fraction=float(total.sum()/group.opportunities.sum()),institutions=len(influence)))
    result=pd.DataFrame(records);result.to_csv(out/'direction_rates.csv',index=False)
    ev=pd.concat(events);assert not ev.duplicated(['quantile','cell_id','skill_id','year']).any()
    support=pd.concat(supports).groupby(['quantile','year'])[['risk','entries','risks_with_matched_sources','entries_with_matched_sources']].sum().reset_index()
    support.to_csv(out/'coverage.csv',index=False)
    ev.groupby(['quantile','skill_id']).size().rename('first_entries').reset_index().to_csv(out/'skill_entry_counts.csv',index=False)
    return result,ev


def rate_plot(d,out):
    fig,axes=plt.subplots(2,2,figsize=(12,8),sharex=True)
    for row,q in enumerate([.75,.9]):
        for col,channel in enumerate(['same_field','other_field']):
            ax=axes[row,col];g=d[(d['quantile']==q)&(d.channel==channel)].sort_values('bin')
            ax.errorbar(g.bin,g.standardized_rate*100,yerr=1.96*g.se*100,fmt='o-',color='#225e91',capsize=4,lw=1.7)
            ax.scatter(g.bin,g.raw_rate*100,color='#b3b3b3',s=22,label='Tasa sin estandarizar')
            ax.set_title(('Misma disciplina' if col==0 else 'Disciplinas distintas')+f' · umbral P{int(q*100)}',fontsize=11)
            ax.set_xticks(range(5),LABELS,fontsize=8);ax.grid(axis='y',alpha=.2)
            ax.set_ylabel('Incorporación sostenida (%)')
            ax.spines[['top','right']].set_visible(False)
    fig.suptitle('¿En qué dirección aparecen las habilidades?\nExposiciones potenciales; no transmisiones identificadas',fontsize=15)
    fig.text(.5,.025,'Azul: mismas disciplinas×años, con igual composición entre direcciones. Barras: incertidumbre agrupada por universidad.\nCada oportunidad receptora distribuye peso 1 entre sus emisores comparables, por canal. No es un efecto causal ajustado.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.08,1,.92])
    for extension in ['png','pdf','svg']:fig.savefig(out/f'direction_rates.{extension}',dpi=180)
    plt.close(fig)


def examples(meta,scores,status,valid,events,parent,skills,margin,out,n):
    # Choose rich examples by first-entry count only, NEVER by gradient/sign.
    rank=events[events['quantile']==.75].groupby('skill_id').size().sort_values(ascending=False)
    keys={(r.cell_id,r.year):i for i,r in enumerate(meta.itertuples())}
    cells=meta.cell_id.to_numpy();inst=meta.inst_id.to_numpy();counts=meta.syllabi_cnt.to_numpy()
    catalog={}
    for q in [.75,.9]:
        allcuts=pd.concat([pd.read_csv(f) for f in sorted(parent.glob(f'q{int(q*100)}_block_*/thresholds.csv'))]).set_index('skill_id')
        made=0
        for skill in rank.index:
            if made>=n:break
            e=events[(events['quantile']==q)&(events.skill_id==skill)].copy()
            if len(e)<10:continue
            cut=allcuts.loc[skill];z=((np.asarray(scores[:,[skill]])-cut.baseline_mean)/cut.baseline_sd)
            origin=first_origins(meta,z,np.array([cut.presence_cutoff_z]),margin,keys)[:,0]
            candidates=[]
            for cell,a in enumerate(origin):
                if a<2002 or a>2014:continue
                source=keys[(cell,int(a))];sid=inst[source]
                if not valid[a-2002,sid]:continue
                receivers=[]
                for r in e.itertuples():
                    if r.unitid==meta.unitid.iloc[source] or r.year<int(a)+2:continue
                    p0=keys.get((cell,r.year-2),-1);p1=keys.get((cell,r.year-1),-1)
                    if p0<0 or p1<0 or counts[p0]<9 or counts[p1]<9:continue
                    if z[p0,0]<cut.presence_cutoff_z+margin or z[p1,0]<cut.presence_cutoff_z+margin:continue
                    if not valid[a-2002,inst[r.row]]:continue
                    receivers.append(r)
                if receivers:candidates.append((len(receivers),int(a),cell,source,receivers))
            if not candidates:continue
            # Most observable downstream opportunities, then earliest origin,
            # then program ID; no use of selectivity magnitude or direction.
            candidates.sort(key=lambda v:(-v[0],v[1],v[2]));_,a,cell,s,rs=candidates[0]
            nodes=[]
            for r in rs:
                record=meta.iloc[r.row]
                nodes.append(dict(year=int(r.year),status=float(status[a-2002,inst[r.row]]),institution=str(record.institution_name),
                    field=str(record.fos),unitid=int(r.unitid),same_field=bool(record.fos==meta.fos.iloc[s])))
            source=meta.iloc[s]
            catalog[f'{q}:{skill}']=dict(quantile=q,skill_id=int(skill),skill=skills[skill],anchor_year=a,
                source=dict(year=a,status=float(status[a-2002,inst[s]]),institution=str(source.institution_name),field=str(source.fos),unitid=int(source.unitid)),
                receivers=nodes,total_first_entries=len(e),other_documented_prior_sources=int(((origin>=0)&(origin<a)).sum()),
                selection='Most first entries, then focal emitter with most dated observable receiver opportunities; no direction criterion')
            made+=1
    (out/'examples.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n')
    selected=[v for v in catalog.values() if v['quantile']==.75]
    if not selected:raise ValueError('No displayable examples')
    fig,axes=plt.subplots(3,2,figsize=(13,12),squeeze=False)
    for ax,c in zip(axes.ravel(),selected[:6]):
        s=c['source'];r=c['receivers']
        for same,color,label in [(True,'#2476ad','Misma disciplina'),(False,'#df853c','Otra disciplina')]:
            g=[x for x in r if x['same_field']==same]
            ax.scatter([x['year'] for x in g],[x['status'] for x in g],s=23,alpha=.65,color=color,label=label)
        ax.scatter(s['year'],s['status'],s=100,marker='D',color='#222222',label='Emisor focal')
        ax.axhline(s['status'],color='#777777',ls='--',lw=.8)
        ax.set_title(textwrap.fill(c['skill'],52),fontsize=10)
        ax.set_xlabel('Año de primera entrada sostenida');ax.set_ylabel(f'Selectividad fijada en {c["anchor_year"]}')
        ax.grid(alpha=.15);ax.spines[['top','right']].set_visible(False)
        below=sum(x['status']<s['status']-.25 for x in r);above=sum(x['status']>s['status']+.25 for x in r)
        ax.text(.02,.02,f'{len(r)} receptores potenciales: {below} debajo, {above} encima\n{c["other_documented_prior_sources"]} programas ya presentes antes del emisor focal',transform=ax.transAxes,fontsize=8)
    for ax in axes.ravel()[len(selected[:6]):]:ax.set_visible(False)
    axes[0,0].legend(fontsize=8,loc='best')
    fig.suptitle('Secuencias de aparición con un emisor focal\nEjemplos elegidos por cobertura, sin seleccionar patrones top-down',fontsize=15)
    fig.text(.5,.02,'Cada panel congela TODAS las posiciones en el primer año sostenido del emisor focal. Los puntos son entradas posteriores.\nLa coexistencia temporal no demuestra transmisión; el emisor focal no es necesariamente el origen de la habilidad.',ha='center',fontsize=9)
    fig.tight_layout(rect=[0,.065,1,.93])
    for extension in ['png','pdf','svg']:fig.savefig(out/f'appearance_sequences.{extension}',dpi=170)
    plt.close(fig)
    return catalog


def html(catalog,out):
    payload=json.dumps(catalog,ensure_ascii=False).replace('</','<\\/')
    template='''<!doctype html><html lang="es"><meta charset="utf-8"><title>Aparición sostenida de habilidades</title>
<style>body{font:16px system-ui;background:#f4f6f8;color:#223041;margin:30px auto;max-width:1120px;padding:0 20px}main{background:white;padding:24px;border-radius:12px}select{max-width:700px;padding:8px;margin:8px}svg{width:100%;height:auto}p{line-height:1.5}.note{color:#536474;font-size:14px}</style>
<main><h1>Secuencias de aparición sostenida</h1><p>Selecciona una habilidad. La posición de cada universidad queda fijada en el primer año sostenido del emisor focal.</p>
<select id="selection"></select><select id="field"></select><label><input type="checkbox" id="links"> Mostrar conexiones temporales posibles</label>
<svg id="chart" viewBox="0 0 1000 550"></svg><p id="info"></p>
<p class="note">Las líneas posibles no identifican transmisiones. Se incluyen únicamente receptores con entrada sostenida posterior y un emisor focal que conservaba presencia alta antes de esa entrada. Otros programas pueden haber sido emisores. Pasa el cursor sobre los puntos para ver institución, disciplina y año.</p>
<h2>Dirección y oportunidades de incorporación</h2><img src="direction_rates.png" style="width:100%"><p class="note">Las tasas distribuyen cada oportunidad receptora entre emisores comparables; se estandarizan por disciplina y año. No sustituyen los modelos ajustados ni son probabilidades de transmisión de una díada.</p></main>
<script>const data=__DATA__;const sel=document.getElementById('selection'),field=document.getElementById('field'),chart=document.getElementById('chart');
Object.entries(data).forEach(([key,v])=>{let o=document.createElement('option');o.value=key;o.textContent='P'+Math.round(v.quantile*100)+' · '+v.skill;sel.append(o)});
function node(tag,attrs={},txt){let n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(txt!==undefined)n.textContent=txt;chart.append(n);return n}
function render(reset){let c=data[sel.value];if(reset){field.replaceChildren();['Todas las disciplinas',...new Set(c.receivers.map(x=>x.field).sort())].forEach(f=>{let o=document.createElement('option');o.value=f;o.textContent=f;field.append(o)})}
let rs=c.receivers.filter(r=>field.value==='Todas las disciplinas'||r.field===field.value),s=c.source;chart.replaceChildren();let ys=[s.status,...rs.map(r=>r.status)],ymin=Math.min(...ys)-.3,ymax=Math.max(...ys)+.3;
const X=y=>80+840*(y-c.anchor_year)/(2017-c.anchor_year),Y=v=>465-385*(v-ymin)/(ymax-ymin);
for(let y=c.anchor_year;y<=2017;y++){node('line',{x1:X(y),x2:X(y),y1:70,y2:465,stroke:'#e4e8ec'});node('text',{x:X(y),y:490,'text-anchor':'middle','font-size':12},y)}
for(let v=Math.ceil(ymin);v<ymax;v++){node('line',{x1:80,x2:920,y1:Y(v),y2:Y(v),stroke:'#e4e8ec'});node('text',{x:65,y:Y(v)+4,'text-anchor':'end','font-size':12},v)}
node('line',{x1:80,x2:920,y1:Y(s.status),y2:Y(s.status),stroke:'#6c7885','stroke-dasharray':'5 5'});
if(document.getElementById('links').checked)rs.forEach(r=>node('line',{x1:X(s.year),y1:Y(s.status),x2:X(r.year),y2:Y(r.status),stroke:'#a3adb7','stroke-opacity':.3,'stroke-dasharray':'3 4'}));
rs.forEach(r=>{let n=node('circle',{cx:X(r.year),cy:Y(r.status),r:5,fill:r.same_field?'#2476ad':'#df853c',opacity:.7});let t=document.createElementNS(n.namespaceURI,'title');t.textContent=r.institution+' · '+r.field+' · '+r.year+' · selectividad '+r.status.toFixed(2)+' en '+c.anchor_year;n.append(t)});
let n=node('rect',{x:X(s.year)-6,y:Y(s.status)-6,width:12,height:12,fill:'#222'}),t=document.createElementNS(n.namespaceURI,'title');t.textContent='Emisor focal: '+s.institution+' · '+s.field+' · '+s.year;n.append(t);
node('text',{x:80,y:28,'font-size':16},c.skill);node('text',{x:80,y:50,'font-size':12},'Selectividad de todas las instituciones fijada en '+c.anchor_year+' · azul: misma disciplina; naranja: otra disciplina');
let below=rs.filter(r=>r.status<s.status-.25).length,above=rs.filter(r=>r.status>s.status+.25).length;
document.getElementById('info').textContent='Emisor focal: '+s.institution+' ('+s.field+'). '+rs.length+' entradas posteriores compatibles: '+below+' debajo y '+above+' encima. '+c.other_documented_prior_sources+' programas ya tenían presencia sostenida documentada antes del emisor focal.';}
sel.onchange=()=>render(true);field.onchange=()=>render(false);document.getElementById('links').onchange=()=>render(false);render(true);</script></html>'''
    (out/'appearance_explorer.html').write_text(template.replace('__DATA__',payload))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tag',default='cascades1')
    parser.add_argument('--parent',default='incorporation_ipeds_origin1');parser.add_argument('--examples',type=int,default=6)
    args=parser.parse_args()
    if not all(re.fullmatch('[A-Za-z0-9_-]+',x) for x in [args.tag,args.parent]):parser.error('Invalid tag')
    parent=ROOT/'outputs/sustained_incorporation'/args.parent
    meta,scores,status,valid,skills,design=load(parent)
    out=ROOT/'outputs/diffusion_visuals'/args.tag;cache=ROOT/'data/derived/diffusion_visuals'/args.tag
    out.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
    config=dict(parent=args.parent,activities=2070,quantiles=[.75,.9],origin='first documented sustained presence in emitter',
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),parent_design_sha256=hashlib.sha256((parent/'design.json').read_bytes()).hexdigest(),
        examples=args.examples,bins=[-1,-.25,.25,1],first_entries_only=True,causal_transmissions=False,
        rate='Each receiver outcome split equally among origin-comparable active sources within each external channel',
        standardization='common field×year strata with ≥10 weighted opportunities in each of five bins; university-clustered uncertainty')
    if (out/'design.json').exists() and json.loads((out/'design.json').read_text())!=config:raise ValueError('Changed design/code: use a new tag')
    (out/'design.json').write_text(json.dumps(config,indent=2)+'\n')
    folders=[]
    for q in [.75,.9]:
        files=sorted(parent.glob(f'q{int(q*100)}_block_*/thresholds.csv'))
        ids=np.concatenate([pd.read_csv(f).skill_id.to_numpy() for f in files])
        if sorted(ids.tolist())!=list(range(2070)):raise ValueError('Incomplete skill coverage')
        for i,f in enumerate(files):
            folder=cache/f'q{int(q*100)}_block_{i:03d}';folder.mkdir(exist_ok=True);folders.append((q,folder))
            if (folder/'complete.json').exists():continue
            print(f'P{int(q*100)} block {i+1}/{len(files)}: first entries and origin-dated opportunities',flush=True)
            process(meta,scores,status,valid,pd.read_csv(f),design['margin_sd'],folder)
    rates,events=summarize(folders,out);rate_plot(rates,out)
    catalog=examples(meta,scores,status,valid,events,parent,skills,design['margin_sd'],out,args.examples);html(catalog,out)
    (out/'complete.json').write_text(json.dumps(dict(activities=2070,blocks_per_threshold=65,examples=len(catalog),complete=True))+'\n')
    print(f'Finished: {out}',flush=True)


if __name__=='__main__':main()
