from __future__ import annotations

import importlib.util
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

MODULE_PATH = (
    Path(__file__).parents[2]
    / "helper_scripts/maintenance_scripts/p0b_alr_current_head_rollforward_v1.py"
)
TEST_OLD_PIN_BASE64 = (
    "ewogICJoZWFkIjogIjI3NTkwMWJhYTA5NjU2ZTg0MmYxNGIxMWU5NGMwMGY5YmZlMGMzODAiLAogICJk"
    "ZXJpdmVkX2F0X3V0YyI6ICIyMDI2LTA3LTE3VDEzOjQxOjAxWiIsCiAgIndyaXRlciI6ICJkZXJpdmVf"
    "ZXhwZWN0ZWRfc291cmNlX2hlYWQuc2giLAogICJiYXNlX2RpciI6ICIvaG9tZS9uY3l1L0J5Yml0T3Bl"
    "bkNsYXcvc3J2Igp9Cg=="
)


def configure_overlay(module, overlay, engine):
    return overlay.configure(
        engine,
        expected_head=module.TARGET_HEAD,
        old_head=module.OLD_HEAD,
        old_pin_sha256=module.OLD_PIN_SHA256,
        old_pin_base64=TEST_OLD_PIN_BASE64,
        expected_old_pin_ino=61384029,
    )


def load_module():
    spec = importlib.util.spec_from_file_location("p0b_rollforward_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.configure_runtime_generation(
        target_head="211f26c8e865757633076bc137c743f48fed80b6",
        old_head="275901baa09656e842f14b11e94c00f9bfe0c380",
        old_pin_sha256="74d3b05bc45402d762dfbdfb55844ca3fcf052850ea02d4803cee84ae5aff311",
        old_unit_sha256="526fbcd67ca109668ec7ac7586b99e6b6393e6630bb741df71f4a935a1cc7518",
    )
    return module


def runtime_authorization(module, *, phase: str, target_head: str | None = None) -> dict:
    head = target_head or module.TARGET_HEAD
    governance = {
        key: "sha256:" + format(index, "064x")
        for index, key in enumerate(sorted(
            module.GOVERNANCE_BINDING_FIELDS - {
                "compiled_route_schema", "context_artifact_schema",
                "ops_preflight_observed_at", "ops_preflight_expires_at",
                "phase_runtime_bindings_path", "authorization_path",
            }
        ), 1)
    }
    governance.update({
        "compiled_route_schema": "hybrid_execution_dag_v1",
        "context_artifact_schema": "context_artifact_v1",
        "ops_preflight_observed_at": "2026-07-17T11:50:00Z",
        "ops_preflight_expires_at": "2026-07-17T12:30:00Z",
        "phase_runtime_bindings_path": "/tmp/phase-runtime-bindings.json",
        "authorization_path": f"/tmp/{phase}-authorization.json",
    })
    claims = module.STAGE_CLAIM_FIELDS if phase == "stage" else module.CUTOVER_CLAIM_FIELDS
    authorization = {
        "schema_version": module.AUTHORIZATION_SCHEMA,
        "adapter_id": module.ADAPTER_ID,
        "phase": phase,
        "intent_id": f"p0b-{phase}-intent-0001",
        "intent_digest": "sha256:" + "1" * 64,
        "task_contract_digest": "sha256:" + "2" * 64,
        "context_artifact_digest": "sha256:" + "3" * 64,
        "governance_bindings": governance,
        "claim_bindings": {key: "sha256:" + "4" * 64 for key in claims},
        "expected_source_head": head,
        "expected_origin_main_head": head,
        "expected_old_runtime_source_head": module.OLD_HEAD,
        "expected_old_pin_digest": "sha256:" + module.OLD_PIN_SHA256,
        "expected_source_tree_digest": "sha256:" + "5" * 64,
        "expected_pin_consumer_inventory_digest": "sha256:" + "6" * 64,
        "expected_runtime_identity_digest": "sha256:" + "7" * 64,
        "target_host": "trade-core",
        "target_environment": "trade_core_alr",
        "target_user_unit": module.UNIT_NAME,
        "require_clean_tree": True,
        "require_fresh_origin_main": True,
        "phase1_effect_receipt_digest": None if phase == "stage" else "sha256:" + "8" * 64,
        "phase1_closure_digest": None if phase == "stage" else "sha256:" + "9" * 64,
        "sealed_lineage_bundle_digest": None if phase == "stage" else "sha256:" + "a" * 64,
        "private_bundle_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
        "observer_requirement": "NOT_APPLICABLE" if phase == "stage" else "REQUIRED_PASS",
        "approved_by": "PM",
        "approved_at": "2026-07-17T11:55:00Z",
        "expires_at": "2026-07-17T12:20:00Z",
        "typed_confirm": f"p0b-alr-rollforward:{phase}:trade-core:{head}:p0b-{phase}-intent-0001",
        "hard_stops": [f"hard-stop-{index}" for index in range(8)],
    }
    authorization["authorization_digest"] = module.canonical_digest(authorization)
    return authorization


def phase_runtime_bindings(module, authorization: dict) -> dict:
    phase = authorization["phase"]
    execution_tree = {"tracked_paths": {"adapter.py": "a" * 64}}
    source = {
        "source": {
            "branch": "main", "clean": True,
            "head": authorization["expected_source_head"],
            "origin_main": authorization["expected_origin_main_head"],
            "remote_origin_main": authorization["expected_origin_main_head"],
        },
        "execution_tree": execution_tree,
        "source_tree_digest": module.canonical_digest(execution_tree),
    }
    active = active_identity()
    active["ALRSourceHead"] = authorization["expected_old_runtime_source_head"]
    old_pin_sha = authorization["expected_old_pin_digest"].removeprefix("sha256:")
    service = {
        "unit_sha256": module.OLD_UNIT_SHA256,
        "pin_sha256": old_pin_sha,
        "unit_head": authorization["expected_old_runtime_source_head"],
        "pin_head": authorization["expected_old_runtime_source_head"],
        "active_identity": active,
        "unit_identity": sealed_identity(module.OLD_UNIT_SHA256, 100),
        "pin_identity": sealed_identity(old_pin_sha, 61384029),
        "unit_lock_identity": {
            "dev": 66312, "ino": 101, "uid": 1000, "gid": 1000,
            "mode": 0o600, "nlink": 1,
        },
        "cost_lock_identity": {
            "dev": 66312, "ino": 102, "uid": 1000, "gid": 1000,
            "mode": 0o600, "nlink": 1,
        },
        "alpha_lock_identity": {
            "dev": 66312, "ino": 103, "uid": 1000, "gid": 1000,
            "mode": 0o600, "nlink": 1,
        },
    }
    pin_consumers = {"cost": {"count": 1}, "alpha": {"count": 1}}
    runtime_identity = {
        "schema_version": "p0b_protected_runtime_identity_v1",
        "target_host": "trade-core", "target_user_unit": module.UNIT_NAME,
        "source_head": active["ALRSourceHead"], "invocation_id": active["InvocationID"],
        "main_pid": active["MainPID"],
        "main_pid_start_ticks": active["ProcessStartTicks"],
        "control_group": active["ControlGroup"],
        "unit_fragment_path": str(module.UNIT_PATH),
        "unit_file_sha256": module.OLD_UNIT_SHA256,
        "pin_path": str(module.PIN_PATH), "pin_sha256": old_pin_sha,
        "cost_pin_lock_path": str(module.COST_LOCK),
        "alpha_pin_lock_path": str(module.ALPHA_LOCK), "nrestarts": 0,
        "active_state": "active", "sub_state": "running",
        "observed_at": "2026-07-17T11:58:00Z",
    }
    protected_payload = {"stable": True, "pin_consumers": pin_consumers}
    protected = {
        "service_baseline": service,
        "protected": protected_payload,
        "protected_digest": module.canonical_digest(protected_payload),
        "pin_consumer_inventory": pin_consumers,
        "pin_consumer_inventory_digest": module.canonical_digest(pin_consumers),
        "runtime_identity": runtime_identity,
        "runtime_identity_digest": module.canonical_digest(runtime_identity),
    }
    inventories = {
        "live_inventory": {},
        "completion_inventory": {"completion.json": {"sha256": "1" * 64}},
        "producer_inventory": {"board.json": {"sha256": "2" * 64}},
        "ledger_inventory": ledger_pre_inventory(),
        "lane_effective_config": module.Runtime.lane_effective_config(),
    }
    for key in list(inventories):
        inventories[key.replace("inventory", "inventory_digest") if "inventory" in key else "lane_effective_config_digest"] = module.canonical_digest(inventories[key])
    intent = authorization["intent_id"]
    if phase == "stage":
        root = module.STAGING_ROOT / intent
        paths = {
            "staging_root": str(root), "cron_destination": str(root / "cron-scratch"),
            "sealed_destination": str(root / "sealed"),
            "publisher_receipt_path": str(root / "staging-publisher-result.json"),
            "private_deps_receipt_path": str(root / "private-deps-receipt.json"),
            "private_deps_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
            "phase1_receipt_path": str(module.RECEIPT_DIR / f"{intent}.phase1.json"),
            "phase1_closure_path": str(module.RECEIPT_DIR / f"{intent}.phase1.closure.json"),
        }
        lineage = {
            "p0a_completed_board_input": {"path": "/tmp/p0a-board.json", "sha256": "b" * 64},
            "private_bundle_destination_absent": {
                "destination": str(module.PRIVATE_BUNDLE_DESTINATION), "absent": True,
            },
        }
    else:
        paths = {
            "phase1_receipt_path": "/tmp/phase1.json",
            "phase1_closure_path": "/tmp/phase1-closure.json",
            "live_destination": str(module.EVIDENCE_DIR),
            "provisional_cutover_path": str(module.RECEIPT_DIR / f"{intent}.phase2.provisional.json"),
            "observer_input_path": str(module.RECEIPT_DIR / f"{intent}.phase2.observer-input.json"),
        }
        lineage = {
            "phase1_receipt": {"path": paths["phase1_receipt_path"], "sha256": "8" * 64},
            "phase1_closure": {"path": paths["phase1_closure_path"], "sha256": "9" * 64},
            "sealed_lineage_bundle": {"path": "/tmp/lineage.json", "sha256": "a" * 64},
            "completion": {"path": "/tmp/completion.json", "sha256": "1" * 64},
            "producer_board": {"path": "/tmp/board.json", "sha256": "2" * 64},
            "staged_board": {"path": "/tmp/sealed/board.json", "sha256": "3" * 64},
            "staging_publisher_receipt": {"path": "/tmp/publisher.json", "sha256": "4" * 64},
            "private_deps_receipt": {"path": "/tmp/private.json", "sha256": "5" * 64},
            "token": "6" * 32, "max_age_seconds": 3600,
            "proposed_unit_sha256": "7" * 64,
            "private_deps_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
            "private_deps_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
            "completion_inventory_digest": inventories["completion_inventory_digest"],
            "producer_inventory_digest": inventories["producer_inventory_digest"],
            "ledger_pre_inventory_digest": module.canonical_digest(ledger_pre_inventory()),
            "ledger_post_inventory_digest": inventories["ledger_inventory_digest"],
            "lane_effective_config_digest": inventories["lane_effective_config_digest"],
        }
    sections = {
        "source_attestation": source,
        "protected_runtime_baseline": protected,
        "phase_paths": paths,
        "inventories": inventories,
        "lineage": lineage,
    }
    bindings = {
        "schema_version": module.RUNTIME_BINDINGS_SCHEMA,
        "phase": phase, "intent_id": intent,
        "target_head": authorization["expected_source_head"], **sections,
        "section_claims": {
            section: {
                "claim": claim,
                "digest": module.canonical_digest(sections[section]),
            }
            for section, claim in module.RUNTIME_BINDING_SECTIONS.items()
        },
        "observed_at": "2026-07-17T11:58:00Z",
        "expires_at": "2026-07-17T12:10:00Z",
    }
    bindings["artifact_digest"] = module.canonical_digest(bindings)
    claims = authorization["claim_bindings"]
    for section, claim in module.RUNTIME_BINDING_SECTIONS.items():
        claims[claim] = module.canonical_digest(sections[section])
    claims["p0b_phase_runtime_bindings"] = bindings["artifact_digest"]
    authorization["governance_bindings"]["phase_runtime_bindings_artifact_digest"] = bindings["artifact_digest"]
    claims["p0b_target_source_attestation"] = module.canonical_digest(source)
    claims["p0b_protected_runtime_baseline"] = protected["protected_digest"]
    claims["p0b_live_inventory"] = inventories["live_inventory_digest"]
    claims["p0b_completion_inventory"] = inventories["completion_inventory_digest"]
    claims["p0b_producer_inventory"] = inventories["producer_inventory_digest"]
    authorization["expected_source_tree_digest"] = source["source_tree_digest"]
    authorization["expected_pin_consumer_inventory_digest"] = protected["pin_consumer_inventory_digest"]
    authorization["expected_runtime_identity_digest"] = protected["runtime_identity_digest"]
    if phase == "stage":
        claims["p0b_p0a_completed_board_input"] = "sha256:" + lineage["p0a_completed_board_input"]["sha256"]
        claims["p0b_private_bundle_destination_absent_attestation"] = module.canonical_digest(lineage["private_bundle_destination_absent"])
    else:
        authorization["phase1_effect_receipt_digest"] = "sha256:" + lineage["phase1_receipt"]["sha256"]
        authorization["phase1_closure_digest"] = "sha256:" + lineage["phase1_closure"]["sha256"]
        authorization["sealed_lineage_bundle_digest"] = "sha256:" + lineage["sealed_lineage_bundle"]["sha256"]
        for key, claim in {
            "phase1_receipt": "p0b_phase1_receipt",
            "phase1_closure": "p0b_phase1_closure",
            "sealed_lineage_bundle": "p0b_sealed_lineage_bundle",
            "private_deps_receipt": "p0b_private_bundle_receipt",
            "staged_board": "p0b_staged_candidate_board",
        }.items():
            claims[claim] = "sha256:" + lineage[key]["sha256"]
        claims["p0b_observer_source"] = "sha256:" + module.OBSERVER_V2_SHA256
    authorization["authorization_digest"] = module.canonical_digest({
        key: value for key, value in authorization.items() if key != "authorization_digest"
    })
    return bindings


