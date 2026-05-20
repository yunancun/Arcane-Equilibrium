"""
MODULE_NOTE
模塊用途：Phase 1b sim harness queue-aware bias 修正（P2-SIM-QUEUE-AWARE-ADJUSTMENT v55）。

為什麼存在：原 `_did_fill_within_window` 用 BBO-cross-proxy 判 fill — best_bid ≥ limit
或 best_ask ≤ limit within timeout 即視為成交。此 proxy 系統性樂觀，因為：
  1. 沒考慮 queue position：my order 在 queue 末尾 vs 隊首 fill 機率不同；
  2. 沒對齊 trade tape：只看 BBO touch 不看實際 taker hit volume；
  3. PA cell selection report §5.1 指出 proxy 高估 ~10-15pp（21pp empirical anchor
     per QA 6/3 attempts/fills CI）。

設計：保守線性飽和 model — 把 `binary cross 是否觸發` 拆成兩步：
  step 1: BBO-cross-proxy 仍是 necessary condition（cross 才是 fill 候選）；
  step 2: 在 cross moment，計 queue_factor = my_qty / (my_qty + depth_5)，
          降低 fill_probability_adjusted = 1.0 × (1 - QUEUE_WEIGHT × queue_factor)；
  step 3: cell-level aggregate 用 `mean(fill_p_adjusted)` 而非 `n_fills / n_eligible`，
          保留 per-fill binary semantics 不破壞 backward compat。

為什麼用 ob_snapshots.bid_depth_5 / ask_depth_5 而非 market_tickers.bid_size：
empirical query 14d / 16.3M rows：market_tickers.bid_size 僅 1.15% > 0；
ob_snapshots.bid_depth_5 100% 有效（per 14d V094 sample）。粒度 1m aggregate
（vs sim 60-90s timeout window）勉強夠用，缺失時 fail-closed 退回 proxy 不調整。

主要函數：compute_queue_factor / apply_queue_adjustment / clamp_queue_factor_max。

依賴：std math only（純函數，無 IO，可單測）。

硬邊界：
  - depth_5 <= 0 或缺失 → queue_factor=None（caller 退回 proxy 不調整，不擴大樂觀）；
  - my_qty <= 0 → queue_factor=None（不正常 input）；
  - queue_factor ∈ [0, 1]，QUEUE_WEIGHT 可調但默認校在使 14d sample bias 降至 ≤ 5pp。
  - 不改 binary `simulated_fill` field（per-fill 仍是 {True, False}）；
    僅 aggregate 額外提供 queue_adjusted_fill_rate field。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# 預設 queue factor 權重。
# 為什麼 0.40：
#   - PA cell selection §5.1 標 bias ~10pp 保守估計；
#   - 線性 model 在 my_qty=depth_5 時 queue_factor=0.5，乘 0.40 = 0.20 → 對應
#     ~20pp downward adjustment；
#   - 若 my_qty << depth_5（small order），queue_factor → 0，queue 維度幾乎不調整；
#   - 此常數可由 regression CLI 動態 sweep 調整；source code 不寫硬編碼覆蓋。
DEFAULT_QUEUE_WEIGHT = 0.40

# 預設 base rejection rate（非 queue 來源的 systematic fill failure）。
# 為什麼引入：14d V094 regression 揭露 BBO-cross-proxy 對 close path
# 不只是「queue position」問題；還有 PostOnly reject / cancel race /
# trade-tape sparse 等與 queue 無關的 fail mode。empirical 14d gap ~61pp，
# queue-only model 無法解釋（factor < 0.02 主導）；base_rejection 是
# 「BBO touch ≠ taker fill on my side」的 systematic 折扣。
# 為什麼默認 0.0：a priori 不假設 base rejection 存在；regression CLI
# 用 `--base-rejection` 顯式 inject empirical value（透明，無 overfitting
# fitting trick）。
#
# ⚠️ FAMILY-SPECIFIC 警告（per E2 review MEDIUM-1, 2026-05-20）：
# `base_rejection_rate` 是 **family-specific empirical anchor 參數**，不是物理常數。
# 適用範圍：每個 strategy family（grid / phys_lock_giveback / phys_lock_stale_roc_neg ...）
# 必須各自用對應 anchor cell（如 G-AB-01-C90 / PG-AB-01-C15 / PS-AB-01-C10）跑
# regression 校自家 base_rejection；不可直接外推。
# 為什麼：不同 family 的 PostOnly path / cancel race / fallback timing 不同
# 造成 non-queue fail mode 分布不同；single value 對全 family 套用會錯估 bias。
# 當前 source 維持 default=0.0 不 hardcode 任一 family 的 calibrated value；
# regression CLI 透過 `--base-rejection` 顯式 inject + JSON artifact 記錄
# anchor cell family，避免結論被誤外推。
DEFAULT_BASE_REJECTION_RATE = 0.0


@dataclass(frozen=True)
class QueueDepthSample:
    """單一 ob_snapshots 1m bucket 對應的 queue depth 樣本。

    為什麼 frozen：snapshot timepoint immutable；hash 用於 dedupe。
    不變量：bid_depth_5 ≥ 0，ask_depth_5 ≥ 0（PG schema constraint）。
    """
    ts_bucket_start: object  # datetime
    symbol: str
    bid_depth_5: Optional[float]
    ask_depth_5: Optional[float]


def compute_queue_factor(
    my_qty: float,
    same_side_depth_5: Optional[float],
) -> Optional[float]:
    """線性飽和 queue factor。

    公式：queue_factor = my_qty / (my_qty + depth_5)

    語義：
      - my_qty=0 → 0（不存在 placement，proxy 不需調整）；
      - my_qty<<depth_5 → 接近 0（順位前，proxy 樂觀偏差小）；
      - my_qty=depth_5 → 0.5（順位中段）；
      - my_qty>>depth_5 → 接近 1（順位末，proxy 嚴重高估）。

    為什麼選此公式：
      - 連續、單調、saturated bounded [0,1]；
      - 不需 calibration regression 額外參數（QUEUE_WEIGHT 在外層 apply）；
      - 對「placement BBO 同側 size 越大 fill 機率越低」物理直觀（task brief 要求）；
      - 與 standard queue-position model（Roll 1984 / Glosten-Milgrom）的 single-
        parameter linear approximation 一致。

    局限：
      - 不模擬真實 limit-order-book ahead-volume；只用 top-5 depth_5 aggregate；
      - 不考慮 order placement timing（先掛單 vs 後掛單）；
      - 不模擬 partial fill（pull-back scenario）；
      - 對 close-only / IOC / postOnly reject 路徑 inseparable。

    fail-closed：
      - depth_5 None / <= 0 → 回 None（caller 退回 proxy 不調整）；
      - my_qty <= 0 → 回 None（不正常 input）。
    """
    if my_qty is None or not math.isfinite(my_qty) or my_qty <= 0:
        return None
    if same_side_depth_5 is None or not math.isfinite(same_side_depth_5):
        return None
    if same_side_depth_5 <= 0:
        return None
    denom = my_qty + same_side_depth_5
    if denom <= 0:
        return None
    factor = my_qty / denom
    # clamp [0, 1]（理論上不會超界，但浮點安全）
    if factor < 0.0:
        return 0.0
    if factor > 1.0:
        return 1.0
    return factor


def apply_queue_adjustment(
    fill_probability_proxy: float,
    queue_factor: Optional[float],
    queue_weight: float = DEFAULT_QUEUE_WEIGHT,
    base_rejection_rate: float = DEFAULT_BASE_REJECTION_RATE,
) -> float:
    """套用 queue-aware adjustment 至 BBO-cross-proxy fill probability。

    完整公式：
      fill_p_adjusted = fill_p_proxy
                       × (1 - base_rejection_rate)
                       × (1 - queue_weight × queue_factor)

    兩維度 down-weighting：
      1. base_rejection_rate：非 queue 來源的 systematic fail mode
         （PostOnly reject / cancel race / trade-tape sparse / BBO touch ≠ taker hit）；
         a priori 默認 0；用 regression CLI 對 empirical 14d sample 校；
      2. queue_factor × queue_weight：queue position 來源的 down-weight
         （my_qty 相對 depth_5 比例）；理論派生 physical model。

    為什麼乘性 down-weight 而非加性：
      - 加性會在 fill_p_proxy=0（cross 沒發生）時 produce 負概率，需額外 clamp；
      - 乘性自然保持 fill_p_proxy=0 → fill_p_adjusted=0（proxy 沒 cross 則 adjusted
        必 0），不破壞「no cross → no fill」necessary condition；
      - 兩 factor 互不耦合（base_rejection 與 queue_factor 各自獨立，物理上獨立 fail mode）。

    queue_factor=None → 只套 base_rejection，不調 queue（fail-closed）。

    回傳保證在 [0, 1]。
    """
    if not math.isfinite(fill_probability_proxy):
        return 0.0
    if fill_probability_proxy <= 0.0:
        return 0.0
    if fill_probability_proxy >= 1.0:
        # cap at 1 for safety against accumulated float drift
        fill_probability_proxy = 1.0
    # clamp base_rejection_rate
    if not math.isfinite(base_rejection_rate):
        base_rejection_rate = 0.0
    if base_rejection_rate < 0.0:
        base_rejection_rate = 0.0
    elif base_rejection_rate > 1.0:
        base_rejection_rate = 1.0
    base_factor = 1.0 - base_rejection_rate
    # queue factor 處理（None / NaN → 不調 queue 維度）
    queue_adjustment = 1.0
    if queue_factor is not None and math.isfinite(queue_factor):
        if queue_factor < 0.0:
            queue_factor = 0.0
        elif queue_factor > 1.0:
            queue_factor = 1.0
        local_weight = queue_weight
        if not math.isfinite(local_weight):
            local_weight = 0.0
        elif local_weight < 0.0:
            local_weight = 0.0
        elif local_weight > 1.0:
            local_weight = 1.0
        queue_adjustment = 1.0 - local_weight * queue_factor
        if queue_adjustment < 0.0:
            queue_adjustment = 0.0
        elif queue_adjustment > 1.0:
            queue_adjustment = 1.0
    return fill_probability_proxy * base_factor * queue_adjustment


def select_same_side_depth(
    position_is_long: bool,
    depth_sample: Optional[QueueDepthSample],
) -> Optional[float]:
    """根據 close direction 選 depth_5 側。

    為什麼這方向定義：
      - position_is_long=True → close 是 SELL limit → my order placed at ASK side
        → 我 ahead-of-me 的 same-side queue 是 ask_depth_5；
      - position_is_long=False → close 是 BUY limit → my order placed at BID side
        → ahead-of-me queue 是 bid_depth_5。

    depth_sample=None → 回 None（caller 退回 proxy 不調整）。
    """
    if depth_sample is None:
        return None
    if position_is_long:
        return depth_sample.ask_depth_5
    return depth_sample.bid_depth_5
