"""AEG-S2 breadth ladder runner 測試矩陣（PA §7 T-tier-nest..T-manifest-index）。

MODULE_NOTE:
  模塊用途：驗證 breadth ladder 純函數核心（tiers + ladder）+ artifact 落地 +
    healthcheck。核心 case 全 synthetic（Mac 可跑，不連 PG），證「錯誤實作會 fail」
    （bite-proof 哲學，mirror FND-2/sibling）。
  涵蓋：
    T-tier-nest        — tier 嵌套（cohort_ids 組裝；recommended_tier 會 fail）
    T-survivor-inherit — alive_mask 繼承 + 0 自寫 listed_at 查詢（靜態）
    T-breadth-not-nindep — ★ 招牌：n_independent(full)==n_independent(core25)
    T-monotonic-survives — net edge 隨 breadth 存活
    T-monotonic-collapse — narrow fluke 塌縮
    T-insufficient-n     — n_independent<30 sample 牆
    T-top-liq-pit-flag   — top_liquidity asof-constant 降級標記
    T-determinism        — ladder_id 跨進程穩定 + row bytes 相同
    T-candidate-agnostic — protocol 可插兩候選 + 0 候選硬編碼（靜態）
    T-forbidden-route    — read-only 靜態（0 control_api / 0 DB write / OPENCLAW_DATA_DIR）
    T-manifest-index     — artifact 完整 + provenance 鏈
    + healthcheck        — survivorship PIT artifact 檢查三態
    + HIGH-1（re-E2）    — survivorship 真繼承 + 破 tautology bite：
        * non_inheriting_adapter_sets_false_and_healthcheck_fail — 壞 adapter→False+FAIL
        * well_behaved_adapter_yields_true — 對照 True（推導非常數）
        * adapter_clamps_dead_symbol_zero_holdings_after_delist — DEADUSDT delist 後 0 持倉
        * count_seen_delisted_real_uses_alive_mask — _count_seen_delisted 真用 alive_mask
        * harness_healthcheck_gate_raises_on_non_inheriting — healthcheck wiring load-bearing
    + NIT               — _fmt_num(-0.0) 正規化 determinism
  依賴：pytest + 標準庫 + numpy（HIGH-1 synthetic panel）（conftest 已把 research/ 加 sys.path）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aeg_breadth_ladder import (
    BREADTH_LADDER_VERSION,
    N_INDEPENDENT_PROMOTION_FLOOR,
)
from aeg_breadth_ladder import tiers as tiers_mod
from aeg_breadth_ladder import ladder as ladder_mod
from aeg_breadth_ladder import artifact as artifact_mod
from aeg_breadth_ladder import universe_artifact as ua_mod
from aeg_breadth_ladder import healthcheck as hc_mod
from aeg_breadth_ladder.evaluator import TierResult, StubEvaluator, CandidateEvaluator
from aeg_breadth_ladder.harness import assemble_tier_results, run_ladder


# ───────────────────────── synthetic helpers ─────────────────────────

def _u_row(symbol, cohort_ids, *, included=True, alive_from="2024-06-03T00:00:00+00:00",
           alive_to="2026-06-03T00:00:00+00:00", seen_delisted=False,
           recommended_tier="full_survivorship", unknown_lifetime=False):
    """synthetic FND-2 universe row（含 (b) 需要的欄）。"""
    return {
        "symbol": symbol,
        "cohort_ids": cohort_ids,           # list（synthetic）或 JSON 字串皆可
        "included": included,
        "alive_from_utc": alive_from,
        "alive_to_utc": alive_to,
        "seen_delisted": seen_delisted,
        "recommended_tier": recommended_tier,
        "unknown_lifetime": unknown_lifetime,
        "universe_id": "synthetic_universe_id",
        "run_id": "synthetic_fnd2_run",
    }


def _tr(tier, *, breadth, net_bps=None, n_independent=40, sample_unit="non_overlapping_holding_window",
        seen_delisted=0, gross_bps=None, long_bps=None, short_bps=None, t_hac=None,
        survivorship_mask_applied=True):
    """synthetic TierResult（預設 survivorship_mask_applied=True = well-behaved 候選）。"""
    return TierResult(
        tier=tier, breadth_symbol_count=breadth, seen_delisted_count=seen_delisted,
        net_bps=net_bps, gross_bps=gross_bps, cost_bps=11.0,
        net_to_cost_ratio=(net_bps / 11.0 if net_bps is not None else None),
        n_independent=n_independent, sample_unit=sample_unit, t_stat_hac=t_hac,
        long_leg_net_bps=long_bps, short_leg_net_bps=short_bps,
        pit_mask_source="fnd2_alive_from_alive_to", leak_free_signal=True,
        survivorship_mask_applied=survivorship_mask_applied,
    )


def _full_meta_args(tier_results, **overrides):
    """build_ladder 共用 kwargs（含 top_liquidity 降級 metadata）。"""
    quality, pit_mode, exclusion = ua_mod.tier_quality_and_exclusion()
    base = dict(
        run_id="r1", candidate_id="cand_x",
        asof_utc="2026-06-03T00:00:00+00:00",
        window_start_utc="2024-06-03T00:00:00+00:00",
        window_end_utc="2026-06-03T00:00:00+00:00",
        fnd2_universe_id="uid_1", fnd2_run_id="fnd2_run_1",
        tier_quality_by_name=quality, tier_rank_pit_mode_by_name=pit_mode,
        promotion_exclusion_by_name=exclusion,
    )
    base.update(overrides)
    return base


# ───────────────────────── T-tier-nest ─────────────────────────

def test_t_tier_nest_cohort_ids_build_nested_sets():
    """BTCUSDT cohort_ids=[full,core25] → 同時在 core25 / top_liquidity / full 三 tier。

    bite：用 recommended_tier（single-pick）組裝會讓 tier 互斥（BTC 只在 core25），
    本 test 證必須用 cohort_ids（multi-membership）+ nested 不變量成立。
    """
    rows = [
        _u_row("BTCUSDT", ["full_survivorship", "core25_pinned"]),
        _u_row("ALTUSDT", ["full_survivorship", "top_liquidity_40_50"]),
        _u_row("DEADUSDT", ["full_survivorship", "historical_delisted"], seen_delisted=True),
    ]
    tiers = tiers_mod.assemble_tiers(rows)
    # BTCUSDT 同時在三 nested tier（core25 ⊂ top_liq ⊂ full）。
    assert "BTCUSDT" in tiers[tiers_mod.TIER_CORE25_PINNED]
    assert "BTCUSDT" in tiers[tiers_mod.TIER_TOP_LIQUIDITY_40_50]   # nested：top_liq 含 core25
    assert "BTCUSDT" in tiers[tiers_mod.TIER_FULL_SURVIVORSHIP]
    # ALTUSDT 在 top_liq + full，但不在 core25。
    assert "ALTUSDT" in tiers[tiers_mod.TIER_TOP_LIQUIDITY_40_50]
    assert "ALTUSDT" in tiers[tiers_mod.TIER_FULL_SURVIVORSHIP]
    assert "ALTUSDT" not in tiers[tiers_mod.TIER_CORE25_PINNED]
    # nested 不變量成立。
    tiers_mod.assert_nested_invariant(tiers)


def test_t_tier_nest_recommended_tier_would_break_nesting():
    """證明若用 recommended_tier（single-pick）組 tier，BTC 不會出現在 top_liquidity。

    這是「為什麼必須用 cohort_ids」的反證：模擬一個錯誤組裝器只看 recommended_tier，
    結果 core25 ⊄ top_liquidity，nested 斷言會 fail。
    """
    rows = [
        _u_row("BTCUSDT", ["full_survivorship", "core25_pinned"], recommended_tier="core25_pinned"),
        _u_row("ALTUSDT", ["full_survivorship", "top_liquidity_40_50"],
               recommended_tier="top_liquidity_40_50"),
    ]

    # 錯誤組裝器：依 recommended_tier single-pick（每 symbol 只進一個 tier）。
    def _wrong_assemble(rows):
        out = {t.name: set() for t in tiers_mod.BREADTH_TIERS}
        for r in rows:
            out.setdefault(r["recommended_tier"], set()).add(r["symbol"])
        return {k: frozenset(v) for k, v in out.items()}

    wrong = _wrong_assemble(rows)
    # BTC 在 core25 但不在 top_liquidity（single-pick 的指紋）。
    assert "BTCUSDT" in wrong[tiers_mod.TIER_CORE25_PINNED]
    assert "BTCUSDT" not in wrong[tiers_mod.TIER_TOP_LIQUIDITY_40_50]
    # nested 不變量在錯誤組裝下 fail（core25 ⊄ top_liq）。
    with pytest.raises(AssertionError):
        tiers_mod.assert_nested_invariant(wrong)


def test_t_tier_nest_cohort_ids_json_string_parsed():
    """cohort_ids 為 JSON array 字串（CSV 讀回的真實形）→ 正確解析。"""
    rows = [
        _u_row("BTCUSDT", '["full_survivorship","core25_pinned"]'),
        _u_row("ALTUSDT", '["full_survivorship","top_liquidity_40_50"]'),
    ]
    tiers = tiers_mod.assemble_tiers(rows)
    assert "BTCUSDT" in tiers[tiers_mod.TIER_CORE25_PINNED]
    assert "BTCUSDT" in tiers[tiers_mod.TIER_TOP_LIQUIDITY_40_50]
    tiers_mod.assert_nested_invariant(tiers)


def test_t_tier_nest_excluded_rows_skipped():
    """included=false 的 row 不入任何 tier（FND-2 excluded 是診斷行）。"""
    rows = [
        _u_row("BTCUSDT", ["full_survivorship", "core25_pinned"]),
        _u_row("EXCLUDEDUSDT", ["full_survivorship"], included=False),
    ]
    tiers = tiers_mod.assemble_tiers(rows)
    assert "EXCLUDEDUSDT" not in tiers[tiers_mod.TIER_FULL_SURVIVORSHIP]
    assert "BTCUSDT" in tiers[tiers_mod.TIER_FULL_SURVIVORSHIP]


# ───────────────────────── T-survivor-inherit ─────────────────────────

def test_t_survivor_inherit_alive_mask_exact_from_artifact():
    """alive_mask 精確 = FND-2 artifact 的 alive_from/alive_to（繼承不重算）。"""
    rows = [
        _u_row("BTCUSDT", ["full_survivorship", "core25_pinned"],
               alive_from="2024-06-03T00:00:00+00:00", alive_to="2026-06-03T00:00:00+00:00"),
        _u_row("DEADUSDT", ["full_survivorship", "historical_delisted"],
               alive_from="2024-07-03T00:00:00+00:00", alive_to="2025-01-01T00:00:00+00:00",
               seen_delisted=True),
    ]
    mask = ua_mod.build_alive_mask(rows)
    af, at = mask["DEADUSDT"]
    assert af.isoformat() == "2024-07-03T00:00:00+00:00"
    assert at.isoformat() == "2025-01-01T00:00:00+00:00"
    # delisted map（artifact 權威）。
    delisted = ua_mod.build_seen_delisted_map(rows)
    assert delisted["DEADUSDT"] is True
    assert delisted["BTCUSDT"] is False


def test_t_survivor_inherit_no_listed_at_query_static():
    """靜態：tiers/ladder/universe_artifact 源碼（去註釋/字串後）0 自寫 listed_at /
    symbol_universe_snapshots SELECT（(b) 繼承 mask，不重算，MIT b.2）。"""
    pkg = Path(__file__).resolve().parents[1] / "aeg_breadth_ladder"
    for fname in ("tiers.py", "ladder.py", "universe_artifact.py"):
        code = _strip_comments_and_strings((pkg / fname).read_text(encoding="utf-8"))
        assert "symbol_universe_snapshots" not in code, f"{fname} 不得自寫 universe snapshot 查詢"
        assert "listed_at" not in code, f"{fname} 不得自寫 listed_at 查詢"
        assert "delisted_at" not in code, f"{fname} 不得自寫 delisted_at 查詢"


# ───────────────────────── T-breadth-not-nindep（★ 招牌）─────────────────────────

def test_t_breadth_not_nindep_n_independent_invariant():
    """★ core25(25 sym) vs full(800 sym) 餵相同 time-period 結構 → n_independent 相同。

    bite：若實作讓 n_independent 隨 symbol 漲（symbol-scaled 污染）→ invariant 自證
    False + monotonicity 不成立。本 test 餵 time-cluster-bound n_independent（兩 tier
    皆 40），斷言 breadth 大幅不同但 n_independent 不變。
    """
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=8.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=7.0,
                                              n_independent=40),
    }
    rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    # breadth 大幅不同。
    assert summary["per_tier_breadth"]["core25_pinned"] == 25
    assert summary["per_tier_breadth"]["full_survivorship"] == 800
    # ★ n_independent 不變（time-cluster-bound，NOT 33× symbol-scaled）。
    assert summary["per_tier_n_independent"]["core25_pinned"] == 40
    assert summary["per_tier_n_independent"]["full_survivorship"] == 40
    assert summary["monotonicity"]["n_independent_invariant_to_breadth"] is True


def test_t_breadth_not_nindep_symbol_scaled_is_detected():
    """bite 反證：若 n_independent 被 symbol-scaled（full=33×core25）→ invariant 自證 False。"""
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=8.0, n_independent=40),
        # 錯誤：n_independent 隨 symbol 膨脹（false-rich-sample）。
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=7.0,
                                              n_independent=40 * 32),
    }
    _rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    # invariant 必為 False（1280 >> 2×40）→ 暴露 symbol-scaled 污染。
    assert summary["monotonicity"]["n_independent_invariant_to_breadth"] is False


# ───────────────────────── T-monotonic-survives ─────────────────────────

def test_t_monotonic_survives():
    """net_bps[core25]=10 [full]=8（衰減但存活，n_indep>=30）→ survives / breadth_real。"""
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=8.0,
                                              n_independent=40),
    }
    _rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    mono = summary["monotonicity"]
    assert mono["net_bps_monotonic_in_breadth"] is True
    assert mono["net_bps_trend"] == "survives"
    assert summary["verdict_hint"] == "breadth_real"
    assert mono["narrow_only_edge"] is False


# ───────────────────────── T-monotonic-collapse ─────────────────────────

def test_t_monotonic_collapse_narrow_fluke():
    """net_bps[core25]=20 [full]=1（塌縮窄基）→ collapses_to_narrow / breadth-limited。"""
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=20.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=1.0,
                                              n_independent=40),
    }
    _rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    mono = summary["monotonicity"]
    assert mono["net_bps_trend"] == "collapses_to_narrow"
    assert mono["narrow_only_edge"] is True
    assert summary["verdict_hint"] == "breadth-limited"


def test_t_monotonic_collapse_to_negative():
    """net_bps[core25]=15 [full]=-3（加寬翻負）→ collapses_to_narrow。"""
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=15.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=-3.0,
                                              n_independent=40),
    }
    _rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    assert summary["monotonicity"]["net_bps_trend"] == "collapses_to_narrow"
    assert summary["verdict_hint"] == "breadth-limited"


# ───────────────────────── T-insufficient-n ─────────────────────────

def test_t_insufficient_n_sample_wall():
    """任一 nested tier n_independent=8（cost-wall weekly 牆）→ insufficient_n_independent
    + 該 tier excluded_from_promotion + reason 含 n_independent_below_30。"""
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=9.0,
                                              n_independent=8),
    }
    rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    assert summary["verdict_hint"] == "insufficient_n_independent"
    full_row = next(r for r in rows if r["breadth_cohort"] == "full_survivorship")
    assert full_row["excluded_from_promotion"] is True
    assert "n_independent_below_30" in (full_row["exclusion_reason"] or "")


# ───────────────────────── T-top-liq-pit-flag ─────────────────────────

def test_t_top_liq_pit_flag_diagnostic_only():
    """top_liquidity tier 標 asof_constant / liquidity_source_not_pit / excluded_from_promotion。"""
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: _tr("top_liquidity_40_50", breadth=50, net_bps=9.0,
                                                n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=8.0,
                                              n_independent=40),
    }
    rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    tl = next(r for r in rows if r["breadth_cohort"] == "top_liquidity_40_50")
    assert tl["tier_rank_pit_mode"] == "asof_constant"
    assert tl["tier_quality"] == "liquidity_source_not_pit"
    assert tl["excluded_from_promotion"] is True
    # monotonicity 主軸應排除 top_liquidity（diagnostic-only）→ 只用 core25/full → survives。
    assert summary["monotonicity"]["net_bps_trend"] == "survives"


# ───────────────────────── T-determinism ─────────────────────────

def test_t_determinism_same_input_same_ladder_id(tmp_path):
    """同 universe + 同 candidate 跑兩次 → ladder_id 相同 + row bytes 相同。"""
    def _make():
        return {
            tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0,
                                              n_independent=40, t_hac=1.23),
            tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=8.0,
                                                  n_independent=40, t_hac=0.98),
        }
    rows1, sum1 = ladder_mod.build_ladder(_make(), **_full_meta_args(_make(), run_id="run_a"))
    rows2, sum2 = ladder_mod.build_ladder(_make(), **_full_meta_args(_make(), run_id="run_b"))
    # ladder_id 與 run_id 無關（同 universe + 同 candidate）。
    assert sum1["ladder_id"] == sum2["ladder_id"]

    w1 = artifact_mod.write_all(
        rows1, sum1, run_id="run_a", candidate_id="cand_x",
        fnd2_universe_id="uid_1", fnd2_run_id="fnd2_run_1",
        source_tables=["market.klines"], repo_root=Path("."), runtime_host="test",
        artifact_root=tmp_path,
    )
    w2 = artifact_mod.write_all(
        rows2, sum2, run_id="run_b", candidate_id="cand_x",
        fnd2_universe_id="uid_1", fnd2_run_id="fnd2_run_1",
        source_tables=["market.klines"], repo_root=Path("."), runtime_host="test",
        artifact_root=tmp_path,
    )

    def _csv_no_runid(path):
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        return [ln.split(",", 1)[1] if "," in ln else ln for ln in lines]
    assert _csv_no_runid(w1["breadth_ladder_csv"]) == _csv_no_runid(w2["breadth_ladder_csv"])


def test_t_determinism_different_net_changes_ladder_id():
    """net_bps 改變 → ladder_id 改變（digest 有 bite，非常數）。"""
    base = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=8.0,
                                              n_independent=40),
    }
    changed = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=99.0,
                                              n_independent=40),
    }
    _r1, s1 = ladder_mod.build_ladder(base, **_full_meta_args(base))
    _r2, s2 = ladder_mod.build_ladder(changed, **_full_meta_args(changed))
    assert s1["ladder_id"] != s2["ladder_id"]


# ───────────────────────── T-candidate-agnostic ─────────────────────────

def test_t_candidate_agnostic_two_stubs_isolated():
    """兩個 stub CandidateEvaluator（不同 candidate_id）→ 同 (b) 跑出兩組 ladder，
    candidate_id 正確隔離。"""
    tiers_by_name = {
        tiers_mod.TIER_CORE25_PINNED: frozenset({"BTCUSDT"}),
        tiers_mod.TIER_FULL_SURVIVORSHIP: frozenset({"BTCUSDT", "ALTUSDT"}),
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: frozenset({"BTCUSDT"}),
        tiers_mod.TIER_SCANNER_ACTIVE_ASOF: frozenset(),
    }
    ev_a = StubEvaluator("candidate_alpha", {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=1, net_bps=5.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=2, net_bps=4.0,
                                              n_independent=40),
    })
    ev_b = StubEvaluator("candidate_beta", {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=1, net_bps=15.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=2, net_bps=1.0,
                                              n_independent=40),
    })
    # 確認 stub 滿足 protocol。
    assert isinstance(ev_a, CandidateEvaluator)

    res_a = assemble_tier_results(ev_a, tiers_by_name=tiers_by_name, alive_mask={}, seen_delisted_map={})
    res_b = assemble_tier_results(ev_b, tiers_by_name=tiers_by_name, alive_mask={}, seen_delisted_map={})
    _ra, sa = ladder_mod.build_ladder(res_a, **_full_meta_args(res_a, candidate_id=ev_a.candidate_id))
    _rb, sb = ladder_mod.build_ladder(res_b, **_full_meta_args(res_b, candidate_id=ev_b.candidate_id))
    assert sa["candidate_id"] == "candidate_alpha"
    assert sb["candidate_id"] == "candidate_beta"
    # 不同候選 → 不同 verdict（alpha survives，beta collapse）。
    assert sa["monotonicity"]["net_bps_trend"] == "survives"
    assert sb["monotonicity"]["net_bps_trend"] == "collapses_to_narrow"
    assert sa["ladder_id"] != sb["ladder_id"]


def test_t_candidate_agnostic_no_candidate_hardcoded_static():
    """靜態：tiers/ladder 源碼 0 候選名硬編碼（candidate-agnostic 自證）。"""
    pkg = Path(__file__).resolve().parents[1] / "aeg_breadth_ladder"
    for fname in ("tiers.py", "ladder.py"):
        code = _strip_comments_and_strings((pkg / fname).read_text(encoding="utf-8"))
        for cand in ("multiday", "funding_tilt", "listing_fade", "listing-fade"):
            assert cand not in code, f"{fname} 不得硬編碼候選名 {cand}（candidate-agnostic）"


# ───────────────────────── T-forbidden-route ─────────────────────────

def _strip_comments_and_strings(src: str) -> str:
    """以 tokenize 移除註釋與字串字面值，只留可執行 code 識別字（mirror FND-2 test）。"""
    import io
    import tokenize
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src
    return " ".join(out)


def test_t_forbidden_route_read_only_static():
    """ladder/tiers/universe_artifact/artifact/evaluator/healthcheck 源碼（去註釋/字串後）：
    0 control_api_v1 import / 0 DB write / 0 _fetch_historical_universe_snapshot_sync /
    artifact root 用 OPENCLAW_DATA_DIR（無硬編碼 /tmp/openclaw 進 code）。"""
    pkg = Path(__file__).resolve().parents[1] / "aeg_breadth_ladder"
    files = ("tiers.py", "ladder.py", "universe_artifact.py", "artifact.py",
             "evaluator.py", "healthcheck.py", "harness.py")
    for fname in files:
        raw = (pkg / fname).read_text(encoding="utf-8")
        code = _strip_comments_and_strings(raw)
        assert "control_api_v1" not in code, f"{fname} 不得 import control_api_v1 runtime"
        assert "_fetch_historical_universe_snapshot_sync" not in code, \
            f"{fname} 不得呼叫 _fetch_historical_universe_snapshot_sync"
        # 0 DB write 動詞（去字串後不得有 INSERT/UPDATE/DELETE/DROP/CREATE TABLE token）。
        for write_verb in ("INSERT", "UPDATE", "DELETE", "DROP"):
            assert write_verb not in code, f"{fname} 不得有 DB write 動詞 {write_verb}"

    # artifact root 用 OPENCLAW_DATA_DIR（raw 驗確切字串；harness/evaluator 委派候選 loader
    # 的 read-only session 由該 loader 保證）。
    art_raw = (pkg / "artifact.py").read_text(encoding="utf-8")
    assert "OPENCLAW_DATA_DIR" in art_raw
    # 硬編碼 /tmp/openclaw 只能作為 env 缺失時的 fallback 預設（與 FND-2 同模式）。
    # 確認沒有把 /tmp/openclaw 當主路徑寫死（出現必須伴隨 OPENCLAW_DATA_DIR getenv）。
    assert "os.environ.get(\"OPENCLAW_DATA_DIR\"" in art_raw


def test_t_forbidden_route_evaluator_delegates_readonly():
    """evaluator 真跑路徑委派 multiday data_loader（read-only session 由該 loader 保證）；
    evaluator 自身不開新 PG 連線 / 不設寫 session（靜態確認無 set_session(readonly=False)）。"""
    pkg = Path(__file__).resolve().parents[1] / "aeg_breadth_ladder"
    ev_raw = (pkg / "evaluator.py").read_text(encoding="utf-8")
    assert "readonly=False" not in ev_raw
    # evaluator 不自寫 psycopg2.connect（委派候選 loader）。
    ev_code = _strip_comments_and_strings(ev_raw)
    assert "psycopg2" not in ev_code


# ───────────────────────── T-manifest-index ─────────────────────────

def test_t_manifest_and_index_complete(tmp_path):
    """全 artifact write → 4 檔皆生成；artifact_index 每 child 有 path/sha256/byte_size/
    row_count/schema_version；manifest 含 fnd2_universe_id/fnd2_run_id provenance 鏈。"""
    tier_results = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0,
                                          n_independent=40, seen_delisted=2),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=8.0,
                                              n_independent=40, seen_delisted=255),
    }
    rows, summary = ladder_mod.build_ladder(tier_results, **_full_meta_args(tier_results))
    written = artifact_mod.write_all(
        rows, summary, run_id="t_manifest", candidate_id="cand_x",
        fnd2_universe_id="uid_abc", fnd2_run_id="fnd2_run_xyz",
        source_tables=["market.klines", "market.funding_rates", "<fnd2 universe artifact>"],
        repo_root=Path("."), runtime_host="test", artifact_root=tmp_path,
    )
    run_dir = Path(written["run_dir"])
    assert (run_dir / "breadth_ladder.csv").exists()
    assert (run_dir / "breadth_ladder_summary.json").exists()
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "artifact_index.json").exists()

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["program"] == "AEG"
    assert manifest["breadth_ladder_version"] == BREADTH_LADDER_VERSION
    assert manifest["fnd2_universe_id"] == "uid_abc"     # provenance 鏈
    assert manifest["fnd2_run_id"] == "fnd2_run_xyz"
    assert manifest["ladder_id"] == summary["ladder_id"]
    assert "<fnd2 universe artifact>" in manifest["source_tables"]

    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    names = {e["name"] for e in index["artifacts"]}
    assert {"breadth_ladder.csv", "breadth_ladder_summary.json", "manifest.json"} <= names
    for e in index["artifacts"]:
        assert e["sha256"] and len(e["sha256"]) == 64
        assert e["byte_size"] > 0
        assert "schema_version" in e
    csv_entry = next(e for e in index["artifacts"] if e["name"] == "breadth_ladder.csv")
    assert csv_entry["row_count"] == len(rows)

    # summary delisted_proof_total = 各 tier seen_delisted_count 加總。
    assert summary["delisted_proof_total"] == 2 + 255


# ───────────────────────── healthcheck ─────────────────────────

def test_healthcheck_pass_with_delisted_proof(tmp_path):
    """delisted_proof_total>=1 + survivorship 繼承 → PASS。"""
    breadth = tmp_path / "breadth_ladder_summary.json"
    breadth.write_text(json.dumps({
        "delisted_proof_total": 255, "survivorship_inherited_from_fnd2": True,
    }), encoding="utf-8")
    fnd2 = tmp_path / "universe_summary.json"
    fnd2.write_text(json.dumps({"survivor_rejection_status": "PASS"}), encoding="utf-8")
    status, msg = hc_mod.check_aeg_breadth_universe_pit(breadth, fnd2)
    assert status == "PASS", msg


def test_healthcheck_fail_truncated_to_current_survivor(tmp_path):
    """delisted_proof_total==0 但 FND-2 status != PROVEN_NONE → FAIL（truncation 指紋）。"""
    breadth = tmp_path / "breadth_ladder_summary.json"
    breadth.write_text(json.dumps({
        "delisted_proof_total": 0, "survivorship_inherited_from_fnd2": True,
    }), encoding="utf-8")
    fnd2 = tmp_path / "universe_summary.json"
    fnd2.write_text(json.dumps({"survivor_rejection_status": "PASS"}), encoding="utf-8")
    status, msg = hc_mod.check_aeg_breadth_universe_pit(breadth, fnd2)
    assert status == "FAIL", msg
    assert "truncate" in msg


def test_healthcheck_pass_proven_none_in_window(tmp_path):
    """delisted_proof_total==0 但 FND-2 PROVEN_NONE_IN_WINDOW → PASS（窗內確無 delisted）。"""
    breadth = tmp_path / "breadth_ladder_summary.json"
    breadth.write_text(json.dumps({
        "delisted_proof_total": 0, "survivorship_inherited_from_fnd2": True,
    }), encoding="utf-8")
    fnd2 = tmp_path / "universe_summary.json"
    fnd2.write_text(json.dumps({"survivor_rejection_status": "PROVEN_NONE_IN_WINDOW"}),
                    encoding="utf-8")
    status, _msg = hc_mod.check_aeg_breadth_universe_pit(breadth, fnd2)
    assert status == "PASS"


def test_healthcheck_fail_not_inherited(tmp_path):
    """survivorship_inherited_from_fnd2 != true → FAIL（(b) 疑自寫 mask）。"""
    breadth = tmp_path / "breadth_ladder_summary.json"
    breadth.write_text(json.dumps({
        "delisted_proof_total": 255, "survivorship_inherited_from_fnd2": False,
    }), encoding="utf-8")
    fnd2 = tmp_path / "universe_summary.json"
    fnd2.write_text(json.dumps({"survivor_rejection_status": "PASS"}), encoding="utf-8")
    status, _msg = hc_mod.check_aeg_breadth_universe_pit(breadth, fnd2)
    assert status == "FAIL"


def test_healthcheck_warn_missing_artifact(tmp_path):
    """artifact 缺 → WARN（不打 FAIL，artifact 可能尚未生成）。"""
    status, _msg = hc_mod.check_aeg_breadth_universe_pit(
        tmp_path / "nope.json", tmp_path / "nope2.json")
    assert status == "WARN"


# ───────────────────────── end-to-end (synthetic FND-2 artifact + stub candidate) ─────────────────────────

def test_run_ladder_end_to_end_with_stub(tmp_path):
    """run_ladder 全鏈（synthetic FND-2 artifact + StubEvaluator）→ 產 breadth artifact。

    驗 harness 編排：讀 FND-2 artifact → assemble tiers → alive_mask → evaluate →
    ladder → write，全程 0 PG（StubEvaluator 注入）。
    """
    # 構造 synthetic FND-2 artifact（universe.csv + summary）。
    fnd2_dir = tmp_path / "fnd2_run"
    fnd2_dir.mkdir()
    import csv as _csv
    cols = ua_mod._REQUIRED_FND2_COLUMNS + ("universe_id",)
    with open(fnd2_dir / "universe.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(list(cols))
        # BTCUSDT core25, ALTUSDT top_liq, DEADUSDT delisted。
        w.writerow(["BTCUSDT", '["full_survivorship","core25_pinned"]', "true",
                    "2024-06-03T00:00:00+00:00", "2026-06-03T00:00:00+00:00", "false",
                    "core25_pinned", "false", "uid_e2e"])
        w.writerow(["ALTUSDT", '["full_survivorship","top_liquidity_40_50"]', "true",
                    "2024-06-03T00:00:00+00:00", "2026-06-03T00:00:00+00:00", "false",
                    "top_liquidity_40_50", "false", "uid_e2e"])
        w.writerow(["DEADUSDT", '["full_survivorship","historical_delisted"]', "true",
                    "2024-07-03T00:00:00+00:00", "2025-01-01T00:00:00+00:00", "true",
                    "full_survivorship", "false", "uid_e2e"])
    (fnd2_dir / "universe_summary.json").write_text(json.dumps({
        "universe_id": "uid_e2e", "run_id": "fnd2_run_e2e",
        "survivor_rejection_status": "PASS", "delisted_proof_count": 1,
    }), encoding="utf-8")

    stub = StubEvaluator("e2e_candidate", {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=0, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: _tr("top_liquidity_40_50", breadth=0, net_bps=9.0,
                                                n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=0, net_bps=8.0,
                                              n_independent=40),
    })

    class _Args:
        run_id = "breadth_e2e"
        fnd2_run_dir = str(fnd2_dir)
        asof = "2026-06-03T00:00:00Z"
        window_start = "2024-06-03T00:00:00Z"
        window_end = "2026-06-03T00:00:00Z"
        artifact_root = str(tmp_path / "out")
        session_id = None
        created_by_role = "E1"

    result = run_ladder(_Args(), evaluator=stub)
    summary = result["summary"]
    assert summary["candidate_id"] == "e2e_candidate"
    assert summary["fnd2_universe_id"] == "uid_e2e"
    assert summary["fnd2_run_id"] == "fnd2_run_e2e"
    # DEADUSDT 在 full tier 且 seen_delisted → delisted_proof_total>=1。
    assert summary["delisted_proof_total"] >= 1
    assert summary["survivorship_inherited_from_fnd2"] is True
    # monotonicity 主軸排除 top_liquidity（diagnostic-only）→ core25/full survives。
    assert summary["monotonicity"]["net_bps_trend"] == "survives"

    # healthcheck 對產出的 artifact PASS。
    written = result["written"]
    status, msg = hc_mod.check_aeg_breadth_universe_pit(
        Path(written["breadth_ladder_summary"]), fnd2_dir / "universe_summary.json")
    assert status == "PASS", msg
    # run_ladder 內建 healthcheck gate 也回 PASS（load-bearing）。
    assert result["healthcheck"]["status"] == "PASS", result["healthcheck"]
    persisted_summary = json.loads(
        Path(written["breadth_ladder_summary"]).read_text(encoding="utf-8")
    )
    # summary artifact 必須持久化 healthcheck；否則 CLI stdout PASS 不能被事後審計。
    assert persisted_summary["survivorship_healthcheck"] == result["healthcheck"]


# ───────── HIGH-1：survivorship 真繼承 + 破 tautology bite（re-E2）─────────

class _NonInheritingEvaluator:
    """bite：漏用 alive_mask / 漏 alive_to 上界的壞 adapter（survivorship_mask_applied=False）。

    模擬一個收了 alive_mask 卻**從不 apply**、PnL 跑在 listed_at-only survivorship 的
    候選——必須讓 summary 推導 survivorship_inherited_from_fnd2=False 且 healthcheck FAIL。
    """

    candidate_id = "non_inheriting_bad_adapter"

    def __init__(self, results_by_tier: dict):
        self._results = results_by_tier

    def evaluate(self, *, tier, universe, alive_mask):
        from dataclasses import replace
        base = self._results.get(tier)
        if base is None:
            return TierResult(
                tier=tier, breadth_symbol_count=len(universe), seen_delisted_count=0,
                n_independent=0, sample_unit="bad_no_result",
                survivorship_mask_applied=None,
            )
        # 關鍵 bite：明確標 False（收了 alive_mask 卻不 apply）。
        return replace(base, survivorship_mask_applied=False)


def test_high1_non_inheriting_adapter_sets_false_and_healthcheck_fail(tmp_path):
    """★ bite：非繼承 adapter → survivorship_inherited_from_fnd2=False + healthcheck FAIL。

    證明繼承自證**不是寫死 True 的 tautology**：壞 adapter（不 apply alive_mask）必被抓。
    對照 well-behaved 路徑（_tr 預設 mask_applied=True）會回 True（見其他 test）。
    """
    tiers_by_name = {
        tiers_mod.TIER_CORE25_PINNED: frozenset({"BTCUSDT"}),
        tiers_mod.TIER_FULL_SURVIVORSHIP: frozenset({"BTCUSDT", "DEADUSDT"}),
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: frozenset({"BTCUSDT"}),
        tiers_mod.TIER_SCANNER_ACTIVE_ASOF: frozenset(),
    }
    bad = _NonInheritingEvaluator({
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=1, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: _tr("top_liquidity_40_50", breadth=1, net_bps=9.0,
                                                n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=2, net_bps=8.0,
                                              n_independent=40),
    })
    alive_mask = {
        "BTCUSDT": (None, None),
        "DEADUSDT": (None, None),
    }
    res = assemble_tier_results(bad, tiers_by_name=tiers_by_name, alive_mask=alive_mask,
                               seen_delisted_map={"DEADUSDT": True})
    _rows, summary = ladder_mod.build_ladder(res, **_full_meta_args(res, candidate_id=bad.candidate_id))
    # 推導非寫死：壞 adapter → False。
    assert summary["survivorship_inherited_from_fnd2"] is False

    # 寫 artifact 後 healthcheck 對此 summary FAIL（繼承斷言抓到非繼承）。
    written = artifact_mod.write_all(
        _rows, summary, run_id="bad_run", candidate_id=bad.candidate_id,
        fnd2_universe_id="uid_bad", fnd2_run_id="fnd2_bad",
        source_tables=["market.klines"], repo_root=Path("."), runtime_host="test",
        artifact_root=tmp_path,
    )
    fnd2 = tmp_path / "universe_summary.json"
    fnd2.write_text(json.dumps({"survivor_rejection_status": "PASS"}), encoding="utf-8")
    status, msg = hc_mod.check_aeg_breadth_universe_pit(
        Path(written["breadth_ladder_summary"]), fnd2)
    assert status == "FAIL", msg
    assert "繼承" in msg or "inherit" in msg.lower() or "mask" in msg.lower()


def test_high1_well_behaved_adapter_yields_true():
    """對照：mask_applied=True 的 well-behaved 候選 → survivorship_inherited_from_fnd2=True
    （證明推導**有兩種輸出**，非常數 False）。"""
    res = {
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=25, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=800, net_bps=8.0,
                                              n_independent=40),
    }
    _rows, summary = ladder_mod.build_ladder(res, **_full_meta_args(res))
    assert summary["survivorship_inherited_from_fnd2"] is True


def _synthetic_panel_with_dead_symbol(n_days=120, dead_alive_to_idx=60):
    """建 synthetic multiday Panel：BTCUSDT 全窗存活；DEADUSDT 價格全窗有、但中途 delist。

    DEADUSDT 的 panel.survivorship（listed_at-only 模擬）刻意全 True（價格全有）→ 用來
    證明：唯有套 FND-2 alive_mask 的 alive_to 上界才能讓 delist 後 surv=False。
    """
    import datetime as _dt
    import numpy as _np
    from multiday_trend_diagnostic.data_loader import Panel

    base = _dt.date(2024, 6, 3)
    dates = [base + _dt.timedelta(days=i) for i in range(n_days)]
    # 簡單上升+雜訊（確定性 seed），讓 TSMOM 有可算觀測。
    rng = _np.random.default_rng(42)
    btc = 100.0 * _np.cumprod(1.0 + 0.001 + 0.01 * rng.standard_normal(n_days))
    dead = 50.0 * _np.cumprod(1.0 + 0.0005 + 0.01 * rng.standard_normal(n_days))
    close = {"BTCUSDT": btc, "DEADUSDT": dead}
    # listed_at-only survivorship：兩者全 True（價格全有；無 delist 上界）。
    surv = {"BTCUSDT": _np.ones(n_days, dtype=bool), "DEADUSDT": _np.ones(n_days, dtype=bool)}
    empty = {s: _np.full(n_days, _np.nan) for s in close}
    return Panel(
        dates=dates, close=close, open_=dict(empty), high=dict(empty), low=dict(empty),
        volume=dict(empty), survivorship=surv, regime=_np.array(["chop"] * n_days, dtype=object),
        funding_mean_per_8h={s: 0.0 for s in close}, coverage_notes={},
    ), dates, dead_alive_to_idx


def test_high1_adapter_clamps_dead_symbol_zero_holdings_after_delist():
    """★ HIGH-1 核心：真 adapter 用 alive_mask 把 DEADUSDT 在 delist 後持倉 clip 成 0。

    panel.survivorship[DEADUSDT] 全 True（listed_at-only 無上界）；FND-2 alive_mask 給
    alive_to=date[60]。斷言：
      (1) adapter 的 clamped survivorship 在 delist 後（date>alive_to）全 False；
      (2) 用 clamped survivorship 跑 tsmom，DEADUSDT 在 delist 後的進場觀測=0
          （持倉=0 / 0 PnL 貢獻）；對照 listed_at-only 會有 >0 後段觀測（證 clamp 有 bite）。
    """
    import datetime as _dt
    import numpy as _np
    from aeg_breadth_ladder.evaluator import MultidayTrendReferenceEvaluator
    from multiday_trend_diagnostic import stats

    panel, dates, dead_idx = _synthetic_panel_with_dead_symbol(n_days=120, dead_alive_to_idx=60)
    alive_to = dates[dead_idx]
    alive_mask = {
        "BTCUSDT": (None, None),
        "DEADUSDT": (
            _dt.datetime(2024, 6, 3, tzinfo=_dt.timezone.utc),
            _dt.datetime(alive_to.year, alive_to.month, alive_to.day, tzinfo=_dt.timezone.utc),
        ),
    }
    ev = MultidayTrendReferenceEvaluator(panel, k=10)
    tier_syms = ("BTCUSDT", "DEADUSDT")
    clamped = ev._clamped_survivorship(tier_syms, alive_mask, panel)

    # (1) DEADUSDT delist 後全 False。
    dead_surv = clamped["DEADUSDT"]
    for i, d in enumerate(dates):
        if d > alive_to:
            assert not dead_surv[i], f"DEADUSDT 在 delist 後 date={d} 仍標存活（未 clip）"
    # delist 前仍有存活日（不是全砍）。
    assert dead_surv[: dead_idx + 1].any()

    # (2) 用 clamped survivorship 跑 tsmom：DEADUSDT delist 後進場觀測=0。
    k = 10
    dead_close = _np.asarray(panel.close["DEADUSDT"], dtype=float)
    n = len(dead_close)

    def _post_delist_entries(surv_arr):
        cnt = 0
        for t in range(k + 1, n - k):
            if t <= dead_idx:
                continue  # 只數 delist 後的進場日
            if surv_arr is not None and (not surv_arr[t] or not surv_arr[t + k]):
                continue
            cnt += 1
        return cnt

    # clamped → delist 後 0 進場（0 持倉 / 0 PnL 貢獻）。
    assert _post_delist_entries(clamped["DEADUSDT"]) == 0
    # 對照 listed_at-only（panel 原值，全 True）→ delist 後有 >0 進場（證 clamp 真有 bite）。
    assert _post_delist_entries(panel.survivorship["DEADUSDT"]) > 0

    # 整段 tsmom 觀測數：clamped < listed_at-only（dead symbol 後段被砍）。
    surv_clamped = {"DEADUSDT": clamped["DEADUSDT"]}
    surv_naive = {"DEADUSDT": panel.survivorship["DEADUSDT"]}
    close_only_dead = {"DEADUSDT": panel.close["DEADUSDT"]}
    t_clamped = stats.tsmom_significance(close_only_dead, surv_clamped, k)
    t_naive = stats.tsmom_significance(close_only_dead, surv_naive, k)
    assert t_clamped["n_obs"] < t_naive["n_obs"], (t_clamped["n_obs"], t_naive["n_obs"])

    # adapter.evaluate 端到端：full tier 自證 mask_applied + delisted_clipped_count>=1。
    tr = ev.evaluate(tier="full_survivorship", universe=tier_syms, alive_mask=alive_mask)
    assert tr.survivorship_mask_applied is True
    assert tr.notes.get("delisted_clipped_count", 0) >= 1


def test_high1_count_seen_delisted_real_uses_alive_mask():
    """★ _count_seen_delisted 真用 alive_mask 數 delist-after-clip（非佔位 0）。"""
    import datetime as _dt
    from aeg_breadth_ladder.evaluator import MultidayTrendReferenceEvaluator

    panel, dates, dead_idx = _synthetic_panel_with_dead_symbol(n_days=120, dead_alive_to_idx=60)
    alive_to = dates[dead_idx]
    alive_mask = {
        "BTCUSDT": (None, None),  # 仍上市（alive_to=None）→ 不算 delist
        "DEADUSDT": (None, _dt.datetime(alive_to.year, alive_to.month, alive_to.day,
                                        tzinfo=_dt.timezone.utc)),
    }
    ev = MultidayTrendReferenceEvaluator(panel, k=10)
    # DEADUSDT alive_to 早於 panel 末日 → 計 1；BTCUSDT alive_to=None → 不計。
    assert ev._count_seen_delisted(("BTCUSDT", "DEADUSDT"), alive_mask, panel) == 1
    assert ev._count_seen_delisted(("BTCUSDT",), alive_mask, panel) == 0


def test_high1_harness_healthcheck_gate_raises_on_non_inheriting(tmp_path):
    """★ healthcheck wiring load-bearing：run_ladder 對非繼承 adapter raise（非 silent-dead）。"""
    fnd2_dir = tmp_path / "fnd2_run"
    fnd2_dir.mkdir()
    import csv as _csv
    cols = ua_mod._REQUIRED_FND2_COLUMNS + ("universe_id",)
    with open(fnd2_dir / "universe.csv", "w", encoding="utf-8", newline="") as fh:
        w = _csv.writer(fh)
        w.writerow(list(cols))
        w.writerow(["BTCUSDT", '["full_survivorship","core25_pinned"]', "true",
                    "2024-06-03T00:00:00+00:00", "2026-06-03T00:00:00+00:00", "false",
                    "core25_pinned", "false", "uid_g"])
        w.writerow(["DEADUSDT", '["full_survivorship","historical_delisted"]', "true",
                    "2024-07-03T00:00:00+00:00", "2025-01-01T00:00:00+00:00", "true",
                    "full_survivorship", "false", "uid_g"])
    (fnd2_dir / "universe_summary.json").write_text(json.dumps({
        "universe_id": "uid_g", "run_id": "fnd2_run_g", "survivor_rejection_status": "PASS",
    }), encoding="utf-8")

    bad = _NonInheritingEvaluator({
        tiers_mod.TIER_CORE25_PINNED: _tr("core25_pinned", breadth=0, net_bps=10.0, n_independent=40),
        tiers_mod.TIER_TOP_LIQUIDITY_40_50: _tr("top_liquidity_40_50", breadth=0, net_bps=9.0,
                                                n_independent=40),
        tiers_mod.TIER_FULL_SURVIVORSHIP: _tr("full_survivorship", breadth=0, net_bps=8.0,
                                              n_independent=40),
    })

    class _Args:
        run_id = "breadth_gate"
        fnd2_run_dir = str(fnd2_dir)
        asof = "2026-06-03T00:00:00Z"
        window_start = "2024-06-03T00:00:00Z"
        window_end = "2026-06-03T00:00:00Z"
        artifact_root = str(tmp_path / "out")
        session_id = None
        created_by_role = "E1"

    with pytest.raises(RuntimeError) as ei:
        run_ladder(_Args(), evaluator=bad)
    assert "healthcheck FAIL" in str(ei.value)


def test_nit_fmt_num_negative_zero_normalized():
    """NIT：_fmt_num(-0.0) 正規化為 '0'（signed-zero determinism）。"""
    assert ladder_mod._fmt_num(-0.0) == "0"
    assert ladder_mod._fmt_num(0.0) == "0"
    # -0.0 與 0.0 進 digest 一致（不因 signed-zero 漂移）。
    assert ladder_mod._canonical_cell(-0.0) == ladder_mod._canonical_cell(0.0)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
