"""Observer-pipeline healthcheck [19].
Observer pipeline 健康檢查 [19]。

Extracted from ``checks_derived.py`` by T6-FUP-WARN-ZONE-FILES-SPLIT.
由 T6-FUP-WARN-ZONE-FILES-SPLIT 自 ``checks_derived.py`` 抽出。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

def check_observer_pipeline_alive() -> tuple[str, str]:
    """[19] OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26): observer cron freshness + ok ratio.

    The G9-04 (commit ``c7d7179``) follow-up audit uncovered that
    ``bybit_full_readonly_observer_cycle.py`` had 9 hard-coded ``scripts/``
    paths surviving the ``f42face`` 98-shim wipe (2026-04-23). Cron ran
    ``cron_observer_cycle.sh`` every 5 minutes and 100% of stages fail-loop
    with ``[Errno 2] No such file or directory`` for **3 full days** — yet
    the cron wrapper's ``if ... ; then ... else echo "non-fatal" ; fi``
    pattern translated every failure into an info log line and exit 0.
    Cron daemon never noticed; healthcheck never noticed; no other guard
    was watching this pipeline. That is the textbook silent-fail mode
    CLAUDE.md §七 "被動等待 TODO 必附 healthcheck" was written to prevent.

    Two-axis verdict using purely filesystem state:
      1. **Freshness** — ``runtime/bybit/bybit_observer_cycle_latest.json``
         must have been written within the last 24h. Cron runs every 5min
         under nominal load; missing the 24h window = pipeline definitely
         dead even if cron is dispatching (locked file? venv missing?
         systemd cron disabled?).
      2. **ok ratio** — read the JSON, sum ``steps[].ok`` over the most
         recent cycle. ≥75% PASS is healthy; 50-75% WARN (degraded but
         partial); <50% FAIL (silent-fail mode). 0% with mtime fresh =
         the post-f42face fingerprint we saw — that's why <50% must FAIL.

    Three-state output:
      - **FAIL**: latest JSON missing OR mtime > 24h OR ok ratio < 50%
        OR JSON parse error (corruption is itself a silent-fail signal).
      - **WARN**: ok ratio in [50%, 75%) OR mtime in (1h, 24h] (cron may
        have skipped a beat — drift indicator).
      - **PASS**: mtime ≤ 1h AND ok ratio ≥ 75%.

    Phase 1a / first-run note: when the pipeline has never run, the JSON
    does not exist — that registers as FAIL because ``cron_observer_cycle``
    is wired up by default in production crontabs and "never ran" is a
    real silent-fail (operator forgot to enable cron / VENV moved /
    OPENCLAW_SRV_ROOT unset). Operators bringing up a fresh node that
    does not yet have observer cron should comment out [19] in runner
    or set ``OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1`` (latter PASS-skip).

    Cross-platform: pure ``Path.stat()`` + ``json.loads()`` — no
    Linux-only API. Mac dev-only environments without observer cron
    can set ``OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1``.

    [19] OBSERVER-PIPELINE-POST-F42FACE-CLEANUP（2026-04-26）：observer
    cron 新鮮度 + ok 比率守衛。G9-04 follow-up audit 揭發
    ``bybit_full_readonly_observer_cycle.py`` 有 9 條 hard-coded
    ``scripts/`` 路徑（2026-04-23 commit ``f42face`` 清 98 個 shim 後失效），
    cron 每 5 分鐘觸發、100% 階段 ``[Errno 2] No such file`` 連續 3 天，
    但 cron wrapper 的 ``if ... ; then ... else echo "non-fatal"`` pattern
    把所有失敗譯成 log 行 + exit 0。cron daemon、healthcheck、所有 guard
    都沒看見。這正是 CLAUDE.md §七「被動等待 TODO 必附 healthcheck」要防的
    教科書級 silent-fail 模式。

    兩軸 verdict（純檔案系統）：
      1. **新鮮度** — ``runtime/bybit/bybit_observer_cycle_latest.json``
         mtime 必須在 24h 內。標準負載下 cron 5min 一次，逾 24h = pipeline
         必死（即便 cron 還在 dispatch）。
      2. **ok 比率** — 讀 JSON 統計 ``steps[].ok``。≥75% 健康；
         50-75% WARN（部分降級）；<50% FAIL（silent-fail 模式）。
         post-f42face 連 3 天 0% + mtime 新 = 本 ticket 觸發點，因此 <50%
         必 FAIL。

    三態輸出：FAIL（檔缺 / mtime>24h / ok<50% / JSON 壞）/ WARN（ok 50-75%
    或 mtime 1-24h）/ PASS（mtime≤1h + ok≥75%）。

    跨平台：純 ``Path.stat()`` + ``json.loads()``，無 Linux-only API。
    Mac dev-only 環境若無 observer cron 可設
    ``OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1``。
    """
    # Optional opt-out for environments that legitimately don't run the
    # observer cron (Mac dev-only, fresh nodes pre-cron-bootstrap).
    # 允許環境級 opt-out（Mac dev / 尚未啟用 cron 的新節點）。
    if os.environ.get("OPENCLAW_OBSERVER_PIPELINE_OPTIONAL") == "1":
        return (
            "PASS",
            "observer pipeline optional (OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1, skip)",
        )

    # Locate the cycle JSON. OPENCLAW_SRV_ROOT is the canonical anchor;
    # fall back to OPENCLAW_BASE_DIR for forward-compat per CLAUDE.md §六.
    # 解析 cycle JSON 路徑。OPENCLAW_SRV_ROOT 為主錨，OPENCLAW_BASE_DIR
    # 為 forward-compat fallback（CLAUDE.md §六）。
    base = os.environ.get("OPENCLAW_SRV_ROOT") or os.environ.get(
        "OPENCLAW_BASE_DIR"
    )
    if not base:
        # Last-resort default: production Linux layout.
        # 最終 fallback：生產 Linux 預設路徑。
        base = str(Path.home() / "BybitOpenClaw" / "srv")
    cycle_path = (
        Path(base)
        / "docker_projects"
        / "trading_services"
        / "runtime"
        / "bybit"
        / "bybit_observer_cycle_latest.json"
    )

    if not cycle_path.exists():
        # Missing entirely — pipeline either never ran or output was wiped.
        # Either way that is a real silent-fail in production.
        # 檔完全不存在 — 從未跑或 output 被清掉，生產環境兩種都算真實 silent-fail。
        return (
            "FAIL",
            f"observer cycle JSON missing at {cycle_path} — cron not running? "
            "(set OPENCLAW_OBSERVER_PIPELINE_OPTIONAL=1 if intentional)",
        )

    # Freshness — the cron beat is 5 min, so 1h leaves > 10 missed cycles
    # before WARN; 24h leaves > 280 missed cycles before FAIL. That's the
    # ratio CLAUDE.md §七 expects for "silent-dead 自動偵測".
    # 新鮮度：cron 5min 一次，1h ≈ 12 拍 buffer → WARN 門檻；24h ≈ 288 拍
    # buffer → FAIL 門檻，符合 CLAUDE.md §七 silent-dead 自動偵測比例。
    try:
        mtime = datetime.fromtimestamp(
            cycle_path.stat().st_mtime, tz=timezone.utc
        )
        age_h = (datetime.now(tz=timezone.utc) - mtime).total_seconds() / 3600.0
    except OSError as e:
        return ("FAIL", f"observer cycle JSON stat failed: {e}")

    if age_h > 24.0:
        return (
            "FAIL",
            f"observer cycle JSON stale (age={age_h:.1f}h > 24h, "
            f"path={cycle_path}) — cron daemon / wrapper / venv likely broken",
        )

    # Parse JSON for the ok ratio. Corruption itself is a silent-fail signal
    # (wrapper aborted mid-write? disk full?). Treat as FAIL.
    # 解析 JSON 算 ok 比率。檔損壞本身就是 silent-fail（wrapper 寫一半中斷？
    # 磁碟滿？）— 直接 FAIL。
    try:
        cycle = json.loads(cycle_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return (
            "FAIL",
            f"observer cycle JSON parse error (age={age_h:.1f}h, "
            f"path={cycle_path}): {e}",
        )

    steps = cycle.get("steps")
    if not isinstance(steps, list) or not steps:
        # Schema drift — old cycle shape or partial write. Don't pretend
        # we know the ok ratio; surface the anomaly with WARN so operator
        # checks vs FAIL'ing on a healthcheck-side schema bug.
        # Schema 漂移 — 舊版 cycle 結構或部分寫入。不假設知道 ok 比率，
        # 用 WARN 提報讓 operator 確認，避免 healthcheck-side schema bug
        # 直接 FAIL。
        return (
            "WARN",
            f"observer cycle JSON has no steps array "
            f"(age={age_h:.1f}h, path={cycle_path}) — schema drift?",
        )

    total = len(steps)
    ok_count = sum(1 for s in steps if isinstance(s, dict) and s.get("ok") is True)
    ratio = ok_count / total if total else 0.0
    overall_ok = bool(cycle.get("overall_ok"))

    base_msg = (
        f"age={age_h:.1f}h, ok={ok_count}/{total} ({ratio:.0%}), "
        f"overall_ok={overall_ok}, path={cycle_path}"
    )

    # Severity ladder: <50% ok ratio FAIL (post-f42face fingerprint),
    # 50-75% WARN (degraded), ≥75% with mtime ≤ 1h PASS.
    # 嚴重度階梯：ok<50% FAIL（post-f42face 指紋）、50-75% WARN（部分降級）、
    # ≥75% 且 mtime ≤ 1h PASS。
    if ratio < 0.5:
        return (
            "FAIL",
            base_msg + " — silent-fail mode (post-f42face fingerprint? "
            "check observer_cycle path config + cron wrapper + venv)",
        )
    if ratio < 0.75:
        return ("WARN", base_msg + " — degraded; investigate failing steps")
    if age_h > 1.0:
        # ≥75% ok but mtime drift — cron may have skipped a beat or
        # cron daemon is paused. Surface as WARN for operator triage.
        # ok≥75% 但 mtime 漂移 — cron 可能漏拍或 daemon 暫停，WARN 提示
        # operator triage。
        return ("WARN", base_msg + " — mtime drift (>1h since last cycle)")
    return ("PASS", base_msg)
