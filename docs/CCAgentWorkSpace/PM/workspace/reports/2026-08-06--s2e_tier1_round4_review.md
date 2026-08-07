# S2E Tier 1 durability anchor — 第四輪三路獨立複核（PR 前 exit review）

日期：2026-08-06
受審：`agent/aiml-s2e-tier1-durability-anchor-20260802` @ `8d070334e`，baseline `origin/main`=`e8d7d2454`
複核角色：E2（對抗代碼）／E3（安全）／E4-verifier（測試證據），三路獨立並行，互不讀對方輸出
PM：逐條複驗關鍵項，非轉述

## 一、裁決

**第四輪初判 FAIL**（E3 FAIL／E4 FAIL），修復後複驗放行。兩條 P1 都是**本分支自己引入**的，
且都不是前三輪找過的東西——這是第四輪存在的理由。

| 輪次 | 受審 head | 裁決 |
|---|---|---|
| 第一輪 | `4826a761b` 世代 | FAIL（4×P1＋6×P2） |
| 第二輪 | `b1f67d8d7` | FAIL（E2/E3 FAIL、E4 PASS 附三項必辦） |
| 第三輪 | `5ed9d7729`→`6f563c299` | 九項全收（無報告檔，findings 只在 commit message） |
| **第四輪** | **`8d070334e`** | **FAIL → 修復後 PASS**（本檔） |

## 二、兩條 P1（各由一路獨立發現，PM 複驗成立）

### R4-1（E3）· `safe.directory` 把 git 的 fail-closed 換成一條提權路徑

`aiml_gate_receipt_schema_core.py` 的 `git_argv()` 帶了 command 域的
`-c safe.directory=<repo_root>`。它的誠實邊界註解寫「本家族只跑
rev-parse/for-each-ref/log/show/merge-base/cat-file/config，都不評估會執行外部程式的
config key」——**兩個子句都是假的**：本家族實際跑 `git status`（`_require_clean`，全 repo 15 處），
而 `core.fsmonitor` 正是會執行外部程式的 config key。

E3 實測（git 2.50.1，2026-08-06）：`git -c safe.directory=<repo> -C <repo> status` 會執行
`.git/config` 裡的 `core.fsmonitor`；`status` 與 `diff` 觸發，`log`/`show`/`rev-parse` 不觸發。
於是在**該旗標自己引用來授權自己的那個差異 uid 拓撲**（root-owned producer 讀 `ncyu` 所有的 repo）
底下，寫得了 `.git/config` 的**非 root repo owner** 可以驗證器身分執行任意程式。
同 uid 時不是提權（寫 config 的人就是驗證器自己），所以嚴重度綁在該旗標的正當性理由上。

**收法**：移除 `safe.directory`，恢復 git 原生拒讀。逐鍵 denylist 不是可收斂的解——
`filter.<drv>.clean` 經 `.gitattributes` 走同一條路，而 `filter.*` 的驅動名無法窮舉。
差異 uid 的放行改由 operator 寫進 **root 自己的** protected config
（`git config --system --add safe.directory <path>`），那是 git 設計該功能的位置，
也是 repo owner 寫不到的位置。E2 F-05 指出的失敗仍在，但它是**大聲且 typed 的 REJECTED**，
不是靜默放行——這正是它該有的形狀。回歸：舊測試 `..._reads_a_repository_owned_by_another_uid`
斷言同情境得 `FLOOR_VERIFIED`，已翻正為 `..._refuses_...`；另加
`test_git_argv_does_not_trust_the_repositorys_own_config`（argv 不得含 `safe.directory`；
差異 uid 底下 hook 不得被執行）。

### F-1（E4）· 分支留下一條 baseline 綠、HEAD 紅的測試

`program_code/ml_training/tests/test_aiml_gate_receipt_validator_s2_4.py:1029` 斷言
`len(SCHEMA_FILES) == 93`。本分支退掉一個 schema、加入兩個，實值為 **94**。
`test_agent_governance_s2_5_recovery.py:1944-1945` 的孿生斷言（59→60、93→94）改了，這條漏了。
E4 在乾淨 baseline worktree 實測：`e8d7d2454` 綠、`8d070334e` 紅，0.09s 就跑完。

