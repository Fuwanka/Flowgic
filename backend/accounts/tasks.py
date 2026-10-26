# Письмо запускается после commit, чтобы не отправить код от отменённой транзакции. Транспорт задаёт
# EMAIL_BACKEND.
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_password_reset_email(email, code):
    return send_mail(
        subject='Сброс пароля Flowgic',
        message=f'Ваш код для сброса пароля: {code}. Код действует 10 минут.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
