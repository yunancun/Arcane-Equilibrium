"""Rust scanner read helpers for API and agent surfaces.

MODULE_NOTE (English):
  The authoritative market scanner lives in Rust. This module keeps Python
  control-plane consumers on that source by reading IPC `get_scanner_status`,
  then optionally enriching top candidates from the latest persisted scanner
  snapshot so per-strategy judgments remain visible without changing the Rust
  hot path.

MODULE_NOTE (中文):
  權威 scanner 在 Rust。此模組讓 Python 控制面消費同一來源：先讀 IPC
  `get_scanner_status`，再盡力從最新 scanner snapshot 補齊 per-strategy
  judgments。這只改善 API / Agent / 學習面的可見性，不改 Rust hot path。
"""

from __future__ import annotations

import asyncio
import json
import logging
from copy import deepcopy
from typing import Any

from .secret_runtime import get_secret_value

logger = logging.getLogger(__name__)

SCANNER_CONTEXT_FIELDS: tuple[str, ...] = (
    "scan_id",
    "symbol",
    "best_strategy",
    "intent_strategy",
    "market_regime",
    "trend_phase",
    "trend_score",
    "range_score",
    "shock_score",
    "close_alignment",
    "range_position",
    "crowding_score",
    "reversal_risk_score",
    "directional_efficiency",
    "de",
    "dir_pct",
    "signed_dir_pct",
    "range_pct",
    "fr_bps",
    "edge_bps",
    "edge_bonus",
    "edge_n",
    "edge_status",
    "route_mode",
    "market_status",
    "route_reason",
    "final_score",
    "raw_score",
    "sector",
)

FITNESS_FIELDS: tuple[str, ...] = (
    "f_ma",
    "f_grid",
    "f_bbrv",
    "f_bkout",
    "f_funding_arb",
)

BREAKOUT_PROXY_FIELDS: tuple[str, ...] = (
    "f_bkout",
    "trend_phase",
    "trend_score",
    "range_score",
    "shock_score",
    "close_alignment",
    "range_position",
    "crowding_score",
    "reversal_risk_score",
)


async def fetch_scanner_status(*, timeout: float = 3.0) -> dict[str, Any]:
    """Fetch authoritative Rust scanner status through IPC.

    透過 IPC 讀取 Rust scanner 權威狀態。
    """
    from .ipc_client import EngineIPCClient  # noqa: PLC0415

    client = EngineIPCClient()
    try:
        await client.connect()
        result = await client.call("get_scanner_status", params={}, timeout=timeout)
        return result if isinstance(result, dict) else {"status": "invalid_response"}
    finally:
        await client.disconnect()


def fetch_rust_scanner_opportunities_sync(
    *,
    limit: int | None = 10,
    timeout: float = 3.0,
) -> list[dict[str, Any]]:
    """Synchronous wrapper for ScoutWorker threads.

    If called from an already-running event loop we fail soft to avoid blocking
    the loop with a nested run. API handlers should call `fetch_scanner_status`
    directly.

    ScoutWorker thread 使用的同步包裝。若已在 event loop 內則 fail-soft，
    避免 nested run 阻塞；API handler 應直接 await `fetch_scanner_status`。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        try:
            status = asyncio.run(fetch_scanner_status(timeout=timeout))
        except Exception as exc:  # noqa: BLE001 - agent intel must fail soft
            logger.debug("Rust scanner IPC unavailable for ScoutWorker: %s", exc)
            return []
        status = enrich_scanner_status_with_db(status)
        return normalize_scanner_opportunities(status, limit=limit)

    logger.debug("Rust scanner sync fetch skipped inside running event loop")
    return []


def enrich_scanner_status_with_db(status: dict[str, Any]) -> dict[str, Any]:
    """Merge latest DB snapshot candidate details into IPC top candidates.

    IPC intentionally keeps the scanner response compact. The DB snapshot
    carries the full `ScoredSymbol`, including `strategy_judgments`, so this
    enrichment exposes strategy-specific scanner reasoning to GUI/Agent/ML
    surfaces without a Rust rebuild.

    將最新 DB scanner snapshot 的候選細節合併到 IPC top candidates。IPC
    保持輕量，DB snapshot 保留完整 `ScoredSymbol`，因此可在不 rebuild Rust
    的情況下把 per-strategy 判斷暴露給 GUI / Agent / ML 讀面。
    """
    if not isinstance(status, dict):
        return status
    last_scan = status.get("last_scan")
    if not isinstance(last_scan, dict):
        return status
    candidates = last_scan.get("top_candidates")
    if not isinstance(candidates, list) or not candidates:
        return status

    snapshot_by_symbol = fetch_latest_scanner_snapshot_candidate_map()
    if not snapshot_by_symbol:
        return status

    enriched = deepcopy(status)
    enriched_last_scan = enriched.get("last_scan")
    if not isinstance(enriched_last_scan, dict):
        return status

    merged_candidates: list[Any] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            merged_candidates.append(candidate)
            continue
        symbol = str(candidate.get("symbol") or "")
        snapshot_candidate = snapshot_by_symbol.get(symbol)
        if isinstance(snapshot_candidate, dict):
            merged = dict(snapshot_candidate)
            merged.update(candidate)
            merged_candidates.append(merged)
        else:
            merged_candidates.append(candidate)
    enriched_last_scan["top_candidates"] = merged_candidates
    enriched_last_scan["candidate_detail_source"] = "ipc_plus_latest_scanner_snapshot"
    return enriched


def fetch_latest_scanner_snapshot_candidate_map() -> dict[str, dict[str, Any]]:
    """Return latest persisted scanner candidates keyed by symbol, fail-soft.

    讀取最近一次持久化 scanner candidates 並按 symbol 建索引；失敗時返回空表。
    """
    dsn = (
        get_secret_value("OPENCLAW_DATABASE_URL")
        or get_secret_value("DATABASE_URL")
    )
    if not dsn:
        return {}
    try:
        import psycopg2  # type: ignore  # noqa: PLC0415
    except ImportError:
        return {}

    try:
        with psycopg2.connect(dsn, connect_timeout=1) as conn:  # pragma: no cover - DB path
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT candidates
                    FROM trading.scanner_snapshots
                    ORDER BY ts DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - optional enrichment only
        logger.debug("scanner snapshot enrichment unavailable: %s", exc)
        return {}

    if not row:
        return {}
    candidates = _coerce_candidates(row[0])
    out: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        symbol = candidate.get("symbol")
        if symbol:
            out[str(symbol)] = candidate
    return out


def normalize_scanner_opportunities(
    status: dict[str, Any],
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Normalize Rust scanner candidates to GUI/Agent-compatible rows.

    將 Rust scanner candidate 正規化成 GUI / Agent 可直接消費的資料列。
    """
    last_scan = status.get("last_scan") if isinstance(status, dict) else None
    if not isinstance(last_scan, dict):
        return []
    candidates = last_scan.get("top_candidates") or []
    if not isinstance(candidates, list):
        return []

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        rows.append(normalize_scanner_candidate(candidate))
        if limit is not None and len(rows) >= limit:
            break
    return rows


