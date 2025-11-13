from django.db import models
from src.accounts.models import User

class Cargo(models.Model):
    name = models.CharField(max_length=100, verbose_name='Название груза')
    description = models.TextField(blank=True, verbose_name='Описание')
    weight = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Вес (кг)')
    category = models.CharField(max_length=50, verbose_name='Категория')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.weight} кг)"

class Driver(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, limit_choices_to={'role': 'driver'})
    license_number = models.CharField(max_length=50, verbose_name='Номер лицензии')
    vehicle = models.CharField(max_length=100, verbose_name='Транспортное средство')
    status = models.CharField(
        max_length=20,
        choices=[('available', 'Свободен'), ('busy', 'В рейсе')],
        default='available'
    )

    def __str__(self):
        return f"{self.user.username} — {self.vehicle}"
    
class Route(models.Model):
    cargo = models.ForeignKey(Cargo, on_delete=models.CASCADE)
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True)
    customer = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'role': 'customer'})
    start_point = models.CharField(max_length=100, verbose_name='Пункт отправления')
    end_point = models.CharField(max_length=100, verbose_name='Пункт назначения')
    date_start = models.DateField()
    date_end = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('created', 'Создан'),
            ('in_transit', 'В пути'),
            ('completed', 'Завершён'),
            ('canceled', 'Отменён')
        ],
        default='created'
    )

    def __str__(self):
        return f"{self.cargo.name}: {self.start_point} → {self.end_point}"