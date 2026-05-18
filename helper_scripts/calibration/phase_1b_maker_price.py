"""
MODULE_NOTE
模塊用途：Python port of Rust `compute_close_limit_price` 與 `compute_post_only_price`，
供 Phase 1b calibration sweep simulation 使用。
源碼對應：`rust/openclaw_engine/src/strategies/common/maker_price.rs:159-226` (close)
            + `maker_price.rs:252-352` (post_only)。
主要類/函數：MakerPriceInputs / CloseMakerPricePolicy /
            compute_close_limit_price / compute_post_only_price。
依賴：std math only（純函數，無 IO）。
硬邊界：與 Rust source 1:1 算法對應；浮點容差 1e-9；不可加 cosmetic 變動；
        所有 strict-skip 路徑回 None（fail-closed），caller 必跳過該 cell × fill。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# spec / Rust source 一致的 spread guard 常數（Block 4 D-axis 可 override）
CLOSE_MAKER_SPREAD_GUARD_BPS_DEFAULT = 50.0


@dataclass(frozen=True)
class MakerPriceInputs:
    """對應 Rust `MakerPriceInputs` struct。

    為什麼 Optional：tick 階段可能 BBO 或 tick_size 缺失（cold start / cache miss）；
    strict path 在缺失時回 None（fail-closed）。
    """
    last_price: float
    best_bid: Optional[float]
    best_ask: Optional[float]
    tick_size: Optional[float]


@dataclass(frozen=True)
class CloseMakerPricePolicy:
    """對應 Rust `CloseMakerPricePolicy` struct。

    為什麼 frozen：policy 是 cell-level immutable input；hash 用於 dedupe。
    """
    buffer_ticks: int
    offset_bps: float
    timeout_ms: int


def _is_finite_positive(x: Optional[float]) -> bool:
    """對應 Rust `.filter(|v| v.is_finite() && *v > 0.0)`。"""
    return x is not None and math.isfinite(x) and x > 0.0


def compute_close_limit_price(
    position_is_long: bool,
    inputs: MakerPriceInputs,
    policy: CloseMakerPricePolicy,
    spread_guard_bps: float = CLOSE_MAKER_SPREAD_GUARD_BPS_DEFAULT,
) -> Optional[float]:
    """Rust `compute_close_limit_price` 1:1 port。

    `position_is_long=True` → close 是 SELL → 反向呼 `compute_post_only_price(is_long=False)`
    `position_is_long=False` → close 是 BUY → 反向呼 `compute_post_only_price(is_long=True)`

    為什麼 spread_guard 傳參：原始 Rust 用 const，calibration sweep Block 4 動態變動；
    參數預設 = 50.0 baseline，與 Rust const 對齊。
    fail-closed：locked/crossed book / spread > guard / tick widen overflow → None。
    """
    bid = inputs.best_bid if _is_finite_positive(inputs.best_bid) else None
    ask = inputs.best_ask if _is_finite_positive(inputs.best_ask) else None

    buffer_ticks = max(policy.buffer_ticks, 1)

    if bid is not None and ask is not None:
        if ask <= bid:
            # locked/crossed book → strict skip
            return None
        mid = (bid + ask) * 0.5
        spread_bps = ((ask - bid) / mid) * 10_000.0
        if math.isfinite(spread_bps) and spread_bps > spread_guard_bps:
            return None

        if _is_finite_positive(inputs.tick_size):
            tick = inputs.tick_size  # type: ignore[assignment]
            half_spread = (ask - bid) * 0.5
            required_ticks = math.ceil(half_spread / tick)
            # 為什麼比較 buffer_ticks float：對應 Rust `f64::from(buffer_ticks)`；
            # required_ticks 從 ceil 是整數，比較仍正確。
            if math.isfinite(required_ticks) and required_ticks > float(buffer_ticks):
                if required_ticks > float(2**32 - 1):
                    # small-tick widening overflow → strict skip
                    return None
                buffer_ticks = int(required_ticks)

    # 對應 Rust：compute_post_only_price(!position_is_long, ...)
    # close long position is sell (is_long=False); close short position is buy (is_long=True)
    return compute_post_only_price(
        is_long=(not position_is_long),
        inputs=inputs,
        fallback_offset_bps=policy.offset_bps,
        buffer_ticks=buffer_ticks,
    )


def compute_post_only_price(
    is_long: bool,
    inputs: MakerPriceInputs,
    fallback_offset_bps: float,
    buffer_ticks: int,
) -> Optional[float]:
    """Rust `compute_post_only_price` 1:1 port (maker_price.rs:252-352)。

    is_long=True → buy side，掛 best_bid - buffer×tick（嚴格被動）
    is_long=False → sell side，掛 best_ask + buffer×tick（嚴格被動）

    為什麼保留 fallback_offset_bps 參數但未使用：與 Rust signature 一致；
    Rust 的 fallback_offset_bps 在 warn log 引用但不參與計算（strict-skip 路徑下
    無 last_price ± offset_bps fallback）。
    fail-closed：tick_size 缺 / 無 BBO / crossed book / 計算後 price ≤ 0 → None。
    """
    if not _is_finite_positive(inputs.tick_size):
        return None
    tick = inputs.tick_size  # type: ignore[assignment]

    bid = inputs.best_bid if _is_finite_positive(inputs.best_bid) else None
    ask = inputs.best_ask if _is_finite_positive(inputs.best_ask) else None

    if bid is not None and ask is not None and ask <= bid:
        # crossed/locked book → strict skip
        return None

    buffer = float(buffer_ticks) * tick
    cross_buffer = tick if buffer_ticks == 0 else buffer

    price: Optional[float] = None
    if is_long:
        if bid is not None:
            price = bid - buffer
        elif ask is not None:
            price = ask - cross_buffer
        else:
            return None
    else:
        if ask is not None:
            price = ask + buffer
        elif bid is not None:
            price = bid + cross_buffer
        else:
            return None

    if price is not None and math.isfinite(price) and price > 0.0:
        return price
    return None


# spec §2.3 Adverse selection / fee saving constants
MAKER_FEE_BPS = 2.0   # DEFAULT_MAKER_FEE 0.0002 → 2.0 bps
TAKER_FEE_BPS = 5.5   # DEFAULT_TAKER_FEE 0.00055 → 5.5 bps
FEE_SAVING_CAP_BPS = TAKER_FEE_BPS - MAKER_FEE_BPS  # 3.5 bps spec §0.2 cap


def compute_fee_saving_bps(
    simulated_fill_px: float,
    actual_taker_px: float,
    position_is_long: bool,
) -> float:
    """依 spec §2.3 fee saving formula。

    fee_saving_bps = (taker_fee - maker_fee) - max(0, slippage_realized_bps)
                   = 3.5 - max(0, slippage)
    slippage_realized_bps:
      - close long (sell): slippage > 0 if simulated < actual (sell at lower price = worse)
      - close short (buy): slippage > 0 if simulated > actual (buy at higher price = worse)

    為什麼僅在 simulated worse 才扣：模擬 fill 比 taker 同價或更好（rare in passive
    maker） → 不扣 slippage cost；冷靜地 cap 在 3.5 bps fee saving。
    """
    # direction_sign: 對 long close (sell)，slippage_realized > 0 if simulated_px < actual_taker_px
    # 對 short close (buy)，slippage_realized > 0 if simulated_px > actual_taker_px
    if position_is_long:
        # sell: lower price = worse
        slippage_raw = (actual_taker_px - simulated_fill_px) / actual_taker_px * 10_000.0
    else:
        # buy: higher price = worse
        slippage_raw = (simulated_fill_px - actual_taker_px) / actual_taker_px * 10_000.0
    slippage_cost = max(0.0, slippage_raw)
    return FEE_SAVING_CAP_BPS - slippage_cost


def compute_adverse_selection_proxy_bps(
    mid_at_fill_plus_60s: Optional[float],
    simulated_fill_px: float,
    position_is_long: bool,
) -> Optional[float]:
    """spec §2.3 adverse selection proxy。

    proxy_bps = (mid_+60s - simulated_fill_px) * direction_sign / simulated_fill_px * 10000
    direction_sign：
      - close long (sell maker fill): market moves DOWN after fill = adverse;
        sign reflects: (mid_after - simulated) * +1 → negative if market went down → adverse
        Wait: original spec §2.3 反向定義：positive = adverse；
        對 sell close：fill 後 market 跌（mid_after < simulated）= 我們本可
        以更低價 sell → 不是 adverse；market 漲（mid_after > simulated）= 我們本
        可以更高價 sell → 是 adverse；對齊 → sell direction_sign = +1。
      - close short (buy maker fill): market UP after fill = adverse buy（本可以
        更高價 buy 喔不對，是本可以更低價 buy → 反）；
        DOWN after fill = adverse （本可以更低價 buy）；對齊 → buy direction_sign = -1.

    為什麼這實現：仔細對 spec wording「positive = market moved against us after our fill」：
      - sell close fill at $100，market 漲到 $101 → 我們收 $100 但其他人現在能收 $101
        → 對「我們」而言，市場相對 fill 已往上 = 我們持倉若無 fill 就更值錢 = adverse
        → proxy = (101 - 100) / 100 * 10000 = +100 bps
        → sell: sign = +1 適用 (mid_after - sim_fill)
      - buy close fill at $100，market 跌到 $99 → 我們付 $100 但現在能付 $99
        → 對「我們」而言，買貴了 = adverse
        → proxy = (99 - 100) / 100 * 10000 = -100；要 +100 → sign = -1
        → buy: (sim_fill - mid_after) = 100 - 99 = +1 → 等同 (mid - sim) * -1

    return None 當 mid_at_fill_plus_60s 不可用（tick 缺失）。
    """
    if mid_at_fill_plus_60s is None or not math.isfinite(mid_at_fill_plus_60s):
        return None
    if simulated_fill_px <= 0:
        return None
    direction_sign = 1.0 if position_is_long else -1.0
    return (
        (mid_at_fill_plus_60s - simulated_fill_px)
        * direction_sign
        / simulated_fill_px
        * 10_000.0
    )
