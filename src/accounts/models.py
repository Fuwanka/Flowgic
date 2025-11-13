from django.db import models
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
        class Role(models.TextChoices):
            DISPATCHER = 'dispatcher', 'Диспетчер'
            DRIVER = 'driver', 'Водитель'
            CUSTOMER = 'customer', 'Заказчик'
            MANAGER = 'manager', 'Руководитель'

        role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        verbose_name='Роль пользователя'
        )

        def __str__(self):
            return f"{self.username} ({self.get_role_display()})"
