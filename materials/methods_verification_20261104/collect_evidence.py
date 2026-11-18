from pathlib import Path
import ast,csv,json,hashlib,shutil,sys,datetime,collections,zipfile
ROOT=Path.cwd(); OA=Path('D:/社会物理学论文/code/OpenAlex'); OUT=ROOT/'outputs/methods_evidence_audit_20261104';CLEAN=ROOT/'data/processed/mobility_city_harmonized_20261020'
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import pandas as pd,numpy as np
CAT={'fixed':'01_fixed_new_cities','rarefaction':'02_equal_event_sampling','model':'03_models','clean':'04_geographic_cleaning','samples':'05_samples_groups'}
for folder in CAT.values():
 for sub in ['original','exports_20261104']:(OUT/folder/sub).mkdir(parents=True,exist_ok=True)
manifest=json.loads((CLEAN/'manifest.json').read_text(encoding='utf-8'));records=[];registered={};missing=[]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def add(p,category,role,proof='',saved_hash=None):
 p=Path(p);p=p if p.is_absolute() else ROOT/p;key=(str(p),category)
 if key in registered:return registered[key]
 if not p.is_file():missing.append({'category':category,'path':str(p),'role':role});return None
 st=p.stat();dest=None
 if p.suffix.lower() in ['.py','.sql','.json','.csv','.md','.yml','.yaml','.txt'] and st.st_size<=8*1024*1024:
  dest=OUT/CAT[category]/'original'/p.name
  if dest.exists() and sha(dest)!=sha(p):dest=dest.with_name(hashlib.sha256(str(p).encode()).hexdigest()[:8]+'__'+p.name)
  shutil.copy2(p,dest)
 current_hash=sha(p) if st.st_size<=30*1024*1024 else None
 r={'category':category,'role':role,'source_path':str(p),'bytes':st.st_size,'modified_utc':datetime.datetime.fromtimestamp(st.st_mtime,datetime.timezone.utc).isoformat(),'sha256_current':current_hash,'sha256_historical':saved_hash,'historical_hash_matches':(current_hash==saved_hash) if current_hash and saved_hash else None,'local_copy':str(dest.relative_to(OUT)) if dest else None,'copy_policy':'historical file copied unchanged' if dest else 'path only; large or binary file','evidence':proof,'csv_rows':None,'csv_columns':None}
 if p.suffix.lower()=='.csv' and st.st_size<8*1024*1024:
  with p.open(encoding='utf-8-sig',newline='') as h:
   rd=csv.reader(h);r['csv_columns']=next(rd,[]);r['csv_rows']=sum(1 for _ in rd)
 records.append(r);registered[key]=r;return r
fixedbase=ROOT/'outputs/prism_fig2_5_20261023/QA/results_20261023';rareb=ROOT/'outputs/cross_scale_mechanism_validation_20261030'
for n in ['verify_combined_cities.py','combined_city_checks.json','combined_fixed_city_annual.csv','combined_fixed_city_trends.csv','combined_post1998_city_cohort.csv']:add(fixedbase/n,'fixed','Historical fixed-city/new-city analysis','Program writes these filenames; summary stores input hash')
for n in ['Fig4_all_country_combined_metrics.csv','Fig4_country_concentration_trends.csv']:add(ROOT/'figures/v3/source_data'/n,'fixed','All-city annual metrics / fitted classification','Comparison in fixed-city verification')
checks=json.loads((fixedbase/'combined_city_checks.json').read_text());add(CLEAN/'analysis/domestic_city_margins.csv','fixed','Archived city-year margins','Hash recorded by historical verifier',checks['source_sha256'])
for sub in ['', 'rarefaction_200_independent_seed']:
 for n in ['event_rarefaction_plan.json','event_rarefaction_summary.json','event_rarefaction_annual.csv','event_rarefaction_trends.csv']:add(rareb/sub/n,'rarefaction','Original '+('200-repetition independent-seed run' if sub else '50-repetition diagnostic run'),'Plan records seed/repetitions; results store mean/quantiles, not individual draws')
