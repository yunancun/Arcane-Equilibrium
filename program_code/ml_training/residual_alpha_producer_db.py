"""
MODULE_NOTE
模塊用途：Residual alpha producer 的 DB adapter（R-2）。把真實 demo 資料
（FIFO round-trip 候選報酬 + market.klines 1m factor + PIT universe）組裝成
R-1 ``build_residual_alpha_report`` 的輸入並評估。
主要函數：
  - 純核心（無 DB，Mac 可全測）：``contained_bar_return_bps``、
    ``pit_active_symbols``、``assemble_residual_inputs``、
    ``build_residual_report_from_data``、``to_epoch_seconds``。
  - DB 層（Linux runtime 驗證）：``load_round_trips``、``load_klines``、
    ``load_symbol_lifecycles``、``build_cycle_residual_reports``（見檔尾）。
依賴：residual_alpha_producer（R-1）+ realized_edge_stats（FIFO 配對）+
  psycopg2（DB 層）；純核心只用標準庫。
硬邊界（QC/MIT 2026-06-05 對抗審定稿）：
  - 候選 = FIFO round-trip ``net_pnl_bps``（真實 [entry,exit] 窗、扣費、帶方向），
    **不得**用 decision_outcomes.outcome_*（固定時程毛價格）或未濾 reject 的
    label_net_edge_bps（99.9% 為 rejected_governance=0 佔位）。
  - factor = BTC 與 PIT-equal-weight market 在候選**同一 [entry,exit] 窗**的
    報酬，僅用**完全落在窗內**的 1m bar（open≥entry 且 close≤exit）；straddling /
    partial bar 一律排除（resample-boundary 防滲漏）。
  - PIT universe 用 listed_at/delisted_at lifecycle 權威（含已下市），**禁用**
    「取最新 snapshot、忽略 delisted」的 survivorship 捷徑。
  - 全程 UTC epoch 秒；只讀 DB；不碰 runtime / order / risk / auth。
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Hashable, Mapping, Sequence

try:  # 套件式 import（app runtime）
    from program_code.learning_engine.residual_alpha_producer import (
        ResidualAlphaProducerResult,
        build_residual_alpha_report,
    )
except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
    from learning_engine.residual_alpha_producer import (  # type: ignore
        ResidualAlphaProducerResult,
        build_residual_alpha_report,
    )


BTC_SYMBOL = "BTCUSDT"
KLINES_1M_INTERVAL_SEC: float = 60.0
DEFAULT_MIN_BASKET_SYMBOLS = 8


# ---------------------------------------------------------------------------
# 純核心（無 DB）—— leak surface 全在此，Mac 可全測
# ---------------------------------------------------------------------------


def to_epoch_seconds(value: Any) -> float | None:
    """把 datetime / 數值轉成 UTC epoch 秒（float）。

    naive datetime 一律當 UTC（MIT UTC 紀律：禁 naive↔aware 混比）。非法值回
    None。R-2 全程用 epoch 秒，確保 R-1 的 embargo（ts − gap）與 contained-bar
    算術皆為數值運算。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        out = float(value)
        return out if math.isfinite(out) else None
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return None


def contained_bar_return_bps(
    bars: Sequence[Mapping[str, Any]],
    entry_ts: float,
    exit_ts: float,
    interval_sec: float = KLINES_1M_INTERVAL_SEC,
) -> float | None:
    """用**僅完全落在 [entry_ts, exit_ts] 內**的 bar 算 open→close 報酬（bps）。

    bars: ``[{"ts": epoch_sec, "open": float, "close": float}, ...]``；``ts`` 是
    bar 的 OPEN time（UTC epoch 秒）。bar 完全包含的判定：
    ``bar.ts >= entry_ts`` 且 ``bar.ts + interval_sec <= exit_ts``。
    straddling（跨 entry 或 exit）/ partial bar 一律排除。無包含 bar 或價格非法
    回 None（caller 應丟棄該觀測，不得回退到跨界 bar）。
    """
    inside: list[tuple[float, Mapping[str, Any]]] = []
    for bar in bars:
        bts = _finite(bar.get("ts"))
        if bts is None:
            continue
        if bts >= entry_ts and bts + interval_sec <= exit_ts:
            inside.append((bts, bar))
    if not inside:
        return None
    inside.sort(key=lambda item: item[0])
    first_open = _finite(inside[0][1].get("open"))
    last_close = _finite(inside[-1][1].get("close"))
    if first_open is None or last_close is None or first_open <= 0.0:
        return None
    return (last_close / first_open - 1.0) * 10_000.0


