"""Forward-time logical-distance tests on aggregate city OD choices only.

No author trajectories are loaded or generated. Historical profiles and network
representations always precede their predicted flows by one four-year period.
"""
from pathlib import Path
import os,sys,json,time,hashlib
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='2'
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps'),str(ROOT/'outputs/country_typology_validation_20261029/python_deps'),str(ROOT/'scripts/reports')]
import numpy as np,pandas as pd,duckdb
from scipy.sparse import coo_matrix
from scipy.optimize import minimize
from scipy.stats import binomtest
from sklearn.decomposition import TruncatedSVD
from validate_cross_scale_mechanisms_20261030 import probabilities,distances
from validate_aggregate_alternatives_20261030 import bootstrap_ci

OUT=ROOT/'outputs/logical_distance_validation_20261030';OUT.mkdir(exist_ok=True,parents=True)
PRE=ROOT/'outputs/cross_scale_mechanism_validation_20261030'
CLEAN=ROOT/'data/processed/mobility_city_harmonized_20261020'
FEATURES=['log_lag_mass','log_geographic_distance','log1p_lag_destination_inflow','log1p_lag_pair_flow',
          'disciplinary_distance','international_partner_distance','latent_partner_distance','missing_field_profile','missing_partner_profile']
SEED=20261030

def log(x):print(time.strftime('%H:%M:%S'),x,flush=True)
def save(name,x):(OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding='utf8')
def readpq(path):
    c=duckdb.connect();s=c.sql(f"SELECT * FROM read_parquet('{path.as_posix()}')").df();c.close();return s
def norm(x):
    s=np.linalg.norm(x,axis=1,keepdims=True);return np.divide(x,s,out=np.zeros_like(x),where=s>0)

def plan():
    if (OUT/'analysis_plan.json').exists():return
    save('analysis_plan.json',dict(date='2026-10-30',status='Exploratory plan saved before this logical-distance comparison.',
      units='City-city-period flow aggregates. No personal trajectories read or synthesized.',
      periods='Seven four-year periods1998-2025; lag one period; train2002-2013,validate2014-2017,test2018-2025.',
      samples='Manuscript76 destination countries. International uses existing top100 foreign-origin exact-distance risk sets; domestic top50 origin cities per country selected from1998-2013 only. Candidate destinations have positive lagged verified stock and coordinates. Zero-flow pairs remain; domestic self pairs removed.',
      distances={'disciplinary':'One minus cosine of lagged26-field city activity-count vectors from independent aggregated stock CSV. Counts can overlap; do not label totals unique people.',
                 'functional':'One minus cosine of TF-IDF weighted city international partner-country count vectors. Both inbound and outbound events define partner-country contexts. Built from preceding-period aggregate international OD.',
                 'latent':'32-dimensional TruncatedSVD of the same preceding-period TF-IDF partner matrix; cosine distance. Fixed rank and seed; no rank search. This is a functional embedding of aggregate profiles, not the trajectory word2vec algorithm.'},
      missing='All models include identical missing-profile indicators. Missing vector similarity is set0 (distance1).',
      comparisons='Geography baseline versus replacing geography with logical distances; adding field/partner/latent distances; adding distances beyond destination inflow AND direct OD history.',
      primary_metric='Country-level paired conditional Poisson deviance reduction on held-out periods; country bootstrap4000. CPC secondary. All candidates and total choice-group counts held identical within comparisons.',
      fitting='Each country has equal total training weight; observed source-city/destination-country/period totals conditioned on.',
      secondary='32D latent partner embedding; all models reported. Pointwise bootstrap intervals, descriptive paired-country signs with Holm-adjusted two-sided binomial tests within split.',
      limits=['Past mobility-derived distance is predictive network information; not independent evidence of causal cultural or institutional mechanisms.','No same-year inversion of the target flow as distance.','No actual language, coauthorship, citation or prestige distances tested.','Conditional allocation cannot identify effect on national total inflows.'],
      manuscript_modified=False))

