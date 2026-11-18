"""Observed geographic coverage: four upper panels and one city-entry dot panel.

Contract: compare complete international and domestic event volumes with a
constant-baseline mean-flow-per-directed-route reference in the same numerical
unit, then compare country-contact and domestic-city coverage
using unique city dots grouped by country and first-recorded inflow cohort.
Source-partner distributions are standalone
upper panels; country trajectory examples and their leaders are omitted.
Original V1 and V2 exports remain untouched.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'v3'))
from figure_style import font_size, output_root, WIDTH_PT, PROFILE, specification, apply_axes_typography

ROOT = Path(__file__).resolve().parents[2]
CLEAN_DIR = ROOT / "data" / "processed" / "mobility_city_harmonized_20261020"
CANONICAL = CLEAN_DIR / "analysis" / "flow_top100.parquet"
OUT = output_root(Path(__file__).resolve().parent)
QA = OUT / "QA" / "Fig2"
DEPS = ROOT / "tmp" / "nhb_fig2_python_deps"
SKILL = Path.home() / ".codex" / "skills" / "nature-figure" / "scripts"
sys.path[:0] = [str(DEPS), str(SKILL), str(ROOT / "figures")]

import duckdb
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, FancyArrowPatch, Patch
from matplotlib.path import Path as MplPath
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
from scipy.interpolate import PchipInterpolator
import pymupdf

from audit_panel_alignment import require_matplotlib_panel_alignment

from figure_palette import BLUE, RED, GREEN, GRAY, GOLD, YEAR_COLORS, COUNTRY_COLORS, OTHER_COLOR
from fig2_city_entry_clusters import draw_city_clusters
TEAL = GREEN
INK = "#17212A"
GREY = GRAY
YEARS = np.arange(1998, 2026)
DENSITY_YEARS = [1998, 2007, 2016, 2025]
NAMES = {"US": "United States", "DE": "Germany", "GB": "United Kingdom", "JP": "Japan", "CN": "China"}
COUNTRY_NAMES = {
    'AE':'United Arab Emirates','AM':'Armenia','AR':'Argentina','AT':'Austria','AU':'Australia',
    'BD':'Bangladesh','BE':'Belgium','BG':'Bulgaria','BR':'Brazil','BY':'Belarus','CA':'Canada',
    'CH':'Switzerland','CL':'Chile','CM':'Cameroon','CN':'China','CO':'Colombia','CR':'Costa Rica',
    'CU':'Cuba','CZ':'Czechia','DE':'Germany','DK':'Denmark','DZ':'Algeria','EE':'Estonia',
    'EG':'Egypt','ES':'Spain','FI':'Finland','FR':'France','GB':'United Kingdom','GH':'Ghana',
    'GR':'Greece','HR':'Croatia','HU':'Hungary','ID':'Indonesia','IE':'Ireland','IL':'Israel',
    'IN':'India','IR':'Iran','IS':'Iceland','IT':'Italy','JO':'Jordan','JP':'Japan','KE':'Kenya',
    'KR':'South Korea','KW':'Kuwait','LK':'Sri Lanka','LT':'Lithuania','MA':'Morocco','MT':'Malta',
    'MW':'Malawi','MX':'Mexico','MY':'Malaysia','NG':'Nigeria','NL':'Netherlands','NO':'Norway',
    'NZ':'New Zealand','PH':'Philippines','PK':'Pakistan','PL':'Poland','PR':'Puerto Rico',
    'PT':'Portugal','RE':'Réunion','RO':'Romania','RS':'Serbia','RU':'Russia','SA':'Saudi Arabia',
    'SE':'Sweden','SI':'Slovenia','SK':'Slovakia','TH':'Thailand','TN':'Tunisia','TR':'Turkey',
    'TZ':'Tanzania','UA':'Ukraine','UG':'Uganda','US':'United States','VE':'Venezuela',
    'VN':'Vietnam','ZA':'South Africa',
}


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, records):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(4*1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def rebuild_cleaned_inputs(source_out):
    """Recompute every quantity from the cleaned annual, all-researcher flows.

    Canonical city identifiers already incorporate the geographic cleaning.
    Region strings must never be used to split these identifiers again.
    """
    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='3GB'")
    sqlpath = str(CANONICAL).replace("'", "''")
    con.execute(f"CREATE TEMP VIEW flows AS SELECT * FROM read_parquet('{sqlpath}')")
    invalid = con.execute("""SELECT count(*) FROM flows WHERE flow<=0
        OR year NOT BETWEEN 1998 AND 2025 OR origin=destination
        OR origin IS NULL OR destination IS NULL""").fetchone()[0]
    assert invalid == 0, 'Clean intercity input contains invalid or self-loop records'
    con.execute("""CREATE TEMP TABLE routes AS
        SELECT year,origin_country,destination_country,sum(flow) flow
        FROM flows WHERE origin_country<>destination_country GROUP BY ALL""")
    con.execute("""CREATE TEMP TABLE domestic_counts AS
        SELECT year,'inflow' side,destination_country country,
            count(DISTINCT destination) cities,sum(flow) flow
        FROM flows WHERE origin_country=destination_country GROUP BY ALL
        UNION ALL
        SELECT year,'outflow',origin_country,count(DISTINCT origin),sum(flow)
        FROM flows WHERE origin_country=destination_country GROUP BY ALL""")
    # Independently reconcile the newly supplied cleaned margin table.
    supplied = {(r['country'],r['side'],int(r['year'])):
                (int(r['cities']),float(r['flow'])) for r in
                read_csv(CLEAN_DIR/'analysis'/'domestic_country_city_counts.csv')}
    domestic = {(cc,side,y):(n,float(v)) for y,side,cc,n,v in
                con.execute('SELECT * FROM domestic_counts').fetchall()}
    assert domestic == supplied
    source = [dict(zip(['year','international_flow','domestic_flow','country_links',
        'international_city_links','domestic_city_links','countries_inflow',
        'international_cities_inflow','domestic_cities_inflow','countries_outflow',
        'international_cities_outflow','domestic_cities_outflow'], row)) for row in
        con.execute("""SELECT year,
        sum(flow) FILTER(WHERE origin_country<>destination_country),
        sum(flow) FILTER(WHERE origin_country=destination_country),
        count(DISTINCT (origin_country,destination_country)) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT (origin,destination)) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT (origin,destination)) FILTER(WHERE origin_country=destination_country),
        count(DISTINCT destination_country) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT destination) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT destination) FILTER(WHERE origin_country=destination_country),
        count(DISTINCT origin_country) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT origin) FILTER(WHERE origin_country<>destination_country),
        count(DISTINCT origin) FILTER(WHERE origin_country=destination_country)
        FROM flows GROUP BY year ORDER BY year""").fetchall()]
    assert len(source)==28
    assert sum(r['international_flow'] for r in source)==11529374
    assert sum(r['domestic_flow'] for r in source)==18173850
    for name in ['country_links','international_city_links','domestic_city_links']:
        for row in source:
            row[name+'_index']=100*row[name]/source[0][name]
    incoming = {(cc,y):float(v) for y,cc,v in con.execute("""
        SELECT year,destination_country,sum(flow) FROM routes GROUP BY ALL""").fetchall()}
    outgoing = {(cc,y):float(v) for y,cc,v in con.execute("""
        SELECT year,origin_country,sum(flow) FROM routes GROUP BY ALL""").fetchall()}
    # Derive the continuous sample from the complete cleaned input, requiring
    # at least two origin cities and two destination cities in every year.
    all_country_codes={cc for cc,side,year in domestic}
    countries=sorted(cc for cc in all_country_codes if all(
        domestic.get((cc,side,int(y)),(0,0))[0]>=2
        for side in ['inflow','outflow'] for y in YEARS))
    exclusions=[dict(country=cc,years_with_domestic_inflow=sum((cc,'inflow',int(y)) in domestic for y in YEARS),
        years_with_domestic_outflow=sum((cc,'outflow',int(y)) in domestic for y in YEARS))
        for cc in sorted(set(COUNTRY_NAMES)-set(countries))]
    country=[]
    for cc in countries:
        for side,lookup in [('inflow',incoming),('outflow',outgoing)]:
            for year in map(int,YEARS):
                n,volume=domestic[cc,side,year]
                country.append(dict(country=cc,side=side,year=year,
                    international_flow=lookup.get((cc,year),0.),
                    domestic_flow=volume,domestic_cities=n))
    con.close()
    write_csv(source_out/'Fig2_source_data.csv',source)
    write_csv(source_out/'Fig2_country_year_data.csv',country)
    write_csv(source_out/'Fig2_fixed_sample_exclusions.csv',exclusions)
    provenance=dict(source_parquet=str(CANONICAL.relative_to(ROOT)),
        source_sha256=file_hash(CANONICAL),cleaning_manifest=str((CLEAN_DIR/'manifest.json').relative_to(ROOT)),
        city_identifier='Cleaned stable origin/destination IDs; no new concatenation with region or city names',
        source_tier='Annual top100pct; one tier only',years=[1998,2025],
        international_events=sum(r['international_flow'] for r in source),
        domestic_intercity_events=sum(r['domestic_flow'] for r in source),
        counted_events=sum(r['international_flow']+r['domestic_flow'] for r in source),
        event_scope='Confirmed international and domestic intercity events; within-city and unresolved records excluded',
        original_fixed_sample_n=len(COUNTRY_NAMES),fixed_sample_n=len(countries),
        fixed_country_codes=countries,sample_exclusions=exclusions,
        sample_rule='From the complete cleaned data, require at least two domestic origin cities and two destination cities in every year 1998–2025',
        cleaned_domestic_margin_table_matches_exactly=True)
    (QA/'cleaned_data_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf8')
    return source,country,countries,provenance


def configure():
    mpl.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial"],
        "font.size": font_size(8), "axes.labelsize": font_size(8), "xtick.labelsize": font_size(7),
        "ytick.labelsize": font_size(7), "axes.linewidth": .6,
        "axes.spines.right": False, "axes.spines.top": False,
        "axes.unicode_minus": False, "text.color": INK, "axes.labelcolor": INK,
        "xtick.color": INK, "ytick.color": INK, "pdf.use14corefonts": True,
        "pdf.fonttype": 42, "svg.fonttype": "none", "legend.frameon": False,
        "legend.fontsize": font_size(7), "savefig.facecolor": "white",
        "path.simplify": False,
    })


def label(ax, letter, *, offset=-.055, vertical=1.075):
    ax.set_gid(letter)
    ax.text(offset, vertical, letter, transform=ax.transAxes, fontsize=font_size(10),
            fontweight="bold", ha="left", va="bottom")
    ax.tick_params(length=2.4, width=.55, pad=2.5)
    ax.set_axisbelow(True)


def coverage_panel(ax, curves, xlabel, ylabel):
    """Show monotone b interpolants and original d curves, preserving raw values."""
    displayed=[]
    for year in DENSITY_YEARS:
        rows = [r for r in curves if r["year"] == year]
        x=np.asarray([r["source_locations_threshold"] for r in rows],dtype=float)
        y=np.asarray([100*r["fraction_at_least_threshold"] for r in rows],dtype=float)
        if ax.get_gid()=='d':
            # Connect every original integer threshold; no smoothing, fitting,
            # thinning, jitter or change in empirical percentages is applied.
            xx,yy=x,y;method='Original integer thresholds connected by straight segments'
            line,=ax.plot(xx,yy,color=YEAR_COLORS[year],linewidth=1.1,
                    linestyle='-',solid_capstyle='round',
                    solid_joinstyle='round',label=str(year))
        else:
            logx=np.log10(x);interpolant=PchipInterpolator(logx,y,extrapolate=False)
            dense=np.unique(np.r_[np.linspace(logx[0],logx[-1],1601),logx])
            xx,yy=10**dense,interpolant(dense)
            assert np.max(np.abs(interpolant(logx)-y))<1e-12
            assert np.all(np.diff(yy)<=1e-10) and min(yy)>=-1e-10 and max(yy)<=100+1e-10
            method='Monotone PCHIP interpolation in original threshold, passing every empirical knot'
            line,=ax.plot(xx,yy,color=YEAR_COLORS[year],linewidth=1.,
                linestyle='-',solid_capstyle='round',solid_joinstyle='round',label=str(year))
        line.get_path().should_simplify=False
        displayed.extend(dict(panel=ax.get_gid(),year=year,source_locations_threshold=float(a),
            percentage=float(b),method=method) for a,b in zip(xx,yy))
    xmax = max(r["source_locations_threshold"] for r in curves)
    ax.set_xscale("log")
    display_max=xmax*1.04
    assert display_max>=xmax
    ax.set_xlim(1, display_max)
    ax.set_ylim(0, 100)
    # Powers-of-ten ticks are equally spaced on the logarithmic display and
    # remain readable integer labels without decimal values.
    xticks = [1., 10., 100.]
    ax.set_xticks(xticks, [f"{x:,}" for x in xticks])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value,_: f'{int(round(value)):,}'))
    ax.set_xticks([], minor=True)
    ax.set_yticks([0, 50, 100])
    ax.set_xlabel(xlabel, labelpad=4)
    # Keep the original positive-count log scale and decimal tick labels.
    ax.set_title(ylabel, loc="left", fontsize=font_size(7.5), fontweight="normal", pad=9)
    ax.legend(loc='lower left' if ax.get_gid()=='b' else 'upper right',
              bbox_to_anchor=(.025,.025) if ax.get_gid()=='b' else (.98,.98),
              fontsize=font_size(6),ncol=1,handlelength=.95,handletextpad=.35,
              labelspacing=.3,borderaxespad=0,borderpad=.15)
    return displayed


def coverage_legend_geometry(fig, axes):
    renderer=fig.canvas.get_renderer(); scale=fig.dpi/72; records=[]
    for ax in axes:
        frame=ax.get_window_extent(renderer); legend=ax.get_legend().get_window_extent(renderer)
        assert frame.x0<=legend.x0 and frame.x1>=legend.x1
        assert frame.y0<=legend.y0 and frame.y1>=legend.y1
        for line in ax.lines:
            points=line.get_transform().transform(line.get_path().vertices)
            assert not np.any((points[:,0]>legend.x0-1*scale)&(points[:,0]<legend.x1+1*scale)
                &(points[:,1]>legend.y0-1*scale)&(points[:,1]<legend.y1+1*scale)),ax.get_gid()
        xmax=max(max(line.get_xdata()) for line in ax.lines)
        terminal=ax.transData.transform((xmax,0))[0]
        records.append(dict(panel=ax.get_gid(),plot_bbox_pt=(frame.extents/scale).tolist(),
            legend_bbox_pt=(legend.extents/scale).tolist(),
            placement='Inside the axes, lower-left of the curves' if ax.get_gid()=='b' else 'Inside the axes, upper-right of the curves',
            observed_x_max=float(xmax),display_x_max=float(ax.get_xlim()[1]),
            legend_column_count=1,original_curve_vertices_clear_of_legend=True))
    return records


def label_stack_ends(fig,ax,layers,groups,colors):
    """Label each terminal layer with a short elbow and parallel horizontal ends."""
    fig.canvas.draw()
    scale=fig.dpi/72
    axis=ax.get_window_extent().transformed(mpl.transforms.Affine2D().scale(1/scale))
    heights=np.array([float(layer[-1]) for layer in layers])
    centers=np.cumsum(heights)-heights/2
    points=ax.transData.transform(np.column_stack([np.full(len(centers),2025.),centers]))/scale
    ys=points[:,1].copy()
    gap=10. if PROFILE=='manuscript' else 8.5
    ys[0]=max(ys[0],axis.y0+7)
    for i in range(1,len(ys)):ys[i]=max(ys[i],ys[i-1]+gap)
    if ys[-1]>axis.y1-5:
        ys[-1]=axis.y1-5
        for i in range(len(ys)-2,-1,-1):ys[i]=min(ys[i],ys[i+1]-gap)
    assert ys[0]>=axis.y0+6
    records=[]
    for i,(cc,color) in enumerate(zip(groups,colors)):
        code=cc if cc!='Other countries' else 'Others'
        # Reserve a narrow label column before the next panel's y-axis title.
        label_y=ys[i]
        vertices=np.array([[points[i,0],points[i,1]],[axis.x1+2,label_y],[axis.x1+4,label_y]])
        label_x=axis.x1+6
        fig.add_artist(Line2D(vertices[:,0]/(fig.get_figwidth()*72),vertices[:,1]/(fig.get_figheight()*72),
            transform=fig.transFigure,color=color,lw=.65,zorder=8))
        fig.text(label_x/(fig.get_figwidth()*72),label_y/(fig.get_figheight()*72),code,
            ha='left',va='center',fontsize=font_size(5.8),color='black')
        records.append(dict(panel=ax.get_gid(),country=cc,label=code,year=2025,
            flow_thousand_events=float(heights[i]),layer_center_thousand_events=float(centers[i]),
            line_pdf_points=[[float(x),float(fig.get_figheight()*72-y)] for x,y in vertices],
            label_pdf_anchor=[float(label_x),float(fig.get_figheight()*72-label_y)]))
    return records


def source_partner_distributions(aggregate, country_values, countries, source_out):
    """Count distinct observed incoming partners using the current geographic scope.

    Each directed edge is counted once across disciplines. International curves
    describe all countries with positive annual inflow. Domestic curves give
    each country in the same fixed sample equal weight, independent of its city count.
    """
    canonical = CANONICAL
    scope_manifest = CLEAN_DIR/'manifest.json'
    digest = file_hash(canonical)
    quote = lambda value: "'"+str(value).replace("'", "''")+"'"
    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='2GB'")
    year_sql = ",".join(map(str, DENSITY_YEARS))
    con.execute(f"""CREATE TEMP TABLE flows AS
        SELECT year,origin_country,destination_country,flow,origin,destination
        FROM read_parquet({quote(canonical)}) WHERE year IN ({year_sql}) AND flow>0
            AND origin<>destination""")
    con.execute("""CREATE TEMP TABLE edges AS
        SELECT DISTINCT year,origin_country,destination_country,origin,destination FROM flows""")
    # Reconcile counts and volumes against the data already used by the main plots.
    checks = []
    totals = con.execute("""SELECT year,
        sum(flow) FILTER(WHERE origin_country<>destination_country),
        sum(flow) FILTER(WHERE origin_country=destination_country)
        FROM flows GROUP BY year ORDER BY year""").fetchall()
    coverage = con.execute("""SELECT year,
        count(DISTINCT (origin_country,destination_country)) FILTER(WHERE origin_country<>destination_country),
        count(*) FILTER(WHERE origin_country=destination_country),
        count(DISTINCT destination) FILTER(WHERE origin_country=destination_country)
        FROM edges GROUP BY year ORDER BY year""").fetchall()
    for (year, international, domestic), (_, country_links, city_links, inflow_cities) in zip(totals, coverage):
        expected = aggregate[year]
        assert international == float(expected["international_flow"])
        assert domestic == float(expected["domestic_flow"])
        assert country_links == int(expected["country_links"])
        assert city_links == int(expected["domestic_city_links"])
        assert inflow_cities == int(expected["domestic_cities_inflow"])
        checks.append(dict(year=year, international_flow=international, domestic_flow=domestic,
                           international_country_links=country_links, domestic_city_links=city_links,
                           domestic_inflow_cities=inflow_cities, matches_current_figure=True))
    international = [dict(year=y, country=c, source_countries=n) for y,c,n in con.execute("""
        SELECT year,destination_country,count(DISTINCT origin_country)
        FROM edges WHERE origin_country<>destination_country
        GROUP BY ALL ORDER BY ALL""").fetchall()]
    domestic_all = [dict(year=y, country=c, city=node, source_cities=n) for y,c,node,n in con.execute("""
        SELECT year,destination_country,destination,count(*)
        FROM edges WHERE origin_country=destination_country
        GROUP BY ALL ORDER BY ALL""").fetchall()]
    con.close()
    domestic = [r for r in domestic_all if r["country"] in countries]
    for year in DENSITY_YEARS:
        assert sum(r["year"]==year for r in international) == int(aggregate[year]["countries_inflow"])
        for cc in countries:
            assert sum(r["year"]==year and r["country"]==cc for r in domestic) == country_values[cc,"inflow",year]
    country_curves, city_curves, country_summary = [], [], []
    country_grid = np.arange(1, max(r["source_countries"] for r in international)+2)
    city_grid = np.arange(1, max(r["source_cities"] for r in domestic)+2)
    for year in DENSITY_YEARS:
        vals = np.array([r["source_countries"] for r in international if r["year"]==year])
        survival = np.mean(vals[:,None]>=country_grid[None,:], axis=0)
        assert survival[0]==1 and survival[-1]==0 and np.all(np.diff(survival)<=0)
        country_curves.extend(dict(year=year, source_locations_threshold=int(k),
                                   fraction_at_least_threshold=float(p), destination_countries=len(vals))
                              for k,p in zip(country_grid,survival))
        individual = []
        for cc in countries:
            values = np.array([r["source_cities"] for r in domestic if r["year"]==year and r["country"]==cc])
            # Search sorted values instead of allocating a city-by-threshold matrix.
            individual.append((len(values)-np.searchsorted(np.sort(values),city_grid,side="left"))/len(values))
            country_summary.append(dict(year=year,country=cc,destination_cities=len(values),
                                        mean_source_cities=float(np.mean(values)),median_source_cities=float(np.median(values)),
                                        maximum_source_cities=int(max(values))))
        survival = np.mean(individual,axis=0)
        assert survival[0]==1 and survival[-1]==0 and np.all(np.diff(survival)<=1e-12)
        city_curves.extend(dict(year=year, source_locations_threshold=int(k),
                               fraction_at_least_threshold=float(p), countries_equal_weight=len(countries))
                          for k,p in zip(city_grid,survival))
    write_csv(source_out/"Fig2_international_source_partners.csv", international)
    write_csv(source_out/"Fig2_domestic_city_source_partners.csv", domestic)
    write_csv(source_out/"Fig2_domestic_source_partner_country_summary.csv", country_summary)
    write_csv(source_out/"Fig2_international_source_partner_curves.csv", country_curves)
    write_csv(source_out/"Fig2_domestic_source_partner_curves.csv", city_curves)
    write_csv(source_out/"Fig2_partner_data_reconciliation.csv", checks)
    provenance = dict(source_parquet=str(canonical.relative_to(ROOT)), source_sha256=digest,
                      geographic_scope_manifest=str(scope_manifest.relative_to(ROOT)),
                      directed_edges="Positive-flow distinct year, origin city, destination city across all fields; same-city edges excluded after geographic harmonization",
                      international_destination_countries={str(y):sum(r["year"]==y for r in international) for y in DENSITY_YEARS},
                      domestic_city_records_all_countries=len(domestic_all), domestic_city_records_fixed_countries=len(domestic),
                      domestic_country_n=len(countries), domestic_weighting="Within-country city fractions averaged with equal country weights",
                      years=DENSITY_YEARS, reconciliation="All selected-year event totals, geographic node counts and edge counts exactly match existing plotted source tables")
    (QA/"partner_data_provenance.json").write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding="utf-8")
    return country_curves, city_curves, provenance


def circle_intersections(a, ra, b, rb):
    dx, dy = b[0]-a[0], b[1]-a[1]
    distance = math.hypot(dx, dy)
    if distance < 1e-9 or distance > ra+rb or distance < abs(ra-rb):
        return []
    along = (ra*ra-rb*rb+distance*distance)/(2*distance)
    height = math.sqrt(max(0., ra*ra-along*along))
    mx, my = a[0]+along*dx/distance, a[1]+along*dy/distance
    return [(mx-height*dy/distance, my+height*dx/distance),
            (mx+height*dy/distance, my-height*dx/distance)]


def circular_centres(bubble, selected):
    """Pack every country within a circle, with five examples tangent to its lower arc.

    All radii retain their exact quantitative values. Only positions are free.
    Five constrained centres satisfy ||centre|| + radius = container radius,
    at lower-half angles 195, 257, 288, 319 and 350 degrees.
    """
    radii = {cc: max(float(r["circle_radius"]) for r in bubble if r["country"] == cc)
             for cc in {r["country"] for r in bubble}}
    arc_angles = dict(zip(selected, [195., 257., 288., 319., 350.]))
    gap = .85
    initial_radius = math.sqrt(sum(r*r for r in radii.values())/.77)
    remaining = sorted(set(radii)-set(selected), key=lambda cc: (-radii[cc], cc))
    for attempt in range(12):
        radius = initial_radius*1.025**attempt
        centres = {cc: ((radius-radii[cc])*math.cos(math.radians(angle)),
                        (radius-radii[cc])*math.sin(math.radians(angle))) for cc, angle in arc_angles.items()}
        if any(math.dist(centres[ca], centres[cb]) < radii[ca]+radii[cb]+gap
               for i, ca in enumerate(selected) for cb in selected[i+1:]):
            continue
        failed = False
        for cc in remaining:
            r = radii[cc]
            existing = list(centres)
            candidates = [(0., 0.)]
            for i, ca in enumerate(existing):
                candidates.extend(circle_intersections((0., 0.), radius-r-.2,
                                                      centres[ca], radii[ca]+r+gap))
                for cb in existing[i+1:]:
                    candidates.extend(circle_intersections(centres[ca], radii[ca]+r+gap,
                                                          centres[cb], radii[cb]+r+gap))
            points = np.asarray(candidates, dtype=float)
            points = points[np.hypot(points[:, 0], points[:, 1])+r <= radius+1e-5]
            if len(points):
                positions = np.array([centres[other] for other in existing])
                required = np.array([r+radii[other]+gap-.015 for other in existing])
                distances2 = ((points[:, None, :]-positions[None, :, :])**2).sum(axis=2)
                points = points[np.all(distances2 >= required[None, :]**2, axis=1)]
            if not len(points):
                failed = True; break
            scores = np.hypot(points[:, 0], points[:, 1])+.008*points[:, 1]
            centres[cc] = tuple(points[int(np.argmin(scores))])
        if failed:
            continue
        for i, ca in enumerate(centres):
            assert math.hypot(*centres[ca])+radii[ca] <= radius+1e-4
            for cb in list(centres)[i+1:]:
                assert math.dist(centres[ca], centres[cb]) >= radii[ca]+radii[cb]+gap-.02
        for cc in selected:
            assert centres[cc][1] < 0
            assert np.isclose(math.hypot(*centres[cc])+radii[cc], radius)
        return centres, radius, arc_angles
    raise RuntimeError("Could not fit country circles within a circular envelope")


def prepare_comparison_series(aggregate, country, selected, source_out):
    """Use the current geographic scope for event volumes and both partner directions."""
    canonical=CANONICAL
    margins=CLEAN_DIR/'analysis'/'domestic_city_margins.csv'
    quote=lambda value:"'"+str(value).replace("'","''")+"'"
    con=duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='2GB'")
    con.execute(f"""CREATE TEMP TABLE routes AS
        SELECT year,origin_country,destination_country,sum(flow) flow
        FROM read_parquet({quote(canonical)})
        WHERE flow>0 AND year BETWEEN 1998 AND 2025
            AND origin_country<>destination_country GROUP BY ALL""")
    partner_records=[dict(year=y,country=cc,source_countries=n,international_flow=flow)
        for y,cc,n,flow in con.execute("""SELECT year,destination_country,count(*),sum(flow)
            FROM routes GROUP BY ALL ORDER BY ALL""").fetchall()]
    destination_records=[dict(year=y,country=cc,destination_countries=n,international_flow=flow)
        for y,cc,n,flow in con.execute("""SELECT year,origin_country,count(*),sum(flow)
            FROM routes GROUP BY ALL ORDER BY ALL""").fetchall()]
    domestic_records=con.execute(f"""SELECT year,country,sum(flow) FROM read_csv_auto({quote(margins)})
        WHERE side='inflow' GROUP BY ALL ORDER BY ALL""").fetchall()
    domestic_city_records=con.execute(f"""SELECT year,side,country,count(*)
        FROM read_csv_auto({quote(margins)}) GROUP BY ALL ORDER BY ALL""").fetchall()
    combined_country_records=con.execute("""SELECT year,country,count(DISTINCT partner)
        FROM (SELECT year,destination_country country,origin_country partner FROM routes
              UNION ALL SELECT year,origin_country,destination_country FROM routes)
        GROUP BY ALL ORDER BY ALL""").fetchall()
    combined_city_records=con.execute(f"""SELECT year,country,count(DISTINCT city_id)
        FROM read_csv_auto({quote(margins)}) WHERE flow>0
        GROUP BY ALL ORDER BY ALL""").fetchall()
    con.close()
    partners={(r['country'],r['year']):r for r in partner_records}
    destinations={(r['country'],r['year']):r for r in destination_records}
    domestic={(cc,y):flow for y,cc,flow in domestic_records}
    domestic_city_counts={(cc,side,y):n for y,side,cc,n in domestic_city_records}
    combined_countries={(cc,y):n for y,cc,n in combined_country_records}
    combined_cities={(cc,y):n for y,cc,n in combined_city_records}
    combined=[dict(country=cc,year=y,international_total_countries=combined_countries[cc,y],
        domestic_total_cities=combined_cities[cc,y]) for cc in selected for y in map(int,YEARS)]
    write_csv(source_out/'Fig2_combined_location_counts.csv',combined)
    lookup={(r['country'],r['side'],int(r['year'])):r for r in country}
    for year in map(int,YEARS):
        records=[r for r in partner_records if r['year']==year]
        expected=aggregate[year]
        assert len(records)==int(expected['countries_inflow'])
        assert sum(r['source_countries'] for r in records)==int(expected['country_links'])
        assert sum(r['international_flow'] for r in records)==float(expected['international_flow'])
        out_records=[r for r in destination_records if r['year']==year]
        assert len(out_records)==int(expected['countries_outflow'])
        assert sum(r['destination_countries'] for r in out_records)==int(expected['country_links'])
        assert sum(r['international_flow'] for r in out_records)==float(expected['international_flow'])
        assert sum(v for (cc,y),v in domestic.items() if y==year)==float(expected['domestic_flow'])
    arrays={geo:{} for geo in ['international','domestic']}
    stack_rows=[]
    for cc in selected:
        for year in map(int,YEARS):
            assert destinations[cc,year]['international_flow']==float(lookup[cc,'outflow',year]['international_flow'])
            for side in ['inflow','outflow']:
                assert domestic_city_counts[cc,side,year]==int(float(lookup[cc,side,year]['domestic_cities']))
        for geo in arrays:
            vals=[]
            for year in map(int,YEARS):
                value=float(lookup[cc,'inflow',year][geo+'_flow'])
                expected=partners[cc,year]['international_flow'] if geo=='international' else domestic[cc,year]
                assert value==expected
                vals.append(value)
                stack_rows.append(dict(geography=geo,country=cc,year=year,flow_events=value,flow_million_events=value/1e6))
            arrays[geo][cc]=np.asarray(vals)
    write_csv(source_out/'Fig2_five_country_flows.csv',stack_rows)
    complete_stack_rows=list(stack_rows)
    for geo in arrays:
        totals=np.asarray([float(aggregate[int(y)][geo+'_flow']) for y in YEARS])
        residual=totals-np.sum([arrays[geo][cc] for cc in selected],axis=0)
        assert np.all(residual>=0)
        arrays[geo]['Other countries']=residual
        assert np.allclose(np.sum(list(arrays[geo].values()),axis=0),totals,rtol=0,atol=1e-7)
        complete_stack_rows.extend(dict(geography=geo,country='Other countries',year=int(y),
            flow_events=float(value),flow_million_events=float(value)/1e6) for y,value in zip(YEARS,residual))
    write_csv(source_out/'Fig2_all_country_stacks.csv',complete_stack_rows)
    write_csv(source_out/'Fig2_country_source_counts_annual.csv',partner_records)
    write_csv(source_out/'Fig2_country_destination_counts_annual.csv',destination_records)
    provenance=dict(selected_countries=selected,event_count_unit='One observed mobility event counted once',
        international_direction='Inflow to each selected country from all other countries',
        domestic_direction='All intercity mobility events within each selected country; destination margins counted once',
        stack_scope='Auxiliary historical country decomposition; no longer displayed in a or c',
        other_country_rule='Complete annual total minus the sum of the five separately labelled countries',
        all_28_stacked_totals_reconciled=True,
        stored_units='Raw events and million events in auxiliary tables; displayed global totals use thousand events',
        incoming_partner_count='Distinct source countries with positive annual flow',
        outgoing_partner_count='Distinct destination countries with positive annual flow',
        domestic_city_directions='Positive-flow destination cities for inflow; positive-flow origin cities for outflow',
        all_28_global_years_reconciled=True,all_five_country_flow_series_reconciled=True,
        combined_country_count='Union of source and destination countries, deduplicated per country-year',
        combined_domestic_city_count='Union of domestic origin and destination stable city IDs per country-year')
    (QA/'comparison_data_provenance.json').write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
    return arrays,partners,destinations,combined,provenance


def country_count_axis(values):
    """Choose each country's own integer-count scale using all observations."""
    lo,hi=float(min(values)),float(max(values))
    padding=max(1.,.08*max(hi-lo,1.))
    locator=MaxNLocator(nbins=3,integer=True,min_n_ticks=3)
    ticks=locator.tick_values(max(0,lo-padding),hi+padding)
    ticks=ticks[ticks>=0]
    assert ticks[0]<=lo and ticks[-1]>=hi
    return (float(ticks[0]),float(ticks[-1])),ticks


