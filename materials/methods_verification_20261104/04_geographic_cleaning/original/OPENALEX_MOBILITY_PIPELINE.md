# OpenAlex 学者流动数据：从原始快照到清洗数据集的完整处理过程

本文档记录 `openalex_mobility_deduped/` 数据集的完整生成链路：从本地 OpenAlex 原始快照
（`openalex_snapshot/data/`）出发，经过提取、去重、聚合、计数、清洗，到最终可用的学者流动数据。

---

## 1. 数据流总览

```
原始快照 openalex_snapshot/data/
   ├── works/        492,361,307 条 work（2127 个 gz，381 个 updated_date 分区，2016–2026）
   ├── authors/      113,641,286 条 author（546 个 gz，55 个分区，仅 2026-02-01..03-30）
   └── institutions/ 121,512 条 institution（50 个 gz）

作者实体侧（旧，仅对照）                        works 侧（新，主链路）
  s11_extract_author_entity_mobility.py            s10_extract_works_author_mobility.py
        ↓                                              ↓  (S1/S2/S3 分级定位 + 学科 + 统计)
  openalex_mobility_author_entity/                         openalex_mobility_works_raw/_partials/*.tsv
        ↓ s20_dedupe_author_entity_mobility.py              ↓ DuckDB 全核并行（去重/聚合/计数）
  openalex_mobility_author_entity_deduped/                 openalex_mobility_deduped/
                                                       ├─ detail_author_work_locations.parquet
                                                       ├─ detail_author_year_locations.csv, detail_authors.csv
                                                       ├─ institutions.csv
                                                       ├─ mobility_by_field / by_subfield (+author).csv
                                                       ├─ count_stock_city_field_year.csv   (存量计数)
                                                       ├─ count_mobility_flow_by_field.csv   (城际流动计数)
                                                       └─ *_clean(_primary).csv        (P0+P1 清洗)
```

主链路（最终数据集）是 **works 侧**；作者实体侧仅作为对照与历史产物保留。
最终交付**只保留 CSV**（parquet 中间格式已按需求删除，唯一例外见第 9 节）。

---

## 2. 原始数据

### 2.1 目录布局
- 根目录：`/data2/openAlex/openalex_snapshot/data/`
- 每个实体按 `updated_date=YYYY-MM-DD/part_XXXX.gz` 分区；每行一个 JSON 对象。

### 2.2 各实体规模

| 实体 | gz 文件数 | updated_date 分区数 | 记录数 | 分区时间范围 |
|---|---|---|---|---|
| works | 2,127 | 381 | 492,361,307 | 2016-06-24 ~ 2026-03-30 |
| authors | 546 | 55 | 113,641,286 | 2026-02-01 ~ 2026-03-30 |
| institutions | 50 | 50 | 121,512 | 2026-02 ~ 2026-03 |

### 2.3 关键语义与坑
- **works 分区**：按 work 的最后更新日期分区；同一 work 基本只出现在一个分区（少量跨分区重复，见去重）。
- **authors 快照只覆盖约 2 个月的更新窗口**（2026-02-01..03-30），不是完整作者全集；
  因此不能以 `authors` 实体作为作者全集，最终以 **works 的 authorships** 为准。
- works 中每个 `authorship` 含：`author.id`、`author.display_name`、`orcid`、`author_position`、
  `institutions[]`（含 id / country_code）、`countries[]`、`raw_affiliation_strings` 等。
- `institutions` 实体含 `geo`（city / region / country_code / country / latitude / longitude）与
  `display_name_alternatives` 等，用于地理回填。

---

## 3. 作者实体侧（旧流水线，保留对照）

### 3.1 提取
脚本：`s11_extract_author_entity_mobility.py`
- 输入：`authors/`、`institutions/` 快照（`--partition all`）。
- 逻辑：读 `authors.affiliations[].institution` + `affiliations[].years[]`，用 institutions 实体补 geo。
- 输出目录：`openalex_mobility_author_entity/`（**未去重的中间目录已删除**；去重版 `openalex_mobility_author_entity_deduped/` 保留）
  - `detail_authors.csv`（作者元数据：display_name/orcid/works_count/h_index…）
  - `authors__topics.csv`、`authors__topic_share.csv`（作者主题分布）
  - `authors__affiliations.csv`、`authors__affiliation_years.csv`
  - `detail_author_year_locations.csv`（作者-年-机构，含 geo）
  - `institutions.csv`

### 3.2 去重
脚本：`s20_dedupe_author_entity_mobility.py`
- 按每个 author 的最新 `updated_date` 保留一行，子表按该 author 的保留版本过滤。
- 输出目录：`openalex_mobility_author_entity_deduped/`（当前仍在，未改动）。

