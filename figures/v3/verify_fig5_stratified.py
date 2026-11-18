"""Check full-series share stratification and every linked distribution mark."""
from __future__ import annotations
import json
import os
from prepare_fig5_combined import read, OUT, DATA, CLEAN
if os.environ.get('NHB_FIGURE_PROFILE')=='journal':
    OUT=OUT/'NHB_final';DATA=OUT/'source_data'
import duckdb
import numpy as np
from scipy import stats
import pymupdf


def verify(manifest):
    annual=read(DATA/'Fig5_combined_country_year_metrics.csv')
    reference={(r['country'],int(r['year'])):r for r in annual}
    observations=read(DATA/'Fig5_stratified_annual_observations.csv')
    trends=read(DATA/'Fig5_stratified_country_trends.csv')
    assert len(observations)==2128 and len(trends)==76
    path=str(CLEAN/'flow_top100.parquet').replace("'","''")
    con=duckdb.connect()
    # Count raw international events twice: one endpoint at each country.
    totals={int(y):2*float(f) for y,f in con.execute(f"""SELECT year,sum(flow)
        FROM read_parquet('{path}') WHERE origin_country<>destination_country AND flow>0 GROUP BY year""").fetchall()}
    con.close()
    centered=np.arange(28,dtype=float)-13.5
    denominator=centered@centered
    values={}
    for trend in trends:
        cc=trend['country']
        rows=sorted((r for r in observations if r['country']==cc),key=lambda r:int(r['year']))
        assert [int(r['year']) for r in rows]==list(range(1998,2026))
        shares=[];ginis=[]
        for r in rows:
            ref=reference[cc,int(r['year'])]
            share=float(ref['international_flow'])/totals[int(r['year'])]
            assert np.isclose(float(r['global_combined_international_flow']),totals[int(r['year'])])
            assert np.isclose(float(r['international_share']),share,rtol=1e-12)
            assert np.isclose(float(r['domestic_Gini']),float(ref['domestic_Gini']),atol=1e-12)
            shares.append(share);ginis.append(float(r['domestic_Gini']))
        share_rate=float(100*np.expm1(centered@np.log(shares)/denominator))
        gini_rate=float(1000*centered@np.asarray(ginis)/denominator)
        assert np.isclose(share_rate,float(trend['international_share_annual_rate_pct']),atol=1e-10)
        assert np.isclose(gini_rate,float(trend['domestic_gini_trend_pp_decade']),atol=1e-10)
        values[cc]=(share_rate,gini_rate)
    ordered=sorted(values,key=lambda cc:values[cc][0])
    lookup={r['country']:r for r in trends}
    for j,cc in enumerate(ordered):assert int(lookup[cc]['group'])==j//19+1
    hist=read(DATA/'Fig5_stratified_histogram.csv')
    edges=np.array([float(r['lower']) for r in hist]+[float(hist[-1]['upper'])])
    count,_=np.histogram([v[0] for v in values.values()],bins=edges)
    assert np.array_equal(count,[int(r['countries']) for r in hist]) and int(count.sum())==76
    density=read(DATA/'Fig5_stratified_density_curves.csv')
    strips=read(DATA/'Fig5_stratified_country_strip.csv')
    assert len(density)==1604 and len(strips)==76
    all_gini=np.array([v[1] for v in values.values()])
    robust_sd=min(np.std(all_gini,ddof=1),np.subtract(*np.percentile(all_gini,[75,25]))/1.34)
    bandwidth=.9*robust_sd*19**(-.2)
    groups=read(DATA/'Fig5_stratified_groups.csv')
    for group in range(1,5):
        codes=ordered[(group-1)*19:group*19]
        vv=np.array([values[cc][1] for cc in codes])
        rows=[r for r in density if int(r['group'])==group]
        xx=np.array([float(r['x']) for r in rows])
        assert all(np.isclose(float(r['bandwidth']),bandwidth) for r in rows)
        expected=stats.norm.pdf((xx[:,None]-vv)/bandwidth).mean(axis=1)/bandwidth
        assert np.allclose(expected,[float(r['density']) for r in rows],atol=1e-12)
        spec=next(r for r in manifest['panels'] if r.get('group')==group)
        summary=next(r for r in groups if int(r['group'])==group)
        assert np.isclose(spec['median'],np.median(vv)) and np.isclose(float(summary['gini_trend_median']),np.median(vv))
        assert int(summary['gini_increasing'])==int((vv>0).sum())
        assert {r['country'] for r in strips if int(r['group'])==group}==set(codes)
    density_geometry_error=hist_geometry_error=strip_error=0.
    with pymupdf.open(OUT/'Fig5.pdf') as doc:
        page=doc[0];drawings=page.get_drawings()
        circles=[d for d in drawings if d['fill'] is not None and len(d['items'])>=4 and all(i[0]=='c' for i in d['items'])]
        centers=np.array([[(d['rect'].x0+d['rect'].x1)/2,(d['rect'].y0+d['rect'].y1)/2] for d in circles])
        def position(ps,x,y):
            rect=pymupdf.Rect(ps['bbox_pdf_pt'])
            return np.array([rect.x0+(x-ps['xlim'][0])/np.diff(ps['xlim'])[0]*rect.width,
                rect.y1-(y-ps['ylim'][0])/np.diff(ps['ylim'])[0]*rect.height])
        def line_distance(point,draws):
            segments=[(np.array(i[1]),np.array(i[2])) for d in draws for i in d['items'] if i[0]=='l']
            start=np.array([s for s,e in segments]);vectors=np.array([e-s for s,e in segments])
            norm=np.sum(vectors*vectors,axis=1);keep=norm>1e-20
            start=start[keep];vectors=vectors[keep];norm=norm[keep]
            fraction=np.clip(np.sum((point-start)*vectors,axis=1)/norm,0,1)
            return float(np.min(np.linalg.norm(point-start-fraction[:,None]*vectors,axis=1)))
        for group in range(1,5):
            ps=next(r for r in manifest['panels'] if r.get('group')==group)
            colour=manifest['palette']['quartile_groups'][group-1]
            rgb=np.array([int(colour[i:i+2],16) for i in [1,3,5]])/255
            lines=[d for d in drawings if d['color'] is not None and np.allclose(d['color'],rgb,atol=1e-5)
                and np.isclose(d['width'],1.1)]
            for r in [r for r in density if int(r['group'])==group]:
                p=position(ps,float(r['x']),float(r['density']))
                assert np.linalg.norm(p-[float(r['pdf_x_pt']),float(r['pdf_y_pt'])])<.002
                error=line_distance(p,lines);assert error<.002
                density_geometry_error=max(density_geometry_error,error)
            for r in [r for r in strips if int(r['group'])==group]:
                assert np.isclose(float(r['x']),values[r['country']][1])
                p=position(ps,float(r['x']),float(r['display_y']))
                error=float(np.min(np.linalg.norm(centers-p,axis=1)))
                assert error<.002;strip_error=max(strip_error,error)
        ps=next(r for r in manifest['panels'] if r['panel']=='c')
        rgb=np.array([63,119,106])/255
        lines=[d for d in drawings if d['color'] is not None and np.allclose(d['color'],rgb,atol=1e-5) and np.isclose(d['width'],1.1)]
        for r in hist:
            p=position(ps,(float(r['lower'])+float(r['upper']))/2,float(r['countries']))
            error=line_distance(p,lines);assert error<.002;hist_geometry_error=max(hist_geometry_error,error)
    return dict(full_series_trends_checked=152,raw_global_denominators_checked=28,groups=4,countries_per_group=19,
        histogram_countries=76,histogram_bins_checked=22,kernel_density_values_checked=1604,country_strip_points_checked=76,
        density_bandwidth=float(bandwidth),max_density_pdf_error_pt=density_geometry_error,
        max_histogram_pdf_error_pt=hist_geometry_error,max_country_strip_pdf_error_pt=strip_error)
