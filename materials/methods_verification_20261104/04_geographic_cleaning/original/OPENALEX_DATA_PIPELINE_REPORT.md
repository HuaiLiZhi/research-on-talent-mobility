# OpenAlex 作者流动性数据管线报告

> 生成时间：2026-09-13
> 数据根目录：`/data2/openAlex`
> 快照版本：OpenAlex standard snapshot，最新分区 `updated_date=2026-03-30`（对应 RELEASE 2026-03-30）

---

## 1. 原始数据概况

| 指标 | 数值 |
|---|---:|
| works `.gz` 文件数 | 2,127 |
| `updated_date` 分区数 | 381 |
| works 压缩总大小 | 639,189,333,248 字节（约 595 GiB） |
| **原始 works 记录数（所有分区叠加）** | **492,361,307** |

- 原始记录数由 `openalex_snapshot/data/works/manifest` 中 2,127 个条目的 `record_count` 求和得到，与抽取日志 `openalex_mobility_works_raw/_extraction_stats.json` 中的 `"works": 492361307` 完全一致。
- 该数值是**所有历史月度分区叠加后的原始行数**，同一篇 work 可能出现在多个 `updated_date` 分区中（存在跨分区重复）。
- 快照 `RELEASE_NOTES.txt` 指出：walden 数据集（含 xpack）去重后的全量 works 约为 **463M**。

---

## 2. 是否清洗 / 清洗依据

有清洗，分三层进行。

### 2.1 按 `updated_date` 去重（实体级）

脚本：`s20_dedupe_author_entity_mobility.py`

- 对 `authors` / `institutions` 等实体，同一 `id` **只保留 `updated_date` 最新的一条记录**。
- 对作者子表（`authors__topics`、`authors__topic_share`、`authors__affiliations`、`authors__affiliation_years`、`author_year_locations`），保留其 `updated_date` 等于该 author 最新日期的行。
- 输出目录：`openalex_mobility_author_entity_deduped/`。

### 2.2 抽取时的规则过滤（记录级）

脚本：`s10_extract_works_author_mobility.py`

- 必须存在合法 `publication_year`（1500–2100），否则丢弃；必须有 `author_id`，否则丢弃。
- 地点解析优先级：
  - **S1 机构**：`authorships.institutions[].id` 关联 institutions 表得到 city/region/country/lat/lon；
  - **S2 国家**：`authorships.countries[]` 中未被 S1 覆盖的国家；
  - **S3 文本解析**：用 `raw_affiliation_strings` 解析国家名/代码，或在无歧义时提升为机构。
- 始终无法确定国家（地理锚点）的 authorship 被丢弃，并计入 `dropped_after_all_stages`。
- 同一文件内按 `(geo_level, country, institution)` 去重。

### 2.3 整表 `sort -u` 去重（跨分区）

脚本：`s21_dedupe_works_mobility.sh`

- 行内容已做 sanitize（无内嵌 tab/换行），因此字节完全相同的行即为跨 `updated_date` 分区的重复，用 `sort -u` 去除。

### 2.4 抽取统计（`_extraction_stats.json`）

| 指标 | 数值 |
|---|---:|
| 扫描 works 总数 | 492,361,307 |
| 有 publication_year 的 works | 464,758,184 |
| authorships 总数 | 779,075,357 |
| 无 author_id 的 authorship | 548,278,450 |
| 所有阶段后丢弃数 | 320,153,162 |
| 机构级行数 | 566,155,520 |
| 国家（S2）行数 | 442,655 |
| 文本解析机构行数 | 2,310,368 |
| 文本解析国家行数 | 13,819,018 |
| 输出总行数 | 582,727,561 |
| **authorship 覆盖率** | **58.91%** |

输出文件：`openalex_mobility_works_raw/author_work_locations.csv`（约 169 GB）。

---

## 3. 处理后的核心结果表

聚合脚本：`s41_count_flow.py`、`s40_count_stock.py`、`s30_aggregate_discipline_tables.py`
输出目录：`openalex_mobility_deduped/`

| 文件 | 行数（含表头） | 数据记录数 |
|---|---:|---:|
| `count_mobility_flow_by_field.csv` | 26,627,090 | **26,627,089** |
| `count_stock_city_field_year.csv` | 12,721,015 | **12,721,014** |

### 3.1 `count_mobility_flow_by_field.csv`

- 含义：以作者**主导 field** 归类，聚合“城市 → 城市”的年度迁移流量。
- 逻辑：每个 (author, year) 取 `works_count` 最大的城市作为该年所在地，用 `lag` 与上一年比较；城市不同（或国家代码不同）即记为一次迁移；`COUNT(DISTINCT author_id)` 作为 `mobility_count`。
- 字段：`from_city, from_country, from_region, from_country_code, from_latitude, from_longitude, to_city, to_country, to_region, to_country_code, to_latitude, to_longitude, year, field_display_name, mobility_count`。

### 3.2 `count_stock_city_field_year.csv`

- 含义：城市 × 年份 × field 的作者/论文存量统计（stock）。
- 逻辑：对去重后的 `detail_author_work_locations.parquet`，按 `country_code, country_name, geo_city, geo_region, geo_latitude, geo_longitude, publication_year, field_id` 分组，统计 `COUNT(DISTINCT author_id)` 与 `COUNT(DISTINCT work_id)`。
- 字段：`country_code, country_name, geo_city, geo_region, geo_latitude, geo_longitude, year, field_id, field_display_name, author_count, works_count`。

---

## 4. 相关文件索引

| 用途 | 路径 |
|---|---|
| 原始快照 | `openalex_snapshot/` |
| 原始实体 CSV（未去重） | `openalex_mobility_author_entity/` |
| 按 updated_date 去重后实体 CSV | `openalex_mobility_author_entity_deduped/` |
| 全量作者-工作地点抽取 | `openalex_mobility_works_raw/` |
| 去重 + 聚合结果 | `openalex_mobility_deduped/` |
| 抽取统计 | `openalex_mobility_works_raw/_extraction_stats.json` |
| 抽取脚本 | `s10_extract_works_author_mobility.py` |
| 实体去重脚本 | `s20_dedupe_author_entity_mobility.py` |
| 整表去重脚本 | `s21_dedupe_works_mobility.sh` |
| 聚合脚本 | `s41_count_flow.py`、`s40_count_stock.py`、`s30_aggregate_discipline_tables.py` |