add(ROOT/'scripts/reports/validate_event_rarefaction_20261030.py','rarefaction','Historical rarefaction entry point','Identical to November1 archived snapshot')
add(ROOT/'outputs/literature_network_validation_20261029/domestic_od_year.parquet','rarefaction','Archived annual domestic OD input')
add(CLEAN/'count_mobility_flow_annual_clean.parquet','rarefaction','Archived international input','top100pct + international',manifest['output_files']['count_mobility_flow_annual_clean.parquet']['sha256'])
for folder in [ROOT/'outputs/international_signal_validation_20261030',ROOT/'outputs/logical_distance_validation_20261030',ROOT/'outputs/results_network_revision_20261030/analysis',ROOT/'outputs/fig6_full_model_revision_20261030/analysis']:
 for p in folder.iterdir():
  if p.is_file() and p.suffix.lower() in ['.json','.csv','.npz','.parquet']:add(p,'model','Historical model configuration / fit / input / evaluation','Saved in '+str(folder.relative_to(ROOT)))
for n in ['analysis_plan.json','final_validation.json']:add(ROOT/'outputs/fig6_full_model_revision_20261030'/n,'model','Integrated annual reconstruction record','A_all_international_signals; no refitting')
for n in ['Fig6_evaluation_errors.csv','Fig6_evaluation_country_year_indices.csv','Fig6_annual_MAE_curves.csv']:add(ROOT/'outputs/fig6_integrated_axes_20261030/artwork/source_data'/n,'model','Saved 2018–2025 evaluation','Saved integrated annual reconstruction; calculation in plot_network_fig6_20261030.py')
for n in ['city_author_year_mass.parquet','international_city_od_period.parquet','canonical_accounting.csv','author_mass_mapping_coverage.csv']:add(rareb/n,'model','Archived aggregate model-support input')
for p in CLEAN.rglob('*'):
 if p.is_file() and p.suffix.lower() in ['.csv','.parquet','.json','.md'] and 'round2_diagnostics' not in p.parts:add(p,'clean','October20 data / city mapping / geographic review ledger','Canonical manifest created_utc='+manifest['created_utc'],manifest.get('output_files',{}).get(p.name,{}).get('sha256'))
for rel,h in manifest['scripts'].items():add(ROOT/rel,'clean','Historical cleanup script','Hash recorded in October20 manifest',h)
for rel in manifest.get('reference_manifests',[]):add(ROOT/rel,'clean','Geographic reference version manifest')
add(ROOT/'data/processed/mobility_admin_city_20261020/manifest.json','clean','Alternative administrative-city version — not canonical','Keep distinct from mobility_city_harmonized_20261020')
samplefiles={'fixed203':'outputs/results_caption_alignment_20261031/artwork/source_data/Fig3_fixed_country_membership.csv','sample76':'outputs/mechanism_validation_20261030/sample76.csv','common45':'outputs/mechanism_validation_20261030/common45.csv','T1_T4':'outputs/results_caption_alignment_20261031/artwork/source_data/Fig3_Fig5_quartile_membership.csv','field26':'outputs/results_caption_alignment_20261031/artwork/source_data/Fig5_field_domain_mapping.csv'}
for k,p in samplefiles.items():add(ROOT/p,'samples',k,'Current figure source data or archived matched sample')
for n in ['canonical_domain_domestic_annual.csv','canonical_domain_domestic_trends.csv','canonical_domain_fixed_city_annual.csv','canonical_domain_trend_summary.csv','same_city_list_all_domains.csv','same_country_same_fixed_cities_domain_annual.csv','same_country_same_fixed_cities_domain_summary.csv','same_country_same_fixed_cities_domain_trends.csv','domain_comparability_audit.json']:add(ROOT/'outputs/mechanism_validation_20261030'/n,'samples','Archived domain and fixed-city results','Existing October30 output, not recomputed')
for n in ['Fig3_fixed_country_metrics.csv','Fig3_fixed_country_year_data.csv','Fig5_domestic_country_annual_metrics.csv','Fig5_domestic_country_trends.csv']:add(ROOT/'outputs/results_caption_alignment_20261031/artwork/source_data'/n,'samples','Current figure annual sample / index support')
add(ROOT/'outputs/results_T_groups_20261029/quantitative_checks.json','samples','Outdated group-size summary — not current T1–T4','Contains 19/19/19/19; current membership is 15/14/24/23')
entries={'rarefaction':['scripts/reports/validate_event_rarefaction_20261030.py'],'model':['scripts/reports/validate_international_signals_20261030.py','scripts/reports/validate_logical_distance_20261030.py','scripts/reports/complete_network_section_20261030.py','scripts/reports/annual_network_reconstruction_20261030.py','scripts/plots/plot_network_fig6_20261030.py'],'clean':list(manifest['scripts']),'samples':['scripts/reports/analyze_mechanism_domains_20261030.py','scripts/reports/check_domain_mechanism_comparability_20261030.py']}
code_sha={str(ROOT/'scripts/reports/validate_international_signals_20261030.py'):json.loads((ROOT/'outputs/international_signal_validation_20261030/validation_checks.json').read_text())['script_sha256'],str(ROOT/'scripts/reports/validate_logical_distance_20261030.py'):json.loads((ROOT/'outputs/logical_distance_validation_20261030/runtime.json').read_text())['script_sha256']}
for category,initial in entries.items():
 todo=[ROOT/rel for rel in initial];seen=set()
 while todo:
  p=todo.pop()
  if str(p) in seen or not p.exists():continue
  seen.add(str(p));add(p,category,'Historical entry point / local helper dependency','Original code copied, not executed',code_sha.get(str(p)))
  try:tree=ast.parse(p.read_text(encoding='utf-8-sig'))
  except SyntaxError:continue
  for n in ast.walk(tree):
   mods=[n.module] if isinstance(n,ast.ImportFrom) and n.module else [a.name for a in n.names] if isinstance(n,ast.Import) else []
   for mod in mods:
    for base in [p.parent,ROOT/'scripts/reports',ROOT/'scripts/plots']:
     f=base/(mod.split('.')[0]+'.py')
     if f.exists() and str(f) not in seen:todo.append(f)
