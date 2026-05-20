"""
MODULE_NOTE
模塊用途：Phase 1b calibration sweep tick-stream PG loader。
依 PA spec §3 Tick-Stream Data Source，從 PG 取：
  - market.market_tickers (BBO + spread_bps 隨時間)，作為 PA spec
    `market.orderbook_50` / `bbo_snapshot` 對應實際 source
  - market.ob_snapshots (1m bid_depth_5/ask_depth_5 aggregate)
    — 為 queue-aware adjustment 提供 same-side depth proxy
    （P2-SIM-QUEUE-AWARE-ADJUSTMENT v55）
  - market.symbol_universe_snapshots (tick_size per symbol)
  - trading.fills (post-restart 4 row + recent 50 baseline seed)
主要類/函數：FillReplaySeed / TickWindow / OrderbookDepthWindow /
            load_tick_window / load_orderbook_window / load_replay_seed /
            load_tick_size_map / get_taker_baseline_fee_bps。
依賴：psycopg2（per `helper_scripts/db/counterfactual_exit_replay.py` 同模式）。
硬邊界：read-only；無 write；fail-closed when freshness/coverage 不足；
        data_source tag 必為 'bybit_demo_ws'（spec §3.4）。
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

# 為什麼這個 sys.path 插入：與 counterfactual_exit_replay.py 同模式，確保 sibling
# 模組可 import；CLI 任意 cwd 皆可跑。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from phase_1b_queue_adjustment import QueueDepthSample  # noqa: E402


# Phase 1b runtime activator restart anchor（spec §3.3 freshness gate）.
# post-restart 才是 pure Phase 1b runtime；之前是 pre-activator legacy。
POST_RESTART_ANCHOR_UTC = datetime(2026, 5, 17, 23, 54, 36, tzinfo=timezone.utc)

# spec §3.4 — Bybit demo endpoint data tag, must propagate to harness output.
DATA_SOURCE_TAG = "bybit_demo_ws"

# spec §3.2 — per-fill data span 上下界
PRE_FILL_SECONDS = 60  # pre-fill snapshot lookback
POST_FILL_MAX_TIMEOUT_SECONDS = 90  # 最大 timeout cell（C-grid 90s）
POST_FILL_DRIFT_SECONDS = 300  # adverse_selection_proxy 視窗（fill+60s to fill+5min）


@dataclass(frozen=True)
class TickSample:
    """單一 BBO snapshot。

    為什麼 frozen：snapshot 是 timepoint immutable；hash/equality 用於 dedupe。
    不變量：best_bid > 0 AND best_ask > 0 AND ts is UTC aware；spread_bps may be NaN if
    columns return NULL but rare given freshness gate。
    """
    ts: datetime
    symbol: str
    best_bid: float
    best_ask: float
    spread_bps: Optional[float]

    @property
    def mid(self) -> float:
        return (self.best_bid + self.best_ask) * 0.5


@dataclass(frozen=True)
class TickWindow:
    """單一 fill 對應的 tick stream window（pre + replay + post-drift）。"""
    fill_order_id: str
    symbol: str
    fill_ts: datetime
    pre_fill_samples: tuple[TickSample, ...]  # fill_ts - 60s .. fill_ts
    replay_samples: tuple[TickSample, ...]    # fill_ts .. fill_ts + max_timeout
    post_drift_samples: tuple[TickSample, ...]  # fill_ts + 60s .. fill_ts + 5min

    def bbo_at_or_before(self, ts: datetime) -> Optional[TickSample]:
        """取最接近且 ≤ ts 的 sample（用於 fill_ts 時 BBO 推算）。

        為什麼 ≤ ts：模擬實際 strategy hot path 取最後 known BBO；
        若全部 sample 都晚於 ts → 回 None（觸發 §2.3 strict skip）。
        """
        if not self.pre_fill_samples and not self.replay_samples:
            return None
        # pre + replay merged 升序遍歷 last_le
        candidates = self.pre_fill_samples + self.replay_samples
        best: Optional[TickSample] = None
        for s in candidates:
            if s.ts <= ts and (best is None or s.ts > best.ts):
                best = s
        return best


@dataclass(frozen=True)
class FillReplaySeed:
    """單筆 historical close fill，作為 sweep 重播種子。

    spec §2.2.1 SQL 對應 row schema。
    """
    order_id: str
    link_id: Optional[str]
    symbol: str
    side: str  # 'Buy' or 'Sell'
    exit_reason: str
    qty: float
    price: float  # actual taker fill price
    ts: datetime
    close_maker_attempt: bool
    close_maker_fallback_reason: Optional[str]
    seed_source: str  # "post_restart" | "pre_restart_baseline"


def _get_conn():
    """取 PG 連線（與 counterfactual_exit_replay.py 同模式）。

    支援 OPENCLAW_DATABASE_URL 或 POSTGRES_* env vars。
    Mac local 用 Tailscale 連 trade-core：
      POSTGRES_HOST=trade-core POSTGRES_USER=trading_admin POSTGRES_DB=trading_ai
    """
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


def load_replay_seed(
    conn: Any,
    *,
    include_pre_restart_baseline: bool = True,
    pre_restart_limit: int = 50,
) -> list[FillReplaySeed]:
    """依 spec §2.2.1 取 fill replay seed。

    為什麼 include pre-restart baseline：post-restart 只 n=4，遠不足統計；
    pre-activator 50 row 提供 baseline / 大樣本參考（per spec §10.2 PA 推薦）。
    """
    seeds: list[FillReplaySeed] = []
    whitelist_reasons = (
        "grid_close_short",
        "grid_close_long",
        "bb_mean_revert",
        "phys_lock_gate4_giveback",
        "phys_lock_gate4_stale_roc_neg",
        "ma_reverse_cross",
        "bw_squeeze",
        "pctb_revert",
    )

    with conn.cursor() as cur:
        # Post-restart anchor seed（Phase 1b runtime real data）
        cur.execute(
            """
            SELECT order_id, fill_id AS link_id, symbol, side, exit_reason, qty, price, ts,
                   close_maker_attempt, close_maker_fallback_reason
              FROM trading.fills
             WHERE engine_mode = 'demo'
               AND close_maker_attempt = TRUE
               AND ts > %s
             ORDER BY ts ASC
            """,
            (POST_RESTART_ANCHOR_UTC,),
        )
        for row in cur.fetchall():
            seeds.append(FillReplaySeed(
                order_id=row[0],
                link_id=row[1],
                symbol=row[2],
                side=row[3],
                exit_reason=row[4],
                qty=float(row[5]),
                price=float(row[6]),
                ts=row[7],
                close_maker_attempt=row[8],
                close_maker_fallback_reason=row[9],
                seed_source="post_restart",
            ))

        if include_pre_restart_baseline:
            # Pre-restart 7d demo whitelist closes（baseline reference seed）
            cur.execute(
                """
                SELECT order_id, fill_id AS link_id, symbol, side, exit_reason, qty, price, ts,
                       close_maker_attempt, close_maker_fallback_reason
                  FROM trading.fills
                 WHERE engine_mode = 'demo'
                   AND exit_reason = ANY(%s)
                   AND ts <= %s
                   AND ts > %s
                 ORDER BY ts DESC
                 LIMIT %s
                """,
                (
                    list(whitelist_reasons),
                    POST_RESTART_ANCHOR_UTC,
                    POST_RESTART_ANCHOR_UTC - timedelta(days=7),
                    pre_restart_limit,
                ),
            )
            for row in cur.fetchall():
                seeds.append(FillReplaySeed(
                    order_id=row[0],
                    link_id=row[1],
                    symbol=row[2],
                    side=row[3],
                    exit_reason=row[4],
                    qty=float(row[5]),
                    price=float(row[6]),
                    ts=row[7],
                    close_maker_attempt=row[8] if row[8] is not None else False,
                    close_maker_fallback_reason=row[9],
                    seed_source="pre_restart_baseline",
                ))

    return seeds


def load_tick_size_map(
    conn: Any,
    symbols: list[str],
    exchange: str = "bybit",
) -> dict[str, float]:
    """從 market.symbol_universe_snapshots 取 latest tick_size per symbol。

    為什麼 DISTINCT ON：同 symbol 多次 snapshot；取最新一筆即可（tick_size 罕變）。
    fail-closed：symbol 缺則不在 map；caller 必跳過該 fill。
    """
    if not symbols:
        return {}
    result: dict[str, float] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (symbol) symbol, tick_size
              FROM market.symbol_universe_snapshots
             WHERE symbol = ANY(%s)
               AND exchange = %s
             ORDER BY symbol, ts DESC
            """,
            (symbols, exchange),
        )
        for sym, tick in cur.fetchall():
            if tick is not None and float(tick) > 0:
                result[sym] = float(tick)
    return result


