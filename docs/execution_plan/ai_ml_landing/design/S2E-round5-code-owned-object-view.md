# S2E round-5 — 差異 uid 拓撲:從 code-owned bare object view 取事實

- 狀態:source 設計修復已落地(本輪)。**不含**三支 root-owned producer 本體、不含
  信任根 provision、不含任何 receipt/runtime/deploy/PG/broker 動作。九項 authority
  維持全 false,production effect 維持 0/6。
- 對應代碼:`aiml_gate_receipt_git_view.py`(**新葉**;view / 佈局解析 / ref 讀取器 /
  衛生事實的實作正本)、`aiml_gate_receipt_schema_core.py`(re-export + `git_argv` +
  唯一的工作樹讀取原語)、`aiml_gate_receipt_s2e_{launch,anchor_floor,consumption,review}.py`
  (消費面),以及五個登記面(§5 debt 1)。
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

`code_owned_object_view(repo_root)` yield 一個**驗證器自己建的 bare repo**,裡面
**物化**一份只含物件的 store。git 只從那裡取物件,**不讀被驗者的 config、不跑它的
hook、不解析它的 attributes、也不對它做 ownership 檢查**。於是 §1 的共同前提整個消失。

> **round-6 修正**:初版是以 `objects/info/alternates` 掛上被驗者的 `objects/`,並宣稱
> alternates 是「純內容定址資料面」。**那句是假的**,E3 實測推翻(§6 P0-C)。現在
> `_materialize_object_store` 在 view 內建一個目錄,只放 loose fanout 目錄與
> `pack/*.{pack,idx}` 的 symlink——沒有 `info/`、沒有 `multi-pack-index`、沒有
> `*.bitmap`、沒有 `*.promisor`。那些面在 view 裡**不存在**,不是被檢查掉。

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
| 每次呼叫建一個、離開即刪 | 無快取、無 module 級可變狀態 ⇒ 沒有跨呼叫污染,也沒有需要註冊的可變單例。實測 ~28 ms/次(含 126 條 symlink) |
| object store 是物化的,不是掛 alternates | 沒有 `info/` ⇒ 沒有 alternates(P0-B 的競爭窗口消失)、沒有 commit-graph(P0-C 的圖偽造面消失);沒有 midx/bitmap/promisor。剩下能換的只有物件位元組,而那是內容定址、git 讀出來會複驗 sha |
| gitdir / commondir / objects 全部 owner-pin + 佈局不變式 | 被驗者書寫的 `gitdir:`/`commondir`/symlink 不得把 root 驗證器帶去別人的資料(P0-A) |

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

> **本節的宣稱範圍曾被 round-5 的 E2/E3 複核收窄,round-6 拆分波已收口三條 P0。** 下面「證得到」的三條仍然成立
> (E3 以武裝 `core.fsmonitor`/`filter.*.clean/process`/`diff.*.textconv`/`core.hooksPath`
> /`core.pager`/`core.editor`/`uploadpack.packObjectsHook`/`include.path` 的被驗者實測:
> 零 sentinel 命中、事實全數取得,`_GIT_ENV_ALLOWLIST` 與 `safe.directory` 皆未回歸),
> 初版「view 只從 alternate 取內容定址物件」那句是假的,已改寫;三條
> CONFIRMED-exploitable 的殘留(§6 P0-A/B/C)在 operator 2026-08-08 授權的拆分波中收掉,
> 各帶回歸測試。**仍未經第二輪對抗複核**(§6 末)。

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

## 5. 拆分波(operator 2026-08-08 授權)與五個登記面

初版把 view 就地塞在 `schema_core`,因為新 leaf 進入 engine-scanner 的 runtime import
閉包後必須同時登記到五個 wave-exit digest 承載面,而那超出當時的授權。operator 授權
之後,本輪把它拆出來並完成登記:

| 登記面 | 內容 |
|---|---|
| `program_code/ml_training/application_bundle_runtime_closure_v1.json` | `python_modules` 60 → 61,`self_digest` 以 `validator.artifact_self_digest` 重算(`sha256:86c34fce…` → `sha256:d464e5d9…`)。手改而不重算等於只有名字沒有綁定 |
| `aiml_gate_receipt_validator.py` `_W0_OWNED_PATHS` | 該表註解已明寫:拆分後的家族若不擴列,`owned_path_diff_digest` 的覆蓋面會**靜默收窄**(E2 P1-2 抓過一次) |
| `aiml_gate_receipt_wave_w2.py` `_W2_OWNED_PATHS` | 同上 |
| `aiml_gate_receipt_wave_w3.py` `_W3_OWNED_PATHS` | 同上 |
| `aiml_gate_receipt_wave_w5.py` `_W5_OWNED_PATHS` | 同上;前例是 `aiml_gate_receipt_w5_obligations.py` 的同型拆分 |

