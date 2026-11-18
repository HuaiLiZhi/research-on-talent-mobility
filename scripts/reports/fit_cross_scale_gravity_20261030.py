"""Held-out conditional gravity tests of domestic-network information.

Conditioning removes source-country/destination-country/period totals. This is
an allocation prediction exercise, not an estimate of causal attraction effects.
"""
from pathlib import Path
import os,sys,time,json,hashlib
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:
    os.environ[name]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps')]
import numpy as np,pandas as pd,duckdb
from scipy.optimize import minimize
from scipy.special import logsumexp
OUT=ROOT/'outputs/mechanism_validation_20261030'
DOMAINS=['Physical Sciences','Life Sciences','Health Sciences','Social Sciences']
NAMES=['log_lag_author_year_mass','log_approx_distance','log1p_lag_international_inflow','log1p_lag_domestic_partners']
SEED=20261030
def log(s):print(time.strftime('%H:%M:%S'),s,flush=True)
def q(p):return "'"+str(p).replace("'","''")+"'"
def save(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
def gini(v):
    v=np.sort(np.asarray(v,dtype=float));n=len(v)
    return float(2*np.dot(np.arange(1,n+1),v)/(n*v.sum())-(n+1)/n) if n>1 and v.sum()>0 else np.nan
def ci(v,rng):
    v=np.asarray(v);v=v[np.isfinite(v)]
    if len(v)==0:return [np.nan,np.nan]
    bs=np.median(v[rng.integers(0,len(v),(4000,len(v)))],axis=1)
    return np.quantile(bs,[.025,.975]).tolist()
def haversine(lat1,lon1,lat2,lon2):
    a=np.sin((lat1[:,None]-lat2[None,:])/2)**2+np.cos(lat1[:,None])*np.cos(lat2[None,:])*np.sin((lon1[:,None]-lon2[None,:])/2)**2
    return np.maximum(6371.0088*2*np.arcsin(np.sqrt(np.clip(a,0,1))),1.)

def blocks():
    c=duckdb.connect()
    def read(name):return c.sql(f'SELECT * FROM read_parquet({q(OUT/name)})').df()
    mass=read('primary_author_year_stock.parquet')
    origins=read('fixed_origin_centroids.parquet').set_index('country')
    origins['lat']=np.arctan2(origins.z,np.sqrt(origins.x**2+origins.y**2))
    origins['lon']=np.arctan2(origins.y,origins.x)
    inflow=read('international_city_inflow.parquet')
    partners=read('domestic_period_partners.parquet')
    od=read('international_destination_od.parquet')
    cities=pd.read_csv(ROOT/'data/processed/mobility_city_harmonized_20261020/cities.csv').drop_duplicates('city_id').set_index('city_id')
    sample76=pd.read_csv(OUT/'sample76.csv').country.tolist()
    sample45=pd.read_csv(OUT/'common45.csv').country.tolist()
    lists={};audit=[]
    for domain in ['All']+DOMAINS:
        log('Build complete conditional destination risk sets: '+domain)
        data=[];countries=sample76 if domain=='All' else sample45
        for country in countries:
            for p in [1,2,3]:
                s=mass[(mass.domain==domain)&(mass.country==country)&(mass.p==p-1)].set_index('city').sort_index()
                s=s[s.index.isin(cities.index)]
                loc=cities.loc[s.index]
                valid=loc.latitude.between(-90,90)&loc.longitude.between(-180,180)&(s.mass>0)
                s=s[valid];loc=cities.loc[s.index]
                a=od[(od.domain==domain)&(od.country==country)&(od.p==p)]
                all_events=float(a.flow.sum())
                if len(s)<2:continue
                a=a[a.d.isin(s.index)&a.oc.isin(origins.index)]
                if len(a)==0:continue
                origin_names=sorted(a.oc.unique());ii={v:i for i,v in enumerate(origin_names)};jj={v:j for j,v in enumerate(s.index)}
                y=np.zeros((len(ii),len(jj)))
                np.add.at(y,([ii[x] for x in a.oc],[jj[x] for x in a.d]),a.flow.to_numpy())
                oc=origins.loc[origin_names]
                distance=haversine(oc.lat.to_numpy(),oc.lon.to_numpy(),np.radians(loc.latitude.to_numpy()),np.radians(loc.longitude.to_numpy()))
                v=inflow[(inflow.domain==domain)&(inflow.country==country)&(inflow.p==p-1)].set_index('city').flow.reindex(s.index).fillna(0).to_numpy()
                z=partners[(partners.domain==domain)&(partners.country==country)&(partners.p==p-1)].set_index('city').partners.reindex(s.index).fillna(0).to_numpy()
                cov=[np.broadcast_to(np.log(s.mass.to_numpy()),y.shape),np.log(distance),
                     np.broadcast_to(np.log1p(v),y.shape),np.broadcast_to(np.log1p(z),y.shape)]
                data.append(dict(domain=domain,country=country,p=p,y=y,n=y.sum(1),cov=cov,cities=s.index.to_list()))
                audit.append(dict(domain=domain,country=country,period=p,all_incoming=all_events,retained_incoming=float(y.sum()),
                  retained_fraction=float(y.sum()/all_events),source_countries=len(ii),candidate_cities=len(jj),risk_pairs=int(y.size),recorded_zero_pairs=int((y==0).sum())))
        lists[domain]=data
    pd.DataFrame(audit).to_csv(OUT/'conditional_gravity_risk_set_audit.csv',index=False)
    c.close();return lists

def fit(data,cols):
    train=[b for b in data if b['p']<3]
    totals={country:sum(b['y'].sum() for b in train if b['country']==country) for country in sorted({b['country'] for b in train})}
    def objective(beta):
        value=0.;gradient=np.zeros(len(cols))
        for b in train:
            eta=sum(beta[k]*b['cov'][col] for k,col in enumerate(cols))
            lse=logsumexp(eta,axis=1)
            probability=np.exp(eta-lse[:,None]);resid=b['n'][:,None]*probability-b['y']
            w=1/(len(totals)*totals[b['country']])
            value+=w*(np.dot(b['n'],lse)-np.sum(b['y']*eta))
            for k,col in enumerate(cols):gradient[k]+=w*np.sum(resid*b['cov'][col])
        return value,gradient
    initial=np.array([1. if col in [0,2] else -.3 if col==1 else 0. for col in cols])
    result=minimize(objective,initial,jac=True,method='L-BFGS-B',options={'maxiter':250,'ftol':1e-12,'gtol':1e-7})
    grad=float(np.max(np.abs(objective(result.x)[1])))
    if not result.success or grad>1e-5:raise RuntimeError(str((result.message,grad)))
    return dict(cols=cols,beta=result.x.tolist(),training_objective=float(result.fun),gradient=grad,iterations=int(result.nit))

def evaluate(data,fits):
    rows=[]
    for model,fit_ in fits.items():
        for b in data:
            if b['p']!=3:continue
            eta=sum(fit_['beta'][k]*b['cov'][col] for k,col in enumerate(fit_['cols']))
            lp=eta-logsumexp(eta,axis=1)[:,None]
            predicted=b['n'][:,None]*np.exp(lp)
            y=b['y'];actual_city=y.sum(0);pred_city=predicted.sum(0)
            rows.append(dict(domain=b['domain'],country=b['country'],model=model,events=int(y.sum()),
              negative_log_likelihood_per_event=float(-np.sum(y*lp)/y.sum()),
              OD_CPC=float(np.minimum(y,predicted).sum()/y.sum()),
              city_margin_CPC=float(np.minimum(actual_city,pred_city).sum()/y.sum()),
              observed_HHI=float(np.sum((actual_city/actual_city.sum())**2)),
              predicted_HHI=float(np.sum((pred_city/pred_city.sum())**2)),
              observed_Gini_same_candidates=gini(actual_city),predicted_Gini_same_candidates=gini(pred_city)))
    return pd.DataFrame(rows)

def shared_domain_fit(data_by_domain,initial_fits):
    log('Fit shared domestic-network coefficient across all four domains')
    domains=list(DOMAINS);train={d:[b for b in data_by_domain[d] if b['p']<3] for d in domains}
    totals={d:{cc:sum(b['y'].sum() for b in train[d] if b['country']==cc) for cc in sorted({b['country'] for b in train[d]})} for d in domains}
    x0=np.r_[np.concatenate([initial_fits[d]['M2_network']['beta'][:3] for d in domains]),np.mean([initial_fits[d]['M2_network']['beta'][3] for d in domains])]
    def objective(beta):
        value=0.;gradient=np.zeros(len(beta))
        for di,d in enumerate(domains):
            z=np.r_[beta[di*3:di*3+3],beta[-1]]
            for b in train[d]:
                eta=sum(z[k]*b['cov'][k] for k in range(4));lse=logsumexp(eta,axis=1)
                resid=b['n'][:,None]*np.exp(eta-lse[:,None])-b['y']
                w=1/(len(domains)*len(totals[d])*totals[d][b['country']])
                value+=w*(np.dot(b['n'],lse)-np.sum(b['y']*eta))
                for k in range(3):gradient[di*3+k]+=w*np.sum(resid*b['cov'][k])
                gradient[-1]+=w*np.sum(resid*b['cov'][3])
        return value,gradient
    fit_=minimize(objective,x0,jac=True,method='L-BFGS-B',options={'maxiter':250,'ftol':1e-12,'gtol':1e-7})
    gradient=float(np.max(np.abs(objective(fit_.x)[1])))
    assert fit_.success and gradient<1e-5,(fit_.message,gradient)
    return {d:dict(cols=[0,1,2,3],beta=np.r_[fit_.x[di*3:di*3+3],fit_.x[-1]].tolist(),gradient=gradient,iterations=int(fit_.nit)) for di,d in enumerate(domains)}

def main():
    data=blocks();fits={};metrics=[]
    for d,bs in data.items():
        fits[d]={}
        for name,cols in [('M0_gravity',[0,1]),('M1_history',[0,1,2]),('M2_network',[0,1,2,3])]:
            log('Fit '+d+' '+name)
            fits[d][name]=fit(bs,cols)
            log('Coefficients '+str(fits[d][name]['beta']))
        metrics.append(evaluate(bs,fits[d]))
        save('conditional_gravity_fits.json',fits)
    shared=shared_domain_fit(data,fits)
    for d in DOMAINS:
        fits[d]['M2_shared_domain_network']=shared[d]
        metrics.append(evaluate(data[d],{'M2_shared_domain_network':shared[d]}))
    save('conditional_gravity_fits.json',fits)
    metrics=pd.concat(metrics,ignore_index=True);metrics.to_csv(OUT/'conditional_gravity_holdout_country_metrics.csv',index=False)
    rows=[];contrasts=[];rng=np.random.default_rng(SEED)
    for d,s in metrics.groupby('domain'):
        comparisons=[('M0_gravity','M1_history'),('M1_history','M2_network')]
        if d!='All':comparisons.append(('M2_shared_domain_network','M2_network'))
        for a,b in comparisons:
            z=s[s.model==a].merge(s[s.model==b],on=['domain','country'],suffixes=('_base','_new'))
            z['log_loss_reduction']=z.negative_log_likelihood_per_event_base-z.negative_log_likelihood_per_event_new
            z['CPC_gain']=z.OD_CPC_new-z.OD_CPC_base
            z['base_model']=a;z['new_model']=b
            contrasts.append(z[['domain','country','base_model','new_model','log_loss_reduction','CPC_gain']])
            lo,hi=ci(z.log_loss_reduction,rng);clo,chi=ci(z.CPC_gain,rng)
            rows.append(dict(domain=d,base_model=a,new_model=b,countries=len(z),holdout_events=int(z.events_new.sum()),
              median_log_loss_reduction=float(z.log_loss_reduction.median()),log_loss_CI_low=lo,log_loss_CI_high=hi,
              countries_improved_log_loss=int((z.log_loss_reduction>0).sum()),median_CPC_gain=float(z.CPC_gain.median()),CPC_CI_low=clo,CPC_CI_high=chi))
    contrasts=pd.concat(contrasts,ignore_index=True);contrasts.to_csv(OUT/'conditional_gravity_country_contrasts.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'conditional_gravity_holdout_summary.csv',index=False)
    # Direct paired country contrast: domain-specific versus shared network
    # parameter, averaged equally over domains before resampling countries.
    interaction=contrasts[contrasts.base_model=='M2_shared_domain_network'].groupby('country').log_loss_reduction.mean()
    lo,hi=ci(interaction,rng)
    save('conditional_gravity_manifest.json',{'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'numpy':np.__version__,'fit_weighting':'Each destination country has equal total training weight; within country event-weighted likelihood.',
      'train':'2005-2018','test':'2019-2025','all_zero_destinations':'Included within candidate city lists. Only source-country/destination-country/period groups with positive totals enter conditional likelihood.',
      'mass_lag':'Previous seven-year-period mean distinct primary-affiliation author-years; lagged candidates exclude cities without prior verified stock.',
      'domain_interaction_prediction':{'common_countries':len(interaction),'median_gain_domain_specific_vs_shared':float(interaction.median()),'country_bootstrap_CI':[lo,hi]},
      'causal_interpretation':False,'city_fixed_effects':False,'source_distance_approximation':True})
    log('DONE');print(pd.DataFrame(rows).to_string(index=False),flush=True)
if __name__=='__main__':main()
