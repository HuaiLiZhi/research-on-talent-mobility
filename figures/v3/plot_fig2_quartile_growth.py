"""Country-level mobility and coverage growth across established share quartiles."""
from pathlib import Path
import contextlib
import io
import json

import plot_fig2_period_histograms as base
import duckdb
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter,NullLocator
from scipy.stats import t

ROOT=base.ROOT
WIDTH_MM=180.
HEIGHT_PT=313.
RASTER_DPI=600
EXPORT_SUFFIXES=('.pdf','.svg','.png')
FONT_CONTRACT={'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial'],
               'svg.fonttype':'none','pdf.fonttype':42}
PANEL_SPECS=[('e',45.,'international_flow','partner_countries','International growth (×)','Country coverage (×)'),
             ('f',291.,'domestic_flow','domestic_cities','Domestic growth (×)','City coverage (×)')]


def prepare(source_out):
    groups=base.read(ROOT/'figures/v3/source_data/Fig5_stratified_country_trends.csv')
    membership={r['country']:int(r['group']) for r in groups}
    linked=base.read(ROOT/'figures/v3/source_data/Fig4_Fig5_quartile_membership.csv')
    colours={int(r['group']):r['color'] for r in linked}
    assert membership=={r['country']:int(r['group']) for r in linked}
    assert all(sum(group==g for group in membership.values())==19 for g in range(1,5))
    annual=base.read(ROOT/'figures/v3/source_data/Fig5_combined_country_year_metrics.csv')
    canonical=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet'
    connection=duckdb.connect();connection.execute("SET threads=4")
    partner_rows=connection.execute("""
        WITH flows AS (SELECT year,origin_country,destination_country FROM read_parquet(?)
            WHERE flow>0 AND origin_country<>destination_country AND year BETWEEN1998 AND2025),
        endpoints AS (SELECT year,origin_country country,destination_country partner FROM flows
            UNION ALL SELECT year,destination_country,origin_country FROM flows)
        SELECT country,year,count(DISTINCT partner) FROM endpoints GROUP BY country,year
        """.replace('BETWEEN1998 AND2025','BETWEEN 1998 AND 2025'),[str(canonical)]).fetchall()
    connection.close()
    partners={(cc,int(year)):int(count) for cc,year,count in partner_rows}
    raw=[]
    for country in sorted(membership):
        rr=sorted([r for r in annual if r['country']==country],key=lambda r:int(r['year']))
        assert [int(r['year']) for r in rr]==list(range(1998,2026))
        values=dict(international_flow=np.array([float(r['international_flow']) for r in rr]),
                    partner_countries=np.array([partners[country,int(r['year'])] for r in rr]),
                    domestic_flow=np.array([float(r['domestic_flow_events']) for r in rr]),
                    domestic_cities=np.array([int(r['domestic_cities']) for r in rr]))
        means={key:float(value[:7].mean()) for key,value in values.items()}
        assert all(np.all(value>0) for value in values.values())
        group=membership[country]
        for i,row in enumerate(rr):
            record=dict(country=country,year=int(row['year']),group=group,colour=colours[group])
            for key,value in values.items():
                record[key]=float(value[i]);record[key+'_baseline']=means[key]
                record[key+'_ratio']=float(value[i]/means[key])
            raw.append(record)
    assert len(raw)==2128
    base.write(Path(source_out)/'Fig2_quartile_growth_country_year.csv',raw)
    return raw,membership,colours


def fit_clustered(rows,xkey,ykey):
    x=np.log([r[xkey+'_ratio'] for r in rows]);y=np.log([r[ykey+'_ratio'] for r in rows])
    centre=float(x.mean());design=np.column_stack([np.ones(len(x)),x-centre])
    coefficients=np.linalg.lstsq(design,y,rcond=None)[0]
    residual=y-design@coefficients
    countries=sorted({r['country'] for r in rows})
    scores=np.array([np.sum(design[[r['country']==cc for r in rows]]*
        residual[[r['country']==cc for r in rows],None],axis=0) for cc in countries])
    bread=np.linalg.inv(design.T@design);n=len(x);g=len(countries)
    covariance=g/(g-1)*(n-1)/(n-2)*bread@(scores.T@scores)@bread
    grid=np.linspace(x.min(),x.max(),201);prediction_design=np.column_stack([np.ones(len(grid)),grid-centre])
    estimate=prediction_design@coefficients
    se=np.sqrt(np.maximum(0.,np.einsum('ij,jk,ik->i',prediction_design,covariance,prediction_design)))
    critical=float(t.ppf(.975,g-1))
    return np.exp(grid),np.exp(estimate),np.exp(estimate-critical*se),np.exp(estimate+critical*se),dict(
        centred_log_x=centre,coefficients=coefficients.tolist(),covariance=covariance.tolist(),
        observations=n,countries=countries,clusters=g,degrees_of_freedom=g-1,critical_t=critical)