### 3.3 局限（为什么不作为主链路）
- 作者快照只有 2 个月窗口 → 大量作者缺失；
- 只有约 **28,876,544** 位作者有 `affiliations[].years`（可产生流动行），其余 affiliations 为空；
- 因此作者实体侧覆盖不全，且无法覆盖 2016 年前的历史。

> 对照结论：works 全量侧覆盖 **53,093,779** 位作者，是作者实体移动表作者池的约 1.8 倍。

---

## 4. works 侧旧实现（已删除）

以下早期产物与脚本已被最终数据集取代，**已删除**（不再占用磁盘，也不再维护）：

- ~~`rebuild_author_locations_from_works.py` → `openalex_author_locations_works/`~~
- ~~`extract_openalex_work_author_locations.py` → `openalex_work_author_locations/`~~
- ~~`merge_author_locations.py` → `openalex_author_locations_combined/`~~

其功能分别被主链路的 `s10_extract_works_author_mobility.py` +
`s23_build_mobility_duckdb.py`（去重 per-work 明细、作者-年-机构-学科主表）覆盖。

---

## 5. 主链路：works 全量提取

脚本：`s10_extract_works_author_mobility.py`

### 5.1 目标
从全部 works 快照中，为每条 authorship 提取有效学者、年份、至少国家级的地理位置，
并尽量保留更细粒度（机构 → 城市 → 省州 → 国家），同时保留作品学科。

### 5.2 分级定位（每条 authorship）
| 级别 | 判定 | 产出 |
|---|---|---|
| S1 institution | `authorships.institutions[].id` 命中 institutions 实体 geo | 机构 + 城市/省州/国家/经纬 |
| S2 country | `authorships.countries[]` / 机构 country_code，且未被 S1 覆盖 | 国家 |
| S3 raw text | 仍无国家时解析 `raw_affiliation_strings`：机构名匹配升机构级；否则国家名/两字母码/唯一城市 | 机构或国家 |

规则：
- 只保留有 `author.id` 的 authorship；作者名/ORCID 取自 authorship。
- 必须有 `publication_year`，且年份限制 1500–2100（后续清洗再收窄）。
- **每条输出行保证有 author_id、year、至少 country**，否则丢弃并计入统计。
- 单 authorship 内按 `(level, country, institution)` 去重。

### 5.3 输出（每个 gz → 一个 TSV 分片，22 列）
```
author_id, author_display_name, orcid, work_id, publication_year, author_position,
geo_level, country_code, country_name, institution_id, institution_display_name,
institution_type, institution_ror, geo_city, geo_region, geo_latitude, geo_longitude,
source, field_id, field_display_name, subfield_id, subfield_display_name
```
- `source` ∈ {institution, countries, raw_institution, raw_country}
- 学科来自 work 的 `primary_topic`（field/subfield），缺失时回退到首个 topic。

### 5.4 全量提取统计（第一次全量运行，`_extraction_stats.json`）
| 指标 | 数值 |
|---|---|
| 扫描 works | 492,361,307 |
| 有年份 works | 464,758,184（94.4%） |
| 含 author id 的 authorship | 779,075,357 |
| 无 author id（丢弃） | 548,278,450 |
| 所有阶段后仍无国家（丢弃） | 320,153,162 |
| 输出行 | 582,727,561 |
| 其中有 id authorship 覆盖率 | 58.91% |
| 耗时 | 5,241 s |

> 覆盖率低的主因：2025-11-06 等 bulk 分区几乎没有机构解析、且无 author id 比例高。

---

## 6. 去重与基础聚合（DuckDB 全核并行）

由于分片总量约 215 GB、5.8 亿行，使用 DuckDB（90 线程）代替单线程拼接。
脚本：`s23_build_mobility_duckdb.py`

1. **物化**：所有 `chunk_*.tsv` → `mobility_mob.parquet`（约 19.4 GB，耗时 171 s；中间文件，已删除）。
2. **去重 per-work**：`SELECT DISTINCT *` → `detail_author_work_locations.parquet`
   - 5,819.4 万行（581,947,959），较原始 582,727,561 行去除 **779,602** 条跨分区重复。
3. **作者-年-机构-学科主表**：`detail_author_year_locations.csv`
   - 键：`(author_id, year, institution_id, field_id, subfield_id)`
   - `works_count = COUNT(*)`（去重后即不同 work 数）
   - 行数 **413,016,578**。
4. **作者元数据**：`detail_authors.csv`（**53,093,779** 位；works_count、first_year、last_year）。

