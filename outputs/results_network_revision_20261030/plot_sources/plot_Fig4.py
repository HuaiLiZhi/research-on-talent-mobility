"""Manuscript Fig5: all-city and initial-city Gini across countries and years.

Figure contract: compare all-city and initial-city Gini slopes in the complete
fixed 76-country sample, then illustrate annual divergence in four countries.
One case per T group maximizes mean Gini separation after volume/coverage gates;
selection is illustrative, while prevalence uses the entire 76-country pool.
A square hero spans two rows; four square cases each use one common Gini axis.
Initial cities are recorded in 1998 and active in the displayed year; their
full domestic margins are retained. All 28 annual observations are plotted.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from io import BytesIO
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'figures/v3'), str(Path(__file__).resolve().parents[3] / 'scripts/plots/paper_figures/qa')]

from figure_style import (
    ANNUAL_LINEWIDTH_PT, ANNUAL_MARKER_EDGE_PT, ANNUAL_MARKER_PT,
    AXIS_LINEWIDTH_PT, COUNTRY_POINT_ALPHA, COUNTRY_POINT_EDGE_PT, COUNTRY_POINT_PT2,
    PROFILE, REFERENCE_COLOUR, REFERENCE_LINESTYLE, REFERENCE_LINEWIDTH_PT,
    TICK_LINEWIDTH_PT, WIDTH_PT, apply_axes_typography, font_size, specification,
)

OUT=Path(__file__).resolve().parents[1]/'artwork'
DATA=OUT/'source_data'
QA=OUT/'QA'/'Fig4'
CLEAN=ROOT/'data'/'processed'/'mobility_city_harmonized_20261020'
CANONICAL=CLEAN/'analysis'/'flow_top100.parquet'

import duckdb
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle,ConnectionPatch
from matplotlib.ticker import MaxNLocator,FormatStrFormatter
from matplotlib.transforms import Bbox
from matplotlib.path import Path as PlotPath
import pymupdf
from audit_panel_alignment import require_matplotlib_panel_alignment

from figure_palette import BLUE, RED
INK='#17212A'
NAMES={'CA':'Canada','PL':'Poland','BR':'Brazil','IN':'India'}
CASE_COUNTRIES=['CA','PL','BR','IN']
CASE_ROLES={'CA':'T1: rising all-city Gini with little full-period change among initial cities',
    'PL':'Rising all-city Gini and declining initial-city Gini',
    'BR':'Both Gini series decline, with a larger decline among initial cities',
    'IN':'Near-zero all-city slope and declining initial-city Gini'}
CASE_MIN_TOTAL=100000;CASE_MIN_ANNUAL=1000;CASE_MIN_CITIES=30
YEARS=list(range(1998,2026))
MARKER_INDICES=[0,5,10,15,20,25,27]
MAJOR_COUNTRY_LABEL_COUNT=10
PERIPHERAL_LABEL_CODES=['ID','IR','PK','BD','VN','GH','UG','PH']
LABEL_BANDS=[-2.5,-2.15,-1.8,-1.45,-1.15,-.8,-.45,-.1,0]
INITIAL_SOURCE=ROOT/'outputs/paper_final/source_data/results_revision_20261111/entry_components_annual.csv'


def write_csv(name,rows):
    with (DATA/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_data():
    con=duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='2GB'")
    path=str(CANONICAL).replace("'","''")
    con.execute(f"""CREATE TEMP VIEW domestic AS SELECT year,origin_country country,
        origin,destination,flow FROM read_parquet('{path}')
        WHERE origin_country=destination_country AND flow>0""")
    pool=json.loads((OUT/'QA'/'figure_manifest.json').read_text(encoding='utf8'))[
        'cleaned_data_provenance']['fixed_country_codes']
    assert len(pool)==76
    codes=','.join("'"+cc+"'" for cc in pool)
    totals={(cc,int(y)):float(v) for cc,y,v in con.execute(f"""
        SELECT country,year,sum(flow) FROM domestic WHERE country IN ({codes})
        GROUP BY ALL""").fetchall()}
    margins=[dict(year=int(y),country=cc,city_id=city,total_city_strength=float(v))
        for y,cc,city,v in con.execute(f"""
        SELECT year,country,city,sum(flow) FROM (
            SELECT year,country,destination city,flow FROM domestic WHERE country IN ({codes})
            UNION ALL SELECT year,country,origin city,flow FROM domestic WHERE country IN ({codes}))
        GROUP BY ALL ORDER BY country,year,city""").fetchall()]
    con.close()
    supplied={}
    with (CLEAN/'analysis'/'domestic_city_margins.csv').open(encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            if r['country'] in pool:
                key=r['country'],int(r['year']),r['city_id']
                supplied[key]=supplied.get(key,0.)+float(r['flow'])
    assert {(r['country'],r['year'],r['city_id']):r['total_city_strength'] for r in margins}==supplied
    initial_ids={cc:set() for cc in pool}
    for row in margins:
        if row['year']==1998:initial_ids[row['country']].add(row['city_id'])
    groups={};initial_groups={};all_metrics=[]
    for row in margins:
        groups.setdefault((row['country'],row['year']),[]).append(row['total_city_strength'])
        if row['city_id'] in initial_ids[row['country']]:
            initial_groups.setdefault((row['country'],row['year']),[]).append(row['total_city_strength'])
    for cc in pool:
        for year in YEARS:
            values=np.array(groups[cc,year]);n=len(values)
            total=float(sum(values));p=values/total
            assert n>=2 and np.all(p>0) and np.isclose(sum(p),1)
            assert total==2*totals[cc,year]
            hhi=float(sum(p*p))
            gini=float(2*np.dot(np.arange(1,n+1),np.sort(p))/n-(n+1)/n)
            initial_values=np.array(initial_groups[cc,year]);initial_n=len(initial_values)
            initial_p=initial_values/initial_values.sum()
            assert initial_n>=2 and np.all(initial_p>0) and np.isclose(initial_p.sum(),1)
            initial_gini=float(2*np.dot(np.arange(1,initial_n+1),np.sort(initial_p))/initial_n-(initial_n+1)/initial_n)
            if year==1998:assert np.isclose(gini,initial_gini,atol=1e-12)
            all_metrics.append(dict(country=cc,year=year,N=n,flow_events=totals[cc,year],
                total_city_strength=total,HHI=hhi,Gini=gini,normalized_equivalent_cities=1/(n*hhi),
                Gini_Initial=initial_gini,N_Initial=initial_n))
    with INITIAL_SOURCE.open(encoding='utf-8-sig',newline='') as f:
        archived={(r['country'],int(r['year'])):r for r in csv.DictReader(f)}
    assert set(archived)=={(r['country'],r['year']) for r in all_metrics}
    for r in all_metrics:
        expected=archived[r['country'],r['year']]
        assert np.isclose(r['Gini'],float(expected['Gini_All']),atol=1e-12,rtol=0)
        assert np.isclose(r['Gini_Initial'],float(expected['Gini_CI']),atol=1e-12,rtol=0)
        assert r['N_Initial']==int(expected['N_C'])+int(expected['N_I'])
    audit=[]
    for cc in pool:
        rs=[r for r in all_metrics if r['country']==cc]
        hs=float(np.polyfit(YEARS,[r['HHI'] for r in rs],1)[0])
        gs=float(np.polyfit(YEARS,[r['Gini'] for r in rs],1)[0])
        initial_gs=float(np.polyfit(YEARS,[r['Gini_Initial'] for r in rs],1)[0])
        mean_gap=float(np.mean([r['Gini']-r['Gini_Initial'] for r in rs]))
        es=float(np.polyfit(YEARS,[r['normalized_equivalent_cities'] for r in rs],1)[0])
        audit.append(dict(country=cc,total_domestic_events=sum(r['flow_events'] for r in rs),
            years_with_events=len(rs),HHI_annual_slope=hs,Gini_annual_slope=gs,
            initial_city_Gini_annual_slope=initial_gs,mean_annual_Gini_gap=mean_gap,
            normalized_equivalent_cities_annual_slope=es,
            minimum_cities=min(r['N'] for r in rs),
            Gini_fitted_1998_2025_change=27*gs,median_HHI=float(np.median([r['HHI'] for r in rs])),
            both_trends_positive=hs>0 and gs>0,
            Gini_case_eligible=gs>0 and 27*gs>=.005 and min(r['N'] for r in rs)>=30))
    audit.sort(key=lambda r:(-r['total_domestic_events'],r['country']))
    with ((Path(__file__).resolve().parents[3] / 'outputs/results_network_revision_20261030/artwork/source_data/trajectory_membership.csv')).open(encoding='utf-8-sig',newline='') as f:
        quartile_by_country={r['country']:int(r['group']) for r in csv.DictReader(f)}
    candidates=[]
    for r in audit:
        cc=r['country'];minimum_annual=min(m['flow_events'] for m in all_metrics if m['country']==cc)
        eligible=r['total_domestic_events']>=CASE_MIN_TOTAL and minimum_annual>=CASE_MIN_ANNUAL and r['minimum_cities']>=CASE_MIN_CITIES
        candidates.append(dict(country=cc,group=quartile_by_country[cc],total_domestic_events=r['total_domestic_events'],
            minimum_annual_events=minimum_annual,minimum_cities=r['minimum_cities'],
            mean_annual_Gini_gap=r['mean_annual_Gini_gap'],eligible=eligible,selected=cc in CASE_COUNTRIES))
    eligible_candidates=sorted([r for r in candidates if r['eligible']],
        key=lambda r:(-r['mean_annual_Gini_gap'],r['country']))
    gap_ranks={r['country']:i+1 for i,r in enumerate(eligible_candidates)}
    group_candidates={q:[r for r in eligible_candidates if r['group']==q] for q in range(1,5)}
    assert all(group_candidates.values())
    group_ranks={r['country']:i+1 for q in range(1,5) for i,r in enumerate(group_candidates[q])}
    assert [group_candidates[q][0]['country'] for q in range(1,5)]==CASE_COUNTRIES
    for r in candidates:
        r['eligible_gap_rank']=gap_ranks.get(r['country'],'')
        r['within_T_gap_rank']=group_ranks.get(r['country'],'')
    assert len(CASE_COUNTRIES)==4
    assert all(r['eligible'] for r in candidates if r['selected'])
    write_csv('Fig4_quartile_case_candidates.csv',candidates)
    # The largest mean annual all-minus-initial Gini gap within each eligible
    # T group; all 28 years enter the score. Prevalence uses all 76 countries.
    selected=CASE_COUNTRIES.copy();case_selection=[];period_summaries=[]
    for i,cc in enumerate(selected):
        chosen=next(r for r in audit if r['country']==cc)
        rs=[r for r in all_metrics if r['country']==cc]
        case_selection.append(dict(panel='bcde'[i],position=i+1,country=cc,country_name=NAMES[cc],group=quartile_by_country[cc],
            total_domestic_events=chosen['total_domestic_events'],volume_rank=audit.index(chosen)+1,
            minimum_cities=chosen['minimum_cities'],minimum_annual_events=min(r['flow_events'] for r in rs),
            normalized_equivalent_cities_slope_pp=100*chosen['normalized_equivalent_cities_annual_slope'],
            initial_city_Gini_slope_pp=100*float(np.polyfit(YEARS,[r['Gini_Initial'] for r in rs],1)[0]),
            mean_annual_Gini_gap=chosen['mean_annual_Gini_gap'],eligible_gap_rank=gap_ranks[cc],
            within_T_gap_rank=group_ranks[cc],eligible_countries_in_T=len(group_candidates[quartile_by_country[cc]]),
            Gini_slope_pp=100*chosen['Gini_annual_slope'],illustrative_role=CASE_ROLES[cc],
            selection_rule='One country per T group: largest mean annual all-city minus initial-city Gini gap within the group among countries with total domestic events >=100000, every-year events >=1000 and every-year positive-flow cities >=30; all 28 years enter the score; all 76 countries retained in panel a'))
        for first in [1998,2005,2012,2019]:
            period=[r for r in rs if first<=r['year']<=first+6]
            period_summaries.append(dict(country=cc,first_year=first,last_year=first+6,
                **{metric:float(np.mean([r[metric] for r in period]))
                   for metric in ['N','flow_events','normalized_equivalent_cities','Gini','Gini_Initial','N_Initial']}))
    trends=[]
    for i,r in enumerate(audit):
        r.update(volume_rank=i+1,selected=r['country'] in selected,
            panel='bcde'[selected.index(r['country'])] if r['country'] in selected else '')
        x=100*r['normalized_equivalent_cities_annual_slope'];y=100*r['Gini_annual_slope']
        category=('Relative concentration' if x<0 and y>0 else
            'Deconcentration' if x>0 and y<0 else 'Mixed changes')
        trends.append(dict(country=r['country'],normalized_equivalent_cities_slope_pp=x,
            initial_city_Gini_slope_pp=100*r['initial_city_Gini_annual_slope'],
            Gini_slope_pp=y,category=category,case_panel=r['panel'],
            years=28,first_year=1998,last_year=2025))
    metrics=[dict(country_name=NAMES[r['country']],**r) for r in all_metrics if r['country'] in selected]
    write_csv('Fig4_country_selection.csv',audit)
    write_csv('Fig4_country_concentration_trends.csv',trends)
    write_csv('Fig4_all_country_combined_metrics.csv',all_metrics)
    write_csv('Fig4_domestic_city_margins.csv',[r for r in margins if r['country'] in selected])
    write_csv('Fig4_domestic_country_metrics.csv',metrics)
    write_csv('Fig4_case_selection.csv',case_selection)
    write_csv('Fig4_case_period_summary.csv',period_summaries)
    checks=dict(sample_countries=len(pool),both_HHI_and_Gini_positive=sum(r['both_trends_positive'] for r in audit),
        Gini_positive=sum(r['Gini_annual_slope']>0 for r in audit),
        relative_concentration=sum(r['category']=='Relative concentration' for r in trends),
        deconcentration=sum(r['category']=='Deconcentration' for r in trends),
        mixed_changes=sum(r['category']=='Mixed changes' for r in trends),
        combined_city_margins_match_directional_cleaned_margins_exactly=True,
        all_city_strength_totals_twice_domestic_events=True,
        initial_city_Gini_matches_Fig4_source=True,
        all_city_slope_higher_than_initial=sum(r['Gini_slope_pp']>r['initial_city_Gini_slope_pp'] for r in trends),
        initial_Gini_declines_all_Gini_rises=sum(r['initial_city_Gini_slope_pp']<0<r['Gini_slope_pp'] for r in trends),
        eligible_case_countries=len(eligible_candidates),
        eligible_countries_by_T={f'T{q}':len(group_candidates[q]) for q in range(1,5)},
        initial_city_definition='Cities recorded in 1998 and active in the plotted year, retaining full domestic margins')
    return selected,metrics,trends,checks,case_selection


def metric_axis(values,metric):
    """Choose a padded, country-specific scale using all 28 annual observations."""
    low=float(min(values));high=float(max(values));span=high-low
    pad=max(.12*span,.00012 if metric=='HHI' else .003)
    locator=MaxNLocator(nbins=3,steps=[1,2,5,10],min_n_ticks=3)
    ticks=locator.tick_values(max(0.,low-pad),min(1.,high+pad))
    ticks=ticks[(ticks>=0)&(ticks<=1)]
    assert ticks[0]<=low and ticks[-1]>=high
    return (float(ticks[0]),float(ticks[-1])),ticks


def place_inset_labels(fig,ax,rows,codes,font,excluded):
    """Globally favour nearby direct labels; route only necessary short leaders."""
    from scipy.optimize import milp,Bounds,LinearConstraint
    from scipy.sparse import coo_matrix
    fig.canvas.draw();renderer=fig.canvas.get_renderer();scale=fig.dpi/72
    locations={r['country']:ax.transData.transform((r['x'],r['y']))/scale for r in rows}
    guide_paths=[PlotPath(line.get_transform().transform(line.get_path().vertices)/scale)
                 for line in ax.lines if line.get_visible()]
    origin=ax.transData.transform((0,0))/scale
    frame=Bbox.from_extents(*(ax.get_window_extent().extents/scale)).padded(-1.1)
    choices={};all_options=[]
    def box_distance(point,box):
        return float(np.hypot(max(box.x0-point[0],0,point[0]-box.x1),max(box.y0-point[1],0,point[1]-box.y1)))
    for cc in codes:
        r=next(r for r in rows if r['country']==cc);point=locations[cc]
        sample=ax.text(.5,.5,cc,transform=ax.transAxes,fontsize=font,ha='left',va='bottom')
        bb=sample.get_window_extent(renderer);width=bb.width/scale;height=bb.height/scale;sample.remove()
        options=[]
        for distance in [3,4,5,6,7,8,9,10,12,14,16,18,20,24,28,32,36,40]:
            for angle in np.arange(0,360,15):
                dx=distance*np.cos(np.deg2rad(angle));dy=distance*np.sin(np.deg2rad(angle))
                ha='left' if dx>1 else 'right' if dx< -1 else 'center';va='bottom' if dy>1 else 'top' if dy< -1 else 'center'
                x=point[0]+dx-(0 if ha=='left' else width if ha=='right' else width/2)
                y=point[1]+dy-(0 if va=='bottom' else height if va=='top' else height/2)
                box=Bbox.from_bounds(x,y,width,height);pad=box.padded(.65)
                if not (frame.contains(pad.x0,pad.y0) and frame.contains(pad.x1,pad.y1)):continue
                if any(pad.overlaps(b.padded(.35)) for b in excluded):continue
                if any(guide.intersects_bbox(box.padded(1.),filled=False) for guide in guide_paths):continue
                if any(box_distance(p,box)<2.1 for p in locations.values()):continue
                own_distance=box_distance(point,box)
                nearest_other=min(box_distance(p,box) for country,p in locations.items() if country!=cc)
                same_x=(box.x1<origin[0]-1.5 if r['x']<0 else box.x0>origin[0]+1.5)
                same_y=(box.y0>origin[1]+1.5 if r['y']>0 else box.y1<origin[1]-1.5)
                leader=own_distance>7 or nearest_other<own_distance+3 or not (same_x and same_y)
                path=None
                if leader:
                    nearest=np.array([np.clip(point[0],box.x0,box.x1),np.clip(point[1],box.y0,box.y1)])
                    delta=nearest-point;length=np.linalg.norm(delta);start=point+delta/length*2.3;end=nearest-delta/length*.8
                    path=PlotPath(np.vstack([start,end]))
                    if any(path.intersects_bbox(b.padded(.35),filled=False) for b in excluded):continue
                    segment=end-start;norm=segment@segment
                    if norm<=0:continue
                    if any(np.linalg.norm(p-(start+np.clip((p-start)@segment/norm,0,1)*segment))<.35
                           for country,p in locations.items() if country!=cc):continue
                options.append(dict(country=cc,dx=float(dx),dy=float(dy),ha=ha,va=va,box=box,path=path,
                    distance=distance,leader=leader,cost=10000*leader+own_distance**2+distance*.05))
        options.sort(key=lambda o:o['cost'])
        # Keep angular alternatives for every country instead of placing labels greedily.
        selected=[o for o in options if not o['leader']][:70]
        selected.extend([o for o in options if o['leader']][:40])
        for lo,hi in [(0,10),(10,18),(18,26),(26,34),(34,42)]:
            for angle_bin in range(8):
                selected.extend([o for o in options if o['leader'] and lo<=o['distance']<hi
                    and int((np.rad2deg(np.arctan2(o['dy'],o['dx']))%360)//45)==angle_bin][:2])
        selected=list({id(o):o for o in selected}.values())
        assert selected,cc
        choices[cc]=list(range(len(all_options),len(all_options)+len(selected)));all_options.extend(selected)
    rr=[];ccs=[];values=[];lower=[];upper=[]
    def constraint(indices,lo,hi):
        row=len(lower);rr.extend([row]*len(indices));ccs.extend(indices);values.extend([1.]*len(indices));lower.append(lo);upper.append(hi)
    for ids in choices.values():constraint(ids,1,1)
    for i,code in enumerate(codes):
        for other in codes[i+1:]:
            for first in choices[code]:
                a=all_options[first]
                for second in choices[other]:
                    b=all_options[second]
                    conflict=a['box'].padded(.5).overlaps(b['box'].padded(.5))
                    horizontal_gap=max(a['box'].x0-b['box'].x1,b['box'].x0-a['box'].x1,0)
                    centre_gap=abs((a['box'].y0+a['box'].y1-b['box'].y0-b['box'].y1)/2)
                    if horizontal_gap<7 and centre_gap<font*.95:conflict=True
                    if not conflict and a['path'] is not None:conflict=a['path'].intersects_bbox(b['box'].padded(.8),filled=False)
                    if not conflict and b['path'] is not None:conflict=b['path'].intersects_bbox(a['box'].padded(.8),filled=False)
                    if not conflict and a['path'] is not None and b['path'] is not None:
                        conflict=a['path'].intersects_path(b['path'],filled=False)
                    if conflict:constraint([first,second],-np.inf,1)
    matrix=coo_matrix((values,(rr,ccs)),shape=(len(lower),len(all_options))).tocsc()
    result=milp(np.asarray([o['cost'] for o in all_options]),integrality=np.ones(len(all_options)),bounds=Bounds(0,1),
        constraints=LinearConstraint(matrix,np.asarray(lower),np.asarray(upper)),options=dict(time_limit=35,mip_rel_gap=0.))
    assert result.x is not None, result.message
    chosen=[o for o,value in zip(all_options,result.x) if value>.5];assert len(chosen)==len(codes)
    output=[]
    for option in chosen:
        code=option['country'];row=next(r for r in rows if r['country']==code)
        ax.annotate(code,xy=(row['x'],row['y']),xytext=(option['dx'],option['dy']),textcoords='offset points',
            fontsize=font,color='black',ha=option['ha'],va=option['va'],zorder=10)
        if option['path'] is not None:
            xy=ax.transData.inverted().transform(option['path'].vertices*scale)
            ax.plot(xy[:,0],xy[:,1],color='#7B838C',linewidth=.4,zorder=9)
        output.append(dict(country=code,point_x=row['x'],point_y=row['y'],label_x=option['dx'],label_y=option['dy'],leader=option['leader']))
    return output,dict(method='Global binary placement: minimize leaders, then label-to-point distance; forbid label collisions, point occlusion and crossing leaders',
        labelled_countries=len(codes),leader_count=sum(o['leader'] for o in chosen),solver_optimal=bool(result.success),solver_message=result.message)


def main():
    DATA.mkdir(exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    selected,metrics,trends,checks,case_selection=prepare_data()
    group_source=DATA/'trajectory_membership.csv'
    with group_source.open(encoding='utf-8-sig',newline='') as f:
        groups={r['country']:int(r['group']) for r in csv.DictReader(f)}
    assert set(groups)=={r['country'] for r in trends} and len(groups)==76
    assert [list(groups.values()).count(q) for q in range(1,5)]==[15,14,24,23]
    colours={1:'#7E99F4',2:'#A5AEB7',3:'#7AB656',4:'#CC7C71'}
    assert checks['all_city_slope_higher_than_initial']==69
    assert checks['initial_Gini_declines_all_Gini_rises']==38
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica'],
        'font.size':7,'axes.labelsize':7,'xtick.labelsize':7,'ytick.labelsize':7,
        'axes.linewidth':AXIS_LINEWIDTH_PT,'axes.spines.top':False,'axes.spines.right':False,
        'text.color':INK,'axes.labelcolor':INK,'xtick.color':INK,'ytick.color':INK,
        'axes.unicode_minus':False,'legend.frameon':False,'pdf.use14corefonts':False,
        'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white',
        'path.simplify':False})
    width_pt=WIDTH_PT;height_pt=100*72/25.4
    fig=plt.figure(figsize=(width_pt/72,height_pt/72))
    panel_width=75.;panel_height=75.;hero_size=190.
    bottom=height_pt-38-hero_size
    grid=fig.add_gridspec(2,3,left=38/width_pt,right=471/width_pt,
        bottom=bottom/height_pt,top=(height_pt-38)/height_pt,
        width_ratios=[190,75,75],height_ratios=[75,75],
        wspace=46.5/(340/3),hspace=40/75)
    hero=fig.add_subplot(grid[:,0]);hero.set_gid('a')
    axes=[hero];axis_records=[];plotted=[]
    low,high=-.65,1.95
    hero.set(xlim=(low,high),ylim=(low,high))
    hero.fill_between([low,high],[low,high],[high,high],color='#F3F4F5',lw=0,zorder=0)
    hero.plot([low,high],[low,high],color=REFERENCE_COLOUR,lw=.8,
              linestyle=REFERENCE_LINESTYLE,zorder=1)
    hero.axvline(0,color=REFERENCE_COLOUR,lw=REFERENCE_LINEWIDTH_PT,
                 linestyle=REFERENCE_LINESTYLE,zorder=1)
    hero.set_xticks([-.5,0,.5,1,1.5]);hero.set_yticks([-.5,0,.5,1,1.5])
    hero.xaxis.set_major_formatter(FormatStrFormatter('%g'))
    hero.yaxis.set_major_formatter(FormatStrFormatter('%g'))
    zoom_limits=dict(x=[-.55,.20],y=[-.25,.40])
    zoom_members=[r for r in trends if zoom_limits['x'][0]<=r['initial_city_Gini_slope_pp']<=zoom_limits['x'][1]
                  and zoom_limits['y'][0]<=r['Gini_slope_pp']<=zoom_limits['y'][1]]
    assert set(selected)<={r['country'] for r in zoom_members}
    inset_bounds=[.45,.055,.53,.44]
    inset_x=[low+(high-low)*inset_bounds[0],low+(high-low)*(inset_bounds[0]+inset_bounds[2])]
    inset_y=[low+(high-low)*inset_bounds[1],low+(high-low)*(inset_bounds[1]+inset_bounds[3])]
    assert not any(inset_x[0]-.04<r['initial_city_Gini_slope_pp']<inset_x[1]+.04
                   and inset_y[0]-.03<r['Gini_slope_pp']<inset_y[1]+.03 for r in trends)
    hero.hlines([0,0],[low,inset_x[1]],[inset_x[0],high],color=REFERENCE_COLOUR,
                lw=REFERENCE_LINEWIDTH_PT,linestyle=REFERENCE_LINESTYLE,zorder=1)
    for group in range(1,5):
        rs=[r for r in trends if groups[r['country']]==group]
        hero.scatter([r['initial_city_Gini_slope_pp'] for r in rs],[r['Gini_slope_pp'] for r in rs],
            s=COUNTRY_POINT_PT2,color=colours[group],alpha=COUNTRY_POINT_ALPHA,
            edgecolors=['black' if r['country'] in selected else 'white' for r in rs],
            linewidths=[.65 if r['country'] in selected else COUNTRY_POINT_EDGE_PT for r in rs],zorder=3)
    hero.set_xlabel('Initial City Gini Slope (pp/year)',fontsize=7,labelpad=5)
    hero.set_ylabel('All City Gini Slope (pp/year)',fontsize=7,labelpad=5)
    hero.tick_params(axis='both',length=2,width=TICK_LINEWIDTH_PT,pad=2.5,labelsize=7)
    hero.text(-22/hero_size,1+7/hero_size,'a',transform=hero.transAxes,
        fontsize=7,fontweight='bold',ha='left',va='bottom')
    handles=[Line2D([],[],marker='o',linestyle='none',markersize=np.sqrt(COUNTRY_POINT_PT2),
        markerfacecolor=colours[q],markeredgecolor='white',markeredgewidth=COUNTRY_POINT_EDGE_PT,
        alpha=COUNTRY_POINT_ALPHA,label=f'T{q}') for q in range(1,5)]
    hero.legend(handles=handles,loc='upper left',bbox_to_anchor=(-.01,.985),ncol=1,
        fontsize=7,handletextpad=.3,handlelength=.65,labelspacing=.45,borderaxespad=0,
        borderpad=.4,title='Share Growth',title_fontsize=7,frameon=False)
    zoom=hero.inset_axes(inset_bounds,zorder=5);zoom.set_gid('a_zoom')
    zoom.set(xlim=zoom_limits['x'],ylim=zoom_limits['y']);zoom.set_facecolor('white')
    for spine in zoom.spines.values():
        spine.set_visible(True);spine.set_linewidth(.55);spine.set_color('#606A74')
    xx=np.array([zoom_limits['x'][0],zoom_limits['y'][0],zoom_limits['x'][1]])
    zoom.fill_between(xx,np.maximum(xx,zoom_limits['y'][0]),zoom_limits['y'][1],
        where=xx<=zoom_limits['y'][1],color='#F3F4F5',lw=0,zorder=0)
    zoom.plot([zoom_limits['y'][0],zoom_limits['x'][1]],
              [zoom_limits['y'][0],zoom_limits['x'][1]],color=REFERENCE_COLOUR,
              lw=.8,linestyle=REFERENCE_LINESTYLE,zorder=1)
    zoom.axvline(0,color=REFERENCE_COLOUR,lw=REFERENCE_LINEWIDTH_PT,linestyle=REFERENCE_LINESTYLE,zorder=1)
    zoom.axhline(0,color=REFERENCE_COLOUR,lw=REFERENCE_LINEWIDTH_PT,linestyle=REFERENCE_LINESTYLE,zorder=1)
    zoom.set_xticks([-.5,-.25,0]);zoom.set_yticks([-.2,0,.3])
    zoom.xaxis.set_major_formatter(FormatStrFormatter('%g'));zoom.yaxis.set_major_formatter(FormatStrFormatter('%g'))
    zoom.tick_params(axis='both',length=1.8,width=.45,pad=1.8,labelsize=7,colors='black')
    zoom.yaxis.tick_right()
    zoom.tick_params(axis='y',direction='out',pad=2)
    for group in range(1,5):
        rs=[r for r in zoom_members if groups[r['country']]==group]
        zoom.scatter([r['initial_city_Gini_slope_pp'] for r in rs],[r['Gini_slope_pp'] for r in rs],
            s=13,color=colours[group],alpha=COUNTRY_POINT_ALPHA,
            edgecolors=['black' if r['country'] in selected else 'white' for r in rs],
            linewidths=[.65 if r['country'] in selected else COUNTRY_POINT_EDGE_PT for r in rs],zorder=3)
    roi=Rectangle((zoom_limits['x'][0],zoom_limits['y'][0]),
        zoom_limits['x'][1]-zoom_limits['x'][0],zoom_limits['y'][1]-zoom_limits['y'][0],
        facecolor='none',edgecolor='#606A74',lw=.65,zorder=2)
    hero.add_patch(roi)
    connector=ConnectionPatch(xyA=(0,.5),coordsA=zoom.transAxes,
        xyB=(zoom_limits['x'][1],sum(zoom_limits['y'])/2),coordsB=hero.transData,
        color='#A9AFB6',lw=.5,zorder=1.5,clip_on=False)
    hero.add_artist(connector)
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    obstacles=[Bbox.from_extents(*(t.get_window_extent(renderer).extents*72/fig.dpi))
               for t in zoom.get_yticklabels()+zoom.get_xticklabels()]
    zoom_rows=[dict(country=r['country'],x=r['initial_city_Gini_slope_pp'],y=r['Gini_slope_pp']) for r in zoom_members]
    with (DATA/'Fig4_country_selection.csv').open(encoding='utf-8-sig',newline='') as f:
        volume_ranking=list(csv.DictReader(f))
    major_codes=[r['country'] for r in volume_ranking[:MAJOR_COUNTRY_LABEL_COUNT]]
    annotation_codes=list(dict.fromkeys(major_codes+selected))
    assert set(annotation_codes)<={r['country'] for r in zoom_members}
    labels,label_report=place_inset_labels(fig,zoom,zoom_rows,annotation_codes,7,obstacles)
    for label in labels:
        label['volume_rank']=next(i+1 for i,r in enumerate(volume_ranking) if r['country']==label['country'])
        label['case_country']=label['country'] in selected
        label['major_country']=label['country'] in major_codes
        label['display']='a_zoom'
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    parent_obstacles=[Bbox.from_extents(*(obj.get_window_extent(renderer).extents*72/fig.dpi)).padded(2.)
                      for obj in [hero.get_legend()]]
    parent_obstacles.append(Bbox.from_extents(*(zoom.get_tightbbox(renderer).extents*72/fig.dpi)).padded(2.))
    parent_rows=[dict(country=r['country'],x=r['initial_city_Gini_slope_pp'],y=r['Gini_slope_pp']) for r in trends]
    assert not set(PERIPHERAL_LABEL_CODES)&{r['country'] for r in zoom_members}
    peripheral_labels,peripheral_label_report=place_inset_labels(
        fig,hero,parent_rows,PERIPHERAL_LABEL_CODES,7,parent_obstacles)
    for label in peripheral_labels:
        label['volume_rank']=next(i+1 for i,r in enumerate(volume_ranking) if r['country']==label['country'])
        label['case_country']=False
        label['major_country']=False
        label['display']='a'
    labels.extend(peripheral_labels)
    fig.legend(handles=[Line2D([],[],color=RED,lw=ANNUAL_LINEWIDTH_PT,label='All Cities'),
                        Line2D([],[],color=BLUE,lw=ANNUAL_LINEWIDTH_PT,label='Initial Cities')],
        loc='upper center',bbox_to_anchor=(372.75/width_pt,(height_pt-7)/height_pt),ncol=2,
        fontsize=7,labelcolor='black',handlelength=1.8,handletextpad=.5,columnspacing=1.8,borderaxespad=0)
    for i,cc in enumerate(selected):
        row,col=divmod(i,2);letter='bcde'[i]
        ax=fig.add_subplot(grid[row,col+1]);ax.set_gid(letter);axes.append(ax)
        both=sorted([r for r in metrics if r['country']==cc],key=lambda r:r['year'])
        ylim,ticks=metric_axis([r[k] for r in both for k in ['Gini','Gini_Initial']],'Gini')
        if len(ticks)>5:ticks=ticks[::2]
        ax.set_ylim(*ylim);ax.set_yticks(ticks);ax.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))
        ax.tick_params(axis='y',labelsize=7,length=1.8,width=TICK_LINEWIDTH_PT,pad=.5,colors='black')
        assert [r['year'] for r in both]==YEARS
        assert np.isclose(both[0]['Gini'],both[0]['Gini_Initial'],atol=1e-12)
        for key,color in [('Gini_Initial',BLUE),('Gini',RED)]:
            ys=[r[key] for r in both]
            ax.plot(YEARS,ys,color=color,lw=ANNUAL_LINEWIDTH_PT,linestyle='-',marker='o',
                markersize=ANNUAL_MARKER_PT,markevery=MARKER_INDICES,markerfacecolor=color,
                markeredgecolor='white',markeredgewidth=ANNUAL_MARKER_EDGE_PT,zorder=3)
            plotted.extend(dict(panel=letter,country=cc,metric=key,year=y,value=float(v),axis='shared')
                           for y,v in zip(YEARS,ys))
        ax.set_xlim(1996,2027);ax.set_xticks([1998,2012,2025])
        ax.tick_params(axis='x',length=2,width=TICK_LINEWIDTH_PT,pad=2.3,labelsize=7,colors='black')
        ax.set_xlabel('Year',fontsize=7,labelpad=3);ax.set_title(f'{NAMES[cc]} (T{groups[cc]})',fontsize=7,pad=7)
        if col==0:ax.set_ylabel('Domestic City Gini',fontsize=7,labelpad=3)
        ax.text(-22/panel_width,1+7/panel_height,letter,transform=ax.transAxes,
                fontsize=7,fontweight='bold',ha='left',va='bottom')
        axis_records.append(dict(panel=letter,country=cc,row=row+1,shared_Gini_limits=list(ylim),
            width_pt=panel_width,height_pt=panel_height))
    apply_axes_typography(fig,grid_json_out=QA/'grid.json');fig.canvas.draw()
    alignment=require_matplotlib_panel_alignment(fig,json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',
        tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True,axes=axes+[zoom],
        exemptions=[dict(panels=['a_zoom'],checks=['all'],reason='Nested zoom of the marked a-panel region, not a primary grid cell')])
    comparison=[]
    for r in trends:
        x=r['initial_city_Gini_slope_pp'];y=r['Gini_slope_pp']
        xy=hero.transData.transform((x,y));r.update(pdf_x_pt=float(xy[0]*72/fig.dpi),pdf_y_pt=float(height_pt-xy[1]*72/fig.dpi))
        comparison.append(dict(country=r['country'],group=groups[r['country']],initial_city_Gini_slope_pp=x,
            all_city_Gini_slope_pp=y,slope_difference_pp=y-x,above_equality=int(y>x),
            initial_decline_all_rise=int(x<0<y),case_panel=r['case_panel']))
    write_csv('Fig5_slope_comparison.csv',comparison)
    write_csv('Fig4_country_concentration_trends.csv',trends)
    write_csv('Fig4_plotted_values.csv',plotted)
    write_csv('Fig4_scatter_country_labels.csv',labels)
    write_csv('Fig4_zoom_points.csv',zoom_rows)
    stem=OUT/'Fig4'
    fig.savefig(stem.with_suffix('.pdf'));fig.savefig(stem.with_suffix('.svg'))
    fig.savefig(stem.with_suffix('.png'),dpi=600)
    with pymupdf.open(stem.with_suffix('.pdf')) as doc:
        page=doc[0];page.get_pixmap(matrix=pymupdf.Matrix(2.6,2.6),alpha=False).save(QA/'preview.png')
        fonts=sorted({f[3] for f in page.get_fonts()})
        for ax in axes:
            b=ax.get_position();clip=pymupdf.Rect(b.x0*width_pt-36,height_pt-b.y1*height_pt-26,
                b.x1*width_pt+12,height_pt-b.y0*height_pt+35)
            page.get_pixmap(matrix=pymupdf.Matrix(3.2,3.2),clip=clip,alpha=False).save(QA/f'preview_{ax.get_gid()}.png')
    report=dict(figure='Fig5',archetype='quantitative grid',dimensions_mm=[180,100],fonts_pdf=fonts,
        claim='All-city Gini slopes exceed initial-city slopes in 69 of 76 countries; selected high-volume country histories illustrate their annual divergence',
        selected_countries=selected,selection_scope='One illustration per T group selected for separation; prevalence uses all 76 countries',
        selection_rule='Among countries with total domestic events >=100000, events in every year >=1000 and active cities in every year >=30, choose the largest arithmetic mean all-city minus initial-city Gini gap over all 28 years within each of T1–T4',
        case_selection=case_selection,all_country_trend_audit=checks,years=YEARS,
        event_count_note='Flow weights count mobility events, not full-period unique researchers',
        scatter=dict(x='Initial-city Gini OLS slope (pp/year)',y='All-city Gini OLS slope (pp/year)',
            equal_x_y_limits=[low,high],diagonal='Equality',shade='All-city slope > initial-city slope',
            countries=76,above_equality=69,initial_decline_all_rise=38,point_colours='Canonical T1–T4'),
        zoom=dict(bounds_parent_axes=inset_bounds,xlim=zoom_limits['x'],ylim=zoom_limits['y'],
                  countries=len(zoom_members),labelled_countries=annotation_codes,label_placement=label_report),
        country_annotation_rule='Inset: ten largest countries by cumulative domestic events plus four cases, giving twelve codes. Parent: eight additional codes identify peripheral positions outside the zoom rectangle. Country data and T memberships unchanged.',
        major_country_codes=major_codes,
        peripheral_country_codes=PERIPHERAL_LABEL_CODES,peripheral_label_placement=peripheral_label_report,
        case_metrics=dict(red='All-city Gini',blue='Initial-city Gini',shared_y_axis=True,
            initial_definition='Recorded in 1998 and active in the displayed year; full domestic margins retained',
            interval='None: raw annual indices',all_28_years_in_lines=True,
            marker_years=[YEARS[i] for i in MARKER_INDICES]),
        axis_records=axis_records,source_rows=len(metrics),plotted_values=len(plotted),alignment=alignment['verdict'],
        source_data=['Fig5_slope_comparison.csv','Fig4_plotted_values.csv','Fig4_domestic_country_metrics.csv',
                     'Fig4_case_selection.csv','Fig4_quartile_case_candidates.csv','Fig4_all_country_combined_metrics.csv'],
        canonical_input_sha256=sha256(CANONICAL),initial_source_sha256=sha256(INITIAL_SOURCE))
    (QA/'figure_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    plt.close(fig)
    print(json.dumps(dict(countries=76,selected=selected,above_equality=69,initial_decline_all_rise=38,
                          eligible=checks['eligible_case_countries'],alignment=alignment['verdict']),ensure_ascii=False))


if __name__=='__main__':
    main()