for n in ['s00_preprocess_openalex_snapshot.py','s10_extract_works_author_mobility.py','s20_dedupe_author_entity_mobility.py','s22_build_author_year_locations.py','s23_build_mobility_duckdb.py','s27_build_tiered_flow.py','s31_aggregate_author_year.py','s52_clean_flow.py','s53_clean_city_regions.py','OPENALEX_MOBILITY_PIPELINE.md','OPENALEX_STORAGE_AND_TOOLCHAIN_REPORT.md','OPENALEX_DATA_PIPELINE_REPORT.md','OPENALEX_FIELDS_USED_REPORT.md','OPENALEX_DATA_CLEANING_AND_MOBILITY_METHODS.md']:add(OA/n,'clean','Upstream OpenAlex code / documentation, historical run not pinned','Current local version; distinguish works-based pipeline from older author-entity pipeline')
# Newly organized views use only archived indicators and city-year records. No indicators, models or draws are recomputed.
cs=set(pd.read_csv(ROOT/samplefiles['sample76']).country);alltr=pd.read_csv(ROOT/'figures/v3/source_data/Fig4_country_concentration_trends.csv');fixtr=pd.read_csv(fixedbase/'combined_fixed_city_trends.csv')
comp=alltr[['country','category','normalized_equivalent_cities_slope_pp','Gini_slope_pp']].rename(columns={'category':'all_city_category'}).merge(fixtr.rename(columns={'category':'fixed_city_category'}),on='country',validate='one_to_one');comp.to_csv(OUT/CAT['fixed']/'exports_20261104/fixed_city_before_after_classification.csv',index=False,encoding='utf-8-sig')
assert sha(CLEAN/'analysis/domestic_city_margins.csv')==checks['source_sha256']
a=pd.read_csv(CLEAN/'analysis/domestic_city_margins.csv',usecols=['year','country','city_id','flow']);a=a[a.country.isin(cs)&a.year.between(1998,2025)&(a.flow>0)]
city=a.groupby(['country','city_id'],as_index=False).agg(first_year=('year','min'),last_year=('year','max'),positive_flow_years=('year','nunique'));city=city.merge(pd.read_csv(CLEAN/'cities.csv')[['city_id','city','region','country_name']],on='city_id',how='left',validate='many_to_one');city['fixed_every_year']=city.positive_flow_years.eq(28);city['first_recorded_after_1998']=city.first_year.gt(1998)
for name,rows in [('city_membership_76_countries.csv',city),('fixed_city_list_76_countries.csv',city[city.fixed_every_year]),('new_city_list_after1998.csv',city[city.first_recorded_after_1998])]:rows.to_csv(OUT/CAT['fixed']/'exports_20261104'/name,index=False,encoding='utf-8-sig')
assert city[city.fixed_every_year].groupby('country').size().reindex(fixtr.country).to_numpy().tolist()==fixtr.N_fixed.tolist()
rare=pd.read_csv(rareb/'rarefaction_200_independent_seed/event_rarefaction_trends.csv');dom=rare[rare.kind=='domestic'].copy()
def category(g,r):return np.select([(g>0)&(r<0),(g<0)&(r>0)],['Relative concentration','Deconcentration'],default='Mixed changes')
dom['observed_category']=category(dom.observed_Gini_slope,dom.observed_R_slope);dom['rarefied_category']=category(dom.rarefied_Gini_slope,dom.rarefied_R_slope)
dom.to_csv(OUT/CAT['rarefaction']/'exports_20261104/rarefaction_classification_76.csv',index=False,encoding='utf-8-sig');dom[dom.rarefied_events>=1000].to_csv(OUT/CAT['rarefaction']/'exports_20261104/rarefaction_subsample_19.csv',index=False,encoding='utf-8-sig')
assert len(dom)==76 and (dom.observed_category=='Relative concentration').sum()==63 and (dom.rarefied_category=='Relative concentration').sum()==18 and len(dom[dom.rarefied_events>=1000])==19
f203=pd.read_csv(ROOT/samplefiles['fixed203']);f203=f203[f203.included==1];f203.to_csv(OUT/CAT['samples']/'exports_20261104/fixed203_countries.csv',index=False,encoding='utf-8-sig');groups=pd.read_csv(ROOT/samplefiles['T1_T4']);groups['trajectory']=groups['group'].map({1:'T1',2:'T2',3:'T3',4:'T4'});groups.to_csv(OUT/CAT['samples']/'exports_20261104/T1_T4_membership.csv',index=False,encoding='utf-8-sig')
assert len(f203)==203 and set(groups.country)==cs and groups['group'].value_counts().sort_index().tolist()==[15,14,24,23]
array_meta={}
for f in [ROOT/'outputs/logical_distance_validation_20261030/domestic_design.npz',ROOT/'outputs/international_signal_validation_20261030/international_features.npz']:
 array_meta[str(f)]={}
 with zipfile.ZipFile(f) as z:
  for member in z.namelist():
   with z.open(member) as h:
    version=np.lib.format.read_magic(h);shape,fortran,dtype=np.lib.format.read_array_header_1_0(h) if version==(1,0) else np.lib.format.read_array_header_2_0(h)
   array_meta[str(f)][member]={'shape':list(shape),'dtype':str(dtype),'fortran':fortran}
