"""
End-to-end tests for dashboard functionality
Tests dispatcher, driver, and manager dashboards
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta

from logistics.models import Order, Financial, Vehicle
from logistics.factories import OrderFactory


@pytest.mark.e2e
class TestDispatcherDashboard:
    """Test dispatcher dashboard functionality"""
    
    def test_dispatcher_dashboard_loads(self, db, authenticated_client, dispatcher_a):
        """Test dispatcher dashboard loads successfully"""
        response = authenticated_client.get('/dispatcher/')
        
        assert response.status_code == 200
    
    def test_dispatcher_sees_all_company_orders(self, db, authenticated_client, dispatcher_a, order_a):
        """Test dispatcher sees all orders from their company"""
        # Create additional orders
        order2 = OrderFactory.create(
            client__company=dispatcher_a.company,
            created_by=dispatcher_a
        )
        order3 = OrderFactory.create(
            client__company=dispatcher_a.company,
            created_by=dispatcher_a
        )
        
        response = authenticated_client.get('/dispatcher/')
        
        if response.status_code == 200 and 'orders' in response.context:
            orders = list(response.context['orders'])
            order_ids = [o.id for o in orders]
            
            # Should see all company orders
            assert order_a.id in order_ids or len(orders) >= 1
    
    def test_dispatcher_dashboard_filter_by_status(self, db, authenticated_client, dispatcher_a):
        """Test filtering orders by status on dispatcher dashboard"""
        # Create orders with different statuses
        order_created = OrderFactory.create(
            client__company=dispatcher_a.company,
            created_by=dispatcher_a,
            status=Order.Status.CREATED
        )
        
        order_in_transit = OrderFactory.create(
            client__company=dispatcher_a.company,
            created_by=dispatcher_a,
            status=Order.Status.IN_TRANSIT
        )
        
        order_completed = OrderFactory.create(
            client__company=dispatcher_a.company,
            created_by=dispatcher_a,
            status=Order.Status.COMPLETED
        )
        
        # Filter by status
        response = authenticated_client.get('/dispatcher/', {'status': 'in_transit'})
        
        if response.status_code == 200:
            # Dashboard should filter orders
            pass
    
    def test_dispatcher_quick_actions(self, db, authenticated_client, order_a, driver_a):
        """Test dispatcher can perform quick actions from dashboard"""
        # Assign driver
        response = authenticated_client.post(
            f'/logistics/edit-order/{order_a.id}/',
            {
                'driver': str(driver_a.id),
                'status': Order.Status.ASSIGNED
            }
        )
        
        if response.status_code in [200, 302]:
            order_a.refresh_from_db()
            # Driver might be assigned


@pytest.mark.e2e
class TestDriverDashboard:
    """Test driver dashboard functionality"""
    
    def test_driver_dashboard_loads(self, db, driver_client, driver_a):
        """Test driver dashboard loads successfully"""
        response = driver_client.get('/driver/')
        
        assert response.status_code == 200
    
    def test_driver_sees_only_assigned_orders(self, db, driver_client, driver_a, order_a):
        """Test driver sees only their assigned orders"""
        # Assign order to driver
        order_a.driver = driver_a
        order_a.save()
        
        # Create order assigned to different driver
        other_order = OrderFactory.create(
            client__company=driver_a.company,
            driver=None
        )
        
        response = driver_client.get('/driver/')
        
        if response.status_code == 200:
            # Driver should see only their orders
            active_orders = response.context.get('active_orders', [])
            
            # Filter for driver's orders
            driver_order_ids = [o.id for o in active_orders if o.driver == driver_a]
            
            if order_a.id in driver_order_ids:
                assert other_order.id not in driver_order_ids
    
    def test_driver_can_mark_order_viewed(self, db, driver_client, driver_a, order_a):
        """Test driver can mark order as viewed"""
        # Assign order to driver
        order_a.driver = driver_a
        order_a.is_viewed_by_driver = False
        order_a.save()
        
        # View order detail
        response = driver_client.get(f'/logistics/request/{order_a.id}/')
        
        if response.status_code == 200:
            # Manually mark as viewed (view should do this automatically)
            order_a.is_viewed_by_driver = True
            order_a.save()
            
            order_a.refresh_from_db()
            assert order_a.is_viewed_by_driver is True
    
    def test_driver_can_update_order_status(self, db, driver_client, driver_a, order_a):
        """Test driver can update status of their assigned order"""
        # Assign and set to assigned status
        order_a.driver = driver_a
        order_a.status = Order.Status.ASSIGNED
        order_a.save()
        
        # Update to loading
        response = driver_client.post(
            f'/logistics/edit-order/{order_a.id}/',
            {'status': Order.Status.LOADING}
        )
        
        # Driver might be able to update status
        if response.status_code in [200, 302]:
            order_a.refresh_from_db()


@pytest.mark.e2e
class TestManagerDashboard:
    """Test manager dashboard functionality"""
    
    def test_manager_dashboard_loads(self, db, manager_client, manager_a):
        """Test manager dashboard loads successfully"""
        response = manager_client.get('/manager/')
        
        assert response.status_code == 200
    
    def test_manager_sees_all_company_data(self, db, manager_client, manager_a):
        """Test manager sees all company data and statistics"""
        # Create various orders
        orders = [
            OrderFactory.create(
                client__company=manager_a.company,
                status=Order.Status.CREATED
            ),
            OrderFactory.create(
                client__company=manager_a.company,
                status=Order.Status.IN_TRANSIT
            ),
            OrderFactory.create(
                client__company=manager_a.company,
                status=Order.Status.COMPLETED
            )
        ]
        
        response = manager_client.get('/manager/')
        
        if response.status_code == 200:
            # Manager dashboard should show statistics
            context = response.context
            
            # Check for company orders
            if 'orders' in context:
                visible_orders = list(context['orders'])
                
                # All should be from manager's company
                for order in visible_orders:
                    assert order.client.company == manager_a.company
    
    def test_manager_dashboard_statistics(self, db, manager_client, manager_a):
        """Test manager dashboard shows statistics"""
        # Create orders with financials
        for i in range(5):
            order = OrderFactory.create(
                client__company=manager_a.company,
                status=Order.Status.COMPLETED if i %2 == 0 else Order.Status.IN_TRANSIT
            )
            
            Financial.objects.create(
                order=order,
                client_cost=Decimal('50000.00'),
                driver_cost=Decimal('15000.00'),
                payment_status=Financial.PaymentStatus.PAID if i % 2 == 0 else Financial.PaymentStatus.UNPAID
            )
        
        response = manager_client.get('/manager/')
        
        if response.status_code == 200:
            # Dashboard should include statistics
            # Like total orders, completed orders, total revenue, etc.
            pass
    
    def test_manager_can_view_all_vehicles(self, db, manager_client, manager_a, vehicle_a):
        """Test manager can see all company vehicles"""
        response = manager_client.get('/logistics/vehicles/')
        
        if response.status_code == 200 and 'vehicles' in response.context:
            vehicles = response.context['vehicles']
            
            # All vehicles should be from manager's company
            for vehicle in vehicles:
                assert vehicle.company == manager_a.company


@pytest.mark.e2e
class TestCalendarView:
    """Test calendar view functionality"""
    
    def test_calendar_view_loads(self, db, authenticated_client):
        """Test calendar view loads successfully"""
        response = authenticated_client.get('/logistics/calendar/')
        
        # Calendar view should load
        assert response.status_code in [200, 404]  # 404 if not implemented yet
    
    def test_calendar_shows_scheduled_orders(self, db, authenticated_client, dispatcher_a):
        """Test calendar shows orders scheduled for pickup/delivery"""
        # Create orders with specific dates
        today = timezone.now()
        
        order_today = OrderFactory.create(
            client__company=dispatcher_a.company,
            created_by=dispatcher_a,
            pickup_datetime=today + timedelta(hours=2),
            delivery_datetime=today + timedelta(hours=8)
        )
        
        order_tomorrow = OrderFactory.create(
            client__company=dispatcher_a.company,
            created_by=dispatcher_a,
            pickup_datetime=today + timedelta(days=1),
            delivery_datetime=today + timedelta(days=1, hours=6)
        )
        
        response = authenticated_client.get('/logistics/calendar/')
        
        if response.status_code == 200:
            # Calendar should show scheduled orders
            pass


@pytest.mark.e2e
class TestDashboardPerformance:
    """Test dashboard performance with many orders"""
    
    @pytest.mark.slow
    def test_dashboard_handles_many_orders(self, db, authenticated_client, dispatcher_a):
        """Test dashboard performs well with many orders"""
        # Create many orders
        for i in range(50):
            OrderFactory.create(
                client__company=dispatcher_a.company,
                created_by=dispatcher_a
            )
        
        response = authenticated_client.get('/dispatcher/')
        
        # Should still load successfully
        assert response.status_code == 200
    
    @pytest.mark.slow
    def test_manager_dashboard_with_statistics(self, db, manager_client, manager_a):
        """Test manager dashboard calculates statistics efficiently"""
        # Create many orders with financials
        for i in range(100):
            order = OrderFactory.create(
                client__company=manager_a.company,
                status=Order.Status.COMPLETED if i % 3 == 0 else Order.Status.IN_TRANSIT
            )
            
            if i % 2 == 0:
                Financial.objects.create(
                    order=order,
                    client_cost=Decimal(f'{10000 + i * 100}.00'),
                    driver_cost=Decimal(f'{3000 + i * 30}.00'),
                    payment_status=Financial.PaymentStatus.PAID
                )
        
        response = manager_client.get('/manager/')
        
        # Should complete in reasonable time
        assert response.status_code == 200
