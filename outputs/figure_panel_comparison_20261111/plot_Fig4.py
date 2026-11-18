"""Lay out the existing international and domestic expansion panels separately.

All quantitative marks and fitted curves come from the frozen current source
tables. No observations are discarded and no statistical model is refitted.
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
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator, FuncFormatter, MaxNLocator, NullLocator
import numpy as np
import pymupdf
from audit_panel_alignment import require_matplotlib_panel_alignment
from figure_style import apply_light_grids,apply_nhb_typography

OUT = ROOT / 'outputs/figure_panel_comparison_20261111'
SOURCE = ROOT / 'outputs/fig2_split_20261102/before/source_data'
ARTWORK = OUT / 'artwork'
QA = OUT / 'QA/Fig4'
WIDTH_MM = 180.0
HEIGHT_PT = 160.0
RASTER_DPI = 600
YEAR_COLOURS = {1998: '#7E99F4', 2007: '#CC7C71',
                2016: '#7AB656', 2025: '#C9A45C'}
GROUP_COLOURS = {1: '#7E99F4', 2: '#A5AEB7', 3: '#7AB656', 4: '#CC7C71'}
RED, BLUE = '#CC7C71', '#7E99F4'
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
        'axes.linewidth': .6, 'axes.unicode_minus': False,
        'axes.labelcolor': '#111111', 'text.color': '#111111',
        'xtick.color': '#111111', 'ytick.color': '#111111',
        'svg.fonttype': 'none', 'pdf.fonttype': 42,
        'savefig.facecolor': 'white', 'legend.frameon': False,
        'path.simplify': False,
    })


def axes_row():
    width_pt = WIDTH_MM / 25.4 * 72
    fig = plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_PT / 72))
    axes = []
    for panel, x in zip('abc', [45., 211., 377.]):
        ax = fig.add_axes([x / width_pt, 32 / HEIGHT_PT,
                           125 / width_pt, 101 / HEIGHT_PT])
        ax.set_gid(panel)
        ax.text(-14 / 125, 1 + 8 / 101, panel, transform=ax.transAxes,
                fontsize=10, fontweight='bold', va='bottom', ha='left')
        ax.tick_params(length=2.4, width=.55, pad=2.5)
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
    for values, colour, linewidth, label, zorder in [
            (reference, BLUE, 1.05, 'Predicted', 2),
            (observed, RED, 2.0, 'Observed', 3)]:
        ax.plot(years, values, color=colour, linewidth=linewidth,
                marker='o', markersize=4.5, markeredgecolor='white',
                markeredgewidth=.35, clip_on=False, label=label, zorder=zorder)
    ax.set_xlim(1998, 2025)
    ax.set_xticks([1998, 2012, 2025])
    ax.set_ylim(0, 1100 if geography == 'international' else 1900)
    ax.set_yticks([0, 250, 500, 750, 1000] if geography == 'international'
                 else [0, 500, 1000, 1500])
    ax.set_xlabel('Year', labelpad=4)
    label = 'International flow' if geography == 'international' else 'Domestic intercity flow'
    ax.set_ylabel(label + '\n(thousand events)', labelpad=2)
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


def draw_comparison(ax):
    """Matched endpoint decreases; categorical dodge never changes x values."""
    with (OUT / 'source_data/international_comparison.csv').open(
            encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 4
    styles = {'BRIDGE': ('o', '#252A2E', '#252A2E', .11),
              'Yenilmez2026': ('s', 'white', '#747B82', -.11)}
    drawn = []
    for metric, center in [('HHI', 1.), ('Gini', 0.)]:
        pair = []
        for source, (marker, face, edge, offset) in styles.items():
            row = next(r for r in rows if r['metric'] == metric and r['source'] == source)
            assert row['countries'] == '147' and row['years'] == '1998-2023'
            decrease = 100 * (float(row['initial']) - float(row['final'])) / float(row['initial'])
            assert np.isclose(decrease, -float(row['relative_change_pct']), atol=1e-12)
            yy = center + offset
            pair.append((decrease, yy))
            ax.scatter([decrease], [yy], marker=marker, s=20, facecolors=face,
                       edgecolors=edge, linewidths=.8, zorder=4)
            ax.annotate(f'{decrease:.2f}', xy=(decrease, yy),
                        xytext=(0, 4 if offset > 0 else -4), textcoords='offset points',
                        ha='center', va='bottom' if offset > 0 else 'top', fontsize=7)
            drawn.append(dict(metric=metric, source=source, decrease_percent=decrease,
                              categorical_y=yy, countries=147, years='1998-2023'))
        ax.plot(*np.array(pair).T, color='#B8BEC3', lw=.75, zorder=2)
    ax.set(xlim=(0, 50), ylim=(-.55, 2.0))
    ax.set_xticks([0, 25, 50])
    ax.set_yticks([1., 0.], ['HHI', 'Gini'])
    ax.set_xlabel('Concentration decrease (%)', labelpad=4)
    handles = [Line2D([], [], linestyle='None', marker=marker, markersize=4.2,
                      markerfacecolor=face, markeredgecolor=edge, markeredgewidth=.8,
                      label='BRIDGE' if source == 'BRIDGE' else 'Scopus')
               for source, (marker, face, edge, _) in styles.items()]
    ax.legend(handles=handles, loc='upper left', borderaxespad=.25,
              handletextpad=.5, labelspacing=.35, fontsize=7)
    return {'countries': 147, 'years': [1998, 2023], 'points': drawn,
            'comparison_doi': '10.1007/s41109-026-00840-0',
            'definition': '100 * (index_1998 - index_2023) / index_1998',
            'matched_pool': 'Same 147 annually positive countries; full international margins renormalized within the common pool',
            'uncertainty': 'Descriptive endpoint changes; no uncertainty interval'}


def draw_entry(ax):
    """Every country is retained at its unjittered 2025 entry shares."""
    with (OUT / 'source_data/entrant_2025.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({r['country'] for r in rows}) == 76
    assert all(int(r['year']) == 2025 and int(r['N_E']) <= int(r['N']) for r in rows)
    x = 100 * np.array([float(r['entrant_city_share']) for r in rows])
    y = 100 * np.array([float(r['entrant_flow_share']) for r in rows])
    assert np.allclose(x, [100 * int(r['N_E']) / int(r['N']) for r in rows])
    assert np.all((x >= 0) & (x <= 100) & (y >= 0) & (y <= 100))
    mx, my = float(np.median(x)), float(np.median(y))
    ax.plot([0, 100], [0, 100], color='#969DA3', lw=.75, ls=(0, (3, 2)), zorder=1)
    ax.scatter(x, y, s=18, facecolors='#7C8389', edgecolors='white',
               linewidths=.35, alpha=.75, zorder=3)
    ax.scatter([mx], [my], marker='+', s=50, c='#15191C', linewidths=1.1, zorder=5)
    ax.text(.04, .96, f'Medians\n{mx:.1f}%, {my:.1f}%', transform=ax.transAxes,
            ha='left', va='top', fontsize=7, linespacing=1.25)
    ax.set(xlim=(-2, 102), ylim=(-2, 102))
    ax.set_xticks([0, 50, 100]); ax.set_yticks([0, 50, 100])
    ax.set_xlabel('New-city count share (%)', labelpad=4)
    ax.set_ylabel('New-city flow share (%)', labelpad=4)
    return {'countries': 76, 'year': 2025, 'country_points': [
                dict(country=r['country'], city_count_share_percent=float(xx),
                     flow_share_percent=float(yy)) for r, xx, yy in zip(rows, x, y)],
            'median_city_share_percent': mx, 'median_flow_share_percent': my,
            'countries_below_equality': int(np.sum(y < x)),
            'median_marker': 'Coordinate-wise medians, not an additional country',
            'new_city_definition': 'First recorded after 1998, active in 2025',
            'all_observations_retained': True, 'jitter_or_offsets': False}


def draw_growth(ax, geography, summaries, fitted):
    xkey = 'international_flow' if geography == 'international' else 'domestic_flow'
    ykey = 'partner_countries' if geography == 'international' else 'domestic_cities'
    original_panel = 'e' if geography == 'international' else 'f'
    curves = [r for r in fitted if r['panel'] == original_panel]
    xx = np.array([float(r['x']) for r in curves])
    yy = np.array([float(r['estimate']) for r in curves])
    lower = np.array([float(r['lower95']) for r in curves])
    upper = np.array([float(r['upper95']) for r in curves])
    assert np.all(np.diff(xx) > 0)
    assert np.all(lower <= yy) and np.all(yy <= upper)
    ax.fill_between(xx, lower, upper, color='#747B83', alpha=.10, linewidth=0, zorder=0)
    ax.plot(xx, yy, color='#59616A', linewidth=1.3, zorder=1)
    x = np.array([float(r[xkey + '_growth_pct']) for r in summaries])
    y = np.array([float(r[ykey + '_growth_pct']) for r in summaries])
    group_counts = {}
    for group, colour in GROUP_COLOURS.items():
        mask = np.array([int(r['group']) == group for r in summaries])
        group_counts[f'T{group}'] = int(mask.sum())
        assert all(r['colour'] == colour for r in summaries if int(r['group']) == group)
        ax.scatter(x[mask], y[mask], s=24, facecolors=to_rgba(colour, .55),
                   edgecolors=colour, linewidths=.65, zorder=4)
    assert list(group_counts.values()) == [15, 14, 24, 23]
    ax.set_xlim(min(0., x.min() - .06 * np.ptp(x)), x.max() + .06 * np.ptp(x))
    all_y = np.r_[y, lower, upper]
    ax.set_ylim(min(0., all_y.min() - .06 * np.ptp(all_y)),
                all_y.max() + .08 * np.ptp(all_y))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
    ax.set_xlabel('International growth (%/yr)' if geography == 'international'
                  else 'Domestic growth (%/yr)', labelpad=4)
    ax.set_ylabel('Partner growth (%/yr)' if geography == 'international'
                  else 'City growth (%/yr)', labelpad=4)
    handles = [Line2D([], [], linestyle='None', marker='o', markersize=4.5,
                      markerfacecolor=to_rgba(colour, .55), markeredgecolor=colour,
                      markeredgewidth=.5, label=f'T{group}')
               for group, colour in GROUP_COLOURS.items()]
    ax.legend(handles=handles, loc='lower right', ncol=2, fontsize=7.5,
              handlelength=.7, handletextpad=.4, columnspacing=.8,
              labelspacing=.3, borderaxespad=.4)
    grid(ax)
    return {'countries': len(summaries), 'groups': group_counts,
            'fit_vertices': len(curves), 'fit_and_CI_unchanged': True,
            'all_country_observations_retained': True}


def main():
    ARTWORK.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    configure()
    volume = read_csv('Fig2_growth_reference.csv')
    coverage = read_csv('Fig2_coverage_display_curves.csv')
    summaries = read_csv('Fig2_quartile_country_growth.csv')
    fitted = read_csv('Fig2_quartile_country_pooled_fits.csv')
    assert len(volume) == 56 and len(summaries) == 76 and len(fitted) == 402
    reports = []
    for number, geography in [(4, 'domestic')]:
        fig, axes = axes_row()
        report = {'figure': number, 'geography': geography,
                  'width_mm': WIDTH_MM, 'height_mm': HEIGHT_PT / 72 * 25.4,
                  'volume': draw_volume(axes[0], geography, volume),
                  'entry': draw_entry(axes[1]),
                  'growth': draw_growth(axes[2], geography, summaries, fitted)}
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
        'new_panel_source_sha256': hashlib.sha256((OUT / 'source_data/entrant_2025.csv').read_bytes()).hexdigest()
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'figures': [4], 'outputs': str(ARTWORK),
                      'all_data_and_fits_preserved': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