def test_formal_runtime_authorization_accepts_arbitrary_merged_head_and_exact_contract() -> None:
    module = load_module()
    arbitrary = "d" * 40
    authorization = runtime_authorization(module, phase="stage", target_head=arbitrary)
    module.validate_runtime_authorization(
        authorization, phase="stage",
        now=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
    )
    assert authorization["expected_source_head"] == arbitrary


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("extra", "runtime_bindings_fields_invalid"),
        ("section", "runtime_bindings_section_claim_invalid"),
        ("expired", "runtime_bindings_expired_or_not_yet_valid"),
        ("ttl", "runtime_bindings_expired_or_not_yet_valid"),
        ("path", "runtime_bindings_paths_invalid"),
        ("artifact_claim", "runtime_bindings_artifact_digest_invalid"),
    ],
)
def test_phase_runtime_bindings_are_exact_fresh_and_claim_bound(mutation, reason) -> None:
    module = load_module()
    authorization = runtime_authorization(module, phase="stage")
    bindings = phase_runtime_bindings(module, authorization)
    if mutation == "extra":
        bindings["unexpected"] = True
    elif mutation == "section":
        bindings["section_claims"]["phase_paths"]["digest"] = "sha256:" + "f" * 64
        bindings["artifact_digest"] = module.canonical_digest({
            key: value for key, value in bindings.items() if key != "artifact_digest"
        })
        authorization["claim_bindings"]["p0b_phase_runtime_bindings"] = bindings["artifact_digest"]
        authorization["governance_bindings"]["phase_runtime_bindings_artifact_digest"] = bindings["artifact_digest"]
    elif mutation == "expired":
        bindings["expires_at"] = "2026-07-17T11:59:00Z"
    elif mutation == "ttl":
        bindings["expires_at"] = "2026-07-17T12:30:00Z"
    elif mutation == "path":
        bindings["phase_paths"]["sealed_destination"] = "/tmp/not-authorized"
        digest = module.canonical_digest(bindings["phase_paths"])
        bindings["section_claims"]["phase_paths"]["digest"] = digest
        authorization["claim_bindings"]["p0b_runtime_paths_binding"] = digest
        bindings["artifact_digest"] = module.canonical_digest({
            key: value for key, value in bindings.items() if key != "artifact_digest"
        })
        authorization["claim_bindings"]["p0b_phase_runtime_bindings"] = bindings["artifact_digest"]
        authorization["governance_bindings"]["phase_runtime_bindings_artifact_digest"] = bindings["artifact_digest"]
    else:
        authorization["claim_bindings"]["p0b_phase_runtime_bindings"] = "sha256:" + "f" * 64
    with pytest.raises(module.RollforwardError, match=reason):
        module.validate_phase_runtime_bindings(
            bindings, authorization,
            now=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize("phase", ["stage", "cutover"])
def test_phase_runtime_bindings_derive_internal_plan_without_external_approval(phase) -> None:
    module = load_module()
    authorization = runtime_authorization(module, phase=phase)
    bindings = phase_runtime_bindings(module, authorization)
    module.validate_runtime_authorization(
        authorization, phase=phase,
        now=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
    )
    module.validate_phase_runtime_bindings(
        bindings, authorization,
        now=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
    )
    plan = module.derive_internal_plan(authorization, bindings)
    assert plan["schema_version"] == module.INTERNAL_PLAN_SCHEMA
    assert plan["approval_id"] == authorization["intent_id"]
    assert plan["authorization_digest"] == authorization["authorization_digest"]
    assert ("staging" in plan) is (phase == "stage")
    assert ("evidence" in plan) is (phase == "cutover")


@pytest.mark.parametrize("failure", ["tamper", "delete"])
def test_cutover_reopens_receipt_closure_and_sealed_bundle_before_use(monkeypatch, failure) -> None:
    module = load_module()
    authorization = runtime_authorization(module, phase="cutover")
    bindings = phase_runtime_bindings(module, authorization)
    lineage = bindings["lineage"]
    opened = []

    def fake_read(path, *, label, expected_sha256=None):
        opened.append(label)
        if failure == "tamper" and label == "phase1_closure":
            raise module.RollforwardError("bound_artifact_hash_mismatch:phase1_closure")
        if failure == "delete" and label == "sealed_lineage_bundle":
            raise module.RollforwardError("bound_artifact_deleted")
        return {}, {"path": str(path), "sha256": expected_sha256}

    monkeypatch.setattr(module, "read_bound_json", fake_read)
    kwargs = {
        "phase1_receipt_path": Path(lineage["phase1_receipt"]["path"]),
        "phase1_receipt_sha256": lineage["phase1_receipt"]["sha256"],
    }
    if failure == "tamper":
        with pytest.raises(module.RollforwardError, match="hash_mismatch"):
            module.revalidate_cutover_lineage(bindings, **kwargs)
        assert opened == ["phase1_receipt", "phase1_closure"]
    else:
        with pytest.raises(module.RollforwardError, match="deleted"):
            module.revalidate_cutover_lineage(bindings, **kwargs)
        assert opened == ["phase1_receipt", "phase1_closure", "sealed_lineage_bundle"]


@pytest.mark.parametrize("failure", [None, "governance_path", "raw_self_hash"])
def test_main_effect_requires_exact_formal_runtime_path_and_file_self_hash(
    monkeypatch, capsys, failure
) -> None:
    module = load_module()
    auth_path = Path("/tmp/formal-stage-authorization.json")
    runtime_path = Path("/tmp/phase-runtime-bindings.json")
    runtime_raw_sha = "e" * 64
    argv = [
        "--phase1-preflight", "--authorization-json", str(auth_path),
        "--runtime-bindings-json", str(runtime_path),
        "--runtime-bindings-sha256", (
            "f" * 64 if failure == "raw_self_hash" else runtime_raw_sha
        ),
    ]
    authorization = runtime_authorization(module, phase="stage")
    authorization["governance_bindings"]["authorization_path"] = str(auth_path)
    bindings = phase_runtime_bindings(module, authorization)
    authorization["governance_bindings"]["authorized_argv_digest"] = (
        module.authorized_effect_argv_digest(argv)
    )
    if failure == "governance_path":
        authorization["governance_bindings"]["phase_runtime_bindings_path"] = (
            "/tmp/different-runtime-bindings.json"
        )
    authorization["authorization_digest"] = module.canonical_digest({
        key: value for key, value in authorization.items()
        if key != "authorization_digest"
    })

    def fake_read(path, *, label, expected_sha256=None):
        if label == "runtime_authorization":
            return authorization, {"path": str(path), "sha256": "a" * 64}
        assert label == "phase_runtime_bindings"
        if expected_sha256 != runtime_raw_sha:
            raise module.RollforwardError("bound_hash_or_identity_mismatch:phase_runtime_bindings")
        return bindings, {"path": str(path), "sha256": runtime_raw_sha}

    class EffectRuntime:
        @staticmethod
        def now():
            return datetime(2026, 7, 17, 12, tzinfo=timezone.utc)

        def __init__(self, plan):
            self.plan = plan

    class Transaction:
        def __init__(self, runtime, plan):
            self.runtime = runtime
            self.plan = plan

        def preflight(self):
            return {"status": "PHASE1_STAGING_PREFLIGHT_PASS"}

    monkeypatch.setattr(module, "read_bound_json", fake_read)
    monkeypatch.setattr(module, "Runtime", EffectRuntime)
    monkeypatch.setattr(module, "Phase1Transaction", Transaction)
    status = module.main(argv)
    payload = json.loads(capsys.readouterr().out)
    if failure is None:
        assert status == 0
        assert payload["status"] == "PHASE1_STAGING_PREFLIGHT_PASS"
    else:
        assert status == 4
        assert payload["status"] == "BLOCKED_NO_EFFECT"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("context_plan", "runtime_authorization_contract_invalid"),
        ("extra_claim", "runtime_authorization_contract_invalid"),
        ("raw_governance", "runtime_authorization_value_invalid"),
        ("digest_tamper", "runtime_authorization_digest_invalid"),
    ],
)
def test_formal_runtime_authorization_rejects_old_or_ambiguous_authority(mutation, reason) -> None:
    module = load_module()
    authorization = runtime_authorization(module, phase="cutover")
    if mutation == "context_plan":
        authorization["governance_bindings"]["context_artifact_schema"] = "context_plan_v1"
    elif mutation == "extra_claim":
        authorization["claim_bindings"]["generic_deployment_intent"] = "sha256:" + "f" * 64
    elif mutation == "raw_governance":
        authorization["claim_bindings"]["p0b_adapter_source"] = "f" * 64
    else:
        authorization["expected_source_tree_digest"] = "sha256:" + "f" * 64
    if mutation != "digest_tamper":
        projection = {key: value for key, value in authorization.items() if key != "authorization_digest"}
        authorization["authorization_digest"] = module.canonical_digest(projection)
    with pytest.raises(module.RollforwardError, match=reason):
        module.validate_runtime_authorization(
            authorization, phase="cutover",
            now=datetime(2026, 7, 17, 12, tzinfo=timezone.utc),
        )


def test_default_invocation_is_inert(capsys) -> None:
    module = load_module()
    assert module.main([]) == 4
    assert '"status":"BLOCKED_NO_EFFECT"' in capsys.readouterr().out


def test_lane_environment_is_fixed_sanitized_and_git_side_effect_free(tmp_path) -> None:
    module = load_module()
    staging = {
        "cron_destination": str(tmp_path / "cron-scratch"),
        "sealed_destination": str(tmp_path / "sealed"),
    }
    hostile = {
        "BASH_ENV": "/tmp/hostile",
        "LD_PRELOAD": "/tmp/hostile.so",
        "PYTHONPATH": "/tmp/hostile-python",
        "POSTGRES_PASSWORD": "secret",
        "OPENCLAW_UNAPPROVED": "1",
    }
    old = {key: os.environ.get(key) for key in hostile}
    try:
        os.environ.update(hostile)
        env = module.Runtime.lane_environment(staging)
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    assert not (set(hostile) & set(env))
    assert env == {
        **module.SYSTEM_ENV,
        "OPENCLAW_BASE_DIR": str(module.REPO),
        "OPENCLAW_DATA_DIR": str(module.DATA),
        "OPENCLAW_SECRETS_ROOT": str(module.SECRETS_ROOT),
        "OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON": str(module.STANDING_AUTH_PATH),
        "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD": module.TARGET_HEAD,
        "OPENCLAW_EXPECTED_SOURCE_HEAD": module.TARGET_HEAD,
        "OPENCLAW_COST_GATE_LEARNING_LEDGER": str(module.LEDGER_PATH),
        "OPENCLAW_COST_GATE_LEARNING_MATERIALIZE_REJECTS": "1",
        "OPENCLAW_COST_GATE_LEARNING_APPEND_MATERIALIZED_REJECTS": "1",
        "OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES": "1",
        "OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES": "0",
        "OPENCLAW_CRON_OOM_VICTIM_SCORE": "800",
        "ALR_CANDIDATE_EVIDENCE_DIR": staging["cron_destination"],
    }
    assert env["GIT_OPTIONAL_LOCKS"] == "0"
    assert env["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert env["GIT_CONFIG_SYSTEM"] == "/dev/null"
    assert env["GIT_CONFIG_KEY_0"] == "core.fsmonitor"
    assert env["GIT_CONFIG_VALUE_0"] == "false"
    assert env["GIT_CONFIG_KEY_1"] == "core.hooksPath"
    assert env["GIT_CONFIG_VALUE_1"] == "/dev/null"
    source = module.MODULE_SOURCE if hasattr(module, "MODULE_SOURCE") else MODULE_PATH.read_text()
    assert "dict(os.environ)" not in source
    assert '"PYTHONPATH"' not in source
    assert '"PYTHONDONTWRITEBYTECODE"' not in source


def test_pin_overlay_overwrites_base_engine_system_and_derive_environments() -> None:
    module = load_module()
    spec = importlib.util.spec_from_file_location("pin_overlay_environment_test", module.PIN_OVERLAY)
    assert spec is not None and spec.loader is not None
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)
    engine = SimpleNamespace(
        SYSTEM_ENV={"HOSTILE": "1"},
        DERIVE_ENV={"HOSTILE": "1"},
    )
    configured = configure_overlay(module, overlay, engine)
    assert configured.SYSTEM_ENV == module.SYSTEM_ENV
    assert configured.DERIVE_ENV == {
        **module.SYSTEM_ENV,
        "OPENCLAW_BASE_DIR": str(module.REPO),
        "OPENCLAW_DATA_DIR": str(module.DATA),
    }
    assert "HOSTILE" not in configured.SYSTEM_ENV
    assert "HOSTILE" not in configured.DERIVE_ENV


