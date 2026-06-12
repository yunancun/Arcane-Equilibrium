"""Closed-PnL 游標分頁 / 視窗推進 / 行正規化 / PG 備援讀模型。

MODULE_NOTE
模塊用途：從 strategy_ai_routes 抽出的 Demo closed-PnL 讀模型純邏輯 —
    游標編解碼、7 天視窗推進、Bybit 分頁抓取、trading.fills PG 備援、
    策略歸屬豐富化、cursor-mode 預載 payload 組裝。route handler 只做
    parse → call → format，本模塊承載全部分頁/視窗/正規化邏輯。
主要函數：
    _closed_pnl_encode_cursor / _closed_pnl_decode_cursor — 游標 base64 JSON 編解碼
    _closed_pnl_history_bounds — start/end 毫秒邊界推導
    _closed_pnl_bybit_state_with_cursor / _closed_pnl_previous_window_state — 視窗狀態機
    _fetch_closed_pnl_bybit_history_page — 跨視窗 Bybit 分頁抓取（rc 由呼叫端注入）
    _fetch_strategy_by_order_id / _attach_closed_pnl_strategy — PG join 策略歸屬
    _fetch_pg_closed_pnl_fallback — Bybit 不可用時的 trading.fills 只讀備援
    _closed_pnl_history_cursor_payload — cursor-mode 全歷史預載編排
依賴：fastapi.HTTPException、app.db_pool（懶加載）、asyncio。
硬邊界：
    - 所有 PG 查詢參數化（%s）、設 SET LOCAL statement_timeout，GUI 讀路徑不得阻塞事件迴圈。
    - 不直接呼叫 _get_rust_client / _engine_owner_strategy_map（route 層 monkeypatch 縫）：
      rc 與 engine_owner_lookup 由呼叫端注入，failure-state record/clear 亦由呼叫端注入，
      以保持 strategy_ai_routes 命名空間的測試 monkeypatch 語意不變。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import time
from typing import Any, Callable

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ── Closed-PnL 讀模型常量（與 strategy_ai_routes 原值一致）──
# 對齊 Rust 真實 order_link_id 鑄造前綴 grammar（已 grep 核對非文檔假設）：
#   開倉  step_4_5_dispatch.rs:662      oc_{em}_{ts}_{seq}
#   風控平 commands.rs:931+988         oc_risk_{em}_{ts}_{seq}（影子軌為 sh_risk_，不入此讀模型）
#   maker fallback 平 commands.rs:1112 oc_close_mf_fb_{em}_{ts}_{seq}
#   IPC 平 commands.rs:1350/1547       oc_ipc_close_{em}_{ts}_{seq}
# em = order_link_mode_tag()（pipeline_ctor.rs:317）∈ {dm=demo, ld=live_demo, lv=live, xx=paper-defensive}。
# 為何中綴 alternation 把 ipc_close_ / close_mf_fb_ 排在泛 close_[a-z0-9_]+_ 前：
#   泛規則會先吃掉 oc_ipc_close_ 的 "ipc_close_"（"ipc" 命中 [a-z0-9_]+）導致 em 錯位，
#   故更具體前綴必先匹配。lv 不入 owner-map 時與 dm/ld 一致 fall-through 至 unknown，
#   非 oc_ 或 em∉{dm,ld,lv}（含 xx）則整體不 match → external/unknown，與舊行為相容。
_OPENCLAW_LINK_RE = re.compile(
    r"^oc_(?:risk_|ipc_close_|close_mf_fb_|close_[a-z0-9_]+_)?(?P<engine>dm|ld|lv)(?:_|$)",
    re.I,
)
# orderLinkId em 兩字元標籤 → engine 名映射（module-level const，避免每次呼叫重建）。
# lv（live mainnet）必須映射為 "live"，不可誤判為 demo（會污染 live 訂單歸屬）。
_ENGINE_BY_TAG = {"dm": "demo", "ld": "live_demo", "lv": "live"}
_CLOSED_PNL_DAY_MS = 24 * 60 * 60 * 1000
_CLOSED_PNL_MAX_WINDOW_MS = 7 * 24 * 60 * 60 * 1000
_CLOSED_PNL_ALL_HISTORY_DAYS = 730
_CLOSED_PNL_MAX_WINDOWS_PER_PRELOAD = 8
_CLOSED_PNL_CURSOR_VERSION = 1
_GUI_READ_STATEMENT_TIMEOUT_MS = int(os.getenv("OPENCLAW_GUI_READ_STATEMENT_TIMEOUT_MS", "1500"))
_CLOSED_PNL_STRATEGY_TIME_MATCH_MS = int(
    os.getenv("OPENCLAW_CLOSED_PNL_STRATEGY_TIME_MATCH_MS", "600000")
)

# engine_owner_lookup 注入型別：engine 名 → {symbol: owner_strategy}
EngineOwnerLookup = Callable[[str], dict[str, str]]


def _safe_float(value: Any) -> float | None:
    """Best-effort float conversion. Returns None on any failure.
    Bybit REST positions return stringified numbers; this normalizes them.
    Best-effort 轉 float；失敗返回 None。Bybit REST 倉位數值常為字串。
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN guard / NaN 守衛
        return None
    return f