def prepare():
    plan()
    if not (OUT/'city_field_period.parquet').exists():
        log('Build lagged city-field profiles from aggregate stock records')
        c=duckdb.connect();c.execute("SET threads=3; SET memory_limit='3GB'")
        c.execute(f"CREATE TABLE cw AS SELECT * FROM read_csv('{(CLEAN/'city_crosswalk.csv').as_posix()}',header=true,all_varchar=true)")
        c.execute("""CREATE TABLE gm AS SELECT upper(raw_country) raw_country,try_cast(source_geonameid AS BIGINT) gid,
          min(city_id) city,min(country_code) country FROM cw WHERE analysis_ready='True' AND raw_country IS NOT NULL
          AND try_cast(source_geonameid AS BIGINT) IS NOT NULL GROUP BY1,2
          HAVING count(DISTINCT city_id)=1 AND count(DISTINCT country_code)=1""".replace('BY1','BY 1'))
        c.execute(f"CREATE TABLE catalog AS SELECT city_id,country_code FROM read_csv('{(CLEAN/'cities.csv').as_posix()}',header=true) WHERE analysis_ready")
        source=ROOT/'data/input/stock/count_stock_city_field_year_annual.csv'
        c.execute(f"""CREATE TABLE stock AS SELECT floor((year-1998)/4)::INT p,upper(country_code) raw_country,
          try_cast(city_geonames_id AS BIGINT) gid,city_key,field_display_name field,author_count::DOUBLE mass,works_count::DOUBLE works
          FROM read_csv('{source.as_posix()}',header=true,sample_size=100000)
          WHERE tier='top100pct' AND year BETWEEN1998 AND2025 AND author_count>0 AND field_display_name IS NOT NULL""".replace('BETWEEN1998 AND2025','BETWEEN 1998 AND 2025'))
        c.execute("""CREATE TABLE mapped AS SELECT s.*,coalesce(g.city,cc.city_id) city,
          coalesce(g.country,cc.country_code,s.raw_country) country FROM stock s
          LEFT JOIN gm g ON s.raw_country=g.raw_country AND s.gid=g.gid
          LEFT JOIN catalog cc ON s.city_key=cc.city_id""")
        c.execute(f"""COPY(SELECT p,country,city,field,sum(mass) mass,sum(works) works FROM mapped
          WHERE city IS NOT NULL AND lower(field) NOT IN('unknown','unspecified','') GROUP BY ALL)
          TO '{(OUT/'city_field_period.parquet').as_posix()}'(FORMAT PARQUET,COMPRESSION ZSTD)""")
        c.sql('SELECT p,sum(mass) input_mass,sum(CASE WHEN city IS NOT NULL THEN mass ELSE0 END) mapped_mass FROM mapped GROUP BY1 ORDER BY1'.replace('ELSE0','ELSE 0').replace('BY1','BY 1')).df().to_csv(OUT/'field_profile_mapping_audit.csv',index=False)
        c.close()
    if not (OUT/'domestic_od_period.parquet').exists():
        c=duckdb.connect();c.execute(f"""COPY(SELECT floor((year-1998)/4)::INT p,country,o,d,sum(flow) flow
          FROM read_parquet('{(ROOT/'outputs/literature_network_validation_20261029/domestic_od_year.parquet').as_posix()}') GROUP BY ALL)
          TO '{(OUT/'domestic_od_period.parquet').as_posix()}'(FORMAT PARQUET,COMPRESSION ZSTD)""");c.close()
    return

