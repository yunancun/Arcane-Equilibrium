"""Cron heartbeat sentinel healthchecks [75]-[80].

MODULE_NOTE:
  P1-CRON-INSTALL-WAVE-1（2026-05-18）— 5 個 cron wrapper 已 source/test
  closed 但 crontab 尚未 install。每個 wrapper 在啟動時 touch
  ``${OPENCLAW_DATA_DIR:-/tmp/openclaw}/cron_heartbeat/<name>.last_fire``
  sentinel；本套哨兵以 sentinel mtime 推斷 cron 是否「按時 fire」。

  為什麼 touch-at-start 而非 touch-at-end：``wave9_replay_no_live_mutation_watch.sh``
  以 ``exec python3 - <<PYEOF`` 結尾把 shell 替換成 Python，後面再 append
  ``touch`` 不會執行。改為 start-time touch 即「cron 被排程觸發」的證據，與
  operator 提出的 "verifies cron fires every Nmin" 語意一致；whether the
  workload 自己 succeeded 是各 cron 自己的 exit code + log，不在本哨兵範圍。

  本套哨兵預設 WARN（缺失 / 過時）而非 FAIL：cron infra 不是 promotion-blocking
  surface（operator 明示 2026-05-18 dispatch）。OPENCLAW_CRON_HEARTBEAT_REQUIRED=1
  可升 WARN → FAIL 進入 fail-closed 模式。

  Threshold 設計（heartbeat staleness）：
    [75] panel_aggregator_health        每 5min  → stale > 7min  → WARN
    [76] wave9_replay_no_live_mutation  每 60min → stale > 75min → WARN
    [77] replay_key_rotation_check      每日     → stale > 25h   → WARN
    [78] feature_baseline_writer        每日     → stale > 25h   → WARN
    [79] blocked_symbols_30d_unblock    每週     → stale > 8d    → WARN
    [80] trading_ai_pg_dump_freshness   每日     → stale > 26h   → WARN/FAIL
    [91] kline_calibration              每日     → stale > 25h   → WARN

  Sentinel 缺失 → WARN「heartbeat file missing — cron not installed or
  has never fired」；過時 → WARN「heartbeat stale (age=<s>s, threshold=<s>s)
  — cron likely stopped firing」；新鮮 → PASS。

  [80] 不同於 [75]-[79]：它是 P0-OPS-4 GAP-D PG dump cron 的 wrapper，
  delegate 給 standalone ``helper_scripts/canary/healthchecks/check_pg_dump_freshness.py``
  跑完整 7 check（5 verify_pg_dump.sh + L0 schema coverage + governance audit
  trail）；本檔僅作 runner.py 註冊點 + verdict 提取，不重複實作以保單一 SSOT。
"""

from __future__ import annotations

import os
import time
from pathlib import Path


# 預設 sentinel 根目錄；可由 OPENCLAW_CRON_HEARTBEAT_DIR 覆蓋（方便測試）
_DEFAULT_HEARTBEAT_SUBDIR = "cron_heartbeat"
_REQUIRED_ENV = "OPENCLAW_CRON_HEARTBEAT_REQUIRED"
_TRUE_VALUES = {"1", "true", "yes", "on", "required"}


def _resolve_heartbeat_dir() -> Path:
    """解析 sentinel 目錄。優先讀 OPENCLAW_CRON_HEARTBEAT_DIR；否則
    OPENCLAW_DATA_DIR/cron_heartbeat；最後 fallback /tmp/openclaw/cron_heartbeat。
    """
    explicit = os.environ.get("OPENCLAW_CRON_HEARTBEAT_DIR", "").strip()
    if explicit:
        return Path(explicit)
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip()
    return Path(data_dir) / _DEFAULT_HEARTBEAT_SUBDIR


def _required_mode() -> bool:
    return os.environ.get(_REQUIRED_ENV, "").strip().lower() in _TRUE_VALUES


