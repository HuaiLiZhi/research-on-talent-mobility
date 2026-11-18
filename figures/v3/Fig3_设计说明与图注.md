# Fig3 国家层面跨国流动的分布变化

统一排版：图宽180毫米、高约125.85毫米，Helvetica字体，全部文字为黑色。当前目录为正文阅读版，坐标标题9pt、刻度与图例8pt；NHB_final为期刊字号版，常规文字6—7pt。输出PDF、可编辑SVG与600dpi PNG。

## 当前布局

a、b分别展示1998、2007、2016和2025年的国家流入、流出份额密度。右上保留峰部放大图，四条同色竖虚线标示各年的实际国家份额中位数。原右上年度HHI小图已删除。

c、d各含两张正方形主图。左图是四个年份的洛伦兹曲线，保留其局部放大图；右图是1998—2025年的年度HHI与Gini双纵轴图。c对应流入，d对应流出。前列国家累计份额小图已删除。

年度图中，蓝色实线为HHI，对应左轴；红色实线为Gini，对应右轴。两项指标均保留全部28年观测，小圆点沿用各指标颜色。流入、流出图使用相同的HHI范围0.06—0.11及Gini范围0.84—0.94，横轴均为1998—2025年。两项指标使用独立的纵轴刻度。坐标轴、刻度及指标名称均为黑色，每个年度图右上方标出HHI和Gini线条图例。

第二行四个主图均为约78.22×78.22pt的正方形，同组左右绘图区间距40pt，为双纵轴数字及名称留出空间。第一行物理尺寸保留，两行绘图区间距约39.66pt。c、d年度图的右侧轴线分别与a、b的右侧边缘严格对齐。全图共有六张主图、四张局部放大图及两条次纵轴。

密度峰部放大范围保留为log10份额−2.15至−1.15、密度0.32至0.41；a、b右上放大图扩大为约90.79×66.31pt，面积约为之前的两倍。主图横轴显示范围缩短为log10份额−4.25至2，保留全部实际国家份额，删除底部逐国短标记。洛伦兹放大图聚焦于累计国家比例75%—93%、累计流量比例3%—32%，放大图约32.53×52.41pt，并使用无弯曲的直线连接主图框选区域。四张放大图与主图框选区域使用相同数据范围和物理长宽比，直接裁剪原始路径，不重新拟合或平滑。均等分配参考线在放大图文字下方断开，实际洛伦兹曲线保持完整。

## 数据与计算

使用当前清洗后的年度全体研究者跨国事件，按目的地国家汇总流入、按来源国家汇总流出，并与清洗数据附带的国家年度汇总表核对。样本为相应年份、相应方向有正流量的全部国家。密度以国家为等权观测，使用log10百分比份额和共同带宽0.3216506491，每条密度在对数坐标中积分为1。HHI、Gini和洛伦兹曲线由同一组国家份额计算。

中位数先在原始国家百分比份额上计算，再转换为对数坐标。蓝、红、绿、黄分别对应1998、2007、2016和2025年，仅用于密度与洛伦兹快照及其放大图。年度双纵轴图的蓝、红色分别表示HHI和Gini，图内另有明确的指标图例。

## 简短中文图注

**图3 国家层面跨国研究者流动的分布变化。** a、b，四个年份的国家流入、流出份额分布；右上放大图中的同色竖虚线表示各年国家份额中位数。c、d分别对应流入与流出：左图为洛伦兹曲线及局部放大图，右图为1998—2025年年度HHI（蓝色，左轴）与Gini（红色，右轴）。灰色对角虚线表示均等分配。两方向的同类图采用相同坐标范围。

## English caption

**Fig. 3 | Country-level distributions of international researcher mobility.** a,b, National inflow and outflow share distributions in four selected years. Upper-right insets enlarge the peak region; coloured vertical dashed guides mark median country shares. c,d, Inflow and outflow comparisons: Lorenz curves with local enlargements (left), and annual HHI (blue, left axis) and Gini (red, right axis) over 1998–2025 (right). Grey dashed diagonals indicate equal distribution. Matched inflow and outflow plots use identical axis ranges.

## 来源表与复核

- Fig3_country_year_data.csv：全部年度、两个方向的国家流量与份额。
- Fig3_country_metrics.csv：年度HHI、Gini及辅助分布指标。
- Fig3_density_curves.csv：八条密度曲线。
- Fig3_lorenz_curves.csv：八条洛伦兹曲线。
- Fig3_density_median_guides.csv：八条中位数竖线的实际数值与PDF位置。
- Fig3_annual_dual_axis_plotted_values.csv：当前四条年度曲线的112个实际值、轴归属与PDF位置。
- Fig3_zoom_windows.csv及Fig3_zoom_curves.csv：四张放大图的取景范围和路径。

此前覆盖、累计前列国家份额及HHI小图的来源表保留为辅助或历史记录，已不对应当前的嵌图。当前数据与PDF点位、曲线路径、字体、对齐及文字碰撞检查在QA/Fig3中。


## 洛伦兹局部放大更新

c、d左图取景同步调整为累计国家比例75%—93%、累计流量3%—32%。放大图约32.53×52.41 pt，横纵物理放大倍率相等，由约1.526倍增至2.310倍，即曲线细节相对上一版增大约51%。放大图内路径与主图指示框中的原始曲线严格一致。两方向使用相同范围，仍采用直线连接指示框与放大图；a、b和两个年度双轴图均保持原样。
