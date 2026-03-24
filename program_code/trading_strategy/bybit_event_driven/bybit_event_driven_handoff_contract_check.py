#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_handoff_contract_check.py

Role:
- 校验 D23.8 event-driven handoff 输出结构是否合法

Purpose in system:
- 保证 event-driven handoff 也有 contract 层保护
- 防止 handoff 文件存在但字段缺失、版本错误、结构漂移

Upstream:
- bybit_event_driven_handoff.py

Output:
- bybit_event_driven_handoff_contract_latest.json

Maintenance notes:
- 这是 contract checker，不负责业务语义深校验
- 这里只检查结构、版本、基础字段类型
'''
"""

import json
import time
from pathlib import Path

HANDOFF_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_handoff_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_handoff_contract_latest.json"
OUT_DATED_PREFIX = OUT_DIR / "bybit_event_driven_handoff_contract_"


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
    obj = load_json(HANDOFF_PATH)
    checks = []

    add_check(checks, "handoff_exists", HANDOFF_PATH.exists(), str(HANDOFF_PATH))
    add_check(checks, "handoff_type_expected", obj.get("handoff_type") == "bybit_event_driven_handoff", obj.get("handoff_type"))
    add_check(checks, "handoff_version_v1", obj.get("handoff_version") == "v1", obj.get("handoff_version"))
    add_check(checks, "stage_d23_8", obj.get("stage") == "D23.8", obj.get("stage"))
    add_check(checks, "exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))

    add_check(checks, "current_status_present", isinstance(obj.get("current_status"), dict), type(obj.get("current_status")).__name__)
    add_check(checks, "state_layer_present", isinstance(obj.get("state_layer"), dict), type(obj.get("state_layer")).__name__)
    add_check(checks, "phase_layer_present", isinstance(obj.get("phase_layer"), dict), type(obj.get("phase_layer")).__name__)
    add_check(checks, "input_layer_present", isinstance(obj.get("input_layer"), dict), type(obj.get("input_layer")).__name__)
    add_check(checks, "decision_layer_present", isinstance(obj.get("decision_layer"), dict), type(obj.get("decision_layer")).__name__)
    add_check(checks, "outcome_layer_present", isinstance(obj.get("outcome_layer"), dict), type(obj.get("outcome_layer")).__name__)

    add_check(checks, "operator_guidance_list", isinstance(obj.get("operator_guidance"), list), type(obj.get("operator_guidance")).__name__)
    add_check(checks, "next_recommended_build_order_list", isinstance(obj.get("next_recommended_build_order"), list), type(obj.get("next_recommended_build_order")).__name__)
    add_check(checks, "known_limitations_list", isinstance(obj.get("known_limitations"), list), type(obj.get("known_limitations")).__name__)

    failed = [c for c in checks if not c["ok"]]
    ts_ms = int(time.time() * 1000)

    result = {
        "report_type": "bybit_event_driven_handoff_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = Path(str(OUT_DATED_PREFIX) + f"{ts_ms}.json")
    dated_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
