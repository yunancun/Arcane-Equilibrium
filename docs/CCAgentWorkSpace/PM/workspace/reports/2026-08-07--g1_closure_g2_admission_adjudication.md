# G1 收口裁決 ＋ G2 admission（2026-08-07）

**角色**：PM（決策與投影；本輪不是 source 實作任務）
**基線**：`main` = `b1d2eea034dcec9f0cfee2262abe75896bfc9f91`（PR #179 已 merge），worktree clean
**分支**：`claude/g1-closure-g2-admission-554cdd`
**證據等級**：本輪全部證據為 Mac 本地 `LOCAL_REPRODUCIBLE`，**不是** closure-admissible 強 PASS
**authority／effect**：九項 authority 全 false，production effect 0/6，S2 未關閉；本輪零 host、零
runtime、零 broker、零 order

---

## 〇、四項裁決摘要

| # | 事項 | 裁決 |
|---|---|---|
| 1 | G1 收口 | `DONE_SOURCE_LANDED`；同一 commit 內 G2 接任唯一 ACTIVE row，不出現零 ACTIVE 中間態 |
| 2 | G2 本體 | `LW1@SOURCE_READY` 與 `LW1@EXTERNAL_ATTESTED` 判定為**兩個必須機械獨立**的述詞；只 re-admit **LW2 source slice**；LW3–LW5 維持 WAITING；`S3.1A` **有條件**成為第二 writer |
| 3 | context store 結轉 | **不接進 transport／admission 面**；若日後要接，只接 persist 面，owner=E5→E1，先有 profile 才有實作 |
| 4 | action packet 過期 | 目錄維持 8 項，**必做清單改由 bound checkout 導出**；成因是「靜態清單 ＋ 早於事實的 pin」。第一版全域刪除是錯的（造出反向錯誤），已依 PR #180 Codex P1 更正 |

---

## 一、G1 收口裁決

### 1.1 五條 exit 條件逐條

| exit 條件 | 實測 | 判定 |
|---|---|---|
| 所有 active callers 有 machine-checkable 安全 transport | caller inventory 41 tracked 檔、零 active inline caller；`--context-artifact` 改 `@path`-only typed refusal（`agent_governance.py:459`）；`closure`／`closure-quality`／`project-closure` 的寬鬆 loader 一併補 size guard | MET |
| 原兩個 failing tests 經語義修復後全綠 | `tests/structure/test_aiml_s2_effect_host_run.py` = **48 passed／0 failed／0 skipped／0 error**（改動前 47 collected／45 passed／2 failed） | MET |
| adjacent regression 全綠 | 含新增 `test_agent_governance_context_transport.py` 合計 **65 passed／1 skipped**（skip = Linux 常數測試在 darwin 誠實跳過，非規避）；`test_development_agent_governance.py` ＋ `test_agent_governance_command_capture_v2.py` = **55 passed** | MET |
| Registry／context payload headroom 有 current Linux limit 證據 | trade-core 唯讀實測 PAGE_SIZE=4096、單 argv 上限 131,071 ⇒ MAX_ARG_STRLEN=131,072、ARG_MAX=2,097,152 | MET **但見 §五**：該實測由前一 session 當日取得，**本 session 無法複驗** |
| `agent_governance.py validate` PASS | `{"status": "PASS", "roles": 20}`（本輪重跑） | MET |

### 1.2 反作弊複核（由 operator 複驗、本輪採信）

PR #179 只動 4 檔；`.codex/agent_registry_v1.json` **零位元組變動**（即：不是靠改 Registry
把 cap 問題做掉的）；兩支舊測試是改寫更名，舊名保留在新 docstring；**零新增 skip／xfail**。
禁止事項（只調高 cap、刪除／skip／放寬測試、截斷 mandatory Context、把 source PASS 當
runtime）逐條未發生。

### 1.3 分項判定（closure_packet_v1 三欄分離）

- `work_status` = **DONE**
- `gate_verdict` = **PASS（source only, `LOCAL_REPRODUCIBLE`）**
- `disposition` = **CLOSED_SOURCE_LANDED**

G1 **不**主張任何 runtime 事實。source 三端同步、deploy、restart、runtime attestation
全部不在本輪，也不因 G1 收口而被授予。

---

## 二、G2 admission（本體裁決）

### 2.1 現況：code 裡目前**不存在** source／attested 之分

實測 `program_code/ml_training/aiml_gate_receipt_s2e_launch.py`：

