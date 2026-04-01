#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_build_decision_packet.py
Role:
- 汇总 snapshot / ws smoke / ws runtime facts / preflight
- 生成 observer 决策输入包 decision packet

Purpose in system:
- 是 observer verdict 的直接上游
- 统一各来源信息，减少下游重复解析

Downstream:
- bybit_decision_packet_to_postgres.py
- bybit_build_observer_verdict.py
- bybit_readonly_final_summary.py
- bybit_readonly_audit.py

Maintenance notes:
- 当前 should_query_ai=false 是设计要求，不是故障
- 改 source_refs / freshness / risk_flags 后要同步 audit
'''

"""

import json
import sys
import time
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_misc_tools_dir = _script_dir.parent / "misc_tools"
if str(_misc_tools_dir) not in sys.path:
    sys.path.insert(0, str(_misc_tools_dir))
import bybit_path_policy as bpp

SNAPSHOT_PATH = bpp.CONNECTOR_LOGS_ROOT / "bybit_system_snapshot_latest.json"
WS_SUMMARY_PATH = bpp.WS_LOGS_DIR / "bybit_private_ws_smoke_latest.json"
WS_RUNTIME_FACTS_PATH = bpp.BYBIT_RUNTIME_ROOT / "bybit_ws_runtime_facts_latest.json"
PREFLIGHT_GUARD_PATH = bpp.BYBIT_RUNTIME_ROOT / "bybit_private_rest_preflight_latest.json"

OUT_DIR = bpp.DECISION_PACKETS_ROOT
OUT_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

def now_ms():  # TODO: consolidate with app.utils.time_utils.now_ms
    return int(time.time() * 1000)

def main():
    snapshot = load_json(SNAPSHOT_PATH)
    ws_summary = load_json(WS_SUMMARY_PATH)
    ws_runtime = load_json(WS_RUNTIME_FACTS_PATH)
    preflight = load_json(PREFLIGHT_GUARD_PATH)

    packet_generated_ts_ms = now_ms()
    freshness_reference_ts_ms = packet_generated_ts_ms

    payload = (snapshot or {}).get("payload") or {}

    account = payload.get("account") or {}
    positions = payload.get("positions") or {}
    order_history = payload.get("order_history") or {}
    execution_history = payload.get("execution_history") or {}

    account_resp = account.get("response") or {}
    account_result = account_resp.get("result") or {}
    account_list = account_result.get("list") or []
    account_first = account_list[0] if account_list else {}
    coins = account_first.get("coin") or []
    usdt_coin = next((c for c in coins if c.get("coin") == "USDT"), {})

    positions_resp = positions.get("response") or {}
    positions_result = positions_resp.get("result") or {}
    positions_list = positions_result.get("list") or []

    order_resp = order_history.get("response") or {}
    order_result = order_resp.get("result") or {}
    order_list = order_result.get("list") or []

    exec_spot = execution_history.get("spot") or {}
    exec_linear = execution_history.get("linear") or {}
    exec_spot_items = exec_spot.get("items") or []
    exec_linear_items = exec_linear.get("items") or []

    snapshot_ts_ms = snapshot.get("ts_ms") if snapshot else None
    ws_ts_ms = ws_summary.get("ts_ms") if ws_summary else None
    ws_runtime_ts_ms = ws_runtime.get("ts_ms") if ws_runtime else None
    preflight_ts_ms = preflight.get("ts_ms") if preflight else None

    freshness = {
        "packet_generated_ts_ms": packet_generated_ts_ms,
        "freshness_reference_ts_ms": freshness_reference_ts_ms,
        "snapshot_ts_ms": snapshot_ts_ms,
        "snapshot_age_ms": (freshness_reference_ts_ms - snapshot_ts_ms) if isinstance(snapshot_ts_ms, int) else None,
        "ws_ts_ms": ws_ts_ms,
        "ws_age_ms": (freshness_reference_ts_ms - ws_ts_ms) if isinstance(ws_ts_ms, int) else None,
        "ws_runtime_facts_ts_ms": ws_runtime_ts_ms,
        "ws_runtime_facts_age_ms": (freshness_reference_ts_ms - ws_runtime_ts_ms) if isinstance(ws_runtime_ts_ms, int) else None,
        "preflight_ts_ms": preflight_ts_ms,
        "preflight_age_ms": (freshness_reference_ts_ms - preflight_ts_ms) if isinstance(preflight_ts_ms, int) else None,
    }

    risk_flags = []
    if len(positions_list) == 0:
        risk_flags.append("no_open_positions")
    if ws_runtime and ws_runtime.get("signal_strength") == "control_only":
        risk_flags.append("ws_control_only_no_business_events")
    if preflight and not preflight.get("allowed_to_continue", False):
        risk_flags.append("preflight_guard_blocking")

    candidate_questions_for_ai = []
    if len(exec_spot_items) + len(exec_linear_items) == 0:
        candidate_questions_for_ai.append("No recent execution history detected. Is there enough signal context to justify AI reasoning?")
    if len(order_list) == 0:
        candidate_questions_for_ai.append("No recent order history detected. Should the system lower decision urgency?")
    if ws_runtime and ws_runtime.get("signal_strength") == "control_only":
        candidate_questions_for_ai.append("Persistent WS is connected but only control messages are present. Should the system keep observer urgency low?")

    packet = {
        "packet_type": "bybit_decision_packet",
        "packet_version": "v4",
        "ts_ms": packet_generated_ts_ms,
        "packet_generated_ts_ms": packet_generated_ts_ms,
        "freshness_reference_ts_ms": freshness_reference_ts_ms,
        "exchange": "bybit",
        "mode": "read_only",
        "autonomous_execution": False,
        "source_refs": {
            "source_snapshot_path": str(SNAPSHOT_PATH),
            "source_snapshot_ts_ms": snapshot_ts_ms,
            "source_ws_smoke_path": str(WS_SUMMARY_PATH),
            "source_ws_smoke_ts_ms": ws_ts_ms,
            "source_ws_runtime_facts_path": str(WS_RUNTIME_FACTS_PATH),
            "source_ws_runtime_facts_ts_ms": ws_runtime_ts_ms,
            "source_preflight_guard_path": str(PREFLIGHT_GUARD_PATH),
            "source_preflight_guard_ts_ms": preflight_ts_ms,
        },
        "input_integrity": {
            "snapshot_present": bool(snapshot),
            "ws_smoke_present": bool(ws_summary),
            "ws_runtime_facts_present": bool(ws_runtime),
            "preflight_present": bool(preflight),
            "preflight_allowed_to_continue": bool((preflight or {}).get("allowed_to_continue", False)),
        },
        "account_summary": {
            "account_type": account_first.get("accountType"),
            "total_equity": account_first.get("totalEquity"),
            "total_wallet_balance": account_first.get("totalWalletBalance"),
            "total_available_balance": account_first.get("totalAvailableBalance"),
            "coin_count": len(coins),
            "usdt_equity": usdt_coin.get("equity"),
            "usdt_wallet_balance": usdt_coin.get("walletBalance"),
            "usdt_usd_value": usdt_coin.get("usdValue"),
        },
        "position_summary": {
            "category": positions_result.get("category"),
            "position_count": len(positions_list),
            "nonzero_position_count": len([p for p in positions_list if str(p.get("size", "0")) not in ("0", "0.0", "")]),
            "symbols": sorted(list({p.get("symbol") for p in positions_list if p.get("symbol")})),
        },
        "order_summary": {
            "category": order_result.get("category"),
            "order_count": len(order_list),
            "symbols": sorted(list({o.get("symbol") for o in order_list if o.get("symbol")})),
        },
        "execution_summary": {
            "spot_execution_count": len(exec_spot_items),
            "linear_execution_count": len(exec_linear_items),
            "total_execution_count": len(exec_spot_items) + len(exec_linear_items),
            "symbols": sorted(list({
                x.get("symbol")
                for x in (exec_spot_items + exec_linear_items)
                if x.get("symbol")
            })),
        },
        "ws_session_summary": {
            "present": bool(ws_summary),
            "ts_ms": ws_ts_ms,
            "auth_ok": ws_summary.get("auth_ok") if ws_summary else None,
            "subscribe_ok": ws_summary.get("subscribe_ok") if ws_summary else None,
            "topics_requested": ws_summary.get("topics_requested") or ws_summary.get("topics") or [],
            "subscribed_topics": ws_summary.get("subscribed_topics") or [],
            "message_count": ws_summary.get("message_count") if ws_summary else None,
            "topic_message_count": ws_summary.get("topic_message_count") or {},
            "errors": ws_summary.get("errors") or [],
        },
        "ws_runtime_summary": {
            "present": bool(ws_runtime),
            "ts_ms": ws_runtime_ts_ms,
            "listener_health": ws_runtime.get("listener_health") if ws_runtime else None,
            "connection_state": ws_runtime.get("connection_state") if ws_runtime else None,
            "signal_strength": ws_runtime.get("signal_strength") if ws_runtime else None,
            "business_signal_state": ws_runtime.get("business_signal_state") if ws_runtime else None,
            "connection_activity_state": ws_runtime.get("connection_activity_state") if ws_runtime else None,
            "running": ws_runtime.get("running") if ws_runtime else None,
            "auth_ok_count": ws_runtime.get("auth_ok_count") if ws_runtime else None,
            "subscribe_ok_count": ws_runtime.get("subscribe_ok_count") if ws_runtime else None,
            "message_count": ws_runtime.get("message_count") if ws_runtime else None,
            "control_message_count_estimate": ws_runtime.get("control_message_count_estimate") if ws_runtime else None,
            "business_message_count_estimate": ws_runtime.get("business_message_count_estimate") if ws_runtime else None,
            "business_topic_event_count": ws_runtime.get("business_topic_event_count") if ws_runtime else None,
            "last_event_age_ms": ws_runtime.get("last_event_age_ms") if ws_runtime else None,
            "notes": ws_runtime.get("notes") or [],
        },
        "freshness": freshness,
        "risk_flags": risk_flags,
        "candidate_questions_for_ai": candidate_questions_for_ai,
        "local_decision_hints": {
            "should_query_ai": False,
            "reason": "v4 packet still observer-first; AI gating not yet enabled",
            "observer_mode_preferred": True,
        }
    }

    latest_path = OUT_DIR / "bybit_decision_packet_latest.json"
    dated_path = OUT_DIR / f"bybit_decision_packet_{packet_generated_ts_ms}.json"

    latest_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(packet, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")

if __name__ == "__main__":
    main()
