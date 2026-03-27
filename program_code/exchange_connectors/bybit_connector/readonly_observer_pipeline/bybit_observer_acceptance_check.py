#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_observer_acceptance_check.py
Role:
- 根据当前 readonly observer 产物做阶段验收
- 生成 overall_passed / failed_checks

Purpose in system:
- 定义“当前观察器是否通过验收”的标准
- 是 runtime_state_resolver 的重要输入

Maintenance notes:
- 最常见失败原因是 freshness 过期，而不是代码损坏
- 修改阈值或检查项时，要同步 summary / audit 理解
'''

"""

import json
import time
from pathlib import Path

CYCLE_SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_observer_cycle_latest.json")
DECISION_PACKET_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")
PERSISTENT_WS_STATUS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/ws_persistent/bybit_private_ws_listener_status_latest.json")
WS_RUNTIME_FACTS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_ws_runtime_facts_latest.json")
PREFLIGHT_GUARD_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_private_rest_preflight_latest.json")
SNAPSHOT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_VERDICTS = {"OBSERVE_ONLY", "REFRESH_REQUIRED"}
MAX_SNAPSHOT_AGE_MS = 15 * 60 * 1000

def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

def main():
    now_ms = int(time.time() * 1000)

    cycle = load_json(CYCLE_SUMMARY_PATH)
    packet = load_json(DECISION_PACKET_PATH)
    verdict = load_json(VERDICT_PATH)
    persistent_ws = load_json(PERSISTENT_WS_STATUS_PATH)
    ws_facts = load_json(WS_RUNTIME_FACTS_PATH)
    preflight = load_json(PREFLIGHT_GUARD_PATH)
    snapshot = load_json(SNAPSHOT_PATH)

    checks = []

    def add(name, passed, detail):
        checks.append({
            "name": name,
            "passed": bool(passed),
            "detail": detail
        })

    add("cycle_summary_exists", cycle is not None, str(CYCLE_SUMMARY_PATH))
    add("decision_packet_exists", packet is not None, str(DECISION_PACKET_PATH))
    add("observer_verdict_exists", verdict is not None, str(VERDICT_PATH))
    add("persistent_ws_status_exists", persistent_ws is not None, str(PERSISTENT_WS_STATUS_PATH))
    add("ws_runtime_facts_exists", ws_facts is not None, str(WS_RUNTIME_FACTS_PATH))
    add("preflight_guard_exists", preflight is not None, str(PREFLIGHT_GUARD_PATH))
    add("snapshot_exists", snapshot is not None, str(SNAPSHOT_PATH))

    if cycle:
        add("cycle_overall_ok", cycle.get("overall_ok") is True, cycle.get("overall_ok"))

    if packet:
        add("packet_version_v4", packet.get("packet_version") == "v4", packet.get("packet_version"))
        add("packet_mode_read_only", packet.get("mode") == "read_only", packet.get("mode"))
        add("packet_ai_hint_false", (packet.get("local_decision_hints") or {}).get("should_query_ai") is False,
            (packet.get("local_decision_hints") or {}).get("should_query_ai"))
        snap_ts = ((packet.get("source_refs") or {}).get("source_snapshot_ts_ms"))
        if isinstance(snap_ts, int):
            add("snapshot_age_within_15m", (now_ms - snap_ts) <= MAX_SNAPSHOT_AGE_MS, now_ms - snap_ts)

    if verdict:
        add("verdict_version_v4", verdict.get("verdict_version") == "v4", verdict.get("verdict_version"))
        add("verdict_execution_disabled", verdict.get("execution_allowed") is False, verdict.get("execution_allowed"))
        add("verdict_code_expected", verdict.get("verdict_code") in ALLOWED_VERDICTS, verdict.get("verdict_code"))

    if persistent_ws:
        add("persistent_ws_running", persistent_ws.get("running") is True, persistent_ws.get("running"))
        add("persistent_ws_auth_ok", (persistent_ws.get("auth_ok_count") or 0) >= 1, persistent_ws.get("auth_ok_count"))
        add("persistent_ws_subscribe_ok", (persistent_ws.get("subscribe_ok_count") or 0) >= 1, persistent_ws.get("subscribe_ok_count"))

    if ws_facts:
        add("ws_facts_present", ws_facts.get("present") is True, ws_facts.get("present"))
        add("ws_connection_connected", ws_facts.get("connection_state") == "connected", ws_facts.get("connection_state"))
        add("ws_signal_known", ws_facts.get("signal_strength") in {"control_only", "business_active", "none"},
            ws_facts.get("signal_strength"))

    if preflight:
        add("preflight_allowed", preflight.get("allowed_to_continue") is True, preflight.get("allowed_to_continue"))

    if snapshot:
        pts = snapshot.get("payload_time_summary") or {}
        add("snapshot_version_v2", snapshot.get("snapshot_version") == "v2", snapshot.get("snapshot_version"))
        add("snapshot_payload_times_present",
            all(pts.get(k) is not None for k in [
                "account_payload_ts_ms",
                "positions_payload_ts_ms",
                "order_history_payload_ts_ms",
                "execution_history_payload_ts_ms",
            ]),
            pts)

    failed = [c for c in checks if not c["passed"]]

    report = {
        "report_type": "bybit_observer_acceptance_check",
        "report_version": "v4",
        "ts_ms": now_ms,
        "overall_passed": len(failed) == 0,
        "passed_count": len(checks) - len(failed),
        "total_checks": len(checks),
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    latest = OUT_DIR / "bybit_observer_acceptance_latest.json"
    dated = OUT_DIR / f"bybit_observer_acceptance_{now_ms}.json"
    txt = json.dumps(report, ensure_ascii=False, indent=2)
    latest.write_text(txt + "\n", encoding="utf-8")
    dated.write_text(txt + "\n", encoding="utf-8")

    print(txt)
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")

if __name__ == "__main__":
    main()
