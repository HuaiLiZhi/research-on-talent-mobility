#!/usr/bin/env python3
"""Full-coverage author mobility extractor from the OpenAlex works snapshot.

Goal
----
Keep EVERY resolvable (scholar, year, place) with at least country-level
granularity, preserving finer granularity (institution -> city/region/country)
whenever available, and require an explicit publication year and a valid
OpenAlex author id on every output row.

Strategy per authorship (in priority order):
  S1 institution : authorships.institutions[].id is joined to the institutions
                   entity (geo city/region/country/lat/lon) -> one row per
                   distinct institution, geo_level='institution'.
  S2 country     : for a country implied by authorships.countries[] /
                   institution country_code that is NOT already covered by an
                   S1 row -> one row, geo_level='country'.
  S3 text parse  : for an authorship that still has NO country after S1/S2,
                   parse raw_affiliation_strings (institution-name promotion
                   first when it is unambiguous and consistent, otherwise a
                   country name/code) -> geo_level='institution' or 'country'.

Every emitted row is guaranteed to carry country_code+country_name, a year,
and author_id.  Rows that cannot satisfy the country guarantee are dropped
and counted in per-run stats so the remaining gap is auditable.

An authorship whose author has no OpenAlex id, or whose work has no
publication_year, is never emitted (they cannot be attributed / dated).

Notes / decisions from raw-data forensics:
  - do NOT use the authors entity snapshot as the universe (it only covers a
    2-month updated_date window here); authorships in works are the universe,
    and author display_name/orcid come from the authorship itself.
  - output rows are de-duplicated within each source file; exact duplicate
    rows can still arise across updated_date partitions for the small set of
    works archived in >1 partition (see --final-dedup for a one-off pass).

Pipeline: identical chunked/resumable model as the earlier extractors: each
works .gz is scanned by a worker into an atomic chunk TSV; killed workers only
lose their own chunk and it is retried on resume.

Output (CSV, UTF-8 BOM + header)
  author_id, author_display_name, orcid, work_id, publication_year,
  author_position, geo_level, country_code, country_name, institution_id,
  institution_display_name, institution_type, institution_ror, geo_city,
  geo_region, geo_latitude, geo_longitude, source

Usage:
  python s10_extract_works_author_mobility.py            # full corpus
  python s10_extract_works_author_mobility.py \
      --start-year 1995 --end-year 2025 --workers 32 \
      --text-parse --promote-institutions
"""
from __future__ import annotations

import argparse, csv, gzip, io, json, os, re, sys, time, unicodedata
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass

def env_or(key: str, default: str) -> str:
    return os.environ.get(key) or default

DEFAULT_DATA_ROOT   = "/data2/openAlex/openalex_snapshot/data"
DEFAULT_OUTPUT_NAME = "openalex_mobility_works_raw"
DEFAULT_WORKERS     = max(1, (os.cpu_count() or 2) - 1)
DEFAULT_BUF_MB      = 256
PROGRESS_STEP       = 1_000_000
PROGRESS_WORKS      = 200_000
MAX_RETRIES         = 6

_BUF_BYTES: int = DEFAULT_BUF_MB * 1024 * 1024
_INST: dict = {}          # inst id -> inst row tuple
_CTRY_CODE2NAME: dict = {}
_CTRY_NAME2CODE: dict = {}
_CTRY_CODE_RE: re.Pattern | None = None
_CTRY_NAME_RE: re.Pattern | None = None
_TOKEN_INDEX: dict = {}   # distinctive token -> list of normalized-name-keys
_NAME_KEYS: dict = {}     # normalized name key -> (iid, name, ccode)
_INST_BY_ID: dict = {}    # iid -> (norm_name_key, ccode)
_CITY2CC: dict = {}       # normalized geo_city -> set of country codes


def set_csv_limit() -> None:
    n = sys.maxsize
    while True:
        try:
            csv.field_size_limit(n); return
        except OverflowError:
            n //= 10


def _clean(fh):
    for line in fh:
        yield line.replace("\x00", "")


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode("ascii")


