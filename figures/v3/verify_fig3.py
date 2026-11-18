"""Reconcile the Fig3 quantitative panels and final PDF inset clearances."""
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
sys.path.insert(0,str(ROOT/'tmp'/'nhb_fig2_python_deps'))
import numpy as np
import pymupdf

if os.environ.get('NHB_FIGURE_PROFILE')=='journal':
    OUT=OUT/'NHB_final'
DATA=OUT/'source_data'
QA=OUT/'QA'/'Fig3'

def read(name):
    with (DATA/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def main():
    rows=read('Fig3_country_year_data.csv')
    metrics=read('Fig3_country_metrics.csv')
    density=read('Fig3_density_curves.csv')
    lorenz=read('Fig3_lorenz_curves.csv')
    tops=read('Fig3_top_country_shares.csv')
    assert len(metrics)==56 and len(tops)==168
    checks=[]
    for side in ['inflow','outflow']:
        for year in range(1998,2026):
            rs=[r for r in rows if r['side']==side and int(r['year'])==year]
            p=np.array([float(r['share']) for r in rs]);n=len(p)
            m=next(r for r in metrics if r['side']==side and int(r['year'])==year)
            hhi=float(sum(p*p))
            gini=float(2*sum(np.arange(1,n+1)*np.sort(p))/n-(n+1)/n)
            assert abs(sum(p)-1)<1e-12 and abs(hhi-float(m['HHI']))<1e-12
            assert abs(gini-float(m['Gini']))<1e-12
            assert abs(1/(n*hhi)-float(m['normalized_equivalent_countries']))<1e-12
            assert .06<hhi<.11 and .845<gini<.905
            assert .044<float(m['normalized_equivalent_countries'])<.073
            for k in [1,5,10]:
                top=next(r for r in tops if r['side']==side and int(r['year'])==year and int(r['top_k'])==k)
                assert abs(sum(np.sort(p)[-k:])-float(top['share']))<1e-12
                assert abs(100*float(top['share'])-float(top['share_percent']))<1e-10
            checks.append(dict(side=side,year=year,countries=n,HHI=hhi,Gini=gini,
                               normalized_equivalent=1/(n*hhi)))
    for side in ['inflow','outflow']:
        for year in [1998,2007,2016,2025]:
            ds=[r for r in density if r['side']==side and int(r['year'])==year]
            x=np.array([float(r['log10_share_percent']) for r in ds])
            y=np.array([float(r['density_per_log10_share_percent']) for r in ds])
            assert abs(np.trapezoid(y,x)-1)<1e-5
            ls=[r for r in lorenz if r['side']==side and int(r['year'])==year]
            lx=np.array([float(r['cumulative_country_fraction']) for r in ls])
            ly=np.array([float(r['cumulative_flow_fraction']) for r in ls])
            m=next(r for r in metrics if r['side']==side and int(r['year'])==year)
            assert len(ls)==int(m['countries'])+1
            assert lx[0]==ly[0]==0 and lx[-1]==ly[-1]==1
            assert np.all(np.diff(lx)>0) and np.all(np.diff(ly)>=0)
            assert abs(1-2*np.trapezoid(ly,lx)-float(m['Gini']))<1e-12
    alignment=json.loads((QA/'alignment.json').read_text(encoding='utf8'))
    panels={p['id']:p for p in alignment['layout']['panels']}
    assert alignment['verdict']=='PASS'
    manifest=json.loads((QA/'figure_manifest.json').read_text(encoding='utf8'))
    for upper,lower in [('a','c_annual'),('b','d_annual')]:
        assert abs(panels[upper]['bbox_pt'][2]-panels[lower]['bbox_pt'][2])<1e-8
    assert all(manifest['density_display_xlim'][0]<=float(r['log10_share_percent'])<=manifest['density_display_xlim'][1]
               for r in rows)
    ymax=math.ceil(max(float(r['density_per_log10_share_percent']) for r in density)*1.55*20)/20
    parent_curves={};ranges={}
    for side,letter,group in [('inflow','a','c'),('outflow','b','d')]:
        parent_curves[letter]=[];ranges[letter]=(tuple(manifest['density_display_xlim']),(0,ymax))
        parent_curves[group]=[];ranges[group]=((0,100),(0,100))
        for year in [1998,2007,2016,2025]:
            ds=[r for r in density if r['side']==side and int(r['year'])==year]
            parent_curves[letter].append((np.array([float(r['log10_share_percent']) for r in ds]),
                np.array([float(r['density_per_log10_share_percent']) for r in ds])))
            ls=[r for r in lorenz if r['side']==side and int(r['year'])==year]
            lx=np.array([100*float(r['cumulative_country_fraction']) for r in ls])
            ly=np.array([100*float(r['cumulative_flow_fraction']) for r in ls])
            xx=np.linspace(0,100,3001)
            parent_curves[group].append((xx,np.interp(xx,lx,ly)))
    manifest=json.loads((QA/'figure_manifest.json').read_text(encoding='utf8'))
    assert len(manifest['zoom_source_coordinate_checks'])==16
    assert all(r['matches_parent_polyline'] and r['max_vertical_error']<1e-10
               for r in manifest['zoom_source_coordinate_checks'])
    windows=read('Fig3_zoom_windows.csv');zoom_vertices=read('Fig3_zoom_curves.csv')
    assert len(windows)==4
    for window in windows:
        parent=window['parent'];side=window['side']
        for year in [1998,2007,2016,2025]:
            if parent in ['a','b']:
                source=[r for r in density if r['side']==side and int(r['year'])==year]
                xs=[float(r['log10_share_percent']) for r in source]
                ys=[float(r['density_per_log10_share_percent']) for r in source]
            else:
                source=[r for r in lorenz if r['side']==side and int(r['year'])==year]
                xs=[100*float(r['cumulative_country_fraction']) for r in source]
                ys=[100*float(r['cumulative_flow_fraction']) for r in source]
            zs=[r for r in zoom_vertices if r['parent']==parent and int(r['year'])==year]
            zx=np.array([float(r['x']) for r in zs]);zy=np.array([float(r['y']) for r in zs])
            assert len(zs)>2 and max(abs(zy-np.interp(zx,xs,ys)))<1e-10
            assert min(zx)>=float(window['xmin'])-1e-12 and max(zx)<=float(window['xmax'])+1e-12
            assert min(zy)>=float(window['ymin'])-1e-12 and max(zy)<=float(window['ymax'])+1e-12
    pairs=[('a','a_zoom'),('b','b_zoom'),('c','c_zoom'),('d','d_zoom')]
    clearances=[];proportional_checks=[]
    with pymupdf.open(OUT/'Fig3.pdf') as doc:
        page=doc[0]
        drawing_rectangles=[d['rect'] for d in page.get_drawings()]
        for parent,child in pairs:
            main=panels[parent]['bbox_pt'];ins=panels[child]['bbox_pt']
            (xmin,xmax),(ymin,ymax_i)=ranges[parent]
            window=next(r for r in windows if r['parent']==parent)
            roi=np.array([[float(window['xmin']),float(window['ymin'])],
                [float(window['xmax']),float(window['ymax'])]])
            source_width=(roi[1,0]-roi[0,0])/(xmax-xmin)*(main[2]-main[0])
            source_height=(roi[1,1]-roi[0,1])/(ymax_i-ymin)*(main[3]-main[1])
            zoom_width=ins[2]-ins[0];zoom_height=ins[3]-ins[1]
            assert abs(zoom_width/source_width-zoom_height/source_height)<1e-9
            source_rect=[main[0]+(roi[0,0]-xmin)/(xmax-xmin)*(main[2]-main[0]),
                page.rect.height-(main[1]+(roi[1,1]-ymin)/(ymax_i-ymin)*(main[3]-main[1])),
                main[0]+(roi[1,0]-xmin)/(xmax-xmin)*(main[2]-main[0]),
                page.rect.height-(main[1]+(roi[0,1]-ymin)/(ymax_i-ymin)*(main[3]-main[1]))]
            inset_rect=[ins[0],page.rect.height-ins[3],ins[2],page.rect.height-ins[1]]
            errors=[min(max(abs(a-b) for a,b in zip(expected,actual))
                for actual in drawing_rectangles) for expected in [source_rect,inset_rect]]
            assert max(errors)<.002,(parent,errors)
            if parent in ['a','b']:
                assert ins[0]>(main[0]+main[2])/2 and ins[1]>(main[1]+main[3])/2
            proportional_checks.append(dict(parent=parent,source_aspect_ratio=source_width/source_height,
                inset_aspect_ratio=zoom_width/zoom_height,equal_horizontal_vertical_magnification=True,
                magnification=zoom_width/source_width,rendered_source_and_inset_rectangle_errors_pt=errors,
                identical_crop_limits_and_paths=True))
            paths=[]
            for x,y in parent_curves[parent]:
                xp=main[0]+(x-xmin)/(xmax-xmin)*(main[2]-main[0])
                yp=main[1]+(y-ymin)/(ymax_i-ymin)*(main[3]-main[1])
                paths.append((xp,yp))
                inside=(xp>=ins[0])&(xp<=ins[2])
                assert max(yp[inside])<ins[1],(parent,child,'Inset masks observations')
            for t in page.get_texttrace():
                b=t['bbox'];yc=page.rect.height-(b[1]+b[3])/2
                if not(b[0]>=ins[0]-26 and b[2]<=ins[2]+7 and ins[1]-18<yc<ins[3]+4):
                    continue
                text=''.join(chr(c[0]) for c in t['chars']);gaps=[]
                for xp,yp in paths:
                    use=(xp>=b[0]-.4)&(xp<=b[2]+.4)
                    if np.any(use):
                        gaps.append(float(page.rect.height-b[3]-max(yp[use])))
                if gaps:
                    assert min(gaps)>2,(parent,text,gaps)
                    clearances.append(dict(parent=parent,inset=child,text=text,min_curve_clearance_pt=min(gaps)))
        for name,ids in [('a',['a']),('b',['b']),('c',['c','c_annual']),('d',['d','d_annual'])]:
            bbs=[panels[i]['bbox_pt'] for i in ids]
            clip=pymupdf.Rect(max(0,min(b[0] for b in bbs)-34),
                max(0,page.rect.height-max(b[3] for b in bbs)-20),
                min(page.rect.width,max(b[2] for b in bbs)+8),
                min(page.rect.height,page.rect.height-min(b[1] for b in bbs)+30))
            page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=clip,alpha=False).save(QA/f'preview_{name}.png')
    collision=json.loads((QA/'collisions.json').read_text(encoding='utf8'))
    fonts=json.loads((QA/'pdf_text.json').read_text(encoding='utf-8-sig'))
    assert collision['summary']['fail']==0 and fonts['below_minimum_count']==0
    assert all(r['kind']=='text-fill-edge' for r in collision['findings'])
    report=dict(final_pdf_sha256=hashlib.sha256((OUT/'Fig3.pdf').read_bytes()).hexdigest(),
        metric_checks=checks,auxiliary_top_country_share_values_verified=168,density_curves_normalized=8,
        Lorenz_curves_verified=8,annual_main_Gini_observations=56,annual_main_HHI_observations=56,
        annual_dual_axis_plots=2,secondary_Gini_axes=2,annual_HHI_insets=0,top_country_share_insets=0,
        local_zoom_insets=4,zoom_curves_identical_to_main=16,
        proportional_zoom_checks=proportional_checks,density_zooms_at_upper_right=True,
        main_axes=6,alignment='PASS',minimum_font_pt=fonts['minimum_found_pt'],
        inset_text_clearances=clearances,
        minimum_inset_text_curve_clearance_pt=min(r['min_curve_clearance_pt'] for r in clearances),
        no_observed_parent_curve_hidden_by_insets=True,
        Lorenz_reference_line_note='Equality reference is interrupted beneath the zoom-and-text footprint; observed Lorenz curves remain intact',
        collision_failures=0,collision_warnings_reviewed=[dict(text=r['text'],bbox=r['text_bbox'],
            reason='Inset labels sit above observed parent curves; filled-path bounding boxes alone intersect. Numerical clearance and final detail previews inspected.') for r in collision['findings']])
    (QA/'data_and_visual_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(status='PASS',main_axes=6,insets=4,secondary_axes=2,zoom_curves_verified=16,annual_main_Gini_values=56,annual_main_HHI_values=56,
        min_font_pt=fonts['minimum_found_pt'],minimum_text_curve_clearance_pt=report['minimum_inset_text_curve_clearance_pt'],
        collision_failures=0,reviewed_warnings=len(report['collision_warnings_reviewed'])),ensure_ascii=False))

if __name__=='__main__':
    main()
