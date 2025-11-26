from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from django.shortcuts import redirect

urlpatterns = [
    path('login/', views.custom_login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),  # ← исправлено
    path('', lambda request: redirect('home')),  # ← теперь отдельно
    path('home/', views.home_view, name='home'),
    path('delete_account/', views.delete_account_view, name='delete_account'),
    path('password_reset/', views.password_reset_request_view, name='password_reset_request'),
    path('password_reset_confirm/', views.password_reset_confirm_view, name='password_reset_confirm'),
    path('register/', views.register_view, name='register'),
    path('client/new/', views.create_client_view, name='create_client'),
]

