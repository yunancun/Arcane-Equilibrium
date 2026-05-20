"""
MODULE_NOTE
模塊用途：Phase 1b calibration sweep per-cell simulation engine。
依 PA spec §2.3 algorithm：對每 cell × 每 historical fill seed：
  1. 從 fill_ts 前 60s 取 tick window；
  2. 在 fill_ts 用 compute_close_limit_price 計 simulated maker limit；
  3. 在 fill_ts ~ fill_ts+timeout_ms 期間 replay BBO，判定該 limit 是否成交；
  4. 計 fee_saving_bps + adverse_selection_proxy_bps；
  5. P2-SIM-QUEUE-AWARE-ADJUSTMENT v55：用 ob_snapshots depth_5 估 queue
     ahead-of-me size，把 fill_probability_proxy 下調至 queue-aware 值。
  6. 與 cell baseline 比較得 PASS/CONDITIONAL/FAIL 評估。
主要類/函數：FillSimulationResult / CellSimulationOutcome /
            simulate_cell_against_fill / simulate_cell / simulate_all_cells /
            load_all_orderbook_windows。
依賴：phase_1b_sweep_cells / phase_1b_tick_loader / phase_1b_maker_price /
      phase_1b_queue_adjustment（pure modules）。
硬邊界：read-only PG；無 IPC；無 trading side effect；CSV/JSON 輸出僅至
        helper_scripts/calibration/output/；data_source 必 tag bybit_demo_ws。
注意：v55 之前的 sweep 用 BBO-cross-proxy 判 fill — close path 系統性樂觀
10-15pp（per PA cell selection report §5.1）。v55 新增 queue-aware aggregate
（queue_adjusted_fill_rate）作為更接近 real-world 的 fill rate estimate；
per-fill binary `simulated_fill` 仍保留 backward compat。
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
    OrderbookDepthWindow,
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
from phase_1b_queue_adjustment import (  # noqa: E402
    DEFAULT_BASE_REJECTION_RATE,
    DEFAULT_QUEUE_WEIGHT,
    apply_queue_adjustment,
    compute_queue_factor,
    select_same_side_depth,
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

    Queue-aware adjustment（P2-SIM-QUEUE-AWARE-ADJUSTMENT v55）：
      `simulated_fill` 仍是 binary（BBO-cross-proxy 結果，per-fill semantics 不變）。
      `queue_adjusted_fill_probability` 是 cross 發生時的調整後機率 ∈ [0, 1]；
      cross 沒發生（simulated_fill=False） → 0.0；
      orderbook depth 缺 → 等於 1.0（fail-closed 退回 proxy 不調整）。
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
    # P2-SIM-QUEUE-AWARE-ADJUSTMENT v55 新增
    queue_adjusted_fill_probability: float = 0.0
    same_side_depth_5: Optional[float] = None
    queue_factor: Optional[float] = None


@dataclass(frozen=True)
class CellSimulationOutcome:
    """單一 cell 跨所有 fill 的 aggregate 結果。

    spec §2.4 schema 對應；report 階段加 Wilson CI + pass_gate。

    Queue-aware adjustment（P2-SIM-QUEUE-AWARE-ADJUSTMENT v55）：
      `maker_fill_rate` 仍是 BBO-cross-proxy n_fills / n_eligible（unchanged
      backward-compat）。`queue_adjusted_fill_rate` 是 mean(queue_adjusted_fill_
      probability) / n_eligible，預期低 ~10-15pp（per PA cell selection report §5.1）。
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
    # P2-SIM-QUEUE-AWARE-ADJUSTMENT v55 新增
    queue_adjusted_fill_rate: float = 0.0
    queue_adjusted_eligible_with_depth: int = 0  # eligible 中真正有 depth proxy 套用的 n
    # diagnostic per-fill list
    per_fill_results: tuple[FillSimulationResult, ...] = ()
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
    orderbook_window: Optional[OrderbookDepthWindow] = None,
    queue_weight: float = DEFAULT_QUEUE_WEIGHT,
    base_rejection_rate: float = DEFAULT_BASE_REJECTION_RATE,
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

    # 步驟 6: queue-aware adjustment（P2-SIM-QUEUE-AWARE-ADJUSTMENT v55）
    # 為什麼這步：BBO-cross-proxy 系統性樂觀（高估 ~10-15pp per PA §5.1）；
    # 用 ob_snapshots depth_5 估 queue ahead-of-me size 下調 fill_probability。
    # fail-closed：depth proxy 缺 → queue_adjusted_fill_probability = simulated_fill 對應
    # 0/1（不調整，保留 backward-compat）。
    fill_p_proxy = 1.0 if simulated_fill else 0.0
    queue_factor: Optional[float] = None
    same_side_depth: Optional[float] = None
    if orderbook_window is not None:
        depth_sample = orderbook_window.depth_at_or_before(seed.ts)
        same_side_depth = select_same_side_depth(position_is_long, depth_sample)
        queue_factor = compute_queue_factor(seed.qty, same_side_depth)
    queue_adjusted_p = apply_queue_adjustment(
        fill_probability_proxy=fill_p_proxy,
        queue_factor=queue_factor,
        queue_weight=queue_weight,
        base_rejection_rate=base_rejection_rate,
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
        queue_adjusted_fill_probability=queue_adjusted_p,
        same_side_depth_5=same_side_depth,
        queue_factor=queue_factor,
    )