- `S2E_WAVE_EXIT_IDS`（`:78-86`）把每個 wave 綁到唯一一個 exit id；
- `_ready_status_for`（`:620`）只認得兩種 ready：`W0_GENESIS_READY`、
  `TASK_BRANCH_CHECKPOINT_READY`，**兩者都只能由 receipt 產生**；
- `validate_s2e_launch_transition`（`:921`）是唯一的 ADVANCE 來源，且必須拿到
  candidate 自己的 durability anchor ＋ acceptance review bundle 才可能零錯。

而每一份 receipt 的發行都要穿過 16 項 external prerequisites（12 個 fixed host path ＋
4 個 service），其中 11 個 `/etc/arcane-equilibrium/**` 信任根不存在、`ncyu-nas:22`
Connection refused、三支 root-owned producer 未實作。

**結論**：今天「LW1 尚未 attested」與「LW1 的 source 尚未完成」在 code 裡是**同一個狀態**。
所以 LW2 的 source 作者權被 external prerequisites 綁架——這正是 G2 要拆的東西。
但也要說清楚：**這個融合在今天沒有造成任何錯誤放行**，它造成的是不必要的停擺；
拆開的收益是排程，不是安全。因此拆法必須是「加一個弱述詞」，不是「放寬既有強述詞」。

### 2.2 邊界定義（裁決）

| | `LW1@SOURCE_READY` | `LW1@EXTERNAL_ATTESTED` |
|---|---|---|
| 由什麼證明 | **只有 repo 位元組**：LW1 owned source manifest 於 bound head 存在且 generation 相符 | W0 genesis receipt ＋ LW1 wave receipt ＋ transition `ADVANCE`，且 16 項 prerequisites READY |
| 誰可以計算 | 任何 checkout，離線、無私鑰 | 只有具備 out-of-band trusted-host capability 的驗證面 |
| 它**授予**什麼 | 僅：**撰寫**下一個 wave 的 source slice 的權限 | receipt 發行、wave 關閉、`SOURCE_LANDED` 投影、任何 effect |
| 它**永遠不**授予 | `lw2_unlocked`、任何 exit id、任何 receipt、任何 effect、任何 authority | —— |
| 失敗時 | 只擋 source 作者權 | fail closed，維持現狀 |

**硬門不動**：16 項 external prerequisites 對 publication／production effect／platform
attestation／S2 closure 的要求，不得降低、改名、以模擬錨替代或以文字豁免。九項 authority
維持全 false，production effect 維持 0/6。

### 2.3 機械化規格（＝G2 剩餘 scope，本輪**不**實作）

新增一個 receipt-free 述詞（暫名 `s2e_wave_source_readiness_v1`），與既有 receipt gate **並存**：

1. **輸入**：`repo_root`、`wave` id、該 wave 的 owned source manifest（路徑 ＋ 期望 generation）。全部是 repository bytes。
2. **輸出**：typed verdict `SOURCE_READY` / `SOURCE_INCOMPLETE`，外加一個**恆為 false 且無法由本述詞改寫**的 `external_attested` 欄位。
3. **不可達性（必須有負向測試釘住）**：
   - `SOURCE_READY` 不得讓 `validate_s2e_launch_transition` 少回任何一條 error；
   - caller 提供的 `SOURCE_READY` 不得成為任何 receipt 的合法輸入；
   - 任何 package 的 `SOURCE_LANDED` 投影不得只由 source readiness 導出；
   - `closure_projection` 的七個 `const: false` 欄位不得被本述詞觸及。
4. **不得動**：`S2E_WAVE_EXIT_IDS`、`_ready_status_for`、transition gate、receipt schema、launch spec §LW1 全文。
5. **route**：PM → PA（介面）→ E1 → E2 → E4；surfaces 不含 runtime／bybit／ibkr。
6. **`SOURCE_READY` 的語義刻意收窄到「結構存在」（2026-08-09 依 Codex P2 更正）**。初稿把
   「exact-head 測試綠、review debt 已收」也寫進定義，但述詞的輸入只有 `repo_root`／`wave`／
   path manifest——**兩個 repo 位元組完全相同、但測試執行結果與 review 結論不同的狀態，
   在該輸入下不可區分**。所以照初稿實作只有兩種下場：要嘛忽略那兩項要求，要嘛謊稱已建立。
   正確的切法是：測試綠與 review provenance 屬於**另一個證據類別**（`command_capture_v2`／
   review provenance），repo 位元組推導不出來，硬塞進去會把這個「弱述詞」重新拖回需要
   attested capture。因此 `SOURCE_READY` **只**斷言結構存在；authoring admission 另外要求
   PM 在 task contract 的 `claim_inputs` 綁定 exact-head 測試 capture 與 review provenance，
   **在述詞之外**。述詞弱，是設計，不是疏漏。

