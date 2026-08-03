"""Adversarial closure tests for current-head S2E launch issuance."""

from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
STRUCTURE = ROOT / "tests" / "structure"
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (STRUCTURE, HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import test_agent_governance_s2e_launch_receipts as support  # noqa: E402
import aiml_gate_receipt_s2e_consumption as consumption  # noqa: E402


launch = support.launch
s2e = support.s2e
validator = support.validator
LAUNCH_CONTRACT_DIGEST = support.LAUNCH_CONTRACT_DIGEST
NEXT_GENERATION_TASK_CONTRACT_DIGEST = (
    support.NEXT_GENERATION_TASK_CONTRACT_DIGEST
)
_DEFAULT_BOOTSTRAP = object()


def test_review_manifest_closes_oracle_and_offline_provider_dependencies() -> None:
    head = support._git(ROOT, "rev-parse", "HEAD")
    tree = support._git(ROOT, "rev-parse", "HEAD^{tree}")
    genesis_candidate = {
        "schema_version": "s2e_launch_genesis_receipt_v1",
        "wave": "W0-GENESIS",
        "schema_carrier_head": head,
        "schema_carrier_tree": tree,
    }
    manifest = validator.s2e_review_source_blob_manifest(
        genesis_candidate,
        repo_root=ROOT,
    )
    paths = {entry["path"] for entry in manifest}

    assert {
        ".codex/agent_registry_v1.json",
        ".codex/providers/governed_pytest_v1/lock.json",
        (
            ".codex/providers/governed_pytest_v1/wheels/"
            "pytest-9.0.3-py3-none-any.whl"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_capture.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_context_validation.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_generation_summary.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_registry.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_routing.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_schema.py"
        ),
        (
            "helper_scripts/maintenance_scripts/"
            "agent_governance_workflow_receipts.py"
        ),
        "program_code/ml_training/tests/__init__.py",
    } <= paths

    lw1_candidate = {
        "schema_version": "s2e_launch_wave_receipt_v1",
        "wave": "S2E-LW1",
        "source_head": head,
        "source_tree": tree,
    }
    lw1_manifest = validator.s2e_review_source_blob_manifest(
        lw1_candidate,
        repo_root=ROOT,
    )
    assert "program_code/ml_training/tests/__init__.py" in {
        entry["path"] for entry in lw1_manifest
    }
    # 這兩條是 review 成本護欄,不是治理不變式——source 端沒有任何地方強制 256。
    # 2026-08-03:加入 durability anchor floor 後 LW1 manifest 由 256 → 257,亦即
    # 舊界線在當時已正好卡滿,任何新增受治理檔案都會踩到。改為 288(+32 headroom)
    # 並保留上界,目的是擋住 manifest 無界成長,不是擋住單一檔案的合法新增。
    assert len(manifest) <= 288
    assert len(lw1_manifest) <= 288
    genesis_argv = validator.s2e_review_test_argv(
        genesis_candidate,
        repo_root=ROOT,
    )
    lw1_argv = validator.s2e_review_test_argv(
        lw1_candidate,
        repo_root=ROOT,
    )
    assert len(genesis_argv[genesis_argv.index("-q") + 1:]) == 8
    assert len(lw1_argv[lw1_argv.index("-q") + 1:]) == 37


def _review_for_wave(
    case: dict,
    candidate: dict,
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    intent_suffix: str,
    grant_bootstrap: bool = True,
) -> tuple[dict, dict, dict, dict, dict, dict, dict, dict | None]:
    repo = case["repo"]
    capture = support._actual_capture(
        repo,
        carrier_path="lw1-current.txt",
        task_digest=candidate["generation_task_contract_digest"],
        context_digest="sha256:" + intent_suffix[0] * 64,
        monkeypatch=monkeypatch,
        argv=validator.s2e_review_test_argv(candidate, repo_root=repo),
    )
    chain = validator.build_s2e_disposable_test_effect_chain(
        capture,
        candidate=candidate,
        repo_root=repo,
        observed_at=capture["completed_at"],
    )
    issued_at = case["now"]
    manifest = validator.s2e_review_source_blob_manifest(
        candidate, repo_root=repo
    )
    bundle = {
        "schema_version": "s2e_launch_acceptance_review_bundle_v1",
        "candidate_payload_digest": candidate["payload_digest"],
        "launch_id": candidate["launch_id"],
        "wave": candidate["wave"],
        "wave_exit_id": candidate["wave_exit_id"],
        "reviewed_source_head": candidate["source_head"],
        "reviewed_source_tree": candidate["source_tree"],
        "generation_task_contract_digest": candidate[
            "generation_task_contract_digest"
        ],
        "source_blob_manifest": manifest,
        "predicate_results": validator.s2e_review_predicate_results(
            candidate,
            source_blob_manifest=manifest,
            governed_capture_record=capture,
            disposable_test_effect_chains=[chain],
            predecessor_chain=[case["issued"]],
            repo_root=repo,
        ),
        "consumed_predecessor_digests": [],
        "disposable_test_effect_chain_digests": [chain["chain_digest"]],
        "governed_capture_identity": {
            "schema_version": "governed_capture_identity_v1",
            "record_digest": capture["record_digest"],
            "context_artifact_digest": capture["context_artifact_digest"],
            "task_contract_digest": capture["task_contract_digest"],
            "node_id": capture["node_id"],
            "role_id": capture["role_id"],
            "native_agent": capture["native_agent"],
            "permission": capture["permission"],
        },
        "governed_capture_record_digest": capture["record_digest"],
        "reviewer_identity": {
            field: capture[field]
            for field in ("node_id", "role_id", "native_agent", "permission")
        },
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat(),
        "signer": {
            "role": "S2E_SIGNER",
            "identity": s2e.S2E_RECEIPT_SIGNER_IDENTITY,
            "namespace": s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            "key_generation": "independent_off_repo_ed25519_v1",
            "anchor": "fixed_off_repo_public_trust_root_v1",
            "key_fingerprint": case["fingerprint"],
        },
        "durability_anchor_binding": None,
    }
    signed = validator.s2e_acceptance_review_signed_bytes(bundle)
    bundle["signed_core_digest"] = "sha256:" + hashlib.sha256(signed).hexdigest()
    bundle["signature"] = {
        "algorithm": "SSHSIG",
        "signed_digest": bundle["signed_core_digest"],
        "signature": support._sign_sshsig(
            case["private_key"],
            signed,
            namespace=s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
            directory=tmp_path,
        ),
    }
    # candidate 自己的 review anchor 必須嚴格晚於前一份的 carrier anchor(gen 2),
    # 且帶前手 head:committed floor 的跨 receipt 單調性在 transition 上執法。
    anchor_attestation = support._durability_anchor_attestation(
        validator.s2e_acceptance_review_worm_payload(bundle),
        trust=case["external_trust"],
        issued_at=issued_at,
        directory=tmp_path,
        generation=3,
        previous_head=case["carrier_anchor"]["anchor_head_digest"],
    )
    bundle["durability_anchor_binding"] = support._anchor_binding(
        anchor_attestation
    )
    bundle["bundle_digest"] = validator.s2e_acceptance_review_bundle_digest(
        bundle
    )
    bootstrap = None
    if grant_bootstrap:
        bootstrap_issued_at = case["now"] + timedelta(minutes=1)
        registry_request = validator.build_s2e_predecessor_registry_request(
            candidate=candidate,
            predecessor_receipt=case["issued"],
            predecessor_chain=[case["issued"]],
            acceptance_review_bundle_digest=bundle["bundle_digest"],
            consumed_at=bootstrap_issued_at,
        )
        registry_attestation = support._predecessor_registry_attestation(
            registry_request,
            trust=case["external_trust"],
            issued_at=bootstrap_issued_at,
            directory=tmp_path,
        )
        bootstrap_core = (
            validator.build_s2e_launch_consumption_bootstrap_authority_core(
                candidate=candidate,
                predecessor_receipt=case["issued"],
                predecessor_chain=[case["issued"]],
                acceptance_review_bundle_digest=bundle["bundle_digest"],
                registry_attestation=registry_attestation,
                signer=bundle["signer"],
                issued_at=bootstrap_issued_at,
                expires_at=case["now"] + timedelta(minutes=5),
            )
        )
        bootstrap_signed = (
            validator.s2e_launch_consumption_bootstrap_signed_bytes(
                bootstrap_core
            )
        )
        bootstrap = {
            **bootstrap_core,
            "signed_core_digest": (
                "sha256:" + hashlib.sha256(bootstrap_signed).hexdigest()
            ),
        }
        bootstrap["signature"] = {
            "algorithm": "SSHSIG",
            "signed_digest": bootstrap["signed_core_digest"],
            "signature": support._sign_sshsig(
                case["private_key"],
                bootstrap_signed,
                namespace=s2e.S2E_RECEIPT_SIGNATURE_NAMESPACE,
                directory=tmp_path,
            ),
        }
        bootstrap["authority_digest"] = (
            validator.s2e_launch_consumption_bootstrap_authority_digest(
                bootstrap
            )
        )
    monkeypatch.setattr(
        s2e,
        "_trusted_issuance_now",
        lambda: case["now"] + timedelta(minutes=1),
    )
    return (bundle, capture, chain, anchor_attestation, bootstrap)


def _issue_wave(
    case: dict,
    review: tuple,
    candidate: dict,
    *,
    bootstrap_authority: object = _DEFAULT_BOOTSTRAP,
) -> dict:
    bundle, capture, chain, anchor, bootstrap = review
    selected_bootstrap = (
        bootstrap
        if bootstrap_authority is _DEFAULT_BOOTSTRAP
        else bootstrap_authority
    )
    return validator.issue_s2e_launch_receipt(
        candidate,
        acceptance_review_bundle=bundle,
        repo_root=case["repo"],
        governed_capture_record=capture,
        disposable_test_effect_chains=[chain],
        durability_anchor_attestation=anchor,
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        predecessor_consumption_bootstrap_authority=selected_bootstrap,
    )


def test_typed_effect_chain_rejects_resealed_cross_link_forgery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = support._issued_genesis_authority_case(tmp_path, monkeypatch)
    candidate = s2e._pending_candidate_from_issued(case["issued"])
    capture = case["authority"]["review_governed_capture_record"]
    forged = deepcopy(
        case["authority"]["review_disposable_test_effect_chains"][0]
    )
    forged["effect_id"] = "sha256:" + "1" * 64
    for index, section in enumerate(
        ("intent", "result", "postcheck", "rollback"), start=2
    ):
        forged[section]["effect_id"] = "sha256:" + str(index) * 64
    forged["result"]["intent_digest"] = "sha256:" + "6" * 64
    forged["postcheck"]["result_digest"] = "sha256:" + "7" * 64
    forged["postcheck"]["source_head"] = "a" * 40
    forged["postcheck"]["repository_generation_before"] = (
        "sha256:" + "b" * 64
    )
    forged["postcheck"]["repository_generation_after"] = (
        "sha256:" + "c" * 64
    )
    forged["rollback"]["result_digest"] = "sha256:" + "8" * 64
    forged["rollback"]["postcheck_digest"] = "sha256:" + "9" * 64
    for section, digest_field in (
        ("intent", "intent_digest"),
        ("result", "result_digest"),
        ("postcheck", "postcheck_digest"),
        ("rollback", "rollback_digest"),
    ):
        forged[section][digest_field] = validator.canonical_digest({
            key: value
            for key, value in forged[section].items()
            if key != digest_field
        })
    forged["chain_digest"] = validator.canonical_digest({
        key: value
        for key, value in forged.items()
        if key != "chain_digest"
    })
    errors = validator.validate_s2e_disposable_test_effect_chain(
        forged,
        candidate=candidate,
        governed_capture_record=capture,
        repo_root=case["repo"],
    )
    assert any("effect_id binding differs" in error for error in errors)
    assert any("does not bind exact intent" in error for error in errors)
    assert any("does not bind result and postcheck" in error for error in errors)
    assert any("zero repository residue" in error for error in errors)


def test_historical_review_cannot_be_reissued_after_head_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = support._issued_genesis_authority_case(tmp_path, monkeypatch)
    pending = s2e._pending_candidate_from_issued(case["issued"])
    authority = case["authority"]
    result = validator.issue_s2e_launch_receipt(
        pending,
        acceptance_review_bundle=authority["acceptance_review_bundle"],
        repo_root=case["repo"],
        governed_capture_record=authority["review_governed_capture_record"],
        disposable_test_effect_chains=authority[
            "review_disposable_test_effect_chains"
        ],
        durability_anchor_attestation=authority[
            "review_durability_anchor_attestation"
        ],
    )
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any("not the clean current HEAD" in error for error in result["errors"])


def test_wave_issuance_binds_effects_and_consumes_predecessor_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = support._issued_genesis_authority_case(tmp_path, monkeypatch)
    repo = case["repo"]
    source_head = support._commit(
        repo, "lw1-current.txt", "LW1\n", "LW1 source"
    )
    candidate = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=source_head,
        schema_carrier_head=case["schema_carrier"],
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        now=case["now"],
    )
    profile = validator.s2e_review_test_argv(candidate, repo_root=repo)
    assert "tests/structure/test_agent_governance_command_capture_v2.py" in profile
    assert "tests/structure/test_agent_governance_node_permissions.py" in profile
    review = _review_for_wave(
        case,
        candidate,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        intent_suffix="a-first001",
    )
    first = _issue_wave(case, review, candidate)
    assert first["status"] == "ISSUED"
    issued = first["issued_receipt"]
    assert issued["side_effect_class"] == "DISPOSABLE_TEST"
    assert issued["disposable_effect_chain_digests"] == [
        review[2]["chain_digest"]
    ]
    assert issued["predecessor_consumption"] == first[
        "predecessor_consumption_result"
    ]["entry"]
    forged_consumption = deepcopy(issued)
    forged_consumption["predecessor_consumption"]["entry_digest"] = (
        "sha256:" + "0" * 64
    )
    forged_consumption["payload_digest"] = validator.launch_payload_digest(
        forged_consumption
    )
    assert any(
        "consumption entry digest is invalid" in error
        for error in validator.validate_s2e_launch_wave_receipt(
            forged_consumption, repo_root=repo
        )
    )
    assert first["predecessor_consumption_result"]["status"] == (
        "IDEMPOTENT_AUTHORITY_RESTORE"
    )
    assert first["predecessor_consumption_result"][
        "state_recovery_performed"
    ] is True
    assert first["predecessor_consumption_result"][
        "physical_state_write_performed"
    ] is True
    assert first["predecessor_consumption_result"][
        "mutation_performed"
    ] is False
    assert support._git(repo, "status", "--porcelain=v1") == ""
    ledger = consumption.FileS2ELaunchConsumptionStore(repo).read()
    assert consumption.validate_s2e_launch_consumption_ledger(ledger) == []
    assert len(ledger["entries"]) == 1
    no_external_floor = _issue_wave(
        case,
        review,
        candidate,
        bootstrap_authority=None,
    )
    assert no_external_floor["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "fresh signed external single-use registry authority is required"
        in error
        for error in no_external_floor["errors"]
    )

    store = consumption.FileS2ELaunchConsumptionStore(repo)
    store.state_path.unlink()
    retry = _issue_wave(case, review, candidate)
    assert retry["status"] == "ISSUED"
    assert retry["issued_receipt"]["payload_digest"] == issued["payload_digest"]
    assert retry["predecessor_consumption_result"]["status"] == (
        "IDEMPOTENT_REPLAY"
    )
    assert retry["predecessor_consumption_result"][
        "state_recovery_performed"
    ] is True
    assert store.state_path.is_file()

    moved_state = store.state_path.with_suffix(".moved")
    store.state_path.rename(moved_state)
    renamed_retry = _issue_wave(case, review, candidate)
    assert renamed_retry["status"] == "ISSUED"
    assert renamed_retry["predecessor_consumption_result"][
        "state_recovery_performed"
    ] is True
    moved_state.unlink()

    store.state_path.write_text(
        json.dumps(consumption._empty_ledger()) + "\n",
        encoding="utf-8",
    )
    store.state_path.chmod(0o600)
    reset = _issue_wave(case, review, candidate)
    assert reset["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "differs from tombstone anchor" in error
        for error in reset["errors"]
    )
    store.state_path.unlink()
    recovered_retry = _issue_wave(case, review, candidate)
    assert recovered_retry["status"] == "ISSUED"
    assert recovered_retry["predecessor_consumption_result"][
        "state_recovery_performed"
    ] is True

    moved_paths = []
    for path in (store.state_path, store.anchor_path, store.lock_path):
        moved = path.with_name(path.name + ".moved")
        path.rename(moved)
        moved_paths.append(moved)
    renamed_all = _issue_wave(
        case, review, candidate, bootstrap_authority=None
    )
    assert renamed_all["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "fresh signed external single-use registry authority is required"
        in error
        for error in renamed_all["errors"]
    )
    restored_from_authority = _issue_wave(case, review, candidate)
    assert restored_from_authority["status"] == "ISSUED"
    assert (
        restored_from_authority["issued_receipt"]["payload_digest"]
        == issued["payload_digest"]
    )
    assert restored_from_authority["predecessor_consumption_result"][
        "bootstrap_authority_applied"
    ] is True
    assert restored_from_authority["predecessor_consumption_result"][
        "status"
    ] == "IDEMPOTENT_AUTHORITY_RESTORE"
    assert restored_from_authority["predecessor_consumption_result"][
        "state_recovery_performed"
    ] is True
    assert restored_from_authority["predecessor_consumption_result"][
        "physical_state_write_performed"
    ] is True
    assert restored_from_authority["predecessor_consumption_result"][
        "mutation_performed"
    ] is False
    for moved in moved_paths:
        moved.unlink()

    sibling_head = support._commit(
        repo, "lw1-sibling.txt", "sibling\n", "LW1 sibling source"
    )
    sibling = launch.build_wave_candidate(
        repo_root=repo,
        wave="S2E-LW1",
        source_head=sibling_head,
        schema_carrier_head=case["schema_carrier"],
        predecessor_receipt=case["issued"],
        predecessor_authority=case["authority"],
        launch_contract_digest=LAUNCH_CONTRACT_DIGEST,
        generation_task_contract_digest=NEXT_GENERATION_TASK_CONTRACT_DIGEST,
        now=case["now"],
    )
    sibling_review = _review_for_wave(
        case,
        sibling,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        intent_suffix="b-second02",
        grant_bootstrap=True,
    )
    blocked = _issue_wave(case, sibling_review, sibling)
    assert blocked["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "already consumed by another successor" in error
        for error in blocked["errors"]
    )
    assert blocked["issued_receipt"] is None
    assert len(
        consumption.FileS2ELaunchConsumptionStore(repo).read()["entries"]
    ) == 1

    store.anchor_path.unlink()
    missing_anchor = _issue_wave(case, sibling_review, sibling)
    assert missing_anchor["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "tombstone anchor is missing" in error
        for error in missing_anchor["errors"]
    )
    store.state_path.unlink()
    reset_pair = _issue_wave(
        case,
        sibling_review,
        sibling,
        bootstrap_authority=None,
    )
    assert reset_pair["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "fresh signed external single-use registry authority is required"
        in error
        for error in reset_pair["errors"]
    )
    store.lock_path.unlink()
    triple_reset = _issue_wave(
        case,
        sibling_review,
        sibling,
        bootstrap_authority=None,
    )
    assert triple_reset["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "fresh signed external single-use registry authority is required"
        in error
        for error in triple_reset["errors"]
    )
    assert triple_reset["issued_receipt"] is None
    cross_candidate_authority = _issue_wave(
        case,
        sibling_review,
        sibling,
        bootstrap_authority=review[4],
    )
    assert cross_candidate_authority["status"] == (
        "EXTERNAL_VERIFICATION_PENDING"
    )
    assert any(
        "candidate_payload_digest binding differs" in error
        for error in cross_candidate_authority["errors"]
    )

    support._git(repo, "checkout", "--detach", candidate["source_head"])
    restored_after_delete = _issue_wave(case, review, candidate)
    assert restored_after_delete["status"] == "ISSUED"
    assert (
        restored_after_delete["issued_receipt"]["payload_digest"]
        == issued["payload_digest"]
    )
    assert restored_after_delete["predecessor_consumption_result"][
        "status"
    ] == "IDEMPOTENT_AUTHORITY_RESTORE"
    assert restored_after_delete["predecessor_consumption_result"][
        "physical_state_write_performed"
    ] is True
    assert restored_after_delete["predecessor_consumption_result"][
        "mutation_performed"
    ] is False
    support._git(repo, "checkout", "--detach", sibling["source_head"])
    sibling_still_blocked = _issue_wave(case, sibling_review, sibling)
    assert sibling_still_blocked["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert any(
        "already consumed by another successor" in error
        for error in sibling_still_blocked["errors"]
    )


