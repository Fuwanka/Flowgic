"""Explicit administrator-only model preparation; inference never downloads weights."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


LOCK = Path(__file__).with_name('models.lock.json')


def verify(root):
    for model in json.loads(LOCK.read_text(encoding='utf-8-sig')):
        directory = root / model['repository'].split('/')[-1]
        for item in model['files']:
            path = directory / item['file']
            if not path.is_file() or path.stat().st_size != item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError(f'Model file failed verification: {directory.name}/{item["file"]}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--download', action='store_true', help='Explicitly fetch pinned official Hugging Face files')
    args = parser.parse_args()
    root = args.root.resolve()
    if args.download:
        for model in json.loads(LOCK.read_text(encoding='utf-8-sig')):
            directory = root / model['repository'].split('/')[-1]
            directory.mkdir(parents=True, exist_ok=True)
            for item in model['files']:
                path = directory / item['file']
                if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']:
                    continue
                url = f'https://huggingface.co/{model["repository"]}/resolve/{model["revision"]}/{item["file"]}'
                with urlopen(url, timeout=120) as response:
                    data = response.read(item['bytes'] + 1)
                if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
                    raise ValueError('Downloaded model hash/size differs from lock file')
                temporary = path.with_suffix(path.suffix + '.part')
                temporary.write_bytes(data)
                temporary.replace(path)
    verify(root)
    print('Both pinned OCR model bundles verified (SHA-256).')


if __name__ == '__main__':
    main()
