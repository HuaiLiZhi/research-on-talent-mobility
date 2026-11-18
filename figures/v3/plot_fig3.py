"""Fig3: national densities, Lorenz curves and annual Gini comparisons.

Figure contract: compare observed national flow distributions in four years;
retain empirical skewness and distinguish share-density shape from inequality.
Python quantitative grid; Helvetica; 2+4 main axes with editable PDF/SVG.
Uses cleaned annual all-researcher intercity events, with no city recoding.
"""
from __future__ import annotations

import csv
import io
import hashlib
import json
import math
import sys
from pathlib import Path

from figure_style import font_size, output_root, WIDTH_PT, PROFILE, specification, apply_axes_typography

ROOT=Path(__file__).resolve().parents[2]
OUT=output_root(Path(__file__).resolve().parent)
DATA=OUT/'source_data'
QA=OUT/'QA'/'Fig3'
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
from matplotlib.patches import ConnectionPatch, Rectangle
import pymupdf
from audit_panel_alignment import require_matplotlib_panel_alignment

YEARS=[1998,2007,2016,2025]
from figure_palette import YEAR_COLORS,BLUE,RED
COLORS=YEAR_COLORS.copy()
INK='#17212A'
DENSITY_ZOOM=dict(xlim=(-2.15,-1.15),ylim=(.32,.41),box=(.49,.59,.49,.40))
LORENZ_ZOOM=dict(xlim=(75,93),ylim=(3,32),box=(.04,.30,.56,.67))


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
    con.execute(f"""CREATE TEMP VIEW international AS SELECT year,
        origin_country,destination_country,flow FROM read_parquet('{path}')
        WHERE origin_country<>destination_country AND flow>0""")
    rows=[dict(year=y,side=side,country=cc,flow=float(flow)) for y,side,cc,flow in
        con.execute("""SELECT year,'inflow' side,destination_country country,sum(flow) flow
            FROM international GROUP BY ALL UNION ALL
            SELECT year,'outflow',origin_country,sum(flow) FROM international GROUP BY ALL
            ORDER BY side,year,country""").fetchall()]
    con.close()
    with (CLEAN/'analysis'/'country_annual_margins.csv').open(encoding='utf-8-sig',newline='') as f:
        supplied={(int(r['year']),r['side'],r['country']):float(r['flow']) for r in csv.DictReader(f)}
    assert {(r['year'],r['side'],r['country']):r['flow'] for r in rows}==supplied
    groups={(side,y):[r for r in rows if r['side']==side and r['year']==y]
            for side in ['inflow','outflow'] for y in range(1998,2026)}
    metrics=[];lorenz=[]
    for (side,year),rs in groups.items():
        values=np.array([r['flow'] for r in rs]);total=float(sum(values))
        shares=values/total;n=len(values)
        assert np.isclose(sum(shares),1.) and np.all(shares>0)
        for r,p in zip(rs,shares):
            r.update(share=float(p),share_percent=float(100*p),log10_share_percent=float(np.log10(100*p)))
        ordered=np.sort(shares)
        x=np.arange(n+1)/n;y=np.r_[0,np.cumsum(ordered)];y[-1]=1.
        gini=float(1-2*np.trapezoid(y,x))
        hhi=float(sum(shares**2))
        metrics.append(dict(side=side,year=year,countries=n,total_events=total,HHI=hhi,
            equivalent_countries=1/hhi,normalized_equivalent_countries=1/(n*hhi),Gini=gini,
            top1_share=float(max(shares)),top5_share=float(sum(ordered[-5:])),
            top10_share=float(sum(ordered[-10:])),maximum_share=float(max(shares))))
        if year in YEARS:
            lorenz.extend(dict(side=side,year=year,rank=int(i),countries=n,
                cumulative_country_fraction=float(a),cumulative_flow_fraction=float(b))
                for i,(a,b) in enumerate(zip(x,y)))
    for year in range(1998,2026):
        assert sum(r['flow'] for r in groups['inflow',year])==sum(r['flow'] for r in groups['outflow',year])
    assert sum(m['total_events'] for m in metrics if m['side']=='inflow')==11529374
    # One data-derived absolute log-space bandwidth for all eight profiles.
    snapshots={(s,y):np.array([r['log10_share_percent'] for r in groups[s,y]])
               for s in ['inflow','outflow'] for y in YEARS}
    pooled=np.concatenate(list(snapshots.values()))
    robust_scale=min(float(np.std(pooled,ddof=1)),float(np.subtract(*np.percentile(pooled,[75,25]))/1.34))
    bandwidth=.9*robust_scale*float(np.median([len(v) for v in snapshots.values()]))**(-.2)
    lower=min(-5.5,math.floor((min(pooled)-5*bandwidth)*2)/2)
    upper=2. # log10(100%): the maximum possible national share.
    grid=np.linspace(lower,upper,1801)
    density=[];profiles={};checks=[]
    for (side,year),values in snapshots.items():
        z=(grid[:,None]-values[None,:])/bandwidth
        reflected=(grid[:,None]-(2*upper-values)[None,:])/bandwidth
        curve=np.mean(np.exp(-.5*z*z)+np.exp(-.5*reflected*reflected),axis=1)/(bandwidth*math.sqrt(2*math.pi))
        integral=float(np.trapezoid(curve,grid))
        assert abs(integral-1)<1e-5 and np.all(curve>=0)
        profiles[side,year]=curve
        density.extend(dict(side=side,year=year,log10_share_percent=float(x),share_percent=float(10**x),
            density_per_log10_share_percent=float(p),bandwidth_log10=bandwidth) for x,p in zip(grid,curve))
        checks.append(dict(side=side,year=year,countries=len(values),density_integral=integral))
    write_csv('Fig3_country_year_data.csv',rows)
    write_csv('Fig3_country_metrics.csv',metrics)
    write_csv('Fig3_density_curves.csv',density)
    write_csv('Fig3_lorenz_curves.csv',lorenz)
    write_csv('Fig3_HHI_insets.csv',[dict(side=r['side'],year=r['year'],HHI=r['HHI'],
        highlighted_year=r['year'] in YEARS) for r in metrics])
    write_csv('Fig3_top_country_shares.csv',[dict(side=r['side'],year=r['year'],top_k=k,
        share=r[f'top{k}_share'],share_percent=100*r[f'top{k}_share'])
        for r in metrics for k in [1,5,10]])
    write_csv('Fig3_distribution_insets.csv',[dict(side=r['side'],year=r['year'],
        Gini=r['Gini'],normalized_equivalent_countries=r['normalized_equivalent_countries'],
        countries=r['countries'],highlighted_year=r['year'] in YEARS) for r in metrics])
    return groups,metrics,lorenz,grid,profiles,bandwidth,checks


