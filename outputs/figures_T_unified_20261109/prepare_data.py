"""Use the existing Fig3--5 country assignments for Fig1 and Fig2.

Country values and histogram bins are preserved; descriptive KDEs and group
summaries are recomputed after reassignment, with the same absolute bandwidth.
"""
from pathlib import Path
import csv
import hashlib
import json
import shutil
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
OLD=ROOT/'outputs/fig1_histogram_fig2_labels_20261109'
DATA=OUT/'source_data'
DATA.mkdir(parents=True,exist_ok=True)

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as h:return list(csv.DictReader(h))

def write(name,rows):
    with (DATA/name).open('w',encoding='utf-8-sig',newline='') as h:
        w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

for rel in ['outputs/fig1_histogram_fig2_labels_20261109/plot_Fig1.py',
            'outputs/fig1_histogram_fig2_labels_20261109/plot_Fig2.py',
            'outputs/paper_final/introduction.tex','outputs/paper_final/results.tex',
            'outputs/paper_final/methods.tex','scripts/plots/paper_figures/manifest.json',
            *[f'outputs/paper_final/figures/Fig{n}.{e}' for n in [1,2] for e in ['pdf','svg','png']]]:
    p=ROOT/rel;target=OUT/'before'/rel;target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():shutil.copy2(p,target)

canonical=ROOT/'outputs/results_network_revision_20261030/artwork/source_data/trajectory_membership.csv'
shutil.copy2(canonical,DATA/'trajectory_membership.csv')
members=read(canonical);membership={r['country']:r for r in members}
original=read(OLD/'source_data/Fig2_quartile_country_trends.csv')
assert len(members)==len(original)==76 and set(membership)=={r['country'] for r in original}
rates=np.array([float(r['international_share_annual_rate_pct']) for r in members])
cuts=np.array([np.median(rates[rates<0]),0.,np.median(rates[rates>0])])
assert np.all(rates!=0)
counts=[sum(int(r['group'])==q for r in members) for q in range(1,5)]
assert counts==[15,14,24,23]
trends=[]
for r in original:
    m=membership[r['country']]
    assert np.isclose(float(r['international_share_annual_rate_pct']),float(m['international_share_annual_rate_pct']),atol=1e-10,rtol=0)
    expected=int(np.searchsorted(cuts,float(m['international_share_annual_rate_pct']),side='left')+1)
    assert int(m['group'])==expected
    new=dict(r,group=int(m['group']),international_share_log_slope=float(m['international_share_log_slope']),
             international_share_annual_rate_pct=float(m['international_share_annual_rate_pct']))
    trends.append(new)
write('Fig2_T_country_trends.csv',trends)
assert all(a['domestic_gini_trend_pp_decade']==b['domestic_gini_trend_pp_decade'] for a,b in zip(original,trends))

# Cross-check the frozen Fig4 and Fig3 group assignments country by country.
fig4=read(ROOT/'outputs/fig2_split_20261102/before/source_data/Fig2_quartile_country_growth.csv')
fig3=read(ROOT/'outputs/results_caption_alignment_20261031/artwork/source_data/Fig3_Fig5_quartile_membership.csv')
for rows in [fig3,fig4]:
    assert len(rows)==76 and all(int(r['group'])==int(membership[r['country']]['group']) for r in rows)

groups=[]
for q in range(1,5):
    rows=[r for r in trends if r['group']==q]
    vals=np.array([float(r['domestic_gini_trend_pp_decade']) for r in rows])
    g=np.array([float(r['international_share_annual_rate_pct']) for r in rows])
    groups.append(dict(group=q,countries=len(rows),international_rate_min=float(g.min()),international_rate_max=float(g.max()),
        gini_trend_median=float(np.median(vals)),gini_trend_mean=float(vals.mean()),
        gini_trend_q25=float(np.quantile(vals,.25)),gini_trend_q75=float(np.quantile(vals,.75)),
        gini_increasing=int(sum(vals>0)),gini_decreasing=int(sum(vals<0)),
        country_codes=' '.join(sorted(r['country'] for r in rows))))
write('Fig2_T_groups.csv',groups)

hist=read(OLD/'source_data/Fig2_quartile_histogram.csv')
edges=np.r_[[float(r['lower']) for r in hist],float(hist[-1]['upper'])]
assert np.array_equal(np.histogram(rates,bins=edges)[0],[int(r['countries']) for r in hist])
shutil.copy2(OLD/'source_data/Fig2_quartile_histogram.csv',DATA/'Fig2_T_histogram.csv')

old_density=read(OLD/'source_data/Fig2_quartile_density_curves.csv')
bandwidth=float(old_density[0]['bandwidth'])
assert np.allclose([float(r['bandwidth']) for r in old_density],bandwidth)
xx=np.array([float(r['x']) for r in old_density if int(r['group'])==1])
assert len(xx)==401 and np.all(np.diff(xx)>0)
density=[]
for q in range(1,5):
    vals=np.array([float(r['domestic_gini_trend_pp_decade']) for r in trends if r['group']==q])
    yy=np.exp(-.5*((xx[:,None]-vals[None,:])/bandwidth)**2).mean(axis=1)/(bandwidth*np.sqrt(2*np.pi))
    density.extend(dict(panel='defg'[q-1],group=q,x=float(x),density=float(y),bandwidth=bandwidth) for x,y in zip(xx,yy))
write('Fig2_T_density_curves.csv',density)

# Keep every country's x value and display-only vertical position unchanged.
old_strip=read(OLD/'source_data/Fig2_quartile_country_strip.csv')
assert len(old_strip)==76 and {r['country'] for r in old_strip}==set(membership)
strip=[]
for r in old_strip:
    q=int(membership[r['country']]['group'])
    strip.append(dict(panel='defg'[q-1],country=r['country'],group=q,x=r['x'],display_y=r['display_y']))
write('Fig2_T_country_strip.csv',strip)
for name in ['Fig2_growth_reference.csv','Fig2_coverage_display_curves.csv']:
    shutil.copy2(OLD/'source_data'/name,DATA/name)

provenance=dict(countries=76,country_years=2128,years=[1998,2025],
    group_cuts_pct_per_year=cuts.tolist(),countries_per_group=counts,
    grouping='Sign of fitted international-share growth, followed by median within each sign group; ties to T1 or T3',
    labels=['Faster decline','Slower decline','Slower growth','Faster growth'],
    source_membership=str(canonical.relative_to(ROOT)),source_membership_sha256=sha(canonical),
    domestic_country_values_source='Previous frozen 76-country full-period domestic Gini trends',
    domestic_country_values_source_sha256=sha(OLD/'source_data/Fig2_quartile_country_trends.csv'),
    kde_bandwidth=bandwidth,kde_policy='Same fixed absolute Gaussian bandwidth and 401-point grid in every group; each country equally weighted within its new group',
    histogram_bins_unchanged=22,all_country_values_retained=True,groups=groups)
(DATA/'Fig2_T_provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
print(json.dumps(dict(countries_per_group=counts,cuts=cuts.tolist(),medians=[r['gini_trend_median'] for r in groups],bandwidth=bandwidth)))