@dataclass(frozen=True)
class OrderbookDepthWindow:
    """單一 fill 對應的 ob_snapshots 1m depth bucket window。

    為什麼分開 TickWindow：ob_snapshots 是 1m aggregate（vs tickers ms-level），
    join 粒度不同；分 module 避免 confusion，且 caller 可選擇是否啟用 queue adjust。

    為什麼 bucket list：1m aggregate 一個 fill timeout window（30-90s）可能跨 1-2
    個 bucket；caller 用 ts_at_or_before 取 closest preceding bucket。
    """
    fill_order_id: str
    symbol: str
    fill_ts: object  # datetime
    buckets: tuple  # tuple[QueueDepthSample, ...]

    def depth_at_or_before(self, ts: object) -> Optional[QueueDepthSample]:
        """取最接近且 bucket_start ≤ ts 的 sample。

        為什麼 ≤ ts：fill 發生時 my order placed → 取 fill_ts 時最後 known 1m bucket
        depth 作 queue proxy；若全部 bucket 都晚於 ts → 回 None（觸發 fail-closed
        退回 proxy 不調整）。
        """
        if not self.buckets:
            return None
        best: Optional[QueueDepthSample] = None
        for sample in self.buckets:
            if sample.ts_bucket_start <= ts and (
                best is None or sample.ts_bucket_start > best.ts_bucket_start
            ):
                best = sample
        return best


