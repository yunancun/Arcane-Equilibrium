"""
MODULE_NOTE
模塊用途：M4 Stage 1 Python 端 Event-Window Analysis Algorithm-B（per W1-B spec §2.2）。
   3 種 event detector + pre/post window forward return shift + N >= 30 硬 gate。

對齊 Rust m4_miner::event_window — 同 detector 邏輯 + 同 forward shift 公式 +
同 sample gate verdict。

不變量：
   - I-4 強制 N < 30 → 'exploratory'
   - pre window 必排除 event_t 本身
   - post window 必從 event_t + 1 起
   - 同 symbol 連續 event 在 < 2 × max(pre,post) 內合併
"""
from __future__ import annotations

from typing import Sequence


def detect_funding_flip_events(
    funding_rates: Sequence[float], magnitude_gate: float = 0.0001
) -> list[int]:
    """偵測 funding flip event（sign change + |rate| >= magnitude_gate）。

    baseline magnitude_gate = 0.0001（0.01%）per W1-B spec §1.4。
    """
    events: list[int] = []
    for i in range(1, len(funding_rates)):
        prev = funding_rates[i - 1]
        cur = funding_rates[i]
        sign_change = (prev > 0 and cur < 0) or (prev < 0 and cur > 0)
        large_enough = abs(cur) >= magnitude_gate
        if sign_change and large_enough:
            events.append(i)
    return events


def detect_large_funding_spike_events(
    funding_rates: Sequence[float], magnitude_gate: float = 0.001
) -> list[int]:
    """偵測 large funding spike（|rate| >= magnitude_gate）。

    baseline magnitude_gate = 0.001（0.1%）per W1-B spec §2.2.1。
    為什麼不需要 sign change：spike 只關心 magnitude 是否超閾值。
    """
    return [i for i, rate in enumerate(funding_rates) if abs(rate) >= magnitude_gate]


def detect_liquidation_cascade_events(
    cascade_size_usd: Sequence[float], cascade_threshold_usd: float = 5_000_000.0
) -> list[int]:
    """偵測 liquidation cascade event（cascade_size >= threshold）。

    baseline cascade_threshold = 5M USD per W1-B spec §2.2.1。
    Input cascade_size_usd 假定為 5min aggregated bucket（caller 預處理）。
    """
    return [i for i, size in enumerate(cascade_size_usd) if size >= cascade_threshold_usd]


def merge_close_events(
    event_indices: Sequence[int], pre_window: int, post_window: int
) -> list[int]:
    """合併連續 event（< 2 × max(pre,post) 內）為單一 event。

    per W1-B spec §2.2.4 邊界 invariant：避免雙重計算同一 cascade。
    """
    if not event_indices:
        return []
    merge_distance = 2 * max(pre_window, post_window)
    merged: list[int] = []
    last: int | None = None
    for idx in event_indices:
        if last is None or idx - last >= merge_distance:
            merged.append(idx)
            last = idx
        # 否則合併：保留更早的 idx（first-occurrence semantic）
    return merged


def event_window_forward_shift(
    forward_return_bps: Sequence[float],
    event_index: int,
    pre_window: int,
    post_window: int,
) -> tuple[float, float, float] | None:
    """單一 event 算 pre/post window forward return mean + effect。

    公式（per W1-B spec §2.2.2）：
       pre  = mean(forward_return[event_t - pre_window : event_t])
       post = mean(forward_return[event_t + 1 : event_t + post_window + 1])
       effect = post - pre

    為什麼跳過 event bar 本身：event 本身的 bar 屬 transition zone，含 event signal
    會 leak 進 post window（per W1-B I-1）。
    """
    n = len(forward_return_bps)
    if event_index < pre_window or event_index + post_window + 1 > n:
        return None
    pre_slice = forward_return_bps[event_index - pre_window : event_index]
    post_slice = forward_return_bps[event_index + 1 : event_index + post_window + 1]
    if not pre_slice or not post_slice:
        return None
    pre_mean = sum(pre_slice) / len(pre_slice)
    post_mean = sum(post_slice) / len(post_slice)
    effect = post_mean - pre_mean
    return pre_mean, post_mean, effect


def event_window_sample_gate(n_events: int) -> str:
    """Event-window sample-gate verdict — per W1-B spec §2.2.3 + I-4。

    Returns: 'preregistered_candidate' / 'exploratory'

    為什麼 30：Mann-Whitney U power > 0.5 at d=0.5 medium effect。
    為什麼 hard gate 而非 soft warning：避免 N=5 的 spurious 顯著被誤 promote。
    """
    if n_events < 30:
        return "exploratory"
    return "preregistered_candidate"
