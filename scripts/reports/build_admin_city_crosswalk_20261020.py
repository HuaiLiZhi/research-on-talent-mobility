"""A strict municipal-boundary crosswalk; unresolved units never pass as cities.

This extends the earlier place crosswalk without overwriting it. Source place
identity and municipal-boundary identity are separate checks. A populated-place
feature by itself is not evidence of an independent municipality.
"""
from pathlib import Path
from collections import Counter,defaultdict
import csv,hashlib,json,math,re,sys,unicodedata,zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb,numpy as np,pyogrio,pycountry
from pyproj import Transformer
from shapely import from_wkb,make_valid,union_all
from shapely.geometry import Point
from shapely.ops import transform
from shapely.strtree import STRtree

OLD=ROOT/'data/processed/mobility_city_harmonized_20261020'
OUT=ROOT/'data/processed/mobility_admin_city_20261020'
REF=ROOT/'data/raw/geo/municipal_20261020'
SCOPE=json.loads((ROOT/'results/figure_revision_20261015/unified_country_scope/data_manifest.json').read_text(encoding='utf8'))['country_mapping']

def norm(s):
    return re.sub('[^a-z0-9]','', ''.join(c for c in unicodedata.normalize('NFKD',str(s)).lower() if not unicodedata.combining(c)))

def clean_label(text):
    original=str(text);current=original
    for _ in range(2):
        for encoding in ['latin1','cp1252']:
            try:
                repaired=current.encode(encoding).decode('utf8')
                if repaired!=current:current=repaired;break
            except (UnicodeError,LookupError):pass
        else:break
    return {'Greater Sudbury / Grand Sudbu*':'Greater Sudbury',
            'Distrito Especial, Industrial Y Portuario De Barr*':'Barranquilla'}.get(current,current)


def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def write(p,rows):
    if not rows:return
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def dist(a,b,c,d):
    try:
        a,b,c,d=map(float,[a,b,c,d])
        if not (-90<=a<=90 and -180<=b<=180 and -90<=c<=90 and -180<=d<=180):return float('inf')
        if a==b==0:return float('inf')
        a,b,c,d=map(math.radians,[a,b,c,d])
        return 12742*math.asin(math.sqrt(min(1,math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2)))
    except (TypeError,ValueError):return float('inf')

def shapes(path):
    if path.suffix=='.zip':
        with zipfile.ZipFile(path) as z:member=next(n for n in z.namelist() if n.endswith('.shp'))
        uri='/vsizip/'+path.resolve().as_posix()+'/'+member
    else:uri=str(path)
    meta,_,geometry,columns=pyogrio.raw.read(uri)
    crs=meta['crs'];gs=from_wkb(geometry)
    if crs not in ['EPSG:4326','EPSG:4269','EPSG:7844','EPSG:6668','EPSG:4612']:
        converter=Transformer.from_crs(crs,4326,always_xy=True)
        gs=[transform(converter.transform,g) if g is not None else None for g in gs]
    fields=list(meta['fields'])
    return [(dict(zip(fields,vs)),g) for vs,g in zip(zip(*columns),gs) if g is not None and not g.is_empty]

def load_us_status(path):
    with zipfile.ZipFile(path) as z, z.open(z.namelist()[0]) as f:
        text=f.read().decode('utf-8-sig').splitlines()
    return {r['GEOID'].strip():r['FUNCSTAT'].strip() for r in csv.DictReader(text,delimiter='\t')}

