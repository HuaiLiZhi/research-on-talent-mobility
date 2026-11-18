"""One dot per cleaned domestic destination city, grouped by country.

Organic, unbounded country islands borrow the visual grammar of Murray et al.
(PNAS 2023), Fig.2A. Coordinates are display geometry, not learned embeddings.
Cohort colours encode first positive domestic inflow within the study window.
No observation is sampled or replicated.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
from functools import lru_cache

import duckdb
import numpy as np
from matplotlib.lines import Line2D
from scipy.spatial import cKDTree
from fig2_continents import COUNTRY_CONTINENT, pack_continents, draw_continent_enclosures

COHORTS = ((1998, 1998, '1998', 1998),
           (1999, 2007, '1999–2007', 2007),
           (2008, 2016, '2008–2016', 2016),
           (2017, 2025, '2017–2025', 2025))


def write_csv(path, rows):
    with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
        out = csv.DictWriter(handle, fieldnames=list(rows[0]))
        out.writeheader()
        out.writerows(rows)


def load_cities(canonical, countries, source_out):
    """Use all28 study years and stable destination IDs, one row per city."""
    database = duckdb.connect()
    database.execute("SET threads=4; SET memory_limit='2GB'")
    country_sql = ','.join("'" + cc.replace("'", "''") + "'" for cc in countries)
    path = str(canonical).replace("'", "''")
    rows = database.execute(f"""
        SELECT destination_country country, destination city_id,
               min(year) first_year, max(year) last_year,
               count(DISTINCT year) observed_years, sum(flow) domestic_inflow,
               first(destination_city ORDER BY year, destination_city) city_name
        FROM read_parquet('{path}')
        WHERE origin_country=destination_country AND flow>0
          AND origin<>destination AND year BETWEEN 1998 AND 2025
          AND destination_country IN ({country_sql})
        GROUP BY destination_country,destination
        ORDER BY destination_country,first_year,destination
    """).fetchall()
    database.close()
    records = []
    for cc, city, first, last, years, volume, name in rows:
        cohort = next((label, key) for low, high, label, key in COHORTS if low <= first <= high)
        records.append(dict(country=cc, city_id=city, city_name=name,
                            first_year=first, last_year=last, observed_years=years,
                            total_domestic_inflow=float(volume),
                            first_recorded_period=cohort[0], colour_key=cohort[1]))
    assert len(records) == len({(r['country'], r['city_id']) for r in records})
    assert {r['country'] for r in records} == set(countries)
    assert all(r['total_domestic_inflow'] > 0 and 1998 <= r['first_year'] <= 2025 for r in records)
    # Independently reconcile against the cleaned directional margin table.
    margin = Path(canonical).parent / 'domestic_city_margins.csv'
    first_from_margins = {}
    with margin.open(encoding='utf-8-sig', newline='') as handle:
        for r in csv.DictReader(handle):
            if r['side'] != 'inflow' or r['country'] not in countries or float(r['flow']) <= 0:
                continue
            key = (r['country'], r['city_id'])
            first_from_margins[key] = min(int(r['year']), first_from_margins.get(key, 9999))
    assert first_from_margins == {(r['country'], r['city_id']): r['first_year'] for r in records}
    summary = []
    for cc in countries:
        rr = [r for r in records if r['country'] == cc]
        row = dict(country=cc, unique_domestic_inflow_cities=len(rr))
        row.update({f'first_{key}': sum(r['colour_key'] == key for r in rr) for _, _, _, key in COHORTS})
        summary.append(row)
    write_csv(Path(source_out) / 'Fig2_city_first_inflow_cohorts.csv', records)
    write_csv(Path(source_out) / 'Fig2_city_entry_country_summary.csv', summary)
    return records, summary


@lru_cache(maxsize=100)
def organic_unit_points(count, country):
    """Relaxed random display slots in an irregular, unbounded island.

    Rank display slots by an angular envelope to get exactly the required count.
    Slot selection never filters city records. Country-specific reproducible
    jitter and asymmetry break the former hexagonal/concentric visual pattern.
    """
    seed = int(hashlib.sha256(country.encode()).hexdigest()[:12], 16)
    rng = np.random.default_rng(seed)
    radius = max(8., math.sqrt(count / 2.0) + 10.)
    bound = int(math.ceil(radius / (math.sqrt(3) / 2))) + 4
    indices = np.arange(-bound, bound + 1)
    q, row = np.meshgrid(indices, indices)
    x = q.ravel() + (row.ravel() % 2) * .5
    y = math.sqrt(3) / 2 * row.ravel()
    x += rng.uniform(-.42, .42, len(x))
    y += rng.uniform(-.42, .42, len(y))
    angles = np.arctan2(y, x)
    phase = rng.uniform(0, 2 * math.pi)
    # Organic lobes vary by country; the boundary is never drawn.
    envelope = 1 + .10 * np.sin(3 * angles + phase) + .06 * np.cos(5 * angles - phase)
    score = np.hypot(x, y) / envelope
    order = np.argsort(score, kind='stable')
    assert len(order) >= count
    xy = np.column_stack((x[order[:count]], y[order[:count]]))
    theta = rng.uniform(0, math.pi)
    rotation = np.array([[math.cos(theta), -math.sin(theta)],
                         [math.sin(theta), math.cos(theta)]])
    xy = xy @ rotation.T
    # Repel only colliding display slots, preserving the uneven scatter while
    # ensuring individual city dots do not occlude each other.
    for _ in range(120):
        pairs = np.asarray(list(cKDTree(xy).query_pairs(.75)), dtype=int)
        if not len(pairs):
            break
        delta = xy[pairs[:, 1]] - xy[pairs[:, 0]]
        distance = np.linalg.norm(delta, axis=1)
        push = delta / distance[:, None] * ((.751 - distance) * .52)[:, None]
        step = np.zeros_like(xy)
        np.add.at(step, pairs[:, 0], -push)
        np.add.at(step, pairs[:, 1], push)
        xy += step
    if count > 1:
        assert cKDTree(xy).query(xy, k=2)[0][:, 1].min() > .735
    # Follow the same irregular envelope used to create the point island.
    # Increasing normalized radius gives increasing proximity to its edge.
    angle = np.arctan2(xy[:, 1], xy[:, 0]) - theta
    boundary = 1 + .10*np.sin(3*angle+phase) + .06*np.cos(5*angle-phase)
    radial = np.linalg.norm(xy, axis=1) / boundary
    radial /= max(float(radial.max()), 1e-9)
    order = np.argsort(radial, kind='stable')
    return xy[order], radial[order]


def organic_points(count, spacing, country):
    """Scale the city slots and reserve an exterior country-label footprint."""
    xy = organic_unit_points(count, country)[0].copy() * spacing
    label = np.array([(xy[:, 0].min() + xy[:, 0].max()) / 2,
                      xy[:, 1].min() - 8.5])
    xmin, xmax = min(xy[:, 0].min(), label[0] - 7.4), max(xy[:, 0].max(), label[0] + 7.4)
    ymin, ymax = label[1] - 4.8, xy[:, 1].max()
    centre = np.array([(xmin + xmax) / 2, (ymin + ymax) / 2])
    xy -= centre
    label -= centre
    label_corners = label + np.array([[-7.4, -4.8], [-7.4, 7.0], [7.4, -4.8], [7.4, 7.0]])
    outer = max(float(np.linalg.norm(xy, axis=1).max()) + spacing * .4,
                float(np.linalg.norm(label_corners, axis=1).max()))
    return xy, max(outer, 8.3), label


def circle_intersections(a, ra, b, rb):
    delta = np.asarray(b) - np.asarray(a)
    distance = float(np.linalg.norm(delta))
    if distance < 1e-9 or distance > ra + rb or distance < abs(ra - rb):
        return []
    along = (ra * ra - rb * rb + distance * distance) / (2 * distance)
    height = math.sqrt(max(0., ra * ra - along * along))
    middle = np.asarray(a) + along * delta / distance
    perp = np.array([-delta[1], delta[0]]) / distance
    return [middle + height * perp, middle - height * perp]


def pack_country_circles(radii, width, height, gap=1.7):
    """Tangent candidate placement within a wide rectangle, largest first."""
    countries = sorted(radii, key=lambda cc: (-radii[cc], cc))
    placed = {}
    centers, previous_radii = [], []
    for index, cc in enumerate(countries):
        radius = radii[cc]
        if radius * 2 > min(width, height):
            return None
        if index == 0:
            # Keep the largest country left of centre, giving the smaller
            # countries an uninterrupted field on the right.
            center = np.array([max(radius, width * .22), height * .5])
        else:
            candidates = [np.array([x, y]) for x in [radius, width - radius]
                          for y in [radius, height - radius]]
            for i, (old, old_radius) in enumerate(zip(centers, previous_radii)):
                distance = radius + old_radius + gap
                for j in range(i):
                    candidates.extend(circle_intersections(old, distance, centers[j],
                                      radius + previous_radii[j] + gap))
                for x in [radius, width - radius]:
                    side = distance * distance - (x - old[0]) ** 2
                    if side >= 0:
                        candidates.extend([np.array([x, old[1] + math.sqrt(side)]),
                                           np.array([x, old[1] - math.sqrt(side)])])
                for y in [radius, height - radius]:
                    side = distance * distance - (y - old[1]) ** 2
                    if side >= 0:
                        candidates.extend([np.array([old[0] + math.sqrt(side), y]),
                                           np.array([old[0] - math.sqrt(side), y])])
            points = np.asarray(candidates)
            inside = ((points[:, 0] >= radius - 1e-6) & (points[:, 0] <= width - radius + 1e-6)
                      & (points[:, 1] >= radius - 1e-6) & (points[:, 1] <= height - radius + 1e-6))
            points = points[inside]
            if not len(points):
                return None
            distances = ((points[:, None, :] - np.asarray(centers)[None, :, :]) ** 2).sum(axis=2)
            required = (radius + np.asarray(previous_radii) + gap - .001) ** 2
            points = points[np.all(distances >= required[None, :], axis=1)]
            if not len(points):
                return None
            # Compact left-to-right packing; symmetrical score avoids making
            # the cloud appear to encode a geographical or quantitative axis.
            score = points[:, 0] + .09 * np.abs(points[:, 1] - height * .5)
            center = points[int(np.argmin(score))]
        placed[cc] = center
        centers.append(center)
        previous_radii.append(radius)
    return placed


def pack_country_islands(local, width, height, gap=3.0, seed=20261027, compact=False):
    """Pack point-and-label footprints, without drawing their rectangles.

    Reproducible random anchors scatter countries throughout the panel. Maximal
    free rectangles enforce clearance, without aligned rows or a spatial size
    ranking. These invisible footprints include each point island and label.
    """
    bounds = {}
    for cc, (xy, _, label) in local.items():
        bounds[cc] = (min(xy[:, 0].min() - .5, label[0] - 7.4) - gap/2,
                      label[1] - 4.8 - gap/2,
                      max(xy[:, 0].max() + .5, label[0] + 7.4) + gap/2,
                      xy[:, 1].max() + .5 + gap/2)
    free = [(0., 0., width, height)]
    placed = {}
    ordered = sorted(local, key=lambda cc: (-(bounds[cc][2]-bounds[cc][0])
                                             * (bounds[cc][3]-bounds[cc][1]), cc))
    for index, cc in enumerate(ordered):
        left, bottom, right, top = bounds[cc]
        w, h = right-left, top-bottom
        rng = np.random.default_rng(int(hashlib.sha256(f'{seed}:{cc}'.encode()).hexdigest()[:12], 16))
        anchor = rng.uniform([0, 0], [width, height])
        candidates = []
        for fx, fy, fw, fh in free:
            if w <= fw + 1e-7 and h <= fh + 1e-7:
                if compact:
                    x = fx if anchor[0] < width/2 else fx+fw-w
                    y = fy if anchor[1] < height/2 else fy+fh-h
                    score = (min(fw-w, fh-h), max(fw-w, fh-h),
                             (x+w/2-anchor[0])**2 + (y+h/2-anchor[1])**2)
                else:
                    x = float(np.clip(anchor[0]-w/2, fx, fx+fw-w))
                    y = float(np.clip(anchor[1]-h/2, fy, fy+fh-h))
                    score = ((x+w/2-anchor[0])**2 + (y+h/2-anchor[1])**2,
                             min(fw-w, fh-h), fw*fh-w*h)
                candidates.append((score, x, y))
        if not candidates:
            return None
        _, x, y = min(candidates)
        placed[cc] = np.array([x-left, y-bottom])
        new = []
        for fx, fy, fw, fh in free:
            fr, ft = fx+fw, fy+fh
            if x >= fr-1e-7 or x+w <= fx+1e-7 or y >= ft-1e-7 or y+h <= fy+1e-7:
                new.append((fx, fy, fw, fh));continue
            if x > fx+1e-7: new.append((fx, fy, x-fx, fh))
            if x+w < fr-1e-7: new.append((x+w, fy, fr-x-w, fh))
            if y > fy+1e-7: new.append((fx, fy, fw, y-fy))
            if y+h < ft-1e-7: new.append((fx, y+h, fw, ft-y-h))
        free = []
        for i, box in enumerate(new):
            bx, by, bw, bh = box
            if any(i != j and bx >= ox-1e-7 and by >= oy-1e-7
                   and bx+bw <= ox+ow+1e-7 and by+bh <= oy+oh+1e-7
                   and (box != other or i > j)
                   for j, other in enumerate(new) for ox, oy, ow, oh in [other]):
                continue
            free.append(box)
    return placed


def layout_cities(records, width=446., height=174.):
    grouped = {}
    for r in records:
        grouped.setdefault(r['country'], []).append(r)
    for cc in grouped:
        grouped[cc].sort(key=lambda r: (r['first_year'], r['city_id']))
    # The spacing adapts only display geometry, never city counts or records.
    for spacing in np.arange(1.70, 1.04, -.025):
        local = {cc: organic_points(len(rr), float(spacing), cc) for cc, rr in grouped.items()}
        radii = {cc: geometry[1] for cc, geometry in local.items()}
        centers, continents = pack_continents(local, pack_country_islands)
        if centers is not None:
            break
    else:
        raise RuntimeError('All cities and country labels cannot fit the preserved panel dimensions.')
    # Continental group regions already balance the full preserved canvas.
    extent = [min(centers[cc][0] + min(local[cc][0][:, 0].min(), local[cc][2][0]-7.4) for cc in centers),
              max(centers[cc][0] + max(local[cc][0][:, 0].max(), local[cc][2][0]+7.4) for cc in centers),
              min(centers[cc][1] + local[cc][2][1]-4.8 for cc in centers),
              max(centers[cc][1] + local[cc][0][:, 1].max() for cc in centers)]
    shift = np.zeros(2)
    placed, labels = [], {}
    for cc, rr in grouped.items():
        center = centers[cc] + shift
        centers[cc] = center
        xy = local[cc][0] + center
        labels[cc] = local[cc][2] + center
        radial = organic_unit_points(len(rr), cc)[1]
        for rank, (row, point, distance) in enumerate(zip(rr, xy, radial)):
            placed.append(dict(row, x_pt=float(point[0]), y_pt=float(point[1]),
                               radial_rank=rank, normalized_radial_distance=float(distance),
                               continent=COUNTRY_CONTINENT[cc]))
    xy = np.array([[r['x_pt'], r['y_pt']] for r in placed])
    distances = cKDTree(xy).query(xy, k=2)[0][:, 1]
    assert float(distances.min()) >= float(spacing) * .73
    assert len(placed) == len(records)
    return placed, labels, radii, dict(spacing_pt=float(spacing),
            marker_diameter_pt=float(spacing) * .70, country_gap_pt=1.7,
            minimum_dot_distance_pt=float(distances.min()),
            display_extent_pt=extent, point_count=len(placed), country_count=len(grouped),
            placement='Countries form six continental groups with coloured dashed enclosures and direct labels; country islands remain irregular and chronological centre-to-edge city ordering is preserved',
            layout_seed=20261063, continents=continents,
            chronological_layout='Ascending observed first_year assigned to ascending envelope-normalized radial distance',
            reference_style='Murray et al. PNAS2023, doi:10.1073/pnas.2305414120, Fig.2A; visual grammar only',
            country_label_location='Outside each point island, below its lower edge',
            legend_labels=['1998', '2007', '2016', '2025'])


def draw_city_clusters(ax, canonical, countries, source_out, qa, year_colors):
    records, summary = load_cities(canonical, countries, source_out)
    placed, centers, radii, geometry = layout_cities(records)
    ax.set_xlim(0, 446)
    ax.set_ylim(-3, 197)
    ax.set_aspect('equal', adjustable='box')
    ax.set_axis_off()
    groups, outlines, membership = draw_continent_enclosures(ax, placed, centers, geometry['continents'])
    geometry['continents'] = groups
    write_csv(Path(source_out) / 'Fig2_city_continent_membership.csv', membership)
    write_csv(Path(source_out) / 'Fig2_city_continent_outlines.csv', outlines)
    # Deepen only the city-point colours, preserving the established hue families.
    # Upper-row year curves and continent outlines retain their existing colours.
    point_colors = {key: '#' + ''.join(f'{round(int(colour[i:i+2],16)*.82):02X}'
                       for i in (1,3,5)) for key, colour in year_colors.items()}
    for _, _, label, key in COHORTS:
        rr = [r for r in placed if r['colour_key'] == key]
        dots = ax.scatter([r['x_pt'] for r in rr], [r['y_pt'] for r in rr],
                   s=geometry['marker_diameter_pt'] ** 2, color=point_colors[key],
                   linewidths=0, edgecolors='none', alpha=1., zorder=3)
        dots.set_gid(f'city_cohort_{key}')
    country_labels = []
    for cc in sorted(centers):
        x, y = centers[cc]
        ax.text(x, y, cc, fontsize=8., color='black', ha='center', va='center', zorder=4)
        country_labels.append(dict(country=cc, x_pt=float(x), y_pt=float(y),
                                   font_size_pt=8., radius_pt=radii[cc], continent=COUNTRY_CONTINENT[cc]))
    ax.text(0, 191., 'First recorded domestic inflow', fontsize=8.5,
            color='black', ha='left', va='center')
    legend = ax.legend(handles=[Line2D([], [], linestyle='none', marker='o', markersize=3.5,
                        markeredgewidth=0, color=point_colors[key], label=str(key))
                        for _, _, label, key in COHORTS],
              loc='upper right', bbox_to_anchor=(1.015, 1.005), ncol=4,
              frameon=False, fontsize=8., columnspacing=.9, handletextpad=.35,
              handlelength=.6, borderaxespad=0)
    legend.set_in_layout(False)
    write_csv(Path(source_out) / 'Fig2_city_entry_points_plotted.csv', placed)
    write_csv(Path(source_out) / 'Fig2_city_cluster_labels.csv', country_labels)
    geometry.update(cohorts=[dict(label=str(key), first_recorded_period=label, colour_key=key, colour=point_colors[key],
                                 cities=sum(r['colour_key'] == key for r in records))
                            for _, _, label, key in COHORTS],
                    scope='Union of positive domestic destination cities across all28 years in the fixed76-country cohort',
                    one_point_per='(country, cleaned destination city ID)',
                    all_cities_retained=True, no_city_repeated=True,
                    first_recorded_year='Earliest positive domestic inflow during1998-2025; not an assumed real onset',
                    labels=country_labels, point_colours=point_colors,
                    point_alpha=1., colour_darkening_factor=.82)
    (Path(qa) / 'city_entry_geometry.json').write_text(json.dumps(geometry, ensure_ascii=False, indent=2), encoding='utf-8')
    return geometry
