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
      - subprocess.Popen wrapper with whitelisted env propagation +
        spawn-then-poll dead-runner detection (REF-20 Sprint 1 Track A —
        no live secrets per V3 §6.2 + §12 #14 red-line)
      - manifest JSON fixture writer (REF-20 Sprint 1 Track A —
        embeds run_id so Rust runner can self-verify basename match)
      - psutil-based PID identity verifier (REF-20 Sprint 1 Track A
        helper, also used by Track C P0-4 cancel pid check)
      - artifact path allowlist guard (REF-20 Sprint 1 Track C P0-5b —
        denies path traversal attacks via ``Path.resolve().is_relative_to``
        check against ``OPENCLAW_DATA_DIR/replay_artifacts/`` root)
      - release profile detector (REF-20 Sprint 1 Track C P0-2 —
        ``OPENCLAW_RELEASE_PROFILE`` reading, used to gate the
        ``OPENCLAW_REPLAY_VERIFY_TEST_KEY`` test seed in production)

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
      - subprocess.Popen 包裝 + spawn-then-poll 早死偵測（REF-20 Sprint 1
        Track A — 白名單 env 傳遞；無 live secrets per V3 §6.2 + §12 #14 紅線）
      - manifest JSON fixture writer（REF-20 Sprint 1 Track A —
        embed run_id 使 Rust runner 可自驗 basename 一致）
      - psutil-based PID 身份驗證器（REF-20 Sprint 1 Track A 共用 helper，
        Track C P0-4 cancel pid 檢查亦用）
      - artifact 路徑白名單守門（REF-20 Sprint 1 Track C P0-5b —
        透過 ``Path.resolve().is_relative_to`` 對 ``OPENCLAW_DATA_DIR/
        replay_artifacts/`` 根目錄檢查，封堵路徑遍歷攻擊）
      - release profile 偵測器（REF-20 Sprint 1 Track C P0-2 —
        讀 ``OPENCLAW_RELEASE_PROFILE``，用以在 production 阻斷
        ``OPENCLAW_REPLAY_VERIFY_TEST_KEY`` test seed）

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

import json
import logging
import os
import subprocess
import time
from datetime import datetime, timezone
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


def _is_executable_file(p: Path) -> bool:
    """Validate path is a regular file with executable bit set.
    驗 path 是 regular file 且具執行 bit。

    Guards against directory + non-executable + symlink-to-deleted attack
    surfaces where Path.exists() alone returns True but subprocess.Popen
    will raise PermissionError / IsADirectoryError. E2 R1 review HIGH-1
    finding (2026-05-04).
    防範 directory + 非執行檔 + symlink 指向已刪除目標等場景；
    這些情境 ``Path.exists()`` 會回 True 但 ``subprocess.Popen`` 必拋
    ``PermissionError`` / ``IsADirectoryError``。E2 R1 review HIGH-1
    發現（2026-05-04）。

    ``Path.is_file()`` 已 follow symlink 至目標、過濾 dangling symlink
    與 directory；再用 ``os.access(p, os.X_OK)`` 驗 effective UID 對該
    file 具執行權，封堵「mode 0644 file 名為 replay_runner」誤建場景。
    """
    return p.is_file() and os.access(p, os.X_OK)


def resolve_replay_runner_bin() -> Path:
    """Resolve replay_runner binary path per CLAUDE.md §六 + cross-platform.
    依 CLAUDE.md §六 跨平台解析 replay_runner binary 路徑。

    REF-20 Sprint A R1-T1 (2026-05-04): Codex production-readiness review
    revealed the legacy chain only probed the crate-local layout
    ``rust/openclaw_engine/target/...`` while cargo workspace (post
    2026-04-15 root ``Cargo.toml`` workspace consolidation) emits to
    ``rust/target/...``. The disk-truth divergence caused ``/run`` to
    surface ``binary_not_found`` even when ``cargo build --release -p
    openclaw_engine --bin replay_runner`` had succeeded. This 5-path
    fallback adds the workspace target layout in front while keeping
    the legacy nested layout as a compat path for partial rollouts.

    REF-20 Sprint A R1-T1（2026-05-04）：Codex production-readiness 審
    揭露舊鏈僅探 crate-local 路徑 ``rust/openclaw_engine/target/...``，
    但 cargo workspace（2026-04-15 root ``Cargo.toml`` workspace 合併
    後）emit 到 ``rust/target/...``。磁碟真相落差導致 ``/run`` 仍回
    ``binary_not_found`` 即使 ``cargo build --release -p openclaw_engine
    --bin replay_runner`` 已成功。此 5 path fallback 把 workspace target
    放前，legacy nested 留作 partial rollout 的 compat 路徑。

    Priority / 優先級:
      1. ``OPENCLAW_REPLAY_RUNNER_BIN`` env override (operator / test).
      2. ``$OPENCLAW_BASE_DIR/rust/target/release/replay_runner``
         (workspace; current real layout post 2026-04-15).
      3. ``$OPENCLAW_BASE_DIR/rust/target/debug/replay_runner``
         (workspace; dev path).
      4. ``$OPENCLAW_BASE_DIR/rust/openclaw_engine/target/release/replay_runner``
         (legacy nested; partial-rollout compat).
      5. ``$OPENCLAW_BASE_DIR/rust/openclaw_engine/target/debug/replay_runner``
         (legacy debug; final fallback — may not exist; caller surfaces 503).

    Existence check uses ``_is_executable_file()`` (E2 R1 review HIGH-1):
    ``Path.is_file()`` skips directories + dangling symlinks, and
    ``os.access(..., os.X_OK)`` verifies executable bit so caller
    ``subprocess.Popen`` does not raise ``IsADirectoryError`` /
    ``PermissionError`` post-resolution.

    存在性檢查走 ``_is_executable_file()``（E2 R1 review HIGH-1）：
    ``Path.is_file()`` 過濾 directory + dangling symlink；
    ``os.access(..., os.X_OK)`` 驗執行 bit，使後續 ``subprocess.Popen``
    不會在解析後仍拋 ``IsADirectoryError`` / ``PermissionError``。

    Returns Path even if binary does not exist on disk; caller surfaces
    missing-bin via 503 degraded response.
    """
    # Step 1: Operator/test override (highest priority).
    # 步驟 1：operator / test 覆寫（最高優先）。
    override = os.environ.get("OPENCLAW_REPLAY_RUNNER_BIN", "").strip()
    if override:
        return Path(override)

    # E2 R1 review MEDIUM-1: strip whitespace-only OPENCLAW_BASE_DIR
    # so leading/trailing spaces never propagate into Path() and become
    # garbage filesystem paths (e.g. "   /rust/target/release/...").
    # E2 R1 review MEDIUM-1：strip 掉 OPENCLAW_BASE_DIR 的前後空白，
    # 避免空白被併進 Path() 變成 garbage 路徑。
    base_dir = os.environ.get("OPENCLAW_BASE_DIR", "").strip()
    if not base_dir:
        # PATH-relative last resort — used in CI / sandbox runs where
        # OPENCLAW_BASE_DIR is unset and the binary is staged into PATH.
        # PATH 相對的最後 fallback — 用於 CI / sandbox 未設 OPENCLAW_BASE_DIR
        # 但 binary 已 stage 進 PATH 的場景。
        return Path("replay_runner")

    # Step 2: Workspace target release (current real layout 2026-05-04).
    # 步驟 2：workspace target release（2026-05-04 真實佈局）。
    workspace_release = Path(base_dir) / "rust/target/release/replay_runner"
    if _is_executable_file(workspace_release):
        return workspace_release

    # Step 3: Workspace target debug (dev path).
    # 步驟 3：workspace target debug（dev 路徑）。
    workspace_debug = Path(base_dir) / "rust/target/debug/replay_runner"
    if _is_executable_file(workspace_debug):
        return workspace_debug

    # Step 4: Legacy nested crate-local release (compat fallback for
    # partial rollouts that haven't migrated to workspace target).
    # 步驟 4：legacy nested crate-local release（partial rollout 尚未遷移
    # 到 workspace target 時的 compat fallback）。
    legacy_release = (
        Path(base_dir) / "rust/openclaw_engine/target/release/replay_runner"
    )
    if _is_executable_file(legacy_release):
        return legacy_release

    # Step 5: Legacy nested crate-local debug (final fallback).
    # 步驟 5：legacy nested crate-local debug（最終 fallback）。
    legacy_debug = (
        Path(base_dir) / "rust/openclaw_engine/target/debug/replay_runner"
    )
    return legacy_debug  # may not exist; caller surfaces via 503


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


def table_present(cur: Any, schema: str, table: str) -> bool:
    """Generic schema-presence factory used by REF-20 V### gating paths.
    REF-20 V### 路徑統一用的 schema 存在性 factory。

    Sprint 1 Track D consolidates the legacy ``v045_table_present`` into a
    parameterised factory so V049/V050/V051 callers can probe their FK
    targets with the same fail-closed semantics. The legacy
    ``v045_table_present`` and new V049/V050/V051 helpers below are thin
    wrappers around this factory; they remain importable for callers that
    type-check on the helper's name.

    Sprint 1 Track D 把 legacy ``v045_table_present`` 收斂成參數化 factory，
    讓 V049/V050/V051 callers 用相同 fail-closed 語意 probe FK 目標。下方
    legacy ``v045_table_present`` 與新 V049/V050/V051 helper 都是本 factory
    的薄封裝；按 helper 名 type-check 的 caller 仍可 import。

    Returns / 回傳:
        True  — schema.table exists in catalog
        False — table absent OR catalog query failed (fail-closed default)
    """
    try:
        cur.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s "
            "LIMIT 1;",
            (schema, table),
        )
        return cur.fetchone() is not None
    except Exception:  # noqa: BLE001 — fail-closed schema probe
        return False


