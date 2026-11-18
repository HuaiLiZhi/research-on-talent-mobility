"""Aggregate-network diagnostics and finite-event distribution comparisons.

Exploratory follow-up. No individual data; no causal intervention. The actual
origin totals supplied to all conditional predictions are held unchanged.
"""
from pathlib import Path
import os,sys,json,time
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps'),str(ROOT/'outputs/country_typology_validation_20261029/python_deps'),str(ROOT/'scripts/reports')]
import numpy as np,pandas as pd
from scipy.sparse import coo_matrix
from validate_logical_distance_20261030 import readpq
from validate_cross_scale_mechanisms_20261030 import probabilities
from validate_aggregate_alternatives_20261030 import bootstrap_ci
SRC=ROOT/'outputs/international_signal_validation_20261030'
LOG=ROOT/'outputs/logical_distance_validation_20261030'
PRE=ROOT/'outputs/cross_scale_mechanism_validation_20261030'
OUT=ROOT/'outputs/results_network_revision_20261030/analysis';OUT.mkdir(parents=True,exist_ok=True)
RANDOMIZATIONS=100;SIMULATIONS=200;SEED=20261030

def log(s):print(time.strftime('%H:%M:%S'),s,flush=True)
def save(n,v):(OUT/n).write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
def gini(x):
    x=np.asarray(x,dtype=float);x=np.atleast_2d(x);n=x.shape[1]
    return 2*(np.sort(x,axis=1)*np.arange(1,n+1)).sum(1)/(n*x.sum(1))-(n+1)/n

def predict(d,f,feature=None):
    xx=d['x'][:,f['cols']].astype(float)
    if feature is not None:
        where=f['cols'].index(17);xx[:,where]=feature
    eta=((xx-np.asarray(f['mean']))/np.asarray(f['scale']))@np.asarray(f['beta'])
    pr,starts,sizes,_=probabilities(eta,d['group'])
    tot=np.add.reduceat(d['y'],starts).astype(float)
    mu=pr*np.repeat(tot,sizes)
    assert np.max(abs(np.add.reduceat(mu,starts)-tot)/np.maximum(tot,1))<1e-10
    return pr,mu,starts,sizes,tot

def deviance(y,mu):
    y=np.asarray(y,dtype=float);mu=np.asarray(mu,dtype=float)
    return 2*(np.where(y>0,y*np.log(np.maximum(y,1e-300)/np.maximum(mu,1e-300)),0)-y+mu)

def prepare():
    save('analysis_plan.json',dict(status='Exploratory plan saved before the present diagnostics and simulations; follows earlier international-feature exploration.',
      question='Does foreign-city correspondence add information beyond fixed international margins, and how does the fitted term alter domestic city strength distributions under identical origin totals?',
      conditioning='Observed origin-city/country/four-year-period totals supplied. Only already declared city risk sets; remaining flows held observed.',
      randomization=dict(repetitions=RANDOMIZATIONS,construction='Within each directed origin-country/destination-country block, randomly rematch integer event stubs. Preserve each city outgoing flow to each country and each city incoming flow from each country exactly. Geographic country-pair constraints retained. Distinct city degree and city-pair history are not preserved.',
        test='On later-period lag networks only, replace two-step feature in the already fitted actual-network model; do not refit or perturb domestic history, mass, geography or field predictors. This is a correspondence-disruption diagnostic, not an optimally refitted null competitor or causal experiment.'),
      simulation=dict(repetitions=SIMULATIONS,construction='For each observed origin group, draw multinomial counts over the same candidate destinations with fixed actual event total. Compare baseline and baseline+two-step, add unmodeled observed edges unchanged. Compute combined domestic city inflow+outflow strength on the union of candidate and observed city nodes, including zeros.',
        scope='Two held-out four-year periods, not annual1998-2025 trend attribution. Finite integer events prevent treating every tiny predicted probability as an observed active city.',
        metrics='Gini on common city opportunity pool, HHI, and a positive-strength-only Gini sensitivity. Per-country differences average the two periods and simulations.'),
      uncertainty='Country-bootstrap4000 pointwise intervals for paired country summaries; randomization percentiles describe randomization variation; simulations do not create independent countries.',
      scope_limits=['No independent fresh holdout; same later years used in previous explorations.','International network is observational and shared across countries.','No same-person multi-step paths inferred.'],manuscript_modified=False))
    full=dict(np.load(LOG/'domestic_design.npz',allow_pickle=False));extra=dict(np.load(SRC/'international_features.npz',allow_pickle=False))
    mask=full['p']>=5
    d={k:v[mask] for k,v in full.items() if k in ['y','p','country','group']}
    d['x']=np.column_stack([full['x'][mask],extra['x'][mask]])
    d['country_codes']=full['country_codes'];d['o']=extra['origin_index'][mask];d['dest']=extra['destination_index'][mask];d['cities']=extra['city_codes']
    fits=json.loads((SRC/'fits.json').read_text())
    return d,fits

