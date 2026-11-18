# 行政城市边界匹配数据

**状态：可核验子集已生成；全量全球城市统一尚未完成。** 请先阅读同目录的《行政城市清洗核查报告.md》。当前严格子集只覆盖原始流动事件的一部分，不能直接替换全球论文分析。

## 数据文件

- `city_crosswalk.csv`：全部原始地点到市镇的映射；`analysis_ready` 和 `municipality_verified` 表示是否通过本轮匹配，`review_reason` 保留未通过原因，`previous_city_id` 保留上一轮标识。
- `cities.csv`：仅包含通过匹配的行政市镇目录；不包含待核查地点。年度城市数仍须按实际流量计算。
- `mobility_annual_admin_city_verified.parquet`：年度影响力层级，保留五个 tier。全体研究者选择 `top100pct`，不能将重叠 tier 相加。
- `mobility_career_admin_city_verified.parquet`：职业生涯影响力层级。
- `mobility_baseline_admin_city_verified.parquet`：基础表的行政市镇匹配版本。原输入的学科标签分别保留，学科分析不要混用三个版本。
- `analysis/flow_top100.parquet`：由年度全体研究者生成的严格城市流动数据。
- `analysis/country_flow_top100.parquet`：单独保留具有可识别国家代码的跨国事件，不因缺少市级边界就自动丢弃国家级记录；其总体与严格城市子集不同。
- `analysis/*_city_margins.csv`、`*_country_city_counts.csv`、`*_city_metrics.csv`：严格子集的城市边际流量、数量及集中度。它们描述的是当前可核验子集。

## 核查文件

- `audit/validation.json`：逐项核查及全量完成状态。
- `audit/unresolved_places.csv`、`unresolved_priority.csv`：待核查地点及按相关端点流量排列的优先级。`incident_events` 是端点相关量，同一事件可能涉及两个地点，不能把它们相加当作事件总数。
- `audit/institutions_requiring_precise_geocoding.csv`：从本地机构表关联的地址核查清单。
- `audit/used_municipal_boundaries.geojson`：本轮实际使用的市镇参考边界。
- `audit/country_municipal_rules.csv`：各国采用的行政层级和来源。
- `audit/full_event_ledger_*.parquet`：包含全部原始事件的逐条新归属账本。
- `audit/needs_municipal_review_*.parquet`、`within_same_municipality_*.parquet`：待核查与同市镇事件，均保留，不计入严格城际文件。
- `audit/place_catalog_including_unverified.csv`：含未核实地点的辅助目录，不能用行数统计城市数量。

源数据、上一轮清洗数据和已有图表保留原样。输入关系和哈希见 `manifest.json`。原始作者—机构记录缺少的校区归属，不能通过城市中心点凭空补齐。
