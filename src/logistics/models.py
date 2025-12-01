import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import MinValueValidator
from decimal import Decimal

import accounts


# ---------------------------------------------------------
# 1. Компания (companies)
# ---------------------------------------------------------
class Company(models.Model):
    class Type(models.TextChoices):
        LOGISTICS = 'logistics', 'Логистика'
        MANUFACTURER = 'manufacturer', 'Производитель'
        RETAIL = 'retail', 'Розница'
        GOVERNMENT = 'government', 'Государственный'

    id_company = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, verbose_name='Название компании')
    inn = models.CharField(max_length=12, blank=True, null=True, verbose_name='ИНН')
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        verbose_name='Отраслевая принадлежность'
    )
    
    address = models.JSONField(
        blank=True,
        null=True,
        verbose_name='Адрес',
        help_text='Структурированный адрес: {region, city, street, building, postcode}'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата регистрации')

    class Meta:
        db_table = 'companies'
        verbose_name = 'Компания'
        verbose_name_plural = 'Компании'

    def __str__(self):
        return self.name

# ---------------------------------------------------------
# 2. Водитель (drivers) - его больше нет, он в accounts/models
# ---------------------------------------------------------

# ---------------------------------------------------------
# 3. Клиент (clients) - внешние заказчики перевозок
# ---------------------------------------------------------
class Client(models.Model):
    id_client = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='clients',
        db_column='company_id',
        verbose_name='Компания'
    )
    name = models.CharField(max_length=255, verbose_name='Название заказчика')
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name='Телефон')
    email = models.EmailField(blank=True, null=True, verbose_name='Email')
    class Meta:
        db_table = 'clients'
        verbose_name = 'Клиент'
        verbose_name_plural = 'Клиенты'

    def __str__(self):
        return self.name


# ---------------------------------------------------------
# 4. Транспортное средство (vehicles)
# ---------------------------------------------------------
class Vehicle(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Доступен'
        IN_TRIP = 'in_trip', 'В рейсе'
        MAINTENANCE = 'maintenance', 'На обслуживании'
        BLOCKED = 'blocked', 'Заблокирован'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='vehicles',
        db_column='company_id',
        verbose_name='Компания'
    )
    reg_number = models.CharField(
        max_length=20,
        verbose_name='Гос. номер',
        help_text='Уникальный в рамках компании'
    )
    type = models.CharField(max_length=50, verbose_name='Тип ТС', help_text='Например: "рефрижератор", "фура", "газель"')
    model = models.CharField(max_length=100, blank=True, null=True, verbose_name='Марка и модель')
    capacity_kg = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name='Грузоподъёмность (кг)'
    )
    last_maintenance = models.DateField(blank=True, null=True, verbose_name='Дата последнего ТО')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
        verbose_name='Статус'
    )

    class Meta:
        db_table = 'vehicles'
        verbose_name = 'Транспортное средство'
        verbose_name_plural = 'Транспортные средства'
        unique_together = [['company', 'reg_number']]

    def __str__(self):
        return f"{self.reg_number} ({self.type})"


# ---------------------------------------------------------
# 5. Заказ на перевозку (orders)
# ---------------------------------------------------------
class Order(models.Model):
    class Status(models.TextChoices):
        CREATED = 'created', 'Создан'
        ASSIGNED = 'assigned', 'Назначен'
        LOADING = 'loading', 'Погрузка'
        IN_TRANSIT = 'in_transit', 'В пути'
        DELIVERED = 'delivered', 'Доставлен'
        COMPLETED = 'completed', 'Завершён'
        CANCELLED = 'cancelled', 'Отменён'
        DELAYED = 'delayed', 'Задержан'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='orders',
        db_column='client_id',
        verbose_name='Клиент'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_orders',
        db_column='created_by',
        verbose_name='Создал (диспетчер)'
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        db_column='vehicle_id',
        verbose_name='Транспортное средство'
    )
    driver = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        #related_name='orders',
        null=True,
        blank=True,
        db_column='driver_id',
        limit_choices_to={'role':'driver'},
        verbose_name='Водитель'
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
        verbose_name='Статус'
    )
    cargo_type = models.CharField(max_length=100, verbose_name='Тип груза')
    cargo_mass_kg = models.IntegerField(
        validators=[MinValueValidator(0)],
        verbose_name='Масса груза (кг)'
    )
    # Поля для маршрута
    origin = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Пункт отправления',
        help_text='Адрес или название точки отправления'
    )
    destination = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Пункт назначения',
        help_text='Адрес или название точки назначения'
    )
    agreed_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Договоренная стоимость',
        help_text='Стоимость перевозки'
    )
    pickup_datetime = models.DateTimeField(verbose_name='Плановое время забора')
    delivery_datetime = models.DateTimeField(verbose_name='Плановое время доставки')
    distance_km = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Расстояние (км)'
    )
    planned_route = models.TextField(
        blank=True,
        null=True,
        verbose_name='Маршрут',
        help_text='Координаты маршрута (GEOGRAPHY LINESTRING в PostGIS, здесь TextField)'
    )
    delay_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Причина задержки'
    )
    is_viewed_by_driver = models.BooleanField(
        default=False,
        verbose_name='Просмотрен водителем',
        help_text='Отмечается True когда водитель открывает заказ'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    class Meta:
        db_table = 'orders'
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']
    
    @property
    def cargo(self):
        """Alias for cargo_type for template compatibility"""
        return self.cargo_type

    @property
    def order_number(self):
        """Returns a short, user-friendly order number"""
        return str(self.id).split('-')[0].upper()

    def __str__(self):
        return f"Заказ #{self.id} — {self.cargo_type}"


# ---------------------------------------------------------
# 6. События по заказу (order_events)
# ---------------------------------------------------------
class OrderEvent(models.Model):
    class EventType(models.TextChoices):
        ASSIGNED = 'assigned', 'Назначен'
        LOADED = 'loaded', 'Загружен'
        DEPARTED = 'departed', 'Отправлен'
        TEMPERATURE_VIOLATION = 'temperature_violation', 'Нарушение температурного режима'
        DELIVERED = 'delivered', 'Доставлен'
        DOCUMENT_SIGNED = 'document_signed', 'Документ подписан'
        STATUS_CHANGED = 'status_changed', 'Изменение статуса'
        PAYMENT_UPDATED = 'payment_updated', 'Обновление оплаты'
        LOCATION_UPDATE = 'location_update', 'Обновление местоположения'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='events',
        db_column='order_id',
        verbose_name='Заказ'
    )
    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        verbose_name='Тип события'
    )
    event_data = models.JSONField(
        blank=True,
        null=True,
        verbose_name='Данные события',
        help_text='Дополнительные данные: координаты, скорость, уровень батареи датчика и т.д.'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Время события')

    class Meta:
        db_table = 'order_events'
        verbose_name = 'Событие по заказу'
        verbose_name_plural = 'События по заказам'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_event_type_display()} — Заказ #{self.order.id}"


