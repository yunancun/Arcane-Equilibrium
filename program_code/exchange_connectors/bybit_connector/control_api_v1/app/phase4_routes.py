"""
Phase 4 Dashboard Routes — skeleton (4-00).
Phase 4 儀表板路由 — 骨架（4-00）。

MODULE_NOTE (中文):
  本模組為 Phase 4 儀表板提供骨架路由：
  1. GET /api/v1/phase4/status — 返回四個模組（Teacher/LinUCB/News/DL-3）的紅黃綠燈狀態
  2. GET /api/v1/phase4 — 渲染靜態 tab-phase4.html（重定向至 /static/tab-phase4.html）

  狀態源：先嘗試 IPC `get_phase4_status`，失敗時 fail-closed 回 grey + degraded。
  後續 4-01 ... 4-21 會將 stub grey 替換為各模組真實聚合（Teacher 回放/LinUCB regret/
  News severity/DL-3 health）。

MODULE_NOTE (English):
  Skeleton routes for the Phase 4 dashboard:
  1. GET /api/v1/phase4/status — returns traffic-light state for 4 modules
     (Teacher / LinUCB / News / DL-3).
  2. GET /api/v1/phase4 — redirects to the static tab-phase4.html.

  Status source: tries IPC `get_phase4_status`; on failure fail-closed to grey
  with degraded=true. Sub-tasks 4-01 ... 4-21 will replace the grey stub with
  the real per-module aggregations.

Safety:
  - Read-only — no trading state mutation. / 純讀取，不改交易狀態。
  - Fail-closed — IPC down → grey, never silent green. / IPC 斷線時退回 grey，
    永不靜默回 green。
  - No hard-coded paths — see CLAUDE.md §七 cross-platform rule.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Router prefix follows the project's /api/v1 convention.
# 路由前綴遵循項目 /api/v1 約定。
phase4_router = APIRouter(prefix="/api/v1/phase4", tags=["phase4"])


# Allowed traffic-light vocabulary / 合法紅黃綠燈詞彙
_VALID_LIGHTS = {"grey", "green", "yellow", "red"}

# Phase 4 module keys (must stay in sync with Rust handle_get_phase4_status).
# Phase 4 模組鍵（必須與 Rust handle_get_phase4_status 保持同步）。
_MODULE_KEYS = ("teacher", "linucb", "news", "dl3")


def _grey_payload(degraded: bool, reason: str | None = None) -> dict[str, Any]:
    """
    Build a grey-only payload (used as fail-closed default).
    構造全 grey 的 payload（fail-closed 預設）。
    """
    payload: dict[str, Any] = {key: "grey" for key in _MODULE_KEYS}
    payload["last_update_ms"] = int(time.time() * 1000)
    payload["degraded"] = degraded
    if reason is not None:
        payload["reason"] = reason
    return payload


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize a phase4 status payload.
    Unknown / invalid status values are coerced to "grey" (fail-closed).
    校驗並標準化 phase4 狀態 payload。未知或非法狀態值強制降為 "grey"（fail-closed）。
    """
    out: dict[str, Any] = {}
    for key in _MODULE_KEYS:
        v = payload.get(key)
        out[key] = v if isinstance(v, str) and v in _VALID_LIGHTS else "grey"
    last_ms = payload.get("last_update_ms")
    out["last_update_ms"] = (
        int(last_ms) if isinstance(last_ms, (int, float)) and last_ms > 0
        else int(time.time() * 1000)
    )
    out["degraded"] = False
    return out


