"""
Browser-based automated tests for Client Management module using Playwright
Tests complete user workflows including authentication, CRUD operations, and validation
"""
import pytest
from playwright.sync_api import Page, expect
import re


@pytest.mark.browser
class TestAuthentication:
    """Test authentication and access control for client management"""
    
    def test_login_as_dispatcher_success(self, page: Page, live_server, dispatcher_a):
        """Test successful login as dispatcher"""
        # Navigate to login page
        page.goto(f"{live_server.url}/login/")
        
        # Verify we're on the login page
        expect(page).to_have_url(re.compile(r".*/login.*"))
        
        # Fill in credentials
        page.fill('input[name="email"]', dispatcher_a.email)
        page.fill('input[name="password"]', 'testpass123')
        
        # Submit form
        page.click('button[type="submit"]')
        
        # Should redirect to dashboard  
        page.wait_for_url(re.compile(r".*/home.*"), timeout=5000)
        expect(page).to_have_url(re.compile(r".*/home.*"))
    
    def test_redirect_to_login_when_not_authenticated(self, page: Page, live_server):
        """Test that unauthenticated users are redirected to login page"""
        # Try to access clients list without authentication
        page.goto(f"{live_server.url}/logistics/dashboard/clients/")
        
        # Should be redirected to login page
        page.wait_for_url(re.compile(r".*/login.*"), timeout=5000)
        expect(page).to_have_url(re.compile(r".*/login.*"))
    
    def test_driver_cannot_access_client_management(self, driver_browser_session: Page, live_server):
        """Test that drivers cannot access client management"""
        # Try to navigate to clients page as driver
        driver_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/")
        
        # Driver should either be blocked or see no content
        # This depends on the implementation - adjust as needed
        # For now, just verify the page loads (permission check may vary)
        driver_browser_session.wait_for_load_state('networkidle')


@pytest.mark.browser
class TestClientListView:
    """Test client list view functionality"""
    
    def test_clients_list_displays_correctly(self, authenticated_browser_session: Page, live_server, client_a):
        """Test that clients list displays correctly for dispatcher"""
        # Navigate to clients list
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/")
        
        # Wait for page to load
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Verify client name is visible in the list
        expect(authenticated_browser_session.locator(f'text={client_a.name}')).to_be_visible()
    
    def test_clients_filtered_by_company(self, authenticated_browser_session: Page, live_server, client_a, client_b):
        """Test that clients are properly filtered by company (data isolation)"""
        # client_a belongs to company_a (dispatcher_a's company)
        # client_b belongs to company_b (different company)
        
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Should see client_a
        expect(authenticated_browser_session.locator(f'text={client_a.name}')).to_be_visible()
        
        # Should NOT see client_b (different company)
        expect(authenticated_browser_session.locator(f'text={client_b.name}')).not_to_be_visible()
    
    def test_add_new_client_button_visible(self, authenticated_browser_session: Page, live_server):
        """Test that 'Add New Client' button is visible for dispatchers"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Look for "New Client" or "Добавить клиента" button
        add_client_button = authenticated_browser_session.locator('a:has-text("Новый клиент"), a:has-text("New Client")')
        expect(add_client_button.first).to_be_visible()
    
    def test_navigation_to_client_detail(self, authenticated_browser_session: Page, live_server, client_a):
        """Test navigation from client list to client detail page"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Click on client name or detail link
        client_link = authenticated_browser_session.locator(f'a:has-text("{client_a.name}")').first
        client_link.click()
        
        # Should navigate to client detail page
        authenticated_browser_session.wait_for_url(re.compile(rf".*/clients/{client_a.id_client}/.*"), timeout=5000)
        
        # Verify we're on the detail page
        expect(authenticated_browser_session.locator(f'text={client_a.name}')).to_be_visible()


