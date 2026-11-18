"""Download attributed GeoNames reference files with durable provenance."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'data/raw/geo/geonames_20261020'
FILES=['allCountries.zip','hierarchy.zip','admin1CodesASCII.txt','admin2Codes.txt','readme.txt']


def download(name):
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/name
    if target.exists() and (not name.endswith('.zip') or zipfile.is_zipfile(target)):
        return dict(name=name,bytes=target.stat().st_size,sha256=hashlib.sha256(target.read_bytes()).hexdigest(),cached=True)
    url='https://download.geonames.org/export/dump/'+name
    partial=OUT/(name+'.part')
    for attempt in range(4):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'BRIDGE-research-city-harmonization/1.0'})
            h=hashlib.sha256();n=0;last=time.monotonic()
            with urllib.request.urlopen(req,timeout=60) as response,partial.open('wb') as f:
                headers=dict(response.headers)
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    f.write(chunk);h.update(chunk);n+=len(chunk)
                    if time.monotonic()-last>25:
                        print(f'{name}: {n/1e6:.1f} MB downloaded',flush=True);last=time.monotonic()
            if name.endswith('.zip'):
                with zipfile.ZipFile(partial) as archive:
                    assert archive.testzip() is None
            partial.replace(target)
            print(f'{name}: complete, {n/1e6:.1f} MB',flush=True)
            return dict(name=name,url=url,bytes=n,sha256=h.hexdigest(),http_headers=headers,
                        downloaded_utc=datetime.now(timezone.utc).isoformat())
        except Exception as error:
            print(f'{name}: attempt {attempt+1} failed: {error}',flush=True)
            if attempt==3:raise
            time.sleep(2)


if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=3) as pool:
        records=[future.result() for future in as_completed([pool.submit(download,n) for n in FILES])]
    (OUT/'download_manifest.json').write_text(json.dumps(dict(
        provider='GeoNames',license='CC BY 4.0',license_url='https://creativecommons.org/licenses/by/4.0/',
        source_readme='https://download.geonames.org/export/dump/readme.txt',files=records),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Reference downloads complete',flush=True)
