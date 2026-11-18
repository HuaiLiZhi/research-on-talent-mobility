#!/usr/bin/env python3
"""Build a per-author-year table distinguishing CAREER vs ANNUAL c-score.

- career : six indicators from cumulative non-self citations up to year Y
- annual : six indicators from non-self citations received in year Y only
Both are normalized per year; tiers (top 2/10/20/50%) computed per year among
authors with works_count>=5.

Per-year citations come from the citation graph (referenced_works), so this does
NOT depend on counts_by_year; self-citations are removed.

Output: openalex_author_impact_inputs/author_year_cscore_career_annual.parquet/.csv
"""
from __future__ import annotations
import argparse, os, time
import duckdb

CG = "/data2/openAlex/openalex_citation_graph/_partials/chunk_*.tsv"
OUT = "/data2/openAlex/openalex_author_impact_inputs"
TMP = "/data2/openAlex/duckdb_tmp"

def log(m): print("[%s] %s" % (time.strftime("%H:%M:%S"), m), flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-glob", default=CG)
    ap.add_argument("--out-dir", default=OUT)
    ap.add_argument("--min-works", type=int, default=5)
    ap.add_argument("--threads", type=int, default=90)
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True); os.makedirs(TMP, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads=%d" % a.threads)
    con.execute("SET memory_limit='180GB'")
    con.execute("SET temp_directory='%s'" % TMP)
    con.execute("SET preserve_insertion_order=false")
    t0 = time.time()

    log("load citation graph")
    con.execute(f"""
      CREATE TABLE g AS
      SELECT column0 AS kind, column1 AS work_id, column2 AS v1, column3 AS v2,
             column4 AS v3, column5 AS v4, column6 AS v5
      FROM read_csv('{a.input_glob}', delim='\t', header=false, all_varchar=true,
        columns={{'column0':'VARCHAR','column1':'VARCHAR','column2':'VARCHAR','column3':'VARCHAR',
                  'column4':'VARCHAR','column5':'VARCHAR','column6':'VARCHAR'}})
    """)
    con.execute("CREATE TABLE wm AS SELECT work_id, try_cast(v1 AS INT) AS year, v2 AS field_id, v3 AS subfield_id, try_cast(v4 AS BIGINT) AS acount FROM g WHERE kind='M'")
    con.execute("CREATE TABLE wa AS SELECT work_id, v1 AS author_id, v2 AS apos FROM g WHERE kind='A'")
    con.execute("CREATE TABLE wr AS SELECT work_id, v1 AS ref FROM g WHERE kind='R'")
    con.execute("DROP TABLE g")
    log("wm=%d wa=%d wr=%d %.0fs" % (
        con.execute("select count(*) from wm").fetchone()[0],
        con.execute("select count(*) from wa").fetchone()[0],
        con.execute("select count(*) from wr").fetchone()[0], time.time()-t0))

    log("citations per (cited work, citing year)")
    con.execute("""
      CREATE TABLE cy AS
      SELECT r.ref AS work_id, m.year AS citing_year, count(*) AS cites
      FROM wr r JOIN wm m ON m.work_id = r.work_id
      WHERE m.year IS NOT NULL GROUP BY r.ref, m.year
    """)
    log("self-citation edges")
    con.execute("CREATE TABLE wal AS SELECT work_id, list(author_id) AS authors FROM wa GROUP BY work_id")
    con.execute("""
      CREATE TABLE self_edges AS
      SELECT r.work_id AS citing, r.ref AS cited
      FROM wr r JOIN wal c ON r.work_id=c.work_id JOIN wal d ON r.ref=d.work_id
      WHERE len(list_intersect(c.authors,d.authors)) > 0
    """)
    con.execute("""
      CREATE TABLE self_cnt AS
      SELECT se.cited AS work_id, wm.year AS citing_year, count(*) AS self_cites
      FROM self_edges se JOIN wm ON wm.work_id=se.citing GROUP BY se.cited, wm.year
    """)
    con.execute("DROP TABLE self_edges")
    con.execute("""
      CREATE TABLE nonself AS
      SELECT c.work_id, c.citing_year AS year, greatest(c.cites-coalesce(s.self_cites,0),0) AS cites
      FROM cy c LEFT JOIN self_cnt s ON c.work_id=s.work_id AND c.citing_year=s.citing_year
    """)
    con.execute("DROP TABLE cy"); con.execute("DROP TABLE self_cnt")
    log("nonself rows=%d %.0fs" % (con.execute("select count(*) from nonself").fetchone()[0], time.time()-t0))

    log("author-work-year")
    con.execute("""
      CREATE TABLE awy AS
      SELECT a.author_id, a.work_id, n.year, n.cites, a.apos, m.acount
      FROM nonself n JOIN wa a ON n.work_id=a.work_id JOIN wm m ON n.work_id=m.work_id
      WHERE n.cites > 0
    """)
    con.execute("DROP TABLE nonself")
    log("awy rows=%d %.0fs" % (con.execute("select count(*) from awy").fetchone()[0], time.time()-t0))

    log("career cumulative")
    con.execute("""
      CREATE TABLE awyc AS
      SELECT *, sum(cites) OVER (PARTITION BY author_id, work_id ORDER BY year
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum
      FROM awy
    """)

    def indicators(src_table, name):
        con.execute(f"""
          CREATE TABLE {name} AS
          SELECT author_id, year, count(DISTINCT work_id) AS works_count, sum(cites) AS nc,
                 max(rn) FILTER (WHERE cites >= rn) AS h,
                 max(rn2) FILTER (WHERE cites::DOUBLE/nullif(acount,0) >= rn2) AS hm,
                 sum(cites) FILTER (WHERE acount=1) AS ncs,
                 sum(cites) FILTER (WHERE acount=1 OR apos='first') AS ncsf,
                 sum(cites) FILTER (WHERE acount=1 OR apos IN ('first','last')) AS ncsfl
          FROM (
            SELECT *, row_number() OVER (PARTITION BY author_id, year ORDER BY cites DESC) AS rn,
                   row_number() OVER (PARTITION BY author_id, year
                                      ORDER BY (cites::DOUBLE/nullif(acount,0)) DESC) AS rn2
            FROM {src_table}
          ) GROUP BY author_id, year
        """)

    con.execute("CREATE TABLE career_in AS SELECT author_id, work_id, year, cum AS cites, apos, acount FROM awyc")
    con.execute("CREATE TABLE annual_in AS SELECT author_id, work_id, year, cites, apos, acount FROM awy")
    con.execute("DROP TABLE awyc"); con.execute("DROP TABLE awy")
    log("indicator inputs ready %.0fs" % (time.time()-t0))
    indicators("career_in", "ay_career")
    log("career indicators rows=%d %.0fs" % (con.execute("select count(*) from ay_career").fetchone()[0], time.time()-t0))
    indicators("annual_in", "ay_annual")
    log("annual indicators rows=%d %.0fs" % (con.execute("select count(*) from ay_annual").fetchone()[0], time.time()-t0))
    con.execute("DROP TABLE career_in"); con.execute("DROP TABLE annual_in")

    def scored(ay, name):
        con.execute(f"""
          CREATE TABLE {name} AS
          WITH n AS (SELECT year, max(ln(1+coalesce(nc,0))) mnc, max(ln(1+coalesce(h,0))) mh,
                            max(ln(1+coalesce(hm,0))) mhm, max(ln(1+coalesce(ncs,0))) mncs,
                            max(ln(1+coalesce(ncsf,0))) mncsf, max(ln(1+coalesce(ncsfl,0))) mncsfl
                     FROM {ay} GROUP BY year)
          SELECT a.*, ( ln(1+coalesce(a.nc,0))/n.mnc + ln(1+coalesce(a.h,0))/n.mh
                      + ln(1+coalesce(a.hm,0))/n.mhm + ln(1+coalesce(a.ncs,0))/n.mncs
                      + ln(1+coalesce(a.ncsf,0))/n.mncsf + ln(1+coalesce(a.ncsfl,0))/n.mncsfl ) AS cscore
          FROM {ay} a JOIN n ON a.year=n.year
        """)
    scored("ay_career", "sc_career")
    scored("ay_annual", "sc_annual")
    con.execute("DROP TABLE ay_career"); con.execute("DROP TABLE ay_annual")

    def tiered(sc, name):
        con.execute(f"""
          CREATE TABLE {name} AS
          WITH r AS (
            SELECT author_id, year, works_count, cscore,
                   row_number() OVER (PARTITION BY year ORDER BY cscore DESC) AS rn,
                   count(*) OVER (PARTITION BY year) AS n
            FROM {sc} WHERE works_count >= {a.min_works}
          )
          SELECT author_id, year, works_count, cscore,
                 rn::DOUBLE/nullif(n,0) AS pct_rank,
                 (rn <= ceil(n*0.02)) AS top2pct,
                 (rn <= ceil(n*0.10)) AS top10pct,
                 (rn <= ceil(n*0.20)) AS top20pct,
                 (rn <= ceil(n*0.50)) AS top50pct
          FROM r
        """)
    tiered("sc_career", "t_career")
    tiered("sc_annual", "t_annual")

    log("join career + annual")
    con.execute("""
      CREATE TABLE out AS
      SELECT coalesce(c.author_id,a.author_id) AS author_id,
             coalesce(c.year,a.year) AS year,
             coalesce(c.works_count,a.works_count) AS works_count,
             c.cscore AS cscore_career, c.pct_rank AS pct_career,
             coalesce(c.top2pct,false) AS top2pct_career, coalesce(c.top10pct,false) AS top10pct_career,
             coalesce(c.top20pct,false) AS top20pct_career, coalesce(c.top50pct,false) AS top50pct_career,
             a.cscore AS cscore_annual, a.pct_rank AS pct_annual,
             coalesce(a.top2pct,false) AS top2pct_annual, coalesce(a.top10pct,false) AS top10pct_annual,
             coalesce(a.top20pct,false) AS top20pct_annual, coalesce(a.top50pct,false) AS top50pct_annual
      FROM t_career c FULL OUTER JOIN t_annual a ON c.author_id=a.author_id AND c.year=a.year
    """)
    log("out rows=%d %.0fs" % (con.execute("select count(*) from out").fetchone()[0], time.time()-t0))
    pq = os.path.join(a.out_dir, "author_year_cscore_career_annual.parquet")
    cs = os.path.join(a.out_dir, "author_year_cscore_career_annual.csv")
    con.execute("COPY (SELECT * FROM out) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)" % pq)
    con.execute("COPY (SELECT * FROM out) TO '%s' (HEADER, DELIMITER ',')" % cs)
    st = con.execute("select min(year),max(year),count(*) from out").fetchone()
    log("year range/count=%s wrote %s" % (st, pq))
    log("ALL DONE %.0fs" % (time.time()-t0))
    con.close()

if __name__ == "__main__":
    raise SystemExit(main())
