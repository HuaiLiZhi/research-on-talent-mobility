"""Country-paired domain comparisons and exact matched HHI references."""
from pathlib import Path
import os,sys,json,time,argparse,hashlib,itertools
for name in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[name]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps')]
import numpy as np,pandas as pd,duckdb
from scipy.stats import binomtest,friedmanchisquare,wilcoxon
from statsmodels.stats.multitest import multipletests
OUT=ROOT/'outputs/mechanism_validation_20261030'
PREVIOUS=ROOT/'outputs/literature_pathway_extension_20261030'
DOMAINS=['Physical Sciences','Life Sciences','Health Sciences','Social Sciences']
RNG=np.random.default_rng(20261030)
def log(s):print(time.strftime('%H:%M:%S'),s,flush=True)
def q(p):return "'"+str(p).replace("'","''")+"'"
def save(name,obj):(OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf8')
def gini(v):
    v=np.sort(np.asarray(v,dtype=float));n=len(v)
    return float(2*np.dot(np.arange(1,n+1),v)/(n*v.sum())-(n+1)/n) if n>1 and v.sum()>0 else np.nan
def metrics(v):
    v=np.asarray(v,dtype=float);v=v[v>0];p=v/v.sum();h=np.sum(p*p)
    return dict(N=len(v),HHI=h,Gini=gini(v),R=1/(h*len(v)))
def interval(v,stat=np.median):
    v=np.asarray(v,dtype=float);v=v[np.isfinite(v)]
    if len(v)==0:return [np.nan,np.nan]
    bs=stat(v[RNG.integers(0,len(v),(4000,len(v)))],axis=1)
    return np.quantile(bs,[.025,.975]).tolist()

def trends():
    log('Recompute canonical concentration by domain, using the common45 countries')
    c=duckdb.connect();c.execute("SET threads=2;SET memory_limit='2GB'")
    common=pd.read_csv(OUT/'common45.csv').country.tolist()
    z=c.sql(f"SELECT * FROM read_parquet({q(OUT/'domestic_domain_city_year.parquet')}) WHERE domain<>'Unspecified'").df()
    z=z[z.country.isin(common)]
    annual=[];fixed=[]
    for (d,cc),s in z.groupby(['domain','country']):
        persistent=s.groupby('city').year.nunique();persistent=persistent[persistent==28].index
        for year,g in s.groupby('year'):
            annual.append(dict(domain=d,country=cc,year=int(year),**metrics(g.strength)))
            v=g[g.city.isin(persistent)].strength
            if len(v)>1:fixed.append(dict(domain=d,country=cc,year=int(year),flow_coverage=float(v.sum()/g.strength.sum()),**metrics(v)))
    annual=pd.DataFrame(annual);fixed=pd.DataFrame(fixed)
    annual.to_csv(OUT/'canonical_domain_domestic_annual.csv',index=False)
    fixed.to_csv(OUT/'canonical_domain_fixed_city_annual.csv',index=False)
    slopes=[]
    for label,data in [('all_recorded',annual),('persistent_cities',fixed)]:
        for (d,cc),s in data.groupby(['domain','country']):
            if len(s)!=28:continue
            x=s.year.to_numpy();x=x-x.mean();g=s.Gini.to_numpy();r=s.R.to_numpy()
            slopes.append(dict(domain=d,country=cc,city_membership=label,Gini_pp_year=float(100*np.dot(x,g)/np.dot(x,x)),R_pp_year=float(100*np.dot(x,r)/np.dot(x,x)),
              city_growth_percent_year=float(100*np.expm1(np.dot(x,np.log(s.N))/np.dot(x,x))),N_initial=int(s.loc[s.year==1998,'N'].iloc[0]),N_final=int(s.loc[s.year==2025,'N'].iloc[0])))
    slopes=pd.DataFrame(slopes);slopes.to_csv(OUT/'canonical_domain_domestic_trends.csv',index=False)
    intl=c.sql(f"""SELECT domain,year,country,sum(flow) strength FROM (
      SELECT domain,year,oc country,flow FROM read_parquet({q(OUT/'international_domain_country_od_year.parquet')})
      UNION ALL SELECT domain,year,country,flow FROM read_parquet({q(OUT/'international_domain_country_od_year.parquet')})) GROUP BY ALL""").df()
    rows=[]
    for (d,year),s in intl.groupby(['domain','year']):rows.append(dict(domain=d,year=int(year),**metrics(s.strength)))
    ia=pd.DataFrame(rows);ia.to_csv(OUT/'canonical_domain_international_annual.csv',index=False)
    summaries=[]
    for d in ['All']+DOMAINS:
        i=ia[ia.domain==d];x=i.year.to_numpy();x=x-x.mean();s=slopes[(slopes.domain==d)&(slopes.city_membership=='all_recorded')]
        f=slopes[(slopes.domain==d)&(slopes.city_membership=='persistent_cities')]
        summaries.append(dict(domain=d,domestic_countries=len(s),international_Gini_pp_year=float(100*np.dot(x,i.Gini)/np.dot(x,x)),
          median_domestic_Gini_pp_year=float(s.Gini_pp_year.median()),positive_Gini_countries=int((s.Gini_pp_year>0).sum()),
          joint_concentration_countries=int(((s.Gini_pp_year>0)&(s.R_pp_year<0)).sum()),
          persistent_eligible_countries=len(f),persistent_deconcentration_countries=int(((f.Gini_pp_year<0)&(f.R_pp_year>0)).sum())))
    pd.DataFrame(summaries).to_csv(OUT/'canonical_domain_trend_summary.csv',index=False)
    c.close()

def matched_hhi():
    log('Stratify previously matched domestic continuation risk sets by recorded field domain')
    c=duckdb.connect()
    a=c.sql(f"SELECT * FROM read_parquet({q(PREVIOUS/'full_matching_cohort_destination_counts.parquet')})").df()
    b=c.sql(f"SELECT * FROM read_parquet({q(PREVIOUS/'full_matching_other_destination_counts.parquet')})").df()
    strata=c.sql(f"SELECT stratum_id,field FROM read_parquet({q(PREVIOUS/'full_matching_strata.parquet')})").df();c.close()
    mapping=pd.read_csv(OUT/'field_domain_mapping.csv')[['field','domain']]
    strata=strata.merge(mapping,on='field',how='left').fillna({'domain':'Unspecified'})
    a=a.merge(strata[['stratum_id','domain']],on='stratum_id',validate='many_to_one')
    b=b.merge(strata[['stratum_id','domain']],on='stratum_id',validate='many_to_one')
    allrows=[]
    for mode in ['All','Domains']:
        aa=a.copy();bb=b.copy()
        if mode=='All':aa['domain']='All';bb['domain']='All'
        target=aa.groupby(['domain','country','stratum_id','d']).weight.sum().rename('target').reset_index()
        control=bb.rename(columns={'weight':'control'})
        z=target.merge(control,on=['domain','country','stratum_id','d'],how='outer').fillna({'target':0,'control':0})
        z['pooled']=z.target+z.control
        margins=z.groupby(['domain','country','stratum_id']).agg(n=('target','sum'),M=('pooled','sum'),control_total=('control','sum')).reset_index()
        z=z.merge(margins,on=['domain','country','stratum_id'],validate='many_to_one')
        z['prob']=z.pooled/z.M;z['expected']=z.n*z.prob;z['prob2']=z.prob*z.prob
        p2=z.groupby(['domain','country','stratum_id']).prob2.sum().rename('sum_p2').reset_index()
        margins=margins.merge(p2,on=['domain','country','stratum_id'],validate='one_to_one')
        margins['variance']=np.where(margins.M>1,margins.n*(margins.M-margins.n)/(margins.M-1)*(1-margins.sum_p2),0)
        for (d,cc),s in z.groupby(['domain','country']):
            m=margins[(margins.domain==d)&(margins.country==cc)]
            cohort=aa[(aa.domain==d)&(aa.country==cc)]
            n=s.target.sum();ob=s.groupby('d').target.sum();mu=s.groupby('d').expected.sum()
            en=cohort.groupby('arrival_city').weight.sum()
            h0=np.sum((en.to_numpy()/n)**2);h1=np.sum((ob.to_numpy()/n)**2)
            eh=(np.sum(mu.to_numpy()**2)+m.variance.sum())/n**2
            allrows.append(dict(domain=d,country=cc,records=int(n),entry_HHI=h0,next_HHI=h1,expected_HHI=eh,
              entry_Gini_positive=gini(en[en>0]),next_Gini_positive=gini(ob[ob>0]),
              relative_change_from_entry_pct=100*(h1/h0-1),relative_excess_over_matched_pct=100*(h1/eh-1),
              reference_supported_fraction=float(m.loc[m.control_total>0,'n'].sum()/n)))
    rows=pd.DataFrame(allrows);rows.to_csv(OUT/'domain_country_matched_hhi.csv',index=False)
    # Guard against accidental changes to the prior all-domain benchmark.
    prior=pd.read_csv(PREVIOUS/'fully_matched_country_hhi.csv')
    check=rows[rows.domain=='All'].merge(prior,on='country',suffixes=('_new','_old'))
    for x in ['records','entry_HHI','next_HHI','expected_HHI']:
        assert np.allclose(check[x+'_new'],check[x+'_old'],rtol=1e-9,atol=1e-12),x
    common=set(pd.read_csv(OUT/'common45.csv').country)
    sub=rows[rows.domain.isin(DOMAINS)&rows.country.isin(common)&(rows.records>=100)]
    eligible=sub.groupby('country').domain.nunique();balanced=set(eligible[eligible==4].index)
    summary=[]
    for sample,ss in [('available_country_domains_min100',sub),('same_country_all_four_domains_min100',sub[sub.country.isin(balanced)])]:
        for d,s in ss.groupby('domain'):
            v=s.relative_excess_over_matched_pct.to_numpy();lo,hi=interval(v)
            summary.append(dict(sample=sample,domain=d,countries=len(s),records=int(s.records.sum()),
              median_entry_to_next_HHI_pct=float(s.relative_change_from_entry_pct.median()),median_excess_vs_reference_pct=float(np.median(v)),
              CI_low=lo,CI_high=hi,above_reference=int((v>0).sum()),p_sign=float(binomtest(int((v>0).sum()),len(v),.5).pvalue),
              median_reference_supported_fraction=float(s.reference_supported_fraction.median())))
    summary=pd.DataFrame(summary);summary['p_holm_four_domains']=np.nan
    for sample in summary['sample'].unique():
        m=summary['sample']==sample;summary.loc[m,'p_holm_four_domains']=multipletests(summary.loc[m,'p_sign'],method='holm')[1]
    summary.to_csv(OUT/'domain_matched_hhi_summary.csv',index=False)
    save('domain_hhi_audit.json',{'prior_all_domain_reference_reproduced':True,'balanced_country_count':len(balanced),
      'domain_assignment':'Recorded field at next domestic move, exactly matching the existing risk sets.',
      'conditional_reference':'Independent finite hypergeometric draws within matched risk sets, which can overlap; no global label permutation or causal identification.'})
    log('Prior exact HHI reference reproduced; domain extension complete')

def paths():
    log('Compare individual paths across domains within the same countries')
    x=pd.read_csv(OUT/'domain_country_arrival_paths.csv')
    common=set(pd.read_csv(OUT/'common45.csv').country)
    rows=[];summary=[];paired=[];omnibus=[]
    for horizon in [3,5]:
        s=x[(x.horizon==horizon)&(x.max_observation_gap==0)&x.domain.isin(DOMAINS)&x.country.isin(common)]
        counts=s.groupby(['domain','country','path']).records.sum().unstack('path',fill_value=0)
        counts['total']=counts.sum(axis=1)
        enough=counts[counts.total>=100].reset_index().groupby('country').domain.nunique()
        eligible=set(enough[enough==4].index)
        r=counts.reset_index();r=r[r.country.isin(eligible)]
        for path in ['domestic','previous_origin_return','third_country','no_recorded_intercity_change','unresolved_next']:
            r[path+'_share']=r[path]/r.total
        r['horizon']=horizon;rows.append(r)
        for d,g in r.groupby('domain'):
            lo,hi=interval(g.domestic_share)
            summary.append(dict(horizon=horizon,domain=d,countries=len(g),entry_records=int(g.total.sum()),
              pooled_domestic_share=float(g.domestic.sum()/g.total.sum()),country_median_domestic_share=float(g.domestic_share.median()),
              country_median_CI_low=lo,country_median_CI_high=hi,
              country_median_previous_origin_return=float(g.previous_origin_return_share.median()),
              country_median_third_country=float(g.third_country_share.median()),
              country_median_no_change=float(g.no_recorded_intercity_change_share.median())))
        pivot=r.pivot(index='country',columns='domain',values='domestic_share').reindex(columns=DOMAINS)
        if len(pivot)>2:
            test=friedmanchisquare(*[pivot[d].to_numpy() for d in DOMAINS])
            omnibus.append(dict(horizon=horizon,countries=len(pivot),Friedman_statistic=float(test.statistic),p=float(test.pvalue)))
        for a,b in itertools.combinations(DOMAINS,2):
            v=(pivot[b]-pivot[a]).to_numpy();lo,hi=interval(v)
            p=float(wilcoxon(v,method='auto').pvalue) if np.any(v!=0) else 1.
            paired.append(dict(horizon=horizon,base_domain=a,comparison_domain=b,countries=len(v),median_difference_pp=float(100*np.median(v)),CI_low_pp=100*lo,CI_high_pp=100*hi,p_wilcoxon=p))
    summary=pd.DataFrame(summary);summary.to_csv(OUT/'domain_path_summary_balanced.csv',index=False)
    pd.concat(rows,ignore_index=True).to_csv(OUT/'domain_country_paths_balanced.csv',index=False)
    paired=pd.DataFrame(paired);paired['p_holm_six_pairs']=np.nan
    for h in [3,5]:
        m=paired.horizon==h;paired.loc[m,'p_holm_six_pairs']=multipletests(paired.loc[m,'p_wilcoxon'],method='holm')[1]
    paired.to_csv(OUT/'domain_path_paired_comparisons.csv',index=False)
    pd.DataFrame(omnibus).to_csv(OUT/'domain_path_omnibus.csv',index=False)
    # Pooled route accounting across all76, preserving unspecified fields.
    pooled=x[(x.horizon==5)&(x.max_observation_gap==0)].groupby(['domain','path']).records.sum().reset_index()
    pooled['domain_total']=pooled.groupby('domain').records.transform('sum');pooled['share']=pooled.records/pooled.domain_total
    pooled.to_csv(OUT/'domain_path_pooled76.csv',index=False)
    contrib=pd.read_csv(OUT/'domain_country_year_continuation_contribution.csv')
    pooledc=contrib.groupby('domain')[['all_domestic_events','target_events']].sum();pooledc['fraction']=pooledc.target_events/pooledc.all_domestic_events
    pooledc.reset_index().to_csv(OUT/'domain_continuation_contribution_summary.csv',index=False)
    first=int(contrib.loc[contrib.target_events>0,'year'].min());last=int(contrib.loc[contrib.target_events>0,'year'].max())
    window=contrib[contrib.year.between(first,last)].groupby('domain')[['all_domestic_events','target_events']].sum()
    window['fraction']=window.target_events/window.all_domestic_events;window['first_year']=first;window['last_year']=last
    window.reset_index().to_csv(OUT/'continuation_contribution_actual_event_window.csv',index=False)
    countryc=contrib.groupby(['domain','country'])[['all_domestic_events','target_events']].sum();countryc['fraction']=countryc.target_events/countryc.all_domestic_events
    countryc.reset_index().to_csv(OUT/'domain_country_continuation_contribution.csv',index=False)
    reverse=pd.read_csv(OUT/'domain_source_country_domestic_to_international.csv')
    rr=reverse.groupby('domain')[['international_departures','preceded_by_domestic_within5']].sum();rr['fraction']=rr.preceded_by_domestic_within5/rr.international_departures
    rr.reset_index().to_csv(OUT/'domain_domestic_to_international_summary.csv',index=False)
    log('Balanced-domain path comparisons complete')

def main():
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=['aggregate','paths','all'],default='all');args=p.parse_args()
    if args.stage in ['aggregate','all']:trends();matched_hhi()
    if args.stage in ['paths','all']:paths()
    save('domain_analysis_runtime.json',{'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'country_bootstrap_replicates':4000,'seed':20261030})
if __name__=='__main__':main()