def _one_entry_consumption_ledger() -> dict:
    entry = {
        "schema_version": (
            "s2e_launch_predecessor_consumption_entry_v1"
        ),
        "sequence": 1,
        "previous_entry_digest": None,
        "launch_id": "S2E-LW1-LW5",
        "predecessor_payload_digest": "sha256:" + "1" * 64,
        "successor_candidate_payload_digest": "sha256:" + "2" * 64,
        "successor_wave": "S2E-LW1",
        "successor_source_head": "3" * 40,
        "acceptance_review_bundle_digest": "sha256:" + "4" * 64,
        "consumed_at": "2026-07-30T12:00:00+00:00",
        "side_effect_class": "LOCAL_SOURCE_CONTROL_STATE",
        "production_effect": False,
    }
    entry["entry_digest"] = (
        consumption.s2e_launch_consumption_entry_digest(entry)
    )
    ledger = {
        "schema_version": (
            "s2e_launch_predecessor_consumption_ledger_v1"
        ),
        "launch_id": "S2E-LW1-LW5",
        "entries": [entry],
    }
    ledger["ledger_digest"] = (
        consumption.s2e_launch_consumption_ledger_digest(ledger)
    )
    return ledger


def _seed_consumption_store(
    store: consumption.FileS2ELaunchConsumptionStore,
) -> dict:
    ledger = _one_entry_consumption_ledger()
    store._atomic_write(store.anchor_path, ledger)
    store._atomic_write(store.state_path, ledger)
    store.lock_path.touch(mode=0o600)
    store.lock_path.chmod(0o600)
    return ledger


