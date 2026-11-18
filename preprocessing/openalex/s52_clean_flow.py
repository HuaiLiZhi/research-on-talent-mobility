import duckdb, time, os

DED="/data2/openAlex/openalex_mobility_deduped"
SRC=os.path.join(DED,"detail_author_work_locations.parquet")
INST="/data2/openAlex/openalex_mobility_author_entity_deduped/institutions.csv"
OUT=os.path.join(DED,"count_mobility_flow_by_field_clean.csv")
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
        median(ic.lat) FILTER (WHERE ic.lat BETWEEN -90 AND 90 AND ic.lat<>0) AS lat,
        median(ic.lon) FILTER (WHERE ic.lon BETWEEN -180 AND 180 AND ic.lon<>0) AS lon
 FROM inst_city ic LEFT JOIN rbest USING(city_key) LEFT JOIN cbest USING(city_key)
 GROUP BY ic.city_key, cbest.city, rbest.region""")
log("citymap done %.0fs"%(time.time()-t0))

log("clean per-work (for primary institution + author field)")
con.execute(f"""CREATE TEMP TABLE mc AS
 SELECT w.author_id, w.work_id, try_cast(w.publication_year AS INTEGER) AS year,
        w.institution_id, w.field_id, w.field_display_name
 FROM read_parquet('{SRC}') w
 WHERE try_cast(w.publication_year AS INTEGER) BETWEEN {Y0} AND {Y1}""")
log("mc rows=%d %.0fs"%(con.execute("select count(*) from mc").fetchone()[0],time.time()-t0))

log("primary institution + author dominant field")
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
log("prim/dom done %.0fs"%(time.time()-t0))

log("author-year primary city (cleaned)")
con.execute("""CREATE TEMP TABLE ayc AS
 SELECT p.author_id, p.year,
        coalesce(cm.city_disp, i.geo_city) AS city,
        i.geo_country_code AS country_code, i.geo_country AS country_name,
        coalesce(nullif(i.geo_region,''), cm.region) AS region,
        coalesce(cm.lat, CASE WHEN i.lat BETWEEN -90 AND 90 AND i.lat<>0 THEN i.lat END) AS lat,
        coalesce(cm.lon, CASE WHEN i.lon BETWEEN -180 AND 180 AND i.lon<>0 THEN i.lon END) AS lon,
        cm.city_key AS city_key
 FROM prim p JOIN inst i ON p.primary_institution_id=i.id
 LEFT JOIN citymap cm ON cm.city_key = CASE
     WHEN coalesce(i.geo_geonames_city_id,'')<>'' THEN 'gn:'||i.geo_geonames_city_id
     WHEN coalesce(i.geo_city,'')<>'' THEN 'cc:'||coalesce(i.geo_country_code,'')||'|'||lower(i.geo_city)
     ELSE NULL END""")
log("ayc rows=%d %.0fs"%(con.execute("select count(*) from ayc").fetchone()[0],time.time()-t0))

log("flow")
con.execute(f"""
COPY (
 WITH seq AS (
   SELECT author_id, year, city, country_code, country_name, region, lat, lon, city_key,
          lag(city) OVER w AS p_city, lag(city_key) OVER w AS p_key,
          lag(country_code) OVER w AS p_cc, lag(country_name) OVER w AS p_country,
          lag(region) OVER w AS p_region, lag(lat) OVER w AS p_lat, lag(lon) OVER w AS p_lon
   FROM ayc WHERE city_key IS NOT NULL
   WINDOW w AS (PARTITION BY author_id ORDER BY year)
 )
 SELECT s.p_city AS from_city, s.p_country AS from_country, s.p_region AS from_region,
        s.p_cc AS from_country_code, s.p_lat AS from_latitude, s.p_lon AS from_longitude,
        s.city AS to_city, s.country_name AS to_country, s.region AS to_region,
        s.country_code AS to_country_code, s.lat AS to_latitude, s.lon AS to_longitude,
        s.year, d.dom_field_name AS field_display_name,
        COUNT(DISTINCT s.author_id) AS mobility_count
 FROM seq s JOIN author_dom d USING(author_id)
 WHERE s.p_city IS NOT NULL AND s.city IS NOT NULL
   AND (s.p_key <> s.city_key OR coalesce(s.p_cc,'') <> coalesce(s.country_code,''))
 GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14
) TO '{OUT}' (HEADER, DELIMITER ',')
""")
log("rows=%d ALL DONE %.0fs"%(con.execute(f"select count(*) from read_csv_auto('{OUT}', header=true)").fetchone()[0], time.time()-t0))
con.close()