def representations():
    if (OUT/'representations.npz').exists():return dict(np.load(OUT/'representations.npz',allow_pickle=False))
    fields=readpq(OUT/'city_field_period.parquet');ii=readpq(PRE/'international_city_od_period.parquet')
    mass=readpq(PRE/'city_author_year_mass.parquet');nodes=sorted(set(fields.city)|set(ii.o)|set(ii.d)|set(mass.city))
    index={v:i for i,v in enumerate(nodes)};fcodes=sorted(fields.field.unique());partners=sorted(set(ii.oc)|set(ii.country));fmap={v:i for i,v in enumerate(fcodes)};pcodes={v:i for i,v in enumerate(partners)}
    output=dict(city_codes=np.array(nodes,dtype='U'),field_codes=np.array(fcodes,dtype='U'),partner_countries=np.array(partners,dtype='U'));audit=[]
    for p in range(6):
        f=fields[fields.p==p];F=coo_matrix((f.mass.to_numpy(),(f.city.map(index).to_numpy(),f.field.map(fmap).to_numpy())),shape=(len(nodes),len(fcodes))).toarray().astype('float32');F=norm(F)
        v=ii[ii.p==p];r=np.r_[v.o.map(index),v.d.map(index)];cc=np.r_[v.country.map(pcodes),v.oc.map(pcodes)];w=np.r_[v.flow,v.flow]
        A=coo_matrix((w,(r,cc)),shape=(len(nodes),len(partners))).tocsr();A.sum_duplicates()
        row_sum=np.asarray(A.sum(1)).ravel();idf=np.log((1+int((row_sum>0).sum()))/(1+A.getnnz(axis=0)))+1
        tf=A.multiply(np.divide(1,row_sum,out=np.zeros_like(row_sum),where=row_sum>0)[:,None]).tocsr().multiply(idf[None,:]).tocsr()
        N=norm(tf.toarray().astype('float32'));svd=TruncatedSVD(n_components=32,random_state=SEED,n_iter=7)
        E=norm(svd.fit_transform(tf).astype('float32'));output[f'field_{p}']=F;output[f'partner_{p}']=N;output[f'latent_{p}']=E
        audit.append(dict(period=p,cities_with_field_profile=int((np.linalg.norm(F,axis=1)>0).sum()),cities_with_partner_profile=int((row_sum>0).sum()),latent_explained_variance=float(svd.explained_variance_ratio_.sum())))
        log('Prepared previous-period logical representations '+str(p))
    np.savez_compressed(OUT/'representations.npz',**output);pd.DataFrame(audit).to_csv(OUT/'representation_audit.csv',index=False)
    return output

def logical_features(rep,p,origins,destinations):
    idx=pd.Index(rep['city_codes']);oi=idx.get_indexer(origins);di=idx.get_indexer(destinations);assert (oi>=0).all() and (di>=0).all()
    arrays=[];missing=[]
    for kind in ['field','partner','latent']:
        mat=rep[f'{kind}_{p-1}'];a=mat[oi];b=mat[di];sim=np.clip(a@b.T,-1,1)
        arrays.append((1-sim).astype('float32'))
        if kind!='latent':missing.append(((np.linalg.norm(a,axis=1)==0)[:,None]|(np.linalg.norm(b,axis=1)==0)[None,:]).astype('float32'))
    return arrays+missing

