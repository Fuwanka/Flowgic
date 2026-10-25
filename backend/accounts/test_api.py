from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.db import IntegrityError
from django.utils import timezone
from ninja.testing import TestClient
from ninja_jwt.tokens import AccessToken

from flowgic.api import api
from logistics.models import Company

from . import services
from .models import PasswordResetCode, User
from .tasks import send_password_reset_email

pytestmark = [pytest.mark.integration, pytest.mark.django_db]
PASSWORD = 'Long-test-password-42!'
NEW_PASSWORD = 'New-long-password-75!'


@pytest.fixture(autouse=True)
def isolated_auth_cache(monkeypatch):
    """Use real Redis, but isolate and delete only this test's own keys."""
    original = services.private_cache_key
    prefix = str(uuid4())
    keys = set()

    def test_key(*args):
        key = f'test:{prefix}:{original(*args)}'
        keys.add(key)
        return key

    monkeypatch.setattr(services, 'private_cache_key', test_key)
    yield
    if keys:
        cache.delete_many(keys)


@pytest.fixture
def api_client():
    return TestClient(api)


@pytest.fixture
def token_pair(api_client, dispatcher_a):
    response = api_client.post('/accounts/token', json={
        'email': dispatcher_a.email, 'password': 'testpass123',
    })
    assert response.status_code == 200
    return response.json()


def bearer(pair):
    return {'Authorization': f'Bearer {pair["access"]}'}


def registration(**changes):
    return {
        'email': 'new-owner@example.test', 'password': PASSWORD,
        'full_name': 'Новый руководитель', 'company_name': 'Новая компания',
        **changes,
    }


def test_registration_creates_company_and_tokens(db, api_client):
    response = api_client.post('/accounts/register', json=registration(email=' Owner@Example.Test '))
    assert response.status_code == 201
    data = response.json()
    user = User.objects.get(email='owner@example.test')
    assert user.check_password(PASSWORD)
    assert user.role == User.Role.Manager and user.company.type == Company.Type.LOGISTICS
    assert data['user']['company']['id_company'] == str(user.company_id)
    me = api_client.get('/accounts/me', headers=bearer(data['tokens']))
    assert me.status_code == 200 and me.json()['id'] == user.pk
    assert not {'password', 'is_superuser', 'is_staff'} & data['user'].keys()


def test_registration_cannot_join_company_by_name(db, api_client, company_a):
    response = api_client.post('/accounts/register', json=registration(company_name=company_a.name))
    assert response.status_code == 201
    assert response.json()['user']['company']['id_company'] != str(company_a.pk)
    assert Company.objects.filter(name=company_a.name).count() == 2


def test_duplicate_email_does_not_create_company(db, api_client, dispatcher_a):
    count = Company.objects.count()
    response = api_client.post('/accounts/register', json=registration(email=dispatcher_a.email.upper()))
    assert response.status_code == 409 and response.json()['code'] == 'email_exists'
    assert Company.objects.count() == count


@pytest.mark.parametrize('extra', [
    {'company_id': str(uuid4())}, {'is_superuser': True}, {'is_staff': True}, {'role': 'administrator'},
])
def test_registration_rejects_privileged_fields(db, api_client, extra):
    assert api_client.post('/accounts/register', json=registration(**extra)).status_code == 422
    assert not User.objects.filter(email='new-owner@example.test').exists()


@pytest.mark.parametrize('changes,status', [
    ({'email': 'bad'}, 422), ({'company_name': '   '}, 422),
    ({'company_type': 'unknown'}, 422), ({'password': '12345678'}, 400),
])
def test_registration_validates_data_before_writes(db, api_client, changes, status):
    companies, users = Company.objects.count(), User.objects.count()
    response = api_client.post('/accounts/register', json=registration(**changes))
    assert response.status_code == status
    assert (Company.objects.count(), User.objects.count()) == (companies, users)


def test_registration_rolls_back_when_token_issuance_fails(db):
    companies, users = Company.objects.count(), User.objects.count()
    with patch('accounts.services._issue_tokens', side_effect=RuntimeError('signer failure')):
        with pytest.raises(RuntimeError):
            services.register_with_tokens(**registration())
    assert (Company.objects.count(), User.objects.count()) == (companies, users)