def growth_reference_series(aggregate, source_out):
    """Use observed route counts with a fixed baseline mean flow per route.

    The blue curve is a descriptive reference, not a fitted counterfactual or
    a database-coverage adjustment. Both curves retain every annual observation.
    """
    baseline_year = int(min(YEARS))
    first = aggregate[baseline_year]
    records = []
    arrays = {}
    for geography, route_key in [('international', 'country_links'),
                                  ('domestic', 'domestic_city_links')]:
        baseline_flow = float(first[geography+'_flow'])
        baseline_routes = int(first[route_key])
        assert baseline_routes > 0 and baseline_flow > 0
        values = []
        for year in map(int, YEARS):
            flow = float(aggregate[year][geography+'_flow'])
            routes = int(aggregate[year][route_key])
            assert flow > 0 and routes > 0
            reference = baseline_flow*routes/baseline_routes
            values.append(reference/1000)
            records.append(dict(geography=geography,year=year,
                observed_events=flow,positive_directed_routes=routes,
                mean_events_per_route=flow/routes,baseline_year=baseline_year,
                baseline_events=baseline_flow,baseline_directed_routes=baseline_routes,
                constant_baseline_mean_events_per_route=baseline_flow/baseline_routes,
                reference_events=reference,observed_to_reference_ratio=flow/reference))
        arrays[geography] = np.asarray(values)
    write_csv(source_out/'Fig2_growth_reference.csv',records)
    return arrays,records


