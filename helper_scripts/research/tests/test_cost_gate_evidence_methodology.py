"""證據方法學重設計回歸(B2-1:P1-2 / P2-8 / F7)。

MODULE_NOTE:
  模塊用途：覆蓋 QC spec §7 測試用例 1-5(P1-2)、10-13(P2-8)、14-17(F7)。
    P2-7 Rust 用例(6/9)在 rust/openclaw_engine/src/demo_learning_lane_tests.rs;
    用例 7(MC 誤殺率)、8(配對 L1)為 §3 診斷數學，此處以 UCB 純函數等價驗證(7)。
  依賴：conftest 把 research/ 加進 sys.path(以模組名 import lane package)。
"""

from __future__ import annotations

import datetime as dt
import math

import pytest

from cost_gate_learning_lane import cost_model
from cost_gate_learning_lane import evidence_stats
from cost_gate_learning_lane.outcome_review import (
    BlockedOutcomeReviewConfig,
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
)


NOW = dt.datetime(2026, 7, 4, 18, 0, 0, tzinfo=dt.timezone.utc)


def _quantile_payload(*, symbols, global_q75, asof=None, global_n=200):
    return {
        "asof": (asof or NOW.isoformat()),
        "symbols": symbols,
        "global": {"n": global_n, "q75": global_q75},
    }


def _blocked_admission_row(attempt_id, symbol, side, entry, ts_ms, horizon=60):
    return {
        "record_type": "probe_admission_decision",
        "attempt_id": attempt_id,
        "decision": "REJECT",
        "allowed_to_submit_order": False,
        "side_cell_key": f"strat|{symbol}|{side}",
        "event": {
            "strategy_name": "strat",
            "symbol": symbol,
            "side": side,
            "entry_price": entry,
            "ts_ms": ts_ms,
        },
        "outcome_horizon_minutes": horizon,
    }


def _obs(symbol, ts_ms, price):
    return {"symbol": symbol, "ts_ms": ts_ms, "price": price}


# ---------------------------------------------------------------------------
# P1-2:成本模型
# ---------------------------------------------------------------------------


def test_cost_fallback_chain():
    """用例 1:symbol_q75 / global_q75 / toml_tier 三態 + 全部 ≥ 11.0 floor。"""
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(
            symbols=[{"symbol": "AAAUSDT", "n": 25, "q75": 14.0}],
            global_q75=12.0,
        )
    )
    # symbol A:n=25 ≥ 20 → symbol_q75。
    a = cost_model.conservative_cost_bps(symbol="AAAUSDT", horizon_minutes=60, table=table, now=NOW)
    assert a["cost_model_source"] == "symbol_q75"
    assert a["slippage_bps"] == 14.0
    # symbol B:n<20 → global_q75。
    table_b = cost_model.load_slippage_quantiles(
        _quantile_payload(
            symbols=[{"symbol": "BBBUSDT", "n": 5, "q75": 99.0}],
            global_q75=12.0,
        )
    )
    b = cost_model.conservative_cost_bps(symbol="BBBUSDT", horizon_minutes=60, table=table_b, now=NOW)
    assert b["cost_model_source"] == "global_q75"
    assert b["slippage_bps"] == 12.0
    # artifact 缺失 → toml_tier。
    c = cost_model.conservative_cost_bps(symbol="CCCUSDT", horizon_minutes=60, table=None, now=NOW)
    assert c["cost_model_source"] == "toml_tier"
    for out in (a, b, c):
        assert out["cost_bps"] >= cost_model.FEE_FLOOR_BPS


def test_cost_ge_realized_quantile():
    """用例 2(驗收 A1 直測):cost_bps == 2×(5.5+q75)×1.3(funding=0)。"""
    q75 = 24.97
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(symbols=[{"symbol": "DDDUSDT", "n": 50, "q75": q75}], global_q75=q75)
    )
    out = cost_model.conservative_cost_bps(symbol="DDDUSDT", horizon_minutes=60, table=table, now=NOW)
    expected = 2.0 * (5.5 + q75) * 1.3
    assert out["cost_bps"] == pytest.approx(expected, abs=1e-9)


def test_cost_floor_and_thin_sample():
    """負滑點/畸形 → 夾到 fee_floor 並改記 source。"""
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(symbols=[{"symbol": "EEEUSDT", "n": 30, "q75": -100.0}], global_q75=-100.0)
    )
    out = cost_model.conservative_cost_bps(symbol="EEEUSDT", horizon_minutes=60, table=table, now=NOW)
    assert out["cost_bps"] == cost_model.FEE_FLOOR_BPS
    assert out["cost_model_source"] == "fee_floor"


