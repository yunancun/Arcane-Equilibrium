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


# ---------------------------------------------------------------------------
# 多因子 bucket 路徑（Gap B：btc + market + funding-carry）—— leak surface 全在此
# ---------------------------------------------------------------------------
# 為什麼加多因子：候選對 BTC 中性，但對板塊/市值（market basket）或 funding-carry
# 殘留 beta 仍會偽裝成 edge（funding-tilt 策略即死於 carry beta，BTC-price beta 抓
# 不到）。多因子殘差化把這些已實現曝險一併扣除，讓 gate 看到的是真 residual α。
# 行為中性硬約束：required_factors 預設仍是 ("btc",)；只有 caller（未來的 Stage-0R
# orchestrator）顯式傳 ("btc","market","funding") 才啟用，現有 cron/payload 流不變。


def _bucketed_symbol_return(
    klines: Sequence[Mapping[str, Any]],
    bucket_sec: float,
) -> dict[float, float]:
    """單一 symbol 的 bucket open→close 報酬（bps），與 ``bucketed_btc_factor``
    同語意（一桶多根取最早 open、最晚 close；價格非法則該桶無值）。"""
    by_bucket: dict[float, list[tuple[float, Mapping[str, Any]]]] = {}
    for bar in klines:
        ts = _finite(bar.get("ts"))
        if ts is None:
            continue
        by_bucket.setdefault(bucket_floor(ts, bucket_sec), []).append((ts, bar))
    out: dict[float, float] = {}
    for bucket_ts, bars in by_bucket.items():
        bars.sort(key=lambda item: item[0])
        first_open = _finite(bars[0][1].get("open"))
        last_close = _finite(bars[-1][1].get("close"))
        if first_open is None or last_close is None or first_open <= 0.0:
            continue
        out[bucket_ts] = (last_close / first_open - 1.0) * 10_000.0
    return out


def bucketed_funding_factor(
    funding_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    position_symbols: Sequence[str],
    *,
    net_side: int = 1,
    bucket_sec: float = DEFAULT_BUCKET_SEC,
) -> dict[float, float]:
    """每桶已實現 funding-carry（bps），PIT、leak-free。

    funding_by_symbol: ``{symbol: [{"ts": settlement_epoch, "funding_rate": frac}, ...]}``；
      ``ts`` 是 funding **結算時刻**（Bybit market.funding_rates.ts，8h 結算）。
    position_symbols: 該候選持倉的 symbol（多 symbol 取等權平均）。
    net_side: +1=做多、-1=做空（caller 提供候選淨方向）。

    PIT 規則（§5.1 最高風險，硬約束）：一桶 ``(bucket_start, bucket_end]`` 的
    funding 只計**結算時刻 ts 落在桶窗內**的結算列，即
    ``bucket_start < ts <= bucket_end``。**永不**用桶結束後才結算的下一筆 rate
    （那是策略當下不可能知道的未來費率）；以結算時刻歸桶等價於「只用
    ``ts <= bucket_end`` 的已結算列」並按桶切分。realized-over-window 累加。

    sign：Bybit funding_rate 為正代表多方付費給空方。故對候選報酬軸的貢獻是
    ``-net_side * funding_rate``（做多付費=負報酬；做空收費=正報酬），轉 bps。
    回 ``{bucket_ts: funding_bps}``；桶內無結算列則該桶無值（caller 對不齊的桶
    自然落在 factor 缺值而被丟棄，不回退）。
    """
    side = 1 if int(net_side) >= 0 else -1
    syms = [s for s in position_symbols if s in funding_by_symbol]
    if not syms:
        return {}
    # 先把每個 symbol 的結算列依桶累加 realized funding（fraction）。
    per_symbol_bucket: dict[str, dict[float, float]] = {}
    for symbol in syms:
        acc: dict[float, float] = {}
        for row in funding_by_symbol.get(symbol, ()):  # type: ignore[union-attr]
            ts = _finite(row.get("ts"))
            rate = _finite(row.get("funding_rate"))
            if ts is None or rate is None:
                continue
            # 結算時刻歸桶：ts 落在 (bucket_start, bucket_end] → 進該桶。
            # 用 ceil-1 對齊：恰在桶邊界 ts==bucket_start 的結算屬「上一桶尾」，
            # 故落點桶 = floor((ts - epsilon)/bucket)，等價 (bucket_start, bucket_end]。
            bucket_ts = bucket_floor(ts - _BUCKET_EPS, bucket_sec)
            acc[bucket_ts] = acc.get(bucket_ts, 0.0) + rate
        per_symbol_bucket[symbol] = acc
    # 跨 symbol 等權平均（只在有列的 symbol 上平均，與 market basket 一致）。
    all_buckets: set[float] = set()
    for acc in per_symbol_bucket.values():
        all_buckets.update(acc)
    out: dict[float, float] = {}
    for bucket_ts in all_buckets:
        members = [
            per_symbol_bucket[s][bucket_ts]
            for s in syms
            if bucket_ts in per_symbol_bucket[s]
        ]
        if not members:
            continue
        realized = sum(members) / len(members)
        out[bucket_ts] = -side * realized * 10_000.0
    return out


