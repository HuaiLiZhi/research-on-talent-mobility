"""Five-panel network comparison with annual conditional reconstructions."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tmp/nhb_fig2_python_deps'),str(Path(__file__).resolve().parents[2] / 'scripts/plots/paper_figures/qa')]
import numpy as np,pandas as pd
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator,FormatStrFormatter
from audit_panel_alignment import require_matplotlib_panel_alignment
OUT=ROOT/'outputs/fig6_integrated_axes_20261030/artwork'
QA=OUT/'QA/Fig6';QA.mkdir(parents=True,exist_ok=True)
DATA=OUT/'source_data';DATA.mkdir(parents=True,exist_ok=True)
SRC=ROOT/'outputs/international_signal_validation_20261030'
OLD=ROOT/'outputs/results_network_revision_20261030'
ANNUAL=ROOT/'outputs/fig6_full_model_revision_20261030/analysis'
COLORS={1:'#7E99F4',2:'#A5AEB7',3:'#7AB656',4:'#CC7C71'}
BLUE='#7E99F4';RED='#CC7C71';GRAY='#A5AEB7';INK='#30343B';GRID='#E4E7EB'
WIDTH_MM=180;HEIGHT_MM=148;RASTER_DPI=600

def main():
    mpl.rcParams.update({'font.family':'sans-serif','font.sans-serif':['Arial','Helvetica','DejaVu Sans'],
      'font.size':8.5,'axes.labelsize':8.5,'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,
      'axes.linewidth':.7,'axes.spines.right':False,'axes.spines.top':False,'pdf.fonttype':42,'svg.fonttype':'none',
      'axes.unicode_minus':False,'savefig.facecolor':'white','legend.frameon':False})
    fig=plt.figure(figsize=(WIDTH_MM/25.4,HEIGHT_MM/25.4),dpi=300)
    W,H=fig.get_size_inches()*72
    def panel(label,x,y,w,h):
        ax=fig.add_axes([x/W,y/H,w/W,h/H]);ax.set_gid(label)
        ax.text(-15/w,1+8/h,label,transform=ax.transAxes,fontsize=10,fontweight='bold',va='bottom',ha='left')
        ax.tick_params(length=2.5,width=.55,pad=3,colors='black')
        ax.set_axisbelow(True);ax.grid(color=GRID,linewidth=.55)
        return ax
    a=panel('a',46,279,174,101);b=panel('b',346,279,140,101)
    c=panel('c',46,45,174,174)
    d=panel('d',298,153,188,66);e=panel('e',298,45,188,66)
    # Only the tested aggregate configuration; colours match the other figures.
    a.set(xlim=(0,1),ylim=(0,1));a.axis('off')
    for start,end,color in [((.17,.29),(.46,.72),RED),((.54,.72),(.83,.29),RED),((.26,.21),(.74,.21),BLUE)]:
        a.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=10,color=color,lw=1.8))
    for x,y,label,color in [(.17,.21,'i',BLUE),(.5,.79,'k',RED),(.83,.21,'j',BLUE)]:
        a.scatter([x],[y],s=215,facecolor=color,edgecolor='white',linewidth=.9,zorder=4)
        a.text(x,y,label,color='white',ha='center',va='center',fontsize=9,fontweight='bold',zorder=5)
    a.text(.5,1.01,'Foreign city',ha='center',va='bottom',fontsize=8.5)
    a.text(.5,.02,'Domestic cities',ha='center',va='bottom',fontsize=8.5)
    # These intervals retain the original matched country analysis.
    summary=pd.read_csv(SRC/'comparison_summary.csv')
    names=['P_partner_country','G_international_gateway','R_foreign_city_reach','C_international_centrality','S_shared_foreign_cities','T_foreign_two_step','A_all_international_signals']
    labels=['Partner countries','International volume','Foreign-city reach','Network centrality','Shared foreign cities','Two-step links','Integrated model']
    vals=summary[(summary.split=='test')&(summary.base=='B_history_field')].set_index('new').loc[names].reset_index()
    for i,row in vals.iterrows():
        color=RED if i in [5,6] else GRAY
        b.errorbar(row.median_deviance_reduction_pct,6-i,xerr=[[row.median_deviance_reduction_pct-row.CI_low],[row.CI_high-row.median_deviance_reduction_pct]],
                   fmt='D' if i==6 else 'o',ms=4.5,color=color,ecolor=color,elinewidth=1.5,capsize=2,markeredgewidth=.6,zorder=3)
    b.set(yticks=np.arange(6,-1,-1),yticklabels=labels,xlim=(-.2,7.5),ylim=(-.6,6.6))
    b.tick_params(axis='y',length=0,pad=4);b.set_xticks([0,2,4,6]);b.grid(axis='y',visible=False)
    b.axvline(0,color='#ADB4BC',lw=.7,zorder=1);b.set_xlabel('Deviance reduction (%)',labelpad=5)
    vals.to_csv(DATA/'Fig6_allocation_additions.csv',index=False)
    members=pd.read_csv(OLD/'artwork/source_data/trajectory_membership.csv')[['country','group']]
    null=pd.read_csv(OLD/'analysis/network_randomization_country_summary.csv').merge(members,on='country',validate='one_to_one')
    assert len(null)==76
    for group,s in null.groupby('group'):
        c.scatter(s.actual_gain_pct,s.randomized_gain_median_pct,s=27,color=COLORS[int(group)],alpha=1.,edgecolor='white',linewidth=.35,zorder=3)
    c.plot([-12,42],[-12,42],color='#7B828B',lw=.8,ls=(0,(3,3)),zorder=1)
    c.set(xlim=(-12,42),ylim=(-12,42),xticks=[-10,0,10,20,30,40],yticks=[-10,0,10,20,30,40])
    c.set_xlabel('Actual gain (%)',labelpad=5);c.set_ylabel('Rematched gain (%)',labelpad=4)
    handles=[Line2D([],[],color=COLORS[i],marker='o',linestyle='none',ms=4,label=f'T{i}') for i in range(1,5)]
    c.legend(handles=handles,loc='lower center',bbox_to_anchor=(.5,1.03),ncol=4,
             columnspacing=.45,handletextpad=.25,borderaxespad=0,fontsize=7.5)
    # Calculate every point from that year's flows and origin totals.
    run=json.loads((ANNUAL/'annual_summary.json').read_text());assert run['international_model']=='A_all_international_signals'
    country_year=pd.read_csv(ANNUAL/'annual_country_indices.csv')
    country_year=country_year[country_year.year.between(2018,2025)].copy()
    assert len(country_year)==608 and country_year.groupby('year').country.nunique().eq(76).all()
    errors=[]
    for metric in ['Gini','HHI']:
        scale=100 if metric=='Gini' else 1
        for model in ['reference','international']:
            error=(country_year[f'{model}_{metric}']-country_year[f'observed_{metric}'])*scale
            errors.append(dict(metric=metric,model=model,MAE=float(error.abs().mean()),
                RMSE=float(np.sqrt(np.square(error).mean())),MedAE=float(error.abs().median()),
                units='percentage points' if metric=='Gini' else 'dimensionless',countries=76,country_years=608))
    error_frame=pd.DataFrame(errors)
    error_frame.to_csv(DATA/'Fig6_evaluation_errors.csv',index=False)
    country_year.to_csv(DATA/'Fig6_evaluation_country_year_indices.csv',index=False)
    annual_errors=[]
    for ax,metric in [(d,'Gini'),(e,'HHI')]:
        scale=100 if metric=='Gini' else 1
        plotted=[]
        for model,color,label in [('reference',GRAY,'Reference'),('international',RED,'Integrated')]:
            absolute=(country_year[f'{model}_{metric}']-country_year[f'observed_{metric}']).abs()*scale
            series=country_year.assign(absolute_error=absolute).groupby('year').absolute_error.mean()
            assert series.index.tolist()==list(range(2018,2026))
            expected=error_frame[(error_frame.metric==metric)&(error_frame.model==model)].MAE.iloc[0]
            assert np.isclose(series.mean(),expected,rtol=0,atol=1e-12)
            annual_errors.extend(dict(year=int(year),metric=metric,model=model,MAE=float(value),countries=76,
                units='percentage points' if metric=='Gini' else 'dimensionless') for year,value in series.items())
            ax.plot(series.index,series.to_numpy(),color=color,lw=2.,marker='o',ms=3.5,mec='white',mew=.45,zorder=3 if model=='international' else 2)
            plotted.extend(series.to_list())
        ax.set(xlim=(2017.9,2025.1),xticks=list(range(2018,2026)));ax.set_xlabel('Year',labelpad=5);ax.set_ylabel('MAE',labelpad=5)
        limits=(.9,1.7) if metric=='Gini' else (.007,.0115)
        ticks=[1.,1.2,1.4,1.6] if metric=='Gini' else [.007,.008,.009,.010,.011]
        assert limits[0]<min(plotted) and max(plotted)<limits[1]
        ax.set_ylim(*limits);ax.set_yticks(ticks)
        ax.yaxis.set_major_formatter(FormatStrFormatter('%.1f' if metric=='Gini' else '%.3f'))
        ax.set_title(metric,fontsize=8.5,pad=5)
    annual_error_frame=pd.DataFrame(annual_errors)
    annual_error_frame.to_csv(DATA/'Fig6_annual_MAE_curves.csv',index=False)
    line_handles=[Line2D([],[],color=RED,lw=2,marker='o',ms=3.5,label='Integrated'),
                  Line2D([],[],color=GRAY,lw=2,marker='o',ms=3.5,label='Reference')]
    fig.legend(handles=line_handles,loc='center',bbox_to_anchor=(392/W,244/H),ncol=2,handlelength=1.6,handletextpad=.4,columnspacing=1.4,fontsize=7.5)
    null.to_csv(DATA/'Fig6_actual_rematched_country_gains.csv',index=False)
    fig.canvas.draw()
    require_matplotlib_panel_alignment(fig,json_out=QA/'alignment.json',overlay_svg=QA/'alignment.svg',
        row_groups=[],column_groups=[['d','e']],exclude_axes=[a],strict=True)
    fig.savefig(OUT/'Fig6.pdf');fig.savefig(OUT/'Fig6.svg');fig.savefig(OUT/'Fig6.png',dpi=600)
    (QA/'figure_contract.json').write_text(json.dumps(dict(width_mm=WIDTH_MM,height_mm=HEIGHT_MM,font_size_pt=8.5,
       archetype='Restored asymmetric layout: a/b above, square c below left, annual d/e stacked below right',
       conclusion='The integrated model has lower annual country-mean absolute errors in domestic Gini and HHI than the reference throughout2018-2025; the foreign-city diagnostic remains a separate two-step comparison.',
       units='76 countries; all annual summaries use the same country sample.',
       uncertainty='b country-bootstrap95% intervals. c median over100 rematches. d/e mean absolute country-level errors in each year; no inferential uncertainty band or simulation interval.',
       annual_years=[2018,2025],annual_values_recalculated=True,no_interpolation=True,no_display_offsets=True,
       annual_predictors='Saved preceding-four-year block features, constant within each target block.',
       evaluation_only=True,shading_removed=True,origin_totals_supplied=True,
       all76_countries=True,annual_model='A_all_international_signals',international_feature_count=9,
       model_selection='The integrated model uses the existing joint specification; no refitting or reselection.',
       palette={'integrated_model':RED,'reference_model':GRAY},
       error_axes={'d':{'ylim':[.9,1.7],'ticks':[1.,1.2,1.4,1.6]},'e':{'ylim':[.007,.0115],'ticks':[.007,.008,.009,.010,.011]},'both':{'xlim':[2017.9,2025.1],'ticks':list(range(2018,2026))}},
       scale_reason='User requested closer views of model differences. Linear nonzero vertical ranges include every value with marker clearance; original8 annual observations and units unchanged.',
       group_palette={f'T{k}':v for k,v in COLORS.items()},group_marker_alpha=1.,
       annotations='Repeated numeric annotations and Observed legend removed. Both vertical axes are MAE; Gini and HHI are concise panel titles. Gini errors in percentage points, HHI dimensionless. Each annual point averages76 individual country errors; not the error between aggregated median curves.',
       geometry_exclusion='a is axis-free; b and c have deliberately unequal spans; d/e column edges and widths are audited.'),ensure_ascii=False,indent=2),encoding='utf8')
    plt.close(fig);print('Fig6 exported',flush=True)

if __name__=='__main__':main()
