"""Aggregate-only, forward-time comparison of spatial and two-layer models.

No author records are read. All predictors are previous-period aggregate data.
Primary evaluations are paired country-level held-out allocation scores.
"""
from pathlib import Path
import os, sys, json, time, hashlib
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[k]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import numpy as np
import pandas as pd
import duckdb
from scipy.sparse import coo_matrix
from scipy.special import logsumexp
from scipy.optimize import minimize

OUT=ROOT/'outputs/aggregate_model_comparison_20261030'
OUT.mkdir(exist_ok=True,parents=True)
PRE=ROOT/'outputs/cross_scale_mechanism_validation_20261030'
CLEAN=ROOT/'data/processed/mobility_city_harmonized_20261020'
SEED=20261030

def log(s): print(time.strftime('%H:%M:%S'),s,flush=True)
def save(name,x): (OUT/name).write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf8')
def readpq(p):
    c=duckdb.connect(); d=c.sql(f"SELECT * FROM read_parquet('{p.as_posix()}')").df(); c.close(); return d
def parquet(d,name):
    c=duckdb.connect(); c.register('d',d); c.execute(f"COPY d TO '{(OUT/name).as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)");c.close()
def plan():
    save('analysis_plan.json',dict(date='2026-10-30',status='Exploratory, specified before computing these alternative models.',
      units='Country-city-four-year-period aggregates; no individual data or individual paths read.',
      periods=['1998-2001','2002-2005','2006-2009','2010-2013','2014-2017','2018-2021','2022-2025'],
      train=[1,2,3],validation=[4],test=[5,6],seed=SEED,
      scope='Same manuscript 76 countries. Candidate cities have positive verified author mass and coordinates in the preceding period. Outcomes include recorded zero inflow cities on that candidate list.',
      target='International and domestic CITY INFLOWS; directional mechanism diagnostics, not manuscript combined-strength concentration.',
      baseline='Conditional city allocation: lag research mass and geographic accessibility. Domestic access is sum other-city mass / true distance. International access uses lag-mass-weighted foreign-country centroids (approximation).',
      models=['G0_mass_access','H1_own_history_degree','C2_local_cross_layer','N3_network_cross_layer','Radiation_domestic_only'],
      network='D/I are directed aggregate OD matrices; P_s row-normalizes layer s. International signal P_I.T @ domestic_inflow; domestic signal P_D.T @ international_inflow. Counts are exposure indices, not same-person continuation.',
      radiation='Finite, row-normalized radiation probabilities using research mass as opportunities; lag domestic outflow weights supply origin mixture. Strictly closer opportunities; equal-distance ties share the same opportunity count.',
      primary='Country-equal training and country-paired held-out log loss. CPC and same-candidate HHI/Gini errors secondary. No model selected on test data.',
      limits=['Conditional on observed country-period total, not future total prediction.','Aggregated network lag does not identify causal spillover.','Candidate support excludes cities without prior mapped stock.','International accessibility baseline uses approximate foreign centroids; exact-distance OD check planned for any claimed international network increment.','All model families and negative results will be reported.'],
      manuscript_modified=False))

def distance(a,b):
    x=np.radians(a);y=np.radians(b)
    z=np.sin((x[:,None,0]-y[None,:,0])/2)**2+np.cos(x[:,None,0])*np.cos(y[None,:,0])*np.sin((x[:,None,1]-y[None,:,1])/2)**2
    return np.maximum(6371.0088*2*np.arcsin(np.sqrt(np.clip(z,0,1))),1.)