# bucket 邊界 epsilon：結算時刻恰在桶起點時歸入「上一桶」，確保
# (bucket_start, bucket_end] 半開區間語意（避免把桶起點當下一桶的未來費率）。
_BUCKET_EPS: float = 1e-6


def bucketed_multi_factor(
    klines_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]],
    lifecycles: Mapping[str, tuple[float | None, float | None]],
    *,
    required_factors: tuple[str, ...] = ("btc",),
    bucket_sec: float = DEFAULT_BUCKET_SEC,
    btc_symbol: str = BTC_SYMBOL,
    min_basket_symbols: int = DEFAULT_MIN_BASKET_SYMBOLS,
    funding_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    position_symbols: Sequence[str] | None = None,
    net_side: int = 1,
) -> dict[float, dict[str, float]]:
    """在同一條非重疊 exit-keyed 4h bucket 網格上產出多因子 panel。

    回 ``{bucket_ts: {"btc":.., "market":.., "funding":..}}``（僅含 required_factors
    要求的因子）。每個因子都在同一桶網格、與候選 bucket 報酬同單位（bps）、同時程，
    故 beta 是真實已實現曝險、leak-free。

    - "btc"：``klines_by_symbol[btc_symbol]`` 的桶 open→close 報酬。
    - "market"：每桶取**該桶窗內 PIT-active**（``pit_active_symbols`` lifecycle 權威，
      含已下市、排 survivorship）的 symbol 等權平均；成員 < ``min_basket_symbols``
      則該桶無 market 值。桶窗用 ``[bucket_start, bucket_end]``（含界，與
      pit_active_symbols 的 listed<=entry / delisted>exit 判定一致）。
    - "funding"：見 ``bucketed_funding_factor``（PIT：只用 ts<=bucket_end 的已結算列）。
      需 caller 傳 ``funding_by_symbol`` + ``position_symbols`` + ``net_side``；缺則
      raise（不得靜默產出無 funding 的 panel，避免誤判殘差化已涵蓋 carry）。

    桶若缺任一 required factor 值，該桶不入 panel（R-1 的對齊只取 factor 含全部
    required factor 的 ts）。
    """
    # 先逐因子算各自的 bucket→value，再在桶層 intersection 組裝。
    btc_by_bucket: dict[float, float] = {}
    if "btc" in required_factors:
        btc_by_bucket = _bucketed_symbol_return(
            klines_by_symbol.get(btc_symbol, ()), bucket_sec
        )

    market_by_bucket: dict[float, float] = {}
    if "market" in required_factors:
        # 各 symbol 的桶報酬先算好（含 btc 自身可入 basket，與 1m 路徑一致：basket
        # 是 PIT universe 等權，不刻意剔除 btc）。
        symbol_bucket_returns: dict[str, dict[float, float]] = {
            symbol: _bucketed_symbol_return(klines, bucket_sec)
            for symbol, klines in klines_by_symbol.items()
        }
        all_buckets: set[float] = set()
        for ret_map in symbol_bucket_returns.values():
            all_buckets.update(ret_map)
        for bucket_ts in all_buckets:
            bucket_start = bucket_ts
            bucket_end = bucket_ts + bucket_sec
            active = pit_active_symbols(lifecycles, bucket_start, bucket_end)
            members = [
                symbol_bucket_returns[s][bucket_ts]
                for s in active
                if s in symbol_bucket_returns and bucket_ts in symbol_bucket_returns[s]
            ]
            if len(members) < min_basket_symbols:
                continue
            market_by_bucket[bucket_ts] = sum(members) / len(members)

    funding_by_bucket: dict[float, float] = {}
    if "funding" in required_factors:
        if funding_by_symbol is None or position_symbols is None:
            raise ValueError(
                "funding factor requires funding_by_symbol and position_symbols"
            )
        funding_by_bucket = bucketed_funding_factor(
            funding_by_symbol,
            position_symbols,
            net_side=net_side,
            bucket_sec=bucket_sec,
        )

    factor_maps: dict[str, dict[float, float]] = {}
    for fac in required_factors:
        if fac == "btc":
            factor_maps["btc"] = btc_by_bucket
        elif fac == "market":
            factor_maps["market"] = market_by_bucket
        elif fac == "funding":
            factor_maps["funding"] = funding_by_bucket
        else:
            raise ValueError(f"unsupported factor: {fac!r}")

    # 桶層 intersection：只保留所有 required factor 都有值的桶。
    if not factor_maps:
        return {}
    common: set[float] | None = None
    for ret_map in factor_maps.values():
        keys = set(ret_map)
        common = keys if common is None else (common & keys)
    common = common or set()
    panel: dict[float, dict[str, float]] = {}
    for bucket_ts in common:
        panel[bucket_ts] = {fac: factor_maps[fac][bucket_ts] for fac in required_factors}
    return panel


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