def _norm(s: str) -> str:
    """Lowercase, ascii-fold, drop punctuation, collapse whitespace."""
    s = _ascii((s or "").lower())
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _sanitize(v) -> str:
    return (v or "").replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


# --------------------------------------------------------------------------
# institution + country tables (phase0, small: ~121k institutions)
# --------------------------------------------------------------------------
COUNTRY_ALIASES = {
    "usa": "US", "us": "US", "u.s.": "US", "u s": "US", "u.s.a": "US",
    "america": "US", "united states": "US", "united states of america": "US",
    "uk": "GB", "u.k.": "GB", "united kingdom": "GB", "great britain": "GB",
    "england": "GB", "scotland": "GB", "wales": "GB",
    "northern ireland": "GB", "britain": "GB",
    "south korea": "KR", "korea": "KR", "republic of korea": "KR",
    "russia": "RU", "russian federation": "RU",
    "czechia": "CZ", "czech republic": "CZ",
    "taiwan": "TW", "china taipei": "TW", "republic of china": "TW",
    "hong kong": "HK", "macao": "MO", "macau": "MO",
    "palestine": "PS", "west bank and gaza": "PS",
    "iran": "IR", "syria": "SY", "vietnam": "VN", "laos": "LA",
    "brunei": "BN", "moldova": "MD", "tanzania": "TZ",
    "venezuela": "VE", "bolivia": "BO", "viet nam": "VN",
    "korea republic of": "KR", "democratic people s republic of korea": "KP",
    "north korea": "KP", "congo": "CD", "dr congo": "CD",
    "congo democratic republic": "CD", "cape verde": "CV",
    "cote d ivoire": "CI", "ivory coast": "CI", "eswatini": "SZ",
    "macedonia": "MK", "north macedonia": "MK", "burma": "MM",
    "myanmar": "MM", "swaziland": "SZ", "timor leste": "TL",
    "east timor": "TL", "falkland islands": "FK", "palestinian territories": "PS",
}
CITY_HINTS_RE = re.compile(
    r"(department|university|college|institute|school|hospital|clinic|center|"
    r"centre|laboratory|lab|faculty|academy|company|corp|gmbh|s a r l|ltd|"
    r"foundation|institution|ministry|national|research)", re.I)


