"""S2.4(WP4·W5)§10.5 驗收項覆蓋缺口的 focused / security 回歸(§10.3 W5 row)。

W5 的工作是「把 §10.5 每一條驗收項對到一支**source 錯了就會紅**的測試」。逐條核對之後,
下面六條的既有覆蓋是空的或半空的——每一條在此補上,而且每一條都經過在丟棄式 clone 內
變異 source 證明會轉紅:

* **#15(秘密/編碼秘密的遞迴掃描)**:``assert_no_secret_material`` 支援 base64 /
  base16(大小寫)/ urlsafe-base64 / hex 四種編碼形,但**沒有任何測試碰過它們**——把那四行
  刪掉,全樹 5965 支測試依然全綠,而一個 base64 化的 DSN 就能抵達可序列化 verdict。
* **#12(observer 身分)**:既有唯一斷言是
  ``not any("aiml_observer_ro" in s for s in driver.revoked_statements)``,它會通過是因為
  fixture 的 manifest 本來就沒提過 observer,而不是因為 source 擋住了它——把 schema 的
  ``role_name`` const 換成 ``{"type": "string"}``,那句斷言仍然綠。
* **#16(WP4 不安裝 controller/fit_evaluation/serving/deleter)**:此前零測試。
* **#29(inactive postcheck 不作 runtime-directory / 已解密憑證宣稱)**:此前只有封閉
  schema 的隱含保證,沒有任何測試指名這件事。
* **#11(``/usr/bin/python3`` 與 ``alr_shadow``)**:§12 #3 明文禁止 system Python 與可變
  checkout 進生產 unit,但兩個替換都沒有顯式負向。
* **#1(schema round-trip 完整性)**:CP2a/CP2b 對 30 份 schema 逐份 round-trip,但沒有任何
  測試要求「S2.4 的**每一份** schema 都在中央 ``SCHEMA_FILES`` 上」——新增一份沒人 round-trip
  的 schema 不會弄紅任何東西。

* **#28 前半(一份獨立重算的 refresh attestation)**:W5 前半段記錄它「無 source 可測」
  (§10.1 明列的 schema 檔不存在);W5 後半段把 §9.2 的閘實作出來,於是本檔補上正向與**每一種**
  §9.2 明文禁止的失敗模式——只複述舊 digest / 同一個 producer 節點 / refresh 去 refresh
  refresh / 自證 status / 被替換或已漂移的原身分 / 過時 head / 兩份 refresh —— 並把
  §10.5 #28 後半(runtime·topology·prepare·auth 永不可引用刷新)**經同一支閘**再證一次
  (既有的 TTL lane 測試不重複)。

仍以**誠實記錄**留著的是 §10.5 #26 的 ``PR_SET_DUMPABLE=0``:一個沒有任何 enforcement 的
宣告常數,以 W5 obligation 的形狀釘在這裡,任何人默默拿掉義務或默默「實作了但沒關閉義務」
都會轉紅。

本檔零 runtime 接觸:所有斷言都在記憶體內對 source 投影求值。
"""
from __future__ import annotations

import base64
import json
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

import agent_governance_s2_4_apply as apply_mod  # noqa: E402
import agent_governance_s2_4_credential as credential  # noqa: E402
import agent_governance_s2_4_install_driver as runner  # noqa: E402
import agent_governance_s2_4_render as render  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402
import agent_governance_s2_4_topology as _topology  # noqa: E402
import s2_4_w3b_testkit as kit  # noqa: E402
from aiml_gate_receipt_classifiers import (  # noqa: E402
    AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2,
)

from test_agent_governance_s2_4_apply import (  # noqa: E402
    _FakePgDriver, _pg_intent, _pg_kwargs,
)

_SENTINEL = "aiml-w5-sentinel-not-a-real-credential"
_UNIT_FIELDS = dict(kit.UNIT_FIELDS)


@pytest.fixture()
def signed(tmp_path, monkeypatch):
    return kit.signed_authorizations(tmp_path, monkeypatch)


def _encoded_forms(secret: str) -> dict[str, str]:
    raw = secret.encode("utf-8")
    return {
        "raw": secret,
        "base64": base64.b64encode(raw).decode("ascii"),
        "base16_upper": base64.b16encode(raw).decode("ascii"),
        "base16_lower": base64.b16encode(raw).decode("ascii").lower(),
        "urlsafe_base64": base64.urlsafe_b64encode(raw).decode("ascii"),
        "hex": raw.hex(),
    }


# ══════════════ §10.5 #15:遞迴的秘密**與編碼秘密**掃描 ══════════════════════════
@pytest.mark.parametrize("form_name", sorted(_encoded_forms(_SENTINEL)))
def test_every_encoded_sentinel_form_reaching_a_serializable_surface_is_a_leak(
    form_name: str,
) -> None:
    """§10.5 #15 明文要求 *encoded-secret* 掃描。``assert_no_secret_material`` 一直有做,
    但在 W5 之前**沒有任何測試**碰過明文以外的形——刪掉四種編碼形全樹仍綠。"""

    form = _encoded_forms(_SENTINEL)[form_name]
    # 藏在巢狀結構深處:list -> dict -> str(掃描必須是遞迴的)。
    artifact = {"reasons": [{"detail": f"observed dsn={form}"}]}
    with pytest.raises(credential.SecretMaterialLeak):
        credential.assert_no_secret_material(artifact, [_SENTINEL])


def test_a_secret_rendered_into_a_dict_key_or_a_bytes_node_is_still_a_leak() -> None:
    """秘密可以出現在**鍵**上,也可以是 bytes;兩條走訪邊都必須被覆蓋。"""

    forms = _encoded_forms(_SENTINEL)
    with pytest.raises(credential.SecretMaterialLeak):
        credential.assert_no_secret_material({forms["base64"]: "x"}, [_SENTINEL])
    with pytest.raises(credential.SecretMaterialLeak):
        credential.assert_no_secret_material(
            {"blob": _SENTINEL.encode("utf-8")}, [_SENTINEL]
        )
    with pytest.raises(credential.SecretMaterialLeak):
        credential.assert_no_secret_material(
            ("outer", ["inner", forms["hex"]]), [_SENTINEL]
        )


