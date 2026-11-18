"""Fig2 expansion, sign-anchored T1--T4 growth ranges and domestic Gini densities.

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
from audit_panel_alignment import require_matplotlib_panel_alignment
from figure_style import apply_light_grids, apply_nhb_typography

OUT = ROOT / 'outputs/figure_curves_fit_20261111'
DATA = ROOT / 'outputs/figures_T_unified_20261109/source_data'
ARTWORK = OUT / 'artwork'
QA = OUT / 'QA/Fig2'
WIDTH_MM = 180.
WIDTH = WIDTH_MM / 25.4 * 72
HEIGHT = 380.
COLORS = ['#7E99F4', '#A5AEB7', '#7AB656', '#CC7C71']
MEDIAN = '#E5BC5E'


def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    ARTWORK.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    source_path = OUT / 'plot_Fig4.py'
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

    def panel(name, left, bottom, width, height):
        ax = fig.add_axes([left / WIDTH, bottom / HEIGHT, width / WIDTH, height / HEIGHT])
        ax.set_gid(name)
        ax.tick_params(length=2.4, width=.55, pad=2.5)
        ax.set_axisbelow(True)
        axes[name] = ax
        return ax

    def letter(name, left, top):
        fig.text(left / WIDTH, top / HEIGHT, name, fontweight='bold',
                 fontsize=10, ha='left', va='bottom')

    top_bottom, top_height = 249., 101.
    for name, left in zip('abc', [45., 211., 377.]):
        panel(name, left, top_bottom, 125., top_height)
        letter(name, left - 14, top_bottom + top_height + 8)
    volume = current.draw_volume(axes['a'], 'international', read('Fig2_growth_reference.csv'))
    comparison = current.draw_comparison(axes['b'])

    trends = read('Fig2_T_country_trends.csv')
    groups = read('Fig2_T_groups.csv')
    histogram = read('Fig2_T_histogram.csv')
    density_rows = read('Fig2_T_density_curves.csv')
    rug_rows = read('Fig2_T_country_strip.csv')
    provenance = json.loads((DATA / 'Fig2_T_provenance.json').read_text(encoding='utf8'))
    cuts = np.asarray(provenance['group_cuts_pct_per_year'])
    rates = np.array([float(r['international_share_annual_rate_pct']) for r in trends])
    assert len(trends) == 76 and len({r['country'] for r in trends}) == 76
    group_counts = [sum(int(r['group']) == q for r in trends) for q in range(1, 5)]
    assert group_counts == [15, 14, 24, 23]
    assert np.allclose([np.median(rates[rates < 0]), 0., np.median(rates[rates > 0])], cuts)
    for r in trends:
        assert int(np.searchsorted(cuts, float(r['international_share_annual_rate_pct']), side='left') + 1) == int(r['group'])

    # Preserve the original histogram; colours now identify the unified T ranges.
    c = axes['c']
    counts = np.array([int(r['countries']) for r in histogram])
    edges = np.r_[[float(r['lower']) for r in histogram], float(histogram[-1]['upper'])]
    assert np.array_equal(np.histogram(rates, bins=edges)[0], counts)
    boundaries = np.r_[edges[0], cuts, edges[-1]]
    for j, (lo, hi) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        local_edges = np.r_[lo, edges[(edges > lo) & (edges < hi)], hi]
        mids = (local_edges[:-1] + local_edges[1:]) / 2
        local_counts = counts[np.searchsorted(edges, mids, side='right') - 1]
        c.stairs(local_counts, local_edges, baseline=0, fill=True,
                 color=COLORS[j], alpha=.23, linewidth=0)
    c.stairs(counts, edges, color='#3F776A', linewidth=1.1, zorder=3)
    c.set(xlim=(edges[0], edges[-1]), ylim=(0, counts.max() * 1.30))
    c.set_xticks([-5, 0, 5, 10])
    c.set_yticks([0, 4, 8, 12])
    c.set_ylabel('Countries', labelpad=4)
    c.set_xlabel('International share growth (%/year)', labelpad=9)
    c.xaxis.set_label_position('top')
    for cut in cuts:
        c.axvline(cut, ymax=.9, color='#747C80', lw=.55, ls=(0, (3, 2)))
    c.xaxis.set_minor_locator(AutoMinorLocator(2))
    c.yaxis.set_minor_locator(AutoMinorLocator(2))

    fig.canvas.draw()
    starts = []
    for j, (lo, hi) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        x0, x1 = [c.transData.transform((x, 0))[0] / fig.dpi * 72 for x in [lo, hi]]
        center = (x0 + x1) / 2
        fig.add_artist(Line2D([(x0 + 1) / WIDTH, (x1 - 1) / WIDTH], [224 / HEIGHT] * 2,
                             transform=fig.transFigure, color=COLORS[j], lw=2.))
        fig.text(center / WIDTH, 232 / HEIGHT, f'T{j+1}', ha='center', va='center', fontsize=7)
        starts.append(center)

    # KDEs were recomputed from all 76 unchanged country values in the T groups.
    lower_left, lower_right, gutter = 45., 502., 14.
    lower_width = (lower_right - lower_left - 3 * gutter) / 4
    ymax = max(float(r['density']) for r in density_rows) * 1.27
    summaries = []
    for j in range(4):
        q = j + 1
        name = 'defg'[j]
        left = lower_left + j * (lower_width + gutter)
        ax = panel(name, left, 43., lower_width, lower_width)
        values = [r for r in density_rows if int(r['group']) == q]
        xx = np.array([float(r['x']) for r in values])
        yy = np.array([float(r['density']) for r in values])
        assert np.all(np.diff(xx) > 0), 'The frozen KDE grid must be strictly increasing.'
        countries = [r for r in rug_rows if int(r['group']) == q]
        median = float(next(r for r in groups if int(r['group']) == q)['gini_trend_median'])
        assert len(countries) == group_counts[j] and len(values) == 401
        assert np.isclose(median, np.median([float(r['x']) for r in countries]))
        ax.fill_between(xx, 0, yy, color=COLORS[j], alpha=.17, linewidth=0, zorder=1)
        ax.plot(xx, yy, color=COLORS[j], lw=1.1, zorder=2)
        ax.axvline(0, color='#899095', lw=.55, ls=(0, (2, 2)), zorder=.5)
        ax.plot([median] * 2, [0, np.interp(median, xx, yy)], color=MEDIAN,
                lw=1.2, ls=(0, (4, 2)), zorder=4)
        ax.scatter([float(r['x']) for r in countries], [float(r['display_y']) for r in countries],
                   s=8, color='#4A4A4A', alpha=.70, edgecolors='none', linewidths=0, zorder=5)
        ax.set(xlim=(-5, 22), ylim=(0, ymax))
        ax.set_xticks([0, 10, 20])
        ax.yaxis.set_major_locator(MaxNLocator(nbins=3))
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
        if j == 0:
            ax.set_ylabel('Density', labelpad=4)
        else:
            ax.tick_params(axis='y', labelleft=False)
        lo, hi = boundaries[j:j+2]
        interval = (f'< {hi:.2f}%' if j == 0 else f'≥ {lo:.2f}%' if j == 3
                    else f'{lo:.2f} to {hi:.2f}%')
        ax.set_title(f'T{q}', fontsize=7, pad=10)
        ax.text(.97, .95, f'Median {median:.2f}', transform=ax.transAxes,
                ha='right', va='top', fontsize=7)
        letter(name, left - 14, 43 + lower_width + 8)
        target = left + lower_width / 2
        fig.add_artist(Line2D([starts[j] / WIDTH, starts[j] / WIDTH, target / WIDTH],
                             [218 / HEIGHT, 206 / HEIGHT, 178 / HEIGHT],
                             transform=fig.transFigure, color=COLORS[j], lw=.55, alpha=.75, zorder=0))
        summaries.append({'panel': name, 'trajectory_group': q, 'countries': group_counts[j], 'median': median,
                          'KDE_vertices_recomputed': len(values), 'country_values_unchanged': True})

    fig.text((lower_left + lower_right) / 2 / WIDTH, 16 / HEIGHT,
             'Domestic Gini trend (pp/decade)', ha='center', va='center', fontsize=7)
    fig.legend(handles=[
        Line2D([], [], color=MEDIAN, lw=1.2, ls=(0, (4, 2)), label='Median'),
        Line2D([], [], color='#899095', lw=.55, ls=(0, (2, 2)), label='No change')],
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
        row_groups=[list('abc'), list('defg')], column_groups=[])
    metadata = {
        'figure': 'Fig2', 'dimensions_mm': [180., HEIGHT / 72 * 25.4],
        'group_membership_source': provenance['source_membership'],
        'group_cuts_pct_per_year': cuts.tolist(),
        'trajectory_groups': 'T1--T4: sign of international-share growth, then median within each sign group',
        'volume': volume, 'comparison': comparison, 'lower_panels': summaries,
        'comparison_source_sha256': hashlib.sha256((OUT / 'source_data/annual_comparison.csv').read_bytes()).hexdigest(),
        'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in DATA.glob('Fig2*')},
        'source_policy': 'All country values and histogram bins unchanged; KDEs and group summaries recomputed for canonical T1--T4.'}
    (QA / 'figure_manifest.json').write_text(json.dumps(metadata, indent=2), encoding='utf8')
    for ext in ['pdf', 'svg', 'png']:
        fig.savefig(ARTWORK / f'Fig2.{ext}', dpi=600)
    with pymupdf.open(ARTWORK / 'Fig2.pdf') as doc:
        doc[0].get_pixmap(matrix=pymupdf.Matrix(2.6, 2.6), alpha=False).save(QA / 'preview.png')
    plt.close(fig)
    print(json.dumps({'figure': 'Fig2', 'panels': 7, 'group_counts': group_counts}))


if __name__ == '__main__':
    main()