def international_design(rep):
    cache=OUT/'international_design.npz'
    if cache.exists():return dict(np.load(cache,allow_pickle=False))
    old=dict(np.load(PRE/'gravity_design.npz',allow_pickle=False));ii=readpq(PRE/'international_city_od_period.parquet');top=pd.read_csv(PRE/'training_selected_foreign_origins.csv')
    x=np.empty((len(old['y']),9),dtype='float32');x[:,:3]=old['x'][:,[0,1,3]];audits=[]
    for ci,cc in enumerate(old['country_codes']):
        src=top[top.country==cc].o.to_numpy()
        for p in range(1,7):
            rows=np.flatnonzero((old['country']==ci)&(old['p']==p))
            if not len(rows):continue
            g=old['group'][rows];n=int((g==g[0]).sum());dst=old['city_codes'][old['city'][rows[:n]]]
            current=ii[(ii.country==cc)&(ii.p==p)&ii.o.isin(src)&ii.d.isin(dst)]
            present=set(current.o);origins=[o for o in src if o in present]
            expected=current.pivot_table(index='o',columns='d',values='flow',aggfunc='sum',fill_value=0).reindex(index=origins,columns=dst,fill_value=0).to_numpy()
            assert expected.size==len(rows) and np.array_equal(expected.ravel(),old['y'][rows])
            previous=ii[(ii.country==cc)&(ii.p==p-1)&ii.o.isin(origins)&ii.d.isin(dst)]
            h=previous.pivot_table(index='o',columns='d',values='flow',aggfunc='sum',fill_value=0).reindex(index=origins,columns=dst,fill_value=0).to_numpy()
            x[rows,3]=np.log1p(h).ravel();lf=logical_features(rep,p,origins,dst)
            for k,z in enumerate(lf):x[rows,4+k]=z.ravel()
            audits.append(dict(target='I',country=cc,p=p,events=float(expected.sum()),candidate_pairs=len(rows),missing_field_event_fraction=float((expected*lf[3]).sum()/expected.sum()),missing_partner_event_fraction=float((expected*lf[4]).sum()/expected.sum())))
    d={k:old[k] for k in ['y','p','country','group','country_codes']};d['x']=x;assert np.isfinite(x).all()
    np.savez_compressed(cache,**d);pd.DataFrame(audits).to_csv(OUT/'international_profile_coverage.csv',index=False);return d

def domestic_design(rep):
    cache=OUT/'domestic_design.npz'
    if cache.exists():return dict(np.load(cache,allow_pickle=False))
    od=readpq(OUT/'domestic_od_period.parquet');m=readpq(PRE/'city_author_year_mass.parquet');m['p']=(m.year-1998)//4;m=m.groupby(['p','country','city'],as_index=False).mass.sum();m['mass']/=4
    coords=pd.read_csv(CLEAN/'cities.csv').drop_duplicates('city_id').set_index('city_id');coords=coords[coords.latitude.between(-90,90)&coords.longitude.between(-180,180)]
    countries=pd.read_csv(ROOT/'outputs/mechanism_validation_20261030/sample76.csv').country.tolist()
    top=od[(od.p<=3)&od.country.isin(countries)&od.o.isin(coords.index)].groupby(['country','o']).flow.sum().reset_index().sort_values(['country','flow'],ascending=[True,False]).groupby('country').head(50)
    top.to_csv(OUT/'domestic_training_selected_origins.csv',index=False);xs=[];ys=[];cs=[];ps=[];gs=[];audits=[];gid=0
    for ci,cc in enumerate(countries):
        src=top[top.country==cc].o.to_numpy()
        for p in range(1,7):
            s=m[(m.country==cc)&(m.p==p-1)&m.city.isin(coords.index)].sort_values('city');dst=s.city.to_numpy()
            if len(dst)<2:continue
            current=od[(od.country==cc)&(od.p==p)&od.o.isin(src)&od.d.isin(dst)];present=set(current.o);origins=np.array([o for o in src if o in present])
            if not len(origins):continue
            y=current.pivot_table(index='o',columns='d',values='flow',aggfunc='sum',fill_value=0).reindex(index=origins,columns=dst,fill_value=0).to_numpy()
            previous=od[(od.country==cc)&(od.p==p-1)];hp=previous.pivot_table(index='o',columns='d',values='flow',aggfunc='sum',fill_value=0).reindex(index=origins,columns=dst,fill_value=0).to_numpy()
            hd=previous.groupby('d').flow.sum().reindex(dst).fillna(0).to_numpy();a=coords.loc[origins];b=coords.loc[dst]
            dist=distances(a.latitude.to_numpy(),a.longitude.to_numpy(),b.latitude.to_numpy(),b.longitude.to_numpy());shape=y.shape
            lf=logical_features(rep,p,origins,dst);keep=origins[:,None]!=dst[None,:]
            x=np.stack([np.broadcast_to(np.log(s.mass.to_numpy()),shape),np.log(dist),np.broadcast_to(np.log1p(hd),shape),np.log1p(hp)]+lf,axis=-1)[keep]
            assert np.all(y[~keep]==0);yy=y[keep];gg=np.broadcast_to(np.arange(gid,gid+len(origins))[:,None],shape)[keep];gid+=len(origins)
            xs.append(x.astype('float32'));ys.append(yy.astype('float32'));cs.append(np.full(len(yy),ci,dtype='int16'));ps.append(np.full(len(yy),p,dtype='int8'));gs.append(gg.astype('int32'))
            all_events=float(od[(od.country==cc)&(od.p==p)].flow.sum())
            audits.append(dict(target='D',country=cc,p=p,events=float(yy.sum()),candidate_pairs=len(yy),all_country_events=all_events,flow_coverage=float(yy.sum()/all_events),missing_field_event_fraction=float((y*lf[3]).sum()/y.sum()),missing_partner_event_fraction=float((y*lf[4]).sum()/y.sum())))
    d=dict(x=np.vstack(xs),y=np.concatenate(ys),country=np.concatenate(cs),p=np.concatenate(ps),group=np.concatenate(gs),country_codes=np.array(countries,dtype='U'))
    assert np.isfinite(d['x']).all();np.savez_compressed(cache,**d);pd.DataFrame(audits).to_csv(OUT/'domestic_profile_coverage.csv',index=False);return d