def normalize_scanner_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Normalize one Rust scanner candidate while preserving old GUI fields.

    正規化單個 Rust scanner candidate，同時保留舊 GUI 欄位。
    """
    scanner_context = _pick_fields(candidate, SCANNER_CONTEXT_FIELDS)
    fitness = _pick_fields(candidate, FITNESS_FIELDS)
    breakout_inputs = _pick_fields(candidate, BREAKOUT_PROXY_FIELDS)
    strategy_judgments = candidate.get("strategy_judgments")
    if not isinstance(strategy_judgments, dict):
        strategy_judgments = {}
    opportunity = _candidate_opportunity(candidate, strategy_judgments)

    return {
        "symbol": candidate.get("symbol"),
        "strategy_type": candidate.get("best_strategy"),
        "score": candidate.get("final_score"),
        "reason": _candidate_reason(candidate),
        "scanner_context": scanner_context,
        "opportunity": opportunity,
        "strategy_judgments": strategy_judgments,
        "fitness": fitness,
        "breakout_proxy": {
            "source": "scanner_market_structure_proxy",
            "strategy": "bb_breakout",
            "inputs": breakout_inputs,
            "note": (
                "audit_only_no_new_gate: f_bkout is shaped from scanner "
                "trend/range/close/crowding context; true BB bandwidth remains "
                "the strategy/indicator domain"
            ),
        },
    }


def _candidate_opportunity(
    candidate: dict[str, Any],
    strategy_judgments: dict[str, Any],
) -> dict[str, Any]:
    """Return best-route scanner opportunity if present.

    回傳 best-route scanner opportunity；缺失時返回空 dict。Rust v1 把
    opportunity 掛在每個 strategy_judgment 上，這裡只做讀面正規化，不重算。
    """
    direct = candidate.get("opportunity")
    if isinstance(direct, dict):
        return direct
    for best_strategy in _strategy_key_aliases(str(candidate.get("best_strategy") or "")):
        judgment = strategy_judgments.get(best_strategy)
        if isinstance(judgment, dict):
            opportunity = judgment.get("opportunity")
            if isinstance(opportunity, dict):
                return opportunity
    return {}


def _strategy_key_aliases(raw: str) -> tuple[str, ...]:
    aliases = {
        "MaCrossover": "ma_crossover",
        "GridTrading": "grid_trading",
        "BbReversion": "bb_reversion",
        "BbBreakout": "bb_breakout",
        "FundingArb": "funding_arb",
    }
    mapped = aliases.get(raw)
    return (raw, mapped) if mapped and mapped != raw else (raw,)


def _candidate_reason(candidate: dict[str, Any]) -> str:
    """Build a compact candidate reason string for legacy GUI cells.

    為舊 GUI 儲存格組合精簡 candidate reason 字串。
    """
    sector = candidate.get("sector") or ""
    edge_bonus = candidate.get("edge_bonus")
    edge_n = candidate.get("edge_n")
    parts: list[str] = []
    if sector:
        parts.append(str(sector))
    if edge_bonus is not None and edge_n:
        try:
            parts.append(f"edge={float(edge_bonus):+.2f} (n={int(edge_n)})")
        except (TypeError, ValueError):
            pass
    return " · ".join(parts) if parts else "--"


def _pick_fields(source: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Copy non-null fields from a source dict.

    從來源 dict 複製非空欄位。
    """
    return {
        field: source[field]
        for field in fields
        if field in source and source[field] is not None
    }


def _coerce_candidates(raw: Any) -> list[Any]:
    """Coerce DB JSON payloads into a candidate list.

    將 DB JSON payload 轉成 candidate list；格式不符時返回空列。
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []
