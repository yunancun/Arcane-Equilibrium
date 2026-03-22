#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_readonly_audit.py
Role:
- 做跨文件一致性审计
- 检查 version / refs / freshness / runtime / summary / handoff / business_event_state 是否一致

Purpose in system:
- 是当前阶段最后一道一致性检查
- 最容易暴露“改了一个文件忘了同步别处”的问题

Current integrated stage:
- 已接入 business event state
- 当前版本应为 v2

Maintenance notes:
- 改任何 version / 引用字段 / 状态枚举，优先同步这里
- audit fail 不一定是逻辑错，也可能只是版本规则没更新
'''

"""

import json
import time
from pathlib import Path

SNAPSHOT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")
PACKET_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")
ACCEPTANCE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_observer_acceptance_latest.json")
RUNTIME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")
FINAL_SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_readonly_final_summary_latest.json")
HANDOFF_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_next_phase_handoff_latest.json")
WS_FACTS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_ws_runtime_facts_latest.json")
PREFLIGHT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_private_rest_preflight_latest.json")
BUSINESS_EVENT_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_readonly_audit_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def add(checks, name, ok, detail=None):
    checks.append({
        "name": name,
        "ok": bool(ok),
        "detail": detail
    })


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_readonly_audit_{ts_ms}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")
    print(text)
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


def main():
    snapshot = load_json(SNAPSHOT_PATH)
    packet = load_json(PACKET_PATH)
    verdict = load_json(VERDICT_PATH)
    acceptance = load_json(ACCEPTANCE_PATH)
    runtime = load_json(RUNTIME_PATH)
    final_summary = load_json(FINAL_SUMMARY_PATH)
    handoff = load_json(HANDOFF_PATH)
    ws_facts = load_json(WS_FACTS_PATH)
    preflight = load_json(PREFLIGHT_PATH)
    business_event_state = load_json(BUSINESS_EVENT_STATE_PATH)

    # 兼容不同版本 snapshot 时间字段
    snapshot_ts = (
        snapshot.get("snapshot_ts_ms")
        or snapshot.get("ts_ms")
        or (snapshot.get("source_refs") or {}).get("source_snapshot_ts_ms")
    )

    checks = []

    add(checks, "snapshot_exists", SNAPSHOT_PATH.exists(), str(SNAPSHOT_PATH))
    add(checks, "packet_exists", PACKET_PATH.exists(), str(PACKET_PATH))
    add(checks, "verdict_exists", VERDICT_PATH.exists(), str(VERDICT_PATH))
    add(checks, "acceptance_exists", ACCEPTANCE_PATH.exists(), str(ACCEPTANCE_PATH))
    add(checks, "runtime_exists", RUNTIME_PATH.exists(), str(RUNTIME_PATH))
    add(checks, "final_summary_exists", FINAL_SUMMARY_PATH.exists(), str(FINAL_SUMMARY_PATH))
    add(checks, "handoff_exists", HANDOFF_PATH.exists(), str(HANDOFF_PATH))
    add(checks, "ws_facts_exists", WS_FACTS_PATH.exists(), str(WS_FACTS_PATH))
    add(checks, "preflight_exists", PREFLIGHT_PATH.exists(), str(PREFLIGHT_PATH))
    add(checks, "business_event_state_exists", BUSINESS_EVENT_STATE_PATH.exists(), str(BUSINESS_EVENT_STATE_PATH))

    add(checks, "snapshot_version_v2", snapshot.get("snapshot_version") == "v2", snapshot.get("snapshot_version"))
    add(checks, "packet_version_v4", packet.get("packet_version") == "v4", packet.get("packet_version"))
    add(checks, "verdict_version_v4", verdict.get("verdict_version") == "v4", verdict.get("verdict_version"))
    add(checks, "acceptance_version_v4", acceptance.get("report_version") == "v4", acceptance.get("report_version"))
    add(checks, "runtime_version_v5", runtime.get("state_version") == "v5", runtime.get("state_version"))
    add(checks, "final_summary_version_v4", final_summary.get("summary_version") == "v4", final_summary.get("summary_version"))
    add(checks, "handoff_version_v3", handoff.get("handoff_version") == "v3", handoff.get("handoff_version"))
    add(checks, "business_event_state_version_v1", business_event_state.get("state_version") == "v1", business_event_state.get("state_version"))

    add(
        checks,
        "packet_snapshot_ref_matches_snapshot",
        (packet.get("source_refs") or {}).get("source_snapshot_ts_ms") == snapshot_ts,
        {
            "packet": (packet.get("source_refs") or {}).get("source_snapshot_ts_ms"),
            "snapshot": snapshot_ts,
        }
    )

    add(
        checks,
        "verdict_packet_ref_matches_packet",
        verdict.get("source_packet_ts_ms") == packet.get("ts_ms"),
        {
            "verdict": verdict.get("source_packet_ts_ms"),
            "packet": packet.get("ts_ms"),
        }
    )

    add(checks, "acceptance_passed", acceptance.get("overall_passed") is True, acceptance.get("overall_passed"))
    add(checks, "runtime_ready", runtime.get("overall_runtime_state") == "ready_readonly_observer", runtime.get("overall_runtime_state"))
    add(checks, "verdict_observe_only", verdict.get("verdict_code") == "OBSERVE_ONLY", verdict.get("verdict_code"))
    add(checks, "preflight_allowed", preflight.get("allowed_to_continue") is True, preflight.get("allowed_to_continue"))
    add(checks, "ws_connected", ws_facts.get("connection_state") == "connected", ws_facts.get("connection_state"))

    payload_freshness = runtime.get("payload_freshness") or {}
    add(checks, "account_payload_fresh", payload_freshness.get("account_payload_state") == "fresh", payload_freshness.get("account_payload_state"))
    add(checks, "positions_payload_fresh", payload_freshness.get("positions_payload_state") == "fresh", payload_freshness.get("positions_payload_state"))
    add(checks, "order_history_payload_fresh", payload_freshness.get("order_history_payload_state") == "fresh", payload_freshness.get("order_history_payload_state"))
    add(checks, "execution_payload_fresh", payload_freshness.get("execution_history_payload_state") == "fresh", payload_freshness.get("execution_history_payload_state"))

    allowed_business_states = {
        "healthy_no_business_events_yet",
        "healthy_business_events_present",
        "stale_or_missing_business_event_feed",
    }

    add(
        checks,
        "business_event_state_allowed",
        runtime.get("business_event_state") in allowed_business_states,
        runtime.get("business_event_state"),
    )

    add(
        checks,
        "business_event_state_matches_source",
        runtime.get("business_event_state") == business_event_state.get("state_code"),
        {
            "runtime": runtime.get("business_event_state"),
            "source": business_event_state.get("state_code"),
        }
    )

    add(
        checks,
        "business_event_state_healthy_matches_source",
        runtime.get("business_event_healthy") == business_event_state.get("healthy"),
        {
            "runtime": runtime.get("business_event_healthy"),
            "source": business_event_state.get("healthy"),
        }
    )

    add(
        checks,
        "summary_business_event_state_matches_runtime",
        ((final_summary.get("business_event_status") or {}).get("state_code")) == runtime.get("business_event_state"),
        {
            "summary": (final_summary.get("business_event_status") or {}).get("state_code"),
            "runtime": runtime.get("business_event_state"),
        }
    )

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "audit_type": "bybit_readonly_audit",
        "audit_version": "v2",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "total_checks": len(checks),
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    save_json(obj)


if __name__ == "__main__":
    main()
