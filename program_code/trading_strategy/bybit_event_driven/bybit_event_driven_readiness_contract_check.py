#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_readiness_contract_check.py

Role:
- 校验 D23.7 readiness summary 输出结构是否合法

Purpose in system:
- 保证 event-driven summary 本身也具备 contract 校验
'''
"""

import json
import time
from pathlib import Path

SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_readiness_summary_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_readiness_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    })


def main():
    obj = load_json(SUMMARY_PATH)
    checks = []

    add_check(checks, "summary_exists", SUMMARY_PATH.exists(), str(SUMMARY_PATH))
    add_check(checks, "summary_type_expected", obj.get("summary_type") == "bybit_event_driven_readiness_summary", obj.get("summary_type"))
    add_check(checks, "summary_version_v1", obj.get("summary_version") == "v1", obj.get("summary_version"))
    add_check(checks, "stage_d23_7", obj.get("stage") == "D23.7", obj.get("stage"))
    add_check(checks, "exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
    add_check(checks, "readiness_ok_bool", isinstance(obj.get("readiness_ok"), bool), obj.get("readiness_ok"))
    add_check(checks, "current_mode_allowed", obj.get("current_mode") in ["observe_only_retained", "transition_path_open"], obj.get("current_mode"))
    add_check(checks, "state_layer_present", isinstance(obj.get("state_layer"), dict), type(obj.get("state_layer")).__name__)
    add_check(checks, "phase_layer_present", isinstance(obj.get("phase_layer"), dict), type(obj.get("phase_layer")).__name__)
    add_check(checks, "input_layer_present", isinstance(obj.get("input_layer"), dict), type(obj.get("input_layer")).__name__)
    add_check(checks, "decision_layer_present", isinstance(obj.get("decision_layer"), dict), type(obj.get("decision_layer")).__name__)
    add_check(checks, "outcome_layer_present", isinstance(obj.get("outcome_layer"), dict), type(obj.get("outcome_layer")).__name__)
    add_check(checks, "consistency_layer_present", isinstance(obj.get("consistency_layer"), dict), type(obj.get("consistency_layer")).__name__)

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_driven_readiness_contract_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")


if __name__ == "__main__":
    main()
