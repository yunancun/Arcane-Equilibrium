from __future__ import annotations

"""
Executor Routes — operator API for ExecutorAgent shadow_mode flip + auth gates.
執行器路由 — Operator 用 API：執行器 shadow_mode 翻轉 + 授權門控。

MODULE_NOTE (EN):
  G3-02 Phase C — operator-facing IPC bridge for ExecutorAgent shadow→live
  toggle, behind an auth gate that mirrors the existing 5-gate live chain.
  Per RFC §6.1 (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g3_01_executor_agent_ipc_rfc.md`):
    "Operator flips `shadow_mode=false` via IPC on demo → SubmitOrder reaches
    Rust intent_processor → real demo fill → unblock live gate."

  Endpoint:
    POST /api/v1/executor/shadow-toggle
      body: {"engine": "demo"|"live"|"paper", "shadow_mode": bool, "source": str = "operator"}
      auth:
        - always: Operator role (current_actor)
        - if shadow_mode=false AND engine=live: full 5-gate chain
            1. Operator role  (Python; verified above)
            2. live_reserved global mode
            3. OPENCLAW_ALLOW_MAINNET=1 env (Mainnet only — bybit_endpoint=mainnet)
            4. live secret slot has api_key + api_secret
            5. authorization.json HMAC valid + unexpired + env_allowed match
        - if shadow_mode=false AND engine=demo: just Operator role
        - any → shadow_mode=true (retreat): just Operator role (cheap retreat per §六 #6)
        - paper engine: Operator role only (paper is opt-in via env per
          memory/project_paper_pipeline_disabled_by_default.md)

  On gate success:
    Calls IPC `patch_risk_config` with `{engine, patch: {executor: {shadow_mode: ...}}, source}`
    — the Phase A path that already round-trips the executor sub-config + IPC
    audit log via Rust ConfigStore.

  On gate failure:
    Returns 403 with `gate_failed` field naming the specific gate (not just
    "denied") so operators can self-diagnose. Audit log entry written either
    way (success + failure) via change_audit_log.

  Phase A schema landed: `RiskConfig.executor.{shadow_mode, max_position_pct,
  per_symbol_position_cap}` + `validate()` + 3-env TOML + 4 IPC e2e Rust tests
  (commits 16c97c1 + 03acedb + 3bed899).

  Phase B Python cache landed: ExecutorConfigCache polls `get_risk_config`
  every N s; ExecutorAgent reads `shadow_mode_provider()` → cache. Operator
  flip via this endpoint → next IPC poll picks up the change → ExecutorAgent
  starts (or stops) submitting real intents on the next tick.

  Runtime impact: NEW endpoint, gated. Default state: nothing calls it. Once
  operator invokes with `shadow_mode=false`, demo session begins submitting
  real (demo) orders within the cache poll interval (~10s default).

MODULE_NOTE (中):
  G3-02 Phase C — Operator 透過此 API flip ExecutorAgent shadow_mode；授權
  鏈完全沿用既有 5-gate live chain，未重寫。

  Endpoint：
    POST /api/v1/executor/shadow-toggle
      body：{"engine": "demo"|"live"|"paper", "shadow_mode": bool, "source": "operator"}
      門控：
        - 永遠：Operator 角色（current_actor）
        - shadow_mode=false 且 engine=live：完整 5-gate
        - shadow_mode=false 且 engine=demo：僅 Operator 角色
        - 任意 → shadow_mode=true：僅 Operator 角色（撤退便宜）
        - paper：僅 Operator 角色

  成功 → 呼叫 IPC `patch_risk_config`（Phase A 既有路徑），Rust 寫入 audit。
  失敗 → 403 + 具體失敗的 gate 名稱（不是模糊的 "denied"），方便 operator 自診。

  Phase A schema 已落（Rust 端）；Phase B Python cache 已落 — 此 endpoint 是
  把這套基礎設施暴露給 operator 的最後一塊。
"""

import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as base
from .ipc_dispatch import one_shot_ipc_call

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

executor_router = APIRouter(
    prefix="/api/v1/executor",
    tags=["Executor / 執行器控制"],
)