def v045_table_present(cur: Any) -> bool:
    """Check whether replay.run_state (V045) is deployed.
    檢查 replay.run_state（V045）是否已部署。

    Thin wrapper around ``table_present(cur, 'replay', 'run_state')``;
    kept for backward-compat with replay_routes.py legacy callers.
    """
    return table_present(cur, "replay", "run_state")


def v049_table_present(cur: Any) -> bool:
    """Check whether replay.experiments (V049 full 22-column form) is deployed.
    檢查 replay.experiments（V049 完整 22 column 型）是否已部署。

    Note: V041 already creates a 4-column stub of replay.experiments; this
    helper does NOT distinguish V041 stub from V049 full schema. Callers
    requiring V049 22-column shape should additionally probe specific
    column presence (e.g. manifest_jsonb, signature_key_ref).

    註：V041 已建 4 column stub 的 replay.experiments；本 helper 不分辨 V041
    stub 與 V049 完整 schema。需要 V049 22 column shape 的 caller 應另探具體
    column（如 manifest_jsonb / signature_key_ref）。
    """
    return table_present(cur, "replay", "experiments")


def v050_table_present(cur: Any) -> bool:
    """Check whether replay.simulated_fills (V050) is deployed.
    檢查 replay.simulated_fills（V050）是否已部署。
    """
    return table_present(cur, "replay", "simulated_fills")


def v051_columns_present(cur: Any) -> bool:
    """Check whether learning.mlde_shadow_recommendations has V051 columns.
    檢查 learning.mlde_shadow_recommendations 是否已加 V051 兩欄。

    V051 adds replay_experiment_id (uuid) + manifest_hash (bytea) + paired
    CHECK chk_mlde_shadow_replay_lineage. This helper probes the two
    column names; callers needing the CHECK constraint should query
    pg_constraint directly.

    V051 加 replay_experiment_id（uuid）+ manifest_hash（bytea）+ 配對 CHECK
    chk_mlde_shadow_replay_lineage。本 helper 探兩欄存在；需 CHECK 約束的
    caller 直接 query pg_constraint。
    """
    try:
        cur.execute(
            "SELECT COUNT(*) "
            "FROM information_schema.columns "
            "WHERE table_schema = 'learning' "
            "  AND table_name = 'mlde_shadow_recommendations' "
            "  AND column_name IN ('replay_experiment_id', 'manifest_hash');"
        )
        row = cur.fetchone()
        return bool(row and row[0] == 2)
    except Exception:  # noqa: BLE001 — fail-closed schema probe
        return False


# ─── Subprocess spawn / 子程序啟動 ───────────────────────────────────