def prepare():
    if (OUT/'city_period_design.parquet').exists(): return
    plan(); log('Read canonical city OD aggregates and independent city-year mass')
    mass=readpq(PRE/'city_author_year_mass.parquet'); mass['p']=(mass.year-1998)//4
    mass=mass.groupby(['p','country','city'],as_index=False).mass.sum();mass['mass']/=4
    c=duckdb.connect()
    dd=c.sql(f"SELECT floor((year-1998)/4)::INT p,country,o,d,sum(flow) flow FROM read_parquet('{(ROOT/'outputs/literature_network_validation_20261029/domestic_od_year.parquet').as_posix()}') GROUP BY ALL").df();c.close()
    ii=readpq(PRE/'international_city_od_period.parquet')
    totals={'domestic':float(dd.flow.sum()),'international':float(ii.flow.sum())}
    assert totals=={'domestic':18173850.,'international':11529374.},totals
    save('canonical_accounting.json',totals)
    coords=pd.read_csv(CLEAN/'cities.csv').drop_duplicates('city_id').set_index('city_id')
    coords=coords[coords.latitude.between(-90,90)&coords.longitude.between(-180,180)]
    countries=pd.read_csv(ROOT/'outputs/mechanism_validation_20261030/sample76.csv').country.tolist()
    nodes=sorted(set(mass.city)|set(dd.o)|set(dd.d)|set(ii.o)|set(ii.d));index={v:i for i,v in enumerate(nodes)};n=len(nodes)
    def matrix(a):
        r=a.o.map(index).to_numpy();s=a.d.map(index).to_numpy();return coo_matrix((a.flow,(r,s)),shape=(n,n)).tocsr()
    mats={};vectors={}
    for p in range(7):
        D=matrix(dd[dd.p==p]);I=matrix(ii[ii.p==p]);Dout=np.asarray(D.sum(1)).ravel();Iout=np.asarray(I.sum(1)).ravel()
        PD=D.multiply(np.divide(1,Dout,out=np.zeros_like(Dout),where=Dout>0)[:,None]).tocsr()
        PI=I.multiply(np.divide(1,Iout,out=np.zeros_like(Iout),where=Iout>0)[:,None]).tocsr()
        Din=np.asarray(D.sum(0)).ravel();Iin=np.asarray(I.sum(0)).ravel()
        degree_D=(D+D.T).getnnz(axis=1);degree_I=(I+I.T).getnnz(axis=1)
        vectors[p]=dict(Din=Din,Iin=Iin,Dout=Dout,Iout=Iout,degree_D=degree_D,degree_I=degree_I,
                        Dsignal=np.asarray(PD.T@Iin).ravel(),Isignal=np.asarray(PI.T@Din).ravel())
        mats[p]=(D,I)
    rows=[];audit=[];radiation=[]
    for p in range(1,7):
        lag=mass[mass.p==p-1].copy();lag=lag[lag.city.isin(coords.index)]
        la=coords.loc[lag.city,['latitude','longitude']].to_numpy();m0=lag.mass.to_numpy()
        la_rad=np.radians(la);cart=np.c_[np.cos(la_rad[:,0])*np.cos(la_rad[:,1]),np.cos(la_rad[:,0])*np.sin(la_rad[:,1]),np.sin(la_rad[:,0])]
        ct=pd.DataFrame(cart*m0[:,None],columns=['x','y','z']);ct['country']=lag.country.to_numpy();ct['mass']=m0
        ct=ct.groupby('country').sum();ct['lat']=np.degrees(np.arctan2(ct.z,np.sqrt(ct.x**2+ct.y**2)));ct['lon']=np.degrees(np.arctan2(ct.y,ct.x))
        for cc in countries:
            s=lag[lag.country==cc].sort_values('city'); ids=s.city.map(index).to_numpy();m=s.mass.to_numpy();cities=s.city.tolist()
            if len(s)<2:continue
            xy=coords.loc[cities,['latitude','longitude']].to_numpy();ns=len(s)
            access=np.zeros(ns);rad=np.zeros(ns);wo=vectors[p-1]['Dout'][ids]
            if wo.sum()==0:wo=m.copy()
            wo=wo/wo.sum()
            # Only aggregate origin outflow weights enter radiation, never author paths.
            for start in range(0,ns,64):
                stop=min(start+64,ns);dist=distance(xy[start:stop],xy)
                dist[np.arange(stop-start),np.arange(start,stop)]=np.inf
                access[start:stop]=(1/dist)@m
                order=np.argsort(dist,axis=1,kind='stable');ds=np.take_along_axis(dist,order,axis=1);ms=m[order]
                cs=np.cumsum(ms,axis=1)-ms
                # Strictly closer: equal-distance opportunities share their first rank.
                for r in range(len(order)):
                    first=np.r_[True,np.diff(ds[r])!=0];starts=np.maximum.accumulate(np.where(first,np.arange(ns),0));cs[r]=cs[r,starts]
                mi=m[start:stop,None];prob=mi*ms/((mi+cs)*(mi+cs+ms));prob[~np.isfinite(ds)]=0
                prob/=prob.sum(1,keepdims=True)
                unsorted=np.empty_like(prob);np.put_along_axis(unsorted,order,prob,axis=1)
                rad+=wo[start:stop]@unsorted
            access=np.maximum(access,1e-12)
            foreign=ct[ct.index!=cc];fi=(foreign.mass.to_numpy()[None,:]/distance(xy,foreign[['lat','lon']].to_numpy())).sum(1)
            v=vectors[p-1];cur=vectors[p]
            base=pd.DataFrame(dict(country=cc,p=p,city=cities,mass=m,access_D=access,access_I=fi,
                lag_D=v['Din'][ids],lag_I=v['Iin'][ids],degree_D=v['degree_D'][ids],degree_I=v['degree_I'][ids],signal_D=v['Dsignal'][ids],signal_I=v['Isignal'][ids],
                y_D=cur['Din'][ids],y_I=cur['Iin'][ids],radiation_D=rad))
            rows.append(base)
            for target in ['D','I']:
                all_flow=(dd[(dd.p==p)&(dd.country==cc)].flow.sum() if target=='D' else ii[(ii.p==p)&(ii.country==cc)].flow.sum())
                audit.append(dict(country=cc,p=p,target=target,candidate_cities=ns,retained_flow=float(base['y_'+target].sum()),all_flow=float(all_flow),coverage=float(base['y_'+target].sum()/all_flow) if all_flow else None))
        log('Prepared lag-only four-year period '+str(p))
    data=pd.concat(rows,ignore_index=True);parquet(data,'city_period_design.parquet');pd.DataFrame(audit).to_csv(OUT/'risk_set_coverage.csv',index=False)
    assert np.isfinite(data.select_dtypes('number')).all().all()
    save('preparation_audit.json',dict(rows=len(data),countries=len(countries),nodes=n,periods=6,unique_city_country=int(data[['country','city']].drop_duplicates().shape[0]),no_individual_records_read=True))

