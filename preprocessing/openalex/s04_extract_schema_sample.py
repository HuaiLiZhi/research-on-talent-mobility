#!/usr/bin/env python3
"""Scan ALL OpenAlex raw entities and collect the complete set of JSON field
paths (with types and example values) that appear, then emit a markdown
schema/sample document.

Resumable: each entity's schema is written to a partial JSON immediately, so a
re-run skips entities already scanned (use --force to rescan).
"""
from __future__ import annotations
import argparse, gzip, json, os, time, multiprocessing as mp

ROOT = "/data2/openAlex/openalex_snapshot/data"
OUT_MD = "/data2/openAlex/OPENALEX_SCHEMA_SAMPLE.md"
MAX_KEYS_MAP = 100
MAX_LIST_ITEMS = 50
DYNAMIC_KEYS = {"abstract_inverted_index"}   # never expand these dict keys

def walk(obj, path, out, depth=0):
    if depth > 14:
        return
    if isinstance(obj, dict):
        leaf = path.rsplit(".", 1)[-1]
        e = out.setdefault(path, {"types": set(), "example": None})
        if leaf in DYNAMIC_KEYS or len(obj) > MAX_KEYS_MAP:
            e["types"].add("object(map)")
            if e["example"] is None and obj:
                e["example"] = "keys like: " + ", ".join(map(str, list(obj.keys())[:3]))
            return
        e["types"].add("object")
        for k, v in obj.items():
            walk(v, (path + "." + k) if path else k, out, depth + 1)
    elif isinstance(obj, list):
        e = out.setdefault(path, {"types": set(), "example": None})
        e["types"].add("array")
        ep = path + "[]"
        if not obj:
            return
        first = obj[0]
        if isinstance(first, (dict, list)):
            for it in obj[:MAX_LIST_ITEMS]:
                walk(it, ep, out, depth + 1)
        else:
            e2 = out.setdefault(ep, {"types": set(), "example": None})
            e2["types"].add("null" if first is None else type(first).__name__)
            if e2["example"] is None and first is not None:
                e2["example"] = str(first)[:160]
    else:
        e = out.setdefault(path, {"types": set(), "example": None})
        e["types"].add("null" if obj is None else type(obj).__name__)
        if e["example"] is None and obj is not None:
            e["example"] = str(obj)[:160]

def scan_files(files):
    out = {}
    n = 0
    for f in files:
        try:
            with gzip.open(f, "rb") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    walk(rec, "", out)
                    n += 1
        except Exception:
            pass
    return ({k: {"types": sorted(v["types"]), "example": v["example"]} for k, v in out.items()}, n)

def merge_into(acc, part):
    for k, v in part.items():
        e = acc.setdefault(k, {"types": set(), "example": None})
        e["types"].update(v["types"])
        if e["example"] is None and v["example"] is not None:
            e["example"] = v["example"]

