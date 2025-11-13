from django.urls import path
from django.contrib.auth import views as auth_views
from .views import dispatcher_page, driver_page, client_page

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='/login/'), name='logout'),
    path('dispatcher/', dispatcher_page, name='dispatcher'),
    path('driver/', driver_page, name='driver'),
    path('client/', client_page, name='client'),
]
