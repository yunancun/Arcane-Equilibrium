#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
LATEST_PATH = BASE / "bybit_decision_lease_chapter_summary_latest.json"

EXPECTED_STAGES = [f"I{i}" for i in range(1, 10)]

STAGE_KEYWORDS = {
    "I1": [
        "decision_lease_schema",
        "decision_lease_final_audit",
    ],
    "I2": [
        "decision_lease_preflight",
        "decision_lease_shadow_issue",
        "decision_lease_shadow_audit",
        "decision_lease_shadow_final_audit",
    ],
    "I3": [
        "decision_lease_consume_policy",
        "decision_lease_consume_gate",
        "decision_lease_consume_final_audit",
    ],
    "I4": [
        "decision_lease_replay_policy",
        "decision_lease_replay_guard",
        "decision_lease_replay_final_audit",
    ],
    "I5": [
        "decision_lease_friction_metrics",
        "decision_lease_adaptive_ttl",
        "decision_lease_friction_final_audit",
    ],
    "I6": [
        "decision_lease_approval_bridge",
    ],
    "I7": [
        "execution_authority_aggregator",
    ],
    "I8": [
        "manual_approval_packet",
    ],
    "I9": [
        "operator_ack_shadow",
    ],
}


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def as_list(v: Any) -> List[Any]:
    return v if isinstance(v, list) else []


def merged_unique(*parts: Any) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for part in parts:
        for item in as_list(part):
            if item is None:
                continue
            key = json.dumps(item, ensure_ascii=False, sort_keys=True) if isinstance(item, (dict, list)) else str(item)
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def normalize_stage_name(stage: Any) -> Optional[str]:
    if not isinstance(stage, str):
        return None
    head = stage.split("-", 1)[0]
    if head in EXPECTED_STAGES:
        return head
    if stage in EXPECTED_STAGES:
        return stage
    return None


def any_closed_state(obj: Dict[str, Any]) -> bool:
    bad_markers = ("not_closed", "blocked", "failed", "invalid", "error")
    for k, v in obj.items():
        if not (k.endswith("_state") and isinstance(v, str)):
            continue
        vv = v.strip().lower()
        if "closed" in vv and not any(marker in vv for marker in bad_markers):
            return True
    return False


def any_stage_closed_flag(obj: Dict[str, Any]) -> bool:
    for k, v in obj.items():
        if isinstance(v, bool) and v is True:
            if k.endswith("_stage_closed") or k.endswith("_chapter_closed"):
                return True
    return False


def any_ready_flag(obj: Dict[str, Any]) -> bool:
    for k, v in obj.items():
        if isinstance(v, bool) and v is True and k.startswith("ready_for_"):
            return True
    return False


def audit_summary_closed(obj: Dict[str, Any]) -> bool:
    audit_summary = obj.get("audit_summary") or {}
    if not isinstance(audit_summary, dict):
        return False
    for k, v in audit_summary.items():
        if isinstance(v, bool) and v is True:
            if k.endswith("_stage_closed") or k.endswith("_chapter_closed") or k.startswith("ready_for_"):
                return True
    return False


def object_closes_stage(obj: Dict[str, Any]) -> bool:
    for k in (
        "overall_ok",
        "audit_ok",
        "summary_ok",
        "handoff_ok",
        "schema_ok",
        "decision_ok",
        "gate_ok",
        "runtime_ok",
        "log_ok",
    ):
        if obj.get(k) is True:
            return True

    if any_stage_closed_flag(obj):
        return True
    if any_closed_state(obj):
        return True
    if any_ready_flag(obj):
        return True
    if audit_summary_closed(obj):
        return True

    return False


def choose_best_stage_obj(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not candidates:
        return None

    scored = []
    for item in candidates:
        obj = item["obj"]
        path = item["path"]
        score = 0

        if object_closes_stage(obj):
            score += 100

        lower = path.name.lower()
        if "final_audit" in lower:
            score += 30
        if "handoff" in lower:
            score += 20
        if "summary" in lower:
            score += 15
        if "audit" in lower:
            score += 10

        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]


def save_report(report: Dict[str, Any], latest_path: Path) -> None:
    ts_ms = report.get("ts_ms")
    dated_path = latest_path.with_name(latest_path.stem.replace("_latest", f"_{ts_ms}") + latest_path.suffix)
    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dated_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


