"""Exploratory paired domain contrasts and common fixed-city comparison."""
from pathlib import Path
import os,sys,itertools,json,time
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'outputs/mechanism_validation_20261030'
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps'),str(ROOT/'scripts/reports')]
import numpy as np,pandas as pd,duckdb
from scipy.stats import wilcoxon,friedmanchisquare
from statsmodels.stats.multitest import multipletests
from analyze_mechanism_domains_20261030 import DOMAINS,metrics,interval

def paired(pivot,quantity):
    rows=[];pivot=pivot.reindex(columns=DOMAINS).dropna()
    for a,b in itertools.combinations(DOMAINS,2):
        v=(pivot[b]-pivot[a]).to_numpy();lo,hi=interval(v)
        rows.append(dict(quantity=quantity,base_domain=a,comparison_domain=b,countries=len(v),median_paired_difference=float(np.median(v)),CI_low=lo,CI_high=hi,
          p_wilcoxon=float(wilcoxon(v,method='auto').pvalue) if np.any(v!=0) else 1.))
    r=pd.DataFrame(rows);r['p_holm_six_pairs']=multipletests(r.p_wilcoxon,method='holm')[1]
    return r

def main():
    c=duckdb.connect();common=pd.read_csv(OUT/'common45.csv').country.tolist()
    c.register('common',pd.DataFrame({'country':common}))
    z=c.sql(f"SELECT x.* FROM read_parquet('{OUT/'domestic_domain_city_year.parquet'}') x JOIN common USING(country) WHERE domain NOT IN ('All','Unspecified')").df();c.close()
    # Every included city has positive flows in each of28 years in all4 domains.
    n=z.groupby(['country','city','domain']).year.nunique().rename('years').reset_index()
    n=n[n.years==28].groupby(['country','city']).domain.nunique().rename('domains').reset_index()
    commoncities=n[n.domains==4][['country','city']]
    counts=commoncities.groupby('country').size();eligible=counts[counts>=2].index
    commoncities=commoncities[commoncities.country.isin(eligible)]
    commoncities.to_csv(OUT/'same_city_list_all_domains.csv',index=False)
    a=z.merge(commoncities,on=['country','city']);totals=z.groupby(['country','domain','year']).strength.sum()
    annual=[]
    for (cc,d,y),s in a.groupby(['country','domain','year']):
        annual.append(dict(country=cc,domain=d,year=int(y),flow_coverage=float(s.strength.sum()/totals.loc[(cc,d,y)]),**metrics(s.strength)))
    annual=pd.DataFrame(annual);annual.to_csv(OUT/'same_country_same_fixed_cities_domain_annual.csv',index=False)
    slopes=[]
    for (cc,d),s in annual.groupby(['country','domain']):
        assert len(s)==28
        x=s.year.to_numpy();x=x-x.mean()
        slopes.append(dict(country=cc,domain=d,Gini_pp_year=float(100*np.dot(x,s.Gini)/np.dot(x,x)),R_pp_year=float(100*np.dot(x,s.R)/np.dot(x,x)),N=int(s.N.iloc[0]),
          flow_coverage_1998=float(s.loc[s.year==1998,'flow_coverage'].iloc[0]),flow_coverage_2025=float(s.loc[s.year==2025,'flow_coverage'].iloc[0])))
    slopes=pd.DataFrame(slopes);slopes.to_csv(OUT/'same_country_same_fixed_cities_domain_trends.csv',index=False)
    summary=[]
    for d,s in slopes.groupby('domain'):
        lo,hi=interval(s.Gini_pp_year)
        summary.append(dict(domain=d,countries=len(s),median_fixed_cities=float(s.N.median()),median_Gini_pp_year=float(s.Gini_pp_year.median()),CI_low=lo,CI_high=hi,
          positive_Gini=int((s.Gini_pp_year>0).sum()),joint_concentration=int(((s.Gini_pp_year>0)&(s.R_pp_year<0)).sum()),
          joint_deconcentration=int(((s.Gini_pp_year<0)&(s.R_pp_year>0)).sum()),
          median_flow_coverage_1998=float(s.flow_coverage_1998.median()),median_flow_coverage_2025=float(s.flow_coverage_2025.median())))
    pd.DataFrame(summary).to_csv(OUT/'same_country_same_fixed_cities_domain_summary.csv',index=False)
    paired(slopes.pivot(index='country',columns='domain',values='Gini_pp_year'),'Gini_pp_year_same_cities').to_csv(OUT/'same_city_domain_paired_Gini_trend_comparisons.csv',index=False)
    mh=pd.read_csv(OUT/'domain_country_matched_hhi.csv');mh=mh[mh.domain.isin(DOMAINS)&mh.country.isin(common)&(mh.records>=100)]
    paired(mh.pivot(index='country',columns='domain',values='relative_excess_over_matched_pct'),'matched_HHI_excess_percent').to_csv(OUT/'domain_matched_hhi_paired_comparisons.csv',index=False)
    (OUT/'domain_comparability_audit.json').write_text(json.dumps({'country_count':len(eligible),'same_city_list_in_all_four_domains':True,
      'minimum_fixed_city_count':2,'additional_analysis':'Exploratory extension prompted by the domain-specific fixed-city results; not a prespecified primary test.',
      'bootstrap':'Country-paired nominal95% percentile intervals; six Wilcoxon comparisons Holm-adjusted within each analysis.'},indent=2),encoding='utf8')
    print(pd.DataFrame(summary).to_string(index=False))
if __name__=='__main__':main()
