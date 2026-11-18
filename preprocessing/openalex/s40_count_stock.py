import duckdb, time, os

DED = "/data2/openAlex/openalex_mobility_deduped"
AYL = os.path.join(DED, "detail_author_year_locations.parquet")
AWL = os.path.join(DED, "detail_author_work_locations.parquet")
TMP = "/data2/openAlex/duckdb_tmp"

def log(m): print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

con = duckdb.connect()
con.execute("SET threads=90")
con.execute("SET memory_limit='180GB'")
con.execute("SET temp_directory='%s'" % TMP)
con.execute("SET preserve_insertion_order=false")
con.execute("PRAGMA enable_progress_bar=false")
os.makedirs(TMP, exist_ok=True)
t0=time.time()

A = "read_parquet('%s')" % AYL
W = "read_parquet('%s')" % AWL

# ---------- stock: city x year x field counts (from per-work deduped) ----------
log("stock table city x year x field")
con.execute("""
COPY (
  SELECT country_code, country_name, geo_city, geo_region,
         geo_latitude, geo_longitude,
         publication_year AS year, field_id,
         any_value(field_display_name) AS field_display_name,
         COUNT(DISTINCT author_id) AS author_count,
         COUNT(DISTINCT work_id) AS works_count
  FROM %s
  GROUP BY country_code, country_name, geo_city, geo_region,
           geo_latitude, geo_longitude, publication_year, field_id
) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)
""" % (W, os.path.join(DED,"count_stock_city_field_year.parquet")))
con.execute("COPY (SELECT * FROM read_parquet('%s')) TO '%s' (HEADER, DELIMITER ',')"
            % (os.path.join(DED,"count_stock_city_field_year.parquet"),
               os.path.join(DED,"count_stock_city_field_year.csv")))
log("stock done %.0fs" % (time.time()-t0))

# ---------- flow: author-dominant field ----------
log("author dominant field")
con.execute("""
CREATE TEMP TABLE author_dom AS
SELECT author_id, arg_max(field_id, tot) AS dom_field,
       arg_max(fname, tot) AS dom_field_name
FROM (
  SELECT author_id, field_id,
         any_value(field_display_name) AS fname,
         SUM(works_count) AS tot
  FROM %s GROUP BY author_id, field_id
) GROUP BY author_id
""" % A)
log("author_dom done %.0fs" % (time.time()-t0))

# ---------- flow: one best city per author-year, then lag -> moves ----------
log("flow table city-to-city")
con.execute("""
COPY (
  WITH ayc AS (
    SELECT author_id, year, geo_city, geo_country, geo_region,
           geo_country_code, geo_latitude, geo_longitude,
           SUM(works_count) AS wc
    FROM (
      SELECT author_id, publication_year AS year, geo_city, geo_country,
             geo_region, geo_country_code, geo_latitude, geo_longitude, works_count
      FROM %s
      WHERE coalesce(geo_city,'') <> ''
    )
    GROUP BY author_id, year, geo_city, geo_country, geo_region,
             geo_country_code, geo_latitude, geo_longitude
  ),
  best AS (
    SELECT author_id, year, geo_city, geo_country, geo_region,
           geo_country_code, geo_latitude, geo_longitude,
           row_number() OVER (PARTITION BY author_id, year
                              ORDER BY wc DESC, geo_city) AS rn
    FROM ayc
  ),
  seq AS (
    SELECT author_id, year, geo_city, geo_country, geo_region,
           geo_country_code, geo_latitude, geo_longitude,
           lag(geo_city)          OVER w AS p_city,
           lag(geo_country)       OVER w AS p_country,
           lag(geo_region)        OVER w AS p_region,
           lag(geo_country_code)  OVER w AS p_cc,
           lag(geo_latitude)      OVER w AS p_lat,
           lag(geo_longitude)     OVER w AS p_lon
    FROM best WHERE rn = 1
    WINDOW w AS (PARTITION BY author_id ORDER BY year)
  )
  SELECT s.p_city   AS from_city,   s.p_country AS from_country,
         s.p_region AS from_region, s.p_cc      AS from_country_code,
         s.p_lat    AS from_latitude, s.p_lon   AS from_longitude,
         s.geo_city AS to_city,     s.geo_country AS to_country,
         s.geo_region AS to_region, s.geo_country_code AS to_country_code,
         s.geo_latitude AS to_latitude, s.geo_longitude AS to_longitude,
         s.year,
         d.dom_field_name AS field_display_name,
         COUNT(DISTINCT s.author_id) AS mobility_count
  FROM seq s JOIN author_dom d USING(author_id)
  WHERE s.p_city IS NOT NULL AND s.p_city <> ''
    AND coalesce(s.geo_city,'') <> ''
    AND (lower(s.p_city) <> lower(s.geo_city)
         OR (coalesce(s.p_cc,'') <> '' AND coalesce(s.geo_country_code,'') <> ''
             AND s.p_cc <> s.geo_country_code))
  GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12,13,14
) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)
""" % (A, os.path.join(DED,"count_mobility_flow_by_field.parquet")))
con.execute("COPY (SELECT * FROM read_parquet('%s')) TO '%s' (HEADER, DELIMITER ',')"
            % (os.path.join(DED,"count_mobility_flow_by_field.parquet"),
               os.path.join(DED,"count_mobility_flow_by_field.csv")))
log("flow done %.0fs" % (time.time()-t0))
log("ALL DONE %.0fs" % (time.time()-t0))
con.close()
