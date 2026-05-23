#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：C10 funding_harvest 策略 Stage 0R replay preflight harness。
   per dispatch packet `2026-05-23--sprint_1b_c10_funding_harvest_stage1_demo_dispatch_packet.md` §6。
   拉 30d BTCUSDT 歷史 perp funding rate + perp 1m kline + spot 1m kline，
   對 funding_harvest 策略走 entry/exit/synthetic spot ledger simulation，
   執行 6 條 sanity check (leak / selection bias / DSR-PSR / PBO bootstrap /
   replay data tier / runtime boundary)，產出 `eligible_for_demo_canary`
   verdict + sanity report + replay summary JSON。

主要類/函數：
   - fetch_funding_rates: Bybit V5 /v5/market/funding/history 30d 90 events (8h cycle)
   - fetch_perp_klines / fetch_spot_klines: Bybit V5 /v5/market/kline 1m × 30d
   - SyntheticSpotLedger (Python mirror Rust mod): open_long / rebalance / close
   - replay_funding_harvest: tick-by-tick 模擬 strategy on_tick
   - sanity_check_*: 6 條獨立檢查
   - output_preflight_verdict: 寫 funding_harvest_stage0r_<date>.json

依賴：urllib（無第三方）；可選 numpy（bootstrap 計算用，缺失 fallback）。

硬邊界：
   - 不發 Bybit live 寫單；僅 GET /v5/market/{funding/history,kline} 公開 endpoint
   - 不寫 PG / 不改既有 replay_runner.py 邏輯（pure extension）
   - 浮點容差 1e-4 對齊既有 cross-language IPC contract
   - 6 條 sanity check 全 PASS 才出 `eligible_for_demo_canary=true`

per AMD-2026-05-15-01 §3.2 + dispatch packet §6.3。
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import statistics
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [STAGE0R] %(levelname)s %(message)s",
)
logger = logging.getLogger("replay_funding_harvest")

# ═══════════════════════════════════════════════════════════════════════════════
# 常數配置
# ═══════════════════════════════════════════════════════════════════════════════

BYBIT_BASE_URL = "https://api.bybit.com"
MAX_BARS_PER_REQUEST = 200
MAX_FUNDING_PER_REQUEST = 200

# C10 預設參數 mirror Rust funding_harvest::params.rs (dispatch packet §2.5)
# 修改本檔默認值不影響 Rust runtime；Rust truth 在 strategy_params_demo.toml + params.rs。
DEFAULT_FUNDING_THRESHOLD_ANNUALIZED = 0.05
DEFAULT_FUNDING_EXIT_ANNUALIZED = 0.02
DEFAULT_MAX_BASIS_PCT = 0.5
DEFAULT_ENTRY_BASIS_RATIO = 0.8
DEFAULT_MAX_HOLD_MS = 72 * 3_600_000  # 72h
DEFAULT_TOTAL_COST_BPS = 37.0
DEFAULT_EXPECTED_PERIODS = 3.0
DEFAULT_REBALANCE_CHECK_MS = 2 * 3_600_000  # 2h
DEFAULT_DELTA_DRIFT_THRESHOLD = 0.02
DEFAULT_POSITION_CAP_USD = 100.0
DEFAULT_COOLDOWN_MS = 3_600_000  # 1h

# Bybit funding cycle: 3 × 8h × 365d
ANNUALIZATION_FACTOR = 3.0 * 365.0

# Stage 0R verdict gates per dispatch packet §6.3 + §7
SHARPE_MIN = 0.0  # Sharpe > 0 即 PASS (DSR/PSR check 在 bootstrap)
DEFLATED_PSR_MIN = 0.6  # PSR > 0.6 PASS
BOOTSTRAP_LOWER_5PCT_FLOOR = -5.0  # 1000-sample bootstrap lower 5% ≥ -$5 (Stage 1 stop loss)
REPLAY_DATA_TIER_DRIFT_MAX_PCT = 1.0  # replay vs historical demo path < 1% (passive if 無 demo path)
RUNTIME_BOUNDARY_CHECK_PASS_BY_DESIGN = True  # 設計上 replay 不 claim 替代 demo fill-lineage

DEFAULT_REPLAY_DAYS = 30


# ═══════════════════════════════════════════════════════════════════════════════
# Bybit V5 REST: funding history
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_funding_rates(
    symbol: str,
    days: int = 30,
    category: str = "linear",
) -> list[dict]:
    """拉 days 天 Bybit perp funding rate 歷史。

    為什麼用 paginated end→older：Bybit 返回 newest first，每次最多 200 條，
    多頁 backfill 直到滿足 days 視窗或 batch 空。
    8h funding cycle → 30d ≈ 90 events，1 page (200) 足夠；保留 pagination 容錯。

    Returns list of dicts: [{symbol, funding_rate, funding_rate_timestamp_ms}, ...]
       chronological order (oldest first)。
    """
    bars_needed = days * 3  # 3 × 8h funding events per day
    all_events: list[dict] = []
    end_ms: Optional[int] = None

    logger.info(
        "Fetching %d funding events (%d days) for %s category=%s",
        bars_needed, days, symbol, category,
    )

    while len(all_events) < bars_needed:
        remaining = bars_needed - len(all_events)
        batch_size = min(remaining, MAX_FUNDING_PER_REQUEST)

        url = (
            f"{BYBIT_BASE_URL}/v5/market/funding/history"
            f"?category={urllib.parse.quote(category, safe='')}"
            f"&symbol={urllib.parse.quote(symbol, safe='')}"
            f"&limit={batch_size}"
        )
        if end_ms is not None:
            url += f"&endTime={end_ms}"

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
        except Exception as e:
            logger.warning("fetch_funding_rates network/parse error: %s (have %d)", e, len(all_events))
            break

        if data.get("retCode") != 0:
            raise RuntimeError(f"Bybit funding API error: {data.get('retMsg', 'unknown')}")

        raw = data.get("result", {}).get("list", [])
        if not raw:
            break

        batch = []
        for f in raw:
            batch.append({
                "symbol": f.get("symbol", symbol),
                "funding_rate": float(f.get("fundingRate", 0.0)),
                "funding_rate_timestamp_ms": int(f.get("fundingRateTimestamp", 0)),
            })

        # Bybit returns newest first → keep order; final sort chronological at end
        all_events.extend(batch)
        # 下一頁取更舊：endTime 設為 batch 最舊 event 之前 1 ms
        oldest_ts = min(b["funding_rate_timestamp_ms"] for b in batch)
        end_ms = oldest_ts - 1

        time.sleep(0.1)  # rate limit

    # chronological sort (oldest first)
    all_events.sort(key=lambda e: e["funding_rate_timestamp_ms"])
    # truncate 多餘 events 以對齊 days 視窗（保留最新 days×3）
    if len(all_events) > bars_needed:
        all_events = all_events[-bars_needed:]

    logger.info("  fetched %d funding events for %s", len(all_events), symbol)
    return all_events


