"""Editable BRIDGE schematic, with isometric city glyphs and explicit inputs.

The schematic inherits only general visual conventions from a supplied style
reference. All vector artwork is drawn anew. Icons, example networks, feature
cells and flow-share glyphs are conceptual illustrations. The two map cards
use attributed geographic source data, without displayed place names.
"""

from __future__ import annotations

import json
import csv
import hashlib
import math
import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa'))
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

OUT = PROJECT / "outputs/fig1_histogram_fig2_labels_20261109/artwork"
QA = PROJECT / "outputs/fig1_histogram_fig2_labels_20261109/QA/Fig1"
OUT.mkdir(parents=True, exist_ok=True)
QA.mkdir(parents=True, exist_ok=True)

DESIGN_WIDTH, DESIGN_HEIGHT = 214.0, 106.0
# Crop the deleted output card while preserving the accepted geometry and type.
WIDTH = 178.0 * DESIGN_WIDTH / 231.0
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
        options["linestyle"] = (0, (4.0, 2.6))
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


# Native Matplotlib layout; map and glyph helpers are inherited from the
# preserved Fig1 source. Symbols remain conceptual, without encoded measurements.
domain_icons = []


def coverage_and_distribution(y, domestic=False):
    colour = GREEN if domestic else BLUE
    branch = "Domestic" if domestic else "International"
    frame("city_summary" if domestic else "country_summary", 98., y, 54., 32.)
    text(111.4,y+18.5,"City Coverage" if domestic else "Country Coverage",7.)
    text(137.3,y+18.5,"Flow Shares",7.)
    nodes = [(104.,y+25.),(109.2,y+28.),(116.5,y+27.),
             (118.5,y+22.),(110.7,y+22.2)]
    for a,b in [(0,1),(1,2),(2,3),(4,1),(0,4)]:
        link(nodes[a],nodes[b],colour,trim=1.05,width=.55)
    for xx,yy in nodes:
        if domestic:
            rect(xx-.9,yy-.9,1.8,1.8,"white",colour,.6,z=6)
        else:
            dot(xx,yy,.95,"white",colour)
    shades=[colour,"#B7C7F9" if not domestic else "#A7CB8D",
            "#D3DEF9" if not domestic else "#CDDFC0",
            "#E6EBF6" if not domestic else "#E1E9DA"]
    for j,h in enumerate([4.9,3.6,2.4,1.4]):
        rect(129.8+j*4.1,y+22.,2.8,h+1.4,shades[j],colour,.4,z=6)
    path([(100.,y+15.5),(150.,y+15.5)],LIGHT,.45,arrow=False)
    text(125.,y+12.5,"By Discipline",7.)
    for title,cx,tint,symbol in [
        ("Physical",105.1,BLUE,"Atom"),("Life",118.3,GREEN,"DNA"),
        ("Health",131.5,RED,"Heart and pulse"),("Social",144.7,DISCIPLINE_COLOR,"People")
    ]:
        disciplinary_icon(title,cx,y+7.6,tint)
        text(cx,y+2.5,title,7.)
        domain_icons.append(dict(branch=branch,domain=title,symbol=symbol,color=tint,
                                 center_mm=[cx+48.,y+7.6],label_anchor_mm=[cx+48.,y+2.5]))


# Data and BRIDGE are conceptual containers, distinguished by dashed borders.
frame("data",2.,2.,48.,100.,dashed=True)
text(5.,99.8,"Data",10.,weight="bold",ha="left")
for layer,(xx,yy) in enumerate([(7.7,87.3),(8.4,88.),(9.1,88.7)]):
    paper(xx,yy,w=4.7,h=6.6,z=3+layer)
dot(25.,91.,.95,"white",INK)
rect(23.55,86.9,2.9,2.8,"#EEF1F4",INK,.55,.9,z=6)
building(40.,87.4,w=2.7,h=4.2)
for x,label in [(11.1,"Works"),(25.,"Authors"),(40.,"Institutions")]:
    text(x,84.7,label,7.)