def add_annual_inset(fig,parent,annual,metric,gid,box,ylim,yticks,labels,ylabel):
    """Small annual metric, with the four snapshot years highlighted."""
    rect=parent.get_position()
    x,y,w,h=box
    ax=fig.add_axes([rect.x0+x*rect.width,rect.y0+y*rect.height,
                     w*rect.width,h*rect.height])
    ax.set_gid(gid)
    ax.plot([r['year'] for r in annual],[r[metric] for r in annual],color=INK,
        linewidth=.85,marker='o',markersize=1.3,markeredgewidth=0,zorder=2)
    for year in YEARS:
        value=next(r[metric] for r in annual if r['year']==year)
        ax.plot(year,value,marker='o',markersize=3.,linestyle='none',
            markerfacecolor=COLORS[year],markeredgecolor='white',markeredgewidth=.4,zorder=3)
    ax.set(xlim=(1996,2027),ylim=ylim)
    ax.set_xticks([1998,2025]);ax.set_yticks(yticks,labels)
    ax.tick_params(labelsize=font_size(5.2),length=1.4,width=.4,pad=1.4)
    ax.spines['left'].set_linewidth(.4);ax.spines['bottom'].set_linewidth(.4)
    ax.set_xlabel('')
    if metric=='normalized_equivalent_countries':
        ax.set_ylabel('');ax.set_title(ylabel,fontsize=font_size(5.4),loc='left',pad=2)
    else:ax.set_ylabel(ylabel,fontsize=font_size(5.4),labelpad=1.5)
    return ax


