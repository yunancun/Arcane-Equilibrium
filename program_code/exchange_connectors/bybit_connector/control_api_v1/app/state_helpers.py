"""
MODULE_NOTE (中文):
  狀態操作輔助函數模塊。包含請求指紋計算、版本斷言、冪等性緩存、
  審計字段寫入等純狀態操作。從 main_legacy.py 拆分而來。

  ★ 注意：依賴 settings 單例的函數（build_source_context / envelope_response /
  get_latest_snapshot / build_authenticated_actor / current_actor）留在 main_legacy.py，
  因為多個測試依賴 importlib.reload(main_legacy) 來重建 Settings 實例。

MODULE_NOTE (English):
  State operation helper functions module. Contains request fingerprint calculation,
  revision assertions, idempotency cache, audit field writing, and other pure state
  operations. Extracted from main_legacy.py.

  ★ Note: Functions that depend on the settings singleton (build_source_context /
  envelope_response / get_latest_snapshot / build_authenticated_actor / current_actor)
  remain in main_legacy.py because multiple tests rely on importlib.reload(main_legacy)
  to recreate the Settings instance.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from fastapi import HTTPException, status

from .state_compiler import now_ms
from .state_models import RequestEnvelope, SourceContext

logger = logging.getLogger(__name__)


def request_fingerprint(envelope: RequestEnvelope) -> str:
    payload = envelope.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def ensure_source_is_usable(source_context: SourceContext) -> None:
    if source_context.runtime_connection_state in {"down", "unknown"}:
        raise HTTPException(status_code=503, detail={"reason_codes": ["runtime_fact_unavailable"]})
    if source_context.rest_private_connection_state in {"down", "unknown"}:
        raise HTTPException(status_code=503, detail={"reason_codes": ["connector_unavailable"]})
    if source_context.source_snapshot_completeness_state == "missing":
        raise HTTPException(status_code=503, detail={"reason_codes": ["source_snapshot_incomplete"]})


def _assert_revision(snapshot: dict[str, Any], envelope: RequestEnvelope) -> None:
    # KNOWN LIMITATION: This revision check runs BEFORE STORE.mutate() acquires the lock.
    # Under concurrent requests, the revision could change between this check and the
    # actual mutation. The risk is low because the mutator re-reads current state inside
    # the lock. A full fix would move revision checking into mutate() itself.
    # 已知限制：此版本检查在 STORE.mutate() 获取锁之前运行。
    if envelope.expected_state_revision != snapshot["meta"]["state_revision"]:
        raise HTTPException(status_code=409, detail={"reason_codes": ["state_revision_mismatch"]})


def _assert_previous_state(snapshot: dict[str, Any], envelope: RequestEnvelope, allowed: set[str] | None = None) -> None:
    current = snapshot["control_plane"]["demo_control"]["demo_state_switch"]
    expected = envelope.expected_previous_state
    if expected is None or expected != current or (allowed is not None and current not in allowed):
        raise HTTPException(status_code=409, detail={"reason_codes": ["previous_state_mismatch"]})


def _check_idempotency(snapshot: dict[str, Any], envelope: RequestEnvelope) -> dict[str, Any] | None:
    record = snapshot["records"]["idempotency"].get(envelope.idempotency_key)
    if record is None:
        return None
    if record["fingerprint"] != request_fingerprint(envelope):
        raise HTTPException(status_code=409, detail={"reason_codes": ["idempotency_conflict"]})
    return record["response"]


_IDEMPOTENCY_TTL_MS = 24 * 60 * 60 * 1000  # 24 小时 / 24 hours
_IDEMPOTENCY_MAX_ENTRIES = 500  # 最大缓存条目 / Max cached entries


def _store_idempotent_response(state: dict[str, Any], envelope: RequestEnvelope, response: dict[str, Any]) -> None:
    stored_response = dict(response)
    stored_response.pop("snapshot", None)
    cache = state["records"]["idempotency"]
    cache[envelope.idempotency_key] = {
        "request_id": envelope.request_id,
        "fingerprint": request_fingerprint(envelope),
        "stored_ts_ms": now_ms(),
        "response": stored_response,
    }
    # 清理过期和超量条目 / Cleanup expired and overflow entries
    _cleanup_idempotency_cache(cache)


def _cleanup_idempotency_cache(cache: dict[str, Any]) -> None:
    """移除过期和超量的幂等性缓存条目 / Remove expired and overflow idempotency cache entries."""
    # Fast path: skip all work when cache is well under limit (avoids O(n) scan on every store)
    if len(cache) <= _IDEMPOTENCY_MAX_ENTRIES // 2:
        return
    cutoff = now_ms() - _IDEMPOTENCY_TTL_MS
    expired_keys = [k for k, v in cache.items() if v.get("stored_ts_ms", 0) < cutoff]
    for k in expired_keys:
        del cache[k]
    # O(n log n) sort only when over limit — guarded by size check
    if len(cache) > _IDEMPOTENCY_MAX_ENTRIES:
        sorted_keys = sorted(cache.keys(), key=lambda k: cache[k].get("stored_ts_ms", 0))
        for k in sorted_keys[: len(cache) - _IDEMPOTENCY_MAX_ENTRIES]:
            del cache[k]


def _write_audit_fields(
    state: dict[str, Any],
    *,
    action_type: str,
    operator_id: str,
    request_id: str,
    result: str,
    reason_codes: list[str],
    is_control_action: bool,
) -> str:
    ts = now_ms()
    audit_ref = f"audit:{action_type}:{ts}"
    audit = state["audit_context"]
    audit["last_state_revision_before"] = state["meta"]["state_revision"]
    audit["last_state_revision_after"] = state["meta"]["state_revision"] + 1

    audit["last_write_action_type"] = action_type
    audit["last_write_action_request_id"] = request_id
    audit["last_write_action_ts_ms"] = ts
    audit["last_write_action_by"] = operator_id
    audit["last_write_action_result"] = result
    audit["last_write_action_reason_codes"] = list(reason_codes)
    audit["last_write_action_audit_ref"] = audit_ref

    if is_control_action:
        audit["last_control_action_type"] = action_type
        audit["last_control_action_request_id"] = request_id
        audit["last_control_action_ts_ms"] = ts
        audit["last_control_action_by"] = operator_id
        audit["last_control_action_result"] = result
        audit["last_control_action_reason_codes"] = list(reason_codes)
        audit["last_control_action_audit_ref"] = audit_ref

        audit["last_operator_action_type"] = action_type
        audit["last_operator_action_ts_ms"] = ts
        audit["last_operator_action_result"] = result
        audit["last_operator_action_operator"] = operator_id
        audit["last_operator_action_target"] = "control_plane"
        audit["last_operator_action_request_id"] = request_id
        audit["last_operator_action_reason_codes"] = list(reason_codes)
        audit["last_operator_action_audit_ref"] = audit_ref

    return audit_ref


def _bump_revision(state: dict[str, Any]) -> None:
    state["meta"]["state_revision"] += 1


def _blocked(reason_codes: list[str]) -> None:
    raise HTTPException(status_code=422, detail={"reason_codes": reason_codes})
