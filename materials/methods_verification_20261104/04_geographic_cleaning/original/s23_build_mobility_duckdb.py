import duckdb, time, os

CHUNKS = "/data2/openAlex/openalex_mobility_works_raw/_partials/chunk_*.tsv"
DB = "/data2/openAlex/mobility.duckdb"
TMP = "/data2/openAlex/duckdb_tmp"
DED = "/data2/openAlex/openalex_mobility_deduped"
MOB = "/data2/openAlex/mobility_mob.parquet"

NAMES = ["author_id","author_display_name","orcid","work_id","publication_year",
 "author_position","geo_level","country_code","country_name","institution_id",
 "institution_display_name","institution_type","institution_ror","geo_city",
 "geo_region","geo_latitude","geo_longitude","source","field_id",
 "field_display_name","subfield_id","subfield_display_name"]
NAMES_SQL = "[" + ",".join("'%s'" % n for n in NAMES) + "]"
READ = ("read_csv('%s', delim='\\t', header=false, names=%s, all_varchar=true)"
        % (CHUNKS, NAMES_SQL))

def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)

con = duckdb.connect(DB)
con.execute("SET threads=90")
con.execute("SET memory_limit='200GB'")
con.execute("SET temp_directory='%s'" % TMP)
con.execute("SET preserve_insertion_order=false")
con.execute("PRAGMA enable_progress_bar=false")

t0=time.time()
log("materialize chunks -> parquet")
if not os.path.exists(MOB):
    con.execute("COPY (SELECT * FROM %s) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)" % (READ, MOB))
log("parquet done %.0fs size=%.1fGB" % (time.time()-t0, os.path.getsize(MOB)/1e9))

log("dedup per-work parquet")
con.execute("COPY (SELECT DISTINCT * FROM read_parquet('%s')) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)"
            % (MOB, os.path.join(DED,"detail_author_work_locations.parquet")))
log("dedup per-work done %.0fs" % (time.time()-t0))

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
          COUNT(DISTINCT work_id) AS works_count
   FROM read_parquet('%s')
   GROUP BY author_id, publication_year, institution_id, field_id, subfield_id
 ) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)
""" % (MOB, os.path.join(DED,"detail_author_year_locations.parquet")))
log("author_year_locations done %.0fs" % (time.time()-t0))

log("authors")
con.execute("""
 COPY (
   SELECT author_id AS id,
          any_value(author_display_name) AS display_name,
          any_value(orcid) AS orcid,
          COUNT(DISTINCT work_id) AS works_count,
          min(publication_year) AS first_year,
          max(publication_year) AS last_year
   FROM read_parquet('%s')
   GROUP BY author_id
 ) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)
""" % (MOB, os.path.join(DED,"detail_authors.parquet")))
log("authors done %.0fs" % (time.time()-t0))
log("ALL BASE DONE %.0fs" % (time.time()-t0))
con.close()
