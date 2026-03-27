#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_latest_consistency_check.py

Role:
- 检查当前 readonly observer / business-event 相关 latest 文件之间的引用一致性
- 重点检查 packet / verdict / runtime / summary / audit / handoff / business_event_state 等对象是否互相对齐

Purpose in system:
- 这是人工维护安全层
- 用来发现“某个 latest 文件已经刷新，但下游还没同步”这类隐蔽问题
- 适合在每次大改脚本后做最终 consistency 验收

Checks included:
- packet.source_snapshot_ts_ms == snapshot.ts_ms
- verdict.source_packet_ts_ms == packet.ts_ms
- runtime.business_event_state == business_event_state.state_code
- summary.business_event_status.state_code == runtime.business_event_state
- handoff.business_event_status.state_code == runtime.business_event_state
- summary.latest_packet.ts_ms == packet.ts_ms
- summary.latest_verdict.ts_ms == verdict.ts_ms

Maintenance notes:
- 这是 D22.6 的“横向一致性检查器”
- 如果后续字段名改动，必须同步修改这里
'''
"""

import json
import time
from pathlib import Path

SNAPSHOT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")
PACKET_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")
RUNTIME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")
SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_readonly_final_summary_latest.json")
HANDOFF_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_next_phase_handoff_latest.json")
AUDIT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_readonly_audit_latest.json")
BUSINESS_EVENT_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_latest_consistency_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def add_check(checks, name, ok, detail):
    checks.append({
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    })


def main():
    snapshot = load_json(SNAPSHOT_PATH)
    packet = load_json(PACKET_PATH)
    verdict = load_json(VERDICT_PATH)
    runtime = load_json(RUNTIME_PATH)
    summary = load_json(SUMMARY_PATH)
    handoff = load_json(HANDOFF_PATH)
    audit = load_json(AUDIT_PATH)
    business_event_state = load_json(BUSINESS_EVENT_STATE_PATH)

    snapshot_ts = snapshot.get("snapshot_ts_ms") or snapshot.get("ts_ms")
    packet_ts = packet.get("ts_ms")
    verdict_ts = verdict.get("ts_ms")
    runtime_business_state = runtime.get("business_event_state")
    source_business_state = business_event_state.get("state_code")

    checks = []

    add_check(
        checks,
        "packet_snapshot_ref_matches_snapshot",
        packet.get("source_refs", {}).get("source_snapshot_ts_ms") == snapshot_ts,
        {
            "packet": packet.get("source_refs", {}).get("source_snapshot_ts_ms"),
            "snapshot": snapshot_ts,
        },
    )

    add_check(
        checks,
        "verdict_packet_ref_matches_packet",
        verdict.get("source_packet_ts_ms") == packet_ts,
        {
            "verdict": verdict.get("source_packet_ts_ms"),
            "packet": packet_ts,
        },
    )

    add_check(
        checks,
        "runtime_business_event_state_matches_source",
        runtime_business_state == source_business_state,
        {
            "runtime": runtime_business_state,
            "source": source_business_state,
        },
    )

    add_check(
        checks,
        "summary_business_event_state_matches_runtime",
        summary.get("business_event_status", {}).get("state_code") == runtime_business_state,
        {
            "summary": summary.get("business_event_status", {}).get("state_code"),
            "runtime": runtime_business_state,
        },
    )

    add_check(
        checks,
        "handoff_business_event_state_matches_runtime",
        handoff.get("business_event_status", {}).get("state_code") == runtime_business_state,
        {
            "handoff": handoff.get("business_event_status", {}).get("state_code"),
            "runtime": runtime_business_state,
        },
    )

    add_check(
        checks,
        "summary_packet_ts_matches_packet",
        summary.get("latest_packet", {}).get("ts_ms") == packet_ts,
        {
            "summary": summary.get("latest_packet", {}).get("ts_ms"),
            "packet": packet_ts,
        },
    )

    add_check(
        checks,
        "summary_verdict_ts_matches_verdict",
        summary.get("latest_verdict", {}).get("ts_ms") == verdict_ts,
        {
            "summary": summary.get("latest_verdict", {}).get("ts_ms"),
            "verdict": verdict_ts,
        },
    )

    add_check(
        checks,
        "audit_overall_ok_true",
        audit.get("overall_ok") is True,
        audit.get("overall_ok"),
    )

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_latest_consistency_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed) == 0,
        "total_checks": len(checks),
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")


if __name__ == "__main__":
    main()