async def _query_engine_status() -> dict[str, Any]:
    """
    Query the Rust engine via IPC for the latest phase4 aggregation.
    Falls back to grey on any failure (no exception raised to caller).
    通過 IPC 向 Rust 引擎查詢最新的 phase4 聚合，任何失敗均退回 grey
    （不向呼叫者拋例外）。
    """
    try:
        # Lazy import to avoid hard coupling in test environments.
        # 延遲匯入以避免在測試環境硬耦合。
        from .ipc_client import EngineIPCClient  # type: ignore
    except Exception as exc:  # pragma: no cover - import-time guard
        logger.warning("phase4: IPC client import failed: %s", exc)
        return _grey_payload(degraded=True, reason="ipc_client_import_failed")

    client_factory = getattr(EngineIPCClient, "get_singleton", None)
    if client_factory is None:
        # No singleton helper — best effort: return grey.
        # 沒有 singleton helper — 盡力而為：返回 grey。
        return _grey_payload(degraded=True, reason="no_singleton")

    try:
        client = client_factory()
        raw = await client.get_phase4_status()
        if not isinstance(raw, dict):
            return _grey_payload(degraded=True, reason="bad_payload_shape")
        return _sanitize(raw)
    except Exception as exc:
        logger.warning("phase4: IPC get_phase4_status failed: %s", exc)
        return _grey_payload(degraded=True, reason=f"ipc_error:{type(exc).__name__}")


@phase4_router.get("/status")
async def get_phase4_status() -> dict[str, Any]:
    """
    Phase 4 dashboard status aggregation endpoint.
    Phase 4 儀表板狀態聚合端點。

    Returns a flat dict:
        {
          "teacher":  "grey" | "green" | "yellow" | "red",
          "linucb":   "grey" | ...,
          "news":     "grey" | ...,
          "dl3":      "grey" | ...,
          "last_update_ms": <unix-millis>,
          "degraded": <bool>,
          "reason":   <optional str>
        }

    Until 4-01 ... 4-21 are implemented, every module is reported as "grey"
    (not started). The frontend should render grey lights as neutral.
    在 4-01 ... 4-21 實作之前，所有模組均回報為 "grey"（未啟動）。前端應將
    grey 燈渲染為中性灰色。
    """
    return await _query_engine_status()


# ---------------------------------------------------------------------------
# 4-06 · LinUCB Card backend route
# 4-06 · LinUCB 卡片後端路由
# ---------------------------------------------------------------------------

_V1_15_STRATEGIES = (
    "ma_crossover",
    "bb_reversion",
    "bb_breakout",
    "grid_trading",
    "donchian_breakout",
)
_V1_15_REGIMES = ("trending", "ranging", "volatile")


def _default_linucb_payload(reason: str) -> dict[str, Any]:
    """Fail-closed payload for the LinUCB card.
    LinUCB 卡片的 fail-closed 預設 payload。
    """
    # Empty grey arms / 空灰 arm 列表
    arms: list[dict[str, Any]] = []
    for regime in _V1_15_REGIMES:
        for strat in _V1_15_STRATEGIES:
            arms.append({"arm_id": f"{regime}__{strat}", "n_pulls": 0, "converged": False})
    return {
        "ok": False,
        "reason": reason,
        "active_version": "v1_15",
        "feature_schema_hash": None,
        "total_pulls": 0,
        "converged_arms": 0,
        "min_samples_per_arm": 100,
        "arms": arms,
        "shadow": {"active": False},
        "migrations": [],
        "last_update_ms": int(time.time() * 1000),
    }


