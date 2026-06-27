"""Security primitives: password hashing, JWT issue/verify, and auth dependencies.

Token model
-----------
* Access token  - short-lived, carries ``roles`` claim, sent as Bearer or in an
  HttpOnly cookie for browser sessions.
* Refresh token - long-lived, ``type=refresh``, carries a ``jti`` so it can be
  rotated/revoked. Rotation is enforced in the auth service.

Auth modes
----------
* ``local`` (default): the platform signs/verifies its own HS256 tokens, so the
  system is fully runnable without an external IdP.
* ``oidc``: tokens are verified against a Keycloak/OIDC issuer's JWKS. The
  verification seam is defined here; wiring the live JWKS client is an
  environment concern documented in docs/auth.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from passlib.context import CryptContext

from banking_ai.core.config import Settings, get_settings
from banking_ai.core.errors import AuthenticationError, AuthorizationError
from banking_ai.core.rbac import permissions_for_roles

# pbkdf2_sha256 is pure-Python, dependency-light and FIPS-friendly. Production
# deployments may switch to argon2 by adding it to the schemes list.
_pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

TokenType = Literal["access", "refresh"]


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _pwd_context.verify(plain, hashed)
    except ValueError:
        # Malformed hash -> treat as non-match rather than raising.
        return False


def _now() -> datetime:
    return datetime.now(tz=UTC)


def create_token(
    *,
    subject: str,
    roles: list[str],
    token_type: TokenType,
    settings: Settings | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Create a signed JWT. Returns ``(token, jti)``."""
    settings = settings or get_settings()
    ttl = (
        settings.security_access_token_ttl_seconds
        # ("access"/"refresh" below are token *type* labels, not secrets.)
        if token_type == "access"  # nosec B105
        else settings.security_refresh_token_ttl_seconds
    )
    issued = _now()
    jti = uuid.uuid4().hex
    payload: dict[str, Any] = {
        "sub": subject,
        "roles": roles,
        "type": token_type,
        "iat": int(issued.timestamp()),
        "nbf": int(issued.timestamp()),
        "exp": int((issued + timedelta(seconds=ttl)).timestamp()),
        "jti": jti,
        "iss": settings.app_name,
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(
        payload, settings.security_jwt_secret, algorithm=settings.security_jwt_algorithm
    )
    return token, jti


def decode_token(
    token: str,
    *,
    expected_type: TokenType | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Decode and validate a JWT. Raises :class:`AuthenticationError` on failure."""
    settings = settings or get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.security_jwt_secret,
            algorithms=[settings.security_jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc

    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError(f"Expected a {expected_type} token.")
    return payload


@dataclass(slots=True)
class Principal:
    """The authenticated caller, with resolved permissions."""

    user_id: str
    email: str | None
    roles: list[str]
    permissions: set[str] = field(default_factory=set)
    token_id: str | None = None

    @classmethod
    def from_claims(cls, claims: dict[str, Any]) -> Principal:
        roles = list(claims.get("roles", []))
        return cls(
            user_id=str(claims["sub"]),
            email=claims.get("email"),
            roles=roles,
            permissions=permissions_for_roles(roles),
            token_id=claims.get("jti"),
        )

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions

    def require(self, *permissions: str) -> None:
        missing = [p for p in permissions if p not in self.permissions]
        if missing:
            raise AuthorizationError(
                "Missing required permission(s).",
                details={"missing": missing},
            )
