from django.urls import path
from . import views

urlpatterns = [
    path('dispatcher/', views.dispatcher_dashboard, name='dispatcher_dashboard'),
    path('driver/', views.driver_dashboard, name='driver_dashboard'),
    path('customer/', views.customer_dashboard, name='customer_dashboard'),
    path('new/', views.new_request, name='new_request'),
    path('request/<uuid:order_id>/', views.request_detail, name='request_detail'),
    path('order/<uuid:order_id>/edit/', views.edit_order, name='edit_order'),
    path('request/<uuid:order_id>/payment/', views.update_payment_status, name='update_payment_status'),
    path('request/<uuid:order_id>/status/', views.update_order_status, name='update_order_status'),
]
