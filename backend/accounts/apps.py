# Регистрация Django-приложения accounts; бизнес-правила не выполняются при импорте конфигурации.
from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