path([(11.1,82.8),(11.1,80.8),(40.,80.8),(40.,82.8)],LIGHT,.5,arrow=False)
path([(25.,82.8),(25.,80.8)],LIGHT,.5,arrow=False)
text(26.,71.4,"Fields",8.1)
attribute_groups=[
    (10.5,58.,"Identifiers",GREY),(26.,58.,"Time",DISCIPLINE_COLOR),
    (41.5,58.,"Geography",GREEN),(10.5,37.6,"Affiliations",BLUE),
    (26.,37.6,"Discipline",RED),(41.5,37.6,"Flows",INK)]
for xx,yy,label,colour in attribute_groups:
    attribute_icon(label,xx,yy,colour)
    text(xx,yy-5.5,label,7.)
text(26.,22.3,"Extracted Data",8.1)
data_output=linked_attribute_table(6.4,7.8)

frame("bridge",54.,2.,150.,100.,dashed=True)
text(57.,99.8,"BRIDGE",10.,weight="bold",ha="left")
frame("llm_processing",58.,8.,29.,88.)
text(72.5,93.7,"LLM",8.8,weight="bold")
input_endpoint=(58.,52.)
path([data_output,(52.,data_output[1]),(52.,52.),input_endpoint],lw=.8,radius=1.1)
path([(58.,52.),(59.3,52.)],ARROW_COLOR,.55,arrow=False)
path([(59.3,28.5),(59.3,75.5)],ARROW_COLOR,.55,arrow=False)
path([(59.3,75.5),(61.,75.5)],lw=.55)
path([(59.3,28.5),(61.,28.5)],lw=.55)
primary_affiliation_map(61.,64.,23.)
city_harmonization_map(61.,17.,23.)
text(72.5,60.,"Primary Affiliation\nSelection",7.)
text(72.5,14.5,"City Merging",7.)
path([(84.,75.5),(85.5,75.5)],ARROW_COLOR,.55,arrow=False)
path([(84.,28.5),(85.5,28.5)],ARROW_COLOR,.55,arrow=False)
path([(85.5,28.5),(85.5,75.5)],ARROW_COLOR,.55,arrow=False)
path([(85.5,52.),(89.,52.)],ARROW_COLOR,.65,arrow=False)
path([(89.,20.),(89.,84.)],ARROW_COLOR,.65,arrow=False)
path([(89.,84.),(91.,84.)],lw=.8)
path([(89.,20.),(91.,20.)],lw=.8)

bridge_before=set(ax.get_children())
RESTORE_ARROW_COLORS=True

# Two equally tall networks leave room for the quantitative histogram.
resized_network_artists=set()
network_start=set(ax.get_children())
frame("international",43.,58.,50.,32.)
text(68.,87.8,"International Mobility",8.8)
tile(55.,75.,18.,10.,"#E9EFFC","#B1BFE7")
tile(81.,75.,17.,10.,"#E9EFFC","#B1BFE7")
tile(68.5,68.,13.,6.5,"#EEF2FC","#B1BFE7")
intl={"i":(52.2,74.),"j":(57.6,78.),"k":(78.2,74.4),
      "l":(83.3,78.),"m":(66.8,67.4),"n":(70.3,69.2)}
for a,b,bend in [("i","k",.10),("k","j",-.12),("j","m",0.),
                 ("m","i",.08),("l","n",.08),("n","k",0.)]:
    link(intl[a],intl[b],BLUE,bend=bend,width=.75)
for xx,yy in intl.values():
    building(xx,yy,w=1.7,h=2.4)
for xx,yy,label in [(54.5,66.2,"A"),(81.,66.2,"B"),(68.5,60.5,"C")]:
    text(xx,yy,label,7.)

international_artists=set(ax.get_children())-network_start
for artist in international_artists:
    artist.set_transform(Affine2D().translate(0.,-58.).scale(1.,.875).translate(48.,70.)+ax.transData)
resized_network_artists.update(international_artists)
FRAMES['international'].update(y=70.,height=28.)
network_start=set(ax.get_children())

