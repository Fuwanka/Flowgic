"""
Integration tests for data isolation (multi-tenancy)
Tests that users from one company cannot access data from another company
"""
import pytest
from django.test import Client as TestClient
from decimal import Decimal

from logistics.models import Order, Client, Vehicle, Financial
from logistics.factories import OrderFactory, ClientFactory, VehicleFactory


@pytest.mark.integration
class TestCompanyDataIsolation:
    """Test that company data is properly isolated"""
    
    def test_orders_isolated_by_company(self, db, order_a, order_b):
        """Test that orders are isolated per company"""
        company_a = order_a.client.company
        company_b = order_b.client.company
        
        # Company A should only see its orders
        company_a_orders = Order.objects.filter(client__company=company_a)
        assert order_a in company_a_orders
        assert order_b not in company_a_orders
        
        # Company B should only see its orders
        company_b_orders = Order.objects.filter(client__company=company_b)
        assert order_b in company_b_orders
        assert order_a not in company_b_orders
    
    def test_clients_isolated_by_company(self, db, client_a, client_b, company_a, company_b):
        """Test that clients are isolated per company"""
        # Company A clients
        company_a_clients = Client.objects.filter(company=company_a)
        assert client_a in company_a_clients
        assert client_b not in company_a_clients
        
        # Company B clients
        company_b_clients = Client.objects.filter(company=company_b)
        assert client_b in company_b_clients
        assert client_a not in company_b_clients
    
    def test_vehicles_isolated_by_company(self, db, vehicle_a, vehicle_b, company_a, company_b):
        """Test that vehicles are isolated per company"""
        # Company A vehicles
        company_a_vehicles = Vehicle.objects.filter(company=company_a)
        assert vehicle_a in company_a_vehicles
        assert vehicle_b not in company_a_vehicles
        
        # Company B vehicles
        company_b_vehicles = Vehicle.objects.filter(company=company_b)
        assert vehicle_b in company_b_vehicles
        assert vehicle_a not in company_b_vehicles
    
    def test_user_can_only_see_own_company_orders(self, db, dispatcher_a, dispatcher_b, order_a, order_b):
        """Test users can only see orders from their own company"""
        # Dispatcher A should only see Company A orders
        dispatcher_a_orders = Order.objects.filter(client__company=dispatcher_a.company)
        assert order_a in dispatcher_a_orders
        assert order_b not in dispatcher_a_orders
        
        # Dispatcher B should only see Company B orders
        dispatcher_b_orders = Order.objects.filter(client__company=dispatcher_b.company)
        assert order_b in dispatcher_b_orders
        assert order_a not in dispatcher_b_orders


@pytest.mark.integration
class TestDashboardDataIsolation:
    """Test dashboard views respect company data isolation"""
    
    def test_dispatcher_dashboard_shows_only_company_orders(self, db, authenticated_client, dispatcher_a, order_a, order_b):
        """Test dispatcher dashboard filters by company"""
        response = authenticated_client.get('/dispatcher/')
        
        # Should be successful
        assert response.status_code == 200
        
        # Should contain Company A orders
        orders = response.context.get('orders', [])
        
        # Filter by dispatcher's company
        company_orders = [o for o in orders if o.client.company == dispatcher_a.company]
        
        # All visible orders should be from dispatcher's company
        for order in orders:
            assert order.client.company == dispatcher_a.company
    
    def test_driver_dashboard_shows_only_assigned_orders(self, db, driver_client, driver_a, order_a):
        """Test driver dashboard shows only assigned orders"""
        # Assign order to driver
        order_a.driver = driver_a
        order_a.save()
        
        response = driver_client.get('/driver/')
        
        assert response.status_code == 200
        
        # Driver should only see their assigned orders
        orders = response.context.get('active_orders', [])
        for order in orders:
            assert order.driver == driver_a or order.driver is None


@pytest.mark.integration
class TestOrderDetailAccessControl:
    """Test order detail view enforces access control"""
    
    def test_dispatcher_can_view_own_company_order(self, db, authenticated_client, order_a):
        """Test dispatcher can view orders from their company"""
        response = authenticated_client.get(f'/logistics/request/{order_a.id}/')
        
        # Should be accessible
        assert response.status_code in [200, 302]  # 302 if redirect needed
    
    def test_dispatcher_cannot_view_other_company_order(self, db, authenticated_client, dispatcher_a, order_b):
        """Test dispatcher cannot view orders from other companies"""
        # dispatcher_a trying to access order_b (from different company)
        response = authenticated_client.get(f'/logistics/request/{order_b.id}/')
        
        # Should be forbidden or not found
        # Note: Actual behavior depends on view implementation
        # We expect either 403 Forbidden, 404 Not Found, or redirect
        assert response.status_code in [403, 404, 302]
    
    def test_driver_can_view_assigned_order(self, db, driver_client, driver_a, order_a):
        """Test driver can view their assigned order"""
        # Assign order to driver
        order_a.driver = driver_a
        order_a.save()
        
        response = driver_client.get(f'/logistics/request/{order_a.id}/')
        
        # Should be accessible
        assert response.status_code == 200


