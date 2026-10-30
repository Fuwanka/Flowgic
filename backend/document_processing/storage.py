"""Originals never have a public MEDIA_URL; every read passes tenant/RBAC checks."""
import io
import re
import warnings

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from PIL import Image
from pypdf import PdfReader

from .exceptions import ProcessingError

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 10
MAX_PIXELS = 25_000_000


def private_storage():
    return FileSystemStorage(location=settings.OCR_PRIVATE_ROOT)


def validate_upload(upload):
    data = upload.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise ProcessingError('Допустим файл до 20 МБ.', code='invalid_file', status=422)
    try:
        if data.startswith(b'%PDF-'):
            reader = PdfReader(io.BytesIO(data), strict=True)
            if reader.is_encrypted or not 1 <= len(reader.pages) <= MAX_PAGES:
                raise ValueError('pages/encryption')
            content_type, extension = 'application/pdf', 'pdf'
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as picture:
                    if (picture.format not in {'PNG', 'JPEG'} or picture.width * picture.height > MAX_PIXELS
                            or min(picture.size) < 16 or max(picture.size) > 12000 or getattr(picture, 'n_frames', 1) != 1):
                        raise ValueError('format/size')
                    extension = 'png' if picture.format == 'PNG' else 'jpg'
                    content_type = 'image/png' if extension == 'png' else 'image/jpeg'
                    picture.verify()
    except Exception as exc:
        raise ProcessingError('Нужен корректный PNG, JPEG или PDF без пароля: до 10 страниц и 25 Мп на изображение.', code='invalid_file', status=422) from exc
    filename = re.sub(r'[\x00-\x1f\x7f]', '', str(upload.name).replace('\\', '/').split('/')[-1])[:200]
    return data, content_type, extension, filename or f'document.{extension}'
