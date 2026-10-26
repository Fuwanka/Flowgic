# Каталог доступен операторам; подписка и счётчики всегда относятся к request.auth.company, а не к
# параметрам URL.
from ninja import Router

from accounts.authentication import jwt_auth
from accounts.schemas import ErrorOut

from . import services
from .schemas import PlanOut, SubscriptionOut

router = Router(tags=['billing'], auth=jwt_auth)


@router.get('/subscription', response={200: SubscriptionOut, 401: ErrorOut, 403: ErrorOut}, operation_id='getCompanySubscription')
def subscription(request):
    return services.get_billing_profile(request.auth)


@router.get('/plans', response={200: list[PlanOut], 401: ErrorOut, 403: ErrorOut}, operation_id='listSubscriptionPlans')
def plans(request):
    return services.get_available_plans(request.auth)
