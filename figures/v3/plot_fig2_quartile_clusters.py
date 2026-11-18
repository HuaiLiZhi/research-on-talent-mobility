"""Country growth summaries with descriptive quartile dispersion regions."""
from pathlib import Path
import contextlib
import io
import json

import plot_fig2_quartile_growth as previous
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
from scipy.stats import t

base=previous.base
WIDTH_MM=180.
HEIGHT_PT=313.
RASTER_DPI=600
EXPORT_SUFFIXES=('.pdf','.svg','.png')
FONT_CONTRACT={'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial'],
               'svg.fonttype':'none','pdf.fonttype':42}
PANEL_SPECS=[('e',45.,'international_flow','partner_countries','International growth (%/yr)','Partner growth (%/yr)'),
             ('f',291.,'domestic_flow','domestic_cities','Domestic growth (%/yr)','City growth (%/yr)')]


def summarize(raw,membership,colours):
    summaries=[]
    for country in sorted(membership):
        rows=sorted([r for r in raw if r['country']==country],key=lambda r:r['year'])
        years=np.array([r['year'] for r in rows]);assert years.tolist()==list(range(1998,2026))
        result=dict(country=country,group=membership[country],colour=colours[membership[country]],years=28)
        for key in ['international_flow','partner_countries','domestic_flow','domestic_cities']:
            values=np.array([r[key] for r in rows]);assert np.all(values>0)
            slope=float(np.polyfit(years-years[0],np.log(values),1)[0])
            result[key+'_log_slope']=slope;result[key+'_growth_pct']=float(100*np.expm1(slope))
        summaries.append(result)
    return summaries


def pooled_fit(x,y,grid):
    centre=float(x.mean());design=np.column_stack([np.ones(len(x)),x-centre])
    bread=np.linalg.inv(design.T@design);coefficient=np.linalg.lstsq(design,y,rcond=None)[0]
    residual=y-design@coefficient;leverage=np.einsum('ij,jk,ik->i',design,bread,design)
    scores=design*(residual/(1-leverage))[:,None]
    covariance=bread@(scores.T@scores)@bread
    pred=np.column_stack([np.ones(len(grid)),grid-centre]);estimate=pred@coefficient
    se=np.sqrt(np.maximum(0.,np.einsum('ij,jk,ik->i',pred,covariance,pred)))
    critical=float(t.ppf(.975,len(x)-2))
    return estimate,estimate-critical*se,estimate+critical*se,dict(
        centre_x=centre,coefficients=coefficient.tolist(),covariance=covariance.tolist(),
        observations=len(x),degrees_of_freedom=len(x)-2,critical_t=critical,covariance_type='HC3')


def central_region(values):
    centre=np.median(values,axis=0);covariance=np.cov(values,rowvar=False,ddof=1)
    inverse=np.linalg.inv(covariance);difference=values-centre
    distances=np.einsum('ij,jk,ik->i',difference,inverse,difference)
    radius2=float(np.sort(distances)[12])
    theta=np.linspace(0,2*np.pi,361)
    circle=np.column_stack([np.cos(theta),np.sin(theta)])
    boundary=centre+np.sqrt(radius2)*circle@np.linalg.cholesky(covariance).T
    return boundary,dict(centre=centre.tolist(),covariance=covariance.tolist(),radius_squared=radius2,
        countries=19,central_countries=int(np.sum(distances<=radius2+1e-10)),coverage_rule='13th smallest empirical Mahalanobis distance from coordinate-wise group median')


