#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_full_readonly_observer_cycle.py
Role:
- 串行执行 readonly observer 主链路
- 记录每一步 stage 的 stdout / stderr / ok / returncode
- 对 guard 阶段额外保留 parsed_guard

Purpose in system:
- 是 D21/D22 observer 主流程执行器
- 是 acceptance / final summary / 审计的重要上游

Stage order:
- private_rest x4
- guard x1
- post_guard x4

Maintenance notes:
- 这是主骨架脚本之一，修改要非常谨慎
- 任何 stdout 解析逻辑改动，都可能影响 parsed_guard / cycle step_count / stage_counts
'''

"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

PRIVATE_REST_STEPS = [
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_private_account_check.py",
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_private_positions_check.py",
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_private_order_history_check.py",
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_private_execution_history_check.py",
]

GUARD_SCRIPT = "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_private_rest_preflight_guard.py"

POST_GUARD_STEPS = [
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_snapshot_to_postgres.py",
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_normalize_latest_snapshot_to_postgres.py",
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_ws_smoke_to_postgres.py",
    "/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_observer_pipeline.py",
]

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH_LATEST = OUT_DIR / "bybit_observer_cycle_latest.json"

def now_ms():
    return int(time.time() * 1000)

def clean_wrapper_stderr(stderr_text: str) -> str:
    if not stderr_text:
        return ""
    kept = []
    for line in stderr_text.splitlines():
        if line.startswith("[wrapper] saved_latest="):
            continue
        if line.startswith("[wrapper] saved_dated="):
            continue
        kept.append(line)
    return "\n".join(kept).strip()

def run_cmd(cmd, stage):
    env = os.environ.copy()
    env["BYBIT_WRAPPER_QUIET"] = "1"
    proc = subprocess.run(cmd, text=True, capture_output=True, env=env)
    return {
        "stage": stage,
        "script": cmd[-1],
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": clean_wrapper_stderr(proc.stderr),
    }

def save_cycle_result(obj):
    ts = now_ms()
    dated = OUT_DIR / f"bybit_observer_cycle_{ts}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_PATH_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")

def main():
    steps = []

    for script in PRIVATE_REST_STEPS:
        step = run_cmd([sys.executable, script], "private_rest")
        steps.append(step)

    guard = run_cmd([sys.executable, GUARD_SCRIPT], "guard")
    guard_stdout = (guard.get("stdout") or "").strip()
    guard_json = {}
    if guard_stdout:
        try:
            decoder = json.JSONDecoder()
            for i, ch in enumerate(guard_stdout):
                if ch != "{":
                    continue
                try:
                    obj, end = decoder.raw_decode(guard_stdout[i:])
                    if isinstance(obj, dict):
                        guard_json = obj
                        break
                except Exception:
                    continue
        except Exception:
            guard_json = {}
    guard["parsed_guard"] = guard_json
    steps.append(guard)

    if guard_json.get("allowed_to_continue") is False:
        result = {
            "overall_ok": False,
            "stopped_at": GUARD_SCRIPT,
            "reason": "guard_blocked_pipeline",
            "steps": steps,
        }
        save_cycle_result(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    for script in POST_GUARD_STEPS:
        step = run_cmd([sys.executable, script], "post_guard")
        steps.append(step)

    result = {
        "overall_ok": True,
        "steps": steps,
    }
    save_cycle_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
