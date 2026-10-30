"""Internal offline OCR service. Run a single Uvicorn worker per CPU instance."""
from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
import hmac
import hashlib
from io import BytesIO
import json
import logging
import math
import os
from pathlib import Path
import sys
import threading
from typing import Callable
import warnings

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException


MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_BODY_BYTES = MAX_FILE_BYTES + 64 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_PAGES = 10
MAX_IMAGE_PIXELS = 25_000_000
MAX_IMAGE_SIDE = 12_000
MAX_RENDER_PIXELS = 14_000_000
MAX_RENDER_SIDE = 8_000
ENGINE_NAME = 'paddleocr-3.7.0/PP-OCRv5_mobile_det/eslav_PP-OCRv5_mobile_rec'
logger = logging.getLogger('flowgic.ocr')
_network_state = threading.local()


def _outbound_guard(event, _arguments):
    if getattr(_network_state, 'blocked', False) and event in {'socket.connect', 'socket.getaddrinfo'}:
        raise RuntimeError('OCR outbound network is disabled')


# The guard applies only inside model import/initialization/inference. Inbound
# ASGI sockets and independent HTTP health probes remain available.
sys.addaudithook(_outbound_guard)


@contextmanager
def _offline():
    previous = getattr(_network_state, 'blocked', False)
    _network_state.blocked = True
    try:
        yield
    finally:
        _network_state.blocked = previous


class DocumentRejected(Exception):
    def __init__(self, code: str, status: int = 422):
        self.code, self.status = code, status


class _BodyTooLarge(Exception):
    pass


class UploadBoundaryMiddleware:
    """Authenticate and cap the complete request before multipart parsing."""

    def __init__(self, app, key: str):
        self.app, self.key = app, key.encode('utf-8')

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') != '/recognize':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        supplied = headers.get(b'x-ocr-service-key', b'')
        if not supplied or not hmac.compare_digest(supplied, self.key):
            return await JSONResponse({'detail': 'unauthorized'}, status_code=401)(scope, receive, send)
        length = headers.get(b'content-length')
        if length:
            try:
                if int(length) < 0 or int(length) > MAX_BODY_BYTES:
                    raise _BodyTooLarge
            except (ValueError, _BodyTooLarge):
                return await JSONResponse({'detail': 'file_too_large'}, status_code=413)(scope, receive, send)
        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > MAX_BODY_BYTES:
                    raise _BodyTooLarge
            return message

        try:
            return await self.app(scope, limited_receive, send)
        except _BodyTooLarge:
            return await JSONResponse({'detail': 'file_too_large'}, status_code=413)(scope, receive, send)


class PaddleEngine:
    def __init__(self):
        root_value = os.environ.get('OCR_MODEL_ROOT', '')
        if not root_value:
            raise RuntimeError('OCR_MODEL_ROOT is required')
        root = Path(root_value).resolve(strict=True)
        lock = json.loads(Path(__file__).with_name('models.lock.json').read_text(encoding='utf-8-sig'))
        for entry in lock:
            directory = root / entry['repository'].split('/')[-1]
            for item in entry['files']:
                path = directory / item['file']
                if not path.is_file() or path.stat().st_size != item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                    raise RuntimeError('Pinned OCR checkpoint verification failed')
        detector = root / 'PP-OCRv5_mobile_det'
        recognizer = root / 'eslav_PP-OCRv5_mobile_rec'
        for model in (detector, recognizer):
            # Do not fall back to a model registry when a mounted checkpoint is
            # incomplete. These files are present in the validated v5 bundles.
            for name in ('inference.json', 'inference.pdiparams', 'inference.yml'):
                if not (model / name).is_file():
                    raise RuntimeError('Local OCR model bundle is incomplete')
        cache = Path(os.environ.get('OCR_CACHE_ROOT', '/tmp/flowgic-ocr-cache' if os.name != 'nt' else str(root.parent / 'service-cache')))
        cache.mkdir(parents=True, exist_ok=True)
        os.environ['PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'] = 'True'
        os.environ['PADDLE_PDX_CACHE_HOME'] = str(cache.resolve())
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        os.environ['OMP_NUM_THREADS'] = '4'
        with _offline():
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(
                text_detection_model_name='PP-OCRv5_mobile_det',
                text_detection_model_dir=str(detector),
                text_recognition_model_name='eslav_PP-OCRv5_mobile_rec',
                text_recognition_model_dir=str(recognizer),
                use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, device='cpu', cpu_threads=4,
                enable_mkldnn=True, text_det_limit_side_len=1600,
                text_det_limit_type='max', text_recognition_batch_size=8,
            )

    def predict(self, image):
        import numpy as np
        with _offline():
            # Paddle's ndarray reader follows OpenCV's BGR channel order.
            result = list(self.ocr.predict(np.asarray(image.convert('RGB'))[:, :, ::-1].copy()))[0]
        width, height = image.size
        texts, scores, polygons = result['rec_texts'], result['rec_scores'], result['rec_polys']
        if not len(texts) == len(scores) == len(polygons) or len(texts) > 10_000:
            raise RuntimeError('Unexpected OCR output')
        lines = []
        for text, confidence, polygon in zip(texts, scores, polygons):
            text, score = str(text).strip(), float(confidence)
            if not text:
                continue
            if len(text) > 4096 or not math.isfinite(score) or not 0 <= score <= 1:
                raise RuntimeError('Unexpected OCR output')
            points = np.asarray(polygon, dtype=float)
            if points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all():
                raise RuntimeError('Unexpected OCR polygon')
            left = max(0.0, min(float(points[:, 0].min()), width))
            top = max(0.0, min(float(points[:, 1].min()), height))
            right = max(left, min(float(points[:, 0].max()), width))
            bottom = max(top, min(float(points[:, 1].max()), height))
            lines.append({'text': text, 'confidence': round(score, 6),
                          'bbox': [round(left / width * 100, 4), round(top / height * 100, 4),
                                   round((right - left) / width * 100, 4), round((bottom - top) / height * 100, 4)]})
        return lines


