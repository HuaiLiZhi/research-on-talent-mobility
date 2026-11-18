"""Editable BRIDGE schematic, with isometric city glyphs and explicit inputs.

The schematic inherits only general visual conventions from a supplied style
reference. All vector artwork is drawn anew. Icons, example networks, feature
cells and flow-share glyphs are conceptual illustrations. The two map cards
use attributed geographic source data, without displayed place names.
"""

from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "tmp" / "nhb_fig2_python_deps"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'scripts/plots/paper_figures/qa'))
sys.path.insert(0, str(PROJECT / "scripts/plots/paper_figures/qa"))
sys.path.insert(0, str(PROJECT / "figures/v3"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.path import Path as MplPath
from matplotlib.transforms import Affine2D
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, FancyBboxPatch, PathPatch, Polygon, Rectangle
from shapely import make_valid
from shapely.geometry import shape
from shapely.ops import unary_union

from audit_panel_alignment import require_matplotlib_panel_alignment
from figure_style import configure_nhb_typography,schematic_font_size,specification,FONT_FAMILY

OUT = PROJECT / "figures/fig1_framework_detailed"
QA = PROJECT / "outputs/fig1_framework_detailed"
OUT.mkdir(parents=True, exist_ok=True)
QA.mkdir(parents=True, exist_ok=True)

DESIGN_WIDTH, DESIGN_HEIGHT = 231.0, 82.0
WIDTH = 180.0
NATIVE_SCALE = WIDTH / DESIGN_WIDTH
BOTTOM_CAPTION_SPACE = 0.
HEIGHT = (DESIGN_HEIGHT+BOTTOM_CAPTION_SPACE) * NATIVE_SCALE
INK = "#363B40"
ARROW_COLOR = "#000000"
RESTORE_ARROW_COLORS = False
GREY = "#A5AEB7"
LIGHT = "#D5DCE2"
BLUE = "#7E99F4"
GREEN = "#7AB656"
RED = "#CC7C71"
YELLOW = "#E5BC5E"
DISCIPLINE_COLOR = "#A88A44"
DATA_FIELDS = {
    "Identifiers": ["work identifier", "author identifier", "institution identifier"],
    "Time": ["publication year", "event year"],
    "Geography": ["country", "region", "city", "coordinates", "stable city identifier"],
    "Affiliations": ["affiliation institution", "distinct affiliated works"],
    "Discipline": ["work field", "author primary field"],
    "Flows": ["origin", "destination", "flow count", "event classification"],
}

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 8.8, "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "savefig.facecolor": "white", "axes.linewidth": 0.7,
})
configure_nhb_typography()
fig = plt.figure(figsize=(WIDTH / 25.4, HEIGHT / 25.4), facecolor="white")
ax = fig.add_axes((0, 0, 1, 1))
ax.set(xlim=(0, DESIGN_WIDTH), ylim=(-BOTTOM_CAPTION_SPACE, DESIGN_HEIGHT))
ax.set_axis_off()
FRAMES = {}
FRAME_PATCHES = {}
ROUTES = []
MAP_DATA = PROJECT / "data/raw/fig1_shanghai_real_maps_20261103"
regions = json.loads((MAP_DATA / "shanghai_pudong.geojson").read_text(encoding="utf-8"))
SHANGHAI = shape(regions["features"][0]["geometry"])
PUDONG = shape(regions["features"][1]["geometry"])
DISTRICTS = [shape(f["geometry"]) for f in json.loads(
    (MAP_DATA / "shanghai_districts.geojson").read_text(encoding="utf-8"))["features"]]
SQUARE_MAP_DATA = PROJECT / "data/raw/fig1_square_maps_20261103"
PROVINCES = [make_valid(shape(f["geometry"])) for f in json.loads(
    (SQUARE_MAP_DATA / "china_provinces.geojson").read_text(encoding="utf-8"))["features"]]
CHINA = unary_union(PROVINCES)
CANDIDATE_CITIES = json.loads((SQUARE_MAP_DATA / "candidate_cities.geojson").read_text(
    encoding="utf-8"))["features"]
CONTEXT_MAP_DATA = PROJECT / "data/raw/fig1_map_context_20261103"
CONTEXT_MANIFEST = json.loads((CONTEXT_MAP_DATA / "manifest.json").read_text(encoding="utf-8"))
MAP_CONTEXT = {key: [shape(f["geometry"]) for f in json.loads(
    (CONTEXT_MAP_DATA / f"{key}_context.geojson").read_text(encoding="utf-8"))["features"]]
    for key in ["national", "city"]}
MAP_AUDIT = {"sources": [str(MAP_DATA / "manifest.json"),
                          str(SQUARE_MAP_DATA / "manifest.json"),
                          str(CONTEXT_MAP_DATA / "manifest.json")],
             "synthetic_geographic_geometry": False, "street_map_displayed": False,
             "place_names_displayed": False, "panels": {}}


def text(x, y, label, size=8.8, color=INK, weight="normal", ha="center", va="center"):
    return ax.text(x, y, label, fontsize=schematic_font_size(size), color=color, fontweight=weight,
                   ha=ha, va=va, linespacing=1.13, zorder=8)


def rect(x, y, w, h, fill="white", edge=INK, lw=0.6, radius=0, dashed=False, z=1):
    options = dict(facecolor=fill, edgecolor=edge, linewidth=lw, zorder=z)
    if dashed:
        options["linestyle"] = (0, (1.2, 1.6))
    if radius:
        p = FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={radius}", **options)
    else:
        p = Rectangle((x, y), w, h, **options)
    ax.add_patch(p)
    return p


def frame(key, x, y, w, h, edge=INK, dashed=False):
    FRAMES[key] = dict(x=x, y=y, width=w, height=h)
    patch=rect(x, y, w, h, "white", edge, 0.6, 1.8, dashed)
    FRAME_PATCHES[key]=patch
    return patch


