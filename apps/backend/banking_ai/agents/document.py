"""Document agent.

Deterministic document understanding: it parses ``Label: value`` style fields
out of extracted text, checks them against an expected field set for the
document kind, flags missing/empty fields, and produces human-readable review
notes. None of this requires an LLM, so it is fully unit-testable; an optional
narrative summary can be produced by the summarization agent on top.
"""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.schemas.document import DocumentReview, ExtractedField

# Expected fields per document kind (extensible). Kept here so the contract is
# explicit and versionable rather than buried in prompt text.
EXPECTED_FIELDS: dict[str, list[str]] = {
    "identity": ["full_name", "date_of_birth", "document_number", "expiry_date"],
    "proof_of_address": ["full_name", "address", "issue_date"],
    "bank_statement": ["account_number", "statement_period", "closing_balance"],
    "generic": [],
}

_FIELD_LINE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 _/-]{1,48}?)\s*[:=]\s*(.+?)\s*$")


def _normalise_key(raw: str) -> str:
    return re.sub(r"[\s/-]+", "_", raw.strip().lower())


def parse_fields(text: str) -> dict[str, str]:
    """Extract ``label: value`` pairs from document text (last value wins)."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        match = _FIELD_LINE.match(line)
        if match:
            key = _normalise_key(match.group(1))
            value = match.group(2).strip()
            if value:
                fields[key] = value
    return fields


class DocumentAgentInput(BaseModel):
    document_id: uuid.UUID
    kind: str = "generic"
    text: str
    extra_expected_fields: list[str] = Field(default_factory=list)


class DocumentAgent(BaseAgent[DocumentAgentInput, DocumentReview]):
    name = "document_agent"

    async def run(self, payload: DocumentAgentInput) -> DocumentReview:
        parsed = parse_fields(payload.text)
        expected = list(
            dict.fromkeys(EXPECTED_FIELDS.get(payload.kind, []) + payload.extra_expected_fields)
        )

        extracted = [
            ExtractedField(name=name, value=parsed.get(name), present=name in parsed)
            for name in expected
        ]
        # Also surface any fields found that were not expected.
        for name, value in parsed.items():
            if name not in expected:
                extracted.append(ExtractedField(name=name, value=value, present=True))

        missing = [name for name in expected if name not in parsed]

        notes: list[str] = []
        if not parsed:
            notes.append("No structured fields could be parsed from the document text.")
        if missing:
            notes.append(f"Missing expected field(s): {', '.join(missing)}.")
        if payload.kind == "generic" and not expected:
            notes.append("No expected-field schema for 'generic'; extracted values only.")

        word_count = len(payload.text.split())
        summary = (
            f"Document {payload.document_id} ({payload.kind}): parsed {len(parsed)} field(s) "
            f"from ~{word_count} words; {len(missing)} expected field(s) missing."
        )

        requires_review = bool(missing) or not parsed
        return DocumentReview(
            document_id=payload.document_id,
            summary=summary,
            extracted_fields=extracted,
            missing_fields=missing,
            review_notes=notes,
            requires_human_review=requires_review,
        )
