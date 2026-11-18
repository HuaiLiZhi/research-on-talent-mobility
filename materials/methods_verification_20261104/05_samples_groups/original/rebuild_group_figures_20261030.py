"""Preserve the manuscript figure templates and update descriptive memberships."""
from pathlib import Path
import sys,json,shutil,subprocess
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps')]
import pandas as pd,numpy as np
OUT=ROOT/'outputs/results_network_revision_20261030'
BUILD=OUT/'artwork';BUILD.mkdir(exist_ok=True)
SOURCES=OUT/'plot_sources';SOURCES.mkdir(exist_ok=True)
(BUILD/'source_data').mkdir(exist_ok=True);(BUILD/'QA').mkdir(exist_ok=True)
COLORS={1:'#7E99F4',2:'#A5AEB7',3:'#7AB656',4:'#CC7C71'}
groups=pd.read_csv(ROOT/'outputs/tier_role_audit_20261030/sign_and_nested_display_proposal.csv')
groups['group']=groups.nested_display_group.str[1:].astype(int)
groups['international_share_log_slope']=groups.log_share_slope
groups['international_share_annual_rate_pct']=groups.share_growth_pct
groups['color']=groups.group.map(COLORS)
GROUP=BUILD/'source_data/trajectory_membership.csv';groups.to_csv(GROUP,index=False)

def adapt3():
    source=(ROOT/'figures/v4/plot_fig3.py').read_text(encoding='utf8')
    source=source.replace("ROOT=Path(__file__).resolve().parents[2];V3=ROOT/'figures/v3'",f"ROOT=Path({str(ROOT.as_posix())!r});V3=ROOT/'figures/v3'")
    source=source.replace("OUT=output_root(Path(__file__).resolve().parent);DATA=OUT/'source_data';QA=OUT/'QA/Fig3'",f"OUT=Path({str(BUILD.as_posix())!r});DATA=OUT/'source_data';QA=OUT/'QA/Fig3'")
    source=source.replace("FIG5_GROUPS=V3/'source_data/Fig5_stratified_country_trends.csv'",f"FIG5_GROUPS=Path({str(GROUP.as_posix())!r})")
    source=source.replace('GROUP_COLORS=[BLUE,GRAY,GREEN,RED]',f'GROUP_COLORS={list(COLORS.values())!r}')
    start=source.index('def prepare():');end=source.index('\ndef group_total_shares',start)
    replacement='''def prepare():
    observations=read(ROOT/'figures/v4/source_data/Fig3_combined_country_year_data.csv')
    for r in observations:
        for k in list(r):
            if k!='country':r[k]=int(r[k]) if k=='year' else float(r[k])
    metrics=read(ROOT/'figures/v4/source_data/Fig3_combined_country_metrics.csv')
    for r in metrics:
        for k in list(r):r[k]=int(r[k]) if k in ['year','countries'] else float(r[k])
    lorenz=read(ROOT/'figures/v4/source_data/Fig3_combined_lorenz_curves.csv')
    groups=[]
    for r in read(FIG5_GROUPS):
        groups.append(dict(country=r['country'],group=int(r['group']),international_share_log_slope=float(r['international_share_log_slope']),international_share_annual_rate_pct=float(r['international_share_annual_rate_pct'])))
    assert [sum(r['group']==g for r in groups) for g in range(1,5)]==[15,14,24,23]
    quartile_rows=[];stats=[]
    for year in range(1998,2026):
        total=next(r['combined_flow_endpoints'] for r in metrics if r['year']==year)
        for r in groups:
            events=next(v['combined_flow'] for v in observations if v['country']==r['country'] and v['year']==year)
            quartile_rows.append(dict(country=r['country'],group=r['group'],year=year,country_combined_flow=events,global_combined_flow=total,share_percent=100*events/total))
        for group in range(1,5):
            values=np.asarray([r['share_percent'] for r in quartile_rows if r['year']==year and r['group']==group])
            q1,median,q3=np.percentile(values,[25,50,75]);iqr=q3-q1;low=min(values[values>=q1-1.5*iqr]);high=max(values[values<=q3+1.5*iqr])
            stats.append(dict(group=group,year=year,countries=len(values),q1=float(q1),median=float(median),q3=float(q3),whisker_low=float(low),whisker_high=float(high),minimum=float(min(values)),maximum=float(max(values)),outlier_count=int(sum((values<low)|(values>high)))))
    from matplotlib.ticker import MaxNLocator
    ticks=MaxNLocator(nbins=5,steps=[1,2,2.5,5,10]).tick_values(0,max(r['median'] for r in stats)*1.08)
    globals()['LINE_YLIM']=(0.,float(ticks[-1]));globals()['LINE_YTICKS']=ticks.tolist()
    cuts=np.array([np.median([r['international_share_annual_rate_pct'] for r in groups if r['international_share_annual_rate_pct']<0]),0.,np.median([r['international_share_annual_rate_pct'] for r in groups if r['international_share_annual_rate_pct']>0])])
    write('Fig3_combined_country_year_data.csv',observations);write('Fig3_combined_country_metrics.csv',metrics)
    write('Fig3_combined_lorenz_curves.csv',lorenz);write('Fig3_Fig5_quartile_membership.csv',groups)
    write('Fig3_quartile_annual_shares.csv',quartile_rows);write('Fig3_quartile_box_statistics.csv',stats)
    return observations,metrics,lorenz,groups,quartile_rows,stats,cuts

'''
    source=source[:start]+replacement+source[end:]
    source=source.replace("a.set_yticks(LINE_YTICKS,['0','0.3','0.6','0.9','1.2','1.5'])","a.set_yticks(LINE_YTICKS,[f'{v:g}' for v in LINE_YTICKS])")
    source=source.replace('countries_per_group=19','countries_per_group=[15,14,24,23]').replace('Median of 19 country shares','Median of the country shares in each display group')
    source=source.replace("group-total stacked shares", "display-group total stacked shares")
    return source

