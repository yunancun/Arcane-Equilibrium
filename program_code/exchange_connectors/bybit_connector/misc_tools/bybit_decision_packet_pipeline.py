#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path
import os

BUILD_SCRIPT = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/program_code/exchange_connectors/bybit_connector/scripts/bybit_build_decision_packet.py")
LOAD_SCRIPT = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/program_code/exchange_connectors/bybit_connector/scripts/bybit_decision_packet_to_postgres.py")

def run_cmd(cmd):
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

def main():
    build = run_cmd([sys.executable, str(BUILD_SCRIPT)])
    if not build["ok"]:
        print(json.dumps({
            "build_decision_packet": build,
            "overall_ok": False,
            "failed_stage": "build_decision_packet",
        }, ensure_ascii=False, indent=2))
        return

    load = run_cmd([sys.executable, str(LOAD_SCRIPT)])
    result = {
        "build_decision_packet": build,
        "load_to_postgres": load,
        "overall_ok": load["ok"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
