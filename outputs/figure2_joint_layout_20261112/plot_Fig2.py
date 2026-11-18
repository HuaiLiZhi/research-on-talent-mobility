"""Fig2 expansion, international Gini, and a joint view of international and domestic trends.

Country observations are preserved. KDEs and medians use exactly the same
country assignments as Fig3--5, with a common fixed smoothing bandwidth.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'figures/v3'),
                str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa')]
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import AutoMinorLocator, MaxNLocator
import numpy as np
import pymupdf
from scipy.stats import spearmanr
from audit_panel_alignment import require_matplotlib_panel_alignment
from figure_style import (
    ANNUAL_LINEWIDTH_PT, ANNUAL_MARKER_EDGE_PT, ANNUAL_MARKER_PT,
    COUNTRY_POINT_ALPHA, COUNTRY_POINT_EDGE_PT, COUNTRY_POINT_PT2,
    DISTRIBUTION_LINEWIDTH_PT, DISTRIBUTION_POINT_PT2, REFERENCE_COLOUR,
    REFERENCE_LINESTYLE, REFERENCE_LINEWIDTH_PT, TICK_LINEWIDTH_PT,
    apply_light_grids, apply_nhb_typography,
)

OUT = Path(__file__).resolve().parent
COMPARISON_SOURCE = ROOT / 'outputs/figure_gini_palette_20261111'
DATA = ROOT / 'outputs/figures_T_unified_20261109/source_data'
ARTWORK = OUT / 'artwork'
QA = OUT / 'QA/Fig2'
WIDTH_MM = 180.
WIDTH = WIDTH_MM / 25.4 * 72
HEIGHT = 477.
COLORS = ['#7E99F4', '#A5AEB7', '#7AB656', '#CC7C71']
MEDIAN = '#E5BC5E'
FIXED_COUNTRY_METRICS = ROOT / 'outputs/figure_revision_20261111/artwork/source_data/Fig3_fixed_country_metrics.csv'
ALL_COUNTRY_METRICS = ROOT / 'figures/v4/source_data/Fig3_combined_country_metrics.csv'
PLOT_DATA = OUT / 'source_data'
GINI_CSV = PLOT_DATA / 'international_gini.csv'
SCATTER_CSV = PLOT_DATA / 'country_scatter.csv'
MARGINAL = '#3F776A'


def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def draw_international_gini(ax, red, blue):
    """Compare the same 203 countries with all countries observed each year."""
    plotted = []
    for sample, label, colour, path in [
        ('Fixed', 'Initial Countries', red, FIXED_COUNTRY_METRICS),
        ('All', 'All Countries', blue, ALL_COUNTRY_METRICS),
    ]:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        years = [int(row['year']) for row in rows]
        values = [float(row['Gini']) for row in rows]
        assert years == list(range(1998, 2026))
        ax.plot(years, values, color=colour, linewidth=ANNUAL_LINEWIDTH_PT,
                marker='o', markersize=ANNUAL_MARKER_PT, markeredgecolor='white',
                markeredgewidth=ANNUAL_MARKER_EDGE_PT, label=label, zorder=3)
        plotted.extend(dict(sample=sample, year=year, Gini=value) for year, value in zip(years, values))
    ax.set(xlim=(1996, 2027), ylim=(.84, .91))
    ax.set_xticks([1998, 2012, 2025])
    ax.set_yticks([.85, .88, .91])
    ax.set_xlabel('Year', labelpad=4)
    ax.set_ylabel('International Mobility Gini', labelpad=4)
    ax.legend(loc='lower left', bbox_to_anchor=(.025, .035),
              borderaxespad=0, handlelength=1.3, labelspacing=.25)
    with GINI_CSV.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['sample', 'year', 'Gini'])
        writer.writeheader()
        writer.writerows(plotted)
    return {'countries_in_fixed_sample': 203, 'observations': len(plotted),
            'plotted_data_sha256': hashlib.sha256(GINI_CSV.read_bytes()).hexdigest()}


def draw_joint_distribution(scatter, below, right, trends, histogram, density_rows, cuts):
    rates = np.array([float(r['international_share_annual_rate_pct']) for r in trends])
    gini = np.array([float(r['domestic_gini_trend_pp_decade']) for r in trends])
    groups = np.array([int(r['group']) for r in trends])
    counts = np.array([int(r['countries']) for r in histogram])
    edges = np.r_[[float(r['lower']) for r in histogram], float(histogram[-1]['upper'])]
    assert np.array_equal(np.histogram(rates, bins=edges)[0], counts)
    assert len(trends) == len({r['country'] for r in trends}) == 76
    group_counts = np.bincount(groups, minlength=5)[1:]
    assert group_counts.tolist() == [15, 14, 24, 23]
    assert np.allclose([np.median(rates[rates < 0]), 0., np.median(rates[rates > 0])], cuts)
    assert np.array_equal(np.searchsorted(cuts, rates, side='left') + 1, groups)
    rho = float(spearmanr(rates, gini).statistic)
    assert round(rho, 2) == .52

    boundaries = np.r_[edges[0], cuts, edges[-1]]
    scatter.set(xlim=(edges[0], edges[-1]), ylim=(-5, 22))
    assert np.all((gini >= -5) & (gini <= 22))
    scatter.set_xticks([-5, 0, 5, 10])
    scatter.set_yticks([-5, 0, 5, 10, 15, 20])
    scatter.set_xlabel('International Share Growth (%/year)', labelpad=3)
    scatter.xaxis.set_label_position('top')
    scatter.set_ylabel('Domestic City Gini Slope (pp/decade)', labelpad=5)
    scatter.tick_params(axis='x', which='both', top=True, labeltop=True,
                        bottom=False, labelbottom=False)
    scatter.spines['top'].set_visible(True)
    scatter.axhline(0, color=REFERENCE_COLOUR, lw=REFERENCE_LINEWIDTH_PT,
                    ls=REFERENCE_LINESTYLE, zorder=1)
    for cut in cuts:
        scatter.axvline(cut, color=REFERENCE_COLOUR, lw=REFERENCE_LINEWIDTH_PT,
                        ls=REFERENCE_LINESTYLE, zorder=1)
        below.axvline(cut, color=REFERENCE_COLOUR, lw=REFERENCE_LINEWIDTH_PT,
                      ls=REFERENCE_LINESTYLE, zorder=1)
    centres = (boundaries[:-1] + boundaries[1:]) / 2
    for index, colour in enumerate(COLORS):
        selected = groups == index + 1
        scatter.scatter(rates[selected], gini[selected], s=COUNTRY_POINT_PT2, color=colour,
                        edgecolors='white', linewidths=COUNTRY_POINT_EDGE_PT,
                        alpha=COUNTRY_POINT_ALPHA, zorder=3)
    scatter.text(.96, .943, f'Spearman ρ = {rho:.2f}', transform=scatter.transAxes,
                 va='top', ha='right')

    # Match the former c outline and split its fill at the same T boundaries.
    for colour, lo, hi in zip(COLORS, boundaries[:-1], boundaries[1:]):
        local_edges = np.r_[lo, edges[(edges > lo) & (edges < hi)], hi]
        midpoints = (local_edges[:-1] + local_edges[1:]) / 2
        bin_counts = counts[np.searchsorted(edges, midpoints, side='right') - 1]
        below.stairs(bin_counts, local_edges, baseline=0, fill=True,
                     color=colour, alpha=.23, linewidth=0)
    below.stairs(counts, edges, color=MARGINAL, linewidth=DISTRIBUTION_LINEWIDTH_PT, zorder=3)
    below.set(ylim=(counts.max() * 1.17, 0), yticks=[])
    below.spines['left'].set_visible(False)
    below.spines['bottom'].set_visible(False)
    below.tick_params(axis='x', which='both', bottom=False, labelbottom=False)

    density_grid = np.array([float(row['x']) for row in density_rows if int(row['group']) == 1])
    densities = []
    for group in range(1, 5):
        values = [row for row in density_rows if int(row['group']) == group]
        assert np.array_equal(density_grid, [float(row['x']) for row in values])
        densities.append([float(row['density']) for row in values])
    # With the common bandwidth, the weighted group densities add to the pooled KDE.
    contributions = np.asarray(densities) * (group_counts / len(trends))[:, None]
    pooled_density = np.zeros_like(density_grid)
    for colour, contribution in zip(COLORS, contributions):
        edge = pooled_density + contribution
        right.fill_betweenx(density_grid, pooled_density, edge, color=colour,
                            alpha=.23, linewidth=0)
        pooled_density = edge
    right.plot(pooled_density, density_grid, color=MARGINAL, lw=DISTRIBUTION_LINEWIDTH_PT)
    right.set_xlim(0, pooled_density.max() * 1.10)
    right.set_axis_off()

    fields = ['country', 'group', 'international_share_annual_rate_pct', 'domestic_gini_trend_pp_decade']
    with SCATTER_CSV.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(trends)
    return centres, group_counts.tolist(), {
        'countries': len(trends), 'spearman_rho': rho,
        'x_axis': 'Above the scatterplot',
        'bottom_marginal': 'Inverted histogram with the original bins and fills split at the T cutoffs',
        'right_marginal': 'Pooled KDE with group-size-weighted T1-T4 density fills',
        'plotted_data_sha256': hashlib.sha256(SCATTER_CSV.read_bytes()).hexdigest(),
    }


def main():
    ARTWORK.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    PLOT_DATA.mkdir(exist_ok=True)
    source_path = COMPARISON_SOURCE / 'plot_Fig4.py'
    spec = importlib.util.spec_from_file_location('current_expansion', source_path)
    current = importlib.util.module_from_spec(spec)
    import_paths = list(sys.path)
    try:
        spec.loader.exec_module(current)
    finally:
        # Retain the active import environment after loading the shared helpers.
        sys.path[:] = import_paths
    current.configure()
    mpl.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica'],
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    fig = plt.figure(figsize=(WIDTH / 72, HEIGHT / 72))
    axes = {}

    def panel(name, left, bottom, width, height, **shared):
        ax = fig.add_axes([left / WIDTH, bottom / HEIGHT, width / WIDTH, height / HEIGHT], **shared)
        ax.set_gid(name)
        ax.tick_params(length=2.4, width=TICK_LINEWIDTH_PT, pad=2.5)
        ax.set_axisbelow(True)
        axes[name] = ax
        return ax

    def letter(name, left, top):
        fig.text(left / WIDTH, top / HEIGHT, name, fontweight='bold',
                 fontsize=10, ha='left', va='bottom')

    upper_top = HEIGHT - 24.
    left, small_side = 45., 120.
    a_bottom = upper_top - small_side
    b_top = a_bottom - 30.
    a = panel('a', left, a_bottom, small_side, small_side)
    b = panel('b', left, b_top - small_side, small_side, small_side)
    letter('a', left - 14., upper_top + 8.)
    letter('b', left - 14., b_top + 8.)
    volume = current.draw_volume(a, 'international', read('Fig2_growth_reference.csv'))
    trends = read('Fig2_T_country_trends.csv')
    international_gini = draw_international_gini(b, current.RED, current.BLUE)

    joint_left, joint_side = 229., 223.
    joint_bottom = upper_top - joint_side
    marginal_height = 33.
    marginal_bottom = joint_bottom - marginal_height - 8.
    scatter = panel('c', joint_left, joint_bottom, joint_side, joint_side)
    below = panel('c_x_marginal', joint_left, marginal_bottom, joint_side, marginal_height,
                  sharex=scatter)
    right = panel('c_y_marginal', 459., joint_bottom, 43., joint_side, sharey=scatter)
    letter('c', joint_left - 14., upper_top + 8.)
    groups = read('Fig2_T_groups.csv')
    histogram = read('Fig2_T_histogram.csv')
    density_rows = read('Fig2_T_density_curves.csv')
    rug_rows = read('Fig2_T_country_strip.csv')
    provenance = json.loads((DATA / 'Fig2_T_provenance.json').read_text(encoding='utf8'))
    cuts = np.asarray(provenance['group_cuts_pct_per_year'])
    centres, group_counts, joint_summary = draw_joint_distribution(
        scatter, below, right, trends, histogram, density_rows, cuts,
    )
    fig.canvas.draw()
    starts = [scatter.transData.transform((centre, 0))[0] / fig.dpi * 72 for centre in centres]

    # KDEs were recomputed from all 76 unchanged country values in the T groups.
    lower_left, lower_right, gutter = 45., 502., 14.
    lower_width = (lower_right - lower_left - 3 * gutter) / 4
    lower_bottom, lower_height = 43., .90 * lower_width
    lower_top = lower_bottom + lower_height
    ymax = max(float(r['density']) for r in density_rows) * 1.27
    summaries = []
    for j in range(4):
        q = j + 1
        name = 'defg'[j]
        left = lower_left + j * (lower_width + gutter)
        ax = panel(name, left, lower_bottom, lower_width, lower_height)
        values = [r for r in density_rows if int(r['group']) == q]
        xx = np.array([float(r['x']) for r in values])
        yy = np.array([float(r['density']) for r in values])
        assert np.all(np.diff(xx) > 0), 'The frozen KDE grid must be strictly increasing.'
        countries = [r for r in rug_rows if int(r['group']) == q]
        median = float(next(r for r in groups if int(r['group']) == q)['gini_trend_median'])
        assert len(countries) == group_counts[j] and len(values) == 401
        assert np.isclose(median, np.median([float(r['x']) for r in countries]))
        ax.fill_between(xx, 0, yy, color=COLORS[j], alpha=.17, linewidth=0, zorder=1)
        ax.plot(xx, yy, color=COLORS[j], lw=DISTRIBUTION_LINEWIDTH_PT, zorder=2)
        ax.axvline(0, color=REFERENCE_COLOUR, lw=REFERENCE_LINEWIDTH_PT,
                   ls=REFERENCE_LINESTYLE, zorder=.5)
        ax.plot([median] * 2, [0, np.interp(median, xx, yy)], color=MEDIAN,
                lw=1.2, ls=(0, (4, 2)), zorder=4)
        ax.scatter([float(r['x']) for r in countries], [float(r['display_y']) for r in countries],
                   s=DISTRIBUTION_POINT_PT2, color='#4A4A4A', alpha=.70,
                   edgecolors='none', linewidths=0, zorder=5)
        ax.set(xlim=(-5, 22), ylim=(0, ymax))
        ax.set_xticks([0, 10, 20])
        ax.yaxis.set_major_locator(MaxNLocator(nbins=3))
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        if j == 0:
            ax.set_ylabel('Probability Density', labelpad=4)
        else:
            ax.tick_params(axis='y', labelleft=False)
        ax.set_title(f'T{q}', fontsize=7, pad=10)
        ax.text(.97, .95, f'Median {median:.2f}', transform=ax.transAxes,
                ha='right', va='top', fontsize=7)
        letter(name, left - 14, lower_top + 8.)
        target = left + lower_width / 2
        fig.add_artist(Line2D([starts[j] / WIDTH, starts[j] / WIDTH, target / WIDTH],
                             [(marginal_bottom - 6.) / HEIGHT, (marginal_bottom - 10.) / HEIGHT,
                              (lower_top + 19.) / HEIGHT],
                             transform=fig.transFigure, color=COLORS[j], lw=.55, alpha=.75, zorder=0))
        summaries.append({'panel': name, 'trajectory_group': q, 'countries': group_counts[j], 'median': median,
                          'KDE_vertices_recomputed': len(values), 'country_values_unchanged': True})

    fig.text((lower_left + lower_right) / 2 / WIDTH, 16 / HEIGHT,
             'Domestic City Gini Slope (pp/decade)', ha='center', va='center', fontsize=7)
    fig.legend(handles=[
        Line2D([], [], color=MEDIAN, lw=1.2, ls=(0, (4, 2)), label='Median'),
        Line2D([], [], color=REFERENCE_COLOUR, lw=REFERENCE_LINEWIDTH_PT,
               ls=REFERENCE_LINESTYLE, label='No change')],
        loc='center right', bbox_to_anchor=(lower_right / WIDTH, 16 / HEIGHT), ncol=2,
        fontsize=7, handlelength=1.3, handletextpad=.4, columnspacing=.8,
        borderaxespad=0, borderpad=0)
    apply_nhb_typography(fig)
    fig.canvas.draw()
    apply_light_grids(fig, json_out=QA / 'grids.json')
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig, axes=list(axes.values()),
        json_out=QA / 'alignment.json', overlay_svg=QA / 'alignment.svg', strict=True,
        tolerance_pt=1.5, gutter_tolerance_pt=1.5,
        row_groups=[list('defg')], column_groups=[list('ab')])
    assert np.allclose(scatter.get_position().extents[[0, 2]], below.get_position().extents[[0, 2]])
    assert np.allclose(scatter.get_position().extents[[1, 3]], right.get_position().extents[[1, 3]])
    panel_sizes = {name: [ax.get_position().width * WIDTH, ax.get_position().height * HEIGHT]
                   for name, ax in axes.items()}
    for name in 'abc':
        width, height = panel_sizes[name]
        assert np.isclose(width, height), f'Panel {name} must be square.'
    metadata = {
        'figure': 'Fig2', 'dimensions_mm': [180., HEIGHT / 72 * 25.4],
        'panel_sizes_pt': panel_sizes,
        'group_membership_source': provenance['source_membership'],
        'group_cuts_pct_per_year': cuts.tolist(),
        'trajectory_groups': 'T1--T4: sign of international-share growth, then median within each sign group',
        'volume': volume, 'international_gini': international_gini,
        'joint_distribution': joint_summary, 'lower_panels': summaries,
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in DATA.glob('Fig2*')},
        'source_policy': 'All 76 countries and T memberships retained. Panels a and d-g retain their original data.'}
    (QA / 'figure_manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf8')
    for ext in ['pdf', 'svg', 'png']:
        fig.savefig(ARTWORK / f'Fig2.{ext}', dpi=600)
    with pymupdf.open(ARTWORK / 'Fig2.pdf') as doc:
        doc[0].get_pixmap(matrix=pymupdf.Matrix(2.6, 2.6), alpha=False).save(QA / 'preview.png')
    plt.close(fig)
    print(json.dumps({'figure': 'Fig2', 'panels': 7, 'group_counts': group_counts}))


if __name__ == '__main__':
    main()