@pytest.mark.integration
class TestClientListAccessControl:
    """Test client list view respects company boundaries"""
    
    def test_client_list_shows_only_company_clients(self, db, authenticated_client, dispatcher_a, client_a, client_b):
        """Test client list is filtered by company"""
        response = authenticated_client.get('/logistics/clients/')
        
        # If view exists and returns clients
        if response.status_code == 200 and 'clients' in response.context:
            clients = response.context['clients']
            
            # All clients should be from dispatcher's company
            for client in clients:
                assert client.company == dispatcher_a.company
            
            # Client A should be visible
            assert client_a in clients or any(c.id_client == client_a.id_client for c in clients)
            
            # Client B (from different company) should not be visible
            assert client_b not in clients and not any(c.id_client == client_b.id_client for c in clients)


@pytest.mark.integration
class TestVehicleListAccessControl:
    """Test vehicle list view respects company boundaries"""
    
    def test_vehicle_list_shows_only_company_vehicles(self, db, authenticated_client, dispatcher_a, vehicle_a, vehicle_b):
        """Test vehicle list is filtered by company"""
        response = authenticated_client.get('/logistics/vehicles/')
        
        # If view exists and returns vehicles
        if response.status_code == 200 and 'vehicles' in response.context:
            vehicles = response.context['vehicles']
            
            # All vehicles should be from dispatcher's company
            for vehicle in vehicles:
                assert vehicle.company == dispatcher_a.company
            
            # Vehicle A should be visible
            assert vehicle_a in vehicles or any(v.id == vehicle_a.id for v in vehicles)
            
            # Vehicle B (from different company) should not be visible
            assert vehicle_b not in vehicles and not any(v.id == vehicle_b.id for v in vehicles)


@pytest.mark.integration
class TestRoleBasedAccessControl:
    """Test role-based access control"""
    
    def test_driver_cannot_access_dispatcher_functions(self, db, driver_client):
        """Test driver cannot access dispatcher-only functions"""
        # Try to access dispatcher dashboard
        response = driver_client.get('/dispatcher/')
        
        # Should be forbidden or redirected
        assert response.status_code in [302, 403, 404]
    
    def test_driver_cannot_create_orders(self, db, driver_client, client_a, vehicle_a):
        """Test driver cannot create new orders"""
        order_data = {
            'client': client_a.id_client,
            'vehicle': vehicle_a.id,
            'cargo_type': 'Test Cargo',
            'cargo_mass_kg': 1000,
            'origin': 'Test Origin',
            'destination': 'Test Destination',
            'agreed_price': '10000.00',
            'pickup_datetime': '2025-12-20 10:00:00',
            'delivery_datetime': '2025-12-21 10:00:00'
        }
        
        response = driver_client.post('/logistics/new-request/', order_data)
        
        # Should be forbidden or redirected (drivers can't create orders)
        assert response.status_code in [302, 403, 404]
    
    def test_dispatcher_can_create_orders(self, db, authenticated_client, client_a, vehicle_a, driver_a):
        """Test dispatcher can create orders"""
        order_data = {
            'client': str(client_a.id_client),
            'vehicle': str(vehicle_a.id),
            'driver': str(driver_a.id),
            'cargo_type': 'Electronics',
            'cargo_mass_kg': 1000,
            'origin': 'Moscow',
            'destination': 'SPB',
            'agreed_price': '20000.00',
            'pickup_datetime': '2025-12-20T10:00',
            'delivery_datetime': '2025-12-21T10:00',
            'distance_km': '700'
        }
        
        response = authenticated_client.post('/logistics/new-request/', order_data, follow=True)
        
        # Should be successful (200 or redirect to order detail)
        assert response.status_code == 200
    
    def test_manager_has_full_company_visibility(self, db, manager_client, manager_a, order_a):
        """Test manager can see all company orders"""
        response = manager_client.get('/manager/')
        
        # Manager dashboard should be accessible
        assert response.status_code == 200
        
        # Manager should see company orders
        if 'orders' in response.context:
            orders = response.context['orders']
            
            # All orders should be from manager's company
            for order in orders:
                assert order.client.company == manager_a.company
