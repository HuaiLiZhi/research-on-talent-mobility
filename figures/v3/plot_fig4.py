"""Fig4: all-country concentration trends beside four domestic-city histories.

Figure contract: establish prevalence in the complete fixed 76-country sample,
then show the retained four country histories. A square hero spans two rows;
four square cases retain independent country scales and outer metric titles.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from io import BytesIO
import sys
from pathlib import Path

from figure_style import font_size, output_root, WIDTH_PT, PROFILE, specification, apply_axes_typography

ROOT=Path(__file__).resolve().parents[2]
OUT=output_root(Path(__file__).resolve().parent)
DATA=OUT/'source_data'
QA=OUT/'QA'/'Fig4'
CLEAN=ROOT/'data'/'processed'/'mobility_city_harmonized_20261020'
CANONICAL=CLEAN/'analysis'/'flow_top100.parquet'
SKILL=Path.home()/'.codex'/'skills'/'nature-figure'/'scripts'
sys.path[:0]=[str(ROOT/'tmp'/'nhb_fig2_python_deps'),str(SKILL)]

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

from figure_palette import BLUE, RED, GRAY, GREEN
INK='#17212A'
NAMES={'US':'United States','PL':'Poland','BR':'Brazil','IN':'India'}
CASE_COUNTRIES=['US','PL','BR','IN']
CASE_ROLES={'US':'T1: gradual persistent relative concentration',
    'PL':'T2: larger sustained relative concentration',
    'BR':'T3: full-period deconcentration followed by recent reconcentration',
    'IN':'T4: non-monotonic adjustment and weak full-period domestic trends'}
CASE_MIN_TOTAL=100000;CASE_MIN_ANNUAL=1000;CASE_MIN_CITIES=30
YEARS=list(range(1998,2026))
MARKER_INDICES=[0,5,10,15,20,25,27]
LABEL_BANDS=[-2.5,-2.15,-1.8,-1.45,-1.15,-.8,-.45,-.1,0]
LEFT_METRIC='normalized_equivalent_cities'
LEFT_LEGEND=r'$R$'


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
    groups={};all_metrics=[]
    for row in margins:
        groups.setdefault((row['country'],row['year']),[]).append(row['total_city_strength'])
    for cc in pool:
        for year in YEARS:
            values=np.array(groups[cc,year]);n=len(values)
            total=float(sum(values));p=values/total
            assert n>=2 and np.all(p>0) and np.isclose(sum(p),1)
            assert total==2*totals[cc,year]
            hhi=float(sum(p*p))
            gini=float(2*np.dot(np.arange(1,n+1),np.sort(p))/n-(n+1)/n)
            all_metrics.append(dict(country=cc,year=year,N=n,flow_events=totals[cc,year],
                total_city_strength=total,HHI=hhi,Gini=gini,normalized_equivalent_cities=1/(n*hhi)))
    audit=[]
    for cc in pool:
        rs=[r for r in all_metrics if r['country']==cc]
        hs=float(np.polyfit(YEARS,[r['HHI'] for r in rs],1)[0])
        gs=float(np.polyfit(YEARS,[r['Gini'] for r in rs],1)[0])
        es=float(np.polyfit(YEARS,[r['normalized_equivalent_cities'] for r in rs],1)[0])
        audit.append(dict(country=cc,total_domestic_events=sum(r['flow_events'] for r in rs),
            years_with_events=len(rs),HHI_annual_slope=hs,Gini_annual_slope=gs,
            normalized_equivalent_cities_annual_slope=es,
            minimum_cities=min(r['N'] for r in rs),
            Gini_fitted_1998_2025_change=27*gs,median_HHI=float(np.median([r['HHI'] for r in rs])),
            both_trends_positive=hs>0 and gs>0,
            Gini_case_eligible=gs>0 and 27*gs>=.005 and min(r['N'] for r in rs)>=30))
    audit.sort(key=lambda r:(-r['total_domestic_events'],r['country']))
    with (ROOT/'figures/v3/source_data/Fig5_stratified_country_trends.csv').open(encoding='utf-8-sig',newline='') as f:
        quartile_by_country={r['country']:int(r['group']) for r in csv.DictReader(f)}
    candidates=[]
    for r in audit:
        cc=r['country'];minimum_annual=min(m['flow_events'] for m in all_metrics if m['country']==cc)
        eligible=r['total_domestic_events']>=CASE_MIN_TOTAL and minimum_annual>=CASE_MIN_ANNUAL and r['minimum_cities']>=CASE_MIN_CITIES
        candidates.append(dict(country=cc,group=quartile_by_country[cc],total_domestic_events=r['total_domestic_events'],
            minimum_annual_events=minimum_annual,minimum_cities=r['minimum_cities'],eligible=eligible,selected=cc in CASE_COUNTRIES))
    assert [quartile_by_country[c] for c in CASE_COUNTRIES]==[1,2,3,4]
    assert all(r['eligible'] for r in candidates if r['selected'])
    write_csv('Fig4_quartile_case_candidates.csv',candidates)
    # Explicit illustrative cases chosen after reviewing event volumes and
    # complete annual histories. Prevalence still uses the entire 76-country pool.
    selected=CASE_COUNTRIES.copy();case_selection=[];period_summaries=[]
    for i,cc in enumerate(selected):
        chosen=next(r for r in audit if r['country']==cc)
        rs=[r for r in all_metrics if r['country']==cc]
        case_selection.append(dict(panel='bcde'[i],position=i+1,country=cc,country_name=NAMES[cc],group=quartile_by_country[cc],
            total_domestic_events=chosen['total_domestic_events'],volume_rank=audit.index(chosen)+1,
            minimum_cities=chosen['minimum_cities'],minimum_annual_events=min(r['flow_events'] for r in rs),
            normalized_equivalent_cities_slope_pp=100*chosen['normalized_equivalent_cities_annual_slope'],
            Gini_slope_pp=100*chosen['Gini_annual_slope'],illustrative_role=CASE_ROLES[cc],
            selection_rule='One country per Fig5 quartile; total domestic events >=100000, every-year events >=1000 and every-year positive-flow cities >=30; contrasting complete annual trajectories; all 76 countries retained in panel a'))
        for first in [1998,2005,2012,2019]:
            period=[r for r in rs if first<=r['year']<=first+6]
            period_summaries.append(dict(country=cc,first_year=first,last_year=first+6,
                **{metric:float(np.mean([r[metric] for r in period]))
                   for metric in ['N','flow_events','normalized_equivalent_cities','Gini']}))
    trends=[]
    for i,r in enumerate(audit):
        r.update(volume_rank=i+1,selected=r['country'] in selected,
            panel='bcde'[selected.index(r['country'])] if r['country'] in selected else '')
        x=100*r['normalized_equivalent_cities_annual_slope'];y=100*r['Gini_annual_slope']
        category=('Relative concentration' if x<0 and y>0 else
            'Deconcentration' if x>0 and y<0 else 'Mixed changes')
        trends.append(dict(country=r['country'],normalized_equivalent_cities_slope_pp=x,
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
        all_city_strength_totals_twice_domestic_events=True)
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
                if not (box.x1<origin[0]-1.5 if r['x']<0 else box.x0>origin[0]+1.5):continue
                if not (box.y0>origin[1]+1.5 if r['y']>0 else box.y1<origin[1]-1.5):continue
                if any(box_distance(p,box)<2.1 for p in locations.values()):continue
                own_distance=box_distance(point,box)
                nearest_other=min(box_distance(p,box) for country,p in locations.items() if country!=cc)
                leader=own_distance>12
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
        selected=[]
        selected.extend([o for o in options if not o['leader']][:100])
        selected.extend([o for o in options if o['leader']][:65])
        for lo,hi in [(20,30),(30,42)]:
            selected.extend([o for o in options if o['leader'] and lo<=o['distance']<hi][:25])
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
    group_source=ROOT/'figures/v3/source_data/Fig5_stratified_country_trends.csv'
    with group_source.open(encoding='utf-8-sig',newline='') as f:fig5_groups=list(csv.DictReader(f))
    quartiles={r['country']:int(r['group']) for r in fig5_groups}
    assert len(fig5_groups)==76 and set(quartiles)=={r['country'] for r in trends}
    assert all(list(quartiles.values()).count(q)==19 for q in range(1,5))
    quartile_colors={1:BLUE,2:GRAY,3:GREEN,4:RED};background='#F3F4F5'
    membership=[dict(country=r['country'],group=quartiles[r['country']],
        international_share_annual_rate_pct=float(next(g['international_share_annual_rate_pct'] for g in fig5_groups if g['country']==r['country'])),
        domestic_category=r['category'],color=quartile_colors[quartiles[r['country']]]) for r in trends]
    quartile_summary=[dict(group=q,countries=19,
        relative_concentration=sum(r['group']==q and r['domestic_category']=='Relative concentration' for r in membership),
        deconcentration=sum(r['group']==q and r['domestic_category']=='Deconcentration' for r in membership),
        mixed_changes=sum(r['group']==q and r['domestic_category']=='Mixed changes' for r in membership),
        color=quartile_colors[q]) for q in range(1,5)]
    write_csv('Fig4_Fig5_quartile_membership.csv',membership)
    write_csv('Fig4_quartile_concentration_summary.csv',quartile_summary)
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial'],
        'font.size':font_size(7),'axes.labelsize':font_size(6.4),'xtick.labelsize':font_size(6),'ytick.labelsize':font_size(6),
        'axes.linewidth':.55,'axes.spines.top':False,'axes.spines.right':False,
        'text.color':INK,'axes.labelcolor':INK,'xtick.color':INK,'ytick.color':INK,
        'axes.unicode_minus':False,'legend.frameon':False,'pdf.use14corefonts':True,
        'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
    width_pt=WIDTH_PT;height_pt=100*72/25.4
    fig=plt.figure(figsize=(width_pt/72,height_pt/72))
    panel_width=75.;panel_height=75.;hero_size=190.
    bottom=height_pt-38-hero_size
    grid=fig.add_gridspec(2,3,left=38/width_pt,right=471/width_pt,
        bottom=bottom/height_pt,top=(height_pt-38)/height_pt,
        width_ratios=[190,75,75],height_ratios=[75,75],
        wspace=46.5/(340/3),hspace=40/75)
    hero=fig.add_subplot(grid[:,0]);hero.set_gid('a')
    axes=[hero];twins=[];axis_records=[];plotted=[]
    hero.set_xlim(-2.6,.6);hero.set_ylim(-.35,2.05)
    hero.fill_between([-2.6,0],0,2.05,color=background,zorder=0,linewidth=0)
    # Stop the zero guide below the upper-right legend; no observation lies there.
    vertical_guide=hero.axvline(0,ymax=.78,color=GRAY,linewidth=.65,zorder=1)
    main_zero_line=hero.axhline(0,color=GRAY,linewidth=.65,zorder=1)
    hero.set_xticks([-2.5,-2,-1.5,-1,-.5,0,.5])
    hero.set_yticks([-.25,0,.5,1,1.5,2])
    hero.xaxis.set_major_formatter(FormatStrFormatter('%g'))
    hero.yaxis.set_major_formatter(FormatStrFormatter('%g'))
    zoom_limits=dict(x=[-.30,.135],y=[-.195,.33])
    zoom_members=[r for r in trends
        if zoom_limits['x'][0]<=r['normalized_equivalent_cities_slope_pp']<=zoom_limits['x'][1]
        and zoom_limits['y'][0]<=r['Gini_slope_pp']<=zoom_limits['y'][1]]
    for group in range(1,5):
        rs=[r for r in trends if quartiles[r['country']]==group]
        hero.scatter([r['normalized_equivalent_cities_slope_pp'] for r in rs],
            [r['Gini_slope_pp'] for r in rs],s=22,color=quartile_colors[group],
            edgecolors=['black' if r['country'] in selected else 'white' for r in rs],
            linewidths=[.65 if r['country'] in selected else .45 for r in rs],zorder=3)
    # Preserve the largest 15 countries and sample the negative-x range in
    # short intervals. Labels stay in their points' quadrants.
    label_bands=LABEL_BANDS
    q2=[r for r in trends if r['normalized_equivalent_cities_slope_pp']<0 and r['Gini_slope_pp']>0]
    volume_order={r['country']:i for i,r in enumerate(trends)}
    interval_representatives=[]
    for lo,hi in zip(label_bands,label_bands[1:]):
        in_band=[r for r in q2 if lo<=r['normalized_equivalent_cities_slope_pp']<hi]
        if in_band:
            interval_representatives.append(min(in_band,key=lambda r:volume_order[r['country']])['country'])
    major_codes=[r['country'] for r in trends[:15]]
    main_label_positions={
        # Upper-left quadrant: normalized equivalent-city count decreases, Gini increases.
        'UG':(-2.46,1.90),'VN':(-2.12,1.76),'GH':(-1.96,1.43),
        'BD':(-1.42,1.00),'ID':(-1.03,1.11),'IR':(-.54,.615),
        'MA':(.31,-.26)}
    inset_label_positions={
        'CA':(-.174,.175),'FR':(-.030,.133),'ES':(-.082,.122),
        'GB':(-.078,.085),'US':(-.078,.043),'DE':(-.068,.150),
        'IT':(-.132,.019),'CN':(-.066,-.017),'JP':(-.095,-.065),
        'KR':(-.050,-.075),'IN':(.010,.070),'CM':(.046,.048),
        'PL':(-.24,.26),'TR':(-.29,-.09),'RU':(-.03,-.19),'BR':(.10,-.20)}
    leaders={'GB','DE','CN','JP','IN'}
    label_positions=main_label_positions|inset_label_positions
    assert set(label_positions)==set(major_codes)|set(interval_representatives)|{'CM','MA'}|set(selected)
    assert set(inset_label_positions)<={r['country'] for r in zoom_members}
    assert not set(main_label_positions)&{r['country'] for r in zoom_members}
    inset_bounds=[.035,.06,.50,.415]
    inset_underlying_x=[-2.6+3.2*inset_bounds[0],-2.6+3.2*(inset_bounds[0]+inset_bounds[2])]
    inset_underlying_y=[-.35+2.4*inset_bounds[1],-.35+2.4*(inset_bounds[1]+inset_bounds[3])]
    assert not any(inset_underlying_x[0]-.04<r['normalized_equivalent_cities_slope_pp']<inset_underlying_x[1]+.04
        and inset_underlying_y[0]-.03<r['Gini_slope_pp']<inset_underlying_y[1]+.03 for r in trends)
    # Stop the parent reference line at the inset edges instead of retaining
    # an invisible stroke behind inset text in the editable PDF.
    main_zero_line.remove()
    hero.hlines([0,0],[-2.6,inset_underlying_x[1]],[inset_underlying_x[0],.6],
        color=GRAY,linewidth=.65,zorder=1)
    zoom=hero.inset_axes(inset_bounds,zorder=5)
    zoom.set_gid('a_zoom')
    zoom.set_xlim(*zoom_limits['x']);zoom.set_ylim(*zoom_limits['y'])
    zoom.set_facecolor('white')
    for spine in zoom.spines.values():
        spine.set_visible(True);spine.set_linewidth(.55);spine.set_color('#606A74')
    zoom.fill_between([zoom_limits['x'][0],0],0,zoom_limits['y'][1],color=background,
        zorder=0,linewidth=0)
    zoom.axvline(0,color='#A9AFB6',linewidth=.5,zorder=1)
    zoom.axhline(0,xmin=.10,color='#A9AFB6',linewidth=.5,zorder=1)
    zoom.set_xticks([-.25,-.1,0,.1]);zoom.set_yticks([-.15,0,.3])
    zoom.xaxis.set_major_formatter(FormatStrFormatter('%g'))
    zoom.yaxis.set_major_formatter(FormatStrFormatter('%g'))
    zoom.tick_params(axis='both',length=1.8,width=.45,pad=1.8,labelsize=font_size(5.5),colors='black')
    zoom.tick_params(axis='y',direction='in',pad=-3)
    for text in zoom.get_yticklabels():text.set_ha('left')
    for group in range(1,5):
        rs=[r for r in zoom_members if quartiles[r['country']]==group]
        if not rs:continue
        zoom.scatter([r['normalized_equivalent_cities_slope_pp'] for r in rs],
            [r['Gini_slope_pp'] for r in rs],s=13,color=quartile_colors[group],
            edgecolors=['black' if r['country'] in selected else 'white' for r in rs],
            linewidths=[.65 if r['country'] in selected else .4 for r in rs],zorder=3)
    roi=Rectangle((zoom_limits['x'][0],zoom_limits['y'][0]),
        zoom_limits['x'][1]-zoom_limits['x'][0],zoom_limits['y'][1]-zoom_limits['y'][0],
        facecolor='none',edgecolor='#606A74',linewidth=.65,zorder=2)
    hero.add_patch(roi)
    for corner,y in [(0,zoom_limits['y'][0])]:
        connector=ConnectionPatch(xyA=(1,corner),coordsA=zoom.transAxes,
            xyB=(zoom_limits['x'][0],y),coordsB=hero.transData,
            color='#A9AFB6',linewidth=.5,zorder=1.5,clip_on=False)
        hero.add_artist(connector)
    scatter_labels=[]
    for cc,label_xy in main_label_positions.items():
        r=next(r for r in trends if r['country']==cc)
        point=(r['normalized_equivalent_cities_slope_pp'],r['Gini_slope_pp'])
        location='inset' if cc in inset_label_positions else 'main'
        label_axis=zoom if location=='inset' else hero
        arrowprops=(dict(arrowstyle='-',color='#58616A',linewidth=.45 if location=='inset' else .55,
                shrinkA=1.5 if location=='inset' else 3,
                shrinkB=2 if location=='inset' else 2.5,connectionstyle='arc3,rad=0')
            if cc in leaders else None)
        label_axis.annotate(cc,xy=point,xytext=label_xy,fontsize=font_size(5.8) if location=='inset' else font_size(6.8),color='black',
            ha='left',va='center',zorder=2,arrowprops=arrowprops)
        scatter_labels.append(dict(country=cc,point_x=point[0],point_y=point[1],
            label_x=label_xy[0],label_y=label_xy[1],
            major_country=cc in major_codes,interval_representative=cc in interval_representatives,
            display=location,leader=cc in leaders))
    zoom_rows=[dict(country=r['country'],x=r['normalized_equivalent_cities_slope_pp'],y=r['Gini_slope_pp']) for r in zoom_members]
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    tick_obstacles=[Bbox.from_extents(*(text.get_window_extent(renderer).extents*72/fig.dpi))
        for text in zoom.get_yticklabels()]
    moved,inset_label_layout=place_inset_labels(fig,zoom,zoom_rows,list(inset_label_positions),
        6.0 if PROFILE=='manuscript' else 5.5,tick_obstacles)
    for label_row in moved:
        cc=label_row['country'];point=np.array([label_row['point_x'],label_row['point_y']])
        target=zoom.transData.inverted().transform(zoom.transData.transform(point)+
            np.array([label_row['label_x'],label_row['label_y']])*fig.dpi/72)
        inset_label_positions[cc]=tuple(target)
        scatter_labels.append(dict(country=cc,point_x=point[0],point_y=point[1],label_x=float(target[0]),label_y=float(target[1]),
            major_country=cc in major_codes,interval_representative=cc in interval_representatives,
            display='inset',leader=label_row['leader']))
    hero.set_xlabel(r'$\beta_R$ (pp/year)',fontsize=font_size(7),labelpad=5)
    hero.set_ylabel('Annual change in Gini (pp/year)',fontsize=font_size(7),labelpad=5)
    hero.tick_params(axis='both',length=2,width=.45,pad=2.5,labelsize=font_size(6))
    hero.text(-22/hero_size,1+7/hero_size,'a',transform=hero.transAxes,
        fontsize=font_size(9.2),fontweight='bold',ha='left',va='bottom')
    legend_handles=[Line2D([],[],marker='o',linestyle='none',markersize=4,
        markerfacecolor=quartile_colors[q],markeredgewidth=0,label=f'T{q}') for q in range(1,5)]
    quartile_legend=hero.legend(handles=legend_handles,loc='upper right',bbox_to_anchor=(.99,.99),ncol=1,
        fontsize=font_size(5.8),handletextpad=.3,handlelength=.65,
        labelspacing=.45,borderaxespad=0,borderpad=.4,title='Share growth',title_fontsize=font_size(5.8),
        frameon=True,edgecolor='black',facecolor='white',framealpha=1,fancybox=False)
    quartile_legend.get_frame().set_linewidth(.65)
    case_legend=fig.legend(handles=[
        Line2D([],[],color=BLUE,linewidth=1.3,label=LEFT_LEGEND),
        Line2D([],[],color=RED,linewidth=1.3,label='Gini')],
        loc='upper center',bbox_to_anchor=(372.75/width_pt,(height_pt-7)/height_pt),
        ncol=2,fontsize=font_size(6.6),labelcolor='black',handlelength=1.8,handletextpad=.5,
        columnspacing=1.8,borderaxespad=0)
    for i,cc in enumerate(selected):
        row,col=divmod(i,2);letter='bcde'[i]
        ax=fig.add_subplot(grid[row,col+1])
        right=ax.twinx()
        ax.set_gid(letter);right.set_gid(letter+'_gini')
        axes.append(ax);twins.append(right)
        right.patch.set_visible(False)
        right.spines['left'].set_visible(False);right.spines['bottom'].set_visible(False)
        right.spines['right'].set_visible(True)
        right.spines['right'].set_color('black')
        ax.spines['left'].set_color('black');ax.spines['bottom'].set_color('black')
        both=[r for r in metrics if r['country']==cc]
        limits={}
        for metric,axis,color in [(LEFT_METRIC,ax,BLUE),('Gini',right,RED)]:
            ylim,ticks=metric_axis([r[metric] for r in both],metric)
            if metric=='Gini' and len(ticks)>5:ticks=ticks[::2]
            limits[metric]=list(ylim)
            axis.set_ylim(*ylim);axis.set_yticks(ticks)
            step=float(min(np.diff(ticks)))
            decimals=2
            while max(abs(float(f'{tick:.{decimals}f}')-tick) for tick in ticks)>step*1e-6:
                decimals+=1
            axis.yaxis.set_major_formatter(FormatStrFormatter(f'%.{decimals}f'))
            axis.tick_params(axis='y',labelsize=font_size(5.8),length=1.8,width=.45,pad=.5,colors='black')
            rs=sorted(both,key=lambda r:r['year'])
            assert [r['year'] for r in rs]==YEARS
            ys=[r[metric] for r in rs]
            line,=axis.plot(YEARS,ys,color=color,linewidth=1.3,linestyle='-',
                marker='o',markersize=2.6,markevery=MARKER_INDICES,
                markerfacecolor=color,markeredgecolor='white',markeredgewidth=.35,zorder=3)
            assert line.get_linestyle()=='-' and np.array_equal(line.get_ydata(),ys)
            plotted.extend(dict(panel=letter,country=cc,metric=metric,year=y,
                value=float(v),axis='left' if metric==LEFT_METRIC else 'right') for y,v in zip(YEARS,ys))
        ax.set_xlim(1996,2027);ax.set_xticks([1998,2012,2025])
        ax.tick_params(axis='x',length=2,width=.45,pad=2.3,labelsize=font_size(5.8),colors='black')
        ax.set_xlabel('Year',fontsize=font_size(6.4),labelpad=3,color='black')
        ax.set_title(f'T{quartiles[cc]} {NAMES[cc]}',fontsize=font_size(8),fontweight='normal',pad=7)
        if col==0:ax.set_ylabel(r'$R$',fontsize=font_size(7),labelpad=2.5,color='black')
        if col==1:right.set_ylabel('Gini',fontsize=font_size(7),labelpad=3,color='black')
        ax.text(-22/panel_width,1+7/panel_height,letter,transform=ax.transAxes,fontsize=font_size(9.2),fontweight='bold',
            ha='left',va='bottom')
        axis_records.append(dict(panel=letter,country=cc,row=row+1,normalized_equivalent_cities_axis_title=col==0,Gini_axis_title=col==1,
            normalized_equivalent_cities_limits=limits[LEFT_METRIC],
            Gini_limits=limits['Gini'],width_pt=panel_width,height_pt=panel_height))
    fig.canvas.draw()
    inset_footprint=zoom.get_tightbbox(fig.canvas.get_renderer()).transformed(fig.dpi_scale_trans.inverted())
    inset_footprint_pt=[float(v*72) for v in inset_footprint.extents]
    nearest_point_clearance=min(float(np.hypot(
        max(inset_footprint_pt[0]-hero.transData.transform((r['normalized_equivalent_cities_slope_pp'],r['Gini_slope_pp']))[0]*72/fig.dpi,
            0,hero.transData.transform((r['normalized_equivalent_cities_slope_pp'],r['Gini_slope_pp']))[0]*72/fig.dpi-inset_footprint_pt[2]),
        max(inset_footprint_pt[1]-hero.transData.transform((r['normalized_equivalent_cities_slope_pp'],r['Gini_slope_pp']))[1]*72/fig.dpi,
            0,hero.transData.transform((r['normalized_equivalent_cities_slope_pp'],r['Gini_slope_pp']))[1]*72/fig.dpi-inset_footprint_pt[3])))
        -np.sqrt(22)/2-.325 for r in trends)
    # At least 1.5 pt of white space remains beyond every full marker outline.
    assert nearest_point_clearance>1.5, nearest_point_clearance
    apply_axes_typography(fig,grid_json_out=QA/'grid.json')
    # Keep the math subscript above the final 5-pt glyph floor.
    if PROFILE=='journal':hero.xaxis.label.set_fontsize(7.5)
    fig.canvas.draw()
    legend_bottom=quartile_legend.get_window_extent(fig.canvas.get_renderer()).y0-4*fig.dpi/72
    fraction=(legend_bottom-hero.get_window_extent().y0)/hero.get_window_extent().height
    vertical_guide.set_ydata([0,max(0,min(.98,float(fraction)))])
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',
        tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True,
        axes=axes+[zoom],exemptions=[dict(panels=['a_zoom'],checks=['all'],
            reason='Nested magnification of the marked a-panel region; inset is not a comparable cell of the primary five-panel grid.')])
    for r in trends:
        xy=hero.transData.transform((r['normalized_equivalent_cities_slope_pp'],r['Gini_slope_pp']))
        r.update(pdf_x_pt=float(xy[0]/fig.dpi*72),pdf_y_pt=float(height_pt-xy[1]/fig.dpi*72))
    write_csv('Fig4_country_concentration_trends.csv',trends)
    zoom_data=[]
    for r in zoom_members:
        xy=zoom.transData.transform((r['normalized_equivalent_cities_slope_pp'],r['Gini_slope_pp']))
        zoom_data.append(dict(country=r['country'],point_x=r['normalized_equivalent_cities_slope_pp'],
            point_y=r['Gini_slope_pp'],category=r['category'],labelled=r['country'] in inset_label_positions,
            pdf_x_pt=float(xy[0]/fig.dpi*72),pdf_y_pt=float(height_pt-xy[1]/fig.dpi*72)))
    write_csv('Fig4_zoom_points.csv',zoom_data)
    write_csv('Fig4_scatter_country_labels.csv',scatter_labels)
    write_csv('Fig4_plotted_values.csv',plotted)
    stem=OUT/'Fig4'
    fig.savefig(stem.with_suffix('.pdf'))
    fig.savefig(stem.with_suffix('.svg'))
    png_buffer=BytesIO();fig.savefig(png_buffer,format='png',dpi=600)
    stem.with_suffix('.png').write_bytes(png_buffer.getvalue())
    with pymupdf.open(stem.with_suffix('.pdf')) as doc:
        page=doc[0]
        page.get_pixmap(matrix=pymupdf.Matrix(2.6,2.6),alpha=False).save(QA/'preview.png')
        fonts=sorted({f[3] for f in page.get_fonts()})
        for i,a in enumerate(axes):
            b=a.get_position();clip=pymupdf.Rect(b.x0*width_pt-34,
                height_pt-b.y1*height_pt-26,b.x1*width_pt+35,height_pt-b.y0*height_pt+35)
            page.get_pixmap(matrix=pymupdf.Matrix(3.2,3.2),clip=clip,alpha=False).save(QA/f'preview_{"abcde"[i]}.png')
        b=zoom.get_position()
        clip=pymupdf.Rect(b.x0*width_pt-17,height_pt-b.y1*height_pt-8,
            b.x1*width_pt+5,height_pt-b.y0*height_pt+15)
        page.get_pixmap(matrix=pymupdf.Matrix(5,5),clip=clip,alpha=False).save(QA/'preview_a_zoom.png')
    manifest=dict(figure='Fig4',edition='v3',archetype='quantitative grid',
        claim='63 of the fixed 76 countries have declining normalized equivalent city count and increasing Gini across 1998–2025; four country histories display these same two metrics',
        dimensions_mm=[180,100],fonts_pdf=fonts,layout='Square scatter hero spanning two rows at left; four square histories in a 2x2 grid at right',
        selected_countries=selected,
        selection_rule='Keep all 76 countries in panel a. Panels b-e show one sufficiently observed case from each Fig5 quartile: United States, Poland, Brazil and India. Selection uses volume thresholds and complete trajectories, not endpoint differences.',
        case_volume_thresholds=dict(total_domestic_events=CASE_MIN_TOTAL,minimum_events_every_year=CASE_MIN_ANNUAL,minimum_cities_every_year=CASE_MIN_CITIES),
        case_selection=case_selection,
        selection_scope='Prevalence is calculated using all 76 countries, never the four illustrative cases',
        geographical_scope='Domestic intercity flows determine axes; international share-growth quartiles determine point colours',
        years=YEARS,source_tier='Annual top100pct; all fields aggregated once',
        input=str(CANONICAL.relative_to(ROOT)),input_sha256=sha256(CANONICAL),
        source_rows=len(metrics),plotted_values=len(plotted),curves=8,scatter_points=len(trends),
        scatter=dict(x='OLS slope of 1 / (N * HHI), multiplied by 100',y='OLS slope of Gini, multiplied by 100',
            slope_unit='percentage points per year',years=28,scales='linear',
            xlim=[-2.6,.6],ylim=[-.35,2.05],point_size_pt2=22,
            color_encoding='Exact Fig5 international-share growth quartile, independent of domestic trend quadrant',
            quartile_colors={f'T{q}':color for q,color in quartile_colors.items()},
            quartile_membership=quartiles,quartile_summary=quartile_summary,
            group_source=str(group_source.relative_to(ROOT)),group_source_sha256=sha256(group_source),
            background=dict(color=background,region='Upper-left quadrant: R trend negative and Gini trend positive'),
            criterion='Relative concentration: x < 0 and y > 0; deconcentration: x > 0 and y < 0; mixed changes: other sign combinations',
            labelled_countries=list(label_positions),
            major_country_codes=major_codes,interval_representatives=interval_representatives,
            annotation_x_band_edges=label_bands,
            major_country_annotation_rule='Label all of the largest 15 cumulative domestic-flow countries. In each negative-x interval select the country with highest cumulative domestic events among T2 points. Add CM, MA and all four case countries. Text stays in the same quadrant as its point.',
            label_style='Country codes use nearby collision-free positions and short leaders as needed; labels remain in their point quadrants',
            leader_countries=sorted(r['country'] for r in scatter_labels if r['leader']),
            label_spacing_rule='Main and inset labels sit close to their points; labels within the magnified region appear only in the inset'),
        zoom=dict(xlim=zoom_limits['x'],ylim=zoom_limits['y'],parent='a',axes_id='a_zoom',
            bounds_parent_axes=inset_bounds,point_count=len(zoom_members),
            labelled_countries=list(inset_label_positions),main_labels=list(main_label_positions),
            marker_size_pt2=13,scale='linear; same data values and units as the parent',
            main_roi_rectangle=True,connectors=1,footprint_bbox_pt=inset_footprint_pt,
            minimum_main_marker_edge_clearance_pt=nearest_point_clearance),
        inset_label_layout=inset_label_layout,
        metrics=dict(normalized_equivalent_cities='1 / (N * HHI), with N the number of positive combined-strength cities',Gini='Uncorrected Gini over cities with positive combined domestic strength'),
        displayed_symbols=dict(R='Normalized equivalent city count',beta_R='Fitted annual trend in R, displayed in percentage points per year'),
        combined_city_strength='Domestic inflow plus outflow for the same stable city ID; normalize by the sum of combined city strengths (twice the number of domestic events); indices are computed after combining, never averaged across directions',
        city_scope='Union of positive domestic inflow and outflow cities in each country-year, using cleaned stable city IDs',
        axis_rule='Normalized equivalent city count left, Gini right; independent country-specific limits and ticks; left metric titles only on the far-left case plots and Gini titles only on the far-right case plots; axes, ticks and metric titles black; one shared metric legend above panels b-e',
        palette=dict(normalized_equivalent_cities=BLUE,Gini=RED),line_rule='Two solid lines per country; no directional subdivision',
        marker_years=[YEARS[i] for i in MARKER_INDICES],markers_are_subsampled_but_lines_use_all_annual_values=True,
        axis_records=axis_records,all_country_trend_audit=checks,
        statistics='Hero: ordinary least-squares slopes fitted to all 28 annual observations, descriptive sign classification without significance claims. Cases: raw annual indices, no smoothing or uncertainty bands.',
        source_data=['Fig4_country_selection.csv','Fig4_domestic_city_margins.csv',
            'Fig4_domestic_country_metrics.csv','Fig4_all_country_combined_metrics.csv','Fig4_plotted_values.csv',
            'Fig4_country_concentration_trends.csv','Fig4_scatter_country_labels.csv','Fig4_zoom_points.csv',
            'Fig4_case_selection.csv','Fig4_case_period_summary.csv',
            'Fig4_Fig5_quartile_membership.csv','Fig4_quartile_concentration_summary.csv','Fig4_quartile_case_candidates.csv'],
        historical_case_selection_tables=['Fig4_quadrant_case_selection.csv','Fig4_diagonal_case_selection.csv'])
    manifest['formatting']=specification()
    (QA/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    plt.close(fig)
    print(json.dumps(dict(outputs=[str(stem.with_suffix(s)) for s in ['.pdf','.svg','.png']],
        selected_countries=selected,dimensions_mm=[180,100],plotted_values=len(plotted),
        all_country_trend_audit=checks),ensure_ascii=False))


if __name__=='__main__':
    main()
