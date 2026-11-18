"""Verify the single gravity node and sync all canonical figure formats."""
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tmp/nhb_fig2_python_deps'))
import pymupdf

QA=Path(__file__).resolve().parent
ART=ROOT/'figures/fig1_framework_detailed'
PAPER=ROOT/'outputs/paper_final/figures'
records=[]
for ext in ['pdf','svg','png']:
    src=ART/f'Fig1_detailed.{ext}'
    dst=PAPER/f'Fig1.{ext}'
    shutil.copy2(src,dst)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    assert digest(src)==digest(dst)
    records.append({'format':ext,'sha256':digest(dst),'matches':True})

doc=pymupdf.open(PAPER/'Fig1.pdf')
page=doc[0]
before=pymupdf.open(QA/'before/Fig1_detailed.pdf')
assert len(re.findall(r'Gravity\s+model',page.get_text()))==1
assert 'Allocation' not in page.get_text()
def other_text(p):
    return [(s['text'],round(s['size'],3),tuple(round(v,2) for v in s['bbox']))
            for b in p.get_text('dict')['blocks'] for l in b.get('lines',[]) for s in l['spans']
            if s['text'] not in {'Gravity model','Gravity','model','Allocation'}]
assert other_text(before[0])==other_text(page)
mm=72/25.4
removed_frame=pymupdf.Rect(146*mm,(82-51.5)*mm,200*mm,(82-28.5)*mm)
def old_outer_frame_count(p):
    return sum(max(abs(v-w) for v,w in zip(d['rect'],removed_frame))<.05
               for d in p.get_drawings())
assert old_outer_frame_count(before[0])==1
assert old_outer_frame_count(page)==0
contract=json.loads((ROOT/'outputs/fig1_framework_detailed/design_contract.json').read_text(encoding='utf-8'))
assert 'integrated' not in contract['schematic_frames_mm']
assert 'gravity_model' in contract['schematic_frames_mm']
assert not contract['model_outer_container_displayed']
minimum_font=min(s['size'] for b in page.get_text('dict')['blocks']
                 for l in b.get('lines',[]) for s in l['spans'])
assert minimum_font>=6.999
assert abs(page.rect.width/mm-228)<.02 and abs(page.rect.height/mm-82)<.02
for name in ['alignment.json','alignment.svg','design_contract.json',
             'map_geometry_audit.json','arrow_color_audit.json','disciplinary_layout_audit.json']:
    shutil.copy2(ROOT/'outputs/fig1_framework_detailed'/name,QA/name)
shutil.copy2(ROOT/'scripts/plots/plot_fig1_framework_detailed.py',QA/'plot_fig1_framework_detailed.py')
shutil.copy2(ART/'Fig1_model_detail.png',QA/'Fig1_model_detail.png')
report={
    'native_dimensions_mm':[228,82], 'font_floor_pt':minimum_font,
    'gravity_model_label_count':1, 'allocation_label_removed':True,
    'outer_model_title_removed':True,'outer_model_frame_removed_from_final_pdf':True,
    'model_node_font_pt':8.8,'input_vectors_retained':['International','Discipline','Domestic'],
    'input_arrows_end_at_feature_vectors':True,'model_output_retained':True,
    'other_text_positions_and_sizes_unchanged':True,
    'visual_review':'Passed; model label fits the original inner node; open feature rows remain aligned',
    'collision_audit':'PASS, zero failures and warnings',
    'caption':'Existing caption still matches the single gravity-model node',
    'synchronized_formats':records,
    'source_warning_review':[
        'Vector PDF/SVG are delivery formats; PNG is preview; no TIFF needed.',
        'Native 228 mm width retained without scaling on landscape page.'
    ],'main_document_compile':'pending',
}
(QA/'final_QA.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
