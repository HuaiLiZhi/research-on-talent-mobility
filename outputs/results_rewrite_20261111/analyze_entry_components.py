"""Exact descriptive C/I/E decomposition of recorded domestic distributions.

Analysis choices follow the preceding revision plan. This is an accounting
decomposition, not a causal intervention on migration events.
"""
from pathlib import Path
import csv
import hashlib
import json
import numpy as np
import duckdb

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
OUT.mkdir(parents=True,exist_ok=True)
SOURCE=ROOT/'outputs/mechanism_validation_20261030/domestic_domain_city_year.parquet'
SAMPLE=ROOT/'outputs/mechanism_validation_20261030/sample76.csv'
plan=dict(sample='Same frozen 76 countries, combined domestic strength, 1998-2025',
          groups=dict(C='Positive flow in all 28 years',I='First recorded in 1998, not C; active this year',E='First recorded after 1998; active this year'),
          reference='C; preserve full-network city margins, renormalize selected city weights',
          attribution='Average the two insertion orders of I and E',
          primary='Gini and normalized equivalent-city proportion R; HHI retained as directional check',
          trends='OLS on the same 28 annual observations for each component',
          scope='Descriptive distribution-composition attribution; no causal identification',
          reporting='All76; no contribution ratios for near-zero total slopes; no sum-of-medians identity')
planpath=OUT/'entry_decomposition_plan.json'
if not planpath.exists():planpath.write_text(json.dumps(plan,indent=2),encoding='utf8')
else:assert json.loads(planpath.read_text(encoding='utf8'))==plan

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as h:return list(csv.DictReader(h))

