"""Four pooled disciplinary domains: distributions and matched annual changes.

Real cleaned event data only. Python/matplotlib exports preserve editable text.
The 45-country common sample and all 28 years are used without visual sampling.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
SOURCE_DIR = ROOT / 'results/disciplinary_domains_20261022'
sys.path[:0] = [str(ROOT / 'figures/v3'),
                str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa')]
import numpy as np
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from audit_panel_alignment import require_matplotlib_panel_alignment
import pymupdf
from figure_style import PROFILE, specification, apply_light_grids,apply_nhb_typography
from figure_palette import BLUE, RED, GREEN, YELLOW

OUT = BASE / 'artwork'
DATA = OUT / 'source_data'
QA = OUT.parent / 'QA/Fig6'
DOMAINS = ['Physical Sciences', 'Life Sciences', 'Health Sciences', 'Social Sciences']
LABELS = {'Physical Sciences': 'Physical\nSciences', 'Life Sciences': 'Life\nSciences',
          'Health Sciences': 'Health\nSciences', 'Social Sciences': 'Social\nSciences'}
COLORS = dict(zip(DOMAINS, [BLUE, GREEN, RED, YELLOW]))
YEARS = np.arange(1998, 2026)
TIME = YEARS - YEARS.mean()
WIDTH, HEIGHT = 180 / 25.4 * 72, 140 / 25.4 * 72
LOWER_POINT_SIZE = 18.
LOWER_POINT_ALPHA = .90
SWARM_POINT_SIZE = 7.
SWARM_POINT_ALPHA = .90
ANNUAL_LINEWIDTH = 2.
LOWER_X_LIMITS = (-1., 18.5)


def read(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.DictReader(handle))


def write(name, rows):
    assert rows
    with (DATA / name).open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def slope_pp(values):
    a = np.asarray(values, dtype=float)
    assert a.shape == (28,) and np.all(np.isfinite(a))
    return float(100 * (TIME @ a) / (TIME @ TIME))


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def prepare():
    manifest = json.loads((SOURCE_DIR / 'manifest.json').read_text(encoding='utf8'))
    source_path = ROOT / manifest['source']
    assert sha256(source_path) == manifest['source_sha256'], 'Cleaned input has changed; recompute domain data.'
    cohort = sorted(manifest['common_countries'])
    assert len(cohort) == 45
    taxonomy = read(SOURCE_DIR / 'field_domain_mapping.csv')
    assert len(taxonomy) == 26 and set(r['domain'] for r in taxonomy) == set(DOMAINS)
    country = read(SOURCE_DIR / 'domain_country_annual_metrics.csv')
    domestic_all = read(SOURCE_DIR / 'domain_domestic_country_annual_metrics.csv')
    domestic = [r for r in domestic_all if r['country'] in cohort]
    assert len(country) == 112 and len(domestic) == 4 * 45 * 28
    C = {(r['domain'], int(r['year'])): r for r in country}
    U = {(r['domain'], r['country'], int(r['year'])): r for r in domestic}
    assert len(C) == 112 and len(U) == 5040
    national, country_slopes, annual, changes, summaries = [], [], [], [], []
    for domain in DOMAINS:
        cg = np.array([float(C[domain, int(y)]['Gini']) for y in YEARS])
        national.append(dict(domain=domain, Gini_slope_pp=slope_pp(cg), years=28,
                             first_year=1998, last_year=2025))
        matrix = np.array([[float(U[domain, code, int(y)]['Gini']) for y in YEARS] for code in cohort])
        assert all(int(U[domain, code, int(y)]['N']) >= 2 for code in cohort for y in YEARS)
        differences = (matrix - matrix[:, :1]) * 100
        quantiles = np.quantile(differences, [.25, .5, .75], axis=0)
        gs = []
        for code, vals, diff in zip(cohort, matrix, differences):
            metric = slope_pp(vals)
            norm = slope_pp([float(U[domain, code, int(y)]['normalized_equivalent']) for y in YEARS])
            gs.append(metric)
            category = ('concentration' if metric > 0 and norm < 0 else
                        'deconcentration' if metric < 0 and norm > 0 else 'mixed')
            country_slopes.append(dict(domain=domain, country=code, Gini_slope_pp=metric,
                                       normalized_equivalent_slope_pp=norm, category=category))
            for year, value in zip(YEARS, diff):
                changes.append(dict(domain=domain, country=code, year=int(year), Gini_change_pp=float(value)))
        qs = np.quantile(gs, [.25, .5, .75])
        summaries.append(dict(domain=domain, countries=45, domestic_Gini_slope_q1=float(qs[0]),
                              domestic_Gini_slope_median=float(qs[1]), domestic_Gini_slope_q3=float(qs[2]),
                              positive_Gini_countries=int(np.sum(np.array(gs) > 0)),
                              joint_concentration_countries=sum(r['category'] == 'concentration' for r in country_slopes if r['domain'] == domain),
                              national_Gini_slope_pp=national[-1]['Gini_slope_pp']))
        for j, year in enumerate(YEARS):
            annual.append(dict(domain=domain, year=int(year), countries=45,
                               country_Gini=float(cg[j]), country_Gini_change_pp=float((cg[j]-cg[0])*100),
                               domestic_change_q1_pp=float(quantiles[0, j]),
                               domestic_change_median_pp=float(quantiles[1, j]),
                               domestic_change_q3_pp=float(quantiles[2, j])))
    for name, rows in [('Fig5_field_domain_mapping.csv', taxonomy),
                       ('Fig5_country_annual_metrics.csv', country),
                       ('Fig5_domestic_country_annual_metrics.csv', domestic),
                       ('Fig5_national_trends.csv', national),
                       ('Fig5_domestic_country_trends.csv', country_slopes),
                       ('Fig5_annual_changes.csv', annual),
                       ('Fig5_country_year_changes.csv', changes),
                       ('Fig5_summary.csv', summaries)]:
        write(name, rows)
    return manifest, cohort, national, country_slopes, annual, summaries



def packed_y(values, row, ax, minimum_distance_pt=2.65):
    """Pack vertically in physical units; retain each measured x exactly."""
    scale = ax.figure.dpi / 72
    candidates = [0.]
    for delta in np.arange(.045, .406, .045):
        candidates.extend([float(delta), -float(delta)])
    placed, result = [], {}
    for index in np.argsort(values, kind='stable'):
        valid = []
        for offset in candidates:
            pt = ax.transData.transform((values[index], row + offset)) / scale
            clearance = min((np.linalg.norm(pt-p) for p in placed), default=1e6)
            if clearance >= minimum_distance_pt:
                valid.append((abs(offset), candidates.index(offset), offset, pt))
        assert valid, 'Expand the swarm; do not drop measurements.'
        _, _, offset, pt = min(valid, key=lambda x: x[:2])
        placed.append(pt)
        result[int(index)] = row + offset
    return np.array([result[i] for i in range(len(values))])


def coverage_pairs(domestic):
    from scipy.stats import spearmanr
    metrics = read(SOURCE_DIR/'domain_domestic_country_annual_metrics.csv')
    indexed = {(r['domain'], r['country'], int(r['year'])): r for r in metrics}
    pairs, fits, associations = [], [], []
    for j, domain in enumerate(DOMAINS):
        members = [r for r in domestic if r['domain'] == domain]
        current = []
        for member in members:
            counts = np.array([float(indexed[domain, member['country'], int(y)]['N']) for y in YEARS])
            assert counts.shape == (28,) and np.all(counts >= 2)
            beta = float(TIME @ np.log(counts) / (TIME @ TIME))
            current.append(dict(domain=domain, country=member['country'], panel=chr(99+j),
                city_count_growth_pct=float(100*np.expm1(beta)),
                Gini_slope_pp=float(member['Gini_slope_pp']),
                N_1998=int(counts[0]), N_2025=int(counts[-1])))
        assert len(current) == 45
        x = np.array([r['city_count_growth_pct'] for r in current])
        y = np.array([r['Gini_slope_pp'] for r in current])
        xx = np.linspace(float(x.min()), float(x.max()), 121)
        design = np.column_stack([np.ones(45), x])
        intercept, slope = np.linalg.lstsq(design, y, rcond=None)[0]
        rng = np.random.default_rng(61023+j)
        boot = []
        for _ in range(2000):
            selected = rng.integers(0, 45, 45)
            coeff = np.linalg.lstsq(design[selected], y[selected], rcond=None)[0]
            boot.append(coeff[0]+coeff[1]*xx)
        lo, hi = np.quantile(boot, [.025, .975], axis=0)
        for xv, lv, hv in zip(xx, lo, hi):
            fits.append(dict(domain=domain, panel=chr(99+j), x=float(xv),
                fit=float(intercept+slope*xv), lower=float(lv), upper=float(hv)))
        associations.append(dict(domain=domain, countries=45, spearman_rho=float(spearmanr(x,y).statistic),
            ols_intercept=float(intercept), ols_slope=float(slope), bootstrap_resamples=2000,
            seed=61023+j, positive_Gini_countries=int(sum(y>0)), positive_coverage_growth=int(sum(x>0))))
        pairs.extend(current)
    return pairs, fits, associations


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    provenance, cohort, national, domestic, annual, summaries = prepare()
    pairs, fits, associations = coverage_pairs(domestic)
    label_pt = 9. if PROFILE == 'manuscript' else 7.
    tick_pt = 8. if PROFILE == 'manuscript' else 6.5
    letter_pt = 10. if PROFILE == 'manuscript' else 8.
    mpl.rcParams.update({'font.family':'sans-serif', 'font.sans-serif':['Arial','Helvetica'],
        'pdf.use14corefonts':False, 'pdf.fonttype':42, 'svg.fonttype':'none',
        'font.size':tick_pt, 'axes.labelsize':label_pt, 'axes.linewidth':.55,
        'axes.spines.top':False, 'axes.spines.right':False, 'axes.unicode_minus':False,
        'text.color':'black', 'axes.labelcolor':'black', 'xtick.color':'black',
        'ytick.color':'black', 'legend.frameon':False, 'path.simplify':False,
        'savefig.facecolor':'white'})
    fig = plt.figure(figsize=(WIDTH/72, HEIGHT/72), dpi=300)
    axes = {}
    def panel(name, left, bottom, width, height):
        ax = fig.add_axes([left/WIDTH, bottom/HEIGHT, width/WIDTH, height/HEIGHT])
        ax.set_gid(name)
        ax.tick_params(length=2.5, width=.55, pad=3, labelsize=tick_pt)
        axes[name] = ax
        return ax
    def letter(name, x, y):
        fig.text(x/WIDTH, y/HEIGHT, name, fontweight='bold', fontsize=letter_pt,
            ha='left', va='baseline')

    a = panel('a', 44, 219, 166, 140)
    a.set(xlim=(-.45,2.95), ylim=(-.55,3.55))
    a.set_xticks([0,1,2])
    a.set_yticks([3,2,1,0], [LABELS[d] for d in DOMAINS])
    a.tick_params(axis='y', length=0, pad=6, labelsize=tick_pt)
    a.set_xlabel('Gini trend (pp/year)', labelpad=6)
    a.axvline(0, color='#A5AEB7', linewidth=.7, linestyle=(0,(2.5,2.5)), zorder=.5)
    for y in [.5,1.5,2.5]:
        a.axhline(y, color='#E5E7E9', linewidth=.5, zorder=.1)
    fig.canvas.draw()
    points, summary_marks = [], []
    for i, domain in enumerate(DOMAINS):
        row, color = 3-i, COLORS[domain]
        members = [r for r in domestic if r['domain'] == domain]
        x = np.array([r['Gini_slope_pp'] for r in members])
        y = packed_y(x, row+.05, a)
        a.scatter(x, y, s=SWARM_POINT_SIZE, facecolor=color, alpha=SWARM_POINT_ALPHA, edgecolors='none', zorder=3)
        for r, yy in zip(members, y):
            points.append(dict(r, panel='a', x=float(r['Gini_slope_pp']), y=float(yy), color=color))
        q1, med, q3 = np.quantile(x,[.25,.5,.75])
        a.plot([med,med],[row-.27,row+.37], color=color, linewidth=1.15, zorder=4)
        ng = next(r['Gini_slope_pp'] for r in national if r['domain']==domain)
        a.scatter([ng],[row-.30], s=21, marker='D', facecolor=color,
            edgecolors='black', linewidths=.55, zorder=5)
        summary_marks.append(dict(domain=domain, y=row-.30, q1=float(q1),
            median=float(med), q3=float(q3), national=float(ng)))
    a.legend(handles=[
        Line2D([],[],marker='D',markersize=4.2,markerfacecolor='#A5AEB7',markeredgecolor='black',
            markeredgewidth=.5,linestyle='none',label='International'),
        Line2D([],[],marker='o',markersize=3.2,markerfacecolor='#A5AEB7',markeredgecolor='none',
            linestyle='none',label='Domestic')],
        loc='lower left', bbox_to_anchor=(-.02,1.01), ncol=2, handlelength=.7,
        handletextpad=.4, columnspacing=1.0, borderaxespad=0, fontsize=tick_pt)

    b = panel('b', 254, 219, 252, 140)
    b.set(xlim=(1997.4, 2025.6), ylim=(-8, 22))
    b.set_xticks([1998, 2005, 2012, 2019, 2025])
    b.set_yticks([-5, 0, 5, 10, 15, 20])
    b.set_xlabel('Year', labelpad=6)
    b.set_ylabel('Gini change (pp)', labelpad=6)
    b.axhline(0, color='#A5AEB7', linewidth=.6, zorder=.5)
    international_style = (0, (3.5, 2.3))
    curve_values = []
    for domain in DOMAINS:
        vals = [r for r in annual if r['domain'] == domain]
        year = np.array([r['year'] for r in vals])
        international = np.array([r['country_Gini_change_pp'] for r in vals])
        domestic_median = np.array([r['domestic_change_median_pp'] for r in vals])
        b.plot(year, international, color=COLORS[domain], linestyle=international_style,
               linewidth=ANNUAL_LINEWIDTH, zorder=3)
        b.plot(year, domestic_median, color=COLORS[domain],
               linewidth=ANNUAL_LINEWIDTH, zorder=4)
        curve_values.extend(dict(r, color=COLORS[domain]) for r in vals)
    b.legend(handles=[
        Line2D([], [], color='#59616A', linestyle=international_style,
               linewidth=ANNUAL_LINEWIDTH, label='International'),
        Line2D([], [], color='#59616A', linewidth=ANNUAL_LINEWIDTH, label='Domestic')],
        loc='lower left', bbox_to_anchor=(0, 1.01), ncol=2, handlelength=2.2,
        handletextpad=.5, columnspacing=1.0, borderaxespad=0, fontsize=tick_pt)
    letter('a', 21, 369)
    letter('b', 231, 369)
    fig.legend(handles=[Line2D([],[],color=COLORS[d],linewidth=2,
        label=d.replace('Sciences','sciences')) for d in DOMAINS],
        loc='center',bbox_to_anchor=(.52,389/HEIGHT),ncol=4,frameon=False,
        handlelength=1.0,handletextpad=.4,columnspacing=1.0,fontsize=tick_pt)

    fit_lines = []
    for j,domain in enumerate(DOMAINS):
        name = chr(99+j)
        left = 44+j*119
        ax = panel(name,left,52,105,105)
        ax.set_box_aspect(1)
        ax.set(xlim=LOWER_X_LIMITS,ylim=(-.70,3.5))
        ax.set_xticks([0,5,10,15])
        ax.set_yticks([0,1,2])
        if j>0:
            ax.tick_params(labelleft=False)
        else:
            ax.set_ylabel('Gini trend (pp/year)',labelpad=7)
        ax.axhline(0,color='#A5AEB7',linewidth=.6,zorder=.5)
        current = [r for r in pairs if r['domain']==domain]
        ax.scatter([r['city_count_growth_pct'] for r in current],
            [r['Gini_slope_pp'] for r in current],s=LOWER_POINT_SIZE,facecolor=COLORS[domain],
            alpha=LOWER_POINT_ALPHA,edgecolors='none',zorder=3)
        prediction = [r for r in fits if r['domain']==domain]
        ax.fill_between([r['x'] for r in prediction],[r['lower'] for r in prediction],
            [r['upper'] for r in prediction],color=COLORS[domain],alpha=.14,linewidth=0,zorder=1)
        association = next(r for r in associations if r['domain']==domain)
        line_x = np.asarray([r['x'] for r in prediction])
        line_y = np.asarray([r['fit'] for r in prediction])
        ax.plot(line_x,line_y,
            color='#333333',linewidth=1.15,zorder=4)
        observed_min,observed_max = min(r['x'] for r in prediction),max(r['x'] for r in prediction)
        fit_lines.extend(dict(domain=domain,panel=name,x=float(x),fit=float(y),
            within_observed_range=bool(observed_min<=x<=observed_max)) for x,y in zip(line_x,line_y))
        rho = next(r['spearman_rho'] for r in associations if r['domain']==domain)
        fig.text((left+52.5)/WIDTH,162/HEIGHT,f'Spearman r = {rho:.2f}',
            ha='center',va='baseline',fontsize=tick_pt)
        fig.text((left+52.5)/WIDTH,174/HEIGHT,domain.replace('Sciences','sciences'),
            ha='center',va='baseline',fontsize=label_pt)
        letter(name,left-23,184)
    fig.text((44+506)/2/WIDTH,18/HEIGHT,
        'City count growth (%/year)',ha='center',fontsize=label_pt)

    apply_nhb_typography(fig)
    fig.canvas.draw()
    apply_light_grids(fig,json_out=QA/'grid.json')
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,axes=list(axes.values()),strict=True,
        json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',
        tolerance_pt=1.5,gutter_tolerance_pt=1.5,
        row_groups=[['a','b'],['c','d','e','f']],column_groups=[],
        exemptions=[dict(panels=['b'],checks=['panel-width'],
            reason='The annual comparison is wider to show eight series on one pair of axes.')])
    assert abs(axes['a'].get_position().x0-axes['c'].get_position().x0)*WIDTH < .01
    scale = fig.dpi/72
    for r in points:
        x,y = a.transData.transform((r['x'],r['y']))/scale
        r.update(pdf_x_pt=float(x),pdf_y_pt=float(HEIGHT-y))
    for r in pairs:
        x,y = axes[r['panel']].transData.transform((r['city_count_growth_pct'],r['Gini_slope_pp']))/scale
        r.update(pdf_x_pt=float(x),pdf_y_pt=float(HEIGHT-y))
    for r in summary_marks:
        x,y = a.transData.transform((r['national'],r['y']))/scale
        r.update(national_pdf_x_pt=float(x),national_pdf_y_pt=float(HEIGHT-y))
    write('Fig5_scatter_plotted_values.csv',points)
    write('Fig5_summary_marks.csv',summary_marks)
    write('Fig5_curve_plotted_values.csv',curve_values)
    write('Fig5_coverage_concentration_points.csv',pairs)
    write('Fig5_coverage_concentration_fits.csv',fits)
    write('Fig5_coverage_concentration_fit_lines.csv',fit_lines)
    write('Fig5_coverage_concentration_associations.csv',associations)
    rects = []
    for name,ax in axes.items():
        bb=ax.get_position()
        rects.append(dict(panel=name,bbox_pdf_pt=[bb.x0*WIDTH,HEIGHT-bb.y1*HEIGHT,
            bb.x1*WIDTH,HEIGHT-bb.y0*HEIGHT]))
    manifest = dict(figure='Fig6',version='v4',profile=PROFILE,dimensions_mm=[180,140],
        domains=DOMAINS,palette=COLORS,countries=cohort,country_sample_n=45,
        domestic_country_domain_points=180,national_diamonds=4,annual_values=112,
        annual_line_vertices=224,annual_domestic_country_values=5040,panels=rects,
        y_axes=6,source=provenance['source'],source_sha256=provenance['source_sha256'],
        source_tables_sha256={p.name:sha256(p) for p in SOURCE_DIR.glob('*.csv')},
        pooling=provenance['pooling_policy'],domestic_policy=provenance['domestic_policy'],
        typography=specification(),associations=associations,
        swarm_point_style=dict(size_pt2=SWARM_POINT_SIZE,alpha=SWARM_POINT_ALPHA),
        annual_linewidth_pt=ANNUAL_LINEWIDTH,
        lower_point_style=dict(size_pt2=LOWER_POINT_SIZE,alpha=LOWER_POINT_ALPHA),
        lower_annotation_placement='Spearman coefficients outside plot areas, below the domain titles.',
        shared_axis_xlim=list(LOWER_X_LIMITS),fit_line_within_observed_range=True,
        fit_policy='Original OLS coefficients, with lines and pointwise 95% country-bootstrap intervals restricted to the observed x range of each domain; all 45 countries retained and the same 2000 bootstrap resamples used.',
        annual_policy='Panel b shares one Year axis and one Gini change axis. International domain changes from 1998 are dashed. Domestic medians of changes from country-specific 1998 baselines are solid.',
        axis_labels=dict(a_x='Gini trend (pp/year)',annual_x='Year',
            annual_y='Gini change (pp)',lower_x='City count growth (%/year)',
            lower_y='Gini trend (pp/year)'),
        axis_details_in_caption='Panel b compares annual changes from the corresponding 1998 baseline. Domestic baselines are country-specific. Panels c–f show fitted annual percentage growth in the number of cities with recorded domestic flows. pp denotes percentage points.',
        data_policy='Domestic series use the same 45 countries in every domain. International series use all countries with recorded flows in each domain and year.',
        interpretation='Associations between changes in recorded geographic coverage and distributions; no causal effect claimed.',
        artwork_policy='Original data-driven geometry; style and evidence hierarchy adapted from a provided visual reference.')
    (QA/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    for suffix in ['.pdf','.svg','.png']:
        fig.savefig(OUT/('Fig6'+suffix),dpi=600)
    with pymupdf.open(OUT/'Fig6.pdf') as doc:
        page=doc[0]
        page.get_pixmap(matrix=pymupdf.Matrix(2.7,2.7),alpha=False).save(QA/'preview.png')
    plt.close(fig)
    print(json.dumps(dict(profile=PROFILE,countries=45,points=180,associations=associations),ensure_ascii=False))


if __name__=='__main__':
    main()
