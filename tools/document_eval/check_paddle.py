"""Evaluate predefined page-region text anchors; not an extraction accuracy benchmark."""
import argparse
import json
from pathlib import Path
import re
import unicodedata


def normalize(text):
    return re.sub(r'\s+','',unicodedata.normalize('NFKC',text).casefold())


def matches(expected,observed):
    normalized_lines=[normalize(line) for line in observed.splitlines()]
    expected,observed=normalize(expected),normalize(observed)
    if re.fullmatch(r"[0-9.,'–-]+",expected):
        return any(re.search(r'(?<![0-9])'+re.escape(expected)+r'(?![0-9])',line)
                   for line in normalized_lines)
    return expected in observed


def region_lines(result,box):
    x,y,w,h=box
    lines=[]
    for line in result.get('lines',[]):
        polygon=line['polygon']
        cx=100*sum(p[0] for p in polygon)/len(polygon)/result['image_width']
        cy=100*sum(p[1] for p in polygon)/len(polygon)/result['image_height']
        if x<=cx<=x+w and y<=cy<=y+h:
            lines.append(line['text'])
    return '\n'.join(lines)


def evaluate(results,checks):
    by_file={r['file']:r for r in results}
    records=[]
    for check in checks:
        result=by_file.get(check['file'])
        text=region_lines(result,check['bbox']) if result and result['status']=='success' else ''
        records.append({**check,'observed_region_text':text,
                        'matched':bool(result) and result['status']=='success' and matches(check['expected'],text)})
    return {'scope':'Text presence within manually specified regions; not field assignment, semantic correctness, CER or whole-document accuracy.',
            'checks':len(records),'matched':sum(r['matched'] for r in records),'results':records}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--checks',type=Path,default=Path(__file__).with_name('paddle_checks.json'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    results=[json.loads(s) for s in args.results.read_text(encoding='utf-8').splitlines() if s.strip()]
    checks=json.loads(args.checks.read_text(encoding='utf-8'))['checks']
    report=evaluate(results,checks)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'matched':report['matched'],'checks':report['checks']}))
