"""ORM models package.

Importing this package registers every table on ``Base.metadata`` so Alembic
autogeneration and ``create_all`` (tests) see the full schema.
"""

from banking_ai.db.base import Base
from banking_ai.db.models.document import Document, DocumentChunk, EmbeddingMetadata
from banking_ai.db.models.iam import (
    Permission,
    Role,
    User,
    role_permissions,
    user_roles,
)
from banking_ai.db.models.observability import (
    AuditLog,
    CostTracking,
    Feedback,
    Incident,
    ModelCall,
)
from banking_ai.db.models.workflow import (
    AgentRun,
    Application,
    Approval,
    TaskStatus,
    Workflow,
)

__all__ = [
    "AgentRun",
    "Application",
    "Approval",
    "AuditLog",
    "Base",
    "CostTracking",
    "Document",
    "DocumentChunk",
    "EmbeddingMetadata",
    "Feedback",
    "Incident",
    "ModelCall",
    "Permission",
    "Role",
    "TaskStatus",
    "User",
    "Workflow",
    "role_permissions",
    "user_roles",
]
