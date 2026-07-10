"""WP-A.4 反事實重跑管線純函數回歸(預註冊 §2/§3/§4/§5/§8/§10)。

MODULE_NOTE:
  模塊用途:覆蓋 counterfactual_rerun 的判準承載鏈 —— CR1 day-cluster 單側
    t(§4,含退化保護與 IID 收斂性)、greedy 非重疊窗(§2.6)、kline 補算
    markout 的 leak-free/censored 語義(§2.1)、雙源觀測組裝與複本一致性
    (§2.1/§2.3,build_observations_for_cell)、E1-E5 eligibility 旗標邊界
    (§3,build_cell_horizon_stats)、cluster V=0 併入 DATA_INTEGRITY(§4)、
    family 選擇含 NEAR 排除(§5.1)、§8.1 判定式真值表、§10.1 deviation_log
    靜態清單、凍結 ledger 視圖重建的檔案歸屬規則。統計判準本身凍結於預註冊
    文檔,測試只驗實作忠實性。
  依賴:conftest 把 research/ 加進 sys.path。
"""

from __future__ import annotations

import datetime as dt
import json

from cost_gate_learning_lane import counterfactual_rerun as cr
from cost_gate_learning_lane.evidence_stats import (
    cluster_one_sided_t_p_value,
    one_sided_t_p_value,
)


# ---------------------------------------------------------------------------
# §4 CR1 cluster-robust t
# ---------------------------------------------------------------------------

