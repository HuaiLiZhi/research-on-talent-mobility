import duckdb, time, os, shutil

DED = "/data2/openAlex/openalex_mobility_deduped"
DWORK = os.path.join(DED, "detail_author_work_locations.parquet")
TMP = "/data2/openAlex/duckdb_tmp"

def log(m): print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

con = duckdb.connect()
con.execute("SET threads=90")
con.execute("SET memory_limit='180GB'")
con.execute("SET temp_directory='%s'" % TMP)
con.execute("SET preserve_insertion_order=false")
con.execute("PRAGMA enable_progress_bar=false")

t0=time.time()
D = "read_parquet('%s')" % DWORK

log("author_year_locations")
con.execute("""
COPY (
  SELECT author_id,
         any_value(author_display_name) AS author_display_name,
         any_value(orcid) AS orcid,
         publication_year AS year,
         institution_id,
         any_value(institution_ror) AS institution_ror,
         any_value(institution_display_name) AS institution_display_name,
         any_value(institution_type) AS institution_type,
         any_value(country_code) AS institution_country_code,
         any_value(geo_city) AS geo_city,
         any_value(geo_region) AS geo_region,
         any_value(country_code) AS geo_country_code,
         any_value(country_name) AS geo_country,
         any_value(geo_latitude) AS geo_latitude,
         any_value(geo_longitude) AS geo_longitude,
         field_id,
         any_value(field_display_name) AS field_display_name,
         subfield_id,
         any_value(subfield_display_name) AS subfield_display_name,
         COUNT(*) AS works_count
  FROM %s
  GROUP BY author_id, publication_year, institution_id, field_id, subfield_id
) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)
""" % (D, os.path.join(DED,"detail_author_year_locations.parquet")))
log("author_year_locations done %.0fs" % (time.time()-t0))

log("authors")
con.execute("""
COPY (
  SELECT author_id AS id,
         any_value(author_display_name) AS display_name,
         any_value(orcid) AS orcid,
         COUNT(*) AS works_count,
         min(publication_year) AS first_year,
         max(publication_year) AS last_year
  FROM %s
  GROUP BY author_id
) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)
""" % (D, os.path.join(DED,"detail_authors.parquet")))
log("authors done %.0fs" % (time.time()-t0))
log("BASE DONE %.0fs" % (time.time()-t0))
con.close()
