# Регистрация marketplace; выбор подходящих предложений выполняется при запросе, не при старте
# Django.
from django.apps import AppConfig


class MarketplaceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'marketplace'