def test_consumption_store_refuses_a_symlink_state_file(tmp_path: Path) -> None:
    repo, _, _, _ = support._repo(tmp_path)
    store = consumption.FileS2ELaunchConsumptionStore(repo)
    _seed_consumption_store(store)
    store.state_path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    store.state_path.symlink_to(outside)
    with pytest.raises(OSError):
        store.read()


def test_consumption_store_refuses_a_symlink_lock_file(tmp_path: Path) -> None:
    repo, _, _, _ = support._repo(tmp_path)
    store = consumption.FileS2ELaunchConsumptionStore(repo)
    outside = tmp_path / "outside.lock"
    outside.write_text("\n", encoding="utf-8")
    store.lock_path.symlink_to(outside)
    with pytest.raises(OSError):
        store.update(lambda ledger: ledger)


def test_consumption_store_refuses_a_symlink_anchor_file(tmp_path: Path) -> None:
    repo, _, _, _ = support._repo(tmp_path)
    store = consumption.FileS2ELaunchConsumptionStore(repo)
    _seed_consumption_store(store)
    store.anchor_path.unlink()
    outside = tmp_path / "outside-anchor.json"
    outside.write_text("{}\n", encoding="utf-8")
    store.anchor_path.symlink_to(outside)
    with pytest.raises(OSError):
        store.read()


