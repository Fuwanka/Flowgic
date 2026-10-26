# Конфигурация домена перевозок. Миграции сохраняют существующие таблицы и внешние ключи.
from django.apps import AppConfig


class LogisticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'logistics'
