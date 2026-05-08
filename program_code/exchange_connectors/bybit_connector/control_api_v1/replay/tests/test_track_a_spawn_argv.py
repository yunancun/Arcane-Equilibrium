"""REF-20 Sprint 1 Track A — spawn argv schema fix tests.
REF-20 Sprint 1 Track A — spawn argv schema 修復測試。

MODULE_NOTE (EN):
    Pytest coverage for the REF-20 Sprint 1 Track A fix:

      - ``write_manifest_fixture`` writes JSON with embedded ``run_id`` and
        does not mutate caller's dict.
      - ``build_default_manifest_payload`` returns a 6-field payload that
        matches the Rust ``ReplayManifest`` struct expected schema.
      - ``spawn_replay_runner`` argv now uses ``--manifest <PATH>
        --output-dir <PATH>`` (Rust-aligned), NOT ``--manifest-id <UUID>
        --run-id <UUID>`` (Python-only schema that Rust rejected).
      - ``spawn_replay_runner`` polls 1.5s after Popen; alive → returns
        (pid, None); dead-runner (binary exits non-zero) → returns
        (None, "spawn_died_early:exit=<rc>"). This is the root cause of
        Wave 1-9 e2e replay never having actually run.
      - ``verify_replay_runner_pid`` rejects PID-reuse / unknown processes
        via psutil cmdline check.

MODULE_NOTE (中):
    REF-20 Sprint 1 Track A 修復的 pytest 覆蓋：

      - ``write_manifest_fixture`` 寫 JSON 含 embedded ``run_id`` + 不改
        caller 的 dict。
      - ``build_default_manifest_payload`` 回 6 欄位 payload 對齊 Rust
        ``ReplayManifest`` 預期 schema。
      - ``spawn_replay_runner`` argv 改用 ``--manifest <PATH> --output-dir
        <PATH>``（對齊 Rust），不再傳 Rust 拒收的 ``--manifest-id <UUID>
        --run-id <UUID>``。
      - ``spawn_replay_runner`` 在 Popen 後 poll 1.5s；alive 回 (pid, None)；
        dead-runner（binary 非 0 結束）回 (None, "spawn_died_early:
        exit=<rc>")。這正是 Wave 1-9 e2e replay 從未跑過的根因。
      - ``verify_replay_runner_pid`` 透過 psutil cmdline check 拒
        PID-reuse / 不明 process。

SPEC: REF-20 V3 §6 (Replay Runner Contract) + Sprint 1 partition Track A
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_replay_dir = os.path.dirname(_test_dir)
_control_api_dir = os.path.dirname(_replay_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay import route_helpers as _rh  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════════
# write_manifest_fixture — embedded run_id + JSON serialisation
# ═══════════════════════════════════════════════════════════════════════════════


def test_write_manifest_fixture_embeds_run_id(tmp_path: Path) -> None:
    """``write_manifest_fixture`` writes JSON with ``run_id`` field embedded.
    ``write_manifest_fixture`` 寫 JSON 含 embedded ``run_id`` 欄位。
    """
    payload = {
        "experiment_id": "exp_track_a_001",
        "data_tier": "S3",
        "fixture_uri": "/tmp/fixture.json",
        "signature": "ph_sig",
        "manifest_hash": "ph_hash",
        "signature_key_ref": "ph_ref",
    }
    out_path = _rh.write_manifest_fixture(
        run_id="run_track_a_42",
        manifest_data=payload,
        output_dir=tmp_path,
    )
    assert out_path == tmp_path / "manifest.json"
    assert out_path.exists()

    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["run_id"] == "run_track_a_42"
    assert written["experiment_id"] == "exp_track_a_001"
    assert written["data_tier"] == "S3"
    assert written["signature"] == "ph_sig"


def test_write_manifest_fixture_does_not_mutate_caller_dict(tmp_path: Path) -> None:
    """Caller's dict must not be mutated (Python deep-copy invariant).
    Caller 的 dict 不可被改（Python deep-copy 不變量）。
    """
    payload = {"experiment_id": "exp_a", "data_tier": "S3"}
    _rh.write_manifest_fixture(
        run_id="run_xyz",
        manifest_data=payload,
        output_dir=tmp_path,
    )
    assert "run_id" not in payload  # caller's dict untouched
    assert list(payload.keys()) == ["experiment_id", "data_tier"]


def test_write_manifest_fixture_rejects_empty_run_id(tmp_path: Path) -> None:
    """Empty run_id raises ValueError (fail-closed schema validation).
    空 run_id 觸發 ValueError（fail-closed schema 驗證）。
    """
    with pytest.raises(ValueError, match="run_id"):
        _rh.write_manifest_fixture(
            run_id="",
            manifest_data={"experiment_id": "x"},
            output_dir=tmp_path,
        )


def test_write_manifest_fixture_rejects_non_dict(tmp_path: Path) -> None:
    """Non-dict manifest_data raises ValueError.
    非 dict 的 manifest_data 觸發 ValueError。
    """
    with pytest.raises(ValueError, match="manifest_data"):
        _rh.write_manifest_fixture(
            run_id="run_x",
            manifest_data="not a dict",  # type: ignore[arg-type]
            output_dir=tmp_path,
        )


def test_write_manifest_fixture_creates_output_dir(tmp_path: Path) -> None:
    """output_dir is mkdir-ed if missing (parents=True).
    output_dir 不存在時 mkdir（parents=True）。
    """
    nested = tmp_path / "deeply" / "nested" / "run_id_dir"
    assert not nested.exists()
    out_path = _rh.write_manifest_fixture(
        run_id="run_nested",
        manifest_data={"experiment_id": "exp_nested"},
        output_dir=nested,
    )
    assert nested.exists()
    assert out_path.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# E2 finding F1 retrofit — byte-equal cross-language canonical contract.
# E2 finding F1 retrofit — 跨語言 canonical 契約 byte-equal。
#
# These two cases lock in the JSON serialisation invariants required for
# Rust ``manifest_signer.rs::canonical_body_for_signing`` to produce
# byte-equal bytes after envelope strip. The Rust constant is
# ``ENVELOPE_KEYS_FOR_SIGNING = ["signature", "manifest_hash",
# "signature_key_ref"]`` (see manifest_signer.rs line 574-575).
#
# Without the three kwargs (sort_keys=True / separators=(',', ':') /
# ensure_ascii=False) the disk-fixture bytes parse-then-canonicalize on
# the Python side could diverge from a future Python sign helper that
# uses the canonical kwargs, causing every HMAC verify to fail-closed
# in production once Wave 6 V042 lands.
# ═══════════════════════════════════════════════════════════════════════════════


def _python_canonical_body_for_signing(disk_bytes: bytes) -> bytes:
    """Mirror Rust ``canonical_body_for_signing``.
    鏡像 Rust ``canonical_body_for_signing``。

    Reference: srv/rust/openclaw_engine/src/replay/manifest_signer.rs
    line 574 (``ENVELOPE_KEYS_FOR_SIGNING``) + line 594 (``canonical_body_for_signing``).

    Algorithm (V3 §6.2 sorted-keys serde_json contract):
      1. parse disk bytes → dict (REJECT non-dict).
      2. drop envelope keys ``signature`` / ``manifest_hash`` / ``signature_key_ref``.
      3. ``json.dumps(stripped, sort_keys=True, separators=(',', ':'),
         ensure_ascii=False).encode('utf-8')``.

    Rust mirror produces byte-identical output via ``serde_json::to_vec``
    over a ``BTreeMap``-backed ``Value`` (alphabetical keys + compact
    separators + raw UTF-8).
    """
    obj = json.loads(disk_bytes.decode("utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("manifest body must be a JSON object")
    envelope_keys = ("signature", "manifest_hash", "signature_key_ref")
    stripped = {k: v for k, v in obj.items() if k not in envelope_keys}
    return json.dumps(
        stripped,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def test_write_manifest_fixture_byte_equal_canonical_with_non_ascii(
    tmp_path: Path,
) -> None:
    """Disk-fixture parse + envelope strip + Python canonical re-serialise
    yields byte-identical output to the canonical-form expected bytes for
    a manifest containing non-ASCII payload (e.g. strategy_name).

    含 non-ASCII 字串的 manifest，磁碟 bytes 經 envelope strip + Python
    canonical 重序列化結果與「直接 canonical 化 stripped dict」byte-equal。

    This is the E2 finding F1 invariant: ``ensure_ascii=False`` is the
    critical kwarg — Python default ``ensure_ascii=True`` would emit
    ``\\u6d4b\\u8bd5`` (escaped) on disk while a future Python sign
    helper computing canonical bytes from the in-memory dict (using
    ``ensure_ascii=False``) would produce raw UTF-8 — byte mismatch =
    HMAC verify永遠 fail。

    本測試是 E2 finding F1 不變量：``ensure_ascii=False`` 為關鍵 kwarg。
    Python 預設 True 會把 测试 escape 成 ``\\u6d4b\\u8bd5``，但未來
    Python sign helper 從 in-memory dict 計算 canonical bytes（用
    ensure_ascii=False）會產出 raw UTF-8 — byte 不等 = HMAC verify 永遠 fail。
    """
    # 含 U+6D4B U+8BD5 (测试) 的 strategy_name；分號全形 (U+FF1B) 提高難度。
    # Manifest with non-ASCII strategy_name (測試 + fullwidth semicolon).
    payload = {
        "experiment_id": "exp_byte_equal_001",
        "data_tier": "S3",
        "fixture_uri": str(tmp_path / "fixture.json"),
        "strategy_name": "测试_grid；非ASCII",
        "signature": "ph_sig_to_strip",
        "manifest_hash": "ph_hash_to_strip",
        "signature_key_ref": "ph_ref_to_strip",
    }
    out_path = _rh.write_manifest_fixture(
        run_id="run_byte_equal_001",
        manifest_data=payload,
        output_dir=tmp_path,
    )
    disk_bytes = out_path.read_bytes()

    # Sanity: disk MUST contain raw UTF-8 (NOT \uXXXX escape).
    # Sanity: 磁碟必為 raw UTF-8（**不**得 \uXXXX escape）。
    assert "测试_grid".encode("utf-8") in disk_bytes, (
        "disk bytes contain \\uXXXX escape; ensure_ascii=False contract violated"
    )
    assert b"\\u6d4b" not in disk_bytes, (
        "disk bytes contain \\u6d4b escape; ensure_ascii=False contract violated"
    )

    # Strip envelope on the disk-side path.
    # 在磁碟側剝除 envelope。
    canonical_from_disk = _python_canonical_body_for_signing(disk_bytes)

    # Manually construct expected canonical bytes from the same payload
    # source (with run_id added) sans envelope.
    # 從同一 payload 來源（加 run_id 後）構造 expected canonical bytes（不含 envelope）。
    expected_dict = {
        "experiment_id": "exp_byte_equal_001",
        "data_tier": "S3",
        "fixture_uri": str(tmp_path / "fixture.json"),
        "strategy_name": "测试_grid；非ASCII",
        "run_id": "run_byte_equal_001",
    }
    expected_canonical = json.dumps(
        expected_dict,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")

    assert canonical_from_disk == expected_canonical, (
        f"canonical drift: from_disk={canonical_from_disk!r} "
        f"expected={expected_canonical!r}"
    )

    # SHA-256 byte-equal cross-check (additional belt-and-braces).
    # SHA-256 byte-equal 雙保險。
    import hashlib
    assert (
        hashlib.sha256(canonical_from_disk).hexdigest()
        == hashlib.sha256(expected_canonical).hexdigest()
    )


def test_write_manifest_fixture_sort_keys_independent_of_input_order(
    tmp_path: Path,
) -> None:
    """Two callers passing the SAME logical manifest in DIFFERENT key
    insertion orders produce byte-equal disk bytes (sort_keys=True
    invariant — locks alphabetical canonical form).

    兩個 caller 傳遞「邏輯相同但 key 順序不同」的 manifest，磁碟 bytes
    必 byte-equal（sort_keys=True 不變量 — 鎖定 alphabetical canonical form）。

    Without sort_keys=True, Python 3.7+ preserves dict insertion order —
    different caller order = different disk bytes = different canonical
    form = HMAC verify drift.

    無 sort_keys=True 時 Python 3.7+ 保留 dict insertion order — caller 順序
    不同 = 磁碟 bytes 不同 = canonical form 不同 = HMAC verify 漂移。
    """
    # Caller A: alphabetical insertion order.
    # Caller A：alphabetical insertion order。
    payload_a = {
        "data_tier": "S3",
        "experiment_id": "exp_sort_keys",
        "fixture_uri": "/tmp/fixture.json",
        "manifest_hash": "ph_hash",
        "signature": "ph_sig",
        "signature_key_ref": "ph_ref",
    }
    # Caller B: deliberate reverse-alphabetical / chaotic order.
    # Caller B：刻意反 alphabetical / 混亂順序。
    payload_b = {
        "signature_key_ref": "ph_ref",
        "signature": "ph_sig",
        "manifest_hash": "ph_hash",
        "fixture_uri": "/tmp/fixture.json",
        "experiment_id": "exp_sort_keys",
        "data_tier": "S3",
    }
    out_a = _rh.write_manifest_fixture(
        run_id="run_sort_keys_a",
        manifest_data=payload_a,
        output_dir=tmp_path / "a",
    )
    out_b = _rh.write_manifest_fixture(
        run_id="run_sort_keys_a",  # SAME run_id so disk bytes should be identical
        manifest_data=payload_b,
        output_dir=tmp_path / "b",
    )
    disk_a = out_a.read_bytes()
    disk_b = out_b.read_bytes()
    assert disk_a == disk_b, (
        f"sort_keys invariant violated: "
        f"disk_a={disk_a!r} disk_b={disk_b!r}"
    )

    # Cross-check canonical body bytes match too (envelope strip path).
    # 雙重驗證 canonical body bytes 也對齊（envelope strip 路徑）。
    canon_a = _python_canonical_body_for_signing(disk_a)
    canon_b = _python_canonical_body_for_signing(disk_b)
    assert canon_a == canon_b


# ═══════════════════════════════════════════════════════════════════════════════
# build_default_manifest_payload — 6 minimum fields
# ═══════════════════════════════════════════════════════════════════════════════


def test_build_default_manifest_payload_has_6_minimum_fields(tmp_path: Path) -> None:
    """Default payload must have 6 fields the Rust ReplayManifest struct reads.
    預設 payload 必含 Rust ReplayManifest struct 讀的 6 個欄位。
    """
    payload = _rh.build_default_manifest_payload(
        experiment_id="exp_minimum",
        output_dir=tmp_path,
    )
    expected_keys = {
        "experiment_id",
        "data_tier",
        "fixture_uri",
        "signature",
        "manifest_hash",
        "signature_key_ref",
    }
    assert set(payload.keys()) >= expected_keys
    # NOT yet embed run_id (write_manifest_fixture's job).
    # 此處尚未 embed run_id（由 write_manifest_fixture 加）。
    assert "run_id" not in payload


def test_build_default_manifest_payload_respects_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPENCLAW_REPLAY_FIXTURE_URI env overrides default fixture_uri.
    OPENCLAW_REPLAY_FIXTURE_URI env 覆寫預設 fixture_uri。
    """
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_URI", "/custom/fixture/path.json")
    payload = _rh.build_default_manifest_payload(
        experiment_id="exp_envtest",
        output_dir=tmp_path,
    )
    assert payload["fixture_uri"] == "/custom/fixture/path.json"