def _age_seconds(sentinel: Path, now: float) -> float | None:
    """回傳 sentinel 的年齡秒數；不存在或 stat 失敗回 None。"""
    try:
        return max(0.0, now - sentinel.stat().st_mtime)
    except OSError:
        return None


def _format_age(age_s: float) -> str:
    """人類可讀的年齡格式：< 60s 用秒、< 3600 用分、其餘用小時。"""
    if age_s < 60.0:
        return f"{age_s:.0f}s"
    if age_s < 3600.0:
        return f"{age_s / 60.0:.1f}min"
    if age_s < 86400.0:
        return f"{age_s / 3600.0:.1f}h"
    return f"{age_s / 86400.0:.2f}d"


def _classify(
    check_id: str,
    sentinel_name: str,
    cadence_label: str,
    threshold_seconds: float,
    now: float | None = None,
) -> tuple[str, str]:
    """共用 PASS/WARN 判斷邏輯。WARN-by-default；required mode 升 FAIL。"""
    now_ts = time.time() if now is None else now
    sentinel = _resolve_heartbeat_dir() / sentinel_name
    warn_severity = "FAIL" if _required_mode() else "WARN"
    age = _age_seconds(sentinel, now_ts)

    base = (
        f"{check_id} {sentinel_name} cron heartbeat — "
        f"cadence={cadence_label}, threshold={_format_age(threshold_seconds)}, "
        f"sentinel={sentinel}"
    )

    if age is None:
        return (
            warn_severity,
            base
            + "; heartbeat file missing — cron not installed or has never fired",
        )
    if age > threshold_seconds:
        return (
            warn_severity,
            base
            + f"; heartbeat stale age={_format_age(age)} ({age:.0f}s) "
            "— cron likely stopped firing",
        )
    return (
        "PASS",
        base + f"; heartbeat fresh age={_format_age(age)} ({age:.0f}s)",
    )


# ---------------------------------------------------------------------------
# 5 個 healthcheck 公開函數，runner.py 直接登記。
# 為什麼公開五個小函數而非一個 loop：runner.py 既有風格是「一個 check_id 一個
# 函數」，便於 results 列表逐項追蹤；也方便 follow-up wave 改 threshold 時各
# 自獨立。
# ---------------------------------------------------------------------------


def check_75_panel_aggregator_health_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[75] panel_aggregator_health_cron 5min cadence heartbeat。

    cron 由 W1 sub-task 3（E1-γ, 2026-05-11）建立但尚未 install 到 crontab；
    threshold 7min = cadence 5min + 2min grace（與 [66] panel freshness 對齊）。
    """
    return _classify(
        check_id="[75]",
        sentinel_name="panel_aggregator_health.last_fire",
        cadence_label="*/5 * * * *",
        threshold_seconds=7 * 60,
        now=now,
    )


def check_76_wave9_replay_no_live_mutation_watch_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[76] wave9_replay_no_live_mutation_watch hourly heartbeat。

    REF-20 Wave 9 R20-W9-T1 — 14d gradient observation；hourly cron 但尚未
    install。threshold 75min = cadence 60min + 15min grace（cron 起跑延遲常見）。
    """
    return _classify(
        check_id="[76]",
        sentinel_name="wave9_replay_no_live_mutation_watch.last_fire",
        cadence_label="0 * * * *",
        threshold_seconds=75 * 60,
        now=now,
    )


def check_77_replay_key_rotation_check_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[77] replay_key_rotation_check daily heartbeat。

    REF-20 P2a-S1 — daily probe of 90d HMAC key rotation；尚未 install。
    threshold 25h = cadence 24h + 1h grace（DST / drift / leap 容差）。
    """
    return _classify(
        check_id="[77]",
        sentinel_name="replay_key_rotation_check.last_fire",
        cadence_label="0 9 * * *",
        threshold_seconds=25 * 3600,
        now=now,
    )


def check_78_feature_baseline_writer_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[78] feature_baseline_writer daily heartbeat。

    W-AUDIT-4b runtime apply wrapper；daily cron 但尚未 install。
    threshold 25h = cadence 24h + 1h grace。
    """
    return _classify(
        check_id="[78]",
        sentinel_name="feature_baseline_writer.last_fire",
        cadence_label="41 4 * * *",
        threshold_seconds=25 * 3600,
        now=now,
    )


