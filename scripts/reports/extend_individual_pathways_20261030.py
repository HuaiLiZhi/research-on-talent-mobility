"""Return/onward route profiles and hierarchy-matched domestic pathways.

Person identifiers stay in temporary in-memory/spill tables and are never
written to deliverable CSVs. This subset is not the canonical manuscript sample.
"""
from pathlib import Path
import os,sys,json,time,hashlib
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[key]='2'
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'outputs/literature_pathway_extension_20261030'
sys.path[:0]=[str(ROOT/'outputs/country_typology_validation_20261029/python_deps'),str(ROOT/'tmp/nhb_fig2_python_deps')]
import numpy as np,pandas as pd,duckdb
from scipy.stats import binomtest,spearmanr
from statsmodels.stats.multitest import multipletests

SOURCE=ROOT/'data/input/mobility/openalex_mobility_rates/author_year_primary_location.parquet'
CLEAN=ROOT/'data/processed/mobility_city_harmonized_20261020'
SEED=20261030
def q(p):return "'"+str(p).replace("'","''")+"'"
def log(s):print(time.strftime('%H:%M:%S'),s,flush=True)
def js(name,x):(OUT/name).write_text(json.dumps(x,indent=2,ensure_ascii=False),encoding='utf8')

def reconstruct(c):
    log('Reconstruct chronological affiliation transitions, including observation gaps')
    c.execute(f"CREATE TABLE cw AS SELECT * FROM read_csv({q(CLEAN/'city_crosswalk.csv')},header=true,all_varchar=true)")
    c.execute("""CREATE TABLE gm AS SELECT raw_country original_country,try_cast(source_geonameid AS BIGINT) gid,
      min(city_id) city,min(country_code) country FROM cw WHERE analysis_ready='True'
      AND try_cast(source_geonameid AS BIGINT) IS NOT NULL AND raw_country IS NOT NULL
      GROUP BY1,2 HAVING count(DISTINCT city_id)=1 AND count(DISTINCT country_code)=1""".replace('GROUP BY1','GROUP BY 1'))
    c.execute(f"""CREATE TABLE transitions AS SELECT * FROM (
       SELECT author_id,year,country_code to_country_code,city_key to_city_key,geo_city,
         coalesce(field_display_name,'Unspecified') field,
         year-min(year) OVER(PARTITION BY author_id) observed_career_span,
         max(year) OVER(PARTITION BY author_id) last_year,
         lag(year) OVER w previous_year,lag(country_code) OVER w from_country_code,
         lag(city_key) OVER w from_city_key,lag(geo_city) OVER w from_city
       FROM read_parquet({q(SOURCE)}) WHERE city_key IS NOT NULL AND year<=2025
       WINDOW w AS(PARTITION BY author_id ORDER BY year))
       WHERE year BETWEEN1998 AND2025 AND from_city IS NOT NULL AND geo_city IS NOT NULL
       AND (from_city_key<>to_city_key OR coalesce(from_country_code,'')<>coalesce(to_country_code,''))""".replace('BETWEEN1998 AND2025','BETWEEN 1998 AND 2025'))
    raw=c.sql('SELECT count(*) FROM transitions').fetchone()[0]
    c.execute("""CREATE TABLE events AS SELECT t.author_id,t.year,t.field,t.observed_career_span,t.last_year,
      year-previous_year obs_gap,g.country oc,h.country dc,g.city o,h.city d,
      (g.city IS NOT NULL AND h.city IS NOT NULL) verified
      FROM transitions t LEFT JOIN gm g ON t.from_country_code=g.original_country
        AND try_cast(regexp_extract(t.from_city_key,'^gn:([0-9]+)$',1) AS BIGINT)=g.gid
      LEFT JOIN gm h ON t.to_country_code=h.original_country
        AND try_cast(regexp_extract(t.to_city_key,'^gn:([0-9]+)$',1) AS BIGINT)=h.gid
      WHERE(g.city IS NULL OR h.city IS NULL OR g.city<>h.city)""")
    c.execute('DROP TABLE transitions')
    # Publication observation can continue when the geographic key is missing.
    # Follow-up and observed-career start therefore use ALL author-year records.
    c.execute(f"""CREATE TEMP TABLE career_bounds AS SELECT p.author_id,min(p.year) first_year,max(p.year) final_year
      FROM read_parquet({q(SOURCE)}) p SEMI JOIN(SELECT DISTINCT author_id FROM events) e ON p.author_id=e.author_id
      WHERE p.year<=2025 GROUP BY p.author_id""")
    c.execute('UPDATE events SET last_year=b.final_year,observed_career_span=events.year-b.first_year FROM career_bounds b WHERE events.author_id=b.author_id')
    c.execute('DROP TABLE career_bounds')
    accounting=c.sql("SELECT CASE WHEN NOT verified THEN 'unresolved' WHEN oc<>dc THEN 'international' ELSE 'domestic' END category,count(*) records FROM events GROUP BY1".replace('BY1','BY 1')).df()
    accounting.to_csv(OUT/'microdata_accounting.csv',index=False)
    c.execute("""CREATE TABLE sequenced AS SELECT *,lead(year) OVER w next_year,lead(dc) OVER w next_country,
      lead(o) OVER w next_origin,lead(d) OVER w next_city,lead(verified) OVER w next_verified,
      lead(obs_gap) OVER w next_gap,lead(field) OVER w next_field,
      lead(observed_career_span) OVER w next_career
      FROM events WINDOW w AS(PARTITION BY author_id ORDER BY year)""")
    c.execute("""CREATE TABLE arrivals AS SELECT * FROM(
      SELECT *,row_number() OVER(PARTITION BY author_id,dc ORDER BY year) rn
      FROM sequenced WHERE verified AND oc<>dc) WHERE rn=1 AND year BETWEEN2012 AND2018""".replace('BETWEEN2012 AND2018','BETWEEN 2012 AND 2018'))
    c.execute('DROP TABLE sequenced')
    log(f'Raw changes {raw:,}; mapped micro-event subset created')
    return raw,accounting

