# S2E round-5 — 差異 uid 拓撲:從 code-owned bare object view 取事實

- 狀態:source 設計修復已落地(本輪)。**不含**三支 root-owned producer 本體、不含
  信任根 provision、不含任何 receipt/runtime/deploy/PG/broker 動作。九項 authority
  維持全 false,production effect 維持 0/6。
- 對應代碼:`aiml_gate_receipt_schema_core.py`(view 與 ref 讀取器的實作正本)、
  `aiml_gate_receipt_s2e_anchor_floor.py`(object-store 衛生判定)、
  `aiml_gate_receipt_s2e_{launch,consumption,review}.py`(消費面)。
  **沒有新增模組**:見 §5 debt 1 的取捨。
- 逐字保留的問題敘述在 `schema_core.git_argv` 的 docstring;本檔只寫**解法**與
  **它證得到什麼、證不到什麼**。

## 1. 問題的形狀(摘要;正本在 `git_argv` docstring)

§LW1 的目標拓撲是 root-owned producer 讀 ncyu 所有的 repo。舊實作是
`git -C <被驗者> …`,它要求 git 把**外人所有的目錄當成 repository 打開**。這一個
動作同時帶來兩個後果,而且兩者發生在**同一步**(repository discovery):

1. git 讀該 repo 的 local config ⇒ `core.fsmonitor`、以及經 `.gitattributes` 的
   `filter.<drv>.clean` 進場。本家族實際會跑 `git status`(舊 `_require_clean`),
   所以寫得了 `.git/config` 的**非 root repo owner** 可以用驗證器的身分執行任意程式。
2. ownership 檢查 ⇒ 差異 uid 時 `rc=128 fatal: detected dubious ownership`。

兩條看似可行的出口都已被實測證偽,不再重來:

- `-c safe.directory=<repo>`(command 域):等於把 (1) 打開。逐鍵 denylist 不收斂。
- `git config --system --add safe.directory`:`git_subprocess_env()` 設
  `GIT_CONFIG_NOSYSTEM=1` 且不帶 `HOME`,system/global 兩個 protected 域都讀不到;
  而且就算讀得到,放行仍然等於 (1)。

## 2. 解法:不打開被驗者,只掛它的 object store

`code_owned_object_view(repo_root)` yield 一個**驗證器自己建的 bare repo**,以
`objects/info/alternates` 掛上被驗者的 `objects/` 目錄。alternates 是純內容定址
資料面:git 只從那裡取物件,**不讀它的 config、不跑它的 hook、不解析它的
attributes、也不對它做 ownership 檢查**。於是 §1 的共同前提整個消失。

`git_argv` 一個字沒改,仍然只是 `[git, -C, <path>, *args]`,仍是本家族唯一的 argv
建構入口(`agent_governance_s2e_lw1_action_packet.py` 的呼叫形狀因此不變)。改的是
**傳進去的那個 `<path>`**。

view 的性質(逐條被 `test_object_view_is_private_and_carries_no_executable_surface`
釘住):

| 性質 | 為什麼 |
|---|---|
| 本 uid 所有、0700、祖先鏈逐層驗過 | `TMPDIR` 是 ambient 值;攻擊者所有的父目錄可以把 0700 的 view 整個換掉(TOCTOU)⇒ `config` 被替換 ⇒ fsmonitor 從側門回來。祖先只能由 root 或本 uid 所有;group/other 可寫時必須帶 sticky(`/tmp` 的 1777 合格) |
| `config` 逐位元組由代碼寫出 | 沒有 remote(promisor 抓不到網路,缺物件就是缺)、沒有 `core.fsmonitor`、沒有 filter driver |
| 沒有 `hooks/`、沒有 `info/grafts`、`refs/` 全空 | replace ref 與 graft 都不生效,被驗者改寫不了物件圖 |
| 沒有工作樹 | `git status` 在這裡是**結構上**跑不起來(`fatal: this operation must be run in a work tree`),不是靠自律不去呼叫 |
| 每次呼叫建一個、離開即刪 | 無快取、無 module 級可變狀態 ⇒ 沒有跨呼叫污染,也沒有需要註冊的可變單例 |

### 2.1 名字面與物件面分離

view 的 `refs/` 刻意留空、`HEAD` 指向一個不存在的分支,所以 **view 不替被驗者解析
任何名字**。真的需要被驗者 ref 儲存的兩項事實(`HEAD`、`_PROTECTED_ANCESTOR_REFS`)
由 `read_subject_ref` 以**純位元組讀取**取得(`O_NOFOLLOW`、逐項尺寸上界、symref
鏈深度上界、reftable backend 直接 fail-closed),再把 40-hex 交進 view。

