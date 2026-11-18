"""Recompute current manuscript figures from the cleaned annual event dataset.

No geographical recleaning and no overlapping influence tiers are combined.
Current plotting designs, estimator definitions and random seeds are retained.
"""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np

STAMP = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
RESUME = len(sys.argv)==3 and sys.argv[1]=='--resume'
OUT = Path(sys.argv[2]).resolve() if RESUME else ROOT / 'outputs' / ('fig2_6_recalculation_' + STAMP)
CLEAN = ROOT / 'data/processed/mobility_city_harmonized_20261020'
MASTER = CLEAN / 'count_mobility_flow_annual_clean.parquet'
ANALYSIS = CLEAN / 'analysis'
PROJECT = ROOT / 'outputs/prism_fig2_5_20261023'
SKILL = Path(__file__).resolve().parents[4] / 'scripts/plots/paper_figures/qa'
PYTHON = sys.executable
ENV = dict(os.environ, PYTHONUTF8='1', MPLBACKEND='Agg', NHB_FIGURE_PROFILE='manuscript')
ENV['PYTHONPATH'] = os.pathsep.join([str(ROOT/'tmp/nhb_fig2_python_deps'),str(ROOT/'figures/v3'),str(SKILL),ENV.get('PYTHONPATH','')])
STAGES = json.loads((OUT/'execution.json').read_text(encoding='utf-8')) if RESUME else []


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def quote(path):
    return "'" + str(path).replace("'","''") + "'"


def run(name, script, args=(), required=True):
    if RESUME and any(s['name']==name and s['returncode']==0 for s in STAGES):
        print('ALREADY PASS '+name,flush=True)
        return 0
    started = time.monotonic()
    print('START ' + name,flush=True)
    log = OUT/'logs'/(name+'.txt')
    with log.open('w',encoding='utf-8') as f:
        result = subprocess.run([PYTHON,'-X','utf8',str(script),*map(str,args)],cwd=ROOT,env=ENV,stdout=f,stderr=subprocess.STDOUT)
    STAGES.append(dict(name=name,script=str(script),returncode=result.returncode,seconds=round(time.monotonic()-started,2),log=str(log)))
    save('execution.json',STAGES)
    print(('PASS ' if result.returncode==0 else 'CHECK ')+name+' '+str(STAGES[-1]['seconds'])+'s',flush=True)
    if required and result.returncode:
        print(log.read_text(encoding='utf-8')[-5000:],flush=True)
        raise RuntimeError('Stage failed: '+name)
    return result.returncode


