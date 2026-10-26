# company=NULL — общий каталог. Демо-оффер обязательно принадлежит компании; логи кликов разделены
# по tenant.
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from .validators import validate_offer_url


class PartnerOffer(models.Model):
    class Category(models.TextChoices):
        INSURANCE = 'INSURANCE', 'Страхование груза'
        FUEL = 'FUEL', 'Топливные карты'
        FACTORING = 'FACTORING', 'Факторинг'
        TELEMATICS = 'TELEMATICS', 'Телематика'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=80, unique=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    target_url = models.URLField(max_length=1000, validators=[validate_offer_url])
    active = models.BooleanField(default=True)
    company = models.ForeignKey(
        'logistics.Company', null=True, blank=True, on_delete=models.CASCADE,
        related_name='partner_offers',
        help_text='Пусто — общий каталог; компания — предложение только для её пользователей.',
    )
    is_demo = models.BooleanField(default=False)
    minimum_order_value = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal('100000.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text='Минимальная стоимость заказа для страхового предложения.',
    )
    priority = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['priority', 'id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minimum_order_value__gte=0),
                name='marketplace_offer_minimum_nonnegative',
            ),
            models.CheckConstraint(
                condition=models.Q(is_demo=False) | models.Q(company__isnull=False),
                name='marketplace_demo_offer_has_company',
            ),
        ]

    def __str__(self):
        return self.title


class OfferClickLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(
        'logistics.Company', on_delete=models.CASCADE, related_name='offer_clicks',
    )
    offer = models.ForeignKey(PartnerOffer, on_delete=models.PROTECT, related_name='clicks')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='offer_clicks',
    )
    order = models.ForeignKey(
        'logistics.Order', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='offer_clicks',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', 'id']
        indexes = [
            models.Index(fields=['company', '-created_at'], name='marketplace_click_company_time'),
            models.Index(fields=['offer', '-created_at'], name='marketplace_click_offer_time'),
        ]
