"""Pre-specified exploratory validation of two cross-scale process questions.

Only aggregate data are exported. Manuscript and canonical data are unchanged.
"""
from pathlib import Path
import os, sys, json, time, hashlib
for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[key] = '2'
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tmp/nhb_fig2_python_deps'), str(ROOT/'outputs/country_typology_validation_20261029/python_deps')]
import numpy as np
import pandas as pd
import duckdb
from scipy.optimize import minimize
from scipy.special import logsumexp
from scipy.stats import binomtest
CLEAN = ROOT/'data/processed/mobility_city_harmonized_20261020'
OUT = ROOT/'outputs/cross_scale_mechanism_validation_20261030'
OUT.mkdir(parents=True, exist_ok=True)
SEED = 20261030

def log(s): print(time.strftime('%H:%M:%S'), s, flush=True)
def q(p): return "'"+str(p).replace("'", "''")+"'"
def js(name, x): (OUT/name).write_text(json.dumps(x, ensure_ascii=False, indent=2), encoding='utf8')
def readpq(path):
    c=duckdb.connect(); r=c.sql(f'SELECT * FROM read_parquet({q(path)})').df();c.close();return r
def connect():
    c = duckdb.connect()
    c.execute("SET threads=3; SET memory_limit='3GB'; SET preserve_insertion_order=false")
    c.execute(f'SET temp_directory={q(OUT/"duckdb_temp")}')
    return c
def export(c, sql, name):
    c.execute(f'COPY ({sql}) TO {q(OUT/name)} (FORMAT PARQUET,COMPRESSION ZSTD)')

def plan():
    if (OUT/'analysis_plan.json').exists(): return
    js('analysis_plan.json', dict(date='2026-10-30', status='exploratory; recorded before new model results', seed=SEED,
      section4_question='Does lagged domestic city partner count add to research size, physical distance and prior international inflows when explaining international arrival-city allocation?',
      section4_primary='Conditional gravity: foreign source city x destination country x period margins held fixed. All eligible destination cities with positive lagged observable author mass and confirmed coordinates. Top 100 foreign source cities per country selected only using 1998-2013 international events. Actual source-city distances. Predictors lagged one four-year period.',
      periods=['1998-2001','2002-2005','2006-2009','2010-2013','2014-2017','2018-2021','2022-2025'],
      train=[1,2,3], validation=[4], test=[5,6],
      section4_models=['mass+distance','mass+distance+domestic_degree','mass+distance+prior_international_inflow','mass+distance+prior_international_inflow+domestic_degree'],
      section4_sensitivity=['city fixed effects if estimation feasible','degree shuffled within country-period lag-mass deciles on held-out predictions'],
      section4_decision='Require held-out improvement beyond both mass-distance and prior-international-history baselines; assess countries equally as well as events. Positive coefficients alone are insufficient. This is conditional allocation, not effect on total national inflows.',
      section5_question='How much does first domestic continuation after observed international entry redistribute the same cohort, and how much does its conditional allocation change the full domestic distribution?',
      section5_primary='Reproduce existing matched HHI; replace only target destination margins in the same verified microdata subset and same 2012-2023 calendar window by finite-sample conditional expected margins; retain origins and totals. Report contribution fraction before interpreting aggregate consequence.',
      section5_endpoints=['same-cohort entry-to-next HHI','conditional-reference HHI excess','full-domestic Gini and HHI changes after replacing target destination margins'],
      limits=['Individual subset is not fully reconciled to canonical data; raw difference previously 314.','Publication observation is not residential retention.','Reference scenarios are descriptive/model-based, not causal interventions.','Keep degree, history and aggregate concentration failures visible; do not search for new endpoints after seeing results.'],
      manuscript_modified=False))

