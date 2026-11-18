"""Fig3: international share trajectories, share increases and HHI contributions."""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=(Path(__file__).resolve().parents[2]);V3=ROOT/'figures/v3'
sys.path[:0]=[str(V3),str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa')]
from figure_style import (
    ANNUAL_LINEWIDTH_PT, ANNUAL_MARKER_EDGE_PT, ANNUAL_MARKER_PT,
    AXIS_LINEWIDTH_PT, COUNTRY_POINT_ALPHA, COUNTRY_POINT_EDGE_PT, COUNTRY_POINT_PT2,
    REFERENCE_COLOUR, REFERENCE_LINESTYLE, REFERENCE_LINEWIDTH_PT,
    TICK_LINEWIDTH_PT, WIDTH_PT, apply_axes_typography,
    font_size, specification,
)
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.legend_handler import HandlerTuple
import pymupdf
from audit_panel_alignment import require_matplotlib_panel_alignment

OUT=ROOT/'outputs/figure_revision_20261111/artwork';DATA=OUT/'source_data';QA=OUT.parent/'QA/Fig3'
CLEAN=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis'
CANONICAL=CLEAN/'flow_top100.parquet'
FIG5_GROUPS=(Path(__file__).resolve().parents[2] / 'outputs/results_network_revision_20261030/artwork/source_data/trajectory_membership.csv')
SNAPSHOTS=[1998,2007,2016,2025];GROUP_COLORS=['#7E99F4', '#A5AEB7', '#7AB656', '#CC7C71']
GROUP_MARKERS = {1: '^', 2: 'o', 3: 's', 4: 'D'}
LINE_YLIM=(0.,1.5)
MEDIAN_MARKER_PT=5.6
LINE_YTICKS=[0.,.3,.6,.9,1.2,1.5]
TOTAL_COLORS=GROUP_COLORS+['#EDF0F3'];TOTAL_ALPHAS=[.18]*4+[1.]
GROUP_LABELS = ('T1', 'T2', 'T3', 'T4', 'Others')
POINT_COLOURS = [*GROUP_COLORS, '#78838D']


def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def write(name,rows):
    assert rows
    with (DATA/name).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,list(rows[0]));writer.writeheader();writer.writerows(rows)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare():
    observations=read(ROOT/'figures/v4/source_data/Fig3_combined_country_year_data.csv')
    for r in observations:
        for k in list(r):
            if k!='country':r[k]=int(r[k]) if k=='year' else float(r[k])
    metrics=read(ROOT/'figures/v4/source_data/Fig3_combined_country_metrics.csv')
    for r in metrics:
        for k in list(r):r[k]=int(r[k]) if k in ['year','countries'] else float(r[k])
    lorenz=read(ROOT/'figures/v4/source_data/Fig3_combined_lorenz_curves.csv')
    groups=[]
    for r in read(FIG5_GROUPS):
        groups.append(dict(country=r['country'],group=int(r['group']),international_share_log_slope=float(r['international_share_log_slope']),international_share_annual_rate_pct=float(r['international_share_annual_rate_pct'])))
    assert [sum(r['group']==g for r in groups) for g in range(1,5)]==[15,14,24,23]
    quartile_rows=[];stats=[]
    for year in range(1998,2026):
        total=next(r['combined_flow_endpoints'] for r in metrics if r['year']==year)
        for r in groups:
            events=next(v['combined_flow'] for v in observations if v['country']==r['country'] and v['year']==year)
            quartile_rows.append(dict(country=r['country'],group=r['group'],year=year,country_combined_flow=events,global_combined_flow=total,share_percent=100*events/total))
        for group in range(1,5):
            values=np.asarray([r['share_percent'] for r in quartile_rows if r['year']==year and r['group']==group])
            q1,median,q3=np.percentile(values,[25,50,75]);iqr=q3-q1;low=min(values[values>=q1-1.5*iqr]);high=max(values[values<=q3+1.5*iqr])
            stats.append(dict(group=group,year=year,countries=len(values),q1=float(q1),median=float(median),q3=float(q3),whisker_low=float(low),whisker_high=float(high),minimum=float(min(values)),maximum=float(max(values)),outlier_count=int(sum((values<low)|(values>high)))))
    from matplotlib.ticker import MaxNLocator
    ticks=MaxNLocator(nbins=5,steps=[1,2,2.5,5,10]).tick_values(0,max(r['median'] for r in stats)*1.08)
    globals()['LINE_YLIM']=(0.,float(ticks[-1]));globals()['LINE_YTICKS']=ticks.tolist()
    cuts=np.array([np.median([r['international_share_annual_rate_pct'] for r in groups if r['international_share_annual_rate_pct']<0]),0.,np.median([r['international_share_annual_rate_pct'] for r in groups if r['international_share_annual_rate_pct']>0])])
    write('Fig3_combined_country_year_data.csv',observations);write('Fig3_combined_country_metrics.csv',metrics)
    write('Fig3_combined_lorenz_curves.csv',lorenz);write('Fig3_Fig5_quartile_membership.csv',groups)
    write('Fig3_quartile_annual_shares.csv',quartile_rows);write('Fig3_quartile_box_statistics.csv',stats)
    return observations,metrics,lorenz,groups,quartile_rows,stats,cuts