def path(points, color=INK, lw=0.75, arrow=True, dashed=False, z=4, radius=0):
    """One continuous path, with optional rounded right-angle elbows."""
    # Data-preparation arrows stay black; BRIDGE recovers its input colours.
    if arrow and (not RESTORE_ARROW_COLORS or color == INK):
        color = ARROW_COLOR
    q=np.asarray(points,dtype=float)
    assert len(q)>=2 and np.all(np.linalg.norm(np.diff(q,axis=0),axis=1)>0)
    vertices=[q[0]];codes=[MplPath.MOVETO]
    for j in range(1,len(q)-1):
        before=q[j]-q[j-1];after=q[j+1]-q[j]
        r=min(radius,np.linalg.norm(before)/2,np.linalg.norm(after)/2)
        if r and abs(np.dot(before,after))<1e-8:
            start=q[j]-before/np.linalg.norm(before)*r
            end=q[j]+after/np.linalg.norm(after)*r
            vertices.extend([start,q[j],end])
            codes.extend([MplPath.LINETO,MplPath.CURVE3,MplPath.CURVE3])
        else:
            vertices.append(q[j]);codes.append(MplPath.LINETO)
    vertices.append(q[-1]);codes.append(MplPath.LINETO)
    route=MplPath(vertices,codes)
    style=dict(linewidth=lw,zorder=z,linestyle=(0,(2,2)) if dashed else "solid",
               capstyle="round",joinstyle="round")
    if arrow:
        patch=FancyArrowPatch(path=route,arrowstyle="-|>",mutation_scale=6.5,
                              color=color,**style)
    else:
        patch=PathPatch(route,facecolor="none",edgecolor=color,**style)
    ax.add_patch(patch)
    global_points=q+np.array([48. if RESTORE_ARROW_COLORS else 0.,0.])
    ROUTES.append({'points_mm':(global_points*NATIVE_SCALE).tolist(),'arrow':arrow,'color':color,
                   'corner_radius_mm':radius*NATIVE_SCALE,'single_continuous_path':True})
    return patch


def link(a, b, color, bend=0.0, width=0.65, trim=1.4):
    if not RESTORE_ARROW_COLORS:
        color = ARROW_COLOR
    dx, dy = b[0] - a[0], b[1] - a[1]
    dist = math.hypot(dx, dy)
    aa = (a[0] + dx / dist * trim, a[1] + dy / dist * trim)
    bb = (b[0] - dx / dist * trim, b[1] - dy / dist * trim)
    ax.add_patch(FancyArrowPatch(aa, bb, arrowstyle="-|>", mutation_scale=5.8,
                                linewidth=width, color=color, shrinkA=0, shrinkB=0,
                                connectionstyle=f"arc3,rad={bend}", zorder=4))


def dot(x, y, r=0.85, fill="white", edge=INK, z=6):
    ax.add_patch(Circle((x, y), r, facecolor=fill, edgecolor=edge, linewidth=0.55, zorder=z))


def tile(cx, cy, w, h, fill, edge):
    top = [(cx - w / 2, cy), (cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2)]
    rim = [(cx - w / 2, cy), (cx, cy - h / 2 - 0.65), (cx + w / 2, cy),
           (cx + w / 2, cy - 0.65), (cx, cy - h / 2 - 1.25), (cx - w / 2, cy - 0.65)]
    ax.add_patch(Polygon(rim, facecolor="#EDF0F3", edgecolor=edge, linewidth=0.45, zorder=2))
    ax.add_patch(Polygon(top, facecolor=fill, edgecolor=edge, linewidth=0.55, zorder=3))


def building(cx, cy, w=1.7, h=2.6, roof="#F8FAFC", edge=INK):
    # The footprint lies on the plane; top and two faces give a restrained
    # isometric cue without perspective-dependent text or simulated measurements.
    d = w * 0.38
    left = [(cx - w / 2, cy), (cx, cy - d), (cx, cy + h - d), (cx - w / 2, cy + h)]
    right = [(cx, cy - d), (cx + w / 2, cy), (cx + w / 2, cy + h), (cx, cy + h - d)]
    top = [(cx - w / 2, cy + h), (cx, cy + h - d),
           (cx + w / 2, cy + h), (cx, cy + h + d)]
    for vertices, fill in [(left, "white"), (right, "#E9EDF1"), (top, roof)]:
        ax.add_patch(Polygon(vertices, facecolor=fill, edgecolor=edge, linewidth=0.5, zorder=6))


def paper(x, y, w=5.5, h=7.4, fill="white", z=3):
    vertices = [(x, y), (x + w, y), (x + w, y + h - 1.6),
                (x + w - 1.6, y + h), (x, y + h)]
    ax.add_patch(Polygon(vertices, facecolor=fill, edgecolor=INK, linewidth=0.55, zorder=z))
    path([(x + w - 1.6, y + h), (x + w - 1.6, y + h - 1.6),
          (x + w, y + h - 1.6)], arrow=False, lw=0.45, z=z + .1)
    for yy, length in [(y + 2.0, w - 1.8), (y + 3.5, w - 1.5), (y + 5.0, w - 2.3)]:
        path([(x + 0.8, yy), (x + 0.8 + length, yy)], color=GREY, lw=0.5, arrow=False, z=z + .1)


def attribute_icon(kind, x, y, colour):
    """Attribute families illustrated by original vector glyphs, without values."""
    if kind == "Identifiers":
        centers = [(x-1.8,y+1.4),(x+1.8,y+1.4),(x,y-1.5)]
        for a,b in [(0,1),(0,2),(1,2)]:
            path([centers[a],centers[b]],colour,.6,arrow=False,z=5)
        for xx,yy in centers:
            dot(xx,yy,.8,"white",colour)
    elif kind == "Time":
        rect(x-2.7,y-2.3,5.4,4.8,"#FFFAEE",colour,.55,.5,z=5)
        path([(x-2.7,y+.8),(x+2.7,y+.8)],colour,.5,arrow=False,z=6)
        for dx in [-1.5,1.5]:
            path([(x+dx,y+1.8),(x+dx,y+3.)],colour,.65,arrow=False,z=6)
        for dx in [-1.5,0,1.5]:
            for dy in [-1.3,-.1]:
                rect(x+dx-.3,y+dy-.3,.6,.6,"#EAD39A",colour,.15,z=6)
    elif kind == "Geography":
        vertices = np.array([[0,-3.],[-.9,-1.3],[-2.2,.2],[-1.9,1.5],
                             [-1.4,3.1],[1.4,3.1],[1.9,1.5],
                             [2.2,.2],[.9,-1.3],[0,-3.]])+np.array([x,y])
        codes = [MplPath.MOVETO]+[MplPath.CURVE4]*9
        ax.add_patch(PathPatch(MplPath(vertices,codes),facecolor="#EDF5E7",
                               edgecolor=colour,lw=.6,zorder=5))
        dot(x,y+.9,.65,"white",colour)
    elif kind == "Affiliations":
        building(x-2.3,y-1.9,w=1.45,h=2.5,roof="#EEF2FE",edge=colour)
        building(x,y-2.1,w=2.,h=4.,roof="#EEF2FE",edge=colour)
        building(x+2.3,y-1.9,w=1.45,h=2.5,roof="#EEF2FE",edge=colour)
    elif kind == "Discipline":
        disciplinary_icon("Physical",x,y,colour)
    elif kind == "Flows":
        points=[(x-2.5,y-1.4),(x,y+1.8),(x+2.5,y-1.4)]
        for a,b in [(0,1),(1,2),(0,2)]:
            link(points[a],points[b],colour,trim=.7,width=.55)
        for xx,yy in points:
            dot(xx,yy,.65,"white",colour)
    else:
        raise ValueError(kind)


