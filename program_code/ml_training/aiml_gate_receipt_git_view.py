"""驗證面取 repo 事實的唯一底層面:code-owned object view(S2E round-5 拆分波)。

`aiml_gate_receipt_schema_core` 的**下層**純葉模組:只做檔案系統與 `tempfile` 的事,
top-level 不匯入本家族任何模組(schema_core 反向匯入並 re-export,單向、無環)。獨立
成檔是 operator 於 2026-08-08 授權的拆分波:它是一條信任邊界,值得被單獨審,而且併回
`schema_core` 會越過 2000 行治理上限。本葉進入 engine-scanner 的 runtime import 閉包,
故同波登記於五個 wave-exit digest 承載面(`application_bundle_runtime_closure_v1.json`
與 W0/W2/W3/W5 四份 owned-path);漏登記會讓 `owned_path_diff_digest` 的覆蓋面靜默收窄。

問題形狀與兩條已證偽的出口,逐字記在 `schema_core.git_argv` 的 docstring;設計全文在
`docs/execution_plan/ai_ml_landing/design/S2E-round5-code-owned-object-view.md`。

## 這個 view 擋住什麼

舊拓撲 `git -C <被驗者>` 讓 git **discover** 外人的目錄為 repository,於是它的
`.git/config`(`core.fsmonitor`、`filter.<drv>.clean`…)、hook、`.gitattributes` 與工作樹
全部進場,而 discover 正是 ownership 檢查發生的地方。本 view 反過來:驗證器自建一個
bare repo,並在其中**物化**一個只含物件的 object store。

round-5 的 E3 對抗複核推翻了初版的三個前提,三條都在本檔收口:

- **P0-A**:`.git` 檔裡的 `gitdir:`、`commondir`、`objects` symlink 全都由被驗者書寫,
  而初版只跟隨、不驗。root 驗證器因此可被指向任何它讀得到的 repo(E3 實測讀出 victim
  repo 的位元組),連 consume-once ledger 的位置都由被驗者選。git 的 ownership 檢查本來
  是那道意外屏障;移除它就必須自己補上。`subject_layout` 現在把三者都釘到
  **`repo_root` 自己的 owner**,並要求 gitdir 與 commondir 符合 git 的 worktree 佈局
  不變式(`<commondir>/worktrees/<name>`)。
- **P0-B**:初版用 `objects/info/alternates` 掛被驗者的 store,而「巢狀 alternates 一律
  拒」是 check-then-use——E3 的樸素競爭器 400 次試驗 leaked 134。
- **P0-C**:alternate **不是**純內容定址面。git 也從那裡載入
  `objects/info/commit-graph`、`commit-graphs/*`、`pack/multi-pack-index`、`*.bitmap`,
  而那些是攻擊者撰寫、未對物件複驗的。E3 實測改 4 個位元組即可讓
  `log --full-history` 少走一筆 floor revision,而所有周邊不變量照樣綠。

B 與 C 有共同的結構解,即 `_materialize_object_store`:view 的 `objects/` 由本模組建立,
裡面**只有** loose-object fanout 目錄與 `pack/*.{pack,idx}` 的 symlink。沒有 `info/`
(⇒ 沒有 alternates、沒有 commit-graph)、沒有 `multi-pack-index`、沒有 `*.bitmap`。
被驗者寫不進 view 目錄本身(0700、驗證器所有),所以**那兩個具體的面**不存在。
E2 與 E3 round-6 各自實測確認:alternates 競爭器 400 次 leaked 0(原 134),帶偽造
commit-graph 的 repo 經 view 走訪回誠實歷史。B 與 C 這兩條向量確實關掉了。

**round-6 曾在此寫過一句「剩下能被替換的只有物件位元組本身,而那是內容定址的:git 讀出來
會複驗 sha」——那句是假的,永久撤回,不得寫回去。** E2 與 E3 於 git 2.55.0 各自實證:
`cat-file -p` / `--batch` / `show <rev>:<path>` 這條 blob 讀取路徑**不**複驗 sha
(只有 `fsck`/`verify-pack` 會,而本家族兩者都不跑),loose 與 packed 兩種形式都能讓
一個 object id 回出攻擊者選定的位元組。

round-7 加了兩條緩解,round-8 的第三輪 E2/E3 又各自把它們的**強版本**推翻。以下是
收窄後、代碼真的背得起來的宣稱:

- **來源**:`_materialize_object_store` 逐**物件**物化,每檔連結時驗 `S_ISREG` 與 owner。
  這關掉了兩條具體向量(建構時就存在的 in-fanout symlink;列舉後**新建**的物件)。
  **但 view 存的是路徑 symlink,git 在讀取時才解參考**,所以 `S_ISREG`/owner 是
  check-then-use:已連結物件的內容與型別在整個 view 生命週期內仍是活的,連結後把該檔
  換成指向別的 store 的 symlink 仍然讀得到(E3 racer 300 次中 21 次)。
- **內容**:`commit_blob_bytes` 對 `cat-file --batch` 標頭的 object id 重算 sha1。
  這綁的是 **`payload ↔ oid`**,**不是 `oid ↔ path`** —— 那個 oid 是 git 走 **tree**
  解出來的,而 tree 物件從不被複驗。改寫 tree 即可讓標頭指向攻擊者挑的 blob,而該 blob
  完美地雜湊成自己的 id(E2/E3 各自無競爭復現;E3 據此讓 floor gate 回 `VERIFIED`、
  `floor_generation = 9`、`errors: []`)。commit 物件同樣未驗。

**因此本模組的誠實宣稱範圍是:**

1. **已關且經復現確認**:R4-1 那條「以驗證器身分執行任意程式」。E3 把
   `core.fsmonitor`/`filter.*.clean`/`diff.*.textconv`/`core.hooksPath`/`core.pager`/
   `core.editor`/`uploadpack.packObjectsHook`/`include.path` 全部武裝後實測零命中,而事實
   照樣取得。這是本輪真正買到的東西。
2. **tamper-evident,對「意外損壞」有效**:物件位元組與 object id 不符會被擋
   (損壞、gc 讀到一半、store 被改寫)。
3. **對敵意 repo owner 不成立**:被驗者能讓本家族證明他挑的位元組。
   **§LW1 意義下的外部性一項都不提供**,任何投影都不得把本模組讀成「P0-1 已關」或
   「receipt 可抗同一 writer 改寫」。要達到那個級別需要驗**整條解析鏈**(commit → tree
   → blob)或對 view 跑 `fsck`/`verify-pack`,並以 hardlink/copy 而非 symlink 物化——
   那是「一次驗證一個 view」的重構,尚未進行。見設計檔 §6。

sha256 object format 顯式拒(`STORE_UNSUPPORTED_OBJECT_FORMAT`):sha1 重算對它恆假,
而恆假的完整性檢查比沒有更糟。
"""

