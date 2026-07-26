"""S2.4(WP4·W4)wave-exit 綁定的 code-owned 投影葉模組(§10.3 W4 row)。

鏡 :mod:`aiml_gate_receipt_wave_w3`:facade 逐名 re-export,``derive_wave_exit_status``
的 W4 分支委派本葉。W4a 面(permit ↔ plan 綁定、replay ledger append、install lock、
三本 WAL journal、§9 TTL 預算、獨立補償後 postcheck)於此折成「活」再導出,任何 ABI/行為
漂移都必然弄破 W4 wave-exit:

- ``_W4_OWNED_PATHS``:三個新 governed 葉(permit/journal/lock)、W4 發射葉、wave 投影葉、
  facade 與 contracts 葉、被 W4a 改動的四支 route 葉、授權 schema,以及六支 focused 測試;
- ``w4_exported_abi_projection``:§10.2/§10.3 W4 exit 的 exported-ABI 投影,折入七個活面——
  ``authorization_id`` 由 payload 導出(intent 替換必被拒)、replay ledger 的 consume-once /
  idempotent-replay 裁決、install lock 的 exact 取得契約與競爭/hostile 路徑、三本 journal 的
  路徑導出與 durability 契約、write-ahead crash 三窗、§9 三條 TTL 不等式、以及
  ``COMPENSATED_EXACT`` 必須來自**獨立** verifier 的補償後再觀測;
- W4 的 PASS 另需前導 W3 wave-exit「連同其 W2/W1/W0/admission 鏈」一起再導出 PASS
  (predecessor 物件鏈驗在 facade 的 ``derive_wave_exit_status``)。

receipt 只帶 evidence,PASS 恆由中央 validator 導出;通過「不」認證任何 runtime——
九 authority / production_apply_performed / running_attested 恆 false。
facade 依 2000 行治理拆分規約「只」經 schema_core.resolve_facade() 取得;governed helper
模組於函式內延遲匯入(保 monkeypatch 縫、避免 import 循環)。
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
_HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
if str(_HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(_HELPER_DIR))
_PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
if str(_PROGRAM_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE_DIR))

from aiml_gate_receipt_schema_core import canonical_digest, resolve_facade  # noqa: E402

_SCHEMA_DIR_REL = "program_code/ml_training/schemas/aiml_gate_receipts"
# §10.1 + §10.1.1(2026-07-26 PM path-scope amendment):W4a 的 owned-path 投影。
_W4_OWNED_PATHS = tuple(sorted((
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_apply.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_component.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_host_identity.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
    # W4b 的 aggregate 交易葉(§10.1 明列)與其 §10.1.1 拆出的 §5.2 recovery/wiring 葉。
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_install_driver.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_reconcile.py",
    # W4a 的三個新 governed 葉(§5.2 durable WAL / install lock + §9.1 replay append / §9 預算)。
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_journal.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_lock.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_permit.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_prepare.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_probe.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_w4_emit.py",
    "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w3.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w4.py",
    # W4 的 wave 投影葉進入 consumer runtime import 閉包的宣告面(§8.1 allowlist)。
    "program_code/ml_training/application_bundle_runtime_closure_v1.json",
    # PERMIT_PLAN_BINDING 的 additive schema 面(payload_binding)。
    f"{_SCHEMA_DIR_REL}/s2_4_operator_authorization_v1.schema.json",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    "tests/structure/s2_4_w3b_testkit.py",
    # W4b 的共用腳手架與三支 focused 測試(aggregate 交易 / crash matrix / §5.3 逐列)。
    "tests/structure/s2_4_w4b_testkit.py",
    "tests/structure/test_agent_governance_s2_4_apply.py",
    "tests/structure/test_agent_governance_s2_4_apply_pg_disposable.py",
    "tests/structure/test_agent_governance_s2_4_crash_matrix.py",
    "tests/structure/test_agent_governance_s2_4_host_identity.py",
    "tests/structure/test_agent_governance_s2_4_install.py",
    "tests/structure/test_agent_governance_s2_4_install_driver.py",
    # W3 的 wave 測試在 W4a 之後把「未實作 wave」的邊界從 W4 推到 W5。
    "tests/structure/test_agent_governance_s2_4_install_w3.py",
    "tests/structure/test_agent_governance_s2_4_install_w4.py",
    "tests/structure/test_agent_governance_s2_4_journal.py",
    "tests/structure/test_agent_governance_s2_4_lock.py",
    "tests/structure/test_agent_governance_s2_4_permit.py",
    "tests/structure/test_agent_governance_s2_4_pre_state_matrix.py",
    "tests/structure/test_agent_governance_s2_4_prepare.py",
    "tests/structure/test_agent_governance_s2_4_probe.py",
)))
# §10.2/§10.3 W4 exported-ABI 的 code-owned 骨架(live 部分見 w4_exported_abi_projection)。
_W4_EXPORTED_ABI = {
    "wave": "W4",
    "wave_scope": (
        "the aggregate install transaction. W4a: probe/PREPARE/APPLY permit-to-plan "
        "binding, the replay-ledger append side, the exact install-lock acquisition "
        "contract, the three §5.2 durable WAL journals with write-ahead ordering and "
        "deterministic reconcile, the §9 TTL budget inequalities, and the independent "
        "post-compensation residue postcheck. W4b: the §6/§10.2 top-level "
        "apply_s2_4_install_plan transaction — plan validation, the §10.5 #24 aggregate "
        "inputs and success predicate, the field-by-field aggregate/PG permit payload "
        "comparison, the §5.1 acyclic plan-to-intent binding, consume-once under the "
        "acquired lock, the five §5.1 rows as write-ahead steps, §5.2 startup "
        "reconciliation, the §5.4 ownership-aware reverse compensation chain, the "
        "independent aggregate postcheck and the immutable install effect receipt"
    ),
    "typed_failures": [
        "AUTHORIZATION_REJECTED",
        "CANDIDATE_POLICY_CONFIGURATION_REQUIRED",
        "EXTERNAL_VERIFICATION_PENDING",
        "HOST_CREDENTIAL_CAPABILITY_UNSATISFIED",
        "INSTALL_LOCK_HELD",
        "JOURNAL_CORRUPT_RECOVERY_REQUIRED",
        "PG_TOPOLOGY_UNPROVEN",
        "POSTCHECK_FAILED_ROLLED_BACK",
        "PREEXISTING_UNOWNED_STATE",
        "PREPARED_BUNDLE_INVALID",
        "PRECHECK_FAILED",
        "PRESTATE_MISMATCH",
        "RECOVERY_REQUIRED",
        "TTL_BUDGET_EXCEEDED",
    ],
    "permit_plan_binding_contract": (
        "authorization_id = canonical_digest({domain, profile_identity, "
        "signature_namespace, payload_fields, payload_binding}); payload_binding carries the "
        "exact VALUE of every §9.1 payload field except the self-referential authorization_id. "
        "Layer (a) re-derives the id from the permit's own payload unconditionally; layer (b) "
        "compares payload_binding against values the consuming gate re-derives independently "
        "from the probe/prepare intent or the plan reference. One signed permit therefore "
        "authorizes exactly one intent/plan inside its TTL (§10.5 #36)"
    ),
    "replay_append_contract": (
        "consumption entries are appended hash-chained and fsynced only under the exclusive "
        "install lock, decided against the durable ledger head read under that lock; the same "
        "key with the same plan binding is an idempotent replay that appends nothing and "
        "re-executes nothing, while the same key with a different plan/permit digest is "
        "AUTHORIZATION_REJECTED (§10.5 #8)"
    ),
    "install_lock_contract": (
        "directory FD with O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC plus device/inode/mode binding, "
        "openat(O_NOFOLLOW|O_CREAT|O_CLOEXEC, 0600), fstat proving a root-owned regular file "
        "of mode 0600 with link count one on the expected device, then non-blocking exclusive "
        "flock; the lock is never unlinked; contention is INSTALL_LOCK_HELD with zero install "
        "mutation and symlink/hardlink/replaced-parent/permissive mode is PRECHECK_FAILED"
    ),
    "wal_contract": (
        "one journal per probe/PREPARE/APPLY at the exact §5.2 path derived from the "
        "respective core digest; APPLYING is written and fsynced BEFORE the external effect, "
        "the subject is then independently re-observed, and APPLIED records the OBSERVED "
        "digest before VERIFYING; every update is same-filesystem temp create + file fsync + "
        "atomic rename + parent-dir fsync with a canonical inner self-digest and a separate "
        "outer checksum; malformed/truncated/checksum-invalid bytes are "
        "JOURNAL_CORRUPT_RECOVERY_REQUIRED and are never renamed away or overwritten"
    ),
    "compensation_exactness_contract": (
        "s2_4_component_effect_rollback_v1.status==COMPENSATED_EXACT is emitted only when the "
        "INDEPENDENT postcheck verifier, re-run after compensation, reports the applied state "
        "absent, the pre-state lineage intact and an observation that actually changed; an "
        "unobtainable independent re-observation yields COMPENSATED_NOT_REOBSERVED with "
        "exact_pre_state_restored=false, and any disproof is RECOVERY_REQUIRED"
    ),
    "driver_injection_contract": (
        "every host action stays behind the injected InstallLockDriver / DurableFileDriver / "
        "AggregateInstallDriver protocols; driver=None is a typed "
        "EXTERNAL_VERIFICATION_PENDING with zero mutation"
    ),
    # ── W4b(aggregate 交易)的 exported-ABI 契約 ────────────────────────────────
    "aggregate_transaction_contract": (
        "apply_s2_4_install_plan(plan, authorization_set, driver) is the single top-level "
        "APPLY entry point (§10.2). Fixed order: validate s2_4_install_plan_v1 centrally -> "
        "§10.5 #24 inputs (both scoped terminal probe receipts, the PREPARE result, the five "
        "plan-pinned component intents) -> field-by-field aggregate/PG permit payload "
        "comparison -> §9 APPLY TTL budget -> driver=None is EXTERNAL_VERIFICATION_PENDING -> "
        "acquire the install lock -> §5.2 startup reconciliation -> consume both permits once "
        "under that lock -> the five §5.1 rows as write-ahead steps -> independent aggregate "
        "postcheck -> §10.5 #24 success predicate -> observed inactive unit -> terminal "
        "journal -> immutable s2_4_install_effect_receipt_v1"
    ),
    "success_identity_contract": (
        "the frozen success identity is s2_4_install_effect_receipt_v1(status="
        "APPLIED_INACTIVE) and it is unreachable from source by construction: the recorded "
        "evidence class comes from derive_recorded_evidence_class, which refuses a "
        "self-declared attested class, so an in-memory/disposable driver terminates at "
        "SOURCE_SIMULATION_PASS with all nine authorities false (§6 table, §10.5 #13). Only "
        "a trusted-host attested production driver (W6B) can reach APPLIED_INACTIVE"
    ),
    "plan_intent_binding_contract": (
        "§5.1 forbids a digest/signature cycle, so the plan core pins each component intent "
        "by a domain-separated digest over the intent MINUS its two self-referential fields "
        "(install_plan_digest, self_digest), while the intent's install_plan_digest is "
        "compared to the plan's core_digest directly. Coverage does not narrow: every other "
        "intent field is pinned by the plan and the plan pointer is pinned by the comparison"
    ),
    "aggregate_payload_comparison_contract": (
        "the aggregate and PG permits are compared field by field against the validated "
        "plan: 14 of each profile's 15 §9.1 payload fields are re-derived independently from "
        "the plan core, the terminal INSTALLED_UNIT probe receipt, the PG row's component "
        "intent and the code-owned rollback contracts; the 15th (authorization_id) is "
        "self-referential and issued_at/expires_at are pinned to the permit's own recorded "
        "window by PERMIT_PLAN_BINDING layer (a) plus the §9.1 TTL ceiling. "
        "derive_permit_payload_coverage() reports zero uncompared fields, so a future payload "
        "field nobody compares breaks the W4 wave exit"
    ),
    "reverse_compensation_contract": (
        "failure after any applied row compensates in the §5.4 reverse order (unit -> "
        "launch/application bundle -> base runtime -> credential -> auth/PG -> host "
        "identity) through one typed reverse op per row, whose authority is the code-derived "
        "per-row rollback contract digest the PG permit also signs. A row that never mutated "
        "is never 'compensated'. Exactness comes only from the INDEPENDENT post-compensation "
        "re-observation; a unit-byte rollback must re-assert daemon-reload and an HBA "
        "rollback must re-assert the topology-attested reload and confirm aiml_observer_ro "
        "survives. Anything unproven is RECOVERY_REQUIRED, never APPLIED_INACTIVE"
    ),
    "startup_reconcile_contract": (
        "before accepting a new probe, prepare intent or plan the runner reconciles every "
        "non-terminal journal it is given a path for, while holding the install lock: "
        "observed == planned post-state resumes verification, observed == pre-state marks the "
        "step not applied and resumes safely, a task-owned partial with a valid journal "
        "ownership binding compensates in reverse order, and ambiguous ownership/state is "
        "RECOVERY_REQUIRED with zero new mutation; malformed bytes are "
        "JOURNAL_CORRUPT_RECOVERY_REQUIRED and are never renamed away. Only CLEAN and "
        "STEP_NOT_APPLIED admit new work"
    ),
    "runner_wal_lock_wiring_contract": (
        "JournalRoutedDriver routes an existing probe/PREPARE/APPLY driver's "
        "journal_transition calls through W4a's JournalStore under one acquired install lock "
        "and delegates every other attribute unchanged, so hasattr-based hard checks and the "
        "driver's host-call sequence are untouched; no lock is a typed refusal and a "
        "non-durable write raises instead of continuing"
    ),
    # §10.3 誠實面:W4a **不**提供、且不得被當成已提供的義務。每一項都帶 typed 狀態與 owner。
    "remaining_owned_obligations": [
        {
            "obligation_id": "ENCRYPTED_BLOB_DIGEST_ORDERING",
            "typed_status": "OPEN_DESIGN_QUESTION",
            "owner_wave": "W4/W6",
            "spec_refs": ["§5.1", "§7"],
            "statement": (
                "CREDENTIAL_INSTALL's signed intent must carry encrypted_blob_digest, but that "
                "digest is the hash of non-deterministic `systemd-creds encrypt` output. "
                "Either the intent cannot be signed before the encryption runs, or the "
                "plaintext handle must survive the signing window. W4a does not resolve the "
                "§5.1 ordering question; it is carried forward unchanged from W3."
            ),
            "w4_provides": (
                "nothing new; the fail-closed encrypt-then-compare binding from W3 is unchanged"
            ),
        },
        {
            "obligation_id": "OBSERVER_SPACE_PRE_STATE_DIGEST",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§5.2", "§5.4", "§6"],
            "statement": (
                "W4b closed the half that source can close: the plan's aggregate "
                "core.pre_state_digest is now DEFINED as the domain-separated canonical "
                "projection over the five rows' declared pre-states "
                "(derive_plan_pre_state_projection), and the aggregate refuses a plan whose "
                "signed value does not re-derive it — the plan-level digest space is no longer "
                "undefined. The remaining half is the observer side: the independent "
                "verifier's observed_subject_digest is produced by an injected host protocol, "
                "so source cannot make observed_subject_digest == the plan's expected "
                "pre-state digest a meaningful equality. What would close it: a W6B production "
                "postcheck driver contract requiring the verifier to return "
                "canonical_digest over the SAME code-owned per-row pre-state projection "
                "shape, at which point the aggregate can pass that value as the existing "
                "expected_post_compensation_digest parameter and the equality becomes "
                "load-bearing. Verifying that contract needs a real host observer, so it "
                "cannot be closed in the source lane."
            ),
            "w4_provides": (
                "the plan-side digest-space definition plus its enforcement, the independent "
                "post-compensation re-run, the two-flag residue verdict, the "
                "changed-observation check and the optional exact-digest parameter that the "
                "W6B contract will fill"
            ),
        },
        {
            "obligation_id": "ATTESTED_EVIDENCE_CLASS_VERIFIER",
            "typed_status": "NOT_PROVIDED_BY_W4",
            "owner_wave": "W6B",
            "spec_refs": ["§6", "§10.2", "§10.5 #13", "§10.5 #14"],
            "statement": (
                "The aggregate transaction's success identity APPLIED_INACTIVE is gated on the "
                "RECORDED evidence class being attested, and derive_recorded_evidence_class "
                "refuses every self-declared attested class because nothing in-process can "
                "distinguish a fixture from a real host driver. There is therefore no code "
                "path in the source lane that can emit APPLIED_INACTIVE — every driver W4b can "
                "be handed terminates at SOURCE_SIMULATION_PASS. A trusted-host platform "
                "attestation verifier (the same obligation W3 recorded in its "
                "evidence_class_contract) is W6B's, and until it exists §11.3 EFFECT_DONE_"
                "INACTIVE is unreachable, which is the intended posture rather than a defect."
            ),
            "w4_provides": (
                "the reachable-but-authority-locked branch, its typed SOURCE_SIMULATION_PASS "
                "terminal with all nine authorities false, and a test proving a self-declared "
                "PLATFORM_ATTESTED driver still cannot reach APPLIED_INACTIVE"
            ),
        },
        {
            "obligation_id": "PRIOR_LINEAGE_ENTRY_IDENTITY",
            "typed_status": "NOT_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§5.1", "§9.1"],
            "statement": (
                "W4b requires the durable replay ledger to be non-empty before APPLY, because "
                "§5.1 mandates that the PREPARE_SANDBOX probe, PREPARE and the INSTALLED_UNIT "
                "probe each durably consumed their own permit first; an empty ledger is proof "
                "that lineage never happened. It does NOT verify WHICH permits those entries "
                "are, because probe_id/prepare_id are not carried in the install plan (the "
                "plan binds only the receipt digests). Closing it needs either the probe/"
                "PREPARE authorization ids threaded into the APPLY inputs by the W6B runner "
                "(which holds all three phases) or a plan-core field, i.e. a schema change "
                "that §10.4 forbids the worker from choosing."
            ),
            "w4_provides": (
                "the non-empty-ledger gate, a typed AUTHORIZATION_REJECTED with zero mutation "
                "when it is empty, and the append-before/after ledger views used by the rows"
            ),
        },
        {
            "obligation_id": "STARTUP_RECONCILE_LANE_PATHS",
            "typed_status": "NOT_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§5.2"],
            "statement": (
                "Startup reconciliation always inspects the APPLY lane (its path derives from "
                "plan_id) but can only inspect the probe/PREPARE lanes when the caller supplies "
                "their exact derived paths, because probe_id/prepare_id are not derivable from "
                "the plan. A W6B runner that omits startup_journal_paths therefore leaves those "
                "two lanes unchecked. Closing it means the W6B runner passing the paths it "
                "already holds from W6A (still derived by the journal leaf, never joined from a "
                "caller string), or the same plan-core/threading change named in "
                "PRIOR_LINEAGE_ENTRY_IDENTITY."
            ),
            "w4_provides": (
                "the three-lane reconcile with per-lane typed outcomes, the fail-closed refusal "
                "when no path at all is supplied, and tests covering a stranded probe lane"
            ),
        },
    ],
}
# code-owned 探針輸入(與真 repo/runtime 無關;只為把行為折成 deterministic 投影值)。
_W4_HOST = "trade-core"
_W4_SOURCE_HEAD = "0" * 40
_W4_MIRROR = ("203.0.113.0/24",)
_W4_CGROUP_ROOT = "/sys/fs/cgroup/system.slice"
_W4_CREATED_AT = "2026-07-26T00:00:00+00:00"
_W4_EXPIRES_AT = "2026-07-26T00:10:00+00:00"
_W4_PLAN_CORE_DIGEST = "sha256:" + "1" * 64
_W4_PLAN_ID = "s2-4-" + "1" * 64


def _file_sha256(path: Path) -> str | None:
    try:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _probe_intent_probe():
    """W4 投影用的乾淨 PREPARE_SANDBOX probe intent(code-owned;非任何真主機的輸入)。"""

    import agent_governance_s2_4_probe as _probe

    core = _probe.build_capability_probe_core(
        scope="PREPARE_SANDBOX",
        host=_W4_HOST,
        cgroup_manager_scope="system_manager",
        cgroup_root_pattern=_W4_CGROUP_ROOT,
        source_head=_W4_SOURCE_HEAD,
        target_host=_W4_HOST,
        created_at=_W4_CREATED_AT,
        max_cleanup_seconds=30,
        max_cgroup_drain_seconds=10,
        artifact_mirror_allowlist=list(_W4_MIRROR),
    )
    return _probe.build_capability_probe_intent(
        core, expires_at=_W4_EXPIRES_AT, max_ttl_seconds=600
    )


def _permit_binding_live() -> dict[str, Any]:
    """PERMIT_PLAN_BINDING 的活再導出(id 由 payload 導出 / intent 替換必被拒)。"""

    import agent_governance_s2_4_probe as _probe

    facade = resolve_facade()
    live: dict[str, Any] = {}
    try:
        intent = _probe_intent_probe()
        binding = _probe.probe_permit_payload_binding(
            intent, artifact_mirror_allowlist=list(_W4_MIRROR)
        )
        binding["issued_at"] = _W4_CREATED_AT
        binding["expires_at"] = _W4_EXPIRES_AT
        permit = facade.build_s2_4_operator_authorization(
            "capability_probe",
            payload_binding=binding,
            issued_at=_W4_CREATED_AT,
            expires_at=_W4_EXPIRES_AT,
        )
        live["authorization_id_is_payload_derived"] = permit[
            "authorization_id"
        ] == facade.derive_authorization_id(permit)
        expected = {
            key: value
            for key, value in binding.items()
            if key not in {"issued_at", "expires_at"}
        }
        live["clean_plan_binding_status"] = facade.derive_permit_plan_binding_status(
            permit, expected_payload_binding=expected, profile_key="capability_probe"
        )["status"]
        # intent 替換:另一份 intent(不同 target host → 不同 core digest/probe_id)。
        other_core = _probe.build_capability_probe_core(
            scope="PREPARE_SANDBOX",
            host=_W4_HOST,
            cgroup_manager_scope="system_manager",
            cgroup_root_pattern=_W4_CGROUP_ROOT,
            source_head=_W4_SOURCE_HEAD,
            target_host="other-host",
            created_at=_W4_CREATED_AT,
            max_cleanup_seconds=30,
            max_cgroup_drain_seconds=10,
            artifact_mirror_allowlist=list(_W4_MIRROR),
        )
        other_intent = _probe.build_capability_probe_intent(
            other_core, expires_at=_W4_EXPIRES_AT, max_ttl_seconds=600
        )
        substituted = _probe.probe_permit_payload_binding(
            other_intent, artifact_mirror_allowlist=list(_W4_MIRROR)
        )
        live["intent_substitution_status"] = facade.derive_permit_plan_binding_status(
            permit, expected_payload_binding=substituted, profile_key="capability_probe"
        )["status"]
        # 舊形 permit(只有名字、沒有值)必被拒:payload_binding 缺席即無法綁 plan。
        legacy = {key: value for key, value in permit.items() if key != "payload_binding"}
        live["legacy_permit_without_payload_binding_status"] = (
            facade.derive_permit_plan_binding_status(
                legacy, expected_payload_binding=expected, profile_key="capability_probe"
            )["status"]
        )
        live["payload_binding_field_counts"] = {
            key: len(facade.authorization_payload_binding_fields(key))
            for key in sorted(facade.S2_4_AUTHORIZATION_PROFILES)
        }
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        for key in (
            "authorization_id_is_payload_derived",
            "clean_plan_binding_status",
            "intent_substitution_status",
            "legacy_permit_without_payload_binding_status",
            "payload_binding_field_counts",
        ):
            live.setdefault(key, None)
    return live


def _lock_live() -> dict[str, Any]:
    """install lock 的活再導出(無 driver 必 typed pending 且零變更 / unlink 面必被拒)。"""

    import agent_governance_s2_4_lock as _lock

    live: dict[str, Any] = {}
    try:
        pending = _lock.acquire_s2_4_install_lock(None)
        live["source_lane_status"] = pending["status"]
        live["source_lane_mutation_performed"] = pending["mutation_performed"]
        live["source_lane_driver_engaged"] = pending["driver_engaged"]
        live["lock_never_unlinked"] = pending["lock_unlinked"] is False
        stub = type("_UnlinkStub", (), {"unlink": lambda self: None})()
        live["unlink_surface_rejected"] = bool(_lock.assert_no_lock_unlink_surface(stub))
        live["clean_driver_has_no_unlink_surface"] = (
            _lock.assert_no_lock_unlink_surface(object()) == []
        )
    except Exception:  # noqa: BLE001
        for key in (
            "source_lane_status",
            "source_lane_mutation_performed",
            "source_lane_driver_engaged",
            "lock_never_unlinked",
            "unlink_surface_rejected",
            "clean_driver_has_no_unlink_surface",
        ):
            live.setdefault(key, None)
    return live


def _journal_live() -> dict[str, Any]:
    """三本 WAL journal 的活再導出(路徑導出 / 兩道 digest / corrupt / reconcile 四分)。"""

    import agent_governance_s2_4_journal as _journal
    import agent_governance_s2_4_prepare as _prepare

    live: dict[str, Any] = {}
    try:
        sample = "0" * 64
        live["prepare_journal_path_matches_prepare_leaf"] = _journal.prepare_journal_path(
            _journal.PREPARE_ID_PREFIX + sample
        ) == _prepare.prepare_journal_path(_journal.PREPARE_ID_PREFIX + sample)
        journal = _journal.build_install_journal(
            plan_id=_W4_PLAN_ID,
            plan_core_digest=_W4_PLAN_CORE_DIGEST,
            idempotency_key=_W4_PLAN_ID,
            expected_pre_state_digest="sha256:" + "2" * 64,
            aggregate_rollback_digest="sha256:" + "3" * 64,
            entries=[{
                "seq": 0, "step_index": 0, "state": "APPLYING",
                "pre_state_digest": "sha256:" + "2" * 64,
                "post_state_digest": "sha256:" + "4" * 64,
                "fsynced": True, "recorded_at": _W4_CREATED_AT,
            }],
            terminal=False,
        )
        live["journal_integrity_reobserves"] = (
            _journal.journal_integrity_errors(journal) == []
        )
        live["journal_self_and_outer_digests_differ"] = (
            journal["self_digest"] != journal["outer_checksum"]
        )
        tampered = dict(journal)
        tampered["terminal"] = True
        live["tampered_journal_breaks_digests"] = bool(
            _journal.journal_integrity_errors(tampered)
        )
        live["truncated_bytes_status"] = _journal.verify_journal_bytes(
            b'{"schema_version": "s2_4_install_journal_v1", "entr',
            journal_path=_journal.install_journal_path(_W4_PLAN_ID),
        )["status"]
        live["reconcile_resume_status"] = _journal.reconcile_journal(
            journal, observed_state_digest="sha256:" + "4" * 64
        )["status"]
        live["reconcile_not_applied_status"] = _journal.reconcile_journal(
            journal, observed_state_digest="sha256:" + "2" * 64
        )["status"]
        live["reconcile_ambiguous_status"] = _journal.reconcile_journal(
            journal, observed_state_digest="sha256:" + "9" * 64
        )["status"]
        live["journal_destructive_surface_rejected"] = bool(
            _journal.assert_no_journal_destructive_surface(
                type("_S", (), {"unlink": lambda self: None})()
            )
        )
    except Exception:  # noqa: BLE001
        for key in (
            "prepare_journal_path_matches_prepare_leaf",
            "journal_integrity_reobserves",
            "journal_self_and_outer_digests_differ",
            "tampered_journal_breaks_digests",
            "truncated_bytes_status",
            "reconcile_resume_status",
            "reconcile_not_applied_status",
            "reconcile_ambiguous_status",
            "journal_destructive_surface_rejected",
        ):
            live.setdefault(key, None)
    return live


def _budget_live() -> dict[str, Any]:
    """§9 三條 TTL 不等式 + 過期後只剩安全清理的活再導出。"""

    import agent_governance_s2_4_permit as _permit

    live: dict[str, Any] = {}
    try:
        satisfied = _permit.derive_ttl_budget_status(
            "APPLY",
            budget={term: 60 for term in _permit.APPLY_TTL_BUDGET_TERMS},
            remaining_ttls={term: 900 for term in _permit.APPLY_TTL_BOUND_TERMS},
        )
        live["apply_budget_satisfied_status"] = satisfied["status"]
        # §9:3600 秒的操作不能在 900 秒 permit 下跑。
        exceeded = _permit.derive_ttl_budget_status(
            "APPLY",
            budget={
                **{term: 0 for term in _permit.APPLY_TTL_BUDGET_TERMS},
                "apply_budget": 3600,
            },
            remaining_ttls={term: 900 for term in _permit.APPLY_TTL_BOUND_TERMS},
        )
        live["apply_budget_exceeded_status"] = exceeded["status"]
        live["apply_budget_binding_evidence"] = exceeded["binding_evidence"]
        missing_term = {
            term: 60 for term in _permit.APPLY_TTL_BUDGET_TERMS if term != "safety_margin"
        }
        live["missing_term_status"] = _permit.derive_ttl_budget_status(
            "APPLY",
            budget=missing_term,
            remaining_ttls={term: 900 for term in _permit.APPLY_TTL_BOUND_TERMS},
        )["status"]
        live["post_expiry_cleanup_status"] = _permit.derive_post_expiry_operation_status(
            operation="transient_unit_stop", permit_expired=True
        )["status"]
        live["post_expiry_creation_status"] = _permit.derive_post_expiry_operation_status(
            operation="transient_unit_create", permit_expired=True
        )["status"]
        live["post_expiry_unknown_status"] = _permit.derive_post_expiry_operation_status(
            operation="something_new", permit_expired=True
        )["status"]
        live["expiry_during_apply_status"] = _permit.derive_expiry_during_apply_status(
            permit_expires_at=_W4_CREATED_AT,
            observed_now=_W4_EXPIRES_AT,
            mutation_performed=True,
        )["status"]
    except Exception:  # noqa: BLE001
        for key in (
            "apply_budget_satisfied_status",
            "apply_budget_exceeded_status",
            "apply_budget_binding_evidence",
            "missing_term_status",
            "post_expiry_cleanup_status",
            "post_expiry_creation_status",
            "post_expiry_unknown_status",
            "expiry_during_apply_status",
        ):
            live.setdefault(key, None)
    return live


def _compensation_live() -> dict[str, Any]:
    """``COMPENSATED_EXACT`` 只由**獨立** verifier 的補償後再觀測導出的活再導出。"""

    import agent_governance_s2_4_component as _component

    live: dict[str, Any] = {}
    try:
        live["applier_self_report_is_not_exact"] = _component.derive_compensation_status(
            _component.compensation_outcome(compensated=True, reobserved=True)
        ) == (_component.COMPENSATION_STATUS_NOT_REOBSERVED, False)
        live["independent_confirmation_is_exact"] = _component.derive_compensation_status(
            _component.compensation_outcome(
                compensated=True, reobserved=True, independent_reobserved=True
            )
        ) == (_component.COMPENSATION_STATUS_EXACT, True)
        live["independent_disproof_is_recovery"] = _component.derive_compensation_status(
            _component.compensation_outcome(
                compensated=True, reobserved=True, independent_reobserved=False
            )
        ) == (_component.COMPENSATION_STATUS_RECOVERY_REQUIRED, False)
        no_verifier = _component.independent_post_compensation_postcheck(
            driver=object(), component_effect_class="HOST_IDENTITY_INSTALL",
            install_plan_digest=_W4_PLAN_CORE_DIGEST, applier_node="applier",
            pre_state_digest="sha256:" + "2" * 64,
        )
        live["no_verifier_is_unavailable"] = (
            no_verifier["status"] == _component.POST_COMPENSATION_POSTCHECK_UNAVAILABLE
            and no_verifier["independent_reobserved"] is None
        )
    except Exception:  # noqa: BLE001
        for key in (
            "applier_self_report_is_not_exact",
            "independent_confirmation_is_exact",
            "independent_disproof_is_recovery",
            "no_verifier_is_unavailable",
        ):
            live.setdefault(key, None)
    return live


def _aggregate_live() -> dict[str, Any]:
    """W4b aggregate 交易的活再導出(source lane 零變更 / 逐欄 payload 覆蓋 / §5.1 無環)。"""

    import agent_governance_s2_4_install_driver as _runner

    live: dict[str, Any] = {}
    try:
        pending = _runner.apply_s2_4_install_plan(None, None, None)
        live["malformed_plan_status"] = pending["status"]
        live["malformed_plan_mutation_performed"] = pending["mutation_performed"]
        live["success_identity"] = _runner.AGGREGATE_STATUS_APPLIED_INACTIVE
        live["source_lane_identity"] = _runner.AGGREGATE_STATUS_SOURCE_SIMULATION
        live["apply_row_order"] = list(_runner.APPLY_ROW_ORDER)
        live["reverse_compensation_order"] = list(_runner.REVERSE_COMPENSATION_ORDER)
        live["apply_row_step_index"] = dict(_runner.APPLY_ROW_STEP_INDEX)
        coverage = _runner.derive_permit_payload_coverage()
        live["payload_comparison_complete"] = {
            key: row["complete"] for key, row in coverage.items()
        }
        live["payload_uncompared_fields"] = {
            key: row["uncompared_fields"] for key, row in coverage.items()
        }
        # §5.1 無 digest 環:兩個自指欄位換掉不改 binding,其餘任一欄改必改 binding。
        intent = {
            "schema_version": "s2_4_component_effect_intent_v1",
            "component_effect_class": "HOST_IDENTITY_INSTALL",
            "install_plan_digest": "sha256:" + "1" * 64,
            "pre_state_digest": "sha256:" + "2" * 64,
            "required_intent_fields": {
                "uid_gid_directory_manifest_digest": "sha256:" + "3" * 64
            },
            "expires_at": _W4_EXPIRES_AT,
            "self_digest": "sha256:" + "4" * 64,
        }
        baseline = _runner.component_intent_plan_binding_digest(intent)
        live["binding_ignores_self_referential_fields"] = all(
            _runner.component_intent_plan_binding_digest({**intent, field: "sha256:" + "9" * 64})
            == baseline
            for field in ("install_plan_digest", "self_digest")
        )
        live["binding_pins_every_other_field"] = all(
            _runner.component_intent_plan_binding_digest({**intent, field: value}) != baseline
            for field, value in (
                ("pre_state_digest", "sha256:" + "9" * 64),
                ("expires_at", _W4_CREATED_AT),
                ("component_effect_class", "ENGINE_SCANNER"),
            )
        )
        live["forbidden_aggregate_surface_rejected"] = bool(
            _runner.assert_no_aggregate_forbidden_surface(
                type("_Stub", (), {"start_transient_unit": lambda self: None})()
            )
        )
        live["clean_aggregate_surface_accepted"] = (
            _runner.assert_no_aggregate_forbidden_surface(object()) == []
        )
        # typed 終端集合必為 install receipt schema 的封閉 enum 子集(無別名換成 success)。
        schema = resolve_facade()._load_schema("s2_4_install_effect_receipt_v1")
        live["typed_statuses_within_receipt_enum"] = set(
            _runner.AGGREGATE_TYPED_STATUSES
        ) <= set(schema["$defs"]["status"]["enum"])
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        for key in (
            "malformed_plan_status",
            "malformed_plan_mutation_performed",
            "success_identity",
            "source_lane_identity",
            "apply_row_order",
            "reverse_compensation_order",
            "apply_row_step_index",
            "payload_comparison_complete",
            "payload_uncompared_fields",
            "binding_ignores_self_referential_fields",
            "binding_pins_every_other_field",
            "forbidden_aggregate_surface_rejected",
            "clean_aggregate_surface_accepted",
            "typed_statuses_within_receipt_enum",
        ):
            live.setdefault(key, None)
    return live


def _reconcile_live() -> dict[str, Any]:
    """§5.2 啟動 reconcile 的活再導出(lock 必需 / 無 driver typed pending / 四分投影)。"""

    import agent_governance_s2_4_journal as _journal
    import agent_governance_s2_4_reconcile as _reconcile

    live: dict[str, Any] = {}
    try:
        paths = {"install": _journal.install_journal_path("s2-4-" + "a" * 64)}
        live["lock_required_status"] = _reconcile.reconcile_startup_journals(
            object(), journal_paths=paths, lock_verdict=None
        )["status"]
        held = {"status": "INSTALL_LOCK_ACQUIRED"}
        pending = _reconcile.reconcile_startup_journals(
            None, journal_paths=paths, lock_verdict=held
        )
        live["source_lane_status"] = pending["status"]
        live["source_lane_mutation_performed"] = pending["mutation_performed"]
        live["source_lane_admits_new_work"] = pending["admits_new_work"]
        live["no_paths_status"] = _reconcile.reconcile_startup_journals(
            object(), journal_paths={}, lock_verdict=held
        )["status"]
        live["reconcile_projection"] = dict(_reconcile._RECONCILE_PROJECTION)
        live["admits_new_work_only_for"] = list(_reconcile.RECONCILE_ADMITS_NEW_WORK)
        live["lanes"] = list(_reconcile.RECONCILE_LANES)
        # RUNNER_WAL_LOCK_WIRING:沒有已取得的 lock 就拒絕落盤。
        routed = _reconcile.JournalRoutedDriver(
            object(), store=_journal.JournalStore(
                None, journal_path=_journal.install_journal_path("s2-4-" + "a" * 64)
            ),
            build_journal=lambda entries, terminal: {}, lock_verdict=None,
            clock=lambda: __import__("datetime").datetime(
                2030, 1, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        )
        try:
            routed.journal_transition(entry={"state": "APPLYING"})
            live["routed_without_lock_refused"] = False
        except _reconcile.InstallDriverContractError as error:
            live["routed_without_lock_refused"] = (
                error.code == "journal_transition_requires_the_install_lock"
            )
    except Exception:  # noqa: BLE001
        for key in (
            "lock_required_status",
            "source_lane_status",
            "source_lane_mutation_performed",
            "source_lane_admits_new_work",
            "no_paths_status",
            "reconcile_projection",
            "admits_new_work_only_for",
            "lanes",
            "routed_without_lock_refused",
        ):
            live.setdefault(key, None)
    return live


def w4_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W4 exported-ABI 投影:code-owned 骨架 + 四葉 ABI 與其活再導出。"""

    import agent_governance_s2_4_install_driver as _runner
    import agent_governance_s2_4_journal as _journal
    import agent_governance_s2_4_lock as _lock
    import agent_governance_s2_4_permit as _permit

    try:
        journal_abi = _journal.journal_abi_projection()
    except Exception:  # noqa: BLE001
        journal_abi = None
    try:
        lock_abi = _lock.lock_abi_projection()
    except Exception:  # noqa: BLE001
        lock_abi = None
    try:
        permit_abi = _permit.permit_abi_projection()
    except Exception:  # noqa: BLE001
        permit_abi = None
    try:
        install_driver_abi = _runner.install_driver_abi_projection()
    except Exception:  # noqa: BLE001
        install_driver_abi = None
    return {
        **_W4_EXPORTED_ABI,
        "journal_abi": journal_abi,
        "lock_abi": lock_abi,
        "permit_abi": permit_abi,
        "install_driver_abi": install_driver_abi,
        "permit_binding_live": _permit_binding_live(),
        "lock_live": _lock_live(),
        "journal_live": _journal_live(),
        "budget_live": _budget_live(),
        "compensation_live": _compensation_live(),
        "aggregate_live": _aggregate_live(),
        "reconcile_live": _reconcile_live(),
    }


