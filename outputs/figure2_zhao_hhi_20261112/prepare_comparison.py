"""Matched five-year national-share HHI from BRIDGE and Zhao et al. (2023).

Pool flows before computing HHI. Preserve full-network margins, then select a
fixed country pool. This is a new calculation from the published OD data, not
the complement of the paper's country-specific migration-spread measure.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import urllib.request

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATA = OUT / 'source_data'
CURRENT = ROOT / 'figures/v4/source_data/Fig3_combined_country_year_data.csv'
SCOPE = ROOT / 'results/figure_revision_20261015/unified_country_scope/data_manifest.json'
BASE_URL = ('https://raw.githubusercontent.com/zxy919781142/'
            'A-gender-perspective-on-the-global-migration-of-scholars/main/')
REMOTE_FILES = {
    'Zhao2023_OD.csv': 'Aggregated_Academic_Migration_Data/0_OD_migration_flow.csv',
    'Zhao2023_country_margins.csv': 'Aggregated_Academic_Migration_Data/0_gendered_net_migration_all.csv',
    'Zhao2023_README.md': 'README.md',
}
PERIODS = [(1998, 2002), (2003, 2007), (2008, 2012), (2013, 2017)]
# Repair missing/non-ISO codes in the author's labels, without changing places.
ISO_REPAIRS = {
    'Bonaire, Saint Eustatius and Saba': 'BQ', 'Curacao': 'CW',
    'Kosovo': 'XK', 'Namibia': 'NA', 'Palestinian Territory': 'PS',
    'Reunion': 'RE', 'Sint Maarten': 'SX', 'Timor Leste': 'TL', 'Vatican': 'VA',
}


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def write(name, rows):
    assert rows
    with (DATA / name).open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    for name, remote in REMOTE_FILES.items():
        path = DATA / name
        if not path.exists():
            with urllib.request.urlopen(BASE_URL + remote, timeout=30) as response:
                path.write_bytes(response.read())

    scope_map = json.loads(SCOPE.read_text(encoding='utf-8'))['country_mapping']
    labels = {}
    published_margins = read(DATA / 'Zhao2023_country_margins.csv')
    for row in published_margins:
        name, code = row['residenceCountry'].strip(), row['iso2'].strip()
        code = ISO_REPAIRS.get(name, code)
        assert len(code) == 2 and code.isalpha(), (name, code)
        if name in labels:
            assert labels[name] == code, name
        labels[name] = code
    write('country_mapping.csv', [dict(source_country=name, iso2=code,
          matched_unit=scope_map.get(code, code), iso_code_repaired=name in ISO_REPAIRS)
          for name, code in sorted(labels.items())])

    # Each pair of values is [inflow, outflow].
    panels = {source: defaultdict(lambda: defaultdict(lambda: [0., 0.]))
              for source in ['BRIDGE', 'Zhao2023']}
    unaligned = defaultdict(lambda: defaultdict(lambda: [0., 0.]))
    removed_rows = Counter()
    removed_weights = Counter()
    raw_weights = Counter()
    raw_rows = read(DATA / 'Zhao2023_OD.csv')
    assert len(raw_rows) == 23412
    keys = set()
    for row in raw_rows:
        period = int(float(row['period']))
        lo, hi = PERIODS[period - 1]
        assert row['period_year'] == f'{lo}-{hi}'
        origin, destination = row['from'].strip(), row['to'].strip()
        assert origin in labels and destination in labels
        weight = float(row['all_period_flow'])
        assert np.isfinite(weight) and weight > 0 and origin != destination
        key = (period, origin, destination)
        assert key not in keys, key
        keys.add(key)
        raw_weights[period] += weight
        unaligned[period][origin][1] += weight
        unaligned[period][destination][0] += weight
        origin = scope_map.get(labels[origin], labels[origin])
        destination = scope_map.get(labels[destination], labels[destination])
        if origin == destination:
            removed_rows[period] += 1
            removed_weights[period] += weight
            continue
        panels['Zhao2023'][period][origin][1] += weight
        panels['Zhao2023'][period][destination][0] += weight

    # Verify that the OD inputs reproduce the author's separate national totals.
    for row in published_margins:
        period, name = int(row['period']), row['residenceCountry'].strip()
        actual = unaligned[period][name]
        assert np.allclose(actual, [float(row['inflow_period']),
                                   float(row['outflow_period'])], rtol=0, atol=0), (period, name)
    assert list(raw_weights.values()) == [155445., 183315., 247253., 302685.]

    annual_rows = read(CURRENT)
    current_snapshot = []
    for row in annual_rows:
        year = int(row['year'])
        if not 1998 <= year <= 2017:
            continue
        period = 1 + (year - 1998) // 5
        country = row['country']
        assert scope_map.get(country, country) == country
        inflow, outflow = float(row['inflow']), float(row['outflow'])
        assert min(inflow, outflow) >= 0
        assert np.isclose(float(row['combined_flow']), inflow + outflow)
        panels['BRIDGE'][period][country][0] += inflow
        panels['BRIDGE'][period][country][1] += outflow
        current_snapshot.append(dict(year=year, country=country,
                                     inflow=inflow, outflow=outflow))
    write('BRIDGE_annual_country_margins_1998_2017.csv', current_snapshot)

    country_sets = [set(country for country, value in panels[source][period].items()
                        if sum(value) > 0)
                    for source in panels for period in range(1, 5)]
    pool = sorted(set.intersection(*country_sets))
    assert len(pool) > 100
    pool_set = set(pool)
    full_margins, matched_margins, comparison, coverage = [], [], [], []
    for source, periods in panels.items():
        for period in range(1, 5):
            countries = periods[period]
            inflow = sum(v[0] for v in countries.values())
            outflow = sum(v[1] for v in countries.values())
            assert inflow == outflow and inflow > 0
            combined_total = inflow + outflow
            selected = sum(sum(countries[c]) for c in pool)
            for country, value in sorted(countries.items()):
                full_margins.append(dict(source=source, period=period, country=country,
                    inflow=value[0], outflow=value[1], combined_flow=sum(value),
                    in_matched_pool=country in pool_set))
            for country in pool:
                value = countries[country]
                matched_margins.append(dict(source=source, period=period, country=country,
                    inflow=value[0], outflow=value[1], combined_flow=sum(value),
                    share=sum(value) / selected))
            values = np.array([sum(countries[c]) for c in pool])
            shares = values / values.sum()
            assert np.all(shares > 0) and np.isclose(shares.sum(), 1.)
            hhi = float(shares @ shares)
            assert 1. / len(pool) <= hhi <= 1.
            lo, hi = PERIODS[period - 1]
            comparison.append(dict(source=source, period=period, period_start=lo,
                period_end=hi, midpoint=(lo+hi)/2, countries=len(pool),
                combined_flow_sum=float(values.sum()), HHI=hhi))
            coverage.append(dict(source=source, period=period,
                full_network_countries=len(countries), matched_countries=len(pool),
                full_network_event_weight=inflow, matched_strength_fraction=selected/combined_total,
                excluded_units=';'.join(sorted(set(countries)-pool_set))))
    summaries = {}
    for source in panels:
        rows = [r for r in comparison if r['source'] == source]
        baseline = rows[0]['HHI']
        for row in rows:
            row['index_first_period_100'] = 100 * row['HHI'] / baseline
        summaries[source] = dict(first_HHI=baseline, last_HHI=rows[-1]['HHI'],
            endpoint_decline_percent=100 * (1 - rows[-1]['HHI'] / baseline))
    write('period_HHI_comparison.csv', comparison)
    write('full_network_country_margins.csv', full_margins)
    write('matched_country_margins.csv', matched_margins)
    write('coverage.csv', coverage)
    write('matched_countries.csv', [dict(country=c) for c in pool])
    provenance = dict(
        comparison='Recomputed global country-share HHI from Zhao et al. (2023) public OD flows',
        DOI='10.1073/pnas.2214664120', retrieved_date='2026-11-12',
        metric='HHI of combined inflow-plus-outflow national shares, computed after pooling five years',
        sources={name: dict(url=BASE_URL+remote, sha256=sha(DATA/name))
                 for name, remote in REMOTE_FILES.items()},
        current_input=str(CURRENT.relative_to(ROOT)), current_input_sha256=sha(CURRENT),
        geographic_scope_source=str(SCOPE.relative_to(ROOT)), geographic_scope_sha256=sha(SCOPE),
        country_scope_mapping=scope_map, iso_repairs=ISO_REPAIRS,
        raw_OD_rows=len(raw_rows), raw_event_weight=dict(raw_weights),
        removed_within_aggregated_unit_rows=dict(removed_rows),
        removed_within_aggregated_unit_weight=dict(removed_weights),
        pool_rule='Same units with positive combined flow in both sources in all four periods; full-network margins retained before selection and renormalization',
        matched_countries=len(pool), country_pool=pool, periods=PERIODS,
        summaries=summaries,
        interpretation='Descriptive cross-source comparison; affiliation-change and migration-event definitions remain source-specific; no hypothesis test or CI estimated',
        distinction='Not 1 minus the paper\'s country-specific migration spread; no annual observations invented',
    )
    provenance['derived_file_sha256'] = {p.name: sha(p) for p in DATA.glob('*.csv')}
    (DATA/'comparison_provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    print(json.dumps(dict(countries=len(pool), summaries=summaries,
          removed_within_unit_weights=dict(removed_weights), coverage=coverage), indent=2))


if __name__ == '__main__':
    main()
