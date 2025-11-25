from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, get_user_model
from django.contrib.auth.hashers import make_password
from django.contrib import messages
from logistics.models import Company  # Импортируем Company из logistics
from .models import User

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
        user = User.objects.create(
            full_name=full_name,
            email=email,
            password=make_password(password),  # хэшируем пароль
            company=company_obj,
            role=role
        )

        # Автоматически авторизуем пользователя после регистрации
        login(request, user)
        messages.success(request, f'Добро пожаловать, {full_name}!')
        return redirect('home')  # или куда нужно после регистрации

    return render(request, 'accounts/login_register.html', {'tab': 'register'})


def custom_login_view(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')

        # Аутентификация пользователя
        user = authenticate(request, email=email, password=password)

        if user is not None:
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.full_name}!')
            return redirect('home')  # или куда нужно после логина
        else:
            messages.error(request, 'Неверный email или пароль')
            return redirect('login')

    return render(request, 'accounts/login_register.html', {'tab': 'login'})
