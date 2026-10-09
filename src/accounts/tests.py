"""
Unit tests for Accounts models
Tests user model, roles, and authentication
"""
import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

from accounts.models import User, PasswordResetCode
from logistics.models import Company


@pytest.mark.unit
class TestUserModel:
    """Unit tests for User model"""
    
    def test_user_creation_with_all_fields(self, db, company_a):
        """Test creating user with all fields"""
        user = User(
            email='newuser@test.com',
            company=company_a,
            role=User.Role.Dispatcher,
            full_name='John Doe',
            phone='+79991234567',
            status=User.Status.ACTIVE
        )
        user.set_password('securepass123')
        user.save()
        
        assert user.email == 'newuser@test.com'
        assert user.check_password('securepass123')
        assert user.company == company_a
        assert user.role == User.Role.Dispatcher
        assert user.status == User.Status.ACTIVE
    
    def test_user_roles(self, db, company_a):
        """Test different user roles"""
        dispatcher = User(email='dispatcher@test.com', company=company_a, role=User.Role.Dispatcher)
        dispatcher.set_password('pass')
        dispatcher.save()
        
        manager = User(email='manager@test.com', company=company_a, role=User.Role.Manager)
        manager.set_password('pass')
        manager.save()
        
        driver = User(email='driver@test.com', company=company_a, role=User.Role.Driver)
        driver.set_password('pass')
        driver.save()
        
        assert dispatcher.role == User.Role.Dispatcher
        assert manager.role == User.Role.Manager
        assert driver.role == User.Role.Driver
    
    def test_user_status_transitions(self, db, company_a):
        """Test user status changes"""
        user = User(email='user@test.com', company=company_a, status=User.Status.INVITED)
        user.set_password('pass')
        user.save()
        
        assert user.status == User.Status.INVITED
        
        # Activate user
        user.status = User.Status.ACTIVE
        user.save()
        assert user.status == User.Status.ACTIVE
        
        # Block user
        user.status = User.Status.BLOCKED
        user.save()
        assert user.status == User.Status.BLOCKED
    
    def test_user_email_is_username(self, db, company_a):
        """Test that email is used as username field"""
        user = User(email='email_login@test.com', company=company_a)
        user.set_password('pass')
        user.save()
        
        assert User.USERNAME_FIELD == 'email'
        assert user.email == 'email_login@test.com'
    
    def test_user_company_association(self, db, company_a, company_b):
        """Test users are associated with correct company"""
        user_a = User(email='usera@test.com', company=company_a)
        user_a.set_password('pass')
        user_a.save()
        
        user_b = User(email='userb@test.com', company=company_b)
        user_b.set_password('pass')
        user_b.save()
        
        assert user_a.company == company_a
        assert user_b.company == company_b
        assert user_a.company != user_b.company
    
    def test_user_full_name_auto_populate(self, db, company_a):
        """Test full_name auto-populates from first_name and last_name"""
        user = User(email='auto@test.com', company=company_a, first_name='Ivan', last_name='Petrov')
        user.set_password('pass')
        user.save()
        
        # Save method should auto-populate full_name
        assert user.full_name == 'Ivan Petrov'
    
    def test_user_string_representation(self, db, dispatcher_a):
        """Test __str__ method"""
        string_repr = str(dispatcher_a)
        assert 'Dispatcher' in string_repr or dispatcher_a.full_name in string_repr


@pytest.mark.unit
class TestPasswordResetCode:
    """Unit tests for PasswordResetCode model"""
    
    def test_password_reset_code_creation(self, db, dispatcher_a):
        """Test creating password reset code"""
        code = PasswordResetCode.objects.create(
            user=dispatcher_a,
            code='123456'
        )
        
        assert code.user == dispatcher_a
        assert code.code == '123456'
        assert code.created_at is not None
    
    def test_password_reset_code_is_valid_fresh(self, db, dispatcher_a):
        """Test that fresh code is valid"""
        code = PasswordResetCode.objects.create(
            user=dispatcher_a,
            code='123456'
        )
        
        # Fresh code should be valid (less than 10 minutes old)
        assert code.is_valid() is True
    
    def test_password_reset_code_is_valid_expired(self, db, dispatcher_a):
        """Test that old code is invalid"""
        code = PasswordResetCode.objects.create(
            user=dispatcher_a,
            code='123456'
        )
        
        # Manually set created_at to 11 minutes ago
        code.created_at = timezone.now() - timedelta(minutes=11)
        code.save()
        
        # Expired code should be invalid
        assert code.is_valid() is False


