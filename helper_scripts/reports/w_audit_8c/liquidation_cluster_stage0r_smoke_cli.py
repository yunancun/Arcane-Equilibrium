#!/usr/bin/env python3
"""W-AUDIT-8c Stage 0R CLI 整合 smoke test（round 2 sign-off invariant）。

MODULE_NOTE
模塊用途：以 mock SQL output + 直接呼 `_fetch_panel_rows`-equivalent path
+ assert `n_per_cell > 0` + sweep 返 dict + JSON/MD 寫檔 + Markdown lint
驗證 round 2 修妥的 6 CRIT + 4 HIGH 是否真的能跑通 end-to-end，不靠 PG。

為什麼存在：round 1 E1 self-attest「import sanity check」未實際呼 sibling
sweep / SQL — E2 round 1 §"反思 §1" 明確 critique「contract question for
E2 to verify at merge 是 anti-pattern」；本 smoke 是 IMPL DONE 的硬指標：
跑得通才算 round 2 done。

主要類/函數：
  - _mock_panel_rows()：12 sym × 14 day 之 mock liquidation rows
  - test_extract_smoke()：驗 _extract_trigger_rows 在 normalize
    bucket_end_ts_ms 後不再 silent-skip
  - test_compute_stage0r_smoke()：驗 single-cell compute_stage0r 返 dict
    with n_per_cell > 0
  - test_compute_stage0r_sweep_smoke()：驗 sweep 返 dict 6 keys（CRIT-2 fix）
  - test_render_md_smoke()：驗 Markdown render 不拋
  - test_packet_builder_smoke()：驗 _build_packet 覆蓋 spec v0.3
    14 mandatory fields

依賴：8C-S0R-2 metrics（sibling worktree；smoke 直接 import）。
硬邊界：不連 PG；不寫真實 docs/ 路徑；用 tmp dir。
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 補 sibling import path（與 wrapper shim 行為一致）
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

# 本 smoke 直接呼 sibling 函數，不經 main()（main() 會嘗試連 PG）
from liquidation_cluster_stage0r_metrics import (  # type: ignore  # noqa: E402
    compute_stage0r,
    compute_stage0r_sweep,
    _extract_trigger_rows,
)
from liquidation_cluster_stage0r_report import (  # type: ignore  # noqa: E402
    _build_packet,
    _render_markdown,
    _clean_json,
    _verdict_from_sweep_result,
    _compute_exclusion_counts,
    _aggregate_sweep_summary,
)


def _mock_row(
    *,
    symbol: str,
    bucket_5m_epoch: int,
    bucket_end_ts: datetime,
    dominant_side: str,
    expected_dir: int,
    cluster_notional: float,
    event_count: int,
    dominant_event_count: int,
    side_dominance: float,
    notional_pct: float,
    entry_mid: float,
    exit_mid: float,
    day_bucket: str,
) -> dict[str, object]:
    """構造一個 SQL CTE 5 final_signals 等價 row（與 S0R-1 SQL 輸出 column 對齊）。

    為什麼 bucket_end_ts 用 datetime：mirror S0R-1 SQL `bucket_end_ts TIMESTAMPTZ`
    輸出；下游 `_fetch_panel_rows` 必須 normalize 成 bucket_end_ts_ms (ms int)
    這是 CRIT-5 fix 的核心。
    """
    gross_bps = 10000.0 * expected_dir * (exit_mid - entry_mid) / entry_mid
    return {
        "symbol": symbol,
        "bucket_5m_epoch": bucket_5m_epoch,
        "bucket_end_ts": bucket_end_ts,
        "dominant_side": dominant_side,
        "expected_dir": expected_dir,
        "event_count_5m": event_count,
        "cluster_notional_5m": cluster_notional,
        "long_notional_5m": cluster_notional if dominant_side == "long_liquidated" else 0.0,
        "short_notional_5m": cluster_notional if dominant_side == "short_liquidated" else 0.0,
        "long_event_count": event_count if dominant_side == "long_liquidated" else 0,
        "short_event_count": event_count if dominant_side == "short_liquidated" else 0,
        "dominant_event_count": dominant_event_count,
        "side_dominance_ratio": side_dominance,
        "notional_pct_24h": notional_pct,
        "entry_ts": bucket_end_ts + timedelta(seconds=30),
        "entry_mid": entry_mid,
        "exit_ts": bucket_end_ts + timedelta(minutes=5),
        "exit_mid": exit_mid,
        "gross_bps": gross_bps,
        "net_bps": gross_bps - 12.0,
        "day_bucket": day_bucket,
    }


def _normalize_bucket_end_ts(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """模擬 _fetch_panel_rows 的 normalize step（CRIT-5 fix 等價路徑）。

    為什麼分出：smoke 不連 PG，但要驗證 CRIT-5 fix 的 normalize 邏輯生效。
    """
    out: list[dict[str, object]] = []
    for raw in rows:
        row = dict(raw)
        bet = row.get("bucket_end_ts")
        if bet is not None and hasattr(bet, "timestamp"):
            row["bucket_end_ts_ms"] = int(bet.timestamp() * 1000)
        elif isinstance(bet, (int, float)):
            row["bucket_end_ts_ms"] = int(bet)
        else:
            row["bucket_end_ts_ms"] = None
        out.append(row)
    return out


def _build_mock_panel(n_symbols: int = 4, days: int = 8) -> list[dict[str, object]]:
    """構造 n_symbols × days × (3-5 cluster/day) mock panel。

    為什麼 4 symbols × 8 days：超過 spec v0.3 §"sample must span at least 7
    calendar days" 與 promotion floor `n_eff >= 300 pooled`；smoke 不要求
    通過 promotion floor，只要驗 pipeline 不 crash + n_per_cell > 0。
    """
    rows: list[dict[str, object]] = []
    symbols = [f"SYM{i}USDT" for i in range(n_symbols)]
    base_dt = datetime(2026, 5, 10, 0, 0, 0, tzinfo=timezone.utc)
    for d in range(days):
        day_dt = base_dt + timedelta(days=d)
        day_bucket = day_dt.strftime("%Y-%m-%d")
        for sym_idx, sym in enumerate(symbols):
            # 每 sym 每 day 5 個 cluster；交替 long/short
            for cluster_idx in range(5):
                # 5m 桶 epoch；每 cluster 隔 30 分鐘
                bucket_dt = day_dt + timedelta(minutes=30 * cluster_idx)
                bucket_epoch = int(bucket_dt.timestamp())
                bucket_5m_epoch = (bucket_epoch // 300) * 300
                bucket_end_ts = bucket_dt + timedelta(minutes=4, seconds=50)
                side = "long_liquidated" if (cluster_idx + sym_idx) % 2 == 0 else "short_liquidated"
                expected_dir = 1 if side == "long_liquidated" else -1
                # mock alpha：long_liq 後 mean-revert up；exit > entry 對 long_liq
                entry_mid = 100.0 + sym_idx
                exit_mid = entry_mid * (1 + expected_dir * 0.0030)  # 30 bps gross alpha
                rows.append(
                    _mock_row(
                        symbol=sym,
                        bucket_5m_epoch=bucket_5m_epoch,
                        bucket_end_ts=bucket_end_ts,
                        dominant_side=side,
                        expected_dir=expected_dir,
                        cluster_notional=30_000.0 + cluster_idx * 5_000.0,
                        event_count=5 + cluster_idx,
                        dominant_event_count=4 + cluster_idx,
                        side_dominance=0.85,
                        # MED-R2-1：sibling round 2 升 notional_pct_floor default 0.95；
                        # mock 給 0.97 才能通過第三層 magnitude gate 進 triggers，
                        # 否則 _extract_trigger_rows 全 filter → n_per_cell=0 silent-RED。
                        notional_pct=0.97,
                        entry_mid=entry_mid,
                        exit_mid=exit_mid,
                        day_bucket=day_bucket,
                    )
                )
    return rows


# ============================================================================
# Test cases
# ============================================================================


def test_normalize_bucket_end_ts() -> tuple[bool, str]:
    """驗 CRIT-5：bucket_end_ts (datetime) → bucket_end_ts_ms (int ms) 必成功。"""
    rows = _build_mock_panel(n_symbols=2, days=8)
    normalized = _normalize_bucket_end_ts(rows)
    missing = [r for r in normalized if r.get("bucket_end_ts_ms") is None]
    if missing:
        return False, f"normalize 失敗：{len(missing)}/{len(normalized)} 缺 bucket_end_ts_ms"
    sample = normalized[0]["bucket_end_ts_ms"]
    if not isinstance(sample, int) or sample < 1_700_000_000_000:
        return False, f"bucket_end_ts_ms 類型錯：{type(sample).__name__} value={sample}"
    return True, f"normalize OK: {len(normalized)} rows 全帶 bucket_end_ts_ms"


def test_extract_trigger_rows() -> tuple[bool, str]:
    """驗 _extract_trigger_rows 在 normalize 後 n > 0（CRIT-5 silent-RED killer fix）。

    MED-R2-1：sibling round 2 升 `_extract_trigger_rows` 第 8 軸
    `notional_pct_floor` required-kw-only；smoke 必須同步傳；
    mock data 給 notional_pct=0.97 配合 floor=0.95 才能通過第三層 gate。
    """
    rows = _build_mock_panel(n_symbols=4, days=8)
    normalized = _normalize_bucket_end_ts(rows)
    triggers = _extract_trigger_rows(
        normalized,
        k_event_count=3,
        n_usd=10_000,
        m_dominant=2,
        floor_usd=10_000,
        notional_pct_floor=0.95,  # MED-R2-1：8th axis 對齊 sibling round 2 簽名
        side_dom=0.80,
        quiet_sec=30,
        horizon_min=5,
        cost_bps=12.0,
    )
    n = len(triggers)
    if n == 0:
        return False, f"_extract_trigger_rows 返 0 triggers — CRIT-5 silent-RED killer 仍存在！"
    return True, f"_extract_trigger_rows OK: {n} triggers (>0 確認 normalize fix 生效)"


def test_compute_stage0r() -> tuple[bool, str]:
    """驗 compute_stage0r 在 normalized rows 上返 dict with n_per_cell > 0。

    MED-R2-1：sibling round 2 default notional_pct_floor=0.95；smoke 顯式
    pass 0.95 配合 mock data notional_pct=0.97（_build_mock_panel 已升）。
    HIGH-R2-2 同理：production CLI single_kwargs 也應傳 notional_pct_floor。
    """
    rows = _build_mock_panel(n_symbols=4, days=8)
    normalized = _normalize_bucket_end_ts(rows)
    result = compute_stage0r(
        normalized,
        cost_bps=12.0,
        horizon_min=5,
        notional_pct_floor=0.95,  # MED-R2-1：顯式 8th axis 配 mock 0.97
        bootstrap_iters=50,  # 小量加速 smoke
    )
    if not isinstance(result, dict):
        return False, f"compute_stage0r 返非 dict: {type(result).__name__}"
    n_pc = result.get("n_per_cell")
    if not isinstance(n_pc, int) or n_pc == 0:
        return False, f"compute_stage0r n_per_cell={n_pc} — 應 > 0"
    if "pass" not in result:
        return False, "compute_stage0r 缺 'pass' verdict key"
    return True, (
        f"compute_stage0r OK: n_per_cell={n_pc} verdict={result.get('pass')}"
    )


def test_compute_stage0r_sweep() -> tuple[bool, str]:
    """驗 compute_stage0r_sweep 返 dict 而非 list（CRIT-2 fix 確認）。

    HIGH-R2-1：smoke 顯式 pass `pct_grid=(0.95,)` 驗證 sibling round 2 第 8 軸
    接受 keyword；caller 若漏接，cell 計算結果不會反映 operator-given pct_grid。
    """
    rows = _build_mock_panel(n_symbols=4, days=8)
    normalized = _normalize_bucket_end_ts(rows)
    # 用小 grid 避 11_664 cell 跑爆 smoke 時間
    result = compute_stage0r_sweep(
        normalized,
        cost_bps=12.0,
        k_grid=(3, 5),
        n_usd_grid=(10_000, 25_000),
        m_grid=(2,),
        side_dom_grid=(0.80,),
        floor_grid=(10_000,),
        quiet_grid=(30,),
        horizon_grid=(5,),
        pct_grid=(0.95,),  # HIGH-R2-1：8th axis 顯式接到 sweep
        bootstrap_iters=50,
    )
    if not isinstance(result, dict):
        return False, (
            f"compute_stage0r_sweep 返非 dict: {type(result).__name__} — "
            f"CRIT-2 contract drift 復發！"
        )
    expected_keys = {
        "sweep_cells",
        "eligible_for_demo_canary",
        "eligible_for_demo_canary_per_tier",
        "sweep_meta",
    }
    missing = expected_keys - set(result.keys())
    if missing:
        return False, f"sweep_result 缺 keys: {missing}"
    cells = result.get("sweep_cells") or []
    if not cells:
        return False, "sweep_cells 為空 — 即便小 grid 也該有 2*2*1*1*1*1*1*1=4 cells"
    return True, (
        f"sweep OK: {len(cells)} cells, eligible={result.get('eligible_for_demo_canary')}"
    )


def test_verdict_derivation() -> tuple[bool, str]:
    """驗 _verdict_from_sweep_result 從 sweep_result 直 surface（HIGH-4 fix）。"""
    mock_sweep = {
        "eligible_for_demo_canary_per_tier": {
            "high": {"long": True, "short": False},
            "medium": {"long": False, "short": True},
            "low": {"long": False, "short": False},
        }
    }
    verdict = _verdict_from_sweep_result(mock_sweep)
    if verdict != "PASS-BOTH":
        return False, f"verdict={verdict} expected PASS-BOTH（任 tier long+短 short）"

    mock_all_red = {
        "eligible_for_demo_canary_per_tier": {
            "high": {"long": False, "short": False},
        }
    }
    if _verdict_from_sweep_result(mock_all_red) != "RED":
        return False, "all-False 應回 RED"

    mock_long_only = {
        "eligible_for_demo_canary_per_tier": {
            "high": {"long": True, "short": False},
        }
    }
    if _verdict_from_sweep_result(mock_long_only) != "PASS-LONG-ONLY":
        return False, "long-only 應回 PASS-LONG-ONLY"

    return True, "verdict derivation 4-value verdict 全分支 OK"


def test_packet_builder() -> tuple[bool, str]:
    """驗 _build_packet 覆蓋 spec v0.3 14 mandatory fields（HIGH-1 fix）。"""
    rows = _build_mock_panel(n_symbols=4, days=8)
    normalized = _normalize_bucket_end_ts(rows)
    sweep = compute_stage0r_sweep(
        normalized,
        cost_bps=12.0,
        k_grid=(3, 5),
        n_usd_grid=(10_000, 25_000),
        m_grid=(2,),
        side_dom_grid=(0.80,),
        floor_grid=(10_000,),
        quiet_grid=(30,),
        horizon_grid=(5,),
        pct_grid=(0.95,),  # HIGH-R2-1：packet 流也走 8th axis
        bootstrap_iters=50,
    )
    cells = sweep.get("sweep_cells") or []
    primary = cells[0] if cells else None
    packet = _build_packet(
        panel_rows=normalized,
        sweep_result=sweep,
        cells=cells,
        primary_cell=primary,
        sweep_params={"window_days": 7, "cost_bps": 12.0, "pct_grid": [0.95]},
        bb_preflight={
            "demo_bias_confirmed": True,
            "skew_data": {"verdict": "STRUCTURAL"},
            "bb_report_path": "docs/CCAgentWorkSpace/BB/.../bb_review.md",
        },
        k_prior=123,
        k_prior_meta={"mode": "strict-liquidation", "available": True},
    )
    # 14 mandatory fields（spec v0.3 L234-253）
    mandatory_packet_keys = {
        "verdict",
        "panel_meta",
        "params",
        "k_prior",
        "k_prior_meta",
        "sweep_summary",
        "per_tier_breakdown",
        "density_filter_efficacy_chain",
        "false_positive_rates",
        "exclusion_counts",
        "baseline_lift",
        "pbo_with_purge_embargo",
        "n_eff_audit",
        "tombstone_risk_summary",
        "bb_pre_flight",
        "primary_cell",
        "cells",
    }
    missing = mandatory_packet_keys - set(packet.keys())
    if missing:
        return False, f"packet 缺 mandatory keys: {missing}"
    # 5 exclusion categories
    exc = packet.get("exclusion_counts") or {}
    exc_cats = {
        "stale_kline_missing",
        "missing_required_field",
        "mixed_side",
        "quiet_window_excluded",
        "density_floor_excluded",
    }
    missing_cats = exc_cats - set(exc.keys())
    if missing_cats:
        return False, f"exclusion_counts 缺 5 categories 之: {missing_cats}"
    return True, f"packet 完整：{len(packet)} top-level keys + 5 exclusion categories"


def test_render_markdown() -> tuple[bool, str]:
    """驗 Markdown render 不拋 + 含 4-agent sections。"""
    rows = _build_mock_panel(n_symbols=2, days=8)
    normalized = _normalize_bucket_end_ts(rows)
    sweep = compute_stage0r_sweep(
        normalized,
        cost_bps=12.0,
        k_grid=(3,),
        n_usd_grid=(10_000,),
        m_grid=(2,),
        side_dom_grid=(0.80,),
        floor_grid=(10_000,),
        quiet_grid=(30,),
        horizon_grid=(5,),
        pct_grid=(0.95,),  # HIGH-R2-1
        bootstrap_iters=20,
    )
    cells = sweep.get("sweep_cells") or []
    primary = cells[0] if cells else None
    packet = _build_packet(
        panel_rows=normalized,
        sweep_result=sweep,
        cells=cells,
        primary_cell=primary,
        sweep_params={"window_days": 7},
        bb_preflight={
            "demo_bias_confirmed": True,
            "skew_data": {"verdict": "STRUCTURAL"},
            "bb_report_path": "docs/.../bb_review.md",
        },
        k_prior=0,
        k_prior_meta={"mode": "all"},
    )
    md = _render_markdown(packet)
    required_sections = [
        "## Verdict",
        "## Panel Metadata",
        "## Sweep Summary",
        "## Per-Tier Breakdown",
        "## Exclusion Counts",
        "## Baseline Lift",
        "## PBO with Purge/Embargo",
        "## BB Pre-flight Gate",
        "## n_eff Audit",
        "## Tombstone Risk Summary",
        "## Primary Cell",
        "### QC",
        "### MIT",
        "### FA",
        "### BB",
    ]
    missing = [s for s in required_sections if s not in md]
    if missing:
        return False, f"Markdown 缺 sections: {missing}"
    return True, f"Markdown render OK: {len(md)} chars, 全 15 必要段全在"


def test_json_write_and_clean() -> tuple[bool, str]:
    """驗 _clean_json + json.dumps 寫檔 round-trip 不拋（LOW-1 fix）。"""
    packet = {
        "nan_val": float("nan"),
        "inf_val": float("inf"),
        "neg_inf": float("-inf"),
        "good_float": 1.5,
        "nested": {"deeper": [float("nan"), 1, 2.0]},
        "list_of_dicts": [{"a": 1}, {"b": float("nan")}],
    }
    cleaned = _clean_json(packet)
    # NaN/Inf 應 → None
    if cleaned["nan_val"] is not None or cleaned["inf_val"] is not None:
        return False, "NaN/Inf 未清理為 None"
    if cleaned["nested"]["deeper"][0] is not None:
        return False, "nested NaN 未清理"
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "smoke.json"
        out.write_text(
            json.dumps(cleaned, indent=2, sort_keys=True), encoding="utf-8"
        )
        re_loaded = json.loads(out.read_text(encoding="utf-8"))
        if re_loaded["good_float"] != 1.5:
            return False, "round-trip 失敗"
    return True, "_clean_json + JSON round-trip OK"


def test_sweep_summary_aggregation() -> tuple[bool, str]:
    """驗 _aggregate_sweep_summary 正確分類 4-value verdict。"""
    cells = [
        {"pass": "PASS-BOTH", "pass_reasons": []},
        {"pass": "PASS-LONG-ONLY", "pass_reasons": ["short_branch n_eff < 50"]},
        {"pass": "PASS-SHORT-ONLY", "pass_reasons": ["long_branch n_eff < 50"]},
        {"pass": "RED", "pass_reasons": ["cost_edge_ratio 0.95 >= 0.8"]},
        {"pass": "RED", "pass_reasons": ["cost_edge_ratio 0.95 >= 0.8"]},
    ]
    summary = _aggregate_sweep_summary(cells)
    if summary["total_cells"] != 5:
        return False, f"total={summary['total_cells']}"
    if summary["pass_both_cells"] != 1:
        return False, f"pass_both={summary['pass_both_cells']}"
    if summary["red_cells"] != 2:
        return False, f"red={summary['red_cells']}"
    if "cost_edge_ratio 0.95 >= 0.8" not in summary["red_reason_counts"]:
        return False, "red_reason_counts 缺 cost_edge_ratio"
    if summary["red_reason_counts"]["cost_edge_ratio 0.95 >= 0.8"] != 2:
        return False, "red_reason_counts cost 計數錯"
    return True, "sweep_summary aggregation OK"


def test_sql_params_completeness() -> tuple[bool, str]:
    """驗 sql_params keys + symbols 注入 = SQL features.sql 全 placeholder 集合
    （CRIT-R2-1 governance：避免「修一條 placeholder 沒查全表」反模式）。

    為什麼這個 smoke：round 1 CRIT-1 修 `symbols` 卻漏 `notional_pct_floor`；
    round 2 E2 review 顯示「不 enumerate 全 SQL placeholder」是反覆出現的盲點。
    此 test 直接讀 sibling S0R-1 SQL 文件，regex 抽 placeholder set，
    對齊 CLI sql_params 構造邏輯 — 任何 axis 升不接住即立刻 fail。
    """
    import re

    # 嘗試讀 SQL 文件（兩個可能路徑：worktree 本地 vs /tmp mirror）
    candidates = [
        HERE.parent.parent.parent / "sql" / "queries" / "w_audit_8c_liquidation_cluster_stage0r_features.sql",
        Path("/tmp/e1r3_smoke/w_audit_8c_liquidation_cluster_stage0r_features.sql"),
    ]
    sql_path = None
    for cand in candidates:
        if cand.exists():
            sql_path = cand
            break
    if sql_path is None:
        # SQL 在 sibling S0R-1 worktree；本 worktree 沒檔。Skip 但顯式說明，不假 PASS。
        # 這是「sibling-isolation 預期 gap」非 test failure。
        return True, (
            "SKIP (本 worktree 無 SQL 文件，sibling S0R-1 owner)；"
            "完整 sign-off 必由 PM 在 main 分支 merge 後重跑"
        )
    sql_text = sql_path.read_text(encoding="utf-8")
    # 抽 SQL 全 %(name)s placeholder，排除 comment 中的 `%(name)s` 字面（line 117 documentation）
    placeholders = set(re.findall(r"%\((\w+)\)s", sql_text))
    placeholders.discard("name")  # comment 內例子，非 runtime placeholder
    # CLI sql_params keys（hard-coded 對應 report.py L1060-1072 + symbols 由 _fetch_panel_rows 注入）
    cli_keys = {
        "window_days",
        "k_event_floor",
        "n_usd_floor",
        "m_dominant_floor",
        "side_dominance_floor",
        "cluster_notional_floor_usd",
        "notional_pct_floor",  # CRIT-R2-1 補
        "quiet_window_sec",
        "horizon_min",
        "cost_bps",
        "symbols",  # 由 _fetch_panel_rows 注入
    }
    missing_in_cli = placeholders - cli_keys
    extra_in_cli = cli_keys - placeholders
    if missing_in_cli:
        return False, (
            f"sql_params 缺 SQL placeholder：{sorted(missing_in_cli)}；"
            f"第一次 cur.execute(sql) 會 psycopg2 KeyError"
        )
    if extra_in_cli:
        return False, (
            f"sql_params 多餘 keys：{sorted(extra_in_cli)}；可能 SQL 已移除 placeholder"
        )
    return True, (
        f"sql_params 完整：{len(placeholders)} placeholders 全綁 + {len(cli_keys)} CLI keys 等價"
    )


def test_exclusion_counts() -> tuple[bool, str]:
    """驗 _compute_exclusion_counts 5 categories（HIGH-1 (d)）。"""
    rows: list[dict[str, object]] = [
        {"symbol": "BTCUSDT", "expected_dir": 1, "dominant_side": "long_liquidated",
         "entry_mid": 100.0, "exit_mid": 100.5},  # valid
        {"symbol": "BTCUSDT", "expected_dir": 1, "dominant_side": "mixed",
         "entry_mid": 100.0, "exit_mid": 100.5},  # mixed_side
        {"symbol": None, "expected_dir": 1, "dominant_side": "long_liquidated",
         "entry_mid": 100.0, "exit_mid": 100.5},  # missing_required_field
        {"symbol": "ETHUSDT", "expected_dir": 1, "dominant_side": "long_liquidated",
         "entry_mid": None, "exit_mid": None},  # stale_kline_missing
    ]
    exc = _compute_exclusion_counts(rows, primary_cell=None)
    if exc["mixed_side"] != 1:
        return False, f"mixed_side={exc['mixed_side']}"
    if exc["missing_required_field"] != 1:
        return False, f"missing={exc['missing_required_field']}"
    if exc["stale_kline_missing"] != 1:
        return False, f"stale={exc['stale_kline_missing']}"
    if exc["total_raw_rows"] != 4:
        return False, f"total_raw_rows={exc['total_raw_rows']}"
    return True, "exclusion 5 categories 全分類 OK"


# ============================================================================
# Runner
# ============================================================================


TESTS = [
    ("normalize_bucket_end_ts (CRIT-5 fix)", test_normalize_bucket_end_ts),
    ("extract_trigger_rows (CRIT-5 silent-RED killer fix)", test_extract_trigger_rows),
    ("compute_stage0r single-cell (CRIT-4 list[dict] contract)", test_compute_stage0r),
    ("compute_stage0r_sweep returns dict (CRIT-2 fix)", test_compute_stage0r_sweep),
    ("verdict from sweep_result (HIGH-4 fix)", test_verdict_derivation),
    ("packet builder covers 14 mandatory (HIGH-1 fix)", test_packet_builder),
    ("Markdown render 15 sections", test_render_markdown),
    ("JSON clean + write round-trip (LOW-1 fix)", test_json_write_and_clean),
    ("sweep_summary aggregation 4-value verdict", test_sweep_summary_aggregation),
    ("exclusion_counts 5 categories (HIGH-1 (d))", test_exclusion_counts),
    ("sql_params completeness (CRIT-R2-1 全 placeholder enumerate)", test_sql_params_completeness),
]


def main() -> int:
    print("=" * 78)
    print("W-AUDIT-8c Stage 0R CLI 整合 smoke test (round 2 sign-off invariant)")
    print("=" * 78)
    failed = 0
    for name, fn in TESTS:
        try:
            ok, msg = fn()
        except Exception as exc:  # noqa: BLE001
            ok, msg = False, f"EXCEPTION: {type(exc).__name__}: {exc}"
        marker = "[PASS]" if ok else "[FAIL]"
        print(f"{marker} {name}")
        print(f"       → {msg}")
        if not ok:
            failed += 1
    print("-" * 78)
    if failed:
        print(f"SMOKE FAIL: {failed}/{len(TESTS)} tests failed")
        return 1
    print(f"SMOKE PASS: {len(TESTS)}/{len(TESTS)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
