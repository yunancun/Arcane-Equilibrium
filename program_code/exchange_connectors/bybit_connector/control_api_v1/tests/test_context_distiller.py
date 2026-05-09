from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.context_distiller import ContextDistillationConfig, ContextDistiller
from app.layer2_cost_tracker import Layer2CostTracker
from app.layer2_engine import Layer2Engine


def test_distiller_compacts_known_sections_and_bounds_lists() -> None:
    distiller = ContextDistiller(
        ContextDistillationConfig(max_events=2, max_positions=1, max_str_chars=40)
    )

    summary = distiller.distill_mapping(
        {
            "market": {
                "symbol": "BTCUSDT",
                "btc_price": 65000.1234567,
                "regime": "trending",
                "hurst": 0.61234567,
                "ignored": "not part of compact market",
            },
            "portfolio": {
                "balance": 1000.0,
                "positions": [
                    {"symbol": "BTCUSDT", "side": "long", "notional_usd": 120.0},
                    {"symbol": "ETHUSDT", "side": "short", "notional_usd": 80.0},
                ],
            },
            "events": [
                {"event_type": "news", "summary": "A" * 200},
                {"event_type": "risk", "reason": "drawdown"},
                {"event_type": "extra", "reason": "must be dropped"},
            ],
            "pressure": {"confidence_floor": 0.63, "qty_ceiling": 0.85},
        }
    )

    assert list(summary) == ["market", "portfolio", "events", "pressure"]
    assert summary["market"]["symbol"] == "BTCUSDT"
    assert summary["market"]["btc_price"] == 65000.123457
    assert "ignored" not in summary["market"]
    assert summary["portfolio"]["position_count"] == 2
    assert len(summary["portfolio"]["positions"]) == 1
    assert len(summary["events"]) == 2
    assert summary["events"][0]["summary"].endswith("...<truncated>")


def test_update_snapshot_is_deep_copied() -> None:
    distiller = ContextDistiller()
    cycle = {"market": {"symbol": "BTCUSDT", "regime": "range"}}

    distiller.update_after_each_cycle(cycle)
    cycle["market"]["regime"] = "mutated"

    snapshot = distiller.snapshot()
    assert snapshot["market"]["regime"] == "range"

    snapshot["market"]["regime"] = "caller_mutated"
    assert distiller.snapshot()["market"]["regime"] == "range"


def test_prompt_context_is_bounded_and_accepts_json_string() -> None:
    distiller = ContextDistiller(ContextDistillationConfig(max_events=5, max_str_chars=80))
    noisy = {
        "market": {"symbol": "BTCUSDT", "regime": "volatile"},
        "events": [{"summary": "x" * 500} for _ in range(20)],
    }

    prompt = distiller.distill_for_prompt(json.dumps(noisy), max_chars=220)

    assert len(prompt) <= 220
    assert "BTCUSDT" in prompt
    assert "volatile" in prompt
    assert "x" * 100 not in prompt


def test_layer2_engine_uses_distiller_for_triage_and_manual_context() -> None:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    try:
        tracker = Layer2CostTracker(state_file=path)
        engine = Layer2Engine(cost_tracker=tracker)

        triage_context = engine._build_triage_context(
            {
                "market": {"symbol": "BTCUSDT", "regime": "volatile"},
                "events": [{"summary": "x" * 5000}],
            }
        )
        assert triage_context.startswith("Current market context:\n")
        assert len(triage_context) <= 2050
        assert "BTCUSDT" in triage_context
        assert "x" * 1000 not in triage_context

        user_message = engine._build_user_message(
            symbol="BTCUSDT",
            context=json.dumps({"market": {"symbol": "BTCUSDT", "hurst": 0.61}}),
        )
        assert "Additional context:" in user_message
        assert "hurst" in user_message
    finally:
        if os.path.exists(path):
            os.unlink(path)
