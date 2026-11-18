#!/usr/bin/env python3
"""Stream-deduplicate OpenAlex mobility CSVs by latest updated_date without MySQL.

This script is designed for very large CSV files. It avoids DuckDB JOIN/GROUP BY
memory pressure by doing sequential CSV passes.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import time
from pathlib import Path

DEFAULT_INPUT_DIR = "/data2/openAlex/openalex_mobility_author_entity"
DEFAULT_OUTPUT_DIR = "/data2/openAlex/openalex_mobility_author_entity_deduped"
PROGRESS_STEP = 1_000_000

AUTHOR_CHILD_TABLES = {
    "authors__topics": "parent_id",
    "authors__topic_share": "parent_id",
    "authors__affiliations": "parent_id",
    "authors__affiliation_years": "parent_id",
    "author_year_locations": "author_id",
}


def set_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean_lines(handle):
    for line in handle:
        yield line.replace("\x00", "")


def latest_dates(path: Path, id_column: str) -> dict[str, str]:
    latest: dict[str, str] = {}
    rows = 0
    start = time.time()
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(clean_lines(handle))
        for row in reader:
            rows += 1
            item_id = row.get(id_column, "")
            updated_date = row.get("updated_date", "")
            if item_id and updated_date and updated_date > latest.get(item_id, ""):
                latest[item_id] = updated_date
            if rows % PROGRESS_STEP == 0:
                elapsed = max(0.001, time.time() - start)
                print(f"scan {path.name}: rows={rows:,} unique={len(latest):,} speed={rows / elapsed:,.0f} rows/s", flush=True)
    print(f"scan {path.name}: done rows={rows:,} unique={len(latest):,}", flush=True)
    return latest


def write_latest_entity(path: Path, out_path: Path, id_column: str, latest: dict[str, str]) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written_ids: set[str] = set()
    rows = written = 0
    start = time.time()
    with path.open("r", newline="", encoding="utf-8-sig") as src, out_path.open("w", newline="", encoding="utf-8-sig") as dst:
        reader = csv.DictReader(clean_lines(src))
        if reader.fieldnames is None:
            return 0
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            rows += 1
            item_id = row.get(id_column, "")
            if item_id and item_id not in written_ids and row.get("updated_date", "") == latest.get(item_id, None):
                writer.writerow(row)
                written_ids.add(item_id)
                written += 1
            if rows % PROGRESS_STEP == 0:
                elapsed = max(0.001, time.time() - start)
                print(f"write {out_path.name}: read={rows:,} written={written:,} speed={rows / elapsed:,.0f} rows/s", flush=True)
    print(f"write {out_path.name}: done read={rows:,} written={written:,}", flush=True)
    return written


def write_author_child(path: Path, out_path: Path, author_column: str, latest_authors: dict[str, str]) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = written = 0
    start = time.time()
    with path.open("r", newline="", encoding="utf-8-sig") as src, out_path.open("w", newline="", encoding="utf-8-sig") as dst:
        reader = csv.DictReader(clean_lines(src))
        if reader.fieldnames is None:
            return 0
        writer = csv.DictWriter(dst, fieldnames=reader.fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            rows += 1
            author_id = row.get(author_column, "")
            if author_id and row.get("updated_date", "") == latest_authors.get(author_id, None):
                writer.writerow(row)
                written += 1
            if rows % PROGRESS_STEP == 0:
                elapsed = max(0.001, time.time() - start)
                print(f"write {out_path.name}: read={rows:,} written={written:,} speed={rows / elapsed:,.0f} rows/s", flush=True)
    print(f"write {out_path.name}: done read={rows:,} written={written:,}", flush=True)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream-deduplicate OpenAlex mobility CSV files by latest updated_date.")
    parser.add_argument("--input-dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true", default=True)
    parser.add_argument("--no-overwrite", dest="overwrite", action="store_false")
    return parser.parse_args()


def main() -> int:
    set_csv_field_limit()
    args = parse_args()
    start = time.time()
    input_dir = Path(args.input_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    if not input_dir.is_dir():
        raise FileNotFoundError(input_dir)
    if output_dir.exists():
        if not args.overwrite:
            raise FileExistsError(f"{output_dir} exists; choose another --output-dir")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    authors_csv = input_dir / "detail_authors.csv"
    institutions_csv = input_dir / "institutions.csv"
    print("scan latest author dates", flush=True)
    latest_authors = latest_dates(authors_csv, "id")
    print("write detail_authors.csv", flush=True)
    write_latest_entity(authors_csv, output_dir / "detail_authors.csv", "id", latest_authors)

    for table, author_column in AUTHOR_CHILD_TABLES.items():
        src = input_dir / f"{table}.csv"
        if not src.is_file():
            print(f"skip missing {src}", flush=True)
            continue
        print(f"write {table}.csv", flush=True)
        write_author_child(src, output_dir / f"{table}.csv", author_column, latest_authors)

    print("scan latest institution dates", flush=True)
    latest_institutions = latest_dates(institutions_csv, "id")
    print("write institutions.csv", flush=True)
    write_latest_entity(institutions_csv, output_dir / "institutions.csv", "id", latest_institutions)

    print(f"done seconds={time.time() - start:.1f} output={output_dir}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
