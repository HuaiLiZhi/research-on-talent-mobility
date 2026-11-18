#!/usr/bin/env python3
"""Preprocess OpenAlex snapshot gzip files into plain training inputs.

This is a file-only pipeline: it does not create or use SQLite (or any other
database).  Each source ``.gz`` is normalized once into a resumable JSONL gzip
shard.  Normalized author records are then hash-partitioned on disk, deduplicated
by author/version with bounded memory, and exported to the files consumed by the
sci-mobility Word2Vec workflow.

Default outputs under ``--output-root``::

    preprocess_manifest.json
    Data/Raw/all-years_transitions.txt
    Data/Raw/all-years_annual_affiliation_groups.csv
    Data/Additional/institution_lookup.txt
    Data/Additional/all-years_inst_sizes_author.txt

The internal ``.openalex_preprocess_cache`` directory contains ordinary gzip
JSONL shards used only for restart/re-export.  Training reads the final
``transitions.txt`` and never opens the OpenAlex snapshot or these cache shards.
Use ``--discard-normalized-cache`` to remove them after a successful export.

Only Python's standard library is required.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence


SCHEMA_VERSION = "3-file-only"
DEFAULT_DATA_ROOT = Path("/data2/openAlex/openalex_snapshot/data")
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "sci_mobility_openalex_data"
MANIFEST_NAME = "preprocess_manifest.json"
CACHE_DIR_NAME = ".openalex_preprocess_cache"
LOCK_NAME = ".s00_preprocess_openalex_snapshot.lock"
LEGACY_SQLITE_FILES = (
    "openalex_preprocessed.sqlite3",
    "openalex_preprocessed.sqlite3-wal",
    "openalex_preprocessed.sqlite3-shm",
)
DEFAULT_AUTHOR_BUCKETS = 2_048
DEFAULT_MAX_BUCKET_MIB = 32
DEFAULT_ROUTE_BUFFER_MIB = 128


@dataclass(frozen=True)
class NormalizeTask:
    entity: str
    source_path: str
    source_relative_path: str
    source_root: str
    source_size: int
    source_mtime_ns: int
    data_path: str
    metadata_path: str
    normalization_signature: str
    start_year: int | None
    end_year: int | None
    id_style: str
    topic_source: str
    field_level: str
    skip_bad_lines: bool
    drop_empty_author_records: bool
    compression_level: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def suffix(value: Any) -> str:
    text = str(value or "").strip().rstrip("/")
    return text.rsplit("/", 1)[-1] if text else ""


def entity_id(value: Any, style: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return suffix(text) if style == "suffix" else text


def field_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    tail = text.rstrip("/").rsplit("/", 1)[-1]
    match = re.search(r"(\d+)$", tail)
    if match:
        return match.group(1)
    return re.sub(r"\s+", "_", tail).strip("_")


def pick_category(topic: dict[str, Any], level: str) -> str:
    nested = topic.get(level)
    if isinstance(nested, dict):
        for key in ("id", "display_name"):
            code = field_code(nested.get(key))
            if code:
                return code
    for key in (f"{level}_id", f"{level}_display_name"):
        code = field_code(topic.get(key))
        if code:
            return code
    if level == "topic":
        for key in ("id", "display_name"):
            code = field_code(topic.get(key))
            if code:
                return code
    return ""


def author_field(record: dict[str, Any], source: str, level: str) -> str:
    primary = "topic_share" if source == "topic_share" else "topics"
    fallback = "topics" if primary == "topic_share" else "topic_share"
    for name in (primary, fallback):
        topics = record.get(name)
        if not isinstance(topics, list):
            continue
        weight_key = "value" if name == "topic_share" else "count"
        best: tuple[float, int, str] | None = None
        for position, topic in enumerate(topics):
            if not isinstance(topic, dict):
                continue
            code = pick_category(topic, level)
            if not code:
                continue
            try:
                weight = float(topic.get(weight_key, 0) or 0)
            except (TypeError, ValueError):
                weight = 0.0
            candidate = (weight, -position, code)
            if best is None or candidate > best:
                best = candidate
        if best is not None:
            return best[2]
    return "0"


def source_updated_date(path: Path) -> str:
    for part in reversed(path.parts):
        if part.startswith("updated_date="):
            return part.split("=", 1)[1]
    return ""


def version_parts(value: Any, fallback: str) -> tuple[int, str]:
    """Create a stable, lexicographically comparable UTC version key."""
    text = str(value or fallback or "").strip()
    if not text:
        return 0, ""
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
        normalized = parsed.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return 1, normalized
    except ValueError:
        return 0, text


def numeric_or_none(value: Any, kind: type[int] | type[float]) -> int | float | None:
    if value in (None, ""):
        return None
    try:
        return kind(value)
    except (TypeError, ValueError):
        return None


def iter_jsonl_gz(path: Path, skip_bad_lines: bool) -> Iterator[tuple[int, dict[str, Any] | None]]:
    with gzip.open(path, "rt", encoding="utf-8", errors="strict") as handle:
        for line_number, line in enumerate(handle, 1):
            cleaned = line.replace("\x00", "").strip()
            if not cleaned:
                continue
            try:
                record = json.loads(cleaned)
            except (json.JSONDecodeError, UnicodeError) as exc:
                if skip_bad_lines:
                    yield line_number, None
                    continue
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if isinstance(record, dict):
                yield line_number, record


def snapshot_files(data_root: Path, entity: str, partition: str) -> list[Path]:
    entity_dir = data_root / entity
    if not entity_dir.is_dir():
        raise FileNotFoundError(f"OpenAlex entity directory not found: {entity_dir}")
    partitions = sorted(
        (path for path in entity_dir.iterdir() if path.is_dir() and path.name.startswith("updated_date=")),
        key=lambda path: path.name,
        reverse=True,
    )
    if partition == "all":
        selected = partitions
    elif partition == "latest":
        selected = partitions[:1]
    else:
        name = partition if partition.startswith("updated_date=") else f"updated_date={partition}"
        selected = [entity_dir / name]
    files = [file for directory in selected if directory.is_dir() for file in sorted(directory.glob("*.gz"))]
    if not files:
        raise FileNotFoundError(f"No .gz files found for {entity!r}, partition={partition!r}")
    return files


def source_fingerprint(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def normalized_shard_paths(cache_root: Path, entity: str, relative_path: str) -> tuple[Path, Path]:
    digest = hashlib.sha256(relative_path.encode("utf-8")).hexdigest()
    directory = cache_root / "normalized" / entity
    return directory / f"{digest}.jsonl.gz", directory / f"{digest}.meta.json"


def source_index(files: Sequence[Path], data_root: Path) -> list[dict[str, Any]]:
    records = []
    for path in files:
        size, mtime_ns = source_fingerprint(path)
        records.append(
            {
                "relative_path": path.relative_to(data_root).as_posix(),
                "size": size,
                "mtime_ns": mtime_ns,
            }
        )
    return records


def build_task(
    entity: str,
    source: Path,
    source_record: dict[str, Any],
    data_root: Path,
    cache_root: Path,
    normalization_signature: str,
    args: argparse.Namespace,
) -> NormalizeTask:
    relative = str(source_record["relative_path"])
    data_path, metadata_path = normalized_shard_paths(cache_root, entity, relative)
    return NormalizeTask(
        entity=entity,
        source_path=str(source),
        source_relative_path=relative,
        source_root=str(data_root),
        source_size=int(source_record["size"]),
        source_mtime_ns=int(source_record["mtime_ns"]),
        data_path=str(data_path),
        metadata_path=str(metadata_path),
        normalization_signature=normalization_signature,
        start_year=args.start_year,
        end_year=args.end_year,
        id_style=args.id_style,
        topic_source=args.topic_source,
        field_level=args.field_level,
        skip_bad_lines=args.skip_bad_lines,
        drop_empty_author_records=args.drop_empty_author_records,
        compression_level=args.cache_compression_level,
    )


def cached_shard(task: NormalizeTask) -> dict[str, Any]:
    metadata_path = Path(task.metadata_path)
    data_path = Path(task.data_path)
    metadata = load_json(metadata_path)
    expected = {
        "schema_version": SCHEMA_VERSION,
        "entity": task.entity,
        "source_root": task.source_root,
        "source_relative_path": task.source_relative_path,
        "source_size": task.source_size,
        "source_mtime_ns": task.source_mtime_ns,
        "normalization_signature": task.normalization_signature,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        return {}
    if not data_path.is_file():
        return {}
    try:
        if data_path.stat().st_size != int(metadata.get("output_bytes", -1)):
            return {}
        if int(metadata.get("uncompressed_bytes", -1)) < 0:
            return {}
    except (OSError, TypeError, ValueError):
        return {}
    metadata = dict(metadata)
    metadata["data_path"] = str(data_path)
    return metadata


def normalize_author_file(task: NormalizeTask) -> dict[str, Any]:
    started = time.time()
    source = Path(task.source_path)
    data_path = Path(task.data_path)
    metadata_path = Path(task.metadata_path)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    temp = data_path.with_name(data_path.name + f".{os.getpid()}.tmp")
    fallback_date = source_updated_date(source)
    json_rows = records = transition_rows = annual_groups = bad_lines = uncompressed_bytes = 0
    tie_prefix = f"{fallback_date}/{source.name}"
    try:
        if source_fingerprint(source) != (task.source_size, task.source_mtime_ns):
            raise RuntimeError(f"Source changed before parsing started: {source}")
        with gzip.open(
            temp,
            "wt",
            encoding="utf-8",
            newline="\n",
            compresslevel=task.compression_level,
        ) as output:
            for line_number, record in iter_jsonl_gz(source, task.skip_bad_lines):
                if record is None:
                    bad_lines += 1
                    continue
                json_rows += 1
                author_id = entity_id(record.get("id"), task.id_style)
                if not author_id:
                    continue
                by_year: dict[int, set[str]] = {}
                affiliations = record.get("affiliations")
                if isinstance(affiliations, list):
                    for affiliation in affiliations:
                        if not isinstance(affiliation, dict):
                            continue
                        institution = affiliation.get("institution")
                        if not isinstance(institution, dict):
                            continue
                        org_id = entity_id(institution.get("id"), task.id_style)
                        years = affiliation.get("years")
                        if not org_id or not isinstance(years, list):
                            continue
                        for raw_year in years:
                            try:
                                year = int(raw_year)
                            except (TypeError, ValueError):
                                continue
                            if (task.start_year is None or year >= task.start_year) and (
                                task.end_year is None or year <= task.end_year
                            ):
                                by_year.setdefault(year, set()).add(org_id)
                groups = [[year, sorted(orgs)] for year, orgs in sorted(by_year.items())]
                if not groups and task.drop_empty_author_records:
                    continue
                code = author_field(record, task.topic_source, task.field_level) if groups else "0"
                valid_version, version = version_parts(record.get("updated_date"), fallback_date)
                tie_breaker = f"{tie_prefix}:{line_number:012d}"
                normalized = [author_id, valid_version, version, tie_breaker, code, groups]
                normalized_line = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n"
                output.write(normalized_line)
                uncompressed_bytes += len(normalized_line.encode("utf-8"))
                records += 1
                annual_groups += len(groups)
                transition_rows += sum(len(orgs) for _, orgs in groups)
        if source_fingerprint(source) != (task.source_size, task.source_mtime_ns):
            raise RuntimeError(f"Source changed while it was being parsed: {source}")
        os.replace(temp, data_path)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "entity": "authors",
            "source_root": task.source_root,
            "source_relative_path": task.source_relative_path,
            "source_size": task.source_size,
            "source_mtime_ns": task.source_mtime_ns,
            "normalization_signature": task.normalization_signature,
            "data_path": str(data_path),
            "output_bytes": data_path.stat().st_size,
            "uncompressed_bytes": uncompressed_bytes,
            "json_rows": json_rows,
            "records": records,
            "transition_rows_before_deduplication": transition_rows,
            "annual_groups_before_deduplication": annual_groups,
            "bad_lines": bad_lines,
            "seconds": round(time.time() - started, 3),
        }
        write_json_atomic(metadata_path, metadata)
        return metadata
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def normalize_institution_file(task: NormalizeTask) -> dict[str, Any]:
    started = time.time()
    source = Path(task.source_path)
    data_path = Path(task.data_path)
    metadata_path = Path(task.metadata_path)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    temp = data_path.with_name(data_path.name + f".{os.getpid()}.tmp")
    fallback_date = source_updated_date(source)
    json_rows = records = bad_lines = uncompressed_bytes = 0
    tie_prefix = f"{fallback_date}/{source.name}"
    try:
        if source_fingerprint(source) != (task.source_size, task.source_mtime_ns):
            raise RuntimeError(f"Source changed before parsing started: {source}")
        with gzip.open(
            temp,
            "wt",
            encoding="utf-8",
            newline="\n",
            compresslevel=task.compression_level,
        ) as output:
            for line_number, record in iter_jsonl_gz(source, task.skip_bad_lines):
                if record is None:
                    bad_lines += 1
                    continue
                json_rows += 1
                raw_id = str(record.get("id") or "").strip()
                org_id = entity_id(raw_id, task.id_style)
                if not org_id:
                    continue
                geo = record.get("geo") if isinstance(record.get("geo"), dict) else {}
                valid_version, version = version_parts(record.get("updated_date"), fallback_date)
                tie_breaker = f"{tie_prefix}:{line_number:012d}"
                normalized = [
                    org_id,
                    valid_version,
                    version,
                    tie_breaker,
                    raw_id,
                    record.get("ror"),
                    record.get("display_name"),
                    record.get("type"),
                    geo.get("city"),
                    geo.get("region"),
                    geo.get("country_code") or record.get("country_code"),
                    geo.get("country"),
                    numeric_or_none(geo.get("latitude"), float),
                    numeric_or_none(geo.get("longitude"), float),
                    numeric_or_none(record.get("works_count"), int),
                    numeric_or_none(record.get("cited_by_count"), int),
                ]
                normalized_line = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")) + "\n"
                output.write(normalized_line)
                uncompressed_bytes += len(normalized_line.encode("utf-8"))
                records += 1
        if source_fingerprint(source) != (task.source_size, task.source_mtime_ns):
            raise RuntimeError(f"Source changed while it was being parsed: {source}")
        os.replace(temp, data_path)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "entity": "institutions",
            "source_root": task.source_root,
            "source_relative_path": task.source_relative_path,
            "source_size": task.source_size,
            "source_mtime_ns": task.source_mtime_ns,
            "normalization_signature": task.normalization_signature,
            "data_path": str(data_path),
            "output_bytes": data_path.stat().st_size,
            "uncompressed_bytes": uncompressed_bytes,
            "json_rows": json_rows,
            "records": records,
            "bad_lines": bad_lines,
            "seconds": round(time.time() - started, 3),
        }
        write_json_atomic(metadata_path, metadata)
        return metadata
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def normalize_institutions(tasks: Sequence[NormalizeTask]) -> list[dict[str, Any]]:
    results = []
    for index, task in enumerate(tasks, 1):
        metadata = cached_shard(task)
        if metadata:
            print(f"[institutions {index}/{len(tasks)}] cached {task.source_path}", flush=True)
        else:
            metadata = normalize_institution_file(task)
            print(
                f"[institutions {index}/{len(tasks)}] records={metadata['records']:,} "
                f"bad={metadata['bad_lines']:,} {task.source_path}",
                flush=True,
            )
        results.append(metadata)
    return results


def normalize_authors(tasks: Sequence[NormalizeTask], workers: int) -> list[dict[str, Any]]:
    results_by_source: dict[str, dict[str, Any]] = {}
    remaining = []
    for task in tasks:
        metadata = cached_shard(task)
        if metadata:
            results_by_source[task.source_relative_path] = metadata
        else:
            remaining.append(task)
    cached = len(tasks) - len(remaining)
    if cached:
        print(f"[authors] cached files={cached:,}; remaining={len(remaining):,}", flush=True)
    if remaining:
        worker_count = max(1, min(workers, len(remaining)))
        pending_limit = worker_count * 2
        iterator = iter(remaining)
        pending: dict[Any, NormalizeTask] = {}
        completed = 0

        def submit_one(pool: ProcessPoolExecutor) -> bool:
            try:
                task = next(iterator)
            except StopIteration:
                return False
            pending[pool.submit(normalize_author_file, task)] = task
            return True

        try:
            with ProcessPoolExecutor(max_workers=worker_count) as pool:
                for _ in range(min(pending_limit, len(remaining))):
                    submit_one(pool)
                while pending:
                    done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                    for future in done:
                        task = pending.pop(future)
                        try:
                            metadata = future.result()
                        except Exception as exc:
                            raise RuntimeError(f"Failed normalizing {task.source_path}: {exc}") from exc
                        results_by_source[task.source_relative_path] = metadata
                        completed += 1
                        seconds = max(0.001, float(metadata.get("seconds", 0)))
                        print(
                            f"[authors {completed}/{len(remaining)}] records={metadata['records']:,} "
                            f"pairs={metadata['transition_rows_before_deduplication']:,} "
                            f"bad={metadata['bad_lines']:,} "
                            f"rate={metadata['records'] / seconds:,.0f}/s {task.source_path}",
                            flush=True,
                        )
                        submit_one(pool)
        except Exception:
            print(traceback.format_exc(), file=sys.stderr)
            raise
    return [results_by_source[task.source_relative_path] for task in tasks]


def record_key(record: list[Any]) -> tuple[int, str, str]:
    return int(record[1]), str(record[2]), str(record[3])


def merge_institutions(shards: Sequence[dict[str, Any]]) -> tuple[dict[str, list[Any]], dict[str, int]]:
    latest: dict[str, list[Any]] = {}
    duplicate_versions = equal_date_conflicts = 0
    for shard in shards:
        with gzip.open(Path(str(shard["data_path"])), "rt", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                org_id = str(record[0])
                existing = latest.get(org_id)
                if existing is not None:
                    duplicate_versions += 1
                    if record[1:3] == existing[1:3] and record[4:] != existing[4:]:
                        equal_date_conflicts += 1
                if existing is None or record_key(record) > record_key(existing):
                    latest[org_id] = record
    return latest, {
        "institutions": len(latest),
        "duplicate_versions": duplicate_versions,
        "equal_date_conflicts": equal_date_conflicts,
    }


def bucket_number(author_id: str, bucket_count: int) -> int:
    digest = hashlib.sha256(author_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % bucket_count


def valid_route_cache(route_root: Path, route_revision: str) -> list[Path]:
    marker = load_json(route_root / "route_manifest.json")
    if marker.get("route_revision") != route_revision:
        return []
    records = marker.get("buckets")
    if not isinstance(records, list):
        return []
    paths = []
    for record in records:
        if not isinstance(record, dict):
            return []
        path = route_root / str(record.get("name", ""))
        try:
            expected_size = int(record.get("bytes", -1))
        except (TypeError, ValueError):
            return []
        if not path.is_file() or path.stat().st_size != expected_size:
            return []
        paths.append(path)
    return paths


def route_author_shards(
    shards: Sequence[dict[str, Any]],
    route_root: Path,
    route_revision: str,
    bucket_count: int,
    buffer_limit_bytes: int,
    skip_disk_space_check: bool,
) -> tuple[list[Path], int]:
    cached = valid_route_cache(route_root, route_revision)
    if cached:
        marker = load_json(route_root / "route_manifest.json")
        print(f"[route] cached buckets={len(cached):,}", flush=True)
        return cached, int(marker.get("records", 0))
    if route_root.exists():
        shutil.rmtree(route_root)
    route_root.mkdir(parents=True, exist_ok=True)
    expected_route_bytes = sum(int(shard["uncompressed_bytes"]) for shard in shards)
    free_bytes = shutil.disk_usage(route_root).free
    gib = 1024**3
    if not skip_disk_space_check and free_bytes < int(expected_route_bytes * 1.05):
        raise RuntimeError(
            f"Not enough free space for routed author buckets: need at least "
            f"{expected_route_bytes / gib:.1f} GiB, available {free_bytes / gib:.1f} GiB. "
            "Free disk space or use a larger --output-root."
        )
    print(
        f"[disk] routed author data≈{expected_route_bytes / gib:.1f} GiB; "
        f"free={free_bytes / gib:.1f} GiB",
        flush=True,
    )
    if free_bytes < expected_route_bytes * 3:
        print(
            "WARNING: free space is less than three times the routed data estimate; "
            "final temporary exports may exhaust the disk.",
            file=sys.stderr,
            flush=True,
        )

    buffers: dict[int, list[str]] = {}
    buffered_bytes = records = flushes = 0

    def flush_buffers() -> None:
        nonlocal buffered_bytes, flushes
        if not buffers:
            return
        for number in sorted(buffers):
            path = route_root / f"bucket_{number:05d}.jsonl"
            with path.open("a", encoding="utf-8", newline="") as handle:
                handle.writelines(buffers[number])
        buffers.clear()
        buffered_bytes = 0
        flushes += 1

    for index, shard in enumerate(shards, 1):
        with gzip.open(Path(str(shard["data_path"])), "rt", encoding="utf-8") as source:
            for line in source:
                record = json.loads(line)
                number = bucket_number(str(record[0]), bucket_count)
                buffers.setdefault(number, []).append(line)
                buffered_bytes += len(line)
                records += 1
                if buffered_bytes >= buffer_limit_bytes:
                    flush_buffers()
        if index % 100 == 0 or index == len(shards):
            print(f"[route {index}/{len(shards)}] records={records:,} flushes={flushes:,}", flush=True)
    flush_buffers()
    bucket_paths = sorted(route_root.glob("bucket_*.jsonl"))
    marker = {
        "schema_version": SCHEMA_VERSION,
        "route_revision": route_revision,
        "records": records,
        "expected_route_bytes": expected_route_bytes,
        "buckets": [{"name": path.name, "bytes": path.stat().st_size} for path in bucket_paths],
    }
    write_json_atomic(route_root / "route_manifest.json", marker)
    return bucket_paths, records


def period_label(start_year: int | None, end_year: int | None) -> str:
    if start_year is None and end_year is None:
        return "all-years"
    if start_year is None:
        return f"through-{end_year}"
    if end_year is None:
        return f"from-{start_year}"
    return f"{start_year}-{end_year}"


def transition_destinations(
    output_root: Path,
    start_year: int | None,
    end_year: int | None,
) -> dict[str, Path]:
    years = period_label(start_year, end_year)
    return {
        "transitions": output_root / "Data" / "Raw" / f"{years}_transitions.txt",
        "annual_affiliation_groups": output_root
        / "Data"
        / "Raw"
        / f"{years}_annual_affiliation_groups.csv",
        "institution_lookup": output_root / "Data" / "Additional" / "institution_lookup.txt",
        "institution_sizes": output_root / "Data" / "Additional" / f"{years}_inst_sizes_author.txt",
    }


def atomic_text_path(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination.with_name(destination.name + f".{os.getpid()}.tmp")


def export_outputs(
    bucket_paths: Sequence[Path],
    institutions: dict[str, list[Any]],
    destinations: dict[str, Path],
    require_metadata: bool,
    require_coordinates: bool,
    max_bucket_bytes: int,
) -> tuple[dict[str, int], dict[str, int | None]]:
    if require_coordinates:
        allowed_orgs: set[str] | None = {
            org_id for org_id, record in institutions.items() if record[12] is not None and record[13] is not None
        }
    elif require_metadata:
        allowed_orgs = set(institutions)
    else:
        allowed_orgs = None
    temp_paths = {name: atomic_text_path(path) for name, path in destinations.items()}
    transition_rows = annual_groups = duplicate_versions = equal_date_conflicts = empty_latest_authors = 0
    observed_min_year: int | None = None
    observed_max_year: int | None = None
    institution_sizes: Counter[tuple[str, int]] = Counter()
    try:
        with temp_paths["transitions"].open("w", newline="", encoding="utf-8") as transition_handle, temp_paths[
            "annual_affiliation_groups"
        ].open("w", newline="", encoding="utf-8-sig") as group_handle:
            transition_writer = csv.writer(transition_handle, delimiter="\t", lineterminator="\n")
            transition_writer.writerow(["cluster_id", "pub_year", "cwts_org_no", "LR_main_field_no"])
            group_writer = csv.writer(group_handle, lineterminator="\n")
            group_writer.writerow(
                [
                    "cluster_id",
                    "pub_year",
                    "institution_ids_json",
                    "institution_group_token",
                    "group_size",
                    "LR_main_field_no",
                ]
            )
            for index, bucket_path in enumerate(bucket_paths, 1):
                size = bucket_path.stat().st_size
                if size > max_bucket_bytes:
                    raise RuntimeError(
                        f"Author bucket is {size / (1024 ** 2):.1f} MiB, above the configured limit: "
                        f"{bucket_path}. Increase --author-buckets and rerun."
                    )
                latest: dict[str, list[Any]] = {}
                with bucket_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        record = json.loads(line)
                        author_id = str(record[0])
                        existing = latest.get(author_id)
                        if existing is not None:
                            duplicate_versions += 1
                            if record[1:3] == existing[1:3] and record[4:] != existing[4:]:
                                equal_date_conflicts += 1
                        if existing is None or record_key(record) > record_key(existing):
                            latest[author_id] = record
                for author_id in sorted(latest):
                    record = latest[author_id]
                    field = str(record[4] or "0")
                    groups = record[5] if isinstance(record[5], list) else []
                    wrote_author = False
                    for raw_year, raw_orgs in groups:
                        year = int(raw_year)
                        orgs = sorted(
                            {
                                str(org_id)
                                for org_id in raw_orgs
                                if allowed_orgs is None or str(org_id) in allowed_orgs
                            }
                        )
                        if not orgs:
                            continue
                        wrote_author = True
                        observed_min_year = year if observed_min_year is None else min(observed_min_year, year)
                        observed_max_year = year if observed_max_year is None else max(observed_max_year, year)
                        for org_id in orgs:
                            transition_writer.writerow([author_id, year, org_id, field])
                            transition_rows += 1
                            institution_sizes[(org_id, year)] += 1
                        group_writer.writerow(
                            [
                                author_id,
                                year,
                                json.dumps(orgs, ensure_ascii=False, separators=(",", ":")),
                                "|".join(orgs),
                                len(orgs),
                                field,
                            ]
                        )
                        annual_groups += 1
                    if not wrote_author:
                        empty_latest_authors += 1
                if index % 100 == 0 or index == len(bucket_paths):
                    print(
                        f"[deduplicate {index}/{len(bucket_paths)}] transitions={transition_rows:,} "
                        f"groups={annual_groups:,}",
                        flush=True,
                    )
        with temp_paths["institution_sizes"].open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["cwts_org_no", "pub_year", "person_count"])
            for (org_id, year), count in sorted(institution_sizes.items()):
                writer.writerow([org_id, year, count])
        lookup_columns = [
            "cwts_org_no",
            "openalex_institution_id",
            "ror",
            "full_name",
            "type",
            "city",
            "region",
            "country_iso_alpha",
            "country",
            "latitude",
            "longitude",
            "works_count",
            "cited_by_count",
        ]
        lookup_rows = 0
        with temp_paths["institution_lookup"].open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(lookup_columns)
            for org_id in sorted(institutions):
                if allowed_orgs is not None and org_id not in allowed_orgs:
                    continue
                record = institutions[org_id]
                writer.writerow(["" if value is None else value for value in [record[0], *record[4:]]])
                lookup_rows += 1
        for name, destination in destinations.items():
            os.replace(temp_paths[name], destination)
        return (
            {
                "transitions": transition_rows,
                "annual_affiliation_groups": annual_groups,
                "institution_lookup": lookup_rows,
                "institution_sizes": len(institution_sizes),
            },
            {
                "duplicate_author_versions": duplicate_versions,
                "equal_date_author_conflicts": equal_date_conflicts,
                "empty_latest_authors": empty_latest_authors,
                "observed_min_year": observed_min_year,
                "observed_max_year": observed_max_year,
            },
        )
    except Exception:
        for temp in temp_paths.values():
            temp.unlink(missing_ok=True)
        raise


def exports_current(
    manifest: dict[str, Any],
    source_revision: str,
    export_signature: str,
    destinations: dict[str, Path],
) -> bool:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        return False
    if not manifest.get("exports_complete"):
        return False
    if manifest.get("source_revision") != source_revision:
        return False
    if manifest.get("export_signature") != export_signature:
        return False
    exports = manifest.get("exports")
    if not isinstance(exports, dict):
        return False
    for name, destination in destinations.items():
        record = exports.get(name)
        if not isinstance(record, dict) or not destination.is_file():
            return False
        try:
            if Path(str(record["path"])).resolve() != destination.resolve():
                return False
            if int(record["bytes"]) != destination.stat().st_size:
                return False
        except (KeyError, OSError, TypeError, ValueError):
            return False
    return True


def acquire_lock(path: Path, force_unlock: bool) -> int:
    if force_unlock:
        path.unlink(missing_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(
            f"Another preprocessing run may be active: {path}. "
            "If this is a stale lock, rerun with --force-unlock."
        ) from exc
    os.write(descriptor, f"pid={os.getpid()} started={utc_now()}\n".encode("utf-8"))
    return descriptor


def release_lock(descriptor: int | None, path: Path) -> None:
    if descriptor is not None:
        os.close(descriptor)
        path.unlink(missing_ok=True)


def safe_output_root(path: Path) -> None:
    resolved = path.resolve()
    if resolved == Path(resolved.anchor) or resolved.parent == resolved:
        raise ValueError(f"Unsafe output root: {resolved}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="File-only OpenAlex .gz preprocessing for scientific-mobility training."
    )
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--partition",
        default="all",
        help=(
            "all (default), YYYY-MM-DD, or updated_date=YYYY-MM-DD; "
            "latest reads only the newest directory and is not a full-snapshot shortcut"
        ),
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=None,
        help="Optional lower year bound; omit to retain every available year.",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=None,
        help="Optional upper year bound; omit to retain every available year.",
    )
    parser.add_argument("--id-style", choices=["suffix", "url"], default="suffix")
    parser.add_argument("--topic-source", choices=["topic_share", "topics"], default="topic_share")
    parser.add_argument("--field-level", choices=["domain", "field", "subfield", "topic"], default="field")
    parser.add_argument("--workers", type=int, default=max(1, min(16, (os.cpu_count() or 2) - 1)))
    parser.add_argument("--author-buckets", type=int, default=DEFAULT_AUTHOR_BUCKETS)
    parser.add_argument("--max-bucket-mib", type=int, default=DEFAULT_MAX_BUCKET_MIB)
    parser.add_argument("--route-buffer-mib", type=int, default=DEFAULT_ROUTE_BUFFER_MIB)
    parser.add_argument("--cache-compression-level", type=int, choices=range(1, 10), default=1)
    parser.add_argument("--require-institution-metadata", action="store_true")
    parser.add_argument("--require-coordinates", action="store_true")
    parser.add_argument("--skip-bad-lines", action="store_true")
    parser.add_argument(
        "--drop-empty-author-records",
        action="store_true",
        help=(
            "Skip authors with no affiliations in the selected years. Faster for a clean OpenAlex "
            "snapshot, but unsafe if the input mixes historical versions of the same author."
        ),
    )
    parser.add_argument(
        "--skip-disk-space-check",
        action="store_true",
        help="Bypass the routed-bucket free-space check (not recommended).",
    )
    parser.add_argument(
        "--force-export",
        action="store_true",
        help="Regenerate final files; reuse normalized file shards when they are still valid.",
    )
    parser.add_argument(
        "--discard-normalized-cache",
        action="store_true",
        help="Remove normalized restart/re-export shards after a successful export.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete this script's file cache, manifest, and any legacy SQLite cache before rebuilding.",
    )
    parser.add_argument(
        "--force-unlock",
        action="store_true",
        help="Remove a stale lock file first; do not use while another run is active.",
    )
    args = parser.parse_args()
    if args.start_year is not None and args.end_year is not None and args.start_year > args.end_year:
        parser.error("--start-year must be <= --end-year")
    for name in ("workers", "author_buckets", "max_bucket_mib", "route_buffer_mib"):
        if getattr(args, name) < 1:
            parser.error(f"--{name.replace('_', '-')} must be >= 1")
    if args.require_coordinates:
        args.require_institution_metadata = True
    return args


def main() -> int:
    args = parse_args()
    args.data_root = args.data_root.resolve()
    args.output_root = args.output_root.resolve()
    safe_output_root(args.output_root)
    args.output_root.mkdir(parents=True, exist_ok=True)
    lock_path = args.output_root / LOCK_NAME
    lock_descriptor: int | None = None
    started = time.time()
    try:
        lock_descriptor = acquire_lock(lock_path, args.force_unlock)
        cache_root = args.output_root / CACHE_DIR_NAME
        manifest_path = args.output_root / MANIFEST_NAME
        if args.rebuild:
            if cache_root.exists():
                shutil.rmtree(cache_root)
            legacy_spool = args.output_root / ".openalex_preprocess_spool"
            if legacy_spool.exists():
                shutil.rmtree(legacy_spool)
            for filename in LEGACY_SQLITE_FILES:
                (args.output_root / filename).unlink(missing_ok=True)
            manifest_path.unlink(missing_ok=True)

        institution_files = snapshot_files(args.data_root, "institutions", args.partition)
        author_files = snapshot_files(args.data_root, "authors", args.partition)
        institution_sources = source_index(institution_files, args.data_root)
        author_sources = source_index(author_files, args.data_root)
        normalization_configuration = {
            "schema_version": SCHEMA_VERSION,
            "data_root": str(args.data_root),
            "partition": args.partition,
            "start_year": args.start_year,
            "end_year": args.end_year,
            "id_style": args.id_style,
            "topic_source": args.topic_source,
            "field_level": args.field_level,
            "skip_bad_lines": args.skip_bad_lines,
            "drop_empty_author_records": args.drop_empty_author_records,
        }
        normalization_signature = stable_hash(normalization_configuration)
        source_payload = {
            "data_root": str(args.data_root),
            "institutions": institution_sources,
            "authors": author_sources,
        }
        source_revision = stable_hash(source_payload)
        export_configuration = {
            "normalization_signature": normalization_signature,
            "require_institution_metadata": args.require_institution_metadata,
            "require_coordinates": args.require_coordinates,
            "author_buckets": args.author_buckets,
        }
        export_signature = stable_hash(export_configuration)
        destinations = transition_destinations(args.output_root, args.start_year, args.end_year)
        manifest = load_json(manifest_path)
        print(
            f"source={args.data_root} institutions_gz={len(institution_files):,} "
            f"authors_gz={len(author_files):,} workers={args.workers}",
            flush=True,
        )
        if not args.force_export and exports_current(
            manifest,
            source_revision,
            export_signature,
            destinations,
        ):
            if args.discard_normalized_cache:
                shutil.rmtree(cache_root, ignore_errors=True)
            print(
                f"done in {time.time() - started:.1f}s; source files and exports are current; "
                "no gzip data read and no output rewritten",
                flush=True,
            )
            return 0

        institution_tasks = [
            build_task(
                "institutions",
                path,
                record,
                args.data_root,
                cache_root,
                normalization_signature,
                args,
            )
            for path, record in zip(institution_files, institution_sources)
        ]
        author_tasks = [
            build_task(
                "authors",
                path,
                record,
                args.data_root,
                cache_root,
                normalization_signature,
                args,
            )
            for path, record in zip(author_files, author_sources)
        ]
        institution_shards = normalize_institutions(institution_tasks)
        author_shards = normalize_authors(author_tasks, args.workers)
        institutions, institution_stats = merge_institutions(institution_shards)

        route_revision = stable_hash(
            {
                "source_revision": source_revision,
                "normalization_signature": normalization_signature,
                "author_buckets": args.author_buckets,
            }
        )
        route_root = cache_root / "routed_authors"
        bucket_paths, routed_records = route_author_shards(
            author_shards,
            route_root,
            route_revision,
            args.author_buckets,
            args.route_buffer_mib * 1024 * 1024,
            args.skip_disk_space_check,
        )
        output_rows, author_stats = export_outputs(
            bucket_paths,
            institutions,
            destinations,
            args.require_institution_metadata,
            args.require_coordinates,
            args.max_bucket_mib * 1024 * 1024,
        )
        exports = {
            name: {
                "path": str(path),
                "rows": output_rows[name],
                "bytes": path.stat().st_size,
            }
            for name, path in destinations.items()
        }
        completed_manifest = {
            "schema_version": SCHEMA_VERSION,
            "exports_complete": True,
            "created_at": utc_now(),
            "seconds": round(time.time() - started, 3),
            "normalization_configuration": normalization_configuration,
            "normalization_signature": normalization_signature,
            "export_configuration": export_configuration,
            "export_signature": export_signature,
            "source_revision": source_revision,
            "sources": source_payload,
            "processing": {
                "normalized_institution_files": len(institution_shards),
                "normalized_author_files": len(author_shards),
                "routed_author_records": routed_records,
                "institution_deduplication": institution_stats,
                "author_deduplication": author_stats,
            },
            "exports": exports,
            "normalized_cache_retained": not args.discard_normalized_cache,
        }
        write_json_atomic(manifest_path, completed_manifest)

        if args.discard_normalized_cache:
            shutil.rmtree(cache_root, ignore_errors=True)
        else:
            shutil.rmtree(route_root, ignore_errors=True)
        print(
            f"done in {time.time() - started:.1f}s; transitions={output_rows['transitions']:,}; "
            f"groups={output_rows['annual_affiliation_groups']:,}; no SQLite created",
            flush=True,
        )
        return 0
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        release_lock(lock_descriptor, lock_path)


if __name__ == "__main__":
    raise SystemExit(main())