def fit(d,cols):
    mask=d['p']<=3;x=d['x'][mask][:,cols].astype(float);y=d['y'][mask].astype(float);g=d['group'][mask];cc=d['country'][mask]
    mean=x.mean(0);scale=x.std(0);scale[scale<1e-10]=1;z=(x-mean)/scale
    starts=np.r_[0,np.flatnonzero(np.diff(g))+1];sizes=np.diff(np.r_[starts,len(g)]);tot=np.add.reduceat(y,starts);tt=np.repeat(tot,sizes)
    ctot=np.bincount(cc,weights=y);w=1/(np.count_nonzero(ctot)*ctot[cc]);gw=w[starts]
    def objective(beta):
        eta=z@beta;pr,_,_,lse=probabilities(eta,g);err=(tt*pr-y)*w
        return np.dot(gw*tot,lse)-np.dot(w*y,eta),z.T@err
    res=minimize(objective,np.zeros(len(cols)),jac=True,method='L-BFGS-B',options=dict(maxiter=300,gtol=1e-7,ftol=1e-12))
    grad=float(np.max(np.abs(objective(res.x)[1])));assert res.success and grad<1e-5,(res.message,grad)
    return dict(cols=cols,beta=res.x.tolist(),mean=mean.tolist(),scale=scale.tolist(),coefficients=(res.x/scale).tolist(),gradient=grad,iterations=int(res.nit))

def evaluate(d,f,name,target):
    mask=d['p']>=4;x=d['x'][mask][:,f['cols']];eta=((x-np.array(f['mean']))/np.array(f['scale']))@np.array(f['beta'])
    y=d['y'][mask].astype(float);g=d['group'][mask];pr,starts,sizes,_=probabilities(eta,g);mu=pr*np.repeat(np.add.reduceat(y,starts),sizes)
    dev=2*(np.where(y>0,y*np.log(np.maximum(y,1e-300)/np.maximum(mu,1e-300)),0)-y+mu)
    rows=[];cs=d['country'][mask];ps=d['p'][mask]
    for ci in np.unique(cs):
        for p in [4,5,6]:
            k=(cs==ci)&(ps==p)
            if not k.any():continue
            rows.append(dict(target=target,model=name,country=str(d['country_codes'][ci]),p=p,events=float(y[k].sum()),deviance=float(dev[k].sum()),CPC=float(np.minimum(y[k],mu[k]).sum()/y[k].sum())))
    assert np.isfinite(mu).all();return rows

