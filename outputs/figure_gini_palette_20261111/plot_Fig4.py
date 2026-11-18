"""Render domestic mobility expansion and T-group Gini comparisons.

Current data tables supply annual flows, Gini values and country memberships.
Supporting comparison and coverage functions are also used by other figures.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'figures/v3'),
                str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa')]
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, FuncFormatter, NullLocator
import numpy as np
import pymupdf
from audit_panel_alignment import require_matplotlib_panel_alignment
from figure_style import (
    ANNUAL_LINEWIDTH_PT, ANNUAL_MARKER_EDGE_PT, ANNUAL_MARKER_PT, AXIS_LINEWIDTH_PT,
    DISTRIBUTION_POINT_PT2,
    REFERENCE_COLOUR, REFERENCE_LINESTYLE, REFERENCE_LINEWIDTH_PT,
    TICK_LINEWIDTH_PT, apply_light_grids, apply_nhb_typography,
)
from figure_palette import BLUE, RED, GREEN, GRAY

OUT = ROOT / 'outputs/figure_gini_palette_20261111'
SOURCE = ROOT / 'outputs/fig2_split_20261102/before/source_data'
ARTWORK = OUT / 'artwork'
ENTRY_ANNUAL = ROOT / 'outputs/paper_final/source_data/results_revision_20261111/entry_components_annual.csv'
QA = OUT / 'QA/Fig4'
GINI_SLOPES = OUT / 'source_data/Fig4c_country_gini_slopes.csv'
GROUP_SUMMARY = OUT / 'source_data/Fig4c_T_group_summary.csv'
WIDTH_MM = 180.0
HEIGHT_PT = 160.0
GROUP_MEDIAN_MARKER_PT = 5.6
RASTER_DPI = 600
YEAR_COLOURS = {1998: '#7E99F4', 2007: '#CC7C71',
                2016: '#7AB656', 2025: '#C9A45C'}
GROUP_COLOURS = {1: BLUE, 2: GRAY, 3: GREEN, 4: RED}
EXPORT_SUFFIXES = ('.pdf', '.svg', '.png')


def read_csv(name):
    with (SOURCE / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def configure():
    mpl.rcParams.update({
        'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica'],
        'font.size': 9, 'axes.labelsize': 9, 'xtick.labelsize': 8,
        'ytick.labelsize': 8, 'legend.fontsize': 7.6,
        'axes.spines.right': False, 'axes.spines.top': False,
        'axes.linewidth': AXIS_LINEWIDTH_PT, 'axes.unicode_minus': False,
        'axes.labelcolor': '#111111', 'text.color': '#111111',
        'xtick.color': '#111111', 'ytick.color': '#111111',
        'svg.fonttype': 'none', 'pdf.fonttype': 42,
        'savefig.facecolor': 'white', 'legend.frameon': False,
        'path.simplify': False,
    })


def axes_layout():
    width_pt = WIDTH_MM / 25.4 * 72
    fig = plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_PT / 72))
    layout = {'a': (45., 32., 125., 101.),
              'b': (211., 32., 125., 101.),
              'c': (377., 32., 125., 101.)}
    axes = []
    for panel, (left, bottom, width, height) in layout.items():
        ax = fig.add_axes([left / width_pt, bottom / HEIGHT_PT,
                           width / width_pt, height / HEIGHT_PT])
        ax.set_gid(panel)
        ax.text(-14 / width, 1 + 8 / height, panel, transform=ax.transAxes,
                fontsize=10, fontweight='bold', va='bottom', ha='left')
        ax.tick_params(length=2.4, width=TICK_LINEWIDTH_PT, pad=2.5)
        ax.set_axisbelow(True)
        axes.append(ax)
    return fig, axes


def grid(ax, *, logarithmic=False):
    ax.grid(True, which='major', color='#E6E9ED', linewidth=.45)
    if not logarithmic:
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax.grid(True, which='minor', color='#E6E9ED', linewidth=.45)
    ax.tick_params(which='minor', length=0)


def draw_volume(ax, geography, rows):
    data = sorted([r for r in rows if r['geography'] == geography],
                  key=lambda r: int(r['year']))
    years = np.array([int(r['year']) for r in data])
    assert years.tolist() == list(range(1998, 2026))
    observed = np.array([float(r['observed_events']) for r in data]) / 1000
    reference = np.array([float(r['reference_events']) for r in data]) / 1000
    for values, colour, label, zorder in [
            (reference, BLUE, 'Predicted', 2), (observed, RED, 'Observed', 3)]:
        ax.plot(years, values, color=colour, linewidth=ANNUAL_LINEWIDTH_PT,
                marker='o', markersize=ANNUAL_MARKER_PT, markeredgecolor='white',
                markeredgewidth=ANNUAL_MARKER_EDGE_PT, clip_on=False, label=label, zorder=zorder)
    ax.set_xlim(1998, 2025)
    ax.set_xticks([1998, 2012, 2025])
    ax.set_ylim(0, 1100 if geography == 'international' else 1900)
    ax.set_yticks([0, 250, 500, 750, 1000] if geography == 'international'
                 else [0, 500, 1000, 1500])
    ax.set_xlabel('Year', labelpad=4)
    label = ('International Mobility\nEvents (Thousands)' if geography == 'international'
             else 'Domestic Intercity Mobility\nEvents (Thousands)')
    ax.set_ylabel(label, labelpad=2)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc='upper left',
              handlelength=1.2, handletextpad=.4, labelspacing=.35, borderaxespad=.45)
    grid(ax)
    return {'annual_observations_per_series': len(years),
            'observed_events': (observed * 1000).tolist(),
            'reference_events': (reference * 1000).tolist()}


def draw_reach(ax, geography, rows):
    original_panel = 'b' if geography == 'international' else 'd'
    data = [r for r in rows if r['panel'] == original_panel]
    report = []
    for year, colour in YEAR_COLOURS.items():
        values = [r for r in data if int(r['year']) == year]
        x = np.array([float(r['source_locations_threshold']) for r in values])
        y = np.array([float(r['percentage']) for r in values])
        assert np.all(x > 0), 'Source-count thresholds on a log axis must be positive.'
        assert np.all(np.diff(x) > 0)
        assert np.all(np.diff(y) <= 1e-8)
        assert y.min() >= -1e-8 and y.max() <= 100 + 1e-8
        ax.plot(x, y, color=colour, linewidth=1.1,
                linestyle='-', label=str(year), solid_capstyle='round',
                solid_joinstyle='round')
        report.append({'year': year, 'vertices': len(values),
                       'all_original_vertices_retained': True})
    ax.set_xscale('log')
    ax.set_xlim(1, max(float(r['source_locations_threshold']) for r in data) * 1.04)
    ax.set_ylim(0, 100)
    ax.set_xticks([1, 10, 100])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f'{int(round(value)):,}'))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.set_yticks([0, 50, 100])
    ax.set_xlabel('Source countries' if geography == 'international' else 'Source cities',
                  labelpad=4)
    ax.set_title('Countries (%)' if geography == 'international' else 'Cities (%)',
                 loc='left', fontsize=8.5, fontweight='normal', pad=9)
    ax.legend(loc='lower left' if geography == 'international' else 'upper right',
              handlelength=1.1, handletextpad=.4, labelspacing=.3, borderaxespad=.35)
    grid(ax, logarithmic=True)
    return report


def draw_comparison(ax, metric='Gini'):
    """All 26 annual values, normalized within each source to 1998=100."""
    with (OUT / 'source_data/annual_comparison.csv').open(
            encoding='utf-8-sig', newline='') as stream:
        all_rows = list(csv.DictReader(stream))
    assert metric in ['HHI', 'Gini'] and len(all_rows) == 104
    curves = []
    styles = [('BRIDGE', 'BRIDGE', RED, 2.0, 4.5),
              ('Yenilmez2026', 'Scopus', BLUE, 1.05, 3.2)]
    for source, label, color, linewidth, markersize in styles:
        rows = sorted([r for r in all_rows if r['metric'] == metric and r['source'] == source],
                      key=lambda r: int(r['year']))
        years = np.array([int(r['year']) for r in rows])
        raw = np.array([float(r['raw_value']) for r in rows])
        values = np.array([float(r['index_1998_100']) for r in rows])
        assert years.tolist() == list(range(1998, 2024))
        assert all(int(r['countries']) == 147 for r in rows)
        assert np.all(raw > 0) and np.allclose(values, 100 * raw / raw[0])
        assert values[0] == 100
        ax.plot(years, values, color=color, lw=linewidth, ls='-',
                marker='o', markersize=markersize, markerfacecolor=color,
                markeredgecolor='white', markeredgewidth=.35, label=label, zorder=3)
        curves.append({'source': source, 'metric': metric, 'years': years.tolist(),
                       'raw_values': raw.tolist(), 'indexed_values': values.tolist(),
                       'endpoint_decline_percent': float(100 - values[-1])})
    ax.set_xlim(1997.3, 2023.7)
    ax.set_xticks([1998, 2010, 2023])
    ax.set_ylim((55, 105) if metric == 'HHI' else (90, 102))
    ax.set_yticks([60, 80, 100] if metric == 'HHI' else [92, 96, 100])
    ax.set_xlabel('Year', labelpad=4)
    ax.set_ylabel(f'Indexed {metric}', labelpad=3)
    ax.legend(loc='lower left', borderaxespad=.3, fontsize=7,
              handlelength=1.6, handletextpad=.5, labelspacing=.4)
    return {'countries': 147, 'years': [1998, 2023], 'metric': metric,
            'curves': curves, 'comparison_doi': '10.1007/s41109-026-00840-0',
            'definition': '100 * index_year / source_specific_index_1998',
            'matched_pool': 'Same 147 annually positive countries; full international margins renormalized within the common pool',
            'no_interpolation_or_smoothing': True,
            'colours': {'BRIDGE': RED, 'Yenilmez2026': BLUE},
            'uncertainty': 'Descriptive annual indices; no uncertainty interval'}


def draw_domestic_gini(ax, rows):
    """Compare annual domestic city Gini with and without newly recorded cities."""
    years = np.arange(1998, 2026)
    countries = {r['country'] for r in rows}
    assert len(countries) == 76
    by_year = {year: [r for r in rows if int(r['year']) == year] for year in years}
    assert sum(map(len, by_year.values())) == len(rows)
    assert all(len(group) == len(countries) and {r['country'] for r in group} == countries
               for group in by_year.values())
    assert all(float(r['Gini_All']) == float(r['Gini_CI']) for r in by_year[years[0]])

    curves = {}
    for key, label, colour, zorder in [('Gini_CI', 'Initial Cities', BLUE, 2),
                                        ('Gini_All', 'All Cities', RED, 3)]:
        values = np.array([np.median([float(r[key]) for r in by_year[year]]) for year in years])
        assert np.all((values >= .55) & (values <= .78))
        ax.plot(years, values, color=colour, linewidth=ANNUAL_LINEWIDTH_PT,
                marker='o', markersize=ANNUAL_MARKER_PT, markeredgecolor='white',
                markeredgewidth=ANNUAL_MARKER_EDGE_PT, label=label, zorder=zorder,
                clip_on=False)
        curves[key] = values.tolist()

    ax.set(xlim=(1998, 2025), ylim=(.55, .78))
    ax.set_xticks([1998, 2012, 2025])
    ax.set_yticks([.55, .60, .65, .70, .75])
    ax.set_xlabel('Year', labelpad=4)
    ax.set_ylabel('Domestic City Gini', labelpad=4)
    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc='lower right',
              handlelength=1.2, handletextpad=.4, labelspacing=.35, borderaxespad=.45)
    grid(ax)
    return dict(countries=len(countries), years=years.tolist(), annual_medians=curves,
                source_data=ENTRY_ANNUAL.relative_to(ROOT).as_posix())


def draw_gini_comparison(ax, annual):
    """Compare full-period Gini slopes using the two city sets in panel b."""
    years = np.arange(1998, 2026, dtype=float)
    centered_years = years - years.mean()
    denominator = np.dot(centered_years, centered_years)
    with (OUT / 'source_data/trajectory_membership.csv').open(
            encoding='utf-8-sig', newline='') as stream:
        membership = {r['country']: r for r in csv.DictReader(stream)}
    assert {r['country'] for r in annual} == set(membership)

    points = []
    for country in sorted(membership):
        observations = sorted([r for r in annual if r['country'] == country],
                              key=lambda r: int(r['year']))
        assert [int(r['year']) for r in observations] == years.tolist()
        values = np.array([[float(r['Gini_CI']), float(r['Gini_All'])] for r in observations])
        initial_slope, all_slope = 100 * centered_years @ values / denominator
        points.append(dict(country=country, group=int(membership[country]['group']),
                           initial_gini_slope_pp_year=float(initial_slope),
                           all_gini_slope_pp_year=float(all_slope),
                           above_equality=int(all_slope > initial_slope),
                           decline_to_rise=int(initial_slope < 0 < all_slope)))

    for point in points:
        point['slope_difference_pp_year'] = (point['all_gini_slope_pp_year']
                                             - point['initial_gini_slope_pp_year'])
    difference = np.array([r['slope_difference_pp_year'] for r in points])
    median = float(np.median(difference))
    higher = int(np.count_nonzero(difference > 0))
    reversal = sum(r['decline_to_rise'] for r in points)
    group_counts = {f'T{group}': sum(r['group'] == group for r in points)
                    for group in GROUP_COLOURS}
    assert list(group_counts.values()) == [15, 14, 24, 23]

    ax.set(xlim=(-.65, 2.0), ylim=(-.55, 3.55))
    ax.set_xticks([-.5, 0, .5, 1, 1.5, 2])
    ax.set_yticks([3, 2, 1, 0], ['T1', 'T2', 'T3', 'T4'])
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_locator(NullLocator())
    ax.tick_params(axis='y', length=0)
    ax.axvline(0, color=REFERENCE_COLOUR, lw=REFERENCE_LINEWIDTH_PT,
               linestyle=REFERENCE_LINESTYLE, zorder=1)

    height_pt = ax.get_position().height * ax.figure.get_figheight() * 72
    group_summaries = []
    for group in range(1, 5):
        members = [r for r in points if r['group'] == group]
        level = 4 - group
        up = sum(r['above_equality'] for r in members)
        summary = dict(group=f'T{group}', countries=len(members), higher_slopes=up,
                       shift_up_fraction=up / len(members),
                       median_difference_pp_year=float(np.median(
                           [r['slope_difference_pp_year'] for r in members])))
        # The small categorical offsets preserve all measured Gini slopes.
        jitter = ((np.arange(len(members)) * .6180339887498949) % 1 - .5) * .08
        for key, colour, dodge, prefix, label in [
                ('initial_gini_slope_pp_year', BLUE, .26, 'initial', 'Initial Cities'),
                ('all_gini_slope_pp_year', RED, -.26, 'all', 'All Cities')]:
            values = np.array([r[key] for r in members])
            q1, med, q3 = np.quantile(values, [.25, .5, .75])
            y = level + dodge + jitter
            for point, offset in zip(members, jitter):
                point[f'{prefix}_display_offset_pt'] = float(offset * height_pt / 4.1)
            ax.scatter(values, y, s=DISTRIBUTION_POINT_PT2, color=colour,
                       alpha=.35, edgecolors='white', linewidths=.2, zorder=2)
            ax.hlines(level+dodge, q1, q3, color=colour, linewidth=1.3, zorder=3)
            ax.scatter([med], [level+dodge], s=GROUP_MEDIAN_MARKER_PT**2,
                       marker='D', color=colour, edgecolors='white', linewidths=.5,
                       label=label if group == 1 else None, zorder=4)
            summary[f'{prefix}_median_pp_year'] = float(med)
            summary[f'{prefix}_q1_pp_year'] = float(q1)
            summary[f'{prefix}_q3_pp_year'] = float(q3)
        group_summaries.append(summary)

    handles, labels = ax.get_legend_handles_labels()
    ax.legend(handles[::-1], labels[::-1], loc='upper right',
              fontsize=7, handlelength=.7, handletextpad=.4,
              labelspacing=.3, borderaxespad=.45)
    ax.set_xlabel('Gini Slope (pp/year)', labelpad=4)

    with GROUP_SUMMARY.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(group_summaries[0]))
        writer.writeheader()
        writer.writerows(group_summaries)

    with GINI_SLOPES.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(points[0]))
        writer.writeheader()
        writer.writerows(points)
    return dict(countries=len(points), country_points=points, groups=group_counts,
                higher_slopes=higher, decline_to_rise=reversal, median_difference_pp_year=median,
                x_definition='Gini slope, on a linear scale',
                y_definition='T1–T4 groups with bounded categorical dot offsets',
                group_summaries=group_summaries, x_scale='linear',
                summary_intervals='25th–75th percentiles across countries within each group',
                summary_data=GROUP_SUMMARY.relative_to(ROOT).as_posix(),
                slope_method='OLS with intercept on 28 annual observations, multiplied by 100',
                source_data=ENTRY_ANNUAL.relative_to(ROOT).as_posix(),
                plotted_data=GINI_SLOPES.relative_to(ROOT).as_posix())


def main():
    ARTWORK.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    configure()
    volume = read_csv('Fig2_growth_reference.csv')
    with ENTRY_ANNUAL.open(encoding='utf-8-sig', newline='') as stream:
        annual = list(csv.DictReader(stream))
    assert len(volume) == 56 and len(annual) == 76 * 28
    reports = []
    for number, geography in [(4, 'domestic')]:
        fig, axes = axes_layout()
        report = {'figure': number, 'geography': geography,
                  'width_mm': WIDTH_MM, 'height_mm': HEIGHT_PT / 72 * 25.4,
                  'volume': draw_volume(axes[0], geography, volume),
                  'gini': draw_domestic_gini(axes[1], annual),
                  'country_comparison': draw_gini_comparison(axes[2], annual)}
        apply_nhb_typography(fig)
        fig.canvas.draw()
        apply_light_grids(fig, json_out=QA / f'Fig{number}.grids.json')
        alignment = require_matplotlib_panel_alignment(
            fig, json_out=QA / f'Fig{number}.alignment.json',
            overlay_svg=QA / f'Fig{number}.alignment.svg',
            row_groups=[['a', 'b', 'c']], column_groups=[],
            tolerance_pt=1.5, gutter_tolerance_pt=1.5,
            require_panel_labels=True, strict=True)
        report['alignment_verdict'] = alignment.get('verdict')
        for suffix in EXPORT_SUFFIXES:
            options = {'dpi': RASTER_DPI} if suffix == '.png' else {}
            fig.savefig(ARTWORK / f'Fig{number}{suffix}', **options)
        with pymupdf.open(ARTWORK / f'Fig{number}.pdf') as document:
            document[0].get_pixmap(matrix=pymupdf.Matrix(2.6, 2.6), alpha=False).save(QA / 'preview.png')
        plt.close(fig)
        reports.append(report)
    (OUT / 'render_report.json').write_text(
        json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    (QA / 'figure_manifest.json').write_text(json.dumps({
        'figure': 'Fig4', 'panels': reports,
        'new_panel_source_sha256': hashlib.sha256(ENTRY_ANNUAL.read_bytes()).hexdigest()
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'figures': [4], 'outputs': str(ARTWORK),
                      'country_comparisons': 76}, ensure_ascii=False))


if __name__ == '__main__':
    main()