def _load_institutions(institutions_csv: Path, alias_extra: Path | None = None) -> None:
    """Populate INST maps from a institutions.csv (id -> geo) and optionally a
    raw institutions snapshot JSONL.gz (used for display-name aliases)."""
    # pass 1: canonical row per institution (geo) from institutions.csv
    rows = {}
    t0 = time.time()
    n = 0
    with institutions_csv.open("r", newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(_clean(fh)):
            n += 1
            iid = (r.get("id") or "").strip()
            if not iid:
                continue
            rows[iid] = (iid,
                         r.get("ror") or "", r.get("display_name") or "",
                         r.get("type") or "",
                         r.get("country_code") or "",          # inst cc (raw)
                         r.get("geo_city") or "",
                         r.get("geo_geonames_city_id") or "",
                         r.get("geo_region") or "",
                         r.get("geo_country_code") or "",       # canonical cc
                         r.get("geo_country") or "",
                         r.get("geo_latitude") or "",
                         r.get("geo_longitude") or "",
                         r.get("updated_date") or "")
    # if a raw institutions snapshot is available, prefer its richer geo/aliases
    if alias_extra and alias_extra.is_dir():
        seen_latest = {}
        tmp = {}
        for g in sorted(alias_extra.rglob("*.gz")):
            with gzip.open(g, "rb") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    iid = rec.get("id") or ""
                    if not iid:
                        continue
                    if iid in seen_latest and seen_latest[iid] >= (rec.get("updated_date") or ""):
                        continue
                    seen_latest[iid] = rec.get("updated_date") or ""
                    g2 = rec.get("geo") or {}
                    tmp[iid] = (iid,
                                rec.get("ror") or "",
                                rec.get("display_name") or "",
                                rec.get("type") or "",
                                rec.get("country_code") or "",
                                (g2.get("city") or ""),
                                (g2.get("geonames_city_id") or ""),
                                (g2.get("region") or ""),
                                (g2.get("country_code") or ""),
                                (g2.get("country") or ""),
                                (g2.get("latitude") or ""),
                                (g2.get("longitude") or ""),
                                rec.get("updated_date") or "")
        rows.update(tmp)  # raw snapshot overrides/augments the csv rows
    for iid, t in rows.items():
        _INST[iid] = t
    print("[phase0] institutions={:,}  in {:.0f}s".format(len(_INST), time.time() - t0), flush=True)


def _build_country_tables() -> None:
    from collections import defaultdict
    city2cc = defaultdict(set)
    for (_id, _ror, _dname, _typ, icc, city, _gid, _region, cc, cname, _lat, _lon, _ud) in _INST.values():
        eff = cc or icc
        if eff and cname:
            _CTRY_CODE2NAME.setdefault(eff, cname)
        if city and eff:
            city2cc[_norm(city)].add(eff)
    for k, v in city2cc.items():
        _CITY2CC[k] = frozenset(v)
    # build reverse name table (canonical english names + aliases)
    for cc, cname in _CTRY_CODE2NAME.items():
        k = _norm(cname)
        if k and k not in _CTRY_NAME2CODE:
            _CTRY_NAME2CODE[k] = cc
    for alias, cc in COUNTRY_ALIASES.items():
        k = _norm(alias)
        if k and k not in _CTRY_NAME2CODE:
            _CTRY_NAME2CODE[k] = cc
    # every name->code should have a code->name
    for k, cc in _CTRY_NAME2CODE.items():
        if cc not in _CTRY_CODE2NAME:
            _CTRY_CODE2NAME[cc] = cc
    codes = sorted(_CTRY_CODE2NAME.keys())
    _CTRY_CODE_RE = re.compile(r"(?<![A-Za-z])({0})(?![A-Za-z])".format("|".join(re.escape(c) for c in codes)))
    names = sorted(_CTRY_NAME2CODE.keys(), key=lambda s: -len(s))
    _CTRY_NAME_RE = re.compile(r"\b({0})\b".format("|".join(re.escape(n) for n in names)))
    print("[phase0] countries={:,}  name patterns={:,}".format(
        len(codes), len(names)), flush=True)


def _build_institution_name_index() -> None:
    """Token index over normalized institution display names/aliases for the
    S3 'promote to institution' step. Distinctive tokens only (<=MAX ids)."""
    from collections import defaultdict
    token_ids = defaultdict(list)
    nkeys = {}
    stop = {"the", "of", "and", "in", "for", "de", "la", "da", "do", "at", "on", "univ", "universidade"}
    max_per_token = 400
    for iid, t in _INST.items():
        _, _r, dname, _ty, icc, *_rest = t
        names = {dname}
        for nm in names:
            k = _norm(nm)
            if not k or len(k) < 5:
                continue
            nkeys.setdefault(k, (iid, nm, icc))
            seen_tokens = set()
            for tk in k.split():
                if len(tk) >= 4 and tk not in stop and tk not in seen_tokens:
                    seen_tokens.add(tk)
                    if len(token_ids[tk]) <= max_per_token:
                        token_ids[tk].append(k)
    _NAME_KEYS.update(nkeys)
    _TOKEN_INDEX.update(token_ids)
    _INST_BY_ID.update({iid: (_norm(t[2]), t[4]) for iid, t in _INST.items()})
    print("[phase0] name-index tokens={:,}  normalized names={:,}".format(
        len(_TOKEN_INDEX), len(_NAME_KEYS)), flush=True)


def _worker_init(buf_bytes: int, text_parse: bool, promote: bool) -> None:
    global _BUF_BYTES, _TEXT_PARSE, _PROMOTE
    _BUF_BYTES = buf_bytes
    _TEXT_PARSE = text_parse
    _PROMOTE = promote
    set_csv_limit()
    # NOTE: institutions/country/name-index tables are module globals set in the
    # parent before the pool is created; workers inherit them via fork (COW).


_TEXT_PARSE: bool = True
_PROMOTE: bool = True


# --------------------------------------------------------------------------
# raw-affiliation text parsing (S3)
# --------------------------------------------------------------------------
def _text_country(text: str):
    """Return (cc, cname) for a raw affiliation string, else (None, None).

    Tries, in order: full country names/aliases, ISO country-code tokens,
    then a city whose name maps to a unique country."""
    if not text:
        return None, None
    t = _ascii(text)
    found = []
    if _CTRY_CODE_RE:
        for m in _CTRY_CODE_RE.finditer(t):
            found.append(m.group(1).upper())
    nfound = []
    if _CTRY_NAME_RE:
        for m in _CTRY_NAME_RE.finditer(t.lower()):
            k = _norm(m.group(0))
            cc = _CTRY_NAME2CODE.get(k)
            if cc:
                nfound.append(cc)
    cc = None
    if nfound:
        cc = nfound[-1]
    elif found:
        cc = found[-1]
    else:
        # city -> unique country
        tn = _norm(t)
        hits = set()
        for w in tn.split():
            if len(w) < 3:
                continue
            s = _CITY2CC.get(w)
            if s is not None and len(s) == 1:
                hits.add(next(iter(s)))
        if len(hits) == 1:
            cc = hits.pop()
        else:
            return None, None
    return cc, _CTRY_CODE2NAME.get(cc, cc)


def _match_institution(text: str, cc: str):
    """If raw text contains one unambiguous institution display name whose
    country == cc, return (iid, display_name, country_code); else None."""
    t = _norm(text)
    if not t or len(t) < 8:
        return None
    cand_keys = set()
    for tk in t.split():
        if len(tk) < 4:
            continue
        keys = _TOKEN_INDEX.get(tk)
        if keys:
            cand_keys.update(keys)
    best = None
    best_len = 0
    for k in cand_keys:
        if k in t and len(k) > best_len:
            best = k
            best_len = len(k)
    if not best:
        return None
    iid, nm, icc = _NAME_KEYS[best]
    # verify: the institution's country must match the text country
    tup = _INST.get(iid)
    gcc = tup[8] if tup else ""
    gcc = gcc or icc or ""
    if gcc and gcc != cc:
        return None
    return iid, nm, gcc or cc


# --------------------------------------------------------------------------
# works scanning
# --------------------------------------------------------------------------
def _worker_scan_file(task: tuple) -> tuple:
    src_str, chunk_path_str, tmp_path_str, start_year, end_year = task
    src = Path(src_str); out_path = Path(chunk_path_str); tmp_path = Path(tmp_path_str)
    inst = _INST
    n_works = n_year = n_auth = n_naid = n_drop = 0
    r_institution = r_country = r_text_inst = r_text_cc = 0
    n_rows = 0
    t0 = time.time()
    stat = {}
    auth_keys: set = set()
    cur_fid = cur_fname = cur_sfid = cur_sfname = ""

    def emit(aid, aname, orcid, wid, year, apos, level, cc, cname, iid, dname,
             typ, ror, city, region, lat, lon, source) -> None:
        nonlocal n_rows, r_institution, r_country, r_text_inst, r_text_cc
        key = (level, cc, iid)
        if key in auth_keys:
            return
        auth_keys.add(key)
        out_file.write("\t".join([
            aid, _sanitize(aname), _sanitize(orcid), wid, str(year),
            _sanitize(apos), level, cc, _sanitize(cname),
            iid, _sanitize(dname), _sanitize(typ), _sanitize(ror),
            _sanitize(city), _sanitize(region),
            ("" if lat in (None, "") else str(lat)),
            ("" if lon in (None, "") else str(lon)),
            source,
            cur_fid, _sanitize(cur_fname), cur_sfid, _sanitize(cur_sfname),
        ]) + "\n")
        n_rows += 1
        if source == "institution": r_institution += 1
        elif source == "countries": r_country += 1
        elif source == "raw_institution": r_text_inst += 1
        else: r_text_cc += 1

    out_file = io.open(str(tmp_path), "w", encoding="utf-8", newline="")
    try:
        with gzip.open(src, "rb") as f:
            for raw_line in f:
                line = raw_line.decode("utf-8", "replace")
                if not line.strip():
                    continue
                rec = json.loads(line)
                if not isinstance(rec, dict):
                    continue
                year = rec.get("publication_year")
                n_works += 1
                if not year:
                    continue
                try:
                    year = int(year)
                except (TypeError, ValueError):
                    continue
                if year < 1500 or year > 2100:
                    continue
                if start_year and year < start_year:
                    continue
                if end_year and year > end_year:
                    continue
                n_year += 1
                wid = rec.get("id") or ""
                # work discipline: primary_topic field/subfield, fallback first topic
                pt = rec.get("primary_topic")
                if not isinstance(pt, dict):
                    pt = {}
                fld = pt.get("field") if isinstance(pt.get("field"), dict) else {}
                sfd = pt.get("subfield") if isinstance(pt.get("subfield"), dict) else {}
                cur_fid = fld.get("id") or ""
                cur_fname = fld.get("display_name") or ""
                cur_sfid = sfd.get("id") or ""
                cur_sfname = sfd.get("display_name") or ""
                if not cur_fid and not cur_sfid:
                    tops = rec.get("topics")
                    if isinstance(tops, list) and tops and isinstance(tops[0], dict):
                        t0 = tops[0]
                        fld = t0.get("field") if isinstance(t0.get("field"), dict) else {}
                        sfd = t0.get("subfield") if isinstance(t0.get("subfield"), dict) else {}
                        cur_fid = fld.get("id") or ""
                        cur_fname = fld.get("display_name") or ""
                        cur_sfid = sfd.get("id") or ""
                        cur_sfname = sfd.get("display_name") or ""
                auths = rec.get("authorships")
                if not isinstance(auths, list):
                    continue
                for item in auths:
                    if not isinstance(item, dict):
                        continue
                    au = item.get("author") if isinstance(item.get("author"), dict) else {}
                    aid = au.get("id") or ""
                    aname = au.get("display_name") or ""
                    orcid = au.get("orcid") or ""
                    if not aid:
                        n_naid += 1
                        continue
                    apos = item.get("author_position") or ""
                    n_auth += 1
                    auth_keys.clear()
                    emitted_cc: set = set()
                    seen_iid: set = set()
                    texts = item.get("raw_affiliation_strings")
                    if isinstance(texts, list):
                        text = " ; ".join(_sanitize(x) for x in texts if x)
                    else:
                        text = ""
                    raw = (item.get("raw_affiliation_string") or "") if isinstance(item.get("raw_affiliation_string"), str) else ""
                    if raw and not text:
                        text = raw

                    # ---- S1: resolved institutions
                    insts = item.get("institutions")
                    if isinstance(insts, list):
                        for inst in insts:
                            if not isinstance(inst, dict):
                                continue
                            iid = inst.get("id") or ""
                            icc = inst.get("country_code") or ""
                            if not iid and not icc:
                                continue
                            if iid and iid in seen_iid:
                                continue
                            if iid:
                                seen_iid.add(iid)
                            tup = _INST.get(iid)
                            if tup:
                                _id, ror, dname, typ, icc2, city, gid, region, gcc, cname, lat, lon, _ud = tup
                                cc = gcc or icc or icc2 or ""
                                if not cc and _TEXT_PARSE:
                                    cc, cname = _text_country(text)
                                if not cc:
                                    continue  # cannot guarantee country
                                cname = cname or cc
                                emit(aid, aname, orcid, wid, year, apos,
                                     "institution", cc, _CTRY_CODE2NAME.get(cc, cc), iid,
                                     dname or inst.get("display_name") or "",
                                     typ or inst.get("type") or "",
                                     ror or inst.get("ror") or "",
                                     city, region, lat, lon, "institution")
                                emitted_cc.add(cc)
                            else:
                                # institution id not in our geo table
                                cc = icc or ""
                                if not cc and _TEXT_PARSE:
                                    cc, cname = _text_country(text)
                                if not cc:
                                    continue
                                emit(aid, aname, orcid, wid, year, apos,
                                     "institution", cc, _CTRY_CODE2NAME.get(cc, cc),
                                     iid, inst.get("display_name") or "",
                                     inst.get("type") or "", inst.get("ror") or "",
                                     "", "", "", "", "institution")
                                emitted_cc.add(cc)

                    # ---- S2: country codes not covered by an institution row
                    countries = item.get("countries")
                    added_s2 = False
                    if isinstance(countries, list):
                        for cc in countries:
                            cc = (cc or "").strip().upper()
                            if not cc or cc in emitted_cc:
                                continue
                            emit(aid, aname, orcid, wid, year, apos,
                                 "country", cc, _CTRY_CODE2NAME.get(cc, cc),
                                 "", "", "", "", "", "", "", "", "countries")
                            emitted_cc.add(cc)
                            added_s2 = True

                    # ---- S3: raw text fallback when nothing emitted yet
                    if not emitted_cc and text and _TEXT_PARSE:
                        cc, cname = _text_country(text)
                        if cc:
                            promoted = None
                            if _PROMOTE and _NAME_KEYS and _TOKEN_INDEX:
                                promoted = _match_institution(text, cc)
                            if promoted:
                                iid, dname, pcc = promoted
                                tup = _INST.get(iid)
                                if tup:
                                    _id, ror, dname2, typ, icc2, city, gid, region, gcc, gcn, lat, lon, _ud = tup
                                    emit(aid, aname, orcid, wid, year, apos,
                                         "institution", pcc, _CTRY_CODE2NAME.get(pcc, pcc),
                                         iid, dname2 or dname, typ or "",
                                         ror or "", city, region, lat, lon,
                                         "raw_institution")
                                else:
                                    emit(aid, aname, orcid, wid, year, apos,
                                         "institution", pcc, _CTRY_CODE2NAME.get(pcc, pcc),
                                         iid, dname, "", "", "", "", "", "",
                                         "raw_institution")
                                emitted_cc.add(pcc)
                            else:
                                emit(aid, aname, orcid, wid, year, apos,
                                     "country", cc, _CTRY_CODE2NAME.get(cc, cc),
                                     "", "", "", "", "", "", "", "", "raw_country")
                                emitted_cc.add(cc)
                    if not emitted_cc:
                        n_drop += 1

                if n_works % PROGRESS_WORKS == 0:
                    print("[{}] works={:,} year={:,} auths={:,} rows={:,}  {:.0f} auths/s".format(
                        src.name, n_works, n_year, n_auth, n_rows,
                        n_auth / max(0.001, time.time() - t0)), flush=True)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise
    finally:
        out_file.close()

    try:
        tmp_path.replace(out_path)
    except OSError:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise

    stat = dict(works=n_works, works_year=n_year, authorships=n_auth,
                authorships_no_author_id=n_naid, dropped_after_all_stages=n_drop,
                rows=n_rows, rows_institution=r_institution, rows_country=r_country,
                rows_raw_institution=r_text_inst, rows_raw_country=r_text_cc)
    print("[{}] done {}  {:.0f} auths/s".format(src.name, stat,
          n_auth / max(0.001, time.time() - t0)), flush=True)
    return str(out_path), stat


OUT_FIELDS = ("author_id author_display_name orcid work_id publication_year "
              "author_position geo_level country_code country_name "
              "institution_id institution_display_name institution_type "
              "institution_ror geo_city geo_region geo_latitude geo_longitude "
              "source field_id field_display_name subfield_id "
              "subfield_display_name").split()


def concatenate_partials(partial_paths, out_csv: Path, header_fields: list) -> int:
    n = 0
    with out_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=header_fields)
        w.writeheader()
        for idx, p in enumerate(partial_paths, 1):
            pth = Path(p)
            if not pth.exists() or pth.stat().st_size == 0:
                continue
            with pth.open("r", encoding="utf-8") as g:
                for line in g:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) < len(header_fields):
                        parts += [""] * (len(header_fields) - len(parts))
                    fh.write(",".join(
                        '"{}"'.format(p.replace('"', '""')) if ("," in p or '"' in p)
                        else p for p in parts[:len(header_fields)]
                    ) + "\n")
                    n += 1
            if idx % 10 == 0 or idx == len(partial_paths):
                print("[phase3] {}/{} files  rows={:,}".format(
                    idx, len(partial_paths), n), flush=True)
    return n


