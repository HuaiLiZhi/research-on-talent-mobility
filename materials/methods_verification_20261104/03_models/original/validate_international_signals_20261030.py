"""Exploratory international-network predictors of domestic city OD allocation.

Uses aggregate city networks only. Fix the hypotheses before this comparison,
rank candidates on 2014-2017, then report all later-period comparisons. Later
periods have been used in earlier model exploration; this is not a fresh holdout.
"""
from pathlib import Path
import os, sys, json, time, hashlib
for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS']:
    os.environ[key] = '2'
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tmp/nhb_fig2_python_deps'),
               str(ROOT/'outputs/country_typology_validation_20261029/python_deps'),
               str(ROOT/'scripts/reports')]
import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from scipy.stats import binomtest
from validate_logical_distance_20261030 import readpq, fit
from validate_cross_scale_mechanisms_20261030 import probabilities
from validate_aggregate_alternatives_20261030 import bootstrap_ci

SOURCE = ROOT/'outputs/logical_distance_validation_20261030'
PRE = ROOT/'outputs/cross_scale_mechanism_validation_20261030'
OUT = ROOT/'outputs/international_signal_validation_20261030'
OUT.mkdir(parents=True, exist_ok=True)
FEATURES = ['log_lag_mass', 'log_geographic_distance',
            'log1p_lag_destination_domestic_inflow', 'log1p_lag_domestic_pair_flow',
            'disciplinary_distance', 'partner_country_distance',
            'latent_partner_distance', 'missing_field_profile',
            'missing_partner_country_profile',
            'log1p_destination_international_inflow',
            'log1p_destination_international_outflow',
            'log1p_destination_foreign_origin_city_count',
            'log1p_destination_foreign_destination_city_count',
            'log_inward_PageRank_relative_uniform',
            'log_outward_PageRank_relative_uniform',
            'shared_foreign_destination_city_cosine',
            'shared_foreign_origin_city_cosine',
            'log1p_foreign_mediated_two_step_expected_flow']
BASE = [0, 1, 2, 3, 7, 8, 4]
CONFIGS = {'B_history_field': BASE, 'P_partner_country': BASE+[5],
           'G_international_gateway': BASE+[9, 10],
           'R_foreign_city_reach': BASE+[11, 12],
           'C_international_centrality': BASE+[13, 14],
           'S_shared_foreign_cities': BASE+[15, 16],
           'T_foreign_two_step': BASE+[17],
           'A_all_international_signals': BASE+list(range(9, 18))}
CANDIDATES = [k for k in CONFIGS if k not in ['B_history_field', 'P_partner_country']]
SEED = 20261030


def log(s):
    print(time.strftime('%H:%M:%S'), s, flush=True)


def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf8')


def plan():
    if (OUT/'analysis_plan.json').exists():
        return
    save('analysis_plan.json', {
        'date': '2026-10-30',
        'status': 'Exploratory follow-up motivated by previously weak partner-country distance. Saved before new feature construction and model fits.',
        'question': 'Does lagged international network information improve domestic city OD allocation beyond geography, research mass, domestic destination/pair history and disciplinary similarity?',
        'units': 'Aggregate city OD-period counts only. No person trajectories read or synthesized.',
        'time': 'Train 2002-2013, rank on 2014-2017; report 2018-2025 as later-period evaluation. These later years were inspected in earlier explorations and are not a fresh independent confirmation set.',
        'sample': 'Exactly the saved domestic risk set: 76 countries, top50 domestic origins chosen in training years, all candidate destinations with positive lagged verified stock and coordinates, zero-flow cells kept and self pairs removed.',
        'conditioning': 'Each origin-city/destination-country/period observed event total is supplied; allocation, not unconditional total forecast.',
        'baseline': [FEATURES[i] for i in BASE],
        'hypotheses': {
            'gateway': 'Separate destination international inbound and outbound event counts.',
            'reach': 'Separate numbers of distinct foreign origin and destination cities.',
            'centrality': 'Directed weighted PageRank of international network and its reverse; damping0.85, uniform teleportation, no tuning.',
            'shared_cities': 'Separate incoming/outgoing TF-IDF foreign-city profiles, compared by cosine; more specific than shared partner countries.',
            'two_step': 'W @ row_normalize(W), restricted to domestic source/destination pairs. All intermediate nodes are foreign. Counts are network pathways, not the same individuals taking two moves.',
            'all': 'All nine new international features jointly, report alongside individual hypotheses.'},
        'lags': 'All international predictors use the entire immediately preceding four-year period; no contemporaneous target counts enter predictors.',
        'primary': 'Country-median paired conditional Poisson deviance reduction; all models reported. Rank only by validation median deviance reduction.',
        'secondary': 'CPC, raw R2=1-SSE/SST and log1p R2 on country-pooled OD cells; examine temporal sign stability.',
        'multiplicity': 'Holm correction of paired country sign tests over all7 additions to baseline per split; direct comparisons of each of6 new additions with partner-distance model are a separate family.',
        'intervals': '4000 paired-country bootstrap pointwise intervals; shared network dependence is not eliminated by country bootstrap.',
        'model_configs': CONFIGS,
        'limitations': ['Observational cross-layer associations, not causal effects.',
                       'New feature search is exploratory, including reused evaluation periods.',
                       'Domestic risk set covers about79.29% of 76-country later domestic events.',
                       'No guarantee of any improvement or coefficient sign; failures retained.'],
        'manuscript_modified': False})


