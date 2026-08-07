# S2E Tier 1 remediation — 三路獨立複核（第二輪）：**FAIL**

日期：2026-08-03
受審：`agent/aiml-s2e-tier1-durability-anchor-20260802` @ `b1f67d8d7`，baseline `097c879b9`
裁決：**E2 FAIL／E3 FAIL／E4 PASS（附三項必辦）** ⇒ 總體 FAIL
PM 複驗：關鍵項逐條自行複算，非轉述

## 一、決定性結論：承重論證未被任何一行代碼執法

設計正本 §二與模組 docstring 都宣稱：git 是 §LW1 要求的「**外部**、由不同 owner/capability
控制、位於可替換 state root 之外」的持久層，因為「改寫 GitHub main 需要另一組 capability
（token＋PR＋required checks＋branch protection）」。

**E2 與 E3 各自獨立證偽這一句。** `grep origin/|remote|ls-remote|for-each-ref` 在
`aiml_gate_receipt_s2e_anchor_floor.py` 與 `aiml_gate_receipt_s2e_launch.py` **零命中**。
`at_commit` 一路來自被驗證者自己遞來的 receipt（`launch.py:942-947` 的 `source_head`、
`:1600-1602` 的 `reviewed_head`），`repo_root` 是 CLI 的 `--repo-root`。攻擊者**不必碰
GitHub、不必 rewrite 歷史**：

```
git checkout -b x <真 GENESIS commit>  →  commit 一份自製 floor  →  以該 commit 為 source_head
→  read_committed_durability_anchor_floor 回 errors == []
```

E2 的 `test_floor_read_at_an_unpushed_local_commit` 與 E3 的 PoC B 各自 PASS。

**後果**：spec §LW1「同一 writer 可 coherent rewrite ⇒ 只能得 `UNVERIFIED`」在代碼線上
**仍未成立**。floor 把「caller 遞一份 JSON」提升為「caller 遞一個 repository＋一個 commit」——
這是真實的成本上升，但不是規範要求的外部性。

**PM 自我更正**：我在 PROGRESS.md 寫「structurally unreachable rather than merely
promised」，這句話當時就沒有代碼支撐，是我採信設計敘述未自行查證。已撤回。

## 二、P0/P1 finding

### P0-1 · 同一 writer 用一條 local branch 即可取得任意 floor
`aiml_gate_receipt_s2e_anchor_floor.py:110-213`（無任何 ref/remote 綁定）
＋ `aiml_gate_receipt_s2e_launch.py:942-947,1600-1602`（`at_commit` 來自受驗 receipt）
＋ `agent_governance_s2e_launch_receipts.py:66-137`（`--repo-root` 由 caller 給）

E2/E3 獨立復現。`_is_ancestor` 不解決此問題：它比的是攻擊者自建鏈**內部**的關係，恆真。

### P1-2 · `at_commit` 對 git 的參數注入 ⇒ 任意檔案**截斷**
`aiml_gate_receipt_s2e_anchor_floor.py:122-132`（revision 位在 `--` **之前**，無
`--end-of-options`）、`:161`、`:191`；全模組**零 hex 驗證**（PM grep 複驗）。

**PM 實測（scratchpad，git 2.55）**：
```
printf 'SENTINEL-MUST-SURVIVE\n' > victim.txt
git -C <repo> log --format=%H --reverse --full-history "--output=victim.txt" -- .
→ exit=0；victim.txt 變成 0 bytes
```
E3 原報告寫「檔案被建立/覆寫」，**實際更嚴重：既有檔案被截斷為 0**。以 verifier 的 uid
可截斷任意可寫路徑——含 consumption ledger；若 gate 以 root 跑則含 `/etc` trust root。
未發現單 token 可達代碼執行。

**PM 修正一個過度連結**：截斷的是**工作樹**檔案，而 floor 走 `git show <commit>:<path>`
讀 commit 位元組，**故截斷 floor 檔不影響 floor 讀取**。P1-2 與 P1-3 是兩條獨立缺陷，
不構成鏈。

### P1-3 · 已 commit 的 0-byte floor ＝ **零錯誤 fail-open**
`aiml_gate_receipt_s2e_anchor_floor.py:146`（`last_raw = b""`）、`:167-169`（dedupe 的
`continue` 在 shape 檢查**之前**）、`:203`（`return previous_floor, []`）

PM 逐行複驗成立：第一個 revision 若為空檔 ⇒ `raw == last_raw` ⇒ `continue` ⇒ shape／
GENESIS／遞增檢查全跳過 ⇒ `previous_floor` 維持 `None` ⇒ 尾端 `head_raw == last_raw == b""`
⇒ 無錯 ⇒ 回傳 **`(None, [])`**。兩個呼叫點（`launch.py:951`、`:1607`）是 `if floor is not
None:`，於是整組 floor 規則靜默消失。E2 端到端 `test_EMPTY_committed_floor_is_fail_open`
PASSED，發出的 receipt 帶 `anchor_generation == 999` ＋ 捏造前手。

