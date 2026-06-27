"""Authentication and identity schemas."""

from __future__ import annotations

from pydantic import EmailStr, Field

from banking_ai.schemas.common import ApiModel


class LoginRequest(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenPair(ApiModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(ApiModel):
    # Optional in body; browser clients send it via HttpOnly cookie instead.
    refresh_token: str | None = None


class CurrentUser(ApiModel):
    id: str
    email: EmailStr
    roles: list[str]
    permissions: list[str]
