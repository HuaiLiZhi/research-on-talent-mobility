"""Build a reversible, evidence-based place-to-city crosswalk.

Original IDs and point/name matches identify places. Explicit subcity hierarchy,
official US place polygons and documented overrides define city membership.
Unverified subcity assignments remain visible for review; no nearest-city merge.
"""
from pathlib import Path
from collections import defaultdict, Counter
import csv
import hashlib
import json
import math
import re
import sys
import unicodedata
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
import numpy as np
import pycountry
import shapefile
from shapely.geometry import Point,shape
from shapely.strtree import STRtree

OUT=ROOT/'data/processed/mobility_city_harmonized_20261020'
REF=ROOT/'data/raw/geo/geonames_20261020'
SCOPE=json.loads((ROOT/'results/figure_revision_20261015/unified_country_scope/data_manifest.json').read_text(encoding='utf-8'))['country_mapping']
US_STATE_FIPS=dict(pair.split(':') for pair in ('01:AL 02:AK 04:AZ 05:AR 06:CA 08:CO 09:CT 10:DE 11:DC 12:FL 13:GA 15:HI 16:ID 17:IL 18:IN 19:IA 20:KS 21:KY 22:LA 23:ME 24:MD 25:MA 26:MI 27:MN 28:MS 29:MO 30:MT 31:NE 32:NV 33:NH 34:NJ 35:NM 36:NY 37:NC 38:ND 39:OH 40:OK 41:OR 42:PA 44:RI 45:SC 46:SD 47:TN 48:TX 49:UT 50:VT 51:VA 53:WA 54:WV 55:WI 56:WY').split())


def norm(text):
    return re.sub('[^a-z0-9]','', ''.join(c for c in unicodedata.normalize('NFKD',str(text)).lower() if not unicodedata.combining(c)))


def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def write(path,records):
    if not records:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)


def valid(lat,lon):
    try:return -90<=float(lat)<=90 and -180<=float(lon)<=180 and not (float(lat)==0 and float(lon)==0)
    except (ValueError,TypeError):return False


def distance(a,b,c,d):
    if not valid(a,b) or not valid(c,d):return float('inf')
    la1,lo1,la2,lo2=map(math.radians,map(float,[a,b,c,d]))
    h=math.sin((la1-la2)/2)**2+math.cos(la1)*math.cos(la2)*math.sin((lo1-lo2)/2)**2
    return 12742*math.asin(math.sqrt(min(1,max(0,h))))