行數壓力隨之解除,`require_own_clean_checkout`(家族唯一的工作樹讀取原語)也一併移到
`schema_core`,與守著它的 `git_own_checkout_guard` 放在一起:
`git_view` 647、`schema_core` 1751、`s2e_launch` 1992、`anchor_floor` 814 —— 全部在
2000 以下且有實際餘裕,不再需要為了塞下安全修補而砍註解。

## 6. round-5 對抗複核的發現與處置

本輪跑了獨立的 E2(對抗代碼複核)與 E3(信任邊界安全複核)。兩者都確認核心機制成立,
也都找到缺陷。E3 的三條 high 已在拆分波中收口,各帶回歸測試與實測數字。

### 已收(三條 P0)

**P0-A(E3 P0-1)指標重導向。** `subject_git_dir` 跟隨 `.git` 檔的
`gitdir: <絕對路徑>`、`subject_common_dir` 跟隨 `commondir`、view realpath
`<common>/objects` —— 三者都不驗 owner。E3 實測:被驗者寫
`gitdir: /path/to/victim/.git`,root 驗證器就讀出了 victim 的位元組;而
`aiml_gate_receipt_s2e_consumption` 由 commondir 導出 consume-once ledger 的
`state_path`/`lock_path`,所以**防重放帳本的位置也由被驗者選**(指到空目錄 ⇒ 帳本重新
變空),並讓 root 在他指定的目錄裡建檔。重導向本身不是新的(`git rev-parse
--git-common-dir` 一向跟隨同樣的指標);**新的是 git 的 ownership 檢查原本是那道意外
屏障,而本輪刻意移除了它**。

收法兩條:(1) **owner pin** —— gitdir/commondir/objects 都必須屬於 `repo_root` 自己的
owner(不是 euid;驗證器是 root,被驗者不是),所以被驗者只能指向他本來就讀得到的東西;
(2) **git 自己的回指不變式** —— linked worktree 的 `<gitdir>/gitdir` 必須寫回該 worktree
的 `.git` 路徑。同 uid 的兩個 repo 之間的重指因此也擋住了(owner pin 對它無效)。
回歸:`test_subject_cannot_redirect_the_verifier_with_a_gitdir_pointer`,同時斷言真的
linked worktree 仍然解得出來——閘不能是把功能關掉。

**P0-B(E3 P0-2)巢狀 alternates 的拒絕是 check-then-use。** `exists()` 與 git 開檔之間
隔著 mkdtemp、祖先驗證、三次寫入與 spawn,而被驗者擁有 `objects/info/`。E3 的樸素競爭器
400 次:**leaked 134 / refused 161 / clean 105**。

**P0-C(E3 P0-3)alternate 的資料面不是純內容定址。** git 也從 alternate 載入
`objects/info/commit-graph`、`commit-graphs/*`、`pack/multi-pack-index`、`*.bitmap`
—— 攻擊者撰寫、git 不對物件複驗。E3 實測改 `c3` 的 CDAT parent1 欄位 4 個位元組,
`floor_history_errors` 的 `--full-history` 走訪就少掉 `c2`,而 `_object_store_errors`
回 `[]`、`merge-base --is-ancestor` 仍 True、`git commit-graph verify` 也 rc=0 ⇒
`FLOOR_VERIFIED`。這正好打掉 `--full-history` 那條具名防線。

B 與 C 的共同結構解是 `_materialize_object_store`(§2 的方框)。實測:同一個競爭器對
物化後的 view 跑 400 次 → **leaked 0 / refused 0 / clean 400**;帶 commit-graph 與
multi-pack-index 的 repo 經 view 走訪,結果等於誠實歷史。回歸:
`test_materialized_store_has_no_window_for_injected_alternates`(60 次帶競爭執行緒)、
`test_materialized_store_excludes_the_graph_surfaces_git_does_not_verify`。

### 已收(P1)