def linked_attribute_table(x,y,w=38.,h=11.):
    """Schematic linked records; column groups represent types, not counts."""
    groups=[(6.7,GREY,"#EEF1F4"),(4.3,DISCIPLINE_COLOR,"#FBF3DD"),
            (8.1,GREEN,"#EDF5E7"),(6.6,BLUE,"#EEF2FE"),
            (5.3,RED,"#F8EDEA"),(7.,INK,"#F1F3F5")]
    assert abs(sum(g[0] for g in groups)-w)<1e-8
    for dx,dy in [(1.2,1.2),(.6,.6),(0.,0.)]:
        rect(x+dx,y+dy,w,h,"white",GREY,.35,.25,z=3)
    start=x
    for width,colour,tint in groups:
        rect(start,y,width,h,tint,GREY,.25,z=4)
        rect(start,y+h-1.7,width,1.7,colour,GREY,.25,z=5)
        for fraction in [.33,.66]:
            path([(start+width*fraction,y),(start+width*fraction,y+h-1.7)],
                 GREY,.18,arrow=False,z=5)
        for row,yy in enumerate(np.linspace(y+1.,y+h-3.,4)):
            path([(start+.55,yy),(start+width-.55,yy)],"#BAC4CC",.28,
                 arrow=False,z=5)
        start+=width
    return (x+w+1.2,y+h/2)


def vector(x, y, n, colour, cell=1.65, height=2.7):
    for j in range(n):
        rect(x + j * cell, y, cell, height,
             fill=colour if j % 3 else "#EEF1F4", edge=GREY, lw=0.4, z=5)


def matrix(x, y, w=6.7, h=7.2, colour=BLUE):
    # Icon of an OD matrix: cell shades are schematic, with no numeric scale.
    for row in range(3):
        for col in range(3):
            fill = colour if (row, col) in {(0, 1), (1, 0), (1, 2), (2, 1)} else "#F0F3F6"
            if row == col:
                fill = "white"
            rect(x + col * w / 3, y + row * h / 3, w / 3, h / 3,
                 fill, GREY, lw=0.35, z=5)


def disciplinary_icon(kind, cx, cy, colour):
    """Small original vector symbols for the four OpenAlex domains."""
    if kind == "Physical":
        for angle in [0., 60., -60.]:
            ax.add_patch(Ellipse((cx,cy),5.4,2.2,angle=angle,facecolor="none",
                                 edgecolor=colour,lw=.65,zorder=5))
        dot(cx,cy,.4,colour,colour)
        dot(cx+2.35,cy+.55,.26,colour,colour)
    elif kind == "Life":
        yy = np.linspace(-2.45,2.45,100)
        xx = 1.25*np.sin(yy*1.45)
        for sign in [-1,1]:
            ax.plot(cx+sign*xx,cy+yy,color=colour,lw=.75,zorder=6)
        for y0 in np.linspace(-2.1,2.1,8):
            x0 = 1.25*np.sin(y0*1.45)
            path([(cx-x0,cy+y0),(cx+x0,cy+y0)],colour,.5,arrow=False,z=5)
    elif kind == "Health":
        vertices = np.array([
            [0,-2.4],[-3.5,.15],[-2.7,2.6],[-1.3,2.35],
            [-.6,2.3],[-.2,1.8],[0,1.25],
            [.2,1.8],[.6,2.3],[1.3,2.35],
            [2.7,2.6],[3.5,.15],[0,-2.4],[0,-2.4],
        ]) + np.array([cx,cy])
        codes = [MplPath.MOVETO]+[MplPath.CURVE4]*12+[MplPath.CLOSEPOLY]
        ax.add_patch(PathPatch(MplPath(vertices,codes),facecolor="#F8EDEA",
                               edgecolor=colour,lw=.65,zorder=5))
        path([(cx-1.75,cy-.05),(cx-.8,cy-.05),(cx-.35,cy+.75),
              (cx+.1,cy-.85),(cx+.55,cy+.1),(cx+1.65,cy+.1)],
             colour,.6,arrow=False,z=6)
    elif kind == "Social":
        for dx in [-1.8,1.8]:
            dot(cx+dx,cy+.85,.52,"#FBF3DF",colour)
            rect(cx+dx-.75,cy-1.9,1.5,1.65,"#FBF3DF",colour,.6,.6,z=5)
        dot(cx,cy+1.7,.65,"#F3E2B8",colour,z=7)
        rect(cx-1.,cy-1.9,2.,2.45,"#F3E2B8",colour,.65,.7,z=7)
    else:
        raise ValueError(kind)


def geo_projection(bounds, x, y, w, h, pad=.45, standard_latitude=31.2):
    """North-up local equirectangular projection; equal geographic aspect."""
    west, south, east, north = bounds
    assert west < east and south < north and min(w, h) > 2 * pad
    cos_lat = math.cos(math.radians(standard_latitude))
    scale = min((w-2*pad)/((east-west)*cos_lat), (h-2*pad)/(north-south))
    def project(coordinates):
        q = np.asarray(coordinates, dtype=float)
        return np.column_stack((x + w/2 + (q[:, 0]-(west+east)/2)*cos_lat*scale,
                                y + h/2 + (q[:, 1]-(south+north)/2)*scale))
    return project


def geo_draw(geometry, project, face, edge, lw=.35, z=4, clip=None, dashed=False):
    """Render the actual polygon rings or line vertices; do not invent shapes."""
    if geometry.is_empty:
        return
    if geometry.geom_type in {"MultiPolygon", "MultiLineString", "GeometryCollection"}:
        for part in geometry.geoms:
            geo_draw(part, project, face, edge, lw, z, clip, dashed)
        return
    if geometry.geom_type == "Polygon":
        paths = []
        for ring in [geometry.exterior, *geometry.interiors]:
            vertices = project(ring.coords)
            codes = np.full(len(vertices), MplPath.LINETO, dtype=np.uint8)
            codes[0], codes[-1] = MplPath.MOVETO, MplPath.CLOSEPOLY
            paths.append(MplPath(vertices, codes))
        patch = PathPatch(MplPath.make_compound_path(*paths), facecolor=face,
                          edgecolor=edge, lw=lw, zorder=z,
                          linestyle=(0, (1.5, 1.5)) if dashed else "solid")
        if clip is not None:
            patch.set_clip_path(clip)
        ax.add_patch(patch)
    elif geometry.geom_type in {"LineString", "LinearRing"}:
        p = project(geometry.coords)
        line, = ax.plot(p[:,0], p[:,1], color=edge, lw=lw, zorder=z,
                        solid_capstyle="round", solid_joinstyle="round")
        if clip is not None:
            line.set_clip_path(clip)