def draw_bubble_panel(ax, records, metric, selected):
    centres,radius,angles=circular_centres(records,selected)
    grouped={cc:[r for r in records if r['country']==cc] for cc in centres}
    radii={cc:max(r['circle_radius'] for r in rs) for cc,rs in grouped.items()}
    ax.set_xlim(-radius-3,radius+3);ax.set_ylim(-radius-3,radius+3)
    ax.set_aspect('equal',adjustable='box')
    ax.set_xticks([]);ax.set_yticks([])
    for spine in ax.spines.values():spine.set_visible(False)
    packed=[]
    for cc,rs in grouped.items():
        for r in sorted(rs,key=lambda r:r['circle_radius'],reverse=True):
            assert np.isclose(r['circle_radius']**2,r[metric])
            ax.add_patch(Circle(centres[cc],r['circle_radius'],facecolor=YEAR_COLORS[r['year']],
                edgecolor='none',linewidth=0,zorder=3))
            packed.append(dict(r,circle_x=centres[cc][0],circle_y=centres[cc][1],colour=YEAR_COLORS[r['year']]))
    return dict(ax=ax,centres=centres,radii=radii,radius=radius,angles=angles,packed=packed,
                inner_radii={cc:min(r['circle_radius'] for r in rs) for cc,rs in grouped.items()})