def test_registration_rolls_back_unrelated_database_failure(db):
    count = Company.objects.count()
    with patch.object(User, 'save', side_effect=IntegrityError('database failure')):
        with pytest.raises(IntegrityError):
            services.register_account(**registration())
    assert Company.objects.count() == count


def test_login_case_insensitive_and_records_last_login(api_client, dispatcher_a):
    response = api_client.post('/accounts/token', json={
        'email': dispatcher_a.email.upper(), 'password': 'testpass123',
    })
    assert response.status_code == 200
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.last_login is not None


@pytest.mark.parametrize('changes', [
    {'is_active': False}, {'status': User.Status.BLOCKED}, {'status': User.Status.INVITED}, {'company': None},
])
def test_login_rejects_unavailable_accounts(api_client, dispatcher_a, changes):
    for key, value in changes.items():
        setattr(dispatcher_a, key, value)
    dispatcher_a.save()
    response = api_client.post('/accounts/token', json={
        'email': dispatcher_a.email, 'password': 'testpass123',
    })
    assert response.status_code == 401


def test_login_unknown_and_wrong_password_have_same_error(api_client, dispatcher_a):
    responses = [api_client.post('/accounts/token', json={'email': email, 'password': 'wrong'}).json()
                 for email in [dispatcher_a.email, 'missing@example.test']]
    assert responses[0] == responses[1]


def test_login_rate_limit_uses_redis(api_client, dispatcher_a):
    for _ in range(10):
        assert api_client.post('/accounts/token', json={
            'email': dispatcher_a.email, 'password': 'wrong',
        }).status_code == 401
    response = api_client.post('/accounts/token', json={
        'email': dispatcher_a.email, 'password': 'testpass123',
    })
    assert response.status_code == 429


def test_refresh_rotates_and_old_refresh_cannot_be_reused(api_client, token_pair):
    response = api_client.post('/accounts/token/refresh', json={'refresh': token_pair['refresh']})
    assert response.status_code == 200
    fresh = response.json()
    assert fresh['refresh'] != token_pair['refresh'] and fresh['access'] != token_pair['access']
    assert api_client.get('/accounts/me', headers=bearer(fresh)).status_code == 200
    assert api_client.post('/accounts/token/refresh', json={'refresh': token_pair['refresh']}).status_code == 401


@pytest.mark.parametrize('token_kind', ['access', 'refresh'])
def test_verify_valid_tokens(api_client, token_pair, token_kind):
    assert api_client.post('/accounts/token/verify', json={'token': token_pair[token_kind]}).status_code == 200


@pytest.mark.parametrize('value', ['garbage', 'a.b.c'])
def test_invalid_token_rejected(api_client, value):
    assert api_client.get('/accounts/me', headers={'Authorization': f'Bearer {value}'}).status_code == 401
    assert api_client.post('/accounts/token/refresh', json={'refresh': value}).status_code == 401
    assert api_client.post('/accounts/token/verify', json={'token': value}).status_code == 401


def test_expired_and_wrong_type_tokens_rejected(api_client, token_pair):
    expired = AccessToken(token_pair['access'])
    expired.set_exp(lifetime=timedelta(seconds=-1))
    assert api_client.get('/accounts/me', headers={'Authorization': f'Bearer {expired}'}).status_code == 401
    assert api_client.get('/accounts/me', headers={'Authorization': f'Bearer {token_pair["refresh"]}'}).status_code == 401
    assert api_client.post('/accounts/token/refresh', json={'refresh': token_pair['access']}).status_code == 401


def test_no_token_and_session_cookie_do_not_authorize_api(db, client, dispatcher_a):
    client.force_login(dispatcher_a)
    response = client.get('/api/accounts/me')
    assert response.status_code == 401
    assert response['WWW-Authenticate'] == 'Bearer'


def test_profile_always_uses_current_identity(api_client, token_pair, dispatcher_a, dispatcher_b):
    response = api_client.get('/accounts/me', data={'user_id': dispatcher_b.pk}, headers=bearer(token_pair))
    assert response.status_code == 200
    assert response.json()['id'] == dispatcher_a.pk
    assert response.json()['company']['id_company'] == str(dispatcher_a.company_id)


