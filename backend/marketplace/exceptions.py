# Ошибки доступности оффера преобразуются центральным API в контролируемые 400/403/404.
class MarketplaceError(Exception):
    def __init__(self, detail, *, code='invalid_marketplace_input', status=400):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status = status