def check_79_blocked_symbols_30d_unblock_check_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[79] blocked_symbols_30d_unblock_check weekly heartbeat。

    W5-E1-C P1-DYNAMIC-UNBLOCK-CHECK-1 — 每週日 04:00 UTC 跑 30d cycle；
    尚未 install。threshold 8d = cadence 7d + 1d grace；配對 [64]
    unblock_candidates_drift（每週日 05:00 UTC，1h 後驗 cron 寫入結果）。
    """
    return _classify(
        check_id="[79]",
        sentinel_name="blocked_symbols_30d_unblock_check.last_fire",
        cadence_label="0 4 * * 0",
        threshold_seconds=8 * 86400,
        now=now,
    )


def check_91_kline_calibration_cron_fires(
    now: float | None = None,
) -> tuple[str, str]:
    """[91] kline_calibration daily heartbeat（INTRADAY-KLINES-PERMANENT-FIX R3）。

    kline_calibration_cron.sh（Rust kline_calibration_checker R3 旋轉採樣 truth-test）
    daily cron 但 crontab 尚未 install；wrapper start-time touch
    ``kline_calibration.last_fire`` sentinel，本哨兵驗 mtime < threshold。
    threshold 25h = cadence 24h + 1h grace（與 [78] feature_baseline_writer 對齊）。

    ID 註：PA spec §3.1 標 ``[81]``，但 ``[81]``/``[82]`` 已被 P5-SM
    ``check_81_lease_ipc_soak`` / ``check_82_lease_ipc_soak_window`` 占用（cursor 區塊）；
    本 cron heartbeat 取下一自由 filesystem slot ``[91]``（[90] cost_gate_double_deduct
    為當前最高），避免 ID 撞號（沿用 codebase ``[58]→[68]`` 重定址慣例）。
    WARN-by-default（cron infra 非 promotion-blocking）；
    OPENCLAW_CRON_HEARTBEAT_REQUIRED=1 升 WARN → FAIL。
    """
    return _classify(
        check_id="[91]",
        sentinel_name="kline_calibration.last_fire",
        cadence_label="17 5 * * *",
        threshold_seconds=25 * 3600,
        now=now,
    )


def check_80_pg_dump_freshness(
    now: float | None = None,
) -> tuple[str, str]:
    """[80] trading_ai_pg_dump cron + 7-check freshness wrapper（P0-OPS-4 GAP-D）。

    為什麼 wrapper 而非自己實作：standalone
    ``helper_scripts/canary/healthchecks/check_pg_dump_freshness.py`` 是 SSOT
    （operator ad-hoc + dashboard 共用），本檔僅 delegate 取 verdict + 7 check
    結果 collapse 成 runner.py 期待的 ``(verdict, msg)`` tuple。任何 5 + L0 +
    audit-log 邏輯改動只動 standalone module 一處。

    特殊處理：
      - import 失敗（standalone module 缺）→ FAIL（infra 缺檔，不可繼續）
      - standalone ``run()`` 拋例外 → WARN（runner 不該 crash；其他 check
        仍要跑完）
      - sub-check INSUFFICIENT_SAMPLE（V113 未 apply / dump 未 fire）→ PASS-skip
        透傳，避免 first-day deploy 阻擋
      - 整體 verdict FAIL → ``OPENCLAW_CRON_HEARTBEAT_REQUIRED=1`` 升 FAIL
        （與 [75]-[79] 對齊）；否則 WARN

    ``now`` 參數保留是為與 [75]-[79] _classify signature 對齊測試介面；本 check
    不用（standalone 自己取 ``time.time()``）。
    """
    del now  # 為 signature 對齊保留，不使用

    try:
        # 為什麼用 importlib：standalone module 路徑在 ``srv/helper_scripts/canary/
        # healthchecks/`` 不在本 package；走 sys.path 動態 import 避免硬編
        # relative import 跨 package。對齊 [20] check_h_state_gateway_freshness
        # 同模式。
        import importlib
        import sys
        from pathlib import Path

        srv_root = (
            os.environ.get("OPENCLAW_BASE_DIR")
            or str(Path.home() / "BybitOpenClaw" / "srv")
        )
        healthchecks_dir = Path(srv_root) / "helper_scripts" / "canary" / "healthchecks"
        if str(healthchecks_dir) not in sys.path:
            sys.path.insert(0, str(healthchecks_dir))

        mod = importlib.import_module("check_pg_dump_freshness")
    except ImportError as e:
        warn_severity = "FAIL" if _required_mode() else "WARN"
        return (
            warn_severity,
            f"[80] standalone check_pg_dump_freshness import failed: {e} "
            "— P0-OPS-4 GAP-D infra missing",
        )

    try:
        result = mod.run()
    except SystemExit:
        # standalone connect_pg() 在 missing creds 用 sys.exit(2)；不能讓它打掛 runner。
        warn_severity = "FAIL" if _required_mode() else "WARN"
        return (
            warn_severity,
            "[80] standalone run() exited (PG creds / connect failure) — "
            "check_pg_dump_freshness.py --status 看細節",
        )
    except Exception as e:  # noqa: BLE001 — runner 不可 crash 必須包裝
        warn_severity = "FAIL" if _required_mode() else "WARN"
        return (
            warn_severity,
            f"[80] standalone run() raised {type(e).__name__}: {e}",
        )

    overall = result.get("verdict", "WARN")
    sub_checks = result.get("checks", [])
    # Collapse 成單行 summary：``[80] verdict=PASS (7 check: ...)``
    # 取 non-PASS 的 sub-check id + verdict 摘要；全 PASS 則只報 count。
    non_pass = [
        f"{c['id']}:{c['verdict']}"
        for c in sub_checks
        if c.get("verdict") != "PASS"
    ]
    if non_pass:
        summary = (
            f"[80] pg_dump_freshness verdict={overall} "
            f"(7 sub-check; non-PASS: {', '.join(non_pass)})"
        )
    else:
        summary = (
            f"[80] pg_dump_freshness verdict={overall} "
            f"(7 sub-check all PASS)"
        )

    # FAIL 升級：standalone 已決定整體 verdict；本 wrapper 對 FAIL 看 REQUIRED env
    # 升級語意僅供 cron_heartbeat 一致性；standalone FAIL 本身就會被 runner
    # ``aggregate severity`` 認知為 FAIL。
    if overall == "FAIL":
        return ("FAIL", summary)
    if overall == "WARN":
        return ("WARN", summary)
    if overall == "INSUFFICIENT_SAMPLE":
        # 與 _common.severity_max 一致：INSUFFICIENT_SAMPLE 比 WARN 輕；
        # runner 顯示為 INSUFFICIENT_SAMPLE 即可，operator 知道 cron 未 fire。
        return ("INSUFFICIENT_SAMPLE", summary)
    return ("PASS", summary)


__all__ = [
    "check_75_panel_aggregator_health_cron_fires",
    "check_76_wave9_replay_no_live_mutation_watch_cron_fires",
    "check_77_replay_key_rotation_check_cron_fires",
    "check_78_feature_baseline_writer_cron_fires",
    "check_79_blocked_symbols_30d_unblock_check_cron_fires",
    "check_80_pg_dump_freshness",
    "check_91_kline_calibration_cron_fires",
]
