"""Country-specific municipal tiers, with explicit exclusions and provenance."""
from pathlib import Path
from collections import defaultdict
import json, re
from shapely.geometry import shape
from shapely import union_all, make_valid

def load(add, shapes, ref, country_rules, norm):
    # Washington has no separate active city government because it is consolidated
    # with the District. FUNCSTAT=N alone is not a reason to exclude the city.
    source='https://www.census.gov/geographies/reference-files/2010/geo/state-local-geo-guides-2010/districtofcolumbia.html'
    for p,g in shapes(ref.parent/'us_census_places_2024/cb_2024_us_place_500k.zip'):
        if str(p['GEOID'])=='1150000':
            add('municipal:US_place2024:1150000','US','Washington',g,'US Census 2024 city coextensive with District',source,2024,
                kind='consolidated city / district government',region='District of Columbia',extra='FUNCSTAT N: municipal government provided by coextensive District; documented exception, not a CDP')
    if (ref/'US_COUNTY_2024.zip').exists():
        for p,g in shapes(ref/'US_COUNTY_2024.zip'):
            if str(p['GEOID'])=='15003':
                add('municipal:US_consolidated2024:15003','US','Honolulu',g,'US Census 2024 Honolulu consolidated city-county',
                    'https://www.census.gov/geographies/reference-files/2010/geo/state-local-geo-guides-2010/hawaii.html',2024,
                    kind='consolidated city-county',region='Hawaii',extra='documented municipal government coextensive with Honolulu County; other Hawaii counties are NOT automatically municipalities')

    ext=ref/'extension'
    if (ext/'CN_100000_full.json').exists():
        national=json.loads((ext/'CN_100000_full.json').read_text(encoding='utf8'))
        direct={110000,120000,310000,500000}
        for f in national['features']:
            p=f['properties']
            if p['adcode'] in direct:
                add('municipal:CN_direct:'+str(p['adcode']),'CN',p['name'],shape(f['geometry']),
                    'Alibaba DataV administrative map reference','https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json','retrieved 2026-10-20',
                    kind='direct-administered municipality',extra='secondary simplified map, source CRS not asserted; raw/reference membership must survive +/-0.015 degree boundary buffer')
        seen=set()
        for path in sorted(ext.glob('CN_*_full.json')):
            if path.name=='CN_100000_full.json':continue
            d=json.loads(path.read_text(encoding='utf8'))
            for f in d.get('features',[]):
                p=f['properties'];code=p.get('adcode');name=p.get('name','');level=p.get('level')
                if not name.endswith('市') or not isinstance(code,int) or code in seen:continue
                # Internal districts are never independent cities. County-level
                # cities keep priority over their containing prefectural city.
                if level not in ['city','district']:continue
                seen.add(code)
                kind='prefectural' if level=='city' else 'countycity'
                add('municipal:CN_'+kind+':'+str(code),'CN',name,shape(f['geometry']),
                    'Alibaba DataV administrative map reference','https://geo.datav.aliyun.com/areas_v3/bound/'+path.name[3:],'retrieved 2026-10-20',
                    kind=kind+' administrative city',extra='city names and six-digit adcodes retained; independent county-level cities take priority; district/community records map to containing city; conservative interior-membership requirement')
        country_rules.append(dict(country='CN',unit='direct-administered or prefectural city; independently administered county-level cities take priority; internal districts are not cities',
            source='Alibaba DataV GeoAtlas administrative map, retrieved 2026-10-20; secondary reference',
            verification='both source points inside same city and more than 0.015 degrees from boundary; boundary CRS offset sensitivity screened; non-city prefectures excluded'))

    if (ext/'NZ_TA2025.geojson').exists():
        data=json.loads((ext/'NZ_TA2025.geojson').read_text(encoding='utf8'))
        for f in data['features']:
            p=f['properties'];code=str(p.get('TA2025_V1_00',p.get('TA2025',p.get('TA2025_CODE',''))))
            name=p.get('TA2025_V1_00_NAME',p.get('TA2025_NAME',p.get('NAME','')))
            if not name or code=='999' or 'outside' in name.lower():continue
            add('municipal:NZ_TA2025:'+code,'NZ',name,shape(f['geometry']),'Stats NZ Territorial Authority 2025',
                'https://services2.arcgis.com/vKb0s8tBIA3bdocZ/arcgis/rest/services/Territorial_Authority_2025/FeatureServer',2025,
                kind='territorial authority',extra='official StatsNZGeospatial feature service; regional councils and community boards are not used')
        country_rules.append(dict(country='NZ',unit='territorial authority',source='Stats NZ Territorial Authority 2025',verification='official municipal-equivalent boundary polygons'))

    if (ext/'IE_LA2024.geojson').exists():
        data=json.loads((ext/'IE_LA2024.geojson').read_text(encoding='utf8'))
        groups=defaultdict(list);labels={}
        for f in data['features']:
            p=f['properties'];name=p.get('ENG_NAME_VALUE','')
            if not name:continue
            code=str(p['BDY_ID']);groups[code].append(make_valid(shape(f['geometry'])));labels[code]=name
        assert len(groups)==31,('Incomplete Irish authority download',len(groups))
        for code,geometries in groups.items():
            add('municipal:IE_LA2024:'+code,'IE',labels[code],union_all(geometries),'Tailte Eireann Local Authorities National Statutory Boundaries 2024',
                'https://services-eu1.arcgis.com/FH5XCsx8rYXqnjF5/arcgis/rest/services/LocalAuthorities_NationalStatutoryBoundaries_Ungeneralised_2024/FeatureServer',2024,
                kind='city/county local authority',extra='official national statutory authority boundaries; local electoral areas are not municipalities')
        country_rules.append(dict(country='IE',unit='city/county local authority',source='Tailte Eireann statutory boundaries 2024',verification='official local-authority layer; not the GISCO electoral-area layer'))

    # Indonesia: kota is a municipality; a kabupaten is NOT silently promoted.
    # Jakarta's five internal administrative cities have no autonomous government.
    jp=ref/'gb_IDN_ADM1.geojson'
    if jp.exists():
        for p,g in shapes(jp):
            if 'jakarta' in p['shapeName'].lower():
                add('municipal:ID_capital:jakarta','ID','Jakarta',g,'geoBoundaries Jakarta provincial-city boundary mirror',
                    'https://barat.jakarta.go.id/index.php/profil/sejarah',2017,kind='special capital municipal equivalent',
                    extra='five internal administrative cities and administrative regency are not autonomous local governments; province-city kept together')
    path=ref/'gb_IDN_ADM2.geojson'
    if path.exists():
        for p,g in shapes(path):
            name=p['shapeName']
            if not re.match(r'^Kota\s',name,re.I) or 'jakarta' in name.lower():continue
            add('municipal:ID_kota2020:'+str(p['shapeID']),'ID',re.sub(r'^Kota\s+','',name,flags=re.I),g,
                'geoBoundaries municipal mirror; BPS Indonesia / WFP / OCHA','https://www.geoboundaries.org/api/current/gbOpen/IDN/ADM2/',2020,
                extra='only Kota-labeled autonomous municipalities; regencies excluded')
        country_rules.append(dict(country='ID',unit='autonomous Kota; Jakarta special-capital city equivalent',source='BPS/geoBoundaries 2020 municipal reference; Jakarta official administrative explanation',verification='Kabupaten not promoted to city; Jakarta internal administrative cities dissolved'))

    path=ref/'gb_RUS_ADM1.geojson'
    if path.exists():
        for p,g in shapes(path):
            if p.get('shapeISO') not in ['RU-MOW','RU-SPE']:continue
            add('municipal:RU_federalcity:'+p['shapeISO'],'RU',p['shapeName'],g,'geoBoundaries / OpenStreetMap federal-city boundary mirror',
                'https://www.vsrf.ru/en/documents/constitution/',2017,kind='federal city',
                extra='only Moscow and Saint Petersburg city-subject polygons; Moscow Oblast and other oblasts are NOT cities')
        country_rules.append(dict(country='RU',unit='Moscow and Saint Petersburg federal cities only',source='geoBoundaries 2017 federal-city mirror; constitutional status',verification='other Russian cities still require suitable city boundaries; no oblast or raion promoted'))
    path=ref/'gb_SGP_ADM0.geojson'
    if path.exists():
        for p,g in shapes(path):
            add('municipal:SG_citystate','SG','Singapore',g,'geoBoundaries / URA city-state boundary reference',
                'https://www.mfa.gov.sg/about-singapore/',2016,kind='city-state',extra='planning areas and subzones are not independent cities')
        country_rules.append(dict(country='SG',unit='one city-state',source='URA/geoBoundaries 2016; Singapore MFA city-state definition',verification='planning areas not promoted to separate cities'))
