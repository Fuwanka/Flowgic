# Worker получает настройки Django и Redis из окружения. Фоновые задачи не определяют разрешение на
# превышение квоты.
"""Celery application; connection settings are shared with Django."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flowgic.settings")

app = Celery("flowgic")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
