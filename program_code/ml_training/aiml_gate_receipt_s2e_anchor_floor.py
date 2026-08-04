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
- **`at_commit` 由被驗證者遞來**,因此「floor 已在 git 裡」本身不是外部性。外部性
  來自 `_PROTECTED_ANCESTOR_REFS`:鏈尾必須是某個 code-owned 受保護 ref 的祖先。
  不可達時本模組**不判 PASS 也不判 FAIL,而是判 `UNVERIFIED`**——那正是 §LW1
  「同一 writer 可 coherent rewrite ⇒ 只能得 `UNVERIFIED`」的處置。
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any, NamedTuple

from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _load_schema, canonical_digest, git_subprocess_env,
)


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

# ── P0-1(PM 2026-08-04 裁決;出處:2026-08-03 三路複核 §六「必要」第 1 項的二選一) ──
# 複核給的是二選一:(a) 把 floor 綁到 caller 選不了的 ref,或 (b) 誠實判 UNVERIFIED。
# PM 把兩者合成為一條:**綁受保護 ref,且不可達時判 UNVERIFIED 而非 FAIL**,因為
# §LW1 自己就把「同一 writer 可 coherent rewrite」寫成 UNVERIFIED 的典型判定,不是
# 硬失敗。這讓 feature branch 在 merge 前仍可跑並得到誠實結果,而不是假綠或假紅。
#
# 名單刻意是**模組級常數**:不從 argv／函式參數／環境變數取。任何一條可注入的路徑
# 都會讓「外部性」重新回到被驗證者手上,那正是複核 P0-1 的根因。
#
# **誠實邊界(不得在 PR 說明裡被寫成更強的宣稱)**:`refs/remotes/origin/main` 是
# **本地** remote-tracking ref。能以驗證器的 uid 寫 `.git` 的人可以 `git update-ref`
# 直接指定它——本模組的測試就是這樣建可達 fixture 的。因此本條**不是**密碼學外部性,
# 而是:(1) 把「遞一個 commit」提升為「同時偽造 remote-tracking 狀態」,(2) 在真實
# CI／clone 上讓該 ref 由 fetch 決定、攻擊者要改就得動 GitHub 那組 capability。
# 真正的外部性上界仍在 §LW1 說的「不同 owner/capability」,那需要驗證器不與被驗者
# 共用 uid;在受檢主機上執行的驗證器沒有辦法自證這件事(與 §5.3 的資訊論上界同型)。
_PROTECTED_ANCESTOR_REFS = ("refs/remotes/origin/main",)
# P1-2:`at_commit` 一路來自受驗 receipt 的 `source_head`／`reviewed_head`。git 的
# revision 位置在 `--` 之前,`--output=<path>` 這種單 token 參數會被當成選項吃掉——
# PM 於 git 2.55 實測 `git log ... "--output=victim.txt" -- .` 把既有檔案**截斷為
# 0 bytes** 且 exit 0。因此任何 git 呼叫**之前**先做逐字形狀驗證,不合格不進 subprocess。
_EXACT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

FLOOR_VERIFIED = "VERIFIED"
FLOOR_REJECTED = "REJECTED"
FLOOR_UNVERIFIED = "UNVERIFIED"


class CommittedFloorReading(NamedTuple):
    """一次 floor 讀取的 typed 結果:verdict + floor + errors。

    刻意**不是** `(floor, errors)` 二元組。舊形狀讓呼叫端只能問「floor 是不是
    None」,而 `(None, [])` 這個組合在 P1-3 裡靜默關掉了整組 floor 規則。三欄形狀
    使 `verdict` 成為第一級事實,並讓舊的二元解包在第一次執行就當場 ValueError,
    而不是安靜地繼續跑。
    """

    verdict: str
    floor: dict[str, Any] | None
    errors: list[str]


def _floor_reading(
    verdict: str, floor: dict[str, Any] | None, errors: list[str]
) -> CommittedFloorReading:
    """唯一建構入口:非 VERIFIED 一律 `floor=None` 且 `errors` 必非空。

    P1-3 的教訓是「floor is None 且 errors 為空」可以讓整組規則靜默消失。這裡把該
    形狀變成**建構期不可能**:任何非 VERIFIED 的判定若沒帶理由,會被補上一條具名
    錯誤。UNVERIFIED 因此永遠帶得動呼叫端的 fail-closed,絕不會被當成沒事。
    """

    if verdict == FLOOR_VERIFIED and isinstance(floor, dict) and not errors:
        return CommittedFloorReading(FLOOR_VERIFIED, floor, [])
    stated = sorted(set(errors)) or [
        f"durability anchor floor is {verdict} without a stated reason"
    ]
    return CommittedFloorReading(
        FLOOR_UNVERIFIED if verdict == FLOOR_UNVERIFIED else FLOOR_REJECTED,
        None,
        stated,
    )


