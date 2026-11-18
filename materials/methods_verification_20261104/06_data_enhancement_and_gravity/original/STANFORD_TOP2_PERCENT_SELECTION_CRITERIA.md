# 斯坦福／Elsevier 全球前 2% 科学家数据集：筛选标准

核对日期：2026-09-16。本文说明官方数据集的入选口径，以及它与本项目 OpenAlex `top2` 分层的区别。

## 1. 数据集与版本

通常所称的“斯坦福全球前 2% 科学家榜单”，对应 **Updated science-wide author databases of standardized citation indicators** 系列数据集；研究对象是全球作者，并非仅限斯坦福大学学者。

本次核对时，官方入口指向 **V8（2025 年更新）**：

| 项目 | V8 口径 |
| --- | --- |
| 发布日期 | 2025-09-19 |
| 数据来源 | Scopus 作者档案与引文数据 |
| Scopus 快照日期 | 正文说明为 2025-08-01 |
| 生涯影响力统计截止 | 2024 年末 |
| 单年度影响力统计年份 | 2024 年 |
| 学科体系 | Science-Metrix，22 个领域、174 个细分学科 |
| 固定版本 DOI | `10.17632/btchxktzyw.8` |

来源：[官方 V8 数据集](https://elsevier.digitalcommonsdata.com/datasets/btchxktzyw/8)。该页正文仍出现“version (7)”字样，与页首及 DOI 的 V8 不一致；本文以页首与 DOI 识别版本，并保留这一元数据差异。页内采集日期字段也与正文快照日期不同，复现时应同时记录原始说明。

## 2. 核心筛选逻辑

**入选条件是“全球前 100,000 名”与“主要细分学科前 2%”的并集，而非同时满足两者。** 排名依据是综合引文指标 **c-score**。

| 入选路径 | 判定含义 |
| --- | --- |
| 全球排名路径 | 按 c-score 排入全球前 100,000 名；考虑含自引和剔除自引口径 |
| 细分学科路径 | 即使未进入全球前 100,000 名，仍可凭主要细分学科内 c-score 前 2% 入选 |

细分学科比较总体以**至少发表 5 篇论文**的作者为基础。不要把这一学科百分位总体定义，擅自扩写为两个入选路径均需额外执行的统一过滤条件；精确复现应核对所用版本的原表及代码。以上并集规则与学科比较总体见 [2020 年方法更新论文](https://doi.org/10.1371/journal.pbio.3000918)。

因此，以下筛选都不能直接替代官方名单：

- 将全部作者按 h-index、总被引次数或 FWCI 排序后直接取前 2%。
- 要求作者既进入全球前 100,000 名，又进入细分学科前 2%。
- 先筛出某个国家、机构或本项目中的作者，再在这个局部样本中取前 2%。

最后一种方式改变了排名分母。研究某机构的入选者时，应先确定官方入选身份，再按机构筛选。

## 3. c-score 使用的六项指标

| 指标 | 含义 |
| --- | --- |
| NC | 总被引次数 |
| H | h-index |
| Hm | 经共同作者数量调整的 Schreiber hm-index |
| NCS | 独立作者论文的被引次数 |
| NCSF | 独立作者或第一作者论文的被引次数 |
| NCSFL | 独立作者、第一作者或末位作者论文的被引次数 |

六项指标经对数变换、标准化后等权相加。不同论文中的署名指标缩写略有差异，以上采用 NCS／NCSF／NCSFL 表示。后面三项统计的是对应论文的**被引次数**，不是发文篇数；末位作者也不能直接替换成通讯作者。方法见 [2016 年综合指标论文](https://doi.org/10.1371/journal.pbio.1002501)。

2020 年更新论文给出的计算形式为：

```text
c(i) = Σ[k=1..6] log(1 + x(i,k)) / max[j] log(1 + x(j,k))
```

其中 `x(i,k)` 为作者 i 的第 k 项指标；分母使用对应统计总体的最大对数值。实际计算需采用相应版本、时间窗口、自引口径的归一化参数，不能用本项目局部作者样本的最大值替代。公式来源：[2020 年方法更新论文](https://doi.org/10.1371/journal.pbio.3000918)。

## 4. 生涯榜、年度榜与自引口径

| 名单 | 时间含义 |
| --- | --- |
| 生涯影响力榜（career-long） | 数据库所覆盖的长期引文积累；V8 截至 2024 年末 |
| 单年度影响力榜（single-year） | 在指定年度收到的引用；V8 为 2024 年收到的引用 |

年度榜允许此前发表的论文在该年度获得引用，不应误写成“只评价当年发表的论文”。两份名单分别计算，研究中应分别保留入选标记。[官方 V8 说明](https://elsevier.digitalcommonsdata.com/datasets/btchxktzyw/8)

数据库同时提供含自引与剔除自引指标。2019 年方法说明中，剔除自引按论文作者重合判断：施引论文与被引论文存在任一共同作者时，相应引用被作为自引处理。它比仅识别被评价作者本人自引的口径更广。[2019 年数据库方法论文](https://doi.org/10.1371/journal.pbio.3000384)

## 5. “前 2%”的分母和边界

应使用作者的**主要细分学科**及该学科合格作者总体。以排名 1 为最好、学科作者总数为 N，可以用下面的关系理解“从顶端计数的比例”：

```text
top_fraction = subfield_rank / subfield_author_count
```

例如，学科中有 50,000 位合格作者，排名 800 对应前 1.6%。这是排名比例示例，不能据此自行规定官方的并列名次、取整或边界实现；应以目标版本发布的入选表和代码为准。学科归属及排名比例方法见 [2019 年数据库方法论文](https://doi.org/10.1371/journal.pbio.3000384)。

特别注意：

- 已发布的入选名单是筛选结果，不能用名单中某学科的人数作为该学科全部作者数。
- `rank / N <= 0.02` 是从顶端计数的表达；“百分位大于 98”属于另一种方向的表达，离散样本与并列值处理也可能不同。
- 官方年度榜不等于按职业年龄分组排名。若自行按首发年份分组，所得结果属于新的研究定义。

## 6. 与本项目现有 `top2` 分层的区别

下表来自项目当前脚本的文档与默认参数；实际运行时应同时保存命令行参数。

| 维度 | 官方 Stanford／Elsevier 名单 | 本项目 FWCI 分层 | 本项目 h-index 分层 |
| --- | --- | --- | --- |
| 数据基础 | Scopus | OpenAlex works 与作者主题 | OpenAlex 作者、主题、机构年份 CSV |
| 排序指标 | c-score | 作者论文 FWCI 的算术平均值 | 作者 `summary_stats_h_index` |
| 学科体系 | Science-Metrix 主要细分学科 | OpenAlex field／subfield；默认 field | OpenAlex field／subfield；默认 field |
| 比较组 | 全球或主要细分学科总体 | 学科 × 首次发表年份区间 | 学科 × 最早机构年份区间 |
| 职业起始年份分组 | 上述官方入选规则未设置此分组 | 默认 5 年一组 | 默认 5 年一组；机构年份作为代理 |
| `top2` 定义 | 前 100,000 名或学科前 2% | 组内百分位 `> 98` | 组内百分位 `> 98` |

本地依据：

- [FWCI 分层脚本](D:/社会物理学论文/code/OpenAlex/s12_extract_author_fwci_tiers.py)：有主要主题、具有足够数值 FWCI 论文的作者进入计算；默认最少 1 篇有效 FWCI 论文。
- [h-index 分层脚本](D:/社会物理学论文/code/OpenAlex/s13_extract_author_hindex_tiers.py)：要求主要主题、数值 h-index 和至少一个机构年份；并列值采用平均秩。

**项目当前的 `top2` 应称为“本项目定义的组内前 2% 作者”，不能直接称为“斯坦福全球前 2% 科学家”。** FWCI 与 h-index 分层都是独立的研究操作化定义，不能因为阈值同为 2% 就认定为官方名单复现。

## 7. 本项目使用官方名单时的建议

以下是项目实施建议，不是官方新增筛选条件。

1. **固定版本和榜单类型。** 保存 DOI、下载日期、引用统计年份及文件名；生涯榜和年度榜分别导入。
2. **以官方表中的成员身份判定入选。** 不在截取后的项目样本中重新生成“官方前 2%”。若另取剔除自引的严格子集，应单独命名并记录筛选条件。
3. **建立作者匹配表。** 保留 Scopus 作者标识与 OpenAlex ID 的映射，结合 ORCID、论文 DOI、机构等信息核对；姓名相同不足以确认身份。
4. **区分不入选和匹配失败。** 未匹配到 OpenAlex 的官方入选作者应保留为未匹配记录，避免直接记作非入选。
5. **保留时间边界。** 若用较新榜单研究较早年份的学者流动，应称为“后来入选者的历史流动”；若要研究当时的高影响力身份，应使用相应历史年份可获得的榜单或指标，避免引入未来信息。

建议新增的项目字段：`dataset_version`、`citation_year`、`list_type`、`scopus_author_id`、`openalex_author_id`、`listed_in_official_table`、`match_status`。这些是建议字段名，不是对官方文件表头的转录。

## 8. 核查范围与参考来源

本文已核对官方数据集页面、原始方法论文和本项目两个分层脚本；未下载并逐行检查 V8 完整名单，也未执行 Scopus—OpenAlex 作者匹配。因此，具体列名、边界作者和并列名次的精确复现仍需以原始文件及对应代码核验。

1. Ioannidis, J. P. A. (2025). *August 2025 data-update for Updated science-wide author databases of standardized citation indicators*. Elsevier Data Repository, V8. [数据集 DOI](https://doi.org/10.17632/btchxktzyw.8)。
2. Ioannidis, J. P. A., Boyack, K. W., & Baas, J. (2020). *Updated science-wide author databases of standardized citation indicators*. PLOS Biology, 18(10), e3000918. [方法更新](https://doi.org/10.1371/journal.pbio.3000918)。
3. Ioannidis, J. P. A., Baas, J., Klavans, R., & Boyack, K. W. (2019). *A standardized citation metrics author database annotated for scientific field*. PLOS Biology, 17(8), e3000384. [数据库方法](https://doi.org/10.1371/journal.pbio.3000384)。
4. Ioannidis, J. P., Klavans, R., & Boyack, K. W. (2016). *Multiple Citation Indicators and Their Composite across Scientific Disciplines*. PLOS Biology, 14(7), e1002501. [综合指标方法](https://doi.org/10.1371/journal.pbio.1002501)。
