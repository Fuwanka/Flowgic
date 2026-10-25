from django.core.exceptions import ValidationError as DjangoValidationError
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, ValidationError

from accounts.api import router as accounts_router
from accounts.exceptions import AccountError

api = NinjaAPI(title='Flowgic API', version='1.0.0')


@api.exception_handler(AccountError)
def account_error(request, error):
    response = api.create_response(request, {'detail': error.detail, 'code': error.code}, status=error.status)
    if error.status == 401:
        response['WWW-Authenticate'] = 'Bearer'
    return response


@api.exception_handler(AuthenticationError)
def missing_authentication(request, error):
    return account_error(request, AccountError('Требуется JWT.', code='authentication_failed', status=401))


@api.exception_handler(DjangoValidationError)
def domain_validation(request, error):
    return account_error(request, AccountError(' '.join(error.messages)))


@api.exception_handler(ValidationError)
def input_validation(request, error):
    # Never echo passwords or JWT values from validation inputs/context.
    detail = [
        {'loc': item.get('loc', []), 'msg': item.get('msg', 'Некорректное значение.'), 'type': item.get('type', 'value_error')}
        for item in error.errors
    ]
    return api.create_response(request, {'detail': detail}, status=422)


api.add_router('/accounts', accounts_router)
