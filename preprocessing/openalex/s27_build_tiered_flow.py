#!/usr/bin/env python3
"""Tiered mobility flow counts: city-to-city moves counted per impact tier
(top2/10/20/50/100%), separately for CAREER and ANNUAL c-score.

For a move at year t, the author's tier is taken at year t-1 (no look-ahead).
tier='top100pct' means all movers (no impact filter).

Outputs (CSV):
  openalex_mobility_deduped/count_mobility_flow_career.csv
  openalex_mobility_deduped/count_mobility_flow_annual.csv
columns: from_city, from_country, from_region, from_country_code, from_latitude,
         from_longitude, to_city, to_country, to_region, to_country_code,
         to_latitude, to_longitude, year, field_display_name, tier, mobility_count
"""
from __future__ import annotations
import argparse, os, time
import duckdb

DED = "/data2/openAlex/openalex_mobility_deduped"
SRC = os.path.join(DED, "detail_author_work_locations.parquet")
INST = "/data2/openAlex/openalex_mobility_author_entity_deduped/institutions.csv"
CAREER = "/data2/openAlex/openalex_author_impact_inputs/author_year_cscore_career.parquet"
ANNUAL = "/data2/openAlex/openalex_author_impact_inputs/author_year_cscore_annual.parquet"
TMP = "/data2/openAlex/duckdb_tmp"
Y0, Y1 = 1900, 2026
TIERS = [("top2pct", 0.02), ("top10pct", 0.10), ("top20pct", 0.20), ("top50pct", 0.50), ("top100pct", None)]