# market.klines 多 symbol 查詢（Gap B market basket 來源；欄位同 _BTC_KLINES_QUERY）。
# 用 ANY(%(symbols)s) 一次拉多 symbol，呼叫端按 symbol group。
_MULTI_KLINES_QUERY = """
SELECT symbol, ts, open, close
FROM market.klines
WHERE symbol = ANY(%(symbols)s) AND timeframe = %(tf)s
  AND ts >= %(start)s AND ts <= %(end)s
ORDER BY symbol, ts ASC
"""

# market.symbol_universe_snapshots：lifecycle 權威（Linux 2026-06-08 驗 948 symbol，
# listed_at/delisted_at 已 populate）。同 symbol 多筆 snapshot ts → 取最早 listed_at
# 與**最新一筆**的 delisted_at（is_delisted_at_asof 反映當前下市狀態，用 DISTINCT ON
# 取每 symbol 最新 ts 的 delisted_at；listed_at 取全期最小，含已下市，排 survivorship）。
_SYMBOL_LIFECYCLE_QUERY = """
SELECT
    u.symbol,
    u.listed_min AS listed_at,
    latest.delisted_at AS delisted_at
FROM (
    SELECT symbol, MIN(listed_at) AS listed_min
    FROM market.symbol_universe_snapshots
    GROUP BY symbol
) u
LEFT JOIN LATERAL (
    SELECT delisted_at
    FROM market.symbol_universe_snapshots s
    WHERE s.symbol = u.symbol
    ORDER BY s.ts DESC
    LIMIT 1
) latest ON TRUE
"""