def _fetch_linucb_state_from_pg() -> dict[str, Any]:  # pragma: no cover — live DB path
    """Read learning.linucb_state + recent linucb_migrations from PG.
    從 PG 讀取 linucb_state 與最近的 linucb_migrations。

    Fail-soft: any exception → grey placeholder via caller.
    """
    import os

    try:
        import psycopg2  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"psycopg2_unavailable:{exc}") from exc

    dsn = os.environ.get("OPENCLAW_PG_DSN") or os.environ.get("PG_DSN")
    if not dsn:
        raise RuntimeError("no_dsn")

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Active version = most recent migration's to_version, default v1_15
            cur.execute(
                "SELECT to_version FROM learning.linucb_migrations "
                "ORDER BY migration_id DESC LIMIT 1"
            )
            row = cur.fetchone()
            active_version = row[0] if row else "v1_15"

            # Per-arm state for the active version
            cur.execute(
                "SELECT arm_id, n_pulls, feature_schema_hash "
                "FROM learning.linucb_state WHERE arm_space_version = %s",
                (active_version,),
            )
            arm_rows = cur.fetchall()

            # Recent migrations (last 5)
            cur.execute(
                "SELECT migration_id, from_version, to_version, direction, gamma, "
                "n_arms_before, n_arms_after, started_ts "
                "FROM learning.linucb_migrations ORDER BY migration_id DESC LIMIT 5"
            )
            mig_rows = cur.fetchall()

    min_samples = 100
    arms_payload = [
        {
            "arm_id": r[0],
            "n_pulls": int(r[1] or 0),
            "converged": int(r[1] or 0) >= min_samples,
        }
        for r in arm_rows
    ]
    schema_hash = arm_rows[0][2] if arm_rows else None
    total_pulls = sum(a["n_pulls"] for a in arms_payload)
    converged_arms = sum(1 for a in arms_payload if a["converged"])
    migrations_payload = [
        {
            "migration_id": m[0],
            "from_version": m[1],
            "to_version": m[2],
            "direction": m[3],
            "gamma": float(m[4]) if m[4] is not None else None,
            "n_arms_before": m[5],
            "n_arms_after": m[6],
            "started_ts": m[7].isoformat() if m[7] is not None else None,
        }
        for m in mig_rows
    ]
    return {
        "ok": True,
        "active_version": active_version,
        "feature_schema_hash": schema_hash,
        "total_pulls": total_pulls,
        "converged_arms": converged_arms,
        "min_samples_per_arm": min_samples,
        "arms": arms_payload,
        "shadow": {"active": False},  # filled by shadow_compare job output when present
        "migrations": migrations_payload,
        "last_update_ms": int(time.time() * 1000),
    }


@phase4_router.get("/linucb")
async def get_phase4_linucb() -> dict[str, Any]:
    """LinUCB card data: active version, per-arm pulls, recent migrations.
    LinUCB 卡片資料：啟用版本 / per-arm pulls / 最近遷移。

    Fail-closed: any error → ok=false grey placeholder (never raises).
    """
    try:
        return _fetch_linucb_state_from_pg()
    except Exception as exc:
        logger.warning("phase4/linucb fail-soft: %s", exc)
        return _default_linucb_payload(reason=f"{type(exc).__name__}")


# ---------------------------------------------------------------------------
# 4-03 · Teacher Card backend route
# 4-03 · Teacher 卡片後端路由
# ---------------------------------------------------------------------------


def _default_teacher_payload(reason: str) -> dict[str, Any]:
    """Fail-closed payload for the Teacher card.
    Teacher 卡片的 fail-closed 預設 payload。
    """
    return {
        "ok": False,
        "reason": reason,
        "status_light": "grey",
        "total_7d": 0,
        "applied_7d": 0,
        "exec_rate": 0.0,
        "avg_outcome_24h": None,
        "recent": [],
        "last_update_ms": int(time.time() * 1000),
    }


def _classify_teacher_status(
    exec_rate: float, avg_outcome_24h: float | None
) -> str:
    """Map exec_rate + avg_outcome_24h into a red/yellow/green status light.
    將 exec_rate + avg_outcome_24h 對映為 red/yellow/green 燈號。

    Rules / 規則:
        - exec_rate >= 0.8 AND avg_outcome >= 0  -> green
        - exec_rate in [0.6, 0.8) OR avg_outcome < 0 (mild) -> yellow
        - exec_rate < 0.6 OR avg_outcome very negative      -> red
    """
    outcome = avg_outcome_24h if avg_outcome_24h is not None else 0.0
    if exec_rate >= 0.8 and outcome >= 0.0:
        return "green"
    if exec_rate < 0.6:
        return "red"
    if outcome < -10.0:  # USD threshold for "very negative"
        return "red"
    return "yellow"


