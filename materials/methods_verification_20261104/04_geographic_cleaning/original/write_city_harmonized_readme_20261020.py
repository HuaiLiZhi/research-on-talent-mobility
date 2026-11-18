"""Write a user-facing dataset guide after validation succeeds."""
from pathlib import Path
from collections import Counter
import csv
import hashlib
import json

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/processed/mobility_city_harmonized_20261020'


def main():
    cross=json.loads((OUT/'audit/crosswalk_summary.json').read_text(encoding='utf-8'))
    qa=json.loads((OUT/'audit/validation.json').read_text(encoding='utf-8'))
    accounting=json.loads((OUT/'audit/event_accounting.json').read_text(encoding='utf-8'))
    consistency=json.loads((OUT/'audit/top100_cross_input_consistency.json').read_text(encoding='utf-8'))
    with (OUT/'city_crosswalk.csv').open(encoding='utf-8-sig',newline='') as f:mapping=list(csv.DictReader(f))
    repairs=Counter('缺失国家补回' if not r['raw_country'] else '国家编码纠正'
                    for r in mapping if r['country_corrected']=='True')
    reviews=cross['raw_place_instances']-cross['analysis_ready_place_instances']
    lines=['# 城市地名与层级清洗后的研究者流动数据','',
        '生成日期：2026-10-20。研究窗口：1998—2025 年。所有原始 CSV、原有中间结果和图表均保持原样。','',
        '## 从哪个文件开始使用','',
        '后续论文分析优先使用 `count_mobility_flow_annual_clean.parquet`；需要 CSV 时使用同名 `.csv`。全体研究者筛选 `tier = top100pct`，其他影响力层级分别使用，不能将相互重叠的层级相加。','',
        '| 文件 | 内容 |','| --- | --- |',
        '| count_mobility_flow_annual_clean.csv / .parquet | 年度影响力分层，保留全部五个 tier |',
        '| count_mobility_flow_career_clean.csv / .parquet | 职业生涯影响力分层，保留全部五个 tier |',
        '| mobility_flow_by_field_city_clean.csv / .parquet | 原基础流动表的城市清洗版本 |',
        '| city_crosswalk.csv | 原始地点到统一城市的逐条对应及归并依据 |',
        '| cities.csv | 统一城市目录、唯一标识、坐标与地区字段 |',
        '| audit/unresolved_places.csv | 需进一步确认的地点，未强行归并 |',
        '| analysis/ | 新数据计算的国家及城市边际流量、城市数量、HHI、等价数量和 Gini |','',
        'CSV 文件较大，Parquet 与 CSV 包含同一清洗结果，更适合直接读取和统计。','',
        '## 完成的清洗','',
        '1. 从三份原始流动表提取地点记录，恢复可核对的原始 GeoNames 标识。缺少标识时，以地点名、坐标或官方城市边界核对。','2. 将确认属于同一城市的地区名称、缺失地区版本及名称变体归到统一的 `city_id`。不同州的同名城市保留为不同城市。',
        '3. 将有明确归属的市内行政区、社区和郊区归入城市本体。使用 GeoNames 明确的城市组成关系、部分国家的市镇行政编码、美国官方 place 边界及带出处的个别归并规则。',
        '4. 同时转换流动的来源地与目的地。转换后两端为同一城市的事件单独保存为市内事件，不再计入清洗后的城际流动。',
        '5. 对国家、坐标、地点名相互冲突，或仅能定位到较粗行政区的记录单独保留待核查。','',
        '已核对的例子包括：纽约各区归纽约；拉霍亚归圣迭戈；浦东归上海；江宁归南京；多伦多原市镇归多伦多；Parkville、Carlton 归墨尔本；Martinsried 归 Planegg。伦敦、东京、柏林不同地区字段版本均已归到各自统一城市标识。',
        '独立城市保护检查包括：不同州的 Cambridge、纽约与堪萨斯的 Manhattan、Beverly Hills 与 Los Angeles、Osaka 与 Suita、Paris 与 Orsay、Planegg 与 Munich，均保留区别。','',
        '## 清洗范围与待核查记录','',
        f"共处理 {cross['raw_place_instances']:,} 条不同原始地点记录，其中 {cross['analysis_ready_place_instances']:,} 条通过本版地理核对，{reviews:,} 条列入待核查文件。一个地点可在多个年份、学科和流向中重复出现，因此该数量不是流动事件次数。",
        f"根据可核对的稳定标识与坐标，补回 {repairs['缺失国家补回']:,} 条地点记录的缺失国家编码，并纠正 {repairs['国家编码纠正']:,} 条地点记录的国家编码。记录均保留清洗前字段。",'',
        '本版采用固定参考地理口径贯穿整个研究期。它统一地名、明确的市内组成关系和部分国家的市镇单位；不同国家的行政制度仍不同，本版不是全球统一建成区或功能城市区边界产品。无法确认的归属保留待核查，不按最近的大城市猜测合并。','',
        '## 全体研究者的流动量对账','',
        '以下仅列 `top100pct`，不将重叠影响力层级相加。三份输入的全体研究者空间流动总量一致。','',
        '| 分类 | 事件次数 |','| --- | ---: |']
    annual=next(r for r in accounting if r['dataset']=='annual')
    labels={'international':'清洗后跨国流动','domestic_intercity':'清洗后国内城际流动',
        'within_city_after_merge':'归并后属于市内的事件','needs_review':'待核查事件'}
    counts={r['event_status']:int(r['events']) for r in annual['classification'] if r['tier']=='top100pct'}
    for key in ['international','domestic_intercity','within_city_after_merge','needs_review']:
        lines.append(f'| {labels[key]} | {counts[key]:,} |')
    total=next(r['events'] for r in annual['before'] if r['tier']=='top100pct')
    lines += [f'| 原始研究窗口内合计 | {int(total):,} |','',
        '清洗后的城际事件、市内事件和待核查事件相加，与原始窗口内有效正流量精确相等。该核对对三个输入、每个 tier 分别完成。市内和待核查记录均未丢失，保存在 audit 文件夹的对应 Parquet 中。','',
        '## 2025 年国内流入地点数量','',
        '| 国家代码 | 原论文数据 | 清洗后数据 |','| --- | ---: | ---: |']
    for r in qa['selected_2025_counts']:
        lines.append(f"| {r['country']} | {r['existing_count']:,} | {r['cleaned_count']:,} |")
    lines += ['','这些数量同时受到城市归并、地理质量筛选和补回缺失国家信息的影响，不能将净变化全部解释为城区合并的数量。已有图表需要按新数据重新计算。','',
        '## 三份输入的关系','',
        '年度和职业生涯分层表的 top100pct 在城市对、年份和学科上的计数一致。基础表与现行分层表在原始学科归属上存在差异；将学科加总后，城市对和年份的空间流量完全一致。本次清洗分别保留各原始表的学科归属，未强行改写标签。后续学科分析统一使用年度清洗表，避免混用。差异记录见 `audit/top100_cross_input_consistency.json`。','',
        '## 主要字段','',
        '- `from_city_id`、`to_city_id`：来源与目的地的统一城市标识，统计时使用此字段，不再用地区名称和城市名拼接。',
        '- `from_city`、`to_city`：统一城市名；`from_country_code`、`to_country_code` 为国家双字母代码；`from_region`、`to_region` 为统一地区名。',
        '- `year`、`field_display_name`、`tier`：年份、原输入学科、影响力层级。',
        '- `mobility_count`：聚合流动事件次数。`geography` 为 international 或 domestic_intercity。',
        '- 对应表中的 `raw_*` 保留原字段，`merge_rule` 与 `evidence` 记录处理规则和依据，`review_reason` 记录待核查原因。','',
        '## 校验与复现','',
        '检查结果见 `audit/validation.json`。已核对：地点与城市标识唯一、同一城市元数据一致、同一已识别 GeoNames 地点不再按地区字段拆分、指定城区正确归并、独立城市保持区分、清洗表无同城事件和重复城市对键、各层级流动量精确守恒。',
        '源文件及交付文件校验码见 `manifest.json`。原始参考下载和许可见 `data/raw/geo/geonames_20261020/download_manifest.json` 及美国边界目录的 manifest。',
        '复现脚本按 prepare_city_harmonization_references、prepare_city_harmonization_nodes、import_city_harmonization_gazetteer、build_city_harmonization_map、rebuild_city_harmonized_flows、validate_city_harmonized_data 的顺序执行，脚本日期均为 20261020。原始作者位置地理键另保存在 audit/source_author_location_geographic_keys.csv。','',
        '## 地理参考资料','',
        '- [GeoNames 数据格式、地点类型和层级说明](https://download.geonames.org/export/dump/readme.txt)，固定下载版本 2026-10-20，CC BY 4.0。',
        '- [美国人口普查局 2024 城市地理边界](https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html)，固定使用 2024 place 边界。',
        '- 个别人工核实的城市组成关系及出处见 `city_parent_overrides.csv`。','']
    (OUT/'README_清洗说明.md').write_text('\n'.join(lines),encoding='utf-8')
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    manifest['validation']='audit/validation.json'
    manifest['cross_input_consistency']='audit/top100_cross_input_consistency.json'
    manifest['cleaning_policy']='cleaning_policy.json'
    manifest['scripts']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (ROOT/'scripts/reports').glob('*city*20261020.py') if 'audit_us_' not in p.name}
    manifest['reference_manifests']=['data/raw/geo/geonames_20261020/download_manifest.json','data/raw/geo/us_census_places_2024/manifest.json']
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Dataset README and provenance written')


if __name__=='__main__':main()