def pagerank(W, reverse=False):
    A = W.T.tocsr() if reverse else W
    strength = np.asarray(A.sum(axis=1)).ravel()
    P = A.multiply(np.divide(1., strength, out=np.zeros_like(strength), where=strength>0)[:, None]).tocsr()
    n = A.shape[0]
    r = np.full(n, 1/n)
    for iterations in range(2000):
        new = .85*(P.T@r + r[strength==0].sum()/n) + .15/n
        error = np.abs(new-r).sum()
        r = new
        if error < 1e-12:
            break
    assert error < 1e-12 and abs(r.sum()-1) < 1e-10
    return r, dict(iterations=iterations+1, L1_error=float(error), sum=float(r.sum()))


def tfidf_unit(A):
    A = A.tocsr()
    row = np.asarray(A.sum(axis=1)).ravel()
    active = int((row>0).sum())
    idf = 1 + np.log((1+active)/(1+A.getnnz(axis=0)))
    T = A.multiply(np.divide(1., row, out=np.zeros_like(row), where=row>0)[:, None]).multiply(idf[None, :]).tocsr()
    norms = np.sqrt(np.asarray(T.multiply(T).sum(axis=1)).ravel())
    return T.multiply(np.divide(1., norms, out=np.zeros_like(norms), where=norms>0)[:, None]).tocsr()


def build():
    plan()
    d = dict(np.load(SOURCE/'domestic_design.npz', allow_pickle=False))
    cache = OUT/'international_features.npz'
    if cache.exists():
        z = dict(np.load(cache, allow_pickle=False))
        assert len(z['x']) == len(d['y'])
        d['x'] = np.column_stack([d['x'], z['x']])
        return d
    nodes = np.load(SOURCE/'representations.npz', allow_pickle=False)['city_codes']
    index = pd.Index(nodes)
    ii = readpq(PRE/'international_city_od_period.parquet')
    od = readpq(SOURCE/'domestic_od_period.parquet')
    mass = readpq(PRE/'city_author_year_mass.parquet')
    mass['p'] = (mass.year-1998)//4
    mass = mass.groupby(['p', 'country', 'city'], as_index=False).mass.sum()
    coords = pd.read_csv(ROOT/'data/processed/mobility_city_harmonized_20261020/cities.csv').drop_duplicates('city_id').set_index('city_id')
    coords = coords[coords.latitude.between(-90,90)&coords.longitude.between(-180,180)]
    top = pd.read_csv(SOURCE/'domestic_training_selected_origins.csv')
    x = np.empty((len(d['y']), 9), dtype='float32')
    origin_index = np.empty(len(d['y']), dtype='int32')
    destination_index = np.empty(len(d['y']), dtype='int32')
    assigned = np.zeros(len(d['y']), dtype=bool)
    audit = []
    for p in range(1,7):
        v = ii[ii.p==p-1]
        oi = index.get_indexer(v.o); di = index.get_indexer(v.d)
        assert (oi>=0).all() and (di>=0).all() and (v.oc!=v.country).all()
        W = coo_matrix((v.flow.to_numpy(dtype=float), (oi,di)), shape=(len(nodes), len(nodes))).tocsr()
        W.sum_duplicates(); W.eliminate_zeros()
        inbound = np.asarray(W.sum(axis=0)).ravel()
        outbound = np.asarray(W.sum(axis=1)).ravel()
        indegree = W.getnnz(axis=0); outdegree = W.getnnz(axis=1)
        pin, ai = pagerank(W)
        pout, ao = pagerank(W, reverse=True)
        unit_out = tfidf_unit(W); unit_in = tfidf_unit(W.T)
        P = W.multiply(np.divide(1., outbound, out=np.zeros_like(outbound), where=outbound>0)[:,None]).tocsr()
        for ci, country in enumerate(d['country_codes']):
            rows = np.flatnonzero((d['country']==ci)&(d['p']==p))
            if not len(rows):
                continue
            src = top[top.country==country].o.to_numpy()
            dest = mass[(mass.country==country)&(mass.p==p-1)&mass.city.isin(coords.index)].sort_values('city').city.to_numpy()
            current = od[(od.country==country)&(od.p==p)&od.o.isin(src)&od.d.isin(dest)]
            present = set(current.o)
            origins = np.array([o for o in src if o in present])
            expected = current.pivot_table(index='o', columns='d', values='flow', aggfunc='sum', fill_value=0).reindex(index=origins, columns=dest, fill_value=0).to_numpy()
            keep = origins[:,None]!=dest[None,:]
            assert np.array_equal(expected[keep], d['y'][rows])
            a = index.get_indexer(origins); b = index.get_indexer(dest)
            assert (a>=0).all() and (b>=0).all()
            shared_out = (unit_out[a]@unit_out[b].T).toarray()
            shared_in = (unit_in[a]@unit_in[b].T).toarray()
            paths = (W[a]@P[:,b]).toarray()
            nodefeatures = [np.log1p(inbound[b]), np.log1p(outbound[b]),
                            np.log1p(indegree[b]), np.log1p(outdegree[b]),
                            np.log(pin[b]*len(nodes)), np.log(pout[b]*len(nodes))]
            arr = np.stack([np.broadcast_to(q,expected.shape) for q in nodefeatures]
                           +[np.clip(shared_out,0,1),np.clip(shared_in,0,1),np.log1p(paths)], axis=-1)[keep]
            assert arr.shape==(len(rows),9) and np.isfinite(arr).all()
            x[rows] = arr
            origin_index[rows] = np.broadcast_to(a[:,None], expected.shape)[keep]
            destination_index[rows] = np.broadcast_to(b[None,:], expected.shape)[keep]
            assigned[rows] = True
        audit.append(dict(p=p, international_nodes=len(nodes), directed_links=int(W.nnz),
                          previous_international_events=float(W.sum()), PageRank_in=ai, PageRank_out=ao))
        log('International features built for target period '+str(p))
    assert assigned.all() and np.isfinite(x).all()
    np.savez_compressed(cache, x=x, origin_index=origin_index, destination_index=destination_index, city_codes=nodes)
    save('feature_construction_audit.json', audit)
    d['x'] = np.column_stack([d['x'],x])
    return d


