"""Extract sourced real geography for Fig.1; no synthetic map primitives."""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tmp/nhb_fig2_python_deps'))
from shapely.geometry import shape, mapping, Polygon, LineString, box, Point
from shapely.ops import unary_union

OUT = ROOT / 'data/raw/fig1_shanghai_real_maps_20261103'
GEO = ROOT / 'data/raw/geo/municipal_20261020'
BBOX = (121.490, 31.226, 121.512, 31.242)
viewport = box(*BBOX)
adm1 = json.loads((GEO / 'gb_CHN_ADM1.geojson').read_text(encoding='utf-8'))
adm3 = json.loads((GEO / 'gb_CHN_ADM3.geojson').read_text(encoding='utf-8'))
original_shanghai = next(f for f in adm1['features'] if f['properties']['shapeName'] == 'Shanghai Municipality')
pudong = next(f for f in adm3['features'] if f['properties']['shapeName'] == 'Pudong New District')
district_names = {'Huangpu District', 'Xuhui District', 'Changning District', "Jing'an District",
                 'Putuo District', 'Hongkou District', 'Yangpu District', 'Minhang District',
                 'Baoshan District', 'Jiading District', 'Pudong New District', 'Jinshan District',
                 'Songjiang District', 'Qingpu District', 'Fengxian District', 'Chongming District'}
context = [f for f in adm3['features'] if f['properties']['shapeName'] in district_names
           and box(120.7,30.4,122.3,32.1).covers(shape(f['geometry']).representative_point())]
assert len(context) == 16
# Use one matched boundary vintage at both levels. The independently sourced
# ADM1 simplification clips coastal districts; dissolving the 16 real ADM3
# districts retains their actual outer edges and guarantees geographic nesting.
shanghai_geom = unary_union([shape(f['geometry']) for f in context])
pudong_geom = shape(pudong['geometry'])
assert pudong_geom.difference(shanghai_geom).area < 1e-10
shanghai = {'type':'Feature', 'properties': {'shapeName':'Shanghai Municipality',
            'derivation':'Union of the 16 matched 2017 Shanghai district geometries'},
            'geometry':mapping(shanghai_geom)}
assert shanghai_geom.covers(viewport.centroid)
assert pudong_geom.covers(viewport.centroid)
regions = {'type': 'FeatureCollection', 'features': [shanghai, pudong]}
(OUT / 'shanghai_pudong.geojson').write_text(json.dumps(regions, ensure_ascii=False), encoding='utf-8')
(OUT / 'shanghai_districts.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': context}, ensure_ascii=False), encoding='utf-8')

xml = ET.parse(OUT / 'lujiazui_osm.osm').getroot()
nodes = {n.get('id'): (float(n.get('lon')), float(n.get('lat'))) for n in xml.findall('node')}
features = []
for way in xml.findall('way'):
    tags = {t.get('k'): t.get('v') for t in way.findall('tag')}
    refs = [n.get('ref') for n in way.findall('nd')]
    if not all(n in nodes for n in refs) or len(refs) < 2:
        continue
    coordinates = [nodes[n] for n in refs]
    kind = None
    if 'building' in tags and coordinates[0] == coordinates[-1] and len(coordinates) >= 4:
        geometry = Polygon(coordinates)
        kind = 'building'
    elif 'highway' in tags:
        geometry = LineString(coordinates)
        kind = 'road'
    elif tags.get('natural') == 'water' and coordinates[0] == coordinates[-1] and len(coordinates) >= 4:
        geometry = Polygon(coordinates)
        kind = 'water'
    elif tags.get('leisure') in {'park', 'garden'} and coordinates[0] == coordinates[-1] and len(coordinates) >= 4:
        geometry = Polygon(coordinates)
        kind = 'park'
    if kind is None:
        continue
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    clipped = geometry.intersection(viewport)
    if clipped.is_empty:
        continue
    century = kind == 'road' and tags.get('name') == '世纪大道'
    features.append({'type': 'Feature', 'properties': {
        'osm_way_id': way.get('id'), 'kind': kind,
        'highway': tags.get('highway'), 'name': tags.get('name'),
        'name_en': tags.get('name:en'), 'century_avenue': century,
    }, 'geometry': mapping(clipped)})
assert any(f['properties']['century_avenue'] for f in features)
counts = {k: sum(f['properties']['kind'] == k for f in features) for k in ['building', 'road', 'water', 'park']}
assert counts['building'] > 100 and counts['road'] > 100
local = {'type': 'FeatureCollection', 'bbox': list(BBOX), 'features': features}
(OUT / 'century_avenue_local.geojson').write_text(json.dumps(local, ensure_ascii=False), encoding='utf-8')

metadata = [json.loads((OUT / f'CHN_ADM{a}_metadata.json').read_text(encoding='utf-8')) for a in (1,3)]
assert metadata[0]['boundaryID'].endswith('43563684')
assert metadata[1]['boundaryID'].endswith('62558664')
manifest = {
    'purpose': 'Illustrative real maps for city identity resolution; not mobility observations or an LLM validation experiment',
    'figure_backend': 'Python/Matplotlib; all boundaries, roads and footprints from sourced geometry',
    'local_bbox_wgs84': list(BBOX),
    'all_selected_features_retained': True,
    'local_geometry_counts': counts,
    'century_avenue_segments': sum(f['properties']['century_avenue'] for f in features),
    'century_avenue_locator': list(viewport.centroid.coords)[0],
    'local_centroid_within_pudong_and_shanghai': True,
    'shanghai_context_districts': len(context),
    'boundary_sources': [{k:m.get(k) for k in ['boundaryID', 'boundaryYearRepresented', 'boundarySource', 'boundaryLicense', 'boundarySourceURL', 'gjDownloadURL']} for m in metadata[1:]],
    'shanghai_boundary_derivation': 'Dissolve all 16 Shanghai district geometries from the same ADM3 source; no manually invented outlines',
    'pudong_outside_shanghai_area': pudong_geom.difference(shanghai_geom).area,
    'unused_boundary_sources': 'The independent 2019 ADM1 simplification and downloaded current OSM maritime municipality geometry are archived, not drawn',
    'osm_source': 'https://api.openstreetmap.org/api/0.6/map?bbox=121.490,31.226,121.512,31.242',
    'attribution': 'geoBoundaries; © OpenStreetMap contributors',
    'osm_license': 'Open Database License 1.0',
    'osm_license_url': 'https://www.openstreetmap.org/copyright',
    'style_reference': 'User-supplied RegionDCL diagram: compact map crops, highlighted matching regions and dashed zoom connectors; no contrastive-learning claim',
    'sha256': {},
}
for name in ['shanghai_pudong.geojson', 'shanghai_districts.geojson', 'century_avenue_local.geojson', 'lujiazui_osm.osm']:
    manifest['sha256'][name] = hashlib.sha256((OUT/name).read_bytes()).hexdigest()
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(manifest, ensure_ascii=False, indent=2))
