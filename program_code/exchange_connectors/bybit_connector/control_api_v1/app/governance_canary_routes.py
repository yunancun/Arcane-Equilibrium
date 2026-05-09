"""
治理 Canary 路由 — Graduated Canary Stage GUI 後端端點（W-AUDIT-9 T5）。

模組目的：
  AMD-2026-05-09-03 §4.3 GUI surface 配套後端路由，提供 OpenClaw Control Console
  Governance tab「Graduated Canary Cohort Status」section 顯示 + manual promote
  按鈕所需的兩個端點：

    GET  /api/v1/governance/canary/cohorts
        列出 active cohorts 最新 stage（per cohort latest row）+ stage metric
        registry。read-only；不寫任何狀態。

    POST /api/v1/governance/canary/manual_promote
        operator-only 手動晉升 cohort stage（Stage N → Stage N+1）。
        必經：
          1. require_operator_role auth gate（FastAPI Depends）
          2. acquire LeaseScope::CanaryStagePromotion lease（TTL 60s strict per
             AMD §4.5；caller 不可覆寫）
          3. 寫入 governance.canary_stage_log row（transition_kind='manual_promote'，
             decision_lease_id NOT NULL）
          4. release lease（不論成功/失敗）
        per AMD-2026-05-09-03 §4.5 + §7 E2 audit point #2。

  Routes 註冊在 governance_routes.governance_router（沿用 governance_extended_routes
  pattern）— 不新建 prefix 避免 GUI fetch URL drift。

不變量（per AMD-2026-05-09-03）：
  - manual_promote 必伴隨非空 decision_lease_id（PG CHECK 強制 + 本路由強制）
  - acquire 失敗 → fail-closed 回 423 LOCKED，不寫 log
  - operator role 缺失 → 401/403（沿用 _require_operator_role）
  - cohort_id Stage 1/2 必為 'strategy:symbol:env'，Stage 0/3/4 必為 'global'
    （per V080 schema convention；本路由不額外校驗，由 PG CHECK + caller 自律）

E2 重點審查（per AMD §7 + memory feedback_v_migration_pg_dry_run）：
  #1 manual_promote PG CHECK constraint canary_stage_log_manual_promote_lease_required_chk
     由 V080 強制；應用層也守此 invariant（本檔 _validate_manual_promote_payload）
  #2 lease acquire 走 governance_lease_bridge（IPC 啟用時）+ PA push back #2
     SHADOW_BYPASS short-circuit；caller 看到 SHADOW_BYPASS:* sentinel 必拒絕寫
     manual_promote row（shadow 不算真授權鏈）。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from .governance_routes import (
    GovernanceResponse,
    _get_auth_actor,
    _require_operator_role,
    governance_router,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常數
# ═══════════════════════════════════════════════════════════════════════════════

# AMD-2026-05-09-03 §4.5：CanaryStagePromotion lease TTL 60s strict
# caller 不可覆寫，避免 silent drift
_CANARY_PROMOTION_LEASE_TTL_SECONDS = 60.0

# AMD-2026-05-09-03 §4.5：lease scope 字面值（與 Rust LeaseScope::CanaryStagePromotion
# audit_str 對齊；governance_hub.acquire_lease 接受 &str 故傳字串）
_LEASE_SCOPE_CANARY_PROMOTION = "CanaryStagePromotion"

# Stage 範圍（per AMD §2.2 5-stage 表）
_VALID_STAGES = (0, 1, 2, 3, 4)

# transition_kind 常數（與 V080 CHECK constraint 對齊）
_TRANSITION_MANUAL_PROMOTE = "manual_promote"


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response 模型
# ═══════════════════════════════════════════════════════════════════════════════

class CanaryManualPromoteRequest(BaseModel):
    """
    手動晉升 cohort stage 的請求 body。

    cohort_id 規格 per V080 schema convention：
      Stage 1/2：'<strategy>:<symbol>:<environment>'（例如 'grid:BTCUSDT:demo'）
      Stage 0/3/4：'global'

    from_stage / to_stage 必為相鄰 stage（晉升只能 +1，不可跳階；rollback 不
    走本端點走 auto_rollback / incident_rollback）。
    """
    cohort_id: str = Field(..., min_length=1, max_length=200, description="Cohort identifier")
    from_stage: int = Field(..., ge=0, le=4, description="當前 stage（0..=4）")
    to_stage: int = Field(..., ge=0, le=4, description="目標 stage（0..=4）")
    reason: str = Field(..., min_length=1, max_length=500, description="operator 晉升理由")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助函式
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_manual_promote_payload(body: CanaryManualPromoteRequest) -> None:
    """
    校驗 manual_promote 請求體。
    違反 invariant 拋 HTTPException(400)。

    校驗規則：
      1. from_stage / to_stage 必為相鄰且 to_stage = from_stage + 1
         （per AMD §2.2 stage 必逐級晉升；跳級需 operator 顯式拍板新 cohort
         不走本端點）
      2. to_stage 不可為 4（Stage 4 = LIVE_PENDING，per AMD §3.3 + §2.2 必走
         5-gate live boundary，不走 graduated canary 自動 / 手動晉升路徑）
      3. cohort_id 字串不為空（Pydantic 已校驗）
    """
    if body.to_stage != body.from_stage + 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"manual_promote 必為相鄰 stage 晉升（from={body.from_stage} → "
                f"to={body.to_stage}）；跳階或退級不走本端點。per AMD-2026-05-09-03 §2.2。"
            ),
        )
    if body.to_stage == 4:
        raise HTTPException(
            status_code=400,
            detail=(
                "Stage 4 = LIVE_PENDING 不走 graduated canary 自動/手動晉升；"
                "必經 5-gate live boundary（CLAUDE.md §四 line 125-136）。"
            ),
        )


def _is_shadow_bypass_lease(lease_id: str | None) -> bool:
    """
    判斷 lease_id 是否為 SHADOW_BYPASS sentinel（per governance_hub.acquire_lease
    PA push back #2 short-circuit）。

    SHADOW_BYPASS sentinel 不算真授權鏈：caller 看到此 sentinel 必拒絕寫
    canary_stage_log manual_promote row，per AMD §4.5 + V080 PG CHECK
    canary_stage_log_manual_promote_lease_required_chk（NOT NULL）+ E2 audit
    point #2 SHADOW_BYPASS 不應通過真 audit chain。
    """
    return isinstance(lease_id, str) and lease_id.startswith("SHADOW_BYPASS:")


def _write_canary_stage_log_manual_promote(
    cohort_id: str,
    from_stage: int,
    to_stage: int,
    decision_lease_id: str,
    reason: str,
) -> int | None:
    """
    寫入 governance.canary_stage_log 一筆 manual_promote row。

    Args:
        cohort_id: cohort 識別字串（per V080 schema convention）
        from_stage / to_stage: 起始 / 目的 stage（0..=4）
        decision_lease_id: 已 acquired 的 lease_id（UUID 字串；NOT NULL，per V080
            CHECK constraint canary_stage_log_manual_promote_lease_required_chk）
        reason: operator 晉升理由（寫入 description；schema 無 reason 欄位故附在
            triggered_metric 名稱前綴）

    Returns:
        新 row 的 stage_log_id；失敗回 None（caller 必 fail-closed）

    Note:
        decision_lease_id 必為合法 UUID 字串（PG schema column 是 UUID type）。
        SHADOW_BYPASS sentinel 不可進入此函式（caller 必先檢查）。
    """
    try:
        from .db_pool import get_pg_conn
    except ImportError:
        logger.error("db_pool unavailable; cannot write canary_stage_log row")
        return None

    # decision_lease_id 必為合法 UUID（V080 column type 是 UUID NULL）
    # SHADOW_BYPASS sentinel 由 caller 過濾，理論上不會到此；保險仍校驗。
    try:
        lease_uuid = uuid.UUID(decision_lease_id)
    except (ValueError, TypeError):
        logger.error(
            "decision_lease_id 非合法 UUID 字串，拒寫 canary_stage_log row: %s",
            decision_lease_id,
        )
        return None

    created_at_ms = int(time.time() * 1000)
    # AMD §4.2 + V080 schema：manual_promote 的 triggered_metric 通常 NULL，
    # 但保留 reason 上下文寫 description（schema 無 reason column；用前綴標記）
    triggered_metric = f"manual_promote:{reason[:200]}"

    try:
        with get_pg_conn() as conn:
            if conn is None:
                logger.error("PG connection unavailable; cannot write canary_stage_log row")
                return None
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO governance.canary_stage_log (
                        cohort_id,
                        from_stage,
                        to_stage,
                        transition_kind,
                        decision_lease_id,
                        triggered_metric,
                        triggered_value,
                        created_at_ms
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING stage_log_id
                    """,
                    (
                        cohort_id,
                        from_stage,
                        to_stage,
                        _TRANSITION_MANUAL_PROMOTE,
                        str(lease_uuid),
                        triggered_metric,
                        None,  # triggered_value：manual_promote 無 metric 取值
                        created_at_ms,
                    ),
                )
                row = cur.fetchone()
                conn.commit()
                if row is None:
                    return None
                return int(row[0])
    except Exception as exc:  # noqa: BLE001（DB write 故意 catch all 為 fail-closed）
        logger.error("寫入 canary_stage_log row 失敗: %s", exc)
        return None