# Whitelist engine names — prevents IPC injection via the request body.
# 引擎白名單 — 防止經由 request body 注入 IPC params。
_ALLOWED_ENGINES: frozenset[str] = frozenset({"paper", "demo", "live"})


# ═══════════════════════════════════════════════════════════════════════════════
# Request / response models / 請求 / 回應 模型
# ═══════════════════════════════════════════════════════════════════════════════


class ShadowToggleRequest(BaseModel):
    """Body for POST /api/v1/executor/shadow-toggle.
    POST /api/v1/executor/shadow-toggle 的請求 body。

    Fields:
      engine: target engine ("paper" | "demo" | "live"). Whitelisted server-side.
      shadow_mode: True = log only, False = forward SubmitOrder IPC to Rust.
      source: provenance label written to IPC audit log; defaults to "operator".

    引擎名稱由伺服器端白名單驗證；shadow_mode=False 才會解鎖真實送單。
    """

    engine: str = Field(..., description="Target engine: paper | demo | live")
    shadow_mode: bool = Field(..., description="True=shadow (log only); False=submit real intents")
    source: str = Field(default="operator", min_length=1, max_length=64, description="Audit provenance tag")


# ═══════════════════════════════════════════════════════════════════════════════
# 5-gate verifier — reuse / wrap existing live-gate logic from live_session_*
# 5 道門控驗證 — 沿用既有 live_session_* 的 logic 不重寫
# ═══════════════════════════════════════════════════════════════════════════════


def _gate_failure(gate_name: str, hint: str) -> HTTPException:
    """Build a 403 with a structured `gate_failed` payload for operator self-diagnosis.

    Distinct from a generic "denied" — operator can read the specific failing
    gate and either fix the missing piece (env var, missing key, expired
    authorization) or escalate.

    建構 403 並回傳具體 gate_failed 名稱，方便 operator 自診（補 env / 補 key
    / 重簽授權）或升級求助。
    """
    return HTTPException(
        status_code=403,
        detail={
            "ok": False,
            "gate_failed": gate_name,
            "hint": hint,
        },
    )


def _verify_demo_gate(actor: Any) -> None:
    """Demo flip to live: just Operator role (live-gate not required for demo).

    Per RFC §4.4 auth matrix: demo's authorization needs are weaker because
    demo uses the demo API endpoint. Operator role + the calling auth check
    (Bearer token) are sufficient.

    demo flip：demo 走 demo endpoint，無需完整 live-gate；Operator 角色足矣。
    """
    # Operator role check — reuse governance_routes pattern.
    # Operator 角色檢查 — 沿用 governance_routes 模式。
    from .governance_routes import _require_operator_role
    _require_operator_role(actor)


def _verify_paper_gate(actor: Any) -> None:
    """Paper engine: any Operator-authenticated request OK.

    Per task spec: "for paper engine, accept any auth (Operator role only) since
    paper is opt-in via env" (memory/project_paper_pipeline_disabled_by_default.md).
    paper 引擎：predefined opt-in via env，Operator 角色即可。
    """
    from .governance_routes import _require_operator_role
    _require_operator_role(actor)


