import uuid

from django.conf import settings
from django.db import models


class ProcessedDocument(models.Model):
    class Status(models.TextChoices):
        QUEUED = 'queued', 'В очереди'
        PROCESSING = 'processing', 'Распознаётся'
        NEEDS_REVIEW = 'needs_review', 'Требует проверки'
        CONFIRMED = 'confirmed', 'Подтверждён'
        FAILED = 'failed', 'Ошибка'

    class Type(models.TextChoices):
        AUTO = 'auto', 'Определить автоматически'
        TN = 'tn', 'Транспортная накладная'
        TTN = 'ttn', 'Товарно-транспортная накладная'
        TORG12 = 'torg12', 'ТОРГ-12'
        UPD = 'upd', 'УПД'
        REQUEST = 'request', 'Заявка'
        OTHER = 'other', 'Прочий'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey('logistics.Company', on_delete=models.CASCADE, related_name='processed_documents')
    order = models.ForeignKey('logistics.Order', on_delete=models.CASCADE, related_name='processed_documents')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='uploaded_documents')
    upload_key = models.UUIDField()
    original_filename = models.CharField(max_length=200)
    content_type = models.CharField(max_length=50)
    storage_key = models.CharField(max_length=250)
    sha256 = models.CharField(max_length=64)
    byte_size = models.PositiveIntegerField()
    requested_type = models.CharField(max_length=10, choices=Type.choices, default=Type.AUTO)
    document_type = models.CharField(max_length=10, choices=Type.choices, default=Type.AUTO)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    version = models.PositiveIntegerField(default=1)
    attempts = models.PositiveSmallIntegerField(default=0)
    run_token = models.UUIDField(null=True, editable=False)
    processing_started_at = models.DateTimeField(null=True)
    engine = models.CharField(max_length=100, null=True)
    pages = models.JSONField(default=list)
    fields = models.JSONField(default=dict)
    confirmed_fields = models.JSONField(default=dict)
    warnings = models.JSONField(default=list)
    error = models.CharField(max_length=300, null=True)
    order_baseline = models.JSONField(default=dict)
    confirmed_at = models.DateTimeField(null=True)
    confirmed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='confirmed_documents')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['company', 'upload_key'], name='ocr_company_upload_key')]
        indexes = [models.Index(fields=['company', 'order', '-created_at']), models.Index(fields=['company', 'status'])]


class DocumentReview(models.Model):
    """Snapshot of the operator's confirmation, separate from OCR evidence."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey('logistics.Company', on_delete=models.CASCADE)
    document = models.OneToOneField(ProcessedDocument, on_delete=models.CASCADE, related_name='review')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    document_type = models.CharField(max_length=10)
    fields = models.JSONField()
    order_changes = models.JSONField(default=dict)
    apply_to_order = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
