#!/usr/bin/env python3
"""Shared helper for the 4 ``bybit_private_*_check.py`` stub wrappers.

MODULE_NOTE (EN): OBSERVER-RESTORE-1 (2026-04-27) — when commit ``f42face``
(2026-04-23) deleted the legacy ``helper_scripts/maintenance_scripts/
bybit_connector/`` directory containing the ``.py.orig`` stubs that the
4 thin wrappers ``execv``'d into, the readonly observer cycle started
returning ``returncode=2`` for 8 days straight (silent-fail caught by
healthcheck [19] added 2026-04-26). This helper inlines the canned-stub
emission so the 4 wrappers no longer depend on the deleted
``_bybit_latest_wrapper.py`` + ``.orig``.

Output contract (preserved byte-for-byte vs pre-f42face stub):
  1. Canned JSON to stdout (cycle ``run_cmd`` captures into
     ``steps[].stdout`` for operator triage)
  2. LATEST file at ``<srv>/log_files/connector_logs/<prefix>_latest.json``
     (or ``<srv>/docker_projects/.../<prefix>_latest.json`` for
     execution_history per its legacy path)
  3. Dated copy ``<latest_dir>/<prefix>_<ts_ms>.json`` mirroring the old
     ``_bybit_latest_wrapper.py`` dual-write behaviour
  4. Exit 0

Schema:
  * ``api_key_not_configured`` branch when no api_key file is present in
    either OPENCLAW_SECRETS_DIR/demo/api_key or .../prod/api_key
  * ``not_implemented`` branch when a key is configured (real REST call
    will be wired in a follow-up WS-RETIRE-1 ticket)

Cross-platform per CLAUDE.md §七.1: no hardcoded user-home paths;
SRV root resolution via ``OPENCLAW_SRV_ROOT`` → ``OPENCLAW_BASE_DIR`` →
``"."`` fallback. Secrets resolution via ``OPENCLAW_SECRETS_DIR`` (slot
base) → ``OPENCLAW_SECRETS_ROOT/secret_files/bybit`` → repo-relative
``../secrets/secret_files/bybit``.

MODULE_NOTE (中): OBSERVER-RESTORE-1（2026-04-27）— commit ``f42face``
（2026-04-23）刪除 ``helper_scripts/maintenance_scripts/bybit_connector/``
目錄含 ``.py.orig`` stub 後，4 個 thin wrapper ``execv`` 撞 file-not-found
連續 8 天 silent-fail（2026-04-26 補 healthcheck [19] 揭發）。本 helper
內聯 canned stub 邏輯，移除對已刪 ``_bybit_latest_wrapper.py`` + ``.orig``
的依賴。

輸出契約（與 ``f42face`` 前 stub byte-identical）：
  1. Canned JSON 寫 stdout（cycle ``run_cmd`` 捕獲入 ``steps[].stdout``）
  2. LATEST 檔於 ``<srv>/log_files/connector_logs/<prefix>_latest.json``
     （execution_history 走 ``<srv>/docker_projects/.../<prefix>_latest.json``
     legacy 路徑）
  3. Dated 副本 ``<latest_dir>/<prefix>_<ts_ms>.json`` 對齊原
     ``_bybit_latest_wrapper.py`` 雙寫行為
  4. Exit 0

Schema：``api_key_not_configured`` 分支（兩個 slot 皆無 api_key）/
``not_implemented`` 分支（key 存在但真 REST 未接線，留待 WS-RETIRE-1
follow-up ticket 完成）。

跨平台（CLAUDE.md §七.1）：無 user-home 寫死路徑；SRV root
``OPENCLAW_SRV_ROOT`` → ``OPENCLAW_BASE_DIR`` → ``"."`` fallback；
secrets ``OPENCLAW_SECRETS_DIR`` → ``OPENCLAW_SECRETS_ROOT/secret_files/bybit``
→ repo-relative fallback。
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def srv_root() -> Path:
    """Resolve repo root from env vars with documented fallback chain.
    從 env var 解析 repo root，有 documented fallback 鏈。"""
    return Path(
        os.environ.get("OPENCLAW_SRV_ROOT")
        or os.environ.get("OPENCLAW_BASE_DIR")
        or "."
    )


def _key_configured() -> bool:
    """Return True iff a non-empty api_key file exists in demo or prod slot.
    當 demo 或 prod slot 任一非空 api_key 檔存在時回 True。"""
    secrets_dir_env = os.environ.get("OPENCLAW_SECRETS_DIR")
    secrets_root_env = os.environ.get("OPENCLAW_SECRETS_ROOT")
    if secrets_dir_env:
        slot_base = Path(secrets_dir_env)
    elif secrets_root_env:
        slot_base = Path(secrets_root_env) / "secret_files" / "bybit"
    else:
        # Last-resort default: production Linux layout (one level above srv/).
        # 最終 fallback：生產 Linux 預設路徑（srv/ 上一級）。
        slot_base = srv_root().resolve().parent / "secrets" / "secret_files" / "bybit"
    for slot in ("demo", "prod"):
        key_path = slot_base / slot / "api_key"
        try:
            if key_path.exists() and key_path.stat().st_size > 0:
                return True
        except OSError:
            # Permission / FS error — treat as not configured (fail-closed).
            # 權限 / FS 錯 — 視為未配置（fail-closed）。
            continue
    return False


def emit_stub(prefix: str, latest_path: Path, payload_extra: dict) -> int:
    """Emit canned stub JSON + write LATEST + dated. Returns exit code.

    Args:
        prefix: dated filename stem, e.g. ``bybit_private_account_check``.
        latest_path: full path of the ``<prefix>_latest.json`` file.
        payload_extra: schema-specific fields merged into the canned JSON
            payload (e.g. ``{"position_count": 0, "positions": []}`` for the
            positions stub). Empty dict ``{}`` for stubs with no extra fields.

    Behaviour:
        * If no api_key configured (demo or prod slot): emit
          ``api_key_not_configured`` payload.
        * If api_key configured: emit ``not_implemented`` payload (caller
          schemas reuse the same ``payload_extra`` shape so downstream
          consumers don't see schema drift between branches).

    將 canned stub JSON 輸出 + 寫 LATEST + dated；回傳 exit code。
    無 api_key 配置時 → ``api_key_not_configured``；有 key 時 →
    ``not_implemented``（兩分支共用 ``payload_extra`` shape，下游無 schema 漂移）。
    """
    if _key_configured():
        base = {
            "ok": False,
            "retCode": -1,
            "retMsg": "not_implemented",
            "health_state": "not_implemented",
            "issues": ["real API call not implemented"],
        }
    else:
        base = {
            "ok": False,
            "retCode": -1,
            "retMsg": "api_key_not_configured",
            "health_state": "credential_misconfigured",
            "issues": ["credential files missing"],
        }
    payload = {**base, **payload_extra}
    body = json.dumps(payload, ensure_ascii=False)
    # stdout: cycle's run_cmd captures this into steps[].stdout for
    # operator triage visibility.
    # stdout：cycle ``run_cmd`` 捕獲入 ``steps[].stdout`` 利 operator triage。
    sys.stdout.write(body + "\n")
    # LATEST + dated dual-write per the pre-f42face wrapper contract.
    # LATEST + dated 雙寫，對齊 ``f42face`` 前 wrapper 既有契約。
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    ts_ms = int(time.time() * 1000)
    dated = latest_path.parent / f"{prefix}_{ts_ms}.json"
    latest_path.write_text(body, encoding="utf-8")
    dated.write_text(body, encoding="utf-8")
    return 0