### P1-4 · floor 歷史不必以 `GENESIS_ARMED` 起頭
`:173-176` 只擋「index≠0 再進 GENESIS_ARMED」，不要求 index 0 必須是 GENESIS_ARMED。
orphan branch 上單一 commit 即可鑄出任意 `ADVANCED/gen=N`（E2 case F、E3 PoC C，皆零錯誤）。
設計 §3.4.3／§3.5 明文要求「只允許出現在鏈的第一個 commit」，實作只做了前半。
**且此洞已被測試固化為正常行為**：`test_..._launch_receipts.py:2851-2862` 自己就從
`_advanced_floor(2)` 起頭建歷史。

### P1-5 · shallow／不完整 object store ⇒ 歷史檢查變 no-op
`:119-141`。E2 實測：同一份被 rollback 的 repo，full clone 判紅、`depth=1` shallow clone
回 `(gen=2, errors=[])`。無 `--is-shallow-repository`／replace-ref 檢查。
`.github/workflows/ci.yml` 僅 3 個 checkout 帶 `fetch-depth: 0`，其餘十餘個用預設 depth 1。

### P1-6 · 環境未淨化，ambient `GIT_DIR` 蓋過 `-C`
`:60-65`、`launch.py:239-256`（皆無 `env=`）。E3 實測：`repo_root` 指真 repo 但 `GIT_DIR`
指攻擊者 repo 時，回傳攻擊者 repo 的 floor，`errors == []`。與 CLAUDE.md 封殺直接 `psql`
的理由（ambient `psqlrc`／`PG*` routing）同型。

## 三、確認關閉的（不因總裁決抹掉）

| 上輪 finding | 本輪 |
|---|---|
| P1-2 readback 自簽自證 | **CLOSED**。replica 走獨立 trust root＋第二把 SSHSIG；E2 實測用 anchor key 簽 replica 側 ⇒ 雙向 typed 拒絕。三個 `const:true` 已刪，死碼消失 |
| P1-4 綁定可整段刪而全綠 | **CLOSED**。E2 重做上輪 mutation ⇒ `10 failed, 90 passed`；E4 的 M9a/M9b 同樣 KILLED。斷言逐字錯誤訊息，非 `assert errors` |
| P2-1 假 predicate | **CLOSED**（`s2e_review.py:776-783` 已改名） |
| P2-3 replica 無 freshness 下界 | **CLOSED**（重用 `_freshness_errors`） |
| P2-6 提案未標 superseded | **CLOSED** |
| P1-3 `localhost` 通過 | **PARTIALLY**。原字面攻擊**仍全部 `errors == []`**（locator 後段仍是自由字串），改由 host fingerprint 不等承擔。路線合法（複核 §六第 3 項給的替代），但**不得宣稱「off-host 已被執法」** |
| P1-1 monotonic head | **PARTIALLY**。同一 ancestry 內單調性是真的（E2 的 merge/evil-merge/sibling 四種 topology 全被擋、E4 的 M1/M3/M4/M5 全 KILLED），但 ancestry 由 caller 選 ⇒ P0-1 |

E4 另確認：`--full-history` 有真測試背書（M5 KILLED，E1 加它的理由成立）；
`require_current_freshness` 豁免**精確**（唯一 `=False` 呼叫點是 `launch.py:808`，對象兩者
皆被已發 receipt digest 釘死、物理不可重鑄；窗長上界恆檢查由 601s 案例背書）；
`const:true` 是**真轉移且淨增益**（新 schema 零個 `const:true` 布林，且新增
`test_replica_flag_fields_are_rejected_by_schema` 反向封死舊面）；**日期腐化 0 finding**；
行數 1991／1983／418 全部復算相符、無越 2000。

## 四、E4 的三項必辦（mutation SURVIVED）

- **M11**：`_FLOOR_INVARIANT_FIELDS` 跨歷史不可變無測試。E4 判為 **E1 真漏想**，構造極簡
  （`_advanced_floor(1)` 後 commit 一份 `anchor_locator` 不同、gen=2 的 floor），三行可補。
- **M14**：ADVANCED floor 下 `anchor_generation == floor_generation` 的重放被放行
  （genesis 分支另有硬檢查，只有 ADVANCED 這支裸露）。
- **M10**（尾端 byte-for-byte）：E2 與 E4 **獨立同意 E1「構造不出」的結論**，但 E2 補充
  正確處置＝在 seam 層 monkeypatch `_git_bytes` 測（三行），E4 則主張標為
  defense-in-depth／known-untestable。兩者都認為「沉默的覆蓋債」不可接受。