> 除 `detail_author_work_locations.parquet` 外，其余中间 parquet 已按需求删除，仅保留 CSV。

---

## 7. 学科聚合表与计数表

### 7.1 学科流动表
脚本：`s30_aggregate_discipline_tables.py`，从 `author_year_locations` 聚合。

| 文件 | 行数 | 学科来源 |
|---|---|---|
| `detail_mobility_by_field.csv` | 360,872,720 | 作品 primary_topic 的 field |
| `detail_mobility_by_subfield.csv` | 413,016,578 | 作品 primary_topic 的 subfield |
| `detail_mobility_by_field_author.csv` | 295,581,405 | 作者主导 field（按作品数 argmax） |
| `detail_mobility_by_subfield_author.csv` | 295,581,405 | 作者主导 subfield |

列：
```
author_id, author_display_name, orcid, year, institution_id, institution_display_name,
institution_type, institution_ror, country_code, country_name, geo_city, geo_region,
geo_latitude, geo_longitude, <field|subfield>_id, <field|subfield>_display_name, works_count
```

### 7.2 存量计数表（城市×年×学科）
脚本：`s40_count_stock.py`，从 `detail_author_work_locations.parquet` 直接分组。
- 文件：`count_stock_city_field_year.csv`，**12,721,014** 行。
- 列：`country_code, country_name, geo_city, geo_region, geo_latitude, geo_longitude, year, field_id, field_display_name, author_count, works_count`
- `author_count` = 不同作者数；`works_count` = 不同论文数。

> 清洗版见 8.3：`count_stock_city_field_year_clean.csv`（5,701,448 行）与
> `count_stock_city_field_year_clean_primary.csv`（4,874,234 行）。

### 7.3 城际流动计数表
脚本：`s41_count_flow.py`，与旧 `city_mobility_by_field.csv` 同构。
- 口径：每个作者每年取 `works_count` 最大的城市为主城市，相邻年份城市（或国家）变化记一次迁移；
  field 用作者主导 field。
- 文件：`count_mobility_flow_by_field.csv`，**26,627,089** 行，迁移事件 36,378,486。
- 列：`from_city, from_country, from_region, from_country_code, from_latitude, from_longitude, to_city, to_country, to_region, to_country_code, to_latitude, to_longitude, year, field_display_name, mobility_count`

> 清洗版见 8.4：`count_mobility_flow_by_field_clean.csv`（20,646,492 行，迁移事件 36,376,033）。

### 7.4 Python 版替代脚本（等价逻辑，未用于全量）
`s21_dedupe_works_mobility.sh` → `s22_build_author_year_locations.py` → `s33_aggregate_field_subfield.py`。

---

## 8. 数据清洗（P0 + P1，按主机构）

清洗脚本：
- `s50_clean_mobility.py`：流动明细（作者级）清洗；
- `s51_clean_stock.py`：存量计数清洗（回到去重 per-work 明细重算）；
- `s52_clean_flow.py`：城际流动计数清洗。

### 8.1 通用清洗规则（P0 + P1）
1. **年份**：转 int，限定 **1900–2026**（原始 `<1900` 206,729 行、`>2026` 547 行剔除）。
2. **geo_level**：有 institution_id → `institution`，否则 `country`。
3. **经纬度**：范围校验（纬度 ±90、经度 ±180），空/0 置 null；机构行使用城市级代表坐标
   （同一 `city_key` 内机构坐标的中位数）。
4. **机构类型**：用 institutions 实体按 institution_id 回填缺失。
5. **城市消歧**：
   - `city_key` = `gn:<geonames_city_id>`（优先）或 `cc:<国家>|<城市小写>`；
   - `city_norm` = 去音标小写；`city_geonames_id` 保留；
   - 同城机构坐标取中位数作为该城市代表坐标。
6. **省/州补全**：按 `city_key` 取同城机构中出现最多的非空 `region` 回填。
7. **主机构**：每个 `(author, year)` 取 `works_count`（作品数）合计最大的机构为
   `primary_institution_id`，行加 `is_primary` 标记；**primary 表**仅保留主机构行（消除共同挂靠噪声）。
8. 学科空值按要求**不处理**。

### 8.2 流动明细清洗（`s50_clean_mobility.py`）
输入 `detail_mobility_by_field.csv`（原 360,872,720 行）→ 输出：

| 文件 | 行数 | 说明 |
|---|---|---|
| `detail_mobility_by_field_clean.csv` | 360,665,444 | 清洗后全量（含 `is_primary`） |
| `detail_mobility_by_field_clean_primary.csv` | 219,858,164 | 仅主机构行 |
| `detail_mobility_by_field_clean_stats.json` | — | 统计 |