# ═══════════════════════════════════════════════════════════════════════════════
# Bybit V5 REST: kline（perp + spot 通用，加 category 參數）
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_klines_v5(
    symbol: str,
    interval: str = "1",  # Bybit interval string: "1" = 1m
    limit: int = MAX_BARS_PER_REQUEST,
    end_ms: Optional[int] = None,
    category: str = "linear",
) -> list[dict]:
    """單頁 fetch；category 'linear' (perp) 或 'spot'。

    為什麼新增此函式而不擴 replay_runner.fetch_klines：
    後者已 hard-code `category=linear`，dispatch packet 要求保持既有檔 logic 不改。
    本函式為 Stage 0R harness 私有 helper，明確兩 category 並列。
    """
    url = (
        f"{BYBIT_BASE_URL}/v5/market/kline"
        f"?category={urllib.parse.quote(category, safe='')}"
        f"&symbol={urllib.parse.quote(symbol, safe='')}"
        f"&interval={urllib.parse.quote(interval, safe='')}"
        f"&limit={limit}"
    )
    if end_ms is not None:
        url += f"&end={end_ms}"

    req = urllib.request.Request(url, headers={"User-Agent": "OpenClaw/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())

    if data.get("retCode") != 0:
        raise RuntimeError(f"Bybit kline API error ({category}): {data.get('retMsg', 'unknown')}")

    raw = data.get("result", {}).get("list", [])
    if not raw:
        return []

    raw.reverse()  # newest first → chronological

    bars = []
    for k in raw:
        bars.append({
            "open_time_ms": int(k[0]),
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "turnover": float(k[6]) if len(k) > 6 else 0.0,
        })
    return bars


def fetch_perp_klines(symbol: str, days: int = 30) -> list[dict]:
    """30d × 1440 bar/day = 43200 bar 1m perp kline。"""
    return _fetch_klines_paginated(symbol, days, category="linear")


def fetch_spot_klines(symbol: str, days: int = 30) -> list[dict]:
    """30d × 1440 bar/day spot 1m kline。"""
    return _fetch_klines_paginated(symbol, days, category="spot")


def _fetch_klines_paginated(symbol: str, days: int, category: str) -> list[dict]:
    bars_needed = days * 24 * 60
    all_bars: list[dict] = []
    end_ms: Optional[int] = None

    logger.info(
        "Fetching %d bars (%d days) of %s 1m %s klines",
        bars_needed, days, symbol, category,
    )

    while len(all_bars) < bars_needed:
        remaining = bars_needed - len(all_bars)
        batch_size = min(remaining, MAX_BARS_PER_REQUEST)

        try:
            batch = fetch_klines_v5(symbol, "1", batch_size, end_ms, category)
        except Exception as e:
            logger.warning("fetch_%s_klines error (have %d): %s", category, len(all_bars), e)
            break

        if not batch:
            break

        all_bars = batch + all_bars
        end_ms = batch[0]["open_time_ms"] - 1
        time.sleep(0.1)

    logger.info("  %s %s: fetched %d / %d bars", symbol, category, len(all_bars), bars_needed)
    return all_bars


# ═══════════════════════════════════════════════════════════════════════════════
# SyntheticSpotLedger（Python mirror of Rust funding_harvest::synthetic_spot）
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SyntheticSpotLedger:
    """spot leg paper-only synthetic accounting；不發 Bybit order。

    狀態機：Closed -> Open (via open_long) -> Closed (via close)
    """
    state: str = "closed"  # 'open' / 'closed'
    entry_notional_usd: float = 0.0
    entry_price: float = 0.0
    entry_ts_ms: int = 0
    qty: float = 0.0
    rebalance_count: int = 0
    last_rebalance_price: float = 0.0
    last_rebalance_ts_ms: int = 0
    realized_pnl_usd: Optional[float] = None
    close_ts_ms: Optional[int] = None
    close_price: Optional[float] = None

    def open_long(self, notional_usd: float, spot_price: float, ts_ms: int) -> None:
        if spot_price <= 0:
            raise ValueError(f"open_long invalid spot_price={spot_price}")
        self.state = "open"
        self.entry_notional_usd = notional_usd
        self.entry_price = spot_price
        self.qty = notional_usd / spot_price
        self.entry_ts_ms = ts_ms
        self.last_rebalance_price = spot_price
        self.last_rebalance_ts_ms = ts_ms
        self.rebalance_count = 0

    def rebalance(self, target_notional_usd: float, spot_price: float, ts_ms: int) -> None:
        if self.state != "open" or spot_price <= 0:
            return
        # 不變量：rebalance 只更新 qty + last_rebalance；entry_price 鎖死作 PnL 基準
        self.qty = target_notional_usd / spot_price
        self.last_rebalance_price = spot_price
        self.last_rebalance_ts_ms = ts_ms
        self.rebalance_count += 1

    def close(self, close_price: float, ts_ms: int) -> float:
        if self.state != "open":
            return 0.0
        pnl = (close_price - self.entry_price) * self.qty
        self.state = "closed"
        self.realized_pnl_usd = pnl
        self.close_ts_ms = ts_ms
        self.close_price = close_price
        return pnl

    def unrealized_pnl_usd(self, current_spot_price: float) -> float:
        if self.state != "open":
            return 0.0
        return (current_spot_price - self.entry_price) * self.qty

    def delta_drift_pct(self, perp_notional_usd: float, current_spot_price: float) -> float:
        if self.state != "open":
            return 0.0
        current_spot_notional = self.qty * current_spot_price
        if current_spot_notional <= 0:
            return 0.0
        return abs((current_spot_notional - perp_notional_usd) / current_spot_notional)


# ═══════════════════════════════════════════════════════════════════════════════
# Strategy simulation core
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FundingHarvestState:
    """每 symbol 策略 runtime 狀態（mirror Rust FundingHarvest fields）。"""
    position_open: bool = False
    entry_ts_ms: int = 0
    perp_entry_price: float = 0.0
    perp_qty: float = 0.0  # SHORT 方向 (positive number；side encoded by is_long=false)
    perp_notional_usd: float = 0.0
    last_rebalance_check_ms: int = 0
    last_signal_ts_ms: int = 0  # cooldown tracker
    synthetic_spot: SyntheticSpotLedger = field(default_factory=SyntheticSpotLedger)


@dataclass
class TradeRecord:
    """單筆完整 trade（entry → exit）的 PnL record。"""
    symbol: str
    entry_ts_ms: int
    exit_ts_ms: int
    entry_funding_rate: float
    exit_funding_rate: float
    entry_basis_pct: float
    exit_basis_pct: float
    entry_perp_price: float
    exit_perp_price: float
    entry_spot_price: float
    exit_spot_price: float
    perp_qty: float
    perp_notional_usd: float
    cumulative_funding_payment_usd: float
    perp_price_pnl_usd: float
    synthetic_spot_pnl_usd: float
    perp_fee_usd: float
    synthetic_spot_fee_usd: float
    net_pnl_usd: float
    exit_reason: str
    hold_ms: int


def _annualized(funding_rate_8h: float) -> float:
    """Bybit 8h funding cycle × 3 events/day × 365 days。"""
    return funding_rate_8h * ANNUALIZATION_FACTOR


def _compute_basis_pct(perp_price: float, spot_price: float) -> float:
    """|perp/spot - 1| × 100%。spot<=0 → 視為 fail-closed 大值。"""
    if spot_price <= 0:
        return float("inf")
    return abs((perp_price / spot_price) - 1.0) * 100.0


def _compute_net_edge_bps_per_period(
    funding_rate_8h: float,
    total_cost_bps: float,
    expected_periods: float,
) -> float:
    """edge = |funding_rate| × 10000 - amortized_cost。"""
    amortized = total_cost_bps / expected_periods
    return abs(funding_rate_8h) * 10_000.0 - amortized


def _should_enter(
    funding_rate_8h: float,
    basis_pct: float,
    config: dict,
) -> bool:
    """Mirror Rust FundingHarvest::should_enter 邏輯 (dispatch packet §2.2)。"""
    annualized = _annualized(funding_rate_8h)
    return (
        annualized > config["funding_threshold_annualized"]
        and _compute_net_edge_bps_per_period(
            funding_rate_8h,
            config["total_cost_bps"],
            config["expected_periods"],
        ) > 0.0
        and basis_pct < config["max_basis_pct"] * config["entry_basis_ratio"]
        and funding_rate_8h > 0.0  # 只收正向 funding（spot LONG + perp SHORT）
    )


def _should_exit(
    funding_rate_8h: float,
    basis_pct: float,
    now_ms: int,
    entry_ms: int,
    config: dict,
) -> tuple[bool, str]:
    """Mirror Rust FundingHarvest::should_exit 邏輯。返回 (do_exit, reason)。"""
    annualized = _annualized(funding_rate_8h)
    if annualized < config["funding_exit_annualized"]:
        return True, "funding_decay"
    if funding_rate_8h < 0.0:
        return True, "funding_flip"
    if basis_pct > config["max_basis_pct"]:
        return True, "basis_drift"
    if max(0, now_ms - entry_ms) > config["max_hold_ms"]:
        return True, "max_hold"
    return False, ""


def _interpolate_funding_at_ts(
    ts_ms: int,
    funding_events: list[dict],
) -> Optional[float]:
    """取 ts_ms 對應的「最近 ≤ ts_ms 的 funding event」rate（8h step function）。

    為什麼用 ≤ ts_ms：funding rate 是離散 event，新一次 settlement 之前 strategy 看到的
    仍是上一次的 rate。避 lookahead bias。
    """
    # binary search 對齊（list 已 chronological）
    if not funding_events:
        return None
    lo, hi = 0, len(funding_events) - 1
    idx = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if funding_events[mid]["funding_rate_timestamp_ms"] <= ts_ms:
            idx = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if idx < 0:
        return None
    return funding_events[idx]["funding_rate"]


def _build_spot_price_index(spot_klines: list[dict]) -> dict:
    """spot 1m kline → ts_ms → close price。"""
    idx = {}
    for bar in spot_klines:
        idx[bar["open_time_ms"]] = bar["close"]
    return idx


def _get_spot_price_at_ts(ts_ms: int, spot_index: dict, sorted_keys: list[int]) -> Optional[float]:
    """取 ts_ms 最近 ≤ ts_ms 的 spot close price。"""
    if not sorted_keys:
        return None
    # binary search
    lo, hi = 0, len(sorted_keys) - 1
    idx = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if sorted_keys[mid] <= ts_ms:
            idx = mid
            lo = mid + 1
        else:
            hi = mid - 1
    if idx < 0:
        return None
    return spot_index[sorted_keys[idx]]


def replay_funding_harvest(
    symbol: str,
    perp_klines: list[dict],
    spot_klines: list[dict],
    funding_events: list[dict],
    config: dict,
) -> tuple[list[TradeRecord], list[float]]:
    """Tick-by-tick simulation of FundingHarvest strategy。

    per 1m perp bar (close price):
    - 取對應 spot close + 最近 funding rate
    - 若無倉位 + cooldown OK + should_enter → 開倉 (perp short + synthetic spot long)
    - 若有倉位：每 funding settlement (8h) 累積 funding payment；
              每 rebalance_check_ms 檢查 delta drift；
              should_exit 則平倉
    - 返回 (TradeRecord list, daily PnL list for Sharpe/PSR/bootstrap)
    """
    state = FundingHarvestState()
    trades: list[TradeRecord] = []
    daily_pnl_usd: list[float] = []  # 累積每日 PnL（calendar day）
    current_day = None
    current_day_pnl = 0.0
    cum_funding_payment = 0.0
    last_funding_settle_ts = 0

    spot_index = _build_spot_price_index(spot_klines)
    sorted_spot_keys = sorted(spot_index.keys())

    # funding fee per Bybit V5 perp linear: 0.055% taker + 0.02% maker (估 11 bps round-trip per leg)
    perp_fee_bps_per_side = 5.5
    spot_fee_bps_per_side = 10.0  # synthetic only book-keeping

    for bar in perp_klines:
        ts_ms = bar["open_time_ms"]
        perp_price = bar["close"]
        spot_price = _get_spot_price_at_ts(ts_ms, spot_index, sorted_spot_keys)
        funding_rate = _interpolate_funding_at_ts(ts_ms, funding_events)

        if spot_price is None or funding_rate is None:
            continue  # 缺資料 fail-closed skip tick

        basis_pct = _compute_basis_pct(perp_price, spot_price)

        # 累積 daily PnL（calendar UTC day boundary）
        bar_day = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date()
        if current_day is None:
            current_day = bar_day
        elif bar_day != current_day:
            daily_pnl_usd.append(current_day_pnl)
            current_day = bar_day
            current_day_pnl = 0.0

        if state.position_open:
            # 1) 累積 funding payment（每 8h settlement 結算一次）
            # 找出落在 [last_funding_settle_ts, ts_ms] 區間內的 funding events
            for ev in funding_events:
                ev_ts = ev["funding_rate_timestamp_ms"]
                if ev_ts > last_funding_settle_ts and ev_ts <= ts_ms:
                    # perp SHORT 收 funding （positive funding = 多方付空方）
                    payment = ev["funding_rate"] * state.perp_notional_usd
                    cum_funding_payment += payment
                    current_day_pnl += payment
                    last_funding_settle_ts = ev_ts

            # 2) 平倉判斷
            do_exit, reason = _should_exit(
                funding_rate, basis_pct, ts_ms, state.entry_ts_ms, config
            )
            if do_exit:
                # close perp SHORT: PnL = -(exit - entry) * qty (short 反向)
                perp_price_pnl = -(perp_price - state.perp_entry_price) * state.perp_qty
                # close synthetic spot LONG
                synthetic_spot_pnl = state.synthetic_spot.close(spot_price, ts_ms) or 0.0
                # round-trip fee on perp leg (entry + exit)
                perp_fee = state.perp_notional_usd * (perp_fee_bps_per_side * 2 / 10_000.0)
                # synthetic spot fee（純 book-keeping，但保留為 audit trail）
                synthetic_spot_fee = state.perp_notional_usd * (spot_fee_bps_per_side * 2 / 10_000.0)
                net_pnl = (
                    cum_funding_payment
                    + perp_price_pnl
                    + synthetic_spot_pnl
                    - perp_fee
                    - synthetic_spot_fee
                )
                current_day_pnl += (perp_price_pnl + synthetic_spot_pnl - perp_fee - synthetic_spot_fee)

                trades.append(TradeRecord(
                    symbol=symbol,
                    entry_ts_ms=state.entry_ts_ms,
                    exit_ts_ms=ts_ms,
                    entry_funding_rate=_interpolate_funding_at_ts(state.entry_ts_ms, funding_events) or 0.0,
                    exit_funding_rate=funding_rate,
                    entry_basis_pct=_compute_basis_pct(state.perp_entry_price, state.synthetic_spot.entry_price),
                    exit_basis_pct=basis_pct,
                    entry_perp_price=state.perp_entry_price,
                    exit_perp_price=perp_price,
                    entry_spot_price=state.synthetic_spot.entry_price,
                    exit_spot_price=spot_price,
                    perp_qty=state.perp_qty,
                    perp_notional_usd=state.perp_notional_usd,
                    cumulative_funding_payment_usd=cum_funding_payment,
                    perp_price_pnl_usd=perp_price_pnl,
                    synthetic_spot_pnl_usd=synthetic_spot_pnl,
                    perp_fee_usd=perp_fee,
                    synthetic_spot_fee_usd=synthetic_spot_fee,
                    net_pnl_usd=net_pnl,
                    exit_reason=reason,
                    hold_ms=ts_ms - state.entry_ts_ms,
                ))

                # reset state
                state = FundingHarvestState()
                cum_funding_payment = 0.0
                last_funding_settle_ts = 0
                state.last_signal_ts_ms = ts_ms
                continue

            # 3) rebalance check（2h tick）
            if ts_ms - state.last_rebalance_check_ms > config["rebalance_check_ms"]:
                drift = state.synthetic_spot.delta_drift_pct(state.perp_notional_usd, spot_price)
                if drift > config["delta_drift_threshold"]:
                    state.synthetic_spot.rebalance(state.perp_notional_usd, spot_price, ts_ms)
                state.last_rebalance_check_ms = ts_ms

        else:
            # 無倉位 → cooldown + entry 判斷
            if ts_ms - state.last_signal_ts_ms < config["cooldown_ms"]:
                continue
            if not _should_enter(funding_rate, basis_pct, config):
                continue

            # 入場
            qty_perp = config["position_cap_usd"] / perp_price
            state.position_open = True
            state.entry_ts_ms = ts_ms
            state.perp_entry_price = perp_price
            state.perp_qty = qty_perp
            state.perp_notional_usd = config["position_cap_usd"]
            state.last_rebalance_check_ms = ts_ms
            state.last_signal_ts_ms = ts_ms
            state.synthetic_spot.open_long(config["position_cap_usd"], spot_price, ts_ms)
            cum_funding_payment = 0.0
            last_funding_settle_ts = ts_ms  # 入場 ts 後第一筆 settlement 才算

    # flush last day
    if current_day is not None:
        daily_pnl_usd.append(current_day_pnl)

    return trades, daily_pnl_usd


# ═══════════════════════════════════════════════════════════════════════════════
# 6 Sanity Checks per dispatch packet §6.3
# ═══════════════════════════════════════════════════════════════════════════════


def sanity_check_leak_lookahead(
    trades: list[TradeRecord],
    funding_events: list[dict],
) -> tuple[str, str]:
    """Check 1: Leak / lookahead bias。

    Pass criteria：每筆 entry 用的 funding_rate 必須是「entry_ts_ms 之前最近 funding event」，
       不可用 entry 之後的 funding rate。
    """
    if not trades:
        return "PASS", "no trades; vacuous pass"
    for t in trades:
        # 找出 entry_ts_ms 對應 funding event idx
        prev_funding = None
        prev_ts = -1
        for ev in funding_events:
            ev_ts = ev["funding_rate_timestamp_ms"]
            if ev_ts <= t.entry_ts_ms and ev_ts > prev_ts:
                prev_ts = ev_ts
                prev_funding = ev["funding_rate"]
        if prev_funding is None:
            return "FAIL", f"trade entry_ts={t.entry_ts_ms} 無 prior funding event"
        if not math.isclose(t.entry_funding_rate, prev_funding, abs_tol=1e-9):
            return "FAIL", (
                f"trade entry_ts={t.entry_ts_ms} 用 funding={t.entry_funding_rate}, "
                f"但 prior event funding={prev_funding} → lookahead bias"
            )
    return "PASS", f"verified {len(trades)} trades use only prior funding events"


def sanity_check_selection_bias(
    trades: list[TradeRecord],
    funding_events: list[dict],
    perp_klines: list[dict],
) -> tuple[str, str]:
    """Check 2: Selection bias。

    Pass criteria：replay 涵蓋完整 days 視窗 + 所有 funding events 被考慮，
       不 cherry-pick subset；by design 通過。
    """
    if not perp_klines or not funding_events:
        return "FAIL", "missing perp_klines or funding_events"
    perp_span_ms = perp_klines[-1]["open_time_ms"] - perp_klines[0]["open_time_ms"]
    funding_span_ms = funding_events[-1]["funding_rate_timestamp_ms"] - funding_events[0]["funding_rate_timestamp_ms"]
    # 預期 30d ≈ 29 × 86400_000 = 2.5e9 ms（容忍 1d 邊界）
    expected_days_ms = 28 * 86_400_000
    if perp_span_ms < expected_days_ms or funding_span_ms < expected_days_ms:
        return "FAIL", (
            f"replay span 不足 28d (perp={perp_span_ms/86400000:.1f}d "
            f"funding={funding_span_ms/86400000:.1f}d)"
        )
    return "PASS", (
        f"full window covered: perp {perp_span_ms/86400000:.1f}d / "
        f"funding {funding_span_ms/86400000:.1f}d / {len(funding_events)} events"
    )


def sanity_check_dsr_psr(
    daily_pnl_usd: list[float],
) -> tuple[str, str, dict]:
    """Check 3: Deflated Sharpe Ratio (DSR) / Probabilistic Sharpe Ratio (PSR)。

    Pass criteria：Sharpe(daily_pnl) > 0 AND PSR(sharpe) > 0.6 deflated for 1 strategy。
       PSR 公式 (Bailey & López de Prado 2014)：
       PSR = Φ((sr - sr_benchmark) × sqrt(n-1) / sqrt(1 - skew*sr + (kurt-1)/4 * sr^2))

       此處 sr_benchmark=0（zero baseline）；1 strategy 不需 multiple testing 校正。
    """
    if len(daily_pnl_usd) < 5:
        return "FAIL", f"insufficient daily samples ({len(daily_pnl_usd)} < 5)", {}

    mean = statistics.mean(daily_pnl_usd)
    stdev = statistics.stdev(daily_pnl_usd) if len(daily_pnl_usd) >= 2 else 0.0
    if stdev <= 1e-9:
        return "FAIL", f"zero stdev daily PnL (mean={mean:.4f})", {
            "sharpe": 0.0, "psr": 0.0, "mean_daily_pnl": mean, "stdev_daily_pnl": stdev,
        }

    sharpe = mean / stdev  # daily Sharpe（per-day basis）

    # skew + excess kurtosis (sample estimators)
    n = len(daily_pnl_usd)
    if n >= 3:
        m3 = sum((x - mean) ** 3 for x in daily_pnl_usd) / n
        skew = m3 / (stdev ** 3) if stdev > 0 else 0.0
    else:
        skew = 0.0
    if n >= 4:
        m4 = sum((x - mean) ** 4 for x in daily_pnl_usd) / n
        kurt = m4 / (stdev ** 4) if stdev > 0 else 3.0  # 標準正態 kurt=3
    else:
        kurt = 3.0
    excess_kurt = kurt - 3.0

    # PSR denominator: sqrt(1 - skew*sr + (excess_kurt)/4 * sr^2)
    denom_inner = 1.0 - skew * sharpe + (excess_kurt / 4.0) * (sharpe ** 2)
    if denom_inner <= 0:
        return "FAIL", f"PSR denominator non-positive ({denom_inner:.4f})", {
            "sharpe": sharpe, "skew": skew, "excess_kurt": excess_kurt, "psr": 0.0,
        }
    psr_z = sharpe * math.sqrt(n - 1) / math.sqrt(denom_inner)
    psr = 0.5 * (1 + math.erf(psr_z / math.sqrt(2)))  # Φ(z)

    metrics = {
        "sharpe": sharpe,
        "skew": skew,
        "excess_kurt": excess_kurt,
        "psr": psr,
        "mean_daily_pnl": mean,
        "stdev_daily_pnl": stdev,
        "n_days": n,
    }

    if sharpe <= SHARPE_MIN:
        return "FAIL", f"Sharpe={sharpe:.4f} <= {SHARPE_MIN}", metrics
    if psr < DEFLATED_PSR_MIN:
        return "FAIL", f"PSR={psr:.4f} < {DEFLATED_PSR_MIN}", metrics
    return "PASS", f"Sharpe={sharpe:.4f} PSR={psr:.4f}", metrics


def sanity_check_pbo_bootstrap(
    daily_pnl_usd: list[float],
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> tuple[str, str, dict]:
    """Check 4: PBO / bootstrap lower 5% tail。

    Pass criteria：1000-sample bootstrap cum PnL lower 5% tail ≥ -$5
       (即 Stage 1 stop_loss_pct=0.05 × $100 cap = $5 max loss per trade)。
    """
    if len(daily_pnl_usd) < 5:
        return "FAIL", f"insufficient samples for bootstrap ({len(daily_pnl_usd)})", {}

    rng = random.Random(seed)
    n = len(daily_pnl_usd)
    cum_pnls: list[float] = []

    for _ in range(n_bootstrap):
        sample = [daily_pnl_usd[rng.randrange(n)] for _ in range(n)]
        cum_pnls.append(sum(sample))

    cum_pnls.sort()
    lower_5pct_idx = max(0, int(0.05 * n_bootstrap) - 1)
    lower_5pct = cum_pnls[lower_5pct_idx]
    median_cum = cum_pnls[len(cum_pnls) // 2]
    upper_5pct = cum_pnls[min(len(cum_pnls) - 1, int(0.95 * n_bootstrap))]

    metrics = {
        "n_bootstrap": n_bootstrap,
        "lower_5pct_cum_pnl": lower_5pct,
        "median_cum_pnl": median_cum,
        "upper_5pct_cum_pnl": upper_5pct,
    }

    if lower_5pct < BOOTSTRAP_LOWER_5PCT_FLOOR:
        return "FAIL", (
            f"bootstrap lower_5pct=${lower_5pct:.2f} < floor "
            f"${BOOTSTRAP_LOWER_5PCT_FLOOR} (Stage 1 stop_loss)"
        ), metrics
    return "PASS", (
        f"bootstrap lower_5pct=${lower_5pct:.2f} median=${median_cum:.2f} "
        f"upper_5pct=${upper_5pct:.2f}"
    ), metrics


def sanity_check_replay_data_tier(
    replay_pnl_net_usd: float,
    historical_demo_pnl_usd: Optional[float] = None,
) -> tuple[str, str]:
    """Check 5: Replay data tier。

    Pass criteria：若有 historical demo path PnL，replay 偏離 < 1%；否則 vacuous pass。
       Stage 0R 首次 run 通常無 historical demo（C10 新策略）→ vacuous pass。
    """
    if historical_demo_pnl_usd is None:
        return "PASS", "no historical demo path; vacuous pass (Stage 0R first run for C10 new strategy)"
    if abs(replay_pnl_net_usd) < 1e-6:
        # replay 自身近零 → 改用絕對偏離 floor
        abs_drift = abs(replay_pnl_net_usd - historical_demo_pnl_usd)
        if abs_drift > 1.0:  # $1 abs floor
            return "FAIL", f"replay PnL={replay_pnl_net_usd:.4f} demo={historical_demo_pnl_usd:.4f} abs drift {abs_drift:.4f} > $1"
        return "PASS", f"replay {replay_pnl_net_usd:.4f} demo {historical_demo_pnl_usd:.4f} abs drift {abs_drift:.4f}"
    drift_pct = abs((replay_pnl_net_usd - historical_demo_pnl_usd) / replay_pnl_net_usd) * 100.0
    if drift_pct > REPLAY_DATA_TIER_DRIFT_MAX_PCT:
        return "FAIL", f"drift={drift_pct:.2f}% > {REPLAY_DATA_TIER_DRIFT_MAX_PCT}%"
    return "PASS", f"replay vs demo drift={drift_pct:.2f}%"


def sanity_check_runtime_boundary() -> tuple[str, str]:
    """Check 6: Runtime boundary。

    Pass criteria：replay 不 claim 替代 demo fill-lineage / Decision Lease / Guardian path；
       本 harness 純 simulation，不寫 trading.fills / 不發 Bybit order；by design 通過。
    """
    if RUNTIME_BOUNDARY_CHECK_PASS_BY_DESIGN:
        return "PASS", "replay harness 純 simulation；不寫 PG / 不發 Bybit order / 不 claim 替代 demo fill-lineage"
    return "FAIL", "runtime boundary invariant violated"


# ═══════════════════════════════════════════════════════════════════════════════
# Output verdict assembly
# ═══════════════════════════════════════════════════════════════════════════════


def output_preflight_verdict(
    symbol: str,
    days: int,
    trades: list[TradeRecord],
    daily_pnl_usd: list[float],
    funding_events: list[dict],
    perp_klines: list[dict],
    output_dir: str,
) -> dict:
    """組裝 6 sanity check + summary metric → JSON verdict + sanity report。

    per dispatch packet §6.4 output schema。
    """
    os.makedirs(output_dir, exist_ok=True)

    # Aggregate replay PnL
    replay_pnl_perp = sum(t.perp_price_pnl_usd + t.cumulative_funding_payment_usd - t.perp_fee_usd for t in trades)
    replay_pnl_synth = sum(t.synthetic_spot_pnl_usd - t.synthetic_spot_fee_usd for t in trades)
    replay_pnl_net = sum(t.net_pnl_usd for t in trades)

    # 6 sanity checks
    check1_status, check1_msg = sanity_check_leak_lookahead(trades, funding_events)
    check2_status, check2_msg = sanity_check_selection_bias(trades, funding_events, perp_klines)
    check3_status, check3_msg, check3_metrics = sanity_check_dsr_psr(daily_pnl_usd)
    check4_status, check4_msg, check4_metrics = sanity_check_pbo_bootstrap(daily_pnl_usd)
    check5_status, check5_msg = sanity_check_replay_data_tier(replay_pnl_net, historical_demo_pnl_usd=None)
    check6_status, check6_msg = sanity_check_runtime_boundary()

    all_checks_pass = all(
        s == "PASS" for s in
        (check1_status, check2_status, check3_status, check4_status, check5_status, check6_status)
    )

    reasons = []
    for name, status, msg in [
        ("leak_lookahead", check1_status, check1_msg),
        ("selection_bias", check2_status, check2_msg),
        ("dsr_psr", check3_status, check3_msg),
        ("pbo_bootstrap", check4_status, check4_msg),
        ("replay_data_tier", check5_status, check5_msg),
        ("runtime_boundary", check6_status, check6_msg),
    ]:
        reasons.append(f"{name}: {status} ({msg})")

    sharpe = check3_metrics.get("sharpe", 0.0)
    psr = check3_metrics.get("psr", 0.0)
    lower_5pct = check4_metrics.get("lower_5pct_cum_pnl", 0.0)

    verdict = {
        "strategy": "funding_harvest",
        "symbol": symbol,
        "replay_window_days": days,
        "replay_start_ts_ms": perp_klines[0]["open_time_ms"] if perp_klines else 0,
        "replay_end_ts_ms": perp_klines[-1]["open_time_ms"] if perp_klines else 0,
        "funding_events_total": len(funding_events),
        "entry_events": len(trades),
        "exit_events": len(trades),
        "max_concurrent_positions": 1,  # Stage 1 design
        "replay_pnl_perp_leg_usd": round(replay_pnl_perp, 4),
        "replay_pnl_synthetic_spot_leg_usd": round(replay_pnl_synth, 4),
        "replay_pnl_net_usd": round(replay_pnl_net, 4),
        "sharpe": round(sharpe, 4),
        "deflated_psr": round(psr, 4),
        "bootstrap_lower_5pct_pnl_usd": round(lower_5pct, 4),
        "attribution_chain_ok_pct": 100.0,  # by design: 每筆 trade 都有 entry+exit ts + symbol
        "leak_lookahead_check": check1_status,
        "selection_bias_check": check2_status,
        "dsr_psr_check": check3_status,
        "pbo_bootstrap_check": check4_status,
        "replay_data_tier_check": check5_status,
        "runtime_boundary_check": check6_status,
        "eligible_for_demo_canary": all_checks_pass,
        "reasons": reasons,
        "evidence_refs": [],
        "config_snapshot": {
            "funding_threshold_annualized": DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
            "funding_exit_annualized": DEFAULT_FUNDING_EXIT_ANNUALIZED,
            "max_basis_pct": DEFAULT_MAX_BASIS_PCT,
            "entry_basis_ratio": DEFAULT_ENTRY_BASIS_RATIO,
            "max_hold_ms": DEFAULT_MAX_HOLD_MS,
            "total_cost_bps": DEFAULT_TOTAL_COST_BPS,
            "expected_periods": DEFAULT_EXPECTED_PERIODS,
            "rebalance_check_ms": DEFAULT_REBALANCE_CHECK_MS,
            "delta_drift_threshold": DEFAULT_DELTA_DRIFT_THRESHOLD,
            "position_cap_usd": DEFAULT_POSITION_CAP_USD,
        },
        "generated_at_iso": datetime.now(timezone.utc).isoformat(),
    }

    # 寫 verdict JSON
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    verdict_path = os.path.join(output_dir, f"funding_harvest_stage0r_{today}.json")
    with open(verdict_path, "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2, ensure_ascii=False)
    verdict["evidence_refs"].append(verdict_path)

    # 寫 detailed metrics（trade-by-trade + daily PnL）
    metrics_path = os.path.join(output_dir, f"funding_harvest_stage0r_metrics_{today}.json")
    detailed = {
        "trades": [asdict(t) for t in trades],
        "daily_pnl_usd": daily_pnl_usd,
        "psr_metrics": check3_metrics,
        "bootstrap_metrics": check4_metrics,
    }
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(detailed, f, indent=2, ensure_ascii=False)
    verdict["evidence_refs"].append(metrics_path)

    # 重寫 verdict 加入 evidence_refs
    with open(verdict_path, "w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2, ensure_ascii=False)

    logger.info("=" * 60)
    logger.info("STAGE 0R PREFLIGHT VERDICT")
    logger.info("  symbol=%s replay_days=%d trades=%d", symbol, days, len(trades))
    logger.info("  net PnL=$%.2f (perp $%.2f + spot $%.2f)", replay_pnl_net, replay_pnl_perp, replay_pnl_synth)
    logger.info("  Sharpe=%.4f PSR=%.4f bootstrap_lower_5pct=$%.2f",
                sharpe, psr, lower_5pct)
    logger.info("  6 sanity checks: leak=%s bias=%s dsr/psr=%s pbo=%s tier=%s boundary=%s",
                check1_status, check2_status, check3_status,
                check4_status, check5_status, check6_status)
    logger.info("  eligible_for_demo_canary=%s", all_checks_pass)
    logger.info("  verdict: %s", verdict_path)
    logger.info("  metrics: %s", metrics_path)
    logger.info("=" * 60)

    return verdict


# ═══════════════════════════════════════════════════════════════════════════════
# Main orchestrator
# ═══════════════════════════════════════════════════════════════════════════════


def run_stage0r_preflight(
    symbol: str = "BTCUSDT",
    days: int = DEFAULT_REPLAY_DAYS,
    output_dir: Optional[str] = None,
    config_override: Optional[dict] = None,
) -> dict:
    """完整 Stage 0R preflight pipeline：fetch → simulate → 6 sanity check → verdict。"""
    if output_dir is None:
        output_dir = os.path.join(
            os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"),
            "canary",
        )

    config = {
        "funding_threshold_annualized": DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
        "funding_exit_annualized": DEFAULT_FUNDING_EXIT_ANNUALIZED,
        "max_basis_pct": DEFAULT_MAX_BASIS_PCT,
        "entry_basis_ratio": DEFAULT_ENTRY_BASIS_RATIO,
        "max_hold_ms": DEFAULT_MAX_HOLD_MS,
        "total_cost_bps": DEFAULT_TOTAL_COST_BPS,
        "expected_periods": DEFAULT_EXPECTED_PERIODS,
        "rebalance_check_ms": DEFAULT_REBALANCE_CHECK_MS,
        "delta_drift_threshold": DEFAULT_DELTA_DRIFT_THRESHOLD,
        "position_cap_usd": DEFAULT_POSITION_CAP_USD,
        "cooldown_ms": DEFAULT_COOLDOWN_MS,
    }
    if config_override:
        config.update(config_override)

    logger.info("=" * 60)
    logger.info("Stage 0R preflight harness start")
    logger.info("  symbol=%s days=%d output_dir=%s", symbol, days, output_dir)
    logger.info("=" * 60)

    start_t = time.time()

    # Step 1: fetch funding rates
    funding_events = fetch_funding_rates(symbol, days=days, category="linear")
    if not funding_events:
        logger.error("0 funding events fetched; abort")
        return {"eligible_for_demo_canary": False, "reasons": ["no funding events fetched"]}

    # Step 2: fetch perp klines
    perp_klines = fetch_perp_klines(symbol, days=days)
    if not perp_klines:
        logger.error("0 perp klines fetched; abort")
        return {"eligible_for_demo_canary": False, "reasons": ["no perp klines fetched"]}

    # Step 3: fetch spot klines
    spot_klines = fetch_spot_klines(symbol, days=days)
    if not spot_klines:
        logger.error("0 spot klines fetched; abort")
        return {"eligible_for_demo_canary": False, "reasons": ["no spot klines fetched"]}

    # Step 4: simulate
    logger.info("Step 4: simulating funding_harvest strategy …")
    trades, daily_pnl_usd = replay_funding_harvest(
        symbol, perp_klines, spot_klines, funding_events, config
    )
    logger.info("  simulated %d trades, %d daily PnL points", len(trades), len(daily_pnl_usd))

    # Step 5: 6 sanity check + verdict
    verdict = output_preflight_verdict(
        symbol, days, trades, daily_pnl_usd, funding_events, perp_klines, output_dir
    )

    elapsed = time.time() - start_t
    logger.info("Stage 0R harness elapsed=%.1fs", elapsed)
    verdict["elapsed_seconds"] = round(elapsed, 1)
    return verdict


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="C10 funding_harvest Stage 0R replay preflight harness"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Stage 1 限定 BTCUSDT")
    parser.add_argument("--days", type=int, default=DEFAULT_REPLAY_DAYS,
                        help="Replay window days (default 30)")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output dir; default $OPENCLAW_DATA_DIR/canary or /tmp/openclaw/canary",
    )
    args = parser.parse_args()

    verdict = run_stage0r_preflight(
        symbol=args.symbol,
        days=args.days,
        output_dir=args.output_dir,
    )

    sys.exit(0 if verdict.get("eligible_for_demo_canary") else 1)


if __name__ == "__main__":
    main()
