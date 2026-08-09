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
| object store 是物化的,不是掛 alternates | 沒有 `info/` ⇒ 沒有 alternates、沒有 commit-graph;沒有 midx/bitmap/promisor。**這一格原本還寫「剩下能換的只有物件位元組,而那是內容定址、git 讀出來會複驗 sha」——已撤回,那句是假的(§6 NEW-P0-1)** |
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
> 拆分波之後又跑了第二輪 E2/E3。結論:**P0-B 與 P0-C 確實關掉了**(兩位各自重建復現:
> alternates 競爭器 400 次 leaked 0,偽造 commit-graph 經 view 走訪回誠實歷史),
> **P0-A 只關掉跨 uid 那一半**,而拆分波用來論證 B/C「結構上關掉」的那句話是假的,
> 因此又冒出三條 NEW P0。本輪 gate verdict 仍是 **FAIL**,見 §6。

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

### round-6 第二輪 E2/E3:兩條真關掉,一條半關,三條新 P0

拆分波之後跑了第二輪獨立 E2/E3。兩位都從零重建復現,不採信本檔的描述。

**確認關掉(可以不用再扛)**

- **P0-B**:alternates 競爭器 400 次 `leaked 0 / refused 0 / clean 400`(原 134/400)。
  結構性的:view 的 `objects/` 只接受 `[0-9a-f]{2}` 與 `pack/*.{pack,idx}`,`info` 兩個
  過濾器都不匹配,而 view 目錄 0700/驗證器所有。
- **P0-C**:重建 CDAT parent1 的 4-byte 偽造。被驗者自己的 git 仍被騙
  (`--full-history` 少一筆),經 view 走訪回誠實歷史。midx/`.bitmap`/`.rev` 的排除也
  查過沒有造成 git 答錯,只是變慢。
- FIFO wedge、group/world-writable `.git`:關掉。
- 五(六)個登記面:E2 逐項驗過——closure `self_digest` 確為重算且與中央閘導出一致
  (`runtime_import_closure_size: 61`,雙向 exact-match),§10.1.2 (b) 的 46 條**恰好**等於
  `(W3∪W4∪W5) \ §10.1 逐字清單`,45→46 與 1.73×→1.77× 算術正確,wave 歸屬
  (W0/W2/W3/W5,不在 W1/W4)與 `schema_core` 完全平行、不是缺口。

**NEW P0-1(兩位各自 CONFIRMED)——「物件位元組是內容定址、git 會複驗 sha」是假的**

這是拆分波用來論證 B/C 殘餘風險有界的那一句,寫在 `git_view` docstring、
`_materialize_object_store` 與本檔 §2 表格。git **只有** `fsck`/`verify-pack` 會複驗,
而本家族兩者都不跑。`parse_object()` 走的路徑(`ls-tree`/`log`/`rev-list`/`merge-base`)
是安全的;`git show <rev>:<path>` 與 `cat-file --batch` 走的是
`read_object_file`→`get_tree_entry`,**不驗**。兩位在 git 2.55.0 各自實證 loose 與 packed
兩種形式都能讓一個 object id 回出攻擊者選定的位元組,`git fsck` 是唯一會發現的東西。

落點兩處,都在本輪要保護的證據面上:

- `s2e_anchor_floor.py:522/564` 只用 `show {commit}:{path}` 讀 floor,無 blob-id 交叉比對
  ⇒ 攻擊者可在走訪的每一個 commit 上自撰 floor 內容,而 commit 鏈、祖先鏈、受保護 ref
  錨定與 `_object_store_errors` 全部保持誠實。效果等同原 P0-C,而且不需要競爭。
- `s2e_review.py:494-508` 的 `s2e_review_source_blob_manifest` 從 `ls-tree` 取
  `git_blob`(誠實)、從 `show` 取 `sha256`(攻擊者選),**兩者從不比對**。於是簽出去的
  source blob manifest 帶著一個任何第三方重建同一 commit 都重現不出來的 digest。