def main():
    raw=read(OUT/'audit/raw_place_instances.csv')
    original=read(OUT/'audit/source_author_location_geographic_keys.csv')
    primary=defaultdict(list)
    primary_global=defaultdict(list)
    for s in original:
        if s['city_geonames_id']:
            primary[s['country'],norm(s['city'])].append(s)
            primary_global[norm(s['city'])].append(s)
    c=duckdb.connect(str(OUT/'audit/city_matching.duckdb'))
    c.execute("set threads=4;set memory_limit='3GB'")
    c.read_csv(str(OUT/'audit/raw_place_instances.csv'),header=True,all_varchar=True).create_view('raw_current_csv')
    c.execute('create or replace table raw as select * from raw_current_csv')
    c.execute("attach '"+str(REF/'reference.duckdb').replace("'","''")+"' as ref (read_only)")
    c.read_csv(str(OUT/'audit/source_author_location_geographic_keys.csv'),header=True,all_varchar=True).create_view('primary_location_csv')
    c.execute("create or replace table original_ids as select distinct try_cast(city_geonames_id as bigint) gid from primary_location_csv where city_geonames_id<>''")
    c.execute('create or replace table original_gaz as select g.* from ref.gaz g join original_ids o on g.geonameid=o.gid')
    ids={int(s['city_geonames_id']) for s in original if s['city_geonames_id']}
    gaz={r['geonameid']:r for r in c.execute('select * from original_gaz').fetchdf().to_dict('records')}
    # Match current normalized labels as a fallback for missing original IDs.
    c.execute("create or replace temp table name_candidates as select distinct r.raw_place_id,g.* from raw r join ref.gaz g on r.country=g.country and g.name_key=regexp_replace(lower(strip_accents(r.city)),'[^a-z0-9]','','g') where g.name_key<>''")
    name_candidates=defaultdict(list)
    for r in c.execute('select * from name_candidates').fetchdf().to_dict('records'):
        name_candidates[r['raw_place_id']].append(r);gaz[r['geonameid']]={k:v for k,v in r.items() if k!='raw_place_id'}
    # Gazetteer membership is immutable for this run.
    for r in c.execute("select p.* from ref.gaz p join ref.hierarchy h on p.geonameid=h.parent join original_ids o on o.gid=h.child").fetchdf().to_dict('records'):
        gaz[r['geonameid']]=r
    cn_admin=c.execute("select * from ref.gaz where country='CN' and feature_class='A'").fetchdf().to_dict('records')
    cn_districts=defaultdict(list)
    for g in cn_admin:
        if g['feature_code']=='ADM3' and (g['name'].endswith(' Qu') or g['name'].endswith(' Xinqu')):
            root=g['name_key']
            root=re.sub('(xinqu|qu)$','',root)
            cn_districts[g['admin1'],g['admin2'],root].append(g)
    cn_seats=defaultdict(list)
    for g in c.execute("select * from ref.gaz where country='CN' and feature_code in ('PPLC','PPLA','PPLA2')").fetchdf().to_dict('records'):
        cn_seats[g['admin1'],g['admin2']].append(g);gaz[g['geonameid']]=g
    municipalities={}
    for cc,level in [('DE','ADM4'),('CH','ADM3'),('FR','ADM4')]:
        for g in c.execute('select * from ref.gaz where country=? and feature_code=?',[cc,level]).fetchdf().to_dict('records'):
            codes=(g['admin1'],g['admin2'],g['admin3'],g['admin4']) if level=='ADM4' else (g['admin1'],g['admin2'],g['admin3'])
            municipalities[cc,codes]=g;gaz[g['geonameid']]=g
    admin1={}
    with (REF/'admin1CodesASCII.txt').open(encoding='utf-8') as f:
        for line in f:
            code,name,ascii_name,gid=line.rstrip('\n').split('\t');admin1[code]=(name,gid)
    # Official place polygons protect independent cities that GeoNames calls PPLX.
    print('Loading official US city/place boundaries',flush=True)
    us_zip=ROOT/'data/raw/geo/us_census_places_2024/cb_2024_us_place_500k.zip'
    us_reader=shapefile.Reader(str(us_zip))
    us_shapes=[];us_info=[]
    for item in us_reader.iterShapeRecords():
        props=item.record.as_dict();geometry=shape(item.shape.__geo_interface__)
        if not geometry.is_valid:
            from shapely import make_valid
            geometry=make_valid(geometry)
        us_shapes.append(geometry);us_info.append(props)
    us_tree=STRtree(us_shapes)
    print('US boundaries:',len(us_info),'fields:',list(us_info[0]),flush=True)
    # Curated rules only target confirmed components; records retain the citation.
    overrides_path=ROOT/'data/processed/mobility_city_harmonized_20261020/city_parent_overrides.csv'
    overrides=read(overrides_path) if overrides_path.exists() else []
    overrides_by_name={(r['country'],norm(r['child_name'])):r for r in overrides}
    overrides_by_id={int(r['child_geonameid']):r for r in overrides if r.get('child_geonameid')}
    def get_gaz(gid):
        gid=int(gid)
        if gid not in gaz:
            got=c.execute('select * from ref.gaz where geonameid=?',[gid]).fetchdf().to_dict('records')
            if got:gaz[gid]=got[0]
        return gaz.get(gid)
    def target_by_name(cc,name,lat,lon):
        rs=c.execute("select * from ref.gaz where country=? and name_key=? and feature_class='P' order by population desc nulls last",[cc,norm(name)]).fetchdf().to_dict('records')
        if not rs:return None
        rs.sort(key=lambda z:(distance(lat,lon,z['latitude'],z['longitude'])>150,-int(z['population'] or 0)))
        g=rs[0];gaz[g['geonameid']]=g;return g
    parent_edges=defaultdict(list)
    for parent,child,kind in c.execute('select parent,child,kind from ref.hierarchy').fetchall():
        parent_edges[int(child)].append((int(parent),kind))
    mapped=[]
    assert len({r['raw_place_id'] for r in raw})==len(raw) and all(r['raw_place_id'] for r in raw)
    for n in raw:
        lat,lon=n['latitude'],n['longitude'];nk=norm(n['city']);source=None;method='';confidence=''
        opts=[]
        for s in primary[n['country'],nk]:
            gid=int(s['city_geonames_id']);g=gaz.get(gid)
            if not g:continue
            d=distance(lat,lon,s['latitude'],s['longitude'])
            if d<=5 or (not valid(lat,lon) and s['region']==n['region']):
                opts.append((d,0 if s['region']==n['region'] else 1,-int(s['author_year_records']),gid))
        if opts:
            opts.sort();source=get_gaz(opts[0][3]);method='original_geonames_id';confidence='high'
        if not source and valid(lat,lon):
            global_opts=[]
            for s in primary_global[nk]:
                gid=int(s['city_geonames_id']);g=gaz.get(gid)
                if not g:continue
                d=distance(lat,lon,s['latitude'],s['longitude'])
                if d<=2 and distance(lat,lon,g['latitude'],g['longitude'])<=10:
                    global_opts.append((d,-int(s['author_year_records']),gid))
            if global_opts:
                global_opts.sort();source=get_gaz(global_opts[0][2]);method='original_id_name_coordinate_country_repair';confidence='high'
        if not source:
            candidates=[]
            for g in name_candidates[n['raw_place_id']]:
                d=distance(lat,lon,g['latitude'],g['longitude'])
                if d<=25:
                    candidates.append((d,0 if g['feature_class']=='P' else 1,-int(g['population'] or 0),g['geonameid']))
            if candidates:
                candidates.sort();best=candidates[0]
                source=get_gaz(best[3]);method='same_country_name_coordinate';confidence='high' if best[0]<=5 else 'medium'
        target=source;rule='retain_identified_place';evidence='GeoNames 2026-10-20 place identity';review=''
        if source:
            coord_error=distance(lat,lon,source['latitude'],source['longitude'])
            if coord_error>100 and valid(lat,lon):review='coordinate_conflict_over_100km'
            # Stable GeoNames IDs can reveal contradictory original country labels.
            cc=SCOPE.get(source['country'],source['country'])
            if source['country']!=n['country'] and coord_error>10:
                review='country_conflict_needs_review';cc=SCOPE.get(n['country'],n['country'])
            override=overrides_by_id.get(source['geonameid']) or overrides_by_name.get((source['country'],nk))
            if override and (not override.get('max_distance_km') or distance(lat,lon,
                  get_gaz(int(override['parent_geonameid']))['latitude'],get_gaz(int(override['parent_geonameid']))['longitude'])<=float(override['max_distance_km'])):
                target=get_gaz(int(override['parent_geonameid']));rule='documented_city_component' if target['geonameid']!=source['geonameid'] else 'verified_independent_place';evidence=override['evidence_url']
            elif source['country'] in ['DE','CH','FR']:
                cc_level=source['country'];codes=(source['admin1'],source['admin2'],source['admin3'],source['admin4']) if cc_level in ['DE','FR'] else (source['admin1'],source['admin2'],source['admin3'])
                municipality=municipalities.get((cc_level,codes)) if codes[-1] else None
                if municipality:
                    target=municipality;rule='country_municipality_admin_codes';evidence='GeoNames administrative containment: DE/FR ADM4 municipality; CH ADM3 municipality'
            elif source['country']=='CN' and source['admin1'] in ['22','23','28','33']:
                main_name={'22':'Beijing','23':'Shanghai','28':'Tianjin','33':'Chongqing'}[source['admin1']]
                main=target_by_name('CN',main_name,source['latitude'],source['longitude'])
                if main and distance(source['latitude'],source['longitude'],main['latitude'],main['longitude'])<=350:
                    target=main;rule='china_direct_municipality';evidence='GeoNames ADM1 direct-administered municipality and its city seat'
            elif source['country']=='CN' and source['feature_code'] not in ['PPLC','PPLA','PPLA2']:
                district_key=re.sub('(xinqu|qu)$','',source['name_key'])
                districts=cn_districts[source['admin1'],source['admin2'],district_key]
                seats=cn_seats[source['admin1'],source['admin2']]
                if districts and len(seats)==1 and any(distance(source['latitude'],source['longitude'],x['latitude'],x['longitude'])<=40 for x in districts):
                    target=seats[0];rule='china_verified_urban_district';evidence='GeoNames same-name ADM3 Qu/Xinqu within the same prefecture and unique city seat'
                elif source['feature_class']=='A' and source['name_key'].endswith('shi'):
                    main=target_by_name('CN',re.sub(r'\s+(Shi|City)$','',source['name'],flags=re.I),source['latitude'],source['longitude'])
                    if main and main['admin1']==source['admin1'] and distance(source['latitude'],source['longitude'],main['latitude'],main['longitude'])<=150:
                        target=main;rule='china_city_administrative_name';evidence='GeoNames city administrative Shi and same-name city seat within same province'
            elif source['feature_code']=='PPLX':
                parents=[get_gaz(pid) for pid,kind in parent_edges[source['geonameid']]]
                parents=[g for g in parents if g and g['feature_class']=='P' and g['feature_code'] not in ['PPLX','PPLH','PPLS'] and g['country']==source['country'] and distance(source['latitude'],source['longitude'],g['latitude'],g['longitude'])<=100]
                if len({g['geonameid'] for g in parents})==1:
                    target=parents[0];rule='geonames_explicit_subcity_parent';evidence='GeoNames feature PPLX and explicit hierarchy parent'
                else:review=review or 'subcity_parent_unresolved'
            if source['feature_class']=='A' and target==source and rule=='retain_identified_place':
                base_name=re.sub(r'^(City|Town|Municipality|District) of ','',source['name'],flags=re.I)
                possible=target_by_name(source['country'],base_name,source['latitude'],source['longitude'])
                if possible and possible['admin1']==source['admin1'] and distance(source['latitude'],source['longitude'],possible['latitude'],possible['longitude'])<=20:
                    target=possible;rule='administrative_name_to_city_seat';evidence='GeoNames identical place name, same ADM1, city seat within 20 km'
            # A US point contained in a named official place uses that place's boundary.
            if cc=='US' and valid(lat,lon):
                # One stable GeoNames place must not split again because its original points differ.
                use_reference=source['country']=='US' and distance(lat,lon,source['latitude'],source['longitude'])<=25
                point=Point(source['longitude'],source['latitude']) if use_reference else Point(float(lon),float(lat))
                hits=us_tree.query(point,predicate='intersects')
                if len(hits)==1:
                    props=us_info[int(hits[0])]
                    cleaned_id='us_census2024:'+str(props['GEOID'])
                    city=props['NAME'];state_code=props.get('STUSPS','') or US_STATE_FIPS.get(props['STATEFP'],'')
                    if not state_code:
                        state_code=next((k.split('.')[1] for k,v in admin1.items() if k.startswith('US.') and source['admin1'] and k.endswith('.'+source['admin1'])),source['admin1'])
                    region=admin1.get('US.'+state_code,(state_code,''))[0]
                    region_code='US.'+state_code
                    rule='official_us_place_polygon';evidence='https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html'
                    if review=='subcity_parent_unresolved':review=''
                    city_lat,city_lon=float(lat),float(lon)
                else:cleaned_id=None
            else:cleaned_id=None
            if cleaned_id is None:
                cleaned_id='gn:'+str(target['geonameid']);city=target['name']
                region_code=target['country']+'.'+target['admin1']
                region=admin1.get(region_code,('', ''))[0]
                city_lat,city_lon=target['latitude'],target['longitude']
                if target['feature_class']=='A' and rule=='retain_identified_place':review=review or 'administrative_feature_needs_city_review'
                if target['feature_code']=='PPLX' and rule=='retain_identified_place':review=review or 'subcity_parent_unresolved'
                if target['feature_code'] in ['PPLH','PPLG']:review=review or 'historical_or_government_feature'
        else:
            cc=SCOPE.get(n['country'],n['country']);cleaned_id='unresolved:'+n['raw_place_id']
            city=n['city'];region=n['region'];region_code='';city_lat=lat;city_lon=lon
            method='unmatched';confidence='unresolved';rule='retain_for_review';evidence='';review='place_identity_unresolved'
            if cc=='US' and valid(lat,lon):
                hits=us_tree.query(Point(float(lon),float(lat)),predicate='intersects')
                if len(hits)==1:
                    props=us_info[int(hits[0])];state_code=props['STUSPS']
                    cleaned_id='us_census2024:'+str(props['GEOID']);city=props['NAME']
                    region=admin1.get('US.'+state_code,(state_code,''))[0];region_code='US.'+state_code
                    method='official_us_polygon_identity';confidence='high';rule='official_us_place_polygon'
                    evidence='https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html';review=''
        country_obj=pycountry.countries.get(alpha_2=cc)
        row=dict(raw_place_id=n['raw_place_id'],raw_country=n['country'],raw_region=n['region'],raw_city=n['city'],
            raw_latitude=lat,raw_longitude=lon,source_geonameid=source['geonameid'] if source else '',
            source_feature_code=source['feature_code'] if source else '',match_method=method,match_confidence=confidence,
            city_id=('review:'+n['raw_place_id'] if review=='country_conflict_needs_review' else cleaned_id),country_code=cc,country_name=country_obj.name if country_obj else cc,
            region_code=region_code,region=region,city=city,city_geonameid=target['geonameid'] if target else '',
            city_latitude=city_lat,city_longitude=city_lon,merge_rule=rule,evidence=evidence,
            review_reason=review,analysis_ready=not bool(review),country_corrected=(cc!=SCOPE.get(n['country'],n['country'])))
        mapped.append(row)
    # Each final city has a single point representation, independent of its source nodes.
    grouped=defaultdict(list)
    for row in mapped:grouped[row['city_id']].append(row)
    for city_id, group in grouped.items():
        points=[(float(r['city_latitude']),float(r['city_longitude'])) for r in group if valid(r['city_latitude'],r['city_longitude'])]
        if points:
            lat,lon=np.median(points,axis=0)
            for row in group:row['city_latitude']=lat;row['city_longitude']=lon
    write(OUT/'city_crosswalk.csv',mapped)
    write(OUT/'audit/unresolved_places.csv',[r for r in mapped if not r['analysis_ready']])
    write(OUT/'audit/changed_city_records.csv',[r for r in mapped if r['merge_rule']!='retain_identified_place' or r['country_corrected'] or norm(r['raw_region'])!=norm(r['region'])])
    write(OUT/'cities.csv',[dict(city_id=k,country_code=g[0]['country_code'],country_name=g[0]['country_name'],
        region_code=g[0]['region_code'],region=g[0]['region'],city=g[0]['city'],city_geonameid=g[0]['city_geonameid'],
        latitude=g[0]['city_latitude'],longitude=g[0]['city_longitude'],source_place_instances=len(g),
        analysis_ready=any(r['analysis_ready'] for r in g)) for k,g in sorted(grouped.items())])
    summary=dict(raw_place_instances=len(raw),unique_cleaned_city_ids=len(grouped),
        match_methods=dict(Counter(r['match_method'] for r in mapped)),merge_rules=dict(Counter(r['merge_rule'] for r in mapped)),
        review_reasons=dict(Counter(r['review_reason'] for r in mapped if r['review_reason'])),
        country_corrections=sum(r['country_corrected'] for r in mapped),analysis_ready_place_instances=sum(r['analysis_ready'] for r in mapped))
    (OUT/'audit/crosswalk_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    c.close()


if __name__=='__main__':main()