def group_total_shares(observations,groups):
    cohort={r['country']:r['group'] for r in groups};rows=[]
    labels=['T1','T2','T3','T4','Others'];codes=[1,2,3,4,0]
    membership=[dict(country=cc,group=cohort.get(cc,0),category='T'+str(cohort[cc]) if cc in cohort else 'Others')
        for cc in sorted({r['country'] for r in observations})]
    for year in range(1998,2026):
        rs=[r for r in observations if r['year']==year];total=sum(r['combined_flow'] for r in rs);lower=0.
        for order,(code,label) in enumerate(zip(codes,labels)):
            selected=[r for r in rs if cohort.get(r['country'],0)==code]
            events=sum(r['combined_flow'] for r in selected);share=100*events/total
            rows.append(dict(year=year,group=code,category=label,stack_order=order,countries=len(selected),
                combined_flow=events,global_combined_flow=total,share_percent=share,lower_percent=lower,upper_percent=lower+share))
            lower+=share
        assert abs(lower-100)<1e-10 and sum(r['combined_flow'] for r in rows if r['year']==year)==total
    write('Fig3_group_total_annual_shares.csv',rows);write('Fig3_group_total_country_membership.csv',membership)
    return rows


def fixed_country_distribution(observations):
    """Hold membership fixed; retain each member's full international margins."""
    study_years=set(range(1998,2026))
    recorded={cc:{r['year'] for r in observations if r['country']==cc and r['combined_flow']>0}
        for cc in sorted({r['country'] for r in observations})}
    cohort={cc for cc,years in recorded.items() if years==study_years}
    assert len(cohort)==203
    membership=[dict(country=cc,included=int(cc in cohort),observed_years=len(years),
        first_year=min(years),last_year=max(years),
        rule='Positive combined international flow in every study year') for cc,years in recorded.items()]
    rows=[];metrics=[];lorenz=[]
    for year in sorted(study_years):
        worldwide=[r for r in observations if r['year']==year]
        selected=sorted([r for r in worldwide if r['country'] in cohort],key=lambda r:r['combined_flow'])
        assert len(selected)==len(cohort) and {r['country'] for r in selected}==cohort
        total=sum(r['combined_flow'] for r in selected);world=sum(r['combined_flow'] for r in worldwide)
        shares=np.asarray([r['combined_flow']/total for r in selected]);n=len(shares)
        assert np.all(shares>0) and abs(sum(shares)-1)<1e-12
        x=np.arange(n+1)/n;y=np.r_[0,np.cumsum(shares)];y[-1]=1.
        hhi=float(sum(shares**2));gini=float(1-2*np.trapezoid(y,x))
        metrics.append(dict(year=year,countries=n,fixed_country_combined_flow=total,
            global_combined_flow=world,global_flow_coverage=total/world,HHI=hhi,Gini=gini,
            equivalent_countries=1/hhi,normalized_equivalent_countries=1/(n*hhi)))
        rows.extend(dict(year=year,country=r['country'],inflow=r['inflow'],outflow=r['outflow'],
            combined_flow=r['combined_flow'],fixed_country_combined_flow=total,global_combined_flow=world,
            fixed_share=float(p),fixed_share_percent=float(100*p),global_share=r['share'])
            for r,p in zip(selected,shares))
        if year in SNAPSHOTS:
            codes=['']+[r['country'] for r in selected]
            lorenz.extend(dict(year=year,rank=i,country_at_rank=cc,countries=n,
                cumulative_country_percent=float(a*100),cumulative_flow_percent=float(b*100),sample='fixed_203')
                for i,(cc,a,b) in enumerate(zip(codes,x,y)))
    write('Fig3_fixed_country_membership.csv',membership)
    write('Fig3_fixed_country_year_data.csv',rows)
    write('Fig3_fixed_country_metrics.csv',metrics)
    write('Fig3_fixed_country_lorenz_curves.csv',lorenz)
    return rows,metrics,lorenz,membership