放大器兩個:全 packed 的 store 也不安全(同名 loose object 會蓋過 pack);而
`_materialize_object_store` 只驗 fanout **目錄**不是 symlink、**不看目錄內容**,所以
`objects/<xx>/<yyy>` 放 symlink 即可無競爭讀到外部物件庫(E2 實測 100%,findings `[]`)。
**這代表 P0-B 的 confused-deputy 讀取只是換了路徑,沒有被關掉。**

收法(未做):讀出位元組後對 tree 記錄的 blob id 重算比對——`review.py` 上一行就已經有
`blob`,`anchor_floor` 補一次 `ls-tree` 即可;以及逐物件物化(`S_ISREG` + owner 檢查)
或 hardlink/copy,而不是逐目錄 symlink。

**NEW P0-2(E3 CONFIRMED)——物化不是快照**

被驗者事先建好 256 個空 fanout 目錄(對 git 無害),全部會被連上,於是 store 在 view 的
整個生命週期內都是**活**的:`t0` 與 `t1` 可以回不同位元組。而且每次 git 呼叫都建新 view
(`anchor_floor:271/290`、`review:246/258`),所以驗證面**沒有任何跨呼叫一致性**。
另外,列舉時 `S_ISDIR(lstat)`、git 在讀取時才解析 symlink 鏈 ⇒ 列舉後把已連結的 fanout
換成 symlink,就能讀到 `subject_layout` 明確拒絕過的 store。

**NEW P0-3(E3 CONFIRMED)——ledger 可被重指到*任意*目錄**

`git_view.subject_common_dir` 完全沒有驗證(無 owner pin、無佈局不變式),而
`s2e_consumption.py:549` 是 `subject_common_dir(subject_git_dir(repo_root))` ——對同一個
攻擊者可寫的 `commondir` 檔做了**兩次獨立讀取**,第二次不驗。E3 racer 3000 次:
`RELOCATED 555 / refused 983 / honest 1462`。目標**不受 owner pin 約束**,因為第二次讀取
根本不驗。`read()` 在三個檔都不存在時回 `_empty_ledger()` ⇒ 18.5%/次的重放繞過,
且 `_atomic_write`/`_open_lock` 會讓驗證器在攻擊者指定的目錄裡建檔。
**這比 §5 記的「殘留 #4」嚴重,而且是本輪代碼引入的,不是繼承自 git。**
一行可收:改用 `subject_layout(repo_root).common_dir` 這個唯一釘過的值,刪掉相容 re-read。

**P0-A 只關掉一半**

owner pin 真的擋掉跨 uid 的三條向量(`gitdir:`、`commondir`、`objects` symlink,三條實測
皆 refused),那部分該留。但**回指不變式是空的**:owner pin 允許的目標恰好是被驗者所有的
目錄,所以他對任何通過 pin 的目標都寫得了 `<gitdir>/gitdir`(兩位各自一行復現)。
E3 另外構造出一個只含 `objects/` 與 `worktrees/w/{gitdir,commondir,HEAD,refs}` 的合成
common dir,無競爭地取得任意 ledger 目錄。而
`test_subject_cannot_redirect_the_verifier_with_a_gitdir_pointer` **不具鑑別性**:它的
fixture 同 uid,卻刻意不寫攻擊者會寫的那一個檔。

### round-7:三條 NEW P0 收口(operator 2026-08-09 授權)

**NEW P0-1(位元組不是內容定址的)** —— 兩條配套,不再依賴 git 的任何隱含保證:

- *內容*:`schema_core.commit_blob_bytes`(家族**唯一**的 blob 讀取原語)讀出後以
  `git_blob_sha1` 對 `cat-file --batch` 標頭裡那個 git 從 tree 解出的 object id 重算
  比對,對不上就當缺席。新增 `verified_blob_bytes` 單路徑入口;`anchor_floor`、
  `s2e_review`、`s2e_launch`(carrier)原本用 `show` 的**每一處**都改走它。家族內
  已無未驗證的 blob 讀取,並由 AST 斷言執法(只掃代碼字面量,不掃 docstring)。
