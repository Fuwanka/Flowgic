from io import BytesIO
import os
import socket
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image

import app


def png_bytes(size=(100, 80), format='PNG'):
    output = BytesIO()
    with Image.new('RGB', size, 'white') as image:
        image.save(output, format=format)
    return output.getvalue()


class FakeEngine:
    def __init__(self):
        self.calls = 0

    def predict(self, image):
        self.calls += 1
        return [{'text': 'Масса груза: 15,5 т', 'confidence': .97, 'bbox': [10, 20, 30, 2]}]


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'OCR_SERVICE_KEY': 'unit-test-key-never-production'})
        self.env.start()
        self.engine = FakeEngine()
        self.application = app.create_app(lambda: self.engine)
        self.client_context = TestClient(self.application)
        self.client = self.client_context.__enter__()
        self.headers = {'X-OCR-Service-Key': 'unit-test-key-never-production'}

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.env.stop()

    def upload(self, payload=None, **kwargs):
        return self.client.post('/recognize', headers=self.headers,
            files={'file': ('ignored-path.png', payload if payload is not None else png_bytes(), 'image/png')}, **kwargs)

    def test_health_contains_only_readiness(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'ready': True})

    def test_png_and_jpeg_real_decoding_and_contract(self):
        for fmt in ('PNG', 'JPEG'):
            response = self.upload(png_bytes(format=fmt))
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data['engine'], app.ENGINE_NAME)
            self.assertEqual(data['pages'][0]['number'], 1)
            self.assertEqual(data['pages'][0]['width'], 100)
            self.assertEqual(data['pages'][0]['height'], 80)
            self.assertEqual(data['pages'][0]['lines'][0]['text'], 'Масса груза: 15,5 т')

    def test_authentication_happens_before_parsing(self):
        for headers in ({}, {'X-OCR-Service-Key': 'wrong'}):
            response = self.client.post('/recognize', headers=headers, content=b'not multipart')
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json(), {'detail': 'unauthorized'})
        self.assertEqual(self.engine.calls, 0)

    def test_url_and_path_are_never_accepted(self):
        response = self.client.post('/recognize', headers=self.headers, json={'file': 'http://example.com/a.pdf'})
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/recognize', headers=self.headers, data={'file': 'C:/private/document.pdf'})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.engine.calls, 0)

    def test_invalid_and_unsupported_bytes(self):
        self.assertEqual(self.upload(b'not image').status_code, 422)
        response = self.upload(png_bytes(format='GIF'))
        self.assertEqual(response.status_code, 415)
        self.assertEqual(response.json(), {'detail': 'unsupported_file_type'})
        self.assertEqual(self.engine.calls, 0)

    def test_empty_and_oversize_file(self):
        self.assertEqual(self.upload(b'').status_code, 400)
        with patch.object(app, 'MAX_FILE_BYTES', 100):
            response = self.upload(b'x' * 101)
        self.assertEqual(response.status_code, 413)
        response = self.client.post('/recognize', headers={**self.headers, 'Content-Length': str(app.MAX_BODY_BYTES + 1)}, content=b'')
        self.assertEqual(response.status_code, 413)

    def test_dimension_limit_before_inference(self):
        response = self.upload(png_bytes((15, 80)))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {'detail': 'image_dimensions_exceeded'})
        self.assertEqual(self.engine.calls, 0)

    def test_real_pdf_rasterization_and_page_limit(self):
        output = BytesIO()
        with Image.new('RGB', (72, 72), 'white') as image:
            image.save(output, format='PDF', resolution=72)
        response = self.upload(output.getvalue())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()['pages']), 1)
        self.assertEqual(response.json()['pages'][0]['width'], 180)
        with patch.object(app, 'MAX_PAGES', 0):
            response = self.upload(output.getvalue())
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {'detail': 'page_limit_exceeded'})

    def test_busy_response_and_lock_release(self):
        self.application.state.lock.acquire()
        try:
            response = self.upload()
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {'detail': 'ocr_busy'})
        finally:
            self.application.state.lock.release()
        self.assertEqual(self.upload().status_code, 200)

    def test_errors_do_not_reveal_internal_details(self):
        with patch.object(self.engine, 'predict', side_effect=RuntimeError('SECRET path C:/private')):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'detail': 'ocr_failed'})
        self.assertNotIn('SECRET', response.text)
        self.assertEqual(self.upload().status_code, 200)

    def test_missing_models_leave_unready(self):
        def fail():
            raise RuntimeError('private checkpoint path')
        with TestClient(app.create_app(fail)) as client:
            self.assertEqual(client.get('/health').json(), {'ready': False})
            self.assertEqual(client.get('/health').status_code, 503)
            self.assertEqual(client.post('/recognize', headers=self.headers).json(), {'detail': 'ocr_not_ready'})

    def test_missing_key_forbids_startup(self):
        with patch.dict(os.environ, {'OCR_SERVICE_KEY': ''}):
            with self.assertRaises(RuntimeError):
                app.create_app()

    def test_model_calls_cannot_open_python_outbound_sockets(self):
        with app._offline():
            with self.assertRaisesRegex(RuntimeError, 'outbound network'):
                socket.getaddrinfo('example.com', 443)


if __name__ == '__main__':
    unittest.main()
