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
  **撤回**「工作樹乾淨」這一條,並在代碼裡具名。理由兩條,缺一不可:
  1. **取不到**:跨 uid 沒有任何不經被驗者可寫執行面的取得方式(§1 兩條死路)。
  2. **不承重**:本家族每一項投影都走 `<commit>:<path>`(`commit_blob_bytes`),
     工作樹的位元組進不了任何 digest;髒樹改不了該 bundle 的任何結論。

  留下的是 view 真的能證、而且正是這個檢查要的那一條:**候選必須等於當前 HEAD 的
  commit 與 tree**。錯誤字串同步從 `not the clean current HEAD` 改為
  `not the current HEAD generation`——舊字串會繼續宣稱一件已經不再檢查的事。

## 4. 這組改動證得到什麼、證不到什麼

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
