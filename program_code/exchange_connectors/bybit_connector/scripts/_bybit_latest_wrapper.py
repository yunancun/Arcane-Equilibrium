#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: _bybit_latest_wrapper.py
Role:
- 提供 latest / dated 文件写入相关的通用包装能力
- 主要用于让其他脚本稳定输出 latest.json + dated.json

Purpose in system:
- 降低重复写文件逻辑
- 让各阶段输出格式更统一

Typical related scripts:
- bybit_private_*_check.py
- bybit_snapshot_to_postgres.py
- bybit_build_ws_runtime_facts.py
- bybit_build_decision_packet.py
- bybit_build_observer_verdict.py

Maintenance notes:
- 修改这里前，先确认不会影响现有 latest / dated 文件契约
- 如果改输出路径或命名规则，需要同步检查下游读取脚本
'''

"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

def main():
    if len(sys.argv) != 4:
        print("usage: _bybit_latest_wrapper.py <orig_script> <latest_path> <dated_prefix>", file=sys.stderr)
        sys.exit(2)

    orig_script = Path(sys.argv[1])
    latest_path = Path(sys.argv[2])
    dated_prefix = sys.argv[3]

    quiet = os.environ.get("BYBIT_WRAPPER_QUIET", "").strip() in {"1", "true", "TRUE", "yes", "YES"}

    latest_path.parent.mkdir(parents=True, exist_ok=True)
    ts_ms = int(time.time() * 1000)
    dated_path = latest_path.parent / f"{dated_prefix}_{ts_ms}.json"

    proc = subprocess.run(
        [sys.executable, str(orig_script)],
        text=True,
        capture_output=True,
    )

    if proc.stdout:
        sys.stdout.write(proc.stdout)
    if proc.stderr:
        sys.stderr.write(proc.stderr)

    if proc.returncode != 0:
        sys.exit(proc.returncode)

    raw = proc.stdout.strip()
    if not raw:
        print(f"[wrapper] empty stdout from {orig_script}", file=sys.stderr)
        sys.exit(1)

    obj = None
    try:
        obj = json.loads(raw)
    except Exception:
        lines = [x for x in proc.stdout.splitlines() if x.strip()]
        for i in range(len(lines)):
            candidate = "\n".join(lines[i:])
            try:
                obj = json.loads(candidate)
                raw = candidate
                break
            except Exception:
                pass

    if obj is None:
        print(f"[wrapper] failed to parse JSON stdout from {orig_script}", file=sys.stderr)
        sys.exit(1)

    normalized = json.dumps(obj, ensure_ascii=False, indent=2)
    latest_path.write_text(normalized + "\n", encoding="utf-8")
    dated_path.write_text(normalized + "\n", encoding="utf-8")

    if not quiet:
        print(f"[wrapper] saved_latest={latest_path}", file=sys.stderr)
        print(f"[wrapper] saved_dated={dated_path}", file=sys.stderr)

if __name__ == "__main__":
    main()
