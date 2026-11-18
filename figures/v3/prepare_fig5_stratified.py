"""Prepare full-period international-share groups and domestic urban trends."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tmp/nhb_fig2_python_deps'))
import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATA = OUT / 'source_data'
QA = OUT / 'QA/Fig5'
CLEAN = ROOT / 'data/processed/mobility_city_harmonized_20261020/analysis'


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(name, rows):
    with (DATA / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def prepare():
    annual = read(DATA / 'Fig5_combined_country_year_metrics.csv')
    countries = sorted({r['country'] for r in annual})
    assert len(countries) == 76 and len(annual) == 2128
    totals = defaultdict(float)
    focal = defaultdict(float)
    margins = read(CLEAN / 'country_annual_margins.csv')
    for r in margins:
        year = int(r['year'])
        totals[year] += float(r['flow'])
        focal[r['country'], year] += float(r['flow'])
    observations, trends = [], []
    for cc in countries:
        rows = sorted((r for r in annual if r['country'] == cc), key=lambda r: int(r['year']))
        years = np.array([int(r['year']) for r in rows])
        assert np.array_equal(years, np.arange(1998, 2026))
        flows = np.array([float(r['international_flow']) for r in rows])
        assert np.all(flows > 0)
        assert np.allclose(flows, [focal[cc, int(y)] for y in years])
        shares = flows / np.array([totals[int(y)] for y in years])
        gini = np.array([float(r['domestic_Gini']) for r in rows])
        hhi = np.array([float(r['domestic_HHI']) for r in rows])
        share_fit = stats.linregress(years - 1998, np.log(shares))
        gini_fit = stats.linregress(years - 1998, gini)
        hhi_fit = stats.linregress(years - 1998, np.log(hhi))
        trends.append(dict(country=cc, years=28,
            international_share_log_slope=share_fit.slope,
            international_share_annual_rate_pct=float(100 * np.expm1(share_fit.slope)),
            domestic_gini_trend_pp_decade=float(1000 * gini_fit.slope),
            domestic_hhi_annual_rate_pct=float(100 * np.expm1(hhi_fit.slope)),
            first_international_share=float(shares[0]), last_international_share=float(shares[-1])))
        for j, r in enumerate(rows):
            observations.append(dict(country=cc, year=int(years[j]), international_flow=float(flows[j]),
                global_combined_international_flow=totals[int(years[j])], international_share=float(shares[j]),
                domestic_Gini=float(gini[j]), domestic_HHI=float(hhi[j])))
    rates = np.array([r['international_share_annual_rate_pct'] for r in trends])
    cuts = np.quantile(rates, [.25, .50, .75], method='linear')
    assert np.all(np.diff(cuts) > 0)
    for r in trends:
        r['group'] = int(np.searchsorted(cuts, r['international_share_annual_rate_pct'], side='right') + 1)
    groups = []
    for group in range(1, 5):
        rows = [r for r in trends if r['group'] == group]
        vals = np.array([r['domestic_gini_trend_pp_decade'] for r in rows])
        assert len(rows) == 19
        groups.append(dict(group=group, countries=len(rows),
            international_rate_min=min(r['international_share_annual_rate_pct'] for r in rows),
            international_rate_max=max(r['international_share_annual_rate_pct'] for r in rows),
            gini_trend_median=float(np.median(vals)), gini_trend_mean=float(vals.mean()),
            gini_trend_q25=float(np.quantile(vals, .25)), gini_trend_q75=float(np.quantile(vals, .75)),
            gini_increasing=int((vals > 0).sum()), gini_decreasing=int((vals < 0).sum()),
            country_codes=' '.join(r['country'] for r in rows)))
    write('Fig5_stratified_annual_observations.csv', observations)
    write('Fig5_stratified_country_trends.csv', trends)
    write('Fig5_stratified_groups.csv', groups)
    manifest = dict(countries=76, country_years=2128, years=[1998, 2025], quartile_cuts=cuts.tolist(),
        grouping='Quartiles of fitted annual relative change in a country share of worldwide international mobility',
        international_rate='100 * (exp(slope(ln(international_flow/global_combined_international_flow) ~ year)) - 1)',
        domestic_trend='1000 * slope(domestic combined-city Gini ~ year), Gini percentage points per decade',
        denominator='Sum of international inflow and outflow margins over ALL countries each year, not only the 76-country panel',
        exclusions='No additional exclusions within the established 76-country panel; all 28 years are used for every country',
        inferential_boundary='International share gains/losses are country trajectories, not country-specific global deconcentration indices',
        groups=groups,
        inputs=[dict(file=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                for path in [DATA/'Fig5_combined_country_year_metrics.csv', CLEAN/'country_annual_margins.csv']])
    (QA / 'stratified_data_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(dict(cuts=cuts.tolist(), groups=groups), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    prepare()