# ═══════════════════════════════════════════════════════════════════════════════
# spawn_replay_runner — argv schema + spawn-then-poll
# ═══════════════════════════════════════════════════════════════════════════════


def test_spawn_replay_runner_argv_uses_manifest_path_not_uuid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """argv must contain --manifest <PATH> --output-dir <PATH>, NOT
    --manifest-id <UUID> --run-id <UUID> (REF-20 Sprint 1 Track A root cause).

    argv 必含 --manifest <PATH> --output-dir <PATH>，**不**得有
    --manifest-id <UUID> --run-id <UUID>（REF-20 Sprint 1 Track A 根因）。
    """
    # Mock binary exists.
    # mock binary 存在。
    fake_bin = tmp_path / "replay_runner"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_bin))

    # Pre-write manifest fixture so spawn passes the existence check.
    # 預寫 manifest fixture 讓 spawn 通過 existence check。
    output_dir = tmp_path / "out"
    fixture_path = _rh.write_manifest_fixture(
        run_id="run_argv_test",
        manifest_data={"experiment_id": "exp_argv"},
        output_dir=output_dir,
    )

    captured_argv: list = []

    class _FakeProc:
        pid = 999_999
        def __init__(self, argv, **kwargs):
            captured_argv.extend(argv)
        def poll(self):
            return None  # alive

    monkeypatch.setattr("replay.route_helpers.subprocess.Popen", _FakeProc)
    monkeypatch.setattr("replay.route_helpers.time.sleep", lambda s: None)

    pid, err = _rh.spawn_replay_runner(
        run_id="run_argv_test",
        manifest_id="man_uuid_dummy",
        output_dir=output_dir,
        manifest_fixture_path=fixture_path,
        poll_grace_seconds=0.0,
    )
    assert pid == 999_999
    assert err is None
    # argv shape verification.
    # argv 形狀驗證。
    assert "--manifest" in captured_argv
    assert "--output-dir" in captured_argv
    # Forbidden flags MUST NOT appear (Rust rejects them as UnknownArg).
    # 禁用 flag 必不出現（Rust 拒為 UnknownArg）。
    assert "--manifest-id" not in captured_argv
    assert "--run-id" not in captured_argv

    # Verify --manifest value is the fixture path, --output-dir the dir.
    # 驗證 --manifest 值是 fixture 路徑，--output-dir 是目錄。
    manifest_idx = captured_argv.index("--manifest")
    assert captured_argv[manifest_idx + 1] == str(fixture_path)
    output_idx = captured_argv.index("--output-dir")
    assert captured_argv[output_idx + 1] == str(output_dir)


