# S2E Tier 1 durability anchor — 三路獨立對抗複核：**FAIL**

日期：2026-08-03
受審：`agent/aiml-s2e-tier1-durability-anchor-20260802`，baseline `097c879b9`
複核者：E2（對抗代碼）／E3（安全）／E4-verifier（測試證據），三路獨立派工、互不可見
裁決：**三路全 FAIL**，且獨立收斂到同一組缺陷
PM 複驗：以下每一條 PM 已自行讀 source／spec 原文複算，非轉述

## 一、決定性結論：實作違反它引用來授權自己的那句 spec

交付報告宣稱 Tier 1「正是 §LW1 spec anchor 選言的第二支」。**這個宣稱不成立。**

`docs/execution_plan/ai_ml_landing/design/S2E-launch-wave-specs.md` §LW1 原文（PM 逐字複讀）：

> anchor 必須使用 append-only/WORM，或使用同時綁獨立 key identity、**外部** monotonic
> counter/append-only head、trusted freshness window、latest-generation immutable readback
> 的 trusted-host SSHSIG，**單一簽章不能防 rollback**；**同一 writer 可 coherent rewrite
> 或舊合法 anchor 可重放時只能得 `UNVERIFIED`**。

三處逐字違反：

| spec 要求 | 實作 |
|---|---|
| monotonic counter/head 必須**外部** | host-local（`host:append-only-durability-anchor:`） |
| **單一簽章不能防 rollback** | 正是單一簽章：一把 anchor key 同時簽 anchor head **與**它自己的 off-host readback 證明 |
| 同一 writer 可 coherent rewrite 時**只能得 `UNVERIFIED`** | 同一 writer 的 coherent rewrite 回傳 `[]`＝VERIFIED（E2/E3 各自獨立 PoC 實證） |

註：`TODO.md` 第 170 行的摘要投影漏掉了「外部」二字，這可能是交付時誤讀的來源。
全文 spec 才是正本（`TODO.md:149` 自己就寫「全文 spec=…§LW1」）。

## 二、四條 P1（E2／E3 獨立發現，PM 複驗）

### P1-1 · monotonic append-only head 完全未被強制
`program_code/ml_training/aiml_gate_receipt_s2e_external_evidence.py:473-479`

連續性檢查只比對 **null vs non-null 形狀**：第一代不得帶前手、後續代不得缺前手。
`previous_anchor_head_digest` 的**值**從不與任何真實前手比對，且全 repo 無任何持久化 head 狀態。
整條鏈自封閉——所有 digest 都從同一份 attestation 內部欄位重算。

實證（E2/E3 各自獨立跑出同結果）：同一 locator 上兩份 `gen=1/prev=None` 全接受；
`gen=999 + 從未存在的 previous head` 接受；端到端 `build_s2e_launch_predecessor_authority`
在同一 locator 上接受兩個互不相連的創世 head。

攻擊：持有 anchor 私鑰者（即 trade-core 上的 root）可刪掉 ledger 尾部、重簽一份
`gen=1/prev=null` 綁到任意新 payload，驗證端零錯誤。**這是本專案第 ③ 類慣犯缺陷
（hash-chain 不持久化 ⇒ 尾截斷不可測）原封不動重現。**

### P1-2 · off-host readback 由寫入者本人自證，distinct-actor 要求整個消失
`aiml_gate_receipt_s2e_external_evidence.py:488-498`；schema `$defs.replica_readback`

三個 readback 旗標在 schema 是 `"const": true`——**只能是 true，資訊量為零**。
唯一有內容的 `replica_head_digest` 與 `anchor_head_digest` 由同一把 key 在同一份文件裡
寫下並簽名。沒有 replica 端的第二簽章、沒有 replica key identity、沒有 replica trust root。

對照被取代的 Tier 0：`agent_governance_terminal_receipt_external_sink.py:1323-1345` 明文
硬擋「a positive external worm readback ACK cannot be issued by the bound append actor」；
專案 Registry 不變式（`.codex/agent_registry_v1.json`）逐字寫著
**"readback ACK requires a distinct actor"** 與 **"independent readback ACK by a distinct
actor"**（PM 已 grep 複驗）。Tier 1 對此**沒有任何替代物**。

副作用：`:488-493` 那段程式碼是**不可達死碼**（schema `const` 先擋），對應的 3 個
negative case 只證明了 schema，沒證明任何 validator 行為。

### P1-3 · 「off-host」在代碼裡零強制，純命名
`aiml_gate_receipt_s2e_external_evidence.py:43`；schema pattern `^replica:offhost-append-only:...`

前綴之後是自由字串，驗證端從不連線、不解析、不比對 host identity。實證全部接受：
`replica:offhost-append-only:localhost`、`...:127.0.0.1:9000/s2e`、
以及 replica 路徑與 anchor 路徑指向**同一個目錄**。

由於 replica 是 Tier 1 **唯一剩下的 durability 保證**，此條直接摧毀該保證：
只控制 host 即可同時滿足 anchor 與 replica 兩端。

