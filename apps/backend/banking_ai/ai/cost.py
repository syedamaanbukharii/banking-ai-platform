"""Very small token-cost estimator.

Prices are indicative USD per 1K tokens and intentionally conservative; they
drive the ``cost_tracking`` table and budget dashboards, not billing. Update as
provider pricing changes (kept in one place on purpose).
"""

from __future__ import annotations

# (provider, model_prefix) -> (input_per_1k, output_per_1k)
_PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("groq", "llama-3.1-8b"): (0.00005, 0.00008),
    ("groq", "llama-3.1-70b"): (0.00059, 0.00079),
    ("groq", "mixtral"): (0.00024, 0.00024),
    ("local_gemma", ""): (0.0, 0.0),  # self-hosted: no marginal token cost
    ("echo", ""): (0.0, 0.0),
}

_DEFAULT = (0.0005, 0.0015)


def _lookup(provider: str, model: str) -> tuple[float, float]:
    best: tuple[float, float] | None = None
    best_len = -1
    for (prov, prefix), price in _PRICES.items():
        if prov == provider and model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = price, len(prefix)
    return best or _DEFAULT


def estimate_cost_usd(
    *, provider: str, model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    in_price, out_price = _lookup(provider, model)
    cost = (prompt_tokens / 1000.0) * in_price + (completion_tokens / 1000.0) * out_price
    return round(cost, 6)
