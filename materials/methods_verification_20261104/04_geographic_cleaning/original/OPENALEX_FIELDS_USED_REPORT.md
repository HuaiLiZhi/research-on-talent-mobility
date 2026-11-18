# 研究中实际使用的 OpenAlex 字段报告

> 生成时间：2026-09-13
> 数据快照：`/data2/openAlex/openalex_snapshot/data`（updated_date 最新 2026-03-30）
> 研究对象：作者学术流动性（author mobility）与城市/学科存量

---

## 1. 总体说明

研究只使用了 OpenAlex 标准快照中的 **3 个实体 + 1 套主题分类体系**：

| 实体 | 快照目录 | 用途 |
|---|---|---|
| works | `data/works/` | 论文年份、学科、作者归属、FWCI |
| authors | `data/authors/` | 作者身份、h-index、主题/机构 |
| institutions | `data/institutions/` | 机构地理坐标与国家 |
| topics/field/subfield/domain | 内嵌于 works/authors | 学科分类 |

下游实际落地的 CSV 只有 7 张（`openalex_mobility_author_entity_deduped/`）：`detail_authors.csv`、`authors__topics.csv`、`authors__topic_share.csv`、`authors__affiliations.csv`、`authors__affiliation_years.csv`、`institutions.csv`、`detail_author_year_locations.csv`。以下字段即这些表及其上游抽取脚本真正读取/消费的字段。

---

## 2. works 实体字段

直接扫描 `works/updated_date=*/part_*.gz` 使用（`s10_extract_works_author_mobility.py`、`s12_extract_author_fwci_tiers.py`）：

| 字段路径 | 含义 | 研究用途 |
|---|---|---|
| `id` | work ID | 唯一标识 / 去重键 |
| `publication_year` | 发表年份 | 年度聚合、迁移序列 |
| `primary_topic.field.id` | 主领域 ID | 论文学科 field |
| `primary_topic.field.display_name` | 主领域名 | 学科标签 |
| `primary_topic.subfield.id` | 主子领域 ID | 论文学科 subfield |
| `primary_topic.subfield.display_name` | 主子领域名 | 学科标签 |
| `topics[0].field/subfield` | 首个 topic 的领域 | primary_topic 缺失时回退 |
| `fwci` | 领域归一化引文影响 | FWCI 分层（`s12_extract_author_fwci_tiers.py`） |
| `updated_date` | 快照更新日期 | 多分区版本去重（保留最新） |
| `authorships` | 作者署名列表 | 抽取作者-地点（见下） |

### 2.1 `authorships[]`（works 内嵌，实际使用）

| 字段路径 | 含义 | 研究用途 |
|---|---|---|
| `author.id` | 作者 ID | author_id（必需） |
| `author.display_name` | 作者名 | 展示 |
| `author.orcid` | ORCID | 作者标识 |
| `author_position` | 作者位次 | 代表地点选择 |
| `is_corresponding` | 是否通讯作者 | 导出备用 |
| `institutions[].id` | 机构 ID | 关联机构地理 |
| `institutions[].display_name` | 机构名 | 展示 |
| `institutions[].country_code` | 机构国家码 | 国家解析 |
| `institutions[].type` | 机构类型 | 机构类型分析 |
| `institutions[].ror` | 机构 ROR | 机构标识 |
| `countries[]` | 署名国家码 | 国家级别地点 |
| `raw_affiliation_strings[]` | 原始署名文本 | 文本回退解析国家/机构 |
| `raw_affiliation_string` | 原始署名文本（旧字段） | 文本回退解析 |
| `affiliations[].institution_ids[]` | 署名机构 ID | 通用导出链接表 |
| `affiliations[].raw_affiliation_string` | 署名原始文本 | 通用导出 |

---

## 3. authors 实体字段

`s01_export_openalex_entities.py` 导出，`s20_dedupe_author_entity_mobility.py` 去重后使用：

### 3.1 `detail_authors.csv`

| 字段 | 含义 | 研究用途 |
|---|---|---|
| `id` | author ID | 主键 |
| `display_name` | 作者名 | 展示 |
| `orcid` | ORCID | 作者标识 |
| `works_count` | 论文数 | 学者规模指标 |
| `cited_by_count` | 被引数 | 学者影响力 |
| `summary_stats.h_index` | h-index | 学者分层（`s13_extract_author_hindex_tiers.py`） |
| `summary_stats.i10_index` | i10-index | 学者影响力 |
| `summary_stats.2yr_mean_citedness` | 两年平均被引 | 学者影响力 |
| `updated_date` | 更新日期 | 版本去重 |

### 3.2 `authors__topics.csv` / `authors__topic_share.csv`

| 字段 | 含义 | 研究用途 |
|---|---|---|
| `parent_id` | author ID | 关联作者 |
| `position` | 主题排名 | 取 rank-1 主导学科 |
| `topic_id` / `topic_display_name` | 主题 ID/名 | 学科 |
| `topic_count`（topics） | 论文计数 | 主导学科判定 |
| `topic_value`（topic_share） | 主题份额 | 主导学科判定 |
| `subfield_id` / `subfield_display_name` | 子领域 ID/名 | 学科分类 |
| `field_id` / `field_display_name` | 领域 ID/名 | 学科分类 |
| `domain_id` / `domain_display_name` | 域 ID/名 | 学科分类 |
| `updated_date` | 更新日期 | 版本去重 |

### 3.3 `authors__affiliations.csv`

