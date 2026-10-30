"""Verify local snapshots without running Django or loading document models."""
import argparse
import json
from pathlib import Path

from prepare import FIELDS, digest, score_eligible


def verify(root):
    root = Path(root).resolve()
    seen_docs, seen_hashes, groups = set(), {}, {}
    counts = {'documents':0, 'pages':0, 'eligible_holdout_documents':0}
    for line in (root / 'manifest.jsonl').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        doc = json.loads(line)
        identity = doc['document_id']
        if identity in seen_docs:
            raise ValueError('Duplicate document_id')
        seen_docs.add(identity)
        if groups.setdefault(doc['source_group'], doc['split']) != doc['split']:
            raise ValueError('Document group leaks between splits')
        if set(doc['gold']) != set(FIELDS) or not doc['pages']:
            raise ValueError('Missing expected fields or pages')
        page_numbers = set()
        for page in doc['pages']:
            path = (root / page['file']).resolve()
            if not path.is_relative_to(root):
                raise ValueError('Path escapes dataset directory')
            if digest(path) != page['sha256']:
                raise ValueError('Image checksum changed')
            if page['page_number'] in page_numbers:
                raise ValueError('Duplicate page number')
            page_numbers.add(page['page_number'])
            if seen_hashes.setdefault(page['sha256'], doc['split']) != doc['split']:
                raise ValueError('Exact image duplicate leaks between splits')
            counts['pages'] += 1
        counts['documents'] += 1
        counts['eligible_holdout_documents'] += bool(score_eligible(doc))
    return counts


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    print(json.dumps(verify(parser.parse_args().root), indent=2))