def test_the_secret_scanner_is_a_real_predicate_not_a_constant() -> None:
    """一個對任何輸入都拋例外的掃描器,或一個沒有哨兵就拒絕一切的掃描器,都證明不了東西。"""

    credential.assert_no_secret_material(
        {"reasons": ["nothing sensitive here"], "digest": "sha256:" + "0" * 64}, [_SENTINEL]
    )
    # 沒有活哨兵 = 沒有可掃的東西(而不是把所有字串都當秘密)。
    credential.assert_no_secret_material({"reasons": [_SENTINEL]}, [])


def test_a_base64_rendered_secret_never_reaches_a_row_verdict(signed) -> None:
    """端到端:五 row 唯一的出境面 ``_verdict`` 也必須擋住**編碼**形,不只明文。

    既有的 ``test_a_verdict_that_would_carry_secret_material_is_dropped_wholesale`` 用的是
    明文密碼,所以生產路徑上的編碼形分支從來沒被走過。
    """

    from test_agent_governance_s2_4_host_identity import (
        _FakeHostIdentityDriver, _host_identity_intent,
    )

    broker = credential.SecretBroker(operation_id="w5-op")
    pg_handle = broker.mint_first_provisioning_handles()[0]
    password = pg_handle.consume(operation_id="w5-op").decode("ascii")
    encoded = base64.b64encode(password.encode("utf-8")).decode("ascii")
    intent, manifest = _host_identity_intent()

    class _Base64LeakyDriver(_FakeHostIdentityDriver):
        def independent_postcheck(self, *, component_effect_class, install_plan_digest,
                                  applier_node):
            observed = super().independent_postcheck(
                component_effect_class=component_effect_class,
                install_plan_digest=install_plan_digest, applier_node=applier_node,
            )
            # 明文從未出現;只有 base64 形。
            observed["verifier_node"] = f"s2-4-verifier?blob={encoded}"
            return observed

    driver = _Base64LeakyDriver()
    leaked = driver.independent_postcheck(
        component_effect_class="HOST_IDENTITY_INSTALL",
        install_plan_digest=kit.PLAN_DIGEST, applier_node="s2-4-host-identity-applier",
    )
    assert password not in leaked["verifier_node"]
    assert encoded in leaked["verifier_node"]
    verdict = apply_mod.apply_s2_4_host_identity(
        intent, driver=driver, uid_gid_directory_manifest=manifest,
        **kit.common_apply_kwargs(signed),
    )
    assert verdict["status"] == "SECRET_MATERIAL_LEAK_BLOCKED"
    assert verdict["blocks_aggregate"] is True
    assert encoded not in json.dumps(verdict, default=str)
    broker.zeroize_all()


# ══════════════ §10.5 #12:S2.4 永不建立/刪除/收回 observer 身分 ═════════════════
def test_the_acl_manifest_schema_pins_the_scanner_role_by_const() -> None:
    """``role_name`` 是 schema 層的 const。它一旦鬆成 ``{"type": "string"}``,S2.4 的
    ``drop_task_owned_role`` / ``revoke_manifest_grants`` 就能被指到任何角色上。"""

    schema = validator._load_schema("pg_acl_manifest_v1")
    assert schema["properties"]["role_name"] == {"const": "aiml_engine_scanner"}
    assert schema["properties"]["component"] == {"const": "engine_scanner"}


def test_an_acl_manifest_naming_the_observer_role_is_refused_before_any_driver_contact(
    signed,
) -> None:
    """§10.5 #12 的真謂詞:即使 caller 遞交一份「內部自洽」(self_digest 已重算)的
    manifest,把角色換成 ``aiml_observer_ro``,也必須在任何 driver 接觸之前 typed 拒絕。

    既有測試斷言的是「revoked_statements 裡沒有 observer」——那在 fixture manifest 從不
    提及 observer 的前提下恆真,證明不了任何 source 行為。
    """

    attestation = kit.topology_attestation()
    forged = deepcopy(kit.PG_ACL_MANIFEST)
    forged["role_name"] = "aiml_observer_ro"
    forged["self_digest"] = validator.artifact_self_digest(forged)
    # 中央閘直接拒(closed schema 的 const)。
    assert validator.validate_aiml_artifact(forged)

    driver = _FakePgDriver()
    verdict = apply_mod.apply_s2_4_pg_role_acl(
        _pg_intent(attestation), driver=driver,
        **_pg_kwargs(attestation, acl_manifest=forged),
        **kit.common_apply_kwargs(signed, pg=True),
    )
    assert verdict["status"] == "PRECHECK_FAILED"
    assert verdict["mutation_performed"] is False
    assert driver.calls == []
    assert driver.dropped is False
    assert driver.revoked_statements == []


def test_no_generated_statement_names_a_role_other_than_the_scanner_or_public() -> None:
    """唯一的 SQL 產生點只會提到 scanner 角色本身,或 §2.1 封閉邊界要收回的 PUBLIC。"""

    manifest = deepcopy(kit.PG_ACL_MANIFEST)
    statements = list(apply_mod.generate_manifest_grant_statements(manifest)) + list(
        apply_mod.generate_manifest_revoke_statements(manifest)
    )
    assert statements
    for statement in statements:
        assert (
            '"aiml_engine_scanner"' in statement
            or statement.rstrip().endswith("FROM PUBLIC")
        ), statement
        assert "aiml_observer_ro" not in statement


def test_the_observer_role_is_absent_from_the_whole_s2_4_apply_surface() -> None:
    """S2.4 的 PG row 只在**補償**時提到 observer,而且只是「必須存活」的再確認,
    不是任何 create/drop/revoke 面。"""

    text = (HELPERS / "agent_governance_s2_4_apply.py").read_text(encoding="utf-8")
    for verb in ("CREATE ROLE", "DROP ROLE", "ALTER ROLE"):
        assert f'{verb} "aiml_observer_ro"' not in text
    manifest = json.loads(
        (ML_ROOT / "pg_acl_manifest_v1.json").read_text(encoding="utf-8")
    )
    assert manifest["role_name"] == "aiml_engine_scanner"
    assert "aiml_observer_ro" not in json.dumps(manifest)