def prepare():
    plan()
    c=connect()
    if not (OUT/'city_author_year_mass.parquet').exists():
        log('Aggregate deduplicated observable authors by confirmed city-year')
        c.execute(f"CREATE TABLE cw AS SELECT * FROM read_csv({q(CLEAN/'city_crosswalk.csv')},header=true,all_varchar=true)")
        c.execute("""CREATE TABLE gm AS SELECT raw_country original_country,try_cast(source_geonameid AS BIGINT) gid,
        min(city_id) city,min(country_code) country FROM cw WHERE analysis_ready='True'
        AND try_cast(source_geonameid AS BIGINT) IS NOT NULL AND raw_country IS NOT NULL
        GROUP BY 1,2 HAVING count(DISTINCT city_id)=1 AND count(DISTINCT country_code)=1""")
        source=ROOT/'data/input/mobility/openalex_mobility_rates/author_year_primary_location.parquet'
        export(c,f"""SELECT p.year,g.country,g.city,count(DISTINCT p.author_id)::BIGINT mass
          FROM read_parquet({q(source)}) p JOIN gm g ON p.country_code=g.original_country
          AND try_cast(regexp_extract(p.city_key,'^gn:([0-9]+)$',1) AS BIGINT)=g.gid
          WHERE p.year BETWEEN 1998 AND 2025 GROUP BY 1,2,3""",'city_author_year_mass.parquet')
        log('Observable author aggregation complete')
    if not (OUT/'raw_author_year_coverage.csv').exists():
        source=ROOT/'data/input/mobility/openalex_mobility_rates/author_year_primary_location.parquet'
        c.sql(f"SELECT year,count(*) primary_rows FROM read_parquet({q(source)}) WHERE year BETWEEN 1998 AND 2025 GROUP BY 1 ORDER BY 1").df().to_csv(OUT/'raw_author_year_coverage.csv',index=False)
    if not (OUT/'international_city_od_period.parquet').exists():
        c.execute(f"CREATE VIEW f AS SELECT *,floor((year-1998)/4)::INT p FROM read_parquet({q(CLEAN/'count_mobility_flow_annual_clean.parquet')}) WHERE tier='top100pct' AND year BETWEEN 1998 AND 2025 AND geography IN ('international','domestic_intercity')")
        c.sql('SELECT geography,sum(mobility_count) events FROM f GROUP BY 1').df().to_csv(OUT/'canonical_accounting.csv',index=False)
        export(c,"SELECT p,from_country_code oc,to_country_code country,from_city_id o,to_city_id d,sum(mobility_count)::DOUBLE flow FROM f WHERE geography='international' GROUP BY ALL",'international_city_od_period.parquet')
        export(c,"WITH links AS(SELECT DISTINCT p,from_country_code country,from_city_id city,to_city_id partner FROM f WHERE geography='domestic_intercity' UNION SELECT DISTINCT p,to_country_code country,to_city_id city,from_city_id partner FROM f WHERE geography='domestic_intercity') SELECT p,country,city,count(*) domestic_degree FROM links GROUP BY ALL",'domestic_city_degree.parquet')
        export(c,"SELECT p,to_country_code country,to_city_id city,sum(mobility_count) international_inflow FROM f WHERE geography='international' GROUP BY ALL",'international_city_inflow.parquet')
    c.close()
    mass=readpq(OUT/'city_author_year_mass.parquet')
    coverage=mass.groupby('year').mass.sum().rename('mapped_author_years').reset_index().merge(pd.read_csv(OUT/'raw_author_year_coverage.csv'),on='year')
    coverage['mapped_fraction_of_primary_rows']=coverage.mapped_author_years/coverage.primary_rows
    coverage.to_csv(OUT/'author_mass_mapping_coverage.csv',index=False)
    log('Prepared gravity inputs')

def distances(la1,lo1,la2,lo2):
    a=np.radians(la1)[:,None];b=np.radians(la2)[None,:]
    v=np.sin((a-b)/2)**2+np.cos(a)*np.cos(b)*np.sin((np.radians(lo1)[:,None]-np.radians(lo2)[None,:])/2)**2
    return np.maximum(6371.0088*2*np.arcsin(np.sqrt(np.clip(v,0,1))),1)