def test_spawn_replay_runner_alive_after_poll_returns_pid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: spawn → poll alive → return (pid, None).
    Happy path：spawn → poll alive → 回 (pid, None)。
    """
    fake_bin = tmp_path / "replay_runner"
    fake_bin.write_text("#!/bin/sh\nsleep 5\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_bin))

    output_dir = tmp_path / "out"
    fixture_path = _rh.write_manifest_fixture(
        run_id="run_alive",
        manifest_data={"experiment_id": "exp_alive"},
        output_dir=output_dir,
    )

    class _FakeAliveProc:
        pid = 12345
        def __init__(self, *args, **kwargs):
            pass
        def poll(self):
            return None  # still running

    monkeypatch.setattr("replay.route_helpers.subprocess.Popen", _FakeAliveProc)
    monkeypatch.setattr("replay.route_helpers.time.sleep", lambda s: None)

    pid, err = _rh.spawn_replay_runner(
        run_id="run_alive",
        manifest_id="man_id",
        output_dir=output_dir,
        manifest_fixture_path=fixture_path,
        poll_grace_seconds=0.1,
    )
    assert pid == 12345
    assert err is None


def test_spawn_replay_runner_dead_after_poll_returns_failed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dead-runner path: spawn → poll exits non-zero → (None, spawn_died_early:exit=N).
    Dead-runner 路徑：spawn → poll 非 0 → (None, spawn_died_early:exit=N)。

    This is the exact REF-20 Sprint 1 Track A root cause: Rust binary
    rejected --manifest-id flag as CliError::UnknownArg, exited non-zero,
    Python never polled and trusted Popen → V045 stuck at 'running'.

    這正是 REF-20 Sprint 1 Track A 根因：Rust binary 拒 --manifest-id flag
    為 CliError::UnknownArg，非 0 結束，Python 不 poll 信任 Popen → V045
    卡 'running'。
    """
    fake_bin = tmp_path / "replay_runner"
    fake_bin.write_text("#!/bin/sh\nexit 2\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_bin))

    output_dir = tmp_path / "out"
    fixture_path = _rh.write_manifest_fixture(
        run_id="run_dead",
        manifest_data={"experiment_id": "exp_dead"},
        output_dir=output_dir,
    )

    class _FakeDeadProc:
        pid = 22222
        def __init__(self, *args, **kwargs):
            pass
        def poll(self):
            return 2  # exited with code 2 (CliError::UnknownArg style)

    monkeypatch.setattr("replay.route_helpers.subprocess.Popen", _FakeDeadProc)
    monkeypatch.setattr("replay.route_helpers.time.sleep", lambda s: None)

    pid, err = _rh.spawn_replay_runner(
        run_id="run_dead",
        manifest_id="man_id_dead",
        output_dir=output_dir,
        manifest_fixture_path=fixture_path,
        poll_grace_seconds=0.1,
    )
    assert pid is None
    assert err is not None
    assert err.startswith("spawn_died_early:exit=")
    assert "exit=2" in err


def test_spawn_replay_runner_returns_manifest_fixture_not_found_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Manifest fixture missing → fail-closed before spawn.
    Manifest fixture 缺 → spawn 前 fail-closed。
    """
    fake_bin = tmp_path / "replay_runner"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_bin))

    pid, err = _rh.spawn_replay_runner(
        run_id="run_no_fixture",
        manifest_id="man_id",
        output_dir=tmp_path / "out",
        manifest_fixture_path=tmp_path / "nonexistent_manifest.json",
        poll_grace_seconds=0.0,
    )
    assert pid is None
    assert err == "manifest_fixture_not_found"


def test_spawn_replay_runner_returns_binary_not_found_when_bin_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Binary missing → fail-closed before any other check.
    Binary 缺 → 其他 check 前 fail-closed。
    """
    monkeypatch.setenv(
        "OPENCLAW_REPLAY_RUNNER_BIN",
        str(tmp_path / "definitely_does_not_exist"),
    )
    output_dir = tmp_path / "out"
    fixture_path = _rh.write_manifest_fixture(
        run_id="run_no_bin",
        manifest_data={"experiment_id": "x"},
        output_dir=output_dir,
    )
    pid, err = _rh.spawn_replay_runner(
        run_id="run_no_bin",
        manifest_id="man_id",
        output_dir=output_dir,
        manifest_fixture_path=fixture_path,
        poll_grace_seconds=0.0,
    )
    assert pid is None
    assert err == "binary_not_found"


# ═══════════════════════════════════════════════════════════════════════════════
# verify_replay_runner_pid — psutil-based identity check
# ═══════════════════════════════════════════════════════════════════════════════


def test_verify_replay_runner_pid_accepts_replay_runner_cmdline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psutil cmdline contains 'replay_runner' → True.
    psutil cmdline 含 'replay_runner' → True。
    """
    fake_proc = MagicMock()
    fake_proc.cmdline.return_value = [
        "/path/to/replay_runner", "--manifest", "/x/m.json", "--output-dir", "/x/out",
    ]
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = fake_proc
    fake_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    ok, err = _rh.verify_replay_runner_pid(12345)
    assert ok is True
    assert err is None


def test_verify_replay_runner_pid_accepts_matching_start_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """cmdline + V067 subprocess_started_at_ms match → True."""
    fake_proc = MagicMock()
    fake_proc.cmdline.return_value = ["/path/to/replay_runner"]
    fake_proc.create_time.return_value = 1717000000.123
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = fake_proc
    fake_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    ok, err = _rh.verify_replay_runner_pid(
        12345, expected_started_at_ms=1717000000123
    )
    assert ok is True
    assert err is None


def test_verify_replay_runner_pid_rejects_reused_replay_runner_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """same cmdline but different create_time → PID reuse fail-closed."""
    fake_proc = MagicMock()
    fake_proc.cmdline.return_value = ["/path/to/replay_runner"]
    fake_proc.create_time.return_value = 1717000999.000
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = fake_proc
    fake_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    ok, err = _rh.verify_replay_runner_pid(
        12345, expected_started_at_ms=1717000000123
    )
    assert ok is False
    assert err is not None
    assert err.startswith("pid_start_time_mismatch:")


def test_verify_replay_runner_pid_rejects_unrelated_cmdline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psutil cmdline lacks 'replay_runner' → identity_mismatch.
    psutil cmdline 不含 'replay_runner' → identity_mismatch。
    """
    fake_proc = MagicMock()
    fake_proc.cmdline.return_value = ["/usr/bin/python3", "manage.py", "runserver"]
    fake_psutil = MagicMock()
    fake_psutil.Process.return_value = fake_proc
    fake_psutil.NoSuchProcess = type("NoSuchProcess", (Exception,), {})
    fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    ok, err = _rh.verify_replay_runner_pid(99999)
    assert ok is False
    assert err is not None
    assert err.startswith("pid_identity_mismatch:got=")


def test_verify_replay_runner_pid_handles_no_such_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psutil.NoSuchProcess → pid_not_found (PID died / never existed).
    psutil.NoSuchProcess → pid_not_found（PID 死 / 從未存在）。
    """
    class _NoSuch(Exception):
        pass
    fake_psutil = MagicMock()
    fake_psutil.Process.side_effect = _NoSuch()
    fake_psutil.NoSuchProcess = _NoSuch
    fake_psutil.AccessDenied = type("AccessDenied", (Exception,), {})

    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)
    ok, err = _rh.verify_replay_runner_pid(12345)
    assert ok is False
    assert err == "pid_not_found"


def test_verify_replay_runner_pid_handles_psutil_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """psutil ImportError → fail-closed with psutil_unavailable.
    psutil ImportError → fail-closed 回 psutil_unavailable。
    """
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _bad_import(name: str, *args, **kwargs):
        if name == "psutil":
            raise ImportError("simulated psutil missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "psutil", raising=False)
    monkeypatch.setattr("builtins.__import__", _bad_import)
    ok, err = _rh.verify_replay_runner_pid(1)
    assert ok is False
    assert err == "psutil_unavailable"


# ═══════════════════════════════════════════════════════════════════════════════
# Module export sanity
# ═══════════════════════════════════════════════════════════════════════════════


def test_track_a_helpers_exported() -> None:
    """Track A helpers must be in __all__.
    Track A helpers 必在 __all__ 中。
    """
    expected = {
        "build_default_manifest_payload",
        "spawn_replay_runner",
        "verify_replay_runner_pid",
        "write_manifest_fixture",
        "MANIFEST_FIXTURE_FILENAME",
    }
    actual = set(_rh.__all__)
    missing = expected - actual
    assert not missing, f"missing exports: {missing}"
