"""Independently check pooled source data, transformations, and final PDF geometry."""
from __future__ import annotations
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np
import pymupdf


def read(path):
    return list(csv.DictReader(path.open(encoding='utf-8-sig', newline='')))


def independent_raw_indices():
    src = ROOT/'results/disciplinary_domains_20261022'
    manifest = json.loads((src/'manifest.json').read_text(encoding='utf8'))
    mapping = read(src/'field_domain_mapping.csv')
    cohort = manifest['common_countries']
    codes = ','.join("'"+code+"'" for code in cohort)
    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='3GB'")
    con.execute('CREATE TEMP TABLE taxonomy(field VARCHAR,domain VARCHAR)')
    con.executemany('INSERT INTO taxonomy VALUES (?,?)', [(r['field'],r['domain']) for r in mapping])
    source = str(ROOT/manifest['source']).replace("'", "''")
    con.execute(f"CREATE VIEW events AS SELECT e.*, t.domain FROM read_parquet('{source}') e JOIN taxonomy t USING(field) WHERE flow>0")
    con.execute('''CREATE TEMP TABLE national AS SELECT domain,year,country,sum(flow) strength FROM (
        SELECT domain,year,origin_country country,flow FROM events WHERE origin_country<>destination_country
        UNION ALL
        SELECT domain,year,destination_country country,flow FROM events WHERE origin_country<>destination_country
        ) GROUP BY ALL''')
    con.execute(f'''CREATE TEMP TABLE domestic AS SELECT domain,year,country,city,sum(flow) strength FROM (
        SELECT domain,year,origin_country country,origin city,flow FROM events
        WHERE origin_country=destination_country AND origin_country IN ({codes})
        UNION ALL
        SELECT domain,year,destination_country country,destination city,flow FROM events
        WHERE origin_country=destination_country AND origin_country IN ({codes})
        ) GROUP BY ALL''')
    def calculate(table, keys, place):
        by = ','.join(keys)
        # Pairwise absolute-difference identity via sorted rank, independent of exported indices.
        rows = con.execute(f'''WITH ordered AS (
          SELECT *,row_number() OVER(PARTITION BY {by} ORDER BY strength,{place}) rank_n
          FROM {table})
          SELECT {by}, count(*) n,sum(strength) total,
            sum(strength*strength)/sum(strength)/sum(strength) hhi,
            sum((2.0*rank_n-1)*strength)/(count(*)*sum(strength))-1.0 gini
          FROM ordered GROUP BY {by} ORDER BY {by}''').fetchall()
        result = {}
        for row in rows:
            n, strength, hhi, gini = row[-4:]
            result[tuple(row[:-4])] = dict(N=int(n),flow_events=float(strength/2),HHI=float(hhi),
                Gini=float(gini), equivalent=1/float(hhi), normalized_equivalent=1/(n*float(hhi)))
        return result
    national = calculate('national', ['domain','year'], 'country')
    domestic = calculate('domestic', ['domain','country','year'], 'city')
    assert len(national)==112 and len(domestic)==5040
    all_events = con.execute('SELECT sum(flow) FROM events').fetchone()[0]
    con.close()
    return national, domestic, float(all_events)


def slope(values):
    years=np.arange(1998,2026,dtype=float)
    design=np.column_stack([np.ones(28),years-years.mean()])
    return float(np.linalg.lstsq(design,np.array(values,dtype=float),rcond=None)[0][1]*100)


def rgb(code):
    return tuple(int(code[i:i+2],16)/255 for i in (1,3,5))



