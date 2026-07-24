"""Offline evidence for the LR2 sealed-build binder (S2.3) over a hermetic fixture lock.

Real bytes, nothing mocked, NO network / NO pip / NO subprocess: a small vendored
hash-pinned fixture closure (NOT the real ML closure) is parsed and digested; the
content-addressing determinism (hash twice / rename -> identical), the unpinned-``>=``
and unhashed / broken-closure negatives, the native-lib origin projection, the
isolated launch contract, the receipt round-trip + forgery, and the S1.3
identity-matrix negative-ACL bindings are all exercised deterministically offline.
"""

from __future__ import annotations

import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

import agent_governance_sealed_build as sb  # noqa: E402
import agent_governance_identity_acl_contract as s1_3  # noqa: E402


FIXTURES = ROOT / "tests/fixtures/sealed_build"
LOCK = FIXTURES / "hermetic_closure.lock"
SPEC = FIXTURES / "hermetic_closure.txt"
IDENTITY_RECEIPT_PATH = FIXTURES / "identity_acl_contract_receipt.json"
OBS = "2026-07-24T12:00:00+00:00"
NOW = "2026-07-24T12:05:00+00:00"


def _identity_binding_digest() -> str:
    receipt = json.loads(IDENTITY_RECEIPT_PATH.read_text(encoding="utf-8"))
    return receipt["self_digest"]


# --------------------------------------------------------------------------- #
# closure completeness + content-addressing determinism
# --------------------------------------------------------------------------- #
def test_fixture_closure_is_complete_and_hash_pinned():
    closure = sb.verify_lock_closure(LOCK, SPEC)
    assert closure["entries_total"] == 3
    assert closure["hashed_entries_total"] == 3
    assert closure["unpinned_count"] == 0
    assert [e["name"] for e in closure["entries"]] == ["alpha-lib", "beta-tool", "gamma-dep"]
    assert sb.DIGEST_RE.fullmatch(closure["closure_hash"])


def test_closure_hash_is_content_addressed_not_path_addressed(tmp_path):
    original = sb.verify_lock_closure(LOCK, SPEC)["closure_hash"]
    # 同一批位元組換檔名 → 同一 closure hash(content-addressed,非 path-addressed)。
    renamed_lock = tmp_path / "differently_named.lock"
    renamed_spec = tmp_path / "differently_named.txt"
    shutil.copyfile(LOCK, renamed_lock)
    shutil.copyfile(SPEC, renamed_spec)
    assert sb.verify_lock_closure(renamed_lock, renamed_spec)["closure_hash"] == original
    # 重算兩次亦相同。
    assert sb.verify_lock_closure(LOCK, SPEC)["closure_hash"] == original


def test_unpinned_requirement_is_rejected(tmp_path):
    bad = tmp_path / "unpinned.lock"
    bad.write_text(LOCK.read_text(encoding="utf-8").replace("alpha-lib==1.0.0", "alpha-lib>=1.0.0"))
    with pytest.raises(sb.LockClosureError) as exc:
        sb.verify_lock_closure(bad, SPEC)
    assert "unpinned" in str(exc.value)


def test_entry_without_hash_is_rejected(tmp_path):
    # 移除 beta-tool 的唯一 --hash 行(位於 beta-tool==2.0.0 之後、# via 之前)。
    kept: list[str] = []
    in_beta = False
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line.startswith("beta-tool=="):
            in_beta = True
            kept.append(line.rstrip(" \\"))  # 去掉續行反斜線,使其成為無 hash 的末項
            continue
        if in_beta and line.strip().startswith("--hash=sha256:"):
            continue  # 丟掉 beta-tool 的 hash 行
        if in_beta and not line.strip().startswith("--hash="):
            in_beta = False
        kept.append(line)
    bad = tmp_path / "nohash.lock"
    bad.write_text("\n".join(kept) + "\n")
    with pytest.raises(sb.LockClosureError) as exc:
        sb.verify_lock_closure(bad, SPEC)
    assert "no sha256 hash" in str(exc.value)


def test_missing_top_level_requirement_is_rejected(tmp_path):
    bad_spec = tmp_path / "spec.txt"
    bad_spec.write_text("alpha-lib>=1.0.0\nbeta-tool>=2.0.0\ndelta-absent>=9.9.9\n")
    with pytest.raises(sb.LockClosureError) as exc:
        sb.verify_lock_closure(LOCK, bad_spec)
    assert "top-level requirements missing" in str(exc.value)


def test_broken_transitive_closure_is_rejected(tmp_path):
    # gamma-dep 依賴一個 lock 中不存在的 parent → closure 不封閉。
    text = LOCK.read_text(encoding="utf-8").replace("    #   beta-tool", "    #   ghost-parent")
    bad = tmp_path / "broken.lock"
    bad.write_text(text)
    with pytest.raises(sb.LockClosureError) as exc:
        sb.verify_lock_closure(bad, SPEC)
    assert "transitive closure not closed" in str(exc.value)


def test_orphan_entry_is_rejected(tmp_path):
    # 追加一個既非 direct 亦無 via provenance 的孤兒項。
    text = (
        LOCK.read_text(encoding="utf-8")
        + "orphan-pkg==9.9.9 \\\n    --hash=sha256:" + ("a" * 64) + "\n"
    )
    bad = tmp_path / "orphan.lock"
    bad.write_text(text)
    with pytest.raises(sb.LockClosureError) as exc:
        sb.verify_lock_closure(bad, SPEC)
    assert "orphan" in str(exc.value)