def _verify_live_gate(actor: Any) -> None:
    """Verify the FULL 5-gate live chain for `shadow_mode=false` flip on live.

    Reuses existing live-gate primitives (no new auth logic):
      1. Operator role           — governance_routes._require_operator_role
      2. live_reserved global mode — live_session_routes._get_global_mode_state
      3. OPENCLAW_ALLOW_MAINNET=1 — env (only Mainnet; LiveDemo skips this gate
         per CLAUDE.md §四, but still requires gates 4+5)
      4. secret slot has api_key + api_secret — read from
         $OPENCLAW_SECRETS_DIR/live/api_key + api_secret
      5. authorization.json valid — read from $OPENCLAW_SECRETS_DIR/live/
         authorization.json; check HMAC + expiry + env_allowed match against
         current bybit_endpoint label

    First failing gate raises 403 with `gate_failed` naming the specific
    gate. Operator can resolve by setting env / writing keys / running
    /api/v1/live/auth/renew (which writes authorization.json via
    _write_signed_live_authorization).

    完整 5-gate 鏈：缺哪一道直接報哪一道；不混淆失敗原因。
    """
    # Gate 1: Operator role — same module that live_session_routes / governance_routes use.
    from .governance_routes import _require_operator_role
    _require_operator_role(actor)

    # Gate 2: live_reserved global mode — reuse live_session_routes helper.
    # Lazy import to keep this module import-time cheap and avoid circular imports.
    # 延遲匯入避免循環匯入。
    from .live_session_routes import _get_global_mode_state
    global_mode = _get_global_mode_state()
    if "live" not in global_mode:
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=live_reserved actor=%s mode=%s",
            getattr(actor, "actor_id", "?"), global_mode,
        )
        raise _gate_failure(
            "live_reserved",
            f"Switch Global Mode to live_reserved first (current={global_mode!r}).",
        )

    # Determine endpoint label (mainnet vs live_demo) from secret file.
    # 由 secret 檔案判斷端點 (mainnet vs live_demo)。
    endpoint_label = _current_bybit_endpoint_label()

    # Gate 3: Mainnet-only env check (LiveDemo skips Gate 3 per CLAUDE.md §四).
    # Mainnet 才檢查；LiveDemo 跳過第 3 道（依 §四 設計）。
    if endpoint_label == "mainnet":
        env_val = os.environ.get("OPENCLAW_ALLOW_MAINNET", "").strip()
        if env_val != "1":
            logger.warning(
                "executor.shadow-toggle live gate FAIL gate=mainnet_env actor=%s env=%r",
                getattr(actor, "actor_id", "?"), env_val,
            )
            raise _gate_failure(
                "mainnet_env",
                "OPENCLAW_ALLOW_MAINNET=1 must be set in the engine environment "
                "for Mainnet flip; restart engine after setting.",
            )

    # Gate 4: secret slot has api_key + api_secret.
    # 第 4 道：secret slot 必須有 api_key + api_secret。
    slot_dir = _live_secret_slot_dir()
    api_key_file = slot_dir / "api_key"
    api_secret_file = slot_dir / "api_secret"
    try:
        has_key = api_key_file.exists() and bool(api_key_file.read_text(encoding="utf-8").strip())
        has_secret = api_secret_file.exists() and bool(api_secret_file.read_text(encoding="utf-8").strip())
    except OSError:
        has_key = has_secret = False
    if not (has_key and has_secret):
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=secret_slot actor=%s key=%s secret=%s",
            getattr(actor, "actor_id", "?"), has_key, has_secret,
        )
        raise _gate_failure(
            "secret_slot",
            f"Live secret slot incomplete at {slot_dir}: api_key={has_key} api_secret={has_secret}.",
        )

    # Gate 5: authorization.json present, HMAC valid, unexpired, env_allowed matches.
    # 第 5 道：authorization.json 簽名有效、未過期、env_allowed 含當前端點。
    _verify_authorization_json_or_raise(slot_dir, endpoint_label, actor)


def _live_secret_slot_dir() -> Path:
    """Resolve `…/secret_files/bybit/live/` (same precedence as live_trust_routes).
    Cross-platform: HOME via Path.home(); never hardcoded.
    解析 secret slot 目錄；遵守 OPENCLAW_SECRETS_DIR；跨平台。
    """
    base_env = os.environ.get("OPENCLAW_SECRETS_DIR")
    if base_env:
        return Path(base_env) / "live"
    return Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit" / "live"


def _current_bybit_endpoint_label() -> str:
    """Read `bybit_endpoint` secret file → wire label "live_demo" | "mainnet".
    Defaults to "mainnet" on missing/unknown — Rust live_bybit_environment fail-safe.
    讀 bybit_endpoint 檔；缺漏/未知都回 mainnet（fail-safe，永不靜默降級至 demo）。
    """
    try:
        path = _live_secret_slot_dir() / "bybit_endpoint"
        content = path.read_text(encoding="utf-8").strip().lower()
    except (FileNotFoundError, PermissionError, OSError):
        content = ""
    if content == "demo":
        return "live_demo"
    return "mainnet"


