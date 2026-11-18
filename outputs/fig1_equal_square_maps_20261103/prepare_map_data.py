"""Freeze sourced geography for two illustrative, unlabeled map cards."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tmp/nhb_fig2_python_deps'))
import duckdb
from shapely import make_valid
from shapely.geometry import Point, shape
from shapely.ops import unary_union

OUT = ROOT / 'data/raw/fig1_square_maps_20261103'
OUT.mkdir(parents=True, exist_ok=True)
boundary_source = ROOT / 'data/raw/geo/municipal_20261020/gb_CHN_ADM1.geojson'
boundary_file = OUT / 'china_provinces.geojson'
shutil.copy2(boundary_source, boundary_file)
features = json.loads(boundary_file.read_text(encoding='utf-8'))['features']
country = unary_union([make_valid(shape(f['geometry'])) for f in features])
db_source = ROOT / 'data/raw/geo/geonames_20261020/reference.duckdb'
con = duckdb.connect(str(db_source), read_only=True)
city_features = []
for name in ['Shanghai', 'Beijing', 'Chengdu', "Xi'an", 'Guangzhou', 'Wuhan']:
    row = con.execute('''SELECT geonameid, asciiname, longitude, latitude
        FROM gaz WHERE country = 'CN' AND feature_class = 'P'
        AND (asciiname = ? OR name = ?) ORDER BY population DESC LIMIT 1''',
        [name, name]).fetchone()
    assert row is not None
    geonameid, city, lon, lat = row
    assert country.covers(Point(lon,lat)), city
    city_features.append({'type':'Feature', 'properties':{
        'geonameid':geonameid, 'name':city,
        'selected_primary_location':name == 'Shanghai',
        'role':'Illustrative candidate location, not a measured author record'},
        'geometry':{'type':'Point','coordinates':[lon,lat]}})
con.close()
points_file = OUT / 'candidate_cities.geojson'
points_file.write_text(json.dumps({'type':'FeatureCollection','features':city_features},
                                 indent=2,ensure_ascii=False),encoding='utf-8')
assert sum(f['properties']['selected_primary_location'] for f in city_features) == 1
metadata = json.loads((ROOT / 'data/raw/fig1_shanghai_real_maps_20261103/CHN_ADM1_metadata.json').read_text(encoding='utf-8'))
manifest = {
    'purpose':'Illustrative primary-affiliation selection and parent-city harmonization; no empirical individual record or LLM validation claim',
    'boundary_source_file':str(boundary_source.relative_to(ROOT)),
    'boundary_source_url':metadata['gjDownloadURL'],
    'boundary_license':metadata['boundaryLicense'],
    'all_source_boundary_features_retained':True,
    'city_coordinate_source_file':str(db_source.relative_to(ROOT)),
    'city_coordinate_source':'GeoNames, local reference snapshot 2026-10-20',
    'city_coordinate_license':'CC BY 4.0',
    'city_coordinate_url':'https://www.geonames.org/',
    'city_selection_rule':'Six illustrative cities; one green selected city; no place names displayed',
    'city_example_selection_is_empirical':False,
    'regional_boundary_manifest':'data/raw/fig1_shanghai_real_maps_20261103/manifest.json',
    'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()
              for p in [boundary_file,points_file]},
}
(OUT / 'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
print(json.dumps({'candidate_city_count':len(city_features),
                  'selected_city_count':1,'point_locations_within_boundary':True,
                  'output':str(OUT)}))
