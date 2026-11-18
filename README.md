# Research on Talent Mobility

本仓库维护当前论文 Quantifying Brain Drain and Gain: Large-Scale Trace Studies on Spatial Inequalities in Researcher Mobility 的稿件、图表、分析代码和 OpenAlex 数据处理代码。2026 年 11 月 18 日按最终稿范围整理。

| 目录 | 内容 |
| --- | --- |
| outputs/paper_final/ | 当前英文 LaTeX、中文译稿、中文 Word、主图与补充材料源文件 |
| outputs/paper_final/source_data/ | 当前 Results 和图表的汇总数据 |
| outputs/paper_final/figures/source_data/ | 国家样本、T1–T4、学科映射与方法核对表 |
| preprocessing/openalex/ | OpenAlex 快照提取、去重、聚合及清洗代码 |
| scripts/reports/ | 城市地理归并、跨尺度指标、抽样检验和模型分析 |
| scripts/plots/paper_figures/ | 最终图表入口清单、校验工具和运行入口 |
| figures/v3/、figures/v4/ | 最终绘图调用的样式、计算模块与输入表 |
| 其余 outputs/ 子目录 | 当前绘图和分析依赖的源代码及汇总表 |
| materials/methods_verification_20261104/ | 方法证据、样本和清洗规则的可追溯记录 |
| data/、results/ | 地理参考、城市交叉表及分析汇总输入 |

部分绘图通过动态加载早期脚本复用函数，因此沿用带日期的路径。最终图号与绘制入口以 scripts/plots/paper_figures/manifest.json 为准。

## 论文

在 outputs/paper_final/ 编译 main.tex。中文持续维护文件为 results_zh.md 和 discussion_zh.md。补充材料单独保留，当前主稿沿用最终稿的输入设置。

## 环境与图表

    python -m venv .venv
    python -m pip install -r requirements.txt
    python scripts/plots/paper_figures/verify_manifest.py --check-artwork
    python scripts/plots/paper_figures/render.py Fig1
    python scripts/plots/paper_figures/render.py Fig2

运行入口接受 Fig1 至 Fig6。Fig.3、Fig.5 和 Fig.6 会核验或读取完整清洗输入，需要先准备 data/processed/mobility_city_harmonized_20261020/analysis/flow_top100.parquet。外部输入路径和体积见 data/EXTERNAL_INPUTS.json。清洗和分析脚本保留输入参数及数据路径约定，运行前根据数据位置配置。

完整快照、作者级明细和数 GB 流量表由本地数据处理流程管理。仓库提供可核对的汇总数据、输入哈希与重建代码。验证结果见 REPOSITORY_VERIFICATION.json。

## OpenAlex

处理代码从原 OpenAlex 项目归入 preprocessing/openalex/，逐文件来源与 SHA-256 见该目录的 provenance.json。主处理链使用 works 的 authorships 和机构地理信息，经过年度位置、去重、学科汇总、流量计数和地理清洗。详细运行参数见脚本 --help 及 OPENALEX_MOBILITY_PIPELINE.md。

## 版本记录

本次整理通过普通提交更新 master，历史版本可由 Git 提交记录恢复。最终图表保存在 outputs/paper_final/figures/，其他目录中的导出 PDF 用于与绘图入口清单进行哈希核对。