def pit_active_symbols(
    lifecycles: Mapping[str, tuple[float | None, float | None]],
    entry_ts: float,
    exit_ts: float,
) -> list[str]:
    """回傳在 [entry_ts, exit_ts] 全程可交易的 PIT active universe（含已下市）。

    成員條件：``listed_at <= entry_ts`` 且
    ``(delisted_at is None or delisted_at > exit_ts)``。
    lifecycles: ``{symbol: (listed_at_epoch | None, delisted_at_epoch | None)}``。
    用 lifecycle 權威（含已下市，避免 survivorship）；caller 不得只餵今日 universe。
    """
    out: list[str] = []
    for symbol, life in lifecycles.items():
        listed, delisted = life
        if listed is None or listed > entry_ts:
            continue
        if delisted is not None and delisted <= exit_ts:
            continue
        out.append(symbol)
    return out


def assemble_residual_inputs(
    round_trips: Sequence[Mapping[str, Any]],
    klines_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    lifecycles: Mapping[str, tuple[float | None, float | None]],
    *,
    required_factors: tuple[str, ...] = ("btc", "market"),
    interval_sec: float = KLINES_1M_INTERVAL_SEC,
    btc_symbol: str = BTC_SYMBOL,
    min_basket_symbols: int = DEFAULT_MIN_BASKET_SYMBOLS,
) -> tuple[dict[float, float], dict[float, dict[str, float]], dict[str, int]]:
    """把 round-trips + 1m klines + PIT lifecycles 組裝成 R-1 的 candidate/factor。

    round_trips: ``[{"entry_ts": epoch, "exit_ts": epoch, "net_bps": float}, ...]``
      （ts 已轉 epoch 秒；net_bps 為扣費後、帶方向的 round-trip 淨報酬）。
    required_factors: 要計算的 factor（"btc" 與/或 "market"）。v1 預設可只傳
      ``("btc",)``：單因子 BTC 殘差化，免載入全 universe basket（可擴展），且
      直擊「BTC down-beta 偽裝 edge」主因；"market" 需 PIT 等權 basket（v2）。
    回 ``(candidate_returns, factor_returns, diag)``：candidate=``{entry_ts: net_bps}``，
    factor=``{entry_ts: {factor: bps}}``。每個觀測的 factor 都在該觀測**自己的
    [entry,exit] 窗**上計算，與候選同窗同時程（同單位 bps），故 beta 是真實已實現
    曝險、leak-free。
    """
    candidate: dict[float, float] = {}
    factor: dict[float, dict[str, float]] = {}
    diag = {
        "input": len(round_trips),
        "bad_window": 0,
        "dup_entry_ts": 0,
        "no_btc_bar": 0,
        "thin_basket": 0,
        "aligned": 0,
    }
    btc_bars = klines_by_symbol.get(btc_symbol, ())
    for rt in sorted(round_trips, key=lambda r: _sort_key(r.get("entry_ts"))):
        entry = _finite(rt.get("entry_ts"))
        exit_ = _finite(rt.get("exit_ts"))
        net = _finite(rt.get("net_bps"))
        if entry is None or exit_ is None or net is None or exit_ <= entry:
            diag["bad_window"] += 1
            continue
        if entry in candidate:
            diag["dup_entry_ts"] += 1
            continue
        factor_vals: dict[str, float] = {}
        dropped = False
        for fac in required_factors:
            if fac == "btc":
                btc_ret = contained_bar_return_bps(btc_bars, entry, exit_, interval_sec)
                if btc_ret is None:
                    diag["no_btc_bar"] += 1
                    dropped = True
                    break
                factor_vals["btc"] = btc_ret
            elif fac == "market":
                members: list[float] = []
                for symbol in pit_active_symbols(lifecycles, entry, exit_):
                    ret = contained_bar_return_bps(
                        klines_by_symbol.get(symbol, ()), entry, exit_, interval_sec
                    )
                    if ret is not None:
                        members.append(ret)
                if len(members) < min_basket_symbols:
                    diag["thin_basket"] += 1
                    dropped = True
                    break
                factor_vals["market"] = sum(members) / len(members)
            else:
                raise ValueError(f"unsupported factor: {fac!r}")
        if dropped:
            continue
        candidate[entry] = net
        factor[entry] = factor_vals
    diag["aligned"] = len(candidate)
    return candidate, factor, diag