def evaluate(d, f, name):
    mask = d['p']>=4
    x = d['x'][mask][:,f['cols']]
    eta = ((x-np.asarray(f['mean']))/np.asarray(f['scale']))@np.asarray(f['beta'])
    y = d['y'][mask].astype(float); g=d['group'][mask]
    pr, starts, sizes, _ = probabilities(eta,g)
    totals = np.add.reduceat(y,starts)
    mu = pr*np.repeat(totals,sizes)
    error = float(np.max(abs(np.add.reduceat(mu,starts)-totals)/np.maximum(totals,1)))
    assert np.isfinite(mu).all() and error<1e-10
    cs=d['country'][mask]; ps=d['p'][mask]
    dev=2*(np.where(y>0,y*np.log(np.maximum(y,1e-300)/np.maximum(mu,1e-300)),0)-y+mu)
    rows=[]
    for split, periods in [('validation',[4]),('test',[5,6]),('early_test',[5]),('late_test',[6])]:
        for ci, country in enumerate(d['country_codes']):
            k=(cs==ci)&np.isin(ps,periods)
            yy=y[k]; mm=mu[k]; ly=np.log1p(yy)
            sst=np.square(yy-yy.mean()).sum(); sstl=np.square(ly-ly.mean()).sum()
            rows.append(dict(split=split,model=name,country=str(country),events=float(yy.sum()),cells=int(k.sum()),
                 deviance=float(dev[k].sum()),CPC=float(np.minimum(yy,mm).sum()/yy.sum()),
                 R2_raw=float(1-np.square(yy-mm).sum()/sst) if sst else np.nan,
                 R2_log1p=float(1-np.square(ly-np.log1p(mm)).sum()/sstl) if sstl else np.nan))
    return rows, error


def holm(values):
    p=np.asarray(values); order=np.argsort(p)
    out=np.empty(len(p));out[order]=np.minimum(1,np.maximum.accumulate(p[order]*(len(p)-np.arange(len(p)))))
    return out


