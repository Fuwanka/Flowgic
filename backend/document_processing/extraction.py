"""Conservative, evidence-backed extraction from Russian OCR lines.

This is a versioned rules baseline, not a trained semantic model. Scores describe
OCR support, capped for rule uncertainty; they are not calibrated probabilities.
Every proposal requires human review and missing values remain missing.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
import re
from typing import Any


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
FIELD_IDS = FIELDS
DOCUMENT_TYPES = frozenset({'tn', 'ttn', 'torg12', 'upd', 'request', 'other'})
EXTRACTION_VERSION = 'ru-labels-v3'
_FLAGS = re.IGNORECASE
_ROLE = re.compile(
    r'грузоотправител[ья]|грузополучател[ья]|заказчик(?:\s+перевозки)?|'
    r'плательщик|перевозчик|транспортная\s+организация', _FLAGS)
_ROLE_KEYS = (
    ('sender', re.compile(r'грузоотправител[ья]', _FLAGS)),
    ('recipient', re.compile(r'грузополучател[ья]', _FLAGS)),
    ('customer', re.compile(r'заказчик(?:\s+перевозки)?|плательщик', _FLAGS)),
    ('carrier', re.compile(r'перевозчик|транспортная\s+организация', _FLAGS)),
)
_ORG = re.compile(
    r'(?:\b(?:[ОO0]{3}|[З3]АО|ОАО|ПАО|АО|ИП|ФГУП|МУП|ГУП)\b|'
    r'общество\s+с\s+ограниченной\s+ответственностью)', _FLAGS)
_INN = re.compile(r'(?:ИНН|ЙНН)\s*(?:/\s*КПП)?\s*[:№]?\s*(\d{10}(?:\d{2})?)(?!\d)', _FLAGS)
_KPP = re.compile(r'КПП\s*[:№]?\s*(\d{9})(?!\d)', _FLAGS)
_NUMBER = r"\d+(?:[ \u00a0\u202f'’]\d{3})*(?:[,.]\d+)?"
_MONEY = re.compile(r"(?<![\d.,'’])(" + _NUMBER + r")(?![\d'’])")
_DATE = re.compile(r'(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?!\d)')
_MONTHS = {name: index for index, name in enumerate((
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'), 1)}
_TEXT_DATE = re.compile(r'[«"\']?(\d{1,2})[»"\']?\s+(' + '|'.join(_MONTHS) + r')\s+(\d{4})', _FLAGS)
_TIME = re.compile(r'(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?!\d)')
_BLANK = re.compile(r'^[\W_\d]*$')
_FORM_HINT = re.compile(
    r'наименование|подпись|расшифровка|номер\s+телефона|фамилия|инициалы|'
    r'место\s+нахождения|банковские\s+реквизиты|фактическ|планов|'
    r'масса\s+брутто|код\s+по|грузоотправител|грузополучател', _FLAGS)


@dataclass(frozen=True)
class _Line:
    page: int
    text: str
    box: tuple[float, float, float, float]
    confidence: float | None

    @property
    def x(self):
        return self.box[0]

    @property
    def y(self):
        return self.box[1]

    @property
    def cy(self):
        return self.box[1] + self.box[3] / 2

    @property
    def right(self):
        return self.box[0] + self.box[2]

    def evidence(self):
        return {'page': self.page, 'bbox': list(self.box), 'text': self.text}


def _lines(pages: list[dict]) -> list[_Line]:
    result = []
    for page in pages:
        number = int(page.get('number', 1))
        for raw in page.get('lines', []):
            text = re.sub(r'\s+', ' ', str(raw.get('text', ''))).strip()
            box = raw.get('bbox', [])
            if not text or len(box) != 4:
                continue
            try:
                box = tuple(float(n) for n in box)
                if not all(math.isfinite(n) and 0 <= n <= 100 for n in box):
                    continue
                if box[0] + box[2] > 100.01 or box[1] + box[3] > 100.01:
                    continue
                score = raw.get('confidence')
                score = float(score) if score is not None else None
                if score is not None and (not math.isfinite(score) or not 0 <= score <= 1):
                    score = None
                result.append(_Line(number, text, box, score))
            except (TypeError, ValueError):
                continue
    return sorted(result, key=lambda line: (line.page, line.y, line.x))


def normalize_decimal(value: str) -> str | None:
    """Normalize an explicitly selected number without silently rounding it."""
    cleaned = re.sub(r"[ \u00a0\u202f'’]", '', value).replace(',', '.')
    if not re.fullmatch(r'\d+(?:\.\d+)?', cleaned):
        return None
    try:
        number = Decimal(cleaned)
        return format(number, 'f') if number.is_finite() else None
    except InvalidOperation:
        return None


def _date_value(text: str, with_time=False) -> str | None:
    found = _DATE.search(text)
    try:
        if found:
            day, month, year = map(int, found.groups())
        else:
            found = _TEXT_DATE.search(text)
            if not found:
                return None
            day, month, year = int(found[1]), _MONTHS[found[2].lower()], int(found[3])
        date = datetime(year, month, day).strftime('%Y-%m-%d')
        # A date without a time is not a datetime. Do not invent midnight.
        if with_time:
            time = _TIME.search(text[found.end():])
            if not time:
                return None
            return f'{date}T{int(time[1]):02d}:{int(time[2]):02d}:00'
        return date
    except (ValueError, KeyError):
        return None


def _clean(text: str) -> str:
    text = re.sub(r'^\s*[\s:;=№#)\-–—]+', '', text).strip()
    return text.strip(' ;,_')


def _neighbors(label: _Line, all_lines: list[_Line], *, below=False) -> list[_Line]:
    """Only small, spatially related groups; never global next-text fallback."""
    row = [line for line in all_lines if line is not label and line.page == label.page
           and line.x >= label.right - 0.7
           and abs(line.cy - label.cy) <= max(label.box[3], line.box[3], 0.8) * 0.7
           and not _ROLE.search(line.text)]
    if row:
        return sorted(row, key=lambda line: line.x)
    if below:
        candidates = [line for line in all_lines if line.page == label.page
                      and 0 < line.y - (label.y + label.box[3]) < 2.0
                      and abs(line.x - label.x) < 5
                      and not _ROLE.search(line.text) and not _FORM_HINT.search(line.text)]
        return sorted(candidates, key=lambda line: (line.y, line.x))[:1]
    return []


def _context(line: _Line, match: re.Match, all_lines: list[_Line], *, below=False):
    tail = _clean(line.text[match.end():])
    # Printed form references such as "Всего к оплате (9)" are not values.
    tail = re.sub(r'^[([]\d+[a-zа-я]?[)\]]\s*', '', tail, flags=_FLAGS)
    if tail and re.search(r'[A-Za-zА-Яа-яЁё0-9]', tail):
        return tail, [line]
    neighbors = _neighbors(line, all_lines, below=below)
    return ' '.join(item.text for item in neighbors), [line, *neighbors]


def _role_label(text, regex):
    match = regex.search(text)
    if not match or _ORG.search(text[:match.start()]):
        return None
    if re.search(r'[«"“]', text[:match.start()]):
        return None
    return match


def _classify(lines: list[_Line]) -> str:
    header = '\n'.join(line.text for line in lines if line.page == 1 and line.y < 45).lower()
    if re.search(r'товарно[\s-]*транспортная\s+накладная|форма\s*№?\s*1[\s-]*т\b', header):
        return 'ttn'
    if re.search(r'универсальн\w*\s+передаточн\w*|\bупд\b', header):
        return 'upd'
    if re.search(r'торг[\s-]*12|товарная\s+накладная', header):
        return 'torg12'
    if re.search(r'транспортная\s+накладная', header):
        return 'tn'
    if re.search(r'(?:договор[\s-]*)?заявка\b', header):
        return 'request'
    return 'other'


def _inn_valid(value: str) -> bool:
    def control(weights, digits):
        return str(sum(a * int(b) for a, b in zip(weights, digits)) % 11 % 10)
    if len(value) == 10:
        return control((2, 4, 10, 3, 5, 9, 4, 6, 8), value) == value[-1]
    return (len(value) == 12
            and control((7, 2, 4, 10, 3, 5, 9, 4, 6, 8), value) == value[-2]
            and control((3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8), value) == value[-1])


def extract_document(pages: list[dict[str, Any]], document_type: str = 'auto') -> dict:
    """Produce reviewable field proposals from the internal OCR page contract.

    Bounding boxes are percentages [left, top, width, height], not pixel boxes.
    Missing fields have no evidence or confidence. Values are never written to an
    order here, and this function has no network, database, or filesystem access.
    """
    if document_type not in DOCUMENT_TYPES | {'auto'}:
        raise ValueError('Unsupported document_type')
    lines = _lines(pages)
    fields = {name: {'value': None, 'raw_text': None, 'confidence': None,
                     'evidence': [], 'review_required': True} for name in FIELDS}
    warnings = ['manual_review_required', 'rule_scores_are_not_calibrated']
    blocked = set()

    def warn(message):
        if message not in warnings:
            warnings.append(message)

    def offer(name, value, evidence):
        if not value or not evidence or name in blocked:
            return
        value = str(value).strip()
        if len(value) > 2000:
            warn(f'field_too_long:{name}')
            return
        unique = list(dict.fromkeys(evidence))
        old = fields[name]
        if old['value'] is not None:
            if old['value'] != value:
                # Competing labels/pages require a human decision, not first-wins.
                fields[name] = {'value': None, 'raw_text': None, 'confidence': None,
                                'evidence': [*old['evidence'], *(line.evidence() for line in unique)],
                                'review_required': True}
                blocked.add(name)
                warn(f'conflicting_values:{name}')
            return
        scores = [line.confidence for line in unique if line.confidence is not None]
        fields[name] = {'value': value, 'raw_text': '\n'.join(line.text for line in unique),
                        'confidence': round(min(0.85, min(scores)), 4) if scores else None,
                        'evidence': [line.evidence() for line in unique], 'review_required': True}

    if not lines:
        warn('no_readable_text')
        return {'document_type': 'other' if document_type == 'auto' else document_type,
                'fields': fields, 'warnings': warnings}

    header = '\n'.join(line.text for line in lines if line.page == 1 and line.y < 40)
    if re.search(r'паспорт\s+(?:качества|изделия|гражданина)|сертификат\s+(?:качества|соответствия)|путевой\s+лист', header, _FLAGS):
        warn('unsupported_document')
        return {'document_type': 'other', 'fields': fields, 'warnings': warnings}
    kind = _classify(lines) if document_type == 'auto' else document_type
    if kind == 'other':
        warn('document_type_not_recognized')

    # A document heading is distinct from referenced заявки/доверенности and the
    # printed approval decree date. Never take the first date anywhere on a page.
    heading = re.compile(r'(?:товарно[\s-]*транспортная|транспортная|товарная)\s+накладная|'
                         r'универсальн\w*\s+передаточн\w*\s+документ|счет[\s-]*фактура|'
                         r'(?:договор[\s-]*)?заявка', _FLAGS)
    number_pattern = re.compile(r'(?:№|\bN[oо]?\.?\s)\s*([\wА-Яа-я][\wА-Яа-я/.-]*)', _FLAGS)
    for line in lines:
        match = heading.search(line.text)
        if not match or line.y > 45:
            continue
        context, evidence = _context(line, match, lines)
        found = number_pattern.search(line.text[match.end():]) or number_pattern.search(context)
        is_request = bool(re.search(r'заявка', match[0], _FLAGS))
        if found:
            offer('request_number' if is_request and kind != 'request' else 'document_number', found[1], evidence)
            if is_request:
                offer('request_number', found[1], evidence)
        elif re.search(r'№|\bN\b', line.text[match.end():]) and re.match(r'[\w/.-]*\d[\w/.-]*(?:\s|$)', context):
            # A printed № and its value can be separate OCR cells.
            offer('request_number' if is_request and kind != 'request' else 'document_number', context.split()[0], evidence)
        elif context and re.fullmatch(r'[\w/-]{1,40}', context) and re.search(r'\d', context):
            offer('request_number' if is_request and kind != 'request' else 'document_number', context, evidence)
        if not is_request or kind == 'request':
            value = _date_value(context)
            if value:
                offer('document_date', value, evidence)
    for line in lines:
        if re.search(r'дата\s+(?:составления|документа|накладной)', line.text, _FLAGS):
            match = re.search(r'дата\s+(?:составления|документа|накладной)', line.text, _FLAGS)
            context, evidence = _context(line, match, lines)
            value = _date_value(context)
            # Three spatial date cells may be OCRed as 29 10 2026.
            if not value and re.fullmatch(r'\d{1,2}\s+\d{1,2}\s+\d{4}', context):
                value = _date_value('.'.join(context.split()))
            if value:
                offer('document_date', value, evidence)

    # Role blocks have their own INN/KPP and never share global tax-id matches.
    role_labels = [(line, key, _role_label(line.text, regex)) for line in lines
                   for key, regex in _ROLE_KEYS if _role_label(line.text, regex)]
    for line, role, match in role_labels:
        # Signature blocks and instructions are not company identity labels.
        if re.search(r'груз\s+получил|груз\s+сдал|подпись|расшифровка', line.text, _FLAGS):
            continue
        tail = _clean(line.text[match.end():])
        # A role followed by another role on the same line is ambiguous.
        next_role = _ROLE.search(tail)
        if next_role and re.match(r'\s*:', tail[next_role.end():]):
            tail = tail[:next_role.start()].strip(' ,;')
        block = [line]
        payload = tail
        if not _ORG.search(payload):
            same_page_labels = [item[0] for item in role_labels if item[0].page == line.page and item[0] is not line]
            lower = max([other.cy for other in same_page_labels if other.cy < line.cy - 0.5], default=line.cy - 10)
            upper = min([other.cy for other in same_page_labels if other.cy > line.cy + 0.5], default=line.cy + 10)
            candidates = [other for other in lines if other.page == line.page and other is not line
                          and line.cy - 2.8 <= other.cy <= line.cy + 3.0
                          and (lower + line.cy) / 2 < other.cy < (upper + line.cy) / 2
                          and other.x >= line.x and _ORG.search(other.text)
                          and not _ROLE.search(other.text)]
            if candidates:
                candidate = min(candidates, key=lambda item: (abs(item.cy - line.cy), item.x))
                payload = candidate.text
                block.append(candidate)
        org = _ORG.search(payload)
        if not org:
            continue
        # Name ends before address/tax/bank details; retain OCR spelling.
        name = payload[org.start():]
        stop = re.search(r',?\s*(?:ИНН|ЙНН|КПП|р/с|тел\.?|\b\d{2}[\dоОoO]{4}\b|\bг\.?\s+|адрес\s*:)', name, _FLAGS)
        if stop:
            name = name[:stop.start()]
        quoted = re.search(r'[«"“][^«»"“”]+[»"”]', name)
        if quoted:
            name = name[:quoted.end()]
        name = name.strip(' ,;')
        if len(name) > 3 and not _FORM_HINT.search(name):
            offer(f'{role}_name', name, block)
        if re.search(r'\b[ОO0]{3}\b', payload, _FLAGS) and re.search(r'\b[ОO0]*0[ОO0]*\b', payload, _FLAGS):
            warn(f'ocr_organization_zero_confusion:{role}_name')
        # The name line and immediately adjacent explicit tax-id line only.
        for other in lines:
            if (other.page == line.page and other not in block
                    and other.x >= line.x and abs(other.cy - block[-1].cy) < 2
                    and re.match(r'\s*ИНН\b', other.text, _FLAGS)
                    and not _ROLE.search(other.text)):
                # Avoid a tax line spatially closer to a neighboring role label.
                if not any(abs(label.cy - other.cy) < abs(line.cy - other.cy)
                           for label, _, _ in role_labels if label.page == line.page and label is not line):
                    block.append(other)
        full = ' '.join(item.text for item in block)
        found = _INN.search(full)
        if found:
            offer(f'{role}_inn', found[1], block)
            if not _inn_valid(found[1]):
                warn(f'inn_checksum_failed:{role}_inn')
        if f'{role}_kpp' in fields:
            found = _KPP.search(full)
            if not found:
                found = re.search(r'ИНН\s*/\s*КПП\s*[:№]?\s*\d{10}(?:\d{2})?\s*/\s*(\d{9})(?!\d)', full, _FLAGS)
            if found:
                offer(f'{role}_kpp', found[1], block)
        address = re.search(r'(?:адрес\s*:\s*|(?:\b\d{6},?\s*)?\bг\.?\s+)(.+)', payload, _FLAGS)
        if address:
            value = payload[address.start():]
            value = re.split(r'\b(?:ИНН|ЙНН|КПП|тел\.?|р/с)\b', value, maxsplit=1, flags=_FLAGS)[0]
            offer(f'{role}_address', _clean(re.sub(r'^адрес\s*:', '', value, flags=_FLAGS)), block)

    specs = (
        ('loading_address', r'(?:адрес|пункт|место)\s+(?:погрузки|загрузки)|погрузка\s*:'),
        ('unloading_address', r'(?:адрес|пункт|место)\s+(?:выгрузки|разгрузки)|разгрузка\s*:'),
        ('cargo_description', r'(?:наименование|описание)\s+(?:груза|товара)|груз\s*:'),
        ('driver_name', r'(?:водитель(?:\s*\([^)]*\))?|ФИО\s+водителя)\s*[:=]?'),
    )
    for field, pattern in specs:
        regex = re.compile(pattern, _FLAGS)
        for line in lines:
            match = regex.search(line.text)
            if not match:
                continue
            value, evidence = _context(line, match, lines, below=True)
            if field in {'loading_address', 'unloading_address'}:
                value = re.split(r'(?:адрес|пункт|место)\s+(?:погрузки|выгрузки|загрузки|разгрузки)|\bмаршрут\b', value, maxsplit=1, flags=_FLAGS)[0].strip()
            if field == 'cargo_description' and (value.startswith('(') or '|' in value):
                continue
            if len(value) < 3 or _BLANK.fullmatch(value) or _FORM_HINT.search(value):
                continue
            if field == 'driver_name':
                name = re.search(r'([А-ЯЁ][а-яё-]+\s+(?:[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+|[А-ЯЁ]\.\s*[А-ЯЁ]\.))', value)
                if not name:
                    continue
                value = name[1]
            offer(field, value, evidence)

    # For a narrow table column, retain a single readable product cell below its
    # header. Quantities/units are deliberately not inferred as cargo mass.
    table_hints = re.compile(r'выполненн|оказанн|имущественн|услуг|работ|предъяв|акциз|налог|страна|происхожден|колич|упаков|всего|номер|условн|измерен|наименован|продукци|обозна|^код\b', _FLAGS)
    if kind in {'upd', 'torg12', 'ttn'} and fields['cargo_description']['value'] is None:
        for label in lines:
            if not re.search(r'наименование\s+(?:товара|груза|продукции)', label.text, _FLAGS) or label.box[2] > 35:
                continue
            for candidate in lines:
                if (candidate.page == label.page and label.y + label.box[3] < candidate.y < label.y + label.box[3] + 16
                        and label.x - 1 <= candidate.x <= label.right
                        and candidate.right <= label.right + 3
                        and len(re.findall(r'[А-Яа-яЁё]', candidate.text)) >= 4
                        and not candidate.text.startswith('(') and not table_hints.search(candidate.text)):
                    offer('cargo_description', candidate.text, [label, candidate])

    for field, pattern in (
        ('vehicle_number', r'(?:гос\.?\s*(?:номер|№)|государственный\s+(?:номер|регистрационный\s+номер)|автомобиль|тягач)\s*[:=]?'),
        ('trailer_number', r'(?:полуприцеп|прицеп)(?:\s*(?:№|номер))?\s*[:=]?'),
    ):
        for line in lines:
            match = re.search(pattern, line.text, _FLAGS)
            if not match or (field == 'vehicle_number' and re.search(r'прицеп', line.text, _FLAGS)):
                continue
            context, evidence = _context(line, match, lines)
            plate = re.search(r'\b([АВЕКМНОРСТУХABEKMHOPCTYX]\s*\d{3}\s*[АВЕКМНОРСТУХABEKMHOPCTYX]{2}\s*\d{2,3}|[АВЕКМНОРСТУХABEKMHOPCTYX]{2}\s*\d{4}\s*\d{2,3})\b', context, _FLAGS)
            if plate:
                # Keep Cyrillic/Latin spelling exactly; visually similar letters
                # cannot safely be disambiguated by OCR alone.
                offer(field, re.sub(r'\s+', '', plate[1]).upper(), evidence)

    datetime_specs = (
        ('planned_pickup_datetime', r'(?:планов\w*\s+(?:дата\s+и\s+время\s+)?(?:погрузк[аи]|подач[аи])|дата\s+и\s+время\s+погрузки)'),
        ('planned_delivery_datetime', r'(?:планов\w*\s+(?:дата\s+и\s+время\s+)?(?:доставк[аи]|выгрузк[аи])|дата\s+и\s+время\s+выгрузки)'),
        ('actual_arrival_datetime', r'(?:фактическ\w*\s+(?:дата\s+и\s+время\s+)?(?:прибытия|прибытие)|прибытие\s+факт\.?|время\s+прибытия)'),
        ('actual_departure_datetime', r'(?:фактическ\w*\s+(?:дата\s+и\s+время\s+)?(?:убытия|убытие)|убытие\s+факт\.?|время\s+убытия)'),
    )
    for field, pattern in datetime_specs:
        for line in lines:
            match = re.search(pattern, line.text, _FLAGS)
            if match:
                context, evidence = _context(line, match, lines)
                offer(field, _date_value(context, with_time=True), evidence)

    # Mass requires an explicit cargo-mass label and unit. Column quantities,
    # vehicle capacity, density and volumes never become cargo weight.
    mass_label = re.compile(r'(?:масса\s+(?:груза|брутто|нетто)|вес\s+(?:груза|брутто|нетто)|общая\s+масса)', _FLAGS)
    for line in lines:
        match = mass_label.search(line.text)
        if not match or re.search(r'грузоподъемност|плотност|кг\s*/|кг/|т\s*/|объем', line.text, _FLAGS):
            continue
        context, evidence = _context(line, match, lines)
        mass = re.search(r'(' + _NUMBER + r')\s*(кг|килограмм\w*|т(?:онн\w*)?)(?![а-яё/³\d])', context, _FLAGS)
        if not mass:
            # Header carries the unit, the immediately aligned cell the value.
            unit = re.match(r'\s*[,(:]?\s*(кг|т)\s*[).,:]?\s*$', line.text[match.end():], _FLAGS)
            if unit:
                neighbors = _neighbors(line, lines)
                if len(neighbors) == 1 and re.fullmatch(_NUMBER, neighbors[0].text):
                    mass = re.match(r'(' + _NUMBER + r')\s*(кг|т)', neighbors[0].text + ' ' + unit[1], _FLAGS)
                    evidence = [line, *neighbors]
        if mass:
            offer('cargo_mass', normalize_decimal(mass[1]), evidence)
            offer('cargo_mass_unit', 'kg' if mass[2].lower().startswith(('кг', 'кил')) else 't', evidence)

    numeric_specs = (
        ('package_count', r'(?:количество|кол-во|число)\s+(?:грузовых\s+)?мест'),
        ('freight_amount', r'(?:стоимость|сумма|цена)\s+(?:перевозки|транспортных\s+услуг)|провозная\s+плата|фрахт\s*:'),
        ('cargo_value', r'(?:объявленная\s+стоимость|стоимость|ценность)\s+(?:груза|товара)|всего\s+к\s+оплате|итого\s+с\s+НДС|всего\s+по\s+накладной'),
        ('vat_amount', r'(?:сумма\s+НДС|НДС\s+в\s+сумме|в\s+том\s+числе\s+НДС)'),
    )
    money_evidence = []
    for field, pattern in numeric_specs:
        for line in lines:
            match = re.search(pattern, line.text, _FLAGS)
            if not match:
                continue
            if re.match(r'\s*[:=]?\s*[-−]\s*\d', line.text[match.end():]):
                warn(f'negative_value_requires_review:{field}')
                continue
            context, evidence = _context(line, match, lines)
            if field == 'cargo_value' and kind == 'ttn' and re.search(r'всего\s+к\s+оплате', match[0], _FLAGS) and not re.search(r'за\s+товар', line.text, _FLAGS):
                # In form 1-T this grand total can include warehouse/transport
                # charges. It is neither the goods subtotal nor provable freight.
                warn('ttn_grand_total_includes_possible_charges')
                continue
            if field == 'cargo_value' and re.search(r'всего\s+по\s+накладной', match[0], _FLAGS):
                section = [item for item in lines if item.page == line.page and item.y < line.y and re.search(r'(?:товарный|транспортный)\s+раздел', item.text, _FLAGS)]
                if kind != 'ttn' or not section or not re.search(r'товарный\s+раздел', max(section, key=lambda item: item.y).text, _FLAGS):
                    continue
                # The quantity column can contain 8.000, so require a unique
                # two-decimal monetary cell in the goods subtotal row.
                amounts = [(normalize_decimal(item[1]), item) for item in _MONEY.finditer(context) if re.search(r'[,.]\d{2}$', item[1])]
                if len({value for value, _ in amounts}) == 1:
                    offer(field, amounts[0][0], evidence)
                    money_evidence.extend(evidence)
                continue
            # A bare generic total in a request could be freight; do not choose.
            if field == 'cargo_value' and kind not in {'torg12', 'upd', 'ttn'} and re.search(r'всего\s+к|итого', match[0], _FLAGS):
                continue
            if field == 'vat_amount':
                context = re.sub(r'^\s*\d+(?:[,.]\d+)?\s*%\s*[:=]?', '', context)
            number = _MONEY.search(context)
            if number:
                value = normalize_decimal(number[1])
                if field == 'package_count' and (value is None or not Decimal(value) == Decimal(value).to_integral_value()):
                    continue
                offer(field, value, evidence)
                if field in {'freight_amount', 'cargo_value', 'vat_amount'}:
                    money_evidence.extend(evidence)
    for line in lines:
        rate = re.search(r'(?:ставка\s+)?НДС\s*[:=]?\s*(\d{1,2}(?:[,.]\d+)?)\s*%', line.text, _FLAGS)
        if rate:
            offer('vat_rate', normalize_decimal(rate[1]), [line])
        elif re.search(r'без\s+НДС', line.text, _FLAGS):
            # Exemption is not a numeric zero tax rate.
            warn('vat_exempt_text_present')
    # Currency requires an explicit marker; never assume RUB from document language.
    currency_evidence = list(money_evidence)
    for line in lines:
        match = re.search(r'\bвалюта\b.*?(?::\s*(?:наименование,?\s*код)?)?$', line.text, _FLAGS)
        if match:
            currency_evidence.extend([line, *_neighbors(line, lines)])
    for line in dict.fromkeys(currency_evidence):
        currencies = set()
        if re.search(r'\bруб(?:\.|лей|ля)?\b|₽|\bRUB\b|российский\s+рубль', line.text, _FLAGS):
            currencies.add('RUB')
        if re.search(r'\bUSD\b|доллар|\$', line.text, _FLAGS):
            currencies.add('USD')
        if re.search(r'\bEUR\b|евро|€', line.text, _FLAGS):
            currencies.add('EUR')
        for currency in currencies:
            offer('currency', currency, [line])

    for field, pattern in (
        ('request_number', r'(?:договор[\s-]*)?заявк[аи]\s*(?:№|N[oо]?\.?)\s*([\wА-Яа-я/.-]+)'),
        ('supporting_document_number', r'(?:сопроводительн\w*\s+документ|товарная\s+накладная|доверенность)\s*(?:№|N[oо]?\.?)\s*([\wА-Яа-я/.-]+)'),
    ):
        for line in lines:
            match = re.search(pattern, line.text, _FLAGS)
            if match:
                # The current document header is not its own supporting document.
                if field == 'supporting_document_number' and line.y < 35 and heading.search(line.text):
                    continue
                offer(field, match[1], [line])

    if any(line.confidence is not None and line.confidence < 0.65 for line in lines):
        warn('low_confidence_ocr_present')
    if not any(field['value'] is not None for field in fields.values()):
        warn('no_fields_extracted')
    return {'document_type': kind, 'fields': fields, 'warnings': warnings}
