"""Offline OCR smoke benchmark. This does NOT classify documents or extract business fields."""
import argparse
import faulthandler
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

from prepare import digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--models',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=0)
    parser.add_argument('--mkldnn',action='store_true',help='Enable CPU oneDNN acceleration')
    parser.add_argument('--detector',choices=['PP-OCRv5_server_det','PP-OCRv5_mobile_det'],default='PP-OCRv5_server_det')
    parser.add_argument('--checks-only',action='store_true',help='Run only pages with predeclared text anchors')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    faulthandler.dump_traceback_later(90,repeat=True)
    os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK']='True'
    os.environ['PADDLE_PDX_CACHE_HOME']=str((args.output/'cache').resolve())
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    # Fail rather than making a silent remote fallback, including during initialization.
    def offline(event,arguments):
        if event in {'socket.connect','socket.getaddrinfo'}:
            raise RuntimeError('Outbound Python sockets disabled for local benchmark')
    sys.addaudithook(offline)
    started=time.perf_counter()
    print('Importing local Paddle runtime...',flush=True)
    from paddleocr import PaddleOCR
    import paddle
    import numpy as np
    import psutil
    from PIL import Image
    print('Runtime imported; initializing local models...',flush=True)
    ocr=PaddleOCR(
        text_detection_model_name=args.detector,
        text_detection_model_dir=str((args.models/args.detector).resolve()),
        text_recognition_model_name='eslav_PP-OCRv5_mobile_rec',
        text_recognition_model_dir=str((args.models/'eslav_PP-OCRv5_mobile_rec').resolve()),
        use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False,
        device='cpu',cpu_threads=4,enable_mkldnn=args.mkldnn,
        text_det_limit_side_len=1600,text_det_limit_type='max',
        text_recognition_batch_size=8,
    )
    initialization_seconds=time.perf_counter()-started
    faulthandler.cancel_dump_traceback_later()
    print(json.dumps({'initialization_seconds':round(initialization_seconds,3)}),flush=True)
    pages=[]
    for line in (args.dataset/'manifest.jsonl').read_text(encoding='utf-8').splitlines():
        doc=json.loads(line)
        pages.extend((doc['document_id'],doc['family'],page) for page in doc['pages'])
    if args.limit:
        pages=pages[:args.limit]
    if args.checks_only:
        checks=json.loads(Path(__file__).with_name('paddle_checks.json').read_text(encoding='utf-8'))['checks']
        selected={check['file'] for check in checks}
        pages=[p for p in pages if p[2]['file'] in selected]
    records=[]
    for index,(doc_id,family,page) in enumerate(pages,1):
        image_path=args.dataset/page['file']
        if digest(image_path)!=page['sha256']:
            raise ValueError('Input image changed')
        record={'document_id':doc_id,'family':family,'page_number':page['page_number'],
                'file':page['file'],'sha256':page['sha256']}
        start=time.perf_counter()
        try:
            # RGB image array avoids any URL/path interpretation in the OCR loader.
            array=np.array(Image.open(image_path).convert('RGB'))
            result=list(ocr.predict(array))[0]
            texts=list(result['rec_texts'])
            scores=[float(s) for s in result['rec_scores']]
            boxes=[np.asarray(box).tolist() for box in result['rec_polys']]
            record.update(status='success',image_width=array.shape[1],image_height=array.shape[0],
                          lines=[{'text':t,'confidence':s,'polygon':b} for t,s,b in zip(texts,scores,boxes)])
        except Exception as error:
            record.update(status='failed',error=f'{type(error).__name__}: {error}')
        record['seconds']=round(time.perf_counter()-start,3)
        records.append(record)
        (args.output/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf-8')
        print(json.dumps({'page':index,'of':len(pages),'document_id':doc_id,'status':record['status'],
                          'lines':len(record.get('lines',[])),'seconds':record['seconds']},ensure_ascii=True),flush=True)
    seconds=[r['seconds'] for r in records if r['status']=='success']
    memory=psutil.Process().memory_info()
    summary={'python':sys.version,'platform':platform.platform(),'processor':platform.processor(),
             'paddle':paddle.__version__,'paddleocr':importlib.metadata.version('paddleocr'),
             'paddlex':importlib.metadata.version('paddlex'),'device':'cpu','cpu_threads':4,
             'detector':args.detector,'recognizer':'eslav_PP-OCRv5_mobile_rec',
             'mkldnn':args.mkldnn,'det_limit_side_len':1600,'initialization_seconds':round(initialization_seconds,3),
             'pages':len(records),'success':len(seconds),'failed':len(records)-len(seconds),
             'median_seconds':statistics.median(seconds) if seconds else None,
             'min_seconds':min(seconds) if seconds else None,'max_seconds':max(seconds) if seconds else None,
             'rss_mib':round(memory.rss/1024**2,1),
             'peak_rss_mib':round(getattr(memory,'peak_wset',memory.rss)/1024**2,1),
             'physical_memory_gib':round(psutil.virtual_memory().total/1024**3,1),
             'network':'Python outbound socket audit hook active; inference run under restricted network sandbox',
             'scope':'OCR text and positions only; no complete gold labels, no field-extraction accuracy claim'}
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=True,indent=2))
    faulthandler.cancel_dump_traceback_later()


if __name__=='__main__':
    main()