def _fetch_teacher_state_from_pg() -> dict[str, Any]:  # pragma: no cover — live DB path
    """Read 7d directive_executions stats + recent rows from PG.
    從 PG 讀取 7d directive_executions 統計 + 最近 row。

    Fail-soft: any exception → caller maps to grey placeholder.
    """
    import os

    try:
        import psycopg2  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"psycopg2_unavailable:{exc}") from exc

    dsn = os.environ.get("OPENCLAW_PG_DSN") or os.environ.get("PG_DSN")
    if not dsn:
        raise RuntimeError("no_dsn")

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # 7d aggregate stats
            # 7d 聚合統計
            cur.execute(
                """
                SELECT
                    COUNT(*)::int                                       AS total_7d,
                    COUNT(*) FILTER (WHERE success IS TRUE)::int        AS applied_7d,
                    AVG(outcome_pnl_24h)                                AS avg_outcome_24h
                FROM learning.directive_executions
                WHERE ts >= NOW() - INTERVAL '7 days'
                """
            )
            row = cur.fetchone()
            total_7d = int(row[0] or 0) if row else 0
            applied_7d = int(row[1] or 0) if row else 0
            avg_outcome_24h = float(row[2]) if row and row[2] is not None else None

            # Recent 5 directive executions
            # 最近 5 筆 directive 執行記錄
            cur.execute(
                """
                SELECT execution_id, ts, action_taken, success,
                       strategy_scope, outcome_pnl_24h
                FROM learning.directive_executions
                ORDER BY ts DESC
                LIMIT 5
                """
            )
            recent_rows = cur.fetchall()

    exec_rate = (applied_7d / total_7d) if total_7d > 0 else 0.0
    status_light = _classify_teacher_status(exec_rate, avg_outcome_24h)
    recent = [
        {
            "execution_id": r[0],
            "ts": r[1].isoformat() if r[1] is not None else None,
            "action_taken": r[2],
            "success": bool(r[3]),
            "strategy_scope": r[4],
            "outcome_pnl_24h": float(r[5]) if r[5] is not None else None,
        }
        for r in recent_rows
    ]

    return {
        "ok": True,
        "status_light": status_light,
        "total_7d": total_7d,
        "applied_7d": applied_7d,
        "exec_rate": round(exec_rate, 4),
        "avg_outcome_24h": avg_outcome_24h,
        "recent": recent,
        "last_update_ms": int(time.time() * 1000),
    }


@phase4_router.get("/teacher")
async def get_phase4_teacher() -> dict[str, Any]:
    """Teacher card data: 7d directive stats + recent executions + status light.
    Teacher 卡片資料：7d directive 統計 + 最近執行 + 狀態燈號。

    Fail-closed: any error → ok=false grey placeholder (never raises).
    """
    try:
        return _fetch_teacher_state_from_pg()
    except Exception as exc:
        logger.warning("phase4/teacher fail-soft: %s", exc)
        return _default_teacher_payload(reason=f"{type(exc).__name__}")


# ---------------------------------------------------------------------------
# 4-10 · News Card backend route
# 4-10 · News 卡片後端路由
# ---------------------------------------------------------------------------

# Known news provider names — kept in sync with rust/openclaw_engine/src/news/*.
# 已知的 news provider 名稱 — 與 rust/openclaw_engine/src/news/* 保持同步。
_NEWS_PROVIDER_NAMES = (
    "cryptopanic",
    "cointelegraph_rss",
    "google_news_rss",
    "mock",
)


def _default_news_providers_stub() -> list[dict[str, Any]]:
    """Build the 4-provider unknown-status stub.
    建立 4 個 provider 的 unknown 狀態 stub。

    Provider quota lives in Rust (not PG), so until 4-W4 wiring sweep we
    return status=unknown for all four. This keeps the GUI from lying about
    provider health. / provider quota 在 Rust 側（不在 PG），W4 wiring 完成前
    全部回報 unknown，避免 GUI 虛報健康。
    """
    return [
        {"name": name, "status": "unknown", "quota_remaining": None, "last_fetch": None}
        for name in _NEWS_PROVIDER_NAMES
    ]