def load_symbol_lifecycles(
    conn: Any,
) -> dict[str, tuple[float | None, float | None]]:
    """載全 universe 的 symbol lifecycle（listed_at/delisted_at，epoch 秒）。只讀。

    回 ``{symbol: (listed_at_epoch | None, delisted_at_epoch | None)}``，供
    ``pit_active_symbols`` / ``bucketed_multi_factor`` 的 market basket 做 PIT
    成員判定（含已下市 symbol，排 survivorship bias，§5.2）。listed_at 取全期最小、
    delisted_at 取最新一筆 snapshot（反映當前下市狀態）。Linux runtime 驗 lifecycle
    時序；Mac 測試用合成 lifecycle。
    """
    from psycopg2.extras import RealDictCursor  # lazy

    out: dict[str, tuple[float | None, float | None]] = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(_SYMBOL_LIFECYCLE_QUERY)
        for row in cur.fetchall():
            symbol = str(row.get("symbol") or "").strip()
            if not symbol:
                continue
            listed = to_epoch_seconds(row.get("listed_at"))
            delisted = to_epoch_seconds(row.get("delisted_at"))
            out[symbol] = (listed, delisted)
    return out


def load_klines_by_symbols(
    conn: Any,
    symbols: Sequence[str],
    *,
    start_ts: datetime,
    end_ts: datetime,
    timeframe: str = "4h",
) -> dict[str, list[dict[str, float]]]:
    """載 [start_ts, end_ts] 多 symbol 的 bucket klines（預設 4h）。只讀。

    回 ``{symbol: [{"ts": epoch, "open", "close"}, ...]}``（ts 升序），供
    ``bucketed_multi_factor`` 的 market basket。空 symbols → 回 ``{}``。
    """
    syms = [str(s).strip() for s in symbols if str(s).strip()]
    if not syms:
        return {}
    from psycopg2.extras import RealDictCursor  # lazy

    out: dict[str, list[dict[str, float]]] = {s: [] for s in syms}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            _MULTI_KLINES_QUERY,
            {"symbols": syms, "tf": timeframe, "start": start_ts, "end": end_ts},
        )
        for row in cur.fetchall():
            symbol = str(row.get("symbol") or "").strip()
            ts = to_epoch_seconds(row.get("ts"))
            open_ = _finite(row.get("open"))
            close = _finite(row.get("close"))
            if not symbol or ts is None or open_ is None or close is None:
                continue
            out.setdefault(symbol, []).append({"ts": ts, "open": open_, "close": close})
    return out


# market.funding_rates：欄位已驗 ts(timestamptz)/symbol/funding_rate(real)
# （Linux 2026-06-08，BTCUSDT 8h 結算）。design §2 Gap B 稱此欄為 ``funding_time``，
# 倉內實際欄名是 ``ts``（結算時刻）；語意一致（PIT：只取 ts<=bucket_end 的已結算列）。
_FUNDING_RATES_QUERY = """
SELECT ts, funding_rate
FROM market.funding_rates
WHERE symbol = %(symbol)s
  AND ts >= %(start)s AND ts <= %(end)s
ORDER BY ts ASC
"""


def load_funding_rates(
    conn: Any,
    symbols: Sequence[str],
    *,
    start_ts: datetime,
    end_ts: datetime,
) -> dict[str, list[dict[str, float]]]:
    """載 [start_ts, end_ts] 各 symbol 的 funding 結算列。只讀。

    回 ``{symbol: [{"ts": settlement_epoch, "funding_rate": frac}, ...]}``（ts 升序）。
    ``ts`` 是結算時刻（Bybit 8h），供 ``bucketed_funding_factor`` 做 PIT 歸桶
    （只用 ts<=bucket_end 的已結算列，永不取下一筆未結算費率）。
    Linux runtime 驗證 funding 結算時序語意（§5.1）；Mac 測試用合成結算列。
    """
    from psycopg2.extras import RealDictCursor  # lazy：Mac pure-core 免依賴

    out: dict[str, list[dict[str, float]]] = {}
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for symbol in symbols:
            cur.execute(
                _FUNDING_RATES_QUERY,
                {"symbol": symbol, "start": start_ts, "end": end_ts},
            )
            rows = cur.fetchall()
            series: list[dict[str, float]] = []
            for row in rows:
                ts = to_epoch_seconds(row["ts"])
                rate = _finite(row["funding_rate"])
                if ts is None or rate is None:
                    continue
                series.append({"ts": ts, "funding_rate": rate})
            out[symbol] = series
    return out


