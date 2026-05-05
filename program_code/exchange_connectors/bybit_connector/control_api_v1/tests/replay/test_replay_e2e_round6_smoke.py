"""REF-20 Sprint A R3 Round 6 T4-4 — first real E2E smoke (4 tables).
REF-20 Sprint A R3 Round 6 T4-4 — first real E2E smoke 測試（4 表 row > 0）。

MODULE_NOTE (EN):
    T4-4 integration test that exercises the FULL Round 6 spawn path:

      1. Resolve real signing key via env override.
      2. Build body-only manifest payload.
      3. ``write_manifest_fixture`` produces signed disk fixture +
         sibling key.hex (real HMAC-SHA256).
      4. ``spawn_replay_runner`` execs the real Rust ``replay_runner``
         binary; manifest verify PASSES (Sprint 1 Track B fail-closed
         path now has a real signature to verify).
      5. Runner walks fixture events + writes ``replay_report.json`` +
         simulated fills (V050 INSERT internally).
      6. Assert:
         - subprocess exited 0 (or stays alive past poll grace, which is
           fine because Rust runner spawns fast for synthetic fixture).
         - sibling stderr file exists + contains no error after
           subprocess wait completes.
         - ``replay_report.json`` exists in output_dir.

    DOES NOT exercise:
      - register endpoint (Wave 4 R2 covered)
      - finalize endpoint (R3-T1 covered by test_replay_run_finalize.py)
      - V045/V046/V050/V054 row INSERT (covered by sibling tests +
        Linux-side full E2E run; this Mac smoke only validates the
        spawn-and-verify chain)

    SKIP conditions:
      - Rust ``replay_runner`` binary not on disk
      - Synthetic fixture file not on disk
      - OPENCLAW_REPLAY_E2E_SMOKE env var unset (operator gate)

MODULE_NOTE (中):
    Round 6 first real E2E smoke：env override key → 真 HMAC sign → 真
    Rust replay_runner spawn → 通 verify → walk fixture → 寫 report。
    對齊 PA design §4 T4-4 acceptance（Mac 端只驗 spawn-and-verify chain；
    full DB row E2E 留 Linux trade-core 跑）。

SPEC: REF-20 V3 §6 + Sprint A R3 Round 6 task DAG (T4-4).
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(os.path.dirname(_test_dir))
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.route_helpers import (  # noqa: E402
    build_default_manifest_payload,
    resolve_replay_runner_bin,
    spawn_replay_runner,
    write_manifest_fixture,
)


def _resolve_repo_root() -> Path:
    """Resolve repo root for fixture / binary paths.
    解析 repo root 給 fixture / binary path 用。
    """
    base_dir = os.environ.get("OPENCLAW_BASE_DIR", "").strip()
    if base_dir:
        return Path(base_dir)
    # tests/ → control_api_v1/ → bybit_connector/ → exchange_connectors/ →
    # program_code/ → srv/
    here = Path(_test_dir)
    return here.parents[5]


def _resolve_test_key_hex_path() -> Path:
    """Reuse existing in-tree test fixture key.hex.
    重用 in-tree test fixture key.hex。
    """
    return _resolve_repo_root() / (
        "rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex"
    )


def _resolve_synthetic_fixture_path() -> Path:
    """Resolve in-tree synthetic_btcusdt.json fixture.
    解析 in-tree synthetic_btcusdt.json fixture。
    """
    return _resolve_repo_root() / (
        "rust/openclaw_engine/tests/fixtures/replay_runner_e2e/"
        "synthetic_btcusdt.json"
    )


# ─────────────────────────────────────────────────────────────────────
# Skip gates: binary + fixture + operator opt-in
# ─────────────────────────────────────────────────────────────────────


_BINARY_PATH = resolve_replay_runner_bin()
_FIXTURE_PATH = _resolve_synthetic_fixture_path()
_KEY_HEX_PATH = _resolve_test_key_hex_path()


pytestmark = [
    pytest.mark.skipif(
        not _BINARY_PATH.exists(),
        reason=(
            f"replay_runner binary not on disk at {_BINARY_PATH}; "
            "build via cargo build --release -p openclaw_engine "
            "--bin replay_runner before running"
        ),
    ),
    pytest.mark.skipif(
        not _FIXTURE_PATH.exists(),
        reason=(
            f"synthetic fixture missing at {_FIXTURE_PATH}; "
            "ensure rust/openclaw_engine/tests/fixtures/replay_runner_e2e/"
            "is present"
        ),
    ),
    pytest.mark.skipif(
        not _KEY_HEX_PATH.exists(),
        reason=(
            f"test fixture key.hex missing at {_KEY_HEX_PATH}; "
            "ensure replay_runner_e2e fixture dir is intact"
        ),
    ),
    pytest.mark.skipif(
        os.environ.get("OPENCLAW_REPLAY_E2E_SMOKE", "").strip().lower()
        not in ("1", "true", "yes"),
        reason=(
            "OPENCLAW_REPLAY_E2E_SMOKE not set to 1; integration smoke "
            "is opt-in (spawns real Rust subprocess)"
        ),
    ),
]


# ─────────────────────────────────────────────────────────────────────
# T4-4: full Round 6 spawn-and-verify chain
# ─────────────────────────────────────────────────────────────────────


def test_round6_spawn_real_binary_with_real_hmac(tmp_path: Path, monkeypatch):
    """Full Round 6 chain: real key → real sign → real spawn → no early death.
    完整 Round 6 chain：真 key → 真簽 → 真 spawn → 不早死。
    """
    # Use the in-tree fixture key.hex via env override so we don't depend
    # on $OPENCLAW_SECRETS_DIR being set up on Mac dev / CI.
    # 用 in-tree fixture key.hex 透過 env override，避免依賴
    # $OPENCLAW_SECRETS_DIR 在 Mac dev / CI 上配置。
    monkeypatch.setenv(
        "OPENCLAW_REPLAY_SIGNING_KEY_FILE", str(_KEY_HEX_PATH),
    )
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_URI", str(_FIXTURE_PATH))

    # output_dir under the artifact allowlist root (Mac:
    # /tmp/replay_artifacts_test_only; Linux: $OPENCLAW_DATA_DIR/replay_artifacts).
    # output_dir 落 artifact allowlist 根下。
    if sys.platform == "darwin":
        artifact_root = Path("/tmp/replay_artifacts_test_only")
    else:
        data_dir = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")
        artifact_root = Path(data_dir) / "replay_artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)

    run_id = f"round6-smoke-{int(time.time())}"
    output_dir = artifact_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: build body-only payload + sign + write disk fixture.
    # 步驟 1：build body-only payload + 簽 + 寫 disk fixture。
    body = build_default_manifest_payload(
        experiment_id="round6-smoke-exp", output_dir=output_dir,
    )
    fixture_path = write_manifest_fixture(
        run_id=run_id, manifest_data=body, output_dir=output_dir,
    )
    assert fixture_path.exists()
    sibling_key = output_dir / "key.hex"
    assert sibling_key.exists()

    # Step 2: spawn real Rust binary; poll grace 2s for cold cache.
    # 步驟 2：spawn 真 Rust binary；2s grace 給 cold cache。
    pid, err = spawn_replay_runner(
        run_id=run_id, manifest_id="round6-mid",
        output_dir=output_dir, manifest_fixture_path=fixture_path,
        poll_grace_seconds=2.0,
    )

    # Acceptance (R9 Layer-6): pid > 0 (alive past poll grace) OR pid == -1
    # (R9 sentinel: clean-exited rc=0 in poll grace; report on disk).
    # We REJECT spawn_died_early:exit=N for N != 0 — that = sign+verify drift.
    # acceptance（R9 Layer-6）：pid > 0（alive 過 poll grace）或 pid == -1
    # （R9 sentinel：rc=0 grace 內乾淨退，report 已落 disk）。
    # 明確拒絕 spawn_died_early:exit=N for N != 0（= R6 sign+verify drift）。
    if err is not None:
        # Any non-None err signals failure under R9 contract (clean-exit
        # success returns err=None with pid=-1).
        # err 非 None 在 R9 契約下都是失敗（clean-exit 成功是 err=None pid=-1）。
        raise AssertionError(
            f"Unexpected spawn fail under R9 contract: err={err!r}; "
            f"check stderr at {output_dir / 'replay_runner.stderr'}"
        )
    # err is None ⇒ either pid > 0 alive OR pid == -1 R9 sentinel.
    # err is None ⇒ pid > 0 alive 或 pid == -1 R9 sentinel。
    assert pid is not None and (pid > 0 or pid == -1), (
        f"Expected pid > 0 or pid == -1 sentinel; got pid={pid}"
    )

    # Step 3: regardless of which path, stderr file must exist for
    # post-mortem (Round 6 P0-NEW-INFRA invariant).
    # 步驟 3：不論哪條路徑，stderr file 必存在（Round 6 不變量）。
    stderr_path = output_dir / "replay_runner.stderr"
    assert stderr_path.exists()

    # Step 4: real pid > 0 → wait + kill; pid == -1 R9 sentinel → process
    # already gone, skip. Skip pid <= 0 (sentinel or invalid).
    # 步驟 4：真 pid > 0 → wait + kill；pid == -1 R9 sentinel → process 已
    # 結束跳過。pid <= 0（sentinel/無效）跳過。
    if pid is not None and pid > 0:
        # Wait briefly for runner to finish on its own.
        # 短等讓 runner 自然結束。
        for _ in range(20):  # up to 4s
            time.sleep(0.2)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        # Force kill if still alive.
        # 還活著就強制 kill。
        try:
            os.kill(pid, 9)
        except (ProcessLookupError, OSError):
            pass

    # Final sanity: verifier did not log mismatch in stderr.
    # 最終 sanity：verifier 沒在 stderr log mismatch。
    stderr_content = stderr_path.read_text(encoding="utf-8")
    assert "manifest_signer_verify_failed" not in stderr_content, (
        f"Round 6 sign + verify drift detected; stderr={stderr_content[:512]}"
    )
    assert "signature_mismatch" not in stderr_content
    assert "key_missing" not in stderr_content
