"""Recompute disciplinary comparisons from harmonized annual mobility events."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

from figure_style import output_root
OUT = output_root(Path(__file__).resolve().parent)
ROOT = Path(__file__).resolve().parents[2]
DATA = OUT / 'source_data'
QA = OUT / 'QA/Fig6'
SOURCE = ROOT / 'data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet'
sys.path.insert(0, str(ROOT / 'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np

YEARS = np.arange(1998, 2026)
TIME = YEARS - YEARS.mean()
PERIODS = [(1998, 2004), (2005, 2011), (2012, 2018), (2019, 2025)]
CATEGORIES = ['Relative concentration', 'Deconcentration', 'Mixed changes']


def read(name):
    with (DATA / name).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(name, rows):
    assert rows
    with (DATA / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def slope(values):
    v = np.asarray(values, dtype=float)
    assert v.shape == (28,) and np.all(np.isfinite(v))
    return float(TIME @ v / (TIME @ TIME))


def growth(values):
    v = np.asarray(values, dtype=float)
    assert np.all(v > 0)
    return float(100 * np.expm1(slope(np.log(v))))


def classify(gini_slope, normalized_slope):
    tolerance = 1e-10
    if gini_slope > tolerance and normalized_slope < -tolerance:
        return CATEGORIES[0]
    if gini_slope < -tolerance and normalized_slope > tolerance:
        return CATEGORIES[1]
    return CATEGORIES[2]


def prepare_stacked_panels():
    """Counts and event-weighted shares are additive 100-percent compositions."""
    QA.mkdir(parents=True, exist_ok=True)
    annual = read('Fig6_field_annual_data.csv')
    trends = read('Fig6_domestic_country_trends.csv')
    fields = sorted({r['field'] for r in annual})
    assert len(fields) == 26
    classifications, stacks, domestic_classes, ratios = [], [], [], []
    for scale in ['country', 'domestic_city']:
        for start, end in PERIODS:
            time = np.arange(7) - 3
            for field in fields:
                rows = sorted([r for r in annual if r['field'] == field and r['scale'] == scale
                               and start <= int(r['year']) <= end], key=lambda r: int(r['year']))
                assert len(rows) == 7
                gini = float(time @ np.array([float(r['Gini']) for r in rows]) / (time @ time) * 100)
                normalized = float(time @ np.array([float(r['normalized_equivalent']) for r in rows]) / (time @ time) * 100)
                classifications.append(dict(field=field, scale=scale, start_year=start, end_year=end,
                                            Gini_slope_pp=gini, normalized_slope_pp=normalized,
                                            category=classify(gini, normalized)))
            selected = [r for r in classifications if r['scale'] == scale and r['start_year'] == start]
            for category in CATEGORIES:
                count = sum(r['category'] == category for r in selected)
                stacks.append(dict(scale=scale, start_year=start, end_year=end, category=category,
                                   fields=count, denominator_fields=26, share_percent=100 * count / 26))
    for row in trends:
        domestic_classes.append(dict(row, category=classify(float(row['Gini_slope_pp']),
                                                            float(row['normalized_slope_pp']))))
    for field in fields:
        rows = [r for r in domestic_classes if r['field'] == field]
        total_flow = sum(float(r['total_domestic_events']) for r in rows)
        for basis in ['countries', 'flow']:
            denominator = len(rows) if basis == 'countries' else total_flow
            for category in CATEGORIES:
                selected = [r for r in rows if r['category'] == category]
                numerator = len(selected) if basis == 'countries' else sum(float(r['total_domestic_events']) for r in selected)
                ratios.append(dict(field=field, basis=basis, category=category, numerator=numerator,
                                   denominator=denominator, share_percent=100 * numerator / denominator))
    con = duckdb.connect()
    path = str(SOURCE).replace("'", "''")
    volumes = []
    for geo, period, total in con.execute(f"""SELECT
        CASE WHEN origin_country=destination_country THEN 'domestic_city' ELSE 'country' END AS geo,
        floor((year-1998)/7)::INTEGER AS period,sum(flow) AS total
        FROM read_parquet('{path}') WHERE flow>0 AND field<>'Unknown' GROUP BY geo,period ORDER BY geo,period""").fetchall():
        start, end = PERIODS[period]
        volumes.append(dict(scale=geo, start_year=start, end_year=end, total_events=float(total),
                            mean_annual_events=float(total / 7), mean_annual_million=float(total / 7e6)))
    con.close()
    assert len(volumes) == 8
    write('Fig6_period_trend_classification.csv', classifications)
    write('Fig6_period_discipline_composition.csv', stacks)
    write('Fig6_period_flow_volumes.csv', volumes)
    write('Fig6_country_trend_classification.csv', domestic_classes)
    write('Fig6_domestic_trend_composition.csv', ratios)
    info = dict(source_sha256=sha256(SOURCE), categories=CATEGORIES,
                classification='Gini slope>0 and evenness slope<0: relative concentration; opposite signs: deconcentration; other combinations: mixed; numerical zero tolerance=1e-10 percentage points/year',
                panel_a='Four independent seven-year trends per field and scale; each stack contains the same 26 fields with equal weights',
                panel_a_top='Global mean annual international/domestic event counts in each period, across all 26 named fields; each event counted once',
                panel_b='Full-period country-specific domestic classifications; country-count share versus share of total 1998–2025 domestic events in the same fixed field cohort',
                samples='Same field-specific fixed countries and combined-strength metrics as the current Fig6',
                files={name: sha256(DATA / name) for name in [
                    'Fig6_period_trend_classification.csv', 'Fig6_period_discipline_composition.csv',
                    'Fig6_period_flow_volumes.csv', 'Fig6_country_trend_classification.csv',
                    'Fig6_domestic_trend_composition.csv']})
    (QA / 'stacked_data_manifest.json').write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(period_field_classifications=len(classifications), stacked_segments=len(stacks),
                          country_classifications=len(domestic_classes), ratio_segments=len(ratios))))


def metric_sql(table, keys, place):
    group = ','.join(keys)
    return f"""WITH ranked AS (
        SELECT *,row_number() OVER(PARTITION BY {group} ORDER BY flow,{place}) AS rk
        FROM {table})
        SELECT {group},count(*) AS N,sum(flow) AS strength,
            sum(flow*flow)/power(sum(flow),2) AS HHI,
            2.0*sum(rk*flow)/(count(*)*sum(flow))-(count(*)+1.0)/count(*) AS Gini
        FROM ranked GROUP BY {group} ORDER BY {group}"""


def fetch_metrics(con, table, keys, place):
    rows = []
    for result in con.execute(metric_sql(table, keys, place)).fetchall():
        values, n, total, hhi, gini = result[:-4], *result[-4:]
        row = dict(zip(keys, values))
        row.update(N=int(n), combined_strength=float(total), flow_events=float(total / 2),
                   HHI=float(hhi), Gini=float(max(0., gini)),
                   equivalent=1 / float(hhi), normalized_equivalent=1 / (int(n) * float(hhi)))
        assert row['N'] >= 2 and 0 < row['normalized_equivalent'] <= 1 + 1e-12
        rows.append(row)
    return rows


def prepare():
    DATA.mkdir(exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    countries = json.loads((OUT / 'QA/figure_manifest.json').read_text(encoding='utf8'))[
        'cleaned_data_provenance']['fixed_country_codes']
    assert len(countries) == 76 and not set(countries) & {'HK', 'MO', 'TW'}
    codes = ','.join("'" + cc + "'" for cc in countries)
    con = duckdb.connect()
    con.execute("SET threads=4; SET memory_limit='2GB'")
    sqlpath = str(SOURCE).replace("'", "''")
    con.execute(f"CREATE VIEW all_events AS SELECT * FROM read_parquet('{sqlpath}') WHERE flow>0")
    field_totals = con.execute('SELECT field,count(*),sum(flow) FROM all_events GROUP BY field ORDER BY field').fetchall()
    fields = [f for f, _, _ in field_totals if f != 'Unknown']
    assert len(fields) == 26
    con.execute("CREATE VIEW events AS SELECT * FROM all_events WHERE field<>'Unknown'")
    assert con.execute('SELECT count(*) FROM events WHERE origin=destination').fetchone()[0] == 0
    print('Computing combined country margins for 26 fields', flush=True)
    con.execute("""CREATE TEMP TABLE international_margins AS
        SELECT field,year,country,sum(flow) AS flow FROM (
            SELECT field,year,origin_country AS country,flow FROM events WHERE origin_country<>destination_country
            UNION ALL
            SELECT field,year,destination_country,flow FROM events WHERE origin_country<>destination_country)
        GROUP BY ALL""")
    international = fetch_metrics(con, 'international_margins', ['field', 'year'], 'country')
    print('Computing within-country city margins by field', flush=True)
    con.execute(f"""CREATE TEMP TABLE domestic_margins AS
        SELECT field,year,country,city,sum(flow) AS flow FROM (
            SELECT field,year,origin_country AS country,origin AS city,flow FROM events
                WHERE origin_country=destination_country AND origin_country IN ({codes})
            UNION ALL
            SELECT field,year,destination_country,destination,flow FROM events
                WHERE origin_country=destination_country AND origin_country IN ({codes}))
        GROUP BY ALL""")
    domestic = fetch_metrics(con, 'domestic_margins', ['field', 'country', 'year'], 'city')
    totals = {(f, int(y), geo): float(v) for f, y, geo, v in con.execute("""
        SELECT field,year,CASE WHEN origin_country=destination_country THEN 'domestic'
        ELSE 'international' END AS geography,sum(flow) FROM events GROUP BY ALL""").fetchall()}
    margin_count = con.execute('SELECT count(*) FROM domestic_margins').fetchone()[0]
    con.close()

    grouped = defaultdict(list)
    for r in domestic:
        grouped[r['field'], r['country']].append(r)
    cohorts = {field: sorted(cc for (f, cc), rows in grouped.items()
                             if f == field and len(rows) == 28 and min(r['N'] for r in rows) >= 2)
               for field in fields}
    assert all(cohorts.values())
    national = {(r['field'], r['year']): r for r in international}
    local = {(r['field'], r['country'], r['year']): r for r in domestic}
    annual, country_trends, samples, summary, periods, boxes = [], [], [], [], [], []
    retained = []
    for field in fields:
        cohort = cohorts[field]
        trend_rows = []
        for cc in cohort:
            rows = [local[field, cc, int(y)] for y in YEARS]
            retained.extend(rows)
            tr = dict(field=field, country=cc, years=28,
                      Gini_slope_pp=100 * slope([r['Gini'] for r in rows]),
                      normalized_slope_pp=100 * slope([r['normalized_equivalent'] for r in rows]),
                      HHI_slope=slope([r['HHI'] for r in rows]),
                      equivalent_growth_pct=growth([r['equivalent'] for r in rows]),
                      total_domestic_events=sum(r['flow_events'] for r in rows))
            country_trends.append(tr)
            trend_rows.append(tr)
        for year in map(int, YEARS):
            r = national[field, year]
            assert r['flow_events'] == totals[field, year, 'international']
            annual.append(dict(field=field, scale='country', year=year, flow_events=r['flow_events'],
                               N=float(r['N']), equivalent=r['equivalent'],
                               normalized_equivalent=r['normalized_equivalent'], Gini=r['Gini'], country_sample_n=0))
            rows = [local[field, cc, year] for cc in cohort]
            annual.append(dict(field=field, scale='domestic_city', year=year,
                               flow_events=sum(r['flow_events'] for r in rows),
                               N=float(np.median([r['N'] for r in rows])),
                               equivalent=float(np.median([r['equivalent'] for r in rows])),
                               normalized_equivalent=float(np.median([r['normalized_equivalent'] for r in rows])),
                               Gini=float(np.median([r['Gini'] for r in rows])), country_sample_n=len(cohort)))
        global_domestic = sum(totals[field, int(y), 'domestic'] for y in YEARS)
        sample_domestic = sum(r['total_domestic_events'] for r in trend_rows)
        samples.append(dict(field=field, countries=len(cohort), country_codes=','.join(cohort),
                            retained_domestic_flow_percent=100 * sample_domestic / global_domestic,
                            retained_domestic_events=sample_domestic, all_domestic_events=global_domestic))
        for scale in ['country', 'domestic_city']:
            rows = sorted([r for r in annual if r['field'] == field and r['scale'] == scale], key=lambda r: r['year'])
            summary.append(dict(field=field, scale=scale, flow_growth_pct=growth([r['flow_events'] for r in rows]),
                                equivalent_growth_pct=growth([r['equivalent'] for r in rows]),
                                normalized_growth_pct=growth([r['normalized_equivalent'] for r in rows]),
                                normalized_slope_pp=100 * slope([r['normalized_equivalent'] for r in rows]),
                                Gini_slope_pp=100 * slope([r['Gini'] for r in rows]),
                                country_sample_n=len(cohort) if scale == 'domestic_city' else 0))
            baseline = np.mean([r['normalized_equivalent'] for r in rows if r['year'] <= 2004])
            for start, end in PERIODS:
                chunk = [r for r in rows if start <= r['year'] <= end]
                mean = float(np.mean([r['normalized_equivalent'] for r in chunk]))
                periods.append(dict(field=field, scale=scale, start_year=start, end_year=end, years=len(chunk),
                                    normalized_mean=mean, baseline_mean=float(baseline), index=100 * mean / baseline))
        values = np.array([r['Gini_slope_pp'] for r in trend_rows])
        q1, median, q3 = np.quantile(values, [.25, .5, .75])
        iqr = q3 - q1
        within = values[(values >= q1 - 1.5 * iqr) & (values <= q3 + 1.5 * iqr)]
        boxes.append(dict(field=field, countries=len(cohort), q1=float(q1), median=float(median), q3=float(q3),
                          whisker_low=float(within.min()), whisker_high=float(within.max()),
                          minimum=float(values.min()), maximum=float(values.max()),
                          countries_Gini_increasing=int(sum(values > 0)),
                          countries_joint_concentration=sum(r['Gini_slope_pp'] > 0 and r['normalized_slope_pp'] < 0 for r in trend_rows)))
    write('Fig6_country_annual_metrics.csv', international)
    write('Fig6_domestic_country_year_metrics.csv', retained)
    write('Fig6_domestic_country_trends.csv', country_trends)
    write('Fig6_field_annual_data.csv', annual)
    write('Fig6_field_trends.csv', summary)
    write('Fig6_domestic_country_samples.csv', samples)
    write('Fig6_period_indices.csv', periods)
    write('Fig6_country_trend_boxes.csv', boxes)
    manifest = dict(source=str(SOURCE.relative_to(ROOT)), source_sha256=sha256(SOURCE),
                    fields=fields, excluded_fields=['Unknown'], field_event_totals=field_totals,
                    years=YEARS.tolist(), domestic_universe=countries, domestic_cohorts=cohorts,
                    domestic_country_years_before_continuity_filter=len(domestic),
                    domestic_country_years_retained=len(retained), domestic_city_margin_rows=margin_count,
                    country_field_annual_records=len(international), field_country_trends=len(country_trends),
                    cohort_rule='Within the existing 76-country pool, retain field-country pairs with >=2 positive combined-strength cities in every year 1998–2025',
                    metric_policy='Combine inflow and outflow at each country or stable city before computing indices; never average directional indices',
                    event_policy='Each international or domestic event counted once for volume; combined margin sums equal twice event totals',
                    auxiliary_period_indices='Country combined-strength evenness; median within-country combined-strength city evenness for fixed field-specific cohorts; four seven-year means indexed to 1998–2004=100',
                    box_policy='Country-specific OLS Gini slopes from 28 annual values; box=25th–75th percentiles, line=median, whiskers=observed extrema within 1.5 IQR',
                    summary=dict(fields_with_international_flow_growth=sum(r['flow_growth_pct'] > 0 for r in summary if r['scale'] == 'country'),
                                 fields_with_domestic_flow_growth=sum(r['flow_growth_pct'] > 0 for r in summary if r['scale'] == 'domestic_city'),
                                 fields_with_positive_domestic_median_Gini_trend=sum(r['median'] > 0 for r in boxes)),
                    source_data_sha256={p.name: sha256(p) for p in DATA.glob('Fig6_*.csv')})
    (QA / 'data_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(fields=len(fields), cohort_range=[min(map(len, cohorts.values())), max(map(len, cohorts.values()))],
                          country_trends=len(country_trends), summary=manifest['summary']), ensure_ascii=False))


if __name__ == '__main__':
    prepare()
    prepare_stacked_panels()