誠實邊界:ref 值本來就由被驗者決定(他也決定自己 commit 什麼),讀它沒有交出新的
信任;而讀**檔案**不會執行任何東西。

E1 於 git 2.55 實測的陷阱,已釘進測試:**裸** `git rev-parse HEAD` 在解不出來時
回 `rc=0` 並原樣印回字串 `HEAD`(fail-open 形狀)。本家族每一條名字解析因此一律走
`--verify`,或先由 `read_subject_ref` 換成 40-hex。

### 2.2 衛生判定改為檔案系統事實

`shallow` / `info/grafts` / `refs/replace/` / promisor 四條原本是
`git -C <被驗者> rev-parse/for-each-ref/config` 問出來的——那正是「把外人的目錄當
repository 打開」的一部分。改由 `anchor_floor._object_store_errors` 直接 stat(`shallow`、`info/grafts`、
`refs/replace/**` 與 `packed-refs`、`objects/pack/*.promisor`、巢狀 `alternates`)。

其中數條在 view 底下已經**結構上失效**,實測佐證:

- promisor:view 沒有 remote。同一個 `--filter=blob:none` clone,被驗者自己
  `git show <old>:a.txt` 會靜默走網路抓回來(rc=0),經 view 則
  `fatal: bad object …`(rc=128)。這消掉了本家族唯一的 runtime effect 來源。
- shallow:view 不掛 shallow graft,缺 parent 會直接炸
  (`fatal: cannot simplify <c> (because of <parent>)`),而不是靜默把歷史截短。
- replace ref / grafts:view 的 `refs/` 與 `info/` 都是空的,不生效。

仍然**顯式回報**這四條,是為了讓 typed reason 保持精確,不是把一條真判定換成泛用錯誤。
promisor 的 config 文字掃描只是第二道,且只能讓判定更嚴,永遠不能用來取得肯定事實。

## 3. 具名撤回:驗證面的「工作樹乾淨」

工作樹乾淨是 bare view **回答不了**的唯一一項事實,而取得它的動作正是本漏洞本體。
處置按「面別」切開,兩邊都寫明:

- **generation 面**(`_require_own_clean_checkout`,作者為自己剛做完的樹發射
  candidate):保留 `git status`,但先過 `git_own_checkout_guard`
  (`st_uid == geteuid()`),外人所有的樹一律大聲拒。這**不是**「假設同 uid」——
  同 uid 是被驗證後才成立的前提。作者跑到自己寫的 `core.fsmonitor` 不是提權,
  寫 config 的人就是執行者本人。
- **驗證面**(`_acceptance_review_bundle_errors(require_current_generation=True)`):
  **撤回**「工作樹乾淨」這一條,並在代碼裡具名。

  留下的是 view 真的能證、而且正是這個檢查要的那一條:**候選必須等於當前 HEAD 的
  commit 與 tree**。錯誤字串同步從 `not the clean current HEAD` 改為
  `not the current HEAD generation`——舊字串會繼續宣稱一件已經不再檢查的事。

  > **更正(E2 round-5 F1,CONFIRMED)。** 本節初版給了兩條並列理由,第二條是假的,
  > 已在代碼與此處改掉,不得寫回去:
  >
  > 1. **取不到**(成立):跨 uid 沒有任何不經被驗者可寫執行面的取得方式(§1 兩條死路)。
  > 2. ~~**不承重**:每項投影都走 `<commit>:<path>`,工作樹位元組進不了任何 digest。~~
  >    **證偽。** 同一個函式往下 110 行,`validate_governed_command_capture(...,
  >    reexecute=_commit(repo_root, "HEAD") == reviewed_head)` 會經
  >    `agent_governance_command_capture_v2._replay_errors` →
  >    `agent_governance_generation_summary.capture_generation_summary`,而後者
  >    (`:275-279`)把 `git diff --binary` 的串流摘要與 untracked 清單放進
  >    `generation_digest`。**工作樹位元組確實進得了驗證面的 digest,髒樹確實改得了
  >    結論。** 而且 `_git_root`(`:60-63`)以 **ambient env 與 ambient PATH** 跑
  >    `git rev-parse --show-toplevel`、`cwd=<被驗者>`——那正是本輪要消掉的 discover
  >    動作,在差異 uid 下 rc=128 且該 `ValueError` 一路無人接,會變成未捕捉例外而不是
  >    typed verdict。
  >
  >    撤回本身仍然正確(理由 1 獨立成立,而恢復 `git status` 等於恢復 R4-1 的 RCE),
  >    但 `agent_governance_command_capture_v2` / `agent_governance_generation_summary`
  >    是**同一缺陷類別的未修實例**,且不在本輪 path manifest 內。見 §5 debt 4。

