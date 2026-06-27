# Authentication & Authorization

## Modes

`SECURITY_AUTH_MODE` selects how callers are authenticated:

- **`local`** (default): the API issues and validates its own HS256 JWTs. Users live in
  the `users` table with `pbkdf2_sha256` password hashes. `login` returns an access +
  refresh token pair and sets HttpOnly cookies; `refresh` rotates the pair. This mode
  needs no external identity provider and is what the tests and quickstart use.
- **`oidc`**: tokens are issued by an external IdP (Keycloak in the compose stack). The
  API verifies them against the IdP's JWKS and provisions/links users from verified
  claims. Token verification for OIDC is a documented seam in `core/security.py`
  (`OIDC_ISSUER`, `OIDC_JWKS_URL`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`); the local
  HS256 path is fully implemented so the platform is runnable without an IdP.

The app refuses to boot in non-local environments if the JWT secret is missing,
placeholder, or shorter than 32 characters, and requires `OIDC_CLIENT_SECRET` when
`SECURITY_AUTH_MODE=oidc`.

## Tokens

Access and refresh tokens carry `sub`, `roles`, `type`, `iat`, `nbf`, `exp`, `jti`, and
`iss`. `decode_token` enforces `exp`/`iat`/`sub` and the expected token `type`.
The `Principal` resolves `roles → permissions` at request time; unknown role strings
are ignored (defence-in-depth against tampered tokens).

## Roles

Roles mirror the target users: `customer_support_agent`, `banking_operations_executive`,
`compliance_officer`, `risk_analyst`, `loan_officer`, `auditor`, `manager`,
`system_admin`. The Keycloak realm export defines the same roles and maps them into a
`roles` claim.

## Permission matrix

The API checks permissions, not roles. `system_admin` holds all permissions.

| Permission | support | ops_exec | compliance | risk | loan | auditor | manager |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| `document:read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `document:upload` | ✓ | ✓ |   |   | ✓ |   | ✓ |
| `workflow:read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `workflow:start` | ✓ | ✓ |   |   | ✓ |   | ✓ |
| `workflow:approve` |   |   | ✓ | ✓ |   |   | ✓ |
| `workflow:reject` |   |   | ✓ | ✓ |   |   | ✓ |
| `workflow:escalate` |   |   | ✓ |   |   |   | ✓ |
| `kyc:review` |   |   |   |   |   |   | (admin) |
| `fraud:review` |   |   |   | ✓ |   |   | (admin) |
| `compliance:read` | (read-only set) | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `loan:process` |   |   |   |   | ✓ |   | (admin) |
| `audit:read` |   |   | ✓ |   |   | ✓ | ✓ |
| `agent:read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `agent:run` | ✓ | ✓ | ✓ | ✓ | ✓ |   | ✓ |
| `search:read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `admin:read` |   |   |   |   |   |   | (admin) |
| `admin:manage` |   |   |   |   |   |   | (admin) |

`kyc:review`, `loan:process`, `admin:*` are held by `system_admin`; assign them to the
appropriate domain roles in your IdP/role design as needed. The source of truth is
`core/rbac.py` (`ROLE_PERMISSIONS`).

## Seeding

In local environments the app seeds the permission/role catalogue and a dev admin
(`SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD`) on startup. Seeding is idempotent. In
non-local environments, provision users via the IdP.