def draw_panels(container,canonical,countries,source_out,qa,year_colours):
    raw,membership,colours=previous.prepare(source_out)
    summaries=summarize(raw,membership,colours);assert set(countries)==set(membership)
    fig=container.figure;width,old_height=fig.get_size_inches()*72
    upper=[(ax,ax.get_position().bounds) for ax in fig.axes if ax is not container]
    fig.set_size_inches(width/72,HEIGHT_PT/72,forward=True)
    for ax,(x,y,w,h) in upper:
        ax.set_position([x,(y*old_height-(old_height-HEIGHT_PT))/HEIGHT_PT,w,h*old_height/HEIGHT_PT])
    container.set_position([45/width,43/HEIGHT_PT,202/width,95/HEIGHT_PT]);container.clear();container.set_gid('e')
    right=fig.add_axes([291/width,43/HEIGHT_PT,202/width,95/HEIGHT_PT]);right.set_gid('f')
    points=[];boundaries=[];curves=[];statistics=[];regions=[];panels=[]
    for ax,(panel,x0,xkey,ykey,xlabel,ylabel) in zip([container,right],PANEL_SPECS):
        ax.text(-18/202,1+8/95,panel,transform=ax.transAxes,fontsize=10,fontweight='bold',ha='left',va='bottom')
        xx=np.array([r[xkey+'_growth_pct'] for r in summaries]);yy=np.array([r[ykey+'_growth_pct'] for r in summaries])
        grid=np.linspace(xx.min(),xx.max(),201);estimate,lower,upper,fit=pooled_fit(xx,yy,grid)
        band=ax.fill_between(grid,lower,upper,color='#747B83',alpha=.10,linewidth=0,zorder=0)
        band.set_gid('country_trend_band_'+panel)
        line,=ax.plot(grid,estimate,color='#59616A',linewidth=1.3,zorder=1)
        line.set_gid('country_trend_fit_'+panel)
        all_x=list(xx);all_y=list(yy)+list(lower)+list(upper)
        for group in range(1,5):
            rows=[r for r in summaries if r['group']==group];colour=colours[group]
            values=np.array([[r[xkey+'_growth_pct'],r[ykey+'_growth_pct']] for r in rows])
            boundary,region=central_region(values)
            fill=ax.fill(boundary[:,0],boundary[:,1],facecolor=to_rgba(colour,.06),edgecolor='none',zorder=1.1)[0]
            fill.set_gid(f'country_cluster_fill_{panel}_Q{group}')
            outline,=ax.plot(boundary[:,0],boundary[:,1],color=colour,linestyle=(0,(3,2)),linewidth=1.0,zorder=2)
            outline.set_gid(f'country_cluster_outline_{panel}_Q{group}')
            marks=ax.scatter(values[:,0],values[:,1],s=24,facecolors=to_rgba(colour,.55),
                             edgecolors=colour,linewidths=.65,zorder=4)
            marks.set_gid(f'country_cluster_points_{panel}_Q{group}')
            points.extend(dict(panel=panel,country=r['country'],group=group,xkey=xkey,ykey=ykey,
                               x=float(v[0]),y=float(v[1]),colour=colour) for r,v in zip(rows,values))
            boundaries.extend(dict(panel=panel,group=group,vertex=i,x=float(v[0]),y=float(v[1]),colour=colour)
                              for i,v in enumerate(boundary))
            regions.append(dict(panel=panel,group=group,colour=colour,**region))
            all_x.extend(boundary[:,0]);all_y.extend(boundary[:,1])
        xspan=max(all_x)-min(all_x);yspan=max(all_y)-min(all_y)
        ax.set_xlim(min(0.,min(all_x)-.06*xspan),max(all_x)+.06*xspan)
        ax.set_ylim(min(0.,min(all_y)-.06*yspan),max(all_y)+.08*yspan)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5));ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.set_xlabel(xlabel,labelpad=4);ax.set_ylabel(ylabel,labelpad=4)
        ax.tick_params(axis='both',length=2.4,width=.55,pad=2.5)
        for name,spine in ax.spines.items():
            spine.set_visible(name in ['left','bottom']);spine.set_linewidth(.6)
        ax.grid(False)
        handles=[Line2D([],[],linestyle='None',marker='o',markersize=4.5,markerfacecolor=to_rgba(colours[g],.55),
                       markeredgecolor=colours[g],markeredgewidth=.5,label=f'T{g}') for g in range(1,5)]
        ax.legend(handles=handles,loc='lower right',frameon=False,ncol=2,fontsize=8,handlelength=.7,
                  handletextpad=.4,columnspacing=.8,labelspacing=.3,borderaxespad=.45)
        panels.append(dict(panel=panel,plot_rectangle_pt=[x0,43.,202.,95.],xkey=xkey,ykey=ykey,
            xlim=list(ax.get_xlim()),ylim=list(ax.get_ylim()),xscale='linear',yscale='linear',xlabel=xlabel,ylabel=ylabel))
        statistics.append(dict(panel=panel,**fit))
        curves.extend(dict(panel=panel,x=float(x),estimate=float(y),lower95=float(lo),upper95=float(hi))
                      for x,y,lo,hi in zip(grid,estimate,lower,upper))
    base.write(Path(source_out)/'Fig2_quartile_country_growth.csv',summaries)
    base.write(Path(source_out)/'Fig2_quartile_country_points.csv',points)
    base.write(Path(source_out)/'Fig2_quartile_country_regions.csv',boundaries)
    base.write(Path(source_out)/'Fig2_quartile_country_pooled_fits.csv',curves)
    geometry=dict(type='country_growth_summary_clusters',country_point_summary=True,countries=sorted(membership),
        country_count=76,point_count=152,country_years_used=2128,years=list(range(1998,2026)),panels=panels,
        statistics=statistics,regions=regions,groups=[dict(group=g,countries=19,colour=colours[g]) for g in range(1,5)],
        growth='100*(exp(slope of log annual metric on year)-1);all28years used for each country',
        region='Descriptive central13/19 data ellipse,not confidence interval',confidence='Pooled76-country OLS with HC3 covariance and74df t interval',
        grouping='Unchanged Fig3/Fig4/Fig5 share-growth quartiles',no_jitter=True,no_insets=True,no_histograms=True)
    (Path(qa)/'quartile_country_cluster_geometry.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')
    return geometry


