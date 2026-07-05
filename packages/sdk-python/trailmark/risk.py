"""Client-side risk scoring heuristics.

Simple, deterministic, and fully configurable — the score travels with the
event and drives the supervisory-review requirement (FINRA 3110). Firms tune
thresholds and weights to their own written supervisory procedures; explicit
per-trace overrides always win over heuristics.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel


class RiskAssessment(BaseModel):
    risk_score: float
    risk_tier: str
    risk_flags: list[str]
    requires_supervisor_review: bool


@dataclass
class RiskConfig:
    # Tier boundaries (score is clamped to [0, 0.99])
    medium_threshold: float = 0.4
    high_threshold: float = 0.75
    critical_threshold: float = 0.9
    # Score at or above this requires supervisory attestation
    review_threshold: float = 0.75

    # Base score by action_type; unknown types get `default_base`
    base_scores: dict[str, float] = field(
        default_factory=lambda: {
            "tool_call": 0.15,
            "decision": 0.35,
            "communication": 0.25,
        }
    )
    default_base: float = 0.15

    # Substring of action_name → (score bump, risk flag)
    keyword_weights: dict[str, tuple[float, str]] = field(
        default_factory=lambda: {
            "wire": (0.35, "wire_transfer"),
            "transfer": (0.20, "funds_movement"),
            "liquidat": (0.40, "liquidation"),
            "margin": (0.30, "margin_risk"),
            "option": (0.30, "complex_product"),
            "derivative": (0.30, "complex_product"),
            "recommend": (0.15, "recommendation"),
            "close_account": (0.30, "account_closure"),
        }
    )

    # Keys searched (recursively) in the input payload for a monetary amount
    amount_keys: tuple[str, ...] = ("amount", "notional", "value_usd", "usd_value")
    # Descending (threshold, bump, flag) — first match wins
    amount_thresholds: tuple[tuple[float, float, str], ...] = (
        (1_000_000, 0.40, "notional_over_1m"),
        (100_000, 0.25, "notional_over_100k"),
        (10_000, 0.10, "notional_over_10k"),
    )


def _find_amount(payload: Any, keys: tuple[str, ...], depth: int = 0) -> float | None:
    if depth > 4 or not isinstance(payload, dict):
        return None
    best: float | None = None
    for key, value in payload.items():
        if key in keys and isinstance(value, (int, float)) and not isinstance(value, bool):
            best = max(best or 0.0, float(value))
        elif isinstance(value, dict):
            nested = _find_amount(value, keys, depth + 1)
            if nested is not None:
                best = max(best or 0.0, nested)
    return best


def tier_for(score: float, config: RiskConfig) -> str:
    if score >= config.critical_threshold:
        return "CRITICAL"
    if score >= config.high_threshold:
        return "HIGH"
    if score >= config.medium_threshold:
        return "MEDIUM"
    return "LOW"


def assess(
    action_type: str,
    action_name: str,
    input_payload: Any,
    config: RiskConfig,
) -> RiskAssessment:
    score = config.base_scores.get(action_type, config.default_base)
    flags: list[str] = []

    lowered = action_name.lower()
    for keyword, (bump, flag) in config.keyword_weights.items():
        if keyword in lowered:
            score += bump
            if flag not in flags:
                flags.append(flag)

    amount = _find_amount(input_payload, config.amount_keys)
    if amount is not None:
        for threshold, bump, flag in config.amount_thresholds:
            if amount >= threshold:
                score += bump
                flags.append(flag)
                break

    score = round(min(0.99, max(0.0, score)), 3)
    return RiskAssessment(
        risk_score=score,
        risk_tier=tier_for(score, config),
        risk_flags=flags,
        requires_supervisor_review=score >= config.review_threshold,
    )
