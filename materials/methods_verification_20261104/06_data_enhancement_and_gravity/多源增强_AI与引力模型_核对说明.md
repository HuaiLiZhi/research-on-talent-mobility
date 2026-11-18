# 多源数据增强、AI与引力模型：实际记录核对

核对日期：2026年11月4日。范围为本项目、相邻 OpenAlex 项目的程序、已保存结果与10月20日地理清洗档案。本次仅整理既有材料、筛选既有结果表和核对程序，没有重新拟合、抽样或清洗，也没有修改论文。

**目前最准确的概括是：OpenAlex研究者流动记录，经外部地理参考数据统一城市身份，并在作者报告的LLM辅助下处理部分模糊城市归属；另以加入国际网络信息的起点约束引力模型，检验国内城市间目的地分配。** 目前材料不支持把这一过程扩写为“整合ORCID和官方高被引名单的Agent自主数据增强”，也不支持将模型拟合改善表述为已识别的集中化因果机制。

本目录的 [补充文件索引](<补充文件索引.csv>) 提供每份原始文件的完整路径、本地副本和本次校验值；[补充核对结果](<补充核对结果.json>) 保存了下述既有汇总结果。

## 一、实际使用的数据源

| 数据源或名称 | 与当前分析的实际关系 | 可以写入论文的作用 | 证据状态 |
|---|---|---|---|
| OpenAlex works、authors、institutions及主题分类 | 核心书目与机构记录 | 关联作者、作品、机构和地理属性；选择年度主机构；识别地点变化；赋予学科标签 | 上游提取程序及流量构建程序可查。三类实体属于同一个数据提供方 |
| GeoNames | 直接进入10月20日最终地理清洗 | 恢复地名标识，核对名称、坐标、地点类型、行政编码及父子关系，统一城市身份 | 固定下载版本2026-10-20；清单含 allCountries、hierarchy、admin1CodesASCII、admin2Codes 等文件及校验码 |
| 美国人口普查局城市地理边界 | 直接进入10月20日最终地理清洗 | 以空间包含关系核对美国地点归属，并保护应独立保留的城市 | 2024 places、1:500,000，文件 cb_2024_us_place_500k.zip；下载清单和程序均可查 |
| 带出处的城市组成关系表 | 直接进入最终地理清洗 | 处理已确认的城市组成部分，记录父城市标识、适用距离和参考出处 | city_parent_overrides.csv；含地方政府网页出处；不是一份新增研究者数据库 |
| ORCID | 上游记录携带的元数据 | 可以说明“保留OpenAlex记录中的ORCID字段” | 提取代码从 authorship 取ORCID；未找到独立ORCID数据导入、跨库职业轨迹整合或利用ORCID修正作者身份的已归档流程 |
| ROR | 机构记录携带的元数据 | 保留机构标识 | 未找到为当前主样本另行导入ROR数据库的证据；不能将字段存在等同于外部源整合 |
| 全球前2%科学家 | 项目存在自行计算的影响力分层分支 | 若讨论历史探索，须称“本项目定义的影响力层级” | 当前 top2pct 来自项目的评分和排序程序，不等同于官方Stanford/Elsevier名单；当前主分析使用 top100pct，不以该层级筛选 |
| 高被引科学家/Clarivate榜单 | 未找到进入当前主样本的记录 | 目前不列作实际整合源 | 未找到相应外部名单导入、作者匹配表或主分析配置 |
| Natural Earth、geoBoundaries、OpenStreetMap | Fig1地图素材 | 地图展示及其来源说明 | 素材目录为2026-11-03的Fig1专用地图目录；不属于10月20日最终流动清洗程序列明的增强输入 |

“多源数据增强”可以保留，但应具体限定为**书目数据与外部地理参考信息的整合**。机构属性补全主要是OpenAlex内部表之间的关联，不宜写成额外整合了多个研究者身份数据库。

主要依据：