def derive_net_side_from_fills(
    fills: Sequence[Mapping[str, Any]],
    strategy_name: str,
) -> tuple[int, dict[str, float]]:
    """從 fills 推導候選策略的**淨方向**（+1=做多 / -1=做空），純函數。

    為什麼這是 MIT 硬條件（funding sign）：``load_round_trips`` 的 FIFO 配對只回
    ``net_bps``，**丟失** entry side（往返淨報酬不帶方向）。但 funding-carry factor
    的 sign 取決於候選**淨持倉方向**——funding_rate 為正時做多付費（負報酬）、做空收費
    （正報酬）。若用 ``net_side=+1`` 預設套到一個淨做空候選，funding factor 會**反號**，
    殘差化不但沒扣除 carry beta 反而**放大**它 → 正是本功能要消滅的 false-promote 向量。
    故 orchestrator 必須先從真實 fills 推導 net_side，**絕不**把 +1 預設送進真實 run。

    推導：候選**入場成交**（``strategy_name`` 等於候選策略、且非平倉——平倉用 prefixed
    名 ``risk_close:`` / ``strategy_close:`` / ``stop_*`` 並帶 realized_pnl）的
    **淨 signed-qty** = Σ side_sign × qty（Buy=+1、Sell=-1）。其符號即淨方向曝險。
    回 ``(net_side, diag)``：net_side ∈ {+1, -1}（淨 0 / 無入場成交時回 +1 並於 diag
    標 ``ambiguous=1.0`` 供 caller fail-loud，**不**靜默吞）。

    diag: ``{"entry_fills": n, "net_signed_qty": float, "abs_signed_qty": float,
            "ambiguous": 0.0|1.0}``。
    """
    net_signed_qty = 0.0
    abs_signed_qty = 0.0
    entry_fills = 0
    for fill in fills:
        name = str(fill.get("strategy_name") or "")
        if name != strategy_name:
            # 只看候選自己的入場成交；平倉成交用 prefixed 名（與候選名不同）→
            # 自然被此判據排除，無需重複 is_exit 前綴清單。
            continue
        # 雙保險：即使平倉成交誤帶候選名（理論上不該），realized_pnl != 0 視為平倉略過。
        realized = _finite(fill.get("realized_pnl"))
        if realized is not None and realized != 0.0:
            continue
        qty = _finite(fill.get("qty"))
        if qty is None or qty <= 0.0:
            continue
        side = str(fill.get("side") or "").strip().lower()
        if side == "buy":
            sign = 1.0
        elif side == "sell":
            sign = -1.0
        else:
            continue
        net_signed_qty += sign * qty
        abs_signed_qty += qty
        entry_fills += 1
    diag = {
        "entry_fills": float(entry_fills),
        "net_signed_qty": net_signed_qty,
        "abs_signed_qty": abs_signed_qty,
        "ambiguous": 0.0,
    }
    if entry_fills == 0 or net_signed_qty == 0.0:
        diag["ambiguous"] = 1.0
        return 1, diag
    return (1 if net_signed_qty > 0.0 else -1), diag


def load_candidate_net_side(
    conn: Any,
    strategy_name: str,
    *,
    engine_mode: str = "demo",
    since: datetime,
) -> tuple[int, dict[str, float]]:
    """讀 trading.fills 推導候選策略淨方向（+1/-1），只讀。

    重用 realized_edge_stats 的 ``_FILLS_QUERY`` + ``_engine_mode_scope``（與
    ``load_round_trips`` 同一 fills 來源），交給純函數 ``derive_net_side_from_fills``
    計算。回 ``(net_side, diag)``。Linux runtime 驗 fills.side 語意；Mac 測試用合成 fills。
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
    return derive_net_side_from_fills(fills, strategy_name)


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
    "bucketed_funding_factor",
    "bucketed_multi_factor",
    "build_bucketed_residual_report",
    "load_round_trips",
    "load_btc_klines",
    "load_klines_by_symbols",
    "load_symbol_lifecycles",
    "load_funding_rates",
    "derive_net_side_from_fills",
    "load_candidate_net_side",
    "build_strategy_residual_report",
]
