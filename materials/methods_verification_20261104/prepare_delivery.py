"""Consolidate archived evidence only; never run research analyses."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json
import os
import re
import shutil

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'outputs/methods_evidence_audit_20261104'
SUPPLEMENT = SOURCE / '06_data_enhancement_and_gravity'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def js(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def key(path):
    return str(Path(path).resolve()).replace('\\', '/').casefold()

def writecsv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

paper_before = {p.name: sha(p) for p in (ROOT/'outputs/paper_final').glob('*.tex')}
categories = {
    'fixed': '01_fixed_new_cities',
    'rarefaction': '02_equal_event_sampling',
    'model': '03_models',
    'clean': '04_geographic_cleaning',
    'samples': '05_samples_groups',
    'enhancement': '06_data_enhancement_and_gravity',
}

files = [p for p in SOURCE.rglob('*') if p.is_file()
         and 'inventory' not in p.relative_to(SOURCE).parts
         and p.suffix.lower() != '.zip']
history = {'file_manifest.json', '文件索引.csv', 'delivery_receipt.json', 'package_validation.json'}
copied_map = {}
for path in files:
    relative = path.relative_to(SOURCE)
    target = OUT / (Path('collection_history') / relative if len(relative.parts) == 1 and path.name in history else relative)
    target.parent.mkdir(exist_ok=True, parents=True)
    shutil.copy2(path, target)
    assert sha(path) == sha(target)
    copied_map[key(path)] = target

original = js(SOURCE/'file_manifest.json')
records = []
source_map = {}
for item in original:
    local = Path(item['local_copy'].replace('\\', '/')) if item.get('local_copy') else None
    record = {
        'category': item['category'],
        'role': item['role'],
        'source_path': item['source_path'].replace('\\', '/'),
        'local_copy': local.as_posix() if local else None,
        'bytes': item['bytes'],
        'source_modified_utc': item['modified_utc'],
        'sha256_at_collection': item.get('sha256_current'),
        'sha256_historical': item.get('sha256_historical'),
        'historical_hash_matches': item.get('historical_hash_matches'),
        'evidence': item.get('evidence'),
        'csv_rows': item.get('csv_rows'),
        'csv_columns': item.get('csv_columns'),
        'batch': 'five_original_categories',
    }
    if local:
        assert (OUT/local).is_file()
        assert sha(OUT/local) == record['sha256_at_collection']
        source_map.setdefault(key(item['source_path']), OUT/local)
    records.append(record)

with (SUPPLEMENT/'补充文件索引.csv').open(encoding='utf-8-sig', newline='') as handle:
    supplement = list(csv.DictReader(handle))
for item in supplement:
    local = Path(categories['enhancement'])/item['local_copy']
    assert sha(OUT/local) == item['sha256']
    records.append({
        'category': 'enhancement', 'role': item['role'],
        'source_path': item['source_path'], 'local_copy': local.as_posix(),
        'bytes': int(item['bytes']), 'source_modified_utc': None,
        'sha256_at_collection': item['sha256'], 'sha256_historical': None,
        'historical_hash_matches': None,
        'evidence': 'Supplement collected from existing code/configuration/result files; no scientific reanalysis',
        'csv_rows': None, 'csv_columns': None, 'batch': 'data_enhancement_and_gravity_supplement',
    })
    source_map.setdefault(key(item['source_path']), OUT/local)

for record in records:
    path = Path(record['source_path'])
    try:
        record['project_relative_source'] = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        record['project_relative_source'] = None
    if record['local_copy']:
        record['availability'] = 'included_unchanged_snapshot'
    else:
        record['availability'] = 'local_path_and_version_only'

(OUT/'file_manifest.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
csv_rows = []
for record in records:
    entry = record.copy()
    if entry['csv_columns'] is not None:
        entry['csv_columns'] = json.dumps(entry['csv_columns'], ensure_ascii=False)
    csv_rows.append(entry)
writecsv(OUT/'文件索引.csv', csv_rows)
writecsv(OUT/'大型文件路径与版本.csv', [r for r in csv_rows if not r['local_copy']])

# Make collection reports navigable from a repository checkout. Original source
# snapshots and historical metadata remain byte-identical and are not rewritten.
link_checks = []
source_lookup = {key(r['source_path']): r for r in records}
for document in OUT.rglob('*.md'):
    relative = document.relative_to(OUT)
    if 'original' in relative.parts or 'manuscript_snapshot' in relative.parts:
        continue
    body = document.read_text(encoding='utf-8-sig')
    def replace(match):
        label, raw = match.groups()
        target_string = raw.strip('<>')
        if not re.match(r'^[A-Za-z]:[/\\]', target_string):
            return match.group(0)
        cleaned = re.sub(r':\d+$', '', target_string)
        lookup_key = key(cleaned)
        if lookup_key in copied_map:
            target = copied_map[lookup_key]
        elif lookup_key in source_map:
            target = source_map[lookup_key]
        else:
            # The remaining source paths intentionally identify large local
            # inputs. The main manifest records their versions and exact paths.
            target = OUT/'大型文件路径与版本.csv' if lookup_key in source_lookup else OUT/'文件索引.csv'
        rel = Path(os.path.relpath(target, document.parent)).as_posix()
        assert target.is_file(), target
        link_checks.append(dict(document=relative.as_posix(), old_target=target_string, new_target=rel))
        return f'[{label}](<{rel}>)'
    body = re.sub(r'\[([^\]\n]+)\]\((<[^>\n]+>|[A-Za-z]:[/\\][^\n)]+)\)', replace, body)
    document.write_text(body, encoding='utf-8')

(OUT/'补充材料入口.md').write_text('''# 合集入口

两轮材料现已整合在本目录，统一说明和文件索引以合集为准。

- [合集说明](README.md)
- [多源增强、AI与引力模型核对](06_data_enhancement_and_gravity/多源增强_AI与引力模型_核对说明.md)
- [统一文件索引](文件索引.csv)
- [大型文件路径与版本](大型文件路径与版本.csv)
''', encoding='utf-8')

counts = Counter(r['category'] for r in records)
unique_sources = len({key(r['source_path']) for r in records})
included = sum(bool(r['local_copy']) for r in records)
path_only = len(records)-included

readme = f'''# Methods核验材料合集

整理日期：2026-11-04。此目录合并固定/新增城市、等事件抽样、模型、地理清洗、样本分组，以及多源增强/AI/引力模型两轮核对材料。

本次整理没有重跑清洗、指标计算、抽样或模型，也没有修改论文。原始程序和结果在各类 `original/` 中按收集时字节保留；本次从既有输出整理的名单和对照表放在 `exports_20261104/`。大型原始数据和模型数组保留存储路径、大小及已有版本/校验信息。

## 阅读入口

1. [材料索引与核对说明](材料索引与核对说明.md)：第一轮五类材料、版本和缺口。
2. [Methods逐项核对](Methods逐项核对.md)：Methods描述与实际程序/结果的对应。
3. [多源增强、AI与引力模型核对](06_data_enhancement_and_gravity/多源增强_AI与引力模型_核对说明.md)：八个占位符的事实依据与可用表述。
4. [统一文件索引](文件索引.csv) / [JSON清单](file_manifest.json)：共{len(records)}条索引、{unique_sources}个不同来源文件；{included}条有随附副本，{path_only}条保留大型文件路径。
5. [大型文件路径与版本](大型文件路径与版本.csv)：未上传的原始数据、数组和中间数据位置。

## 六类材料

| 目录 | 内容 |
|---|---|
| [01_fixed_new_cities](01_fixed_new_cities/) | 历史程序、76国年度指标、固定城市/新增城市名单、分类对照及数量/流量占比 |
| [02_equal_event_sampling](02_equal_event_sampling/) | 50次诊断与200次正式抽样记录、种子、年度汇总、最终分类、19国子样本 |
| [03_models](03_models/) | 模型程序和依赖快照、配置、拟合、评价、随机化/模拟与年度重建 |
| [04_geographic_cleaning](04_geographic_cleaning/) | 10月20日清洗程序、城市映射、审核记录、清单和数据版本 |
| [05_samples_groups](05_samples_groups/) | 203国、76国、45国、T1—T4及26学科映射 |
| [06_data_enhancement_and_gravity](06_data_enhancement_and_gravity/) | 实际增强源、LLM/Agent证据、质量验证、引力模型目标、实现及主要结果 |

## 版本与解释

- 200次等事件抽样的种子为20261048；已保存均值、分位数和趋势汇总，未找到其逐次原始抽样明细。模型的有限事件模拟逐次结果另有保存，两者不可混称。
- 城市名单由既有城市年度边际表恢复，已标为本次导出；固定城市数量与当时输出逐国一致。
- 当前T1—T4规模为15、14、24、23；旧19国等分汇总只作历史材料。
- 外部增强源可确认GeoNames、美国人口普查局城市边界及带出处的城市组成规则。独立ORCID、官方前2%和高被引榜单整合、LLM访问/提示词及人工准确率记录的证据状态详见第06类。
- 历史模型提供的是给定起点总量的国内目的地分配及重建结果。特定两步通路的随机化结果、有限事件模拟以及时间评价范围均保留，不据拟合改善推断因果机制。
- `original/` 是归档位置，不能当成历史执行目录。程序的实际源路径及项目相对位置见总索引；快照中的原始路径、依赖和参数未改写。
- 报告链接已尽量转为相对路径；历史源文件和JSON中的原始绝对路径继续保留用于追溯。指向大型文件的链接引导到路径索引，不表示大型数据已随仓库上传。
- `manuscript_snapshot/` 是核对时的论文片段；`collection_history/` 保留最初两轮收集记录。第一轮清单和旧压缩包收据中的数量/路径属于当时记录，当前合集以本目录总索引和核验清单为准。
- `collect_evidence.py`、`collect_supplement.py`、`check_package.py` 等为材料收集脚本；并非本次重新运行的研究分析。`prepare_delivery.py` 是本次合并脚本。

## 完整性

`SHA256SUMS` 列出本次交付文件的校验值；`.gitattributes` 禁止自动换行转换，以保持历史快照的字节和校验值一致。`delivery_validation.json` 记录合并检查结果。
'''
(OUT/'README.md').write_text(readme, encoding='utf-8')
(OUT/'.gitattributes').write_text('# Preserve historical evidence bytes, including original whitespace.\n* -text -whitespace\n', encoding='utf-8')

portable_links_checked = 0
for document in OUT.rglob('*.md'):
    if 'original' in document.relative_to(OUT).parts:
        continue
    for raw in re.findall(r'\]\(([^\n)]+)\)', document.read_text(encoding='utf-8')):
        target = raw.strip('<>').split('#',1)[0]
        if not target or re.match(r'^[a-z]+://', target, re.I):
            continue
        target = re.sub(r':\d+$', '', target)
        assert (document.parent/target).exists(), (document, target)
        portable_links_checked += 1

original_hash_checks = []
for record in records:
    if record['local_copy']:
        assert sha(OUT/record['local_copy']) == record['sha256_at_collection']
        original_hash_checks.append(record['local_copy'])

# Check only concrete credential formats, not generic variable names or hashes.
secrets = []
credential_patterns = [r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
                       r'\bgh[pousr]_[A-Za-z0-9]{30,}', r'\bsk-[A-Za-z0-9_-]{32,}']
for path in OUT.rglob('*'):
    if path.is_file() and path.suffix.lower() in {'.py','.md','.json','.txt','.tex','.csv'}:
        data = path.read_text(encoding='utf-8-sig')
        if any(re.search(pattern, data) for pattern in credential_patterns):
            secrets.append(path.relative_to(OUT).as_posix())
assert not secrets, secrets

paper_after = {p.name: sha(p) for p in (ROOT/'outputs/paper_final').glob('*.tex')}
assert paper_before == paper_after
validation = dict(
    index_entries=len(records), unique_source_files=unique_sources,
    categories=dict(counts), entries_with_included_snapshots=included,
    entries_with_large_local_paths_only=path_only,
    snapshot_hash_checks=len(original_hash_checks), snapshot_hash_mismatches=0,
    portable_report_links_rewritten=len(link_checks),
    portable_report_links_checked=portable_links_checked,
    research_analyses_rerun=False, manuscript_unchanged=True,
    concrete_credentials_detected=0,
    scope='Only consolidated Methods-verification materials; other workspace edits excluded',
)
(OUT/'delivery_validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')

checksum_files = sorted(p for p in OUT.rglob('*') if p.is_file() and p.name != 'SHA256SUMS' and p.suffix != '.zip')
(OUT/'SHA256SUMS').write_text(''.join(f'{sha(p)}  {p.relative_to(OUT).as_posix()}\n' for p in checksum_files), encoding='utf-8')
print(json.dumps(validation, ensure_ascii=False))
print('delivery_files', len(checksum_files)+1)
print('delivery_bytes', sum(p.stat().st_size for p in checksum_files)+(OUT/'SHA256SUMS').stat().st_size)
