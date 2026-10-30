"""Pure unit tests: no database, Paddle weights or external network required."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from document_processing.extraction import FIELD_IDS, extract_document, normalize_decimal


def page(*texts):
    return [{'number': 1, 'width': 1000, 'height': 1400, 'lines': [
        {'text': text, 'confidence': .99, 'bbox': [5, 2 + i * 3, 85, 2]}
        for i, text in enumerate(texts)]}]


class ExtractionTests(unittest.TestCase):
    def test_37_fields_and_nulls_without_fabricated_defaults(self):
        result = extract_document(page('Транспортная накладная'))
        self.assertEqual(len(FIELD_IDS), 37)
        self.assertEqual(set(result['fields']), set(FIELD_IDS))
        self.assertEqual(result['document_type'], 'tn')
        for field in result['fields'].values():
            self.assertIsNone(field['value'])
            self.assertIsNone(field['confidence'])
            self.assertEqual(field['evidence'], [])
            self.assertTrue(field['review_required'])

    def test_russian_numbers_preserve_precision(self):
        for raw, expected in [('12 345,67', '12345.67'), ('1\u00a0234,500', '1234.500'),
                              ('1\u202f234.5', '1234.5'), ('0,00', '0.00')]:
            with self.subTest(raw=raw):
                self.assertEqual(normalize_decimal(raw), expected)
        self.assertIsNone(normalize_decimal('12,5,6'))

    def test_freight_and_cargo_value_remain_distinct(self):
        result = extract_document(page('Транспортная накладная № ТН-7 от 29.10.2026',
            'Стоимость перевозки: 12 345,67 руб.', 'Объявленная стоимость груза: 850 000,00 руб.',
            'Сумма НДС: 2 057,61 руб.', 'Ставка НДС: 20%'))
        values = {key: val['value'] for key, val in result['fields'].items()}
        self.assertEqual(values['freight_amount'], '12345.67')
        self.assertEqual(values['cargo_value'], '850000.00')
        self.assertEqual(values['vat_amount'], '2057.61')
        self.assertEqual(values['vat_rate'], '20')
        self.assertEqual(values['currency'], 'RUB')
        for field in result['fields'].values():
            if field['value'] is not None:
                self.assertTrue(field['evidence'])
                self.assertLessEqual(field['confidence'], .85)

    def test_roles_tax_ids_and_addresses_do_not_bleed(self):
        result = extract_document(page('Товарно-транспортная накладная № 12 от 29.10.2026',
            'Грузоотправитель: ООО «Карьер», г. Красноярск, ул. Лесная, 1, ИНН 7707083893 КПП 770701001',
            'Грузополучатель: ООО «Стройка», г. Томск, ул. Мира, 2, ИНН 7736050003 КПП 773601001',
            'Заказчик: ООО «Заказчик», ИНН 7702070139 КПП 770201001',
            'Перевозчик: ООО «Рейс», ИНН 7710140679'))
        values = {key: val['value'] for key, val in result['fields'].items()}
        self.assertEqual(values['sender_name'], 'ООО «Карьер»')
        self.assertEqual(values['recipient_name'], 'ООО «Стройка»')
        self.assertEqual(values['customer_name'], 'ООО «Заказчик»')
        self.assertEqual(values['carrier_name'], 'ООО «Рейс»')
        self.assertEqual(values['sender_inn'], '7707083893')
        self.assertEqual(values['recipient_inn'], '7736050003')
        self.assertEqual(values['customer_kpp'], '770201001')
        self.assertTrue(values['sender_address'].startswith('г. Красноярск'))
        self.assertTrue(values['recipient_address'].startswith('г. Томск'))

    def test_inn_checksum_and_ooo_zero_confusion_require_review(self):
        result = extract_document(page('Транспортная накладная',
            'Грузоотправитель: 000 «Карьер», ИНН 1234567890'))
        self.assertEqual(result['fields']['sender_name']['value'], '000 «Карьер»')
        self.assertIn('ocr_organization_zero_confusion:sender_name', result['warnings'])
        self.assertIn('inn_checksum_failed:sender_inn', result['warnings'])

    def test_combined_inn_kpp_label(self):
        result = extract_document(page('Транспортная накладная',
            'Грузоотправитель: ООО «Карьер», ИНН/КПП 7707083893/770701001'))
        self.assertEqual(result['fields']['sender_inn']['value'], '7707083893')
        self.assertEqual(result['fields']['sender_kpp']['value'], '770701001')

    def test_global_unassigned_inn_is_not_guessed(self):
        result = extract_document(page('Транспортная накладная', 'ИНН 7707083893', 'КПП 770701001'))
        self.assertTrue(all(result['fields'][name]['value'] is None
                            for name in ('sender_inn', 'recipient_inn', 'carrier_inn', 'customer_inn')))

    def test_document_heading_dates_not_approval_or_request_reference(self):
        result = extract_document(page('Утверждена постановлением от 21.12.2020 № 2200',
            'Транспортная накладная № ТН-42 от 29.10.2026',
            'Договор-заявка № З-98 от 27.10.2026',
            'Сопроводительный документ № СЧ-67'))
        self.assertEqual(result['fields']['document_number']['value'], 'ТН-42')
        self.assertEqual(result['fields']['document_date']['value'], '2026-10-29')
        self.assertEqual(result['fields']['request_number']['value'], 'З-98')
        self.assertEqual(result['fields']['supporting_document_number']['value'], 'СЧ-67')

    def test_text_month_and_invalid_date(self):
        result = extract_document(page('Транспортная накладная № 1 от «29» октября 2026'))
        self.assertEqual(result['fields']['document_date']['value'], '2026-10-29')
        result = extract_document(page('Транспортная накладная № 1 от 31.02.2026'))
        self.assertIsNone(result['fields']['document_date']['value'])

    def test_split_date_cells_with_evidence(self):
        data = [{'number': 1, 'lines': [
            {'text': 'Транспортная накладная', 'bbox': [5, 5, 60, 2]},
            {'text': 'Дата составления', 'bbox': [50, 10, 20, 2]},
            {'text': '29', 'bbox': [72, 10, 3, 2]},
            {'text': '10', 'bbox': [78, 10, 3, 2]},
            {'text': '2026', 'bbox': [84, 10, 8, 2]},
        ]}]
        field = extract_document(data)['fields']['document_date']
        self.assertEqual(field['value'], '2026-10-29')
        self.assertEqual(len(field['evidence']), 4)

    def test_passport_and_vehicle_waybill_are_negative(self):
        for title in ('Паспорт качества № 123', 'Путевой лист грузового автомобиля № 123'):
            result = extract_document(page(title, 'Грузоотправитель: ООО «Карьер»', 'Масса груза: 20 т'))
            self.assertEqual(result['document_type'], 'other')
            self.assertIn('unsupported_document', result['warnings'])
            self.assertTrue(all(field['value'] is None for field in result['fields'].values()))

    def test_mass_not_capacity_density_volume_or_table_quantity(self):
        result = extract_document(page('Товарная накладная ТОРГ-12',
            'Грузоподъемность автомобиля: 20 т', 'Плотность груза: 1 600 кг/м3',
            'Объем: 15 м3', 'Наименование товара | единица | количество | цена',
            'Песок | м3 | 15 | 800', 'Масса груза: 23,75 т', 'Количество мест: 10'))
        self.assertEqual(result['fields']['cargo_mass']['value'], '23.75')
        self.assertEqual(result['fields']['cargo_mass_unit']['value'], 't')
        self.assertEqual(result['fields']['package_count']['value'], '10')
        result = extract_document(page('Товарная накладная ТОРГ-12',
            'Грузоподъемность автомобиля: 20 т', 'Плотность груза: 1 600 кг/м3', 'Песок | м3 | 15 | 800'))
        self.assertIsNone(result['fields']['cargo_mass']['value'])

    def test_planned_actual_and_no_invented_midnight(self):
        result = extract_document(page('Транспортная накладная',
            'Плановая погрузка: 29.10.2026 09:30', 'Плановая доставка: 30.10.2026 12:00',
            'Фактическое прибытие: 29.10.2026 10:05', 'Фактическое убытие: 29.10.2026 11:15'))
        for key, expected in [('planned_pickup_datetime', '2026-10-29T09:30:00'),
                              ('planned_delivery_datetime', '2026-10-30T12:00:00'),
                              ('actual_arrival_datetime', '2026-10-29T10:05:00'),
                              ('actual_departure_datetime', '2026-10-29T11:15:00')]:
            self.assertEqual(result['fields'][key]['value'], expected)
        result = extract_document(page('Транспортная накладная', 'Плановая погрузка: 29.10.2026'))
        self.assertIsNone(result['fields']['planned_pickup_datetime']['value'])

    def test_conflicting_pages_clear_proposal_and_keep_evidence(self):
        data = page('Транспортная накладная № 1 от 29.10.2026', 'Масса груза: 15 т')
        second = page('Масса груза: 16 т')[0]
        second['number'] = 2
        result = extract_document([*data, second])
        self.assertIsNone(result['fields']['cargo_mass']['value'])
        self.assertEqual(len(result['fields']['cargo_mass']['evidence']), 2)
        self.assertIn('conflicting_values:cargo_mass', result['warnings'])

    def test_driver_and_plates(self):
        result = extract_document(page('Транспортная накладная',
            'Водитель: Иванов Иван Иванович', 'Автомобиль: КамАЗ А123ВС124', 'Прицеп: АВ123424'))
        self.assertEqual(result['fields']['driver_name']['value'], 'Иванов Иван Иванович')
        self.assertEqual(result['fields']['vehicle_number']['value'], 'А123ВС124')
        self.assertEqual(result['fields']['trailer_number']['value'], 'АВ123424')

    def test_spatial_company_value_above_its_label(self):
        data = [{'number': 1, 'lines': [
            {'text': 'Товарно-транспортная накладная', 'bbox': [30, 5, 60, 2]},
            {'text': 'ООО «Карьер», ИНН 7707083893', 'bbox': [20, 18, 65, 2]},
            {'text': 'Грузоотправитель', 'bbox': [5, 20, 14, 2]},
            {'text': 'р/с 40702810000000000000', 'bbox': [20, 20, 65, 2]},
            {'text': 'ООО «Стройка», ИНН 7736050003', 'bbox': [20, 24, 65, 2]},
            {'text': 'Грузополучатель', 'bbox': [5, 26, 14, 2]},
        ]}]
        result = extract_document(data)
        self.assertEqual(result['fields']['sender_name']['value'], 'ООО «Карьер»')
        self.assertEqual(result['fields']['recipient_name']['value'], 'ООО «Стройка»')

    def test_exempt_vat_is_not_zero_rate_and_currency_not_defaulted(self):
        result = extract_document(page('Заявка № 17 от 29.10.2026', 'Стоимость перевозки: 12000 без НДС'))
        self.assertIsNone(result['fields']['vat_rate']['value'])
        self.assertIsNone(result['fields']['currency']['value'])
        self.assertIn('vat_exempt_text_present', result['warnings'])

    def test_nonfinite_boxes_are_ignored(self):
        result = extract_document([{'number': 1, 'lines': [{'text': 'Масса груза: 15 т',
            'bbox': [float('nan'), 5, 20, 2], 'confidence': 1}]}])
        self.assertIn('no_readable_text', result['warnings'])

    def test_apostrophe_grouping_in_money_is_not_truncated(self):
        result = extract_document(page('УПД', "Всего к оплате: 40'516.18 руб."))
        self.assertEqual(result['fields']['cargo_value']['value'], '40516.18')

    def test_ttn_grand_total_with_possible_charges_is_not_goods_or_freight(self):
        result = extract_document(page('Товарно-транспортная накладная', "Всего к оплате: 40'516.18 руб.", 'Складские или транспортные расходы: 3000.00'))
        self.assertIsNone(result['fields']['cargo_value']['value'])
        self.assertIsNone(result['fields']['freight_amount']['value'])
        self.assertIn('ttn_grand_total_includes_possible_charges', result['warnings'])

    def test_negative_amount_is_not_silently_read_as_positive(self):
        result = extract_document(page('УПД', 'Стоимость товара: -1200,00 руб.'))
        self.assertIsNone(result['fields']['cargo_value']['value'])
        self.assertIn('negative_value_requires_review:cargo_value', result['warnings'])

    def test_ttn_goods_subtotal_ignores_quantity_and_charge_inclusive_total(self):
        data = [{'number': 1, 'lines': [
            {'text': 'Товарно-транспортная накладная', 'bbox': [5, 5, 80, 2]},
            {'text': '1. ТОВАРНЫЙ РАЗДЕЛ', 'bbox': [30, 10, 40, 2]},
            {'text': 'Всего по накладной', 'bbox': [10, 57, 20, 2]},
            {'text': '8.000', 'bbox': [35, 57, 5, 2]},
            {'text': 'X', 'bbox': [65, 57, 3, 2]},
            {'text': "37'516.18", 'bbox': [80, 57, 10, 2]},
            {'text': "Всего к оплате: 40'516.18", 'bbox': [70, 70, 25, 2]},
        ]}]
        result = extract_document(data)
        self.assertEqual(result['fields']['cargo_value']['value'], '37516.18')
        self.assertIsNone(result['fields']['freight_amount']['value'])

    def test_explicit_currency_cell_without_money_marker(self):
        data = [{'number': 1, 'lines': [
            {'text': 'Валюта: наименование, код', 'bbox': [54, 29, 12, 2]},
            {'text': 'Российский рубль, 643', 'bbox': [68, 29, 10, 2]},
        ]}]
        self.assertEqual(extract_document(data, document_type='upd')['fields']['currency']['value'], 'RUB')

    def test_printed_form_reference_is_not_money(self):
        data = [{'number': 1, 'lines': [
            {'text': 'УПД', 'bbox': [5, 5, 10, 2]},
            {'text': 'Всего к оплате (9)', 'bbox': [10, 60, 20, 2]},
            {'text': '535808,00', 'bbox': [50, 60, 10, 2]},
        ]}]
        self.assertEqual(extract_document(data)['fields']['cargo_value']['value'], '535808.00')
        self.assertIsNone(extract_document(page('УПД', 'Всего к оплате (9)'))['fields']['cargo_value']['value'])

    def test_tabular_header_is_not_a_cargo_description(self):
        data = [{'number': 1, 'lines': [
            {'text': 'УПД', 'bbox': [5, 5, 10, 2]},
            {'text': 'Наименование товара (описание', 'bbox': [13, 41, 12, 2]},
            {'text': 'выполненных работ, оказанных', 'bbox': [13, 44, 12, 2]},
            {'text': '1а', 'bbox': [19, 48, 1, 2]},
            {'text': 'Лом и отходы черных металлов', 'bbox': [13, 50, 12, 2]},
        ]}]
        result = extract_document(data)
        self.assertEqual(result['fields']['cargo_description']['value'], 'Лом и отходы черных металлов')
        self.assertIsNone(result['fields']['cargo_mass']['value'])

    def test_split_invoice_number_and_company_address_tail(self):
        data = [{'number': 1, 'lines': [
            {'text': 'Счет-фактура №', 'bbox': [10, 10, 12, 2]},
            {'text': '703', 'bbox': [24, 10, 3, 2]},
            {'text': 'от', 'bbox': [29, 10, 2, 2]},
            {'text': 'Грузоотправитель: Общество с ограниченной ответственностью "Завод" 394ооо, Воронежская', 'bbox': [5, 20, 90, 2]},
        ]}]
        result = extract_document(data, document_type='upd')
        self.assertEqual(result['fields']['document_number']['value'], '703')
        self.assertEqual(result['fields']['sender_name']['value'], 'Общество с ограниченной ответственностью "Завод"')

    def test_route_cells_stop_at_next_route_label(self):
        data = [{'number': 1, 'lines': [
            {'text': 'Пункт погрузки', 'bbox': [5, 26, 8, 2]},
            {'text': 'г. Москва, Карьер, 17', 'bbox': [14, 26, 24, 2]},
            {'text': 'Пункт разгрузки', 'bbox': [44, 26, 9, 2]},
            {'text': 'г. Тула, Стройка, 12', 'bbox': [54, 26, 20, 2]},
            {'text': 'Маршрут', 'bbox': [82, 26, 8, 2]},
        ]}]
        result = extract_document(data, document_type='ttn')
        self.assertEqual(result['fields']['loading_address']['value'], 'г. Москва, Карьер, 17')
        self.assertEqual(result['fields']['unloading_address']['value'], 'г. Тула, Стройка, 12')


if __name__ == '__main__':
    unittest.main()