- [上游作品—作者—机构提取程序](<../04_geographic_cleaning/original/s10_extract_works_author_mobility.py>)：ORCID随行保存；机构资料通过OpenAlex机构表关联，原始地址回退匹配也使用已有机构字典。
- [年度主机构和分层流量构建](<../04_geographic_cleaning/original/s27_build_tiered_flow.py>)：按作品数选主机构，以OpenAlex author ID串接记录；top100pct不加影响力过滤。
- [最终清洗政策](<../04_geographic_cleaning/original/cleaning_policy.json>)、[GeoNames下载清单](<../04_geographic_cleaning/original/download_manifest.json>)、[美国边界清单](<../04_geographic_cleaning/original/4c816919__manifest.json>)。
- [官方前2%与项目分层的区别](<original/STANFORD_TOP2_PERCENT_SELECTION_CRITERIA.md>)。其中建议未来建立外部作者匹配表的文字不是已实施记录。

## 二、AI/Agent究竟做了什么

**合适名称：LLM-assisted city identity resolution / LLM辅助城市身份消歧与归并。**

- 作者此前确认使用的模型为 **DeepSeek-V4.1-Flash**。这是作者提供的型号；本地档案尚不能核实访问日期、固定快照、接口、输入字段、提示词或参数。
- 作者确认的任务是判断模糊的城市身份、候选父城市和归并关系。最终可复现的归并结果保存在城市映射表中，通过稳定标识应用于各年份。
- 主机构选择由确定性规则实现：每个作者年度按关联的不同作品数选机构，并用机构ID处理并列。**未找到LLM替代该计数规则的记录。** Fig1把两步放在LLM区域里，不能据此反推主机构也是由LLM判断。
- 作者身份沿用OpenAlex author ID。未找到LLM研究者身份匹配、独立ORCID消歧或机构信息生成的归档证据。
- 最终地理清洗程序可验证名称与坐标匹配、GeoNames关系判断、边界包含、国家字段修复及稳定城市键生成。程序中未找到实际LLM调用或Agent编排；不能把这些规则步骤全部归为AI操作。
- 未发现可用于证明自主Agent执行链的任务计划、工具调用、状态流转或逐项执行日志。“LLM辅助处理”比“Agent工作流程”更贴近目前证据。写代码或组织文件时使用AI助手，也不等同于对数据记录执行了可审计的Agent流程。

检索范围记录在 [核验记录](<核验记录.json>) 与 [逐行检索命中](<上游程序与清洗程序_检索命中.csv>)。检索覆盖OpenAlex顶层Python研究程序及七个规范清洗程序；缺少本地调用记录不能排除作者在外部界面中使用过LLM。

## 三、增强数据的验证与实际改善

### 已完成、可提供程序和结果的验证

1. 原始地点键、城市目录键唯一；每个城市只有一组统一元数据。
2. 同一已确认GeoNames地点不会再因地区字段不同被拆为多个城市。
3. 七组指定城区归并案例通过测试，如浦东—上海、江宁—南京、La Jolla—San Diego；六项独立城市保护测试通过，避免把邻近独立城市合并。
4. 清洗后数据无同城流动、重复OD聚合键、非正流量或超出研究期的记录。
5. 原始事件精确分账：30,335,569 = 29,703,224确认城际事件 + 183,001归并后同城事件 + 449,344待地理核查事件。确认样本含11,529,374国际事件和18,173,850国内城际事件。
6. 逐数据集、逐影响力层级核对事件守恒，并比较年度、职业生涯及基础表的全体研究者空间流量一致性。学科标签差异另有保留，不能把不同源表无条件混用。

### 已保存的质量改善量

| 项目 | 已保存的结果 | 正确解释 |
|---|---|---|
| 原始地点记录 | 16,484条 | 去重后的原始地点组合，不是独立研究者或流动事件 |
| 可进入分析的地点记录 | 15,294条 | 通过当时规则的原始地点记录数，不是匹配准确率 |
| 国家字段更正 | 1,082条地点记录 | 映射表的字段修复量，不代表经独立金标准确认的模型正确数 |
| 统一城市标识目录 | 14,820个标识 | 目录包含待核查标识，不等同于确认样本中实际有流量的城市数 |
| 美国2025年国内流入城市数 | 2,772 → 2,693 | 来自既有清洗前后对照；同时受城市统一和待核查记录排除影响 |
| 中国对应城市数 | 427 → 348 | 同上 |
| 澳大利亚对应城市数 | 182 → 62 | 同上；不能将所有变化都解释为LLM纠错 |