def add_top_country_inset(fig,parent,groups,side,gid):
    """Explain overall Gini with the shares held by the first ten ranked countries."""
    rect=parent.get_position()
    x,y,w,h=.36,.85,.57,.22
    ax=fig.add_axes([rect.x0+x*rect.width,rect.y0+y*rect.height,
        w*rect.width,h*rect.height],zorder=5)
    ax.set_gid(gid)
    records=[]
    for year in YEARS:
        ordered=sorted(groups[side,year],key=lambda r:(-r['flow'],r['country']))
        shares=np.array([r['share_percent'] for r in ordered[:10]])
        cumulative=np.cumsum(shares)
        assert len(cumulative)==10 and np.all(np.diff(cumulative)>0) and cumulative[-1]<80
        ax.plot(np.arange(1,11),cumulative,color=COLORS[year],linewidth=.85,
            marker='o',markersize=1.6,markevery=[0,4,9],markeredgewidth=0,zorder=2)
        records.extend(dict(panel=gid,side=side,year=year,top_k=k,
            ranked_country=r['country'],country_share_percent=float(p),
            cumulative_share_percent=float(total),countries=len(ordered))
            for k,(r,p,total) in enumerate(zip(ordered[:10],shares,cumulative),1))
    ax.set(xlim=(.7,10.3),ylim=(0,80))
    ax.set_xticks([1,5,10]);ax.set_yticks([0,80],['0','80'])
    ax.tick_params(labelsize=font_size(5.2),length=1.4,width=.4,pad=1.4)
    ax.spines['left'].set_linewidth(.4);ax.spines['bottom'].set_linewidth(.4)
    ax.set_title('Share (%)',fontsize=font_size(5.4),loc='left',pad=4)
    ax.set_xlabel('Top k',fontsize=font_size(5.2),labelpad=1.3)
    return ax,records


def clip_polyline(xs,ys,xlim,ylim):
    """Clip straight path segments before export, preserving the parent geometry."""
    parts=[];current=[]
    for x0,x1,y0,y1 in zip(xs[:-1],xs[1:],ys[:-1],ys[1:]):
        dx=x1-x0;dy=y1-y0;t0=0.;t1=1.;visible=True
        for p,q in [(-dx,x0-xlim[0]),(dx,xlim[1]-x0),(-dy,y0-ylim[0]),(dy,ylim[1]-y0)]:
            if p==0:
                if q<0:visible=False;break
            elif p<0:t0=max(t0,q/p)
            else:t1=min(t1,q/p)
        if not visible or t0>t1:
            if current:parts.append(np.array(current));current=[]
            continue
        start=(x0+t0*dx,y0+t0*dy);end=(x0+t1*dx,y0+t1*dy)
        if current and not np.allclose(current[-1],start,rtol=0,atol=1e-12):
            parts.append(np.array(current));current=[]
        if not current:current.append(start)
        current.append(end)
    if current:parts.append(np.array(current))
    return parts


