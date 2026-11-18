"""Secondary reverse-direction test using a fixed gravity-accessibility baseline.

This predicts country-internal combined city strength, not individual domestic
move hazards. Accessibility uses lagged mass divided by true intercity distance;
the inverse-distance exponent is fixed at one, not estimated or selected.
"""
from pathlib import Path
import os,sys,time,json,hashlib
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps'),str(ROOT/'scripts/reports')]
import numpy as np,pandas as pd,duckdb
from fit_cross_scale_gravity_20261030 import fit,evaluate,haversine,ci,DOMAINS
OUT=ROOT/'outputs/mechanism_validation_20261030'
def log(s):print(time.strftime('%H:%M:%S'),s,flush=True)
def main():
    c=duckdb.connect()
    mass=c.sql(f"SELECT * FROM read_parquet('{OUT/'primary_author_year_stock.parquet'}')").df()
    strength=c.sql(f"SELECT floor((year-1998)/7)::INT p,domain,country,city,sum(strength) strength FROM read_parquet('{OUT/'domestic_domain_city_year.parquet'}') GROUP BY ALL").df()
    intl=c.sql(f"SELECT * FROM read_parquet('{OUT/'international_city_inflow.parquet'}')").df()
    partners=c.sql(f"SELECT * FROM read_parquet('{OUT/'domestic_period_partners.parquet'}')").df();c.close()
    cities=pd.read_csv(ROOT/'data/processed/mobility_city_harmonized_20261020/cities.csv').drop_duplicates('city_id').set_index('city_id')
    sample76=pd.read_csv(OUT/'sample76.csv').country.tolist();sample45=pd.read_csv(OUT/'common45.csv').country.tolist()
    metrics=[];allfits={};audit=[]
    for domain in ['All']+DOMAINS:
        log('Build lagged gravity accessibility: '+domain);blocks=[]
        for cc in (sample76 if domain=='All' else sample45):
            for p in [1,2,3]:
                s=mass[(mass.domain==domain)&(mass.country==cc)&(mass.p==p-1)].set_index('city').sort_index()
                s=s[s.index.isin(cities.index)];loc=cities.loc[s.index]
                good=loc.latitude.between(-90,90)&loc.longitude.between(-180,180)&(s.mass>0)
                s=s[good];loc=cities.loc[s.index]
                if len(s)<2:continue
                y0=strength[(strength.domain==domain)&(strength.country==cc)&(strength.p==p)].set_index('city').strength
                y=y0.reindex(s.index).fillna(0).to_numpy()[None,:]
                if y.sum()==0:continue
                lat=np.radians(loc.latitude.to_numpy());lon=np.radians(loc.longitude.to_numpy());m=s.mass.to_numpy()
                access=np.zeros(len(s))
                for start in range(0,len(s),128):
                    stop=min(start+128,len(s));dd=haversine(lat[start:stop],lon[start:stop],lat,lon)
                    dd[np.arange(stop-start),np.arange(start,stop)]=np.inf
                    access[start:stop]=(1/dd)@m
                assert np.all(access>0)
                def lag(df,col):return df[(df.domain==domain)&(df.country==cc)&(df.p==p-1)].set_index('city')[col].reindex(s.index).fillna(0).to_numpy()
                cov=[np.log(m)[None,:],np.log(access)[None,:],np.log1p(lag(strength,'strength'))[None,:],
                     np.log1p(lag(intl,'flow'))[None,:],np.log1p(lag(partners,'partners'))[None,:]]
                blocks.append(dict(domain=domain,country=cc,p=p,y=y,n=y.sum(1),cov=cov))
                audit.append(dict(domain=domain,country=cc,period=p,candidate_cities=len(s),all_strength=float(y0.sum()),retained_strength=float(y.sum()),retained_fraction=float(y.sum()/y0.sum())))
        fits={}
        for name,cols in [('D0_mass_accessibility',[0,1]),('D1_domestic_history',[0,1,2,4]),('D2_international_history',[0,1,2,3,4])]:
            fits[name]=fit(blocks,cols);log(domain+' '+name+' '+str(fits[name]['beta']))
        allfits[domain]=fits;metrics.append(evaluate(blocks,fits))
        (OUT/'domestic_allocation_fits.json').write_text(json.dumps(allfits,indent=2),encoding='utf8')
    metrics=pd.concat(metrics,ignore_index=True);metrics.to_csv(OUT/'domestic_allocation_holdout_metrics.csv',index=False)
    pd.DataFrame(audit).to_csv(OUT/'domestic_allocation_risk_set_audit.csv',index=False)
    rows=[];contrasts=[];rng=np.random.default_rng(20261030)
    for domain,s in metrics.groupby('domain'):
        for a,b in [('D0_mass_accessibility','D1_domestic_history'),('D1_domestic_history','D2_international_history')]:
            z=s[s.model==a].merge(s[s.model==b],on=['domain','country'],suffixes=('_base','_new'))
            z['log_loss_reduction']=z.negative_log_likelihood_per_event_base-z.negative_log_likelihood_per_event_new
            z['CPC_gain']=z.city_margin_CPC_new-z.city_margin_CPC_base
            z['base_model']=a;z['new_model']=b;contrasts.append(z[['domain','country','base_model','new_model','log_loss_reduction','CPC_gain']])
            lo,hi=ci(z.log_loss_reduction,rng);clo,chi=ci(z.CPC_gain,rng)
            rows.append(dict(domain=domain,base_model=a,new_model=b,countries=len(z),median_log_loss_reduction=float(z.log_loss_reduction.median()),
              log_loss_CI_low=lo,log_loss_CI_high=hi,countries_improved=int((z.log_loss_reduction>0).sum()),median_CPC_gain=float(z.CPC_gain.median()),CPC_CI_low=clo,CPC_CI_high=chi))
    pd.concat(contrasts,ignore_index=True).to_csv(OUT/'domestic_allocation_country_contrasts.csv',index=False)
    pd.DataFrame(rows).to_csv(OUT/'domestic_allocation_holdout_summary.csv',index=False)
    (OUT/'domestic_allocation_manifest.json').write_text(json.dumps({'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
      'status':'Secondary exploratory reverse-direction allocation test, not a full domestic OD gravity model.',
      'gravity_accessibility':'A_j=sum_i!=j M_i/d_ij; lagged primary-affiliation author-year mass, true harmonized intercity distances, inverse-distance exponent fixed1.',
      'features':['log lag mass','log lag gravity accessibility','log1p lag combined domestic strength','log1p lag international inflow','log1p lag domestic partners'],
      'outcome':'Combined domestic inflow+outflow city strength. Not a count of unique domestic events.',
      'scope':'Condition on country/period totals and lagged candidate-city list; train2005-2018, test2019-2025; equal-country fitting.',
      'causal_interpretation':False},indent=2),encoding='utf8')
    log('DONE');print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
