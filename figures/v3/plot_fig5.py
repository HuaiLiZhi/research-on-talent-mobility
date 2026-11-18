"""Fig5: country means plus international-share groups and domestic urban trends.
Python/matplotlib; all 76 countries and all 28 years, with a linked distribution row.
"""
from __future__ import annotations

import csv
import io
import json
import math
import sys
from pathlib import Path

from figure_style import font_size, output_root, WIDTH_PT, PROFILE, specification, apply_axes_typography

ROOT = Path(__file__).resolve().parents[2]
OUT = output_root(Path(__file__).resolve().parent)
DATA = OUT / 'source_data'
QA = OUT / 'QA/Fig5'
SKILL = Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa'
sys.path[:0] = [str(ROOT/'tmp/nhb_fig2_python_deps'), str(SKILL)]

import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, ConnectionPatch
from matplotlib.path import Path as PlotPath
from matplotlib.ticker import FormatStrFormatter, FuncFormatter, NullLocator
from matplotlib.transforms import Bbox
from matplotlib.colors import LinearSegmentedColormap,LogNorm
from scipy import stats
import pymupdf
from audit_panel_alignment import require_matplotlib_panel_alignment

from figure_palette import BLUE, RED, GRAY, GREEN, YELLOW
INK = '#000000'
MARKER_COLOR = '#4A4A4A'
MARKER_ALPHA = .70
COLORS = {'inflow': BLUE, 'outflow': RED}
SIDES = ('inflow', 'outflow')


