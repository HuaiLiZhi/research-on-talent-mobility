#!/usr/bin/env python3
"""Build a deduped, works-based author mobility dataset directory.

Input : author_work_locations_deduped.csv  (per-work rows from
        s10_extract_works_author_mobility.py, de-duplicated and sorted by
        author_id via s21_dedupe_works_mobility.sh).  Columns (22):
          author_id, author_display_name, orcid, work_id, publication_year,
          author_position, geo_level, country_code, country_name,
          institution_id, institution_display_name, institution_type,
          institution_ror, geo_city, geo_region, geo_latitude, geo_longitude,
          source, field_id, field_display_name, subfield_id,
          subfield_display_name

Output directory mirrors openalex_mobility_author_entity_deduped/:
  <out>/detail_author_year_locations.csv   one row per
        (author, year, institution, field, subfield) with works_count,
        geo, author name/orcid -- the deduped mobility dataset with discipline.
  <out>/detail_authors.csv                 author metadata derived from works.
  <out>/institutions.csv            copied companion.

Usage:
  python s22_build_author_year_locations.py \
      --input /data2/openAlex/openalex_mobility_works_raw/author_work_locations_deduped.csv \
      --out-dir /data2/openAlex/openalex_mobility_deduped \
      --institutions /data2/openAlex/openalex_mobility_author_entity_deduped/institutions.csv
"""
from __future__ import annotations

import argparse
import csv
import shutil
import time

A_ID, A_NAME, A_ORCID = 0, 1, 2
WORK, YEAR = 3, 4
CC, CNAME = 7, 8
IID, INAME, ITYPE, IROR = 9, 10, 11, 12
CITY, REGION, LAT, LON = 13, 14, 15, 16
FID, FNAME = 18, 19
SFID, SFNAME = 20, 21

AYL_COLS = ["author_id", "author_display_name", "orcid", "year",
            "institution_id", "institution_ror", "institution_display_name",
            "institution_type", "institution_country_code",
            "geo_city", "geo_region", "geo_country_code", "geo_country",
            "geo_latitude", "geo_longitude",
            "field_id", "field_display_name",
            "subfield_id", "subfield_display_name", "works_count"]
AUTHORS_COLS = ["id", "display_name", "orcid", "works_count",
                "first_year", "last_year"]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--institutions",
                   default="/data2/openAlex/openalex_mobility_author_entity_deduped/institutions.csv")
    p.add_argument("--progress-step", type=int, default=50_000_000)
    return p.parse_args()


def main() -> int:
    a = parse_args()
    t0 = time.time()
    import os
    os.makedirs(a.out_dir, exist_ok=True)

    ayl_path = os.path.join(a.out_dir, "detail_author_year_locations.csv")
    authors_path = os.path.join(a.out_dir, "detail_authors.csv")

    n_in = n_out = n_auth = 0
    with open(a.input, "r", newline="", encoding="utf-8-sig") as fh, \
         open(ayl_path, "w", newline="", encoding="utf-8-sig") as af, \
         open(authors_path, "w", newline="", encoding="utf-8-sig") as uf:
        r = csv.reader(fh)
        header = next(r, None)
        if header is None:
            raise SystemExit("empty input")
        aw = csv.writer(af); uw = csv.writer(uf)
        aw.writerow(AYL_COLS); uw.writerow(AUTHORS_COLS)

        cur = None
        meta = ("", "")
        groups: dict = {}      # (year,iid,fid,sfid) -> set(work)
        iattrs: dict = {}      # iid -> attrs
        fn: dict = {}          # fid -> fname
        sfn: dict = {}         # sfid -> sfname
        allworks: set = set()
        ymin = None; ymax = None

        def flush():
            nonlocal n_out, n_auth
            if cur is None:
                return
            for (year, iid, fid, sfid), works in sorted(groups.items()):
                at = iattrs.get(iid, ("", "", "", "", "", "", "", "", ""))
                aw.writerow([cur, meta[0], meta[1], year, iid,
                             at[2], at[0], at[1], at[3],
                             at[5], at[6], at[3], at[4],
                             at[7], at[8],
                             fid, fn.get(fid, ""), sfid, sfn.get(sfid, ""),
                             len(works)])
                n_out += 1
            uw.writerow([cur, meta[0], meta[1], len(allworks),
                         ymin if ymin is not None else "",
                         ymax if ymax is not None else ""])
            n_auth += 1
            groups.clear(); iattrs.clear(); fn.clear(); sfn.clear(); allworks.clear()

        for row in r:
            if len(row) < 22:
                continue
            n_in += 1
            aid = row[A_ID]
            if aid != cur:
                flush()
                cur = aid
                meta = (row[A_NAME], row[A_ORCID])
                ymin = ymax = None
            iid = row[IID]
            if iid and iid not in iattrs:
                iattrs[iid] = (row[INAME], row[ITYPE], row[IROR], row[CC],
                               row[CNAME], row[CITY], row[REGION],
                               row[LAT], row[LON])
            fid = row[FID]; sfid = row[SFID]
            if fid and fid not in fn:
                fn[fid] = row[FNAME]
            if sfid and sfid not in sfn:
                sfn[sfid] = row[SFNAME]
            k = (row[YEAR], iid, fid, sfid)
            e = groups.get(k)
            if e is None:
                groups[k] = {row[WORK]}
            else:
                e.add(row[WORK])
            allworks.add(row[WORK])
            try:
                y = int(row[YEAR])
                ymin = y if ymin is None else min(ymin, y)
                ymax = y if ymax is None else max(ymax, y)
            except ValueError:
                pass
            if n_in % a.progress_step == 0:
                print("[build] read={:,}  ayl_rows={:,}  authors={:,}  {:.0f}s".format(
                    n_in, n_out, n_auth, time.time() - t0), flush=True)
        flush()

    if a.institutions and __import__("os").path.isfile(a.institutions):
        shutil.copy2(a.institutions, __import__("os").path.join(a.out_dir, "institutions.csv"))

    print("[build] done  input_rows={:,}  author_year_rows={:,}  authors={:,}  "
          "{:.0f}s".format(n_in, n_out, n_auth, time.time() - t0), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
