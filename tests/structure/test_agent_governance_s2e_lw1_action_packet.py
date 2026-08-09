from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts" / "maintenance_scripts"
ML_ROOT = ROOT / "program_code" / "ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_s2e_lw1_action_packet as action  # noqa: E402
import agent_governance_s2_5_recovery as recovery  # noqa: E402
import aiml_gate_receipt_s2_5_host_capture as host_capture  # noqa: E402
import aiml_gate_receipt_s2e_external_evidence as external  # noqa: E402
import aiml_gate_receipt_s2e_launch as launch  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "S2E LW1 Test")
    _git(repo, "config", "user.email", "s2e-lw1@example.invalid")
    (repo / "checkpoint.txt").write_text("LW1\n", encoding="ascii")
    _git(repo, "add", "checkpoint.txt")
    _git(repo, "commit", "-qm", "LW1 checkpoint")
    return repo


def _inventory(*, ready: bool = False) -> dict:
    path_status = "READY" if ready else "ABSENT"
    service_status = "READY" if ready else "NOT_CONFIGURED"
    return {
        "schema_version": action.INVENTORY_SCHEMA_VERSION,
        "host": "trade-core",
        "observed_at": "2026-08-02T03:54:12Z",
        "evidence_class": "UNAUTHENTICATED_READ_ONLY_OBSERVATION",
        "linux_source_head": "8" * 40,
        "linux_worktree_clean": True,
        "fixed_path_statuses": {
            path: path_status for path in action.EXPECTED_PATHS
        },
        "service_statuses": {
            item_id: service_status for item_id in action.EXPECTED_SERVICE_IDS
        },
        "runtime_units": [
            {
                "unit": "arcane-equilibrium-aiml-engine-scanner.service",
                "load_state": "not-found",
                "active_state": "inactive",
                "sub_state": "dead",
            },
            {
                "unit": "openclaw-learning.service",
                "load_state": "not-found",
                "active_state": "inactive",
                "sub_state": "dead",
            },
        ],
        "canonical_roots": [
            {"path": "/opt/arcane-equilibrium/aiml", "status": "ABSENT"},
            {"path": "/var/lib/arcane-equilibrium/aiml", "status": "ABSENT"},
        ],
    }


