"""Reconcile four-year country histograms with cleaned margins and vector output."""
from pathlib import Path
import csv
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tmp/nhb_fig2_python_deps'))
import numpy as np
import pymupdf


def read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def main():
    out = Path(__file__).parent
    data, qa = out / 'source_data', out / 'QA/Fig2'
    manifest = json.loads((qa / 'figure_manifest.json').read_text(encoding='utf-8'))
    geometry = manifest['histogram_panel']
    countries = set(geometry['countries'])
    assert len(countries) == 76 and geometry['prior_streamgraph_removed']
    assert geometry['snapshot_years'] == [1998, 2007, 2016, 2025]
    assert not geometry['arithmetic_averaging']
    assert json.loads((qa / 'alignment.json').read_text())['verdict'] == 'PASS'
    alignment = json.loads((qa / 'alignment.json').read_text())['layout']
    assert np.isclose(alignment['figure']['height_pt'], 313.)
    for panel in alignment['panels']:
        assert np.isclose(panel['bbox_pt'][3] - panel['bbox_pt'][1], 95.)
    clean = ROOT / 'data/processed/mobility_city_harmonized_20261020/analysis'
    country_margins = read(clean / 'country_annual_margins.csv')
    inflows = {(r['country'], int(r['year'])): float(r['flow'])
               for r in country_margins
               if r['side'] == 'inflow' and r['country'] in countries}
    city_sets = {}; global_city_sets = {}
    for row in read(clean / 'domestic_city_margins.csv'):
        if row['side'] == 'inflow' and float(row['flow']) > 0:
            global_city_sets.setdefault(int(row['year']), set()).add(row['city_id'])
        if row['side'] == 'inflow' and row['country'] in countries:
            city_sets.setdefault((row['country'], int(row['year'])), set()).add(row['city_id'])
    annual = read(data / 'Fig2_histogram_annual_inputs.csv')
    assert len(annual) == 76 * 28
    for row in annual:
        key = row['country'], int(row['year'])
        assert float(row['international_flow']) == inflows[key]
        assert int(row['domestic_cities']) == len(city_sets[key])
    observations = read(data / 'Fig2_histogram_country_snapshots.csv')
    assert len(observations) == 608
    for row in observations:
        lo, hi = int(row['start_year']), int(row['end_year'])
        cc = row['country']
        expected = [inflows[cc, year] if row['metric'] == 'international_flow'
                    else len(city_sets[cc, year]) for year in range(lo, hi + 1)]
        assert len(expected) == int(row['annual_observations']) == 1
        assert lo == hi == int(row['year'])
        assert float(row['value']) == expected[0]
    summaries = read(data / 'Fig2_histogram_summaries.csv')
    for row in summaries:
        values = [float(r['value']) for r in observations
                  if r['panel'] == row['panel'] and r['period'] == row['period']]
        assert len(values) == 76
        for metric, function in [('arithmetic_mean', np.mean), ('median', np.median),
                                 ('minimum', np.min), ('maximum', np.max)]:
            assert np.isclose(float(row[metric]), function(values), atol=1e-10)
    bins = read(data / 'Fig2_histogram_bins.csv')
    ns = '{http://www.w3.org/2000/svg}'
    svg = ET.parse(out / 'Fig2.svg').getroot()
    groups = {g.get('id'): g for g in svg.iter(ns + 'g')}

    def path(identifier):
        element = next(groups[identifier].iter(ns + 'path'))
        numbers = re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?', element.get('d'))
        return np.array(numbers, dtype=float).reshape(-1, 2), element.get('style', '')

    for panel in geometry['panels']:
        x0, y0, width, height = panel['plot_rectangle_pt']
        xmin, xmax = panel['xlim']
        ymax = panel['ylim'][1]
        assert panel['xscale'] == 'log' and xmin > 0
        for period in geometry['periods']:
            selected = [r for r in bins if r['panel'] == panel['panel'] and r['period'] == period['label']]
            assert len(selected) == geometry['bins_per_panel'] == 50
            assert sum(int(r['countries']) for r in selected) == 76
            edges = [float(r['left']) for r in selected] + [float(selected[-1]['right'])]
            assert np.allclose(np.diff(np.log10(edges)), np.diff(np.log10(edges))[0])
            values = [float(r['value']) for r in observations
                      if r['panel'] == panel['panel'] and r['period'] == period['label']]
            assert list(np.histogram(values, edges)[0]) == [int(r['countries']) for r in selected]
            for row in selected:
                points, _ = path(f"hist_{panel['panel']}_{period['start_year']}_{row['bin_index']}")
                left, right = [x0 + np.log10(v / xmin) / np.log10(xmax / xmin) * width
                               for v in (float(row['left']), float(row['right']))]
                assert np.allclose([points[:, 0].min(), points[:, 0].max()], [left, right], atol=1e-5)
                assert np.isclose(np.ptp(points[:, 1]), int(row['countries']) / ymax * height, atol=1e-5)
        for guide in geometry['summary_guides']:
            if guide['panel'] != panel['panel']:
                continue
            period = next(p for p in geometry['periods'] if p['label'] == guide['period'])
            points, style = path(f"hist_{panel['panel']}_{period['start_year']}_{guide['statistic']}")
            expected_x = x0 + np.log10(guide['value'] / xmin) / np.log10(xmax / xmin) * width
            assert np.allclose(points[:, 0], expected_x, atol=1e-5)
            assert ('stroke-dasharray' in style) == (guide['statistic'] == 'median')
    assert geometry['detail_panels'] == []
    assert not any('_detail_' in identifier for identifier in groups if identifier)
    growth_count = 0
    if 'country_city_growth_panel' in manifest:
        growth = manifest['country_city_growth_panel']
        country_sets = {}
        for row in country_margins:
            if row['side'] == 'inflow' and float(row['flow']) > 0:
                country_sets.setdefault(int(row['year']), set()).add(row['country'])
        rows = read(data / 'Fig2_country_city_coverage_growth.csv')
        assert len(rows) == 56
        x0, y0, width, height = growth['plot_rectangle_pt']
        for series in growth['series']:
            selected = [row for row in rows if row['metric'] == series['metric']]
            assert [int(row['year']) for row in selected] == list(range(1998,2026))
            margins = country_sets if series['metric'] == 'countries_inflow' else global_city_sets
            baseline_count = len(margins[1998])
            points, _ = path('coverage_growth_' + series['metric'])
            assert points.shape == (28,2)
            for index,row in enumerate(selected):
                year = int(row['year']); expected_count = len(margins[year])
                assert int(row['count']) == expected_count
                assert int(row['baseline_count']) == baseline_count
                relative = expected_count / baseline_count
                assert np.isclose(float(row['relative_coverage']), relative)
                expected = [x0+(year-1998)/27*width,
                            313-(y0+(relative-growth['ylim'][0])/(growth['ylim'][1]-growth['ylim'][0])*height)]
                assert np.allclose(points[index], expected, atol=1e-5)
        growth_count = len(rows)
    with pymupdf.open(out / 'Fig2.pdf') as document, pymupdf.open(ROOT / 'figures/v4/Fig2.pdf') as reference:
        page = document[0]
        clip = pymupdf.Rect(0, 0, page.rect.width, 150)
        actual = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip, alpha=False)
        baseline = reference[0].get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=clip, alpha=False)
        upper_identical = actual.samples == baseline.samples
        delta = np.abs(np.frombuffer(actual.samples, dtype=np.uint8).astype(int)
                       - np.frombuffer(baseline.samples, dtype=np.uint8).astype(int))
        # A different page height can change subpixel antialiasing. Verify the
        # original text and point geometry independently before accepting this.
        actual_words = page.get_text('words', clip=clip)
        reference_words = reference[0].get_text('words', clip=clip)
        assert len(actual_words) == len(reference_words)
        for a, b in zip(actual_words, reference_words):
            assert a[4] == b[4] and np.allclose(a[:4], b[:4], atol=.001, rtol=0)
        assert delta.max() <= 5 and np.mean(delta != 0) < .0001
        if growth_count:
            previous = ROOT / 'outputs/fig2_v3_histograms_20261028/country_city_growth_update/Fig2.pdf'
            with pymupdf.open(previous) as retained:
                roi = pymupdf.Rect(265,150,page.rect.width,page.rect.height)
                actual_f = page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=roi,alpha=False)
                previous_f = retained[0].get_pixmap(matrix=pymupdf.Matrix(3,3),clip=roi,alpha=False)
                assert actual_f.samples == previous_f.samples, 'f must remain unchanged'
        spans = [s for b in page.get_text('dict')['blocks'] if 'lines' in b
                 for line in b['lines'] for s in line['spans']]
        minimum_pt = min(s['size'] for s in spans)
        assert minimum_pt >= 7.99
        page.get_pixmap(matrix=pymupdf.Matrix(3, 3), alpha=False).save(qa / 'preview.png')
    protected = json.loads((ROOT / 'outputs/fig2_v3_histograms_20261028/protected_files.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest for name, digest in protected.items())
    active_panels = {panel['panel'] for panel in geometry['panels']}
    result = dict(status='PASS', countries=76, cleaned_annual_records_verified=2128,
                  snapshot_observations_verified=608,
                  histogram_bins_verified=sum(row['panel'] in active_panels for row in bins),
                  geographic_growth_observations_verified=growth_count,
                  logarithmically_spaced_bins_per_year=50, logarithmic_x_axes=True,
                  snapshot_years=geometry['snapshot_years'],all_main_plot_heights_pt=95.,
                  insets_removed=True,
                  summary_guide_lines_verified=len(geometry['summary_guides']), upper_a_d_render_identical=upper_identical,
                  upper_a_d_text_geometry_preserved=True,
                  upper_a_d_max_raster_difference=int(delta.max()),
                  upper_a_d_changed_pixel_fraction=float(np.mean(delta != 0)),
                  protected_files_unchanged=len(protected), minimum_text_pt=minimum_pt,
                  alignment='PASS', all_values_positive=True)
    (qa / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
