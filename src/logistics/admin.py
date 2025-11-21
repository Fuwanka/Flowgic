from django.contrib import admin
from .models import Company, Driver, Vehicle, Order

admin.site.register(Company)
admin.site.register(Driver)
admin.site.register(Vehicle)
admin.site.register(Order)
