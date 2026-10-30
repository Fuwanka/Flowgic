"""Build a local, auditable Russian document evaluation candidate set.

No OCR, model downloads or network calls. Existing labels are NOT gold labels.
Run from the repository root; outputs contain original document data.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import shutil

FIELDS = (
    'document_number', 'document_date', 'sender_name', 'recipient_name',
    'customer_name', 'carrier_name', 'sender_inn', 'sender_kpp', 'recipient_inn',
    'recipient_kpp', 'customer_inn', 'customer_kpp', 'carrier_inn',
    'sender_address', 'recipient_address', 'customer_address', 'carrier_address',
    'loading_address', 'unloading_address', 'planned_pickup_datetime',
    'planned_delivery_datetime', 'actual_arrival_datetime', 'actual_departure_datetime',
    'cargo_description', 'cargo_mass', 'cargo_mass_unit', 'package_count',
    'driver_name', 'vehicle_number', 'trailer_number', 'freight_amount',
    'cargo_value', 'vat_rate', 'vat_amount', 'currency',
    'request_number', 'supporting_document_number',
)
# F identifiers in logika.py have more reliable semantics than some rectangle labels.
# Even so, conflicts are preserved for review; no field is auto-approved.
FID_MAP = dict(zip(
    ['F001','F002','F003','F004','F005','F006','F007','F008','F009','F010',
     'F011','F013','F014','F015','F016','F017','F018','F019','F020','F021'],
    ['document_number','document_date','sender_name','recipient_name','freight_amount',
     'cargo_description','carrier_name','sender_inn','recipient_inn','sender_kpp',
     'recipient_kpp','request_number','supporting_document_number',
     'actual_arrival_datetime','actual_departure_datetime','carrier_inn',
     'driver_name','vehicle_number','loading_address','unloading_address']))
LABEL_MAP = {
    'waybill_number':'document_number', 'product_name':'cargo_description',
    'contract_number':'request_number', 'invoice_number':'supporting_document_number',
    'total_amount':'freight_amount', 'arrival_time':'actual_arrival_datetime',
    'departure_time':'actual_departure_datetime',
}

# Positive documents: 96 construction + 16 general + 16 food + 16 industrial.
# Negative examples are measured separately. Counts are acquisition targets only.
PLAN = {
    'tn_paper_archive': (28, 4, 4, 4),
    'etrn_visualization': (20, 4, 4, 4),
    'transport_request': (16, 4, 2, 2),
    'ttn_1t': (12, 0, 2, 2),
    'torg12': (10, 2, 2, 2),
    'upd': (10, 2, 2, 2),
    'negative': (0, 0, 0, 0),
}


def acquisition_rows():
    rows = []
    for family, quotas in PLAN.items():
        for industry, count in zip(('construction', 'general', 'food_cold_chain', 'industrial'), quotas):
            for index in range(count):
                # Alternate capture types rather than filling a whole industry with scans.
                capture = ('digital_pdf', 'scan', 'phone_photo', 'digital_pdf')[index % 4]
                rows.append({'slot_id':f'ru-{len(rows)+1:03d}', 'family':family,
                             'industry':industry, 'capture':capture, 'status':'missing',
                             'document_id':'', 'source_url':'', 'rights_status':'pending'})
    for index in range(16):
        rows.append({'slot_id':f'ru-{len(rows)+1:03d}', 'family':'negative',
                     'industry':'not_applicable', 'capture':('scan','phone_photo')[index % 2],
                     'status':'missing', 'document_id':'', 'source_url':'', 'rights_status':'pending'})
    return rows


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def page_identity(filename):
    """Keep both pages and future image variants in one source document group."""
    name = re.sub(r'^[0-9a-f]{8}-', '', filename, flags=re.I)
    match = re.search(r'_page[-_](\d+)', name)
    page = int(match.group(1)) if match else 1
    group = re.sub(r'_page[-_]\d+', '', Path(name).stem)
    return group, page


def regions(task):
    annotations = task.get('annotations', [])
    if len(annotations) != 1:
        raise ValueError('Expected one source annotation; adjudicate alternatives explicitly')
    grouped = defaultdict(list)
    for region in annotations[0].get('result', []):
        grouped[region['id']].append(region)
    output = []
    for region_id, entries in grouped.items():
        rect = next((r for r in entries if r['type'] == 'rectanglelabels'), None)
        if rect is None:
            continue
        labels = rect['value'].get('rectanglelabels', [])
        label = labels[0] if labels else None
        fids = [c for r in entries if r.get('from_name') == 'field_id'
                for c in r['value'].get('choices', [])]
        texts = [t for r in entries if r['type'] == 'textarea'
                 for t in r['value'].get('text', [])]
        semantic = LABEL_MAP.get(label, label)
        fid_semantic = FID_MAP.get(fids[0]) if fids else None
        candidate = fid_semantic or semantic
        issues = []
        if fid_semantic and semantic != fid_semantic:
            issues.append('label_fid_conflict')
        if candidate not in FIELDS:
            issues.append('unknown_field')
        if len(texts) != 1 or not texts[0].strip():
            issues.append('missing_or_multiple_transcriptions')
        value = rect['value']
        box = [value[k] for k in ('x', 'y', 'width', 'height')]
        if (any(not 0 <= v <= 100 for v in box) or box[0]+box[2] > 100.01
                or box[1]+box[3] > 100.01 or box[2] <= 0 or box[3] <= 0):
            issues.append('invalid_bbox')
        if value.get('rotation', 0) or rect.get('image_rotation', 0):
            issues.append('rotated_bbox_needs_review')
        output.append({
            'source_region_id': region_id, 'source_label': label,
            'source_field_ids': fids, 'candidate_field': candidate,
            'raw_text': '\n'.join(texts), 'bbox_xywh_percent': box,
            'image_width': rect.get('original_width'),
            'image_height': rect.get('original_height'),
            'review_status': 'pending', 'issues': issues,
        })
    return output


def score_eligible(document):
    """Fail closed: source labels and contaminated samples never form a holdout."""
    return (
        document.get('review_status') == 'approved'
        and document.get('rights_status') == 'approved'
        and document.get('provenance_kind') == 'real'
        and document.get('split') == 'holdout'
        and document.get('training_exposure') == 'none_verified'
        and document.get('reviewer')
        and document.get('second_reviewer')
        and document['reviewer'] != document['second_reviewer']
        and document.get('pages')
        and all(page.get('review_status') == 'approved' for page in document['pages'])
        and set(document.get('gold', {})) == set(FIELDS)
        and all(v.get('status') in {'present','absent','unreadable','not_applicable'}
                and (v.get('status') != 'present' or
                     (v.get('value') is not None and v.get('evidence')))
                for v in document['gold'].values())
    )


def build(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Output exists; choose a new version directory')
    export = source / 'dataset/raw/train1.json'
    tasks = json.loads(export.read_text(encoding='utf-8'))
    # Detect exact exposure to both former OCR training and Donut metadata.
    known_hashes = set()
    metadata = source / 'dataset/train/metadata.jsonl'
    for line in metadata.read_text(encoding='utf-8').splitlines():
        if line.strip():
            path = metadata.parent / json.loads(line)['file_name']
            known_hashes.add(digest(path))
    old_export = source / 'project-1-at-2026-04-18-05-40-eb2e8e7a.json'
    old_names = set()
    if old_export.exists():
        old_names = {t['file_upload'] for t in json.loads(old_export.read_text(encoding='utf-8'))}
    documents = {}
    # Validate every input before creating the output directory.
    prepared = []
    for task in tasks:
        filename = task['file_upload']
        if Path(filename).name != filename or '/' in filename or '\\' in filename:
            raise ValueError('Unsafe source filename')
        image = source / 'dataset/annotated' / filename
        image_hash = digest(image)
        group, number = page_identity(filename)
        prepared.append((filename, image, image_hash, group, number, regions(task)))
    destination.mkdir(parents=True)
    (destination / 'images').mkdir()
    for filename, image, image_hash, group, number, labels in prepared:
        doc_id = 'fv-' + hashlib.sha256(group.encode('utf-8')).hexdigest()[:16]
        doc = documents.setdefault(doc_id, {
            'schema_version': '1.0', 'document_id': doc_id, 'source_group': group,
            'family': 'unclassified', 'family_status': 'pending_visual_review',
            'provenance_kind': 'unknown', 'rights_status': 'pending',
            'review_status': 'pending', 'split': 'quarantine',
            'training_exposure': 'unknown', 'pages': [],
            'gold': {field: {'status':'unreviewed', 'value':None, 'evidence':[]}
                     for field in FIELDS},
        })
        exposure = image_hash in known_hashes or filename in old_names
        if exposure:
            doc['training_exposure'] = 'known_source_used_by_existing_training'
        target = f'images/{doc_id}-p{number:03d}{image.suffix.lower()}'
        if any(p['page_number'] == number for p in doc['pages']):
            raise ValueError(f'Duplicate source page in {doc_id}')
        shutil.copyfile(image, destination / target)
        doc['pages'].append({'page_number':number, 'file':target, 'sha256':image_hash,
                             'source_file':filename, 'review_status':'pending',
                             'candidate_regions':labels})
    records = sorted(documents.values(), key=lambda d:d['document_id'])
    for doc in records:
        doc['pages'].sort(key=lambda p:p['page_number'])
    write_jsonl(destination / 'manifest.jsonl', records)
    counts = Counter(issue for d in records for p in d['pages']
                     for r in p['candidate_regions'] for issue in r['issues'])
    summary = {
        'documents':len(records), 'pages':len(prepared),
        'candidate_regions':sum(len(p['candidate_regions']) for d in records for p in d['pages']),
        'eligible_holdout_documents':sum(bool(score_eligible(d)) for d in records),
        'training_exposure':dict(Counter(d['training_exposure'] for d in records)),
        'issues':dict(counts), 'source_export_sha256':digest(export),
        'warning':'Candidate quarantine only. Not a representative or verified benchmark.',
    }
    (destination / 'inventory.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    review = ['<!doctype html><meta charset="utf-8"><title>Flowgic: проверка кандидатов</title>',
              '<style>body{font:16px sans-serif;margin:2rem} img{max-width:900px;width:100%} td,th{border:1px solid #aaa;padding:6px} table{border-collapse:collapse} section{margin-bottom:3rem}</style>',
              '<h1>Кандидаты: все записи требуют проверки</h1>',
              '<p>Это просмотр исходной разметки, не подтверждённые ответы. Правки в manifest.jsonl. Отсутствие разметки не означает отсутствие значения.</p>']
    for doc in records:
        review.append(f'<h2>{html.escape(doc["document_id"])}</h2>')
        for page in doc['pages']:
            review.append(f'<section><h3>Страница {page["page_number"]}</h3><a href="{page["file"]}"><img loading="lazy" src="{page["file"]}"></a><table><tr><th>Поле-кандидат</th><th>Текст</th><th>Проблемы</th></tr>')
            for r in page['candidate_regions']:
                review.append('<tr>' + ''.join(f'<td>{html.escape(str(v))}</td>' for v in
                    (r['candidate_field'], r['raw_text'], ', '.join(r['issues']))) + '</tr>')
            review.append('</table></section>')
    (destination / 'review.html').write_text('\n'.join(review), encoding='utf-8')
    write_acquisition(destination / 'acquisition.csv')
    return summary


def write_acquisition(path):
    rows = acquisition_rows()
    with Path(path).open('x', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path, records):
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), ensure_ascii=True, indent=2))
