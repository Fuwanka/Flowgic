from io import BytesIO
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import pytest
from django.http import Http404

from .documents import (
    DOCX_CONTENT_TYPE, DocumentDataError, InvalidDocumentTypeError,
    generate_order_document,
)
from .models import Document

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def document_text(content):
    with ZipFile(BytesIO(content)) as archive:
        assert archive.testzip() is None
        xml = archive.read('word/document.xml')
        root = ET.fromstring(xml)
        ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        text = '\n'.join(node.text or '' for node in root.findall('.//w:t', ns))
        # The generated output must not carry unfilled trusted template variables.
        for member in archive.namelist():
            if member.startswith('word/') and member.endswith('.xml'):
                assert b'{{' not in archive.read(member)
        return text


@pytest.mark.parametrize('document_type,title', [
    ('application', 'Договор-заявка'), ('ttn', 'ТТН по заказу'),
])
def test_order_docx_contains_scoped_order_data(dispatcher_a, order_a, document_type, title):
    result = generate_order_document(dispatcher_a, order_a.pk, document_type)
    assert result.content_type == DOCX_CONTENT_TYPE
    assert result.filename == f'order-{order_a.order_number.lower()}-{document_type}.docx'
    text = document_text(result.content)
    for value in (
        title, order_a.order_number, 'Company A', '1234567890', 'Client A',
        'client_a@test.com', 'Moscow', 'Saint Petersburg', 'Electronics',
        '5000', '50 000,00', 'A111AA77', 'Volvo FH16', 'Driver A', 'ЧЕРНОВИК',
    ):
        assert value in text
    assert Document.objects.filter(order=order_a).count() == 0


def test_document_generation_does_not_write_order(dispatcher_a, order_a, django_assert_num_queries):
    previous_updated = order_a.updated_at
    # One preloaded tenant query; no resource lookups or writes during generation.
    with django_assert_num_queries(1):
        generate_order_document(dispatcher_a, order_a.pk)
    order_a.refresh_from_db()
    assert order_a.updated_at == previous_updated


def test_foreign_company_order_is_hidden(dispatcher_a, order_b):
    with pytest.raises(Http404):
        generate_order_document(dispatcher_a, order_b.pk)


def test_assigned_driver_can_download_own_order(driver_a, order_a):
    assert 'Electronics' in document_text(generate_order_document(driver_a, order_a.pk).content)


def test_driver_cannot_download_other_assignment(driver_a, order_a, dispatcher_a):
    order_a.driver = None
    order_a.save(update_fields=['driver'])
    with pytest.raises(Http404):
        generate_order_document(driver_a, order_a.pk)
    # The company operator still has access to the unassigned order draft.
    assert generate_order_document(dispatcher_a, order_a.pk).content.startswith(b'PK')


@pytest.mark.parametrize('unavailable', ['blocked', 'inactive', 'no_company'])
def test_unavailable_account_cannot_generate_document(dispatcher_a, order_a, unavailable):
    if unavailable == 'blocked':
        dispatcher_a.status = 'blocked'
    elif unavailable == 'inactive':
        dispatcher_a.is_active = False
    else:
        dispatcher_a.company = None
    dispatcher_a.save()
    with pytest.raises(Http404):
        generate_order_document(dispatcher_a, order_a.pk)


def test_missing_optional_resources_and_legal_details_are_explicit(dispatcher_a, order_a):
    order_a.driver = None
    order_a.vehicle = None
    order_a.agreed_price = None
    order_a.distance_km = None
    order_a.save()
    company = order_a.client.company
    company.inn = None
    company.address = None
    company.save(update_fields=['inn', 'address'])
    for document_type in ('application', 'ttn'):
        text = document_text(generate_order_document(dispatcher_a, order_a.pk, document_type).content)
        assert 'Не указано' in text and 'None' not in text
        assert '__________________' in text
        assert 'ЧЕРНОВИК' in text


def test_user_text_is_xml_escaped_and_not_executed_as_template(dispatcher_a, order_a):
    order_a.cargo_type = '<Груз> & "особый" {{ 7*7 }}\x01'
    order_a.origin = 'Склад <А> & склад Б'
    order_a.save(update_fields=['cargo_type', 'origin'])
    result = generate_order_document(dispatcher_a, order_a.pk)
    with ZipFile(BytesIO(result.content)) as archive:
        xml = archive.read('word/document.xml')
        root = ET.fromstring(xml)
        text = '\n'.join(root.itertext())
        assert '<Груз> & "особый" {{ 7*7 }}' in text
        assert 'Склад <А> & склад Б' in text
        assert '\x01' not in text
        assert b'&lt;' in xml and b'&amp;' in xml


@pytest.mark.parametrize('resource', ['driver', 'vehicle'])
def test_corrupt_cross_tenant_resource_is_not_disclosed(dispatcher_a, order_a, driver_b, vehicle_b, resource):
    setattr(order_a, resource, driver_b if resource == 'driver' else vehicle_b)
    order_a.save(update_fields=[resource])
    with pytest.raises(DocumentDataError):
        generate_order_document(dispatcher_a, order_a.pk)


@pytest.mark.parametrize('document_type', ['', 'pdf', '../application', 'APPLICATION'])
def test_invalid_document_type_is_rejected(dispatcher_a, order_a, document_type):
    with pytest.raises(InvalidDocumentTypeError):
        generate_order_document(dispatcher_a, order_a.pk, document_type)
