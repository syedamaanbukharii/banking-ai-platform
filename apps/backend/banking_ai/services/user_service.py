"""User & authentication service.

Encapsulates credential verification and token issuance for the local auth mode.
In OIDC mode the API validates tokens against the IdP (Keycloak) and provisions
users from verified claims; that verification path is a documented seam in
``core/security`` and ``docs/auth.md``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from banking_ai.core.config import Settings, get_settings
from banking_ai.core.errors import AuthenticationError
from banking_ai.core.logging import get_logger
from banking_ai.core.security import create_token, decode_token, verify_password
from banking_ai.db.models.iam import User
from banking_ai.schemas.auth import TokenPair

logger = get_logger(__name__)


class UserService:
    def __init__(self, session: AsyncSession, *, settings: Settings | None = None) -> None:
        self._session = session
        self._settings = settings or get_settings()

    async def get_by_email(self, email: str) -> User | None:
        return (
            await self._session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    async def authenticate(self, email: str, password: str) -> User:
        user = await self.get_by_email(email)
        # Verify even when the user is missing to reduce timing side channels.
        hashed = user.hashed_password if user and user.hashed_password else None
        ok = verify_password(password, hashed) if hashed else _dummy_verify(password)
        if not user or not user.is_active or not ok:
            logger.warning("auth.failed", email=email)
            raise AuthenticationError("Invalid email or password.")
        logger.info("auth.success", user_id=str(user.id))
        return user

    def issue_tokens(self, user: User) -> TokenPair:
        roles = user.role_names()
        access, _ = create_token(
            subject=str(user.id),
            roles=roles,
            token_type="access",  # nosec B106
            settings=self._settings,
            extra_claims={"email": user.email},
        )
        refresh, _ = create_token(
            subject=str(user.id),
            roles=roles,
            token_type="refresh",  # nosec B106
            settings=self._settings,
            extra_claims={"email": user.email},
        )
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.security_access_token_ttl_seconds,
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        claims = decode_token(refresh_token, expected_type="refresh", settings=self._settings)
        user = (
            await self._session.execute(select(User).where(User.id == _as_uuid(claims["sub"])))
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            raise AuthenticationError("Refresh subject is no longer valid.")
        # New pair each refresh (rotation); stateless tokens expire naturally.
        return self.issue_tokens(user)


def _dummy_verify(password: str) -> bool:
    # Constant-ish work to avoid leaking user existence via timing.
    from banking_ai.core.security import hash_password, verify_password

    return verify_password(password, hash_password("not-a-real-password"))


def _as_uuid(value: str) -> object:
    import uuid

    try:
        return uuid.UUID(str(value))
    except ValueError as exc:  # pragma: no cover - malformed token subject
        raise AuthenticationError("Malformed token subject.") from exc
