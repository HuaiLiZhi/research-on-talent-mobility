"""Compare four annual country snapshots below the unchanged upper panels."""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
V3,V4=ROOT/'figures/v3',ROOT/'figures/v4'
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps'),str(V3),str(V4),
              str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa')]
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.colors import to_rgba
from matplotlib.ticker import FuncFormatter,MaxNLocator
from audit_panel_alignment import require_matplotlib_panel_alignment
from figure_style import output_root
from figure_palette import YEAR_COLORS

OUT=output_root(V3)
QA=OUT/'QA/Fig2'
WIDTH_MM=180.
HEIGHT_PT=313.
PANEL_HEIGHT_PT=95.
LOWER_LIGHT_GRIDS=False
RASTER_DPI=600
EXPORT_SUFFIXES=('.pdf','.svg','.png')
FONT_CONTRACT={'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial'],
               'svg.fonttype':'none','pdf.fonttype':42}
SNAPSHOT_YEARS=(1998,2007,2016,2025)
PERIODS=[(str(year),year,year,YEAR_COLORS[year]) for year in SNAPSHOT_YEARS]
METRICS=[('e','international_flow','International inflow (events/year)'),
         ('f','domestic_cities','Domestic inflow cities')]
BINS=50


def read(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def write(path,rows):
    with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def count_format(value,_):
    if value>=1000:return f'{value/1000:g}k'
    return f'{value:g}'


def prepare(source_out,countries):
    rows=[r for r in read(source_out/'Fig2_country_year_data.csv') if r['side']=='inflow']
    inputs=[dict(country=r['country'],year=int(r['year']),international_flow=float(r['international_flow']),
                 domestic_cities=int(r['domestic_cities'])) for r in rows]
    write(source_out/'Fig2_histogram_annual_inputs.csv',inputs)
    observations=[];stats=[];bins=[];peak=0
    for panel,metric,xlabel in METRICS:
        groups=[]
        for label,lo,hi,colour in PERIODS:
            vals=[]
            for cc in countries:
                rr=[r for r in inputs if r['country']==cc and lo<=r['year']<=hi]
                assert len(rr)==1 and rr[0]['year']==lo==hi
                value=float(rr[0][metric]);assert value>0
                vals.append(value)
                observations.append(dict(panel=panel,metric=metric,country=cc,period=label,
                    start_year=lo,end_year=hi,annual_observations=1,year=lo,value=value,colour=colour))
            groups.append(vals)
            stats.append(dict(panel=panel,metric=metric,period=label,countries=len(vals),
                arithmetic_mean=float(np.mean(vals)),median=float(np.median(vals)),
                minimum=float(np.min(vals)),maximum=float(np.max(vals)),colour=colour))
        minimum,maximum=np.min(groups),np.max(groups)
        low=np.floor(np.log10(minimum)*5)/5
        high=np.ceil(np.log10(maximum)*5)/5
        edges=np.geomspace(10**low,10**high,BINS+1)
        for (label,lo,hi,colour),values in zip(PERIODS,groups):
            counts,_=np.histogram(values,bins=edges);assert counts.sum()==76
            peak=max(peak,int(counts.max()))
            bins.extend(dict(panel=panel,metric=metric,period=label,bin_index=i,
                left=float(a),right=float(b),countries=int(n),colour=colour)
                for i,(a,b,n) in enumerate(zip(edges[:-1],edges[1:],counts)))
    write(source_out/'Fig2_histogram_country_snapshots.csv',observations)
    write(source_out/'Fig2_histogram_summaries.csv',stats)
    write(source_out/'Fig2_histogram_bins.csv',bins)
    return observations,stats,bins,float(np.ceil(peak*1.35/5)*5)


def draw_histograms(container,canonical,countries,source_out,qa,year_colours):
    source_out=Path(source_out);fig=container.figure
    observations,stats,bins,ymax=prepare(source_out,countries)
    width,old_height=fig.get_size_inches()*72
    upper=[(ax,ax.get_position().bounds) for ax in fig.axes if ax is not container]
    fig.set_size_inches(width/72,HEIGHT_PT/72,forward=True)
    height=HEIGHT_PT
    # Shorten the canvas without scaling the upper plot areas, labels or fonts.
    for ax,(x,y,w,h) in upper:
        ax.set_position([x,(y*old_height-(old_height-height))/height,w,h*old_height/height])
    container.set_position([45/width,43/height,202/width,PANEL_HEIGHT_PT/height])
    # Re-anchor the original e label after replacing its spanning plot area.
    label=next(t for t in container.texts if t.get_text()=='e')
    label.set_position((-18/202,1+8/PANEL_HEIGHT_PT))
    right=fig.add_axes([291/width,43/height,202/width,PANEL_HEIGHT_PT/height]);right.set_gid('f')
    right.text(-18/202,1+8/PANEL_HEIGHT_PT,'f',transform=right.transAxes,fontsize=10,
               fontweight='bold',ha='left',va='bottom')
    rects=[];guides=[]
    for ax,(panel,metric,xlabel),x0 in zip([container,right],METRICS,[45.,291.]):
        panel_bins=[r for r in bins if r['panel']==panel]
        first=[r for r in panel_bins if r['period']==PERIODS[0][0]]
        edges=np.array([r['left'] for r in first]+[first[-1]['right']])
        ax.set_xscale('log');ax.set_xlim(edges[0],edges[-1]);ax.set_ylim(0,ymax)
        ax.set_xlabel(xlabel,labelpad=4)
        ax.set_ylabel('Countries',labelpad=4)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4,integer=True))
        ticks=[v for v in [1,2,10,100,1000,10000,100000,1000000] if edges[0]<=v<=edges[-1]]
        if metric=='international_flow':ticks=[v for v in ticks if v!=2]
        ax.set_xticks(ticks);ax.xaxis.set_major_formatter(FuncFormatter(count_format))
        ax.tick_params(axis='both',which='major',length=3,pad=3)
        ax.tick_params(axis='x',which='minor',bottom=False)
        for name,spine in ax.spines.items():spine.set_visible(name in ['left','bottom']);spine.set_linewidth(.6)
        for group_index,(period,lo,hi,colour) in enumerate(PERIODS):
            values=[r['value'] for r in observations if r['panel']==panel and r['period']==period]
            _,_,patches=ax.hist(values,bins=edges,facecolor=to_rgba(colour,.20),edgecolor=colour,
                linewidth=.55,zorder=2+group_index)
            for i,p in enumerate(patches):p.set_gid(f'hist_{panel}_{lo}_{i}')
            stat=next(r for r in stats if r['panel']==panel and r['period']==period)
            for kind,style in [('arithmetic_mean','solid'),('median',(0,(4,3)))]:
                value=stat[kind]
                line=ax.vlines(value,0,ymax*.82,colors=colour,linestyles=style,linewidth=1.25,zorder=5)
                line.set_gid(f'hist_{panel}_{lo}_{kind}')
                guides.append(dict(panel=panel,period=period,statistic=kind,value=value,
                    line_style='solid' if kind=='arithmetic_mean' else 'dashed',colour=colour))
        if panel=='e':
            handles=[Patch(facecolor=colour,edgecolor=colour,alpha=.5,label=period) for period,_,_,colour in PERIODS]
        else:
            handles=[Line2D([],[],color='black',lw=1.25,linestyle='solid',label='Mean'),
                     Line2D([],[],color='black',lw=1.25,linestyle=(0,(4,3)),label='Median')]
        ax.legend(handles=handles,loc='upper right',bbox_to_anchor=(.98,.99),frameon=False,
            fontsize=8,ncol=2,handlelength=1.1,handletextpad=.4,columnspacing=1.,labelspacing=.4,borderaxespad=0)
        rects.append(dict(panel=panel,plot_rectangle_pt=[x0,43.,202.,PANEL_HEIGHT_PT],
            xlim=[float(edges[0]),float(edges[-1])],ylim=[0,ymax],xscale='log',
            xticks=ticks,xlabel=xlabel))
    write(source_out/'Fig2_histogram_summary_guides.csv',guides)
    result=dict(type='four_year_country_histograms',point_count=len(observations),snapshot_years=SNAPSHOT_YEARS,
        country_count=len(countries),countries=countries,periods=[dict(label=p,start_year=a,end_year=b,colour=c) for p,a,b,c in PERIODS],
        annual_inputs=2128,country_snapshot_metric_observations=len(observations),bins_per_panel=BINS,
        bin_spacing='Equal width in logarithmic coordinates; geometric bin edges',
        panels=rects,detail_panels=[],summary_guides=guides,arithmetic_averaging=False,
        purpose='Compare the distributions across the same national systems, complementing global annual totals and source coverage',
        descriptive_no_uncertainty=True,prior_streamgraph_removed=True)
    (Path(qa)/'histogram_geometry.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def main():
    spec=importlib.util.spec_from_file_location('fig2_v4_shared_histograms',V4/'plot_fig2.py')
    shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
    shared.OUT,shared.QA=OUT,QA
    original_configure=shared.configure
    def configure():
        original_configure();shared.mpl.rcParams.update(FONT_CONTRACT)
    shared.configure=configure;shared.draw_city_clusters=draw_histograms
    original_style=shared.apply_axes_typography
    def style(fig,**options):
        original_style(fig,**options)
        if not LOWER_LIGHT_GRIDS:
            for artist in list(getattr(fig,'_light_grid_artists',[])):
                if (artist.get_gid() or '').startswith(('e_','f_')):
                    artist.remove();fig._light_grid_artists.remove(artist)
            report=getattr(fig,'_light_grid_audit',None)
            if report:
                for record in report['axes']:
                    if record['axes'] in ['e','f']:record.update(grid=False,reason='Clean overlapping histograms')
                if options.get('grid_json_out'):Path(options['grid_json_out']).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    shared.apply_axes_typography=style
    def alignment(fig,**options):
        for ax in fig.axes:
            if ax.get_gid() in list('abcdef'):
                assert np.isclose(ax.get_position().height*fig.get_size_inches()[1]*72,PANEL_HEIGHT_PT)
        options['row_groups']=[['a','b','c','d'],['e','f']]
        options['column_groups']=[]
        return require_matplotlib_panel_alignment(fig,**options)
    shared.require_matplotlib_panel_alignment=alignment
    with contextlib.redirect_stdout(io.StringIO()):shared.main()
    p=QA/'figure_manifest.json';manifest=json.loads(p.read_text(encoding='utf-8'));hist=manifest.pop('city_entry_panel')
    manifest.update(edition='v3',archetype='Four upper panels and two country-distribution histograms',histogram_panel=hist)
    manifest['claim']='Recorded international flow volume and domestic city coverage expand across national systems.'
    manifest['panels'].update(e='International inflow distributions across countries in1998,2007,2016,2025',
                              f='Domestic inflow-city count distributions across the same countries and four years')
    manifest['layout'].update(second_row=['e','f'],lower_plot_width_pt=202.,lower_plot_height_pt=PANEL_HEIGHT_PT,
                              native_height_pt=HEIGHT_PT,removed='Prior country streamgraph replaced by two period-comparison histograms')
    for key in ['city_panel_width_pt','city_panel_height_pt']:
        manifest['layout'].pop(key,None)
    manifest['layout']['former_insets']='Upper distribution panels b,d are standalone; e,f have no insets'
    manifest['selected_countries']=hist['countries']
    manifest['city_label_rule']='All76 countries contribute to both distributions; no country labels are required for aggregated bins'
    manifest['legend_placement'].update(e='Four-year legend in two columns at upper right',f='Mean/median line-style key in one row at upper right')
    manifest['palette']['snapshots']={p[0]:p[3] for p in PERIODS}
    manifest['uncertainty']='Descriptive country distributions for four observed years; solid lines are arithmetic means across countries and dashed lines are medians; no period averaging or confidence intervals'
    manifest['auxiliary_data']='Annual inputs, country snapshots, summaries, bins and summary guides define lower panels; earlier detail-bin and lower-panel display tables are historical auxiliary data'
    p.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    caption=(r'\textbar\ \textbf{Expansion in recorded researcher mobility and geographic coverage.} '
        r'\textbf{a,c,} Annual international (a) and domestic intercity (c) mobility events. Red curves show observed totals; blue curves hold mean events per recorded route at its initial-year level. '
        r'\textbf{b,d,} Percentages of destination countries (b) and domestic destination cities (d) connected to at least the indicated number of sources. Domestic percentages give equal weight to 76 countries. Colours distinguish 1998, 2007, 2016 and 2025. '
        r'\textbf{e,f,} Distributions across the same 76 countries of international inflow events (e) and domestic inflow-city counts (f) in 1998, 2007, 2016 and 2025. Colours match b,d. Solid lines mark arithmetic means across countries; dashed lines mark medians. Horizontal axes are logarithmic, with 50 bins equally spaced in log coordinates and shared across years within each panel.')
    (OUT/'Fig2_caption.tex').write_text(r'\caption{'+caption+'}\n'+r'\label{fig:fig2}'+'\n',encoding='utf-8')
    (OUT/'Fig2_设计说明与图注.md').write_text(
        '# Fig2 v3 四个年份的国家分布比较\n\n'
        'a–d保持原样。删除原e的流带图，改为并排的e、f两张直方图。左侧展示各国跨国流入次数，右侧展示各国国内流入城市数量。'
        '比较1998、2007、2016和2025年，同一76国样本在每个年份各贡献一个观测值，不计算时期平均。四个年份颜色与b、d一致。使用半透明柱体与同色轮廓叠加，实线标出跨国家算术均值，虚线标出中位数。'
        'e、f绘图区高度均为95pt，与第一行四图相同；画布相应缩短，保持第一行字号、宽度、图形及两行间距。'
        '删除e、f的全部嵌套小图。横轴恢复对数刻度，各图根据四年全部观测值确定完整范围，每张图采用50个对数等距分箱，所有观测值均保留。纵轴为每个区间内的国家数，两张图共用纵轴范围。'
        '不拟合正态曲线，不生成模拟数据，不绘制推断置信区间。仅修改v3，未同步到v4及论文最终文件。\n\n'
        '## Figure legend\n\n'+caption+'\n',encoding='utf-8')
    print(json.dumps({'outputs':[str(OUT/('Fig2'+e)) for e in EXPORT_SUFFIXES],
        'countries':76,'snapshot_years':SNAPSHOT_YEARS,'country_snapshot_observations':608,'lower_panels':['e','f']},ensure_ascii=False))


if __name__=='__main__':main()
