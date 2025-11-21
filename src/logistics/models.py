from django.db import models
from django.conf import settings
from django.utils import timezone


# ---------------------------------------------------------
# 1. Компания
# ---------------------------------------------------------
class Company(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


# ---------------------------------------------------------
# 2. Водитель (сущность, связанная с пользователем)
# ---------------------------------------------------------
class Driver(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="drivers")

    license_number = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f"Водитель {self.user.username}"


# ---------------------------------------------------------
# 3. Транспорт
# ---------------------------------------------------------
class Vehicle(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="vehicles")

    plate_number = models.CharField(max_length=50)      # Госномер
    model = models.CharField(max_length=100)
    capacity_kg = models.PositiveIntegerField(default=0)
    volume_m3 = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.plate_number} ({self.model})"


# ---------------------------------------------------------
# 4. Заказ
# ---------------------------------------------------------
class Order(models.Model):
    STATUS_CHOICES = [
        ("created", "Создан"),
        ("assigned", "Назначен водителю"),
        ("in_progress", "В пути"),
        ("delivered", "Доставлен"),
        ("cancelled", "Отменён"),
    ]

    # Кто создал заказ (диспетчер)
    dispatcher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="dispatcher_orders"
    )

    # Кто является заказчиком
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="customer_orders"
    )

    driver = models.ForeignKey(
        Driver,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders"
    )

    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Информация о грузе
    cargo_type = models.CharField(max_length=255)
    weight = models.PositiveIntegerField()       # в кг
    volume = models.PositiveIntegerField()       # в литрах или м³ — на твой выбор

    # Адреса
    pickup_address = models.CharField(max_length=500)
    delivery_address = models.CharField(max_length=500)

    # Время
    pickup_time = models.DateTimeField(null=True, blank=True)
    delivery_time = models.DateTimeField(null=True, blank=True)

    # Статус
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="created"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True)

    def __str__(self):
        return f"Заказ #{self.id} — {self.cargo_type}"
