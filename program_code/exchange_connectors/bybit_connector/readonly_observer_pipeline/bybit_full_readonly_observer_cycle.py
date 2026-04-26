#!/usr/bin/env python3
"""
MODULE_NOTE (EN):
Script: bybit_full_readonly_observer_cycle.py
Role:
- Run the readonly observer pipeline (private REST x4 → guard → post_guard x3)
- Capture stdout / stderr / ok / returncode for each stage
- Persist parsed_guard so downstream acceptance / final summary can read it
- Exit code 1 when ``overall_ok == false`` so cron / wrapper can react

Purpose in system:
- D21 / D22 main observer flow runner
- Upstream of acceptance / final summary / audit checks

Stage order:
- private_rest x4 (account / positions / order_history / execution_history)
- guard x1 (rest_preflight_guard — may early-stop the pipeline)
- post_guard x3 (snapshot_to_postgres / normalize_latest_snapshot_to_postgres /
  observer_pipeline)

OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26):
- Hard-coded ``scripts/`` paths (deleted by commit ``f42face`` 98 shim wipe
  on 2026-04-23) repointed to the real source dirs:
    * io_and_persistence/<file> for 7 of the 8 remaining steps
    * readonly_observer_pipeline/<file> for ``bybit_observer_pipeline.py``
- ``bybit_ws_smoke_to_postgres.py`` step removed entirely — that caller
  itself referenced two more dead ``scripts/`` paths
  (``bybit_private_ws_smoke_test_v2.py`` + ``bybit_load_ws_jsonl_to_postgres.py``)
  and was replaced upstream by Rust
  ``bybit_private_ws_status_writer.rs`` (WS-RETIRE-1, see CLAUDE.md §三).
- Step count drops 9 → 8.
- ``main()`` now exits 1 on ``overall_ok == false`` so cron noise wrappers
  can no longer swallow silent FAILs (cron 5min × 3d = 864 silent fails
  was the trigger to refactor this).

MODULE_NOTE (中):
Script: bybit_full_readonly_observer_cycle.py
作用：
- 串行執行 readonly observer 主鏈路（private_rest x4 → guard → post_guard x3）
- 紀錄每一步 stage 的 stdout / stderr / ok / returncode
- 對 guard 階段保留 parsed_guard
- ``overall_ok == false`` 時 exit 1，讓 cron / wrapper 真實感知失敗

系統角色：
- D21 / D22 observer 主流程執行器
- acceptance / final summary / 審計上游

階段順序：
- private_rest x4
- guard x1 (rest_preflight_guard, 可能提前終止管線)
- post_guard x3 (snapshot_to_postgres / normalize_latest_snapshot_to_postgres /
  observer_pipeline)

OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26):
- 硬編碼的 ``scripts/`` 路徑（2026-04-23 commit ``f42face`` 刪 98 個 shim 後失效）
  改指向真實檔位置：
    * 7 / 8 個步驟在 io_and_persistence/
    * 1 個步驟在 readonly_observer_pipeline/
- ``bybit_ws_smoke_to_postgres.py`` 步驟整個移除 — 該 caller 內部又引用兩條
  dead ``scripts/`` 路徑（``bybit_private_ws_smoke_test_v2.py`` +
  ``bybit_load_ws_jsonl_to_postgres.py``），且其上游價值已被 Rust
  ``bybit_private_ws_status_writer.rs`` 取代（WS-RETIRE-1，見 CLAUDE.md §三）。
- 步驟數 9 → 8。
- ``main()`` 在 ``overall_ok == false`` 時 exit 1，避免 cron noise wrapper
  吞掉 silent FAIL（cron 5 min × 3d = 864 次靜默失敗為本次修復觸發點）。

Maintenance notes:
- 這是主骨架腳本之一，修改要非常謹慎
- 任何 stdout 解析邏輯改動都可能影響 parsed_guard / cycle step_count / stage_counts
- 新增步驟前先查 ``helper_scripts/db/passive_wait_healthcheck/checks_derived.py``
  ``check_observer_pipeline_alive`` 的契約（24h JSON freshness + ok_step ratio）
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Resolve repo root once, fall back to "." for ad-hoc shells.
# 統一解析 repo root，shell 直跑時 fallback "."。
_REPO_ROOT = os.environ.get("OPENCLAW_SRV_ROOT", ".")
_BYBIT_BASE = (
    _REPO_ROOT
    + "/program_code/exchange_connectors/bybit_connector"
)

# Real script directories after commit `f42face` (2026-04-23) wiped the
# legacy `scripts/` shim layer:
#   * io_and_persistence/  — REST + guard + persistence helpers
#   * readonly_observer_pipeline/  — high-level orchestration helpers
# 真實腳本目錄（commit `f42face` 2026-04-23 清掉 legacy `scripts/` shim 後）：
#   * io_and_persistence/  — REST + guard + 持久化 helper
#   * readonly_observer_pipeline/  — 高階編排 helper
_IO = _BYBIT_BASE + "/io_and_persistence"
_OBS = _BYBIT_BASE + "/readonly_observer_pipeline"

PRIVATE_REST_STEPS = [
    _IO + "/bybit_private_account_check.py",
    _IO + "/bybit_private_positions_check.py",
    _IO + "/bybit_private_order_history_check.py",
    _IO + "/bybit_private_execution_history_check.py",
]

GUARD_SCRIPT = _IO + "/bybit_private_rest_preflight_guard.py"

POST_GUARD_STEPS = [
    _IO + "/bybit_snapshot_to_postgres.py",
    _IO + "/bybit_normalize_latest_snapshot_to_postgres.py",
    # NOTE: bybit_ws_smoke_to_postgres.py removed by
    # OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26):
    # the caller + bybit_private_ws_smoke_test_v2.py + the venv it referenced
    # are all dead; Rust bybit_private_ws_status_writer.rs (WS-RETIRE-1)
    # already produces the bybit_private_ws_listener_status_latest.json
    # this step used to feed.
    # 註：bybit_ws_smoke_to_postgres.py 已由本 ticket 移除；其 caller +
    # v2 smoke test + 它引用的 venv 均已死，Rust ws_status_writer 已接管
    # status JSON 產生（WS-RETIRE-1）。
    _OBS + "/bybit_observer_pipeline.py",
]

OUT_DIR = Path(_REPO_ROOT + "/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_PATH_LATEST = OUT_DIR / "bybit_observer_cycle_latest.json"


def now_ms():  # TODO: consolidate with app.utils.time_utils.now_ms
    """Wall-clock millis. Kept inline for zero-dep CLI use.
    返回毫秒級牆鐘時間，保留 inline 以維持 zero-dep CLI 可用。"""
    return int(time.time() * 1000)


def clean_wrapper_stderr(stderr_text: str) -> str:
    """Strip legacy ``[wrapper]`` debug prefixes so cycle JSON stays readable.
    過濾 legacy ``[wrapper]`` debug 前綴，保持 cycle JSON 可讀性。"""
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
    """Spawn one stage script under the same Python interpreter, capture all output.
    用相同 Python interpreter 執行單一 stage 腳本並捕捉 stdout/stderr/exit code。"""
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
    """Persist latest + dated copy of the cycle JSON for downstream consumers.
    寫入 latest 與 dated 兩份 cycle JSON 供下游消費。"""
    ts = now_ms()
    dated = OUT_DIR / f"bybit_observer_cycle_{ts}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_PATH_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")


def main():
    """Run the cycle and exit 1 when overall_ok is false (no silent-fail).
    執行 cycle，``overall_ok`` 為 false 時 exit 1（避免 silent-fail）。"""
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
        # Guard explicitly blocked — emit cycle JSON and exit 1 (gate fail
        # is treated as overall pipeline fail; downstream healthcheck +
        # cron must surface this, not swallow it).
        # Guard 明確阻擋 — 寫 cycle JSON 後 exit 1（Gate 失敗 = 管線失敗，
        # 下游 healthcheck + cron 必須看見，不能吞）。
        result = {
            "overall_ok": False,
            "stopped_at": GUARD_SCRIPT,
            "reason": "guard_blocked_pipeline",
            "steps": steps,
        }
        save_cycle_result(result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    for script in POST_GUARD_STEPS:
        step = run_cmd([sys.executable, script], "post_guard")
        steps.append(step)

    all_steps_ok = guard.get("ok", False) and all(s.get("ok", False) for s in steps)
    result = {
        "overall_ok": all_steps_ok,
        "steps": steps,
    }
    save_cycle_result(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Propagate failure as exit code so cron / wrapper can react.
    # OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26) — previous
    # behaviour returned 0 unconditionally, letting noise wrappers swallow
    # 100% step failure for 3 days straight.
    # 將失敗以 exit code propagate 給 cron / wrapper 處理。
    # 本 ticket 修復前 main() 永遠回 None（exit 0），讓 noise wrapper 連續
    # 3 天吞掉 100% step failure。
    return 0 if all_steps_ok else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