def ratio_ticks(limits,candidates):
    return [value for value in candidates if limits[0]<=value<=limits[1]]


def draw_panels(container,canonical,countries,source_out,qa,year_colours):
    observations,membership,colours=prepare(source_out)
    assert set(countries)==set(membership)
    fig=container.figure;width,old_height=fig.get_size_inches()*72
    upper=[(ax,ax.get_position().bounds) for ax in fig.axes if ax is not container]
    fig.set_size_inches(width/72,HEIGHT_PT/72,forward=True)
    for ax,(x,y,w,h) in upper:
        ax.set_position([x,(y*old_height-(old_height-HEIGHT_PT))/HEIGHT_PT,w,h*old_height/HEIGHT_PT])
    container.set_position([45/width,43/HEIGHT_PT,202/width,95/HEIGHT_PT]);container.clear();container.set_gid('e')
    right=fig.add_axes([291/width,43/HEIGHT_PT,202/width,95/HEIGHT_PT]);right.set_gid('f')
    plotted=[];curves=[];stats=[];panels=[]
    for ax,(panel,x0,xkey,ykey,xlabel,ylabel) in zip([container,right],PANEL_SPECS):
        ax.text(-18/202,1+8/95,panel,transform=ax.transAxes,fontsize=10,fontweight='bold',ha='left',va='bottom')
        ax.set_xscale('log');ax.set_yscale('log')
        all_x=[];all_y=[]
        for group in range(1,5):
            rr=[r for r in observations if r['group']==group];colour=colours[group]
            x=np.array([r[xkey+'_ratio'] for r in rr]);y=np.array([r[ykey+'_ratio'] for r in rr])
            grid,estimate,lower,upper,fit=fit_clustered(rr,xkey,ykey)
            band=ax.fill_between(grid,lower,upper,color=colour,alpha=.10,linewidth=0,zorder=1)
            band.set_gid(f'quartile_band_{panel}_Q{group}')
            line,=ax.plot(grid,estimate,color=colour,linewidth=1.7,zorder=4)
            line.set_gid(f'quartile_fit_{panel}_Q{group}')
            points=ax.scatter(x,y,s=11,facecolors=to_rgba(colour,.23),edgecolors=to_rgba(colour,.50),linewidths=.25,zorder=3)
            points.set_gid(f'quartile_points_{panel}_Q{group}')
            plotted.extend(dict(panel=panel,country=r['country'],year=r['year'],group=group,
                xkey=xkey,ykey=ykey,x=float(xx),y=float(yy),colour=colour)
                for r,xx,yy in zip(rr,x,y))
            curves.extend(dict(panel=panel,group=group,x=float(xx),estimate=float(yy),lower95=float(lo),upper95=float(hi),colour=colour)
                for xx,yy,lo,hi in zip(grid,estimate,lower,upper))
            stats.append(dict(panel=panel,group=group,xkey=xkey,ykey=ykey,colour=colour,**fit))
            all_x.extend(x);all_y.extend(y);all_y.extend(lower);all_y.extend(upper)
        xlim=10**np.array([np.floor(np.log10(min(all_x))*5)/5,np.ceil(np.log10(max(all_x))*5)/5])
        ylim=10**np.array([np.floor(np.log10(min(all_y))*5)/5,np.ceil(np.log10(max(all_y))*5)/5])
        ax.set_xlim(*xlim);ax.set_ylim(*ylim)
        ax.set_xticks(ratio_ticks(xlim,[.1,1,10,100,1000,10000]))
        ax.set_yticks(ratio_ticks(ylim,[.2,.5,1,2,5,10,20,50]))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value,pos:f'{value:g}'))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value,pos:f'{value:g}'))
        ax.xaxis.set_minor_locator(NullLocator());ax.yaxis.set_minor_locator(NullLocator())
        ax.set_xlabel(xlabel,labelpad=4);ax.set_ylabel(ylabel,labelpad=4);ax.tick_params(axis='both',length=3,pad=3)
        for spine in ax.spines.values():spine.set_visible(True);spine.set_linewidth(.6)
        ax.grid(False)
        handles=[Line2D([],[],linestyle='None',marker='o',markersize=4.5,
            markerfacecolor=to_rgba(colours[g],.55),markeredgecolor=colours[g],markeredgewidth=.5,label=f'T{g}') for g in range(1,5)]
        ax.legend(handles=handles,loc='lower right',frameon=False,ncol=2,fontsize=8,
            handlelength=.7,handletextpad=.4,columnspacing=.8,labelspacing=.3,borderaxespad=.45)
        panels.append(dict(panel=panel,plot_rectangle_pt=[x0,43.,202.,95.],xkey=xkey,ykey=ykey,
            xlim=xlim.tolist(),ylim=ylim.tolist(),xscale='log',yscale='log',xlabel=xlabel,ylabel=ylabel))
    base.write(Path(source_out)/'Fig2_quartile_growth_points.csv',plotted)
    base.write(Path(source_out)/'Fig2_quartile_growth_fits.csv',curves)
    geometry=dict(type='country_year_growth_by_share_quartile',countries=sorted(membership),country_count=76,
        point_count=len(plotted),country_years=2128,years=list(range(1998,2026)),panels=panels,statistics=stats,
        groups=[dict(group=g,countries=19,colour=colours[g]) for g in range(1,5)],
        baseline_years=list(range(1998,2005)),baseline='Own-country arithmetic mean over first seven years',
        grouping='Exact fixed Fig3/Fig4/Fig5 international-share growth quartiles; no new classification',
        scope='International inflow and outflow strengths combined; partner countries counted as a union. Domestic event counts once per event,city counts union origins/destinations.',
        confidence='OLS in log growth ratios;country-clustered covariance with finite-sample correction and18df t critical value',
        no_jitter=True,no_insets=True,no_histograms=True)
    (Path(qa)/'quartile_growth_geometry.json').write_text(json.dumps(geometry,indent=2),encoding='utf-8')
    return geometry