**這條的意義不在一行數字**：兩個 commit message 都寫「Five S2E files: 127 passed」，
而那五個檔是作者自己挑的——**綠色只覆蓋被挑的範圍**，紅的那條剛好不在裡面。
證據範圍由被審者自選時，「全綠」是一句關於選擇的陳述，不是關於分支的陳述。

E2 獨立得到同一條，並要求「檢查五個 S2E 檔之外是否還有 baseline 綠、branch 紅的斷言」。
PM 據此把回歸面擴到 14 個檔，**又抓到兩條同族**：
`test_agent_governance_s2_5_recovery_anchor_schemas.py:103` 與
`..._store_schemas.py:287`（`617 passed / 2 failed`）。再全 repo grep 出**第三條**
`test_agent_governance_s2_2b.py:110`（它連 14 檔集合都不在裡面）。
四條全部是同一個 `SCHEMA_FILES == 93`，四條全部修為 `94`。
一條漏改是疏忽；四條漏改而 commit message 寫「全綠」，是證據範圍的問題。

## 三、P2（已收）

- **R4-3（E3）· 模組 docstring 過度宣稱**：`aiml_gate_receipt_s2e_external_evidence.py` 的
  `validate_s2e_durability_anchor_attestation` 寫「spec 的兩條否定條款在結構上成立：只取得
  anchor host 的 root 拿不到第二台機器對改寫後 head 的簽章」。該句只涵蓋私鑰放在哪裡，
  漏掉更強的事實：replica 的信任根是 `/etc/arcane-equilibrium/aiml/s2e-offhost-replica-trust-root-v1.json`，
  **host root 改得動它**，於是根本不需要第二台機器的 key。設計正本 §5.3 寫對了，docstring 沒跟上。
  依 2026-08-03 operator 裁決（不宣稱 §LW1 externality），這正是被撤回過的方向。已改寫為
  逐條列出代碼「實際執法什麼」，並明寫「能寫這兩個 `/etc` 檔的人可以在同一台機器產出兩份簽章，
  代碼偵測不到」。
- **R4-4（E3）· operator 正面貼用文件會直接吃拒絕**：provisioning prompt 說 predecessor registry 的
  `attestor_class="EXTERNAL_APPEND_ONLY_PREDECESSOR_REGISTRY_V1"`，代碼要的是 `HOST_...`（Tier 1 已改）；
  又說四份 profile 欄位集合一律「完全等於這 9 個」，但 durability anchor 與 off-host replica 是 **10 個**
  （多 `host_fingerprint`）。fail-closed 方向，但這份文件的存在意義就是別讓 operator session 白燒，
  照著做保證吃兩次 `trust root fields are not exact`／`attestor_class is invalid`。連同殘留的
  「9 項」「14 項」舊數一併更正為 11 項／16 項。
- **R4-2（E3）· `patternProperties` 漏改**：`agent_governance_schema.py:170` 仍是裸 `re.compile`，
  於是 `6f563c299` 宣稱的「本檔是全 repo 556 個 pattern 唯一的 ECMA 忠實執行點」對這一側不成立
  （`$` 在 Python 允許尾隨換行）。不從任何 S2E anchor schema 可達，但 `s2_4_dependency_refresh_attestation_v1`
  等三個 schema 用得到。兩側現在共用 `_compiled_pattern`。

- **R4-1b（E2）· 誠實邊界註解漏列 `status`**：`git_argv` 的 enumeration 對它列出的指令
  是對的（E2 逐項實測：`log`／`show`／`rev-parse`／`merge-base` 都不觸發 fsmonitor），
  **錯在漏列**——而漏掉的那一個正是唯一會觸發的。已隨 R4-1 一併改寫。
