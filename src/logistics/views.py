from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.utils import timezone
from accounts.decorators import role_required
from .models import Order, Vehicle, Company, Client, Financial
from decimal import Decimal
from accounts.models import User
from django.shortcuts import get_object_or_404, render
import datetime
from django.utils.timezone import now
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth

from django.core.serializers.json import DjangoJSONEncoder
import json


@role_required(['dispatcher'])
def dispatcher_dashboard(request):
    return render(request, 'logistics/dispatcher_dashboard.html')


@role_required(['driver'])
def driver_dashboard(request):
    return render(request, 'logistics/driver_dashboard.html')


@role_required(['customer', 'manager'])
def customer_dashboard(request):
    return render(request, 'logistics/customer_dashboard.html')


@login_required
def new_request(request):
    """View for creating a new order/request"""
    from .forms import OrderForm
    
    if request.method == 'POST':
        form = OrderForm(request.POST, user=request.user)
        if form.is_valid():
            order = form.save(commit=False)
            order.created_by = request.user
            order.save()
            messages.success(request, f'Order #{order.id} created successfully!')
            return redirect('request_detail', order_id=order.id)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = OrderForm(user=request.user)
    
    return render(request, 'logistics/new_request.html', {'form': form})


@login_required
def request_detail(request, order_id):
    """View for displaying order details"""
    order = get_object_or_404(Order, id=order_id)

    # Always create Financial if not exists
    Financial.objects.get_or_create(
        order=order,
        defaults={
            'client_cost': order.agreed_price or Decimal('0.00'),
            'driver_cost': Decimal('0.00'),
            'fuel_expenses': Decimal('0.00'),
            'third_party_cost': Decimal('0.00'),
        }
    )

    # Mark as viewed if driver opens their assigned order
    if request.user.role == 'driver' and order.driver == request.user:
        if not order.is_viewed_by_driver:
            order.is_viewed_by_driver = True
            order.save()
    
    # Create a dictionary for quick status lookup
    status_dict = dict(Order.Status.choices)
    
    return render(request, 'logistics/request_detail.html', {
        'order': order,
        'status_choices': Order.Status.choices,
        'status_dict': status_dict,
        'user': request.user
    })


@login_required
def edit_order(request, order_id):
    """View for editing order - dispatchers can edit driver/status, drivers can edit status only"""
    order = get_object_or_404(Order, id=order_id)
    
    # Determine which form to use based on role
    if request.user.role == 'dispatcher':
        from .forms import OrderEditForm
        FormClass = OrderEditForm
    elif request.user.role == 'driver' and order.driver == request.user:
        from .forms import DriverOrderStatusForm
        FormClass = DriverOrderStatusForm
    else:
        messages.error(request, 'You do not have permission to edit this order')
        return redirect('request_detail', order_id=order.id)
    
    if request.method == 'POST':
        form = FormClass(request.POST, instance=order)
        if form.is_valid():
            form.save()
            messages.success(request, 'Order updated successfully!')
            return redirect('request_detail', order_id=order.id)
    else:
        form = FormClass(instance=order)
    
    context = {
        'form': form,
        'order': order,
        'is_driver': request.user.role == 'driver',
    }
    return render(request, 'logistics/edit_order.html', context)