def verify_profile(out, national, domestic):
    from scipy.stats import spearmanr
    data, qa = out/'source_data', out/'QA/Fig6'
    m=json.loads((qa/'figure_manifest.json').read_text(encoding='utf8'))
    cohort=m['countries'];domains=m['domains']
    assert len(cohort)==45 and len(domains)==4 and len(m['panels'])==7
    errors=[]
    for name,raw,keys in [('Fig6_country_annual_metrics.csv',national,['domain','year']),
                          ('Fig6_domestic_country_annual_metrics.csv',domestic,['domain','country','year'])]:
        rows=read(data/name);assert len(rows)==len(raw)
        for row in rows:
            key=tuple(int(row[k]) if k=='year' else row[k] for k in keys)
            for key2,value in raw[key].items():
                error=abs(float(row[key2])-value);errors.append(error)
                assert error<1e-9,(name,key,key2,error)
    years=np.arange(1998,2026);design=np.column_stack([np.ones(28),years-years.mean()])
    fitted={};growth={}
    for d in domains:
        for c in cohort:
            fitted[d,c]=slope([domestic[d,c,y]['Gini'] for y in years])
            beta=np.linalg.lstsq(design,np.log([domestic[d,c,y]['N'] for y in years]),rcond=None)[0][1]
            growth[d,c]=100*np.expm1(beta)
    for r in read(data/'Fig6_domestic_country_trends.csv'):
        assert abs(float(r['Gini_slope_pp'])-fitted[r['domain'],r['country']])<1e-10
    for r in read(data/'Fig6_national_trends.csv'):
        assert abs(float(r['Gini_slope_pp'])-slope([national[r['domain'],y]['Gini'] for y in years]))<1e-10
    annual=read(data/'Fig6_annual_changes.csv');assert len(annual)==112
    for r in annual:
        d,y=r['domain'],int(r['year'])
        diff=[100*(domestic[d,c,y]['Gini']-domestic[d,c,1998]['Gini']) for c in cohort]
        assert np.max(np.abs(np.quantile(diff,[.25,.5,.75])-[float(r[k]) for k in
            ['domestic_change_q1_pp','domestic_change_median_pp','domestic_change_q3_pp']]))<1e-9
        assert abs(float(r['country_Gini_change_pp'])-100*(national[d,y]['Gini']-national[d,1998]['Gini']))<1e-9
    points=read(data/'Fig6_scatter_plotted_values.csv')
    paired=read(data/'Fig6_coverage_concentration_points.csv')
    assert len(points)==len(paired)==180
    for r in points+paired:
        assert abs(float(r['Gini_slope_pp'])-fitted[r['domain'],r['country']])<1e-10
    for r in paired:
        assert abs(float(r['city_count_growth_pct'])-growth[r['domain'],r['country']])<1e-9
    for r in read(data/'Fig6_coverage_concentration_associations.csv'):
        x=[growth[r['domain'],c] for c in cohort];y=[fitted[r['domain'],c] for c in cohort]
        assert abs(float(r['spearman_rho'])-spearmanr(x,y).statistic)<1e-12
        coeff=np.linalg.lstsq(np.column_stack([np.ones(45),x]),y,rcond=None)[0]
        assert np.max(np.abs(coeff-[float(r['ols_intercept']),float(r['ols_slope'])]))<1e-12
    with pymupdf.open(out/'Fig6.pdf') as doc:
        assert len(doc)==1;pg=doc[0];drawings=pg.get_drawings()
        assert abs(pg.rect.width-180/25.4*72)<.01 and abs(pg.rect.height-140/25.4*72)<.01
        matched=[]
        assert m['lower_point_style']==dict(size_pt2=18.,alpha=.90)
        assert m['swarm_point_style']==dict(size_pt2=7.,alpha=.90)
        for r in points+paired:
            color=rgb(m['palette'][r['domain']]);pt=np.array([float(r['pdf_x_pt']),float(r['pdf_y_pt'])])
            expected_alpha=.90
            expected_diameter=np.sqrt(7. if r['panel']=='a' else 18.)
            candidates=[]
            for j,item in enumerate(drawings):
                if item.get('fill') is None or max(abs(x-y) for x,y in zip(item['fill'],color))>1e-4:continue
                if abs(item.get('fill_opacity',1)-expected_alpha)>.001:continue
                rect=item['rect']
                if abs(rect.width-expected_diameter)>.002 or abs(rect.height-expected_diameter)>.002:continue
                if np.linalg.norm(np.array([(rect.x0+rect.x1)/2,(rect.y0+rect.y1)/2])-pt)<.02:candidates.append(j)
            assert len(candidates)==1,(r['panel'],r['domain'],r['country'],candidates)
            matched.extend(candidates)
        assert len(set(matched))==360
        for r in read(data/'Fig6_summary_marks.csv'):
            pt=np.array([float(r['national_pdf_x_pt']),float(r['national_pdf_y_pt'])]);color=rgb(m['palette'][r['domain']])
            candidates=[]
            for item in drawings:
                if item.get('fill') is None or max(abs(x-y) for x,y in zip(item['fill'],color))>1e-4:continue
                rect=item['rect']
                if not 6<rect.width<7:continue
                if np.linalg.norm(np.array([(rect.x0+rect.x1)/2,(rect.y0+rect.y1)/2])-pt)<.02:candidates.append(item)
            assert len(candidates)==1
        text=[span for block in pg.get_text('dict')['blocks'] if 'lines' in block
              for line in block['lines'] for span in line['spans']]
        assert all('Helvetica' in r['font'] and r['color']==0 for r in text)
        assert min(r['size'] for r in text)>=5
        assert sorted(r['text'] for r in text if 'Bold' in r['font'])==list('abcdefg')
        for r in text:
            assert pg.rect.contains(pymupdf.Rect(r['bbox'])),r['text']
        for forbidden in ['Hong Kong','Macao','Macau','Taiwan']:
            assert forbidden not in pg.get_text()
        fonts=sorted({r['font'] for r in text})
    boxes={r['panel']:r['bbox_pdf_pt'] for r in m['panels']}
    for p in 'defg':
        b=boxes[p];assert abs(b[2]-b[0]-105)<1e-7 and abs(b[3]-b[1]-105)<1e-7
    assert np.ptp([boxes[p][1] for p in 'abc'])<1e-7
    assert np.ptp([boxes[p][3] for p in 'abc'])<1e-7
    assert abs(boxes['a'][0]-boxes['d'][0])<1e-7
    alignment=json.loads((qa/'alignment.json').read_text(encoding='utf8'))
    assert alignment['verdict']=='PASS'
    report=dict(status='PASS',raw_annual_metric_groups_checked=5152,
        largest_absolute_index_error=max(errors),country_domain_Gini_trends_refitted=180,
        country_domain_coverage_growth_trends_refitted=180,national_Gini_trends_refitted=4,
        annual_country_baseline_comparisons=5040,rendered_country_points_checked=360,
        national_diamonds_checked=4,domain_associations_refitted=4,common_sample=45,
        panel_alignment='PASS',fonts=fonts,figure_sha256=hashlib.sha256((out/'Fig6.pdf').read_bytes()).hexdigest())
    (qa/'data_and_visual_checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(out,json.dumps(report))


def main():
    national,domestic,events=independent_raw_indices()
    assert events==29699142
    for out in [BASE,BASE/'NHB_final']:
        verify_profile(out,national,domestic)


if __name__=='__main__':main()
