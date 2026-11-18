"""Annual Gini companion to the two-source HHI comparison in Fig2b."""
from pathlib import Path
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
import pymupdf
from figure_style import apply_light_grids, apply_nhb_typography
from audit_panel_alignment import require_matplotlib_panel_alignment

WIDTH_MM, HEIGHT_PT = 89., 178.


def main():
    spec = importlib.util.spec_from_file_location('curve_helpers', OUT / 'plot_Fig4.py')
    shared = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(shared)
    shared.configure()
    plt.rcParams.update({'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica'],
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    qa = OUT / 'QA/FigS2'
    qa.mkdir(parents=True, exist_ok=True)
    (OUT / 'artwork').mkdir(exist_ok=True)
    width_pt = WIDTH_MM / 25.4 * 72
    fig = plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_PT / 72))
    ax = fig.add_axes([44 / width_pt, 35 / HEIGHT_PT, (width_pt - 55) / width_pt, 129 / HEIGHT_PT])
    ax.set_gid('Gini')
    data = shared.draw_comparison(ax, metric='Gini')
    apply_nhb_typography(fig)
    fig.canvas.draw(); apply_light_grids(fig, json_out=qa / 'grids.json')
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig, axes=[ax], json_out=qa / 'alignment.json',
        overlay_svg=qa / 'alignment.svg', tolerance_pt=1.5, gutter_tolerance_pt=1.5, strict=True)
    for ext in ['pdf', 'svg', 'png']:
        fig.savefig(OUT / 'artwork' / f'FigS2.{ext}', dpi=600)
    with pymupdf.open(OUT / 'artwork/FigS2.pdf') as document:
        document[0].get_pixmap(matrix=pymupdf.Matrix(2.6, 2.6), alpha=False).save(qa / 'preview.png')
    (qa / 'figure_manifest.json').write_text(json.dumps({
        'figure': 'FigS2', 'dimensions_mm': [WIDTH_MM, HEIGHT_PT / 72 * 25.4],
        'comparison': data, 'role': 'Gini sensitivity companion to main HHI comparison'
    }, indent=2), encoding='utf-8')
    plt.close(fig)
    print('FigS2: two annual Gini curves, same matched 147-country sample.')


if __name__ == '__main__':
    main()