def label_bubble_countries(fig,geometry,selected,panel):
    """Label all sufficiently large circles using ISO 3166-1 alpha-2 codes."""
    ax=geometry['ax'];renderer=fig.canvas.get_renderer()
    scale=np.linalg.norm(ax.transData.transform((1,0))-ax.transData.transform((0,0)))*72/fig.dpi
    records=[]
    for cc in sorted(geometry['centres'],key=lambda code:-geometry['radii'][code]):
        name=COUNTRY_NAMES[cc]
        fonts=list(dict.fromkeys(font_size(v) for v in ([6.8,6.4,6.0,5.6,5.2] if cc in selected else [6.0,5.6,5.2])))
        available=geometry['radii'][cc]*scale-.65
        chosen=None
        for text in [cc]:
            for font in fonts:
                lines=text.split('\n');properties=FontProperties(family='sans-serif',size=font)
                widths=[max(pymupdf.get_text_length(line,fontname='helv',fontsize=font),
                    renderer.get_text_width_height_descent(line,properties,ismath=False)[0]*72/fig.dpi) for line in lines]
                width=max(widths);height=font*(1+1.45*(len(lines)-1))
                if math.hypot(width/2+.2,height/2+.2)<=available:
                    chosen=(text,font,width,height);break
            if chosen:break
        if chosen:
            text,font,width,height=chosen
            ax.text(*geometry['centres'][cc],text,ha='center',va='center',multialignment='center',
                fontsize=font,linespacing=1.45,color=INK,zorder=5)
            records.append(dict(panel=panel,country=cc,country_name=name,label=text.replace('\n',' / '),
                label_type='ISO2',font_size_pt=font,
                label_width_pt=width,label_height_pt=height,available_disk_radius_pt=available,labelled=True))
        else:
            records.append(dict(panel=panel,country=cc,country_name=name,label='',label_type='too_small',
                font_size_pt='',label_width_pt='',label_height_pt='',available_disk_radius_pt=available,labelled=False))
    assert all(next(r for r in records if r['country']==cc)['labelled'] for cc in selected)
    return records