def randomization(d,fits):
    file=OUT/'network_randomization_country.csv'
    if file.exists():return pd.read_csv(file)
    ii=readpq(PRE/'international_city_od_period.parquet');idx=pd.Index(d['cities']);n=len(idx)
    baseline=fits['B_history_field'];actual=fits['T_foreign_two_step']
    _,mu0,_,_,_=predict(d,baseline);_,mua,_,_,_=predict(d,actual)
    base_dev=np.bincount(d['country'],weights=deviance(d['y'],mu0),minlength=76)
    actual_dev=np.bincount(d['country'],weights=deviance(d['y'],mua),minlength=76)
    prepared={}
    for p in [5,6]:
        v=ii[ii.p==p-1].sort_values(['oc','country','o','d']).copy()
        weights=v.flow.to_numpy(dtype=np.int64);assert np.array_equal(weights,v.flow.to_numpy())
        oi=idx.get_indexer(v.o);di=idx.get_indexer(v.d);assert (oi>=0).all() and (di>=0).all()
        os=np.repeat(oi,weights);ds=np.repeat(di,weights)
        newblock=np.r_[True,(v.oc.to_numpy()[1:]!=v.oc.to_numpy()[:-1])|(v.country.to_numpy()[1:]!=v.country.to_numpy()[:-1])]
        edge_starts=np.flatnonzero(newblock);counts=np.add.reduceat(weights,edge_starts);starts=np.r_[0,np.cumsum(counts)[:-1]]
        out=np.bincount(os,minlength=n).astype(float);inside=np.bincount(ds,minlength=n)
        row_specs=[]
        for ci in range(76):
            rows=np.flatnonzero((d['p']==p)&(d['country']==ci))
            oo,oinv=np.unique(d['o'][rows],return_inverse=True);dd,dinv=np.unique(d['dest'][rows],return_inverse=True)
            row_specs.append((rows,oo,dd,oinv,dinv))
        prepared[p]=dict(os=os,ds=ds,starts=starts,counts=counts,out=out,inside=inside,specs=row_specs,ones=np.ones(len(os),dtype='float32'))
    rng=np.random.default_rng(SEED+910);rows=[];audits=[]
    for rep in range(RANDOMIZATIONS):
        feature=np.empty(len(d['y']),dtype='float32')
        for p,q in prepared.items():
            ds=q['ds'].copy()
            for start,count in zip(q['starts'],q['counts']):rng.shuffle(ds[start:start+count])
            W=coo_matrix((q['ones'],(q['os'],ds)),shape=(n,n)).tocsr().astype(float)
            out=np.asarray(W.sum(1)).ravel();inside=np.asarray(W.sum(0)).ravel()
            assert np.array_equal(out,q['out']) and np.array_equal(inside,q['inside'])
            P=W.multiply(np.divide(1,out,out=np.zeros_like(out),where=out>0)[:,None]).tocsr()
            for rr,oo,dd,oi,di in q['specs']:
                paths=(W[oo]@P[:,dd]).toarray()
                feature[rr]=np.log1p(paths[oi,di])
            if rep==0:
                assert np.array_equal(np.add.reduceat(ds.size*np.zeros(len(q['counts']),dtype=int)+q['counts'],np.array([0])),[len(ds)])
                audits.append(dict(target_period=p,event_stubs=len(ds),country_pair_blocks=len(q['counts']),all_city_inout_margins_exact=True,all_city_partner_country_margins_exact_by_construction=True))
        _,mun,_,_,_=predict(d,actual,feature)
        null_dev=np.bincount(d['country'],weights=deviance(d['y'],mun),minlength=76)
        for ci,cc in enumerate(d['country_codes']):
            rows.append(dict(replicate=rep,country=str(cc),baseline_deviance=float(base_dev[ci]),actual_deviance=float(actual_dev[ci]),randomized_deviance=float(null_dev[ci]),
                actual_gain_pct=float(100*(1-actual_dev[ci]/base_dev[ci])),randomized_gain_pct=float(100*(1-null_dev[ci]/base_dev[ci]))))
        if rep%10==0:log('Foreign-partner randomization '+str(rep+1)+'/'+str(RANDOMIZATIONS))
    frame=pd.DataFrame(rows);frame.to_csv(file,index=False);save('network_randomization_checks.json',audits)
    per=frame.groupby('country').agg(actual_gain_pct=('actual_gain_pct','first'),randomized_gain_median_pct=('randomized_gain_pct','median'),
        randomized_gain_q025_pct=('randomized_gain_pct',lambda x:np.quantile(x,.025)),randomized_gain_q975_pct=('randomized_gain_pct',lambda x:np.quantile(x,.975))).reset_index()
    per['actual_minus_randomized_pct']=per.actual_gain_pct-per.randomized_gain_median_pct
    per.to_csv(OUT/'network_randomization_country_summary.csv',index=False)
    nullmed=frame.groupby('replicate').randomized_gain_pct.median()
    save('network_randomization_summary.json',dict(countries=76,randomizations=RANDOMIZATIONS,actual_gain_median_pct=float(per.actual_gain_pct.median()),
         randomized_gain_median_pct=float(nullmed.median()),randomized_median_q025_pct=float(nullmed.quantile(.025)),randomized_median_q975_pct=float(nullmed.quantile(.975)),
         countries_actual_above_null_median=int((per.actual_minus_randomized_pct>0).sum()),median_paired_actual_minus_null_pct=float(per.actual_minus_randomized_pct.median()),
         actual_minus_null_country_bootstrap_CI=bootstrap_ci(per.actual_minus_randomized_pct,np.random.default_rng(SEED)),
         note='Conditional fixed-coefficient feature disruption, not refitted null models; not a causal or independent confirmation test.'))
    return frame

