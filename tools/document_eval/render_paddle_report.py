"""Create a local review of OCR text and control anchors beside original pages."""
import argparse
from collections import defaultdict
import html
import json
import os
from pathlib import Path


def render(run, dataset):
    run, dataset=Path(run).resolve(),Path(dataset).resolve()
    results=[json.loads(s) for s in (run/'results.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
    checks=json.loads((run/'checks.json').read_text(encoding='utf-8'))
    by_file=defaultdict(list)
    for check in checks['results']:
        by_file[check['file']].append(check)
    body=['<!doctype html><meta charset="utf-8"><title>PaddleOCR: локальная проверка</title>',
          '<style>body{font:16px sans-serif;margin:2rem}section{border-top:1px solid #ccc;margin-top:2rem;padding-top:1rem}.row{display:grid;grid-template-columns:1fr 1fr;gap:2rem}img{width:100%}pre{white-space:pre-wrap;max-height:1000px;overflow:auto}.pass{color:#166534}.fail{color:#b91c1c}td{padding:5px;border:1px solid #ccc}table{border-collapse:collapse}@media(max-width:800px){.row{display:block}}</style>',
          '<h1>PaddleOCR: локальный OCR-прогон</h1>',
          '<p>Здесь проверяется текст, а не распределение реквизитов по полям заказа. Контрольные фрагменты — частичная разметка публичных примеров.</p>',
          f'<p>Совпало контрольных фрагментов: {checks["matched"]} из {checks["checks"]}.</p>']
    for result in results:
        body += [f'<section><h2>{html.escape(result["document_id"])} · страница {result["page_number"]}</h2>',
                 f'<p>{html.escape(result["status"])} · {result["seconds"]} с · строк: {len(result.get("lines",[]))}</p>']
        selected=by_file[result['file']]
        if selected:
            body += ['<table><tr><th>Проверка</th><th>Ожидалось</th><th>Распознано в области</th><th>Совпадение</th></tr>']
            for c in selected:
                body += ['<tr>'+''.join(f'<td>{html.escape(str(v))}</td>' for v in
                                       (c['id'],c['expected'],c['observed_region_text'],c['matched']))+'</tr>']
            body += ['</table>']
        src=os.path.relpath(dataset/result['file'],run).replace('\\','/')
        text='\n'.join(line['text'] for line in result.get('lines',[])) or result.get('error','')
        body += [f'<div class="row"><a href="{html.escape(src,quote=True)}"><img loading="lazy" src="{html.escape(src,quote=True)}"></a><pre>{html.escape(text)}</pre></div></section>']
    (run/'review.html').write_text('\n'.join(body),encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True)
    args=parser.parse_args()
    render(args.run,args.dataset)