def main() -> None:
    now_ms = int(time.time() * 1000)
    all_latest_files = sorted(BASE.glob("*_latest.json"))

    stage_candidates: Dict[str, List[Dict[str, Any]]] = {s: [] for s in EXPECTED_STAGES}
    source_errors: List[str] = []

    # pass 1: 先按 stage 字段识别
    seen_paths_by_stage: Dict[str, set] = {s: set() for s in EXPECTED_STAGES}
    for p in all_latest_files:
        obj = read_json(p)
        if not isinstance(obj, dict):
            continue

        raw_stage = obj.get("stage")
        stage = normalize_stage_name(raw_stage)
        if stage in stage_candidates:
            discovery_mode = "stage_field" if raw_stage == stage else "normalized_stage_field"
            stage_candidates[stage].append(
                {"path": p, "obj": obj, "discovery_mode": discovery_mode}
            )
            seen_paths_by_stage[stage].add(str(p))

    # pass 2: 如果某 stage 还没识别到，再按文件名关键词补
    for stage in EXPECTED_STAGES:
        if stage_candidates[stage]:
            continue

        keywords = STAGE_KEYWORDS.get(stage, [])
        for p in all_latest_files:
            name = p.name.lower()
            if not any(kw in name for kw in keywords):
                continue

            obj = read_json(p)
            if not isinstance(obj, dict):
                continue

            if str(p) in seen_paths_by_stage[stage]:
                continue

            stage_candidates[stage].append(
                {"path": p, "obj": obj, "discovery_mode": "filename_keyword"}
            )
            seen_paths_by_stage[stage].add(str(p))

    stage_sources: Dict[str, Optional[str]] = {}
    stage_discovery_mode: Dict[str, Optional[str]] = {}
    stage_status: Dict[str, bool] = {}
    chosen_objs: Dict[str, Optional[Dict[str, Any]]] = {}

    for stage in EXPECTED_STAGES:
        chosen = choose_best_stage_obj(stage_candidates[stage])
        if chosen is None:
            stage_sources[stage] = None
            stage_discovery_mode[stage] = None
            stage_status[stage] = False
            chosen_objs[stage] = None
            source_errors.append(f"{stage.lower()}_stage_source_missing")
            continue

        stage_sources[stage] = str(chosen["path"])
        stage_discovery_mode[stage] = chosen.get("discovery_mode")
        chosen_objs[stage] = chosen["obj"]
        stage_status[stage] = object_closes_stage(chosen["obj"])

        if not stage_status[stage]:
            source_errors.append(f"{stage.lower()}_stage_not_closed")

    runtime_view: Dict[str, Any] = {}
    for stage in ["I9", "I8", "I7", "I6", "I5", "I4", "I3", "I2", "I1"]:
        obj = chosen_objs.get(stage)
        if not isinstance(obj, dict):
            continue
        for k in (
            "ack_runtime_view",
            "schema_runtime_view",
            "bridge_runtime_view",
            "runtime_view",
            "schema_runtime",
        ):
            maybe = obj.get(k)
            if isinstance(maybe, dict) and maybe:
                runtime_view = maybe
                break
        if runtime_view:
            break

    execution_authority = runtime_view.get("execution_authority", "not_granted")
    decision_lease_emitted = runtime_view.get("decision_lease_emitted", False)
    live_operator_ack_enabled = runtime_view.get("live_operator_ack_enabled", False)

    runtime_still_protected = (
        execution_authority == "not_granted"
        and decision_lease_emitted is False
        and live_operator_ack_enabled is False
    )

    i_chapter_closed = all(stage_status.values()) and len(stage_status) == 9
    summary_ok = i_chapter_closed and runtime_still_protected

    if summary_ok:
        summary_state = "decision_lease_chapter_closed_shadow_ready_for_future_live_design"
        recommended_action = "may_progress_to_i10_handoff_and_archive"
        operator_message = (
            "I chapter summary complete. I1~I9 are closed as a shadow-only decision-lease control plane, "
            "while runtime remains protected."
        )
        ready_for_future_live_design = True
    else:
        summary_state = "decision_lease_chapter_not_closed"
        recommended_action = "inspect_i10_stage_discovery_failures"
        operator_message = "I chapter summary indicates closure is not yet complete."
        ready_for_future_live_design = False

    warning_flags = merged_unique(
        *(obj.get("warning_flags") for obj in chosen_objs.values() if isinstance(obj, dict))
    )

    report = {
        "summary_type": "bybit_decision_lease_chapter_summary",
        "summary_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I10",
        "summary_ok": summary_ok,
        "source_integrity": {
            "source_errors": source_errors,
            "stage_sources": stage_sources,
            "stage_discovery_mode": stage_discovery_mode,
            "discovered_latest_file_count": len(all_latest_files),
        },
        "stage_status": stage_status,
        "chapter_summary": {
            "i_chapter_closed": i_chapter_closed,
            "shadow_control_plane_closed": i_chapter_closed,
            "runtime_still_protected": runtime_still_protected,
            "ready_for_future_live_design": ready_for_future_live_design,
            "execution_authority": execution_authority,
            "decision_lease_emitted": decision_lease_emitted,
            "live_operator_ack_enabled": live_operator_ack_enabled,
        },
        "warning_flags": warning_flags,
        "summary_state": summary_state,
        "recommended_action": recommended_action,
        "operator_message": operator_message,
    }

    save_report(report, LATEST_PATH)


if __name__ == "__main__":
    main()
