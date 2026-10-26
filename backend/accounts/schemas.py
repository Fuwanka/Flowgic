# Входные DTO запрещают лишние поля: браузер не может передать company, is_staff или произвольное
# повышение роли.
from typing import Literal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from ninja import Schema
from pydantic import ConfigDict, Field, field_validator

from .models import User
from .security import normalize_email


class InputSchema(Schema):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)


class EmailIn(InputSchema):
    email: str = Field(max_length=254, json_schema_extra={'format': 'email'})

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        value = normalize_email(value)
        try:
            validate_email(value)
        except ValidationError as error:
            raise ValueError('Некорректный email.') from error
        return value


class LoginIn(EmailIn):
    password: str = Field(min_length=1, max_length=128)


class RegistrationIn(LoginIn):
    full_name: str = Field(min_length=1, max_length=255)
    company_name: str = Field(min_length=1, max_length=255)
    company_type: Literal['logistics', 'manufacturer', 'retail', 'government'] = 'logistics'
    role: User.Role = User.Role.Manager

    @field_validator('full_name', 'company_name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Поле не должно быть пустым.')
        return value.strip()


class RefreshIn(InputSchema):
    refresh: str = Field(min_length=1, max_length=4096)


class VerifyIn(InputSchema):
    token: str = Field(min_length=1, max_length=4096)


class PasswordResetConfirmIn(EmailIn):
    code: str = Field(pattern=r'^[0-9]{6}$')
    new_password: str = Field(min_length=1, max_length=128)


class PasswordChangeIn(InputSchema):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class ProfileUpdateIn(InputSchema):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    theme: User.Theme | None = None

    @field_validator('full_name', 'theme')
    @classmethod
    def not_null(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError('Поле не должно быть пустым.')
        return value


class CompanyOut(Schema):
    id_company: UUID
    name: str
    type: str


class ProfileOut(Schema):
    id: int
    email: str
    full_name: str
    phone: str | None
    role: User.Role
    status: User.Status
    theme: User.Theme
    company: CompanyOut


class TokenPairOut(Schema):
    access: str
    refresh: str


class RegistrationOut(Schema):
    user: ProfileOut
    tokens: TokenPairOut


class MessageOut(Schema):
    detail: str


class ErrorOut(Schema):
    detail: str
    code: str


class DriverOut(Schema):
    """Справочник не раскрывает пароли, служебные флаги или чужую компанию."""
    id: int
    email: str
    full_name: str
    phone: str | None
    status: User.Status


class DriverCreateIn(EmailIn):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    password: str = Field(min_length=8, max_length=128)


class DriverUpdateIn(InputSchema):
    full_name: str = Field(min_length=1, max_length=255)
    phone: str | None = Field(default=None, max_length=20)
    status: User.Status = User.Status.ACTIVE
