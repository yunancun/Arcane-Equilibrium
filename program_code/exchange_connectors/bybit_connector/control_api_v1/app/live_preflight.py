from __future__ import annotations

"""
MODULE_NOTE (中文):
  模塊用途：Live 寫入面共用的前置門控（preflight）原語。執行器 gate、
  live-session start/resume/grant、system-mode 切換都從這裡取得同一套判斷，
  避免 P1-01（驗簽用錯 secret 域）這類重複實作分叉。

  主要函數：
    - live_auth_signing_key()        — 取得 live-auth 簽名 key（單一來源）。
    - verify_signed_authorization()  — authorization.json schema+HMAC+期效+env
                                       驗證的唯一真相實作（從 executor_routes 搬入）。
    - engine_mode_readback()         — 包裝既有 Rust IPC "get_state"，回讀引擎
                                       實際 system_mode / trading_mode / status。
    - all_five_live_gates_ok()       — 整合 role + live_reserved 精確匹配 +
                                       OPENCLAW_ALLOW_MAINNET + secret slot +
                                       （選配）簽名授權，回 (ok, reason_codes)。

  依賴：live_trust_routes（簽名 key + canonical payload helpers，lazy import）、
       executor_routes（_gate_failure taxonomy、secret slot 路徑，lazy import）、
       ipc_dispatch.one_shot_ipc_call（讀回引擎狀態）。

  硬邊界（為何 fail-closed）：
    - Python 控制面狀態僅為 advisory，永不權威化 live readiness（PA ruling §0）。
    - 任何斷言 live 就緒的回應，必須有「IPC 成功 + 回讀」或「對齊 Rust 同一 key
      域的簽名驗證」背書；缺 secret / IPC 失敗 / snapshot stale 一律當失敗，
      不可 fail-open。
    - live_reserved 必須精確 ==，禁止 substring "live"（live_demo_observe 等
      含 "live" 子串的模式不得放行）。
"""

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 精確匹配的 live global mode。禁止 substring 比對（見 MODULE_NOTE 硬邊界）。
_REQUIRED_LIVE_GLOBAL_MODE = "live_reserved"


def live_auth_signing_key() -> str:
    """取得 live-auth 簽名 key（單一來源）。

    為何集中：P1-01 的 root cause 是 executor verifier 直讀 OPENCLAW_IPC_SECRET
    （IPC transport 域），而 signer（live_trust_routes）與 Rust live_authorization
    用的是 OPENCLAW_LIVE_AUTH_SIGNING_KEY。兩個 secret 域必須一致，否則合法簽名
    被拒、IPC-only 簽名卻能過。

    委派給 live_trust_routes._read_live_auth_signing_key()（OPS-2 Phase 2
    cutover 後純讀 OPENCLAW_LIVE_AUTH_SIGNING_KEY，無 IPC fallback）。

    Returns:
        非空簽名 key 字串；空字串代表 caller 必須 fail-closed。
    """
    from . import live_trust_routes as ltr  # noqa: PLC0415

    return ltr._read_live_auth_signing_key()


