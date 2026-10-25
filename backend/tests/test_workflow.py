import pytest
import re
from playwright.sync_api import Page, expect
from django.contrib.auth import get_user_model
from django.test import LiveServerTestCase
from logistics.models import Company, Client
from accounts.models import User

User = get_user_model()

@pytest.mark.e2e
@pytest.mark.browser
class TestDispatcherOrderWorkflowPlaywright:
    """E2E-тест с Playwright: создание заказа диспетчером"""

    def test_dispatcher_creates_order_via_ui(
        self, 
        live_server, 
        page: Page, 
        dispatcher_a, 
        client_a
    ):
        # 1. Логинимся
        page.goto(f"{live_server.url}/login/")
        page.fill("input[name='email']", dispatcher_a.email)
        page.fill("input[name='password']", "testpass123")
        page.click("button[type='submit']")
        
        # 2. Проверяем, что попали на дашборд
        expect(page).to_have_url(f"{live_server.url}/home/")

        # 3. Переходим на создание заказа
        page.goto(f"{live_server.url}/logistics/new/")

        # 4. Заполняем форму
        page.select_option("select[name='client']", str(client_a.id_client))
        page.fill("input[name='cargo_type']", "Electronics")
        page.fill("input[name='cargo_mass_kg']", "1000")
        page.fill("input[name='origin']", "Moscow")
        page.fill("input[name='destination']", "Krasnoyarsk")
        page.fill("input[name='agreed_price']", "25000.00")
        
        # Устанавливаем даты (формат должен совпадать с вашим)
        pickup = (page.evaluate("() => new Date(Date.now() + 86400000).toISOString().slice(0, 16)"))
        delivery = (page.evaluate("() => new Date(Date.now() + 172800000).toISOString().slice(0, 16)"))
        page.fill("input[name='pickup_datetime']", pickup)
        page.fill("input[name='delivery_datetime']", delivery)

        page.select_option("select[name='status']", "created")

        # 5. Отправляем
        page.click("button[type='submit']")

        # 6. Проверяем успех
        expect(page).to_have_url(re.compile(r'.*/logistics/request/[0-9a-f-]+/'))
        expect(page.locator('body')).to_contain_text('Electronics')

        # 7. Проверяем, что заказ есть в БД
        from logistics.models import Order
        assert Order.objects.filter(client=client_a).exists()
