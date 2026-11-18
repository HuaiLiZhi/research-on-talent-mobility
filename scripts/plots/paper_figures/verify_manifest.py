"""Check the frozen manuscript figure-code inventory without running renderers."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-artwork',action='store_true',
                        help='Also check locally retained drawing and manuscript PDFs.')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[3]
    manifest=json.loads((Path(__file__).with_name('manifest.json')).read_text(encoding='utf-8'))
    entries=manifest['python_code']
    paths={item['path'] for item in entries}
    assert len(paths)==len(entries),'Duplicate code paths'
    assert {f['manuscript_figure'] for f in manifest['figures']}=={
        'Fig1','Fig2','Fig3','Fig4','Fig5','Fig6'}
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    for item in entries:
        path=root/item['path']
        assert path.is_file(),f'Missing code: {item["path"]}'
        ast.parse(path.read_text(encoding='utf-8-sig'),filename=item['path'])
        code_hash=hashlib.sha256(path.read_text(encoding='utf-8-sig').encode('utf-8')).hexdigest()
        assert code_hash==item['sha256'],f'Code changed: {item["path"]}'
    assets=manifest.get('asset_files',[])
    for item in assets:
        path=root/item['path']
        assert path.is_file(),f'Missing map resource: {item["path"]}'
        assert digest(path)==item['sha256'],f'Map resource changed: {item["path"]}'
        json.loads(path.read_text(encoding='utf-8-sig'))
    supplementary=manifest.get('supplementary_figures',[])
    for figure in manifest['figures']+supplementary:
        assert figure['renderer'] in paths,f'Unlisted renderer: {figure["renderer"]}'
        if args.check_artwork:
            for field in ['rendered_pdf','manuscript_pdf']:
                path=root/figure[field]
                assert path.is_file(),f'Missing local PDF: {figure[field]}'
                assert digest(path)==figure['pdf_sha256'],f'PDF changed: {figure[field]}'
    print(json.dumps({'status':'PASS','figures':len(manifest['figures']),
                      'supplementary_figures':len(supplementary),
                      'python_files':len(entries),'map_resources':len(assets),
                      'artwork_checked':args.check_artwork},indent=2))


if __name__=='__main__':
    main()
