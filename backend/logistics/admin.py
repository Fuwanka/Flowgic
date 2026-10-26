# Административная работа с доменными данными; штатные пользователи SPA работают через tenant-scoped
# API.
from django.contrib import admin
from .models import Company, Vehicle, Order

admin.site.register(Company)
admin.site.register(Vehicle)
admin.site.register(Order)

