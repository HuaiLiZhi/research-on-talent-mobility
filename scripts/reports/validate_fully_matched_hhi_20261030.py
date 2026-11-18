"""Exact HHI expectation for independent finite draws in matched risk sets.

Risk sets can overlap through different required follow-up thresholds. This
is an explicitly defined conditional resampling reference, not one global
label permutation across disjoint strata and not causal identification.
"""
from pathlib import Path
import sys,json,itertools,hashlib
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/literature_pathway_extension_20261030'
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import numpy as np,pandas as pd,duckdb
from scipy.stats import binomtest

def exact_small_example():
    pools=[['A','A','B'],['A','B','C']];sizes=[2,1]
    vals=[]
    for selections in itertools.product(*[list(itertools.combinations(p,n)) for p,n in zip(pools,sizes)]):
        picked=sum([list(s) for s in selections],[]);v=np.array([picked.count(k) for k in ['A','B','C']]);vals.append(np.sum((v/v.sum())**2))
    means=np.zeros(3);var=0
    for p,n in zip(pools,sizes):
        prob=np.array([p.count(k)/len(p) for k in ['A','B','C']]);means+=n*prob
        var+=n*(len(p)-n)/(len(p)-1)*(1-np.sum(prob**2))
    analytic=(np.sum(means**2)+var)/sum(sizes)**2
    assert abs(analytic-np.mean(vals))<1e-12
    return dict(enumerated_mean=float(np.mean(vals)),analytic_mean=float(analytic),combinations=len(vals),passed=True)

def main():
    check=exact_small_example()
    c=duckdb.connect()
    a=c.sql(f"SELECT * FROM read_parquet('{OUT/'full_matching_cohort_destination_counts.parquet'}')").df()
    b=c.sql(f"SELECT * FROM read_parquet('{OUT/'full_matching_other_destination_counts.parquet'}')").df()
    c.close()
    keys=['country','stratum_id','d']
    target=a.groupby(keys).weight.sum().rename('target').reset_index();control=b.rename(columns={'weight':'control'})
    assert not target.duplicated(keys).any() and not control.duplicated(keys).any()
    z=target.merge(control,on=keys,how='outer').fillna({'target':0,'control':0})
    z['pooled']=z.target+z.control
    margins=z.groupby(['country','stratum_id']).agg(n=('target','sum'),M=('pooled','sum'),control_total=('control','sum')).reset_index()
    z=z.merge(margins,on=['country','stratum_id'],validate='many_to_one')
    z['probability']=z.pooled/z.M;z['expected']=z.n*z.probability
    sq=z.groupby(['country','stratum_id']).probability.apply(lambda s:np.sum(s.to_numpy()**2)).rename('sum_p_squared').reset_index()
    margins=margins.merge(sq,on=['country','stratum_id'])
    margins['variance_sum']=np.where(margins.M>1,margins.n*(margins.M-margins.n)/(margins.M-1)*(1-margins.sum_p_squared),0)
    assert margins.variance_sum.min()>-1e-8
    rows=[]
    for cc,g in z.groupby('country'):
        n=g.target.sum();ob=g.groupby('d').target.sum();mu=g.groupby('d').expected.sum()
        m=margins[margins.country==cc];variance=m.variance_sum.sum();eh=(np.sum(mu.to_numpy()**2)+variance)/(n*n)
        obs=np.sum((ob.to_numpy()/n)**2)
        ent=a[a.country==cc].groupby('arrival_city').weight.sum();h0=np.sum((ent.to_numpy()/n)**2)
        supported=m.loc[m.control_total>0,'n'].sum()/n
        rows.append(dict(country=cc,records=int(n),entry_HHI=float(h0),next_HHI=float(obs),expected_HHI=float(eh),
          relative_change_from_entry_pct=100*(obs/h0-1),relative_excess_over_matched_pct=100*(obs/eh-1),
          difference_from_reference=float(obs-eh),reference_supported_record_fraction=float(supported),
          deterministic_only_record_fraction=float(m.loc[m.control_total==0,'n'].sum()/n),strata=len(m)))
    r=pd.DataFrame(rows);r.to_csv(OUT/'fully_matched_country_hhi.csv',index=False)
    rng=np.random.default_rng(20261030);summaries=[]
    for minimum in [100,500]:
        s=r[r.records>=minimum];v=s.relative_excess_over_matched_pct.to_numpy();bs=np.median(v[rng.integers(0,len(s),(4000,len(s)))],axis=1)
        summaries.append(dict(minimum_records=minimum,countries=len(s),records=int(s.records.sum()),
          median_change_from_entry_pct=float(s.relative_change_from_entry_pct.median()),median_excess_vs_reference_pct=float(np.median(v)),
          median_excess_CI_low=float(np.quantile(bs,.025)),median_excess_CI_high=float(np.quantile(bs,.975)),
          above_reference=int((s.difference_from_reference>0).sum()),below_reference=int((s.difference_from_reference<0).sum()),
          sign_test_p=float(binomtest(int((s.difference_from_reference>0).sum()),len(s),.5).pvalue),
          median_reference_supported_fraction=float(s.reference_supported_record_fraction.median())))
    report=dict(exact_expectation_check=check,summary=summaries,conditional_null='independent finite hypergeometric draws in each matched conditional risk set; pooled target/control destination counts, fixed case counts; overlapping risk sets possible',global_permutation_test=False,
      bootstrap_unit='country',bootstrap_replicates=4000,individual_confidence_claims=False,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'fully_matched_hhi_summary.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
