from pathlib import Path
import collections
import csv
import hashlib
import json
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np

QA = Path(__file__).parent
DATA = REPO / 'figures/v3/source_data'
SOURCE = REPO / 'data/processed/mobility_city_harmonized_20261020/analysis/domestic_city_margins.csv'

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))

def save(name, records):
    with (QA / name).open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)

def metrics(values):
    values = np.sort(np.asarray(list(values), dtype=float))
    n = len(values)
    total = float(values.sum())
    shares = values / total
    hhi = float(np.dot(shares, shares))
    gini = float(2 * np.dot(np.arange(1, n + 1), values) / (n * total) - (n + 1) / n)
    return n, hhi, 1 / hhi, 1 / (n * hhi), gini

def slope(values):
    years = np.arange(1998, 2026, dtype=float)
    values = np.asarray(values, dtype=float)
    centered = years - years.mean()
    return float(np.dot(centered, values - values.mean()) / np.dot(centered, centered))

base = read(DATA / 'Fig4_all_country_combined_metrics.csv')
countries = sorted({row['country'] for row in base})
baseline = {(row['country'], int(row['year'])): row for row in base}
country_sql = ','.join("'" + country + "'" for country in countries)
connection = duckdb.connect()
connection.execute('SET threads=4')
rows = connection.execute(f"""
    SELECT country, year, city_id, sum(flow)
    FROM read_csv_auto('{SOURCE.as_posix()}')
    WHERE flow > 0 AND year BETWEEN 1998 AND 2025
      AND country IN ({country_sql})
    GROUP BY ALL ORDER BY ALL
""").fetchall()
connection.close()

by_country = collections.defaultdict(lambda: collections.defaultdict(dict))
first_year = {}
city_years = collections.Counter()
for country, year, city, value in rows:
    by_country[country][year][city] = float(value)
    first_year[country, city] = min(year, first_year.get((country, city), year))
    city_years[country, city] += 1

fixed_annual, cohort_annual, fixed_trends = [], [], []
for country, years in sorted(by_country.items()):
    assert len(years) == 28
    fixed = {city for (cc, city), n in city_years.items() if cc == country and n == 28}
    country_fixed = []
    for year, cities in sorted(years.items()):
        n, hhi, equivalent, normalized, gini = metrics(cities.values())
        expected = baseline[country, year]
        assert n == int(expected['N'])
        assert abs(hhi - float(expected['HHI'])) < 1e-10
        assert abs(gini - float(expected['Gini'])) < 1e-10
        later = {city: value for city, value in cities.items() if first_year[country, city] > 1998}
        cohort_annual.append(dict(
            country=country, year=year, N=n,
            post1998_cities=len(later), post1998_count_share=len(later) / n,
            post1998_flow_share=sum(later.values()) / sum(cities.values())))
        if len(fixed) >= 2:
            nf, hf, eqf, rf, gf = metrics(cities[city] for city in fixed)
            record = dict(
                country=country, year=year, N_fixed=nf, HHI=hf,
                equivalent_cities=eqf, normalized_equivalent_cities=rf, Gini=gf,
                city_strength_coverage=sum(cities[city] for city in fixed) / sum(cities.values()))
            fixed_annual.append(record)
            country_fixed.append(record)
    if country_fixed:
        rs = slope([row['normalized_equivalent_cities'] for row in country_fixed])
        gs = slope([row['Gini'] for row in country_fixed])
        category = ('Deconcentration' if rs > 0 and gs < 0 else
                    'Relative concentration' if rs < 0 and gs > 0 else 'Mixed changes')
        fixed_trends.append(dict(
            country=country, N_fixed=len(fixed), normalized_slope_pp_year=rs * 100,
            Gini_slope_pp_year=gs * 100, category=category,
            coverage_1998=country_fixed[0]['city_strength_coverage'],
            coverage_2025=country_fixed[-1]['city_strength_coverage']))

save('combined_fixed_city_annual.csv', fixed_annual)
save('combined_fixed_city_trends.csv', fixed_trends)
save('combined_post1998_city_cohort.csv', cohort_annual)
last = [row for row in cohort_annual if row['year'] == 2025]
post = [row for row in cohort_annual if row['year'] > 1998]
summary = dict(
    source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    combined_country_year_metrics_reconciled=len(baseline), countries=len(countries),
    fixed_city_countries=len(fixed_trends),
    fixed_city_categories=dict(collections.Counter(row['category'] for row in fixed_trends)),
    fixed_city_median_count=float(np.median([row['N_fixed'] for row in fixed_trends])),
    fixed_median_coverage_1998=float(np.median([row['coverage_1998'] for row in fixed_trends])),
    fixed_median_coverage_2025=float(np.median([row['coverage_2025'] for row in fixed_trends])),
    post1998_2025_median_city_count_share=float(np.median([row['post1998_count_share'] for row in last])),
    post1998_2025_median_city_flow_share=float(np.median([row['post1998_flow_share'] for row in last])),
    country_years_post1998=len(post),
    post1998_count_share_exceeds_flow_share=sum(row['post1998_count_share'] > row['post1998_flow_share'] for row in post))
(QA / 'combined_city_checks.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary, indent=2))
