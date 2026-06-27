"""Database seeding.

Creates the RBAC permission/role catalogue and a development admin user. Safe to
run repeatedly (idempotent): existing rows are reused. The admin credentials come
from ``SEED_ADMIN_EMAIL`` / ``SEED_ADMIN_PASSWORD`` and exist only to make local
runs usable; in non-local environments you would provision users via OIDC.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from banking_ai.core.config import Settings
from banking_ai.core.logging import get_logger
from banking_ai.core.rbac import ROLE_PERMISSIONS, Permission
from banking_ai.core.rbac import Role as RbacRole
from banking_ai.core.security import hash_password
from banking_ai.db.models.iam import Permission as PermissionModel
from banking_ai.db.models.iam import Role as RoleModel
from banking_ai.db.models.iam import User

logger = get_logger(__name__)


async def seed_rbac(session: AsyncSession) -> dict[str, RoleModel]:
    """Ensure all permissions and roles exist; return roles by name."""
    # Permissions.
    perms: dict[str, PermissionModel] = {}
    existing_perms = (await session.execute(select(PermissionModel))).scalars().all()
    for p in existing_perms:
        perms[p.code] = p
    for permission in Permission:
        if permission.value not in perms:
            row = PermissionModel(code=permission.value)
            session.add(row)
            perms[permission.value] = row
    await session.flush()

    # Roles + mappings (eager-load permissions so we never lazy-read in async).
    roles: dict[str, RoleModel] = {}
    existing_roles = (
        (await session.execute(select(RoleModel).options(selectinload(RoleModel.permissions))))
        .scalars()
        .all()
    )
    for r in existing_roles:
        roles[r.name] = r
    for role, permissions in ROLE_PERMISSIONS.items():
        role_row = roles.get(role.value)
        if role_row is None:
            # Set the permission collection at creation time (no read-back needed).
            role_row = RoleModel(
                name=role.value,
                permissions=[perms[p.value] for p in permissions],
            )
            session.add(role_row)
            roles[role.value] = role_row
            continue
        current = {p.code for p in role_row.permissions}
        for permission in permissions:
            if permission.value not in current:
                role_row.permissions.append(perms[permission.value])
    await session.flush()
    logger.info("seed.rbac", roles=len(roles), permissions=len(perms))
    return roles


async def seed_admin(session: AsyncSession, settings: Settings) -> User:
    """Create (or fetch) the development admin user with the system_admin role."""
    roles = await seed_rbac(session)
    existing = (
        await session.execute(select(User).where(User.email == settings.seed_admin_email))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    admin = User(
        email=settings.seed_admin_email,
        full_name="Local Admin",
        hashed_password=hash_password(settings.seed_admin_password),
        is_active=True,
    )
    admin.roles.append(roles[RbacRole.SYSTEM_ADMIN.value])
    session.add(admin)
    await session.flush()
    logger.info("seed.admin", email=admin.email)
    return admin
