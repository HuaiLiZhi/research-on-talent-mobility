"""Additional, attributed municipal references; no arbitrary ADM tier promotion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import hashlib, json, sys, time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tmp/nhb_fig2_python_deps'))
import truststore
truststore.inject_into_ssl()
OUT = ROOT / 'data/raw/geo/municipal_20261020/extension'
OUT.mkdir(exist_ok=True)
records = []

def get(name, url):
    path = OUT / name
    if not path.exists():
        for attempt in range(3):
            try:
                with urlopen(Request(url, headers={'User-Agent':'BRIDGE-research-municipal-audit/1.0'}), timeout=40) as response:
                    data = response.read()
                json.loads(data)
                temporary = path.with_suffix(path.suffix + '.part')
                temporary.write_bytes(data)
                temporary.replace(path)
                break
            except Exception:
                if attempt == 2: raise
                time.sleep(1)
    data = path.read_bytes()
    records.append(dict(file=name, url=url, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()))
    return json.loads(data)

def china():
    base = 'https://geo.datav.aliyun.com/areas_v3/bound/'
    national = get('CN_100000_full.json', base + '100000_full.json')
    provinces = [f for f in national['features'] if f['properties']['adcode'] not in [100000,710000,810000,820000] and f['properties'].get('childrenNum',0)>0]
    direct = {110000,120000,310000,500000}
    def province(f):
        code = f['properties']['adcode']
        return get(f'CN_{code}_full.json', base + str(code) + '_full.json')
    with ThreadPoolExecutor(max_workers=6) as pool:
        children = list(pool.map(province, provinces))
    prefectures = []
    for parent, child in zip(provinces, children):
        if parent['properties']['adcode'] in direct: continue
        for f in child['features']:
            p = f['properties']
            if p.get('level') == 'city' and p.get('childrenNum',0)>0:
                prefectures.append(p['adcode'])
    def prefecture(code):
        try: return get(f'CN_{code}_full.json', base + str(code) + '_full.json')
        except Exception as error:
            print('Missing prefecture child layer',code,str(error)[:70],flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(prefecture,prefectures))
    print('China province layers',len(provinces),'prefecture child layers',len(prefectures),flush=True)

def arcgis(name, service, item):
    metadata = get(name+'_metadata.json',service+'?f=json')
    item_metadata = get(name+'_item.json','https://www.arcgis.com/sharing/rest/content/items/'+item+'?f=json')
    assert 'error' not in metadata and 'error' not in item_metadata
    layer = metadata['layers'][0]['id']
    query=service+'/'+str(layer)+'/query?'
    total=get(name+'_count.json',query+urlencode(dict(where='1=1',returnCountOnly='true',f='json')))['count']
    features=[]
    fields='BDY_ID,ENG_NAME_VALUE,OBJECTID' if name.startswith('IE_') else '*'
    for offset in range(0,total,1000):
        url=query+urlencode(dict(where='1=1',outFields=fields,outSR=4326,f='geojson',returnGeometry='true',
            resultOffset=offset,resultRecordCount=1000,orderByFields='OBJECTID',geometryPrecision=6,maxAllowableOffset=.00005))
        page=get(name+'_page_'+str(offset)+'.geojson',url)
        assert 'error' not in page and page.get('features')
        features.extend(page['features'])
    assert len(features)==total,(name,len(features),total)
    data=dict(type='FeatureCollection',features=features)
    (OUT/(name+'.geojson')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
    print(name,len(features),features[0]['properties'],flush=True)

def main():
    china()
    arcgis('NZ_TA2025','https://services2.arcgis.com/vKb0s8tBIA3bdocZ/arcgis/rest/services/Territorial_Authority_2025/FeatureServer','d3d3d1c8fb2142f6b222a4233360be16')
    (OUT/'download_manifest.json').write_text(json.dumps(dict(retrieved_utc=datetime.now(timezone.utc).isoformat(),files=records,
        china_notes='Alibaba DataV is a secondary map reference, not an official government boundary release. Boundary membership must be robust to GCJ02/WGS84 offset; independent county-level cities must have priority. Map labels and adcodes are retained.'),ensure_ascii=False,indent=2),encoding='utf8')

if __name__=='__main__': main()