def write(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def metrics(v):
    v=np.sort(np.asarray(v,dtype=float))
    assert len(v)>=2 and np.all(v>0)
    p=v/v.sum();n=len(v);h=float(p@p)
    return dict(Gini=float(2*np.dot(np.arange(1,n+1),p)/n-(n+1)/n),R=1/(n*h),HHI=h)

sample=sorted(r['country'] for r in read(SAMPLE));assert len(sample)==76
c=duckdb.connect()
c.execute('SET threads=2')
z=c.sql(f"SELECT country,year,city,strength FROM read_parquet('{SOURCE.as_posix()}') WHERE domain='All' AND country IN (SELECT country FROM read_csv_auto('{SAMPLE.as_posix()}')) ORDER BY country,year,city").df()
c.close()
assert z.duplicated(['country','year','city']).sum()==0 and (z.strength>0).all()
annual=[];endpoints=[]
for cc,s in z.groupby('country',sort=True):
    meta=s.groupby('city').year.agg(['min','count'])
    continuous=set(meta.index[meta['count']==28]);initial=set(meta.index[meta['min']==1998])
    assert len(continuous)>=2 and continuous<=initial
    for year,g in s.groupby('year',sort=True):
        is_c=g.city.isin(continuous).to_numpy();is_i=g.city.isin(initial-continuous).to_numpy();is_e=~g.city.isin(initial).to_numpy()
        assert np.all(is_c.astype(int)+is_i.astype(int)+is_e.astype(int)==1)
        v=g.strength.to_numpy(dtype=float)
        pools=dict(C=metrics(v[is_c]),CI=metrics(v[is_c|is_i]),CE=metrics(v[is_c|is_e]),All=metrics(v))
        row=dict(country=cc,year=int(year),N=len(v),N_C=int(sum(is_c)),N_I=int(sum(is_i)),N_E=int(sum(is_e)),
                 entrant_city_share=float(np.mean(is_e)),entrant_flow_share=float(v[is_e].sum()/v.sum()),
                 continuous_flow_share=float(v[is_c].sum()/v.sum()))
        for m in ['Gini','R','HHI']:
            a,b,d,f=[pools[k][m] for k in ['C','CI','CE','All']]
            e=.5*((d-a)+(f-b));i=.5*((b-a)+(f-d))
            assert abs(f-a-e-i)<1e-13
            for k,value in dict(All=f,C=a,Entry=e,Intermittent=i,CI=b,CE=d).items():row[f'{m}_{k}']=value
        annual.append(row)
        if year==2025:endpoints.append(row)

assert len(annual)==2128
trends=[];x=np.arange(28,dtype=float);x-=x.mean()
for cc in sample:
    rs=sorted([r for r in annual if r['country']==cc],key=lambda r:r['year'])
    assert [r['year'] for r in rs]==list(range(1998,2026))
    row=dict(country=cc)
    for m in ['Gini','R','HHI']:
        for comp in ['All','C','Entry','Intermittent']:
            values=np.array([r[f'{m}_{comp}'] for r in rs])
            row[f'{m}_{comp}_slope']=float(x@values/(x@x))
        assert abs(row[f'{m}_All_slope']-sum(row[f'{m}_{k}_slope'] for k in ['C','Entry','Intermittent']))<1e-13
    row['all_relative_concentration']=int(row['Gini_All_slope']>0 and row['R_All_slope']<0)
    row['continuous_deconcentration']=int(row['Gini_C_slope']<0 and row['R_C_slope']>0)
    row['entry_relative_concentration']=int(row['Gini_Entry_slope']>0 and row['R_Entry_slope']<0)
    row['entry_largest_positive_Gini_component']=int(row['Gini_Entry_slope']>0 and row['Gini_Entry_slope']>max(row['Gini_C_slope'],row['Gini_Intermittent_slope']))
    trends.append(row)

old_all=read(ROOT/'figures/v3/source_data/Fig4_country_concentration_trends.csv')
old_fixed=read(ROOT/'outputs/fig2_6_recalculation_20261023_180757/auxiliary_data/fixed_cities/combined_fixed_city_trends.csv')
index={r['country']:r for r in trends};errors=[]
for rows,comp in [(old_all,'All'),(old_fixed,'C')]:
    for r in rows:
        k='Gini_slope_pp' if comp=='All' else 'Gini_slope_pp_year'
        errors.append(abs(100*index[r['country']][f'Gini_{comp}_slope']-float(r[k])))
        k='normalized_equivalent_cities_slope_pp' if comp=='All' else 'normalized_slope_pp_year'
        errors.append(abs(100*index[r['country']][f'R_{comp}_slope']-float(r[k])))
assert max(errors)<1e-10
write('entry_components_annual.csv',annual);write('entry_components_trends.csv',trends)
write('entrant_2025.csv',endpoints)
summary=[]
for m in ['Gini','R','HHI']:
    for comp in ['All','C','Intermittent','Entry']:
        values=np.array([r[f'{m}_{comp}_slope'] for r in trends])
        summary.append(dict(metric=m,component=comp,countries=76,median_annual_slope=float(np.median(values)),
                            median_pp_year=float(100*np.median(values)) if m!='HHI' else '',
                            mean_annual_slope=float(np.mean(values)),positive=int(sum(values>1e-15)),negative=int(sum(values < -1e-15))))
write('entry_components_summary.csv',summary)
concentrated=[r for r in trends if r['all_relative_concentration']]
scope=dict(countries=76,country_years=2128,input_city_year_rows=len(z),
           reproduced_primary_max_error_pp=max(errors),
           all_relative_concentration=len(concentrated),
           continuous_deconcentration=sum(r['continuous_deconcentration'] for r in trends),
           all_concentration_but_continuous_deconcentration=sum(r['continuous_deconcentration'] for r in concentrated),
           entry_joint_concentration_all=sum(r['entry_relative_concentration'] for r in trends),
           entry_joint_concentration_among_concentrating=sum(r['entry_relative_concentration'] for r in concentrated),
           entry_largest_positive_Gini_component_among_concentrating=sum(r['entry_largest_positive_Gini_component'] for r in concentrated),
           entrant_2025_median_city_share=float(np.median([r['entrant_city_share'] for r in endpoints])),
           entrant_2025_median_flow_share=float(np.median([r['entrant_flow_share'] for r in endpoints])),
           entrant_count_share_gt_flow_share_country_years=sum(r['entrant_city_share']>r['entrant_flow_share'] for r in annual if r['year']>1998),
           summaries=summary,source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [SOURCE,SAMPLE]},
           interpretation='Exact accounting of the recorded distribution, including full external-group city margins; no intervention on actual flows')
(OUT/'entry_decomposition_results.json').write_text(json.dumps(scope,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in scope.items() if k not in ['source_hashes','interpretation','summaries']},indent=2))
print(json.dumps(summary,indent=2))
