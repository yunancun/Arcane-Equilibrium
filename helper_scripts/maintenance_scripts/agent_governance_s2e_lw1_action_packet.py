#!/usr/bin/env python3
"""Build a non-authoritative S2E-LW1 external-prerequisite action packet."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "program_code" / "ml_training"
for candidate in (Path(__file__).resolve().parent, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from agent_governance_schema import schema_subset_errors  # noqa: E402
import agent_governance_s2_5_recovery as recovery  # noqa: E402
from aiml_gate_receipt_s2_5_host_capture import (  # noqa: E402
    HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH,
    RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH,
)
from aiml_gate_receipt_s2e_external_evidence import (  # noqa: E402
    DURABILITY_ANCHOR_TRUST_ROOT_PATH,
    OFFHOST_REPLICA_TRUST_ROOT_PATH,
    PREDECESSOR_REGISTRY_TRUST_ROOT_PATH,
)
from aiml_gate_receipt_s2e_launch import (  # noqa: E402
    S2E_RECEIPT_TRUST_ROOT_PATH,
)
from aiml_gate_receipt_schema_core import (  # noqa: E402
    _contains_github_secret_like_content,
    canonical_digest,
    git_argv,
    git_subprocess_env,
)


SCHEMA_VERSION = "s2e_lw1_operator_action_packet_v1"
INVENTORY_SCHEMA_VERSION = "s2e_lw1_readonly_inventory_v1"
BLOCKED_STATE = "BLOCKED_EXTERNAL_PREREQUISITES_ACTION_PACKET_READY"
SCHEMA_PATH = (
    REPO_ROOT / ".codex" / "schemas" / f"{SCHEMA_VERSION}.schema.json"
)
PATH_STATUS_VALUES = frozenset({
    "ABSENT",
    "NOT_OBSERVED",
    "PRESENT_UNVERIFIED",
    "READY",
})
SERVICE_STATUS_VALUES = frozenset({
    "NOT_CONFIGURED",
    "NOT_OBSERVED",
    "PRESENT_UNVERIFIED",
    "READY",
})
_PATH_PREREQUISITES = (
    (
        "S2E_RECEIPT_TRUST_ROOT",
        str(S2E_RECEIPT_TRUST_ROOT_PATH),
        "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE",
    ),
    (
        "DURABILITY_ANCHOR_TRUST_ROOT",
        str(DURABILITY_ANCHOR_TRUST_ROOT_PATH),
        "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE",
    ),
    (
        "PREDECESSOR_REGISTRY_TRUST_ROOT",
        str(PREDECESSOR_REGISTRY_TRUST_ROOT_PATH),
        "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE",
    ),
    (
        "RECOVERY_HOST_CAPTURE_TRUST_ROOT",
        str(RECOVERY_HOST_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_AUTHORIZATION_TRUST_ROOT",
        str(recovery.RECOVERY_AUTHORIZATION_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_ANCHOR_TRUST_ROOT",
        str(recovery.RECOVERY_ANCHOR_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_ANCHOR_READBACK_TRUST_ROOT",
        str(recovery.RECOVERY_ANCHOR_READBACK_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_CONSUMPTION_TRUST_ROOT",
        str(recovery.RECOVERY_CONSUMPTION_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_ACTOR_CAPTURE_TRUST_ROOT",
        str(recovery.RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT",
        str(recovery.RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_PUBLIC_KEY_PATH),
        "FIXED_PUBLIC_KEY_NOT_GROUP_OR_OTHER_WRITABLE",
    ),
    (
        "RECOVERY_HOST_CAPTURE_ATTESTOR_CAPABILITY",
        HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH,
        "ROOT_OWNED_FIXED_ATTESTOR_DERIVES_COMPLETE_SIGNED_CAPTURE_FROM_IMMUTABLE_SOURCE",
    ),
    (
        "OFFHOST_REPLICA_TRUST_ROOT",
        str(OFFHOST_REPLICA_TRUST_ROOT_PATH),
        "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE",
    ),
)
# Tier 1(operator 2026-08-02 裁決):durability 走 carrier schema 早已宣告的
# TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1 adapter。三項改為 host 側 root-owned 能力與
# off-host 副本,不再需要任何付費外部 custody 服務,也不做不可逆的 COMPLIANCE 保留。
_SERVICE_PREREQUISITES = (
    (
        "HOST_APPEND_ONLY_DURABILITY_ANCHOR",
        "operator-config:host-append-only-durability-anchor",
        "ROOT_OWNED_FIXED_APPEND_ONLY_ANCHOR_WITH_MONOTONIC_HEAD",
    ),
    (
        "OFFHOST_APPEND_ONLY_REPLICA",
        "operator-config:offhost-append-only-replica",
        "OFFHOST_APPEND_ONLY_REPLICA_WITH_LATEST_GENERATION_READBACK",
    ),
    (
        "HOST_APPEND_ONLY_PREDECESSOR_REGISTRY",
        "operator-config:host-predecessor-registry",
        "DISTINCT_FIXED_ROOT_APPEND_ONLY_SINGLE_USE_REGISTRY",
    ),
    # 與 OFFHOST_APPEND_ONLY_REPLICA 是兩件事:後者是副本儲存與複寫路徑,前者是
    # 「誰在第二台機器上用第二把 key 簽回讀證言」。合併會讓 packet 無法表達
    # 「副本有了但沒人能簽」這個真實中間態。
    (
        "OFFHOST_REPLICA_READBACK_SIGNER_CAPABILITY",
        "operator-config:offhost-replica-readback-signer",
        "OFFHOST_ROOT_OWNED_SIGNER_ON_SEPARATE_HOST_REACHABLE_FROM_TRADE_CORE_"
        "PRIVATE_KEY_NEVER_ON_ANCHOR_HOST",
    ),
)
EXPECTED_PATHS = tuple(item[1] for item in _PATH_PREREQUISITES)
EXPECTED_SERVICE_IDS = tuple(item[0] for item in _SERVICE_PREREQUISITES)
# 完整的有序動作目錄。它是**目錄**,不是「operator 現在必做的清單」——後者由
# `required_action_ids()` 從 packet 綁定的那個 checkout 推導。
#
# 為什麼要分這兩層(PR #180 Codex P1,複驗成立):`COMMIT_GENESIS_ARMED_DURABILITY_
# ANCHOR_FLOOR` 曾被本檔全域刪除,理由是該 floor 已於 `fdf3c0fa6` commit。但 packet
# 綁定的 checkpoint `970734ae0`(2026-08-03 04:35:38 +0200)比它早五分鐘,那個 head 的
# 樹裡**沒有** floor 檔;在該 pin 上重建 packet 於是漏掉一個當時真正必要的步驟,而且
# 照樣通過驗證。全域刪除把一種腐化(該做的已做完)換成了另一種(還沒做的被當成做完)。
#
# 腐化的真正成因是「靜態清單 + 早於事實的 pin」,round-2 與 round-4 兩度點名都沒有
# 任何測試看得到。所以正解是讓清單**恆等於 bound checkout 的事實**:目錄固定,
# 已完成項由該 commit 的樹決定,validator 在同一個 head 重算後逐項比對。
CANONICAL_ACTION_IDS = (
    "PROVISION_FIXED_TRUST_ROOTS",
    "PROVISION_HOST_CAPTURE_ATTESTOR_CAPABILITY",
    "PROVISION_HOST_APPEND_ONLY_DURABILITY_ANCHOR",
    "CONFIGURE_OFFHOST_APPEND_ONLY_REPLICA",
    "PROVISION_OFFHOST_REPLICA_READBACK_SIGNER",
    "PROVISION_DISTINCT_HOST_APPEND_ONLY_PREDECESSOR_REGISTRY",
    "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR",
    "RESUME_W0_AND_LW1_RECEIPT_CHAIN_WITH_FRESH_EVIDENCE",
)
REPOSITORY_COMPLETION_WITNESSES = {
    "COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR": (
        "docs/execution_plan/ai_ml_landing/receipts/S2E-LW1-LW5/"
        "durability-anchor-floor-v1.json"
    ),
}
# 只有一條的理由要寫明:其餘七項全是 host 側 provisioning(root-owned 信任根、
# append-only anchor、off-host replica、predecessor registry),repo 位元組永遠證明
# 不了它們的完成,故 witness 表天生稀疏。也正因為只有一條,一份靜態清單才能腐化多日
# 而 CI 全綠——這張表存在的目的就是讓下一條 witness 一出現就被機器抓到。
_COMMIT_RE = re.compile(r"\A[0-9a-f]{40}\Z")


def completed_action_ids(repo_root: Path, *, at_commit: str) -> tuple[str, ...]:
    """回傳在 `at_commit` 的樹裡已可由 repo 位元組證明完成的 action id(排序後)。

    刻意讀該 commit 的樹而不是工作樹:packet 的 pin 可能遠早於 current HEAD,
    而「當時該不該做這一步」只有那個 head 答得出來。`at_commit` 先做 40-hex 驗證
    再進 git——它在 validate 路徑上來自受檢 packet,屬於 caller 可控輸入。
    """

    if not _COMMIT_RE.match(at_commit):
        raise ValueError(f"LW1 completion probe needs a 40-hex commit: {at_commit!r}")
    return tuple(sorted(
        action_id
        for action_id, witness in REPOSITORY_COMPLETION_WITNESSES.items()
        if _witness_is_committed_blob(repo_root, at_commit, witness)
    ))


def _witness_is_committed_blob(
    repo_root: Path, at_commit: str, witness: str
) -> bool:
    """witness 是否在 `at_commit` 的樹裡、且確實是一個 blob。

    `--full-tree` 不能省(E2 P2-1,已實測):`ls-tree` 的 pathspec 預設相對於 `-C` 的
    prefix,而同一函式裡的 `rev-parse` 是 prefix 無關的。少了它,只要把 `--repo-root`
    指到任一子目錄,witness 就查不到 ⇒ 導出清單多一項 ⇒ **那份已經腐化的 8 項 packet
    反而通過驗證**,正是本次改動要消滅的那個缺陷。

    另外要求 type 是 `blob`:`ls-tree` 對一個目錄同樣會回一列,於是一個剛好同名的
    tree 會被當成「該步驟已完成」。今天 witness 表只有一條具體的 `.json`,但這張表
    的存在意義就是「下一條 witness 一出現就被機器接住」,守衛必須先於那一條存在。
    """

    entry = _git(repo_root, "ls-tree", "--full-tree", at_commit, "--", witness)
    fields = entry.split(maxsplit=2)
    return len(fields) >= 2 and fields[1] == "blob"


def required_action_ids(repo_root: Path, *, at_commit: str) -> tuple[str, ...]:
    """目錄減去該 checkout 已能證明完成的項;目錄順序保留。"""

    completed = set(completed_action_ids(repo_root, at_commit=at_commit))
    return tuple(
        action_id
        for action_id in CANONICAL_ACTION_IDS
        if action_id not in completed
    )


def _git(repo_root: Path, *args: str) -> str:
    return subprocess.run(
        git_argv(repo_root, *args),
        cwd=repo_root,
        check=True,
        capture_output=True,
        env=git_subprocess_env(),
        text=True,
    ).stdout.strip()


def packet_digest(packet: dict[str, Any]) -> str:
    return canonical_digest({
        key: value for key, value in packet.items() if key != "packet_digest"
    })


def _strict_inventory(inventory: Any) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not isinstance(inventory, dict):
        return {}, ["LW1 read-only inventory must be an object"]
    expected_fields = {
        "schema_version",
        "host",
        "observed_at",
        "evidence_class",
        "linux_source_head",
        "linux_worktree_clean",
        "fixed_path_statuses",
        "service_statuses",
        "runtime_units",
        "canonical_roots",
    }
    if set(inventory) != expected_fields:
        errors.append("LW1 read-only inventory fields differ from closed contract")
    if inventory.get("schema_version") != INVENTORY_SCHEMA_VERSION:
        errors.append("LW1 read-only inventory schema_version is invalid")
    if inventory.get("evidence_class") != (
        "UNAUTHENTICATED_READ_ONLY_OBSERVATION"
    ):
        errors.append("LW1 inventory cannot self-promote its evidence class")
    path_statuses = inventory.get("fixed_path_statuses")
    if not isinstance(path_statuses, dict) or set(path_statuses) != set(
        EXPECTED_PATHS
    ):
        errors.append("LW1 inventory fixed path set differs from code-owned set")
    elif any(value not in PATH_STATUS_VALUES for value in path_statuses.values()):
        errors.append("LW1 inventory contains an invalid fixed path status")
    service_statuses = inventory.get("service_statuses")
    if not isinstance(service_statuses, dict) or set(service_statuses) != set(
        EXPECTED_SERVICE_IDS
    ):
        errors.append("LW1 inventory service set differs from code-owned set")
    elif any(
        value not in SERVICE_STATUS_VALUES for value in service_statuses.values()
    ):
        errors.append("LW1 inventory contains an invalid service status")
    if _contains_github_secret_like_content(inventory):
        errors.append("LW1 inventory contains secret-like material")
    return inventory, sorted(set(errors))


def build_s2e_lw1_operator_action_packet(
    *,
    repo_root: Path,
    inventory: Any,
) -> dict[str, Any]:
    """Build one blocked packet; this function cannot emit readiness authority."""

    inventory, errors = _strict_inventory(inventory)
    if errors:
        raise ValueError("; ".join(errors))
    root = repo_root.resolve()
    if _git(root, "status", "--porcelain=v1"):
        raise ValueError("LW1 action packet requires a clean source checkpoint")
    source_head = _git(root, "rev-parse", "HEAD")
    source_tree = _git(root, "rev-parse", "HEAD^{tree}")
    actions = required_action_ids(root, at_commit=source_head)
    if not actions:
        raise ValueError(
            "this checkpoint already completes every LW1 operator action; "
            "do not emit a blocked packet"
        )
    path_statuses = inventory["fixed_path_statuses"]
    service_statuses = inventory["service_statuses"]
    prerequisites = [
        {
            "prerequisite_id": item_id,
            "category": "FIXED_HOST_PATH",
            "locator": path,
            "required_property": required,
            "status": path_statuses[path],
            "blocking": path_statuses[path] != "READY",
            "secret_material_allowed": False,
        }
        for item_id, path, required in _PATH_PREREQUISITES
    ]
    prerequisites.extend(
        {
            "prerequisite_id": item_id,
            "category": "EXTERNAL_SERVICE",
            "locator": locator,
            "required_property": required,
            "status": service_statuses[item_id],
            "blocking": service_statuses[item_id] != "READY",
            "secret_material_allowed": False,
        }
        for item_id, locator, required in _SERVICE_PREREQUISITES
    )
    prerequisites.sort(key=lambda item: item["prerequisite_id"])
    blocked_ids = sorted(
        item["prerequisite_id"] for item in prerequisites if item["blocking"]
    )
    if not blocked_ids:
        raise ValueError(
            "all LW1 external prerequisites appear READY; do not emit a blocked packet"
        )
    packet = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "UNBLOCK_S2E_LW1_EXTERNAL_EVIDENCE_AND_RECEIPT_CHAIN",
        "launch_id": "S2E-LW1-LW5",
        "wave": "S2E-LW1",
        "state": BLOCKED_STATE,
        "source_binding": {
            "implementation_checkpoint_head": source_head,
            "implementation_checkpoint_tree": source_tree,
            "worktree_clean_at_build": True,
        },
        "readonly_observation": {
            "host": inventory["host"],
            "observed_at": inventory["observed_at"],
            "evidence_class": inventory["evidence_class"],
            "inventory_digest": canonical_digest(inventory),
            "linux_source_head": inventory["linux_source_head"],
            "linux_worktree_clean": inventory["linux_worktree_clean"],
            "runtime_units": deepcopy(inventory["runtime_units"]),
            "canonical_roots": deepcopy(inventory["canonical_roots"]),
        },
        "prerequisites": prerequisites,
        "blocked_prerequisite_ids": blocked_ids,
        "required_action_ids": list(actions),
        "closure_projection": {
            "g0_state": "SOURCE_COMPLETE_RUNTIME_INDETERMINATE",
            "lw1_state": "BLOCKED_EXTERNAL_PREREQUISITES",
            "w0_genesis_receipt_issued": False,
            "lw1_wave_receipt_issued": False,
            "lw1_transition_gate_advance": False,
            "lw2_unlocked": False,
            "s2e_2b_2_closed": False,
            "s2_closed": False,
            "runtime_state": "UNVERIFIED_NOT_OBSERVED",
        },
        "authority_boundaries": {
            "task_issued_authority_count": 0,
            "total_authority_count": 9,
            "admitted_production_effect_receipt_count": 0,
            "total_production_effect_receipt_count": 6,
            "production_runtime_effect_performed_by_task": False,
            "packet_execution_receipt_absent_within_task_scope": True,
            "production_deploy_restart_pg_broker_order_authorized": False,
        },
        "sensitive_material_policy": {
            "policy": "NO_SECRET_MATERIAL_IN_PACKET",
            "credential_channel_name_only": True,
            "private_key_material_permitted": False,
        },
        "next_action": (
            "OPERATOR_PROVISION_EXTERNAL_PREREQUISITES_THEN_RESUME_S2E_LW1"
        ),
    }
    packet["packet_digest"] = packet_digest(packet)
    validation_errors = validate_s2e_lw1_operator_action_packet(
        packet, repo_root=root
    )
    if validation_errors:
        raise ValueError("; ".join(validation_errors))
    return packet


def validate_s2e_lw1_operator_action_packet(
    packet: Any,
    *,
    repo_root: Path,
) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = schema_subset_errors(packet, schema, root_schema=schema)
    if errors or not isinstance(packet, dict):
        return errors
    prerequisites = packet["prerequisites"]
    expected = {
        item_id: (path, required)
        for item_id, path, required in _PATH_PREREQUISITES
    }
    expected.update({
        item_id: (locator, required)
        for item_id, locator, required in _SERVICE_PREREQUISITES
    })
    actual_ids = [item["prerequisite_id"] for item in prerequisites]
    if actual_ids != sorted(expected) or len(actual_ids) != len(set(actual_ids)):
        errors.append("LW1 packet prerequisite IDs differ from code-owned set")
    for item in prerequisites:
        item_id = item["prerequisite_id"]
        if item_id not in expected:
            continue
        if (item["locator"], item["required_property"]) != expected[item_id]:
            errors.append(f"LW1 packet prerequisite binding differs: {item_id}")
        if item["blocking"] != (item["status"] != "READY"):
            errors.append(f"LW1 packet blocker projection differs: {item_id}")
        if item["secret_material_allowed"] is not False:
            errors.append(f"LW1 packet permits secret material: {item_id}")
    expected_blocked = sorted(
        item["prerequisite_id"] for item in prerequisites if item["blocking"]
    )
    if not expected_blocked:
        errors.append("LW1 blocked packet has no blocked prerequisite")
    if packet["blocked_prerequisite_ids"] != expected_blocked:
        errors.append("LW1 packet blocked prerequisite projection differs")
    binding = packet["source_binding"]
    try:
        head = binding["implementation_checkpoint_head"]
        if _git(repo_root, "rev-parse", f"{head}^{{commit}}") != head:
            errors.append("LW1 packet implementation checkpoint is unavailable")
        if _git(repo_root, "rev-parse", f"{head}^{{tree}}") != binding[
            "implementation_checkpoint_tree"
        ]:
            errors.append("LW1 packet implementation checkpoint tree differs")
        # 動作清單在 packet **自己綁定的 head** 上重算,不是在 repo_root 的 HEAD 上。
        # 兩者常常不同,而「那時該不該做這一步」只有 bound head 答得出來。
        if tuple(packet["required_action_ids"]) != required_action_ids(
            repo_root, at_commit=head
        ):
            errors.append(
                "LW1 packet action sequence differs from the sequence its bound "
                "checkpoint requires"
            )
    except (OSError, ValueError, subprocess.CalledProcessError):
        errors.append("LW1 packet source binding cannot be verified")
    if packet["packet_digest"] != packet_digest(packet):
        errors.append("LW1 packet digest is invalid")
    if _contains_github_secret_like_content(packet):
        errors.append("LW1 packet contains secret-like material")
    return sorted(set(errors))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    build.add_argument("--inventory", type=Path, required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    validate.add_argument("--packet", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.action == "build":
        inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
        packet = build_s2e_lw1_operator_action_packet(
            repo_root=args.repo_root,
            inventory=inventory,
        )
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
        return 0
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    errors = validate_s2e_lw1_operator_action_packet(
        packet, repo_root=args.repo_root
    )
    print(json.dumps({"status": "PASS" if not errors else "FAIL", "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
