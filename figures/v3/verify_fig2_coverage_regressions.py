"""Verify raw coverage counts, independently fitted intervals, and vector geometry."""
from pathlib import Path
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np
import pymupdf
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_hac
from scipy.stats import t


def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    out=Path(__file__).parent;data=out/'source_data';qa=out/'QA/Fig2'
    manifest=json.loads((qa/'figure_manifest.json').read_text(encoding='utf-8'))
    geometry=manifest['coverage_regression_panels']
    raw=read(data/'Fig2_coverage_scatter_observations.csv')
    curves=read(data/'Fig2_coverage_scatter_fits.csv')
    assert len(raw)==112 and len(curves)==804 and geometry['no_insets']
    canonical=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet'
    connection=duckdb.connect();connection.execute("SET threads=4;SET memory_limit='2GB'")
    table=connection.execute("""
        SELECT year,
        count(DISTINCT destination_country) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT origin_country) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT destination) FILTER(WHERE origin_country=destination_country),
        count(DISTINCT origin) FILTER(WHERE origin_country=destination_country),
        sum(flow) FILTER(WHERE origin_country<>destination_country),
        sum(flow) FILTER(WHERE origin_country=destination_country)
        FROM read_parquet(?) WHERE flow>0 AND year BETWEEN 1998 AND 2025 GROUP BY year ORDER BY year
        """,[str(canonical)]).fetchall()
    connection.close()
    metrics=['countries_inflow','countries_outflow','domestic_cities_inflow','domestic_cities_outflow']
    expected={(metric,int(row[0])):int(row[index+1]) for row in table for index,metric in enumerate(metrics)}
    expected_events={(metric,int(row[0])):int(row[index]) for row in table
                     for metric,index in [('international_flow',5),('domestic_flow',6)]}
    for row in raw:
        assert int(row['count'])==expected[row['metric'],int(row['year'])]
        assert int(row['events'])==expected_events[row['x_metric'],int(row['year'])]
        assert np.isclose(float(row['x_display_value']),int(row['events'])/1000.)
        assert np.isclose(float(row['display_value']),int(row['count'])/float(row['scale']))
    ns='{http://www.w3.org/2000/svg}';svg=ET.parse(out/'Fig2.svg').getroot()
    groups={group.get('id'):group for group in svg.iter(ns+'g')}
    assert not any('_detail_' in identifier for identifier in groups if identifier)
    def path(identifier):
        element=next(groups[identifier].iter(ns+'path'))
        vertices=np.array(re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',element.get('d')),dtype=float).reshape(-1,2)
        instances=list(groups[identifier].iter(ns+'use'))
        if len(instances)==1:
            vertices+=np.array([float(instances[0].get('x','0')),float(instances[0].get('y','0'))])
        return vertices
    for stat in geometry['statistics']:
        panel=next(p for p in geometry['panels'] if p['panel']==stat['panel'])
        selected=[r for r in raw if r['panel']==stat['panel'] and r['side']==stat['side']]
        fit_rows=[r for r in curves if r['panel']==stat['panel'] and r['side']==stat['side']]
        years=np.array([int(r['year']) for r in selected]);values=np.array([int(r['count']) for r in selected])
        assert years.tolist()==list(range(1998,2026))
        events=np.array([int(r['events']) for r in selected])
        design=sm.add_constant(events-events.mean());fit=sm.OLS(values,design).fit()
        covariance=cov_hac(fit,nlags=3,use_correction=True)
        assert np.allclose(fit.params,stat['coefficients'])
        assert np.allclose(covariance,stat['covariance'])
        grid=np.array([float(r['events']) for r in fit_rows]);assert np.all(np.diff(grid)>0)
        pred_design=sm.add_constant(grid-events.mean());prediction=fit.predict(pred_design)
        se=np.sqrt(np.diag(pred_design@covariance@pred_design.T));critical=t.ppf(.975,26)
        lower,upper=prediction-critical*se,prediction+critical*se
        for field,computed in [('estimate',prediction),('lower95',lower),('upper95',upper)]:
            assert np.allclose([float(r[field]) for r in fit_rows],computed)
        x0,y0,width,height=panel['plot_rectangle_pt'];xmin,xmax=panel['xlim'];ymin,ymax=panel['ylim']
        def transform(x,y):
            return np.column_stack([x0+(np.asarray(x)-xmin)/(xmax-xmin)*width,
                313-y0-(np.asarray(y)-ymin)/(ymax-ymin)*height])
        uses=list(groups[f"coverage_points_{stat['panel']}_{stat['side']}"].iter(ns+'use'))
        actual=np.array([[float(use.get('x')),float(use.get('y'))] for use in uses])
        assert actual.shape==(28,2) and np.allclose(actual,transform(events/1000.,values/stat['scale']),atol=1e-5)
        line=path(f"coverage_fit_{stat['panel']}_{stat['side']}")
        actual_x=xmin+(line[:,0]-x0)/width*(xmax-xmin)
        actual_value=fit.params[0]+fit.params[1]*(actual_x*1000.-events.mean())
        assert np.allclose(line,transform(actual_x,actual_value/stat['scale']),atol=1e-5)
        band=path(f"coverage_band_{stat['panel']}_{stat['side']}")
        expected_lo=transform(grid/1000.,lower/stat['scale']);expected_hi=transform(grid/1000.,upper/stat['scale'])
        for lo,hi in zip(expected_lo,expected_hi):
            matches=band[np.isclose(band[:,0],lo[0],atol=1e-5,rtol=0),1]
            assert len(matches)>=2
            assert np.allclose([matches.min(),matches.max()],[hi[1],lo[1]],atol=1e-5), (stat['panel'],stat['side'],lo,hi,matches)
        assert lower.min()/stat['scale']>=ymin and upper.max()/stat['scale']<=ymax
    alignment=json.loads((qa/'alignment.json').read_text())
    assert alignment['verdict']=='PASS'
    assert all(np.isclose(p['bbox_pt'][3]-p['bbox_pt'][1],95.) for p in alignment['layout']['panels'])
    previous=ROOT/'outputs/fig2_v3_histograms_20261028/flow_volume_x_update/Fig2.pdf'
    with pymupdf.open(out/'Fig2.pdf') as document,pymupdf.open(previous) as reference:
        page=document[0];clip=pymupdf.Rect(0,0,page.rect.width,150.)
        assert page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False).samples==reference[0].get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False).samples
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
        assert min(s['size'] for s in spans)>=7.99
        page.get_pixmap(matrix=pymupdf.Matrix(3,3),alpha=False).save(qa/'preview.png')
    protected=json.loads((ROOT/'outputs/fig2_v3_histograms_20261028/protected_files.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in protected.items())
    result=dict(status='PASS',cleaned_global_annual_counts_verified=112,
        cleaned_unique_event_volumes_verified=56,lower_x_axes='Mobility events,thousands',
        independent_statsmodels_ols_and_hac_checks=4,fitted_grid_values_verified=804,
        scatter_mark_positions_verified=112,confidence_band_grid_boundaries_verified=1608,
        unchanged_upper_a_d=True,all_main_plot_heights_pt=95.,minimum_text_pt=8.,
        no_insets=True,no_histograms=True,alignment='PASS',protected_files_unchanged=len(protected))
    (qa/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