- *前提*:sha256 object format 顯式拒(`STORE_UNSUPPORTED_OBJECT_FORMAT`)——sha1 重算
  對它恆假,而恆假的完整性檢查比沒有更糟。
- 實測:竄改唯一一份 loose 物件後,`git cat-file -p` 回 `EVIL CONTENT`(rc=0),
  `commit_blob_bytes` 回 `{path: None}`,兩支 `_verified_bytes` 都 `OSError`。

**NEW P0-2(物化不是快照)** —— `_materialize_object_store` 改為逐**物件**:view 內的
fanout 是真目錄,裡面逐檔 symlink,每檔連結時驗 `S_ISREG`(拒 symlink)且驗 owner。
實測:被驗者在自己 fanout **內**放的 symlink 不被連(E2 那條 100% 無競爭洩漏關掉,
`cat-file` rc=128);view 建好後才寫入的物件不可見(E3 靠預建 256 個空 fanout 讓 store
保持活的那條關掉)。216 個 loose 物件的 repo 一次 view 約 30 ms。

**NEW P0-3(ledger 可重指到任意目錄)** —— `subject_common_dir` 改收 `repo_root` 並回
`subject_layout(repo_root).common_dir`,`s2e_consumption._git_common_dir` 隨之只解析一次
且是驗過的那一次。原本的巢狀兩層(`subject_common_dir(subject_git_dir(...))`)對同一個
被驗者可寫檔讀兩次、第二次不驗,E3 racer 3000 次 relocated 555。回歸測試以 AST 斷言
「恰好一次解析呼叫,而且是驗過的那一支」。

三條各帶回歸測試(`test_blob_bytes_must_hash_to_the_object_id_the_tree_records`、
`test_materialized_store_links_objects_not_directories`、
`test_consumption_ledger_resolves_its_common_dir_exactly_once`),每一條都先確認
「不修的話 git 真的會把假東西交出來」再斷言本家族拒收。

### 未收(具名留給下一輪)

0. **P0-A 的另一半仍未收**:同 uid 的重指沒有被擋住(被驗者可把 commondir 指到另一個
   自己的 repo,或用只含 `objects/` 與 `worktrees/w/` 的合成目錄,取得一份空的
   consume-once ledger)。owner pin 擋掉跨 uid,回指不變式已因空洞而移除。真正的收法是
   把 ledger 綁到 caller 選不了的身分,屬另一個 scope。該缺口已寫進
   `test_gitdir_pointer_redirect_is_pinned_to_the_subjects_own_uid` 的斷言,所以「收掉了」
   必須靠改測試宣告,不能靠改文件。
1. ~~**第七個登記面被漏掉(E2 P1-3)**~~ **已收,且該發現一半不成立。** E2 報
   「簽名不再涵蓋這段代碼」——實測不對:`_s2e_review_source_paths` 走
   `_repo_python_import_closure`,而 `schema_core` 於 top-level 匯入 view 葉,所以它本來
   就在 reviewer 簽名的 `source_blob_manifest` 裡(實測 175 條 closure 內含它)。
   成立的另一半是:涵蓋不該只靠某條 import 恰好存在。已依 `s2e_dispatch.py` 的先例把它
   顯式列進 `S2E_REVIEW_BASE_PATHS`,並在既有的先例斷言旁加上同型斷言。
