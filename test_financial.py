import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.flowgic.settings')
django.setup()

from logistics.models import Order, Financial, Client, Company, Vehicle
from accounts.models import User
from django.contrib.auth.models import User as AuthUser

# Create test data
company = Company.objects.create(name='Test Company', inn='1234567890', type='logistics')
client = Client.objects.create(company=company, name='Test Client', phone='1234567890', email='test@example.com')
user = User.objects.create_user(username='testuser', email='test@example.com', password='password', role='dispatcher', company=company)
vehicle = Vehicle.objects.create(company=company, reg_number='TEST123', type='truck', capacity_kg=10000)

# Create order
order = Order.objects.create(
    client=client,
    created_by=user,
    vehicle=vehicle,
    cargo_type='Test Cargo',
    cargo_mass_kg=5000,
    origin='Moscow',
    destination='SPB',
    agreed_price=Decimal('10000.00'),
    pickup_datetime='2023-01-01 10:00:00',
    delivery_datetime='2023-01-01 15:00:00',
    distance_km=Decimal('700.00')
)

# Create financial record
financial = Financial.objects.create(
    order=order,
    client_cost=Decimal('10000.00'),
    driver_cost=Decimal('2000.00'),
    fuel_expenses=Decimal('1500.00')
)

print(f"Initial profit: {financial.profit}")

# Update expenses
financial.fuel_expenses = Decimal('2000.00')
financial.driver_cost = Decimal('2500.00')
financial.save()

print(f"Updated profit: {financial.profit}")

# Test with text inputs (simulate parsing)
def parse_decimal(value):
    try:
        return Decimal(value.replace(',', '.'))
    except:
        return Decimal('0.00')

# Simulate form input
fuel_input = '2,500.50'
driver_input = '3 000'

financial.fuel_expenses = parse_decimal(fuel_input)
financial.driver_cost = parse_decimal(driver_input)
financial.save()

print(f"Profit after text input simulation: {financial.profit}")

# Clean up
financial.delete()
order.delete()
vehicle.delete()
user.delete()
client.delete()
company.delete()

print("Test completed successfully")
