# 当前 Fig2 绘图数据

全部数值使用 data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet 重新计算，采用年度全体研究者口径，仅包含确认的跨国和国内城际事件。城市按清洗后的稳定 ID 去重，不再拼接地区名称生成城市。

- Fig2_source_data.csv：全部国家的年度总流动量、地点数和联系数。
- Fig2_country_year_data.csv：固定 76 国、两个方向、28 年的数量及流量。
- Fig2_all_country_stacks.csv：a、b 的五国与 Others 六层流量。
- Fig2_*source_partner_curves.csv：a、b 嵌套小图的四年份累积比例。
- Fig2_*bubbles.csv：c、d 的实际数量、平方根半径和圆心。
- Fig2_country_trajectories.csv：e–i 的国家、城市年度去重总数两条实线，以及保留为辅助数据的四项分方向数量。
- Fig2_combined_location_counts.csv：第三行两条实线的精确值；国家按来源国和目的国的并集、城市按国内来源与目的地稳定城市 ID 的并集计数。
- Fig2_bubble_size_legend.csv：c、d 右上角竖直标尺的数量刻度、物理位置与对应气泡直径。
- Fig2_bubble_country_labels.csv、Fig2_bubble_connectors.csv：国家标注与引线对应关系。
- Fig2_fixed_sample_exclusions.csv：清洗后不再满足全年连续国内流动记录要求的原样本成员。

原始 78 国样本按相同连续观测条件重新筛选为 76 国。a、b 的完整流动总量及 a 的嵌套小图不受此固定样本限制。清洗前或旧画法的中间表保存在 ../QA/previous_inputs_not_used 中，不参与当前计算。输入哈希及核对结果见 ../QA/cleaned_data_provenance.json 与 ../QA/cleaned_figure_checks.json。

## Fig5

当前一行三图：a为国内城市HHI，b为国内城市Gini，两图横轴均为跨国流入加流出的年均事件数；c为同一国家各年度国际伙伴HHI与国内城市HHI的六边形密度图及两侧直方图。国内流量先在同一稳定城市ID合并流入与流出，再逐年计算两项指标，最后对28年等权平均。当前2128项国家年度记录和76组均值分别见Fig5_combined_country_year_metrics.csv、Fig5_combined_country_mean_levels.csv。

Fig5_combined_fits.csv、Fig5_combined_fit_curves.csv和Fig5_combined_fit_bootstrap.csv保存两组拟合、482个曲线位置及10000组国家自助样本参数。HHI采用log–log拟合；Gini采用logit变换拟合后返回原尺度，曲线及置信带保持在0—1内。Fig5_scatter_plotted_values.csv为152个主图点，Fig5_country_labels.csv为40个国家标注，Fig5_combined_fit_plotted_values.csv为当前拟合曲线的精确绘图坐标。所有点为深灰色、70%不透明度，无描边；a为蓝色拟合，b为红色拟合。

Fig5_international_partner_margins.csv为202817条按双向外国伙伴汇总的流量。Fig5_partner_city_concentration_observations.csv为c的2128项配对集中度；国际伙伴HHI按一国内部的伙伴份额计算，不能视为全球国家间HHI。Fig5_partner_city_concentration_hexagons.csv为218个非空六边形、计数及数据/PDF顶点，Fig5_partner_city_concentration_marginal_histograms.csv为两组共56个直方图区间。所有观测均逐一核对几何归属，未抽样。密度采用青色，边缘分布为灰色，合并年度记录的Spearman为−0.0469。原Fig5_annual_volume_*是旧规模图来源，当前不再使用。

原Fig5_country_year_data.csv、Fig5_country_trends.csv、Fig5_HHI_*、Fig5_level_*、Fig5_zoom_*和旧固定效应统计表为辅助或历史来源，当前图中不使用。原两面板成图及来源存于../QA/Fig5/previous_two_combined_panels，原四面板成图和来源存于../QA/Fig5/previous_contribution_four_panels。当前完整口径、审核和独立复算见../Fig5_设计说明与图注.md与../QA/Fig5。

## Fig3

