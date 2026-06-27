"""Audit agent.

Assembles a deterministic, tamper-evident evidence bundle for a workflow: it
canonicalises the supplied evidence (sorted keys), computes a SHA-256 digest
over it, and returns both. The digest lets reviewers detect later tampering. The
agent does not write to the database itself — the audit *service* persists the
append-only ``audit_logs`` record.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent


class AuditInput(BaseModel):
    workflow_id: str
    evidence: dict[str, object] = Field(default_factory=dict)


class AuditBundle(BaseModel):
    workflow_id: str
    canonical_json: str
    sha256: str
    item_count: int


class AuditAgent(BaseAgent[AuditInput, AuditBundle]):
    name = "audit_agent"

    async def run(self, payload: AuditInput) -> AuditBundle:
        canonical = json.dumps(payload.evidence, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return AuditBundle(
            workflow_id=payload.workflow_id,
            canonical_json=canonical,
            sha256=digest,
            item_count=len(payload.evidence),
        )