def add_bubble_size_legend(fig,geometry,panel,values,centre_x_pt,title):
    """One vertical ticked ruler, calibrated to actual bubble diameters."""
    ax=geometry['ax']
    scale=np.linalg.norm(ax.transData.transform((1,0))-ax.transData.transform((0,0)))*72/fig.dpi
    width,height=fig.get_size_inches()*72
    top_pdf=height-195.
    zero_pdf=top_pdf+2*math.sqrt(max(values))*scale
    fig.text(centre_x_pt/width,207/height,title,fontsize=font_size(6.2),
        ha='center',va='center',color=INK,zorder=7)
    fig.add_artist(Line2D([centre_x_pt/width]*2,
        [1-zero_pdf/height,1-top_pdf/height],transform=fig.transFigure,
        color=INK,linewidth=.65,zorder=6))
    records=[]
    for value in values:
        radius_pt=math.sqrt(value)*scale
        tick_pdf=zero_pdf-2*radius_pt
        fig.add_artist(Line2D([(centre_x_pt-1.8)/width,(centre_x_pt+1.8)/width],
            [1-tick_pdf/height]*2,transform=fig.transFigure,color=INK,linewidth=.65,zorder=6))
        fig.text((centre_x_pt+5)/width,1-tick_pdf/height,f'{value:,}',fontsize=font_size(6.2),
            ha='left',va='center',color=INK,zorder=7)
        records.append(dict(panel=panel,quantity=value,circle_radius_pt=radius_pt,
            circle_diameter_pt=2*radius_pt,ruler_x_pt=centre_x_pt,
            ruler_zero_pdf_pt=zero_pdf,tick_pdf_pt=tick_pdf,
            scale_pt_per_data_unit=scale))
    return dict(records=records)