### 2.4 LW2–LW5 逐波裁決

| wave | 其 acceptance 的性質 | 裁決 |
|---|---|---|
| **LW2**（S2E.2b-2 host-runner checkpoint） | 交付物是 S2.5 runner **source**；ABI 前驅 LW1 的 source 已在 main 上完整；固定序中它是下一個 | **RE-ADMIT source slice**（條件見下） |
| **LW3**（S2E.2b-3 五支 row driver ＋ kernel amendments） | TODO 明文「五支 driver 必須在真 disposable target 可執行；packet-ready 前 T2 不得 SKIP」——acceptance 本身是 execution-bound | **維持 WAITING**。它的 source slice 沒有可抵達的 closure，admit 只會產生無法收口的半片 |
| **LW4**（S2E.4 runtime-capture evidence kind／signer／closure schema） | 混合：schema／kind／signer 是 repo bytes，但 S2.0/S2.1 的 platform-attested success representation 不是 | **維持 WAITING**。其 source-only 子集**可能**可拆，但本輪沒有 PA 級的 path/ABI 獨立性證明；具名為下一輪的 PA 前置分析項，不在本輪 admit |
| **LW5**（S2E.5 disposable rehearsal） | acceptance 就是在 disposable target 上重放 | **維持 WAITING** |

**LW2 source slice 的放行條件（三條全滿足才可 dispatch）**：

1. §2.3 的述詞已 landed 並經 E2/E4 獨立審核——**先有機械邊界，才有依它排程的工作**；
2. 並行的 uid-topology writer session 已收口。它獨佔
   `aiml_gate_receipt_{schema_core,s2e_launch,s2e_anchor_floor,s2e_consumption,s2e_review}.py`，
   而 shared kernel／route／closure writer 依 TODO §LW map 全部串行；
3. dispatch 前重新確認 `S2E_WAVE_EXIT_IDS["S2E-LW2"]` 仍不可由 source readiness 觸及。

**LW2 source slice 的硬停止**：不得發行任何 receipt、不得接觸 host、不得把
`S2E_2B_2B_HOST_RUNNER_CHECKPOINT_READY` 投影為已達成、不得宣稱 LW2 已 landed。
它的合法終態是 `SOURCE_AUTHORED_PENDING_EXTERNAL_ATTESTATION`。

### 2.5 `S3.1A` 是否可作第二個互斥 writer

**依賴**：PROGRESS `S3.1A` 的 dependency 欄位為 `S2.3`，而 `S2.3@SOURCE_READY` 已 MET
（`sealed_build_receipt_v1`，PR #122 merge `051df8262`）。它 exits `SOURCE_READY`，
required effect 欄位是「classifier-derived PG/service **source**」——migration 是被**撰寫**，
不是被 apply。因此 S3.1A 的 source slice 本身不觸 host／effect。

**裁決：可以，但「路徑互斥」不是充分條件。** 兩個 writer 即使 owned paths 完全不相交，
仍共用三個 git 之外或跨檔的全局命名空間；dispatch 前必須先取得三項預留，否則兩條線會
在合併時互撞：

1. **`V###` migration 編號**——這是 git 之外的全局命名空間（本專案已有前例教訓）。S3.1A 若新增 migration，需先預留號段。
2. **`SCHEMA_FILES` 計數斷言**——現值 **94**，被至少四支測試逐一斷言（`test_agent_governance_s2_5_recovery_anchor_schemas.py:106`、`..._store_schemas.py:288` 等）。任一 lane 註冊新 schema 都會同時弄紅另一 lane。round-4 的 F-1（93 vs 94）正是這個形狀。
3. **governed review-manifest 上界**——基線 254 → 257，bound 264。這是共享預算，不是 per-lane 預算。

**投影狀態**：`S3.1A = READY_SECOND_WRITER_CANDIDATE_PENDING_NAMESPACE_RESERVATION`。
本輪**不 dispatch**（operator hard stop：不得順帶開始 S3）。

---

## 三、G1 結轉：context store 是否接進 transport 面