- **R4-4（E2）· 設計正本的前置算式自相矛盾**：`design/S2E-LW1-tier1-remediation.md` §4.4 寫
  「新增第 11 列」與「**11 path + 4 service = `16`**」——11+4=15，算式本身就不成立。
  實測活值 `len(_PATH_PREREQUISITES)=12`／`_SERVICE_PREREQUISITES=4`／`EXPECTED_ACTION_IDS=8`；
  代碼、committed packet 與 `TODO.md` 一直是對的 16，只有設計正本錯。同段「3 份 JSON profile」
  實際出貨 4 份。**這是本檔第二次前置數算錯**，故以具名更正保留，不原地抹除。
- **R4-9（E2）· 同一個 dict 裡兩格待遇不一致**：`AnchorGateObservations` docstring 說
  `floor_verdicts`「程式消費者有兩處」，而那兩處都只是把值序列化成 stdout JSON；
  同一份 dict 裡的 `host_identity` 卻誠實記為「無程式消費者」。同一份 docstring 隨即自承
  「gate 行為完全由 `errors` 決定」。寬鬆的那一半已改為「序列化出口」，兩格的程式消費者
  同記為零。TODO 與 commit message 本來就寫對，只有 docstring 沒跟上。
- **R4-5（E2）· provisioning prompt 殘留舊數**：`:174`「9 項逐檔實測狀態」、`:177`「14 項 blocker」
  ——round-1 P2-5 的殘渣。與 R4-4 同批改為 11 項／16 項。

## 四、不改、只記錄的項目

- **F-2（E4）· 本 PR 不得 squash-merge**：`test_agent_governance_s2e_lw1_committed_action_packet.py:89-96`
  斷言釘住的 `implementation_checkpoint_head`=`970734ae0` 是 `HEAD` 的祖先。`gh pr merge --merge`
  保住它；**squash 或 rebase merge 會讓它在 main 上永久紅**，且
  `test_..._is_regenerable_by_its_generator`（clone 後 detach 到該 commit）一併紅。
- **R4-7（E2，P2）· round-2「should」第 12 項第三次原封未動**：
  `2026-08-02--s2e_lw1_external_prerequisite_action_packet.json` 的 `required_action_ids`
  仍列 `COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR`，但該 floor 已於 `fdf3c0fa6` commit；
  `EXPECTED_ACTION_IDS` 是靜態 tuple，generator 不與現實比對，因此**沒有任何測試抓得到**。
  packet `source_binding` 仍釘 `970734ae0`。方向是 fail-closed（叫 operator 去做一件已完成的事），
  但真修法要改 generator 語義＋重算 packet digest＋同步 TODO 與測試釘值，屬另一件工作。
  **具名結轉，不再靜默。**
- **R4-8（E2，P2）· 三個 commit 的 bisect 紅窗**：floor 路徑於 `447e5bad7` 進
  `S2E_REVIEW_BASE_PATHS`，floor 檔案到 `fdf3c0fa6` 才加入；E2 實測該窗內 review oracle 報
  `required S2E review Git blob is missing`。違反設計 §九「每一步結束都是合法停點」。
  修它要改寫已推的歷史，代價高於收益。**具名結轉，不再靜默。**
- **R4-10（E2，P2 資訊性）**：`issuance_result_digest`／`verification_result_digest` 現在涵蓋
  `anchor_gate_observations`，其中嵌了 `LOCAL_HOST_KEYS_OBSERVED`／`UNREADABLE`
  ⇒ **digest 依驗證主機而異**（Mac 與 trade-core 同輸入不同值）。今日惰性：兩個 digest 都無
  自我一致性測試以外的消費者。一旦被當證據使用即成真缺陷。