Fig3_country_year_data.csv、Fig3_country_metrics.csv、Fig3_density_curves.csv、Fig3_HHI_insets.csv、Fig3_lorenz_curves.csv 和 Fig3_distribution_insets.csv 为完整上二下四布局提供数据。c、d 左侧为带局部放大图的洛伦兹曲线，右侧为年度 Gini 主图和归一化等价国家数嵌图。a、b 左上角放大密度曲线峰部。Fig3_zoom_windows.csv 记录四个取景范围；Fig3_zoom_curves.csv 提供直接裁剪自主图路径的放大曲线。全部使用相同清洗后的跨国事件，在每年相应方向的全部有流量国家中计算。归一化等价数量用当年实际有流量国家数归一化。Fig3_top_country_shares.csv 保留为辅助数据，当前图中不展示。详情见 ../Fig3_设计说明与图注.md 和 ../QA/Fig3。

## Fig4

Fig4_all_country_combined_metrics.csv 保留固定 76 国合并国内流入和流出后的全部 2,128 个国家年度指标，包括 N、HHI、Gini 和归一化等价城市数。Fig4_country_concentration_trends.csv 为左侧大散点图的 76 国全部数据，记录基于 28 年观测拟合的归一化等价城市数和 Gini 年变化、分类与 PDF 点位置；63 国同时呈现前者下降与后者上升，2 国相反，11 国为混合变化。Fig4_country_selection.csv 记录全部国家趋势及保留的四个案例。Fig4_scatter_country_labels.csv 记录 a 中22个国家标注的实际点坐标、文字位置、选择依据、主图/放大图显示位置及是否使用引线；其中12个密集区域标注只在放大图显示，主图不重复标注。Fig4_zoom_points.csv记录矩形范围内全部26个国家的原始数值、类别和PDF坐标。保留累计国内事件量前15国，并按第二象限横轴小区间补充代表性国家；第一和第四象限均标注全部国家。分别在主图和放大图中核验所有文字的完整边界，均留在对应数据点所属象限，第二象限文字不越过零轴。Fig4_domestic_city_margins.csv 为美国、德国、加拿大、西班牙按稳定城市 ID 合并的国内流入加流出量；Fig4_domestic_country_metrics.csv 为四国的 112 个国家年度记录；Fig4_plotted_values.csv 为右侧 8 条曲线的 224 个精确值。所有指标在合并流量后重新计算，不平均两个方向的指标。右侧各国采用独立数轴，轴线、刻度及轴标题为黑色，b—e 共用 HHI/Gini 图例。详情见 ../Fig4_设计说明与图注.md 与 ../QA/Fig4。


## Fig6

当前图使用a竖向堆积柱、b逐学科两列横向堆积条、c国家Gini趋势箱线散点的布局。Fig6_period_trend_classification.csv保存26学科×2尺度×4时期的208项分类，Fig6_period_discipline_composition.csv保存8个100%学科构成的24个类别比例，Fig6_period_flow_volumes.csv保存8个时期年均事件量。Fig6_country_trend_classification.csv为884个固定国家学科组合的全期分类，Fig6_domestic_trend_composition.csv保存26学科×2种权重×3类别的156个比例。国家数量占比与事件流量占比均按相同固定学科国家样本计算。分类使用Gini上升且归一化等价数量下降、相反组合、混合变化三类。

Fig6_country_annual_metrics.csv为728个国家尺度学科年度指标，Fig6_domestic_country_year_metrics.csv为24,752个国内国家学科年度指标。城市流入与流出先合并再计算指标。Fig6_domestic_country_samples.csv列出各学科固定14—68国的名单及覆盖率。c的26个箱线图、884个国家点及其原始数据保持原样。

当前a、b最终几何记录于Fig6_period_stack_plotted_values.csv、Fig6_period_volume_plotted_values.csv和Fig6_ratio_stack_plotted_values.csv。c点、箱体和名称分别记录于Fig6_country_trend_plotted_values.csv、Fig6_box_plotted_values.csv及Fig6_discipline_labels.csv。旧增长率、色块指数及其绘图数据保留为辅助表，不用于当前a、b。详情见../Fig6_设计说明与图注.md与../QA/Fig6。


Fig6版式更新：横向183×105.83毫米，a上下图间距1.5pt，b两列各33pt、间隔1pt，b与c间隔4pt。c恢复纵轴线、26个刻度及向左偏移的共享学科名称；来源表保留各学科样本数量，图中不再设n列。全部数值及分类保持原定义，绘图坐标按新布局更新。
