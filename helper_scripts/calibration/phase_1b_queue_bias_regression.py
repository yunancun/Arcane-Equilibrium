"""
MODULE_NOTE
模塊用途：Historical regression CLI — 驗 P2-SIM-QUEUE-AWARE-ADJUSTMENT v55 bias 修正
是否真實降低 sweep proxy 與 actual fill rate 的 gap。

設計：
  1. 從 V094 trading.fills 拉 14d 內 close_maker_attempt=TRUE 樣本（含 actual maker
     vs taker fallback 標籤）作 ground truth；
  2. 對每 fill 做兩種 simulation：
     (a) original BBO-cross-proxy（queue_weight=0 / orderbook_windows=None）；
     (b) queue-aware adjusted（queue_weight=0.40 默認 / orderbook_windows=有 depth）；
  3. 對比三個 fill rate：
     - actual_fill_rate = liquidity_role='maker' 數 / total attempts；
     - sweep_proxy_fill_rate = sum(simulated_fill) / n_eligible；
     - sweep_adjusted_fill_rate = sum(queue_adjusted_fill_probability) / n_eligible；
  4. 計算 bias_before（proxy vs actual）vs bias_after（adjusted vs actual），
     驗 |bias_after| ≤ 5pp 判定 verdict PASS/FAIL；
  5. 也對 queue_weight ∈ [0.10, 0.20, 0.30, 0.40, 0.50, 0.60] sweep 找最佳 weight。

⚠️ 適用範圍 disclaimers（per E2 review 2026-05-20）：
  - MEDIUM-1: `base_rejection_rate` 是 **family-specific empirical anchor** —
    結論限 ANCHOR_CELL 對應 family（grid_close_*）；其他 family 需用對應
    anchor cell 重跑（如 PG-AB-01-C15 / PS-AB-01-C10）。
  - MEDIUM-2: 預設 `--sample-end-utc=now()` 是 sliding window，每次跑會抓不同
    sample；audit 時刻對齊請顯式 pass `--sample-end-utc YYYY-MM-DDThh:mm:ss+00:00`
    可 bit-exact 重現；JSON artifact 紀錄 `sample_window_start_utc` /
    `sample_window_end_utc` / `sample_window_pinned`。

主要函數：load_v094_attempts / run_regression / print_results / find_best_params。

依賴：phase_1b_sweep_replay / phase_1b_tick_loader / phase_1b_queue_adjustment / psycopg2。

硬邊界：read-only PG；無 IPC；無 trading side effect；JSON 輸出可選；
        每 cell 對齊單一 baseline cell（G-AB-01-C90 grid 預設，per Phase 2a deploy）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_1b_queue_adjustment import (  # noqa: E402
    DEFAULT_BASE_REJECTION_RATE,
    DEFAULT_QUEUE_WEIGHT,
)
from phase_1b_sweep_cells import CalibrationCell  # noqa: E402
from phase_1b_sweep_replay import (  # noqa: E402
    simulate_cell,
    load_all_tick_windows,
    load_all_orderbook_windows,
)
from phase_1b_tick_loader import (  # noqa: E402
    FillReplaySeed,
    load_tick_size_map,
)


# 為什麼用 G-AB-01-C90 作 anchor cell：Phase 2a deploy 用的同 cell（per E1 archive
# `2026-05-19--todo_v55_translation_archive.md`），與 actual demo runtime 直接對應；
# regression 對齊單一 cell 才能與 actual fill rate 直接比較。
ANCHOR_CELL = CalibrationCell(
    cell_id="G-AB-01-C90",
    family="grid",
    block=1,
    offset_bps=0.5,
    buffer_ticks=1,
    timeout_ms=90_000,
    spread_guard_bps=50.0,
    is_baseline=True,
    direction_note="Phase 2a deploy anchor cell",
)


def _get_conn():
    """取 PG 連線（與 phase_1b_tick_loader._get_conn 同模式）。"""
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


def load_v094_attempts(
    conn: Any,
    lookback_days: int = 14,
    sample_end_utc: Optional[datetime] = None,
) -> tuple[list[FillReplaySeed], int, int, datetime, datetime]:
    """從 V094 close_maker_attempt=TRUE 拉 sample + actual liquidity_role。

    為什麼直接讀 V094：bias regression 需 actual maker vs taker 標籤（V094 加的
    close_maker_attempt + close_maker_fallback_reason 兩列），這是 source-of-truth
    of real fill rate；不能用 pre-restart baseline（沒有 attempt 標籤）。

    為什麼支援 `sample_end_utc`（per E2 review MEDIUM-2, 2026-05-20）：
    原 `ts > NOW() - interval` 是 **sliding window** — 不同時刻跑會抓不同 sample，
    artifact 雖含 query/params 但缺 ts pinning → audit 重現性不足。
    顯式 pass `sample_end_utc=X` 可 pin window end，windows = [X-lookback, X]，
    對齊 V094 audit 時刻可 bit-exact 重現。
    default `None` = `now()`（向後相容）— 不破壞舊 CLI 行為。

    回傳：(seeds list, actual_maker_count, actual_taker_count,
            window_start_utc, window_end_utc)
    """
    seeds: list[FillReplaySeed] = []
    actual_maker = 0
    actual_taker = 0

    # 為什麼在 Python 側 resolve window 邊界：JSON artifact 與 SQL 必須一致；
    # 若用 PG NOW() 則 artifact 記錄與實際查詢時刻可能差 ms，破壞 deterministic
    # 重現。改在 Python 算出明確 (start, end) timestamptz 後 inject SQL。
    if sample_end_utc is None:
        window_end = datetime.now(timezone.utc)
    else:
        # 容錯：若 caller 給 naive datetime，假設 UTC（避免 tz drift）
        if sample_end_utc.tzinfo is None:
            window_end = sample_end_utc.replace(tzinfo=timezone.utc)
        else:
            window_end = sample_end_utc.astimezone(timezone.utc)
    window_start = window_end - timedelta(days=lookback_days)

    with conn.cursor() as cur:
        # 為什麼用 grid family exit_reason：anchor cell 是 grid family，與 sim
        # 對齊；其它 family 不會被 cell.family='grid' 匹配，自然被 family_mismatch
        # skip — 一致性。
        # 為什麼用 exit_reason ANY array：與 FAMILY_EXIT_REASONS['grid'] 對齊；
        # 不抓 phys_lock family 避免 family_mismatch skip 干擾 regression。
        # ⚠️ FAMILY-SPECIFIC 限制：本 query 結論僅適用 grid family；
        # phys_lock_giveback / phys_lock_stale_roc_neg 需各自用對應 anchor cell
        # 重跑（per E2 review MEDIUM-1, 2026-05-20）。
        # 為什麼用顯式 BETWEEN：取代原 `ts > NOW() - interval` sliding window，
        # 對齊 audit 時刻 bit-exact 重現（per MEDIUM-2）。
        cur.execute(
            """
            SELECT order_id, fill_id AS link_id, symbol, side, exit_reason,
                   qty, price, ts, close_maker_attempt,
                   close_maker_fallback_reason, liquidity_role
              FROM trading.fills
             WHERE engine_mode = 'demo'
               AND close_maker_attempt = TRUE
               AND exit_reason = ANY(%s)
               AND ts >= %s
               AND ts <= %s
             ORDER BY ts ASC
            """,
            (
                [
                    "grid_close_short",
                    "grid_close_long",
                    "bb_mean_revert",
                    "ma_reverse_cross",
                    "bw_squeeze",
                    "pctb_revert",
                ],
                window_start,
                window_end,
            ),
        )
        for row in cur.fetchall():
            (order_id, link_id, symbol, side, exit_reason,
             qty, price, ts, attempt, fallback, role) = row
            seeds.append(FillReplaySeed(
                order_id=order_id,
                link_id=link_id,
                symbol=symbol,
                side=side,
                exit_reason=exit_reason,
                qty=float(qty),
                price=float(price),
                ts=ts,
                close_maker_attempt=attempt,
                close_maker_fallback_reason=fallback,
                seed_source="v094_regression",
            ))
            if role == "maker":
                actual_maker += 1
            elif role == "taker":
                actual_taker += 1
    return seeds, actual_maker, actual_taker, window_start, window_end


def run_regression(
    conn: Any,
    cell: CalibrationCell,
    seeds: list[FillReplaySeed],
    queue_weight: float = DEFAULT_QUEUE_WEIGHT,
    base_rejection_rate: float = DEFAULT_BASE_REJECTION_RATE,
) -> dict:
    """跑 single-weight regression。

    回傳 dict 含：
      - n_attempts: total seed count
      - n_eligible: cell-level 扣 skip 後分母
      - n_proxy_fills: BBO-cross-proxy fill count（binary）
      - sweep_proxy_fill_rate: n_proxy_fills / n_eligible
      - sweep_adjusted_fill_rate: mean(queue_adjusted_fill_probability) eligible
      - skip breakdown
    """
    if not seeds:
        return {
            "n_attempts": 0,
            "n_eligible": 0,
            "n_proxy_fills": 0,
            "sweep_proxy_fill_rate": 0.0,
            "sweep_adjusted_fill_rate": 0.0,
            "queue_weight": queue_weight,
            "eligible_with_depth": 0,
            "skip_breakdown": {},
        }
    symbols = list({s.symbol for s in seeds})
    tick_size_map = load_tick_size_map(conn, symbols)
    print(f"[regression] loading tick windows for {len(seeds)} seeds ...",
          file=sys.stderr)
    tick_windows = load_all_tick_windows(conn, seeds)
    print(f"[regression] loading orderbook windows for {len(seeds)} seeds ...",
          file=sys.stderr)
    orderbook_windows = load_all_orderbook_windows(conn, seeds)
    print(f"[regression] running simulate_cell (cell={cell.cell_id} weight={queue_weight}) ...",
          file=sys.stderr)
    outcome = simulate_cell(
        cell=cell,
        seeds=seeds,
        tick_windows=tick_windows,
        tick_size_map=tick_size_map,
        orderbook_windows=orderbook_windows,
        queue_weight=queue_weight,
        base_rejection_rate=base_rejection_rate,
    )
    skip = {
        "spread_guard": outcome.n_skipped_spread_guard,
        "no_bbo": outcome.n_skipped_no_bbo,
        "tick_missing": outcome.n_skipped_tick_missing,
        "family_mismatch": outcome.n_skipped_family_mismatch,
        "crossed_book": outcome.n_skipped_crossed_book,
    }
    n_skip_total = sum(skip.values())
    n_eligible = outcome.n_attempts - n_skip_total
    return {
        "n_attempts": outcome.n_attempts,
        "n_eligible": n_eligible,
        "n_proxy_fills": outcome.n_simulated_fills,
        "sweep_proxy_fill_rate": outcome.maker_fill_rate,
        "sweep_adjusted_fill_rate": outcome.queue_adjusted_fill_rate,
        "queue_weight": queue_weight,
        "base_rejection_rate": base_rejection_rate,
        "eligible_with_depth": outcome.queue_adjusted_eligible_with_depth,
        "skip_breakdown": skip,
        # diagnostic per-fill samples（前 5 row）作 sanity check
        "sample_results": [
            {
                "order_id": r.fill_order_id,
                "symbol": r.symbol,
                "side": r.exit_reason,
                "qty": _qty_for_diagnostic(seeds, r.fill_order_id),
                "simulated_fill": r.simulated_fill,
                "queue_adjusted_p": round(r.queue_adjusted_fill_probability, 4),
                "queue_factor": (round(r.queue_factor, 4)
                                 if r.queue_factor is not None else None),
                "depth_5": (round(r.same_side_depth_5, 2)
                            if r.same_side_depth_5 is not None else None),
                "skip": r.skipped_reason,
            }
            for r in outcome.per_fill_results[:5]
        ],
    }


def _qty_for_diagnostic(seeds: list[FillReplaySeed], order_id: str) -> Optional[float]:
    """便利函數：找 seed.qty 用於 diagnostic table 顯示。"""
    for s in seeds:
        if s.order_id == order_id:
            return s.qty
    return None


def compute_bias(sweep_rate: float, actual_rate: float) -> float:
    """bias = sweep - actual (positive = sweep 高估)。單位：percentage points。"""
    return (sweep_rate - actual_rate) * 100.0


def print_results(
    regression: dict,
    actual_maker: int,
    actual_taker: int,
    target_bias_pp: float = 5.0,
    window_start_utc: Optional[datetime] = None,
    window_end_utc: Optional[datetime] = None,
    lookback_days: int = 14,
) -> None:
    """格式化輸出 regression 結果 + verdict。

    為什麼加 disclaimer block（per E2 review MEDIUM-1, 2026-05-20）：
    `base_rejection_rate` 是 family-specific empirical anchor；
    本 regression 結論限 anchor cell 對應 family；外推到其他 family 需各自校。
    """
    total_real = actual_maker + actual_taker
    actual_rate = (actual_maker / total_real) if total_real > 0 else 0.0
    proxy_rate = regression["sweep_proxy_fill_rate"]
    adjusted_rate = regression["sweep_adjusted_fill_rate"]
    bias_before = compute_bias(proxy_rate, actual_rate)
    bias_after = compute_bias(adjusted_rate, actual_rate)
    bias_reduction = abs(bias_before) - abs(bias_after)
    verdict = "PASS" if abs(bias_after) <= target_bias_pp else "FAIL"
    print()
    print("=" * 76)
    print(f"P2-SIM-QUEUE-AWARE-ADJUSTMENT v55 — Historical Regression Result")
    print("=" * 76)
    print(f"Cell: {ANCHOR_CELL.cell_id} (family={ANCHOR_CELL.family}"
          f", timeout {ANCHOR_CELL.timeout_ms}ms)")
    print(f"Queue weight       : {regression['queue_weight']:.2f}")
    print(f"Base rejection rate: {regression['base_rejection_rate']:.2f}")
    if window_start_utc is not None and window_end_utc is not None:
        print(f"Sample window UTC  : [{window_start_utc.isoformat()},"
              f" {window_end_utc.isoformat()}]")
        print(f"Lookback days      : {lookback_days}")
    print()
    print("[1] Sample summary")
    print(f"  V094 close_maker_attempt=TRUE rows     : {total_real}")
    print(f"    Actual maker (real fill)             : {actual_maker}")
    print(f"    Actual taker (fallback)              : {actual_taker}")
    print(f"  Sweep simulation n_attempts            : {regression['n_attempts']}")
    print(f"    n_eligible (post strict-skip)        : {regression['n_eligible']}")
    print(f"    eligible_with_depth (queue applied)  : {regression['eligible_with_depth']}")
    print()
    print("[2] Skip breakdown")
    for k, v in regression["skip_breakdown"].items():
        print(f"    {k:18s}: {v}")
    print()
    print("[3] Fill rate comparison")
    print(f"  actual_fill_rate                        : {actual_rate*100:6.2f}%")
    print(f"  sweep_proxy_fill_rate (BBO-cross only) : {proxy_rate*100:6.2f}%")
    print(f"  sweep_adjusted_fill_rate (queue-aware) : {adjusted_rate*100:6.2f}%")
    print()
    print("[4] Bias analysis (positive = sweep optimistic)")
    print(f"  bias_before (proxy − actual)           : {bias_before:+.2f} pp")
    print(f"  bias_after  (adjusted − actual)        : {bias_after:+.2f} pp")
    print(f"  |bias| reduction                        : {bias_reduction:+.2f} pp")
    print()
    print("[5] Verdict")
    print(f"  Target |bias_after| ≤ {target_bias_pp:.1f} pp           : {verdict}")
    print()
    print("[6] Sample diagnostic (first 5 fills)")
    for s in regression["sample_results"]:
        marker = ""
        if s["skip"]:
            marker = f"(SKIP {s['skip']})"
        print(f"  {s['order_id'][:30]:30s} sym={s['symbol']:8s} qty={s['qty']!s:>10}"
              f" depth={s['depth_5']!s:>10} factor={s['queue_factor']!s:>6}"
              f" fill={s['simulated_fill']!s:5} adj_p={s['queue_adjusted_p']:.3f}"
              f" {marker}")
    print("=" * 76)
    print()
    # 為什麼放結尾：disclaimer 是讀者解讀數字後最該看見的限制（per E2 MEDIUM-1）
    print("[DISCLAIMER — per E2 review MEDIUM-1, 2026-05-20]")
    print(f"  本 regression base_rejection={regression['base_rejection_rate']:.2f}"
          f" 是針對 anchor cell `{ANCHOR_CELL.cell_id}` (family=`{ANCHOR_CELL.family}`)")
    print(f"  以 {lookback_days}d V094 sample n={total_real} 校的 family-specific anchor。")
    print(f"  不應外推到其他 family（phys_lock_giveback / phys_lock_stale_roc_neg ...）；")
    print(f"  非 grid family 需各自用對應 anchor cell（如 PG-AB-01-C15 / PS-AB-01-C10）")
    print(f"  重跑此 regression CLI 校自家 base_rejection 值。")
    if window_start_utc is not None and window_end_utc is not None:
        print(f"  Sample window 已 pin 至 [{window_start_utc.isoformat()},"
              f" {window_end_utc.isoformat()}]，可 bit-exact 重現。")
    print("=" * 76)
    print()


def find_best_params(
    conn: Any,
    cell: CalibrationCell,
    seeds: list[FillReplaySeed],
    actual_rate: float,
    queue_weights: tuple = (0.10, 0.20, 0.40, 0.60, 0.80),
    base_rejections: tuple = (0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80),
) -> dict:
    """2D sweep (queue_weight × base_rejection_rate) 找最低 |bias_after| 設定。

    為什麼 2D sweep：14d V094 regression 揭示 queue-only model 對 close path
    bias collapse（factor < 0.02 dominant → queue 維度幾乎不調）；必須加
    base_rejection_rate empirical 校。2D 找最佳 (queue_weight, base_rejection)
    pair 才能 separation queue 與 non-queue 兩個 fail mode 貢獻。
    """
    print(f"[regression] 2D sweep queue_weight × base_rejection ...", file=sys.stderr)
    symbols = list({s.symbol for s in seeds})
    tick_size_map = load_tick_size_map(conn, symbols)
    tick_windows = load_all_tick_windows(conn, seeds)
    orderbook_windows = load_all_orderbook_windows(conn, seeds)
    results = []
    best_pair = None
    best_abs_bias = float("inf")
    for w in queue_weights:
        for b in base_rejections:
            outcome = simulate_cell(
                cell=cell, seeds=seeds,
                tick_windows=tick_windows, tick_size_map=tick_size_map,
                orderbook_windows=orderbook_windows,
                queue_weight=w, base_rejection_rate=b,
            )
            adj_rate = outcome.queue_adjusted_fill_rate
            bias = adj_rate - actual_rate
            results.append({
                "queue_weight": w,
                "base_rejection": b,
                "adjusted_fill_rate": adj_rate,
                "bias_pp": bias * 100.0,
            })
            if abs(bias) < best_abs_bias:
                best_abs_bias = abs(bias)
                best_pair = (w, b)
    return {
        "best_queue_weight": best_pair[0] if best_pair else None,
        "best_base_rejection": best_pair[1] if best_pair else None,
        "best_abs_bias_pp": best_abs_bias * 100.0,
        "sweep": results,
    }


def _parse_sample_end_utc(raw: Optional[str]) -> Optional[datetime]:
    """解析 `--sample-end-utc` CLI 參數（per E2 review MEDIUM-2）。

    支援格式：
      - ISO 8601 with tz suffix: '2026-05-20T03:00:00+00:00' / 'Z'
      - ISO 8601 naive UTC: '2026-05-20T03:00:00'（無 tz 視為 UTC）
      - 'now' / None → 回 None（caller fallback now()）

    無效字串 → ValueError，由 argparse 報錯。
    """
    if raw is None or raw == "" or raw.lower() == "now":
        return None
    # 容忍 'Z' suffix
    s = raw.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="P2-SIM-QUEUE-AWARE-ADJUSTMENT v55 historical regression",
    )
    parser.add_argument(
        "--lookback-days", type=int, default=14,
        help="V094 sample lookback window (default 14)",
    )
    parser.add_argument(
        "--sample-end-utc", type=str, default=None,
        help="Pin sample window END timestamp (UTC ISO-8601, e.g. "
             "'2026-05-20T03:00:00+00:00'). Default = now() (sliding). "
             "顯式 pass 對齊 audit 時刻可 bit-exact 重現（per E2 MEDIUM-2, 2026-05-20）。",
    )
    parser.add_argument(
        "--queue-weight", type=float, default=DEFAULT_QUEUE_WEIGHT,
        help=f"queue adjustment weight (default {DEFAULT_QUEUE_WEIGHT})",
    )
    parser.add_argument(
        "--base-rejection", type=float, default=DEFAULT_BASE_REJECTION_RATE,
        help=f"base rejection rate for non-queue fail modes "
             f"(default {DEFAULT_BASE_REJECTION_RATE}). "
             f"⚠️ family-specific anchor — 結論限 anchor cell 對應 family "
             f"(per E2 MEDIUM-1, 2026-05-20)。",
    )
    parser.add_argument(
        "--target-bias-pp", type=float, default=5.0,
        help="Target |bias_after| pass threshold in percentage points (default 5)",
    )
    parser.add_argument(
        "--sweep-params", action="store_true",
        help="2D sweep (queue_weight × base_rejection) 找最佳 pair",
    )
    parser.add_argument(
        "--json-out", type=str, default=None,
        help="Optional JSON output path",
    )
    args = parser.parse_args()

    # 為什麼在 main 入口就解析：失敗早 abort（argparse-friendly）
    sample_end_utc = _parse_sample_end_utc(args.sample_end_utc)

    conn = _get_conn()
    try:
        seeds, actual_maker, actual_taker, window_start_utc, window_end_utc = (
            load_v094_attempts(
                conn,
                lookback_days=args.lookback_days,
                sample_end_utc=sample_end_utc,
            )
        )
        total_real = actual_maker + actual_taker
        if total_real == 0:
            print("[regression] no V094 close_maker_attempt=TRUE sample in window — abort",
                  file=sys.stderr)
            return 2
        actual_rate = actual_maker / total_real
        regression = run_regression(
            conn, ANCHOR_CELL, seeds,
            queue_weight=args.queue_weight,
            base_rejection_rate=args.base_rejection,
        )
        print_results(
            regression,
            actual_maker=actual_maker, actual_taker=actual_taker,
            target_bias_pp=args.target_bias_pp,
            window_start_utc=window_start_utc,
            window_end_utc=window_end_utc,
            lookback_days=args.lookback_days,
        )

        sweep_result: Optional[dict] = None
        if args.sweep_params:
            sweep_result = find_best_params(
                conn, ANCHOR_CELL, seeds, actual_rate=actual_rate,
            )
            print(f"[sweep] 2D sweep vs actual_rate {actual_rate*100:.2f}%")
            # 把 sweep 表攤 csv-like 印出
            print(f"{'queue_w':>8} {'base':>6} {'adj_rate%':>10} {'bias_pp':>10}")
            for r in sweep_result["sweep"]:
                print(f"{r['queue_weight']:>8.2f} {r['base_rejection']:>6.2f}"
                      f"  {r['adjusted_fill_rate']*100:>8.2f}"
                      f"  {r['bias_pp']:>+8.2f}")
            print(f"[sweep] best (queue_w={sweep_result['best_queue_weight']:.2f}"
                  f", base={sweep_result['best_base_rejection']:.2f})"
                  f" |bias|={sweep_result['best_abs_bias_pp']:.2f}pp")

        if args.json_out:
            payload = {
                "cell": ANCHOR_CELL.to_dict(),
                # ⚠️ family-specific anchor disclosure（per E2 MEDIUM-1, 2026-05-20）
                "anchor_family": ANCHOR_CELL.family,
                "anchor_disclaimer": (
                    f"base_rejection={args.base_rejection:.2f} is family-specific "
                    f"empirical anchor calibrated on cell '{ANCHOR_CELL.cell_id}' "
                    f"(family='{ANCHOR_CELL.family}', n={total_real}, "
                    f"lookback={args.lookback_days}d). DO NOT extrapolate to other "
                    f"families (phys_lock_giveback / phys_lock_stale_roc_neg ...) "
                    f"without rerunning regression with corresponding anchor cells."
                ),
                "lookback_days": args.lookback_days,
                # window pinning（per E2 MEDIUM-2, 2026-05-20）
                "sample_end_utc": (
                    sample_end_utc.isoformat() if sample_end_utc else None
                ),
                "sample_window_start_utc": window_start_utc.isoformat(),
                "sample_window_end_utc": window_end_utc.isoformat(),
                "sample_window_pinned": sample_end_utc is not None,
                "actual_maker": actual_maker,
                "actual_taker": actual_taker,
                "actual_fill_rate": actual_rate,
                "regression": regression,
                "sweep_result": sweep_result,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            with open(args.json_out, "w") as fh:
                json.dump(payload, fh, indent=2, default=str)
            print(f"[regression] JSON saved → {args.json_out}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