def floor_gate_errors(reading: CommittedFloorReading, *, label: str) -> list[str]:
    """把一次 reading 轉成呼叫端要 extend 的 errors,並保證非 VERIFIED 必留痕。

    這是 P1-3 在呼叫端的那一半:`_floor_reading` 保證模組內不可能產出無理由的
    非 VERIFIED,本函式保證即使有人日後繞過該建構入口,呼叫端仍拿得到非空 errors。
    """

    errors = [f"{label}: {error}" for error in reading.errors]
    if reading.verdict != FLOOR_VERIFIED and not errors:
        errors.append(f"{label}: verdict {reading.verdict} carried no stated reason")
    return errors


def durability_anchor_floor_repo_path() -> str:
    """Return the code-owned repository path of the committed floor."""

    return _FLOOR_REPO_PATH


def durability_anchor_floor_digest(floor: dict[str, Any]) -> str:
    """Canonical self-digest over every field except the digest itself."""

    return canonical_digest({
        key: value for key, value in floor.items() if key != "floor_digest"
    })


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    # P1-6:`env=` 白名單。沒有它,ambient `GIT_DIR` 會蓋過 `-C`,驗證器讀到的是
    # 攻擊者 repo 的 floor 而且零錯誤(E3 實測)。
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=True,
        capture_output=True,
        env=git_subprocess_env(),
    ).stdout


def _git_ok(repo_root: Path, *args: str) -> bool:
    """只問離開碼的 git 呼叫(祖先判定、ref 解析);同樣走白名單環境。"""

    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        env=git_subprocess_env(),
    ).returncode == 0


def _object_store_errors(repo_root: Path) -> list[str]:
    """P1-5:非完整 object store 會讓整組歷史檢查靜默變成 no-op。

    E2 實測:同一份被 rollback 的 repo,full clone 判紅、`depth=1` shallow clone
    回 `(gen=2, errors=[])`——因為被 rollback 的那段歷史根本不在錐體裡。replace ref
    則可以把任一 commit 的內容整個換掉。這是**驗證器自身環境不合格**,不是被驗對象
    的性質,所以判 REJECTED(拒絕在這個環境裡跑)而不是 UNVERIFIED。
    """

    try:
        shallow = _git_bytes(repo_root, "rev-parse", "--is-shallow-repository")
        replaced = _git_bytes(
            repo_root, "for-each-ref", "--format=%(refname)", "refs/replace/"
        )
    except (OSError, subprocess.CalledProcessError) as error:
        return [f"durability anchor floor object store is unreadable: {error}"]
    errors: list[str] = []
    if shallow.decode("ascii", errors="replace").strip() != "false":
        errors.append(
            "durability anchor floor cannot be read from a shallow repository"
        )
    if replaced.strip():
        errors.append(
            "durability anchor floor cannot be read from a repository that "
            "rewrites objects through replace refs"
        )
    return errors


