#!/usr/bin/env python3
import json
import subprocess
import sys
import time
from pathlib import Path

OBSERVER_CYCLE_SCRIPT = Path("/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_full_readonly_observer_cycle.py")
DECISION_PACKET_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def run_cmd(cmd):
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

def load_json_if_exists(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

def main():
    started_ts_ms = int(time.time() * 1000)

    cycle = run_cmd([sys.executable, str(OBSERVER_CYCLE_SCRIPT)])

    packet = load_json_if_exists(DECISION_PACKET_PATH)
    verdict = load_json_if_exists(VERDICT_PATH)

    finished_ts_ms = int(time.time() * 1000)

    summary = {
        "run_type": "bybit_observer_cycle_entrypoint",
        "run_version": "v1",
        "started_ts_ms": started_ts_ms,
        "finished_ts_ms": finished_ts_ms,
        "duration_ms": finished_ts_ms - started_ts_ms,
        "overall_ok": cycle["ok"],
        "cycle_returncode": cycle["returncode"],
        "latest_decision_packet": None,
        "latest_observer_verdict": None,
        "status_summary": {
            "mode": None,
            "observer_mode": True,
            "execution_allowed": None,
            "should_refresh_rest": None,
            "should_query_ai": None,
            "verdict_code": None,
            "packet_snapshot_age_ms": None,
        },
        "stdout_path_hint": str(OUT_DIR / "bybit_observer_cycle_latest.json"),
        "raw_cycle_stdout": cycle["stdout"],
        "raw_cycle_stderr": cycle["stderr"],
    }

    if packet:
        summary["latest_decision_packet"] = {
            "ts_ms": packet.get("ts_ms"),
            "packet_type": packet.get("packet_type"),
            "packet_version": packet.get("packet_version"),
            "exchange": packet.get("exchange"),
            "risk_flags": packet.get("risk_flags") or [],
            "freshness": packet.get("freshness") or {},
            "local_decision_hints": packet.get("local_decision_hints") or {},
        }
        summary["status_summary"]["mode"] = packet.get("mode")
        summary["status_summary"]["should_query_ai"] = (packet.get("local_decision_hints") or {}).get("should_query_ai")
        summary["status_summary"]["packet_snapshot_age_ms"] = ((packet.get("freshness") or {}).get("snapshot_age_ms"))

    if verdict:
        summary["latest_observer_verdict"] = {
            "ts_ms": verdict.get("ts_ms"),
            "verdict_type": verdict.get("verdict_type"),
            "verdict_version": verdict.get("verdict_version"),
            "verdict_code": verdict.get("verdict_code"),
            "urgency": verdict.get("urgency"),
            "risk_flags": verdict.get("risk_flags") or [],
            "reasons": verdict.get("reasons") or [],
            "next_steps": verdict.get("next_steps") or [],
        }
        summary["status_summary"]["execution_allowed"] = verdict.get("execution_allowed")
        summary["status_summary"]["should_refresh_rest"] = verdict.get("should_refresh_rest")
        summary["status_summary"]["verdict_code"] = verdict.get("verdict_code")

    latest_path = OUT_DIR / "bybit_observer_cycle_latest.json"
    dated_path = OUT_DIR / f"bybit_observer_cycle_{finished_ts_ms}.json"

    latest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")

if __name__ == "__main__":
    main()