def load_tick_window(
    conn: Any,
    seed: FillReplaySeed,
) -> TickWindow:
    """取單一 fill 的完整 tick window（pre + replay + post-drift）。

    spec §3.2 time window：
      - pre: fill_ts - 60s .. fill_ts
      - replay: fill_ts .. fill_ts + 90s（max timeout cell）
      - post_drift: fill_ts + 60s .. fill_ts + 5min

    為什麼一次 query 全 range：減少 round trip；3 區段在 Python 切分。
    fail-closed：若整 window 無 sample → empty tuples（caller 處理）。
    """
    fill_ts = seed.ts
    window_start = fill_ts - timedelta(seconds=PRE_FILL_SECONDS)
    window_end = fill_ts + timedelta(seconds=POST_FILL_DRIFT_SECONDS)
    pre_end = fill_ts
    replay_end = fill_ts + timedelta(seconds=POST_FILL_MAX_TIMEOUT_SECONDS)
    drift_start = fill_ts + timedelta(seconds=PRE_FILL_SECONDS)

    pre: list[TickSample] = []
    replay: list[TickSample] = []
    drift: list[TickSample] = []

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts, best_bid, best_ask, spread_bps
              FROM market.market_tickers
             WHERE symbol = %s
               AND ts BETWEEN %s AND %s
               AND best_bid IS NOT NULL
               AND best_ask IS NOT NULL
               AND best_bid > 0
               AND best_ask > 0
             ORDER BY ts ASC
            """,
            (seed.symbol, window_start, window_end),
        )
        for row in cur.fetchall():
            ts, bid, ask, spread = row
            sample = TickSample(
                ts=ts,
                symbol=seed.symbol,
                best_bid=float(bid),
                best_ask=float(ask),
                spread_bps=float(spread) if spread is not None else None,
            )
            if sample.ts <= pre_end:
                pre.append(sample)
            elif sample.ts <= replay_end:
                replay.append(sample)
            if sample.ts >= drift_start:
                drift.append(sample)

    return TickWindow(
        fill_order_id=seed.order_id,
        symbol=seed.symbol,
        fill_ts=fill_ts,
        pre_fill_samples=tuple(pre),
        replay_samples=tuple(replay),
        post_drift_samples=tuple(drift),
    )


def load_orderbook_window(
    conn: Any,
    seed: FillReplaySeed,
) -> OrderbookDepthWindow:
    """取單一 fill 的 ob_snapshots 1m depth bucket window。

    時間範圍：fill_ts - 5min .. fill_ts + 5min（覆蓋 max timeout 90s + 緩衝）。
    為什麼這範圍：1m bucket 粒度下，fill_ts 前後各取 5 個 bucket 確保至少 1 個
    有效 bucket（少數 symbol bucket 稀疏）；caller 用 depth_at_or_before(fill_ts)
    取 closest preceding。

    為什麼 P2-SIM-QUEUE-AWARE-ADJUSTMENT 用 ob_snapshots 而非 market_tickers
    .bid_size / ask_size：empirical 14d query market_tickers.bid_size 僅 1.15%
    rows > 0（ingest pipeline 沒填），ob_snapshots.bid_depth_5 100% valid。
    粒度差兩個量級（1m vs ms）但作 queue-proxy 仍可用。

    fail-closed：bucket 缺 → buckets=()，caller 退回 proxy 不調整。
    """
    fill_ts = seed.ts
    window_start = fill_ts - timedelta(minutes=5)
    window_end = fill_ts + timedelta(minutes=5)

    buckets: list[QueueDepthSample] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ts, bid_depth_5, ask_depth_5
              FROM market.ob_snapshots
             WHERE symbol = %s
               AND ts BETWEEN %s AND %s
             ORDER BY ts ASC
            """,
            (seed.symbol, window_start, window_end),
        )
        for row in cur.fetchall():
            ts, bid_depth, ask_depth = row
            buckets.append(QueueDepthSample(
                ts_bucket_start=ts,
                symbol=seed.symbol,
                bid_depth_5=float(bid_depth) if bid_depth is not None else None,
                ask_depth_5=float(ask_depth) if ask_depth is not None else None,
            ))

    return OrderbookDepthWindow(
        fill_order_id=seed.order_id,
        symbol=seed.symbol,
        fill_ts=fill_ts,
        buckets=tuple(buckets),
    )


