"""
MODULE_NOTE
模塊用途：Phase 1b calibration sweep per-cell simulation engine。
依 PA spec §2.3 algorithm：對每 cell × 每 historical fill seed：
  1. 從 fill_ts 前 60s 取 tick window；
  2. 在 fill_ts 用 compute_close_limit_price 計 simulated maker limit；
  3. 在 fill_ts ~ fill_ts+timeout_ms 期間 replay BBO，判定該 limit 是否成交；
  4. 計 fee_saving_bps + adverse_selection_proxy_bps；
  5. 與 cell baseline 比較得 PASS/CONDITIONAL/FAIL 評估。
主要類/函數：FillSimulationResult / CellSimulationOutcome /
            simulate_cell_against_fill / simulate_cell / simulate_all_cells。
依賴：phase_1b_sweep_cells / phase_1b_tick_loader / phase_1b_maker_price（pure modules）。
硬邊界：read-only PG；無 IPC；無 trading side effect；CSV/JSON 輸出僅至
        helper_scripts/calibration/output/；data_source 必 tag bybit_demo_ws。
注意：spec §2.3.5 標 future enhancement 的「精確 queue position」用簡化版
（first version per task ask）— 用 BBO 反向側 cross 即視為成交，不模擬 queue。
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_1b_sweep_cells import CalibrationCell, FAMILY_EXIT_REASONS  # noqa: E402
from phase_1b_tick_loader import (  # noqa: E402
    FillReplaySeed,
    TickSample,
    TickWindow,
    DATA_SOURCE_TAG,
    POST_FILL_DRIFT_SECONDS,
    load_replay_seed,
    load_tick_size_map,
    load_tick_window,
    get_taker_baseline_fee_bps,
    verify_freshness,
)
from phase_1b_maker_price import (  # noqa: E402
    CloseMakerPricePolicy,
    MakerPriceInputs,
    FEE_SAVING_CAP_BPS,
    compute_adverse_selection_proxy_bps,
    compute_close_limit_price,
    compute_fee_saving_bps,
)


# spec §2.3 — 適用 fill 判定的最小 BBO sample 數
MIN_REPLAY_SAMPLES_FOR_FILL = 1

# 浮點容忍：BBO sample 與 limit_price 比較時的 epsilon。
# 為什麼 1e-6：tick_size 最小 0.00001 (1e-5)；epsilon 比 tick 小一個數量級夠用；
# 同時容忍 Python f64 浮點誤差（如 100.02000000000001）；
# 與 Rust hot path 浮點比較行為一致。
FILL_PRICE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class FillSimulationResult:
    """單一 cell × 單一 fill 模擬結果。

    為什麼這結構：可後續 aggregate；serialize JSON 報告所需 fields 全在一處。
    """
    cell_id: str
    fill_order_id: str
    symbol: str
    fill_ts: datetime
    exit_reason: str
    seed_source: str
    # 模擬結果
    simulated_fill: bool
    simulated_fill_px: Optional[float]
    simulated_fill_ts: Optional[datetime]
    actual_taker_px: float  # 對應 seed.price
    fee_saving_bps: Optional[float]
    adverse_selection_proxy_bps: Optional[float]
    # 跳過分類（per spec §2.3.3 / §2.3.4）
    skipped_reason: Optional[str]  # 'spread_guard' / 'no_bbo' / 'tick_size_missing' /
                                     # 'family_exit_mismatch' / 'crossed_book' / None
    # 額外診斷
    limit_price: Optional[float]  # 計算出的 maker limit；None 若 strict skip
    mid_at_fill_plus_60s: Optional[float]


@dataclass(frozen=True)
class CellSimulationOutcome:
    """單一 cell 跨所有 fill 的 aggregate 結果。

    spec §2.4 schema 對應；report 階段加 Wilson CI + pass_gate。
    """
    cell_id: str
    n_attempts: int
    n_simulated_fills: int
    n_skipped_spread_guard: int
    n_skipped_no_bbo: int
    n_skipped_tick_missing: int
    n_skipped_family_mismatch: int
    n_skipped_crossed_book: int
    # rates
    maker_fill_rate: float
    expected_fee_saving_bps: float  # mean across simulated fills
    adverse_selection_proxy_bps: Optional[float]  # mean across simulated fills
    # diagnostic per-fill list
    per_fill_results: tuple[FillSimulationResult, ...]
    data_source: str = DATA_SOURCE_TAG


def _bbo_at_or_before(samples: tuple[TickSample, ...], ts: datetime) -> Optional[TickSample]:
    """從 sample tuple 取最後一個 ts ≤ 給定 ts 的 sample。

    為什麼線性掃描：每 fill 對應 ~120 samples（60s + 90s ~ 1Hz），線性 O(n)
    成本可忽略；避免引入 bisect/numpy 依賴。
    """
    best: Optional[TickSample] = None
    for s in samples:
        if s.ts <= ts and (best is None or s.ts > best.ts):
            best = s
    return best


def _bbo_in_range(
    samples: tuple[TickSample, ...],
    start: datetime,
    end: datetime,
) -> list[TickSample]:
    """取 [start, end] 範圍內 sample（含邊界）。"""
    return [s for s in samples if start <= s.ts <= end]


def simulate_cell_against_fill(
    cell: CalibrationCell,
    seed: FillReplaySeed,
    tick_window: TickWindow,
    tick_size: float,
) -> FillSimulationResult:
    """spec §2.3 algorithm — 對單一 cell × fill 跑模擬。

    步驟對應 spec §2.3:
      1. 確認 fill exit_reason 屬於 cell.family 的 whitelist（不匹配 → skip）
      2. 取 fill_ts 時最新 BBO → 計 limit_price = compute_close_limit_price(...)
      3. limit_price=None → skip 分類至對應 reason
      4. 在 [fill_ts, fill_ts + timeout_ms] 範圍 replay BBO：
         - For close long (sell limit at P): 若任何 sample best_bid ≥ P → fill 成立
         - For close short (buy limit at P): 若任何 sample best_ask ≤ P → fill 成立
      5. 若 timeout 內未成交 → simulated_fill=False（不算 cell PASS 分子）
      6. 計 fee_saving_bps + adverse_selection_proxy_bps

    為什麼用 BBO cross 替代 trade tape：
      PG 無 tick-level trade tape；用 BBO 反向側越過 limit 視為「會被 fill」
      （保守模型 — 真實 fill 需 trade actually print，BBO cross 是 necessary
      condition 但非 sufficient）；對 calibration 用途足夠。spec §2.3.5 標
      future enhancement 用 trade tape 精化。
    """
    # 步驟 1: family / exit_reason 匹配
    allowed_reasons = FAMILY_EXIT_REASONS.get(cell.family, [])
    canonical_reason = seed.exit_reason or ""
    # 對應 Rust canonical_close_maker_reason 簡化版（去 strategy_close: / risk_close: prefix）
    for prefix in ("strategy_close:", "risk_close:"):
        if canonical_reason.startswith(prefix):
            canonical_reason = canonical_reason[len(prefix):].strip()
    if canonical_reason not in allowed_reasons:
        return FillSimulationResult(
            cell_id=cell.cell_id,
            fill_order_id=seed.order_id,
            symbol=seed.symbol,
            fill_ts=seed.ts,
            exit_reason=seed.exit_reason,
            seed_source=seed.seed_source,
            simulated_fill=False,
            simulated_fill_px=None,
            simulated_fill_ts=None,
            actual_taker_px=seed.price,
            fee_saving_bps=None,
            adverse_selection_proxy_bps=None,
            skipped_reason="family_exit_mismatch",
            limit_price=None,
            mid_at_fill_plus_60s=None,
        )

    # 步驟 2: 取 fill_ts 時最新 BBO
    bbo_at_fill = _bbo_at_or_before(
        tick_window.pre_fill_samples + tick_window.replay_samples,
        seed.ts,
    )
    if bbo_at_fill is None:
        return FillSimulationResult(
            cell_id=cell.cell_id,
            fill_order_id=seed.order_id,
            symbol=seed.symbol,
            fill_ts=seed.ts,
            exit_reason=seed.exit_reason,
            seed_source=seed.seed_source,
            simulated_fill=False,
            simulated_fill_px=None,
            simulated_fill_ts=None,
            actual_taker_px=seed.price,
            fee_saving_bps=None,
            adverse_selection_proxy_bps=None,
            skipped_reason="no_bbo",
            limit_price=None,
            mid_at_fill_plus_60s=None,
        )

    # 步驟 2: position_is_long 反推
    # seed.side='Buy' → close order 是 BUY → 原 position 是 SHORT → position_is_long=False
    # seed.side='Sell' → close order 是 SELL → 原 position 是 LONG → position_is_long=True
    position_is_long = seed.side.lower() == "sell"

    inputs = MakerPriceInputs(
        last_price=seed.price,
        best_bid=bbo_at_fill.best_bid,
        best_ask=bbo_at_fill.best_ask,
        tick_size=tick_size,
    )
    policy = CloseMakerPricePolicy(
        buffer_ticks=cell.buffer_ticks,
        offset_bps=cell.offset_bps,
        timeout_ms=cell.timeout_ms,
    )
    limit_price = compute_close_limit_price(
        position_is_long=position_is_long,
        inputs=inputs,
        policy=policy,
        spread_guard_bps=cell.spread_guard_bps,
    )

    # 步驟 3: strict-skip 分類
    if limit_price is None:
        # 嘗試診斷 skip reason — 與 Rust 邏輯保持邏輯一致
        if bbo_at_fill.best_ask <= bbo_at_fill.best_bid:
            skip = "crossed_book"
        elif bbo_at_fill.spread_bps is not None and bbo_at_fill.spread_bps > cell.spread_guard_bps:
            skip = "spread_guard"
        elif not (tick_size > 0):
            skip = "tick_size_missing"
        else:
            skip = "spread_guard"  # 包含 small-tick widen overflow / 其他 strict skip
        return FillSimulationResult(
            cell_id=cell.cell_id,
            fill_order_id=seed.order_id,
            symbol=seed.symbol,
            fill_ts=seed.ts,
            exit_reason=seed.exit_reason,
            seed_source=seed.seed_source,
            simulated_fill=False,
            simulated_fill_px=None,
            simulated_fill_ts=None,
            actual_taker_px=seed.price,
            fee_saving_bps=None,
            adverse_selection_proxy_bps=None,
            skipped_reason=skip,
            limit_price=None,
            mid_at_fill_plus_60s=None,
        )

    # 步驟 4: replay BBO 判定成交
    timeout_end = seed.ts + timedelta(milliseconds=cell.timeout_ms)
    replay_in_window = _bbo_in_range(tick_window.replay_samples, seed.ts, timeout_end)

    simulated_fill = False
    simulated_fill_px: Optional[float] = None
    simulated_fill_ts: Optional[datetime] = None

    if len(replay_in_window) >= MIN_REPLAY_SAMPLES_FOR_FILL:
        # close long = SELL limit at limit_price，需 best_bid ≥ limit_price 才會 taker hit it
        # close short = BUY limit at limit_price，需 best_ask ≤ limit_price 才會 taker hit it
        # 為什麼加 FILL_PRICE_TOLERANCE：避免 Python f64 從 widening 計算累積誤差
        # （如 100.02000000000001 vs 100.02）誤判 fill。
        for sample in replay_in_window:
            if position_is_long:
                # SELL limit fills when buyer side reaches our ask
                if sample.best_bid >= (limit_price - FILL_PRICE_TOLERANCE):
                    simulated_fill = True
                    simulated_fill_px = limit_price
                    simulated_fill_ts = sample.ts
                    break
            else:
                # BUY limit fills when seller side reaches our bid
                if sample.best_ask <= (limit_price + FILL_PRICE_TOLERANCE):
                    simulated_fill = True
                    simulated_fill_px = limit_price
                    simulated_fill_ts = sample.ts
                    break

    # 步驟 5: adverse selection proxy （+60s mid）
    mid_at_fill_plus_60s: Optional[float] = None
    if tick_window.post_drift_samples:
        target_ts = seed.ts + timedelta(seconds=60)
        nearest = _bbo_at_or_before(tick_window.post_drift_samples, target_ts)
        if nearest is not None:
            mid_at_fill_plus_60s = nearest.mid

    fee_saving_bps: Optional[float] = None
    adverse_proxy_bps: Optional[float] = None
    if simulated_fill and simulated_fill_px is not None:
        fee_saving_bps = compute_fee_saving_bps(
            simulated_fill_px=simulated_fill_px,
            actual_taker_px=seed.price,
            position_is_long=position_is_long,
        )
        adverse_proxy_bps = compute_adverse_selection_proxy_bps(
            mid_at_fill_plus_60s=mid_at_fill_plus_60s,
            simulated_fill_px=simulated_fill_px,
            position_is_long=position_is_long,
        )

    return FillSimulationResult(
        cell_id=cell.cell_id,
        fill_order_id=seed.order_id,
        symbol=seed.symbol,
        fill_ts=seed.ts,
        exit_reason=seed.exit_reason,
        seed_source=seed.seed_source,
        simulated_fill=simulated_fill,
        simulated_fill_px=simulated_fill_px,
        simulated_fill_ts=simulated_fill_ts,
        actual_taker_px=seed.price,
        fee_saving_bps=fee_saving_bps,
        adverse_selection_proxy_bps=adverse_proxy_bps,
        skipped_reason=None,
        limit_price=limit_price,
        mid_at_fill_plus_60s=mid_at_fill_plus_60s,
    )


def simulate_cell(
    cell: CalibrationCell,
    seeds: list[FillReplaySeed],
    tick_windows: dict[str, TickWindow],
    tick_size_map: dict[str, float],
) -> CellSimulationOutcome:
    """對單一 cell 跑全 seed 模擬，aggregate 結果。

    為什麼 tick_window 用 order_id key：每 seed.order_id 唯一；同 fill 對應同
    window 在多 cell 間共享，減少 PG 查詢成本。
    """
    per_fill_results: list[FillSimulationResult] = []
    for seed in seeds:
        if seed.order_id not in tick_windows:
            # window 未載入 → skip 該 fill (no_bbo 路徑)
            per_fill_results.append(FillSimulationResult(
                cell_id=cell.cell_id,
                fill_order_id=seed.order_id,
                symbol=seed.symbol,
                fill_ts=seed.ts,
                exit_reason=seed.exit_reason,
                seed_source=seed.seed_source,
                simulated_fill=False,
                simulated_fill_px=None,
                simulated_fill_ts=None,
                actual_taker_px=seed.price,
                fee_saving_bps=None,
                adverse_selection_proxy_bps=None,
                skipped_reason="no_bbo",
                limit_price=None,
                mid_at_fill_plus_60s=None,
            ))
            continue
        tick_size = tick_size_map.get(seed.symbol)
        if tick_size is None:
            per_fill_results.append(FillSimulationResult(
                cell_id=cell.cell_id,
                fill_order_id=seed.order_id,
                symbol=seed.symbol,
                fill_ts=seed.ts,
                exit_reason=seed.exit_reason,
                seed_source=seed.seed_source,
                simulated_fill=False,
                simulated_fill_px=None,
                simulated_fill_ts=None,
                actual_taker_px=seed.price,
                fee_saving_bps=None,
                adverse_selection_proxy_bps=None,
                skipped_reason="tick_size_missing",
                limit_price=None,
                mid_at_fill_plus_60s=None,
            ))
            continue
        result = simulate_cell_against_fill(
            cell=cell,
            seed=seed,
            tick_window=tick_windows[seed.order_id],
            tick_size=tick_size,
        )
        per_fill_results.append(result)

    # aggregate
    n_attempts = len(per_fill_results)
    n_simulated_fills = sum(1 for r in per_fill_results if r.simulated_fill)
    n_skip_spread_guard = sum(1 for r in per_fill_results if r.skipped_reason == "spread_guard")
    n_skip_no_bbo = sum(1 for r in per_fill_results if r.skipped_reason == "no_bbo")
    n_skip_tick = sum(1 for r in per_fill_results if r.skipped_reason == "tick_size_missing")
    n_skip_family = sum(1 for r in per_fill_results if r.skipped_reason == "family_exit_mismatch")
    n_skip_crossed = sum(1 for r in per_fill_results if r.skipped_reason == "crossed_book")

    # 分母 = n_attempts - n_skipped_total（spec §2.4: maker_fill_rate denom 是
    # n_attempts - n_skipped_spread_guard，但我們擴展為扣除全部 strict-skip 因 cell
    # 真實 "fillable" 樣本必扣 BBO/tick 缺失）
    n_skip_total = n_skip_spread_guard + n_skip_no_bbo + n_skip_tick + n_skip_family + n_skip_crossed
    eligible = n_attempts - n_skip_total
    maker_fill_rate = (n_simulated_fills / eligible) if eligible > 0 else 0.0

    fee_savings = [r.fee_saving_bps for r in per_fill_results
                   if r.fee_saving_bps is not None]
    expected_fee_saving_bps = (sum(fee_savings) / len(fee_savings)) if fee_savings else 0.0

    adverses = [r.adverse_selection_proxy_bps for r in per_fill_results
                if r.adverse_selection_proxy_bps is not None]
    adverse_selection_proxy_bps = (sum(adverses) / len(adverses)) if adverses else None

    return CellSimulationOutcome(
        cell_id=cell.cell_id,
        n_attempts=n_attempts,
        n_simulated_fills=n_simulated_fills,
        n_skipped_spread_guard=n_skip_spread_guard,
        n_skipped_no_bbo=n_skip_no_bbo,
        n_skipped_tick_missing=n_skip_tick,
        n_skipped_family_mismatch=n_skip_family,
        n_skipped_crossed_book=n_skip_crossed,
        maker_fill_rate=maker_fill_rate,
        expected_fee_saving_bps=expected_fee_saving_bps,
        adverse_selection_proxy_bps=adverse_selection_proxy_bps,
        per_fill_results=tuple(per_fill_results),
        data_source=DATA_SOURCE_TAG,
    )


def simulate_all_cells(
    cells: list[CalibrationCell],
    seeds: list[FillReplaySeed],
    tick_windows: dict[str, TickWindow],
    tick_size_map: dict[str, float],
) -> list[CellSimulationOutcome]:
    """對 N cells × seeds 跑全部 simulation。

    為什麼順序執行：spec §5 Step 3 提到 batch ≤30s/cell × 81 ≈ 40min；無
    parallel 必要；保持單線程確保 deterministic + 易除錯。
    """
    return [
        simulate_cell(cell, seeds, tick_windows, tick_size_map)
        for cell in cells
    ]


def load_all_tick_windows(
    conn: Any,
    seeds: list[FillReplaySeed],
) -> dict[str, TickWindow]:
    """批量載入 tick window per seed.order_id。

    為什麼 dict by order_id：同一 seed 在多 cell 間共享 window；
    cache hit 避免重複 PG 查詢。
    """
    out: dict[str, TickWindow] = {}
    for seed in seeds:
        out[seed.order_id] = load_tick_window(conn, seed)
    return out