def add_visible_leader(fig, geometries, start, end_x, end_y, color):
    """Clip leaders against both bubble panels so no line cuts through a circle."""
    p0=np.asarray(start)
    p1=np.array([p0[0],.70*p0[1]+.30*end_y])
    p2=np.array([end_x,.20*p0[1]+.80*end_y])
    p3=np.array([end_x,end_y])
    t=np.linspace(0,1,601)[:,None]
    points=(1-t)**3*p0+3*(1-t)**2*t*p1+3*(1-t)*t*t*p2+t**3*p3
    visible=np.ones(len(points),dtype=bool)
    for geometry in geometries:
        data_points=geometry['ax'].transData.inverted().transform(fig.transFigure.transform(points))
        for cc,centre in geometry['centres'].items():
            visible &= np.sum((data_points-np.asarray(centre))**2,axis=1)>(geometry['radii'][cc]+1.1)**2
    runs,current=[],[]
    for point,show in zip(points,visible):
        if show:current.append(point)
        elif current:runs.append(current);current=[]
    if current:runs.append(current)
    for run in runs:
        if len(run)>1:
            path=MplPath(run,[MplPath.MOVETO]+[MplPath.LINETO]*(len(run)-1))
            fig.add_artist(FancyArrowPatch(path=path,transform=fig.transFigure,arrowstyle='-',
                color=color,linewidth=.53,alpha=.62,zorder=.3))