def simulation(d,fits):
    file=OUT/'distribution_simulation_country_period.csv'
    if file.exists():return pd.read_csv(file)
    od=readpq(LOG/'domestic_od_period.parquet')
    p0,m0,starts,sizes,tot=predict(d,fits['B_history_field'])
    p1,m1,_,_,_=predict(d,fits['T_foreign_two_step'])
    results=[];samples=[];audit=[];rng=np.random.default_rng(SEED+117)
    for ci,cc in enumerate(d['country_codes']):
        for p in [5,6]:
            rr=np.flatnonzero((d['country']==ci)&(d['p']==p))
            observed=od[(od.country==cc)&(od.p==p)]
            nodes=sorted(set(observed.o)|set(observed.d)|set(d['cities'][d['dest'][rr]]))
            idx=pd.Index(nodes);oo=idx.get_indexer(observed.o);dd=idx.get_indexer(observed.d)
            obs_out=np.bincount(oo,weights=observed.flow,minlength=len(nodes))
            obs_in=np.bincount(dd,weights=observed.flow,minlength=len(nodes))
            observed_strength=obs_out+obs_in
            model_old_in=np.bincount(idx.get_indexer(d['cities'][d['dest'][rr]]),weights=d['y'][rr],minlength=len(nodes))
            untouched=observed_strength-model_old_in
            assert untouched.min()>-1e-8
            sim0=np.broadcast_to(untouched,(SIMULATIONS,len(nodes))).copy();sim1=sim0.copy()
            groups=[j for j,start in enumerate(starts) if d['country'][start]==ci and d['p'][start]==p]
            for j in groups:
                sl=slice(starts[j],starts[j]+sizes[j]);local=idx.get_indexer(d['cities'][d['dest'][sl]])
                total=int(tot[j]);assert total==tot[j]
                for probabilities_,buffer in [(p0,sim0),(p1,sim1)]:
                    prob=probabilities_[sl].copy();prob/=prob.sum()
                    draws=rng.multinomial(total,prob,size=SIMULATIONS)
                    buffer[:,local]+=draws
            strength_total=2*observed.flow.sum()
            assert np.allclose(sim0.sum(1),strength_total) and np.allclose(sim1.sum(1),strength_total)
            g0=gini(sim0);g1=gini(sim1)
            h0=np.square(sim0/strength_total).sum(1);h1=np.square(sim1/strength_total).sum(1)
            positive0=np.array([gini(x[x>0])[0] for x in sim0]);positive1=np.array([gini(x[x>0])[0] for x in sim1])
            obs_g=float(gini(observed_strength)[0]);obs_h=float(np.square(observed_strength/strength_total).sum())
            results.append(dict(country=str(cc),p=p,pool_cities=len(nodes),all_events=float(observed.flow.sum()),modeled_events=float(d['y'][rr].sum()),
                observed_Gini_pool=obs_g,observed_HHI=obs_h,baseline_Gini_mean=float(g0.mean()),international_Gini_mean=float(g1.mean()),
                baseline_HHI_mean=float(h0.mean()),international_HHI_mean=float(h1.mean()),
                delta_Gini_pp=float(100*(g1-g0).mean()),delta_HHI=float((h1-h0).mean()),
                delta_Gini_positive_only_pp=float(100*(positive1-positive0).mean()),
                baseline_Gini_abs_error=float(abs(g0.mean()-obs_g)),international_Gini_abs_error=float(abs(g1.mean()-obs_g)),
                baseline_HHI_abs_error=float(abs(h0.mean()-obs_h)),international_HHI_abs_error=float(abs(h1.mean()-obs_h))))
            samples.extend(dict(country=str(cc),p=p,replicate=j,delta_Gini_pp=float(100*(g1[j]-g0[j])),delta_HHI=float(h1[j]-h0[j])) for j in range(SIMULATIONS))
            audit.append(dict(country=str(cc),p=p,total_strength_preserved=True,common_opportunity_pool=len(nodes),unmodeled_edges_held_observed=True))
        if ci%10==0:log('Finite-event distribution comparison '+str(ci+1)+'/76 countries')
    frame=pd.DataFrame(results);frame.to_csv(file,index=False);pd.DataFrame(samples).to_csv(OUT/'distribution_simulation_replicates.csv',index=False);save('simulation_checks.json',audit)
    per=frame.groupby('country').mean(numeric_only=True).reset_index();per.to_csv(OUT/'distribution_simulation_country_summary.csv',index=False)
    summ=dict(countries=76,periods=[5,6],simulations=SIMULATIONS,modeled_events=float(frame.modeled_events.sum()),all_events=float(frame.all_events.sum()))
    for metric in ['delta_Gini_pp','delta_HHI','delta_Gini_positive_only_pp']:
        s=per[metric];summ[metric]=dict(median=float(s.median()),q25=float(s.quantile(.25)),q75=float(s.quantile(.75)),country_bootstrap_CI=bootstrap_ci(s,rng),countries_positive=int((s>0).sum()))
    for metric in ['Gini','HHI']:
        summ[metric+'_error']=dict(countries_improved=int((per['international_'+metric+'_abs_error']<per['baseline_'+metric+'_abs_error']).sum()),
            baseline_median_error=float(per['baseline_'+metric+'_abs_error'].median()),international_median_error=float(per['international_'+metric+'_abs_error'].median()))
    save('distribution_simulation_summary.json',summ);return frame

def main():
    d,fits=prepare();randomization(d,fits);simulation(d,fits)
    log('All added network diagnostics complete')

if __name__=='__main__':main()