def w4_owned_path_diff_digest(repo_root: Path = REPO_ROOT) -> str:
    """W4 owned-path 內容投影 digest(同 W2/W3 機制,綁 W4 面;缺檔記 None)。"""

    projection: dict[str, str | None] = {}
    for rel in sorted(_W4_OWNED_PATHS):
        projection[rel] = _file_sha256(repo_root / rel)
    return canonical_digest(projection)


def w4_structural_errors(receipt: dict[str, Any], repo_root: Path = REPO_ROOT) -> list[str]:
    """wave=W4 的自足結構再導出(facade ``_wave_exit_structural_errors`` 委派)。

    除 digest 恆等外,把 W4 exit 的謂詞「顯式」折活:permit id 必由 payload 導出、intent
    替換與缺 payload_binding 的舊形 permit 必被拒、install lock 無 driver 必 typed pending
    且零變更、三本 journal 的路徑/兩道 digest/corrupt/reconcile 四分必再導出、§9 三條不等式
    必雙向再導出、``COMPENSATED_EXACT`` 必只由獨立 verifier 導出。
    """

    reasons: list[str] = []
    if receipt.get("predecessor_wave_receipt_digest") is None:
        reasons.append(
            "W4 wave-exit requires a non-null predecessor_wave_receipt_digest "
            "(the W3 wave-exit self_digest)"
        )
    projection = w4_exported_abi_projection(repo_root)
    if receipt.get("exported_abi_digest") != canonical_digest(projection):
        reasons.append(
            "wave-exit exported_abi_digest does not re-derive the W4 exported-ABI projection"
        )
    for name in ("journal_abi", "lock_abi", "permit_abi", "install_driver_abi"):
        if projection.get(name) is None:
            reasons.append(f"W4 {name} projection cannot be re-derived")
    permit_live = projection["permit_binding_live"]
    if permit_live.get("authorization_id_is_payload_derived") is not True:
        reasons.append(
            "W4 authorization_id does not re-derive from the permit's own payload_binding "
            "(a permit that is not bound to its payload authorizes any intent of its class)"
        )
    if permit_live.get("clean_plan_binding_status") != "PERMIT_PLAN_BINDING_VERIFIED":
        reasons.append(
            "W4 permit plan binding does not verify against the intent it was minted for"
        )
    if permit_live.get("intent_substitution_status") != "PERMIT_PLAN_BINDING_REJECTED":
        reasons.append(
            "W4 does not reject an intent substitution under one signed permit (§10.5 #36)"
        )
    if permit_live.get("legacy_permit_without_payload_binding_status") != (
        "PERMIT_PLAN_BINDING_REJECTED"
    ):
        reasons.append(
            "W4 does not reject a legacy permit that names payload fields without binding "
            "their values"
        )
    lock_live = projection["lock_live"]
    if lock_live.get("source_lane_status") != "EXTERNAL_VERIFICATION_PENDING":
        reasons.append(
            "W4 source-lane install lock does not re-derive EXTERNAL_VERIFICATION_PENDING"
        )
    if lock_live.get("source_lane_mutation_performed") is not False or (
        lock_live.get("source_lane_driver_engaged") is not False
    ):
        reasons.append(
            "W4 source-lane install lock must perform zero mutation and engage no driver"
        )
    if lock_live.get("lock_never_unlinked") is not True or (
        lock_live.get("unlink_surface_rejected") is not True
    ) or lock_live.get("clean_driver_has_no_unlink_surface") is not True:
        reasons.append(
            "W4 install lock unlink boundary is not load-bearing (§5.2: never unlinked)"
        )
    journal_live = projection["journal_live"]
    if journal_live.get("prepare_journal_path_matches_prepare_leaf") is not True:
        reasons.append(
            "W4 PREPARE journal path derivation drifted from the W3 prepare leaf's own value"
        )
    if journal_live.get("journal_integrity_reobserves") is not True or (
        journal_live.get("journal_self_and_outer_digests_differ") is not True
    ) or journal_live.get("tampered_journal_breaks_digests") is not True:
        reasons.append(
            "W4 journal canonical self-digest plus separate outer checksum are not "
            "load-bearing (§5.2)"
        )
    if journal_live.get("truncated_bytes_status") != "JOURNAL_CORRUPT_RECOVERY_REQUIRED":
        reasons.append(
            "W4 truncated journal bytes do not re-derive JOURNAL_CORRUPT_RECOVERY_REQUIRED"
        )
    if journal_live.get("reconcile_resume_status") != "RESUME_VERIFICATION" or (
        journal_live.get("reconcile_not_applied_status") != "STEP_NOT_APPLIED_RESUME"
    ) or journal_live.get("reconcile_ambiguous_status") != "RECOVERY_REQUIRED":
        reasons.append(
            "W4 deterministic reconcile does not re-derive the §5.2 outcomes "
            "(resume / not-applied / ambiguous)"
        )
    if journal_live.get("journal_destructive_surface_rejected") is not True:
        reasons.append(
            "W4 does not reject a journal driver exposing unlink/truncate/rotate (§5.2: a "
            "corrupt journal is never renamed away or overwritten)"
        )
    budget_live = projection["budget_live"]
    if budget_live.get("apply_budget_satisfied_status") != "TTL_BUDGET_SATISFIED" or (
        budget_live.get("apply_budget_exceeded_status") != "TTL_BUDGET_EXCEEDED"
    ):
        reasons.append("W4 §9 TTL budget inequality does not re-derive in both directions")
    if budget_live.get("missing_term_status") != "TTL_BUDGET_REJECTED":
        reasons.append(
            "W4 §9 TTL budget accepts an incomplete term set (a missing term silently "
            "loosens the inequality)"
        )
    if budget_live.get("post_expiry_cleanup_status") != (
        "POST_EXPIRY_SAFETY_CLEANUP_AUTHORIZED"
    ) or budget_live.get("post_expiry_creation_status") != "POST_EXPIRY_OPERATION_FORBIDDEN":
        reasons.append(
            "W4 post-expiry authority does not re-derive '新建禁止、安全清理不被阻擋' "
            "(§10.5 #10)"
        )
    if budget_live.get("post_expiry_unknown_status") != "UNKNOWN_OPERATION_FORBIDDEN":
        reasons.append("W4 post-expiry operation table is not fail-closed for unknown names")
    if budget_live.get("expiry_during_apply_status") != "EXPIRY_DURING_APPLY_COMPENSATE":
        reasons.append(
            "W4 expiry during apply does not re-derive compensation (expiry never converts a "
            "partial apply into success)"
        )
    compensation_live = projection["compensation_live"]
    if compensation_live.get("applier_self_report_is_not_exact") is not True:
        reasons.append(
            "W4 still lets an applier-side self-report claim COMPENSATED_EXACT"
        )
    if compensation_live.get("independent_confirmation_is_exact") is not True or (
        compensation_live.get("independent_disproof_is_recovery") is not True
    ) or compensation_live.get("no_verifier_is_unavailable") is not True:
        reasons.append(
            "W4 independent post-compensation postcheck does not drive the three-way "
            "exactness verdict"
        )
    aggregate_live = projection["aggregate_live"]
    if aggregate_live.get("malformed_plan_status") != "PRECHECK_FAILED" or (
        aggregate_live.get("malformed_plan_mutation_performed") is not False
    ):
        reasons.append(
            "W4 aggregate transaction does not typed-reject a malformed plan with zero mutation"
        )
    if aggregate_live.get("success_identity") != "APPLIED_INACTIVE" or (
        aggregate_live.get("source_lane_identity") != "SOURCE_SIMULATION_PASS"
    ):
        reasons.append(
            "W4 aggregate success identity drifted from §10.2 "
            "s2_4_install_effect_receipt_v1(status=APPLIED_INACTIVE)"
        )
    if aggregate_live.get("apply_row_order") != [
        "HOST_IDENTITY_INSTALL", "PG_ROLE_ACL_MIGRATION", "CREDENTIAL_INSTALL",
        "LEARNING_RUNTIME", "ENGINE_SCANNER",
    ]:
        reasons.append("W4 aggregate does not drive the five rows in the §5.1 required order")
    if aggregate_live.get("reverse_compensation_order") != [
        "ENGINE_SCANNER", "LEARNING_RUNTIME", "CREDENTIAL_INSTALL",
        "PG_ROLE_ACL_MIGRATION", "HOST_IDENTITY_INSTALL",
    ]:
        reasons.append(
            "W4 reverse compensation order is not the §5.4 chain (unit -> launch/application "
            "bundle -> base runtime -> credential -> auth/PG -> host identity)"
        )
    if aggregate_live.get("payload_comparison_complete") != {
        "apply_aggregate": True, "pg_migration": True
    } or aggregate_live.get("payload_uncompared_fields") != {
        "apply_aggregate": [], "pg_migration": []
    }:
        reasons.append(
            "W4 does not compare EVERY §9.1 permit payload field against the validated plan "
            "(an uncompared field is a field the operator did not effectively sign for this plan)"
        )
    if aggregate_live.get("binding_ignores_self_referential_fields") is not True or (
        aggregate_live.get("binding_pins_every_other_field") is not True
    ):
        reasons.append(
            "W4 plan-to-intent binding is not the §5.1 acyclic form (it must exclude exactly "
            "the two self-referential fields and pin every other one)"
        )
    if aggregate_live.get("forbidden_aggregate_surface_rejected") is not True or (
        aggregate_live.get("clean_aggregate_surface_accepted") is not True
    ):
        reasons.append(
            "W4 does not reject an aggregate driver exposing a probe/enable/start surface "
            "(§8.3: S2.4 installs the unit inactive and never starts it)"
        )
    if aggregate_live.get("typed_statuses_within_receipt_enum") is not True:
        reasons.append(
            "W4 aggregate typed statuses are not a subset of the frozen install-receipt enum "
            "(no alias may turn one of them into success)"
        )
    reconcile_live = projection["reconcile_live"]
    if reconcile_live.get("lock_required_status") != "INSTALL_LOCK_REQUIRED":
        reasons.append(
            "W4 startup reconciliation does not require the acquired install lock (§5.2)"
        )
    if reconcile_live.get("source_lane_status") != "EXTERNAL_VERIFICATION_PENDING" or (
        reconcile_live.get("source_lane_mutation_performed") is not False
    ) or reconcile_live.get("source_lane_admits_new_work") is not False:
        reasons.append(
            "W4 source-lane startup reconciliation must be typed pending with zero mutation "
            "and must not admit new work"
        )
    if reconcile_live.get("no_paths_status") != "RECOVERY_REQUIRED":
        reasons.append(
            "W4 startup reconciliation is not fail-closed when it is given no lane to inspect"
        )
    if reconcile_live.get("admits_new_work_only_for") != [
        "STARTUP_RECONCILE_CLEAN", "STARTUP_RECONCILE_STEP_NOT_APPLIED"
    ]:
        reasons.append(
            "W4 startup reconciliation admits new work outside the two §5.2 safe outcomes"
        )
    if reconcile_live.get("routed_without_lock_refused") is not True:
        reasons.append(
            "W4 RUNNER_WAL_LOCK_WIRING does not refuse to journal without the install lock"
        )
    if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W4_OWNED_PATHS)):
        reasons.append("wave-exit owned_path_manifest_digest is not the exact W4 owned-path set")
    if receipt.get("owned_path_diff_digest") != w4_owned_path_diff_digest(repo_root):
        reasons.append(
            "wave-exit owned_path_diff_digest does not re-derive the W4 owned-path content "
            "projection"
        )
    return reasons