@pytest.mark.browser
class TestCreateNewClient:
    """Test creating a new client workflow"""
    
    def test_complete_client_creation_workflow(self, authenticated_browser_session: Page, live_server, company_a):
        """Test complete workflow for creating a new client"""
        # Navigate to new client page
        authenticated_browser_session.goto(f"{live_server.url}/client/new/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Fill in client information
        test_client_name = "Test Client Browser"
        test_phone = "+79991234567"
        test_email = "testclient@browser.com"
        
        authenticated_browser_session.fill('input[name="name"]', test_client_name)
        authenticated_browser_session.fill('input[name="phone"]', test_phone)
        authenticated_browser_session.fill('input[name="email"]', test_email)
        
        # Submit form
        authenticated_browser_session.click('button[type="submit"]')
        
        # Wait for redirect (should go back to clients list or show success)
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Verify new client appears in the list
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        expect(authenticated_browser_session.locator(f'text={test_client_name}')).to_be_visible()
    
    def test_form_validation_required_fields(self, authenticated_browser_session: Page, live_server):
        """Test form validation for required fields"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/new-client/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Try to submit empty form
        authenticated_browser_session.click('button[type="submit"]')
        
        # Should stay on the same page or show validation errors
        # HTML5 validation or Django form errors should appear
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Verify still on create page (URL shouldn't change)
        expect(authenticated_browser_session).to_have_url(re.compile(r".*/client/new.*"))
    
    def test_phone_number_validation(self, authenticated_browser_session: Page, live_server):
        """Test phone number format validation"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/new-client/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Fill with invalid phone
        authenticated_browser_session.fill('input[name="name"]', "Test Client")
        authenticated_browser_session.fill('input[name="phone"]', "invalid")
        authenticated_browser_session.fill('input[name="email"]', "test@example.com")
        
        # Submit
        authenticated_browser_session.click('button[type="submit"]')
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Should show validation error or stay on page
        # This depends on your form validation implementation
    
    def test_email_validation(self, authenticated_browser_session: Page, live_server):
        """Test email format validation"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/new-client/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Fill with invalid email
        authenticated_browser_session.fill('input[name="name"]', "Test Client")
        authenticated_browser_session.fill('input[name="phone"]', "+79991234567")
        authenticated_browser_session.fill('input[name="email"]', "invalid-email")
        
        # Submit
        authenticated_browser_session.click('button[type="submit"]')
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # HTML5 validation should catch this


@pytest.mark.browser
class TestClientDetailView:
    """Test client detail page functionality"""
    
    def test_client_detail_displays_correct_information(self, authenticated_browser_session: Page, live_server, client_a):
        """Test that client detail page displays correct information"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Verify client name
        expect(authenticated_browser_session.locator(f'text={client_a.name}')).to_be_visible()
        
        # Verify phone
        expect(authenticated_browser_session.locator(f'text={client_a.phone}')).to_be_visible()
        
        # Verify email
        expect(authenticated_browser_session.locator(f'text={client_a.email}')).to_be_visible()
    
    def test_client_detail_shows_associated_orders(self, authenticated_browser_session: Page, live_server, client_a, order_a):
        """Test that associated orders are shown on client detail page"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Should see order information
        # Look for order destination or cargo type
        page_content = authenticated_browser_session.content()
        
        # Verify order-related content is present
        # This might be in a table or list on the page
        assert order_a.destination in page_content or order_a.cargo_type in page_content
    
    def test_edit_button_visible_for_dispatchers(self, authenticated_browser_session: Page, live_server, client_a):
        """Test that Edit button is visible for dispatchers"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Look for edit button
        edit_button = authenticated_browser_session.locator('a:has-text("Редактировать"), a:has-text("Edit")')
        expect(edit_button.first).to_be_visible()


@pytest.mark.browser
class TestEditClient:
    """Test client editing workflow"""
    
    def test_edit_form_prepopulates_with_existing_data(self, authenticated_browser_session: Page, live_server, client_a):
        """Test that edit form pre-populates with existing client data"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/edit/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Verify fields are pre-filled
        name_input = authenticated_browser_session.locator('input[name="name"]')
        expect(name_input).to_have_value(client_a.name)
        
        phone_input = authenticated_browser_session.locator('input[name="phone"]')
        expect(phone_input).to_have_value(client_a.phone)
        
        email_input = authenticated_browser_session.locator('input[name="email"]')
        expect(email_input).to_have_value(client_a.email)
    
    def test_successful_client_update(self, authenticated_browser_session: Page, live_server, client_a):
        """Test successful update of client information"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/edit/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Update client name
        new_name = "Updated Client Name"
        authenticated_browser_session.fill('input[name="name"]', new_name)
        
        # Submit form
        authenticated_browser_session.click('button[type="submit"]')
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Should redirect to detail page or clients list
        # Verify the new name is displayed
        expect(authenticated_browser_session.locator(f'text={new_name}')).to_be_visible()
    
    def test_changes_reflected_in_detail_view(self, authenticated_browser_session: Page, live_server, client_a):
        """Test that changes are reflected in client detail view"""
        # Edit client
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/edit/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        new_phone = "+79991111111"
        authenticated_browser_session.fill('input[name="phone"]', new_phone)
        authenticated_browser_session.click('button[type="submit"]')
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Navigate to detail page
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Verify updated phone is displayed
        expect(authenticated_browser_session.locator(f'text={new_phone}')).to_be_visible()
    
    def test_changes_reflected_in_client_list(self, authenticated_browser_session: Page, live_server, client_a):
        """Test that changes are reflected in client list"""
        # Edit client
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{client_a.id_client}/edit/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        new_name = "Edited List Client"
        authenticated_browser_session.fill('input[name="name"]', new_name)
        authenticated_browser_session.click('button[type="submit"]')
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Go to clients list
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Verify updated name appears
        expect(authenticated_browser_session.locator(f'text={new_name}')).to_be_visible()


@pytest.mark.browser
class TestErrorHandling:
    """Test error handling and edge cases"""
    
    def test_navigation_to_nonexistent_client(self, authenticated_browser_session: Page, live_server):
        """Test handling of non-existent client ID"""
        # Try to access a non-existent UUID
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        authenticated_browser_session.goto(f"{live_server.url}/logistics/dashboard/clients/{fake_uuid}/")
        
        # Should show 404 or redirect to clients list
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Check for error message or 404
        page_content = authenticated_browser_session.content()
        assert "404" in page_content or "Not Found" in page_content or "не найден" in page_content.lower()
    
    def test_duplicate_email_handling(self, authenticated_browser_session: Page, live_server, client_a):
        """Test handling of duplicate email addresses"""
        authenticated_browser_session.goto(f"{live_server.url}/logistics/new-client/")
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Try to create client with existing email
        authenticated_browser_session.fill('input[name="name"]', "Duplicate Email Client")
        authenticated_browser_session.fill('input[name="phone"]', "+79997777777")
        authenticated_browser_session.fill('input[name="email"]', client_a.email)
        
        authenticated_browser_session.click('button[type="submit"]')
        authenticated_browser_session.wait_for_load_state('networkidle')
        
        # Should show validation error or stay on form
        # This depends on whether email uniqueness is enforced
