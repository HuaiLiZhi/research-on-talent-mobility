import duckdb, time, os, json

DED="/data2/openAlex/openalex_mobility_deduped"
SRC=os.path.join(DED,"detail_mobility_by_field.parquet")
INST="/data2/openAlex/openalex_mobility_author_entity_deduped/institutions.csv"
TMP="/data2/openAlex/duckdb_tmp"
CLEAN=os.path.join(DED,"detail_mobility_by_field_clean.parquet")
PRIM=os.path.join(DED,"detail_mobility_by_field_clean_primary.parquet")
Y0,Y1=1900,2026

def log(m): print("[%s] %s"%(time.strftime("%H:%M:%S"),m),flush=True)
con=duckdb.connect()
con.execute("SET threads=90"); con.execute("SET memory_limit='180GB'")
con.execute("SET temp_directory='%s'"%TMP); con.execute("SET preserve_insertion_order=false")
os.makedirs(TMP,exist_ok=True)
t0=time.time()

log("load institutions + build city canonical map")
con.execute(f"""CREATE TEMP TABLE inst AS
 SELECT id, ror, display_name, type, country_code, geo_city,
        geo_geonames_city_id, geo_region, geo_country_code, geo_country,
        try_cast(geo_latitude AS DOUBLE) lat, try_cast(geo_longitude AS DOUBLE) lon
 FROM read_csv('{INST}', header=true, all_varchar=true)""")
con.execute("""CREATE TEMP TABLE inst_city AS
 SELECT CASE WHEN coalesce(geo_geonames_city_id,'')<>'' THEN 'gn:'||geo_geonames_city_id
             WHEN coalesce(geo_city,'')<>'' THEN 'cc:'||coalesce(geo_country_code,'')||'|'||lower(geo_city)
             ELSE NULL END AS city_key,
        geo_city AS city, geo_region AS region, lat, lon
 FROM inst""")
con.execute("""CREATE TEMP TABLE citymap AS
 WITH r AS (SELECT city_key, region, count(*) c FROM inst_city
            WHERE region IS NOT NULL AND region<>'' GROUP BY city_key, region),
      rbest AS (SELECT city_key, arg_max(region,c) region FROM r GROUP BY city_key),
      c AS (SELECT city_key, city, count(*) c FROM inst_city
            WHERE city IS NOT NULL AND city<>'' GROUP BY city_key, city),
      cbest AS (SELECT city_key, arg_max(city,c) city FROM c GROUP BY city_key)
 SELECT ic.city_key, cbest.city AS city_disp, rbest.region,
        median(ic.lat) FILTER (WHERE ic.lat BETWEEN -90 AND 90 AND ic.lat<>0) lat,
        median(ic.lon) FILTER (WHERE ic.lon BETWEEN -180 AND 180 AND ic.lon<>0) lon
 FROM inst_city ic LEFT JOIN rbest USING(city_key) LEFT JOIN cbest USING(city_key)
 GROUP BY ic.city_key, cbest.city, rbest.region""")
log("citymap done %.0fs"%(time.time()-t0))

log("clean join")
con.execute(f"""CREATE TEMP TABLE mc AS
 SELECT m.author_id, m.author_display_name, m.orcid,
        try_cast(m.year AS INTEGER) AS year,
        CASE WHEN coalesce(m.institution_id,'')<>'' THEN 'institution' ELSE 'country' END AS geo_level,
        m.country_code, m.country_name,
        m.geo_city,
        lower(strip_accents(m.geo_city)) AS city_norm,
        CASE WHEN i.geo_geonames_city_id IS NOT NULL AND i.geo_geonames_city_id<>'' THEN i.geo_geonames_city_id ELSE NULL END AS city_geonames_id,
        CASE WHEN coalesce(i.geo_geonames_city_id,'')<>'' THEN 'gn:'||i.geo_geonames_city_id
             WHEN coalesce(m.geo_city,'')<>'' THEN 'cc:'||coalesce(m.country_code,'')||'|'||lower(m.geo_city)
             ELSE NULL END AS city_key,
        coalesce(nullif(m.geo_region,''), cm.region) AS geo_region,
        CASE WHEN cm.lat IS NOT NULL THEN cm.lat
             WHEN try_cast(m.geo_latitude AS DOUBLE) BETWEEN -90 AND 90 AND try_cast(m.geo_latitude AS DOUBLE)<>0
                  THEN try_cast(m.geo_latitude AS DOUBLE) ELSE NULL END AS geo_latitude,
        CASE WHEN cm.lon IS NOT NULL THEN cm.lon
             WHEN try_cast(m.geo_longitude AS DOUBLE) BETWEEN -180 AND 180 AND try_cast(m.geo_longitude AS DOUBLE)<>0
                  THEN try_cast(m.geo_longitude AS DOUBLE) ELSE NULL END AS geo_longitude,
        m.institution_id,
        coalesce(nullif(m.institution_display_name,''), i.display_name) AS institution_display_name,
        coalesce(nullif(m.institution_type,''), i.type) AS institution_type,
        coalesce(nullif(m.institution_ror,''), i.ror) AS institution_ror,
        m.field_id, m.field_display_name, m.works_count
 FROM read_parquet('{SRC}') m
 LEFT JOIN inst i ON m.institution_id = i.id
 LEFT JOIN citymap cm ON cm.city_key = CASE
     WHEN coalesce(i.geo_geonames_city_id,'')<>'' THEN 'gn:'||i.geo_geonames_city_id
     WHEN coalesce(m.geo_city,'')<>'' THEN 'cc:'||coalesce(m.country_code,'')||'|'||lower(m.geo_city)
     ELSE NULL END
 WHERE try_cast(m.year AS INTEGER) BETWEEN {Y0} AND {Y1}""")
log("mc rows=%d %.0fs"%(con.execute("select count(*) from mc").fetchone()[0], time.time()-t0))

log("primary institution per (author, year)")
con.execute("""CREATE TEMP TABLE prim AS
 SELECT author_id, year, institution_id AS primary_institution_id FROM (
   SELECT author_id, year, institution_id, SUM(works_count) w,
          row_number() OVER (PARTITION BY author_id, year
                             ORDER BY SUM(works_count) DESC, institution_id) rn
   FROM mc WHERE coalesce(institution_id,'')<>''
   GROUP BY author_id, year, institution_id) WHERE rn=1""")

FINAL = """SELECT mc.*, 
   (mc.institution_id IS NOT NULL AND mc.institution_id<>'' AND mc.institution_id = p.primary_institution_id) AS is_primary,
   p.primary_institution_id
 FROM mc LEFT JOIN prim p ON mc.author_id=p.author_id AND mc.year=p.year"""

log("write clean full")
con.execute("COPY (%s) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)"%(FINAL,CLEAN))
con.execute("COPY (SELECT * FROM read_parquet('%s')) TO '%s' (HEADER, DELIMITER ',')"
            %(CLEAN, CLEAN.replace(".parquet",".csv")))
log("write clean primary")
con.execute("COPY (%s WHERE mc.institution_id IS NOT NULL AND mc.institution_id<>'' AND mc.institution_id=p.primary_institution_id) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)"
            %(FINAL,PRIM))
con.execute("COPY (SELECT * FROM read_parquet('%s')) TO '%s' (HEADER, DELIMITER ',')"
            %(PRIM, PRIM.replace(".parquet",".csv")))
log("ALL DONE %.0fs"%(time.time()-t0))
con.close()
