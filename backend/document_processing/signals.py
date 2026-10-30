"""Remove a private original only after its record deletion commits."""
from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ProcessedDocument
from .storage import private_storage


@receiver(post_delete, sender=ProcessedDocument)
def remove_private_original(sender, instance, **kwargs):
    storage, key = private_storage(), instance.storage_key
    transaction.on_commit(lambda: storage.delete(key), robust=True)
