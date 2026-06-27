"""Role-based access control (RBAC) model.

Roles mirror the target users in the specification (section 3). Permissions are
fine-grained verbs on resources; roles are bundles of permissions. The API layer
checks permissions (not roles) so authorization stays decoupled from org
structure and can later evolve toward ABAC without touching endpoints.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    CUSTOMER_SUPPORT = "customer_support_agent"
    OPS_EXECUTIVE = "banking_operations_executive"
    COMPLIANCE_OFFICER = "compliance_officer"
    RISK_ANALYST = "risk_analyst"
    LOAN_OFFICER = "loan_officer"
    AUDITOR = "auditor"
    MANAGER = "manager"
    SYSTEM_ADMIN = "system_admin"


class Permission(StrEnum):
    # Documents
    DOCUMENT_READ = "document:read"
    DOCUMENT_UPLOAD = "document:upload"
    # Workflows
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_START = "workflow:start"
    WORKFLOW_APPROVE = "workflow:approve"
    WORKFLOW_REJECT = "workflow:reject"
    WORKFLOW_ESCALATE = "workflow:escalate"
    # Domain reviews
    KYC_REVIEW = "kyc:review"
    FRAUD_REVIEW = "fraud:review"
    COMPLIANCE_READ = "compliance:read"
    LOAN_PROCESS = "loan:process"
    # Audit
    AUDIT_READ = "audit:read"
    # Agents / search
    AGENT_READ = "agent:read"
    AGENT_RUN = "agent:run"
    SEARCH_READ = "search:read"
    # Admin
    ADMIN_READ = "admin:read"
    ADMIN_MANAGE = "admin:manage"


_READ_ONLY: set[Permission] = {
    Permission.DOCUMENT_READ,
    Permission.WORKFLOW_READ,
    Permission.AGENT_READ,
    Permission.SEARCH_READ,
    Permission.COMPLIANCE_READ,
}

ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.SYSTEM_ADMIN: set(Permission),  # all permissions
    Role.MANAGER: _READ_ONLY
    | {
        Permission.DOCUMENT_UPLOAD,
        Permission.WORKFLOW_START,
        Permission.WORKFLOW_APPROVE,
        Permission.WORKFLOW_REJECT,
        Permission.WORKFLOW_ESCALATE,
        Permission.AGENT_RUN,
        Permission.AUDIT_READ,
    },
    Role.OPS_EXECUTIVE: _READ_ONLY
    | {
        Permission.DOCUMENT_UPLOAD,
        Permission.WORKFLOW_START,
        Permission.AGENT_RUN,
    },
    Role.CUSTOMER_SUPPORT: {
        Permission.DOCUMENT_READ,
        Permission.DOCUMENT_UPLOAD,
        Permission.WORKFLOW_READ,
        Permission.WORKFLOW_START,
        Permission.SEARCH_READ,
        Permission.AGENT_RUN,
    },
    Role.COMPLIANCE_OFFICER: _READ_ONLY
    | {
        Permission.COMPLIANCE_READ,
        Permission.WORKFLOW_APPROVE,
        Permission.WORKFLOW_REJECT,
        Permission.WORKFLOW_ESCALATE,
        Permission.AUDIT_READ,
        Permission.AGENT_RUN,
    },
    Role.RISK_ANALYST: _READ_ONLY
    | {
        Permission.FRAUD_REVIEW,
        Permission.WORKFLOW_APPROVE,
        Permission.WORKFLOW_REJECT,
        Permission.AGENT_RUN,
    },
    Role.LOAN_OFFICER: _READ_ONLY
    | {
        Permission.DOCUMENT_UPLOAD,
        Permission.LOAN_PROCESS,
        Permission.WORKFLOW_START,
        Permission.AGENT_RUN,
    },
    Role.AUDITOR: _READ_ONLY | {Permission.AUDIT_READ},
}


def permissions_for_roles(roles: list[str] | set[str]) -> set[str]:
    """Resolve a set of role names to the union of their permission strings.

    Unknown role strings are ignored (defence-in-depth against tampered tokens).
    """
    resolved: set[str] = set()
    for raw in roles:
        try:
            role = Role(raw)
        except ValueError:
            continue
        resolved.update(p.value for p in ROLE_PERMISSIONS.get(role, set()))
    return resolved