def build_design():
    cache=OUT/'gravity_design.npz'
    if cache.exists(): return dict(np.load(cache,allow_pickle=False))
    mass=readpq(OUT/'city_author_year_mass.parquet');mass['p']=((mass.year-1998)//4).astype(int)
    m=mass.groupby(['p','country','city']).mass.sum().div(4).rename('mass').reset_index()
    od=readpq(OUT/'international_city_od_period.parquet')
    deg=readpq(OUT/'domestic_city_degree.parquet');hist=readpq(OUT/'international_city_inflow.parquet')
    coords=pd.read_csv(CLEAN/'cities.csv').drop_duplicates('city_id').set_index('city_id')
    coords=coords[np.isfinite(coords.latitude)&np.isfinite(coords.longitude)]
    sample=pd.read_csv(ROOT/'figures/v3/source_data/Fig4_country_concentration_trends.csv').country.tolist()
    top=od[(od.p<=3)&od.country.isin(sample)&od.o.isin(coords.index)].groupby(['country','o']).flow.sum().reset_index().sort_values(['country','flow'],ascending=[True,False]).groupby('country').head(100)
    top.to_csv(OUT/'training_selected_foreign_origins.csv',index=False)
    xx=[]; yy=[]; pp=[]; cc=[];gg=[];city=[]; audits=[];gid=0
    log('Build exact conditional foreign-city destination-choice risk sets')
    for country in sample:
        origins=top[top.country==country].o.to_numpy(); oc=coords.loc[origins]
        for p in range(1,7):
            s=m[(m.country==country)&(m.p==p-1)&m.city.isin(coords.index)].copy()
            s=s.merge(deg[deg.p==p-1][['country','city','domestic_degree']],on=['country','city'],how='left').merge(hist[hist.p==p-1][['country','city','international_inflow']],on=['country','city'],how='left').fillna(0).sort_values('city')
            if len(s)<2:continue
            dnames=s.city.to_numpy(); dc=coords.loc[dnames]; dstidx={v:i for i,v in enumerate(dnames)};oidx={v:i for i,v in enumerate(origins)}
            obs=od[(od.country==country)&(od.p==p)];a=obs[obs.o.isin(oidx)&obs.d.isin(dstidx)]
            y=np.zeros((len(origins),len(s)))
            if len(a):y[[oidx[z] for z in a.o],[dstidx[z] for z in a.d]]=a.flow
            keep=y.sum(1)>0;y=y[keep];oo=oc.iloc[np.flatnonzero(keep)]
            if not len(y):continue
            dist=distances(oo.latitude.to_numpy(),oo.longitude.to_numpy(),dc.latitude.to_numpy(),dc.longitude.to_numpy())
            shape=y.shape
            x=np.column_stack([np.broadcast_to(np.log(s.mass.to_numpy()),shape).ravel(),np.log(dist).ravel(),np.broadcast_to(np.log1p(s.domestic_degree.to_numpy()),shape).ravel(),np.broadcast_to(np.log1p(s.international_inflow.to_numpy()),shape).ravel()])
            ids=np.repeat(np.arange(gid,gid+len(y)),len(s));gid+=len(y)
            xx.append(x.astype('float32')); yy.append(y.ravel().astype('float32'));pp.append(np.full(y.size,p,dtype='int8'));cc.append(np.full(y.size,sample.index(country),dtype='int16'));gg.append(ids.astype('int32'));city.append(np.tile(dnames,len(y)))
            audits.append(dict(country=country,period=p,source_cities=len(y),destination_cities=len(s),risk_pairs=y.size,retained_events=float(y.sum()),all_country_events=float(obs.flow.sum()),flow_coverage=float(y.sum()/obs.flow.sum())))
    codes=np.unique(np.concatenate(city));lookup={v:i for i,v in enumerate(codes)}
    data=dict(x=np.vstack(xx),y=np.concatenate(yy),p=np.concatenate(pp),country=np.concatenate(cc),group=np.concatenate(gg),city=np.array([lookup[v] for v in np.concatenate(city)],dtype='int32'),city_codes=codes.astype('U'),country_codes=np.array(sample,dtype='U'))
    np.savez_compressed(cache,**data);pd.DataFrame(audits).to_csv(OUT/'gravity_risk_set_coverage.csv',index=False)
    log(f'Choice design: {len(data["y"]):,} pairs, {len(codes)} cities')
    return data

def probabilities(eta,g):
    starts=np.r_[0,np.flatnonzero(np.diff(g))+1]; sizes=np.diff(np.r_[starts,len(g)])
    shift=np.maximum.reduceat(eta,starts);ex=np.exp(eta-np.repeat(shift,sizes));sums=np.add.reduceat(ex,starts)
    return ex/np.repeat(sums,sizes),starts,sizes,shift+np.log(sums)

def fit_choice(d,cols,fe=False):
    train=d['p']<=3;x=d['x'][train][:,cols].astype(float);y=d['y'][train].astype(float);g=d['group'][train];city=d['city'][train]
    mean=x.mean(0);scale=x.std(0);z=(x-mean)/scale;ncity=len(d['city_codes'])
    starts=np.r_[0,np.flatnonzero(np.diff(g))+1];sizes=np.diff(np.r_[starts,len(g)]);tot=np.add.reduceat(y,starts);tt=np.repeat(tot,sizes);norm=y.sum()
    def fun(b):
        eta=z@b[:len(cols)]
        if fe:eta+=b[len(cols):][city]
        pr,_,_,lse=probabilities(eta,g);err=tt*pr-y
        val=(np.dot(tot,lse)-np.dot(y,eta))/norm
        grad=z.T@err/norm
        if fe:
            # Fixed, weak shrinkage prevents diverging city effects at cities with no training arrivals.
            # Sensitivity only; penalty was chosen for numerical existence, not held-out performance.
            val+=5*np.dot(b[len(cols):],b[len(cols):])/norm
            grad=np.r_[grad,(np.bincount(city,weights=err,minlength=ncity)+10*b[len(cols):])/norm]
        return val,grad
    b=np.zeros(len(cols)+(ncity if fe else 0));res=minimize(fun,b,jac=True,method='L-BFGS-B',options=dict(maxiter=1600 if fe else 180,gtol=1e-7,ftol=1e-11,maxcor=16))
    log(f'Fitted cols={cols} FE={fe}: {res.message}, iterations={res.nit}')
    return dict(cols=cols,fe=fe,b=res.x,mean=mean,scale=scale,loss=float(res.fun),success=bool(res.success),gradient=float(np.max(np.abs(res.jac))),iterations=int(res.nit),city_effect_penalty=10 if fe else 0)

def predict(d,fit,mask,x_override=None):
    x=d['x'][mask] if x_override is None else x_override
    z=(x[:,fit['cols']]-fit['mean'])/fit['scale'];eta=z@fit['b'][:len(fit['cols'])]
    if fit['fe']:eta+=fit['b'][len(fit['cols']):][d['city'][mask]]
    g=d['group'][mask];y=d['y'][mask].astype(float);pr,starts,sizes,_=probabilities(eta,g);tot=np.add.reduceat(y,starts)
    return pr*np.repeat(tot,sizes)

def evaluate(d,mask,mu,model):
    y=d['y'][mask].astype(float);cc=d['country'][mask];ps=d['p'][mask];ci=d['city'][mask];rows=[]
    dev=2*(np.where(y>0,y*np.log(np.maximum(y,1e-300)/np.maximum(mu,1e-300)),0)-y+mu)
    for c in np.unique(cc):
        for p in np.unique(ps):
            s=(cc==c)&(ps==p)
            if not s.any():continue
            yy=y[s];mm=mu[s];oi=np.bincount(ci[s],weights=yy);mi=np.bincount(ci[s],weights=mm)
            rows.append(dict(model=model,country=str(d['country_codes'][c]),period=int(p),events=float(yy.sum()),deviance=float(dev[s].sum()),CPC=float(np.minimum(yy,mm).sum()/yy.sum()),observed_HHI=float(np.sum((oi/oi.sum())**2)),predicted_HHI=float(np.sum((mi/mi.sum())**2))))
    return rows

def gravity():
    d=build_design();fits={};rows=[]
    configs=[('gravity',[0,1],False),('gravity_domestic',[0,1,2],False),('gravity_history',[0,1,3],False),('gravity_history_domestic',[0,1,3,2],False),('gravity_cityFE',[0,1],True),('gravity_domestic_cityFE',[0,1,2],True)]
    if (OUT/'gravity_fits.npz').exists():
        old=np.load(OUT/'gravity_fits.npz',allow_pickle=True);fits=old['fits'].item()
    for name,cols,fe in configs:
        if name not in fits or (fe and not fits[name].get('city_effect_penalty')):
            fits[name]=fit_choice(d,cols,fe);np.savez(OUT/'gravity_fits.npz',fits=np.array(fits,dtype=object))
        rows+=evaluate(d,d['p']>=4,predict(d,fits[name],d['p']>=4),name)
    metrics=pd.DataFrame(rows);metrics.to_csv(OUT/'gravity_heldout_metrics.csv',index=False)
    params=[]
    for model,f in fits.items():
        for j,col in enumerate(f['cols']):params.append(dict(model=model,feature=['log_mass','log_distance','log1p_domestic_degree','log1p_international_history'][col],coefficient=float(f['b'][j]/f['scale'][j]),converged=f['success'],max_gradient=f['gradient']))
    pd.DataFrame(params).to_csv(OUT/'gravity_parameters.csv',index=False)
    # Shuffle only degree assignment, preserving within-city replication across foreign origins.
    log('Test feature assignment with held-out within-mass-decile degree shuffles')
    mask=d['p']>=5;base=d['x'][mask].copy();cc=d['country'][mask];pp=d['p'][mask];ci=d['city'][mask]
    unique=pd.DataFrame(dict(c=cc,p=pp,city=ci,mass=base[:,0],degree=base[:,2])).drop_duplicates(['c','p','city'])
    unique['bin']=unique.groupby(['c','p']).mass.transform(lambda a:pd.qcut(a.rank(method='first'),min(10,len(a)),labels=False))
    key=pd.MultiIndex.from_arrays([cc,pp,ci]);ukey=pd.MultiIndex.from_frame(unique[['c','p','city']]);indexer=ukey.get_indexer(key)
    rng=np.random.default_rng(SEED);sh=[]
    for rep in range(20):
        shuffled=unique.degree.to_numpy().copy()
        for ids in unique.groupby(['c','p','bin']).indices.values():shuffled[ids]=rng.permutation(shuffled[ids])
        x=base.copy();x[:,2]=shuffled[indexer]
        mu=predict(d,fits['gravity_history_domestic'],mask,x)
        for r in evaluate(d,mask,mu,'shuffled_degree'):r['replicate']=rep;sh.append(r)
    pd.DataFrame(sh).to_csv(OUT/'gravity_degree_shuffle_metrics.csv',index=False)
    summary=[];rng=np.random.default_rng(SEED)
    for split,ps in [('validation',[4]),('test',[5,6])]:
        for baseline,extended in [('gravity','gravity_domestic'),('gravity_history','gravity_history_domestic'),('gravity_cityFE','gravity_domestic_cityFE')]:
            z=metrics[metrics.period.isin(ps)].groupby(['model','country'])[['deviance','events']].sum().reset_index()
            a=z[z.model==baseline].merge(z[z.model==extended],on='country',suffixes=('_base','_plus'))
            a['improvement']=100*(1-a.deviance_plus/a.deviance_base)
            v=a.improvement.to_numpy();bs=np.median(v[rng.integers(0,len(v),(4000,len(v)))],axis=1)
            summary.append(dict(split=split,baseline=baseline,extended=extended,countries=len(a),event_weighted_deviance_improvement_pct=float(100*(1-a.deviance_plus.sum()/a.deviance_base.sum())),median_country_improvement_pct=float(np.median(v)),median_CI_low=float(np.quantile(bs,.025)),median_CI_high=float(np.quantile(bs,.975)),countries_improved=int((v>0).sum()),countries_worse=int((v<0).sum())))
    js('gravity_comparison_summary.json',summary)
    log('Gravity analysis DONE');print(json.dumps(summary,indent=2))

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'prepare'
    if mode=='prepare':prepare()
    elif mode=='gravity':gravity()
