"""REF-20 Sprint A R3 Round 6 T4-2 — spawn_replay_runner stderr capture.
REF-20 Sprint A R3 Round 6 T4-2 — spawn_replay_runner stderr 捕獲測試。

MODULE_NOTE (EN):
    T4-2 unit tests for ``replay/route_helpers.py::spawn_replay_runner``
    stderr-to-disk path:

      * subprocess early-death writes stderr to
        ``<output_dir>/replay_runner.stderr`` and returns envelope-only
        reason_code ``spawn_died_early:exit=N`` (Round 7 SEC-04 invariant).
      * Round 7 (2026-05-05) FINDING-2 fix: reason_code is decoupled from
        stderr text — diagnostic flow is server log + disk file, NOT 503
        detail JSON. ``test_spawn_stderr_excerpt_not_in_reason_code``
        locks this invariant against regression.
      * stderr file persists post-spawn for post-mortem ssh inspection.
      * stderr_path allowlist guard rejects paths outside the artifact
        tree (defense-in-depth; unlikely to fire when output_dir is
        server-side resolved).
      * ``_read_stderr_excerpt`` helper handles missing file +
        OSError gracefully (no exception leak).

MODULE_NOTE (中):
    Round 6 ``spawn_replay_runner`` stderr → disk file 補完。Round 7
    FINDING-2 fix：reason_code 從 stderr text 解耦（envelope-only）；
    診斷流走 server log + disk file，**不**走 503 detail JSON。
    ``test_spawn_stderr_excerpt_not_in_reason_code`` 鎖此不變量防回歸。

SPEC: REF-20 V3 §6 (Replay Runner Contract) + Sprint A R3 Round 6/7 task DAG.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(os.path.dirname(_test_dir))
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.route_helpers import (  # noqa: E402
    _read_stderr_excerpt,
    spawn_replay_runner,
)


def _make_fake_runner(tmp_path: Path, exit_code: int, stderr_text: str) -> Path:
    """Create a fake replay_runner shell script that exits with stderr.
    建假 replay_runner shell 腳本，輸出 stderr 後以指定 exit_code 退出。
    """
    fake = tmp_path / "fake_replay_runner"
    # POSIX sh shim — mirrors the shape of replay_runner CLI; we only need
    # it to write to stderr then exit. ``printf`` chosen over ``echo`` to
    # avoid shell-specific escaping issues; we use single-quote-safe text
    # via Python's repr quoting on the caller side.
    # POSIX sh shim — 形狀對齊 replay_runner CLI；用 printf 避免 echo 特定
    # shell 不一致；單引號 safe 由 caller repr 處理。
    safe_text = stderr_text.replace("'", "'\"'\"'")
    fake.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' '{safe_text}' >&2\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    return fake


def _make_fake_manifest(output_dir: Path) -> Path:
    """Touch a manifest file so spawn_replay_runner pre-checks pass.
    建空 manifest file 讓 spawn_replay_runner 預檢通過。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = output_dir / "manifest.json"
    manifest.write_text("{}", encoding="utf-8")
    return manifest


@pytest.fixture
def isolated_data_dir(tmp_path: Path, monkeypatch):
    """Point OPENCLAW_DATA_DIR at tmp_path so allowlist root resolves under tmp.
    OPENCLAW_DATA_DIR 指 tmp_path，allowlist 根落 tmp 下。
    """
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path))
    # Ensure Mac is treated like Linux for allowlist resolution test purposes.
    # Note: route_helpers.resolve_artifact_allowlist_root() uses sys.platform
    # check; on darwin it returns /tmp/replay_artifacts_test_only. We work
    # around by using /tmp on Mac.
    # Mac 與 Linux 的 allowlist 路徑差異由 sys.platform 處理；test 用真實值。
    yield tmp_path


# ─────────────────────────────────────────────────────────────────────
# T4-2.1: subprocess early-death writes stderr to disk
# ─────────────────────────────────────────────────────────────────────


