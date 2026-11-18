# Fig6 四大学科类别中的集中化变化

本版采用分布概览、完整年度过程和分组散点关联的阅读顺序。图宽180 mm、高140 mm，沿用蓝、绿、红、黄四种颜色；Helvetica字体，除面板字母外不加粗。本图保存在v4，并同步至当前论文；旧版已备份。

a与d的左侧纵轴位于同一条竖线上；其余面板恢复并保留原来的上三图、下四图布局。

b、c绘图区宽度由88 pt增至108 pt，约加宽23%；a、d的纵轴对齐及整图180 × 140 mm尺寸保持不变。

## 图表内容

a展示四类国内城市Gini年度趋势的蜂群散点，每类45个国家。圆点面积调整为7平方磅，透明度为0.90，使圆点稍大且更清晰。横坐标保留各国的实际趋势值，纵向排布用于分开重叠点。彩色短竖线为国内国家趋势的中位数，菱形为该类跨国流动在国家之间的Gini年度趋势。灰色虚线表示零变化。

b展示各类国家间Gini相对1998年的变化。c展示各国国内城市Gini相对本国1998年的变化，曲线为国家中位数，阴影为国家之间的四分位区间。b、c年度曲线统一加粗至2磅。b与c分开绘制，分别具有自己的纵轴，以清楚区分国家间分布和各国内部城市分布。

d至g分别为理工科学、生命科学、健康科学和人文社会科学。横轴为有国内流动记录城市数的拟合年增长率，纵轴为国内城市Gini的年度趋势。每个点表示一个国家，全部45国均显示。黑线为普通最小二乘拟合，统一延伸至完整横轴范围−1至18.5；延伸段使用原有拟合系数。阴影为2,000次国家层面bootstrap得到的逐点95%置信区间，保留在各类实际观测范围内。各图使用相同横纵轴范围，便于比较。散点面积由9增加至18平方磅，透明度由0.65调整为0.90，四类仍使用原有配色。Spearman相关系数依次为0.64、0.67、0.79和0.77，放在各小图标题下方、绘图区外，避免网格被文字截断成短线。

## 数据口径

26个学科先按OpenAlex的四大类归并流量，再计算各类国家和城市指标。国内城市流入、流出强度先相加。四类共用相同的45个国家；每个国家、每个类别在1998—2025年均有至少两座城市记录国内流动。国家尺度使用各类当年所有有流量国家。

所有趋势使用28年年度序列。Gini趋势以百分点每年表示。城市记录数量增长率由城市数量对数对年份拟合，并转换为百分比年率。城市覆盖和Gini的关联描述记录中的共同变化。相邻点和bootstrap重采样均来自实际国家数据，没有生成替代观测或删减散点。

四类国家间Gini年度趋势均为负。国内城市Gini年度趋势为正的国家数依次为41、41、37和45，分母均为45。c中的阴影为国家间四分位区间，d至g中的阴影为拟合关系的置信区间，两者含义不同。

## 中文图注

**图6 四大学科类别中的国家去集中化与国内城市集中化。** a，各国国内城市Gini的年度趋势，以及各类国家间Gini的年度趋势。圆点表示国家，竖线为国内趋势中位数，菱形表示国家尺度趋势。b、c，国家间Gini的变化，以及国内城市Gini变化的国家中位数和四分位区间，均以1998年为基期；国内变化按各国自己的基期值计算。d–g，四类中城市记录数量增长率与国内城市Gini趋势的关联。每点表示一个国家；黑线为采用相同横轴范围的线性拟合，阴影为实际观测范围内由2,000次国家层面bootstrap得到的逐点95%置信区间。四类共用45国样本，覆盖1998—2025年，流入与流出合并统计。pp表示百分点。

## English legend

**Fig. 6 | National deconcentration and domestic urban concentration across four disciplinary domains.** **a,** Domestic urban Gini trends across countries (dots), their medians (vertical marks), and international country-level Gini trends (diamonds). **b,c,** Changes in international Gini (b) and median changes in domestic urban Gini (c), relative to 1998. Domestic changes use each country’s own 1998 baseline; shading in c indicates the interquartile range across countries. **d–g,** Fitted annual growth in the number of cities with recorded domestic flows versus annual domestic Gini trends in physical, life, health and social sciences, respectively. Each point represents one country. Lines show ordinary least-squares fits evaluated over a common x-axis range; shading indicates pointwise 95% confidence intervals within each domain’s observed growth range, from 2,000 country-level bootstrap resamples. All domains use the same 45-country domestic sample over 1998–2025. Inflows and outflows are combined. pp, percentage points.

## 导出与检查

PDF、SVG和600 dpi PNG位于本目录；NHB_final中为相同布局的较小字号版本。PDF与SVG保留可编辑文字。source_data保存年度指标、实际散点位置、拟合曲线及统计汇总。QA中保存独立原始数据核验、七个面板的对齐检查、字体大小与文字碰撞检查。


## 简化后的坐标名称

a的横轴和d—g的纵轴保留Gini trend (pp/year)，b、c共享纵轴简化为Gini change (pp)，1998年基期及国内逐国计算方式放在图注。d—g共享横轴采用City count growth (%/year)，在图注中明确表示有国内流动记录城市数的拟合年增长率。Year和学科名称保持原写法。pp表示百分点；原始基期、单位、数据和布局未改变。
