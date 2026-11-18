"""Re-fit pooled cross-scale allocation models and audit pathway summaries.

Read existing harmonized sufficient statistics; write only to a new audit folder.
The original analysis outputs and manuscript are never modified.
"""
from pathlib import Path
import sys, os, inspect, json, hashlib, time
for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[key] = '2'
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tmp/nhb_fig2_python_deps'), str(ROOT/'scripts/reports')]
import numpy as np
import pandas as pd
import duckdb
from scipy.stats import binomtest
import fit_cross_scale_gravity_20261030 as gravity
import validate_international_to_domestic_allocation_20261030 as reverse
import validate_fully_matched_hhi_20261030 as hhi

OUT = ROOT/'outputs/results45_revalidation_20261030'
OUT.mkdir(exist_ok=True)
SOURCE = ROOT/'outputs/mechanism_validation_20261030'
PATHS = ROOT/'outputs/literature_pathway_extension_20261030'
checks = {}
def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
def log(value):
    print(time.strftime('%H:%M:%S'), value, flush=True)

def refit_international():
    # Clone the tested construction function with All-only scope and isolated output.
    src = inspect.getsource(gravity.blocks).replace("['All']+DOMAINS", "['All']")
    src = src.replace("to_csv(OUT/'conditional_gravity_risk_set_audit.csv'", "to_csv(AUDIT/'conditional_gravity_risk_set_audit.csv'")
    ns = dict(gravity.__dict__, AUDIT=OUT)
    exec(src, ns)
    blocks = ns['blocks']()['All']
    fits = {}
    for name, cols in [('M0_gravity',[0,1]), ('M1_history',[0,1,2]), ('M2_network',[0,1,2,3])]:
        log('Re-fit international '+name)
        fits[name] = gravity.fit(blocks, cols)
    save('international_refitted_parameters.json', fits)
    result = gravity.evaluate(blocks, fits)
    result.to_csv(OUT/'international_refitted_metrics.csv', index=False)
    old = pd.read_csv(SOURCE/'conditional_gravity_holdout_country_metrics.csv')
    old = old[(old.domain=='All') & old.model.isin(fits)]
    z = result.merge(old, on=['domain','country','model'], suffixes=('_new','_old'), validate='one_to_one')
    checks['international_refit_max_abs_metric_difference'] = float(max(
        (z[f'{col}_new']-z[f'{col}_old']).abs().max()
        for col in ['negative_log_likelihood_per_event','OD_CPC','city_margin_CPC']))
    assert len(z)==76*3
    return result

def refit_domestic():
    src = inspect.getsource(reverse.main).replace("['All']+DOMAINS", "['All']")
    src = src.replace("(OUT/'domestic_allocation_fits.json')", "(AUDIT/'domestic_allocation_fits.json')")
    src = src.replace("to_csv(OUT/", "to_csv(AUDIT/")
    src = src.replace("(OUT/'domestic_allocation_manifest.json')", "(AUDIT/'domestic_allocation_manifest.json')")
    ns = dict(reverse.__dict__, AUDIT=OUT)
    exec(src, ns)
    log('Re-fit domestic allocation models')
    ns['main']()
    result = pd.read_csv(OUT/'domestic_allocation_holdout_metrics.csv')
    old = pd.read_csv(SOURCE/'domestic_allocation_holdout_metrics.csv')
    old = old[old.domain=='All']
    z = result.merge(old, on=['domain','country','model'], suffixes=('_new','_old'), validate='one_to_one')
    checks['domestic_refit_max_abs_metric_difference'] = float(max(
        (z[f'{col}_new']-z[f'{col}_old']).abs().max()
        for col in ['negative_log_likelihood_per_event','city_margin_CPC']))
    assert len(z)==76*3
    return result

def paired_summary(result, names, cpc):
    rng = np.random.default_rng(20261030)
    rows = []
    for a,b in names:
        x = result[result.model==a].merge(result[result.model==b], on=['country','domain'], suffixes=('_base','_new'), validate='one_to_one')
        v = x.negative_log_likelihood_per_event_base-x.negative_log_likelihood_per_event_new
        w = x[cpc+'_new']-x[cpc+'_base']
        rows.append(dict(base=a, added=b, countries=len(x), improved=int((v>0).sum()),
                         median_loss_reduction=float(v.median()), loss_CI=gravity.ci(v,rng),
                         median_CPC_gain=float(w.median()), CPC_CI=gravity.ci(w,rng)))
    return rows