def _closed_pnl_encode_cursor(payload: dict[str, Any]) -> str:
    data = dict(payload)
    data["v"] = _CLOSED_PNL_CURSOR_VERSION
    raw = json.dumps(data, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _closed_pnl_decode_cursor(cursor: str | None) -> dict[str, Any]:
    if not cursor:
        return {}
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid closed-pnl cursor") from exc
    if not isinstance(data, dict) or data.get("v") != _CLOSED_PNL_CURSOR_VERSION:
        raise HTTPException(status_code=400, detail="invalid closed-pnl cursor")
    return data


def _closed_pnl_optional_ms(value: Any) -> int | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _closed_pnl_history_bounds(
    *,
    start_time: Any,
    end_time: Any,
    lookback_days: int,
) -> tuple[int, int]:
    now_ms = int(time.time() * 1000)
    end_ms = _closed_pnl_optional_ms(end_time)
    if end_ms is None:
        end_ms = (now_ms // 5000) * 5000
    start_ms = _closed_pnl_optional_ms(start_time)
    if start_ms is None:
        try:
            requested_days = int(lookback_days)
        except Exception:
            requested_days = _CLOSED_PNL_ALL_HISTORY_DAYS
        safe_days = min(max(requested_days, 1), _CLOSED_PNL_ALL_HISTORY_DAYS)
        start_ms = end_ms - safe_days * _CLOSED_PNL_DAY_MS
    if end_ms < start_ms:
        raise HTTPException(status_code=400, detail="end_time must be >= start_time")
    return start_ms, end_ms


def _closed_pnl_initial_bybit_state(
    *,
    start_ms: int,
    end_ms: int,
    symbol: str | None,
) -> dict[str, Any]:
    window_start_ms = max(start_ms, end_ms - _CLOSED_PNL_MAX_WINDOW_MS)
    return {
        "source": "bybit",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "window_start_ms": window_start_ms,
        "window_end_ms": end_ms,
        "cursor": None,
        "symbol": symbol,
    }


def _closed_pnl_previous_window_state(state: dict[str, Any]) -> dict[str, Any] | None:
    start_ms = int(state.get("start_ms") or 0)
    window_start_ms = int(state.get("window_start_ms") or 0)
    prev_end_ms = window_start_ms - 1
    if prev_end_ms < start_ms:
        return None
    return {
        "source": "bybit",
        "start_ms": start_ms,
        "end_ms": int(state.get("end_ms") or prev_end_ms),
        "window_start_ms": max(start_ms, prev_end_ms - _CLOSED_PNL_MAX_WINDOW_MS),
        "window_end_ms": prev_end_ms,
        "cursor": None,
        "symbol": state.get("symbol"),
    }


def _closed_pnl_bybit_state_with_cursor(
    *,
    cursor: str | None,
    start_ms: int,
    end_ms: int,
    symbol: str | None,
) -> dict[str, Any]:
    decoded = _closed_pnl_decode_cursor(cursor)
    if decoded.get("source") != "bybit":
        return _closed_pnl_initial_bybit_state(start_ms=start_ms, end_ms=end_ms, symbol=symbol)
    return {
        "source": "bybit",
        "start_ms": int(decoded.get("start_ms") or start_ms),
        "end_ms": int(decoded.get("end_ms") or end_ms),
        "window_start_ms": int(decoded.get("window_start_ms") or start_ms),
        "window_end_ms": int(decoded.get("window_end_ms") or end_ms),
        "cursor": decoded.get("cursor") or None,
        "symbol": decoded.get("symbol") or symbol,
    }


def _fetch_closed_pnl_bybit_history_page(
    rc: Any,
    *,
    limit: int,
    cursor: str | None,
    symbol: str | None,
    start_ms: int,
    end_ms: int,
) -> tuple[list[dict[str, Any]], str | None]:
    rows: list[dict[str, Any]] = []
    state = _closed_pnl_bybit_state_with_cursor(
        cursor=cursor,
        start_ms=start_ms,
        end_ms=end_ms,
        symbol=symbol,
    )
    next_state: dict[str, Any] | None = None
    seen_cursors: set[str] = {str(state["cursor"])} if state.get("cursor") else set()
    calls = 0
    while state and len(rows) < limit and calls < _CLOSED_PNL_MAX_WINDOWS_PER_PRELOAD:
        calls += 1
        page_limit = min(100, max(1, limit - len(rows)))
        bybit_cursor = state.get("cursor") or None
        result = rc.get_closed_pnl(
            "linear",
            symbol=symbol,
            start_time=int(state["window_start_ms"]),
            end_time=int(state["window_end_ms"]),
            limit=page_limit,
            cursor=bybit_cursor,
        )
        items = result.get("list") if isinstance(result, dict) else result
        if isinstance(items, list):
            rows.extend([dict(row) for row in items if isinstance(row, dict)])
        next_bybit_cursor = (
            result.get("nextPageCursor")
            if isinstance(result, dict)
            else None
        )
        if next_bybit_cursor:
            if next_bybit_cursor in seen_cursors:
                logger.warning("Bybit closed-pnl returned repeated cursor; stopping pagination")
                next_state = None
                break
            seen_cursors.add(str(next_bybit_cursor))
            next_state = {**state, "cursor": str(next_bybit_cursor)}
            if len(rows) >= limit:
                break
            state = next_state
            continue
        previous = _closed_pnl_previous_window_state(state)
        if len(rows) >= limit:
            next_state = previous
            break
        state = previous
        next_state = state
    if len(rows) < limit and state is not None and calls >= _CLOSED_PNL_MAX_WINDOWS_PER_PRELOAD:
        next_state = state
    next_cursor = _closed_pnl_encode_cursor(next_state) if next_state else None
    return rows[:limit], next_cursor


def _closed_pnl_pg_cursor(
    *,
    offset: int,
    symbol: str | None,
    start_ms: int,
    end_ms: int,
    engine_modes: tuple[str, ...],
) -> str:
    return _closed_pnl_encode_cursor({
        "source": "pg",
        "offset": offset,
        "symbol": symbol,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "engine_modes": list(engine_modes),
    })


def _strategy_from_order_link_id(
    order_link_id: Any,
    *,
    symbol: str,
    engine_owner_lookup: EngineOwnerLookup,
) -> tuple[str, str]:
    """Infer strategy_name/source from Bybit orderLinkId when PG join misses.

    engine_owner_lookup 為注入縫：對應 strategy_ai_routes._engine_owner_strategy_map，
    以保留 route 層測試 monkeypatch 語意（本模塊不直接引用該全域名）。
    """
    link = str(order_link_id or "").strip()
    match = _OPENCLAW_LINK_RE.match(link)
    if not link or not match:
        return "external_manual", "bybit_unknown"
    # em 兩字元標籤 → engine 名顯式映射（_ENGINE_BY_TAG，module-level）。未知 em
    # 不會發生（正則已限定 dm|ld|lv），保險起見以 "demo" 兜底維持舊行為。
    engine = _ENGINE_BY_TAG.get(match.group("engine").lower(), "demo")
    owner = engine_owner_lookup(engine).get(symbol)
    if owner:
        return owner, "pg_link_id"
    return "unknown_pending", "pg_missing_unknown_external"


def _closed_pnl_time_ms(row: dict[str, Any]) -> int:
    for key in ("updatedTime", "updated_time_ms", "createdTime", "created_time_ms"):
        value = _safe_float(row.get(key))
        if value is not None and value > 0:
            return int(value)
    return 0


def _time_fallback_allowed(order_link_id: Any) -> bool:
    """僅在 link id 缺失或呈 OpenClaw 形狀時允許 PG 時間窗口歸因。

    非空且非 OpenClaw 的 link 保持 external/manual，避免只因同 symbol 附近
    有一筆引擎 close fill，就把真正 operator / 交易所側成交誤標為策略成交。
    """
    link = str(order_link_id or "").strip()
    return not link or bool(_OPENCLAW_LINK_RE.match(link))


def _fetch_strategy_by_order_id(
    order_ids: list[str],
    *,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
) -> dict[str, dict[str, Any]]:
    """Read-only PG join: Bybit orderId/link id → latest local fill attribution."""
    ids = sorted({oid for oid in order_ids if oid})
    if not ids:
        return {}
    safe_modes = tuple(engine_modes or ("demo", "live_demo"))
    mode_placeholders = ", ".join(["%s"] * len(safe_modes))
    try:
        from . import db_pool  # noqa: PLC0415
        conn = db_pool.get_conn()
    except Exception:
        return {}
    if conn is None:
        return {}
    try:
        cur = conn.cursor()
        # 為什麼設語句逾時：GUI 讀路徑不得被慢查詢阻塞事件迴圈線程池。
        cur.execute("SET LOCAL statement_timeout = %s", (_GUI_READ_STATEMENT_TIMEOUT_MS,))
        cur.execute(
            "SELECT DISTINCT ON (order_id) order_id, strategy_name, realized_pnl "
            "FROM trading.fills "
            f"WHERE order_id = ANY(%s) AND engine_mode IN ({mode_placeholders}) "
            "ORDER BY order_id, ts DESC",
            (ids, *safe_modes),
        )
        rows = cur.fetchall()
        return {
            str(order_id): {
                "strategy_name": str(strategy_name) if strategy_name else "",
                "realized_pnl": _safe_float(realized_pnl),
            }
            for order_id, strategy_name, realized_pnl in rows
            if order_id
        }
    except Exception as exc:
        logger.warning("closed-pnl PG strategy join failed: %s", exc)
        return {}
    finally:
        try:
            db_pool.put_conn(conn)
        except Exception:
            pass


def _fetch_strategy_by_symbol_time(
    indexed_rows: list[tuple[int, dict[str, Any]]],
    *,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
) -> dict[int, dict[str, Any]]:
    """Bybit 缺 orderLinkId 時，用 symbol + close time 做只讀 fallback 歸因。

    精確 order-id/link-id join 仍是首選。這條窄 fallback 只處理 Bybit
    closed-PnL 行 ``orderLinkId`` 為空、但本地引擎已在 ``trading.fills``
    寫入帶 strategy_name close fill 的情況。
    """
    targets: list[tuple[int, str, int, float | None]] = []
    for idx, row in indexed_rows:
        if not isinstance(row, dict) or not _time_fallback_allowed(row.get("orderLinkId")):
            continue
        sym = str(row.get("symbol") or "").strip()
        ts_ms = _closed_pnl_time_ms(row)
        if not sym or ts_ms <= 0:
            continue
        targets.append((idx, sym, ts_ms, _safe_float(row.get("closedPnl"))))
    if not targets:
        return {}

    safe_modes = tuple(engine_modes or ("demo", "live_demo"))
    mode_placeholders = ", ".join(["%s"] * len(safe_modes))
    symbols = sorted({sym for _, sym, _, _ in targets})
    min_ms = min(ts_ms for _, _, ts_ms, _ in targets) - _CLOSED_PNL_STRATEGY_TIME_MATCH_MS
    max_ms = max(ts_ms for _, _, ts_ms, _ in targets) + _CLOSED_PNL_STRATEGY_TIME_MATCH_MS
    # 限制候選掃描量：GUI 顯示歸因不可退化成寬歷史查詢。
    candidate_limit = min(max(len(targets) * 12, 100), 1000)
    try:
        from . import db_pool  # noqa: PLC0415
        conn = db_pool.get_conn()
    except Exception:
        return {}
    if conn is None:
        return {}
    try:
        cur = conn.cursor()
        cur.execute("SET LOCAL statement_timeout = %s", (_GUI_READ_STATEMENT_TIMEOUT_MS,))
        cur.execute(
            "SELECT ts, order_id, symbol, side, qty, realized_pnl, strategy_name "
            "FROM trading.fills "
            f"WHERE engine_mode IN ({mode_placeholders}) "
            "AND symbol = ANY(%s) "
            "AND ts >= to_timestamp(%s / 1000.0) "
            "AND ts <= to_timestamp(%s / 1000.0) "
            "AND COALESCE(realized_pnl, 0) <> 0 "
            "AND strategy_name IS NOT NULL AND strategy_name <> '' "
            "AND strategy_name NOT LIKE 'unattributed:%%' "
            "ORDER BY ts DESC LIMIT %s",
            (*safe_modes, symbols, min_ms, max_ms, candidate_limit),
        )
        rows = cur.fetchall()
    except Exception as exc:
        logger.warning("closed-pnl PG time-window strategy lookup failed: %s", exc)
        return {}
    finally:
        try:
            db_pool.put_conn(conn)
        except Exception:
            pass

    candidates_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for ts, order_id, sym, side, qty, realized_pnl, strategy_name in rows:
        if not sym or not strategy_name:
            continue
        try:
            ts_ms = int(ts.timestamp() * 1000) if ts is not None else 0
        except Exception:
            ts_ms = 0
        if ts_ms <= 0:
            continue
        candidates_by_symbol.setdefault(str(sym), []).append({
            "ts_ms": ts_ms,
            "order_id": str(order_id or ""),
            "side": str(side or ""),
            "qty": _safe_float(qty),
            "realized_pnl": _safe_float(realized_pnl),
            "strategy_name": str(strategy_name),
        })

    matches: dict[int, dict[str, Any]] = {}
    used: set[tuple[str, int, str]] = set()
    for idx, sym, row_ts_ms, bybit_pnl in targets:
        best: tuple[float, int, dict[str, Any]] | None = None
        for cand in candidates_by_symbol.get(sym, []):
            delta = abs(int(cand["ts_ms"]) - row_ts_ms)
            if delta > _CLOSED_PNL_STRATEGY_TIME_MATCH_MS:
                continue
            key = (str(cand.get("order_id") or ""), int(cand["ts_ms"]), cand["strategy_name"])
            if key in used:
                continue
            pg_pnl = cand.get("realized_pnl")
            pnl_penalty = 0.0
            if bybit_pnl is not None and pg_pnl is not None:
                denom = max(abs(float(bybit_pnl)), 1.0)
                pnl_penalty = min(abs(float(pg_pnl) - float(bybit_pnl)) / denom, 10.0)
            score = float(delta) + pnl_penalty * 10_000.0
            if best is None or score < best[0]:
                best = (score, delta, cand)
        if best is None:
            continue
        _, delta, cand = best
        key = (str(cand.get("order_id") or ""), int(cand["ts_ms"]), cand["strategy_name"])
        used.add(key)
        matches[idx] = {
            "strategy_name": cand["strategy_name"],
            "realized_pnl": cand.get("realized_pnl"),
            "match_delta_ms": delta,
        }
    return matches


def _closed_pnl_float(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    return _safe_float(value)


def _closed_pnl_snake_row(row: dict[str, Any]) -> dict[str, Any]:
    """Expose stable snake_case aliases while preserving raw Bybit camelCase."""
    closed_pnl = _closed_pnl_float(row, "closedPnl")
    open_fee = _closed_pnl_float(row, "openFee")
    close_fee = _closed_pnl_float(row, "closeFee")
    fill_count = row.get("fillCount")
    try:
        fill_count_int = int(fill_count) if fill_count is not None and fill_count != "" else 0
    except Exception:
        fill_count_int = 0
    out = dict(row)
    out.update({
        "symbol": row.get("symbol") or "",
        "side": row.get("side") or "",
        "qty": _closed_pnl_float(row, "qty") or 0.0,
        "avg_entry_price": _closed_pnl_float(row, "avgEntryPrice"),
        "avg_exit_price": _closed_pnl_float(row, "avgExitPrice"),
        "closed_pnl": closed_pnl if closed_pnl is not None else 0.0,
        "bybit_closed_pnl": closed_pnl if closed_pnl is not None else 0.0,
        "open_fee": open_fee,
        "close_fee": close_fee,
        "closed_size": _closed_pnl_float(row, "closedSize"),
        "fill_count": fill_count_int,
        "updated_time_ms": int(_closed_pnl_float(row, "updatedTime") or 0),
        "created_time_ms": int(_closed_pnl_float(row, "createdTime") or 0),
        "order_id": row.get("orderId") or "",
        "order_link_id": row.get("orderLinkId") or "",
        "leverage": row.get("leverage") or "",
        "exec_type": row.get("execType") or "",
    })
    return out


def _attach_closed_pnl_strategy(
    rows: list[dict[str, Any]],
    *,
    engine_owner_lookup: EngineOwnerLookup,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
) -> list[dict[str, Any]]:
    """Attach strategy_name, source, PG PnL and drift fields.

    engine_owner_lookup 為注入縫（見 _strategy_from_order_link_id）。
    """
    lookup_ids: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("orderId", "orderLinkId"):
            value = str(row.get(key) or "").strip()
            if value:
                lookup_ids.append(value)
    strategy_by_order_id = _fetch_strategy_by_order_id(lookup_ids, engine_modes=engine_modes)
    time_lookup_rows: list[tuple[int, dict[str, Any]]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        order_id = str(row.get("orderId") or "").strip()
        order_link_id = str(row.get("orderLinkId") or "").strip()
        pg_match = strategy_by_order_id.get(order_id) or strategy_by_order_id.get(order_link_id)
        if not (pg_match and pg_match.get("strategy_name")):
            time_lookup_rows.append((idx, row))
    strategy_by_time = _fetch_strategy_by_symbol_time(
        time_lookup_rows,
        engine_modes=engine_modes,
    )
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        order_id = str(row.get("orderId") or "").strip()
        order_link_id = str(row.get("orderLinkId") or "").strip()
        enriched = _closed_pnl_snake_row(row)
        pg_match = strategy_by_order_id.get(order_id) or strategy_by_order_id.get(order_link_id)
        pg_pnl = pg_match.get("realized_pnl") if pg_match else None
        if pg_match and pg_match.get("strategy_name"):
            enriched["strategy_name"] = pg_match["strategy_name"]
            enriched["strategy_source"] = "pg_fill"
        elif idx in strategy_by_time:
            time_match = strategy_by_time[idx]
            enriched["strategy_name"] = time_match["strategy_name"]
            enriched["strategy_source"] = "pg_time_window"
            enriched["strategy_match_delta_ms"] = time_match.get("match_delta_ms")
            pg_pnl = time_match.get("realized_pnl")
        else:
            strategy_name, strategy_source = _strategy_from_order_link_id(
                row.get("orderLinkId"),
                symbol=str(enriched.get("symbol") or ""),
                engine_owner_lookup=engine_owner_lookup,
            )
            enriched["strategy_name"] = strategy_name
            enriched["strategy_source"] = strategy_source
        bybit_pnl = _safe_float(enriched.get("closed_pnl"))
        enriched["pg_engine_pnl"] = pg_pnl
        if pg_pnl is not None and bybit_pnl is not None:
            diff = abs(float(pg_pnl) - float(bybit_pnl))
            enriched["pnl_source_drift_usd"] = diff
            enriched["pnl_source_drift_pct"] = (
                diff / abs(float(bybit_pnl)) if abs(float(bybit_pnl)) > 0 else None
            )
        else:
            enriched["pnl_source_drift_usd"] = None
            enriched["pnl_source_drift_pct"] = None
        out.append(enriched)
    return out


def _fetch_pg_closed_pnl_fallback(
    *,
    limit: int,
    offset: int,
    symbol: str | None,
    start_ms: int,
    end_ms: int,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
) -> dict[str, Any]:
    """Read-only fallback from trading.fills when Bybit REST is unavailable."""
    safe_modes = tuple(engine_modes or ("demo", "live_demo"))
    mode_placeholders = ", ".join(["%s"] * len(safe_modes))
    try:
        from . import db_pool  # noqa: PLC0415
        conn = db_pool.get_conn()
    except Exception as exc:
        raise RuntimeError("pg_unavailable") from exc
    if conn is None:
        raise RuntimeError("pg_unavailable")
    try:
        where = (
            f"engine_mode IN ({mode_placeholders}) "
            "AND ts >= to_timestamp(%s / 1000.0) "
            "AND ts <= to_timestamp(%s / 1000.0) "
            "AND COALESCE(realized_pnl, 0) <> 0"
        )
        params: list[Any] = [*safe_modes, start_ms, end_ms]
        if symbol:
            where += " AND symbol = %s"
            params.append(symbol)
        params.extend([limit + 1, offset])
        cur = conn.cursor()
        # 為什麼設語句逾時：GUI 讀路徑不得被慢查詢阻塞事件迴圈線程池。
        cur.execute("SET LOCAL statement_timeout = %s", (_GUI_READ_STATEMENT_TIMEOUT_MS,))
        cur.execute(
            "SELECT ts, order_id, symbol, side, qty, price, fee, realized_pnl, strategy_name "
            f"FROM trading.fills WHERE {where} ORDER BY ts DESC LIMIT %s OFFSET %s",
            tuple(params),
        )
        rows = cur.fetchall()
    finally:
        try:
            db_pool.put_conn(conn)
        except Exception:
            pass

    has_more = len(rows) > limit
    out: list[dict[str, Any]] = []
    for ts, order_id, sym, side, qty, price, fee, rpnl, strategy in rows[:limit]:
        ts_ms = int(ts.timestamp() * 1000) if ts is not None else 0
        strategy_name = strategy or "unknown_external"
        row = {
            "symbol": sym or "",
            "side": side or "",
            "qty": str(qty if qty is not None else 0),
            "avgEntryPrice": str(price if price is not None else 0),
            "avgExitPrice": str(price if price is not None else 0),
            "closedPnl": str(rpnl if rpnl is not None else 0),
            "openFee": "",
            "closeFee": str(fee if fee is not None else 0),
            "closedSize": str(qty if qty is not None else 0),
            "fillCount": "1",
            "updatedTime": str(ts_ms),
            "orderId": order_id or "",
            "orderLinkId": "",
            "leverage": "",
            "execType": "pg_fallback",
            "strategy_name": strategy_name,
            "strategy_source": "pg_fill" if strategy else "pg_missing_unknown_external",
            "pg_engine_pnl": float(rpnl) if rpnl is not None else 0.0,
        }
        normalized = _closed_pnl_snake_row(row)
        normalized["strategy_name"] = row["strategy_name"]
        normalized["strategy_source"] = row["strategy_source"]
        normalized["pg_engine_pnl"] = row["pg_engine_pnl"]
        normalized["pnl_source_drift_usd"] = 0.0
        normalized["pnl_source_drift_pct"] = 0.0
        out.append(normalized)
    return {
        "list": out,
        "count": len(out),
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + len(out) if has_more else None,
        "next_cursor": _closed_pnl_pg_cursor(
            offset=offset + len(out),
            symbol=symbol,
            start_ms=start_ms,
            end_ms=end_ms,
            engine_modes=safe_modes,
        ) if has_more else None,
        "source": "pg_fallback",
        "source_ts": int(time.time() * 1000),
        "cache_age": 0.0,
        "cache_age_seconds": 0.0,
        "degraded_reason": (
            "bybit_closed_pnl_unavailable; pg_fallback_estimated_from_trading_fills; "
            "avgEntryPrice/avgExitPrice/closedSize/fillCount are approximate"
        ),
    }


async def _closed_pnl_history_cursor_payload(
    *,
    rc: Any,
    limit: int,
    cursor: str | None,
    symbol: str | None,
    start_time: Any,
    end_time: Any,
    lookback_days: int,
    engine_modes: tuple[str, ...],
    client_unavailable_reason: str,
    engine_owner_lookup: EngineOwnerLookup,
    record_failure: Callable[[], dict[str, Any]],
    clear_failures: Callable[[], None],
) -> dict[str, Any]:
    """Cursor-mode all-history read model for GUI preloading.

    為什麼注入 rc / engine_owner_lookup / record_failure / clear_failures：
    這四者在 strategy_ai_routes 為 route 層 monkeypatch / 全域狀態縫，
    由呼叫端注入以保留既有測試語意，並避免本模塊與 route 模塊循環引用。
    """
    safe_modes = tuple(engine_modes or ("demo", "live_demo"))
    cursor_state = _closed_pnl_decode_cursor(cursor)
    start_ms, end_ms = _closed_pnl_history_bounds(
        start_time=start_time,
        end_time=end_time,
        lookback_days=lookback_days,
    )
    sym = symbol
    if cursor_state:
        start_ms = int(cursor_state.get("start_ms") or start_ms)
        end_ms = int(cursor_state.get("end_ms") or end_ms)
        sym = cursor_state.get("symbol") or sym
    if cursor_state.get("source") == "pg":
        pg_modes = tuple(cursor_state.get("engine_modes") or safe_modes)
        offset = int(cursor_state.get("offset") or 0)
        payload = await asyncio.to_thread(
            _fetch_pg_closed_pnl_fallback,
            limit=limit,
            offset=offset,
            symbol=sym,
            start_ms=start_ms,
            end_ms=end_ms,
            engine_modes=pg_modes,
        )
        payload.update({
            "all_history": True,
            "range_start_ms": start_ms,
            "range_end_ms": end_ms,
            "page_size": 50,
            "preload_limit": limit,
        })
        return payload

    if rc is None:
        try:
            payload = await asyncio.to_thread(
                _fetch_pg_closed_pnl_fallback,
                limit=limit,
                offset=0,
                symbol=sym,
                start_ms=start_ms,
                end_ms=end_ms,
                engine_modes=safe_modes,
            )
            pg_reason = payload.get("degraded_reason") or "pg_fallback"
            pg_reason = pg_reason.removeprefix("bybit_closed_pnl_unavailable; ")
            payload["degraded_reason"] = f"{client_unavailable_reason}; {pg_reason}"
            payload["bybit_failure_count_60s"] = 0
            payload["degraded_until_ms"] = None
            payload.update({
                "all_history": True,
                "range_start_ms": start_ms,
                "range_end_ms": end_ms,
                "page_size": 50,
                "preload_limit": limit,
            })
            return payload
        except Exception:
            return {
                "enabled": False,
                "source": "pg_fallback",
                "source_ts": int(time.time() * 1000),
                "cache_age": None,
                "cache_age_seconds": None,
                "list": [],
                "count": 0,
                "limit": limit,
                "offset": 0,
                "has_more": False,
                "next_offset": None,
                "next_cursor": None,
                "degraded_reason": f"{client_unavailable_reason}_and_pg_fallback_failed",
                "all_history": True,
                "range_start_ms": start_ms,
                "range_end_ms": end_ms,
                "page_size": 50,
                "preload_limit": limit,
            }

    try:
        rows, next_cursor = await asyncio.to_thread(
            _fetch_closed_pnl_bybit_history_page,
            rc,
            limit=limit,
            cursor=cursor,
            symbol=sym,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        clear_failures()
        enriched = await asyncio.to_thread(
            _attach_closed_pnl_strategy,
            rows,
            engine_owner_lookup=engine_owner_lookup,
            engine_modes=safe_modes,
        )
        return {
            "list": enriched,
            "count": len(enriched),
            "limit": limit,
            "offset": 0,
            "has_more": bool(next_cursor),
            "next_offset": None,
            "next_cursor": next_cursor,
            "source": "bybit_api",
            "source_ts": int(time.time() * 1000),
            "cache_age": 0.0,
            "cache_age_seconds": 0.0,
            "degraded_reason": None,
            "all_history": True,
            "range_start_ms": start_ms,
            "range_end_ms": end_ms,
            "page_size": 50,
            "preload_limit": limit,
        }
    except Exception as exc:
        failure_state = record_failure()
        degraded_suffix = (
            "; bybit_unavailable_5min_contact_operator"
            if failure_state["degraded_until_ms"] is not None
            else ""
        )
        try:
            payload = await asyncio.to_thread(
                _fetch_pg_closed_pnl_fallback,
                limit=limit,
                offset=0,
                symbol=sym,
                start_ms=start_ms,
                end_ms=end_ms,
                engine_modes=safe_modes,
            )
            payload["degraded_reason"] = (
                f"{payload.get('degraded_reason') or 'bybit_closed_pnl_unavailable'}"
                f"; bybit_failure_count_60s={failure_state['bybit_failure_count_60s']}"
                f"{degraded_suffix}"
            )
            payload.update(failure_state)
            payload.update({
                "all_history": True,
                "range_start_ms": start_ms,
                "range_end_ms": end_ms,
                "page_size": 50,
                "preload_limit": limit,
            })
            return payload
        except Exception as pg_exc:
            logger.exception("Bybit closed-pnl cursor mode and PG fallback both failed")
            from .error_sanitize import sanitize_exc_for_detail  # noqa: PLC0415
            raise HTTPException(
                status_code=502,
                detail=sanitize_exc_for_detail(pg_exc, "closed_pnl_unavailable"),
            ) from pg_exc
