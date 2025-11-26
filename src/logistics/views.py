from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import role_required
from .models import Order


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
        form = OrderForm(user=request.user)
    
    return render(request, 'logistics/new_request.html', {'form': form})


@login_required
def request_detail(request, order_id):
    """View for displaying order details"""
    order = get_object_or_404(Order, id=order_id)
    
    # Mark as viewed if driver opens their assigned order
    if request.user.role == 'driver' and order.driver == request.user:
        if not order.is_viewed_by_driver:
            order.is_viewed_by_driver = True
            order.save()
    
    return render(request, 'logistics/request_detail.html', {'order': order})


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