**事實**：`helper_scripts/maintenance_scripts/agent_governance_context_store.py`（424 行）
提供無損 content-addressed 去重，G1 實測 487,892 → 194,318 bytes（消除 60.2%），
`verify_round_trip` 逐位驗證，已有測試釘住。全 repo grep 顯示它**目前零 production
consumer**——只有自己的 CLI 與 `tests/structure/test_context_artifact_store.py`。
其 MODULE_NOTE 的硬邊界寫明：它是**儲存表示層，不是 admission gate**；所有消費面
（`validate_context_artifact` / `CONTEXT_ADMISSION_V1` / capture-command / closure）
只接受 resolve 後的全量 `context_artifact_v1`。

**裁決：不接進 transport／admission 面。** 三個理由：

1. **它買不到 transport 安全**。G1 已用 `@path`-only ＋ 讀取側預算把 argv 懸崖結構性移除；
   單一 argv 已不承載 payload。60.2% 省的是**磁碟**，不是 execve 參數。
2. **它會在 G1 剛加固的那道門上開新面**。admission 若接受 dehydrated 形式，就把「一份
   自我驗證的 payload」換成「payload ＋ blob store」，多出一個 resolve-time 的
   TOCTOU 面——而 G1 這一輪的主要工作正是把 stat/read 之間的窗口關掉。該模塊自己的硬邊界
   已經寫對了，不該被推翻。
3. **它的收益面已經有歸屬**。PR #172（WP-D）已把 store 落在 artifact 落盤面（39 份實測
   21.4MB → 3.0MB）。

**若日後要接，接在哪裡、誰接**：只接 **persist／retention 寫入面**，不接 reader／admission
面；owner = **E5 → E1 → E2/E4**；gate = admission 契約逐位不變（負向測試：admission 面收到
dehydrated 形式必須 typed 拒絕）。**前置**：必須先有 repository-reproducible profile 證明
compiled-artifact 磁碟成長是實際瓶頸，才可派 E1——與
`P2-W5-PROJECTION-MEMOIZATION` 同一紀律，不得沿用未持久化的歷史數值。

投影為 `P2-CONTEXT-STORE-PERSIST-FACE-ONLY`（DEFERRED，具名）。**不屬於 G2 scope。**

---

## 四、Action packet 過期修正

### 4.1 它不是一開始就寫錯

| 事實 | 實測 |
|---|---|
| packet 綁定的 checkpoint | `970734ae0`，2026-08-03 **04:35:38** +0200 |
| 該 head 的樹裡有沒有 floor 檔 | **沒有**（`git cat-file -e 970734ae0:…/durability-anchor-floor-v1.json` → ABSENT） |
| floor 何時 commit | `fdf3c0fa6`，2026-08-03 **04:40:35** +0200（晚 5 分鐘），且**是 `b1d2eea03` 的祖先** |

所以 `COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR` 在寫下的當時是對的。**腐化的成因是
「靜態清單 ＋ 早於事實的 pin」**，不是誰算錯項數。round-2（第 11／12 項）與 round-4
（「具名結轉」）兩度點名，兩度存活，因為沒有任何斷言把清單與 repo 事實比對。

**實害**：operator 照 packet 第 7 步會再 commit 一次創世 floor，而
`aiml_gate_receipt_s2e_anchor_floor.py:533` 明文拒絕鏈上第二個 `GENESIS_ARMED`。

### 4.2 第一版修法是錯的，Codex P1 抓到（2026-08-09 更正）

**初版把該 action 從清單全域刪除。** 那治好了「已完成卻仍要求」，卻造出反向錯誤：
packet 綁定的 pin `970734ae0` 的樹裡**沒有** floor 檔，在該 pin 上重建（
`test_committed_action_packet_is_regenerable_by_its_generator` 正是這麼做的）會產生一份
**漏掉一個當時真正必要步驟**的 packet，而且照樣通過驗證。逐條複驗後成立：全域刪除只是把
一種腐化換成另一種。

### 4.3 正解：清單由 bound checkout 推導

| 檔 | 改動 |
|---|---|
| `agent_governance_s2e_lw1_action_packet.py` | `CANONICAL_ACTION_IDS` 維持 **8 項有序目錄**；新增 `REPOSITORY_COMPLETION_WITNESSES`、`completed_action_ids(repo_root, at_commit=…)`（讀該 commit 的樹，不是工作樹）與 `required_action_ids(…)`＝目錄減去已完成項；validator 在 **packet 自己綁定的 head** 重算並要求逐項相等 |
| `.codex/schemas/…schema.json` | `required_action_ids` 由固定 8 項 `const` 改為「目錄成員、唯一、1–8 項」的陣列約束；**逐項相等改由 code-owned validator 執法**。這比原 `const` **更嚴**——`const` 無法隨 checkout 調整，它只能在「對舊 pin 錯」與「對新 pin 錯」之間二選一 |
| committed packet artifact | **repin 到 `2f9b6cde4`**（floor 已在該樹內），於該 head 導出 **7 項**；`sha256:b28d49fe…a9cdf` → `sha256:8c495279…6436ba`；除 `packet_digest` 與 `source_binding` 外**逐欄不變**（inventory、16 項 prerequisites、closure_projection、authority_boundaries 全部原樣） |
| `S2E-LW1-tier1-remediation.md` | §七的「共 8 項」加前向標記（不原地抹除），全文記入「演變軌跡」 |

