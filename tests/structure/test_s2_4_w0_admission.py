"""W0 (WP4) source-implementation admission alignment — always-run offline tests.

These need NO PostgreSQL / no runtime. They prove the central-validator DERIVES
``ADMITTED``/``PASS`` from repository re-derivation and never from a caller-supplied
status:

- derived-``ADMITTED`` happy path with a REAL receipt (actual current source_head,
  the exact §1.2 predecessor merges, freshly recomputed projection/trust-pin/driver
  digests);
- reject a self-declared ``status``/``pass``/``done`` (§10.5 #27);
- reject the old ``S2.1@EFFECT_DONE``-before-``S2.4`` effect chain if a projection
  reintroduces it (§10.5 #20);
- reject a WP3 ``systemctl --user`` production path from the WP3 executable
  constants (§10.5 #20);
- tamper each predecessor head / trust pin / projection digest / driver-reachability
  flag → derivation returns non-``ADMITTED`` (§10.5 #27);
- frozen S0.3 classifier + v1 component-classifier bytes unchanged after adding the
  two W0 schemas (§10.5 #2);
- PR #132 projection + PR #134 WP3 system-level property present.

The admission receipt is SOURCE evidence: nine authorities false,
production_apply_performed false, running_attested false. The derivation
authenticates the INTEGRITY of the source seams, never a runtime.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_alr_quiesce_inventory as inventory  # noqa: E402
import agent_governance_pg_observer_bootstrap as observer  # noqa: E402


def _current_head() -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _build_admission_receipt(source_head: str) -> dict:
    """A REAL, derivation-passing admission receipt built from live repo bytes."""

    module_bytes = (ROOT / validator._TRUSTED_HOST_MODULE_PATH).read_bytes()
    test_bytes = (ROOT / validator._TRUSTED_HOST_TEST_PATH).read_bytes()
    receipt = {
        "schema_version": "s2_4_source_admission_receipt_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "work_package": "WP4",
        "wave": "W0",
        "source_head": source_head,
        "predecessor_heads": dict(validator._PREDECESSOR_HEADS),
        "three_head_projection_digest": validator.three_head_projection_digest(),
        "trust_pin_digests": {
            "trusted_host_module_blob": validator.git_blob_sha1(module_bytes),
            "trusted_host_module_sha256": "sha256:" + hashlib.sha256(module_bytes).hexdigest(),
            "independent_test_blob": validator.git_blob_sha1(test_bytes),
            "independent_test_sha256": "sha256:" + hashlib.sha256(test_bytes).hexdigest(),
            "operator_fingerprint": validator._OPERATOR_FINGERPRINT,
        },
        "s2_0_driver_reachability_proof": {
            "adapter_id": "pg_observer_bootstrap_adapter_v1",
            "registry_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
            "unconditional_production_pending_removed": True,
            "driver_protocol_present": True,
            "production_success_status": "APPLIED",
        },
        "wp3_system_unit_alignment_proof": {
            "lifecycle_owner": "host_system_manager",
            "systemctl_user_absent": True,
            "role": "aiml_engine_scanner",
            "database": "trading_ai",
        },
        "frozen_classifier_digest": validator.aiml_effect_classifier_digest(),
        "component_classifier_v1_digest": validator.aiml_component_effect_class_matrix_digest(),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        # 由 code-owned W0 負向測試清單「重算」而得(不硬編陳舊字面量);admission 因此
        # 真正綁定本檔負向測試身分,而非帶任意 digest 佯裝負向測試已驗。
        "negative_tests_pass": validator.w0_negative_test_manifest_digest(),
    }
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


def _build_wave_exit_receipt(admission: dict) -> dict:
    receipt = {
        "schema_version": "s2_4_wave_exit_receipt_v1",
        "wave": "W0",
        "predecessor_wave_receipt_digest": None,
        "source_admission_receipt_digest": admission["self_digest"],
        "source_head": admission["source_head"],
        "owned_path_manifest_digest": validator.canonical_digest(
            sorted(validator._W0_OWNED_PATHS)
        ),
        # T1(a):owned_path_diff_digest 由 W0 owned-path 內容投影再導出(非任意佔位字面量)。
        "owned_path_diff_digest": validator.w0_owned_path_diff_digest(),
        "exported_abi_digest": validator.canonical_digest(validator._W0_EXPORTED_ABI),
        # T1(b):test/capture/review 三類皆為「非空」合法 digest list(空/任意值不得導 PASS)。
        "test_digests": [validator.canonical_digest(["test_s2_4_w0_admission"])],
        "capture_digests": [validator.canonical_digest(["w0b-capture"])],
        "review_fragment_digests": [validator.canonical_digest(["e2-review-fragment"])],
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    return receipt


# ── happy path ───────────────────────────────────────────────────────────────


@pytest.fixture()
def clean_owned_scope(monkeypatch):
    """把「owned scope 相對 bound commit 乾淨」當作**前提**,而不是當作被證的事。

    W5 對抗審計第三輪 P1-D 之後每一波的 wave-exit 都消費自己的 owned-scope 內容差異
    (``validator._owned_scope_delta_reasons``),所以在一棵**未提交**的開發樹上那條具名
    reason 是預期存在的。本檔這些斷言證的是鏈綁定 / 結構 / 發射路徑,不是這棵樹乾不乾淨;
    「髒 owned scope 必須弄破該波 wave exit」的正反兩向由
    ``test_agent_governance_s2_4_install_w5.py::
    test_every_wave_exit_consumes_its_own_owned_scope_delta`` 逐波釘住。
    """

    monkeypatch.setattr(validator, "_owned_scope_delta_reasons", lambda *_a, **_k: [])


def test_source_admission_derives_admitted_on_real_receipt() -> None:
    receipt = _build_admission_receipt(_current_head())
    result = validator.derive_source_admission_status(receipt)
    assert result == {"status": "ADMITTED", "reasons": []}
    # central gate returns [] (schema + full derivation)
    assert validator.validate_aiml_artifact(receipt) == []


def test_wave_exit_derives_pass_when_bound_admission_is_admitted(clean_owned_scope) -> None:
    admission = _build_admission_receipt(_current_head())
    wave_exit = _build_wave_exit_receipt(admission)
    result = validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    )
    assert result == {"status": "PASS", "reasons": []}
    # central gate (no bound admission) still validates the self-contained structure
    assert validator.validate_aiml_artifact(wave_exit) == []


def test_central_gate_wave_exit_is_structural_only_not_w0_pass(clean_owned_scope) -> None:
    # 邊界回歸釘:中央閘的 wave-exit 分支只做 STRUCTURAL-ONLY 再導出,乾淨的 [] 「不」等於 W0 PASS。
    admission = _build_admission_receipt(_current_head())
    wave_exit = _build_wave_exit_receipt(admission)
    # 竄改綁定的 admission digest 為假值,但 wave-exit 本身結構仍自足合法。
    wave_exit["source_admission_receipt_digest"] = "sha256:" + "0" * 64
    wave_exit["self_digest"] = validator.artifact_self_digest(wave_exit)
    # (a) 中央閘只驗結構 → 回 [](記錄此危害:bogus admission digest 仍過中央閘)。
    assert validator.validate_aiml_artifact(wave_exit) == []
    # (b) 真 PASS 需綁定「已導 ADMITTED 的 admission」再導出;bogus digest 與 admission.self_digest
    #     不符 → NON-PASS。此釘住「中央閘單獨結果不得讀為 PASS」。
    result = validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    )
    assert result["status"] == "NOT_PASS"
    assert any(
        "source_admission_receipt_digest does not bind" in r for r in result["reasons"]
    )


# ── §10.5 #27: caller cannot self-declare a status ───────────────────────────


@pytest.mark.parametrize("field, value", [
    ("status", "ADMITTED"),
    ("pass", True),
    ("done", True),
    ("admitted", True),
])
def test_reject_self_declared_admission_status(field: str, value) -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt[field] = value
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("must not self-declare status" in reason for reason in result["reasons"])
    # the closed schema also rejects it at the central gate
    assert validator.validate_aiml_artifact(receipt) != []


@pytest.mark.parametrize("field, value", [
    ("status", "PASS"),
    ("pass", True),
    ("done", True),
])
def test_reject_self_declared_wave_exit_status(field: str, value) -> None:
    admission = _build_admission_receipt(_current_head())
    wave_exit = _build_wave_exit_receipt(admission)
    wave_exit[field] = value
    wave_exit["self_digest"] = validator.artifact_self_digest(wave_exit)
    result = validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    )
    assert result["status"] == "NOT_PASS"
    assert any("must not self-declare status" in reason for reason in result["reasons"])
    assert validator.validate_aiml_artifact(wave_exit) != []


# ── §10.5 #20: reject the old effect chain / a --user WP3 path ────────────────


def test_reject_old_effect_chain_if_reintroduced_into_a_projection() -> None:
    # a projection that reverted the canonical apply-order back to the old
    # S2.1@EFFECT_DONE-before-S2.4 chain (new chain absent) is rejected.
    old_chain_only = "operator apply order: S2.0→S2.1→S2.4→S2.5→S2.2B (old cycle)"
    errors = validator._projection_effect_dag_errors({"TODO.md": old_chain_only})
    assert errors and all("missing the canonical" in e for e in errors)
    # the real repo projections DO carry the new canonical chain.
    real_texts = validator._read_three_head_texts(ROOT)
    assert validator._projection_effect_dag_errors(real_texts) == []


def test_reject_wp3_systemctl_user_production_path_from_executable_constants() -> None:
    # the WP3 executable allowlist executably rejects any `--user` (user-systemd) form;
    # only the system-level manager path is admitted (PR #134 system-level property).
    with pytest.raises(Exception):
        inventory._assert_allowlisted_systemctl(
            [inventory.SYSTEMD, "--user", "show", inventory.UNIT_NAME]
        )
    inventory._assert_allowlisted_systemctl(
        [inventory.SYSTEMD, "show", inventory.UNIT_NAME]
    )
    assert inventory.SYSTEMD == "/usr/bin/systemctl"
    # a receipt claiming a user-systemd WP3 path fails the derived property re-check.
    receipt = _build_admission_receipt(_current_head())
    receipt["wp3_system_unit_alignment_proof"]["systemctl_user_absent"] = False
    receipt["wp3_system_unit_alignment_proof"]["lifecycle_owner"] = "user_systemd"
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("wp3_system_unit_alignment_proof" in r for r in result["reasons"])


# ── §10.5 #27: tamper each re-derived input → non-ADMITTED ────────────────────


def test_tamper_predecessor_head_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["predecessor_heads"]["wp3_system_unit_merge"] = "0" * 40
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("predecessor" in r for r in result["reasons"])


def test_tamper_trust_pin_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["trust_pin_digests"]["trusted_host_module_sha256"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("trust pin" in r for r in result["reasons"])


def test_tamper_operator_fingerprint_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["trust_pin_digests"]["operator_fingerprint"] = "SHA256:" + "A" * 43
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("operator_fingerprint" in r or "trust pin" in r for r in result["reasons"])


def test_tamper_projection_digest_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["three_head_projection_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("three_head_projection_digest" in r for r in result["reasons"])


def test_tamper_driver_reachability_flag_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["s2_0_driver_reachability_proof"]["unconditional_production_pending_removed"] = False
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("s2_0_driver_reachability_proof" in r for r in result["reasons"])


def test_tamper_frozen_classifier_digest_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["frozen_classifier_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("frozen_classifier_digest" in r for r in result["reasons"])


def test_tamper_production_flag_true_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["production_authority_flags"]["production_apply_performed"] = True
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("production_authority_flags" in r for r in result["reasons"])


def test_tamper_component_classifier_v1_digest_breaks_admission() -> None:
    receipt = _build_admission_receipt(_current_head())
    receipt["component_classifier_v1_digest"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("component_classifier_v1_digest" in r for r in result["reasons"])


def test_tamper_negative_tests_pass_breaks_admission() -> None:
    # negative_tests_pass 是形狀合法卻不符 code-owned 清單的 digest → 綁定(非形狀)檢查必拒。
    receipt = _build_admission_receipt(_current_head())
    receipt["negative_tests_pass"] = validator.canonical_digest(["wrong-manifest"])
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any(
        "negative_tests_pass does not re-derive to the W0 negative-test manifest" in r
        for r in result["reasons"]
    )


def test_tamper_non_ancestor_source_head_breaks_admission() -> None:
    # 有效 40-hex 但「非」PR#132/#134 predecessor 後代的 commit:predecessor_heads 仍與
    # _PREDECESSOR_HEADS 相等(不觸 dict-equality guard),故控制流真正進入祖裔 LOOP,
    # 每個 predecessor 的 _git_is_ancestor 皆回 False → 兩條 "is not an ancestor" reason。
    receipt = _build_admission_receipt("0" * 39 + "1")
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert receipt["predecessor_heads"] == dict(validator._PREDECESSOR_HEADS)
    assert [
        r for r in result["reasons"] if "is not an ancestor" in r
    ] == [
        f"admission predecessor {name} is not an ancestor of source_head"
        for name in validator._PREDECESSOR_HEADS
    ]


# ── manifest binding is honest: it enumerates the real committed negatives ────


def test_w0_negative_test_manifest_matches_the_committed_negatives() -> None:
    # 清單必須「恰好」等於本檔實際定義的 reject_/tamper_ 負向測試(雙向防漂移):少列 →
    # admission 對未驗測試背書;多列 → digest 綁到不存在的測試。
    committed = tuple(sorted(
        name for name in globals()
        if name.startswith(("test_reject_", "test_tamper_"))
    ))
    assert validator._W0_NEGATIVE_TEST_MANIFEST == committed


# ── §10.5 #2: frozen S0.3 + v1 component bytes unchanged after the schemas ────


def test_frozen_classifier_and_component_v1_unchanged_after_registering_w0_schemas() -> None:
    assert validator.aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert validator.aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    # the two W0 schemas are registered in SCHEMA_FILES only (schema lookup), never in
    # PROGRAM_SCHEMA_PATHS (the fixed 7-name S0.3 tuple) — proving the classifier inputs
    # are untouched.
    for key in ("s2_4_source_admission_receipt_v1", "s2_4_wave_exit_receipt_v1"):
        assert key in validator.SCHEMA_FILES
        assert (validator.SCHEMA_DIR / validator.SCHEMA_FILES[key]).is_file()
    assert len(validator.PROGRAM_SCHEMA_PATHS) == 7
    for key in ("s2_4_source_admission_receipt_v1", "s2_4_wave_exit_receipt_v1"):
        assert not any(key in path for path in validator.PROGRAM_SCHEMA_PATHS)


# ── PR #132 projection + PR #134 WP3 system-level property present ─────────────


def test_pr132_projection_and_pr134_wp3_property_present() -> None:
    # PR #132 effect-DAG projection + PR #134 WP3 unit merge are the exact §1.2 lineage.
    assert validator._PREDECESSOR_HEADS == {
        "program_dag_projection_merge": "4915be30c4214f8a3d591b7f9259169cdb65c75b",
        "wp3_system_unit_merge": "e514f1e761ab9c1965a133f1f113e2e7ccd854df",
    }
    # both are ancestors of the current source_head.
    head = _current_head()
    for merge in validator._PREDECESSOR_HEADS.values():
        assert validator._git_is_ancestor(ROOT, merge, head)
    # PR #132 projection: the corrected effect DAG is present in all three docs.
    assert validator._projection_effect_dag_errors(
        validator._read_three_head_texts(ROOT)
    ) == []
    # PR #134 WP3 system-level property re-derives (role + no --user), property-only
    # (NOT bound to the exact unit name — §7 #4 defers that to W2).
    assert validator._wp3_system_unit_property_errors({
        "lifecycle_owner": "host_system_manager",
        "systemctl_user_absent": True,
        "role": "aiml_engine_scanner",
        "database": "trading_ai",
    }) == []


# ── Codex remediation counterfactuals: each fix rejects the exact bad case ─────


def test_t1_empty_or_arbitrary_wave_exit_evidence_does_not_derive_pass() -> None:
    # T1:空 test/capture/review 證據 list 或任意 owned_path_diff_digest 一律不得導 PASS。
    admission = _build_admission_receipt(_current_head())
    empty = _build_wave_exit_receipt(admission)
    empty["capture_digests"] = []
    empty["review_fragment_digests"] = []
    empty["self_digest"] = validator.artifact_self_digest(empty)
    r_empty = validator.derive_wave_exit_status(empty, source_admission_receipt=admission)
    assert r_empty["status"] == "NOT_PASS"
    assert any("capture_digests" in r for r in r_empty["reasons"])
    # 任意(形狀合法)owned_path_diff_digest:繞不過內容投影再導出。
    arbitrary = _build_wave_exit_receipt(admission)
    arbitrary["owned_path_diff_digest"] = validator.canonical_digest(["arbitrary-diff"])
    arbitrary["self_digest"] = validator.artifact_self_digest(arbitrary)
    r_arb = validator.derive_wave_exit_status(arbitrary, source_admission_receipt=admission)
    assert r_arb["status"] == "NOT_PASS"
    assert any("owned_path_diff_digest" in r for r in r_arb["reasons"])


def test_t2_source_head_not_current_checkout_head_breaks_admission() -> None:
    # T2:有效 40-hex 且為兩 predecessor 的後代(HEAD~1),但 != 目前 checkout HEAD → drift → NOT_ADMITTED。
    parent = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD~1"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    receipt = _build_admission_receipt(parent)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any(
        "source_head is not the current checkout HEAD" in r for r in result["reasons"]
    )
    # 乾淨性:parent 為兩 predecessor 後代,故不應出現任何 "is not an ancestor" reason。
    assert not [r for r in result["reasons"] if "is not an ancestor" in r]


def test_t3_schema_extra_property_admission_is_not_admitted_and_blocks_pass() -> None:
    # T3:額外 forbidden 欄位(self_digest 會把它一併雜湊,故 self_digest 檢查抓不到)——
    # closed-schema additionalProperties:false 於再導出「之前」擋下;經 wave-exit 直呼路徑亦擋。
    receipt = _build_admission_receipt(_current_head())
    receipt["evil_extra"] = "sha256:" + "0" * 64
    receipt["self_digest"] = validator.artifact_self_digest(receipt)
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("unexpected property evil_extra" in r for r in result["reasons"])
    # wave-exit → derive_source_admission_status(bound) 亦回 NOT_PASS(繞過中央閘的直呼路徑)。
    wave_exit = _build_wave_exit_receipt(receipt)
    wr = validator.derive_wave_exit_status(wave_exit, source_admission_receipt=receipt)
    assert wr["status"] == "NOT_PASS"


def test_t4_signature_only_but_unreachable_driver_breaks_admission(monkeypatch) -> None:
    # T4:模擬回歸——保留 driver 參數(signature 仍含)卻重引入「無條件 pending」(未跑 reachable §6 閘)。
    # 舊 inspect.signature 檢查會誤放行;新行為探針因 reason 不含 AUTHORIZATION_REJECTED → 導出 False。
    def _fake_apply(intent, operator_authorization=None, signature=None, *,
                    now, source_head, driver=None, **kwargs):
        return {
            "status": "EXTERNAL_VERIFICATION_PENDING",
            "boundary": {"production_apply_performed": False, "nine_authorities_false": True},
            "failure_reason": "production observer apply deferred to the S2.0 EFFECT session",
        }

    monkeypatch.setattr(observer, "apply_observer_bootstrap", _fake_apply)
    receipt = _build_admission_receipt(_current_head())
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any(
        "s2_0_driver_reachability_proof.unconditional_production_pending_removed" in r
        for r in result["reasons"]
    )


def test_t5_non_allowlist_exception_is_not_treated_as_user_form_rejection(monkeypatch) -> None:
    # T5:allowlist 探針拋「非 QuiesceHostReadError」的例外(回歸引入的 TypeError)不得被誤讀為
    # 「--user 被拒」的證據——舊 broad except 會偽證 systemctl_user_absent=True 而放行。
    def _boom(argv):
        raise TypeError("regression: allowlist signature changed")

    monkeypatch.setattr(inventory, "_assert_allowlisted_systemctl", _boom)
    receipt = _build_admission_receipt(_current_head())
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("unexpected (non-allowlist) error" in r for r in result["reasons"])


def test_t6_non_dict_bound_admission_returns_typed_not_pass() -> None:
    # T6:綁定的 source_admission_receipt 非 dict(list/str/int)→ typed NOT_PASS,絕無 AttributeError。
    admission = _build_admission_receipt(_current_head())
    wave_exit = _build_wave_exit_receipt(admission)
    for bad in (["not", "a", "dict"], "string-admission", 12345, None):
        result = validator.derive_wave_exit_status(
            wave_exit, source_admission_receipt=bad
        )
        assert result["status"] == "NOT_PASS", bad
    # 明確一例的 reason(非 dict 於 derive_source_admission_status 回「must be an object」)。
    r = validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=["not", "a", "dict"]
    )
    assert any("must be an object" in reason for reason in r["reasons"])


def test_t7_database_rederived_from_consumer_and_dsn_drift_breaks_admission(monkeypatch) -> None:
    # T7:database 由消費端權威 DSN 常量再讀取(非硬編鏡像);消費端 dbname 漂移 → admission 失敗。
    assert validator._consumer_authoritative_database() == "trading_ai"
    monkeypatch.setattr(
        validator,
        "_consumer_authoritative_database",
        lambda repo_root=validator.REPO_ROOT: "some_other_db",
    )
    receipt = _build_admission_receipt(_current_head())
    result = validator.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any(
        "wp3_system_unit_alignment_proof.database" in r for r in result["reasons"]
    )
