from __future__ import annotations

"""
MODULE_NOTE (中文):
  System / Health legacy 路由（E5-P0-5 拆分自 legacy_routes.py）。
  包含 13 條只讀路由：
    GET /api/v1/system/overview           — 系統總覽
    GET /api/v1/system/chapter-status     — 章節狀態
    GET /api/v1/system/control-plane      — 控制平面
    GET /api/v1/system/capability-matrix  — 能力矩陣
    GET /api/v1/system/product-families   — 產品族狀態
    GET /api/v1/system/business/daily     — 當日經營指標
    GET /api/v1/system/business/summary   — 完整經營與收益摘要
    GET /api/v1/system/health             — 健康遙測（需 auth，完整 snapshot）
    GET /api/v1/system/grafana-health     — Grafana 健康代理
    GET /api/v1/system/audit-summary      — 審計摘要
    GET /api/v1/system/source-context     — 資料源上下文
    GET /api/v1/health/db                 — PostgreSQL 連接池健康檢查
    GET /api/v1/healthz                   — 輕量 liveness probe（無 auth，監控用）

  ★ Monkey-patch 安全：所有 request-time 呼叫透過 `_base.xxx(...)` 取值，不可
    在模組 top-level 捕獲 STORE / envelope_response / get_latest_snapshot。

MODULE_NOTE (English):
  System / Health read-only legacy routes (split out of legacy_routes.py in E5-P0-5).
  Contains 12 routes covering system overview, chapter status, control plane,
  capability matrix, product families, business metrics, health telemetry,
  Grafana proxy, audit summary, source context, and DB pool health probe.

  ★ Monkey-patch safety: all patched symbols resolved via `_base.xxx(...)` at
    request time. No module-level capture of STORE/envelope_response/get_latest_snapshot.
"""

from typing import Any

from fastapi import Depends

from .control_ops import build_overview
from .pnl_ops import build_business_summary
from .state_models import (
    BusinessSummaryData,
    OverviewData,
    ResponseEnvelope,
)