def main():
    OUT.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    source_out=OUT/'source_data';source_out.mkdir(exist_ok=True)
    configure()
    source,country,countries,cleaned_provenance=rebuild_cleaned_inputs(source_out)
    aggregate={int(r['year']):r for r in source}
    country_values={(r['country'],r['side'],int(r['year'])):float(r['domestic_cities']) for r in country}
    assert len(source)==28 and len(country_values)==len(countries)*2*28
    selected=['US','DE','GB','JP','CN']
    assert all(cc in countries for cc in selected)
    country_colors=COUNTRY_COLORS.copy()
    other_color=OTHER_COLOR
    assert set(country_colors.values()).isdisjoint(YEAR_COLORS.values())
    stack_groups=selected+['Other countries']
    stack_colors=[country_colors[cc] for cc in selected]+[other_color]
    country_curves,city_curves,partner_provenance=source_partner_distributions(aggregate,country_values,countries,source_out)
    flows,partners,destinations,combined_counts,comparison_provenance=prepare_comparison_series(aggregate,country,selected,source_out)
    combined_lookup={(r['country'],r['year']):r for r in combined_counts}
    growth_references,growth_records=growth_reference_series(aggregate,source_out)

    international_bubbles=[dict(country=cc,year=year,source_countries=partners[cc,year]['source_countries'],
        circle_radius=math.sqrt(partners[cc,year]['source_countries'])) for cc in countries for year in DENSITY_YEARS]
    domestic_bubbles=[dict(country=cc,year=year,domestic_inflow_cities=int(country_values[cc,'inflow',year]),
        circle_radius=math.sqrt(country_values[cc,'inflow',year])) for cc in countries for year in DENSITY_YEARS]

    # Preserve the upper row and total canvas. One lower panel spans the exact
    # union of the two former country-bubble rectangles.
    height_pt=370.
    fig=plt.figure(figsize=(WIDTH_PT/72,height_pt/72))
    def axes_at(letter,x,y,width,height):
        ax=fig.add_axes([x/WIDTH_PT,y/height_pt,width/WIDTH_PT,height/height_pt])
        label(ax,letter,offset=-14/width,vertical=1+8/height)
        return ax
    a,b,c,d=[axes_at(letter,x,250.,88.,95.)
             for letter,x in zip('abcd',[45.,159.,291.,405.])]
    e=axes_at('e',41.,18.,446.,200.)
    # Keep the second-row panel letter below the first-row x-axis titles.
    next(text for text in e.texts if text.get_text() == 'e').set_position((-14/446, .955))
    volume_rows=[]
    growth_geometry=[]
    for ax,geo,ylabel,upper,ticks in [
        (a,'international','International inflow',1100.,[0,250,500,750,1000]),
        (c,'domestic','Domestic intercity flow',1900.,[0,500,1000,1500])]:
        total=np.array([float(aggregate[int(year)][geo+'_flow'])/1e3 for year in YEARS])
        reference=growth_references[geo]
        ax.plot(YEARS,reference,color=BLUE,linewidth=1.05,marker='o',markersize=4.5,
            markeredgecolor='white',markeredgewidth=.35,zorder=2,clip_on=False,label='Reference')
        ax.plot(YEARS,total,color=RED,linewidth=2.0,marker='o',markersize=4.5,
            markeredgecolor='white',markeredgewidth=.35,zorder=3,clip_on=False,label='Observed')
        volume_rows.extend(dict(panel=ax.get_gid(),geography=geo,year=int(year),
            flow_events=float(aggregate[int(year)][geo+'_flow']),flow_thousand_events=float(value))
            for year,value in zip(YEARS,total))
        assert max(total)<upper
        ax.set_xlim(1998,2025);ax.set_ylim(0,upper)
        ax.set_xticks([1998,2012,2025]);ax.set_yticks(ticks)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value,_:f'{value:.0f}'))
        ax.set_ylabel(ylabel+'\n(thousand events)',labelpad=0 if ax is a else -1)
        ax.set_xlabel('Year',labelpad=4)
        ax.legend(handles=[
            Line2D([],[],color=RED,lw=2.0,marker='o',markersize=4.5,
                markeredgecolor='white',markeredgewidth=.35,label='Observed'),
            Line2D([],[],color=BLUE,lw=1.05,marker='o',markersize=4.5,
                markeredgecolor='white',markeredgewidth=.35,label='Reference')],
            loc='upper left',bbox_to_anchor=(.025,.98),frameon=False,
            fontsize=font_size(5.5),handlelength=1.15,handletextpad=.4,
            labelspacing=.3,borderaxespad=0)
        growth_geometry.append(dict(panel=ax.get_gid(),geography=geo,
            xlim=[1998,2025],ylim=[0,upper],observed_color=RED,reference_color=BLUE,
            observed_linewidth_pt=2.,reference_linewidth_pt=1.05,
            observed_marker_diameter_pt=4.5,reference_marker_diameter_pt=4.5,between_curve_fill=False,
            observed_thousand_events=total.tolist(),reference_thousand_events=reference.tolist()))
    coverage_display=coverage_panel(b,country_curves,'Source countries','Countries (%)')
    coverage_display+=coverage_panel(d,city_curves,'Source cities','Cities (%)')
    city_geometry=draw_city_clusters(e,CANONICAL,countries,source_out,QA,YEAR_COLORS)
    write_csv(source_out/'Fig2_annual_volume_plot.csv',volume_rows)
    (QA/'growth_plot_geometry.json').write_text(json.dumps(growth_geometry,indent=2),encoding='utf8')
    apply_axes_typography(fig,grid_json_out=QA/'grid.json')
    fig.canvas.draw()
    for record in coverage_display:
        axis=b if record['panel']=='b' else d
        xy=axis.transData.transform((record['source_locations_threshold'],record['percentage']))/fig.dpi*72
        record.update(pdf_x_pt=float(xy[0]),pdf_y_pt=float(fig.get_size_inches()[1]*72-xy[1]))
    write_csv(source_out/'Fig2_coverage_display_curves.csv',coverage_display)
    (QA/'coverage_plot_geometry.json').write_text(json.dumps([
        dict(panel=ax.get_gid(),xlim=[float(v) for v in ax.get_xlim()],ylim=[float(v) for v in ax.get_ylim()],xticks=[float(v) for v in ax.get_xticks()],
            xscale=ax.get_xscale(),curve_style='Monotone PCHIP through empirical knots' if ax is b else 'Original straight segments',
            linewidth_pt=1. if ax is b else 1.1) for ax in [b,d]],indent=2),encoding='utf-8')
    coverage_checks=coverage_legend_geometry(fig,[b,d])
    (QA/'Fig2_standalone_legend_geometry.json').write_text(json.dumps(coverage_checks,ensure_ascii=False,indent=2),encoding='utf8')
    require_matplotlib_panel_alignment(fig,json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',strict=True,
        tolerance_pt=1.5,gutter_tolerance_pt=1.5,
        row_groups=[['a','b','c','d']],column_groups=[],
        exemptions=[dict(panels=['a','b','c','d'],checks=['horizontal-gutter'],
            reason='The two international plots and two domestic plots are paired: within-pair gutters are 26 pt; the 44-pt central gutter separates mobility types and accommodates the domestic-flow vertical title. All four plot widths and heights remain equal.')])
    stem=OUT/'Fig2'
    fig.savefig(stem.with_suffix('.pdf'),facecolor='white')
    fig.savefig(stem.with_suffix('.svg'),facecolor='white')
    fig.savefig(stem.with_suffix('.png'),facecolor='white',dpi=600)
    with pymupdf.open(stem.with_suffix('.pdf')) as doc:
        page=doc[0];page.get_pixmap(matrix=pymupdf.Matrix(2.2,2.2),alpha=False).save(QA/'preview.png')
        fonts=sorted({font[3] for font in page.get_fonts()})
        dimensions=[page.rect.width*25.4/72,page.rect.height*25.4/72]
    manifest=dict(figure='Fig2',edition='v4',archetype='asymmetric mixed-modality figure',
        claim='Recorded event volumes and route coverage expand; unique domestic destination cities show their first-recorded entry periods by country.',
        dimensions_mm=dimensions,fonts_pdf=fonts,country_sample_n=len(countries),selected_countries=selected,
        layout=dict(rows=2,first_row=['a','b','c','d'],second_row=['e'],
            top_plot_width_pt=88.,top_plot_height_pt=95.,city_panel_width_pt=446.,city_panel_height_pt=200.,
            within_mobility_pair_gutter_pt=26.,between_mobility_pair_gutter_pt=44.,
            removed='Former lower e/f nested country bubbles and their size rulers; replaced by one city-entry dot panel',
            former_insets='Now standalone panels b and d; no inset axes remain'),
        panels={'a':'Global international event totals versus a constant-baseline mean-flow-per-directed-country-pair reference; thousand events',
            'b':'Destination countries receiving flows from at least the indicated number of source countries; four annual snapshots',
            'c':'Global domestic intercity event totals versus a constant-baseline mean-flow-per-directed-city-pair reference; thousand events',
            'd':'Destination cities receiving flows from at least the indicated number of source cities; equal-country mean; four annual snapshots',
            'e':f'One equal-sized dot per unique domestic inflow city in the same {len(countries)} countries; colour is first-recorded entry cohort'},
        event_volume_unit='Thousand events in a and c; complete global totals with no excluded countries',
        palette=dict(volumes=dict(international=RED,domestic=RED,reference=BLUE),years=YEAR_COLORS),
        volume_comparison=dict(baseline_year=int(min(YEARS)),
            formula='Reference at t = observed baseline events / positive baseline directed routes * positive directed routes at t',
            routes='Distinct positive-flow directed country pairs for international events; directed stable city pairs within countries for domestic events',
            observed_line='Bold red, 2 pt, all 28 annual observations with 4.5-pt circular markers',
            reference_line='Blue, 1.05 pt, all 28 annual route counts with 4.5-pt circular markers and constant baseline mean events per route',
            fill='None',
            interpretation='Descriptive comparison using the changing positive-route set; not a causal counterfactual or database-coverage correction'),
        international_city_flow_excluded=True,
        city_entry_panel=city_geometry,
        city_label_rule='All76 countries use black ISO alpha-2 codes below their irregular city islands; no outline or leader.',
        selected_country_outer_borders=False,connectors='None',
        legend_placement=dict(a_c='Observed and Reference inside upper-left; no country breakdown',
            b='Vertical four-year legend within lower-left blank region',
            d='Vertical four-year legend within upper-right blank region outside the curves',
            e='Four endpoint-year labels1998,2007,2016,2025 along top of lower panel; periods defined in caption'),
        distribution_curve_style=dict(b='Shape-preserving PCHIP in log10 threshold; every empirical knot retained exactly, no extrapolation',
            d='Solid straight segments connect all original integer thresholds on the log-count axis; colour distinguishes years; no smoothing or fitted values',
            thresholds_and_percentages_unchanged=True),
        coverage_x_axes='b logarithmic upper limit 223.6; d upper limit extended to 1000 with ticks 1, 10, 100, 1000. All empirical data retained.',
        comparison_data_provenance=comparison_provenance,source_partner_data_provenance=partner_provenance,
        cleaned_data_provenance=cleaned_provenance,
        source_hashes={str(path.relative_to(ROOT)):file_hash(path) for path in [CANONICAL,
            CLEAN_DIR/'manifest.json',CLEAN_DIR/'city_crosswalk.csv',CLEAN_DIR/'cleaning_policy.json']},
        auxiliary_data='Former bubbles, country decompositions and trajectories remain historical numeric tables; city first-record and plotted-position CSVs are authoritative for panel e',
        uncertainty='Descriptive counts and an explicit constant-baseline reference; no shading, fitted trends or confidence intervals')
    manifest['formatting']=specification()
    (QA/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    plt.close(fig)
    print(json.dumps(dict(outputs=[str(stem.with_suffix(ext)) for ext in ['.pdf','.svg','.png']],
        dimensions_mm=dimensions,panels=list(manifest['panels']),unique_cities=city_geometry['point_count']),ensure_ascii=False))


if __name__=='__main__':
    main()
