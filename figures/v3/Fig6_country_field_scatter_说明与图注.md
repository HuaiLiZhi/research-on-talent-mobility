# Fig6 国家与学科组合散点图

每个点代表一个国家中的一个学科，共886个组合，涉及77个国家和26个学科。使用当前清洗后的国内城际流动数据，在所有国家中保留1998—2025年每年都有该学科国内流动的组合。未对流动量设置门槛，也不再限于之前的国家样本。其余2308个组合缺少完整28年记录，未参与这一全期趋势比较。

国内城市的流入、流出量先按稳定城市标识相加，再计算该国该学科每年的HHI和Gini。横轴是HHI的拟合年变化，纵轴是Gini的拟合年变化，两者均对完整28年年度值作普通最小二乘拟合，单位均为百分点每年。每个组合使用自己的国内城市分布，不使用跨国流量份额，也不使用跨国汇总后的学科中位数。

颜色对应OpenAlex四大学科类。理工科学为蓝色，共376点；生命科学为绿色，共180点；健康科学为红色，共146点；人文社会科学为黄色，共184点。虚线采用该类所有点的凸包外扩轮廓，用来表示成员分布范围，不代表置信区间。点位保留真实坐标，未按类别平移或抖动。

右上方表示HHI和Gini同时上升，左下方表示两者同时下降。左上方表示HHI下降而Gini上升，右下方表示HHI上升而Gini下降。两项指标关注分布的不同方面，不能把所有Gini上升的点都解释为两项指标共同支持集中化。

## 简短图注

**图6 不同国家与学科的国内城市集中趋势。** 每个点代表一个国家与学科组合，横、纵轴分别为国内城市HHI和Gini的年变化，均由1998—2025年完整年度序列拟合，单位为百分点每年。流入与流出先在城市层面合并。共包含77个国家、26个学科的886个组合。颜色与同色虚线轮廓区分四大学科类，灰色参考线表示零变化。

**Fig. 6 | Domestic urban concentration trends across countries and fields.** Each point represents a country–field combination. The horizontal and vertical axes show annual changes in domestic urban HHI and Gini, respectively, fitted over 1998–2025 and expressed in percentage points per year. Incoming and outgoing strengths are combined at each city before calculating the indices. The figure includes 886 combinations across 77 countries and 26 fields with observations in all 28 years. Colours and dashed envelopes identify four research domains; grey lines mark zero change.

## 文件与复核

图宽180毫米、高170毫米，绘图区为400×400pt的正方形。正文阅读版与NHB_final期刊字号版均提供PDF、可编辑SVG和600dpi PNG。原有Fig6与26学科汇总散点图保留。

source_data中的Fig6_country_field_scatter_points.csv记录全部点的身份、类别与坐标。Fig6_country_field_annual_metrics.csv保存24808条年度指标，Fig6_country_field_availability.csv记录所有3194个有国内流动记录的国家与学科组合及其筛选情况。QA中记录数据、字体、点位、轮廓与碰撞检查。