# ══════════════ §10.5 #16:WP4 不安裝 controller/fit_evaluation/serving/deleter ══
@pytest.mark.parametrize("identity", [
    "controller", "fit_evaluation", "serving", "deleter",
    "aiml_controller", "aiml_fit_evaluation", "aiml_serving", "aiml_deleter",
])
def test_wp4_installs_no_controller_fit_evaluation_serving_or_deleter(identity: str) -> None:
    """§2 明文:那四個元件的身分只在其擁有 session 才會啟用。此前**零測試**。"""

    surface = " ".join(
        list(runner.APPLY_ROW_ORDER)
        + sorted(AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2)
        + sorted(runner.ROW_APPLIER_NODES.values())
        + sorted(runner.ROW_PAYLOAD_ALLOWLIST)
    ).lower()
    assert identity not in surface
    manifest = json.loads(
        (ML_ROOT / "pg_acl_manifest_v1.json").read_text(encoding="utf-8")
    )
    assert identity not in json.dumps(manifest).lower()


def test_the_aggregate_drives_exactly_the_five_engine_scanner_rows() -> None:
    assert list(runner.APPLY_ROW_ORDER) == [
        "HOST_IDENTITY_INSTALL", "PG_ROLE_ACL_MIGRATION", "CREDENTIAL_INSTALL",
        "LEARNING_RUNTIME", "ENGINE_SCANNER",
    ]
    assert sorted(AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2) == [
        "CREDENTIAL_INSTALL", "ENGINE_SCANNER", "HOST_CAPABILITY_PROBE",
        "HOST_IDENTITY_INSTALL", "LEARNING_RUNTIME", "LEARNING_RUNTIME_PREPARE",
        "PG_ROLE_ACL_MIGRATION",
    ]


# ══════════════ §10.5 #29:inactive postcheck 不作 runtime/憑證宣稱 ══════════════
@pytest.mark.parametrize("schema_key", [
    "s2_4_install_postcheck_v1", "s2_4_install_effect_receipt_v1",
])
def test_the_s2_4_terminal_artifacts_carry_no_runtime_or_decrypted_credential_claim(
    schema_key: str,
) -> None:
    """§10.5 #29:S2.4 只觀測 loaded+disabled+inactive。終端 artifact 的封閉欄位集不得
    出現 runtime-directory / 已解密憑證 / running 這類宣稱面。"""

    schema = validator._load_schema(schema_key)
    assert schema.get("additionalProperties") is False
    properties = sorted(schema.get("properties", {}))
    for marker in ("runtime_director", "decrypt", "enabled", "active", "running"):
        offenders = [name for name in properties if marker in name]
        assert not offenders, (schema_key, marker, offenders)


@pytest.mark.parametrize("verb", [
    "enable", "enable_unit", "start", "start_unit", "restart", "restart_unit",
    "kill", "send_signal", "start_transient_unit",
])
def test_the_aggregate_driver_surface_refuses_every_lifecycle_verb(verb: str) -> None:
    """``enable --now`` 屬 S2.5A(§12 #7)。aggregate driver 上出現任一生命週期面即 typed 拒,
    而且**絕不**被呼叫。"""

    assert verb in set(runner.FORBIDDEN_AGGREGATE_METHODS)
    called: list[str] = []
    stub = type(
        "_Lifecycle", (), {verb: lambda self, *a, **k: called.append(verb)}
    )()
    reasons = runner.assert_no_aggregate_forbidden_surface(stub)
    assert reasons and any(verb in reason for reason in reasons)
    assert called == []


def test_s2_5_lifecycle_source_now_exists_and_the_obligation_is_closed() -> None:
    """§10.5 #29 的後半句自 2026-07-28 起**有了 owner**(本測試舊版要求的 revisit):
    WP5 落地 S2.5 design + 三態 lifecycle fixtures,帳本 row 依 PM O-1 裁決改標
    ``CLOSED_BY_S2_5_SOURCE``(row 保留作歷史,不刪)。三個 subject 一起釘住,任一側
    倒退(design 消失/fixtures 消失/typed_status 軟化回 OUT_OF_WP4_SCOPE)即紅。"""

    design_dir = ROOT / "docs/execution_plan/ai_ml_landing/design"
    assert sorted(path.name for path in design_dir.glob("S2.5-*.md")) == [
        "S2.5-running-attestation-source-seam.md"
    ], "the S2.5 design vanished (or forked); §10.5 #29's second clause lost its owner"
    row = next(
        row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
        if row["obligation_id"] == "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST"
    )
    assert row["typed_status"] == "CLOSED_BY_S2_5_SOURCE", row["typed_status"]
    fixtures = ROOT / "tests/structure/test_agent_governance_s2_5_lifecycle_fixtures.py"
    assert fixtures.is_file() and fixtures.read_text(encoding="utf-8").strip(), (
        "the S2.5 lifecycle fixtures file is absent/empty while the ledger row claims "
        "CLOSED_BY_S2_5_SOURCE"
    )


# ══════════════ §10.5 #11 / §12 #3:system Python 與已退役身分 ═══════════════════
def _mutate_unit(rendered: str, kind: str) -> str:
    if kind == "system_interpreter":
        line = next(l for l in rendered.splitlines() if l.startswith("ExecStart="))
        return rendered.replace(line, "ExecStart=/usr/bin/python3 -I -B \\")
    if kind == "alr_shadow_user":
        return rendered.replace("User=aiml-engine-scanner", "User=alr_shadow")
    if kind == "alr_shadow_group":
        return rendered.replace("Group=aiml-engine-scanner", "Group=alr_shadow")
    if kind == "mutable_checkout":
        return rendered.replace(
            "WorkingDirectory=/var/lib/arcane-equilibrium/aiml/engine-scanner",
            "WorkingDirectory=/home/ncyu/BybitOpenClaw/srv",
        )
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", [
    "system_interpreter", "alr_shadow_user", "alr_shadow_group", "mutable_checkout",
])
def test_a_system_interpreter_or_retired_identity_in_the_unit_is_a_typed_rejection(
    kind: str,
) -> None:
    """§12 #3:生產 unit 不得用 system Python 或可變 checkout;§8.3/PR #134 之後
    ``alr_shadow`` 不再是 S2.4 的任何身分。此前三者都沒有顯式負向。"""

    rendered = render.render_engine_scanner_unit(dict(_UNIT_FIELDS))
    assert render.derive_rendered_unit_status(rendered)["status"] == "PASS"
    verdict = render.derive_rendered_unit_status(_mutate_unit(rendered, kind))
    assert verdict["status"] == "ENGINE_SCANNER_UNIT_INVALID"
    assert verdict["reasons"]