def summarize_hhi_change(observations, metrics, groups):
    """Sum squared worldwide country shares by year and trajectory group."""
    membership = {row['country']: f"T{row['group']}" for row in groups}
    years = [row['year'] for row in metrics]
    assert years == list(range(1998, 2026))
    totals = {row['year']: row['combined_flow_endpoints'] for row in metrics}
    contributions = {year: dict.fromkeys(GROUP_LABELS, 0.) for year in years}
    for row in observations:
        year = row['year']
        group = membership.get(row['country'], 'Others')
        contributions[year][group] += (row['combined_flow'] / totals[year]) ** 2

    baseline = contributions[years[0]]
    initial_hhi = metrics[0]['HHI']
    annual = []
    for year, metric in zip(years, metrics):
        changes = {group: contributions[year][group] - baseline[group] for group in GROUP_LABELS}
        assert np.isclose(sum(changes.values()), metric['HHI'] - initial_hhi, rtol=0, atol=1e-12)
        annual.extend(dict(year=year, group=group, HHI_contribution=contributions[year][group],
                           change_since_1998=changes[group]) for group in GROUP_LABELS)
    final = contributions[years[-1]]
    endpoints = [dict(group=group, initial_HHI=baseline[group], final_HHI=final[group],
                      change_HHI=final[group] - baseline[group]) for group in GROUP_LABELS]
    write('Fig3_HHI_group_annual.csv', annual)
    write('Fig3_HHI_group_changes.csv', endpoints)
    return annual, dict(endpoint_years=[years[0], years[-1]], initial_HHI=initial_hhi,
                        final_HHI=metrics[-1]['HHI'], worldwide_change_HHI=metrics[-1]['HHI'] - initial_hhi,
                        display_multiplier=1000, groups=endpoints)


def draw_country_share_changes(ax, observations, groups):
    """Show initial shares and signed endpoint changes for all 76 grouped countries."""
    endpoints = {
        year: {row['country']: 100 * row['share'] for row in observations if row['year'] == year}
        for year in (1998, 2025)
    }
    points = []
    for row in groups:
        country = row['country']
        initial = endpoints[1998][country]
        final = endpoints[2025][country]
        points.append(dict(country=country, group=f"T{row['group']}", initial_share_pct=initial,
                           final_share_pct=final, change_pp=final - initial))
    assert len(points) == len({row['country'] for row in points}) == 76
    assert all(row['initial_share_pct'] > 0 for row in points)
    write('Fig3_country_share_changes_plotted.csv', points)

    ax.set_xscale('log')
    ax.set_yscale('symlog', linthresh=.1)
    ax.set(xlim=(.012, 40), ylim=(-10, 10))
    ax.set_xticks([.02, .1, 1, 10], ['0.02', '0.1', '1', '10'])
    ax.set_yticks([-5, -1, -.1, 0, .1, 1, 5], ['−5', '−1', '−0.1', '0', '0.1', '1', '5'])
    ax.minorticks_off()
    ax.set_xlabel('Initial Share (%)', labelpad=4)
    ax.set_ylabel('Share Change (pp)', labelpad=4)
    ax.axhline(0, color=REFERENCE_COLOUR, linewidth=REFERENCE_LINEWIDTH_PT,
               linestyle=REFERENCE_LINESTYLE, zorder=1)

    for group, colour in zip(GROUP_LABELS[:4], GROUP_COLORS):
        members = [row for row in points if row['group'] == group]
        coordinates = np.array([(row['initial_share_pct'], row['change_pp']) for row in members])
        ax.scatter(*coordinates.T, s=COUNTRY_POINT_PT2, color=colour, edgecolors='white',
                   linewidths=COUNTRY_POINT_EDGE_PT, alpha=COUNTRY_POINT_ALPHA, zorder=3)
    return dict(countries=len(points), x_scale='log', y_scale='symlog',
                y_linear_threshold_pp=.1,
                group_sizes={group: sum(row['group'] == group for row in points)
                             for group in GROUP_LABELS[:4]})


