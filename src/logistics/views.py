from django.shortcuts import render
from accounts.decorators import role_required


@role_required(['dispatcher'])
def dispatcher_dashboard(request):
    return render(request, 'logistics/dispatcher_dashboard.html')


@role_required(['driver'])
def driver_dashboard(request):
    return render(request, 'logistics/driver_dashboard.html')


@role_required(['customer', 'manager'])
def customer_dashboard(request):
    return render(request, 'logistics/customer_dashboard.html')

