from django.db import models
from django.contrib.auth.models import AbstractUser
from django.dispatch import dispatcher


class User(AbstractUser):
    class Role(models.TextChoices):
        Dispatcher = 'dispatcher', 'Диспетчер'
        Manager = 'manager', 'руководитель'
        Driver = 'driver', 'водитель'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Активен'
        INVITED = 'invited', 'Приглашён'
        BLOCKED = 'blocked', 'Заблокирован'

    # Ссылка на компанию (обязательное поле)
    company = models.ForeignKey(
        'logistics.Company',
        on_delete=models.CASCADE,
        related_name='users',
        db_column='company_id',
        verbose_name='Компания',
        null=True,
        blank=True
    )
    
    # В AbstractUser email уже имеет unique=True, но можно переопределить
    email = models.EmailField(unique=True, verbose_name='Email')
    
    # Телефон
    phone = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name='Телефон'
    )
    
    # Полное имя (можно использовать first_name и last_name из AbstractUser)
    # Но добавим full_name для удобства
    full_name = models.CharField(
        max_length=255,
        blank=True,
        verbose_name='ФИО',
        help_text='Полное имя пользователя'
    )
    
    # Роль пользователя
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.Driver,
        verbose_name='Роль пользователя'
    )
    
    # Статус аккаунта
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name='Статус аккаунта'
    )
    
    # Password уже есть в AbstractUser
    # last_login уже есть в AbstractUser
    # date_joined (created_at) уже есть в AbstractUser как date_joined

    class Meta:
        db_table = 'users'
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        # Убираем username из обязательных полей, используем email для входа
        # Но оставляем username для совместимости

    def save(self, *args, **kwargs):
        # Автоматически заполняем full_name из first_name и last_name, если не указано
        if not self.full_name and (self.first_name or self.last_name):
            self.full_name = f"{self.first_name} {self.last_name}".strip()
        super().save(*args, **kwargs)

    def __str__(self):
        name = self.full_name or self.get_full_name() or self.username
        return f"{name} ({self.get_role_display()})"
