# Fig3 v4 国家份额与集中度变化

图宽180毫米、高112.59毫米，采用Helvetica和黑色坐标轴文字。提供正文阅读版及NHB_final期刊字号版，均导出PDF、可编辑SVG和600dpi PNG。

## 图表结构

左侧a为跨两行的大正方形，右侧b、c为上下排列的两个等大正方形。a约87.54毫米见方，b、c约35.31毫米见方。左右主绘图区的水平间距从55磅增至78磅，约27.52毫米；相邻纵轴标题分列显示。b、c上下间距保留48磅，约16.93毫米。三个主绘图区均为正方形，a上沿与b对齐、下沿与c对齐。

a沿用Fig5的76国及Q1—Q4分组，每组19国。各国全球跨国流量份额的1998—2025年拟合相对年增长率决定分组，切点约为每年−0.8904%、0.8768%和3.7107%。实线及年度圆点表示组内19国份额的中位数，使用左轴Median country share (%)，范围0—1.5%，间隔0.3个百分点。浅色堆积色带表示各组全球合计份额，使用右轴Group share (%)，范围0—100%。Others包含76国以外全部国家，五层每年合计为100%。四组颜色与Fig5一致，堆积透明度为18%。中位数和合计份额是不同统计量，分别读取对应纵轴。

b以Gini为唯一纵轴，c以HHI为唯一纵轴，每张图均直接比较固定203国与全部有流量国家。红线表示固定203国，蓝线表示全部国家；两图的颜色含义完全一致。横轴均为年份，b的Gini范围为0.84—0.91，c的HHI范围为0.06—0.11，两图各保留全部28年的两个范围的年度值。

固定203国选取研究期每年都有正的跨国流入或流出的国家，不设流量规模门槛。每年先合并各国跨国流入与流出，再除以这203国同年的合并流量总和。保留入选国家的完整国际流量，包括与203国之外国家之间的联系。全部国家曲线则保留当年全部有流量国家，并使用全球合并流量作为份额分母。

b、c均采用b原有的线条样式：2磅粗实线与直径4.5磅的完整实心圆点。取消半侧描边和圆点裁切，两张图使用相同的线宽、圆点、配色与绘制顺序。所有原始曲线保留实际年度数值与位置。c另加一条向上偏移2.25磅的红色描边及完整圆点，使其紧贴蓝线并可辨识；这是显示偏移，实际HHI差异由右上角小图读取。c的右上方另设差值小图，展示全部28年的固定国家HHI减去全部国家HHI；灰线和圆点表示年度差值，纵轴从0至0.0001，顶部刻度以1e-4标示。小图使用独立尺度，主曲线仍保留原始值。每图左下角图例简化为Fixed和All，指标名仍位于单一纵轴，两图与a之间的78磅间距不变。

## 数据与结果

所有指标由清洗后的flow_top100.parquet重新汇总。每次跨国事件对应来源国和目的地国各一个端点；全期11,529,374次国际事件对应23,058,748个流量端点。指标先合并流入与流出后计算，不平均两个方向各自的HHI或Gini。

固定203国提供5,684个国家—年份观测，覆盖的全球合并流量比例在1998年为99.9958%，2025年为99.9422%。其余21个非持续有记录国家只从红色固定国家曲线的计算范围排除，仍纳入a的全球分母、Others色带以及b、c的蓝色全部国家曲线。a的2,128个国家—年份份额、112个中位数以及140个组年度合计份额均保持不变。

固定203国的HHI由0.10157降至0.07010，Gini由0.89746降至0.84181；全部国家的相应值由0.10156降至0.07002、由0.90219降至0.85512。两图保留全部28年的年度变化。b、c分别在同一指标下比较固定国家与全球总体。两个范围的Gini和HHI均下降，说明去集中化也发生在持续参与跨国流动的国家之间。HHI差值由1998年的约0.00000856变为2025年的约0.00008091；差值小图用于展示两种计算口径的微小差异。HHI两条曲线的接近程度反映固定203国涵盖了接近全部的跨国流量。

## 中文图注

**图3 跨国研究者流动的国家分布变化。** a，Q1—Q4各组国家份额的年度中位数（实线与圆点，左轴）及全球合计份额（浅色堆积色带，右轴）。分组沿用Fig5的份额增长率四分位组，每组19国；Others包含其余国家，五层每年合计为100%。b、c，分别比较固定203国（Fixed，红色）与全部有流量国家（All，蓝色）的年度Gini和HHI，每张图采用单一纵轴。固定203国在研究期每年均有跨国流动记录，份额在该范围内逐年重新计算。b、c均采用实线和完整圆点；c另以向上偏移2.25磅的红色描边辅助辨识。c的小图为固定203国与全部国家HHI之差，纵轴从零开始。各国流入与流出先合并，再计算份额和指标。

## English caption

**Fig. 3 | Changes in the national distribution of international researcher mobility.** a, Annual median country shares (solid lines and circles, left axis) and total group shares of worldwide flows (pale stacked areas, right axis). Q1–Q4 retain the Fig. 5 share-growth quartiles, with 19 countries per group. Others includes all remaining countries, completing the stack to 100% each year. b,c, Annual Gini and HHI, respectively, comparing a fixed 203-country cohort (Fixed, red) with all countries with recorded flows (All, blue), using one y axis per panel. The fixed cohort comprises countries recorded in every study year, with shares renormalized within this cohort annually. For visibility, c adds a red trace displaced upward by 2.25 pt; its inset shows the exact Fixed-minus-All HHI difference on a zero-based axis. Country inflows and outflows are combined before calculating shares and indices.

## 源表与核验

- Fig3_combined_country_year_data.csv及Fig3_combined_country_metrics.csv：全球国家年度流量、份额与指标。
- Fig3_fixed_country_membership.csv、Fig3_fixed_country_year_data.csv及Fig3_fixed_country_metrics.csv：固定国家纳入规则、5,684个国家—年份观测和28年指标。
- Fig3_Fig5_quartile_membership.csv、Fig3_quartile_annual_shares.csv及Fig3_quartile_box_statistics.csv：四组成员、年度份额与中位数等汇总值，当前不绘制箱体或须线。
- Fig3_quartile_median_lines.csv、Fig3_group_total_annual_shares.csv、Fig3_group_total_country_membership.csv及Fig3_group_total_band_vertices.csv：a的曲线、分组和堆积边界。
- Fig3_fixed_country_annual_metrics_plotted.csv及Fig3_combined_annual_metrics_plotted.csv：固定203国与全部国家各56个年度指标及PDF坐标；各表Gini对应b，HHI对应c。
- Fig3_combined_lorenz_curves.csv及Fig3_fixed_country_lorenz_curves.csv：保留的辅助洛伦兹数据，当前未绘制。
- Fig3_HHI_difference_inset.csv：全部28年的HHI差值、两种口径的原值及差值小图中的PDF坐标。

QA/Fig3保存数据、PDF曲线与圆点坐标、字体、面板对齐、标题间距及碰撞检查。本次修改前的完整版本已归档。v4正文阅读版同步到最终图表文件夹及当前LaTeX项目的图片文件夹；源文件和两种字号版本均保留。