def _default_news_payload(reason: str) -> dict[str, Any]:
    """Fail-closed payload for the News card.
    News 卡片的 fail-closed 預設 payload。
    """
    return {
        "ok": False,
        "reason": reason,
        "status_light": "grey",
        "total_24h": 0,
        "halt_triggers_24h": 0,
        "max_severity_24h": None,
        "recent": [],
        "providers": _default_news_providers_stub(),
        "last_update_ms": int(time.time() * 1000),
    }


def _classify_news_status(
    total_24h: int, halt_triggers_24h: int, max_severity_24h: float | None
) -> str:
    """Map news stats into a red/yellow/green status light.
    將新聞統計對映為 red/yellow/green 燈號。

    Rules / 規則:
        - max_severity_24h >= 0.95                 -> red   (極高風險新聞)
        - total_24h == 0                           -> yellow (無新聞，可能 provider 死)
        - otherwise (正常拉取中)                    -> green
    Note: halt_triggers_24h is surfaced via metrics but does not itself
    downgrade the light — halts are expected behavior when news is severe.
    註：halt_triggers_24h 只作為顯示指標，不會單獨降級燈號 — halt 是嚴重新聞
    下的預期行為。
    """
    if max_severity_24h is not None and max_severity_24h >= 0.95:
        return "red"
    if total_24h == 0:
        return "yellow"
    return "green"


def _fetch_news_state_from_pg() -> dict[str, Any]:  # pragma: no cover — live DB path
    """Read 24h market.news_signals stats + recent 10 rows from PG.
    從 PG 讀取 24h market.news_signals 統計 + 最近 10 條。

    Fail-soft: any exception → caller maps to grey placeholder.
    """
    import os

    try:
        import psycopg2  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"psycopg2_unavailable:{exc}") from exc

    dsn = os.environ.get("OPENCLAW_PG_DSN") or os.environ.get("PG_DSN")
    if not dsn:
        raise RuntimeError("no_dsn")

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # 24h aggregate stats / 24h 聚合統計
            # Column names confirmed against sql/migrations/V002__market_tables.sql:
            #   ts TIMESTAMPTZ / severity REAL (0..1) / source TEXT / summary TEXT / source_url TEXT
            cur.execute(
                """
                SELECT
                    COUNT(*)::int                                    AS total_24h,
                    COUNT(*) FILTER (WHERE severity >= 0.8)::int     AS halt_triggers_24h,
                    MAX(severity)                                    AS max_severity_24h
                FROM market.news_signals
                WHERE ts >= NOW() - INTERVAL '24 hours'
                """
            )
            row = cur.fetchone()
            total_24h = int(row[0] or 0) if row else 0
            halt_triggers_24h = int(row[1] or 0) if row else 0
            max_severity_24h = float(row[2]) if row and row[2] is not None else None

            # Recent 10 headlines / 最近 10 條
            cur.execute(
                """
                SELECT ts, source, severity, summary, source_url
                FROM market.news_signals
                ORDER BY ts DESC
                LIMIT 10
                """
            )
            recent_rows = cur.fetchall()

    status_light = _classify_news_status(total_24h, halt_triggers_24h, max_severity_24h)
    recent = [
        {
            "ts": r[0].isoformat() if r[0] is not None else None,
            "source": r[1],
            "severity": float(r[2]) if r[2] is not None else None,
            "summary": r[3],
            "source_url": r[4],
        }
        for r in recent_rows
    ]

    return {
        "ok": True,
        "status_light": status_light,
        "total_24h": total_24h,
        "halt_triggers_24h": halt_triggers_24h,
        "max_severity_24h": max_severity_24h,
        "recent": recent,
        # Provider health stub — real quota lives in Rust, wired in 4-W4.
        # Provider 健康 stub — 真實 quota 在 Rust，4-W4 wiring 階段接通。
        "providers": _default_news_providers_stub(),
        "last_update_ms": int(time.time() * 1000),
    }


