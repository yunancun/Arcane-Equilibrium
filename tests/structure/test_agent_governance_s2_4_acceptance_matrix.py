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

另外兩條是**誠實記錄**而非新覆蓋:§10.5 #28 的「一份獨立重算的 refresh attestation」在此
checkout 上沒有 source 可測(§10.1 明列的 schema 檔不存在),而 §10.5 #26 的
``PR_SET_DUMPABLE=0`` 是一個沒有任何 enforcement 的宣告常數。兩者都以 W5 obligation 的形狀
釘在這裡,任何人默默拿掉義務或默默「實作了但沒關閉義務」都會轉紅。

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


def test_no_s2_5_lifecycle_source_exists_in_this_repository() -> None:
    """§10.5 #29 的後半句(「S2.5 fixtures own `enable --now`…」)在 WP4 沒有擁有者:
    S2.5 的 source 根本不存在。誠實記錄,而不是算成已覆蓋。"""

    design_dir = ROOT / "docs/execution_plan/ai_ml_landing/design"
    assert not list(design_dir.glob("S2.5-*.md")), (
        "an S2.5 design landed; §10.5 #29's second clause now has an owner and this "
        "test plus the S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST obligation must be revisited"
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
    assert live["s2_4_schema_count"] == 38


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


# ══════════════ 誠實記錄:兩項 W5 不能在 source 關閉的義務 ═══════════════════════
def test_the_dependency_refresh_attestation_is_absent_and_recorded_as_an_obligation() -> None:
    """§10.1 把 ``s2_4_dependency_refresh_attestation_v1.schema.json`` 列進 owned-path,
    §9.2 讓它成為過期 source 身分**唯一**的補救途徑,§10.3 的 W5 row 要求 W5 產出它。
    它在這個 head 上完全不存在:沒有 schema、沒有 SCHEMA_FILES 條目、沒有 validator 分支、
    沒有 builder、沒有測試。W5 不擁有「寫生產閘」,所以把它釘成 obligation。"""

    from aiml_gate_receipt_wave_w5 import _DEPENDENCY_REFRESH_SCHEMA

    declared = (
        ML_ROOT / "schemas/aiml_gate_receipts"
        / f"{_DEPENDENCY_REFRESH_SCHEMA}.schema.json"
    )
    absent = not declared.is_file() and _DEPENDENCY_REFRESH_SCHEMA not in (
        validator.SCHEMA_FILES
    )
    obligations = {
        row["obligation_id"]: row
        for row in validator._W5_EXPORTED_ABI["remaining_owned_obligations"]
    }
    if absent:
        entry = obligations["DEPENDENCY_REFRESH_ATTESTATION_ABSENT"]
        assert entry["typed_status"] == "NOT_PROVIDED_BY_W5_SOURCE_ABSENT"
        assert entry["owner_wave"] == "PM"
        assert "§9.2" in entry["spec_refs"]
        # 誠實邊界:第二半(過期 runtime/topology/prepare/auth 不得以引用刷新)**是**被證明的。
        assert "cannot be refreshed by reference" in entry["statement"]
    else:  # pragma: no cover - 一旦有人實作了它,義務必須被關閉而不是留著
        assert "DEPENDENCY_REFRESH_ATTESTATION_ABSENT" not in obligations


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
    assert entry["typed_status"] == "PARTIALLY_PROVIDED_BY_W4B"
    assert entry["owner_wave"] == "W6B"
    assert "BOTH halves W4 named are still open" in entry["statement"]
    assert "PERMIT_CLOCK_SKEW_SECONDS" in entry["statement"]
    assert _Path(ROOT).is_dir()
