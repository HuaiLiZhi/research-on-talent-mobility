"""Verify all-year country summaries,actual group regions,and final vector marks."""
from pathlib import Path
import csv,hashlib,json,re,sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb,numpy as np,pymupdf,statsmodels.api as sm
from scipy.stats import linregress,t

def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def main():
    out=Path(__file__).parent;data=out/'source_data';qa=out/'QA/Fig2'
    manifest=json.loads((qa/'figure_manifest.json').read_text(encoding='utf-8'))
    geom=manifest['quartile_country_cluster_panels']
    raw=read(data/'Fig2_quartile_growth_country_year.csv');summary=read(data/'Fig2_quartile_country_growth.csv')
    points=read(data/'Fig2_quartile_country_points.csv');curves=read(data/'Fig2_quartile_country_pooled_fits.csv')
    assert len(raw)==2128 and len(summary)==76 and len(points)==152 and len(curves)==402
    groups={r['country']:int(r['group']) for r in read(data/'Fig5_stratified_country_trends.csv')}
    assert groups=={r['country']:int(r['group']) for r in read(ROOT/'figures/v4/source_data/Fig3_Fig5_quartile_membership.csv')}
    colours={int(r['group']):r['color'] for r in read(data/'Fig4_Fig5_quartile_membership.csv')}
    canonical=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet'
    con=duckdb.connect();con.execute('SET threads=4')
    table=con.execute("""
      WITH flows AS (SELECT * FROM read_parquet(?) WHERE flow>0 AND year BETWEEN 1998 AND 2025),
      international AS (SELECT year,origin_country country,destination_country partner,flow FROM flows WHERE origin_country<>destination_country
        UNION ALL SELECT year,destination_country,origin_country,flow FROM flows WHERE origin_country<>destination_country),
      i AS (SELECT country,year,sum(flow) fi,count(DISTINCT partner) k FROM international GROUP BY country,year),
      d AS (SELECT origin_country country,year,sum(flow) fd FROM flows WHERE origin_country=destination_country GROUP BY country,year),
      endpoints AS (SELECT origin_country country,year,unnest([origin,destination]) city FROM flows WHERE origin_country=destination_country),
      n AS (SELECT country,year,count(DISTINCT city) nc FROM endpoints GROUP BY country,year)
      SELECT country,year,fi,k,fd,nc FROM i JOIN d USING(country,year) JOIN n USING(country,year)
    """,[str(canonical)]).fetchall();con.close()
    expected={(cc,int(year)):dict(international_flow=float(fi),partner_countries=int(k),domestic_flow=float(fd),domestic_cities=int(n))
              for cc,year,fi,k,fd,n in table if cc in groups}
    assert len(expected)==2128
    for row in raw:
        for key,value in expected[row['country'],int(row['year'])].items():assert float(row[key])==value
    by_country={r['country']:r for r in summary}
    for country,row in by_country.items():
        assert int(row['group'])==groups[country] and row['colour']==colours[groups[country]]
        for key in ['international_flow','partner_countries','domestic_flow','domestic_cities']:
            years=np.arange(1998,2026);values=np.array([expected[country,int(y)][key] for y in years])
            slope=linregress(years,np.log(values)).slope
            assert np.isclose(float(row[key+'_log_slope']),slope)
            assert np.isclose(float(row[key+'_growth_pct']),100*np.expm1(slope))
    ns='{http://www.w3.org/2000/svg}';svg=ET.parse(out/'Fig2.svg').getroot();nodes={g.get('id'):g for g in svg.iter(ns+'g')}
    def path(identifier):
        group=nodes[identifier];element=next(group.iter(ns+'path'))
        vertices=np.array(re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',element.get('d')),dtype=float).reshape(-1,2)
        uses=list(group.iter(ns+'use'))
        if len(uses)==1:vertices+=np.array([float(uses[0].get('x','0')),float(uses[0].get('y','0'))])
        return vertices
    for panel in geom['panels']:
        label=panel['panel'];x0,y0,w,h=panel['plot_rectangle_pt'];xmin,xmax=panel['xlim'];ymin,ymax=panel['ylim']
        def transform(x,y):return np.column_stack([x0+(np.asarray(x)-xmin)/(xmax-xmin)*w,313-y0-(np.asarray(y)-ymin)/(ymax-ymin)*h])
        for group in range(1,5):
            rr=[r for r in points if r['panel']==label and int(r['group'])==group];assert len(rr)==19
            for r in rr:
                row=by_country[r['country']]
                assert float(r['x'])==float(row[r['xkey']+'_growth_pct']) and float(r['y'])==float(row[r['ykey']+'_growth_pct'])
                assert int(r['group'])==groups[r['country']] and r['colour']==colours[group]
            values=np.array([[float(r['x']),float(r['y'])] for r in rr])
            uses=list(nodes[f'country_cluster_points_{label}_Q{group}'].iter(ns+'use'))
            actual=np.array([[float(u.get('x')),float(u.get('y'))] for u in uses])
            assert actual.shape==(19,2) and np.allclose(actual,transform(values[:,0],values[:,1]),atol=1e-5)
            region=next(r for r in geom['regions'] if r['panel']==label and r['group']==group)
            centre=np.median(values,axis=0);covariance=np.cov(values,rowvar=False,ddof=1);inverse=np.linalg.inv(covariance)
            distance=np.einsum('ij,jk,ik->i',values-centre,inverse,values-centre);radius=np.sort(distance)[12]
            assert np.allclose(centre,region['centre']) and np.allclose(covariance,region['covariance'])
            assert np.isclose(radius,region['radius_squared']) and np.sum(distance<=radius+1e-10)==region['central_countries']==13
            boundary=path(f'country_cluster_fill_{label}_Q{group}')
            original=np.column_stack([xmin+(boundary[:,0]-x0)/w*(xmax-xmin),ymin+(313-y0-boundary[:,1])/h*(ymax-ymin)])
            actual_distance=np.einsum('ij,jk,ik->i',original-centre,inverse,original-centre)
            assert np.allclose(actual_distance,radius,atol=1e-5)
            assert original[:,0].min()>=xmin and original[:,0].max()<=xmax and original[:,1].min()>=ymin and original[:,1].max()<=ymax
        rr=[r for r in points if r['panel']==label];x=np.array([float(r['x']) for r in rr]);y=np.array([float(r['y']) for r in rr])
        fit=sm.OLS(y,sm.add_constant(x)).fit();cov=fit.get_robustcov_results(cov_type='HC3').cov_params()
        stat=next(s for s in geom['statistics'] if s['panel']==label);change=np.array([[1,x.mean()],[0,1]])
        assert np.allclose(change@fit.params,stat['coefficients']) and np.allclose(change@cov@change.T,stat['covariance'])
        curve=[r for r in curves if r['panel']==label];grid=np.array([float(r['x']) for r in curve]);design=sm.add_constant(grid)
        estimate=fit.predict(design);se=np.sqrt(np.diag(design@cov@design.T));critical=t.ppf(.975,74)
        lower,upper=estimate-critical*se,estimate+critical*se
        for key,computed in [('estimate',estimate),('lower95',lower),('upper95',upper)]:assert np.allclose([float(r[key]) for r in curve],computed)
        band=path('country_trend_band_'+label)
        for lo,hi in zip(transform(grid,lower),transform(grid,upper)):
            matches=band[np.isclose(band[:,0],lo[0],atol=1e-5,rtol=0),1]
            assert len(matches)>=2 and np.allclose([matches.min(),matches.max()],[hi[1],lo[1]],atol=1e-5)
    alignment=json.loads((qa/'alignment.json').read_text());assert alignment['verdict']=='PASS'
    assert all(np.isclose(p['bbox_pt'][3]-p['bbox_pt'][1],95.) for p in alignment['layout']['panels'])
    previous=ROOT/'outputs/fig2_v3_histograms_20261028/quartile_country_clusters_update/Fig2.pdf'
    with pymupdf.open(out/'Fig2.pdf') as doc,pymupdf.open(previous) as ref:
        page=doc[0];clip=pymupdf.Rect(0,0,page.rect.width,150.)
        assert page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False).samples==ref[0].get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False).samples
        assert min(s['size'] for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans'])>=7.99
        page.get_pixmap(matrix=pymupdf.Matrix(3,3),alpha=False).save(qa/'preview.png')
    protected=json.loads((ROOT/'outputs/fig2_v3_histograms_20261028/protected_files.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in protected.items())
    result=dict(status='PASS',countries=76,annual_records_used=2128,source_metrics_verified=8512,
        growth_rates_verified=304,country_point_positions_verified=152,group_sizes=[19]*4,
        descriptive_regions_verified=8,countries_inside_each_region=13,independent_hc3_fits_verified=2,
        fitted_grid_values_verified=402,confidence_boundaries_verified=804,unchanged_upper_a_d=True,
        minimum_text_pt=8.,all_main_plot_heights_pt=95.,alignment='PASS',no_point_jitter=True,
        protected_files_unchanged=len(protected))
    (qa/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