frame("domestic",43.,6.,50.,32.)
text(68.,35.8,"Domestic Mobility",8.8)
tile(61.,21.5,29.,16.5,"#EDF4E7","#ACC795")
tile(83.,28.,10.,3.,"#F0F5EC","#ACC795")
tile(83.,14.5,10.,3.,"#F0F5EC","#ACC795")
dom={"i":(53.4,20.2),"j":(60.6,25.8),"p":(67.1,21.5),
     "q":(62.8,16.5),"r":(56.8,17.)}
for a,b in [("i","j"),("j","p"),("p","q"),("q","i"),("i","r"),("r","p")]:
    link(dom[a],dom[b],GREEN,trim=1.3,width=.75)
for xx,yy in dom.values():
    building(xx,yy,w=1.7,h=2.2)
for cy in [28.,14.5]:
    mini=[(80.9,cy-.2),(83.4,cy+1.1),(85.1,cy-.1)]
    for a,b in [(0,1),(1,2)]:
        link(mini[a],mini[b],GREEN,trim=.7,width=.5)
    for xx,yy in mini:
        building(xx,yy,w=.95,h=1.)
for xx,yy,label in [(60.6,8.2,"A"),(83.,22.4,"B"),(83.,8.9,"C")]:
    text(xx,yy,label,7.)

domestic_artists=set(ax.get_children())-network_start
for artist in domestic_artists:
    artist.set_transform(Affine2D().translate(0.,-6.).scale(1.,.875).translate(48.,6.)+ax.transData)
resized_network_artists.update(domestic_artists)
FRAMES['domestic'].update(height=28.)

# The full Fig2c source distribution replaces the text-only typology card.
frame('trajectory_groups',43.,36.,50.,32.)
text(68.,65.8,'Share Growth (%/Year)',7.)
path([(68.,70.),(68.,68.)],BLUE,.65)
path([(68.,36.),(68.,34.)],GREY,.6,arrow=False,dashed=True)

# Four disciplinary domains appear within BOTH subsequent analysis cards.
coverage_and_distribution(66.,domestic=False)
coverage_and_distribution(6.,domestic=True)
path([(93.,84.),(98.,84.)],BLUE,.8)
path([(93.,20.),(98.,20.)],GREEN,.8)

# Mobility and field-tagged information supply model features directly.
# Descriptive coverage and share outputs are not themselves model predictors.
feature_input_routes={
    "International":[(93.,76.),(95.5,76.),(95.5,60.),(101.,60.)],
    "Domestic":[(93.,28.),(95.5,28.),(95.5,44.),(101.,44.)]}
feature_rows={"International":60.,"Domestic":44.}
for label,colour,tint in [("International",BLUE,"#C2D0FB"),("Domestic",GREEN,"#C9DFB8")]:
    path(feature_input_routes[label],colour,.9,radius=.9)
    yy=feature_rows[label]
    text(108.425,yy+(-3. if label=="International" else 3.),label,7.)
    vector(101.,yy-1.15,6,tint,cell=1.65,height=2.3)
    vector(110.9,yy-1.15,3,"#F1DDAE",cell=1.65,height=2.3)
FRAME_PATCHES["gravity_model"]=rect(122.5,43.7,18.,16.6,"white",INK,.65,.6)
FRAMES["gravity_model"]=dict(x=122.5,y=43.7,width=18.,height=16.6)
gravity_model_label=text(131.5,56.,"Gravity\nModel",8.8)
globe_cx,globe_cy,globe_r=131.5,47.9,3.4
globe_blue,globe_mesh,globe_orange="#337FB8","#A5B8C6","#E29A43"
for dy in [-globe_r*.5,0.,globe_r*.5]:
    half=math.sqrt(globe_r**2-dy**2)
    path([(globe_cx-half,globe_cy+dy),(globe_cx+half,globe_cy+dy)],globe_mesh,.35,arrow=False,z=5)
ax.add_patch(Ellipse((globe_cx,globe_cy),3.4,2*globe_r,facecolor="none",edgecolor=globe_mesh,lw=.4,zorder=5))
ax.add_patch(Circle((globe_cx,globe_cy),globe_r,facecolor="none",edgecolor=globe_blue,lw=.6,zorder=6))
globe_link=np.array([[-2.,-.9],[-.6,3.6],[1.4,3.1],[2.4,.9]])+np.array([globe_cx,globe_cy])
ax.add_patch(PathPatch(MplPath(globe_link,[MplPath.MOVETO]+[MplPath.CURVE4]*3),
                       facecolor="none",edgecolor=globe_orange,lw=.75,zorder=7))