def sample_record(f):
    with gzip.open(f, "rb") as fh:
        for line in fh:
            if line.strip():
                try:
                    return json.loads(line)
                except Exception:
                    continue
    return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", default=ROOT)
    ap.add_argument("--out-md", default=OUT_MD)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--entities", default="", help="comma list; default all")
    ap.add_argument("--force", action="store_true", help="rescan even if partial exists")
    a = ap.parse_args()

    parts_dir = os.path.join(os.path.dirname(a.out_md), "_openalex_schema_parts")
    os.makedirs(parts_dir, exist_ok=True)
    ents = ([e.strip() for e in a.entities.split(",") if e.strip()]
            or sorted(d for d in os.listdir(a.data_root)
                      if os.path.isdir(os.path.join(a.data_root, d))))

    for ent in ents:
        part_path = os.path.join(parts_dir, ent + ".json")
        if os.path.exists(part_path) and not a.force:
            print("[schema] %s cached, skip" % ent, flush=True)
            continue
        d = os.path.join(a.data_root, ent)
        files = sorted(f for f in (os.path.join(dp, fn)
                       for dp, _, fns in os.walk(d) for fn in fns) if f.endswith(".gz"))
        if not files:
            continue
        t0 = time.time()
        acc = {}
        nrec = 0
        if len(files) > 40:
            with mp.Pool(a.workers) as pool:
                for part, n in pool.imap_unordered(scan_files, [[f] for f in files], chunksize=4):
                    merge_into(acc, part); nrec += n
        else:
            part, n = scan_files(files)
            merge_into(acc, part); nrec = n
        obj = {"paths": {k: {"types": sorted(v["types"]), "example": v["example"]}
                         for k, v in acc.items()},
               "n_records": nrec, "n_files": len(files),
               "seconds": round(time.time() - t0, 1),
               "sample": sample_record(files[-1])}
        with open(part_path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        print("[schema] %-20s files=%d records=%d paths=%d %.0fs" % (
            ent, len(files), nrec, len(acc), time.time() - t0), flush=True)

    schemas = {}
    for ent in ents:
        p = os.path.join(parts_dir, ent + ".json")
        if os.path.exists(p):
            schemas[ent] = json.load(open(p, encoding="utf-8"))
    write_md(schemas, a.out_md)
    print("wrote", a.out_md, "entities=%d" % len(schemas), flush=True)

def write_md(schemas, out_md):
    L = []
    L.append("# OpenAlex 原始数据字段样例（全量扫描）\n")
    L.append("本文档由全量扫描 `openalex_snapshot/data/` 下所有实体生成，")
    L.append("列出每个实体中出现过的**全部 JSON 字段路径**、类型与样例值，并附一条完整样例记录。\n")
    L.append("> 路径规则：`a.b` 为对象字段，`a[]` 为数组元素，`a[].b` 为数组元素对象字段；")
    L.append("`object(map)` 表示键名动态的映射（如 `abstract_inverted_index`，不展开键）。\n")
    L.append("\n## 目录\n")
    for ent in schemas:
        L.append("- [`%s/`](#%s)" % (ent, ent.replace("-", "")))
    for ent, s in schemas.items():
        L.append("\n---\n")
        L.append("## `%s/`\n" % ent)
        L.append("- 文件数：%d；扫描记录数：%s；耗时：%ss\n" % (
            s["n_files"], format(s["n_records"], ","), s["seconds"]))
        L.append("### 字段清单\n")
        L.append("| 字段路径 | 类型 | 样例值 |")
        L.append("|---|---|---|")
        for p in sorted(s["paths"]):
            v = s["paths"][p]
            types = "/".join(v["types"])
            ex = (v["example"] or "").replace("|", "\\|").replace("\n", " ")
            if len(ex) > 100:
                ex = ex[:100] + "…"
            L.append("| `%s` | %s | %s |" % (p or "(root)", types, ex))
        L.append("\n### 样例记录\n")
        L.append("```json")
        L.append(pretty_sample(s.get("sample")))
        L.append("```\n")
    open(out_md, "w", encoding="utf-8").write("\n".join(L))

def pretty_sample(rec):
    def trunc(o, depth=0):
        if isinstance(o, dict):
            if len(o) > 60:
                ks = list(o.keys())[:5]
                return {k: trunc(o[k], depth + 1) for k in ks} | {"__truncated_keys__": "%d keys" % len(o)}
            return {k: trunc(v, depth + 1) for k, v in o.items()}
        if isinstance(o, list):
            if len(o) > 5:
                return [trunc(x, depth + 1) for x in o[:3]] + ["__%d more__" % (len(o) - 3)]
            return [trunc(x, depth + 1) for x in o]
        if isinstance(o, str) and len(o) > 300:
            return o[:300] + "…"
        return o
    return json.dumps(trunc(rec), ensure_ascii=False, indent=2)

if __name__ == "__main__":
    raise SystemExit(main())
