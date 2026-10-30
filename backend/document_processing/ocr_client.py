"""Only the configured internal OCR service receives bytes; URLs are never supplied by users."""
import json
import math
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from django.conf import settings


class OCRUnavailable(Exception):
    pass


def validate_response(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('engine'), str) or not 1 <= len(payload['engine']) <= 100:
        raise ValueError('engine')
    pages = payload.get('pages')
    if not isinstance(pages, list) or not 1 <= len(pages) <= 10:
        raise ValueError('pages')
    for number, page in enumerate(pages, 1):
        if page.get('number') != number or any(type(page.get(key)) is not int or not 1 <= page[key] <= 20000 for key in ('width', 'height')):
            raise ValueError('page')
        if not isinstance(page.get('lines'), list) or len(page['lines']) > 5000:
            raise ValueError('lines')
        for line in page['lines']:
            if not isinstance(line.get('text'), str) or len(line['text']) > 4000:
                raise ValueError('text')
            score, bbox = line.get('confidence'), line.get('bbox')
            if type(score) not in (float, int) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('confidence')
            if not isinstance(bbox, list) or len(bbox) != 4 or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 100 for v in bbox):
                raise ValueError('bbox')
    return {'engine': payload['engine'], 'pages': pages}


def recognize(data, content_type):
    url, key = settings.OCR_SERVICE_URL, settings.OCR_SERVICE_KEY
    parsed = urlsplit(url)
    if not key or parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OCRUnavailable('OCR service is not configured')
    boundary = uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="document"\r\nContent-Type: {content_type}\r\n\r\n'.encode() + data + f'\r\n--{boundary}--\r\n'.encode())
    request = Request(url.rstrip('/') + '/recognize', data=body, method='POST', headers={
        'Content-Type': f'multipart/form-data; boundary={boundary}', 'X-OCR-Service-Key': key,
    })
    try:
        with urlopen(request, timeout=settings.OCR_SERVICE_TIMEOUT) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
            raise ValueError('response too big')
        return validate_response(json.loads(raw))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, AttributeError) as exc:
        raise OCRUnavailable('OCR service failed') from exc
