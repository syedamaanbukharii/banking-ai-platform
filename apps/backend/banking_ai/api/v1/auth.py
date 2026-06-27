"""Authentication endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from banking_ai.api.deps import PrincipalDep, SessionDep, SettingsDep
from banking_ai.core.config import Settings
from banking_ai.schemas.auth import CurrentUser, LoginRequest, RefreshRequest, TokenPair
from banking_ai.schemas.common import ErrorResponse
from banking_ai.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])

_RESPONSES: dict[int | str, dict[str, Any]] = {401: {"model": ErrorResponse}}


def _set_auth_cookies(response: Response, tokens: TokenPair, settings: Settings) -> None:
    response.set_cookie(
        "access_token",
        tokens.access_token,
        max_age=settings.security_access_token_ttl_seconds,
        httponly=True,
        secure=settings.security_cookie_secure,
        samesite="lax",
        domain=settings.security_cookie_domain or None,
    )
    response.set_cookie(
        "refresh_token",
        tokens.refresh_token,
        max_age=settings.security_refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.security_cookie_secure,
        samesite="lax",
        domain=settings.security_cookie_domain or None,
    )


@router.post("/login", response_model=TokenPair, responses=_RESPONSES)
async def login(
    payload: LoginRequest,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    service = UserService(session, settings=settings)
    user = await service.authenticate(payload.email, payload.password)
    tokens = service.issue_tokens(user)
    _set_auth_cookies(response, tokens, settings)
    return tokens


@router.post("/refresh", response_model=TokenPair, responses=_RESPONSES)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
) -> TokenPair:
    # Accept the refresh token from the JSON body or the HttpOnly cookie.
    token = payload.refresh_token or request.cookies.get("refresh_token") or ""
    service = UserService(session, settings=settings)
    tokens = await service.refresh(token)
    _set_auth_cookies(response, tokens, settings)
    return tokens


@router.get("/me", response_model=CurrentUser)
async def me(principal: PrincipalDep) -> CurrentUser:
    return CurrentUser(
        id=principal.user_id,
        email=principal.email or "",
        roles=principal.roles,
        permissions=sorted(principal.permissions),
    )