这些结果支持“减少地理标识拆分、统一已确认城区、隔离冲突记录并保留可追溯分账”。**未找到独立随机人工核验样本、precision/recall/F1、LLM判断准确率或与无LLM清洗流程的对照实验。** 映射表的confidence字段属于规则标签，不是经过验证的准确率。

OpenAlex旧流程说明还记载过省/州填充率45.5%升至89.52%，但它来自较早的处理阶段，不能直接作为10月20日最终清洗或LLM增强的效果数字。

依据：[验证程序](<../04_geographic_cleaning/original/validate_city_harmonized_data_20261020.py>)、[已运行验证结果](<../04_geographic_cleaning/original/validation.json>)、[映射汇总](<../04_geographic_cleaning/original/crosswalk_summary.json>)。这些是内部规则与一致性检验，不能升级为独立地理真值验证。

## 四、引力模型要回答什么问题

**科学问题：在控制目的地科研规模、地理距离、既往国内流动和学科相似性后，城市的国际网络联系是否为国内研究者流向哪些城市提供额外信息？**

BRIDGE的覆盖与分布指标描述“哪些地方参与、各占多少”；模型进一步描述“在给定国内起点流出总量时，各目的地获得多少流量，以及哪些国际网络特征有助于解释这种分配”。模型的输出是国内城市OD期望流量，可进一步汇总为国内城市强度、Gini与HHI并与观测值比较。

模型的被解释对象属于**国内城市分析**。国际流动提供滞后网络特征；学科信息提供城市研究结构的距离变量。它不是国家去集中化模型，也不是四大学科分别拟合的机制模型。T1—T4用于分层展示，不是当前模型的解释变量。

当前Results只有国际、国内、学科三节，未报告这组模型结果。若保留这一结构，模型应明确定位为国内城市部分的补充分析，并给出对应结果或补充材料引用。不能仅在引言和Methods宣布模型已回答问题，而全文没有对应结果。此次未改动该结构。

## 五、引力模型的具体实现

### 类型与单位

模型可称为 **an origin-constrained gravity model with lagged international-network features**，即加入滞后国际网络特征的起点约束引力模型。计算采用目的地条件选择概率；在起点总量固定时，以加权条件多项似然拟合，其与相应条件Poisson表述等价。它不是简单的对数流量OLS，也不是未经约束的总流量预测。

对象是76国内的城市—城市—四年期聚合OD计数。共有七个四年期；特征使用前一期信息，2002—2013年拟合，2014—2017年比较模型，2018—2025年作后期评价。每国最多选择50个起点，选择依据限于1998—2013年的累计流出；候选目的地需有前期科研存量和有效坐标。保留候选零流量城市对，排除同城配对。设计包含3,069,435个候选OD—时期单元；后期覆盖6,984,347次国内事件，占相应76国事件的79.3%。

### 输入变量

| 变量组 | 变量及来源 |
|---|---|
| 基准科研规模 | 前期目的地年度主机构作者记录的平均量；来自既有聚合科研存量，不是城市总人口 |
| 基准空间阻力 | 城市坐标的大圆距离，最低1 km |
| 国内历史 | 前期目的地国内流入、前期相同国内OD流量 |
| 学科结构 | 26学科城市活动向量的余弦距离；另保留空学科/伙伴画像指示变量。学科计数可能重叠，不能将向量总和称为唯一研究者数 |
| 国际门户规模（2项） | 前期目的地国际流入、国际流出 |
| 国际伙伴范围（2项） | 前期不同外国来源城市数、外国目的城市数 |
| 国际网络地位（2项） | 加权有向国际网络及其反向网络的PageRank |
| 国际伙伴结构相似性（2项） | 国内起终点的外国来源城市画像、外国目的城市画像相似性，分别TF–IDF加权后算余弦 |
| 外国中介两步联系（1项） | 国际网络中从国内起点经外国城市到国内终点的加权连接 |

另有“国际伙伴国家画像距离”比较模型；它与上述全部九项国际特征的综合规格是不同模型，不能混用。