def w4_chain_binding_errors(
    receipt: dict[str, Any],
    source_admission_receipt: dict[str, Any],
    predecessor_wave_receipt: dict[str, Any],
    head: str | None,
) -> list[str]:
    """W4 predecessor/admission/HEAD 綁定檢查(facade 於 W3 鏈已導 PASS 後呼叫)。"""

    reasons: list[str] = []
    if predecessor_wave_receipt.get("wave") != "W3":
        reasons.append("W4 wave-exit predecessor must be the W3 wave-exit receipt")
    if predecessor_wave_receipt.get("self_digest") != receipt.get(
        "predecessor_wave_receipt_digest"
    ):
        reasons.append(
            "W4 predecessor_wave_receipt_digest does not bind the derived W3 wave-exit receipt"
        )
    if source_admission_receipt.get("self_digest") != receipt.get(
        "source_admission_receipt_digest"
    ):
        reasons.append(
            "wave-exit source_admission_receipt_digest does not bind the derived admission receipt"
        )
    if head is None:
        reasons.append(
            "W4 wave-exit source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
        )
    elif receipt.get("source_head") != head:
        reasons.append("W4 wave-exit source_head is not the current checkout HEAD")
    if receipt.get("source_head") != predecessor_wave_receipt.get("source_head"):
        reasons.append("W4 wave-exit source_head differs from the bound W3 wave-exit receipt")
    if receipt.get("source_head") != source_admission_receipt.get("source_head"):
        reasons.append("W4 wave-exit source_head differs from the bound admission receipt")
    return reasons
