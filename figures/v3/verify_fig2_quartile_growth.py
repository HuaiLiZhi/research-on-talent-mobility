"""Check fixed quartiles,cleaned counts,normalization,cluster fits and vector marks."""
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
from statsmodels.stats.sandwich_covariance import cov_cluster
from scipy.stats import linregress,t


def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))


def main():
    out=Path(__file__).parent;data=out/'source_data';qa=out/'QA/Fig2'
    manifest=json.loads((qa/'figure_manifest.json').read_text(encoding='utf-8'))
    geometry=manifest['quartile_growth_panels'];raw=read(data/'Fig2_quartile_growth_country_year.csv')
    points=read(data/'Fig2_quartile_growth_points.csv');curves=read(data/'Fig2_quartile_growth_fits.csv')
    assert len(raw)==2128 and len(points)==4256 and len(curves)==1608
    groups={r['country']:int(r['group']) for r in read(data/'Fig5_stratified_country_trends.csv')}
    reference={r['country']:int(r['group']) for r in read(ROOT/'figures/v4/source_data/Fig3_Fig5_quartile_membership.csv')}
    colours={int(r['group']):r['color'] for r in read(data/'Fig4_Fig5_quartile_membership.csv')}
    assert groups==reference and set(groups)==set(geometry['countries'])
    assert [sum(group==g for group in groups.values()) for g in range(1,5)]==[19]*4
    clean=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis'
    connection=duckdb.connect();connection.execute("SET threads=4")
    table=connection.execute("""
      WITH flows AS (SELECT * FROM read_parquet(?) WHERE flow>0 AND year BETWEEN 1998 AND 2025),
      international AS (SELECT year,origin_country country,destination_country partner,flow FROM flows WHERE origin_country<>destination_country
        UNION ALL SELECT year,destination_country,origin_country,flow FROM flows WHERE origin_country<>destination_country),
      i AS (SELECT country,year,sum(flow) international_flow,count(DISTINCT partner) partners FROM international GROUP BY country,year),
      events AS (SELECT origin_country country,year,sum(flow) domestic_flow FROM flows WHERE origin_country=destination_country GROUP BY country,year),
      city_union AS (SELECT origin_country country,year,unnest([origin,destination]) city FROM flows WHERE origin_country=destination_country),
      cities AS (SELECT country,year,count(DISTINCT city) city_count FROM city_union GROUP BY country,year)
      SELECT i.country,i.year,i.international_flow,i.partners,events.domestic_flow,cities.city_count
      FROM i JOIN events USING(country,year) JOIN cities USING(country,year)
      """,[str(clean/'flow_top100.parquet')]).fetchall();connection.close()
    expected={(cc,int(year)):dict(international_flow=float(fi),partner_countries=int(k),domestic_flow=float(fd),domestic_cities=int(n))
              for cc,year,fi,k,fd,n in table if cc in groups}
    assert len(expected)==2128
    for row in raw:
        cc,year=row['country'],int(row['year']);group=groups[cc]
        assert int(row['group'])==group and row['colour']==colours[group]
        for metric,value in expected[cc,year].items():
            assert float(row[metric])==value
            baseline=np.mean([expected[cc,y][metric] for y in range(1998,2005)])
            assert np.isclose(float(row[metric+'_baseline']),baseline)
            assert np.isclose(float(row[metric+'_ratio']),value/baseline)
    # Reconstruct the existing share-growth grouping using the worldwide denominator.
    country_flows={};totals={year:0. for year in range(1998,2026)}
    for row in read(clean/'country_annual_margins.csv'):
        year=int(row['year']);key=row['country'],year
        country_flows[key]=country_flows.get(key,0.)+float(row['flow']);totals[year]+=float(row['flow'])
    codes=sorted(groups);years=np.arange(1998,2026)
    rates=np.array([100*np.expm1(linregress(years-years[0],np.log([country_flows[cc,int(y)]/totals[int(y)] for y in years])).slope) for cc in codes])
    cuts=np.quantile(rates,[.25,.5,.75],method='linear')
    assert {cc:int(np.searchsorted(cuts,rate,side='right')+1) for cc,rate in zip(codes,rates)}==groups
    lookup={(r['country'],int(r['year'])):r for r in raw}
    for row in points:
        original=lookup[row['country'],int(row['year'])]
        assert int(row['group'])==int(original['group']) and row['colour']==original['colour']
        assert float(row['x'])==float(original[row['xkey']+'_ratio'])
        assert float(row['y'])==float(original[row['ykey']+'_ratio'])
    ns='{http://www.w3.org/2000/svg}';svg=ET.parse(out/'Fig2.svg').getroot()
    nodes={g.get('id'):g for g in svg.iter(ns+'g')}
    def path(identifier):
        element=next(nodes[identifier].iter(ns+'path'))
        vertices=np.array(re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',element.get('d')),dtype=float).reshape(-1,2)
        uses=list(nodes[identifier].iter(ns+'use'))
        if len(uses)==1:vertices+=np.array([float(uses[0].get('x','0')),float(uses[0].get('y','0'))])
        return vertices
    for stat in geometry['statistics']:
        panel=next(p for p in geometry['panels'] if p['panel']==stat['panel'])
        rr=[r for r in points if r['panel']==stat['panel'] and int(r['group'])==stat['group']]
        curve=[r for r in curves if r['panel']==stat['panel'] and int(r['group'])==stat['group']]
        assert len(rr)==532 and len({r['country'] for r in rr})==19
        x=np.log([float(r['x']) for r in rr]);y=np.log([float(r['y']) for r in rr])
        design=sm.add_constant(x-x.mean());fit=sm.OLS(y,design).fit()
        covariance=cov_cluster(fit,np.array([r['country'] for r in rr]),use_correction=True)
        assert np.allclose(fit.params,stat['coefficients']) and np.allclose(covariance,stat['covariance'])
        grid=np.array([float(r['x']) for r in curve]);assert np.all(np.diff(grid)>0)
        grid_design=sm.add_constant(np.log(grid)-x.mean());estimate=fit.predict(grid_design)
        se=np.sqrt(np.diag(grid_design@covariance@grid_design.T));critical=t.ppf(.975,18)
        expected_estimate=np.exp(estimate);lo=np.exp(estimate-critical*se);hi=np.exp(estimate+critical*se)
        for key,values in [('estimate',expected_estimate),('lower95',lo),('upper95',hi)]:
            assert np.allclose([float(r[key]) for r in curve],values)
        x0,y0,w,h=panel['plot_rectangle_pt'];xmin,xmax=panel['xlim'];ymin,ymax=panel['ylim']
        def transform(xx,yy):return np.column_stack([x0+np.log10(np.asarray(xx)/xmin)/np.log10(xmax/xmin)*w,
            313-y0-np.log10(np.asarray(yy)/ymin)/np.log10(ymax/ymin)*h])
        uses=list(nodes[f"quartile_points_{stat['panel']}_Q{stat['group']}"].iter(ns+'use'))
        actual=np.array([[float(use.get('x')),float(use.get('y'))] for use in uses])
        assert actual.shape==(532,2) and np.allclose(actual,transform(np.exp(x),np.exp(y)),atol=1e-5)
        band=path(f"quartile_band_{stat['panel']}_Q{stat['group']}")
        for lower,upper in zip(transform(grid,lo),transform(grid,hi)):
            matches=band[np.isclose(band[:,0],lower[0],atol=1e-5,rtol=0),1]
            assert len(matches)>=2 and np.allclose([matches.min(),matches.max()],[upper[1],lower[1]],atol=1e-5)
    alignment=json.loads((qa/'alignment.json').read_text());assert alignment['verdict']=='PASS'
    assert all(np.isclose(p['bbox_pt'][3]-p['bbox_pt'][1],95.) for p in alignment['layout']['panels'])
    previous=ROOT/'outputs/fig2_v3_histograms_20261028/quartile_growth_update/Fig2.pdf'
    with pymupdf.open(out/'Fig2.pdf') as document,pymupdf.open(previous) as reference_pdf:
        page=document[0];clip=pymupdf.Rect(0,0,page.rect.width,150.)
        assert page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False).samples==reference_pdf[0].get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False).samples
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
        assert min(s['size'] for s in spans)>=7.99
        page.get_pixmap(matrix=pymupdf.Matrix(3,3),alpha=False).save(qa/'preview.png')
    protected=json.loads((ROOT/'outputs/fig2_v3_histograms_20261028/protected_files.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in protected.items())
    result=dict(status='PASS',countries=76,country_years=2128,group_sizes=[19]*4,
        source_metrics_verified=8512,normalized_ratios_verified=8512,scatter_positions_verified=4256,
        group_assignments_reconstructed_from_worldwide_shares=True,group_colours_match_fig4_fig5=True,
        independent_cluster_covariance_checks=8,fit_grid_values_verified=1608,band_boundaries_verified=3216,
        unchanged_upper_a_d=True,minimum_text_pt=8.,all_main_plot_heights_pt=95.,alignment='PASS',
        protected_files_unchanged=len(protected))
    (qa/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
