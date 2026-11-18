"""Prepare audited aggregates and field-labelled individual paths for validation.

All public-facing outputs are aggregates. Temporary DuckDB contains person keys
and stays under tmp/, outside the manuscript and report deliverables.
"""
from pathlib import Path
import os, sys, json, time, argparse, importlib.util, hashlib
for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[name] = '2'
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tmp/nhb_fig2_python_deps')]
import pandas as pd
import duckdb

OUT = ROOT/'outputs/mechanism_validation_20261030'
PRIVATE = ROOT/'tmp/mechanism_validation_20261030'
CLEAN = ROOT/'data/processed/mobility_city_harmonized_20261020'
SOURCE = ROOT/'data/input/mobility/openalex_mobility_rates/author_year_primary_location.parquet'
DOMAINS = ['Physical Sciences','Life Sciences','Health Sciences','Social Sciences']
def q(p): return "'"+str(p).replace("'","''")+"'"
def log(s): print(time.strftime('%H:%M:%S'), s, flush=True)
def save(name,obj): (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def copy(c,sql,name): c.execute(f'COPY ({sql}) TO {q(OUT/name)} (FORMAT PARQUET,COMPRESSION ZSTD)')

def setup(c):
    mapping=pd.read_csv(ROOT/'outputs/fig2_6_recalculation_20261023_180757/source_data/Fig6/Fig6_field_domain_mapping.csv')
    c.register('field_domains',mapping[['field','domain']])
    sample=pd.read_csv(ROOT/'figures/v3/source_data/Fig4_country_concentration_trends.csv')[['country']]
    common=pd.read_csv(ROOT/'figures/v4/source_data/Fig6_country_year_changes.csv')[['country']].drop_duplicates()
    assert len(sample)==76 and len(common)==45
    c.register('sample76',sample); c.register('common45',common)
    sample.to_csv(OUT/'sample76.csv',index=False);common.to_csv(OUT/'common45.csv',index=False)
    mapping.to_csv(OUT/'field_domain_mapping.csv',index=False)

def canonical(c):
    if (OUT/'canonical_prepared.json').exists(): return
    log('Aggregate canonical cleaned events, with exactly one field-domain assignment per event')
    c.execute(f'''CREATE OR REPLACE TEMP TABLE f AS SELECT year, floor((year-1998)/7)::INT p,
      origin_country oc,destination_country country,origin o,destination d,flow,
      coalesce(m.domain,'Unspecified') AS domain
      FROM read_parquet({q(CLEAN/'analysis/flow_top100.parquet')}) x
      LEFT JOIN field_domains m ON x.field=m.field''')
    accounts=c.sql("SELECT CASE WHEN oc=country THEN 'domestic' ELSE 'international' END geography,sum(flow) events FROM f GROUP BY 1").df()
    assert accounts.events.sum()==29703224
    accounts.to_csv(OUT/'canonical_event_accounting.csv',index=False)
    c.execute("CREATE OR REPLACE TEMP TABLE expanded AS SELECT * FROM f UNION ALL SELECT year,p,oc,country,o,d,flow,'All' AS domain FROM f")
    copy(c,"SELECT p,domain,oc,country,d,sum(flow) flow FROM expanded WHERE oc<>country GROUP BY ALL",'international_destination_od.parquet')
    copy(c,"SELECT p,domain,country,d city,sum(flow) flow FROM expanded WHERE oc<>country GROUP BY ALL",'international_city_inflow.parquet')
    # Partners count distinct cities, combining both directions, within a period.
    copy(c,"""SELECT p,domain,country,city,count(DISTINCT partner) partners FROM (
      SELECT p,domain,country,o city,d partner FROM expanded WHERE oc=country
      UNION ALL SELECT p,domain,country,d city,o partner FROM expanded WHERE oc=country)
      GROUP BY ALL""",'domestic_period_partners.parquet')
    copy(c,"""SELECT year,domain,country,city,sum(flow) strength FROM (
      SELECT year,domain,country,o city,flow FROM expanded WHERE oc=country
      UNION ALL SELECT year,domain,country,d city,flow FROM expanded WHERE oc=country)
      GROUP BY ALL""",'domestic_domain_city_year.parquet')
    copy(c,"SELECT year,domain,oc,country,sum(flow) flow FROM expanded WHERE oc<>country GROUP BY ALL",'international_domain_country_od_year.parquet')
    c.execute('DROP TABLE expanded');c.execute('DROP TABLE f')
    save('canonical_prepared.json',{'events':accounts.to_dict('records'),'no_manuscript_changes':True})
    log('Canonical event total reconciled: 29,703,224')

def unique_stock(c):
    if (OUT/'stock_prepared.json').exists(): return
    log('Count distinct active author-years in harmonized primary-affiliation cities')
    c.execute(f"CREATE OR REPLACE TEMP TABLE cw_stock AS SELECT * FROM read_csv({q(CLEAN/'city_crosswalk.csv')},header=true,all_varchar=true)")
    c.execute("""CREATE OR REPLACE TEMP TABLE gm_stock AS SELECT raw_country original_country,
      try_cast(source_geonameid AS BIGINT) gid,min(city_id) city,min(country_code) country
      FROM cw_stock WHERE analysis_ready='True' AND try_cast(source_geonameid AS BIGINT) IS NOT NULL
      AND raw_country IS NOT NULL GROUP BY 1,2 HAVING count(DISTINCT city_id)=1 AND count(DISTINCT country_code)=1""")
    # Audit sample is explicitly a deterministic 1% of authors, not a claim that
    # a sample audit proves full-table uniqueness. Exact distinct keys below
    # prevent repeated rows within a city/year/domain increasing its stock.
    audit=c.sql(f"""SELECT count(*) author_year_keys,sum(CASE WHEN n>1 THEN 1 ELSE 0 END) duplicate_keys,
      max(n) maximum_rows FROM(SELECT author_id,year,count(*) n
      FROM read_parquet({q(SOURCE)}) WHERE year BETWEEN 1998 AND 2025 AND hash(author_id)%100=0 GROUP BY 1,2)""").df().to_dict('records')[0]
    c.execute(f"""CREATE OR REPLACE TEMP TABLE stock_mapped AS SELECT p.author_id,p.year,
      floor((p.year-1998)/7)::INT period,g.country,g.city,coalesce(m.domain,'Unspecified') AS domain
      FROM read_parquet({q(SOURCE)}) p
      LEFT JOIN gm_stock g ON p.country_code=g.original_country
       AND try_cast(regexp_extract(p.city_key,'^gn:([0-9]+)$',1) AS BIGINT)=g.gid
      LEFT JOIN field_domains m ON p.field_display_name=m.field
      WHERE p.year BETWEEN 1998 AND 2025""")
    mapping=c.sql('SELECT count(*) AS rows,sum((city IS NOT NULL)::INT) mapped_rows FROM stock_mapped').df().to_dict('records')[0]
    copy(c,"""SELECT period p,domain,country,city,
      count(DISTINCT (author_id,year))/7.0 mass FROM stock_mapped WHERE city IS NOT NULL GROUP BY ALL
      UNION ALL SELECT period p,'All' AS domain,country,city,
      count(DISTINCT (author_id,year))/7.0 mass FROM stock_mapped WHERE city IS NOT NULL GROUP BY ALL""",'primary_author_year_stock.parquet')
    # Early scientific-activity centroid is fixed before evaluation, and its
    # approximation to true origin-city distance is documented explicitly.
    c.execute(f"CREATE OR REPLACE TEMP TABLE catalog AS SELECT * FROM read_csv({q(CLEAN/'cities.csv')},header=true)")
    copy(c,f"""SELECT s.country,sum(s.mass*cos(radians(c.latitude))*cos(radians(c.longitude)))/sum(s.mass) x,
      sum(s.mass*cos(radians(c.latitude))*sin(radians(c.longitude)))/sum(s.mass) y,
      sum(s.mass*sin(radians(c.latitude)))/sum(s.mass) z FROM read_parquet({q(OUT/'primary_author_year_stock.parquet')}) s
      JOIN catalog c ON s.city=c.city_id WHERE s.p=0 AND s.domain='All'
      AND c.latitude BETWEEN -90 AND 90 AND c.longitude BETWEEN -180 AND 180 GROUP BY s.country""",'fixed_origin_centroids.parquet')
    c.execute('DROP TABLE stock_mapped')
    save('stock_prepared.json',{'source':str(SOURCE),'audit_1pct_authors':audit,'mapping':mapping,
      'mass':'Distinct author-year pairs at harmonized annual primary-affiliation city, divided by seven; primary-location activity, not population or all employed scientists.',
      'distance':'Fixed 1998-2004 primary-author-activity-weighted origin-country centroid to actual destination-city coordinates; approximate source-country distance.'})
    log('Independent primary-affiliation author-year stock complete')

def micro(c):
    if (OUT/'micro_prepared.json').exists(): return
    spec=importlib.util.spec_from_file_location('previous_pathways',ROOT/'scripts/reports/extend_individual_pathways_20261030.py')
    previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous);previous.OUT=OUT
    if 'arrivals' not in [x[0] for x in c.sql('SHOW TABLES').fetchall()]:
        raw,accounting=previous.reconstruct(c)
    else:
        raw=30335255
        accounting=c.sql("SELECT CASE WHEN NOT verified THEN 'unresolved' WHEN oc<>dc THEN 'international' ELSE 'domestic' END category,count(*) records FROM events GROUP BY 1").df()
    log('Aggregate individual arrival pathways by entry field/domain and country')
    parts=[]
    for horizon in [3,5]:
        for maxgap in [0,1,2]:
            # Symmetric target definition for observation-gap sensitivity.
            extra='' if maxgap==0 else f'AND a.obs_gap<={maxgap} AND (a.next_year IS NULL OR a.next_year>a.year+{horizon} OR a.next_gap<={maxgap})'
            z=c.sql(f"""SELECT a.dc country,coalesce(m.domain,'Unspecified') AS domain,
              CASE WHEN a.year<=2014 THEN 'early' ELSE 'late' END cohort,
              CASE WHEN next_year<=a.year+{horizon} AND NOT next_verified THEN 'unresolved_next'
              WHEN next_year<=a.year+{horizon} AND next_country=dc THEN 'domestic'
              WHEN next_year<=a.year+{horizon} AND next_country=oc THEN 'previous_origin_return'
              WHEN next_year<=a.year+{horizon} THEN 'third_country'
              ELSE 'no_recorded_intercity_change' END path,count(*) records
              FROM arrivals a JOIN sample76 s ON a.dc=s.country
              LEFT JOIN field_domains m ON a.field=m.field
              WHERE a.last_year>=a.year+{horizon} {extra} GROUP BY ALL""").df()
            z['horizon']=horizon;z['max_observation_gap']=maxgap;parts.append(z)
    allroutes=pd.concat(parts,ignore_index=True)
    allroutes.to_csv(OUT/'domain_country_arrival_paths.csv',index=False)
    old=pd.read_csv(ROOT/'outputs/literature_pathway_extension_20261030/pooled_five_year_path_counts.csv')
    total=allroutes[(allroutes.horizon==5)&(allroutes.max_observation_gap==0)].records.sum()
    assert total==old.records.sum()==1810380
    # Comparable-window denominator quantifies contribution to domestic flows;
    # it does not divide a five-year cohort subset by the 28-year global total.
    contribution=c.sql("""WITH target AS(SELECT a.dc country,a.next_year AS year,
      coalesce(m.domain,'Unspecified') AS domain,count(*) target_events FROM arrivals a
      JOIN sample76 s ON a.dc=s.country LEFT JOIN field_domains m ON a.next_field=m.field
      WHERE a.last_year>=a.year+5 AND a.next_year<=a.year+5 AND a.next_verified
      AND a.next_country=a.dc GROUP BY ALL),denominator AS(
      SELECT e.dc country,e.year,coalesce(m.domain,'Unspecified') AS domain,count(*) all_domestic_events
      FROM events e JOIN sample76 s ON e.dc=s.country LEFT JOIN field_domains m ON e.field=m.field
      WHERE e.verified AND e.oc=e.dc AND e.year BETWEEN 2012 AND 2023 GROUP BY ALL)
      SELECT d.*,coalesce(t.target_events,0) target_events FROM denominator d LEFT JOIN target t USING(country,year,domain)""").df()
    contribution.to_csv(OUT/'domain_country_year_continuation_contribution.csv',index=False)
    # Directly observed reverse chain D -> I, not multiplication of aggregate edges.
    reverse=c.sql("""WITH p AS(SELECT *,lag(oc) OVER w previous_oc,
      lag(dc) OVER w previous_dc,lag(year) OVER w previous_event_year,
      lag(verified) OVER w previous_verified,lag(d) OVER w previous_destination
      FROM events WINDOW w AS(PARTITION BY author_id ORDER BY year))
      SELECT dc country,coalesce(m.domain,'Unspecified') AS domain,count(*) international_entries,
      sum((previous_verified AND previous_oc=previous_dc AND previous_dc=oc
        AND previous_destination=o AND year-previous_event_year<=5)::INT) preceded_by_domestic_within5
      FROM p LEFT JOIN field_domains m ON p.field=m.field
      WHERE verified AND oc<>dc AND year BETWEEN 2012 AND 2018 GROUP BY ALL""").df()
    # In reverse chains the organising domestic network belongs to the SOURCE.
    reverse.to_csv(OUT/'all_destination_reverse_chain_diagnostic.csv',index=False)
    reverse_source=c.sql("""WITH p AS(SELECT *,lag(oc) OVER w previous_oc,
      lag(dc) OVER w previous_dc,lag(year) OVER w previous_event_year,
      lag(verified) OVER w previous_verified,lag(d) OVER w previous_destination
      FROM events WINDOW w AS(PARTITION BY author_id ORDER BY year))
      SELECT oc country,coalesce(m.domain,'Unspecified') AS domain,count(*) international_departures,
      sum((previous_verified AND previous_oc=previous_dc AND previous_dc=oc
        AND previous_destination=o AND year-previous_event_year<=5)::INT) preceded_by_domestic_within5
      FROM p JOIN sample76 s ON p.oc=s.country LEFT JOIN field_domains m ON p.field=m.field
      WHERE verified AND oc<>dc AND year BETWEEN 2012 AND 2018 GROUP BY ALL""").df()
    reverse_source.to_csv(OUT/'domain_source_country_domestic_to_international.csv',index=False)
    save('micro_prepared.json',{'raw_changes':int(raw),'unreconciled_raw_difference':30335569-int(raw),
      'micro_event_accounting':accounting.to_dict('records'),'adequately_observed_entry_records':int(total),
      'person_ids_exported':False,'five_year_routes_reproduced':True,
      'reverse_chain':'Previous observed intercity event domestic in departure country, within five years; conditional on recorded international departure, not a domestic-to-international transition hazard.',
      'entry_field':'Field recorded at international entry. Matched HHI uses field recorded at next domestic move; these are distinct assignments.'})
    log('Pathway and reverse-chain aggregates complete')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['aggregate','micro','all'],default='all');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);PRIVATE.mkdir(parents=True,exist_ok=True)
    if not (OUT/'analysis_plan.json').exists():
        save('analysis_plan.json',{'date':'2026-10-30','purpose':'Exploratory validation of cross-scale process hypotheses; analysis choices fixed before fitting this extension, not a preregistration.',
          'canonical_sample':'29,703,224 harmonized events; geography-verified microdata subset separately accounted.',
          'gravity':'Conditional destination-choice Poisson/multinomial gravity. Train 2005-2018; hold out 2019-2025. Candidate cities have positive lagged distinct author-year mass and valid coordinates. Condition on source-country/destination-country/period totals.',
          'models':['M0 lagged mass + approximate geographic distance','M1 M0 + lagged international city inflow','M2 M1 + lagged domestic partner-city count'],
          'primary_contrast':'M2 versus M1 in held-out period; equal-country fitting and country-level validation; M1 vs M0 documents importance of international history.',
          'domains':'Four prespecified OpenAlex domains; same45-country sample for domain comparisons. Pooled model76 countries. Compare effects directly across matched countries, not significant vs nonsignificant.',
          'pathways':'Entry2012-2018; first next observed event within3/5 years; sufficient later publication observation; same-subject entry and domestic continuation comparison.',
          'matched_reference':'Reuse strictly matched country/origin/year/field/career/followup risk sets. Stratify by next-move field domain; exact finite conditional-resampling HHI expectation. Risk sets may overlap; not one global label permutation.',
          'inference':'Country bootstrap intervals, paired country contrasts; sign-test family Holm across4 domains; no causal claims.',
          'unknown_fields':'Retain in pooled accounting, exclude from named-domain comparisons; report exclusions.',
          'scope':'No edits to manuscript or final figures; do not force T1-T4 or mechanism-positive conclusions.'})
    c=duckdb.connect(str(PRIVATE/'private_analysis.duckdb'))
    c.execute("SET threads=4; SET memory_limit='5GB'; SET preserve_insertion_order=false")
    c.execute(f"SET temp_directory={q(PRIVATE/'spill')}")
    setup(c)
    if args.stage in ['aggregate','all']: canonical(c);unique_stock(c)
    if args.stage in ['micro','all']: micro(c)
    save('preparation_runtime.json',{'duckdb':duckdb.__version__,'pandas':pd.__version__,
      'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    c.close();log('Preparation finished')
if __name__=='__main__': main()
