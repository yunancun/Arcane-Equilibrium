from __future__ import annotations

"""
Agent Roster helpers (split from agents_routes per E2 round-2 M-3).
Agent 追蹤視圖輔助函數（M-3 從 agents_routes 拆出）。

MODULE_NOTE (EN): Three helper families backing the agent roster routes:
  (1) ``_fetch_*`` SELECT-only SQL readers, (2) ``_build_*_card`` per-role
  card builders, (3) ``_compose_summary_zh`` Strategist single-line zh
  summary. All pure-read + fail-closed (PG outage → empty + err-tag str,
  never raises). Cross-platform clean (no /Users / /home hardcoded paths).
  Each helper is also re-exported by ``agents_routes.py`` for legacy patch
  call sites. Hard contracts: SELECT-only · statement_timeout=2s ·
  PG outage → degraded=true (never 5xx) · ``LIKE 'agent_%'`` forbidden
  (use IN; H-3) · new endpoint queries hit hypertable indexes.

MODULE_NOTE (中): 三族 helper：(1) ``_fetch_*`` 純讀 SQL (2) ``_build_*_card``
  卡片組裝 (3) ``_compose_summary_zh`` 策略師中文摘要。皆純讀 + fail-closed
  （PG 不可達回空 + err-tag，絕不 raise）。跨平台乾淨無硬編路徑。
  ``agents_routes.py`` re-export 每個 helper 維持舊 patch site 相容。
  硬約束：純 SELECT · 2s timeout · PG 斷線 → degraded=true（非 5xx）·
  禁 ``LIKE 'agent_%'``（H-3 改 IN）· 新 endpoint 走索引。
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Tuple

from .db_pool import get_pg_conn

logger = logging.getLogger(__name__)


# ── Constants / 常量 ─────────────────────────────────────────────────────────

# Statement timeout for every read in this module — 2s is plenty for the 24h
# hypertable aggregates we run, and short enough that a stuck PG never wedges
# the GUI 30s polling loop.
# 本模組所有 SELECT 的 statement_timeout = 2s；24h 聚合查詢綽綽有餘，又短到
# 不會卡住前端 30s 輪詢迴圈。
_STATEMENT_TIMEOUT_MS: int = 2_000

# Heartbeat staleness bands derived from CognitiveModulator scan_interval EMA.
# 心跳判定：<1.5×EMA → 綠（active），<3× → 黃（slow），≥3× → 紅（offline）。
_HEARTBEAT_SLOW_FACTOR: float = 1.5
_HEARTBEAT_OFFLINE_FACTOR: float = 3.0

# Fallback scan interval (seconds) when CognitiveModulator unavailable. Matches
# the cognitive_modulator default base value so heartbeat math degrades cleanly.
# CognitiveModulator 不可達時的後備 scan_interval（秒），對齊默認 base 值。
_DEFAULT_SCAN_INTERVAL_S: int = 60

# H-3：5 runtime agent ``ai_usage_log.scope`` 白名單；``WHERE scope = ANY(...)``
# 走 V010 ``idx_ai_usage_log_scope_time(scope, time DESC)`` btree 索引，並消
# 除 ``LIKE 'agent_%'`` 的 ``_`` 單字元 wildcard 歧義（會誤中 agentX...）。
# H-3: 5-agent ``ai_usage_log.scope`` whitelist; ANY-array hits V010 btree
# index and avoids the ``LIKE 'agent_%'`` wildcard pitfall.
_AGENT_SCOPES: tuple[str, ...] = (
    "agent_scout",
    "agent_strategist",
    "agent_guardian",
    "agent_executor",
    "agent_analyst",
)

# Static role metadata — pure GUI presentation (emoji + zh/en label).
# 角色靜態 metadata（純呈現用）。
_ROLE_META: dict[str, dict[str, str]] = {
    "scout":      {"label_zh": "偵察員", "label_en": "Scout",      "emoji": "🔭"},
    "strategist": {"label_zh": "策略師", "label_en": "Strategist", "emoji": "♟️"},
    "guardian":   {"label_zh": "守門員", "label_en": "Guardian",   "emoji": "🛡️"},
    "executor":   {"label_zh": "執行員", "label_en": "Executor",   "emoji": "🧤"},
    "analyst":    {"label_zh": "分析師", "label_en": "Analyst",    "emoji": "🔍"},
}

# Per-role state-label Chinese translations / Per-role 中文 state label 字典。
_STATE_LABEL_ZH: dict[Tuple[str, str], str] = {
    ("scout", "active"): "巡邏中", ("scout", "idle"): "待命",
    ("scout", "slow"): "慢半拍", ("scout", "offline"): "失聯",
    ("strategist", "thinking"): "思考中", ("strategist", "watching"): "觀望",
    ("strategist", "budget_low"): "預算吃緊", ("strategist", "rejecting"): "拒絕信號中",
    ("strategist", "offline"): "失聯",
    ("guardian", "guarding"): "把關中", ("guardian", "tightening"): "收緊中",
    ("guardian", "frozen"): "凍結新倉", ("guardian", "offline"): "失聯",
    ("executor", "shadow"): "影子模式", ("executor", "live"): "真倉執行",
    ("executor", "unknown"): "狀態未確認", ("executor", "offline"): "失聯",
    ("analyst", "reviewing"): "復盤中", ("analyst", "waiting"): "等資料",
    ("analyst", "offline"): "失聯",
}


def _today_utc_start_ts() -> datetime:
    """UTC 0 點作為 24h 視窗下界 / Today's UTC midnight as 24h window floor."""
    now = datetime.now(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# ── Singleton accessors / 單例存取（延遲取得，失敗收縮） ─────────────────────


def _get_strategy_wiring() -> Any | None:
    """Lazily resolve strategy_wiring via sys.modules / 延遲解析避免 import 循環。"""
    return sys.modules.get("app.strategy_wiring") or sys.modules.get(
        "program_code.exchange_connectors.bybit_connector.control_api_v1.app.strategy_wiring"
    )


def _safe_get(obj: Any, attr: str) -> Any | None:
    """Best-effort getattr that swallows AttributeError / 安全 getattr。"""
    if obj is None:
        return None
    try:
        return getattr(obj, attr, None)
    except Exception:  # pragma: no cover - defensive
        return None


def _safe_call(fn: Optional[Callable[..., Any]], *args: Any, **kwargs: Any) -> Any | None:
    """Call ``fn`` and swallow any exception → None / 安全 call。"""
    if fn is None:
        return None
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("agents_routes safe_call failed: %s", exc)
        return None


def _get_cognitive_scan_interval_s() -> int:
    """讀 EMA 平滑後的 scan_interval（H-2：走 Strategist 公開 API，禁碰私有屬性）。
    Read EMA-smoothed scan_interval via Strategist public API (H-2).
    """
    sw = _get_strategy_wiring()
    strategist = _safe_get(sw, "STRATEGIST_AGENT")
    if strategist is None:
        return _DEFAULT_SCAN_INTERVAL_S
    interval = _safe_call(_safe_get(strategist, "get_scan_interval_seconds"))
    if interval is None or not isinstance(interval, (int, float)):
        return _DEFAULT_SCAN_INTERVAL_S
    return max(int(interval), 1)


# ── Heartbeat / state derivation / 心跳與狀態推導 ────────────────────────────


def _last_heartbeat_ms_from_eval_log(strategist: Any) -> int | None:
    """Most recent eval timestamp_ms from Strategist eval log / 取最近 eval 時戳。
    L-1：limit=1 → 單元素 list；用 ``[0]`` 表意明確（``[-1]`` 是無聲 no-op）。
    """
    recent = _safe_call(_safe_get(strategist, "get_recent_evaluations"), 1)
    if not recent:
        return None
    last = recent[0]
    if not isinstance(last, dict):
        return None
    ts = last.get("timestamp_ms")
    return int(ts) if isinstance(ts, (int, float)) else None


def _derive_heartbeat_state(
    last_heartbeat_ms: int | None,
    scan_interval_s: int,
    *,
    healthy_label: str,
    idle_label: str,
) -> Tuple[str, int | None]:
    """Map heartbeat lag → state band / 心跳延遲映射顏色狀態。

    <1.5×scan_interval → ``healthy_label`` / <3× → "slow" / ≥3× → "offline".
    None heartbeat → ``idle_label`` (cold start, not failure).
    """
    if last_heartbeat_ms is None:
        return idle_label, None
    now_ms = int(time.time() * 1000)
    lag_s = max(0, (now_ms - last_heartbeat_ms) / 1000.0)
    if lag_s < scan_interval_s * _HEARTBEAT_SLOW_FACTOR:
        return healthy_label, last_heartbeat_ms
    if lag_s < scan_interval_s * _HEARTBEAT_OFFLINE_FACTOR:
        return "slow", last_heartbeat_ms
    return "offline", last_heartbeat_ms


def _ms_to_iso(ms: int | None) -> str | None:
    """Convert ms-epoch to ISO-8601 UTC string. None → None / 毫秒轉 ISO 字串。"""
    if ms is None:
        return None
    try:
        return (
            datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
            .isoformat()
        )
    except Exception:
        return None


# ── DB read helpers (sync, called via asyncio.to_thread) / DB 同步讀（to_thread 包裹） ──


def _set_statement_timeout(cur: Any) -> None:
    """Set statement_timeout=2s on this cursor's transaction / 設 2s 超時保護。

    SET LOCAL reverts at commit/rollback so the timeout never leaks to the
    next pooled request. SET LOCAL 在 commit/rollback 自動還原，不污染 pool。
    """
    cur.execute("SET LOCAL statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))


def _fetch_today_costs_by_role() -> Tuple[dict[str, float], str | None]:
    """Today's UTC AI cost per ``agent_<role>`` scope / 今日各 agent scope 的 AI 成本。

    H-3：``WHERE scope = ANY(%s)`` 取代 ``LIKE 'agent_%%'`` — 走 V010
    ``idx_ai_usage_log_scope_time`` btree 索引 + 消除 ``_`` SQL wildcard 歧義。
    Returns ({role: cost_usd}, err_or_none).
    """
    today_start = _today_utc_start_ts()
    sql = """
        SELECT scope,
               COALESCE(SUM(cost_usd), 0.0)::float8 AS cost_usd
          FROM learning.ai_usage_log
         WHERE time >= %s
           AND scope = ANY(%s)
         GROUP BY scope
    """
    out: dict[str, float] = {}
    with get_pg_conn() as conn:
        if conn is None:
            return out, "pg_unavailable"
        try:
            cur = conn.cursor()
            _set_statement_timeout(cur)
            cur.execute(sql, (today_start, list(_AGENT_SCOPES)))
            for tup in cur.fetchall():
                scope, cost = tup
                if not isinstance(scope, str) or not scope.startswith("agent_"):
                    continue
                role = scope[len("agent_"):]
                out[role] = float(cost or 0.0)
            return out, None
        except Exception as exc:
            logger.warning("agents_routes today_costs query failed: %s", exc)
            return out, f"pg_error:{type(exc).__name__}"


def _fetch_today_intent_counts_by_strategy() -> Tuple[dict[str, int], int, str | None]:
    """Today's intent count grouped by strategy_name / 今日 intent 分策略計數。

    ``trading.intents`` is a daily-chunked hypertable; today's window touches
    exactly 1 chunk → partition prune sufficient.
    Returns ({strategy_name: count}, total, err_or_none).
    """
    today_start = _today_utc_start_ts()
    sql = """
        SELECT strategy_name,
               COUNT(*)::bigint AS n
          FROM trading.intents
         WHERE ts >= %s
         GROUP BY strategy_name
    """
    by_strategy: dict[str, int] = {}
    total = 0
    with get_pg_conn() as conn:
        if conn is None:
            return by_strategy, 0, "pg_unavailable"
        try:
            cur = conn.cursor()
            _set_statement_timeout(cur)
            cur.execute(sql, (today_start,))
            for tup in cur.fetchall():
                strat, n = tup
                n_int = int(n or 0)
                total += n_int
                if isinstance(strat, str):
                    by_strategy[strat] = n_int
            return by_strategy, total, None
        except Exception as exc:
            logger.warning("agents_routes today_intents query failed: %s", exc)
            return by_strategy, 0, f"pg_error:{type(exc).__name__}"


def _fetch_today_risk_verdict_counts() -> Tuple[dict[str, int], str | None]:
    """Today's risk_verdicts grouped by verdict / 今日 risk_verdict 按結果分組計數。

    Returns ({verdict_lc: count}, err_or_none) — verdict downcased.
    """
    today_start = _today_utc_start_ts()
    sql = """
        SELECT verdict,
               COUNT(*)::bigint AS n
          FROM trading.risk_verdicts
         WHERE ts >= %s
         GROUP BY verdict
    """
    out: dict[str, int] = {}
    with get_pg_conn() as conn:
        if conn is None:
            return out, "pg_unavailable"
        try:
            cur = conn.cursor()
            _set_statement_timeout(cur)
            cur.execute(sql, (today_start,))
            for tup in cur.fetchall():
                verdict, n = tup
                if isinstance(verdict, str):
                    out[verdict.lower()] = int(n or 0)
            return out, None
        except Exception as exc:
            logger.warning("agents_routes today_verdicts query failed: %s", exc)
            return out, f"pg_error:{type(exc).__name__}"


def _fetch_recent_rejected_verdicts(limit: int) -> Tuple[list[dict[str, Any]], str | None]:
    """Most recent ``REJECTED`` rows from ``trading.risk_verdicts`` (C-1a).
    plan §F「Lease 與守門紀錄」5 行表的後端查詢。hypertable 自然 partition prune。
    Returns ([{ts, symbol, reason, risk_level}], err_or_none).
    """
    sql = """
        SELECT ts,
               symbol,
               reason,
               risk_level
          FROM trading.risk_verdicts
         WHERE verdict = 'REJECTED'
         ORDER BY ts DESC
         LIMIT %s
    """
    rows: list[dict[str, Any]] = []
    with get_pg_conn() as conn:
        if conn is None:
            return rows, "pg_unavailable"
        try:
            cur = conn.cursor()
            _set_statement_timeout(cur)
            cur.execute(sql, (max(int(limit), 1),))
            for tup in cur.fetchall():
                ts, symbol, reason, risk_level = tup
                rows.append({
                    "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "symbol": symbol if isinstance(symbol, str) else None,
                    "reason": reason if isinstance(reason, str) else None,
                    "risk_level": risk_level if isinstance(risk_level, str) else None,
                })
            return rows, None
        except Exception as exc:
            logger.warning("agents_routes recent_rejects query failed: %s", exc)
            return rows, f"pg_error:{type(exc).__name__}"


def _fetch_shadow_vs_live_summary(
    since_hours: int,
) -> Tuple[dict[str, Any], str | None]:
    """Aggregate ``trading.fills`` over the last N hours, split demo vs live_demo.
    彙總最近 N 小時 ``trading.fills``，切 demo / live_demo 兩組（C-1b）。

    Per memory ``project_engine_mode_tag_live_demo`` engine writes BOTH
    ``'live'`` AND ``'live_demo'`` for LiveDemo traffic (43k historical
    'live' rows are LiveDemo) — UNION both under the ``live_demo`` bucket.
    記憶 ``engine_mode_tag_live_demo``：'live' 與 'live_demo' 都是 LiveDemo，
    本聚合 UNION 至 ``live_demo`` 桶；``demo`` 獨立。
    Index: V015 ``idx_fills_engine_mode_ts(engine_mode, ts DESC)``。
    Returns ({"demo":{count,total_pnl_usd,avg_slippage_bps},
             "live_demo":{...}}, err_or_none).
    """
    sql = """
        SELECT CASE WHEN engine_mode IN ('live', 'live_demo')
                    THEN 'live_demo'
                    ELSE 'demo'
               END AS bucket,
               COUNT(*)::bigint AS n,
               COALESCE(SUM(realized_pnl), 0.0)::float8 AS total_pnl,
               COALESCE(AVG(slippage_bps), 0.0)::float8 AS avg_slip
          FROM trading.fills
         WHERE engine_mode IN ('demo', 'live', 'live_demo')
           AND ts >= NOW() - make_interval(hours => %s)
         GROUP BY bucket
    """
    empty_bucket: dict[str, Any] = {
        "count": 0,
        "total_pnl_usd": 0.0,
        "avg_slippage_bps": 0.0,
    }
    out: dict[str, Any] = {
        "demo": dict(empty_bucket),
        "live_demo": dict(empty_bucket),
    }
    with get_pg_conn() as conn:
        if conn is None:
            return out, "pg_unavailable"
        try:
            cur = conn.cursor()
            _set_statement_timeout(cur)
            cur.execute(sql, (max(int(since_hours), 1),))
            for tup in cur.fetchall():
                bucket, n, pnl, slip = tup
                if bucket not in ("demo", "live_demo"):
                    continue
                out[bucket] = {
                    "count": int(n or 0),
                    "total_pnl_usd": float(pnl or 0.0),
                    "avg_slippage_bps": float(slip or 0.0),
                }
            return out, None
        except Exception as exc:
            logger.warning("agents_routes shadow_vs_live query failed: %s", exc)
            return out, f"pg_error:{type(exc).__name__}"


# ── async wrappers (H-4) / 非同步包裝（H-4） ────────────────────────────────


async def afetch_today_costs_by_role() -> Tuple[dict[str, float], str | None]:
    """H-4：sync fetch via ``asyncio.to_thread`` 避免阻塞 event loop。

    psycopg2 是同步的，statement_timeout=2s 觸發時 uvicorn event loop 會
    被卡 2 秒；包 to_thread 隔絕到 threadpool。
    """
    return await asyncio.to_thread(_fetch_today_costs_by_role)


async def afetch_today_intent_counts_by_strategy() -> Tuple[dict[str, int], int, str | None]:
    """Async wrapper for intent counts / intent 計數的非同步包裝（H-4）."""
    return await asyncio.to_thread(_fetch_today_intent_counts_by_strategy)


async def afetch_today_risk_verdict_counts() -> Tuple[dict[str, int], str | None]:
    """Async wrapper for risk_verdict counts / risk_verdict 計數的非同步包裝（H-4）."""
    return await asyncio.to_thread(_fetch_today_risk_verdict_counts)


async def afetch_recent_rejected_verdicts(limit: int) -> Tuple[list[dict[str, Any]], str | None]:
    """Async wrapper for recent rejects (C-1a, H-4)."""
    return await asyncio.to_thread(_fetch_recent_rejected_verdicts, limit)


async def afetch_shadow_vs_live_summary(since_hours: int) -> Tuple[dict[str, Any], str | None]:
    """Async wrapper for shadow-vs-live summary (C-1b, H-4)."""
    return await asyncio.to_thread(_fetch_shadow_vs_live_summary, since_hours)


# ── Strategist summary_zh composer / 策略師中文一句話組合 ───────────────────


def _compose_summary_zh(
    strategist: Any,
    *,
    state: str,
    intent_count_today: int,
    rejection_count_today: int,
) -> str:
    """Strategist「他在想什麼」單行中文摘要（plan §「後端配合」強制後端組句）。
    Compose Strategist single-line zh summary (server-side per plan).
    H1-H5 raw thought-gate output never exposed — only derived NL phrase.
    """
    if state == "budget_low":
        return "暂停思考中，今日 AI 思考预算已用完（重置时间 00:00 UTC）"
    if state == "rejecting" and rejection_count_today > 0:
        return f"刚刚否决了交易提案，因为风险预算不够（今日已拒绝 {rejection_count_today} 次）"
    if state == "offline":
        return "等待下一輪掃描"

    recent = _safe_call(_safe_get(strategist, "get_recent_evaluations"), 1) or []
    if recent:
        # L-1: ``recent`` is at most 1 element (we asked for limit=1); use [0]
        # for clarity. ``[-1]`` was a no-op disguise that read as "last of many".
        # L-1：``recent`` 最多 1 條（limit=1），用 [0] 表意明確。
        last = recent[0] if isinstance(recent[0], dict) else None
        symbols = last.get("symbols") if last else None
        if isinstance(symbols, list) and symbols:
            symbol = str(symbols[0])
            # Strip USDT suffix for friendlier human reading. BTC/ETH/STRK
            # without -USDT is what an operator says out loud.
            # 去掉 USDT 後綴更貼近 operator 口語表述。
            if symbol.endswith("USDT"):
                symbol_short = symbol[:-4]
            else:
                symbol_short = symbol
            evaluation = last.get("evaluation") if isinstance(last, dict) else None
            confidence = None
            if isinstance(evaluation, dict):
                conf = evaluation.get("confidence")
                if isinstance(conf, (int, float)):
                    confidence = float(conf)
            if confidence is not None and confidence > 0.0:
                return (
                    f"正在评估 {symbol_short} 信号，因为最近 {intent_count_today} 个交易意图"
                    f"（信心 {confidence:.2f}）"
                )
            return f"正在评估 {symbol_short} 信号，等待更多市场证据"

    return "等待下一轮扫描"


# ── Per-role roster builders / 單個 role 卡片組裝 ─────────────────────────────


def _build_role_envelope(role: str) -> dict[str, Any]:
    """Common card scaffold shared by every role / 5 個 role 共用骨架。"""
    meta = _ROLE_META[role]
    return {
        "role": role,
        "label_zh": meta["label_zh"],
        "label_en": meta["label_en"],
        "emoji": meta["emoji"],
        "state": "offline",
        "state_label_zh": _STATE_LABEL_ZH.get((role, "offline"), "失聯"),
        "summary_zh": "等待下一轮扫描",
        "last_heartbeat_ts": None,
        "today_cost_usd": 0.0,
        "today_decisions": 0,
    }


def _build_scout_card(
    today_costs_by_role: dict[str, float],
    today_intent_total: int,
    scan_interval_s: int,
) -> dict[str, Any]:
    """Scout card / 偵察員卡片。"""
    sw = _get_strategy_wiring()
    scout = _safe_get(sw, "SCOUT_AGENT")
    stats = _safe_call(_safe_get(scout, "get_stats")) or {}

    card = _build_role_envelope("scout")
    card["today_cost_usd"] = float(today_costs_by_role.get("scout", 0.0))
    card["today_decisions"] = int(stats.get("intel_produced", 0)) if stats else 0

    # Scout cycle ~30 min ≫ scan_interval；無逐條時戳，RUNNING + 有產出 = active。
    # Scout cycle far longer than scan_interval; running+intel>0 → active.
    state_value = stats.get("state", "stopped") if stats else "stopped"
    intel_produced = int(stats.get("intel_produced", 0)) if stats else 0
    if scout is None or state_value != "running":
        card["state"] = "offline"
    elif intel_produced > 0:
        card["state"] = "active"
    else:
        card["state"] = "idle"
    card["state_label_zh"] = _STATE_LABEL_ZH.get(
        ("scout", card["state"]), card["state_label_zh"]
    )

    if card["state"] in ("active", "idle"):
        card["summary_zh"] = (
            f"正在扫描市场（已产出 {intel_produced} 条情报）"
            if card["state"] == "active"
            else "等待下一轮扫描"
        )
    return card


def _build_strategist_card(
    today_costs_by_role: dict[str, float],
    today_intent_total: int,
    today_verdicts: dict[str, int],
    scan_interval_s: int,
) -> dict[str, Any]:
    """Strategist card with structured ``summary_zh`` / 策略師卡片含結構化中文摘要。"""
    sw = _get_strategy_wiring()
    strategist = _safe_get(sw, "STRATEGIST_AGENT")
    stats = _safe_call(_safe_get(strategist, "get_stats")) or {}

    card = _build_role_envelope("strategist")
    card["today_cost_usd"] = float(today_costs_by_role.get("strategist", 0.0))
    card["today_decisions"] = today_intent_total

    last_hb_ms = _last_heartbeat_ms_from_eval_log(strategist)
    state, last_hb_ms_out = _derive_heartbeat_state(
        last_hb_ms,
        scan_interval_s,
        healthy_label="thinking",
        idle_label="watching",
    )

    intel_evaluated = int(stats.get("intel_evaluated", 0))
    h1_budget_skip = int(stats.get("h1_budget_skip", 0))
    if intel_evaluated > 0 and h1_budget_skip / max(intel_evaluated, 1) >= 0.5:
        state = "budget_low"

    rejected = int(stats.get("evaluations_rejected", 0))
    produced = int(stats.get("intents_produced", 0))
    if rejected > 0 and rejected > produced * 2:
        state = "rejecting"

    card["state"] = state
    card["state_label_zh"] = _STATE_LABEL_ZH.get(
        ("strategist", state), card["state_label_zh"]
    )
    card["last_heartbeat_ts"] = _ms_to_iso(last_hb_ms_out)

    card["summary_zh"] = _compose_summary_zh(
        strategist,
        state=state,
        intent_count_today=today_intent_total,
        rejection_count_today=int(today_verdicts.get("rejected", 0)),
    )
    return card


def _build_guardian_card(
    today_costs_by_role: dict[str, float],
    today_verdicts: dict[str, int],
) -> dict[str, Any]:
    """Guardian card / 守門員卡片。"""
    sw = _get_strategy_wiring()
    guardian = _safe_get(sw, "GUARDIAN_AGENT")
    stats = _safe_call(_safe_get(guardian, "get_stats")) or {}

    card = _build_role_envelope("guardian")
    card["today_cost_usd"] = float(today_costs_by_role.get("guardian", 0.0))
    total_verdicts = sum(today_verdicts.values())
    card["today_decisions"] = total_verdicts

    state_value = stats.get("state", "stopped") if stats else "stopped"
    rejected = int(today_verdicts.get("rejected", 0))
    approved = int(today_verdicts.get("approved", 0))

    if guardian is None or state_value != "running":
        state = "offline"
    elif rejected > 0 and approved == 0:
        state = "frozen"
    elif rejected > approved * 0.5 and total_verdicts >= 4:
        state = "tightening"
    else:
        state = "guarding"

    card["state"] = state
    card["state_label_zh"] = _STATE_LABEL_ZH.get(
        ("guardian", state), card["state_label_zh"]
    )

    if state == "frozen":
        card["summary_zh"] = (
            f"今日凍結新倉提案 — 已拒絕 {rejected} 次（無通過）"
        )
    elif state == "tightening":
        card["summary_zh"] = (
            f"今日把關較嚴 — 通過 {approved} 次 / 拒絕 {rejected} 次"
        )
    elif state == "guarding":
        if total_verdicts == 0:
            card["summary_zh"] = "等待下一筆風險審批"
        else:
            card["summary_zh"] = (
                f"正在把關交易意圖（今日已審 {total_verdicts} 次）"
            )
    return card


def _build_executor_card(
    today_costs_by_role: dict[str, float],
    today_intent_total: int,
) -> dict[str, Any]:
    """Executor card with shadow/live banner data / 執行員卡片含影子/真倉資料。

    Backend ships raw ``shadow_mode`` (bool) + ``engine_mode`` (str) +
    ``today_orders`` (int = executions_success); GUI picks gradient + copy
    for the plan UX A-grade three-layer shadow/live separation. C-3 contract:
    ``ExecutorAgent.get_stats()`` MUST expose both ``shadow_mode`` and
    ``orders_submitted`` — missing field → fail-closed ``shadow_mode=True``.
    C-3：缺欄位 → fail-closed shadow=True，避免 degraded 快照誤渲染 live 綠標。
    """
    sw = _get_strategy_wiring()
    executor = _safe_get(sw, "EXECUTOR_AGENT")
    stats = _safe_call(_safe_get(executor, "get_stats")) or {}

    card = _build_role_envelope("executor")
    card["today_cost_usd"] = float(today_costs_by_role.get("executor", 0.0))
    card["today_decisions"] = today_intent_total

    # C-3：shadow_mode 由 get_stats() 透出（SoT=ExecutorConfigCache provider）；
    # 僅欄位缺席時 fail-closed True。``int(0/1)`` 經 ``bool(...)`` 轉換正確。
    # C-3: shadow_mode surfaced via get_stats(); fail-closed True only on miss.
    shadow_raw = stats.get("shadow_mode")
    shadow_mode = (
        bool(shadow_raw) if shadow_raw is not None else True
    )
    card["shadow_mode"] = shadow_mode

    engine_mode = (
        os.environ.get("OPENCLAW_ENGINE_MODE")
        or os.environ.get("OPENCLAW_EXECUTOR_CACHE_ENGINE")
        or "paper"
    )
    card["engine_mode"] = engine_mode

    # C-3：orders_submitted = executions_success（實際成交，非 attempt）。
    card["today_orders"] = int(stats.get("orders_submitted", 0)) if stats else 0

    state_value = stats.get("state", "stopped") if stats else "stopped"
    if executor is None or state_value != "running":
        # Plan §"絕不允許灰色「未知」"：任何狀態無法確認時走紅 + 暫停接單文案。
        card["state"] = "offline"
        card["state_label_zh"] = _STATE_LABEL_ZH[("executor", "offline")]
        card["summary_zh"] = "状态未确认，已暂停接单"
    elif shadow_mode:
        card["state"] = "shadow"
        card["state_label_zh"] = _STATE_LABEL_ZH[("executor", "shadow")]
        card["summary_zh"] = (
            f"影子模式 — 模拟成单 {card['today_orders']} 笔，不会送真单到交易所"
        )
    else:
        card["state"] = "live"
        card["state_label_zh"] = _STATE_LABEL_ZH[("executor", "live")]
        card["summary_zh"] = (
            f"真仓执行中 — 真实成单 {card['today_orders']} 笔（{engine_mode}）"
        )

    return card


def _build_analyst_card(
    today_costs_by_role: dict[str, float],
    scan_interval_s: int,
) -> dict[str, Any]:
    """Analyst card / 分析師卡片。"""
    sw = _get_strategy_wiring()
    analyst = _safe_get(sw, "ANALYST_AGENT")
    stats = _safe_call(_safe_get(analyst, "get_stats")) or {}

    card = _build_role_envelope("analyst")
    card["today_cost_usd"] = float(today_costs_by_role.get("analyst", 0.0))
    trades_analyzed = int(stats.get("trades_analyzed", 0)) if stats else 0
    card["today_decisions"] = trades_analyzed

    state_value = stats.get("state", "stopped") if stats else "stopped"
    if analyst is None or state_value != "running":
        state = "offline"
    elif trades_analyzed > 0:
        state = "reviewing"
    else:
        state = "waiting"

    card["state"] = state
    card["state_label_zh"] = _STATE_LABEL_ZH.get(
        ("analyst", state), card["state_label_zh"]
    )

    if state == "reviewing":
        card["summary_zh"] = (
            f"正在复盘最近的成交（今日已分析 {trades_analyzed} 笔）"
        )
    elif state == "waiting":
        card["summary_zh"] = "等待新成交进入复盘队列"
    return card


__all__ = [
    "_STATEMENT_TIMEOUT_MS",
    "_HEARTBEAT_SLOW_FACTOR",
    "_HEARTBEAT_OFFLINE_FACTOR",
    "_DEFAULT_SCAN_INTERVAL_S",
    "_AGENT_SCOPES",
    "_ROLE_META",
    "_STATE_LABEL_ZH",
    "_today_utc_start_ts",
    "_get_strategy_wiring",
    "_safe_get",
    "_safe_call",
    "_get_cognitive_scan_interval_s",
    "_last_heartbeat_ms_from_eval_log",
    "_derive_heartbeat_state",
    "_ms_to_iso",
    "_set_statement_timeout",
    "_fetch_today_costs_by_role",
    "_fetch_today_intent_counts_by_strategy",
    "_fetch_today_risk_verdict_counts",
    "_fetch_recent_rejected_verdicts",
    "_fetch_shadow_vs_live_summary",
    "afetch_today_costs_by_role",
    "afetch_today_intent_counts_by_strategy",
    "afetch_today_risk_verdict_counts",
    "afetch_recent_rejected_verdicts",
    "afetch_shadow_vs_live_summary",
    "_compose_summary_zh",
    "_build_role_envelope",
    "_build_scout_card",
    "_build_strategist_card",
    "_build_guardian_card",
    "_build_executor_card",
    "_build_analyst_card",
]