@pytest.mark.parametrize("drift_surface", ["local_head", "local_origin", "remote_origin"])
def test_source_snapshot_freshly_binds_local_and_true_remote_heads(drift_surface, monkeypatch) -> None:
    module = load_module()
    runtime = object.__new__(module.Runtime)
    local_head = module.TARGET_HEAD if drift_surface != "local_head" else "a" * 40
    local_origin = module.TARGET_HEAD if drift_surface != "local_origin" else "b" * 40
    remote_origin = module.TARGET_HEAD if drift_surface != "remote_origin" else "c" * 40
    monkeypatch.setattr(module.os, "getuid", lambda: 1000)
    monkeypatch.setattr(module.os, "getgid", lambda: 1000)
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command == ["/usr/bin/git", "symbolic-ref", "--quiet", "--short", "HEAD"]:
            return SimpleNamespace(stdout="main\n")
        if command == ["/usr/bin/git", "rev-parse", "HEAD"]:
            return SimpleNamespace(stdout=local_head + "\n")
        if command == ["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"]:
            return SimpleNamespace(stdout="")
        if command == ["/usr/bin/git", "rev-parse", "origin/main"]:
            return SimpleNamespace(stdout=local_origin + "\n")
        assert command == [
            "/usr/bin/git", "ls-remote", "--exit-code", "origin", "refs/heads/main"
        ]
        return SimpleNamespace(stdout=f"{remote_origin}\trefs/heads/main\n")

    runtime.run = fake_run
    with pytest.raises(module.RollforwardError, match="target_no_longer_current"):
        runtime.source_snapshot()
    assert calls == [
        ["/usr/bin/git", "symbolic-ref", "--quiet", "--short", "HEAD"],
        ["/usr/bin/git", "rev-parse", "HEAD"],
        ["/usr/bin/git", "status", "--porcelain=v1", "--untracked-files=all"],
        ["/usr/bin/git", "rev-parse", "origin/main"],
        ["/usr/bin/git", "ls-remote", "--exit-code", "origin", "refs/heads/main"],
    ]


def test_source_snapshot_records_fresh_true_remote_head(monkeypatch) -> None:
    module = load_module()
    runtime = object.__new__(module.Runtime)
    monkeypatch.setattr(module.os, "getuid", lambda: 1000)
    monkeypatch.setattr(module.os, "getgid", lambda: 1000)
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        if command[1] == "symbolic-ref":
            return SimpleNamespace(stdout="main\n")
        if command[1] == "status":
            return SimpleNamespace(stdout="")
        if command[1] == "rev-parse":
            return SimpleNamespace(stdout=module.TARGET_HEAD + "\n")
        return SimpleNamespace(stdout=f"{module.TARGET_HEAD}\trefs/heads/main\n")

    runtime.run = fake_run
    snapshot = runtime.source_snapshot()
    assert snapshot["origin_main"] == module.TARGET_HEAD
    assert snapshot["remote_origin_main"] == module.TARGET_HEAD
    assert calls[-1] == [
        "/usr/bin/git", "ls-remote", "--exit-code", "origin", "refs/heads/main"
    ]


def test_git_capture_uses_null_hooks_no_optional_locks_and_no_inherited_env(monkeypatch) -> None:
    module = load_module()
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout=module.TARGET_HEAD + "\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    runtime = object.__new__(module.Runtime)
    runtime.run(["/usr/bin/git", "rev-parse", "origin/main"], cwd=module.REPO)
    assert captured["env"] == module.SYSTEM_ENV
    assert captured["env"]["GIT_OPTIONAL_LOCKS"] == "0"
    assert captured["env"]["GIT_CONFIG_VALUE_1"] == "/dev/null"
    assert "BASH_ENV" not in captured["env"]


def test_retained_ledger_inventory_streams_hash_bytes_lines_and_identity(tmp_path) -> None:
    module = load_module()
    main = tmp_path / "probe_ledger.jsonl"
    shard = tmp_path / "probe_ledger.20260717T120000Z.jsonl"
    main.write_bytes(b'{"a":1}\n{"b":2}')
    shard.write_bytes(b'{"c":3}\n')
    inventory = module.Runtime.ledger_inventory(tmp_path)
    assert set(inventory) == {main.name, shard.name}
    assert inventory[main.name]["sha256"] == hashlib.sha256(main.read_bytes()).hexdigest()
    assert inventory[main.name]["bytes"] == len(main.read_bytes())
    assert inventory[main.name]["lines"] == 2
    assert inventory[shard.name]["lines"] == 1
    assert {"dev", "ino", "uid", "gid", "mode", "nlink"} <= set(inventory[main.name])


def test_retained_ledger_inventory_rejects_noncanonical_or_symlink_entries(tmp_path) -> None:
    module = load_module()
    (tmp_path / "probe_ledger.jsonl").write_text("{}\n")
    target = tmp_path / "outside.jsonl"
    target.write_text("{}\n")
    (tmp_path / "probe_ledger.bad.jsonl").symlink_to(target)
    with pytest.raises(module.RollforwardError, match="unsafe_ledger_entry"):
        module.Runtime.ledger_inventory(tmp_path)


def test_effective_ledger_config_is_fixed_and_content_bound() -> None:
    module = load_module()
    config = module.Runtime.lane_effective_config()
    assert config == {
        "ledger_path": str(module.LEDGER_PATH),
        "materialize_rejects": True,
        "append_materialized_rejects": True,
        "append_outcomes": True,
        "record_probe_outcomes": False,
    }
    assert module.Runtime.lane_effective_config_sha256() == module.canonical_digest(config)


def test_phase1_private_bundle_stage_is_applied_and_receipt_sealed(monkeypatch, tmp_path) -> None:
    module = load_module()
    destination = tmp_path / "p0b-observer-deps"
    receipt = tmp_path / "private-deps-receipt.json"
    tmp_path.chmod(0o700)

    class Stager:
        SOURCE_ROOT = tmp_path / "source"
        DESTINATION_PARENT = tmp_path
        DESTINATION_NAME = destination.name
        SEALED_MANIFEST = {"psycopg2": {"x.py": "a" * 64}}

        @staticmethod
        def stage_bundle(**kwargs):
            assert kwargs["apply"] is True
            assert kwargs["strict_anchors"] is True
            return {
                "schema_version": "p0b_psycopg_private_bundle_stage_v1",
                "status": "APPLIED_POSTCHECK_PASS",
                "destination": str(destination),
                "source_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
                "destination_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
                "mutation_performed": True,
                "boundaries": {
                    "service_mutation": False, "database_access": False,
                    "broker_contact": False, "credential_access": False,
                    "subprocess_spawned": False, "source_repository_mutation": False,
                },
            }

    monkeypatch.setattr(module, "PRIVATE_BUNDLE_DESTINATION", destination)
    monkeypatch.setattr(module, "load_private_bundle_stager", lambda: Stager)
    monkeypatch.setattr(module, "require_private_directory", lambda _path: {})
    runtime = object.__new__(module.Runtime)
    sealed = runtime.stage_private_dependencies(receipt)
    assert sealed["private_deps_receipt"]["path"] == str(receipt)
    assert sealed["private_deps_destination"] == str(destination)
    assert json.loads(receipt.read_text())["status"] == "APPLIED_POSTCHECK_PASS"


def test_global_pin_consumers_require_exactly_one_cost_and_one_alpha_line() -> None:
    module = load_module()
    text = """
# comment
*/5 * * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/cost_gate_learning_lane_cron.sh
7 * * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/alpha_discovery_throughput_cron.sh
"""
    snapshot = module.Runtime.crontab_consumers_from_text(text)
    assert snapshot["cost"]["count"] == 1
    assert snapshot["alpha"]["count"] == 1
    assert snapshot["generation_overrides"] == []
    assert "line" not in snapshot["cost"]

    with pytest.raises(module.RollforwardError, match="consumer_count"):
        module.Runtime.crontab_consumers_from_text(
            text + "9 * * * * helper_scripts/cron/cost_gate_learning_lane_cron.sh\n"
        )
    with pytest.raises(module.RollforwardError, match="generation_override"):
        module.Runtime.crontab_consumers_from_text(
            text.replace(
                "7 *", f"OPENCLAW_EXPECTED_SOURCE_HEAD={'f' * 40} 7 *", 1
            )
        )


def test_lane_snapshot_requires_both_cost_and_alpha_quiescence() -> None:
    module = load_module()
    runtime = object.__new__(module.Runtime)
    runtime.pin = SimpleNamespace(assert_lane_quiescent=lambda: {"cost": "quiet"})
    runtime.alpha_lane_snapshot = lambda: {"alpha": "quiet"}
    assert runtime.lane_snapshot() == {
        "cost": {"cost": "quiet"}, "alpha": {"alpha": "quiet"}
    }


def test_full_user_unit_inventory_hashes_disk_units_and_rejects_reload(tmp_path) -> None:
    module = load_module()
    fragment = tmp_path / "example.service"
    fragment.write_text("[Service]\nExecStart=/bin/true\n")
    runtime = object.__new__(module.Runtime)

    def fake_run(command, **_kwargs):
        if "list-unit-files" in command:
            return SimpleNamespace(stdout="example.service enabled\n")
        need_reload = fake_run.need_reload
        return SimpleNamespace(
            stdout=(
                "LoadState=loaded\n"
                f"NeedDaemonReload={need_reload}\n"
                f"FragmentPath={fragment}\n"
                "DropInPaths=\n"
            )
        )

    fake_run.need_reload = "no"
    runtime.run = fake_run
    inventory = runtime.user_unit_inventory()
    assert inventory["example.service"]["fragment"]["sha256"] == hashlib.sha256(
        fragment.read_bytes()
    ).hexdigest()
    fake_run.need_reload = "yes"
    with pytest.raises(module.RollforwardError, match="user_unit_reload_pending"):
        runtime.user_unit_inventory()


def test_any_pending_user_manager_job_is_rejected() -> None:
    module = load_module()
    runtime = object.__new__(module.Runtime)
    runtime.run = lambda *_args, **_kwargs: SimpleNamespace(
        stdout="42 openclaw-watchdog.service restart running\n"
    )
    with pytest.raises(module.RollforwardError, match="user_manager_job_queued"):
        runtime.no_queued_job()


def test_low_cost_alr_availability_probe_binds_pid_ticks_and_cgroup(tmp_path) -> None:
    module = load_module()
    proc_root = tmp_path / "proc"
    cgroup_root = tmp_path / "cgroup"
    (proc_root / "42").mkdir(parents=True)
    stat_tail = ["S"] + ["0"] * 18 + ["88"] + ["0"] * 5
    (proc_root / "42" / "stat").write_text(f"42 (alr shadow) {' '.join(stat_tail)}\n")
    cgroup = cgroup_root / "user.slice/alr"
    cgroup.mkdir(parents=True)
    (cgroup / "cgroup.procs").write_text("42\n")
    (cgroup / "cgroup.events").write_text("populated 1\nfrozen 0\n")
    observed = module.Runtime.alr_availability_probe(
        {"MainPID": "42", "ProcessStartTicks": "88", "ControlGroup": "/user.slice/alr"},
        proc_root=proc_root,
        cgroup_root=cgroup_root,
    )
    assert observed["pid"] == 42
    assert observed["start_ticks"] == "88"
    assert observed["cgroup_populated"] == "1"
    (cgroup / "cgroup.procs").write_text("")
    with pytest.raises(module.RollforwardError, match="availability"):
        module.Runtime.alr_availability_probe(
            {"MainPID": "42", "ProcessStartTicks": "88", "ControlGroup": "/user.slice/alr"},
            proc_root=proc_root,
            cgroup_root=cgroup_root,
        )


def test_contained_lane_calls_availability_monitor_while_process_runs(monkeypatch, tmp_path) -> None:
    module = load_module()

    class FakeProcess:
        pid = 555
        returncode = 0

        def __init__(self):
            self.calls = 0

        def communicate(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(["lane"], timeout)
            return "ok", ""

    process = FakeProcess()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: process)

    def fake_killpg(_pid, sig):
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(module.os, "killpg", fake_killpg)
    samples = []
    completed = module.Runtime.run_contained(
        ["lane"], cwd=tmp_path, env={}, timeout=10,
        monitor=lambda: samples.append("sample") or {"ok": True},
        monitor_interval=0.01,
    )
    assert completed.returncode == 0
    assert len(samples) >= 2


def active_identity() -> dict[str, object]:
    return {
        "MainPID": "1953143",
        "ProcessStartTicks": "88",
        "InvocationID": "22006ec883284246a8eda9887f21f8e0",
        "NRestarts": 0,
        "ControlGroup": "/user.slice/alr",
        "ALRSourceHead": "275901baa09656e842f14b11e94c00f9bfe0c380",
    }


