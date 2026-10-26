# Ключи Redis не раскрывают email; password stamp делает выпущенные JWT недействительными после
# смены пароля.
"""Pure helpers; never trust role/company claims supplied by a client."""
from django.utils.crypto import salted_hmac


def normalize_email(email):
    return (email or '').strip().lower()


def password_stamp(user):
    return salted_hmac('accounts.jwt.password', user.password).hexdigest()


def private_cache_key(purpose, value):
    digest = salted_hmac(f'accounts.{purpose}', str(value)).hexdigest()
    return f'accounts:{purpose}:{digest}'
