"""Loan agent.

Deterministic affordability assessment: computes debt-to-income (DTI) and a
simple disposable-income check, then produces a transparent recommendation. The
final lending decision is reserved for a human with ``loan:process`` (the
orchestrator marks LOAN workflows as approval-gated); this agent only advises.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from banking_ai.agents.base import BaseAgent
from banking_ai.db.models.enums import RiskLevel


class LoanInput(BaseModel):
    monthly_income: float = Field(gt=0)
    monthly_debt: float = Field(default=0.0, ge=0)
    monthly_expenses: float = Field(default=0.0, ge=0)
    loan_amount: float = Field(gt=0)
    term_months: int = Field(gt=0, le=480)
    annual_interest_rate: float = Field(default=0.0, ge=0, le=1)


class LoanResult(BaseModel):
    estimated_monthly_payment: float
    dti_ratio: float
    disposable_after_payment: float
    risk_level: RiskLevel
    recommendation: str
    requires_human_review: bool
    rationale: list[str]


# Documented policy thresholds.
DTI_WARN = 0.36
DTI_MAX = 0.43


class LoanAgent(BaseAgent[LoanInput, LoanResult]):
    name = "loan_agent"

    async def run(self, payload: LoanInput) -> LoanResult:
        payment = _monthly_payment(
            principal=payload.loan_amount,
            annual_rate=payload.annual_interest_rate,
            term_months=payload.term_months,
        )
        total_debt = payload.monthly_debt + payment
        dti = total_debt / payload.monthly_income
        disposable = payload.monthly_income - payload.monthly_expenses - total_debt

        rationale = [
            f"Estimated monthly payment: {payment:.2f}.",
            f"DTI ratio: {dti:.2%} (warn ≥ {DTI_WARN:.0%}, max ≥ {DTI_MAX:.0%}).",
            f"Disposable income after payment: {disposable:.2f}.",
        ]

        if dti >= DTI_MAX or disposable < 0:
            risk = RiskLevel.HIGH
            recommendation = "Decline or restructure: affordability thresholds exceeded."
        elif dti >= DTI_WARN:
            risk = RiskLevel.MEDIUM
            recommendation = "Refer for manual underwriting: elevated DTI."
        else:
            risk = RiskLevel.LOW
            recommendation = "Within affordability policy: recommend approval subject to sign-off."

        return LoanResult(
            estimated_monthly_payment=round(payment, 2),
            dti_ratio=round(dti, 4),
            disposable_after_payment=round(disposable, 2),
            risk_level=risk,
            recommendation=recommendation,
            requires_human_review=True,  # lending decisions always need sign-off
            rationale=rationale,
        )


def _monthly_payment(*, principal: float, annual_rate: float, term_months: int) -> float:
    if annual_rate == 0:
        return principal / term_months
    r = annual_rate / 12.0
    factor = (1 + r) ** term_months
    return principal * (r * factor) / (factor - 1)