- **E3 的三項 P3**（E3 與 E2 各自獨立編號，ID 有重疊，此處以角色區分）：
  `_GIT_SEARCH_PATH` 含兩個 stock macOS 下 user-writable 的目錄
  （`/usr/bin/git` 先命中，今日不可達）；256 revision × timeout 的最壞 wall bound 約 6.4h；
  `_floor_shape_errors` 讀 commit bytes 但用 working-tree schema 判形（schema 檔在
  `S2E_REVIEW_BASE_PATHS` 內，且 current-generation 路徑有 `_require_clean`，部分緩解）；
  `--repo-root` 未綁 `parents[2]`，指向另一份 clone 可繞過 protected-ref 綁定——該綁定本來就
  只宣稱擋意外與漂移，wrong-clone 是它擋不住的漂移之一。以上均記為 debt，不在本輪修。
- **`host_identity` 仍無程式消費者**（E2 F-07，模組自陳）：不改，繼續具名。

## 五、三路各自確認為真的部分（不因初判 FAIL 而抹掉）

E3 以**建構**（scratch repo，非讀碼）逐項驗證後確認成立的安全性質，摘要：
E3-A（PATH 繼承 RCE）確實關閉——惡意 `git` 置於 `PATH` 最前且 `GIT_EXEC_PATH` 同指，
`git_executable()` 仍回 `/usr/bin/git`，假二進位從未被執行；orphan-branch 偽造
`ADVANCED gen=4242` 得 `REJECTED`，且**再打一條 `git update-ref refs/remotes/origin/main`
仍 `REJECTED`**（P1-4 對偽造 protected ref 亦成立）；未合併的 floor 推進得 `UNVERIFIED` 具名，
無 fail-open；`at_commit` 形狀驗證先於任何 subprocess（`--output=...`、12-hex、尾隨換行全 REJECTED）；
ambient `GIT_DIR`/`GIT_CONFIG_COUNT` 全被中和；grafts／replace ref／promisor／`--depth 1`
各自具名 REJECTED；固定路徑無 traversal；schema 錨點修正雙向正確
（`sha256:<64hex>\n` 現在拒、`(^|/)\.\.(/|$)` 仍以 search 命中）；`UNVERIFIED` 可達且不可升級
（`_floor_reading` 是全 repo 唯一構造點）；`now` 永不由 caller 提供；
`require_current_freshness=False` 只有一個 caller，且 ≤600s 窗長在兩條路徑上都無條件強制；
跨 receipt 的 monotonic 鏈釘死在 committed bytes，創世重放被三重擋；
floor artifact 與 `aiml_gate_receipt_s2e_anchor_floor.py` 皆已入 `S2E_REVIEW_BASE_PATHS`，
reviewer 簽名的 `source_blob_manifest` 逐位元組釘住它們；trust-root 讀取 fail-closed
且 TOCTOU 硬化（`O_NOFOLLOW`、`fstat` `S_ISREG`、`st_nlink == 1`、uid 0、mode 恰 `0644`、
≤16KB、拒重複 key、欄位集合精確相等、fingerprint 由 public key 重算）；
`EXTERNAL_WORM_V1` 現在具名 fail closed；全 tree 無殘留 WORM 引用；
9,156 行 diff 內**零密鑰／憑證／高熵 blob**。

E2 獨立跑了 **17 個變異，全部 KILLED**（protected-ref 綁定、generation 嚴格遞增、chain-head 必為
`GENESIS_ARMED`、`_object_store_errors`、40-hex `at_commit` 形狀、`_FLOOR_INVARIANT_FIELDS`、
`floor_gate_errors`、grafts、promisor、`durability_anchor_floor_errors`、
`durability_anchor_floor_binding_errors`、`durability_anchor_transition_order_errors`、
`next_floor_projection` None-guard、issuance `observations=` 接線、replica 第二把簽章、
四個 host-fingerprint 檢查、`_freshness_errors`）。其中一個在窄選擇下 survived、放寬後被
round-2 M14 的 `test_advanced_floor_rejects_a_replayed_generation` 殺掉——**E2 對每個 survivor
都重跑更寬的選擇**，這是正確的方法論：KILLED 是可靠結論，窄選擇下的 SURVIVED 不是。
E2 另獨立復現 baseline「五個 S2E 檔 127 passed」（20m36s）。
E4 的變異矩陣 **8/8 全被殺**（committed anchor floor 讀取、2-of-2 key 分離、replica 第二把簽章、
replica host-fingerprint↔trust root、replica ≠ 本機 key、freshness window、floor verdict 傳遞、
floor generation 嚴格遞增、protected-ancestry）。這與第一輪「整段刪掉、72 個測試全綠」是相反的形狀。
斷言訊息釘定全面（`assert errors` 之後一律跟一條訊息 pin），無 wall-clock 日期腐化 fixture
（時間一律以凍結字面量經 `now=` 傳入，兩處 issuance 走 monkeypatch）。
manifest cost guard 的更正屬實：baseline `e8d7d2454` 實測 **254**、HEAD **257**，
上界 264，註解與實值相符。

