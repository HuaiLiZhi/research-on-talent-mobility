"""Build a local indexed GeoNames gazetteer; metadata, no mobility records."""
from pathlib import Path
import sys
import zipfile
import shutil
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
REF=ROOT/'data/raw/geo/geonames_20261020'
COLS=['geonameid','name','asciiname','alternatenames','latitude','longitude',
      'feature_class','feature_code','country','cc2','admin1','admin2','admin3','admin4',
      'population','elevation','dem','timezone','modified']


if __name__=='__main__':
    for archive,member in [('allCountries.zip','allCountries.txt'),('hierarchy.zip','hierarchy.txt')]:
        target=REF/member
        if not target.exists():
            print('Extracting '+member,flush=True)
            with zipfile.ZipFile(REF/archive) as z, z.open(member) as src,target.open('wb') as dst:
                shutil.copyfileobj(src,dst,1024*1024*8)
    c=duckdb.connect(str(REF/'reference.duckdb'))
    c.execute("set threads=4;set memory_limit='3GB'")
    cols='{'+','.join("'"+k+"':'VARCHAR'" for k in COLS)+'}'
    path=str(REF/'allCountries.txt').replace("'","''")
    print('Importing geographic records',flush=True)
    c.execute(f"""create or replace table gaz as select try_cast(geonameid as bigint) geonameid,
      name,asciiname,alternatenames,try_cast(latitude as double) latitude,try_cast(longitude as double) longitude,
      feature_class,feature_code,country,coalesce(admin1,'') admin1,coalesce(admin2,'') admin2,
      coalesce(admin3,'') admin3,coalesce(admin4,'') admin4,try_cast(population as bigint) population,
      regexp_replace(lower(strip_accents(name)),'[^a-z0-9]','','g') name_key,
      regexp_replace(lower(strip_accents(asciiname)),'[^a-z0-9]','','g') ascii_key
      from read_csv('{path}',delim='\\t',header=false,columns={cols},quote='',escape='',
        max_line_size=16777216,null_padding=true) where feature_class in ('P','A')""")
    c.execute('create index if not exists idx_gaz_id on gaz(geonameid)')
    c.execute('create index if not exists idx_gaz_name on gaz(country,name_key)')
    c.read_csv(str(REF/'hierarchy.txt'),sep='\t',header=False,columns={'parent':'BIGINT','child':'BIGINT','kind':'VARCHAR'}).create_view('hier_raw')
    c.execute('create or replace table hierarchy as select * from hier_raw')
    c.execute('create index if not exists idx_hier_child on hierarchy(child)')
    print('Gazetteer classes:',c.execute('select feature_class,count(*) from gaz group by 1').fetchall(),flush=True)
    print('Hierarchy:',c.execute('select kind,count(*) from hierarchy group by 1').fetchall(),flush=True)
    c.close()
