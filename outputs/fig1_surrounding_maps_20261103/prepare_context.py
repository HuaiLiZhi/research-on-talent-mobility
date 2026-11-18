"""Extract actual surrounding geography for the two schematic map viewports."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tmp/nhb_fig2_python_deps'))
from shapely import make_valid
from shapely.geometry import box, mapping, shape

OUT = ROOT / 'data/raw/fig1_map_context_20261103'
OUT.mkdir(parents=True,exist_ok=True)
VIEWS = {'national':[65.,4.,144.,68.7], 'city':[120.15,30.2,122.75,32.4]}
sources = {
    'national':ROOT / 'results/NHB_Fig1/20260913/ne_110m_admin_0_countries.geojson',
    'city':ROOT / 'data/raw/geo/municipal_20261020/gb_CHN_ADM3.geojson',
}
counts = {}
for key, source in sources.items():
    view = box(*VIEWS[key])
    items = json.loads(source.read_text(encoding='utf-8'))['features']
    selected = []
    for idx, feature in enumerate(items):
        if not feature.get('geometry'):
            continue
        geometry = make_valid(shape(feature['geometry']))
        if not geometry.intersects(view):
            continue
        clipped = geometry.intersection(view)
        if clipped.is_empty:
            continue
        selected.append({'type':'Feature','properties':{'source_feature_index':idx},
                         'geometry':mapping(clipped)})
    target = OUT / f'{key}_context.geojson'
    target.write_text(json.dumps({'type':'FeatureCollection','features':selected},
                                separators=(',',':')),encoding='utf-8')
    counts[key] = {'source_features':len(items),'viewport_features':len(selected),
                  'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
manifest = {
    'purpose':'Neutral surrounding land/boundaries for map context; not mobility observations',
    'viewports_wgs84':VIEWS,
    'sources':{k:str(v.relative_to(ROOT)) for k,v in sources.items()},
    'national_provider':'Natural Earth, 1:110m admin-0 countries; https://www.naturalearthdata.com/',
    'city_provider':'geoBoundaries, CHN ADM3, same 2017 source as highlighted city/district geometry',
    'city_source_license':'Open Database License 1.0; © OpenStreetMap contributors',
    'extraction':'All features intersecting each rectangular display viewport; clipped to that viewport; no invented geography',
    'displayed_place_names':False, 'counts_and_hashes':counts,
}
(OUT / 'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps(counts,indent=2))
