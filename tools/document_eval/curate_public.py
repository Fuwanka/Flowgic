"""Materialize explicit source page selections as pending annotation cases."""
import argparse
from collections import Counter
import html
import json
from pathlib import Path
import shutil
import subprocess

from prepare import FIELDS, digest, write_jsonl


def curate(source, output, plan):
    source, output = Path(source).resolve(), Path(output).resolve()
    entries=json.loads(Path(plan).read_text(encoding='utf-8'))
    sources={r['id']:r for r in map(json.loads,(source/'sources.jsonl').read_text(encoding='utf-8').splitlines())}
    renderer=shutil.which('pdftoppm')
    if not renderer:
        raise RuntimeError('pdftoppm is required')
    output.mkdir(parents=True,exist_ok=False)
    (output/'images').mkdir()
    records=[]
    gallery=['<!doctype html><meta charset="utf-8"><title>Flowgic: отобранные открытые примеры</title>',
             '<style>body{font:16px sans-serif;max-width:1200px;margin:2rem auto}img{max-width:100%;max-height:1300px}section{padding:2rem 0;border-top:1px solid #bbb}</style>',
             '<h1>Отобранные страницы: разметка ожидается</h1>',
             '<p>Рабочая публичная выборка. Независимость от предобучения не установлена. Это не готовые эталонные ответы.</p>']
    for case in entries:
        src=sources[case['source']]
        if src['download_status']!='downloaded':
            raise ValueError('Source not downloaded: '+case['source'])
        pdf=source/src['file']
        if digest(pdf)!=src['sha256']:
            raise ValueError('Original PDF changed')
        doc={'schema_version':'1.0','document_id':'public-'+case['id'],
             'source_group':case['source'],'split':'public_development',
             'family':case['family'],'family_status':'first_visual_triage',
             'provenance_kind':'public_example','rights_status':'not_established',
             'training_exposure':'public_pretraining_unknown','training_allowed':False,
             'review_status':'pending','source_url':src['url'],
             'source_pdf_sha256':src['sha256'],'source_pdf_file':str(pdf),
             'sample_kind':case['kind'],'review_notes':case['note'],'pages':[],
             'gold':{f:{'status':'unreviewed','value':None,'evidence':[]} for f in FIELDS}}
        for page in case['pages']:
            if not isinstance(page,int) or not 1<=page<=src['page_count']:
                raise ValueError('Page out of range')
            prefix=output/'images'/f'{case["id"]}-p{page:03d}'
            subprocess.run([renderer,'-f',str(page),'-l',str(page),'-scale-to','1800',
                            '-singlefile','-png',str(pdf),str(prefix)],check=True,capture_output=True,timeout=40)
            image=prefix.with_suffix('.png')
            doc['pages'].append({'page_number':page,'file':image.relative_to(output).as_posix(),
                                 'sha256':digest(image),'source_file':src['file'],
                                 'review_status':'pending','candidate_regions':[]})
        records.append(doc)
        gallery += [f'<section><h2>{html.escape(case["id"])} — {html.escape(case["family"])}</h2>',
                    f'<p>{html.escape(case["note"])}</p>',f'<p><a href="{html.escape(src["url"],quote=True)}">Источник</a> · {html.escape(case["kind"])}</p>']
        gallery += [f'<p>Страница источника {p["page_number"]}</p><a href="{p["file"]}"><img loading="lazy" src="{p["file"]}"></a>' for p in doc['pages']]
        gallery += ['</section>']
    write_jsonl(output/'manifest.jsonl',records)
    (output/'review.html').write_text('\n'.join(gallery),encoding='utf-8')
    summary={'cases':len(records),'selected_pages':sum(len(d['pages']) for d in records),
             'families':dict(Counter(d['family'] for d in records)),
             'kinds':dict(Counter(d['sample_kind'] for d in records)),
             'approved_gold_documents':0,'note':'First visual triage; no completed field annotation or independent holdout.'}
    (output/'inventory.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plan',type=Path,default=Path(__file__).with_name('public_cases.json'))
    args=parser.parse_args()
    print(json.dumps(curate(args.source,args.output,args.plan),ensure_ascii=True,indent=2))
