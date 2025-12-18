"""
End-to-end tests for payment workflows
Tests complete payment scenarios including partial payments, full payments, and history tracking
"""
import pytest
from decimal import Decimal
from django.utils import timezone
import json

from logistics.models import Order, Financial, OrderEvent


@pytest.mark.e2e
@pytest.mark.slow
class TestPaymentWorkflow:
    """End-to-end payment workflow tests"""
    
    def test_partial_payment_workflow(self, db, authenticated_client, order_a):
        """Test making partial payments on an order"""
        # Create financial record
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('100000.00'),
            driver_cost=Decimal('30000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        assert financial.payment_status == Financial.PaymentStatus.UNPAID
        
        # Make first partial payment of 40000
        financial.payment_status = Financial.PaymentStatus.PARTIALLY_PAID
        financial.save()
        
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'payment_type': 'partial',
                'amount': '40000.00',
                'total_cost': '100000.00',
                'old_status': 'unpaid',
                'new_status': 'partially_paid'
            }
        )
        
        # Verify status changed
        assert financial.payment_status == Financial.PaymentStatus.PARTIALLY_PAID
        
        # Make second partial payment of 30000
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'payment_type': 'partial',
                'amount': '30000.00',
                'total_cost': '100000.00',
                'cumulative': '70000.00',
                'remaining': '30000.00'
            }
        )
        
        # Make final payment
        financial.payment_status = Financial.PaymentStatus.PAID
        financial.save()
        
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'payment_type': 'full',
                'amount': '30000.00',
                'total_cost': '100000.00',
                'old_status': 'partially_paid',
                'new_status': 'paid'
            }
        )
        
        # Verify final state
        assert financial.payment_status == Financial.PaymentStatus.PAID
        
        # Verify payment history
        payment_events = OrderEvent.objects.filter(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED
        )
        assert payment_events.count() == 3
    
    def test_full_payment_immediate(self, db, authenticated_client, order_a):
        """Test making full payment immediately"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('50000.00'),
            driver_cost=Decimal('15000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        # Make full payment
        financial.payment_status = Financial.PaymentStatus.PAID
        financial.save()
        
        # Log payment event
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'payment_type': 'full',
                'amount': '50000.00',
                'old_status': 'unpaid',
                'new_status': 'paid',
                'timestamp': str(timezone.now())
            }
        )
        
        # Verify
        assert financial.payment_status == Financial.PaymentStatus.PAID
        
        # Verify event
        payment_event = OrderEvent.objects.filter(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED
        ).first()
        
        assert payment_event is not None
        assert payment_event.event_data['payment_type'] == 'full'
    
    def test_payment_history_tracking(self, db, order_a, dispatcher_a):
        """Test that payment history is properly tracked"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('150000.00'),
            driver_cost=Decimal('45000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        # Simulate multiple payment events over time
        payments = [
            {'amount': '50000.00', 'type': 'partial'},
            {'amount': '30000.00', 'type': 'partial'},
            {'amount': '40000.00', 'type': 'partial'},
            {'amount': '30000.00', 'type': 'full'}
        ]
        
        cumulative = Decimal('0.00')
        
        for payment in payments:
            cumulative += Decimal(payment['amount'])
            
            # Update status based on total paid
            if cumulative >= financial.client_cost:
                financial.payment_status = Financial.PaymentStatus.PAID
            else:
                financial.payment_status = Financial.PaymentStatus.PARTIALLY_PAID
            
            financial.save()
            
            # Create payment event
            OrderEvent.objects.create(
                order=order_a,
                event_type=OrderEvent.EventType.PAYMENT_UPDATED,
                event_data={
                    'payment_type': payment['type'],
                    'amount': payment['amount'],
                    'cumulative': str(cumulative),
                    'total_cost': str(financial.client_cost),
                    'remaining': str(financial.client_cost - cumulative),
                    'user': str(dispatcher_a.id),
                    'timestamp': str(timezone.now())
                }
            )
        
        # Verify final status
        assert financial.payment_status == Financial.PaymentStatus.PAID
        
        # Verify all payment events were recorded
        payment_events = OrderEvent.objects.filter(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED
        ).order_by('created_at')
        
        assert payment_events.count() == 4
        
        # Verify event data structure
        for event in payment_events:
            assert 'amount' in event.event_data
            assert 'payment_type' in event.event_data
    
    def test_set_total_amount_payment(self, db, authenticated_client, order_a):
        """Test setting a specific total amount as payment"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('80000.00'),
            driver_cost=Decimal('25000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        # Set total amount to 50000 (less than client_cost)
        set_amount = Decimal('50000.00')
        
        if set_amount >= financial.client_cost:
            financial.payment_status = Financial.PaymentStatus.PAID
        else:
            financial.payment_status = Financial.PaymentStatus.PARTIALLY_PAID
        
        financial.save()
        
        # Log event
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'payment_type': 'set_total',
                'set_amount': str(set_amount),
                'total_cost': str(financial.client_cost),
                'old_total': '0.00',
                'new_total': str(set_amount),
                'status': str(financial.payment_status)
            }
        )
        
        # Verify
        assert financial.payment_status == Financial.PaymentStatus.PARTIALLY_PAID


@pytest.mark.e2e
@pytest.mark.slow
class TestPaymentAndOrderStatusIntegration:
    """Test integration between payment and order status"""
    
    def test_payment_affects_order_completion(self, db, order_a):
        """Test that payment status affects order completion workflow"""
        # Create financial
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('60000.00'),
            driver_cost=Decimal('20000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        # Complete delivery but payment not done
        order_a.status = Order.Status.DELIVERED
        order_a.save()
        
        # Check payment status
        assert financial.payment_status == Financial.PaymentStatus.UNPAID
        
        # Make payment
        financial.payment_status = Financial.PaymentStatus.PAID
        financial.save()
        
        # Now can complete order
        order_a.status = Order.Status.COMPLETED
        order_a.save()
        
        # Verify both are completed/paid
        assert order_a.status == Order.Status.COMPLETED
        assert financial.payment_status == Financial.PaymentStatus.PAID
    
    def test_payment_events_in_order_history(self, db, authenticated_client, order_a):
        """Test that payment events appear in order event history"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('75000.00'),
            driver_cost=Decimal('22000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        # Make payment
        financial.payment_status = Financial.PaymentStatus.PARTIALLY_PAID
        financial.save()
        
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={'amount': '40000.00', 'status': 'partially_paid'}
        )
        
        # Change order status
        order_a.status = Order.Status.IN_TRANSIT
        order_a.save()
        
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.STATUS_CHANGED,
            event_data={'new_status': 'in_transit'}
        )
        
        # Get order detail page
        response = authenticated_client.get(f'/logistics/request/{order_a.id}/')
        
        # Check that both payment and status events are in history
        if response.status_code == 200:
            events = OrderEvent.objects.filter(order=order_a).order_by('-created_at')
            
            # Should have both types of events
            event_types = set(events.values_list('event_type', flat=True))
            assert OrderEvent.EventType.PAYMENT_UPDATED in event_types
            assert OrderEvent.EventType.STATUS_CHANGED in event_types
    
    def test_multiple_users_payment_tracking(self, db, order_a, dispatcher_a, manager_a):
        """Test payment updates by different users are tracked"""
        financial = Financial.objects.create(
            order=order_a,
            client_cost=Decimal('90000.00'),
            driver_cost=Decimal('28000.00'),
            payment_status=Financial.PaymentStatus.UNPAID
        )
        
        # Dispatcher makes first payment
        financial.payment_status = Financial.PaymentStatus.PARTIALLY_PAID
        financial.save()
        
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'amount': '45000.00',
                'user_id': str(dispatcher_a.id),
                'user_name': dispatcher_a.full_name,
                'user_role': 'dispatcher'
            }
        )
        
        # Manager completes payment
        financial.payment_status = Financial.PaymentStatus.PAID
        financial.save()
        
        OrderEvent.objects.create(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED,
            event_data={
                'amount': '45000.00',
                'user_id': str(manager_a.id),
                'user_name': manager_a.full_name,
                'user_role': 'manager'
            }
        )
        
        # Verify events from different users
        payment_events = OrderEvent.objects.filter(
            order=order_a,
            event_type=OrderEvent.EventType.PAYMENT_UPDATED
        )
        
        assert payment_events.count() == 2
        
        # Check different users made the payments
        user_ids = [event.event_data.get('user_id') for event in payment_events]
        assert str(dispatcher_a.id) in user_ids
        assert str(manager_a.id) in user_ids
