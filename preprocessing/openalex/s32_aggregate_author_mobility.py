#!/usr/bin/env python3
"""Aggregate the deduplicated author-mobility rows into scholar-mobility
tables keyed by (author, year, institution, discipline).

Input : author_work_locations_deduped.csv (output of s21_dedupe_works_mobility.sh;
        sorted by author_id, so all rows of one author are contiguous).
Output: two CSV tables sharing the same schema, one at FIELD level and one at
        SUBFIELD level:
          author_id, author_display_name, orcid, year,
          institution_id, institution_display_name, institution_type,
          institution_ror, country_code, country_name, geo_city, geo_region,
          geo_latitude, geo_longitude, <field|subfield>_id,
          <field|subfield>_display_name, works_count

works_count is the number of DISTINCT work_ids the author had in that
(year, institution, discipline) cell.

Usage:
  python s32_aggregate_author_mobility.py \
      --input  /data2/openAlex/openalex_mobility_works_raw/author_work_locations_deduped.csv \
      --field-out    /data2/openAlex/openalex_mobility_works_raw/detail_mobility_by_field.csv \
      --subfield-out /data2/openAlex/openalex_mobility_works_raw/detail_mobility_by_subfield.csv
"""
from __future__ import annotations

import argparse
import csv
import sys
import time

# column indices of author_work_locations*.csv (22 cols)
A_ID, A_NAME, A_ORCID = 0, 1, 2
WORK, YEAR = 3, 4
CC, CNAME = 7, 8
IID, INAME, ITYPE, IROR = 9, 10, 11, 12
CITY, REGION, LAT, LON = 13, 14, 15, 16
FID, FNAME = 18, 19
SFID, SFNAME = 20, 21

COMMON = ["author_id", "author_display_name", "orcid", "year",
          "institution_id", "institution_display_name", "institution_type",
          "institution_ror", "country_code", "country_name",
          "geo_city", "geo_region", "geo_latitude", "geo_longitude"]
FIELD_COLS = COMMON + ["field_id", "field_display_name", "works_count"]
SUB_COLS = COMMON + ["subfield_id", "subfield_display_name", "works_count"]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--field-out", required=True)
    p.add_argument("--subfield-out", required=True)
    p.add_argument("--progress-step", type=int, default=50_000_000)
    return p.parse_args()


def main() -> int:
    a = parse_args()
    t0 = time.time()
    n_in = n_field = n_sub = 0

    with open(a.input, "r", newline="", encoding="utf-8-sig") as fh, \
         open(a.field_out, "w", newline="", encoding="utf-8-sig") as ff, \
         open(a.subfield_out, "w", newline="", encoding="utf-8-sig") as sf:
        r = csv.reader(fh)
        header = next(r, None)
        if header is None:
            raise SystemExit("empty input")
        fw = csv.writer(ff); sw = csv.writer(sf)
        fw.writerow(FIELD_COLS); sw.writerow(SUB_COLS)

        cur_aid = None
        meta = ("", "")
        # group key -> [set(work_id), attrs tuple, discipline display name]
        fg: dict = {}
        sg: dict = {}

        def flush():
            nonlocal n_field, n_sub
            if cur_aid is None:
                return
            for (year, iid, fid), (works, attrs, fname) in sorted(fg.items()):
                fw.writerow([cur_aid, meta[0], meta[1], year, iid,
                             attrs[0], attrs[1], attrs[2], attrs[3], attrs[4],
                             attrs[5], attrs[6], attrs[7], attrs[8],
                             fid, fname, len(works)])
                n_field += 1
            for (year, iid, sfid), (works, attrs, sfname) in sorted(sg.items()):
                sw.writerow([cur_aid, meta[0], meta[1], year, iid,
                             attrs[0], attrs[1], attrs[2], attrs[3], attrs[4],
                             attrs[5], attrs[6], attrs[7], attrs[8],
                             sfid, sfname, len(works)])
                n_sub += 1
            fg.clear(); sg.clear()

        for row in r:
            if len(row) < 22:
                continue
            n_in += 1
            aid = row[A_ID]
            if aid != cur_aid:
                flush()
                cur_aid = aid
                meta = (row[A_NAME], row[A_ORCID])
            attrs = (row[INAME], row[ITYPE], row[IROR], row[CC], row[CNAME],
                     row[CITY], row[REGION], row[LAT], row[LON])
            wid = row[WORK]
            year = row[YEAR]
            iid = row[IID]
            kf = (year, iid, row[FID])
            e = fg.get(kf)
            if e is None:
                fg[kf] = [ {wid}, attrs, row[FNAME] ]
            else:
                e[0].add(wid)
            ks = (year, iid, row[SFID])
            e = sg.get(ks)
            if e is None:
                sg[ks] = [ {wid}, attrs, row[SFNAME] ]
            else:
                e[0].add(wid)
            if n_in % a.progress_step == 0:
                print("[agg] read={:,}  field_rows={:,}  subfield_rows={:,}  "
                      "{:.0f}s".format(n_in, n_field, n_sub, time.time() - t0),
                      flush=True)
        flush()

    print("[agg] done  input_rows={:,}  field_rows={:,}  subfield_rows={:,}  "
          "{:.0f}s".format(n_in, n_field, n_sub, time.time() - t0), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