def sealed_identity(sha256: str, ino: int) -> dict[str, object]:
    return {
        "sha256": sha256, "dev": 66312, "ino": ino, "uid": 1000,
        "gid": 1000, "mode": 0o600, "nlink": 1, "size": 193,
    }


def ledger_pre_inventory() -> dict[str, dict[str, object]]:
    return {
        "probe_ledger.jsonl": {
            "sha256": "9" * 64, "bytes": 100, "lines": 2,
            "dev": 66312, "ino": 300, "uid": 1000, "gid": 1000,
            "mode": 0o600, "nlink": 1,
        }
    }


def ledger_post_inventory() -> dict[str, dict[str, object]]:
    result = ledger_pre_inventory()
    result["probe_ledger.jsonl"] = {
        **result["probe_ledger.jsonl"], "sha256": "e" * 64, "bytes": 140, "lines": 3,
    }
    return result


def approval(module, *, phase: int) -> dict:
    common = {
        "schema_version": module.INTERNAL_PLAN_SCHEMA,
        "phase": phase,
        "approval_id": f"rollforward-phase{phase}-approval",
        "authorization_digest": "sha256:" + "c" * 64,
        "target_head": module.TARGET_HEAD,
        "old_head": module.OLD_HEAD,
        "not_before_utc": "2026-07-17T00:00:00Z",
        "expires_at_utc": "2026-07-18T00:00:00Z",
        "protected_sha256": module.canonical_digest({"protected": True}),
        "service_baseline": {
            "unit_sha256": module.OLD_UNIT_SHA256,
            "pin_sha256": module.OLD_PIN_SHA256,
            "unit_head": module.OLD_HEAD,
            "pin_head": module.OLD_HEAD,
            "active_identity": active_identity(),
            "unit_identity": sealed_identity(module.OLD_UNIT_SHA256, 100),
            "pin_identity": sealed_identity(module.OLD_PIN_SHA256, 61384029),
            "unit_lock_identity": {
                "dev": 66312, "ino": 101, "uid": 1000, "gid": 1000,
                "mode": 0o600, "nlink": 1,
            },
            "cost_lock_identity": {
                "dev": 66312, "ino": 102, "uid": 1000, "gid": 1000,
                "mode": 0o600, "nlink": 1,
            },
            "alpha_lock_identity": {
                "dev": 66312, "ino": 103, "uid": 1000, "gid": 1000,
                "mode": 0o600, "nlink": 1,
            },
        },
        "formal_authority": {
            "authorization": {"path": "/tmp/formal-authorization.json", "sha256": "c" * 64},
            "authorization_digest": "sha256:" + "c" * 64,
            "runtime_bindings": {"path": "/tmp/phase-runtime-bindings.json", "sha256": "d" * 64},
            "runtime_bindings_artifact_digest": "sha256:" + "d" * 64,
            "authorized_runtime": {
                "expected_old_runtime_source_head": module.OLD_HEAD,
                "expected_old_pin_digest": "sha256:" + module.OLD_PIN_SHA256,
                "expected_source_tree_digest": "sha256:" + "e" * 64,
                "expected_pin_consumer_inventory_digest": "sha256:" + "f" * 64,
                "expected_runtime_identity_digest": "sha256:" + "1" * 64,
            },
        },
    }
    if phase == 1:
        root = module.STAGING_ROOT / common["approval_id"]
        common["staging"] = {
            "cron_destination": str(root / "cron-scratch"),
            "sealed_destination": str(root / "sealed"),
            "publisher_receipt_path": str(root / "staging-publisher-result.json"),
            "private_deps_receipt_path": str(root / "private-deps-receipt.json"),
            "private_deps_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
            "private_deps_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
            "expected_head_override": module.TARGET_HEAD,
            "baseline_live_inventory_sha256": module.canonical_digest({}),
            "baseline_ledger_inventory_sha256": module.canonical_digest(ledger_pre_inventory()),
            "lane_effective_config_sha256": module.Runtime.lane_effective_config_sha256(),
            "lane_timeout_seconds": 3600,
        }
    else:
        staged = module.STAGING_ROOT / "rollforward-phase1-approval" / "sealed" / "blocked_outcome_review_20260717T120000Z.json"
        h = "a" * 64
        common["evidence"] = {
            "phase1_receipt": {"path": str(module.RECEIPT_DIR / "rollforward-phase1-approval.phase1.json"), "sha256": "1" * 64},
            "phase1_closure": {"path": str(module.RECEIPT_DIR / "rollforward-phase1-approval.phase1.closure.json"), "sha256": "6" * 64},
            "sealed_lineage_bundle": {"path": str(module.RECEIPT_DIR / "rollforward-phase1-approval.phase1.lineage.json"), "sha256": "7" * 64},
            "completion": {"path": str(module.COMPLETION_DIR / "token.completion.json"), "sha256": "2" * 64},
            "producer_board": {"path": str(module.PRODUCER_DIR / staged.name), "sha256": h},
            "staged_board": {"path": str(staged), "sha256": h},
            "staging_publisher_receipt": {"path": str(module.STAGING_ROOT / "rollforward-phase1-approval" / "staging-publisher-result.json"), "sha256": "3" * 64},
            "private_deps_receipt": {"path": str(module.STAGING_ROOT / "rollforward-phase1-approval" / "private-deps-receipt.json"), "sha256": "b" * 64},
            "private_deps_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
            "private_deps_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
            "token": "4" * 32,
            "max_age_seconds": 86400,
            "proposed_unit_sha256": "5" * 64,
            "live_destination": str(module.EVIDENCE_DIR),
            "live_board_absent": True,
            "live_inventory_sha256": module.canonical_digest({}),
            "completion_inventory_sha256": module.canonical_digest({}),
            "producer_inventory_sha256": module.canonical_digest({}),
            "ledger_pre_inventory_sha256": module.canonical_digest(ledger_pre_inventory()),
            "ledger_post_inventory_sha256": module.canonical_digest(ledger_post_inventory()),
            "lane_effective_config_sha256": module.Runtime.lane_effective_config_sha256(),
        }
        common["observer"] = {
            "provisional_cutover_path": str(
                module.RECEIPT_DIR / f"{common['approval_id']}.phase2.provisional.json"
            ),
            "observer_input_path": str(
                module.RECEIPT_DIR / f"{common['approval_id']}.phase2.observer-input.json"
            ),
            "observer_source_digest": "sha256:" + module.OBSERVER_V2_SHA256,
        }
        common["lineage_authority"] = {
            "phase1_effect_receipt_digest": "sha256:" + "1" * 64,
            "phase1_closure_digest": "sha256:" + "6" * 64,
            "sealed_lineage_bundle_digest": "sha256:" + "7" * 64,
        }
    return common


class FakeRuntime:
    def __init__(self, module, approval_data: dict) -> None:
        self.m = module
        self.approval = approval_data
        self.events: list[str] = []
        self.head = module.OLD_HEAD
        self.unit_head = module.OLD_HEAD
        self.running = True
        self.receipt_collision = False
        self.fail_source = False
        self.fail_lane = False
        self.fail_evidence = False
        self.fail_publish = False
        self.fail_pin = False
        self.protected_drift_after_unit = False
        self.fence_drift_after_stop = False
        self.fail_semantic_lineage = False
        self.fail_semantic_lineage_at = None
        self.semantic_lineage_calls = 0
        self.fail_stop_after_effect = False
        self.revive_on_first_proof = False
        self.fail_compensation_stop = False
        self.stop_calls = 0
        self.cutover_lock_held = False
        self.observer_pass = False
        self.observer_drift = False
        self.nrestarts = "0"
        self.protected = {"protected": True}
        self.source = {"head": module.TARGET_HEAD, "origin_main": module.TARGET_HEAD, "clean": True}
        self.tree = {"tree": "exact"}
        self.live: dict[str, str] = {}
        self.completion_inventory: dict[str, str] = {}
        self.producer_inventory: dict[str, str] = {}
        self.ledger = (
            ledger_post_inventory() if approval_data["phase"] == 2 else ledger_pre_inventory()
        )

    def now(self):
        return datetime(2026, 7, 17, 12, tzinfo=timezone.utc)

    def receipt_absent(self, phase):
        if self.receipt_collision:
            raise self.m.RollforwardError("receipt_exists")

    def source_snapshot(self):
        if self.fail_source:
            raise self.m.RollforwardError("target_no_longer_current")
        return self.source

    def execution_tree_lease(self):
        return self.tree

    def lane_snapshot(self):
        if self.fail_lane:
            raise self.m.RollforwardError("natural_lane_not_quiescent")
        return {"quiescent": True}

    def protected_snapshot(self):
        if self.protected_drift_after_unit and self.unit_head == self.m.TARGET_HEAD:
            return {"protected": False, "NeedDaemonReload": "yes"}
        return self.protected

    def unit_snapshot(self, *, expected_head):
        if self.unit_head != expected_head:
            raise self.m.RollforwardError("unit_head")
        sha = self.m.OLD_UNIT_SHA256 if expected_head == self.m.OLD_HEAD else "5" * 64
        identity = sealed_identity(sha, 100)
        return {"identity": identity, "head": expected_head, "raw": b"old"}

    def pin_snapshot(self, *, expected_head):
        if self.head != expected_head:
            raise self.m.RollforwardError("pin_head")
        sha = self.m.OLD_PIN_SHA256 if expected_head == self.m.OLD_HEAD else "6" * 64
        identity = sealed_identity(sha, 61384029 if expected_head == self.m.OLD_HEAD else 200)
        return {"identity": identity, "payload": {"head": expected_head}}

    def service_snapshot(self, *, require_active):
        if require_active and not self.running:
            raise self.m.RollforwardError("not_running")
        if require_active is False and self.running:
            raise self.m.RollforwardError("not_stopped")
        result = {key: str(value) for key, value in active_identity().items()}
        result.update({
            "ALRSourceHead": self.unit_head,
            "ControlGroup": "/user.slice/alr",
            "ActiveState": "active" if self.running else "inactive",
            "SubState": "running" if self.running else "dead",
            "NRestarts": self.nrestarts,
        })
        if not self.running:
            result["MainPID"] = "0"
        return result

    def no_queued_job(self):
        return {"status": "NO_QUEUED_JOB"}

    def lane_inventories(self, *, staging):
        return {"completion": {}, "producer": {}, "cron_staging": {}, "sealed_staging": {}, "live": dict(self.live)}

    def inventory_digest(self, value):
        return self.m.canonical_digest(value)

    def ledger_inventory(self):
        return json.loads(json.dumps(self.ledger))

    def lane_effective_config_sha256(self):
        return self.m.Runtime.lane_effective_config_sha256()

    def persist_path(self, path, payload):
        event = "intent" if ".intent." in str(path) else "attempt"
        self.events.append(event)
        return {"path": str(path), "sha256": "7" * 64, "size": 1}

    def persist_receipt(self, phase, payload):
        self.events.append("effect")
        return {"path": f"phase{phase}", "sha256": "8" * 64, "size": 1}

    def stage_lane(self, before):
        self.events.append("lane")
        self.ledger = ledger_post_inventory()
        name = "blocked_outcome_review_20260717T120000Z.json"
        return {
            "token": "4" * 32,
            "completion": {"path": "completion", "sha256": "2" * 64},
            "producer_board": {"path": "producer", "sha256": "a" * 64},
            "staged_board": {"path": name, "sha256": "a" * 64},
            "staging_publisher_receipt": {"path": "publisher", "sha256": "3" * 64},
            "private_deps_receipt": {"path": "private-deps", "sha256": "b" * 64},
            "private_deps_destination": str(self.m.PRIVATE_BUNDLE_DESTINATION),
            "private_deps_manifest_sha256": self.m.PRIVATE_BUNDLE_MANIFEST_SHA256,
            "publisher_result": {"status": "PUBLISHED"},
            "completion_inventory_sha256": self.m.canonical_digest(self.completion_inventory),
            "producer_inventory_sha256": self.m.canonical_digest(self.producer_inventory),
            "ledger_pre_inventory_sha256": self.m.canonical_digest(before["ledger_inventory"]),
            "ledger_post_inventory_sha256": self.m.canonical_digest(self.ledger),
            "lane_effective_config_sha256": self.m.Runtime.lane_effective_config_sha256(),
        }

    @contextmanager
    def transaction_lock(self):
        self.events.append("admit_lock")
        yield {"lane": True, "unit": True}

    def phase1_receipt(self):
        if self.fail_evidence:
            raise self.m.RollforwardError("missing_phase1")
        return {"payload": {"status": "PHASE1_STAGING_APPLIED_PASS"}}

    def validate_authorized_phase1_lineage(self):
        self.semantic_lineage_calls += 1
        if self.fail_semantic_lineage or self.semantic_lineage_calls == self.fail_semantic_lineage_at:
            raise self.m.RollforwardError("phase1_sealed_lineage_bundle_semantic_mismatch")
        return {"status": "PHASE1_SEMANTIC_LINEAGE_PASS"}

    def evidence_snapshot(self):
        if self.fail_evidence:
            raise self.m.RollforwardError("stale_or_cross_head")
        return {"status": "COMPLETE", "source_head": self.m.TARGET_HEAD}

    def live_inventory(self):
        return dict(self.live)

    def generation_fence_snapshot(self):
        snapshot = {
            "completion_inventory_sha256": self.m.canonical_digest(self.completion_inventory),
            "producer_inventory_sha256": self.m.canonical_digest(self.producer_inventory),
            "ledger_post_inventory_sha256": self.m.canonical_digest(self.ledger),
            "lane_effective_config_sha256": self.m.Runtime.lane_effective_config_sha256(),
        }
        if self.fence_drift_after_stop and not self.running:
            snapshot["producer_inventory_sha256"] = self.m.canonical_digest({"new": "c" * 64})
        return snapshot

    @contextmanager
    def cutover_lock(self):
        self.events.append("lock")
        self.cutover_lock_held = True
        try:
            yield {"lane": True, "unit": True, "publisher": True, "publisher_module": object()}
        finally:
            self.cutover_lock_held = False

    def stop_alr(self):
        self.events.append("stop")
        self.stop_calls += 1
        if self.fail_compensation_stop and self.stop_calls >= 2:
            raise self.m.RollforwardError("compensation_stop_failed")
        self.running = False
        if self.fail_stop_after_effect and self.stop_calls == 1:
            raise self.m.RollforwardError("stop_failed_after_effect")
        return {"action": "stop"}

    def prove_old_absent_twice(self, prior):
        if self.revive_on_first_proof and self.stop_calls == 1:
            self.running = True
            raise self.m.RollforwardError("unexpected_revival")
        self.events.extend(["empty1", "empty2"])
        return [{"ordinal": 1}, {"ordinal": 2}]

    def advance_pin(self):
        self.events.append("pin")
        self.head = self.m.TARGET_HEAD
        if self.fail_pin:
            raise self.m.RollforwardError("ambiguous_pin_write")
        return {"status": "APPLIED_POSTCHECK_PASS"}

    def publish_live_locked(self, publisher, binding):
        self.events.append("publish")
        if self.fail_publish:
            raise self.m.RollforwardError("publisher_not_published")
        name = Path(binding["path"]).name
        self.live[name] = binding["sha256"]
        return {"status": "PUBLISHED", "published_path": str(self.m.EVIDENCE_DIR / name)}

    def atomic_unit_to_target(self):
        self.events.append("unit")
        self.unit_head = self.m.TARGET_HEAD
        return b"old", {"identity": {"sha256": "5" * 64}}

    def daemon_reload(self):
        self.events.append("reload")
        return {"action": "daemon-reload"}

    def reset_failed(self):
        self.events.append("reset")
        return {"action": "reset-failed"}

    def restart_alr(self):
        self.events.append("restart")
        self.running = True
        return {"action": "restart"}

    def wait_stable_target(self, *, prior):
        return self.service_snapshot(require_active=True)

    def current_observer_v2_admission(self, **_kwargs):
        assert self.cutover_lock_held is False
        self.events.append("observer")
        if self.observer_drift:
            self.nrestarts = "1"
        if self.observer_pass:
            return {"status": "OBSERVER_V2_EXACT_POSTCHECK_PASS"}
        return {"status": "PENDING_OBSERVER_V2_INTEGRATION", "apply_capable": False}


