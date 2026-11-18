"""Publish a complete record-level audit without declaring unresolved data clean."""
from pathlib import Path
from collections import Counter, defaultdict
import csv, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
OUT=ROOT/'data/processed/mobility_admin_city_20261020'
A=OUT/'audit'

def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

REASONS={
 'municipal_boundary_source_not_verified':('缺少已核验的适用市级边界','补充该国适用的行政市边界；县、省或统计区不能直接替代城市'),
 'place_identity_or_coordinate_unresolved':('地点名称、身份或坐标冲突','回溯机构原始地址、校区坐标和机构标识；核对名称与位置'),
 'point_not_in_verified_municipality_or_ambiguous_boundary':('未落入适用市级边界或归属不唯一','核对边界覆盖、建制状态和机构地址；不能按最近城市强行合并'),
 'source_and_original_point_cross_municipal_boundary':('原始点与地名库参考点分属不同市','回溯机构地址，判定哪个位置正确'),
 'source_administrative_unit_coarser_than_municipality':('原始名称为更粗行政区','提取机构或校区所在地，不能用上级行政区中心点替代'),
 'coarse_london_label_requires_institution_address':('London总称缺少具体市政归属','根据机构或校区地址识别市政单位；不能把共享中心点统一分配到同一自治市'),
 'coarse_tokyo_label_requires_institution_address':('Tokyo总称缺少具体市政归属','根据机构或校区地址识别市町村或特别区；政令市普通区仍归所属市'),
 'map_coordinate_offset_or_city_boundary_requires_review':('参考地图坐标偏移或边界归属不稳定','核对坐标系及机构精确地址；边界附近地点暂不通过'),
 'verified_unincorporated_census_designated_place':('已确认非建制统计地点','保留为非行政城市地点；不得强并入邻近行政市'),
}

