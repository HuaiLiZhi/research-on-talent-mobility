"""Write new cleaned mobility datasets and an exact event-accounting ledger."""
from pathlib import Path
from datetime import datetime, timezone
import csv
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import duckdb
from prepare_city_harmonization_nodes_20261020 import identity,quote

OUT=ROOT/'data/processed/mobility_city_harmonized_20261020'
RAW=ROOT/'data/input/mobility/openalex'
INPUTS=[('annual','count_mobility_flow_annual.csv'),('career','count_mobility_flow_career.csv'),
        ('baseline','mobility_flow_by_field_clean.csv')]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def export(c,sql,path,parquet=False):
    path.parent.mkdir(parents=True,exist_ok=True)
    c.execute(f"COPY ({sql}) TO {quote(path)} (FORMAT "+('PARQUET,COMPRESSION ZSTD' if parquet else 'CSV,HEADER TRUE')+')')


def main():
    (OUT/'analysis').mkdir(exist_ok=True);(OUT/'audit').mkdir(exist_ok=True)
    c=duckdb.connect(str(OUT/'audit/flow_rebuild.duckdb'))
    c.execute("SET threads=4; SET memory_limit='4GB';SET preserve_insertion_order=false")
    c.execute('create or replace table mapping as select * from read_csv('+quote(OUT/'city_crosswalk.csv')+',header=true,all_varchar=true)')
    n,unique=c.execute('select count(*),count(distinct raw_place_id) from mapping').fetchone();assert n==unique
    c.execute('create or replace table countries as select distinct country_code,country_name from mapping')
    c.execute('create or replace table city_catalog as select * from read_csv('+quote(OUT/'cities.csv')+',header=true,all_varchar=true)')
    audits=[]
    for dataset,filename in INPUTS:
        checkpoint=OUT/'audit'/f'dataset_{dataset}.json'
        if checkpoint.exists():
            prior=json.loads(checkpoint.read_text(encoding='utf-8'))
            assert prior['city_crosswalk_sha256']==sha(OUT/'city_crosswalk.csv')
            audits.append(prior['dataset_audit']);print('Reusing completed '+dataset+' dataset',flush=True);continue
        print('Cleaning '+filename,flush=True)
        tier="coalesce(nullif(trim(tier),''),'unknown_tier')" if dataset!='baseline' else "'top100pct'"
        normalized=f"""SELECT try_cast(year AS INTEGER) AS year,{tier} AS tier,
          coalesce(nullif(trim(field_display_name),''),'Unknown') AS field,
          upper(trim(coalesce(from_country_code,''))) AS oc,lower(trim(coalesce(from_region,''))) AS orr,
          lower(trim(coalesce(from_city,''))) AS oci,round(try_cast(from_latitude AS DOUBLE),5) AS olat,
          round(try_cast(from_longitude AS DOUBLE),5) AS olon,
          upper(trim(coalesce(to_country_code,''))) AS dc,lower(trim(coalesce(to_region,''))) AS drr,
          lower(trim(coalesce(to_city,''))) AS dci,round(try_cast(to_latitude AS DOUBLE),5) AS dlat,
          round(try_cast(to_longitude AS DOUBLE),5) AS dlon,try_cast(mobility_count AS DOUBLE) AS flow
          FROM read_csv({quote(RAW/filename)},header=true,all_varchar=true)
          WHERE try_cast(year AS INTEGER) BETWEEN 1998 AND 2025
            AND try_cast(mobility_count AS DOUBLE)>0 AND isfinite(try_cast(mobility_count AS DOUBLE))"""
        c.execute('create or replace table raw_current as '+normalized)
        c.execute(f"""create or replace table keyed as select *,
          {identity('oc','orr','oci','olat','olon')} AS origin_raw_place_id,
          {identity('dc','drr','dci','dlat','dlon')} AS destination_raw_place_id from raw_current""")
        missing=c.execute('''select count(*) from keyed k left join mapping o on k.origin_raw_place_id=o.raw_place_id
          left join mapping d on k.destination_raw_place_id=d.raw_place_id where o.raw_place_id is null or d.raw_place_id is null''').fetchone()[0]
        assert missing==0,(dataset,'unmapped joins',missing)
        # Full ledger retains raw place IDs, allowing every new city flow to be traced back.
        c.execute('''create or replace table ledger as select k.year,k.tier,k.field,
          k.origin_raw_place_id,k.destination_raw_place_id,
          o.city_id origin_city_id,d.city_id destination_city_id,
          o.country_code origin_country,d.country_code destination_country,
          o.region origin_region,d.region destination_region,o.city origin_city,d.city destination_city,
          try_cast(o.city_latitude AS DOUBLE) origin_lat,try_cast(o.city_longitude AS DOUBLE) origin_lon,
          try_cast(d.city_latitude AS DOUBLE) destination_lat,try_cast(d.city_longitude AS DOUBLE) destination_lon,
          CASE WHEN o.analysis_ready<>'True' OR d.analysis_ready<>'True' THEN 'needs_review'
               WHEN o.city_id=d.city_id THEN 'within_city_after_merge'
               WHEN o.country_code=d.country_code THEN 'domestic_intercity' ELSE 'international' END event_status,
          CASE WHEN oc='' OR dc='' THEN 'original_country_missing'
               WHEN oc=dc THEN 'original_same_country' ELSE 'original_different_countries' END original_country_relation,
          k.flow AS flow,1 AS original_aggregate_rows
          from keyed k join mapping o on k.origin_raw_place_id=o.raw_place_id
            join mapping d on k.destination_raw_place_id=d.raw_place_id''')
        before=c.execute('select tier,sum(flow),count(*) from raw_current group by tier order by tier').fetchall()
        after=c.execute('select tier,sum(flow),sum(original_aggregate_rows) from ledger group by tier order by tier').fetchall()
        assert before==after,(dataset,before,after)
        export(c,'select * from ledger',OUT/'audit'/f'full_event_ledger_{dataset}.parquet',True)
        for status,name in [('within_city_after_merge','within_city_events'),('needs_review','needs_review_events')]:
            export(c,f"select * from ledger where event_status='{status}'",OUT/'audit'/f'{name}_{dataset}.parquet',True)
        clean='''WITH g AS (SELECT year,field,tier,origin_city_id,destination_city_id,event_status,sum(flow) mobility_count
          FROM ledger WHERE event_status IN ('international','domestic_intercity') GROUP BY ALL)
          SELECT o.city AS from_city,o.country_name AS from_country,o.country_code AS from_country_code,
          o.region AS from_region,try_cast(o.latitude AS DOUBLE) AS from_latitude,try_cast(o.longitude AS DOUBLE) AS from_longitude,
          d.city AS to_city,d.country_name AS to_country,d.country_code AS to_country_code,d.region AS to_region,
          try_cast(d.latitude AS DOUBLE) AS to_latitude,try_cast(d.longitude AS DOUBLE) AS to_longitude,
          g.year,g.field AS field_display_name,g.tier,g.origin_city_id AS from_city_id,g.destination_city_id AS to_city_id,
          g.mobility_count,g.event_status AS geography FROM g JOIN city_catalog o ON g.origin_city_id=o.city_id
          JOIN city_catalog d ON g.destination_city_id=d.city_id'''
        stem={'annual':'count_mobility_flow_annual_clean','career':'count_mobility_flow_career_clean','baseline':'mobility_flow_by_field_city_clean'}[dataset]
        c.execute('create or replace table clean_current as '+clean)
        export(c,'select * from clean_current',OUT/(stem+'.parquet'),True)
        export(c,'select * from clean_current',OUT/(stem+'.csv'))
        audit=c.execute('''select tier,event_status,count(*) ledger_rows,sum(flow) events,
            sum(original_aggregate_rows) original_rows from ledger group by tier,event_status order by tier,event_status''').fetchdf().to_dict('records')
        audits.append(dict(dataset=dataset,input_file=str((RAW/filename).relative_to(ROOT)),input_bytes=(RAW/filename).stat().st_size,
            input_sha256=sha(RAW/filename),output_csv=stem+'.csv',output_parquet=stem+'.parquet',
            totals_conserved_by_tier=True,before=[dict(tier=t,events=v,rows=n) for t,v,n in before],classification=audit))
        export(c,'select * from ledger where tier=\'top100pct\'',OUT/'audit'/f'top100_event_ledger_{dataset}.parquet',True)
        if dataset=='annual':
            export(c,"""select year,origin_country,destination_country,origin_region,destination_region,
             origin_city,destination_city,origin_lat,origin_lon,destination_lat,destination_lon,field,sum(flow) flow,
             origin_city_id AS origin,destination_city_id AS destination from ledger
             where tier='top100pct' and event_status in ('international','domestic_intercity') group by all""",OUT/'analysis/flow_top100.parquet',True)
        checkpoint.write_text(json.dumps(dict(city_crosswalk_sha256=sha(OUT/'city_crosswalk.csv'),dataset_audit=audits[-1]),ensure_ascii=False,indent=2),encoding='utf-8')
        print(dataset+': exact flow conservation confirmed for every tier',flush=True)
    # Descriptive tables use only the new annual top100pct intercity dataset.
    c.read_parquet(str(OUT/'analysis/flow_top100.parquet')).create_view('clean_flows')
    c.execute('''create or replace table margins as select geography,year,field,side,country,region,city_id,city,sum(flow) flow from (
       select case when origin_country=destination_country then 'domestic' else 'international' end geography,
         year,field,'outflow' side,origin_country country,origin_region region,origin city_id,origin_city city,flow from clean_flows
       union all select case when origin_country=destination_country then 'domestic' else 'international' end,
         year,field,'inflow',destination_country,destination_region,destination,destination_city,flow from clean_flows)
       group by all''')
    for geo in ['international','domestic']:
        export(c,f"select year,side,country,region,city_id,city,sum(flow) flow from margins where geography='{geo}' group by all order by year,side,country,city_id",OUT/'analysis'/f'{geo}_city_margins.csv')
    export(c,"select year,side,country,sum(flow) flow from margins where geography='international' group by all order by year,side,country",OUT/'analysis/country_annual_margins.csv')
    export(c,"""select year,side,country,count(distinct city_id) cities,sum(flow) flow from margins
       where geography='domestic' group by all order by year,side,country""",OUT/'analysis/domestic_country_city_counts.csv')
    for geo,groups in [('domestic',['year','side','country']),('international',['year','side'])]:
        group=','.join(groups)
        sql=f"""WITH a AS (select {group},city_id,sum(flow) flow from margins where geography='{geo}' group by all),
          r AS (select *,count(*) over(partition by {group}) n,
          row_number() over(partition by {group} order by flow,city_id) rank_asc from a)
          select {group},count(*) N,sum(flow) flow,sum(flow*flow)/sum(flow)^2 HHI,
          sum(flow)^2/sum(flow*flow) N_eff,sum(flow)^2/sum(flow*flow)/count(*) normalized_N_eff,
          sum((2*rank_asc-n-1)*flow)/(count(*)*sum(flow)) Gini from r group by {group} order by {group}"""
        export(c,sql,OUT/'analysis'/f'{geo}_city_metrics.csv')
    (OUT/'audit/event_accounting.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
    files={str(p.relative_to(OUT)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.glob('*.csv')}
    files.update({str(p.relative_to(OUT)):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in OUT.glob('*.parquet')})
    manifest=dict(created_utc=datetime.now(timezone.utc).isoformat(),years=[1998,2025],source_inputs=audits,
        city_crosswalk_sha256=sha(OUT/'city_crosswalk.csv'),output_files=files,
        tiers='Each tier retained and checked separately; overlapping tiers must never be added together',
        output_scope='Confirmed intercity events only in clean files; within-city and unresolved records retained separately in audit ledgers',
        reference_geography='Fixed 2026-10-20 GeoNames; fixed US Census 2024 places; documented country municipality and parent rules',
        source_preservation='All source CSVs and existing manuscript figures left unchanged')
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    c.close();print('All three cleaned datasets and audit ledgers complete',flush=True)


if __name__=='__main__':main()