def test_profile_patch_updates_only_self(api_client, token_pair, dispatcher_a, dispatcher_b):
    response = api_client.patch('/accounts/me', json={
        'full_name': 'Новое имя', 'phone': '+79991234567', 'theme': 'dark',
    }, headers=bearer(token_pair))
    assert response.status_code == 200
    dispatcher_a.refresh_from_db()
    dispatcher_b.refresh_from_db()
    assert dispatcher_a.full_name == 'Новое имя' and dispatcher_a.theme == User.Theme.DARK
    assert dispatcher_b.full_name == 'Dispatcher B'


@pytest.mark.parametrize('data', [
    {'role': 'manager'}, {'company_id': str(uuid4())}, {'email': 'other@example.test'},
    {'is_superuser': True}, {'id': 100}, {'theme': None}, {'full_name': ' '},
])
def test_profile_patch_rejects_membership_and_invalid_values(api_client, token_pair, data):
    assert api_client.patch('/accounts/me', json=data, headers=bearer(token_pair)).status_code == 422


@pytest.mark.parametrize('changes', [{'status': User.Status.BLOCKED}, {'is_active': False}, {'company': None}])
def test_existing_tokens_stop_working_after_account_disabled(api_client, token_pair, dispatcher_a, changes):
    for key, value in changes.items():
        setattr(dispatcher_a, key, value)
    dispatcher_a.save()
    assert api_client.get('/accounts/me', headers=bearer(token_pair)).status_code == 401
    assert api_client.post('/accounts/token/refresh', json={'refresh': token_pair['refresh']}).status_code == 401


def test_logout_revokes_both_tokens(api_client, token_pair):
    response = api_client.post('/accounts/logout', json={'refresh': token_pair['refresh']}, headers=bearer(token_pair))
    assert response.status_code == 200
    assert api_client.get('/accounts/me', headers=bearer(token_pair)).status_code == 401
    assert api_client.post('/accounts/token/refresh', json={'refresh': token_pair['refresh']}).status_code == 401
    assert api_client.post('/accounts/token/verify', json={'token': token_pair['access']}).status_code == 401


def test_logout_cannot_revoke_another_company_session(api_client, token_pair, dispatcher_b):
    other = api_client.post('/accounts/token', json={
        'email': dispatcher_b.email, 'password': 'testpass123',
    }).json()
    assert api_client.post('/accounts/logout', json={'refresh': other['refresh']}, headers=bearer(token_pair)).status_code == 403
    assert api_client.get('/accounts/me', headers=bearer(other)).status_code == 200


def test_password_change_invalidates_tokens(api_client, token_pair, dispatcher_a):
    response = api_client.post('/accounts/password/change', json={
        'current_password': 'testpass123', 'new_password': NEW_PASSWORD,
    }, headers=bearer(token_pair))
    assert response.status_code == 200
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.check_password(NEW_PASSWORD)
    assert api_client.get('/accounts/me', headers=bearer(token_pair)).status_code == 401
    assert api_client.post('/accounts/token/refresh', json={'refresh': token_pair['refresh']}).status_code == 401
    assert api_client.post('/accounts/token', json={'email': dispatcher_a.email, 'password': NEW_PASSWORD}).status_code == 200


def test_password_change_requires_current_password(api_client, token_pair, dispatcher_a):
    response = api_client.post('/accounts/password/change', json={
        'current_password': 'wrong', 'new_password': NEW_PASSWORD,
    }, headers=bearer(token_pair))
    assert response.status_code == 401
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.check_password('testpass123')


def test_reset_request_generic_async_and_throttled(api_client, dispatcher_a, django_capture_on_commit_callbacks):
    with patch('accounts.services.send_password_reset_email.delay') as enqueue:
        with django_capture_on_commit_callbacks(execute=True):
            known = api_client.post('/accounts/password/reset', json={'email': dispatcher_a.email})
            assert not enqueue.called
        assert enqueue.call_count == 1
        code = PasswordResetCode.objects.get(user=dispatcher_a)
        assert enqueue.call_args.args == (dispatcher_a.email, code.code)
        assert len(code.code) == 6 and code.code.isdigit()
        with django_capture_on_commit_callbacks(execute=True):
            unknown = api_client.post('/accounts/password/reset', json={'email': 'missing@example.test'})
            repeat = api_client.post('/accounts/password/reset', json={'email': dispatcher_a.email})
        assert known.status_code == unknown.status_code == repeat.status_code == 202
        assert known.json() == unknown.json() == repeat.json()
        assert code.code not in known.content.decode()
        assert enqueue.call_count == 1


