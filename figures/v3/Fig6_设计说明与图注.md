# Fig6 学科趋势与国内城市集中化

统一排版：宽180毫米；当前目录为正文阅读版，坐标标题9pt、刻度和图例8pt；NHB_final为期刊成稿版，常规文字6–7pt。插图宽度设为18厘米。详见图表尺寸与插入说明.md。

## 简短中文图注

**图6 国家间与国内城市流动的学科差异。** a，上方为四个七年时期的年均流动事件数，下方为26个学科在国家尺度和国内城市尺度上呈现各类趋势的比例。b，每个学科在国家尺度和国内城市尺度上的时期分类构成，各列以四个七年时期为分母，每期占25%。红色表示归一化等价地点数下降且Gini上升，蓝色表示相反组合，灰色表示混合变化。a与b均按各期7个年度观测分类。c，各学科国内城市Gini年变化的国家分布，箱体为四分位范围，中心线为中位数，须延伸至1.5倍四分位距内最远观测；散点表示国家，各学科固定样本为14—68国。城市流入与流出先合并再计算指标。黄色标记三个代表性学科。

## English caption

**Fig. 6 | Disciplinary differences in international and domestic urban mobility.** a, Mean annual event volumes (top) and proportions of 26 disciplines classified by concentration trends at country and domestic city scales (bottom), across four seven-year periods. b, Period-classification compositions within each discipline at country and domestic city scales; each of the four seven-year periods contributes 25%. Red denotes declining normalized equivalent location counts and increasing Gini; blue denotes the reverse combination; grey denotes mixed changes. Classifications in a and b use seven annual observations per period. c, Country distributions of domestic urban Gini trends. Boxes show interquartile ranges, lines show medians, whiskers reach the most extreme observations within 1.5 interquartile ranges, and points represent countries. Field-specific cohorts contain 14–68 countries. Indices combine inflows and outflows before calculation. Yellow marks three illustrative disciplines.

## 图形结构

a采用上下两个对齐的竖柱图。上方为跨国与国内两组、每组四期的年均事件量；下方为相同两组、相同四期的100%堆积柱。下方每根柱的分母均为26个具名学科，学科等权。每层是学科数量占比。

b每个学科对应两列100%堆积条，左列Country表示国家尺度，右列Domestic表示国内城市尺度。分别汇总该学科在1998—2004年、2005—2011年、2012—2018年和2019—2025年的四次分类，每期等权。各类时期数除以4得到条段比例，三个类别之和为100%。a按时期比较不同学科，b按学科比较四个时期。

c保留此前的26个横向箱线图和884个国家学科散点，横轴为国内城市Gini年变化，单位为百分点每年。散点的数值、纵向抖动及箱线统计均与修改前一致，绘图位置按新的横向版式缩放。26个学科名称只出现一次，按c中国家趋势中位数从高到低排列，全部学科名改为单行，与b的两列比例条共用行中心。学科名绑定到c的纵轴，统一向左偏移以容纳b；c的黑色纵轴线和26个刻度明确显示。

主色为红色#CC7C71、蓝色#7E99F4与灰色#A5AEB7。红色对应归一化等价数量下降且Gini上升的相对集中化，蓝色对应相反组合的去集中化，其余组合为灰色混合变化。黄色#C9A45C标记Energy、Computer Science和Physics and Astronomy。c的国家点为#4A4A4A、不透明度37%、无描边。

## 数据与计算

采用当前清洗后的年度全体研究者事件表，以稳定城市ID统计26个具名学科。国家尺度先合并该国跨国流入与流出，再计算国家间指标；国内尺度先合并同一城市的国内流入与流出，再在其所属国家和学科内计算指标。每次事件在流动规模中计一次，计算份额的合并流量总和为事件数的两倍。

a上方使用26个具名学科、全部国家的跨国与国内年度事件量，分别汇总四个七年期，再除以7。a下方分别对各学科的国家年度指标和国内年度指标，在每个七年期内拟合Gini与归一化等价数量的线性趋势，依两者符号联合分类。国内年度指标为固定国家样本的国家指标中位数。各期分类基于7年完整序列，分母始终为26个学科。

b与a使用相同的分期分类：对每个学科每个七年期的Gini和归一化等价地点数分别作线性拟合，按两个斜率的符号联合分类。左列使用全部国家间的跨国流动分布，右列使用逐国计算国内城市指标后得到的固定国家样本年度中位数。每类的条段比例为该类别出现的时期数除以4。数值零容差为1e-10百分点每年。

国内候选范围沿用Fig2—5的固定76国；每个学科保留全28年均有国内城际流动、每年至少两座有合并流量城市的国家。各学科14—68国，合计884个国家学科组合，覆盖对应学科全期国内事件的78.28%—99.57%。名单及覆盖率列于Fig6_domestic_country_samples.csv。a、b的国内年度指标与c使用相同的学科固定国家样本。

c的箱体和散点描述国家之间的趋势差异。箱线图须之外的国家点完整显示，纵向抖动仅区分重合点，横坐标保持实际数值。

## 文件与复核

当前成图为Fig6.pdf、Fig6.svg及600dpi Fig6.png，宽180毫米、高127毫米，Helvetica字体、黑色文字。

当前a、b的数据为Fig6_period_trend_classification.csv、Fig6_period_discipline_composition.csv、Fig6_period_flow_volumes.csv及Fig6_scale_period_composition.csv。对应的完整PDF几何见Fig6_period_stack_plotted_values.csv、Fig6_period_volume_plotted_values.csv和Fig6_scale_period_stack_plotted_values.csv。所有数据位于source_data。

旧画法的增长率和时期指数表保留为辅助数据，当前a、b使用分期分类与时期比例绘图。旧版按国家数和流量加权的Fig6_domestic_trend_composition.csv及Fig6_ratio_stack_plotted_values.csv保留为历史辅助数据。c及其国家指标表保持原样。原始数据核对、全期与分期斜率、100%加总、国家数及事件权重、PDF位置、字体和碰撞结果见QA/Fig6。此前图形保存在该QA文件夹的历史记录中，未新增版本文件夹。


## 参考图几何与纵轴

采用180×127毫米的横向比例，为26个学科名称保留独立文字列。a宽75pt，下方堆积图高217.5pt，上方规模图高70.7pt，二者间距1.8pt。

b两列各宽26pt，列间距1pt；b与c间距4pt。b、c共享290pt绘图区高度，26行中心间距约11.15pt；c宽约161.24pt，所有观测点及分类比例保留。

c恢复黑色左侧纵轴线和26个短刻度。全部学科名称作为c的真实纵轴刻度名，向左留出两列b的位置，图中只显示一套名称。国家样本数移至图注及来源表，图中取消单独的n列。共享图例放在学科名称列下方。