- 覆盖作者：全量 53,024,590；主机构表 50,945,985。
- `(author, year, institution, field)` 无重复键。
- 新增列：`year(int)`、`geo_level`、`city_norm`、`city_geonames_id`、`city_key`、`is_primary`、`primary_institution_id`。
- 省/州填充率 45.5% → **89.52%**。

### 8.3 存量计数清洗（`s51_clean_stock.py`）
由于存量表已聚合，需回到去重 per-work 明细重算，再套用 8.1 规则。输出：

| 文件 | 行数 | 说明 |
|---|---|---|
| `count_stock_city_field_year_clean.csv` | 5,701,448 | 清洗后全量存量 |
| `count_stock_city_field_year_clean_primary.csv` | 4,874,234 | 仅主机构 |

- 列：`country_code, country_name, geo_city, city_norm, city_geonames_id, city_key, geo_region, geo_latitude, geo_longitude, geo_level, year, field_id, field_display_name, author_count, works_count`
- `author_count` = 不同作者数；`works_count` = 不同论文数。
- 行数较原表（12,721,014）下降，主要是城市消歧把原先仅因 region/坐标不同而分裂的行合并。

### 8.4 城际流动计数清洗（`s52_clean_flow.py`）
基于清洗后的“作者-年-主机构城市”序列重算迁移计数。输出：

| 文件 | 行数 | 迁移事件 | 说明 |
|---|---|---|---|
| `count_mobility_flow_by_field_clean.csv` | 20,646,492 | 36,376,033 | 清洗后城际流动计数（年份 1901–2026） |

- 列：`from_city, from_country, from_region, from_country_code, from_latitude, from_longitude, to_city, to_country, to_region, to_country_code, to_latitude, to_longitude, year, field_display_name, mobility_count`
- 口径：每个 `(作者,年)` 取主机构的城市为当年城市；相邻年份主城市（或国家）变化记一次迁移；
  field 用作者主导 field。
- 行数较未清洗版（26,627,089）下降，主要是城市消歧合并了城市对；迁移事件总量基本一致。

---

## 9. 最终数据集目录清单：`openalex_mobility_deduped/`

> 按要求最终只保留 CSV；parquet 中间格式已删除，唯一例外是 `detail_author_work_locations.parquet`
> （去重 per-work 明细，无 CSV 版本，用于复现聚合）。

| 文件 | 大小 | 行数 | 说明 |
|---|---|---|---|
| `detail_author_work_locations.parquet` | 27.6 GB | 581,947,959 | 去重 per-work 明细（22 列，唯一 parquet） |
| `detail_author_year_locations.csv` | 140 GB | 413,016,578 | 去重主表（作者,年,机构,field,subfield） |
| `detail_authors.csv` | 3.6 GB | 53,093,779 | 作者元数据 |
| `institutions.csv` | 23 MB | 121,512 | 机构表 |
| `detail_mobility_by_field.csv` | 100 GB | 360,872,720 | 作品 field 聚合（未清洗） |
| `detail_mobility_by_subfield.csv` | 119 GB | 413,016,578 | 作品 subfield 聚合（未清洗） |
| `detail_mobility_by_field_author.csv` | 81 GB | 295,581,405 | 作者主导 field（未清洗） |
| `detail_mobility_by_subfield_author.csv` | 84 GB | 295,581,405 | 作者主导 subfield（未清洗） |
| `count_stock_city_field_year.csv` | 1.5 GB | 12,721,014 | 城市×年×field 存量计数（未清洗） |
| `count_mobility_flow_by_field.csv` | 3.7 GB | 26,627,089 | 城际流动计数（未清洗） |
| `detail_mobility_by_field_clean.csv` | 130 GB | 360,665,444 | 清洗后流动明细（全量） |
| `detail_mobility_by_field_clean_primary.csv` | 80 GB | 219,858,164 | 清洗后流动明细（主机构） |
| `count_stock_city_field_year_clean.csv` | 928 MB | 5,701,448 | 清洗后存量计数（全量） |
| `count_stock_city_field_year_clean_primary.csv` | 803 MB | 4,874,234 | 清洗后存量计数（主机构） |
| `count_mobility_flow_by_field_clean.csv` | 3.2 GB | 20,646,492 | 清洗后城际流动计数 |
| `detail_mobility_by_field_clean_stats.json` | 560 B | — | 流动明细清洗统计 |