def test_spawn_writes_stderr_to_disk_on_early_death(
    tmp_path: Path, monkeypatch, isolated_data_dir,
):
    """Fake runner exits 1 with stderr → file persists + reason includes excerpt.
    假 runner exit 1 帶 stderr → file 落 disk + reason 含摘要。
    """
    # Use Mac-aware artifact dir resolution.
    if sys.platform == "darwin":
        artifact_root = Path("/tmp/replay_artifacts_test_only")
    else:
        artifact_root = isolated_data_dir / "replay_artifacts"
    output_dir = artifact_root / "test-run-stderr-1"
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest = _make_fake_manifest(output_dir)
    fake_runner = _make_fake_runner(
        tmp_path, exit_code=1,
        stderr_text="manifest_signer_verify_failed: mode=signature_mismatch",
    )
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_runner))

    pid, err = spawn_replay_runner(
        run_id="test-run-stderr-1", manifest_id="mid-1",
        output_dir=output_dir, manifest_fixture_path=manifest,
        poll_grace_seconds=0.5,
    )
    assert pid is None
    assert err is not None
    # Round 7 (2026-05-05) FINDING-2 fix: reason_code is envelope-only
    # (``spawn_died_early:exit=N``, NO stderr text). The stderr file on
    # disk still carries the verifier reason for post-mortem.
    # Round 7 FINDING-2 fix：reason_code 為 envelope-only
    # （``spawn_died_early:exit=N``，**不含** stderr text）。stderr 文字
    # 仍寫 disk file 供 post-mortem。
    assert err == "spawn_died_early:exit=1"

    # File persists for post-mortem; verifier reason is on disk (not in
    # reason_code, per §九 SEC-04).
    # File 持久落 disk 供 post-mortem；verifier reason 在 disk（不在
    # reason_code，對齊 §九 SEC-04）。
    stderr_path = output_dir / "replay_runner.stderr"
    assert stderr_path.exists()
    content = stderr_path.read_text(encoding="utf-8")
    assert "manifest_signer_verify_failed" in content
    assert "signature_mismatch" in content


def test_spawn_stderr_excerpt_not_in_reason_code(
    tmp_path: Path, monkeypatch, isolated_data_dir,
):
    """Round 7 SEC-04 invariant: reason_code MUST NOT contain stderr text.
    Round 7 SEC-04 不變量：reason_code 必**不**含 stderr text。

    Round 6 design embedded a 256-byte stderr excerpt into ``reason_code``
    (e.g. ``spawn_died_early:exit=2:stderr=<excerpt>``); that string flows
    into ``HTTPException(503).detail`` and back to API clients, leaking
    server-side absolute paths / fingerprint hex.

    Round 7 (2026-05-05) FINDING-2 fix locks reason_code to envelope-only
    form ``spawn_died_early:exit=N`` so the public 503 detail stays free
    of server-side info. The stderr text remains on disk
    (``replay_runner.stderr``) for operator post-mortem.

    Round 6 設計把 256 byte stderr 摘要 embed 進 reason_code（例
    ``spawn_died_early:exit=2:stderr=<excerpt>``）；此字串流入
    ``HTTPException(503).detail`` 回 API client，洩 server-side absolute
    path / fingerprint hex。Round 7 FINDING-2 fix 鎖 reason_code 為
    envelope-only 形式 ``spawn_died_early:exit=N``，503 detail 不再含
    server-side info。stderr text 仍寫 disk（``replay_runner.stderr``）
    供 operator 診斷。
    """
    if sys.platform == "darwin":
        artifact_root = Path("/tmp/replay_artifacts_test_only")
    else:
        artifact_root = isolated_data_dir / "replay_artifacts"
    output_dir = artifact_root / "test-run-cap"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _make_fake_manifest(output_dir)

    # Long stderr that includes faux server path + fingerprint to verify
    # neither leaks into reason_code (this is the SEC-04 invariant test).
    # 長 stderr 包含 faux server path + fingerprint，驗任一都不洩進
    # reason_code（SEC-04 不變量測試）。
    long_stderr = (
        "manifest_signer_verify_failed: mode=signature_mismatch "
        "/srv/openclaw_runtime/replay_artifacts/run-x/manifest.json "
        "fingerprint=deadbeefcafebabe"
    ) + "X" * 4096  # > 4KB
    fake_runner = _make_fake_runner(
        tmp_path, exit_code=2, stderr_text=long_stderr,
    )
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_runner))

    pid, err = spawn_replay_runner(
        run_id="test-run-cap", manifest_id="mid-cap",
        output_dir=output_dir, manifest_fixture_path=manifest,
        poll_grace_seconds=0.5,
    )
    assert pid is None
    # Round 7 invariant: reason_code is envelope-only.
    # Round 7 不變量：reason_code envelope-only。
    assert err == "spawn_died_early:exit=2"
    # No stderr / path / fingerprint hex leaked into reason_code.
    # 無 stderr / path / fingerprint hex 洩入 reason_code。
    assert "stderr=" not in err
    assert "manifest_signer_verify_failed" not in err
    assert "/srv/" not in err
    assert "deadbeef" not in err

    # stderr file on disk DOES carry the diagnostic text (post-mortem path).
    # disk 上的 stderr file 仍含診斷文字（post-mortem 路徑）。
    stderr_path = output_dir / "replay_runner.stderr"
    assert stderr_path.exists()
    content = stderr_path.read_text(encoding="utf-8")
    assert "manifest_signer_verify_failed" in content
    assert "deadbeef" in content