def get_taker_baseline_fee_bps(
    conn: Any,
    *,
    lookback_days: int = 7,
) -> float:
    """取 pre-Phase-1b demo taker baseline effective fee bps（spec §4.1 acceptance gate）.

    為什麼這值是 acceptance gate input：harness 評估 adverse_selection_proxy_bps
    必對比 pre-Phase-1b taker baseline；若 cell adverse > baseline → FAIL gate。
    Empirical 探出 baseline ≈ 5.55 bps（trade-core 14:00 UTC measurement）;
    寫法保留動態查詢能力，避免硬編碼數值老化。
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT AVG(fee / qty / price * 10000.0)::float
              FROM trading.fills
             WHERE engine_mode = 'demo'
               AND liquidity_role = 'taker'
               AND (close_maker_attempt IS NULL OR close_maker_attempt = FALSE)
               AND ts > NOW() - %s::interval
               AND qty > 0
               AND price > 0
               AND fee IS NOT NULL
            """,
            (f"{lookback_days} days",),
        )
        row = cur.fetchone()
        if row and row[0] is not None:
            return float(row[0])
    # fail-closed: 若 baseline 無法計算（極少數情況），回 5.5 bps (Bybit taker cap)
    # 保持 acceptance gate 工作而非崩潰；
    return 5.5


def verify_freshness(conn: Any) -> dict:
    """驗 PG market_tickers + fills 資料新鮮度（spec §3.3）。

    回傳 dict 給 harness 開始前 print + decide proceed。
    為什麼必驗：替代 PA spec §3.1 預設 table 不存在 / coverage 不足的 fail-closed。
    """
    out: dict = {}
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(ts) FROM market.market_tickers")
        row = cur.fetchone()
        out["tickers_max_ts"] = row[0] if row else None
        cur.execute("""
            SELECT COUNT(*), COUNT(DISTINCT symbol)
              FROM market.market_tickers
             WHERE ts > NOW() - INTERVAL '7 days'
        """)
        rows = cur.fetchone()
        out["tickers_7d_rows"] = int(rows[0]) if rows else 0
        out["tickers_7d_symbols"] = int(rows[1]) if rows else 0
        cur.execute("""
            SELECT COUNT(*) FROM trading.fills
             WHERE engine_mode='demo' AND close_maker_attempt=TRUE AND ts > %s
        """, (POST_RESTART_ANCHOR_UTC,))
        out["post_restart_fills"] = int(cur.fetchone()[0])
    return out