from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any, Iterator


_OBJECT_VIEW_MODE = 0o700
_OBJECT_VIEW_FILE_MODE = 0o600
_OBJECT_VIEW_CONFIG = (
    "[core]\n"
    "\trepositoryformatversion = 0\n"
    "\tbare = true\n"
    "\tlogallrefupdates = false\n"
)
# 刻意是一個不存在的分支名:`git -C <view> rev-parse --verify HEAD` 必須 rc≠0。
# E1 於 git 2.55 實測的陷阱:**裸** `rev-parse HEAD` 解不出來時回 `rc=0` 並原樣印回
# `HEAD`(fail-open),只有 `--verify` 才 `rc=128`;故名字解析一律 `--verify`,或先由
# `read_subject_ref` 換成 40-hex。
_OBJECT_VIEW_HEAD = "ref: refs/heads/code-owned-object-view-has-no-refs\n"

MAX_REF_FILE_BYTES = 4096
MAX_PACKED_REFS_BYTES = 4 * 1024 * 1024
MAX_SUBJECT_CONFIG_BYTES = 1024 * 1024
_MAX_SYMREF_DEPTH = 8
_MAX_REPLACE_REF_SCAN_ENTRIES = 4096
# round-8:這個常數在 round-6 數的是 **fanout 目錄**(≤256),round-7 改成數 **物件**
# 卻沒跟著改,於是 4096 掉進 git 自己 `gc.auto` 預設 6700 以下——一個 git 刻意容忍的
# 正常 repo(E2 實測 5003 個 loose 物件)會被拒,而且 `subject_object_store_findings`
# 還回 `[]`(只有 `git_failure_detail` 說得出原因)。上界改成遠高於 `gc.auto`;
# 「超上界要成為 typed finding 而不是只在 failure_detail 裡」仍未收,見設計檔 §6。
_MAX_VIEW_OBJECT_LINKS = 200_000
_REF_NAME_PATTERN = re.compile(r"\Arefs/[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_FANOUT_PATTERN = re.compile(r"\A[0-9a-f]{2}\Z")
# 只連這兩種副檔名。`.rev`/`.bitmap`/`multi-pack-index` 都只是加速結構,git 沒有它們
# 一樣能從 `.idx` 走;而 `.bitmap`/midx 正是 P0-C 的攻擊面,`.promisor` 則會讓 git 認為
# 缺物件可以去網路抓。
_LINKED_PACK_SUFFIXES = (".pack", ".idx")

# `subject_object_store_findings` 的 typed 標記:只描述被驗者 gitdir 的**檔案系統
# 事實**,不下任何 receipt 判定;呼叫端各自映射成自己的領域訊息。
STORE_UNREADABLE = "UNREADABLE"
STORE_SHALLOW = "SHALLOW"
STORE_GRAFTS = "GRAFTS"
STORE_REPLACE_REFS = "REPLACE_REFS"
STORE_PROMISOR = "PROMISOR"
STORE_UNSUPPORTED_REF_BACKEND = "UNSUPPORTED_REF_BACKEND"
STORE_NESTED_ALTERNATES = "NESTED_ALTERNATES"
STORE_INDETERMINATE = "INDETERMINATE"
STORE_UNSUPPORTED_OBJECT_FORMAT = "UNSUPPORTED_OBJECT_FORMAT"

# 只認 git 真正的鍵形(`remote.<n>.promisor`、`remote.<n>.partialclonefilter`、
# `extensions.partialclone` 在 INI 裡就是行首這三個鍵),不做整檔子字串掃描——後者會被
# remote 名稱或 URL 裡的巧合字樣誤觸。這一路只能讓判定更嚴,永遠不能取得肯定事實。
_PROMISOR_CONFIG_KEY = re.compile(
    r"(?im)^[ \t]*(promisor|partialclonefilter|partialclone)[ \t]*="
)
# round-7:`commit_blob_bytes` 用 sha1 對 object id 重算(P0-1)。sha256 object format
# 的 repo 那個比對會恆假,而恆假的完整性檢查比沒有更糟——它看起來像在保護。顯式拒。
# view 的 config 寫死 `repositoryformatversion = 0`,sha256 本來也讀不了,所以這條只是
# 把既有的隱性失敗換成具名理由。
_SHA256_OBJECT_FORMAT = re.compile(r"(?im)^[ \t]*objectformat[ \t]*=[ \t]*sha256")


def read_bounded(path: Path, limit: int) -> bytes:
    """讀一個**常規檔**的前 `limit` 位元組;symlink/非常規檔/超限一律 `OSError`。

    `O_NOFOLLOW` 擋最後一節的 symlink。`O_NONBLOCK` 同樣必要(E3 round-5 實測):它不擋
    FIFO,而 `S_ISREG` 的拒絕在 open **之後**,故 `mkfifo .git/HEAD` 能讓驗證器永遠卡在
    open——in-process 阻塞,家族裡每個 subprocess `timeout=` 都救不到。
    """

    import os
    import stat as stat_module

    flags = (
        os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        info = os.fstat(descriptor)
        if not stat_module.S_ISREG(info.st_mode):
            raise OSError(f"{path} is not a regular file")
        if info.st_size > limit:
            raise OSError(f"{path} exceeds its admitted size")
        payload = bytearray()
        while len(payload) < limit:
            chunk = os.read(descriptor, limit - len(payload))
            if not chunk:
                break
            payload.extend(chunk)
        return bytes(payload)
    finally:
        os.close(descriptor)


def _real_directory(path: Path, *, owner: int, label: str) -> Path:
    """`path` 必須是一個**真目錄**(不是 symlink)且屬於 `owner`;否則 `OSError`。"""

    import os
    import stat as stat_module

    info = os.lstat(path)
    if not stat_module.S_ISDIR(info.st_mode):
        raise OSError(f"{label} is not a directory: {path}")
    if info.st_uid != owner:
        raise OSError(
            f"{label} is owned by uid {info.st_uid}, not by the subject repository's "
            f"owner uid {owner}: {path}"
        )
    return path


class SubjectLayout(Any if False else object):  # noqa: E721 - 純資料載體
    """被驗者的 repo 佈局,三個路徑都已 owner-pin 並過佈局不變式(P0-A)。"""

    __slots__ = ("root", "git_dir", "common_dir", "objects", "owner")

    def __init__(
        self, root: Path, git_dir: Path, common_dir: Path, objects: Path, owner: int
    ) -> None:
        self.root = root
        self.git_dir = git_dir
        self.common_dir = common_dir
        self.objects = objects
        self.owner = owner


def subject_layout(repo_root: Path | str) -> SubjectLayout:
    """解析並**釘住**被驗者的 gitdir / commondir / objects。

    P0-A(E3 round-5,CONFIRMED):`.git` 檔的 `gitdir:` 指標、`commondir` 指標與
    `objects` symlink 全部由被驗者書寫。初版只跟隨、不驗,於是 root 驗證器可被指向任何
    它讀得到的路徑——E3 用 `gitdir: <victim>/.git` 實測讀出了 victim repo 的位元組,
    並讓 consume-once ledger(`aiml_gate_receipt_s2e_consumption` 由 commondir 導出)
    整個換位置。重導向本身不是新的(`git rev-parse --git-common-dir` 一向跟隨同樣的
    指標),**新的是 git 的 ownership 檢查原本是那道意外屏障,而本輪刻意移除了它**。

    這裡補上的替代是 **owner pin**:gitdir/commondir/objects 都必須屬於 `repo_root`
    自己的 owner(不是 euid——驗證器多半是 root,被驗者不是),`objects` 還必須是
    commondir 底下的**真**子目錄而非 symlink。被驗者因此只能指向他本來就讀得到的東西。
    E2/E3 round-6 各自實測三條跨 uid 向量(`gitdir:`、`commondir`、`objects` symlink)
    皆被拒。

    **round-6 撤回。** 初版還加了第二條「linked-worktree 回指不變式」(要求
    `<gitdir>/gitdir` 指回被驗者的 `.git`),並宣稱它能擋住同 uid 兩個 repo 之間的重指。
    **那個推論是空的**:owner pin 允許的目標恰好是被驗者所有的目錄,所以他對任何通過
    pin 的目標都寫得了回指——E2 與 E3 各以一行復現。它唯一擋到的是「忘了寫回指」的
    天真重指,代價卻是**拒絕兩種 git 接受的合法佈局**(`--separate-git-dir` 與 submodule
    工作樹都用 `.git` 指標檔而沒有回指),而且錯誤被報成「object store is unreadable」。
    買不到安全又擋掉合法輸入,所以整條移除。

    **誠實邊界(未收)**:同 uid 的重指**沒有被擋住**——被驗者可以把 commondir 指到另一個
    自己的 repo,拿到一份空的 consume-once ledger,甚至用一個只含 `objects/` 與
    `worktrees/w/` 的合成目錄。要收它需要把 ledger 綁到 caller 選不了的身分。另外 owner
    是從 realpath 後的 `repo_root` 自行導出的,所以對「連 `repo_root` 路徑本身都被重指」
    的情形自我一致、偵測不到——理想上該由 producer 傳入預期 owner uid。見設計檔 §6。
    """

    import os
    import stat as stat_module

    root = Path(os.path.realpath(str(repo_root)))
    owner = os.lstat(root).st_uid
    marker = root / ".git"
    try:
        info: Any = marker.lstat()
    except OSError:
        info = None
    if info is not None and stat_module.S_ISDIR(info.st_mode):
        git_dir = _real_directory(marker, owner=owner, label="subject gitdir")
    elif info is not None and stat_module.S_ISREG(info.st_mode):
        text = read_bounded(marker, MAX_REF_FILE_BYTES).decode("utf-8", "replace")
        head, separator, tail = text.partition("gitdir:")
        if head.strip() or not separator:
            raise OSError(f"{marker} is not a valid gitdir pointer")
        # git 只讀指標檔的第一行;整檔 strip 會把多行內容黏成一個含換行的路徑。
        target = Path(tail.splitlines()[0].strip() if tail.strip() else "")
        if not target.is_absolute():
            target = root / target
        git_dir = _real_directory(
            Path(os.path.realpath(str(target))), owner=owner, label="subject gitdir"
        )
    elif (root / "objects").is_dir() and (root / "HEAD").is_file():
        git_dir = _real_directory(root, owner=owner, label="subject gitdir")
    else:
        # 這兩支必須留著:少了它們,不是 repo 的路徑會走到下面的 `git_dir` 而拋
        # `UnboundLocalError`——那**不是** `OSError`,呼叫端的 fail-closed 接不到,
        # 於是「讀不到」變成 crash。round-6 移除回指檢查時真的把它們一起刪掉了,
        # `test_owned_path_projection_is_fail_closed_without_a_resolvable_commit` 抓到。
        raise OSError(f"{root} is not a Git repository this view can read")
    pointer = git_dir / "commondir"
    common_dir = git_dir
    if pointer.is_file():
        raw = read_bounded(pointer, MAX_REF_FILE_BYTES).decode("utf-8", "replace")
        first = raw.splitlines()[0].strip() if raw.strip() else ""
        if first:
            candidate = Path(first)
            if not candidate.is_absolute():
                candidate = git_dir / candidate
            common_dir = _real_directory(
                Path(os.path.realpath(str(candidate))),
                owner=owner,
                label="subject git common dir",
            )
    if common_dir != git_dir and (
        git_dir.parent.name != "worktrees" or git_dir.parent.parent != common_dir
    ):
        raise OSError(
            "subject gitdir is not a linked worktree of its own common dir: "
            f"{git_dir} vs {common_dir}"
        )
    objects = _real_directory(
        common_dir / "objects", owner=owner, label="subject object store"
    )
    return SubjectLayout(root, git_dir, common_dir, objects, owner)


def subject_git_dir(repo_root: Path | str) -> Path:
    """被驗者的 gitdir(已 owner-pin;見 `subject_layout`)。"""

    return subject_layout(repo_root).git_dir


def subject_common_dir(repo_root: Path | str) -> Path:
    """`<git-common-dir>`,取自**唯一一次**已驗證的 `subject_layout` 解析。

    P0-3(E3 round-6,CONFIRMED):本函式原本收 `git_dir` 並**重讀一次**
    `<gitdir>/commondir`——同一個被驗者可寫的檔被讀兩次,第二次完全不驗(無 owner pin、
    無佈局不變式)。`s2e_consumption._git_common_dir` 正是
    `subject_common_dir(subject_git_dir(repo_root))` 這個組合,於是被驗者只要在兩次讀取
    之間改寫 `commondir`,就能把 consume-once ledger 的 `state_path`/`lock_path` 指到
    **任意**目錄(E3 racer 3000 次:relocated 555)。帳本三個檔都不存在時 `read()` 回
    `_empty_ledger()` ⇒ 重放繞過,而且 `_atomic_write`/`_open_lock` 會讓驗證器在攻擊者
    指定的目錄裡建檔。目標不受 owner pin 約束,因為第二次讀取根本不驗。

    改成收 `repo_root` 並回 `subject_layout(repo_root).common_dir`:全程只有一次讀取,
    而且是驗過的那一次。
    """

    return subject_layout(repo_root).common_dir


def _verify_private_directory(path: Path) -> None:
    """`path` 自身與每一層祖先都不得被本行程以外的身分改寫。

    mkdtemp 的目錄是 0700 且原子建立,但它的**位置**來自 ambient `TMPDIR`。若 `TMPDIR`
    由攻擊者所有,他能 rename/刪掉 view 換上自己的 ⇒ view 的內容在建立與使用之間被換掉。
    故祖先只能由 root 或本 uid 所有,group/other 可寫時必須帶 sticky(`/tmp` 的 1777)。
    """

    import os
    import stat as stat_module

    euid = os.geteuid()
    info = os.lstat(path)
    if (
        not stat_module.S_ISDIR(info.st_mode)
        or info.st_uid != euid
        or stat_module.S_IMODE(info.st_mode) != _OBJECT_VIEW_MODE
    ):
        raise OSError(f"{path} is not a private directory owned by this process")
    current = path.parent
    while True:
        ancestor = os.lstat(current)
        if not stat_module.S_ISDIR(ancestor.st_mode):
            raise OSError(f"{current} is not a directory")
        if ancestor.st_uid not in (0, euid):
            raise OSError(f"{current} is owned by an untrusted uid")
        writable = ancestor.st_mode & (stat_module.S_IWGRP | stat_module.S_IWOTH)
        if writable and not ancestor.st_mode & stat_module.S_ISVTX:
            raise OSError(f"{current} is group/other writable without the sticky bit")
        parent = current.parent
        if parent == current:
            return
        current = parent


def _write_view_file(path: Path, payload: str) -> None:
    import os

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, _OBJECT_VIEW_FILE_MODE)
    try:
        os.write(descriptor, payload.encode("utf-8"))
    finally:
        os.close(descriptor)


def _materialize_object_store(objects: Path, target: Path, *, owner: int) -> None:
    """在 view 內建一個**只含物件**的 store(P0-B / P0-C 的共同結構解)。

    `target` 由本模組建立、驗證器所有、被驗者寫不進去,裡面只有:

    - 每個 loose-object fanout 目錄(`objects/[0-9a-f]{2}`)的 symlink;
    - `objects/pack/*.{pack,idx}` 的 symlink。

    刻意**沒有**的東西才是重點:沒有 `info/`(⇒ 沒有 `alternates`、沒有 `commit-graph`、
    沒有 `commit-graphs/`)、沒有 `multi-pack-index`、沒有 `*.bitmap`、沒有 `*.promisor`。
    初版把被驗者的 `objects/` 整個以 alternates 掛上去,於是:
    (a) 「巢狀 alternates 一律拒」是 check-then-use,E3 的樸素競爭器 400 次 leaked 134;
    (b) commit-graph / midx / bitmap 會被 git 載入且**不對物件複驗**,E3 實測改 4 個
    位元組就能讓 `log --full-history` 少走一筆 floor revision,而 `_object_store_errors`
    回 `[]`、`merge-base --is-ancestor` 仍 True、`git commit-graph verify` 也 rc=0。
    物化之後這兩個面在 view 裡**不存在**,不是「被檢查掉」——沒有窗口可競爭。

    逐**物件**物化:view 內的 fanout 是真目錄,裡面逐檔 symlink,每檔連結時驗 `S_ISREG`
    (拒 symlink)且驗 owner。這關掉 round-6 的兩條具體向量——建構時就存在的 in-fanout
    symlink,以及列舉後**新建**的物件(後者靠預建 256 個空 fanout 也拿不到)。實測 216 個
    loose 物件 +3 個 pack 的 repo,一次 view 約 30 ms。

    **誠實邊界(round-8 收窄,不得再寫成「真正的快照語義」)。** 這裡連的是**路徑**
    symlink,git 在讀取時才解參考,所以 `S_ISREG` 與 owner 是 check-then-use:只有**名字
    集合**是快照,已連結物件的**內容與型別**在整個 view 生命週期內都還是活的。連結通過
    檢查之後把該檔換成指向別的 store 的 symlink,仍然讀得到(E3 racer 300 次中 21 次;
    E2 另給出視窗內的確定性交換)。要真正定住需要 hardlink/copy 而非 symlink,屬未進行的
    「一次驗證一個 view」重構。
    """

    import os
    import stat as stat_module

    target.mkdir()
    linked = 0
    with os.scandir(objects) as fanouts:
        for fanout in sorted(fanouts, key=lambda item: item.name):
            if _FANOUT_PATTERN.fullmatch(fanout.name) is None:
                continue
            if not stat_module.S_ISDIR(fanout.stat(follow_symlinks=False).st_mode):
                # fanout 位置放 symlink 是被驗者在重指物件來源:略過,缺物件 fail-closed。
                continue
            mirrored = target / fanout.name
            mirrored.mkdir()
            with os.scandir(fanout.path) as loose:
                for entry in loose:
                    info = entry.stat(follow_symlinks=False)
                    if not stat_module.S_ISREG(info.st_mode) or info.st_uid != owner:
                        continue
                    linked += 1
                    if linked > _MAX_VIEW_OBJECT_LINKS:
                        raise OSError(
                            "subject object store exceeds its admitted entry count"
                        )
                    os.symlink(entry.path, mirrored / entry.name)
    pack_source = objects / "pack"
    try:
        pack_info = os.lstat(pack_source)
    except OSError:
        return
    if not stat_module.S_ISDIR(pack_info.st_mode):
        return
    pack_target = target / "pack"
    pack_target.mkdir()
    with os.scandir(pack_source) as entries:
        for entry in entries:
            if not entry.name.endswith(_LINKED_PACK_SUFFIXES):
                continue
            info = entry.stat(follow_symlinks=False)
            if not stat_module.S_ISREG(info.st_mode) or info.st_uid != owner:
                continue
            linked += 1
            if linked > _MAX_VIEW_OBJECT_LINKS:
                raise OSError("subject object store exceeds its admitted entry count")
            os.symlink(entry.path, pack_target / entry.name)


@contextlib.contextmanager
def code_owned_object_view(repo_root: Path | str) -> Iterator[Path]:
    """yield 一個 code-owned bare repo 的路徑,內含被驗者物件的物化 store。

    本家族的驗證面只把這個路徑交給 `git_argv`(generation 面另有
    `git_own_checkout_guard`;`agent_governance_s2e_lw1_action_packet` 仍是未收的殘留,
    見設計檔 §5)。目錄由本行程建立、本 uid 所有、0700、祖先鏈逐層驗過;`config` 逐位
    元組由代碼寫出(無 remote、無 fsmonitor、無 filter driver);無 `hooks/`、
    `refs/` 全空;無工作樹(⇒ `git status` 結構上跑不起來)。object store 由
    `_materialize_object_store` 物化,不掛被驗者的目錄。每次呼叫建一個:無快取、無
    module 級可變狀態,故無跨呼叫污染與可變單例。
    """

    import os
    import shutil
    import tempfile

    layout = subject_layout(repo_root)
    view = Path(os.path.realpath(tempfile.mkdtemp(prefix="s2e-object-view-")))
    try:
        _verify_private_directory(view)
        _materialize_object_store(layout.objects, view / "objects", owner=layout.owner)
        (view / "refs").mkdir()
        _write_view_file(view / "HEAD", _OBJECT_VIEW_HEAD)
        _write_view_file(view / "config", _OBJECT_VIEW_CONFIG)
        yield view
    finally:
        shutil.rmtree(view, ignore_errors=True)


def git_own_checkout_guard(repo_root: Path | str) -> Path:
    """確認 `repo_root` 是**本 uid 自己的** checkout,回其 realpath;否則 `OSError`。

    generation 面(作者為自己的樹發射 candidate)是本家族唯一還需要工作樹事實的地方。
    誠實邊界:這**不是**「假設同 uid」,同 uid 是被**驗證**的前提。

    E3 round-5 P1-6:初版只比對目錄 owner。但 `git status` 真正要求的性質是「這棵樹的
    `.git` 只有我寫得了」——一棵 euid 所有、`.git` 卻 group/world-writable 的 checkout
    (共用 CI 樹、umask 意外)會通過 owner 檢查,然後照樣執行別人寫進去的
    `core.fsmonitor`,而 git 自己的 `safe.directory` 因為 uid 相符也幫不上忙。因此
    `.git` 的 mode 一併檢查。仍未收的是祖先鏈與 check-then-exec 之間的窗口。
    """

    import os
    import stat as stat_module

    root = Path(os.path.realpath(str(repo_root)))
    info = os.lstat(root)
    if not stat_module.S_ISDIR(info.st_mode):
        raise OSError(f"{root} is not a directory")
    if info.st_uid != os.geteuid():
        raise OSError(
            f"{root} is owned by another uid; the generation face refuses to read a "
            "foreign working tree (the verification face uses the code-owned object "
            "view instead)"
        )
    marker = os.lstat(root / ".git")
    if marker.st_uid != os.geteuid():
        raise OSError(f"{root}/.git is owned by another uid")
    if marker.st_mode & (stat_module.S_IWGRP | stat_module.S_IWOTH):
        raise OSError(
            f"{root}/.git is group or other writable, so its config is not exclusively "
            "this uid's; the generation face refuses to run git status against it"
        )
    return root


# 「存在但讀不到」與「不存在」必須分開:前者不得回落 packed-refs,否則被驗者把 loose
# ref 弄成讀不到、同時在 packed-refs 手寫一行,就能讓解析回錯的 sha(E2 F7)。
_REF_UNREADABLE = object()


def _loose_ref_value(git_dir: Path, common: Path, name: str) -> Any:
    if any(part in ("", ".", "..") for part in name.split("/")):
        return None
    candidates = [git_dir / name] if name == "HEAD" else [common / name, git_dir / name]
    for candidate in candidates:
        try:
            raw = read_bounded(candidate, MAX_REF_FILE_BYTES)
        except FileNotFoundError:
            continue
        except OSError:
            return _REF_UNREADABLE
        return raw.decode("utf-8", "replace").strip()
    return None


def _packed_ref_value(common: Path, name: str) -> str | None:
    try:
        raw = read_bounded(common / "packed-refs", MAX_PACKED_REFS_BYTES)
    except OSError:
        return None
    for line in raw.decode("utf-8", "replace").splitlines():
        if not line or line[0] in "#^":
            continue
        value, _, listed = line.partition(" ")
        if listed.strip() == name and re.fullmatch(r"[0-9a-f]{40}", value):
            return value
    return None


def read_subject_ref(repo_root: Path | str, name: str = "HEAD") -> str | None:
    """把被驗者的 ref 名解析成 40-hex;解不出來一律 `None`(fail-closed)。

    view 的 `refs/` 是空的,故必須來自被驗者 ref 儲存的事實在此以**純位元組讀取**取得,
    再以明確 40-hex 交給 view。ref 檔是資料不是執行面,且 ref 值本來就由被驗者決定。
    reftable backend 不鏡射,偵到回 `None`。
    """

    try:
        layout = subject_layout(repo_root)
    except OSError:
        return None
    git_dir, common = layout.git_dir, layout.common_dir
    if (common / "reftable").is_dir() or (git_dir / "reftable").is_dir():
        return None
    current = name
    for _ in range(_MAX_SYMREF_DEPTH):
        if current != "HEAD" and _REF_NAME_PATTERN.fullmatch(current) is None:
            return None
        value = _loose_ref_value(git_dir, common, current)
        if value is _REF_UNREADABLE:
            return None
        if value is None:
            # git 從不從 packed-refs 解析 HEAD。
            return None if current == "HEAD" else _packed_ref_value(common, current)
        if value.startswith("ref:"):
            current = value[4:].strip()
            continue
        return value if re.fullmatch(r"[0-9a-f]{40}", value) else None
    return None


def resolve_named_revision(repo_root: Path | str, revision: str) -> str:
    """把名字換成 view 解得出來的 40-hex;40-hex 原樣回,解不出即 `OSError`。

    view 的 `refs/` 刻意留空,所以它解不出任何名字。E2 round-5 F6:初版只改寫字面
    `"HEAD"`,於是 generation 面不再吃 branch/tag,CLI 傳 `--source-head main` 從發得出
    receipt 變成 traceback。這裡把常見的 ref 名一併解析,仍解不出來就給一句具名錯誤,
    而不是讓 git 的 `unknown revision` 從 `CalledProcessError` 裸逸出去。
    """

    if re.fullmatch(r"[0-9a-f]{7,40}", revision):
        return revision
    candidates = (
        [revision]
        if revision.startswith("refs/")
        else ["HEAD"]
        if revision == "HEAD"
        else [f"refs/heads/{revision}", f"refs/tags/{revision}",
              f"refs/remotes/{revision}"]
    )
    for candidate in candidates:
        resolved = read_subject_ref(repo_root, candidate)
        if resolved is not None:
            return resolved
    raise OSError(
        f"revision {revision!r} could not be resolved from the subject's ref storage "
        "(the code-owned object view resolves no names of its own)"
    )


def _replace_refs_present(git_dir: Path, common: Path) -> bool:
    """`refs/replace/` 底下有沒有東西(loose 或 packed)。

    E2 F4:每一條 except 都必須 fail-**closed**。它取代的 `git for-each-ref` 在任何失敗
    上都會拋並產出「object store is unreadable」;若這裡把「讀不到」當成「沒有 replace
    ref」,被驗者只要讓 `packed-refs` 超出上界或不可讀,就能把一條真判定靜默關掉。
    """

    import os

    unreadable: list[OSError] = []
    for base in {git_dir, common}:
        root = base / "refs" / "replace"
        if not root.is_dir():
            continue
        visited = 0
        for _, _, files in os.walk(root, onerror=unreadable.append):
            if files or unreadable:
                return True
            visited += 1
            if visited > _MAX_REPLACE_REF_SCAN_ENTRIES:
                return True
        if unreadable:
            return True
    try:
        raw = read_bounded(common / "packed-refs", MAX_PACKED_REFS_BYTES)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return any(
        line.partition(" ")[2].strip().startswith("refs/replace/")
        for line in raw.decode("utf-8", "replace").splitlines()
        if line and line[0] not in "#^"
    )


def _promisor_marks_present(common: Path, git_dir: Path) -> bool:
    """partial(promisor)clone 的檔案系統痕跡。

    主判準是 `objects/pack/*.promisor` 標記檔——git 自己為每個從 promisor remote 取來的
    pack 寫下的。config 掃描是第二道,只認 git 真正的鍵形,且只能讓判定更嚴。
    """

    pack = common / "objects" / "pack"
    if pack.is_dir():
        try:
            if any(entry.suffix == ".promisor" for entry in pack.iterdir()):
                return True
        except OSError:
            return True
    for base in {common, git_dir}:
        for name in ("config", "config.worktree"):
            try:
                raw = read_bounded(base / name, MAX_SUBJECT_CONFIG_BYTES)
            except FileNotFoundError:
                continue
            except OSError:
                return True
            if _PROMISOR_CONFIG_KEY.search(raw.decode("utf-8", "replace")):
                return True
    return False



def _sha256_object_format(common: Path, git_dir: Path) -> bool:
    """被驗者是否使用 sha256 object format(P0-1 的 sha1 重算對它不成立)。"""

    for base in {common, git_dir}:
        try:
            raw = read_bounded(base / "config", MAX_SUBJECT_CONFIG_BYTES)
        except FileNotFoundError:
            continue
        except OSError:
            return True
        if _SHA256_OBJECT_FORMAT.search(raw.decode("utf-8", "replace")):
            return True
    return False


def subject_object_store_findings(repo_root: Path | str) -> list[str]:
    """被驗者 object store 的 typed 衛生事實,全部由檔案系統判定。

    這些事實以前是 `git -C <被驗者> rev-parse/for-each-ref/config` 問出來的,亦即「把
    外人的目錄當 repository 打開」的一部分。改成 stat 之後判定同樣完整,而且其中數條在
    物化的 view 底下已經**結構上不可能生效**;仍然顯式回報,是為了讓 typed reason 保持
    精確。`STORE_INDETERMINATE` 與其他標記並列出現時代表「查不出來」,呼叫端必須把它
    當成拒絕理由而不是「沒發現問題」。
    """

    try:
        layout = subject_layout(repo_root)
    except OSError:
        return [STORE_UNREADABLE]
    git_dir, common = layout.git_dir, layout.common_dir
    findings: list[str] = []
    try:
        if (common / "reftable").is_dir() or (git_dir / "reftable").is_dir():
            findings.append(STORE_UNSUPPORTED_REF_BACKEND)
        if _sha256_object_format(common, git_dir):
            findings.append(STORE_UNSUPPORTED_OBJECT_FORMAT)
        if (git_dir / "shallow").exists() or (common / "shallow").exists():
            findings.append(STORE_SHALLOW)
        if (common / "info" / "grafts").exists():
            findings.append(STORE_GRAFTS)
        if (common / "objects" / "info" / "alternates").exists():
            findings.append(STORE_NESTED_ALTERNATES)
        if _replace_refs_present(git_dir, common):
            findings.append(STORE_REPLACE_REFS)
        if _promisor_marks_present(common, git_dir):
            findings.append(STORE_PROMISOR)
    except OSError:
        return [STORE_INDETERMINATE]
    return findings
