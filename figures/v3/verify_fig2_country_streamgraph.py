"""Reconcile stream thickness, country labels, and unchanged upper panels."""
from pathlib import Path
import csv
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
import re

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import numpy as np
import pymupdf


def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def main():
    out=Path(__file__).parent;data=out/'source_data';qa=out/'QA/Fig2'
    manifest=json.loads((qa/'figure_manifest.json').read_text(encoding='utf-8'))
    geom=manifest['country_stream_panel']
    assert manifest['edition']=='v3' and geom['country_count']==7
    assert json.loads((qa/'alignment.json').read_text(encoding='utf-8'))['verdict']=='PASS'
    selection=read(data/'Fig2_country_stream_selection.csv')
    annual=read(data/'Fig2_country_stream_annual.csv')
    boundaries=read(data/'Fig2_country_stream_boundaries.csv')
    labels=read(data/'Fig2_country_stream_labels.csv')
    members={r['country'] for r in selection}
    selected=[r['country'] for r in selection[:7]]
    assert set(selected)==set(geom['stack_order'])
    assert len(selection)==76 and len(annual)==196 and len(boundaries)==7567 and len(labels)==7
    # Use the canonical cleaned city margins, independently of plotting tables.
    totals={cc:0. for cc in members};city_sets={}
    clean=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/domestic_city_margins.csv'
    for r in read(clean):
        if r['side']=='inflow' and r['country'] in members:
            cc=r['country'];year=int(r['year']);totals[cc]+=float(r['flow'])
            city_sets.setdefault((cc,year),set()).add(r['city_id'])
    assert selected==sorted(totals,key=lambda cc:(-totals[cc],cc))[:7]
    for r in selection:
        assert np.isclose(float(r['total_domestic_events']),totals[r['country']])
    for r in annual:
        assert int(r['domestic_inflow_cities'])==len(city_sets[r['country'],int(r['year'])])
    curves={cc:[r for r in boundaries if r['country']==cc] for cc in selected}
    for cc,rows in curves.items():
        assert len(rows)==1081
        x=np.array([float(r['year']) for r in rows])
        assert np.all(np.diff(x)>0)
        lo=np.array([float(r['lower']) for r in rows]);hi=np.array([float(r['upper']) for r in rows])
        n=np.array([float(r['display_cities']) for r in rows])
        assert np.allclose(hi-lo,n,atol=1e-10)
        for year in range(1998,2026):
            i=np.flatnonzero(np.isclose(x,year,atol=1e-12,rtol=0))[0]
            assert abs(n[i]-len(city_sets[cc,year]))<1e-9
        for year in range(1998,2025):
            part=n[(x>=year)&(x<=year+1)]
            ends=[len(city_sets[cc,year]),len(city_sets[cc,year+1])]
            assert part.min()>=min(ends)-1e-9 and part.max()<=max(ends)+1e-9
    # Verify actual vector thickness at all observed-year knots in the SVG.
    ns='{http://www.w3.org/2000/svg}';svg=ET.parse(out/'Fig2.svg').getroot()
    stream_paths={}
    for cc in selected:
        group=next(g for g in svg.iter(ns+'g') if g.get('id')=='country_stream_'+cc)
        path=next(group.iter(ns+'path'))
        nums=[float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',path.get('d'))]
        stream_paths[cc]=np.array(nums).reshape(-1,2)
    x0,y0,w,h=geom['plot_rectangle_pt'];ylim=geom['ylim'];height=370.
    for r in annual:
        xx=x0+(int(r['year'])-1998)/27*w
        yy=stream_paths[r['country']][np.isclose(stream_paths[r['country']][:,0],xx,atol=.00001,rtol=0),1]
        assert len(yy)>=2,(r['country'],r['year'])
        expected=int(r['domestic_inflow_cities'])/(ylim[1]-ylim[0])*h
        assert abs(np.ptp(yy)-expected)<.001
    with pymupdf.open(out/'Fig2.pdf') as doc,pymupdf.open(ROOT/'figures/v4/Fig2.pdf') as ref:
        page=doc[0];assert abs(page.rect.height-height)<.001
        # Equal native canvas and fonts permit a strict upper-row raster comparison.
        # The upper-row xlabel glyphs end at145.46pt; lower-panel text starts
        # near153pt in V4, so150pt isolates all of a-d without including e.
        clip=pymupdf.Rect(0,0,page.rect.width,150.)
        p=page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False)
        q=ref[0].get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False)
        delta=np.abs(np.frombuffer(p.samples,dtype=np.uint8).astype(int)-np.frombuffer(q.samples,dtype=np.uint8).astype(int))
        upper_identical=bool(np.max(delta)==0)
        if not upper_identical:
            # Font/output rounding can alter antialiasing by a small amount.
            assert delta.max()<=20 and np.mean(delta!=0)<.005
        spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']]
        assert min(s['size'] for s in spans)>=7.99
        assert all(sum(s['text']==cc for s in spans)==1 for cc in selected)
        assert not any('r =' in s['text'] for s in spans)
        page.get_pixmap(matrix=pymupdf.Matrix(3,3),alpha=False).save(qa/'preview.png')
        page.get_pixmap(matrix=pymupdf.Matrix(4,4),clip=pymupdf.Rect(0,155,page.rect.width,page.rect.height),alpha=False).save(qa/'stream_panel_preview.png')
    protected_path=ROOT/'outputs/fig2_v3_country_streamgraph_20261028/protected_files.json'
    protected=json.loads(protected_path.read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in protected.items())
    result=dict(status='PASS',countries=selected,annual_city_counts_verified=196,
        all_observed_years_preserved=True,svg_stream_thicknesses_verified=196,
        shape_preserving_interpolation_verified=True,direct_country_labels=7,
        upper_a_d_render_identical=upper_identical,upper_a_d_max_pixel_difference=int(delta.max()),
        protected_v4_and_manuscript_files_unchanged=len(protected),alignment='PASS',minimum_text_pt=8.)
    (qa/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
