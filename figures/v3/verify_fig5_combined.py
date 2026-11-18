"""Independently validate combined margins, indices, transformed fits and PDF geometry."""
from __future__ import annotations
import hashlib,json,os,sys
from pathlib import Path
from prepare_fig5_combined import read,ROOT,OUT,DATA,QA,CLEAN
if os.environ.get('NHB_FIGURE_PROFILE')=='journal':
    OUT=OUT/'NHB_final'
    DATA=OUT/'source_data';QA=OUT/'QA/Fig5'
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np
from scipy import stats
from scipy.special import logit,expit
import pymupdf
from matplotlib.path import Path as PlotPath

def main():
    source=json.loads((QA/'data_manifest.json').read_text(encoding='utf8'))
    manifest=json.loads((QA/'figure_manifest.json').read_text(encoding='utf8'))
    countries=source['country_codes'];assert len(countries)==76 and not set(countries)&{'HK','MO','TW'}
    annual=read(DATA/'Fig5_combined_country_year_metrics.csv');means=read(DATA/'Fig5_combined_country_mean_levels.csv')
    fits=read(DATA/'Fig5_combined_fits.csv');curves=read(DATA/'Fig5_combined_fit_curves.csv')
    boots=read(DATA/'Fig5_combined_fit_bootstrap.csv');points=read(DATA/'Fig5_scatter_plotted_values.csv')
    labels=read(DATA/'Fig5_country_labels.csv')
    assert len(annual)==2128 and len(means)==76 and len(points)==152 and len(fits)==2
    annual_lookup={(r['country'],int(r['year'])):r for r in annual}
    mean_lookup={r['country']:r for r in means}
    codes=','.join("'"+c+"'" for c in countries)
    con=duckdb.connect()
    path=str(CLEAN/'domestic_city_margins.csv').replace("'","''")
    margins=con.execute(f"""WITH combined AS (
        SELECT country,year,city_id,sum(flow) strength FROM read_csv_auto('{path}')
        WHERE country IN ({codes}) GROUP BY ALL)
        SELECT country,year,list(strength) FROM combined GROUP BY ALL""").fetchall()
    assert len(margins)==2128
    for cc,year,vals in margins:
        w=np.asarray(vals);w.sort();n=len(w);cdf=np.r_[0,np.cumsum(w)/w.sum()]
        gini=1-2*np.trapezoid(cdf,np.arange(n+1)/n)
        hhi=float(np.sum(w*w)/w.sum()**2);ref=annual_lookup[cc,int(year)]
        assert np.isclose(gini,float(ref['domestic_Gini']),atol=1e-12)
        assert np.isclose(hhi,float(ref['domestic_HHI']),atol=1e-12)
        assert n==int(ref['domestic_cities'])
        assert np.isclose(w.sum(),float(ref['domestic_city_strength']))
        assert np.isclose(w.sum(),2*float(ref['domestic_flow_events']))
    path=str(CLEAN/'country_annual_margins.csv').replace("'","''")
    international=con.execute(f"SELECT country,year,sum(flow) FROM read_csv_auto('{path}') WHERE country IN ({codes}) GROUP BY ALL").fetchall()
    con.close();assert len(international)==2128
    for cc,year,flow in international:assert np.isclose(flow,float(annual_lookup[cc,int(year)]['international_flow']))
    for cc in countries:
        rows=sorted([r for r in annual if r['country']==cc],key=lambda r:int(r['year']))
        assert [int(r['year']) for r in rows]==list(range(1998,2026))
        ref=mean_lookup[cc]
        for target,col in [('mean_annual_international_flow','international_flow'),('mean_domestic_HHI','domestic_HHI'),('mean_domestic_Gini','domestic_Gini')]:
            assert np.isclose(float(ref[target]),np.mean([float(r[col]) for r in rows]),atol=1e-12)
    x=np.log10([float(r['mean_annual_international_flow']) for r in means])
    for metric in ['HHI','Gini']:
        observed=np.array([float(r['mean_domestic_'+metric]) for r in means])
        y=np.log10(observed) if metric=='HHI' else logit(observed)
        a,b=np.linalg.lstsq(np.column_stack([np.ones(76),x]),y,rcond=None)[0]
        fit=next(r for r in fits if r['metric']==metric)
        assert np.allclose([a,b],[float(fit['intercept']),float(fit['slope'])],atol=1e-12)
        rx,ry=stats.rankdata(x),stats.rankdata(observed)
        assert np.isclose(float(fit['spearman_r']),np.corrcoef(rx,ry)[0,1])
        assert np.isclose(float(fit['pearson_r']),np.corrcoef(x,y)[0,1])
        rows=[r for r in curves if r['metric']==metric];br=[r for r in boots if r['metric']==metric]
        assert len(rows)==241 and len(br)==5000
        grid=np.log10([float(r['x']) for r in rows]);pred=a+b*grid
        posterior=np.array([float(r['intercept']) for r in br])[:,None]+np.array([float(r['slope']) for r in br])[:,None]*grid
        lo,hi=np.quantile(posterior,[.025,.975],axis=0)
        transform=(lambda z:10**z) if metric=='HHI' else expit
        assert np.allclose(transform(pred),[float(r['y']) for r in rows])
        assert np.allclose(transform(lo),[float(r['ci_low']) for r in rows])
        assert np.allclose(transform(hi),[float(r['ci_high']) for r in rows])
        if metric=='Gini':assert np.all((transform(lo)>0)&(transform(hi)<1))
    alignment=json.loads((QA/'alignment.json').read_text(encoding='utf8'))
    fonts=json.loads((QA/'pdf_text.json').read_text(encoding='utf8'))
    collision=json.loads((QA/'collisions.json').read_text(encoding='utf8'))
    preflight=json.loads((QA/'source_preflight.json').read_text(encoding='utf8'))
    assert alignment['verdict']=='PASS' and fonts['below_minimum_count']==0 and collision['summary']['fail']==0
    assert preflight['summary']['counts'].get('FAIL',0)==0
    assert all(f['severity']=='WARN' and f['kind']=='text-fill-edge' for f in collision['findings'])
    max_point_error=0;max_line_error=0;labels_checked=0;band_vertices=0
    with pymupdf.open(OUT/'Fig5.pdf') as doc:
        page=doc[0]
        assert np.isclose(page.rect.width/72*25.4,180,atol=.001) and np.isclose(page.rect.height,425,atol=.001)
        assert np.allclose([page.rect.width/72*25.4,page.rect.height/72*25.4],manifest['dimensions_mm'],atol=.001)
        draws=page.get_drawings()
        circles=[d for d in draws if d['fill'] is not None and len(d['items'])>=4 and all(i[0]=='c' for i in d['items'])]
        assert len(circles)==228
        # MuPDF colour management introduces sub-8-bit RGB rounding for PDF greys.
        assert all(d['type']=='f' and d['color'] is None and np.all(np.rint(np.array(d['fill'])*255)==74) and np.isclose(d['fill_opacity'],.7,atol=1e-6) for d in circles)
        spans=[s for block in page.get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for s in line['spans']]
        for ps in manifest['panels']:
            if ps['panel'] not in ['a','b']:continue
            panel=ps['panel'];metric=ps['metric'];rect=pymupdf.Rect(ps['bbox_pdf_pt'])
            def to_pdf(xx,yy):
                xlo,xhi=np.log10(ps['xlim']);xv=np.log10(xx)
                if metric=='HHI':ylo,yhi=np.log10(ps['ylim']);yv=np.log10(yy)
                else:ylo,yhi=ps['ylim'];yv=yy
                return np.array([rect.x0+(xv-xlo)/(xhi-xlo)*rect.width,rect.y1-(yv-ylo)/(yhi-ylo)*rect.height])
            rows=[r for r in points if r['panel']==panel];assert len(rows)==76
            assert {r['country'] for r in rows}==set(countries)
            number=10 if manifest['formatting']['profile']=='manuscript' else 15
            major={r['country'] for r in sorted(means,key=lambda r:-float(r['total_international_events']))[:number]}
            assert major<=set(ps['labelled_countries'])
            for r in rows:
                ref=mean_lookup[r['country']];xx=float(ref['mean_annual_international_flow']);yy=float(ref['mean_domestic_'+metric])
                assert np.allclose([float(r['x']),float(r['y'])],[xx,yy])
                pt=to_pdf(xx,yy)
                assert np.linalg.norm(pt-np.array([float(r['pdf_x_pt']),float(r['pdf_y_pt'])]))<.002
                error=min(np.linalg.norm(pt-np.array([(d['rect'].x0+d['rect'].x1)/2,(d['rect'].y0+d['rect'].y1)/2])) for d in circles)
                assert error<.002;max_point_error=max(max_point_error,float(error))
            for r in [r for r in labels if r['panel']==panel]:
                # PDF font ascent/descent boxes differ slightly from the
                # Matplotlib text extents used to place the same label.
                label_rect=pymupdf.Rect(rect.x0-.5,rect.y0-.5,rect.x1+.5,rect.y1+.5)
                found=[s for s in spans if s['text']==r['country'] and label_rect.contains(pymupdf.Rect(s['bbox']))]
                assert len(found)==1;labels_checked+=1
            color=np.array([int(manifest['palette'][metric][i:i+2],16) for i in [1,3,5]])/255
            lines=[d for d in draws if d['color'] is not None and np.allclose(d['color'],color,atol=1e-5) and np.isclose(d['width'],1.1)]
            segments=[(np.array([i[1].x,i[1].y]),np.array([i[2].x,i[2].y])) for d in lines for i in d['items'] if i[0]=='l']
            start=np.array([s for s,e in segments]);vec=np.array([e-s for s,e in segments]);norm=np.sum(vec*vec,axis=1)
            fills=[d for d in draws if d['fill'] is not None and np.allclose(d['fill'],color,atol=1e-5) and np.isclose(d['fill_opacity'],.13,atol=.001)]
            vertices=np.array([[p.x,p.y] for d in fills for i in d['items'] if i[0]=='l' for p in i[1:]])
            cr=[r for r in curves if r['metric']==metric]
            for r in cr:
                pt=to_pdf(float(r['x']),float(r['y']))
                fraction=np.clip(np.sum((pt-start)*vec,axis=1)/norm,0,1)
                error=float(np.min(np.linalg.norm(pt-start-fraction[:,None]*vec,axis=1)))
                assert error<.002;max_line_error=max(max_line_error,error)
                for key in ['ci_low','ci_high']:
                    pt=to_pdf(float(r['x']),float(r[key]))
                    assert np.min(np.linalg.norm(vertices-pt,axis=1))<.002;band_vertices+=1
    from verify_fig5_stratified import verify
    stratified_report=verify(manifest)
    report=dict(status='PASS',countries=76,country_years=2128,independent_source='Directional cleaned city-margin CSV and country-margin CSV',
        recomputed_annual_indices=4256,combined_international_totals_checked=2128,country_means_checked=228,
        fits_checked=2,bootstrap_replicates_checked=10000,confidence_band_vertices_checked=band_vertices,
        pdf_markers_checked=228,country_labels_checked=labels_checked,max_pdf_marker_error_pt=max_point_error,
        max_pdf_fit_error_pt=max_line_error,alignment='PASS',collision_failures=0,collision_warnings=collision['summary']['warn'],
        minimum_font_pt=fonts['minimum_found_pt'],all_markers_dark_gray_with_transparency=True,all_marker_edges_removed=True,
        final_pdf_sha256=hashlib.sha256((OUT/'Fig5.pdf').read_bytes()).hexdigest())
    report.update(stratified_report)
    (QA/'data_and_visual_checks.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
