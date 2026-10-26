"""Настоящая production SPA + живой Ninja API на отдельной pytest-БД.

Тестовый origin раздаёт бандл и проксирует /api как Nginx. Он не внедряет
фиктивные ответы: роли, записи и финансовые расчёты проходят через Django.
"""
import functools
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import re
from datetime import timedelta
from django.utils import timezone
from accounts.models import User
from marketplace.models import OfferClickLog

import pytest
from playwright.sync_api import expect

from logistics.demo import seed_demo_company
from logistics.models import Client, Financial, Order

pytestmark = [pytest.mark.integration, pytest.mark.browser, pytest.mark.django_db(transaction=True)]
PASSWORD = 'Browser-demo-password-42!'


@pytest.fixture
def spa_origin(live_server):
    dist = Path(os.environ.get('SPA_DIST', Path(__file__).resolve().parents[2] / 'frontend-web' / 'dist'))
    if not (dist / 'index.html').exists():
        pytest.fail('Production SPA отсутствует: выполните npm run build --prefix frontend-web или соберите Docker test.')

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path.startswith('/api/'):
                return self.proxy()
            # Прямая ссылка /orders/{uuid} возвращает index.html, как try_files в Nginx.
            if not Path(self.translate_path(self.path)).is_file():
                self.path = '/index.html'
            return super().do_GET()

        def proxy(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0))) if self.command != 'GET' else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in {'host', 'content-length', 'connection', 'accept-encoding'}}
            request = Request(live_server.url + self.path, data=body, headers=headers, method=self.command)
            try:
                response = urlopen(request, timeout=20)
            except HTTPError as error:
                response = error
            with response:
                self.send_response(response.status)
                for name, value in response.headers.items():
                    if name.lower() not in {'transfer-encoding', 'connection', 'date', 'server'}:
                        self.send_header(name, value)
                self.end_headers()
                self.wfile.write(response.read())

        do_POST = do_PUT = do_PATCH = do_DELETE = proxy

    server = ThreadingHTTPServer(('localhost', 0), functools.partial(Handler, directory=str(dist)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://localhost:{server.server_port}'
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


@pytest.fixture
def showroom():
    return seed_demo_company(slug='spa-browser', password=PASSWORD)


def login(page, origin, email):
    page.goto(origin + '/login')
    expect(page.get_by_role('heading', name='С возвращением')).to_be_visible()
    capture(page, f'login-{page.viewport_size["width"]}')
    page.get_by_label('Рабочий email', exact=True).fill(email)
    page.get_by_label('Пароль', exact=True).fill(PASSWORD)
    page.get_by_role('button', name='Войти в Flowgic').click()
    expect(page.get_by_role('heading', name='Перевозки под контролем')).to_be_visible()


def capture(page, name):
    directory = os.environ.get('SPA_SCREENSHOTS')
    if directory:
        Path(directory).mkdir(parents=True, exist_ok=True)
        page.evaluate('window.scrollTo(0, 0)')
        expect(page.locator('.ant-spin-spinning')).to_have_count(0, timeout=8000)
        expect(page.locator('.ant-message-notice')).to_have_count(0, timeout=8000)
        page.screenshot(path=str(Path(directory) / f'{name}.png'), full_page=True, animations='disabled')


def test_spa_login_filter_calendar_detail_finance_download_and_reload(page, spa_origin, showroom):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    login(page, spa_origin, showroom.login_emails[1])
    expect(page.get_by_role('table')).to_be_visible()
    capture(page, 'orders')
    page.get_by_role('combobox', name='Фильтр статуса').click()
    page.get_by_title('Завершён', exact=True).click()
    expect(page.locator('.orders-panel .ant-table-row')).to_have_count(2)
    page.get_by_role('button', name='Календарь', exact=True).click()
    expect(page.get_by_role('dialog', name='Календарь перевозок')).to_be_visible()
    expect(page.locator('.calendar-order').first).to_be_visible()
    capture(page, 'calendar')
    page.locator('.ant-modal-close').click()
    page.locator('.order-number').first.click()
    expect(page.get_by_role('heading', name='Маршрут и груз')).to_be_visible()
    page.get_by_label('Выплата водителю, ₽', exact=True).fill('25000')
    page.get_by_role('button', name='Рассчитать', exact=True).click()
    expect(page.get_by_text('ещё не сохранено', exact=False)).to_be_visible()
    page.get_by_role('button', name='Сохранить расчёт', exact=True).click()
    expect(page.get_by_text('Финансовый расчёт сохранён', exact=True)).to_be_visible()
    order_id = page.url.rsplit('/', 1)[1]
    assert Financial.objects.filter(order__client__company=showroom.company, order_id=order_id).get().driver_cost == 25000
    page.get_by_role('combobox', name='Статус заказа').click()
    page.get_by_title('В пути', exact=True).click()
    expect(page.get_by_text('Статус обновлён', exact=True)).to_be_visible()
    with page.expect_download() as download:
        page.get_by_role('button', name='Скачать заявку', exact=True).click()
    assert download.value.suggested_filename.endswith('-application.docx')
    with page.expect_download() as download:
        page.get_by_role('button', name='ТТН DOCX', exact=True).click()
    assert download.value.suggested_filename.endswith('-ttn.docx')
    expect(page.get_by_role('region', name='Партнёрские предложения')).to_be_visible()
    capture(page, 'order-detail')
    # Подменяется только внешний сайт партнёра, наш API и запись клика остаются реальными.
    page.context.route('https://example.com/**', lambda route: route.fulfill(status=200, body='Demo partner'))
    with page.expect_popup() as opened:
        page.get_by_role('button', name='Подробнее', exact=True).first.click()
    opened.value.wait_for_url(re.compile(r'https://example.com/.*'))
    opened.value.close()
    assert OfferClickLog.objects.filter(company=showroom.company, order_id=order_id).count() == 1
    page.reload()
    expect(page.get_by_role('heading', name='Маршрут и груз')).to_be_visible()
    page.get_by_role('button', name='Выйти', exact=True).click()
    expect(page.get_by_role('heading', name='С возвращением')).to_be_visible()
    assert page.evaluate("sessionStorage.getItem('flowgic.session.v1')") is None
    assert not errors


def test_spa_directories_quota_and_company_switch(page, spa_origin, showroom):
    login(page, spa_origin, showroom.login_emails[1])
    page.get_by_role('link', name='Клиенты', exact=True).click()
    page.get_by_role('button', name='Добавить клиента', exact=True).click()
    page.get_by_label('Название клиента', exact=True).fill('Клиент из SPA')
    page.get_by_label('Email', exact=True).fill('spa-client@example.test')
    page.get_by_role('button', name='Сохранить', exact=True).click()
    expect(page.get_by_text('Клиент из SPA', exact=True)).to_be_visible()
    assert Client.objects.filter(company=showroom.company, name='Клиент из SPA').exists()
    capture(page, 'clients')
    page.get_by_role('link', name='Заказы', exact=True).click()
    page.get_by_role('button', name='Новый заказ', exact=True).click()
    page.get_by_label('Клиент', exact=True).click()
    page.get_by_title('Клиент из SPA', exact=True).click()
    page.get_by_label('Груз', exact=True).fill('Тестовая перевозка SPA')
    for label, days in [('Погрузка', 1), ('Доставка', 2)]:
        field = page.get_by_label(label, exact=True)
        field.fill((timezone.now() + timedelta(days=days)).strftime('%d.%m.%Y %H:%M'))
        field.press('Enter')
    page.get_by_role('button', name='Создать заказ', exact=True).click()
    expect(page.get_by_role('heading', name='Маршрут и груз')).to_be_visible()
    assert Order.objects.filter(client__company=showroom.company, cargo_type='Тестовая перевозка SPA').exists()
    page.get_by_role('link', name='Водители', exact=True).click()
    page.get_by_role('button', name='Добавить водителя', exact=True).click()
    page.get_by_label('ФИО водителя', exact=True).fill('Водитель из SPA')
    page.get_by_label('Email', exact=True).fill('spa-driver@example.test')
    page.get_by_label('Начальный пароль', exact=True).fill(PASSWORD)
    page.get_by_role('button', name='Сохранить', exact=True).click()
    expect(page.get_by_text('Водитель из SPA', exact=True)).to_be_visible()
    assert User.objects.filter(company=showroom.company, email='spa-driver@example.test', role='driver').exists()
    page.get_by_role('link', name='Транспорт', exact=True).click()
    page.get_by_role('button', name='Добавить транспорт', exact=True).click()
    for label, value in [('Госномер', 'SPA-QUOTA'), ('Тип транспорта', 'Фура'), ('Грузоподъёмность, кг', '20000')]:
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role('button', name='Сохранить', exact=True).click()
    expect(page.get_by_role('dialog', name='Достигнут лимит тарифа', exact=True)).to_be_visible()
    capture(page, 'quota')
    page.get_by_role('button', name='Посмотреть тарифы', exact=True).click()
    expect(page.get_by_role('heading', name='Тариф и использование')).to_be_visible()
    page.get_by_role('button', name='Выйти', exact=True).click()
    page.get_by_role('link', name='Создать компанию', exact=True).click()
    page.get_by_label('Ваше имя', exact=True).fill('Новый руководитель')
    page.get_by_label('Название компании', exact=True).fill('Другая компания SPA')
    page.get_by_label('Рабочий email', exact=True).fill('new-spa-owner@example.test')
    page.get_by_label('Пароль', exact=True).fill(PASSWORD)
    page.get_by_role('button', name='Создать рабочее пространство', exact=True).click()
    expect(page.get_by_role('heading', name='Перевозки под контролем')).to_be_visible()
    expect(page.get_by_text('Пока нет заказов', exact=True)).to_be_visible()
    page.get_by_role('link', name='Клиенты', exact=True).click()
    expect(page.get_by_text('Клиент из SPA', exact=True)).to_have_count(0)


def test_spa_mobile_navigation_and_driver_guard(page, spa_origin, showroom):
    page.set_viewport_size({'width': 390, 'height': 844})
    login(page, spa_origin, showroom.login_emails[1])
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    capture(page, 'mobile')
    page.get_by_role('button', name='Открыть навигацию').click()
    page.get_by_role('link', name='Водители', exact=True).last.click()
    expect(page.get_by_role('heading', name='Водители', exact=True).first).to_be_visible()
    page.get_by_role('button', name='Открыть навигацию').click()
    page.get_by_role('button', name='Выйти', exact=True).last.click()
    expect(page.get_by_role('heading', name='С возвращением')).to_be_visible()
    page.get_by_label('Рабочий email', exact=True).fill(showroom.login_emails[2])
    page.get_by_label('Пароль', exact=True).fill(PASSWORD)
    page.get_by_role('button', name='Войти в Flowgic').click()
    expect(page.get_by_text('Кабинет команды', exact=True)).to_be_visible()
