import duckdb, time, os

DED="/data2/openAlex/openalex_mobility_deduped"
SRC=os.path.join(DED,"detail_author_work_locations.parquet")
INST="/data2/openAlex/openalex_mobility_author_entity_deduped/institutions.csv"
TMP="/data2/openAlex/duckdb_tmp"
Y0,Y1=1900,2026

def log(m): print("[%s] %s"%(time.strftime("%H:%M:%S"),m),flush=True)
con=duckdb.connect()
con.execute("SET threads=90"); con.execute("SET memory_limit='180GB'")
con.execute("SET temp_directory='%s'"%TMP); con.execute("SET preserve_insertion_order=false")
os.makedirs(TMP,exist_ok=True)
t0=time.time()

log("institutions + citymap")
con.execute(f"""CREATE TEMP TABLE inst AS
 SELECT id, ror, display_name, type, country_code, geo_city, geo_geonames_city_id,
        geo_region, geo_country_code, geo_country,
        try_cast(geo_latitude AS DOUBLE) lat, try_cast(geo_longitude AS DOUBLE) lon
 FROM read_csv('{INST}', header=true, all_varchar=true)""")
con.execute("""CREATE TEMP TABLE inst_city AS
 SELECT CASE WHEN coalesce(geo_geonames_city_id,'')<>'' THEN 'gn:'||geo_geonames_city_id
             WHEN coalesce(geo_city,'')<>'' THEN 'cc:'||coalesce(geo_country_code,'')||'|'||lower(geo_city)
             ELSE NULL END AS city_key, geo_city city, geo_region region, lat, lon FROM inst""")
con.execute("""CREATE TEMP TABLE citymap AS
 WITH r AS (SELECT city_key, region, count(*) c FROM inst_city WHERE region IS NOT NULL AND region<>'' GROUP BY city_key, region),
      rbest AS (SELECT city_key, arg_max(region,c) region FROM r GROUP BY city_key),
      c AS (SELECT city_key, city, count(*) c FROM inst_city WHERE city IS NOT NULL AND city<>'' GROUP BY city_key, city),
      cbest AS (SELECT city_key, arg_max(city,c) city FROM c GROUP BY city_key)
 SELECT ic.city_key, cbest.city city_disp, rbest.region,
        median(ic.lat) FILTER (WHERE ic.lat BETWEEN -90 AND 90 AND ic.lat<>0) lat,
        median(ic.lon) FILTER (WHERE ic.lon BETWEEN -180 AND 180 AND ic.lon<>0) lon
 FROM inst_city ic LEFT JOIN rbest USING(city_key) LEFT JOIN cbest USING(city_key)
 GROUP BY ic.city_key, cbest.city, rbest.region""")
log("citymap done %.0fs"%(time.time()-t0))

log("clean per-work detail")
con.execute(f"""CREATE TEMP TABLE mc AS
 SELECT w.author_id, w.work_id, try_cast(w.publication_year AS INTEGER) AS year,
        CASE WHEN coalesce(w.institution_id,'')<>'' THEN 'institution' ELSE 'country' END AS geo_level,
        w.country_code, w.country_name, w.geo_city,
        lower(strip_accents(w.geo_city)) AS city_norm,
        CASE WHEN coalesce(i.geo_geonames_city_id,'')<>'' THEN i.geo_geonames_city_id ELSE NULL END AS city_geonames_id,
        CASE WHEN coalesce(i.geo_geonames_city_id,'')<>'' THEN 'gn:'||i.geo_geonames_city_id
             WHEN coalesce(w.geo_city,'')<>'' THEN 'cc:'||coalesce(w.country_code,'')||'|'||lower(w.geo_city)
             ELSE NULL END AS city_key,
        coalesce(nullif(w.geo_region,''), cm.region) AS geo_region,
        CASE WHEN cm.lat IS NOT NULL THEN cm.lat
             WHEN try_cast(w.geo_latitude AS DOUBLE) BETWEEN -90 AND 90 AND try_cast(w.geo_latitude AS DOUBLE)<>0
                  THEN try_cast(w.geo_latitude AS DOUBLE) ELSE NULL END AS geo_latitude,
        CASE WHEN cm.lon IS NOT NULL THEN cm.lon
             WHEN try_cast(w.geo_longitude AS DOUBLE) BETWEEN -180 AND 180 AND try_cast(w.geo_longitude AS DOUBLE)<>0
                  THEN try_cast(w.geo_longitude AS DOUBLE) ELSE NULL END AS geo_longitude,
        w.institution_id, w.field_id, w.field_display_name
 FROM read_parquet('{SRC}') w
 LEFT JOIN inst i ON w.institution_id=i.id
 LEFT JOIN citymap cm ON cm.city_key = CASE
     WHEN coalesce(i.geo_geonames_city_id,'')<>'' THEN 'gn:'||i.geo_geonames_city_id
     WHEN coalesce(w.geo_city,'')<>'' THEN 'cc:'||coalesce(w.country_code,'')||'|'||lower(w.geo_city)
     ELSE NULL END
 WHERE try_cast(w.publication_year AS INTEGER) BETWEEN {Y0} AND {Y1}""")