def build_residual_report_from_data(
    round_trips: Sequence[Mapping[str, Any]],
    klines_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    lifecycles: Mapping[str, tuple[float | None, float | None]],
    *,
    n_trials: int,
    embargo_gap: float,
    peer_oos_returns: Sequence[Any] | None = None,
    required_factors: tuple[str, ...] = ("btc", "market"),
    interval_sec: float = KLINES_1M_INTERVAL_SEC,
    btc_symbol: str = BTC_SYMBOL,
    min_basket_symbols: int = DEFAULT_MIN_BASKET_SYMBOLS,
    **gate_kwargs: Any,
) -> tuple[ResidualAlphaProducerResult, dict[str, int]]:
    """組裝真實資料並呼叫 R-1，回 ``(result, diag)``。

    required_factors: v1 可傳 ``("btc",)`` 單因子（免 basket，可擴展）。
    embargo_gap 建議 ≥ 候選持倉窗的保守上界（如多日 perp 的最大持倉秒數），
    避免接縫窗重疊滲漏。n_trials 必須是本輪真實達標 cell 數×時程（非 1、非 row 數）。
    """
    candidate, factor, diag = assemble_residual_inputs(
        round_trips,
        klines_by_symbol,
        lifecycles,
        required_factors=required_factors,
        interval_sec=interval_sec,
        btc_symbol=btc_symbol,
        min_basket_symbols=min_basket_symbols,
    )
    result = build_residual_alpha_report(
        candidate,
        factor,
        n_trials=n_trials,
        peer_oos_returns=peer_oos_returns,
        required_factors=required_factors,
        embargo_gap=embargo_gap,
        **gate_kwargs,
    )
    return result, diag


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _sort_key(value: Any) -> float:
    out = _finite(value)
    return out if out is not None else math.inf


# ---------------------------------------------------------------------------
# 非重疊 bucket 路徑（QC/MIT 2026-06-05 對抗審定稿）= v1 主路徑
# ---------------------------------------------------------------------------
# 為什麼改 bucket：per-round-trip 報酬會重疊（grid 並行持多腿）→ 序列自相關 →
# PSR/DSR 的 sqrt(N) 高估獨立性 → beta 偽裝能過閘（=本模組要防的失敗模式從後門
# 重現）。改成非重疊 bucket：①報酬按 **exit_ts** 歸屬（一筆 trip 只進它的 exit
# 桶，已實現於 exit→無前視，duration leak 結構性消失）②factor=同桶 BTC 報酬
# ③embargo 變乾淨的 bucket gap。i.i.d. 違反大幅緩解；R-1 的 entry-keyed embargo
# 在非重疊桶 ts 上即正確，R-1 無需改。

DEFAULT_BUCKET_SEC: float = 4 * 3600.0  # 4h；demo ~49 天 → ~294 桶，n_eval 充足


def bucket_floor(ts: float, bucket_sec: float = DEFAULT_BUCKET_SEC) -> float:
    """把 epoch 秒 floor 到 bucket 網格起點（UTC-aligned：epoch 0 即 4h 邊界）。"""
    return math.floor(ts / bucket_sec) * bucket_sec


def bucket_round_trips_by_exit(
    round_trips: Sequence[Mapping[str, Any]],
    bucket_sec: float = DEFAULT_BUCKET_SEC,
) -> tuple[dict[float, float], dict[float, int]]:
    """依 **exit_ts** 把 round-trips 歸入非重疊 bucket。

    bucket 報酬 = 桶內各 trip net_bps 之和（已實現於 exit → 無前視）。回
    ``({bucket_ts: sum_net_bps}, {bucket_ts: count})``。exit 缺失/非法、或
    exit<=entry 者跳過。
    """
    sums: dict[float, float] = {}
    counts: dict[float, int] = {}
    for rt in round_trips:
        exit_ = _finite(rt.get("exit_ts"))
        net = _finite(rt.get("net_bps"))
        if exit_ is None or net is None:
            continue
        entry = _finite(rt.get("entry_ts"))
        if entry is not None and exit_ <= entry:
            continue
        bucket = bucket_floor(exit_, bucket_sec)
        sums[bucket] = sums.get(bucket, 0.0) + net
        counts[bucket] = counts.get(bucket, 0) + 1
    return sums, counts


