"""KYC agent.

Deterministic Know-Your-Customer checks (spec: KYC/AML automation). The agent
validates completeness of a customer profile, runs cross-field consistency
checks (e.g. name on document vs application, age derived from DOB), assigns a
transparent risk level, and decides whether a human reviewer is required. All
logic is rule-based and explainable — no opaque model decision sits on the
approval path.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.db.models.enums import RiskLevel

REQUIRED_PROFILE_FIELDS = ("full_name", "date_of_birth", "country", "document_number")

# Illustrative higher-risk jurisdictions list (configurable in a real system via
# a sanctions/PEP data feed; kept explicit here for transparency and testing).
HIGH_RISK_COUNTRIES = {"XX", "ZZ"}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y")


def _parse_date(value: str) -> date | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _age_on(reference: date, dob: date) -> int:
    years = reference.year - dob.year
    if (reference.month, reference.day) < (dob.month, dob.day):
        years -= 1
    return years


class KycInput(BaseModel):
    profile: dict[str, str] = Field(default_factory=dict)
    document_fields: dict[str, str] = Field(default_factory=dict)
    today: date | None = None  # injectable for deterministic tests


class KycResult(BaseModel):
    complete: bool
    missing_fields: list[str]
    inconsistencies: list[str]
    risk_level: RiskLevel
    requires_human_review: bool
    rationale: list[str]


class KycAgent(BaseAgent[KycInput, KycResult]):
    name = "kyc_agent"

    async def run(self, payload: KycInput) -> KycResult:
        profile = {k.lower(): v for k, v in payload.profile.items()}
        doc = {k.lower(): v for k, v in payload.document_fields.items()}
        today = payload.today or date.today()

        missing = [f for f in REQUIRED_PROFILE_FIELDS if not profile.get(f)]
        inconsistencies: list[str] = []
        rationale: list[str] = []

        # Cross-field: name on document vs application profile.
        if (
            profile.get("full_name")
            and doc.get("full_name")
            and _norm_name(profile["full_name"]) != _norm_name(doc["full_name"])
        ):
            inconsistencies.append("Name on document does not match application profile.")

        # Cross-field: document number matches (if both present).
        if (
            profile.get("document_number")
            and doc.get("document_number")
            and profile["document_number"].strip() != doc["document_number"].strip()
        ):
            inconsistencies.append("Document number mismatch between profile and document.")

        # Age check from DOB.
        risk = RiskLevel.LOW
        dob_raw = profile.get("date_of_birth")
        if dob_raw:
            dob = _parse_date(dob_raw)
            if dob is None:
                inconsistencies.append(f"Unparseable date_of_birth: {dob_raw!r}.")
            else:
                age = _age_on(today, dob)
                rationale.append(f"Derived age: {age}.")
                if age < 18:
                    risk = RiskLevel.HIGH
                    inconsistencies.append("Applicant is under 18.")
                elif age > 120:
                    inconsistencies.append("Implausible age (>120); check date_of_birth.")

        # Jurisdiction risk.
        country = (profile.get("country") or "").upper()
        if country in HIGH_RISK_COUNTRIES:
            risk = _escalate(risk, RiskLevel.HIGH)
            rationale.append(f"Country {country} is on the higher-risk list.")

        # Any inconsistency lifts risk to at least MEDIUM.
        if inconsistencies:
            risk = _escalate(risk, RiskLevel.MEDIUM)

        complete = not missing
        if not complete:
            rationale.append(f"Profile incomplete; missing {', '.join(missing)}.")

        # HITL: required when incomplete, inconsistent, or risk >= HIGH.
        requires_review = (
            not complete or bool(inconsistencies) or risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        )
        if requires_review:
            rationale.append("Routed to human review (HITL).")
        else:
            rationale.append("Automated KYC checks passed; no human review required.")

        return KycResult(
            complete=complete,
            missing_fields=missing,
            inconsistencies=inconsistencies,
            risk_level=risk,
            requires_human_review=requires_review,
            rationale=rationale,
        )


def _norm_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


_RISK_ORDER = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


def _escalate(current: RiskLevel, floor: RiskLevel) -> RiskLevel:
    return current if _RISK_ORDER.index(current) >= _RISK_ORDER.index(floor) else floor
