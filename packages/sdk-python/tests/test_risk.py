from trailmark.risk import RiskConfig, assess


def test_low_risk_tool_call():
    r = assess("tool_call", "generate_client_email", {}, RiskConfig())
    assert r.risk_tier == "LOW"
    assert r.requires_supervisor_review is False
    assert r.risk_flags == []


def test_wire_transfer_with_large_amount_is_high_risk():
    r = assess("tool_call", "wire_transfer_execute", {"amount": 250_000}, RiskConfig())
    assert r.risk_score >= 0.75
    assert r.requires_supervisor_review is True
    assert "wire_transfer" in r.risk_flags
    assert "notional_over_100k" in r.risk_flags


def test_amount_found_in_nested_payload():
    r = assess("decision", "margin_extension", {"request": {"notional": 2_000_000}}, RiskConfig())
    assert "notional_over_1m" in r.risk_flags
    assert r.risk_tier in ("HIGH", "CRITICAL")


def test_liquidation_decision_is_critical():
    r = assess("decision", "account_liquidation_full", {"amount": 1_500_000}, RiskConfig())
    assert r.risk_tier == "CRITICAL"
    assert "liquidation" in r.risk_flags


def test_score_is_clamped():
    r = assess(
        "decision",
        "wire_transfer_liquidation_margin_options_recommendation",
        {"amount": 9_999_999},
        RiskConfig(),
    )
    assert r.risk_score <= 0.99


def test_thresholds_are_configurable():
    strict = RiskConfig(review_threshold=0.1, medium_threshold=0.05,
                        high_threshold=0.2, critical_threshold=0.5)
    r = assess("tool_call", "generate_client_email", {}, strict)
    assert r.requires_supervisor_review is True
    assert r.risk_tier == "MEDIUM"


def test_custom_keywords():
    config = RiskConfig(keyword_weights={"crypto": (0.6, "digital_asset")})
    r = assess("tool_call", "crypto_purchase", {}, config)
    assert "digital_asset" in r.risk_flags
    assert r.risk_score >= 0.7