def test_governance_and_live_rendezvous_bindings_are_current() -> None:
    module = load_module()
    assert module.TARGET_HEAD == "211f26c8e865757633076bc137c743f48fed80b6"
    assert module.AUTHORIZATION_SCHEMA == "p0b_alr_runtime_authorization_v1"
    assert not hasattr(module, "TASK_FACTS_SHA256")
    assert not hasattr(module, "ROUTE_ARTIFACT_SHA256")
    assert module.PIN_OVERLAY.name == "p0b_generation_pin_apply_current_head_v1.py"
    assert not module.PIN_OVERLAY.with_name("p0b_generation_pin_apply_eeaac_v1.py").exists()
    assert str(module.EVIDENCE_DIR) == "/home/ncyu/.local/share/openclaw/alr-candidate-evidence"
    assert hashlib.sha256(module.PIN_OVERLAY.read_bytes()).hexdigest() == module.PIN_OVERLAY_SHA256


def test_target_pin_overlay_seals_reviewed_engine_and_exact_old_pin() -> None:
    module = load_module()
    spec = importlib.util.spec_from_file_location("pin_overlay_under_test", module.PIN_OVERLAY)
    assert spec is not None and spec.loader is not None
    overlay = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overlay)
    engine = configure_overlay(module, overlay, type("Engine", (), {})())
    assert overlay.BASE_WRAPPER_SHA256 == "4ced9de5f688c2db0a12c1f11058001e069fc8e6f6e72dff299178136cd5e9b7"
    assert engine.EXPECTED_HEAD == module.TARGET_HEAD
    assert engine.OLD_HEAD == module.OLD_HEAD
    assert engine.OLD_PIN_SHA256 == module.OLD_PIN_SHA256
    assert engine.EXPECTED_OLD_PIN_INO == 61384029


def test_phase1_stages_without_stopping_or_repinning_old_runtime() -> None:
    module = load_module()
    approved = approval(module, phase=1)
    runtime = FakeRuntime(module, approved)
    result = module.Phase1Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE1_STAGING_APPLIED_PASS"
    assert runtime.events == ["admit_lock", "intent", "attempt", "lane", "lock", "effect"]
    assert runtime.running is True
    assert runtime.head == module.OLD_HEAD
    assert runtime.unit_head == module.OLD_HEAD
    assert result["live_publication_performed"] is False
    assert result["boundaries"]["pg_access"] == "normal_lane_readonly"
    assert result["sealed_lineage"]["ledger_pre_inventory_sha256"] == approved["staging"]["baseline_ledger_inventory_sha256"]
    assert result["sealed_lineage"]["ledger_post_inventory_sha256"] == module.canonical_digest(ledger_post_inventory())
    assert result["sealed_lineage"]["private_deps_destination"] == str(module.PRIVATE_BUNDLE_DESTINATION)


def test_phase1_empty_engine_baseline_rejects_zero_to_one_drift() -> None:
    module = load_module()
    approved = approval(module, phase=1)

    class EngineDriftRuntime(FakeRuntime):
        def __init__(self, runtime_module, approval_data):
            super().__init__(runtime_module, approval_data)
            self.protected = {"engine": []}

        def stage_lane(self, before):
            staged = super().stage_lane(before)
            self.protected = {
                "engine": [{"pid": 2193188, "start_ticks": "2300000000000"}]
            }
            return staged

    runtime = EngineDriftRuntime(module, approved)
    approved["protected_sha256"] = module.canonical_digest(runtime.protected)
    result = module.Phase1Transaction(runtime, approved).apply()

    assert result["status"] == "PHASE1_STAGING_FAILED_OLD_ALR_VERIFIED"
    assert result["old_runtime_verified"] is True
    assert runtime.running is True
    assert "effect" not in runtime.events


@pytest.mark.parametrize("failure", ["source", "lane", "collision"])
def test_phase1_admission_failure_has_no_effect(failure) -> None:
    module = load_module()
    approved = approval(module, phase=1)
    runtime = FakeRuntime(module, approved)
    runtime.fail_source = failure == "source"
    runtime.fail_lane = failure == "lane"
    runtime.receipt_collision = failure == "collision"
    with pytest.raises(module.RollforwardError):
        module.Phase1Transaction(runtime, approved).preflight()
    assert runtime.events == []


def test_phase2_reaches_target_then_fails_closed_pending_observer_v2() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    result = module.Phase2Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
    assert runtime.events == [
        "intent", "lock", "attempt", "stop", "empty1", "empty2", "pin",
        "publish", "unit", "reload", "reset", "restart", "observer", "stop",
        "empty1", "empty2", "attempt",
    ]
    assert runtime.events.count("restart") == 1
    assert result["observer_v2_integration"] == "FAILED_EXACT_POSTCHECK"
    assert runtime.running is False


@pytest.mark.parametrize("failure_call", [1, 3])
def test_phase2_semantic_lineage_is_revalidated_before_any_service_mutation(failure_call) -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.fail_semantic_lineage_at = failure_call
    with pytest.raises(module.RollforwardError, match="semantic_mismatch"):
        module.Phase2Transaction(runtime, approved).apply()
    assert "stop" not in runtime.events
    assert runtime.running is True


def test_phase2_releases_mutation_locks_before_exact_observer_success() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.observer_pass = True
    result = module.Phase2Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE2_APPLIED_POSTCHECK_PASS"
    assert result["mutation_locks_released_before_observer"] is True
    assert runtime.running is True
    assert runtime.cutover_lock_held is False
    assert runtime.events[-2:] == ["observer", "effect"]


def test_post_observer_restart_drift_compensation_stops_before_failure_ledger() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.observer_pass = True
    runtime.observer_drift = True
    result = module.Phase2Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
    assert result["mutation_locks_released_before_observer"] is True
    assert runtime.events.index("observer") < runtime.events.index("stop", 4)
    assert runtime.running is False


def exact_nonempty_observer_board(module):
    row = {
        "schema_version": "cost_gate_learning_candidate_v2",
        "candidate_id": "candidate-dynamic-1",
        "candidate_family_key": "1" * 64,
        "stable_cohort_hash": "2" * 64,
        "candidate_identity": {"strategy_name": "ma_crossover"},
        "identity_complete": True,
        "arbiter_input": {"score": "0.700000000000000000"},
        "arbiter_input_complete": True,
        "selection_eligible": True,
        "blockers": [],
        # This audit-only field is intentionally excluded from candidate_set_hash.
        "qualified_metrics_actionable": True,
    }
    board = {
        "schema_version": "cost_gate_learning_candidate_board_v2",
        "as_of_utc_date": "2026-07-17", "candidate_universe_complete": True,
        "lineage_partition_complete": True,
        "raw_blocked_outcome_row_count": 0,
        "qualified_lineage_outcome_row_count": 0,
        "unqualified_lineage_outcome_row_count": 0,
        "invalid_lineage_outcome_row_count": 0,
        "invalid_exact_cohort_row_count": 0,
        "invalid_identity_family_row_count": 0,
        "unassigned_invalid_lineage_outcome_row_count": 0,
        "unqualified_raw_valid_evaluation_missing_row_count": 0,
        "unqualified_event_outside_evaluation_window_row_count": 0,
        "consistent_duplicate_event_hash_extra_row_count": 0,
        "conflicting_duplicate_event_hash_row_count": 0,
        "conflicting_duplicate_event_hash_attribution_row_count": 0,
        "lineage_exclusion_reason_counts": {}, "candidate_rows": [row],
    }
    semantic_rows = [{field: row[field] for field in module.CANDIDATE_SELECTION_FIELDS}]
    semantic_rows.sort(
        key=lambda item: (item["candidate_id"], module.canonical_digest(item))
    )
    board["selection_hash"] = module.canonical_digest({
        "schema_version": "cost_gate_learning_candidate_selection_v2",
        "candidate_rows": semantic_rows,
    }).removeprefix("sha256:")
    selection_fields = set(module.CANDIDATE_SELECTION_FIELDS)
    audit_rows = [{
        "candidate_id": row["candidate_id"],
        **{key: value for key, value in row.items()
           if key not in selection_fields and key != "candidate_id"},
    }]
    board["audit_hash"] = module.canonical_digest({
        "schema_version": "cost_gate_learning_candidate_audit_v2",
        **{field: board[field] for field in module.CANDIDATE_BOARD_AUDIT_FIELDS},
        "candidate_audit_rows": audit_rows,
    }).removeprefix("sha256:")
    board["board_hash"] = module.canonical_digest(board).removeprefix("sha256:")
    return board, module.canonical_digest(semantic_rows).removeprefix("sha256:")


def test_core_observer_projection_excludes_audit_only_candidate_fields() -> None:
    module = load_module()
    board, expected_candidate_set = exact_nonempty_observer_board(module)
    validated = module.validate_observer_board_hashes(board)
    assert validated["candidate_set_hash"] == expected_candidate_set
    assert validated["candidate_set_hash"] != module.canonical_digest(
        board["candidate_rows"]
    ).removeprefix("sha256:")


@pytest.mark.parametrize("field", ["selection_hash", "audit_hash", "board_hash"])
def test_core_observer_projection_rejects_forged_board_hashes(field) -> None:
    module = load_module()
    board, _ = exact_nonempty_observer_board(module)
    board[field] = "f" * 64
    with pytest.raises(module.RollforwardError, match=f"observer_{field}_mismatch"):
        module.validate_observer_board_hashes(board)


