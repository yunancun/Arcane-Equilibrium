#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
TARGET = BASE / "bybit_decision_lease_replay_guard_latest.json"
STEM = "bybit_decision_lease_replay_guard_contract"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: Dict[str, Any]) -> None:
    latest = BASE / f"{STEM}_latest.json"
    dated = BASE / f"{STEM}_{obj['ts_ms']}.json"
    latest.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(TARGET) if TARGET.exists() else {}

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("report_exists", TARGET.exists(), str(TARGET))
    add("gate_type_expected", obj.get("gate_type") == "bybit_decision_lease_replay_guard", obj.get("gate_type"))
    add("gate_version_v1", obj.get("gate_version") == "v1", obj.get("gate_version"))
    add("stage_i4b", obj.get("stage") == "I4-B", obj.get("stage"))
    add("gate_ok_bool", isinstance(obj.get("gate_ok"), bool), obj.get("gate_ok"))
    add("guard_decision_dict", isinstance(obj.get("guard_decision"), dict), type(obj.get("guard_decision")).__name__ if obj.get("guard_decision") is not None else None)
    add("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__ if obj.get("checks") is not None else None)
    add("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__ if obj.get("failed_checks") is not None else None)
    add("gate_state_known", obj.get("gate_state") in {
        "decision_lease_replay_guard_blocked",
        "decision_lease_replay_guard_ready_soft_warn",
        "decision_lease_replay_guard_ready",
    }, obj.get("gate_state"))
    add("allow_progress_bool", isinstance(obj.get("allow_progress_to_i4c_final_audit"), bool), obj.get("allow_progress_to_i4c_final_audit"))

    report = {
        "report_type": STEM,
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }
    save_report(report)


if __name__ == "__main__":
    main()