2. **已 commit 的 wave-exit receipt 因本輪失效(E2 P1-4;自行複算後修正數字)**:
   把新葉列進 `_W0/_W2/_W3/_W5_OWNED_PATHS` 改變了
   `canonical_digest(sorted(_WX_OWNED_PATHS))`,而 `wave_w2:468`/`wave_w3:751`/
   `wave_w5:1630` 拿它與 receipt 的 `owned_path_manifest_digest` 比對。實測
   `docs/.../receipts/S2.4-WP4-W{0,2,3,5}/` 底下 **14 份** receipt(含 `regenerated-*`)
   現在對不上;E2 報 4 份是低估。
   **一點必要的區分**:其中 `S2.4-WP4-W0-wave-exit-receipt-v1.json` 帶 `74e51a48…`,
   而各波的 `regenerated-W0-*` 帶 `00674c05…`——兩者本來就不一致,**那一份在本輪之前
   就是 stale 的**,不能算到本輪頭上。其餘 13 份是本輪造成的。
   `owned_path_diff_digest` 同步移動。這是與 W5 re-emission 同一類的投影義務,屬
   PM/operator 範疇,本輪只揭露不代發。
3. **`--separate-git-dir` 與 submodule 工作樹被拒(E2 P2-6 / E3 P1-5)**:git 只為 linked
   worktree 寫 `<gitdir>/gitdir`,而本輪對所有 `.git` 指標檔都要求它;且錯誤被報成
   `STORE_UNREADABLE` →「object store is unreadable」,理由字串說謊。symlink 形的 `.git`
   同樣被拒。
4. **例外紀律仍不完整(E2 P2-8)**:`s2e_launch:1497`(與 `:1379` 同一函式,只有 1379 有
   try)、`:1180`、`s2e_review` 八處、以及 `_git_binding_errors` 沒接 `TimeoutExpired`
   (本輪剛加了 `timeout=180`,所以現在可達)。
5. **`command_capture_v2` / `generation_summary`** 仍是同一缺陷類別的未修實例(round-5
   E2 F1),不在 path manifest 內。
6. **subprocess 輸出無尺寸上界**(E3 round-5 P1-5 後半):E3 實測 1.2 MB 的 `.git` 把
   RSS 推到 687 MB。timeout 已補,記憶體未封。
7. **`agent_governance_s2e_lw1_action_packet.py`**:PM lane 獨佔,未碰。
8. **測試鑑別性**:P0-A 的回歸測試如上不具鑑別性;
   `test_materialized_store_excludes_the_graph_surfaces...` 的走訪斷言對 P0-C 是空的
   (它寫的 commit-graph 是誠實的),真正承重的只有 `assert not (view/objects/info).exists()`,
   而 docstring 宣稱的 multi-pack-index 那一句沒有對應斷言。
9. **reftable ref backend 未鏡射**,偵到即 fail-closed。
10. **owner pin 的前提未寫明(E3 P2)**:`repo_root` 先 realpath 再由目標導出 owner,
    所以 pin 對「連 repo_root 路徑本身都被重指」的情形自我一致、偵測不到。應由 producer
    傳入預期 owner uid,而不是自行導出。

### 複核狀態(2026-08-09)

| 輪 | E2 / E3 | 結果 |
|---|---|---|
| round-5 初版 | 都跑了 | E2 F1 等 + E3 三條 P0 |
| round-6 拆分波 | 都跑了 | P0-B/P0-C 確認關閉;P0-A 半關;三條 NEW P0 |
| round-7 三條 P0 收口 | **未跑** | 派工當下撞到 usage 上限,見下 |

**round-7 的全部改動未經對抗複核。** 前兩輪各自證明了「上一輪的修復本身帶新缺陷」
(round-6 修 round-5,被 round-6 複核抓到三條新 P0;round-7 修那三條),所以這一輪
**必須**補第三輪 E2/E3 才能談 merge。已派工但因 usage 上限中止,待額度恢復後重派。

證據面現況:凍結 HEAD `41dfab03a`、乾淨工作樹的完整掃描為
**8087 passed / 0 failed / 56 skipped / 0 error**(68 分 06 秒,exit 0)。這證明沒有回歸,
**不**證明三條 P0 的收法沒有新洞——那正是第三輪要查的。
