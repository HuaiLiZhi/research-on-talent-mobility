#!/usr/bin/env python3
"""Aggregate the deduped author-year mobility dataset into scholar-mobility
tables by discipline.

Input : <deduped-dir>/detail_author_year_locations.csv (from
        s22_build_author_year_locations.py), grouped by author_id.  Columns (20):
          author_id, author_display_name, orcid, year, institution_id,
          institution_ror, institution_display_name, institution_type,
          institution_country_code, geo_city, geo_region, geo_country_code,
          geo_country, geo_latitude, geo_longitude, field_id,
          field_display_name, subfield_id, subfield_display_name, works_count

Outputs (all keyed by scholar + year + institution):
  detail_mobility_by_field.csv          discipline = the WORK's primary field
  detail_mobility_by_subfield.csv       discipline = the WORK's primary subfield
  detail_mobility_by_field_author.csv   discipline = the AUTHOR's dominant field
  detail_mobility_by_subfield_author.csv discipline = the AUTHOR's dominant subfield

works_count is the number of distinct works in the (author, year, institution)
cell (for the *_author tables) or in the (author, year, institution, discipline)
cell (for the work-discipline tables).
"""
from __future__ import annotations

import argparse
import csv
import time

A_ID, A_NAME, A_ORCID = 0, 1, 2
YEAR = 3
IID, IROR, INAME, ITYPE, ICC = 4, 5, 6, 7, 8
CITY, REGION, GCC, GC, LAT, LON = 9, 10, 11, 12, 13, 14
FID, FNAME = 15, 16
SFID, SFNAME = 17, 18
WC = 19

COMMON = ["author_id", "author_display_name", "orcid", "year",
          "institution_id", "institution_display_name", "institution_type",
          "institution_ror", "country_code", "country_name",
          "geo_city", "geo_region", "geo_latitude", "geo_longitude"]
FIELD_COLS = COMMON + ["field_id", "field_display_name", "works_count"]
SUB_COLS = COMMON + ["subfield_id", "subfield_display_name", "works_count"]


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True,
                   help="<deduped-dir>/detail_author_year_locations.csv")
    p.add_argument("--out-dir", required=True)
    p.add_argument("--progress-step", type=int, default=50_000_000)
    return p.parse_args()


def main() -> int:
    a = parse_args()
    import os
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()

    fw = csv.writer(open(os.path.join(a.out_dir, "detail_mobility_by_field.csv"),
                         "w", newline="", encoding="utf-8-sig"))
    sw = csv.writer(open(os.path.join(a.out_dir, "detail_mobility_by_subfield.csv"),
                         "w", newline="", encoding="utf-8-sig"))
    faw = csv.writer(open(os.path.join(a.out_dir, "detail_mobility_by_field_author.csv"),
                          "w", newline="", encoding="utf-8-sig"))
    saw = csv.writer(open(os.path.join(a.out_dir, "detail_mobility_by_subfield_author.csv"),
                          "w", newline="", encoding="utf-8-sig"))
    fw.writerow(FIELD_COLS); sw.writerow(SUB_COLS)
    faw.writerow(FIELD_COLS); saw.writerow(SUB_COLS)

    n_in = n_f = n_s = n_fa = n_sa = 0
    with open(a.input, "r", newline="", encoding="utf-8-sig") as fh:
        r = csv.reader(fh)
        next(r, None)
        cur = None
        meta = ("", "")
        fg: dict = {}   # (year,iid,fid) -> [wc, attrs]
        sg: dict = {}   # (year,iid,sfid) -> [wc, attrs]
        cell: dict = {} # (year,iid) -> [wc, attrs]
        fsum: dict = {} # fid -> [wc, fname]
        ssum: dict = {} # sfid -> [wc, sfname]

        def flush():
            nonlocal n_f, n_s, n_fa, n_sa
            if cur is None:
                return
            # author dominant discipline (by total works_count)
            dom_f = max(fsum.items(), key=lambda kv: kv[1][0])[0] if fsum else ""
            dom_fname = fsum.get(dom_f, ("", ""))[1] if fsum else ""
            dom_s = max(ssum.items(), key=lambda kv: kv[1][0])[0] if ssum else ""
            dom_sname = ssum.get(dom_s, ("", ""))[1] if ssum else ""
            for (year, iid, fid), (wc, at) in sorted(fg.items()):
                fw.writerow([cur, meta[0], meta[1], year, iid,
                             at[0], at[1], at[2], at[3], at[4],
                             at[5], at[6], at[7], at[8],
                             fid, fsum.get(fid, ("", ""))[1] if fid else "",
                             wc]); n_f += 1
            for (year, iid, sfid), (wc, at) in sorted(sg.items()):
                sw.writerow([cur, meta[0], meta[1], year, iid,
                             at[0], at[1], at[2], at[3], at[4],
                             at[5], at[6], at[7], at[8],
                             sfid, ssum.get(sfid, ("", ""))[1] if sfid else "",
                             wc]); n_s += 1
            for (year, iid), (wc, at) in sorted(cell.items()):
                faw.writerow([cur, meta[0], meta[1], year, iid,
                              at[0], at[1], at[2], at[3], at[4],
                              at[5], at[6], at[7], at[8],
                              dom_f, dom_fname, wc]); n_fa += 1
                saw.writerow([cur, meta[0], meta[1], year, iid,
                              at[0], at[1], at[2], at[3], at[4],
                              at[5], at[6], at[7], at[8],
                              dom_s, dom_sname, wc]); n_sa += 1
            fg.clear(); sg.clear(); cell.clear(); fsum.clear(); ssum.clear()

        for row in r:
            if len(row) < 20:
                continue
            n_in += 1
            aid = row[A_ID]
            if aid != cur:
                flush()
                cur = aid
                meta = (row[A_NAME], row[A_ORCID])
            year = row[YEAR]; iid = row[IID]
            wc = int(row[WC] or 0)
            at = (row[INAME], row[ITYPE], row[IROR], row[ICC], row[GC],
                  row[CITY], row[REGION], row[LAT], row[LON])
            fid = row[FID]; sfid = row[SFID]
            kf = (year, iid, fid)
            e = fg.get(kf)
            if e is None:
                fg[kf] = [wc, at]
            else:
                e[0] += wc
            ks = (year, iid, sfid)
            e = sg.get(ks)
            if e is None:
                sg[ks] = [wc, at]
            else:
                e[0] += wc
            kc = (year, iid)
            e = cell.get(kc)
            if e is None:
                cell[kc] = [wc, at]
            else:
                e[0] += wc
            if fid:
                e = fsum.get(fid)
                if e is None:
                    fsum[fid] = [wc, row[FNAME]]
                else:
                    e[0] += wc
            if sfid:
                e = ssum.get(sfid)
                if e is None:
                    ssum[sfid] = [wc, row[SFNAME]]
                else:
                    e[0] += wc
            if n_in % a.progress_step == 0:
                print("[agg] read={:,}  field={:,}  subfield={:,}  field_author={:,}  {:.0f}s".format(
                    n_in, n_f, n_s, n_fa, time.time() - t0), flush=True)
        flush()

    print("[agg] done input={:,} field={:,} subfield={:,} field_author={:,} "
          "subfield_author={:,} {:.0f}s".format(
              n_in, n_f, n_s, n_fa, n_sa, time.time() - t0), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
