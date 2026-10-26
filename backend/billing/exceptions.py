# Структура quota_exceeded является контрактом HTTP 402 и окна тарифа в React.
class QuotaExceededError(Exception):
    def __init__(self, *, resource, limit, current, plan_type):
        self.resource = resource
        self.limit = limit
        self.current = current
        self.plan_type = plan_type
        label = {'vehicles': 'активных транспортных средств', 'orders': 'заказов за месяц'}[resource]
        self.detail = f'Лимит {label} тарифа {plan_type} достигнут. Выберите подходящий тариф.'
        super().__init__(self.detail)

    def as_dict(self):
        return {
            'detail': self.detail, 'code': 'quota_exceeded', 'resource': self.resource,
            'limit': self.limit, 'current': self.current, 'plan_type': self.plan_type,
        }