## 六、誠實邊界

- 本輪全部證據為 **Mac 本地 source／scratch-repo 觀察**（`LOCAL_REPRODUCIBLE`）。
  零 runtime、零 PG、零網路、零 service、零 broker；不構成 closure-admissible 的強 PASS
  （E4 明確聲明其四元組是**未經 attest 的直接執行**，因為 dispatch 未綁 admitted node-id）。
- **三支 root-owned producer 能力（`attest-v2`／durability anchor／predecessor registry）仍未實作**，
  11 個 `/etc/arcane-equilibrium/**` 信任根在任何 host 上皆不存在，`ncyu-nas:22` 仍 Connection refused。
  沒有任何真實 attestation 曾被端到端驗證過。所有簽章路徑都只跑過 repo 自己的 fixture。
- 代碼在 2-of-2 上**實際**執法的是：兩份 SSHSIG 各自對兩個 root-owned 檔驗過、兩個 `key_fingerprint`
  互異且都異於 receipt signer、`replica_host_fingerprint` 等於其信任根宣告值且異於 anchor、
  且不在 `/etc/ssh/ssh_host_*.pub` 內。**能寫這兩個 `/etc` 檔的人可以在同一台機器產出兩份簽章。**
  §LW1 externality 依 2026-08-03 operator 裁決**不被宣稱**，`UNVERIFIED` 是誠實終態。
- 變異矩陣是測試強度的**下界**：8 個具名執法被殺不等於全分支覆蓋完備。
- E2 於第四輪中途遭 session 用量上限中斷，恢復後以有界預算交付；其未觸及的範圍逐項記為 NOT REACHED，
  不以「未發現」冒充「已檢查」：三個變異（git timeout、`git_executable`/`PATH` 釘定、
  `_compiled_pattern` 翻譯器）只讀碼未執行變異；未跑完整 `tests/structure`；
  `aiml_gate_receipt_s2e_review.py` 的 predicate oracle 內部與 `s2_5_recovery`／
  `application_bundle_runtime_closure_v1.json` 的 delta 只看 diff，未對抗性探測。
- E2 的裁決**只綁 `8d070334e`**。它交付時工作樹已含本輪修復的未提交改動（E2 明確聲明那些不是它寫的，
  且不在它的複核範圍內）——這是正確的邊界宣告。本檔的修復面由 PM 負責，並以修復後的完整回歸承擔。
- **三路的 P0-1 判讀一致**：E2 逐檔查遍 source／docstring／design／TODO，**找不到任何一句**
  把 `UNVERIFIED` 講成已達成 §LW1 externality。這是這條鏈上第一次三路都確認誠實面沒有破口。

## 六之二、第五輪(PR #178 Codex review)四條 thread 的收口

開 PR 後 Codex bot 提四條未解 thread,逐條在 source 複驗後全部成立:

