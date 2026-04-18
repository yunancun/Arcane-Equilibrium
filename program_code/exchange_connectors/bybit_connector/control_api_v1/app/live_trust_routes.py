# MODULE_NOTE (English):
#   Live Trust Routes — REST API endpoints for the Earned-Trust TTL ladder.
#   Separated from live_session_routes.py to keep that file under the 1200-line limit.
#
#   Endpoints:
#     GET  /api/v1/live/auth/trust-status  — current tier, metrics, renewal recommendation
#     POST /api/v1/live/auth/renew         — Operator confirms renewal at recommended (or chosen) tier
#     POST /api/v1/live/auth/renew-review  — Operator completes mandatory T3 full review + renew
#
# MODULE_NOTE (中文):
#   實盤信任路由 — 贏得信任 TTL 階梯的 REST API 端點。
#   從 live_session_routes.py 分離以保持該文件在 1200 行限制內。
#
#   端點：
#     GET  /api/v1/live/auth/trust-status  — 當前 tier、指標、續期建議
#     POST /api/v1/live/auth/renew         — Operator 確認以建議（或選擇）tier 續期
#     POST /api/v1/live/auth/renew-review  — Operator 完成強制 T3 全面審查後續期

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import stat
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from . import main_legacy as base
from .earned_trust_engine import (
    TIER_NAMES,
    TIER_TTL_HOURS,
    TrustMetrics,
    TrustTier,
    get_trust_engine,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# LIVE-GATE-BINDING-1: signed authorization file for Rust engine
# LIVE-GATE-BINDING-1：給 Rust 引擎消費的簽名授權檔
# ─────────────────────────────────────────────────────────────────────────────
#
# Rust refuses to spawn the Live pipeline unless this file exists, parses,
# verifies HMAC, is not expired, and whitelists the current bybit_endpoint.
# The canonical payload layout MUST match
# `rust/openclaw_engine/src/live_authorization.rs::canonical_payload`:
#   version|tier|issued_at_ms|expires_at_ms|operator_id|env_allowed_sorted_csv
#
# LiveDemo is held to the same bar as Mainnet by design — the point of
# LiveDemo is to exercise the Live gate before real money. (See memory
# `feedback_live_no_degradation_by_endpoint.md`.)

_AUTHORIZATION_SCHEMA_VERSION = 1
_AUTHORIZATION_FILENAME = "authorization.json"
_ENV_LIVE_DEMO = "live_demo"
_ENV_MAINNET = "mainnet"

# Canonical tier-name mapping used on the wire. Must stay stable — Rust logs
# this string for audit. Matches `TrustTier.name` (e.g. TrustTier.T0_ENTRY.name).
_TIER_WIRE_NAME = {
    TrustTier.T0_ENTRY: "T0_ENTRY",
    TrustTier.T1_PROVISIONAL: "T1_PROVISIONAL",
    TrustTier.T2_ESTABLISHED: "T2_ESTABLISHED",
    TrustTier.T3_TRUSTED: "T3_TRUSTED",
}


def _live_secret_slot_dir() -> Path:
    """
    Resolve the on-disk `.../secret_files/bybit/live/` directory using the
    same precedence as Rust `read_secret_file` and Python settings_routes.

    Cross-platform: uses HOME / USERPROFILE via Path.home(); never hardcodes.
    """
    base_env = os.environ.get("OPENCLAW_SECRETS_DIR")
    if base_env:
        return Path(base_env) / "live"
    return Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit" / "live"


def _current_bybit_endpoint_label() -> str:
    """
    Read `bybit_endpoint` secret file and translate to the wire label used in
    `env_allowed`. Defaults to mainnet on any missing/unknown value, matching
    Rust's `live_bybit_environment()` fail-safe.
    """
    try:
        path = _live_secret_slot_dir() / "bybit_endpoint"
        content = path.read_text(encoding="utf-8").strip().lower()
    except (FileNotFoundError, PermissionError, OSError):
        content = ""
    if content == "demo":
        return _ENV_LIVE_DEMO
    # "mainnet" or empty or unknown → mainnet (fail-safe: never silently downgrade to demo)
    return _ENV_MAINNET


def _canonical_authorization_payload(
    version: int,
    tier: str,
    issued_at_ms: int,
    expires_at_ms: int,
    operator_id: str,
    env_allowed: list[str],
) -> str:
    """
    Build the bytes that get HMAC-signed. MUST match Rust canonical_payload
    exactly (pipe-separated, env_allowed sorted+deduped ASCII-ascending).
    """
    envs_sorted = sorted(set(env_allowed))
    return f"{version}|{tier}|{issued_at_ms}|{expires_at_ms}|{operator_id}|{','.join(envs_sorted)}"


def _sign_authorization_payload(payload: str, ipc_secret: str) -> str:
    """HMAC-SHA256 → hex-lowercase. Matches Rust `compute_signature`."""
    mac = hmac.new(ipc_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return mac.hexdigest()


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """
    Write `data` to `path` atomically (tmpfile + rename) with chmod 600.
    Prevents Rust from reading a partially-written file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, stat.S_IRWXU)
    except OSError:
        pass  # best-effort on exotic filesystems

    fd, tmp_path = tempfile.mkstemp(
        prefix=".authorization.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, sort_keys=True, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp_path, path)  # atomic on POSIX + Windows
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _write_signed_live_authorization(
    operator_id: str,
    tier: int,
    expires_at_ms: int,
) -> dict[str, Any]:
    """
    Sign and persist the Earned-Trust authorization record that the Rust
    engine's LIVE-GATE-BINDING-1 reads.

    Raises RuntimeError if `OPENCLAW_IPC_SECRET` is unset — Rust will also
    refuse to verify without it, so failing here surfaces the config error
    at approval time instead of at engine restart.

    對 Rust 引擎 LIVE-GATE-BINDING-1 簽名寫入贏得信任授權記錄。
    """
    ipc_secret = os.environ.get("OPENCLAW_IPC_SECRET", "").strip()
    if not ipc_secret:
        raise RuntimeError(
            "OPENCLAW_IPC_SECRET is not set — cannot sign live authorization. "
            "Set it in the control-api environment before approving live auth. / "
            "OPENCLAW_IPC_SECRET 未設定，無法簽署 live 授權"
        )

    tier_enum = TrustTier(tier)
    tier_name = _TIER_WIRE_NAME[tier_enum]
    issued_at_ms = int(time.time() * 1000)
    env_allowed = [_current_bybit_endpoint_label()]

    payload = _canonical_authorization_payload(
        version=_AUTHORIZATION_SCHEMA_VERSION,
        tier=tier_name,
        issued_at_ms=issued_at_ms,
        expires_at_ms=expires_at_ms,
        operator_id=operator_id,
        env_allowed=env_allowed,
    )
    sig = _sign_authorization_payload(payload, ipc_secret)

    record = {
        "version": _AUTHORIZATION_SCHEMA_VERSION,
        "tier": tier_name,
        "issued_at_ms": issued_at_ms,
        "expires_at_ms": expires_at_ms,
        "operator_id": operator_id,
        "env_allowed": env_allowed,
        "sig": sig,
    }

    path = _live_secret_slot_dir() / _AUTHORIZATION_FILENAME
    _atomic_write_json(path, record)
    logger.warning(
        "LIVE-GATE-BINDING-1: signed live authorization written path=%s tier=%s "
        "env_allowed=%s expires_at_ms=%d operator=%s / 已寫入簽名 live 授權",
        path,
        tier_name,
        env_allowed,
        expires_at_ms,
        operator_id,
    )
    return record


def _delete_live_authorization_file() -> bool:
    """
    Remove the authorization file so Rust refuses to (re)spawn Live. Called
    during revoke flows and whenever the old authorization is superseded.
    Returns True if a file was deleted.
    """
    path = _live_secret_slot_dir() / _AUTHORIZATION_FILENAME
    try:
        path.unlink()
        logger.warning(
            "LIVE-GATE-BINDING-1: live authorization file removed path=%s / "
            "已刪除 live 授權檔案",
            path,
        )
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.error(
            "LIVE-GATE-BINDING-1: failed to remove live authorization file %s: %s",
            path,
            exc,
        )
        return False


def _get_hub():
    """Lazy import GovernanceHub singleton. / 延遲導入 GovernanceHub 單例。"""
    try:
        from .paper_trading_routes import GOV_HUB
        return GOV_HUB
    except (ImportError, AttributeError):
        return None

live_trust_router = APIRouter(
    prefix="/api/v1/live",
    tags=["Live Trust / 實盤信任階梯"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Auth helpers (reuse governance_routes pattern) / 認證輔助
# ─────────────────────────────────────────────────────────────────────────────

def _get_auth_actor(
    request: Any = None,
    authorization: str | None = None,
) -> Any:
    from .governance_routes import _get_auth_actor as _gov_get_actor
    return _gov_get_actor(request, authorization)


def _require_operator(actor: Any) -> None:
    from .governance_routes import _require_operator_role
    _require_operator_role(actor)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics collection helper / 指標收集輔助
# ─────────────────────────────────────────────────────────────────────────────

def _collect_live_metrics() -> TrustMetrics:
    """
    Collect live trading metrics from available sources.
    Gracefully degrades: missing data fields default to 0 / None.
    從可用數據源收集實盤交易指標。優雅降級：缺失數據字段默認為 0。
    """
    m = TrustMetrics()
    try:
        from .ipc_state_reader import get_rust_reader
        rust = get_rust_reader()

        # PaperState metrics from live engine / 從 live 引擎讀取 PaperState 指標
        snap = rust.get_engine_snapshot("live") or rust.get_snapshot() or {}
        paper = snap.get("paper_state") or {}

        m.net_pnl = float(paper.get("net_pnl") or paper.get("cumulative_pnl") or 0.0)
        m.consecutive_losses = int(paper.get("consecutive_losses") or 0)

        # Full metrics from the existing metrics endpoint logic / 從現有 metrics 端點邏輯讀取完整指標
        try:
            from .paper_trading_routes import compute_full_metrics
            full = compute_full_metrics(mode="live") or {}
            trade = full.get("trade_metrics") or {}
            risk = full.get("drawdown_metrics") or {}

            m.win_rate_pct = float(trade.get("win_rate") or 0.0) * 100.0
            m.profit_factor = float(trade.get("profit_factor") or 0.0)
            m.sharpe = float(full.get("sharpe") or full.get("sharpe_ratio") or 0.0)
            m.max_window_drawdown_pct = float(risk.get("max_drawdown_pct") or 0.0)

            # Cost ratio: total_fees / gross_pnl (approximate) / 費率比
            gross = float(trade.get("gross_pnl") or 0.0)
            fees = float(trade.get("total_fees") or 0.0)
            if gross > 0:
                m.cost_ratio = fees / gross
        except Exception:
            pass  # metrics unavailable — keep defaults

        # Daily drawdown from live contraction state / 從縮倉狀態讀取日內回撤
        try:
            from .live_session_routes import _live_contraction_state  # type: ignore[attr-defined]
            if _live_contraction_state == "halted":
                m.max_daily_drawdown_pct = 15.0
            elif _live_contraction_state == "warned":
                m.max_daily_drawdown_pct = 5.0
        except Exception:
            pass

        # Reconciler state / 對賬狀態
        try:
            hub = _get_hub()
            if hub is not None:
                recon = getattr(hub, "_reconciler", None)
                if recon is not None:
                    state = getattr(recon, "state", None)
                    if state is not None:
                        drift_cycles = getattr(state, "major_drift_cycles", 0) or 0
                        m.reconciler_major_drift_cycles = int(drift_cycles)
        except Exception:
            pass

        # Incident counts / 事件計數
        try:
            hub = _get_hub()
            if hub is not None:
                incidents = getattr(hub, "_incident_log", None)
                if incidents is not None:
                    # Count recent incidents in observation window / 統計觀察窗口內近期事件
                    window_ms = 30 * 86_400_000  # 30-day window / 30 天窗口
                    cutoff_ms = int(time.time() * 1000) - window_ms
                    all_incidents = getattr(incidents, "get_all", lambda: [])()
                    for inc in all_incidents:
                        ts = getattr(inc, "ts_ms", 0) or 0
                        if ts < cutoff_ms:
                            continue
                        sev = str(getattr(inc, "severity", "") or "").lower()
                        if sev == "critical":
                            m.critical_incident_count += 1
                        elif sev == "major":
                            m.major_incident_count += 1
        except Exception:
            pass

    except Exception as exc:
        logger.warning(
            "live_trust_routes: metrics collection error (using defaults): %s / "
            "指標收集錯誤（使用默認值）: %s", exc, exc,
        )

    return m


# ─────────────────────────────────────────────────────────────────────────────
# Governance auth helper / 治理授權輔助
# ─────────────────────────────────────────────────────────────────────────────

def _create_live_auth(actor_id: str, tier: int) -> tuple[str, int]:
    """
    Create + auto-approve a live SM-01 authorization at the given tier TTL.
    Returns (auth_id, expires_at_ms). Raises on failure.
    按給定 tier TTL 創建並自動批准 live SM-01 授權。返回 (auth_id, expires_at_ms)。
    """
    hub = _get_hub()
    if hub is None or not getattr(hub, "_initialized", False):
        raise RuntimeError("GovernanceHub not available")
    auth_sm = getattr(hub, "_authorization_sm", None)
    if auth_sm is None:
        raise RuntimeError("Authorization SM not available")

    ttl_h = TIER_TTL_HOURS.get(tier, 24)
    expires_at_ms = int((time.time() + ttl_h * 3600) * 1000)
    live_scope = {
        "mode": "live",
        "trust_tier": tier,
        "tier_name": TIER_NAMES.get(tier, "T0"),
        "execution": ["live_submit", "paper_submit"],
        "approved_by": actor_id,
    }
    auth_obj = auth_sm.create_draft(
        title=f"Live Auth — {TIER_NAMES.get(tier, 'T0')} — {actor_id}",
        scope=live_scope,
        created_by=actor_id,
        description=(
            f"Earned-trust renewal at {TIER_NAMES.get(tier, 'T0')} (TTL={ttl_h}h) "
            f"authorized by Operator '{actor_id}'. / "
            f"以 {TIER_NAMES.get(tier, 'T0')} 贏得信任續期（TTL={ttl_h}h），Operator '{actor_id}' 授權。"
        ),
        expires_at_ms=expires_at_ms,
    )
    auth_id = auth_obj.authorization_id
    auth_sm.submit_for_approval(auth_id)
    auth_sm.approve(
        auth_id,
        approved_by=actor_id,
        reason=(
            f"Operator confirmed earned-trust renewal tier={tier} ttl={ttl_h}h. / "
            f"Operator 確認贏得信任續期 tier={tier} ttl={ttl_h}h。"
        ),
    )
    _inval = getattr(hub, "_invalidate_auth_cache", None)
    if _inval:
        _inval()
    return auth_id, expires_at_ms


def _revoke_existing_live_auths(actor_id: str) -> None:
    """
    Revoke all currently ACTIVE live-scoped authorizations before creating new one.
    Also deletes the signed LIVE-GATE-BINDING-1 authorization.json so Rust
    refuses to keep the Live pipeline running past this revoke point.
    在創建新授權前撤銷所有當前有效的 live 授權，並刪除簽名檔案讓 Rust 拒絕
    繼續運行 Live 管線。
    """
    try:
        hub = _get_hub()
        if hub is None:
            return
        auth_sm = getattr(hub, "_authorization_sm", None)
        if auth_sm is None:
            return
        for auth in auth_sm.get_effective():
            scope = getattr(auth, "scope", {}) or {}
            if isinstance(scope, dict) and scope.get("mode") == "live":
                auth_sm.revoke(
                    auth.authorization_id,
                    reason=f"superseded_by_earned_trust_renewal actor={actor_id}",
                )
    except Exception as exc:
        logger.warning("Failed to revoke existing live auths: %s", exc)
    # Always attempt to clear the signed authorization file even if SM-01
    # revoke path errored — Rust's gate is the last line of defence and must
    # not keep running on a stale on-disk record.
    # 即使 SM-01 revoke 失敗也要嘗試刪除簽名檔案 — Rust gate 是最後防線，
    # 不能留著陳舊 on-disk 記錄繼續跑。
    _delete_live_authorization_file()


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response models / 請求/響應模型
# ─────────────────────────────────────────────────────────────────────────────

class RenewBody(BaseModel):
    """
    POST /api/v1/live/auth/renew request body.
    POST /api/v1/live/auth/renew 請求體。
    """
    accepted_tier: Optional[int] = Field(
        default=None,
        ge=0, le=3,
        description="Tier to renew at. If omitted, uses system recommendation. / "
                    "續期 tier。省略時使用系統建議。",
    )
    reason: str = Field(
        default="operator_renew",
        min_length=1, max_length=500,
        description="Operator note for audit trail. / Operator 審計備注。",
    )


class FullReviewBody(BaseModel):
    """
    POST /api/v1/live/auth/renew-review — T3 full review body.
    T3 全面審查請求體。
    """
    review_notes: str = Field(
        min_length=10, max_length=1000,
        description="Operator's review notes (mandatory for T3 review). / "
                    "Operator 審查備注（T3 審查必填）。",
    )
    confirmed_tier: int = Field(
        ge=0, le=3,
        description="Tier confirmed after review. / 審查後確認的 tier。",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints / 端點
# ─────────────────────────────────────────────────────────────────────────────

@live_trust_router.get("/auth/trust-status")
def get_trust_status(
    actor: Any = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Get current earned-trust state + renewal recommendation.
    Always safe to call; does not require Operator role (read-only).
    獲取當前贏得信任狀態 + 續期建議。始終安全調用；不需要 Operator 角色（只讀）。
    """
    engine = get_trust_engine()
    snapshot = engine.get_state_snapshot()

    # Collect metrics and evaluate renewal recommendation / 收集指標並評估續期建議
    try:
        metrics = _collect_live_metrics()
        rec = engine.evaluate_renewal(metrics)
        recommendation = {
            "recommended_tier": rec.recommended_tier,
            "recommended_tier_name": TIER_NAMES.get(rec.recommended_tier, "T0"),
            "recommended_ttl_hours": rec.recommended_ttl_hours,
            "action": rec.action,
            "reasons": rec.reasons,
            "requires_operator_review": rec.requires_operator_review,
        }
        metrics_dict = rec.metrics_snapshot or {}
    except Exception as exc:
        logger.warning("trust-status: evaluation error: %s", exc)
        recommendation = {"action": "unknown", "reasons": [str(exc)]}
        metrics_dict = {}

    return {
        "ok": True,
        "data": {
            **snapshot,
            "recommendation": recommendation,
            "metrics": metrics_dict,
            "tier_ladder": [
                {
                    "tier": t,
                    "name": TIER_NAMES[t],
                    "ttl_hours": TIER_TTL_HOURS[t],
                }
                for t in range(4)
            ],
        },
    }


@live_trust_router.post("/auth/renew")
def post_live_renew(
    body: RenewBody,
    request: Request,
    authorization: str | None = None,
    actor: Any = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Operator renews Live authorization at the earned tier (or manually overrides lower).
    Creates new SM-01 auth, revokes old one, updates trust engine state.
    Blocks if T3 requires mandatory full review (use /renew-review instead).

    Operator 以贏得的 tier 續期實盤授權（或手動選擇較低 tier）。
    創建新 SM-01 授權，撤銷舊授權，更新信任引擎狀態。
    T3 需要強制全面審查時阻塞（改用 /renew-review）。
    """
    _require_operator(actor)
    actor_id = getattr(actor, "actor_id", "operator")
    engine = get_trust_engine()

    # Check if mandatory review is required / 檢查是否需要強制審查
    snapshot = engine.get_state_snapshot()
    if snapshot.get("requires_operator_review"):
        raise HTTPException(
            status_code=409,
            detail=(
                "T3 has reached the auto-renewal limit. "
                "Use POST /api/v1/live/auth/renew-review for mandatory full review. / "
                "T3 已達到自動續期上限。請使用 /renew-review 進行強制全面審查。"
            ),
        )

    # Evaluate recommended tier / 評估建議 tier
    metrics = _collect_live_metrics()
    rec = engine.evaluate_renewal(metrics)
    recommended_tier = rec.recommended_tier

    # Operator may override downward only (cannot self-promote above recommendation)
    # Operator 只能向下覆蓋（不能自我提升超過建議）
    if body.accepted_tier is not None:
        if body.accepted_tier > recommended_tier:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot accept tier {body.accepted_tier} higher than "
                    f"system recommendation {recommended_tier}. / "
                    f"不能接受高於系統建議 {recommended_tier} 的 tier {body.accepted_tier}。"
                ),
            )
        final_tier = body.accepted_tier
    else:
        final_tier = recommended_tier

    # Create new auth / 創建新授權
    try:
        _revoke_existing_live_auths(actor_id)
        auth_id, expires_at_ms = _create_live_auth(actor_id, final_tier)
    except Exception as exc:
        logger.error("live_trust_routes: failed to create live auth: %s", exc)
        raise HTTPException(status_code=500, detail=f"Auth creation failed: {exc}")

    # Notify trust engine / 通知信任引擎
    engine.on_auth_renewed(new_tier=final_tier, new_expires_ts_ms=expires_at_ms)

    # LIVE-GATE-BINDING-1: sign + persist authorization.json so the Rust engine
    # will (re-)spawn Live. Revoke already deleted any prior record. Failure
    # here = fatal to the renew path because Rust will refuse Live without it.
    # 簽名寫入 authorization.json，Rust 引擎才會 (re-)spawn Live。此步驟失敗 =
    # 視同 renew 失敗，否則 operator 誤以為批准成功但 Rust 其實拒啟。
    try:
        _write_signed_live_authorization(
            operator_id=actor_id,
            tier=final_tier,
            expires_at_ms=expires_at_ms,
        )
    except Exception as exc:
        logger.error(
            "live_trust_routes: failed to write signed authorization: %s", exc
        )
        raise HTTPException(
            status_code=500,
            detail=f"Signed authorization write failed: {exc}",
        )

    # Re-grant execution authority in live_session_routes / 重新授予 execution_authority
    try:
        from .live_session_routes import _grant_execution_authority_internal
        _grant_execution_authority_internal()
    except Exception:
        pass  # non-fatal — operator can use grant endpoint separately

    logger.warning(
        "Live auth RENEWED tier=%s ttl=%dh actor=%s auth_id=%s / "
        "實盤授權已續期 tier=%s ttl=%dh actor=%s",
        TIER_NAMES.get(final_tier), TIER_TTL_HOURS.get(final_tier, 24),
        actor_id, auth_id, TIER_NAMES.get(final_tier), TIER_TTL_HOURS.get(final_tier, 24),
    )

    return {
        "ok": True,
        "data": {
            "auth_id": auth_id,
            "tier": final_tier,
            "tier_name": TIER_NAMES.get(final_tier, "T0"),
            "ttl_hours": TIER_TTL_HOURS.get(final_tier, 24),
            "expires_at_ms": expires_at_ms,
            "action": rec.action,
            "reasons": rec.reasons,
        },
        "message": f"live_auth_renewed_tier_{final_tier}",
    }


@live_trust_router.post("/auth/renew-review")
def post_live_renew_review(
    body: FullReviewBody,
    request: Request,
    authorization: str | None = None,
    actor: Any = Depends(base.current_actor),
) -> dict[str, Any]:
    """
    Mandatory full Operator review for T3 after auto-renewal limit exhausted.
    Operator must provide review_notes and confirm a tier (T0–T3 allowed).
    This resets the T3 renewal counter.

    T3 自動續期上限耗盡後的強制 Operator 全面審查。
    Operator 必須提供 review_notes 並確認 tier（T0-T3 均可）。
    此操作重置 T3 續期計數器。
    """
    _require_operator(actor)
    actor_id = getattr(actor, "actor_id", "operator")
    engine = get_trust_engine()

    final_tier = body.confirmed_tier

    try:
        _revoke_existing_live_auths(actor_id)
        auth_id, expires_at_ms = _create_live_auth(actor_id, final_tier)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Auth creation failed: {exc}")

    # Reset T3 counter + update state / 重置 T3 計數器 + 更新狀態
    with engine._lock:
        engine._state.renewals_at_t3 = 0
        engine._state.promotion_history.append({
            "ts_ms": int(time.time() * 1000),
            "from_tier": engine._state.current_tier,
            "to_tier": final_tier,
            "event": "operator_full_review",
            "notes": body.review_notes[:200],
        })
    engine.on_auth_renewed(new_tier=final_tier, new_expires_ts_ms=expires_at_ms)

    # LIVE-GATE-BINDING-1: sign + persist authorization.json (same reasoning
    # as the /renew endpoint — Rust engine refuses Live without it).
    try:
        _write_signed_live_authorization(
            operator_id=actor_id,
            tier=final_tier,
            expires_at_ms=expires_at_ms,
        )
    except Exception as exc:
        logger.error(
            "live_trust_routes (renew-review): failed to write signed authorization: %s",
            exc,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Signed authorization write failed: {exc}",
        )

    try:
        from .live_session_routes import _grant_execution_authority_internal
        _grant_execution_authority_internal()
    except Exception:
        pass

    logger.warning(
        "Live auth FULL REVIEW completed tier=%s actor=%s auth_id=%s / "
        "實盤授權全面審查完成 tier=%s actor=%s",
        TIER_NAMES.get(final_tier), actor_id, auth_id, TIER_NAMES.get(final_tier),
    )

    return {
        "ok": True,
        "data": {
            "auth_id": auth_id,
            "tier": final_tier,
            "tier_name": TIER_NAMES.get(final_tier, "T0"),
            "ttl_hours": TIER_TTL_HOURS.get(final_tier, 24),
            "expires_at_ms": expires_at_ms,
            "review_notes_length": len(body.review_notes),
        },
        "message": "live_auth_full_review_complete",
    }