**測試（`test_required_actions_are_derived_from_the_bound_checkout` 同時釘兩個方向）**：
在合成 repo 裡，witness 未 commit 時必須得到完整 8 項（**這一條對「全域刪除」版本為紅**），
commit witness 之後必須得到 7 項且其餘項順序不變，且同一 repo 的兩個 head 必須給出不同答案
——這正是「清單綁 checkout」與「清單是靜態常數」的可測差別。另有：current HEAD 上該項必須
從必做清單消失、`at_commit` 非 40-hex 必須在進 git 前被拒（validate 路徑上它來自受檢
packet，屬 caller 可控輸入）、全部動作皆完成時不得再發 blocked packet。

**witness 表只有一條**，因為其餘七項全是 host 側 provisioning，repo 位元組永遠證明不了
它們的完成。這個稀疏性本身就是靜態清單能腐化多日而 CI 全綠的原因。

### 4.4 具名未複驗：committed packet 的 host 觀察已對不上

PR #181（2026-08-08 merge）記錄 operator 已開 `ncyu-nas:22` 並 provision 11 個信任根。
committed packet 的 `readonly_observation` 仍是 **2026-08-02 的全 ABSENT 觀察**，與該報告
不一致。**本輪不刷新它**：刷新需要一次 trade-core 上的新鮮唯讀 inventory 擷取，PM session
的 `ssh trade-core` 被 publickey 拒；憑 operator 報告改寫 inventory 位元組會是**捏造主機觀察**。
故 16 項 prerequisites 的 `status`／`blocking` 維持原樣並具名標記為 stale。
（PR #181 只改 fingerprint 常數、未改路徑，故 `EXPECTED_PATHS` 與 packet 的 locator 仍相符。）

### 4.5 未觸及

16 項 prerequisites（12 path ＋ 4 service）、`prerequisites`／`blocked_prerequisite_ids`／
`closure_projection`／`authority_boundaries` 的 `const` 硬門、launch spec §LW1 全文、
receipt schema、九項 authority、production effect 0/6。本次只動 operator 待辦清單。

### 4.6 兩項具名的 scope 擴張

原路徑 manifest 不含 `.codex/schemas/s2e_lw1_operator_action_packet_v1.schema.json`
與 design master。但該 schema 以 `const` 陣列釘死同一份清單，只改 code 會讓 generator 被
自己的 schema 擋掉、build 直接 raise、committed packet 重建不出來。**operator 2026-08-07
裁定擴入這兩檔**。第二項（2026-08-09）：Codex 的 CI 失敗指向
`tests/structure/test_agent_governance_context_pack_reachability.py`——它斷言 ACTIVE row 的
投影必須帶出其 S2E lineage predecessor。這**不是**被釘死的舊字串，而是一條真的 Context
可達性不變量：我的 G2 row 依賴欄沒有任何 `S2E.` token，於是編譯出的 Context 少了 lineage
predecessor——那是 Context 品質的退步，不只是測試紅。**修 TODO（在 manifest 內），不修測試**：
G2 的依賴欄補上 `S2E.2b-1`（與 G1 同一條 lineage predecessor）。該 schema 不在 validator 的 `SCHEMA_FILES` 註冊表、不是 receipt schema、
引用者只有 generator ＋ committed artifact ＋ 該設計檔，與並行 uid lane 的 hard-stop 檔零交集。

---

## 五、未複驗項與誠實邊界

