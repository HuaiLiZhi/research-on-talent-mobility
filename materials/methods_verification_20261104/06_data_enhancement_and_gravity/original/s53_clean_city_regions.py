#!/usr/bin/env python3
"""Clean city mobility CSVs produced by s60_analyze_city_mobility.py.

For rows whose origin or destination city has an empty region/province, fill it
from another row with the same country, city name, latitude, and longitude when
that matched city has a non-empty region. After filling, aggregate rows with the
same origin, destination, year, and taxonomy label by summing mobility_count.

Default input files:
  <output-dir>/results/city_mobility_by_*.csv

Default output files:
  <output-dir>/results_cleaned/<same filename>
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

DEFAULT_OUTPUT_DIR = "/data2/openAlex/openalex_analysis_city_mobility"
DEFAULT_INPUT_GLOB = "city_mobility_by_*.csv"
DEFAULT_OUTPUT_SUBDIR = "results_cleaned"

BASE_FIELDS = {
    "from_city", "from_country", "from_region", "from_country_code",
    "from_latitude", "from_longitude",
    "to_city", "to_country", "to_region", "to_country_code",
    "to_latitude", "to_longitude", "year", "mobility_count",
}


class ProgressBar:
    def __init__(self, label: str, total: int, enabled: bool = True, width: int = 32) -> None:
        self.label = label
        self.total = max(total, 0)
        self.enabled = enabled and total > 0
        self.width = width
        self.current = 0
        self.started_at = time.time()
        self.last_rendered_at = 0.0

    def update(self, step: int = 1, force: bool = False) -> None:
        if not self.enabled:
            return
        self.current = min(self.total, self.current + step)
        now = time.time()
        if not force and self.current < self.total and now - self.last_rendered_at < 0.2:
            return
        self.last_rendered_at = now
        ratio = self.current / self.total if self.total else 1.0
        filled = min(self.width, int(self.width * ratio))
        bar = "#" * filled + "-" * (self.width - filled)
        elapsed = max(0.001, now - self.started_at)
        rate = self.current / elapsed
        print(
            "\r[{label}] |{bar}| {current:,}/{total:,} {percent:6.2f}% {rate:,.0f}/s".format(
                label=self.label,
                bar=bar,
                current=self.current,
                total=self.total,
                percent=ratio * 100,
                rate=rate,
            ),
            end="",
            file=sys.stderr,
            flush=True,
        )
        if self.current >= self.total:
            print(file=sys.stderr, flush=True)


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


def _norm_text(value: str | None) -> str:
    return _clean_text(value).casefold()


def _norm_coordinate(value: str | None) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    try:
        return format(Decimal(text).normalize(), "f")
    except InvalidOperation:
        return text


def _is_missing_region(value: str | None) -> bool:
    text = _clean_text(value)
    return not text or text.casefold() in {"unknown", "none", "null", "nan", "na", "n/a"}


def _city_key(row: dict[str, str], prefix: str) -> tuple[str, str, str, str]:
    return (
        _norm_text(row.get(prefix + "_country_code")) or _norm_text(row.get(prefix + "_country")),
        _norm_text(row.get(prefix + "_city")),
        _norm_coordinate(row.get(prefix + "_latitude")),
        _norm_coordinate(row.get(prefix + "_longitude")),
    )


def _detect_label_column(fieldnames: list[str]) -> str:
    candidates = [name for name in fieldnames if name not in BASE_FIELDS]
    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly one taxonomy label column besides base fields; found {}".format(candidates)
        )
    return candidates[0]


def _build_region_lookup(
    rows: list[dict[str, str]],
    show_progress: bool = True,
    label: str = "build lookup",
) -> dict[tuple[str, str, str, str], str]:
    values: dict[tuple[str, str, str, str], set[str]] = defaultdict(set)
    display_values: dict[tuple[str, str, str, str], dict[str, str]] = defaultdict(dict)
    progress = ProgressBar(label, len(rows), show_progress)

    for row in rows:
        for prefix in ("from", "to"):
            region = _clean_text(row.get(prefix + "_region"))
            if _is_missing_region(region):
                continue
            key = _city_key(row, prefix)
            if not all(key):
                continue
            norm_region = _norm_text(region)
            values[key].add(norm_region)
            display_values[key].setdefault(norm_region, region)
        progress.update()
    progress.update(0, force=True)

    lookup: dict[tuple[str, str, str, str], str] = {}
    ambiguous = 0
    resolve_progress = ProgressBar(label + " resolve", len(values), show_progress)
    for key, region_values in values.items():
        if len(region_values) == 1:
            norm_region = next(iter(region_values))
            lookup[key] = display_values[key][norm_region]
        else:
            ambiguous += 1
        resolve_progress.update()
    resolve_progress.update(0, force=True)

    if ambiguous:
        print(
            "[warn] skipped {} city keys with conflicting non-empty regions".format(ambiguous),
            file=sys.stderr,
            flush=True,
        )
    return lookup


def _fill_missing_regions(
    rows: list[dict[str, str]],
    lookup: dict[tuple[str, str, str, str], str],
    show_progress: bool = True,
    label: str = "fill regions",
) -> tuple[int, int]:
    checked = 0
    filled = 0
    progress = ProgressBar(label, len(rows), show_progress)
    for row in rows:
        for prefix in ("from", "to"):
            region_col = prefix + "_region"
            if not _is_missing_region(row.get(region_col)):
                continue
            checked += 1
            key = _city_key(row, prefix)
            if not all(key):
                continue
            replacement = lookup.get(key)
            if replacement:
                row[region_col] = replacement
                filled += 1
        progress.update()
    progress.update(0, force=True)
    return checked, filled


def _merge_rows(
    rows: list[dict[str, str]],
    fieldnames: list[str],
    label_col: str,
    show_progress: bool = True,
    label: str = "merge rows",
) -> list[dict[str, str]]:
    geo_fields = [name for name in fieldnames if name != "mobility_count"]
    count_by_key: dict[tuple[str, ...], int] = defaultdict(int)
    row_by_key: dict[tuple[str, ...], dict[str, str]] = {}
    progress = ProgressBar(label, len(rows), show_progress)

    for row in rows:
        key = tuple(_clean_text(row.get(name)) for name in geo_fields)
        try:
            count = int(_clean_text(row.get("mobility_count")) or "0")
        except ValueError:
            count = int(float(_clean_text(row.get("mobility_count")) or "0"))
        count_by_key[key] += count
        if key not in row_by_key:
            row_by_key[key] = {name: _clean_text(row.get(name)) for name in fieldnames}
        progress.update()
    progress.update(0, force=True)

    merged = []
    collect_progress = ProgressBar(label + " collect", len(row_by_key), show_progress)
    for key, row in row_by_key.items():
        row["mobility_count"] = str(count_by_key[key])
        merged.append(row)
        collect_progress.update()
    collect_progress.update(0, force=True)

    if show_progress and merged:
        print("[sort rows] sorting {:,} merged rows".format(len(merged)), file=sys.stderr, flush=True)
    merged.sort(
        key=lambda row: (
            -int(row.get("mobility_count", "0") or "0"),
            row.get("from_country_code", ""),
            row.get("from_city", ""),
            row.get("to_country_code", ""),
            row.get("to_city", ""),
            row.get("year", ""),
            row.get(label_col, ""),
        )
    )
    return merged


def clean_file(input_csv: Path, output_csv: Path, show_progress: bool = True) -> dict[str, int]:
    if show_progress:
        print("[file] cleaning {}".format(input_csv), file=sys.stderr, flush=True)
    with input_csv.open("r", newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError("No CSV header found: {}".format(input_csv))
        fieldnames = list(reader.fieldnames)
        missing = BASE_FIELDS - set(fieldnames)
        if missing:
            raise ValueError("Missing required columns in {}: {}".format(input_csv, sorted(missing)))
        label_col = _detect_label_column(fieldnames)
        rows = [dict(row) for row in reader]
    if show_progress:
        print("[read rows] {:,} rows loaded".format(len(rows)), file=sys.stderr, flush=True)

    lookup = _build_region_lookup(rows, show_progress=show_progress)
    checked, filled = _fill_missing_regions(rows, lookup, show_progress=show_progress)
    merged_rows = _merge_rows(rows, fieldnames, label_col, show_progress=show_progress)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    write_progress = ProgressBar("write rows", len(merged_rows), show_progress)
    with output_csv.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in merged_rows:
            writer.writerow(row)
            write_progress.update()
    write_progress.update(0, force=True)

    return {
        "input_rows": len(rows),
        "missing_regions_checked": checked,
        "regions_filled": filled,
        "output_rows": len(merged_rows),
        "merged_rows": len(rows) - len(merged_rows),
    }


def _resolve_inputs(args: argparse.Namespace) -> list[Path]:
    if args.input_file:
        return [Path(args.input_file).expanduser().resolve()]

    input_dir = Path(args.input_dir).expanduser().resolve() if args.input_dir else (
        Path(args.output_dir).expanduser().resolve() / "results"
    )
    return sorted(input_dir.glob(args.input_glob))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill missing city regions and merge duplicate OD rows in city mobility CSVs."
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help="Output directory used by s60_analyze_city_mobility.py")
    parser.add_argument("--input-dir", default="",
                        help="Directory containing city_mobility_by_*.csv; defaults to <output-dir>/results")
    parser.add_argument("--input-file", default="",
                        help="Clean one CSV file instead of all matching files in the input directory")
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB,
                        help="Glob for input files when --input-file is not set")
    parser.add_argument("--cleaned-dir", default="",
                        help="Directory for cleaned CSVs; defaults to <output-dir>/results_cleaned")
    parser.add_argument("--suffix", default="",
                        help="Optional filename suffix before .csv, e.g. _cleaned")
    parser.add_argument("--overwrite", action="store_true",
                        help="Write cleaned output back to the input file")
    parser.add_argument("--no-progress", action="store_true",
                        help="Disable terminal progress bars")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inputs = _resolve_inputs(args)
    if not inputs:
        print("No input CSV files found.", file=sys.stderr)
        return 1

    if args.cleaned_dir:
        cleaned_dir = Path(args.cleaned_dir).expanduser().resolve()
    else:
        cleaned_dir = Path(args.output_dir).expanduser().resolve() / DEFAULT_OUTPUT_SUBDIR

    file_progress = ProgressBar("files", len(inputs), not args.no_progress)
    for input_csv in inputs:
        if args.overwrite:
            output_csv = input_csv
        elif args.input_file and args.cleaned_dir:
            output_csv = cleaned_dir / input_csv.name
        elif args.suffix:
            output_csv = cleaned_dir / (input_csv.stem + args.suffix + input_csv.suffix)
        else:
            output_csv = cleaned_dir / input_csv.name

        stats = clean_file(input_csv, output_csv, show_progress=not args.no_progress)
        file_progress.update()
        print(
            "{} -> {}  input_rows={:,} filled={:,}/{:,} merged={:,} output_rows={:,}".format(
                input_csv,
                output_csv,
                stats["input_rows"],
                stats["regions_filled"],
                stats["missing_regions_checked"],
                stats["merged_rows"],
                stats["output_rows"],
            ),
            flush=True,
        )
    file_progress.update(0, force=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