def test_spawn_stderr_disk_file_2kb_cap_on_read(
    tmp_path: Path, monkeypatch, isolated_data_dir,
):
    """_read_stderr_excerpt reads at most 2KB tail from disk.
    _read_stderr_excerpt 從 disk 讀至多 2KB 尾段。
    """
    stderr_path = tmp_path / "big.stderr"
    stderr_path.write_text("Y" * (1024 * 64), encoding="utf-8")  # 64KB
    out = _read_stderr_excerpt(stderr_path, cap_bytes=2048)
    # Y * 64K and we read tail 2KB → exactly 2048 chars.
    # Y * 64K 讀尾 2KB → 正好 2048 char。
    assert len(out) == 2048
    assert out == "Y" * 2048


def test_spawn_stderr_excerpt_handles_missing_file():
    """Missing stderr file → returns sentinel string, no exception.
    缺 stderr 檔 → 回 sentinel 字串，不拋 exception。
    """
    out = _read_stderr_excerpt(Path("/nonexistent/path/x.stderr"))
    assert out == "<stderr_file_missing>"


# ─────────────────────────────────────────────────────────────────────
# T4-2.2: allowlist guard
# ─────────────────────────────────────────────────────────────────────


def test_spawn_stderr_path_outside_allowlist_blocked(
    tmp_path: Path, monkeypatch, isolated_data_dir,
):
    """output_dir outside allowlist → spawn returns stderr_path_outside_allowlist.
    output_dir 在 allowlist 外 → spawn 回 stderr_path_outside_allowlist。
    """
    # output_dir at /tmp/some_random — allowlist is
    # /tmp/replay_artifacts_test_only on Mac or $OPENCLAW_DATA_DIR/replay_artifacts
    # on Linux. Our tmp_path/foo is outside both.
    # output_dir 在 /tmp/some_random — allowlist 在 Mac 或 Linux 都不含此。
    output_dir = tmp_path / "foo_outside"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _make_fake_manifest(output_dir)
    fake_runner = _make_fake_runner(
        tmp_path, exit_code=0, stderr_text="should not run",
    )
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_runner))

    pid, err = spawn_replay_runner(
        run_id="test-outside", manifest_id="mid-outside",
        output_dir=output_dir, manifest_fixture_path=manifest,
        poll_grace_seconds=0.5,
    )
    assert pid is None
    assert err == "stderr_path_outside_allowlist"


# ─────────────────────────────────────────────────────────────────────
# T4-2.3: spawn happy path keeps stderr file open for post-mortem
# ─────────────────────────────────────────────────────────────────────


def test_spawn_alive_path_stderr_file_exists(
    tmp_path: Path, monkeypatch, isolated_data_dir,
):
    """Successful spawn keeps stderr file alive for runner to keep writing.
    成功 spawn 保留 stderr 檔給 runner 持續寫入。
    """
    if sys.platform == "darwin":
        artifact_root = Path("/tmp/replay_artifacts_test_only")
    else:
        artifact_root = isolated_data_dir / "replay_artifacts"
    output_dir = artifact_root / "test-run-alive"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _make_fake_manifest(output_dir)

    # Fake runner sleeps for 5 seconds (longer than poll_grace) so it stays
    # alive through the poll. Will be killed by test cleanup.
    # 假 runner 睡 5 秒（> poll_grace），poll 期間活著。test 結束後手動 kill。
    fake = tmp_path / "long_runner"
    fake.write_text(
        "#!/bin/sh\necho 'runner started' >&2\nsleep 5\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake))

    pid, err = spawn_replay_runner(
        run_id="test-run-alive", manifest_id="mid-alive",
        output_dir=output_dir, manifest_fixture_path=manifest,
        poll_grace_seconds=0.3,
    )
    try:
        assert pid is not None, f"spawn failed unexpectedly: {err}"
        assert err is None
        # stderr file path exists.
        # stderr file 存在。
        stderr_path = output_dir / "replay_runner.stderr"
        assert stderr_path.exists()
    finally:
        if pid is not None:
            try:
                os.kill(pid, 9)
            except (ProcessLookupError, OSError):
                pass


# ─────────────────────────────────────────────────────────────────────
# T4-2.4: spawn fail paths surface stderr_open_error / etc.
# ─────────────────────────────────────────────────────────────────────


def test_spawn_binary_not_found(
    tmp_path: Path, monkeypatch, isolated_data_dir,
):
    """Non-existent binary path → binary_not_found (existing path).
    不存在 binary path → binary_not_found（既有 path）。
    """
    if sys.platform == "darwin":
        artifact_root = Path("/tmp/replay_artifacts_test_only")
    else:
        artifact_root = isolated_data_dir / "replay_artifacts"
    output_dir = artifact_root / "test-run-no-bin"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = _make_fake_manifest(output_dir)

    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", "/nonexistent/binary")

    pid, err = spawn_replay_runner(
        run_id="test-run-no-bin", manifest_id="mid-no-bin",
        output_dir=output_dir, manifest_fixture_path=manifest,
        poll_grace_seconds=0.1,
    )
    assert pid is None
    assert err == "binary_not_found"