def make_blocks(data,target):
    bs=[]
    for (cc,p),s in data.groupby(['country','p'],sort=True):
        y=s['y_'+target].to_numpy();N=y.sum()
        if N==0:continue
        own=s['lag_'+target].to_numpy();other=s['lag_'+('I' if target=='D' else 'D')].to_numpy()
        x=np.c_[np.log(s.mass),np.log(s['access_'+target]),np.log1p(own),np.log1p(s['degree_'+target]),np.log1p(other),np.log1p(s['signal_'+target])]
        # One mass-proportional pseudo-event only prevents assigning zero probability
        # to newly observed city inflows; fixed before this secondary comparison.
        persist=(own+s.mass.to_numpy()/s.mass.sum())/(own.sum()+1.)
        bs.append(dict(country=cc,p=int(p),y=y,N=N,x=x,radiation=s.radiation_D.to_numpy(),persistence=persist))
    return bs

def fit(bs,cols):
    tr=[b for b in bs if b['p']<=3];countries=sorted({b['country'] for b in tr});counts={c:sum(b['p']<=3 and b['country']==c for b in tr) for c in countries}
    # Each country and each available training period receive equal weight.
    def obj(beta):
        val=0.;grad=np.zeros(len(cols))
        for b in tr:
            x=b['x'][:,cols];eta=x@beta;lp=eta-logsumexp(eta);pr=np.exp(lp);shares=b['y']/b['N'];w=1/(len(countries)*counts[b['country']])
            val-=w*np.dot(shares,lp);grad+=w*x.T@(pr-shares)
        return val,grad
    res=minimize(obj,np.zeros(len(cols)),jac=True,method='L-BFGS-B',options=dict(maxiter=350,gtol=1e-8,ftol=1e-13))
    err=float(np.max(np.abs(obj(res.x)[1])));assert res.success and err<1e-5,(res.message,err)
    return dict(cols=cols,beta=res.x.tolist(),gradient=err,iterations=int(res.nit),loss=float(res.fun))

def gini(x):
    x=np.sort(x);n=len(x);return float(2*np.dot(np.arange(1,n+1),x)/(n*x.sum())-(n+1)/n)

def evaluate(bs,fits,target):
    rows=[]
    for b in bs:
        if b['p']<4:continue
        y=b['y'];s=y/b['N']
        for name,f in fits.items():
            if name in ['Radiation','Persistence']:
                pr=b['radiation' if name=='Radiation' else 'persistence'].copy();pr=np.maximum(pr,1e-300);pr/=pr.sum()
            else:
                eta=b['x'][:,f['cols']]@np.array(f['beta']);pr=np.exp(eta-logsumexp(eta))
            rows.append(dict(target=target,model=name,country=b['country'],p=b['p'],events=int(b['N']),
              nll=float(-np.dot(s,np.log(np.maximum(pr,1e-300)))),CPC=float(np.minimum(s,pr).sum()),
              HHI_abs_error=float(abs(np.sum(s*s)-np.sum(pr*pr))),Gini_abs_error=float(abs(gini(y)-gini(pr)))))
    return pd.DataFrame(rows)