def _check_dimensions(width, height):
    if (width < 16 or height < 16 or width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE
            or width * height > MAX_IMAGE_PIXELS):
        raise DocumentRejected('image_dimensions_exceeded')


def _read_images(payload: bytes):
    """Yield closed-after-use RGB images from bytes; filenames are never used."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    if payload.startswith(b'%PDF-'):
        import pypdfium2 as pdfium
        pdf = None
        try:
            pdf = pdfium.PdfDocument(payload)
            if not 1 <= len(pdf) <= MAX_PAGES:
                raise DocumentRejected('page_limit_exceeded')
            for index in range(len(pdf)):
                page = pdf[index]
                bitmap = None
                try:
                    width, height = page.get_size()
                    if not all(math.isfinite(v) and 0 < v <= 20_000 for v in (width, height)):
                        raise DocumentRejected('image_dimensions_exceeded')
                    scale = min(180 / 72, MAX_RENDER_SIDE / max(width, height),
                                math.sqrt(MAX_RENDER_PIXELS / (width * height)))
                    bitmap = page.render(scale=scale)
                    image = bitmap.to_pil().convert('RGB')
                    _check_dimensions(*image.size)
                    yield image
                    image.close()
                finally:
                    if bitmap is not None:
                        bitmap.close()
                    page.close()
        except DocumentRejected:
            raise
        except Exception:
            raise DocumentRejected('invalid_pdf') from None
        finally:
            if pdf is not None:
                pdf.close()
        return
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(payload)) as source:
                if source.format not in {'PNG', 'JPEG'}:
                    raise DocumentRejected('unsupported_file_type', 415)
                _check_dimensions(*source.size)
                if getattr(source, 'n_frames', 1) != 1:
                    raise DocumentRejected('animated_image_not_supported')
                source.load()
                image = ImageOps.exif_transpose(source).convert('RGB')
                yield image
                image.close()
    except DocumentRejected:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise DocumentRejected('invalid_image') from None


def recognize_bytes(payload: bytes, engine) -> dict:
    if not payload:
        raise DocumentRejected('empty_file', 400)
    if len(payload) > MAX_FILE_BYTES:
        raise DocumentRejected('file_too_large', 413)
    pages = []
    for number, image in enumerate(_read_images(payload), 1):
        width, height = image.size
        pages.append({'number': number, 'width': width, 'height': height, 'lines': engine.predict(image)})
    result = {'engine': ENGINE_NAME, 'pages': pages}
    if len(json.dumps(result, ensure_ascii=False).encode('utf-8')) > MAX_RESPONSE_BYTES:
        raise DocumentRejected('ocr_result_too_large')
    return result


def create_app(engine_factory: Callable = PaddleEngine) -> FastAPI:
    key = os.environ.get('OCR_SERVICE_KEY', '')
    if not key or key.strip() != key:
        raise RuntimeError('OCR_SERVICE_KEY must be configured')

    @asynccontextmanager
    async def lifespan(application):
        application.state.engine = None
        try:
            application.state.engine = await run_in_threadpool(engine_factory)
        except Exception as exc:
            # Do not log input contents, credentials, checkpoint paths or a stack.
            logger.error('OCR initialization failed (%s)', type(exc).__name__)
        yield
        application.state.engine = None

    application = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    application.state.engine = None
    application.state.lock = threading.Lock()
    application.add_middleware(UploadBoundaryMiddleware, key=key)

    @application.get('/health')
    async def health():
        ready = application.state.engine is not None
        return JSONResponse({'ready': ready}, status_code=200 if ready else 503)

    @application.post('/recognize')
    async def recognize(request: Request):
        engine = application.state.engine
        if engine is None:
            return JSONResponse({'detail': 'ocr_not_ready'}, status_code=503)
        if not application.state.lock.acquire(blocking=False):
            return JSONResponse({'detail': 'ocr_busy'}, status_code=503, headers={'Retry-After': '15'})
        try:
            if not request.headers.get('content-type', '').lower().startswith('multipart/form-data;'):
                raise DocumentRejected('multipart_file_required', 400)
            try:
                async with request.form(max_files=1, max_fields=0, max_part_size=MAX_FILE_BYTES) as form:
                    if list(form.keys()) != ['file'] or len(form.getlist('file')) != 1 or not isinstance(form['file'], UploadFile):
                        raise DocumentRejected('single_file_required', 400)
                    upload = form['file']
                    payload = await upload.read(MAX_FILE_BYTES + 1)
            except _BodyTooLarge:
                raise
            except DocumentRejected:
                raise
            except (StarletteHTTPException, ValueError):
                raise DocumentRejected('invalid_multipart', 400) from None
            result = await run_in_threadpool(recognize_bytes, payload, engine)
            return JSONResponse(result)
        except DocumentRejected as exc:
            return JSONResponse({'detail': exc.code}, status_code=exc.status)
        except _BodyTooLarge:
            return JSONResponse({'detail': 'file_too_large'}, status_code=413)
        except Exception as exc:
            logger.error('OCR operation failed (%s)', type(exc).__name__)
            return JSONResponse({'detail': 'ocr_failed'}, status_code=503)
        finally:
            application.state.lock.release()

    return application


# Uvicorn factory mode avoids reading configuration at import/test collection.
# python -m uvicorn app:create_app --factory --workers 1 --host 127.0.0.1 --port 8090
