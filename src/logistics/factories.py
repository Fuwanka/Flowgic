"""
Factory classes for generating test data
This can be used as an alternative to fixtures for more flexible test data generation
"""
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
import uuid

from logistics.models import Company, Client, Vehicle, Order, Financial, OrderEvent
from accounts.models import User


class CompanyFactory:
    """Factory for creating Company instances"""
    
    @staticmethod
    def create(name=None, inn=None, type=None, **kwargs):
        return Company.objects.create(
            name=name or f'Test Company {uuid.uuid4().hex[:8]}',
            inn=inn or f'{uuid.uuid4().int % 10**12:012d}',
            type=type or Company.Type.LOGISTICS,
            **kwargs
        )


class UserFactory:
    """Factory for creating User instances"""
    
    @staticmethod
    def create(email=None, role=None, company=None, **kwargs):
        if company is None:
            company = CompanyFactory.create()
        
        email = email or f'user_{uuid.uuid4().hex[:8]}@test.com'
        role = role or User.Role.Driver
        password = kwargs.pop('password', 'testpass123')
        
        user = User(
            email=email,
            company=company,
            role=role,
            full_name=kwargs.pop('full_name', f'Test User'),
            status=kwargs.pop('status', User.Status.ACTIVE),
            **kwargs
        )
        user.set_password(password)
        user.save()
        return user
    
    @staticmethod
    def create_dispatcher(company=None, **kwargs):
        return UserFactory.create(role=User.Role.Dispatcher, company=company, **kwargs)
    
    @staticmethod
    def create_manager(company=None, **kwargs):
        return UserFactory.create(role=User.Role.Manager, company=company, **kwargs)
    
    @staticmethod
    def create_driver(company=None, **kwargs):
        return UserFactory.create(role=User.Role.Driver, company=company, **kwargs)


class ClientFactory:
    """Factory for creating Client instances"""
    
    @staticmethod
    def create(company=None, name=None, **kwargs):
        if company is None:
            company = CompanyFactory.create()
        
        return Client.objects.create(
            company=company,
            name=name or f'Test Client {uuid.uuid4().hex[:8]}',
            phone=kwargs.pop('phone', f'+7{uuid.uuid4().int % 10**10:010d}'),
            email=kwargs.pop('email', f'client_{uuid.uuid4().hex[:8]}@test.com'),
            **kwargs
        )


class VehicleFactory:
    """Factory for creating Vehicle instances"""
    
    @staticmethod
    def create(company=None, reg_number=None, **kwargs):
        if company is None:
            company = CompanyFactory.create()
        
        reg_number = reg_number or f'T{uuid.uuid4().int % 1000:03d}XX77'
        
        return Vehicle.objects.create(
            company=company,
            reg_number=reg_number,
            type=kwargs.pop('type', 'Фура'),
            model=kwargs.pop('model', 'Test Model'),
            capacity_kg=kwargs.pop('capacity_kg', 10000),
            status=kwargs.pop('status', Vehicle.Status.AVAILABLE),
            **kwargs
        )


class OrderFactory:
    """Factory for creating Order instances"""
    
    @staticmethod
    def create(client=None, created_by=None, vehicle=None, driver=None, **kwargs):
        if client is None:
            company = CompanyFactory.create()
            client = ClientFactory.create(company=company)
        else:
            company = client.company
        
        if created_by is None:
            created_by = UserFactory.create_dispatcher(company=company)
        
        if vehicle is None:
            vehicle = VehicleFactory.create(company=company)
        
        if driver is None:
            driver = UserFactory.create_driver(company=company)
        
        return Order.objects.create(
            client=client,
            created_by=created_by,
            vehicle=vehicle,
            driver=driver,
            status=kwargs.pop('status', Order.Status.CREATED),
            cargo_type=kwargs.pop('cargo_type', 'Test Cargo'),
            cargo_mass_kg=kwargs.pop('cargo_mass_kg', 5000),
            origin=kwargs.pop('origin', 'Moscow'),
            destination=kwargs.pop('destination', 'SPB'),
            agreed_price=kwargs.pop('agreed_price', Decimal('10000.00')),
            pickup_datetime=kwargs.pop('pickup_datetime', timezone.now() + timedelta(days=1)),
            delivery_datetime=kwargs.pop('delivery_datetime', timezone.now() + timedelta(days=2)),
            distance_km=kwargs.pop('distance_km', Decimal('700.00')),
            **kwargs
        )


class FinancialFactory:
    """Factory for creating Financial instances"""
    
    @staticmethod
    def create(order=None, **kwargs):
        if order is None:
            order = OrderFactory.create()
        
        return Financial.objects.create(
            order=order,
            client_cost=kwargs.pop('client_cost', Decimal('10000.00')),
            driver_cost=kwargs.pop('driver_cost', Decimal('3000.00')),
            third_party_cost=kwargs.pop('third_party_cost', Decimal('500.00')),
            fuel_expenses=kwargs.pop('fuel_expenses', None),  # Will be auto-calculated
            payment_status=kwargs.pop('payment_status', Financial.PaymentStatus.UNPAID),
            **kwargs
        )


class OrderEventFactory:
    """Factory for creating OrderEvent instances"""
    
    @staticmethod
    def create(order=None, event_type=None, **kwargs):
        if order is None:
            order = OrderFactory.create()
        
        return OrderEvent.objects.create(
            order=order,
            event_type=event_type or OrderEvent.EventType.STATUS_CHANGED,
            event_data=kwargs.pop('event_data', {}),
            **kwargs
        )