def spawn_replay_runner(
    *,
    run_id: str,
    manifest_id: str,
    output_dir: Path,
    manifest_fixture_path: Path,
    poll_grace_seconds: float = 1.5,
) -> Tuple[Optional[int], Optional[str]]:
    """Spawn replay_runner Rust binary + poll once for early-death detection.
    Spawn replay_runner Rust binary，並在 ``poll_grace_seconds`` 後 poll 一次
    偵測早死亡。

    REF-20 Sprint 1 Track A — schema-aligned argv:
      - Rust CLI parser (``cli.rs``) accepts only POSIX-style flags
        ``--manifest <PATH> --output-dir <PATH> [--baseline-id <STR>]``.
        The previous Python sibling passed ``--manifest-id <UUID>
        --run-id <UUID>`` which Rust rejected as ``CliError::UnknownArg``
        (binary exited non-zero, but Python never polled, so V045 row
        stayed at ``status='running'`` — the entire Wave 1-9 e2e replay
        path never actually executed). This commit aligns Python with
        Rust by passing the manifest fixture path written via
        ``_write_manifest_fixture``; ``run_id`` lives inside the manifest
        JSON (Rust ``ReplayManifest`` struct ``run_id: Option<String>``).
        ``manifest_id`` is kept as logging metadata only (audit trail).

    REF-20 Sprint 1 Track A — schema-aligned argv：
      - Rust CLI parser（``cli.rs``）只接受 POSIX 風格旗標
        ``--manifest <PATH> --output-dir <PATH> [--baseline-id <STR>]``。
        前版 Python 傳 ``--manifest-id <UUID> --run-id <UUID>`` 被 Rust 拒
        為 ``CliError::UnknownArg``（binary 非 0 結束，但 Python 沒 poll，
        V045 row 卡在 ``status='running'`` — 整個 Wave 1-9 e2e replay 路徑
        從未真正跑過）。本 commit 將 Python 對齊 Rust：傳由
        ``_write_manifest_fixture`` 寫出的 manifest fixture 路徑；``run_id``
        於 manifest JSON 內（Rust ``ReplayManifest`` 加 ``run_id: Option<String>``
        欄位）。``manifest_id`` 純為 logging metadata（audit trail）。

    Whitelisted environment variables (no live secrets propagation per
    V3 §6.2 + §12 #14 red-line).

    白名單 env 傳遞（無 live secrets per V3 §6.2 + §12 #14 紅線）。

    Args:
        run_id: V045 PK；audit / logging only（不再傳 argv，從 manifest 讀）。
        manifest_id: V045 manifest_id FK；audit / logging only。
        output_dir: per-run artifact 目錄（Rust ``--output-dir`` arg）。
            Caller responsible for `output_dir.basename() == run_id` invariant
            (Rust ``replay_runner`` self-verifies basename matches manifest
            ``run_id`` field; mismatch → CliError + abort).
        manifest_fixture_path: 已落盤的 manifest JSON path（Rust ``--manifest`` arg）。
            通常由 ``_write_manifest_fixture(run_id, manifest_data, output_dir)`` 寫出。
        poll_grace_seconds: spawn 後等多久 poll 一次（預設 1.5s）。

    Returns / 回傳:
        (pid, None) on successful Popen + alive after poll;
        (None, "binary_not_found") if binary path does not exist;
        (None, "manifest_fixture_not_found") if manifest_fixture_path missing;
        (None, "mkdir_error:<ExcName>") on output_dir mkdir failure;
        (None, "spawn_error:<ExcName>") on Popen failure;
        (None, "spawn_died_early:exit=<rc>") on early death within poll window
            (binary exited non-zero before poll_grace_seconds elapsed —
            typical of CLI schema mismatch, manifest hash drift, etc.).
    """
    bin_path = resolve_replay_runner_bin()
    if not bin_path.exists():
        log.warning(
            "replay_runner binary not found at %s; "
            "set OPENCLAW_REPLAY_RUNNER_BIN to override",
            bin_path,
        )
        return None, "binary_not_found"

    # Manifest fixture must already exist on disk (Caller writes it via
    # _write_manifest_fixture before spawn; this is fail-closed).
    # Manifest fixture 必先落盤（Caller 在 spawn 前透過 _write_manifest_fixture
    # 寫；這是 fail-closed 守門）。
    if not manifest_fixture_path.exists():
        log.warning(
            "replay_runner manifest fixture not found at %s",
            manifest_fixture_path,
        )
        return None, "manifest_fixture_not_found"

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.warning("output_dir mkdir failed: %s", exc)
        return None, f"mkdir_error:{type(exc).__name__}"

    argv = [
        str(bin_path),
        "--manifest", str(manifest_fixture_path),
        "--output-dir", str(output_dir),
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
    except (OSError, FileNotFoundError, PermissionError) as exc:
        log.warning(
            "replay_runner Popen failed: %s (bin=%s)",
            exc, bin_path,
        )
        return None, f"spawn_error:{type(exc).__name__}"

    # Poll-then-INSERT 'running' (root cause #2 of REF-20 Sprint 1 Track A).
    # The previous flow trusted Popen to mean "alive"; Rust binary could
    # exit non-zero on CliError::UnknownArg + Python never noticed.
    # 1.5s grace is the upper bound observed for Linux release binary cold
    # cache + CLI parse + manifest fail-closed path.
    #
    # Poll-then-INSERT 'running'（REF-20 Sprint 1 Track A 第二個根因）。
    # 前版流程信任 Popen = alive；Rust binary 可能 CliError::UnknownArg 非 0
    # 結束，Python 完全沒察覺。1.5s grace 為 Linux release binary cold cache
    # + CLI parse + manifest fail-closed 觀察到的上限。
    if poll_grace_seconds > 0:
        time.sleep(poll_grace_seconds)
    rc = proc.poll()
    if rc is not None and rc != 0:
        log.warning(
            "replay_runner died early: pid=%d exit=%d run_id=%s "
            "(likely CLI schema mismatch / manifest fail-closed)",
            proc.pid, rc, run_id,
        )
        return None, f"spawn_died_early:exit={rc}"
    if rc is not None and rc == 0:
        # Pathological: binary exited cleanly within grace window. Treat
        # as alive=False since downstream wait/UPDATE assumes a live PID.
        # 病態：binary 在 grace 視窗內乾淨退出。視為 alive=False，因下游
        # wait/UPDATE 假設 PID 仍活。
        log.warning(
            "replay_runner exited 0 within poll grace: pid=%d run_id=%s "
            "(report should still be on disk)",
            proc.pid, run_id,
        )
        return None, "spawn_died_early:exit=0"

    log.info(
        "replay_runner spawned + alive after poll: pid=%d run_id=%s "
        "manifest_id=%s manifest=%s output_dir=%s",
        proc.pid, run_id, manifest_id, manifest_fixture_path, output_dir,
    )
    return proc.pid, None


# ─── Manifest fixture writer + PID identity verifier / Manifest fixture 寫入器 + PID 身份驗證 ─

# Default manifest fixture filename (rust replay_runner reads this exact name
# when sibling key.hex archive is also placed in the same directory).
# 預設 manifest fixture 檔名（Rust replay_runner 讀此檔名；同目錄並擺
# sibling key.hex archive 時亦相容）。
MANIFEST_FIXTURE_FILENAME = "manifest.json"


def build_default_manifest_payload(
    *,
    experiment_id: str,
    output_dir: Path,
) -> dict:
    """Build the default manifest payload for Track A spawn flow.
    構造 Track A spawn 流程預設 manifest payload。

    REF-20 Sprint 1 Track A — Wave 4 ``ReplayManifest`` struct reads 6
    minimum fields (experiment_id / data_tier / fixture_uri / signature /
    manifest_hash / signature_key_ref). Track A uses *placeholder* values
    for signature/hash because Wave 4 ``load_and_verify_manifest`` falls
    through with stderr warning when sibling key.hex archive is absent
    (Wave 6 V042 SQL archive integration replaces with full HMAC verify).
    ``run_id`` is added by ``write_manifest_fixture`` (NOT here) so this
    payload is run_id-independent + cacheable.

    REF-20 Sprint 1 Track A — Wave 4 ``ReplayManifest`` struct 讀 6 個
    最小欄位。Track A 用 *placeholder* 值給 signature/hash（Wave 6 V042
    SQL archive integration 換實 HMAC verify）。``run_id`` 由
    ``write_manifest_fixture`` 添加（**不**在此），使本 payload 與
    run_id 解耦 + 可快取。

    Cross-language envelope contract / 跨語言 envelope 契約:
        Three keys belong to the *envelope* (signature / manifest_hash /
        signature_key_ref) and are stripped before signing. The body bytes
        that ARE signed are the remaining keys re-serialized canonically
        with sort_keys=True + separators=(',', ':') + ensure_ascii=False.
        Rust mirror: ``rust/openclaw_engine/src/replay/manifest_signer.rs::
        canonical_body_for_signing`` (constant ``ENVELOPE_KEYS_FOR_SIGNING``;
        see line 574). Python sibling ``replay/manifest_signer.py::sign``
        consumes the same canonical bytes shape (E2 finding F1 retrofit
        invariant — ensure_ascii=False is critical because Python default
        True would emit ``\\uXXXX`` for non-ASCII while Rust serde_json
        emits raw UTF-8 → byte mismatch).

        三個 key 屬 envelope（簽名前剝除），其餘 key 用 sort_keys=True +
        separators=(',', ':') + ensure_ascii=False 重序列化為簽名 body
        bytes。Rust 鏡像見 ``rust/openclaw_engine/src/replay/manifest_signer.rs::
        canonical_body_for_signing``（常量 ``ENVELOPE_KEYS_FOR_SIGNING``；
        line 574）。Python ``replay/manifest_signer.py::sign`` 接同 canonical
        bytes 形狀（E2 finding F1 retrofit 不變量 — ensure_ascii=False 為關鍵，
        Python 預設 True 會輸出 ``\\uXXXX`` 而 Rust serde_json 輸出 raw
        UTF-8 → byte 不等）。

    Args:
        experiment_id: V045 experiment_id。
        output_dir: per-run artifact 目錄；fixture_uri 預設指向 sibling
            ``fixture.json``（caller 後續可由 OPENCLAW_REPLAY_FIXTURE_URI
            env var 或 manifest dict mutation 覆寫）。

    Returns:
        dict 含 6 個 minimum field（無 run_id；由 write_manifest_fixture 加）。
    """
    return {
        "experiment_id": experiment_id,
        "data_tier": "S3",
        "fixture_uri": (
            os.environ.get("OPENCLAW_REPLAY_FIXTURE_URI", "").strip()
            or str(output_dir / "fixture.json")
        ),
        "signature": "placeholder_signature_wave6_v042_pending",
        "manifest_hash": "placeholder_hash_wave6_v042_pending",
        "signature_key_ref": "placeholder_key_ref",
    }


def write_manifest_fixture(
    *,
    run_id: str,
    manifest_data: dict,
    output_dir: Path,
    fixture_filename: str = MANIFEST_FIXTURE_FILENAME,
) -> Path:
    """Write manifest JSON fixture to ``output_dir / fixture_filename``.
    寫 manifest JSON fixture 到 ``output_dir / fixture_filename``。

    REF-20 Sprint 1 Track A — Python writes the manifest the Rust runner
    reads from ``--manifest <PATH>``. ``run_id`` is **embedded inside** the
    manifest JSON (top-level ``run_id`` field) so the Rust side can
    self-verify: ``manifest.run_id == output_dir.basename()`` invariant
    (PA push back #2 — guards against Python/Rust UUID drift).

    REF-20 Sprint 1 Track A — Python 寫 manifest 給 Rust runner 從
    ``--manifest <PATH>`` 讀。``run_id`` **嵌入** manifest JSON 內
    （頂層 ``run_id`` 欄位）使 Rust 端可自驗：``manifest.run_id ==
    output_dir.basename()`` 不變量（PA push back #2 — 防 Python/Rust
    UUID 漂移）。

    JSON serialisation contract / JSON 序列化契約 (E2 finding F1):
        Disk-fixture bytes are written with ``sort_keys=True +
        separators=(',', ':') + ensure_ascii=False`` so Rust serde_json
        ``canonical_body_for_signing`` (after envelope strip) yields
        byte-equal canonical body for HMAC verify. Three settings are all
        load-bearing:

          * sort_keys=True       — alphabetical keys ↔ Rust BTreeMap default.
          * separators=(',', ':') — compact ↔ Rust serde_json compact default.
          * ensure_ascii=False    — raw UTF-8 ↔ Rust serde_json never escapes.

        Without ``ensure_ascii=False`` Python default writes ``\\u6d4b\\u8bd5``
        for U+6D4B U+8BD5 (测试) while Rust serde_json reads the
        same characters but re-serialises them as raw UTF-8 bytes; the
        canonical form would differ → HMAC verify fails permanently.

        Rust contract reference:
        ``rust/openclaw_engine/src/replay/manifest_signer.rs`` line 574-575
        (``pub const ENVELOPE_KEYS_FOR_SIGNING: [&str; 3] = ["signature",
        "manifest_hash", "signature_key_ref"]``) +
        ``canonical_body_for_signing`` (line 594-625).

        磁碟 fixture bytes 用 ``sort_keys=True + separators=(',', ':') +
        ensure_ascii=False`` 寫入，使 Rust serde_json
        ``canonical_body_for_signing`` 剝除 envelope 後 byte-equal 與
        Python sign 路徑算 canonical body 結果。三項設定缺一不可
        （sort_keys ↔ BTreeMap、compact ↔ serde_json default、
        ensure_ascii=False ↔ raw UTF-8 不 escape）。

    Args:
        run_id: V045 PK；強制 embed 到 manifest JSON。
        manifest_data: 既有 manifest dict（會被 deep-copied 後加 run_id 鍵）。
            Caller 提供 ``experiment_id`` / ``data_tier`` / ``fixture_uri`` /
            ``signature`` / ``manifest_hash`` / ``signature_key_ref``；本函式
            僅添加 ``run_id``，不改其他欄位。
        output_dir: per-run artifact 目錄；不存在則 mkdir。
        fixture_filename: 預設 ``manifest.json``（與 Rust e2e fixture 對齊）。

    Returns / 回傳:
        Path 於落盤的 manifest JSON 檔案。

    Raises:
        ValueError: ``run_id`` 為空或 ``manifest_data`` 不是 dict。
        OSError: mkdir 或 write 失敗（caller 由 spawn fail-closed 路徑捕獲）。
    """
    if not run_id:
        raise ValueError("run_id must be a non-empty string")
    if not isinstance(manifest_data, dict):
        raise ValueError("manifest_data must be a dict")

    output_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = output_dir / fixture_filename

    # Deep-copy via JSON round-trip so caller's dict is untouched + we get
    # only JSON-serialisable payload (no datetime / Path leakage).
    # The canonical-form kwargs (separators / ensure_ascii) are kept on the
    # round-trip dump as well so any non-string scalar that Python's default
    # json prints differently from the disk-bytes path (none today, but
    # defensive against future field additions) cannot drift between the
    # two passes — both paths use the SAME canonical settings.
    #
    # 透過 JSON round-trip 深拷貝：caller 的 dict 不被改 + 確保 payload 只含
    # JSON 可序化值（無 datetime / Path 洩漏）。round-trip dump 也帶上 canonical
    # 參數（separators / ensure_ascii），防未來新欄位讓兩段 dump 行為漂移。
    payload = json.loads(
        json.dumps(
            manifest_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        )
    )
    payload["run_id"] = run_id

    # Disk-fixture write: canonical form for cross-language byte-equal
    # contract (E2 finding F1). NOT human-pretty; operator inspecting the
    # fixture should pipe through ``jq .`` for indentation. The byte-equal
    # contract dominates because Rust serde_json
    # ``canonical_body_for_signing`` re-canonicalizes to the same shape;
    # if Python wrote ``\\uXXXX`` for non-ASCII or used spaced separators,
    # any subsequent Python sign call computing canonical bytes via the
    # same json.dumps kwargs would still match Rust — but mixed kwargs
    # between this writer and any future Python sign helper would silently
    # diverge. Keeping kwargs identical here is the cheapest invariant.
    #
    # 磁碟 fixture 寫入：跨語言 byte-equal 契約所需 canonical form（E2 finding
    # F1）。**非**人讀美化版；operator 檢查 fixture 請用 ``jq .`` 加縮排。
    # byte-equal 契約優先，因 Rust serde_json ``canonical_body_for_signing``
    # 會 re-canonicalize 至同 shape；若 Python 寫 ``\\uXXXX`` 或加 space
    # separator，後續 Python sign helper 用相同 dumps kwargs 仍可對齊 Rust，
    # 但本 writer 與未來 sign helper 之間 kwargs 不同就會悄悄漂移 — 此處
    # kwargs 統一是最便宜的不變量。
    fixture_path.write_text(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info(
        "manifest fixture written: run_id=%s path=%s",
        run_id, fixture_path,
    )
    return fixture_path


def verify_replay_runner_pid(pid: int) -> Tuple[bool, Optional[str]]:
    """Verify ``pid`` belongs to a process whose argv contains ``replay_runner``.
    驗證 ``pid`` 的 process argv 含 ``replay_runner``。

    REF-20 Sprint 1 Track A helper, also reused by Track C (P0-4 cancel
    pid identity check). PID-reuse safe: ``psutil.Process(pid).cmdline()``
    returns the *current* process's argv; if the original replay_runner
    died and pid was reused by an unrelated process, cmdline is unrelated
    string list and check returns False (fail-closed).

    REF-20 Sprint 1 Track A 共用 helper，Track C（P0-4 cancel pid 身份
    檢查）亦會用。PID reuse 安全：``psutil.Process(pid).cmdline()`` 回
    *當前* process 的 argv；若原 replay_runner 已死且 pid 被無關 process
    復用，cmdline 將是無關字串清單，本檢查回 False（fail-closed）。

    Args:
        pid: OS process id from V045 ``subprocess_pid`` column.

    Returns / 回傳:
        (True, None) — argv contains 'replay_runner';
        (False, "pid_not_found") — process does not exist;
        (False, "pid_no_cmdline") — process exists but cmdline empty (zombie);
        (False, "pid_identity_mismatch:got=<truncated_cmdline>") — argv does
            not contain 'replay_runner' (PID reuse / wrong PID).
        (False, "psutil_unavailable") — psutil import failed (Mac dev fallback).
    """
    try:
        import psutil  # type: ignore[import-not-found]
    except ImportError:
        log.warning("psutil unavailable; PID identity check skipped (fail-closed)")
        return False, "psutil_unavailable"

    try:
        proc = psutil.Process(pid)
        cmdline = proc.cmdline()
    except psutil.NoSuchProcess:
        return False, "pid_not_found"
    except psutil.AccessDenied:
        return False, "pid_access_denied"
    except Exception as exc:  # noqa: BLE001 — fail-closed identity probe
        log.warning("psutil.Process(%d) failed: %s", pid, exc)
        return False, f"psutil_error:{type(exc).__name__}"

    if not cmdline:
        return False, "pid_no_cmdline"
    joined = " ".join(cmdline)
    if "replay_runner" not in joined:
        truncated = joined[:80]  # bound payload size
        return False, f"pid_identity_mismatch:got={truncated}"
    return True, None


# ─── Track C extracted helpers / Track C 抽出 helpers (LOC budget relief) ─

# Default statement_timeout for replay_routes safe-pg helpers (ms).
# replay_routes safe-pg helpers 的預設 statement_timeout（毫秒）。
DEFAULT_PG_STATEMENT_TIMEOUT_MS = 2_000


def replay_response_envelope(
    data: Any,
    *,
    degraded: bool = False,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """Standard replay response envelope (mirrors agents_routes shape).
    標準 replay response 信封（鏡像 agents_routes 形狀）。
    """
    return {
        "ok": True,
        "data": data,
        "degraded": degraded,
        "reason": reason,
        "is_simulated": False,
        "data_category": "replay_lab",
    }


def emit_replay_audit_stub(
    *,
    event_type: str,
    actor_id: str,
    experiment_id: Optional[str],
    manifest_hash: Optional[str],
    decision: str,
    extra_payload: Optional[dict[str, Any]] = None,
) -> None:
    """STUB audit emitter for replay events — log only, no DB INSERT.
    STUB audit 發射器 — 僅 log，不寫 DB。

    Sprint 1 Track C uses event_type values now also enumerated by V053
    (replay_signature_test_key_blocked / replay_pid_identity_mismatch /
    replay_idor_admin_bypass / replay_artifact_path_traversal_blocked /
    replay_argv_mismatch_blocked) plus pre-existing replay_run_started /
    replay_run_cancelled / replay_manifest_verify_attempted. INSERT will
    follow once V053 deploys (PM-staged).
    Sprint 1 Track C 用的 event_type 值現亦由 V053 列舉；INSERT 等 V053
    部署後（PM 排程）。
    """
    payload = {
        "event_type": event_type,
        "actor_id": actor_id,
        "experiment_id": experiment_id,
        "manifest_hash": manifest_hash,
        "decision": decision,
        "ts_iso": datetime.now(timezone.utc).isoformat(),
        "extra": extra_payload or {},
    }
    log.info("replay_audit_stub: %s", json.dumps(payload, sort_keys=True))


def safe_pg_select(
    get_pg_conn_fn: Any,
    sql: str,
    params: tuple[Any, ...] | list[Any],
    statement_timeout_ms: int = DEFAULT_PG_STATEMENT_TIMEOUT_MS,
) -> Tuple[list[tuple[Any, ...]], Optional[str]]:
    """Run SELECT with statement_timeout + PG-degraded fail-closed envelope.
    執行 SELECT，套 statement_timeout + PG 中斷 fail-closed 信封。

    Returns (rows, err_or_none); PG unreachable → ([], "pg_unavailable");
    query exception → ([], f"pg_error:<ExcName>"). V3 §12 #22 binding.
    回 (rows, err_or_none)；PG 不可達 → ([], "pg_unavailable")；查詢異常
    → ([], f"pg_error:<ExcName>")。V3 §12 #22 約束。
    """
    rows: list[tuple[Any, ...]] = []
    with get_pg_conn_fn() as conn:
        if conn is None:
            return rows, "pg_unavailable"
        try:
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout_ms,))
            cur.execute(sql, tuple(params))
            rows = list(cur.fetchall())
            return rows, None
        except Exception as exc:  # noqa: BLE001 — fail-closed PG envelope
            log.warning("replay safe_pg_select failed: %s", exc)
            return rows, f"pg_error:{type(exc).__name__}"


# ─── Track C P0-2 release-profile gate / Track C P0-2 release-profile 守門 ─


# Recognised release profile values; production = "live" (case-insensitive).
# 已識別的 release profile 值；production = "live"（大小寫不敏感）。
RELEASE_PROFILE_LIVE = "live"
RELEASE_PROFILE_ENV_VAR = "OPENCLAW_RELEASE_PROFILE"


def is_live_release_profile() -> bool:
    """Return True iff OPENCLAW_RELEASE_PROFILE env var is set to 'live'.
    當 OPENCLAW_RELEASE_PROFILE env 為 'live' 時回 True。

    REF-20 Sprint 1 Track C P0-2 — runtime gate for production paths
    that must reject ``OPENCLAW_REPLAY_VERIFY_TEST_KEY`` injection.
    Case-insensitive comparison; missing or empty env → not live (dev /
    test default).

    REF-20 Sprint 1 Track C P0-2 — 為 production 路徑提供 runtime gate；
    必拒絕 ``OPENCLAW_REPLAY_VERIFY_TEST_KEY`` 注入。大小寫不敏感比對；
    env 缺 / 空 → 非 live（dev / test 預設）。

    Returns / 回傳:
        True iff env var equals 'live' (case-insensitive); False otherwise.
    """
    raw = os.environ.get(RELEASE_PROFILE_ENV_VAR, "").strip().lower()
    return raw == RELEASE_PROFILE_LIVE


# ─── Track C P0-5b artifact allowlist / Track C P0-5b artifact 白名單 ─


def resolve_artifact_allowlist_root() -> Path:
    """Resolve the trusted root that ALL artifact_path values MUST live within.
    解析 artifact_path 必須位於其下的信任根目錄。

    REF-20 Sprint 1 Track C P0-5b — defends against attackers who
    INSERT-d ``replay.report_artifacts.artifact_path = '/etc/passwd'``
    (or any path outside the trusted artifact tree). Production root is
    ``$OPENCLAW_DATA_DIR/replay_artifacts/``; Mac dev uses
    ``/tmp/replay_artifacts_test_only/`` (mirrors
    ``resolve_artifact_output_dir`` so writes + reads share a single root).

    REF-20 Sprint 1 Track C P0-5b — 防範 attacker 寫
    ``replay.report_artifacts.artifact_path = '/etc/passwd'``（或任何信任
    artifact tree 外的路徑）。生產根 = ``$OPENCLAW_DATA_DIR/replay_artifacts/``；
    Mac dev = ``/tmp/replay_artifacts_test_only/``（鏡像
    ``resolve_artifact_output_dir`` 讓寫 + 讀共用同一根）。

    Returns / 回傳:
        Path 解析後的信任根目錄（不保證 exists；caller 拿來給
        ``artifact_path_within_allowlist`` 對比即可）。
    """
    import sys
    if sys.platform == "darwin":
        return Path("/tmp/replay_artifacts_test_only")
    data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    return Path(data_dir) / "replay_artifacts"


def artifact_path_within_allowlist(
    artifact_path: Path,
    allowlist_root: Optional[Path] = None,
) -> Tuple[bool, Optional[str]]:
    """Check artifact_path is contained inside allowlist_root after resolve.
    解析後檢查 artifact_path 是否在 allowlist_root 之下。

    REF-20 Sprint 1 Track C P0-5b — fail-closed path-traversal guard.
    Uses ``Path.resolve()`` (Python 3.9+) to follow symlinks + collapse
    ``..`` then ``is_relative_to`` for the prefix check. If the file
    does not exist, ``resolve(strict=False)`` still returns the canonical
    absolute path (we only refuse on traversal escape, not on absent
    files — caller handles file-not-found separately).

    REF-20 Sprint 1 Track C P0-5b — fail-closed 路徑遍歷守門。用
    ``Path.resolve()``（Python 3.9+）跟隨 symlink + 折疊 ``..``，再用
    ``is_relative_to`` 做前綴檢查。檔案不存在時 ``resolve(strict=False)``
    仍回 canonical 絕對路徑（本檢查只在「遍歷逃逸」時拒絕，不為「檔案
    不存在」拒絕 — 後者由 caller 另行處理）。

    Args:
        artifact_path: V046 ``artifact_path`` column value (raw, untrusted).
        allowlist_root: Optional override; defaults to
            ``resolve_artifact_allowlist_root()``.

    Returns / 回傳:
        (True, None) — within allowlist (safe to open);
        (False, "path_traversal_escape") — resolved path is outside root;
        (False, "path_resolve_error:<ExcName>") — resolve() raised
            (e.g. invalid UTF-8 byte path, OS-specific error). Fail-closed.
    """
    root = allowlist_root if allowlist_root is not None else resolve_artifact_allowlist_root()
    try:
        resolved_artifact = artifact_path.resolve(strict=False)
        resolved_root = root.resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        log.warning(
            "artifact_path_within_allowlist: resolve failed: artifact=%s root=%s exc=%s",
            artifact_path, root, exc,
        )
        return False, f"path_resolve_error:{type(exc).__name__}"

    # Python 3.9+ has Path.is_relative_to; we keep a conservative fallback for
    # older interpreters via str.startswith with explicit os.sep boundary.
    # Python 3.9+ 有 Path.is_relative_to；老解譯器用 str.startswith 加 os.sep
    # 邊界做保守 fallback。
    try:
        within = resolved_artifact.is_relative_to(resolved_root)
    except AttributeError:  # pragma: no cover — Py<3.9 fallback
        root_str = str(resolved_root) + os.sep
        within = str(resolved_artifact).startswith(root_str) or str(resolved_artifact) == str(resolved_root)

    if not within:
        return False, "path_traversal_escape"
    return True, None


# ─── Sprint A R1-T3 /replay/health helper / R1-T3 /replay/health 輔助 ──


def compute_replay_health_state(
    *,
    rows: list[tuple[Any, ...]],
    pg_err: Optional[str],
) -> dict[str, Any]:
    """Compute /api/v1/replay/health response data + wiring_status.
    計算 /api/v1/replay/health 回應資料 + wiring_status。

    REF-20 Sprint A R1-T3 (2026-05-04): monitoring probe that lets
    operator verify the four foundational pre-conditions for /run + the
    rest of the Replay Lab actually being usable, BEFORE attempting an
    actual run:

      1. resolve_replay_runner_bin() now returns a real on-disk binary;
      2. OPENCLAW_DATA_DIR exists + is writable;
      3. replay schema is reachable (PG up + V045 + V049 deployed);
      4. binary release profile env var is reported (live / paper / blank).

    Auth on the route side is intentionally permissive
    (Depends(base.current_actor) only, NOT require_scope_and_operator)
    so monitoring infra can probe without holding write scope. Leak
    surface is bounded to "resolved binary path + writable bool +
    release profile" — no secrets / actor identity / PG creds exposed.

    Leak surface note (E2 R1 review MEDIUM-2 — 2026-05-04): the response
    data intentionally includes the resolved binary absolute path so
    monitoring infra can correlate ``binary_missing`` with the exact
    expected location. The sibling ``/health/signature`` endpoint returns
    only module status (no path). This richer body MUST stay scoped to
    logged-in actors (current ``Depends(base.current_actor)`` floor);
    any future viewer-only / unauthenticated role added to the auth
    layer needs to RE-AUDIT whether ``binary_path`` exposure is
    acceptable. When extending RBAC, treat this route as needing the
    minimum scope ``replay:read`` (not ``replay:read:any``) — viewers
    that should NOT see absolute paths must hit ``/health/signature``
    instead.

    REF-20 Sprint A R1-T3（2026-05-04）：monitoring probe，讓 operator
    在實際發起 /run 之前能先驗 Replay Lab 真正可用所需的四個基礎前置：

      1. resolve_replay_runner_bin() 回傳的 binary 真實落盤；
      2. OPENCLAW_DATA_DIR 存在且可寫；
      3. replay schema 可達（PG up + V045 + V049 deploy）；
      4. binary release profile env var（live / paper / 空）。

    Route 端 auth 刻意寬鬆（只用 Depends(base.current_actor)，**不**用
    require_scope_and_operator），讓 monitoring infra 不持有 write scope
    亦可 probe。leak surface 限縮為「resolved binary path + writable bool
    + release profile」— 不外洩 secrets / actor 身份 / PG 憑證。

    Leak surface 註記（E2 R1 review MEDIUM-2 — 2026-05-04）：回應 data
    刻意包含 resolved binary 的絕對路徑，讓 monitoring infra 能將
    ``binary_missing`` 對應到精確期望位置；姊妹端點 ``/health/signature``
    僅回模組狀態（無路徑）。此較豐 body **必須** 限縮給已登入 actor
    （現以 ``Depends(base.current_actor)`` 為底）；未來若 auth 層加
    viewer-only / 未登入角色，需重審 ``binary_path`` 是否仍可暴露。
    擴 RBAC 時請視本 route 至少需 ``replay:read``（非 ``replay:read:any``）
    scope；不應看絕對路徑的 viewer 改打 ``/health/signature``。

    Args:
        rows: list of tuples returned by ``_async_safe_pg_select`` after
            running the V045 + V049 dual-presence probe SQL (caller
            executes the SELECT; this helper only digests rows). The
            expected SQL shape is:
                ``SELECT
                     EXISTS(SELECT 1 FROM information_schema.tables
                            WHERE table_schema='replay'
                              AND table_name='run_state' LIMIT 1),
                     EXISTS(SELECT 1 FROM information_schema.tables
                            WHERE table_schema='replay'
                              AND table_name='experiments' LIMIT 1);``
            Returns 1 row of 2 booleans.
        pg_err: error string from ``_async_safe_pg_select`` (None on
            success; "pg_unavailable" / "pg_error:<ExcName>" on failure).

    Returns / 回傳:
        dict shaped per PA design (9 fields: binary_path / binary_exists
        / binary_release_profile / data_dir / data_dir_writable /
        pg_present / v045_present / v049_present / wiring_status).

    wiring_status rules / wiring_status 規則:
      - ``binary_exists=False`` → ``"binary_missing"`` (highest priority);
      - ``pg_present=False`` OR ``data_dir_writable=False`` → ``"degraded"``;
      - ``v045_present=False`` OR ``v049_present=False`` → ``"degraded"``
        (E2 R1 review LOW-2 — 2026-05-04: PG up but schema partial means
        ``/run`` will fail at the first INSERT; we cannot truthfully claim
        ``ready``);
      - all PASS → ``"ready"``.
    """
    # Step 1: resolve binary path + executable validation (no I/O on bin
    # contents). E2 R1 review HIGH-1: use _is_executable_file() so a
    # directory or non-executable file at the resolved path is correctly
    # classified as "binary missing" instead of misleadingly truthy.
    # 步驟 1：解析 binary 路徑 + 可執行驗證（不讀 bin 內容）。E2 R1 review
    # HIGH-1：用 ``_is_executable_file()`` 確保 directory 或非執行檔
    # 不會被誤判為「binary 存在」。
    binary_path = resolve_replay_runner_bin()
    binary_exists = _is_executable_file(binary_path)

    # Step 2: data_dir resolution + writability (Linux: $OPENCLAW_DATA_DIR
    # default /tmp/openclaw; Mac: $HOME/.openclaw_runtime per CLAUDE.md §六).
    # 步驟 2：data_dir 解析 + 可寫性。
    data_dir_str = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
    data_dir_path = Path(data_dir_str)
    data_dir_writable = (
        data_dir_path.exists() and os.access(data_dir_str, os.W_OK)
    )

    # Step 3: PG + V045 + V049 presence from rows + pg_err.
    # 步驟 3：PG + V045 + V049 存在性（從 rows + pg_err 取）。
    pg_present = pg_err is None
    v045_present = False
    v049_present = False
    if pg_present and rows:
        first = rows[0]
        if len(first) >= 2:
            v045_present = bool(first[0])
            v049_present = bool(first[1])

    # Step 4: aggregate wiring_status (binary_missing > degraded > ready).
    # 步驟 4：聚合 wiring_status（binary_missing > degraded > ready）。
    if not binary_exists:
        wiring_status = "binary_missing"
    elif not pg_present or not data_dir_writable:
        wiring_status = "degraded"
    elif not v045_present or not v049_present:
        # E2 R1 review LOW-2 (2026-05-04): PG reachable but replay schema
        # partial — /run will fail at the first INSERT INTO replay.run_state
        # (V045 missing) or replay.experiments (V049 missing), so we
        # cannot truthfully advertise "ready". Surface as degraded so
        # monitoring + GUI gating fail-fast.
        # E2 R1 review LOW-2（2026-05-04）：PG 可達但 replay schema 殘缺
        # （V045 / V049 任一缺）→ ``/run`` 會在第一筆 INSERT 失敗，不能
        # 誤報 ready；降級為 degraded 讓 monitoring + GUI gate 提早 fail。
        wiring_status = "degraded"
    else:
        wiring_status = "ready"

    return {
        "binary_path": str(binary_path),
        "binary_exists": binary_exists,
        "binary_release_profile": os.environ.get(
            "OPENCLAW_RELEASE_PROFILE", ""
        ).strip(),
        "data_dir": str(data_dir_path),
        "data_dir_writable": data_dir_writable,
        "pg_present": pg_present,
        "v045_present": v045_present,
        "v049_present": v049_present,
        "wiring_status": wiring_status,
    }


# ─── Module export / 模組匯出 ────────────────────────────────────────
__all__ = [
    "ADVISORY_LOCK_GLOBAL_KEY",
    "ADVISORY_LOCK_PER_ACTOR_PREFIX",
    "DEFAULT_PG_STATEMENT_TIMEOUT_MS",
    "MANIFEST_FIXTURE_FILENAME",
    "RELEASE_PROFILE_ENV_VAR",
    "RELEASE_PROFILE_LIVE",
    "SUBPROCESS_ENV_WHITELIST",
    "artifact_path_within_allowlist",
    "build_default_manifest_payload",
    "compute_replay_health_state",
    "count_active_runs_for_actor",
    "count_active_runs_global",
    "emit_replay_audit_stub",
    "is_live_release_profile",
    "replay_response_envelope",
    "resolve_artifact_allowlist_root",
    "resolve_artifact_output_dir",
    "resolve_replay_runner_bin",
    "safe_pg_select",
    "spawn_replay_runner",
    "table_present",
    "try_acquire_pg_advisory_locks",
    "v045_table_present",
    "v049_table_present",
    "v050_table_present",
    "v051_columns_present",
    "verify_replay_runner_pid",
    "write_manifest_fixture",
]
