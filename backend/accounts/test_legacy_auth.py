import pytest
from unittest.mock import patch

from django.core.cache import cache
from django.urls import reverse

from logistics.models import Company

from . import services
from .models import PasswordResetCode, User

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


def test_legacy_registration_creates_new_tenant(client, company_a):
    response = client.post(reverse('register'), {
        'email': 'legacy-owner@example.test', 'password': 'Strong-legacy-password-32!',
        'full_name': 'Новый пользователь', 'company': company_a.name, 'role': 'manager',
    })
    assert response.status_code == 302 and response.url == reverse('home')
    user = User.objects.get(email='legacy-owner@example.test')
    assert user.company_id != company_a.pk
    assert Company.objects.filter(name=company_a.name).count() == 2


def test_legacy_login_rejects_blocked_user(client, dispatcher_a):
    dispatcher_a.status = User.Status.BLOCKED
    dispatcher_a.save(update_fields=['status'])
    key = services.private_cache_key('login-attempts', dispatcher_a.email)
    try:
        response = client.post(reverse('login'), {'email': dispatcher_a.email, 'password': 'testpass123'})
        assert response.url == reverse('login')
        assert '_auth_user_id' not in client.session
    finally:
        cache.delete(key)


def test_legacy_reset_uses_service_and_consumes_code(client, dispatcher_a):
    PasswordResetCode.objects.create(user=dispatcher_a, code='654321')
    response = client.post(reverse('password_reset_confirm'), {
        'email': dispatcher_a.email, 'code': '654321',
        'new_password1': 'New-long-password-75!', 'new_password2': 'New-long-password-75!',
    })
    assert response.url == reverse('home')
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.check_password('New-long-password-75!')
    assert not PasswordResetCode.objects.filter(user=dispatcher_a).exists()


def test_legacy_reset_request_does_not_reveal_unknown_email(client, dispatcher_a):
    emails = [dispatcher_a.email, 'missing-legacy@example.test']
    try:
        with patch('accounts.services.request_password_reset', wraps=services.request_password_reset) as request_reset:
            for email in emails:
                response = client.post(reverse('password_reset_request'), {'email': email})
                assert response.url == reverse('password_reset_confirm')
            assert request_reset.call_count == 2
    finally:
        cache.delete_many([services.private_cache_key('reset-request', email) for email in emails])


def test_home_uses_client_company_when_creator_is_missing(authenticated_client, order_a, order_b):
    order_a.created_by = None
    order_a.save(update_fields=['created_by'])
    response = authenticated_client.get(reverse('home'))
    visible = list(response.context['requests'])
    assert order_a in visible and order_b not in visible


def test_theme_redirect_is_limited_to_local_host(client):
    response = client.get(reverse('toggle_theme'), HTTP_REFERER='https://untrusted.example.test/')
    assert response.status_code == 302 and response.url == '/'
