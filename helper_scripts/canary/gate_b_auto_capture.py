#!/usr/bin/env python3
"""
MODULE_NOTE
模塊用途：Gate-B capture 自動觸發器（AMD-2026-07-10-01）。gate_b_watch 每輪掃描後，
  把 START_GATE_B_NOW 的新上市候選轉成 R-0 隔離 Gate-B 探針的自動啟動；
  operator 授權上限 = 5 個新上市 symbol，計數器持久化於 gate_b_watch_state.json，
  cap 滿自動停 + audit 行。
主要類/函數：maybe_auto_capture（唯一入口）、_spawn_probe、_pid_alive、_append_audit。
依賴：Python 標準庫；由 gate_b_watch sibling-import（本模塊不得反向 import gate_b_watch，
  避免循環依賴）。
硬邊界（R-0 zero-leak 原樣）：
  - 唯一 spawn 目標 = 同 repo 的隔離探針 helper_scripts/research/aeg_gate_b_probe.py
    （其自身禁 import 生產模組、零 auth / 零 order / 零 DB write）。capture 產物只落
    <data_dir>/aeg_gate_b_runs research artifact 目錄，絕不進交易路徑。
  - AUTO_CAPTURE_CAP = 5 為 operator 授權上限（AMD-2026-07-10-01），由測試釘死；
    調升或續期需新的 operator 授權（新 AMD）。cap 滿後 fail-closed 永不再自啟。
  - 預設 OFF：env OPENCLAW_GATE_B_AUTO_CAPTURE=1 才啟用；flag OFF 時本模塊零副作用
    （不動 state、不寫檔、不 spawn）。
  - spawn 失敗 fail-soft：不消耗 cap 名額、寫 probe_launch_failed audit 行，
    窗口仍 fresh 時由下輪 cron 自然重試。
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("gate_b_auto_capture")

# operator 授權正本（audit 行與 artifact summary 均引用此代號）。
AUTHORIZATION_REF = "AMD-2026-07-10-01"
ENV_FLAG = "OPENCLAW_GATE_B_AUTO_CAPTURE"
# 為什麼是常量而非 env 可調：cap=5 是 operator 授權的硬上限，可調參數會讓授權邊界
# 被 runtime env 靜默改寫；測試釘死此值，變更必紅 → 逼新 AMD。
AUTO_CAPTURE_CAP = 5
STATE_KEY = "auto_capture"
# 與 gate_b_watch.ARTIFACT_DIR 同值；字面重複是刻意的（禁止反向 import gate_b_watch）。
ARTIFACT_DIR = "gate_b_watch"
AUDIT_FILE = "gate_b_auto_capture_audit.jsonl"
PROBE_DURATION_SECONDS = 24 * 60 * 60

# 合格 trigger（防 cap 誤耗，見 AMD 觸發邊界節）：
#   prelaunch_active = instruments-info PreLaunch，交易所權威源；
#   announcement_pre_market_listing = 新上市公告（另要求 symbol 出現在標題內）。
# standard_conversion（既有 pre-market 轉標準，非新上市）與 pre-IPO review 不觸發。
TRIGGER_PRELAUNCH_ACTIVE = "prelaunch_active"
TRIGGER_PREMARKET_LISTING = "announcement_pre_market_listing"
ELIGIBLE_TRIGGERS = frozenset({TRIGGER_PRELAUNCH_ACTIVE, TRIGGER_PREMARKET_LISTING})
ACTION_START_NOW = "START_GATE_B_NOW"

STATUS_DISABLED = "DISABLED"
STATUS_IDLE = "IDLE"
STATUS_DRY_RUN = "DRY_RUN"
STATUS_STARTED = "STARTED"
STATUS_ATTRIBUTED = "ATTRIBUTED_TO_RUNNING_PROBE"
STATUS_CAP_REACHED = "CAP_REACHED"
STATUS_LAUNCH_FAILED = "LAUNCH_FAILED"

_SYMBOL_OK_RE = re.compile(r"^[A-Z0-9]{2,20}USDT$")


def probe_script_path() -> Path:
    """R-0 隔離探針的 repo 相對路徑（不硬編碼機器路徑，Mac/Linux 皆可解析）。"""
    return Path(__file__).resolve().parent.parent / "research" / "aeg_gate_b_probe.py"


def _iso_utc(seconds: float) -> str:
    return (
        dt.datetime.fromtimestamp(float(seconds), tz=dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _pid_alive(pid: Any) -> bool:
    """signal 0 探活；任何異常視為已死（保守：寧可再起一個探針也不漏窗口）。"""
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _append_audit(data_dir: str, record: dict[str, Any]) -> None:
    """audit 行 append-only 落 <data_dir>/gate_b_watch/gate_b_auto_capture_audit.jsonl。

    為什麼 fail-soft：audit 寫失敗不應阻斷 watcher 主流程（state 內仍有同等記錄），
    但要 log 讓 cron log 可見。
    """
    path = Path(data_dir) / ARTIFACT_DIR / AUDIT_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError as exc:
        logger.warning("auto-capture audit write failed: %s", exc)


def _spawn_probe(data_dir: str, run_id: str) -> tuple[int, str]:
    """detached spawn 隔離探針；回傳 (pid, log_path)。

    為什麼 start_new_session：探針要跑 24h，必須脫離 cron wrapper 的 process group，
    watcher 本輪結束後探針繼續存活。artifact-root 顯式釘在 data_dir 下，
    避免探針依 env 落到別處（RM-2：capture 產物落持久 SSOT 路徑）。
    """
    script = probe_script_path()
    if not script.is_file():
        raise FileNotFoundError(f"probe script missing: {script}")
    log_dir = Path(data_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_id}.log"
    cmd = [
        sys.executable,
        str(script),
        "--duration-seconds",
        str(PROBE_DURATION_SECONDS),
        "--run-id",
        run_id,
        "--artifact-root",
        str(Path(data_dir) / "aeg_gate_b_runs"),
    ]
    with open(log_path, "a", encoding="utf-8") as log_f:
        proc = subprocess.Popen(  # noqa: S603 - cmd 全為本 repo 常量 + 內生 run_id
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    return proc.pid, str(log_path)


def _eligible_candidates(
    candidates: list[dict[str, Any]],
    captured: dict[str, Any],
) -> list[dict[str, Any]]:
    """篩合格新上市候選：START_NOW + 合格 trigger + 合法 symbol + 未消耗過名額。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for c in candidates:
        if c.get("recommended_action") != ACTION_START_NOW:
            continue
        trigger = c.get("trigger_type")
        if trigger not in ELIGIBLE_TRIGGERS:
            continue
        symbol = str(c.get("symbol") or "")
        # 排除 UNKNOWN / 空 / 非 USDT perp 形狀（regex 誤匹配防線之一）。
        if not _SYMBOL_OK_RE.match(symbol):
            continue
        # 公告類第二道防線：symbol 必須出現在公告標題內，description 正文提及
        # 他幣種的 regex 誤匹配不得燒 cap 名額（AMD 觸發邊界節）。
        if trigger == TRIGGER_PREMARKET_LISTING:
            title = str(c.get("title") or "").upper()
            if symbol not in title:
                continue
        if symbol in captured or symbol in seen:
            continue
        seen.add(symbol)
        out.append(c)
    return out