def bucketed_btc_factor(
    btc_klines: Sequence[Mapping[str, Any]],
    bucket_sec: float = DEFAULT_BUCKET_SEC,
) -> dict[float, dict[str, float]]:
    """從 BTC bucket klines（對應 timeframe，如 4h）建 bucket factor。

    bucket_ts 用 ``bucket_floor(kline.ts)`` 對齊到與 trips 同網格（穩健於邊界偏移）。
    回 ``{bucket_ts: {"btc": bps}}``；一桶多根時取最早 open、最晚 close。
    """
    by_bucket: dict[float, list[tuple[float, Mapping[str, Any]]]] = {}
    for bar in btc_klines:
        ts = _finite(bar.get("ts"))
        if ts is None:
            continue
        by_bucket.setdefault(bucket_floor(ts, bucket_sec), []).append((ts, bar))
    factor: dict[float, dict[str, float]] = {}
    for bucket_ts, bars in by_bucket.items():
        bars.sort(key=lambda item: item[0])
        first_open = _finite(bars[0][1].get("open"))
        last_close = _finite(bars[-1][1].get("close"))
        if first_open is None or last_close is None or first_open <= 0.0:
            continue
        factor[bucket_ts] = {"btc": (last_close / first_open - 1.0) * 10_000.0}
    return factor


def build_bucketed_residual_report(
    round_trips: Sequence[Mapping[str, Any]],
    btc_klines: Sequence[Mapping[str, Any]],
    *,
    n_trials: int,
    bucket_sec: float = DEFAULT_BUCKET_SEC,
    embargo_buckets: int = 1,
    peer_oos_returns: Sequence[Any] | None = None,
    min_train_observations: int = 20,
    min_eval_observations: int = 8,
    **gate_kwargs: Any,
) -> tuple[ResidualAlphaProducerResult, dict[str, float]]:
    """非重疊 bucket BTC-only residual report（v1 主路徑）。

    embargo_buckets：train↔eval 接縫 purge 的 bucket 數（防相鄰桶自相關）。
    回 ``(result, diag)``；diag 含 bucket 數與 per-bucket trip 計數摘要。
    """
    candidate, counts = bucket_round_trips_by_exit(round_trips, bucket_sec)
    factor = bucketed_btc_factor(btc_klines, bucket_sec)
    aligned = sorted(set(candidate) & set(factor))
    diag = {
        "round_trips": float(len(round_trips)),
        "candidate_buckets": float(len(candidate)),
        "factor_buckets": float(len(factor)),
        "aligned_buckets": float(len(aligned)),
        "mean_trips_per_bucket": (sum(counts.values()) / len(counts)) if counts else 0.0,
    }
    result = build_residual_alpha_report(
        candidate,
        factor,
        n_trials=n_trials,
        peer_oos_returns=peer_oos_returns,
        required_factors=("btc",),
        # +0.5 桶：讓 R-1 的 ts-embargo cutoff 落在桶與桶之間，剛好 purge
        # embargo_buckets 個緊鄰 train 桶（grid-aligned 下避免 off-by-one）。
        embargo_gap=(embargo_buckets + 0.5) * bucket_sec if embargo_buckets > 0 else 0.0,
        min_train_observations=min_train_observations,
        min_eval_observations=min_eval_observations,
        **gate_kwargs,
    )
    return result, diag


# ---------------------------------------------------------------------------
# DB 查詢層（Linux runtime 驗證）—— 只讀；BTC-only v1 不需 PIT basket
# ---------------------------------------------------------------------------

# market.klines：欄位已驗 ts/open/close、timeframe='1m'（Linux 2026-06-05）。
_BTC_KLINES_QUERY = """
SELECT ts, open, close
FROM market.klines
WHERE symbol = %(symbol)s AND timeframe = %(tf)s
  AND ts >= %(start)s AND ts <= %(end)s
ORDER BY ts ASC
"""


