"""Shared enumerations used by ORM models and schemas.

Stored as strings in the database for cross-dialect portability and forward
compatibility (adding a value never requires a DB enum migration).
"""

from __future__ import annotations

from enum import StrEnum


class WorkflowType(StrEnum):
    DOCUMENT_INTELLIGENCE = "document_intelligence"
    KYC = "kyc"
    FRAUD_REVIEW = "fraud_review"
    COMPLIANCE = "compliance"
    AUDIT_EVIDENCE = "audit_evidence"
    LOAN = "loan"


class WorkflowStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskState(StrEnum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


class ApprovalKind(StrEnum):
    APPROVAL = "approval"
    REJECTION = "rejection"
    ESCALATION = "escalation"
    MANUAL_REVIEW = "manual_review"


class ApprovalDecision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class AgentRunStatus(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class DocumentStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentSeverity(StrEnum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"


class IncidentStatus(StrEnum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
