# Единая точка сборки модулей и формата ошибок. Общие обработчики не возвращают traceback, пароли
# или значения JWT.
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from ninja import NinjaAPI
from ninja.errors import AuthenticationError, ValidationError

from accounts.api import router as accounts_router
from accounts.exceptions import AccountError
from billing.api import router as billing_router
from billing.exceptions import QuotaExceededError
from marketplace.api import router as marketplace_router
from marketplace.exceptions import MarketplaceError
from logistics.api import router as logistics_router
from logistics.documents import DocumentDataError
from document_processing.api import router as document_processing_router
from document_processing.exceptions import ProcessingError

api = NinjaAPI(title='Flowgic API', version='1.0.0')


@api.exception_handler(ProcessingError)
def processing_error(request, error):
    return api.create_response(request, {'detail': error.detail, 'code': error.code}, status=error.status)


@api.exception_handler(PermissionDenied)
def permission_denied(request, error):
    return api.create_response(request, {'detail': str(error), 'code': 'permission_denied'}, status=403)


@api.exception_handler(Http404)
def not_found(request, error):
    return api.create_response(request, {'detail': 'Объект не найден.', 'code': 'not_found'}, status=404)


@api.exception_handler(DocumentDataError)
def document_data_error(request, error):
    return api.create_response(request, {'detail': str(error), 'code': 'document_data_error'}, status=400)


@api.exception_handler(QuotaExceededError)
def quota_exceeded(request, error):
    return api.create_response(request, error.as_dict(), status=402)


@api.exception_handler(MarketplaceError)
def marketplace_error(request, error):
    return api.create_response(request, {'detail': error.detail, 'code': error.code}, status=error.status)


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
api.add_router('/billing', billing_router)
api.add_router('/marketplace', marketplace_router)
api.add_router('/logistics', logistics_router)
api.add_router('/document-processing', document_processing_router)