@pytest.mark.parametrize("tamper", [False, True])
def test_exact_observer_persists_provisional_and_full_input_then_rechecks(
    monkeypatch, tamper
) -> None:
    module = load_module()
    approved = approval(module, phase=2)
    staged = approved["evidence"]["staged_board"]
    exact_board, expected_candidate_set = exact_nonempty_observer_board(module)
    board_raw = json.dumps({
        "generated_at_utc": "2026-07-17T11:59:00Z",
        "learning_candidate_board": exact_board,
    }).encode()

    class Harness:
        def __init__(self):
            self.approval = approved
            self.persisted = {}
            self.postcheck_count = 0
            self.pin = SimpleNamespace(read_regular_bytes=self.read_regular_bytes)

        def read_regular_bytes(self, path):
            path = Path(path)
            if path == module.PIN_PATH:
                raw = json.dumps({
                    "head": module.TARGET_HEAD,
                    "derived_at_utc": "2026-07-17T12:00:01Z",
                }).encode()
                return raw, {"sha256": hashlib.sha256(raw).hexdigest(), "nlink": 1}
            if path == module.OBSERVER_V2:
                raw = path.read_bytes()
                return raw, {"sha256": module.OBSERVER_V2_SHA256, "nlink": 1}
            return board_raw, {"sha256": staged["sha256"], "nlink": 1}

        def load_bound(self, binding, *, label):
            if label == "observer_staged_board":
                return board_raw, {"sha256": staged["sha256"], "nlink": 1}
            self.postcheck_count += 1
            if tamper and label == "observer_provisional_postcheck":
                raise module.RollforwardError("bound_artifact_hash_mismatch")
            raw = self.persisted[binding["path"]]["raw"]
            return raw, {"sha256": binding["sha256"], "nlink": 1}

        def observer_git_seals(self):
            return ({
                "path": str(module.REPO / "program_code/ml_training/alr_event_consumer.py"),
                "sha256": "4" * 64, "blob_sha1": "5" * 40,
                "ml_training_tree_sha1": "6" * 40,
            }, {
                "origin_main_head": module.TARGET_HEAD, "tracked_file_count": 1,
                "git_index_sha256": "7" * 64, "git_index_size": 1,
                "git_stage_inventory_sha256": "8" * 64,
                "git_stage_inventory_size": 1,
            })

        def persist_path(self, path, payload):
            raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
            binding = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}
            self.persisted[str(path)] = {"payload": payload, "raw": raw}
            return binding

        def observer_runtime_fence(self, active, *, unit_identity, pin_identity):
            return {"active_identity": active, "unit": unit_identity, "pin": pin_identity}

        def run_observer_process(self, command, *, monitor, timeout=7200):
            commands.append((command, {"timeout": timeout}))
            monitor()
            monitor()
            return subprocess.CompletedProcess(
                command, 0,
                stdout=json.dumps({"status": "OBSERVER_V2_EXACT_POSTCHECK_PASS"}),
                stderr="",
            )

    harness = Harness()
    commands = []

    active = {
        "MainPID": "99", "ProcessStartTicks": "100", "InvocationID": "b" * 32,
        "ExecMainStartTimestampMonotonic": "101", "NRestarts": "0",
        "ALRSourceHead": module.TARGET_HEAD,
    }
    call = lambda: module.Runtime.current_observer_v2_admission(
        harness, target_head=module.TARGET_HEAD, active_identity=active,
        generation_fence={
            "completion_inventory_sha256": "sha256:" + "a" * 64,
            "producer_inventory_sha256": "sha256:" + "b" * 64,
            "ledger_post_inventory_sha256": "sha256:" + "c" * 64,
            "lane_effective_config_sha256": "sha256:" + "d" * 64,
        },
        board_sha256=staged["sha256"],
        final_unit={"sha256": "e" * 64}, final_pin={"sha256": "f" * 64},
        observer_not_before_utc="2026-07-17T12:00:00Z",
    )
    if tamper:
        with pytest.raises(module.RollforwardError, match="hash_mismatch"):
            call()
        return
    result = call()
    assert result["status"] == "OBSERVER_V2_EXACT_POSTCHECK_PASS"
    provisional = harness.persisted[approved["observer"]["provisional_cutover_path"]]["payload"]
    full_input = harness.persisted[approved["observer"]["observer_input_path"]]["payload"]
    assert full_input["admitted_board"]["candidate_set_hash"] == expected_candidate_set
    assert set(provisional) == {
        "schema_version", "status", "target_head", "phase1_receipt",
        "cutover_authorization", "cutover_authorization_digest", "live_board",
        "unit", "pin", "private_deps_receipt", "private_deps_destination",
        "private_deps_manifest_sha256", "active_identity", "generation_fence",
        "observer_input_contract_sha256",
    }
    assert commands[0][0][:5] == [
        "/usr/bin/python3", "-I", "-B", str(module.OBSERVER_V2), "--observer-input",
    ]
    assert harness.postcheck_count == 2


def test_observer_process_continuously_samples_runtime_fence(monkeypatch) -> None:
    module = load_module()

    class Process:
        pid = 777
        returncode = 0

        def __init__(self):
            self.calls = 0

        def communicate(self, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired(["observer"], timeout)
            return "{\"status\":\"OBSERVER_V2_EXACT_POSTCHECK_PASS\"}", ""

    process = Process()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: process)
    samples = []
    completed = module.Runtime.run_observer_process(
        ["observer"], monitor=lambda: samples.append("fence") or {"ok": True},
        timeout=30,
    )
    assert completed.returncode == 0
    assert samples == ["fence", "fence", "fence"]


def test_stop_effect_before_return_is_compensated_and_proved_stopped() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.fail_stop_after_effect = True
    result = module.Phase2Transaction(runtime, approved).apply()
    assert runtime.stop_calls == 2
    assert runtime.running is False
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
    assert result["compensation_stop_attempted"] is True


def test_unexpected_revival_is_compensation_stopped_before_failure_ledger() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.revive_on_first_proof = True
    result = module.Phase2Transaction(runtime, approved).apply()
    assert runtime.stop_calls == 2
    assert runtime.running is False
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
    assert runtime.events.index("stop", 4) < runtime.events.index("attempt", 4)


def test_unproved_compensation_state_never_uses_stopped_or_frozen_status() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.fail_compensation_stop = True
    result = module.Phase2Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_STATE_UNVERIFIED"
    assert "FAIL_STOPPED" not in result["status"]
    assert "FROZEN" not in result["status"]
    assert result["alr_stopped"] is None


@pytest.mark.parametrize("reason", ["missing_phase1", "stale_cross_head"])
def test_phase2_refuses_missing_or_stale_lineage_before_effect(reason) -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.fail_evidence = True
    with pytest.raises(module.RollforwardError):
        module.Phase2Transaction(runtime, approved).preflight()
    assert runtime.events == []


def test_phase2_publisher_ambiguity_freezes_stopped_without_backward_effect() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.fail_publish = True
    result = module.Phase2Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
    assert runtime.running is False
    assert runtime.head == module.TARGET_HEAD
    assert "restart" not in runtime.events
    assert "restore" not in runtime.events
    assert result["no_backward_pin_attempted"] is True


@pytest.mark.parametrize("failure", ["pin", "protected_after_unit"])
def test_phase2_partial_effects_never_roll_backward_or_restart_old(failure) -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.fail_pin = failure == "pin"
    runtime.protected_drift_after_unit = failure == "protected_after_unit"
    result = module.Phase2Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
    assert runtime.running is False
    assert runtime.head == module.TARGET_HEAD
    assert "restart" not in runtime.events
    assert "restore" not in runtime.events


def test_phase2_live_inventory_or_receipt_collision_blocks_before_intent() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.live["newer.json"] = "f" * 64
    with pytest.raises(module.RollforwardError, match="live_inventory_drift"):
        module.Phase2Transaction(runtime, approved).preflight()
    runtime.live = {}
    runtime.receipt_collision = True
    with pytest.raises(module.RollforwardError, match="receipt_exists"):
        module.Phase2Transaction(runtime, approved).preflight()
    assert runtime.events == []


def test_phase2_newer_completion_or_producer_is_rejected_before_stop() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    for surface in ("completion", "producer"):
        runtime = FakeRuntime(module, approved)
        if surface == "completion":
            runtime.completion_inventory["new.completion.json"] = "a" * 64
        else:
            runtime.producer_inventory["blocked_outcome_review_new.json"] = "b" * 64
        with pytest.raises(module.RollforwardError, match="generation_fence"):
            module.Phase2Transaction(runtime, approved).preflight()
        assert "stop" not in runtime.events


def test_phase2_retained_ledger_drift_is_rejected_before_stop() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.ledger["probe_ledger.jsonl"]["bytes"] = 141
    with pytest.raises(module.RollforwardError, match="generation_fence"):
        module.Phase2Transaction(runtime, approved).preflight()
    assert "stop" not in runtime.events


def test_phase2_generation_fence_drift_after_stop_freezes_without_restart() -> None:
    module = load_module()
    approved = approval(module, phase=2)
    runtime = FakeRuntime(module, approved)
    runtime.fence_drift_after_stop = True
    result = module.Phase2Transaction(runtime, approved).apply()
    assert result["status"] == "PHASE2_POST_STOP_ATTEMPT_FAILURE_STOPPED_VERIFIED"
    assert runtime.running is False
    assert "stop" in runtime.events
    assert "restart" not in runtime.events


def test_command_allowlist_excludes_pg_broker_source_mutation_and_other_services() -> None:
    module = load_module()
    assert module.Runtime.command_allowed(
        [module.SYSTEMD, "--user", "stop", module.UNIT_NAME], mutate=True
    )
    forbidden = [
        ["/usr/bin/psql", "-c", "select 1"],
        ["/usr/bin/curl", "https://api.bybit.com"],
        ["/usr/bin/git", "reset", "--hard"],
        [module.SYSTEMD, "--user", "restart", "openclaw-trading-api.service"],
    ]
    assert all(not module.Runtime.command_allowed(command, mutate=True) for command in forbidden)
    assert not module.Runtime.command_allowed(["/usr/bin/git", "reset", "--hard"], mutate=False)
    assert not module.Runtime.command_allowed([module.SYSTEMD, "--user", "show", "other.service", "-p", "MainPID"], mutate=False)


def test_lane_and_cutover_boundaries_disclose_different_effect_surfaces() -> None:
    module = load_module()
    assert module.LANE_BOUNDARIES["normal_lane_pg_readonly"] is True
    assert module.LANE_BOUNDARIES["adapter_pg_access"] is False
    assert module.LANE_BOUNDARIES["live_alr_publication"] is False
    assert module.BOUNDARIES["pg_access"] is False
    assert module.BOUNDARIES["broker_contact"] is False


class EvidenceHarness:
    def __init__(
        self,
        module,
        *,
        source_head=None,
        generated="2026-07-17T11:58:00Z",
        publisher_status="PUBLISHED",
        staging_approval_id="rollforward-phase1-approval",
    ):
        self.m = module
        token = "4" * 32
        name = "blocked_outcome_review_20260717T115800Z.json"
        completion_path = module.COMPLETION_DIR / "token.completion.json"
        producer_path = module.PRODUCER_DIR / name
        staged_path = module.STAGING_ROOT / staging_approval_id / "sealed" / name
        publisher_path = module.STAGING_ROOT / staging_approval_id / "staging-publisher-result.json"
        private_path = module.STAGING_ROOT / staging_approval_id / "private-deps-receipt.json"
        bindings = {
            "completion": {"path": str(completion_path), "sha256": "2" * 64},
            "producer_board": {"path": str(producer_path), "sha256": "a" * 64},
            "staged_board": {"path": str(staged_path), "sha256": "a" * 64},
            "staging_publisher_receipt": {"path": str(publisher_path), "sha256": "3" * 64},
            "private_deps_receipt": {"path": str(private_path), "sha256": "b" * 64},
        }
        inventory_bindings = {
            "completion_inventory_sha256": module.canonical_digest({}),
            "producer_inventory_sha256": module.canonical_digest({}),
        }
        private_bindings = {
            "private_deps_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
            "private_deps_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
        }
        self.approval = {
            "evidence": {
                **bindings, **inventory_bindings, **private_bindings,
                "token": token, "max_age_seconds": 86400,
            }
        }
        self.phase1 = {
            "approval_id": "rollforward-phase1-approval",
            "completed_at_utc": "2026-07-17T12:00:00Z",
            "sealed_lineage": {
                "token": token, **bindings, **inventory_bindings, **private_bindings,
            },
        }
        board = {
            "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v6",
            "generated_at_utc": generated,
            "candidate_board_generation_state": "COMPLETE",
            "ledger_scan_status": "COMPLETE",
            "latest_alias_used": False,
            "order_authority": "NOT_GRANTED",
            "promotion_evidence": False,
            "learning_candidate_board": {
                "schema_version": "cost_gate_learning_candidate_board_v2",
                "candidate_universe_complete": True,
                "candidate_rows": [],
            },
        }
        completion = {
            "schema_version": "research_workload_completion_v1",
            "lane": "cost", "status": "COMPLETE", "token": token,
            "source_head": source_head or module.TARGET_HEAD,
            "ts_utc": "2026-07-17T11:59:00Z",
            "completion_paths": [str(producer_path)],
            "sha256_by_path": {str(producer_path): "a" * 64},
        }
        publisher = {
            "schema_version": "alr_candidate_board_publish_result_v2",
            "status": publisher_status, "published_path": str(staged_path),
            "source_content_sha256": "a" * 64, "latest_alias_written": False,
        }
        private = {
            "schema_version": "p0b_psycopg_private_bundle_stage_v1",
            "status": "APPLIED_POSTCHECK_PASS",
            "destination": str(module.PRIVATE_BUNDLE_DESTINATION),
            "source_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
            "destination_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
            "mutation_performed": True,
            "boundaries": {
                "service_mutation": False, "database_access": False,
                "broker_contact": False, "credential_access": False,
                "subprocess_spawned": False, "source_repository_mutation": False,
            },
        }
        self.raw = {
            str(completion_path): json.dumps(completion).encode(),
            str(producer_path): json.dumps(board).encode(),
            str(staged_path): json.dumps(board).encode(),
            str(publisher_path): json.dumps(publisher).encode(),
            str(private_path): json.dumps(private).encode(),
        }

    def phase1_receipt(self):
        return {"payload": self.phase1}

    def load_bound(self, binding, *, label):
        return self.raw[binding["path"]], {"sha256": binding["sha256"], "size": len(self.raw[binding["path"]])}

    def now(self):
        return datetime(2026, 7, 17, 12, 1, tzinfo=timezone.utc)

    _path_parent_exact = staticmethod(lambda path, parent: path.is_absolute() and path.parent == parent and "latest" not in path.name.lower())


