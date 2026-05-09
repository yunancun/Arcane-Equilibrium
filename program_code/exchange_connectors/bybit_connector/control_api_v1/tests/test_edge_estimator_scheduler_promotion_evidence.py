from __future__ import annotations

import sys
from pathlib import Path


_THIS_DIR = Path(__file__).resolve().parent
_CONTROL_API = _THIS_DIR.parent
_BYBIT_CONNECTOR = _CONTROL_API.parent
_EXCHANGE_CONNECTORS = _BYBIT_CONNECTOR.parent
_PROGRAM_CODE = _EXCHANGE_CONNECTORS.parent
_SRV_ROOT = _PROGRAM_CODE.parent
for _p in (str(_CONTROL_API), str(_SRV_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from app.edge_estimator_scheduler import EdgeEstimatorScheduler  # noqa: E402


def test_run_one_mode_pushes_demo_promotion_evidence(monkeypatch):
    sched = EdgeEstimatorScheduler(modes=("demo",), interval_s=3600.0, days_back=7)
    js_results = {
        ("ma_crossover", "BTCUSDT"): {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "grand_mean_bps": 1.0,
            "raw_bps_series": [15.0, 20.0, 18.0, 22.0] * 80,
        },
    }
    captured = {}

    def _fake_push(results, **kwargs):
        captured["results"] = results
        captured["kwargs"] = kwargs
        return {"status": "ok", "strategies": 1, "ledger_rows": 1}

    monkeypatch.setattr(
        "ml_training.james_stein_estimator.run_james_stein",
        lambda **kwargs: js_results,
    )
    monkeypatch.setattr(
        "ml_training.promotion_evidence.push_promotion_evidence_from_js_results",
        _fake_push,
    )

    summary = sched._run_one_mode("demo")

    assert summary["n_cells"] == 1
    assert summary["promotion_evidence"]["status"] == "ok"
    assert captured["results"] is js_results
    assert captured["kwargs"]["engine_mode"] == "demo"
    assert captured["kwargs"]["source"] == "edge_estimator_scheduler"


def test_run_one_mode_skips_livedemo_promotion_evidence(monkeypatch):
    sched = EdgeEstimatorScheduler(modes=("live_demo",), interval_s=3600.0, days_back=7)
    js_results = {
        ("ma_crossover", "BTCUSDT"): {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "grand_mean_bps": 1.0,
            "raw_bps_series": [15.0, 20.0, 18.0, 22.0] * 80,
        },
    }
    monkeypatch.setattr(
        "ml_training.james_stein_estimator.run_james_stein",
        lambda **kwargs: js_results,
    )

    summary = sched._run_one_mode("live_demo")

    assert summary["promotion_evidence"] == {
        "status": "skipped",
        "reason": "demo_only_promotion_evidence",
        "engine_mode": "live_demo",
    }
