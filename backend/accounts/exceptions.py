"""Application errors shared by HTML and API adapters."""


class AccountError(Exception):
    def __init__(self, detail, *, code='invalid_input', status=400):
        super().__init__(detail)
        self.detail = detail
        self.code = code
        self.status = status


def authentication_failed():
    return AccountError(
        'Неверные учётные данные или недействительный токен.',
        code='authentication_failed', status=401,
    )