def test_evidence_validator_accepts_exact_target_and_rejects_cross_head_or_stale() -> None:
    module = load_module()
    exact = EvidenceHarness(module)
    result = module.Runtime.evidence_snapshot(exact)
    assert result["status"] == "COMPLETE"
    assert result["authority"] == {"order": False, "probe": False, "promotion": False, "runtime": False}
    cross_head = EvidenceHarness(module, source_head=module.OLD_HEAD)
    with pytest.raises(module.RollforwardError, match="current_head_completion"):
        module.Runtime.evidence_snapshot(cross_head)
    stale = EvidenceHarness(module, generated="2026-07-15T11:58:00Z")
    with pytest.raises(module.RollforwardError, match="lineage_order|stale"):
        module.Runtime.evidence_snapshot(stale)
    already = EvidenceHarness(module, publisher_status="ALREADY_PUBLISHED")
    with pytest.raises(module.RollforwardError, match="publisher_receipt"):
        module.Runtime.evidence_snapshot(already)


def test_evidence_validator_accepts_dynamic_nonempty_candidate_rows() -> None:
    module = load_module()
    harness = EvidenceHarness(module)
    board_paths = (
        harness.approval["evidence"]["producer_board"]["path"],
        harness.approval["evidence"]["staged_board"]["path"],
    )
    board = json.loads(harness.raw[board_paths[0]])
    board["learning_candidate_board"]["candidate_rows"] = [
        {"candidate_id": "dynamic-1", "score": 0.7}
    ]
    for path in board_paths:
        harness.raw[path] = json.dumps(board).encode()
    result = module.Runtime.evidence_snapshot(harness)
    assert result["candidate_count"] == 1


def test_phase2_inventory_fence_must_equal_phase1_sealed_inventory() -> None:
    module = load_module()
    harness = EvidenceHarness(module)
    harness.phase1["sealed_lineage"]["completion_inventory_sha256"] = module.canonical_digest(
        {"new.completion.json": "d" * 64}
    )
    with pytest.raises(module.RollforwardError, match="phase1_to_phase2_lineage"):
        module.Runtime.evidence_snapshot(harness)


def test_approval_requires_full_protected_sha256() -> None:
    module = load_module()
    approved = approval(module, phase=1)
    approved["protected_sha256"] = "sha256:"
    with pytest.raises(module.RollforwardError, match="approval_binding"):
        module.validate_approval(
            approved, phase=1, now=datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
        )


@pytest.mark.parametrize("lock_name", ["cost_lock_identity", "alpha_lock_identity"])
def test_approval_requires_both_lane_lock_identities(lock_name) -> None:
    module = load_module()
    approved = approval(module, phase=1)
    approved["service_baseline"].pop(lock_name)
    with pytest.raises(module.RollforwardError, match="approval_service_baseline"):
        module.validate_approval(
            approved, phase=1, now=datetime(2026, 7, 17, 12, tzinfo=timezone.utc)
        )


def test_phase2_staging_paths_are_bound_to_phase1_approval_root() -> None:
    module = load_module()
    harness = EvidenceHarness(module, staging_approval_id="different-phase1-approval")
    with pytest.raises(module.RollforwardError, match="noncanonical_evidence_path"):
        module.Runtime.evidence_snapshot(harness)


def test_target_alr_stability_window_is_at_least_five_seconds(monkeypatch) -> None:
    module = load_module()
    assert module.ALR_STABLE_WINDOW_SECONDS >= 5
    sleeps: list[float] = []
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleeps.append(seconds))

    class StableHarness:
        def service_snapshot(self, *, require_active):
            assert require_active is True
            return {
                "MainPID": "99",
                "ProcessStartTicks": "100",
                "InvocationID": "b" * 32,
                "NRestarts": "0",
                "ALRSourceHead": module.TARGET_HEAD,
            }

    result = module.Runtime.wait_stable_target(
        StableHarness(),
        prior={"MainPID": "1", "ProcessStartTicks": "2", "InvocationID": "a" * 32},
    )
    assert result["NRestarts"] == "0"
    assert module.ALR_STABLE_WINDOW_SECONDS in sleeps


def test_protected_unit_snapshot_accepts_stable_historical_restart_baseline() -> None:
    module = load_module()
    stdout = "\n".join(
        (
            "LoadState=loaded",
            "ActiveState=active",
            "SubState=running",
            "MainPID=2168729",
            "ExecMainStartTimestampMonotonic=2309159552956",
            "NRestarts=1",
            "InvocationID=d74a6859241c4f1884bd35e0d08f41bb",
            "FragmentPath=/home/ncyu/.config/systemd/user/openclaw-watchdog.service",
            "DropInPaths=",
            "ControlGroup=/user.slice/openclaw-watchdog.service",
            "NeedDaemonReload=no",
        )
    )

    class Harness:
        @staticmethod
        def run(_command):
            return SimpleNamespace(stdout=stdout)

    snapshot = module.Runtime.protected_unit_snapshot(
        Harness(), "openclaw-watchdog.service"
    )

    assert snapshot["NRestarts"] == "1"
    assert snapshot["InvocationID"] == "d74a6859241c4f1884bd35e0d08f41bb"


def test_deleted_executable_engine_is_still_a_nonempty_candidate(tmp_path) -> None:
    module = load_module()
    process = tmp_path / "2193188"
    process.mkdir()
    (process / "comm").write_text("openclaw-engine\n", encoding="utf-8")
    (process / "exe").symlink_to("/srv/openclaw-engine (deleted)")

    assert module.Runtime._openclaw_engine_pid_candidates(tmp_path) == [2193188]


def test_protected_engine_snapshot_accepts_exact_absence_but_rejects_nonempty_mismatch() -> None:
    module = load_module()

    class MissingTopologyPin:
        @staticmethod
        def engine_processes():
            raise RuntimeError("engine_process_topology_mismatch")

    class AbsentHarness:
        pin = MissingTopologyPin()

        @staticmethod
        def _openclaw_engine_pid_candidates():
            return []

    assert module.Runtime.protected_engine_processes(AbsentHarness()) == []

    class NonemptyHarness(AbsentHarness):
        @staticmethod
        def _openclaw_engine_pid_candidates():
            return [2193188]

    with pytest.raises(
        module.RollforwardError, match="protected_engine_process_topology_invalid"
    ):
        module.Runtime.protected_engine_processes(NonemptyHarness())