def main():
    base.FONT_CONTRACT=FONT_CONTRACT;base.draw_histograms=draw_panels
    base.LOWER_LIGHT_GRIDS=True
    with contextlib.redirect_stdout(io.StringIO()):base.main()
    path=base.QA/'figure_manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
    geometry=manifest.pop('histogram_panel');manifest['quartile_country_cluster_panels']=geometry
    manifest['archetype']='Four upper panels and two country-growth scatter panels with coloured group regions'
    manifest['panels'].update(e='Country-level international volume and partner coverage growth rates',f='Country-level domestic volume and city coverage growth rates')
    manifest['palette']['quartile_groups']={f"T{r['group']}":r['colour'] for r in geometry['groups']}
    manifest['legend_placement'].update(e='T1–T4 lower right',f='T1–T4 lower right')
    manifest['layout']['former_insets']='No lower-panel insets'
    manifest['layout']['axis_style']='All panels use left/bottom0.6pt black spines and shared pale major/midpoint grids'
    manifest['auxiliary_data']='Quartile country growth,points,regions and pooled-fit tables define e,f. Country-year records retain all2128 observations. Earlier lower-panel tables are historical auxiliary data.'
    manifest['uncertainty']=geometry['confidence']+';coloured outlines describe group dispersion'
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    caption=(r'\textbar\ \textbf{Expansion in recorded researcher mobility and geographic coverage.} '
        r'\textbf{a,c,} Annual international (a) and domestic intercity (c) mobility events. Red curves show observed totals; blue curves hold mean events per recorded route at its initial-year level. '
        r'\textbf{b,d,} Percentages of destination countries (b) and domestic destination cities (d) connected to at least the indicated number of sources. Domestic percentages give equal weight to 76 countries. Colours distinguish 1998, 2007, 2016 and 2025. '
        r'\textbf{e,f,} Annual growth rates in international mobility and partner-country coverage (e), and domestic mobility and city coverage (f). Each point represents one country, with rates fitted to all 28 years. T1--T4 retain the international-share growth quartiles used in Figs. 3 and 5 (19 countries each). Coloured ellipses summarize central group dispersion (13 of 19 countries). Grey lines show pooled linear fits; bands indicate HC3-robust 95\% confidence intervals.')
    (base.OUT/'Fig2_caption.tex').write_text(r'\caption{'+caption+'}\n'+r'\label{fig:fig2}'+'\n',encoding='utf-8')
    (base.OUT/'Fig2_设计说明与图注.md').write_text(
        '# Fig2 v3 国家增长趋势与T1–T4聚集\n\n'
        '每国完整28年记录概括为一个点，每图76点、每组19点；相同国家的早期基准点不再反复覆盖。'
        '每项指标以log(年度数量)对年份OLS拟合，斜率转换为年增长率100*(exp(b)-1)。e比较跨国流动量与国际伙伴国家数，f比较国内事件数与有流量城市数；流入流出合并。'
        '四组与Fig3–5一致。浅色区域和同色虚线椭圆以组内增长率的逐维中位数为中心，用全19国样本协方差决定形状，半径取协方差标准化距离第13小的数值，描述组内中心13国。它们不是置信区间，全部散点均保留。'
        '灰线与色带为76个国家间增长率关系的OLS拟合及HC3稳健95%置信区间，74自由度t临界值。'
        '两图均为线性百分比坐标，未移动点、加入抖动或重新分组。边框与a–d一致，仅显示左、下黑色坐标轴，线宽0.6pt；刻度长2.4pt、宽0.55pt、间隔2.5pt。网格沿用共享浅灰样式和主刻度间的中间网格线。主绘图区仍高95pt，仅更新v3。\n\n## Figure legend\n\n'+caption+'\n',encoding='utf-8')
    print(json.dumps({'outputs':[str(base.OUT/('Fig2'+ext)) for ext in EXPORT_SUFFIXES],
        'countries':76,'points_per_panel':76,'groups':4,'annual_records_used':2128},ensure_ascii=False))


if __name__=='__main__':main()
