from __future__ import annotations

import pytest

from app.paper_trading_routes import _resolve_gui_rust_single_order_cap_usd


def test_paper_authorization_cap_uses_gui_rust_percent_semantics() -> None:
    cap, lineage = _resolve_gui_rust_single_order_cap_usd(
        risk_config={
            "config": {
                "limits": {
                    "per_trade_risk_pct": 0.1,
                    "position_size_max_pct": 25.0,
                    "max_order_notional_usdt": 0.0,
                }
            }
        },
        paper_state={"balance": 9551.36942603},
    )

    assert cap == pytest.approx(955.136942603)
    assert lineage["per_trade_budget_usdt"] == pytest.approx(955.136942603)
    assert lineage["single_position_budget_usdt"] == pytest.approx(2387.8423565075)
    assert lineage["max_order_notional_usdt"] == 0.0
    assert lineage["local_10_usdt_cap_is_authority"] is False
    assert lineage["failure_reasons"] == []


def test_paper_authorization_cap_fail_closes_on_missing_equity() -> None:
    cap, lineage = _resolve_gui_rust_single_order_cap_usd(
        risk_config={
            "config": {
                "limits": {
                    "per_trade_risk_pct": 0.1,
                    "position_size_max_pct": 25.0,
                }
            }
        },
        paper_state={},
    )

    assert cap is None
    assert "equity_missing_or_non_positive" in lineage["failure_reasons"]


def test_paper_authorization_cap_rejects_gui_percent_stored_as_rust_fraction() -> None:
    cap, lineage = _resolve_gui_rust_single_order_cap_usd(
        risk_config={
            "config": {
                "limits": {
                    "per_trade_risk_pct": 10.0,
                    "position_size_max_pct": 25.0,
                }
            }
        },
        paper_state={"balance": 9551.36942603},
    )

    assert cap is None
    assert "per_trade_risk_pct_not_rust_fraction" in lineage["failure_reasons"]
