"""Fetch public official Paddle checkpoints at pinned HF revisions; no documents uploaded."""
from concurrent.futures import ThreadPoolExecutor
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

MODELS = ('PP-OCRv5_server_det', 'eslav_PP-OCRv5_mobile_rec')


def get(url):
    with urlopen(Request(url,headers={'User-Agent':'Flowgic-local-OCR-evaluation/1.0'}),timeout=60) as response:
        return response.read()


def download(name, root):
    repo='PaddlePaddle/'+name
    meta=json.loads(get('https://huggingface.co/api/models/'+repo))
    revision=meta['sha']
    folder=root/name
    folder.mkdir(parents=True,exist_ok=False)
    files=[]
    for entry in meta['siblings']:
        filename=entry['rfilename']
        if filename not in {'inference.json','inference.yml','inference.pdiparams','LICENSE','README.md'}:
            continue
        payload=get(f'https://huggingface.co/{repo}/resolve/{revision}/{filename}')
        (folder/filename).write_bytes(payload)
        files.append({'file':filename,'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)})
    if not {'inference.json','inference.yml','inference.pdiparams'} <= {f['file'] for f in files}:
        raise ValueError('Checkpoint lacks expected inference files')
    return {'repository':repo,'revision':revision,'license':meta.get('cardData',{}).get('license'),'files':files}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--detector',choices=['PP-OCRv5_server_det','PP-OCRv5_mobile_det'],default=MODELS[0])
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        records=list(pool.map(lambda name:download(name,args.output),(args.detector,MODELS[1])))
    (args.output/'models.lock.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    print(json.dumps([{'repository':r['repository'],'revision':r['revision'],'license':r['license'],'bytes':sum(f['bytes'] for f in r['files'])} for r in records],indent=2))
