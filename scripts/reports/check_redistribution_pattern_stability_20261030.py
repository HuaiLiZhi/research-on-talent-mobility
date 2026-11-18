from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/literature_pathway_extension_20261030'
sys.path[:0]=[str(ROOT/'outputs/country_typology_validation_20261029/python_deps'),str(ROOT/'tmp/nhb_fig2_python_deps')]
import numpy as np,pandas as pd,duckdb
from sklearn.metrics import adjusted_rand_score

def pattern(d):
    return np.select([(d.next_HHI<d.entry_HHI)&(d.next_HHI>d.expected_HHI),(d.next_HHI<d.entry_HHI)&(d.next_HHI<=d.expected_HHI),(d.next_HHI>=d.entry_HHI)&(d.next_HHI>d.expected_HHI)],['dispersed_above','dispersed_below','concentrated_above'],default='concentrated_below')
def main():
    c=duckdb.connect()
    a=c.sql(f"SELECT a.*,s.required_last_year-5 arrival_year FROM read_parquet('{OUT/'full_matching_cohort_destination_counts.parquet'}') a JOIN read_parquet('{OUT/'full_matching_strata.parquet'}') s USING(stratum_id)").df()
    b=c.sql(f"SELECT * FROM read_parquet('{OUT/'full_matching_other_destination_counts.parquet'}')").df();c.close()
    results=[]
    for label in ['early','late']:
        target=a[a.arrival_year<=2014] if label=='early' else a[a.arrival_year>=2015]
        keys=['country','stratum_id','d'];t=target.groupby(keys).weight.sum().rename('target').reset_index()
        control=b[b.stratum_id.isin(t.stratum_id.unique())].rename(columns={'weight':'control'})
        z=t.merge(control,on=keys,how='outer').fillna({'target':0,'control':0});z['pool']=z.target+z.control
        totals=z.groupby(['country','stratum_id']).agg(n=('target','sum'),M=('pool','sum')).reset_index()
        z=z.merge(totals,on=['country','stratum_id']);z['prob']=z.pool/z.M;z['mu']=z.n*z.prob;z['p2']=z.prob**2
        p2=z.groupby(['country','stratum_id']).p2.sum().reset_index();totals=totals.merge(p2,on=['country','stratum_id'])
        totals['V']=np.where(totals.M>1,totals.n*(totals.M-totals.n)/(totals.M-1)*(1-totals.p2),0)
        for cc,g in z.groupby('country'):
            N=g.target.sum();ob=g.groupby('d').target.sum();mu=g.groupby('d').mu.sum();v=totals[totals.country==cc].V.sum()
            ent=target[target.country==cc].groupby('arrival_city').weight.sum()
            results.append(dict(country=cc,cohort=label,records=int(N),entry_HHI=float(np.sum((ent/N)**2)),next_HHI=float(np.sum((ob/N)**2)),expected_HHI=float((np.sum(mu**2)+v)/N**2)))
    r=pd.DataFrame(results);r['pattern']=pattern(r);r.to_csv(OUT/'redistribution_patterns_by_entry_cohort.csv',index=False)
    out=[]
    for minimum in [100,500]:
        q=r[r.records>=minimum];x=q[q.cohort=='early'].merge(q[q.cohort=='late'],on='country',suffixes=('_early','_late'))
        out.append(dict(minimum_records=minimum,countries=len(x),same_pattern=int((x.pattern_early==x.pattern_late).sum()),same_fraction=float((x.pattern_early==x.pattern_late).mean()),ARI=float(adjusted_rand_score(x.pattern_early,x.pattern_late))))
    (OUT/'redistribution_pattern_stability.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