PATHS=['domestic_redistribution','previous_origin_return','third_country_onward','no_recorded_intercity_change','unresolved_next']
def route_profiles(c,sample):
    log('Split five/three-year routes into domestic, previous-origin return and onward countries')
    allout=[];arrchecks=[]
    for horizon in [3,5]:
        for gap in [0,1,2]:
            for cohort in ['all','early','late']:
                filt='year BETWEEN 2012 AND 2018' if cohort=='all' else ('year BETWEEN 2012 AND 2014' if cohort=='early' else 'year BETWEEN 2015 AND 2018')
                strict='' if gap==0 else f'AND obs_gap<={gap} AND (next_year IS NULL OR next_year>year+{horizon} OR next_gap<={gap})'
                sql=f"""WITH s AS(SELECT dc country,CASE
                  WHEN next_year<=year+{horizon} AND NOT next_verified THEN 'unresolved_next'
                  WHEN next_year<=year+{horizon} AND next_country=dc THEN 'domestic_redistribution'
                  WHEN next_year<=year+{horizon} AND next_country=oc THEN 'previous_origin_return'
                  WHEN next_year<=year+{horizon} THEN 'third_country_onward'
                  ELSE 'no_recorded_intercity_change' END path
                  FROM arrivals WHERE last_year>=year+{horizon} AND {filt} {strict})
                  SELECT country,path,count(*) records FROM s GROUP BY 1,2"""
                r=c.sql(sql).df();r=r[r.country.isin(sample)].copy()
                r['horizon']=horizon;r['max_observation_gap']=gap;r['cohort']=cohort
                allout.append(r)
    allout=pd.concat(allout,ignore_index=True)
    allout.to_csv(OUT/'country_route_profile_variants.csv',index=False)
    p=allout[(allout.horizon==5)&(allout.max_observation_gap==0)&(allout.cohort=='all')].pivot(index='country',columns='path',values='records').fillna(0).reindex(columns=PATHS,fill_value=0)
    p['total']=p.sum(axis=1)
    for x in PATHS:p[x+'_share']=p[x]/p.total
    p['dominant_path']=p[[x+'_share' for x in PATHS[:-1]]].idxmax(axis=1).str.replace('_share','',regex=False)
    rng=np.random.default_rng(SEED);win=[]
    for cc,row in p.iterrows():
        counts=row[PATHS[:-1]].to_numpy(dtype=float);n=int(counts.sum());prob=counts/n
        draws=rng.multinomial(n,prob,size=1000)
        win.append(dict(country=cc,dominant_path=row.dominant_path,dominant_bootstrap_fraction=float(np.mean(draws.argmax(1)==prob.argmax()))))
    p=p.reset_index().merge(pd.DataFrame(win),on=['country','dominant_path'])
    p.to_csv(OUT/'country_five_year_path_profiles.csv',index=False)
    p[PATHS].sum().rename('records').reset_index().rename(columns={'index':'path'}).to_csv(OUT/'pooled_five_year_path_counts.csv',index=False)
    return p,allout