def _query_active_cohorts() -> list[dict[str, Any]]:
    """
    讀 governance.canary_stage_log latest row per cohort，回傳 active cohorts
    的當前 stage state。

    Returns:
        list of dicts:
          - cohort_id: str
          - current_stage: int (0..=4)
          - stage_entered_at_ms: int (latest transition created_at_ms)
          - last_transition_kind: str
          - last_decision_lease_id: str | None
        若 PG 不可用回空 list（GUI fail-soft 顯示「資料載入失敗」）

    Note:
        DISTINCT ON (cohort_id) 取每 cohort 最新 row（per V080 idx_canary_stage_log
        _cohort_created_at hot path）。
    """
    try:
        from .db_pool import get_pg_conn
    except ImportError:
        return []

    try:
        with get_pg_conn() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                # to_regclass 守護：表不存在回空（V080 未 apply 場景）
                cur.execute("SELECT to_regclass('governance.canary_stage_log') IS NOT NULL")
                exists_row = cur.fetchone()
                if not exists_row or not exists_row[0]:
                    return []

                cur.execute(
                    """
                    SELECT DISTINCT ON (cohort_id)
                        cohort_id,
                        to_stage,
                        created_at_ms,
                        transition_kind,
                        decision_lease_id
                    FROM governance.canary_stage_log
                    ORDER BY cohort_id, created_at_ms DESC
                    """
                )
                rows = cur.fetchall() or []
                result = []
                for row in rows:
                    result.append({
                        "cohort_id": str(row[0]) if row[0] else "global",
                        "current_stage": int(row[1]) if row[1] is not None else 0,
                        "stage_entered_at_ms": int(row[2]) if row[2] is not None else 0,
                        "last_transition_kind": str(row[3]) if row[3] else "unknown",
                        "last_decision_lease_id": str(row[4]) if row[4] else None,
                    })
                return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("查詢 active cohorts 失敗: %s", exc)
        return []