def primary_affiliation_map(x, y, side):
    """Actual national outline and city coordinates; candidate choice schematic."""
    clip = rect(x, y, side, side, "#F8FBFD", GREY, .45, .35, z=3)
    view_bounds = CONTEXT_MANIFEST["viewports_wgs84"]["national"]
    project = geo_projection(view_bounds, x, y, side, side, pad=0,
                             standard_latitude=35.)
    for geometry in MAP_CONTEXT["national"]:
        geo_draw(geometry, project, "#E3E8EC", "#C3CBD1", .2, 3.5, clip)
    geo_draw(CHINA, project, "#FCFDFE", GREY, .5, 4, clip)
    for province in PROVINCES:
        geo_draw(province.intersection(CHINA), project, "none", "#C3CBD1", .16, 5, clip)
    # Candidate dots are examples of affiliation cities, not mobility events.
    for selected in [False, True]:
        for feature in CANDIDATE_CITIES:
            if feature["properties"]["selected_primary_location"] != selected:
                continue
            xx, yy = project([feature["geometry"]["coordinates"]])[0]
            if selected:
                dot(xx, yy, 1.25, "none", GREEN, z=7)
                dot(xx, yy, .85, GREEN, "white", z=8)
            else:
                dot(xx, yy, .6, RED, "white", z=6)
    MAP_AUDIT["panels"]["primary_affiliation"] = {
        "rect_mm":[v*NATIVE_SCALE for v in [x,y,side,side]],
        "rect_design_units":[x,y,side,side], "bounds_wgs84":view_bounds,
        "highlighted_feature_bounds_wgs84":list(CHINA.bounds),
        "projection":"Local equirectangular, standard latitude 35 degrees; equal aspect",
        "candidate_city_count":len(CANDIDATE_CITIES),
        "selected_city_count":1, "selected_city_color":GREEN,
        "other_candidate_city_color":RED,
        "point_coordinates_sourced":True, "selection_is_illustrative":True,
        "surrounding_map_visible":True, "background_feature_count":len(MAP_CONTEXT["national"]),
    }


def city_harmonization_map(x, y, side):
    """One true city geometry, green, with its corresponding red district."""
    clip = rect(x, y, side, side, "#F8FBFD", GREY, .45, .35, z=3)
    view_bounds = CONTEXT_MANIFEST["viewports_wgs84"]["city"]
    project = geo_projection(view_bounds, x, y, side, side, pad=0)
    for geometry in MAP_CONTEXT["city"]:
        geo_draw(geometry, project, "#E3E8EC", "#BCC7CE", .22, 3.5, clip)
    geo_draw(SHANGHAI, project, "#D8EACB", GREEN, .65, 4, clip)
    for district in DISTRICTS:
        geo_draw(district.intersection(SHANGHAI), project, "none", "#A8C495", .22, 5, clip)
    geo_draw(PUDONG, project, "#E4AAA0", RED, .65, 6, clip)
    MAP_AUDIT["panels"]["city_harmonization"] = {
        "rect_mm":[v*NATIVE_SCALE for v in [x,y,side,side]],
        "rect_design_units":[x,y,side,side], "bounds_wgs84":view_bounds,
        "highlighted_feature_bounds_wgs84":list(SHANGHAI.bounds),
        "projection":"Local equirectangular, standard latitude 31.2 degrees; equal aspect",
        "parent_city_color":GREEN, "district_color":RED,
        "district_outside_parent_area":PUDONG.difference(SHANGHAI).area,
        "surrounding_map_visible":True, "background_feature_count":len(MAP_CONTEXT["city"]),
    }


def coverage_and_distribution(y, domestic=False):
    """Geographic coverage and flow-share glyphs, without disciplinary detail."""
    colour = GREEN if domestic else BLUE
    key = "city_summary" if domestic else "country_summary"
    frame(key, 98, y, 54, 21)
    text(111.4,y+3.2,"City Coverage" if domestic else "Country Coverage",7.2)
    text(137.3,y+3.2,"Flow Shares",7.2)
    # Keep the overall network glyph without its former dashed subframe.
    nodes = [(104.0, y + 12), (109.2, y + 15.0), (116.5, y + 14.0),
             (118.5, y + 9.0), (110.7, y + 9.2)]
    for a, b in [(0, 1), (1, 2), (2, 3), (4, 1), (0, 4)]:
        link(nodes[a], nodes[b], colour, trim=1.05, width=0.55)
    for xx, yy in nodes:
        if domestic:
            rect(xx - .9, yy - .9, 1.8, 1.8, "white", colour, .6, z=6)
        else:
            dot(xx, yy, .95, "white", colour)

    # A simple share profile replaces the former disciplinary sheet stack.
    shades = [colour, "#B7C7F9" if not domestic else "#A7CB8D",
              "#D3DEF9" if not domestic else "#CDDFC0", "#E6EBF6" if not domestic else "#E1E9DA"]
    for idx, height in enumerate([4.9, 3.6, 2.4, 1.4]):
        rect(129.8 + idx * 4.1, y + 9.0, 2.8, height + 1.4, shades[idx], colour, .4, z=6)


# Source entities, attribute families and coloured columns show data richness.
# Glyphs are schematic; they do not encode row counts or exact field counts.
frame("data",2,2,48,76)
text(5.,75.8,"Data",10.,weight="bold",ha="left")
for layer,(xx,yy) in enumerate([(7.7,63.3),(8.4,64.0),(9.1,64.7)]):
    paper(xx,yy,w=4.7,h=6.6,z=3+layer)
dot(25,67.,.95,"white",INK)
rect(23.55,62.9,2.9,2.8,"#EEF1F4",INK,.55,.9,z=6)
building(40,63.4,w=2.7,h=4.2)
for x,label in [(11.1,"Works"),(25,"Authors"),(40,"Institutions")]:
    text(x,60.7,label,7.2)
path([(11.1,58.8),(11.1,56.8),(40.,56.8),(40.,58.8)],
     LIGHT,.5,arrow=False)
path([(25.,58.8),(25.,56.8)],LIGHT,.5,arrow=False)
text(26.,53.4,"Fields",8.1)
attribute_groups=[
    (10.5,46.,"Identifiers",GREY), (26.,46.,"Time",DISCIPLINE_COLOR),
    (41.5,46.,"Geography",GREEN), (10.5,31.6,"Affiliations",BLUE),
    (26.,31.6,"Discipline",RED), (41.5,31.6,"Flows",INK),
]
for xx,yy,label,colour in attribute_groups:
    attribute_icon(label,xx,yy,colour)
    text(xx,yy-5.5,label,7.2)
text(26.,22.3,"Extracted Data",8.1)
data_output=linked_attribute_table(6.4,7.8)

