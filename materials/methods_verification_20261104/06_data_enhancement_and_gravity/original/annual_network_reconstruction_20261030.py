"""Annual conditional reconstructions with the saved period-level allocation fits.

Use yearly observed origin totals, not interpolated four-year index values.
Predictor values and candidate destinations remain those of the corresponding
period-level design, using its preceding four-year block. No refitting.
"""
from pathlib import Path
import os,sys,json,shutil,time
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps'),str(ROOT/'scripts/reports')]
import numpy as np,pandas as pd,duckdb
from validate_cross_scale_mechanisms_20261030 import probabilities
MODEL_NAME='A_all_international_signals' if '--full' in sys.argv else 'T_foreign_two_step'
OUT=ROOT/('outputs/fig6_full_model_revision_20261030' if '--full' in sys.argv else 'outputs/fig6_annual_revision_20261030')
DATA=OUT/'analysis';DATA.mkdir(parents=True,exist_ok=True)
PAPER=ROOT/'outputs/paper_final';OLD=ROOT/'outputs/results_network_revision_20261030'

def gini(v):
    v=np.sort(np.asarray(v,dtype=float));n=len(v)
    return float(2*np.dot(v,np.arange(1,n+1))/(n*v.sum())-(n+1)/n)

def main():
    before=OUT/'before';before.mkdir(exist_ok=True)
    for name in ['results.tex','methods.tex']:
        if not (before/name).exists():shutil.copy2(PAPER/name,before/name)
    for ext in ['pdf','svg','png']:
        if not (before/f'Fig6.{ext}').exists():shutil.copy2(PAPER/f'figures/Fig6.{ext}',before/f'Fig6.{ext}')
    plot=ROOT/'scripts/plots/plot_network_fig6_20261030.py'
    if not (before/plot.name).exists():shutil.copy2(plot,before/plot.name)
    if (DATA/'annual_country_indices.csv').exists():
        print('Saved annual reconstruction already exists');return
    (OUT/'analysis_plan.json').write_text(json.dumps(dict(
      question='Compare observed annual domestic city indices with conditional reconstructed indices, using the saved reference and user-requested international model.',
      international_model=MODEL_NAME,selection='User-requested full-model display, not re-selection using annual index errors.' if '--full' in sys.argv else 'Previously saved two-step model',
      years=[2002,2025],countries=76,no_interpolation=True,no_refitting=True,
      predictors='Use the same preceding-four-year-block features and candidate destinations as the saved design; hold these fixed within each target block.',
      conditioning='Each year supplies its own actual origin totals within candidate cells. All other domestic flows remain observed.',
      city_pool='Within each country-year use the union of observed city endpoints and the corresponding candidate destinations, retaining zero strengths for Gini in all series.',
      aggregation='Each annual curve is the median of the same 76 countries. Annual calculations use expected city strengths, not the earlier multinomial replicate means.',
      inference='2002-2013 overlaps model fitting; 2014-2017 validation; 2018-2025 temporal evaluation already explored. Not an unconditional forecast.',
      gap='No pre-study lag network is available for 1998-2001; do not manufacture modeled values for those years.'),ensure_ascii=False,indent=2),encoding='utf8')
    full=dict(np.load(ROOT/'outputs/logical_distance_validation_20261030/domestic_design.npz',allow_pickle=False))
    extra=dict(np.load(ROOT/'outputs/international_signal_validation_20261030/international_features.npz',allow_pickle=False))
    fits=json.loads((ROOT/'outputs/international_signal_validation_20261030/fits.json').read_text())
    x=np.column_stack([full['x'],extra['x']]);models=['B_history_field',MODEL_NAME]
    pr={}
    for model in models:
        f=fits[model];eta=((x[:,f['cols']].astype(float)-f['mean'])/f['scale'])@np.asarray(f['beta'])
        pr[model],_,_,_=probabilities(eta,full['group'])
    c=duckdb.connect()
    od=c.sql(f"SELECT * FROM read_parquet('{(ROOT/'outputs/literature_network_validation_20261029/domestic_od_year.parquet').as_posix()}') WHERE year>=2002").df();c.close()
    od['p']=((od.year-1998)//4).astype(int)
    observed_groups=dict(tuple(od.groupby(['country','p'],sort=False)))
    results=[];audits=[];cities=extra['city_codes']
    for ci,cc in enumerate(full['country_codes']):
        for p in range(1,7):
            rr=np.flatnonzero((full['country']==ci)&(full['p']==p));assert len(rr)>0
            source=cities[extra['origin_index'][rr]];dest=cities[extra['destination_index'][rr]]
            design_pairs=pd.MultiIndex.from_arrays([source,dest]);assert design_pairs.is_unique
            groups,gidx=np.unique(full['group'][rr],return_inverse=True)
            observed=observed_groups[(str(cc),p)]
            observed_pair_index=design_pairs.get_indexer(pd.MultiIndex.from_frame(observed[['o','d']]))
            annual_covered=0
            for year in range(1998+4*p,1998+4*(p+1)):
                yr=observed.year.to_numpy()==year;s=observed.loc[yr]
                match=observed_pair_index[yr];valid=match>=0
                yy=np.zeros(len(rr));np.add.at(yy,match[valid],s.flow.to_numpy()[valid])
                annual_covered+=yy.sum()
                nodes=pd.Index(sorted(set(s.o)|set(s.d)|set(dest)))
                io=nodes.get_indexer(s.o);ii=nodes.get_indexer(s.d);di=nodes.get_indexer(dest)
                strength=np.bincount(io,weights=s.flow,minlength=len(nodes))+np.bincount(ii,weights=s.flow,minlength=len(nodes))
                retained=strength-np.bincount(di,weights=yy,minlength=len(nodes));assert retained.min()>-1e-8
                totals=np.bincount(gidx,weights=yy,minlength=len(groups))
                row=dict(country=str(cc),year=year,p=p,pool_cities=len(nodes),active_cities=int((strength>0).sum()),all_events=float(s.flow.sum()),modeled_events=float(yy.sum()),
                  observed_Gini=gini(strength),observed_Gini_positive=gini(strength[strength>0]),observed_HHI=float(np.square(strength/strength.sum()).sum()))
                for label,model in [('reference',models[0]),('international',models[1])]:
                    expected=pr[model][rr]*totals[gidx]
                    assert np.allclose(np.bincount(gidx,weights=expected,minlength=len(groups)),totals,rtol=1e-10,atol=1e-7)
                    model_strength=retained+np.bincount(di,weights=expected,minlength=len(nodes))
                    assert np.isclose(model_strength.sum(),strength.sum(),rtol=1e-12,atol=1e-7)
                    row[label+'_Gini']=gini(model_strength);row[label+'_HHI']=float(np.square(model_strength/model_strength.sum()).sum())
                results.append(row)
            assert np.isclose(annual_covered,full['y'][rr].sum(),atol=.1)
            audits.append(dict(country=str(cc),p=p,annual_events_reconcile_to_period=True,origin_totals_preserved=True,total_city_strength_preserved=True))
        if ci%15==0:print(time.strftime('%H:%M:%S'),f'Annual reconstruction {ci+1}/76 countries',flush=True)
    frame=pd.DataFrame(results);assert len(frame)==76*24 and np.isfinite(frame.select_dtypes('number')).all().all()
    assert frame.groupby('year').country.nunique().eq(76).all()
    held=frame[frame.year>=2018];assert held.modeled_events.sum()==6984347
    frame.to_csv(DATA/'annual_country_indices.csv',index=False)
    curves=[]
    for year,s in frame.groupby('year'):
        row=dict(year=int(year),countries=len(s),phase='Fitting' if year<=2013 else 'Validation' if year<=2017 else 'Evaluation')
        for m in ['Gini','HHI']:
            for model in ['observed','reference','international']:
                v=s[f'{model}_{m}'];row[f'{model}_{m}']=float(v.median())
                row[f'{model}_{m}_q25']=float(v.quantile(.25));row[f'{model}_{m}_q75']=float(v.quantile(.75))
        curves.append(row)
    pd.DataFrame(curves).to_csv(DATA/'annual_median_curves.csv',index=False)
    summary=dict(years=[2002,2025],international_model=MODEL_NAME,model_columns=fits[MODEL_NAME]['cols'],country_years=len(frame),countries=76,evaluation_modeled_events=float(held.modeled_events.sum()),evaluation_all_events=float(held.all_events.sum()),endpoints=[curves[0],curves[-1]])
    for m in ['Gini','HHI']:
        for model in ['reference','international']:
            summary[model+'_'+m+'_median_abs_error_evaluation']=float((held[model+'_'+m]-held['observed_'+m]).abs().median())
    (DATA/'annual_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    (DATA/'annual_conservation_checks.json').write_text(json.dumps(audits,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2),flush=True)

if __name__=='__main__':main()