def log(m): print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=90)
    a = ap.parse_args()
    os.makedirs(TMP, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=%d" % a.threads)
    con.execute("SET memory_limit='180GB'")
    con.execute("SET temp_directory='%s'" % TMP)
    con.execute("SET preserve_insertion_order=false")
    t0 = time.time()

    log("institutions + citymap")
    con.execute(f"""CREATE TEMP TABLE inst AS
      SELECT id, geo_city, geo_geonames_city_id, geo_region, geo_country_code, geo_country,
             try_cast(geo_latitude AS DOUBLE) lat, try_cast(geo_longitude AS DOUBLE) lon
      FROM read_csv('{INST}', header=true, all_varchar=true)""")
    con.execute("""CREATE TEMP TABLE inst_city AS
      SELECT CASE WHEN coalesce(geo_geonames_city_id,'')<>'' THEN 'gn:'||geo_geonames_city_id
                  WHEN coalesce(geo_city,'')<>'' THEN 'cc:'||coalesce(geo_country_code,'')||'|'||lower(geo_city)
                  ELSE NULL END AS city_key, geo_city AS city, geo_region AS region, lat, lon FROM inst""")
    con.execute("""CREATE TEMP TABLE citymap AS
      WITH r AS (SELECT city_key, region, count(*) c FROM inst_city WHERE region IS NOT NULL AND region<>'' GROUP BY city_key, region),
           rbest AS (SELECT city_key, arg_max(region,c) region FROM r GROUP BY city_key),
           c AS (SELECT city_key, city, count(*) c FROM inst_city WHERE city IS NOT NULL AND city<>'' GROUP BY city_key, city),
           cbest AS (SELECT city_key, arg_max(city,c) city FROM c GROUP BY city_key)
      SELECT ic.city_key, cbest.city AS city_disp, rbest.region,
             median(ic.lat) FILTER (WHERE ic.lat BETWEEN -90 AND 90 AND ic.lat<>0) lat,
             median(ic.lon) FILTER (WHERE ic.lon BETWEEN -180 AND 180 AND ic.lon<>0) lon
      FROM inst_city ic LEFT JOIN rbest USING(city_key) LEFT JOIN cbest USING(city_key)
      GROUP BY ic.city_key, cbest.city, rbest.region""")

    log("per-work clean")
    con.execute(f"""CREATE TEMP TABLE mc AS
      SELECT w.author_id, w.work_id, try_cast(w.publication_year AS INTEGER) AS year,
             w.institution_id, w.field_id, w.field_display_name
      FROM read_parquet('{SRC}') w
      WHERE try_cast(w.publication_year AS INTEGER) BETWEEN {Y0} AND {Y1}""")
    log("mc rows=%d %.0fs" % (con.execute("select count(*) from mc").fetchone()[0], time.time()-t0))

    log("primary institution + dominant field")
    con.execute("""CREATE TEMP TABLE prim AS
      SELECT author_id, year, institution_id AS primary_institution_id FROM (
        SELECT author_id, year, institution_id, count(DISTINCT work_id) w,
               row_number() OVER (PARTITION BY author_id, year
                                  ORDER BY count(DISTINCT work_id) DESC, institution_id) rn
        FROM mc WHERE coalesce(institution_id,'')<>'' GROUP BY author_id, year, institution_id) WHERE rn=1""")
    con.execute("""CREATE TEMP TABLE author_dom AS
      SELECT author_id, arg_max(field_id, tot) AS dom_field, arg_max(fname, tot) AS dom_field_name
      FROM (SELECT author_id, field_id, any_value(field_display_name) fname,
                   count(DISTINCT work_id) tot FROM mc GROUP BY author_id, field_id)
      GROUP BY author_id""")
    log("prim/dom done %.0fs" % (time.time()-t0))

    log("author-year primary city + tier (own year)")
    con.execute(f"""CREATE TEMP TABLE ayc AS
      SELECT p.author_id, p.year,
             coalesce(cm.city_disp, i.geo_city) AS city,
             i.geo_country_code AS country_code, i.geo_country AS country_name,
             coalesce(nullif(i.geo_region,''), cm.region) AS region,
             coalesce(cm.lat, CASE WHEN i.lat BETWEEN -90 AND 90 AND i.lat<>0 THEN i.lat END) AS lat,
             coalesce(cm.lon, CASE WHEN i.lon BETWEEN -180 AND 180 AND i.lon<>0 THEN i.lon END) AS lon,
             cm.city_key AS city_key,
             c.pct_rank AS pct_career, n.pct_rank AS pct_annual
      FROM prim p JOIN inst i ON p.primary_institution_id=i.id
      LEFT JOIN citymap cm ON cm.city_key = CASE
          WHEN coalesce(i.geo_geonames_city_id,'')<>'' THEN 'gn:'||i.geo_geonames_city_id
          WHEN coalesce(i.geo_city,'')<>'' THEN 'cc:'||coalesce(i.geo_country_code,'')||'|'||lower(i.geo_city)
          ELSE NULL END
      LEFT JOIN read_parquet('{CAREER}') c ON p.author_id=c.author_id AND p.year=c.year
      LEFT JOIN read_parquet('{ANNUAL}') n ON p.author_id=n.author_id AND p.year=n.year""")
    log("ayc rows=%d %.0fs" % (con.execute("select count(*) from ayc").fetchone()[0], time.time()-t0))

    log("moves")
    con.execute("""
      CREATE TEMP TABLE moves AS
      WITH seq AS (
        SELECT author_id, year, city, country_code, country_name, region, lat, lon, city_key,
               lag(city) OVER w AS p_city, lag(city_key) OVER w AS p_key,
               lag(country_code) OVER w AS p_cc, lag(country_name) OVER w AS p_country,
               lag(region) OVER w AS p_region, lag(lat) OVER w AS p_lat, lag(lon) OVER w AS p_lon,
               lag(pct_career) OVER w AS pct_career_tm1, lag(pct_annual) OVER w AS pct_annual_tm1
        FROM ayc WHERE city_key IS NOT NULL
        WINDOW w AS (PARTITION BY author_id ORDER BY year)
      )
      SELECT author_id, year,
             p_city AS from_city, p_country AS from_country, p_region AS from_region,
             p_cc AS from_country_code, p_lat AS from_latitude, p_lon AS from_longitude,
             city AS to_city, country_name AS to_country, region AS to_region,
             country_code AS to_country_code, lat AS to_latitude, lon AS to_longitude,
             pct_career_tm1, pct_annual_tm1
      FROM seq
      WHERE p_city IS NOT NULL AND city IS NOT NULL
        AND (p_key <> city_key OR coalesce(p_cc,'') <> coalesce(country_code,''))
    """)
    con.execute("CREATE TEMP TABLE mv AS SELECT m.*, d.dom_field_name AS field_display_name FROM moves m JOIN author_dom d USING(author_id)")
    con.execute("DROP TABLE moves; DROP TABLE ayc")
    log("moves rows=%d %.0fs" % (con.execute("select count(*) from mv").fetchone()[0], time.time()-t0))

    GROUP = "from_city, from_country, from_region, from_country_code, from_latitude, from_longitude, to_city, to_country, to_region, to_country_code, to_latitude, to_longitude, year, field_display_name"
    def tiered(pct_col, out):
        parts = []
        for name, thr in TIERS:
            if thr is None:
                where = "1=1"
            else:
                where = f"{pct_col} IS NOT NULL AND {pct_col} <= {thr}"
            parts.append(f"SELECT {GROUP}, '{name}' AS tier, COUNT(DISTINCT author_id) AS mobility_count FROM mv WHERE {where} GROUP BY {GROUP}")
        sql = " UNION ALL ".join(parts)
        con.execute(f"COPY ({sql}) TO '{out}' (HEADER, DELIMITER ',')")
        log("wrote %s rows=%d" % (out, con.execute(f"select count(*) from read_csv_auto('{out}', header=true)").fetchone()[0]))

    tiered("pct_career_tm1", os.path.join(DED, "count_mobility_flow_career.csv"))
    tiered("pct_annual_tm1", os.path.join(DED, "count_mobility_flow_annual.csv"))
    log("ALL DONE %.0fs" % (time.time()-t0))
    con.close()

if __name__ == "__main__":
    raise SystemExit(main())
