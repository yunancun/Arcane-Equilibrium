"""REF-20 P2b-T2 route_helpers — replay_routes.py support utilities.
REF-20 P2b-T2 route_helpers — replay_routes.py 支援工具。

MODULE_NOTE (EN):
    Wave 4 R20-P2b-T2 split out of replay_routes.py to keep the routes
    module under the CLAUDE.md §九 1500 LOC hard cap. This module owns:

      - replay_runner binary path resolution (env override + fallback chain)
      - per-run artifact output directory resolution (cross-platform)
      - PG advisory lock try-acquire (Wave 2 dispatch v1.1 §6 Option C)
      - V045 active-run count helpers (per-actor + global)
      - V045 / V046 schema-presence probes
      - subprocess.Popen wrapper with whitelisted env propagation
        (no live secrets per V3 §6.2 + §12 #14 red-line)

    All helpers are SYNC functions intended to be called from the
    replay_routes.py async route handlers via ``asyncio.to_thread``
    so the uvicorn event loop is never blocked while statement_timeout
    ticks (matches H-4 pattern in agents_routes).

    `route_helpers` does NOT:
      - import FastAPI / pydantic (kept pure utility);
      - couple to GovernanceHub / Decision Lease / live hot path
        (V3 §6.2 + §12 #14 red-line);
      - perform DB INSERT/UPDATE that route_helpers does not own
        (replay.run_state writes belong to replay_routes.py;
        replay.report_artifacts writes belong to canary_writer.py).

MODULE_NOTE (中):
    Wave 4 R20-P2b-T2 從 replay_routes.py 抽出，讓 routes 模組保持在
    CLAUDE.md §九 1500 LOC 硬上限以下。本 module 擁有：

      - replay_runner binary 路徑解析（env override + fallback 鏈）
      - per-run artifact 輸出目錄解析（跨平台）
      - PG advisory lock try-acquire（Wave 2 dispatch v1.1 §6 Option C）
      - V045 active-run 計數 helper（per-actor + global）
      - V045 / V046 schema-presence probe
      - subprocess.Popen 包裝（白名單 env 傳遞；無 live secrets per
        V3 §6.2 + §12 #14 紅線）

    所有 helper 為 SYNC function，由 replay_routes.py 的 async route
    handler 透過 ``asyncio.to_thread`` 呼叫（H-4 pattern），statement_timeout
    觸發時不阻塞 event loop。

    `route_helpers` 不做：
      - import FastAPI / pydantic（保持純 utility）；
      - 耦合 GovernanceHub / Decision Lease / live hot path（V3 §6.2 +
        §12 #14 紅線）；
      - 執行非屬本 module 的 DB INSERT/UPDATE（replay.run_state 寫由
        replay_routes.py 擁有；replay.report_artifacts 寫由 canary_writer.py
        擁有）。

SPEC: REF-20 V3 §3 G7 + §6 (Replay Runner Contract) + §12 #14
      (replay_no_live_mutation; whitelisted subprocess env)
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
          §4 Wave 4 R20-P2b-T2
Wave 2 dispatch v1.1: docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md
                      §6 Option C decision
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional, Tuple

# ─── Logging setup / 日誌設定 ────────────────────────────────────────
log = logging.getLogger("replay.route_helpers")


# ─── Constants / 常量 ────────────────────────────────────────────────
# Advisory lock keys (Wave 2 dispatch v1.1 §6 Option C).
# advisory lock key（Wave 2 dispatch v1.1 §6 Option C）。
ADVISORY_LOCK_GLOBAL_KEY = "replay_run_global"
ADVISORY_LOCK_PER_ACTOR_PREFIX = "replay_run_actor:"

# subprocess.Popen env-var whitelist (V3 §6.2 + §12 #14 — no live secrets).
# subprocess.Popen env-var 白名單（V3 §6.2 + §12 #14 — 無 live secrets）。
SUBPROCESS_ENV_WHITELIST = (
    "OPENCLAW_BASE_DIR",
    "OPENCLAW_DATA_DIR",
    "OPENCLAW_REPLAY_MAC_NO_PRIVATE",
    "OPENCLAW_REPLAY_RUNTIME_ENV",
    "HOME",
    "PATH",
    "USER",
    "LANG",
)


# ─── Binary path resolution / Binary 路徑解析 ────────────────────────


def resolve_replay_runner_bin() -> Path:
    """Resolve replay_runner binary path per CLAUDE.md §六 + cross-platform.
    依 CLAUDE.md §六 跨平台解析 replay_runner binary 路徑。

    Priority / 優先級:
      1. ``OPENCLAW_REPLAY_RUNNER_BIN`` env override (operator / test).
      2. ``$OPENCLAW_BASE_DIR/rust/openclaw_engine/target/release/replay_runner``.
      3. ``$OPENCLAW_BASE_DIR/rust/openclaw_engine/target/debug/replay_runner``.

    Returns Path even if binary does not exist on disk; caller surfaces
    missing-bin via 503 degraded response.
    """
    override = os.environ.get("OPENCLAW_REPLAY_RUNNER_BIN", "").strip()
    if override:
        return Path(override)
    base_dir = os.environ.get("OPENCLAW_BASE_DIR", "")
    if base_dir:
        release_path = (
            Path(base_dir) / "rust/openclaw_engine/target/release/replay_runner"
        )
        if release_path.exists():
            return release_path
        debug_path = (
            Path(base_dir) / "rust/openclaw_engine/target/debug/replay_runner"
        )
        return debug_path
    return Path("replay_runner")


def resolve_artifact_output_dir(run_id: str) -> Path:
    """Resolve per-run artifact output directory.
    解析 per-run artifact 輸出目錄。

    Linux: $OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/.
    Mac:   /tmp/replay_artifacts_test_only/<run_id>/.
    """
    import sys
    if sys.platform == "darwin":
        return Path("/tmp/replay_artifacts_test_only") / run_id
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "replay_artifacts" / run_id


# ─── PG advisory lock helpers / PG advisory lock 輔助 ────────────────


def try_acquire_pg_advisory_locks(
    cur: Any, actor_id: str
) -> Tuple[bool, Optional[str]]:
    """Try to acquire global + per-actor advisory locks within current xact.
    在當前 transaction 內嘗試取得 global + per-actor advisory lock。

    Wave 2 dispatch v1.1 §6 Option C: PG advisory lock retrofit replaces
    in-memory ``_ACTIVE_RUNS`` dict. Both locks must be acquired in the
    SAME transaction; commit/rollback auto-releases (xact-scoped).

    Returns / 回傳:
        (True, None) on both locks acquired;
        (False, "replay_global_cap_exceeded") if global lock contended;
        (False, "replay_per_actor_cap_exceeded") if per-actor lock contended.
    """
    # Step 1: global lock.
    # 步驟 1：global lock。
    cur.execute(
        "SELECT pg_try_advisory_xact_lock(hashtext(%s));",
        (ADVISORY_LOCK_GLOBAL_KEY,),
    )
    row = cur.fetchone()
    if not (row and row[0]):
        return False, "replay_global_cap_exceeded"

    # Step 2: per-actor lock (within same xact).
    # 步驟 2：per-actor lock（同 xact 內）。
    per_actor_key = f"{ADVISORY_LOCK_PER_ACTOR_PREFIX}{actor_id}"
    cur.execute(
        "SELECT pg_try_advisory_xact_lock(hashtext(%s));",
        (per_actor_key,),
    )
    row = cur.fetchone()
    if not (row and row[0]):
        return False, "replay_per_actor_cap_exceeded"

    return True, None


def count_active_runs_for_actor(cur: Any, actor_id: str) -> int:
    """Count active runs (status IN starting/running) for one actor in V045.
    在 V045 計算 actor 的 active run 數（status IN starting/running）。
    """
    cur.execute(
        """
        SELECT COUNT(*) FROM replay.run_state
         WHERE actor_id = %s
           AND status IN ('starting','running');
        """,
        (actor_id,),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def count_active_runs_global(cur: Any) -> int:
    """Count global active runs (status IN starting/running) in V045.
    在 V045 計算全局 active run 數（status IN starting/running）。
    """
    cur.execute(
        """
        SELECT COUNT(*) FROM replay.run_state
         WHERE status IN ('starting','running');
        """,
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def v045_table_present(cur: Any) -> bool:
    """Check whether replay.run_state (V045) is deployed.
    檢查 replay.run_state（V045）是否已部署。
    """
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'replay' AND table_name = 'run_state' "
            "LIMIT 1;"
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001 — fail-closed schema probe
        return False


# ─── Subprocess spawn / 子程序啟動 ───────────────────────────────────


def spawn_replay_runner(
    *,
    run_id: str,
    manifest_id: str,
    output_dir: Path,
) -> Tuple[Optional[int], Optional[str]]:
    """Spawn replay_runner Rust binary; return (pid, err_or_none).
    Spawn replay_runner Rust binary；回 (pid, err_or_none)。

    Whitelisted environment variables (no live secrets propagation per
    V3 §6.2 + §12 #14 red-line). Args = ``--manifest-id <UUID>
    --output-dir <path> --run-id <UUID>``.

    白名單 env 傳遞（無 live secrets per V3 §6.2 + §12 #14 紅線）。
    Args = ``--manifest-id <UUID> --output-dir <path> --run-id <UUID>``。

    Returns / 回傳:
        (pid, None) on successful Popen;
        (None, "binary_not_found") if binary path does not exist;
        (None, f"spawn_error:{type(exc).__name__}") on other failures;
        (None, f"mkdir_error:{type(exc).__name__}") on output_dir mkdir failure.
    """
    bin_path = resolve_replay_runner_bin()
    if not bin_path.exists():
        log.warning(
            "replay_runner binary not found at %s; "
            "set OPENCLAW_REPLAY_RUNNER_BIN to override",
            bin_path,
        )
        return None, "binary_not_found"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("output_dir mkdir failed: %s", exc)
        return None, f"mkdir_error:{type(exc).__name__}"

    argv = [
        str(bin_path),
        "--manifest-id", manifest_id,
        "--output-dir", str(output_dir),
        "--run-id", run_id,
    ]

    # Whitelisted env propagation.
    # 白名單 env 傳遞。
    child_env = {
        k: os.environ[k]
        for k in SUBPROCESS_ENV_WHITELIST
        if k in os.environ
    }

    try:
        proc = subprocess.Popen(  # noqa: S603 — argv static + bin path resolved
            argv,
            env=child_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        log.info(
            "replay_runner spawned: pid=%d run_id=%s manifest_id=%s output_dir=%s",
            proc.pid, run_id, manifest_id, output_dir,
        )
        return proc.pid, None
    except (OSError, FileNotFoundError, PermissionError) as exc:
        log.warning(
            "replay_runner Popen failed: %s (bin=%s)",
            exc, bin_path,
        )
        return None, f"spawn_error:{type(exc).__name__}"


# ─── Module export / 模組匯出 ────────────────────────────────────────
__all__ = [
    "ADVISORY_LOCK_GLOBAL_KEY",
    "ADVISORY_LOCK_PER_ACTOR_PREFIX",
    "SUBPROCESS_ENV_WHITELIST",
    "count_active_runs_for_actor",
    "count_active_runs_global",
    "resolve_artifact_output_dir",
    "resolve_replay_runner_bin",
    "spawn_replay_runner",
    "try_acquire_pg_advisory_locks",
    "v045_table_present",
]
