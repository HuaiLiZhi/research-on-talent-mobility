"""Validate municipal membership, independence safeguards and event accounting."""
from pathlib import Path
from collections import defaultdict,Counter
import csv,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb
OUT=ROOT/'data/processed/mobility_admin_city_20261020'

def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
    cw=read(OUT/'city_crosswalk.csv');catalog=read(OUT/'cities.csv')
    assert len(cw)==len({r['raw_place_id'] for r in cw})==16484
    assert len(catalog)==len({r['city_id'] for r in catalog})
    accepted=[r for r in cw if r['analysis_ready']=='True']
    assert all(r['municipality_verified']=='True' and r['city_id'].startswith('municipal:') and r['evidence'] for r in accepted)
    groups=defaultdict(list);gn=defaultdict(set)
    for r in accepted:
        groups[r['city_id']].append(r)
        if r['source_geonameid']:gn[r['source_geonameid']].add(r['city_id'])
    assert set(groups)=={r['city_id'] for r in catalog}
    assert all(r['analysis_ready']=='True' for r in catalog)
    assert all(len(v)==1 for v in gn.values()),'A source GeoNames identity still splits across accepted municipalities'
    fields=['country_code','city','region','region_code','city_latitude','city_longitude','boundary_year']
    assert all(len({tuple(r[k] for k in fields) for r in v})==1 for v in groups.values())
    def ids(cc,name):return {r['city_id'] for r in accepted if r['raw_country']==cc and r['raw_city']==name}
    # Independent spatial recheck against the archived reference polygons.
    from shapely.geometry import shape,Point
    polygons=json.loads((OUT/'audit/used_municipal_boundaries.geojson').read_text(encoding='utf8'))
    shapes={f['properties']['city_id']:shape(f['geometry']) for f in polygons['features']}
    assert all(shapes[r['city_id']].covers(Point(float(r['raw_longitude']),float(r['raw_latitude']))) for r in accepted)
    assert all(shapes[r['city_id']].boundary.distance(Point(float(r['raw_longitude']),float(r['raw_latitude'])))>.015
        for r in accepted if r['city_id'].startswith('municipal:CN_'))
    assert ids('US','washington d.c.')=={'municipal:US_place2024:1150000'}
    assert ids('US','honolulu')=={'municipal:US_consolidated2024:15003'}
    assert ids('CN','wuxi').isdisjoint(ids('CN','jiangyin')) and ids('CN','jiangyin')
    assert ids('CN','suzhou').isdisjoint(ids('CN','kunshan')) and ids('CN','kunshan')
    safeguards=[]
    for cc,a,b in [('US','calabasas','los angeles'),('US','beverly hills','los angeles'),
                  ('JP','osaka','suita'),('DE','martinsried','munich'),('FR','paris','orsay')]:
        first,second=ids(cc,a),ids(cc,b)
        ok=bool(first and second and first.isdisjoint(second))
        assert ok,(cc,a,b,first,second)
        safeguards.append(dict(country=cc,places=[a,b],independent_municipalities_preserved=True))
    merges=[]
    for cc,children in [('AU',['parkville','carlton']),('CA',['toronto','north york','scarborough'])]:
        sets=[ids(cc,x) for x in children]
        assert all(sets) and len(set.union(*sets))==1,(cc,children,sets)
        merges.append(dict(country=cc,components=children,one_municipal_id=True))
    halle={r['city_id'] for r in accepted if r['previous_city_id'] in ['gn:2911522','gn:6551220']}
    assert len(halle)==1
    assert ids('NL','the hague')
    assert all(r['analysis_ready']=='False' for r in cw if r['review_reason'].startswith('coarse_tokyo_') or r['review_reason'].startswith('coarse_london_'))
    c=duckdb.connect();c.execute("SET threads=4;SET memory_limit='2GB'")
    accounting=[]
    for dataset in ['annual','career','baseline']:
        original=ROOT/'data/processed/mobility_city_harmonized_20261020/audit'/f'full_event_ledger_{dataset}.parquet'
        current=OUT/'audit'/f'full_event_ledger_{dataset}.parquet'
        before=c.execute('SELECT tier,sum(flow),sum(original_aggregate_rows) FROM read_parquet(?) GROUP BY tier ORDER BY tier',[str(original)]).fetchall()
        after=c.execute('SELECT tier,sum(flow),sum(original_aggregate_rows) FROM read_parquet(?) GROUP BY tier ORDER BY tier',[str(current)]).fetchall()
        assert before==after
        clean=OUT/f'mobility_{dataset}_admin_city_verified.parquet'
        invalid=c.execute("SELECT count(*) FROM read_parquet(?) WHERE from_city_id=to_city_id OR mobility_count<=0 OR NOT starts_with(from_city_id,'municipal:') OR NOT starts_with(to_city_id,'municipal:')",[str(clean)]).fetchone()[0]
        duplicate=c.execute('SELECT count(*) FROM (SELECT year,tier,field_display_name,from_city_id,to_city_id,count(*) n FROM read_parquet(?) GROUP BY ALL HAVING n>1)',[str(clean)]).fetchone()[0]
        assert invalid==duplicate==0
        ledger=c.execute("SELECT tier,sum(flow) FROM read_parquet(?) WHERE event_status IN ('international','domestic_intercity') GROUP BY tier ORDER BY tier",[str(current)]).fetchall()
        totals=c.execute('SELECT tier,sum(mobility_count) FROM read_parquet(?) GROUP BY tier ORDER BY tier',[str(clean)]).fetchall()
        assert ledger==totals
        accounting.append(dict(dataset=dataset,tiers=len(before),event_counts_and_original_rows_conserved=True,strict_output_matches_verified_ledger=True,no_self_loops_or_duplicate_od_keys=True))
    file=OUT/'audit/full_event_ledger_annual.parquet'
    totals=c.execute("SELECT event_status,sum(flow) events FROM read_parquet(?) WHERE tier='top100pct' GROUP BY event_status ORDER BY event_status",[str(file)]).fetchdf().to_dict('records')
    overall=sum(r['events'] for r in totals)
    assert overall==30335569
    included=sum(r['events'] for r in totals if r['event_status'] in ['international','domestic_intercity'])
    verified_with_internal=sum(r['events'] for r in totals if r['event_status'] in ['international','domestic_intercity','within_same_municipality'])
    n_countries=len({r['country_code'] for r in accepted})
    unresolved=[r for r in cw if r['analysis_ready']!='True']
    truly_unresolved=[r for r in cw if r['place_audit_status']=='unresolved']
    nonmunicipal=[r for r in cw if r['place_audit_status']=='verified_nonmunicipal_place']
    assert len(accepted)+len(truly_unresolved)+len(nonmunicipal)==len(cw)
    assert not any(r['analysis_ready']=='True' for r in nonmunicipal)
    nonmunicipal_audit=read(OUT/'audit/verified_nonmunicipal_places.csv')
    assert {r['raw_place_id'] for r in nonmunicipal_audit}=={r['raw_place_id'] for r in nonmunicipal}
    from build_admin_city_crosswalk_20261020 import shapes as read_reference_shapes
    codes={r['GEOID'] for r in nonmunicipal_audit}
    cdp={str(p['GEOID']):g for p,g in read_reference_shapes(ROOT/'data/raw/geo/us_census_places_2024/cb_2024_us_place_500k.zip')
        if str(p['GEOID']) in codes and str(p['LSAD'])=='57'}
    assert len(cdp)==len(codes)
    assert all(cdp[r['GEOID']].covers(Point(float(r['longitude']),float(r['latitude']))) for r in nonmunicipal_audit)
    report=dict(raw_place_instances=len(cw),accepted_place_instances=len(accepted),unresolved_place_instances=len(truly_unresolved),
        non_city_matched_place_instances=len(unresolved),
        verified_administrative_units=len(groups),accepted_country_count=n_countries,
        unresolved_place_instances_excluding_verified_nonmunicipal=len(truly_unresolved),
        verified_nonmunicipal_place_instances=len(nonmunicipal),
        stable_city_metadata=True,no_identified_place_split=True,all_accepted_original_points_inside_archived_boundaries=True,municipal_evidence_present_for_each_accepted_record=True,
        independent_city_safeguards=safeguards,confirmed_merges=merges,halle_duplicate_ids_unified=True,
        government_seat_not_misclassified_as_historical=True,
        coarse_london_tokyo_labels_not_assigned_to_arbitrary_district=True,
        washington_consolidated_government_exception_verified=True,
        honolulu_consolidated_city_county_exception_verified=True,
        chinese_independent_county_level_cities_preserved=True,
        nonmunicipal_places_independently_rechecked_against_Census_CDP_boundaries=True,
        chinese_map_coordinate_boundary_sensitivity_screen_passed=True,
        tier_accounting=accounting,top100_event_status=totals,original_top100_events=overall,
        verified_intercity_events=included,verified_including_same_city_events=verified_with_internal,
        verified_intercity_fraction_of_original=included/overall,
        review_reasons=dict(Counter(r['review_reason'] for r in truly_unresolved)),
        verified_nonmunicipal_reasons=dict(Counter(r['review_reason'] for r in nonmunicipal)),
        global_city_standardization_complete=not truly_unresolved,
        global_replacement_gate='PASS' if not unresolved else 'NOT READY: unresolved source identities, administrative boundaries and coarse institution locations remain')
    (OUT/'audit/validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
