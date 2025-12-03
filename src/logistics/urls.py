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
    path('request/<uuid:order_id>/update-financials/', views.update_financials, name='update_financials'),
    
    path('dashboard/vehicles/', views.dashboard_vehicles, name='dashboard_vehicles'),
    path('dashboard/vehicles/<uuid:vehicle_id>/', views.vehicle_detail, name='vehicle_detail'),
    path('dashboard/vehicles/<uuid:vehicle_id>/update-status/', views.vehicle_update_status, name='vehicle_update_status'),
    path('dashboard/vehicles/<uuid:vehicle_id>/plan-maintenance/', views.vehicle_plan_maintenance, name='vehicle_plan_maintenance'),

]

urlpatterns += [
    path('dashboard/clients/', views.dashboard_clients, name='dashboard_clients'),
    path('dashboard/clients/<uuid:client_id>/', views.client_detail, name='client_detail'),
    path('dashboard/clients/<uuid:client_id>/edit/', views.client_edit, name='client_edit'),
]

urlpatterns += [
    path('dashboard/drivers/', views.dashboard_drivers, name='dashboard_drivers'),
    path('dashboard/drivers/<int:user_id>/', views.driver_detail, name='driver_detail'),
]