### 清洗后三张核心表（推荐使用）
| 用途 | 全量 | 主机构 |
|---|---|---|
| 流动明细（作者级） | `detail_mobility_by_field_clean.csv` | `detail_mobility_by_field_clean_primary.csv` |
| 存量计数（城市×年×field） | `count_stock_city_field_year_clean.csv` | `count_stock_city_field_year_clean_primary.csv` |
| 城际流动计数 | `count_mobility_flow_by_field_clean.csv` | —（本身已用主机构口径） |

---

## 10. 覆盖率与已知问题

- **扫描 vs 可用**：扫描全部 492,361,307 篇 work，最终流动表覆盖 **129,882,714** 篇（26.4%）有可定位作者的论文。
- **丢弃原因**：约 41% authorship 无 author id；约 41% 有 id 的 authorship 无任何可解析机构/国家；
  约 2.4% work 无年份。S3 文本兜底可再找回约 1% 的 authorship（含机构名/城市/国家）。
- **地理填充率**（`mobility_by_field`）：国家 100%、城市 96.5%、省/州 45.5%（清洗后 89.52%）。
- **跨分区重复**：per-work 去重去除 779,602 行（0.13%）。
- **authors 快照窗口**：作者实体侧只覆盖 2026-02–03，不作为主数据源。
- **年份异常**：原始存在 1500–2050 的年份，清洗限定 1900–2026。
- **field 空值**：约 1,944,278 行无学科，按要求未处理。

---

## 11. 复现命令

```bash
# 1) 全量提取（works 侧）
python3 s10_extract_works_author_mobility.py \
    --data-root /data2/openAlex/openalex_snapshot/data \
    --output-dir /data2/openAlex/openalex_mobility_works_raw \
    --workers 64

# 2) 去重 + 基础聚合（DuckDB）
python3 s23_build_mobility_duckdb.py        # -> author_work_locations_deduped / author_year_locations / authors

# 3) 学科聚合表
python3 s30_aggregate_discipline_tables.py          # -> mobility_by_field / by_subfield (+author)

# 4) 计数表
python3 s40_count_stock.py          # -> count_stock_city_field_year.csv
python3 s41_count_flow.py            # -> count_mobility_flow_by_field.csv

# 5) 清洗（P0+P1，按主机构）
python3 s50_clean_mobility.py    # -> mobility_by_field_clean(_primary).csv
python3 s51_clean_stock.py         # -> city_field_year_counts_clean(_primary).csv
python3 s52_clean_flow.py          # -> count_mobility_flow_by_field_clean.csv
```

> 说明：`run_duckdb_*.py` / `clean_*.py` 读取分片或 `detail_author_work_locations.parquet`，
> 使用 `SET threads=90, memory_limit='180GB'`，需保证 `temp_directory` 所在盘有足够空间。
> 中间 parquet 仅用于加速，可删除（本数据集已删除，仅保留 `detail_author_work_locations.parquet`）。

---

## 12. 脚本清单

| 脚本 | 作用 |
|---|---|
| `s10_extract_works_author_mobility.py` | works 全量提取（S1/S2/S3 + 学科 + 统计） |
| `s23_build_mobility_duckdb.py` | 分片物化、per-work 去重、author_year_locations、authors |
| `s30_aggregate_discipline_tables.py` | field/subfield 与作者主导学科聚合表 |
| `s40_count_stock.py` | 城市×年×field 存量计数 |
| `s41_count_flow.py` | 城际流动计数 |
| `s50_clean_mobility.py` | 流动明细 P0+P1 清洗（含主机构） |
| `s51_clean_stock.py` | 存量计数清洗（回明细重算，含主机构） |
| `s52_clean_flow.py` | 城际流动计数清洗（含主机构） |
| `s21_dedupe_works_mobility.sh` | 外部排序去重（CSV 版，替代路径） |
| `s22_build_author_year_locations.py` | 生成同构去重目录（替代路径） |
| `s33_aggregate_field_subfield.py` | field/subfield 聚合（替代路径） |
| `s32_aggregate_author_mobility.py` | 早期聚合原型（保留） |

### 历史/对照脚本（保留）
| 脚本 | 输出 |
|---|---|
| `s11_extract_author_entity_mobility.py` | `openalex_mobility_author_entity/`（作者实体侧原始提取；该中间目录已删除，脚本保留以便重建） |
| `s20_dedupe_author_entity_mobility.py` | `openalex_mobility_author_entity_deduped/`（作者实体侧去重数据集，保留） |

> 已删除的旧 works 侧脚本：`rebuild_author_locations_from_works.py`、
> `extract_openalex_work_author_locations.py`、`merge_author_locations.py`
> 及其测试；对应数据目录 `openalex_author_locations_works/`、
> `openalex_work_author_locations/`、`openalex_author_locations_combined/` 一并删除。
