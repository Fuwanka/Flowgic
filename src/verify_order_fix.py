import os
import django
from django.test import Client
from django.contrib.auth import get_user_model
from logistics.models import Client as LogisticsClient, Order
from django.utils import timezone
import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'flowgic.settings')
django.setup()

User = get_user_model()

def verify_fix():
    # Setup
    password = 'password123'
    user, created = User.objects.get_or_create(username='test_dispatcher', defaults={
        'email': 'dispatcher@example.com',
        'role': 'dispatcher'
    })
    if created:
        user.set_password(password)
        user.save()
    
    client_obj, _ = LogisticsClient.objects.get_or_create(name="Test Client", company=user.company)

    c = Client()
    c.login(username='test_dispatcher', password=password)

    # Test 1: Invalid Submission (Missing required fields)
    print("Test 1: Submitting invalid form...")
    response = c.post('/logistics/new/', {
        'client': client_obj.id,
        # Missing cargo_type, origin, etc.
    })
    
    if response.status_code == 200:
        content = response.content.decode('utf-8')
        if 'Please correct the errors below' in content or 'is-invalid' in content or 'text-danger' in content:
            print("SUCCESS: Error message/indicators found in response.")
        else:
            print("FAILURE: No error message found for invalid submission.")
            print(content[:500]) # Print start of content for debugging
    else:
        print(f"FAILURE: Unexpected status code {response.status_code}")

    # Test 2: Valid Submission
    print("\nTest 2: Submitting valid form...")
    valid_data = {
        'client': client_obj.id,
        'cargo_type': 'Test Cargo',
        'origin': 'Origin City',
        'destination': 'Dest City',
        'pickup_datetime': (timezone.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'),
        'delivery_datetime': (timezone.now() + datetime.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M'),
        'status': 'pending',
        'agreed_price': '1000.00'
    }
    
    response = c.post('/logistics/new/', valid_data, follow=True)
    
    if response.status_code == 200:
        # Check if order was created
        last_order = Order.objects.last()
        if last_order and last_order.cargo_type == 'Test Cargo' and last_order.agreed_price == 1000.00:
             print(f"SUCCESS: Order #{last_order.id} created successfully.")
             print(f"Redirected to: {response.redirect_chain}")
        else:
            print("FAILURE: Order not created or data mismatch.")
    else:
        print(f"FAILURE: Unexpected status code {response.status_code}")

if __name__ == '__main__':
    verify_fix()