# ---------------------------------------------------------
# 7. Документы (documents)
# ---------------------------------------------------------
class Document(models.Model):
    class Type(models.TextChoices):
        INVOICE = 'invoice', 'Счёт'
        ACT = 'act', 'Акт'
        UPD = 'upd', 'УПД'
        TTN = 'ttn', 'ТТН'
        CUSTOM = 'custom', 'Прочий'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        SENT = 'sent', 'Отправлен'
        SIGNED = 'signed', 'Подписан'
        PAID = 'paid', 'Оплачен'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='documents',
        db_column='order_id',
        verbose_name='Заказ'
    )
    type = models.CharField(
        max_length=20,
        choices=Type.choices,
        verbose_name='Тип документа'
    )
    number = models.CharField(max_length=50, unique=True, verbose_name='Номер документа')
    issued_at = models.DateField(verbose_name='Дата выставления')
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='Статус'
    )
    file_url = models.URLField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='Ссылка на файл',
        help_text='Ссылка на PDF-файл во внешнем хранилище'
    )
    data = models.JSONField(
        verbose_name='Данные документа',
        help_text='Структурированные реквизиты, суммы, подписи'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        db_table = 'documents'
        verbose_name = 'Документ'
        verbose_name_plural = 'Документы'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_type_display()} №{self.number}"


# ---------------------------------------------------------
# 8. Финансовые данные (financials) - строго 1:1 с Order
# ---------------------------------------------------------
class Financial(models.Model):
    class PaymentStatus(models.TextChoices):
        UNPAID = 'unpaid', 'Не оплачен'
        PARTIALLY_PAID = 'partially_paid', 'Частично оплачен'
        PAID = 'paid', 'Оплачен'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='financial',
        db_column='order_id',
        unique=True,
        verbose_name='Заказ'
    )
    client_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Сумма заказчику'
    )
    driver_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Выплата водителю'
    )
    third_party_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Сторонние расходы',
        help_text='Погрузка, парковка, экспедитор'
    )
    profit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        editable=False,
        verbose_name='Прибыль',
        help_text='Вычисляется как client_cost - driver_cost - third_party_cost'
    )
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        verbose_name='Статус оплаты'
    )
    payment_plan = models.JSONField(
        blank=True,
        null=True,
        verbose_name='График оплат',
        help_text='Массив объектов с датой, суммой и статусом оплаты'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')
    fuel_expenses = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name='Расходы на топливо'
    )

    class Meta:
        db_table = 'financials'
        verbose_name = 'Финансовые данные'
        verbose_name_plural = 'Финансовые данные'

    def save(self, *args, **kwargs):
        """Автоматически вычисляем прибыль при сохранении"""
        # --- Расчёт топлива ---
        AVERAGE_FUEL_CONSUMPTION_L_PER_100KM = Decimal('30.0')  # 30 литров на 100 км
        DIESEL_PRICE_PER_LITER = Decimal('82.0') # Цена бензина за литр

        if self.order.distance_km and self.order.distance_km > 0:
            distance = self.order.distance_km
            fuel_needed_liters = (distance / Decimal('100')) * AVERAGE_FUEL_CONSUMPTION_L_PER_100KM
            self.fuel_expenses = fuel_needed_liters * DIESEL_PRICE_PER_LITER
        else:
            self.fuel_expenses = Decimal('0.00')

        # --- Расчёт прибыли ---
        third_party = self.third_party_cost or Decimal('0.00')
        self.profit = self.client_cost - self.driver_cost - third_party
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Финансы заказа #{self.order.id}"
