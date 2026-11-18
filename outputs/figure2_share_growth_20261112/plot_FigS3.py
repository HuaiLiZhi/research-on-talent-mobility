"""Replot the original Zhao HHI comparison at supplementary-figure size."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path


OUT = Path(__file__).resolve().parent
ORIGINAL = OUT.parent / 'figure2_zhao_hhi_20261112' / 'plot_Fig2.py'
WIDTH_MM, HEIGHT_PT = 89.0, 178.0


def load_module(name, path):
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    original = load_module('original_zhao_panel', ORIGINAL)
    style = load_module('figure_style_helper', original.COMPARISON_SOURCE / 'plot_Fig4.py')
    style.configure()
    original.plt.rcParams.update({
        'font.family': 'sans-serif', 'font.sans-serif': ['Arial', 'Helvetica'],
        'svg.fonttype': 'none', 'pdf.fonttype': 42,
    })
    width_pt = WIDTH_MM / 25.4 * 72
    fig = original.plt.figure(figsize=(WIDTH_MM / 25.4, HEIGHT_PT / 72))
    ax = fig.add_axes([45 / width_pt, 35 / HEIGHT_PT, (width_pt - 55) / width_pt, 115 / HEIGHT_PT])
    ax.set_gid('HHI')
    comparison = original.draw_zhao_hhi(ax)
    ax.set_ylabel('Indexed HHI', labelpad=4)
    ax.legend(loc='lower center', bbox_to_anchor=(.5, 1.05), ncol=2, fontsize=7,
              frameon=False, borderaxespad=0, borderpad=0, handlelength=1.3)
    qa = OUT / 'QA' / 'FigS3'
    qa.mkdir(parents=True, exist_ok=True)
    artwork = OUT / 'artwork'
    artwork.mkdir(exist_ok=True)
    original.apply_nhb_typography(fig)
    fig.canvas.draw()
    original.apply_light_grids(fig, json_out=qa / 'grids.json')
    fig.savefig(artwork / 'FigS3.pdf')
    fig.savefig(artwork / 'FigS3.svg')
    fig.savefig(artwork / 'FigS3.png', dpi=600)
    with original.pymupdf.open(artwork / 'FigS3.pdf') as document:
        document[0].get_pixmap(matrix=original.pymupdf.Matrix(2.6, 2.6), alpha=False).save(qa / 'preview.png')
    (qa / 'figure_manifest.json').write_text(json.dumps({
        'figure': 'FigS3', 'native_width_mm': WIDTH_MM, 'comparison': comparison,
        'source': 'outputs/figure2_zhao_hhi_20261112/source_data/period_HHI_comparison.csv',
    }, indent=2), encoding='utf-8')
    original.plt.close(fig)


if __name__ == '__main__':
    main()