def _query_metric_registry() -> list[dict[str, Any]]:
    """
    讀 governance.canary_stage_metric_registry 全部 active row，按 stage 排序。

    Returns:
        list of dicts: stage / metric_name / direction / threshold_value /
        observation_window_ms / description（per V080 schema columns）
        若表不存在 / PG 不可用回空 list。
    """
    try:
        from .db_pool import get_pg_conn
    except ImportError:
        return []

    try:
        with get_pg_conn() as conn:
            if conn is None:
                return []
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('governance.canary_stage_metric_registry') IS NOT NULL")
                exists_row = cur.fetchone()
                if not exists_row or not exists_row[0]:
                    return []

                cur.execute(
                    """
                    SELECT
                        stage,
                        metric_name,
                        direction,
                        threshold_value,
                        observation_window_ms,
                        description
                    FROM governance.canary_stage_metric_registry
                    WHERE active = TRUE
                    ORDER BY stage ASC, metric_name ASC
                    """
                )
                rows = cur.fetchall() or []
                result = []
                for row in rows:
                    threshold = row[3]
                    # PG NUMERIC → Python Decimal，需 float 化才可序列化 JSON
                    try:
                        threshold_val = float(threshold) if threshold is not None else None
                    except (TypeError, ValueError):
                        threshold_val = None
                    result.append({
                        "stage": int(row[0]) if row[0] is not None else 0,
                        "metric_name": str(row[1]) if row[1] else "",
                        "direction": str(row[2]) if row[2] else "",
                        "threshold_value": threshold_val,
                        "observation_window_ms": int(row[4]) if row[4] is not None else 0,
                        "description": str(row[5]) if row[5] else "",
                    })
                return result
    except Exception as exc:  # noqa: BLE001
        logger.warning("查詢 metric_registry 失敗: %s", exc)
        return []


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