| # | 來源 | 處置 |
|---|---|---|
| P1-D | E2 F2 | view 的 `OSError` 會從 `_is_ancestor` 逸出到四個未包 try 的呼叫點,把 `-> list[str]` 的驗證器變成 crash(合法的 `git clone --shared` 就會觸發)。改為收成 `False` —— 呼叫端一律 `if not _is_ancestor(...)`,故 False 是 fail-closed 的那一邊 |
| P1-E | E3 P1-5 | `s2e_launch` 的 git 呼叫補 `timeout=180`。舊拓撲下這些呼叫在 `rc=128` 就死了,view 把它變成活的解析面。**輸出上界未收**(見下) |
| P1-F | E3 P1-6 | `git_own_checkout_guard` 除 owner 外一併檢查 `.git` 的 mode:group/world-writable 的 `.git` 表示 config 不是本 uid 獨有,`git status` 會跑到別人寫的 `core.fsmonitor`,而 uid 相符讓 git 自己的 `safe.directory` 幫不上忙 |
| P1-G | E2 F6 | `resolve_named_revision` 只改寫字面 `"HEAD"`,於是 generation 面不再吃 branch/tag。現在一併解析 `refs/heads|tags|remotes/<name>`,仍解不出來就給具名 `OSError`,不讓 git 的 `unknown revision` 裸逸出 |
| P1-J | 自審 | F4 的 polarity 修好後,「查不出來」一度借用別條原因的字串。新增 `STORE_INDETERMINATE` 與 “hygiene could not be determined”,不再說謊 |
| — | E2 F3 / E3 P1-4 | `read_bounded` 加 `O_NONBLOCK`:`O_NOFOLLOW` 不擋 FIFO 而 `S_ISREG` 拒絕在 open 之後,`mkfifo .git/HEAD` 原本能讓驗證器**永久**阻塞(in-process,subprocess `timeout=` 救不到) |
| — | E2 F4 | 衛生判定四處 `except OSError` 由 fail-open 改為 fail-closed,`os.walk` 補 `onerror`,`config.worktree` 改從 per-worktree gitdir 讀 |
| — | E2 F7 | loose ref「存在但讀不到」不再回落 packed-refs,`HEAD` 永不從 packed-refs 解析,非 HEAD ref 改為 common-dir 優先 |
| — | E2 F1 | §3 的假理由已更正(見該節方框) |

### 未收(具名留給下一輪)

1. **`command_capture_v2` / `generation_summary` 是同一缺陷類別的未修實例**(E2 F1):
   `_git_root` 以 ambient env/PATH 跑 `git rev-parse --show-toplevel`、`cwd=<被驗者>`,
   而 `capture_generation_summary` 把 `git diff --binary` 與 untracked 清單摘進
   `generation_digest`。不在本輪 path manifest 內。
2. **輸出上界**(E3 P1-5 的後半):`capture_output=True` 沒有尺寸上界,E3 實測 1.2 MB
   的 `.git` 用一顆零填充 blob 把 RSS 推到 687 MB(~250x)。timeout 已補,記憶體未封。
3. **`agent_governance_s2e_lw1_action_packet.py`**(E2 F5b、E3 P2):仍
   `git -C <被驗者>` 跑 `status`(`:239`)與 `rev-parse`(`:382/384`),而 `:382` 在
   **驗證面**上。PM lane 獨佔,本輪硬停止。建議比照 `require_own_clean_checkout`。
4. **ledger 仍可在被驗者自己擁有的目錄之間重指**(P0-A 的誠實邊界):owner pin 之後
   跨 uid 已擋,但把 commondir 指到自己另一個 repo 仍能拿到空帳本。那是
   `--git-common-dir` 語義的既有性質;要收需把 ledger 綁到 caller 選不了的身分。
5. **測試鑑別性**(E2 F9):hardening 的 fsmonitor 測試落在 `reviewed_head != HEAD`
   分支,對 F1 那條路不具鑑別性;`test_verification_face_never_hands_the_subject_
   repository_to_git` 只驅動 floor 路徑;`test_only_the_generation_face_may_read_a_
   working_tree` 是對識別字名的字面代理(本輪已擴到六個模組,但仍不掃 `cwd=`)。
6. **reftable ref backend 未鏡射**,偵到即 fail-closed。

### 未複核

拆分波的全部改動(三條 P0 的收口、五個登記面、六條 P1、以及 `require_own_clean_checkout`
的搬遷)**在 E2/E3 交件之後才寫,沒有經過第二輪對抗複核**。
