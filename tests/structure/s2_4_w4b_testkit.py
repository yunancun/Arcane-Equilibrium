"""S2.4(WP4·W4b)aggregate 交易 focused 測試的共用腳手架(丟棄式,零主機接觸)。

刻意**不是** ``conftest.py``:各測試檔顯式 import 這些純函式/fake。時間全部錨在
:mod:`s2_4_w3b_testkit` 的凍結常量上(無 wall clock,故無日期腐化)。

honesty:此處一切 driver/verifier/檔案系統都是 in-memory fake,``evidence_class`` 一律
``STRUCTURAL_ONLY``——它們只證契約層行為,**絕不**認證任何 runtime,也因此永遠換不到
``APPLIED_INACTIVE``(那需要 W6B 的平台背書)。
"""
from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
PROGRAM_CODE = ROOT / "program_code"
for _candidate in (HELPERS, ML_ROOT, PROGRAM_CODE, ROOT / "tests/structure"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_4_apply as apply_mod  # noqa: E402
import agent_governance_s2_4_credential as credential  # noqa: E402
import agent_governance_s2_4_install_driver as runner  # noqa: E402
import agent_governance_s2_4_journal as journal  # noqa: E402
import agent_governance_s2_4_lock as lock  # noqa: E402
import agent_governance_s2_4_prepare as prepare  # noqa: E402
import agent_governance_s2_4_render as render  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
from test_agent_governance_s2_4_apply import (  # noqa: E402
    _FakeCredentialDriver, _FakeEngineScannerDriver, _FakePgDriver, _FakeRuntimeDriver,
    _public_pre_state,
)
from test_agent_governance_s2_4_host_identity import _FakeHostIdentityDriver  # noqa: E402
from test_agent_governance_s2_4_journal import FakeDurableFs  # noqa: E402
from test_agent_governance_s2_4_lock import FakeLockDriver  # noqa: E402

BLOB_DIGEST = "sha256:" + "d" * 64
APPLY_BUDGET = {term: 30 for term in runner._permit.APPLY_TTL_BUDGET_TERMS}
REMAINING_TTLS = {term: 900 for term in runner._permit.APPLY_TTL_BOUND_TERMS}
CAPTURE = kit.CAPTURE_DIGEST


# ── 五 row 的 unbound intent 主體(install_plan_digest 由 plan builder 重綁)───────
def unbound_component_intents(*, guard: dict[str, Any], attestation: dict[str, Any],
                              bundle: dict[str, Any], prepare_receipt: dict[str, Any],
                              policy_config_hash: str, unit_text: str) -> dict[str, Any]:
    targets = {
        field: apply_mod.install_target_root(identity_field=field, digest=bundle[field])
        for field in apply_mod.INSTALL_ROOTS
    }
    target_manifest = {
        "targets": targets,
        "immutable_modes": dict(apply_mod.IMMUTABLE_TREE_MODES),
        "base_runtime_tree_manifest_digest": bundle["base_runtime_tree_manifest_digest"],
        "application_bundle_manifest_digest": bundle["application_bundle_manifest_digest"],
        "launch_bundle_manifest_digest": bundle["launch_bundle_manifest_digest"],
    }
    unit_manifests = {
        "unit_digest": validator.canonical_digest(unit_text),
        "policy_config_hash": policy_config_hash,
        "guard_digest": guard["self_digest"],
        "evidence_directory": apply_mod.CANDIDATE_EVIDENCE_DIR,
    }
    fields = {
        "HOST_IDENTITY_INSTALL": {
            "uid_gid_directory_manifest_digest": validator.canonical_digest(
                apply_mod.build_uid_gid_directory_manifest(uid=kit.UID, gid=kit.GID)
            ),
        },
        "PG_ROLE_ACL_MIGRATION": {
            "topology_attestation_digest": attestation["self_digest"],
            "acl_manifest_digest": kit.PG_ACL_MANIFEST["self_digest"],
            "pg_migration_permit_digest": "sha256:" + "6" * 64,
            "admin_handle_descriptor_digest": "sha256:" + "7" * 64,
        },
        "CREDENTIAL_INSTALL": {
            "credential_name": credential.CREDENTIAL_UNIT_NAME,
            "encrypted_blob_digest": BLOB_DIGEST,
            "host_identity_digest": validator.canonical_digest(
                apply_mod.host_identity_desired_state(uid=kit.UID, gid=kit.GID)
            ),
        },
        "LEARNING_RUNTIME": {
            "prepare_effect_receipt_digest": prepare_receipt["self_digest"],
            "base_app_launch_target_manifest_digest": validator.canonical_digest(
                target_manifest
            ),
        },
        "ENGINE_SCANNER": {
            "unit_policy_evidence_manifest_digest": validator.canonical_digest(unit_manifests),
            "inactive_post_state_digest": validator.canonical_digest(
                apply_mod.INACTIVE_UNIT_POSTSTATE
            ),
        },
    }
    return {
        name: apply_mod.build_component_effect_intent(
            component_effect_class=name,
            # placeholder:真值由 build_s2_4_install_plan 重綁成 plan 的 core_digest。
            install_plan_digest="sha256:" + "0" * 64,
            pre_state_digest=validator.canonical_digest({"row": name, "pre_state": "absent"}),
            required_intent_fields=values, expires_at=kit.EXPIRES,
        )
        for name, values in fields.items()
    }, targets


# ── PREPARE / probe 證據(以 W3a/W3b 葉真跑一次,注入 driver)────────────────────
def prepare_evidence(private_key: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from test_agent_governance_s2_4_prepare import (
        _FakePrepareDriver, _PINNED, _intent as _p_intent,
    )

    probe = kit.terminal_probe_evidence(private_key)
    prepare_intent = _p_intent(probe["PREPARE_SANDBOX"]["effect_receipt"]["self_digest"])
    verdict = prepare.prepare_s2_4_install_bundle(
        prepare_intent,
        kit.authorization(
            private_key, profile_key="prepare",
            payload_binding=prepare.prepare_permit_payload_binding(prepare_intent),
        ),
        _FakePrepareDriver(),
        now=kit.NOW, clock=kit.frozen_clock(), replay_ledger=kit.replay_ledger(),
        probe_evidence=probe, pinned_artifacts=deepcopy(_PINNED),
        artifact_mirror_allowlist=list(kit.MIRROR),
    )
    assert verdict["status"] == "PREPARED", verdict["reasons"]
    return probe, verdict["prepared_bundle"], verdict["effect_receipt"]


def installed_unit_probe_evidence(private_key: Path) -> dict[str, Any]:
    return kit.terminal_probe_evidence(private_key, scope="INSTALLED_UNIT")


LEDGER_BASENAME = lock.REPLAY_LEDGER_PATH.rsplit("/", 1)[-1]
INSTALL_JOURNAL_PARENT_MODE = journal.JOURNAL_PARENT_MODE


class CountingFs(FakeDurableFs):
    """在**第 N 次** durable 寫入短寫的檔案系統 fake(逐一針對某個落盤 effect edge)。"""

    def __init__(self, *, fail_write_at: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.fail_write_at = fail_write_at
        self.write_count = 0

    def write_bytes(self, *, fd, payload):
        self.write_count += 1
        if self.fail_write_at is not None and self.write_count == self.fail_write_at:
            self.calls.append("write_bytes")
            self.temp_buffers[fd] = bytes(payload)
            return len(payload) - 1
        return super().write_bytes(fd=fd, payload=payload)


class CrashingClock:
    """在指定 label 拋 :class:`agent_governance_s2_4_journal.JournalCrash` 的注入器。"""

    def __init__(self, label: str) -> None:
        self.label = label
        self.seen: list[str] = []

    def __call__(self, label: str) -> None:
        self.seen.append(label)
        if label == self.label:
            raise journal.JournalCrash(label)


def prior_lineage_ledger() -> dict[str, Any]:
    """§5.1 前導 lineage 的消費紀錄(兩個 probe + PREPARE 各自消費過自己的 permit)。

    APPLY 讀到的 durable head **必須**非空:設計的次序是 probe → PREPARE → probe → 簽 plan →
    APPLY,每一段都 durable 消費過自己的 permit。此 fixture 因此比「空 ledger」忠實得多。
    """

    ledger = lock.empty_replay_ledger()
    entries = [
        {
            "authorization_id": "sha256:" + digit * 64,
            "self_digest": "sha256:" + (digit * 63 + "a"),
            "profile_identity": profile,
        }
        for digit, profile in (
            ("1", "aiml-s2-capability-probe-operator-v1"),
            ("2", "aiml-s2-install-prepare-operator-v1"),
            ("3", "aiml-s2-capability-probe-operator-v1"),
        )
    ]
    return lock.append_replay_entries(ledger, entries, consumed_at=kit.ISSUED)


def seed_prior_lineage_ledger(fs: Any) -> dict[str, Any]:
    """把前導 lineage 的 ledger 以 canonical bytes 種到 in-memory 檔案系統。"""

    ledger = prior_lineage_ledger()
    fs.files[LEDGER_BASENAME] = validator._canonical_bytes(ledger)
    return ledger


# ── aggregate driver fake ──────────────────────────────────────────────────────
class FakeAggregateDriver:
    """注入的 :class:`agent_governance_s2_4_install_driver.AggregateInstallDriver` 實作。

    刻意**沒有** probe/enable/start 面;``evidence_class`` 一律 ``STRUCTURAL_ONLY``
    (in-memory fixture 絕不冒充平台背書)。
    """

    evidence_class = "STRUCTURAL_ONLY"

    def __init__(
        self,
        *,
        row_drivers: dict[str, Any],
        fs: Any,
        lock_fake: Any,
        postcheck_flags: dict[str, bool] | None = None,
        verifier_node: str = "s2-4-install-verifier",
        compensation: dict[str, Any] | None = None,
        compensation_raises: tuple[str, ...] = (),
        # 成功路徑的觀測:unit 已安裝且 loaded/disabled/inactive(補償後轉為 absent)。
        unit_state: Any = "inactive",
        trusted_time: str = kit.NOW,
    ) -> None:
        self.row_drivers = dict(row_drivers)
        self._fs = fs
        self._lock = lock_fake
        self.postcheck_flags = dict(postcheck_flags or {})
        self.verifier_node = verifier_node
        self.compensation = dict(compensation or {})
        self.compensation_raises = set(compensation_raises)
        self.unit_state = unit_state
        self.trusted_time = trusted_time
        self.calls: list[str] = []
        self.compensated: list[str] = []

    def lock_driver(self):
        self.calls.append("lock_driver")
        return self._lock

    def file_driver(self):
        self.calls.append("file_driver")
        return self._fs

    def row_driver(self, *, component_effect_class):
        return self.row_drivers[component_effect_class]

    def compensate_component_row(
        self, *, component_effect_class, plan_id, per_row_rollback_digest, ownership_verified
    ):
        self.calls.append(f"compensate:{component_effect_class}")
        if component_effect_class in self.compensation_raises:
            raise RuntimeError("injected compensation failure")
        self.compensated.append(component_effect_class)
        assert per_row_rollback_digest == runner.per_row_rollback_digest(
            plan_id=plan_id, component_effect_class=component_effect_class
        )
        # 真主機上,逆向 op 就是把該 row 的 task-owned delta 移除;故該 row 的**獨立** verifier
        # 之後必須觀測到 applied 狀態已不存在。fake 以同一條 call log 反映該事實
        # (``remove`` 前綴 = PostcheckMixin 判斷「現在是補償之後」的訊號)。
        row_driver = self.row_drivers.get(component_effect_class)
        if row_driver is not None and hasattr(row_driver, "calls"):
            row_driver.calls.append(f"remove:{component_effect_class}")
        default = {
            "compensated": True, "reobserved": True, "observer_role_preserved": True,
            "daemon_reload_reasserted": True, "hba_reload_reasserted": True,
        }
        default.update(self.compensation.get(component_effect_class, {}))
        # 補償跑過之後,已安裝的 unit 必須不存在(逆序補償把它移除了)。
        if component_effect_class == "ENGINE_SCANNER":
            self.unit_state = "absent"
        return default

    def observe_installed_unit_state(self):
        self.calls.append("observe_installed_unit_state")
        if self.unit_state == "absent":
            return None
        if self.unit_state == "inactive":
            return {"loaded": True, "disabled": True, "inactive": True}
        if self.unit_state == "active":
            return {"loaded": True, "disabled": False, "inactive": False, "active": True,
                    "enabled": True}
        return self.unit_state

    def aggregate_independent_postcheck(self, *, plan_id, plan_core_digest, applier_node):
        self.calls.append("aggregate_independent_postcheck")
        flags = {
            "probe_lineage_verified": True, "prepare_lineage_verified": True,
            "plan_lineage_verified": True, "idempotency_verified": True,
            "pre_state_lineage_verified": True, "all_apply_rows_satisfied": True,
        }
        flags.update(self.postcheck_flags)
        return {
            "verifier_node": self.verifier_node,
            "verifier_capture_digest": CAPTURE,
            **flags,
        }

    def trusted_host_time(self):
        return self.trusted_time


# ── 完整的一筆交易的所有輸入 ────────────────────────────────────────────────────
class Fixture:
    """一筆 aggregate 交易的全部輸入(plan / 兩張 permit / 五 row payload / 兩個 probe receipt)。"""

    def __init__(
        self, tmp_path: Path, monkeypatch, *, fs: Any = None, **driver_overrides: Any
    ) -> None:
        private_key, public_key, fingerprint = kit.mint_key(tmp_path)
        kit.install_pinned_key(monkeypatch, public_key, fingerprint)
        self.private_key = private_key
        probe, bundle, prepare_receipt = prepare_evidence(private_key)
        installed = installed_unit_probe_evidence(private_key)
        self.probe_receipts = {
            "PREPARE_SANDBOX": probe["PREPARE_SANDBOX"]["effect_receipt"],
            "INSTALLED_UNIT": installed["INSTALLED_UNIT"]["effect_receipt"],
        }
        self.prepared_bundle = bundle
        self.prepare_receipt = prepare_receipt
        self.attestation = kit.topology_attestation()
        self.guard = kit.topology_guard(self.attestation)
        self.unit_text = kit.rendered_unit()
        policy_bytes, policy_hash = render.render_candidate_policy(
            ROOT / apply_mod.CANDIDATE_POLICY_TEMPLATE_REL, dict(kit.POLICY_BUDGETS)
        )
        del policy_bytes
        unbound, self.targets = unbound_component_intents(
            guard=self.guard, attestation=self.attestation, bundle=bundle,
            prepare_receipt=prepare_receipt, policy_config_hash=policy_hash,
            unit_text=self.unit_text,
        )
        built = runner.build_s2_4_install_plan(
            component_intents=unbound,
            prepare_receipt_digest=prepare_receipt["self_digest"],
            topology_pre_digest=self.attestation["self_digest"],
            hba_delta_digest="sha256:" + "b" * 64,
            source_head=kit.SOURCE_HEAD, target_host=kit.HOST,
            created_at=kit.ISSUED, expires_at=kit.EXPIRES,
        )
        self.plan = built["plan"]
        self.component_intents = built["component_intents"]
        self.authorization_set = self._permits()
        self.fs = fs if fs is not None else FakeDurableFs()
        seed_prior_lineage_ledger(self.fs)
        self.lock_fake = FakeLockDriver()
        self.row_drivers = {
            "HOST_IDENTITY_INSTALL": _FakeHostIdentityDriver(),
            "PG_ROLE_ACL_MIGRATION": _FakePgDriver(),
            "CREDENTIAL_INSTALL": _FakeCredentialDriver(blob_digest=BLOB_DIGEST),
            "LEARNING_RUNTIME": _FakeRuntimeDriver(rehash={
                field: bundle[field] for field in apply_mod.INSTALL_ROOTS
            }),
            "ENGINE_SCANNER": _FakeEngineScannerDriver(),
        }
        self.driver = FakeAggregateDriver(
            row_drivers=self.row_drivers, fs=self.fs, lock_fake=self.lock_fake,
            **driver_overrides,
        )

    def _permits(self) -> dict[str, Any]:
        receipt = self.probe_receipts["INSTALLED_UNIT"]
        aggregate_binding = runner.aggregate_permit_payload_binding(
            self.plan, installed_unit_probe_receipt=receipt,
            issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
        )
        pg_binding = runner.pg_permit_payload_binding(
            self.plan, component_intents=self.component_intents,
            installed_unit_probe_receipt=receipt,
            issued_at=kit.ISSUED, expires_at=kit.EXPIRES,
        )
        return {
            "apply_aggregate": kit.authorization(
                self.private_key, profile_key="apply_aggregate",
                payload_binding=aggregate_binding,
            ),
            "pg_migration": kit.authorization(
                self.private_key, profile_key="pg_migration", payload_binding=pg_binding,
            ),
        }

    def row_payloads(self) -> dict[str, Any]:
        broker = credential.SecretBroker(operation_id="w4b-op")
        pg_handle, dsn_handle = broker.mint_first_provisioning_handles()
        return {
            "HOST_IDENTITY_INSTALL": {
                "uid_gid_directory_manifest": apply_mod.build_uid_gid_directory_manifest(
                    uid=kit.UID, gid=kit.GID
                ),
            },
            "PG_ROLE_ACL_MIGRATION": {
                "acl_manifest": deepcopy(kit.PG_ACL_MANIFEST),
                "topology_attestation": self.attestation,
                "expected_topology": kit.topology_expected(self.attestation),
                "secret_handle": pg_handle,
                "operation_id": "w4b-op",
            },
            "CREDENTIAL_INSTALL": {"dsn_handle": dsn_handle, "operation_id": "w4b-op"},
            "LEARNING_RUNTIME": {
                "prepared_bundle": self.prepared_bundle,
                "prepare_effect_receipt": self.prepare_receipt,
            },
            "ENGINE_SCANNER": {
                "unit_fields": dict(kit.UNIT_FIELDS),
                "candidate_policy_budgets": dict(kit.POLICY_BUDGETS),
                "topology_guard": self.guard,
            },
        }

    def apply(self, **overrides: Any) -> dict[str, Any]:
        payload = {
            "component_intents": self.component_intents,
            "row_payloads": self.row_payloads(),
            "probe_receipts": self.probe_receipts,
            "prepare_effect_receipt": self.prepare_receipt,
            "apply_budget": dict(APPLY_BUDGET),
            "remaining_ttls": dict(REMAINING_TTLS),
            "now": kit.NOW,
            "clock": kit.frozen_clock(),
        }
        driver = overrides.pop("driver", self.driver)
        authorization_set = overrides.pop("authorization_set", self.authorization_set)
        payload.update(overrides)
        return runner.apply_s2_4_install_plan(
            self.plan, authorization_set, driver, **payload
        )

    def persisted_install_journal(self) -> dict[str, Any] | None:
        basename = journal.install_journal_path(self.plan["plan_id"]).rsplit("/", 1)[-1]
        payload = self.fs.files.get(basename)
        if payload is None:
            return None
        verdict = journal.verify_journal_bytes(payload, journal_path=basename)
        assert verdict["status"] == journal.JOURNAL_STATUS_LOADED, verdict["reasons"]
        return verdict["journal"]

    def persisted_replay_ledger(self) -> dict[str, Any] | None:
        basename = lock.REPLAY_LEDGER_PATH.rsplit("/", 1)[-1]
        payload = self.fs.files.get(basename)
        if payload is None:
            return None
        import json as _json

        return _json.loads(payload.decode("utf-8"))