# BRIDGE now encloses the preparation module as well as the analyses/model.
# Draw the real-map cards at global coordinates so their clipping remains exact.
bridge_border=frame("bridge",54.,2.,150.,76.)
text(57.,75.8,"BRIDGE",10.,weight="bold",ha="left")
frame("llm_processing",58.,8.,29.,64.)
text(72.5,69.7,"Data Processing",8.8,weight="bold")
input_endpoint=(58.,40.)
path([data_output,(52.,data_output[1]),(52.,40.),input_endpoint],lw=.8,radius=1.1)
path([(58.,40.),(59.3,40.)],ARROW_COLOR,.55,arrow=False)
path([(59.3,24.5),(59.3,55.5)],ARROW_COLOR,.55,arrow=False)
path([(59.3,55.5),(61.,55.5)],lw=.55)
path([(59.3,24.5),(61.,24.5)],lw=.55)
primary_affiliation_map(61.,44.,23.)
city_harmonization_map(61.,13.,23.)
map_captions=[
    text(72.5,40.,"Primary Affiliation\nSelection",7.),
    text(72.5,10.5,"City Merging (LLM)",7.),
]
# The vertically stacked cards are parallel operations, not sequential steps.
path([(84.,55.5),(85.5,55.5)],ARROW_COLOR,.55,arrow=False)
path([(84.,24.5),(85.5,24.5)],ARROW_COLOR,.55,arrow=False)
path([(85.5,24.5),(85.5,55.5)],ARROW_COLOR,.55,arrow=False)
path([(85.5,40.),(89.,40.)],ARROW_COLOR,.65,arrow=False)
path([(89.,18.),(89.,62.)],ARROW_COLOR,.65,arrow=False)
path([(89.,62.),(91.,62.)],lw=.8)
disciplinary_direct_input=[(89.,40.),(91.,40.)]
path(disciplinary_direct_input,lw=.8)
path([(89.,18.),(91.,18.)],lw=.8)
assert input_endpoint[0]==FRAMES["llm_processing"]["x"]

# The accepted analysis/model artwork retains its original global positions.
bridge_before=set(ax.get_children())
RESTORE_ARROW_COLORS=True

# International city links: country aggregation is used only by the country
# summary branch. The city links themselves also supply model predictors.
frame("international", 43, 50, 50, 24)
text(68, 72.1, "International Mobility", 8.8)
tile(55, 61.2, 18, 7.8, "#E9EFFC", "#B1BFE7")
tile(81, 61.2, 17, 7.8, "#E9EFFC", "#B1BFE7")
tile(68.5, 57.8, 13, 5.3, "#EEF2FC", "#B1BFE7")
intl = {"i": (52.2, 60.0), "j": (57.6, 63.1), "k": (78.2, 60.4),
        "l": (83.3, 63.0), "m": (66.8, 57.2), "n": (70.3, 58.1)}
for a, b, bend in [("i", "k", 0.10), ("k", "j", -0.12), ("j", "m", 0.0),
                   ("m", "i", 0.08), ("l", "n", 0.08), ("n", "k", 0.0)]:
    link(intl[a], intl[b], BLUE, bend=bend, width=0.75)
for xx, yy in intl.values():
    building(xx, yy, w=1.7, h=2.4)
text(54.5, 54.2, "A", 7.2)
text(81.0, 54.2, "B", 7.2)
text(68.5, 52.0, "C", 7.2)

# Domestic networks: i and j are the same schematic cities as above.
frame("domestic", 43, 6, 50, 24)
text(68, 27.8, "Domestic Mobility", 8.8)
tile(61.0, 17.5, 29, 12.5, "#EDF4E7", "#ACC795")
tile(83.0, 22.0, 10, 3.0, "#F0F5EC", "#ACC795")
tile(83.0, 12.7, 10, 3.0, "#F0F5EC", "#ACC795")
dom = {"i": (53.4, 16.5), "j": (60.6, 20.5), "p": (67.1, 17.5),
       "q": (62.8, 13.7), "r": (56.8, 13.5)}
for a, b in [("i", "j"), ("j", "p"), ("p", "q"), ("q", "i"), ("i", "r"), ("r", "p")]:
    link(dom[a], dom[b], GREEN, trim=1.3, width=0.75)
for xx, yy in dom.values():
    building(xx, yy, w=1.7, h=2.2)
for cy in [22.0, 12.7]:
    mini = [(80.9, cy - 0.2), (83.4, cy + 1.1), (85.1, cy - 0.1)]
    for a, b in [(0, 1), (1, 2)]:
        link(mini[a], mini[b], GREEN, trim=0.7, width=0.5)
    for xx, yy in mini:
        building(xx, yy, w=0.95, h=1.0)
text(60.6, 8.2, "A", 7.2)
text(83, 17.4, "B", 7.0)
text(83, 8.0, "C", 7.0)

# Parallel descriptive branches terminate inside BRIDGE.
coverage_and_distribution(53, domestic=False)
coverage_and_distribution(6, domestic=True)
path([(93, 62), (98, 62)], color=BLUE, lw=0.8)
path([(93, 18), (98, 18)], color=GREEN, lw=0.8)

# One compact disciplinary branch sits between the two mobility networks.
# Field-tagged event records and both mobility branches feed the four domains.
# Disciplinary information continues to enter the model on its own path.
frame("disciplinary", 43, 33.0, 50, 14.0)
text(68, 44.5, "Disciplines", 8.8)
domain_icons = []
for title, cx, colour, symbol in [
    ("Physical",49.,BLUE,"Atom"), ("Life",61.5,GREEN,"DNA"),
    ("Health",74.,RED,"Heart and pulse"), ("Social",86.5,DISCIPLINE_COLOR,"People"),
]:
    disciplinary_icon(title,cx,39.5,colour)
    text(cx,35.2,title,7.)
    domain_icons.append({"domain":title,"symbol":symbol,"color":colour,
                         "center_mm":[cx+48,39.5],"label_anchor_mm":[cx+48,35.2],
                         "cell_rect_mm":[cx+48-5.5,33.5,11.,8.3]})
path([(68, 50), (68, 47.0)], color=BLUE, lw=.8)
path([(68, 30), (68, 33.0)], color=GREEN, lw=.8)

# International and domestic links enter the gravity model directly;
# the former International feature extraction container is removed.
feature_input_routes = {
    "International":[(93.,55.),(95.5,55.),(95.5,48.),(101.,48.)],
    "Discipline":[(93.,40.),(101.,40.)],
    "Domestic":[(93.,25.),(95.5,25.),(95.5,32.),(101.,32.)],
}
for label,colour in [("International",BLUE),("Discipline",DISCIPLINE_COLOR),("Domestic",GREEN)]:
    path(feature_input_routes[label],color=colour,lw=.9,radius=.9)
