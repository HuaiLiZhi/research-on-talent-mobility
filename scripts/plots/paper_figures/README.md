# 最终论文绘图入口

主稿位于 outputs/paper_final/。实际绘制入口以 manifest.json 为准。

| 图号 | 绘制脚本 |
| --- | --- |
| Fig1 | outputs/figure_revision_20261111/plot_Fig1.py |
| Fig2 | outputs/figure2_joint_layout_20261112/plot_Fig2.py |
| Fig3 | outputs/figure_revision_20261111/plot_Fig3.py |
| Fig4 | outputs/figure_gini_palette_20261111/plot_Fig4.py |
| Fig5 | outputs/results_network_revision_20261030/plot_sources/plot_Fig4.py |
| Fig6 | outputs/figure6_equal_fits_20261112/plot_Fig6.py |

从仓库根目录运行：

    python scripts/plots/paper_figures/render.py Fig2
    python scripts/plots/paper_figures/verify_manifest.py --check-artwork

render.py 接受 Fig1–Fig6。第三、五、六幅图需要完整的 flow_top100.parquet 输入，按 data/EXTERNAL_INPUTS.json 准备。Fig.5 同时使用已保留的国内城市年度流量边际表。绘制结果写入各脚本的 artwork 目录，论文中的最终导出图位于 outputs/paper_final/figures/。重新绘制会改变 PDF 元数据时间，重新归档时应核对数据和图形后同步清单。

带日期的上游脚本包含被实际导入的函数，按依赖关系保留。qa/ 中的 Python 文件为运行时验证模块。补充图源代码单独保留，主稿按现有 main.tex 设置编译。

样式、配色和物理尺寸由 figures/v3/figure_style.py 及 figure_palette.py 定义。当前默认字体为 Arial，可通过 NHB_FONT_FAMILY 和 NHB_FONT_DIRECTORY 指定本地字体。