def load_round_trips(
    conn: Any,
    strategy_name: str,
    *,
    engine_mode: str = "demo",
    since: datetime,
) -> list[dict[str, float]]:
    """從 trading.fills FIFO 配對出指定 entry strategy 的 round-trips（epoch 秒）。

    重用 realized_edge_stats 的 fills 查詢與 ``_pair_round_trips``（已測 FIFO 配對 +
    扣費 + winsorize + price-jump 防護），只取 exit 完成者。只讀。
    """
    from psycopg2.extras import RealDictCursor  # lazy：Mac pure-core 免依賴

    try:
        from program_code.ml_training import realized_edge_stats as _res
    except ModuleNotFoundError:  # pragma: no cover - 直跑 fallback
        from ml_training import realized_edge_stats as _res  # type: ignore

    modes = _res._engine_mode_scope(engine_mode)
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(_res._FILLS_QUERY, {"since": since, "engine_modes": modes})
        fills = [dict(row) for row in cur.fetchall()]
    out: list[dict[str, float]] = []
    for rec in _res._pair_round_trips(fills):
        if rec.strategy_name != strategy_name or rec.exit_ts is None:
            continue
        entry = to_epoch_seconds(rec.entry_ts)
        exit_ = to_epoch_seconds(rec.exit_ts)
        net = _finite(rec.net_pnl_bps)
        if entry is None or exit_ is None or net is None:
            continue
        out.append({"entry_ts": entry, "exit_ts": exit_, "net_bps": net})
    return out


def load_btc_klines(
    conn: Any,
    *,
    start_ts: datetime,
    end_ts: datetime,
    symbol: str = BTC_SYMBOL,
    timeframe: str = "1m",
) -> list[dict[str, float]]:
    """載 [start_ts, end_ts] 的 BTC 1m bars → ``[{"ts": epoch, "open", "close"}]``。只讀。"""
    from psycopg2.extras import RealDictCursor  # lazy

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            _BTC_KLINES_QUERY,
            {"symbol": symbol, "tf": timeframe, "start": start_ts, "end": end_ts},
        )
        rows = cur.fetchall()
    bars: list[dict[str, float]] = []
    for row in rows:
        ts = to_epoch_seconds(row["ts"])
        open_ = _finite(row["open"])
        close = _finite(row["close"])
        if ts is None or open_ is None or close is None:
            continue
        bars.append({"ts": ts, "open": open_, "close": close})
    return bars


def build_strategy_residual_report(
    conn: Any,
    strategy_name: str,
    *,
    engine_mode: str = "demo",
    since: datetime,
    n_trials: int,
    peer_oos_returns: Sequence[Any] | None = None,
    bucket_sec: float = DEFAULT_BUCKET_SEC,
    embargo_buckets: int = 1,
    klines_timeframe: str = "4h",
    klines_pad_sec: float = DEFAULT_BUCKET_SEC,
    **gate_kwargs: Any,
) -> tuple[ResidualAlphaProducerResult | None, dict[str, float]]:
    """單策略 BTC-only **非重疊 bucket** residual report（v1 主路徑）。

    載 FIFO round-trips + BTC bucket klines（預設 4h）→ 按 exit 歸桶 → R-1。
    peers / n_trials 由 caller（cycle orchestrator）提供；peers 缺則 gate 因無
    PBO evidence 而 defer（honest，非 bug）。只讀；不碰 runtime / order / risk。
    """
    round_trips = load_round_trips(conn, strategy_name, engine_mode=engine_mode, since=since)
    if not round_trips:
        return None, {"round_trips": 0.0, "aligned_buckets": 0.0}
    min_entry = min(rt["entry_ts"] for rt in round_trips)
    max_exit = max(rt["exit_ts"] for rt in round_trips)
    start_dt = datetime.fromtimestamp(min_entry - klines_pad_sec, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(max_exit + klines_pad_sec, tz=timezone.utc)
    btc_klines = load_btc_klines(
        conn, start_ts=start_dt, end_ts=end_dt, timeframe=klines_timeframe
    )
    return build_bucketed_residual_report(
        round_trips,
        btc_klines,
        n_trials=n_trials,
        bucket_sec=bucket_sec,
        embargo_buckets=embargo_buckets,
        peer_oos_returns=peer_oos_returns,
        **gate_kwargs,
    )


__all__ = [
    "BTC_SYMBOL",
    "KLINES_1M_INTERVAL_SEC",
    "DEFAULT_BUCKET_SEC",
    "to_epoch_seconds",
    "contained_bar_return_bps",
    "pit_active_symbols",
    "assemble_residual_inputs",
    "build_residual_report_from_data",
    "bucket_floor",
    "bucket_round_trips_by_exit",
    "bucketed_btc_factor",
    "build_bucketed_residual_report",
    "load_round_trips",
    "load_btc_klines",
    "build_strategy_residual_report",
]