def test_consumption_store_initialization_survives_failed_mutation(
    tmp_path: Path,
) -> None:
    repo, _, _, _ = support._repo(tmp_path)
    store = consumption.FileS2ELaunchConsumptionStore(repo)

    def fail(_ledger: dict) -> dict:
        raise RuntimeError("injected mutation failure")

    with pytest.raises(RuntimeError, match="injected mutation failure"):
        store.update(
            fail,
            bootstrap_prior_ledger=consumption._empty_ledger(),
            bootstrap_result_ledger_digest=(
                _one_entry_consumption_ledger()["ledger_digest"]
            ),
        )
    assert store.lock_path.is_file()
    assert not store.state_path.exists()
    assert not store.anchor_path.exists()
    with pytest.raises(ValueError, match="state and tombstone anchor were reset"):
        store.read()
    with pytest.raises(ValueError, match="state and tombstone anchor were reset"):
        store.update(lambda ledger: ledger)


def test_consumption_store_rejects_a_persisted_valid_empty_generation(
    tmp_path: Path,
) -> None:
    repo, _, _, _ = support._repo(tmp_path)
    store = consumption.FileS2ELaunchConsumptionStore(repo)
    empty = consumption._empty_ledger()
    store._atomic_write(store.anchor_path, empty)
    store._atomic_write(store.state_path, empty)
    store.lock_path.touch(mode=0o600)
    store.lock_path.chmod(0o600)

    with pytest.raises(ValueError, match="valid-empty durable"):
        store.read()
    with pytest.raises(ValueError, match="valid-empty durable"):
        store.update(lambda ledger: ledger)


def test_consumption_store_crash_after_anchor_recovers_exact_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, _, _, _ = support._repo(tmp_path)
    store = consumption.FileS2ELaunchConsumptionStore(repo)
    expected = _one_entry_consumption_ledger()
    atomic_write = store._atomic_write
    injected = False

    def fail_first_state_write(path: Path, ledger: dict) -> None:
        nonlocal injected
        if path == store.state_path and not injected:
            injected = True
            raise OSError("injected state write failure")
        atomic_write(path, ledger)

    monkeypatch.setattr(store, "_atomic_write", fail_first_state_write)
    with pytest.raises(OSError, match="injected state write failure"):
        store.update(
            lambda _ledger: expected,
            bootstrap_prior_ledger=consumption._empty_ledger(),
            bootstrap_result_ledger_digest=expected["ledger_digest"],
        )
    assert store.anchor_path.is_file()
    assert not store.state_path.exists()

    monkeypatch.setattr(store, "_atomic_write", atomic_write)
    recovered = store.update(lambda ledger: ledger)
    assert recovered == expected
    assert store.last_state_recovery_performed is True
    assert store.read() == expected