def simulate_cell(
    cell: CalibrationCell,
    seeds: list[FillReplaySeed],
    tick_windows: dict[str, TickWindow],
    tick_size_map: dict[str, float],
    orderbook_windows: Optional[dict[str, OrderbookDepthWindow]] = None,
    queue_weight: float = DEFAULT_QUEUE_WEIGHT,
    base_rejection_rate: float = DEFAULT_BASE_REJECTION_RATE,
) -> CellSimulationOutcome:
    """對單一 cell 跑全 seed 模擬，aggregate 結果。

    為什麼 tick_window 用 order_id key：每 seed.order_id 唯一；同 fill 對應同
    window 在多 cell 間共享，減少 PG 查詢成本。

    Queue-aware adjustment（P2-SIM-QUEUE-AWARE-ADJUSTMENT v55）：
      orderbook_windows=None → 保留向後兼容（無 queue adjust，queue_adjusted_fill_rate
      等於 maker_fill_rate）。提供 dict 時，每 seed 嘗試查 same key 的 depth window，
      缺則 per-fill fail-closed。
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
        ob_window: Optional[OrderbookDepthWindow] = None
        if orderbook_windows is not None:
            ob_window = orderbook_windows.get(seed.order_id)
        result = simulate_cell_against_fill(
            cell=cell,
            seed=seed,
            tick_window=tick_windows[seed.order_id],
            tick_size=tick_size,
            orderbook_window=ob_window,
            queue_weight=queue_weight,
            base_rejection_rate=base_rejection_rate,
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

    # Queue-aware aggregate（P2-SIM-QUEUE-AWARE-ADJUSTMENT v55）
    # 為什麼用 eligible 作 denom：與 maker_fill_rate 公平比較（同 denom 同 numerator
    # semantics）；queue_adjusted_fill_rate 高估只在 cross 發生時下調的「期望命中率」。
    eligible_results = [r for r in per_fill_results if r.skipped_reason is None]
    queue_adjusted_sum = sum(r.queue_adjusted_fill_probability for r in eligible_results)
    queue_adjusted_fill_rate = (queue_adjusted_sum / eligible) if eligible > 0 else 0.0
    # eligible_with_depth：診斷用 — eligible 中真正套用 queue adjustment 的 n（depth 有效）。
    eligible_with_depth = sum(
        1 for r in eligible_results if r.queue_factor is not None
    )

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
        queue_adjusted_fill_rate=queue_adjusted_fill_rate,
        queue_adjusted_eligible_with_depth=eligible_with_depth,
        per_fill_results=tuple(per_fill_results),
        data_source=DATA_SOURCE_TAG,
    )


def simulate_all_cells(
    cells: list[CalibrationCell],
    seeds: list[FillReplaySeed],
    tick_windows: dict[str, TickWindow],
    tick_size_map: dict[str, float],
    orderbook_windows: Optional[dict[str, OrderbookDepthWindow]] = None,
    queue_weight: float = DEFAULT_QUEUE_WEIGHT,
    base_rejection_rate: float = DEFAULT_BASE_REJECTION_RATE,
) -> list[CellSimulationOutcome]:
    """對 N cells × seeds 跑全部 simulation。

    為什麼順序執行：spec §5 Step 3 提到 batch ≤30s/cell × 81 ≈ 40min；無
    parallel 必要；保持單線程確保 deterministic + 易除錯。

    orderbook_windows=None → 向後兼容 path（無 queue adjust）。
    """
    return [
        simulate_cell(
            cell, seeds, tick_windows, tick_size_map,
            orderbook_windows=orderbook_windows,
            queue_weight=queue_weight,
            base_rejection_rate=base_rejection_rate,
        )
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


def load_all_orderbook_windows(
    conn: Any,
    seeds: list[FillReplaySeed],
) -> dict[str, "OrderbookDepthWindow"]:
    """批量載入 orderbook depth window per seed.order_id。

    為什麼分開 load：ob_snapshots 1m aggregate 是 optional dependency；
    historical regression / queue-aware sweep 才需要；舊 sweep run 不引入新查詢。
    """
    from phase_1b_tick_loader import load_orderbook_window  # 局部 import 避免循環
    out: dict[str, OrderbookDepthWindow] = {}
    for seed in seeds:
        out[seed.order_id] = load_orderbook_window(conn, seed)
    return out
