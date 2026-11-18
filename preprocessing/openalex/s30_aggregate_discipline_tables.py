import duckdb, time, os, shutil

DED = "/data2/openAlex/openalex_mobility_deduped"
AYL = os.path.join(DED, "detail_author_year_locations.parquet")
TMP = "/data2/openAlex/duckdb_tmp"

def log(m): print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

con = duckdb.connect()
con.execute("SET threads=90")
con.execute("SET memory_limit='180GB'")
con.execute("SET temp_directory='%s'" % TMP)
con.execute("SET preserve_insertion_order=false")
con.execute("PRAGMA enable_progress_bar=false")
A = "read_parquet('%s')" % AYL
t0=time.time()

ATTRS_SEL = """
  any_value(author_display_name) AS author_display_name,
  any_value(orcid) AS orcid,
  year,
  institution_id,
  any_value(institution_display_name) AS institution_display_name,
  any_value(institution_type) AS institution_type,
  any_value(institution_ror) AS institution_ror,
  any_value(institution_country_code) AS country_code,
  any_value(geo_country) AS country_name,
  any_value(geo_city) AS geo_city,
  any_value(geo_region) AS geo_region,
  any_value(geo_latitude) AS geo_latitude,
  any_value(geo_longitude) AS geo_longitude
"""

def copy_both(sql_body, name):
    pq = os.path.join(DED, name + ".parquet")
    cs = os.path.join(DED, name + ".csv")
    log("write %s" % name)
    con.execute("COPY (%s) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)" % (sql_body, pq))
    con.execute("COPY (%s) TO '%s' (HEADER, DELIMITER ',')" % (sql_body, cs))
    log("  %s done %.0fs" % (name, time.time()-t0))

# field (work discipline)
copy_both("""
 SELECT author_id, %s, field_id,
        any_value(field_display_name) AS field_display_name,
        SUM(works_count) AS works_count
 FROM %s GROUP BY author_id, year, institution_id, field_id
""" % (ATTRS_SEL, A), "detail_mobility_by_field")

# subfield (work discipline)
copy_both("""
 SELECT author_id, %s, subfield_id,
        any_value(subfield_display_name) AS subfield_display_name,
        SUM(works_count) AS works_count
 FROM %s GROUP BY author_id, year, institution_id, subfield_id
""" % (ATTRS_SEL, A), "detail_mobility_by_subfield")

# author dominant field/subfield
log("author dominant disciplines")
con.execute("""
 CREATE TEMP TABLE fdom AS
 SELECT author_id, arg_max(field_id, tot) AS dom_field,
        arg_max(fname, tot) AS dom_field_name
 FROM (SELECT author_id, field_id, any_value(field_display_name) fname,
              SUM(works_count) tot FROM %s GROUP BY author_id, field_id)
 GROUP BY author_id
""" % A)
con.execute("""
 CREATE TEMP TABLE sdom AS
 SELECT author_id, arg_max(subfield_id, tot) AS dom_sub,
        arg_max(sname, tot) AS dom_sub_name
 FROM (SELECT author_id, subfield_id, any_value(subfield_display_name) sname,
              SUM(works_count) tot FROM %s GROUP BY author_id, subfield_id)
 GROUP BY author_id
""" % A)
log("dominant done %.0fs" % (time.time()-t0))

# author-discipline field table
copy_both("""
 SELECT a.author_id, %s, d.dom_field AS field_id, d.dom_field_name AS field_display_name,
        SUM(a.works_count) AS works_count
 FROM %s a JOIN fdom d USING(author_id)
 GROUP BY a.author_id, a.year, a.institution_id, d.dom_field, d.dom_field_name
""" % (ATTRS_SEL, A), "detail_mobility_by_field_author")

# author-discipline subfield table
copy_both("""
 SELECT a.author_id, %s, d.dom_sub AS subfield_id, d.dom_sub_name AS subfield_display_name,
        SUM(a.works_count) AS works_count
 FROM %s a JOIN sdom d USING(author_id)
 GROUP BY a.author_id, a.year, a.institution_id, d.dom_sub, d.dom_sub_name
""" % (ATTRS_SEL, A), "detail_mobility_by_subfield_author")

# CSV of the deduped dataset + authors
log("write detail_author_year_locations.csv / detail_authors.csv")
con.execute("COPY (SELECT * FROM read_parquet('%s')) TO '%s' (HEADER, DELIMITER ',')"
            % (AYL, os.path.join(DED,"detail_author_year_locations.csv")))
con.execute("COPY (SELECT * FROM read_parquet('%s')) TO '%s' (HEADER, DELIMITER ',')"
            % (os.path.join(DED,"detail_authors.parquet"), os.path.join(DED,"detail_authors.csv")))
inst = "/data2/openAlex/openalex_mobility_author_entity_deduped/institutions.csv"
if os.path.isfile(inst):
    shutil.copy2(inst, os.path.join(DED,"institutions.csv"))
log("ALL DONE %.0fs" % (time.time()-t0))
con.close()
