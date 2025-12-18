import pytest
import os
import re
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from logistics.models import Company, Client, Vehicle, Order, Financial, OrderEvent
from accounts.models import User

# Allow Django ORM operations in async context (required for Playwright tests)
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

User = get_user_model()


@pytest.fixture
def company_a(db):
    """Create a test company A"""
    return Company.objects.create(
        name='Company A',
        inn='1234567890',
        type=Company.Type.LOGISTICS,
        address={
            'region': 'Moscow',
            'city': 'Moscow',
            'street': 'Test Street 1',
            'building': '1',
            'postcode': '123456'
        }
    )


@pytest.fixture
def company_b(db):
    """Create a test company B for isolation testing"""
    return Company.objects.create(
        name='Company B',
        inn='0987654321',
        type=Company.Type.LOGISTICS,
        address={
            'region': 'SPB',
            'city': 'Saint Petersburg',
            'street': 'Test Street 2',
            'building': '2',
            'postcode': '654321'
        }
    )


@pytest.fixture
def dispatcher_a(db, company_a):
    """Create a dispatcher for company A"""
    user = User(
        email='dispatcher_a@test.com',
        company=company_a,
        role=User.Role.Dispatcher,
        full_name='Dispatcher A',
        phone='1234567890',
        status=User.Status.ACTIVE
    )
    user.set_password('testpass123')
    user.save()
    return user


@pytest.fixture
def manager_a(db, company_a):
    """Create a manager for company A"""
    user = User(
        email='manager_a@test.com',
        company=company_a,
        role=User.Role.Manager,
        full_name='Manager A',
        phone='1234567891',
        status=User.Status.ACTIVE
    )
    user.set_password('testpass123')
    user.save()
    return user


@pytest.fixture
def driver_a(db, company_a):
    """Create a driver for company A"""
    user = User(
        email='driver_a@test.com',
        company=company_a,
        role=User.Role.Driver,
        full_name='Driver A',
        phone='1234567892',
        status=User.Status.ACTIVE
    )
    user.set_password('testpass123')
    user.save()
    return user


@pytest.fixture
def dispatcher_b(db, company_b):
    """Create a dispatcher for company B"""
    user = User(
        email='dispatcher_b@test.com',
        company=company_b,
        role=User.Role.Dispatcher,
        full_name='Dispatcher B',
        phone='2234567890',
        status=User.Status.ACTIVE
    )
    user.set_password('testpass123')
    user.save()
    return user


@pytest.fixture
def driver_b(db, company_b):
    """Create a driver for company B"""
    user = User(
        email='driver_b@test.com',
        company=company_b,
        role=User.Role.Driver,
        full_name='Driver B',
        phone='2234567892',
        status=User.Status.ACTIVE
    )
    user.set_password('testpass123')
    user.save()
    return user


@pytest.fixture
def client_a(db, company_a):
    """Create a client for company A"""
    return Client.objects.create(
        company=company_a,
        name='Client A',
        phone='1111111111',
        email='client_a@test.com'
    )


@pytest.fixture
def client_b(db, company_b):
    """Create a client for company B"""
    return Client.objects.create(
        company=company_b,
        name='Client B',
        phone='2222222222',
        email='client_b@test.com'
    )


@pytest.fixture
def vehicle_a(db, company_a):
    """Create a vehicle for company A"""
    return Vehicle.objects.create(
        company=company_a,
        reg_number='A111AA77',
        type='Фура',
        model='Volvo FH16',
        capacity_kg=20000,
        status=Vehicle.Status.AVAILABLE
    )


@pytest.fixture
def vehicle_b(db, company_b):
    """Create a vehicle for company B"""
    return Vehicle.objects.create(
        company=company_b,
        reg_number='B222BB78',
        type='Газель',
        model='GAZelle Next',
        capacity_kg=5000,
        status=Vehicle.Status.AVAILABLE
    )


@pytest.fixture
def order_a(db, client_a, dispatcher_a, vehicle_a, driver_a):
    """Create an order for company A"""
    return Order.objects.create(
        client=client_a,
        created_by=dispatcher_a,
        vehicle=vehicle_a,
        driver=driver_a,
        status=Order.Status.CREATED,
        cargo_type='Electronics',
        cargo_mass_kg=5000,
        origin='Moscow',
        destination='Saint Petersburg',
        agreed_price=Decimal('50000.00'),
        pickup_datetime=timezone.now() + timedelta(days=1),
        delivery_datetime=timezone.now() + timedelta(days=2),
        distance_km=Decimal('700.00')
    )


@pytest.fixture
def order_b(db, client_b, dispatcher_b, vehicle_b, driver_b):
    """Create an order for company B"""
    return Order.objects.create(
        client=client_b,
        created_by=dispatcher_b,
        vehicle=vehicle_b,
        driver=driver_b,
        status=Order.Status.CREATED,
        cargo_type='Furniture',
        cargo_mass_kg=3000,
        origin='Saint Petersburg',
        destination='Kazan',
        agreed_price=Decimal('30000.00'),
        pickup_datetime=timezone.now() + timedelta(days=1),
        delivery_datetime=timezone.now() + timedelta(days=2),
        distance_km=Decimal('1200.00')
    )


@pytest.fixture
def financial_a(db, order_a):
    """Create financial record for order A"""
    return Financial.objects.create(
        order=order_a,
        client_cost=Decimal('50000.00'),
        driver_cost=Decimal('15000.00'),
        third_party_cost=Decimal('2000.00'),
        payment_status=Financial.PaymentStatus.UNPAID
    )


@pytest.fixture
def authenticated_client(client, dispatcher_a):
    """Return a Django test client authenticated as dispatcher A"""
    client.force_login(dispatcher_a)
    return client


@pytest.fixture
def driver_client(client, driver_a):
    """Return a Django test client authenticated as driver A"""
    client.force_login(driver_a)
    return client


@pytest.fixture
def manager_client(client, manager_a):
    """Return a Django test client authenticated as manager A"""
    client.force_login(manager_a)
    return client


# Browser-based test fixtures for Playwright
@pytest.fixture
def authenticated_browser_session(page, live_server, dispatcher_a, db):
    """
    Returns a Playwright page with an authenticated dispatcher session
    Logs in as dispatcher_a and navigates to home page
    """
    # Navigate to login page
    page.goto(f"{live_server.url}/login/")
    
    # Fill in login form
    page.fill('input[name="email"]', dispatcher_a.email)
    page.fill('input[name="password"]', 'testpass123')
    
    # Click login button
    page.click('button[type="submit"]')
    
    # Wait for navigation to complete
    page.wait_for_url(re.compile(r".*/home.*"), timeout=5000)
    
    return page


@pytest.fixture
def driver_browser_session(page, live_server, driver_a, db):
    """
    Returns a Playwright page with an authenticated driver session
    Logs in as driver_a
    """
    # Navigate to login page
    page.goto(f"{live_server.url}/login/")
    
    # Fill in login form
    page.fill('input[name="email"]', driver_a.email)
    page.fill('input[name="password"]', 'testpass123')
    
    # Click login button  
    page.click('button[type="submit"]')
    
    # Wait for navigation to complete
    page.wait_for_url(re.compile(r".*/home.*"), timeout=5000)
    
    return page