def snapshot():
    inputs = [p for p in ANALYSIS.iterdir() if p.is_file()]
    figure_files = []
    for version,figs in [('v3',range(2,6)),('v4',[6])]:
        folder=ROOT/'figures'/version
        figure_files += [folder/('Fig'+str(n)+ext) for n in figs for ext in ['.pdf','.svg','.png']]
        figure_files += list((folder/'source_data').glob('*.csv'))
        figure_files += [p for p in (folder/'QA').rglob('*') if p.is_file() and p.suffix in ['.json','.csv']]
    figure_files += [PROJECT/'main.tex',*(PROJECT/'figures').glob('Fig*.pdf')]
    files=sorted(set(inputs+figure_files))
    with zipfile.ZipFile(OUT/'backup_before_recalculation.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as archive:
        for path in files:
            if path.exists():archive.write(path,path.relative_to(ROOT).as_posix())
    save('before_hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in files if p.exists()})
    print('BACKUP complete',flush=True)


def rebuild_base():
    print('START rebuild_cleaned_base',flush=True)
    con=duckdb.connect()
    con.execute("SET threads=4;SET memory_limit='4GB';SET preserve_insertion_order=false")
    con.read_parquet(str(MASTER)).create_view('cleaned_annual')
    con.execute("""CREATE TEMP VIEW selected AS SELECT * FROM cleaned_annual
        WHERE tier='top100pct' AND year BETWEEN 1998 AND 2025
        AND mobility_count>0 AND isfinite(mobility_count)
        AND geography IN ('international','domestic_intercity')""")
    invalid=con.execute("""SELECT count(*) FROM selected WHERE from_city_id IS NULL OR to_city_id IS NULL
        OR from_city_id=to_city_id OR from_country_code IS NULL OR to_country_code IS NULL
        OR (geography='international') <> (from_country_code<>to_country_code)""").fetchone()[0]
    assert invalid==0
    selection=con.execute('SELECT count(*),sum(mobility_count)::BIGINT FROM selected').fetchone()
    con.execute("""CREATE TEMP VIEW fresh_flows AS SELECT year,
        from_country_code origin_country,to_country_code destination_country,
        from_region origin_region,to_region destination_region,from_city origin_city,to_city destination_city,
        from_latitude origin_lat,from_longitude origin_lon,to_latitude destination_lat,to_longitude destination_lon,
        field_display_name field,mobility_count flow,from_city_id origin,to_city_id destination FROM selected""")
    # Exact comparison is on the scientific key and count, independently of
    # row order, Parquet compression, and descriptive location metadata.
    con.read_parquet(str(ANALYSIS/'flow_top100.parquet')).create_view('previous_flows')
    key='year,origin,destination,field,flow'
    changes=con.execute(f'''SELECT count(*) FROM ((SELECT {key} FROM fresh_flows EXCEPT ALL SELECT {key} FROM previous_flows)
        UNION ALL (SELECT {key} FROM previous_flows EXCEPT ALL SELECT {key} FROM fresh_flows))''').fetchone()[0]
    totals=dict(con.execute("SELECT CASE WHEN origin_country=destination_country THEN 'domestic_intercity' ELSE 'international' END,sum(flow)::BIGINT FROM fresh_flows GROUP BY 1").fetchall())
    assert selection==(15797873,29703224)
    assert totals==dict(domestic_intercity=18173850,international=11529374)
    staged=OUT/'recalculated_flow_top100.parquet'
    con.execute(f'COPY (SELECT * FROM fresh_flows) TO {quote(staged)} (FORMAT PARQUET,COMPRESSION ZSTD)')
    con.read_parquet(str(staged)).create_view('flows')
    con.execute("""CREATE TEMP TABLE margins AS SELECT geography,year,side,country,region,city_id,city,sum(flow) flow FROM (
        SELECT CASE WHEN origin_country=destination_country THEN 'domestic' ELSE 'international' END geography,
        year,'outflow' side,origin_country country,origin_region region,origin city_id,origin_city city,flow FROM flows
        UNION ALL
        SELECT CASE WHEN origin_country=destination_country THEN 'domestic' ELSE 'international' END,
        year,'inflow',destination_country,destination_region,destination,destination_city,flow FROM flows) GROUP BY ALL""")
    generated=[]
    def export(sql,name):
        dest=OUT/name
        con.execute(f'COPY ({sql}) TO {quote(dest)} (FORMAT CSV,HEADER TRUE)')
        generated.append((dest,ANALYSIS/name))
    for geo in ['international','domestic']:
        export(f"SELECT year,side,country,region,city_id,city,sum(flow) flow FROM margins WHERE geography='{geo}' GROUP BY ALL ORDER BY year,side,country,city_id",geo+'_city_margins.csv')
    export("SELECT year,side,country,sum(flow) flow FROM margins WHERE geography='international' GROUP BY ALL ORDER BY year,side,country",'country_annual_margins.csv')
    export("SELECT year,side,country,count(DISTINCT city_id) cities,sum(flow) flow FROM margins WHERE geography='domestic' GROUP BY ALL ORDER BY year,side,country",'domestic_country_city_counts.csv')
    for geo,keys in [('domestic','year,side,country'),('international','year,side')]:
        export(f"""WITH a AS (SELECT {keys},city_id,sum(flow) flow FROM margins WHERE geography='{geo}' GROUP BY ALL),
            r AS (SELECT *,count(*) OVER(PARTITION BY {keys}) n,row_number() OVER(PARTITION BY {keys} ORDER BY flow,city_id) rk FROM a)
            SELECT {keys},count(*) N,sum(flow) flow,sum(flow*flow)/sum(flow)^2 HHI,
            sum(flow)^2/sum(flow*flow) N_eff,sum(flow)^2/sum(flow*flow)/count(*) normalized_N_eff,
            sum((2*rk-n-1)*flow)/(count(*)*sum(flow)) Gini FROM r GROUP BY {keys} ORDER BY {keys}""",geo+'_city_metrics.csv')
    con.close()
    shutil.copyfile(staged,ANALYSIS/'flow_top100.parquet')
    for staged_csv,destination in generated:shutil.copyfile(staged_csv,destination)
    save('base_recalculation.json',dict(master=str(MASTER.relative_to(ROOT)),master_sha256=sha(MASTER),tier='top100pct',years=[1998,2025],rows=selection[0],total_events=selection[1],totals=totals,invalid_rows=invalid,changed_key_count_records_from_previous=changes,city_unit='Stable cleaned city identifiers',outputs={str(p.relative_to(ROOT)):sha(p) for p in ANALYSIS.iterdir() if p.is_file()}))
    print('PASS rebuild_cleaned_base: '+str(selection[1])+' events; changed scientific records='+str(changes),flush=True)


def main():
    if not RESUME:
        OUT.mkdir(parents=True,exist_ok=False)
        (OUT/'logs').mkdir()
    save('figure_contracts.json',dict(backend='Python/matplotlib',reuse='Exact statistical and layout reuse with all source quantities regenerated',figures={
        'Fig2':dict(edition='v3',claim='Observed event volumes and geographic coverage',panels='Event areas; source-partner coverage; nested counts; five country trajectories'),
        'Fig3':dict(edition='v3',claim='National deconcentration across the complete annual record',panels='Log-share KDE; Lorenz curves; separate inflow/outflow annual HHI and Gini'),
        'Fig4':dict(edition='v3',claim='Domestic relative concentration within the expanding positive-city set',panels='All 76-country slope comparison and four country histories'),
        'Fig5':dict(edition='v3',claim='Cross-country association between international participation and domestic flow distribution',panels='Combined-direction country means; international-share-growth quartiles and domestic Gini trends'),
        'Fig6':dict(edition='v4',claim='National and domestic changes across four pooled domains',panels='Gini slopes; baseline changes; coverage-growth associations in the common 45-country cohort')}))
    print('OUTPUT '+str(OUT),flush=True)
    if not RESUME:
        snapshot()
        rebuild_base()
    for name,script in [
        ('render_Fig2','figures/v3/plot_fig2.py'),
        ('render_Fig3','figures/v3/plot_fig3.py'),
        ('render_Fig4','figures/v3/plot_fig4.py'),
        ('prepare_Fig5','figures/v3/prepare_fig5.py'),
        ('render_Fig5','figures/v3/plot_fig5.py'),
        ('prepare_fields','figures/v3/prepare_fig6.py'),
        ('prepare_domains','scripts/reports/analyze_disciplinary_domains_20261022.py'),
        ('render_Fig6','figures/v4/plot_fig6.py'),
    ]:
        run(name,ROOT/script)
    # Existing figure-specific verifiers independently recompute data and
    # inspect rendered geometry. General validators are run on final PDFs.
    for n in range(2,7):
        folder=ROOT/'figures'/('v4' if n==6 else 'v3')
        script=folder/('plot_fig'+str(n)+'.py')
        pdf=folder/('Fig'+str(n)+'.pdf')
        run('Fig'+str(n)+'_source_preflight',SKILL/'validate_figure.py',[script,'--json'],required=False)
        run('Fig'+str(n)+'_pdf_text',SKILL/'audit_pdf_text.py',[pdf,'--min-pt','5','--json'])
        # A REVIEW REQUIRED result is inspected before delivery; FAIL must be fixed.
        run('Fig'+str(n)+'_collisions',SKILL/'audit_figure_collisions.py',[pdf,'--json-out',OUT/('Fig'+str(n)+'_collision.json'),'--overlay-pdf',OUT/('Fig'+str(n)+'_collision.pdf')])
        # Figure-specific checks must inspect this run's reports, not stale
        # reports left beside an earlier export.
        qa=folder/'QA' if n==2 else folder/'QA'/('Fig'+str(n))
        for stage,saved in [('source_preflight','source_preflight.json'),('pdf_text','pdf_text.json')]:
            result=json.loads((OUT/'logs'/('Fig'+str(n)+'_'+stage+'.txt')).read_text(encoding='utf-8'))
            (qa/saved).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        shutil.copyfile(OUT/('Fig'+str(n)+'_collision.json'),qa/'collisions.json')
    for name,script in [
        ('verify_Fig2','figures/v3/verify_fig2_cleaned.py'),
        ('verify_Fig3','figures/v3/verify_fig3.py'),
        ('verify_Fig4','figures/v3/verify_fig4.py'),
        ('verify_Fig5_combined','figures/v3/verify_fig5_combined.py'),
        ('verify_Fig5_groups','figures/v3/verify_fig5_stratified.py'),
        ('verify_Fig6','figures/v4/verify_fig6.py'),
        ('verify_fixed_cities','outputs/prism_fig2_5_20261023/QA/results_20261023/verify_combined_cities.py'),
        ('verify_cross_figure','outputs/prism_fig2_5_20261023/QA/audit_cleaned_data_20261023.py'),
    ]:
        run(name,ROOT/script)
    # Manuscript assets are updated only after data and render checks pass.
    synced=[]
    for n in range(2,7):
        source=ROOT/'figures'/('v4' if n==6 else 'v3')/('Fig'+str(n)+'.pdf')
        dest=PROJECT/'figures'/source.name
        shutil.copyfile(source,dest)
        synced.append(dict(figure=n,source=str(source.relative_to(ROOT)),manuscript_file=str(dest.relative_to(ROOT)),sha256=sha(dest)))
    save('synchronized_figures.json',synced)
    save('run_status.json',dict(status='DATA_AND_RENDER_CHECKS_COMPLETE',output=str(OUT),stages=len(STAGES),synced_figures=synced,manuscript_source_sha256=sha(PROJECT/'main.tex')))
    print('COMPLETE '+str(OUT),flush=True)


if __name__=='__main__':
    main()
