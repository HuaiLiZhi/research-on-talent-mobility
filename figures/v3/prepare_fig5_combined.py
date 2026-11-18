"""Country-level international volume and domestic concentration, both directions combined."""
from __future__ import annotations
import csv,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
DATA=OUT/'source_data';QA=OUT/'QA/Fig5'
CLEAN=ROOT/'data/processed/mobility_city_harmonized_20261020/analysis'
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np
from scipy import stats
from scipy.special import expit,logit
from statsmodels.stats.multitest import multipletests

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(name,rows):
    with (DATA/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def prepare():
    countries=json.loads((OUT/'QA/figure_manifest.json').read_text(encoding='utf8'))['cleaned_data_provenance']['fixed_country_codes']
    assert len(countries)==76 and not set(countries)&{'HK','MO','TW'}
    raw=CLEAN/'flow_top100.parquet';path=str(raw).replace("'","''")
    codes=','.join("'"+c+"'" for c in countries)
    con=duckdb.connect();con.execute("SET threads=4; SET memory_limit='2GB'")
    con.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{path}') WHERE flow>0")
    assert con.execute('SELECT count(*) FROM events WHERE origin=destination').fetchone()[0]==0
    margins=con.execute(f"""WITH city_strengths AS (
        SELECT country,year,city,sum(flow) strength FROM (
            SELECT origin_country country,year,origin city,flow FROM events
            WHERE origin_country=destination_country AND origin_country IN ({codes})
            UNION ALL
            SELECT destination_country country,year,destination city,flow FROM events
            WHERE origin_country=destination_country AND destination_country IN ({codes})
        ) GROUP BY ALL)
        SELECT country,year,list(strength ORDER BY city) FROM city_strengths GROUP BY ALL ORDER BY country,year""").fetchall()
    international={(c,int(y)):float(f) for c,y,f in con.execute(f"""
        SELECT country,year,sum(flow) FROM (
            SELECT origin_country country,year,flow FROM events WHERE origin_country<>destination_country
            UNION ALL
            SELECT destination_country country,year,flow FROM events WHERE origin_country<>destination_country
        ) WHERE country IN ({codes}) GROUP BY ALL""").fetchall()}
    domestic_events={(c,int(y)):float(f) for c,y,f in con.execute(f"""
        SELECT origin_country,year,sum(flow) FROM events
        WHERE origin_country=destination_country AND origin_country IN ({codes}) GROUP BY ALL""").fetchall()}
    con.close()
    reference={(r['country'],int(r['year'])):r for r in read(DATA/'Fig4_all_country_combined_metrics.csv')}
    panel=[]
    for cc,year,vals in margins:
        vals=np.asarray(vals,dtype=float);p=vals/vals.sum();n=len(p)
        hhi=float(p@p);gini=float(2*np.arange(1,n+1)@np.sort(p)/n-(n+1)/n)
        assert n>=2 and np.isclose(vals.sum(),2*domestic_events[cc,year])
        ref=reference[cc,year]
        assert np.isclose(hhi,float(ref['HHI']),atol=1e-12)
        assert np.isclose(gini,float(ref['Gini']),atol=1e-12)
        assert n==int(ref['N'])
        panel.append(dict(country=cc,year=int(year),international_flow=international.get((cc,int(year)),0.),
            domestic_flow_events=domestic_events[cc,year],domestic_city_strength=float(vals.sum()),
            domestic_cities=n,domestic_HHI=hhi,domestic_Gini=gini,domestic_normalized_equivalent=1/(n*hhi)))
    assert len(panel)==2128
    levels=[]
    for cc in countries:
        rs=sorted([r for r in panel if r['country']==cc],key=lambda r:r['year'])
        assert [r['year'] for r in rs]==list(range(1998,2026))
        flow=float(np.mean([r['international_flow'] for r in rs]))
        hhi=float(np.mean([r['domestic_HHI'] for r in rs]));gini=float(np.mean([r['domestic_Gini'] for r in rs]))
        assert flow>0 and 0<hhi<=1 and 0<gini<1
        levels.append(dict(country=cc,years=28,mean_annual_international_flow=flow,
            mean_domestic_HHI=hhi,mean_domestic_Gini=gini,
            mean_domestic_cities=float(np.mean([r['domestic_cities'] for r in rs])),
            total_international_events=sum(r['international_flow'] for r in rs),
            total_domestic_events=sum(r['domestic_flow_events'] for r in rs),
            log10_international_flow=float(np.log10(flow)),log10_domestic_HHI=float(np.log10(hhi))))
    rng=np.random.default_rng(20261021);fits=[];curves=[];boot=[]
    x=np.array([r['log10_international_flow'] for r in levels])
    for metric,transform in [('HHI','log10'),('Gini','logit')]:
        y0=np.array([r['mean_domestic_'+metric] for r in levels])
        y=np.log10(y0) if transform=='log10' else logit(y0)
        result=stats.linregress(x,y);samples=rng.integers(0,76,(5000,76))
        xb=x[samples];yb=y[samples];xc=xb-xb.mean(1,keepdims=True);yc=yb-yb.mean(1,keepdims=True)
        slopes=np.sum(xc*yc,axis=1)/np.sum(xc*xc,axis=1);intercepts=yb.mean(1)-slopes*xb.mean(1)
        grid=np.linspace(float(x.min()),float(x.max()),241)
        predictions=intercepts[:,None]+slopes[:,None]*grid
        lo,hi=np.quantile(predictions,[.025,.975],axis=0)
        fits.append(dict(metric=metric,countries=76,years=28,x_transform='log10',y_transform=transform,
            pearson_r=float(result.rvalue),spearman_r=float(stats.spearmanr(x,y).statistic),
            p_two_sided=float(result.pvalue),slope=float(result.slope),intercept=float(result.intercept),
            r_squared=float(result.rvalue**2),bootstrap_replicates=5000,
            method='OLS of transformed country means; paired-country bootstrap pointwise 95% confidence interval'))
        for xx,ll,hh in zip(grid,lo,hi):
            pred=float(result.intercept+result.slope*xx)
            curves.append(dict(metric=metric,x=float(10**xx),transformed_x=float(xx),transformed_y=pred,
                transformed_ci_low=float(ll),transformed_ci_high=float(hh),
                y=float(10**pred if transform=='log10' else expit(pred)),
                ci_low=float(10**ll if transform=='log10' else expit(ll)),ci_high=float(10**hh if transform=='log10' else expit(hh))))
        for j,(a,b) in enumerate(zip(intercepts,slopes)):
            boot.append(dict(metric=metric,replicate=j+1,intercept=float(a),slope=float(b)))
    for r,p in zip(fits,multipletests([r['p_two_sided'] for r in fits],method='holm')[1]):r['p_holm_two_fits']=float(p)
    write('Fig5_combined_country_year_metrics.csv',panel)
    write('Fig5_combined_country_mean_levels.csv',levels)
    write('Fig5_combined_fits.csv',fits);write('Fig5_combined_fit_curves.csv',curves)
    write('Fig5_combined_fit_bootstrap.csv',boot)
    report=dict(figure='Fig5',edition='v3',countries=76,country_codes=countries,years=list(range(1998,2026)),
        observations=2128,source=str(raw.relative_to(ROOT)),source_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
        international_definition='Annual international inflow plus outflow involving the focal country',
        domestic_definition='At each stable city ID, sum domestic inflow and outflow before recomputing HHI and Gini',
        event_counting='A domestic event contributes strength to both endpoint cities; strength totals are twice domestic event totals',
        mean_definition='Equal-year arithmetic mean of each annual concentration index over 28 years, not pooled-event indices and not an average of directional indices',
        data_checks=dict(combined_metrics_match_Fig4=True,city_strength_equals_twice_domestic_events=True,complete_28_year_panel=True,no_same_city_events=True),
        fits=fits,scope='Cross-country mean-level associations plus within-country partner-city concentration profiles; not concentration trends or causal effects',
        annual_density_definition='All 2128 country-years: international-partner HHI versus domestic-city HHI, defined in partner_concentration_manifest.json',
        repeated_measures='Annual density observations are repeated within 76 countries; no independent-year significance test is reported',
        legacy='Old directional, trend and HHI-contribution tables are auxiliary and not plotted')
    (QA/'data_manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(dict(fits=fits,ranges={k:[min(r[k] for r in levels),max(r[k] for r in levels)] for k in ['mean_annual_international_flow','mean_domestic_HHI','mean_domestic_Gini']}),indent=2))

if __name__=='__main__':prepare()