def draw_hhi_trajectories(ax, annual, multiplier):
    """Trace the contributions to worldwide HHI change from the 1998 baseline."""
    ax.axhline(0, color=REFERENCE_COLOUR, linewidth=REFERENCE_LINEWIDTH_PT,
               linestyle=REFERENCE_LINESTYLE, zorder=1)
    ax.set(xlim=(1997, 2026), ylim=(-34, 14))
    ax.set_xticks([1998, 2012, 2025])
    ax.set_yticks([-30, -20, -10, 0, 10])
    ax.set_xlabel('Year', labelpad=4)
    ax.set_ylabel(r'HHI Contribution Change ($10^{-3}$)', labelpad=4)
    label_offsets = {'T4': 3., 'Others': -4.}
    for group, colour in zip(GROUP_LABELS, POINT_COLOURS):
        rows = [row for row in annual if row['group'] == group]
        years = [row['year'] for row in rows]
        changes = [multiplier * row['change_since_1998'] for row in rows]
        ax.plot(years, changes, color=colour, linewidth=ANNUAL_LINEWIDTH_PT,
                marker='o', markersize=ANNUAL_MARKER_PT, markeredgecolor='white',
                markeredgewidth=ANNUAL_MARKER_EDGE_PT, markevery=[0, 7, 14, 21, 27],
                zorder=2 if group == 'Others' else 3)
        ax.annotate(group, (years[-1], changes[-1]), xytext=(5, label_offsets.get(group, 0.)),
                    textcoords='offset points', ha='left', va='center', annotation_clip=False)