def register_system_legacy_routes(app) -> None:
    """
    Register all system / health legacy routes on the FastAPI app.
    在 FastAPI app 上註冊所有 system / health legacy 路由。
    """
    from . import main_legacy as _base
    settings = _base.settings

    @app.get(
        f"{settings.api_prefix}/system/overview",
        response_model=ResponseEnvelope[OverviewData],
    )
    def get_system_overview(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[OverviewData]:
        """System overview / 系統總覽."""
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=OverviewData(**build_overview(snapshot)),
        )

    @app.get(
        f"{settings.api_prefix}/system/chapter-status",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_chapter_status(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Chapter status view / 章節狀態視圖."""
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=snapshot["chapter_status"],
        )

    @app.get(
        f"{settings.api_prefix}/system/control-plane",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_control_plane(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Control-plane state view / 控制平面狀態視圖."""
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=snapshot["control_plane"],
        )

    @app.get(
        f"{settings.api_prefix}/system/capability-matrix",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_capability_matrix(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Capability matrix view / 能力矩陣視圖."""
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=snapshot["capability_matrix"],
        )

    @app.get(
        f"{settings.api_prefix}/system/product-families",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_product_families(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Product family status view / 產品族狀態視圖."""
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=snapshot["product_family_status"],
        )

    @app.get(
        f"{settings.api_prefix}/system/business/daily",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_business_daily(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Daily business metrics view / 當日經營指標視圖."""
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=snapshot["business_metrics"]["daily"],
        )

    @app.get(
        f"{settings.api_prefix}/system/health",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_health(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Health telemetry view / 健康遙測視圖."""
        snapshot, _ = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=snapshot["health_telemetry"],
        )

    @app.get(
        f"{settings.api_prefix}/system/grafana-health",
        include_in_schema=False,
    )
    async def grafana_health_proxy(actor=Depends(_base.current_actor)):
        """
        Proxy Grafana health check to avoid browser CORS block.
        代理 Grafana 健康檢查，避免瀏覽器 CORS 攔截。
        """
        import asyncio

        try:
            def _check():
                import json
                import urllib.request
                with urllib.request.urlopen(
                    "http://localhost:3000/api/health", timeout=3
                ) as resp:
                    return json.loads(resp.read().decode())

            data = await asyncio.to_thread(_check)
            return {
                "action_result": "success",
                "data": {"ok": True, "version": data.get("version", "?")},
            }
        except Exception:
            return {"action_result": "success", "data": {"ok": False}}

    @app.get(
        f"{settings.api_prefix}/health/db",
        include_in_schema=False,
    )
    def health_db(actor=Depends(_base.current_actor)):
        """
        PostgreSQL connection pool health check.
        PostgreSQL 連接池健康檢查。

        Authenticated detailed probe; public callers should use /api/v1/healthz.
        已認證詳細探測；公開 liveness 請使用 /api/v1/healthz。
        """
        from . import db_pool

        stats = db_pool.pool_stats()
        if not stats.get("available"):
            return {"ok": False, "pool": stats}
        conn = db_pool.get_conn()
        if conn is None:
            return {"ok": False, "pool": stats, "probe": "getconn_failed"}
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return {"ok": True, "pool": stats}
        except Exception as exc:
            _base.logger.warning("health_db probe failed: %s", exc)
            return {"ok": False, "pool": stats, "probe": "probe_failed"}
        finally:
            db_pool.put_conn(conn)

    @app.get(
        f"{settings.api_prefix}/healthz",
        include_in_schema=False,
    )
    def healthz():
        """
        Lightweight liveness probe for monitoring scripts / external probes.
        輕量存活探測，供監控腳本/外部探針使用。

        Intentionally unauthenticated and dependency-free: returns 200 + minimal
        payload as long as the FastAPI app is alive and serving requests.
        Use /api/v1/system/health (auth required) for richer telemetry, or
        /api/v1/health/db for DB pool probe.
        故意不需 auth 也不依賴下游元件：只要 FastAPI 服務在跑就回 200。
        如需更完整遙測請打 /api/v1/system/health（需登入），DB 連線探針請打
        /api/v1/health/db。
        """
        import time as _time

        return {
            "status": "ok",
            "api_version": settings.api_version,
            "schema_version": settings.schema_version,
            "ts_ms": int(_time.time() * 1000),
        }

    @app.get(
        f"{settings.api_prefix}/system/audit-summary",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_audit_summary(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Audit summary view (last control action + last write action) / 審計摘要視圖."""
        snapshot, _ = _base.get_latest_snapshot()
        data = {
            "latest_control_action_summary": {
                "type": snapshot["audit_context"]["last_control_action_type"],
                "request_id": snapshot["audit_context"]["last_control_action_request_id"],
                "ts_ms": snapshot["audit_context"]["last_control_action_ts_ms"],
                "by": snapshot["audit_context"]["last_control_action_by"],
                "result": snapshot["audit_context"]["last_control_action_result"],
                "reason_codes": snapshot["audit_context"]["last_control_action_reason_codes"],
                "audit_ref": snapshot["audit_context"]["last_control_action_audit_ref"],
            },
            "latest_write_action_summary": {
                "type": snapshot["audit_context"]["last_write_action_type"],
                "request_id": snapshot["audit_context"]["last_write_action_request_id"],
                "ts_ms": snapshot["audit_context"]["last_write_action_ts_ms"],
                "by": snapshot["audit_context"]["last_write_action_by"],
                "result": snapshot["audit_context"]["last_write_action_result"],
                "reason_codes": snapshot["audit_context"]["last_write_action_reason_codes"],
                "audit_ref": snapshot["audit_context"]["last_write_action_audit_ref"],
            },
            "last_state_revision_before": snapshot["audit_context"]["last_state_revision_before"],
            "last_state_revision_after": snapshot["audit_context"]["last_state_revision_after"],
        }
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=data,
        )

    @app.get(
        f"{settings.api_prefix}/system/source-context",
        response_model=ResponseEnvelope[dict[str, Any]],
    )
    def get_source_context(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[dict[str, Any]]:
        """Raw source context view / 原始資料源上下文視圖."""
        snapshot, source = _base.get_latest_snapshot()
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=source.model_dump(mode="json"),
        )

    @app.get(
        f"{settings.api_prefix}/system/business/summary",
        response_model=ResponseEnvelope[BusinessSummaryData],
    )
    def get_business_summary(
        actor=Depends(_base.current_actor),
    ) -> ResponseEnvelope[BusinessSummaryData]:
        """
        Complete business and income summary.
        完整經營與收益摘要。

        Richer than /system/business/daily: includes entry history and
        category-level cost breakdown.
        比 /system/business/daily 更完整：包含歷史條目列表和按類別成本分解。
        """
        snapshot, _ = _base.get_latest_snapshot()
        summary = build_business_summary(snapshot)
        return _base.envelope_response(
            snapshot=snapshot,
            request_id=None,
            action_result="success",
            data=BusinessSummaryData(**summary),
        )


__all__ = ["register_system_legacy_routes"]
