"""REF-20 Sprint D R8 maintenance healthcheck sentinels — `[46]`-`[50]`.
REF-20 Sprint D R8 維護面 healthcheck 哨兵 — `[46]`-`[50]`。

MODULE_NOTE (中):
    REF-20 Sprint D R8（2026-05-05）maintenance / observation pass。Sprint A-C
    把 Paper Replay Lab E2E 真實接通；R8 的目標是讓 maintenance 自動化（cron
    驅動）+ silent-dead 偵測（healthcheck 守門），確保 R6/R7 上線後不退化。

    本檔含 5 個 healthcheck sentinel 對應五個 maintenance 面：

      `[46]` mlde_shadow_retention_status
              — V056 retention cron 活性 + 候選 row 不爆量。
              — V056 retention cron freshness + candidate row growth not unbounded.
              — Sibling cron: helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh

      `[47]` replay_runner_binary
              — Linux replay_runner binary 在預期 path 存在 + 可執行。
              — Linux replay_runner binary present at expected path + executable.
              — Sibling: rust/target/release/replay_runner (post --rebuild deploy).

      `[48]` replay_manifest_registry_growth
              — replay.experiments row 增長率（過去 7d / 24h），停滯偵測 Sprint A-C 後 runner 是否仍跑。
              — replay.experiments row growth rate (7d / 24h); detect post-Sprint-A-C runner stall.

      `[49]` replay_artifact_retention
              — V046 replay.report_artifacts oldest row age + total bytes
                vs OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB；既有 cron
                replay_artifact_prune.py 守 storage cap，本哨兵雙重驗證。
              — V046 oldest row age + total bytes; double-checks
                replay_artifact_prune.py cron is keeping cap.

      `[50]` replay_run_state_health
              — replay.run_state status='failed' rate（過去 7d）+ status='running'
                age >1h（zombie subprocess 偵測）。
              — replay.run_state failed rate (7d) + 'running' rows aged >1h
                (zombie subprocess detection).

    所有 sentinel 走 graceful absent fallback（V056/V046/V049 任一缺即
    PASS-skip），確保 pre-deploy 不 false-FAIL；deploy 後自動轉真檢查。

MODULE_NOTE (EN):
    REF-20 Sprint D R8 (2026-05-05) maintenance / observation pass.
    Sprint A-C delivered E2E Paper Replay Lab; R8 goal = maintenance
    automation (cron-driven) + silent-dead detection (healthcheck gates) so
    R6/R7 don't regress post-deploy.

    Five sentinels covering five maintenance surfaces:
      [46] mlde_shadow_retention_status — V056 retention cron freshness +
           candidate row growth bounded.
      [47] replay_runner_binary — Linux replay_runner binary presence +
           executable bit.
      [48] replay_manifest_registry_growth — replay.experiments row growth
           rate to detect post-Sprint-A-C runner stall.
      [49] replay_artifact_retention — V046 oldest row age + total bytes
           cap dual-check vs replay_artifact_prune.py cron.
      [50] replay_run_state_health — failed rate + zombie 'running' rows.

    All sentinels graceful-absent fallback (V056/V046/V049 missing →
    PASS-skip) so pre-deploy never false-FAILs; auto-promotes to real
    check post-deploy.

Spec source / 規格來源:
    - docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md
      Sprint D R8 §6.R8 task 2 (5 healthcheck probes)
    - sql/migrations/V056__mlde_shadow_recommendations_retention_policy.sql
      (sibling retention function)
    - helper_scripts/cron/replay_artifact_prune.py
      (sibling artifact prune cron)
    - helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh
      (sibling retention cron landed Sprint D R8)
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Constants — calibrated per Sprint D R8 spec.
# 常量 — 對齊 Sprint D R8 spec 校準。
# ---------------------------------------------------------------------------

# `[46]` mlde_shadow_retention thresholds.
# `[46]` retention cron 預期每日跑（cron `0 4 * * *`）；連 2 日無觸碰即異常。
RETENTION_LAST_RUN_PASS_MAX_HOURS: float = 26.0
RETENTION_LAST_RUN_WARN_MAX_HOURS: float = 50.0
# 候選 row 上限：candidates_count 超此 = retention 沒有有效跑（assume 30d
# replay + 90d real_outcome retention，正常情況下 candidates 應接近 0 in
# steady state）。
RETENTION_CANDIDATES_FAIL_THRESHOLD: int = 50000

# `[47]` replay_runner_binary expected path on Linux trade-core.
# `[47]` Linux trade-core 上 replay_runner binary 預期路徑。
# 順序對齊 route_helpers.resolve_replay_runner_bin() priority chain。
RUNNER_BINARY_CANDIDATE_PATHS: tuple[str, ...] = (
    "rust/target/release/replay_runner",
    "rust/target/debug/replay_runner",
    "rust/openclaw_engine/target/release/replay_runner",
    "rust/openclaw_engine/target/debug/replay_runner",
)

# `[48]` replay_manifest_registry growth thresholds.
# Sprint A-C 後 runner 應持續增長 row（每次 `/run` 必寫 1 row to
# replay.experiments）；7d 0 增長 = runner 死 / Wave 9 mutation watch fired
# / E2E pipeline broken。
REGISTRY_7D_PASS_MIN_ROWS: int = 1
REGISTRY_24H_WARN_MIN_ROWS: int = 0  # 0 row in 24h = WARN（quiet day），1+ = PASS。

# `[49]` replay_artifact_retention thresholds.
# V046 byte_size 30d retention：oldest row > 30d = retention cron 死 / 沒
# 觸發 storage cap path。Storage cap 默認 1024 MB；超 cap = WARN/FAIL。
ARTIFACT_OLDEST_PASS_MAX_DAYS: int = 30
ARTIFACT_OLDEST_WARN_MAX_DAYS: int = 60
ARTIFACT_STORAGE_CAP_MB_DEFAULT: int = 1024  # match replay_artifact_prune.py default

# `[50]` replay_run_state_health thresholds.
# 7d 失敗率上限：>20% = 系統性問題（fixture broken / Rust binary regression /
# DB schema drift）。
RUN_STATE_FAILED_RATE_PASS_MAX: float = 0.10  # 10%
RUN_STATE_FAILED_RATE_WARN_MAX: float = 0.20  # 20%
RUN_STATE_SUPERSEDING_COMPLETED_MIN: int = 3
# Zombie 'running' rows: >1h still in 'running' status = subprocess 死亡未
# 收回；>4h = 嚴重，可能需 operator 手動 cleanup。
RUN_STATE_ZOMBIE_PASS_MAX_HOURS: float = 1.0
RUN_STATE_ZOMBIE_WARN_MAX_HOURS: float = 4.0

# `[53]` REF-21 V058 symbol universe recorder thresholds.
V058_RECORDER_PASS_MAX_HOURS: float = 2.0
V058_RECORDER_WARN_MAX_HOURS: float = 26.0
V058_RECORDER_MIN_ROWS_24H: int = 1


# ---------------------------------------------------------------------------
# `[46]` mlde_shadow_retention_status — V056 cron freshness + candidate cap.
# `[46]` mlde_shadow retention cron 活性 + 候選 row 上限驗證。
# ---------------------------------------------------------------------------

def check_46_mlde_shadow_retention_status(cur) -> tuple[str, str]:
    """[46] V056 retention cron 活性 + replay-derived 候選 row 上限驗證。

    [46] V056 retention cron freshness + replay-derived candidate cap check.

    Two-axis health probe：
    1. **Cron freshness**: `$OPENCLAW_DATA_DIR/mlde_shadow_recommendations_retention_last_run`
       file mtime；retention cron 跑完即 touch。預期每日跑（cron `0 4 * * *`）；
       連續 26h 沒 touch 即 WARN，>50h FAIL（兩日 cron miss）。
    2. **Candidate count**: replay-derived row 候選計數（V056 dry-run 等價
       SELECT）。穩態應接近 0；若超 50k 表示 retention 沒在 apply 模式跑或
       cron 一直 dry-run（operator 漏 flip flag）。

    Args:
        cur: psycopg2 cursor.

    Returns:
        (status, msg) tuple.
    """
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    # Step 1: Cron freshness via sentinel file mtime.
    # 步驟 1：透過 sentinel 檔 mtime 判斷 cron 活性。
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    sentinel_path = Path(data_dir) / "mlde_shadow_recommendations_retention_last_run"

    cron_age_hours: float | None = None
    cron_status_msg = ""
    if sentinel_path.exists():
        try:
            cron_age_hours = (time.time() - sentinel_path.stat().st_mtime) / 3600.0
            cron_status_msg = f"cron_age={cron_age_hours:.1f}h"
        except OSError as exc:
            cron_status_msg = f"sentinel_stat_failed:{type(exc).__name__}"
    else:
        cron_status_msg = "cron_sentinel_absent (cron not yet installed or never ran)"

    # Step 2: Verify V056 function present (graceful absent fallback).
    # 步驟 2：驗 V056 function 存在（缺即 PASS-skip）。
    try:
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname='learning' AND p.proname='prune_mlde_shadow_recommendations')"
        )
        v056_present = bool(cur.fetchone()[0])
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[46] V056 presence query failed: {exc}")

    if not v056_present:
        return (
            "PASS",
            f"[46] V056 prune_mlde_shadow_recommendations absent (pre-deploy graceful skip); {cron_status_msg}",
        )

    # Step 3: Compute candidate count (mirror V056 dry-run logic).
    # 步驟 3：計算候選 row 計數（鏡像 V056 dry-run 邏輯）。
    replay_retention_days = int(os.environ.get("OPENCLAW_MLDE_REPLAY_RETENTION_DAYS", "30"))
    real_retention_days = int(os.environ.get("OPENCLAW_MLDE_REAL_RETENTION_DAYS", "90"))
    try:
        cur.execute(
            """
            SELECT
              count(*) FILTER (
                WHERE evidence_source_tier IN ('calibrated_replay','synthetic_replay','counterfactual_replay')
                  AND ts < now() - make_interval(days => %s)
              )::bigint AS replay_candidates,
              count(*) FILTER (
                WHERE evidence_source_tier = 'real_outcome'
                  AND ts < now() - make_interval(days => %s)
              )::bigint AS real_candidates
              FROM learning.mlde_shadow_recommendations
            """,
            (replay_retention_days, real_retention_days),
        )
        row = cur.fetchone()
        replay_candidates = int(row[0] or 0)
        real_candidates = int(row[1] or 0)
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[46] candidate query failed: {exc}")

    candidates_total = replay_candidates + real_candidates

    # Verdict: cron freshness OR candidate cap can each independently FAIL.
    # 判定：cron freshness 與 candidate cap 任一失格皆獨立 FAIL/WARN。
    fail_reasons: list[str] = []
    warn_reasons: list[str] = []

    if cron_age_hours is not None:
        if cron_age_hours > RETENTION_LAST_RUN_WARN_MAX_HOURS:
            fail_reasons.append(
                f"cron_age={cron_age_hours:.1f}h > {RETENTION_LAST_RUN_WARN_MAX_HOURS}h FAIL threshold "
                "(2-day cron miss)"
            )
        elif cron_age_hours > RETENTION_LAST_RUN_PASS_MAX_HOURS:
            warn_reasons.append(
                f"cron_age={cron_age_hours:.1f}h > {RETENTION_LAST_RUN_PASS_MAX_HOURS}h PASS threshold "
                "(daily cadence missed)"
            )

    if candidates_total > RETENTION_CANDIDATES_FAIL_THRESHOLD:
        fail_reasons.append(
            f"candidates_total={candidates_total} > {RETENTION_CANDIDATES_FAIL_THRESHOLD} "
            "(retention not in apply mode or cron stuck dry-run)"
        )

    base = (
        f"replay_candidates={replay_candidates} real_candidates={real_candidates} "
        f"({cron_status_msg})"
    )

    if fail_reasons:
        return ("FAIL", f"[46] {base} — " + "; ".join(fail_reasons))
    if warn_reasons:
        return ("WARN", f"[46] {base} — " + "; ".join(warn_reasons))
    return ("PASS", f"[46] {base} — retention healthy")


# ---------------------------------------------------------------------------
# `[47]` replay_runner_binary — Linux binary presence + executable bit.
# `[47]` Linux replay_runner binary 存在性 + 執行 bit 驗證。
# ---------------------------------------------------------------------------

def check_47_replay_runner_binary() -> tuple[str, str]:
    """[47] Linux replay_runner binary 在預期 path 存在 + 可執行。

    [47] Replay runner binary present at expected Linux path + executable.

    Pure filesystem check — runs after `conn.close()`. Mirrors
    `route_helpers.resolve_replay_runner_bin()` priority chain：
      1. `OPENCLAW_REPLAY_RUNNER_BIN` env override
      2-5. fallback list per RUNNER_BINARY_CANDIDATE_PATHS

    若 env override 設定了不存在的 path → FAIL（operator 配置錯）；
    若 4 個 fallback path 全缺 → FAIL（cargo --release 未跑）；
    若 release path 缺但 debug path 在 → WARN（未 --rebuild）；
    若 release path 在 → PASS。

    Returns:
        (status, msg) tuple.
    """
    base_dir_str = os.environ.get("OPENCLAW_BASE_DIR", "").strip()
    if not base_dir_str:
        # Default per CLAUDE.md §六: Linux $HOME/BybitOpenClaw/srv.
        base_dir_str = str(Path.home() / "BybitOpenClaw" / "srv")
    base_dir = Path(base_dir_str)

    # Step 1: Env override (highest priority).
    # 步驟 1：env override（最高優先）。
    override = os.environ.get("OPENCLAW_REPLAY_RUNNER_BIN", "").strip()
    if override:
        override_path = Path(override)
        if override_path.is_file() and os.access(override_path, os.X_OK):
            return (
                "PASS",
                f"[47] runner binary at env override: {override_path} (executable)",
            )
        return (
            "FAIL",
            f"[47] OPENCLAW_REPLAY_RUNNER_BIN={override} but not executable file",
        )

    # Step 2: Probe fallback chain (RUNNER_BINARY_CANDIDATE_PATHS order).
    # 步驟 2：fallback chain 探測。
    found_paths: list[tuple[str, bool]] = []  # (rel_path, is_executable)
    for rel_path in RUNNER_BINARY_CANDIDATE_PATHS:
        candidate = base_dir / rel_path
        if candidate.is_file():
            is_exec = bool(os.access(candidate, os.X_OK))
            found_paths.append((rel_path, is_exec))

    if not found_paths:
        return (
            "FAIL",
            f"[47] replay_runner binary not found at any of {len(RUNNER_BINARY_CANDIDATE_PATHS)} candidate paths "
            f"under base_dir={base_dir} (run cargo build --release -p openclaw_engine --bin replay_runner)",
        )

    # Verdict: prefer first found in priority order.
    # 判定：依優先序取首個 found path。
    primary_path, primary_exec = found_paths[0]
    if not primary_exec:
        return (
            "FAIL",
            f"[47] runner binary at {primary_path} but executable bit missing (chmod +x needed)",
        )

    # Check: workspace release path (priority 1) is preferred over debug.
    # 檢查：workspace release path（priority 1）優於 debug。
    if primary_path.endswith("/debug/replay_runner"):
        return (
            "WARN",
            f"[47] runner binary at {primary_path} (debug build); production should use release "
            "(run cargo build --release -p openclaw_engine --bin replay_runner)",
        )

    return ("PASS", f"[47] runner binary at {primary_path} (release, executable)")


# ---------------------------------------------------------------------------
# `[48]` replay_manifest_registry_growth — row growth rate stalls detection.
# `[48]` replay.experiments row 增長率 stall 偵測。
# ---------------------------------------------------------------------------

def check_48_replay_manifest_registry_growth(cur) -> tuple[str, str]:
    """[48] replay.experiments row growth rate (7d / 24h)；停滯偵測。

    [48] replay.experiments row growth rate (7d / 24h); stall detection.

    Sprint A-C 後每次 `/run` 必寫 1 row to replay.experiments。7d 0 row 增長
    = runner 死 / E2E pipeline broken / register endpoint 拒絕 manifest。
    24h 0 row 是可接受的（quiet day）但 7d 完全 0 增長 → FAIL。

    Args:
        cur: psycopg2 cursor.

    Returns:
        (status, msg) tuple.
    """
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    # Step 1: Verify replay.experiments table presence (graceful absent fallback).
    # 步驟 1：驗 replay.experiments 表存在（缺即 PASS-skip）。
    try:
        cur.execute("SELECT to_regclass('replay.experiments') IS NOT NULL")
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[48] replay.experiments existence query failed: {exc}")

    if not exists_row or not exists_row[0]:
        return (
            "PASS",
            "[48] replay.experiments missing (V049 not applied; pre-deploy graceful skip)",
        )

    # Step 2: Compute total + 7d + 24h growth.
    # 步驟 2：計算 total + 7d + 24h 增長。
    try:
        cur.execute(
            """
            SELECT
              count(*)::bigint AS total_rows,
              count(*) FILTER (WHERE created_at > now() - interval '7 days')::bigint AS rows_7d,
              count(*) FILTER (WHERE created_at > now() - interval '24 hours')::bigint AS rows_24h,
              extract(epoch FROM (now() - max(created_at)))::bigint AS last_age_seconds
            FROM replay.experiments
            """
        )
        row = cur.fetchone()
        total_rows = int(row[0] or 0)
        rows_7d = int(row[1] or 0)
        rows_24h = int(row[2] or 0)
        last_age_seconds = int(row[3]) if row[3] is not None else None
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[48] manifest registry query failed: {exc}")

    # Verdict.
    # 判定。
    if total_rows == 0:
        return (
            "PASS",
            "[48] replay.experiments empty (Sprint A-C pre-smoke or freshly bootstrapped)",
        )

    age_hr_str = f"{last_age_seconds/3600.0:.1f}h" if last_age_seconds is not None else "unknown"
    base = f"total={total_rows} rows_7d={rows_7d} rows_24h={rows_24h} last_age={age_hr_str}"

    # 7d 0 row 增長且 total > 1 → FAIL（runner 真停滯非冷啟動）。
    if rows_7d < REGISTRY_7D_PASS_MIN_ROWS and total_rows >= 2:
        return (
            "FAIL",
            f"[48] {base} — 0 row in 7d but total={total_rows}: runner stalled "
            "(check replay_runner binary + register endpoint logs)",
        )

    if rows_24h <= REGISTRY_24H_WARN_MIN_ROWS:
        return (
            "WARN",
            f"[48] {base} — quiet 24h (0 row registered); confirm operator-driven runs by design",
        )

    return ("PASS", f"[48] {base} — registry growth healthy")


# ---------------------------------------------------------------------------
# `[49]` replay_artifact_retention — V046 oldest age + storage cap dual check.
# `[49]` V046 oldest row age + storage cap 雙重驗證。
# ---------------------------------------------------------------------------

def check_49_replay_artifact_retention(cur) -> tuple[str, str]:
    """[49] V046 replay.report_artifacts oldest age + total bytes 雙重驗證。

    [49] V046 replay.report_artifacts oldest age + total bytes dual-check.

    既有 cron `replay_artifact_prune.py` 守 storage cap（默認 1024 MB）+
    30d TTL；本哨兵雙重驗證 cron 真有效跑：
    - oldest row age >30d = TTL prune cron 死
    - total bytes > storage cap = storage cap prune cron 死

    Cron 驗證 vs 真實 cron 跑：sentinel 從 DB 讀真實狀態而非 cron log（log
    丟失 ≠ silent failure，DB row 是真實 source-of-truth）。

    Args:
        cur: psycopg2 cursor.

    Returns:
        (status, msg) tuple.
    """
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    # Step 1: Verify replay.report_artifacts presence.
    # 步驟 1：驗 V046 replay.report_artifacts 存在性。
    try:
        cur.execute("SELECT to_regclass('replay.report_artifacts') IS NOT NULL")
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[49] replay.report_artifacts existence query failed: {exc}")

    if not exists_row or not exists_row[0]:
        return (
            "PASS",
            "[49] replay.report_artifacts missing (V046 not applied; pre-deploy graceful skip)",
        )

    # Step 2: Compute oldest age + total bytes + row count.
    # 步驟 2：計算最舊 row 年齡 + 總 byte + row 計數。
    try:
        cur.execute(
            """
            SELECT
              count(*)::bigint AS total_rows,
              extract(epoch FROM (now() - min(created_at)))::bigint AS oldest_age_seconds,
              coalesce(sum(byte_size), 0)::bigint AS total_bytes
            FROM replay.report_artifacts
            """
        )
        row = cur.fetchone()
        total_rows = int(row[0] or 0)
        oldest_age_seconds = int(row[1]) if row[1] is not None else None
        total_bytes = int(row[2] or 0)
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[49] artifact retention query failed: {exc}")

    if total_rows == 0:
        return (
            "PASS",
            "[49] replay.report_artifacts empty (no artifacts yet; pre-Sprint-A R3 or freshly pruned)",
        )

    storage_cap_mb = int(os.environ.get("OPENCLAW_REPLAY_ARTIFACT_STORAGE_CAP_MB", str(ARTIFACT_STORAGE_CAP_MB_DEFAULT)))
    storage_cap_bytes = storage_cap_mb * 1024 * 1024
    total_mb = total_bytes / 1024 / 1024
    oldest_age_days: float | None = None
    if oldest_age_seconds is not None:
        oldest_age_days = oldest_age_seconds / 86400.0

    fail_reasons: list[str] = []
    warn_reasons: list[str] = []

    # Oldest age verdict (TTL prune cron health).
    # 最舊年齡判定（TTL prune cron 健康）。
    if oldest_age_days is not None:
        if oldest_age_days > ARTIFACT_OLDEST_WARN_MAX_DAYS:
            fail_reasons.append(
                f"oldest_age={oldest_age_days:.1f}d > {ARTIFACT_OLDEST_WARN_MAX_DAYS}d FAIL threshold "
                "(TTL prune cron silent dead)"
            )
        elif oldest_age_days > ARTIFACT_OLDEST_PASS_MAX_DAYS:
            warn_reasons.append(
                f"oldest_age={oldest_age_days:.1f}d > {ARTIFACT_OLDEST_PASS_MAX_DAYS}d PASS threshold "
                "(TTL prune cron sluggish)"
            )

    # Storage cap verdict (cap prune cron health).
    # Storage cap 判定（cap prune cron 健康）。
    if total_bytes > storage_cap_bytes:
        fail_reasons.append(
            f"total={total_mb:.1f}MB > {storage_cap_mb}MB storage cap "
            "(cap prune cron silent dead)"
        )
    elif total_bytes > storage_cap_bytes * 0.8:
        warn_reasons.append(
            f"total={total_mb:.1f}MB > 80% of {storage_cap_mb}MB cap "
            "(approaching storage cap; cap prune may need to fire)"
        )

    age_str = f"{oldest_age_days:.1f}d" if oldest_age_days is not None else "unknown"
    base = f"total_rows={total_rows} oldest_age={age_str} total_mb={total_mb:.1f} cap_mb={storage_cap_mb}"

    if fail_reasons:
        return ("FAIL", f"[49] {base} — " + "; ".join(fail_reasons))
    if warn_reasons:
        return ("WARN", f"[49] {base} — " + "; ".join(warn_reasons))
    return ("PASS", f"[49] {base} — retention healthy")


# ---------------------------------------------------------------------------
# `[50]` replay_run_state_health — failed rate + zombie 'running' detection.
# `[50]` V045 run_state failed rate + zombie 'running' 偵測。
# ---------------------------------------------------------------------------

def check_50_replay_run_state_health(cur) -> tuple[str, str]:
    """[50] V045 replay.run_state status='failed' rate + zombie 'running' age。

    [50] V045 replay.run_state failed rate + zombie 'running' detection.

    Two-axis health probe：
    1. **Failed rate (7d)**: failed / (completed + failed + cancelled)；
       >10% PASS-WARN，>20% FAIL（系統性問題）。
    2. **Zombie 'running' rows**: status='running' 且 started_at >1h 前 →
       subprocess 死亡未收回；oldest 'running' age >4h = FAIL。

    Pre-Sprint-A R3 bootstrap：表空 = PASS-skip。

    Args:
        cur: psycopg2 cursor.

    Returns:
        (status, msg) tuple.
    """
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    # Step 1: Verify replay.run_state presence (graceful absent fallback).
    # 步驟 1：驗 V045 replay.run_state 存在性（缺即 PASS-skip）。
    try:
        cur.execute("SELECT to_regclass('replay.run_state') IS NOT NULL")
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[50] replay.run_state existence query failed: {exc}")

    if not exists_row or not exists_row[0]:
        return (
            "PASS",
            "[50] replay.run_state missing (V045 not applied; pre-deploy graceful skip)",
        )

    # Step 2: Compute 7d failed rate + zombie 'running' age.
    # 步驟 2：計算 7d 失敗率 + zombie 'running' 年齡。
    try:
        cur.execute(
            """
            SELECT
              count(*) FILTER (WHERE status = 'completed' AND started_at > now() - interval '7 days')::bigint AS completed_7d,
              count(*) FILTER (WHERE status = 'failed' AND started_at > now() - interval '7 days')::bigint AS failed_7d,
              count(*) FILTER (WHERE status = 'cancelled' AND started_at > now() - interval '7 days')::bigint AS cancelled_7d,
              count(*) FILTER (WHERE status = 'running')::bigint AS running_count,
              extract(epoch FROM (now() - min(started_at) FILTER (WHERE status = 'running')))::bigint AS oldest_running_seconds,
              max(started_at) FILTER (WHERE status = 'failed' AND started_at > now() - interval '7 days') AS newest_failed_at,
              max(started_at) FILTER (WHERE status = 'completed' AND started_at > now() - interval '7 days') AS newest_completed_at,
              count(*) FILTER (
                WHERE status = 'completed'
                  AND started_at > (
                    SELECT max(started_at)
                    FROM replay.run_state
                    WHERE status = 'failed'
                      AND started_at > now() - interval '7 days'
                  )
              )::bigint AS completed_after_newest_failed
            FROM replay.run_state
            """
        )
        row = cur.fetchone()
        completed_7d = int(row[0] or 0)
        failed_7d = int(row[1] or 0)
        cancelled_7d = int(row[2] or 0)
        running_count = int(row[3] or 0)
        oldest_running_seconds = int(row[4]) if row[4] is not None else None
        newest_failed_at = row[5]
        newest_completed_at = row[6]
        completed_after_newest_failed = int(row[7] or 0)
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[50] run_state query failed: {exc}")

    total_settled_7d = completed_7d + failed_7d + cancelled_7d
    if total_settled_7d == 0 and running_count == 0:
        return (
            "PASS",
            "[50] replay.run_state empty in 7d (Sprint A-C pre-smoke or quiet week)",
        )

    fail_reasons: list[str] = []
    warn_reasons: list[str] = []

    # Failed rate verdict.
    # 失敗率判定。
    if total_settled_7d > 0:
        failed_rate = failed_7d / total_settled_7d
        if failed_rate > RUN_STATE_FAILED_RATE_WARN_MAX:
            if (
                newest_failed_at is not None
                and newest_completed_at is not None
                and newest_completed_at > newest_failed_at
                and completed_after_newest_failed >= RUN_STATE_SUPERSEDING_COMPLETED_MIN
            ):
                warn_reasons.append(
                    f"historical failed_rate_7d={failed_rate:.1%} > "
                    f"{RUN_STATE_FAILED_RATE_WARN_MAX:.0%} FAIL threshold, but "
                    f"{completed_after_newest_failed} completed runs supersede newest failure"
                )
            else:
                fail_reasons.append(
                    f"failed_rate_7d={failed_rate:.1%} > {RUN_STATE_FAILED_RATE_WARN_MAX:.0%} FAIL threshold"
                )
        elif failed_rate > RUN_STATE_FAILED_RATE_PASS_MAX:
            warn_reasons.append(
                f"failed_rate_7d={failed_rate:.1%} > {RUN_STATE_FAILED_RATE_PASS_MAX:.0%} PASS threshold"
            )
    else:
        failed_rate = 0.0

    # Zombie running verdict.
    # Zombie 'running' 判定。
    if running_count > 0 and oldest_running_seconds is not None:
        oldest_running_hours = oldest_running_seconds / 3600.0
        if oldest_running_hours > RUN_STATE_ZOMBIE_WARN_MAX_HOURS:
            fail_reasons.append(
                f"zombie_running_age={oldest_running_hours:.1f}h > {RUN_STATE_ZOMBIE_WARN_MAX_HOURS}h "
                "FAIL threshold (subprocess died without status update; operator manual cleanup needed)"
            )
        elif oldest_running_hours > RUN_STATE_ZOMBIE_PASS_MAX_HOURS:
            warn_reasons.append(
                f"zombie_running_age={oldest_running_hours:.1f}h > {RUN_STATE_ZOMBIE_PASS_MAX_HOURS}h "
                "PASS threshold (running >1h, may be normal long-form run)"
            )

    base = (
        f"completed_7d={completed_7d} failed_7d={failed_7d} cancelled_7d={cancelled_7d} "
        f"running={running_count} failed_rate={failed_rate:.1%}"
    )

    if fail_reasons:
        return ("FAIL", f"[50] {base} — " + "; ".join(fail_reasons))
    if warn_reasons:
        return ("WARN", f"[50] {base} — " + "; ".join(warn_reasons))
    return ("PASS", f"[50] {base} — run_state health PASS")


# ---------------------------------------------------------------------------
# `[53]` ref21_v058_symbol_universe_recorder — recurring universe snapshots.
# `[53]` REF-21 V058 symbol universe recorder 活性。
# ---------------------------------------------------------------------------

def check_53_ref21_v058_symbol_universe_recorder(cur) -> tuple[str, str]:
    """[53] REF-21 V058 recurring symbol-universe snapshot liveness."""
    try:
        cur.connection.rollback()
    except Exception:  # noqa: BLE001
        pass

    try:
        cur.execute("SELECT to_regclass('market.symbol_universe_snapshots') IS NOT NULL")
        exists_row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[53] V058 existence query failed: {exc}")

    if not exists_row or not exists_row[0]:
        return (
            "PASS",
            "[53] market.symbol_universe_snapshots missing (V058 not applied; pre-deploy graceful skip)",
        )

    try:
        cur.execute(
            """
            SELECT
              count(*)::bigint AS total_rows,
              count(*) FILTER (WHERE ts > now() - interval '24 hours')::bigint AS rows_24h,
              extract(epoch FROM (now() - max(ts)))::bigint AS last_age_seconds
            FROM market.symbol_universe_snapshots
            WHERE exchange = 'bybit'
            """
        )
        row = cur.fetchone()
        total_rows = int(row[0] or 0)
        rows_24h = int(row[1] or 0)
        last_age_seconds = int(row[2]) if row[2] is not None else None
    except Exception as exc:  # noqa: BLE001
        return ("WARN", f"[53] V058 recorder query failed: {exc}")

    if total_rows == 0 or last_age_seconds is None:
        return (
            "FAIL",
            "[53] market.symbol_universe_snapshots exists but has no Bybit rows; recurring recorder/backfill not active",
        )

    age_hours = last_age_seconds / 3600.0
    base = f"total={total_rows} rows_24h={rows_24h} last_age={age_hours:.1f}h"
    if age_hours > V058_RECORDER_WARN_MAX_HOURS:
        return (
            "FAIL",
            f"[53] {base} — V058 recorder stale > {V058_RECORDER_WARN_MAX_HOURS}h",
        )
    if age_hours > V058_RECORDER_PASS_MAX_HOURS or rows_24h < V058_RECORDER_MIN_ROWS_24H:
        return (
            "WARN",
            f"[53] {base} — V058 recorder missed hourly cadence",
        )
    return ("PASS", f"[53] {base} — V058 recorder healthy")
