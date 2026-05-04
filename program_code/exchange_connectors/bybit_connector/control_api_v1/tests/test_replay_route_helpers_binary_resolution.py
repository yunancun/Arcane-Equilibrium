"""REF-20 Sprint A R1-T5 unit tests for resolve_replay_runner_bin().
REF-20 Sprint A R1-T5：resolve_replay_runner_bin() 單元測試。

MODULE_NOTE (EN):
    Sprint A R1-T5 (2026-05-04) hermetic suite covering the 5-path
    fallback chain wired in R1-T1 (``replay/route_helpers.py
    ::resolve_replay_runner_bin``). E2 R1 review (2026-05-04) extended
    the suite with HIGH-1 + MEDIUM-3 + MEDIUM-4 regression cases:

      - directory at the candidate path must NOT be returned (HIGH-1);
      - non-executable file at the candidate path must be skipped (HIGH-1);
      - empty / whitespace-only ``OPENCLAW_REPLAY_RUNNER_BIN`` must NOT
        short-circuit; helper must fall through (MEDIUM-3);
      - legacy release vs legacy debug priority (MEDIUM-4).

    Each test isolates one branch of the chain via ``monkeypatch`` and
    ``tmp_path`` so no test relies on real on-disk binaries or repo
    layout. All seeded files set mode ``0o755`` so the new
    ``_is_executable_file()`` helper used by R1-T1 (E2 R1 review HIGH-1)
    accepts them — fixture ``Path.touch()`` defaults to ``0o644`` which
    would silently break every test post-fix without explicit chmod.

    Test cases (priority order matches helper docstring):
      1. ``OPENCLAW_REPLAY_RUNNER_BIN`` env override returns override path.
      2. Workspace ``rust/target/release`` exists → workspace release.
      3. Workspace release absent + debug exists → workspace debug.
      4. Workspace target absent + legacy nested release exists → legacy.
      5. Nothing exists → returns legacy debug path (caller surfaces 503).
      6. Empty-string env override → fall through to workspace release.
      7. Whitespace-only env override → fall through to workspace release.
      8. Legacy release + legacy debug both present → release wins.
      9. Directory at workspace release path → skipped (HIGH-1).
     10. Non-executable file at workspace release path → skipped (HIGH-1).

    All tests use ``tmp_path`` for filesystem state — never hardcode
    ``/home/ncyu`` / ``/Users/ncyu`` paths (CLAUDE.md §七 ★★ cross-platform
    rule). Each test ``monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN")``
    so a leaked env from a prior test cannot mask the workspace fallback.

MODULE_NOTE (中):
    Sprint A R1-T5（2026-05-04）封閉式測試，覆蓋 R1-T1 在
    ``replay/route_helpers.py::resolve_replay_runner_bin`` 接好的 5 path
    fallback chain。E2 R1 review（2026-05-04）擴增 HIGH-1 + MEDIUM-3 +
    MEDIUM-4 regression case：

      - candidate path 為 directory 時不可回（HIGH-1）；
      - candidate path 為非執行檔時必 skip（HIGH-1）；
      - 空 / 純空白 ``OPENCLAW_REPLAY_RUNNER_BIN`` 不可 short-circuit，
        helper 必 fall through（MEDIUM-3）；
      - legacy release vs legacy debug 順序（MEDIUM-4）。

    每個 test 用 ``monkeypatch`` + ``tmp_path`` 隔離 chain 分支，不依賴
    真實落盤 binary 或 repo 佈局。所有 seed 的檔案明確 ``chmod(0o755)``
    才能通過 R1-T1（E2 R1 review HIGH-1）新增的 ``_is_executable_file()``
    檢查 — fixture ``Path.touch()`` 預設 ``0o644``，若不顯式 chmod，修補
    後既有 test 會 silently 全 fail。

    測試案例（優先級與 helper docstring 對齊）：
      1. ``OPENCLAW_REPLAY_RUNNER_BIN`` env override 回 override 路徑。
      2. Workspace ``rust/target/release`` 存在 → 回 workspace release。
      3. Workspace release 缺 + debug 存在 → 回 workspace debug。
      4. Workspace target 缺 + legacy nested release 存在 → 回 legacy。
      5. 全空 → 回 legacy debug 路徑（caller 透過 503 surface）。
      6. 空字串 env override → fall through 到 workspace release。
      7. 純空白 env override → fall through 到 workspace release。
      8. Legacy release + legacy debug 同時存在 → release 勝出。
      9. workspace release 路徑為 directory → skip（HIGH-1）。
     10. workspace release 路徑為非執行檔 → skip（HIGH-1）。

    所有測試用 ``tmp_path`` 處理檔案系統狀態 — **不**寫死
    ``/home/ncyu`` / ``/Users/ncyu`` 字面值（CLAUDE.md §七 ★★ 跨平台規則）。
    每個 test 都 ``monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN")``，
    避免上一個 test 漏掉的 env 遮蔽 workspace fallback。

SPEC: REF-20 Gap Closure Plan V1 §6.R1 acceptance "binary resolution …
      under unit test that mocks all three layouts (workspace release /
      workspace debug / legacy nested)".
E2 R1 review report:
      docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r1_e2_review.md
Workplan: docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# ── conftest pathing pattern (mirrors test_replay_routes_*.py) ─────────
# conftest 路徑插入 pattern（與 test_replay_routes_*.py 對齊）。
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.route_helpers import (  # noqa: E402
    compute_replay_health_state,
    resolve_replay_runner_bin,
)


# ─── Helper / 輔助 ─────────────────────────────────────────────────────


def _seed_executable(path: Path) -> None:
    """Create a regular file at ``path`` with executable bit set.
    在 ``path`` 建立可執行 regular file。

    Required because R1-T1 + E2 R1 review HIGH-1 fix uses
    ``_is_executable_file(p) = p.is_file() and os.access(p, os.X_OK)``;
    the default ``Path.touch()`` mode ``0o644`` would silently fail.
    R1-T1 + E2 R1 review HIGH-1 修補使用
    ``_is_executable_file(p) = p.is_file() and os.access(p, os.X_OK)``；
    ``Path.touch()`` 預設 mode ``0o644``，未顯式 chmod 會 silently fail。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    path.chmod(0o755)