def main():
    base.FONT_CONTRACT=FONT_CONTRACT;base.draw_histograms=draw_panels
    with contextlib.redirect_stdout(io.StringIO()):base.main()
    path=base.QA/'figure_manifest.json';manifest=json.loads(path.read_text(encoding='utf-8'))
    geometry=manifest.pop('histogram_panel');manifest['quartile_growth_panels']=geometry
    manifest['archetype']='Four upper panels and two matched four-colour growth scatter panels'
    manifest['panels'].update(e='Country-year international volume growth versus partner-country coverage growth',
        f='Country-year domestic volume growth versus city coverage growth')
    manifest['palette']['quartile_groups']={f"T{r['group']}":r['colour'] for r in geometry['groups']}
    manifest['legend_placement'].update(e='T1–T4 lower right',f='T1–T4 lower right')
    manifest['layout']['former_insets']='No lower-panel insets'
    manifest['auxiliary_data']='Quartile growth country-year,point and fit tables define e,f. Previous lower-panel plotting tables are historical auxiliary data.'
    manifest['uncertainty']=geometry['confidence']
    path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    caption=(r'\textbar\ \textbf{Expansion in recorded researcher mobility and geographic coverage.} '
        r'\textbf{a,c,} Annual international (a) and domestic intercity (c) mobility events. Red curves show observed totals; blue curves hold mean events per recorded route at its initial-year level. '
        r'\textbf{b,d,} Percentages of destination countries (b) and domestic destination cities (d) connected to at least the indicated number of sources. Domestic percentages give equal weight to 76 countries. Colours distinguish 1998, 2007, 2016 and 2025. '
        r'\textbf{e,f,} Growth in international mobility and partner-country coverage (e), and domestic mobility and city coverage (f). Each point is one country-year, with inflows and outflows combined. Values are divided by each country\textquotesingle s 1998--2004 mean. T1--T4 retain the international-share growth quartiles used in Figs. 3 and 5 (19 countries each). Axes are logarithmic. Lines show fits to log growth ratios; bands indicate 95\% confidence intervals clustered by country.')
    (base.OUT/'Fig2_caption.tex').write_text(r'\caption{'+caption+'}\n'+r'\label{fig:fig2}'+'\n',encoding='utf-8')
    (base.OUT/'Fig2_设计说明与图注.md').write_text(
        '# Fig2 v3 T1–T4国家的流动与覆盖增长\n\n'
        '第二行颜色沿用Fig3、Fig4和Fig5：T1蓝色、T2灰色、T3绿色、T4红色。固定76国每年各贡献一个点，每图2128点，保留全部28年。'
        'e横轴为各国跨国流入与流出合计的增长倍数，纵轴为与该国相连的国际伙伴国家数增长倍数；相同伙伴在流入流出中只计一次。'
        'f横轴为各国国内城际事件数增长倍数，纵轴为国内有流量城市数增长倍数；城市按来源与目的地取并集。'
        '每国每项指标分别除以1998–2004年的算术均值；双对数坐标保留所有观测范围。四组按原有国际流动份额全期增长率固定，不按国内增长重新分组。'
        '每组在对数增长比上OLS拟合，协方差按19个国家聚类，有限样本修正G/(G−1)*(n−1)/(n−2)，用18自由度t临界值绘制逐点95%置信带。'
        '每组包含19国和532个国家—年观测。a–d保持当前内容，第二行主绘图区高度95pt，仅更新v3。\n\n## Figure legend\n\n'+caption+'\n',encoding='utf-8')
    print(json.dumps({'outputs':[str(base.OUT/('Fig2'+ext)) for ext in EXPORT_SUFFIXES],
        'countries':76,'groups':4,'points_per_panel':2128,'total_points':4256},ensure_ascii=False))


if __name__=='__main__':main()
