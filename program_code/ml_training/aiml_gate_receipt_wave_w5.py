"""S2.4(WP4·W5)wave-exit 綁定的 code-owned 投影葉模組(§10.3 W5 row)。

鏡 :mod:`aiml_gate_receipt_wave_w4`:facade 逐名 re-export,``derive_wave_exit_status``
的 W5 分支委派本葉。W5 是**源碼收口波**——它不新增任何 production gate,只把「§10.5 的
每一條驗收項到底被哪一支測試證明」這件事折成**活**投影,讓覆蓋退化必然弄破 wave-exit:

- ``_W5_OWNED_PATHS``:W5 的投影葉、facade 的 W5 分支、runtime-closure 宣告面,以及
  W5 新寫的兩支測試與被 W5 推進邊界的 W3 wave 測試;
- ``w5_exported_abi_projection``:折入六組**活**再導出。每一組都對應一條 W5 自審發現
  「有名字但沒有證明」的 §10.5 驗收項,任一 source 面被弱化,投影即變值:

  1. ``secret_scan_live``(§10.5 #15):``assert_no_secret_material`` 的**編碼形**偵測。
     W4 之前只有明文形被任何測試碰過;刪掉 b64/b16/urlsafe/hex 四種編碼形,全樹依然全綠。
  2. ``pg_role_identity_live``(§10.5 #12):S2.4 的 PG row 只能作用在 ``aiml_engine_scanner``
     上,``aiml_observer_ro`` 連被命名的資格都沒有——舊有的
     ``not any("aiml_observer_ro" in s for s in revoked)`` 斷言之所以通過,是因為 fixture 的
     manifest 本來就沒提過 observer,而不是因為 source 擋住了它。
  3. ``component_scope_live``(§10.5 #16):§2 明文 S2.4 **不**安裝
     controller / fit_evaluation / serving / deleter;此前零測試。
  4. ``inactive_postcheck_live``(§10.5 #29):S2.4 的 inactive postcheck 不得挾帶
     runtime-directory / 已解密憑證的宣稱,且 ``enable --now`` 屬 S2.5A。
  5. ``rendered_unit_negative_live``(§10.5 #11):``/usr/bin/python3`` 與 ``alr_shadow``
     兩個 §12 明文禁止的身分,在 rendered unit 上必為 typed 拒絕。
  6. ``schema_registration_live``(§10.5 #1 / §9.2 / §10.5 #28):每一份 S2.4 schema 都必須
     真的在中央 ``SCHEMA_FILES`` 上;而 §10.1 明列卻**不存在**的
     ``s2_4_dependency_refresh_attestation_v1`` 被誠實折成一個 typed 缺口,而不是被略過。

- W5 的 PASS 另需前導 W4 wave-exit「連同其 W3/W2/W1/W0/admission 鏈」一起再導出 PASS
  (predecessor 物件鏈驗在 facade 的 ``derive_wave_exit_status``)。

owned-path 投影採 W2 修正後的 **commit-blob** 尺(``owned_path_blob_projection_digest``),
而非 W3/W4 仍在用的工作樹位元組:一份宣稱「HEAD 未變」的 receipt 不該能被髒工作樹自我對上。
髒工作樹這個事實本身折入 ``owned_scope_worktree_delta``,可見而非靜默。

receipt 只帶 evidence,PASS 恆由中央 validator 導出;本波「不」認證任何 runtime——
九 authority / production_apply_performed / running_attested 恆 false,且 W5 不發射任何效果。
facade 依 2000 行治理拆分規約「只」經 schema_core.resolve_facade() 取得;governed helper
模組於函式內延遲匯入(保 monkeypatch 縫、避免 import 循環)。
"""
from __future__ import annotations

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

from aiml_gate_receipt_schema_core import (  # noqa: E402
    canonical_digest,
    owned_path_blob_projection_digest,
    owned_scope_worktree_delta,
    resolve_facade,
)

_SCHEMA_DIR_REL = "program_code/ml_training/schemas/aiml_gate_receipts"
# §10.1 + §10.1.1(2026-07-26 PM path-scope amendment):W5 的 owned-path 投影。
# W5 只擁有「收口」面:投影葉、facade 的 W5 分支、runtime-closure 宣告(facade top-level
# import 使本葉進入 engine-scanner runtime import 閉包)、W5 新寫的兩支測試,以及把
# 「未實作 wave」邊界由 W5 推到 W6 的那支既有 W3 wave 測試。
_W5_OWNED_PATHS = tuple(sorted((
    "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
    "program_code/ml_training/aiml_gate_receipt_schema_core.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w5.py",
    "program_code/ml_training/application_bundle_runtime_closure_v1.json",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    f"{_SCHEMA_DIR_REL}/s2_4_dependency_refresh_attestation_v1.schema.json",
    "tests/structure/test_agent_governance_s2_4_acceptance_matrix.py",
    "tests/structure/test_agent_governance_s2_4_install_w3.py",
    "tests/structure/test_agent_governance_s2_4_install_w5.py",
)))

# §2:S2.4 明文**不**安裝的四個未來元件身分(§10.5 #16)。
_FORBIDDEN_COMPONENT_IDENTITIES = (
    "aiml_controller",
    "aiml_deleter",
    "aiml_fit_evaluation",
    "aiml_serving",
    "controller",
    "deleter",
    "fit_evaluation",
    "serving",
)
# S1.1 的唯讀觀察身分:S2.4 永不建立/刪除/收回它(§10.5 #12)。
_OBSERVER_ROLE = "aiml_observer_ro"
_SCANNER_ROLE = "aiml_engine_scanner"
# §9.2 / §10.1 明列的 dependency-refresh schema。W5 前半段(2026-07-26)在此 head 上**不存在**,
# 被誠實折成 typed 缺口;W5 後半段(2026-07-27)把它實作出來,於是同一個投影鍵由「缺席」翻成
# 「已註冊 + 中央閘活裁決」(§10.5 #28 的前半邊自此可證)。
_DEPENDENCY_REFRESH_SCHEMA = "s2_4_dependency_refresh_attestation_v1"
# §9.2 活探針的 code-owned 固定時鐘/身分(絕不取 wall clock:投影值一旦隨真實時間漂移,
# W5 wave-exit 的 exported_abi_digest 就無法跨時重現)。
_DEPENDENCY_REFRESH_PROBE_NOW = "2026-07-27T00:05:00+00:00"
_DEPENDENCY_REFRESH_PROBE_REPRODUCED_AT = "2026-07-27T00:00:00+00:00"
_DEPENDENCY_REFRESH_PROBE_CALLER = "E1:S2.4:W5-dependency-refresh-probe"
_DEPENDENCY_REFRESH_PROBE_PLATFORM = {
    "os": "darwin",
    "arch": "arm64",
    "python_version": "3.12",
}
# 真實的、已過期的 S2.2A source 身分(repo 內既有 receipt;非合成 fixture)。
_S2_2A_RECEIPT_V1_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v1.json"
)
_S2_2A_RECEIPT_V2_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v2.json"
)
# §10.5 #1:S2.4 owned schema 的完整集合(§10.1 逐行,扣掉上面那份缺席者)。
_S2_4_SCHEMA_KEYS = tuple(sorted((
    "aiml_component_effect_classification_v2",
    "application_bundle_manifest_v1",
    "application_bundle_runtime_closure_v1",
    "base_runtime_tree_manifest_v1",
    "launch_bundle_manifest_v1",
    "network_sandbox_capability_attestation_v1",
    "pg_acl_manifest_v1",
    "pg_topology_attestation_v1",
    "pg_topology_runtime_guard_v1",
    "s2_4_authorization_replay_ledger_v1",
    "s2_4_capability_probe_core_v1",
    "s2_4_capability_probe_effect_receipt_v1",
    "s2_4_capability_probe_intent_v1",
    "s2_4_capability_probe_journal_v1",
    "s2_4_capability_probe_postcheck_v1",
    "s2_4_capability_probe_rollback_v1",
    "s2_4_component_effect_intent_v1",
    "s2_4_component_effect_postcheck_v1",
    "s2_4_component_effect_result_v1",
    "s2_4_component_effect_rollback_v1",
    "s2_4_dependency_refresh_attestation_v1",
    "s2_4_install_effect_receipt_v1",
    "s2_4_install_journal_v1",
    "s2_4_install_plan_core_v1",
    "s2_4_install_plan_v1",
    "s2_4_install_postcheck_v1",
    "s2_4_install_rollback_v1",
    "s2_4_install_step_result_v1",
    "s2_4_operator_authorization_v1",
    "s2_4_pg_hba_delta_v1",
    "s2_4_prepare_core_v1",
    "s2_4_prepare_effect_receipt_v1",
    "s2_4_prepare_intent_v1",
    "s2_4_prepare_journal_v1",
    "s2_4_prepare_postcheck_v1",
    "s2_4_prepare_rollback_v1",
    "s2_4_prepared_install_bundle_v1",
    "s2_4_source_admission_receipt_v1",
    "s2_4_wave_exit_receipt_v1",
)))
# §8.3 unit 渲染探針欄位(與 W2 的探針同形;純 code-owned,與任何主機無關)。
_W5_UNIT_FIELDS = {
    "source_head": "0" * 40,
    "learning_runtime_digest": "sha256:" + "0" * 64,
    "learning_runtime_digest_v2": "sha256:" + "1" * 64,
    "application_bundle_digest": "sha256:" + "2" * 64,
    "launch_bundle_digest": "sha256:" + "3" * 64,
}