for xx,yy in [globe_link[0],globe_link[-1]]:
    dot(xx,yy,.4,globe_orange,globe_orange,z=8)
feature_model_routes={
    "International":[(115.85,60.),(119.2,60.),(119.2,56.),(122.5,56.)],
    "Domestic":[(115.85,44.),(119.2,44.),(119.2,48.),(122.5,48.)]}
for label,colour in [("International",BLUE),("Domestic",GREEN)]:
    path(feature_model_routes[label],colour,.7,radius=.9)
path([(140.5,52.),(161.,52.)],lw=.8)
output_center=(162.5,52.)
output_radius=1.5
ax.add_patch(Circle(output_center,output_radius,facecolor="white",edgecolor=DISCIPLINE_COLOR,lw=.8,zorder=5))

bridge_transform=Affine2D().translate(48.,0.)+ax.transData
for artist in ax.get_children():
    if artist not in bridge_before and artist not in resized_network_artists:
        artist.set_transform(bridge_transform)
for key,geometry in FRAMES.items():
    if key not in {"data","bridge","llm_processing"}:
        geometry["x"]+=48.

# Compact, quantitative Fig2c inset: original bins and country counts.
data=OUT.parent/'source_data'
def read_histogram(name):
    with (data/name).open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))
hist=read_histogram('Fig2_quartile_histogram.csv')
trends=read_histogram('Fig2_quartile_country_trends.csv')
provenance=json.loads((data/'Fig2_quartile_provenance.json').read_text(encoding='utf8'))
rates=np.array([float(r['international_share_annual_rate_pct']) for r in trends])
counts=np.array([int(r['countries']) for r in hist])
edges=np.r_[[float(r['lower']) for r in hist],float(hist[-1]['upper'])]
cuts=np.array(provenance['quartile_cuts'])
boundaries=np.r_[edges[0],cuts,edges[-1]]
assert np.array_equal(np.histogram(rates,bins=edges)[0],counts)
assert counts.sum()==76 and np.allclose(np.quantile(rates,[.25,.5,.75]),cuts)
group_counts=[sum(int(r['group'])==q for r in trends) for q in range(1,5)]
assert group_counts==[19]*4
hist_ax=fig.add_axes([96.5/DESIGN_WIDTH,43./DESIGN_HEIGHT,42./DESIGN_WIDTH,16.3/DESIGN_HEIGHT])
hist_ax.set_gid('share_growth_inset')
palette=[BLUE,GREY,GREEN,RED]
for j,(lo,hi) in enumerate(zip(boundaries[:-1],boundaries[1:])):
    local_edges=np.r_[lo,edges[(edges>lo)&(edges<hi)],hi]
    mid=(local_edges[:-1]+local_edges[1:])/2
    local_counts=counts[np.searchsorted(edges,mid,side='right')-1]
    hist_ax.stairs(local_counts,local_edges,fill=True,color=palette[j],alpha=.23,linewidth=0)
hist_ax.stairs(counts,edges,color='#3F776A',linewidth=.8)
hist_ax.set(xlim=(edges[0],edges[-1]),ylim=(0,counts.max()*1.08))
hist_ax.set_xticks([-5,0,5,10]);hist_ax.set_yticks([5,10])
hist_ax.tick_params(length=1.8,width=.5,pad=.7,labelsize=7.)
hist_ax.spines[['top','right']].set_visible(False)
hist_ax.spines[['left','bottom']].set_linewidth(.5)
hist_ax.grid(False)
for cut in cuts:
    hist_ax.axvline(cut,color='#92999D',lw=.45,ls=(0,(2,2)),zorder=0)
for j in range(4):
    left=96.5+j*10.75
    rect(left,59.9,9.75,3.8,matplotlib.colors.to_rgba(palette[j],.18),palette[j],.35,.4,z=5)
    text(left+4.875,61.8,f'T{j+1}',7.)
