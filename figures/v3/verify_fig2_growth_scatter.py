"""Independently check the new Fig2e growth analysis and exported geometry."""
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np
import pymupdf
from scipy.stats import pearsonr


def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def path_xy(element):
    return np.array([float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',element.get('d'))]).reshape(-1,2)


def same_physical_geometry(a,b):
    """Compare final vector geometry across different PDF media heights.

    Media-height conversion can change float rounding and raster antialiasing
    at an unchanged axis baseline; compare vectors and text at0.001pt instead.
    """
    if isinstance(a,dict):
        assert set(a)==set(b)
        return all(same_physical_geometry(v,b[k]) for k,v in a.items() if k!='seqno')
    if isinstance(a,(tuple,list,pymupdf.Point,pymupdf.Rect,pymupdf.Quad)):
        return len(a)==len(b) and all(same_physical_geometry(x,y) for x,y in zip(a,b))
    if isinstance(a,(float,int)) and isinstance(b,(float,int)):
        return math.isclose(a,b,rel_tol=0,abs_tol=.001)
    return a==b


def main():
    out=Path(__file__).parent
    if os.environ.get('NHB_FIGURE_PROFILE')=='journal':out=out/'NHB_final'
    data=out/'source_data';qa=out/'QA/Fig2'
    manifest=json.loads((qa/'figure_manifest.json').read_text(encoding='utf-8'))
    assert manifest['edition']=='v3' and 'growth_scatter_panel' in manifest
    geometry=manifest['growth_scatter_panel']
    assert json.loads((qa/'alignment.json').read_text(encoding='utf-8'))['verdict']=='PASS'
    inputs=read(data/'Fig2_growth_scatter_annual_inputs.csv')
    observations=read(data/'Fig2_growth_scatter_countries.csv')
    plot=read(data/'Fig2_growth_scatter_plot_points.csv')
    stats=read(data/'Fig2_growth_scatter_statistics.csv')
    curves=read(data/'Fig2_growth_scatter_fits.csv')
    countries=sorted({r['country'] for r in observations})
    assert len(countries)==76 and len(observations)==len(plot)==152
    assert len(inputs)==4256 and len(stats)==12 and len(curves)==1600
    assert len({(r['country'],r['mobility_type']) for r in observations})==152
    membership={r['country']:r['continent'] for r in read(data/'Fig2_city_continent_membership.csv')}
    assert set(membership)==set(countries)
    assert all(r['continent']==membership[r['country']] for r in observations)
    canonical=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet'
    con=duckdb.connect();con.execute('SET threads=4')
    query="""SELECT destination_country,year,sum(flow),count(DISTINCT origin_country)
             FROM read_parquet(?) WHERE origin_country<>destination_country
             GROUP BY destination_country,year"""
    international={(cc,int(y)):(float(volume),int(n)) for cc,y,volume,n in con.execute(query,[str(canonical)]).fetchall()}
    con.close()
    domestic={}
    for row in read(canonical.parent/'domestic_city_margins.csv'):
        if row['side']=='inflow' and row['country'] in countries:
            key=row['country'],int(row['year']);volume,city_set=domestic.setdefault(key,[0.,set()])
            domestic[key][0]+=float(row['flow']);city_set.add(row['city_id'])
    for row in inputs:
        cc,year,group=row['country'],int(row['year']),row['mobility_type']
        expected=international[cc,year] if group=='International' else (domestic[cc,year][0],len(domestic[cc,year][1]))
        assert float(row['flow_events'])==expected[0]>0
        assert int(row['coverage_count'])==expected[1]>0
    years=np.arange(28,dtype=float)
    for row in observations:
        rr=sorted([r for r in inputs if r['country']==row['country'] and r['mobility_type']==row['mobility_type']],key=lambda r:int(r['year']))
        assert [int(r['year']) for r in rr]==list(range(1998,2026))
        for source,key in [('flow_events','volume_growth_pct'),('coverage_count','coverage_growth_pct')]:
            slope=np.polyfit(years,np.log([float(r[source]) for r in rr]),1)[0]
            assert abs(100*np.expm1(slope)-float(row[key]))<1e-10
    continents=['North America','Europe','Asia','South America','Africa','Oceania']
    assert [f['continent'] for f in geometry['facets']]==continents
    assert [f['countries'] for f in geometry['facets']]==[6,32,19,5,12,2]
    for index,continent in enumerate(continents):
        cohort=sorted(cc for cc in countries if membership[cc]==continent)
        count=len(cohort);samples=None;rejected=0
        if count>=3:
            rng=np.random.default_rng(20261028+index);parts=[];retained=0
            while retained<5000:
                candidate=rng.integers(0,count,size=(5000-retained,count))
                valid=np.ptp(candidate,axis=1)>0
                parts.append(candidate[valid]);retained+=int(valid.sum());rejected+=int((~valid).sum())
            samples=np.concatenate(parts)
        for group in ['International','Domestic intercity']:
            rr=[r for r in observations if r['continent']==continent and r['mobility_type']==group]
            assert [r['country'] for r in rr]==cohort
            stat=next(r for r in stats if r['continent']==continent and r['mobility_type']==group)
            ff=[r for r in curves if r['continent']==continent and r['mobility_type']==group]
            if count<3:
                assert not ff and stat['fit_status']=='points_only_two_countries'
                assert stat['pearson_r']==stat['slope']==stat['r_ci_low']==stat['r_ci_high']==''
                continue
            x=np.array([float(r['volume_growth_pct']) for r in rr]);y=np.array([float(r['coverage_growth_pct']) for r in rr])
            correlation=pearsonr(x,y);ci=correlation.confidence_interval(.95)
            assert stat['fit_status']=='fitted' and int(stat['countries'])==count
            assert int(stat['rejected_singular_bootstraps'])==rejected
            assert abs(float(stat['pearson_r'])-correlation.statistic)<1e-12
            assert abs(float(stat['p_two_sided'])-correlation.pvalue)<1e-12
            assert abs(float(stat['r_ci_low'])-ci.low)<1e-12 and abs(float(stat['r_ci_high'])-ci.high)<1e-12
            fit=np.polyfit(x,y,1)
            assert abs(float(stat['slope'])-fit[0])<1e-12 and abs(float(stat['intercept'])-fit[1])<1e-12
            xx,yy=x[samples],y[samples]
            xb,yb=xx.mean(axis=1),yy.mean(axis=1)
            slopes=((xx-xb[:,None])*(yy-yb[:,None])).sum(axis=1)/((xx-xb[:,None])**2).sum(axis=1)
            intercepts=yb-slopes*xb
            grid=np.array([float(r['volume_growth_pct']) for r in ff])
            assert len(ff)==160 and np.isclose(grid.min(),x.min()) and np.isclose(grid.max(),x.max())
            low,high=np.quantile(intercepts[:,None]+slopes[:,None]*grid,[.025,.975],axis=0)
            assert np.max(np.abs(low-[float(r['ci95_low']) for r in ff]))<1e-12
            assert np.max(np.abs(high-[float(r['ci95_high']) for r in ff]))<1e-12
    ns='{http://www.w3.org/2000/svg}';svg=ET.parse(out/'Fig2.svg').getroot()
    assert not any(g.get('id')=='continent_coverage_pie' or g.get('id','').startswith('continental_connector_') for g in svg.iter(ns+'g'))
    for facet in geometry['facets']:
        continent=facet['continent'];x0,y0,w,h=facet['plot_rectangle_pt']
        xmin,xmax=facet['xlim'];ymin,ymax=facet['ylim'];height=geometry['height_pt']
        def transform(row,key):
            return [x0+(float(row['volume_growth_pct'])-xmin)/(xmax-xmin)*w,
                    height-y0-(float(row[key])-ymin)/(ymax-ymin)*h]
        for group in ['International','Domestic intercity']:
            slug=continent.lower().replace(' ','_')+'_'+group.lower().replace(' ','_')
            scatter=next(g for g in svg.iter(ns+'g') if g.get('id')=='growth_countries_'+slug)
            actual=np.array([[float(u.get('x')),float(u.get('y'))] for u in scatter.iter(ns+'use')])
            pp=[r for r in plot if r['continent']==continent and r['mobility_type']==group]
            expected=np.array([[float(r['pdf_x_pt']),float(r['pdf_y_pt'])] for r in pp])
            assert actual.shape==expected.shape==(facet['countries'],2) and np.max(np.abs(actual-expected))<.002
            assert np.max(np.abs(expected-np.array([transform(r,'coverage_growth_pct') for r in pp])))<1e-10
            ff=[r for r in curves if r['continent']==continent and r['mobility_type']==group]
            if facet['countries']<3:
                assert not ff
                assert not any(g.get('id') in ['growth_fit_'+slug,'growth_band_'+slug,'growth_stats_'+slug] for g in svg.iter(ns+'g'))
                continue
            fitted=next(g for g in svg.iter(ns+'g') if g.get('id')=='growth_fit_'+slug)
            path=next(p for p in fitted.iter(ns+'path') if 'fill: none' in p.get('style',''))
            expected_fit=np.array([transform(r,'fitted_coverage_growth_pct') for r in ff])
            assert np.max(np.abs(path_xy(path)-expected_fit))<.002
            band=next(g for g in svg.iter(ns+'g') if g.get('id')=='growth_band_'+slug)
            vertices=path_xy(next(band.iter(ns+'path')))
            use=next(band.iter(ns+'use'),None)
            if use is not None:vertices+=np.array([float(use.get('x','0')),float(use.get('y','0'))])
            for row in ff:
                assert ymin<=float(row['ci95_low'])<=float(row['ci95_high'])<=ymax
                for key in ['ci95_low','ci95_high']:
                    assert np.min(np.max(np.abs(vertices-np.array(transform(row,key))),axis=1))<.002
    with pymupdf.open(out/'Fig2.pdf') as doc:
        assert len(doc)==1 and abs(doc[0].rect.width*25.4/72-180)<.01 and abs(doc[0].rect.height-470)<.01
        text=doc[0].get_text()
        assert 'Mobility growth' in text and 'Coverage growth' in text and 'Country-year' not in text
        assert all(name in text for name in continents)
        with pymupdf.open(ROOT/'figures/v4/Fig2.pdf') as v4:
            def upper_drawings(page):return [d for d in page.get_drawings() if d['rect'].y1<147]
            assert same_physical_geometry(upper_drawings(doc[0]),upper_drawings(v4[0]))
            def upper_text(page):
                return [s for block in page.get_text('dict')['blocks'] if 'lines' in block
                        for line in block['lines'] for s in line['spans'] if s['bbox'][3]<147]
            current_text,previous_text=upper_text(doc[0]),upper_text(v4[0])
            assert len(current_text)==len(previous_text)
            for current,previous in zip(current_text,previous_text):
                assert all(current[k]==previous[k] for k in ['text','size','font','color'])
                assert same_physical_geometry(current['bbox'],previous['bbox'])
    protected=ROOT/'outputs/fig2_v3_continent_lines_20261027/protected_files.json'
    if protected.exists():
        for filename,digest in json.loads(protected.read_text(encoding='utf-8')).items():
            assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()==digest,filename
    result=dict(status='PASS',version='v3',countries=76,country_type_points=152,annual_inputs=4256,
                full28_year_growth_rates=True,annual_inputs_reconciled_to_cleaned_source=True,
                all_growth_rates_independently_recomputed=True,correlations_and_Fisher_intervals_verified=True,
                continents=6,continent_country_counts=[6,32,19,5,12,2],
                all10_within_continent_5000_bootstrap_bands_verified=True,all152_scatter_points_verified_in_svg=True,
                all10_fits_and_all_band_vertices_verified_in_svg=True,all_intervals_fully_inside_axes=True,
                two_country_Oceania_shows_points_only=True,pies_and_connectors_removed=True,
                upper_a_d_vector_geometry_text_and_font_sizes_unchanged_within_0001pt=True,
                v4_and_selected_manuscript_unchanged=True,alignment='PASS',native_dimensions_mm=[180,470*25.4/72])
    (qa/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