# The three feature rows are unboxed; only the actual gravity-model node remains.
feature_rows = {"International":48.,"Discipline":40.,"Domestic":32.}
for label,tint in [("International","#C2D0FB"),("Discipline","#F1DDAE"),("Domestic","#C9DFB8")]:
    yy=feature_rows[label]
    text(108.425,yy-3.,label,7.)
    vector(101.,yy-1.15,9,tint,cell=1.65,height=2.3)
FRAME_PATCHES["gravity_model"]=rect(122.5,31.7,18.,16.6,"white",INK,.65,.6)
FRAMES["gravity_model"]=dict(x=122.5,y=31.7,width=18.,height=16.6)
gravity_model_label = text(131.5,44.,"Gravity\nModel",8.8)
# An editable globe-and-link icon follows the supplied visual design.
globe_cx,globe_cy,globe_r=131.5,35.9,3.4
globe_blue,globe_mesh,globe_orange="#337FB8","#A5B8C6","#E29A43"
for dy in [-globe_r*.5,0.,globe_r*.5]:
    half=math.sqrt(globe_r**2-dy**2)
    path([(globe_cx-half,globe_cy+dy),(globe_cx+half,globe_cy+dy)],
         globe_mesh,.35,arrow=False,z=5)
ax.add_patch(Ellipse((globe_cx,globe_cy),3.4,2*globe_r,
                     facecolor="none",edgecolor=globe_mesh,lw=.4,zorder=5))
ax.add_patch(Circle((globe_cx,globe_cy),globe_r,facecolor="none",
                    edgecolor=globe_blue,lw=.6,zorder=6))
globe_link=np.array([[-2.,-.9],[-.6,3.6],[1.4,3.1],[2.4,.9]])+np.array([globe_cx,globe_cy])
ax.add_patch(PathPatch(MplPath(globe_link,[MplPath.MOVETO]+[MplPath.CURVE4]*3),
                       facecolor="none",edgecolor=globe_orange,lw=.75,zorder=7))
for xx,yy in [globe_link[0],globe_link[-1]]:
    dot(xx,yy,.4,globe_orange,globe_orange,z=8)
feature_model_routes={
    "International":[(115.85,48.),(119.2,48.),(119.2,44.),(122.5,44.)],
    "Discipline":[(115.85,40.),(122.5,40.)],
    "Domestic":[(115.85,32.),(119.2,32.),(119.2,36.),(122.5,36.)],
}
for label,colour in [("International",BLUE),("Discipline",DISCIPLINE_COLOR),("Domestic",GREEN)]:
    path(feature_model_routes[label],color=colour,lw=.7,radius=.9)

# Only the model sends reconstructed flows to the compact external Output.
path([(140.5,40.),(161.,40.)],lw=.8)
frame("output",161.,29.,20.,22.,edge=DISCIPLINE_COLOR)
text(171.,47.,"Output",8.8)
matrix(166.,32.,w=10.,h=10.,colour="#E5C98C")

# Preserve the accepted horizontal BRIDGE/model layout without scaling.
bridge_transform = Affine2D().translate(48, 0) + ax.transData
for artist in ax.get_children():
    if artist not in bridge_before:
        artist.set_transform(bridge_transform)
for key, geometry in FRAMES.items():
    if key not in {"data", "bridge", "llm_processing"}:
        geometry["x"] += 48

# The upper/lower summary frames now have the same inset from the BRIDGE
# boundary as the first module's left edge. Output retains its external gap.
bridge=FRAMES['bridge']
assert FRAMES['llm_processing']['x']-bridge['x']==4.
assert bridge['x']+bridge['width']-(FRAMES['country_summary']['x']+FRAMES['country_summary']['width'])==4.
assert bridge['y']+bridge['height']-(FRAMES['country_summary']['y']+FRAMES['country_summary']['height'])==4.
assert FRAMES['city_summary']['y']-bridge['y']==4.
assert FRAMES['output']['x']-(bridge['x']+bridge['width'])==5.

# One drawing surface: conventional statistical panel alignment is N/A.
# Matching schematic containers are separately measured after final rendering.
arrows = [artist for artist in ax.patches if isinstance(artist, FancyArrowPatch)]
data_arrows = [artist for artist in arrows if artist in bridge_before]
bridge_arrows = [artist for artist in arrows if artist not in bridge_before]
from matplotlib.colors import to_rgba
assert data_arrows and all(artist.get_edgecolor() == to_rgba(ARROW_COLOR)
                          for artist in data_arrows)
bridge_palette = {artist.get_edgecolor() for artist in bridge_arrows}
assert bridge_palette == {to_rgba(c) for c in [BLUE, GREEN, DISCIPLINE_COLOR, ARROW_COLOR]}
assert all(artist.get_edgecolor() == artist.get_facecolor() for artist in arrows)
assert all(patch.get_facecolor()==to_rgba("white") for patch in FRAME_PATCHES.values())
for routes in [feature_input_routes,feature_model_routes]:
    upper=np.asarray(routes["International"])
    lower=np.asarray(routes["Domestic"])
    assert np.allclose(upper[:,0],lower[:,0])
    assert np.allclose(upper[:,1]+lower[:,1],80.)
    for label in ["International","Domestic"]:
        assert np.linalg.norm(np.diff(routes[label],axis=0),axis=1).min()>=2.5
assert feature_rows["International"]+feature_rows["Domestic"]==2*feature_rows["Discipline"]
assert FRAMES["output"]["height"]==22.
assert "Country Coverage & Shares" not in [artist.get_text() for artist in ax.texts]
assert "City Coverage & Shares" not in [artist.get_text() for artist in ax.texts]
assert input_endpoint==(58.,40.)
assert all(word[0].isupper() for artist in ax.texts
           for word in re.findall(r"[A-Za-z]+",artist.get_text()))