def read(name):
    with (DATA/name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(name, rows):
    with (DATA/name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def label_countries(fig, ax, rows, chosen, font, excluded=(), line_obstacles=(), point_clearance=1.5, leader_clearance=2.8, minimum_label_gap=8, direct_label_radius=8, maximum_label_radius=70):
    """Prefer nearby direct labels; keep the entire label in its point quadrant."""
    renderer = fig.canvas.get_renderer()
    scale = fig.dpi/72
    point_xy = {r['country']: ax.transData.transform((r['x'], r['y']))/scale for r in rows}
    axis_bbox = Bbox.from_extents(*(ax.get_window_extent().extents/scale)).padded(-2)
    origin = ax.transData.transform((0, 0))/scale
    fixed_boxes = list(excluded)
    fixed_paths = [PlotPath(np.asarray(p)) for p in line_obstacles]
    candidates = {}
    for cc in chosen:
        r = next(r for r in rows if r['country'] == cc)
        x, y = point_xy[cc]
        options = []
        for distance in [4, 6, 8, 10, 13, 16, 20, 25, 30, 36, 44, 52, 60, 70]:
            if distance>maximum_label_radius:continue
            for angle in [45, 135, -45, -135, 90, -90, 0, 180, 30, 150, -30, -150, 60, 120, -60, -120]:
                dx = distance*math.cos(math.radians(angle))
                dy = distance*math.sin(math.radians(angle))
                ha = 'left' if dx > 1 else 'right' if dx < -1 else 'center'
                va = 'bottom' if dy > 1 else 'top' if dy < -1 else 'center'
                text = ax.annotate(cc, (r['x'], r['y']), xytext=(dx, dy), textcoords='offset points',
                    ha=ha, va=va, fontsize=font, color=INK, zorder=12)
                bb = Bbox.from_extents(*(text.get_window_extent(renderer).extents/scale))
                pad = bb.padded(1.2)
                valid = axis_bbox.contains(bb.x0, bb.y0) and axis_bbox.contains(bb.x1, bb.y1)
                valid &= not any(pad.overlaps(other) for other in fixed_boxes)
                # No label covers another point, a zero reference line, or the wrong quadrant.
                valid &= not any(pad.padded(point_clearance).contains(*p) for p in point_xy.values())
                valid &= (bb.x0 > origin[0]+3.3 if r['x'] > 0 else bb.x1 < origin[0]-3.3)
                valid &= (bb.y0 > origin[1]+3.3 if r['y'] > 0 else bb.y1 < origin[1]-3.3)
                valid &= not any(path.intersects_bbox(pad, filled=False) for path in fixed_paths)
                leader_path = None
                if valid and distance > direct_label_radius:
                    nearest = np.array([np.clip(x, bb.x0, bb.x1), np.clip(y, bb.y0, bb.y1)])
                    delta = nearest - np.array([x,y])
                    length = np.linalg.norm(delta)
                    begin = np.array([x,y]) + delta/length*3.1
                    end = nearest - delta/length*1.2
                    leader_path = PlotPath(np.vstack([begin,end]))
                    valid &= not any(leader_path.intersects_bbox(other.padded(.8), filled=False) for other in fixed_boxes)
                    segment = end-begin
                    segment_norm = float(segment@segment)
                    for other_cc, other_point in point_xy.items():
                        if other_cc == cc:
                            continue
                        fraction = np.clip((other_point-begin)@segment/segment_norm,0,1)
                        valid &= np.linalg.norm(other_point-(begin+fraction*segment))>leader_clearance
                if valid:
                    options.append(dict(dx=dx, dy=dy, ha=ha, va=va, bb=bb, path=leader_path,
                        distance=distance))
                text.remove()
        if not options:
            raise RuntimeError(f'No static label candidates: {ax.get_gid()} {cc}')
        candidates[cc] = options
    order = sorted(chosen, key=lambda cc: len(candidates[cc]))
    solution = {}
    searched = [0]

    from functools import lru_cache
    @lru_cache(None)
    def compatible(cc,i,other_cc,j):
        option=candidates[cc][i];o=candidates[other_cc][j]
        box,path,other=option['bb'],option['path'],o['bb']
        if box.padded(.8).overlaps(other.padded(.8)):return False
        gap=max(box.x0-other.x1,other.x0-box.x1,0)
        if gap<minimum_label_gap and abs((box.y0+box.y1-other.y0-other.y1)/2)<font*.95:
            return False
        if o['path'] is not None and o['path'].intersects_bbox(box.padded(.8),filled=False):return False
        if path is not None and path.intersects_bbox(other.padded(.8),filled=False):return False
        return True

    def place(domains):
        if not domains:return True
        cc=min(domains,key=lambda c:len(domains[c]))
        for i in domains[cc]:
            searched[0]+=1
            if searched[0]>100000:return False
            remaining={c:[j for j in choices if compatible(cc,i,c,j)] for c,choices in domains.items() if c!=cc}
            if any(not choices for choices in remaining.values()):continue
            solution[cc]=candidates[cc][i]
            if place(remaining):return True
            del solution[cc]
        return False

    if not place({cc:list(range(len(candidates[cc]))) for cc in chosen}):
        fig.savefig(QA/'annotation_layout_debug.png',dpi=300)
        raise RuntimeError(f'No nonoverlapping annotation arrangement: {ax.get_gid()}, candidates '+str({cc:len(candidates[cc]) for cc in order})+' nodes '+str(searched[0]))
    labels = []
    for cc in chosen:
        r = next(r for r in rows if r['country'] == cc)
        option = solution[cc]
        ax.annotate(cc, (r['x'],r['y']), xytext=(option['dx'],option['dy']), textcoords='offset points',
            ha=option['ha'], va=option['va'], fontsize=font, color=INK, zorder=12)
        leader = option['path'] is not None
        if leader:
            points = ax.transData.inverted().transform(option['path'].vertices*scale)
            ax.plot(points[:, 0], points[:, 1], color='#7B838C', lw=.4, zorder=10)
        labels.append(dict(panel=ax.get_gid(), country=cc, point_x=r['x'], point_y=r['y'],
            label_x=float(option['dx']), label_y=float(option['dy']),
            offset_unit='points', leader=leader, fontsize=font))
    return labels




def main():
    QA.mkdir(parents=True,exist_ok=True)
    means=read('Fig5_combined_country_mean_levels.csv')
    fits=read('Fig5_combined_fits.csv');curves=read('Fig5_combined_fit_curves.csv')
    trends=read('Fig5_stratified_country_trends.csv')
    groups=read('Fig5_stratified_groups.csv')
    stratification=json.loads((QA/'stratified_data_manifest.json').read_text(encoding='utf8'))
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Helvetica','Arial'],
        'font.size':font_size(7),'axes.labelsize':font_size(7),'xtick.labelsize':font_size(6.5),'ytick.labelsize':font_size(6.5),
        'axes.linewidth':.55,'axes.spines.top':False,'axes.spines.right':False,
        'text.color':INK,'axes.labelcolor':INK,'xtick.color':INK,'ytick.color':INK,
        'axes.unicode_minus':False,'legend.frameon':False,'pdf.use14corefonts':True,
        'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white','path.simplify':False})
    width_pt=WIDTH_PT;height_pt=425.
    main_width=(width_pt-49-6-64)/3
    lower_width=105.
    lower_gutter=(width_pt-49-6-4*lower_width)/3
    assert lower_gutter>0
    fig=plt.figure(figsize=(width_pt/72,height_pt/72),dpi=300);scale=fig.dpi/72
    grid=fig.add_gridspec(1,3,left=49/width_pt,right=(width_pt-6)/width_pt,bottom=255/height_pt,
        top=(255+main_width)/height_pt,wspace=32/main_width)
    axes=[];labels=[];points=[];rendered_fits=[];panel_specs=[]
    for col,metric in enumerate(['HHI','Gini']):
        letter='ab'[col];color=[BLUE,RED][col]
        ax=fig.add_subplot(grid[0,col]);ax.set_gid(letter);axes.append(ax)
        rows=[dict(country=r['country'],x=float(r['mean_annual_international_flow']),
            y=float(r['mean_domestic_'+metric]),total_international_events=float(r['total_international_events'])) for r in means]
        assert len(rows)==76 and all(r['x']>0 and 0<r['y']<1 for r in rows)
        ax.set_xscale('log');ax.set_xlim(100,400000)
        ax.set_xticks([100,1000,10000,100000]);ax.xaxis.set_major_formatter(FuncFormatter(lambda v,p:f'{v:,.0f}'))
        ax.xaxis.set_minor_locator(NullLocator())
        if metric=='HHI':
            ax.set_yscale('log');ax.set_ylim(.005,.8);ax.set_yticks([.01,.03,.1,.3])
            ax.yaxis.set_minor_locator(NullLocator())
            ax.set_ylabel('Domestic HHI',labelpad=6)
        else:
            ax.set_ylim(.2,1.);ax.set_yticks([.2,.4,.6,.8,1.])
            ax.set_ylabel('Domestic Gini',labelpad=6)
        ax.yaxis.set_major_formatter(FormatStrFormatter('%g'));ax.tick_params(length=2.5,width=.5,pad=3)
        curve=[r for r in curves if r['metric']==metric]
        xx=np.array([float(r['x']) for r in curve]);yy=np.array([float(r['y']) for r in curve])
        low=np.array([float(r['ci_low']) for r in curve]);high=np.array([float(r['ci_high']) for r in curve])
        assert np.all(np.diff(xx)>0) and np.all(low>0) and np.all(low<=high)
        if metric=='Gini':assert np.all(high<1)
        ax.fill_between(xx,low,high,color=color,alpha=.13,linewidth=0,zorder=.4)
        ax.plot(xx,yy,color=color,lw=1.1,zorder=1.5)
        ax.scatter([r['x'] for r in rows],[r['y'] for r in rows],s=20,color=MARKER_COLOR,
            alpha=MARKER_ALPHA,edgecolors='none',linewidths=0,zorder=3)
        ax.set_xlabel('International mobility\n(events/year)',labelpad=5)
        fit=next(r for r in fits if r['metric']==metric)
        rho=float(fit['spearman_r'])
        ax.set_title(f'Spearman r = {rho:.2f}',fontsize=font_size(8),pad=10)
        ax.text(-34/190,1+10/190,letter,transform=ax.transAxes,fontsize=font_size(9.2),fontweight='bold',ha='left',va='bottom')
        major=[r['country'] for r in sorted(rows,key=lambda r:-r['total_international_events'])[:15]]
        bins=np.linspace(min(np.log10(r['x']) for r in rows),max(np.log10(r['x']) for r in rows)+1e-9,5)
        representatives=[]
        for lo,hi in zip(bins,bins[1:]):
            within=[r for r in rows if lo<=np.log10(r['x'])<hi]
            if within:representatives.extend([min(within,key=lambda r:r['y'])['country'],max(within,key=lambda r:r['y'])['country']])
        chosen=major[:10] if PROFILE=='manuscript' else major;fig.canvas.draw()
        obstacles=[ax.transData.transform(np.column_stack([xx,v]))/scale for v in [yy,low,high]]
        labels+=label_countries(fig,ax,rows,chosen,font_size(6.0),line_obstacles=obstacles,
            direct_label_radius=16 if letter=='b' else 8,
            minimum_label_gap=8,
            maximum_label_radius=30 if letter=='b' else 70)
        for r in rows:
            px,py=ax.transData.transform((r['x'],r['y']))/scale
            points.append(dict(panel=letter,country=r['country'],metric='mean_domestic_'+metric,x=r['x'],y=r['y'],
                pdf_x_pt=float(px),pdf_y_pt=float(height_pt-py),labelled=r['country'] in chosen,major_country=r['country'] in major))
        for r in curve:
            xy=ax.transData.transform((float(r['x']),float(r['y'])))/scale
            rendered_fits.append(dict(r,panel=letter,pdf_x_pt=float(xy[0]),pdf_y_pt=float(height_pt-xy[1])))
        pos=ax.get_position()
        panel_specs.append(dict(panel=letter,metric=metric,xlim=[100,400000],ylim=list(ax.get_ylim()),xscale='log',yscale=ax.get_yscale(),
            bbox_pdf_pt=[pos.x0*width_pt,height_pt-pos.y1*height_pt,pos.x1*width_pt,height_pt-pos.y0*height_pt],
            labelled_countries=chosen,label_log10_x_band_edges=bins.tolist(),fit_y_transform=fit['y_transform']))
    # Full-period share trajectories define four disjoint country groups.
    # The lower row retains one equally weighted observation per country.
    ax=fig.add_subplot(grid[0,2]);ax.set_gid('c');axes.append(ax)
    rate=np.array([float(r['international_share_annual_rate_pct']) for r in trends])
    cuts=np.asarray(stratification['quartile_cuts'])
    group_colors=[BLUE,GRAY,GREEN,RED]
    xlimits=[-5.,12.]
    edges=np.linspace(*xlimits,23)
    counts,_=np.histogram(rate,bins=edges)
    assert int(counts.sum())==76 and np.all((rate>xlimits[0])&(rate<xlimits[1]))
    boundaries=np.r_[xlimits[0],cuts,xlimits[1]]
    for j,(lo,hi) in enumerate(zip(boundaries[:-1],boundaries[1:])):
        local_edges=np.r_[lo,edges[(edges>lo)&(edges<hi)],hi]
        mid=(local_edges[:-1]+local_edges[1:])/2
        local_counts=counts[np.searchsorted(edges,mid,side='right')-1]
        ax.stairs(local_counts,local_edges,baseline=0,fill=True,color=group_colors[j],alpha=.23,linewidth=0)
    ax.stairs(counts,edges,color='#3F776A',linewidth=1.1,zorder=3)
    ax.set_xlim(*xlimits);ax.set_ylim(0,counts.max()*1.30)
    ax.set_xticks([-5,0,5,10]);ax.set_yticks([0,4,8,12])
    ax.set_ylabel('Countries',labelpad=6)
    ax.set_xlabel('Share growth (%/year)',labelpad=15)
    ax.xaxis.set_label_position('top')
    ax.tick_params(length=2.5,width=.5,pad=3)
    for value,percentile in zip(cuts,[25,50,75]):
        label_level=.78 if percentile==50 else .92
        ax.axvline(value,ymax=label_level-.08,color='#747C80',lw=.55,ls=(0,(3,2)))
        ax.text(value,ax.get_ylim()[1]*label_level,f'{percentile}%',ha='center',va='bottom',fontsize=font_size(6.5))
    ax.text(-34/190,1+10/190,'c',transform=ax.transAxes,fontsize=font_size(9.2),fontweight='bold',ha='left',va='bottom')
    fig.canvas.draw()
    positions=[]
    for j,(lo,hi) in enumerate(zip(boundaries[:-1],boundaries[1:])):
        x0=ax.transData.transform((lo,0))[0]/scale
        x1=ax.transData.transform((hi,0))[0]/scale
        midpoint=(x0+x1)/2
        fig.add_artist(Line2D([(x0+1)/width_pt,(x1-1)/width_pt],[230/height_pt]*2,
            transform=fig.transFigure,color=group_colors[j],lw=2.0,solid_capstyle='butt'))
        fig.text(midpoint/width_pt,237/height_pt,f'T{j+1}',ha='center',va='center',fontsize=font_size(6.5))
        positions.append(midpoint)
    histograms=[dict(panel='c',bin=j+1,lower=float(edges[j]),upper=float(edges[j+1]),countries=int(n))
                for j,n in enumerate(counts)]
    write('Fig5_stratified_histogram.csv',histograms)
    pos=ax.get_position()
    panel_specs.append(dict(panel='c',metric='international_share_annual_rate_pct',xlim=xlimits,
        ylim=list(ax.get_ylim()),xscale='linear',yscale='linear',observations=76,
        quartile_cuts=cuts.tolist(),histogram_bins=22,
        bbox_pdf_pt=[pos.x0*width_pt,height_pt-pos.y1*height_pt,pos.x1*width_pt,height_pt-pos.y0*height_pt]))
    # Use the same absolute smoothing bandwidth and axes for all four groups.
    domestic=np.array([float(r['domestic_gini_trend_pp_decade']) for r in trends])
    robust_sd=min(float(np.std(domestic,ddof=1)),float(np.subtract(*np.percentile(domestic,[75,25]))/1.34))
    bandwidth=.9*robust_sd*19**(-.2)
    xx=np.linspace(-5,22,401)
    densities={}
    for group in range(1,5):
        vals=np.array([float(r['domestic_gini_trend_pp_decade']) for r in trends if int(r['group'])==group])
        densities[group]=np.exp(-.5*((xx[:,None]-vals[None,:])/bandwidth)**2).mean(axis=1)/(bandwidth*np.sqrt(2*np.pi))
    ymax=max(v.max() for v in densities.values())*1.27
    density_rows=[];rug_rows=[]
    lower=fig.add_gridspec(1,4,left=49/width_pt,right=(width_pt-6)/width_pt,bottom=48/height_pt,
        top=(48+lower_width)/height_pt,wspace=lower_gutter/lower_width)
    for j,group in enumerate(range(1,5)):
        letter='defg'[j];color=group_colors[j]
        sub=fig.add_subplot(lower[0,j]);sub.set_gid(letter);axes.append(sub)
        sub.set_box_aspect(1)
        rows=sorted([r for r in trends if int(r['group'])==group],key=lambda r:r['country'])
        vals=np.array([float(r['domestic_gini_trend_pp_decade']) for r in rows])
        density=densities[group];median=float(np.median(vals))
        sub.fill_between(xx,0,density,color=color,alpha=.17,linewidth=0,zorder=1)
        sub.plot(xx,density,color=color,lw=1.1,zorder=2)
        sub.axvline(0,color='#899095',lw=.55,ls=(0,(2,2)),zorder=.5)
        median_height=float(np.interp(median,xx,density))
        sub.plot([median,median],[0,median_height],color=YELLOW,lw=1.2,ls=(0,(4,2)),zorder=4)
        # This narrow strip shows country values; its vertical jitter is display-only.
        rng=np.random.default_rng(1290+group)
        strip_y=ymax*(.025+.022*rng.random(len(rows)))
        sub.scatter(vals,strip_y,s=8,color=MARKER_COLOR,alpha=MARKER_ALPHA,edgecolors='none',linewidths=0,zorder=5)
        sub.set_xlim(-5,22);sub.set_ylim(0,ymax)
        sub.set_xticks([0,10,20]);sub.tick_params(length=2.5,width=.5,pad=3)
        sub.yaxis.set_major_locator(mpl.ticker.MaxNLocator(nbins=3))
        sub.yaxis.set_major_formatter(FormatStrFormatter('%g'))
        if j==0:sub.set_ylabel('Density',labelpad=6)
        else:sub.tick_params(axis='y',labelleft=False)
        lo,hi=boundaries[j:j+2]
        interval=(f'< {hi:.2f}%' if j==0 else f'>= {lo:.2f}%' if j==3 else f'{lo:.2f} to {hi:.2f}%')
        sub.set_title(f'T{group}\n{interval}',fontsize=font_size(7),pad=8,linespacing=1.4)
        sub.text(-.05,1.20,letter,transform=sub.transAxes,fontsize=font_size(9.2),fontweight='bold',ha='left',va='bottom')
        sub.text(.97,.96,f'Median {median:.2f}',transform=sub.transAxes,ha='right',va='top',fontsize=font_size(6.5))
        target=(sub.get_position().x0+sub.get_position().x1)*width_pt/2
        # Route the guide below all upper-row axis labels.
        connector=[(positions[j],226),(positions[j],210),(target,187)]
        fig.add_artist(Line2D([p[0]/width_pt for p in connector],[p[1]/height_pt for p in connector],
            transform=fig.transFigure,color=color,lw=.55,alpha=.75,zorder=0))
        fig.canvas.draw()
        for r,x,y in zip(rows,vals,strip_y):
            pdf=sub.transData.transform((x,y))/scale
            rug_rows.append(dict(panel=letter,country=r['country'],group=group,x=float(x),display_y=float(y),
                pdf_x_pt=float(pdf[0]),pdf_y_pt=float(height_pt-pdf[1])))
        for x,y in zip(xx,density):
            pdf=sub.transData.transform((x,y))/scale
            density_rows.append(dict(panel=letter,group=group,x=float(x),density=float(y),bandwidth=float(bandwidth),
                pdf_x_pt=float(pdf[0]),pdf_y_pt=float(height_pt-pdf[1])))
        p=sub.get_position()
        panel_specs.append(dict(panel=letter,metric='domestic_gini_trend_pp_decade',group=group,
            xlim=[-5,22],ylim=[0,float(ymax)],xscale='linear',yscale='linear',observations=19,
            median=median,bandwidth=float(bandwidth),country_codes=[r['country'] for r in rows],
            bbox_pdf_pt=[p.x0*width_pt,height_pt-p.y1*height_pt,p.x1*width_pt,height_pt-p.y0*height_pt]))
    footer_centre=(49+width_pt-6)/2
    footer_label=fig.text(footer_centre/width_pt,12/height_pt,'Domestic Gini trend (pp/decade)',
        ha='center',va='center',fontsize=font_size(7))
    footer_legend=fig.legend(handles=[Line2D([0],[0],color=YELLOW,lw=1.2,ls=(0,(4,2)),label='Median'),
                        Line2D([0],[0],color='#899095',lw=.55,ls=(0,(2,2)),label='No change')],
        loc='center right',bbox_to_anchor=((width_pt-6)/width_pt,30/height_pt),ncol=2,
        fontsize=font_size(6.5),handlelength=1.4,columnspacing=.8,handletextpad=.45,
        borderaxespad=0,borderpad=0)
    write('Fig5_stratified_density_curves.csv',density_rows)
    write('Fig5_stratified_country_strip.csv',rug_rows)
    fig.canvas.draw()
    apply_axes_typography(fig,grid_json_out=QA/'grid.json')
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    tick_boxes=[text.get_window_extent(renderer).extents/scale for ax in axes if ax.get_gid() in 'defg'
        for text in ax.get_xticklabels() if text.get_visible() and text.get_text()]
    tick_bottom=min(b[1] for b in tick_boxes)
    # One compact footer row: the axis title is centred on all four panels,
    # and the legend occupies the available space at the far right.
    label_height=footer_label.get_window_extent(renderer).height/scale
    legend_height=footer_legend.get_window_extent(renderer).height/scale
    footer_y=tick_bottom-2.5-max(label_height,legend_height)/2
    footer_label.set_position((footer_centre/width_pt,footer_y/height_pt))
    footer_legend.set_bbox_to_anchor(((width_pt-6)/width_pt,footer_y/height_pt))
    fig.canvas.draw()
    name_box=footer_label.get_window_extent(renderer).extents/scale
    legend_box=footer_legend.get_window_extent(renderer).extents/scale
    assert abs((name_box[0]+name_box[2])/2-footer_centre)<.01
    assert name_box[1]>2 and legend_box[0]-name_box[2]>=8
    assert abs((name_box[1]+name_box[3]-legend_box[1]-legend_box[3])/2)<.01
    footer_layout=dict(placement='Shared x-axis title centred directly beneath panels d-g, with the legend at the far right of the same compact row',
        x_axis_title_bbox_pt=name_box.tolist(),legend_bbox_pt=legend_box.tolist(),
        panel_group_centre_pt=footer_centre,
        tick_to_footer_gap_pt=float(tick_bottom-max(name_box[3],legend_box[3])),
        title_to_legend_horizontal_gap_pt=float(legend_box[0]-name_box[2]),
        vertical_centre_difference_pt=float(abs((name_box[1]+name_box[3]-legend_box[1]-legend_box[3])/2)))
    (QA/'footer_legend_geometry.json').write_text(json.dumps(footer_layout,ensure_ascii=False,indent=2),encoding='utf8')
    require_matplotlib_panel_alignment(fig,axes=axes,json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',
        strict=True,tolerance_pt=1.5,gutter_tolerance_pt=1.5)
    write('Fig5_scatter_plotted_values.csv',points);write('Fig5_country_labels.csv',labels)
    write('Fig5_combined_fit_plotted_values.csv',rendered_fits)
    stem=OUT/'Fig5'
    fig.savefig(stem.with_suffix('.pdf'));fig.savefig(stem.with_suffix('.svg'))
    png_buffer=io.BytesIO();fig.savefig(png_buffer,format='png',dpi=600)
    stem.with_suffix('.png').write_bytes(png_buffer.getvalue())
    with pymupdf.open(stem.with_suffix('.pdf')) as doc:
        page=doc[0];fonts=sorted({f[3] for f in page.get_fonts()})
        page.get_pixmap(matrix=pymupdf.Matrix(2.3,2.3),alpha=False).save(QA/'preview.png')
        for panel_ax in axes:
            p=panel_ax.get_position();clip=pymupdf.Rect(max(0,p.x0*width_pt-43),max(0,height_pt-p.y1*height_pt-38),
                min(width_pt,p.x1*width_pt+12),min(height_pt,height_pt-p.y0*height_pt+43))
            page.get_pixmap(matrix=pymupdf.Matrix(4,4),clip=clip,alpha=False).save(QA/f'preview_{panel_ax.get_gid()}.png')
    manifest=dict(figure='Fig5',edition='v3',archetype='Linked distribution stratification below country mean associations',
        question='How do international mobility levels and changing global shares relate to domestic urban flow concentration?',
        claim='Mean international volumes relate to domestic index levels; stratified country trends show how domestic Gini changes across international-share trajectories',
        dimensions_mm=[180,height_pt/72*25.4],fonts_pdf=fonts,panels=panel_specs,scatter_points=152,
        countries_per_mean_panel=76,years=28,labels=len(labels),country_label_leaders=sum(r['leader'] for r in labels),
        palette={'HHI':BLUE,'Gini':RED,'quartile_groups':group_colors,'Median':YELLOW},
        marker_policy=dict(fill=MARKER_COLOR,opacity=MARKER_ALPHA,edge='none',major_country_outline=False),
        directional_policy='International inflow plus outflow; domestic city inflow plus outflow before computing each annual index',
        mean_definition='Equal-year arithmetic means of annual combined-flow indices and country international event counts',
        fit_definition='HHI: log10 HHI on log10 volume; Gini: logit Gini on log10 volume, shown after inverse logit',
        confidence_bands='5000 paired-country bootstrap percentile pointwise 95% intervals in transformed space, back-transformed',
        displayed_correlations='Spearman rank correlations for a and b only',
        stratification_manifest='stratified_data_manifest.json',
        histogram_definition='All 76 fitted international-share annual percentage rates; 22 equal-width bins',
        lower_distribution_definition='Gaussian kernel density estimates with the same pooled-data bandwidth for all four groups; no normal distribution fit',
        lower_country_strip='19 countries per group; horizontal positions are actual Gini trends and vertical jitter is display-only',
        lower_density_bandwidth=float(bandwidth),lower_strip_points=len(rug_rows),
        lower_layout=dict(square_panels=['d','e','f','g'],plot_width_pt=lower_width,
            plot_height_pt=lower_width,horizontal_gutter_pt=lower_gutter),
        lower_footer=footer_layout,
        axis_labels=dict(mean_panel_x='International mobility (events/year)',
            a_y='Domestic HHI',b_y='Domestic Gini',c_x='Share growth (%/year)',
            c_y='Countries',lower_x='Domestic Gini trend (pp/decade)',lower_y='Density'),
        axis_details_in_caption='a,b use equal-year arithmetic means; their x axes and a y axis are logarithmic. c uses relative annual growth in international shares. Domestic metrics describe within-country city distributions. pp denotes percentage points.',
        source_data_manifest='data_manifest.json',fits=fits)
    manifest['formatting']=specification()
    (QA/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(points=len(points),labels=len(labels),groups=4,countries_per_group=19,bandwidth=bandwidth)))


if __name__=='__main__':main()