def verify_signed_authorization(slot_dir: Path, endpoint_label: str, actor: Any) -> None:
    """驗證 authorization.json schema + HMAC + 期效 + env_allowed（唯一真相實作）。

    本函數為 executor_routes._verify_authorization_json_or_raise 搬遷後的本體，
    唯一改動是 HMAC key 改用 live_auth_signing_key()（P1-01），不再直讀
    OPENCLAW_IPC_SECRET。其餘 schema / approved_system_mode / 期效 / env_allowed
    檢查與 _gate_failure taxonomy（authorization / _malformed / _schema /
    _signature / _expired / _env_mismatch）byte-for-byte 保留。

    為何 fail-closed：缺 key 無法驗 HMAC、簽名不符、過期、env 不含當前 endpoint
    都必須 raise，不可放行 — 對齊 Rust live_authorization::verify。

    Raises:
        HTTPException(403)：透過 executor_routes._gate_failure 建構，gate_failed
        欄位細分失敗原因供 operator 自診。
    """
    import hashlib
    import hmac as _hmac
    import json
    import time

    from . import executor_routes as er  # noqa: PLC0415
    from . import live_trust_routes as ltr  # noqa: PLC0415

    _gate_failure = er._gate_failure

    auth_path = slot_dir / "authorization.json"
    if not auth_path.exists():
        logger.warning(
            "live preflight FAIL gate=authorization actor=%s reason=missing path=%s",
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
            "live preflight FAIL gate=authorization actor=%s reason=malformed err=%s",
            getattr(actor, "actor_id", "?"), exc,
        )
        raise _gate_failure(
            "authorization_malformed",
            f"authorization.json parse error: {exc}",
        )

    if version != ltr._AUTHORIZATION_SCHEMA_VERSION:
        logger.warning(
            "live preflight FAIL gate=authorization_schema actor=%s version=%s",
            getattr(actor, "actor_id", "?"), version,
        )
        raise _gate_failure(
            "authorization_schema",
            f"authorization.json version={version} unsupported; "
            f"expected {ltr._AUTHORIZATION_SCHEMA_VERSION}. Run /api/v1/live/auth/renew.",
        )
    approved_system_mode = str(record.get("approved_system_mode", ""))
    if approved_system_mode != ltr._REQUIRED_LIVE_GLOBAL_MODE:
        logger.warning(
            "live preflight FAIL gate=authorization_schema actor=%s approved_system_mode=%s",
            getattr(actor, "actor_id", "?"), approved_system_mode,
        )
        raise _gate_failure(
            "authorization_schema",
            "authorization.json approved_system_mode must be live_reserved. "
            "Run /api/v1/live/auth/renew while Global Mode is live_reserved.",
        )

    # HMAC verify — 必須對齊 Rust compute_signature + Python _sign_authorization_payload。
    # P1-01：key 取自 live-auth 簽名域（live_auth_signing_key），不再用 IPC transport secret。
    signing_key = (live_auth_signing_key() or "").strip()
    if not signing_key:
        # 為何 fail-closed：缺 key 無法驗 HMAC，必須拒絕，不可 fail-open。
        logger.warning(
            "live preflight FAIL gate=authorization actor=%s reason=live_auth_key_missing",
            getattr(actor, "actor_id", "?"),
        )
        raise _gate_failure(
            "authorization",
            "OPENCLAW_LIVE_AUTH_SIGNING_KEY unset — cannot verify HMAC; set in "
            "engine env (OPS-2 Phase 2: no OPENCLAW_IPC_SECRET fallback).",
        )
    envs_sorted = sorted(set(env_allowed))
    payload = ltr._canonical_authorization_payload(
        version=version,
        tier=tier,
        issued_at_ms=issued_at_ms,
        expires_at_ms=expires_at_ms,
        operator_id=operator_id,
        approved_system_mode=approved_system_mode,
        env_allowed=envs_sorted,
    )
    sig_expected = _hmac.new(
        signing_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not _hmac.compare_digest(sig_expected, sig_recorded):
        logger.warning(
            "live preflight FAIL gate=authorization_signature actor=%s",
            getattr(actor, "actor_id", "?"),
        )
        raise _gate_failure(
            "authorization_signature",
            "authorization.json HMAC mismatch — signing key rotated or file tampered. "
            "Run /api/v1/live/auth/renew to re-sign.",
        )

    now_ms = int(time.time() * 1000)
    if expires_at_ms <= now_ms:
        logger.warning(
            "live preflight FAIL gate=authorization_expired actor=%s expires_at_ms=%d now_ms=%d",
            getattr(actor, "actor_id", "?"), expires_at_ms, now_ms,
        )
        raise _gate_failure(
            "authorization_expired",
            f"authorization.json expired at ts_ms={expires_at_ms} (now={now_ms}). "
            "Run /api/v1/live/auth/renew.",
        )

    if endpoint_label not in env_allowed:
        logger.warning(
            "live preflight FAIL gate=authorization_env_mismatch actor=%s endpoint=%s env_allowed=%s",
            getattr(actor, "actor_id", "?"), endpoint_label, env_allowed,
        )
        raise _gate_failure(
            "authorization_env_mismatch",
            f"authorization env_allowed={env_allowed} does not contain current "
            f"endpoint={endpoint_label!r}. Re-issue authorization for the right env.",
        )


async def engine_mode_readback(timeout: float = 3.0) -> dict:
    """讀回 Rust 引擎實際狀態（包裝既有 IPC "get_state"）。

    為何用 IPC 而非讀 pipeline_snapshot.json：IPC get_state 由引擎即時回應，
    代表引擎當下 posture；而 snapshot 檔可能 stale/missing。caller 收到本函數
    成功回傳即視為「引擎確認」；IPC 失敗時本函數 raise，由 caller 決定 fail-closed
    （PA ruling §0 INV-A1）。

    Returns:
        {"system_mode": str, "trading_mode": str, "status": str}（缺欄位回空字串）。

    Raises:
        HTTPException / 其他 IPC 例外：caller 必須 fail-closed，不可當成功。
    """
    from .ipc_dispatch import one_shot_ipc_call  # noqa: PLC0415

    result = await one_shot_ipc_call(
        "get_state",
        {},
        timeout=timeout,
        wrap_errors_as_http=True,
        error_context="engine_mode_readback",
    )
    # get_state 回傳 dict（misc.rs:54-63）；非 dict 時 one_shot_ipc_call 已包成
    # {"result": ...}，視為缺欄位（fail-closed 由 caller 判斷 system_mode 是否符合）。
    return {
        "system_mode": str(result.get("system_mode", "")),
        "trading_mode": str(result.get("trading_mode", "")),
        "status": str(result.get("status", "")),
    }


def _live_secret_slot_dir() -> Path:
    """解析 secret slot 目錄（遵守 OPENCLAW_SECRETS_DIR；跨平台，禁硬編碼 HOME）。

    與 executor_routes._live_secret_slot_dir / live_trust_routes._live_secret_slot_dir
    同一 precedence。
    """
    base_env = os.environ.get("OPENCLAW_SECRETS_DIR")
    if base_env:
        return Path(base_env) / "live"
    return Path.home() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit" / "live"


def all_five_live_gates_ok(
    actor: Any,
    *,
    require_authz: bool,
) -> tuple[bool, list[str]]:
    """整合 live 寫入面門控判斷，回 (ok, reason_codes)。

    依序評估：
      1. Operator 角色（governance_routes._require_operator_role）。
      2. global_mode == "live_reserved"（精確匹配，禁 substring）。
      3. OPENCLAW_ALLOW_MAINNET=1（僅 Mainnet endpoint 要求；live_demo 跳過此門
         但仍需 secret slot + 簽名授權）。
      4. live secret slot 有 api_key + api_secret。
      5. （require_authz=True 時）簽名 authorization.json 有效。

    為何不在內部 raise：caller（start/resume）需要把失敗收斂成統一回應
    （authority:"denied" / session_state:"inactive"），故回 reason_codes 而非
    直接拋。簽名驗證若失敗，verify_signed_authorization 仍會 raise；本函數捕捉
    其 gate_failed 加入 reason_codes，由 caller 決定回傳形態。

    Returns:
        (ok, reason_codes)：ok=True 代表全部門控通過；否則 reason_codes 列出
        失敗門控（fail-closed，順序短路）。
    """
    from . import live_trust_routes as ltr  # noqa: PLC0415
    from .governance_routes import _require_operator_role  # noqa: PLC0415

    reasons: list[str] = []

    # Gate 1: Operator 角色。
    try:
        _require_operator_role(actor)
    except Exception:
        reasons.append("operator_role")
        return False, reasons

    # Gate 2: global_mode 精確 == live_reserved（禁 substring "live"）。
    from . import live_session_routes as lsr  # noqa: PLC0415
    global_mode = lsr._get_global_mode_state()
    if global_mode != _REQUIRED_LIVE_GLOBAL_MODE:
        reasons.append("global_mode_not_live_reserved")
        return False, reasons

    # endpoint label 決定是否需要 Mainnet env gate。
    endpoint_label = ltr._current_bybit_endpoint_label()

    # Gate 3: Mainnet 才要求 OPENCLAW_ALLOW_MAINNET=1。
    if endpoint_label == ltr._ENV_MAINNET:
        if (os.environ.get("OPENCLAW_ALLOW_MAINNET") or "").strip() != "1":
            reasons.append("mainnet_env")
            return False, reasons

    # Gate 4: secret slot 有 api_key + api_secret。
    slot_dir = _live_secret_slot_dir()
    try:
        has_key = (slot_dir / "api_key").exists() and bool(
            (slot_dir / "api_key").read_text(encoding="utf-8").strip()
        )
        has_secret = (slot_dir / "api_secret").exists() and bool(
            (slot_dir / "api_secret").read_text(encoding="utf-8").strip()
        )
    except OSError:
        has_key = has_secret = False
    if not (has_key and has_secret):
        reasons.append("secret_slot")
        return False, reasons

    # Gate 5: 簽名 authorization.json（require_authz 時）。
    if require_authz:
        try:
            verify_signed_authorization(slot_dir, endpoint_label, actor)
        except Exception as exc:
            # 取出 _gate_failure 的 gate_failed 名稱（HTTPException.detail dict）。
            gate_name = "authorization"
            detail = getattr(exc, "detail", None)
            if isinstance(detail, dict) and detail.get("gate_failed"):
                gate_name = str(detail["gate_failed"])
            reasons.append(gate_name)
            return False, reasons

    return True, reasons


def four_gates_minus_authz_ok(actor: Any) -> tuple[bool, list[str]]:
    """評估「5-gate 中除 signed-auth 外的前 4 門」，回 (ok, reason_codes)。

    為何只重組、不新增/不放寬：本函數**不**自行實作任何門控判斷，而是直接委派
    all_five_live_gates_ok(actor, require_authz=False)。該權威 primitive 在
    require_authz=False 時恰好依序評估 Gate 1 (operator-role) / Gate 2
    (global_mode==live_reserved) / Gate 3 (OPENCLAW_ALLOW_MAINNET，僅 Mainnet) /
    Gate 4 (secret slot)，並**跳過** Gate 5 (signed authorization.json)。因此
    本 helper = 「前 4 門必過、第 5 門 (signed-auth) 豁免」，與單一真相
    all_five_live_gates_ok 共用 EXACT 同一份 gate 邏輯，零分叉。

    為何需要豁免第 5 門：POLICY-1 的 operator_override 路徑專供「signed-auth
    結構上不可達」場景（live halt 時 signed authorization 已被自動撤銷，
    require_authz=True 必然失敗，否則 halt 永遠無法恢復）。此 helper **只**豁免
    signed-auth，前 4 門（含 operator-role）一律不放寬——禁止用本函數繞過
    live_reserved / operator / ALLOW_MAINNET / secret-slot 任何一門。

    Returns:
        (ok, reason_codes)：ok=True 代表前 4 門全過；否則 reason_codes 列出
        失敗門控（fail-closed，順序短路）。reason_codes 永不含 "authorization*"，
        因 require_authz=False 不評估第 5 門。
    """
    return all_five_live_gates_ok(actor, require_authz=False)