def main():
    DATA.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    observations,metrics,lorenz,groups,quartile_rows,stats,cuts=prepare()
    fixed_rows,fixed_metrics,fixed_lorenz,fixed_membership=fixed_country_distribution(observations)
    totals=group_total_shares(observations,groups)
    assert min(r['median'] for r in stats)>LINE_YLIM[0] and max(r['median'] for r in stats)<LINE_YLIM[1]
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica'],'font.size':font_size(7),
        'axes.labelsize':font_size(8),'xtick.labelsize':font_size(6.5),'ytick.labelsize':font_size(7),'axes.linewidth':AXIS_LINEWIDTH_PT,
        'axes.spines.top':False,'axes.spines.right':False,'axes.labelcolor':'black','text.color':'black','xtick.color':'black',
        'ytick.color':'black','axes.unicode_minus':False,'legend.frameon':False,'pdf.use14corefonts':False,
        'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white','path.simplify':False})
    left_margin=44.;right_margin=40.;column_gap=78.;row_gap=48.;bottom=38.;top_margin=33.
    small=(WIDTH_PT-left_margin-right_margin-column_gap-row_gap)/3;large=2*small+row_gap;height=bottom+large+top_margin
    fig=plt.figure(figsize=(WIDTH_PT/72,height/72),dpi=300)
    grid=fig.add_gridspec(2,2,left=left_margin/WIDTH_PT,right=(WIDTH_PT-right_margin)/WIDTH_PT,
        bottom=bottom/height,top=(bottom+large)/height,width_ratios=[large,small],
        wspace=column_gap/((large+small)/2),hspace=row_gap/small)
    a=fig.add_subplot(grid[:,0]);a.set_gid('a');a.set_box_aspect(1)
    right_left=left_margin+large+column_gap
    right_width=108.
    b=fig.add_axes([right_left/WIDTH_PT, (bottom+small+row_gap)/height, right_width/WIDTH_PT, small/height]);b.set_gid('b')
    c=fig.add_axes([right_left/WIDTH_PT, bottom/height, right_width/WIDTH_PT, small/height]);c.set_gid('c')
    for ax in (a,b,c):
        ax.tick_params(length=2.5,width=TICK_LINEWIDTH_PT,pad=3)
        ax.annotate(ax.get_gid(),xy=(0,1),xycoords='axes fraction',xytext=(-28 if ax is a else -18,7),textcoords='offset points',
            ha='left',va='bottom',fontsize=font_size(10),fontweight='bold')
    share_axis=a.twinx();share_axis.set_gid('a_share');share_axis.set_zorder(a.get_zorder()-1)
    a.patch.set_visible(False);share_axis.spines['right'].set_visible(True);share_axis.spines['left'].set_visible(False)
    share_axis.spines['bottom'].set_visible(False);share_axis.spines['top'].set_visible(False)
    share_axis.set(ylim=(0,100));share_axis.set_yticks([0,20,40,60,80,100])
    share_axis.set_ylabel('Group Share (%)',labelpad=5);share_axis.tick_params(length=2.5,width=TICK_LINEWIDTH_PT,pad=3)
    band_vertices=[]
    for order,(color,alpha) in enumerate(zip(TOTAL_COLORS,TOTAL_ALPHAS)):
        rs=sorted([r for r in totals if r['stack_order']==order],key=lambda r:r['year'])
        share_axis.fill_between([r['year'] for r in rs],[r['lower_percent'] for r in rs],[r['upper_percent'] for r in rs],
            facecolor=mpl.colors.to_rgba(color,alpha),edgecolor='white',linewidth=.45,zorder=1)
        band_vertices.extend(dict(r,panel='a_share',color=color,fill_alpha=alpha) for r in rs)
    median_lines=[]
    group_handles=[]
    for group,color in enumerate(GROUP_COLORS,1):
        for year in range(1998,2026):
            s=next(r for r in stats if r['group']==group and r['year']==year)
            median_lines.append(dict(panel='a',group=group,year=year,x=float(year),y=s['median'],color=color))
        line=[r for r in median_lines if r['group']==group]
        median_line, = a.plot([r['x'] for r in line],[r['y'] for r in line],color=color,linewidth=ANNUAL_LINEWIDTH_PT,
            marker=GROUP_MARKERS[group],markersize=MEDIAN_MARKER_PT,markeredgecolor='white',
            markeredgewidth=.5,zorder=4)
        group_handles.append((Patch(facecolor=mpl.colors.to_rgba(color,.18),edgecolor='none'), median_line))
    a.set_yscale('linear');a.set(xlim=(1997.25,2025.75),ylim=LINE_YLIM)
    a.set_xticks([1998,2005,2012,2019,2025]);a.set_yticks(LINE_YTICKS,[f'{v:g}' for v in LINE_YTICKS]);a.minorticks_off()
    a.set_xlabel('Year',labelpad=5);a.set_ylabel('Median Country Share (%)',labelpad=5)
    group_handles.append(Patch(facecolor=TOTAL_COLORS[-1],edgecolor='none'))
    fig.legend(handles=group_handles,labels=['T1','T2','T3','T4','Others'],handler_map={tuple:HandlerTuple(ndivide=1)},
        loc='upper center',bbox_to_anchor=((left_margin+large/2)/WIDTH_PT,(height-8)/height),ncol=5,fontsize=font_size(6.3),
        handlelength=1.5,handletextpad=.5,columnspacing=1.25,borderaxespad=0)
    hhi_annual,hhi_change=summarize_hhi_change(observations,metrics,groups)
    country_share_changes=draw_country_share_changes(b,observations,groups)
    draw_hhi_trajectories(c,hhi_annual,hhi_change['display_multiplier'])
    apply_axes_typography(fig,grid_json_out=QA/'grid.json');fig.canvas.draw()
    for r in median_lines:
        xy=a.transData.transform((r['x'],r['y']))/fig.dpi*72
        r.update(pdf_x_pt=float(xy[0]),pdf_y_pt=float(height-xy[1]))
    for r in band_vertices:
        for boundary in ['lower','upper']:
            xy=share_axis.transData.transform((r['year'],r[boundary+'_percent']))/fig.dpi*72
            r['pdf_x_pt']=float(xy[0]);r['pdf_'+boundary+'_y_pt']=float(height-xy[1])
    write('Fig3_quartile_median_lines.csv',median_lines)
    write('Fig3_group_total_band_vertices.csv',band_vertices)
    renderer=fig.canvas.get_renderer();scale=72/fig.dpi
    label_boxes={name:(text.get_window_extent(renderer).extents*scale).tolist()
        for name,text in [('a_right',share_axis.yaxis.label),('c_left',c.yaxis.label)]}
    clearances=dict(b_left=b.get_tightbbox(renderer).x0*scale-label_boxes['a_right'][2],
                    c_left=label_boxes['c_left'][0]-label_boxes['a_right'][2])
    assert min(clearances.values())>=8.,clearances
    require_matplotlib_panel_alignment(fig,json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',
        tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True,exclude_axes=[share_axis],
        row_groups=[],column_groups=[['b','c']])
    stem=OUT/'Fig3';fig.savefig(stem.with_suffix('.pdf'));fig.savefig(stem.with_suffix('.svg'));fig.savefig(stem.with_suffix('.png'),dpi=600)
    with pymupdf.open(stem.with_suffix('.pdf')) as doc:
        page=doc[0];page.get_pixmap(matrix=pymupdf.Matrix(2.4,2.4),alpha=False).save(QA/'preview.png')
        dimensions=[page.rect.width*25.4/72,page.rect.height*25.4/72]
    manifest=dict(figure='Fig3',edition='v4',archetype='quantitative grid',dimensions_mm=dimensions,
        claim='Show group share trajectories, the concentration of positive endpoint changes and group contributions to worldwide HHI change.',
        input=str(CANONICAL.relative_to(ROOT)),input_sha256=sha(CANONICAL),Fig5_group_input=str(FIG5_GROUPS.relative_to(ROOT)),Fig5_group_sha256=sha(FIG5_GROUPS),
        aggregation='Country annual combined_flow = international inflow + outflow. The HHI decomposition in c uses worldwide shares in each year.',
        unique_international_events=11529374,combined_endpoint_total=sum(r['combined_flow_endpoints'] for r in metrics),
        worldwide_country_union=len({r['country'] for r in observations}),worldwide_country_years=len(observations),
        panels=dict(a='Four median country-share lines on the left linear 0-1.5 percent axis, over worldwide display-group total stacked shares on the right linear 0-100 percent axis; Others completes 100 percent',
            b='1998 share and 1998–2025 percentage-point share change for all 76 countries in T1–T4',
            c='Annual changes from 1998 in each group’s contribution to worldwide HHI'),
        fixed_country_cohort=dict(countries=203,country_years=len(fixed_rows),excluded_countries=21,
            rule='Positive combined international inflow plus outflow in all 28 years; no volume threshold',
            membership='Same 203 country members in every year; no rank axis is displayed',
            denominator='Sum of combined country margins of the same fixed 203 countries in each year',
            flow_scope='Full international margins of included countries, including their links with excluded countries',
            global_flow_coverage_by_year={r['year']:r['global_flow_coverage'] for r in fixed_metrics},
            minimum_global_flow_coverage=min(r['global_flow_coverage'] for r in fixed_metrics),
            first_last_metrics=[fixed_metrics[0],fixed_metrics[-1]],
            annual_HHI_Gini='Fixed and worldwide annual Gini plotted in Fig2b. The annual HHI series are retained in source data.'),
        grouping=dict(source='Exact Fig5 T1-T4 memberships independently recomputed from cleaned 28-year shares',quartile_cuts_pct_per_year=cuts.tolist(),countries_per_group=[15,14,24,23],
            annual_share='Country combined events / global combined events in the same year',years=list(range(1998,2026)),
            interpretation='Descriptive growth strata. Overall concentration is quantified in Fig2b and Fig3c.'),
        lineplot=dict(countries=76,country_year_observations=2128,annual_medians=112,boxes=0,whiskers=0,yscale='linear',ylim=LINE_YLIM,yticks=LINE_YTICKS,
            xlim=[1997.25,2025.75],centre='Median of the country shares in each display group, not the group total share',
            group_colours=dict(zip(['T1','T2','T3','T4'],GROUP_COLORS)),within_year_offsets=[0.,0.,0.,0.],
            median_lines='All 28 annual medians per group connected directly at the actual year; T1 triangles, T2 circles, T3 squares, T4 diamonds; no smoothing',
            median_linewidth_pt=ANNUAL_LINEWIDTH_PT,
            median_markers={f'T{group}': marker for group, marker in GROUP_MARKERS.items()},
            median_marker_size_pt=MEDIAN_MARKER_PT,
            axis_range_reason='Tighten to 0-1.5 percent and use equal 0.3-percentage-point intervals; observed median range 0.10335-1.30466 percent is fully visible'),
        stackplot=dict(yscale='linear',ylim=[0,100],yticks=[0,20,40,60,80,100],categories=['T1','T2','T3','T4','Others'],
            fills=dict(zip(['T1','T2','T3','T4','Others'],TOTAL_COLORS)),alphas=TOTAL_ALPHAS,annual_values=140,
            denominator='Worldwide combined inflow and outflow, including countries outside the 76-country cohort',
            membership='Exact Fig5 T1-T4 memberships; Others is the disjoint complement among all worldwide countries',
            interpretation='Band thickness represents group total share on the right axis; fills are not confidence bands',
            all_categories_sum_to_100_each_year=True),
        geometry=dict(left_square_pt=large,right_width_pt=right_width,right_height_pt=small,column_gap_pt=column_gap,
            y_axis_title_boxes_pt=label_boxes,horizontal_title_clearances_pt=clearances),
        alignment_exclusions=[dict(axis='a_share',reason='Secondary group-total share scale sharing the a plot rectangle')],
        a_share_bbox_pt=(share_axis.get_window_extent().extents/fig.dpi*72).tolist(),
        main_axes=3,secondary_axes=1,country_share_changes=country_share_changes,hhi_change=hhi_change,
        annual_metric_style=dict(panel='c',linewidth_pt=ANNUAL_LINEWIDTH_PT,marker='o',marker_diameter_pt=ANNUAL_MARKER_PT),
        exclusions='Panel a medians use 76 countries. Its stacked areas include the whole world. Panel b uses all 76 countries with trajectory assignments, including those with negative changes. Panel c includes all countries with recorded flows in each year.',
        source_data=['Fig3_combined_country_year_data.csv','Fig3_combined_country_metrics.csv','Fig3_combined_lorenz_curves.csv',
            'Fig3_Fig5_quartile_membership.csv','Fig3_quartile_annual_shares.csv','Fig3_quartile_box_statistics.csv',
            'Fig3_quartile_median_lines.csv',
            'Fig3_group_total_annual_shares.csv','Fig3_group_total_country_membership.csv','Fig3_group_total_band_vertices.csv',
            'Fig3_fixed_country_membership.csv','Fig3_fixed_country_year_data.csv','Fig3_fixed_country_metrics.csv','Fig3_fixed_country_lorenz_curves.csv',
            'Fig3_HHI_group_changes.csv','Fig3_HHI_group_annual.csv','Fig3_country_share_changes_plotted.csv'],
        auxiliary_data='Country quartiles/whiskers and raw worldwide/fixed-country Lorenz tables remain for provenance; no Lorenz curve is displayed.',
        uncertainty='Descriptive annual medians and stacked total shares; no spread/confidence bands or p-values claimed.',formatting=specification())
    (QA/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    plt.close(fig);print(json.dumps(dict(outputs=[str(stem.with_suffix(s)) for s in ['.pdf','.svg','.png']],dimensions_mm=dimensions,
        annual_median_values=112,median_source_country_year_observations=2128,all_worldwide_countries=manifest['worldwide_country_union']),ensure_ascii=False))


if __name__=='__main__':main()