@login_required
def update_payment_status(request, order_id):
    """Update payment status for an order (dispatcher/manager only)"""
    from django.http import JsonResponse
    from decimal import Decimal
    from .models import OrderEvent, Financial
    
    # Check permissions
    if request.user.role not in ['dispatcher', 'manager']:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    order = get_object_or_404(Order, id=order_id)
    
    try:
        fully_paid = request.POST.get('fully_paid') == 'true'
        partial_amount = request.POST.get('partial_amount', '').strip()
        
        # Get or create Financial record
        financial, created = Financial.objects.get_or_create(
            order=order,
            defaults={
                'client_cost': order.agreed_price or Decimal('0.00'),
                'driver_cost': Decimal('0.00'),
                'profit': Decimal('0.00'),
            }
        )
        
        old_status = financial.payment_status
        event_data = {}
        
        if fully_paid:
            # Mark as fully paid
            financial.payment_status = 'paid'
            event_data = {'action': 'marked_as_paid', 'user': request.user.username}
        elif partial_amount:
            # Update partial payment
            try:
                amount = Decimal(partial_amount)
                if amount <= 0:
                    return JsonResponse({'success': False, 'error': 'Amount must be positive'}, status=400)
                
                financial.payment_status = 'partially_paid'
                # Store partial amount in payment_plan as the current partial payment
                financial.payment_plan = {
                    'partial_amount': str(amount),
                    'updated_by': request.user.username,
                    'updated_at': str(timezone.now())
                }
                event_data = {'action': 'partial_payment', 'amount': str(amount), 'user': request.user.username}
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Invalid amount'}, status=400)
        else:
            return JsonResponse({'success': False, 'error': 'No payment data provided'}, status=400)
        
        financial.save()
        
        # Log payment update event if status changed
        if old_status != financial.payment_status:
            OrderEvent.objects.create(
                order=order,
                event_type='payment_updated',
                event_data=event_data
            )
        
        return JsonResponse({
            'success': True,
            'payment_status': financial.payment_status,
            'payment_status_display': financial.get_payment_status_display()
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def update_order_status(request, order_id):
    """Update order status (dispatcher/manager only)"""
    from django.http import JsonResponse
    from .models import OrderEvent
    
    # Check permissions
    if request.user.role not in ['dispatcher', 'manager']:
        return JsonResponse({'success': False, 'error': 'Permission denied'}, status=403)
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    order = get_object_or_404(Order, id=order_id)
    
    try:
        new_status = request.POST.get('status', '').strip()
        
        if not new_status:
            return JsonResponse({'success': False, 'error': 'Status is required'}, status=400)
        
        # Validate status
        valid_statuses = [choice[0] for choice in Order.Status.choices]
        if new_status not in valid_statuses:
            return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
        
        old_status = order.status
        
        if old_status != new_status:
            order.status = new_status
            order.save()
            
            # Log status change event
            OrderEvent.objects.create(
                order=order,
                event_type='status_changed',
                event_data={
                    'old_status': old_status,
                    'new_status': new_status,
                    'user': request.user.username
                }
            )
            
            return JsonResponse({
                'success': True,
                'status': order.status,
                'status_display': order.get_status_display()
            })
        else:
            return JsonResponse({'success': False, 'error': 'Status unchanged'}, status=400)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@role_required(['dispatcher', 'manager'])
@require_POST
def update_financials(request, order_id):
    from .models import OrderEvent

    order = get_object_or_404(Order, id=order_id)

    # Обязательно создаём Financial, если его нет
    financial, created = Financial.objects.get_or_create(
        order=order,
        defaults={
            'client_cost': order.agreed_price or Decimal('0.00'),
            'driver_cost': Decimal('0.00'),
            'fuel_expenses': Decimal('0.00'),
            'third_party_cost': Decimal('0.00'),
        }
    )

    try:
        fuel_expenses = Decimal(request.POST.get('fuel_expenses', '0'))
        driver_cost = Decimal(request.POST.get('driver_cost', '0'))

        # Сохраняем старые значения для логирования
        old_fuel_expenses = financial.fuel_expenses
        old_driver_cost = financial.driver_cost
        old_profit = financial.profit
        client_cost = Decimal(request.POST.get('client_cost', str(financial.client_cost)))
        financial.client_cost = client_cost

        """
        order.refresh_from_db()  # на случай кэша
        agreed_price = order.agreed_price or Decimal('0.00')
        if financial.client_cost != agreed_price:
            financial.client_cost = agreed_price
        """
        
        # Обновляем финансовую запись (client_cost уже установлен как agreed_price)
        financial.fuel_expenses = fuel_expenses
        financial.driver_cost = driver_cost
        financial.save()  # Прибыль пересчитается автоматически

        # Логируем изменения в истории заказа
        if old_fuel_expenses != fuel_expenses or old_driver_cost != driver_cost:
            event_data = {
                'old_fuel_expenses': str(old_fuel_expenses),
                'new_fuel_expenses': str(fuel_expenses),
                'old_driver_cost': str(old_driver_cost),
                'new_driver_cost': str(driver_cost),
                'old_profit': str(old_profit),
                'new_profit': str(financial.profit),
                'user': request.user.username
            }
            OrderEvent.objects.create(
                order=order,
                event_type='financials_updated',
                event_data=event_data
            )

        return JsonResponse({
            'success': True,
            'profit': str(financial.profit)
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@login_required
def dashboard_vehicles(request):
    """Список транспорта компании с краткой статистикой и действиями."""
    if not request.user.company:
        messages.error(request, 'У вас не указана компания.')
        return redirect('home')
    vehicles = Vehicle.objects.filter(company=request.user.company).order_by('reg_number')
    return render(request, 'logistics/vehicles_list.html', {'vehicles': vehicles})

@login_required
def vehicle_detail(request, vehicle_id):
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)

    # связанные заказы (если есть)
    orders = vehicle.orders.all() if hasattr(vehicle, 'orders') else []

    # --- Заменяем здесь: получаем реальные записи ТО из модели Maintenance ---
    # ------------------------------------------------------------------------

    # подготовка status_choices (если используется)
    status_choices = []
    try:
        choices_iter = vehicle.Status.choices
    except Exception:
        choices_iter = getattr(Vehicle, 'Status', getattr(Vehicle, 'STATUS_CHOICES', []))
    for item in choices_iter:
        try:
            key, label = item
        except Exception:
            continue
        status_choices.append((key, label, key == vehicle.status))

    return render(request, 'logistics/vehicle_detail.html', {
        'vehicle': vehicle,
        'orders': orders,
        'status_choices': status_choices,
    })

@login_required
@role_required(['dispatcher', 'manager'])
@require_POST
def vehicle_update_status(request, vehicle_id):
    """Обновление статуса ТС (доступно диспетчеру/менеджеру)."""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    new_status = request.POST.get('status', '').strip()
    valid_statuses = [choice[0] for choice in Vehicle.Status.choices]
    if new_status not in valid_statuses:
        return JsonResponse({'success': False, 'error': 'Invalid status'}, status=400)
    vehicle.status = new_status
    vehicle.save(update_fields=['status'])
    return JsonResponse({'success': True, 'status': vehicle.status, 'status_display': vehicle.get_status_display()})

@login_required
@role_required(['dispatcher', 'manager'])
@require_POST
def vehicle_plan_maintenance(request, vehicle_id):
    """Планирование ТО (минимальная версия: обновить дату last_maintenance и комментарий в истории)."""
    vehicle = get_object_or_404(Vehicle, id=vehicle_id)
    date_str = request.POST.get('date', '').strip()
    note = request.POST.get('note', '').strip()
    if not date_str:
        return JsonResponse({'success': False, 'error': 'Date is required'}, status=400)
    try:
        # Формат: YYYY-MM-DD
        from datetime import datetime
        dt = datetime.strptime(date_str, '%Y-%m-%d').date()
        vehicle.last_maintenance = dt
        vehicle.save(update_fields=['last_maintenance'])
        return JsonResponse({'success': True, 'last_maintenance': str(vehicle.last_maintenance), 'note': note})
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid date format (YYYY-MM-DD)'}, status=400)
    


@login_required
def dashboard_clients(request):
    """Список клиентов компании."""
    if not request.user.company:
        messages.error(request, 'У вас не указана компания.')
        return redirect('home')
    clients = Client.objects.filter(company=request.user.company).order_by('name')
    return render(request, 'logistics/clients_list.html', {'clients': clients})

@login_required
def client_detail(request, client_id):
    """Карточка клиента: данные, история взаимодействий (по заказам)."""
    client = get_object_or_404(Client, id_client=client_id)
    orders = client.orders.all().order_by('-created_at')
    return render(request, 'logistics/client_detail.html', {'client': client, 'orders': orders})

@login_required
@role_required(['dispatcher', 'manager'])
def client_edit(request, client_id):
    """Редактирование клиента (имя/телефон/email)."""
    client = get_object_or_404(Client, id_client=client_id)
    from accounts.forms import ClientForm
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, 'Клиент обновлён')
            return redirect('client_detail', client_id=client.id_client)
    else:
        form = ClientForm(instance=client)
    return render(request, 'logistics/client_edit.html', {'form': form, 'client': client})
   


@login_required
def dashboard_drivers(request):
    """Список водителей компании."""
    if not request.user.company:
        messages.error(request, 'У вас не указана компания.')
        return redirect('home')
    drivers = User.objects.filter(role='driver', company=request.user.company).order_by('full_name')
    return render(request, 'logistics/drivers_list.html', {'drivers': drivers})

@login_required
def driver_detail(request, user_id):
    """Карточка водителя: данные, историй заказов."""
    driver = get_object_or_404(User, id=user_id, role='driver')
    orders = Order.objects.filter(driver=driver).order_by('-created_at')
    return render(request, 'logistics/driver_detail.html', {'driver': driver, 'orders': orders})


def calendar_view(request):
    orders = Order.objects.all()
    
    events = []
    for order in orders:
        events.append({
            'title': f"Заказ {order.order_number}: {order.client.name or 'Клиент'}",
            'start': order.pickup_datetime.isoformat(),
            'end': order.delivery_datetime.isoformat(),
            'color': "#37d842",
            'textColor': 'white',
            'extendedProps': {
                'cargo': order.cargo_type,
                'status': order.get_status_display()
            }
        })
    
    events_json = json.dumps(events, cls=DjangoJSONEncoder, ensure_ascii=False)
    
    return render(request, 'logistics/calendar.html', {'events_json': events_json})

@login_required
@role_required(['manager'])
def manager_dashboard(request):
    company = request.user.company
    if not company:
        messages.error(request, "У вас не указана компания.")
        return redirect('home')

    # --- Заказы компании ---
    orders = Order.objects.filter(created_by__company=company).select_related('driver', 'vehicle', 'client', 'financial').order_by('-created_at')

    # --- Статистика по водителям ---
    drivers = User.objects.filter(role='driver', company=company)
    driver_stats = []
    for driver in drivers:
        assigned_count = orders.filter(driver=driver, status__in=[
            Order.Status.ASSIGNED, Order.Status.LOADING, Order.Status.IN_TRANSIT
        ]).count()
        driver_stats.append({
            'driver': driver,
            'assigned_count': assigned_count
        })

    # --- Генерация событий для календаря ---
    events = []
    for order in orders:
        if order.pickup_datetime and order.delivery_datetime:
            events.append({
                'title': f"Заказ {order.order_number}: {order.client.name if order.client else 'Клиент'}",
                'start': order.pickup_datetime.isoformat(),
                'end': order.delivery_datetime.isoformat(),
                'color': "#37d842",
                'textColor': "white",
                'extendedProps': {
                    'cargo': order.cargo_type,
                    'status': order.get_status_display()
                }
            })
    events_json = json.dumps(events, cls=DjangoJSONEncoder, ensure_ascii=False)

    context = {
        'orders': orders,
        'driver_stats': driver_stats,
        'events_json': events_json,
    }

    return render(request, 'logistics/manager_dashboard.html', context)