hist_ax.set_facecolor('white')

# Rendered checks use physical coordinates and retain the 1.5-pt contract.
fig.canvas.draw()
require_matplotlib_panel_alignment(fig,axes=[ax],json_out=QA/"alignment.json",
    overlay_svg=QA/"alignment.svg",tolerance_pt=1.5,gutter_tolerance_pt=1.5,strict=True)
for key in ["y","height"]:
    assert FRAMES["data"][key]==FRAMES["bridge"][key]
for upper,lower in [("international","domestic"),("country_summary","city_summary")]:
    for key in ["x","width","height"]:
        assert FRAMES[upper][key]==FRAMES[lower][key]
    assert FRAMES[upper]["y"]+FRAMES[lower]["y"]+FRAMES[lower]["height"]==104.
assert "disciplinary" not in FRAMES
assert FRAMES['trajectory_groups']['y']>FRAMES['domestic']['y']+FRAMES['domestic']['height']
assert FRAMES['trajectory_groups']['y']+FRAMES['trajectory_groups']['height']<FRAMES['international']['y']
assert FRAMES['trajectory_groups']['width']==FRAMES['international']['width']
assert all(FRAME_PATCHES[key].get_linestyle()!="solid" for key in ["data","bridge"])
assert all(FRAME_PATCHES[key].get_linestyle()=="solid" for key in FRAME_PATCHES if key not in {"data","bridge"})
assert len(domain_icons)==8
for branch in ["International","Domestic"]:
    icons=[r for r in domain_icons if r["branch"]==branch]
    assert [r["domain"] for r in icons]==["Physical","Life","Health","Social"]
    assert len({r["label_anchor_mm"][1] for r in icons})==1
    assert np.allclose(np.diff([r["center_mm"][0] for r in icons]),13.2)
assert set(feature_rows)=={"International","Domestic"}
assert sum(feature_rows.values())==104.
for routes in [feature_input_routes,feature_model_routes]:
    upper,lower=[np.asarray(routes[label]) for label in ["International","Domestic"]]
    assert np.allclose(upper[:,0],lower[:,0])
    assert np.allclose(upper[:,1]+lower[:,1],104.)
    assert all(np.linalg.norm(np.diff(points,axis=0),axis=1).min()>=2.5 for points in [upper,lower])
assert output_center[0]+48.-output_radius-(FRAMES["bridge"]["x"]+FRAMES["bridge"]["width"])==5.
assert abs(WIDTH/DESIGN_WIDTH-178./231.)<1e-12
assert input_endpoint==(FRAMES["llm_processing"]["x"],52.)
map_rects=[r["rect_design_units"] for r in MAP_AUDIT["panels"].values()]
assert len(map_rects)==2 and all(r[2]==r[3]==23. for r in map_rects)
assert map_rects[0][0]==map_rects[1][0]
assert MAP_AUDIT["panels"]["city_harmonization"]["district_outside_parent_area"]<1e-10
assert MAP_AUDIT["panels"]["primary_affiliation"]["other_candidate_city_color"]==RED
assert {r[2] for r in attribute_groups}==set(DATA_FIELDS)
from matplotlib.colors import to_rgba
assert all(p.get_facecolor()==to_rgba("white") for p in FRAME_PATCHES.values())
arrows=[p for p in ax.patches if isinstance(p,FancyArrowPatch)]
assert all(p.get_facecolor()==p.get_edgecolor() for p in arrows)
assert all(p.get_edgecolor()==to_rgba(ARROW_COLOR) for p in arrows if p in bridge_before)
assert {p.get_edgecolor() for p in arrows if p not in bridge_before}=={to_rgba(c) for c in [BLUE,GREEN,ARROW_COLOR]}
renderer=fig.canvas.get_renderer()
model_bounds=gravity_model_label.get_window_extent(renderer).transformed(ax.transData.inverted())
model_frame=FRAMES["gravity_model"]
assert model_frame["x"]+.6<model_bounds.x0<model_bounds.x1<model_frame["x"]+model_frame["width"]-.6
assert model_frame["y"]+.6<model_bounds.y0<model_bounds.y1<model_frame["y"]+model_frame["height"]-.6

