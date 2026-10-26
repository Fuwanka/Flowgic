# Граница записи accounts: пароли, пользователи и токены меняются здесь; другие модули вызывают
# публичные функции.
"""Account business rules shared by the JWT API and existing HTML views."""
import secrets
import time

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from ninja_jwt.exceptions import TokenError
from ninja_jwt.tokens import AccessToken, RefreshToken, UntypedToken

from logistics.services import create_company

from . import selectors
from .exceptions import AccountError, authentication_failed
from .models import PasswordResetCode, User
from .security import normalize_email, password_stamp, private_cache_key
from .tasks import send_password_reset_email
from .permissions import require_operator


@transaction.atomic
def create_driver(user, *, email, full_name, password, phone=None):
    require_operator(user)
    email, full_name = normalize_email(email), full_name.strip()
    if not full_name:
        raise AccountError('Укажите ФИО водителя.')
    if selectors.find_user_by_email(email):
        raise AccountError('Этот email уже используется.', code='email_exists', status=409)
    driver = User(company=user.company, email=email, full_name=full_name, phone=phone,
                  role=User.Role.Driver, status=User.Status.ACTIVE)
    _validate_password(password, driver)
    driver.set_password(password)
    try:
        with transaction.atomic():
            driver.save()
    except IntegrityError as error:
        raise AccountError('Этот email уже используется.', code='email_exists', status=409) from error
    return driver


@transaction.atomic
def update_driver(user, driver_id, *, full_name, phone=None, status='active'):
    from django.shortcuts import get_object_or_404
    require_operator(user)
    driver = get_object_or_404(
        User.objects.filter(company=user.company, role=User.Role.Driver).select_for_update(), pk=driver_id,
    )
    if status not in User.Status.values or not full_name.strip():
        raise AccountError('Укажите ФИО и корректный статус водителя.')
    driver.full_name, driver.phone, driver.status = full_name.strip(), phone, status
    driver.save(update_fields=['full_name', 'phone', 'status'])
    return driver


def _ensure_active(user):
    if not user or not user.is_active or user.status != User.Status.ACTIVE or not user.company_id:
        raise authentication_failed()


def _validate_password(password, user):
    if not isinstance(password, str) or not 1 <= len(password) <= 128:
        raise AccountError('Пароль должен содержать от 1 до 128 символов.', code='invalid_password')
    try:
        validate_password(password, user=user)
    except ValidationError as error:
        raise AccountError(' '.join(error.messages), code='invalid_password') from error


def _counter(key, timeout):
    cache.add(key, 0, timeout=timeout)
    return cache.incr(key)


def authenticate_account(*, email, password, request=None):
    email = normalize_email(email)
    key = private_cache_key('login-attempts', email)
    if cache.get(key, 0) >= 10:
        raise AccountError('Слишком много попыток входа. Повторите позже.', code='rate_limited', status=429)
    candidate = selectors.find_user_by_email(email)
    user = authenticate(request, username=candidate.email if candidate else email, password=password)
    try:
        _ensure_active(user)
    except AccountError:
        _counter(key, 300)
        raise
    cache.delete(key)
    # Retain the select_related company from the identity lookup.
    return candidate


@transaction.atomic
def register_account(*, email, password, full_name, company_name,
                     company_type='logistics', role=User.Role.Manager):
    email = normalize_email(email)
    try:
        validate_email(email)
    except ValidationError as error:
        raise AccountError('Некорректный email.', code='invalid_email') from error
    if selectors.find_user_by_email(email):
        raise AccountError('Пользователь с таким email уже существует.', code='email_exists', status=409)
    if role not in User.Role.values:
        raise AccountError('Некорректная роль.', code='invalid_role')
    full_name, company_name = (full_name or '').strip(), (company_name or '').strip()
    if not full_name or len(full_name) > 255 or not company_name or len(company_name) > 255:
        raise AccountError('Укажите ФИО и название компании (до 255 символов).')
    user = User(email=email, full_name=full_name, role=role, status=User.Status.ACTIVE)
    _validate_password(password, user)
    try:
        # The nested transaction leaves the outer one usable on uniqueness races.
        with transaction.atomic():
            user.company = create_company(name=company_name, company_type=company_type)
            user.set_password(password)
            user.save()
    except IntegrityError as error:
        if not selectors.find_user_by_email(email):
            raise
        raise AccountError('Пользователь с таким email уже существует.', code='email_exists', status=409) from error
    return user


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh['password_stamp'] = password_stamp(user)
    refresh['session_id'] = refresh['jti']
    return {'access': str(refresh.access_token), 'refresh': str(refresh)}


