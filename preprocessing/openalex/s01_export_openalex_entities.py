#!/usr/bin/env python3
"""Extract OpenAlex snapshot gzip JSONL files into structured CSV tables."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import Manager
from pathlib import Path
from typing import Any

SCALARS = (str, int, float, bool, type(None))
PROGRESS_BYTES_STEP = 16 * 1024 * 1024
COPY_BUFFER_SIZE = 64 * 1024 * 1024
DEFAULT_DATA_ROOT = "/data2/openAlex/openalex_snapshot/data"
DEFAULT_OUTPUT_DIR = "/data2/openAlex/openalex_csv"
DEFAULT_CHUNK_DIR = "/data2/openAlex/openalex_tmp_chunks"
DEFAULT_OVERWRITE = True
DEFAULT_PARTITION = "all"
MAIN_ROW_EXCLUDE = {
    "works": {
        "authorships",
        "topics",
        "keywords",
        "concepts",
        "locations",
        "primary_location",
        "best_oa_location",
        "sustainable_development_goals",
        "awards",
        "funders",
        "institutions",
        "referenced_works",
        "related_works",
        "abstract_inverted_index",
        "counts_by_year",
        "mesh",
        "indexed_in",
        "corresponding_author_ids",
        "corresponding_institution_ids",
        "apc_list",
        "apc_paid",
    },
    "authors": {"affiliations", "last_known_institutions", "topics", "topic_share", "x_concepts", "sources", "counts_by_year", "display_name_alternatives"},
    "institutions": {"topics", "topic_share", "associated_institutions", "counts_by_year", "display_name_acronyms", "display_name_alternatives", "roles", "repositories", "lineage"},
    "sources": {"topics", "topic_share", "counts_by_year", "issn", "apc_prices", "societies", "alternate_titles", "host_organization_lineage"},
    "funders": {"counts_by_year", "alternate_titles", "roles"},
    "publishers": {"counts_by_year", "lineage", "alternate_titles", "country_codes", "roles"},
    "subfields": {"topics", "display_name_alternatives", "siblings"},
    "topics": {"keywords", "siblings"},
    "domains": {"display_name_alternatives", "fields", "siblings"},
    "fields": {"display_name_alternatives", "subfields", "siblings"},
    "continents": {"display_name_alternatives", "countries"},
    "countries": {"display_name_alternatives"},
    "awards": {"funded_outputs", "investigators"},
}
LOCATION_VALUE_FIELDS = ("is_oa", "landing_page_url", "pdf_url", "license", "version", "source_id", "source_display_name", "source_issn_l", "source_type")


def set_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


set_csv_field_limit()


def human_bytes(n: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}TB"


def progress_line(done: int, total: int, files_done: int, files_total: int, rows: int, start: float, width: int = 36) -> str:
    ratio = min(1.0, done / total) if total else 1.0
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    elapsed = max(0.001, time.time() - start)
    speed = done / elapsed
    remain = int((total - done) / speed) if speed > 0 and done < total else 0
    return (
        f"\r[{bar}] {ratio * 100:6.2f}% "
        f"{human_bytes(done)}/{human_bytes(total)} "
        f"files={files_done}/{files_total} rows={rows:,} "
        f"speed={human_bytes(int(speed))}/s eta={remain}s"
    ).ljust(120)


def show_progress(done: int, total: int, files_done: int, files_total: int, rows: int, start: float, final: bool = False) -> None:
    print(progress_line(done, total, files_done, files_total, rows, start), end="\n" if final else "", flush=True)


def jdump(v: Any) -> str:
    return "" if v is None else json.dumps(v, ensure_ascii=False, separators=(",", ":"))


def csvv(v: Any) -> Any:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v.replace("\x00", "")
    if isinstance(v, (int, float)):
        return v
    return jdump(v)


def key(v: Any) -> str:
    return v.rstrip("/").rsplit("/", 1)[-1] if isinstance(v, str) else ""


class Writer:
    def __init__(self, root: Path, entity: str, src: Path):
        self.dir = root / entity / src.name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.files: dict[str, Any] = {}
        self.writers: dict[str, csv.DictWriter] = {}
        self.fields: dict[str, list[str]] = {}
        self.rows: dict[str, int] = {}

    def row(self, table: str, row: dict[str, Any]) -> None:
        row = {k: csvv(v) for k, v in row.items()}
        if table not in self.writers:
            fields = list(row)
            self.fields[table] = fields
            f = (self.dir / f"{table}.csv").open("w", newline="", encoding="utf-8-sig")
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            self.files[table], self.writers[table], self.rows[table] = f, w, 0
        missing = [k for k in row if k not in self.fields[table]]
        if missing:
            self._extend(table, missing)
        self.writers[table].writerow({f: row.get(f, "") for f in self.fields[table]})
        self.rows[table] += 1

    def _extend(self, table: str, new_fields: list[str]) -> None:
        self.files[table].close()
        path = self.dir / f"{table}.csv"
        fields = self.fields[table] + new_fields
        tmp = path.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as r:
                existing = list(csv.DictReader(
                    line.replace("\x00", "") for line in r
                ))
            with tmp.open("w", newline="", encoding="utf-8-sig") as o:
                writer = csv.DictWriter(o, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for row in existing:
                    writer.writerow({f: row.get(f, "") for f in fields})
            tmp.replace(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            if not path.exists():
                with path.open("w", newline="", encoding="utf-8-sig") as o:
                    csv.DictWriter(o, fieldnames=fields, extrasaction="ignore").writeheader()
            raise
        f = path.open("a", newline="", encoding="utf-8-sig")
        self.files[table] = f
        self.fields[table] = fields
        self.writers[table] = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")

    def close(self) -> dict[str, str]:
        out = {}
        for table, f in self.files.items():
            f.close()
            if self.rows.get(table, 0):
                out[table] = str(self.dir / f"{table}.csv")
        return out


def flatten_dict(prefix: str, d: Any) -> dict[str, Any]:
    if not isinstance(d, dict):
        return {}
    out = {}
    for k, v in d.items():
        name = f"{prefix}_{k}"
        if isinstance(v, SCALARS):
            out[name] = v
        elif isinstance(v, dict):
            out.update(flatten_dict(name, v))
        elif isinstance(v, list):
            continue
    return out


def main_row(entity: str, rec: dict[str, Any], nested: str, raw: bool) -> dict[str, Any]:
    row = {}
    if raw:
        row["raw_json"] = jdump(rec)
    exclude = MAIN_ROW_EXCLUDE.get(entity, set())
    for k, v in rec.items():
        if k in exclude:
            continue
        if isinstance(v, SCALARS):
            row[k] = v
        elif isinstance(v, dict):
            row.update(flatten_dict(k, v))
        elif nested == "json":
            row[k] = jdump(v)
    return row


def flat(prefix: str, d: Any) -> dict[str, Any]:
    return flatten_dict(prefix, d)


def raw_if_enabled(raw: bool, value: Any) -> dict[str, Any]:
    return {"raw_json": jdump(value)} if raw else {}


def topic(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    r = {"id": x.get("id"), "display_name": x.get("display_name")}
    if x.get("score") is not None:
        r["score"] = x.get("score")
    for p in ("subfield", "field", "domain"):
        r.update(flat(p, x.get(p)))
    r.update(raw_if_enabled(raw, x))
    return r


def topic_share(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    r = {"id": x.get("id"), "display_name": x.get("display_name"), "value": x.get("value")}
    for p in ("subfield", "field", "domain"):
        r.update(flat(p, x.get(p)))
    r.update(raw_if_enabled(raw, x))
    return r


def concept(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    r = {k: x.get(k) for k in ("id", "display_name", "wikidata", "level", "score", "count", "value") if x.get(k) is not None}
    r.update(raw_if_enabled(raw, x))
    return r


def institution(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    return {"id": x.get("id"), "ror": x.get("ror"), "display_name": x.get("display_name"), "country_code": x.get("country_code"), "type": x.get("type"), **raw_if_enabled(raw, x)}


def authorship(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    a = x.get("author") if isinstance(x.get("author"), dict) else {}
    r = {"author_position": x.get("author_position"), "author_id": a.get("id"), "author_display_name": a.get("display_name"), "author_orcid": a.get("orcid"), "is_corresponding": x.get("is_corresponding")}
    r.update(raw_if_enabled(raw, x))
    return r


def authorship_affiliation(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    r = {"raw_affiliation_string": x.get("raw_affiliation_string")}
    r.update(raw_if_enabled(raw, x))
    return r


def location(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    s = x.get("source") if isinstance(x.get("source"), dict) else {}
    r = {"is_oa": x.get("is_oa"), "landing_page_url": x.get("landing_page_url"), "pdf_url": x.get("pdf_url"), "license": x.get("license"), "version": x.get("version"), "source_id": s.get("id"), "source_display_name": s.get("display_name"), "source_issn_l": s.get("issn_l"), "source_type": s.get("type")}
    r.update(raw_if_enabled(raw, x))
    return r


def has_location_value(row: dict[str, Any]) -> bool:
    return any(row.get(k) not in (None, "", [], {}) for k in LOCATION_VALUE_FIELDS)


def counts(x: Any, raw: bool) -> dict[str, Any]:
    if not isinstance(x, dict):
        return {"value": x, **raw_if_enabled(raw, x)}
    r = {k: x.get(k) for k in ("year", "works_count", "cited_by_count", "oa_works_count") if x.get(k) is not None}
    r.update(raw_if_enabled(raw, x))
    return r


def emit_scalar_list(w: Writer, table: str, pid: str, items: Any, value_field: str) -> None:
    if not isinstance(items, list):
        return
    for n, x in enumerate(items, 1):
        w.row(table, {"parent_id": pid, "position": n, value_field: x})


def emit_list(w: Writer, table: str, pid: str, items: Any, mapper, raw: bool) -> None:
    if not isinstance(items, list):
        return
    for n, x in enumerate(items, 1):
        r = {"parent_id": pid, "position": n}
        r.update(mapper(x, raw))
        w.row(table, r)


def emit_authorship_links(w: Writer, pid: str, authorships: Any) -> None:
    if not isinstance(authorships, list):
        return
    for authorship_position, item in enumerate(authorships, 1):
        if not isinstance(item, dict):
            continue
        institutions = item.get("institutions") if isinstance(item.get("institutions"), list) else []
        for institution_position, inst in enumerate(institutions, 1):
            if isinstance(inst, dict):
                w.row("works__authorship_institutions", {"parent_id": pid, "authorship_position": authorship_position, "institution_position": institution_position, "institution_id": inst.get("id"), "institution_display_name": inst.get("display_name")})
        countries = item.get("countries") if isinstance(item.get("countries"), list) else []
        for country_position, country in enumerate(countries, 1):
            w.row("works__authorship_countries", {"parent_id": pid, "authorship_position": authorship_position, "country_position": country_position, "country_code": country})


def emit_authorship_affiliations(w: Writer, pid: str, authorships: Any, raw: bool) -> None:
    if not isinstance(authorships, list):
        return
    for authorship_position, item in enumerate(authorships, 1):
        if not isinstance(item, dict) or not isinstance(item.get("affiliations"), list):
            continue
        for affiliation_position, affiliation in enumerate(item["affiliations"], 1):
            r = {"parent_id": pid, "authorship_position": authorship_position, "affiliation_position": affiliation_position}
            r.update(authorship_affiliation(affiliation, raw))
            w.row("works__authorship_affiliations", r)
            if isinstance(affiliation, dict) and isinstance(affiliation.get("institution_ids"), list):
                for institution_position, institution_id in enumerate(affiliation["institution_ids"], 1):
                    w.row("works__authorship_affiliation_institutions", {"parent_id": pid, "authorship_position": authorship_position, "affiliation_position": affiliation_position, "institution_position": institution_position, "institution_id": institution_id})


def emit_author_affiliation_years(w: Writer, pid: str, affiliations: Any) -> None:
    if not isinstance(affiliations, list):
        return
    for affiliation_position, affiliation in enumerate(affiliations, 1):
        if not isinstance(affiliation, dict) or not isinstance(affiliation.get("years"), list):
            continue
        for year_position, year in enumerate(affiliation["years"], 1):
            w.row("authors__affiliation_years", {"parent_id": pid, "affiliation_position": affiliation_position, "year_position": year_position, "year": year})


def generic_item(x: Any, raw: bool) -> dict[str, Any]:
    if isinstance(x, dict):
        r = {k: v for k, v in x.items() if isinstance(v, SCALARS)}
        for k, v in x.items():
            if isinstance(v, dict):
                r.update(flatten_dict(k, v))
        r.update(raw_if_enabled(raw, x))
        return r
    return {"value": x, **raw_if_enabled(raw, x)}


def emit_common_lists(entity: str, rec: dict[str, Any], w: Writer, raw: bool) -> None:
    pid = str(rec.get("id") or "")
    for name in ("display_name_alternatives", "display_name_acronyms", "alternate_titles", "country_codes", "issn"):
        emit_scalar_list(w, f"{entity}__{name}", pid, rec.get(name), "value")
    for name in ("keywords", "roles", "repositories", "apc_prices", "societies", "fields", "subfields", "siblings", "countries"):
        emit_list(w, f"{entity}__{name}", pid, rec.get(name), generic_item, raw)
    emit_scalar_list(w, f"{entity}__lineage", pid, rec.get("lineage"), "parent_id_ref")
    emit_scalar_list(w, f"{entity}__host_organization_lineage", pid, rec.get("host_organization_lineage"), "organization_id")


def emit_rel(entity: str, rec: dict[str, Any], w: Writer, raw: bool) -> None:
    pid = str(rec.get("id") or "")
    emit_common_lists(entity, rec, w, raw)
    emit_list(w, f"{entity}__topics", pid, rec.get("topics"), topic, raw)
    emit_list(w, f"{entity}__topic_share", pid, rec.get("topic_share"), topic_share, raw)
    for name in ("concepts", "x_concepts"):
        emit_list(w, f"{entity}__{name}", pid, rec.get(name), concept, raw)
    emit_list(w, f"{entity}__counts_by_year", pid, rec.get("counts_by_year"), counts, raw)
    if entity == "works":
        emit_scalar_list(w, "works__indexed_in", pid, rec.get("indexed_in"), "index")
        emit_scalar_list(w, "works__corresponding_author_ids", pid, rec.get("corresponding_author_ids"), "author_id")
        emit_scalar_list(w, "works__corresponding_institution_ids", pid, rec.get("corresponding_institution_ids"), "institution_id")
        if isinstance(rec.get("apc_list"), dict):
            w.row("works__apc_list", {"parent_id": pid, **flatten_dict("", rec["apc_list"])})
        if isinstance(rec.get("apc_paid"), dict):
            w.row("works__apc_paid", {"parent_id": pid, **flatten_dict("", rec["apc_paid"])})
        emit_list(w, "works__authorships", pid, rec.get("authorships"), authorship, raw)
        emit_authorship_links(w, pid, rec.get("authorships"))
        emit_authorship_affiliations(w, pid, rec.get("authorships"), raw)
        emit_list(w, "works__locations", pid, rec.get("locations"), location, raw)
        emit_list(w, "works__referenced_works", pid, rec.get("referenced_works"), lambda x, _raw: {"referenced_work_id": x}, raw)
        emit_list(w, "works__related_works", pid, rec.get("related_works"), lambda x, _raw: {"work_id": x}, raw)
        for col in ("primary_location", "best_oa_location"):
            if isinstance(rec.get(col), dict):
                loc = location(rec[col], raw)
                if has_location_value(loc):
                    r = {"parent_id": pid, "position": 1}
                    r.update(loc)
                    w.row(f"works__{col}", r)
    elif entity == "authors":
        emit_list(w, "authors__last_known_institutions", pid, rec.get("last_known_institutions"), institution, raw)
        def affiliation(x: Any, include_raw: bool) -> dict[str, Any]:
            if not isinstance(x, dict):
                return {"value": x, **raw_if_enabled(include_raw, x)}
            r = flat("institution", x.get("institution") if isinstance(x.get("institution"), dict) else {})
            r.update(raw_if_enabled(include_raw, x))
            return r
        emit_list(w, "authors__affiliations", pid, rec.get("affiliations"), affiliation, raw)
        emit_author_affiliation_years(w, pid, rec.get("affiliations"))
    elif entity == "awards":
        emit_scalar_list(w, "awards__funded_outputs", pid, rec.get("funded_outputs"), "work_id")
        emit_list(w, "awards__investigators", pid, rec.get("investigators"), generic_item, raw)


def process(task: tuple[str, str, str, str, bool, Any]) -> tuple[str, int, dict[str, str], int]:
    entity, src, tmp, nested, raw, progress = task
    path = Path(src)
    w = Writer(Path(tmp), entity, path)
    n = 0
    last_pos = 0
    last_report = 0
    try:
        with gzip.open(path, "rb") as f:
            for line in f:
                pos = f.fileobj.tell()
                delta = pos - last_pos
                if delta > 0:
                    last_pos = pos
                    last_report += delta
                    if last_report >= PROGRESS_BYTES_STEP:
                        progress.put(("bytes", last_report, 0, src))
                        last_report = 0
                if not line.strip():
                    continue
                rec = json.loads(line)
                if isinstance(rec, dict):
                    w.row(entity, main_row(entity, rec, nested, raw))
                    emit_rel(entity, rec, w, raw)
                    n += 1
        if last_report:
            progress.put(("bytes", last_report, 0, src))
        made = w.close()
        progress.put(("file", 0, n, src))
        return src, n, made, path.stat().st_size
    except Exception:
        w.close()
        raise


def entities(root: Path, selected: list[str] | None) -> list[str]:
    out = selected or sorted(p.name for p in root.iterdir() if p.is_dir())
    miss = [e for e in out if not (root / e).is_dir()]
    if miss:
        raise FileNotFoundError(f"missing entity folders: {miss}")
    return out


def gz_files(root: Path, ents: list[str], part: str) -> list[tuple[str, Path]]:
    out = []
    for e in ents:
        parts = sorted(p for p in (root / e).iterdir() if p.is_dir() and p.name.startswith("updated_date="))
        use = parts if part == "all" else [parts[-1] if part == "latest" else root / e / part]
        for p in use:
            out += [(e, f) for f in sorted(p.glob("*.gz"))]
    return out


def header(path: Path) -> list[str]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f), [])


def all_headers_equal(paths: list[Path]) -> bool:
    if not paths:
        return True
    first = header(paths[0])
    return all(header(p) == first for p in paths[1:])


def remove_empty_parents(path: Path, stop: Path) -> None:
    parent = path.parent
    stop = stop.resolve()
    while parent.exists() and parent.resolve() != stop:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def update_merge_progress(done: int, total: int, table: str, start: float, final: bool = False) -> None:
    ratio = min(1.0, done / total) if total else 1.0
    width = 36
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    elapsed = max(0.001, time.time() - start)
    speed = done / elapsed
    remain = int((total - done) / speed) if speed > 0 and done < total else 0
    line = f"\rmerge [{bar}] {ratio * 100:6.2f}% {human_bytes(done)}/{human_bytes(total)} table={table} speed={human_bytes(int(speed))}/s eta={remain}s"
    print(line.ljust(140), end="\n" if final else "", flush=True)


def copy_after_header(src: Path, dst, progress: dict[str, Any], table: str) -> int:
    rows = 0
    with src.open("rb") as f:
        first = f.readline()
        copied = len(first)
        while True:
            buf = f.read(COPY_BUFFER_SIZE)
            if not buf:
                break
            dst.write(buf)
            copied += len(buf)
            rows += buf.count(b"\n")
            if copied - progress["last"] >= PROGRESS_BYTES_STEP:
                progress["done"] += copied - progress["last"]
                progress["last"] = copied
                update_merge_progress(progress["done"], progress["total"], table, progress["start"])
    progress["done"] += copied - progress["last"]
    progress["last"] = 0
    return rows


def fast_merge_same_header(table: str, paths: list[Path], out: Path, progress: dict[str, Any]) -> int:
    rows = 0
    with (out / f"{table}.csv").open("wb") as fo:
        with paths[0].open("rb") as first:
            header_line = first.readline()
        fo.write(header_line)
        for p in paths:
            progress["last"] = 0
            rows += copy_after_header(p, fo, progress, table)
    return rows


def slow_merge_mixed_header(table: str, paths: list[Path], out: Path, progress: dict[str, Any]) -> int:
    fields: list[str] = []
    for p in paths:
        fields += [x for x in header(p) if x not in fields]
    n = 0
    with (out / f"{table}.csv").open("w", newline="", encoding="utf-8-sig") as fo:
        wr = csv.DictWriter(fo, fieldnames=fields, extrasaction="ignore")
        wr.writeheader()
        for p in paths:
            before = progress["done"]
            with p.open("r", newline="", encoding="utf-8-sig") as fi:
                for row in csv.DictReader(fi):
                    wr.writerow({f: row.get(f, "") for f in fields})
                    n += 1
                    if n % 100000 == 0:
                        progress["done"] = min(progress["total"], before + p.stat().st_size)
                        update_merge_progress(progress["done"], progress["total"], table, progress["start"])
            progress["done"] = min(progress["total"], before + p.stat().st_size)
            update_merge_progress(progress["done"], progress["total"], table, progress["start"])
    return n


def delete_chunk_paths(paths: list[Path], chunk_root: Path | None) -> None:
    for p in paths:
        p.unlink(missing_ok=True)
        if chunk_root is not None:
            remove_empty_parents(p, chunk_root)


def merge(chunks: dict[str, list[Path]], out: Path, delete_chunks: bool = True, chunk_root: Path | None = None) -> dict[str, int]:
    counts_out = {}
    total = sum(p.stat().st_size for paths in chunks.values() for p in paths)
    progress = {"done": 0, "total": total, "start": time.time(), "last": 0}
    for table, paths in sorted(chunks.items()):
        paths = sorted(paths)
        if all_headers_equal(paths):
            n = fast_merge_same_header(table, paths, out, progress)
            mode = "fast-copy"
        else:
            n = slow_merge_mixed_header(table, paths, out, progress)
            mode = "safe-rewrite"
        if delete_chunks:
            delete_chunk_paths(paths, chunk_root)
        counts_out[table] = n
        update_merge_progress(min(progress["done"], total), total, table, progress["start"])
        print(f"\nmerged {table}.csv rows={n} mode={mode}", flush=True)
    update_merge_progress(total, total, "done", progress["start"], final=True)
    return counts_out


def collect_existing_chunks(tmp: Path) -> dict[str, list[Path]]:
    chunks: dict[str, list[Path]] = {}
    for path in sorted(tmp.rglob("*.csv")):
        chunks.setdefault(path.stem, []).append(path)
    if not chunks:
        raise FileNotFoundError(f"no chunk CSV files found in {tmp}")
    return chunks


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpenAlex snapshot .gz JSONL to structured CSV")
    p.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    p.add_argument("--entities", nargs="+")
    p.add_argument("--partition", default=DEFAULT_PARTITION, help="latest, all, or updated_date=YYYY-MM-DD")
    p.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    p.add_argument("--nested-mode", choices=["json", "none"], default="json")
    p.add_argument("--include-raw-json", action="store_true")
    p.add_argument("--chunk-dir", default=DEFAULT_CHUNK_DIR, help=f"Directory for temporary per-process CSV chunks. Default: {DEFAULT_CHUNK_DIR}")
    p.add_argument("--keep-chunks", action="store_true", help="Keep chunk files after final CSV files are merged")
    p.add_argument("--merge-only", action="store_true", help="Only merge existing chunk CSV files from --chunk-dir, without reading .gz files")
    p.add_argument("--overwrite", dest="overwrite", action="store_true", default=DEFAULT_OVERWRITE, help="Overwrite output directory before extraction. Enabled by default.")
    p.add_argument("--no-overwrite", dest="overwrite", action="store_false", help="Do not overwrite output directory if it already exists")
    p.add_argument("--resume", action="store_true",
                   help="Skip gz files already recorded in chunk-dir/_done.txt and keep existing chunks.")
    p.add_argument("--skip-errors", action="store_true",
                   help="Log failed gz files to chunk-dir/_errors.txt and continue instead of aborting.")
    return p.parse_args()


def main() -> int:
    a = parse()
    root, out = Path(a.data_root).resolve(), Path(a.output_dir).resolve()
    if not root.is_dir() and not a.merge_only:
        raise FileNotFoundError(root)
    if out.exists() and not a.merge_only:
        if not a.overwrite:
            raise FileExistsError(f"{out} exists; use --overwrite or choose another --output-dir")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    start = time.time()
    tmp = Path(a.chunk_dir).resolve() if a.chunk_dir else out / "_chunks"
    if a.merge_only:
        print(f"Merging existing CSV chunks from {tmp} ...", flush=True)
        tables = merge(collect_existing_chunks(tmp), out, delete_chunks=not a.keep_chunks, chunk_root=tmp)
        with (out / "_manifest.json").open("w", encoding="utf-8") as f:
            json.dump({"mode": "merge-only", "seconds": round(time.time() - start, 3), "tables": tables}, f, ensure_ascii=False, indent=2)
        for table, n in sorted(tables.items()):
            print(f"{table}.csv\t{n}")
        return 0
    ents = entities(root, a.entities)
    files = gz_files(root, ents, a.partition)
    if not files:
        raise FileNotFoundError("no .gz files found")
    tmp = Path(a.chunk_dir).resolve() if a.chunk_dir else out / "_chunks"

    # --- resume / fresh-start handling ---
    done_log   = tmp / "_done.txt"
    error_log  = tmp / "_errors.txt"
    if a.resume and tmp.exists():
        already_done: set[str] = set()
        if done_log.exists():
            already_done = set(done_log.read_text(encoding="utf-8").splitlines())
        skipped = [(e, f) for e, f in files if str(f) in already_done]
        files    = [(e, f) for e, f in files if str(f) not in already_done]
        print(f"Resume mode: {len(skipped)} files already done, {len(files)} remaining.", flush=True)
    else:
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir(parents=True)

    if not files:
        print("All files already processed. Running merge only.", flush=True)
        tables = merge(collect_existing_chunks(tmp), out,
                       delete_chunks=not a.keep_chunks, chunk_root=tmp)
        for table, n in sorted(tables.items()):
            print(f"{table}.csv\t{n}")
        return 0

    total_bytes = sum(f.stat().st_size for _, f in files)
    print(f"entities={len(ents)} files={len(files)} size={human_bytes(total_bytes)} "
          f"workers={a.workers} tmp={tmp}", flush=True)

    results: list[dict] = []
    chunks:  dict[str, list[Path]] = {}
    errors:  list[str] = []
    done_bytes = done_files = done_rows = 0

    # collect chunks from any previously completed files when resuming
    if a.resume and tmp.exists():
        for path in sorted(tmp.rglob("*.csv")):
            chunks.setdefault(path.stem, []).append(path)

    try:
        with Manager() as manager:
            progress = manager.Queue()
            tasks = [(e, str(f), str(tmp), a.nested_mode, a.include_raw_json, progress)
                     for e, f in files]
            with ProcessPoolExecutor(max_workers=a.workers) as ex:
                future_to_src = {ex.submit(process, t): t[1] for t in tasks}
                pending = set(future_to_src)
                show_progress(done_bytes, total_bytes, done_files, len(files), done_rows, start)
                while pending:
                    # drain progress queue
                    try:
                        while True:
                            kind, byte_delta, row_delta, _src = progress.get_nowait()
                            if kind == "bytes":
                                done_bytes += int(byte_delta)
                            elif kind == "file":
                                done_files += 1
                                done_rows  += int(row_delta)
                            show_progress(min(done_bytes, total_bytes), total_bytes,
                                          done_files, len(files), done_rows, start)
                    except Exception:
                        pass
                    finished = {f for f in pending if f.done()}
                    for fut in finished:
                        pending.remove(fut)
                        src_path = future_to_src[fut]
                        try:
                            src_str, n, made, size = fut.result()
                            results.append({"file": src_str, "rows": n, "size": size})
                            for table, path in made.items():
                                chunks.setdefault(table, []).append(Path(path))
                            # record success for resume
                            with done_log.open("a", encoding="utf-8") as dl:
                                dl.write(src_str + "\n")
                        except Exception as exc:
                            msg = f"{src_path}\t{exc}"
                            errors.append(msg)
                            print(f"\nERROR: {msg}", file=sys.stderr, flush=True)
                            with error_log.open("a", encoding="utf-8") as el:
                                el.write(msg + "\n")
                            if not a.skip_errors:
                                raise
                    if not finished:
                        time.sleep(0.2)
                while not progress.empty():
                    try:
                        kind, byte_delta, row_delta, _src = progress.get_nowait()
                        if kind == "bytes":
                            done_bytes += int(byte_delta)
                        elif kind == "file":
                            done_files += 1
                            done_rows  += int(row_delta)
                    except Exception:
                        break
            show_progress(total_bytes, total_bytes, len(files), len(files),
                          done_rows, start, final=True)

        if errors:
            print(f"\n{len(errors)} file(s) failed — see {error_log}", flush=True)

        print("Merging CSV chunks...", flush=True)
        tables = merge(chunks, out, delete_chunks=not a.keep_chunks, chunk_root=tmp)
        with (out / "_manifest.json").open("w", encoding="utf-8") as f:
            json.dump({"data_root": str(root), "partition": a.partition,
                       "seconds": round(time.time() - start, 3),
                       "files": len(files), "errors": len(errors),
                       "tables": tables, "sources": results},
                      f, ensure_ascii=False, indent=2)
        print("done", flush=True)
        for table, n in sorted(tables.items()):
            print(f"{table}.csv\t{n}")
        if not a.keep_chunks:
            shutil.rmtree(tmp, ignore_errors=True)
        return 0
    except Exception:
        print(f"\nFailed. Chunk files kept in {tmp}\n"
              f"Re-run with --resume to continue from where it stopped.",
              file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
