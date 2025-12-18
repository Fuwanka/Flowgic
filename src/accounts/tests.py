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
