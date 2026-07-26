"""S2.4(WP4·W3b)typed PREPARE driver 的 focused 測試(§5.1 / §8.1 / §10.5 #30/#33/#38)。

證明:

- source lane(``driver=None``)回 typed ``EXTERNAL_VERIFICATION_PENDING`` 且**零變更、零
  driver 接觸**;
- §10.5 #38:PREPARE 請求夾帶任一 APPLY surface(persistent-unit / PG / migration / secret /
  credential / host identity / ``/opt`` / ``/etc``)於節點注入前即拒;PREPARE 授權面不能被
  probe / aggregate-install / pg-migration profile 代替;
- §10.5 #33:fetch **不得**執行 artifact;build/import 的 network / credential / state 存取與
  「root 執行 dependency 程式碼」四旗標任一為真即失敗並補償;resource/egress/path 上限
  receipt-bound;寫到 ``/opt``、``/etc``、credstore 或 staging 之外一律 fail-closed;
- §5.1:hash-pin 不符即失敗;PREPARED 產出可被中央閘驗的
  ``s2_4_prepared_install_bundle_v1`` + ``s2_4_prepare_effect_receipt_v1``;
- §5.2:``PREPARING`` 於**建立 staging 之前**入 WAL;之後任一步崩潰都只補償 task-owned
  staging delta;
- 硬邊界 4:caller 遞交 raw shell/SQL/unit/path/secret 鍵一律 typed 拒。
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for candidate in (HELPERS, ML_ROOT, PROGRAM_CODE, ROOT / "tests/structure"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2_4_prepare as prepare  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402

_STAGING_DEVICE = 66306
_STAGING_INODE = 909_090
_PREPARE_AUTH_ID = "sha256:" + "3" * 64
_PINNED = [
    {"locator": "https://mirror.invalid/wheels/numpy-2.0-cp312.whl", "content_digest": "sha256:" + "a" * 64},
    {"locator": "https://mirror.invalid/wheels/psycopg2-2.9-cp312.whl", "content_digest": "sha256:" + "b" * 64},
]
_BASE_TREE = "sha256:" + "c" * 64
_APP_BUNDLE = "sha256:" + "d" * 64
_LAUNCH_BUNDLE = "sha256:" + "e" * 64


def _core() -> dict:
    return prepare.build_prepare_core(
        staging_parent_device=_STAGING_DEVICE, staging_parent_inode=_STAGING_INODE,
        max_bytes=2_000_000_000, max_seconds=1800, max_fetch_bytes=800_000_000,
        max_fetch_seconds=600, max_artifacts=64, max_build_bytes=1_500_000_000,
        max_build_seconds=900, source_head=kit.SOURCE_HEAD, target_host=kit.HOST,
        created_at=kit.ISSUED,
    )


def _intent(probe_receipt_digest: str) -> dict:
    return prepare.build_prepare_intent(
        _core(),
        source_compatibility_receipt_digest="sha256:" + "1" * 64,
        sealed_build_receipt_digest="sha256:" + "2" * 64,
        identity_contract_digest="sha256:" + "3" * 64,
        application_manifest_digest=_APP_BUNDLE,
        prepare_sandbox_probe_receipt_digest=probe_receipt_digest,
        expires_at=kit.EXPIRES, max_ttl_seconds=600,
    )


class _FakePrepareDriver:
    """注入式測試 driver:只記錄固定操作,絕不觸碰任何主機(真 driver 屬 W6A)。"""

    evidence_class = "PLATFORM_ATTESTED"

    def __init__(
        self,
        *,
        executed_artifacts=False,
        build_flags=None,
        written_paths=None,
        root_owned=True,
        fail_at=None,
        residue_ok=True,
        compensation_ok=True,
        parent_overrides=None,
        fetch_digests=None,
    ):
        self.calls: list[str] = []
        self.journal: list[dict] = []
        self.executed_artifacts = executed_artifacts
        self.build_flags = build_flags or {}
        self.written_paths = written_paths
        self.root_owned = root_owned
        self.fail_at = fail_at
        self.residue_ok = residue_ok
        self.compensation_ok = compensation_ok
        self.parent_overrides = parent_overrides or {}
        self.fetch_digests = fetch_digests

    def _maybe_fail(self, label: str) -> None:
        if self.fail_at == label:
            raise RuntimeError(f"injected failure at {label}")

    def journal_transition(self, *, entry):
        self.calls.append("journal:" + entry["state"])
        self.journal.append(dict(entry))

    def verify_staging_parent(self, *, staging_parent):
        self.calls.append("verify_staging_parent")
        self._maybe_fail("verify_staging_parent")
        observed = {
            "device": _STAGING_DEVICE, "inode": _STAGING_INODE, "mode": "0700",
            "owner": "root", "is_symlink": False, "link_count": 2,
        }
        observed.update(self.parent_overrides)
        return observed

    def create_staging_root(self, *, staging_root):
        self.calls.append("create_staging_root")
        self._maybe_fail("create_staging_root")
        self.staging_root = staging_root
        return {"device": _STAGING_DEVICE, "inode": _STAGING_INODE + 1}

    def fetch_pinned_artifacts(self, *, staging_root, pinned_artifacts, fetch_budget):
        self.calls.append("fetch_pinned_artifacts")
        self._maybe_fail("fetch_pinned_artifacts")
        digests = self.fetch_digests or [item["content_digest"] for item in pinned_artifacts]
        return {
            "artifacts": [
                {"locator": item["locator"], "content_digest": digest}
                for item, digest in zip(pinned_artifacts, digests)
            ],
            "executed_artifacts": self.executed_artifacts,
            "bytes_fetched": 12_345,
            "seconds_elapsed": 9,
            "written_paths": self.written_paths
            if self.written_paths is not None
            else [f"{staging_root}/wheels"],
        }

    def build_and_import(self, *, staging_root, build_budget):
        self.calls.append("build_and_import")
        self._maybe_fail("build_and_import")
        flags = {
            "network_access": False, "credential_access": False, "state_access": False,
            "root_executed_dependency_code": False,
        }
        flags.update(self.build_flags)
        return {
            **flags,
            "native_import_proof_digest": "sha256:" + "f" * 64,
            "bytes_written": 54_321,
            "seconds_elapsed": 60,
            "written_paths": [f"{staging_root}/runtime"],
        }

    def freeze_and_rehash_staging(self, *, staging_root):
        self.calls.append("freeze_and_rehash_staging")
        self._maybe_fail("freeze_and_rehash_staging")
        return {
            "root_owned_nonwritable": self.root_owned,
            "device": _STAGING_DEVICE, "inode": _STAGING_INODE + 1,
            "base_runtime_tree_manifest_digest": "sha256:" + "4" * 64,
            "base_runtime_tree_digest": _BASE_TREE,
            "application_bundle_manifest_digest": "sha256:" + "5" * 64,
            "application_bundle_digest": _APP_BUNDLE,
            "launch_bundle_manifest_digest": "sha256:" + "6" * 64,
            "launch_bundle_digest": _LAUNCH_BUNDLE,
        }

    def independent_residue_postcheck(self, *, staging_root, prepare_id, prepare_core_digest):
        self.calls.append("independent_residue_postcheck")
        return {
            "verifier_node": "s2-4-prepare-verifier",
            "zero_residue_outside_staging": self.residue_ok,
            "staging_root_owned_nonwritable": self.root_owned,
            "residue_scan_digest": "sha256:" + "7" * 64,
            "verifier_capture_digest": kit.CAPTURE_DIGEST,
        }

    def compensate_staging(self, *, staging_root):
        self.calls.append("compensate_staging")
        return {
            "task_owned_only": True,
            "staging_delta_removed": self.compensation_ok,
            "staging_absent": self.compensation_ok,
        }

    def trusted_host_time(self):
        self.calls.append("trusted_host_time")
        return kit.NOW


@pytest.fixture()
def signed(tmp_path, monkeypatch):
    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    evidence = kit.terminal_probe_evidence(private_key)
    receipt_digest = evidence["PREPARE_SANDBOX"]["effect_receipt"]["self_digest"]
    return {
        "private_key": private_key,
        "probe_evidence": evidence,
        "intent": _intent(receipt_digest),
        "authorization": kit.authorization(
            private_key, profile_key="prepare", authorization_id=_PREPARE_AUTH_ID
        ),
    }


def _run(signed, driver, **kwargs):
    kwargs.setdefault("now", kit.NOW)
    kwargs.setdefault("clock", kit.frozen_clock())
    kwargs.setdefault("replay_ledger", kit.replay_ledger())
    kwargs.setdefault("probe_evidence", signed["probe_evidence"])
    kwargs.setdefault("pinned_artifacts", deepcopy(_PINNED))
    kwargs.setdefault("artifact_mirror_allowlist", list(kit.MIRROR))
    return prepare.prepare_s2_4_install_bundle(
        kwargs.pop("intent", signed["intent"]),
        kwargs.pop("authorization", signed["authorization"]),
        driver,
        **kwargs,
    )


# ── source lane:driver=None → typed pending,零變更 ─────────────────────────────
def test_source_lane_driver_none_is_pending_with_zero_mutation(signed) -> None:
    verdict = _run(signed, None)
    assert verdict["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert verdict["mutation_performed"] is False
    assert verdict["driver_engaged"] is False
    assert verdict["blocks_apply"] is True
    assert verdict["prepared_bundle"] is None and verdict["effect_receipt"] is None
    assert verdict["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }


def test_missing_authorization_or_ledger_is_typed_rejection_before_any_driver(signed) -> None:
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, authorization=None)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert driver.calls == []
    verdict = _run(signed, driver, replay_ledger=None)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("replay" in reason for reason in verdict["reasons"])
    assert driver.calls == []


@pytest.mark.parametrize("profile_key", ["capability_probe", "apply_aggregate", "pg_migration"])
def test_only_the_prepare_profile_can_authorize_prepare(signed, profile_key) -> None:
    driver = _FakePrepareDriver()
    other = kit.authorization(
        signed["private_key"], profile_key=profile_key,
        authorization_id="sha256:" + "5" * 64,
    )
    verdict = _run(signed, driver, authorization=other)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert driver.calls == []


# ── §10.5 #38 route surface:PREPARE 請求夾帶 APPLY 權限即拒 ────────────────────
@pytest.mark.parametrize("surface", [
    "apply_publish", "persistent_unit_write", "persistent_unit_enable", "persistent_unit_start",
    "daemon_reload", "pg", "migration", "secret", "credential_install", "host_identity",
    "opt_publish", "etc_write", "broker_or_order",
])
def test_prepare_request_carrying_apply_authority_is_rejected(signed, surface) -> None:
    forged = deepcopy(signed["intent"])
    forged["forbidden_surfaces"][surface] = True
    forged["self_digest"] = validator.artifact_self_digest(forged)
    assert prepare.derive_prepare_route_surface_status(forged)["status"] == (
        "PREPARE_ROUTE_SURFACE_REJECTED"
    )
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, intent=forged)
    assert verdict["status"] == "PREPARE_REQUEST_REJECTED"
    assert verdict["mutation_performed"] is False and driver.calls == []


def test_prepare_route_surface_rejects_a_non_prepare_effect_class(signed) -> None:
    forged = deepcopy(signed["intent"])
    forged["route_surface"]["required_effect_class"] = "LEARNING_RUNTIME"
    verdict = prepare.derive_prepare_route_surface_status(forged)
    assert verdict["status"] == "PREPARE_ROUTE_SURFACE_REJECTED"
    assert any("LEARNING_RUNTIME_PREPARE" in reason for reason in verdict["reasons"])


# ── PREPARE_SANDBOX probe 前置(scope 替換/缺席/未綁定即 typed capability 未滿足)──
def test_missing_probe_evidence_is_capability_unsatisfied(signed) -> None:
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, probe_evidence={})
    assert verdict["status"] == "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
    assert driver.calls == []


def test_installed_unit_scope_evidence_cannot_satisfy_prepare(signed, tmp_path) -> None:
    installed = kit.terminal_probe_evidence(signed["private_key"], scope="INSTALLED_UNIT")
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, probe_evidence=installed)
    assert verdict["status"] == "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
    assert driver.calls == []


def test_probe_receipt_digest_must_bind_the_supplied_receipt(signed) -> None:
    forged = _intent("sha256:" + "9" * 64)
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, intent=forged)
    assert verdict["status"] == "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"
    assert driver.calls == []


# ── 硬邊界 4:raw ingress 全拒 ──────────────────────────────────────────────────
@pytest.mark.parametrize("payload", [
    [{"locator": "x", "content_digest": "sha256:" + "a" * 64, "shell": "rm -rf /"}],
    [{"locator": "x", "content_digest": "sha256:" + "a" * 64, "sql": "DROP TABLE learning.x"}],
    [{"locator": "x", "content_digest": "sha256:" + "a" * 64, "unit_text": "[Service]\n"}],
    [{"locator": "x", "content_digest": "sha256:" + "a" * 64, "target_root": "/opt/anything"}],
    [{"locator": "x", "content_digest": "sha256:" + "a" * 64, "secret": "hunter2"}],
])
def test_caller_raw_ingress_is_rejected_before_any_driver(signed, payload) -> None:
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, pinned_artifacts=payload)
    assert verdict["status"] == "PREPARE_REQUEST_REJECTED"
    assert any("raw ingress" in reason for reason in verdict["reasons"])
    assert driver.calls == []


@pytest.mark.parametrize("kwarg", [
    "shell", "command", "sql", "unit_text", "staging_root", "target_root", "secret", "password",
])
def test_prepare_entrypoint_has_no_raw_ingress_parameter(kwarg) -> None:
    """最強形式的拒絕:這些參數在 PREPARE ABI 上**根本不存在**(TypeError)。"""

    import inspect

    assert kwarg not in inspect.signature(prepare.prepare_s2_4_install_bundle).parameters
    with pytest.raises(TypeError):
        prepare.prepare_s2_4_install_bundle(None, None, None, **{kwarg: "injected"})


def test_staging_root_is_derived_never_supplied() -> None:
    prepare_id = "s2-4-prepare-" + "a" * 64
    assert prepare.prepared_staging_root(prepare_id) == (
        "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared/" + prepare_id
    )
    with pytest.raises(prepare.PrepareContractError):
        prepare.prepared_staging_root("/opt/anything")
    with pytest.raises(prepare.PrepareContractError):
        prepare.build_prepare_core(
            staging_parent_path="/tmp/worker-chosen", staging_parent_device=1,
            staging_parent_inode=2, max_bytes=1, max_seconds=1, max_fetch_bytes=1,
            max_fetch_seconds=1, max_artifacts=1, max_build_bytes=1, max_build_seconds=1,
            source_head=kit.SOURCE_HEAD, target_host=kit.HOST, created_at=kit.ISSUED,
        )


# ── 成功路徑:PREPARED + 中央閘可驗的 bundle/receipt ────────────────────────────
def test_prepared_bundle_and_receipt_are_centrally_valid(signed) -> None:
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver)
    assert verdict["status"] == "PREPARED", verdict["reasons"]
    assert verdict["mutation_performed"] is True and verdict["driver_engaged"] is True
    bundle, receipt = verdict["prepared_bundle"], verdict["effect_receipt"]
    assert validator.validate_aiml_artifact(bundle) == []
    assert validator.validate_aiml_artifact(receipt) == []
    assert receipt["terminal_status"] == "PREPARED"
    assert receipt["prepared_install_bundle_digest"] == bundle["self_digest"]
    # bundle 不反綁 receipt/journal(§5.1 #2 的方向性)。
    assert "prepare_effect_receipt_digest" not in bundle
    assert receipt["production_authority_flags"]["production_apply_performed"] is False
    # §5.2:PREPARING 是第一筆 WAL,且在 create_staging_root 之前。
    assert driver.calls[0] == "journal:PREPARING"
    assert driver.calls.index("journal:PREPARING") < driver.calls.index("create_staging_root")
    # 四個 §8.1 內容身分兩兩相異且落在 bundle。
    assert len({
        bundle["base_runtime_tree_digest"], bundle["application_bundle_digest"],
        bundle["launch_bundle_digest"], bundle["native_import_proof_digest"],
    }) == 4
    # 消費者側再導出可用。
    assert prepare.derive_prepared_bundle_status(bundle, receipt, now=kit.NOW)["status"] == (
        "PREPARED_BUNDLE_VALID"
    )


def test_expired_prepared_bundle_is_invalid_for_apply(signed) -> None:
    verdict = _run(signed, _FakePrepareDriver())
    bundle, receipt = verdict["prepared_bundle"], verdict["effect_receipt"]
    late = (kit.ANCHOR.replace(year=2031)).isoformat()
    result = prepare.derive_prepared_bundle_status(bundle, receipt, now=late)
    assert result["status"] == "PREPARED_BUNDLE_INVALID"
    assert any("expired" in reason for reason in result["reasons"])


def test_swapped_prepare_receipt_breaks_the_bundle_lineage(signed) -> None:
    verdict = _run(signed, _FakePrepareDriver())
    bundle, receipt = verdict["prepared_bundle"], verdict["effect_receipt"]
    forged = deepcopy(receipt)
    forged["prepared_install_bundle_digest"] = "sha256:" + "0" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = prepare.derive_prepared_bundle_status(bundle, forged, now=kit.NOW)
    assert result["status"] == "PREPARED_BUNDLE_INVALID"


# ── §10.5 #33:sandbox 能力斷言 ────────────────────────────────────────────────
def test_fetch_that_executes_an_artifact_fails_and_compensates(signed) -> None:
    driver = _FakePrepareDriver(executed_artifacts=True)
    verdict = _run(signed, driver)
    assert verdict["status"] == "PREPARE_FAILED"
    assert any("executed or imported" in reason for reason in verdict["reasons"])
    assert verdict["rollback"]["status"] == "CLEANED_EXACT"
    assert "compensate_staging" in driver.calls


@pytest.mark.parametrize("flag", [
    "network_access", "credential_access", "state_access", "root_executed_dependency_code",
])
def test_build_sandbox_violations_fail_and_compensate(signed, flag) -> None:
    driver = _FakePrepareDriver(build_flags={flag: True})
    verdict = _run(signed, driver)
    assert verdict["status"] == "PREPARE_FAILED"
    assert any("PREPARE sandbox violation" in reason for reason in verdict["reasons"])
    assert verdict["rollback"]["status"] == "CLEANED_EXACT"


def test_hash_pin_mismatch_fails_before_any_publication(signed) -> None:
    driver = _FakePrepareDriver(fetch_digests=["sha256:" + "0" * 64, "sha256:" + "b" * 64])
    verdict = _run(signed, driver)
    assert verdict["status"] == "PREPARE_FAILED"
    assert any("pinned hash" in reason for reason in verdict["reasons"])


@pytest.mark.parametrize("path", [
    "/opt/arcane-equilibrium/aiml/runtimes/x",
    "/etc/credstore.encrypted/aiml-engine-scanner-pg-dsn",
    "/etc/systemd/system/arcane-equilibrium-aiml-engine-scanner.service",
    "/etc/arcane-equilibrium/aiml/engine-scanner/candidate-policy.json",
])
def test_prepare_cannot_publish_outside_its_staging_root(signed, path) -> None:
    driver = _FakePrepareDriver(written_paths=[path])
    verdict = _run(signed, driver)
    assert verdict["status"] == "PREPARE_FAILED"
    assert any("forbidden publication root" in reason or "outside its task-owned" in reason
               for reason in verdict["reasons"])
    assert verdict["rollback"]["status"] == "CLEANED_EXACT"


def test_sandbox_contract_binds_both_subphase_properties(signed) -> None:
    contract = prepare.prepare_sandbox_contract(artifact_mirror_allowlist=list(kit.MIRROR))
    assert contract["fetch_bytes"]["may_execute_artifacts"] is False
    assert contract["build_and_import"]["network_access"] is False
    assert contract["build_and_import"]["root_executes_dependency_code"] is False
    assert contract["build_and_import"]["properties"]["PrivateNetwork"] == "yes"
    assert contract["fetch_bytes"]["properties"]["IPAddressAllow"] == "203.0.113.0/24"
    # mirror allowlist 改變 → sandbox 契約 digest 必變(egress 上限 receipt-bound)。
    other = prepare.prepare_sandbox_contract_digest(artifact_mirror_allowlist=["198.51.100.0/24"])
    assert other != prepare.prepare_sandbox_contract_digest(
        artifact_mirror_allowlist=list(kit.MIRROR)
    )


# ── §5.2 crash matrix / precheck ───────────────────────────────────────────────
def test_crash_before_staging_creation_leaves_zero_mutation(signed) -> None:
    driver = _FakePrepareDriver(fail_at="create_staging_root")
    verdict = _run(signed, driver)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["mutation_performed"] is False


@pytest.mark.parametrize("stage", [
    "fetch_pinned_artifacts", "build_and_import", "freeze_and_rehash_staging",
])
def test_crash_after_staging_creation_compensates_the_task_owned_delta(signed, stage) -> None:
    driver = _FakePrepareDriver(fail_at=stage)
    verdict = _run(signed, driver)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback"]["status"] == "CLEANED_EXACT"
    assert verdict["rollback"]["task_owned_only"] is True
    assert "compensate_staging" in driver.calls


def test_failed_compensation_is_recovery_required(signed) -> None:
    driver = _FakePrepareDriver(fail_at="build_and_import", compensation_ok=False)
    verdict = _run(signed, driver)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["rollback"]["status"] == "NOT_CLEANED"


@pytest.mark.parametrize("override", [
    {"is_symlink": True}, {"owner": "nobody"}, {"mode": "0777"},
    {"device": 1}, {"inode": 1}, {"link_count": 3},
])
def test_hostile_staging_parent_fails_before_mutation(signed, override) -> None:
    driver = _FakePrepareDriver(parent_overrides=override)
    verdict = _run(signed, driver)
    assert verdict["status"] == "PRECHECK_FAILED"
    assert verdict["mutation_performed"] is False
    assert "create_staging_root" not in driver.calls


def test_residue_postcheck_failure_is_recovery_required(signed) -> None:
    driver = _FakePrepareDriver(residue_ok=False)
    verdict = _run(signed, driver)
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert verdict["postcheck"]["status"] == "FAIL"
    assert "compensate_staging" in driver.calls


def test_applier_cannot_be_its_own_verifier(signed) -> None:
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, applier_node="s2-4-prepare-verifier")
    assert verdict["status"] == "RECOVERY_REQUIRED"
    assert any("verifier_node must differ" in reason for reason in verdict["reasons"])


def test_expired_intent_is_rejected_before_any_driver(signed) -> None:
    driver = _FakePrepareDriver()
    verdict = _run(signed, driver, now=(kit.ANCHOR.replace(year=2031)).isoformat())
    assert verdict["status"] in {"PREPARE_REQUEST_REJECTED", "AUTHORIZATION_REJECTED",
                                 "HOST_NETWORK_SANDBOX_CAPABILITY_UNSATISFIED"}
    assert driver.calls == []


def test_prepare_abi_projection_is_stable_and_complete() -> None:
    projection = prepare.prepare_abi_projection()
    assert projection["prepare_route_class"] == "s2_4_prepare_intent"
    assert projection["prepare_staging_parent"] == (
        "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared"
    )
    assert projection["prepare_sandbox_contract_digest"] is not None
    assert "EXTERNAL_VERIFICATION_PENDING" in projection["prepare_typed_statuses"]
    assert projection == prepare.prepare_abi_projection()
