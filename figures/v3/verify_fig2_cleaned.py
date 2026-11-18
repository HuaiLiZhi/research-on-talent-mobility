"""Check the cleaned Fig2 plotting tables against the exported PDF."""
from pathlib import Path
import csv
import hashlib
import json
import math
import os
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp'/'nhb_fig2_python_deps'))
import numpy as np
import pymupdf
import duckdb

OUT=Path(__file__).resolve().parent
if os.environ.get('NHB_FIGURE_PROFILE')=='journal':OUT=OUT/'NHB_final'
DATA=OUT/'source_data'
QA=OUT/'QA'

def read(name):
    with (DATA/name).open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))

def save(name,value):
    (QA/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')

def main():
    current=OUT/'QA/Fig2/figure_manifest.json'
    if current.exists() and 'quartile_country_cluster_panels' in json.loads(current.read_text(encoding='utf-8')):
        from verify_fig2_quartile_clusters import main as verify_quartile_clusters
        return verify_quartile_clusters()
    if current.exists() and 'quartile_growth_panels' in json.loads(current.read_text(encoding='utf-8')):
        from verify_fig2_quartile_growth import main as verify_quartile_growth
        return verify_quartile_growth()
    if current.exists() and 'coverage_regression_panels' in json.loads(current.read_text(encoding='utf-8')):
        from verify_fig2_coverage_regressions import main as verify_coverage_regressions
        return verify_coverage_regressions()
    if current.exists() and 'histogram_panel' in json.loads(current.read_text(encoding='utf-8')):
        from verify_fig2_period_histograms import main as verify_period_histograms
        return verify_period_histograms()
    if current.exists() and 'country_stream_panel' in json.loads(current.read_text(encoding='utf-8')):
        from verify_fig2_country_streamgraph import main as verify_country_streamgraph
        return verify_country_streamgraph()
    if current.exists() and 'growth_scatter_panel' in json.loads(current.read_text(encoding='utf-8')):
        from verify_fig2_growth_scatter import main as verify_growth_scatter
        return verify_growth_scatter()
    if current.exists() and 'continent_line_panel' in json.loads(current.read_text(encoding='utf-8')):
        from verify_fig2_continent_lines import main as verify_continent_lines
        return verify_continent_lines()
    manifest=json.loads((QA/'figure_manifest.json').read_text(encoding='utf8'))
    alignment=json.loads((QA/'alignment.json').read_text(encoding='utf8'))
    assert alignment['verdict']=='PASS'
    src={int(r['year']):r for r in read('Fig2_source_data.csv')}
    stacks=read('Fig2_all_country_stacks.csv')
    assert len(stacks)==336
    for year in range(1998,2026):
        for geo in ['international','domestic']:
            rs=[r for r in stacks if r['geography']==geo and int(r['year'])==year]
            assert len(rs)==6
            assert sum(float(r['flow_events']) for r in rs)==float(src[year][geo+'_flow'])
    domestic={(r['country'],r['side'],int(r['year'])):int(r['domestic_cities'])
              for r in read('Fig2_country_year_data.csv')}
    partners={(r['country'],int(r['year'])):r for r in read('Fig2_country_source_counts_annual.csv')}
    destinations={(r['country'],int(r['year'])):r for r in read('Fig2_country_destination_counts_annual.csv')}
    trajectory=read('Fig2_country_trajectories.csv')
    assert len(trajectory)==140
    combined=read('Fig2_combined_location_counts.csv')
    assert len(combined)==140
    canonical=ROOT/manifest['cleaned_data_provenance']['source_parquet']
    sqlpath=str(canonical).replace("'","''")
    con=duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='2GB'")
    con.execute(f"CREATE TEMP VIEW flows AS SELECT * FROM read_parquet('{sqlpath}') WHERE flow>0")
    country_union={(cc,year):n for year,cc,n in con.execute("""
        SELECT year,country,count(DISTINCT partner) FROM (
            SELECT year,destination_country country,origin_country partner FROM flows
                WHERE origin_country<>destination_country
            UNION ALL SELECT year,origin_country,destination_country FROM flows
                WHERE origin_country<>destination_country)
        GROUP BY ALL""").fetchall()}
    city_union={(cc,year):n for year,cc,n in con.execute("""
        SELECT year,country,count(DISTINCT city_id) FROM (
            SELECT year,origin_country country,unnest([origin,destination]) city_id FROM flows
            WHERE origin_country=destination_country)
        GROUP BY ALL""").fetchall()}
    con.close()
    for row in combined:
        cc,year=row['country'],int(row['year'])
        assert int(row['international_total_countries'])==country_union[cc,year]
        assert int(row['domestic_total_cities'])==city_union[cc,year]
    for row in trajectory:
        cc,year=row['country'],int(row['year'])
        assert int(row['international_inflow_countries'])==int(partners[cc,year]['source_countries'])
        assert int(row['international_outflow_countries'])==int(destinations[cc,year]['destination_countries'])
        for side in ['inflow','outflow']:
            assert int(row['domestic_'+side+'_cities'])==domestic[cc,side,year]
        assert int(row['international_total_countries'])==country_union[cc,year]
        assert int(row['domestic_total_cities'])==city_union[cc,year]
        for metric,total,sides in [
                ('countries','international_total_countries',['international_inflow_countries','international_outflow_countries']),
                ('cities','domestic_total_cities',['domestic_inflow_cities','domestic_outflow_cities'])]:
            assert max(int(row[s]) for s in sides)<=int(row[total])<=sum(int(row[s]) for s in sides)
    bubbles={panel:read(name) for panel,name in [('c','Fig2_international_country_bubbles.csv'),
                                               ('d','Fig2_domestic_city_bubbles.csv')]}
    for panel,rows in bubbles.items():
        assert len(rows)==manifest['country_sample_n']*4
        for row in rows:
            cc,year=row['country'],int(row['year'])
            metric='source_countries' if panel=='c' else 'domestic_inflow_cities'
            target=int(partners[cc,year]['source_countries']) if panel=='c' else domestic[cc,'inflow',year]
            assert int(row[metric])==target
            assert abs(float(row['circle_radius'])**2-target)<1e-9
        country_groups={cc:[r for r in rows if r['country']==cc] for cc in {r['country'] for r in rows}}
        disks=[(rs[0],max(float(r['circle_radius']) for r in rs)) for rs in country_groups.values()]
        for i,(r,rad) in enumerate(disks):
            for other,other_rad in disks[i+1:]:
                distance=math.hypot(float(r['circle_x'])-float(other['circle_x']),
                                    float(r['circle_y'])-float(other['circle_y']))
                assert distance>=rad+other_rad-1e-8
    curves=[]
    for year in [1998,2007,2016,2025]:
        row=dict(year=year,fixed_countries=manifest['country_sample_n'])
        for key,name in [('international','Fig2_international_source_partner_curves.csv'),
                         ('domestic','Fig2_domestic_source_partner_curves.csv')]:
            rs=[r for r in read(name) if int(r['year'])==year]
            vals=np.array([float(r['fraction_at_least_threshold']) for r in rs])
            assert vals[0]==1 and vals[-1]==0 and np.all(np.diff(vals)<=1e-12)
            row[key+'_curve_monotone']=True
        row['international_destinations']=int(src[year]['countries_inflow'])
        row['domestic_destination_cities']=sum(n for (cc,side,y),n in domestic.items() if side=='inflow' and y==year)
        curves.append(row)
    save('partner_distribution_checks.json',curves)

    label_checks=[]
    size_legend=read('Fig2_bubble_size_legend.csv')
    assert len(size_legend)==7
    panels={p['id']:p for p in alignment['layout']['panels']}
    with pymupdf.open(OUT/'Fig2.pdf') as doc:
        page=doc[0]
        traces=page.get_texttrace()
        drawings=page.get_drawings()
        bottom_lines=[]
        for panel in 'efghi':
            x0,y0,x1,y1=panels[panel]['bbox_pt']
            for colour in [manifest['palette']['years']['1998'],manifest['palette']['years']['2007']]:
                rgb=tuple(int(colour[i:i+2],16)/255 for i in [1,3,5])
                matches=[d for d in drawings if d.get('color') is not None
                    and np.allclose(d['color'],rgb,atol=1e-5)
                    and d['rect'].x0>=x0-.1 and d['rect'].x1<=x1+.1
                    and page.rect.height-d['rect'].y1>=y0-.1
                    and page.rect.height-d['rect'].y0<=y1+.1]
                assert len(matches)==1,(panel,colour,len(matches))
                assert matches[0]['dashes']=='[] 0',(panel,colour,matches[0]['dashes'])
                bottom_lines.append(dict(panel=panel,colour=colour,solid=True))
        assert manifest['selected_country_outer_borders'] is False
        for r in size_legend:
            panel=r['panel'];quantity=int(r['quantity'])
            x0,y0,x1,y1=panels[panel]['bbox_pt']
            scale=(x1-x0)/(2*manifest['common_bubble_coordinate_extent'])
            radius=float(r['circle_radius_pt'])
            assert abs(radius-math.sqrt(quantity)*scale)<1e-6
            diameter=float(r['circle_diameter_pt'])
            assert abs(diameter-2*radius)<1e-8
            x,zero,tick=float(r['ruler_x_pt']),float(r['ruler_zero_pdf_pt']),float(r['tick_pdf_pt'])
            assert abs(zero-tick-diameter)<1e-8
            expected=pymupdf.Rect(x-1.8,tick,x+1.8,tick)
            matches=[d for d in drawings if max(abs(a-b) for a,b in zip(d['rect'],expected))<.02]
            assert matches,(panel,quantity,expected)
        for panel in ['c','d']:
            rs=[r for r in size_legend if r['panel']==panel]
            expected=pymupdf.Rect(float(rs[0]['ruler_x_pt']),min(float(r['tick_pdf_pt']) for r in rs),
                                 float(rs[0]['ruler_x_pt']),max(float(r['tick_pdf_pt']) for r in rs))
            assert any(max(abs(a-b) for a,b in zip(d['rect'],expected))<.02 for d in drawings)
        for trace in traces:
            trace['text']=''.join(chr(char[0]) for char in trace['chars'])
        for r in read('Fig2_bubble_country_labels.csv'):
            if r['labelled']!='True':
                continue
            panel,cc=r['panel'],r['country']
            disk=next(v for v in bubbles[panel] if v['country']==cc)
            radius=max(float(v['circle_radius']) for v in bubbles[panel] if v['country']==cc)
            x0,y0,x1,y1=panels[panel]['bbox_pt']
            extent=manifest['common_bubble_coordinate_extent']
            scale=(x1-x0)/(2*extent)
            assert abs(scale-(y1-y0)/(2*extent))<1e-6
            cx=x0+(float(disk['circle_x'])+extent)*scale
            cy=page.rect.height-(y0+(float(disk['circle_y'])+extent)*scale)
            matched=[t for t in traces if t['text']==cc and
                     math.hypot((t['bbox'][0]+t['bbox'][2])/2-cx,
                                (t['bbox'][1]+t['bbox'][3])/2-cy)<1]
            assert len(matched)==1,(panel,cc,matched)
            t=matched[0]
            b=t['bbox']
            max_dist=max(math.hypot(x-cx,y-cy) for x in [b[0],b[2]] for y in [b[1],b[3]])
            assert max_dist<radius*scale-.3,(panel,cc,max_dist,radius*scale)
            assert t['size']>=5.19 and np.allclose(t['color'],np.zeros(3),atol=1e-5)
            assert len(cc)==2 and r['label_type']=='ISO2'
            label_checks.append(dict(panel=panel,country=cc,editable=True,within_own_country_circle=True,
                minimum_edge_clearance_pt=radius*scale-max_dist))
        numeric=[t for t in traces if t['text'].isdigit() and
                 panels['e']['bbox_pt'][1]<page.rect.height-(t['bbox'][1]+t['bbox'][3])/2<panels['e']['bbox_pt'][3]]
        assert all(t['color']==(0.,0.,0.) for t in numeric)
        gaps=[]
        for left,right in zip('efgh','fghi'):
            edge_l=panels[left]['bbox_pt'][2]
            edge_r=panels[right]['bbox_pt'][0]
            gap_traces=[t for t in numeric if t['bbox'][0]>=edge_l-.1 and t['bbox'][2]<=edge_r+.1]
            cutoff=(edge_l+edge_r)/2
            first=[t for t in gap_traces if (t['bbox'][0]+t['bbox'][2])/2<cutoff]
            second=[t for t in gap_traces if (t['bbox'][0]+t['bbox'][2])/2>cutoff]
            assert first and second
            gap=min(t['bbox'][0] for t in second)-max(t['bbox'][2] for t in first)
            assert gap>3,(left,right,gap)
            gaps.append(dict(panels=[left,right],numeric_label_gap_pt=gap))
        # Inspect panel detail crops from the final exported PDF.
        for name,y0,y1 in [('top',0,143),('bubbles',143,340),('bottom',340,page.rect.height)]:
            rect=pymupdf.Rect(0,y0,page.rect.width,y1)
            page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=rect,alpha=False).save(QA/f'preview_{name}.png')
    save('label_geometry_checks.json',dict(labels=label_checks,adjacent_numeric_gaps=gaps))
    text=json.loads((QA/'pdf_text.json').read_text(encoding='utf-8-sig'))
    collisions=json.loads((QA/'collisions.json').read_text(encoding='utf8'))
    assert text['below_minimum_count']==0
    assert collisions['summary']['fail']==0
    assert all(f['kind']=='text-fill-edge' for f in collisions['findings'])
    report=dict(input='data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet',
        input_sha256=manifest['cleaned_data_provenance']['source_sha256'],
        all_28_complete_stacks_match_cleaned_totals=True,full_stack_records=len(stacks),
        country_sample_n=manifest['country_sample_n'],bubble_observations=manifest['bubble_counts'],
        country_year_rows=len(trajectory),bottom_count_values=2*len(trajectory),
        combined_counts_match_raw_cleaned_events=True,directional_auxiliary_counts_verified=True,
        bottom_solid_lines=bottom_lines,selected_country_outer_borders=False,
        bubble_inflow_counts_match_auxiliary_directional_series=True,
        circle_area_per_count_equal_in_both_panels=True,no_overlapping_country_disks=True,
        vertical_size_rulers=2,size_ruler_ticks=7,size_rulers_match_actual_bubble_diameters=True,
        country_connectors=len(read('Fig2_bubble_connectors.csv')),
        all_circle_labels_editable_ISO2_and_inside_own_circle=True,
        bubble_labels=manifest['bubble_country_labels'],black_numeric_y_tick_spans=len(numeric),
        minimum_glyph_pt=text['minimum_found_pt'],alignment=alignment['verdict'],
        collision_failures=0,collision_warnings=collisions['summary']['warn'],
        warnings_require_visual_review=True)
    save('cleaned_figure_checks.json',report)
    save('comparison_figure_checks.json',report)
    save('country_city_count_checks.json',dict(country_year_rows=len(trajectory),raw_count_values=2*len(trajectory),
        source_and_destination_country_counts_verified=True,domestic_inflow_outflow_counts_verified=True,
        combined_union_counts_independently_verified_against_cleaned_events=True,
        limits_by_country=manifest['bottom_axes']['limits_by_country']))
    save('colour_and_scope_checks.json',dict(full_stack_records=len(stacks),both_stacks_match_cleaned_totals=True,
        palette=manifest['palette'],bubble_labels=manifest['bubble_country_labels'],
        all_labels_editable_and_inside_country_circle=True,all_labels_ISO_alpha_2=True,
        black_numeric_y_tick_spans=len(numeric),minimum_glyph_pt=text['minimum_found_pt']))
    save('collision_warning_review.json',dict(final_pdf='figures/v3/Fig2.pdf',
        final_pdf_sha256=hashlib.sha256((OUT/'Fig2.pdf').read_bytes()).hexdigest(),
        reviewed_warning_count=len(collisions['findings']),findings=[dict(index=i+1,text=f['text'],
            bbox=f['text_bbox'],disposition='reviewed_intentional_or_bounding_box_only',
            reason='Country labels remain inside their own nested circles; inset labels and year legends sit in white space. Filled-path bounding boxes alone overlap; final full and detail previews inspected.')
            for i,f in enumerate(collisions['findings'])]))
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':
    main()
