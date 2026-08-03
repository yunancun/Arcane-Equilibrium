"""Committed durability anchor floor: the code-owned, Git-read monotonicity pin.

§LW1 的 anchor 選言要求一個「外部」的 monotonic counter/append-only head。單靠
attestation 自報的 `previous_anchor_head_digest` 無法成立——那條鏈是自封閉的:
四個 digest 全部由 attestation 自己的欄位重算,驗證端從不與任何真實前手比對。

本模組把 receipt 已經釘在 git 上的 anchor 世代投影成一份 **code-owned 路徑**的
committed floor,並由驗證器自己以 `git show <commit>:<path>` 讀 **commit 物件的
位元組**(不是工作樹)。floor 不是新的信任源,也不帶簽章:它的完整性來自
`floor_history_errors` 的祖先鏈 + 嚴格遞增檢查,以及改寫它需要第二組 capability
(GitHub 寫入權 + PR + required checks)這件事實。

誠實邊界(不得在註解或 PR 說明裡被寫成更強的宣稱):

- git 提供的是 *tamper-evident + 需要第二組 capability*,**不是 WORM**。持有 GitHub
  寫入權的人可以合法 merge 一份倒退的 floor;本模組只把這件事變成**機械可偵測**。
- 只有**相鄰世代**宣稱 hash 連結;非相鄰世代之間只宣稱單調遞增。中間條目的
  `entry_digest` 無原像可驗,替 gap 提供 link path 是假的安全性。**本模組不宣稱
  「hash chain 完整性已驗證」。**
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import _load_schema, canonical_digest


LAUNCH_ID = "S2E-LW1-LW5"
DURABILITY_ANCHOR_FLOOR_SCHEMA = "s2e_durability_anchor_floor_v1"
GENESIS_WAVE = "W0-GENESIS"
# floor 的路徑由 LAUNCH_ID 導出,caller 永遠不能指定它;跨 launch 重放因此在路徑層先斷。
_FLOOR_REPO_PATH = (
    f"docs/execution_plan/ai_ml_landing/receipts/{LAUNCH_ID}/"
    "durability-anchor-floor-v1.json"
)
# LW1-LW5 全程最多 6 個 floor commit;上界只用來擋病態歷史,不是效能參數。
MAX_FLOOR_HISTORY_COMMITS = 32
_FLOOR_INVARIANT_FIELDS = ("launch_id", "anchor_locator", "offhost_replica_locator")


def durability_anchor_floor_repo_path() -> str:
    """Return the code-owned repository path of the committed floor."""

    return _FLOOR_REPO_PATH


def durability_anchor_floor_digest(floor: dict[str, Any]) -> str:
    """Canonical self-digest over every field except the digest itself."""

    return canonical_digest({
        key: value for key, value in floor.items() if key != "floor_digest"
    })


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
    ).stdout


def _floor_shape_errors(raw: bytes, *, label: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        floor = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [f"{label} durability anchor floor JSON is invalid: {error}"]
    schema = _load_schema(DURABILITY_ANCHOR_FLOOR_SCHEMA)
    errors = [
        f"{label} durability anchor floor schema violation: {error}"
        for error in schema_subset_errors(floor, schema, root_schema=schema)
    ]
    if errors or not isinstance(floor, dict):
        return None, errors
    if floor.get("floor_digest") != durability_anchor_floor_digest(floor):
        return None, [f"{label} durability anchor floor digest is invalid"]
    if floor.get("launch_id") != LAUNCH_ID:
        return None, [f"{label} durability anchor floor launch_id binding differs"]
    if floor["state"] == "GENESIS_ARMED":
        expected_genesis = (0, None, None, None)
        actual_genesis = (
            floor["floor_generation"],
            floor["floor_head_digest"],
            floor["bound_receipt_payload_digest"],
            floor["bound_acceptance_review_bundle_digest"],
        )
        if actual_genesis != expected_genesis:
            return None, [
                f"{label} GENESIS_ARMED durability anchor floor must be "
                "generation zero with no bound head or receipt"
            ]
    elif (
        floor["floor_generation"] < 1
        or floor["floor_head_digest"] is None
        or floor["bound_receipt_payload_digest"] is None
        or floor["bound_acceptance_review_bundle_digest"] is None
    ):
        return None, [
            f"{label} ADVANCED durability anchor floor must bind an exact head "
            "and issued receipt"
        ]
    return floor, []


def floor_history_errors(
    repo_root: Path, *, at_commit: str
) -> tuple[dict[str, Any] | None, list[str]]:
    """Walk every commit that touched the floor and enforce §3.4 三條歷史性質。

    祖先鏈 + 嚴格遞增 + 單一 GENESIS_ARMED,全部不需要任何私鑰即可執行。
    """

    path = _FLOOR_REPO_PATH
    try:
        # --full-history:關掉 git 的 history simplification。預設模式會在 merge 處
        # 只跟隨一個 parent,足以讓一份被 merge 進來的倒退 floor 從走訪中消失。
        listing = _git_bytes(
            repo_root,
            "log",
            "--format=%H",
            "--reverse",
            "--topo-order",
            "--full-history",
            at_commit,
            "--",
            path,
        ).decode("ascii")
    except (OSError, subprocess.CalledProcessError) as error:
        return None, [f"durability anchor floor history is unavailable: {error}"]
    commits = [line.strip() for line in listing.splitlines() if line.strip()]
    if not commits:
        return None, [
            "durability anchor floor is absent from the reviewed commit history"
        ]
    if len(commits) > MAX_FLOOR_HISTORY_COMMITS:
        return None, ["durability anchor floor history exceeds its admitted length"]
    errors: list[str] = []
    previous_floor: dict[str, Any] | None = None
    previous_commit: str | None = None
    revision_index = 0
    last_raw = b""
    for commit in commits:
        if previous_commit is not None:
            ancestry = subprocess.run(
                [
                    "git", "-C", str(repo_root), "merge-base", "--is-ancestor",
                    previous_commit, commit,
                ],
                capture_output=True,
            )
            if ancestry.returncode != 0:
                errors.append(
                    "durability anchor floor history is not a single ancestor chain"
                )
        try:
            raw = _git_bytes(repo_root, "show", f"{commit}:{path}")
        except (OSError, subprocess.CalledProcessError) as error:
            return None, errors + [
                f"durability anchor floor revision is unreadable: {error}"
            ]
        previous_commit = commit
        if raw == last_raw:
            # merge commit 原樣帶進同一份 floor:那不是一次新的推進,不參與序檢查。
            continue
        floor, shape_errors = _floor_shape_errors(raw, label=f"commit {commit[:12]}")
        if shape_errors or floor is None:
            return None, errors + shape_errors
        if floor["state"] == "GENESIS_ARMED" and revision_index != 0:
            errors.append(
                "durability anchor floor re-enters GENESIS_ARMED after its first commit"
            )
        if previous_floor is not None:
            if floor["floor_generation"] <= previous_floor["floor_generation"]:
                errors.append(
                    "durability anchor floor generation is not strictly increasing"
                )
            for field in _FLOOR_INVARIANT_FIELDS:
                if floor[field] != previous_floor[field]:
                    errors.append(
                        f"durability anchor floor {field} changed across its history"
                    )
        previous_floor = floor
        revision_index += 1
        last_raw = raw
    try:
        head_raw = _git_bytes(repo_root, "show", f"{at_commit}:{path}")
    except (OSError, subprocess.CalledProcessError) as error:
        return None, errors + [
            f"durability anchor floor is unreadable at the reviewed commit: {error}"
        ]
    if head_raw != last_raw:
        errors.append(
            "durability anchor floor at the reviewed commit differs byte-for-byte "
            "from its own history tail"
        )
    if errors:
        return None, sorted(set(errors))
    return previous_floor, []


def read_committed_durability_anchor_floor(
    repo_root: Path, *, at_commit: Any
) -> tuple[dict[str, Any] | None, list[str]]:
    """Read the floor from commit bytes; the working tree is never consulted."""

    if not isinstance(at_commit, str) or not at_commit:
        return None, ["durability anchor floor requires an exact reviewed commit"]
    return floor_history_errors(repo_root, at_commit=at_commit)


def _adjacent_link_errors(
    successor: dict[str, Any],
    *,
    predecessor_generation: Any,
    predecessor_head: Any,
    label: str,
) -> list[str]:
    """相鄰世代(n → n+1)必須 hash 連結;非相鄰世代只宣稱單調,不宣稱連結。"""

    if not isinstance(predecessor_generation, int):
        return []
    if successor.get("anchor_generation") != predecessor_generation + 1:
        return []
    if successor.get("previous_anchor_head_digest") != predecessor_head:
        return [f"{label} does not hash-link to the immediately prior head"]
    return []


def durability_anchor_floor_errors(
    anchor: Any,
    *,
    floor: dict[str, Any],
    label: str,
    candidate_wave: str | None = None,
) -> list[str]:
    """One attestation against the committed floor (§3.3(a) 的五條規則)。"""

    if not isinstance(anchor, dict):
        return [f"{label} requires an exact durability anchor attestation"]
    errors: list[str] = []
    if anchor.get("anchor_locator") != floor["anchor_locator"]:
        errors.append(f"{label} anchor_locator differs from the committed floor")
    if anchor.get("offhost_replica_locator") != floor["offhost_replica_locator"]:
        errors.append(
            f"{label} offhost_replica_locator differs from the committed floor"
        )
    generation = anchor.get("anchor_generation")
    if not isinstance(generation, int) or generation <= floor["floor_generation"]:
        errors.append(
            f"{label} generation does not strictly exceed the committed floor"
        )
    if floor["state"] == "ADVANCED":
        if anchor.get("previous_anchor_head_digest") is None:
            errors.append(
                f"{label} omits a previous head above an ADVANCED committed floor"
            )
        errors.extend(_adjacent_link_errors(
            anchor,
            predecessor_generation=floor["floor_generation"],
            predecessor_head=floor["floor_head_digest"],
            label=label,
        ))
    else:
        if candidate_wave is not None and candidate_wave != GENESIS_WAVE:
            errors.append(
                f"{label} advances a GENESIS_ARMED committed floor from a "
                "non-genesis candidate"
            )
        if generation != 1 or anchor.get("previous_anchor_head_digest") is not None:
            errors.append(
                f"{label} genesis generation must be exactly one with no prior head"
            )
    return errors


def durability_anchor_order_errors(
    sequence: list[tuple[str, Any]], *, floor: dict[str, Any]
) -> list[str]:
    """Strictly order every anchor seen in one transition against the floor."""

    errors: list[str] = []
    previous_label: str | None = None
    previous: dict[str, Any] | None = None
    for label, anchor in sequence:
        if not isinstance(anchor, dict):
            errors.append(f"{label} requires an exact durability anchor attestation")
            previous_label, previous = None, None
            continue
        if anchor.get("anchor_locator") != floor["anchor_locator"]:
            errors.append(f"{label} anchor_locator differs from the committed floor")
        if anchor.get("offhost_replica_locator") != floor["offhost_replica_locator"]:
            errors.append(
                f"{label} offhost_replica_locator differs from the committed floor"
            )
        generation = anchor.get("anchor_generation")
        if previous is not None:
            prior_generation = previous.get("anchor_generation")
            if not isinstance(generation, int) or not isinstance(
                prior_generation, int
            ) or generation <= prior_generation:
                errors.append(
                    f"{label} generation does not strictly exceed {previous_label}"
                )
            errors.extend(_adjacent_link_errors(
                anchor,
                predecessor_generation=prior_generation,
                predecessor_head=previous.get("anchor_head_digest"),
                label=label,
            ))
        previous_label, previous = label, anchor
    return errors


def durability_anchor_floor_binding_errors(
    *,
    floor: dict[str, Any],
    predecessor_receipt: Any,
    predecessor_authority: Any,
) -> list[str]:
    """§3.3(b).1-2:把 caller 供給的 predecessor 綁到 git 上唯一那一份 floor。

    這是整個修法的樞紐。沒有它,transition gate 的兩側都由被驗證者自己提供比較
    基準,「資料已經在 git 裡」對驗證器而言等於「資料在 caller 手裡」。
    """

    if not isinstance(predecessor_receipt, dict):
        return ["transition requires an exact predecessor receipt to bind the floor"]
    errors: list[str] = []
    if floor["bound_receipt_payload_digest"] != predecessor_receipt.get(
        "payload_digest"
    ):
        errors.append(
            "transition predecessor is not the receipt bound by the committed "
            "durability anchor floor"
        )
    if floor["bound_acceptance_review_bundle_digest"] != predecessor_receipt.get(
        "acceptance_review_bundle_digest"
    ):
        errors.append(
            "transition predecessor review bundle is not the bundle bound by the "
            "committed durability anchor floor"
        )
    review_anchor = (
        predecessor_authority.get("review_durability_anchor_attestation")
        if isinstance(predecessor_authority, dict)
        else None
    )
    if isinstance(review_anchor, dict):
        # caller 不能改寫前一份 anchor 的世代——要改必須先 merge 一個 commit。
        if review_anchor.get("anchor_generation") != floor["floor_generation"]:
            errors.append(
                "transition predecessor review durability anchor generation "
                "differs from the committed floor"
            )
        if review_anchor.get("anchor_head_digest") != floor["floor_head_digest"]:
            errors.append(
                "transition predecessor review durability anchor head differs "
                "from the committed floor"
            )
    return errors


def durability_anchor_transition_order_errors(
    *,
    floor: dict[str, Any],
    predecessor_authority: Any,
    candidate_anchor: Any,
) -> list[str]:
    """§3.3(b).3-5:a → b → c 嚴格遞增、相鄰世代 hash 連結、c 必有前手。"""

    authority = predecessor_authority if isinstance(predecessor_authority, dict) else {}
    errors = durability_anchor_order_errors(
        [
            (
                "transition predecessor review durability anchor",
                authority.get("review_durability_anchor_attestation"),
            ),
            (
                "transition predecessor carrier durability anchor",
                authority.get("carrier_durability_anchor_attestation"),
            ),
            ("transition candidate review durability anchor", candidate_anchor),
        ],
        floor=floor,
    )
    if not isinstance(candidate_anchor, dict) or (
        candidate_anchor.get("previous_anchor_head_digest") is None
    ):
        errors.append(
            "transition candidate review durability anchor omits its previous head"
        )
    return errors


def next_durability_anchor_floor(
    receipt: dict[str, Any], bundle: dict[str, Any]
) -> dict[str, Any]:
    """Project the next floor for a human to commit; validators never write files."""

    binding = bundle.get("durability_anchor_binding") or {}
    floor = {
        "schema_version": DURABILITY_ANCHOR_FLOOR_SCHEMA,
        "launch_id": LAUNCH_ID,
        "state": "ADVANCED",
        "anchor_locator": binding.get("anchor_locator"),
        "offhost_replica_locator": binding.get("offhost_replica_locator"),
        "floor_generation": binding.get("anchor_generation"),
        "floor_head_digest": binding.get("anchor_head_digest"),
        "bound_receipt_payload_digest": receipt.get("payload_digest"),
        "bound_acceptance_review_bundle_digest": bundle.get("bundle_digest"),
    }
    floor["floor_digest"] = durability_anchor_floor_digest(floor)
    return floor
