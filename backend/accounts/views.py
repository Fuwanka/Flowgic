"""HTML adapters retained while the web interface moves to the API."""
import json

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from logistics import services as logistics_services
from logistics.forms import VehicleForm
from billing.exceptions import QuotaExceededError

from . import selectors, services
from .exceptions import AccountError
from .forms import ClientForm


def register_view(request):
    if request.method == 'POST':
        try:
            user = services.register_account(
                full_name=request.POST.get('full_name'),
                email=request.POST.get('email'),
                password=request.POST.get('password'),
                company_name=request.POST.get('company'),
                role=request.POST.get('role') or 'manager',
            )
        except (AccountError, ValidationError) as error:
            messages.error(request, str(error))
            return redirect('register')
        login(request, user)
        messages.success(request, f'Добро пожаловать, {user.full_name}!')
        return redirect('home')
    return render(request, 'accounts/login_register.html', {'tab': 'register'})


def custom_login_view(request):
    if request.method == 'POST':
        try:
            user = services.authenticate_account(
                email=request.POST.get('email'), password=request.POST.get('password'), request=request
            )
        except AccountError as error:
            messages.error(request, error.detail)
            return redirect('login')
        login(request, user)
        return redirect('home')
    return render(request, 'accounts/login_register.html', {'tab': 'login'})


@login_required
def home_view(request):
    templates = {
        'dispatcher': 'dashboard/dispatcher_home.html',
        'manager': 'dashboard/manager_home.html',
        'driver': 'dashboard/driver_home.html',
    }
    return render(
        request, templates.get(request.user.role, 'dashboard/home.html'),
        selectors.get_home_context(request.user),
    )


@login_required
def delete_account_view(request):
    if request.method == 'POST':
        services.delete_account(request.user)
        messages.success(request, 'Ваш аккаунт был удалён.')
        return redirect('login')
    return render(request, 'accounts/delete_account.html')


def password_reset_request_view(request):
    if request.method == 'POST':
        services.request_password_reset(email=request.POST.get('email'))
        messages.success(request, 'Если аккаунт существует, письмо с кодом будет отправлено.')
        return redirect('password_reset_confirm')
    return render(request, 'accounts/password_reset_request.html')


def password_reset_confirm_view(request):
    if request.method == 'POST':
        if request.POST.get('new_password1') != request.POST.get('new_password2'):
            messages.error(request, 'Пароли не совпадают')
            return redirect('password_reset_confirm')
        try:
            user = services.confirm_password_reset(
                email=request.POST.get('email'), code=request.POST.get('code'),
                new_password=request.POST.get('new_password1'),
            )
        except AccountError as error:
            messages.error(request, error.detail)
            return redirect('password_reset_confirm')
        update_session_auth_hash(request, user)
        login(request, user)
        messages.success(request, 'Пароль успешно изменён')
        return redirect('home')
    return render(request, 'accounts/password_reset_confirm.html')


@login_required
def create_client_view(request):
    if request.user.role not in {'dispatcher', 'manager'}:
        messages.error(request, 'Only dispatchers and managers can create clients')
        return redirect('home')
    form = ClientForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        client = logistics_services.create_client(request.user, **form.cleaned_data)
        messages.success(request, f'Client "{client.name}" created successfully!')
        return redirect('home')
    return render(request, 'logistics/new_client.html', {'form': form})


@login_required
def create_vehicle_view(request):
    if request.user.role not in {'dispatcher', 'manager'}:
        messages.error(request, 'Only dispatchers and managers can create vehicles')
        return redirect('home')
    form = VehicleForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            vehicle = logistics_services.create_vehicle(request.user, **form.cleaned_data)
        except QuotaExceededError as error:
            form.add_error(None, error.detail)
            return render(request, 'logistics/new_vehicle.html', {'form': form}, status=402)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f'Vehicle "{vehicle.reg_number}" created successfully!')
            return redirect('home')
    return render(request, 'logistics/new_vehicle.html', {'form': form})


def toggle_theme_view(request):
    payload = request.POST if request.method == 'POST' else request.GET
    if request.method == 'POST' and request.content_type == 'application/json':
        try:
            body = json.loads(request.body)
            payload = body if isinstance(body, dict) else {}
        except (ValueError, UnicodeDecodeError):
            payload = {}
    theme = services.resolve_theme(
        requested=payload.get('theme'), user=request.user,
        cookie_theme=request.COOKIES.get('flowgic_theme', 'light'),
    )
    if request.user.is_authenticated:
        services.update_profile(request.user, theme=theme)
    if (
        request.headers.get('x-requested-with') == 'XMLHttpRequest'
        or 'application/json' in (request.headers.get('accept') or '')
        or request.content_type == 'application/json'
    ):
        response = JsonResponse({'status': 'ok', 'theme': theme})
    else:
        referer = request.META.get('HTTP_REFERER') or '/'
        if not url_has_allowed_host_and_scheme(referer, {request.get_host()}, require_https=request.is_secure()):
            referer = '/'
        response = redirect(referer)
    response.set_cookie('flowgic_theme', theme, max_age=365 * 24 * 60 * 60, samesite='Lax')
    return response
