"""REF-21 full-chain replay fixture prep — 自足資料層抽出（2026-06-02）。

MODULE_NOTE
模塊用途：
    從 ``app/replay_full_chain_routes.py``（重構前 1931 LOC，2 route + ~1900
    inline）下推的「自足資料準備層」。承載 full-chain replay fixture 組裝所需
    的純函式與 PG 讀取 helper：production TOML echo、microstructure / orderbook
    overlay、instrument spec、edge snapshot / historical universe 讀取、
    input fidelity 摘要、manifest_jsonb 組裝。

    為何抽出（CLAUDE §七 route rule + §九 LOC guardrail）：
    route handler 應 parse→call→format；~1000 LOC 純資料邏輯 inline 在 2 個
    handler 之下違反該規則且逼近 2000 LOC 硬上限。本 module 把與 ``app/`` 無耦合
    的部分（除 PG 連線經 DI 注入）整塊下移，與既有 ``replay/route_helpers.py`` /
    ``replay/run_route.py`` 的抽出範式一致。

主要類/函數：
    - PG 讀取（DI ``get_pg_conn_fn`` + ``statement_timeout_ms``）：
      ``fetch_microstructure_overlays_sync`` / ``fetch_historical_universe_snapshot_sync``
      / ``fetch_edge_estimate_snapshot_sync``
    - 純轉換：``apply_microstructure_overlays`` / ``instrument_specs_from_universe``
      / ``apply_instrument_specs`` / ``build_input_fidelity_summary``
    - production TOML echo：``load_production_scanner_config`` /
      ``load_production_strategy_params_toml`` / ``load_production_risk_overrides_toml``
    - manifest：``build_manifest_jsonb``
    - 工具：``canonical_sha256`` / ``iso_from_ms`` / ``cursor_fetchall``
      / ``normalise_edge_payload`` / ``json_safe_payload`` / ``finite_float``

依賴：
    stdlib（json/hashlib/os/bisect/datetime/decimal/pathlib/tomllib）。
    PG 連線與 statement timeout 由 caller（route 模塊）以 DI 注入，不直接 import
    ``app.db_pool`` —— 維持 ``replay/`` 對 ``app/`` 零反向 import 的分層不變式。

硬邊界：
    - 純行為保留搬移：SQL 字串、欄位順序、reason code、coverage 計算、manifest
      key 全與重構前 byte-identical。不得「順手優化」。
    - PG 讀取任一例外回 fail-soft 結構（status=unavailable + reason），不外拋；
      與重構前一致（replay 是 audit/evidence 面，缺資料須標記而非中斷）。

SPEC: REF-21 full-chain replay；root principle #8（每筆交易可重建）。
"""

from __future__ import annotations

import bisect
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

# Python 3.11+ stdlib tomllib；Mac dev 在 py3.10 可裝 tomli 1.x backport
# （runtime 跑於 Linux py 3.12.3 已驗，tomllib 直接可用）
try:
    import tomllib  # type: ignore[unresolved-import]
    _TOMLLIB_DECODE_ERROR: type = tomllib.TOMLDecodeError
except ImportError:  # pragma: no cover — Mac py3.10 dev only path
    try:
        import tomli as tomllib  # type: ignore[no-redef]
        _TOMLLIB_DECODE_ERROR = tomllib.TOMLDecodeError
    except ImportError:
        tomllib = None  # type: ignore[assignment]
        _TOMLLIB_DECODE_ERROR = Exception


logger = logging.getLogger(__name__)

# full-chain manifest 內代表「整個 universe」的 symbol sentinel；route 模塊
# re-import 此常量以保單一來源（避免重複字面值漂移）。
_FULL_CHAIN_SYMBOL_SENTINEL = "FULL_CHAIN"