def main():
    v=json.loads((A/'validation.json').read_text(encoding='utf8'))
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf8'))
    assert manifest['crosswalk_sha256']==sha(OUT/'city_crosswalk.csv')
    cw=read(OUT/'city_crosswalk.csv');old=read(A/'before_completion_review/city_crosswalk.csv')
    # Keep the published meanings unambiguous even when reading an older audit
    # schema that counted confirmed nonmunicipal records as unresolved.
    statuses=Counter(r['place_audit_status'] for r in cw)
    assert v['accepted_place_instances']==statuses['verified_municipal_city'] and v['raw_place_instances']==len(cw)
    v.update(unresolved_place_instances=statuses['unresolved'],
        non_city_matched_place_instances=statuses['unresolved']+statuses['verified_nonmunicipal_place'],
        review_reasons=dict(Counter(r['review_reason'] for r in cw if r['place_audit_status']=='unresolved')),
        verified_nonmunicipal_reasons=dict(Counter(r['review_reason'] for r in cw if r['place_audit_status']=='verified_nonmunicipal_place')))
    (A/'validation.json').write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf8')
    oldmap={r['raw_place_id']:r for r in old}
    c=duckdb.connect();c.execute("SET threads=4;SET memory_limit='2GB'")
    file=str(A/'full_event_ledger_annual.parquet')
    c.read_parquet(file).create_view('ledger')
    incident=dict(c.execute("""SELECT rawid,sum(events) FROM (
        SELECT origin_raw_place_id rawid,sum(flow) events FROM ledger WHERE tier='top100pct' GROUP BY 1
        UNION ALL SELECT destination_raw_place_id,sum(flow) FROM ledger WHERE tier='top100pct' GROUP BY 1) GROUP BY rawid""").fetchall())
    rows=[];changes=[]
    for r in cw:
        code=r['review_reason'];status=r['place_audit_status']
        if status=='verified_municipal_city':meaning,action='已匹配行政城市或有据可查的市政等同单位','可在当前参考边界口径下使用'
        else:meaning,action=REASONS[code]
        row=dict(raw_place_id=r['raw_place_id'],raw_country=r['raw_country'],country_code=r['country_code'],raw_region=r['raw_region'],
            raw_city=r['raw_city'],raw_latitude=r['raw_latitude'],raw_longitude=r['raw_longitude'],city_id=r['city_id'],city=r['city'],
            place_audit_status=status,audit_conclusion=meaning,required_action=action,review_reason=code,
            incident_endpoint_events_top100=int(incident.get(r['raw_place_id'],0)),evidence=r['evidence'],boundary_provider=r['boundary_provider'],boundary_year=r['boundary_year'])
        rows.append(row)
        before=oldmap[r['raw_place_id']]
        if before['city_id']!=r['city_id'] or before['review_reason']!=code:
            changes.append(dict(raw_place_id=r['raw_place_id'],raw_country=r['raw_country'],raw_city=r['raw_city'],
                previous_city_id=before['city_id'],current_city_id=r['city_id'],previous_reason=before['review_reason'],current_reason=code,
                current_status=status,incident_endpoint_events_top100=row['incident_endpoint_events_top100']))
    assert len(rows)==16484 and all(r['audit_conclusion'] and r['required_action'] for r in rows)
    rows.sort(key=lambda r:-r['incident_endpoint_events_top100'])
    unresolved=[r for r in rows if r['place_audit_status']=='unresolved']
    nonmunicipal=[r for r in rows if r['place_audit_status']=='verified_nonmunicipal_place']
    write(A/'final_place_audit.csv',rows)
    # Refresh auxiliary inventories after targeted country amendments.
    catalog=read(OUT/'cities.csv');byid=defaultdict(list)
    for r in cw:byid[r['city_id']].append(r)
    extra=[]
    for key,items in byid.items():
        r=items[0]
        if r['analysis_ready']=='True':continue
        extra.append(dict(city_id=key,country_code=r['country_code'],country_name=r['country_name'],region_code=r['region_code'],
            region=r['region'],city=r['city'],city_geonameid=r['city_geonameid'],latitude=r['city_latitude'],longitude=r['city_longitude'],
            source_place_instances=len(items),analysis_ready='False',municipality_verified='False',municipal_unit_type=r['municipal_unit_type'],
            boundary_provider=r['boundary_provider'],boundary_year=r['boundary_year']))
    write(A/'place_catalog_including_unverified.csv',catalog+extra)
    diagnostics=read(A/'point_boundary_checks.csv');dm={r['raw_place_id']:r for r in diagnostics}
    for r in cw:
        if r['analysis_ready']!='True':continue
        if r['boundary_match_method'] not in ['source_and_raw_points_same_municipal_corporation','both_points_in_documented_consolidated_city_county']:continue
        dm[r['raw_place_id']]=dict(raw_place_id=r['raw_place_id'],raw_city=r['raw_city'],source_country=r['raw_country'] or r['country_code'],
            raw_point_candidates=r['city_id'],reference_point_candidates=r['city_id'],assigned_municipality=r['city_id'],review_reason='')
    write(A/'point_boundary_checks.csv',list(dm.values()))
    write(A/'remaining_city_resolution_tasks.csv',unresolved)
    write(A/'unresolved_places.csv',[r for r in cw if r['place_audit_status']=='unresolved'])
    write(A/'review_changes.csv',changes)
    write(A/'unresolved_priority.csv',[dict(r,incident_events=r['incident_endpoint_events_top100']) for r in unresolved])
    countries=defaultdict(list)
    for r in unresolved:countries[r['country_code']].append(r)
    cr=[]
    for cc,items in countries.items():
        cr.append(dict(country_code=cc,unresolved_place_records=len(items),
            incident_endpoint_events_top100=sum(r['incident_endpoint_events_top100'] for r in items),
            reasons=json.dumps(dict(Counter(r['audit_conclusion'] for r in items)),ensure_ascii=False)))
    cr.sort(key=lambda x:-x['incident_endpoint_events_top100']);write(A/'remaining_by_country.csv',cr)
    grouped=defaultdict(list)
    for r in cw:grouped[r['country_code']].append(r)
    write(A/'country_place_coverage.csv',[dict(country_code=cc,raw_places=len(items),
        boundary_matched_places=sum(r['analysis_ready']=='True' for r in items),
        municipal_units=len({r['city_id'] for r in items if r['analysis_ready']=='True'}),
        verified_nonmunicipal_places=sum(r['place_audit_status']=='verified_nonmunicipal_place' for r in items),
        unresolved_places=sum(r['place_audit_status']=='unresolved' for r in items)) for cc,items in sorted(grouped.items())])
    counts={r['event_status']:int(r['events']) for r in v['top100_event_status']}
    total=int(v['original_top100_events']);assigned=int(v['verified_including_same_city_events'])
    oldv=json.loads((A/'before_completion_review/validation.json').read_text(encoding='utf8'))
    summary=dict(all_raw_records_reviewed=True,reviewed_place_records=len(rows),
        city_matched_place_records=v['accepted_place_instances'],verified_nonmunicipal_place_records=len(nonmunicipal),
        still_unresolved_place_records=len(unresolved),original_events_top100=total,event_status=counts,
        both_endpoints_city_assigned=assigned,both_endpoints_city_assigned_percent=100*assigned/total,
        verified_intercity_events=int(v['verified_intercity_events']),
        newly_city_matched_place_records=v['accepted_place_instances']-oldv['accepted_place_instances'],
        newly_city_assigned_events=assigned-int(oldv['verified_including_same_city_events']),
        city_standardization_complete=not unresolved,analysis_ready_full_global_city_dataset=False,
        endpoint_counts_are_not_unique_event_counts=True)
    (A/'completion_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    reasons=Counter(r['audit_conclusion'] for r in unresolved)
    reason_text='\n'.join(f'- {name}：{number:,} 条地点记录。' for name,number in reasons.most_common())
    text=f'''# 行政城市清洗核查报告

更新日期：2026-10-20。

## 核查结论

本轮已对全部 {len(rows):,} 条原始地点记录完成程序核查并给出处理结论。**逐条核查已完成，不等于全量城市归并已完成。** 当前有 {v['accepted_place_instances']:,} 条匹配到 {v['verified_administrative_units']:,} 个行政市镇或对应市政单位；{len(nonmunicipal):,} 条确认属于非建制统计地点；{len(unresolved):,} 条仍缺少足以确定行政城市的资料。

用户确定的口径是各国正式行政城市边界，城区和社区归入所属城市，行政上独立的邻近城市保留区别。地点记录不是城市数量，流动事件也不是研究者人数。

## 本轮新增处理

- 新增匹配 {summary['newly_city_matched_place_records']:,} 条地点记录，两端完成行政城市归属的事件增加 {summary['newly_city_assigned_events']:,} 次。
- 补充中国的行政市参考边界。市辖区不作为独立城市；直辖市统一到相应城市，具有独立行政地位的县级市优先保留。参考源是阿里云 DataV 的简化地图，不能表述为政府发布的法律边界。对原始点和地名库点均要求离边界超过 0.015 度，筛除可能受地图坐标偏移影响的归属。
- 补充新西兰 Stats NZ 2025 年领地管理区官方边界，核对完整的 68 个服务要素，排除不属于行政单位的 Outside 区域。
- 爱尔兰使用 Tailte Eireann 的地方行政机关法定边界服务，分页取得全部 9,161 个几何片段并归并为 31 个地方行政机关，没有把选区当作城市。
- 印度尼西亚只接纳明确的 Kota 市政单位；Kabupaten 县不自动当作城市，雅加达内部非自治行政市归入雅加达。
- 印度补充 Bengaluru、Chennai、Mumbai、Hyderabad、Pune、Kolkata、Ahmedabad 七个市政机构的边界或区划合并边界，采用固定提交版本的 DataMeet 参考数据。资料明确年份的保留原年份，未明确的标为 unspecified；不将德里首都辖区或大都市区当作市政边界。
- 华盛顿市与特区合署政府，按人口普查局的正式说明恢复其市级归属；没有把 FUNCSTAT=N 的所有地点一并放行。
- 檀香山采用有正式市政政府的市县合一边界，内部社区归入同一行政市；没有因 Census 城市图层的统计约定而把它判为非城市，也没有将其他夏威夷县直接当作城市。
- 莫斯科与圣彼得堡按联邦城市参考边界处理，未把州、地区当作城市。新加坡按单一城市国家处理，不把规划区当作独立城市。
- 美国非建制人口普查统计地点单独列为已核验的非行政城市地点；不会并入最近的城市。Bethesda、Stanford 等此类地点保留原始记录。
- 延续独立城市保护：Calabasas 与 Los Angeles、Beverly Hills 与 Los Angeles、Osaka 与 Suita、Paris 与 Orsay 等保持不同城市。

## 流动事件核对

以下为 1998—2025 年年度全体研究者 top100pct。影响力分层相互重叠，不能相加。

- 原始事件：{total:,} 次。
- 两端已确认、跨国：{counts.get('international',0):,} 次。
- 两端已确认、国内城际：{counts.get('domestic_intercity',0):,} 次。
- 两端归入同一市：{counts.get('within_same_municipality',0):,} 次。
- 至少一端确认不属于行政城市，且另一端已确定：{counts.get('outside_municipal_city',0):,} 次。
- 至少一端归属仍未解决：{counts.get('needs_municipal_review',0):,} 次。

两端完成行政城市归属的事件为 {assigned:,} 次，占 {100*assigned/total:.2f}%；其中跨国及国内城际事件 {int(v['verified_intercity_events']):,} 次，占 {100*v['verified_intercity_fraction_of_original']:.2f}%。上述五类精确加总为原始总数。年度、职业生涯和基础表的全部影响力层级均完成流量及原始聚合行数守恒核对。

## 仍需补充的资料

{reason_text}

地点与地名库参考点不一致时，不能仅选取更方便的一端。Tokyo 和 London 的总称记录也不能凭共享中心坐标分派给某个区。当地机构表可辅助列出需要定位的机构，但城市聚合表不能恢复已被合并的机构或校区来源。完整事件明细在 OpenAlex 原处理服务器上，本地项目保留的汇总数据和样例不足以重建这些归属。

印度等国家还需要适用的市政边界。地名库中有一个城市名称、或者存在该国 ADM2/ADM3 层级，并不证明该层级就是行政城市。

## 文件说明

- `city_crosswalk.csv`：全部原始地点映射，`place_audit_status` 区分已匹配行政城市、已确认非行政城市和仍未解决三种状态。
- `cities.csv`：仅包含已匹配的行政市镇或有依据的市政等同单位。
- `audit/final_place_audit.csv`：全部地点的核查结论、依据和下一步处理要求。
- `audit/remaining_city_resolution_tasks.csv`：仍需资料的地点，按相关端点流动量排序。
- `audit/remaining_by_country.csv`：按国家汇总的剩余工作。
- `audit/verified_nonmunicipal_places.csv`：已确认非建制地点，不再混同于普通缺失归属。
- `audit/review_changes.csv`：本轮变更记录。
- `audit/validation.json`：完整性、边界、独立城市保护和各层级数量守恒检查。
- `audit/completion_summary.json`：本轮核查摘要。
- `mobility_*_admin_city_verified.parquet`：两端均匹配且不属于同一城市的流动事件子集。
- `audit/needs_municipal_review_*.parquet`、`outside_municipal_city_*.parquet`、`within_same_municipality_*.parquet`：其余三类完整保留。

`incident_endpoint_events_top100` 统计某地点相关的端点量；同一次事件可在两端各出现一次。该列不能直接加总为事件数。

**当前严格子集仍不能作为完整全球城市数据替换论文分析。** 市级资料缺口会选择性排除地点和国家，须补齐后再更新全球图表和集中度结论。原始输入及现有图表保持不变。

## 主要来源

[阿里云 DataV 边界工具说明](https://help.aliyun.com/en/datav/datav-7-0/user-guide/choropleth-layers-of-v4-x-for-datav-7)、[中国行政代码结构](https://www.stats.gov.cn/sj/tjbz/gjtjbz/202302/t20230213_1902741.html)、[US Census 华盛顿市说明](https://www.census.gov/geographies/reference-files/2010/geo/state-local-geo-guides-2010/districtofcolumbia.html)、[非建制统计地点](https://www.census.gov/programs-surveys/bas/information/cdp.html)、[Stats NZ 地理数据](https://datafinder.stats.govt.nz/)、[爱尔兰地方政府](https://www.gov.ie/en/department-of-housing-local-government-and-heritage/publications/your-council/)、[雅加达内部行政市](https://barat.jakarta.go.id/index.php/profil/sejarah)、[新加坡城市国家说明](https://www.mfa.gov.sg/about-singapore/)。各条映射的实际边界来源和年份保留在映射表中。
'''
    (OUT/'行政城市清洗核查报告.md').write_text(text,encoding='utf8')
    (OUT/'README.md').write_text('# 行政城市核查数据\n\n请先阅读[行政城市清洗核查报告](行政城市清洗核查报告.md)。\n\n全部地点已有核查结论，全量城市归并仍有资料缺口。`analysis_ready=True` 的严格子集不等于完整全球数据。\n\n核查结论保存在 `audit/final_place_audit.csv`；剩余工作见 `audit/remaining_city_resolution_tasks.csv`。\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    c.close()

if __name__=='__main__':main()