基本分配关系为：

\[
\eta_{ij,t}=\boldsymbol\beta^\mathsf T\widetilde{\mathbf x}_{ij,t-1}
 +\boldsymbol\gamma^\mathsf T\widetilde{\mathbf z}_{ij,t-1},\qquad
\mu_{ij,t}=O_{i,t}\frac{\exp(\eta_{ij,t})}{\sum_{\ell\in\mathcal J_{i,t}}\exp(\eta_{i\ell,t})}.
\]

其中 \(\mathbf x\) 是基准变量，\(\mathbf z\) 是国际变量，波浪线表示使用训练数据均值和标准差进行变换，\(O\) 是提供给模型的观测起点流出总量。两步特征具体为：

\[
B_{ij,t-1}=\sum_{k:\,c_k\ne c_i}I_{ik,t-1}
\frac{I_{kj,t-1}}{\sum_\ell I_{k\ell,t-1}},\qquad c_i=c_j.
\]

它是城市网络联系，不是同一研究者连续走完两次国际移动的计数。所有国际变量均取自前一期。当前规格未加入外部GDP、人口、收入、语言或政策数据。

各国总训练权重相同，使用无惩罚L-BFGS-B拟合。评价保持基准与扩展模型的候选城市对、起点总量和时间样本相同，比较Poisson偏差、CPC及原始流量尺度R²。逐年重建使用已保存系数和四年期特征，每年给入实际起点总量，保留未建模流量；然后比较共同城市集合上的Gini与HHI。该步骤不是独立预测未来年度流量。

依据：[模型设计与拟合](<../03_models/original/validate_logical_distance_20261030.py>)、[九项国际特征与模型比较](<../03_models/original/validate_international_signals_20261030.py>)、[年度重建规格](<../03_models/original/f9ab5965__analysis_plan.json>)。

## 六、主要结果，以及它能增加哪些认识

### 后期评价：2018—2025年，76国

下表直接摘自已保存结果。偏差改善、CPC增益和R²增益的区间/中位数以国家配对差为单位；绝对指标是各国指标的中位数，两种汇总不能相互替代。

| 模型或指标 | 既有结果 |
|---|---|
| 综合国际网络模型，相对基准的国家中位偏差下降 | **4.4977%**；国家bootstrap 95%区间 **2.4819%—7.0016%**；58/76国改善；Holm校正符号检验P=0.00002828 |
| 基准 → 综合模型，CPC国家中位数 | **0.83909 → 0.84443** |
| CPC国家配对增益中位数 | 0.004872；95%区间0.002115—0.010153 |
| 基准 → 综合模型，原始流量尺度R²国家中位数 | **0.92816 → 0.94402** |
| R²国家配对增益中位数 | 0.011380 |
| 仅加两步特征的中位偏差下降 | **3.4807%**；95%区间1.7169%—5.9809% |
| 仅加伙伴国家画像距离的中位偏差下降 | **0.2667%**；95%区间0.0943%—0.4655% |

在2014—2017年验证期，两步模型的中位偏差下降2.8279%，综合模型为2.8249%；归档的选择文件选择了两步模型。后来年度图按作者要求使用综合模型，两者均有结果，**不能说综合模型是按验证期中位偏差选出的最优模型**。2018—2025年数据在先前探索中已经被查看，应称后期时间评价，不能称全新独立确认集。

### 国内分布的年度重建：同一608个国家—年度

| 评价指标 | 基准模型 | 综合国际网络模型 |
|---|---:|---:|
| Gini MAE（百分点） | 1.427899 | 1.267973 |
| Gini RMSE（百分点） | 2.018797 | 1.837705 |
| HHI MAE | 0.010218 | 0.009030 |
| HHI RMSE | 0.014620 | 0.013501 |

这支持“国际网络特征在已有空间、规模、学科及国内历史变量之外，提供了有助于国内目的地分配及分布重建的额外信息”。国家层面的描述显示各国流量份额重组；这里进一步显示国际联系的城市结构与国内目的地分配有关。它并未证明国家份额变化导致国内集中化，也没有对四大学科分别识别这一关系。