E3 另指出：這一項**不是** operator 前提變更的必然結果。operator 裁的是「anchor 在 host 上」，
沒有裁「replica 也可以在 host 上」。**這是本次新開的缺口，不是被追認的。**

### P1-4 · 新寫的 anchor 綁定執法可整段刪除而 72 個測試全綠
`aiml_gate_receipt_s2e_launch.py:1159-1174`（carrier `immutable_readback` 四欄綁定）
`aiml_gate_receipt_s2e_launch.py:1478-1492`（`durability_anchor_binding` 五欄綁定）

E2 與 E4 **各自獨立**做 mutation，結果相同：把兩處相等性檢查同時改成 `if False:`，
四個檔 72 個測試無一變紅。這正是 Tier 1 核心承諾（「副本必須回讀到與本機 anchor
完全相同的 head」）在 carrier/review 層的落地點，實測**裸奔**。

E2 誠實界定：Tier 0 的 `external_worm_binding` 同樣沒有 mutation 測試，這是**繼承的
覆蓋債，不是本次新造**。但報告「負向覆蓋是增加而非等量」的宣稱只對 `external_evidence`
模組成立；對本次**重寫過**的 launch 側綁定面，新增覆蓋是 **0**。

## 三、P2（節錄）

- **P2-1 · 簽章治理正本裡固化一句假話**：`aiml_gate_receipt_s2e_review.py:765-772` 仍產出
  `EXTERNAL_WORM_IMMUTABLE_READBACK_VALID` / `required_adapter: EXTERNAL_WORM_V1` 的 PASS
  predicate，而實際上沒有任何 external WORM 參與。不構成授權逃逸，但撞到 CLAUDE.md
  「不得偽造 lineage／evidence」，且未列入交付報告的已知殘留。
- **P2-2 · 「選言」是假的**：`launch.py:1158-1163` 只接受第二支，硬拒 `EXTERNAL_WORM_V1`
  （schema enum 仍列兩支）。這不是「實作了選言的第二支」，是「把選言換成另一支」——
  日後真的採購 S3 Object Lock 反而會被拒。
- **P2-3 · replica readback 無自己的 freshness 下界**（相對 baseline 的**淨回歸**）：
  只檢查 `attestation.observed_at >= readback.observed_at`，無下界。5 年前的回讀可掛在
  剛簽的 anchor 上通過。舊路徑的 `validate_external_worm_readback_ack` 有自己的 TTL 檢查，
  刪三件套時一併刪掉，新 schema 沒補回。
- **P2-4 · key custody「獨立」只到 fingerprint 層**：三把 key 放同一台 host 同一個
  root-only 目錄可全綠，而新增的 provisioning prompt 建議的正是這種放法。
- **P2-5 · operator 正面貼用文件自相矛盾**：provisioning prompt 仍有 5 處寫「9 把」
  （表格實為 10 列）、且第 16 行寫「Tier 1 下 3 項作廢」——與 14/14 全 blocking 直接矛盾。
  交付報告 §四.3 宣稱該檔「已同步更新」，過度。
- **P2-6 · 降級提案未標 superseded**：`2026-08-02--s2e_external_evidence_downgrade_proposal.md:85`
  仍寫「blocker 14 → 11」，單讀該檔者拿到錯數字。

## 四、複核確認為 PASS 的項目（不可因總裁決 FAIL 而抹掉）

三路一致確認以下是紮實的，PM 抽驗通過：

- trust-root 讀取的 TOCTOU 防護（O_NOFOLLOW + lstat/fstat/lstat 三段 dev-ino-mode-uid
  一致性 + `st_nlink != 1` + 16KiB 上限 + 拒重複 key 的嚴格 JSON）——E3 評為「品質很高」。
- SSHSIG domain separation 是真的：namespace 進入簽章 blob，跨 namespace replay 由
  `ssh-keygen -Y verify -n` 阻斷。
- digest 逐項真重算（`attestation_digest`／`signed_core_digest`／entry／head 四者），
  `application_bundle_runtime_closure_v1.json` 的 self_digest 兩路獨立重算皆逐位元相符。
  **「digest 綁定只是名字」這一類慣犯缺陷本次不適用。**
- effect 後例外裸逸：不適用（本 diff 全是純驗證函式，無 effect），try/except 皆 fail-closed。
- secret／SQL／subprocess／argv／env 注入面：零命中；kernel exec 面未被放寬。
  舊 `destination_contract` 的 credential_channel/endpoint/bucket 這組 secret-smuggling
  面隨三件套一併刪除，**淨減少**。
- `external_sink` 三件套移除**沒有覆蓋淨損失**：唯一被刪的 test function 所測的不變量
  （`object_lock_mode == COMPLIANCE`）已隨 operator 裁決不存在；其餘三檔 case 清單逐字相同。
