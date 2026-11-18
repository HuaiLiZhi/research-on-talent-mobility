"""Shared physical typography for manuscript reading and NHB final artwork."""
from __future__ import annotations
import os
from pathlib import Path

PROFILE=os.environ.get('NHB_FIGURE_PROFILE','journal')
assert PROFILE in {'manuscript','journal'}
WIDTH_MM=180.
WIDTH_PT=WIDTH_MM/25.4*72
UNIFORM_FONT_PT=7.
FONT_FAMILY=os.environ.get('NHB_FONT_FAMILY','Arial')

# Physical mark sizes for main manuscript Figs. 2–6.
AXIS_LINEWIDTH_PT = .6
TICK_LINEWIDTH_PT = .55
ANNUAL_LINEWIDTH_PT = 2.0
ANNUAL_MARKER_PT = 4.0
ANNUAL_MARKER_EDGE_PT = .35
COUNTRY_POINT_PT2 = 22.
COUNTRY_POINT_EDGE_PT = .45
COUNTRY_POINT_ALPHA = .92
DISTRIBUTION_POINT_PT2 = 8.
DISTRIBUTION_LINEWIDTH_PT = 1.2
FIT_LINEWIDTH_PT = 1.3
FIT_COLOUR = '#59616A'
REFERENCE_LINEWIDTH_PT = .6
REFERENCE_LINESTYLE = (0, (2, 2))
REFERENCE_COLOUR = '#899095'

MINOR_GRID=dict(color='#E1E4E8',linewidth_pt=.35,alpha=.85,linestyle='solid',per_major_interval=1)
LIGHT_GRID=dict(color='#E1E4E8',linewidth_pt=.35,alpha=.85,linestyle='solid',
    major_ticks_only=False,minor_grid=MINOR_GRID,text_clearance_pt=2.4,zorder=.25,
    complete_plot_boundaries=False,extend_intermediate_spacing_to_edges=True,
    extend_major_spacing_to_edges=True)


def output_root(base):
    output=base if PROFILE=='manuscript' else base/'NHB_final'
    output.mkdir(parents=True,exist_ok=True)
    return output


def font_size(previous):
    """Use one physical text size throughout the final figure."""
    if PROFILE=='journal':return UNIFORM_FONT_PT
    if previous>=9:return 10. if PROFILE=='manuscript' else 8.
    if previous>=7.5:return 9. if PROFILE=='manuscript' else 7.
    if previous>=6.3:return 8.5 if PROFILE=='manuscript' else 7.
    if previous>=5.5:return 8. if PROFILE=='manuscript' else 6.5
    return 7.5 if PROFILE=='manuscript' else 6.


def specification():
    return dict(profile=PROFILE,width_mm=WIDTH_MM,body_reference_pt=[11,12],
        ordinary_text_pt=[7,9] if PROFILE=='manuscript' else [7,7],
        panel_letter_pt=10 if PROFILE=='manuscript' else 7,
        axis_label_pt=9 if PROFILE=='manuscript' else 7,
        tick_and_legend_pt=8 if PROFILE=='manuscript' else 7,
        inset_axis_text_pt=7.5 if PROFILE=='manuscript' else 7,
        font=FONT_FAMILY,insertion_width_mm=180,major_grid=LIGHT_GRID,
        instruction='Insert at 180 mm without further reduction; manuscript and journal files have independent native typography.')


