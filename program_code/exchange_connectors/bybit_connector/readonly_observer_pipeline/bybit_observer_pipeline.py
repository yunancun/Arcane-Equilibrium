#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_misc_tools_dir = _script_dir.parent / "misc_tools"
if str(_misc_tools_dir) not in sys.path:
    sys.path.insert(0, str(_misc_tools_dir))
import bybit_path_policy as bpp

_scripts_dir = bpp.PROGRAM_CODE_ROOT / "exchange_connectors" / "bybit_connector" / "scripts"
BUILD_WS_FACTS = _scripts_dir / "bybit_build_ws_runtime_facts.py"
BUILD_DECISION_PACKET = _scripts_dir / "bybit_build_decision_packet.py"
LOAD_DECISION_PACKET = _scripts_dir / "bybit_decision_packet_to_postgres.py"
BUILD_VERDICT = _scripts_dir / "bybit_build_observer_verdict.py"
LOAD_VERDICT = _scripts_dir / "bybit_observer_verdict_to_postgres.py"

def run_cmd(cmd):
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

def main():
    steps = []

    ordered = [
        ("build_ws_runtime_facts", BUILD_WS_FACTS),
        ("build_decision_packet", BUILD_DECISION_PACKET),
        ("load_decision_packet_to_postgres", LOAD_DECISION_PACKET),
        ("build_observer_verdict", BUILD_VERDICT),
        ("load_observer_verdict_to_postgres", LOAD_VERDICT),
    ]

    for stage_name, script_path in ordered:
        result = run_cmd([sys.executable, str(script_path)])
        steps.append({
            "stage": stage_name,
            "script": str(script_path),
            **result,
        })
        if not result["ok"]:
            print(json.dumps({
                "overall_ok": False,
                "failed_stage": stage_name,
                "steps": steps,
            }, ensure_ascii=False, indent=2))
            return

    print(json.dumps({
        "overall_ok": True,
        "steps": steps,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
