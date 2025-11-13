from django.shortcuts import redirect
from django.contrib.auth import authenticate, login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render


def custom_login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            # Редирект в зависимости от роли
            if user.role == 'dispatcher':
                return redirect('dispatcher_dashboard')
            elif user.role == 'driver':
                return redirect('driver_dashboard')
            elif user.role in ['customer', 'manager']:
                return redirect('customer_dashboard')
    else:
        form = AuthenticationForm()
    return render(request, 'accounts/login.html', {'form': form})