def pathway_audit():
    # Recompute finite-count HHI expectation from matched counts, not saved summaries.
    src = inspect.getsource(hhi.main)
    src = src.replace("to_csv(OUT/", "to_csv(AUDIT/")
    src = src.replace("(OUT/'fully_matched_hhi_summary.json')", "(AUDIT/'fully_matched_hhi_summary.json')")
    ns = dict(hhi.__dict__, AUDIT=OUT)
    exec(src, ns)
    log('Recompute matched finite-count HHI')
    ns['main']()
    a = pd.read_csv(OUT/'fully_matched_country_hhi.csv')
    b = pd.read_csv(PATHS/'fully_matched_country_hhi.csv')
    z = a.merge(b,on='country',suffixes=('_new','_old'),validate='one_to_one')
    checks['matched_HHI_max_abs_difference'] = float(max(
        (z[k+'_new']-z[k+'_old']).abs().max()
        for k in ['entry_HHI','next_HHI','expected_HHI','relative_excess_over_matched_pct']))
    counts = pd.read_csv(PATHS/'pooled_five_year_path_counts.csv')
    assert int(counts.records.sum())==1810380
    counts['percent']=100*counts.records/counts.records.sum()
    counts.to_csv(OUT/'rechecked_pathway_counts.csv',index=False)
    contributions=pd.read_csv(SOURCE/'continuation_contribution_actual_event_window.csv')
    n=int(contributions.target_events.sum()); total=int(contributions.all_domestic_events.sum())
    assert n==319402 and total==9339789
    checks['continuation_contribution_same_event_window']={'target':n,'domestic_events':total,'percent':100*n/total}
    departures=pd.read_csv(SOURCE/'domain_domestic_to_international_summary.csv')
    checks['domestic_before_international']={'departures':int(departures.international_departures.sum()),
        'preceded_by_domestic':int(departures.preceded_by_domestic_within5.sum()),
        'percent':100*departures.preceded_by_domestic_within5.sum()/departures.international_departures.sum()}
    # Aggregate input quality checks keep distinct event counts and city strengths separate.
    c=duckdb.connect()
    can=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet'
    columns=[r[0] for r in c.sql(f"DESCRIBE SELECT * FROM read_parquet('{can}')").fetchall()]
    checks['canonical_flow_columns']=columns
    if 'geography' in columns:
        counts=c.sql(f"SELECT geography,sum(mobility_count)::BIGINT events FROM read_parquet('{can}') WHERE year BETWEEN 1998 AND 2025 GROUP BY geography").df()
    else:
        counts=c.sql(f"SELECT CASE WHEN origin_country=destination_country THEN 'domestic' ELSE 'international' END geography,sum(flow)::BIGINT events FROM read_parquet('{can}') WHERE year BETWEEN 1998 AND 2025 GROUP BY geography").df()
    counts.to_csv(OUT/'canonical_recount.csv',index=False)
    checks['canonical_recount']=counts.to_dict('records')
    assert int(counts.events.sum())==29703224
    c.close()

def main():
    save('audit_plan.json',{'scope':'Re-fit pooled models with identical specifications and rederive matched HHI; no new selection of favorable predictors.',
      'training':'2005-2018','held_out':'2019-2025','unit':'country','country_bootstrap_repetitions':4000,
      'source':'Harmonized canonical event aggregates and cached author-year stock/matched sufficient statistics.',
      'manuscript_modified':False,'causal_inference':False})
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'outputs/paper_final').glob('*.tex')}
    international=refit_international()
    save('international_rechecked_comparisons.json',paired_summary(international,[('M0_gravity','M1_history'),('M1_history','M2_network')],'OD_CPC'))
    domestic=refit_domestic()
    save('domestic_rechecked_comparisons.json',paired_summary(domestic,[('D0_mass_accessibility','D1_domestic_history'),('D1_domestic_history','D2_international_history')],'city_margin_CPC'))
    pathway_audit()
    after={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'outputs/paper_final').glob('*.tex')}
    assert before==after
    checks['manuscript_unchanged']=True
    checks['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    save('revalidation_checks.json',checks)
    log('DONE '+json.dumps(checks,ensure_ascii=False))

if __name__=='__main__':main()
