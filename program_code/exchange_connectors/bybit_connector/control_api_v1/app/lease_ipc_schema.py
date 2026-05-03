"""
Lease IPC Schema — Python ↔ Rust JSON-RPC 2.0 envelope for Decision Lease.
租约 IPC 协议结构 — Python 与 Rust 之间的 JSON-RPC 2.0 信封封装。

MODULE_NOTE (EN):
    Pure-data schema definitions for the Decision Lease retrofit IPC bridge
    (REF-20 Sprint 3 Track H E-3). This module owns:

      1. JSON-RPC method names (string constants) for governance.acquire_lease /
         governance.release_lease / governance.get_lease.
      2. Canonical request param keys + response result keys (avoid stringly-typed
         drift between Python and Rust serde structs).
      3. Helper builders for params dicts (build_acquire_request_params,
         build_release_request_params, build_get_request_params).
      4. Helper parsers for response payloads (parse_acquire_response,
         parse_release_response, parse_get_response).
      5. Sentinel constants for the SHADOW_BYPASS short-circuit path
         (caller never enters IPC; lease_id placeholder).

    This module is the byte-equal contract anchor: any change here MUST be
    mirrored to Rust serde structs in dispatch.rs governance handler. Tests
    pin canonical key spellings + JSON serialization order so accidental drift
    fails fast (REF-20 W8 P6 envelope-signing pattern, scoped to lease).

    Zero side-effects on import; zero singletons; zero IPC clients held here.
    governance_lease_bridge.py owns the actual EngineIPCClient call sites.

MODULE_NOTE (中):
    Decision Lease retrofit IPC 通道（REF-20 Sprint 3 Track H E-3）所用的
    純資料 schema 定義。本模組負責：

      1. JSON-RPC method 名稱（字串常量）：governance.acquire_lease /
         governance.release_lease / governance.get_lease。
      2. canonical 的 request params / response result 鍵集（避免 Python 與
         Rust serde 結構之間出現 stringly-typed 漂移）。
      3. params dict 構造輔助（build_acquire_request_params 等）。
      4. response payload 解析輔助（parse_acquire_response 等）。
      5. SHADOW_BYPASS 短路路徑用的 sentinel（caller 完全不進 IPC；lease_id
         占位字串）。

    本模組是 byte-equal contract 的錨點 — 此處任一改動都必鏡像至 Rust
    dispatch.rs governance handler 的 serde 結構。測試釘 canonical 鍵拼寫
    + JSON 序列化順序，意外漂移會立即 fail（REF-20 W8 P6 envelope-signing
    模式，scope 限縮在 lease）。

    純資料、無副作用、無 singleton、不持有 IPC client。
    governance_lease_bridge.py 才是真正持有 EngineIPCClient 呼叫點的位置。

Safety guarantees / 安全保證:
  - No side effects on import / 匯入無副作用
  - No singletons / 無 singleton
  - Stringly-typed contracts pinned by tests / 字串契約由測試釘住
  - All schema changes require Rust mirror update / 任何改動需同步 Rust 鏡像
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


# ═══════════════════════════════════════════════════════════════════════════════
# JSON-RPC method names / JSON-RPC 方法名稱
# ═══════════════════════════════════════════════════════════════════════════════

# Rust dispatch.rs governance handler must register exactly these three method
# names. Any rename triggers cross-language smoke test failure.
# Rust dispatch.rs governance handler 必須註冊此三方法名；任一改名觸發跨語言
# smoke test 失敗。

METHOD_ACQUIRE_LEASE: str = "governance.acquire_lease"
METHOD_RELEASE_LEASE: str = "governance.release_lease"
METHOD_GET_LEASE: str = "governance.get_lease"


# ═══════════════════════════════════════════════════════════════════════════════
# Request param keys (canonical) / 請求參數鍵（canonical）
# ═══════════════════════════════════════════════════════════════════════════════

# Acquire request (POST → Rust): all keys MUST appear in this order in Rust serde.
# Acquire 請求（往 Rust 發）：Rust serde 中鍵順序必與此處一致。
ACQUIRE_KEY_INTENT_ID: str = "intent_id"
ACQUIRE_KEY_SCOPE: str = "scope"
ACQUIRE_KEY_TTL_MS: str = "ttl_ms"          # Python ttl_seconds × 1000
ACQUIRE_KEY_PROFILE: str = "profile"        # "Production" / "Validation" / "Exploration"
ACQUIRE_KEY_SOURCE_STAGE: str = "source_stage"  # "executor_agent_python" / "router" / "scout" ...

# Release request:
RELEASE_KEY_LEASE_ID: str = "lease_id"
RELEASE_KEY_OUTCOME: str = "outcome"        # "Consumed" / "Failed" / "Cancelled"

# Get request:
GET_KEY_LEASE_ID: str = "lease_id"


# ═══════════════════════════════════════════════════════════════════════════════
# Response result keys / 回應結果鍵
# ═══════════════════════════════════════════════════════════════════════════════

# Acquire response result (Rust → Python):
# Rust E-1 facade returns LeaseId enum: Active(String) | Bypass.
# Serde shape is one of:
#   {"lease_id": "lease:abc...", "outcome": "Active"}
#   {"lease_id": "bypass",        "outcome": "Bypass"}
# This Python schema flattens to a dict so the caller layer sees a stable shape.
# Rust E-1 facade 回 LeaseId enum：Active(String) | Bypass。serde 形狀為其一：
#   {"lease_id": "lease:abc...", "outcome": "Active"}
#   {"lease_id": "bypass",        "outcome": "Bypass"}
# 本 Python schema 把 enum 攤平成 dict，caller 層看到穩定形狀。
RESPONSE_KEY_LEASE_ID: str = "lease_id"
RESPONSE_KEY_OUTCOME: str = "outcome"        # Acquire only

# Release response: {"ok": true} or error envelope; no positive payload field.
# Release 回應：{"ok": true} 或錯誤封包；無正向 payload 欄位。
RESPONSE_KEY_OK: str = "ok"

# Get response: serialized LeaseObject (Rust serde of LeaseObject struct).
# Schema follows decision_lease_state_machine.LeaseObject equivalent fields:
#   lease_id / state / scope / created_by / created_at_ms / expires_at_ms / ...
# Get 回應：序列化的 LeaseObject（Rust serde 的 LeaseObject 結構）。
# 對齊 Python decision_lease_state_machine.LeaseObject 的欄位 schema。


# ═══════════════════════════════════════════════════════════════════════════════
# Outcome / Profile / Scope canonical strings / 標準字串
# ═══════════════════════════════════════════════════════════════════════════════

# Acquire response outcome enum (mirror of Rust LeaseId discriminant):
OUTCOME_ACTIVE: str = "Active"
OUTCOME_BYPASS: str = "Bypass"

# Release request outcome enum (mirror of Rust LeaseOutcome enum):
OUTCOME_CONSUMED: str = "Consumed"
OUTCOME_FAILED: str = "Failed"
OUTCOME_CANCELLED: str = "Cancelled"

# Profile enum (mirror of Rust GovernanceProfile):
PROFILE_PRODUCTION: str = "Production"
PROFILE_VALIDATION: str = "Validation"
PROFILE_EXPLORATION: str = "Exploration"

# Default Python source stage (executor_agent.py:454 caller path):
DEFAULT_SOURCE_STAGE_PY_EXECUTOR: str = "executor_agent_python"


# ═══════════════════════════════════════════════════════════════════════════════
# Sentinels / 占位字串
# ═══════════════════════════════════════════════════════════════════════════════

# SHADOW_BYPASS sentinel — returned by caller-side short-circuit when
# shadow_mode_provider() reports True. The IPC layer is NEVER engaged on this
# path; Rust SM never sees the call; no audit row is emitted.
# This sentinel string is opaque to executor_agent.py:454 (it just needs a
# truthy str so the fail-closed branch at L459 does not reject the order).
# Format: SHADOW_BYPASS:<intent_id> for trace-back in logs.
#
# SHADOW_BYPASS sentinel — 當 shadow_mode_provider() 回報 True 時，caller 端
# 短路返回此 sentinel；IPC 層完全不啟動；Rust SM 不會見到本次呼叫；audit row
# 也不會 emit。executor_agent.py:454 看到此字串時，僅判斷其為 truthy str，
# L459 的 fail-closed 分支不會拒絕該訂單（保持 shadow path 既有行為）。
# 格式：SHADOW_BYPASS:<intent_id>，方便 log 追溯。
SHADOW_BYPASS_PREFIX: str = "SHADOW_BYPASS:"


def make_shadow_bypass_lease_id(intent_id: str) -> str:
    """Build the SHADOW_BYPASS sentinel for a given intent.
    為指定 intent 構造 SHADOW_BYPASS sentinel。

    Args / 參數:
        intent_id: caller-supplied intent id / caller 提供的 intent id

    Returns / 回傳:
        ``SHADOW_BYPASS:<intent_id>`` — opaque truthy string for caller compat.
        ``SHADOW_BYPASS:<intent_id>`` — caller 兼容的不透明 truthy 字串。
    """
    return f"{SHADOW_BYPASS_PREFIX}{intent_id}"


def is_shadow_bypass_lease_id(lease_id: str) -> bool:
    """Detect a shadow bypass sentinel (so callers can skip release_lease IPC).
    檢測是否為 shadow bypass sentinel（以便 caller 跳過 release_lease IPC）。

    Args / 參數:
        lease_id: lease_id string returned by acquire_lease().

    Returns / 回傳:
        True if the string is a SHADOW_BYPASS sentinel; False otherwise.
        若為 SHADOW_BYPASS sentinel 則 True；否則 False。
    """
    return isinstance(lease_id, str) and lease_id.startswith(SHADOW_BYPASS_PREFIX)


# ═══════════════════════════════════════════════════════════════════════════════
# Request builders / 請求建構
# ═══════════════════════════════════════════════════════════════════════════════

def build_acquire_request_params(
    *,
    intent_id: str,
    scope: str,
    ttl_seconds: float,
    profile: str = PROFILE_PRODUCTION,
    source_stage: str = DEFAULT_SOURCE_STAGE_PY_EXECUTOR,
) -> dict[str, Any]:
    """Construct the JSON-RPC params dict for governance.acquire_lease.
    構造 governance.acquire_lease 的 JSON-RPC params 字典。

    Converts ttl_seconds (Python float) → ttl_ms (Rust u32). The Rust facade
    rejects ttl_ms outside [100, 300_000]; we let Rust enforce that boundary
    rather than duplicating the check here (single source of truth: Rust spec).
    將 ttl_seconds（Python float）轉為 ttl_ms（Rust u32）。Rust facade 會拒絕
    [100, 300_000] 以外的 ttl_ms；本層不重複檢查邊界（單一真實來源 = Rust spec）。

    Args / 參數:
        intent_id: trade intent unique id / 交易 intent 唯一 id
        scope: e.g. "TRADE_ENTRY" / "TRADE_EXIT" / 例如交易進場、退場
        ttl_seconds: 0.1-300 / 0.1-300 秒
        profile: "Production" / "Validation" / "Exploration"
        source_stage: telemetry tag / 遙測標籤

    Returns / 回傳:
        params dict with canonical keys / canonical 鍵的 params 字典

    Raises / 例外:
        TypeError if any required arg is wrong type / 任一必需參數型別錯誤
    """
    if not isinstance(intent_id, str) or not intent_id:
        raise TypeError("intent_id must be non-empty str / intent_id 必為非空 str")
    if not isinstance(scope, str) or not scope:
        raise TypeError("scope must be non-empty str / scope 必為非空 str")
    if not isinstance(ttl_seconds, (int, float)) or ttl_seconds <= 0:
        raise TypeError("ttl_seconds must be positive number / ttl_seconds 必為正數")
    if profile not in (PROFILE_PRODUCTION, PROFILE_VALIDATION, PROFILE_EXPLORATION):
        raise TypeError(
            f"profile must be one of Production/Validation/Exploration / "
            f"profile 必為 Production/Validation/Exploration: got {profile!r}"
        )

    return {
        ACQUIRE_KEY_INTENT_ID: intent_id,
        ACQUIRE_KEY_SCOPE: scope,
        ACQUIRE_KEY_TTL_MS: int(ttl_seconds * 1000),
        ACQUIRE_KEY_PROFILE: profile,
        ACQUIRE_KEY_SOURCE_STAGE: source_stage,
    }


def build_release_request_params(
    *,
    lease_id: str,
    outcome: str = OUTCOME_CONSUMED,
) -> dict[str, Any]:
    """Construct params dict for governance.release_lease.
    構造 governance.release_lease 的 params 字典。

    Args / 參數:
        lease_id: previously acquired lease id (NOT a SHADOW_BYPASS sentinel —
            caller must short-circuit before calling this builder).
            先前 acquire 的 lease id（不可為 SHADOW_BYPASS sentinel — caller
            必須在呼叫此 builder 前自行短路）。
        outcome: "Consumed" / "Failed" / "Cancelled"

    Raises / 例外:
        TypeError on bad args / 參數錯誤時拋出
        ValueError if lease_id looks like SHADOW_BYPASS / 若 lease_id 為
            SHADOW_BYPASS 則拋出（caller bug — 不該走到 IPC）
    """
    if not isinstance(lease_id, str) or not lease_id:
        raise TypeError("lease_id must be non-empty str / lease_id 必為非空 str")
    if is_shadow_bypass_lease_id(lease_id):
        raise ValueError(
            "SHADOW_BYPASS sentinel must not reach IPC builder; caller must "
            "short-circuit. / SHADOW_BYPASS sentinel 不應到達 IPC builder；"
            "caller 必須短路。"
        )
    if outcome not in (OUTCOME_CONSUMED, OUTCOME_FAILED, OUTCOME_CANCELLED):
        raise TypeError(
            f"outcome must be Consumed/Failed/Cancelled / "
            f"outcome 必為 Consumed/Failed/Cancelled: got {outcome!r}"
        )

    return {
        RELEASE_KEY_LEASE_ID: lease_id,
        RELEASE_KEY_OUTCOME: outcome,
    }


def build_get_request_params(*, lease_id: str) -> dict[str, Any]:
    """Construct params dict for governance.get_lease.
    構造 governance.get_lease 的 params 字典。
    """
    if not isinstance(lease_id, str) or not lease_id:
        raise TypeError("lease_id must be non-empty str / lease_id 必為非空 str")
    if is_shadow_bypass_lease_id(lease_id):
        raise ValueError(
            "SHADOW_BYPASS sentinel must not reach IPC builder. / "
            "SHADOW_BYPASS sentinel 不應到達 IPC builder。"
        )
    return {GET_KEY_LEASE_ID: lease_id}


# ═══════════════════════════════════════════════════════════════════════════════
# Response parsers / 回應解析
# ═══════════════════════════════════════════════════════════════════════════════

def parse_acquire_response(result: Mapping[str, Any]) -> tuple[Optional[str], str]:
    """Parse the JSON-RPC result for governance.acquire_lease.
    解析 governance.acquire_lease 的 JSON-RPC result。

    Args / 參數:
        result: dict produced by ``EngineIPCClient.call(METHOD_ACQUIRE_LEASE)``.
            ``EngineIPCClient.call(METHOD_ACQUIRE_LEASE)`` 回傳的 dict。

    Returns / 回傳:
        ``(lease_id, outcome)`` tuple. ``lease_id`` is None if the response
        is malformed (caller treats as fail-closed); ``outcome`` is the raw
        canonical string ("Active" / "Bypass") or empty string on malformed.
        ``(lease_id, outcome)`` 二元組。回應畸形時 ``lease_id=None``（caller
        視為 fail-closed）；``outcome`` 為原始 canonical 字串或空字串。

    Note / 注意:
        Rust facade may wrap the result in a ``"result"`` shell when called
        through ``ipc_dispatch.one_shot_ipc_call`` (see ipc_dispatch.py L106).
        We accept either flat or wrapped shape so this parser is resilient
        to either dispatch helper choice.
        Rust facade 透過 ``ipc_dispatch.one_shot_ipc_call`` 呼叫時，result 可能
        被包在 ``"result"`` 殼裡（見 ipc_dispatch.py L106）。本 parser 同時接受
        平攤與包裝兩種形狀，以對任一 dispatch helper 選擇穩健。
    """
    if not isinstance(result, Mapping):
        return (None, "")

    # Unwrap if shape is {"result": {...}} (one_shot_ipc_call non-dict wrapping).
    # 若形狀為 {"result": {...}}（one_shot_ipc_call 對非 dict 的包裝）則拆殼。
    payload: Mapping[str, Any] = result
    inner = result.get("result")
    if isinstance(inner, Mapping) and RESPONSE_KEY_LEASE_ID in inner:
        payload = inner

    lease_id_val = payload.get(RESPONSE_KEY_LEASE_ID)
    outcome_val = payload.get(RESPONSE_KEY_OUTCOME, "")
    if not isinstance(lease_id_val, str) or not lease_id_val:
        return (None, "")
    if not isinstance(outcome_val, str):
        outcome_val = ""

    return (lease_id_val, outcome_val)


def parse_release_response(result: Mapping[str, Any]) -> bool:
    """Parse JSON-RPC result for governance.release_lease.
    解析 governance.release_lease 的 JSON-RPC result。

    Args / 參數:
        result: response payload / 回應 payload

    Returns / 回傳:
        True if the response indicates success (``ok=true``); False otherwise.
        Malformed payload → False (caller treats as fail-soft).
        若回應指示成功（``ok=true``）則 True；否則 False。
        畸形 payload → False（caller 視為 fail-soft）。
    """
    if not isinstance(result, Mapping):
        return False
    payload: Mapping[str, Any] = result
    inner = result.get("result")
    if isinstance(inner, Mapping) and RESPONSE_KEY_OK in inner:
        payload = inner
    ok_val = payload.get(RESPONSE_KEY_OK)
    return ok_val is True


def parse_get_response(result: Mapping[str, Any]) -> Optional[Mapping[str, Any]]:
    """Parse JSON-RPC result for governance.get_lease (returns LeaseObject dict).
    解析 governance.get_lease 的 JSON-RPC result（回傳 LeaseObject dict）。

    Args / 參數:
        result: response payload / 回應 payload

    Returns / 回傳:
        Lease object dict (Rust serde of LeaseObject) on success; None when not
        found, payload malformed, or outcome indicates absence. Caller may
        adapt this to a dataclass instance if needed.
        成功時回傳 lease object dict（Rust serde 的 LeaseObject）；找不到、
        payload 畸形、或 outcome 指示不存在時回 None。caller 可視需要將其轉為
        dataclass 實例。
    """
    if not isinstance(result, Mapping):
        return None
    payload: Mapping[str, Any] = result
    inner = result.get("result")
    if isinstance(inner, Mapping):
        payload = inner
    if not payload:
        return None
    # The Rust LeaseObject struct includes lease_id; absence indicates
    # "lease not found" → caller treats as None.
    # Rust LeaseObject 結構含 lease_id；缺欄位視為「lease not found」→ None。
    if RESPONSE_KEY_LEASE_ID not in payload:
        return None
    return payload


__all__ = [
    # Method names
    "METHOD_ACQUIRE_LEASE",
    "METHOD_RELEASE_LEASE",
    "METHOD_GET_LEASE",
    # Acquire keys
    "ACQUIRE_KEY_INTENT_ID",
    "ACQUIRE_KEY_SCOPE",
    "ACQUIRE_KEY_TTL_MS",
    "ACQUIRE_KEY_PROFILE",
    "ACQUIRE_KEY_SOURCE_STAGE",
    # Release/Get keys
    "RELEASE_KEY_LEASE_ID",
    "RELEASE_KEY_OUTCOME",
    "GET_KEY_LEASE_ID",
    # Response keys
    "RESPONSE_KEY_LEASE_ID",
    "RESPONSE_KEY_OUTCOME",
    "RESPONSE_KEY_OK",
    # Outcome / Profile constants
    "OUTCOME_ACTIVE",
    "OUTCOME_BYPASS",
    "OUTCOME_CONSUMED",
    "OUTCOME_FAILED",
    "OUTCOME_CANCELLED",
    "PROFILE_PRODUCTION",
    "PROFILE_VALIDATION",
    "PROFILE_EXPLORATION",
    "DEFAULT_SOURCE_STAGE_PY_EXECUTOR",
    # Sentinels
    "SHADOW_BYPASS_PREFIX",
    "make_shadow_bypass_lease_id",
    "is_shadow_bypass_lease_id",
    # Builders
    "build_acquire_request_params",
    "build_release_request_params",
    "build_get_request_params",
    # Parsers
    "parse_acquire_response",
    "parse_release_response",
    "parse_get_response",
]