## 4. 這組改動證得到什麼、證不到什麼

> **本節的宣稱範圍已被 round-5 的 E2/E3 複核收窄。** 下面「證得到」的三條仍然成立
> (E3 以武裝 `core.fsmonitor`/`filter.*.clean/process`/`diff.*.textconv`/`core.hooksPath`
> /`core.pager`/`core.editor`/`uploadpack.packObjectsHook`/`include.path` 的被驗者實測:
> 零 sentinel 命中、事實全數取得,`_GIT_ENV_ALLOWLIST` 與 `safe.directory` 皆未回歸),
> 但**「view 只從 alternate 取內容定址物件」這句是假的**,而且 §5 記了三條
> CONFIRMED-exploitable 的殘留。本輪的 gate verdict 是 **FAIL**,不是 PASS。

**證得到(本輪測試涵蓋)**

- 被驗者的 `core.fsmonitor` 與 `filter.<drv>.clean` 在整條驗證路徑上一次都不被執行。
- 被驗者的 `.git/config` 被封成 `repositoryformatversion = 99`(git 對它**完全**
  拒絕開啟)時,floor 讀取與 review blob manifest **照樣取得到事實**。
- 驗證面每一次 git 呼叫的 repository 引數都不是被驗者路徑,且不帶 `status` /
  `--git-dir` / `--work-tree` / `safe.directory`。

  > 為什麼判準用 version-99 而不是 `GIT_TEST_ASSUME_DIFFERENT_OWNER`:那個 knob 對
  > **每一個** repo 說謊,連驗證器自建的 code-owned view 都會被它毒到,所以它代表
  > 不了本拓撲。version-99 與 dubious ownership **在同一步失敗**(repository
  > discovery),而且它連 protected 域的 `safe.directory` 都救不回來——比差異 uid
  > 更強。因此「事實仍然取得到」就證明了驗證面根本沒把被驗者當 repository 打開。

**證不到(誠實邊界)**

- 本輪全部是 `LOCAL_REPRODUCIBLE` 級的 source/測試證據,不是 runtime 證據。真正
  root-owned producer 對真正 ncyu-owned repo 的執行,仍需 platform/external-attested
  的捕獲。
- 本檔不主張 §LW1 的任何 predicate 因此 SATISFIED,也不主張 P0-1 關閉。
- view 只證 repo 拓撲與位元組,不證任何 runtime/效果/外部事實。

## 5. 留給下一輪的具名債

1. **2000 行上限迫使本輪不能新增模組,而且兩支主檔現在幾乎滿載。**
   本 view 是一條獨立的信任邊界,理應自成一個 leaf(`aiml_gate_receipt_git_view.py`,
   本輪確實先這麼做過)。但新 leaf 進入 engine-scanner 的 runtime import 閉包後,
   必須同時登記到五個 wave-exit digest 承載面:
   `application_bundle_runtime_closure_v1.json`(含 `self_digest` 重算)、
   `aiml_gate_receipt_validator.py` 的 `_W0_OWNED_PATHS`、`aiml_gate_receipt_wave_w2.py`
   的 `_W2_OWNED_PATHS`、`wave_w3.py` 的 `_W3_OWNED_PATHS`、`wave_w5.py` 的
   `_W5_OWNED_PATHS`(`_W0_OWNED_PATHS` 的註解已明寫:拆分後的家族若不擴列,
   owned_path_diff_digest 的覆蓋面會**靜默收窄**——E2 P1-2 抓過一次)。那是 W0/W2/W3/W5
   四波 wave-exit 的重導出,遠超本輪授權,故改為就地放進 `schema_core`(view + ref
   讀取器)與 `anchor_floor`(object-store 衛生判定)。
   代價:`schema_core` 1995/2000、`s2e_launch` 1998/2000(後者在本輪之前就已是 1982,
   長期滿載)。下一次對這兩檔的任何實質改動都會越線。這**不是** exception registry 的
   候選(registry 的紀律是「登記 ≠ 授權長期超標」),而是一項 E5 拆分工作,且該拆分
   必須與上述五個登記面在同一波內一起做。