def test_stale_artifact_falls_back_to_toml():
    """artifact asof 超 48h → 視為不新鮮 → toml_tier。"""
    stale = NOW - dt.timedelta(hours=72)
    table = cost_model.load_slippage_quantiles(
        _quantile_payload(
            symbols=[{"symbol": "FFFUSDT", "n": 30, "q75": 14.0}],
            global_q75=12.0,
            asof=stale.isoformat(),
        )
    )
    out = cost_model.conservative_cost_bps(symbol="FFFUSDT", horizon_minutes=60, table=table, now=NOW)
    assert out["cost_model_source"] == "toml_tier"


def test_funding_crossing_count():
    """用例 5:240m horizon 跨 1 個 8h 結算;60m 不跨(對齊 epoch 邊界)。"""
    # 對齊 8h 邊界的 event ts:2026-07-04T00:00:00Z。
    base = int(dt.datetime(2026, 7, 4, 0, 0, 0, tzinfo=dt.timezone.utc).timestamp() * 1000)
    # 從邊界起 240m 內下一個結算在 +8h → 不跨(240m<480m)。取 event 在 +5h 起 240m 跨 +8h。
    event_5h = base + 5 * 3_600_000
    assert cost_model.funding_crossing_count(event_ts_ms=event_5h, horizon_minutes=240) == 1
    # 60m from +5h → +6h,不跨 +8h → 0。
    assert cost_model.funding_crossing_count(event_ts_ms=event_5h, horizon_minutes=60) == 0
    # 1h fundingInterval:240m horizon 最多 4 次(addendum §C errata)。
    assert (
        cost_model.funding_crossing_count(
            event_ts_ms=base + 1, horizon_minutes=240, funding_interval_hours=1.0
        )
        == 4
    )


# ---------------------------------------------------------------------------
# P1-2c / F1(c):overlay flip + realized 矛盾
# ---------------------------------------------------------------------------


def _blocked_outcome_row(attempt_id, side_cell, gross, *, cost_model_version=None):
    row = {
        "record_type": "blocked_signal_outcome",
        "attempt_id": attempt_id,
        "side_cell_key": side_cell,
        "symbol": side_cell.split("|")[1],
        "strategy_name": side_cell.split("|")[0],
        "side": side_cell.split("|")[2],
        "horizon_minutes": 60,
        "gross_bps": gross,
        "realized_net_bps": gross - 4.0,
        "net_bps_optimistic": gross - 4.0,
        "cost_bps": 4.0,
    }
    if cost_model_version:
        row["cost_model_version"] = cost_model_version
    return row


