from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import EmailStr, Field

from app.schemas.base import BaseSchema
from app.schemas.users import UserRead

class OtpRequestIn(BaseSchema):
    phone: str


class OtpVerifyIn(BaseSchema):
    challenge_id: str
    code: str


class RegisterIn(BaseSchema):
    name: str = Field(min_length=1)
    email: EmailStr | None = None


class RefreshIn(BaseSchema):
    refresh_token: str


class OtpRequestOut(BaseSchema):
    challenge_id: str
    expires_at: datetime


class AuthenticatedOut(BaseSchema):
    status: Literal["authenticated"] = "authenticated"
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserRead


class RegistrationRequiredOut(BaseSchema):
    status: Literal["registration_required"] = "registration_required"
    registration_token: str


# Discriminated union for /otp/verify — OpenAPI renders it as a `oneOf` keyed on
# `status`, so the client (and Swagger) sees both success shapes explicitly.
VerifyOut = Annotated[
    Union[AuthenticatedOut, RegistrationRequiredOut],
    Field(discriminator="status"),
]


class AccessTokenOut(BaseSchema):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
