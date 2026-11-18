# OpenAlex 数据存储与工具链报告

> 生成时间：2026-09-13
> 项目根目录：`/data2/openAlex`

---

## 1. 数据存储位置

| 层级 | 路径 | 格式 | 规模/说明 |
|---|---|---|---|
| 原始快照 | `/data2/openAlex/openalex_snapshot/data/` | gzip JSONL | 约 1.1 TB；21 个实体目录 |
| 原始实体 CSV（未去重） | `/data2/openAlex/openalex_mobility_author_entity/` | CSV | 从快照导出 |
| 全量作者-工作地点抽取 | `/data2/openAlex/openalex_mobility_works_raw/` | CSV | `author_work_locations.csv` 约 169 GB |
| 去重 + 聚合结果 | `/data2/openAlex/openalex_mobility_deduped/` | CSV + Parquet | 含核心结果表 |
| MySQL 数据落盘 | `/usr/local/mysql/data`（容器 bind mount） | InnoDB | 配置 `/usr/local/mysql/conf`，日志 `/usr/local/mysql/logs` |

原始快照 `data/` 下 21 个实体目录：

```
authors  awards  concepts  continents  countries  domains  fields  funders
institutions  institution-types  keywords  languages  licenses  publishers
sdgs  sources  source-types  subfields  topics  works  work-types
```

其中 `works/` 最大，包含 381 个 `updated_date` 分区、2,127 个 `.gz` 文件。

---

## 2. 查询 / 处理引擎

### 2.1 MySQL 8.0（关系库）

- 部署：Docker 容器 `mysql8`，镜像 `mysql:8.0`，实际版本 **8.0.44**。
- 连接：`127.0.0.1:3306`，数据库 **`openalex`**。
- 存储引擎/字符集：`InnoDB`，`utf8mb4` / `utf8mb4_unicode_ci`。
- 建表脚本：`sql/create_openalex_mobility_mysql.sql`。
- 导入脚本：`s70_import_mobility_to_mysql.py`（分块 `LOAD DATA LOCAL INFILE`，`REPLACE/IGNORE` 模式）。
- 已导入表（`openalex_mobility_imported_tables.txt`）：
  - `institutions`
  - `authors`
  - `authors__topics`
  - `authors__topic_share`
  - `authors__affiliations`
  - `authors__affiliation_years`
  - `author_year_locations`

### 2.2 DuckDB（分析型聚合）

- 版本：**1.5.4**。
- 用途：直接读取 Parquet 做大规模聚合，产出流动性/存量结果表。
- 脚本：
  - `s41_count_flow.py` → `count_mobility_flow_by_field.csv`
  - `s40_count_stock.py` → `count_stock_city_field_year.csv`
  - `s30_aggregate_discipline_tables.py` → `mobility_by_field*.csv` 等
- 典型配置：`threads=90`、`memory_limit=180GB`、`temp_directory=/data2/openAlex/duckdb_tmp`。

### 2.3 文件层

- 原始：gzip JSONL
- 中间/结果：CSV、Parquet（ZSTD 压缩）

---

## 3. 主要处理语言与版本

| 语言/运行时 | 版本 | 用途 |
|---|---|---|
| Python | **3.10.14**（base conda `/root/miniconda3`） | 全部抽取 / 去重 / 导入脚本 |
| Python | 3.10.12（conda 环境 `orcid`） | 运行 DuckDB 聚合脚本 |
| DuckDB | **1.5.4** | Parquet 聚合查询 |
| Bash | 系统默认 | `sort -u` 整表跨分区去重（`s21_dedupe_works_mobility.sh`） |

Python 依赖：标准库 + `mysql-connector-python` + `python-dotenv`。

---

## 4. 配置文件

连接与导入参数集中在 `/data2/openAlex/.env`（不含明文密钥）：

| 变量 | 值 |
|---|---|
| `MYSQL_HOST` | `127.0.0.1` |
| `MYSQL_PORT` | `3306` |
| `MYSQL_USER` | `root` |
| `MYSQL_DATABASE` | `openalex` |
| `MYSQL_ENABLE_LOCAL_INFILE` | `true` |
| `MYSQL_DUPLICATE_MODE` | `ignore` |
| `MYSQL_SKIP_EXISTING` | `true` |
| `MYSQL_LOAD_CHUNK_ROWS` | `1000000` |
| `MYSQL_LOAD_CHUNK_DIR` | `/data2/openAlex/openalex_mobility_mysql_load_chunks` |
| `MYSQL_KEEP_LOAD_CHUNKS` | `false` |
| `MYSQL_IMPORTED_TABLES_FILE` | `/data2/openAlex/openalex_mobility_imported_tables.txt` |

> 注：`MYSQL_PASSWORD` 已省略。

---

## 5. 相关文件索引

| 用途 | 路径 |
|---|---|
| 原始快照 | `openalex_snapshot/` |
| MySQL 建表 SQL | `sql/create_openalex_mobility_mysql.sql` |
| MySQL 导入脚本 | `s70_import_mobility_to_mysql.py` |
| DuckDB 聚合脚本 | `s41_count_flow.py`、`s40_count_stock.py`、`s30_aggregate_discipline_tables.py` |
| 连接配置 | `.env` |
