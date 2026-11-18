"""Verify Fig4 source values, rendered curve geometry and export checks."""
from pathlib import Path
import csv
import hashlib
import json
import os
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
if os.environ.get('NHB_FIGURE_PROFILE')=='journal':
    OUT=OUT/'NHB_final'
DATA=OUT/'source_data'
QA=OUT/'QA'/'Fig4'
sys.path.insert(0,str(ROOT/'tmp'/'nhb_fig2_python_deps'))
import numpy as np
import pymupdf


def read(name):
    with (DATA/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def main():
    manifest=json.loads((QA/'figure_manifest.json').read_text(encoding='utf8'))
    alignment=json.loads((QA/'alignment.json').read_text(encoding='utf8'))
    fonts=json.loads((QA/'pdf_text.json').read_text(encoding='utf-8-sig'))
    collision=json.loads((QA/'collisions.json').read_text(encoding='utf8'))
    assert alignment['verdict']=='PASS' and fonts['below_minimum_count']==0
    assert collision['summary']['fail']==0
    selected=manifest['selected_countries']
    rank=read('Fig4_country_selection.csv');all_metrics=read('Fig4_all_country_combined_metrics.csv')
    assert len(rank)==76 and len(all_metrics)==76*28
    assert all(float(a['total_domestic_events'])>=float(b['total_domestic_events']) for a,b in zip(rank,rank[1:]))
    t=np.arange(28)-13.5
    audit_lookup={r['country']:r for r in rank}
    for cc,r in audit_lookup.items():
        rs=sorted([m for m in all_metrics if m['country']==cc],key=lambda m:int(m['year']))
        assert [int(m['year']) for m in rs]==list(range(1998,2026))
        for metric in ['HHI','Gini','normalized_equivalent_cities']:
            slope=float(np.dot(t,[float(m[metric]) for m in rs])/np.dot(t,t))
            assert abs(slope-float(r[metric+'_annual_slope']))<1e-12
        assert int(r['minimum_cities'])==min(int(m['N']) for m in rs)
        assert float(r['total_domestic_events'])==sum(float(m['flow_events']) for m in rs)
    first=[r['country'] for r in rank if r['both_trends_positive']=='True']
    case_rows=read('Fig4_case_selection.csv')
    assert selected==['US','PL','BR','IN'] and len(first)==2
    assert len(case_rows)==4
    for i,r in enumerate(case_rows):
        cc=selected[i];reference=audit_lookup[cc]
        rows=[m for m in all_metrics if m['country']==cc]
        assert int(r['position'])==i+1 and r['country']==cc and r['panel']=='bcde'[i]
        assert float(r['total_domestic_events'])==float(reference['total_domestic_events'])
        assert int(r['volume_rank'])==int(reference['volume_rank'])
        assert int(r['minimum_cities'])==min(int(m['N']) for m in rows)
        assert float(r['minimum_annual_events'])==min(float(m['flow_events']) for m in rows)
        assert int(r['group'])==i+1
        assert float(r['total_domestic_events'])>=100000 and float(r['minimum_annual_events'])>=1000 and int(r['minimum_cities'])>=30
        for metric in ['normalized_equivalent_cities','Gini']:
            assert abs(float(r[metric+'_slope_pp'])-100*float(reference[metric+'_annual_slope']))<1e-12
    summaries=read('Fig4_case_period_summary.csv')
    assert len(summaries)==16
    for r in summaries:
        rows=[m for m in all_metrics if m['country']==r['country']
            and int(r['first_year'])<=int(m['year'])<=int(r['last_year'])]
        assert len(rows)==7
        for metric in ['N','flow_events','normalized_equivalent_cities','Gini']:
            assert abs(float(r[metric])-np.mean([float(m[metric]) for m in rows]))<1e-10
    trends=read('Fig4_country_concentration_trends.csv')
    assert len(trends)==76 and {r['country'] for r in trends}==set(audit_lookup)
    counts={'Relative concentration':0,'Deconcentration':0,'Mixed changes':0}
    for r in trends:
        cc=r['country'];x=float(r['normalized_equivalent_cities_slope_pp']);y=float(r['Gini_slope_pp'])
        assert abs(x-100*float(audit_lookup[cc]['normalized_equivalent_cities_annual_slope']))<1e-12
        assert abs(y-100*float(audit_lookup[cc]['Gini_annual_slope']))<1e-12
        category=('Relative concentration' if x<0 and y>0 else
            'Deconcentration' if x>0 and y<0 else 'Mixed changes')
        assert r['category']==category
        counts[category]+=1
    assert counts=={'Relative concentration':63,'Deconcentration':2,'Mixed changes':11}
    membership=read('Fig4_Fig5_quartile_membership.csv')
    with (ROOT/'figures/v3/source_data/Fig5_stratified_country_trends.csv').open(encoding='utf-8-sig',newline='') as f:
        fig5=list(csv.DictReader(f))
    quartiles={r['country']:int(r['group']) for r in fig5}
    assert len(membership)==76 and {r['country']:int(r['group']) for r in membership}==quartiles
    assert {r['country']:int(r['group']) for r in membership}=={cc:int(q) for cc,q in manifest['scatter']['quartile_membership'].items()}
    assert all(list(quartiles.values()).count(q)==19 for q in range(1,5))
    assert [quartiles[c] for c in selected]==[1,2,3,4]
    candidates=read('Fig4_quartile_case_candidates.csv');assert len(candidates)==76
    for r in candidates:
        cc=r['country'];reference=audit_lookup[cc]
        assert int(r['group'])==quartiles[cc]
        minimum=min(float(m['flow_events']) for m in all_metrics if m['country']==cc)
        expected=float(reference['total_domestic_events'])>=100000 and minimum>=1000 and int(reference['minimum_cities'])>=30
        assert (r['eligible']=='True')==expected and (r['selected']=='True')==(cc in selected)
    quartile_summary=read('Fig4_quartile_concentration_summary.csv')
    assert len(quartile_summary)==4
    for row in membership:
        original=next(r for r in fig5 if r['country']==row['country'])
        assert float(row['international_share_annual_rate_pct'])==float(original['international_share_annual_rate_pct'])
        assert row['domestic_category']==next(r['category'] for r in trends if r['country']==row['country'])
        assert row['color']==manifest['scatter']['quartile_colors']['Q'+row['group']]
    for row in quartile_summary:
        q=int(row['group']);assert int(row['countries'])==19
        for key,category in [('relative_concentration','Relative concentration'),('deconcentration','Deconcentration'),('mixed_changes','Mixed changes')]:
            assert int(row[key])==sum(quartiles[r['country']]==q and r['category']==category for r in trends)
    assert [int(r['relative_concentration']) for r in quartile_summary]==[15,17,13,18]
    margins=read('Fig4_domestic_city_margins.csv')
    metrics=read('Fig4_domestic_country_metrics.csv')
    plotted=read('Fig4_plotted_values.csv')
    labels=read('Fig4_scatter_country_labels.csv')
    zoom_points=read('Fig4_zoom_points.csv')
    zx0,zx1=manifest['zoom']['xlim'];zy0,zy1=manifest['zoom']['ylim']
    zoom_codes={r['country'] for r in trends if zx0<=float(r['normalized_equivalent_cities_slope_pp'])<=zx1
        and zy0<=float(r['Gini_slope_pp'])<=zy1}
    assert len(zoom_points)==manifest['zoom']['point_count']
    assert {r['country'] for r in zoom_points}==zoom_codes
    assert {r['country'] for r in labels if r['display']=='inset'}==set(manifest['zoom']['labelled_countries'])
    assert set(selected)<=set(manifest['zoom']['labelled_countries'])
    for r in zoom_points:
        reference_point=next(p for p in trends if p['country']==r['country'])
        assert float(r['point_x'])==float(reference_point['normalized_equivalent_cities_slope_pp'])
        assert float(r['point_y'])==float(reference_point['Gini_slope_pp'])
        assert r['category']==reference_point['category']
    major_codes=[r['country'] for r in rank[:15]]
    assert manifest['scatter']['major_country_codes']==major_codes
    bands=manifest['scatter']['annotation_x_band_edges']
    assert all(.09<hi-lo<=.351 for lo,hi in zip(bands,bands[1:]))
    representatives=[]
    for lo,hi in zip(bands,bands[1:]):
        candidates=[r for r in trends if lo<=float(r['normalized_equivalent_cities_slope_pp'])<hi
            and float(r['Gini_slope_pp'])>0]
        if candidates:
            representatives.append(min(candidates,key=lambda r:int(audit_lookup[r['country']]['volume_rank']))['country'])
    assert representatives==manifest['scatter']['interval_representatives']
    expected_label_codes=set(major_codes)|set(representatives)|{'CM','MA'}|set(selected)
    assert len(labels)==len(expected_label_codes) and {r['country'] for r in labels}==expected_label_codes
    for label in labels:
        point=next(r for r in trends if r['country']==label['country'])
        assert float(label['point_x'])==float(point['normalized_equivalent_cities_slope_pp'])
        assert float(label['point_y'])==float(point['Gini_slope_pp'])
        assert float(label['label_x'])*float(label['point_x'])>0
        assert float(label['label_y'])*float(label['point_y'])>0
        assert (label['major_country']=='True')==(label['country'] in major_codes)
        assert (label['interval_representative']=='True')==(label['country'] in representatives)
        assert (label['country'] in zoom_codes)==(label['display']=='inset')
        assert (label['leader']=='True')==(label['country'] in manifest['scatter']['leader_countries'])
    q3_labels=[r for r in labels if float(r['point_x'])<0 and float(r['point_y'])<0]
    assert {r['country'] for r in q3_labels}=={'CN','JP','KR','RU','TR'}
    assert len(metrics)==112 and len(plotted)==224
    groups={}
    for r in margins:
        groups.setdefault((r['country'],int(r['year'])),[]).append(float(r['total_city_strength']))
    reference={}
    with (ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/domestic_city_margins.csv').open(
            encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['country'] in selected:
                key=r['country'],int(r['year']),r['city_id']
                reference[key]=reference.get(key,0.)+float(r['flow'])
    assert {(r['country'],int(r['year']),r['city_id']):float(r['total_city_strength']) for r in margins}==reference
    metric_lookup={}
    for m in metrics:
        key=m['country'],int(m['year'])
        v=np.array(groups[key]);n=len(v);p=v/sum(v)
        x=np.arange(n+1)/n;y=np.r_[0,np.cumsum(np.sort(p))]
        assert sum(v)==float(m['total_city_strength'])==2*float(m['flow_events']) and n==int(m['N'])
        assert abs(np.dot(p,p)-float(m['HHI']))<1e-12
        assert abs(1/(n*np.dot(p,p))-float(m['normalized_equivalent_cities']))<1e-12
        assert abs(1-2*np.trapezoid(y,x)-float(m['Gini']))<1e-12
        metric_lookup[key]=m
    for p in plotted:
        assert float(p['value'])==float(metric_lookup[p['country'],int(p['year'])][p['metric']])
    axes={p['id']:p['bbox_pt'] for p in alignment['layout']['panels']}
    line_checks=[]
    with pymupdf.open(OUT/'Fig4.pdf') as doc:
        page=doc[0];paths=page.get_drawings()
        assert abs(page.rect.width-180*72/25.4)<1e-4 and abs(page.rect.height-100*72/25.4)<1e-4
        font_names={f[3].split('+')[-1] for f in page.get_fonts()}
        assert {'Helvetica','Helvetica-Bold'}<=font_names
        assert font_names<={'Helvetica','Helvetica-Bold','ArialMT','DejaVuSans','DejaVuSans-Oblique'}
        for record in manifest['axis_records']:
            panel=record['panel'];cc=record['country'];x0,y0,x1,y1=axes[panel]
            assert abs((x1-x0)-(y1-y0))<1e-8
            for metric in ['normalized_equivalent_cities','Gini']:
                lo,hi=record[metric+'_limits']
                vals=[float(r[metric]) for r in metrics if r['country']==cc]
                assert lo<=min(vals)<=max(vals)<=hi
                color=manifest['palette'][metric]
                rgb=tuple(int(color[i:i+2],16)/255 for i in [1,3,5])
                candidates=[d for d in paths if d['type']=='s' and d.get('color') is not None
                    and np.allclose(d['color'],rgb,atol=1e-5) and len(d['items'])==27
                    and all(item[0]=='l' for item in d['items'])
                    and x0-.1<=d['rect'].x0<=d['rect'].x1<=x1+.1
                    and y0-.1<=page.rect.height-d['rect'].y1<=page.rect.height-d['rect'].y0<=y1+.1]
                assert len(candidates)==1,(panel,metric,len(candidates))
                rs=sorted([r for r in plotted if r['country']==cc and r['metric']==metric],key=lambda r:int(r['year']))
                assert [int(r['year']) for r in rs]==list(range(1998,2026))
                xp=x0+(np.array([int(r['year']) for r in rs])-1996)/31*(x1-x0)
                yp=page.rect.height-(y0+(np.array([float(r['value']) for r in rs])-lo)/(hi-lo)*(y1-y0))
                d=candidates[0]
                coordinates=np.array([tuple(d['items'][0][1])]+[tuple(item[2]) for item in d['items']])
                error=float(np.max(abs(coordinates-np.column_stack([xp,yp]))))
                assert error<.002,(panel,metric,error)
                assert d['dashes']=='[] 0'
                line_checks.append(dict(panel=panel,country=cc,metric=metric,
                    observations=28,solid=True,max_coordinate_error_pt=error))
        traces=page.get_texttrace()
        text=lambda r:''.join(chr(c[0]) for c in r['chars'])
        left_titles=[r for r in traces if text(r)=='R' and abs(r['dir'][1])>.9]
        right_titles=[r for r in traces if text(r)=='Gini' and abs(r['dir'][1])>.9]
        assert len(left_titles)==2 and len(right_titles)==2
        assert all(np.allclose(r['color'],[0,0,0]) for r in left_titles+right_titles)
        assert all(axes['a'][2]<(r['bbox'][0]+r['bbox'][2])/2<axes['b'][0] for r in left_titles)
        assert all((r['bbox'][0]+r['bbox'][2])/2>axes['c'][2] for r in right_titles)
        metric_legends=[r for r in traces if text(r) in ['R','Gini'] and abs(r['dir'][0])>.9
                        and r['bbox'][3]<page.rect.height-axes['b'][3]-10]
        assert len(metric_legends)==2
        assert all(text(r)!='HHI' for r in traces)
        assert all(r['bbox'][3]<page.rect.height-axes['b'][3]-10 for r in metric_legends)
        strings=[''.join(chr(c[0]) for c in r['chars']) for r in traces]
        assert all(strings.count('Q'+str(q))==1 for q in range(1,5))
        assert strings.count('Share growth')==1
        assert all(strings.count(name)==1 for name in ['Q1 United States','Q2 Poland','Q3 Brazil','Q4 India'])
        assert not {'Uganda','Bangladesh','Iran','Morocco'}&set(strings)
        assert 'Domestic urban mobility, 1998–2025' not in strings
        assert '63 of 76 countries' not in strings and 'Relative concentration' not in strings
        for label in labels:
            matches=[r for r,s in zip(traces,strings) if s==label['country']]
            assert len(matches)==1
            assert all(np.allclose(r['color'],[0,0,0]) for r in matches)
            scope='a_zoom' if label['display']=='inset' else 'a'
            ax0,ay0,ax1,ay1=axes[scope]
            limits=manifest['zoom'] if scope=='a_zoom' else manifest['scatter']
            lx0,lx1=limits['xlim'];ly0,ly1=limits['ylim']
            zero_x=ax0-lx0/(lx1-lx0)*(ax1-ax0)
            zero_y=page.rect.height-(ay0-ly0/(ly1-ly0)*(ay1-ay0))
            bx0,by0,bx1,by1=matches[0]['bbox']
            assert ax0<bx0<bx1<ax1
            assert page.rect.height-ay1<by0<by1<page.rect.height-ay0
            assert (bx1<zero_x if float(label['point_x'])<0 else bx0>zero_x)
            assert (by1<zero_y if float(label['point_y'])>0 else by0>zero_y)
        x0,y0,x1,y1=axes['a']
        assert abs((x1-x0)-(y1-y0))<1e-8
        assert abs(y0-axes['d'][1])<1e-8 and abs(y1-axes['b'][3])<1e-8
        scatter_candidates=[p for p in paths if p['type']=='fs' and p.get('fill') is not None
            and len(p['items'])==8 and abs(p['rect'].width-np.sqrt(22))<.005
            and abs(p['rect'].height-np.sqrt(22))<.005
            and x0<=p['rect'].x0<=p['rect'].x1<=x1
            and y0<=page.rect.height-p['rect'].y1<=page.rect.height-p['rect'].y0<=y1]
        assert len(scatter_candidates)==76,len(scatter_candidates)
        marker_errors=[]
        for r in trends:
            x=float(r['normalized_equivalent_cities_slope_pp']);y=float(r['Gini_slope_pp'])
            expected=np.array([x0+(x+2.6)/3.2*(x1-x0),page.rect.height-(y0+(y+.35)/2.4*(y1-y0))])
            assert np.max(abs(expected-[float(r['pdf_x_pt']),float(r['pdf_y_pt'])]))<1e-4
            color=manifest['scatter']['quartile_colors']['Q'+str(quartiles[r['country']])]
            rgb=tuple(int(color[i:i+2],16)/255 for i in [1,3,5])
            matches=[p for p in scatter_candidates if np.allclose(p['fill'],rgb,atol=1e-5)]
            distances=[max(abs(np.array([(p['rect'].x0+p['rect'].x1)/2,
                (p['rect'].y0+p['rect'].y1)/2])-expected)) for p in matches]
            err=min(distances);assert err<.002,(r['country'],err)
            matching_marker=matches[int(np.argmin(distances))]
            assert np.allclose(matching_marker['color'],[0,0,0] if r['country'] in selected else [1,1,1],atol=1e-5)
            marker_errors.append(float(err))
        ix0,iy0,ix1,iy1=axes['a_zoom']
        assert x0<ix0<ix1<(x0+x1)/2+.06*(x1-x0) and y0<iy0<iy1<y1
        for r in trends:
            px=float(r['pdf_x_pt']);py=page.rect.height-float(r['pdf_y_pt'])
            assert not (ix0-2.4<px<ix1+2.4 and iy0-2.4<py<iy1+2.4),r['country']
        zoom_candidates=[p for p in paths if p['type']=='fs' and p.get('fill') is not None
            and len(p['items'])==8 and abs(p['rect'].width-np.sqrt(13))<.005
            and abs(p['rect'].height-np.sqrt(13))<.005
            and ix0<=p['rect'].x0<=p['rect'].x1<=ix1
            and iy0<=page.rect.height-p['rect'].y1<=page.rect.height-p['rect'].y0<=iy1]
        assert len(zoom_candidates)==len(zoom_points)
        zoom_errors=[]
        for r in zoom_points:
            expected=np.array([ix0+(float(r['point_x'])-zx0)/(zx1-zx0)*(ix1-ix0),
                page.rect.height-(iy0+(float(r['point_y'])-zy0)/(zy1-zy0)*(iy1-iy0))])
            assert np.max(abs(expected-[float(r['pdf_x_pt']),float(r['pdf_y_pt'])]))<1e-4
            color=manifest['scatter']['quartile_colors']['Q'+str(quartiles[r['country']])]
            rgb=tuple(int(color[i:i+2],16)/255 for i in [1,3,5])
            matches=[p for p in zoom_candidates if np.allclose(p['fill'],rgb,atol=1e-5)]
            err=min(max(abs(np.array([(p['rect'].x0+p['rect'].x1)/2,
                (p['rect'].y0+p['rect'].y1)/2])-expected)) for p in matches)
            assert err<.002,(r['country'],err)
            zoom_errors.append(float(err))
        inset_pdf_footprint=pymupdf.Rect(ix0,page.rect.height-iy1,ix1,page.rect.height-iy0)
        tick_texts=[r for r in traces if abs(r['size']-manifest['formatting']['inset_axis_text_pt'])<.001]
        assert len(tick_texts)==7
        inset_country_texts=[r for r,s in zip(traces,strings) if s in manifest['zoom']['labelled_countries']]
        for run in tick_texts+inset_country_texts:
            inset_pdf_footprint|=pymupdf.Rect(run['bbox'])
        clearance=[]
        for r in trends:
            px=float(r['pdf_x_pt']);py=float(r['pdf_y_pt'])
            dx=max(inset_pdf_footprint.x0-px,0,px-inset_pdf_footprint.x1)
            dy=max(inset_pdf_footprint.y0-py,0,py-inset_pdf_footprint.y1)
            clearance.append(float(np.hypot(dx,dy)-np.sqrt(22)/2-.325))
        # Match the final 180-mm typography contract used by plot_fig4.py.
        assert min(clearance)>1.5,min(clearance)
        roi_expected=np.array([x0+(zx0+2.6)/3.2*(x1-x0),
            page.rect.height-(y0+(zy1+.35)/2.4*(y1-y0)),
            x0+(zx1+2.6)/3.2*(x1-x0),page.rect.height-(y0+(zy0+.35)/2.4*(y1-y0))])
        assert any(np.max(abs(np.array(tuple(p['rect']))-roi_expected))<.002 for p in paths)
        label_colors=[tuple(int(c[i:i+2],16)/255 for i in [1,3,5]) for c in ['#58616A','#7B838C']]
        leaders=[p for p in paths if p['type']=='s' and p.get('color') is not None
            and any(np.allclose(p['color'],color,atol=1e-5) for color in label_colors)]
        assert len(leaders)==len(manifest['scatter']['leader_countries'])
        for i,first_leader in enumerate(leaders):
            first=np.array([tuple(first_leader['items'][0][1]),tuple(first_leader['items'][-1][2])])
            for other_leader in leaders[i+1:]:
                other=np.array([tuple(other_leader['items'][0][1]),tuple(other_leader['items'][-1][2])])
                delta=first[1]-first[0];segment=other[1]-other[0];denom=np.linalg.det(np.column_stack([delta,-segment]))
                if abs(denom)>1e-10:
                    fractions=np.linalg.solve(np.column_stack([delta,-segment]),other[0]-first[0])
                    assert not np.all((fractions>0)&(fractions<1)), 'Crossing country-label leaders'
    report=dict(status='PASS',input_sha256=manifest['input_sha256'],
        final_pdf_sha256=hashlib.sha256((OUT/'Fig4.pdf').read_bytes()).hexdigest(),
        selected_countries=selected,selection=manifest['selection_rule'],
        one_case_per_Fig5_quartile=True,case_groups=[1,2,3,4],case_volume_thresholds_verified=True,
        case_selection_verified=case_rows,seven_year_case_summaries_verified=len(summaries),
        sample_countries_audited=76,both_HHI_and_Gini_trends_positive=len(first),
        all_country_trend_values_checked=76*3,country_year_metrics_verified=112,
        combined_city_strength_margins_match_cleaned_data=True,auxiliary_HHI_values_verified=112,
        normalized_equivalent_city_values_verified=112,Gini_values_verified=112,
        total_curve_values_verified=224,rendered_curve_geometry_checks=line_checks,
        scatter_observations_verified=76,scatter_category_counts=counts,
        colour_encoding='Fig5 international-share growth quartiles',
        exact_Fig5_membership_verified=True,quartile_sample_sizes=[19]*4,
        quartile_concentration_counts=[15,17,13,18],
        all_main_and_inset_point_colours_verified=True,
        max_rendered_scatter_coordinate_error_pt=max(marker_errors),
        final_dimensions_mm=[180,100],square_plot_areas=True,independent_country_axis_ranges=True,
        normalized_equivalent_city_titles_only_at_far_left=True,Gini_titles_only_at_far_right=True,
        case_axes_and_metric_labels_black=True,shared_case_legend=True,
        scatter_country_labels=[r['country'] for r in labels],scatter_leaders_verified=len(leaders),
        directly_placed_country_labels=len(labels)-len(leaders),
        country_label_leaders_do_not_cross=True,
        all_top15_countries_labelled=True,interval_representatives_verified=representatives,
        labels_kept_in_point_quadrants=True,full_pdf_text_boxes_within_correct_quadrants=True,
        zoom_points_verified=len(zoom_points),zoom_country_labels=manifest['zoom']['labelled_countries'],
        max_rendered_zoom_coordinate_error_pt=max(zoom_errors),
        dense_region_labels_removed_from_main=True,inset_covers_no_main_points=True,
        inset_ticks_and_labels_cover_no_main_points=True,
        minimum_main_marker_edge_clearance_from_inset_footprint_pt=min(clearance),
        rendered_inset_footprint_bbox_pdf_pt=tuple(inset_pdf_footprint),
        zoom_region_rectangle_geometry_verified=True,zoom_markers_preserve_source_values=True,
        removed_subtitle_and_standalone_count_annotations=True,
        main_panels=5,secondary_axes=4,insets=1,
        alignment='PASS',minimum_glyph_pt=fonts['minimum_found_pt'],
        collision_failures=0,collision_warnings=collision['summary']['warn'])
    (QA/'data_and_visual_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='rendered_curve_geometry_checks'},ensure_ascii=False))


if __name__=='__main__':
    main()