def adapt4():
    source=(ROOT/'figures/v3/plot_fig4.py').read_text(encoding='utf8')
    source=source.replace('from pathlib import Path',f"from pathlib import Path\nsys.path[:0]=[{str((ROOT/'figures/v3').as_posix())!r},{str((ROOT/'tmp/nhb_fig2_python_deps').as_posix())!r}]")
    source=source.replace('ROOT=Path(__file__).resolve().parents[2]',f'ROOT=Path({str(ROOT.as_posix())!r})')
    source=source.replace('OUT=output_root(Path(__file__).resolve().parent)',f'OUT=Path({str(BUILD.as_posix())!r})')
    source=source.replace("ROOT/'figures/v3/source_data/Fig5_stratified_country_trends.csv'",f'Path({str(GROUP.as_posix())!r})')
    source=source.replace('assert [quartile_by_country[c] for c in CASE_COUNTRIES]==[1,2,3,4]','assert len(CASE_COUNTRIES)==4')
    source=source.replace('assert all(list(quartiles.values()).count(q)==19 for q in range(1,5))','assert [list(quartiles.values()).count(q) for q in range(1,5)]==[15,14,24,23]')
    source=source.replace('quartile_colors={1:BLUE,2:GRAY,3:GREEN,4:RED}',f'quartile_colors={COLORS!r}')
    source=source.replace('dict(group=q,countries=19,','dict(group=q,countries=list(quartiles.values()).count(q),')
    source=source.replace("ax.set_title(f'T{quartiles[cc]} {NAMES[cc]}'", "ax.set_title(f'{NAMES[cc]}'")
    source=source.replace('One country per Fig5 quartile','Four contrasting domestic trajectories')
    source=source.replace('one sufficiently observed case from each Fig5 quartile','four sufficiently observed contrasting domestic trajectories')
    return source

def adapt2():
    source=(ROOT/'figures/v3/plot_fig2_quartile_clusters.py').read_text(encoding='utf8')
    source=source.replace('import plot_fig2_quartile_growth as previous',f"import sys\nsys.path[:0]=[{str((ROOT/'figures/v3').as_posix())!r},{str((ROOT/'tmp/nhb_fig2_python_deps').as_posix())!r}]\nimport plot_fig2_quartile_growth as previous")
    injection=f'''
base.OUT=Path({str(BUILD.as_posix())!r});base.QA=base.OUT/'QA/Fig2'
def revised_prepare(source_out):
    raw=base.read(Path({str((ROOT/'figures/v3/source_data/Fig2_quartile_growth_country_year.csv').as_posix())!r}))
    group_rows=base.read(Path({str(GROUP.as_posix())!r}))
    membership={{r['country']:int(r['group']) for r in group_rows}}
    colours={COLORS!r}
    for r in raw:
        r['year']=int(r['year']);r['group']=membership[r['country']];r['colour']=colours[r['group']]
        for k in ['international_flow','partner_countries','domestic_flow','domestic_cities']:r[k]=float(r[k])
    base.write(Path(source_out)/'Fig2_quartile_growth_country_year.csv',raw)
    return raw,membership,colours
previous.prepare=revised_prepare
'''
    source=source.replace('base=previous.base','base=previous.base\n'+injection)
    start=source.index('            boundary,region=central_region(values)')
    stop=source.index('            marks=ax.scatter',start)
    source=source[:start]+"            boundary=np.empty((0,2));region=dict(countries=len(rows),dispersion_outline=False)\n"+source[stop:]
    source=source.replace("countries=19,colour=colours[g]","countries=sum(r['group']==g for r in summaries),colour=colours[g]")
    source=source.replace("region='Descriptive central13/19 data ellipse,not confidence interval'","region='No ellipse; group colors are descriptive trajectory strata'")
    source=source.replace("base.write(Path(source_out)/'Fig2_quartile_country_regions.csv',boundaries)","# No dispersion regions are drawn or exported.")
    return source

def main():
    for source,dest in [(ROOT/'figures/v3/QA/figure_manifest.json',BUILD/'QA/figure_manifest.json')]:
        shutil.copy2(source,dest)
    chosen=set(map(int,sys.argv[1:])) if len(sys.argv)>1 else {2,3,4}
    for number,adapter in [(2,adapt2),(3,adapt3),(4,adapt4)]:
        if number not in chosen:continue
        script=SOURCES/f'plot_Fig{number}.py';script.write_text(adapter(),encoding='utf8')
        print('Rendering Fig'+str(number),flush=True)
        result=subprocess.run([sys.executable,'-X','utf8',str(script)],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
        (OUT/f'Fig{number}_render.log').write_text(result.stdout+'\n'+result.stderr,encoding='utf8')
        if result.returncode:print(result.stdout[-1500:]+result.stderr[-3000:]);raise SystemExit(result.returncode)
        print('Fig'+str(number)+' complete',flush=True)
    for ext in ['pdf','png','svg']:
        shutil.copy2(OUT/'before/figures'/f'Fig6.{ext}',BUILD/f'Fig5.{ext}')

if __name__=='__main__':main()
