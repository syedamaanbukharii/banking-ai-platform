"""Identity & access models: users, roles, permissions, associations."""

from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, String, Table, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from banking_ai.db.base import Base, TimestampMixin, UUIDMixin

# Association tables (many-to-many). Kept as Core tables per normalization rules.
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        Uuid(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255))
    hashed_password: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # External identity subject when authenticating via OIDC (Keycloak).
    external_subject: Mapped[str | None] = mapped_column(String(255), index=True)

    roles: Mapped[list[Role]] = relationship(
        secondary=user_roles, back_populates="users", lazy="selectin"
    )

    def role_names(self) -> list[str]:
        return [r.name for r in self.roles]


class Role(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, back_populates="roles", lazy="selectin"
    )


class Permission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("code", name="uq_permission_code"),)

    code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions, back_populates="permissions"
    )


__all__ = ["Permission", "Role", "User", "role_permissions", "user_roles"]