def test_the_clean_rendered_unit_carries_neither_system_python_nor_alr_shadow() -> None:
    rendered = render.render_engine_scanner_unit(dict(_UNIT_FIELDS))
    assert "ExecStart=/opt/arcane-equilibrium/aiml/launches/" in rendered
    assert "/usr/bin/python3" not in rendered
    assert "alr_shadow" not in rendered
    assert "systemctl --user" not in rendered


# ══════════════ §10.5 #1:S2.4 schema 的中央註冊完整性 ═══════════════════════════
def test_every_s2_4_schema_is_registered_centrally_and_resolves_to_a_real_file() -> None:
    """CP2a/CP2b 逐份 round-trip 了 30 份 schema,但沒有任何測試要求「S2.4 的**每一份**
    schema 都在中央委派表上」——新增一份沒人 round-trip 的 schema 不會弄紅任何東西。"""

    live = validator.w5_exported_abi_projection()["schema_registration_live"]
    assert live["unregistered_schema_keys"] == []
    assert live["unresolvable_schema_keys"] == []
    assert live["undeclared_on_disk_schema_keys"] == []
    # 39 = W5 前半段的 38 份 + §10.1 明列而當時缺席、W5 後半段補上的 §9.2 refresh schema。
    assert live["s2_4_schema_count"] == 39
    assert live["dependency_refresh_schema_registered"] is True
    assert live["dependency_refresh_schema_file_exists"] is True


def test_the_schema_directory_holds_no_s2_4_schema_outside_the_declared_inventory() -> None:
    """反向:目錄裡多出一份 S2.4 schema 而沒進 W5 的宣告集合,同樣必須轉紅。"""

    from aiml_gate_receipt_wave_w5 import (
        _DEPENDENCY_REFRESH_SCHEMA, _S2_4_SCHEMA_KEYS,
    )

    schema_dir = ML_ROOT / "schemas/aiml_gate_receipts"
    on_disk = {
        path.name[: -len(".schema.json")]
        for path in schema_dir.glob("*.schema.json")
        if path.name.startswith(("s2_4_", "pg_acl_", "pg_topology_"))
    }
    undeclared = sorted(on_disk - set(_S2_4_SCHEMA_KEYS) - {_DEPENDENCY_REFRESH_SCHEMA})
    assert undeclared == [], (
        f"S2.4 schemas exist on disk but are outside W5's declared inventory: {undeclared}"
    )


# ═════════ §10.5 #28 前半:過期 source 身分需要一份獨立重算的 refresh ═════════════
# 正向素材是 repo 內**真實且已過期**的 S2.2A receipt(generated_at_utc=2026-07-24,
# code-owned 觀測 TTL 3600s),不是合成 fixture;時鐘一律顯式凍結,絕不取 wall clock。
_REFRESH_NOW = "2026-07-27T00:05:00+00:00"
_REFRESH_REPRODUCED_AT = "2026-07-27T00:00:00+00:00"
_REFRESH_CALLER = "E1:S2.4:W5-dependency-refresh-test"
_REFRESH_PLATFORM = {"os": "darwin", "arch": "arm64", "python_version": "3.12"}
_S2_2A_V1 = "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v1.json"
_S2_2A_V2 = "docs/execution_plan/ai_ml_landing/receipts/S2.2A-source-compatibility-receipt-v2.json"
_S2_3_SEALED = "docs/execution_plan/ai_ml_landing/receipts/S2.3-sealed-build-receipt-v1.json"
_S2_3_IDENTITY = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.3-expected-identity-receipt-v1.json"
)


def _receipt(rel: str) -> dict:
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def _reseal(artifact: dict) -> dict:
    artifact = dict(artifact)
    artifact.pop("self_digest", None)
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


def _refresh(original: dict, **overrides) -> dict:
    return validator.build_s2_4_dependency_refresh_attestation(
        original,
        reproducer_caller=overrides.pop("reproducer_caller", _REFRESH_CALLER),
        reproducer_platform=dict(_REFRESH_PLATFORM),
        reproduced_at=overrides.pop("reproduced_at", _REFRESH_REPRODUCED_AT),
        **overrides,
    )


def _derive(refresh, original) -> dict:
    return validator.derive_dependency_refresh_status(
        refresh, original_receipt=original, now=_REFRESH_NOW
    )


@pytest.fixture(scope="module")
def s2_2a_pair():
    original = _receipt(_S2_2A_V1)
    return original, _refresh(original)


def test_one_independently_reproduced_refresh_admits_the_expired_source_identity(
    s2_2a_pair,
) -> None:
    """§9.2 正向:真實已過期的 S2.2A 身分 + 一份獨立重算的 refresh = 被採信。

    復現值不是 caller 帶進來的——builder 與閘共用同一支
    ``reproduce_dependency_semantic_digests``,它只從當前 checkout 的位元組算。
    """

    original, refresh = s2_2a_pair
    # 原身分**確實**已過期(否則正向路徑證不到任何東西)。
    window = validator.dependency_original_observation_window(original)
    assert window[1] < _REFRESH_NOW
    assert validator.validate_aiml_artifact(refresh) == []
    assert not any(key in refresh for key in validator._CALLER_STATUS_KEYS)
    assert refresh["production_authority_flags"] == {
        "nine_authorities_false": True,
        "production_apply_performed": False,
        "running_attested": False,
    }
    outcome = _derive(refresh, original)
    assert outcome == {
        "status": "DEPENDENCY_REFRESH_ADMITTED",
        "reasons": [],
        "dependency_class": "S2_2A_SOURCE_COMPATIBILITY",
        "reproduced_semantic_digests": {
            "capture_contract_digest": original["capture_contract_digest"],
            "learning_runtime_digest": original["learning_runtime_digest"],
            "training_contract_digest": original["training_contract_digest"],
        },
        "admits_expired_source_identity": True,
    }
    admission = validator.derive_source_dependency_admission_status(
        evidence_class="S2_2A_SOURCE_COMPATIBILITY",
        receipt=original,
        refresh=refresh,
        now=_REFRESH_NOW,
    )
    assert admission["status"] == "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"
    assert admission["refresh_admitted"] is True
    assert admission["runtime_observation_substituted"] is False
    # 沒有 refresh 時,同一份過期身分不被採信。
    assert validator.derive_source_dependency_admission_status(
        evidence_class="S2_2A_SOURCE_COMPATIBILITY", receipt=original, now=_REFRESH_NOW
    )["status"] == "SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH"