def test_code_owned_prerequisite_paths_equal_live_fixed_root_constants() -> None:
    expected = {
        str(launch.S2E_RECEIPT_TRUST_ROOT_PATH),
        str(external.DURABILITY_ANCHOR_TRUST_ROOT_PATH),
        str(external.OFFHOST_REPLICA_TRUST_ROOT_PATH),
        str(external.PREDECESSOR_REGISTRY_TRUST_ROOT_PATH),
        str(host_capture.RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        host_capture.HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH,
        str(recovery.RECOVERY_AUTHORIZATION_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_ANCHOR_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_ANCHOR_READBACK_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_CONSUMPTION_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        str(recovery.RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
    }
    assert set(action.EXPECTED_PATHS) == expected
    assert len(action.EXPECTED_PATHS) == 12


def test_required_actions_are_derived_from_the_bound_checkout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """必做清單必須恆等於 bound checkout 的事實,兩個方向都要成立。

    第一版修法把 `COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR` 從清單全域刪除。
    那治好了「已完成卻仍要求」,卻造出反向錯誤:在 witness 尚未存在的 checkpoint 上
    重建 packet 會漏掉一個當時真正必要的步驟,而且照樣通過驗證(PR #180 Codex P1)。
    本測試同時釘住兩個方向,對全域刪除的版本為紅。
    """

    repo = _repo(tmp_path)
    witness = "witness-floor.json"
    action_id = "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR"
    monkeypatch.setitem(action.REPOSITORY_COMPLETION_WITNESSES, action_id, witness)

    before = _git(repo, "rev-parse", "HEAD")
    assert action.completed_action_ids(repo, at_commit=before) == ()
    # 這一句刻意不拿 `CANONICAL_ACTION_IDS` 當右手邊:目錄本身若被縮短,自我比對會
    # 一起縮短而毫無鑑別力(E4 實測「全域刪除」變體時,本檔前五句斷言全部照樣通過)。
    assert "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR" in action.required_action_ids(
        repo, at_commit=before
    ), "witness 不存在時,該步驟仍是 operator 必做的一步"
    assert action.required_action_ids(repo, at_commit=before) == (
        action.CANONICAL_ACTION_IDS
    )

    (repo / witness).write_text("{}\n", encoding="ascii")
    _git(repo, "add", witness)
    _git(repo, "commit", "-qm", "commit the witness")
    after = _git(repo, "rev-parse", "HEAD")

    assert action.completed_action_ids(repo, at_commit=after) == (action_id,)
    derived = action.required_action_ids(repo, at_commit=after)
    assert action_id not in derived
    assert derived == tuple(
        item for item in action.CANONICAL_ACTION_IDS if item != action_id
    ), "移除一項不得改動其餘項的順序"
    # 同一個 repo、同一支 validator,兩個 head 給出兩個答案——這正是「清單綁 checkout」
    # 與「清單是靜態常數」的可測差別。
    assert action.required_action_ids(repo, at_commit=before) != derived


def test_committed_repository_action_is_absent_from_the_live_catalogue_projection(
    tmp_path: Path,
) -> None:
    """在 current HEAD 上,已 commit 的 floor 必須讓該步驟從必做清單消失。"""

    action_id = "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR"
    witness = action.REPOSITORY_COMPLETION_WITNESSES[action_id]
    # witness 必須是 HEAD 上真的被追蹤的檔,不能是本地未追蹤產物——否則這條護欄
    # 會被一個沒進版本控制的檔案誤觸發或誤放行。
    assert _git(ROOT, "ls-files", "--error-unmatch", witness) == witness

    head = _git(ROOT, "rev-parse", "HEAD")
    assert action_id in action.completed_action_ids(ROOT, at_commit=head)
    assert action_id not in action.required_action_ids(ROOT, at_commit=head)


def test_validator_derives_at_the_packets_bound_head_not_at_repo_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validator 必須在 packet 綁定的 head 重算,不是在 `repo_root` 的 HEAD。

    這是本次改動最承重的一句話,而它原本**沒有任何測試**(E4 突變 M3 存活):
    套件裡每一份被驗的 packet 都剛好綁在「導出清單與 current HEAD 相同」的 head 上,
    於是把 validator 改成在 repo HEAD 導出也全綠。這裡讓兩個 head 的答案真的分歧。
    """

    repo = _repo(tmp_path)
    witness = "witness-floor.json"
    action_id = "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR"
    monkeypatch.setitem(action.REPOSITORY_COMPLETION_WITNESSES, action_id, witness)

    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    assert action_id in packet["required_action_ids"]

    # repo 前進到 witness 已 commit 的 head;packet 仍綁在它自己的舊 head 上。
    (repo / witness).write_text("{}\n", encoding="ascii")
    _git(repo, "add", witness)
    _git(repo, "commit", "-qm", "commit the witness")
    assert action.required_action_ids(
        repo, at_commit=_git(repo, "rev-parse", "HEAD")
    ) != tuple(packet["required_action_ids"]), "兩個 head 必須真的分歧,否則本測試無鑑別力"

    assert action.validate_s2e_lw1_operator_action_packet(packet, repo_root=repo) == []


def test_validator_rejects_a_reordered_action_sequence(tmp_path: Path) -> None:
    """內容相同但順序被換過的清單必須被拒——目錄是**有序**的。"""

    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    actions = packet["required_action_ids"]
    actions[0], actions[1] = actions[1], actions[0]
    packet["packet_digest"] = action.packet_digest(packet)
    errors = action.validate_s2e_lw1_operator_action_packet(packet, repo_root=repo)
    assert any("action sequence differs" in error for error in errors), errors


@pytest.mark.parametrize(
    "mutate,expected",
    (
        (lambda ids: [*ids[:-1], ids[0]], "not unique"),
        (lambda ids: [*ids[:-1], "PROVISION_SOMETHING_THAT_DOES_NOT_EXIST"], "outside enum"),
        (lambda ids: [], "shorter than minItems"),
        (lambda ids: [*ids, "PROVISION_SOMETHING_THAT_DOES_NOT_EXIST"], "longer than maxItems"),
    ),
)
def test_schema_still_bounds_the_action_array_after_const_was_replaced(
    tmp_path: Path,
    mutate,
    expected: str,
) -> None:
    """`const` 換成 enum 陣列後,schema 層仍必須擋住四種形狀退化。

    逐項相等已移到 code-owned validator,但 schema 不能因此變成擺設:成員、唯一性
    與長度上下界都要照樣執法,否則這次改動就是淨放寬。
    """

    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    packet["required_action_ids"] = mutate(packet["required_action_ids"])
    packet["packet_digest"] = action.packet_digest(packet)
    errors = action.validate_s2e_lw1_operator_action_packet(packet, repo_root=repo)
    assert any(expected in error for error in errors), errors


def test_completion_probe_is_independent_of_the_repo_root_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """把 `--repo-root` 指到子目錄不得改變導出結果(E2 P2-1)。

    `ls-tree` 的 pathspec 預設相對於 `-C` 的 prefix,而同函式的 `rev-parse` 不是。
    少了 `--full-tree`,子目錄下 witness 查不到 ⇒ 清單多一項 ⇒ 那份已腐化的 8 項
    packet 反而通過驗證,恰好復活本次改動要消滅的缺陷。
    """

    repo = _repo(tmp_path)
    witness = "nested/witness-floor.json"
    action_id = "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR"
    monkeypatch.setitem(action.REPOSITORY_COMPLETION_WITNESSES, action_id, witness)
    (repo / "nested").mkdir()
    (repo / witness).write_text("{}\n", encoding="ascii")
    _git(repo, "add", witness)
    _git(repo, "commit", "-qm", "commit the witness")
    head = _git(repo, "rev-parse", "HEAD")

    from_top = action.required_action_ids(repo, at_commit=head)
    assert action_id not in from_top
    for subdirectory in ("nested", "."):
        assert action.required_action_ids(
            repo / subdirectory, at_commit=head
        ) == from_top, f"repo_root={subdirectory} 改變了導出結果"


def test_completion_probe_does_not_accept_a_tree_as_a_witness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """witness 必須是 blob;同名目錄不得被當成「該步驟已完成」(E2 P3-1)。"""

    repo = _repo(tmp_path)
    action_id = "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR"
    monkeypatch.setitem(action.REPOSITORY_COMPLETION_WITNESSES, action_id, "nested")
    (repo / "nested").mkdir()
    (repo / "nested" / "unrelated.txt").write_text("x\n", encoding="ascii")
    _git(repo, "add", "nested/unrelated.txt")
    _git(repo, "commit", "-qm", "commit a directory at the witness path")

    head = _git(repo, "rev-parse", "HEAD")
    assert action.completed_action_ids(repo, at_commit=head) == ()
    assert action_id in action.required_action_ids(repo, at_commit=head)


def test_completion_probe_rejects_a_non_hex_commit(tmp_path: Path) -> None:
    """`at_commit` 在 validate 路徑上來自受檢 packet,進 git 前必須先驗形狀。"""

    repo = _repo(tmp_path)
    with pytest.raises(ValueError, match="40-hex commit"):
        action.completed_action_ids(repo, at_commit="--output=/tmp/pwned")


def test_build_refuses_when_the_checkpoint_completes_every_action(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """全部動作都已完成時不得再發 blocked packet。"""

    repo = _repo(tmp_path)
    monkeypatch.setattr(
        action,
        "REPOSITORY_COMPLETION_WITNESSES",
        {action_id: "checkpoint.txt" for action_id in action.CANONICAL_ACTION_IDS},
    )
    with pytest.raises(ValueError, match="already completes every LW1 operator action"):
        action.build_s2e_lw1_operator_action_packet(
            repo_root=repo,
            inventory=_inventory(),
        )


def test_absent_external_prerequisites_build_closed_blocked_packet(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    assert action.validate_s2e_lw1_operator_action_packet(
        packet, repo_root=repo
    ) == []
    assert packet["state"] == action.BLOCKED_STATE
    assert len(packet["prerequisites"]) == 16
    assert len(packet["blocked_prerequisite_ids"]) == 16
    assert packet["closure_projection"] == {
        "g0_state": "SOURCE_COMPLETE_RUNTIME_INDETERMINATE",
        "lw1_state": "BLOCKED_EXTERNAL_PREREQUISITES",
        "w0_genesis_receipt_issued": False,
        "lw1_wave_receipt_issued": False,
        "lw1_transition_gate_advance": False,
        "lw2_unlocked": False,
        "s2e_2b_2_closed": False,
        "s2_closed": False,
        "runtime_state": "UNVERIFIED_NOT_OBSERVED",
    }
    assert packet["packet_digest"] == action.packet_digest(packet)


def test_packet_never_contains_or_grants_secret_or_production_authority(
    tmp_path: Path,
) -> None:
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=_repo(tmp_path),
        inventory=_inventory(),
    )
    serialized = json.dumps(packet, sort_keys=True).lower()
    assert "private key" not in serialized
    assert "access_key" not in serialized
    assert "secret_key" not in serialized
    assert packet["authority_boundaries"] == {
        "task_issued_authority_count": 0,
        "total_authority_count": 9,
        "admitted_production_effect_receipt_count": 0,
        "total_production_effect_receipt_count": 6,
        "production_runtime_effect_performed_by_task": False,
        "packet_execution_receipt_absent_within_task_scope": True,
        "production_deploy_restart_pg_broker_order_authorized": False,
    }


def test_all_ready_inventory_cannot_emit_a_blocked_packet(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="do not emit a blocked packet"):
        action.build_s2e_lw1_operator_action_packet(
            repo_root=_repo(tmp_path),
            inventory=_inventory(ready=True),
        )


@pytest.mark.parametrize("mutation", ("missing", "extra", "promoted"))
def test_inventory_set_and_evidence_class_are_closed(
    tmp_path: Path,
    mutation: str,
) -> None:
    inventory = _inventory()
    if mutation == "missing":
        inventory["fixed_path_statuses"].pop(next(iter(action.EXPECTED_PATHS)))
    elif mutation == "extra":
        inventory["fixed_path_statuses"]["/tmp/caller-root"] = "READY"
    else:
        inventory["evidence_class"] = "PLATFORM_OR_EXTERNAL_ATTESTED"
    with pytest.raises(ValueError):
        action.build_s2e_lw1_operator_action_packet(
            repo_root=_repo(tmp_path),
            inventory=inventory,
        )


def test_dirty_source_checkpoint_is_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "checkpoint.txt").write_text("dirty\n", encoding="ascii")
    with pytest.raises(ValueError, match="clean source checkpoint"):
        action.build_s2e_lw1_operator_action_packet(
            repo_root=repo,
            inventory=_inventory(),
        )


@pytest.mark.parametrize(
    "mutate,expected",
    (
        (
            lambda packet: packet["closure_projection"].update(
                lw2_unlocked=True
            ),
            "const False",
        ),
        (
            lambda packet: packet["authority_boundaries"].update(
                task_issued_authority_count=1
            ),
            "const 0",
        ),
        (
            lambda packet: packet["prerequisites"][0].update(
                secret_material_allowed=True
            ),
            "const False",
        ),
    ),
)
def test_schema_rejects_authority_and_secret_boundary_escalation(
    tmp_path: Path,
    mutate,
    expected: str,
) -> None:
    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    mutate(packet)
    errors = action.validate_s2e_lw1_operator_action_packet(
        packet, repo_root=repo
    )
    assert any(expected in error for error in errors), errors


def test_digest_and_source_tree_tampering_fail_closed(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    packet = action.build_s2e_lw1_operator_action_packet(
        repo_root=repo,
        inventory=_inventory(),
    )
    forged_digest = deepcopy(packet)
    forged_digest["next_action"] = "CALLER_CHOSEN"
    assert action.validate_s2e_lw1_operator_action_packet(
        forged_digest, repo_root=repo
    )
    forged_tree = deepcopy(packet)
    forged_tree["source_binding"]["implementation_checkpoint_tree"] = "0" * 40
    forged_tree["packet_digest"] = action.packet_digest(forged_tree)
    errors = action.validate_s2e_lw1_operator_action_packet(
        forged_tree, repo_root=repo
    )
    assert any("checkpoint tree differs" in error for error in errors), errors


def test_cli_build_and_validate_use_same_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _repo(tmp_path)
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(_inventory()), encoding="utf-8")
    assert action.main([
        "build",
        "--repo-root",
        str(repo),
        "--inventory",
        str(inventory_path),
    ]) == 0
    packet = json.loads(capsys.readouterr().out)
    packet_path = tmp_path / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")
    assert action.main([
        "validate",
        "--repo-root",
        str(repo),
        "--packet",
        str(packet_path),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "PASS",
        "errors": [],
    }
