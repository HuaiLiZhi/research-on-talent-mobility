# Fig.1 地图资源

以下文件随 Git 提供，保持绘制脚本使用的路径。运行 `scripts/plots/plot_fig1_framework_detailed.py` 直接读取这些裁剪后的地图，不需要重新下载完整地名库、重新清洗流动数据或调用大语言模型。

## 资源清单

`data/raw/fig1_shanghai_real_maps_20261103/`：

- `shanghai_pudong.geojson`：城市与所属城区的真实边界。
- `shanghai_districts.geojson`：城市内部的同来源区划。
- `manifest.json`：原始来源、边界合成方法和归属信息。
- `CHN_ADM1_metadata.json`、`CHN_ADM3_metadata.json`：边界来源元数据。

`data/raw/fig1_square_maps_20261103/`：

- `china_provinces.geojson`：主机构选择示意使用的国家地图。
- `candidate_cities.geojson`：六个候选城市的来源坐标，包含一个示意选定位置。
- `manifest.json`：国家边界和城市坐标来源。

`data/raw/fig1_map_context_20261103/`：

- `national_context.geojson`：国家地图的周边地理背景。
- `city_context.geojson`：城市地图的周边地理背景。
- `manifest.json`：两个显示范围、裁剪规则与来源校验值。

共 11 个文件。`manifest.json` 中的 `asset_files` 逐项记录用途、字节数及 SHA-256。较早来源清单还保留街道裁剪的历史记录；那些文件不参与当前绘制，也不属于本次资源清单。

## 来源、处理和许可

| 数据 | 来源及处理 | 许可及归属 |
| --- | --- | --- |
| 国家边界 | geoBoundaries `CHN-ADM1-43563684`；保留所用源文件的全部地理要素 | 源元数据标注为 Public Domain |
| 城市、城区及周边区划 | geoBoundaries `CHN-ADM3-62558664`，2017 年区划；同来源的 16 个区划合成城市边界，周边地理按视窗裁剪 | Open Data Commons Open Database License 1.0；geoBoundaries、Lee Beryman、© OpenStreetMap contributors。这些提取和合成后的区划数据库继续按 ODbL 1.0 提供 |
| 候选城市坐标 | GeoNames，2026-10-20 本地参考快照；提取六个城市坐标及标识 | Creative Commons Attribution 4.0；归属 GeoNames。候选身份和绿色选定位置为框架示意 |
| 国家地图的周边背景 | Natural Earth 1:110m admin-0；按显示范围裁剪 | Public Domain；Made with Natural Earth |

许可及原始来源链接：

- [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/)
- [OpenStreetMap copyright and attribution](https://www.openstreetmap.org/copyright)
- [GeoNames data and services](https://www.geonames.org/export/)；[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- [Natural Earth terms of use](https://www.naturalearthdata.com/about/terms-of-use/)
- [geoBoundaries 国家边界原始文件](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/CHN/ADM1/geoBoundaries-CHN-ADM1.geojson)
- [geoBoundaries 城区原始文件](https://github.com/wmgeolab/geoBoundaries/raw/9469f09/releaseData/gbOpen/CHN/ADM3/geoBoundaries-CHN-ADM3.geojson)

以上地理数据保留各自来源许可。论文的图注保留地图归属说明，绘制代码与这些外部地理数据分开管理。