def gz_files(root: Path, entity: str, part: str) -> list:
    d = root / entity
    if not d.is_dir():
        raise FileNotFoundError(d)
    if part == "all":
        parts = sorted((p for p in d.iterdir()
                        if p.is_dir() and p.name.startswith("updated_date=")),
                       reverse=True)
    elif part == "latest":
        ps = sorted(p for p in d.iterdir()
                    if p.is_dir() and p.name.startswith("updated_date="))
        parts = [ps[-1]] if ps else []
    else:
        parts = [d / part]
    return [g for p in parts if p.is_dir() for g in sorted(p.glob("*.gz"))]


def count_partitions(root: Path, entity: str) -> int:
    d = root / entity
    if not d.is_dir():
        return 0
    return sum(1 for p in d.iterdir()
               if p.is_dir() and p.name.startswith("updated_date="))


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT,
                   help="OpenAlex snapshot data root (contains works/...).")
    p.add_argument("--institutions-csv",
                   default=env_or("OPENALEX_MOBILITY_CSV_DIR",
                                  "/data2/openAlex/openalex_mobility_author_entity_deduped") + "/institutions.csv",
                   help="institutions.csv (id, geo, country_code) for S1 geo join.")
    p.add_argument("--institutions-raw-dir",
                   default="/data2/openAlex/openalex_snapshot/data/institutions",
                   help="Raw institutions snapshot dir (for display-name aliases).")
    p.add_argument("--output-dir", default="",
                   help="Output dir; default <snapshot>/../{}".format(DEFAULT_OUTPUT_NAME))
    p.add_argument("--works-partition", default="all",
                   help="'all', 'latest', or updated_date=YYYY-MM-DD.")
    p.add_argument("--start-year", type=int, default=0)
    p.add_argument("--end-year", type=int, default=0)
    p.add_argument("--text-parse", dest="text_parse", action="store_true", default=True,
                   help="Enable S3 raw-affiliation text parsing (default).")
    p.add_argument("--no-text-parse", dest="text_parse", action="store_false")
    p.add_argument("--promote-institutions", dest="promote", action="store_true", default=True,
                   help="Within S3, promote text to institution when unambiguous.")
    p.add_argument("--no-promote-institutions", dest="promote", action="store_false")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    p.add_argument("--buf-mb", type=int, default=DEFAULT_BUF_MB)
    p.add_argument("--keep-partials", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    set_csv_limit()
    a = parse_args(argv)
    wall_t0 = time.time()

    output_dir = (Path(a.output_dir).resolve() if a.output_dir
                  else Path(a.data_root).parent / DEFAULT_OUTPUT_NAME)
    partial_dir = output_dir / "_partials"
    output_dir.mkdir(parents=True, exist_ok=True)
    partial_dir.mkdir(parents=True, exist_ok=True)

    inst_csv = Path(a.institutions_csv)
    if not inst_csv.is_file():
        raise FileNotFoundError(inst_csv)
    inst_raw = Path(a.institutions_raw_dir)

    print("[phase0] loading institutions geo/names ...", flush=True)
    _load_institutions(inst_csv, inst_raw if inst_raw.is_dir() else None)
    _build_country_tables()
    _build_institution_name_index()

    works_files = gz_files(Path(a.data_root).resolve(), "works", a.works_partition)
    if not works_files:
        raise FileNotFoundError("no works .gz under {}/works ({})".format(a.data_root, a.works_partition))
    n_parts = count_partitions(Path(a.data_root).resolve(), "works")
    if n_parts > 1 and a.works_partition == "latest":
        print("[warn] found {} updated_date partitions but scanned only the "
              "latest; historical works never re-updated are MISSING".format(n_parts), flush=True)
    total_bytes = sum(p.stat().st_size for p in works_files)
    print("[phase1] works_files={:,}  bytes={:,}  workers={}  buf={}MB  partitions={}".format(
        len(works_files), total_bytes, a.workers, a.buf_mb, n_parts), flush=True)

    partial_paths = [str(p) for p in sorted(partial_dir.glob("chunk_*.tsv"))]
    total_rows = 0
    stats_agg = {}
    retries = 0
    file_ids = {p: i for i, p in enumerate(works_files)}
    pending = {p for p in works_files
               if not (partial_dir / "chunk_{:05d}.tsv".format(file_ids[p])).exists()}

    while pending:
        for stale in partial_dir.glob("chunk_*.tsv.tmp"):
            try:
                stale.unlink()
            except OSError:
                pass
        new_done = set()
        pool_broke = False
        try:
            with ProcessPoolExecutor(max_workers=a.workers,
                                     initializer=_worker_init,
                                     initargs=(a.buf_mb * 1024 * 1024,
                                               a.text_parse, a.promote)) as pool:
                futs = {}
                for src in pending:
                    cid = file_ids[src]
                    out_path = partial_dir / "chunk_{:05d}.tsv".format(cid)
                    tmp_path = partial_dir / "chunk_{:05d}.tsv.tmp".format(cid)
                    futs[pool.submit(_worker_scan_file,
                                     (str(src), str(out_path), str(tmp_path),
                                      a.start_year, a.end_year))] = src
                for fut in as_completed(futs):
                    src = futs[fut]
                    try:
                        out_path, st = fut.result()
                    except Exception as exc:
                        print("[phase1] {} FAILED (will retry): {}".format(src.name, exc), flush=True)
                        continue
                    if str(out_path) not in partial_paths:
                        partial_paths.append(str(out_path))
                    total_rows += st["rows"]
                    for k, v in st.items():
                        if k not in ("rows",):
                            stats_agg[k] = stats_agg.get(k, 0) + v
                    new_done.add(src)
                    print("[phase1] {}/{} done  rows={:,}".format(
                        len(partial_paths), len(works_files), total_rows), flush=True)
        except Exception as pool_exc:
            pool_broke = True
            print("[phase1] pool broke ({}); retrying remaining {} files".format(
                pool_exc, len(pending)), flush=True)
        pending -= new_done
        retries += 1
        if retries > MAX_RETRIES:
            raise RuntimeError("{} works files unfinished after {} attempts".format(
                len(pending), retries))
        if pending and (pool_broke or len(pending) < 10):
            print("[phase1] retrying {} unfinished files ...".format(len(pending)), flush=True)

    out_csv = output_dir / "author_work_locations.csv"
    print("[phase3] concatenating partials -> {}".format(out_csv), flush=True)
    n_out = concatenate_partials(partial_paths, out_csv, OUT_FIELDS)

    stats_path = output_dir / "_extraction_stats.json"
    summary = dict(stats_agg)
    cov = 0.0
    if summary.get("authorships"):
        cov = (summary.get("authorships") - summary.get("dropped_after_all_stages", 0)) / summary["authorships"]
    summary["rows_total"] = n_out
    summary["authorship_coverage_pct"] = round(100 * cov, 2)
    summary["elapsed_s"] = round(time.time() - wall_t0, 1)
    with stats_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("[stats] {}".format(json.dumps(summary, ensure_ascii=False)), flush=True)

    if not a.keep_partials:
        import shutil
        shutil.rmtree(partial_dir, ignore_errors=True)
        print("[cleanup] partial files removed", flush=True)

    print("\n=== Done ===\n"
          "  works files scanned : {}\n"
          "  output rows         : {:,}\n"
          "  output file         : {}\n"
          "  stats               : {}\n"
          "  wall time           : {:.1f}s\n".format(
              len(works_files), n_out, out_csv, stats_path, time.time() - wall_t0), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
