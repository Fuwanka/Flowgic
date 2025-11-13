from django.contrib import admin
from .models import Cargo, Driver, Route

admin.site.register(Cargo)
admin.site.register(Driver)
admin.site.register(Route)