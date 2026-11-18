from pathlib import Path
import json,csv,re,hashlib,ast,sys,collections
root=Path.cwd();out=root/'outputs/methods_evidence_audit_20261104';records=json.loads((out/'file_manifest.json').read_text(encoding='utf-8'))
checks=[]
def row(topic,status,evidence,note):checks.append(dict(topic=topic,status=status,evidence=evidence,note=note))
row('数据版本','吻合','10月20日manifest与10月23日base_recalculation.json','均指向city_harmonized主Parquet的历史SHA-256；大文件本次未重新哈希。')
row('事件数量','吻合','audit/event_accounting.json；base_recalculation.json','29,703,224=11,529,374+18,173,850；原始总数分解一致。')
row('主要机构规则','代码一致，运行版本待绑定','OpenAlex/s27_build_tiered_flow.py:72–76','按count(DISTINCT work_id)降序、institution_id排序；本机没有上游运行时散列。')
row('主要学科并列','待明确','OpenAlex/s27_build_tiered_flow.py:78–81','使用arg_max，未见显式并列排序；不能补写未执行的tie-break规则。')
row('城市归并程序','已核验版本','清洗manifest的scripts字段','7个程序与历史哈希全部匹配；映射表也匹配。')
row('LLM清洗过程','缺少实际调用证据','现有地理映射表、审核清单；未检出独立LLM调用日志','仅可核验规则和映射证据；模型版本、prompt、调用记录及独立审核还需实际材料。')
row('固定城市','吻合','verify_combined_cities.py；combined_city_checks.json','每个国家每年合计流量为正；固定名单28年；本次恢复名单逐国数量匹配历史N_fixed。')
row('固定城市分类','吻合','combined_fixed_city_trends.csv；分类对照导出','20集中、46去集中、10混合；35/63反向。对照表为本次连接保存结果。')
row('新增城市','吻合','combined_post1998_city_cohort.csv','初始年后首次出现且当前年活跃；占比使用合计城市强度。')
row('等事件200次','吻合','rarefaction_200_independent_seed/event_rarefaction_plan.json','实际plan为200、seed=20261048；默认脚本50须传参数200。')
row('200次逐次原始结果','未保存','validate_event_rarefaction_20261030.py的输出部分','只有均值、分位数和趋势，未找到replicate层面的抽样数组；本次没有重跑。')
row('等事件19国','吻合','200次趋势CSV及summary','rarefied_events>=1000，19国，集中分类11降至4。')
row('模型样本与时段','吻合','logical_distance的设计数组；international_signal的plan和validation','3,069,435候选单元；训练2002–2013、验证2014–2017、后期2018–2025。')
row('模型拟合版本','已核验版本','两个核心程序与runtime/validation的script_sha256','validate_logical_distance和validate_international_signals的历史哈希均匹配。')
row('模型版本选择','需区分两步与综合','validation_selection.json；full-model analysis_plan.json','验证集选中两步；年度综合重建明确指定A_all_international_signals；脚本默认两步，综合需--full。')
row('模型年度重建','吻合','fig6_full_model_revision/analysis/annual_country_indices.csv','2002–2025共1,824行；2018–2025评价608行。未插值、未重新拟合。')
row('MAE/RMSE','吻合，但注意旧summary指标','Fig6_evaluation_errors.csv及原绘图代码74–111行','原annual_summary的median_abs_error是MedAE，不是MAE；Gini误差单位百分点。')
row('203/76/45样本','已找到并核对','样本与分组目录的原文件和导出','203名单需筛included=1；原表224候选；76与45为独立既有样本文件。')
row('T1–T4','当前文件吻合，旧汇总过期','trajectory_membership.csv；sign_and_nested_display_proposal.json','当前15/14/24/23；10月29日旧quantitative_checks仍19/19/19/19。')
row('26学科映射','吻合','Fig5_field_domain_mapping.csv','物理10、生命5、健康5、社会6，总计26。')
row('学科固定城市敏感性','已有历史结果，正文需核对','mechanism_validation_20261030/canonical_domain_fixed_city_annual.csv等','10月30日已经计算并保存；Results笼统写remain to be conducted应按实际范围调整。')
with (out/'Methods逐项核对.csv').open('w',encoding='utf-8-sig',newline='') as h:
 w=csv.DictWriter(h,fieldnames=list(checks[0]));w.writeheader();w.writerows(checks)
