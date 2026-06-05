"""residual_alpha_cycle（R-2b orchestrator）pure-core 測試。

驗 n_trials 搜尋基數推導、單配置診斷性 defer、有參數變體 peers 的 CSCV 路徑、
無資料。DB cycle 層在 Linux runtime 另行驗證。
"""

from __future__ import annotations

import pytest

from program_code.ml_training.residual_alpha_cycle import (
    PBO_NOT_APPLICABLE_SINGLE,
    CellResidualResult,
    derive_n_trials,
    evaluate_cell,
)

_BUCKET = 14400.0  # 4h


def _btc_klines(n: int):
    # btc 桶報酬交替 +50 / -50 bps（讓 beta 可辨識）
    out = []
    for i in range(n):
        ret = 50.0 if i % 2 == 0 else -50.0
        out.append({"ts": i * _BUCKET, "open": 100.0, "close": 100.0 * (1.0 + ret / 10_000.0)})
    return out


def _variant_round_trips(n: int, *, alpha: float, beta: float):
    # 每桶一筆 round-trip，exit 落在桶 i；net = alpha + beta*btc桶報酬 + 微擾
    out = []
    for i in range(n):
        btc = 50.0 if i % 2 == 0 else -50.0
        net = alpha + beta * btc + 0.1 * ((i % 3) - 1)
        out.append({"entry_ts": i * _BUCKET + 100.0, "exit_ts": i * _BUCKET + 200.0, "net_bps": net})
    return out


# ---- derive_n_trials ----

def test_derive_n_trials_cardinality_and_floor():
    n, deriv = derive_n_trials(12, 25, 1)
    assert n == 300
    assert "12var × 25sym × 1strat = 300" in deriv
    # 低於 floor → floored 到 10
    n2, deriv2 = derive_n_trials(1, 1, 1, floor=10)
    assert n2 == 10
    assert "floored to 10" in deriv2
    # 0/負數 clamp 到 1
    n3, _ = derive_n_trials(0, -5, 3, floor=1)
    assert n3 == 3  # 1 × 1 × 3


# ---- evaluate_cell ----

def test_evaluate_cell_single_config_defers():
    rts = _variant_round_trips(120, alpha=8.0, beta=0.2)
    klines = _btc_klines(120)
    res = evaluate_cell(
        "grid_trading::BTCUSDT", rts, klines,
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
        peer_variant_round_trips=None,
        min_train_observations=20, min_eval_observations=8, min_coverage=0.8,
    )
    assert isinstance(res, CellResidualResult)
    assert res.status == "single_config_defer"
    assert res.promotion_ready is False
    assert res.reason == "pbo_not_applicable_single_candidate"
    assert res.report is not None
    assert res.report["pbo_status"] == PBO_NOT_APPLICABLE_SINGLE
    # 單配置 1var×1sym×1strat=1 → floored 到 10
    assert res.n_trials == 10
    assert res.diag["n_peers"] == 0


def test_evaluate_cell_with_peers_runs_cscv():
    candidate = _variant_round_trips(120, alpha=10.0, beta=0.2)
    peers = [
        _variant_round_trips(120, alpha=2.0, beta=0.2),
        _variant_round_trips(120, alpha=3.0, beta=0.2),
        _variant_round_trips(120, alpha=4.0, beta=0.2),
    ]
    klines = _btc_klines(120)
    res = evaluate_cell(
        "grid_trading::BTCUSDT", candidate, klines,
        n_param_variants=4, n_symbols_screened=1, n_strategies_screened=1,
        peer_variant_round_trips=peers,
        min_train_observations=20, min_eval_observations=8, min_coverage=0.8,
    )
    assert res.status == "evaluated"
    assert res.diag["n_peers"] == 3
    assert res.report is not None and "verdict" in res.report
    # 4var×1×1=4 → floored 到 10
    assert res.n_trials == 10


def test_evaluate_cell_no_data():
    res = evaluate_cell(
        "empty::X", [], _btc_klines(10),
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
    )
    assert res.status == "no_data"
    assert res.promotion_ready is False
    assert res.report is None


# ---- R-3 attach primitive + env-flag ----

from datetime import datetime, timezone  # noqa: E402

from program_code.ml_training import residual_alpha_cycle as _cyc  # noqa: E402
from program_code.ml_training.residual_alpha_cycle import (  # noqa: E402
    attach_residual_reports,
    residual_producer_enabled,
)


def test_residual_producer_enabled_env(monkeypatch):
    monkeypatch.delenv("OPENCLAW_RESIDUAL_ALPHA_PRODUCER", raising=False)
    assert residual_producer_enabled() is False  # 預設 OFF
    monkeypatch.setenv("OPENCLAW_RESIDUAL_ALPHA_PRODUCER", "1")
    assert residual_producer_enabled() is True
    monkeypatch.setenv("OPENCLAW_RESIDUAL_ALPHA_PRODUCER", "0")
    assert residual_producer_enabled() is False


class _Rec:
    def __init__(self, strategy, symbol):
        self.strategy_name = strategy
        self.symbol = symbol
        self.payload = {}


def test_attach_residual_reports_maps_to_payload(monkeypatch):
    recs = [_Rec("grid_trading", "BTCUSDT"), _Rec("ma_crossover", "ETHUSDT")]

    def _fake_cycle(conn, cells, **kw):
        return {
            c["cell_key"]: CellResidualResult(
                cell_key=c["cell_key"], status="single_config_defer",
                promotion_ready=False, reason="pbo_not_applicable_single_candidate",
                n_trials=10, n_trials_derivation="...",
                report={"verdict": "defer_data", "pbo_status": "not_applicable_single_candidate"},
                diag={},
            )
            for c in cells
        }

    monkeypatch.setattr(_cyc, "build_cycle_residual_reports", _fake_cycle)
    n = attach_residual_reports(recs, conn=None, since=datetime(2026, 6, 1, tzinfo=timezone.utc))
    assert n == 2
    assert recs[0].payload["demo_residual_alpha_report"]["verdict"] == "defer_data"
    assert recs[1].payload["demo_residual_alpha_report"]["pbo_status"] == "not_applicable_single_candidate"


def test_attach_empty_returns_zero():
    assert attach_residual_reports([], conn=None, since=datetime(2026, 6, 1, tzinfo=timezone.utc)) == 0