# ═══════════════════════════════════════════════════════════════════════════════
# 5-path fallback chain coverage / 5 path fallback chain 覆蓋
# ═══════════════════════════════════════════════════════════════════════════════


def test_env_override_takes_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 1: ``OPENCLAW_REPLAY_RUNNER_BIN`` env override beats every other layout.
    階段 1：``OPENCLAW_REPLAY_RUNNER_BIN`` env override 壓過所有其他佈局。

    Sets the override env var to a path that does NOT need to exist on disk
    (operator override is allowed to point at not-yet-built artifacts; caller
    surfaces missing-bin via 503). Even with workspace release also seeded
    on disk, the override must win.

    把 override env var 指向 disk 上不必存在的路徑（operator override 允許
    指向尚未 build 的 artifact，caller 透過 503 surface missing-bin）。
    即使 workspace release 同時落盤，override 仍須勝出。
    """
    override_path = tmp_path / "custom" / "replay_runner"
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(override_path))
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    # Seed workspace release too — override should still win.
    # 同時種 workspace release — override 仍須勝出。
    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    _seed_executable(workspace_release)

    result = resolve_replay_runner_bin()
    assert result == override_path, (
        f"override env should beat workspace release; got {result}"
    )


def test_workspace_release_preferred(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 2: workspace ``rust/target/release/replay_runner`` is the primary path.
    階段 2：workspace ``rust/target/release/replay_runner`` 為主路徑。

    With override env unset and workspace release on disk, helper must
    return that exact path (post 2026-04-15 cargo workspace consolidation).
    Override env explicitly cleared so a leaked test env cannot mask this.

    override env 未設且 workspace release 落盤時，helper 須回該精確路徑
    （2026-04-15 cargo workspace 合併後的真實佈局）。明確清掉 override
    env，避免 leaked env 遮蔽。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    _seed_executable(workspace_release)

    result = resolve_replay_runner_bin()
    assert result == workspace_release, (
        f"workspace release should win when on disk; got {result}"
    )


def test_workspace_debug_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 3: workspace ``rust/target/debug/replay_runner`` is the dev fallback.
    階段 3：workspace ``rust/target/debug/replay_runner`` 為 dev fallback。

    Workspace release ABSENT + workspace debug PRESENT → debug path returned.
    Used when developer ran ``cargo build`` without ``--release``.

    Workspace release **缺** + workspace debug **存在** → 回 debug 路徑。
    開發者跑 ``cargo build`` 但沒帶 ``--release`` 時走此路。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    workspace_debug = tmp_path / "rust" / "target" / "debug" / "replay_runner"
    _seed_executable(workspace_debug)

    # Sanity: workspace release path must NOT exist.
    # Sanity 檢查：workspace release 必須不存在。
    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    assert not workspace_release.exists()

    result = resolve_replay_runner_bin()
    assert result == workspace_debug, (
        f"workspace debug should be returned when release absent; got {result}"
    )


def test_legacy_release_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Step 4: legacy nested ``rust/openclaw_engine/target/release`` compat layer.
    階段 4：legacy nested ``rust/openclaw_engine/target/release`` 相容層。

    Workspace target absent + legacy nested release present → return legacy
    release. Compat path for partial rollouts that haven't migrated to the
    workspace layout.

    Workspace target 缺 + legacy nested release 存在 → 回 legacy release。
    給尚未遷移到 workspace 佈局的 partial rollout 用的相容路徑。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    legacy_release = (
        tmp_path / "rust" / "openclaw_engine" / "target" / "release" / "replay_runner"
    )
    _seed_executable(legacy_release)

    # Sanity: workspace release + workspace debug must NOT exist.
    # Sanity 檢查：workspace release + workspace debug 必須不存在。
    assert not (tmp_path / "rust" / "target" / "release" / "replay_runner").exists()
    assert not (tmp_path / "rust" / "target" / "debug" / "replay_runner").exists()

    result = resolve_replay_runner_bin()
    assert result == legacy_release, (
        f"legacy nested release should fallback when workspace absent; got {result}"
    )


def test_all_paths_absent_returns_legacy_debug_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 5: nothing exists → return legacy debug path (caller surfaces 503).
    階段 5：全空 → 回 legacy debug 路徑（caller 透過 503 surface）。

    helper docstring contract: returns Path even if binary does not exist
    on disk; caller surfaces missing-bin via 503 degraded response. The
    final fallback is the legacy debug path.

    helper docstring 契約：即便 binary 不存在於 disk 也須回 Path；caller
    透過 503 degraded response surface missing-bin。最後 fallback 是
    legacy debug 路徑。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    # No replay_runner files at any of the 4 layouts.
    # 4 個佈局都無 replay_runner 檔案。
    result = resolve_replay_runner_bin()

    expected = (
        tmp_path / "rust" / "openclaw_engine" / "target" / "debug" / "replay_runner"
    )
    assert result == expected, (
        f"all-empty fallback must be legacy debug path; got {result}"
    )
    # And explicitly: returned path must NOT exist on disk in this case.
    # 並明確驗證：此情境下回傳路徑必不存在於 disk。
    assert not result.exists(), (
        "fallback should be path-only (does not exist); caller surfaces 503"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E2 R1 review HIGH-1 + MEDIUM-3 + MEDIUM-4 regression cases
# ═══════════════════════════════════════════════════════════════════════════════


def test_empty_override_falls_through_to_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2 R1 review MEDIUM-3: empty OPENCLAW_REPLAY_RUNNER_BIN must fall through.
    E2 R1 review MEDIUM-3：空 OPENCLAW_REPLAY_RUNNER_BIN 必 fall through。

    Setting the override env var to an empty string MUST NOT short-circuit
    Step 1; helper must continue to Step 2 (workspace release). Without
    the explicit ``.strip()`` + ``if override:`` guard in the helper, an
    empty-string env var would early-return ``Path("")`` — a silent dead
    path that downstream subprocess.Popen rejects.

    若把 override env var 設為空字串，helper 不可 short-circuit Step 1；
    必繼續到 Step 2（workspace release）。helper 沒有 ``.strip()`` +
    ``if override:`` 守門就會早 return ``Path("")``，下游
    subprocess.Popen 拒絕的 silent dead path。
    """
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", "")
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    _seed_executable(workspace_release)

    result = resolve_replay_runner_bin()
    assert result == workspace_release, (
        f"empty override should fall through to workspace release; got {result}"
    )


