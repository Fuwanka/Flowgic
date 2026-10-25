from ninja_jwt.authentication import JWTAuth
from ninja_jwt.exceptions import InvalidToken, TokenError

from . import services
from .exceptions import authentication_failed


class AccountJWTAuth(JWTAuth):
    def get_user(self, validated_token):
        return services.authenticate_token(validated_token)

    def authenticate(self, request, token):
        try:
            validated = self.get_validated_token(token)
        except (InvalidToken, TokenError, KeyError, TypeError, ValueError) as error:
            raise authentication_failed() from error
        user = self.get_user(validated)
        request.jwt_token = validated
        request.user = user
        return user


jwt_auth = AccountJWTAuth()