def test_capture_phase1_facts_is_read_only_and_needs_no_approval(monkeypatch, capsys) -> None:
    module = load_module()
    effective_config = module.Runtime.lane_effective_config()

    class CaptureRuntime:
        def __init__(self):
            self.events: list[str] = []

        def source_snapshot(self):
            self.events.append("source")
            return {"head": module.TARGET_HEAD, "clean": True}

        def execution_tree_lease(self):
            self.events.append("tree")
            return {"git_tree_listing_sha256": "a" * 64}

        def lane_snapshot(self):
            self.events.append("lane")
            return {"owner_exists": False, "processes": [], "active_cost_scopes": []}

        def protected_snapshot(self):
            self.events.append("protected")
            return {"protected": True}

        def unit_snapshot(self, *, expected_head):
            self.events.append("unit")
            assert expected_head == module.OLD_HEAD
            return {"identity": sealed_identity(module.OLD_UNIT_SHA256, 100), "head": expected_head}

        def pin_snapshot(self, *, expected_head):
            self.events.append("pin")
            assert expected_head == module.OLD_HEAD
            return {"identity": sealed_identity(module.OLD_PIN_SHA256, 61384029), "payload": {"head": expected_head}}

        def service_snapshot(self, *, require_active):
            self.events.append("service")
            assert require_active is True
            return {key: str(value) for key, value in active_identity().items()}

        def unit_lock_snapshot(self):
            self.events.append("unit_lock")
            return {"dev": 66312, "ino": 101, "uid": 1000, "gid": 1000, "mode": 0o600, "nlink": 1}

        def lock_snapshot(self, path, *, label):
            self.events.append(f"{label}_lock")
            ino = 102 if label == "cost" else 103
            return {"dev": 66312, "ino": ino, "uid": 1000, "gid": 1000, "mode": 0o600, "nlink": 1}

        def live_inventory(self):
            self.events.append("live")
            return {}

        def ledger_inventory(self):
            self.events.append("ledger")
            return ledger_pre_inventory()

        def lane_effective_config(self):
            return effective_config

        def lane_effective_config_sha256(self):
            return module.canonical_digest(effective_config)

        def inventory_digest(self, value):
            return module.canonical_digest(value)

        def stop_alr(self):
            raise AssertionError("capture_must_not_mutate")

        def stage_lane(self, before):
            raise AssertionError("capture_must_not_stage")

        def persist_path(self, path, payload):
            raise AssertionError("capture_must_not_persist")

        def persist_receipt(self, phase, payload):
            raise AssertionError("capture_must_not_persist")

        def advance_pin(self):
            raise AssertionError("capture_must_not_repin")

        def restart_alr(self):
            raise AssertionError("capture_must_not_restart")

    runtime = CaptureRuntime()
    monkeypatch.setattr(module, "Runtime", lambda **_kwargs: runtime)
    assert module.main(["--capture-phase1-facts"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PHASE1_FACTS_CAPTURE_PASS"
    assert payload["mutation_performed"] is False
    assert payload["protected_sha256"] == module.canonical_digest({"protected": True})
    assert payload["live_inventory_sha256"] == module.canonical_digest({})
    assert runtime.events == [
        "source", "tree", "lane", "protected", "unit", "pin",
        "service", "unit_lock", "cost_lock", "alpha_lock", "live", "ledger",
    ]


def exact_phase1_lineage(module):
    stage_authorization = runtime_authorization(module, phase="stage")
    stage_bindings = phase_runtime_bindings(module, stage_authorization)
    stage_authorization_path = Path("/tmp/exact-stage-authorization.json")
    stage_bindings_path = Path(stage_authorization["governance_bindings"]["phase_runtime_bindings_path"])
    intent_path = module.RECEIPT_DIR / f"{stage_authorization['intent_id']}.phase1.intent.json"
    receipt_path = module.RECEIPT_DIR / f"{stage_authorization['intent_id']}.phase1.json"
    closure_path = module.RECEIPT_DIR / f"{stage_authorization['intent_id']}.phase1.closure.json"
    bundle_path = module.RECEIPT_DIR / f"{stage_authorization['intent_id']}.phase1.lineage.json"
    private_path = module.STAGING_ROOT / stage_authorization["intent_id"] / "private-deps-receipt.json"
    staged_path = module.STAGING_ROOT / stage_authorization["intent_id"] / "sealed" / "board.json"

    def raw(value):
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    raw_by_path = {
        str(stage_authorization_path): raw(stage_authorization),
        str(stage_bindings_path): raw(stage_bindings),
    }
    binding = lambda path: {
        "path": str(path), "sha256": hashlib.sha256(raw_by_path[str(path)]).hexdigest(),
    }
    intent_payload = {
        "schema_version": module.SCHEMA, "phase": 1, "kind": "intent",
        "approval_id": stage_authorization["intent_id"],
        "target_head": module.TARGET_HEAD,
        "source": stage_bindings["source_attestation"]["source"],
        "execution_tree": stage_bindings["source_attestation"]["execution_tree"],
        "mutation_scope": "normal_lane_and_unwatched_staging_only",
    }
    raw_by_path[str(intent_path)] = raw(intent_payload)
    private_payload = {
        "schema_version": "p0b_psycopg_private_bundle_stage_v1",
        "status": "APPLIED_POSTCHECK_PASS",
        "destination": str(module.PRIVATE_BUNDLE_DESTINATION),
        "source_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
        "destination_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
        "mutation_performed": True,
        "boundaries": {
            "service_mutation": False, "database_access": False,
            "broker_contact": False, "credential_access": False,
            "subprocess_spawned": False, "source_repository_mutation": False,
        },
    }
    raw_by_path[str(private_path)] = raw(private_payload)
    raw_by_path[str(staged_path)] = raw({
        "schema_version": "cost_gate_demo_learning_lane_blocked_outcome_review_v6",
        "candidate_board_generation_state": "COMPLETE", "ledger_scan_status": "COMPLETE",
        "latest_alias_used": False, "order_authority": "NOT_GRANTED",
        "promotion_evidence": False,
        "learning_candidate_board": {
            "schema_version": "cost_gate_learning_candidate_board_v2",
            "candidate_universe_complete": True,
            "candidate_rows": [{"candidate_id": "dynamic-1", "score": 0.7}],
        },
    })
    sealed = {
        "started_at_utc": "2026-07-17T11:58:30Z",
        "completed_at_utc": "2026-07-17T11:59:30Z",
        "token": "4" * 32,
        "completion": {"path": "/tmp/completion.json", "sha256": "3" * 64},
        "producer_board": {"path": "/tmp/board.json", "sha256": binding(staged_path)["sha256"]},
        "cron_staged_board": {"path": "/tmp/cron/board.json", "sha256": binding(staged_path)["sha256"]},
        "staged_board": binding(staged_path),
        "staging_publisher_receipt": {"path": "/tmp/publisher.json", "sha256": "5" * 64},
        "private_deps_receipt": binding(private_path),
        "private_deps_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
        "private_deps_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
        "publisher_result": {
            "schema_version": "alr_candidate_board_publish_result_v2", "status": "PUBLISHED",
            "published_path": str(staged_path), "source_content_sha256": binding(staged_path)["sha256"],
            "latest_alias_written": False,
        },
        "execution_tree": stage_bindings["source_attestation"]["execution_tree"],
        "live_inventory_sha256": stage_bindings["inventories"]["live_inventory_digest"],
        "completion_inventory_sha256": "sha256:" + "1" * 64,
        "producer_inventory_sha256": "sha256:" + "2" * 64,
        "ledger_pre_inventory_sha256": stage_bindings["inventories"]["ledger_inventory_digest"],
        "ledger_post_inventory_sha256": "sha256:" + "3" * 64,
        "lane_effective_config_sha256": stage_bindings["inventories"]["lane_effective_config_digest"],
        "alr_availability_monitor": {
            "sample_count": 2, "first": {"available": True}, "last": {"available": True},
            "final_service_identity": {
                key: value for key, value in stage_bindings["protected_runtime_baseline"]
                ["service_baseline"]["active_identity"].items()
                if key in {"MainPID", "ProcessStartTicks", "InvocationID", "NRestarts", "ControlGroup", "ALRSourceHead"}
            },
        },
        "normal_lane_returncode": 0,
        "observer_source_sha256": module.OBSERVER_V2_SHA256,
    }
    receipt = {
        "schema_version": module.SCHEMA, "phase": 1,
        "status": "PHASE1_STAGING_APPLIED_PASS",
        "approval_id": stage_authorization["intent_id"],
        "authorization_digest": stage_authorization["authorization_digest"],
        "stage_authorization": binding(stage_authorization_path),
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings": binding(stage_bindings_path),
        "stage_runtime_bindings_artifact_digest": stage_bindings["artifact_digest"],
        "stage_authorized_runtime": {
            key: stage_authorization[key] for key in (
                "expected_old_runtime_source_head", "expected_old_pin_digest",
                "expected_source_tree_digest", "expected_pin_consumer_inventory_digest",
                "expected_runtime_identity_digest",
            )
        },
        "target_head": module.TARGET_HEAD, "old_head": module.OLD_HEAD,
        "protected_sha256": stage_bindings["protected_runtime_baseline"]["protected_digest"],
        "old_alr_retained_running": True, "global_pin_retained_old": True,
        "live_publication_performed": False, "sealed_lineage": sealed,
        "completed_at_utc": "2026-07-17T12:00:00Z", "intent": binding(intent_path),
        "locks_held_through_effect_receipt": {
            "cost": stage_bindings["protected_runtime_baseline"]["service_baseline"]["cost_lock_identity"],
            "alpha": stage_bindings["protected_runtime_baseline"]["service_baseline"]["alpha_lock_identity"],
            "unit": stage_bindings["protected_runtime_baseline"]["service_baseline"]["unit_lock_identity"],
            "publisher": True,
        },
        "boundaries": module.LANE_BOUNDARIES,
    }
    raw_by_path[str(receipt_path)] = raw(receipt)
    receipt_binding = binding(receipt_path)
    receipt_digest = "sha256:" + receipt_binding["sha256"]
    phase_result_digest = module.canonical_digest(receipt)
    ops = {
        "schema_version": "ops_p0b_alr_postcheck_v1", "adapter_id": module.ADAPTER_ID,
        "phase": "stage", "intent_id": stage_authorization["intent_id"],
        "intent_digest": stage_authorization["intent_digest"],
        "task_contract_digest": stage_authorization["task_contract_digest"],
        "context_artifact_digest": stage_authorization["context_artifact_digest"],
        "compiled_route_digest": stage_authorization["governance_bindings"]["compiled_route_digest"],
        "source_head": module.TARGET_HEAD, "target_host": "trade-core",
        "target_user_unit": module.UNIT_NAME, "effect_receipt_digest": receipt_digest,
        "phase_result_digest": phase_result_digest, "observer_receipt_digest": None,
        "observed_at": "2026-07-17T12:01:00Z", "expires_at": "2026-07-17T12:11:00Z",
        "verified": True,
    }
    ops["operation_digest"] = module.canonical_digest(ops)
    closure = {
        "schema_version": "p0b_alr_phase1_governance_closure_v1",
        "status": "PHASE1_GOVERNANCE_CLOSURE_PASS", "phase": "stage",
        "intent_id": stage_authorization["intent_id"],
        "intent_digest": stage_authorization["intent_digest"],
        "task_contract_digest": stage_authorization["task_contract_digest"],
        "compiled_route_digest": stage_authorization["governance_bindings"]["compiled_route_digest"],
        "context_artifact_digest": stage_authorization["context_artifact_digest"],
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings_artifact_digest": stage_bindings["artifact_digest"],
        "phase1_effect_receipt_digest": receipt_digest,
        "phase_result_digest": phase_result_digest, "ops_postcheck": ops,
        "ops_postcheck_digest": ops["operation_digest"],
        "closed_at_utc": "2026-07-17T12:02:00Z",
    }
    closure["closure_digest"] = module.canonical_digest(closure)
    raw_by_path[str(closure_path)] = raw(closure)
    closure_binding = binding(closure_path)
    bundle = {
        "schema_version": "p0b_alr_phase1_sealed_lineage_bundle_v1",
        "target_head": module.TARGET_HEAD, "intent_id": stage_authorization["intent_id"],
        "intent_digest": stage_authorization["intent_digest"],
        "task_contract_digest": stage_authorization["task_contract_digest"],
        "compiled_route_digest": stage_authorization["governance_bindings"]["compiled_route_digest"],
        "context_artifact_digest": stage_authorization["context_artifact_digest"],
        "stage_authorization": binding(stage_authorization_path),
        "stage_authorization_digest": stage_authorization["authorization_digest"],
        "stage_runtime_bindings": binding(stage_bindings_path),
        "stage_runtime_bindings_artifact_digest": stage_bindings["artifact_digest"],
        "phase1_effect_receipt": receipt_binding,
        "phase1_effect_receipt_digest": receipt_digest,
        "phase1_closure": closure_binding,
        "phase1_closure_digest": "sha256:" + closure_binding["sha256"],
        "private_deps_receipt": binding(private_path),
        "private_deps_destination": str(module.PRIVATE_BUNDLE_DESTINATION),
        "private_deps_manifest_sha256": module.PRIVATE_BUNDLE_MANIFEST_SHA256,
        "staged_board": binding(staged_path),
    }
    bundle["bundle_digest"] = module.canonical_digest(bundle)
    raw_by_path[str(bundle_path)] = raw(bundle)
    return {
        "raw": raw_by_path, "receipt": receipt_binding,
        "closure": closure_binding, "bundle": binding(bundle_path),
        "receipt_payload": receipt, "closure_payload": closure,
        "bundle_payload": bundle, "authorization": stage_authorization,
        "runtime_bindings": stage_bindings,
    }


@pytest.mark.parametrize("tamper", [None, "arbitrary_closure", "closure_semantics", "bundle_semantics"])
def test_phase1_closure_and_sealed_bundle_are_exact_semantically_bound(tamper) -> None:
    module = load_module()
    fixture = exact_phase1_lineage(module)
    raw_by_path = dict(fixture["raw"])
    closure_binding = dict(fixture["closure"])
    bundle_binding = dict(fixture["bundle"])
    if tamper == "arbitrary_closure":
        raw_by_path[fixture["closure"]["path"]] = json.dumps({"status": "PASS"}).encode()
    elif tamper == "closure_semantics":
        forged = dict(fixture["closure_payload"])
        forged["task_contract_digest"] = "sha256:" + "f" * 64
        forged["closure_digest"] = module.canonical_digest({
            key: value for key, value in forged.items() if key != "closure_digest"
        })
        raw_by_path[fixture["closure"]["path"]] = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    elif tamper == "bundle_semantics":
        forged = dict(fixture["bundle_payload"])
        forged["staged_board"] = {"path": "/tmp/forged.json", "sha256": "f" * 64}
        forged["bundle_digest"] = module.canonical_digest({
            key: value for key, value in forged.items() if key != "bundle_digest"
        })
        raw_by_path[fixture["bundle"]["path"]] = json.dumps(forged, sort_keys=True, separators=(",", ":")).encode()
    if tamper in {"arbitrary_closure", "closure_semantics"}:
        closure_binding["sha256"] = hashlib.sha256(
            raw_by_path[closure_binding["path"]]
        ).hexdigest()
    if tamper == "bundle_semantics":
        bundle_binding["sha256"] = hashlib.sha256(
            raw_by_path[bundle_binding["path"]]
        ).hexdigest()

    class Harness:
        def load_bound(self, binding, *, label):
            raw = raw_by_path[binding["path"]]
            return raw, {"sha256": hashlib.sha256(raw).hexdigest(), "nlink": 1}

    call = lambda: module.validate_phase1_semantic_lineage(
        Harness(), phase1_receipt=fixture["receipt"],
        phase1_closure=closure_binding, sealed_lineage_bundle=bundle_binding,
    )
    if tamper is None:
        assert call()["status"] == "PHASE1_SEMANTIC_LINEAGE_PASS"
    else:
        with pytest.raises(module.RollforwardError, match="phase1_.*(invalid|mismatch)"):
            call()


def test_capture_phase2_facts_is_fresh_hash_bound_and_read_only(monkeypatch, capsys) -> None:
    module = load_module()
    fixture = exact_phase1_lineage(module)
    receipt_path = Path(fixture["receipt"]["path"])
    closure_path = Path(fixture["closure"]["path"])
    sealed = fixture["receipt_payload"]["sealed_lineage"]
    raw = fixture["raw"]

    class CaptureRuntime:
        def __init__(self):
            self.events = []

        def load_bound(self, binding, *, label):
            self.events.append(f"load:{label}")
            content = raw[binding["path"]]
            return content, {"sha256": hashlib.sha256(content).hexdigest(), "nlink": 1}

        def source_snapshot(self):
            self.events.append("source")
            return {"head": module.TARGET_HEAD, "clean": True}

        def execution_tree_lease(self):
            self.events.append("tree")
            return {"git_tree_listing_sha256": "e" * 64}

        def lane_snapshot(self):
            self.events.append("lane")
            return {"cost": {}, "alpha": {}}

        def protected_snapshot(self):
            self.events.append("protected")
            return {"stable": True}

        def unit_snapshot(self, *, expected_head):
            return {"identity": sealed_identity(module.OLD_UNIT_SHA256, 100)}

        def pin_snapshot(self, *, expected_head):
            return {"identity": sealed_identity(module.OLD_PIN_SHA256, 61384029)}

        def service_snapshot(self, *, require_active):
            return {key: str(value) for key, value in active_identity().items()}

        def unit_lock_snapshot(self):
            return {"dev": 1, "ino": 1, "uid": 1000, "gid": 1000, "mode": 0o600, "nlink": 1}

        def lock_snapshot(self, path, *, label):
            return {"dev": 1, "ino": 2 if label == "cost" else 3, "uid": 1000, "gid": 1000, "mode": 0o600, "nlink": 1}

        def live_inventory(self):
            return {}

        def artifact_inventory(self, directory, pattern):
            return {"captured": "f" * 64}

        def ledger_inventory(self):
            return ledger_pre_inventory()

        def inventory_digest(self, value):
            return module.canonical_digest(value)

        def lane_effective_config(self):
            return module.Runtime.lane_effective_config()

        def lane_effective_config_sha256(self):
            return module.Runtime.lane_effective_config_sha256()

        def now(self):
            return datetime(2026, 7, 17, 12, tzinfo=timezone.utc)

        def stop_alr(self):
            raise AssertionError("capture_must_not_mutate")

    runtime = CaptureRuntime()
    effective_config = module.Runtime.lane_effective_config()
    monkeypatch.setattr(module, "Runtime", lambda **_kwargs: runtime)
    runtime.lane_effective_config = lambda: effective_config
    runtime.lane_effective_config_sha256 = lambda: module.canonical_digest(effective_config)
    assert module.main([
        "--capture-phase2-facts",
        "--phase1-receipt-json", str(receipt_path),
        "--phase1-receipt-sha256", fixture["receipt"]["sha256"],
        "--phase1-closure-json", str(closure_path),
        "--phase1-closure-sha256", fixture["closure"]["sha256"],
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PHASE2_FACTS_CAPTURE_PASS"
    assert payload["mutation_performed"] is False
    assert payload["admitted_live_board_absent"] is True
    assert "source" in runtime.events
    assert "load:stage_authorization" in runtime.events
    assert "load:stage_runtime_bindings" in runtime.events
    assert "load:closure" in runtime.events


def test_board_authority_grant_is_rejected() -> None:
    module = load_module()
    board = {"order_authority": "GRANTED", "promotion_evidence": False}
    with pytest.raises(module.RollforwardError, match="authority"):
        module.assert_no_authority(board)