(QA/"connector_layout_audit.json").write_text(json.dumps({
    "module_frames_white":list(FRAME_PATCHES),
    "all_module_backgrounds_white":True,
    "display_labels_title_case":True,
    "output_label":"Output",
    "output_sources":["Gravity Model"],
    "summary_output_connectors":False,
    "summary_glyph_labels":["Country Coverage","City Coverage","Flow Shares"],
    "gravity_model_icon":"Vector globe, latitude/longitude mesh and orange arced connection",
    "horizontal_symmetry_axis_mm":40.*NATIVE_SCALE,
    "feature_row_centers_mm":{k:v*NATIVE_SCALE for k,v in feature_rows.items()},
    "international_domestic_input_routes_are_mirrored":True,
    "international_domestic_model_routes_are_mirrored":True,
    "model_route_vertical_leg_mm":4.*NATIVE_SCALE,
    "model_route_corner_radius_mm":.9*NATIVE_SCALE,
    "external_data_corner_radius_mm":1.1*NATIVE_SCALE,
    "shaft_and_arrowhead_share_a_continuous_path":True,
    "llm_input_stub_starts_at_external_arrow_endpoint":True,
    "map_arrowheads_end_at_map_border":True,
    "routes":ROUTES,
},indent=2),encoding="utf-8")
(QA / "arrow_color_audit.json").write_text(json.dumps({
    "arrow_count": len(arrows), "data_processing_arrow_count": len(data_arrows),
    "data_processing_arrows_black": True,
    "bridge_arrow_colors": [BLUE, GREEN, DISCIPLINE_COLOR, ARROW_COLOR],
    "bridge_original_blue_green_restored": True,
    "disciplinary_information_enters_model": True,
    "disciplinary_direct_input_from_event_records": True,
    "shaft_head_colors_match": True,
}, indent=2), encoding="utf-8")
fig.canvas.draw()
model_text_bounds = gravity_model_label.get_window_extent(fig.canvas.get_renderer()).transformed(
    ax.transData.inverted())
model_frame = FRAMES["gravity_model"]
assert "integrated" not in FRAMES
assert model_text_bounds.x0 > model_frame["x"]+.6
assert model_text_bounds.x1 < model_frame["x"]+model_frame["width"]-.6
assert model_text_bounds.y0 > model_frame["y"]+.6
assert model_text_bounds.y1 < model_frame["y"]+model_frame["height"]-.6
data_text=[]
for artist in ax.texts:
    bounds=artist.get_window_extent(fig.canvas.get_renderer()).transformed(ax.transData.inverted())
    if bounds.x0>=FRAMES["data"]["x"] and bounds.x1<=FRAMES["data"]["x"]+FRAMES["data"]["width"]:
        data_text.append(artist.get_text())
assert not any(character.isdigit() for label in data_text for character in label)
assert {item[2] for item in attribute_groups}==set(DATA_FIELDS)
(QA/"data_and_llm_layout_audit.json").write_text(json.dumps({
    "used_attribute_families":DATA_FIELDS,
    "attribute_source":"outputs/paper_final/methods.tex; source linkage and flow construction",
    "numeric_quantities_displayed":False,
    "table_columns":"Illustrative attribute groups, not literal field counts",
    "data_panel_text":data_text,
    "data_panel_width_mm":48.*NATIVE_SCALE,"bridge_width_mm":150.*NATIVE_SCALE,
    "llm_inside_bridge":True,"processing_heading":"Data Processing",
    "llm_scope":"City identity resolution and merging only",
    "primary_affiliation_selection":"Deterministic publication-count rule",
    "map_orientation":"Vertical","map_side_mm":23.*NATIVE_SCALE,"map_gap_mm":8.*NATIVE_SCALE,
    "map_captions":["Primary Affiliation Selection","City Merging (LLM)"],
    "nonselected_affiliation_cities_red":True,
    "map_operations_parallel":True,"between_map_arrows":0,
    "input_arrow_stops_at_llm_boundary":True,
    "legacy_trajectory_and_event_glyphs_replaced_by_data_overview":True,
},indent=2),encoding="utf-8")
require_matplotlib_panel_alignment(fig, json_out=QA / "alignment.json",
    overlay_svg=QA / "alignment.svg", tolerance_pt=1.5,
    gutter_tolerance_pt=1.5, strict=True)
for key in ["y", "height"]:
    assert FRAMES["data"][key] == FRAMES["bridge"][key]
for a, b in [("international", "domestic"), ("country_summary", "city_summary")]:
    for key in ["x", "width", "height"]:
        assert FRAMES[a][key] == FRAMES[b][key], (a, b, key)
map_rects = [p["rect_design_units"] for p in MAP_AUDIT["panels"].values()]
assert len(map_rects) == 2
assert all(r[2] == r[3] == 23. for r in map_rects)
assert map_rects[0][0] == map_rects[1][0]
assert map_rects[0][1]-map_rects[1][1]-map_rects[1][3] == 8.
assert MAP_AUDIT["panels"]["primary_affiliation"]["other_candidate_city_color"]==RED
llm=FRAMES["llm_processing"];bridge=FRAMES["bridge"]
assert bridge["x"]<llm["x"] and llm["x"]+llm["width"]<bridge["x"]+bridge["width"]
assert bridge["y"]<llm["y"] and llm["y"]+llm["height"]<bridge["y"]+bridge["height"]
assert MAP_AUDIT["panels"]["city_harmonization"]["district_outside_parent_area"] < 1e-10
assert disciplinary_direct_input[-1] == (FRAMES["disciplinary"]["x"],40.)
assert len(domain_icons) == 4
assert all(item["label_anchor_mm"][1] == 35.2 for item in domain_icons)
assert all(abs(domain_icons[j+1]["center_mm"][0]-domain_icons[j]["center_mm"][0]-12.5)<1e-8
           for j in range(3))
(QA / "disciplinary_layout_audit.json").write_text(json.dumps({
    "direct_input_from":"Harmonized locations and field-tagged mobility event records",
    "direct_input_path_mm":[[v*NATIVE_SCALE for v in point] for point in disciplinary_direct_input],
    "input_stops_at_module_boundary":True,
    "other_inputs":["International mobility","Domestic mobility"],
    "output":"Discipline feature row -> Gravity model",
    "four_domains":[{key:([v*NATIVE_SCALE for v in value] if key.endswith("_mm") else value)
                     for key,value in item.items()} for item in domain_icons],
    "uniform_center_spacing_mm":12.5*NATIVE_SCALE,
    "label_baseline_aligned":True,
},indent=2),encoding="utf-8")

stem = OUT / "Fig1_detailed"
fig.savefig(stem.with_suffix(".pdf"), format="pdf")
fig.savefig(stem.with_suffix(".svg"), format="svg")
fig.savefig(stem.with_suffix(".png"), format="png", dpi=600)
# A Matplotlib-rendered close-up makes the sourced map detail easy to review.
from matplotlib.transforms import Bbox
fig.savefig(OUT / "Fig1_city_merge_detail.png", dpi=450,
            bbox_inches=Bbox.from_extents(*[v*NATIVE_SCALE/25.4 for v in [56,6,89,74]]))
fig.savefig(OUT / "Fig1_data_and_llm_detail.png", dpi=450,
            bbox_inches=Bbox.from_extents(*[v*NATIVE_SCALE/25.4 for v in [0,1,91,81]]))
fig.savefig(OUT / "Fig1_disciplines_detail.png", dpi=450,
            bbox_inches=Bbox.from_extents(*[v*NATIVE_SCALE/25.4 for v in [84,31,144,52]]))
fig.savefig(OUT / "Fig1_model_detail.png", dpi=450,
            bbox_inches=Bbox.from_extents(*[v*NATIVE_SCALE/25.4 for v in [140,26,228,53]]))
