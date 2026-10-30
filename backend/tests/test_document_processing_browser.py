"""Production SPA + real API/DB; OCR inference is replaced by deterministic lines here.

The separate live smoke run exercises the actual Paddle service and Celery broker.
"""
from io import BytesIO
from unittest.mock import patch

import pytest
from PIL import Image
from playwright.sync_api import expect

from document_processing.models import DocumentReview, ProcessedDocument
from document_processing.tasks import process_document
from test_spa_browser import spa_origin, capture

pytestmark = [pytest.mark.browser, pytest.mark.integration, pytest.mark.django_db(transaction=True)]


def test_upload_preview_correct_confirm_and_reload(page, spa_origin, dispatcher_a, order_a, settings, tmp_path):
    settings.OCR_PRIVATE_ROOT = tmp_path / 'private'
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(spa_origin + '/login')
    page.get_by_label('Рабочий email', exact=True).fill(dispatcher_a.email)
    page.get_by_label('Пароль', exact=True).fill('testpass123')
    page.get_by_role('button', name='Войти в Flowgic').click()
    expect(page.get_by_role('heading', name='Перевозки под контролем')).to_be_visible(timeout=15000)
    page.goto(spa_origin + f'/orders/{order_a.pk}')
    panel = page.get_by_role('region', name='Распознавание накладных')
    expect(panel).to_be_visible()
    output = BytesIO()
    Image.new('RGB', (100, 100), 'white').save(output, 'PNG')
    payload = {'engine': 'browser-fixture', 'pages': [{'number': 1, 'width': 100, 'height': 100, 'lines': [
        {'text': 'Товарно-транспортная накладная № 17 от 29.10.2026', 'confidence': .99, 'bbox': [1, 1, 90, 4]},
        {'text': 'Наименование груза: Песок строительный', 'confidence': .98, 'bbox': [1, 10, 90, 4]},
        {'text': 'Масса груза: 20,5 т', 'confidence': .97, 'bbox': [1, 20, 90, 4]},
    ]}]}

    def dispatch(*, args, **_kwargs):
        process_document(*args)

    with patch('document_processing.tasks.recognize', return_value=payload), patch('document_processing.tasks.process_document.apply_async', side_effect=dispatch):
        panel.locator('input[type=file]').set_input_files({'name': 'russian-ttn.png', 'mimeType': 'image/png', 'buffer': output.getvalue()})
        panel.get_by_role('button', name='Распознать', exact=True).click()
        expect(panel.get_by_label('Наименование груза', exact=True)).to_have_value('Песок строительный', timeout=15000)
    panel.get_by_role('button', name='Открыть оригинал для сверки').click()
    expect(panel.get_by_alt_text('Оригинал документа russian-ttn.png')).to_be_visible()
    expect(panel.get_by_role('button', name='Скачать оригинал')).to_be_visible()
    checkbox = panel.get_by_label('Также перенести проверенные данные в заказ')
    expect(checkbox).not_to_be_checked()
    panel.get_by_label('Наименование груза', exact=True).fill('Щебень гранитный 5–20')
    checkbox.check()
    capture(page, 'document-processing-review')
    panel.get_by_role('button', name='Подтвердить и обновить заказ', exact=True).click()
    expect(panel.get_by_text('Проверка документа сохранена', exact=True)).to_be_visible(timeout=15000)
    order_a.refresh_from_db()
    assert order_a.cargo_type == 'Щебень гранитный 5–20' and order_a.cargo_mass_kg == 20500
    document = ProcessedDocument.objects.filter(company=dispatcher_a.company, order=order_a).get()
    assert document.status == 'confirmed'
    assert DocumentReview.objects.filter(company=dispatcher_a.company, document=document, actor=dispatcher_a).exists()
    page.reload()
    expect(panel.get_by_text('Проверка документа сохранена', exact=True)).to_be_visible()
    expect(panel.get_by_label('Наименование груза', exact=True)).to_have_value('Щебень гранитный 5–20')
    capture(page, 'document-processing-confirmed')
    assert not errors