def hierarchy_benchmarks(c,sample):
    log('Prepare same-cohort domestic continuations and early city hierarchy')
    c.register('sample',pd.DataFrame({'country':sample}))
    c.execute("""CREATE TABLE cohort AS SELECT a.author_id,a.dc country,a.year arrival_year,a.d arrival_city,
      a.next_year move_year,a.next_origin o,a.next_city d,a.next_field field,
      CASE WHEN a.next_career<5 THEN0 WHEN a.next_career<10 THEN1 ELSE2 END career_band,
      a.year+5 required_last_year,a.obs_gap,a.next_gap
      FROM arrivals a JOIN sample s ON a.dc=s.country WHERE a.last_year>=a.year+5
      AND a.next_year<=a.year+5 AND a.next_verified AND a.next_country=a.dc""".replace('THEN0','THEN 0').replace('THEN1','THEN 1').replace('ELSE2','ELSE 2'))
    mismatch=c.sql('SELECT count(*) FROM cohort WHERE o<>arrival_city').fetchone()[0]
    assert mismatch==0
    # All reference moves share the same microdata mapping and transition definition.
    # Remove cohort next events, not whole careers. Remaining events are other
    # domestic transitions and may include other internationally experienced authors.
    c.execute("""CREATE TABLE comparison AS SELECT e.dc country,e.o,e.d,e.year move_year,e.field,
      CASE WHEN e.observed_career_span<5 THEN0 WHEN e.observed_career_span<10 THEN1 ELSE2 END career_band,
      e.last_year FROM events e JOIN sample s ON e.dc=s.country
      ANTI JOIN cohort a ON e.author_id=a.author_id AND e.year=a.move_year
      WHERE e.verified AND e.oc=e.dc AND e.year BETWEEN2012 AND2023""".replace('THEN0','THEN 0').replace('THEN1','THEN 1').replace('ELSE2','ELSE 2').replace('BETWEEN2012 AND2023','BETWEEN 2012 AND 2023'))
    c.execute(f"""CREATE TABLE score AS SELECT country,city,sum(strength) early_strength
      FROM read_parquet({q(ROOT/'outputs/country_typology_validation_20261029/city_year_strengths.parquet')})
      WHERE geography='domestic_intercity' AND year<=2011 GROUP BY1,2""".replace('BY1','BY 1'))
    c.execute(f"""CREATE TABLE mass AS SELECT country,city_id city,sum(mass)/2 early_mass
      FROM read_parquet({q(ROOT/'outputs/gravity_classification_20261029/city_stock.parquet')}) WHERE p<2 GROUP BY1,2""".replace('BY1','BY 1'))
    rows=[];support=[]
    configs=[('origin_year',False,False),('origin_year_field',True,False),('origin_year_field_career_observation',True,True)]
    for label,field,full in configs:
        log('Construct benchmark '+label)
        cols='country,o,move_year'+(',field' if field else '')+(',career_band,required_last_year' if full else '')
        c.execute('DROP TABLE IF EXISTS strata')
        c.execute(f'CREATE TABLE strata AS SELECT row_number() OVER() stratum_id,* FROM(SELECT {cols},count(*) n FROM cohort GROUP BY ALL)')
        join='a.country=b.country AND a.o=b.o AND a.move_year=b.move_year'+(' AND a.field=b.field' if field else '')+(' AND a.career_band=b.career_band AND b.last_year>=a.required_last_year' if full else '')
        c.execute('DROP TABLE IF EXISTS risk')
        c.execute(f'CREATE TABLE risk AS SELECT a.stratum_id,a.country,b.d,count(*) weight FROM strata a JOIN comparison b ON {join} GROUP BY ALL')
        if full:
            c.execute(f"COPY strata TO {q(OUT/'full_matching_strata.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)")
            c.execute(f"COPY risk TO {q(OUT/'full_matching_other_destination_counts.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)")
            cohort_join='a.country=x.country AND a.o=x.o AND a.move_year=x.move_year AND a.field=x.field AND a.career_band=x.career_band AND a.required_last_year=x.required_last_year'
            c.execute(f"COPY(SELECT a.stratum_id,x.country,x.arrival_city,x.d,count(*) weight FROM cohort x JOIN strata a ON {cohort_join} GROUP BY ALL) TO {q(OUT/'full_matching_cohort_destination_counts.parquet')} (FORMAT PARQUET,COMPRESSION ZSTD)")
        c.execute('DROP TABLE IF EXISTS reference')
        c.execute("""CREATE TABLE reference AS SELECT r.stratum_id,sum(weight) risk_events,
          sum(weight*ln(1+coalesce(s.early_strength,0)))/sum(weight) ref_log_strength,
          sum(weight*(coalesce(s.early_strength,0)>coalesce(o.early_strength,0))::INT)/sum(weight) ref_upward,
          sum(weight*(coalesce(s.early_strength,0)>0)::INT)/sum(weight) ref_established,
          sum(weight*ln(1+coalesce(m.early_mass,0)))/sum(weight) ref_log_mass
          FROM risk r JOIN strata a USING(stratum_id) LEFT JOIN score s ON r.country=s.country AND r.d=s.city
          LEFT JOIN score o ON a.country=o.country AND a.o=o.city
          LEFT JOIN mass m ON r.country=m.country AND r.d=m.city GROUP BY r.stratum_id""")
        match='a.country=x.country AND a.o=x.o AND a.move_year=x.move_year'+(' AND a.field=x.field' if field else '')+(' AND a.career_band=x.career_band AND a.required_last_year=x.required_last_year' if full else '')
        data=c.sql(f"""SELECT x.country,x.arrival_year,x.obs_gap,x.next_gap,
          ln(1+coalesce(s.early_strength,0))-ln(1+coalesce(o.early_strength,0)) observed_log_change,
          (coalesce(s.early_strength,0)>coalesce(o.early_strength,0))::INT observed_upward,
          (coalesce(s.early_strength,0)>0)::INT observed_established,
          ln(1+coalesce(m.early_mass,0))-ln(1+coalesce(mo.early_mass,0)) observed_mass_change,
          r.ref_log_strength-ln(1+coalesce(o.early_strength,0)) reference_log_change,
          r.ref_upward,r.ref_established,r.ref_log_mass-ln(1+coalesce(mo.early_mass,0)) reference_mass_change,
          r.risk_events
          FROM cohort x JOIN strata a ON {match} JOIN reference r USING(stratum_id)
          LEFT JOIN score s ON x.country=s.country AND x.d=s.city
          LEFT JOIN score o ON x.country=o.country AND x.o=o.city
          LEFT JOIN mass m ON x.country=m.country AND x.d=m.city
          LEFT JOIN mass mo ON x.country=mo.country AND x.o=mo.city""").df()
        # Country-level means, no person identifiers are exported.
        for variation in ['all','early_cohort','late_cohort','gap1','gap2']:
            d=data if variation=='all' else (data[data.arrival_year<=2014] if variation=='early_cohort' else data[data.arrival_year>=2015] if variation=='late_cohort' else data[(data.obs_gap<=int(variation[-1]))&(data.next_gap<=int(variation[-1]))])
            for cc,g in d.groupby('country'):
                rows.append(dict(benchmark=label,variation=variation,country=cc,records=len(g),
                    observed_log_change=g.observed_log_change.mean(),reference_log_change=g.reference_log_change.mean(),
                    excess_log_strength=(g.observed_log_change-g.reference_log_change).mean(),
                    observed_upward=g.observed_upward.mean(),reference_upward=g.ref_upward.mean(),excess_upward=(g.observed_upward-g.ref_upward).mean(),
                    observed_established=g.observed_established.mean(),reference_established=g.ref_established.mean(),excess_established=(g.observed_established-g.ref_established).mean(),
                    observed_mass_change=g.observed_mass_change.mean(),reference_mass_change=g.reference_mass_change.mean(),excess_log_mass=(g.observed_mass_change-g.reference_mass_change).mean()))
        counts=c.sql('SELECT country,count(*) all_records FROM cohort GROUP BY1'.replace('BY1','BY 1')).df()
        matched=data.groupby('country').size().rename('matched_records').reset_index()
        support.append(counts.merge(matched,on='country',how='left').fillna(0).assign(benchmark=label))
        del data
    r=pd.DataFrame(rows);r.to_csv(OUT/'country_hierarchy_benchmarks.csv',index=False)
    sup=pd.concat(support,ignore_index=True);sup['matched_fraction']=sup.matched_records/sup.all_records
    sup.to_csv(OUT/'benchmark_support_by_country.csv',index=False)
    # Independent cross-country reporting. No individual-level p values.
    sums=[];rng=np.random.default_rng(SEED)
    for (label,variation),s in r.groupby(['benchmark','variation']):
        for minimum in [100,500]:
            z=s[s.records>=minimum]
            if len(z)<3:continue
            for metric in ['excess_log_strength','excess_upward','excess_established','excess_log_mass']:
                a=z[metric].to_numpy();nz=a[np.abs(a)>1e-12];bs=np.median(a[rng.integers(0,len(a),(4000,len(a)))],axis=1)
                sums.append(dict(benchmark=label,variation=variation,min_records=minimum,metric=metric,countries=len(z),records=int(z.records.sum()),median=float(np.median(a)),median_CI_low=float(np.quantile(bs,.025)),median_CI_high=float(np.quantile(bs,.975)),positive=int((a>0).sum()),p_sign=float(binomtest(int((nz>0).sum()),len(nz),.5).pvalue) if len(nz) else 1.))
    sums=pd.DataFrame(sums);sums['p_holm_primary']=np.nan
    mask=(sums.benchmark=='origin_year_field_career_observation')&(sums.variation=='all')&(sums.min_records==100)&(sums.metric!='excess_log_mass')
    sums.loc[mask,'p_holm_primary']=multipletests(sums.loc[mask,'p_sign'],method='holm')[1]
    sums.to_csv(OUT/'hierarchy_benchmark_summary.csv',index=False)
    return r,sums,sup