def test_cluster_t_singleton_clusters_equals_iid_t():
    """每觀測自成 cluster(G=n)時 V=s²/n、df=n−1,與 IID t 完全一致。"""
    values = [12.0, -3.0, 7.0, 1.5, -8.0, 20.0]
    clusters = list(range(len(values)))
    out = cluster_one_sided_t_p_value(values, clusters)
    mean = sum(values) / len(values)
    std = (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5
    iid_p = one_sided_t_p_value(mean, std, len(values))
    assert out["g"] == len(values)
    assert out["df"] == len(values) - 1
    assert abs(out["p"] - iid_p) < 1e-12


def test_cluster_t_hand_computed_two_clusters():
    """兩 cluster 手算對照:V = [G/(G−1)]×(1/n²)×ΣS_g²,df=G−1。"""
    values = [10.0, 14.0, 2.0, 6.0]
    clusters = ["d1", "d1", "d2", "d2"]
    out = cluster_one_sided_t_p_value(values, clusters)
    mean = 8.0
    s1 = (10.0 - mean) + (14.0 - mean)  # +8
    s2 = (2.0 - mean) + (6.0 - mean)    # −8
    v = (2 / 1) * (s1 * s1 + s2 * s2) / 16.0  # = 16
    assert out["g"] == 2 and out["df"] == 1
    assert abs(out["t"] - mean / v ** 0.5) < 1e-12
    assert 0.0 < out["p"] < 0.5  # t=2, df=1 → p≈0.1476


def test_cluster_t_degenerate_single_cluster_and_zero_variance():
    """退化保護:G<2 → p=None;V=0(全同值)→ p=None + zero_cluster_variance。"""
    single = cluster_one_sided_t_p_value([5.0, 6.0], ["d1", "d1"])
    assert single["p"] is None
    assert single["degenerate_reason"] == "cluster_count_below_2"
    flat = cluster_one_sided_t_p_value([5.0, 5.0, 5.0, 5.0], ["a", "a", "b", "b"])
    assert flat["p"] is None
    assert flat["degenerate_reason"] == "zero_cluster_variance"


def test_cluster_t_deflates_pseudo_replication_confidence():
    """F1 形態:單日大量同向樣本在 day-cluster 下不得產生 IID 級偽顯著。

    兩日、每日 15 個同向觀測:IID n=30 的 p 遠小;cluster df=1 的 p 必須顯著
    大於 IID p(信心被日級相依正確稀釋)。
    """
    values = [60.0 + (i % 3) for i in range(15)] + [58.0 + (i % 3) for i in range(15)]
    clusters = ["d1"] * 15 + ["d2"] * 15
    out = cluster_one_sided_t_p_value(values, clusters)
    mean = sum(values) / len(values)
    std = (sum((v - mean) ** 2 for v in values) / 29) ** 0.5
    iid_p = one_sided_t_p_value(mean, std, 30)
    assert out["df"] == 1
    assert out["p"] > iid_p * 10


# ---------------------------------------------------------------------------
# §2.6 greedy 非重疊窗
# ---------------------------------------------------------------------------

def test_greedy_non_overlap_earliest_first():
    entries = [{"entry_minute": m} for m in (0, 30, 60, 61, 150)]
    selected, excluded = cr.greedy_non_overlap(entries, horizon_minutes=60)
    assert [e["entry_minute"] for e in selected] == [0, 60, 150]
    assert excluded == 2


# ---------------------------------------------------------------------------
# §2.1 kline 補算 markout
# ---------------------------------------------------------------------------

def _bars(start_minute: int, count: int, price: float = 100.0, step: float = 0.1):
    return {start_minute + i: price + i * step for i in range(count)}


def test_backfill_markout_leak_free_entry_strictly_after_ts():
    """entry = ts 後首根 bar open(嚴格 >);Sell 側 gross 取反號。"""
    bars = _bars(1000, 200)
    ts_ms = 1000 * 60_000 + 30_000  # 分鐘 1000 內 → entry 必須是分鐘 1001
    buy = cr.backfill_markout(bars, ts_ms=ts_ms, horizon_minutes=60, side_sign=1.0)
    assert buy["censored"] is False
    assert buy["entry_minute"] == 1001
    entry_price = bars[1001]
    exit_price = bars[1061]
    expected = (exit_price - entry_price) / entry_price * 10_000.0
    assert abs(buy["gross_bps"] - expected) < 1e-9
    sell = cr.backfill_markout(bars, ts_ms=ts_ms, horizon_minutes=60, side_sign=-1.0)
    assert abs(sell["gross_bps"] + expected) < 1e-9


def test_backfill_markout_censored_semantics():
    """觀測斷供沿 lane 現行:entry 延遲 >5min / exit 延遲超窗 → censored。"""
    no_entry = cr.backfill_markout(
        {2000: 100.0}, ts_ms=1000 * 60_000, horizon_minutes=60, side_sign=1.0
    )
    assert no_entry["censored"] is True
    assert no_entry["censor_reason"] == "entry_observation_gap"
    # entry 有價、exit 目標(+60m)之後 15min 延遲窗內無價 → exit censored。
    bars = _bars(1001, 10)
    no_exit = cr.backfill_markout(
        bars, ts_ms=1000 * 60_000 + 1, horizon_minutes=60, side_sign=1.0
    )
    assert no_exit["censored"] is True
    assert no_exit["censor_reason"] == "exit_observation_gap"


# ---------------------------------------------------------------------------
# §8.1 判定式真值表
# ---------------------------------------------------------------------------

def _cell(**overrides):
    base = {
        "eligible": True,
        "data_integrity_suspect": False,
        "p1_mean_net_E_positive": True,
        "p2_net_E_positive_pct_ge_60": True,
        "bh_fdr_pass": True,
        "p4_no_suspect": True,
        "p5_not_single_regime_episode": True,
    }
    base.update(overrides)
    return base


def test_judge_cell_truth_table():
    assert cr.judge_cell(_cell()) == "PROMOTE_BOUNDED_PROBE_CANDIDATE"
    # §2.3:資料完整性疑點先於一切統計結論(即使 E1-E5 全過也不給 VETO/PROMOTE)。
    assert (
        cr.judge_cell(_cell(data_integrity_suspect=True, eligible=False))
        == "DATA_INTEGRITY_SUSPECT_EXCLUDED"
    )
    # ¬P1 或 ¬P3 → VETO(誤殺假說該 cell 落錘)。
    assert (
        cr.judge_cell(_cell(p1_mean_net_E_positive=False))
        == "BLOCK_CONFIRMED_UNDER_EXPECTED_COST"
    )
    assert (
        cr.judge_cell(_cell(bh_fdr_pass=False))
        == "BLOCK_CONFIRMED_UNDER_EXPECTED_COST"
    )
    assert cr.judge_cell(_cell(bh_fdr_pass=None)) == (
        "BLOCK_CONFIRMED_UNDER_EXPECTED_COST"
    )
    # eligibility 不過 → 禁止方向性結論(§3.4)。
    assert (
        cr.judge_cell(_cell(eligible=False)) == "SAMPLE_INSUFFICIENT_AFTER_DEDUP"
    )
    # P1∧P3 過但 P2/P4/P5 缺 → 非 PROMOTE 非 VETO。
    assert (
        cr.judge_cell(_cell(p5_not_single_regime_episode=False))
        == "NOT_PROMOTED_SECONDARY_CONDITION_FAILED"
    )


# ---------------------------------------------------------------------------
# 凍結 ledger 視圖重建
# ---------------------------------------------------------------------------

def _outcome_row(generated_at: str, cell: str = "s|AAAUSDT|Buy") -> str:
    return json.dumps(
        {
            "record_type": "blocked_signal_outcome",
            "side_cell_key": cell,
            "attempt_id": f"a-{generated_at}",
            "generated_at_utc": generated_at,
            "entry_ts_ms": 1_783_000_000_000,
            "horizon_minutes": 60,
            "gross_bps": 5.0,
            "realized_net_bps": -6.0,
            "censored": False,
        }
    )


def test_load_frozen_ledger_rows_membership(tmp_path):
    """段檔 ts ≤ frozen → 全量;主檔/更晚段檔 → generated_at 過濾;過舊段檔排除。"""
    frozen = dt.datetime(2026, 7, 9, 21, 31, 15, tzinfo=dt.timezone.utc)
    (tmp_path / "probe_ledger.20260701T000000Z.jsonl").write_text(
        _outcome_row("2026-06-30T00:00:00+00:00") + "\n", encoding="utf-8"
    )
    # 凍結後才輪轉的段檔:凍結前後兩行,只有前者屬凍結視圖。
    (tmp_path / "probe_ledger.20260710T010000Z.jsonl").write_text(
        _outcome_row("2026-07-09T20:00:00+00:00")
        + "\n"
        + _outcome_row("2026-07-09T23:00:00+00:00")
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "probe_ledger.jsonl").write_text(
        _outcome_row("2026-07-10T01:00:00+00:00") + "\n", encoding="utf-8"
    )
    # retention cutoff(frozen−14d = 06-25)前的段檔:凍結 run 看不見 → 排除。
    (tmp_path / "probe_ledger.20260620T000000Z.jsonl").write_text(
        _outcome_row("2026-06-19T00:00:00+00:00") + "\n", encoding="utf-8"
    )
    manifest, rows = cr.load_frozen_ledger_rows(tmp_path, frozen_generated_at=frozen)
    memberships = {m["name"]: m["frozen_view_membership"] for m in manifest}
    assert memberships["probe_ledger.20260701T000000Z.jsonl"] == "full"
    assert memberships["probe_ledger.20260710T010000Z.jsonl"] == "generated_at_filtered"
    assert memberships["probe_ledger.jsonl"] == "generated_at_filtered"
    assert (
        memberships["probe_ledger.20260620T000000Z.jsonl"]
        == "excluded_before_retention_cutoff"
    )
    kept = sorted(row["generated_at_utc"] for row in rows)
    assert kept == ["2026-06-30T00:00:00+00:00", "2026-07-09T20:00:00+00:00"]
    assert all("sha256" in m and len(m["sha256"]) == 64 for m in manifest)


# ---------------------------------------------------------------------------
# §2.1/§2.3 雙源觀測組裝(build_observations_for_cell)
# ---------------------------------------------------------------------------

_CELL = "strat|TSTUSDT|Buy"
# 整 UTC 日邊界的 epoch 分鐘基準(讓 day/top-day 計算可控)。
_BASE_MIN = (1_783_000_000_000 // 86_400_000) * 1440


def _ledger_row(
    attempt_id: str,
    entry_ts_ms: int,
    gross: float | None,
    *,
    horizon: int = 60,
    censored: bool = False,
):
    return {
        "record_type": "blocked_signal_outcome",
        "side_cell_key": _CELL,
        "attempt_id": attempt_id,
        "horizon_minutes": horizon,
        "censored": censored,
        "entry_ts_ms": entry_ts_ms,
        "gross_bps": gross,
        "realized_net_bps": (gross - 20.0) if gross is not None else None,
        "funding_drag_bps": 0.0,
    }


def test_build_observations_dual_source_merge_and_attribution():
    """§2.1 雙源合併:同鍵取 ledger、無覆蓋 kline 補算、bar 斷供 censored。

    同時驗代表行規則:同分鐘複本(容差內)取 attempt_id 字典序最小的 gross,
    不取平均(§2.2)。
    """
    m1 = _BASE_MIN + 10
    m2 = _BASE_MIN + 130
    m3 = _BASE_MIN + 310
    ledger = [
        # 同分鐘兩複本:值差 5e-10 < 容差 1e-9 → 一致;代表行 = "a"(字典序最小)。
        _ledger_row("b", m1 * 60_000 + 1_000, 10.0),
        _ledger_row("a", m1 * 60_000 + 2_000, 10.0 + 5e-10),
        # 不同 horizon 的行不得進本 (cell, 60) 組裝。
        _ledger_row("h240", m1 * 60_000 + 3_000, 50.0, horizon=240),
    ]
    pg = [
        # 拒單 ts 落分鐘 m1−1 → 候選 entry 分鐘 = m1,已有 ledger 觀測 → covered。
        {"ts_ms": (m1 - 1) * 60_000 + 5_000},
        # m2:無 ledger 覆蓋、bars 有 entry/exit → kline 補算。
        {"ts_ms": (m2 - 1) * 60_000 + 30_000},
        # m2 同分鐘第二筆秒級重發 → 同觀測(dedup 收縮),歸 duplicate。
        {"ts_ms": (m2 - 1) * 60_000 + 40_000},
        # m3:bars 無價 → entry 觀測斷供 censored。
        {"ts_ms": (m3 - 1) * 60_000},
    ]
    bars = {m2: 100.0, m2 + 60: 101.0}
    bundle = cr.build_observations_for_cell(
        cell_key=_CELL,
        horizon_minutes=60,
        ledger_rows=ledger,
        pg_rejections=pg,
        bars=bars,
    )
    assert bundle["ledger_raw_row_count"] == 2  # horizon-240 行不入
    assert bundle["replica_inconsistent_group_count"] == 0
    assert bundle["pg_rows_covered_by_ledger"] == 1
    assert bundle["pg_rows_backfilled"] == 1
    assert bundle["pg_rows_duplicate_observation"] == 1
    assert bundle["pg_rows_censored"] == 1
    obs = {o["entry_minute"]: o for o in bundle["observations"]}
    assert sorted(obs) == [m1, m2]
    # 代表行 = attempt_id "a" 的 gross(逐位保留,非平均)。
    assert obs[m1]["gross_bps"] == 10.0 + 5e-10
    assert obs[m1]["raw_member_count"] == 2
    assert obs[m1]["obs_source"] == "ledger"
    # kline 補算 gross = (101−100)/100×1e4 = +100bps(Buy)。
    assert obs[m2]["obs_source"] == "kline_backfill"
    assert abs(obs[m2]["gross_bps"] - 100.0) < 1e-9


def test_build_observations_replica_inconsistency_and_e5_drop():
    """§2.3 複本不一致(超容差)必計數;§3 E5 無 gross 的行剔除並計數。"""
    m1 = _BASE_MIN + 10
    m2 = _BASE_MIN + 130
    ledger = [
        _ledger_row("a", m1 * 60_000, 10.0),
        _ledger_row("b", m1 * 60_000 + 500, 10.1),  # 差 0.1bps ≫ 1e-9 容差
        _ledger_row("c", m2 * 60_000, None),  # gross 缺失 → E5 剔除
    ]
    bundle = cr.build_observations_for_cell(
        cell_key=_CELL,
        horizon_minutes=60,
        ledger_rows=ledger,
        pg_rejections=[],
        bars=None,
    )
    assert bundle["replica_inconsistent_group_count"] == 1
    assert bundle["dropped_not_recomputable_row_count"] == 1
    assert [o["entry_minute"] for o in bundle["observations"]] == [m1]


# ---------------------------------------------------------------------------
# §3 E1-E5 eligibility 旗標邊界 + §4 cluster V=0(build_cell_horizon_stats)
# ---------------------------------------------------------------------------

# 已投影(_load_expected_slippage 輸出形)的實測滑點查表:
# cost_E = max(2×(5.5+1.0)+0, 11.0) = 13.0bps → net_expected = gross − 13.0。
_EXPECTED_SLIPPAGE = {
    "per_symbol": {},
    "global_mean_abs": 1.0,
    "global_tail_bps": 2.0,
    "global_tail_metric": "cvar90",
}
_NOW = dt.datetime(2026, 7, 10, 12, 0, tzinfo=dt.timezone.utc)


def _obs_entry(minute: int, gross: float):
    return {
        "entry_minute": minute,
        "gross_bps": gross,
        "obs_source": "ledger",
        "funding_drag_bps": 0.0,
        # 直接給 recorded 保守淨值,避開 conservative_cost_bps 的 TOML/IO 路徑。
        "net_conservative_recorded": gross - 20.0,
        "raw_member_count": 1,
    }


def _bundle(observations, **overrides):
    base = {
        "observations": observations,
        "ledger_raw_row_count": len(observations),
        "ledger_censored_row_count": 0,
        "pg_rejection_row_count": 0,
        "pg_rows_covered_by_ledger": 0,
        "pg_rows_duplicate_observation": 0,
        "pg_rows_backfilled": 0,
        "pg_rows_censored": 0,
        "backfill_censored_key_count": 0,
        "replica_inconsistent_group_count": 0,
        "dropped_not_recomputable_row_count": 0,
    }
    base.update(overrides)
    return base


def _stats(observations, **bundle_overrides):
    return cr.build_cell_horizon_stats(
        cell_key=_CELL,
        horizon_minutes=60,
        membership=["A"],
        obs_bundle=_bundle(observations, **bundle_overrides),
        expected_slippage=_EXPECTED_SLIPPAGE,
        funding_interval_hours=8.0,
        conservative_table=None,
        btc_closes={},
        symbol_closes=None,
        edge_estimate=None,
        now_utc=_NOW,
    )


def _day_spread_entries(day_counts: list[int], jitter_step: float = 0.5):
    """per-day 入選 entry 數 → hourly 間距觀測(60m horizon 下全過非重疊窗)。

    gross 帶跨日變化的 jitter:避免 std=0 / cluster V=0 誤觸資料完整性疑點。
    """
    entries = []
    i = 0
    for day, count in enumerate(day_counts):
        for hour in range(count):
            gross = 14.0 + (i % 7) * jitter_step
            entries.append(_obs_entry(_BASE_MIN + day * 1440 + hour * 60, gross))
            i += 1
    return entries


def test_eligibility_e1_n_eff_boundary_30_vs_29():
    """§3 E1 邊界:n_eff=30 過、29 不過(mutation `>=`→`>` 必紅)。"""
    ok = _stats(_day_spread_entries([5, 5, 5, 5, 5, 5]))
    assert ok["n_eff"] == 30
    assert ok["sample_eligibility_failures"] == []
    assert ok["eligible"] is True
    assert isinstance(ok["p_cluster_one_sided"], float)
    short = _stats(_day_spread_entries([5, 5, 5, 5, 5, 4]))
    assert short["n_eff"] == 29
    assert short["sample_eligibility_failures"] == ["E1_n_eff_below_30"]
    assert short["eligible"] is False
    assert cr.judge_cell(short) == "SAMPLE_INSUFFICIENT_AFTER_DEDUP"


def test_eligibility_e2_distinct_days_boundary_5_vs_4():
    """§3 E2 邊界:distinct UTC days=5 過、4 不過。"""
    ok = _stats(_day_spread_entries([6, 6, 6, 6, 6]))
    assert ok["distinct_entry_utc_days"] == 5
    assert ok["sample_eligibility_failures"] == []
    bad = _stats(_day_spread_entries([8, 8, 7, 7]))
    assert bad["n_eff"] == 30
    assert bad["distinct_entry_utc_days"] == 4
    assert bad["sample_eligibility_failures"] == ["E2_distinct_utc_days_below_5"]


def test_eligibility_e3_top_day_share_boundary_50_vs_above():
    """§3 E3 邊界:top-day share=50.0% 過(≤50)、53.3% 不過。"""
    ok = _stats(_day_spread_entries([15, 4, 4, 4, 3]))
    assert ok["n_eff"] == 30
    assert abs(ok["top_entry_day_share_pct"] - 50.0) < 1e-9
    assert ok["sample_eligibility_failures"] == []
    bad = _stats(_day_spread_entries([16, 4, 4, 3, 3]))
    assert bad["n_eff"] == 30
    assert bad["top_entry_day_share_pct"] > 50.0
    assert bad["sample_eligibility_failures"] == ["E3_top_day_share_above_50pct"]


def test_eligibility_e4_censored_pct_boundary_30_vs_above():
    """§3 E4 邊界:censored_pct=30.0% 過(≤30)、31.4% 不過。"""
    entries = _day_spread_entries([5, 5, 5, 5, 5, 5])
    # 分母 = 有效 raw(35)+ censored;15/(35+15)=30.0% 恰在邊界內。
    ok = _stats(entries, ledger_raw_row_count=35, ledger_censored_row_count=15)
    assert abs(ok["censored_pct"] - 30.0) < 1e-9
    assert ok["sample_eligibility_failures"] == []
    bad = _stats(entries, ledger_raw_row_count=35, ledger_censored_row_count=16)
    assert bad["censored_pct"] > 30.0
    assert bad["sample_eligibility_failures"] == ["E4_censored_pct_above_30"]


def test_eligibility_e5_dropped_rows_flagged_when_below_floor():
    """§3 E5:剔除不可重算行後仍低於 floor → E5 旗標(與 E1 並列透明)。"""
    out = _stats(
        _day_spread_entries([2, 2, 2, 2, 2]),
        dropped_not_recomputable_row_count=3,
    )
    assert out["n_eff"] == 10
    assert "E1_n_eff_below_30" in out["sample_eligibility_failures"]
    assert "E5_after_drop_still_below_floor" in out["sample_eligibility_failures"]


def test_replica_inconsistency_excludes_cell_from_statistics():
    """§2.3:複本不一致的 cell 不給 p、判 DATA_INTEGRITY_SUSPECT_EXCLUDED。"""
    out = _stats(
        _day_spread_entries([5, 5, 5, 5, 5, 5]),
        replica_inconsistent_group_count=1,
    )
    assert out["data_integrity_suspect"] is True
    assert out["p_cluster_one_sided"] is None
    assert out["cluster_degenerate_reason"] == "not_computed"
    assert out["eligible"] is False
    assert cr.judge_cell(out) == "DATA_INTEGRITY_SUSPECT_EXCLUDED"


def test_cluster_zero_variance_folds_into_data_integrity_not_veto():
    """§4 V=0 正本語義:cluster sums 相消(個體 std>0、V=0)= DATA_INTEGRITY。

    退化輸入:每日 {x̄+1, x̄−1, x̄+1, x̄−1, x̄},日 cluster sum 全為 0 → CR1
    V=0 而 std>0。修復前此 cell eligible-with-p-None → 排出 family →
    judge 判 BLOCK_CONFIRMED(方向性統計結論)=違 §4;修復後必須併入
    data_integrity_suspect,只可判 DATA_INTEGRITY_SUSPECT_EXCLUDED。
    """
    entries = []
    for day in range(6):
        for hour, net in enumerate([6.0, 4.0, 6.0, 4.0, 5.0]):
            entries.append(
                _obs_entry(_BASE_MIN + day * 1440 + hour * 60, 13.0 + net)
            )
    out = _stats(entries)
    assert out["n_eff"] == 30
    assert out["sample_eligibility_failures"] == []  # E1-E5 全過
    assert out["std_net_E"] > 0.0
    assert out["zero_variance_suspect"] is False  # std==0 真子集未觸發
    assert out["cluster_degenerate_reason"] == "zero_cluster_variance"
    assert out["p_cluster_one_sided"] is None
    assert out["data_integrity_suspect"] is True
    assert out["eligible"] is False
    verdict = cr.judge_cell(out)
    assert verdict == "DATA_INTEGRITY_SUSPECT_EXCLUDED"
    assert verdict != "BLOCK_CONFIRMED_UNDER_EXPECTED_COST"


# ---------------------------------------------------------------------------
# §5.1 family 選擇(select_family):NEAR-only / ineligible / p=None 排除
# ---------------------------------------------------------------------------


def _family_cell(membership, *, eligible=True, p=0.01):
    return {
        "eligible": eligible,
        "p_cluster_one_sided": p,
        "population_membership": membership,
    }


def test_select_family_membership_rules():
    cell_a = _family_cell(["A"])
    cell_b = _family_cell(["B"])
    cell_ab = _family_cell(["A", "B"])
    near_only = _family_cell(["NEAR_CHARTER_MANDATED"])
    ineligible = _family_cell(["A"], eligible=False)
    p_none = _family_cell(["B"], p=None)
    family = cr.select_family(
        [cell_a, near_only, cell_b, ineligible, p_none, cell_ab]
    )
    assert family == [cell_a, cell_b, cell_ab]


# ---------------------------------------------------------------------------
# §10.1 deviation_log 靜態清單
# ---------------------------------------------------------------------------


def test_base_deviation_log_registers_frozen_sql_projection_rewrite():
    """§10.1 治理一致性:凍結 SQL 的 SELECT 投影改寫必須記入 deviation_log。"""
    log = cr._base_deviation_log()
    assert all(
        entry["level"] == "implementation" and entry["what"] and entry["why"]
        for entry in log
    )
    assert any(
        "SELECT 投影" in entry["what"] and "逐字" in entry["what"]
        for entry in log
    )