md=['# Methods与实际材料逐项核对\n\n本表核对程序、配置和既有结果，不改变方法设计，也不重算统计分析。\n\n| 项目 | 状态 | 证据 | 说明 |\n|---|---|---|---|']
md+=['| '+' | '.join(r.values())+' |' for r in checks]
(out/'Methods逐项核对.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
# Preserve exact fitting/model parameters and entry-point options, with their source files.
fits=json.loads((root/'outputs/international_signal_validation_20261030/fits.json').read_text());plan=json.loads((root/'outputs/international_signal_validation_20261030/analysis_plan.json').read_text());cfg={'source':'existing plan/fits and source code; no refitting','train':'2002-2013','validation':'2014-2017','evaluation':'2018-2025','model_configs':plan['model_configs'],'feature_construction':plan['hypotheses'],'optimizer':{'method':'L-BFGS-B','maxiter':300,'gtol':1e-7,'ftol':1e-12,'penalty':None,'source':'scripts/reports/validate_logical_distance_20261030.py:fit'},'fitted_models':{k:{'columns':v['cols'],'gradient':v['gradient'],'iterations':v['iterations'],'beta':v['beta'],'mean':v['mean'],'scale':v['scale']} for k,v in fits.items()},'annual_reconstruction':json.loads((root/'outputs/fig6_full_model_revision_20261030/analysis_plan.json').read_text()),'seed_statements':[]}
for name in ['validate_event_rarefaction_20261030.py','complete_network_section_20261030.py','validate_international_signals_20261030.py','validate_aggregate_alternatives_20261030.py','validate_cross_scale_mechanisms_20261030.py']:
 p=root/'scripts/reports'/name
 for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
  if re.search(r'SEED\s*=|default_rng|seed\s*=|np\.random',line):cfg['seed_statements'].append({'source_file':str(p),'line':i,'text':line.strip()})
(out/'03_models/exports_20261104/model_configuration_index.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
# Audit the assembled package. No statistical routines are invoked here.
errors=[];copied=0
for r in records:
 source=Path(r['source_path'])
 if not source.is_file() or source.stat().st_size!=r['bytes']:errors.append('Source missing/size changed: '+str(source))
 if r['local_copy']:
  p=out/r['local_copy'];copied+=1
  if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=r['sha256_current']:errors.append('Copy mismatch '+str(p))
  if p.suffix=='.py':
   try:ast.parse(p.read_text(encoding='utf-8-sig'))
   except SyntaxError as e:errors.append('Source syntax issue: '+str(p)+' '+str(e))
 if r['historical_hash_matches'] is False:errors.append('Historical hash mismatch '+str(source))
for name in ['methods.tex','results.tex','supplementary_tables.tex']:
 assert (root/'outputs/paper_final'/name).read_bytes()==(out/'manuscript_snapshot'/name).read_bytes()
assert not errors,errors
# Existing model simulations contain saved replicate IDs; rarefaction results do not.
for r in records:
 if Path(r['source_path']).name in ['distribution_simulation_replicates.csv','network_randomization_country.csv','event_rarefaction_annual.csv']:print(Path(r['source_path']).name,r['csv_rows'],r['csv_columns'][:7])
validation={'scope':'Original-file retrieval and metadata/result-table checks only; no new model fits, indicators, rarefaction or data cleaning','file_index_rows':len(records),'unique_original_files':len({r['source_path'] for r in records}),'copied_index_rows':copied,'large_or_binary_path_only_index_rows':len(records)-copied,'historical_hash_matches':sum(r['historical_hash_matches'] is True for r in records),'historical_hash_mismatches':0,'copy_errors':errors,'manuscript_sources_unchanged':True,'generated_exports_are_marked_as_new_views':True}
(out/'package_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(validation,ensure_ascii=False,indent=2))
