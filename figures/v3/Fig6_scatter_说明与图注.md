# Fig6 学科散点图方案

26个具名学科各对应一个圆点，以OpenAlex四大学科类区分颜色：理工科学为蓝色#7E99F4，生命科学为绿色#7AB656，健康科学为红色#CC7C71，人文社会科学为黄色#C9A45C。

横轴为各学科国家间跨国流动Gini的拟合年变化，纵轴为各学科国内城市Gini年度国家中位数的拟合年变化，单位均为百分点每年。两者均使用1998—2025年全部28个年度值。国内城市指标逐国计算，保留该学科全28年均至少涉及两座有合并流量城市的固定国家样本，各学科14—68国。流入与流出在国家或稳定城市ID上合并后计算指标。

全部点位直接使用既有学科趋势数据，未按大类移动、抖动或分离。虚线为该大类所有学科点的凸包外扩轮廓，边缘留白8pt，用于标示成员分布范围。轮廓之间的重叠表示不同大类在这两项指标上存在相近的学科；虚线圈不表示置信区间。

图中保留全部26个学科名称。较长学科名换行或采用常见英文缩写，完整名称与显示名称的对应关系见Fig6_scatter_points.csv。细灰色引线仅用于较远的名称标注。

## 简短中文图注

**图6 学科流动集中趋势的跨尺度比较。** 每个点代表一个学科，横、纵轴分别为国家间跨国流动Gini与国内城市Gini年度国家中位数的年变化，均使用1998—2025年完整年度序列拟合。颜色与虚线轮廓区分四大学科类，灰色竖线表示国家Gini零变化。点位保留实际指标坐标，虚线圈表示成员分布范围。

## English caption

**Fig. 6 | Disciplinary concentration trends across spatial scales.** Each point represents a field. The horizontal and vertical axes show annual trends in country-level international mobility Gini and the annual country median of domestic urban Gini, respectively, fitted over 1998–2025. Colours and dashed envelopes identify four broad research domains. The grey vertical line marks zero change in country Gini. Envelopes describe domain membership ranges.

## 输出与复核

图宽180毫米、高170毫米，单张正方形绘图区400×400pt。Helvetica字体、黑色文字。当前目录为正文阅读版，NHB_final为期刊字号版。输出PDF、可编辑SVG及600dpi PNG，文件名均为Fig6_scatter。

精确绘图值为source_data/Fig6_scatter_points.csv，26个文字标注和四组轮廓的几何数据分别在Fig6_scatter_labels.csv及Fig6_scatter_envelopes.csv。来源为当前Fig6学科年度趋势表与经官方API核对的大类映射。数据、PDF位置、字体及碰撞检查位于QA/Fig6_scatter。