@phase4_router.get("/news")
async def get_phase4_news() -> dict[str, Any]:
    """News card data: 24h news stats + recent 10 headlines + provider health.
    News 卡片資料：24h 新聞統計 + 最近 10 條 headline + provider 健康。

    Fail-closed: any error → ok=false grey placeholder (never raises).
    """
    try:
        return _fetch_news_state_from_pg()
    except Exception as exc:
        logger.warning("phase4/news fail-soft: %s", exc)
        return _default_news_payload(reason=f"{type(exc).__name__}")


# ---------------------------------------------------------------------------
# 4-14 · DL-3 Foundation Card backend route
# 4-14 · DL-3 基礎模型卡片後端路由
# ---------------------------------------------------------------------------

_KNOWN_DL3_MODEL_KEYS = ("chronos", "timesfm")


def _default_dl3_payload(reason: str) -> dict[str, Any]:
    """Fail-closed payload for the DL-3 card.
    DL-3 卡片的 fail-closed 預設 payload。
    """
    return {
        "ok": False,
        "reason": reason,
        "status_light": "grey",
        "latest_decision": None,
        "auc_delta": None,
        "models": {"chronos": None, "timesfm": None},
        "recent": [],
        "inference_24h": {"count": 0, "avg_latency_ms": None, "ok_rate": None},
        "last_update_ms": int(time.time() * 1000),
    }


def _classify_dl3_status(
    latest_decision: str | None,
    ok_rate: float | None,
) -> str:
    """Map Go/No-Go decision + 24h ok_rate into a red/yellow/green status light.
    將 Go/No-Go 決策 + 24h ok_rate 對映為紅/黃/綠燈號。

    Rules / 規則:
        - latest_decision == "NO_GO"                            -> red
        - latest_decision == "GO" AND (ok_rate None OR >= 1.0)  -> green
        - latest_decision == "GO" AND ok_rate < 1.0             -> yellow (degraded)
        - latest_decision == "PENDING_DATA"                     -> yellow
        - None / unknown                                        -> grey
    """
    if latest_decision == "NO_GO":
        return "red"
    if latest_decision == "GO":
        if ok_rate is None or ok_rate >= 1.0:
            return "green"
        return "yellow"
    if latest_decision == "PENDING_DATA":
        return "yellow"
    return "grey"


def _classify_dl3_model_availability(
    model_key: str, seen_models: set[str]
) -> bool | None:
    """Infer per-model availability from recently observed model names.
    由最近觀察到的 model 名稱推斷每個 model 的可用性。

    Substring match, case-insensitive: 'chronos-t5-tiny' matches key 'chronos'.
    Returns True if ever seen in window, None if never seen (unknown).
    子字串匹配（不分大小寫）；在窗口內看過回 True，沒看過回 None（unknown）。
    """
    key = model_key.lower()
    for m in seen_models:
        if m and key in m.lower():
            return True
    return None