def _protected_ancestry_errors(repo_root: Path, commit: str) -> list[str]:
    """floor 鏈尾必須是某個 code-owned 受保護 ref 的祖先(P0-1)。

    只檢查鏈尾:祖先鏈檢查已保證其餘 revision 都是鏈尾的祖先,祖先關係遞移。
    受保護 ref 一個都解析不出來時**不得 fail-open**,同樣回 UNVERIFIED 的理由。
    """

    resolvable = False
    for ref in _PROTECTED_ANCESTOR_REFS:
        if not _git_ok(
            repo_root, "rev-parse", "--verify", "--quiet", "--end-of-options",
            f"{ref}^{{commit}}",
        ):
            continue
        resolvable = True
        if _git_ok(
            repo_root, "merge-base", "--is-ancestor", "--end-of-options", commit, ref
        ):
            return []
    if not resolvable:
        return [
            "UNVERIFIED: no code-owned protected ref resolves in this repository, "
            "so the floor cannot be shown to require a second capability"
        ]
    return [
        "UNVERIFIED: its history tail is not an ancestor of any code-owned "
        "protected ref, so a single writer could have authored it"
    ]


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
    repo_root: Path, *, at_commit: Any
) -> CommittedFloorReading:
    """Walk every commit that touched the floor and enforce §3.4 三條歷史性質。

    祖先鏈 + 嚴格遞增 + 鏈首唯一 GENESIS_ARMED,全部不需要任何私鑰即可執行;
    最後再要求鏈尾落在受保護 ref 的祖先集合內(P0-1),否則判 UNVERIFIED。
    """

    if not isinstance(at_commit, str) or not _EXACT_COMMIT_PATTERN.match(at_commit):
        # P1-2:先驗形狀再碰 subprocess。這一條**必須**在任何 git 呼叫之前。
        return _floor_reading(FLOOR_REJECTED, None, [
            "durability anchor floor requires an exact 40-hex reviewed commit"
        ])
    path = _FLOOR_REPO_PATH
    store_errors = _object_store_errors(repo_root)
    if store_errors:
        return _floor_reading(FLOOR_REJECTED, None, store_errors)
    try:
        # --full-history:關掉 git 的 history simplification。預設模式會在 merge 處
        # 只跟隨一個 parent,足以讓一份被 merge 進來的倒退 floor 從走訪中消失。
        # --end-of-options:即使上面的形狀驗證日後被改動,revision 也不會被 git
        # 當成選項解析(縱深防禦,非唯一防線)。
        listing = _git_bytes(
            repo_root,
            "log",
            "--format=%H",
            "--reverse",
            "--topo-order",
            "--full-history",
            "--end-of-options",
            at_commit,
            "--",
            path,
        ).decode("ascii")
    except (OSError, subprocess.CalledProcessError) as error:
        return _floor_reading(FLOOR_REJECTED, None, [
            f"durability anchor floor history is unavailable: {error}"
        ])
    commits = [line.strip() for line in listing.splitlines() if line.strip()]
    if not commits:
        return _floor_reading(FLOOR_REJECTED, None, [
            "durability anchor floor is absent from the reviewed commit history"
        ])
    if len(commits) > MAX_FLOOR_HISTORY_COMMITS:
        return _floor_reading(FLOOR_REJECTED, None, [
            "durability anchor floor history exceeds its admitted length"
        ])
    errors: list[str] = []
    previous_floor: dict[str, Any] | None = None
    previous_commit: str | None = None
    revision_index = 0
    # P1-3:哨兵必須是 `None`,不能是 `b""`。`b""` 是一個**合法的位元組值**(已 commit
    # 的 0-byte floor),用它當初始值會讓第一份空檔命中 dedupe 而跳過全部 shape 檢查。
    last_raw: bytes | None = None
    for commit in commits:
        if previous_commit is not None and not _git_ok(
            repo_root, "merge-base", "--is-ancestor", "--end-of-options",
            previous_commit, commit,
        ):
            errors.append(
                "durability anchor floor history is not a single ancestor chain"
            )
        try:
            raw = _git_bytes(repo_root, "show", "--end-of-options", f"{commit}:{path}")
        except (OSError, subprocess.CalledProcessError) as error:
            return _floor_reading(FLOOR_REJECTED, None, errors + [
                f"durability anchor floor revision is unreadable: {error}"
            ])
        previous_commit = commit
        # P1-3:shape 解析必須在 dedupe **之前**。反過來的話,任何與前一份逐位元組
        # 相同的 revision(含第一份對上哨兵)都會跳過 schema／GENESIS／遞增檢查。
        floor, shape_errors = _floor_shape_errors(raw, label=f"commit {commit[:12]}")
        if shape_errors or floor is None:
            return _floor_reading(FLOOR_REJECTED, None, errors + shape_errors)
        if raw == last_raw:
            # merge commit 原樣帶進同一份 floor:那不是一次新的推進,不參與序檢查。
            continue
        if revision_index == 0:
            # P1-4:鏈首必須是創世。舊版只擋「index≠0 再進 GENESIS_ARMED」,於是
            # orphan branch 上單一 commit 就能鑄出任意 ADVANCED/gen=N。
            # `floor_generation == 0` 由 `_floor_shape_errors` 的 GENESIS_ARMED 分支
            # 保證,不在此重複判——重複條件永遠殺不掉,只會製造假的覆蓋。
            if floor["state"] != "GENESIS_ARMED":
                errors.append(
                    "durability anchor floor history does not begin with its "
                    "GENESIS_ARMED commit"
                )
        elif floor["state"] == "GENESIS_ARMED":
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
        head_raw = _git_bytes(repo_root, "show", "--end-of-options", f"{at_commit}:{path}")
    except (OSError, subprocess.CalledProcessError) as error:
        return _floor_reading(FLOOR_REJECTED, None, errors + [
            f"durability anchor floor is unreadable at the reviewed commit: {error}"
        ])
    # 尾端 byte-for-byte:祖先鏈檢查為真時**不可孤立觸發**——`at_commit` 讀到的 blob
    # 必然等於最後一個觸碰該路徑的 commit 的 blob。E2 與 E4 獨立同意構造不出孤立
    # 違例,故本條屬 defense-in-depth;其可執行性由 seam 層測試(monkeypatch
    # `_git_bytes`)背書,不留成沉默的覆蓋債。
    if head_raw != last_raw:
        errors.append(
            "durability anchor floor at the reviewed commit differs byte-for-byte "
            "from its own history tail"
        )
    if previous_floor is None:
        # P1-3 的收口:走到這裡而沒有任何 revision 被採納,就是那個零錯誤 fail-open
        # 的形狀。永遠回非空 errors。
        errors.append(
            "durability anchor floor history yielded no admitted revision"
        )
    if errors:
        return _floor_reading(FLOOR_REJECTED, None, errors)
    unverified = _protected_ancestry_errors(repo_root, commits[-1])
    if unverified:
        return _floor_reading(FLOOR_UNVERIFIED, None, unverified)
    return _floor_reading(FLOOR_VERIFIED, previous_floor, [])


def read_committed_durability_anchor_floor(
    repo_root: Path, *, at_commit: Any
) -> CommittedFloorReading:
    """Read the floor from commit bytes; the working tree is never consulted."""

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