2. **`helper_scripts/maintenance_scripts/agent_governance_s2e_lw1_action_packet.py`
   的 generation 面沒有 own-checkout 閘。** 它仍以 `git_argv(repo_root, …)` 跑
   `status` 與 `rev-parse HEAD`。該檔屬並行的 PM lane,本輪硬停止不得跨界修改;
   `git_argv` 的介面未變,所以它現在照舊可用。建議 PM lane 比照
   `_require_own_clean_checkout` 補上 `git_own_checkout_guard`。
3. **reftable ref backend 未鏡射**,偵到即 fail-closed。若未來被驗者改用 reftable,
   需要一條純資料的 reftable 讀取器,或改由 producer 側提供已解析的 40-hex。

## 6. round-5 對抗複核的未收發現(E2 / E3;本輪 gate verdict = FAIL)

本輪跑了獨立的 E2(對抗代碼複核)與 E3(信任邊界安全複核)。兩者都確認核心機制成立
(見 §4 的方框),也都找到**本輪未收**的缺陷。下列全部是 CONFIRMED,除非另註。
**在 P0-A/B/C 收口之前,本分支不得 merge,也不得被任何 receipt 當成 §LW1 的證據。**

### P0-A(E3 P0-1,high)指標重導向:`gitdir:` / `commondir` / `objects` symlink

`subject_git_dir` 跟隨 `.git` 檔裡的 `gitdir: <絕對路徑>`、`subject_common_dir` 跟隨
`commondir`、`code_owned_object_view` realpath `<common>/objects`——**三者都不驗 owner、
不驗與 `repo_root` 的關係**。E3 實測:被驗者寫 `gitdir: /path/to/victim/.git`,驗證器
(root)就把 victim repo 的 `TODO.md` 位元組讀了出來。`commondir` 與 `objects` symlink
兩條路等價。

比讀取更糟:`aiml_gate_receipt_s2e_consumption` 由 `subject_common_dir(subject_git_dir(...))`
導出 consume-once ledger 的 `state_path`/`lock_path`,所以**被驗者選得了防重放帳本的
位置**(指到空目錄 ⇒ 帳本重新變空),並讓 root 在他指定的目錄裡建檔。

誠實歸因:`git rev-parse --git-common-dir` 本來就跟隨同樣的指標,所以重導向不是新的;
**新的是 git 的 ownership 檢查原本是那道意外屏障,而本輪刻意移除它卻沒有補上替代**。
修法:記下 `lstat(repo_root).st_uid`,要求 gitdir/commondir/objects 三者的 owner 都等於
它(不是等於 euid——驗證器是 root,被驗者不是)。

### P0-B(E3 P0-2,high)巢狀 alternates 的拒絕是 check-then-use

`code_owned_object_view` 的 `exists()` 檢查之後、git 真的開檔之前,隔著 mkdtemp + 祖先
驗證 + 三次寫入 + subprocess spawn。被驗者擁有 `objects/info/`,在那個窗口內建檔即可。
E3 的樸素競爭器 400 次試驗:**leaked 134 / refused 161 / clean 105**。

### P0-C(E3 P0-3,high)alternate 的資料面不是純內容定址

git 也會從 alternate 載入 `objects/info/commit-graph`、`commit-graphs/*`、
`objects/pack/multi-pack-index`、`*.bitmap`——**攻擊者撰寫、非內容定址、git 不對物件
複驗**。E3 實測:對 `c3` 的 CDAT parent1 欄位改 4 個位元組,`floor_history_errors` 的
`log --full-history` 走訪就**少掉 c2**,而 `_object_store_errors` 回 `[]`、
`merge-base --is-ancestor` 仍 True、`git commit-graph verify` 也 rc=0 ⇒
`read_committed_durability_anchor_floor` 回 `FLOOR_VERIFIED`。這正好打掉
`--full-history` 那條具名防線。

**P0-B 與 P0-C 有共同的結構解**:不要把 view 的 `objects` 指向被驗者的目錄,改成在
view 內物化一個只含「loose object fanout 目錄」與 `pack/*.{pack,idx}` 的 symlink 集合
——不連 `info/`(⇒ 沒有 alternates、沒有 commit-graph)、不連 `multi-pack-index`、
不連 `*.bitmap`。一次改動同時關掉競爭窗口與圖偽造。