def test_whitespace_only_override_falls_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2 R1 review MEDIUM-3: whitespace-only override treated as empty post-strip.
    E2 R1 review MEDIUM-3：純空白 override 經 strip 後視同空，fall through。

    A whitespace-only env var (``"   "``) must be normalised by the
    helper's ``.strip()`` and treated as empty so it falls through to
    Step 2 instead of resolving to ``Path("   ")`` — a leading-space
    garbage path that downstream subprocess.Popen rejects.

    純空白 env var（``"   "``）需被 helper 的 ``.strip()`` 視為空，
    fall through 到 Step 2，避免變成 ``Path("   ")`` leading-space
    garbage path 被下游 subprocess.Popen 拒絕。
    """
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", "   ")
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    _seed_executable(workspace_release)

    result = resolve_replay_runner_bin()
    assert result == workspace_release, (
        f"whitespace-only override should fall through to workspace release; got {result}"
    )


def test_legacy_release_preferred_over_legacy_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2 R1 review MEDIUM-4: legacy release wins over legacy debug when both present.
    E2 R1 review MEDIUM-4：legacy release 與 debug 並存時 release 勝出。

    Pinning Step 4 vs Step 5 ordering: if a future regression flips
    ``legacy_release`` and ``legacy_debug`` checks the silent regression
    is not caught by ``test_legacy_release_fallback`` (which only seeds
    legacy release). Seed BOTH and assert release wins.

    釘住 Step 4 vs Step 5 順序：若未來把 ``legacy_release`` 與
    ``legacy_debug`` 檢查順序顛倒，``test_legacy_release_fallback``
    （僅 seed legacy release）抓不到。同時 seed 兩者並驗 release 勝出。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    legacy_release = (
        tmp_path / "rust" / "openclaw_engine" / "target" / "release" / "replay_runner"
    )
    legacy_debug = (
        tmp_path / "rust" / "openclaw_engine" / "target" / "debug" / "replay_runner"
    )
    _seed_executable(legacy_release)
    _seed_executable(legacy_debug)

    # Sanity: workspace target paths must NOT exist (force fall-through to Step 4).
    # Sanity 檢查：workspace target 路徑必不存在（強制 fall through 到 Step 4）。
    assert not (tmp_path / "rust" / "target" / "release" / "replay_runner").exists()
    assert not (tmp_path / "rust" / "target" / "debug" / "replay_runner").exists()

    result = resolve_replay_runner_bin()
    assert result == legacy_release, (
        f"legacy release should beat legacy debug when both present; got {result}"
    )


def test_directory_at_binary_path_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2 R1 review HIGH-1: directory at workspace release path must be skipped.
    E2 R1 review HIGH-1：workspace release 路徑為 directory 必 skip。

    Attacker / mis-operation surface: if ``$OPENCLAW_BASE_DIR/rust/
    target/release/replay_runner`` is a DIRECTORY (e.g. CI / NFS / Docker
    bind-mount where operator can write to that prefix and accidentally
    or maliciously creates a directory named ``replay_runner``),
    ``Path.exists()`` returns True but ``Path.is_file()`` returns False.
    The new ``_is_executable_file()`` guard must skip it and continue
    to Step 3+ instead of returning a directory that subprocess.Popen
    cannot exec.

    攻擊者 / 誤操作 surface：若 ``$OPENCLAW_BASE_DIR/rust/target/release/
    replay_runner`` 是 directory（例 CI / NFS / Docker bind-mount 可寫
    場景下，operator 誤建或攻擊者放一個名為 ``replay_runner`` 的目錄），
    ``Path.exists()`` 回 True 但 ``Path.is_file()`` 回 False。
    ``_is_executable_file()`` 必 skip 並繼續到 Step 3+，不可回一個無法
    exec 的 directory。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    # Workspace release path is a DIRECTORY (not file).
    # workspace release 路徑是 directory（不是檔案）。
    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    workspace_release.mkdir(parents=True)

    # Seed legacy release as a real executable so the chain has somewhere
    # to land after correctly skipping the directory.
    # 種一個 legacy release 真執行檔，讓 chain 正確 skip directory 後仍有著陸點。
    legacy_release = (
        tmp_path / "rust" / "openclaw_engine" / "target" / "release" / "replay_runner"
    )
    _seed_executable(legacy_release)

    result = resolve_replay_runner_bin()
    assert result == legacy_release, (
        f"directory at workspace release must be skipped; got {result}"
    )


def test_non_executable_file_at_binary_path_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2 R1 review HIGH-1: non-executable file at workspace release must be skipped.
    E2 R1 review HIGH-1：workspace release 路徑為非執行檔必 skip。

    If the workspace release file exists but mode is ``0o644`` (e.g. a
    half-built binary, or attacker-deposited config file masquerading as
    the runner), ``Path.is_file()`` returns True but ``os.access(p,
    os.X_OK)`` returns False. The ``_is_executable_file()`` guard must
    skip and fall through to Step 3+; otherwise downstream
    subprocess.Popen raises ``PermissionError`` only at exec time —
    silent monitoring failure mode where ``/health`` advertises
    ``binary_exists=True`` but ``/run`` always fails.

    workspace release 雖存在但 mode ``0o644``（例：半 build 完的 binary
    或攻擊者放置的 config 偽裝），``Path.is_file()`` 回 True 但
    ``os.access(p, os.X_OK)`` 回 False。``_is_executable_file()`` 必 skip
    並 fall through 到 Step 3+；否則下游 subprocess.Popen 在 exec 時才
    拋 ``PermissionError`` — silent monitoring failure：``/health``
    回報 ``binary_exists=True`` 但 ``/run`` 永遠 fail。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))

    # Workspace release exists but is non-executable (mode 0o644).
    # workspace release 存在但非執行檔（mode 0o644）。
    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    workspace_release.parent.mkdir(parents=True)
    workspace_release.touch()
    workspace_release.chmod(0o644)

    # Seed legacy release as a real executable so the chain lands after
    # skipping the non-executable workspace file.
    # 種 legacy release 真執行檔，讓 chain skip 非執行檔後仍有著陸點。
    legacy_release = (
        tmp_path / "rust" / "openclaw_engine" / "target" / "release" / "replay_runner"
    )
    _seed_executable(legacy_release)

    result = resolve_replay_runner_bin()
    assert result == legacy_release, (
        f"non-executable file at workspace release must be skipped; got {result}"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# E2 R1 review LOW-2 — V045 / V049 absent → degraded
# ═══════════════════════════════════════════════════════════════════════════════


def test_health_state_degraded_when_v045_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2 R1 review LOW-2: PG up + V045 absent → wiring_status='degraded'.
    E2 R1 review LOW-2：PG up + V045 缺 → wiring_status='degraded'。

    Before LOW-2 fix, helper returned ``ready`` even when
    ``v045_present=False`` because the gate only checked binary +
    pg_present + data_dir_writable. ``/run`` would then fail at the
    first ``INSERT INTO replay.run_state`` so monitoring was lying.
    Post-fix the helper must surface ``degraded``.

    LOW-2 修補前，gate 只看 binary + pg_present + data_dir_writable，
    即使 ``v045_present=False`` 仍回 ``ready`` — ``/run`` 會在第一筆
    ``INSERT INTO replay.run_state`` 失敗，monitoring 在說謊。修補後
    helper 必標 ``degraded``。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))

    # Real on-disk binary so binary_exists=True and binary_missing branch
    # does not trigger.
    # 真實落盤 binary，避免 binary_missing 路徑誤觸發。
    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    _seed_executable(workspace_release)

    # PG up (pg_err=None) but V045 absent (False), V049 present (True).
    # PG 上線 (pg_err=None) 但 V045 缺 (False)、V049 存在 (True)。
    health = compute_replay_health_state(rows=[(False, True)], pg_err=None)
    assert health["v045_present"] is False
    assert health["v049_present"] is True
    assert health["pg_present"] is True
    assert health["binary_exists"] is True
    assert health["wiring_status"] == "degraded", (
        f"V045 absent + PG up must surface degraded; got {health['wiring_status']}"
    )


def test_health_state_degraded_when_v049_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E2 R1 review LOW-2: PG up + V049 absent → wiring_status='degraded'.
    E2 R1 review LOW-2：PG up + V049 缺 → wiring_status='degraded'。

    Symmetric to V045-absent regression. ``/run`` would fail at
    ``INSERT INTO replay.experiments`` if V049 is missing, so the helper
    must surface degraded rather than misleadingly ``ready``.

    對稱於 V045 absent 回歸。``/run`` 若 V049 缺會在
    ``INSERT INTO replay.experiments`` 失敗，helper 必須 degraded 而非
    誤報 ``ready``。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))

    # Real on-disk binary so binary_exists=True.
    # 真實落盤 binary。
    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    _seed_executable(workspace_release)

    # V045 present, V049 absent.
    # V045 在、V049 缺。
    health = compute_replay_health_state(rows=[(True, False)], pg_err=None)
    assert health["v045_present"] is True
    assert health["v049_present"] is False
    assert health["pg_present"] is True
    assert health["binary_exists"] is True
    assert health["wiring_status"] == "degraded", (
        f"V049 absent + PG up must surface degraded; got {health['wiring_status']}"
    )


def test_health_state_ready_when_all_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sanity: binary + PG + V045 + V049 + data_dir all PASS → wiring_status='ready'.
    Sanity：binary + PG + V045 + V049 + data_dir 全 PASS → wiring_status='ready'。

    Pin the positive case so a future tightening of the rules cannot
    accidentally degrade legitimate happy-path probes.
    釘住 happy-path，避免未來 rule 收緊時誤打到合法的 happy-path probe。
    """
    monkeypatch.delenv("OPENCLAW_REPLAY_RUNNER_BIN", raising=False)
    monkeypatch.setenv("OPENCLAW_BASE_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))

    workspace_release = tmp_path / "rust" / "target" / "release" / "replay_runner"
    _seed_executable(workspace_release)

    health = compute_replay_health_state(rows=[(True, True)], pg_err=None)
    assert health["wiring_status"] == "ready", (
        f"all PASS must yield ready; got {health['wiring_status']}"
    )