log("mc rows=%d %.0fs"%(con.execute("select count(*) from mc").fetchone()[0],time.time()-t0))

log("primary institution per (author, year)")
con.execute("""CREATE TEMP TABLE prim AS
 SELECT author_id, year, institution_id primary_institution_id FROM (
   SELECT author_id, year, institution_id, count(DISTINCT work_id) w,
          row_number() OVER (PARTITION BY author_id, year
                             ORDER BY count(DISTINCT work_id) DESC, institution_id) rn
   FROM mc WHERE coalesce(institution_id,'')<>'' GROUP BY author_id, year, institution_id) WHERE rn=1""")

SELECT_COLS = """country_code, country_name, geo_city, city_norm, city_geonames_id, city_key,
        geo_region, geo_latitude, geo_longitude, geo_level, year, field_id,
        any_value(field_display_name) field_display_name,
        COUNT(DISTINCT author_id) author_count, COUNT(DISTINCT work_id) works_count"""
GROUP_COLS = """country_code, country_name, geo_city, city_norm, city_geonames_id, city_key,
        geo_region, geo_latitude, geo_longitude, geo_level, year, field_id"""

jobs = []
_clean_pq = os.path.join(DED, "count_stock_city_field_year_clean.parquet")
if not os.path.exists(_clean_pq):
    jobs.append(("count_stock_city_field_year_clean",
                 f"SELECT {SELECT_COLS} FROM mc GROUP BY {GROUP_COLS}"))
jobs.append(("count_stock_city_field_year_clean_primary",
    """SELECT mc.country_code, mc.country_name, mc.geo_city, mc.city_norm,
              mc.city_geonames_id, mc.city_key, mc.geo_region, mc.geo_latitude,
              mc.geo_longitude, mc.geo_level, mc.year, mc.field_id,
              any_value(mc.field_display_name) AS field_display_name,
              COUNT(DISTINCT mc.author_id) AS author_count,
              COUNT(DISTINCT mc.work_id) AS works_count
       FROM mc JOIN prim p ON mc.author_id=p.author_id AND mc.year=p.year
       WHERE mc.institution_id=p.primary_institution_id
       GROUP BY mc.country_code, mc.country_name, mc.geo_city, mc.city_norm,
              mc.city_geonames_id, mc.city_key, mc.geo_region, mc.geo_latitude,
              mc.geo_longitude, mc.geo_level, mc.year, mc.field_id"""))
for name, q in jobs:
    log("write %s"%name)
    con.execute("COPY (%s) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)"%(q, os.path.join(DED,name+".parquet")))
    con.execute("COPY (SELECT * FROM read_parquet('%s')) TO '%s' (HEADER, DELIMITER ',')"
                %(os.path.join(DED,name+".parquet"), os.path.join(DED,name+".csv")))
    log("  %s rows=%d"%(name, con.execute("select count(*) from read_parquet('%s')"%os.path.join(DED,name+".parquet")).fetchone()[0]))
log("ALL DONE %.0fs"%(time.time()-t0))
con.close()