def run():
    prepare();rep=representations();fits={};scores=[]
    avail=[7,8];geo=[0,1]+avail;history=[0,1,2,3]+avail
    configs={'G_geography':geo,'L_logic_only':[0,4,5]+avail,'G_field':geo+[4],'G_partner':geo+[5],'G_latent':geo+[6],'G_both':geo+[4,5],
             'H_history':history,'H_field':history+[4],'H_partner':history+[5],'H_latent':history+[6],'H_both':history+[4,5]}
    for target,builder in [('I',international_design),('D',domestic_design)]:
        log('Build choice design '+target);d=builder(rep);fits[target]={}
        for name,cols in configs.items():
            log('Fit '+target+' '+name);f=fit(d,cols);fits[target][name]=f;scores.extend(evaluate(d,f,name,target));save('fits.json',fits)
        del d
    metrics=pd.DataFrame(scores);metrics.to_csv(OUT/'heldout_country_period_metrics.csv',index=False);rows=[];contrasts=[];rng=np.random.default_rng(SEED)
    comparisons=[('G_geography','L_logic_only'),('G_geography','G_field'),('G_geography','G_partner'),('G_geography','G_latent'),('G_geography','G_both'),('G_geography','H_history'),
                 ('H_history','H_field'),('H_history','H_partner'),('H_history','H_latent'),('H_history','H_both')]
    for split,periods in [('validation',[4]),('test',[5,6])]:
        for target in ['I','D']:
            s=metrics[(metrics.target==target)&metrics.p.isin(periods)].groupby(['country','model'])[['events','deviance']].sum().reset_index()
            cpc=metrics[(metrics.target==target)&metrics.p.isin(periods)].groupby(['country','model']).apply(lambda z:np.average(z.CPC,weights=z.events),include_groups=False).rename('CPC').reset_index();s=s.merge(cpc,on=['country','model'])
            for a,b in comparisons:
                z=s[s.model==a].merge(s[s.model==b],on='country',suffixes=('_base','_new'));v=100*(1-z.deviance_new/z.deviance_base);cg=z.CPC_new-z.CPC_base
                ci=bootstrap_ci(v,rng);cci=bootstrap_ci(cg,rng);n=int((v!=0).sum());pv=binomtest(int((v>0).sum()),n,.5).pvalue
                rows.append(dict(split=split,target=target,base=a,new=b,countries=len(z),median_deviance_reduction_pct=float(v.median()),CI_low=ci[0],CI_high=ci[1],countries_better=int((v>0).sum()),median_CPC_gain=float(cg.median()),CPC_CI_low=cci[0],CPC_CI_high=cci[1],event_weighted_deviance_reduction_pct=float(100*(1-z.deviance_new.sum()/z.deviance_base.sum())),paired_sign_p=float(pv)))
                z['gain_pct']=v;z['split']=split;z['target']=target;z['base']=a;z['new']=b;contrasts.append(z)
    summary=pd.DataFrame(rows)
    for split,s in summary.groupby('split'):
        idx=s.paired_sign_p.sort_values().index;pv=summary.loc[idx,'paired_sign_p'].to_numpy();summary.loc[idx,'paired_sign_p_holm']=np.minimum(1,np.maximum.accumulate(pv*(len(pv)-np.arange(len(pv)))))
    summary.to_csv(OUT/'comparison_summary.csv',index=False);pd.concat(contrasts).to_csv(OUT/'paired_country_contrasts.csv',index=False)
    save('runtime.json',dict(features=FEATURES,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),numpy=np.__version__,pandas=pd.__version__,duckdb=duckdb.__version__,no_individual_records_read=True))
    print(summary[summary.split=='test'].to_string(index=False),flush=True)

if __name__=='__main__':run()
