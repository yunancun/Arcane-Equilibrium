"""Committed durability anchor floor: the code-owned, Git-read monotonicity pin.

§LW1 的 anchor 選言要求一個「外部」的 monotonic counter/append-only head。單靠
attestation 自報的 `previous_anchor_head_digest` 無法成立——那條鏈是自封閉的:
四個 digest 全部由 attestation 自己的欄位重算,驗證端從不與任何真實前手比對。

本模組把 receipt 已經釘在 git 上的 anchor 世代投影成一份 **code-owned 路徑**的
committed floor,並由驗證器自己以 `git show <commit>:<path>` 讀 **commit 物件的
位元組**(不是工作樹)。floor 不是新的信任源,也不帶簽章:它只提供**機械可偵測的
歷史性質**——`floor_history_errors` 的祖先鏈 + 嚴格遞增 + 單一創世檢查。

誠實邊界(2026-08-04 撤回上一版的過強宣稱;不得在註解或 PR 說明裡被寫回去):

- **本模組不提供 §LW1 意義下的外部性,一項都不提供。** 上一版本段落寫「改寫它需要
  第二組 capability(GitHub 寫入權 + PR + required checks)這件事實」——**該宣稱已
  撤回,而且已被證偽**:能以驗證器的 uid 寫 `.git` 的人,一條 `git update-ref` 就能
  改掉 `refs/remotes/origin/main`(本模組的測試 fixture 正是這樣建可達歷史的),
  完全不需要碰 GitHub。git 在這裡能證的只有 *tamper-evident*,**既不是 WORM,也不是
  「需要第二組 capability」**。
- 只有**相鄰世代**宣稱 hash 連結;非相鄰世代之間只宣稱單調遞增。中間條目的
  `entry_digest` 無原像可驗,替 gap 提供 link path 是假的安全性。**本模組不宣稱
  「hash chain 完整性已驗證」。**
- **`at_commit` 由被驗證者遞來**,`_PROTECTED_ANCESTOR_REFS` 也只是本地 ref;兩者
  都不構成外部性(見 `_PROTECTED_ANCESTOR_REFS` 上方的誠實邊界)。鏈尾不可達受保護
  ref 時本模組**不判 PASS 也不判 FAIL,而是判 `UNVERIFIED`**——那是 §LW1「同一
  writer 可 coherent rewrite ⇒ 只能得 `UNVERIFIED`」的處置,**不是** P0-1 已關閉的
  證明。任何投影都不得把本模組壓縮成「P0-1 closed」。
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Any, NamedTuple

from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _load_schema, canonical_digest, git_argv, git_subprocess_env,
)


LAUNCH_ID = "S2E-LW1-LW5"
DURABILITY_ANCHOR_FLOOR_SCHEMA = "s2e_durability_anchor_floor_v1"
GENESIS_WAVE = "W0-GENESIS"
# floor 的路徑由 LAUNCH_ID 導出,caller 永遠不能指定它;跨 launch 重放因此在路徑層先斷。
_FLOOR_REPO_PATH = (
    f"docs/execution_plan/ai_ml_landing/receipts/{LAUNCH_ID}/"
    "durability-anchor-floor-v1.json"
)
# 上界只用來擋病態歷史,不是效能參數。**E3-C 實測推翻上一版的 32**:舊註解只算了
# 「改動 floor 的 commit」,漏算 `--full-history` 會把**每一個與某個 parent 的 floor
# blob 不同的 merge** 也列出來。E3 實測合法的 6 次推進在 long-lived branch + 3 次
# back-merge 下列 31 筆(差一筆撞頂)、4 次下列 37 筆 ⇒ 硬 REJECTED 且無 override。
# E1 於 git 2.55 重測同一形狀:每一輪 (branch 推進 + merge 進 main + back-merge)
# 貢獻 1 個推進 + 2 個 merge,故 listed = advances + 2×back-merges(實測 n=0..8 全中)。
# 重新推導的上界:
#   (a) 真正改動 floor 的 commit ≤ 16(LW1-LW5 六次推進 + 創世 + 更正/重發餘裕);
#   (b) 每一次推進最多被 B 條並行 long-lived branch 各帶進 1 個 merge,取 B ≤ 15;
#   ⇒ 16 × (1 + 15) = 256。
# 每筆的成本是 1 次 `git show` + 1 次 `merge-base`(皆帶 timeout),故 256 仍有界。
MAX_FLOOR_HISTORY_COMMITS = 256
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
# 它只做一件事:把「遞一個 commit」提升為「同時偽造本機 remote-tracking 狀態」,
# 於是**意外與漂移**(未 merge、未 fetch、指錯 commit、CI shallow checkout)會得到
# 具名的 UNVERIFIED 而不是靜默 PASS。
# 2026-08-04 撤回:此處原本還寫著「在真實 CI／clone 上讓該 ref 由 fetch 決定、攻擊者
# 要改就得動 GitHub 那組 capability」。驗證器**無法自證自己跑在那種環境裡**,所以那
# 句話在代碼裡不是可執法的性質,只是一個假設;留著它會讓「git = 第二組 capability」
# 這個已撤回的宣稱從側門回來。
# 真正的外部性上界仍在 §LW1 說的「不同 owner/capability」,那需要驗證器不與被驗者
# 共用 uid;在受檢主機上執行的驗證器沒有辦法自證這件事(與 §5.3 的資訊論上界同型)。
_PROTECTED_ANCESTOR_REFS = ("refs/remotes/origin/main",)
# P1-2:`at_commit` 一路來自受驗 receipt 的 `source_head`／`reviewed_head`。git 的
# revision 位置在 `--` 之前,`--output=<path>` 這種單 token 參數會被當成選項吃掉——
# PM 於 git 2.55 實測 `git log ... "--output=victim.txt" -- .` 把既有檔案**截斷為
# 0 bytes** 且 exit 0。因此任何 git 呼叫**之前**先做逐字形狀驗證,不合格不進 subprocess。
# E2 F-04:Python 的 `$` 匹配「字串尾**或尾端換行之前**」,於是 `<40hex>\n` 曾經通過
# `^[0-9a-f]{40}$` 並真的進了 git argv(git 自己拒 ⇒ 當時 fail-closed,但註解與測試
# 宣稱的不變量是假的)。改用 `fullmatch` + `\Z`:`fullmatch` 是主防線,`\Z`(而非
# `$`)是縱深——日後若有人把呼叫改回 `.match`,尾端換行仍然會被拒。
_EXACT_COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")

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


class FloorVerdictObservation(NamedTuple):
    """一次 floor 判定的 typed 觀察:`label` + `verdict`。

    E3-B:`verdict` 原本在模組外零讀者——兩個呼叫點把 `REJECTED` 與 `UNVERIFIED` 壓成
    同一串無型別 errors,下游只能靠錯誤訊息裡的 `"UNVERIFIED: "` 子字串去猜。
    PM 2026-08-04 裁決:`UNVERIFIED` **仍然擋**(它不是 PASS,這點不變),但必須在
    typed 輸出裡分得開,下游才能區分「偽造的 floor 被拒(REJECTED)」與「未 merge
    因而誠實不可驗(UNVERIFIED)」。
    """

    label: str
    verdict: str


class AnchorGateObservations:
    """errors 之外的 typed 觀察通道(floor verdict + 本機 host identity 各一格)。

    刻意是一個具名載體而不是兩個裸 list:兩條觀察沿著同一條驗證路徑產生,分開傳會
    再度出現 E3-E 那種「只接了一半」的縫。`as_records()` 是給 CLI/receipt 序列化用的
    純資料投影——本通道**必須有真消費者**,不得再成為第二個 write-only 通道。

    **消費者邊界(E3-B;逐格具名,兩格成熟度不同,不得被一併宣稱為「有消費者」)**:

    - `floor_verdicts` 有兩個**序列化出口**,都是 stdout JSON 欄位:
      `agent_governance_s2e_launch_receipts` CLI(`transition-gate` 與 `validate`)
      與 `issue_s2e_launch_receipt` 回傳的 `launch_receipt_issuance_result_v1`,
      兩者的欄位名皆為 `anchor_gate_observations`。讀者因此能不解析錯誤字串就分辨
      「偽造/損壞的 floor 被拒(`REJECTED`)」與「未 merge/不可達因而誠實不可驗
      (`UNVERIFIED`)」。
      **E2 round-4 R4-9 更正(2026-08-06)**:本段原寫「程式消費者有兩處」,而那兩處
      都只是把值序列化出去,**沒有任何程式對 `UNVERIFIED` 與 `REJECTED` 分支**。
      同一份 dict 裡的 `host_identity` 被誠實記為「無程式消費者」,兩格待遇不一致,
      而不一致的那一半是寬鬆的那一半。此處統一用「序列化出口」,程式消費者兩格皆
      **為零**;`floor_verdicts` 比 `host_identity` 多的只是 typed 形狀與具名出口。
    - **gate 行為完全由 `errors` 決定**:本通道不放行、不阻擋、不改變任何 status。
      `UNVERIFIED` 照樣擋——它不是 PASS,typed 化只讓它「發得出來」,不讓它通過。
    - `host_identity` 至今**仍無程式消費者**(E2 F-07),僅供 receipt/人工審閱。
    """

    def __init__(self) -> None:
        self.host_identity: list[str] = []
        self.floor_verdicts: list[FloorVerdictObservation] = []

    def as_records(self) -> dict[str, Any]:
        # verdict 以 `(label, verdict)` 去重:一次 issuance 會沿兩條路徑重跑同一組
        # floor 檢查,重複條目只是噪音。去重刻意做在**配對**上而非 label 上——同一
        # label 出現兩個不同 verdict 是真矛盾,那種情況仍留兩筆,不會被壓平掉。
        return {
            "host_identity": sorted(set(self.host_identity)),
            "floor_verdicts": [
                {"label": label, "verdict": verdict}
                for label, verdict in sorted({
                    (item.label, item.verdict) for item in self.floor_verdicts
                })
            ],
        }


def host_identity_sink(
    observations: AnchorGateObservations | None,
) -> list[str] | None:
    """把 typed 通道降解成 `validate_s2e_durability_anchor_attestation` 要的 `list[str]`。

    `None` 保持 `None`(該函式以 `is not None` 判斷要不要記錄),因此「不傳通道」與
    「傳了空通道」語義不同,不會被混為一談。
    """

    return None if observations is None else observations.host_identity


def floor_gate_errors(
    reading: CommittedFloorReading,
    *,
    label: str,
    observations: AnchorGateObservations | None = None,
) -> list[str]:
    """把一次 reading 轉成呼叫端要 extend 的 errors,並保證非 VERIFIED 必留痕。

    這是 P1-3 在呼叫端的那一半:`_floor_reading` 保證模組內不可能產出無理由的
    非 VERIFIED,本函式保證即使有人日後繞過該建構入口,呼叫端仍拿得到非空 errors。
    `observations` 則是 E3-B 的那一半:verdict 在**產生 errors 的同一處**被記成
    typed 事實,不需要下游解析字串。
    """

    errors = [f"{label}: {error}" for error in reading.errors]
    if reading.verdict != FLOOR_VERIFIED and not errors:
        errors.append(f"{label}: verdict {reading.verdict} carried no stated reason")
    if observations is not None:
        observations.floor_verdicts.append(
            FloorVerdictObservation(label, reading.verdict)
        )
    return errors


def durability_anchor_floor_repo_path() -> str:
    """Return the code-owned repository path of the committed floor."""

    return _FLOOR_REPO_PATH


def durability_anchor_floor_digest(floor: dict[str, Any]) -> str:
    """Canonical self-digest over every field except the digest itself."""

    return canonical_digest({
        key: value for key, value in floor.items() if key != "floor_digest"
    })


# E3-D:同家族 `schema_core` 的每一支 git 呼叫都帶 `timeout=`(60/30/180),本模組
# 曾是唯一例外。E3 實測 `--filter=blob:none` 的 promisor clone **不是 shallow**,舊版
# `_object_store_errors` 會放行,接著 `git show <commit>:<path>` 會**走網路**向
# promisor remote 抓 blob;配合阻塞 transport 實測 25s 仍未止且無上界。timeout 是
# 第二道防線,第一道是 `_object_store_errors` 直接拒掉 promisor(唯一的網路路徑)。
_GIT_READ_TIMEOUT_SECONDS = 60
_GIT_PROBE_TIMEOUT_SECONDS = 30
# `subprocess.TimeoutExpired` **不是** `CalledProcessError` 的子類;兩者的共同父類是
# `SubprocessError`。舊的 `except (OSError, CalledProcessError)` 若配上 timeout 會讓
# 逾時裸逸出驗證函式,因此本模組一律捕捉 `SubprocessError`。
_GIT_FAILURES = (OSError, ValueError, subprocess.SubprocessError)


def _git_bytes(repo_root: Path, *args: str) -> bytes:
    # P1-6:`env=` 白名單。沒有它,ambient `GIT_DIR` 會蓋過 `-C`,驗證器讀到的是
    # 攻擊者 repo 的 floor 而且零錯誤(E3 實測)。
    # E3-A:argv[0] 與 `PATH` 皆由 `git_argv`/`git_subprocess_env` 從 code-owned
    # 常數導出,ambient `PATH` 不參與 git 二進位的解析。
    return subprocess.run(
        git_argv(repo_root, *args),
        check=True,
        capture_output=True,
        env=git_subprocess_env(),
        timeout=_GIT_READ_TIMEOUT_SECONDS,
    ).stdout


def _git_ok(repo_root: Path, *args: str) -> bool:
    """只問離開碼的 git 呼叫(祖先判定、ref 解析);同樣走白名單環境。

    逾時/無法執行一律回 `False`(fail-closed):呼叫端只用它做「是不是祖先/解析得出
    來」的肯定判定,回 False 只會讓判定更嚴,不會放行。
    """

    try:
        return subprocess.run(
            git_argv(repo_root, *args),
            capture_output=True,
            env=git_subprocess_env(),
            timeout=_GIT_PROBE_TIMEOUT_SECONDS,
        ).returncode == 0
    except _GIT_FAILURES:
        return False


def _object_store_errors(repo_root: Path) -> list[str]:
    """P1-5:非完整 object store 會讓整組歷史檢查靜默變成 no-op。

    E2 實測:同一份被 rollback 的 repo,full clone 判紅、`depth=1` shallow clone
    回 `(gen=2, errors=[])`——因為被 rollback 的那段歷史根本不在錐體裡。replace ref
    則可以把任一 commit 的內容整個換掉。這是**驗證器自身環境不合格**,不是被驗對象
    的性質,所以判 REJECTED(拒絕在這個環境裡跑)而不是 UNVERIFIED。

    E2 F-01(E1 於 git 2.55 實測裁定;E2 對、E3 錯):`<git-common-dir>/info/grafts`
    是 replace ref 的前身、同一種 object-rewrite 機制,而舊版只查 replace ref。
    兩種構造實測結果不同:
    - **E2 形(危險)**:`<rollback-commit> <genesis-commit>` 把回退 commit 的 parent
      直接接到創世,中間那筆 gen=2 從 `--full-history` 走訪裡消失 ⇒ 同一份被 rollback
      的 repo 由 `REJECTED`(generation is not strictly increasing)翻成 **`VERIFIED
      gen=1`**,而且照樣通過受保護 ref 檢查。
    - **E3 形(無害)**:只把創世 commit 變成 root,不改動 floor 觸碰序 ⇒ 仍 `REJECTED`。
    因此修法必須擋的是 grafts **檔案存在**本身,不是某一種特定寫法。
    `GIT_GRAFT_FILE` 這條 env 路徑早已被 `git_subprocess_env` 的白名單堵住,git 也沒有
    對應的 config key,故「檔案不存在」即為完整判定。

    E3-D:promisor(partial)clone 一併拒。它 `--is-shallow-repository` 回 false,
    卻會讓 `git show <commit>:<path>` 靜默走網路去抓缺失 blob——那是本家族唯一的
    runtime effect 來源,與設計 §8.4「全部是純驗證函式」直接衝突。
    """

    try:
        shallow = _git_bytes(repo_root, "rev-parse", "--is-shallow-repository")
        replaced = _git_bytes(
            repo_root, "for-each-ref", "--format=%(refname)", "refs/replace/"
        )
        common = _git_bytes(repo_root, "rev-parse", "--git-common-dir")
    except _GIT_FAILURES as error:
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
    if _grafts_file_present(repo_root, common):
        errors.append(
            "durability anchor floor cannot be read from a repository that "
            "rewrites commit parentage through a grafts file"
        )
    if _git_ok(
        repo_root, "config", "--get-regexp",
        r"^(remote\..*\.(promisor|partialclonefilter)|extensions\.partialclone)$",
    ):
        errors.append(
            "durability anchor floor cannot be read from a promisor partial clone"
        )
    return errors


def _grafts_file_present(repo_root: Path, common_dir: bytes) -> bool:
    """`<git-common-dir>/info/grafts` 是否存在(路徑解析失敗一律當成存在:fail-closed)。"""

    try:
        raw = common_dir.decode("utf-8").strip()
    except UnicodeDecodeError:
        return True
    if not raw:
        return True
    common = Path(raw)
    if not common.is_absolute():
        common = Path(repo_root) / common
    try:
        return (common / "info" / "grafts").exists()
    except OSError:
        return True


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
        # E2 F-02:舊字串寫「so the floor cannot be shown to require a second
        # capability」,隱含「是祖先時就證明了需要第二組 capability」——那正是本模組
        # 已撤回的宣稱(module docstring)。改寫成只講它真正能證的那件事。
        return [
            "UNVERIFIED: no code-owned protected ref resolves in this repository, "
            "so the floor's history tail cannot be pinned to any code-owned ref"
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

    if not isinstance(at_commit, str) or not _EXACT_COMMIT_PATTERN.fullmatch(
        at_commit
    ):
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
    except _GIT_FAILURES as error:
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
        except _GIT_FAILURES as error:
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
    except _GIT_FAILURES as error:
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


def next_floor_projection(issued_receipt: Any, bundle: Any) -> dict[str, Any] | None:
    """§3.3(d):純投影,供 operator/E1 在同一個 PR 內 commit 下一份 floor。

    驗證器永遠不寫檔;沒有 issued receipt 就沒有可推進的 floor。前置條件放在投影
    函式自己身上,而不是留在某一個呼叫點——第二個呼叫端因此不可能忘記它。
    """

    if not isinstance(issued_receipt, dict) or not isinstance(bundle, dict):
        return None
    return next_durability_anchor_floor(issued_receipt, bundle)