def _fetch_dl3_state_from_pg() -> dict[str, Any]:  # pragma: no cover — live DB path
    """Read DL-3 inference state + latest Go/No-Go decision from PG.
    從 PG 讀取 DL-3 inference 狀態與最新 Go/No-Go 決策。

    Fail-soft: any exception → caller maps to grey placeholder.
    """
    import os

    try:
        import psycopg2  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"psycopg2_unavailable:{exc}") from exc

    dsn = os.environ.get("OPENCLAW_PG_DSN") or os.environ.get("PG_DSN")
    if not dsn:
        raise RuntimeError("no_dsn")

    latest_decision: str | None = "PENDING_DATA"
    auc_delta: float | None = None

    with psycopg2.connect(dsn) as conn:
        with conn.cursor() as cur:
            # Recent 5 inferences / 最近 5 筆推理（V011 schema）
            cur.execute(
                """
                SELECT time, symbol, model, horizon_min, latency_ms, ok, error_msg
                FROM learning.foundation_model_features
                ORDER BY time DESC
                LIMIT 5
                """
            )
            recent_rows = cur.fetchall()

            # 24h aggregate: count / avg_latency / ok_rate
            # 24h 聚合：筆數 / 平均延遲 / 成功率
            cur.execute(
                """
                SELECT
                    COUNT(*)::int                                      AS n,
                    AVG(latency_ms)                                    AS avg_latency,
                    AVG(CASE WHEN ok THEN 1.0 ELSE 0.0 END)            AS ok_rate
                FROM learning.foundation_model_features
                WHERE time >= NOW() - INTERVAL '24 hours'
                """
            )
            agg_row = cur.fetchone()
            count_24h = int(agg_row[0] or 0) if agg_row else 0
            avg_latency_24h = (
                float(agg_row[1]) if agg_row and agg_row[1] is not None else None
            )
            ok_rate_24h = (
                float(agg_row[2]) if agg_row and agg_row[2] is not None else None
            )

            # Distinct models observed in last 24h (for availability inference)
            # 最近 24h 觀察到的不重複 models（用於可用性推斷）
            cur.execute(
                """
                SELECT DISTINCT model
                FROM learning.foundation_model_features
                WHERE time >= NOW() - INTERVAL '24 hours'
                """
            )
            seen_models = {row[0] for row in cur.fetchall() if row and row[0]}

            # Latest Go/No-Go decision — table may not exist yet (fail-soft).
            # 最新 Go/No-Go 決策 — 表可能尚未存在（fail-soft）。
            try:
                cur.execute(
                    """
                    SELECT decision, auc_delta
                    FROM learning.dl3_ab_decisions
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
                dec_row = cur.fetchone()
                if dec_row:
                    latest_decision = dec_row[0]
                    auc_delta = (
                        float(dec_row[1]) if dec_row[1] is not None else None
                    )
            except Exception:
                # Table missing / schema drift — stub as PENDING_DATA.
                # 表不存在 / schema 漂移 — 退回 PENDING_DATA。
                conn.rollback()

    recent = [
        {
            "time": r[0].isoformat() if r[0] is not None else None,
            "symbol": r[1],
            "model": r[2],
            "horizon_min": int(r[3]) if r[3] is not None else None,
            "latency_ms": int(r[4]) if r[4] is not None else None,
            "ok": bool(r[5]),
            "error_msg": r[6],
        }
        for r in recent_rows
    ]

    models_avail = {
        key: _classify_dl3_model_availability(key, seen_models)
        for key in _KNOWN_DL3_MODEL_KEYS
    }

    status_light = _classify_dl3_status(latest_decision, ok_rate_24h)

    return {
        "ok": True,
        "status_light": status_light,
        "latest_decision": latest_decision,
        "auc_delta": auc_delta,
        "models": models_avail,
        "recent": recent,
        "inference_24h": {
            "count": count_24h,
            "avg_latency_ms": avg_latency_24h,
            "ok_rate": ok_rate_24h,
        },
        "last_update_ms": int(time.time() * 1000),
    }


@phase4_router.get("/dl3")
async def get_phase4_dl3() -> dict[str, Any]:
    """DL-3 card data: Go/No-Go decision + per-model availability + recent inferences.
    DL-3 卡片資料：Go/No-Go 決策 + 兩個 model 可用性 + 最近推理列表。

    Fail-closed: any error → ok=false grey placeholder (never raises).
    """
    try:
        return _fetch_dl3_state_from_pg()
    except Exception as exc:
        logger.warning("phase4/dl3 fail-soft: %s", exc)
        return _default_dl3_payload(reason=f"{type(exc).__name__}")


# ---------------------------------------------------------------------------
# 4-20 · Weekly review approval routes
# 4-20 · 週度審查批准路由
# ---------------------------------------------------------------------------


class WeeklyReviewApproveRequest(BaseModel):
    """Operator approve/reject payload for a Phase 4 weekly review row.
    Phase 4 週度審查 row 的 operator 批准/拒絕 payload。
    """

    week_iso: str = Field(..., min_length=1, max_length=16)
    approved_by: str = Field(..., min_length=1, max_length=128)
    decision_notes: str | None = Field(default=None, max_length=2000)


def _update_weekly_review(week_iso: str, approved: bool, approved_by: str, decision_notes: str | None) -> dict:
    """UPDATE learning.weekly_review_log row by week_iso. Fail-soft.
    依 week_iso 更新 learning.weekly_review_log row。fail-soft。

    Returns dict ok/error suitable for direct JSON response.
    返回適合直接 JSON 回應的 ok/error dict。
    """
    import os

    try:
        import psycopg2  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": f"psycopg2 unavailable: {exc}"}

    dsn = os.environ.get("OPENCLAW_PG_DSN") or os.environ.get("PG_DSN")
    if not dsn:
        return {"ok": False, "error": "no_dsn"}

    try:
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE learning.weekly_review_log
                    SET approved = %s,
                        approved_at = NOW(),
                        approved_by = %s,
                        decision_notes = %s
                    WHERE week_iso = %s AND approved IS NULL
                    RETURNING review_id
                    """,
                    (approved, approved_by, decision_notes, week_iso),
                )
                row = cur.fetchone()
                conn.commit()
                if row:
                    return {
                        "ok": True,
                        "review_id": int(row[0]),
                        "week_iso": week_iso,
                        "approved": approved,
                    }
                return {"ok": False, "error": "no_pending_review_for_week"}
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("phase4/weekly_review update fail-soft: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@phase4_router.post("/weekly_review/approve")
async def approve_weekly_review(payload: WeeklyReviewApproveRequest) -> dict[str, Any]:
    """Operator approves a pending weekly review row.
    Operator 批准 pending 的週度審查 row。
    """
    return _update_weekly_review(
        payload.week_iso, True, payload.approved_by, payload.decision_notes
    )


@phase4_router.post("/weekly_review/reject")
async def reject_weekly_review(payload: WeeklyReviewApproveRequest) -> dict[str, Any]:
    """Operator rejects a pending weekly review row.
    Operator 拒絕 pending 的週度審查 row。
    """
    return _update_weekly_review(
        payload.week_iso, False, payload.approved_by, payload.decision_notes
    )


@phase4_router.get("/weekly_review/latest")
async def get_latest_weekly_review() -> dict[str, Any]:
    """GET the most recent weekly review row regardless of approval state.
    取最近一筆週度審查 row，不分批准狀態。

    Fail-soft: any PG error → ok=false (never raises 5xx).
    """
    import os

    try:
        import psycopg2  # type: ignore
    except Exception as exc:
        return {"ok": False, "error": f"psycopg2 unavailable: {exc}", "review": None}

    dsn = os.environ.get("OPENCLAW_PG_DSN") or os.environ.get("PG_DSN")
    if not dsn:
        return {"ok": False, "error": "no_dsn", "review": None}

    try:
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT review_id, week_iso, generated_at, approved,
                           approved_at, approved_by, decision_notes,
                           metrics_json, report_md_path
                    FROM learning.weekly_review_log
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                if not row:
                    return {"ok": True, "review": None}
                return {
                    "ok": True,
                    "review": {
                        "review_id": int(row[0]),
                        "week_iso": row[1],
                        "generated_at": row[2].isoformat() if row[2] else None,
                        "approved": row[3],
                        "approved_at": row[4].isoformat() if row[4] else None,
                        "approved_by": row[5],
                        "decision_notes": row[6],
                        "metrics_json": row[7],
                        "report_md_path": row[8],
                    },
                }
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("phase4/weekly_review/latest fail-soft: %s", exc)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "review": None}


@phase4_router.get("", include_in_schema=False)
async def phase4_tab_redirect() -> RedirectResponse:
    """
    Convenience route — redirect /api/v1/phase4 to the static tab.
    便利路由 — 將 /api/v1/phase4 重定向至靜態 tab 頁面。
    """
    return RedirectResponse(url="/static/tab-phase4.html")
