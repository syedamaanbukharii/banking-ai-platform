"""FastAPI dependencies.

Authentication resolves a :class:`Principal` from either an ``Authorization:
Bearer`` header or an HttpOnly ``access_token`` cookie (browser clients).
Authorization is enforced via :func:`require_permissions`, which checks the
permission set resolved from the caller's roles — endpoints depend on
permissions, not roles.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from banking_ai.api.state import AppState
from banking_ai.core.config import Settings, get_settings
from banking_ai.core.errors import AuthenticationError
from banking_ai.core.security import Principal, decode_token
from banking_ai.db.session import get_sessionmaker

_BEARER_PREFIX = "Bearer "
_COOKIE_NAME = "access_token"


def settings_dep() -> Settings:
    return get_settings()


async def session_dep() -> AsyncIterator[AsyncSession]:
    """Transactional session (commit on success, rollback on error)."""
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def app_state_dep(request: Request) -> AppState:
    state = getattr(request.app.state, "app_state", None)
    if state is None:  # pragma: no cover - app always sets this in lifespan
        raise RuntimeError("Application state is not initialised.")
    return state


def _extract_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if header.startswith(_BEARER_PREFIX):
        return header[len(_BEARER_PREFIX) :].strip()
    cookie = request.cookies.get(_COOKIE_NAME)
    if cookie:
        return cookie
    raise AuthenticationError("Missing bearer token or session cookie.")


def current_principal_dep(
    request: Request,
    settings: Annotated[Settings, Depends(settings_dep)],
) -> Principal:
    """Resolve the authenticated caller from a JWT (header or cookie)."""
    token = _extract_token(request)
    claims = decode_token(token, expected_type="access", settings=settings)
    principal = Principal.from_claims(claims)
    # Make the principal available to logging/audit downstream.
    request.state.principal = principal
    return principal


def require_permissions(*permissions: str) -> Callable[..., Principal]:
    """Dependency factory enforcing that the caller holds all given permissions."""

    def _dep(
        principal: Annotated[Principal, Depends(current_principal_dep)],
    ) -> Principal:
        principal.require(*permissions)
        return principal

    return _dep


SessionDep = Annotated[AsyncSession, Depends(session_dep)]
SettingsDep = Annotated[Settings, Depends(settings_dep)]
StateDep = Annotated[AppState, Depends(app_state_dep)]
PrincipalDep = Annotated[Principal, Depends(current_principal_dep)]
