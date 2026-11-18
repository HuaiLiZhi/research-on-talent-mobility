"""Collect existing provenance and results; never execute research pipelines."""
from pathlib import Path
import csv, hashlib, json, re, shutil, zipfile

ROOT = Path(__file__).resolve().parents[2]
OA = ROOT.parent / 'OpenAlex'
BASE = ROOT / 'outputs/methods_evidence_audit_20261104'
OUT = BASE / '06_data_enhancement_and_gravity'
OUT.mkdir(parents=True, exist_ok=True)
SOURCES = OUT / 'original'
SOURCES.mkdir(exist_ok=True)

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def readj(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def readcsv(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def writecsv(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

paper = ROOT / 'outputs/paper_final'
before = {str(p.relative_to(ROOT)): digest(p) for p in paper.glob('*.tex')}
clean = ROOT / 'data/processed/mobility_city_harmonized_20261020'
model = ROOT / 'outputs/international_signal_validation_20261030'
files = []
def add(path, role):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    assert path.is_file(), path
    dest = SOURCES / path.name
    if dest.exists() and digest(dest) != digest(path):
        dest = SOURCES / (hashlib.sha256(str(path).encode()).hexdigest()[:8] + '__' + path.name)
    shutil.copy2(path, dest)
    assert digest(path) == digest(dest)
    files.append(dict(role=role, source_path=path.as_posix(), local_copy=dest.relative_to(OUT).as_posix(),
                      bytes=path.stat().st_size, sha256=digest(path)))

for name in ['s10_extract_works_author_mobility.py', 's22_build_author_year_locations.py',
             's24_build_impact_tiers_from_refs.py', 's26_build_career_annual_cscore.py',
             's27_build_tiered_flow.py', 's53_clean_city_regions.py', 'OPENALEX_MOBILITY_PIPELINE.md',
             'OPENALEX_DATA_CLEANING_AND_MOBILITY_METHODS.md', 'STANFORD_TOP2_PERCENT_SELECTION_CRITERIA.md']:
    add(OA / name, 'Upstream code/documentation; presence alone does not establish execution of every branch')
for name in ['manifest.json', 'cleaning_policy.json', 'city_parent_overrides.csv',
             'audit/validation.json', 'audit/crosswalk_summary.json', 'audit/event_accounting.json',
             'audit/country_city_counts_before_after.csv']:
    add(clean / name, 'Canonical 20 October geographic harmonization evidence')
for name in ['build_city_harmonization_map_20261020.py', 'validate_city_harmonized_data_20261020.py',
             'prepare_city_harmonization_references_20261020.py', 'validate_logical_distance_20261030.py',
             'validate_international_signals_20261030.py', 'annual_network_reconstruction_20261030.py',
             'complete_network_section_20261030.py']:
    add(ROOT / 'scripts/reports' / name, 'Historical cleaning/model program; copied without execution')
add(ROOT / 'scripts/plots/plot_fig1_framework_detailed.py', 'Illustration-source usage only')
add(ROOT / 'scripts/plots/plot_network_fig6_20261030.py', 'Saved annual-error table generation code')
for rel in ['geonames_20261020/download_manifest.json', 'us_census_places_2024/manifest.json',
            'fig1_shanghai_real_maps_20261103/manifest.json', 'fig1_square_maps_20261103/manifest.json',
            'fig1_map_context_20261103/manifest.json']:
    add(ROOT / 'data/raw' / ('geo/' + rel if rel.startswith(('geonames_', 'us_census_')) else rel),
        'Reference metadata; Fig1 map assets are separate from canonical data cleaning')
for name in ['analysis_plan.json', 'fits.json', 'coefficients.csv', 'comparison_summary.csv',
             'absolute_metrics.csv', 'validation_selection.json', 'validation_checks.json',
             'independent_feature_checks.json', 'feature_construction_audit.json']:
    add(model / name, 'Saved aggregate domestic-allocation model evidence')
for name in ['network_randomization_summary.json', 'distribution_simulation_summary.json']:
    add(ROOT / 'outputs/results_network_revision_20261030/analysis' / name,
        'Saved two-step-specific diagnostic; not integrated-model diagnostics')
add(ROOT / 'outputs/fig6_full_model_revision_20261030/analysis_plan.json',
    'Integrated annual-reconstruction specification')
for name in ['Fig6_evaluation_errors.csv', 'Fig6_annual_MAE_curves.csv']:
    add(ROOT / 'outputs/fig6_integrated_axes_20261030/artwork/source_data' / name,
        'Saved integrated-model annual errors')
writecsv(OUT / '补充文件索引.csv', files)

# Select rows from saved tables without refitting or recomputing any scientific metric.
comparison = [r for r in readcsv(model / 'comparison_summary.csv')
              if r['split'] == 'test' and r['base'] == 'B_history_field']
writecsv(OUT / '既有模型评价_2018_2025.csv', comparison)
absolute = [r for r in readcsv(model / 'absolute_metrics.csv') if r['split'] == 'test']
writecsv(OUT / '既有模型绝对指标_2018_2025.csv', absolute)

# Restrict search to research code, not environments, libraries, credentials or raw records.
oa_code = sorted(OA.glob('*.py'))
clean_code = [ROOT / 'scripts/reports' / n for n in
              ['build_city_harmonization_map_20261020.py', 'import_city_harmonization_gazetteer_20261020.py',
               'prepare_city_harmonization_nodes_20261020.py', 'prepare_city_harmonization_references_20261020.py',
               'rebuild_city_harmonized_flows_20261020.py', 'validate_city_harmonized_data_20261020.py',
               'write_city_harmonized_readme_20261020.py']]
patterns = {
    'ORCID_metadata': r'\borcid\b',
    'external_ranking_or_source': r'clarivate|highly.?cited|stanford|scopus',
    'AI_execution_markers': r'deepseek|\bllm\b|\bagent\b|langchain|langgraph|autogen|chat\.completions|responses\.create',
}
matches = []
for p in oa_code + clean_code:
    for lineno, line in enumerate(p.read_text(encoding='utf-8-sig').splitlines(), 1):
        for category, pattern in patterns.items():
            if re.search(pattern, line, re.I):
                if category == 'AI_execution_markers' and 'User-Agent' in line:
                    continue
                matches.append(dict(category=category, path=p.as_posix(), line=lineno, text=line.strip()))
writecsv(OUT / '上游程序与清洗程序_检索命中.csv', matches)

inventory = readj(BASE / 'inventory/all_paths.json')
path_hits = [p for p in inventory
             if re.search(r'orcid|stanford|clarivate|highly.?cited|deepseek|\bllm\b', Path(p).name, re.I)]
(OUT / '相关文件名线索.json').write_text(json.dumps(path_hits, ensure_ascii=False, indent=2), encoding='utf-8')

payload = {
    'task': 'Collect and explain existing data-enhancement and gravity-model evidence',
    'no_recomputation': True,
    'canonical_dataset': clean.as_posix(),
    'cleaning_summary': readj(clean / 'audit/crosswalk_summary.json'),
    'cleaning_validation': readj(clean / 'audit/validation.json'),
    'cleaning_policy': readj(clean / 'cleaning_policy.json'),
    'model_later_period_comparisons': comparison,
    'model_later_period_absolute_metrics': absolute,
    'model_validation_selection': readj(model / 'validation_selection.json'),
    'two_step_randomization': readj(ROOT / 'outputs/results_network_revision_20261030/analysis/network_randomization_summary.json'),
    'two_step_simulation': readj(ROOT / 'outputs/results_network_revision_20261030/analysis/distribution_simulation_summary.json'),
    'integrated_annual_errors': readcsv(ROOT / 'outputs/fig6_integrated_axes_20261030/artwork/source_data/Fig6_evaluation_errors.csv'),
    'search_scope': {'openalex_top_level_python_files': len(oa_code), 'canonical_cleaning_files': len(clean_code),
                     'AI_execution_marker_hits': sum(m['category'] == 'AI_execution_markers' for m in matches),
                     'caveat': 'A bounded local-code search; absence of archived calls does not disprove author-reported external LLM use.'},
    'LLM_model_name_provenance': 'User confirmed DeepSeek-V4.1-Flash; access/API/snapshot/prompts/validation not recovered',
}
(OUT / '补充核对结果.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
after = {str(p.relative_to(ROOT)): digest(p) for p in paper.glob('*.tex')}
assert before == after
receipt = dict(files_copied=len(files), copied_sha256_verified=True, paper_unchanged=before == after,
               scientific_analyses_executed=False, AI_execution_marker_hits=payload['search_scope']['AI_execution_marker_hits'],
               source_paths_valid=all(Path(r['source_path']).is_file() for r in files))
(OUT / '核验记录.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