# --------------------------------------------------------------------------- #
# native-lib origin + content-addressed wheel digest
# --------------------------------------------------------------------------- #
def test_native_inventory_origin_is_deterministic():
    closure = sb.verify_lock_closure(LOCK, SPEC)
    inv1 = sb.project_native_inventory(closure, native_packages={"gamma-dep"})
    inv2 = sb.project_native_inventory(closure, native_packages={"gamma-dep"})
    assert inv1 == inv2
    assert len(inv1) == 1
    record = inv1[0]
    assert record["package"] == "gamma-dep"
    assert record["version"] == "3.0.0"
    assert record["load_verified_on_target"] is False
    # wheel_sha256 = canonical digest over the package's locked hash set.
    entry = next(e for e in closure["entries"] if e["name"] == "gamma-dep")
    assert record["wheel_sha256"] == sb.canonical_digest(sorted(entry["hashes"]))


# --------------------------------------------------------------------------- #
# sealed receipt over the fixture closure: isolated launch + round-trip + forgery
# --------------------------------------------------------------------------- #
def _sealed_from_fixture():
    closure = sb.verify_lock_closure(LOCK, SPEC)
    native = sb.project_native_inventory(closure, native_packages={"gamma-dep"})
    return sb.build_sealed_build_receipt(
        caller="E1:S2.3:offline",
        platform=sb.target_platform_block(),
        lock_closure=closure,
        native_library_inventory=native,
        lock_tool="uv 0.11.26",
        lock_input_ref="hermetic_closure.lock",
        learning_runtime_choice_receipt_digest=sb.learning_runtime_choice_schema_sha256(),
        runtime_candidate_receipt_b_digest=sb.S1_4_RUNTIME_CANDIDATE_B_DIGEST,
        observation_time=OBS,
        ttl_seconds=1800,
    )


def test_fixture_sealed_receipt_isolated_launch_contract():
    receipt = _sealed_from_fixture()
    launch = receipt["launch"]
    assert launch["launch_interpreter"] == "absolute_pinned"
    assert launch["system_python_fallback_possible"] is False
    assert launch["python_isolated_mode"] is True
    assert launch["ignores_ambient_env"] is True
    assert sb.validate_sealed_build_receipt(receipt, require_success=True, now=NOW) == []


def test_fixture_sealed_receipt_content_digest_binds_the_closure():
    receipt = _sealed_from_fixture()
    assert receipt["closure_hash"] == sb.verify_lock_closure(LOCK, SPEC)["closure_hash"]
    # 篡改 closure_hash 後,runtime_content_digest 重算不符 → 被拒。
    forged = deepcopy(receipt)
    forged["closure_hash"] = "sha256:" + ("b" * 64)
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("independent re-derivation" in e for e in sb.validate_sealed_build_receipt(forged))


# --------------------------------------------------------------------------- #
# S1.3 identity-matrix negative-ACL bindings (bound via the fixture S1.3 receipt)
# --------------------------------------------------------------------------- #
def _identity_from_fixture():
    sealed = _sealed_from_fixture()
    return sb.build_expected_identity_receipt(
        caller="E1:S2.3:offline",
        platform=sb.target_platform_block(),
        sealed_build_digest=sealed["self_digest"],
        runtime_content_digest=sealed["runtime_content_digest"],
        identity_acl_contract_digest=_identity_binding_digest(),
        observation_time=OBS,
        ttl_seconds=1800,
    )


def test_fixture_expected_identity_binds_the_vendored_s1_3_receipt():
    receipt = _identity_from_fixture()
    assert receipt["identity_acl_contract_digest"] == _identity_binding_digest()
    assert sb.validate_expected_identity_receipt(receipt, require_success=True, now=NOW) == []


def test_identity_matrix_component_with_oci_socket_true_is_rejected():
    forged = deepcopy(_identity_from_fixture())
    forged["expected_component_identities"][0]["oci_socket_access"] = True
    forged["self_digest"] = sb.receipt_digest(forged)
    assert sb.validate_expected_identity_receipt(forged) != []


def test_identity_matrix_component_with_dbus_authority_true_is_rejected():
    forged = deepcopy(_identity_from_fixture())
    forged["expected_component_identities"][0]["dbus_authority"] = True
    forged["self_digest"] = sb.receipt_digest(forged)
    assert sb.validate_expected_identity_receipt(forged) != []


def test_identity_matrix_negative_count_below_ten_is_rejected():
    forged = deepcopy(_identity_from_fixture())
    forged["negative_acl_binding"]["count"] = 8
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("count must be an integer >= 10" in e for e in sb.validate_expected_identity_receipt(forged))


def test_identity_matrix_component_not_matching_s1_3_projection_is_rejected():
    forged = deepcopy(_identity_from_fixture())
    # 把 deleter 的 pg_role 改成別的 role_name(不符 S1.3 canonical 投影)。
    row = next(r for r in forged["expected_component_identities"] if r["component"] == "deleter")
    row["pg_role"] = "aiml_engine_scanner"
    forged["self_digest"] = sb.receipt_digest(forged)
    assert any("does not match the bound" in e for e in sb.validate_expected_identity_receipt(forged))


def test_over_grant_kinds_are_at_least_ten():
    # S1.3 的 over-grant 種類數是 negative_acl_binding.count 的真相來源(>=10)。
    assert len(s1_3.OVER_GRANT_KINDS) >= 10
