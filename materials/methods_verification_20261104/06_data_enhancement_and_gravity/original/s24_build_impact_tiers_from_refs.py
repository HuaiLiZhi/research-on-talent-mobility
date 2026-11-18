#!/usr/bin/env python3
"""Compute per-author-year composite citation tiers (top 2/10/20/50%) from the
citation graph (referenced_works), WITHOUT counts_by_year.

Per-year citations come from citing works' publication_year (full history),
self-citations removed (author-set overlap).  c-score is normalized per year;
tiers are global percentiles among eligible authors (works_count>=5).

Output: openalex_author_impact_inputs/author_year_impact_tiers.parquet/.csv
        columns: author_id, year, works_count, nc, h, hm, ncs, ncsf, ncsfl,
                 subfield_id, field_id, cscore, pct_rank,
                 top2pct, top10pct, top20pct, top50pct
"""
from __future__ import annotations
import argparse, json, os, time
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
    log("split tables")
    con.execute("CREATE TABLE wm AS SELECT work_id, try_cast(v1 AS INT) AS year, v2 AS field_id, v3 AS subfield_id, try_cast(v4 AS BIGINT) AS acount FROM g WHERE kind='M'")
    con.execute("CREATE TABLE wa AS SELECT work_id, v1 AS author_id, v2 AS apos FROM g WHERE kind='A'")
    con.execute("CREATE TABLE wr AS SELECT work_id, v1 AS ref FROM g WHERE kind='R'")
    con.execute("DROP TABLE g")
    log("wm=%d wa=%d wr=%d %.0fs" % (
        con.execute("select count(*) from wm").fetchone()[0],
        con.execute("select count(*) from wa").fetchone()[0],
        con.execute("select count(*) from wr").fetchone()[0], time.time()-t0))

    log("per (cited work, citing year) citations from references")
    con.execute("""
      CREATE TABLE cy AS
      SELECT r.ref AS work_id, m.year AS citing_year, count(*) AS cites
      FROM wr r JOIN wm m ON m.work_id = r.work_id
      WHERE m.year IS NOT NULL
      GROUP BY r.ref, m.year
    """)
    log("cy rows=%d %.0fs" % (con.execute("select count(*) from cy").fetchone()[0], time.time()-t0))

    log("self-citation edges")
    con.execute("CREATE TABLE wal AS SELECT work_id, list(author_id) AS authors FROM wa GROUP BY work_id")
    con.execute("""
      CREATE TABLE self_edges AS
      SELECT r.work_id AS citing, r.ref AS cited
      FROM wr r
      JOIN wal c ON r.work_id = c.work_id
      JOIN wal d ON r.ref = d.work_id
      WHERE len(list_intersect(c.authors, d.authors)) > 0
    """)
    con.execute("""
      CREATE TABLE self_cnt AS
      SELECT se.cited AS work_id, wm.year AS citing_year, count(*) AS self_cites
      FROM self_edges se JOIN wm ON wm.work_id = se.citing
      GROUP BY se.cited, wm.year
    """)
    con.execute("DROP TABLE self_edges")
    log("self_edges done %.0fs" % (time.time()-t0))

    log("non-self citations")
    con.execute("""
      CREATE TABLE nonself AS
      SELECT c.work_id, c.citing_year AS year, greatest(c.cites - coalesce(s.self_cites,0),0) AS cites
      FROM cy c LEFT JOIN self_cnt s ON c.work_id=s.work_id AND c.citing_year=s.citing_year
    """)
    con.execute("DROP TABLE cy"); con.execute("DROP TABLE self_cnt")
    log("nonself rows=%d %.0fs" % (con.execute("select count(*) from nonself").fetchone()[0], time.time()-t0))

    log("author-work-year")
    con.execute("""
      CREATE TABLE awy AS
      SELECT a.author_id, a.work_id, n.year, n.cites, a.apos, m.acount, m.field_id, m.subfield_id
      FROM nonself n JOIN wa a ON n.work_id=a.work_id JOIN wm m ON n.work_id=m.work_id
      WHERE n.cites > 0
    """)
    con.execute("DROP TABLE nonself")
    log("awy rows=%d %.0fs" % (con.execute("select count(*) from awy").fetchone()[0], time.time()-t0))

    log("cumulative per (author, work, year)")
    con.execute("""
      CREATE TABLE awyc AS
      SELECT *, sum(cites) OVER (PARTITION BY author_id, work_id ORDER BY year
                                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cum
      FROM awy
    """)
    con.execute("DROP TABLE awy")
    log("awyc done %.0fs" % (time.time()-t0))

    log("author-year indicators")
    con.execute("""
      CREATE TABLE ay AS
      SELECT author_id, year, count(DISTINCT work_id) AS works_count, sum(cum) AS nc,
             max(rn) FILTER (WHERE cum >= rn) AS h,
             max(rn2) FILTER (WHERE cum::DOUBLE/nullif(acount,0) >= rn2) AS hm,
             sum(cum) FILTER (WHERE acount = 1) AS ncs,
             sum(cum) FILTER (WHERE acount = 1 OR apos = 'first') AS ncsf,
             sum(cum) FILTER (WHERE acount = 1 OR apos IN ('first','last')) AS ncsfl
      FROM (
        SELECT *, row_number() OVER (PARTITION BY author_id, year ORDER BY cum DESC) AS rn,
               row_number() OVER (PARTITION BY author_id, year ORDER BY (cum::DOUBLE/nullif(acount,0)) DESC) AS rn2
        FROM awyc
      ) GROUP BY author_id, year
    """)
    con.execute("DROP TABLE awyc")
    log("ay rows=%d %.0fs" % (con.execute("select count(*) from ay").fetchone()[0], time.time()-t0))

    log("dominant subfield/field")
    con.execute("""
      CREATE TABLE dom AS
      WITH sc AS (SELECT a.author_id, m.subfield_id, count(*) c FROM wa a JOIN wm m ON a.work_id=m.work_id
                  WHERE coalesce(m.subfield_id,'')<>'' GROUP BY 1,2),
           fc AS (SELECT a.author_id, m.field_id, count(*) c FROM wa a JOIN wm m ON a.work_id=m.work_id
                  WHERE coalesce(m.field_id,'')<>'' GROUP BY 1,2)
      SELECT coalesce(sc.author_id, fc.author_id) AS author_id,
             arg_max(sc.subfield_id, sc.c) AS subfield_id, arg_max(fc.field_id, fc.c) AS field_id
      FROM sc FULL OUTER JOIN fc ON sc.author_id=fc.author_id GROUP BY 1
    """)
    log("dom done %.0fs" % (time.time()-t0))

    log("c-score + tiers per year")
    con.execute("""
      CREATE TABLE yn AS
      SELECT year, max(ln(1+coalesce(nc,0))) mnc, max(ln(1+coalesce(h,0))) mh,
             max(ln(1+coalesce(hm,0))) mhm, max(ln(1+coalesce(ncs,0))) mncs,
             max(ln(1+coalesce(ncsf,0))) mncsf, max(ln(1+coalesce(ncsfl,0))) mncsfl
      FROM ay GROUP BY year
    """)
    con.execute("""
      CREATE TABLE ays AS
      SELECT a.author_id, a.year, a.works_count, a.nc, a.h, a.hm, a.ncs, a.ncsf, a.ncsfl,
             d.subfield_id, d.field_id,
             ( ln(1+coalesce(a.nc,0))/n.mnc + ln(1+coalesce(a.h,0))/n.mh
             + ln(1+coalesce(a.hm,0))/n.mhm + ln(1+coalesce(a.ncs,0))/n.mncs
             + ln(1+coalesce(a.ncsf,0))/n.mncsf + ln(1+coalesce(a.ncsfl,0))/n.mncsfl ) AS cscore
      FROM ay a JOIN yn n ON a.year=n.year LEFT JOIN dom d ON a.author_id=d.author_id
    """)
    con.execute("DROP TABLE ay")
    log("ays rows=%d %.0fs" % (con.execute("select count(*) from ays").fetchone()[0], time.time()-t0))

    log("tiers (global per year, eligible works>=%d)" % a.min_works)
    con.execute(f"""
      CREATE TABLE tiers AS
      WITH r AS (
        SELECT author_id, year, works_count, nc, h, hm, ncs, ncsf, ncsfl, subfield_id, field_id, cscore,
               row_number() OVER (PARTITION BY year ORDER BY cscore DESC) AS rn,
               count(*) OVER (PARTITION BY year) AS n
        FROM ays WHERE works_count >= {a.min_works}
      )
      SELECT author_id, year, works_count, nc, h, hm, ncs, ncsf, ncsfl, subfield_id, field_id, cscore,
             rn::DOUBLE / nullif(n,0) AS pct_rank,
             (rn <= ceil(n*0.02)) AS top2pct,
             (rn <= ceil(n*0.10)) AS top10pct,
             (rn <= ceil(n*0.20)) AS top20pct,
             (rn <= ceil(n*0.50)) AS top50pct
      FROM r
    """)
    log("tiers rows=%d %.0fs" % (con.execute("select count(*) from tiers").fetchone()[0], time.time()-t0))
    pq = os.path.join(a.out_dir, "author_year_impact_tiers.parquet")
    cs = os.path.join(a.out_dir, "author_year_impact_tiers.csv")
    con.execute("COPY (SELECT * FROM tiers) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)" % pq)
    con.execute("COPY (SELECT * FROM tiers) TO '%s' (HEADER, DELIMITER ',')" % cs)
    st = con.execute("select min(year),max(year),count(distinct year) from tiers").fetchone()
    log("year range=%s wrote %s" % (st, pq))
    log("ALL DONE %.0fs" % (time.time()-t0))
    con.close()

if __name__ == "__main__":
    raise SystemExit(main())
