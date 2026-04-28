from __future__ import annotations

"""
Agent Roster Read-Only Router / Agent 追蹤視圖只讀路由。

MODULE_NOTE (EN): MVP backend for "AI 团队工作台" Learning Cockpit sub-section
  (Plan ``aa-nifty-walrus.md`` Wave T1). This module owns the *routes*; the
  helper composition (``_fetch_*`` SQL readers, ``_build_*_card`` per-role
  builders, ``_compose_summary_zh``) lives in ``agents_routes_helpers.py``
  (E2 round-2 finding M-3 split). The split keeps both files under the §九
  800-line warning line and lets future C-1 / C-2 endpoints land without
  re-breaking it. Endpoints exposed:

    GET /api/v1/agents/roster                — aggregated 5-Agent runtime view
    GET /api/v1/agents/recent_rejects        — recent REJECTED risk_verdicts (C-1a)
    GET /api/v1/agents/shadow_vs_live_summary — demo vs live_demo fills aggregate (C-1b)

  Hard contracts (E2 必查):
    1. Read-only — ``grep -E ' INSERT | UPDATE | DELETE '`` is 0 in this file
       AND in ``agents_routes_helpers.py``.
    2. Fail-closed but degraded-not-fatal — PG outage degrades cost/count
       fields to 0 + sets ``degraded=true``, never 5xx.
    3. ``statement_timeout=2s`` on every read (set by helper).
    4. ``summary_zh`` is composed server-side (handing raw JSON to GUI
       degrades UX A→B per plan §"後端配合").
    5. H1-H5 raw thought-gate output never exposed — only derived
       natural-language phrase.
    6. Cross-platform clean per CLAUDE.md §七 ★★ (no ``/Users`` / ``/home``).
    7. New endpoints (C-1) must hit a hypertable index — verified via
       ``EXPLAIN ANALYZE`` in the E2 report.
    8. All sync PG calls are wrapped via ``asyncio.to_thread`` (H-4) so the
       uvicorn event loop never blocks while ``statement_timeout`` ticks.

MODULE_NOTE (中): Agent 追蹤視圖只讀路由（plan T1 後端 MVP）。本檔僅放
  *route handler*；helper（_fetch_* / _build_*_card / _compose_summary_zh）
  已拆至 ``agents_routes_helpers.py``（E2 round-2 M-3）。兩檔皆保持在
  §九 800 行警告線下，未來 C-1 / C-2 endpoint 再加也不會破。曝露端點：

    GET /api/v1/agents/roster                — 5 個 Agent 聚合視圖
    GET /api/v1/agents/recent_rejects        — 最近 REJECTED 風控裁定（C-1a）
    GET /api/v1/agents/shadow_vs_live_summary — demo vs live_demo 成交聚合（C-1b）

  硬約束（E2 必查）：(1) 純讀（INSERT/UPDATE/DELETE=0，本檔與 helpers 皆然）
  (2) PG 不可達一律 200 + degraded=true (3) statement_timeout=2s（helper 內設）
  (4) summary_zh 後端組句 (5) 不曝露 H1-H5 raw thought-gate (6) 跨平台乾淨
  (7) 新 endpoint 必走索引（EXPLAIN 驗）(8) 所有同步 PG 呼叫經 ``asyncio.to_thread``
  包覆（H-4），避免 statement_timeout 觸發時阻塞 event loop。
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query

from . import main_legacy as base
from . import agents_routes_helpers as _h

# Re-export every helper at module level so existing test patches that target
# ``app.agents_routes._build_executor_card`` / ``_fetch_today_costs_by_role``
# / ``_compose_summary_zh`` etc. continue to work post-split. Plain rebinding
# is sufficient because the helpers don't capture module-local state.
# 將所有 helper 重綁到本模組層級，確保 ``app.agents_routes._foo``
# 既有 test patch 與外部引用不破。helper 不持模組本地 state，純 alias 即可。
_STATEMENT_TIMEOUT_MS = _h._STATEMENT_TIMEOUT_MS
_HEARTBEAT_SLOW_FACTOR = _h._HEARTBEAT_SLOW_FACTOR
_HEARTBEAT_OFFLINE_FACTOR = _h._HEARTBEAT_OFFLINE_FACTOR
_DEFAULT_SCAN_INTERVAL_S = _h._DEFAULT_SCAN_INTERVAL_S
_AGENT_SCOPES = _h._AGENT_SCOPES
_ROLE_META = _h._ROLE_META
_STATE_LABEL_ZH = _h._STATE_LABEL_ZH

_today_utc_start_ts = _h._today_utc_start_ts
_get_strategy_wiring = _h._get_strategy_wiring
_safe_get = _h._safe_get
_safe_call = _h._safe_call
_get_cognitive_scan_interval_s = _h._get_cognitive_scan_interval_s
_last_heartbeat_ms_from_eval_log = _h._last_heartbeat_ms_from_eval_log
_derive_heartbeat_state = _h._derive_heartbeat_state
_ms_to_iso = _h._ms_to_iso
_set_statement_timeout = _h._set_statement_timeout
_fetch_today_costs_by_role = _h._fetch_today_costs_by_role
_fetch_today_intent_counts_by_strategy = _h._fetch_today_intent_counts_by_strategy
_fetch_today_risk_verdict_counts = _h._fetch_today_risk_verdict_counts
_fetch_recent_rejected_verdicts = _h._fetch_recent_rejected_verdicts
_fetch_shadow_vs_live_summary = _h._fetch_shadow_vs_live_summary
_compose_summary_zh = _h._compose_summary_zh
_build_role_envelope = _h._build_role_envelope
_build_scout_card = _h._build_scout_card
_build_strategist_card = _h._build_strategist_card
_build_guardian_card = _h._build_guardian_card
_build_executor_card = _h._build_executor_card
_build_analyst_card = _h._build_analyst_card


# Re-export ``get_pg_conn`` so legacy tests that patched
# ``app.agents_routes.get_pg_conn`` keep working — but post-split the SQL
# actually executes inside ``agents_routes_helpers`` whose own
# ``get_pg_conn`` symbol is the real call site. The integration test fixture
# patches the helper module directly; this alias is kept for backwards
# compatibility (zero call sites left in tests use it post-update, but
# downstream consumers may import it).
# Re-export ``get_pg_conn``：拆分後 SQL 實際在 helpers 內呼叫，新 test
# fixture 直接 patch helper 模組；本 alias 為相容性保留。
from .db_pool import get_pg_conn  # noqa: E402,F401 — alias for legacy test compat


logger = logging.getLogger(__name__)


# ── Router definition / 路由定義 ────────────────────────────────────────────
agents_router = APIRouter(
    prefix="/api/v1/agents",
    tags=["Agents Roster / Agent 追蹤視圖"],
)


# ── Route handlers / 端點 ───────────────────────────────────────────────────


@agents_router.get("/roster")
async def get_agents_roster(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """GET /api/v1/agents/roster — aggregated 5-Agent runtime view / 聚合視圖。

    Returns Plan §"頁面 Layout" §A "Agent 五張卡片" backing data: one card per
    role (identity / state / state_label_zh / summary_zh / heartbeat ts / today
    cost / today decisions). Executor card adds ``shadow_mode`` (bool) +
    ``engine_mode`` + ``today_orders`` for the GUI's three-layer shadow vs
    live visual separation. Auth: viewer scope (same dependency as
    ``/strategist/history``) — read-only payload.

    H-4: every PG fetch is wrapped via ``asyncio.to_thread`` so the uvicorn
    event loop never blocks while ``statement_timeout=2s`` ticks. Three
    aggregates run *concurrently* via ``asyncio.gather`` for ~3× lower P50
    latency vs. sequential.

    回傳 5 張 Agent 卡片資料（plan §A）。Executor 多帶 shadow_mode +
    engine_mode + today_orders 供 GUI 影子/真倉強隔離渲染。Auth 對齊
    ``/strategist/history``（viewer 即可）。

    H-4：每個 PG fetch 經 ``asyncio.to_thread`` 包覆，statement_timeout=2s
    觸發時不阻塞 event loop。3 個聚合 ``asyncio.gather`` 併發跑，P50 延遲
    約為循序的 1/3。
    """
    import asyncio  # local import per route to avoid module-level cycle risk

    response_ts = datetime.now(timezone.utc).isoformat()

    # H-4 + perf: gather 3 sync fetches concurrently on threadpool.
    # H-4 + 效能：3 個同步 fetch 在 threadpool 併發。
    (
        (today_costs_by_role, cost_err),
        (today_by_strategy, today_intent_total, intent_err),
        (today_verdicts, verdict_err),
    ) = await asyncio.gather(
        _h.afetch_today_costs_by_role(),
        _h.afetch_today_intent_counts_by_strategy(),
        _h.afetch_today_risk_verdict_counts(),
    )
    # Silence unused-var warning on the by_strategy breakdown — kept for
    # future consumption (e.g. plan §B pipeline drill-down). 暫保留供 §B 用。
    del today_by_strategy

    degraded = any(err is not None for err in (cost_err, intent_err, verdict_err))
    reason = cost_err or intent_err or verdict_err

    scan_interval_s = _h._get_cognitive_scan_interval_s()

    cards = [
        _h._build_scout_card(today_costs_by_role, today_intent_total, scan_interval_s),
        _h._build_strategist_card(
            today_costs_by_role,
            today_intent_total,
            today_verdicts,
            scan_interval_s,
        ),
        _h._build_guardian_card(today_costs_by_role, today_verdicts),
        _h._build_executor_card(today_costs_by_role, today_intent_total),
        _h._build_analyst_card(today_costs_by_role, scan_interval_s),
    ]

    return {
        "ok": True,
        "data": {
            "ts": response_ts,
            "agents": cards,
            "scan_interval_s": scan_interval_s,
            "degraded": degraded,
            "reason": reason,
        },
        "is_simulated": False,
        "data_category": "agents_roster",
    }


@agents_router.get("/recent_rejects")
async def get_recent_rejects(
    limit: int = Query(5, ge=1, le=50),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """GET /api/v1/agents/recent_rejects — recent REJECTED risk_verdicts (C-1a).

    Plan §F "Lease 與守門紀錄" 5-row table backing endpoint. Pulls the most
    recent ``trading.risk_verdicts`` rows where ``verdict='REJECTED'`` over
    the hypertable. Read-only, ``statement_timeout=2s``, fail-closed →
    ``degraded=true`` on PG outage. Default ``limit=5`` matches plan UX;
    capped at 50 to keep the worst-case index walk bounded.

    Plan §F「Lease 與守門紀錄」5 行表的後端端點。回傳 ``trading.risk_verdicts``
    最近 ``verdict='REJECTED'`` 若干筆。純讀 + 2s timeout，PG 不可達回
    ``degraded=true``。預設 5 筆對齊 plan UX；上限 50 限制 worst-case。

    Response schema:
        {
          ok: bool,
          data: {
            rows: [{ts: ISO-8601, symbol: str, reason: str, risk_level: "P0|P1|P2"}],
            degraded: bool,
            reason: str | null,
          },
          is_simulated: false,
          data_category: "agents_recent_rejects",
        }
    """
    rows, err = await _h.afetch_recent_rejected_verdicts(limit)
    return {
        "ok": True,
        "data": {
            "rows": rows,
            "degraded": err is not None,
            "reason": err,
        },
        "is_simulated": False,
        "data_category": "agents_recent_rejects",
    }


# Mapping of accepted ``since`` query string values to hours.
# 接受的 ``since`` query string 對應小時數。
_SHADOW_VS_LIVE_SINCE_MAP: dict[str, int] = {
    "1h": 1,
    "6h": 6,
    "12h": 12,
    "24h": 24,
    "48h": 48,
    "7d": 24 * 7,
}


@agents_router.get("/shadow_vs_live_summary")
async def get_shadow_vs_live_summary(
    since: str = Query("24h", description="Window: 1h | 6h | 12h | 24h | 48h | 7d"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """GET /api/v1/agents/shadow_vs_live_summary — demo vs live_demo aggregate (C-1b).

    Plan §E "影子 vs 真倉對比" backing endpoint. Aggregates ``trading.fills``
    over the requested window split by ``engine_mode``: ``demo`` is its own
    bucket; ``live`` and ``live_demo`` are UNIONed under ``live_demo`` (per
    memory ``project_engine_mode_tag_live_demo`` — historical 43k 'live' rows
    are LiveDemo traffic, not real Mainnet fills). Returns counts, total
    realized PnL, and average slippage bps per bucket plus a top-level diff
    block (live_demo − demo) for the GUI's "+/- N bps" delta line.

    Plan §E「影子 vs 真倉對比」後端端點。聚合 ``trading.fills`` 視窗內依
    ``engine_mode`` 切桶：``demo`` 獨立；``live`` 與 ``live_demo`` UNION 至
    ``live_demo``（per memory ``engine_mode_tag_live_demo`` — 歷史 43k 'live'
    其實是 LiveDemo）。每桶回成交筆數、累計 realized PnL、平均 slippage bps，
    並補一個頂層 ``diff``（live_demo − demo）給 GUI 渲染「+/- N bps」差異行。

    Response schema:
        {
          ok: bool,
          data: {
            since: str,
            since_hours: int,
            demo: {count: int, total_pnl_usd: float, avg_slippage_bps: float},
            live_demo: {count: int, total_pnl_usd: float, avg_slippage_bps: float},
            diff: {fill_rate_delta_pct: float, slippage_delta_bps: float},
            degraded: bool,
            reason: str | null,
          },
          is_simulated: false,
          data_category: "agents_shadow_vs_live",
        }

    ``fill_rate_delta_pct`` is computed as
    ``(live_demo.count - demo.count) / max(demo.count, 1) * 100`` and is
    intentionally a relative ratio in percent (not bps) — the column name
    keeps the GUI label honest. ``slippage_delta_bps`` is the absolute
    bps difference (live_demo.avg − demo.avg).
    ``fill_rate_delta_pct`` 為相對百分比；``slippage_delta_bps`` 為絕對 bps 差。
    """
    since_hours = _SHADOW_VS_LIVE_SINCE_MAP.get(since, 24)

    summary, err = await _h.afetch_shadow_vs_live_summary(since_hours)

    demo = summary.get("demo", {"count": 0, "total_pnl_usd": 0.0, "avg_slippage_bps": 0.0})
    live_demo = summary.get(
        "live_demo", {"count": 0, "total_pnl_usd": 0.0, "avg_slippage_bps": 0.0}
    )

    # Fill rate delta: relative pct, anchored on demo. demo=0 → 0% (avoid
    # division by zero / inf). 相對百分比，demo=0 時回 0% 避免除零。
    demo_count = int(demo.get("count", 0) or 0)
    live_count = int(live_demo.get("count", 0) or 0)
    if demo_count > 0:
        fill_rate_delta_pct = (live_count - demo_count) / demo_count * 100.0
    else:
        fill_rate_delta_pct = 0.0

    slippage_delta_bps = float(
        live_demo.get("avg_slippage_bps", 0.0) or 0.0
    ) - float(demo.get("avg_slippage_bps", 0.0) or 0.0)

    return {
        "ok": True,
        "data": {
            "since": since,
            "since_hours": since_hours,
            "demo": demo,
            "live_demo": live_demo,
            "diff": {
                "fill_rate_delta_pct": round(fill_rate_delta_pct, 2),
                "slippage_delta_bps": round(slippage_delta_bps, 2),
            },
            "degraded": err is not None,
            "reason": err,
        },
        "is_simulated": False,
        "data_category": "agents_shadow_vs_live",
    }
