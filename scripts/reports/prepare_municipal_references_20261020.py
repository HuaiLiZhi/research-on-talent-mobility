"""Download versioned municipal reference boundaries with attribution and hashes."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,re,sys,time,zipfile
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import truststore
truststore.inject_into_ssl()
OUT=ROOT/'data/raw/geo/municipal_20261020'
OUT.mkdir(parents=True,exist_ok=True)
UA='BRIDGE-academic-municipality-harmonization/1.0'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()

def get(job):
    path=OUT/job['filename'];partial=path.with_suffix(path.suffix+'.part')
    if path.exists() and (not path.name.endswith('.zip') or zipfile.is_zipfile(path)):
        return dict(job,bytes=path.stat().st_size,sha256=sha(path),cached=True)
    for attempt in range(3):
        try:
            started=last=time.monotonic()
            with urlopen(Request(job['url'],headers={'User-Agent':UA}),timeout=60) as r,partial.open('wb') as f:
                expected=r.headers.get('Content-Length');n=0
                while True:
                    b=r.read(1024*1024)
                    if not b:break
                    f.write(b);n+=len(b)
                    if time.monotonic()-last>20:
                        print(job['filename'],round(n/1e6,1),'MB',flush=True);last=time.monotonic()
            assert expected is None or n==int(expected),(n,expected)
            assert n>100
            if path.name.endswith('.zip'):
                assert zipfile.is_zipfile(partial)
            partial.replace(path)
            print('Completed',job['filename'],round(n/1e6,1),'MB',flush=True)
            return dict(job,bytes=n,sha256=sha(path),downloaded_utc=datetime.now(timezone.utc).isoformat())
        except Exception as e:
            print('Retry',job['filename'],attempt+1,str(e)[:150],flush=True)
            if attempt==2:return dict(job,error=str(e))
            time.sleep(2)

def main():
    base_abs='https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/access-and-downloads/digital-boundary-files'
    jobs=[
      dict(filename='EU_LAU_2024_4326.gpkg',url='https://gisco-services.ec.europa.eu/distribution/v2/lau/gpkg/LAU_RG_01M_2024_4326.gpkg',provider='Eurostat GISCO',unit='Local Administrative Unit',license='Eurostat/GISCO non-commercial research attribution terms',official=True),
      dict(filename='US_COUSUB_2024.zip',url='https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_cousub_500k.zip',provider='US Census Bureau',unit='Active governmental minor civil divisions only; statistical units excluded',license='US Government public data',official=True),
      dict(filename='AU_LGA_2025.zip',url=base_abs+'/LGA_2025_AUST_GDA2020.zip',provider='Australian Bureau of Statistics',unit='LGA; statistical approximation of gazetted municipal boundaries; non-incorporated regions separately flagged',license='CC BY 4.0',official=True),
      dict(filename='CA_CSD_2021.zip',url='https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/files-fichiers/lcsd000b21a_e.zip',provider='Statistics Canada',unit='Census subdivision: municipality or separately identified equivalent',license='Statistics Canada Open Licence',official=True),
      dict(filename='BR_Municipios_2024.zip',url='https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2024/Brasil/BR_Municipios_2024.zip',provider='IBGE',unit='Municipio; operational water polygons excluded',license='IBGE public data attribution',official=True),
      dict(filename='JP_N03_2025.zip',url='https://nlftp.mlit.go.jp/ksj/gml/data/N03/N03-2025/N03-20250101_GML.zip',provider='Japan MLIT',unit='Municipalities; designated-city administrative wards dissolved by parent municipality; Tokyo special wards retained',license='CC BY 4.0',official=True),
    ]
    metadata=json.loads((OUT/'geoboundaries_all_metadata.json').read_text(encoding='utf8'))
    # Only layers whose administrative function is municipal, not arbitrary ADM2.
    municipal={
       'AGO':'ADM2','ARM':'ADM2','BEN':'ADM2','BGR':'ADM2','BIH':'ADM3','BOL':'ADM3',
       'CHE':'ADM3','CHL':'ADM3','COL':'ADM2','COM':'ADM3','CRI':'ADM2','CUB':'ADM2',
       'DNK':'ADM2','DOM':'ADM2','DZA':'ADM3','ECU':'ADM2','FSM':'ADM2','GEO':'ADM2',
       'GRC':'ADM3','GTM':'ADM2','HND':'ADM2','ISL':'ADM2','KOR':'ADM2','LUX':'ADM3',
       'MDG':'ADM3','MEX':'ADM2','MLI':'ADM3','NER':'ADM3','NGA':'ADM2','NLD':'ADM2',
       'NPL':'ADM3','PHL':'ADM3','PRI':'ADM2','ROU':'ADM2','SRB':'ADM2','SWE':'ADM2',
       'URY':'ADM2','VEN':'ADM2','ZAF':'ADM3',
    }
    for cc,level in municipal.items():
        r=next((v for v in metadata if v['boundaryISO']==cc and v['boundaryType']==level),None)
        if not r:continue
        url=r['simplifiedGeometryGeoJSON'].replace('https://github.com/','https://media.githubusercontent.com/media/').replace('/raw/','/')
        jobs.append(dict(filename=f'gb_{cc}_{level}.geojson',url=url,provider='geoBoundaries gbOpen',
            official=False,underlying_source=r['boundarySource'],source_url=r['boundarySourceURL'],
            unit=r['boundaryCanonical'],year=r['boundaryYearRepresented'],license=r['boundaryLicense'],
            boundary_id=r['boundaryID'],metadata_reference='geoboundaries_all_metadata.json'))
    (OUT/'download_plan.json').write_text(json.dumps(jobs,ensure_ascii=False,indent=2),encoding='utf8')
    with ThreadPoolExecutor(max_workers=4) as pool:
        records=[f.result() for f in as_completed([pool.submit(get,j) for j in jobs])]
    (OUT/'download_manifest.json').write_text(json.dumps(dict(created_utc=datetime.now(timezone.utc).isoformat(),files=records,
        policy='Official source boundaries preferred. Secondary mirrors are explicitly distinguished; missing or non-municipal layers do not become verified administrative cities.'),ensure_ascii=False,indent=2),encoding='utf8')
    print('Reference jobs',len(records),'errors',sum('error' in r for r in records),flush=True)

if __name__=='__main__':main()
