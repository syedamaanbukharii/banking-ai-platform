"""Fraud agent.

Transparent, rule-based transaction-risk scoring (spec: fraud detection with
human-reviewed high-risk decisions). Each rule contributes a documented weight
and a human-readable reason; the final score is the sum, clamped to [0, 100].
The decision to block or escalate is never taken autonomously for high-risk
cases — those are flagged for human review. Explainability is a first-class
output, not an afterthought.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.db.models.enums import RiskLevel


class Transaction(BaseModel):
    amount: float = Field(ge=0)
    currency: str = "USD"
    country: str | None = None
    account_age_days: int = Field(default=3650, ge=0)
    is_new_beneficiary: bool = False
    beneficiary_country: str | None = None
    channel: str = "web"  # web | mobile | wire | atm
    hour_of_day: int = Field(default=12, ge=0, le=23)
    recent_failed_logins: int = Field(default=0, ge=0)


class FraudInput(BaseModel):
    transaction: Transaction
    customer_avg_amount: float = Field(default=0.0, ge=0)


class FraudSignal(BaseModel):
    rule: str
    weight: int
    reason: str


class FraudResult(BaseModel):
    score: int
    risk_level: RiskLevel
    signals: list[FraudSignal]
    requires_human_review: bool
    recommendation: str


# Documented thresholds (transparent and tunable).
HIGH_RISK_COUNTRIES = {"XX", "ZZ"}
LARGE_AMOUNT_ABS = 10_000.0
ANOMALY_MULTIPLIER = 5.0


class FraudAgent(BaseAgent[FraudInput, FraudResult]):
    name = "fraud_agent"

    async def run(self, payload: FraudInput) -> FraudResult:
        txn = payload.transaction
        signals: list[FraudSignal] = []

        if txn.amount >= LARGE_AMOUNT_ABS:
            signals.append(
                FraudSignal(
                    rule="large_absolute_amount",
                    weight=30,
                    reason=(
                        f"Amount {txn.amount:.2f} {txn.currency} "
                        f"exceeds {LARGE_AMOUNT_ABS:.0f}."
                    ),
                )
            )

        if (
            payload.customer_avg_amount > 0
            and txn.amount > ANOMALY_MULTIPLIER * payload.customer_avg_amount
        ):
            signals.append(
                FraudSignal(
                    rule="amount_anomaly",
                    weight=25,
                    reason=(
                        f"Amount is >{ANOMALY_MULTIPLIER:.0f}x the customer average "
                        f"({payload.customer_avg_amount:.2f})."
                    ),
                )
            )

        if txn.account_age_days < 30:
            signals.append(
                FraudSignal(
                    rule="new_account",
                    weight=15,
                    reason=f"Account is only {txn.account_age_days} day(s) old.",
                )
            )

        if txn.is_new_beneficiary and txn.amount >= 1_000:
            signals.append(
                FraudSignal(
                    rule="new_beneficiary_large",
                    weight=15,
                    reason="Large transfer to a newly added beneficiary.",
                )
            )

        bc = (txn.beneficiary_country or "").upper()
        if bc in HIGH_RISK_COUNTRIES:
            signals.append(
                FraudSignal(
                    rule="high_risk_destination",
                    weight=20,
                    reason=f"Beneficiary country {bc} is on the higher-risk list.",
                )
            )

        if txn.recent_failed_logins >= 3:
            signals.append(
                FraudSignal(
                    rule="failed_login_burst",
                    weight=20,
                    reason=f"{txn.recent_failed_logins} recent failed logins before transaction.",
                )
            )

        if txn.hour_of_day in range(1, 5) and txn.amount >= 1_000:
            signals.append(
                FraudSignal(
                    rule="odd_hour_large",
                    weight=10,
                    reason=("Large transaction during unusual hours " "(01:00-04:59)."),
                )
            )

        score = min(100, sum(s.weight for s in signals))
        risk = _score_to_risk(score)
        requires_review = risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)
        recommendation = _recommendation(risk)

        return FraudResult(
            score=score,
            risk_level=risk,
            signals=signals,
            requires_human_review=requires_review,
            recommendation=recommendation,
        )


def _score_to_risk(score: int) -> RiskLevel:
    if score >= 70:
        return RiskLevel.CRITICAL
    if score >= 45:
        return RiskLevel.HIGH
    if score >= 20:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _recommendation(risk: RiskLevel) -> str:
    return {
        RiskLevel.LOW: "Auto-approve; no action required.",
        RiskLevel.MEDIUM: "Allow with monitoring; no human review required.",
        RiskLevel.HIGH: "Hold and route to a human reviewer before settlement.",
        RiskLevel.CRITICAL: "Block pending mandatory human investigation.",
    }[risk]
