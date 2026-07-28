"""S2.4(WP4·W5)wave-exit 綁定的 code-owned 投影葉模組(§10.3 W5 row)。

鏡 :mod:`aiml_gate_receipt_wave_w4`:facade 逐名 re-export,``derive_wave_exit_status``
的 W5 分支委派本葉。W5 是**源碼收口波**——它不新增任何 production gate,只把「§10.5 的
每一條驗收項到底被哪一支測試證明」這件事折成**活**投影,讓覆蓋退化必然弄破 wave-exit:

- ``_W5_OWNED_PATHS``:W5 的投影葉、facade 的 W5 分支、runtime-closure 宣告面、W5 新寫的
  三支測試、被 W5 推進邊界的 W3 wave 測試,以及 §10.3 要求的 W5 發射面(install 的
  ``w5-emit`` 與 ``agent_governance_s2_4_w5_emit``);
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
# W5 review P2-E:本葉不在 import 期把 ``program_code`` 放進 sys.path。它從來沒用過該路徑
# (§9.2 的 package 形匯入發生在 contracts 葉的函式內),而本葉是 facade top-level import、
# 位於 engine-scanner runtime import 閉包內——讓 broker/exchange/dashboard 在 scanner 進程
# 中變成可匯入的 top-level 套件必須是決策而非 import 副作用(§10.1.1 #4)。

from aiml_gate_receipt_schema_core import (  # noqa: E402
    S2_4_W5_REMAINING_OWNED_OBLIGATIONS,
    canonical_digest,
    owned_path_blob_projection_digest,
    owned_scope_worktree_delta,
    program_code_on_path,
    resolve_facade,
)

_SCHEMA_DIR_REL = "program_code/ml_training/schemas/aiml_gate_receipts"
# §10.1 + §10.1.1(2026-07-26 PM path-scope amendment):W5 的 owned-path 投影。
# W5 只擁有「收口」面:投影葉、facade 的 W5 分支、runtime-closure 宣告(facade top-level
# import 使本葉進入 engine-scanner runtime import 閉包)、W5 新寫的兩支測試,以及把
# 「未實作 wave」邊界由 W5 推到 W6 的那支既有 W3 wave 測試,以及 §10.3 要求的 W5 發射面
# (install CLI 的 w5-emit 與其發射葉——W0-W4 每一波都有,W5 在此之前是唯一缺的)。
_W5_OWNED_PATHS = tuple(sorted((
    # §10.3「Every source wave emits s2_4_wave_exit_receipt_v1」的 W5 發射面。install 是
    # §10.1 逐行列名的檔;發射葉鏡 _w3_emit/_w4_emit,由 §10.1.1 standing rule 入 scope。
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
    "helper_scripts/maintenance_scripts/agent_governance_s2_4_w5_emit.py",
    "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
    "program_code/ml_training/aiml_gate_receipt_schema_core.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    # 2000 行治理拆分(第三輪):§10.3 誠實面帳本的純資料葉。它是 W5 擁有的內容,故必須
    # 在 W5 的 owned scope 裡——否則帳本可以在 wave-exit 看不見的地方被改。
    "program_code/ml_training/aiml_gate_receipt_w5_obligations.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w5.py",
    "program_code/ml_training/application_bundle_runtime_closure_v1.json",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    f"{_SCHEMA_DIR_REL}/s2_4_dependency_refresh_attestation_v1.schema.json",
    "tests/structure/test_agent_governance_s2_4_acceptance_matrix.py",
    "tests/structure/test_agent_governance_s2_4_install_w3.py",
    "tests/structure/test_agent_governance_s2_4_install_w5.py",
    # 2000 行治理拆分:發射器測試使 W5 主測試檔越過 2000 行,故拆為 sibling 測試檔
    # (同 W2/W3 的 *_install_{engine_scanner,application_bundle,render}.py 作法)。
    "tests/structure/test_agent_governance_s2_4_install_w5_emit.py",
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
        "wave exit and not only a test. HEADLINE CORRECTION (adversarial round 3): W5 "
        "scored the map 36 PROVEN / 3 PARTIAL / 0 UNPROVEN. E4 independently rebuilt it and "
        "scored 35 / 4 / 0, and W5 adopts E4's number rather than its own. The two "
        "disagreements are #24 and #28a, and in both cases E4 was right for the same "
        "reason: the guard named by the item had NO discriminating test, so removing the "
        "guard left the whole tree green. #24 — agent_governance_s2_4_host_identity's "
        "refusal of a supplied manifest whose canonical digest is not the one in the signed "
        "intent: replacing that condition with `if False:` left 6111 passed / 46 skipped "
        "unchanged, because the test named for it supplied uid=1/gid=1, which the §8 "
        "identity contract rejects FIRST, so the guard was never reached. #28a — the S2.5 "
        "lifecycle-source fold: it had no reason-level consumer and no test-level "
        "assertion, and inverting it to a false claim left every W5-lane test green. This "
        "round adds a discriminating regression for #24 (a manifest that passes the §8 "
        "contract and differs only in uid/gid, so the digest binding is the only "
        "discriminator) and a two-way reason-level consumer for #28a (plus a glob that "
        "matches the one the test uses instead of a single guessed filename). Whether that "
        "restores either item to PROVEN is the next reviewer's call, not W5's: this row "
        "records the corrected score at the reviewed head and what changed, and does not "
        "self-upgrade"
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
        "which must equal BOTH the refresh's claim and the original receipt's own values. Each "
        "class's semantic set is the ATTESTED SUBJECT, not the producer file's own hash: S2.3 "
        "reproduces the sealed runtime content identity, the native-library inventory, the lock "
        "closure, the expected-component identities, the S1.3 negative/rollback bindings and "
        "the committed sealed receipt it chains to; S1.3 reproduces the invariant identity/ACL "
        "projection and the over-grant kind set; S2.2A reproduces the capture/runtime/training "
        "contract digests. Before the second adversarial round S1.3 and S2.3-expected-identity "
        "carried only (schema_sha256, source_sha256), and source_sha256 was byte-identical to "
        "the producer_module_digest the refresh already bound, so 'independent replay' reduced "
        "to 'two files are unchanged' and every one of eight subject drifts on the real shipped "
        "S2.3 expected-identity receipt still reached DEPENDENCY_REFRESH_ADMITTED. The "
        "refresh therefore cannot be minted from the original digest alone, cannot change any "
        "semantic digest, cannot be produced inside the original's own observation window or "
        "by the same producer label, cannot refresh another refresh (closed enum) and cannot "
        "self-declare a status. The observation window itself is bound to the BLOB AT THE "
        "BOUND COMMIT for the three families whose original is a committed repository "
        "artifact: the family validator authenticates shape and not the window, so before "
        "adversarial round 3 editing observation_time/expires_at on the real shipped "
        "receipts and resealing self_digest skipped this entire gate — forward to "
        "SOURCE_DEPENDENCY_FRESH, backward to SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH with "
        "zero reasons. S1.3 has no committed original and its window is therefore still "
        "caller-chosen, which is recorded as its own obligation rather than claimed closed. "
        "Everything §9.2 marks as freshly observed, freshly re-hashed "
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
    # 每一項都帶 typed 狀態與 owner;W4 交出的**每一項**逐條在此重述(owner/理由可更新,
    # 提供等級不可軟化),加上 W5 逐輪自審新發現的各項。數量不在註解裡複述(舊註解寫的
    # 「十五項/九項」在第二、三輪之後都已腐化):唯一的普查在 W5 lane 的
    # test_the_w5_obligation_ledger_has_no_duplicate_or_unowned_row,它逐列比對 W4 的
    # 活 ABI 與 _W5_NEW。任一項被靜默刪除都會弄破本 wave 的
    # exported-ABI digest。清單本體依 2000 行治理拆分住在 schema_core,物件即單一真相來源。
    "remaining_owned_obligations": S2_4_W5_REMAINING_OWNED_OBLIGATIONS,
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
        # W5 對抗審計第三輪 P2-G:舊版只看一個**猜出來的**檔名
        # (``S2.5-start-source-seams.md``),而同一件事的測試用的是 ``S2.5-*.md`` glob;
        # 於是只有 glob 那一半真的閂得住。兩邊統一用 glob,並把命中檔名折進投影。
        design = REPO_ROOT / "docs" / "execution_plan" / "ai_ml_landing" / "design"
        matches = sorted(path.name for path in design.glob("S2.5-*.md"))
        live["s2_5_lifecycle_source_files"] = matches
        live["s2_5_lifecycle_source_absent"] = not matches
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
            "s2_5_lifecycle_source_files",
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


def _producer_input_scope_live(facade: Any) -> dict[str, bool]:
    """每一族的 producer 輸入集合是否真的蓋住該 producer 自己宣告的輸入(逐族布林)。

    以 producer 的**活**常量比對而非固定數字:allowlist 日後合法長大時本鍵仍為 True,
    但只要有人把 §9.2 的重算範圍縮小(於是物化樹與 clean-tree 閘同時看不到那些位元組),
    對應族即翻成 False,W5 wave-exit 必破。
    """

    with program_code_on_path():
        from ml_training import learning_runtime_manifest as _lrm  # noqa: E402 (lazy)

    identity_producer = (
        "helper_scripts/maintenance_scripts/agent_governance_identity_acl_contract.py"
    )
    schema_dir = _SCHEMA_DIR_REL
    required = {
        # P1-C(對抗審計第三輪):``edge_feature_schema_contract.py`` 之所以在 §9.2 的輸入
        # 集合裡,**只**是為了讓 clean-tree 閘蓋到它——它是被 producer ``import`` 的葉,物化
        # 樹幫不上忙(見 dependency_producer_input_paths 的同址註解)。但它先前不在本 required
        # 集合裡,也沒有別的東西釘住它:刪掉那一行,全樹 6111/46 逐位元組不變,而「commit 已
        # 漂移、攻擊者只在工作樹把位元組放回去」那條攻擊就重新打開。
        "S1_3_IDENTITY_CONTRACT": {
            identity_producer,
            f"{schema_dir}/identity_acl_contract_receipt_v1.schema.json",
        },
        "S2_2A_SOURCE_COMPATIBILITY": set(_lrm.CAPTURE_INPUTS)
        | set(_lrm.LEARNING_CODE_INPUTS_V2)
        | set(_lrm.MIGRATION_INPUTS)
        | {
            _lrm.REGIME_OOS_LABEL_CONTRACT,
            _lrm.POLICY_TEMPLATE,
            _lrm.DEPENDENCY_LOCK_SPEC_FILE,
            _lrm.DEPENDENCY_LOCK_LOCK_FILE,
            "program_code/ml_training/edge_feature_schema_contract.py",
        },
        "S2_3_SEALED_BUILD": {
            "requirements-ml.lock",
            "requirements-ml.txt",
            f"{schema_dir}/sealed_build_receipt_v1.schema.json",
        },
        # P1-A(對抗審計第二輪):expected-identity 的語義主體是 S1.3 常量投影 + lock 封閉
        # 導出的 runtime 內容身分 + repo 內那份已提交的 sealed receipt,三者都必須在集合裡,
        # 否則 clean-tree 閘與物化樹同時看不到它們。
        "S2_3_EXPECTED_IDENTITY": {
            identity_producer,
            "docs/execution_plan/ai_ml_landing/receipts/S2.3-sealed-build-receipt-v1.json",
            "requirements-ml.lock",
            "requirements-ml.txt",
            f"{schema_dir}/expected_identity_receipt_v1.schema.json",
        },
    }
    scope: dict[str, bool] = {}
    for name, row in sorted(facade.S2_4_DEPENDENCY_REFRESH_CLASSES.items()):
        paths = set(facade.dependency_producer_input_paths(name))
        # 每一族都必須有一筆**具名**的 required 集合。舊碼用 ``required.get(name, set())``,
        # 於是漏登記的族拿到空集合 = 恆真,那正是 S1.3 先前的狀態。
        expected = required.get(name)
        scope[name] = (
            expected is not None
            and bool(paths)
            and row["producer_module"] in paths
            and expected <= paths
        )
    return scope


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
    "producer_input_scope_covers_the_allowlists",
    "hand_written_original_status",
    "original_without_self_digest_status",
    "never_refreshable_stub_statuses",
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
        # 10) W5 review P1-A:重算的**範圍**必須真的蓋住 producer 自己的凍結 allowlist。
        # 這是 commit 物化 + clean-tree 閘兩者共用的同一個集合;有人把它縮小,兩半同時變弱。
        live["producer_input_scope_covers_the_allowlists"] = _producer_input_scope_live(facade)
        # 11) W5 review P1-C:原 receipt 未經家族驗證器認證就不得被刷新。手寫一份任何 session
        # 都沒產過的 "original"(自帶 running_attested、自選觀測窗),以及把真 receipt 的
        # self_digest 拿掉,兩者都必須拒——否則「reproduced_at 晚於原到期」這條反自我刷新
        # 控制會因為 original_expires_at 落在偽造者手上而失效。
        forged = {
            "schema_version": "expected_identity_receipt_v1",
            "caller": "E9:hand-written",
            "platform": dict(_DEPENDENCY_REFRESH_PROBE_PLATFORM),
            "observation_time": "2020-01-01T00:00:00+00:00",
            "expires_at": "2020-01-01T00:30:00+00:00",
            "running_attested": True,
            **facade.reproduce_dependency_semantic_digests(
                "S2_3_EXPECTED_IDENTITY",
                original_schema_version="expected_identity_receipt_v1",
                repo_root=repo_root,
            ),
        }
        live["hand_written_original_status"] = _status(_build(original_receipt=forged), forged)
        unsigned = {key: value for key, value in original.items() if key != "self_digest"}
        live["original_without_self_digest_status"] = _status(
            _build(original_receipt=unsigned), unsigned
        )
        # 12) W5 review P2-D:``evidence_class`` 只是 caller 遞交的標籤。九個永不可刷新的類別
        # 在**沒有** refresh 時也不得因為一個兩鍵 stub 而導出 SOURCE_DEPENDENCY_FRESH。
        live["never_refreshable_stub_statuses"] = {
            name: facade.derive_source_dependency_admission_status(
                evidence_class=name,
                receipt={"expires_at": "2099-01-01T00:00:00+00:00"},
                now=_DEPENDENCY_REFRESH_PROBE_NOW,
                repo_root=repo_root,
            )["status"]
            for name in sorted(facade.S2_4_NEVER_REFRESHABLE_EVIDENCE)
        }
        # 13) 簽章判斷的可測形:closed schema 不含任何簽章面。
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


# §9.2 的 typed 裁決今天有沒有**生產**呼叫端(B 項:誠實面必須是被測量出來的,不是被宣稱的)。
#
# W5 對抗審計第三輪 P1-E(E2/E3 同結論):舊版的量測是 ``if f"{name}(" in text`` 施於**原始
# 檔案文字**、且只掃一個非遞迴目錄。兩個方向都壞:一則一句**註解**提到這個名字就讓
# ``production_call_sites`` 變非空,而那條閂的另一臂寫著「close the obligation instead」——
# 一個誤報會逼人刪掉一條仍然為真的誠實列;二則 ``program_code/`` 下的生產面完全沒被看過。
# 現在用 AST 只數 ``ast.Call``,掃描面遞迴涵蓋治理腳本與 program_code,且任何無法解析的檔案
# 一律把量測降成 ``None``(= 無法關閉),永遠不會變成「必須關閉」。
_REFRESH_SCAN_ROOTS = ("helper_scripts/maintenance_scripts", "program_code")
# §9.2 的**定義**面與本波的**量測**面本身不是呼叫端(定義 + facade re-export + 本葉)。
# 這是唯一的排除集合,逐條具名並折進投影,縮小它即改變 exported_abi_digest。
_REFRESH_SCAN_DEFINITION_SITES = (
    "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/aiml_gate_receipt_wave_w5.py",
)
_REFRESH_ADMISSION_ENTRY = "derive_source_dependency_admission_status"
# D 項:wave-exit 的三串 evidence digest 只被形狀約束住,任何 64 位十六進位都合法。
_FABRICATED_EVIDENCE_DIGEST = "sha256:" + "1" * 64
# JSON Schema 的**註解**關鍵字(純文件,不約束任何值)與**形狀**關鍵字。前者出現不得改變
# 「只被形狀約束」這個判斷;出現任何**兩者皆非**的關鍵字則是無法判定 → fail-closed。
_JSON_SCHEMA_ANNOTATION_KEYS = frozenset({
    "$comment", "default", "deprecated", "description", "examples", "readOnly",
    "title", "writeOnly",
})
_JSON_SCHEMA_SHAPE_ONLY_KEYS = frozenset({
    "format", "maxLength", "minLength", "pattern", "type",
})


def _module_calls_the_name(path: Path, name: str) -> bool | None:
    """該 ``.py`` 檔裡有沒有**真的**呼叫 ``name``(``ast.Call``);讀不了/解析不了回 ``None``。"""

    import ast

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError, UnicodeDecodeError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == name:
            return True
        if isinstance(func, ast.Attribute) and func.attr == name:
            return True
    return False


def _refresh_call_site_live(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """§9.2 admission 裁決在生產面的呼叫端(空集合 = 這個閘今天只被測試與 W5 投影呼叫)。"""

    live: dict[str, Any] = {}
    try:
        root = Path(repo_root)
        callers: list[str] = []
        scanned = 0
        undecidable: list[str] = []
        for scan_root in _REFRESH_SCAN_ROOTS:
            for path in sorted((root / scan_root).rglob("*.py")):
                rel = path.relative_to(root).as_posix()
                if rel in _REFRESH_SCAN_DEFINITION_SITES:
                    continue
                parts = rel.split("/")
                if "tests" in parts or "__pycache__" in parts:
                    continue
                scanned += 1
                calls = _module_calls_the_name(path, _REFRESH_ADMISSION_ENTRY)
                if calls is None:
                    undecidable.append(rel)
                elif calls:
                    callers.append(rel)
        live["production_call_site_scan_roots"] = list(_REFRESH_SCAN_ROOTS)
        live["production_call_site_definition_sites"] = list(_REFRESH_SCAN_DEFINITION_SITES)
        live["production_call_site_modules_scanned"] = scanned
        live["production_call_site_undecidable_modules"] = sorted(undecidable)
        # 任何一個檔案量測不出來 = 這個誠實宣稱量測不出來(絕不當成「沒有呼叫端」)。
        live["production_call_sites"] = None if undecidable else sorted(callers)
        # 唯一真的在 APPLY 期消費 §9.2 source 身分的地方(讀 repo 固定路徑的 S2.3 artifact),
        # 它只驗 status/self_digest/三個身分欄位,完全不導新鮮度。
        import agent_governance_s2_4_host_identity as _host

        live["apply_time_consumer"] = (
            "agent_governance_s2_4_host_identity.s2_3_expected_identity_reasons"
        )
        live["apply_time_consumer_derives_freshness"] = (
            _REFRESH_ADMISSION_ENTRY in _host.s2_3_expected_identity_reasons.__code__.co_names
        )
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        for key in (
            "production_call_site_scan_roots",
            "production_call_site_definition_sites",
            "production_call_site_modules_scanned",
            "production_call_site_undecidable_modules",
            "production_call_sites",
            "apply_time_consumer",
            "apply_time_consumer_derives_freshness",
        ):
            live.setdefault(key, None)
    return live


def _evidence_authenticity_live() -> dict[str, Any]:
    """§10.5 / CLAUDE 證據保證:wave-exit 的三串 evidence digest 到底被什麼擋住(誠實測量)。"""

    live: dict[str, Any] = {}
    facade = resolve_facade()
    try:
        schema = facade._load_schema("s2_4_wave_exit_receipt_v1")
        defs = schema.get("$defs", {})
        constraints: dict[str, Any] = {}
        for field in ("test_digests", "capture_digests", "review_fragment_digests"):
            spec = dict(schema["properties"][field])
            item = dict(spec.get("items") or {})
            if "$ref" in item:
                item = dict(defs.get(str(item["$ref"]).rsplit("/", 1)[-1], {}))
            constraints[field] = {
                "min_items": spec.get("minItems"),
                "item_constraint_keys": sorted(item),
            }
        live["wave_exit_evidence_constraints"] = constraints
        # 形狀之外沒有任何東西:沒有 producer 身分、沒有執行憑據、沒有 orchestrator 綁定。
        #
        # P1-E:舊版是**鍵集合**比對(``in (["pattern","type"], ["type"])``),於是在
        # ``$defs/digest`` 上加一句 ``description`` 這種純文件編輯就會把它翻成 False,而那條
        # 閂的另一臂寫著「close the obligation instead」——一個純註解會逼人刪掉一條仍為真的
        # 誠實列。現在先剝掉 JSON Schema 的註解關鍵字,再判斷剩下的是否**全是**形狀關鍵字;
        # 出現任何既非註解也非形狀的關鍵字 = 無法判定 → None → fail-closed(不可關閉),
        # 而不是「必須關閉」。
        decidable = True
        for row in constraints.values():
            keys = set(row["item_constraint_keys"]) - _JSON_SCHEMA_ANNOTATION_KEYS
            row["constraining_keys"] = sorted(keys)
            if keys - _JSON_SCHEMA_SHAPE_ONLY_KEYS:
                # 那個關鍵字可能是真的認證性約束,也可能只是本表不認得的形狀關鍵字。兩者都
                # **不得**被當成「已經不只是形狀」而去要求關閉義務——無法判定就是無法關閉。
                decidable = False
        live["only_shape_is_constrained"] = True if decidable else None
        import agent_governance_s2_4_emit_sink as _sink

        try:
            _sink.validate_emit_evidence(
                {"fabricated": _FABRICATED_EVIDENCE_DIGEST},
                [{"fabricated": _FABRICATED_EVIDENCE_DIGEST}],
                secret_scanner=lambda _payload: False,
            )
            live["emit_sink_accepts_fabricated_evidence"] = True
        except ValueError:
            live["emit_sink_accepts_fabricated_evidence"] = False
        # 掃描器不是恆真:空 evidence 與帶秘密的 evidence 都必須被擋(否則上面那個 True
        # 只是「什麼都不檢查」,而不是「只檢查形狀」)。
        for key, args in (
            ("emit_sink_refuses_empty_evidence", ({}, [{"a": 1}], lambda _p: False)),
            ("emit_sink_refuses_secret_like_evidence",
             ({"a": 1}, [{"a": 1}], lambda _p: True)),
        ):
            try:
                _sink.validate_emit_evidence(args[0], args[1], secret_scanner=args[2])
                live[key] = False
            except ValueError:
                live[key] = True
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        for key in (
            "wave_exit_evidence_constraints",
            "only_shape_is_constrained",
            "emit_sink_accepts_fabricated_evidence",
            "emit_sink_refuses_empty_evidence",
            "emit_sink_refuses_secret_like_evidence",
        ):
            live.setdefault(key, None)
    return live


def w5_exported_abi_projection(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """W5 exported-ABI 投影:code-owned 骨架 + 九組覆蓋缺口的活再導出。"""

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
        "refresh_call_site_live": _refresh_call_site_live(repo_root),
        "evidence_authenticity_live": _evidence_authenticity_live(),
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
        (
            "hand_written_original_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "a hand-written 'original' that no session ever produced — carrying "
            "running_attested and its own chosen observation window — must never be "
            "refreshable; artifact_self_digest against the refresh's own claim is "
            "self-referential and authenticates nothing",
        ),
        (
            "original_without_self_digest_status",
            "DEPENDENCY_REFRESH_REJECTED",
            "an original whose own self_digest field is absent or does not bind its bytes "
            "is not the artifact its producer emitted",
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
    narrowed = sorted(
        name
        for name, covered in (
            live.get("producer_input_scope_covers_the_allowlists") or {}
        ).items()
        if covered is not True
    )
    if narrowed or not live.get("producer_input_scope_covers_the_allowlists"):
        reasons.append(
            "W5 §9.2 recomputation scope no longer covers the producer's own declared input "
            f"allowlist for {narrowed or 'any'} class; both halves of the P1-A fix (commit "
            "materialisation and the clean-tree gate) only see the paths in that set, so a "
            "narrowed scope re-opens the drifted-commit / restored-working-tree admission"
        )
    stubs = live.get("never_refreshable_stub_statuses") or {}
    admitted_stubs = sorted(
        name for name, status in stubs.items() if status != "SOURCE_DEPENDENCY_REJECTED"
    )
    if admitted_stubs or sorted(stubs) != sorted(live.get("never_refreshable_classes") or []):
        reasons.append(
            "W5 derives a freshness verdict for evidence it never checked is the artifact "
            f"evidence_class names ({admitted_stubs or 'projection unavailable'}); a "
            "caller-supplied class label plus an expires_at is not the §9.2 evidence"
        )
    if live.get("refresh_carries_no_signature_field") is not True:
        reasons.append(
            "W5 dependency-refresh schema grew a signature/namespace/profile surface; §9.2 "
            "requires an independent recomputation and §9.1 closes the SSHSIG profile set at "
            "four — a fifth profile is a trust-root change no WP4 worker may make (§12 #15)"
        )
    return reasons


# P1-C 的具名前綴:測試據此把「工作樹髒」這一條與其他結構 reason 分開,而不是靠字串比對。
_W5_OWNED_SCOPE_REASON = "W5 wave-exit owned scope is not at the bound source_head"
# B / D 兩條誠實面 obligation 的識別字(在冊與否由下面的活測量決定)。
_REFRESH_CALL_SITE_OBLIGATION = "SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE"
_EVIDENCE_AUTHENTICITY_OBLIGATION = "EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED"


def _honest_surface_reasons(
    call_sites: dict[str, Any], evidence: dict[str, Any]
) -> list[str]:
    """兩條誠實面義務的**雙向**閂:事實還在 → 必須在冊;事實消失 → 必須關閉。

    這是 W5 對抗審計 B/D 兩項的載重形式。B:``derive_source_dependency_admission_status``
    今天零生產呼叫端,所以「§9.2 的裁決只在 APPLY 期經此入口可達」那句話是假的;那句話被改
    成真的之後,還必須有東西盯著它——有人日後把閘接進 APPLY,義務就得關掉,而不是讓一句
    過期的殘留永遠掛著。D:wave-exit 的三串 evidence digest 只被形狀約束,任何 64 位十六進位
    都通過,所以整條 W0→W5 鏈證不了測試跑過或審查發生過(packet-local artifact 無法認證自身
    執行)。兩者都不是本波能在源碼線關掉的東西,但都必須是**被測量**的、而非被宣稱的。
    """

    reasons: list[str] = []
    obligation_ids = {
        row["obligation_id"] for row in _W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    sites = call_sites.get("production_call_sites")
    scanned = call_sites.get("production_call_site_modules_scanned")
    # P1-E:量測失敗**或**量測含糊一律走 fail-closed 臂(= 不可關閉);「必須關閉」那一臂
    # 只有在量測明確為「有呼叫端」時才可達。掃描面本身塌成 0 個模組同樣是量測失敗。
    if (
        sites is None
        or call_sites.get("apply_time_consumer_derives_freshness") is None
        or not isinstance(scanned, int)
        or scanned <= 0
        or call_sites.get("production_call_site_undecidable_modules")
    ):
        reasons.append(
            "W5 cannot measure whether the §9.2 admission verdict has a production call "
            "site; an unmeasurable honesty claim is not an honesty claim (fail-closed)"
        )
    elif not sites and call_sites.get("apply_time_consumer_derives_freshness") is False:
        if _REFRESH_CALL_SITE_OBLIGATION not in obligation_ids:
            reasons.append(
                f"W5 does not record {_REFRESH_CALL_SITE_OBLIGATION} while "
                f"{_REFRESH_ADMISSION_ENTRY} has zero production call sites and the only "
                "APPLY-time consumer of a §9.2 source identity derives no freshness at all "
                "(§9.2's 'the central validator accepts an expired source identity only "
                "together with one current refresh' has no enforcement point today)"
            )
    elif _REFRESH_CALL_SITE_OBLIGATION in obligation_ids:
        reasons.append(
            f"W5 still records {_REFRESH_CALL_SITE_OBLIGATION} although the §9.2 admission "
            f"verdict is now reached from {sites or 'an APPLY-time consumer'}; close the "
            "obligation instead of carrying a statement that has stopped being true"
        )
    if evidence.get("only_shape_is_constrained") is None or (
        evidence.get("emit_sink_accepts_fabricated_evidence") is None
    ):
        reasons.append(
            "W5 cannot measure what constrains the wave-exit evidence digests (fail-closed)"
        )
    elif (
        evidence.get("emit_sink_refuses_empty_evidence") is not True
        or evidence.get("emit_sink_refuses_secret_like_evidence") is not True
        # 第四輪 P2:sink 探針是**空對照組**,不是本條義務的主體。舊碼把它放在關閉臂的
        # 判準裡,於是在 sink 加一句良性形狀檢查(如 require "command")就讓
        # accepts_fabricated 翻 False、掉進下一臂,吐出「evidence digests are no longer
        # shape-only; close the obligation instead」——而同一份投影裡
        # only_shape_is_constrained 仍是 True。那句話是假的,而它的處方是刪掉一條仍為真的
        # 誠實列。三個探針現在一起當對照:全真才代表「這個守衛真的只檢查形狀」;任一翻面
        # 代表對照組本身變了(拒絕一切 / 拒絕不了任何東西),量測不再成立 → fail-closed。
        or evidence.get("emit_sink_accepts_fabricated_evidence") is not True
    ):
        reasons.append(
            "W5 emit-evidence guard is not a real predicate (a guard that refuses nothing, "
            "or one that refuses everything, measures nothing about the evidence)"
        )
    elif evidence.get("only_shape_is_constrained") is True:
        if _EVIDENCE_AUTHENTICITY_OBLIGATION not in obligation_ids:
            reasons.append(
                f"W5 does not record {_EVIDENCE_AUTHENTICITY_OBLIGATION} while a fabricated "
                "digest still satisfies every evidence constraint the wave-exit chain has; "
                "declaring S2.4@SOURCE_READY *from* this chain would be asserting more than "
                "the chain can carry"
            )
    # 只有「主體本身」被量成 False(schema 真的長出非形狀性約束)才可以要求關閉這一列;
    # 上面第一個 if 已把 None 收走,故本臂等價於 only_shape_is_constrained is False。
    elif _EVIDENCE_AUTHENTICITY_OBLIGATION in obligation_ids:
        reasons.append(
            f"W5 still records {_EVIDENCE_AUTHENTICITY_OBLIGATION} although the evidence "
            "digests are no longer shape-only; close the obligation instead"
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
    obligation_ids = {
        row["obligation_id"] for row in _W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
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
    # P2-G(第三輪):``grant_statement_count`` 先前零消費者。一個生成不出任何 GRANT 的
    # 序列會讓上面兩條「observer 不出現」「每一句都指向 scanner」全部真空成立。
    if not isinstance(pg_live.get("grant_statement_count"), int) or (
        pg_live["grant_statement_count"] <= 0
    ):
        reasons.append(
            "W5 pg_acl_manifest grant sequence generates no statement at all; the "
            "'observer is never named' and 'every statement names the scanner role' "
            "predicates would then hold vacuously (§10.5 #12)"
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
    # P2-G(第三輪):以下三個折進投影的值先前**沒有任何 reason 級消費者**——把它們反轉成
    # 假宣稱,146 支 W5 lane 測試全數仍綠。一個沒有消費者的 fold 只是裝飾品。
    if not postcheck_live.get("aggregate_forbidden_methods"):
        reasons.append(
            "W5 aggregate forbidden-method inventory is empty or unreadable; "
            "'the driver surface refuses enable/start/restart/kill' would then be vacuous"
        )
    for label in ("postcheck", "receipt"):
        if not postcheck_live.get(f"{label}_properties"):
            reasons.append(
                f"W5 s2_4_install_{label} schema exposes no properties at all; a closed "
                "schema with an empty property set carries no lifecycle claim only because "
                "it carries nothing (§10.5 #29 would be satisfied vacuously)"
            )
    # §10.5 #29 第二句(S2.5 fixtures)的雙向 latch——PM O-1 裁決(2026-07-28)後判準改讀
    # typed_status 而非 row 存在與否:row 永遠 carried(W5 帳本鐵則:殘留歷史 load-bearing
    # 的義務不得整列刪掉),「關閉」由 typed_status=CLOSED_BY_S2_5_SOURCE 表達。S2.5 source
    # 缺席時該 row 必須仍記 OUT_OF_WP4_SCOPE;S2.5 source 一旦出現(design 檔 glob 命中),
    # 該 row 必須改標 CLOSED 而不是留著一句已停止為真的話。
    s2_5_absent = postcheck_live.get("s2_5_lifecycle_source_absent")
    s2_5_row = next(
        (
            row
            for row in _W5_EXPORTED_ABI["remaining_owned_obligations"]
            if row["obligation_id"] == "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST"
        ),
        None,
    )
    s2_5_status = None if s2_5_row is None else s2_5_row.get("typed_status")
    if s2_5_absent is None:
        reasons.append(
            "W5 cannot measure whether an S2.5 lifecycle source exists in this repository "
            "(fail-closed); §10.5 #29's second clause then has an unknown owner"
        )
    elif s2_5_row is None:
        reasons.append(
            "W5 dropped the S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST row entirely; a row whose "
            "residual history is load-bearing is carried with a typed closure status, "
            "never removed (PM O-1)"
        )
    elif s2_5_absent and s2_5_status != "OUT_OF_WP4_SCOPE":
        reasons.append(
            "W5 does not record S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST as OUT_OF_WP4_SCOPE "
            "while no S2.5 source exists in this repository; §10.5 #29's second clause has "
            "no owner in WP4 and must be recorded rather than counted as covered"
        )
    elif not s2_5_absent and s2_5_status == "OUT_OF_WP4_SCOPE":
        reasons.append(
            "W5 still records S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST as OUT_OF_WP4_SCOPE "
            f"although {postcheck_live.get('s2_5_lifecycle_source_files')} now exists; "
            "close the obligation (typed_status=CLOSED_BY_S2_5_SOURCE) instead of carrying "
            "a statement that has stopped being true"
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
    # P2-G(第三輪):``dependency_refresh_schema_key`` 先前零消費者——把它換成任意字串,
    # 上面「缺席/存在」的兩向閂就指向一個不存在的 schema 而全樹仍綠。
    if schema_live.get("dependency_refresh_schema_key") != _DEPENDENCY_REFRESH_SCHEMA or (
        _DEPENDENCY_REFRESH_SCHEMA not in _S2_4_SCHEMA_KEYS
    ):
        reasons.append(
            "W5 dependency-refresh schema key is not the §10.1-named "
            f"{_DEPENDENCY_REFRESH_SCHEMA} inside the declared S2.4 inventory; the "
            "absent/present latch below would then be pointed at a schema nobody owns"
        )
    # 誠實邊界:缺席的那一份**必須**同時被 obligation 記著。缺席狀態一旦改變(有人把它
    # 實作了),這裡就會要求 obligation 被關閉,而不是讓一個過期的義務永遠掛著。
    absent = schema_live.get("dependency_refresh_schema_file_exists") is False and (
        schema_live.get("dependency_refresh_schema_registered") is False
    )
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
    # 8) 誠實面必須是**被測量**出來的:§9.2 裁決的生產呼叫端與 evidence 的可認證性,兩者
    #    今天各自的真實狀態決定對應 obligation 是否必須在冊(而不是可以被靜默刪掉)。
    reasons.extend(_honest_surface_reasons(
        projection["refresh_call_site_live"], projection["evidence_authenticity_live"]
    ))
    # 9) W5 對抗審計 P1-C(第三輪 P1-D 抬進共用路徑):owned scope 與 bound commit 的內容
    #    差異必須弄破 wave exit。本葉只保留投影可見性(``owned_scope_worktree_delta`` 仍折在
    #    exported ABI 裡);裁決本身住在 validator 的 ``_owned_scope_delta_reasons``,W0..W5
    #    逐波共用同一把尺——原本只有 W5 消費它,而 W2 擁有 operator 真正執行的四支腳本。
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

    **建構 ≠ 發射**:本函式只回一個記憶體物件、不寫任何檔案。持久化面住在發射葉
    ``agent_governance_s2_4_w5_emit``(install CLI ``w5-emit``,鏡 ``_w3_emit``/``_w4_emit``),
    它呼叫本函式而不另建副本;實際發射正式 ``receipts/S2.4-WP4-W5/`` 是 PM 的收口動作。
    receipt 恆 evidence-only:絕不自帶 status,PASS 恆由中央 validator 導出。
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