contract=dict(
    figure="Fig1",backend="Python / Matplotlib",dimensions_mm=[WIDTH,HEIGHT],
    message="Two geographic scales, each followed by coverage, flow-share and disciplinary analyses; field-tagged mobility information also enters gravity modelling.",
    typography=specification(),outer_borders={"Data":"dashed","BRIDGE":"dashed"},
    mobility_panel_height_mm=28.*NATIVE_SCALE,analysis_panel_height_mm=32.*NATIVE_SCALE,
    removed="Separate central Disciplines module and third model-input row",
    disciplinary_location="Four-domain row in each scale's subsequent analysis card",
    field_information_in_model="Pale gold cells embedded within branch-specific illustrative feature vectors",
    descriptive_summaries_feed_model=False,output="Unlabelled small circle",
    model="Gravity model; predictor definitions and underlying analyses unchanged",
    conceptual_marks="Networks, share bars, feature cells and icons are schematic, not empirical values or exact feature counts",
    map_provenance=MAP_AUDIT["sources"],map_geometry_synthetic=False,
    routes=ROUTES,domain_icons=domain_icons,
    frames_mm={k:{a:v*NATIVE_SCALE for a,v in geometry.items()} for k,geometry in FRAMES.items()},
    symmetry_axis_mm=52.*NATIVE_SCALE,feature_rows_mm={k:v*NATIVE_SCALE for k,v in feature_rows.items()},
    country_typology=dict(labels=['T1','T2','T3','T4'],countries_per_group=group_counts,
        rule='Ascending quartiles of fitted growth in worldwide international mobility shares',
        cuts_pct_per_year=cuts.tolist(),histogram_bins=22,
        source_sha256=hashlib.sha256((data/'Fig2_quartile_histogram.csv').read_bytes()).hexdigest()),
    alignment_note="Single schematic canvas plus a quantitative inset; repeated schematic container bounds and paired connectors checked explicitly. Histogram inset is not a comparable schematic panel.")
(QA/"design_contract.json").write_text(json.dumps(contract,ensure_ascii=False,indent=2),encoding="utf8")
(QA/"map_geometry_audit.json").write_text(json.dumps(MAP_AUDIT,indent=2),encoding="utf8")
(QA/"disciplinary_layout_audit.json").write_text(json.dumps(dict(domains_per_branch=4,
    total_icons=8,standalone_discipline_module=False,standalone_discipline_feature_row=False,
    domain_icons=domain_icons),indent=2),encoding="utf8")
(QA/'typology_audit.json').write_text(json.dumps(contract['country_typology'],indent=2),encoding='utf8')
stem=OUT/"Fig1"
fig.savefig(stem.with_suffix(".pdf"),format="pdf")
fig.savefig(stem.with_suffix(".svg"),format="svg")
fig.savefig(stem.with_suffix(".png"),format="png",dpi=600)
plt.close(fig)
import pymupdf
with pymupdf.open(stem.with_suffix(".pdf")) as doc:
    page=doc[0]
    page.get_pixmap(matrix=pymupdf.Matrix(2.8,2.8),alpha=False).save(QA/"preview.png")
    for name in ["international","trajectory_groups","domestic","country_summary","city_summary","gravity_model"]:
        r=FRAMES[name]
        x0,y0,x1,y1=r["x"],r["y"],r["x"]+r["width"],r["y"]+r["height"]
        factor=NATIVE_SCALE/25.4*72
        clip=pymupdf.Rect(x0*factor-2,(DESIGN_HEIGHT-y1)*factor-2,x1*factor+2,(DESIGN_HEIGHT-y0)*factor+2)
        page.get_pixmap(matrix=pymupdf.Matrix(3.5,3.5),clip=clip,alpha=False).save(QA/f"detail_{name}.png")
print(json.dumps(dict(figure="Fig1",dimensions_mm=[WIDTH,HEIGHT],discipline_rows=2,domains_per_row=4)))