# §10.2/§10.3 W5 exported-ABI 的 code-owned 骨架(live 部分見 w5_exported_abi_projection)。
_W5_EXPORTED_ABI = {
    "wave": "W5",
    "wave_scope": (
        "source closure. W5 adds no production gate and performs no effect: it runs the "
        "focused, adjacent, security and integration lanes, maps every §10.5 acceptance item "
        "to the test that would fail if the source were wrong, writes the tests for the items "
        "that had none, and folds those predicates live into this wave's exported ABI so a "
        "coverage regression breaks the W5 wave exit rather than passing silently. It also "
        "derives the W0->W5 receipt chain and carries every unclosed obligation forward with "
        "an unchanged owner"
    ),
    "typed_failures": [
        "APPLICATION_BUNDLE_TREE_INVALID",
        "ENGINE_SCANNER_UNIT_INVALID",
        "EXTERNAL_VERIFICATION_PENDING",
        "PRECHECK_FAILED",
        "SECRET_MATERIAL_LEAK_BLOCKED",
    ],
    "acceptance_map_contract": (
        "every §10.5 item is classified PROVEN / PARTIALLY_PROVEN / UNPROVEN against a test "
        "that fails when the SOURCE is wrong, never against a test that merely carries the "
        "item's name. The six items W5 found unproven or half-proven "
        "(#1 schema-registration completeness, #11 the /usr/bin/python3 and alr_shadow "
        "identities, #12 the observer role, #15 the encoded-secret forms, #16 the four "
        "components S2.4 does not install, #29 the inactive postcheck's claim surface) are "
        "folded below as live re-derivations, so deleting the source predicate breaks this "
        "wave exit and not only a test"
    ),
    "secret_scan_contract": (
        "assert_no_secret_material walks dicts (keys AND values), lists, tuples, str and "
        "bytes recursively and matches the sentinel in raw, base64, base16 upper, base16 "
        "lower, urlsafe-base64 and hex form. Before W5 only the raw form was exercised by any "
        "test, so removing the four encoded forms left the whole tree green while a "
        "base64-rendered DSN could reach a serializable verdict (§10.5 #15)"
    ),
    "pg_role_identity_contract": (
        "pg_acl_manifest_v1.role_name is a schema-level const of aiml_engine_scanner, so the "
        "single SQL generation point, the revoke sequence and drop_task_owned_role can only "
        "ever name that role; a manifest naming aiml_observer_ro is a central-gate rejection "
        "before any driver contact, and the drop path additionally requires created_role, so "
        "S2.4 can neither create, drop nor revoke the S1.1 observer identity (§10.5 #12)"
    ),
    "component_scope_contract": (
        "§2: S2.4 provisions the engine-scanner vertical slice only. The five APPLY rows, the "
        "seven v2 component classes and the closed ACL manifest carry no controller, "
        "fit_evaluation, serving or deleter identity, so WP4 cannot activate a component whose "
        "owning session has not shipped (§10.5 #16)"
    ),
    "inactive_postcheck_contract": (
        "s2_4_install_postcheck_v1 and s2_4_install_effect_receipt_v1 are closed schemas whose "
        "property sets contain no runtime-directory-exists and no decrypted-credential claim, "
        "and the aggregate driver surface refuses enable/start/restart/kill: S2.4 observes "
        "loaded+disabled+inactive and nothing else. `enable --now`, enabled/reboot persistence "
        "and rollback-to-disabled belong to S2.5A, which has no source in this repository yet "
        "(§10.5 #29)"
    ),
    "rendered_unit_identity_contract": (
        "the rendered unit is byte-compared against the code-owned rendering, so substituting "
        "the system interpreter /usr/bin/python3 for the content-addressed launch interpreter, "
        "or the retired user-level alr_shadow identity for aiml-engine-scanner, is a typed "
        "ENGINE_SCANNER_UNIT_INVALID. §12 #3 forbids system Python and a mutable checkout in "
        "the production unit; before W5 neither substitution had an explicit negative "
        "(§10.5 #11)"
    ),
    "schema_registration_contract": (
        "every S2.4 schema named by §10.1 is registered in the central SCHEMA_FILES delegation "
        "table and resolves to a real file, so a schema can never be shipped outside the "
        "central gate. The §10.1 owned-path inventory is now complete: the one path that was "
        "missing when W5 opened, s2_4_dependency_refresh_attestation_v1, exists, is registered "
        "and has a central branch (§10.5 #1 / §9.2)"
    ),
    "dependency_refresh_contract": (
        "§9.2: an expired S2.2A/S2.3/S1.3 SOURCE identity is admitted only together with ONE "
        "current s2_4_dependency_refresh_attestation_v1 whose semantic digests the VERIFIER "
        "recomputes itself, at the exact current head, from the reviewed producer SSOT, and "
        "which must equal BOTH the refresh's claim and the original receipt's own values. The "
        "refresh therefore cannot be minted from the original digest alone, cannot change any "
        "semantic digest, cannot be produced inside the original's own observation window or "
        "by the same producer label, cannot refresh another refresh (closed enum) and cannot "
        "self-declare a status. Everything §9.2 marks as freshly observed, freshly re-hashed "
        "or newly signed — S2.0 effect, PG topology, both scoped capability probes, the "
        "prepared bundle and all four operator permits — is a closed NEVER_REFRESHABLE table "
        "that returns DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN for any refresh at all "
        "(§10.5 #28, both halves; §12 #15). No SSHSIG: §9.2 names four bindings and no "
        "signature, §9.1 closes the profile set at four, and the unforgeable half of this "
        "gate is the verifier's own recomputation"
    ),
    "boundary_contract": (
        "W5 produces no runtime, host, production-PostgreSQL or effect evidence of any kind. "
        "Every disposable lane runs against a throwaway cluster created by initdb in a temp "
        "directory; the target-host probe lane needs Linux plus systemd-run and skips honestly "
        "on macOS. A green W5 licenses SOURCE_READY only, never an install claim"
    ),
    # ── §10.3 誠實面:W5 **不**提供、且不得被當成已提供的義務。 ──────────────────
    # 每一項都帶 typed 狀態與 owner;W4 交出的十二項逐條在此重述並更新 owner/理由,
    # 加上 W5 自審新發現的四項。任何一項被靜默刪除都會弄破本 wave 的 exported-ABI digest。
    "remaining_owned_obligations": [
        {
            "obligation_id": "ENCRYPTED_BLOB_DIGEST_ORDERING",
            "typed_status": "OPEN_DESIGN_QUESTION",
            "owner_wave": "W6",
            "spec_refs": ["§5.1", "§7"],
            "statement": (
                "CREDENTIAL_INSTALL's signed intent must carry encrypted_blob_digest, but that "
                "digest is the hash of non-deterministic `systemd-creds encrypt` output. W5 "
                "confirms the question is unchanged: the fail-closed encrypt-then-compare "
                "binding still holds and no source change can decide whether the intent is "
                "signed before or after the encryption runs. It is an operator/W6 sequencing "
                "decision about a real host."
            ),
            "w5_provides": "nothing new; carried forward unchanged from W3/W4",
        },
        {
            "obligation_id": "OBSERVER_SPACE_PRE_STATE_DIGEST",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§5.2", "§5.4", "§6"],
            "statement": (
                "The plan-side digest space is defined and enforced (W4b). The observer side "
                "still needs a W6B postcheck driver contract requiring the verifier to return "
                "canonical_digest over the SAME code-owned per-row pre-state projection shape. "
                "W5 cannot close it: verifying that contract needs a real host observer, and no "
                "runtime evidence exists anywhere in S2.4."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "PRIOR_LINEAGE_ENTRY_IDENTITY",
            "typed_status": "NOT_PROVIDED_BY_W5",
            "owner_wave": "W6B",
            "spec_refs": ["§5.1", "§9.1"],
            "statement": (
                "APPLY requires a non-empty replay ledger but cannot verify WHICH permits the "
                "prior entries consumed, because probe_id/prepare_id are not carried in the "
                "install plan. Closing it needs either the W6B runner threading the probe/"
                "PREPARE authorization ids into the APPLY inputs, or a s2_4_install_plan_core_v1 "
                "field — a schema change §10.4 forbids the worker from choosing. Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "PLAN_EXPIRY_OUTSIDE_SIGNED_CORE",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§9", "§9.2", "§10.4", "§10.5 #28"],
            "statement": (
                "s2_4_install_plan_v1.expires_at lives outside core, so it is not covered by the "
                "operator signature. The reachable half is closed (expired plan refused before "
                "any lock/mutation; every TTL bound derived from each artifact's own "
                "expires_at). Moving expires_at inside core is a s2_4_install_plan_core_v1 "
                "schema change §10.4 forbids. Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "INSTALLED_UNIT_PROBE_CORE_BINDING",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§6", "§10.4", "§10.5 #36"],
            "statement": (
                "expected_installed_unit_probe_core_digest is optional at the API and MANDATORY "
                "for the W6 runner; omission is visible as "
                "UNVERIFIED_NO_EXPECTED_VALUE_SUPPLIED on every verdict. Closing it means the "
                "W6B runner always supplying it or adding a plan-core field. Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "EFFECT_RECEIPT_RECONCILE_BINDING",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§5.2", "§10.4"],
            "statement": (
                "s2_4_install_effect_receipt_v1 has no field for the startup-reconcile verdict "
                "and the schema is additionalProperties:false. W4b binds all three signals into "
                "the durable evidence set beside the journal; a consumer holding only the "
                "receipt still cannot re-derive the reconcile verdict. Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "STARTUP_RECONCILE_SURFACE_ABSENT",
            "typed_status": "OPEN_BY_DESIGN_W6_RUNNER_PRECONDITION",
            "owner_wave": "W6",
            "spec_refs": ["§5.2", "§10.5 #39"],
            "statement": (
                "A host driver not wrapped by JournalRoutedDriver has no durable journal "
                "surface, so reconcile_before_new_intent returns "
                "STARTUP_RECONCILE_SURFACE_ABSENT with admits_new_work=None. The W6 runner MUST "
                "inject a journal-routed driver into the probe and PREPARE entry points. "
                "Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "STARTUP_JOURNAL_PARENTS_MUST_PREEXIST",
            "typed_status": "NOT_PROVIDED_BY_W5",
            "owner_wave": "W6B",
            "spec_refs": ["§5.2"],
            "statement": (
                "On a fresh host the three §5.2 journal parents do not exist, so startup "
                "reconciliation returns RECOVERY_REQUIRED and nothing in S2.4 can start until "
                "an operator pre-creates .../s2_4, .../s2_4/probes and .../s2_4/prepared "
                "root-owned 0700. This is an OPERATOR PRECONDITION for the W6 runbook, not a "
                "defect to be fixed by giving the journal surface a mkdir capability. "
                "Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "RECEIPT_EMISSION_PENDING_IS_NOT_A_RECEIPT_RETRY",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§10.5 #8", "§10.5 #14"],
            "statement": (
                "A terminal, complete install can permanently have no receipt: the journal does "
                "not carry the row result/postcheck digests the receipt binds, so "
                "ALREADY_APPLIED_IDEMPOTENT cannot reconstruct it. Actually emitting the "
                "receipt on retry is an artifact-shape decision belonging to the W6B runner. "
                "Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "STRANDED_WAL_TEMP_FILES_ARE_REPORT_ONLY",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§5.2"],
            "statement": (
                "The §5.2 startup enumeration matches, lists and names stranded WAL temp "
                "residue and blocks new work while it exists, but §5.2 forbids this surface "
                "from renaming or removing anything, so clearing it is an operator runbook "
                "step. Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED",
            "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
            "owner_wave": "W6B",
            "spec_refs": ["§9.1", "§10.2"],
            "statement": (
                "W5 reviewed this one line by line because it READS like a source fix. It is "
                "not, and W5's first draft of this correction was itself wrong and is recorded "
                "here rather than silently rewritten. BOTH halves W4 named are still open. "
                "(a) Nothing compares the OBSERVED moment against attestation_expires_at: "
                "derive_apply_attestation_status deliberately excludes the caller's now, so an "
                "attestation whose own expiry has passed still verifies as long as its SIGNED "
                "trusted_host_time sits inside both permit windows. (b) The attestation's "
                "SIGNED trusted_host_time is still never reconciled with the value "
                "driver.trusted_host_time() returned for the same transaction — verified by "
                "reading agent_governance_s2_4_install_evidence.derive_apply_attestation_status, "
                "which compares the signed time only against attestation_expires_at, the 900s "
                "attestation TTL and the two permit windows. What DOES exist, and what W4's "
                "statement omitted, is a DIFFERENT and weaker relation that W5 adds to the "
                "record: agent_governance_s2_4_install_driver._trusted_host_time_reasons "
                "cross-checks driver.trusted_host_time() against the observed moment under the "
                "§9.1 PERMIT_CLOCK_SKEW_SECONDS ceiling (regression: "
                "test_c18_the_trusted_host_time_is_cross_checked_against_the_observed_time). "
                "That bounds the DRIVER's clock, not the attestation's signed value. The "
                "residual is therefore smaller than W4 implied but non-zero: the signed "
                "trusted_host_time is still bounded indirectly, because it must fall inside two "
                "independently signed permit windows that are themselves capped at 900s. "
                "Closing either half needs a decision about WHICH clock is authoritative for "
                "the observed moment on a real host (§9.1 says the host's, and on a real host "
                "the two values come from the same clock); in a source lane where both are "
                "fixtures the question is unanswerable, and wiring the caller's now into the "
                "freshness derivation would REVERSE the W4b property that freshness comes only "
                "from the SIGNED trusted_host_time."
            ),
            "w5_provides": (
                "the line-verified confirmation that both halves are still open (W4's statement "
                "stands), the previously unrecorded driver-clock skew ceiling and its named "
                "regression, the observation that the two 900s permit windows bound the residual, "
                "and the explicit reason this is not a source change"
            ),
        },
        {
            "obligation_id": "ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY",
            "typed_status": "NOT_PROVIDED_BY_W5",
            "owner_wave": "W6B",
            "spec_refs": ["§9.1", "§10.2"],
            "statement": (
                "One physical Ed25519 key roots both the four operator permit profiles and the "
                "apply attestation. Domain separation is namespace-level and real; CUSTODY is "
                "not separated. The fix is a separate attestor keypair with its own pinned "
                "fingerprint, which is a W6 key-custody decision about a real host. W5 confirms "
                "no source change can establish it: the source lane has no key material at all."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "REPLAY_LEDGER_CONSUME_ONCE_IS_A_FILESYSTEM_PROPERTY",
            "typed_status": "OPEN_HONEST_BOUNDARY",
            "owner_wave": "W6B",
            "spec_refs": ["§9.1", "§10.5 #8"],
            "statement": (
                "Ledger rollback and forking are prevented by the root-owned 0700 parent, the "
                "0600 mode and the exclusive install lock, not cryptographically. Closing it "
                "needs a monotonic counter in trusted storage or an attestor-signed ledger "
                "head. Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        {
            "obligation_id": "STARTUP_RECONCILE_LANE_PATHS",
            "typed_status": "NOT_PROVIDED_BY_W5",
            "owner_wave": "W6B",
            "spec_refs": ["§5.2"],
            "statement": (
                "Enumeration sees every non-terminal journal in the three parents, but the "
                "caller's paths still decide which lane receives the independent observation "
                "digest and per-lane ownership key. Closing that half means the W6B runner "
                "passing the probe_id/prepare_id-derived paths it already holds. Unchanged."
            ),
            "w5_provides": "nothing new; owner unchanged",
        },
        # ── W5 自審新增的四項 ────────────────────────────────────────────────────
        {
            "obligation_id": "DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT",
            "typed_status": "NOT_PROVIDED_BY_W5",
            "owner_wave": "PM",
            "spec_refs": ["§3", "§10.4", "§11.3"],
            "statement": (
                "The §9.2 gate itself is now built and load-bearing (schema, central branch, "
                "verifier-side recomputation, builder, tests), so §11.2's 'complete source "
                "inventory' is no longer false and §10.5 #28's first half is PROVEN. What is "
                "NOT closed is the receipt binding: §3 requires the terminal "
                "s2_4_install_effect_receipt_v1 to reference 'source_admission_receipt, W0-W5 "
                "wave-chain and DEPENDENCY-REFRESH digests', and that closed "
                "additionalProperties:false schema has no field for them — a consumer holding "
                "only the install receipt cannot see which refreshes admitted the expired "
                "source identities. Adding the field is an exported-schema change §10.4 "
                "forbids the worker from choosing, exactly like PLAN_EXPIRY_OUTSIDE_SIGNED_CORE "
                "and EFFECT_RECEIPT_RECONCILE_BINDING. Until PM rules, the refresh verdicts are "
                "reachable only through derive_source_dependency_admission_status at APPLY "
                "time, never from the persisted receipt."
            ),
            "w5_provides": (
                "the complete §9.2 gate (four refreshable classes, nine never-refreshable "
                "classes, verifier-side reproduction, one-refresh rule) and the exact residual: "
                "the terminal receipt has nowhere to carry the refresh digests §3 names"
            ),
        },
        {
            "obligation_id": "DEPENDENCY_REFRESH_REPRODUCER_NODE_IS_DECLARATIVE",
            "typed_status": "PARTIALLY_PROVIDED_BY_W5",
            "owner_wave": "W6",
            "spec_refs": ["§9.1", "§9.2"],
            "statement": (
                "§9.2 requires an INDEPENDENT replay. W5 makes two halves of that structural "
                "and one half declarative, and says which is which. STRUCTURAL and unforgeable: "
                "the semantic digests are recomputed BY THE VERIFIER from the repository at the "
                "bound head and must equal both the refresh's claim and the original's own "
                "values, so a refresh can never be minted from the original digest; and "
                "reproduced_at must be strictly after the original evidence's own expiry, so "
                "the same observation cannot be restated as a refresh. DECLARATIVE: that the "
                "reproducing NODE differs from the producing node rests on reproducer_caller "
                "not equalling the original's producer label, which a hostile producer can "
                "simply relabel. The source lane holds no key material at all (see "
                "ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY), so node custody cannot be "
                "established here; closing it means a per-node attestor identity, which is a "
                "W6 key-custody decision about real hosts. A second, smaller asymmetry is "
                "recorded rather than hidden: source_compatibility_receipt_v1/v2 carry no "
                "'caller' or 'platform' field at all, so for S2.2A the producer label degrades "
                "to session_id ('S2.2A') and the platform component of the projection is null."
            ),
            "w5_provides": (
                "the verifier-side recomputation and the strictly-after-expiry rule as the two "
                "unforgeable halves, the caller inequality as the declared half, and the exact "
                "statement of what a relabelling producer could still do"
            ),
        },
        {
            "obligation_id": "PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED",
            "typed_status": "NOT_PROVIDED_BY_W5",
            "owner_wave": "W6B",
            "spec_refs": ["§7", "§10.5 #26"],
            "statement": (
                "§10.5 #26 requires PR_SET_DUMPABLE=0 to be LOAD-BEARING. It is not. "
                "PROCESS_HARDENING_CONTRACT['pr_set_dumpable'] = 0 is a declared constant that "
                "appears in exactly two projection dicts and in nothing else: "
                "derive_host_credential_capability_status checks systemd_creds_available, "
                "tpm2_available and decryption_name_verification and never looks at it, and no "
                "driver protocol method observes it. The pre-existing test named "
                "test_process_hardening_contract_is_load_bearing asserts the constant equals "
                "itself, which is exactly the failure mode this wave was sent to find. The "
                "other four clauses of #26 ARE load-bearing: --with-key=host+tpm2 is enforced "
                "through tpm2_available, the encrypted-blob fingerprint is re-derived and "
                "compared, the closed eight-key DSN set is enforced, and LimitCORE=0 plus the "
                "PG*/LD*/PYTHON* scrub are enforced by the unit's byte-equality check. Closing "
                "this one means observing prctl(PR_GET_DUMPABLE) on the applier and refusing "
                "when it is not 0 — a driver-protocol and host-observation change, i.e. "
                "production implementation on a real host, not a test."
            ),
            "w5_provides": (
                "the finding, the exact reason the existing test is tautological, and the "
                "honest classification of §10.5 #26 as PARTIALLY PROVEN"
            ),
        },
        {
            "obligation_id": "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST",
            "typed_status": "OUT_OF_WP4_SCOPE",
            "owner_wave": "S2.5A",
            "spec_refs": ["§10.5 #29", "§11.3"],
            "statement": (
                "§10.5 #29's second clause says 'S2.5 fixtures own `enable --now`, "
                "enabled/reboot persistence and rollback-to-disabled'. No S2.5 source or "
                "fixture exists in this repository, so that clause has no owner in WP4 and "
                "cannot be satisfied here. What W5 CAN and does prove is the S2.4 half: the "
                "aggregate driver surface refuses enable/start/restart/kill, the closed "
                "postcheck and receipt schemas carry no runtime-directory or "
                "decrypted-credential property, and an enabled or active observation is never "
                "a success. The clause is recorded rather than counted as covered."
            ),
            "w5_provides": (
                "the S2.4 half as a live re-derivation and the explicit statement that the S2.5 "
                "half has no owner in this work package"
            ),
        },
        {
            "obligation_id": "OWNED_PATH_PROJECTION_RULER_IS_NOT_UNIFORM",
            "typed_status": "RECORDED_NOT_ABSORBED",
            "owner_wave": "PM",
            "spec_refs": ["§10.3"],
            "statement": (
                "W0/W1/W2 and W5 project owned-path content from the BOUND COMMIT's blobs "
                "(owned_path_blob_projection_digest), which is the corrected form W2's review "
                "landed after finding that a projection over working-tree bytes lets a receipt "
                "certifying an unchanged HEAD be self-consistent on a dirty tree. W3 and W4 "
                "still hash working-tree bytes through their own _file_sha256. Every wave "
                "remains internally self-consistent, so no chain derivation is wrong today, but "
                "two different rulers are in use across one receipt chain. W5 does not change "
                "aiml_gate_receipt_wave_w3.py or _w4.py: they are W3/W4-owned files and "
                "unifying them is a PM path-scope call, not a test-writer's."
            ),
            "w5_provides": (
                "the corrected ruler for W5's own projection plus owned_scope_worktree_delta "
                "visibility, and this explicit record of the divergence"
            ),
        },
    ],
}


def _secret_scan_live() -> dict[str, Any]:
    """§10.5 #15:秘密掃描的**編碼形**與遞迴面的活再導出。"""

    import base64

    import agent_governance_s2_4_credential as _credential

    live: dict[str, Any] = {}
    secret = "aiml-w5-sentinel-not-a-real-credential"
    raw = secret.encode("utf-8")
    forms = {
        "raw": secret,
        "base64": base64.b64encode(raw).decode("ascii"),
        "base16_upper": base64.b16encode(raw).decode("ascii"),
        "base16_lower": base64.b16encode(raw).decode("ascii").lower(),
        "urlsafe_base64": base64.urlsafe_b64encode(raw).decode("ascii"),
        "hex": raw.hex(),
    }
    try:
        detected: dict[str, bool] = {}
        for name, form in forms.items():
            # 每一種形都藏在**巢狀** artifact 的深處(list -> dict -> str)。
            artifact = {"reasons": [{"detail": f"observed dsn={form}"}]}
            try:
                _credential.assert_no_secret_material(artifact, [secret])
                detected[name] = False
            except _credential.SecretMaterialLeak:
                detected[name] = True
        live["encoded_forms_detected"] = detected
        # dict 的**鍵**也必須被走訪(舊碼曾只走值)。
        try:
            _credential.assert_no_secret_material({forms["base64"]: "x"}, [secret])
            live["dict_key_is_scanned"] = False
        except _credential.SecretMaterialLeak:
            live["dict_key_is_scanned"] = True
        # bytes 節點同樣被走訪。
        try:
            _credential.assert_no_secret_material({"blob": raw}, [secret])
            live["bytes_node_is_scanned"] = False
        except _credential.SecretMaterialLeak:
            live["bytes_node_is_scanned"] = True
        # 乾淨 artifact 絕不誤報(掃描器不是恆真)。
        _credential.assert_no_secret_material(
            {"reasons": ["nothing sensitive here"], "digest": "sha256:" + "0" * 64}, [secret]
        )
        live["clean_artifact_passes"] = True
        # 沒有哨兵 = 沒有可掃的東西(而不是拒絕一切)。
        _credential.assert_no_secret_material({"reasons": [secret]}, [])
        live["no_sentinel_is_a_noop"] = True
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        for key in (
            "encoded_forms_detected",
            "dict_key_is_scanned",
            "bytes_node_is_scanned",
            "clean_artifact_passes",
            "no_sentinel_is_a_noop",
        ):
            live.setdefault(key, None)
    return live


def _pg_role_identity_live() -> dict[str, Any]:
    """§10.5 #12:``aiml_observer_ro`` 連被 S2.4 命名的資格都沒有的活再導出。"""

    import json as _json

    live: dict[str, Any] = {}
    facade = resolve_facade()
    try:
        schema = facade._load_schema("pg_acl_manifest_v1")
        live["manifest_role_name_const"] = schema["properties"]["role_name"].get("const")
        live["manifest_component_const"] = schema["properties"]["component"].get("const")
        manifest_path = (
            REPO_ROOT / "program_code" / "ml_training" / "pg_acl_manifest_v1.json"
        )
        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
        live["shipped_manifest_role_name"] = manifest.get("role_name")
        # observer 身分的 manifest:中央閘在任何 driver 接觸之前就必須拒。
        forged = dict(manifest)
        forged["role_name"] = _OBSERVER_ROLE
        forged["self_digest"] = facade.artifact_self_digest(forged)
        live["observer_named_manifest_is_centrally_rejected"] = bool(
            facade.validate_aiml_artifact(forged)
        )
        # 生成/收回序列只會提到 manifest 的那一個角色;observer 永不出現。
        import agent_governance_s2_4_apply as _apply

        grants = _apply.generate_manifest_grant_statements(manifest)
        revokes = _apply.generate_manifest_revoke_statements(manifest)
        live["grant_statement_count"] = len(grants)
        statements = list(grants) + list(revokes)
        live["observer_absent_from_generated_sql"] = not any(
            _OBSERVER_ROLE in statement for statement in statements
        )
        # 每一句的**授受方**只能是 scanner 角色本身,或 §2.1 封閉邊界要收回的 PUBLIC;
        # 任何第三個具名角色出現在生成序列裡,即代表 S2.4 能作用在別人的身分上。
        live["grantee_vocabulary"] = sorted({
            f'"{_SCANNER_ROLE}"' if f'"{_SCANNER_ROLE}"' in statement
            else ("PUBLIC" if statement.rstrip().endswith("FROM PUBLIC") else statement)
            for statement in statements
        })
        live["every_generated_statement_names_the_scanner_role_or_public"] = all(
            f'"{_SCANNER_ROLE}"' in statement or statement.rstrip().endswith("FROM PUBLIC")
            for statement in statements
        )
    except Exception:  # noqa: BLE001
        for key in (
            "manifest_role_name_const",
            "manifest_component_const",
            "shipped_manifest_role_name",
            "observer_named_manifest_is_centrally_rejected",
            "grant_statement_count",
            "observer_absent_from_generated_sql",
            "grantee_vocabulary",
            "every_generated_statement_names_the_scanner_role_or_public",
        ):
            live.setdefault(key, None)
    return live


def _component_scope_live() -> dict[str, Any]:
    """§10.5 #16:WP4 不含 controller/fit_evaluation/serving/deleter 的活再導出。"""

    live: dict[str, Any] = {}
    try:
        import agent_governance_s2_4_install_driver as _runner
        from aiml_gate_receipt_classifiers import AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2

        live["apply_row_order"] = list(_runner.APPLY_ROW_ORDER)
        live["v2_component_classes"] = sorted(AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2)
        haystack = " ".join(
            list(_runner.APPLY_ROW_ORDER)
            + sorted(AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2)
            + sorted(_runner.ROW_APPLIER_NODES.values())
        ).lower()
        live["forbidden_component_identities_absent"] = {
            name: name not in haystack for name in _FORBIDDEN_COMPONENT_IDENTITIES
        }
        live["row_count"] = len(_runner.APPLY_ROW_ORDER)
    except Exception:  # noqa: BLE001
        for key in (
            "apply_row_order",
            "v2_component_classes",
            "forbidden_component_identities_absent",
            "row_count",
        ):
            live.setdefault(key, None)
    return live


def _inactive_postcheck_live() -> dict[str, Any]:
    """§10.5 #29:S2.4 的 inactive postcheck 不挾帶 runtime-dir / 已解密憑證宣稱。"""

    live: dict[str, Any] = {}
    facade = resolve_facade()
    forbidden_markers = ("runtime_director", "decrypt", "enabled", "active", "running")
    try:
        import agent_governance_s2_4_install_driver as _runner

        for key, label in (
            ("s2_4_install_postcheck_v1", "postcheck"),
            ("s2_4_install_effect_receipt_v1", "receipt"),
        ):
            schema = facade._load_schema(key)
            properties = sorted(schema.get("properties", {}))
            live[f"{label}_properties"] = properties
            live[f"{label}_additional_properties_closed"] = (
                schema.get("additionalProperties") is False
            )
            live[f"{label}_carries_no_lifecycle_claim"] = not any(
                marker in name for name in properties for marker in forbidden_markers
            )
        forbidden = sorted(set(_runner.FORBIDDEN_AGGREGATE_METHODS))
        live["aggregate_forbidden_methods"] = forbidden
        live["enable_and_start_are_forbidden"] = {
            name: name in forbidden
            for name in ("enable", "enable_unit", "start", "start_unit", "restart", "kill")
        }
        live["s2_5_lifecycle_source_absent"] = not (
            REPO_ROOT / "docs" / "execution_plan" / "ai_ml_landing" / "design"
        ).joinpath("S2.5-start-source-seams.md").exists()
    except Exception:  # noqa: BLE001
        for key in (
            "postcheck_properties",
            "postcheck_additional_properties_closed",
            "postcheck_carries_no_lifecycle_claim",
            "receipt_properties",
            "receipt_additional_properties_closed",
            "receipt_carries_no_lifecycle_claim",
            "aggregate_forbidden_methods",
            "enable_and_start_are_forbidden",
            "s2_5_lifecycle_source_absent",
        ):
            live.setdefault(key, None)
    return live


def _rendered_unit_negative_live() -> dict[str, Any]:
    """§10.5 #11 / §12 #3:system Python 與 alr_shadow 身分的 typed 拒絕活再導出。"""

    live: dict[str, Any] = {}
    try:
        import agent_governance_s2_4_render as _render

        rendered = _render.render_engine_scanner_unit(dict(_W5_UNIT_FIELDS))
        live["clean_unit_status"] = _render.derive_rendered_unit_status(rendered)["status"]
        launch_prefix = "/opt/arcane-equilibrium/aiml/launches/"
        live["execstart_is_content_addressed"] = (
            f"ExecStart={launch_prefix}" in rendered
            and "ExecStart=/usr/bin/python3" not in rendered
        )
        # 1) system interpreter 取代 content-addressed launch interpreter。
        interpreter_line = next(
            line for line in rendered.splitlines() if line.startswith("ExecStart=")
        )
        system_python = rendered.replace(
            interpreter_line,
            "ExecStart=/usr/bin/python3 -I -B \\",
        )
        live["system_interpreter_status"] = _render.derive_rendered_unit_status(
            system_python
        )["status"]
        # 2) 已退役的 user-level alr_shadow 身分。
        shadow = rendered.replace(
            "User=aiml-engine-scanner", "User=alr_shadow"
        ).replace("Group=aiml-engine-scanner", "Group=alr_shadow")
        live["alr_shadow_identity_status"] = _render.derive_rendered_unit_status(
            shadow
        )["status"]
        # 3) 可變 checkout 的 WorkingDirectory(§12 #3)。
        checkout = rendered.replace(
            "WorkingDirectory=/var/lib/arcane-equilibrium/aiml/engine-scanner",
            "WorkingDirectory=/home/ncyu/BybitOpenClaw/srv",
        )
        live["mutable_checkout_status"] = _render.derive_rendered_unit_status(
            checkout
        )["status"]
        live["alr_shadow_absent_from_clean_unit"] = "alr_shadow" not in rendered
    except Exception:  # noqa: BLE001
        for key in (
            "clean_unit_status",
            "execstart_is_content_addressed",
            "system_interpreter_status",
            "alr_shadow_identity_status",
            "mutable_checkout_status",
            "alr_shadow_absent_from_clean_unit",
        ):
            live.setdefault(key, None)
    return live


def _schema_registration_live(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """§10.5 #1 / §9.2:每份 S2.4 schema 都在中央閘上;缺席那一份被指名。"""

    live: dict[str, Any] = {}
    facade = resolve_facade()
    try:
        schema_files = facade.SCHEMA_FILES
        schema_dir = repo_root / _SCHEMA_DIR_REL
        live["s2_4_schema_count"] = len(_S2_4_SCHEMA_KEYS)
        live["unregistered_schema_keys"] = sorted(
            key for key in _S2_4_SCHEMA_KEYS if key not in schema_files
        )
        live["unresolvable_schema_keys"] = sorted(
            key
            for key in _S2_4_SCHEMA_KEYS
            if key in schema_files and not (schema_dir / schema_files[key]).is_file()
        )
        # 反向:磁碟上多出一份 S2.4 schema 而沒進宣告集合(= 沒人 round-trip 它),同樣必須
        # 弄破 wave exit,而不只是弄紅一支測試。
        on_disk = {
            path.name[: -len(".schema.json")]
            for path in schema_dir.glob("*.schema.json")
            if path.name.startswith(("s2_4_", "pg_acl_", "pg_topology_"))
        }
        live["undeclared_on_disk_schema_keys"] = sorted(
            on_disk - set(_S2_4_SCHEMA_KEYS) - {_DEPENDENCY_REFRESH_SCHEMA}
        )
        # §10.1 明列卻不存在的那一份:誠實地折成值,而不是被略過。
        live["dependency_refresh_schema_key"] = _DEPENDENCY_REFRESH_SCHEMA
        live["dependency_refresh_schema_registered"] = (
            _DEPENDENCY_REFRESH_SCHEMA in schema_files
        )
        live["dependency_refresh_schema_file_exists"] = (
            schema_dir / f"{_DEPENDENCY_REFRESH_SCHEMA}.schema.json"
        ).is_file()
    except Exception:  # noqa: BLE001
        for key in (
            "s2_4_schema_count",
            "unregistered_schema_keys",
            "unresolvable_schema_keys",
            "undeclared_on_disk_schema_keys",
            "dependency_refresh_schema_key",
            "dependency_refresh_schema_registered",
            "dependency_refresh_schema_file_exists",
        ):
            live.setdefault(key, None)
    return live


_DEPENDENCY_REFRESH_LIVE_KEYS = (
    "refreshable_classes",
    "never_refreshable_classes",
    "reproducible_class_field_sets",
    "central_gate_accepts_the_positive_refresh",
    "positive_refresh_status",
    "positive_admission_status",
    "expired_without_refresh_status",
    "reasserted_original_digest_status",
    "same_producer_node_status",
    "refresh_of_a_refresh_status",
    "builder_refuses_a_refresh_of_a_refresh",
    "self_declared_status_status",
    "substituted_original_status",
    "stale_head_status",
    "semantic_digest_drift_status",
    "two_refreshes_status",
    "never_refreshable_statuses",
    "refresh_carries_no_signature_field",
)


def _dependency_refresh_live(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """§9.2 / §10.5 #28:過期 source 身分的獨立復現閘,逐個失敗模式的活再導出。

    正向用的是 repo 內**真實且已過期**的 S2.2A receipt(非合成 fixture);時鐘為 code-owned
    固定常量,故投影跨時可重現。每一個負向都對應 §9.2 的一句話。
    """

    import json as _json

    live: dict[str, Any] = {}
    facade = resolve_facade()
    try:
        original = _json.loads(
            (repo_root / _S2_2A_RECEIPT_V1_REL).read_text(encoding="utf-8")
        )
        other_original = _json.loads(
            (repo_root / _S2_2A_RECEIPT_V2_REL).read_text(encoding="utf-8")
        )
        live["refreshable_classes"] = sorted(facade.S2_4_DEPENDENCY_REFRESH_CLASSES)
        live["never_refreshable_classes"] = sorted(facade.S2_4_NEVER_REFRESHABLE_EVIDENCE)
        # 四族的語義欄位集都必須真的能由當前 checkout 重算出來(缺一族 = 該族無法被續命)。
        field_sets: dict[str, Any] = {}
        for name, row in sorted(facade.S2_4_DEPENDENCY_REFRESH_CLASSES.items()):
            try:
                reproduced = facade.reproduce_dependency_semantic_digests(
                    name,
                    original_schema_version=row["original_schema_versions"][0],
                    repo_root=repo_root,
                )
                field_sets[name] = sorted(reproduced)
            except Exception:  # noqa: BLE001
                field_sets[name] = None
        live["reproducible_class_field_sets"] = field_sets

        def _build(**overrides: Any) -> dict[str, Any]:
            return facade.build_s2_4_dependency_refresh_attestation(
                overrides.pop("original_receipt", original),
                reproducer_caller=overrides.pop(
                    "reproducer_caller", _DEPENDENCY_REFRESH_PROBE_CALLER
                ),
                reproducer_platform=dict(_DEPENDENCY_REFRESH_PROBE_PLATFORM),
                reproduced_at=_DEPENDENCY_REFRESH_PROBE_REPRODUCED_AT,
                repo_root=repo_root,
                **overrides,
            )

        def _status(refresh: Any, original_receipt: Any = None) -> str:
            return facade.derive_dependency_refresh_status(
                refresh,
                original_receipt=original if original_receipt is None else original_receipt,
                now=_DEPENDENCY_REFRESH_PROBE_NOW,
                repo_root=repo_root,
            )["status"]

        def _reseal(artifact: dict[str, Any]) -> dict[str, Any]:
            artifact = dict(artifact)
            artifact.pop("self_digest", None)
            artifact["self_digest"] = facade.artifact_self_digest(artifact)
            return artifact

        refresh = _build()
        live["central_gate_accepts_the_positive_refresh"] = (
            facade.validate_aiml_artifact(refresh) == []
        )
        live["positive_refresh_status"] = _status(refresh)
        live["positive_admission_status"] = facade.derive_source_dependency_admission_status(
            evidence_class="S2_2A_SOURCE_COMPATIBILITY",
            receipt=original,
            refresh=refresh,
            now=_DEPENDENCY_REFRESH_PROBE_NOW,
            repo_root=repo_root,
        )["status"]
        live["expired_without_refresh_status"] = (
            facade.derive_source_dependency_admission_status(
                evidence_class="S2_2A_SOURCE_COMPATIBILITY",
                receipt=original,
                now=_DEPENDENCY_REFRESH_PROBE_NOW,
                repo_root=repo_root,
            )["status"]
        )
        # 1) 只把舊 digest 再抄一次(§9.2:independently RECOMPUTED,不是複述)。
        reasserted = _reseal({
            **refresh,
            "reproduced_semantic_digests": {
                field: refresh["original_receipt_digest"]
                for field in refresh["reproduced_semantic_digests"]
            },
        })
        live["reasserted_original_digest_status"] = _status(reasserted)
        # 2) 由原 receipt 的同一個 producer 標籤產出。
        same_node = _build(reproducer_caller=original["session_id"])
        live["same_producer_node_status"] = _status(same_node)
        # 3) refresh 去 refresh 另一份 refresh(閘拒 + builder 亦拒)。
        live["refresh_of_a_refresh_status"] = _status(refresh, refresh)
        try:
            _build(original_receipt=refresh)
            live["builder_refuses_a_refresh_of_a_refresh"] = False
        except ValueError:
            live["builder_refuses_a_refresh_of_a_refresh"] = True
        # 4) caller 自證 status。
        live["self_declared_status_status"] = _status({**refresh, "status": "ADMITTED"})
        # 5) 被替換掉的原身分(v1 的 refresh 拿 v2 receipt 來對)。
        live["substituted_original_status"] = _status(refresh, other_original)
        # 6) 過時的 head。
        live["stale_head_status"] = _status(
            _reseal({**refresh, "current_source_head": "0" * 40})
        )
        # 7) 原 receipt 的語義 digest 已經在當前 head 上重算不出來(= 只能重新觀測)。
        drifted = _reseal({
            **original,
            "learning_runtime_digest": "sha256:" + "a" * 64,
        })
        live["semantic_digest_drift_status"] = facade.derive_dependency_refresh_status(
            _reseal({**refresh, "original_receipt_digest": facade.artifact_self_digest(drifted)}),
            original_receipt=drifted,
            now=_DEPENDENCY_REFRESH_PROBE_NOW,
            repo_root=repo_root,
        )["status"]
        # 8) 兩份 refresh(§9.2:one current refresh attestation)。
        live["two_refreshes_status"] = facade.derive_source_dependency_admission_status(
            evidence_class="S2_2A_SOURCE_COMPATIBILITY",
            receipt=original,
            refresh=[refresh, refresh],
            now=_DEPENDENCY_REFRESH_PROBE_NOW,
            repo_root=repo_root,
        )["status"]
        # 9) §10.5 #28 後半:runtime / topology / prepare / auth 一律不可引用刷新。
        live["never_refreshable_statuses"] = {
            name: facade.derive_source_dependency_admission_status(
                evidence_class=name,
                receipt={"expires_at": "2099-01-01T00:00:00+00:00"},
                refresh=refresh,
                now=_DEPENDENCY_REFRESH_PROBE_NOW,
                repo_root=repo_root,
            )["status"]
            for name in sorted(facade.S2_4_NEVER_REFRESHABLE_EVIDENCE)
        }
        # 10) 簽章判斷的可測形:closed schema 不含任何簽章面。
        schema = facade._load_schema(_DEPENDENCY_REFRESH_SCHEMA)
        live["refresh_carries_no_signature_field"] = not any(
            marker in name
            for name in schema.get("properties", {})
            for marker in ("signature", "sshsig", "namespace", "profile_identity")
        )
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        for key in _DEPENDENCY_REFRESH_LIVE_KEYS:
            live.setdefault(key, None)
    return live


def w5_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W5 exported-ABI 投影:code-owned 骨架 + 七組覆蓋缺口的活再導出。"""

    return {
        **_W5_EXPORTED_ABI,
        "owned_scope_worktree_delta": owned_scope_worktree_delta(
            repo_root, _W5_OWNED_PATHS
        ),
        "secret_scan_live": _secret_scan_live(),
        "pg_role_identity_live": _pg_role_identity_live(),
        "component_scope_live": _component_scope_live(),
        "inactive_postcheck_live": _inactive_postcheck_live(),
        "rendered_unit_negative_live": _rendered_unit_negative_live(),
        "schema_registration_live": _schema_registration_live(repo_root),
        "dependency_refresh_live": _dependency_refresh_live(repo_root),
    }


def w5_owned_path_diff_digest(
    repo_root: Path = REPO_ROOT, *, source_head: str | None = None
) -> str:
    """W5 owned-path 內容投影 digest(採 W2 修正後的 commit-blob 尺;缺 blob 記 None)。"""

    return owned_path_blob_projection_digest(
        repo_root, _W5_OWNED_PATHS, source_head=source_head
    )


def _dependency_refresh_reasons(live: dict[str, Any]) -> list[str]:
    """§9.2 活裁決逐條轉成具名 reason(任一失敗模式回到「可過」,W5 exit 必破)。"""

    reasons: list[str] = []
    if sorted(live.get("refreshable_classes") or []) != [
        "S1_3_IDENTITY_CONTRACT",
        "S2_2A_SOURCE_COMPATIBILITY",
        "S2_3_EXPECTED_IDENTITY",
        "S2_3_SEALED_BUILD",
    ]:
        reasons.append(
            "W5 §9.2 refreshable-class table is not the exact three source-identity families "
            "of the §9.2 first row (S2.2A compatibility, S2.3 sealed-build/expected-identity, "
            "S1.3 contract)"
        )
    unreproducible = sorted(
        name
        for name, fields in (live.get("reproducible_class_field_sets") or {}).items()
        if not fields
    )
    if unreproducible or not live.get("reproducible_class_field_sets"):
        reasons.append(
            "W5 cannot independently reproduce the semantic digests of "
            f"{unreproducible or 'any'} §9.2 class at the current head; a class whose "
            "producer checks cannot be replayed can never be refreshed (§9.2)"
        )
    if live.get("central_gate_accepts_the_positive_refresh") is not True:
        reasons.append("W5 central gate rejects a well-formed dependency refresh attestation")
    for key, expected, detail in (
        (
            "positive_refresh_status",
            "DEPENDENCY_REFRESH_ADMITTED",
            "one independently reproduced refresh must admit an expired source identity",
        ),
        (
            "positive_admission_status",
            "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH",
            "the expired S2.2A identity must be admitted THROUGH the refresh, not despite it",
        ),
        (
            "expired_without_refresh_status",
            "SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH",
            "an expired source identity with no refresh must not be admitted",
        ),
        (
            "reasserted_original_digest_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "a refresh that merely re-asserts the original digest is not a reproduction",
        ),
        (
            "same_producer_node_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "a refresh produced by the original's own producer label is not independent",
        ),
        (
            "refresh_of_a_refresh_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "a refresh cannot refresh another refresh",
        ),
        (
            "self_declared_status_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "no S2.4 artifact self-declares its own status",
        ),
        (
            "substituted_original_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "a substituted original identity is not the identity being refreshed",
        ),
        (
            "stale_head_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "the reproduction must be performed at the exact current head",
        ),
        (
            "semantic_digest_drift_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "a refresh cannot change any semantic digest; drifted source must be re-observed",
        ),
        (
            "two_refreshes_status",
            "SOURCE_DEPENDENCY_REJECTED",
            "§9.2 admits an expired source identity together with exactly ONE refresh",
        ),
    ):
        if live.get(key) != expected:
            reasons.append(
                f"W5 §9.2 dependency-refresh gate: {key} is {live.get(key)!r}, expected "
                f"{expected!r} — {detail}"
            )
    if live.get("builder_refuses_a_refresh_of_a_refresh") is not True:
        reasons.append(
            "W5 dependency-refresh builder accepts a refresh as its own original; §9.2 "
            "forbids refreshing a refresh at both the builder and the gate"
        )
    never = live.get("never_refreshable_statuses") or {}
    if sorted(never) != sorted(live.get("never_refreshable_classes") or []) or not never:
        reasons.append(
            "W5 never-refreshable evidence table is not exercised in full; §9.2's runtime/"
            "topology/prepare/auth rows must each refuse a refresh (§10.5 #28)"
        )
    admitted_by_reference = sorted(
        name
        for name, status in never.items()
        if status != "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN"
    )
    if admitted_by_reference:
        reasons.append(
            "W5 accepts refresh-by-reference for evidence §9.2 requires to be freshly "
            f"observed/authorized/re-hashed/newly signed: {admitted_by_reference} "
            "(§10.5 #28 second half / §12 #15)"
        )
    if live.get("refresh_carries_no_signature_field") is not True:
        reasons.append(
            "W5 dependency-refresh schema grew a signature/namespace/profile surface; §9.2 "
            "requires an independent recomputation and §9.1 closes the SSHSIG profile set at "
            "four — a fifth profile is a trust-root change no WP4 worker may make (§12 #15)"
        )
    return reasons


def w5_structural_errors(receipt: dict[str, Any], repo_root: Path = REPO_ROOT) -> list[str]:
    """wave=W5 的自足結構再導出(facade ``_wave_exit_structural_errors`` 委派)。

    除 digest 恆等外,把 W5 exit 的謂詞「顯式」折活:秘密掃描的編碼形、observer 身分的
    不可命名性、四個不被安裝的元件、inactive postcheck 的宣稱面、rendered unit 的兩個
    §12 禁止身分,以及 S2.4 schema 的中央註冊完整性。
    """

    reasons: list[str] = []
    if receipt.get("predecessor_wave_receipt_digest") is None:
        reasons.append(
            "W5 wave-exit requires a non-null predecessor_wave_receipt_digest "
            "(the W4 wave-exit self_digest)"
        )
    projection = w5_exported_abi_projection(repo_root)
    if receipt.get("exported_abi_digest") != canonical_digest(projection):
        reasons.append(
            "wave-exit exported_abi_digest does not re-derive the W5 exported-ABI projection"
        )
    # 1) §10.5 #15:編碼形 + 遞迴面。
    secret_live = projection["secret_scan_live"]
    detected = secret_live.get("encoded_forms_detected") or {}
    missing_forms = sorted(name for name, hit in detected.items() if hit is not True)
    if missing_forms or not detected:
        reasons.append(
            "W5 secret scan does not detect every encoded sentinel form "
            f"(undetected: {missing_forms or 'projection unavailable'}); §10.5 #15 requires a "
            "recursive secret AND encoded-secret scan of all artifacts"
        )
    if secret_live.get("dict_key_is_scanned") is not True or (
        secret_live.get("bytes_node_is_scanned") is not True
    ):
        reasons.append(
            "W5 secret scan does not walk dict keys and bytes nodes (a secret rendered into a "
            "key or a bytes blob would reach a serializable surface)"
        )
    if secret_live.get("clean_artifact_passes") is not True or (
        secret_live.get("no_sentinel_is_a_noop") is not True
    ):
        reasons.append(
            "W5 secret scan is not a real predicate (a scanner that raises on everything, or "
            "one that refuses without a live sentinel, proves nothing)"
        )
    # 2) §10.5 #12:observer 身分。
    pg_live = projection["pg_role_identity_live"]
    if pg_live.get("manifest_role_name_const") != _SCANNER_ROLE:
        reasons.append(
            "W5 pg_acl_manifest_v1.role_name is no longer pinned to a const of "
            f"{_SCANNER_ROLE!r}; S2.4 could then be pointed at the S1.1 observer identity "
            "(§10.5 #12)"
        )
    if pg_live.get("shipped_manifest_role_name") != _SCANNER_ROLE:
        reasons.append("W5 shipped pg_acl_manifest_v1 does not name the engine-scanner role")
    if pg_live.get("observer_named_manifest_is_centrally_rejected") is not True:
        reasons.append(
            "W5 central gate accepts an ACL manifest naming aiml_observer_ro; S2.4 must never "
            "be able to create, drop or revoke the observer role (§10.5 #12)"
        )
    if pg_live.get("observer_absent_from_generated_sql") is not True or (
        pg_live.get("every_generated_statement_names_the_scanner_role_or_public") is not True
    ):
        reasons.append(
            "W5 generated grant/revoke sequence names a role other than the engine-scanner "
            "role (PUBLIC revokes are the only §2.1 exception); S2.4 must be unable to act on "
            "any other identity (§10.5 #12)"
        )
    # 3) §10.5 #16:四個不被安裝的元件。
    scope_live = projection["component_scope_live"]
    leaked = sorted(
        name
        for name, absent in (scope_live.get("forbidden_component_identities_absent") or {}).items()
        if absent is not True
    )
    if leaked or not scope_live.get("forbidden_component_identities_absent"):
        reasons.append(
            "W5 WP4 surface names a component S2.4 does not install "
            f"({leaked or 'projection unavailable'}); §2 reserves controller, fit_evaluation, "
            "serving and deleter for their own owning sessions (§10.5 #16)"
        )
    if scope_live.get("row_count") != 5:
        reasons.append("W5 aggregate no longer drives exactly the five §5.1 component rows")
    # 4) §10.5 #29:inactive postcheck 的宣稱面。
    postcheck_live = projection["inactive_postcheck_live"]
    for label in ("postcheck", "receipt"):
        if postcheck_live.get(f"{label}_additional_properties_closed") is not True:
            reasons.append(
                f"W5 s2_4_install_{label} schema is no longer additionalProperties:false; an "
                "unreviewed runtime/lifecycle claim could be smuggled into a terminal artifact"
            )
        if postcheck_live.get(f"{label}_carries_no_lifecycle_claim") is not True:
            reasons.append(
                f"W5 s2_4_install_{label} carries a runtime-directory/decrypted-credential/"
                "running claim; §10.5 #29 forbids S2.4 from making one"
            )
    forbidden_pairs = postcheck_live.get("enable_and_start_are_forbidden") or {}
    if not all(forbidden_pairs.get(name) is True for name in (
        "enable", "enable_unit", "start", "start_unit", "restart", "kill"
    )):
        reasons.append(
            "W5 aggregate driver surface no longer refuses enable/start/restart/kill; "
            "`enable --now` belongs to S2.5A (§10.5 #29 / §12 #7)"
        )
    # 5) §10.5 #11:rendered unit 的兩個禁止身分。
    unit_live = projection["rendered_unit_negative_live"]
    if unit_live.get("clean_unit_status") != "PASS":
        reasons.append("W5 clean rendered unit does not derive PASS")
    if unit_live.get("execstart_is_content_addressed") is not True or (
        unit_live.get("alr_shadow_absent_from_clean_unit") is not True
    ):
        reasons.append(
            "W5 rendered unit is not content-addressed or still carries the retired alr_shadow "
            "identity (§8.3 / §12 #3)"
        )
    for key, label in (
        ("system_interpreter_status", "/usr/bin/python3 system interpreter"),
        ("alr_shadow_identity_status", "retired alr_shadow service identity"),
        ("mutable_checkout_status", "mutable-checkout WorkingDirectory"),
    ):
        if unit_live.get(key) != "ENGINE_SCANNER_UNIT_INVALID":
            reasons.append(
                f"W5 rendered-unit check accepts a {label}; §12 #3 forbids system Python and a "
                "mutable checkout in the production unit (§10.5 #11)"
            )
    # 6) §10.5 #1 / §9.2:schema 註冊完整性與那一份誠實缺席。
    schema_live = projection["schema_registration_live"]
    if schema_live.get("unregistered_schema_keys"):
        reasons.append(
            "W5 finds S2.4 schemas outside the central SCHEMA_FILES delegation table: "
            f"{schema_live['unregistered_schema_keys']}"
        )
    if schema_live.get("unresolvable_schema_keys"):
        reasons.append(
            "W5 finds registered S2.4 schema keys whose files do not resolve: "
            f"{schema_live['unresolvable_schema_keys']}"
        )
    if schema_live.get("undeclared_on_disk_schema_keys"):
        reasons.append(
            "W5 finds S2.4 schema files on disk that are outside the declared inventory "
            f"({schema_live['undeclared_on_disk_schema_keys']}); a schema nobody round-trips "
            "is a schema outside the central gate (§10.5 #1)"
        )
    if schema_live.get("s2_4_schema_count") != len(_S2_4_SCHEMA_KEYS):
        reasons.append("W5 S2.4 schema inventory projection is not the declared set")
    # 誠實邊界:缺席的那一份**必須**同時被 obligation 記著。缺席狀態一旦改變(有人把它
    # 實作了),這裡就會要求 obligation 被關閉,而不是讓一個過期的義務永遠掛著。
    absent = schema_live.get("dependency_refresh_schema_file_exists") is False and (
        schema_live.get("dependency_refresh_schema_registered") is False
    )
    obligation_ids = {
        row["obligation_id"] for row in _W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    if absent and "DEPENDENCY_REFRESH_ATTESTATION_ABSENT" not in obligation_ids:
        reasons.append(
            "W5 does not record DEPENDENCY_REFRESH_ATTESTATION_ABSENT while "
            f"{_DEPENDENCY_REFRESH_SCHEMA} is genuinely missing from §10.1's owned set"
        )
    if not absent and "DEPENDENCY_REFRESH_ATTESTATION_ABSENT" in obligation_ids:
        reasons.append(
            f"W5 still records DEPENDENCY_REFRESH_ATTESTATION_ABSENT although "
            f"{_DEPENDENCY_REFRESH_SCHEMA} now exists; close the obligation instead"
        )
    # 7) §9.2 / §10.5 #28:過期 source 身分的獨立復現閘。
    reasons.extend(_dependency_refresh_reasons(projection["dependency_refresh_live"]))
    if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W5_OWNED_PATHS)):
        reasons.append("wave-exit owned_path_manifest_digest is not the exact W5 owned-path set")
    if receipt.get("owned_path_diff_digest") != w5_owned_path_diff_digest(
        repo_root, source_head=receipt.get("source_head")
    ):
        reasons.append(
            "wave-exit owned_path_diff_digest does not re-derive the W5 owned-path content "
            "projection"
        )
    return reasons


def w5_chain_binding_errors(
    receipt: dict[str, Any],
    source_admission_receipt: dict[str, Any],
    predecessor_wave_receipt: dict[str, Any],
    head: str | None,
) -> list[str]:
    """W5 predecessor/admission/HEAD 綁定檢查(facade 於 W4 鏈已導 PASS 後呼叫)。"""

    reasons: list[str] = []
    if predecessor_wave_receipt.get("wave") != "W4":
        reasons.append("W5 wave-exit predecessor must be the W4 wave-exit receipt")
    if predecessor_wave_receipt.get("self_digest") != receipt.get(
        "predecessor_wave_receipt_digest"
    ):
        reasons.append(
            "W5 predecessor_wave_receipt_digest does not bind the derived W4 wave-exit receipt"
        )
    if source_admission_receipt.get("self_digest") != receipt.get(
        "source_admission_receipt_digest"
    ):
        reasons.append(
            "wave-exit source_admission_receipt_digest does not bind the derived admission receipt"
        )
    if head is None:
        reasons.append(
            "W5 wave-exit source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
        )
    elif receipt.get("source_head") != head:
        reasons.append("W5 wave-exit source_head is not the current checkout HEAD")
    if receipt.get("source_head") != predecessor_wave_receipt.get("source_head"):
        reasons.append("W5 wave-exit source_head differs from the bound W4 wave-exit receipt")
    if receipt.get("source_head") != source_admission_receipt.get("source_head"):
        reasons.append("W5 wave-exit source_head differs from the bound admission receipt")
    return reasons


def build_w5_wave_exit_receipt(
    admission: dict[str, Any],
    predecessor_wave_exit: dict[str, Any],
    *,
    test_digests: list[str],
    capture_digests: list[str],
    review_fragment_digests: list[str],
) -> dict[str, Any]:
    """綁定當前世代 W0/W1/W2/W3/W4 鏈與真實 test/capture/review 證據 digest 的 W5 wave-exit。

    **建構 ≠ 發射**:本函式只回一個記憶體物件、不寫任何檔案。W5 不擁有發射器;持久化屬
    PM 的收口投影(``w5-emit`` 由 PM 依既有 ``_wN_emit`` 葉的形狀另行落地)。receipt 恆
    evidence-only:絕不自帶 status,PASS 恆由中央 validator 導出。
    """

    facade = resolve_facade()
    receipt: dict[str, Any] = {
        "schema_version": "s2_4_wave_exit_receipt_v1",
        "wave": "W5",
        "predecessor_wave_receipt_digest": predecessor_wave_exit["self_digest"],
        "source_admission_receipt_digest": admission["self_digest"],
        "source_head": admission["source_head"],
        "owned_path_manifest_digest": canonical_digest(sorted(_W5_OWNED_PATHS)),
        "owned_path_diff_digest": w5_owned_path_diff_digest(
            source_head=admission["source_head"]
        ),
        "exported_abi_digest": canonical_digest(w5_exported_abi_projection()),
        "test_digests": list(test_digests),
        "capture_digests": list(capture_digests),
        "review_fragment_digests": list(review_fragment_digests),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
    receipt["self_digest"] = facade.artifact_self_digest(receipt)
    return receipt
