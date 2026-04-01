from __future__ import annotations

"""
MODULE_NOTE (中文):
  Runtime 快照橋接層 — 允許控制 API 從外部 runtime 產出的標準 JSON 快照文件
  讀取真實事實（system_mode / execution_state 等）。若無快照文件則保持本地
  guarded-demo 行為不變。屬於數據層，連接外部 runtime 與內部狀態編譯。

MODULE_NOTE (English):
  Runtime Snapshot Bridge — allows the Control API to read real facts from a
  normalized JSON snapshot file produced by the external runtime (system_mode,
  execution_state, etc.). Falls back to local guarded-demo behavior when no
  snapshot file is provided. Part of data layer, bridging external runtime
  with internal state compilation.

Safety invariant:
  快照文件缺失或損壞時回退至本地默認值（fail-safe），不會暴露未驗證的狀態。
  Missing or corrupted snapshot falls back to local defaults (fail-safe).
"""

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any


RUNTIME_FACT_KEYS = {
    "system_mode_fact",
    "execution_state_fact",
    "runtime_last_refresh_ts_ms",
    "runtime_data_freshness_state",
}

PRODUCT_FACT_KEYS = {
    "exchange_permission_fact",
    "account_permission_fact",
}

SYSTEM_MODE_FACT_TO_OVERVIEW_MODE = {
    "observe_only": "observe_only",
    "shadow_only": "shadow_only",
    "design_only": "design_only",
    "demo_reserved": "demo_reserved",
    "live_reserved": "live_reserved",
}


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_runtime_snapshot_file_path() -> str | None:
    path = os.getenv("OPENCLAW_RUNTIME_SNAPSHOT_FILE")
    return path.strip() if path and path.strip() else None


def load_runtime_snapshot_payload() -> dict[str, Any] | None:
    path = get_runtime_snapshot_file_path()
    if not path:
        return None

    snapshot_path = Path(path)
    if not snapshot_path.exists() or not snapshot_path.is_file():
        return None

    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def overlay_runtime_facts(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = load_runtime_snapshot_payload()
    if payload is None:
        return copy.deepcopy(snapshot)

    merged = copy.deepcopy(snapshot)

    runtime_facts = payload.get("global_runtime_facts")
    if isinstance(runtime_facts, dict):
        for key in RUNTIME_FACT_KEYS:
            if key in runtime_facts:
                merged["global_runtime"]["facts"][key] = runtime_facts[key]

        system_mode_fact = runtime_facts.get("system_mode_fact")
        if system_mode_fact in SYSTEM_MODE_FACT_TO_OVERVIEW_MODE:
            merged["global_runtime"]["derived"]["global_mode_state"] = SYSTEM_MODE_FACT_TO_OVERVIEW_MODE[system_mode_fact]

    product_family_facts = payload.get("product_family_facts")
    if isinstance(product_family_facts, dict):
        for product_family, facts in product_family_facts.items():
            if product_family not in merged.get("product_family_status", {}):
                continue
            if not isinstance(facts, dict):
                continue
            for key in PRODUCT_FACT_KEYS:
                if key in facts:
                    merged["product_family_status"][product_family]["facts"][key] = facts[key]

    health_telemetry = payload.get("health_telemetry")
    if isinstance(health_telemetry, dict):
        for section in ("scores", "metrics", "evaluation_context", "gates"):
            section_value = health_telemetry.get(section)
            if isinstance(section_value, dict) and isinstance(merged["health_telemetry"].get(section), dict):
                merged["health_telemetry"][section].update(section_value)

    snapshot_source_summary = merged.get("meta", {}).get("snapshot_source_summary")
    if isinstance(snapshot_source_summary, dict):
        snapshot_source_summary["runtime_latest_used"] = True

    return merged


def build_runtime_aware_source_context(snapshot: dict[str, Any], settings: Any, source_context_cls: type) -> Any:
    payload = load_runtime_snapshot_payload()
    if payload is None:
        execution_name = settings.execution_connector_name
        return source_context_cls(
            readonly_connector_name=settings.readonly_connector_name,
            readonly_connector_role="fact_source",
            readonly_connector_scope="private_readonly",
            execution_connector_name=execution_name,
            execution_connector_role="execution_source_reserved",
            execution_connector_scope="private_execution" if execution_name else "not_attached",
            connector_role_separation_ok=(execution_name is None or execution_name != settings.readonly_connector_name),
            rest_private_connection_state=settings.rest_private_connection_state,
            ws_private_connection_state=settings.ws_private_connection_state,
            runtime_connection_state=settings.runtime_connection_state,
            account_fact_completeness_state=settings.account_fact_completeness_state,
            source_snapshot_completeness_state=settings.source_snapshot_completeness_state,
            pinned_runtime_snapshot_id=f"runtime:{snapshot['meta']['snapshot_id']}",
            pinned_runtime_snapshot_ts_ms=snapshot["meta"]["snapshot_ts_ms"],
        )

    readonly_name = payload.get("readonly_connector_name") or settings.readonly_connector_name
    execution_name = payload.get("execution_connector_name")
    if execution_name is None:
        execution_name = settings.execution_connector_name

    runtime_snapshot_id = payload.get("runtime_snapshot_id") or payload.get("snapshot_id") or f"runtime:{snapshot['meta']['snapshot_id']}"
    runtime_snapshot_ts_ms = _safe_int(
        payload.get("runtime_snapshot_ts_ms", payload.get("snapshot_ts_ms", snapshot["meta"]["snapshot_ts_ms"])),
        snapshot["meta"]["snapshot_ts_ms"],
    )

    return source_context_cls(
        readonly_connector_name=readonly_name,
        readonly_connector_role="fact_source",
        readonly_connector_scope="private_readonly",
        execution_connector_name=execution_name,
        execution_connector_role="execution_source_reserved",
        execution_connector_scope="private_execution" if execution_name else "not_attached",
        connector_role_separation_ok=(execution_name is None or execution_name != readonly_name),
        rest_private_connection_state=payload.get("rest_private_connection_state") or settings.rest_private_connection_state,
        ws_private_connection_state=payload.get("ws_private_connection_state") or settings.ws_private_connection_state,
        runtime_connection_state=payload.get("runtime_connection_state") or settings.runtime_connection_state,
        account_fact_completeness_state=payload.get("account_fact_completeness_state") or settings.account_fact_completeness_state,
        source_snapshot_completeness_state=payload.get("source_snapshot_completeness_state") or settings.source_snapshot_completeness_state,
        pinned_runtime_snapshot_id=str(runtime_snapshot_id),
        pinned_runtime_snapshot_ts_ms=runtime_snapshot_ts_ms,
    )


def derive_response_snapshot_identity(snapshot: dict[str, Any], source_context: Any) -> tuple[int, str]:
    payload = load_runtime_snapshot_payload()
    if payload is None:
        return snapshot["meta"]["snapshot_ts_ms"], snapshot["meta"]["snapshot_id"]

    response_ts_ms = max(snapshot["meta"]["snapshot_ts_ms"], source_context.pinned_runtime_snapshot_ts_ms)
    identity_payload = {
        "state_snapshot_id": snapshot["meta"]["snapshot_id"],
        "state_revision": snapshot["meta"]["state_revision"],
        "runtime_snapshot_id": source_context.pinned_runtime_snapshot_id,
        "runtime_snapshot_ts_ms": source_context.pinned_runtime_snapshot_ts_ms,
    }
    digest = hashlib.sha1(json.dumps(identity_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return response_ts_ms, f"response:{snapshot['meta']['state_revision']}:{digest}"
