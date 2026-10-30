"""Download an explicit registry of public PDFs to a NEW local quarantine.

No registration, credentials, remote code, training or automatic gold labels.
Requires pypdf for inspection; optional --render uses installed pdftoppm.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

LIMIT = 25 * 1024 * 1024


def encode_url(url):
    parts = urlsplit(url)
    if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
        raise ValueError('Registry must use credential-free HTTPS URLs')
    return urlunsplit((parts.scheme, parts.netloc, quote(parts.path, safe='/%'), parts.query, ''))


def fetch(entry, root):
    from pypdf import PdfReader
    result = {**entry, 'download_status':'failed', 'rights_status':'not_established',
              'training_allowed':False, 'split':'public_development',
              'review_status':'pending', 'eligible_independent_holdout':False,
              'retrieved_at':datetime.now(timezone.utc).isoformat()}
    try:
        with urlopen(Request(encode_url(entry['url']), headers={'User-Agent':'Flowgic-Document-Evaluation/1.0'}), timeout=25) as response:
            payload = response.read(LIMIT+1)
            result['resolved_url'] = response.url
            result['content_type'] = response.headers.get('Content-Type')
        if len(payload) > LIMIT:
            raise ValueError('PDF exceeds 25 MiB limit')
        if not payload.startswith(b'%PDF-'):
            raise ValueError('Response is not a PDF (HTML/login/error page rejected)')
        target = root/'originals'/f'{entry["id"]}.pdf'
        target.write_bytes(payload)
        reader = PdfReader(target)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF requires separate inspection')
        text_pages = [page.extract_text() or '' for page in reader.pages]
        text_path = root/'text'/f'{entry["id"]}.json'
        text_path.write_text(json.dumps({'pages':[{'number':i+1,'text':t} for i,t in enumerate(text_pages)]},ensure_ascii=False,indent=2),encoding='utf-8')
        result.update(download_status='downloaded', file=target.relative_to(root).as_posix(),
                      sha256=hashlib.sha256(payload).hexdigest(), bytes=len(payload),
                      page_count=len(reader.pages), text_file=text_path.relative_to(root).as_posix(),
                      text_characters=sum(map(len,text_pages)))
    except Exception as error:
        result['error'] = f'{type(error).__name__}: {error}'
    return result


def collect(registry, root, render=False):
    entries = json.loads(Path(registry).read_text(encoding='utf-8'))
    ids = [e['id'] for e in entries]
    if len(set(ids)) != len(ids) or any(not re.fullmatch(r'[a-z0-9-]+', i) for i in ids):
        raise ValueError('Unsafe or duplicate registry id')
    root = Path(root).resolve()
    root.mkdir(parents=True,exist_ok=False)
    for directory in ('originals','text','previews'):
        (root/directory).mkdir()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda e:fetch(e,root), entries))
    seen = {}
    renderer = shutil.which('pdftoppm') if render else None
    for result in results:
        if result['download_status'] != 'downloaded':
            continue
        result['exact_duplicate_of'] = seen.get(result['sha256'])
        seen.setdefault(result['sha256'],result['id'])
        result['previews'] = []
        # A first-page preview is triage, not full-document verification.
        if renderer and result['pages'] != []:
            prefix = root/'previews'/f'{result["id"]}-p001'
            try:
                subprocess.run([renderer,'-f','1','-l','1','-scale-to','1500','-singlefile','-png',str(root/result['file']),str(prefix)],check=True,capture_output=True,timeout=40)
                result['previews'] = [prefix.with_suffix('.png').relative_to(root).as_posix()]
            except (subprocess.SubprocessError,OSError) as error:
                result['render_error'] = str(error)
    (root/'sources.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results),encoding='utf-8')
    body = ['<!doctype html><meta charset="utf-8"><title>Flowgic: открытые образцы</title>',
            '<style>body{font:16px sans-serif;max-width:1200px;margin:2rem auto}img{max-width:100%;max-height:1200px}section{border-top:1px solid #ccc;padding:1rem}code{overflow-wrap:anywhere}</style>',
            '<h1>Открытые материалы — рабочая подборка</h1>',
            '<p>Не независимый holdout. Все документы требуют разметки; права на обучение и распространение не установлены. Заголовок источника не подтверждает заполненность формы.</p>']
    for r in results:
        body += [f'<section><h2>{html.escape(r["title"])}</h2>',f'<p>{html.escape(r["family"])} / {html.escape(r["kind"])} / {html.escape(r["download_status"])}</p>',
                 f'<p><a href="{html.escape(encode_url(r["url"]),quote=True)}">Источник</a></p>']
        if r['download_status']=='downloaded':
            body += [f'<p><a href="{r["file"]}">Оригинал PDF ({r["page_count"]} стр.)</a></p>']
            body += [f'<a href="{r["file"]}"><img loading="lazy" src="{p}"></a>' for p in r['previews']]
        else:
            body += [f'<p>{html.escape(r["error"])}</p>']
        body += ['</section>']
    (root/'review.html').write_text('\n'.join(body),encoding='utf-8')
    summary = {'registered_sources':len(results),'downloaded':sum(r['download_status']=='downloaded' for r in results),
               'source_pdf_pages':sum(r.get('page_count',0) for r in results),
               'independent_gold_documents':0,'note':'Source PDFs and handbooks are not counted as fully annotated document examples.'}
    (root/'inventory.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry',type=Path,default=Path(__file__).with_name('public_sources.json'))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    print(json.dumps(collect(args.registry,args.output,args.render),indent=2))