@transaction.atomic
def register_with_tokens(**data):
    user = register_account(**data)
    return user, _issue_tokens(user)


@transaction.atomic
def login_with_tokens(*, email, password, request=None):
    user = authenticate_account(email=email, password=password, request=request)
    user.last_login = timezone.now()
    user.save(update_fields=['last_login'])
    return _issue_tokens(user)


def authenticate_token(token):
    user = selectors.find_token_user(token.get('user_id'))
    _ensure_active(user)
    if not constant_time_compare(token.get('password_stamp', ''), password_stamp(user)):
        raise authentication_failed()
    session_id = token.get('session_id')
    if not session_id or cache.get(private_cache_key('revoked-session', session_id)):
        raise authentication_failed()
    return user


def _read_refresh(raw):
    try:
        return RefreshToken(raw)
    except (TokenError, KeyError, TypeError, ValueError) as error:
        raise authentication_failed() from error


@transaction.atomic
def refresh_tokens(*, refresh):
    token = _read_refresh(refresh)
    actor = authenticate_token(token)
    # Serialize rotation and password changes on the account, then re-check reuse.
    user = User.objects.select_for_update().filter(company=actor.company, pk=actor.pk).get()
    token = _read_refresh(refresh)
    authenticate_token(token)
    token.blacklist()
    return _issue_tokens(user)


def verify_token(*, token):
    try:
        untyped = UntypedToken(token)
        token_class = {'access': AccessToken, 'refresh': RefreshToken}.get(untyped.get('token_type'))
        if token_class is None:
            raise authentication_failed()
        authenticate_token(token_class(token))
    except (TokenError, KeyError, TypeError, ValueError) as error:
        raise authentication_failed() from error


@transaction.atomic
def logout(user, *, refresh, access_token):
    token = _read_refresh(refresh)
    token_user = authenticate_token(token)
    if token_user.pk != user.pk or token.get('session_id') != access_token.get('session_id'):
        raise AccountError('Токен принадлежит другой сессии.', code='permission_denied', status=403)
    User.objects.select_for_update().filter(company=user.company, pk=user.pk).get()
    token = _read_refresh(refresh)
    token.blacklist()
    ttl = max(1, int(token['exp'] - time.time()))
    cache.set(private_cache_key('revoked-session', token['session_id']), True, timeout=ttl)


@transaction.atomic
def update_profile(user, **data):
    if set(data) - {'full_name', 'phone', 'theme'}:
        raise AccountError('Изменение этих полей запрещено.', code='invalid_profile')
    current = User.objects.select_for_update().filter(company=user.company, pk=user.pk).get()
    for field, value in data.items():
        if field == 'full_name' and (not isinstance(value, str) or not value.strip() or len(value) > 255):
            raise AccountError('Укажите ФИО до 255 символов.')
        if field == 'phone' and value is not None and (not isinstance(value, str) or len(value) > 20):
            raise AccountError('Телефон должен содержать до 20 символов.')
        if field == 'theme' and value not in User.Theme.values:
            raise AccountError('Некорректная тема.')
        setattr(current, field, value.strip() if isinstance(value, str) else value)
    if data:
        current.save(update_fields=list(data))
    return selectors.get_profile(current)