### 应保留的两项诊断

1. **两步通路特异性未得到支持。** 保持城市—伙伴国边际量的100次外国城市重配中，实际两步特征增益中位数3.4807%，重配为4.4320%；仅19/76国实际增益高于该国重配中位数。它是固定系数的特征扰动，不是重新拟合的零模型，但现有结果不支持“特定外国中介城市对应关系本身得到独立验证”。
2. **未支持国际联系普遍提高国内Gini。** 两步模型相对基准的有限事件模拟，Gini差异中位数为−0.0922个百分点，95%区间−0.3369至0.1421；HHI差异中位数−0.001512，区间−0.004002至−0.000803。这是两步扩展的条件模拟，不是综合模型的因果效应，更不能据此声称它解释了全球国内城市集中化的形成。

因此，引言适合概括“国际网络信息改善国内流量分配的刻画”，不适合写“揭示国际去集中化驱动国内集中化的机制”。

依据：[模型比较原表](<../03_models/original/comparison_summary.csv>)、[绝对指标](<../03_models/original/absolute_metrics.csv>)、[年度误差原表](<../03_models/original/Fig6_evaluation_errors.csv>)、[两步随机化结果](<../03_models/original/network_randomization_summary.json>)、[两步模拟结果](<../03_models/original/distribution_simulation_summary.json>)。

## 七、逐占位符的可用信息

下面是可据现有证据采用的英文短语。它们是填补事实的候选文本，本次没有写入正文。AI那一项保留作者确认与归档证据的区别；模型发现只有在正文或补充材料实际报告相应结果后，才适合在引言提前概括。

| 占位符 | 建议内容 |
|---|---|
| `[SUPPLEMENTARY_DATA_SOURCES]` | GeoNames geographic identifiers and administrative hierarchies, US Census Bureau place boundaries, and documented city-component mappings |
| `[AI_AGENT_WORKFLOW]` | LLM assistance for ambiguous city-identity and parent-city assignment judgments。模型按作者确认为DeepSeek-V4.1-Flash；现有材料不支持改写为自主Agent流程 |
| `[DATA_ENHANCEMENT_TASKS]` | harmonize city identities, reconcile name and regional variants, assign confirmed city components to their parent cities, and isolate unresolved geographic records。这些是总体清洗任务，不应全部归因于LLM |
| `[VALIDATION_PROCEDURE]` | geographic-identifier consistency checks, targeted tests of city merging and independent-city preservation, duplicate-key checks, and exact event accounting。没有独立人工准确率，不能补写validated matching accuracy |
| `[ANALYSIS_COMPONENT]` | a complementary analysis of domestic intercity flow allocation。国际信息是解释变量，学科画像是控制变量 |
| `[GRAVITY_MODEL_OBJECTIVE]` | test whether lagged international-network information improves the allocation of domestic flows across destination cities beyond geographic distance, research stock, domestic flow history and disciplinary similarity |
| `[GRAVITY_MODEL_IMPLEMENTATION]` | an origin-constrained gravity model fitted to aggregate city-to-city flows, with lagged domestic, disciplinary and international-network predictors and comparisons against observed route counts and city-level distributions |
| `[GRAVITY_MODEL_MAIN_FINDING]` | Lagged international-network features improved the reconstruction of domestic flow allocation and city-level distributions beyond the reference model. 不追加因果、特定通路得到证实或导致集中化的表述 |

其中第五段的研究事件总数可采用 **29,703,224**，或约 **29.7 million**，对应同一确认城际样本。

## 八、仍需补齐的事实记录

- LLM访问日期/快照、接口、实际输入字段、提示词、输出样例、决策数量和最终确认过程；目前不应倒填未记录的流程。
- 若声称使用独立ORCID、官方前2%或高被引科学家名单，需要对应的源文件、版本、作者匹配表和进入主样本的运行记录。当前未检得。
- 若要报告AI增强准确率，需要独立核验结果；目前可报告的是已完成的一致性检查、特定案例检查、字段修复和事件分账。
- 引力模型在当前三节Results中的位置与结果引用需要与引言承诺一致。此项属于写作安排，本次仅说明，未改正文或设计新分析。