def main():
    c=duckdb.connect();c.execute("SET threads=4;SET memory_limit='4GB'; SET preserve_insertion_order=false")
    c.execute(f'SET temp_directory={q(OUT/"duckdb_temp")}')
    raw,accounting=reconstruct(c)
    sample=pd.read_csv(ROOT/'figures/v3/source_data/Fig4_country_concentration_trends.csv').country.tolist()
    p,variants=route_profiles(c,sample)
    # Exact baseline comparison with the previous pilot guards source/sequence changes.
    old=pd.read_csv(ROOT/'outputs/literature_network_validation_20261029/individual_paths_matched76.csv')
    a=p.merge(old,on='country',suffixes=('_new','_old'))
    for fresh,previous in [('domestic_redistribution_new','domestic_redistribution_old'),('total','adequate_arrivals')]:
        assert np.allclose(a[fresh],a[previous]),(fresh,previous)
    assert np.allclose(a.previous_origin_return+a.third_country_onward,a.international_departure)
    log('Previous five-year route accounting reproduced')
    r,sums,sup=hierarchy_benchmarks(c,sample)
    m=dict(date='2026-10-30',source=str(SOURCE),raw_changes=raw,unreconciled_raw_difference=30335569-raw,microdata_accounting=accounting.to_dict('records'),
        sample_countries=len(p),five_year_followup_records=int(p.total.sum()),route_counts=p[PATHS].sum().astype(int).to_dict(),
        previous_pilot_baseline_reproduced=True,manuscript_modified=False,seed=SEED,
        author_identifiers_exported=False,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    js('manifest.json',m);c.close()
    log('DONE');print(json.dumps(m,indent=2));print(sums[(sums.variation=='all')&(sums.min_records==100)].to_string(index=False))

if __name__=='__main__':main()