plt.close(fig)
(QA / "map_geometry_audit.json").write_text(json.dumps(MAP_AUDIT, indent=2), encoding="utf-8")

contract = {
    "role": "Internal detailed vector schematic",
    "archetype": "schematic-led composite",
    "message": "Affiliation records support parallel coverage/distribution analyses "
               "disciplinary comparisons and a domestic allocation model with international, domestic and disciplinary inputs.",
    "backend": "Python / Matplotlib", "dimensions_mm": [WIDTH, HEIGHT],
    "arrow_colors": {"data_processing": ARROW_COLOR, "international": BLUE,
                     "domestic": GREEN, "disciplinary_input": DISCIPLINE_COLOR,
                     "model_output": ARROW_COLOR},
    "compact_layout": "Native 180-mm artwork; Data and BRIDGE retain matching edges and heights. Data Processing contains equal square map cards, operation captions and parallel rails. LLM is labelled only on the city-merging step. Geometry is proportional to the established layout, with typography set independently at final size.",
    "formatting":specification(),
    "style_adaptation": "General thin outlines, rounded containers, pale fills, "
                        "compact local-to-regional map thumbnails, isometric city glyphs and feature cells; all drawn anew. Reference reused for style only.",
    "empirical_data": "The left panel illustrates attribute families actually used in record linkage and mobility construction, without quantities. The two unlabeled national/city map cards use sourced boundaries and city coordinates. Candidate selection, table rows/columns, networks, feature cells, matrix shades and share bars are illustrative.",
    "data_attribute_families":DATA_FIELDS,
    "data_quantities_displayed":False,
    "model": "Gravity-based allocation; blue international, green domestic and gold disciplinary inputs.",
    "model_outer_container_displayed": False,
    "model_display_label": "Gravity Model",
    "model_node_label_font_pt":7.,
    "international_feature_cells": 9, "reference_predictor_cells": 9,
    "panel_backgrounds": "White; colours are retained for geographic features, attribute glyphs, feature cells and flow information",
    "connector_layout": "Continuous shafts/heads; rounded elbows; upper/lower model inputs mirrored about y=40 mm",
    "output_display_label": "Output",
    "data_display_labels":["Fields","Extracted Data"],
    "map_operation_captions":["Primary Affiliation Selection","City Merging (LLM)"],
    "model_icon":"Editable globe with latitude/longitude lines and an orange arced connection",
    "label_capitalization": "Initial capital for every displayed word; BRIDGE and LLM retained",
    "international_input_path": ["International city network", "Network feature vector", "Gravity model"],
    "disciplinary_input_path": ["Disciplines", "Discipline feature vector", "Gravity model"],
    "external_edges": ["Gravity Model -> Output"],
    "data_processing_scope": "Primary affiliation selected by publication-count rules; LLM assists city-name disambiguation and identity harmonization",
    "geographic_example": "Two equal square maps: one selected green city among red candidate cities on a real national map; a red district inside a green parent city. No place names or street map displayed.",
    "parallel_data_preparation": {"branches": ["Primary affiliation", "City harmonization"],
                                  "inter_branch_edges": [], "joint_output": "Annual researcher locations",
                                  "external_input_endpoint_mm": [v*NATIVE_SCALE for v in input_endpoint],
                                  "input_stops_at_frame_boundary": True,
                                  "module_inside_bridge":True,"heading":"Data Processing",
                                  "llm_branch":"City harmonization only",
                                  "map_orientation":"Vertical"},
    "map_provenance": [str(MAP_DATA / "manifest.json"), str(SQUARE_MAP_DATA / "manifest.json"),
                       str(CONTEXT_MAP_DATA / "manifest.json")],
    "surrounding_geographic_context": "Both square maps show sourced neighboring geography in neutral gray, with no place names",
    "disciplinary_display": "Four original domain icons: atom, DNA, heart/pulse and people; short labels Physical, Life, Health and Social",
    "disciplinary_direct_input": "Shared field-tagged event stream -> Disciplines; international and domestic inputs also retained",
    "text_reduction": "Data Processing is the module heading; LLM is attached only to city merging. Short operation captions remain below the maps. Fields and Extracted Data replace longer labels. Attribute icons and coloured columns express data richness. Displayed words have initial capitals. Output receives only reconstructed flows from the gravity model; coverage and share glyphs are labelled individually.",
    "descriptive_summaries_feed_model": False, "reference_model_displayed": False,
    "no_causal_or_forecasting_claim": True,
    "schematic_frames_mm":{k:{axis:value*NATIVE_SCALE for axis,value in geometry.items()} for k,geometry in FRAMES.items()},
    "repeated_container_geometry": "Corresponding left edges, widths and heights equal by construction",
    "current_manuscript_modified": "Fig.1–6 share native 180-mm width and final-size Arial typography",
    "submission_eligibility": "Not assessed for this internal design draft",
}
(QA / "design_contract.json").write_text(json.dumps(contract, indent=2), encoding="utf-8")
(OUT / "Caption_EN_ZH.txt").write_text(
    'BRIDGE framework for analysing researcher mobility. Linked publication, author and institution records provide the fields used to construct mobility data. The maps illustrate parallel steps: primary-affiliation selection by publication counts and city harmonization assisted by a large language model (LLM). Green marks the selected affiliation city and red the other candidates (upper); a red district is merged into its green parent city (lower). Location changes define international and domestic intercity mobility events. Coverage and flow shares are compared across countries, domestic cities and four disciplinary domains. International, domestic and disciplinary inputs jointly enter the gravity model, with reconstructed domestic origin--destination flows shown in Output. Networks, tables and profiles are schematic. Map sources: Natural Earth, geoBoundaries, GeoNames and © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).\n\nBRIDGE研究者流动分析框架。关联文献、作者和机构记录，提取构建流动数据所需的字段。两张地图表示并行的数据处理步骤：按出版物数量选择主要机构，以及由大语言模型（LLM）辅助统一城市身份。上图中，绿色表示主要机构所在城市，红色表示其他候选城市；下图中，红色城区归并至绿色的所属城市。机构所在地的变化用于识别跨国和国内城际流动事件。在国家、国内城市和四大学科层面比较地理覆盖与流量份额。国际、国内和学科信息共同进入引力模型，Output展示模型重建的国内城际起点—终点流量。网络、表格和分布图形均为示意。地图来源：Natural Earth、geoBoundaries、GeoNames与© OpenStreetMap贡献者（https://www.openstreetmap.org/copyright）。\n',
    encoding="utf-8",
)

print(json.dumps({"pdf": str(stem.with_suffix('.pdf')), "svg": str(stem.with_suffix('.svg')),
                  "png": str(stem.with_suffix('.png'))}))
