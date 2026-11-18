"""Preserve both former coverage panels, using neutral year encodings."""
from pathlib import Path
import csv
import importlib.util
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'figures/v3'),
                str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa')]
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pymupdf
from audit_panel_alignment import require_matplotlib_panel_alignment
from figure_style import apply_light_grids, apply_nhb_typography

WIDTH_MM, HEIGHT_PT = 180., 175.


def main():
    (OUT / 'artwork').mkdir(exist_ok=True)
    spec = importlib.util.spec_from_file_location('expansion_helpers', OUT / 'plot_Fig4.py')
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    shared.configure()
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica'],
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    qa = OUT / 'QA/FigS1'
    qa.mkdir(parents=True, exist_ok=True)
    with (OUT / 'source_data/coverage_curves.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    width_pt, height_pt = WIDTH_MM / 25.4 * 72, HEIGHT_PT
    fig = plt.figure(figsize=(WIDTH_MM / 25.4, height_pt / 72))
    styles = {1998: ('#252A2E', '-'), 2007: ('#676F76', (0, (5, 2))),
              2016: ('#252A2E', (0, (4, 2, 1, 2))), 2025: ('#676F76', (0, (1, 1.5)))}
    axes, reports = [], []
    for label, left, geography in [('a', 44., 'international'), ('b', 304., 'domestic')]:
        ax = fig.add_axes([left / width_pt, 35 / height_pt, 185 / width_pt, 110 / height_pt])
        ax.set_gid(label)
        ax.annotate(label, xy=(0, 1), xycoords='axes fraction', xytext=(-14, 8),
                    textcoords='offset points', fontsize=7, fontweight='bold', va='bottom')
        report = shared.draw_reach(ax, geography, rows)
        ax.set_title('International destinations (%)' if geography == 'international'
                     else 'Domestic destinations (%)', loc='left', fontsize=7, pad=9)
        for line in ax.lines:
            year = int(line.get_label())
            color, linestyle = styles[year]
            line.set_color(color); line.set_linestyle(linestyle)
            data = [r for r in rows if r['panel'] == ('b' if geography == 'international' else 'd')
                    and int(r['year']) == year]
            assert np.array_equal(line.get_xdata(), [float(r['source_locations_threshold']) for r in data])
            assert np.array_equal(line.get_ydata(), [float(r['percentage']) for r in data])
        ax.legend(loc='lower left' if geography == 'international' else 'upper right',
                  fontsize=7, handlelength=2.2, handletextpad=.5, labelspacing=.45)
        axes.append(ax); reports.append({'geography': geography, 'curves': report})
    apply_nhb_typography(fig)
    fig.canvas.draw(); apply_light_grids(fig, json_out=qa / 'grids.json')
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig, axes=axes, json_out=qa / 'alignment.json',
        overlay_svg=qa / 'alignment.svg', row_groups=[['a', 'b']], column_groups=[],
        tolerance_pt=1.5, gutter_tolerance_pt=1.5, strict=True, require_panel_labels=True)
    for ext in ['pdf', 'svg', 'png']:
        fig.savefig(OUT / 'artwork' / f'FigS1.{ext}', dpi=600)
    with pymupdf.open(OUT / 'artwork/FigS1.pdf') as document:
        document[0].get_pixmap(matrix=pymupdf.Matrix(2.6, 2.6), alpha=False).save(qa / 'preview.png')
    (qa / 'figure_manifest.json').write_text(json.dumps({
        'figure': 'FigS1', 'dimensions_mm': [180, height_pt / 72 * 25.4],
        'original_panels': ['Fig2b', 'Fig4b'], 'all_vertices_retained': True,
        'year_styles': {year: str(style) for year, style in styles.items()}, 'panels': reports
    }, indent=2), encoding='utf-8')
    plt.close(fig)
    print('FigS1: both coverage panels retained with neutral year encodings.')


if __name__ == '__main__':
    main()
