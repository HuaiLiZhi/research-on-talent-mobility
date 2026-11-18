"""Extract distinct source-place instances from all three mobility CSV inputs."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb

OUT=ROOT/'data/processed/mobility_city_harmonized_20261020'
RAW=ROOT/'data/input/mobility/openalex'
NAMES=['count_mobility_flow_annual.csv','count_mobility_flow_career.csv','mobility_flow_by_field_clean.csv']


def quote(value):return "'"+str(value).replace("'","''")+"'"


def endpoint(prefix):
    return f"""upper(trim(coalesce({prefix}_country_code,''))) AS country,
       lower(trim(coalesce({prefix}_region,''))) AS region,
       lower(trim(coalesce({prefix}_city,''))) AS city,
       round(try_cast({prefix}_latitude AS DOUBLE),5) AS latitude,
       round(try_cast({prefix}_longitude AS DOUBLE),5) AS longitude"""


def identity(country='country',region='region',city='city',lat='latitude',lon='longitude'):
    return f"md5(coalesce({country},'')||chr(31)||coalesce({region},'')||chr(31)||coalesce({city},'')||chr(31)||coalesce(cast({lat} AS VARCHAR),'')||chr(31)||coalesce(cast({lon} AS VARCHAR),''))"


if __name__=='__main__':
    (OUT/'audit').mkdir(parents=True,exist_ok=True)
    con=duckdb.connect(str(OUT/'audit/place_preparation.duckdb'))
    con.execute("SET threads=4;SET memory_limit='3GB'")
    con.execute('CREATE OR REPLACE TABLE instances(country VARCHAR,region VARCHAR,city VARCHAR,latitude DOUBLE,longitude DOUBLE,source_file VARCHAR)')
    for name in NAMES:
        print('Reading geographic fields: '+name,flush=True)
        tier="AND tier='top100pct'" if name.startswith('count_') else ''
        sql=f"""WITH r AS (SELECT * FROM read_csv({quote(RAW/name)},header=true,all_varchar=true)
          WHERE try_cast(year AS INTEGER) BETWEEN 1998 AND 2025 {tier}
            AND try_cast(mobility_count AS DOUBLE)>0),
          p AS (SELECT {endpoint('from')} FROM r UNION ALL SELECT {endpoint('to')} FROM r)
          SELECT DISTINCT *,{quote(name)} AS source_file FROM p"""
        con.execute('INSERT INTO instances '+sql)
        print('Distinct geographic instances in file: '+str(con.execute('SELECT count(*) FROM instances WHERE source_file=?',[name]).fetchone()[0]),flush=True)
    con.execute(f"""COPY (SELECT {identity()} AS raw_place_id,country,region,city,latitude,longitude,
        string_agg(DISTINCT source_file,';') AS source_files FROM instances
        GROUP BY country,region,city,latitude,longitude ORDER BY country,region,city,latitude,longitude)
        TO {quote(OUT/'audit/raw_place_instances.csv')} (FORMAT CSV,HEADER TRUE)""")
    print('All raw place instances: '+str(con.execute(f"SELECT count(*) FROM read_csv({quote(OUT/'audit/raw_place_instances.csv')},header=true)").fetchone()[0]),flush=True)
    con.close()