@governance_router.get("/canary/cohorts")
def get_canary_cohorts() -> dict[str, Any]:
    """
    GET /api/v1/governance/canary/cohorts
    讀取 active cohorts + metric registry，供 GUI Graduated Canary section 顯示。

    Read-only；不需 operator auth（治理觀察面與 SM-01..04 dashboard 一致）。
    """
    cohorts = _query_active_cohorts()
    metrics = _query_metric_registry()

    payload = {
        "cohorts": cohorts,
        "metric_registry": metrics,
        "stages": [
            {"stage": 0, "label": "Stage 0 / Shadow", "scope": "shadow only"},
            {"stage": 1, "label": "Stage 1 / Paper", "scope": "1 strategy x 1 symbol x paper x 7d"},
            {"stage": 2, "label": "Stage 2 / Demo single", "scope": "1 strategy x 1 symbol x demo x 14d"},
            {"stage": 3, "label": "Stage 3 / Demo full", "scope": "5 strategies x demo x 21d"},
            {"stage": 4, "label": "Stage 4 / LIVE_PENDING", "scope": "operator-pinned；不自動晉升"},
        ],
        "now_ms": int(time.time() * 1000),
    }
    return GovernanceResponse.success(data=payload, message="canary_cohorts_status")


@governance_router.post("/canary/manual_promote")
def post_canary_manual_promote(
    body: CanaryManualPromoteRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    POST /api/v1/governance/canary/manual_promote
    Operator 手動晉升 cohort stage（Stage N → Stage N+1，N ∈ {0,1,2}）。

    必經 5 步：
      1. require_operator_role auth gate（拒非 operator 401/403）
      2. _validate_manual_promote_payload（晉升相鄰 + 不可進 Stage 4）
      3. acquire LeaseScope::CanaryStagePromotion lease（TTL 60s strict）
         - SHADOW_BYPASS sentinel 拒（不算真授權鏈）
         - acquire 失敗回 423 LOCKED
      4. 寫 governance.canary_stage_log row（transition_kind='manual_promote'）
         - 寫失敗 → release lease + 回 500
      5. release lease（不論成功/失敗）

    per AMD-2026-05-09-03 §4.5（lease scope 60s）+ §7 E2 audit point #2
    （manual_promote PG NOT NULL constraint）。
    """
    # Step 1: operator role 校驗
    _require_operator_role(actor)

    # Step 2: payload 校驗
    _validate_manual_promote_payload(body)

    # Step 3: acquire LeaseScope::CanaryStagePromotion lease
    # governance_hub.acquire_lease 接受 &str scope；TTL 60s strict per AMD §4.5
    try:
        from .paper_trading_routes import GOV_HUB as _GOV_HUB
    except ImportError:
        _GOV_HUB = None

    if _GOV_HUB is None:
        logger.error("GovernanceHub 不可用；無法 acquire CanaryStagePromotion lease")
        raise HTTPException(
            status_code=503,
            detail="Governance hub unavailable",
        )

    # intent_id 用唯一識別；前綴 'canary-promote-' 便於 audit 篩選
    intent_id = f"canary-promote-{body.cohort_id}-{int(time.time() * 1000)}"
    lease_id = _GOV_HUB.acquire_lease(
        intent_id=intent_id,
        scope=_LEASE_SCOPE_CANARY_PROMOTION,
        ttl_seconds=_CANARY_PROMOTION_LEASE_TTL_SECONDS,
    )

    if lease_id is None:
        logger.warning(
            "acquire CanaryStagePromotion lease 失敗 cohort=%s actor=%s",
            body.cohort_id,
            getattr(actor, "actor_id", "?"),
        )
        raise HTTPException(
            status_code=423,
            detail=(
                "acquire CanaryStagePromotion lease 失敗（governance_hub deny / "
                "shadow / IPC 失敗）；不寫 manual_promote audit row。per AMD §4.5。"
            ),
        )

    # SHADOW_BYPASS sentinel 拒：不算真授權鏈，per AMD §4.5 + V080 NOT NULL constraint
    if _is_shadow_bypass_lease(lease_id):
        logger.warning(
            "CanaryStagePromotion 收到 SHADOW_BYPASS sentinel；拒寫 manual_promote "
            "audit row。lease_id=%s cohort=%s",
            lease_id,
            body.cohort_id,
        )
        # SHADOW_BYPASS sentinel 不需 release（per governance_hub.release_lease 慣例）
        raise HTTPException(
            status_code=409,
            detail=(
                "CanaryStagePromotion 不接受 SHADOW_BYPASS lease；shadow_mode_provider "
                "回 True 表示系統 fail-closed 至 Stage 0，不應走 manual_promote 路徑。"
            ),
        )

    # Step 4: 寫 audit log row
    stage_log_id = _write_canary_stage_log_manual_promote(
        cohort_id=body.cohort_id,
        from_stage=body.from_stage,
        to_stage=body.to_stage,
        decision_lease_id=lease_id,
        reason=body.reason,
    )

    # Step 5: release lease（不論寫 row 成功失敗都釋放，TTL 60s 也會自動 expire）
    try:
        _GOV_HUB.release_lease(lease_id, consumed=True)
    except Exception as exc:  # noqa: BLE001
        # release 失敗不阻塞回應，TTL 自動 expire；只 warn log
        logger.warning("release CanaryStagePromotion lease %s 失敗: %s", lease_id, exc)

    if stage_log_id is None:
        logger.error(
            "寫 canary_stage_log manual_promote row 失敗；lease 已 release。"
            "cohort=%s actor=%s",
            body.cohort_id,
            getattr(actor, "actor_id", "?"),
        )
        raise HTTPException(
            status_code=500,
            detail="寫入 canary_stage_log row 失敗（DB unavailable / schema drift）",
        )

    logger.info(
        "manual_promote 完成 cohort=%s %d→%d stage_log_id=%d actor=%s lease=%s",
        body.cohort_id,
        body.from_stage,
        body.to_stage,
        stage_log_id,
        getattr(actor, "actor_id", "?"),
        lease_id,
    )

    return GovernanceResponse.success(
        data={
            "stage_log_id": stage_log_id,
            "cohort_id": body.cohort_id,
            "from_stage": body.from_stage,
            "to_stage": body.to_stage,
            "decision_lease_id": lease_id,
            "transition_kind": _TRANSITION_MANUAL_PROMOTE,
        },
        message="canary_manual_promote_completed",
    )
