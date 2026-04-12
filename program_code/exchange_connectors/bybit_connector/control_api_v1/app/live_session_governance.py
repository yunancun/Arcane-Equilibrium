"""
Live Session Governance Helpers — GovernanceHub SM-1 authorization lifecycle for live sessions.
實��� Session 治理輔助 — GovernanceHub SM-1 授權生命週期管理。

MODULE_NOTE (EN): Extracted from live_session_routes.py (FIX-08 file size).
  Functions for submitting, freezing, and revoking live-mode SM-1 authorizations
  via GovernanceHub. All fail-soft: errors logged but never block session flow.
MODULE_NOTE (中): 從 live_session_routes.py 提取（FIX-08 文件大小）。
  透過 GovernanceHub 提交、凍結、撤銷 live 模式 SM-1 授權的函數。
  全部 fail-soft：錯誤僅記錄，絕不阻塞 session 流程。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _get_hub():
    """Lazy import GovernanceHub singleton. / 延遲導入 GovernanceHub 單例。"""
    try:
        from .paper_trading_routes import GOV_HUB
        return GOV_HUB
    except (ImportError, AttributeError):
        return None


def _freeze_live_governance_auth(reason: str = "auto_halt_drawdown") -> None:
    """
    Freeze the live-scoped GovernanceHub authorization after auto-halt.
    Creates an audit record showing why the session was stopped.
    在自動停止後凍結 GovernanceHub 中 mode=live 的授權，生成審計記錄。
    """
    try:
        hub = _get_hub()
        if hub is None:
            return
        auth_sm = getattr(hub, "_authorization_sm", None)
        if auth_sm is None:
            return
        effective = auth_sm.get_effective()
        for auth in effective:
            scope = getattr(auth, "scope", {}) or {}
            if isinstance(scope, dict) and scope.get("mode") == "live":
                auth_sm.freeze(auth.authorization_id, reason)
                logger.info(
                    "GovernanceHub live authorization frozen (id=%s reason=%s) / "
                    "實盤 GovernanceHub 授權已凍結（id=%s reason=%s）",
                    auth.authorization_id, reason,
                    auth.authorization_id, reason,
                )
    except Exception as exc:
        logger.warning(
            "Failed to freeze live governance auth (non-fatal): %s / "
            "凍結實盤治理授權失敗（非致命）: %s", exc, exc,
        )


def _submit_live_governance_request(actor_id: str) -> None:
    """
    Create and auto-approve a live-mode SM-1 authorization in GovernanceHub (non-blocking).
    The Operator role + live_reserved global mode gate IS the approval gate — no separate
    manual SM-1 approval step is required for live.
    Failure is logged as warning but never blocks live session start.

    在 GovernanceHub 創建並自動批准 live 模式 SM-1 授權（非阻塞）。
    Operator 角色 + live_reserved 全局模式門控已是批准門控，無需額外手動批准步驟。
    失敗僅警告，不阻塞 session 啟動。
    """
    try:
        hub = _get_hub()
        if hub is None or not getattr(hub, "_initialized", False):
            logger.debug("GovernanceHub not ready — skipping live governance request")
            return
        auth_sm = getattr(hub, "_authorization_sm", None)
        if auth_sm is None:
            logger.debug("GovernanceHub._authorization_sm not available")
            return
        import time as _time
        live_scope = {
            "mode": "live",
            "execution": ["live_submit", "paper_submit"],
            "approved_by": actor_id,
        }
        expires_at_ms = int((_time.time() + 24 * 3600) * 1000)  # 24h TTL / 24小時有效期
        auth_obj = auth_sm.create_draft(
            title=f"Live Session Authorization — {actor_id}",
            scope=live_scope,
            created_by=actor_id,
            description=(
                f"Live session authorized by operator '{actor_id}' "
                "(Operator role + live_reserved mode gate). / "
                f"實盤 session 由 Operator '{actor_id}' 授權"
                "（Operator 角色 + live_reserved 模式雙重門控）。"
            ),
            expires_at_ms=expires_at_ms,
        )
        auth_id = auth_obj.authorization_id
        # DRAFT → PENDING_APPROVAL → ACTIVE: Operator role gate IS the approval.
        # DRAFT → PENDING_APPROVAL → ACTIVE：Operator 角色門控即為批准。
        auth_sm.submit_for_approval(auth_id)
        auth_sm.approve(
            auth_id,
            approved_by=actor_id,
            reason=(
                "Auto-approved: operator explicitly started live session with "
                "Operator role + live_reserved mode. / "
                "自動批准：Operator 角色 + live_reserved 模式雙重驗證後顯式啟動實盤。"
            ),
        )
        # Invalidate GovernanceHub auth cache so is_authorized() picks up the new ACTIVE auth.
        # 使 GovernanceHub 授權快取失效，讓 is_authorized() 立即感知新 ACTIVE 授權。
        _invalidate_fn = getattr(hub, "_invalidate_auth_cache", None)
        if _invalidate_fn is not None:
            _invalidate_fn()
        logger.warning(
            "⚠ Live SM-1 authorization ACTIVE (id=%s actor=%s) — "
            "real funds at risk / 實盤 SM-1 授權已激活（id=%s actor=%s）— 真實資金",
            auth_id, actor_id, auth_id, actor_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to submit live governance request (non-fatal): %s / "
            "提交實盤治理申請失敗（非致命）: %s", exc, exc,
        )


def _revoke_live_governance_auth(reason: str = "live_session_stopped", actor_id: str = "system") -> None:
    """Revoke all live SM-1 auths (session stop / authority revoke / emergency). / 撤銷所有 live SM-1 授權。"""
    try:
        hub = _get_hub()
        if hub is None:
            return
        auth_sm = getattr(hub, "_authorization_sm", None)
        if auth_sm is None:
            return
        # Find all effective live-scoped authorizations and revoke them.
        # 找到所有有效的 live 模式授權並撤銷。
        try:
            all_auths = auth_sm.list_all()
        except Exception:
            all_auths = auth_sm.get_effective()
        revoked = 0
        for auth in all_auths:
            scope = getattr(auth, "scope", {}) or {}
            state = getattr(auth, "state", None)
            state_val = state.value if state is not None else ""
            if (
                isinstance(scope, dict)
                and scope.get("mode") == "live"
                and state_val in ("ACTIVE", "RESTRICTED", "PENDING_APPROVAL", "DRAFT")
            ):
                try:
                    auth_sm.revoke(
                        auth.authorization_id,
                        approved_by=actor_id,
                        reason=reason,
                    )
                    revoked += 1
                except Exception as inner:
                    logger.debug("Could not revoke live auth %s: %s", auth.authorization_id, inner)
        # Invalidate cache after revoking.
        # 撤銷後使快取失效。
        _invalidate_fn = getattr(hub, "_invalidate_auth_cache", None)
        if _invalidate_fn is not None:
            _invalidate_fn()
        if revoked:
            logger.warning(
                "Live SM-1 authorization(s) REVOKED (count=%d reason=%s actor=%s) / "
                "實盤 SM-1 授權已撤銷（數量=%d reason=%s actor=%s）",
                revoked, reason, actor_id, revoked, reason, actor_id,
            )
    except Exception as exc:
        logger.warning(
            "Failed to revoke live governance auth (non-fatal): %s / "
            "撤銷實盤治理授權失敗（非致命）: %s", exc, exc,
        )
