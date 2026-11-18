"""Pool cleaned mobility events using the verified OpenAlex field/domain taxonomy."""
from __future__ import annotations
import csv,hashlib,json,sys
from collections import defaultdict,Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np

OUT=ROOT/'results/disciplinary_domains_20261022'
SOURCE=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet'
FIG=ROOT/'figures/v3'
YEARS=np.arange(1998,2026);TIME=YEARS-YEARS.mean()
PERIODS=[(1998,2004),(2005,2011),(2012,2018),(2019,2025)]
NAMES={'Physical Sciences':'理工科学','Life Sciences':'生命科学',
       'Health Sciences':'健康科学','Social Sciences':'人文社会科学'}

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def slope(values):
    a=np.asarray(values,dtype=float);assert len(a)==28 and np.all(np.isfinite(a))
    return float(TIME@a/(TIME@TIME))

def growth(values):
    a=np.asarray(values,dtype=float);assert np.all(a>0)
    return float(100*np.expm1(slope(np.log(a))))

def category(gini,evenness):
    return 'concentration' if gini>1e-10 and evenness< -1e-10 else 'deconcentration' if gini< -1e-10 and evenness>1e-10 else 'mixed'

def fetch_metrics(con,table,keys,place):
    group=','.join(keys)
    query=f'''WITH ranked AS (SELECT *,row_number() OVER(PARTITION BY {group} ORDER BY flow,{place}) rk FROM {table})
        SELECT {group},count(*) N,sum(flow) strength,sum(flow*flow)/power(sum(flow),2) HHI,
        2.0*sum(rk*flow)/(count(*)*sum(flow))-(count(*)+1.0)/count(*) Gini FROM ranked GROUP BY {group} ORDER BY {group}'''
    rows=[]
    for result in con.execute(query).fetchall():
        n,total,hhi,gini=result[-4:]
        r=dict(zip(keys,result[:-4]));r.update(N=int(n),flow_events=float(total/2),HHI=float(hhi),Gini=max(0.,float(gini)),
            equivalent=1/float(hhi),normalized_equivalent=1/(int(n)*float(hhi)))
        assert 0<r['normalized_equivalent']<=1.00000001
        rows.append(r)
    return rows

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    taxonomy=json.loads((OUT/'openalex_fields_taxonomy.json').read_text(encoding='utf8'))['results']
    mapping=[dict(field=r['display_name'],field_id=r['id'],domain=r['domain']['display_name'],
                  domain_id=r['domain']['id'],domain_zh=NAMES[r['domain']['display_name']]) for r in taxonomy]
    byfield={r['field']:r['domain'] for r in mapping}
    assert len(byfield)==26 and Counter(byfield.values())=={'Physical Sciences':10,'Life Sciences':5,'Health Sciences':5,'Social Sciences':6}
    fields=read(FIG/'source_data/Fig6_field_trends.csv')
    assert set(byfield)=={r['field'] for r in fields}
    write('field_domain_mapping.csv',sorted(mapping,key=lambda r:(r['domain'],r['field'])))
    countries=json.loads((FIG/'QA/figure_manifest.json').read_text(encoding='utf8'))['cleaned_data_provenance']['fixed_country_codes']
    assert len(countries)==76
    con=duckdb.connect();con.execute("SET threads=4;SET memory_limit='3GB'")
    con.execute('CREATE TEMP TABLE taxonomy(field VARCHAR,domain VARCHAR)')
    con.executemany('INSERT INTO taxonomy VALUES (?,?)',list(byfield.items()))
    path=str(SOURCE).replace("'","''");codes=','.join("'"+c+"'" for c in countries)
    con.execute(f"CREATE VIEW all_events AS SELECT * FROM read_parquet('{path}') WHERE flow>0")
    con.execute('CREATE VIEW events AS SELECT e.*,t.domain FROM all_events e JOIN taxonomy t ON e.field=t.field')
    totals=[dict(domain=d,year=y,geography=g,flow_events=float(v)) for d,y,g,v in con.execute('''
        SELECT domain,year,CASE WHEN origin_country=destination_country THEN 'domestic' ELSE 'international' END geo,
        sum(flow) FROM events GROUP BY domain,year,geo ORDER BY domain,year,geo''').fetchall()]
    field_totals=[dict(field=f,domain=byfield[f],year=y,geography=g,flow_events=float(v)) for f,y,g,v in con.execute('''
        SELECT field,year,CASE WHEN origin_country=destination_country THEN 'domestic' ELSE 'international' END geo,
        sum(flow) FROM events GROUP BY field,year,geo ORDER BY field,year,geo''').fetchall()]
    unknown=con.execute("SELECT coalesce(sum(flow),0) FROM all_events WHERE field='Unknown'").fetchone()[0]
    total_all=con.execute('SELECT sum(flow) FROM all_events').fetchone()[0]
    assert sum(r['flow_events'] for r in totals)+unknown==total_all
    print('Computing four-domain country and domestic city distributions',flush=True)
    con.execute('''CREATE TEMP TABLE international_margins AS SELECT domain,year,country,sum(flow) flow FROM (
        SELECT domain,year,origin_country country,flow FROM events WHERE origin_country<>destination_country
        UNION ALL SELECT domain,year,destination_country,flow FROM events WHERE origin_country<>destination_country) GROUP BY ALL''')
    international=fetch_metrics(con,'international_margins',['domain','year'],'country')
    con.execute(f'''CREATE TEMP TABLE domestic_margins AS SELECT domain,year,country,city,sum(flow) flow FROM (
        SELECT domain,year,origin_country country,origin city,flow FROM events
        WHERE origin_country=destination_country AND origin_country IN ({codes})
        UNION ALL SELECT domain,year,destination_country,destination,flow FROM events
        WHERE origin_country=destination_country AND origin_country IN ({codes})) GROUP BY ALL''')
    domestic=fetch_metrics(con,'domestic_margins',['domain','country','year'],'city')
    # Retain pooled location margins so HHI/Gini can be checked independently.
    for table in ['international_margins','domestic_margins']:
        dest=str(OUT/f'{table}.parquet').replace("'","''")
        con.execute(f"COPY (SELECT * FROM {table}) TO '{dest}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.close()
    grouped=defaultdict(list)
    for r in domestic:grouped[r['domain'],r['country']].append(r)
    cohorts={d:{c for (dom,c),rs in grouped.items() if dom==d and len(rs)==28 and min(r['N'] for r in rs)>=2} for d in NAMES}
    common=sorted(set.intersection(*cohorts.values()));assert len(common)>=2
    lookup={(r['domain'],r['country'],r['year']):r for r in domestic}
    volume={(r['domain'],r['year'],r['geography']):r['flow_events'] for r in totals}
    intl={(r['domain'],r['year']):r for r in international}
    annual=[];trends=[];samples=[];country_trends=[];periods=[]
    all_named={g:sum(r['flow_events'] for r in totals if r['geography']==g) for g in ['international','domestic']}
    for d in NAMES:
        local_total=sum(volume[d,int(y),'domestic'] for y in YEARS)
        for basis,cohort in [('common_countries',common),('domain_specific_countries',sorted(cohorts[d]))]:
            retained=sum(lookup[d,c,int(y)]['flow_events'] for c in cohort for y in YEARS)
            samples.append(dict(domain=d,basis=basis,countries=len(cohort),country_codes=','.join(cohort),
                all_domestic_events=local_total,retained_domestic_events=retained,coverage_percent=100*retained/local_total))
            for year in map(int,YEARS):
                rows=[lookup[d,c,year] for c in cohort]
                annual.append(dict(domain=d,scale='domestic_city',basis=basis,year=year,countries=len(cohort),
                    flow_events_global=volume[d,year,'domestic'],flow_events_sample=sum(r['flow_events'] for r in rows),
                    **{k:float(np.median([r[k] for r in rows])) for k in ['N','HHI','Gini','equivalent','normalized_equivalent']}))
            for c in cohort:
                rs=sorted(grouped[d,c],key=lambda r:r['year'])
                gs=slope([r['Gini'] for r in rs])*100;ns=slope([r['normalized_equivalent'] for r in rs])*100
                country_trends.append(dict(domain=d,country=c,basis=basis,Gini_slope_pp=gs,normalized_slope_pp=ns,
                    equivalent_growth_pct=growth([r['equivalent'] for r in rs]),category=category(gs,ns)))
        for year in map(int,YEARS):
            r=intl[d,year]
            assert r['flow_events']==volume[d,year,'international']
            annual.append(dict(domain=d,scale='country',basis='all_countries',year=year,countries=int(r['N']),
                flow_events_global=r['flow_events'],flow_events_sample=r['flow_events'],
                **{k:r[k] for k in ['N','HHI','Gini','equivalent','normalized_equivalent']}))
        for scale,basis in [('country','all_countries'),('domestic_city','common_countries'),('domestic_city','domain_specific_countries')]:
            rs=sorted([r for r in annual if r['domain']==d and r['scale']==scale and r['basis']==basis],key=lambda r:r['year'])
            gs=slope([r['Gini'] for r in rs])*100;ns=slope([r['normalized_equivalent'] for r in rs])*100
            tr=dict(domain=d,domain_zh=NAMES[d],fields=sum(v==d for v in byfield.values()),scale=scale,basis=basis,
                countries=rs[0]['countries'] if scale=='domestic_city' else 0,
                total_events=sum(r['flow_events_global'] for r in rs),
                named_event_share_percent=100*sum(r['flow_events_global'] for r in rs)/all_named['international' if scale=='country' else 'domestic'],
                observed_flow_growth_pct=growth([r['flow_events_global'] for r in rs]),
                Gini_slope_pp=gs,normalized_slope_pp=ns,category=category(gs,ns),
                equivalent_growth_pct=growth([r['equivalent'] for r in rs]),
                **{k+'_'+str(y):next(r[k] for r in rs if r['year']==y) for k in ['N','HHI','Gini','equivalent','normalized_equivalent'] for y in [1998,2025]})
            trends.append(tr)
            for first,last in PERIODS:
                chunk=[r for r in rs if first<=r['year']<=last];t=np.arange(7)-3
                g=float(t@np.array([r['Gini'] for r in chunk])/(t@t)*100)
                n=float(t@np.array([r['normalized_equivalent'] for r in chunk])/(t@t)*100)
                periods.append(dict(domain=d,scale=scale,basis=basis,start=first,end=last,Gini_slope_pp=g,normalized_slope_pp=n,
                    category=category(g,n),Gini_mean=float(np.mean([r['Gini'] for r in chunk])),
                    normalized_mean=float(np.mean([r['normalized_equivalent'] for r in chunk]))))
    field_summary=[]
    field_lookup={(f,g):[r for r in field_totals if r['field']==f and r['geography']==g] for f in byfield for g in ['international','domestic']}
    for d in NAMES:
        fs=sorted(f for f in byfield if byfield[f]==d)
        for scale,geo in [('country','international'),('domestic_city','domestic')]:
            rs=[r for r in fields if r['field'] in fs and r['scale']==scale]
            classes=Counter(category(float(r['Gini_slope_pp']),float(r['normalized_slope_pp'])) for r in rs)
            rates=[growth([r['flow_events'] for r in sorted(field_lookup[f,geo],key=lambda r:r['year'])]) for f in fs]
            field_summary.append(dict(domain=d,scale=scale,fields=len(fs),concentration=classes['concentration'],
                deconcentration=classes['deconcentration'],mixed=classes['mixed'],
                median_global_recorded_flow_growth_pct=float(np.median(rates)),
                median_Gini_slope_pp=float(np.median([float(r['Gini_slope_pp']) for r in rs])),
                median_normalized_slope_pp=float(np.median([float(r['normalized_slope_pp']) for r in rs]))))
    write('domain_global_annual_volumes.csv',totals);write('field_global_annual_volumes.csv',field_totals)
    write('domain_country_annual_metrics.csv',international);write('domain_domestic_country_annual_metrics.csv',domestic)
    write('domain_annual_metrics.csv',annual);write('domain_trends.csv',trends)
    write('domain_domestic_samples.csv',samples);write('domain_domestic_country_trends.csv',country_trends)
    write('domain_period_trends.csv',periods);write('within_domain_field_summary.csv',field_summary)
    named=sum(all_named.values())
    manifest=dict(source=str(SOURCE.relative_to(ROOT)),source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        taxonomy_source='https://api.openalex.org/fields?per-page=100',taxonomy_reference='https://help.openalex.org/data/domains/',
        domains=NAMES,fields_per_domain=dict(Counter(byfield.values())),years=[1998,2025],common_country_count=len(common),
        common_countries=common,domain_specific_country_counts={d:len(v) for d,v in cohorts.items()},
        all_cleaned_events=float(total_all),named_field_events=named,unknown_events=float(unknown),
        event_policy='Observed intercity events; sum of named-field event counts, each counted once. Unknown excluded from domain comparisons.',
        pooling_policy='Sum flows across fields within each domain before calculating country/city indices; never average field HHI or Gini.',
        domestic_policy='Combine inflow and outflow city strengths within each country; primary comparison uses the same continuous >=2-city country cohort for all four domains and every year; annual country medians are fitted over all 28 years.',
        classification='Concentration: Gini slope positive and normalized equivalent number slope negative; deconcentration: opposite; mixed otherwise. Descriptive signs with 1e-10 pp/year tolerance; no significance test.',
        growth_policy='OLS on log annual observed global event count, transformed to percentage growth; descriptive, without coverage correction.',
        field_summary_policy='Within-domain counts use the 26 existing Fig6 field-specific fixed cohorts. This is distinct from pooling all fields into a domain.',
        rows=dict(annual=len(annual),country_annual=len(international),domestic_country_annual=len(domestic),trends=len(trends)))
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(common_country_count=len(common),named_events=named,unknown_events=float(unknown)),ensure_ascii=False))
    for r in trends:
        if r['basis']!='domain_specific_countries':print(json.dumps(r,ensure_ascii=False))
    print('FIELD_SUMMARY',json.dumps(field_summary,ensure_ascii=False))

if __name__=='__main__':main()