- 交付報告的**所有可驗證數字都是誠實的**：四個單檔 26/23/10/13 三方各自精確復現；
  最關鍵的免責宣稱（headroom 紅燈在 baseline 同值 107089、位元組中性）由 E4 以 detached
  worktree 獨立復現，並用 `git show 097c879b9:.codex/agent_registry_v1.json | wc -c`
  交叉驗證。報告 §五主動聲明未做 E2/E4 複核，這個自我披露是對的——本次複核證實了它的必要性。

## 五、E4 具名的證據等級問題

- 全量 `tests/structure/` 的 `5339/16/1/62` **無法經 admitted 通道復現**：
  `capture_governed_command` 硬性上限 `timeout_seconds ≤ 900`，全量套件需 >15 分鐘。
  這同時意味著**報告那一列數字本身不是經 governed capture 產生的**，屬未經 attestation
  的 ungoverned 宣稱，不應與四個 governed 單檔數字並列同一張表。
- 62 errors 的歸因**無法證實亦無法否證**：governed 隔離下該檔誠實 skip（`psycopg2`
  在 no-site 下不可 import），走不到 initdb。機制上說得通，但「全部同根因、沒夾帶真
  regression」無證據。
- 治理副作用（另立 follow-up）：`test_ibkr_feature_flag_secret_auth_source_static.py`
  因檔名含 `secret` 被 preflight 拒（`secret-bearing path is forbidden`），
  **在 governed 通道下永遠無法被 E4 驗證**。
- 併發污染事件（環境觀察）：E4 第一次整檔跑時 governed capture 以
  `governed command mutated whole-repository generation` DENIED，事後發現
  `aiml_gate_receipt_s2e_launch.py` 被改成 `if False:`（另一 session 的 mutation 實驗），
  數分鐘後自行復原。四個單檔跑不受影響（whole-repository generation 前後比對通過）。
  這是 [[project_multi_session_memory_race]] 家族在**測試執行**面的新表現。

## 六、放行條件（三路收斂，PM 採納為 remediation 清單）

**必要（缺一不可放行）**：

1. **跨 receipt 單調性 gate**。E3 指出資料已經在 git 裡：receipt 綁
   `acceptance_review_bundle_digest`，而 bundle 覆蓋 `durability_anchor_binding`，
   其中含 `anchor_generation`／`anchor_head_digest`——**每次發出的 receipt 都把當時的
   anchor head 釘進 git**。只需在 transition gate 加「新 receipt 的 `anchor_generation`
   必須嚴格大於前一份、且 `previous_anchor_head_digest` 必須等於前一份的
   `anchor_head_digest`」。git 就是 spec 要的那個「**外部**、由不同 owner/capability 控制、
   位於可替換 state root 之外」的持久層。這是唯一能把 P1-1 從不可偵測變成可偵測的低成本改動。
2. **replica 必須有自己的 key identity、trust root 與簽章**，覆蓋自己的 `observed_at`
   且納入 ≤10min window。這同時解掉 P1-2、P1-3 的自證問題與 P2-3 的 TTL 回歸，
   並使「單一簽章不能防 rollback」不再被違反（變成雙簽章）。
3. **`offhost_replica_locator` 必須排除 loopback/localhost/本機 host identity**，
   或改為綁定獨立 host fingerprint。
4. **補 P1-4 的 regression**：斷言必須釘具體錯誤訊息，不可用 `assert errors`
   （後者正是 P1-2 那類自我滿足弱斷言）。

**應該**：

5. 把 `EXTERNAL_WORM_V1` 重新接回 `launch.py:1160` 成為**真正的選言**而非替換（P2-2）。
6. 補 operator packet artifact 的 regression（E4 §六，優先級高）：這是**已經實際發生過的
   失效**，不是假想風險——artifact stale 到用自己的 validator 跑都 FAIL 而 CI 全綠。
   形狀必須是三條：(a) committed artifact validate 空 errors；(b) `source_binding` 與
   pin 自洽；(c) **用 generator 以相同輸入重建，斷言與 committed bytes canonical 等值**
   ——只有 (c) 真正把 artifact 綁到 generator，(a)(b) 都繞得過。
   **禁用 wall-clock／硬編日期**，否則就是 [[feedback_test_fixture_wallclock_timebomb]] 的老坑。
7. 更正報告 §一「選言第二支」與「五項語義完全未動」兩處敘述；全量套件那兩列改標
   UNVERIFIED；provisioning prompt 修 5 處「9 把」與第 16 行「3 項作廢」；
   降級提案標 superseded。

## 七、誠實邊界

- 三路複核均**未**取得 admitted node-id／context artifact，故 E2/E3 的 pytest 為
  `LOCAL_REPRODUCIBLE`，**不是 closure-admissible evidence**；只有 E4 走了
  `agent_governance.py capture-command`。
- 本次複核未執行任何 runtime／PG／broker／order／deploy effect。
- 所有 mutation 實驗均已還原，`git status` 乾淨；PoC 檔僅在 scratchpad，未進 repo。
- authority 仍 0/9，production effect 仍 0/6，S2 未關閉，LW2 仍 locked。