| 項目 | 狀態 |
|---|---|
| trade-core `PAGE_SIZE=4096`／單 argv 上限 `131,071`／`ARG_MAX=2,097,152` | **本 session 未複驗**。這是前一 session 當日的唯讀實測；本 session `ssh trade-core` 回 `Permission denied (publickey)`，無獨立複驗管道。沿用但具名標記，**不靜默採信** |
| Linux 端是否已 ff-only 同步到 `b1d2eea03` | **未確認**，同上原因 |
| 本輪全部測試證據 | Mac 本地 `LOCAL_REPRODUCIBLE`；不是 closure-admissible 強 PASS |
| PR #181（2026-08-08 merge）的 provisioning | operator 已開 `ncyu-nas:22`、provision 11 個信任根，證據等級 `operator-reported`。**本 session 同樣無法自驗**；且 committed packet 的 2026-08-02 inventory 因此已對不上（見 §4.4），刷新需要一次新鮮唯讀擷取，不得憑報告改寫 inventory 位元組 |
| runtime | unverified／not observed。正式 V2 units／canonical roots 不存在；legacy `openclaw-alr-shadow.service` active 不等於 V2 landed |

---

## 六、Routing 與具名 skip

`agent_governance.py route` 綁定 task facts（`uncertainty=medium`、`risk=MEDIUM`、
`side_effect_class=repo_write`、surfaces=`governance/docs/python`，**不含 runtime**）：

- DAG digest `sha256:76cf396da1428125fbe392cb7d8f0884bd42c4234249bcf6cd4b469debfa6ff8`
- 必要角色節點：`implementation`(E1) → `independent_review`(E2) → `regression`(E4) →
  `docs_projection`(TW) → `docs_integrity_review`(R4)
- `task_execution_control`：`continuation_mode=finite`、`automatic_wakeup_admitted=false`

**E2／E4 已實際派工並各自回 FAIL，修完才放行（2026-08-09，依 PR #180 Codex P1）**。
初版把這兩個節點記成「具名 skip，代償＝PR bot」，Codex 判定不成立——AGENTS.md 的
source-implementation 硬邊界不是可以用殘餘風險敘述換掉的，admitted node 就是 mandatory。
**這條反駁成立，已照辦。** 兩份審查都不是橡皮圖章：

| 角色 | 初判 | 決定性發現 | 處置 |
|---|---|---|---|
| E2 | **FAIL** | `git ls-tree` 少了 `--full-tree`，pathspec 相對於 `-C` prefix 解析，而同函式的 `rev-parse` 是 prefix 無關的。把 `--repo-root` 指到**任一子目錄**，witness 就查不到 ⇒ 導出多一項 ⇒ **那份已腐化的 8 項 packet 反而通過驗證**。我逐條復現：toplevel 正確、`<root>/docs` 與 `<root>/docs/execution_plan` 皆反轉 | 加 `--full-tree`；補 prefix-independence 測試，移除該旗標實測轉紅 |
| E2 | P3 | witness 若解析成 **tree**（同名目錄）也被算作完成 | 加 blob type 檢查；補測試，移除檢查實測轉紅 |
| E4 | **FAIL** | 突變 **M3**（validator 改在 `repo_root` 的 HEAD 導出，而非 packet 綁定的 head）**全套件存活**——每份受測 packet 都剛好綁在「導出結果與 current HEAD 相同」的 head 上。本次改動最承重的一句話當時**零測試** | 補 divergent-head validator 測試；M3 現實測轉紅 |
| E4 | 覆蓋缺口 | 該測試前五句斷言拿 `CANONICAL_ACTION_IDS` 當右手邊 ⇒ 目錄被縮短時一起縮短、毫無鑑別力，全部鑑別力壓在單一差分句上；validator 層無亂序測試；schema 由 `const` 換成 enum 陣列後完全未被測 | 補字面 id 斷言、validator 層亂序測試、四條 schema 形狀負向測試 |

E2 另具名兩項**接受而非隱藏**的代價（離線可驗性喪失、八項 witness 全命中時的死路），
以及一項它自己的證據缺口：對抗探針無法經 `capture-command` 擷取（wrapper 拒絕 repo 外
腳本路徑與 inline argv 的控制字元），故那些探針只有 `LOCAL_REPRODUCIBLE` 等級。

**仍具名 skip**：TW／R4 兩個 docs 節點未派工，文件投影由 PM 自己寫。殘餘風險＝文件層
無獨立漂移複核；owner=PM。

---

## 七、Finite stop

裁決落帳即停。**不**順帶開始：三支 root-owned producer、S3、LW2 實作、任何 runtime effect。
不進入自我續跑迴圈，不排程喚醒（`automatic_wakeup_admitted=false`）。

下一個 exact 工作：`P0-AIML-G2-SOURCE-EXTERNAL-GATE-SPLIT` 的 §2.3 機械化實作，
由 PM 另行 route/admit。
