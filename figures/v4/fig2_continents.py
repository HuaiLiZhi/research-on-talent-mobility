"""Continent enclosures for the unique-city display in Fig2e.

Country membership follows UN M49 geographic regions. Northern America,
Central America and the Caribbean are combined as North America. Display
coordinates and outlines have no geographic-distance interpretation.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial import ConvexHull
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch

CONTINENT_CODES = {
    'North America': 'CA CR CU MX PR US',
    'South America': 'AR BR CL CO VE',
    'Europe': 'AT BE BG BY CH CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LT MT NL NO PL PT RO RS RU SE SI SK UA',
    'Asia': 'AE AM BD CN ID IL IN IR JO JP KR LK MY PH PK SA TH TR VN',
    'Africa': 'CM DZ EG GH KE MA MW NG TN TZ UG ZA',
    'Oceania': 'AU NZ',
}
COUNTRY_CONTINENT = {cc: name for name, codes in CONTINENT_CODES.items() for cc in codes.split()}
assert len(COUNTRY_CONTINENT) == 76

CONTINENT_COLOURS = {
    'North America': '#285B69',
    'South America': '#A25249',
    'Europe': '#4C68CA',
    'Asia': '#4F8336',
    'Africa': '#94712E',
    'Oceania': '#555F69',
}

# Invisible working regions leave separate, padded space for each continent.
# Their borders are not drawn; the final outlines follow convex hulls instead.
REGIONS = {
    'North America': (0., 55., 138., 119.),
    'South America': (0., 0., 138., 51.),
    'Europe': (142., 0., 158., 174.),
    'Asia': (304., 72., 142., 102.),
    'Africa': (304., 0., 92., 68.),
    'Oceania': (400., 0., 46., 68.),
}


def pack_continents(local, pack_country_islands):
    """Pack every country, irregularly, within its continental group."""
    assert set(local) == set(COUNTRY_CONTINENT)
    centres, groups = {}, []
    for name in ['North America', 'Europe', 'Asia', 'Africa', 'South America', 'Oceania']:
        x, y, width, height = REGIONS[name]
        countries = CONTINENT_CODES[name].split()
        subset = {cc: local[cc] for cc in countries}
        placed = None
        for compact in [False, True]:
            for seed in range(20261063, 20261095):
                placed = pack_country_islands(subset, width-8., height-8.,
                                              seed=seed, gap=1.7, compact=compact)
                if placed is not None:
                    break
            if placed is not None:
                break
        if placed is None:
            return None, None
        offset = np.array([x+4., y+4.])
        centres.update({cc: point+offset for cc, point in placed.items()})
        label_y = 179. if name in {'North America', 'Europe', 'Asia'} else -4.
        groups.append(dict(name=name, countries=countries, colour=CONTINENT_COLOURS[name],
                           region_pt=[x,y,width,height], label_x_pt=x+width/2,
                           label_y_pt=label_y, layout_seed=seed))
    return centres, groups


def rounded_enclosure(points, padding=2.5):
    """A convex hull with a round, constant-distance exterior buffer."""
    points = np.asarray(points)
    hull = points[ConvexHull(points).vertices]
    angles = np.linspace(0, 2*np.pi, 64, endpoint=False)
    circle = padding*np.column_stack([np.cos(angles), np.sin(angles)])
    expanded = (hull[:, None, :] + circle[None, :, :]).reshape(-1, 2)
    return expanded[ConvexHull(expanded).vertices]


def draw_continent_enclosures(ax, points, labels, groups):
    """Unfilled dashed contours and direct labels, with no new legend."""
    outlines, membership = [], []
    for group in groups:
        codes = set(group['countries'])
        selected = [r for r in points if r['country'] in codes]
        xy = np.array([[r['x_pt'], r['y_pt']] for r in selected])
        label_corners = np.concatenate([np.asarray(labels[cc]) +
                           np.array([[-7.4,-4.8],[-7.4,7.0],[7.4,-4.8],[7.4,7.0]])
                           for cc in group['countries']], axis=0)
        # Padding comfortably clears both the city markers and country names.
        boundary = rounded_enclosure(np.vstack([xy, label_corners]), padding=2.5)
        if group['name'] in {'South America', 'Africa', 'Oceania'}:
            group['label_y_pt'] = float(boundary[:, 1].min()) - 9.
            group['label_x_pt'] = float((boundary[:, 0].min()+boundary[:, 0].max())/2)
        path = MplPath(np.vstack([boundary, boundary[0]]),
                       [MplPath.MOVETO]+[MplPath.LINETO]*(len(boundary)-1)+[MplPath.CLOSEPOLY])
        outline = PathPatch(path, facecolor='none', edgecolor=group['colour'],
                            linewidth=.85, linestyle=(0,(3.,2.)), capstyle='round',
                            joinstyle='round', zorder=1, clip_on=False)
        outline.set_gid('continent_outline_'+group['name'].lower().replace(' ','_'))
        ax.add_patch(outline)
        # Darken only the direct text, retaining the outline's colour family.
        colour = '#' + ''.join(f'{round(int(group["colour"][i:i+2],16)*.76):02x}' for i in (1,3,5))
        ax.text(group['label_x_pt'], group['label_y_pt'], group['name'],
                fontsize=8.5, fontweight='bold', ha='center', va='center',
                color=colour, zorder=5, clip_on=False)
        group.update(cities=len(selected), countries_n=len(codes),
                     outline_padding_pt=2.5, outline_linewidth_pt=.85,
                     dash_pattern_pt=[3.,2.], outline_vertices=boundary.tolist())
        assert path.contains_points(xy, radius=1e-6).all()
        for index, vertex in enumerate(boundary):
            outlines.append(dict(continent=group['name'], vertex=index,
                                 x_pt=float(vertex[0]), y_pt=float(vertex[1]),
                                 colour=group['colour']))
        membership += [dict(country=cc, continent=group['name']) for cc in group['countries']]
    assert sum(g['cities'] for g in groups) == len(points)
    return groups, outlines, membership
