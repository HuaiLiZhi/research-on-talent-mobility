"""Validate city merges, independent-city safeguards, and exact flow accounting."""
from pathlib import Path
from collections import defaultdict
import csv
import json
import math
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import duckdb

OUT=ROOT/'data/processed/mobility_city_harmonized_20261020'


def rows(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def main():
    mapping=rows(OUT/'city_crosswalk.csv');assert len(mapping)==len({r['raw_place_id'] for r in mapping})
    assert all(r['raw_place_id'] for r in mapping)
    catalog=rows(OUT/'cities.csv');assert len(catalog)==len({r['city_id'] for r in catalog})
    by_name=defaultdict(set);meta=defaultdict(set);source_ids=defaultdict(set)
    for r in mapping:
        meta[r['city_id']].add((r['country_code'],r['region'],r['city']))
        if r['analysis_ready']=='True':
            by_name[r['raw_country'],r['raw_region'],r['raw_city']].add(r['city_id'])
            if r['source_geonameid']:source_ids[r['source_geonameid']].add(r['city_id'])
            assert r['review_reason']==''
            assert not (r['source_feature_code']=='PPLX' and r['merge_rule']=='retain_identified_place')
    assert all(len(v)==1 for v in meta.values())
    assert all(len(v)==1 for v in source_ids.values())
    def get(cc,name,region=None):
        got=set().union(*(v for (country,reg,city),v in by_name.items() if country==cc and city==name and (region is None or region==reg)))
        assert len(got)==1,(cc,region,name,got)
        return next(iter(got))
    merged=[('US','new york',['brooklyn','manhattan','the bronx','staten island']),
            ('US','san diego',['la jolla']),('CN','shanghai',['pudong']),('CN','nanjing',['jiangning']),
            ('CA','toronto',['etobicoke','north york','scarborough']),('AU','melbourne',['parkville','carlton']),
            ('DE','planegg',['martinsried'])]
    tests=[]
    for cc,parent,children in merged:
        if cc=='US' and parent=='new york':
            key=get(cc,parent,'new york')
            assert all(get(cc,child,'new york')==key for child in children)
        else:
            key=get(cc,parent);assert all(get(cc,child)==key for child in children)
        tests.append(dict(country=cc,parent=parent,components=children,pass_check=True))
    for cc,name in [('GB','london'),('DE','berlin'),('JP','tokyo')]:get(cc,name)
    safeguards=[get('US','cambridge','massachusetts')!=get('US','cambridge','maryland'),
        get('US','manhattan','kansas')!=get('US','manhattan','new york'),
        get('US','beverly hills')!=get('US','los angeles'),
        get('JP','osaka')!=get('JP','suita'),get('FR','paris')!=get('FR','orsay'),
        get('DE','planegg')!=get('DE','munich')]
    assert all(safeguards)
    c=duckdb.connect();c.execute("set threads=2;set memory_limit='1GB'")
    accounting=json.loads((OUT/'audit/event_accounting.json').read_text(encoding='utf-8'))
    for item in accounting:
        path=OUT/item['output_parquet'];c.read_parquet(str(path)).create_view('clean')
        assert c.execute("select count(*) from clean where from_city_id=to_city_id or mobility_count<=0 or year<1998 or year>2025 or from_country_code is null or to_country_code is null").fetchone()[0]==0
        assert c.execute('''select count(*) from (select year,tier,field_display_name,from_city_id,to_city_id,count(*) n
            from clean group by all having n>1)''').fetchone()[0]==0
        clean={t:float(v) for t,v in c.execute('select tier,sum(mobility_count) from clean group by 1').fetchall()}
        parts=defaultdict(float);expected=defaultdict(float)
        for r in item['classification']:
            parts[r['tier']]+=r['events']
            if r['event_status'] in ['international','domestic_intercity']:expected[r['tier']]+=r['events']
        for before in item['before']:
            assert parts[before['tier']]==before['events']
            assert clean.get(before['tier'],0)==expected[before['tier']]
    # Compare against the currently used tables without changing either set.
    old=rows(ROOT/'results/figure_revision_20261015/unified_country_scope/data/domestic_city_margins.csv')
    old_counts=defaultdict(int)
    for r in old:old_counts[r['country'],int(r['year']),r['side']]+=1
    new=rows(OUT/'analysis/domestic_country_city_counts.csv');comparison=[]
    for r in new:
        key=r['country'],int(r['year']),r['side']
        comparison.append(dict(country=r['country'],year=r['year'],side=r['side'],
            existing_count=old_counts.get(key,0),cleaned_count=int(r['cities']),cleaned_flow=float(r['flow']),
            count_change=int(r['cities'])-old_counts.get(key,0)))
    with (OUT/'audit/country_city_counts_before_after.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(comparison[0]));w.writeheader();w.writerows(comparison)
    qa=dict(raw_place_ids_unique=True,city_catalog_unique=True,one_metadata_record_per_city=True,
        no_identified_geonames_place_split=True,confirmed_component_merge_tests=tests,
        independent_city_safeguards=len(safeguards),all_independent_city_safeguards_passed=True,
        flow_conservation_all_datasets_and_tiers=True,clean_files_have_no_self_loops_or_duplicate_od_keys=True,
        comparison_scope='Counts reflect both geographic harmonization and explicit exclusion of records needing review; country repairs may restore previously omitted flows',
        selected_2025_counts=[r for r in comparison if r['year']=='2025' and r['side']=='inflow' and r['country'] in ['US','DE','GB','JP','CN','AU','CA','FR']])
    (OUT/'audit/validation.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(qa,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
