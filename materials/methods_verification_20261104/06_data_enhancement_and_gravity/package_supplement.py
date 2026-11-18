"""Validate and package this read-only evidence supplement."""
from pathlib import Path
import ast, csv, hashlib, json, re, zipfile

OUT = Path(__file__).resolve().parent
BASE = OUT.parent
report = OUT / '多源增强_AI与引力模型_核对说明.md'
text = report.read_text(encoding='utf-8')
with (OUT / '补充文件索引.csv').open(encoding='utf-8-sig', newline='') as f:
    rows = list(csv.DictReader(f))
for row in rows:
    source = Path(row['source_path'])
    copy = OUT / row['local_copy']
    assert source.is_file() and copy.is_file()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == row['sha256']
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == row['sha256']
    if copy.suffix == '.py':
        ast.parse(copy.read_text(encoding='utf-8-sig'))
links = re.findall(r'\]\((D:/[^\n)]+)\)', text)
for link in links:
    path = re.sub(r':\d+$', '', link)
    assert Path(path).exists(), link
placeholders = ['SUPPLEMENTARY_DATA_SOURCES', 'AI_AGENT_WORKFLOW', 'DATA_ENHANCEMENT_TASKS',
                'VALIDATION_PROCEDURE', 'ANALYSIS_COMPONENT', 'GRAVITY_MODEL_OBJECTIVE',
                'GRAVITY_MODEL_IMPLEMENTATION', 'GRAVITY_MODEL_MAIN_FINDING']
assert all(f'[{p}]' in text for p in placeholders)
archive = BASE / '补充材料_多源增强_AI与引力模型.zip'
items = sorted(p for p in OUT.rglob('*') if p.is_file() and p.name != '交付核验.json')
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in items:
        z.write(p, arcname=p.relative_to(BASE).as_posix())
    z.write(BASE / 'collect_supplement.py', arcname='collect_supplement.py')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
receipt = dict(archive=str(archive), bytes=archive.stat().st_size,
               sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
               copied_originals=len(rows), original_and_copy_hashes_verified=True,
               links_checked=len(links), placeholders_covered=placeholders,
               zip_crc_pass=True, scientific_analyses_recomputed=False,
               paper_modified=False)
(OUT / '交付核验.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
