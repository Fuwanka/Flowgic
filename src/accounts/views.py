from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from logistics.models import Company  # Импортируем Company из logistics
from .models import User
from django.contrib.auth.decorators import login_required
from logistics.models import Order
import random
from django.core.mail import send_mail
from django.contrib.auth import update_session_auth_hash
from .models import PasswordResetCode

User = get_user_model()

def register_view(request):
    if request.method == 'POST':
        full_name = request.POST.get('full_name')
        email = request.POST.get('email')
        password = request.POST.get('password')
        company_name = request.POST.get('company')
        role = request.POST.get('role')

        # Получаем или создаём компанию
        company_obj, created = Company.objects.get_or_create(name=company_name)

        # Проверяем, что пользователя с таким email ещё нет
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Пользователь с таким email уже существует')
            return redirect('register')

        # Создаём пользователя
        user = User(
            full_name=full_name,
            email=email,
            company=company_obj,
            role=role
        )
        user.set_password(password)
        user.save()

        login(request, user)
        messages.success(request, f'Добро пожаловать, {full_name}!')
        return redirect('home')

    return render(request, 'accounts/login_register.html', {'tab': 'register'})


def custom_login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Неверный email или пароль')
            return redirect('login')

    return render(request, 'accounts/login_register.html', {'tab': 'login'})


@login_required
def home_view(request):
    user = request.user
    
    # === НОВОЕ: Подготовка данных для календаря ===
    from logistics.models import Order
    import json
    from django.core.serializers.json import DjangoJSONEncoder

    # Берём все заказы, к которым у пользователя есть доступ
    if user.role == 'dispatcher':
        orders_qs = Order.objects.filter(created_by=user)
    elif user.role == 'manager':
        orders_qs = Order.objects.filter(client__company=user.company)
    elif user.role == 'driver':
        orders_qs = Order.objects.filter(driver=user)
    else:
        orders_qs = Order.objects.none()

    # Формируем события для календаря
    orders_for_calendar = orders_qs.filter(
        pickup_datetime__isnull=False,
        delivery_datetime__isnull=False
    )
    
    events = []
    for order in orders_for_calendar:
        events.append({
            "title": f"Заказ {order.order_number}: {order.client.name or 'Клиент'}",
            "start": order.pickup_datetime.isoformat(),
            "end": order.delivery_datetime.isoformat(),
            "color": "#3788d8",
            "textColor": "white",
            "extendedProps": {
                "cargo": order.cargo_type,
                "status": order.get_status_display()
            }
        })
    
    events_json = json.dumps(events, cls=DjangoJSONEncoder, ensure_ascii=False)
    # === КОНЕЦ НОВОГО ===

    # Формируем заявки для дашборда в зависимости от роли
    if user.role == 'dispatcher':
        requests = Order.objects.filter(created_by=user).order_by('-created_at')
        context = {
            'user': user,
            'requests': requests,
            'events_json': events_json  # ← добавляем
        }
        template_name = 'dashboard/dispatcher_home.html'

    elif user.role == 'manager':
        requests = Order.objects.filter(client__company=user.company).order_by('-created_at')
        context = {
            'user': user,
            'requests': requests,
            'events_json': events_json  # ← добавляем
        }
        template_name = 'dashboard/manager_home.html'

    elif user.role == 'driver':
        requests = Order.objects.filter(driver=user).order_by('is_viewed_by_driver', '-created_at')
        unread_count = requests.filter(is_viewed_by_driver=False).count()
        context = {
            'user': user,
            'requests': requests,
            'unread_count': unread_count,
            'events_json': events_json  # ← добавляем
        }
        template_name = 'dashboard/driver_home.html'

    else:
        context = {
            'user': user,
            'events_json': events_json  # ← добавляем
        }
        template_name = 'dashboard/home.html'

    return render(request, template_name, context)


@login_required
def delete_account_view(request):
    if request.method == 'POST':
        user = request.user
        user.delete()
        messages.success(request, 'Ваш аккаунт был удалён.')
        return redirect('login')
    return render(request, 'accounts/delete_account.html')


def password_reset_request_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            messages.error(request, 'Пользователь с таким email не найден')
            return redirect('password_reset_request')

        # генерируем код
        code = str(random.randint(100000, 999999))
        PasswordResetCode.objects.create(user=user, code=code)

        # отправляем письмо
        send_mail(
            subject='Сброс пароля',
            message=f'Ваш код для сброса пароля: {code}',
            from_email='snitch_pc@mail.ru',  # ← совпадает с EMAIL_HOST_USER
            recipient_list=[user.email],
            fail_silently=False,
        )

        messages.success(request, 'Код отправлен на вашу почту')
        return redirect('password_reset_confirm')

    return render(request, 'accounts/password_reset_request.html')


def password_reset_confirm_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        code = request.POST.get('code')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')

        if new_password1 != new_password2:
            messages.error(request, 'Пароли не совпадают')
            return redirect('password_reset_confirm')

        try:
            user = User.objects.get(email=email)
            reset_code = PasswordResetCode.objects.filter(user=user, code=code).latest('created_at')
        except (User.DoesNotExist, PasswordResetCode.DoesNotExist):
            messages.error(request, 'Неверный код или email')
            return redirect('password_reset_confirm')

        if not reset_code.is_valid():
            messages.error(request, 'Код истёк')
            return redirect('password_reset_request')

        # меняем пароль
        user.set_password(new_password1)
        user.save()
        update_session_auth_hash(request, user)  # чтобы сразу авторизовать

        messages.success(request, 'Пароль успешно изменён')
        login(request, user)
        return redirect('home')

    return render(request, 'accounts/password_reset_confirm.html')


@login_required
def create_client_view(request):
    """View for creating new clients - accessible by dispatchers"""
    from .forms import ClientForm
    from logistics.models import Client
    
    # Only dispatchers can create clients
    if request.user.role != 'dispatcher':
        messages.error(request, 'Only dispatchers can create clients')
        return redirect('home')
    
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save(commit=False)
            client.company = request.user.company
            client.save()
            messages.success(request, f'Client "{client.name}" created successfully!')
            return redirect('home')
    else:
        form = ClientForm()
    
    return render(request, 'logistics/new_client.html', {'form': form})


@login_required
def create_vehicle_view(request):
    """View for creating new vehicles - accessible by dispatchers"""
    from logistics.forms import VehicleForm
    from logistics.models import Vehicle
    
    # Only dispatchers can create vehicles
    if request.user.role != 'dispatcher':
        messages.error(request, 'Only dispatchers can create vehicles')
        return redirect('home')
    
    if request.method == 'POST':
        form = VehicleForm(request.POST)
        if form.is_valid():
            vehicle = form.save(commit=False)
            vehicle.company = request.user.company
            vehicle.save()
            messages.success(request, f'Vehicle "{vehicle.reg_number}" created successfully!')
            return redirect('home')
    else:
        form = VehicleForm()
    
    return render(request, 'logistics/new_vehicle.html', {'form': form})