def canonical_sha256(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
# Production TOML loaders — P0 Replay Tier A T3 + T4 (2026-05-11)
# 生產 TOML 讀取器 — P0 Replay Tier A T3 + T4
#
# 目的：讓 replay manifest 直接 echo production TOML 內的 scanner_config /
#       strategy_params / risk_overrides，使 replay 真實 reflect 生產環境配置
#       （pinned 25 sym + per-strategy gate + per-engine risk limits），而不是
#       依賴 Rust replay_default_scanner_config 或 hardcoded fallback。
#
# 設計取捨：
# - 用 tomllib（py 3.11+ stdlib，Linux runtime py 3.12.3 已驗）
# - 路徑來自 OPENCLAW_BASE_DIR；fallback 用 Path(__file__).resolve().parents[N]
#   對齊 paper_trading_routes.py:1128 既有 pattern
# - 每次 build_manifest_jsonb 重讀 TOML（不 cache），確保 manifest 反映當下
#   production 配置；run 是 ad-hoc 觸發，重讀成本可忽略
# - load 失敗（檔案不存在/parse 失敗）回 None，不 raise — replay 退化為
#   舊 Rust replay_default_scanner_config 行為，與 production 不對齊但不阻斷
#
# SAFETY / 不變量：
# - manifest_jsonb 加 top-level "scanner_config" / "strategy_params" /
#   "risk_overrides" key 不破 V3 §5 sha256(manifest_jsonb)==manifest_hash 不變式
#   （experiment_registry compute_manifest_canonical_bytes 對整 dict 做 sort_keys
#   canonical sha256；新 key 直接 land canonical bytes）
# - manifest_jsonb size cap 256KB（_size_cap validator）— scanner_config <2KB、
#   strategy_params <5KB、risk_overrides <10KB 全 OK
# - 新 key 都不以 "_" 開頭 → M-4 _no_reserved_prefix_keys validator 不報拒
# ─────────────────────────────────────────────────────────────────────────────


def resolve_settings_root() -> Path:
    """解析 settings/ 根目錄。

    優先用 OPENCLAW_BASE_DIR env var；fallback 用相對路徑回推 srv/。
    對齊 paper_trading_routes._PAPER_CONFIG_PATH 既有 pattern。

    註：本檔位於 ``control_api_v1/replay/``，與舊 ``app/`` 版本是同層 sibling
    目錄（兩者都在 ``control_api_v1/`` 下一層），故 ``parents[5]`` 同樣回到 srv/，
    與抽出前 ``app/replay_full_chain_routes._resolve_settings_root`` byte-identical。
    OPENCLAW_BASE_DIR 為 runtime 正路，fallback 僅 Mac dev 無 env 時用。
    """
    base = os.environ.get("OPENCLAW_BASE_DIR")
    if base:
        return Path(base) / "settings"
    # fallback: replay/<this>.py → parents[5] = srv/（與 app/ 版本同層同深）
    return Path(__file__).resolve().parents[5] / "settings"


def load_production_scanner_config() -> Optional[dict[str, Any]]:
    """讀 settings/risk_control_rules/scanner_config.toml 為 dict。

    回 None 表示 tomllib 不可用 / 檔案不可讀 / parse 失敗
    （replay 退化為 Rust replay_default_scanner_config）。
    """
    if tomllib is None:
        logger.warning(
            "replay_full_chain: tomllib unavailable (py < 3.11 + no tomli); "
            "scanner_config echo skipped",
        )
        return None
    toml_path = resolve_settings_root() / "risk_control_rules" / "scanner_config.toml"
    if not toml_path.exists():
        logger.warning(
            "replay_full_chain: scanner_config.toml not found at %s; "
            "replay falls back to Rust replay_default_scanner_config",
            toml_path,
        )
        return None
    try:
        with open(toml_path, "rb") as f:
            return tomllib.load(f)
    except (OSError, _TOMLLIB_DECODE_ERROR) as exc:
        logger.warning(
            "replay_full_chain: failed to load scanner_config.toml %s: %s",
            toml_path, exc,
        )
        return None


def load_production_strategy_params_toml(*, engine: str) -> Optional[dict[str, Any]]:
    """讀 settings/strategy_params_<engine>.toml 為 dict。

    engine ∈ {"demo", "live", "paper"}；replay 主要走 demo / live。
    Returns None on failure（manifest 不含此 key，replay 退化為策略默認）。
    """
    if tomllib is None:
        return None
    engine_norm = (engine or "").strip().lower()
    if engine_norm not in ("demo", "live", "paper"):
        return None
    toml_path = resolve_settings_root() / f"strategy_params_{engine_norm}.toml"
    if not toml_path.exists():
        logger.warning(
            "replay_full_chain: strategy_params_%s.toml not found at %s",
            engine_norm, toml_path,
        )
        return None
    try:
        with open(toml_path, "rb") as f:
            return tomllib.load(f)
    except (OSError, _TOMLLIB_DECODE_ERROR) as exc:
        logger.warning(
            "replay_full_chain: failed to load strategy_params_%s.toml %s: %s",
            engine_norm, toml_path, exc,
        )
        return None


def load_production_risk_overrides_toml(*, engine: str) -> Optional[dict[str, Any]]:
    """讀 settings/risk_control_rules/risk_config_<engine>.toml 為 dict。

    engine ∈ {"demo", "live", "paper"}。Returns None on failure。
    """
    if tomllib is None:
        return None
    engine_norm = (engine or "").strip().lower()
    if engine_norm not in ("demo", "live", "paper"):
        return None
    toml_path = (
        resolve_settings_root() / "risk_control_rules" / f"risk_config_{engine_norm}.toml"
    )
    if not toml_path.exists():
        logger.warning(
            "replay_full_chain: risk_config_%s.toml not found at %s",
            engine_norm, toml_path,
        )
        return None
    try:
        with open(toml_path, "rb") as f:
            return tomllib.load(f)
    except (OSError, _TOMLLIB_DECODE_ERROR) as exc:
        logger.warning(
            "replay_full_chain: failed to load risk_config_%s.toml %s: %s",
            engine_norm, toml_path, exc,
        )
        return None


def iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def cursor_fetchall(cur: Any) -> list[Any]:
    rows = cur.fetchall()
    return list(rows or [])


def microstructure_overlay_enabled() -> bool:
    raw = os.environ.get("OPENCLAW_REPLAY_MICROSTRUCTURE_OVERLAY_ENABLED", "1")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def microstructure_max_staleness_ms() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_MICROSTRUCTURE_MAX_STALENESS_MS", "120000")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 120_000
    return max(0, min(parsed, 3_600_000))


def fetch_microstructure_overlays_sync(
    *,
    get_pg_conn_fn: Callable[..., Any],
    statement_timeout_ms: int,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    """Fetch locally recorded ticker BBO rows for fixture enrichment.

    Bybit's public ticker/orderbook REST endpoints are current snapshots, not
    historical endpoints. REF-21 only enriches historical fixtures from locally
    recorded `market.market_tickers` rows and labels the coverage explicitly.
    """
    if not microstructure_overlay_enabled():
        return {
            "status": "disabled",
            "source": "market.market_tickers",
            "records": {},
            "reason": "env_disabled",
        }
    if not symbols:
        return {
            "status": "empty",
            "source": "market.market_tickers",
            "records": {},
            "reason": "empty_symbols",
        }
    try:
        with get_pg_conn_fn() as conn:
            if conn is None:
                return {
                    "status": "unavailable",
                    "source": "market.market_tickers",
                    "records": {},
                    "reason": "pg_unavailable",
                }
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s;", (statement_timeout_ms,))
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'market'
                      AND table_name = 'market_tickers'
                );
                """
            )
            if not bool(cur.fetchone()[0]):
                return {
                    "status": "unavailable",
                    "source": "market.market_tickers",
                    "records": {},
                    "reason": "table_absent",
                }
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'market'
                      AND table_name = 'ob_snapshots'
                );
                """
            )
            has_orderbook = bool(cur.fetchone()[0])
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'market'
                  AND table_name = 'market_tickers';
                """
            )
            ticker_columns = {str(row[0]) for row in cursor_fetchall(cur)}
            funding_expr = (
                "funding_rate"
                if "funding_rate" in ticker_columns
                else "NULL::real AS funding_rate"
            )
            cur.execute(
                f"""
                SELECT
                    symbol,
                    floor(extract(epoch from ts) * 1000)::bigint AS ts_ms,
                    best_bid,
                    best_ask,
                    bid_size,
                    ask_size,
                    spread_bps,
                    volume_24h,
                    turnover_24h,
                    index_price,
                    open_interest,
                    {funding_expr}
                FROM market.market_tickers
                WHERE symbol = ANY(%s)
                  AND ts >= to_timestamp(%s / 1000.0)
                  AND ts <= to_timestamp(%s / 1000.0)
                  AND best_bid IS NOT NULL
                  AND best_ask IS NOT NULL
                ORDER BY symbol, ts ASC;
                """,
                (symbols, start_ms - microstructure_max_staleness_ms(), end_ms),
            )
            rows = cursor_fetchall(cur)
            ob_rows: list[Any] = []
            if has_orderbook:
                cur.execute(
                    """
                    SELECT
                        symbol,
                        floor(extract(epoch from ts) * 1000)::bigint AS ts_ms,
                        bid_depth_5,
                        ask_depth_5,
                        spread_bps
                    FROM market.ob_snapshots
                    WHERE symbol = ANY(%s)
                      AND ts >= to_timestamp(%s / 1000.0)
                      AND ts <= to_timestamp(%s / 1000.0)
                    ORDER BY symbol, ts ASC;
                    """,
                    (
                        symbols,
                        start_ms - microstructure_max_staleness_ms(),
                        end_ms,
                    ),
                )
                ob_rows = cursor_fetchall(cur)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "source": "market.market_tickers",
            "records": {},
            "reason": type(exc).__name__,
            "message": str(exc),
        }

    records: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row[0]).strip().upper()
        best_bid = float(row[2]) if row[2] is not None else None
        best_ask = float(row[3]) if row[3] is not None else None
        if (
            not symbol
            or best_bid is None
            or best_ask is None
            or best_bid <= 0
            or best_ask <= 0
            or best_bid > best_ask
        ):
            continue
        records.setdefault(symbol, []).append({
            "ts_ms": int(row[1]),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_size": float(row[4]) if row[4] is not None else None,
            "ask_size": float(row[5]) if row[5] is not None else None,
            "spread_bps": float(row[6]) if row[6] is not None else None,
            "volume_24h": float(row[7]) if row[7] is not None else None,
            "turnover_24h": float(row[8]) if row[8] is not None else None,
            "index_price": float(row[9]) if row[9] is not None else None,
            "open_interest": float(row[10]) if row[10] is not None else None,
            "funding_rate": float(row[11]) if row[11] is not None else None,
        })
    orderbook_records: dict[str, list[dict[str, Any]]] = {}
    for row in ob_rows:
        symbol = str(row[0]).strip().upper()
        if not symbol:
            continue
        bid_depth = finite_float(row[2])
        ask_depth = finite_float(row[3])
        if bid_depth is None and ask_depth is None:
            continue
        orderbook_records.setdefault(symbol, []).append({
            "ts_ms": int(row[1]),
            "bid_depth_5": bid_depth,
            "ask_depth_5": ask_depth,
            "spread_bps": finite_float(row[4]),
        })
    record_count = sum(len(items) for items in records.values())
    orderbook_count = sum(len(items) for items in orderbook_records.values())
    return {
        "status": "ok" if (record_count or orderbook_count) else "empty",
        "source": "market.market_tickers+market.ob_snapshots",
        "records": records,
        "orderbook_records": orderbook_records,
        "record_count": record_count,
        "orderbook_record_count": orderbook_count,
        "symbol_count": len(records),
        "reason": None if (record_count or orderbook_count) else "no_microstructure_rows_for_window",
    }


def apply_microstructure_overlays(
    events: list[dict[str, Any]],
    overlay: dict[str, Any],
    *,
    max_staleness_ms: int,
) -> dict[str, Any]:
    records_by_symbol = overlay.get("records") if isinstance(overlay, dict) else None
    if not isinstance(records_by_symbol, dict):
        return {
            "status": "unavailable",
            "source": "market.market_tickers",
            "event_count": len(events),
            "enriched_event_count": 0,
            "reason": "records_missing",
        }

    timestamps: dict[str, list[int]] = {}
    for symbol, rows in records_by_symbol.items():
        if not isinstance(rows, list):
            continue
        rows.sort(key=lambda item: int(item.get("ts_ms", 0)))
        timestamps[str(symbol)] = [int(item.get("ts_ms", 0)) for item in rows]
    orderbook_by_symbol = overlay.get("orderbook_records")
    if not isinstance(orderbook_by_symbol, dict):
        orderbook_by_symbol = {}
    orderbook_timestamps: dict[str, list[int]] = {}
    for symbol, rows in orderbook_by_symbol.items():
        if not isinstance(rows, list):
            continue
        rows.sort(key=lambda item: int(item.get("ts_ms", 0)))
        orderbook_timestamps[str(symbol)] = [int(item.get("ts_ms", 0)) for item in rows]

    enriched = 0
    field_counts: dict[str, int] = {
        "best_bid": 0,
        "best_ask": 0,
        "turnover_24h": 0,
        "volume_24h": 0,
        "index_price": 0,
        "open_interest": 0,
        "funding_rate": 0,
        "bid_depth_5": 0,
        "ask_depth_5": 0,
    }
    orderbook_enriched = 0
    for event in events:
        symbol = str(event.get("symbol") or "").upper()
        event_ts = int(event.get("ts_ms") or 0)
        rows = records_by_symbol.get(symbol)
        ts_values = timestamps.get(symbol)
        ticker_enriched = False
        if rows and ts_values:
            idx = bisect.bisect_right(ts_values, event_ts) - 1
            if idx >= 0:
                record = rows[idx]
                age_ms = event_ts - int(record["ts_ms"])
                if 0 <= age_ms <= max_staleness_ms:
                    event["best_bid"] = record["best_bid"]
                    event["best_ask"] = record["best_ask"]
                    field_counts["best_bid"] += 1
                    field_counts["best_ask"] += 1
                    if record.get("bid_size") is not None:
                        event["bid_size"] = record["bid_size"]
                    if record.get("ask_size") is not None:
                        event["ask_size"] = record["ask_size"]
                    if record.get("spread_bps") is not None:
                        event["spread_bps"] = record["spread_bps"]
                    for field in (
                        "turnover_24h",
                        "volume_24h",
                        "index_price",
                        "open_interest",
                        "funding_rate",
                    ):
                        value = record.get(field)
                        if value is None:
                            continue
                        parsed = finite_float(value)
                        if parsed is not None:
                            event[field] = parsed
                            field_counts[field] += 1
                    ticker_enriched = True
        ob_rows = orderbook_by_symbol.get(symbol)
        ob_ts_values = orderbook_timestamps.get(symbol)
        ob_enriched = False
        if ob_rows and ob_ts_values:
            ob_idx = bisect.bisect_right(ob_ts_values, event_ts) - 1
            if ob_idx >= 0:
                ob_record = ob_rows[ob_idx]
                ob_age_ms = event_ts - int(ob_record["ts_ms"])
                if 0 <= ob_age_ms <= max_staleness_ms:
                    for field in ("bid_depth_5", "ask_depth_5", "spread_bps"):
                        value = ob_record.get(field)
                        if value is None:
                            continue
                        parsed = finite_float(value)
                        if parsed is not None:
                            event[field] = parsed
                            if field in field_counts:
                                field_counts[field] += 1
                    ob_enriched = True
                    orderbook_enriched += 1
        if ticker_enriched or ob_enriched:
            event["microstructure_source"] = (
                "market.market_tickers+market.ob_snapshots"
                if ticker_enriched and ob_enriched
                else ("market.ob_snapshots" if ob_enriched else "market.market_tickers")
            )
            enriched += 1

    field_coverage = {
        field: (count / len(events)) if events else 0.0
        for field, count in field_counts.items()
    }
    bbo_anchor_event_count = min(
        field_counts.get("best_bid", 0),
        field_counts.get("best_ask", 0),
    )
    bbo_anchor_coverage_ratio = (
        bbo_anchor_event_count / len(events)
        if events
        else 0.0
    )
    return {
        "status": "ok" if enriched else "empty",
        "source": "market.market_tickers+market.ob_snapshots",
        "event_count": len(events),
        "enriched_event_count": enriched,
        "orderbook_depth_event_count": orderbook_enriched,
        "orderbook_depth_coverage_ratio": (
            orderbook_enriched / len(events)
            if events
            else 0.0
        ),
        "coverage_ratio": (enriched / len(events)) if events else 0.0,
        "bbo_anchor_status": (
            "available" if bbo_anchor_event_count else "unavailable"
        ),
        "bbo_anchor_event_count": bbo_anchor_event_count,
        "bbo_anchor_coverage_ratio": bbo_anchor_coverage_ratio,
        "field_counts": field_counts,
        "field_coverage": field_coverage,
        "max_staleness_ms": max_staleness_ms,
        "reason": None if enriched else "no_matching_bbo_rows",
    }


def instrument_specs_from_universe(
    historical_universe: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    entries = historical_universe.get("entries")
    if not isinstance(entries, list):
        return specs
    for item in entries:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        specs[symbol] = {
            "tick_size": item.get("tick_size"),
            "qty_step": item.get("qty_step"),
            "min_notional": item.get("min_notional"),
            "source": "market.symbol_universe_snapshots",
        }
    return specs


def apply_instrument_specs(
    events: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not specs:
        return {
            "status": "empty",
            "source": "market.symbol_universe_snapshots",
            "event_count": len(events),
            "tick_size_event_count": 0,
            "coverage_ratio": 0.0,
            "reason": "no_specs",
        }
    tick_size_count = 0
    for event in events:
        symbol = str(event.get("symbol") or "").strip().upper()
        spec = specs.get(symbol)
        if not spec:
            continue
        value = spec.get("tick_size")
        if value is None:
            continue
        try:
            tick_size = float(value)
        except (TypeError, ValueError):
            continue
        if tick_size > 0 and tick_size == tick_size:
            event["tick_size"] = tick_size
            tick_size_count += 1
    return {
        "status": "ok" if tick_size_count else "empty",
        "source": "market.symbol_universe_snapshots",
        "event_count": len(events),
        "tick_size_event_count": tick_size_count,
        "coverage_ratio": (tick_size_count / len(events)) if events else 0.0,
        "reason": None if tick_size_count else "no_tick_size_for_events",
    }


def build_input_fidelity_summary(
    *,
    microstructure_stats: dict[str, Any],
    instrument_stats: dict[str, Any],
    edge_snapshot: dict[str, Any],
    execution_calibration: dict[str, Any],
) -> dict[str, Any]:
    field_coverage = microstructure_stats.get("field_coverage")
    if not isinstance(field_coverage, dict):
        field_coverage = {}
    return {
        "indicators": {
            "status": "runner_derived",
            "source": "fixture_ohlcv",
            "warmup_bars": 30,
        },
        "signals": {
            "status": "runner_derived",
            "source": "fixture_ohlcv_indicator_snapshot",
        },
        "microstructure": {
            "status": microstructure_stats.get("status"),
            "source": microstructure_stats.get("source"),
            "coverage_ratio": microstructure_stats.get("coverage_ratio", 0.0),
            "orderbook_depth_event_count": microstructure_stats.get(
                "orderbook_depth_event_count",
                0,
            ),
            "orderbook_depth_coverage_ratio": microstructure_stats.get(
                "orderbook_depth_coverage_ratio",
                0.0,
            ),
            "bbo_anchor_status": microstructure_stats.get("bbo_anchor_status"),
            "bbo_anchor_event_count": microstructure_stats.get(
                "bbo_anchor_event_count",
                0,
            ),
            "bbo_anchor_coverage_ratio": microstructure_stats.get(
                "bbo_anchor_coverage_ratio",
                0.0,
            ),
            "field_coverage": field_coverage,
        },
        "instrument_specs": {
            "status": instrument_stats.get("status"),
            "source": instrument_stats.get("source"),
            "tick_size_coverage_ratio": instrument_stats.get("coverage_ratio", 0.0),
        },
        "edge_snapshot": {
            "status": edge_snapshot.get("status"),
            "source": edge_snapshot.get("source"),
            "cell_count": edge_snapshot.get("cell_count", 0),
            "cutoff_iso": edge_snapshot.get("cutoff_iso"),
        },
        "execution_calibration": {
            "status": execution_calibration.get("status"),
            "source": execution_calibration.get("source"),
            "confidence": execution_calibration.get("execution_confidence"),
            "slippage_sample_count": execution_calibration.get(
                "slippage_sample_count",
                0,
            ),
            "recommended_taker_slippage_bps": execution_calibration.get(
                "recommended_taker_slippage_bps"
            ),
            "risk_overlay_applied": (
                execution_calibration.get("risk_overlay") or {}
            ).get("applied", False),
            "maker_fill_probability_status": execution_calibration.get(
                "maker_fill_probability_status"
            ),
            "maker_fill_confidence": execution_calibration.get(
                "maker_fill_confidence"
            ),
            "maker_order_sample_count": execution_calibration.get(
                "maker_order_sample_count",
                0,
            ),
            "maker_any_fill_probability": execution_calibration.get(
                "maker_any_fill_probability",
                0.0,
            ),
            "recommended_maker_fill_probability_cap": execution_calibration.get(
                "recommended_maker_fill_probability_cap",
            ),
            "latency_status": execution_calibration.get("latency_status"),
            "latency_sample_count": execution_calibration.get(
                "latency_sample_count",
                0,
            ),
            "latency_ms": execution_calibration.get("latency_ms"),
            "recommended_latency_ms": execution_calibration.get(
                "recommended_latency_ms"
            ),
        },
    }


def fetch_historical_universe_snapshot_sync(
    *,
    get_pg_conn_fn: Callable[..., Any],
    statement_timeout_ms: int,
    category: str,
    start_ms: int,
    end_ms: int,
    max_symbols: int,
) -> dict[str, Any]:
    """Read V058 as the default universe source for current-scanner replay."""
    try:
        with get_pg_conn_fn() as conn:
            if conn is None:
                return {
                    "status": "unavailable",
                    "source": "v058_symbol_universe_snapshots",
                    "reason": "pg_unavailable",
                    "symbols": [],
                }
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s;", (statement_timeout_ms,))
            cur.execute("SELECT to_regclass('market.market_tickers') IS NOT NULL;")
            has_market_tickers = bool(cur.fetchone()[0])
            latest_ticker_cte = (
                """
                latest_ticker AS (
                    SELECT DISTINCT ON (mt.symbol)
                        mt.symbol,
                        mt.turnover_24h
                    FROM market.market_tickers mt
                    JOIN candidate_symbols c ON c.symbol = mt.symbol
                    WHERE mt.ts <= to_timestamp(%s / 1000.0)
                    ORDER BY mt.symbol, mt.ts DESC
                )
                """
                if has_market_tickers
                else """
                latest_ticker AS (
                    SELECT NULL::text AS symbol, NULL::real AS turnover_24h
                    WHERE false
                )
                """
            )
            cur.execute(
                f"""
                WITH candidate_symbols AS (
                    SELECT DISTINCT symbol
                    FROM market.symbol_universe_snapshots
                    WHERE exchange = 'bybit'
                      AND category = %s
                      AND ts <= to_timestamp(%s / 1000.0)
                      AND (listed_at IS NULL OR listed_at <= to_timestamp(%s / 1000.0))
                      AND (delisted_at IS NULL OR delisted_at >= to_timestamp(%s / 1000.0))
                ),
                latest AS (
                    SELECT DISTINCT ON (s.symbol)
                        s.symbol,
                        s.ts,
                        s.status,
                        s.base_coin,
                        s.quote_coin,
                        s.contract_type,
                        s.tick_size,
                        s.qty_step,
                        s.min_notional,
                        s.listed_at,
                        s.delisted_at,
                        s.is_delisted_at_asof,
                        s.source_uri
                    FROM market.symbol_universe_snapshots s
                    JOIN candidate_symbols c ON c.symbol = s.symbol
                    WHERE s.exchange = 'bybit'
                      AND s.category = %s
                      AND s.ts <= to_timestamp(%s / 1000.0)
                    ORDER BY s.symbol, s.ts DESC
                ),
                {latest_ticker_cte}
                SELECT
                    latest.symbol,
                    latest.ts,
                    latest.status,
                    latest.base_coin,
                    latest.quote_coin,
                    latest.contract_type,
                    latest.tick_size,
                    latest.qty_step,
                    latest.min_notional,
                    latest.listed_at,
                    latest.delisted_at,
                    latest.is_delisted_at_asof,
                    latest.source_uri,
                    latest_ticker.turnover_24h
                FROM latest
                LEFT JOIN latest_ticker ON latest_ticker.symbol = latest.symbol
                WHERE NOT (
                    latest.is_delisted_at_asof
                    AND COALESCE(latest.delisted_at, latest.ts) < to_timestamp(%s / 1000.0)
                )
                ORDER BY
                    CASE WHEN latest_ticker.turnover_24h IS NULL THEN 1 ELSE 0 END,
                    latest_ticker.turnover_24h DESC NULLS LAST,
                    CASE latest.symbol WHEN 'BTCUSDT' THEN 0 WHEN 'ETHUSDT' THEN 1 ELSE 2 END,
                    latest.is_delisted_at_asof ASC,
                    latest.symbol ASC
                LIMIT %s;
                """,
                (
                    category,
                    end_ms,
                    end_ms,
                    start_ms,
                    category,
                    end_ms,
                    *([end_ms] if has_market_tickers else []),
                    start_ms,
                    max_symbols,
                ),
            )
            rows = cursor_fetchall(cur)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "source": "v058_symbol_universe_snapshots",
            "reason": type(exc).__name__,
            "message": str(exc),
            "symbols": [],
        }

    symbols: list[str] = []
    entries: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row[0]).strip().upper()
        if not symbol:
            continue
        symbols.append(symbol)
        entries.append({
            "symbol": symbol,
            "asof_ts": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "status": row[2],
            "base_coin": row[3],
            "quote_coin": row[4],
            "contract_type": row[5],
            "tick_size": float(row[6]) if row[6] is not None else None,
            "qty_step": float(row[7]) if row[7] is not None else None,
            "min_notional": float(row[8]) if row[8] is not None else None,
            "listed_at": row[9].isoformat() if hasattr(row[9], "isoformat") else row[9],
            "delisted_at": row[10].isoformat() if hasattr(row[10], "isoformat") else row[10],
            "is_delisted_at_asof": bool(row[11]),
            "source_uri": row[12],
            "turnover_24h": float(row[13]) if row[13] is not None else None,
        })
    if not symbols:
        return {
            "status": "empty",
            "source": "v058_symbol_universe_snapshots",
            "reason": "no_rows_for_window",
            "symbols": [],
            "window": {"start_ms": start_ms, "end_ms": end_ms},
        }
    warnings: list[str] = []
    if len(rows) >= max_symbols:
        warnings.append(f"historical_universe_truncated_to_{max_symbols}")
    return {
        "status": "ok",
        "source": "v058_symbol_universe_snapshots",
        "symbols": symbols,
        "symbol_count": len(symbols),
        "entries": entries,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "data_window_start": iso_from_ms(start_ms),
        "data_window_end": iso_from_ms(end_ms),
        "warnings": warnings,
    }


def normalise_edge_payload(payload: Any) -> Optional[dict[str, Any]]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    cell = dict(payload)
    if "runtime_bps" not in cell and "shrunk_bps" not in cell:
        for key in (
            "runtime_edge_bps",
            "shrunk_edge_bps",
            "mean_net_bps",
            "edge_bps",
            "net_bps",
        ):
            if key in cell:
                cell["shrunk_bps"] = cell[key]
                break
    if "runtime_bps" not in cell and "shrunk_bps" not in cell:
        return None
    for key in ("runtime_bps", "shrunk_bps", "win_rate", "win_rate_shrunk", "std_bps"):
        if key in cell and cell[key] is not None:
            try:
                cell[key] = float(cell[key])
            except (TypeError, ValueError):
                return None
    if "n" not in cell:
        for key in ("n_trades", "sample_size", "count"):
            if key in cell:
                cell["n"] = cell[key]
                break
    if "n" in cell and cell["n"] is not None:
        try:
            cell["n"] = int(cell["n"])
        except (TypeError, ValueError):
            cell["n"] = 0
    return json_safe_payload(cell)


def json_safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): json_safe_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe_payload(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        return None
    return parsed


def fetch_edge_estimate_snapshot_sync(
    *,
    get_pg_conn_fn: Callable[..., Any],
    statement_timeout_ms: int,
    symbols: list[str],
    strategies: list[str],
    cutoff_ms: int,
) -> dict[str, Any]:
    """Read V059 historical edge snapshots as replay runner JSON cells."""
    if not symbols or not strategies:
        return {
            "status": "empty",
            "source": "v059_edge_estimate_snapshots",
            "reason": "empty_symbols_or_strategies",
            "edge_estimates": {},
        }
    try:
        with get_pg_conn_fn() as conn:
            if conn is None:
                return {
                    "status": "unavailable",
                    "source": "v059_edge_estimate_snapshots",
                    "reason": "pg_unavailable",
                    "edge_estimates": {},
                }
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s;", (statement_timeout_ms,))
            cur.execute(
                """
                SELECT DISTINCT ON (strategy, symbol)
                    strategy,
                    symbol,
                    asof_ts,
                    source_tier,
                    estimate_payload_jsonb,
                    regime_key,
                    cell_key
                FROM learning.edge_estimate_snapshots
                WHERE symbol = ANY(%s)
                  AND strategy = ANY(%s)
                  AND asof_ts <= to_timestamp(%s / 1000.0)
                  AND is_deprecated_at_asof = false
                ORDER BY
                    strategy,
                    symbol,
                    asof_ts DESC,
                    (regime_key = 'global') DESC,
                    (cell_key = 'default') DESC;
                """,
                (symbols, strategies, cutoff_ms),
            )
            rows = cursor_fetchall(cur)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "source": "v059_edge_estimate_snapshots",
            "reason": type(exc).__name__,
            "message": str(exc),
            "edge_estimates": {},
        }

    edge_estimates: dict[str, Any] = {}
    cells: list[dict[str, Any]] = []
    for row in rows:
        strategy = str(row[0])
        symbol = str(row[1]).upper()
        cell = normalise_edge_payload(row[4])
        if cell is None:
            continue
        key = f"{strategy}::{symbol}"
        edge_estimates[key] = cell
        cells.append({
            "key": key,
            "asof_ts": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
            "source_tier": row[3],
            "regime_key": row[5],
            "cell_key": row[6],
        })
    return {
        "status": "ok" if edge_estimates else "empty",
        "source": "v059_edge_estimate_snapshots",
        "cutoff_ms": cutoff_ms,
        "cutoff_iso": iso_from_ms(cutoff_ms),
        "cell_count": len(edge_estimates),
        "cells": cells,
        "edge_estimates": edge_estimates,
        "reason": None if edge_estimates else "no_cells_for_symbols_strategies_cutoff",
    }


def build_manifest_jsonb(
    *,
    body: Any,
    strategy: str,
    fixture_path: Any,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    scanner_snapshot: dict[str, Any],
    universe_source: str,
    historical_universe: dict[str, Any],
    edge_snapshot: dict[str, Any],
    microstructure_overlay: dict[str, Any],
    input_fidelity: dict[str, Any],
    execution_calibration: dict[str, Any],
    strategy_params: Optional[dict[str, Any]] = None,
    risk_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """組 V049 replay.experiments.manifest_jsonb 結構。

    P0 Replay Tier A T3 + T4（2026-05-11）echo 3 個 production 配置：
    - scanner_config：production scanner_config.toml 整檔（max_symbols / pinned 25 sym
      / anti_churn / market_judgment / opportunity）→ Rust replay_runner 透過
      config.rs:7-31 deserialise 為 ScannerConfig 使用，不再退到 default 2-sym
    - strategy_params：caller 經 IPC 抓的當前 production strategy params blob
      （per-strategy active / cooldown / threshold / maker entry 等）
    - risk_overrides：caller 經 IPC 抓的當前 risk_config blob（limits / per_strategy
      override / agent / cascade / regime）

    這 3 個 key 一起進 manifest_jsonb top-level，V049 register handler 計算
    `sha256(manifest_jsonb)==manifest_hash` 自動 cover；M-4 _no_reserved_prefix_keys
    validator 不報拒（無 "_" 前綴）。
    """
    manifest: dict[str, Any] = {
        "manifest_version": 2,
        "mode": "full_chain",
        "execution_scope": "historical_scanner_timeline_to_strategy_risk_exit",
        "source": "s2_bybit_public_full_chain",
        "fixture_uri": str(fixture_path),
        "symbol": _FULL_CHAIN_SYMBOL_SENTINEL,
        "symbols": symbols,
        "strategy": strategy,
        "timeframe": body.timeframe,
        "data_tier": "S2",
        "engine": body.engine,
        "category": body.category,
        "starting_balance": body.starting_balance,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "universe_preset": body.universe_preset,
        "universe_source": universe_source,
        "historical_universe": historical_universe,
        "scanner_snapshot_hash": canonical_sha256(scanner_snapshot),
        "edge_snapshot_meta": {
            key: value
            for key, value in edge_snapshot.items()
            if key != "edge_estimates"
        },
        "edge_estimates": edge_snapshot.get("edge_estimates") or {},
        "microstructure_overlay": microstructure_overlay,
        "input_fidelity": input_fidelity,
        "execution_calibration": execution_calibration,
        "replay_tier": "s2_public_replay",
        "promotion_allowed": False,
        "promotion_block_reason": "current_config_in_sample_sandbox",
    }

    # T3：scanner_config production TOML echo
    # 讀 settings/risk_control_rules/scanner_config.toml，含 pinned 25 sym
    # + anti-churn 30 cycle + market_judgment per-strategy gate + opportunity
    # canary_block_new_entries 等。失敗回 None → replay 退化用 Rust default。
    scanner_config = load_production_scanner_config()
    if scanner_config is not None:
        manifest["scanner_config"] = scanner_config

    # T4：strategy_params + risk_overrides echo
    # caller 已從 IPC 抓 production runtime 配置（_fetch_full_chain_strategy_params
    # / _fetch_current_risk_config），這裡直接 echo 進 manifest top-level。
    # V049 既有 _replay_strategy_params / _replay_risk_overrides reserved blob
    # 路徑由 register handler 在 server-side 注入；T4 加 top-level 是顯式版本，
    # 讓 manifest_jsonb 自我充分（V049 SELECT manifest_jsonb 直接看到生產配置）。
    if strategy_params is not None:
        manifest["strategy_params"] = strategy_params
    if risk_overrides is not None:
        manifest["risk_overrides"] = risk_overrides

    return manifest