def main():
    OUT.mkdir(exist_ok=True);(OUT/'audit').mkdir(exist_ok=True)
    old=read(OLD/'city_crosswalk.csv')
    c=duckdb.connect();c.execute("SET threads=4;SET memory_limit='3GB'")
    c.execute("ATTACH '"+str(ROOT/'data/raw/geo/geonames_20261020/reference.duckdb').replace("'","''")+"' AS ref (READ_ONLY)")
    c.read_csv(str(OLD/'city_crosswalk.csv'),all_varchar=True).create_view('cw')
    c.execute("CREATE TEMP TABLE relevant_gaz AS SELECT g.* FROM ref.gaz g WHERE g.geonameid IN (SELECT try_cast(source_geonameid as bigint) FROM cw)")
    gaz={r['geonameid']:r for r in c.execute('SELECT * FROM relevant_gaz').fetchdf().to_dict('records')}
    # A coordinate-inconsistent old match gets an exact-name/coordinate retry.
    c.execute("CREATE TEMP TABLE raw_names AS SELECT raw_place_id,coalesce(raw_country,'') cc,regexp_replace(lower(strip_accents(raw_city)),'[^a-z0-9]','','g') nk FROM cw WHERE coalesce(raw_city,'')<>''")
    c.execute("""CREATE TEMP TABLE name_matches AS
       SELECT r.raw_place_id,g.* FROM raw_names r JOIN ref.gaz g ON g.country=r.cc AND g.name_key=r.nk WHERE length(r.nk)>1
       UNION
       SELECT r.raw_place_id,g.* FROM raw_names r JOIN ref.gaz g ON g.country=r.cc AND g.ascii_key=r.nk WHERE length(r.nk)>1
       UNION
       SELECT r.raw_place_id,g.* FROM raw_names r JOIN ref.gaz g ON g.name_key=r.nk WHERE r.cc='' AND length(r.nk)>1
       UNION
       SELECT r.raw_place_id,g.* FROM raw_names r JOIN ref.gaz g ON g.ascii_key=r.nk WHERE r.cc='' AND length(r.nk)>1""")
    candidates=defaultdict(list)
    for r in c.execute('SELECT * FROM name_matches').fetchdf().to_dict('records'):
        candidates[r['raw_place_id']].append(r);gaz[r['geonameid']]={k:v for k,v in r.items() if k!='raw_place_id'}
    region_modes=defaultdict(Counter)
    for r in old:
        g=gaz.get(int(r['source_geonameid'])) if r['source_geonameid'] else None
        if g and r['raw_region'] and r['analysis_ready']=='True':region_modes[g['country'],norm(r['raw_region'])][g['admin1']]+=1
    identities={};identity_audit=[]
    for r in old:
        rid=r['raw_place_id'];g=gaz.get(int(r['source_geonameid'])) if r['source_geonameid'] else None
        d=dist(r['raw_latitude'],r['raw_longitude'],g['latitude'],g['longitude']) if g else float('inf')
        corrected=False
        if g is None or d>20:
            choices=[]
            for q in candidates[rid]:
                e=dist(r['raw_latitude'],r['raw_longitude'],q['latitude'],q['longitude'])
                modes=region_modes[q['country'],norm(r['raw_region'])]
                region_ok=not modes or q['admin1']==modes.most_common(1)[0][0]
                if e<=10 and region_ok:
                    choices.append((e,0 if q['feature_class']=='P' else 1,-int(q['population'] or 0),q))
            choices.sort(key=lambda v:v[:3])
            if choices and (len(choices)==1 or choices[1][0]>choices[0][0]+.5 or choices[0][0]<=1):
                g=choices[0][3];d=choices[0][0];corrected=True
        ready=bool(g and d<=20)
        # Missing coordinates cannot establish boundary membership.
        identities[rid]=dict(g=g,ready=ready,distance_km=d,corrected=corrected)
        identity_audit.append(dict(raw_place_id=rid,raw_city=r['raw_city'],raw_country=r['raw_country'],
            previous_geonameid=r['source_geonameid'],geonameid=g['geonameid'] if g else '',
            distance_km=d if math.isfinite(d) else '',corrected=corrected,identity_ready=ready))
    write(OUT/'audit/place_identity_review.csv',identity_audit)
    print('Identity review',sum(v['ready'] for v in identities.values()),'ready;',sum(v['corrected'] for v in identities.values()),'corrected',flush=True)

    units={};geoms={};country_rules=[]
    def add(key,cc,name,geometry,provider,source_url,year,kind='municipality',region='',extra=''):
        if geometry is None or geometry.is_empty:return
        if not geometry.is_valid:geometry=make_valid(geometry)
        if geometry.geom_type=='GeometryCollection':
            # Topology repair may retain stray boundary lines. They are not
            # municipal territory and have no polygon boundary of their own.
            def polygon_parts(g):
                if g.geom_type in ['Polygon','MultiPolygon']:return [g]
                if hasattr(g,'geoms'):return [p for q in g.geoms for p in polygon_parts(q)]
                return []
            geometry=union_all(polygon_parts(geometry))
        if geometry.is_empty or geometry.geom_type not in ['Polygon','MultiPolygon']:return
        if key in geoms:geoms[key]=union_all([geoms[key],geometry]);return
        rp=geometry.representative_point()
        units[key]=dict(city_id=key,source_country=cc,country_code=SCOPE.get(cc,cc),city=clean_label(name),
            region=region,region_code='',city_geonameid='',latitude=rp.y,longitude=rp.x,
            municipal_unit_type=kind,provider=provider,evidence=source_url,reference_year=str(year),extra=extra,boundary_label_as_supplied=str(name))
        geoms[key]=geometry

    print('Loading European LAU boundaries',flush=True)
    eu=shapes(REF/'EU_LAU_2024_4326.gpkg')
    for props,g in eu:
        cc=str(props['CNTR_CODE']);cc={'EL':'GR','UK':'GB'}.get(cc,cc)
        # These LAU layers are below the municipal tier or electoral areas.
        if cc in ['GR','IE']:continue
        code=str(props['GISCO_ID']);name=str(props['LAU_NAME'])
        if cc=='PT':
            local=code.split('_',1)[1]
            code='PT_'+local[:4];name='Municipality '+local[:4]
        if cc=='HU' and name.lower().startswith('budapest'):
            code='HU_BUDAPEST';name='Budapest'
        if cc=='SK' and re.match(r'^(Bratislava|Košice)\s*[-–]',name):
            name=re.split(r'\s*[-–]',name)[0];code='SK_'+norm(name)
        if cc=='RO' and ('sector' in name.lower() and 'bucure' in name.lower()):
            code='RO_BUCURESTI';name='Bucureşti'
        add('municipal:EU2024:'+code,cc,name,g,'Eurostat GISCO LAU 2024',
            'https://gisco-services.ec.europa.eu/distribution/v2/lau/',2024)
    eu_countries=sorted({u['source_country'] for u in units.values()})
    country_rules.extend(dict(country=cc,unit='municipality / country-specific LAU municipal aggregation',
        source='Eurostat GISCO LAU 2024',verification='official polygons; Greece and Ireland require separate municipal tier') for cc in eu_countries)

    print('Loading US active municipal boundaries',flush=True)
    place_status=load_us_status(REF/'2024_Gaz_place_national.zip')
    for p,g in shapes(ROOT/'data/raw/geo/us_census_places_2024/cb_2024_us_place_500k.zip'):
        code=str(p['GEOID'])
        if place_status.get(code) not in ['A','B','C']:continue
        add('municipal:US_place2024:'+code,'US',p['NAME'],g,'US Census 2024 active incorporated place',
            'https://www.census.gov/geographies/mapping-files/2024/geo/carto-boundary-file.html',2024,
            region=str(p.get('STATE_NAME','')),extra='active incorporated municipal place; statistical CDPs excluded')
    mcd_status=load_us_status(REF/'2024_Gaz_cousubs_national.zip')
    for p,g in shapes(REF/'US_COUSUB_2024.zip'):
        code=str(p['GEOID'])
        if mcd_status.get(code) not in ['A','B','C']:continue
        add('municipal:US_mcd2024:'+code,'US',p['NAME'],g,'US Census 2024 active governmental MCD',
            'https://www.census.gov/library/reference/code-lists/functional-status-codes.html',2024,
            kind='governmental town/township',region=str(p.get('STATE_NAME','')),
            extra='active general-purpose governmental unit; incorporated place has priority in overlaps')
    country_rules.append(dict(country='US',unit='active incorporated place; otherwise active governmental town/township',
        source='Census 2024 places + MCD polygons + FUNCSTAT',verification='CDPs and statistical county divisions excluded'))

    print('Loading Australian LGAs',flush=True)
    for p,g in shapes(REF/'AU_LGA_2025.zip'):
        name=str(p['LGA_NAME25'])
        if 'unincorporated' in name.lower() or 'no usual' in name.lower() or 'migratory' in name.lower():continue
        add('municipal:AU_LGA2025:'+str(p['LGA_CODE25']),'AU',name,g,'ABS LGA 2025',
            'https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/',2025,
            region=str(p['STE_NAME21']),extra='statistical approximation of gazetted municipal boundaries')
    country_rules.append(dict(country='AU',unit='local government area',source='ABS LGA 2025',
        verification='non-incorporated statistical regions excluded; ACT separately requires municipal-equivalent evidence'))

    print('Loading Brazilian municipios',flush=True)
    for p,g in shapes(REF/'BR_Municipios_2024.zip'):
        code=str(p['CD_MUN'])
        if code in ['4300001','4300002']:continue
        add('municipal:BR_IBGE2024:'+code,'BR',p['NM_MUN'],g,'IBGE 2024 municipal mesh',
            'https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html',2024,
            region=str(p.get('NM_UF','')))
    country_rules.append(dict(country='BR',unit='municipio / Federal District',source='IBGE municipal mesh 2024',verification='official polygons'))

    print('Loading Japanese municipalities; dissolve designated-city wards',flush=True)
    jp_groups=defaultdict(list);jp_props={}
    for p,g in shapes(REF/'JP_N03_2025.zip'):
        prefecture=str(p.get('N03_001') or '');name=str(p.get('N03_004') or '')
        if not name or name=='None':continue
        group=(prefecture,name);jp_groups[group].append(g);jp_props[group]=p
    for (prefecture,name),polygons in jp_groups.items():
        p=jp_props[prefecture,name]
        add('municipal:JP_N032025:'+prefecture+':'+name,'JP',name,union_all(polygons),'MLIT N03 2025',
            'https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N03-2025.html',2025,region=prefecture,
            extra='N03_004 municipality retained; N03_005 designated-city wards dissolved; Tokyo special wards are independent local authorities')
    country_rules.append(dict(country='JP',unit='municipality; designated-city wards merged; Tokyo special wards retained',
        source='MLIT N03 2025',verification='official polygons; generic Tokyo labels cannot identify a special ward'))

    print('Loading UK local-authority municipal equivalents',flush=True)
    gb_meta=json.loads((REF/'GB_ONS_metadata.json').read_text(encoding='utf8'))
    for p,g in shapes(REF/'GB_LAD2024.geojson'):
        add('municipal:GB_LAD2024:'+str(p['LAD24CD']),'GB',p['LAD24NM'],g,
            'ONS Local Authority Districts December 2024 BGC',gb_meta['item']['url'],2024,
            kind='municipal-equivalent local authority district',extra='generic London labels require institution-level disambiguation')
    country_rules.append(dict(country='GB',unit='local authority district / municipal equivalent',
        source='ONS Local Authority Districts December 2024',verification='official ONS polygons; generic London not assigned to an arbitrary borough'))

    from municipal_reference_extensions_20261020 import load as load_extensions
    load_extensions(add,shapes,REF,country_rules,norm)

    # Seoul and other Korean metropolitan cities exist as city governments;
    # their internal gu are not independent neighbouring cities.
    korean_cities={'Seoul','Busan','Daegu','Incheon','Gwangju','Daejeon','Ulsan','Sejong'}
    korean_city_geometries=[]
    for p,g in shapes(REF/'gb_KOR_ADM1.geojson'):
        if p['shapeName'] in korean_cities:
            korean_city_geometries.append(g)
            add('municipal:KR_metropolitan:'+norm(p['shapeName']),'KR',p['shapeName'],g,
                'geoBoundaries Korean metropolitan-city boundary mirror; Natural Earth',
                'https://www.geoboundaries.org/api/current/gbOpen/KOR/ADM1/',2021,
                extra='metropolitan city government; internal gu merged to city')
    # South African metropolitan municipalities have no lower local-municipal tier.
    za_metros={'Buffalo City','City of Cape Town','City of Johannesburg','City of Tshwane',
        'Ekurhuleni','eThekwini','Mangaung','Nelson Mandela Bay'}
    for p,g in shapes(REF/'gb_ZAF_ADM2.geojson'):
        if p['shapeName'] in za_metros:
            add('municipal:ZA_metropolitan:'+norm(p['shapeName']),'ZA',p['shapeName'],g,
                'geoBoundaries metropolitan municipality mirror; Municipal Demarcation Board',
                'https://www.geoboundaries.org/api/current/gbOpen/ZAF/ADM2/',2020,
                extra='metropolitan municipality, not district municipality')

    metadata=json.loads((REF/'geoboundaries_all_metadata.json').read_text(encoding='utf8'))
    print('Loading documented municipal reference mirrors',flush=True)
    for path in sorted(REF.glob('gb_*_ADM*.geojson')):
        _,iso,level=path.stem.split('_')
        # Downloaded diagnostic layers do not automatically become city layers.
        # These countries are handled through explicit country-specific rules.
        if iso in ['CHN','IND','RUS','IDN','NZL','SGP']:continue
        obj=pycountry.countries.get(alpha_3=iso)
        cc=obj.alpha_2 if obj else ''
        if not cc or cc in eu_countries or cc in ['US','AU','BR','JP']:continue
        if (iso,level) in [('KOR','ADM1'),('ZAF','ADM2')]:continue
        r=next(v for v in metadata if v['boundaryISO']==iso and v['boundaryType']==level)
        for p,g in shapes(path):
            name=str(p['shapeName'])
            if cc=='KR' and any(q.covers(g.representative_point()) for q in korean_city_geometries):continue
            if cc=='CA' and re.search('unorgani[sz]ed|regional district|territory without|non.municipal',name,re.I):continue
            add('municipal:gb:'+r['boundaryID']+':'+str(p['shapeID']),cc,name,g,
                'geoBoundaries municipal reference; '+r['boundarySource'],r['boundarySourceURL'],r['boundaryYearRepresented'],
                extra='secondary boundary mirror, not represented as an official new government release')
        country_rules.append(dict(country=cc,unit=r['boundaryCanonical'],source=r['boundarySource'],
            verification='secondary municipal-boundary reference; source year '+r['boundaryYearRepresented']))

    print('Indexing',len(units),'municipal units',flush=True)
    by_country=defaultdict(list)
    for key,u in units.items():by_country[u['source_country']].append(key)
    trees={cc:STRtree([geoms[k] for k in keys]) for cc,keys in by_country.items()}
    def hit(cc,lat,lon):
        if cc not in trees:return []
        try:point=Point(float(lon),float(lat))
        except (TypeError,ValueError):return []
        return [by_country[cc][int(i)] for i in trees[cc].query(point,predicate='intersects')]
    def resolve(keys,raw_name):
        if not keys:return None
        county_cities=[k for k in keys if k.startswith('municipal:CN_countycity:')]
        if county_cities:keys=county_cities
        # US active incorporated places precede overlapping governmental MCDs.
        if any(k.startswith('municipal:US_place') for k in keys):keys=[k for k in keys if k.startswith('municipal:US_place')]
        if len(keys)==1:return keys[0]
        exact=[k for k in keys if norm(units[k]['city'])==norm(raw_name)]
        return exact[0] if len(exact)==1 else None
    mapped=[];point_diagnostics=[]
    for r in old:
        item=identities[r['raw_place_id']];g=item['g'];target=None;review='';method=''
        if not item['ready']:
            review='place_identity_or_coordinate_unresolved'
        elif g['country'] not in trees:
            review='municipal_boundary_source_not_verified'
        else:
            cc=g['country'];raw_hits=hit(cc,r['raw_latitude'],r['raw_longitude']);ref_hits=hit(cc,g['latitude'],g['longitude'])
            first=resolve(raw_hits,r['raw_city']);second=resolve(ref_hits,g['name'])
            # A named incorporated city protects Calabasas-like errors in the gazetteer point.
            exact=[k for k in raw_hits if norm(units[k]['city'])==norm(r['raw_city'])]
            if cc=='US' and len(exact)==1 and exact[0].startswith('municipal:US_place'):
                target=exact[0];method='official_name_and_original_point'
            elif first and first==second:
                target=first;method='source_and_raw_points_same_municipality'
            elif first and not second and item['distance_km']<=2:
                target=first;method='original_point_boundary_with_identity_within_2km'
            elif first and second and first!=second:
                review='source_and_original_point_cross_municipal_boundary'
            else:review='point_not_in_verified_municipality_or_ambiguous_boundary'
            # Tokyo is not an existing municipality: its shared city point cannot resolve wards.
            if cc=='JP' and norm(r['raw_city']) in ['tokyo','tokyoto']:
                target=None;review='coarse_tokyo_label_requires_institution_address'
            if cc=='GB' and norm(r['raw_city']) in ['london','greaterlondon']:
                target=None;review='coarse_london_label_requires_institution_address'
            if target and cc=='CN':
                raw_point=Point(float(r['raw_longitude']),float(r['raw_latitude']))
                ref_point=Point(g['longitude'],g['latitude'])
                # DataV metadata do not reliably identify the coordinate datum.
                # Accept only membership invariant to a conservative 0.015-degree
                # displacement, exceeding the usual mainland map-coordinate offset.
                if min(geoms[target].boundary.distance(raw_point),geoms[target].boundary.distance(ref_point))<=.015:
                    target=None;review='map_coordinate_offset_or_city_boundary_requires_review'
            admin_min={'US':3,'AU':2,'CA':3,'BR':2,'JP':2,'KR':2,'AT':3,'BE':4,'BG':2,
                'CH':3,'CZ':3,'DE':4,'DK':2,'ES':3,'EE':2,'FI':3,'FR':4,'GR':3,'HR':2,
                'HU':3,'IT':3,'LT':2,'LU':3,'LV':2,'NL':2,'NO':2,'PL':3,'PT':2,'RO':2,
                'SE':2,'SI':1,'SK':3}
            rank=re.fullmatch(r'ADM([1-5])',g['feature_code'])
            if target and rank and int(rank.group(1))<admin_min.get(cc,1) and norm(r['raw_city'])!=norm(units[target]['city']):
                target=None;review='source_administrative_unit_coarser_than_municipality'
            point_diagnostics.append(dict(raw_place_id=r['raw_place_id'],raw_city=r['raw_city'],source_country=cc,
                raw_point_candidates=';'.join(raw_hits),reference_point_candidates=';'.join(ref_hits),
                assigned_municipality=target or '',review_reason=review))
        if target:
            u=units[target];country=pycountry.countries.get(alpha_2=u['country_code'])
            row=dict(r,source_geonameid=g['geonameid'],source_feature_code=g['feature_code'],
                city_id=target,country_code=u['country_code'],country_name=country.name if country else u['country_code'],
                city=u['city'],city_geonameid='',city_latitude=u['latitude'],city_longitude=u['longitude'],
                region=u['region'] or r['region'],region_code=u['region_code'],
                merge_rule='verified_municipal_boundary',evidence=u['evidence'],review_reason='',analysis_ready='True',
                country_corrected=str(u['country_code']!=SCOPE.get(r['raw_country'],r['raw_country'])),
                municipality_verified='True',municipal_unit_type=u['municipal_unit_type'],boundary_provider=u['provider'],
                boundary_year=u['reference_year'],boundary_match_method=method,identity_corrected=str(item['corrected']),
                previous_city_id=r['city_id'])
        else:
            row=dict(r,city_id='unverified:'+r['raw_place_id'],analysis_ready='False',review_reason=review,
                municipality_verified='False',municipal_unit_type='',boundary_provider='',boundary_year='',
                boundary_match_method='',identity_corrected=str(item['corrected']),previous_city_id=r['city_id'])
            if item['ready']:
                cc=SCOPE.get(g['country'],g['country']);obj=pycountry.countries.get(alpha_2=cc)
                row.update(source_geonameid=g['geonameid'],source_feature_code=g['feature_code'],
                    country_code=cc,country_name=obj.name if obj else cc)
        row['place_identity_ready']=str(item['ready'])
        row['country_analysis_ready']=str(bool(pycountry.countries.get(alpha_2=row['country_code'])) and
            row['review_reason']!='country_conflict_needs_review')
        row['place_audit_status']='verified_municipal_city' if target else 'unresolved'
        mapped.append(row)

    # A populated statistical community can be correctly identified without being
    # an incorporated municipality. Keep it explicitly outside the city sample.
    print('Checking nonmunicipal US statistical places',flush=True)
    cdp=[]
    for p,g in shapes(ROOT/'data/raw/geo/us_census_places_2024/cb_2024_us_place_500k.zip'):
        if str(p.get('LSAD',''))=='57':cdp.append((p,g))
    cdp_tree=STRtree([g for p,g in cdp])
    nonmunicipal=[]
    for row in mapped:
        if row['raw_country']!='US' or row['analysis_ready']=='True':continue
        item=identities[row['raw_place_id']];g=item['g']
        if not item['ready']:continue
        raw=Point(float(row['raw_longitude']),float(row['raw_latitude']));reference=Point(g['longitude'],g['latitude'])
        rh={int(i) for i in cdp_tree.query(raw,predicate='intersects')}
        gh={int(i) for i in cdp_tree.query(reference,predicate='intersects')}
        # Do not override a municipal conflict or an active town/township match.
        if len(rh & gh)!=1 or hit('US',raw.y,raw.x) or hit('US',reference.y,reference.x):continue
        i=next(iter(rh & gh));p,geometry=cdp[i]
        row.update(place_audit_status='verified_nonmunicipal_place',review_reason='verified_unincorporated_census_designated_place',
            evidence='https://www.census.gov/programs-surveys/bas/information/cdp.html',boundary_provider='US Census 2024 CDP (nonmunicipal)',
            boundary_year='2024',boundary_match_method='both_points_same_CDP_outside_active_municipality')
        nonmunicipal.append(dict(raw_place_id=row['raw_place_id'],raw_city=row['raw_city'],reference_CDP=p['NAME'],GEOID=p['GEOID'],
            latitude=row['raw_latitude'],longitude=row['raw_longitude'],decision='outside municipal city; do not merge to nearest city',evidence=row['evidence']))
    write(OUT/'audit/verified_nonmunicipal_places.csv',nonmunicipal)
    # One municipal ID always has one metadata record, regardless of raw region strings.
    grouped=defaultdict(list)
    for r in mapped:grouped[r['city_id']].append(r)
    catalog=[]
    for key,rs in grouped.items():
        if rs[0]['analysis_ready']=='True':
            region=Counter(r['region'] for r in rs if r['region']).most_common(1)
            region=region[0][0] if region else ''
            for r in rs:r['region']=region
        r=rs[0]
        catalog.append(dict(city_id=key,country_code=r['country_code'],country_name=r['country_name'],
            region_code=r['region_code'],region=r['region'],city=r['city'],city_geonameid=r['city_geonameid'],
            latitude=r['city_latitude'],longitude=r['city_longitude'],source_place_instances=len(rs),
            analysis_ready=r['analysis_ready'],municipality_verified=r['municipality_verified'],
            municipal_unit_type=r['municipal_unit_type'],boundary_provider=r['boundary_provider'],boundary_year=r['boundary_year']))
    write(OUT/'city_crosswalk.csv',mapped)
    write(OUT/'cities.csv',[r for r in catalog if r['analysis_ready']=='True'])
    write(OUT/'audit/place_catalog_including_unverified.csv',catalog)
    write(OUT/'audit/unresolved_places.csv',[r for r in mapped if r['analysis_ready']!='True'])
    write(OUT/'audit/point_boundary_checks.csv',point_diagnostics)
    write(OUT/'audit/country_municipal_rules.csv',country_rules)
    used={r['city_id'] for r in mapped if r['analysis_ready']=='True'}
    write(OUT/'audit/used_municipal_boundaries.csv',[units[k] for k in sorted(used)])
    # Store used boundaries so every accepted membership can be independently rechecked.
    accepted=sorted(used)
    with (OUT/'audit/used_municipal_boundaries.geojson').open('w',encoding='utf8') as f:
        from shapely.geometry import mapping
        json.dump(dict(type='FeatureCollection',features=[dict(type='Feature',properties=units[k],geometry=mapping(geoms[k])) for k in accepted]),f,ensure_ascii=False)
    summary=dict(raw_place_instances=len(mapped),verified_place_instances=sum(r['analysis_ready']=='True' for r in mapped),
        verified_nonmunicipal_place_instances=len(nonmunicipal),
        verified_municipalities=len(used),reference_countries=sorted(trees),
        identity_corrections=sum(v['corrected'] for v in identities.values()),
        review_reasons=dict(Counter(r['review_reason'] for r in mapped if r['review_reason'])),
        administrative_definition='An independently governed municipality/city or documented municipal equivalent; internal non-independent wards are dissolved',
        complete_global_verification=all(r['analysis_ready']=='True' for r in mapped),
        global_completion_rule='Cannot claim complete while any source identity, official municipal level, boundary membership, or coarse city label remains unresolved')
    (OUT/'audit/crosswalk_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    c.close()

if __name__=='__main__':main()