def test_backfill_overlay_flip():
    """用例 3:legacy net=+5(cost 4.0),overlay cost=25.0 → candidate=False ∧ flipped=True。"""
    rows = [
        # 3 筆 legacy gross=+9(net_opt=+5),全正 → 樂觀下過線。
        _blocked_outcome_row("a1", "strat|GGGUSDT|Buy", 9.0),
        _blocked_outcome_row("a2", "strat|GGGUSDT|Buy", 9.0),
        _blocked_outcome_row("a3", "strat|GGGUSDT|Buy", 9.0),
    ]
    overlay = {
        aid: {
            "attempt_id": aid,
            "cost_bps_conservative": 25.0,
            "realized_net_bps_conservative": 9.0 - 25.0,
            "cost_model_version": "conservative_v1",
            "cost_model_source": "global_q75",
        }
        for aid in ("a1", "a2", "a3")
    }
    packet = build_blocked_signal_outcome_review(rows, overlay=overlay, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["review_candidate"] is False
    assert cell["candidacy_flipped_by_cost_model"] is True
    assert packet["candidacy_flipped_by_cost_model_count"] == 1


def test_realized_contradiction_flag():
    """用例 4:edge EV=−16.76/n=18 vs counterfactual avg 高 → EXECUTION_REALISM_SUSPECT。"""
    rows = [
        _blocked_outcome_row(f"c{i}", "strat|HHHUSDT|Buy", 79.0, cost_model_version="conservative_v1")
        for i in range(3)
    ]
    edge = {"strat::HHHUSDT": {"realized_ev_bps": -16.76, "n": 18}}
    packet = build_blocked_signal_outcome_review(rows, edge_estimates=edge, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["realized_contradiction"] is True
    assert cell["status"] == "EXECUTION_REALISM_SUSPECT"
    assert cell["review_candidate"] is False


# ---------------------------------------------------------------------------
# P2-8:多重比較
# ---------------------------------------------------------------------------


def test_bh_fdr_vector():
    """用例 10:手算 fixture,q=0.10,m=15 → 通過集 = 兩最小 p。"""
    p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.5] + [0.9] * 8
    assert len(p) == 15
    passed = evidence_stats.bh_fdr_pass(p, 0.10)
    assert passed[0] is True and passed[1] is True
    assert not any(passed[2:])


def test_signflip_selection():
    """用例 11:全 null 80 cells → p 近均勻(多數 >0.05);注入強 cell → p<0.05。"""
    rng = __import__("random").Random(7)
    # 全 null:80 cells,每 cell 12 個對稱樣本。多次重複 ≥8/10 次 p>0.05。
    above = 0
    for trial in range(10):
        cells = [[rng.gauss(0.0, 50.0) for _ in range(12)] for _ in range(80)]
        out = evidence_stats.sign_flip_selection_p_value(cells, b=300, seed=1000 + trial)
        if out["p_selection"] > 0.05:
            above += 1
    assert above >= 8, f"全 null p>0.05 次數={above}"
    # 注入單一強 cell(μ≈5σ/√n)→ p 應顯著。
    strong = [[100.0] * 12] + [[rng.gauss(0.0, 20.0) for _ in range(12)] for _ in range(79)]
    strong_out = evidence_stats.sign_flip_selection_p_value(strong, b=500, seed=42)
    assert strong_out["p_selection"] < 0.05


def test_selection_universe_required():
    """用例 12:packet 必含 selection_universe(消費端 fail-closed on missing K)。"""
    rows = [_blocked_outcome_row(f"s{i}", "strat|IIIUSDT|Buy", 5.0) for i in range(3)]
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    assert "selection_universe" in packet
    su = packet["selection_universe"]
    assert su["k_effective"] == su["n_side_cells"] * su["n_horizons"]
    assert "headline_selection" in packet


def test_bh_fdr_gates_review_candidate():
    """conservative 過線但 BH 未過 → 撤下候選,標 EXPLORATION_CANDIDATE_BH_FDR_NOT_PASSED。"""
    # 高變異數 cell:avg 剛過 0 但 t 檢定不顯著 → BH 不過。
    nets = [1.0, -80.0, 82.0, -78.0, 80.0, 1.0]
    rows = []
    for i, net in enumerate(nets):
        rows.append(
            {
                "record_type": "blocked_signal_outcome",
                "attempt_id": f"b{i}",
                "side_cell_key": "strat|JJJUSDT|Buy",
                "symbol": "JJJUSDT",
                "strategy_name": "strat",
                "side": "Buy",
                "horizon_minutes": 60,
                "gross_bps": net + 4.0,
                "realized_net_bps": net,
                "net_bps_optimistic": net,
                "cost_bps": 4.0,
                "cost_model_version": "conservative_v1",
            }
        )
    cfg = BlockedOutcomeReviewConfig(min_net_positive_pct=0.0)
    packet = build_blocked_signal_outcome_review(rows, cfg=cfg, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["bh_fdr_pass"] is False
    assert cell["review_candidate"] is False


# ---------------------------------------------------------------------------
# F7:censored 出場/入場
# ---------------------------------------------------------------------------


def test_exit_censored():
    """用例 14:exit 後 40min 才有價(horizon 60m,max_exit_delay 15min)→ censored。"""
    ts = 1_782_000_000_000
    ledger = [_blocked_admission_row("e1", "KKKUSDT", "Buy", 100.0, ts, horizon=60)]
    obs = [
        _obs("KKKUSDT", ts, 100.0),  # entry
        _obs("KKKUSDT", ts + 60 * 60_000 + 40 * 60_000, 101.0),  # exit 遲 40min
    ]
    now = dt.datetime.fromtimestamp((ts + 200 * 60_000) / 1000, tz=dt.timezone.utc)
    out = build_blocked_signal_outcome_records(ledger, obs, now_utc=now)
    assert len(out) == 1
    row = out[0]
    assert row["censored"] is True
    assert row["censor_reason"] == "exit_observation_gap"
    assert row["realized_net_bps"] is None


def test_exit_within_delay():
    """用例 15:延遲 10min → 正常 row + exit_delay_ms=600000。"""
    ts = 1_782_000_000_000
    ledger = [_blocked_admission_row("e2", "LLLUSDT", "Buy", 100.0, ts, horizon=60)]
    obs = [
        _obs("LLLUSDT", ts, 100.0),
        _obs("LLLUSDT", ts + 60 * 60_000 + 10 * 60_000, 101.0),  # 遲 10min ≤ 15min
    ]
    now = dt.datetime.fromtimestamp((ts + 200 * 60_000) / 1000, tz=dt.timezone.utc)
    out = build_blocked_signal_outcome_records(ledger, obs, now_utc=now)
    assert len(out) == 1
    assert out[0]["censored"] is False
    assert out[0]["exit_delay_ms"] == 600_000


def test_entry_gap_censored():
    """用例 16:entry 觀測永缺、時限已過 → censored reason=entry_observation_gap。"""
    ts = 1_782_000_000_000
    ledger = [_blocked_admission_row("e3", "MMMUSDT", "Buy", None, ts, horizon=60)]
    # 無 entry_price、無任何觀測 → entry gap;now 遠超時限。
    obs = []
    now = dt.datetime.fromtimestamp((ts + 500 * 60_000) / 1000, tz=dt.timezone.utc)
    out = build_blocked_signal_outcome_records(ledger, obs, now_utc=now)
    assert len(out) == 1
    assert out[0]["censored"] is True
    assert out[0]["censor_reason"] == "entry_observation_gap"


def test_censored_excluded_from_stats():
    """用例 17:cell 10 row 中 4 censored → count=6、pct=40 → OBSERVATION_GAP_SUSPECT。"""
    rows = []
    for i in range(6):
        rows.append(
            {
                "record_type": "blocked_signal_outcome",
                "attempt_id": f"g{i}",
                "side_cell_key": "strat|NNNUSDT|Buy",
                "symbol": "NNNUSDT",
                "strategy_name": "strat",
                "side": "Buy",
                "horizon_minutes": 60,
                "gross_bps": 20.0,
                "realized_net_bps": 5.0,
                "net_bps_optimistic": 5.0,
                "cost_bps": 15.0,
                "cost_model_version": "conservative_v1",
                "censored": False,
            }
        )
    for i in range(4):
        rows.append(
            {
                "record_type": "blocked_signal_outcome",
                "attempt_id": f"gc{i}",
                "side_cell_key": "strat|NNNUSDT|Buy",
                "censored": True,
                "censor_reason": "exit_observation_gap",
                "realized_net_bps": None,
            }
        )
    packet = build_blocked_signal_outcome_review(rows, now_utc=NOW)
    cell = packet["top_side_cells"][0]
    assert cell["outcome_count"] == 6
    assert cell["censored_count"] == 4
    assert cell["censored_pct"] == pytest.approx(40.0)
    assert cell["status"] == "OBSERVATION_GAP_SUSPECT"
    assert cell["review_candidate"] is False


# ---------------------------------------------------------------------------
# P2-7 用例 7 等價(UCB 純函數誤殺率;Rust 側跑 disable 規則本體)
# ---------------------------------------------------------------------------


def test_disable_ucb_false_kill_rate():
    """用例 7:μ=+30,σ=200,n=8 UCB-futility 誤殺率 ∈ [3%,6%](復算 4.4%)。"""
    import random

    rng = random.Random(20260704)
    z = 1.281_551_565_544_600_4
    kills = 0
    trials = 10000
    for _ in range(trials):
        sample = [rng.gauss(30.0, 200.0) for _ in range(8)]
        mean = sum(sample) / 8
        var = sum((v - mean) ** 2 for v in sample) / 7
        std = math.sqrt(var)
        ucb = mean + z * std / math.sqrt(8)
        if ucb < 0.0:
            kills += 1
    rate = kills / trials
    assert 0.03 <= rate <= 0.06, f"誤殺率={rate}"


# ---------------------------------------------------------------------------
# P2-7 用例 6 直測(Python 側禁用規則本體 = summarize_side_cell_runtime_state)
#
# 為什麼補此測(LOW-2):test_disable_ucb_false_kill_rate 只驗 UCB 純函數誤殺率,
# 不觸 Python 禁用規則本體;Rust ucb_futility_disable_rule_matches_spec_thresholds
# 兜住 Rust 側,但 Python-only drift(如 ddof n−1→n、嚴格 <→<=)不會被 golden 常量
# 測試抓到。此處對齊 Rust 三錨點 + n<2 pure-mean 雙向,直跑真 Python 函數,並含兩個
# mutation-敏感錨點:D(ddof)、G(嚴格 <)。
# ---------------------------------------------------------------------------

_UCB_SIDE_CELL_KEY = "ma_crossover|ETHUSDT|Sell"
_UCB_NOW_MS = 1_782_046_800_000


def _ucb_candidate(max_probe_orders: int = 100) -> dict:
    # max_probe_orders 取大值,確保 remaining>0,不被 probe_budget_exhausted 先攔,
    # 使禁用決策純由 UCB-futility 規則主導。
    return {
        "side_cell_key": _UCB_SIDE_CELL_KEY,
        "probe_proposal": {"max_probe_orders": max_probe_orders},
    }


def _ucb_outcome_rows(nets: list[float]) -> list[dict]:
    return [
        {
            "record_type": "probe_outcome",
            "side_cell_key": _UCB_SIDE_CELL_KEY,
            "realized_net_bps": net,
        }
        for net in nets
    ]


def _two_point_mean_std(mean: float, std: float, n: int = 8) -> list[float]:
    # 對稱雙點構造(對齊 Rust scale_to_mean_std):n/2 個 mean+d、n/2 個 mean−d,
    # 則 x̄=mean、s(ddof=1)=std。d=std·√((n−1)/n)。
    d = std * math.sqrt((n - 1) / n)
    half = n // 2
    return [mean + d] * half + [mean - d] * half


def _ucb_disabled(nets: list[float], *, min_failed: int) -> bool:
    from cost_gate_learning_lane.runtime_adapter import (
        RuntimeAdmissionConfig,
        summarize_side_cell_runtime_state,
    )

    state = summarize_side_cell_runtime_state(
        _ucb_candidate(),
        _ucb_outcome_rows(nets),
        now_ms=_UCB_NOW_MS,
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=min_failed),
    )
    return state["disabled"]


def test_python_ucb_futility_disable_rule_matches_spec_thresholds():
    """用例 6 Python 直測:對齊 Rust 三錨點,證 Python 禁用規則本體 = UCB-futility。"""
    # A:n=7 全負 → 未達 n≥8 門檻 → 不禁用(UCB 規則不啟動)。
    assert _ucb_disabled([-120.0] * 7, min_failed=8) is False
    # B:n=8,x̄=−120,s=200 → UCB ≈ −29.4 < 0 → 禁用。
    assert _ucb_disabled(_two_point_mean_std(-120.0, 200.0), min_failed=8) is True
    # C:n=8,x̄=−80,s=200 → UCB ≈ +10.6 > 0 → 不禁用。
    assert _ucb_disabled(_two_point_mean_std(-80.0, 200.0), min_failed=8) is False


def test_python_ucb_futility_pure_mean_fallback_both_directions():
    """n<2 無法估變異數 → 退純均值判準(對齊 Rust (true, Some(mean), None) 分支)。"""
    # n=1 mean=−10 → −10 < 0 → 禁用。
    assert _ucb_disabled([-10.0], min_failed=1) is True
    # n=1 mean=+10 → +10 < 0 False → 不禁用。
    assert _ucb_disabled([10.0], min_failed=1) is False


def test_python_ucb_ddof_and_strict_comparison_are_mutation_sensitive():
    """mutation 自證錨點:若 std 誤用 ddof=n(而非 n−1)或 <→<=,此測必紅。

    D(ddof 敏感):n=8,x̄=−87.693,s(ddof=1)=200 → UCB=+2.93>0 不禁用;若 std 誤除以
      n(ddof=0)則 s=187.08、UCB=−2.93<0 會誤禁 → 突變翻紅。此 mean 精選於兩個 ddof
      判準的翻轉窗口 (−90.62, −84.77) 正中,使唯一區別就是 n−1 vs n。
    G(嚴格 < 敏感):n=1 pure-mean,mean=0.0 → 0<0 為 False 不禁用;若 <→<= 則
      0<=0 為 True 會誤禁 → 突變翻紅。
    """
    # D:正解不禁用(ddof=1);ddof=n 突變會使其禁用。
    assert _ucb_disabled(_two_point_mean_std(-87.693_024_306_047_45, 200.0), min_failed=8) is False
    # G:正解不禁用(嚴格 <);<= 突變會使其禁用。
    assert _ucb_disabled([0.0], min_failed=1) is False