(OUT/CAT['model']/'exports_20261104/saved_array_metadata.json').write_text(json.dumps(array_meta,ensure_ascii=False,indent=2),encoding='utf-8')
facts={'fixed_city_checks':checks,'roster_export':{'city_rows':len(city),'fixed_city_rows':int(city.fixed_every_year.sum()),'new_city_rows':int(city.first_recorded_after_1998.sum()),'country_fixed_counts_match_archived_results':True,'new_export_not_historical_file':True},'rarefaction_plan':json.loads((rareb/'rarefaction_200_independent_seed/event_rarefaction_plan.json').read_text()),'rarefaction_summary':json.loads((rareb/'rarefaction_200_independent_seed/event_rarefaction_summary.json').read_text()),'sample_sizes':{'fixed203':len(f203),'domestic76':len(cs),'domain45':len(pd.read_csv(ROOT/samplefiles['common45'])),'fields':len(pd.read_csv(ROOT/samplefiles['field26'])),'T1_T4':groups['group'].value_counts().sort_index().to_dict()},'classification_counts':{'all_cities':alltr.category.value_counts().to_dict(),'fixed_cities':fixtr.category.value_counts().to_dict()},'fixed_all_concentration_to_deconcentration':int(((comp.all_city_category=='Relative concentration')&(comp.fixed_city_category=='Deconcentration')).sum()),'missing_candidates':missing}
(OUT/'evidence_checks.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),encoding='utf-8');(OUT/'file_manifest.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
with (OUT/'文件索引.csv').open('w',encoding='utf-8-sig',newline='') as h:
 w=csv.DictWriter(h,fieldnames=list(records[0]));w.writeheader()
 for r in records:w.writerow({**r,'csv_columns':json.dumps(r['csv_columns'],ensure_ascii=False) if r['csv_columns'] else ''})
print('Collected',len(records),'original files; copied',sum(bool(r['local_copy']) for r in records),'and indexed',sum(not bool(r['local_copy']) for r in records),'large/binary files by path.',flush=True);print('Recovered membership rosters:',facts['roster_export'],flush=True);print('Missing requested candidate paths:',missing,flush=True)