def test_reset_new_request_invalidates_old_code(api_client, dispatcher_a):
    old = PasswordResetCode.objects.create(user=dispatcher_a, code='654321')
    api_client.post('/accounts/password/reset', json={'email': dispatcher_a.email})
    assert not PasswordResetCode.objects.filter(pk=old.pk).exists()
    assert PasswordResetCode.objects.filter(user=dispatcher_a).count() == 1


def test_reset_is_single_use_and_revokes_jwt(api_client, token_pair, dispatcher_a):
    PasswordResetCode.objects.create(user=dispatcher_a, code='654321')
    payload = {'email': dispatcher_a.email, 'code': '654321', 'new_password': NEW_PASSWORD}
    assert api_client.post('/accounts/password/reset/confirm', json=payload).status_code == 200
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.check_password(NEW_PASSWORD)
    assert not PasswordResetCode.objects.filter(user=dispatcher_a).exists()
    assert api_client.post('/accounts/password/reset/confirm', json=payload).status_code == 400
    assert api_client.get('/accounts/me', headers=bearer(token_pair)).status_code == 401
    assert api_client.post('/accounts/token/refresh', json={'refresh': token_pair['refresh']}).status_code == 401


@pytest.mark.parametrize('kind', ['wrong', 'expired', 'unknown_email'])
def test_reset_rejects_invalid_code_without_password_change(api_client, dispatcher_a, kind):
    code = PasswordResetCode.objects.create(user=dispatcher_a, code='654321')
    if kind == 'expired':
        PasswordResetCode.objects.filter(pk=code.pk).update(created_at=timezone.now() - timedelta(minutes=11))
    response = api_client.post('/accounts/password/reset/confirm', json={
        'email': 'missing@example.test' if kind == 'unknown_email' else dispatcher_a.email,
        'code': '111111' if kind == 'wrong' else '654321', 'new_password': NEW_PASSWORD,
    })
    assert response.status_code == 400 and response.json()['code'] == 'invalid_reset_code'
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.check_password('testpass123')


def test_reset_limited_to_five_guesses(api_client, dispatcher_a):
    PasswordResetCode.objects.create(user=dispatcher_a, code='654321')
    payload = {'email': dispatcher_a.email, 'code': '111111', 'new_password': NEW_PASSWORD}
    for _ in range(5):
        assert api_client.post('/accounts/password/reset/confirm', json=payload).status_code == 400
    payload['code'] = '654321'
    assert api_client.post('/accounts/password/reset/confirm', json=payload).status_code == 400
    dispatcher_a.refresh_from_db()
    assert dispatcher_a.check_password('testpass123')


def test_reset_password_validation_preserves_valid_code(api_client, dispatcher_a):
    PasswordResetCode.objects.create(user=dispatcher_a, code='654321')
    response = api_client.post('/accounts/password/reset/confirm', json={
        'email': dispatcher_a.email, 'code': '654321', 'new_password': '12345678',
    })
    assert response.status_code == 400 and response.json()['code'] == 'invalid_password'
    assert PasswordResetCode.objects.filter(user=dispatcher_a).exists()


def test_password_reset_email_uses_configured_sender(settings, mailoutbox):
    settings.DEFAULT_FROM_EMAIL = 'Flowgic <sender@example.test>'
    assert send_password_reset_email('recipient@example.test', '654321') == 1
    assert mailoutbox[0].from_email == settings.DEFAULT_FROM_EMAIL
    assert mailoutbox[0].to == ['recipient@example.test'] and '654321' in mailoutbox[0].body


def test_validation_errors_do_not_echo_secrets(db, api_client):
    secret = 'Sensitive-password-' * 20
    response = api_client.post('/accounts/register', json=registration(password=secret))
    assert response.status_code == 422
    assert secret not in response.content.decode()


def test_http_routes_and_openapi(db, client):
    response = client.get('/api/openapi.json')
    assert response.status_code == 200
    schema = response.json()
    assert schema['paths']['/api/accounts/token']['post']['operationId'] == 'loginAccount'
    assert schema['paths']['/api/accounts/me']['get']['security']
    assert len(schema['paths']) == 9