def _verify_authorization_json_or_raise(slot_dir: Path, endpoint_label: str, actor: Any) -> None:
    """Verify authorization.json HMAC + expiry + env_allowed.

    Reuses the canonical-payload + sign helpers from live_trust_routes (lazy
    import) — same code path as `_write_signed_live_authorization` produces.
    Mirrors Rust `live_authorization::verify` checks.

    Failure reasons are surfaced as distinct `gate_failed` values:
      - authorization_missing  : file does not exist
      - authorization_malformed: parse / required-field error
      - authorization_signature: HMAC mismatch
      - authorization_expired  : expires_at_ms < now
      - authorization_env_mismatch : current bybit_endpoint not in env_allowed

    驗證 authorization.json 簽名 + 期效 + env_allowed；失敗原因細分回報。
    """
    import hashlib
    import hmac as _hmac
    import json

    auth_path = slot_dir / "authorization.json"
    if not auth_path.exists():
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=authorization actor=%s reason=missing path=%s",
            getattr(actor, "actor_id", "?"), auth_path,
        )
        raise _gate_failure(
            "authorization",
            f"authorization.json missing at {auth_path}; "
            "run /api/v1/live/auth/renew (Operator) first.",
        )

    try:
        record = json.loads(auth_path.read_text(encoding="utf-8"))
        version = int(record["version"])
        tier = str(record["tier"])
        issued_at_ms = int(record["issued_at_ms"])
        expires_at_ms = int(record["expires_at_ms"])
        operator_id = str(record["operator_id"])
        env_allowed = list(record["env_allowed"])
        sig_recorded = str(record["sig"])
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=authorization actor=%s reason=malformed err=%s",
            getattr(actor, "actor_id", "?"), exc,
        )
        raise _gate_failure(
            "authorization_malformed",
            f"authorization.json parse error: {exc}",
        )

    # HMAC verify — must match Rust compute_signature + Python _sign_authorization_payload.
    # HMAC 驗證 — 必須對齊 Rust 與 Python 既有實作。
    ipc_secret = os.environ.get("OPENCLAW_IPC_SECRET", "").strip()
    if not ipc_secret:
        # Treat as authorization gate failure: signature cannot be verified
        # without the secret, so we MUST refuse rather than fail-open.
        # 視為授權 gate 失敗：缺 secret 無法驗 HMAC，必須拒絕，不可 fail-open。
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=authorization actor=%s reason=ipc_secret_missing",
            getattr(actor, "actor_id", "?"),
        )
        raise _gate_failure(
            "authorization",
            "OPENCLAW_IPC_SECRET unset — cannot verify HMAC; set in engine env.",
        )
    envs_sorted = sorted(set(env_allowed))
    payload = f"{version}|{tier}|{issued_at_ms}|{expires_at_ms}|{operator_id}|{','.join(envs_sorted)}"
    sig_expected = _hmac.new(
        ipc_secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not _hmac.compare_digest(sig_expected, sig_recorded):
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=authorization_signature actor=%s",
            getattr(actor, "actor_id", "?"),
        )
        raise _gate_failure(
            "authorization_signature",
            "authorization.json HMAC mismatch — secret rotated or file tampered. "
            "Run /api/v1/live/auth/renew to re-sign.",
        )

    # Expiry check.
    now_ms = int(time.time() * 1000)
    if expires_at_ms <= now_ms:
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=authorization_expired actor=%s expires_at_ms=%d now_ms=%d",
            getattr(actor, "actor_id", "?"), expires_at_ms, now_ms,
        )
        raise _gate_failure(
            "authorization_expired",
            f"authorization.json expired at ts_ms={expires_at_ms} (now={now_ms}). "
            "Run /api/v1/live/auth/renew.",
        )

    # env_allowed must contain current endpoint label.
    if endpoint_label not in env_allowed:
        logger.warning(
            "executor.shadow-toggle live gate FAIL gate=authorization_env_mismatch actor=%s endpoint=%s env_allowed=%s",
            getattr(actor, "actor_id", "?"), endpoint_label, env_allowed,
        )
        raise _gate_failure(
            "authorization_env_mismatch",
            f"authorization env_allowed={env_allowed} does not contain current "
            f"endpoint={endpoint_label!r}. Re-issue authorization for the right env.",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Audit logging / 審計記錄
# ═══════════════════════════════════════════════════════════════════════════════


def _record_shadow_toggle_audit(
    *,
    actor_id: str,
    engine: str,
    target_shadow_mode: bool,
    source: str,
    success: bool,
    gate_failed: str | None,
    ipc_response: dict[str, Any] | None,
) -> None:
    """Write a STATE_CHANGE audit row (best effort; never blocks the request).

    Same pattern as `risk_routes._record_reset_drawdown_audit`. We log success
    AND failure (gate_failed branch) so post-mortem can see who tried + why
    it was rejected — not just the rare success path.

    沿用 risk_routes._record_reset_drawdown_audit 模式；成功 / 失敗都寫，
    post-mortem 可見「誰嘗試 + 為何被拒」，而不只記錄罕見的成功路徑。
    """
    try:
        from .governance_routes import _get_governance_hub  # lazy import
        hub = _get_governance_hub()
    except Exception as exc:  # noqa: BLE001
        logger.warning("executor.shadow-toggle audit: hub lazy import failed: %s", exc)
        return

    if hub is None or getattr(hub, "_change_audit_log", None) is None:
        # Fail-soft: log a warning so the gap is visible. Mirrors risk_routes behavior.
        # Fail-soft：警告記下缺口（與 risk_routes 行為一致）。
        logger.warning(
            "executor.shadow-toggle audit: change_audit_log unavailable — "
            "actor=%s engine=%s success=%s gate_failed=%s (Root Principle #8 trace gap)",
            actor_id, engine, success, gate_failed,
        )
        return

    try:
        from .change_audit_log import ChangeType
        verdict = "applied" if success else "denied"
        what = (
            f"ExecutorAgent shadow_mode flip → {target_shadow_mode} on engine={engine} ({verdict})"
        )
        hub._change_audit_log.record_change(
            change_type=ChangeType.STATE_CHANGE,
            who=actor_id,
            what=what,
            reason=f"source={source}; gate_failed={gate_failed or 'none'}",
            old_value={"engine": engine, "verdict": "request"},
            new_value={
                "shadow_mode": target_shadow_mode,
                "verdict": verdict,
                "gate_failed": gate_failed,
                "ipc_result": ipc_response,
            },
            affected_components=[
                f"executor:{engine}",
                "rust:RiskConfig.executor.shadow_mode",
            ],
            auto_approve=True,  # actor already passed Operator-role gate
        )
    except Exception as exc:  # noqa: BLE001 — audit must never break the request
        logger.warning("executor.shadow-toggle audit write failed: %s", exc)


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════


@executor_router.post("/shadow-toggle")
async def post_executor_shadow_toggle(
    body: ShadowToggleRequest,
    actor: Any = Depends(base.current_actor),
) -> dict[str, Any]:
    """POST /api/v1/executor/shadow-toggle — Operator flip ExecutorAgent shadow_mode.

    Auth flow (per RFC §4.4 + task spec):
      - All requests: Operator role required (current_actor + role check).
      - shadow_mode=False on engine="live": full 5-gate chain
        (Operator + live_reserved + OPENCLAW_ALLOW_MAINNET + secret slot +
        authorization.json HMAC/expiry/env_allowed).
      - shadow_mode=False on engine="demo": Operator role only.
      - shadow_mode=True (retreat) on any engine: Operator role only.
      - paper engine: Operator role only.

    On gate success, calls IPC `patch_risk_config` with the executor sub-patch
    and returns version + applied + ts. The Phase A IPC handler does the
    Rust-side ConfigStore swap + TOML persist + audit row. Once Rust has the
    new value, ExecutorConfigCache (Phase B) picks it up on next poll
    (`OPENCLAW_EXECUTOR_CACHE_POLL_SEC`, default 10s) and the next
    Guardian-approved intent flips its execution path.

    Operator 翻轉 ExecutorAgent shadow_mode 的 API；shadow→live 在 live engine
    上需通過完整 5-gate；demo / paper 僅需 Operator 角色；任何方向退回 shadow
    永遠便宜（principle #6）。

    Returns:
      200 + envelope on success
      400 invalid engine
      401 unauth (handled by current_actor)
      403 + {gate_failed, hint} on gate denial
      500 IPC failure
    """
    # ── Step 1: validate engine ──
    if body.engine not in _ALLOWED_ENGINES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid engine {body.engine!r}; must be one of {sorted(_ALLOWED_ENGINES)}",
        )

    # ── Step 2: gate (varies by engine + direction) ──
    target_shadow = body.shadow_mode
    actor_id = str(getattr(actor, "actor_id", "?"))
    try:
        if target_shadow is True:
            # Retreat to shadow — always cheap (Operator role only).
            # 退回 shadow — 永遠便宜（僅 Operator 角色）。
            from .governance_routes import _require_operator_role
            _require_operator_role(actor)
        else:
            # shadow_mode=False (enable real submit) — engine-conditional gate.
            # shadow_mode=False（解鎖真實送單）— 視 engine 套用不同門控。
            if body.engine == "paper":
                _verify_paper_gate(actor)
            elif body.engine == "demo":
                _verify_demo_gate(actor)
            elif body.engine == "live":
                _verify_live_gate(actor)
            else:  # pragma: no cover — _ALLOWED_ENGINES covers this
                raise HTTPException(status_code=400, detail="unreachable engine branch")
    except HTTPException as exc:
        # Audit denial. Extract gate name from the structured 403 detail when present.
        # 審計拒絕；從 403 結構化 detail 取 gate 名（若有）。
        gate_failed: str | None = None
        if exc.status_code == 403 and isinstance(exc.detail, dict):
            gate_failed = exc.detail.get("gate_failed")
        elif exc.status_code == 403:
            gate_failed = "operator_role"
        elif exc.status_code == 401:
            gate_failed = "unauthenticated"
        _record_shadow_toggle_audit(
            actor_id=actor_id,
            engine=body.engine,
            target_shadow_mode=target_shadow,
            source=body.source,
            success=False,
            gate_failed=gate_failed,
            ipc_response=None,
        )
        raise

    # ── Step 3: dispatch IPC patch_risk_config ──
    # Reuses Phase A's existing IPC handler — partial-merge semantics already
    # cover the executor sub-config, validated by 4 IPC e2e Rust tests in
    # commits 16c97c1 / 03acedb / 3bed899.
    # 沿用 Phase A 的 patch_risk_config IPC（partial-merge 已覆蓋 executor 子欄位）。
    patch_payload = {
        "executor": {
            "shadow_mode": target_shadow,
        },
    }
    try:
        ipc_response = await one_shot_ipc_call(
            "patch_risk_config",
            params={
                "engine": body.engine,
                "patch": patch_payload,
                "source": body.source,
            },
            timeout=5.0,
            wrap_errors_as_http=False,
            error_context="executor_shadow_toggle",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "executor.shadow-toggle IPC failed engine=%s shadow=%s source=%s err=%s",
            body.engine, target_shadow, body.source, exc,
        )
        # Audit IPC failure for post-mortem.
        # 審計 IPC 失敗（post-mortem 用）。
        _record_shadow_toggle_audit(
            actor_id=actor_id,
            engine=body.engine,
            target_shadow_mode=target_shadow,
            source=body.source,
            success=False,
            gate_failed="ipc_unavailable",
            ipc_response=None,
        )
        raise HTTPException(
            status_code=500,
            detail=f"rust_engine_unavailable: patch_risk_config: {exc}",
        ) from exc

    # ── Step 4: success — record audit + return envelope ──
    response_data = {
        "ok": True,
        "engine": body.engine,
        "applied": {"shadow_mode": target_shadow},
        "version": ipc_response.get("version") if isinstance(ipc_response, dict) else None,
        "ts_ms": int(time.time() * 1000),
        "source": body.source,
        "actor": actor_id,
        "ipc_response": ipc_response,
    }
    logger.warning(
        "executor.shadow-toggle SUCCESS actor=%s engine=%s shadow=%s source=%s version=%s",
        actor_id, body.engine, target_shadow, body.source, response_data["version"],
    )
    _record_shadow_toggle_audit(
        actor_id=actor_id,
        engine=body.engine,
        target_shadow_mode=target_shadow,
        source=body.source,
        success=True,
        gate_failed=None,
        ipc_response=ipc_response if isinstance(ipc_response, dict) else None,
    )
    return response_data


__all__ = [
    "executor_router",
    "ShadowToggleRequest",
]