### P1 級(未收)

| # | 來源 | 內容 |
|---|---|---|
| P1-D | E2 F2 | `code_owned_object_view` 的 `OSError` 會從 `_is_ancestor` 逸出到四個未包 try 的呼叫點(`s2e_launch:502/529/570/1062`),把 `-> list[str]` 的驗證器變成 crash。**合法的 `git clone --shared` 就會觸發**。 |
| P1-E | E3 P1-5 | `s2e_launch` 與 `s2e_review` 的 git 呼叫**沒有 `timeout=`、沒有輸出上界**。E3 實測 1.2 MB 的 `.git` 用一顆零填充 blob 把驗證器 RSS 推到 687 MB(~250x)。舊拓撲下這些呼叫在 rc=128 就死了,本輪把它變成活的解析面。 |
| P1-F | E3 P1-6 | `git_own_checkout_guard` 只看目錄 owner,不看 mode、不走祖先鏈——與它旁邊 `_verify_private_directory` 的標準不一致。group/world-writable 的 `.git` 仍會讓 `git status` 跑到攻擊者寫的 `core.fsmonitor`。已在該函式 docstring 具名。 |
| P1-G | E2 F6 | `resolve_named_revision` 只改寫字面 `"HEAD"`,於是 generation 面**不再解析 branch/tag/`HEAD~1`**;CLI 傳 `--source-head main` 從發得出 receipt 變成 traceback。fail-closed,但未文件化、未測試。 |
| P1-H | E2 F5b/F9b、E3 P2 | `agent_governance_s2e_lw1_action_packet.py` 仍 `git -C <被驗者>` 跑 `status`(`:239`)與 `rev-parse`(`:382/384`),而 `:382` 在 **`validate_…` 驗證面**上——比 §5 debt 2 原本寫的「只有 generation 面」更廣。該檔屬 PM lane,本輪硬停止。 |
| P1-I | E2 F9 | 測試鑑別性:(a) hardening 的 fsmonitor 測試落在 `reviewed_head != HEAD` 分支,而該分支本來就跳過唯一會碰工作樹的 `_replay_errors`,故對 F1 那條路不具鑑別性;(b) `test_verification_face_never_hands_the_subject_repository_to_git` 只驅動 floor 路徑,名稱卻宣稱整個驗證面;(c) `test_only_the_generation_face_may_read_a_working_tree` 是對**識別字名**的字面代理,`view = repo_root` 即可滿足,且不掃 `cwd=`、不含 action packet。 |

### 本輪已收(post-review)

- **E3 P1-4 / E2 F3(FIFO)**:`read_bounded` 加 `O_NONBLOCK`。`O_NOFOLLOW` 不擋 FIFO
  而 `S_ISREG` 拒絕在 open 之後,`mkfifo .git/HEAD` 原本能讓驗證器**永久**阻塞
  (in-process,家族裡每個 subprocess `timeout=` 都救不到)。
- **E2 F4(衛生判定 fail-open)**:`_replace_refs_present` / `_promisor_marks_present`
  的每一條 `except OSError` 由「當成沒有」改為 fail-closed,`os.walk` 補 `onerror`;
  `config.worktree` 改從 per-worktree gitdir 讀。實測(0000 權限):unreadable
  `packed-refs`、`refs/replace`、`config` 三者現在都判紅。
  **殘留(未收,P1-J)**:polarity 對了,但**理由字串在說謊**——「讀不到」會被報成
  「rewrites objects through replace refs」/「is a promisor partial clone」。
  fail-closed 的判定沒錯,但 operator 拿到的是一個假的具名原因。應該分出一條
  「object store hygiene could not be determined」而不是借用既有原因。
- **E2 F7(ref 解析回錯的 sha)**:loose ref「存在但讀不到」不再回落 packed-refs,
  `HEAD` 永不從 packed-refs 解析,非 HEAD ref 改為 common-dir 優先。
- **E2 F5a**:指向已不存在的 `subject_object_store_findings` 的 docstring、以及殘留的
  `__pycache__/aiml_gate_receipt_git_view.cpython-310.pyc`。
- **E2 F1**:§3 的假理由已更正(見該節方框)。

### 未複核

`_promisor_marks_present` 改讀 per-worktree `config.worktree`、以及上列「本輪已收」的
五項修補,**是在 E2/E3 交件之後才寫的,沒有經過第二輪對抗複核**。
