"""Direct fixed-event-count rarefaction, prompted by frozen-geography diagnostic.

No gravity model, no new grouping, and no claim to remove bibliographic coverage bias.
"""
from pathlib import Path
import os,sys,json,time
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'scripts/reports'),str(ROOT/'tmp/nhb_fig2_python_deps')]
import validate_cross_scale_mechanisms_20261030 as common
import numpy as np,pandas as pd,duckdb
from scipy.stats import binomtest
REPS=int(sys.argv[1]) if len(sys.argv)>1 else 50
OUT=common.OUT if REPS==50 else common.OUT/f'rarefaction_{REPS}_independent_seed'
OUT.mkdir(exist_ok=True,parents=True);common.OUT=OUT

def indicators(counts,ii,jj,n):
    s=np.bincount(ii,weights=counts,minlength=n)+np.bincount(jj,weights=counts,minlength=n)
    s=np.sort(s[s>0]);nn=len(s);p=s/s.sum();h=np.dot(p,p)
    g=2*np.dot(np.arange(1,nn+1),s)/(nn*s.sum())-(nn+1)/nn
    return [g,h,1/(h*nn),float(nn)]

def main():
    seed=common.SEED+7+(11 if REPS!=50 else 0)
    common.js('event_rarefaction_plan.json',dict(date='2026-10-30',motivation='Frozen-opportunity model suggests active-only indicators respond to event-volume growth. This direct empirical diagnostic was specified before computing rarefaction outcomes.',
      data='Canonical domestic OD annual counts in the manuscript 76 countries; canonical worldwide international country OD counts.',
      years='1998-2025',procedure='For each country/system, set event count to its minimum annual observed total. Draw that many events without replacement from every annual directed OD count vector, using multivariate hypergeometric sampling.',
      replicates=REPS,indicators=['Gini','HHI','R','positive-flow location count'],
      primary='Country full-period OLS trend signs in Gini and R; observed versus mean rarefied annual series.',
      sensitivity='Countries whose minimum annual event count is at least 1000.',
      uncertainty='Country bootstrap for median trends; simulation replicates are not independent countries. Monte Carlo intervals describe resampling, not population sampling uncertainty.',
      limits=['Equal recorded event counts do not correct all publication coverage differences.','City identities and possible location support can still differ across years.','This conditions on the number of observed events rather than treating it as a cause.'],seed=seed))
    rng=np.random.default_rng(seed);c=duckdb.connect()
    dom=c.sql(f"SELECT * FROM read_parquet('{ROOT/'outputs/literature_network_validation_20261029/domestic_od_year.parquet'}')").df()
    canon=ROOT/'data/processed/mobility_city_harmonized_20261020/count_mobility_flow_annual_clean.parquet'
    intl=c.sql(f"SELECT year,from_country_code o,to_country_code d,sum(mobility_count)::BIGINT flow FROM read_parquet('{canon}') WHERE tier='top100pct' AND geography='international' GROUP BY ALL").df();c.close()
    sample=pd.read_csv(ROOT/'figures/v3/source_data/Fig4_country_concentration_trends.csv').country.tolist()
    dom=dom[dom.country.isin(sample)];intl['country']='WORLD'
    assert int(intl.flow.sum())==11529374
    rows=[];trends=[];metrics=['Gini','HHI','R','N'];yearcenter=np.arange(1998,2026,dtype=float);yearcenter-=yearcenter.mean();den=yearcenter@yearcenter
    for kind,data in [('domestic',dom),('international',intl)]:
        for num,(cc,group) in enumerate(data.groupby('country')):
            annual=group.groupby('year').flow.sum();assert len(annual)==28
            target=int(annual.min());obs=[];sim=[]
            for year,z in group.groupby('year',sort=True):
                names=np.unique(np.r_[z.o,z.d]);lookup={v:i for i,v in enumerate(names)}
                ii=np.array([lookup[v] for v in z.o]);jj=np.array([lookup[v] for v in z.d]);counts=z.flow.to_numpy(dtype=np.int64)
                o=np.array(indicators(counts,ii,jj,len(names)));obs.append(o)
                draws=np.empty((REPS,4))
                for rep in range(REPS):
                    sampled=rng.multivariate_hypergeometric(counts,target,method='marginals')
                    assert sampled.sum()==target
                    draws[rep]=indicators(sampled,ii,jj,len(names))
                sim.append(draws)
                row=dict(kind=kind,country=cc,year=int(year),observed_events=int(counts.sum()),rarefied_events=target)
                for j,k in enumerate(metrics):
                    row.update({f'observed_{k}':float(o[j]),f'rarefied_{k}':float(draws[:,j].mean()),f'rarefied_{k}_MC_low':float(np.quantile(draws[:,j],.025)),f'rarefied_{k}_MC_high':float(np.quantile(draws[:,j],.975))})
                rows.append(row)
            obs=np.array(obs);sim=np.array(sim);slopes=yearcenter@obs/den;rs=np.einsum('t,trk->rk',yearcenter,sim)/den
            row=dict(kind=kind,country=cc,rarefied_events=target)
            for j,k in enumerate(metrics):
                row.update({f'observed_{k}_slope':float(slopes[j]),f'rarefied_{k}_slope':float(rs[:,j].mean()),f'rarefied_{k}_slope_MC_low':float(np.quantile(rs[:,j],.025)),f'rarefied_{k}_slope_MC_high':float(np.quantile(rs[:,j],.975))})
            trends.append(row)
            if num%10==0:common.log(f'Event rarefaction {kind}: {num+1} systems complete')
            pd.DataFrame(rows).to_csv(OUT/'event_rarefaction_annual.csv',index=False)
            pd.DataFrame(trends).to_csv(OUT/'event_rarefaction_trends.csv',index=False)
    r=pd.DataFrame(trends);summ=[];rng=np.random.default_rng(common.SEED)
    for kind in ['domestic','international']:
        for minimum in [0,1000]:
            d=r[(r.kind==kind)&(r.rarefied_events>=minimum)]
            if len(d)==0:continue
            rec=dict(kind=kind,min_events=minimum,systems=len(d),median_rarefied_events=float(d.rarefied_events.median()),
              observed_joint_concentration=int(((d.observed_Gini_slope>0)&(d.observed_R_slope<0)).sum()),rarefied_joint_concentration=int(((d.rarefied_Gini_slope>0)&(d.rarefied_R_slope<0)).sum()))
            for k in metrics:
                v=d[f'rarefied_{k}_slope'].to_numpy();bs=np.median(v[rng.integers(0,len(v),(4000,len(v)))],axis=1)
                rec.update({f'observed_{k}_positive':int((d[f'observed_{k}_slope']>0).sum()),f'rarefied_{k}_positive':int((v>0).sum()),f'observed_{k}_median_slope':float(d[f'observed_{k}_slope'].median()),f'rarefied_{k}_median_slope':float(np.median(v)),f'rarefied_{k}_median_CI_low':float(np.quantile(bs,.025)) if len(v)>1 else None,f'rarefied_{k}_median_CI_high':float(np.quantile(bs,.975)) if len(v)>1 else None})
            summ.append(rec)
    common.js('event_rarefaction_summary.json',summ);common.log('Rarefaction DONE');print(json.dumps(summ,indent=2))

if __name__=='__main__':main()