@pytest.mark.unit
class TestThemeSwitching:
    """Unit tests for theme switching functionality"""

    def test_user_theme_default_and_choice(self, db, company_a):
        """Test default theme is light and can be updated to dark"""
        user = User.objects.create(
            email='theme_test@test.com',
            company=company_a,
            role=User.Role.Dispatcher
        )
        assert user.theme == User.Theme.LIGHT

        user.theme = User.Theme.DARK
        user.save()
        user.refresh_from_db()
        assert user.theme == 'dark'

    def test_anonymous_toggle_theme_get(self, client):
        """Test anonymous user toggles theme via GET and gets cookie"""
        response = client.get('/toggle-theme/')
        assert response.status_code == 302
        assert 'flowgic_theme' in response.cookies
        assert response.cookies['flowgic_theme'].value == 'dark'

    def test_anonymous_set_theme_json(self, client):
        """Test anonymous user sets theme via JSON POST"""
        response = client.post(
            '/toggle-theme/',
            data='{"theme": "dark"}',
            content_type='application/json'
        )
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
        assert data['theme'] == 'dark'
        assert response.cookies['flowgic_theme'].value == 'dark'

    def test_authenticated_user_theme_toggle(self, client, dispatcher_a):
        """Test authenticated user toggling theme updates database and cookie"""
        client.force_login(dispatcher_a)
        assert dispatcher_a.theme == 'light'

        # Toggle to dark
        response = client.post(
            '/toggle-theme/',
            data='{"theme": "dark"}',
            content_type='application/json'
        )
        assert response.status_code == 200
        dispatcher_a.refresh_from_db()
        assert dispatcher_a.theme == 'dark'
        assert response.cookies['flowgic_theme'].value == 'dark'

        # Toggle back to light
        response = client.post(
            '/toggle-theme/',
            data='{"theme": "light"}',
            content_type='application/json'
        )
        assert response.status_code == 200
        dispatcher_a.refresh_from_db()
        assert dispatcher_a.theme == 'light'
        assert response.cookies['flowgic_theme'].value == 'light'

    def test_theme_context_processor(self, db, dispatcher_a):
        """Test theme_context processor returns user theme or cookie theme"""
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser
        from accounts.context_processors import theme_context

        factory = RequestFactory()

        # Anonymous with no cookie
        request = factory.get('/')
        request.user = AnonymousUser()
        assert theme_context(request) == {'current_theme': 'light'}

        # Anonymous with cookie
        request.COOKIES['flowgic_theme'] = 'dark'
        assert theme_context(request) == {'current_theme': 'dark'}

        # Authenticated user
        request = factory.get('/')
        dispatcher_a.theme = 'dark'
        dispatcher_a.save()
        request.user = dispatcher_a
        assert theme_context(request) == {'current_theme': 'dark'}

    def test_landing_page_renders_theme_attribute(self, client):
        """Test landing page HTML includes data-theme attribute and theme assets"""
        response = client.get('/')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'data-theme="light"' in content
        assert 'theme.css' in content
        assert 'theme.js' in content
        assert 'theme-toggle' in content

        # With dark theme cookie
        client.cookies['flowgic_theme'] = 'dark'
        response_dark = client.get('/')
        content_dark = response_dark.content.decode('utf-8')
        assert 'data-theme="dark"' in content_dark

    def test_dashboard_renders_user_preferred_theme(self, client, dispatcher_a):
        """Test dashboard renders user's saved dark theme preference"""
        dispatcher_a.theme = 'dark'
        dispatcher_a.save()
        client.force_login(dispatcher_a)

        response = client.get('/home/')
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'data-theme="dark"' in content
        assert 'theme-toggle' in content
        assert 'menu-theme-toggle' in content


