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


# ---- Gap B：多因子 evaluate_cell（funding-loaded pure-carry beta-trap）----


def _flat_btc_klines(n: int):
    # BTC 桶報酬全 0（讓 candidate 的 raw edge 不可能來自 BTC beta）。
    return [{"ts": i * _BUCKET, "open": 100.0, "close": 100.0} for i in range(n)]


def _flat_symbol_klines(n: int):
    # 任一 symbol 桶報酬全 0（market basket 也全 0）。
    return [{"ts": i * _BUCKET, "open": 100.0, "close": 100.0} for i in range(n)]


def test_evaluate_cell_funding_carry_beta_trap_fails():
    """funding pure-carry beta-trap（mirror BTC beta-trap test）：候選 raw edge 全
    來自 funding carry（對 BTC/market 中性），多因子殘差化後殘差必須非正 → fail。

    這正是 funding-tilt 死掉的失敗模式：BTC-price beta 抓不到，funding 因子才抓得到。
    """
    n = 120
    # funding 結算：每桶一筆，rate 在 +0.0015 / -0.0005 間擺動（持續正 carry 偏壓，
    # 模擬 funding-tilt 看似有 edge 的真實樣態：均值為正但全來自 carry）。
    # 做空（net_side=-1）：funding>0=收費=正報酬 → funding factor = +rate*1e4。
    funding_rate_seq = [(0.0015 if i % 2 == 0 else -0.0005) for i in range(n)]
    funding = {
        "BTCUSDT": [
            {"ts": i * _BUCKET + 100.0, "funding_rate": funding_rate_seq[i]} for i in range(n)
        ]
    }
    # 候選 net = beta_f * funding_factor + 微擾（無 alpha）。net_side=-1：
    # funding_factor[i] = +rate[i]*1e4 = +15 / -5 bps；beta_f=1.5 → net 隨 carry 擺動，
    # 均值為正（看似 edge），但 100% 來自 carry beta。
    rts = []
    for i in range(n):
        funding_factor_bps = funding_rate_seq[i] * 1e4  # net_side=-1 → +rate*1e4
        net = 1.5 * funding_factor_bps + 0.05 * ((i % 3) - 1)  # 純 carry beta + 微擾
        rts.append({"entry_ts": i * _BUCKET + 100.0, "exit_ts": i * _BUCKET + 200.0, "net_bps": net})

    klines_by_symbol = {"BTCUSDT": _flat_btc_klines(n)}
    # 補足 market basket（>=8 個 symbol，全 0 報酬）。
    for j in range(10):
        klines_by_symbol[f"S{j}"] = _flat_symbol_klines(n)
    lifecycles = {s: (0.0, None) for s in klines_by_symbol}

    res = evaluate_cell(
        "funding_tilt::BTCUSDT", rts, _flat_btc_klines(n),
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
        peer_variant_round_trips=None,
        required_factors=("btc", "market", "funding"),
        klines_by_symbol=klines_by_symbol,
        lifecycles=lifecycles,
        funding_by_symbol=funding,
        position_symbols=["BTCUSDT"],
        net_side=-1,
        min_train_observations=20, min_eval_observations=8, min_coverage=0.8,
    )
    # 單配置仍走 defer 包裝，但底層 report 的 verdict / reasons 必反映 beta-trap。
    assert res.report is not None
    assert res.promotion_ready is False
    # raw 為正（carry 在 down/up 不對稱下淨正），residual 扣 funding beta 後非正。
    assert res.report["raw_mean_bps"] > 0.0
    assert res.report["residual_mean_bps"] <= 0.0
    # funding beta 必被辨識為主導（beta_loadings 含 funding 且顯著）。
    assert "funding" in res.report["beta_loadings"]
    assert res.report["beta_loadings"]["funding"] == pytest.approx(1.5, abs=0.2)
    # 殘差化後核心 reason 命中 beta-trap 家族。
    reasons = set(res.report.get("reasons", ()))
    assert (
        "raw_positive_residual_non_positive" in reasons
        or "r_beta_retention_below_threshold" in reasons
        or "beta_edge_share_above_threshold" in reasons
    )


def test_evaluate_cell_btc_only_default_unchanged_by_multi_factor_path():
    """行為中性回歸：required_factors 預設 ("btc",) 時，evaluate_cell 走原 BTC-only
    路徑，report 與「不傳 required_factors」完全一致（report dict 相等）。"""
    rts = _variant_round_trips(120, alpha=8.0, beta=0.2)
    klines = _btc_klines(120)
    base = evaluate_cell(
        "grid_trading::BTCUSDT", rts, klines,
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
        min_train_observations=20, min_eval_observations=8, min_coverage=0.8,
    )
    explicit = evaluate_cell(
        "grid_trading::BTCUSDT", rts, klines,
        n_param_variants=1, n_symbols_screened=1, n_strategies_screened=1,
        required_factors=("btc",),
        min_train_observations=20, min_eval_observations=8, min_coverage=0.8,
    )
    assert base.report == explicit.report


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
    # signal_spec 同時被附，且通過 validator
    from program_code.ml_training.candidate_signal_spec import validate_signal_spec
    spec0 = recs[0].payload["signal_spec"]
    v0 = validate_signal_spec(spec0, candidate_id="grid_trading::BTCUSDT", family_id="grid_trading")
    assert v0.ok is True


def test_attach_empty_returns_zero():
    assert attach_residual_reports([], conn=None, since=datetime(2026, 6, 1, tzinfo=timezone.utc)) == 0