def bootstrap_ci(v,rng):
    v=np.asarray(v);x=np.median(v[rng.integers(0,len(v),size=(4000,len(v)))],axis=1);return np.quantile(x,[.025,.975]).tolist()

def run():
    prepare();data=readpq(OUT/'city_period_design.parquet');fits={};scores=[]
    configs={'G0_mass_access':[0,1],'H0_own_history':[0,1,2],'H1_own_history_degree':[0,1,2,3],'C2_local_cross_layer':[0,1,2,3,4],'N3_network_cross_layer':[0,1,2,3,4,5],
             'C0_cross_no_degree':[0,1,2,4],'N0_cross_no_degree':[0,1,2,4,5]}
    for target in ['D','I']:
        bs=make_blocks(data,target);fits[target]={}
        for name,cols in configs.items():
            fits[target][name]=fit(bs,cols);log(target+' '+name+' '+str(fits[target][name]['beta']))
        if target=='D':fits[target]['Radiation']={}
        fits[target]['Persistence']={}
        scores.append(evaluate(bs,fits[target],target))
    save('fitted_models.json',fits);metrics=pd.concat(scores);metrics.to_csv(OUT/'heldout_country_period_scores.csv',index=False)
    summary=[];contrasts=[];rng=np.random.default_rng(SEED)
    for split,periods in [('validation',[4]),('test',[5,6])]:
        for target in ['D','I']:
            s=metrics[(metrics.target==target)&metrics.p.isin(periods)].groupby(['country','model'])[['nll','CPC','HHI_abs_error','Gini_abs_error']].mean().reset_index()
            comparisons=[('G0_mass_access','H1_own_history_degree'),('H1_own_history_degree','C2_local_cross_layer'),('C2_local_cross_layer','N3_network_cross_layer'),('H1_own_history_degree','N3_network_cross_layer')]
            comparisons += [('G0_mass_access','H0_own_history'),('H0_own_history','H1_own_history_degree'),('G0_mass_access','Persistence'),('Persistence','H0_own_history')]
            comparisons += [('H0_own_history','C0_cross_no_degree'),('C0_cross_no_degree','N0_cross_no_degree'),('H0_own_history','N0_cross_no_degree')]
            if target=='D':comparisons+=[('G0_mass_access','Radiation'),('H1_own_history_degree','Radiation')]
            for a,b in comparisons:
                z=s[s.model==a].merge(s[s.model==b],on='country',suffixes=('_base','_new'))
                gain=z.nll_base-z.nll_new;cg=z.CPC_new-z.CPC_base;ci=bootstrap_ci(gain,rng);cci=bootstrap_ci(cg,rng)
                summary.append(dict(split=split,target=target,base=a,new=b,countries=len(z),median_nll_reduction=float(gain.median()),nll_CI_low=ci[0],nll_CI_high=ci[1],countries_better=int((gain>0).sum()),median_CPC_gain=float(cg.median()),CPC_CI_low=cci[0],CPC_CI_high=cci[1],median_HHI_error_reduction=float((z.HHI_abs_error_base-z.HHI_abs_error_new).median()),median_Gini_error_reduction=float((z.Gini_abs_error_base-z.Gini_abs_error_new).median())))
                z['split']=split;z['target']=target;z['base']=a;z['new']=b;z['nll_reduction']=gain;z['CPC_gain']=cg;contrasts.append(z)
    pd.DataFrame(summary).to_csv(OUT/'model_comparison_summary.csv',index=False);pd.concat(contrasts).to_csv(OUT/'paired_country_contrasts.csv',index=False)
    save('runtime_and_scope.json',dict(numpy=np.__version__,pandas=pd.__version__,duckdb=duckdb.__version__,python=sys.version,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),country_weighting='equal country and equal training period; evaluation averages periods within country before country bootstrap',causal=False))
    log('DONE');print(pd.DataFrame(summary).query("split=='test'").to_string(index=False),flush=True)

if __name__=='__main__':run()
