"""
Unit tests for Logistics models
Tests financial operations, order logic, and model validations
"""
import pytest
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.utils import timezone
from datetime import timedelta

from logistics.models import (
    Company, Client, Vehicle, Order, Financial, OrderEvent, Document
)
from logistics.factories import (
    CompanyFactory, ClientFactory, VehicleFactory, OrderFactory, FinancialFactory
)


# ========================================
# Financial Model Tests
# ========================================

@pytest.mark.unit
class TestFinancialModel:
    """Unit tests for Financial model and operations"""
    
    def test_profit_calculation_basic(self, db, order_a):
        """Test basic profit calculation"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('10000.00'),
            driver_cost=Decimal('3000.00'),
            third_party_cost=Decimal('500.00'),
            fuel_expenses=Decimal('2000.00')
        )
        
        # Profit = client_cost - fuel_expenses - driver_cost
        expected_profit = Decimal('10000.00') - Decimal('2000.00') - Decimal('3000.00')
        assert financial.profit == expected_profit
        assert financial.profit == Decimal('5000.00')
    
    def test_profit_calculation_with_auto_fuel(self, db, client_a, dispatcher_a):
        """Test profit calculation with automatic fuel expense calculation"""
        # Create order with known distance
        order = Order.objects.create(
            client=client_a,
            created_by=dispatcher_a,
            cargo_type='Test',
            cargo_mass_kg=5000,
            origin='Moscow',
            destination='SPB',
            agreed_price=Decimal('50000.00'),
            pickup_datetime=timezone.now() + timedelta(days=1),
            delivery_datetime=timezone.now() + timedelta(days=2),
            distance_km=Decimal('700.00')  # 700 km
        )
        
        # Create financial without fuel_expenses (should auto-calculate)
        financial = Financial.objects.create(
            order=order,
            client_cost=Decimal('50000.00'),
            driver_cost=Decimal('15000.00'),
            third_party_cost=Decimal('2000.00')
        )
        
        # Expected fuel: (700 / 100) * 30 L/100km * 82 RUB/L = 17220
        expected_fuel = Decimal('17220.00')
        assert financial.fuel_expenses == expected_fuel
        
        # Profit should account for auto-calculated fuel
        expected_profit = Decimal('50000.00') - expected_fuel - Decimal('15000.00')
        assert financial.profit == expected_profit
    
    def test_profit_calculation_no_third_party_cost(self, db, order_a):
        """Test profit calculation without third-party costs"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('10000.00'),
            driver_cost=Decimal('4000.00'),
            fuel_expenses=Decimal('3000.00')
        )
        
        expected_profit = Decimal('10000.00') - Decimal('3000.00') - Decimal('4000.00')
        assert financial.profit == expected_profit
    
    def test_profit_recalculation_on_update(self, db, order_a):
        """Test that profit is recalculated when costs are updated"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('10000.00'),
            driver_cost=Decimal('3000.00'),
            fuel_expenses=Decimal('2000.00')
        )
        
        initial_profit = financial.profit
        assert initial_profit == Decimal('5000.00')
        
        # Update driver cost
        financial.driver_cost = Decimal('4000.00')
        financial.save()
        
        # Profit should decrease
        assert financial.profit == Decimal('4000.00')
        assert financial.profit < initial_profit
    
    def test_payment_status_transitions(self, db, order_a):
        """Test payment status transitions"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('10000.00'),
            driver_cost=Decimal('3000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        assert financial.payment_status == Financial.PaymentStatus.UNPAID
        
        # Update to partially paid
        financial.payment_status = Financial.PaymentStatus.PARTIALLY_PAID
        financial.save()
        assert financial.payment_status == Financial.PaymentStatus.PARTIALLY_PAID
        
        # Update to paid
        financial.payment_status = Financial.PaymentStatus.PAID
        financial.save()
        assert financial.payment_status == Financial.PaymentStatus.PAID
    
    def test_financial_one_to_one_with_order(self, db, order_a):
        """Test that Financial has one-to-one relationship with Order"""
        financial1 = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('10000.00'),
            driver_cost=Decimal('3000.00')
        )
        
        # Trying to create another financial for same order should fail
        with pytest.raises(IntegrityError):
            Financial.objects.create(
                order=order_a,
                client_cost=Decimal('20000.00'),
                driver_cost=Decimal('5000.00')
            )
    
    def test_fuel_expense_zero_when_no_distance(self, db, client_a, dispatcher_a):
        """Test fuel expense is zero when order has no distance"""
        order = Order.objects.create(
            client=client_a,
            created_by=dispatcher_a,
            cargo_type='Test',
            cargo_mass_kg=5000,
            origin='Local',
            destination='Local',
            agreed_price=Decimal('5000.00'),
            pickup_datetime=timezone.now() + timedelta(days=1),
            delivery_datetime=timezone.now() + timedelta(days=1),
            distance_km=None  # No distance
        )
        
        financial = Financial.objects.create(
            order=order,
            client_cost=Decimal('5000.00'),
            driver_cost=Decimal('2000.00')
        )
        
        assert financial.fuel_expenses == Decimal('0.00')
    
    def test_negative_profit_calculation(self, db, order_a):
        """Test profit calculation when costs exceed client cost (negative profit)"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('5000.00'),
            driver_cost=Decimal('4000.00'),
            fuel_expenses=Decimal('3000.00')
        )
        
        # Negative profit
        assert financial.profit == Decimal('-2000.00')


# ========================================
# Order Model Tests
# ========================================

@pytest.mark.unit
class TestOrderModel:
    """Unit tests for Order model"""
    
    def test_order_creation(self, db, client_a, dispatcher_a):
        """Test basic order creation"""
        order = Order.objects.create(
            client=client_a,
            created_by=dispatcher_a,
            cargo_type='Electronics',
            cargo_mass_kg=1000,
            origin='Moscow',
            destination='Kazan',
            agreed_price=Decimal('25000.00'),
            pickup_datetime=timezone.now() + timedelta(days=1),
            delivery_datetime=timezone.now() + timedelta(days=2),
            distance_km=Decimal('800.00')
        )
        
        assert order.id is not None
        assert order.status == Order.Status.CREATED
        assert order.cargo_type == 'Electronics'
        assert order.is_viewed_by_driver is False
    
    def test_order_status_transitions(self, db, order_a):
        """Test order status can be changed"""
        assert order_a.status == Order.Status.CREATED
        
        order_a.status = Order.Status.ASSIGNED
        order_a.save()
        assert order_a.status == Order.Status.ASSIGNED
        
        order_a.status = Order.Status.IN_TRANSIT
        order_a.save()
        assert order_a.status == Order.Status.IN_TRANSIT
        
        order_a.status = Order.Status.COMPLETED
        order_a.save()
        assert order_a.status == Order.Status.COMPLETED
    
    def test_order_cargo_property(self, db, order_a):
        """Test cargo property alias for cargo_type"""
        assert order_a.cargo == order_a.cargo_type
    
    def test_order_number_property(self, db, order_a):
        """Test order_number property returns short UUID"""
        order_number = order_a.order_number
        assert order_number is not None
        assert len(order_number) <= 8  # First part of UUID
        assert order_number.isupper()
    
    def test_order_driver_assignment(self, db, order_a, driver_a):
        """Test driver can be assigned to order"""
        order_a.driver = driver_a
        order_a.save()
        
        assert order_a.driver == driver_a
    
    def test_order_vehicle_assignment(self, db, order_a, vehicle_a):
        """Test vehicle can be assigned to order"""
        order_a.vehicle = vehicle_a
        order_a.save()
        
        assert order_a.vehicle == vehicle_a
    
    def test_order_viewed_by_driver_flag(self, db, order_a):
        """Test is_viewed_by_driver flag"""
        assert order_a.is_viewed_by_driver is False
        
        order_a.is_viewed_by_driver = True
        order_a.save()
        
        assert order_a.is_viewed_by_driver is True


# ========================================
# Vehicle Model Tests
# ========================================

@pytest.mark.unit
class TestVehicleModel:
    """Unit tests for Vehicle model"""
    
    def test_vehicle_creation(self, db, company_a):
        """Test basic vehicle creation"""
        vehicle = Vehicle.objects.create(
            company=company_a,
            reg_number='A777AA77',
            type='Фура',
            model='Volvo FH16',
            capacity_kg=25000,
            status=Vehicle.Status.AVAILABLE
        )
        
        assert vehicle.id is not None
        assert vehicle.reg_number == 'A777AA77'
        assert vehicle.status == Vehicle.Status.AVAILABLE
    
    def test_vehicle_status_changes(self, db, vehicle_a):
        """Test vehicle status transitions"""
        assert vehicle_a.status == Vehicle.Status.AVAILABLE
        
        vehicle_a.status = Vehicle.Status.IN_TRIP
        vehicle_a.save()
        assert vehicle_a.status == Vehicle.Status.IN_TRIP
        
        vehicle_a.status = Vehicle.Status.MAINTENANCE
        vehicle_a.save()
        assert vehicle_a.status == Vehicle.Status.MAINTENANCE
        
        vehicle_a.status = Vehicle.Status.BLOCKED
        vehicle_a.save()
        assert vehicle_a.status == Vehicle.Status.BLOCKED
    
    def test_vehicle_unique_reg_number_per_company(self, db, company_a):
        """Test that reg_number must be unique within a company"""
        Vehicle.objects.create(
            company=company_a,
            reg_number='UNIQUE123',
            type='Газель',
            capacity_kg=5000
        )
        
        # Trying to create another vehicle with same reg_number in same company
        with pytest.raises(IntegrityError):
            Vehicle.objects.create(
                company=company_a,
                reg_number='UNIQUE123',
                type='Фура',
                capacity_kg=10000
            )
    
    def test_vehicle_same_reg_number_different_companies(self, db, company_a, company_b):
        """Test that same reg_number can exist in different companies"""
        vehicle1 = Vehicle.objects.create(
            company=company_a,
            reg_number='SHARED123',
            type='Фура',
            capacity_kg=10000
        )
        
        # Same reg_number in different company should work
        vehicle2 = Vehicle.objects.create(
            company=company_b,
            reg_number='SHARED123',
            type='Газель',
            capacity_kg=5000
        )
        
        assert vehicle1.reg_number == vehicle2.reg_number
        assert vehicle1.company != vehicle2.company
    
    def test_vehicle_string_representation(self, db, vehicle_a):
        """Test __str__ method"""
        expected = f"{vehicle_a.reg_number} ({vehicle_a.type})"
        assert str(vehicle_a) == expected


# ========================================
# Client Model Tests
# ========================================

@pytest.mark.unit
class TestClientModel:
    """Unit tests for Client model"""
    
    def test_client_creation(self, db, company_a):
        """Test basic client creation"""
        client = Client.objects.create(
            company=company_a,
            name='Test Client Ltd',
            phone='+79991234567',
            email='client@test.com'
        )
        
        assert client.id_client is not None
        assert client.name == 'Test Client Ltd'
        assert client.company == company_a
    
    def test_client_optional_fields(self, db, company_a):
        """Test client can be created without phone/email"""
        client = Client.objects.create(
            company=company_a,
            name='Minimal Client'
        )
        
        assert client.phone in [None, '']
        assert client.email in [None, '']
    
    def test_client_string_representation(self, db, client_a):
        """Test __str__ method"""
        assert str(client_a) == client_a.name


# ========================================
# Company Model Tests
# ========================================

@pytest.mark.unit
class TestCompanyModel:
    """Unit tests for Company model"""
    
    def test_company_creation(self, db):
        """Test basic company creation"""
        company = Company.objects.create(
            name='Test Logistics LLC',
            inn='1234567890',
            type=Company.Type.LOGISTICS
        )
        
        assert company.id_company is not None
        assert company.name == 'Test Logistics LLC'
        assert company.type == Company.Type.LOGISTICS
    
    def test_company_with_address(self, db):
        """Test company creation with structured address"""
        address_data = {
            'region': 'Moscow Oblast',
            'city': 'Moscow',
            'street': 'Lenina Street',
            'building': '10A',
            'postcode': '125009'
        }
        
        company = Company.objects.create(
            name='Company with Address',
            inn='9876543210',
            type=Company.Type.MANUFACTURER,
            address=address_data
        )
        
        assert company.address == address_data
        assert company.address['city'] == 'Moscow'
    
    def test_company_string_representation(self, db, company_a):
        """Test __str__ method"""
        assert str(company_a) == company_a.name


# ========================================
# OrderEvent Model Tests
# ========================================

@pytest.mark.unit
class TestOrderEventModel:
    """Unit tests for OrderEvent model"""
    
    def test_order_event_creation(self, db, order_a):
        """Test creating order event"""
        event = OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.STATUS_CHANGED,
            event_data={
                'old_status': 'created',
                'new_status': 'assigned',
                'changed_by': 'dispatcher'
            }
        )
        
        assert event.id is not None
        assert event.order == order_a
        assert event.event_type == OrderEvent.EventType.STATUS_CHANGED
        assert 'old_status' in event.event_data
    
    def test_payment_updated_event(self, db, order_a):
        """Test payment update event"""
        event = OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'payment_status': 'paid',
                'amount': '50000.00'
            }
        )
        
        assert event.event_type == OrderEvent.EventType.PAYMENT_UPDATED
        assert event.event_data['payment_status'] == 'paid'
