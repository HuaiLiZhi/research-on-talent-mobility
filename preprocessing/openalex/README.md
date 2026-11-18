# OpenAlex 数据处理代码

这些脚本按来源原样导入，校验值记录于 provenance.json。运行位置不要求原来的 Windows OpenAlex 目录。数据根目录通过各脚本命令行参数或环境变量设置，完整快照处理通常在 Linux 上执行，去重 shell 脚本需要 Bash 和 GNU sort。

主链路包括 s00、s10、s21、s22、s23、s30–s33、s40–s41、s50–s53。s01 与 s04 用于实体导出和结构核对。另保留方法证据引用的去重、影响力分层、职业分数及分层流量构建阶段 s20、s24、s26、s27。具体阶段关系和参数以代码及 OPENALEX_MOBILITY_PIPELINE.md 为准。地理交叉表和行政城市归并代码位于仓库的 scripts/reports/。

源文档记录了历史运行路径、统计和部分对照流程，实际复现当前论文请以 outputs/paper_final/methods.tex、最终图表清单及相关输入清单为准。