def _resolve_alert(alert_fn, alert_resolver):
    if alert_fn is not None:
        return alert_fn
    if alert_resolver is not None:
        try:
            return alert_resolver()
        except Exception as exc:  # noqa: BLE001 - 告警面故障不阻斷主流程
            logger.warning("auto-capture alert resolver failed: %s", exc)
    return None


def _send_alert(fn, subject: str, body: str, data_dir: str) -> bool:
    if fn is None:
        return False
    try:
        fn(subject, body, "WARN", data_dir)
        return True
    except Exception as exc:  # noqa: BLE001 - audit 行才是耐久記錄，告警 best-effort
        logger.warning("auto-capture alert send failed: %s", exc)
        return False


def maybe_auto_capture(
    data_dir: str,
    state: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    now: float,
    dry_run: bool = False,
    alert_fn=None,
    alert_resolver=None,
    spawn_fn=None,
    pid_alive_fn=None,
    sleep_fn=time.sleep,
) -> dict[str, Any]:
    """唯一入口：依 AMD-2026-07-10-01 決定是否自動啟動 Gate-B capture。

    回傳 summary dict（進 gate_b_watch latest artifact 供審計 / preflight 判讀）。
    caller（gate_b_watch.run_once）負責在本函數返回後 save_state。
    """
    enabled = os.environ.get(ENV_FLAG, "").strip() == "1"
    existing = state.get(STATE_KEY) if isinstance(state.get(STATE_KEY), dict) else {}
    existing_captured = (
        existing.get("captured_symbols")
        if isinstance(existing.get("captured_symbols"), dict)
        else {}
    )
    summary: dict[str, Any] = {
        "authorization": AUTHORIZATION_REF,
        "enabled": enabled,
        "cap": AUTO_CAPTURE_CAP,
        "used": len(existing_captured),
        "remaining": max(0, AUTO_CAPTURE_CAP - len(existing_captured)),
        "attributed_symbols": [],
        "started_run_id": None,
    }
    if not enabled:
        # flag OFF = 零副作用（不動 state / 不寫檔 / 不 spawn），只回報既有用量。
        summary["status"] = STATUS_DISABLED
        return summary

    ac = state.setdefault(STATE_KEY, {})
    if not isinstance(ac, dict):
        ac = {}
        state[STATE_KEY] = ac
    captured = ac.setdefault("captured_symbols", {})
    if not isinstance(captured, dict):
        captured = {}
        ac["captured_symbols"] = captured

    def _refresh_counts() -> None:
        summary["used"] = len(captured)
        summary["remaining"] = max(0, AUTO_CAPTURE_CAP - len(captured))

    _refresh_counts()

    def _record_cap_reached() -> None:
        """cap 滿自動停：一次性 audit 行 + 告警（冪等 flag 防重複）。"""
        if ac.get("cap_reached_recorded"):
            return
        ac["cap_reached_recorded"] = True
        ac["cap_reached_at"] = now
        _append_audit(
            data_dir,
            {
                "ts_utc": _iso_utc(now),
                "event": "cap_reached",
                "authorization": AUTHORIZATION_REF,
                "cap": AUTO_CAPTURE_CAP,
                "captured_symbols": sorted(captured),
                "note": "auto-capture stopped; renewal requires a new operator AMD",
            },
        )
        fn = _resolve_alert(alert_fn, alert_resolver)
        sent = _send_alert(
            fn,
            f"[GATE-B-AUTO-CAPTURE][CAP] {AUTO_CAPTURE_CAP}/{AUTO_CAPTURE_CAP} listings used",
            (
                f"authorization: {AUTHORIZATION_REF}\n"
                f"captured_symbols: {', '.join(sorted(captured))}\n"
                "auto-capture is now stopped fail-closed; a new operator AMD is required to renew."
            ),
            data_dir,
        )
        if sent:
            sleep_fn(6.0)

    if len(captured) >= AUTO_CAPTURE_CAP:
        _record_cap_reached()
        summary["status"] = STATUS_CAP_REACHED
        return summary

    eligible = _eligible_candidates(candidates, captured)
    # cap 剩額裁剪：一輪出現多個新上市時，只消耗剩餘名額（超出部分下輪不再合格
    # 是接受的邊界——授權只有 5 個，不做隱性放寬）。
    eligible = eligible[: AUTO_CAPTURE_CAP - len(captured)]
    if not eligible:
        summary["status"] = STATUS_IDLE
        return summary

    if dry_run:
        # dry-run 比 watcher 主流程更保守：不 spawn、不消耗名額、不寫 audit。
        summary["status"] = STATUS_DRY_RUN
        summary["attributed_symbols"] = [c["symbol"] for c in eligible]
        print(
            "DRY-RUN would auto-capture: "
            + ", ".join(str(c["symbol"]) for c in eligible)
        )
        return summary

    alive_fn = pid_alive_fn or _pid_alive
    active = ac.get("active_probe") if isinstance(ac.get("active_probe"), dict) else None
    probe_alive = bool(
        active
        and alive_fn(active.get("pid"))
        and now < float(active.get("expires_at") or 0)
    )

    started_run_id: str | None = None
    if not probe_alive:
        run_id = "gate_b_auto_" + dt.datetime.fromtimestamp(
            now, tz=dt.timezone.utc
        ).strftime("%Y%m%dT%H%M%SZ")
        spawn = spawn_fn or _spawn_probe
        try:
            pid, log_path = spawn(data_dir, run_id)
        except Exception as exc:  # noqa: BLE001 - spawn 失敗 fail-soft，不消耗名額
            logger.warning("auto-capture probe launch failed: %s", exc)
            _append_audit(
                data_dir,
                {
                    "ts_utc": _iso_utc(now),
                    "event": "probe_launch_failed",
                    "authorization": AUTHORIZATION_REF,
                    "error": str(exc)[:300],
                    "symbols": [c["symbol"] for c in eligible],
                },
            )
            summary["status"] = STATUS_LAUNCH_FAILED
            return summary
        active = {
            "pid": pid,
            "run_id": run_id,
            "started_at": now,
            "expires_at": now + PROBE_DURATION_SECONDS,
            "log": log_path,
        }
        ac["active_probe"] = active
        started_run_id = run_id
        _append_audit(
            data_dir,
            {
                "ts_utc": _iso_utc(now),
                "event": "probe_started",
                "authorization": AUTHORIZATION_REF,
                "run_id": run_id,
                "pid": pid,
                "duration_seconds": PROBE_DURATION_SECONDS,
                "log": log_path,
            },
        )

    run_id = str(active["run_id"])
    attributed: list[str] = []
    for c in eligible:
        symbol = str(c["symbol"])
        slot = len(captured) + 1
        captured[symbol] = {
            "slot": slot,
            "run_id": run_id,
            "attributed_at": _iso_utc(now),
            "trigger_type": c.get("trigger_type"),
            "candidate_key": c.get("candidate_key"),
        }
        attributed.append(symbol)
        _append_audit(
            data_dir,
            {
                "ts_utc": _iso_utc(now),
                "event": "listing_capture_attributed",
                "authorization": AUTHORIZATION_REF,
                "symbol": symbol,
                "slot": slot,
                "cap": AUTO_CAPTURE_CAP,
                "run_id": run_id,
                "trigger_type": c.get("trigger_type"),
            },
        )

    if started_run_id:
        fn = _resolve_alert(alert_fn, alert_resolver)
        sent = _send_alert(
            fn,
            f"[GATE-B-AUTO-CAPTURE][P1] probe started for {', '.join(attributed)}",
            (
                f"authorization: {AUTHORIZATION_REF}\n"
                f"run_id: {started_run_id}\n"
                f"symbols: {', '.join(attributed)}\n"
                f"cap_used: {len(captured)}/{AUTO_CAPTURE_CAP}\n"
                "boundary: isolated aeg_gate_b_probe only; artifacts stay in "
                "aeg_gate_b_runs; no trading/DB/runtime paths."
            ),
            data_dir,
        )
        if sent:
            sleep_fn(6.0)

    _refresh_counts()
    summary["attributed_symbols"] = attributed
    summary["started_run_id"] = started_run_id
    summary["status"] = STATUS_STARTED if started_run_id else STATUS_ATTRIBUTED
    if len(captured) >= AUTO_CAPTURE_CAP:
        _record_cap_reached()
    return summary
