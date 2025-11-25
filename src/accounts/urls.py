from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from django.shortcuts import redirect

urlpatterns = [
    path('login/', views.custom_login_view, name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('register/', views.register_view, name='register'),
    path('', lambda request: redirect('home')),  # корень сайта → редирект на home
    path('home/', views.home_view, name='home'),
]