def add_zoom_inset(fig,parent,curves,window,xticks,xticklabels,yticks,yticklabels,source_corner):
    """Enlarge the source rectangle isotropically, retaining its exact data limits."""
    rect=parent.get_position()
    x,y,w,h=window['box']
    source=parent.transData.transform([[window['xlim'][0],window['ylim'][0]],
        [window['xlim'][1],window['ylim'][1]]])
    source_size=source[1]-source[0]
    available=np.array([w*rect.width*fig.bbox.width,h*rect.height*fig.bbox.height])
    magnification=float(np.min(available/source_size))
    assert magnification>1
    inset_size=source_size*magnification/np.array([fig.bbox.width,fig.bbox.height])
    # Anchor the fitted rectangle at the upper right of its available slot.
    ax=fig.add_axes([rect.x0+(x+w)*rect.width-inset_size[0],
        rect.y0+(y+h)*rect.height-inset_size[1],*inset_size],zorder=6)
    ax.set_gid(parent.get_gid()+'_zoom')
    checks=[];vertices=[]
    for year,xs,ys in curves:
        assert np.all(np.diff(xs)>0)
        parts=clip_polyline(xs,ys,window['xlim'],window['ylim'])
        assert parts
        errors=[]
        for segment,part in enumerate(parts):
            line,=ax.plot(part[:,0],part[:,1],color=COLORS[year],linewidth=.95)
            errors.append(float(max(abs(line.get_ydata()-np.interp(line.get_xdata(),xs,ys)))))
            vertices.extend(dict(parent=parent.get_gid(),year=year,segment=segment,vertex=i,
                x=float(xv),y=float(yv)) for i,(xv,yv) in enumerate(part))
        assert max(errors)<1e-10
        checks.append(dict(parent=parent.get_gid(),year=year,matches_parent_polyline=True,
            source_vertices=len(xs),zoom_vertices=sum(len(p) for p in parts),max_vertical_error=max(errors)))
    ax.set(xlim=window['xlim'],ylim=window['ylim'])
    ax.set_xticks(xticks,xticklabels);ax.set_yticks(yticks,yticklabels)
    ax.tick_params(labelsize=font_size(5.2),length=1.5,width=.4,pad=1.4)
    for spine in ax.spines.values():
        spine.set_visible(True);spine.set_color('#87919A');spine.set_linewidth(.5)
    xmin,xmax=window['xlim'];ymin,ymax=window['ylim']
    parent.add_patch(Rectangle((xmin,ymin),xmax-xmin,ymax-ymin,facecolor='none',
        edgecolor='#87919A',linewidth=.5,linestyle=(0,(2,2)),zorder=1.5))
    if source_corner=='upper_right':
        parent.add_artist(ConnectionPatch(xyA=(xmin,ymax),coordsA=parent.transData,
            xyB=(1,.5),coordsB=ax.transAxes,axesA=parent,axesB=ax,
            color='#87919A',linewidth=.5,zorder=3,clip_on=False,
            connectionstyle='arc3,rad=0'))
    elif source_corner=='density_upper_right':
        parent.add_artist(ConnectionPatch(xyA=(xmax,ymax),coordsA=parent.transData,
            xyB=(0,0),coordsB=ax.transAxes,axesA=parent,axesB=ax,
            color='#87919A',linewidth=.5,zorder=3,clip_on=False))
    return ax,checks,vertices


