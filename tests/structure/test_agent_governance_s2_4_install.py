"""S2.4(WP4)install 治理模組——W0 發射器 + W1(contracts/routing)收口的 focused 測試。

證明:
- 發射器產出的 receipt 是 evidence-only(無任何 caller status 鍵),
  ADMITTED/PASS 恆由中央 validator 從 repo 再導出;
- 成功發射時持久化物落盤,且 admission/wave-exit 均可獨立重驗;
- 任一導出非 ADMITTED/PASS 時 fail-closed:回 typed refusal 且「不」寫任何檔;
- 空 evidence 直接拒絕(不能以空殼 digest 佯裝證據);
- W1:三 route class 於 source lane 不注入任何 effect 節點(§4)+ FORWARD-only 表面一致性
  + probe/PREPARE 不得攜帶 APPLY 面(§10.5 #38);
- W1:Registry 三 adapter 身分 = §10.2 凍結 ABI,binding = AUTHORITY_LOCKED_PRODUCTION_CAPABLE;
- W1 wave-exit 中央導出:predecessor W0 鏈(連同 admission)必再導出 PASS/ADMITTED;偽造
  (自證 status / 竄改 predecessor / ABI-surface drift / adapter 身分替換 / v2→v1 降級 /
  非當前 HEAD)一律 NOT_PASS(§10.5 #3/#9/#27/#36);
- §9.1 replay 綁定謂詞:unconsumed 才可消費;consuming-twice / same-id-different-plan /
  斷鏈 / 過期 / 未生效 / 跨 profile / 錯信任根一律 AUTHORIZATION_REJECTED;有效簽章在
  source lane 恆帶 typed production_effect=EXTERNAL_VERIFICATION_PENDING(絕不 applied)。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_routing as routing  # noqa: E402
import agent_governance_s2_4_install as install  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402


_TEST_EVIDENCE = {
    "command": "python3 -m pytest tests/structure/test_s2_4_w0_admission.py -q",
    "exit_code": 0,
    "summary": "unit-test placeholder evidence for emitter behavior tests",
}
_REVIEW_PROVENANCE = [
    {"pr": 136, "merge_head": "f" * 40, "verdict": "test-fixture"},
]


def test_emitted_receipts_are_evidence_only_and_centrally_derivable(tmp_path) -> None:
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result["status"] == "W0_RECEIPTS_EMITTED"
    admission = json.loads(
        (tmp_path / install.W0_ADMISSION_FILENAME).read_text(encoding="utf-8")
    )
    wave_exit = json.loads(
        (tmp_path / install.W0_WAVE_EXIT_FILENAME).read_text(encoding="utf-8")
    )
    record = json.loads(
        (tmp_path / install.W0_DERIVATION_RECORD_FILENAME).read_text(encoding="utf-8")
    )
    # evidence-only:兩份 receipt 皆不含任何 caller-status 鍵
    for receipt in (admission, wave_exit):
        assert not any(key in receipt for key in validator._CALLER_STATUS_KEYS)
    # 中央再導出可獨立重驗
    assert validator.derive_source_admission_status(admission) == {
        "status": "ADMITTED",
        "reasons": [],
    }
    assert validator.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    ) == {"status": "PASS", "reasons": []}
    assert validator.validate_aiml_artifact(admission) == []
    assert validator.validate_aiml_artifact(wave_exit) == []
    # derivation record 綁定同一 head 與雙導出結果
    assert record["source_head"] == admission["source_head"]
    assert record["admission_derivation"]["status"] == "ADMITTED"
    assert record["wave_exit_derivation"]["status"] == "PASS"
    # 真實證據原樣持久化(digest 可重算)
    assert record["test_evidence"] == _TEST_EVIDENCE
    assert wave_exit["test_digests"] == [validator.canonical_digest(_TEST_EVIDENCE)]


# --------------------------------------------------------------------------- #
# W2 P2-I(E3):receipt 不得被靜默覆蓋;CLI --out 受限於 repo receipts 目錄
# --------------------------------------------------------------------------- #
def test_emit_refuses_to_silently_overwrite_existing_receipts(tmp_path) -> None:
    first = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert first["status"] == "W0_RECEIPTS_EMITTED"
    # derivation record 綁定 test_evidence 原文 → 覆蓋與否可逐位元組判別。
    target = tmp_path / install.W0_DERIVATION_RECORD_FILENAME
    sentinel = target.read_text(encoding="utf-8")
    # 第二次發射:任一目標已存在 → typed 拒絕且「零寫入」(既有 bytes 逐字不變)。
    second = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence={"command": "different", "exit_code": 0},
        review_provenance=[{"pr": 999, "verdict": "different"}],
    )
    assert second["status"] == "W0_EMIT_REFUSED"
    assert second["stage"] == "output_collision"
    assert any(install.W0_ADMISSION_FILENAME in reason for reason in second["reasons"])
    assert any(
        install.W0_DERIVATION_RECORD_FILENAME in reason for reason in second["reasons"]
    )
    assert target.read_text(encoding="utf-8") == sentinel
    # 顯式覆蓋才允許
    third = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence={"command": "explicit-overwrite", "exit_code": 0},
        review_provenance=[{"pr": 1000, "verdict": "explicit"}],
        allow_overwrite=True,
    )
    assert third["status"] == "W0_RECEIPTS_EMITTED"
    assert target.read_text(encoding="utf-8") != sentinel


def test_partial_collision_still_writes_nothing(tmp_path) -> None:
    """全有全無:只要有一個目標檔存在,其餘檔案也不得被建立。"""
    (tmp_path / install.W0_DERIVATION_RECORD_FILENAME).write_text("{}", encoding="utf-8")
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result["status"] == "W0_EMIT_REFUSED"
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        install.W0_DERIVATION_RECORD_FILENAME
    ]


def test_publication_failure_leaves_no_partial_receipt_set(tmp_path, monkeypatch) -> None:
    """P2-1:發佈途中失敗必須回滾整組——半套殘留會讓下一次重試把自己的殘骸當碰撞。

    修前:逐檔依序寫入,第二個檔案的 I/O 失敗就留下第一個檔案;重試時 collision 檢查
    看到它 → 拒絕 → 這條 lineage 再也發不出來(除非人手清理)。
    """
    import agent_governance_s2_4_emit_sink as sink

    real_link = os.link
    calls = {"count": 0}

    def _failing_link(source, target, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 2:  # 第二個 artifact 推上正位時裝置失敗
            raise OSError(28, "No space left on device")
        return real_link(source, target, *args, **kwargs)

    monkeypatch.setattr(sink.os, "link", _failing_link)
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result["status"] == "W0_EMIT_REFUSED"
    assert result["stage"] == "publication"
    assert any("rolled back" in reason for reason in result["reasons"])
    # 零殘留:既無 receipt、也無 staging/lock 檔
    assert sorted(p.name for p in tmp_path.iterdir()) == []
    # 復原:同一目錄下一次發射必須成功(不得把自己的殘骸看成碰撞)
    monkeypatch.setattr(sink.os, "link", real_link)
    recovered = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert recovered["status"] == "W0_RECEIPTS_EMITTED"
    assert (tmp_path / install.W0_ADMISSION_FILENAME).exists()


def test_concurrent_emitters_are_serialized_by_an_exclusive_publication_lock(
    tmp_path,
) -> None:
    """P2-1:分離的存在性檢查讓兩個並行發射器可以雙雙通過再交錯寫入。

    獨佔建立的 lock 檔把發佈邊界串行化:第二個發射器拿不到 lock 即 typed 拒絕,
    絕不與第一個交錯出兩條混合 lineage。
    """
    import agent_governance_s2_4_emit_sink as sink

    held = tmp_path / sink.PUBLICATION_LOCK_NAME
    held.write_text("31337\n", encoding="utf-8")  # 模擬另一個發射器持有中
    blocked = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert blocked["status"] == "W0_EMIT_REFUSED"
    assert blocked["stage"] == "publication_lock"
    assert sorted(p.name for p in tmp_path.iterdir()) == [sink.PUBLICATION_LOCK_NAME]
    held.unlink()
    released = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert released["status"] == "W0_RECEIPTS_EMITTED"
    # 發佈結束後 lock 必須被釋放(否則下一次發射永遠被自己擋住)
    assert not held.exists()


def test_cli_out_dir_is_constrained_to_the_repository_receipts_directory(
    tmp_path, capsys
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(_TEST_EVIDENCE), encoding="utf-8")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps(_REVIEW_PROVENANCE), encoding="utf-8")
    for action in ("w0-emit", "w1-emit", "w2-emit"):
        exit_code = install._main([
            action,
            "--out", str(tmp_path / "escaped"),
            "--test-evidence", str(evidence),
            "--review-provenance", str(provenance),
        ])
        assert exit_code == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["stage"] == "out_dir"
        assert "receipts" in payload["reasons"][0]
        assert not (tmp_path / "escaped").exists()
    # receipts 目錄內的路徑通過約束(不實際發射,只證解析)
    inside = install.RECEIPTS_ROOT / "S2.4-WP4-W2"
    assert install._resolve_cli_out_dir(inside) == inside.resolve()
    with pytest.raises(ValueError):
        install._resolve_cli_out_dir(install.RECEIPTS_ROOT.parent)


def test_emit_refuses_and_writes_nothing_when_admission_not_admitted(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validator,
        "derive_source_admission_status",
        lambda receipt, *, repo_root=None, now=None: {
            "status": "NOT_ADMITTED",
            "reasons": ["forced-for-fail-closed-branch"],
        },
    )
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result == {
        "status": "W0_EMIT_REFUSED",
        "stage": "source_admission",
        "reasons": ["forced-for-fail-closed-branch"],
    }
    assert list(tmp_path.iterdir()) == []


def test_emit_refuses_and_writes_nothing_when_wave_exit_not_pass(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        validator,
        "derive_wave_exit_status",
        lambda receipt, *, repo_root=None, now=None, source_admission_receipt=None: {
            "status": "NOT_PASS",
            "reasons": ["forced-for-fail-closed-branch"],
        },
    )
    result = install.emit_w0_receipts(
        out_dir=tmp_path,
        test_evidence=dict(_TEST_EVIDENCE),
        review_provenance=[dict(item) for item in _REVIEW_PROVENANCE],
    )
    assert result == {
        "status": "W0_EMIT_REFUSED",
        "stage": "wave_exit",
        "reasons": ["forced-for-fail-closed-branch"],
    }
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "test_evidence,review_provenance",
    [
        ({}, [{"pr": 1}]),
        (None, [{"pr": 1}]),
        ({"ok": 1}, []),
        ({"ok": 1}, [{}]),
        ({"ok": 1}, ["not-an-object"]),
    ],
)
def test_emit_rejects_empty_or_malformed_evidence(
    tmp_path, test_evidence, review_provenance
) -> None:
    with pytest.raises(ValueError):
        install.emit_w0_receipts(
            out_dir=tmp_path,
            test_evidence=test_evidence,
            review_provenance=review_provenance,
        )
    assert list(tmp_path.iterdir()) == []


def test_w0_owned_paths_cover_the_post_split_validator_family() -> None:
    """E2 P1-2 回歸:2000 行拆分後 W0 owned-path 綁定必須覆蓋 validator 全家族。

    否則對 leaf 模組或測試 sibling 的削弱性修改不會改變 wave-exit 的
    owned_path_diff_digest,治理不變量的覆蓋面被靜默收窄。
    """

    required = {
        "program_code/ml_training/aiml_gate_receipt_adoption.py",
        "program_code/ml_training/aiml_gate_receipt_classifiers.py",
        "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
        "program_code/ml_training/aiml_gate_receipt_schema_core.py",
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/aiml_gate_receipt_validator_testkit.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator_adoption.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py",
    }
    missing = required - set(validator._W0_OWNED_PATHS)
    assert not missing, f"W0 owned-path binding misses split family members: {sorted(missing)}"
    # 每一個 pinned 路徑都必須真實存在(防呆:改名/移動後 pin 變成死路徑)。
    dead = [p for p in validator._W0_OWNED_PATHS if not (ROOT / p).is_file()]
    assert not dead, f"W0 owned paths contain dead entries: {dead}"


# ═════════════════════════════ W1(contracts/routing)══════════════════════════
# ── 凍結 digest 恆等(硬約束:byte-identical)────────────────────────────────────
def test_w1_frozen_digests_are_byte_identical() -> None:
    assert validator.aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert validator.aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    assert validator.w0_negative_test_manifest_digest() == (
        "sha256:1bd86de7b636bf57ead1a1ecfd00c9b75379ae49d1458a41bd7c22987d6f92f6"
    )
    assert validator.s2_4_authorization_profiles_digest() == (
        "sha256:79b27b7040e8a8d3af84b6a5f0c7c20e45888caaedac146428145ffea54be2dc"
    )


# ── Registry:三 adapter 身分 = §10.2 凍結 ABI ─────────────────────────────────
_S2_4_ADAPTER_IDS = (
    "s2_4_capability_probe_adapter_v1",
    "s2_4_prepare_adapter_v1",
    "s2_4_install_adapter_v1",
)


def test_registry_declares_three_s2_4_adapters_authority_locked() -> None:
    registry = json.loads(
        (ROOT / ".codex/agent_registry_v1.json").read_text(encoding="utf-8")
    )
    adapters = registry["effect_adapters"]
    for adapter_id in _S2_4_ADAPTER_IDS:
        entry = adapters[adapter_id]
        # §10.2 binding 字串必須逐位元組正確(不是 "apply permanently disabled")。
        assert entry["status"] == "AUTHORITY_LOCKED_PRODUCTION_CAPABLE", adapter_id
        assert entry["owner_session"] == "S2.4"
        # invariant 必載明:reachable-but-authority-locked、fail-closed pending、effect-DAG
        # 位置、probe/PREPARE 不達 APPLY 面、九 authority false、EFFECT 前不注入節點。
        invariant = entry["invariant"]
        for needle in (
            "production reachable but authority-locked",
            "EXTERNAL_VERIFICATION_PENDING",
            "S2.0@EFFECT_DONE -> W6A PREPARE -> W6B APPLY",
            "nine authorities stay false",
            "no route_task effect node or closure effect binding is injected before the S2.4 EFFECT session",
        ):
            assert needle in invariant, (adapter_id, needle)
        # 綁定的 schema 路徑必須真實存在(fail-closed:改名/移動即紅)。
        for key, value in entry.items():
            if key.endswith("_schema_path"):
                assert (ROOT / value).is_file(), (adapter_id, key, value)
        # implementation_paths 必含 install 治理模組;§10.2 的凍結進入點所在的模組也必須在列
        # (CC DRIFT-3:`apply_s2_4_install_plan` 住在 `..._install_driver.py` 而 `install.py`
        # 並不 re-export 它,於是照著 operator 已核准的 adapter 紀錄找,找不到真正碰主機的碼)。
        assert (
            "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py"
            in entry["implementation_paths"]
        )
        for path in entry["implementation_paths"] + entry["component_paths"]:
            assert (ROOT / path).is_file(), (adapter_id, path)
        if adapter_id == "s2_4_install_adapter_v1":
            assert (
                "helper_scripts/maintenance_scripts/agent_governance_s2_4_install_driver.py"
                in entry["implementation_paths"]
            )
    # probe/PREPARE 明文「cannot reach」APPLY 面(§4/§10.5 #38)。
    for adapter_id in _S2_4_ADAPTER_IDS[:2]:
        assert "cannot reach any APPLY surface" in adapters[adapter_id]["invariant"]


# ── Routing:三 route class 於 source lane 不注入 effect 節點(§4)────────────────
def _probe_facts(**overrides):
    facts = {
        "task_shape": "audit",
        "surfaces": ["runtime_effect", "service"],
        "risk": "high",
        "uncertainty": "low",
        "runtime_claim": True,
        "end_to_end_claim": False,
        "side_effect_class": "s2_4_capability_probe_intent",
        "task_prompt": "S2.4 capability probe (source lane)",
        "dirty_scope": [],
        "claim_inputs": {},
    }
    facts.update(overrides)
    return facts


def _install_plan_facts(**overrides):
    base = {
        "side_effect_class": "s2_4_install_plan",
        "surfaces": ["runtime_effect", "service", "pg", "secret"],
        "risk": "critical",
    }
    base.update(overrides)
    return _probe_facts(**base)


@pytest.mark.parametrize("effect", [
    "s2_4_capability_probe_intent", "s2_4_prepare_intent", "s2_4_install_plan",
])
def test_s2_4_route_classes_inject_no_effect_node_in_source_lane(effect) -> None:
    facts = (
        _install_plan_facts() if effect == "s2_4_install_plan"
        else _probe_facts(side_effect_class=effect)
    )
    route = routing.route_task(facts)
    node_ids = [node["id"] for node in route["nodes"]]
    # §4:「No effect node is injected for an ordinary source or documentation task」。
    assert [n for n in route["nodes"] if n["kind"] == "effect_adapter"] == []
    for adapter_id in (
        routing.S2_4_CAPABILITY_PROBE_ADAPTER_ID,
        routing.S2_4_PREPARE_ADAPTER_ID,
        routing.S2_4_INSTALL_ADAPTER_ID,
    ):
        assert adapter_id not in node_ids
    # 同 observer/quiesce 姿態:走 ops_preflight -> ops_postcheck(中間無 effect adapter)。
    assert "ops_preflight" in node_ids and "ops_postcheck" in node_ids
    by_id = {node["id"]: node for node in route["nodes"]}
    assert by_id["ops_postcheck"]["requires"] == ["ops_preflight"]


def test_s2_4_routing_adapter_ids_match_registry_frozen_abi() -> None:
    assert routing.S2_4_CAPABILITY_PROBE_ADAPTER_ID == "s2_4_capability_probe_adapter_v1"
    assert routing.S2_4_PREPARE_ADAPTER_ID == "s2_4_prepare_adapter_v1"
    assert routing.S2_4_INSTALL_ADAPTER_ID == "s2_4_install_adapter_v1"


@pytest.mark.parametrize("effect", [
    "s2_4_capability_probe_intent", "s2_4_prepare_intent",
])
def test_probe_and_prepare_routes_reject_apply_surfaces_and_weak_facts(effect) -> None:
    # §10.5 #38:probe/PREPARE 請求攜帶 APPLY 面(pg/secret)於節點注入前即拒。
    for apply_surface in ("pg", "secret"):
        with pytest.raises(ValueError, match="must not carry APPLY surfaces"):
            routing.route_task(_probe_facts(
                side_effect_class=effect,
                surfaces=["runtime_effect", "service", apply_surface],
            ))
    # deploy 面由既有通用規則更早擋下(deploy surface requires side_effect_class=deploy);
    # 兩道閘任一皆在節點注入前 fail-closed。
    with pytest.raises(ValueError, match="deploy"):
        routing.route_task(_probe_facts(
            side_effect_class=effect,
            surfaces=["runtime_effect", "service", "deploy"],
        ))
    # FORWARD-only:弱 risk / 無 runtime_claim / 缺 runtime_effect+service 面皆拒。
    for bad in (
        {"risk": "low"},
        {"runtime_claim": False},
        {"surfaces": ["governance"]},
    ):
        with pytest.raises(ValueError):
            routing.route_task(_probe_facts(side_effect_class=effect, **bad))


def test_install_plan_route_requires_full_surfaces_and_critical_risk() -> None:
    for bad in (
        {"risk": "high"},                                     # §4:APPLY = critical
        {"runtime_claim": False},
        {"surfaces": ["runtime_effect", "service", "pg"]},    # 缺 secret
        {"surfaces": ["runtime_effect", "service", "secret"]},  # 缺 pg
    ):
        with pytest.raises(ValueError):
            routing.route_task(_install_plan_facts(**bad))


# ── W1 wave-exit 中央導出:happy path + 偽造負例(§10.5 #3/#27/#36)──────────────
_EVID = {
    "test_digests": ["sha256:" + "1" * 64],
    "capture_digests": ["sha256:" + "2" * 64],
    "review_fragment_digests": ["sha256:" + "3" * 64],
}


def _w1_chain():
    admission = install.build_w0_source_admission_receipt(ROOT)
    w0 = install.build_w0_wave_exit_receipt(admission, **deepcopy(_EVID))
    w1 = install.build_w1_wave_exit_receipt(admission, w0, **deepcopy(_EVID))
    return admission, w0, w1


def test_w1_wave_exit_derives_pass_with_full_predecessor_chain() -> None:
    admission, w0, w1 = _w1_chain()
    result = validator.derive_wave_exit_status(
        w1, source_admission_receipt=admission, predecessor_wave_receipt=w0
    )
    assert result == {"status": "PASS", "reasons": []}
    # evidence-only:無任何 caller-status 鍵;中央閘結構驗亦全過。
    assert not any(key in w1 for key in validator._CALLER_STATUS_KEYS)
    assert validator.validate_aiml_artifact(w1) == []


def test_w1_self_declared_status_rejected_before_derivation() -> None:
    # §10.5 #27:caller 自證 status 於 derivation 前即拒。
    admission, w0, w1 = _w1_chain()
    for field, value in (("status", "PASS"), ("pass", True), ("done", True)):
        forged = deepcopy(w1)
        forged[field] = value
        forged["self_digest"] = validator.artifact_self_digest(forged)
        result = validator.derive_wave_exit_status(
            forged, source_admission_receipt=admission, predecessor_wave_receipt=w0
        )
        assert result["status"] == "NOT_PASS"
        assert any("must not self-declare status" in r for r in result["reasons"])
        assert validator.validate_aiml_artifact(forged) != []


def test_w1_requires_predecessor_object_and_exact_digest_binding() -> None:
    admission, w0, w1 = _w1_chain()
    # 缺 predecessor 物件 → typed NOT_PASS(#27:鏈不能只靠 digest 自述)。
    result = validator.derive_wave_exit_status(w1, source_admission_receipt=admission)
    assert result["status"] == "NOT_PASS"
    assert any("requires the bound predecessor_wave_receipt" in r for r in result["reasons"])
    # 竄改 predecessor digest → 綁定失敗。
    forged = deepcopy(w1)
    forged["predecessor_wave_receipt_digest"] = "sha256:" + "0" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = validator.derive_wave_exit_status(
        forged, source_admission_receipt=admission, predecessor_wave_receipt=w0
    )
    assert result["status"] == "NOT_PASS"
    assert any(
        "predecessor_wave_receipt_digest does not bind" in r for r in result["reasons"]
    )
    # 竄改 predecessor 物件本身(W0 receipt 的 owned-path digest)→ W0 鏈斷 → W1 NOT_PASS。
    broken_w0 = deepcopy(w0)
    broken_w0["owned_path_diff_digest"] = validator.canonical_digest(["tampered"])
    broken_w0["self_digest"] = validator.artifact_self_digest(broken_w0)
    rebound = deepcopy(w1)
    rebound["predecessor_wave_receipt_digest"] = broken_w0["self_digest"]
    rebound["self_digest"] = validator.artifact_self_digest(rebound)
    result = validator.derive_wave_exit_status(
        rebound, source_admission_receipt=admission, predecessor_wave_receipt=broken_w0
    )
    assert result["status"] == "NOT_PASS"
    assert any("does not derive PASS" in r for r in result["reasons"])


def test_w1_tampered_admission_input_breaks_the_whole_chain() -> None:
    # #27:竄改 admission 輸入(negative-test manifest digest)→ ADMITTED 斷 → W0/W1 全斷。
    admission, w0, w1 = _w1_chain()
    forged_admission = deepcopy(admission)
    forged_admission["negative_tests_pass"] = validator.canonical_digest(["forged"])
    forged_admission["self_digest"] = validator.artifact_self_digest(forged_admission)
    result = validator.derive_wave_exit_status(
        w1, source_admission_receipt=forged_admission, predecessor_wave_receipt=w0
    )
    assert result["status"] == "NOT_PASS"
    assert any("does not derive ADMITTED" in r for r in result["reasons"])


def test_w1_abi_surface_drift_breaks_derivation(monkeypatch) -> None:
    # #3/#36:竄改 code-owned _W1_EXPORTED_ABI 投影輸入(route class 改名)→ ABI digest 漂移。
    admission, w0, w1 = _w1_chain()
    tampered = deepcopy(validator._W1_EXPORTED_ABI)
    tampered["route_classes"][2] = "s2_4_install_plan_RENAMED"
    monkeypatch.setattr(validator, "_W1_EXPORTED_ABI", tampered)
    result = validator.derive_wave_exit_status(
        w1, source_admission_receipt=admission, predecessor_wave_receipt=w0
    )
    assert result["status"] == "NOT_PASS"
    assert any(
        "exported_abi_digest does not re-derive" in r for r in result["reasons"]
    )


def test_w1_adapter_identity_substitution_breaks_derivation(monkeypatch) -> None:
    # #3:adapter 身分替換(registry 查無此 id → status None ≠ 凍結 binding 字串)→ 拒。
    admission, w0, w1 = _w1_chain()
    substituted = deepcopy(validator._W1_EXPORTED_ABI)
    substituted["adapter_ids"][2] = "s2_4_install_adapter_v2_SUBSTITUTED"
    monkeypatch.setattr(validator, "_W1_EXPORTED_ABI", substituted)
    result = validator.derive_wave_exit_status(
        w1, source_admission_receipt=admission, predecessor_wave_receipt=w0
    )
    assert result["status"] == "NOT_PASS"
    assert any(
        "registry status does not re-derive" in r for r in result["reasons"]
    )


def test_w1_v2_to_v1_classifier_downgrade_breaks_derivation(monkeypatch) -> None:
    # #3:v2→v1 降級——把 v2 矩陣 digest 換成 v1 的凍結 digest → ABI 投影漂移 → 拒。
    admission, w0, w1 = _w1_chain()
    monkeypatch.setattr(
        validator,
        "aiml_component_effect_class_matrix_v2_digest",
        validator.aiml_component_effect_class_matrix_digest,
    )
    result = validator.derive_wave_exit_status(
        w1, source_admission_receipt=admission, predecessor_wave_receipt=w0
    )
    assert result["status"] == "NOT_PASS"
    assert any(
        "exported_abi_digest does not re-derive" in r for r in result["reasons"]
    )


def test_w1_source_head_must_be_current_checkout_head() -> None:
    # #27:W1 receipt 宣稱另一世代(仍為合法 40-hex)→ 非當前 HEAD → 拒。
    admission, w0, w1 = _w1_chain()
    forged = deepcopy(w1)
    forged["source_head"] = "f" * 40
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = validator.derive_wave_exit_status(
        forged, source_admission_receipt=admission, predecessor_wave_receipt=w0
    )
    assert result["status"] == "NOT_PASS"
    assert any("not the current checkout HEAD" in r for r in result["reasons"])


def test_w1_owned_paths_exist_and_cover_the_w1_surfaces() -> None:
    dead = [p for p in validator._W1_OWNED_PATHS if not (ROOT / p).is_file()]
    assert not dead, f"W1 owned paths contain dead entries: {dead}"
    required = {
        ".codex/agent_registry_v1.json",
        "helper_scripts/maintenance_scripts/agent_governance_routing.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure.py",
        "helper_scripts/maintenance_scripts/agent_governance_component_effects.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
        "program_code/ml_training/aiml_gate_receipt_s2_4_contracts.py",
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "tests/structure/test_agent_governance_s2_4_install.py",
        "tests/structure/test_agent_governance_s2_4_install_integration.py",
    }
    missing = required - set(validator._W1_OWNED_PATHS)
    assert not missing, f"W1 owned-path binding misses: {sorted(missing)}"


# ── W2 wave-exit 中央導出:happy path + 偽造負例(§10.3 W2 row/§10.5 #27)────────
def _w2_chain():
    admission, w0, w1 = _w1_chain()
    w2 = install.build_w2_wave_exit_receipt(admission, w1, **deepcopy(_EVID))
    return admission, w0, w1, w2


def test_w2_wave_exit_derives_pass_with_full_predecessor_chain() -> None:
    admission, w0, w1, w2 = _w2_chain()
    result = validator.derive_wave_exit_status(
        w2,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    )
    assert result == {"status": "PASS", "reasons": []}
    assert not any(key in w2 for key in validator._CALLER_STATUS_KEYS)
    assert validator.validate_aiml_artifact(w2) == []


def test_w2_self_declared_status_rejected_before_derivation() -> None:
    admission, w0, w1, w2 = _w2_chain()
    forged = deepcopy(w2)
    forged["status"] = "PASS"
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = validator.derive_wave_exit_status(
        forged,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    )
    assert result["status"] == "NOT_PASS"
    assert any("must not self-declare status" in r for r in result["reasons"])


def test_w2_requires_predecessor_object_and_regenerated_w0_chain() -> None:
    admission, w0, w1, w2 = _w2_chain()
    # 缺 W1 predecessor 物件 → typed NOT_PASS。
    result = validator.derive_wave_exit_status(w2, source_admission_receipt=admission)
    assert result["status"] == "NOT_PASS"
    assert any("requires the bound predecessor_wave_receipt" in r for r in result["reasons"])
    # 缺 predecessor_wave_chain(W1 無法遞迴綁其 W0)→ typed NOT_PASS。
    result = validator.derive_wave_exit_status(
        w2, source_admission_receipt=admission, predecessor_wave_receipt=w1
    )
    assert result["status"] == "NOT_PASS"
    assert any("predecessor_wave_chain" in r for r in result["reasons"])
    # W0/W1 wave 不消費 chain(fail-closed 拒非空 chain,杜絕誤信多綁前導)。
    _admission, w0_only, w1_only = _w1_chain()
    result = validator.derive_wave_exit_status(
        w1_only,
        source_admission_receipt=_admission,
        predecessor_wave_receipt=w0_only,
        predecessor_wave_chain=(w0_only,),
    )
    assert result["status"] == "NOT_PASS"
    assert any("does not accept a predecessor_wave_chain" in r for r in result["reasons"])


def test_w2_tampered_w1_predecessor_breaks_derivation() -> None:
    # (g) 功能探針負例:竄改 W1(owned-path digest)→ W1 鏈斷 → W2 NOT_PASS。
    admission, w0, w1, _w2 = _w2_chain()
    broken_w1 = deepcopy(w1)
    broken_w1["owned_path_diff_digest"] = validator.canonical_digest(["tampered"])
    broken_w1["self_digest"] = validator.artifact_self_digest(broken_w1)
    rebound = install.build_w2_wave_exit_receipt(admission, broken_w1, **deepcopy(_EVID))
    result = validator.derive_wave_exit_status(
        rebound,
        source_admission_receipt=admission,
        predecessor_wave_receipt=broken_w1,
        predecessor_wave_chain=(w0,),
    )
    assert result["status"] == "NOT_PASS"
    assert any("does not derive PASS" in r for r in result["reasons"])
    # 竄改 predecessor digest 綁定 → NOT_PASS。
    forged = deepcopy(_w2)
    forged["predecessor_wave_receipt_digest"] = "sha256:" + "0" * 64
    forged["self_digest"] = validator.artifact_self_digest(forged)
    result = validator.derive_wave_exit_status(
        forged,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    )
    assert result["status"] == "NOT_PASS"
    assert any(
        "predecessor_wave_receipt_digest does not bind" in r for r in result["reasons"]
    )


def test_w2_abi_folds_live_split_and_closure_verdicts(monkeypatch) -> None:
    # §10.3 W2 exit:privilege-split / application-closure 兩個活裁決折進 exported-ABI——
    # 任一被降為非 PASS(模擬源碼回歸)→ 投影變值 + 顯式 reason → W2 導出失敗。
    admission, w0, w1, w2 = _w2_chain()
    monkeypatch.setattr(
        install,
        "derive_engine_scanner_privilege_split",
        lambda repo_root=None, **kwargs: {
            "status": "ENGINE_SCANNER_PRIVILEGE_SPLIT_REQUIRED",
            "manifest_digest": None,
        },
    )
    result = validator.derive_wave_exit_status(
        w2,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    )
    assert result["status"] == "NOT_PASS"
    assert any(
        "engine-scanner privilege-split does not re-derive PASS" in r
        for r in result["reasons"]
    )


def test_w2_unit_template_drift_breaks_derivation(monkeypatch) -> None:
    # template 檔漂移(≠ code-owned 渲染形狀)→ unit_template_matches_renderer=False → 拒。
    import agent_governance_s2_4_render as render

    admission, w0, w1, w2 = _w2_chain()
    monkeypatch.setattr(
        render, "unit_template_text", lambda: "[Service]\nExecStart=/bin/sh\n"
    )
    result = validator.derive_wave_exit_status(
        w2,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    )
    assert result["status"] == "NOT_PASS"
    assert any("unit template" in r for r in result["reasons"])


def test_w2_owned_paths_exist_and_cover_the_w2_surfaces() -> None:
    dead = [p for p in validator._W2_OWNED_PATHS if not (ROOT / p).is_file()]
    assert not dead, f"W2 owned paths contain dead entries: {dead}"
    required = {
        "helper_scripts/deploy/arcane-equilibrium-aiml-engine-scanner.service.template",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_install.py",
        "helper_scripts/maintenance_scripts/agent_governance_s2_4_render.py",
        "program_code/ml_training/aiml_gate_receipt_wave_w2.py",
        "program_code/ml_training/alr_event_consumer.py",
        "program_code/ml_training/application_bundle_runtime_closure_v1.json",
        "program_code/ml_training/pg_acl_manifest_v1.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/base_runtime_tree_manifest_v1.schema.json",
        "program_code/ml_training/schemas/aiml_gate_receipts/launch_bundle_manifest_v1.schema.json",
        "tests/structure/test_agent_governance_s2_4_install_render.py",
        # F1 的真驅動證據面(hermetic fixture 不能自證 psycopg2 的連線期外形)。
        "tests/structure/test_agent_governance_s2_4_consumer_resilience_disposable.py",
    }
    missing = required - set(validator._W2_OWNED_PATHS)
    assert not missing, f"W2 owned-path binding misses: {sorted(missing)}"


# ── §9.1 replay 綁定謂詞(驗證層消費語義;§10.5 #9/#36)─────────────────────────
_AUTH_ISSUED = "2026-07-24T00:00:00+00:00"
_AUTH_EXPIRES = "2026-07-24T00:10:00+00:00"
_AUTH_NOW = "2026-07-24T00:05:00+00:00"
_SIGN_SEQ = [0]


def _mint_ed25519_key(tmp_path, name):
    private_key = tmp_path / name
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
        check=True,
    )
    parts = private_key.with_suffix(".pub").read_text(encoding="ascii").split()
    public_key = " ".join(parts[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    return private_key, public_key, fingerprint


def _install_pinned_key(monkeypatch, public_key, fingerprint) -> None:
    # monkeypatch facade 的信任根副本(非 trusted-host 模組本身);驗簽基元不被 patch。
    monkeypatch.setattr(validator, "S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY", public_key)
    monkeypatch.setattr(validator, "S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT", fingerprint)


def _payload_binding(profile_key="apply_aggregate", **overrides):
    """W4a:profile 的 exact payload_binding(§9.1 payload 減去自指的 authorization_id)。"""

    import hashlib

    profile = validator.S2_4_AUTHORIZATION_PROFILES[profile_key]
    plan_core_digest = overrides.pop(
        "plan_core_digest", "sha256:" + hashlib.sha256(b"w1-plan-core").hexdigest()
    )
    plan_id = "s2-4-" + plan_core_digest.split(":", 1)[1]
    binding = {}
    for field in validator.authorization_payload_binding_fields(profile_key):
        if field == "domain":
            binding[field] = profile["signature_namespace"]
        elif field == "issued_at":
            binding[field] = _AUTH_ISSUED
        elif field == "expires_at":
            binding[field] = _AUTH_EXPIRES
        elif field == "output_derived_unit_digest_or_null":
            binding[field] = None
        elif field == "plan_core_digest":
            binding[field] = plan_core_digest
        elif field in {"plan_id", "idempotency_key"}:
            binding[field] = plan_id
        elif field == "source_head":
            binding[field] = "0" * 40
        elif field == "target_host":
            binding[field] = "trade-core"
        elif field == "scope":
            binding[field] = "PREPARE_SANDBOX"
        else:
            binding[field] = "sha256:" + hashlib.sha256(field.encode("utf-8")).hexdigest()
    binding.update(overrides)
    return binding


def _signed_authorization(private_key, profile_key="apply_aggregate", **overrides):
    profile = validator.S2_4_AUTHORIZATION_PROFILES[profile_key]
    binding = overrides.pop("payload_binding", None) or _payload_binding(profile_key)
    artifact = {
        "schema_version": "s2_4_operator_authorization_v1",
        "profile_identity": profile["profile_identity"],
        "signature_namespace": profile["signature_namespace"],
        "authorization_id": "",
        "payload_fields": list(profile["payload_fields"]),
        "payload_binding": binding,
        "issued_at": _AUTH_ISSUED,
        "expires_at": _AUTH_EXPIRES,
        "sshsig_armored": "-----BEGIN SSH SIGNATURE-----\nAAAA\n-----END SSH SIGNATURE-----\n",
        "self_digest": "sha256:" + "0" * 64,
    }
    # W4a §9.1:authorization_id 由 payload 導出(overrides 可顯式覆蓋以測負向)。
    artifact["authorization_id"] = validator.derive_authorization_id(artifact)
    artifact.update(overrides)
    signed = validator._s2_4_operator_authorization_signed_bytes(artifact)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"replay-auth-{_SIGN_SEQ[0]}.bin"
    message.write_bytes(signed)
    subprocess.run(
        [
            "ssh-keygen", "-Y", "sign", "-f", str(private_key),
            "-n", artifact["signature_namespace"], str(message),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    artifact["sshsig_armored"] = message.with_name(message.name + ".sig").read_text(
        encoding="ascii"
    )
    artifact["self_digest"] = validator.artifact_self_digest(artifact)
    return artifact


def _ledger(entries_spec):
    """entries_spec: [(authorization_id, authorization_digest, profile_identity), ...] → 鏈完整 ledger。"""

    entries = []
    previous = None
    for index, (auth_id, auth_digest, profile_identity) in enumerate(entries_spec):
        entry = {
            "seq": index,
            "prev_entry_digest": previous,
            "authorization_id": auth_id,
            "authorization_digest": auth_digest,
            "profile_identity": profile_identity,
            "consumed_at": _AUTH_ISSUED,
            "fsynced": True,
        }
        entry["entry_digest"] = validator.canonical_digest(entry)
        previous = entry["entry_digest"]
        entries.append(entry)
    ledger = {
        "schema_version": "s2_4_authorization_replay_ledger_v1",
        "ledger_path": (
            "/var/lib/arcane-equilibrium/aiml/install/s2_4/authorization-replay-ledger.json"
        ),
        "entries": entries,
        "append_only": True,
        "self_digest": "sha256:" + "0" * 64,
    }
    ledger["self_digest"] = validator.artifact_self_digest(ledger)
    return ledger


_OTHER = ("sha256:" + "b" * 64, "sha256:" + "c" * 64, "aiml-s2-install-operator-v1")


def test_replay_binding_unconsumed_valid_is_typed_and_never_production(
    tmp_path, monkeypatch
) -> None:
    private_key, public_key, fingerprint = _mint_ed25519_key(tmp_path, "operator")
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    auth = _signed_authorization(private_key)
    ledger = _ledger([_OTHER])  # 無此授權的消費 entry → 未消費
    verdict = validator.derive_authorization_replay_binding(auth, ledger, now=_AUTH_NOW)
    assert verdict["status"] == "UNCONSUMED_AUTHORIZATION_VALID"
    assert verdict["reasons"] == []
    # 有效簽章在 source lane 絕不產生 applied/production:typed 恆值。
    assert verdict["production_effect"] == "EXTERNAL_VERIFICATION_PENDING"


def test_replay_binding_rejects_consuming_twice_and_duplicates(
    tmp_path, monkeypatch
) -> None:
    private_key, public_key, fingerprint = _mint_ed25519_key(tmp_path, "operator")
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    auth = _signed_authorization(private_key)
    consumed = (auth["authorization_id"], auth["self_digest"], auth["profile_identity"])
    # (a) 已消費一次 → 再消費即拒(consuming twice)。
    verdict = validator.derive_authorization_replay_binding(
        auth, _ledger([consumed]), now=_AUTH_NOW
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("already consumed" in r for r in verdict["reasons"])
    # (b) ledger 內同 id 重複兩筆 → 拒。
    verdict = validator.derive_authorization_replay_binding(
        auth, _ledger([consumed, consumed]), now=_AUTH_NOW
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("duplicated consumption" in r for r in verdict["reasons"])


def test_replay_binding_rejects_same_id_different_plan(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_ed25519_key(tmp_path, "operator")
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    auth = _signed_authorization(private_key)
    # 同 replay id 但綁到「不同」授權/plan(authorization_digest ≠ 本授權 self_digest)→ 拒。
    hijacked = (auth["authorization_id"], "sha256:" + "d" * 64, auth["profile_identity"])
    verdict = validator.derive_authorization_replay_binding(
        auth, _ledger([hijacked]), now=_AUTH_NOW
    )
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("DIFFERENT authorization/plan" in r for r in verdict["reasons"])


def test_replay_binding_rejects_broken_or_reordered_chain(tmp_path, monkeypatch) -> None:
    private_key, public_key, fingerprint = _mint_ed25519_key(tmp_path, "operator")
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    auth = _signed_authorization(private_key)
    ledger = _ledger([_OTHER, _OTHER])
    # 亂序:互換兩 entry(seq/prev 雙斷)→ 拒。
    reordered = deepcopy(ledger)
    reordered["entries"] = [reordered["entries"][1], reordered["entries"][0]]
    reordered["self_digest"] = validator.artifact_self_digest(reordered)
    verdict = validator.derive_authorization_replay_binding(auth, reordered, now=_AUTH_NOW)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    # 竄改 entry 內容而不重算 entry_digest → 拒。
    tampered = deepcopy(ledger)
    tampered["entries"][0]["authorization_id"] = "sha256:" + "e" * 64
    tampered["self_digest"] = validator.artifact_self_digest(tampered)
    verdict = validator.derive_authorization_replay_binding(auth, tampered, now=_AUTH_NOW)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("entry_digest does not re-derive" in r for r in verdict["reasons"])


def test_replay_binding_rejects_expired_and_not_yet_valid(tmp_path, monkeypatch) -> None:
    # §9:過期(now > expires+skew)與未生效(now < issued-skew)授權皆拒。
    private_key, public_key, fingerprint = _mint_ed25519_key(tmp_path, "operator")
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    auth = _signed_authorization(private_key)
    ledger = _ledger([_OTHER])
    for stale_now in ("2026-07-24T00:12:00+00:00", "2026-07-23T23:57:00+00:00"):
        verdict = validator.derive_authorization_replay_binding(auth, ledger, now=stale_now)
        assert verdict["status"] == "AUTHORIZATION_REJECTED", stale_now
        assert any("freshness window" in r for r in verdict["reasons"])
    # TTL > profile 上限(§9 不等式的 ceiling 邊)亦拒。
    over_ttl = _signed_authorization(
        private_key, expires_at="2026-07-24T00:16:00+00:00"
    )
    verdict = validator.derive_authorization_replay_binding(over_ttl, ledger, now=_AUTH_NOW)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("TTL exceeds the profile ceiling" in r for r in verdict["reasons"])


def test_replay_binding_rejects_cross_profile_and_wrong_trust_root(
    tmp_path, monkeypatch
) -> None:
    private_key, public_key, fingerprint = _mint_ed25519_key(tmp_path, "operator")
    ledger = _ledger([_OTHER])
    # (a) 錯信任根:丟棄式鑰簽章但「不」改 pinned 根 → 簽章對 pinned 公鑰驗證失敗 → 拒(#9)。
    forged = _signed_authorization(private_key)
    verdict = validator.derive_authorization_replay_binding(forged, ledger, now=_AUTH_NOW)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("SSH signature is invalid" in r for r in verdict["reasons"])
    # (b) 跨 profile namespace/identity 替換:probe payload+簽章冒充 APPLY profile → 拒(#36)。
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    probe_auth = _signed_authorization(private_key, profile_key="capability_probe")
    hijack = deepcopy(probe_auth)
    hijack["profile_identity"] = "aiml-s2-install-operator-v1"
    hijack["signature_namespace"] = "arcane-equilibrium-aiml-s2-install"
    hijack["self_digest"] = validator.artifact_self_digest(hijack)
    verdict = validator.derive_authorization_replay_binding(hijack, ledger, now=_AUTH_NOW)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("payload_fields do not match" in r for r in verdict["reasons"])
    assert any("SSH signature is invalid" in r for r in verdict["reasons"])


def test_replay_binding_defaults_to_wall_clock_and_rejects_expired(
    tmp_path, monkeypatch
) -> None:
    """E2 P2-1/E3 P2-2 回歸:now 省略時默認真實 wall clock(fail-closed)。

    fixture 授權窗固定在 2026-07-24(單調地永遠過期);caller 忘傳 now 不得換得 VALID。
    """

    private_key, public_key, fingerprint = _mint_ed25519_key(tmp_path, "operator")
    _install_pinned_key(monkeypatch, public_key, fingerprint)
    auth = _signed_authorization(private_key)
    ledger = _ledger([_OTHER])
    verdict = validator.derive_authorization_replay_binding(auth, ledger)
    assert verdict["status"] == "AUTHORIZATION_REJECTED"
    assert any("freshness" in reason for reason in verdict["reasons"])
    assert verdict["production_effect"] == "EXTERNAL_VERIFICATION_PENDING"


def test_emitters_refuse_secret_like_evidence(tmp_path) -> None:
    """E3 P2-4 回歸:persisted evidence 含 secret-like 內容即拒發射且不落任何檔。"""

    poisoned = {
        "command": "pytest -q",
        "exit_code": 0,
        "leak": "ghp_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    }
    with pytest.raises(ValueError, match="secret-like"):
        install.emit_w0_receipts(
            out_dir=tmp_path,
            test_evidence=poisoned,
            review_provenance=[{"pr": 1, "verdict": "x"}],
        )
    assert list(tmp_path.iterdir()) == []


# ── D1/D2:consumer 側兩個 code-owned 契約必須 receipt-bound ─────────────────────
def _resilience_module():
    from ml_training import alr_consumer_resilience

    return alr_consumer_resilience


def test_w2_exported_abi_binds_the_cluster_identity_column_contract() -> None:
    """D1:身分列的封閉欄位契約折入 exported ABI(該關聯的 migration 屬 W6B)。

    修前:``CLUSTER_IDENTITY_COLUMNS`` 與 ``cluster_identity_row_digest`` 單方面定義了
    一個別人擁有的關聯——W6B 改名/換序不會弄破任何 W2 receipt,卻讓每次重連的
    row-digest 比對永久失敗(exit 78)。折入後 drift 在 receipt 面就看得見。
    """
    resilience = _resilience_module()
    projection = validator.w2_exported_abi_projection()
    assert projection["cluster_identity_relation_name"] == (
        resilience.CLUSTER_IDENTITY_RELATION
    )
    assert projection["cluster_identity_columns_digest"] == validator.canonical_digest(
        list(resilience.CLUSTER_IDENTITY_COLUMNS)
    )
    assert projection["consumer_liveness_contract_digest"] == validator.canonical_digest(
        resilience.derive_consumer_liveness_contract()
    )


def test_w2_receipt_breaks_when_the_identity_column_contract_drifts(monkeypatch) -> None:
    """W6B 換一個欄位序/欄位名 → W2 wave-exit 立刻 NOT_PASS(不再靜默)。"""
    admission, w0, w1, w2 = _w2_chain()
    resilience = _resilience_module()
    drifted = tuple(reversed(resilience.CLUSTER_IDENTITY_COLUMNS))
    monkeypatch.setattr(resilience, "CLUSTER_IDENTITY_COLUMNS", drifted)
    result = validator.derive_wave_exit_status(
        w2,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    )
    assert result["status"] == "NOT_PASS"
    assert any("exported_abi_digest does not re-derive" in r for r in result["reasons"])


def test_w2_receipt_breaks_when_the_liveness_contract_drifts(monkeypatch) -> None:
    """D2:staleness 門檻/信號面漂移同樣必須弄破 W2 導出。"""
    admission, w0, w1, w2 = _w2_chain()
    resilience = _resilience_module()
    monkeypatch.setattr(
        resilience,
        "derive_consumer_liveness_contract",
        lambda: {"schema_version": "alr_consumer_liveness_contract_v1"},
    )
    result = validator.derive_wave_exit_status(
        w2,
        source_admission_receipt=admission,
        predecessor_wave_receipt=w1,
        predecessor_wave_chain=(w0,),
    )
    assert result["status"] == "NOT_PASS"
    assert any("exported_abi_digest does not re-derive" in r for r in result["reasons"])


def test_w2_structural_errors_flag_an_unresolvable_consumer_contract(monkeypatch) -> None:
    """fail-closed:契約導不出來(import 壞掉)時投影記 None 且顯式列 reason。"""
    import aiml_gate_receipt_wave_w2 as wave_w2

    admission, w0, w1, w2 = _w2_chain()
    real_projection = wave_w2.w2_exported_abi_projection

    def broken_projection(repo_root=wave_w2.REPO_ROOT):
        broken = dict(real_projection(repo_root))
        broken["cluster_identity_columns_digest"] = None
        broken["consumer_liveness_contract_digest"] = None
        return broken

    monkeypatch.setattr(wave_w2, "w2_exported_abi_projection", broken_projection)
    reasons = wave_w2.w2_structural_errors(w2)
    assert any("cluster-identity column contract" in r for r in reasons)
    assert any("liveness/staleness contract" in r for r in reasons)