@pytest.mark.parametrize(
    "rel,dependency_class",
    (
        (_S2_2A_V2, "S2_2A_SOURCE_COMPATIBILITY"),
        (_S2_3_SEALED, "S2_3_SEALED_BUILD"),
        (_S2_3_IDENTITY, "S2_3_EXPECTED_IDENTITY"),
    ),
)
def test_every_shipped_expired_source_identity_is_refreshable(rel, dependency_class) -> None:
    """§9.2 第一列的三族在 repo 內都有真實、已過期的 receipt,且都能被獨立復現。"""

    original = _receipt(rel)
    refresh = _refresh(original)
    assert refresh["dependency_class"] == dependency_class
    assert _derive(refresh, original)["status"] == "DEPENDENCY_REFRESH_ADMITTED"
    assert validator.derive_source_dependency_admission_status(
        evidence_class=dependency_class, receipt=original, refresh=refresh, now=_REFRESH_NOW
    )["status"] == "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"


def test_a_refresh_that_merely_reasserts_the_original_digest_does_not_admit(
    s2_2a_pair,
) -> None:
    """§9.2:「independently RECOMPUTED」——把原 receipt 的 digest 抄進復現欄位不算復現。"""

    original, refresh = s2_2a_pair
    forged = _reseal({
        **refresh,
        "reproduced_semantic_digests": {
            field: refresh["original_receipt_digest"]
            for field in refresh["reproduced_semantic_digests"]
        },
    })
    outcome = _derive(forged, original)
    assert outcome["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any("merely re-asserts" in reason for reason in outcome["reasons"])
    # 中央閘的**自足**分支也擋得住(不需要原 receipt 就能看出這是複述)。
    assert any(
        "merely re-asserts" in error for error in validator.validate_aiml_artifact(forged)
    )


def test_a_refresh_produced_by_the_original_producer_node_does_not_admit(
    s2_2a_pair,
) -> None:
    """§9.2:「independently replays」——同一個 producer 標籤重放的不是獨立復現。"""

    original, _refresh_ok = s2_2a_pair
    same_node = _refresh(original, reproducer_caller=original["session_id"])
    outcome = _derive(same_node, original)
    assert outcome["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any("same node/caller" in reason for reason in outcome["reasons"])


def test_a_refresh_reproduced_inside_the_original_observation_window_does_not_admit(
    s2_2a_pair,
) -> None:
    """同一次觀測不能被改寫成 refresh:``reproduced_at`` 必須嚴格晚於原證據的到期時刻。

    這一條是「不同節點」宣告面之外**結構性**的那一半:即使同一台機器,它也不可能在原觀測窗
    之內產出一份合格的 refresh。
    """

    original, _ok = s2_2a_pair
    window = validator.dependency_original_observation_window(original)
    inside = _refresh(original, reproduced_at=window[0])
    outcome = validator.derive_dependency_refresh_status(
        inside, original_receipt=original, now=_REFRESH_NOW
    )
    assert outcome["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any(
        "not strictly after the original evidence's own expiry" in reason
        for reason in outcome["reasons"]
    )


def test_a_refresh_cannot_refresh_another_refresh(s2_2a_pair) -> None:
    """§9.2 / §12 #15:refresh 不得續 refresh——builder 與閘兩側都拒,schema enum 亦不含它。"""

    original, refresh = s2_2a_pair
    outcome = _derive(refresh, refresh)
    assert outcome["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any("cannot refresh another refresh" in r for r in outcome["reasons"])
    with pytest.raises(ValueError, match="cannot refresh another refresh"):
        _refresh(refresh)
    schema = validator._load_schema("s2_4_dependency_refresh_attestation_v1")
    assert "s2_4_dependency_refresh_attestation_v1" not in (
        schema["properties"]["original_schema_version"]["enum"]
    )


def test_a_refresh_cannot_self_declare_its_own_status(s2_2a_pair) -> None:
    """§10.3 / §12 #15:S2.4 沒有任何 artifact 自證 status——refresh 也不例外。"""

    original, refresh = s2_2a_pair
    for key in validator._CALLER_STATUS_KEYS:
        declared = {**refresh, key: "ADMITTED"}
        outcome = _derive(declared, original)
        assert outcome["status"] == "DEPENDENCY_REFRESH_REJECTED"
        assert any("must not self-declare status" in r for r in outcome["reasons"])
        # 中央閘更早一層就擋掉:closed schema 的 additionalProperties:false 讓自證欄位
        # 連進到 W5 分支的機會都沒有(兩道各自獨立,拿掉任一道另一道仍拒)。
        assert any(
            f"unexpected property {key}" in e
            for e in validator.validate_aiml_artifact(_reseal(declared))
        )


def test_a_substituted_or_stale_dependency_identity_does_not_admit(s2_2a_pair) -> None:
    """被替換的原身分 / 過時的 head / 已漂移的語義 digest,三者都不得被續命。"""

    original, refresh = s2_2a_pair
    # (a) 拿另一份身分(v2 receipt)來對 v1 的 refresh。
    substituted = _derive(refresh, _receipt(_S2_2A_V2))
    assert substituted["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any("substituted source identity" in r for r in substituted["reasons"])
    # (b) 不是當前 head 的復現。
    stale_head = _derive(_reseal({**refresh, "current_source_head": "0" * 40}), original)
    assert stale_head["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any("current checkout HEAD" in r for r in stale_head["reasons"])
    # (c) 原 receipt 的語義 digest 在當前 head 上已重算不出來 → 只能重新觀測,不能刷新。
    drifted = _reseal({**original, "learning_runtime_digest": "sha256:" + "a" * 64})
    drift = _derive(
        _reseal({
            **refresh,
            "original_receipt_digest": validator.artifact_self_digest(drifted),
        }),
        drifted,
    )
    assert drift["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any("must be re-observed, not refreshed" in r for r in drift["reasons"])


def test_the_refresh_is_an_exact_field_set_bound_by_its_canonical_digest(
    s2_2a_pair,
) -> None:
    """與 S2.4 receipt 家族同一套慣例:exact 欄位集 + canonical self-digest 反偽造重算。"""

    original, refresh = s2_2a_pair
    schema = validator._load_schema("s2_4_dependency_refresh_attestation_v1")
    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == sorted(schema["properties"])
    assert sorted(refresh) == sorted(schema["properties"])
    # (a) 多一個欄位 → closed schema 拒(self_digest 會把任意鍵一併雜湊,故只靠它抓不到)。
    extra = _reseal({**refresh, "operator_note": "x"})
    assert validator.validate_aiml_artifact(extra) != []
    assert _derive(extra, original)["status"] == "DEPENDENCY_REFRESH_REJECTED"
    # (b) 少一個欄位 → 拒。
    for field in ("producer_module_digest", "reproduction", "refresh_ttl_seconds"):
        missing = _reseal({k: v for k, v in refresh.items() if k != field})
        assert validator.validate_aiml_artifact(missing) != []
    # (c) 竄改任一欄位而不重封 self_digest → 拒。
    for field, value in (
        ("current_source_head", "1" * 40),
        ("original_expires_at", "2099-01-01T00:00:00+00:00"),
        ("refresh_ttl_seconds", 60),
    ):
        tampered = {**refresh, field: value}
        assert any(
            "self_digest" in e for e in validator.validate_aiml_artifact(tampered)
        ), field
        assert _derive(tampered, original)["status"] == "DEPENDENCY_REFRESH_REJECTED"
    # (d) 復現欄位集不是該族的 exact 集合 → 拒。
    partial = _reseal({
        **refresh,
        "reproduced_semantic_digests": {
            "learning_runtime_digest": refresh["reproduced_semantic_digests"][
                "learning_runtime_digest"
            ]
        },
    })
    assert any(
        "exact §9.2 semantic-digest field set" in e
        for e in validator.validate_aiml_artifact(partial)
    )
    assert _derive(partial, original)["status"] == "DEPENDENCY_REFRESH_REJECTED"
    # (e) 新窗必須短且與 reproduced_at 一致,且 refresh 自身不得已過期。
    assert refresh["refresh_ttl_seconds"] <= validator.MAX_DEPENDENCY_REFRESH_TTL_SECONDS
    expired = _reseal({
        **refresh,
        "expires_at": "2026-07-27T00:01:00+00:00",
        "refresh_ttl_seconds": 60,
    })
    outcome = validator.derive_dependency_refresh_status(
        expired, original_receipt=original, now=_REFRESH_NOW
    )
    assert outcome["status"] == "DEPENDENCY_REFRESH_REJECTED"
    assert any("itself expired" in r for r in outcome["reasons"])


def test_expired_runtime_topology_prepare_and_auth_evidence_route_through_the_same_gate(
    s2_2a_pair,
) -> None:
    """§10.5 #28 後半:§9.2 明列「必須新鮮觀測/新鮮授權/重新雜湊/重新簽章」的每一列,
    遞交任何 refresh 一律 typed 拒。既有的 TTL lane(derive_apply_remaining_ttls)已證
    「過期即拒」,這裡證的是**另一件事**:那些證據**連被刷新的資格都沒有**。"""

    _original, refresh = s2_2a_pair
    never = validator.S2_4_NEVER_REFRESHABLE_EVIDENCE
    assert sorted(never) == [
        "APPLY_AGGREGATE_AUTHORIZATION",
        "CAPABILITY_PROBE_AUTHORIZATION",
        "CAPABILITY_PROBE_RECEIPT_INSTALLED_UNIT",
        "CAPABILITY_PROBE_RECEIPT_PREPARE_SANDBOX",
        "PG_MIGRATION_AUTHORIZATION",
        "PG_TOPOLOGY_ATTESTATION",
        "PREPARED_BUNDLE",
        "PREPARE_AUTHORIZATION",
        "S2_0_EFFECT_RECEIPT",
    ]
    for name in never:
        # 即使該證據**還沒過期**,遞交 refresh 本身就是被禁的行為。此判定先於一切,故
        # 它「不」依賴那份證據是否合格——refresh-by-reference 對這一列永遠非法。
        forbidden = validator.derive_source_dependency_admission_status(
            evidence_class=name,
            receipt={"expires_at": "2099-01-01T00:00:00+00:00"},
            refresh=refresh,
            now=_REFRESH_NOW,
        )
        assert forbidden["status"] == "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN", name
        assert forbidden["refresh_admitted"] is False
        # W5 review P2-D:``evidence_class`` 是 caller 遞交的字串。一個兩鍵 stub 冠上這些
        # 名字時,**不論**新舊都不得導出任何 §9.2 語義(它根本不是那份 artifact)。
        for expires in ("2099-01-01T00:00:00+00:00", "2026-07-24T00:00:00+00:00"):
            stub = validator.derive_source_dependency_admission_status(
                evidence_class=name, receipt={"expires_at": expires}, now=_REFRESH_NOW
            )
            assert stub["status"] == "SOURCE_DEPENDENCY_REJECTED", (name, expires)
            assert any("is not one of the artifacts" in r for r in stub["reasons"]), name
    # DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED 仍然可達,但只對**真的**是那份 artifact
    # 的證據:以 W3b testkit 的真 pg_topology_attestation_v1 逐條走完三個 §9.2 出口。
    fresh_topology = kit.topology_attestation()
    expired_topology = _topology.observe_pg_topology(
        kit.topology_observation(),
        source_head=kit.SOURCE_HEAD, target_host=kit.HOST,
        observed_at="2026-07-20T00:00:00+00:00",
    )
    assert validator.validate_aiml_artifact(fresh_topology) == []
    assert validator.validate_aiml_artifact(expired_topology) == []
    assert validator.derive_source_dependency_admission_status(
        evidence_class="PG_TOPOLOGY_ATTESTATION", receipt=fresh_topology, now=_REFRESH_NOW
    )["status"] == "SOURCE_DEPENDENCY_FRESH"
    reobserve = validator.derive_source_dependency_admission_status(
        evidence_class="PG_TOPOLOGY_ATTESTATION", receipt=expired_topology, now=_REFRESH_NOW
    )
    assert reobserve["status"] == "DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED"
    assert validator.derive_source_dependency_admission_status(
        evidence_class="PG_TOPOLOGY_ATTESTATION", receipt=expired_topology,
        refresh=refresh, now=_REFRESH_NOW,
    )["status"] == "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN"
    # 冠錯類別的**真** artifact 一樣不通過:身分由 code-owned 表決定,不由標籤決定。
    assert validator.derive_source_dependency_admission_status(
        evidence_class="PREPARED_BUNDLE", receipt=fresh_topology, now=_REFRESH_NOW
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"
    # 封閉表:未知類別不預設放行。
    assert validator.derive_source_dependency_admission_status(
        evidence_class="SOMETHING_ELSE", receipt={}, now=_REFRESH_NOW
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"


def test_a_genuine_artifact_of_the_wrong_profile_or_scope_is_not_the_named_evidence(
    tmp_path, monkeypatch,
) -> None:
    """S2.4-AMEND-1(obligation 26):class→artifact 解析綁 §9.1 判別欄位,換標籤買不到 FRESH。

    四個 permit 列 / 兩個 probe 列 many-to-one 映到同一份 schema;判別欄位
    (profile_identity / probe_scope)在 ``_dependency_evidence_receipt_errors`` 執法,
    值由凍結的 §9.1 profiles 導出而非手抄。"""

    import aiml_gate_receipt_s2_4_contracts as contracts

    private_key, public_key, fingerprint = kit.mint_key(tmp_path)
    kit.install_pinned_key(monkeypatch, public_key, fingerprint)
    prepare_permit = kit.authorization(private_key, profile_key="prepare")
    # 真 PREPARE permit 冠 APPLY_AGGREGATE_AUTHORIZATION → REJECTED(非 FRESH)。
    wrong = validator.derive_source_dependency_admission_status(
        evidence_class="APPLY_AGGREGATE_AUTHORIZATION", receipt=prepare_permit, now=kit.NOW
    )
    assert wrong["status"] == "SOURCE_DEPENDENCY_REJECTED"
    assert any("wrong §9.1 profile/scope" in r for r in wrong["reasons"])
    # 正對照:正確 profile + 未過期 → FRESH(判別表不擋真身分)。
    assert validator.derive_source_dependency_admission_status(
        evidence_class="PREPARE_AUTHORIZATION", receipt=prepare_permit, now=kit.NOW
    )["status"] == "SOURCE_DEPENDENCY_FRESH"
    # probe_scope 兩向錯配 + 正對照。
    sandbox = kit.terminal_probe_evidence(private_key)["PREPARE_SANDBOX"]["effect_receipt"]
    mismatched = validator.derive_source_dependency_admission_status(
        evidence_class="CAPABILITY_PROBE_RECEIPT_INSTALLED_UNIT", receipt=sandbox,
        now=kit.NOW,
    )
    assert mismatched["status"] == "SOURCE_DEPENDENCY_REJECTED"
    assert any("wrong §9.1 profile/scope" in r for r in mismatched["reasons"])
    assert validator.derive_source_dependency_admission_status(
        evidence_class="CAPABILITY_PROBE_RECEIPT_PREPARE_SANDBOX", receipt=sandbox,
        now=kit.NOW,
    )["status"] == "SOURCE_DEPENDENCY_FRESH"
    installed = kit.terminal_probe_evidence(private_key, scope="INSTALLED_UNIT")[
        "INSTALLED_UNIT"]["effect_receipt"]
    assert validator.derive_source_dependency_admission_status(
        evidence_class="CAPABILITY_PROBE_RECEIPT_PREPARE_SANDBOX", receipt=installed,
        now=kit.NOW,
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"
    # 判別表由凍結 §9.1 profiles 導出(不手抄),四 permit 列逐一對得上。
    for cls, profile_key in (
        ("APPLY_AGGREGATE_AUTHORIZATION", "apply_aggregate"),
        ("PREPARE_AUTHORIZATION", "prepare"),
        ("PG_MIGRATION_AUTHORIZATION", "pg_migration"),
        ("CAPABILITY_PROBE_AUTHORIZATION", "capability_probe"),
    ):
        assert contracts.S2_4_EVIDENCE_CLASS_DISCRIMINATORS[cls] == (
            "profile_identity",
            validator.S2_4_AUTHORIZATION_PROFILES[profile_key]["profile_identity"],
        )
    assert sorted(contracts.S2_4_EVIDENCE_CLASS_DISCRIMINATORS) == [
        "APPLY_AGGREGATE_AUTHORIZATION",
        "CAPABILITY_PROBE_AUTHORIZATION",
        "CAPABILITY_PROBE_RECEIPT_INSTALLED_UNIT",
        "CAPABILITY_PROBE_RECEIPT_PREPARE_SANDBOX",
        "PG_MIGRATION_AUTHORIZATION",
        "PREPARE_AUTHORIZATION",
    ]


def test_exactly_one_current_refresh_admits_an_expired_source_identity(s2_2a_pair) -> None:
    """§9.2 逐字:「only together with ONE current refresh attestation」。"""

    original, refresh = s2_2a_pair
    assert validator.derive_source_dependency_admission_status(
        evidence_class="S2_2A_SOURCE_COMPATIBILITY",
        receipt=original,
        refresh=[refresh, refresh],
        now=_REFRESH_NOW,
    )["status"] == "SOURCE_DEPENDENCY_REJECTED"
    assert validator.derive_source_dependency_admission_status(
        evidence_class="S2_2A_SOURCE_COMPATIBILITY",
        receipt=original,
        refresh=[refresh],
        now=_REFRESH_NOW,
    )["status"] == "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"


def test_the_refresh_carries_no_signature_surface_and_adds_no_ninth_authority(
    s2_2a_pair,
) -> None:
    """簽章判斷的可測形:§9.2 只要求四項綁定,§9.1 把可用 profile 封閉在**四**個。

    若有人日後替 refresh 加上第五個 SSHSIG profile/namespace,這支測試會轉紅——那是
    §12 #15 明令禁止的 trust-root 變更,不是 WP4 worker 可自選的實作細節。
    """

    _original, refresh = s2_2a_pair
    schema = validator._load_schema("s2_4_dependency_refresh_attestation_v1")
    for marker in ("signature", "sshsig", "namespace", "profile_identity", "signer"):
        assert not any(marker in name for name in schema["properties"]), marker
        assert not any(marker in name for name in refresh), marker
    assert sorted(validator.S2_4_AUTHORIZATION_PROFILES) == [
        "apply_aggregate", "capability_probe", "pg_migration", "prepare",
    ]
    assert validator.s2_4_authorization_profiles_digest() == (
        "sha256:79b27b7040e8a8d3af84b6a5f0c7c20e45888caaedac146428145ffea54be2dc"
    )


# ══════════════════ 誠實記錄:W5 不能在 source 關閉的義務 ═════════════════════════
def test_the_dependency_refresh_residuals_are_named_precisely_not_blanketly() -> None:
    """§9.2 的閘已建成,舊的「整份缺席」義務必須被關掉,換成兩條**精確**的殘留。"""

    obligations = {
        row["obligation_id"]: row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    assert "DEPENDENCY_REFRESH_ATTESTATION_ABSENT" not in obligations
    binding = obligations["DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT"]
    # S2.4-AMEND-1 收口:row 保留作歷史(O-1 先例),typed_status 記關閉來源。
    assert binding["typed_status"] == "CLOSED_BY_S2_4_AMEND_1_SOURCE"
    assert binding["owner_wave"] == "PM"
    assert "§3" in binding["spec_refs"]
    # 關閉事實面:closed receipt schema 現帶必填 dependency_refresh_digests(仍封閉)。
    receipt_schema = validator._load_schema("s2_4_install_effect_receipt_v1")
    assert receipt_schema["additionalProperties"] is False
    assert "dependency_refresh_digests" in receipt_schema["properties"]
    assert "dependency_refresh_digests" in receipt_schema["required"]
    assert receipt_schema["properties"]["dependency_refresh_digests"][
        "additionalProperties"
    ] is False
    node = obligations["DEPENDENCY_REFRESH_REPRODUCER_NODE_IS_DECLARATIVE"]
    assert node["typed_status"] == "PARTIALLY_PROVIDED_BY_W5"
    assert node["owner_wave"] == "W6"
    assert "declarative" in node["statement"].casefold()
    # S2.2A 的 producer 標籤退化為 session_id 這件事被逐字記錄,而不是被藏起來。
    assert "session_id" in node["statement"]
    original = _receipt(_S2_2A_V1)
    assert "caller" not in original and "platform" not in original


def test_pr_set_dumpable_is_declared_but_enforced_nowhere_and_is_recorded() -> None:
    """§10.5 #26 要求 ``PR_SET_DUMPABLE=0`` 是 load-bearing。它不是:
    ``PROCESS_HARDENING_CONTRACT['pr_set_dumpable']`` 只出現在兩個投影 dict 裡,
    ``derive_host_credential_capability_status`` 從不看它,也沒有任何 driver 面觀測它。
    既有的 ``test_process_hardening_contract_is_load_bearing`` 斷言的是常數等於自己。"""

    assert credential.PROCESS_HARDENING_CONTRACT["pr_set_dumpable"] == 0
    # 沒有 pr_set_dumpable 的 capability 觀測依然「滿足」——這正是缺口。
    satisfied = credential.derive_host_credential_capability_status({
        "systemd_creds_available": True,
        "tpm2_available": True,
        "decryption_name_verification": True,
    })
    assert satisfied["status"] == "HOST_CREDENTIAL_CAPABILITY_SATISFIED"
    # 顯式宣告 dumpable=1 也照樣通過(因為根本沒被讀)。
    ignored = credential.derive_host_credential_capability_status({
        "systemd_creds_available": True,
        "tpm2_available": True,
        "decryption_name_verification": True,
        "pr_set_dumpable": 1,
    })
    assert ignored["status"] == "HOST_CREDENTIAL_CAPABILITY_SATISFIED"
    obligations = {
        row["obligation_id"]: row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    entry = obligations["PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED"]
    assert entry["owner_wave"] == "W6B"
    assert "test_process_hardening_contract_is_load_bearing" in entry["statement"]
    # #26 的其餘四款**是** load-bearing:tpm2 缺席即 typed 拒。
    refused = credential.derive_host_credential_capability_status({
        "systemd_creds_available": True,
        "tpm2_available": False,
        "decryption_name_verification": True,
    })
    assert refused["status"] == "HOST_CREDENTIAL_CAPABILITY_UNSATISFIED"


def test_both_halves_of_the_attestation_clock_obligation_are_still_open() -> None:
    """W4 的 ``ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED`` 兩半**都**還開著。

    這支測試存在的理由:W5 一度誤判半邊 (b) 已關(把 driver-clock 的 skew 上限錯認成
    attestation 已簽時間的比對)。這裡把真正的源碼事實釘死——
    ``derive_apply_attestation_status`` 只拿已簽的 ``trusted_host_time`` 去比
    ``attestation_expires_at`` / 900s TTL / 兩張 permit 窗,從不碰 ``driver.trusted_host_time()``,
    也從不碰觀測時刻;而 driver-clock 的 skew 上限是**另一條**較弱的關係,住在 install_driver。
    """

    from pathlib import Path as _Path

    evidence_src = (
        HELPERS / "agent_governance_s2_4_install_evidence.py"
    ).read_text(encoding="utf-8")
    start = evidence_src.index("def derive_apply_attestation_status")
    end = evidence_src.index("\ndef ", start + 1)
    body = evidence_src[start:end]
    # (b) 仍開:attestation 的驗證體內從不出現 driver 的 trusted_host_time() 呼叫。
    assert "driver.trusted_host_time" not in body
    assert "trusted_host_time()" not in body
    # (a) 仍開:驗證體內從不把觀測時刻(caller now / 時鐘 tick)拿來比 attestation_expires_at。
    assert "attestation_expires_at" in body
    for observed_anchor in ("resolve_now(now", "tick()", "datetime.now("):
        assert observed_anchor not in body, observed_anchor
    # 而那條**確實存在**的較弱關係住在 install_driver,並有具名回歸。
    driver_src = (
        HELPERS / "agent_governance_s2_4_install_driver.py"
    ).read_text(encoding="utf-8")
    assert "PERMIT_CLOCK_SKEW_SECONDS" in driver_src
    driver_tests = (
        ROOT / "tests/structure/test_agent_governance_s2_4_install_driver.py"
    ).read_text(encoding="utf-8")
    assert (
        "def test_c18_the_trusted_host_time_is_cross_checked_against_the_observed_time"
        in driver_tests
    )
    obligations = {
        row["obligation_id"]: row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    entry = obligations["ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED"]
    # 兩半都仍開 ⇒ typed_status 必須留在 W4 交出來的「未提供」等級。上一版把它軟化成
    # PARTIALLY_PROVIDED_BY_W4B,與它自己 statement 的第一句直接矛盾(對抗審計第二輪更正)。
    assert entry["typed_status"] == "NOT_PROVIDED_BY_W5"
    assert entry["owner_wave"] == "W6B"
    assert "BOTH halves W4 named are still open" in entry["statement"]
    assert "PERMIT_CLOCK_SKEW_SECONDS" in entry["statement"]
    assert _Path(ROOT).is_dir()