- **P1 `aiml_gate_receipt_s2e_launch.py`**:`validate_s2e_launch_transition` 只對候選 anchor
  做 locator/generation 排序,**從不認證它**;把候選 SSHSIG 與 `attestation_digest` 換成任意值,
  公開 `transition-gate` CLI 仍回零錯誤並印 `ADVANCE`(PROGRESS 把它列為 LW2 解鎖條件)。
  前一份的 review anchor 一直有被認證,候選的沒有。收法:`acceptance_review_bundle` 成為
  必填參數(刻意無 default),bundle 先與這張 receipt 對綁,再以
  `terminal_payload_digest(s2e_acceptance_review_worm_payload(bundle))` 認證候選 anchor。
  **修復第一版自己踩到一個洞,由 E4 實測抓到**:`PENDING_REVIEW` 候選依
  `_common_payload_errors:428` 不得帶 `acceptance_review_bundle_digest`,故第一版的等式
  恆假、`elif` 短路,**anchor 認證那一支永遠走不到**,且 wave issuance 會永久 pending。
  repo 內沒有任何測試把 wave receipt 發到 READY,所以沒有測試會紅——具名為覆蓋缺口。
  現由 `_bundle_binds_this_candidate` 分兩種合法形狀處理。
- **P1 `aiml_gate_receipt_schema_core.py`**:第四輪撤掉 command 域 `safe.directory` 時,
  我寫給 operator 的替代出口是 `git config --system --add safe.directory <path>`。
  **那句是錯的**:`git_subprocess_env()` 設 `GIT_CONFIG_NOSYSTEM=1` 且不帶 `HOME`,
  system 與 global 兩個 protected 域都讀不到,而 `safe.directory` 只在 protected 域生效。
  PM 獨立實測(git 2.55.0,以 `GIT_CONFIG_SYSTEM` 指向含該條目的 config):不帶
  `GIT_CONFIG_NOSYSTEM` 時差異 owner 讀取成功,帶上即 `dubious ownership`。
  更根本的是**就算打開也不該用**——放行等於讓 git 讀非 root 所有的 repo 的 local config,
  `core.fsmonitor`／`filter.<drv>.clean` 隨之回來,就是 R4-1 本身。
  收法:刪掉那條指示,明寫**差異 uid 拓撲目前無受支援的放行路徑**,真正的解在設計層
  (不對外人所有的工作樹跑 `git status`,改從 code-owned bare view 取事實),
  列為三支 root-owned producer 實作的前置設計項。同一段兩次都是「想給一條方便的出口」
  而沒有先實測那條出口——第二次由外部 reviewer 抓到。
- **P2 `aiml_gate_receipt_s2e_external_evidence.py`**:predecessor registry 的
  fingerprint 分離只比 receipt signer 與 durability anchor,**漏了 off-host replica**。
  provisioning 契約要求四個簽章身分互不共用 key;漏這一格等於 replica key 被攻破也能偽造
  single-use registry grant,而 replica 私鑰依設計放在 `ncyu-nas`。已加入 peers。
- **P2 `aiml_gate_receipt_s2e_dispatch.py`**:acceptance-review 的 typed pending 訊息仍要求
  "external WORM evidence",而 Tier 1 已刪掉那份 provider 契約;測試還把該字串硬編下來。
  照這句去做的 operator 會去要一份不存在的東西。已改為 durability anchor＋off-host readback。

本輪另一項結構後果:`aiml_gate_receipt_s2e_launch.py` 兩度越過 2000 行硬門檻。
acceptance-review 的簽章主體／WORM payload／bundle digest／共用 envelope 與
`_bundle_binds_this_candidate` 因此遷入 `aiml_gate_receipt_s2e_review.py`(acceptance review
本來就是該葉的內容),launch 葉逐名 import 回去,公開 ABI 不變。這是把內容放回它該在的葉,
不是為了行數硬拆。

## 七、本輪之後仍未做的事

W5 re-emission（含償還 `209793b70` 的漏發射）在本複核之後執行——`w5-emit` 需
`--review-provenance`，順序不可顛倒。LW1 exit 條件不變：W0 genesis 與 LW1 receipt 仍未發、
transition 未 ADVANCE、LW2 仍 locked、`S2E.2b-2` 未翻轉、production effect 0/6、九項 authority 全 false。