def summarize(metrics):
    rng=np.random.default_rng(SEED)
    summaries=[]; paired=[]; absolute=[]
    for (split,model),s in metrics.groupby(['split','model']):
        q=dict(split=split,model=model,countries=len(s))
        for key in ['CPC','R2_raw','R2_log1p']:
            q[key+'_median']=float(s[key].median())
        absolute.append(q)
    for split,s in metrics.groupby('split'):
        for base in ['B_history_field','P_partner_country']:
            models=[m for m in CONFIGS if m!=base and m!='B_history_field']
            if base=='P_partner_country':
                models=CANDIDATES
            for name in models:
                z=s[s.model==base].merge(s[s.model==name],on=['split','country'],suffixes=('_base','_new'))
                change=100*(1-z.deviance_new/z.deviance_base)
                cg=z.CPC_new-z.CPC_base; rg=z.R2_raw_new-z.R2_raw_base
                ci=bootstrap_ci(change,rng); cci=bootstrap_ci(cg,rng)
                n=int((change!=0).sum())
                p=binomtest(int((change>0).sum()),n,.5).pvalue
                summaries.append(dict(split=split,base=base,new=name,countries=len(z),
                    median_deviance_reduction_pct=float(change.median()),CI_low=ci[0],CI_high=ci[1],
                    countries_better=int((change>0).sum()),median_CPC_gain=float(cg.median()),CPC_CI_low=cci[0],CPC_CI_high=cci[1],
                    median_R2_gain=float(rg.median()),sign_p=p))
                for k, v, c, r in zip(z.country,change,cg,rg):
                    paired.append(dict(split=split,base=base,new=name,country=k,deviance_reduction_pct=float(v),CPC_gain=float(c),R2_gain=float(r)))
    summary=pd.DataFrame(summaries)
    for _,inds in summary.groupby(['split','base']).groups.items():
        summary.loc[inds,'sign_p_holm']=holm(summary.loc[inds,'sign_p'])
    summary.to_csv(OUT/'comparison_summary.csv',index=False)
    pd.DataFrame(paired).to_csv(OUT/'paired_country_contrasts.csv',index=False)
    pd.DataFrame(absolute).to_csv(OUT/'absolute_metrics.csv',index=False)
    rank=summary[(summary.split=='validation')&(summary.base=='B_history_field')&summary.new.isin(CANDIDATES)].sort_values('median_deviance_reduction_pct',ascending=False)
    save('validation_selection.json', dict(criterion='2014-2017 country-median deviance reduction; no test-based selection',
        ranking=rank[['new','median_deviance_reduction_pct','median_CPC_gain']].to_dict('records'),
        selected=rank.iloc[0]['new']))
    log('Full later-period comparison')
    print(summary[(summary.split=='test')&(summary.base=='B_history_field')].to_string(index=False),flush=True)


def main():
    start=time.time()
    d=build()
    fits={}; metrics=[]; checks=[]
    oldfits=json.loads((SOURCE/'fits.json').read_text(encoding='utf8'))['D']
    for name,cols in CONFIGS.items():
        log('Fit '+name)
        if name=='B_history_field':
            f=oldfits['H_field']
        elif name=='P_partner_country':
            f=oldfits['H_both']
        else:
            f=fit(d,cols)
        fits[name]=f
        rows,error=evaluate(d,f,name); metrics.extend(rows)
        checks.append(dict(model=name,finite_predictions=True,max_relative_choice_total_error=error,
                           gradient=f['gradient'],iterations=f['iterations']))
        save('fits.json',fits)
        pd.DataFrame(metrics).to_csv(OUT/'country_metrics.csv',index=False)
        log('Completed '+name)
    frame=pd.DataFrame(metrics)
    # Exactly reproduce existing comparison's country CPC for the common test.
    saved=pd.read_csv(SOURCE/'heldout_r2/country_metrics.csv')
    reproduction=[]
    for new,old in [('B_history_field','H_field'),('P_partner_country','H_both')]:
        z=frame[(frame.model==new)&(frame.split=='test')].merge(saved[(saved.target=='D')&(saved.model==old)],on='country',suffixes=('_new','_old'))
        errs={k:float(abs(z[k+'_new']-z[k+'_old']).max()) for k in ['CPC','R2_raw','R2_log1p']}
        assert len(z)==76 and max(errs.values())<1e-10
        reproduction.append(dict(model=new,errors=errs))
    summarize(frame)
    coef=[]
    for name,f in fits.items():
        for col,b,scaled in zip(f['cols'],f['coefficients'],f['beta']):
            coef.append(dict(model=name,feature=FEATURES[col],coefficient=b,standardized_coefficient=scaled))
    pd.DataFrame(coef).to_csv(OUT/'coefficients.csv',index=False)
    save('validation_checks.json',dict(individual_records_read=False,all_candidate_rows_preserved=True,
         all_predictors_previous_period=True,baseline_reproduction=reproduction,models=checks,
         total_rows=len(d['y']),test_events=float(d['y'][d['p']>=5].sum()),
         runtime_seconds=time.time()-start,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))


if __name__=='__main__':
    main()