def apply_light_grids(fig,json_out=None):
    """Continue major and midpoint guides toward plot limits, clear of text.

    Secondary y axes share the primary grid. Category labels do not imply a
    continuous numerical dimension. All grid segments are decorative only.
    """
    import json
    import re
    import numpy as np
    from matplotlib.collections import LineCollection
    from matplotlib.text import Text
    for artist in getattr(fig,'_light_grid_artists',[]):artist.remove()
    fig._light_grid_artists=[]
    fig.canvas.draw();renderer=fig.canvas.get_renderer()
    pad=LIGHT_GRID['text_clearance_pt']*fig.dpi/72
    text_boxes=[t.get_window_extent(renderer).padded(pad) for t in fig.findobj(Text)
        if t.get_visible() and t.get_text().strip() and t.get_alpha()!=0]
    visited=[];audit=[]
    axes=[]
    def visit(ax):
        if ax in axes:return
        axes.append(ax)
        for child in ax.child_axes:visit(child)
    for ax in fig.axes:visit(ax)
    # Clear the full legend footprint, including its handles and opaque frame.
    # PDF font metrics can differ slightly from individual Agg text extents.
    legends=list(fig.legends)+[ax.get_legend() for ax in axes if ax.get_legend() is not None]
    text_boxes.extend(legend.get_window_extent(renderer).padded(pad) for legend in legends if legend.get_visible())
    for index,ax in enumerate(axes):
        name=ax.get_gid() or f'axes_{index}'
        ax.grid(False,which='both',axis='both')
        rect=ax.get_window_extent(renderer)
        duplicate=any(np.allclose(rect.extents,r,rtol=0,atol=.001) for r in visited)
        if not ax.get_visible() or not ax.axison or duplicate:
            audit.append(dict(axes=name,grid=False,reason='Secondary physical axis' if duplicate else 'No visible data axes'))
            continue
        visited.append(rect.extents.copy())
        def numeric_axis(axis):
            labels=[t.get_text().strip() for t in axis.get_ticklabels() if t.get_visible() and t.get_text().strip()]
            if not labels:return True
            return all(bool(re.search(r'\d',label)) for label in labels)
        enabled={'x':len(ax.get_xticks())>0 and numeric_axis(ax.xaxis),
                 'y':len(ax.get_yticks())>0 and numeric_axis(ax.yaxis)}
        if not any(enabled.values()):
            audit.append(dict(axes=name,grid=False,reason='No numerical tick axes, including packed bubble layouts'))
            continue
        guides=[];segment_counts={'major':0,'intermediate':0,'boundary':0}
        for dimension,ticks in [('x',ax.get_xticks()),('y',ax.get_yticks())]:
            transform=ax.get_xaxis_transform() if dimension=='x' else ax.get_yaxis_transform()
            low,high=(rect.x0,rect.x1) if dimension=='x' else (rect.y0,rect.y1)
            def tick_at(pos):
                pixel=(pos,(rect.y0+rect.y1)/2) if dimension=='x' else ((rect.x0+rect.x1)/2,pos)
                return float(transform.inverted().transform(pixel)[0 if dimension=='x' else 1])
            anchors=[]
            if enabled[dimension]:
                scale=ax.get_xscale() if dimension=='x' else ax.get_yscale()
                for tick in ticks:
                    if scale=='log' and tick<=0:continue
                    point=transform.transform((tick,.5) if dimension=='x' else (.5,tick))
                    pos=float(point[0] if dimension=='x' else point[1])
                    if np.isfinite(pos) and low-2*(high-low)<=pos<=high+2*(high-low):anchors.append((pos,float(tick)))
                anchors.sort()
                anchors=[r for i,r in enumerate(anchors) if not i or r[0]-anchors[i-1][0]>.01]
            if len(anchors)>=2:
                left_step=anchors[1][0]-anchors[0][0];right_step=anchors[-1][0]-anchors[-2][0]
                while anchors[0][0]>low:
                    pos=anchors[0][0]-left_step;anchors.insert(0,(pos,tick_at(pos)))
                while anchors[-1][0]<high:
                    pos=anchors[-1][0]+right_step;anchors.append((pos,tick_at(pos)))
            # Extended anchor positions inside the view need their own major
            # guides as well as the midpoint guides between them.
            major=[r for r in anchors if low+.5<r[0]<high-.5]
            intermediate=[]
            for (p0,t0),(p1,t1) in zip(anchors[:-1],anchors[1:]):
                midpoint=(p0+p1)/2
                if p1-p0>=1 and low+.5<midpoint<high-.5:
                    intermediate.append((midpoint,tick_at(midpoint)))
            for kind,positions,style in [('major',major,LIGHT_GRID),('intermediate',intermediate,MINOR_GRID)]:
                segments=[]
                for pos,tick in positions:
                    if not low+.5<pos<high-.5:continue
                    start,stop=(rect.y0,rect.y1) if dimension=='x' else (rect.x0,rect.x1)
                    intervals=[(float(start),float(stop))]
                    for box in text_boxes:
                        crosses=(box.x0<=pos<=box.x1) if dimension=='x' else (box.y0<=pos<=box.y1)
                        if not crosses:continue
                        left,right=(box.y0,box.y1) if dimension=='x' else (box.x0,box.x1)
                        updated=[]
                        for lo,hi in intervals:
                            if right<=lo or left>=hi:updated.append((lo,hi));continue
                            if lo<left:updated.append((lo,min(left,hi)))
                            if right<hi:updated.append((max(lo,right),hi))
                        intervals=updated
                    saved=[]
                    for lo,hi in intervals:
                        if hi-lo<.25:continue
                        pixels=[(pos,lo),(pos,hi)] if dimension=='x' else [(lo,pos),(hi,pos)]
                        segments.append(ax.transAxes.inverted().transform(pixels))
                        saved.append([[float(x*72/fig.dpi),float(fig.get_figheight()*72-y*72/fig.dpi)] for x,y in pixels])
                    guide=dict(dimension=dimension,level=kind,tick=tick,position_px=pos,retained_segments=len(saved))
                    guide['pdf_segments_pt']=saved
                    guides.append(guide)
                if segments:
                    grid=LineCollection(segments,transform=ax.transAxes,colors=style['color'],
                        linewidths=style['linewidth_pt'],alpha=style['alpha'],linestyles=style['linestyle'],
                        zorder=LIGHT_GRID['zorder'] if kind!='intermediate' else LIGHT_GRID['zorder']-.01,clip_on=True)
                    grid.set_gid(name+'_'+dimension+'_'+kind+'_light_grid');grid.set_in_layout(False);ax.add_collection(grid,autolim=False)
                    fig._light_grid_artists.append(grid);segment_counts[kind]+=len(segments)
        ax.set_axisbelow(True)
        audit.append(dict(axes=name,grid=any(segment_counts.values()),numerical_axes=enabled,
            segments=sum(segment_counts.values()),segment_counts=segment_counts,
            major_guides=[g for g in guides if g['level']=='major'],
            intermediate_guides=[g for g in guides if g['level']=='intermediate'],
            boundary_guides=[g for g in guides if g['level']=='boundary']))
    report=dict(policy=LIGHT_GRID,axes=audit,source_values_changed=False,
        duplicate_y_axes='One grid per physical plot rectangle',
        text_policy='Exact grid paths interrupted around visible text with 2.4 pt clearance to allow for vector font metrics',
        intermediate_rule='One line at the display-space midpoint between neighbouring major ticks, continuing the same spacing toward both edges; no additional ticks or labels',
          boundary_rule='No added perimeter. Both extrapolated major and midpoint guides continue with the neighbouring intervals up to the plot limits; original black axis spines are unchanged.')
    fig._light_grid_audit=report
    if json_out is not None:
        Path(json_out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def configure_nhb_typography():
    """One final-size font family and editable mathematical typography."""
    import matplotlib as mpl
    import matplotlib._mathtext as mathtext_engine
    from matplotlib import font_manager
    font_directory=os.environ.get('NHB_FONT_DIRECTORY')
    if font_directory:
        for pattern in ['*.ttf','*.otf']:
            for path in Path(font_directory).glob(pattern):font_manager.fontManager.addfont(path)
    # Fail explicitly if a requested family is unavailable, rather than silently
    # substituting a different typeface in the delivered artwork.
    font_manager.findfont(font_manager.FontProperties(family=FONT_FAMILY),fallback_to_default=False)
    mpl.rcParams.update({
        'font.family':'sans-serif','font.sans-serif':[FONT_FAMILY],
        'font.size':7.,'axes.labelsize':7.,'xtick.labelsize':7.,'ytick.labelsize':7.,
        'legend.fontsize':7.,'pdf.use14corefonts':False,'pdf.fonttype':42,
        'ps.fonttype':42,'svg.fonttype':'none',
        'mathtext.fontset':'custom','mathtext.rm':FONT_FAMILY,'mathtext.it':FONT_FAMILY+':italic',
        'mathtext.bf':FONT_FAMILY+':bold','mathtext.sf':FONT_FAMILY,'mathtext.tt':FONT_FAMILY,
        'mathtext.fallback':'stix',
    })
    # The requested uniform size also applies to mathematical scripts.
    mathtext_engine.SHRINK_FACTOR=1.


def schematic_font_size(previous):
    """One native-size value for schematic headings and labels."""
    return UNIFORM_FONT_PT


def title_case_display(label):
    """Capitalize display words while preserving math, units and identifiers."""
    import re
    protected = re.compile(
        r'(\$[^$]*\$|\\\([^)]*\\\)|(?:pp|%)/(?:year|yr|decade)|\b(?:pp|km|mm|cm|pt|dpi)\b)')

    def words(part):
        def initial(match):
            word = match.group(0)
            # Lowercase panel labels and scalar symbols retain their notation.
            if len(word) == 1:
                return word
            return word[0].upper() + word[1:]
        return re.sub(r'(?<![A-Za-z0-9_])[A-Za-z]+(?:[\u2019\'][A-Za-z]+)?', initial, part)

    return ''.join(part if i % 2 else words(part)
                   for i, part in enumerate(protected.split(str(label))))


def apply_nhb_typography(fig):
    """Normalize typography without changing data geometry or panel placement."""
    import re
    from matplotlib.text import Text
    configure_nhb_typography()
    axes=[]
    def visit(ax,inset=False):
        if any(item[0] is ax for item in axes):return
        axes.append((ax,inset))
        for child in ax.child_axes:visit(child,True)
    for ax in fig.axes:visit(ax)
    for item in fig.findobj(Text):
        label=item.get_text().strip()
        if not label:continue
        item.set_text(title_case_display(item.get_text()))
        item.set_fontfamily(FONT_FAMILY)
        item.set_math_fontfamily('custom')
        item.set_fontsize(UNIFORM_FONT_PT)
    for ax,inset in axes:
        ax.xaxis.label.set_fontsize(UNIFORM_FONT_PT)
        ax.yaxis.label.set_fontsize(UNIFORM_FONT_PT)
        for item in ax.get_xticklabels()+ax.get_yticklabels():
            item.set_fontsize(UNIFORM_FONT_PT)
        if ax.title.get_text():ax.title.set_fontsize(UNIFORM_FONT_PT)
        legend=ax.get_legend()
        if legend:
            for item in legend.get_texts():item.set_fontsize(UNIFORM_FONT_PT)
            if legend.get_title().get_text():legend.get_title().set_fontsize(UNIFORM_FONT_PT)
    for legend in fig.legends:
        for item in legend.get_texts():item.set_fontsize(UNIFORM_FONT_PT)
        if legend.get_title().get_text():legend.get_title().set_fontsize(UNIFORM_FONT_PT)


def apply_axes_typography(fig,grid_json_out=None):
    """Use exactly the same axis/legend hierarchy in every figure."""
    label_pt=9. if PROFILE=='manuscript' else 7.
    tick_pt=8. if PROFILE=='manuscript' else 6.5
    inset_pt=7.5 if PROFILE=='manuscript' else 6.
    axes=[]
    def visit(ax):
        if ax in axes:return
        axes.append(ax)
        for child in ax.child_axes:visit(child)
    for ax in fig.axes:visit(ax)
    for ax in axes:
        name=ax.get_gid() or ''
        small=any(token in name for token in ['_zoom','_hhi','_evenness','_top_shares','_source_partners']) or name=='a_volume'
        ax.xaxis.label.set_fontsize(inset_pt if small else label_pt)
        ax.yaxis.label.set_fontsize(inset_pt if small else label_pt)
        for text in ax.get_xticklabels()+ax.get_yticklabels():text.set_fontsize(inset_pt if small else tick_pt)
        legend=ax.get_legend()
        if legend:
            for text in legend.get_texts():text.set_fontsize(tick_pt)
    for legend in fig.legends:
        for text in legend.get_texts():text.set_fontsize(tick_pt)
    from matplotlib.text import Text
    for text in fig.findobj(Text):text.set_color('black')
    if PROFILE=='journal':apply_nhb_typography(fig)
    apply_light_grids(fig,json_out=grid_json_out)
