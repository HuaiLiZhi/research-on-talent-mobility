# Fig5 跨国流动与国内城市集中程度的联系

统一排版：宽180毫米；当前目录为正文阅读版，坐标标题9pt、刻度和图例8pt；NHB_final为期刊成稿版，常规文字6–7pt。插图宽度设为18厘米。详见图表尺寸与插入说明.md。

图表采用两行结构。第一行a、b展示国家平均水平的关联，c展示各国国际流量份额变化率的分布，并连接到第二行四个分组分布图。当前版本仍保存在v3中。

## 图注

**图5 跨国流动与国内城市集中程度的联系。** a、b，各国年均跨国流动量与国内城市HHI、Gini年度均值的关系；各年等权，两个横轴和a的纵轴采用对数刻度。实线和阴影表示拟合关系及95%置信带。c，各国全球跨国流量份额的拟合相对年增长率，按四分位数分组。d–g，各组国内城市Gini趋势的核密度分布，单位为百分点/十年；散点表示国家，黄色虚线为中位数，灰线为零变化。使用76国1998—2025年记录，每组19国，流入与流出合并。pp表示百分点。

**Fig. 5 | International mobility and domestic urban concentration.** a,b, Mean annual international mobility versus mean domestic urban HHI and Gini, with equal weight to years. Both horizontal axes and the HHI axis are logarithmic. Lines and shading indicate fits and 95% confidence bands. c, Fitted annual percentage growth in countries’ shares of global international mobility, divided into quartiles. d–g, Kernel densities of domestic urban Gini trends, in percentage points per decade; dots represent countries, yellow dashed lines mark medians and grey lines indicate zero change. All comparisons use 1998–2025 records for 76 countries, with 19 countries per group. Inflows and outflows are combined. pp, percentage points.

## 数据与分组

沿用76国连续观测样本，使用全部28年记录。国内城市流入和流出先按稳定城市ID合并，再计算年度HHI和Gini；没有平均流入与流出的指标。

a、b使用各国28个年度值的算术平均。HHI在对数空间拟合，Gini经logit变换拟合后返回原始尺度；95%置信带来自5000次国家成对自助抽样。两图均展示描述性Spearman相关。

c先将每国每年的跨国流入与流出相加，再除以同年全部国家的双向跨国流量总和。分母包括全部国家，并非只有76国。对各国年度份额取对数后拟合年份，将斜率换算为相对年变化率。国际份额升降与该国流动事件量的升降不同，也不命名为某个国家的去集中化。

四分位切点约为每年−0.89%、0.88%和3.71%，每组19国。下方四图展示各国年度国内城市Gini对年份的拟合斜率，单位为每十年的Gini百分点变化。四图坐标范围相同，使用相同绝对带宽的高斯核密度估计；并未假定国家变化率服从正态分布。底部散点的横坐标为实际变化率，纵向轻微错开仅用于辨认。

四组的国内Gini变化率中位数依次为每十年0.66、2.44、4.16和5.70个百分点。Gini上升的国家分别为15、17、14和19个，其余国家同样完整保留。这些分组比较呈现国际份额变化与国内分布变化的联系，不用于认定因果影响。

## 样式与输出

保留a、b的数据与拟合，按180毫米宽度重排绘图区和国家标注；新增c及其连接的d–g。c的阶梯直方图使用真实国家计数；四分位色带、连接线和下方分布一一对应。沿用蓝、灰、绿、红及黄色，散点为70%不透明度的深灰色，无外边框。

b的国家名优先靠近散点直接标注，较远的标注使用短引线，最大标注偏移为30pt。正文阅读版保留10个国家名，引线由9条减为5条；期刊成稿版保留15个国家名，引线由13条减为5条。

图宽180毫米、高149.93毫米，Helvetica字体和黑色坐标轴；两套字号见统一排版说明。输出PDF、可编辑SVG和600dpi PNG。原三图结构保存在QA历史目录。

当前分组来源表为Fig5_stratified_annual_observations.csv、Fig5_stratified_country_trends.csv和Fig5_stratified_groups.csv；精确绘图值为Fig5_stratified_histogram.csv、Fig5_stratified_density_curves.csv及Fig5_stratified_country_strip.csv。此前国际伙伴HHI相关表为历史辅助数据，不再用于当前图。

方形主图更新：d—g四张分布图的绘图区均为105×105pt，宽高比为1；水平间距约11.75pt。第一行、全部数值、核密度带宽及分组不变。

d—g标题已删除(n = 19)，仅保留Q1—Q4及其国际份额变化率区间。每组19国的样本数继续在图注中说明。分组、曲线和国家散点均不变。

共享横轴名称在d—g四图下方正中，紧接横轴刻度，与刻度仅留2.5pt；Median和No change图例横排在右边，与横轴名称同一行。


## 简化后的坐标名称

a、b横轴采用International mobility (events/year)，纵轴分别为Domestic HHI和Domestic Gini。c横轴采用Share growth (%/year)，表示该国在全球跨国流量中的份额的相对年增长率。d—g共享横轴为Domestic Gini trend (pp/decade)，纵轴简化为Density。均值口径、城市层级、对数坐标及pp的含义在图注中说明，单位和指标数值保留。
