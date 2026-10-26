"""Billing currently evaluates quotas synchronously at each protected write.

Celery workers can use public billing services for future notification/report
tasks; quota enforcement must never depend on an asynchronous task finishing.
"""
