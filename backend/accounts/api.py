"""Transport adapters only: validation, authentication, application calls, output."""
from ninja import Router, Status

from . import selectors, services
from .authentication import jwt_auth
from .schemas import (
    EmailIn, ErrorOut, LoginIn, MessageOut, PasswordChangeIn,
    PasswordResetConfirmIn, ProfileOut, ProfileUpdateIn, RefreshIn,
    RegistrationIn, RegistrationOut, TokenPairOut, VerifyIn,
)

router = Router(tags=['accounts'])
RESET_MESSAGE = 'Если аккаунт существует, письмо с кодом будет отправлено.'


@router.post('/register', response={201: RegistrationOut, 400: ErrorOut, 409: ErrorOut}, operation_id='registerAccount')
def register(request, payload: RegistrationIn):
    user, tokens = services.register_with_tokens(**payload.model_dump())
    return Status(201, {'user': user, 'tokens': tokens})


@router.post('/token', response={200: TokenPairOut, 401: ErrorOut, 429: ErrorOut}, operation_id='loginAccount')
def login(request, payload: LoginIn):
    return services.login_with_tokens(**payload.model_dump(), request=request)


@router.post('/token/refresh', response={200: TokenPairOut, 401: ErrorOut}, operation_id='refreshTokens')
def refresh(request, payload: RefreshIn):
    return services.refresh_tokens(**payload.model_dump())


@router.post('/token/verify', response={200: MessageOut, 401: ErrorOut}, operation_id='verifyToken')
def verify(request, payload: VerifyIn):
    services.verify_token(**payload.model_dump())
    return {'detail': 'Токен действителен.'}


@router.post('/logout', auth=jwt_auth, response={200: MessageOut, 401: ErrorOut, 403: ErrorOut}, operation_id='logoutAccount')
def logout(request, payload: RefreshIn):
    services.logout(request.auth, **payload.model_dump(), access_token=request.jwt_token)
    return {'detail': 'Сессия завершена.'}


@router.get('/me', auth=jwt_auth, response={200: ProfileOut, 401: ErrorOut}, operation_id='getProfile')
def profile(request):
    return selectors.get_profile(request.auth)


@router.patch('/me', auth=jwt_auth, response={200: ProfileOut, 400: ErrorOut, 401: ErrorOut}, operation_id='updateProfile')
def update_profile(request, payload: ProfileUpdateIn):
    return services.update_profile(request.auth, **payload.model_dump(exclude_unset=True))


@router.post('/password/change', auth=jwt_auth, response={200: MessageOut, 400: ErrorOut, 401: ErrorOut}, operation_id='changePassword')
def change_password(request, payload: PasswordChangeIn):
    services.change_password(request.auth, **payload.model_dump())
    return {'detail': 'Пароль изменён. Войдите заново.'}


@router.post('/password/reset', response={202: MessageOut}, operation_id='requestPasswordReset')
def request_password_reset(request, payload: EmailIn):
    services.request_password_reset(**payload.model_dump())
    return Status(202, {'detail': RESET_MESSAGE})


@router.post('/password/reset/confirm', response={200: MessageOut, 400: ErrorOut}, operation_id='confirmPasswordReset')
def confirm_password_reset(request, payload: PasswordResetConfirmIn):
    services.confirm_password_reset(**payload.model_dump())
    return {'detail': 'Пароль изменён. Войдите заново.'}
