from django.urls import path
from . import views

urlpatterns = [
    path('dispatcher/', views.dispatcher_dashboard, name='dispatcher_dashboard'),
    path('driver/', views.driver_dashboard, name='driver_dashboard'),
    path('customer/', views.customer_dashboard, name='customer_dashboard'),
]