| 字段 | 含义 | 研究用途 |
|---|---|---|
| `parent_id` | author ID | 关联作者 |
| `position` | 机构位次 | 机构排序 |
| `institution_id` | 机构 ID | 关联机构 |
| `institution_ror` | 机构 ROR | 机构标识 |
| `institution_display_name` | 机构名 | 展示 |
| `institution_country_code` | 机构国家码 | 国家 |
| `institution_type` | 机构类型 | 机构类型分析 |
| `updated_date` | 更新日期 | 版本去重 |

### 3.4 `authors__affiliation_years.csv`

| 字段 | 含义 | 研究用途 |
|---|---|---|
| `parent_id` | author ID | 关联作者 |
| `affiliation_position` | 机构位次 | 机构排序 |
| `year_position` | 年份位次 | 年份排序 |
| `year` | 归属年份 | 职业起点、年度序列 |
| `updated_date` | 更新日期 | 版本去重 |

---

## 4. institutions 实体字段

`institutions.csv`（地理信息是流动性分析的核心）：

| 字段 | 含义 | 研究用途 |
|---|---|---|
| `id` | 机构 ID | 主键 / 关联作者 |
| `ror` | ROR ID | 机构标识 |
| `display_name` | 机构名 | 展示 |
| `type` | 机构类型 | 机构类型分析 |
| `country_code` | 机构国家码 | 国家（原始） |
| `works_count` | 机构论文数 | 规模 |
| `cited_by_count` | 机构被引数 | 影响力 |
| `geo.city` | 城市 | 城市级地点 |
| `geo.geonames_city_id` | GeoNames 城市 ID | 城市标准化 |
| `geo.region` | 省/州 | 地区 |
| `geo.country_code` | 国家码（规范） | 国家 |
| `geo.country` | 国家名 | 国家 |
| `geo.latitude` | 纬度 | 地理坐标 |
| `geo.longitude` | 经度 | 地理坐标 |
| `updated_date` | 更新日期 | 版本去重 |

---

## 5. 学科分类体系（topics 内嵌字段）

通过 `primary_topic` / `topics[]` / `topic_share[]` 使用：

| 字段 | 含义 |
|---|---|
| `topic.id` / `topic.display_name` | 主题 ID / 名 |
| `subfield.id` / `subfield.display_name` | 子领域 ID / 名 |
| `field.id` / `field.display_name` | 领域 ID / 名 |
| `domain.id` / `domain.display_name` | 域 ID / 名 |
| `topic_share.value` | 主题份额 |
| `topics[].count` | 主题论文计数 |
| `topics[].score` | 主题相关度分数 |

---

## 6. 派生输出字段（非 OpenAlex 原始字段）

用于确认字段的最终流向：

- `detail_author_year_locations.csv`：`author_id, author_display_name, orcid, year, affiliation_position, year_position, institution_id, institution_ror, institution_display_name, institution_type, institution_country_code, geo_city, geo_geonames_city_id, geo_region, geo_country_code, geo_country, geo_latitude, geo_longitude, author_works_count, author_cited_by_count, author_h_index, updated_date`
- `count_mobility_flow_by_field.csv`：`from_city, from_country, from_region, from_country_code, from_latitude, from_longitude, to_city, to_country, to_region, to_country_code, to_latitude, to_longitude, year, field_display_name, mobility_count`
- `count_stock_city_field_year.csv`：`country_code, country_name, geo_city, geo_region, geo_latitude, geo_longitude, year, field_id, field_display_name, author_count, works_count`
- 分层表：`h_index`、`fwci`、`h_index_tier_main/robust`、`fwci_tier_main/robust`、`first_aff_year` 等。

---

## 7. 未使用 / 仅导出未消费的字段

`s01_export_openalex_entities.py` 具备通用展平能力（可导出 `works__locations`、`referenced_works`、`related_works`、`apc_list`、`apc_paid`、`concepts`、`indexed_in`、`corresponding_author_ids`、`corresponding_institution_ids`、`awards` 等），但 `openalex_mobility_author_entity/` 目录中**只落地了上述 7 张表**，因此以下内容未被本研究消费：

- works 的 `locations`、`referenced_works`、`related_works`、`apc_list`、`apc_paid`、`indexed_in`、`is_retracted`、`is_paratext`、`concepts`/`x_concepts`、`counts_by_year`
- works 的 `corresponding_author_ids`、`corresponding_institution_ids`
- awards 实体、funders、sources、publishers 等其它实体

---

## 8. 字段来源脚本索引

| 阶段 | 脚本 | 使用字段 |
|---|---|---|
| 通用实体导出 | `s01_export_openalex_entities.py` | authors / institutions 全标量 + topics/affiliations |
| 作者-工作地点抽取 | `s10_extract_works_author_mobility.py` | works.id/year/primary_topic/authorships/institutions/countries/raw_affiliation |
| 作者-工作地点抽取（简版） | `extract_openalex_work_author_locations.py` | works.id/year/authorships |
| 按年机构重建 | `rebuild_author_locations_from_works.py` | works.publication_year/authorships |
| h-index 分层 | `s13_extract_author_hindex_tiers.py` | authors.summary_stats_h_index、authors__topics、authors__affiliation_years |
| FWCI 分层 | `s12_extract_author_fwci_tiers.py` | works.fwci、works.publication_year、works.authorships |
| 城市-学科存量 | `s14_extract_scholar_stock_by_city_year.py` | author_year_locations + authors__topics |
| 分层存量 | `s15_extract_scholar_tier_stock.py` | author_year_locations + 分层表 |
| 实体去重 | `s20_dedupe_author_entity_mobility.py` | `updated_date` |
