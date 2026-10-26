from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def validate_offer_url(value):
    """Offer links are outbound links only; the application never fetches them."""
    URLValidator(schemes=['http', 'https'])(value)
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValidationError('Ссылка предложения не должна содержать учётные данные.')
