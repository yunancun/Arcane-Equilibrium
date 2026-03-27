#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_build_observer_verdict.py
Role:
- 基于 decision packet 生成 observer verdict
- 当前标准 verdict 通常为 OBSERVE_ONLY

Purpose in system:
- 给出本地只读观察结论
- 是 runtime / summary / handoff / audit 的关键输入

Downstream:
- bybit_observer_verdict_to_postgres.py
- bybit_runtime_state_resolver.py
- bybit_readonly_final_summary.py
- bybit_readonly_audit.py

Maintenance notes:
- OBSERVE_ONLY 是当前健康状态
- 当前不是交易执行 verdict 生成器
'''

"""

import json
import time
from pathlib import Path

PACKET_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path: Path):
    """Load JSON from disk, returning None if the file does not exist."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

def now_ms():
    return int(time.time() * 1000)

def main():
    packet = load_json(PACKET_PATH)
    if packet is None:
        print(f"ERROR: decision packet not found at {PACKET_PATH}")
        return

    risk_flags = packet.get("risk_flags") or []
    local_hints = packet.get("local_decision_hints") or {}
    account_summary = packet.get("account_summary") or {}
    position_summary = packet.get("position_summary") or {}
    order_summary = packet.get("order_summary") or {}
    execution_summary = packet.get("execution_summary") or {}
    freshness = packet.get("freshness") or {}
    ws_runtime_summary = packet.get("ws_runtime_summary") or {}
    source_refs = packet.get("source_refs") or {}

    snapshot_age_ms = freshness.get("snapshot_age_ms")
    ws_runtime_signal = ws_runtime_summary.get("signal_strength")
    ws_listener_health = ws_runtime_summary.get("listener_health")

    verdict_generated_ts_ms = now_ms()

    verdict_code = "OBSERVE_ONLY"
    execution_allowed = False
    should_refresh_rest = False
    should_query_ai = bool(local_hints.get("should_query_ai"))
    urgency = "low"
    reasons = []
    next_steps = [
        "continue observe-only mode",
        "do not enable execution",
        "do not query AI unless later gating explicitly turns it on"
    ]

    if isinstance(snapshot_age_ms, int) and snapshot_age_ms > 15 * 60 * 1000:
        verdict_code = "REFRESH_REQUIRED"
        should_refresh_rest = True
        urgency = "medium"
        reasons = [
            "private REST snapshot is stale > 15m"
        ]
        next_steps = [
            "refresh private REST snapshot first",
            "do not enable execution",
            "do not query AI unless later gating explicitly turns it on"
        ]
    else:
        if position_summary.get("nonzero_position_count", 0) == 0:
            reasons.append("no open positions detected")
        if execution_summary.get("total_execution_count", 0) == 0:
            reasons.append("no recent execution history detected")
        if order_summary.get("order_count", 0) == 0:
            reasons.append("no recent order history detected")
        if ws_runtime_signal == "control_only":
            reasons.append("persistent WS connected but no business topic events observed yet")
        if ws_listener_health == "idle_but_connected":
            reasons.append("persistent WS is alive but currently idle")

    verdict = {
        "verdict_type": "bybit_observer_verdict",
        "verdict_version": "v4",
        "ts_ms": verdict_generated_ts_ms,
        "verdict_generated_ts_ms": verdict_generated_ts_ms,
        "exchange": "bybit",
        "mode": "read_only",
        "source_packet_ts_ms": packet.get("ts_ms"),
        "source_packet_generated_ts_ms": packet.get("packet_generated_ts_ms"),
        "source_packet_freshness_reference_ts_ms": packet.get("freshness_reference_ts_ms"),
        "source_packet_path": str(PACKET_PATH),
        "source_refs": source_refs,
        "verdict_code": verdict_code,
        "execution_allowed": execution_allowed,
        "should_refresh_rest": should_refresh_rest,
        "should_query_ai": should_query_ai,
        "urgency": urgency,
        "account_summary": {
            "total_equity": account_summary.get("total_equity"),
            "usdt_wallet_balance": account_summary.get("usdt_wallet_balance")
        },
        "position_summary": {
            "nonzero_position_count": position_summary.get("nonzero_position_count"),
            "symbols": position_summary.get("symbols") or []
        },
        "order_summary": {
            "order_count": order_summary.get("order_count")
        },
        "execution_summary": {
            "total_execution_count": execution_summary.get("total_execution_count")
        },
        "ws_runtime_summary": {
            "listener_health": ws_runtime_summary.get("listener_health"),
            "connection_state": ws_runtime_summary.get("connection_state"),
            "signal_strength": ws_runtime_summary.get("signal_strength"),
            "business_signal_state": ws_runtime_summary.get("business_signal_state"),
            "connection_activity_state": ws_runtime_summary.get("connection_activity_state"),
            "control_message_count_estimate": ws_runtime_summary.get("control_message_count_estimate"),
            "business_message_count_estimate": ws_runtime_summary.get("business_message_count_estimate"),
            "business_topic_event_count": ws_runtime_summary.get("business_topic_event_count"),
            "last_event_age_ms": ws_runtime_summary.get("last_event_age_ms")
        },
        "freshness": {
            **freshness,
            "verdict_generated_ts_ms": verdict_generated_ts_ms
        },
        "risk_flags": risk_flags,
        "reasons": reasons,
        "next_steps": next_steps
    }

    latest_path = OUT_DIR / "bybit_observer_verdict_latest.json"
    dated_path = OUT_DIR / f"bybit_observer_verdict_{verdict_generated_ts_ms}.json"

    latest_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")

if __name__ == "__main__":
    main()
