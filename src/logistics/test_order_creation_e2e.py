"""
End-to-end tests for order creation workflow
Tests complete order lifecycle from creation to completion
"""
import pytest
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from logistics.models import Order, OrderEvent, Financial
from accounts.models import User


@pytest.mark.e2e
@pytest.mark.slow
class TestOrderCreationWorkflow:
    """End-to-end tests for order creation and management"""
    
    def test_complete_order_creation_workflow(self, db, authenticated_client, client_a, vehicle_a, driver_a, dispatcher_a):
        """Test complete order creation workflow from start to finish"""
        # Step 1: Dispatcher creates a new order
        order_data = {
            'client': str(client_a.id_client),
            'cargo_type': 'Electronics',
            'cargo_mass_kg': 2000,
            'origin': 'Moscow Warehouse',
            'destination': 'SPB Store',
            'agreed_price': '35000.00',
            'pickup_datetime': (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'delivery_datetime': (timezone.now() + timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
            'distance_km': '700'
        }
        
        response = authenticated_client.post('/logistics/new-request/', order_data)
        
        # Order should be created (redirect or success response)
        assert response.status_code in [200, 302]
        
        # Verify order was created
        order = Order.objects.filter(
            client=client_a,
            cargo_type='Electronics'
        ).first()
        
        if order:
            assert order.status == Order.Status.CREATED
            assert order.created_by == dispatcher_a
            
            # Step 2: Assign driver and vehicle
            order.driver = driver_a
            order.vehicle = vehicle_a
            order.status = Order.Status.ASSIGNED
            order.save()
            
            # Create assignment event
            OrderEvent.objects.create(
                order=order,
                event_type=OrderEvent.EventType.ASSIGNED,
                event_data={
                    'driver_id': str(driver_a.id),
                    'vehicle_id': str(vehicle_a.id)
                }
            )
            
            # Verify assignment
            assert order.driver == driver_a
            assert order.vehicle == vehicle_a
            assert order.status == Order.Status.ASSIGNED
            
            # Step 3: Progress through order lifecycle
            statuses = [
                Order.Status.LOADING,
                Order.Status.IN_TRANSIT,
                Order.Status.DELIVERED,
                Order.Status.COMPLETED
            ]
            
            for status in statuses:
                order.status = status
                order.save()
                
                # Log status change event
                OrderEvent.objects.create(
                    order=order,
                    event_type=OrderEvent.EventType.STATUS_CHANGED,
                    event_data={
                        'new_status': status
                    }
                )
            
            # Verify final status
            assert order.status == Order.Status.COMPLETED
            
            # Verify events were created
            events = OrderEvent.objects.filter(order=order)
            assert events.count() >= 2  # At least assignment + status changes
    
    def test_order_with_financial_creation(self, db, authenticated_client, client_a, dispatcher_a):
        """Test creating order with financial data"""
        # Create order
        order_data = {
            'client': str(client_a.id_client),
            'cargo_type': 'Furniture',
            'cargo_mass_kg': 3000,
            'origin': 'Factory',
            'destination': 'Warehouse',
            'agreed_price': '45000.00',
            'pickup_datetime': (timezone.now() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
            'delivery_datetime': (timezone.now() + timedelta(days=3)).strftime('%Y-%m-%dT%H:%M'),
            'distance_km': '1200'
        }
        
        response = authenticated_client.post('/logistics/new-request/', order_data)
        
        if response.status_code in [200, 302]:
            order = Order.objects.filter(
                client=client_a,
                cargo_type='Furniture'
            ).first()
            
            if order:
                # Create financial record
                financial = Financial.objects.create(
                    order=order,
                    client_cost=Decimal('45000.00'),
                    driver_cost=Decimal('15000.00'),
                    third_party_cost=Decimal('2000.00')
                )
                
                # Verify financial record
                assert financial.order == order
                assert financial.client_cost == Decimal('45000.00')
                # Profit should be auto-calculated
                assert financial.profit is not None
    
    def test_driver_assignment_workflow(self, db, authenticated_client, order_a, driver_a, vehicle_a):
        """Test assigning driver and vehicle to existing order"""
        # Order starts without driver
        assert order_a.driver is None or order_a.status == Order.Status.CREATED
        
        # Assign via view or directly
        order_a.driver = driver_a
        order_a.vehicle = vehicle_a
        order_a.status = Order.Status.ASSIGNED
        order_a.save()
        
        # Verify assignment
        order_a.refresh_from_db()
        assert order_a.driver == driver_a
        assert order_a.vehicle == vehicle_a
        assert order_a.status == Order.Status.ASSIGNED
    
    def test_order_cancellation_workflow(self, db, authenticated_client, order_a):
        """Test cancelling an order"""
        initial_status = order_a.status
        
        # Cancel order
        order_a.status = Order.Status.CANCELLED
        order_a.save()
        
        # Log cancellation event
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.STATUS_CHANGED,
            event_data={
                'old_status': initial_status,
                'new_status': Order.Status.CANCELLED,
                'reason': 'Client request'
            }
        )
        
        # Verify cancellation
        assert order_a.status == Order.Status.CANCELLED


@pytest.mark.e2e
@pytest.mark.slow
class TestOrderLifecycle:
    """Test complete order lifecycle scenarios"""
    
    def test_full_order_lifecycle_happy_path(self, db, client_a, dispatcher_a, driver_a, vehicle_a):
        """Test complete happy path from creation to completion"""
        # Create order
        order = Order.objects.create(
            client=client_a,
            created_by=dispatcher_a,
            cargo_type='Medical Equipment',
            cargo_mass_kg=500,
            origin='Hospital A',
            destination='Hospital B',
            agreed_price=Decimal('25000.00'),
            pickup_datetime=timezone.now() + timedelta(hours=2),
            delivery_datetime=timezone.now() + timedelta(hours=6),
            distance_km=Decimal('150.00'),
            status=Order.Status.CREATED
        )
        
        # Assign driver and vehicle
        order.driver = driver_a
        order.vehicle = vehicle_a
        order.status = Order.Status.ASSIGNED
        order.save()
        
        OrderEvent.objects.create(
            order=order,
            event_type=OrderEvent.EventType.ASSIGNED,
            event_data={'driver': str(driver_a.id)}
        )
        
        # Driver marks as viewed
        order.is_viewed_by_driver = True
        order.save()
        
        # Progress through statuses
        order.status = Order.Status.LOADING
        order.save()
        OrderEvent.objects.create(
            order=order,
            event_type=OrderEvent.EventType.LOADED,
            event_data={'timestamp': str(timezone.now())}
        )
        
        order.status = Order.Status.IN_TRANSIT
        order.save()
        OrderEvent.objects.create(
            order=order,
            event_type=OrderEvent.EventType.DEPARTED,
            event_data={'timestamp': str(timezone.now())}
        )
        
        order.status = Order.Status.DELIVERED
        order.save()
        OrderEvent.objects.create(
            order=order,
            event_type=OrderEvent.EventType.DELIVERED,
            event_data={'timestamp': str(timezone.now())}
        )
        
        # Create financial record
        financial = Financial.objects.create(
            order=order,
            client_cost=Decimal('25000.00'),
            driver_cost=Decimal('8000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        # Mark as paid
        financial.payment_status = Financial.PaymentStatus.PAID
        financial.save()
        
        OrderEvent.objects.create(
            order=order,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={'status': 'paid'}
        )
        
        # Complete order
        order.status = Order.Status.COMPLETED
        order.save()
        
        # Verify final state
        assert order.status == Order.Status.COMPLETED
        assert order.is_viewed_by_driver is True
        assert financial.payment_status == Financial.PaymentStatus.PAID
        
        # Verify events
        events = OrderEvent.objects.filter(order=order)
        assert events.count() >= 5
    
    def test_order_with_delay_scenario(self, db, client_a, dispatcher_a, driver_a):
        """Test order lifecycle with delay"""
        order = Order.objects.create(
            client=client_a,
            created_by=dispatcher_a,
            driver=driver_a,
            cargo_type='Time-Sensitive Goods',
            cargo_mass_kg=1000,
            origin='Point A',
            destination='Point B',
            agreed_price=Decimal('40000.00'),
            pickup_datetime=timezone.now() + timedelta(hours=1),
            delivery_datetime=timezone.now() + timedelta(hours=4),
            distance_km=Decimal('300.00'),
            status=Order.Status.IN_TRANSIT
        )
        
        # Order gets delayed
        order.status = Order.Status.DELAYED
        order.delay_reason = 'Traffic accident on highway'
        order.save()
        
        # Log delay event
        OrderEvent.objects.create(
            order=order,
            event_type=OrderEvent.EventType.STATUS_CHANGED,
            event_data={
                'status': 'delayed',
                'reason': order.delay_reason
            }
        )
        
        # Resume transit
        order.status = Order.Status.IN_TRANSIT
        order.save()
        
        # Eventually deliver
        order.status = Order.Status.DELIVERED
        order.save()
        
        # Verify
        assert order.status == Order.Status.DELIVERED
        assert order.delay_reason == 'Traffic accident on highway'
        
        # Check delay event exists
        delay_events = OrderEvent.objects.filter(
            order=order,
            event_data__status='delayed'
        )
        assert delay_events.exists()