## 五、PM 自己的錯，已更正

manifest 上界 256→288 我宣稱「加 floor 前已正好卡滿 256」。**E2 與 E4 各自獨立實測證偽**：
baseline `097c879b9` 的 LW1 manifest 是 **254**（尚有 2 格），本分支新增 anchor_floor 模組、
其 schema 與 floor 檔共 **+3**（並移除舊 WORM provider schema）⇒ 254 → 257，是本次改動吃掉
slack 並超出 1。我的說法是事後合理化。

E2 判 `ACCEPT_WITH_MANDATORY_CORRECTION`，E4 判「方向合理、幅度過寬、以假前提背書」。
已更正：測試註解改寫為真實帳（254 → 257），上界由無依據的 288 收窄為 **264**（257＋7 格），
TODO／PROGRESS 對應句同步更正。

## 六、放行條件（三路收斂，依優先序）

**必要**：
1. **P0-1**：floor commit 必須綁到 caller 無法選擇的 ref（最低成本＝要求
   `merge-base --is-ancestor <floor_commit> refs/remotes/origin/main` 為真）——**或**誠實地
   把 §LW1 裁決改成 `UNVERIFIED`，因為 §LW1 自己就寫著同一 writer 可 coherent rewrite 時
   只能得 `UNVERIFIED`。二選一，不得繼續維持「已達成外部性」的文字宣稱。
2. **P1-2**：任何 git 呼叫前 `^[0-9a-f]{40}$` 驗 `at_commit`；加 `--end-of-options`。
3. **P1-6**：`env=` 白名單，清 `GIT_*`。
4. **P1-3**：`last_raw` 改哨兵（非 `b""`）；dedupe 移到 shape 解析之後；
   `previous_floor is None` 時必回非空 errors；兩個呼叫點不得把 `floor is None` 當無事可查。
5. **P1-4**：鏈首必須 `GENESIS_ARMED/generation==0`，補 negative case，並修正
   `test_..._launch_receipts.py:2851-2862` 這個把洞固化為正常行為的 fixture。
6. **P1-5**：`--is-shallow-repository` ＋ replace-ref 檢查，非完整 object store fail-closed。
7. **E4 三項必辦**（M11／M14 補測、M10 標記）。

**應該**：
8. provisioning prompt 全量更新——E2 實測仍有 5 處「9 把」、`:16` 仍寫「Tier 1 下 3 項作廢」、
   表格**無第 11 列**、全檔 grep **零次** `ncyu-nas`、零次 keyscan，設計 §4.4 要求的
   A0／A4／A5 一項都沒寫。**Q2 的全部安全性都押在 provisioning 上，而 operator 真正會照著
   做的那份 prose 沒有這條**；照它做出來的環境必然驗不過。
9. E3 指出一件**本可執法卻被推給 provisioning** 的事：驗證器跑在 trade-core 上，可以讀
   `/etc/ssh/ssh_host_*.pub` 算本機指紋並要求 `replica_host_fingerprint != 本機指紋`。
   這不是設計 §5.2 拒絕的 loopback 黑名單，是與真實本機 key 的逐字比對。三行。
10. 誠實邊界補一句：兩份 `/etc` trust root 由 trade-core root 產生且可改寫，故 2-of-2 對
    host-root 威脅為零（`_read_trust_root` 的 TOCTOU 防護防的是非-root 替換）。
11. E2-P2-F：`447e5bad7`／`970734ae0`／`acca2095f` 三個 commit 上 review oracle 直接
    `raise`（floor 路徑已進 `S2E_REVIEW_BASE_PATHS` 但檔案要到後面才進 repo）⇒ 該區間
    紅、不可 bisect，違反設計 §九「每一步結束都是合法停點」。
12. E2-P2-I：committed packet 仍列 `COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR` 為
    operator 必做，但該 floor 已 commit；`EXPECTED_ACTION_IDS` 是靜態 tuple，validator
    不比對現況，此不一致無法被任何測試偵測。

## 七、誠實邊界

- 三路皆未取得 admitted node-id／context artifact ⇒ 全部 pytest 為 `LOCAL_REPRODUCIBLE`，
  **不是** closure-admissible `command_capture_v2`。
- E2 在報告中指出真工作樹於 10:51 被改成 `... and False:`。**PM 收尾複驗：工作樹乾淨、
  `:173` 完好、HEAD 仍 `b1f67d8d7`**——那是 E4 當時正在真樹上跑 mutation 的瞬間，E4 已還原。
  非第三方污染，但三路併行在同一工作樹做 mutation 是真實風險，下次應強制各自 clone。
- 本輪未執行任何 runtime／PG／broker／deploy effect。authority 仍 0/9、production effect
  仍 0/6、LW2 仍 locked、S2 未關閉。
