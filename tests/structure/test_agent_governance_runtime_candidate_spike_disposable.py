"""Disposable offline-evidence proof for the LR0C runtime-candidate spike (S1.4).

Real bytes, nothing mocked and NO network / NO daemon: a content-addressed fixture
tree materialized in a ``tempfile`` dir whose dependency-closure hash is computed
twice deterministically, and a genuine ``python3 -I`` subprocess that proves the
host interpreter runs in isolated mode (``sys.flags.isolated==1``,
``no_user_site==1``) and ignores an injected ``PYTHONPATH`` — with a non-isolated
control run proving the injected marker is real.  This is candidate B's
``LOCAL_REPRODUCIBLE`` evidence; the OCI candidate stays DESIGN/MECHANISM only (no
pull/build/network per the PM decision), so nothing here touches docker.

Evidence class: LOCAL_REPRODUCIBLE (a real child interpreter, a real hashed tree).
It proves the content-addressing + isolated-mode MECHANISM, not the real ML
dependency closure (LR2) or any target-host runtime seam (S1.6).  The temp dirs are
torn down in a finally; the ``python3 -I`` probe runs everywhere Python runs.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_runtime_candidate_spike as spike  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402


OBS = "2026-07-22T12:00:00+00:00"
NOW = "2026-07-22T12:05:00+00:00"


@pytest.fixture()
def bundle_dir():
    path = tempfile.mkdtemp(prefix="aiml_s14_bundle_")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# --------------------------------------------------------------------------- #
# content-addressing determinism (OFFLINE_PROVEN, real bytes)
# --------------------------------------------------------------------------- #
def test_content_addressing_hash_is_deterministic_twice(bundle_dir):
    spike.materialize_fixture_bundle(bundle_dir)
    first_hash, first_count = spike.hash_bundle_tree(bundle_dir)
    second_hash, second_count = spike.hash_bundle_tree(bundle_dir)
    assert first_hash == second_hash
    assert first_count == second_count == len(spike.FIXTURE_FILES)
    assert spike.DIGEST_RE.fullmatch(first_hash)


def test_content_addressing_changes_when_a_byte_changes(bundle_dir):
    spike.materialize_fixture_bundle(bundle_dir)
    baseline, _ = spike.hash_bundle_tree(bundle_dir)
    # 內容改一個位元組 → closure hash 必變(內容定址=身分)。
    (Path(bundle_dir) / "manifest.json").write_bytes(b'{"runtime":"content_addressed_fixed_path","x":1}\n')
    mutated, _ = spike.hash_bundle_tree(bundle_dir)
    assert mutated != baseline


def test_native_inventory_hashes_the_fixture_markers(bundle_dir):
    spike.materialize_fixture_bundle(bundle_dir)
    inventory = spike.inventory_native_libraries(bundle_dir)
    names = sorted(record["name"] for record in inventory)
    assert names == ["placeholder_lightgbm", "placeholder_onnxruntime"]
    for record in inventory:
        assert spike.DIGEST_RE.fullmatch(record["sha256"])
        assert record["origin"] == "fixture_vendored_placeholder"


# --------------------------------------------------------------------------- #
# isolated-mode / no-system-python-fallback (OFFLINE_PROVEN, real subprocess)
# --------------------------------------------------------------------------- #
def test_python_isolated_mode_subprocess_actually_ran():
    probe = spike.probe_python_isolated_mode()
    # 真跑 python3 -I 觀察到的旗標:isolated==1、no_user_site==1。
    assert probe["isolated_flag"] == 1
    assert probe["no_user_site_flag"] == 1
    # -I 忽略注入的 PYTHONPATH(marker 不在 sys.path)。
    assert probe["injected_absent_under_isolated"] is True
    # 對照組:無 -I 時同一 marker 必出現於 sys.path(證明 marker 為真、-I 才是抹除機制)。
    assert probe["injected_present_without_isolated"] is True
    assert probe["python_isolated_mode"] is True
    assert probe["ignores_ambient_env"] is True


def test_launch_interpreter_is_absolute_pinned():
    # 絕對釘住的直譯器(sys.executable),非 PATH 查找、非 /usr/bin/python3 回退。
    assert os.path.isabs(sys.executable)
    probe = spike.probe_python_isolated_mode()
    assert probe["launch_interpreter"] == "absolute_pinned"
    assert probe["system_python_fallback_possible"] is False
    # FIX(P2):absolute_pinned 綁定實際解析的絕對路徑(預設 sys.executable,已是絕對)。
    assert probe["launch_interpreter_path"] == sys.executable
    assert os.path.isabs(probe["launch_interpreter_path"])


def test_sealed_input_digest_is_reproducible_twice():
    inputs = {"manifest": b'{"runtime":"fixed"}', "lock": b"# lock", "closure": b"tree"}
    first = spike.build_sealed_input(inputs)
    second = spike.build_sealed_input(inputs)
    assert first["sealed_input_digest"] == second["sealed_input_digest"]
    assert spike.DIGEST_RE.fullmatch(first["sealed_input_digest"])


# --------------------------------------------------------------------------- #
# full candidate-B disposable receipt (real evidence end-to-end)
# --------------------------------------------------------------------------- #
def test_disposable_candidate_b_receipt_is_passing_and_reproducible(bundle_dir):
    spike.materialize_fixture_bundle(bundle_dir)
    closure_hash, count = spike.hash_bundle_tree(bundle_dir)
    inventory = spike.inventory_native_libraries(bundle_dir)
    probe = spike.probe_python_isolated_mode()
    sealed = spike.build_sealed_input({
        "closure_hash": closure_hash.encode("utf-8"),
        "requirements_lock": (Path(bundle_dir) / "requirements.lock").read_bytes(),
        "manifest": (Path(bundle_dir) / "manifest.json").read_bytes(),
    })
    receipt = spike.build_runtime_candidate_receipt(
        caller="E1:S1.4:disposable",
        platform=spike.detect_platform(),
        candidate_id=spike.CANDIDATE_FIXED_PATH,
        target_class="disposable_offline",
        dependency_closure={
            "lock_tool": "stdlib_sha256_closure",
            "lock_input_ref": "runtime_candidate_fixture_v1",
            "closure_hash": closure_hash,
            "hashed_input_count": count,
        },
        native_library_inventory=inventory,
        isolation_mode=probe,
        sealed_input=sealed,
        observation_time=OBS,
        ttl_seconds=3600,
    )
    assert receipt["status"] == "PASS"
    assert receipt["target_class"] == "disposable_offline"
    assert receipt["evidence_class"] == "LOCAL_REPRODUCIBLE"
    assert receipt["secret_scan"]["leaked"] is False
    # closure_hash 可獨立重算並綁定 receipt(可重現)。
    assert receipt["dependency_closure"]["closure_hash"] == spike.hash_bundle_tree(bundle_dir)[0]
    assert spike.validate_runtime_candidate_receipt(receipt, require_success=True, now=NOW) == []
    schema = json.loads(spike.RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema_subset_errors(receipt, schema, schema) == []
    # 五個 runtime seam 全 DEFERRED_S1_6。
    verdicts = {seam["seam_id"]: seam["verdict"] for seam in receipt["seams"]}
    for seam_id in spike.RUNTIME_ONLY_SEAMS:
        assert verdicts[seam_id] == "DEFERRED_S1_6"


def test_disposable_temp_dir_is_torn_down_without_leak():
    path = tempfile.mkdtemp(prefix="aiml_s14_leakcheck_")
    try:
        spike.materialize_fixture_bundle(path)
        assert os.path.isdir(path)
        closure_hash, _ = spike.hash_bundle_tree(path)
        assert spike.DIGEST_RE.fullmatch(closure_hash)
    finally:
        # 即使上面任一斷言失敗,teardown 仍保證執行,不留 disposable store 殘骸。
        shutil.rmtree(path, ignore_errors=True)
    # 拆除後 disposable store 不得殘留。
    assert not os.path.exists(path)