def main():
    DATA.mkdir(exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    groups,metrics,lorenz,grid,profiles,bandwidth,checks=prepare_data()
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial'],
        'font.size':font_size(8),'axes.labelsize':font_size(8),'xtick.labelsize':font_size(6.5),'ytick.labelsize':font_size(7),
        'axes.linewidth':.6,'axes.spines.top':False,'axes.spines.right':False,
        'axes.labelcolor':INK,'text.color':INK,'xtick.color':INK,'ytick.color':INK,
        'axes.unicode_minus':False,'legend.frameon':False,'pdf.use14corefonts':True,
        'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
    # Keep the accepted first row at the same physical size and distance from top.
    base_height_pt=3.3858267717*72
    row_gap_reduction_pt=22
    within_pair_gutter_pt=40.
    lower_size_pt=(.385*WIDTH_PT-within_pair_gutter_pt)/2
    square_height_reduction_pt=102-lower_size_pt
    fig=plt.figure(figsize=(WIDTH_PT/72,5.5905511811-(row_gap_reduction_pt+square_height_reduction_pt)/72))
    height_pt=fig.get_figheight()*72
    def upper_y(y):
        return (height_pt-base_height_pt+y*base_height_pt)/height_pt
    axes=[fig.add_axes([left,upper_y(.17),.385,.68*base_height_pt/height_pt]) for left in [.08,.58]]
    ymax=math.ceil(max(float(max(v)) for v in profiles.values())*1.55*20)/20
    observed_min=min(r['log10_share_percent'] for (side,year),rows in groups.items()
                     if year in YEARS for r in rows)
    density_xlim=(math.floor((observed_min-.25)*4)/4,2.)
    zoom_checks=[];zoom_windows=[];zoom_vertices=[];median_guides=[]
    for ax,side,letter in zip(axes,['inflow','outflow'],'ab'):
        ax.set_gid(letter)
        for year in YEARS:
            curve=profiles[side,year]
            ax.fill_between(grid,0,curve,color=COLORS[year],alpha=.045,linewidth=0)
            ax.plot(grid,curve,color=COLORS[year],linewidth=1.25,label=str(year))
        ticks=[-4,-3,-2,-1,0,1,2]
        ax.set_xlim(density_xlim);ax.set_ylim(0,ymax)
        ax.set_xticks(ticks,['0.0001','','0.01','','1','','100'])
        ax.set_yticks(np.arange(0,ymax+.0001,.1))
        ax.set_xlabel(f'Country {side} share (%)',labelpad=5)
        ax.set_ylabel('Country density',labelpad=5)
        ax.tick_params(length=2.4,width=.55,pad=3)
        ax.text(-.13,1.04,letter,transform=ax.transAxes,fontsize=font_size(10),fontweight='bold',ha='left',va='bottom')
        peak_zoom,zs,zv=add_zoom_inset(fig,ax,[(year,grid,profiles[side,year]) for year in YEARS],
            DENSITY_ZOOM,np.log10([.01,.025,.06]),['0.01','0.025','0.06'],
            [.34,.37,.40],['0.34','0.37','0.40'],'density_upper_right')
        for year in YEARS:
            # The raw-share median is transformed only after it is calculated.
            values=np.array([r['share_percent'] for r in groups[side,year]])
            median=float(np.median(values));log_median=float(np.log10(median))
            density_at_median=float(np.interp(log_median,grid,profiles[side,year]))
            y0=DENSITY_ZOOM['ylim'][0]
            assert DENSITY_ZOOM['xlim'][0]<log_median<DENSITY_ZOOM['xlim'][1]
            assert y0<density_at_median<DENSITY_ZOOM['ylim'][1]
            peak_zoom.plot([log_median,log_median],[y0,density_at_median],
                color=COLORS[year],linewidth=.5,linestyle=(0,(2,1.8)),zorder=1.5)
            median_guides.append(dict(parent=letter,inset=letter+'_zoom',side=side,year=year,
                countries=len(values),median_share_percent=median,log10_median_share_percent=log_median,
                density_at_median=density_at_median,line_y0=y0,line_y1=density_at_median,colour=COLORS[year]))
        zoom_checks.extend(zs);zoom_vertices.extend(zv)
        zoom_windows.append(dict(parent=letter,side=side,kind='density_peak',
            xmin=DENSITY_ZOOM['xlim'][0],xmax=DENSITY_ZOOM['xlim'][1],
            ymin=DENSITY_ZOOM['ylim'][0],ymax=DENSITY_ZOOM['ylim'][1],
            x_coordinate='log10 country share percent',y_coordinate='density per log10 unit'))
    fig.legend(handles=[Line2D([],[],color=COLORS[y],linewidth=1.3,label=str(y)) for y in YEARS],
        loc='upper center',bbox_to_anchor=(.52,upper_y(.995)),ncol=4,fontsize=font_size(7.3),
        handlelength=2.2,columnspacing=2.2,borderaxespad=0)

    # Each lower direction group is a 1x2 pair, exactly beneath its parent column.
    lower_y=(height_pt+square_height_reduction_pt-(366-row_gap_reduction_pt))/height_pt
    lower_h=lower_size_pt/height_pt
    lower_axes={};secondary_axes=[];annual_series=[];reference_guides=[]
    for side,group,left in [('inflow','c',.08),('outflow','d',.58)]:
        l=fig.add_axes([left,lower_y,lower_size_pt/WIDTH_PT,lower_h]);l.set_gid(group)
        t=fig.add_axes([left+(lower_size_pt+within_pair_gutter_pt)/WIDTH_PT,lower_y,lower_size_pt/WIDTH_PT,lower_h]);t.set_gid(group+'_annual')
        lower_axes[group]=l;lower_axes[group+'_annual']=t
        for ax in [l,t]:
            ax.set_box_aspect(1)
            ax.tick_params(labelsize=font_size(6),length=2,width=.5,pad=2.4)
        l.text(-.13*.385*WIDTH_PT/lower_size_pt,1.06,group,transform=l.transAxes,
            fontsize=font_size(10),fontweight='bold',ha='left',va='bottom')
        equality_line,=l.plot([0,100],[0,100],color='#B2B8BD',linestyle=(0,(2.5,2)),linewidth=.6,zorder=1)
        lorenz_paths=[]
        for year in YEARS:
            rs=[r for r in lorenz if r['side']==side and r['year']==year]
            xs=np.array([100*r['cumulative_country_fraction'] for r in rs])
            ys=np.array([100*r['cumulative_flow_fraction'] for r in rs])
            l.plot(xs,ys,color=COLORS[year],linewidth=1.05,zorder=2)
            lorenz_paths.append((year,xs,ys))
        l.set(xlim=(0,100),ylim=(0,100))
        l.set_xticks([0,50,100]);l.set_yticks([0,50,100])
        l.set_xlabel('Countries (%)',fontsize=font_size(6.7),labelpad=4)
        l.set_ylabel('Cumulative flow (%)',fontsize=font_size(6.5),labelpad=3)
        lorenz_zoom,zs,zv=add_zoom_inset(fig,l,lorenz_paths,LORENZ_ZOOM,
            [75,85,93],['75','85','93'],[5,15,30],['5','15','30'],'upper_right')
        reference_guides.append((l,equality_line,lorenz_zoom))
        zoom_checks.extend(zs);zoom_vertices.extend(zv)
        zoom_windows.append(dict(parent=group,side=side,kind='Lorenz_detail',
            xmin=LORENZ_ZOOM['xlim'][0],xmax=LORENZ_ZOOM['xlim'][1],
            ymin=LORENZ_ZOOM['ylim'][0],ymax=LORENZ_ZOOM['ylim'][1],
            x_coordinate='cumulative country percent',y_coordinate='cumulative flow percent'))
        annual=sorted([r for r in metrics if r['side']==side],key=lambda r:r['year'])
        right=t.twinx();right.set_gid(group+'_gini_right');secondary_axes.append(right)
        right.patch.set_visible(False);right.spines['left'].set_visible(False)
        right.spines['bottom'].set_visible(False);right.spines['top'].set_visible(False)
        right.spines['right'].set_visible(True);right.spines['right'].set_linewidth(.6)
        t.plot([r['year'] for r in annual],[r['HHI'] for r in annual],color=BLUE,
            linewidth=1.15,marker='o',markersize=1.8,markeredgewidth=0,zorder=2)
        right.plot([r['year'] for r in annual],[r['Gini'] for r in annual],color=RED,
            linewidth=1.15,marker='o',markersize=1.8,markeredgewidth=0,zorder=2)
        t.set(xlim=(1996,2027),ylim=(.06,.11));t.set_xticks([1998,2012,2025])
        t.set_yticks([.06,.08,.10],['0.06','0.08','0.10'])
        right.set_ylim(.84,.94);right.set_yticks([.85,.90],['0.85','0.90'])
        right.tick_params(length=1.2,width=.5,pad=.5,colors='black')
        t.set_xlabel('Year',fontsize=font_size(6.7),labelpad=4)
        t.set_ylabel('HHI',fontsize=font_size(6.5),labelpad=3)
        right.set_ylabel('Gini',fontsize=font_size(6.5),labelpad=3)
        t.yaxis.set_label_coords(-.38,.5);right.yaxis.set_label_coords(.84,.5)
        t.legend(handles=[Line2D([],[],color=BLUE,linewidth=1.15,label='HHI'),
            Line2D([],[],color=RED,linewidth=1.15,label='Gini')],loc='upper right',
            borderaxespad=.15,handlelength=1.2,handletextpad=.4,labelspacing=.2,borderpad=0)
        for metric,axis in [('HHI',t),('Gini',right)]:
            annual_series.extend(dict(panel=group+'_annual',axes_id=axis.get_gid(),side=side,
                metric=metric,year=r['year'],value=r[metric],axis='left' if metric=='HHI' else 'right') for r in annual)
    fig.canvas.draw()
    # The middle gutter separates the two directional groups. The two within-
    # group gutters and every matched main/inset rectangle are audited in pairs.
    apply_axes_typography(fig,grid_json_out=QA/'grid.json')
    fig.canvas.draw()
    # Interrupt only the equality reference beneath the zoom footprint, so
    # its tick labels remain clear. Every observed Lorenz path stays intact.
    for parent,guide,small in reference_guides:
        footprint=small.get_tightbbox(fig.canvas.get_renderer()).padded(1.5*fig.dpi/72)
        bounds=parent.transData.inverted().transform([[footprint.x0,footprint.y0],[footprint.x1,footprint.y1]])
        enter=max(0.,bounds[0,0],bounds[0,1]);leave=min(100.,bounds[1,0],bounds[1,1])
        if enter<leave:
            points=[0,enter,np.nan,leave,100];guide.set_data(points,points)
    fig.canvas.draw()
    proportional_zoom_checks=[]
    for window in zoom_windows:
        parent=next(a for a in fig.axes if a.get_gid()==window['parent'])
        small=next(a for a in fig.axes if a.get_gid()==window['parent']+'_zoom')
        bounds=np.array([[window['xmin'],window['ymin']],[window['xmax'],window['ymax']]])
        source=parent.transData.transform(bounds)/fig.dpi*72
        inset=small.transData.transform(bounds)/fig.dpi*72
        source_size=source[1]-source[0];inset_size=inset[1]-inset[0]
        scales=inset_size/source_size
        assert abs(scales[0]-scales[1])<1e-10
        assert np.allclose(small.get_xlim(),[window['xmin'],window['xmax']],rtol=0,atol=1e-12)
        assert np.allclose(small.get_ylim(),[window['ymin'],window['ymax']],rtol=0,atol=1e-12)
        proportional_zoom_checks.append(dict(parent=window['parent'],inset=small.get_gid(),
            source_width_pt=float(source_size[0]),source_height_pt=float(source_size[1]),
            inset_width_pt=float(inset_size[0]),inset_height_pt=float(inset_size[1]),
            magnification_x=float(scales[0]),magnification_y=float(scales[1]),
            source_aspect_ratio=float(source_size[0]/source_size[1]),
            inset_aspect_ratio=float(inset_size[0]/inset_size[1]),identical_coordinate_limits=True))
    for record in median_guides:
        small=next(a for a in fig.axes if a.get_gid()==record['inset'])
        vertices=small.transData.transform([[record['log10_median_share_percent'],record['line_y0']],
            [record['log10_median_share_percent'],record['line_y1']]])/fig.dpi*72
        record.update(pdf_x_pt=float(vertices[0,0]),pdf_y0_pt=float(height_pt-vertices[0,1]),
            pdf_y1_pt=float(height_pt-vertices[1,1]))
    write_csv('Fig3_density_median_guides.csv',median_guides)
    for record in annual_series:
        small=next(a for a in fig.axes if a.get_gid()==record['axes_id'])
        xy=small.transData.transform((record['year'],record['value']))/fig.dpi*72
        record.update(pdf_x_pt=float(xy[0]),pdf_y_pt=float(height_pt-xy[1]))
    write_csv('Fig3_annual_dual_axis_plotted_values.csv',annual_series)
    require_matplotlib_panel_alignment(fig,json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',
        tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True,
        row_groups=[['a','b'],['a_zoom','b_zoom'],['c','c_annual'],['d','d_annual'],
                    ['c','d'],['c_annual','d_annual'],['c_zoom','d_zoom']],
        column_groups=[],exemptions=[dict(panels=[a.get_gid() for a in secondary_axes],checks=['all'],
            reason='Secondary Gini y axes intentionally share the square annual HHI plotting rectangles; compare the primary panels separately.')])
    stem=OUT/'Fig3'
    fig.savefig(stem.with_suffix('.pdf'))
    fig.savefig(stem.with_suffix('.svg'))
    png_buffer=io.BytesIO();fig.savefig(png_buffer,format='png',dpi=600)
    stem.with_suffix('.png').write_bytes(png_buffer.getvalue())
    with pymupdf.open(stem.with_suffix('.pdf')) as doc:
        page=doc[0]
        page.get_pixmap(matrix=pymupdf.Matrix(2.4,2.4),alpha=False).save(QA/'preview.png')
        page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=pymupdf.Rect(0,235-row_gap_reduction_pt,page.rect.width,page.rect.height),alpha=False).save(QA/'preview_lower.png')
        dimensions=[page.rect.width*25.4/72,page.rect.height*25.4/72]
        fonts=sorted({f[3] for f in page.get_fonts()})
    write_csv('Fig3_zoom_windows.csv',zoom_windows)
    write_csv('Fig3_zoom_curves.csv',zoom_vertices)
    manifest=dict(figure='Fig3',edition='v3',stage='Complete 2+4 layout: four framed local zooms and two square annual HHI-Gini dual-axis plots; HHI and cumulative-share insets removed',
        dimensions_mm=dimensions,fonts_pdf=fonts,years=YEARS,palette=COLORS,
        input=str(CANONICAL.relative_to(ROOT)),input_sha256=sha256(CANONICAL),
        cleaned_margins_reconciled_exactly=True,annual_tier='top100pct, all fields',
        claim='Country-level international flow distributions show long-term deconcentration, assessed through share density, Lorenz curves and paired annual HHI and Gini',
        archetype='quantitative grid',
        panels=dict(a='Country inflow-share density with an isotropic peak zoom at upper right; no annual HHI inset',
            b='Country outflow-share density, matching inflow density and peak zoom',
            c='Inflow group: Lorenz curves with local zoom; annual HHI (blue, left axis) and Gini (red, right axis) in one square plot',
            d='Outflow group, matching the two inflow plots and insets'),
        lower_layout=dict(plot_width_fraction=lower_size_pt/WIDTH_PT,plot_height_pt=lower_size_pt,plot_width_pt=lower_size_pt,
            square_main_plots=['c','c_annual','d','d_annual'],square_height_reduction_pt=square_height_reduction_pt,physical_first_row_preserved=True,
            row_gap_reduction_pt=row_gap_reduction_pt,plot_area_row_gap_pt=39.662992,
            within_direction_pair_gutter_pt=within_pair_gutter_pt,
            annual_right_edges_match_density_right_edges=True,
            audit_rule='Compare each 1x2 pair and corresponding plots/insets between flow directions; central gutter intentionally separates groups'),
        density_definition='Equal-country Gaussian kernel density of log10 national percentage shares, with one common bandwidth',
        x_axis='Log10 share coordinates in a,b, tick labels in actual percentages; no yearly standardization',
        density_display_xlim=density_xlim,all_observed_shares_inside_display_limits=True,
        density_measure='Probability per log10 unit; each density integrates to one in log coordinates',
        bandwidth=dict(method='Pooled absolute Silverman bandwidth, using median snapshot country count',
            log10_units=bandwidth,identical_for_all_eight_curves=True),
        boundary='Reflect kernels at log10(100%)=2',
        sample='All countries with positive international flow in the corresponding year and direction',
        zero_rule='Zero-flow countries excluded from density and Lorenz samples',
        rugs='Removed as requested; all countries remain in the unchanged density estimates and source data',
        normalized_equivalent_definition='Auxiliary annual metric only: 1/(N*HHI), with N positive-flow countries; not displayed in the current inset',
        statistics='Descriptive observations and distributions; fills are density areas, not confidence intervals',
        density_integral_checks=checks,snapshot_metrics=[m for m in metrics if m['year'] in YEARS],
        source_data=['Fig3_country_year_data.csv','Fig3_country_metrics.csv','Fig3_density_curves.csv',
            'Fig3_annual_dual_axis_plotted_values.csv','Fig3_lorenz_curves.csv',
            'Fig3_zoom_windows.csv','Fig3_zoom_curves.csv','Fig3_density_median_guides.csv'],
        auxiliary_data=['Fig3_top_country_shares.csv','Fig3_distribution_insets.csv'],
        historical_geometry_tables=['Fig3_coverage_inset_plotted_values.csv','Fig3_top_country_inset_plotted_values.csv'],
        annual_dual_axes=dict(HHI=dict(axis='left',range=[.06,.11],colour=BLUE),Gini=dict(axis='right',range=[.84,.94],colour=RED),
            observations_per_metric_per_direction=28,line_values=112,independent_metric_scales=True,
            axis_colours='Black',legend='Metric-coloured solid lines in each annual plot; year colours are used only by density and Lorenz snapshots',
            marker_policy='Small metric-coloured markers show all annual observations'),
        zoom_windows=zoom_windows,zoom_source_coordinate_checks=zoom_checks,
        zoom_method='Clip exact parent paths to identical framed bounds, then enlarge with equal horizontal and vertical physical magnification; no refit, resmoothing or standardization',
        proportional_zoom_checks=proportional_zoom_checks,
        density_median_guides=dict(count=8,definition='Median of raw country percentage shares in each year and direction; logarithm applied after taking the median',
            style='Year-coloured thin dashed vertical guides from the lower zoom boundary to the corresponding density curve; no shifting of close medians'),
        removed_insets=['a_hhi','b_hhi','c_top_shares','d_top_shares'])
    manifest['formatting']=specification()
    (QA/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    plt.close(fig)
    print(json.dumps(dict(outputs=[str(stem.with_suffix(s)) for s in ['.pdf','.svg','.png']],
        dimensions_mm=dimensions,bandwidth_log10=bandwidth,main_axes=6,secondary_axes=2,insets=4),ensure_ascii=False))


if __name__=='__main__':
    main()