def resolve_theme(*, requested, user, cookie_theme='light'):
    if requested in User.Theme.values:
        return requested
    current = user.theme if user.is_authenticated else cookie_theme
    return User.Theme.DARK if current == User.Theme.LIGHT else User.Theme.LIGHT


@transaction.atomic
def delete_account(user):
    User.objects.filter(company=user.company, pk=user.pk).delete()


@transaction.atomic
def request_password_reset(*, email):
    email = normalize_email(email)
    # Same response and cooldown for known and unknown addresses.
    if not cache.add(private_cache_key('reset-request', email), True, timeout=60):
        return
    user = selectors.find_user_by_email(email)
    if not user or not user.is_active or user.status != User.Status.ACTIVE or not user.company_id:
        return
    user = User.objects.select_for_update().filter(company=user.company, pk=user.pk).get()
    PasswordResetCode.objects.filter(user=user).delete()
    code = str(100000 + secrets.randbelow(900000))
    PasswordResetCode.objects.create(user=user, code=code)
    transaction.on_commit(lambda: send_password_reset_email.delay(user.email, code), robust=True)


@transaction.atomic
def confirm_password_reset(*, email, code, new_password):
    actor = selectors.find_user_by_email(email)
    if not actor or not actor.is_active or actor.status != User.Status.ACTIVE or not actor.company_id:
        raise AccountError('Неверный или просроченный код.', code='invalid_reset_code')
    user = User.objects.select_for_update().filter(company=actor.company, pk=actor.pk).get()
    key = private_cache_key('reset-attempts', user.pk)
    if cache.get(key, 0) >= 5:
        raise AccountError('Неверный или просроченный код.', code='invalid_reset_code')
    reset_code = selectors.get_latest_reset_code(user)
    if not reset_code or not reset_code.is_valid() or not constant_time_compare(reset_code.code, str(code)):
        _counter(key, 600)
        raise AccountError('Неверный или просроченный код.', code='invalid_reset_code')
    _validate_password(new_password, user)
    user.set_password(new_password)
    user.save(update_fields=['password'])
    PasswordResetCode.objects.filter(user=user).delete()
    cache.delete(key)
    return user


@transaction.atomic
def change_password(user, *, current_password, new_password):
    current = User.objects.select_for_update().filter(company=user.company, pk=user.pk).get()
    if not current.check_password(current_password):
        raise authentication_failed()
    _validate_password(new_password, current)
    current.set_password(new_password)
    current.save(update_fields=['password'])
    PasswordResetCode.objects.filter(user=current).delete()


@transaction.atomic
def provision_demo_users(company, *, password):
    """Provision a new demo tenant through the account module's write boundary."""
    from logistics.factories import UserFactory

    if not company.is_demo or not company.demo_slug:
        raise AccountError('Требуется демонстрационная компания.', code='demo_company_required')
    if User.objects.filter(company=company).exists():
        raise AccountError('Демонстрационная компания уже содержит пользователей.', code='demo_not_empty')
    _validate_password(password, User(email=f'manager+{company.demo_slug}@demo.example.test'))
    specifications = [
        ('manager', User.Role.Manager, 'Демо: Елена Соколова'),
        ('dispatcher', User.Role.Dispatcher, 'Демо: Антон Волков'),
        ('driver1', User.Role.Driver, 'Демо: Иван Петров'),
        ('driver2', User.Role.Driver, 'Демо: Сергей Орлов'),
        ('driver3', User.Role.Driver, 'Демо: Алексей Кузнецов'),
    ]
    result = {}
    for key, role, name in specifications:
        email = f'{key}+{company.demo_slug}@demo.example.test'
        if selectors.find_user_by_email(email):
            raise AccountError('Демонстрационный email уже занят.', code='demo_email_conflict', status=409)
        result[key] = UserFactory.create(
            company=company, email=email, password=password, role=role,
            full_name=name, phone='+70000000000',
        )
    return result
