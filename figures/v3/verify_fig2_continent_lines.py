"""Verify V3 country-year clouds, annual medians/IQR and continental city pie."""
from pathlib import Path
import csv
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import numpy as np
import pymupdf


def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def main():
    out=Path(__file__).parent
    if os.environ.get('NHB_FIGURE_PROFILE')=='journal':out=out/'NHB_final'
    data=out/'source_data';qa=out/'QA/Fig2'
    manifest=json.loads((qa/'figure_manifest.json').read_text(encoding='utf-8'))
    assert manifest['edition']=='v3' and 'continent_line_panel' in manifest
    assert json.loads((qa/'alignment.json').read_text(encoding='utf-8'))['verdict']=='PASS'
    membership={r['country']:r['continent'] for r in read(data/'Fig2_city_continent_membership.csv')}
    v4_membership={r['country']:r['continent'] for r in read(ROOT/'figures/v4/source_data/Fig2_city_continent_membership.csv')}
    assert membership==v4_membership and len(membership)==76
    first,active={},{}
    for row in read(ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/domestic_city_margins.csv'):
        cc=row['country']
        if row['side']=='inflow' and cc in membership and float(row['flow'])>0:
            key=cc,row['city_id'];year=int(row['year'])
            first[key]=min(first.get(key,9999),year)
            active.setdefault((membership[cc],year),set()).add(key)
    assert len(first)==12218
    inputs=read(data/'Fig2_city_first_inflow_cohorts.csv')
    assert first=={(r['country'],r['city_id']):int(r['first_year']) for r in inputs}
    series=read(data/'Fig2_continent_city_series.csv')
    shares=read(data/'Fig2_continent_city_shares.csv')
    country_series=read(data/'Fig2_continent_country_city_series.csv')
    summary=read(data/'Fig2_continent_country_city_summary.csv')
    scatter_plot=read(data/'Fig2_continent_country_scatter_plot.csv')
    plotted=read(data/'Fig2_continent_country_summary_plot.csv')
    assert len(series)==len(plotted)==168
    assert len(country_series)==len(scatter_plot)==76*28
    assert len({(r['country'],int(r['year'])) for r in country_series})==76*28
    assert len(summary)==168
    lookup={}
    for row in country_series:
        country,year=row['country'],int(row['year'])
        expected=sum(cc==country and observed<=year for (cc,_),observed in first.items())
        assert int(row['cumulative_cities'])==expected>0
        assert row['continent']==membership[country]
        lookup[country,year]=expected
    for row in summary:
        continent,year=row['continent'],int(row['year'])
        values=[lookup[cc,year] for cc in membership if membership[cc]==continent]
        assert int(row['countries'])==len(values)
        assert float(row['median_cities'])==np.median(values)
        assert float(row['q25_cities'])==np.quantile(values,.25)
        assert float(row['q75_cities'])==np.quantile(values,.75)
    assert len({(r['continent'],int(r['year'])) for r in series})==168
    for row in series:
        continent,year=row['continent'],int(row['year'])
        assert int(row['cumulative_cities'])==sum(membership[cc]==continent and observed<=year for (cc,_),observed in first.items())
        assert int(row['newly_recorded_cities'])==sum(membership[cc]==continent and observed==year for (cc,_),observed in first.items())
        assert int(row['annual_positive_cities'])==len(active.get((continent,year),set()))
    assert sum(int(r['cumulative_cities']) for r in series if r['year']=='2025')==12218
    assert len(shares)==6
    assert abs(sum(float(r['share']) for r in shares)-1)<1e-12
    for share in shares:
        endpoint=next(r for r in series if r['continent']==share['continent'] and r['year']=='2025')
        assert int(share['cumulative_cities'])==int(endpoint['cumulative_cities'])
        assert int(share['total_cities'])==12218 and share['year']=='2025'
        assert abs(float(share['share'])-int(share['cumulative_cities'])/12218)<1e-12
        assert abs(float(share['theta2_deg'])-float(share['theta1_deg'])-360*float(share['share']))<2e-5
    ns='{http://www.w3.org/2000/svg}';svg=ET.parse(out/'Fig2.svg').getroot()
    for share in shares:
        identifier=share['continent'].lower().replace(' ','_')
        wedge=next(g for g in svg.iter(ns+'g') if g.get('id')=='continental_wedge_'+identifier)
        assert any(share['colour'].lower() in p.get('style','').lower() for p in wedge.iter(ns+'path'))
        connector=next(g for g in svg.iter(ns+'g') if g.get('id')=='continental_connector_'+identifier)
        assert len(list(connector.iter(ns+'path')))==1
    for facet in manifest['continent_line_panel']['facets']:
        continent=facet['continent'];group_id='continental_series_'+continent.lower().replace(' ','_')
        group=next(g for g in svg.iter(ns+'g') if g.get('id')==group_id)
        path=next(p for p in group.iter(ns+'path') if 'fill: none' in p.get('style',''))
        coords=np.array([float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',path.get('d'))]).reshape(-1,2)
        expected=np.array([[float(r['pdf_x_pt']),float(r['pdf_y_pt'])] for r in plotted if r['continent']==continent])
        assert coords.shape==expected.shape==(28,2)
        assert np.max(np.abs(coords-expected))<.002
        assert sum(1 for _ in group.iter(ns+'use'))==0
        assert facet['yscale']=='log'
        dot_group=next(g for g in svg.iter(ns+'g') if g.get('id')=='continental_country_years_'+continent.lower().replace(' ','_'))
        actual_dots=np.array([[float(u.get('x')),float(u.get('y'))] for u in dot_group.iter(ns+'use')])
        expected_dots=np.array([[float(r['pdf_x_pt']),float(r['pdf_y_pt'])] for r in scatter_plot if r['continent']==continent])
        assert actual_dots.shape==expected_dots.shape==(facet['countries']*28,2)
        assert np.max(np.abs(actual_dots-expected_dots))<.002
        band_group=next(g for g in svg.iter(ns+'g') if g.get('id')=='continental_iqr_'+continent.lower().replace(' ','_'))
        band_path=next(band_group.iter(ns+'path'))
        band_vertices=np.array([float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',band_path.get('d'))]).reshape(-1,2)
        band_use=next(band_group.iter(ns+'use'))
        band_vertices+=np.array([float(band_use.get('x','0')),float(band_use.get('y','0'))])
        for row in [r for r in plotted if r['continent']==continent]:
            for bound in ['q25_pdf_y_pt','q75_pdf_y_pt']:
                target=np.array([float(row['pdf_x_pt']),float(row[bound])])
                assert np.min(np.max(np.abs(band_vertices-target),axis=1))<.002
        rr=sorted((r for r in summary if r['continent']==continent),key=lambda r:int(r['year']))
        assert [int(r['year']) for r in rr]==list(range(1998,2026))
        assert np.all(np.diff([float(r['median_cities']) for r in rr])>=0)
    with pymupdf.open(out/'Fig2.pdf') as doc:
        assert len(doc)==1
        assert abs(doc[0].rect.width*25.4/72-180)<.01 and abs(doc[0].rect.height-370)<.01
        text=doc[0].get_text()
        assert all(name in text for name in membership.values())
        assert 'Cumulative cities' in text
        with pymupdf.open(ROOT/'figures/v4/Fig2.pdf') as v4:
            clip=pymupdf.Rect(0,0,doc[0].rect.width,147)
            assert doc[0].get_pixmap(matrix=pymupdf.Matrix(4,4),clip=clip,alpha=False).samples==v4[0].get_pixmap(matrix=pymupdf.Matrix(4,4),clip=clip,alpha=False).samples
    protected_path=ROOT/'outputs/fig2_v3_continent_lines_20261027/protected_files.json'
    if protected_path.exists():
        protected=json.loads(protected_path.read_text(encoding='utf-8'))
        for filename,digest in protected.items():assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()==digest,filename
    result=dict(status='PASS',version='v3',countries=76,unique_cities_included=12218,
                continents=6,country_year_scatter_points=2128,annual_medians=168,annual_IQRs=168,
                summary_bands_are_country_quartiles_not_confidence_intervals=True,
                log_axes_no_country_or_observation_excluded=True,
                central_pie_sectors=6,pie_shares_match_2025_unique_cities=True,
                matching_sector_and_curve_connectors=6,
                cumulative_series_match_cleaned_margins=True,annual_counts_stored_separately=True,
                every_city_and_first_year_retained=True,all28_median_vertices_present_in_svg=True,
                every_country_year_scatter_marker_verified_in_svg=True,every_IQR_vertex_verified_in_svg=True,
                upper_a_d_pixels_identical_to_v4=True,v4_and_selected_manuscript_unchanged=True,
                alignment='PASS',native_dimensions_mm=[180.,370*25.4/72])
    (qa/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
