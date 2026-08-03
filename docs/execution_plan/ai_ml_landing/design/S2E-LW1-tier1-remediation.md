# S2E-LW1 Tier 1 durability anchor — remediation 設計正本

**日期**: 2026-08-03 ／ **作者**: PA ／ **狀態**: DESIGN_READY（未實作）
**分支**: `agent/aiml-s2e-tier1-durability-anchor-20260802`（HEAD `a2116dd1c`；baseline `097c879b9`）
**上游裁決**: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-03--s2e_tier1_adversarial_review_fail.md` §六
**規範正本**: `docs/execution_plan/ai_ml_landing/design/S2E-launch-wave-specs.md` §LW1（`TODO.md:170` 的摘要投影漏抄「外部」二字，不得當授權來源）

**operator 2026-08-03 兩項裁決（已收進本檔）**：
1. replica 的私鑰與簽章動作歸屬**第二台實體機器 `ncyu-nas`**，trade-core root 不得持有 ⇒ §4.2／§4.4／§5 全面改寫，§5.3 的「書面承擔」降級為明確的**代碼線／provisioning 線**分界。
2. 本 PA 在初版 §十一 具名的 **600 秒 hot-handoff latent P1 本輪一併修** ⇒ 新增 §7.4。

本檔是設計正本，不含實作代碼。E1 依 §9 的順序落地；每一項的落點以 `file:line` 給到函式級。

---

## 一、問題陳述

§LW1 對 anchor 的規範選言第二支要求同時具備四件事：獨立 key identity、**外部** monotonic
counter/append-only head、trusted freshness window、latest-generation immutable readback；
並附兩條否定條款：**單一簽章不能防 rollback**、**同一 writer 可 coherent rewrite 或舊合法 anchor
可重放時只能得 `UNVERIFIED`**。

current head 的實作在三處逐字違反（複核 §一），根因可歸為兩句話：

1. **沒有任何持久狀態在驗證端之外**。`aiml_gate_receipt_s2e_external_evidence.py:473-479`
   的連續性檢查只比 null／non-null 形狀，`previous_anchor_head_digest` 的**值**從不與任何真實
   前手比對；整份 attestation 的四個 digest 全部從它自己的欄位重算（`:255-284`）。鏈是自封閉的。
2. **只有一把 key**。off-host readback（`:488-498`）由 anchor writer 本人在同一份文件裡寫下並
   簽名，`$defs.replica_readback` 的三個旗標是 `const: true`（零資訊），replica 既無 key
   identity、無 trust root、無簽章，`offhost_replica_locator`（`:43` 前綴 + schema pattern）
   之後是自由字串，驗證端從不解析 host identity。

因此**修法的骨架只有兩根**：把 monotonic head 錨到一個驗證端與 anchor 私鑰持有者都改不動的
外部持久層（§3），以及讓 readback 由第二把獨立 key 在第二個 host identity 上簽名（§4）。
其餘兩項（§5 locator、§6 `const: true`）是這兩根骨架的直接推論，不是獨立特性。

---

## 二、「git 當外部持久層」論證的複驗結論

PM/E3 的論證是：receipt 綁 `acceptance_review_bundle_digest`，bundle 綁
`durability_anchor_binding`（`aiml_gate_receipt_s2e_launch.py:1481-1492`），其中含
`anchor_generation`／`anchor_head_digest`，所以「每次發出的 receipt 都已把當時的 anchor head
釘進 git」。

**結論：論證的**方向**成立，但當前形態下的前提不成立，必須補一個 code-owned committed pin
才能真的成為 gate。** 逐條複驗：

| 論證的前提 | 複驗結果 |
|---|---|
| bundle 綁 anchor 五欄，bundle digest 進 receipt | **成立**。`:1481-1492` 逐欄綁定，`:1352` 重算 bundle digest，receipt `:1620-1622` 只存 digest。 |
| 「receipt 已在 git 裡」 | **不成立為 gate**。`docs/execution_plan/ai_ml_landing/receipts/S2E-LW1-LW5/` 目前只有一份 `W0-genesis-pending-review.json`，且**沒有任何代碼讀它**。transition gate 的 `--receipt`／`--predecessor-receipt`／`--predecessor-authority`（`helper_scripts/maintenance_scripts/agent_governance_s2e_launch_receipts.py:128-136`）全部是 caller 提供的任意檔案路徑。目前 gate 的兩側都由 caller 供給，「在 git 裡」是流程事實而非機械事實。 |
| git 是「外部、由不同 owner/capability 控制」 | **條件成立**。anchor 私鑰的持有者是 trade-core 的 root；改寫 GitHub main 需要另一組 capability（GitHub token + PR + required checks + Codex review + branch protection），與 host root 不是同一把權限。這是本專案能拿到的、最接近 §LW1「不同 owner/capability」的真實分隔。 |
| git 位於「可替換 state root 之外」 | **成立且比預期強**。receipt 逐份釘死 commit SHA（`source_head`／`source_tree`／`schema_carrier_head`），`_git_binding_errors`（`:444-457`）與 `_is_ancestor`（`:596-603`）會實際解析它們。**任何 history rewrite 都會讓既發 receipt 釘的 SHA 變成不可達，整條鏈當場 fail-closed**。所以「攻擊者改寫 git 以掩蓋 rollback」不是靜默路徑。 |

**因此本設計採用 git，但必須加一個代碼自己去 git 讀的 pin**：committed durability anchor
floor（§3）。沒有它，「資料已經在 git 裡」對驗證器而言等於「資料在 caller 手裡」。

**誠實邊界（必須寫進 PR 說明，不得省略）**：git 提供的是 *tamper-evident + 需要第二組
capability*，不是 WORM。持有 GitHub 寫入權的人可以合法 merge 一份倒退的 floor；本設計用
「floor 檔案自身歷史的祖先鏈 + 嚴格遞增」把這件事變成**機械可偵測**（§3.4），而不是靠 PR
人工複審。這是可達成的最強形態，不是理想形態。

---

## 三、項目一 · 跨 receipt 單調性 gate（committed anchor floor）

### 3.1 新增 artifact：committed durability anchor floor

路徑（code-owned 常數，由 `LAUNCH_ID` 導出，不可由 caller 指定）：

```
docs/execution_plan/ai_ml_landing/receipts/S2E-LW1-LW5/durability-anchor-floor-v1.json
```

新 schema `s2e_durability_anchor_floor_v1`（`program_code/ml_training/schemas/aiml_gate_receipts/`，
`additionalProperties: false`，全欄 required）：

| 欄位 | 型別 | 語義 |
|---|---|---|
| `schema_version` | const `s2e_durability_anchor_floor_v1` | |
| `launch_id` | const `S2E-LW1-LW5` | 跨 launch replay 的第一道 |
| `state` | enum `GENESIS_ARMED` / `ADVANCED` | 創世只允許出現一次（§3.5） |
| `anchor_locator` | `^host:append-only-durability-anchor:...` | **locator 由 git 釘死**，不再每份 attestation 自報 |
| `offhost_replica_locator` | `^replica:offhost-append-only:...` | 同上；副本身分不可逐份切換 |
| `floor_generation` | integer ≥ 0 | `GENESIS_ARMED` 時為 `0` |
| `floor_head_digest` | digest 或 null | `GENESIS_ARMED` 時為 null |
| `bound_receipt_payload_digest` | digest 或 null | 這個 floor 屬於哪一份已發 receipt |
| `bound_acceptance_review_bundle_digest` | digest 或 null | 同上 |
| `floor_digest` | digest | canonical self-digest（除自身外全欄） |

**floor 不是新的信任源，只是把「bundle 已經釘住的值」投影到一個驗證器自己會去 git 讀的位置。**
它的完整性來自 §3.4 的歷史檢查與 PR gate，不來自簽章；因此不需要第四把 key。

### 3.2 新增模組（不擴張既有檔）

`program_code/ml_training/aiml_gate_receipt_s2e_anchor_floor.py`（預估 ≤170 行），公開面：

- `DURABILITY_ANCHOR_FLOOR_SCHEMA`、`durability_anchor_floor_repo_path()`
- `durability_anchor_floor_digest(floor)`
- `read_committed_durability_anchor_floor(repo_root, *, at_commit) -> tuple[dict|None, list[str]]`
  —— 以 `git show <at_commit>:<path>` 讀 **commit 物件的位元組**（不是工作樹），內含 §3.4 歷史檢查
- `durability_anchor_floor_errors(anchor, *, floor, label)` —— 單份 attestation 對 floor 的規則
- `durability_anchor_order_errors(sequence)` —— 同一次驗證內多份 anchor 的嚴格排序
- `next_durability_anchor_floor(receipt, bundle)` —— 純投影，供 issuance 產出下一份 floor 供人 commit

**為什麼開新檔而不是塞進既有檔**：`aiml_gate_receipt_s2e_launch.py` 現為 1849 行，加上本設計的
接線後若再吞下 floor 讀取＋歷史走訪會逼近 2000（§8.3）；`aiml_gate_receipt_s2e_external_evidence.py`
目前完全不碰 `subprocess`／git，把 git 讀取塞進去會讓「純 attestation 驗證」這個模組邊界破裂。
**deletion test**：刪掉本模組，P1-1 立即完整復發（單調性無處落地），因此它不是為抽象而抽象。

### 3.3 落點與規則

**(a) 單份 anchor 對 floor 的規則** —— 落在
`aiml_gate_receipt_s2e_launch.py:1465-1492`（`validate_s2e_launch_acceptance_review_bundle`
現有 anchor 綁定段之後，同一段內）：

1. 讀 `floor = read_committed_durability_anchor_floor(repo_root, at_commit=reviewed_head)`。
   `reviewed_head` 已在 `:1258-1263` 依 candidate 類型導出；**genesis 用 `schema_carrier_head`，
   wave 用 `source_head`**。讀不到／schema 不合／歷史檢查有錯 ⇒ 直接 fail（不得 fallback）。
2. `floor.launch_id == LAUNCH_ID`；`anchor.anchor_locator == floor.anchor_locator`；
   `anchor.offhost_replica_locator == floor.offhost_replica_locator`。
3. `anchor.anchor_generation > floor.floor_generation`（**嚴格大於**，對 genesis 亦成立：
   `0 → ≥1`）。
4. 若 `floor.state == "ADVANCED"`：`anchor.previous_anchor_head_digest` 不得為 null；
   且當 `anchor.anchor_generation == floor.floor_generation + 1` 時，
   `anchor.previous_anchor_head_digest` 必須**逐字等於** `floor.floor_head_digest`。
   （非相鄰世代不宣稱 hash 連結——理由見 §3.6。）
5. 若 `floor.state == "GENESIS_ARMED"`：candidate 必須是 `W0-GENESIS`，且
   `anchor.anchor_generation == 1`、`previous_anchor_head_digest is None`。

這個落點是唯一必要的落點，因為 `validate_s2e_launch_acceptance_review_bundle` **同時被**
issuance（`:1603-1613`）與 predecessor authority 複驗（`:782-801`）呼叫，兩條路都被覆蓋。

**(b) 跨 receipt 排序規則** —— 落在
`aiml_gate_receipt_s2e_launch.py:868-904`（`validate_s2e_launch_transition`）：

新增 keyword-only 參數 `durability_anchor_attestation`（**candidate 自己的 review anchor**）。
現行簽名拿不到它——wave receipt 只帶 `acceptance_review_bundle_digest`，不帶 binding 實值
（schema `s2e_launch_wave_receipt_v1` required 十八欄無 anchor 欄位；已複驗），
而 `predecessor_authority` 只帶前一份的兩份 anchor。因此**必須從呼叫端傳入**。

令：`a` = `predecessor_authority["review_durability_anchor_attestation"]`、
`b` = `predecessor_authority["carrier_durability_anchor_attestation"]`（兩者已在
`_S2E_PREDECESSOR_AUTHORITY_FIELDS:626-638` 內，不需擴張 authority contract）、
`c` = 新參數。`F` = floor at `receipt["source_head"]`。規則：

1. `F.bound_receipt_payload_digest == predecessor_receipt["payload_digest"]` 且
   `F.bound_acceptance_review_bundle_digest == predecessor_receipt["acceptance_review_bundle_digest"]`
   —— **這一條是整個修法的樞紐**：它把 caller 供給的 predecessor 綁到 git 上唯一那一份 floor。
2. `a.anchor_generation == F.floor_generation` 且 `a.anchor_head_digest == F.floor_head_digest`
   —— caller 不能改寫前一份 anchor 的世代（要改必須先 merge 一個 commit）。
3. `b.anchor_generation > a.anchor_generation`；`c.anchor_generation > b.anchor_generation`；
   三者 `anchor_locator`／`offhost_replica_locator` 全等於 `F` 的兩個 locator。
4. 相鄰世代必須 hash 連結（規則同 §3.3(a).4），對 `a→b`、`b→c` 各判一次。
5. `c.previous_anchor_head_digest` 不得為 null。

**(c) 前一份 anchor 的先後順序** —— 落在
`aiml_gate_receipt_s2e_launch.py:737-821`（`validate_s2e_launch_predecessor_authority`，
在 `:802-820` carrier 驗證之後）：`b.anchor_generation > a.anchor_generation` 在此獨立再判一次，
使得「只跑 authority 複驗、不跑 transition」的路徑也擋得住。這是刻意的重複，成本一行。

**(d) issuance 產出下一份 floor** —— 落在
`aiml_gate_receipt_s2e_launch.py:1678-1696`（`issue_s2e_launch_receipt` 的 result 組裝）：
result 增加 `next_durability_anchor_floor` 欄位（純投影，`state="ADVANCED"`，
generation/head 取自 `acceptance_review_bundle["durability_anchor_binding"]`，
bound 兩欄取自 `issued_receipt`）。**驗證器永遠不寫檔**；commit 由 operator/E1 在同一個 PR 內完成。

**(e) CLI 接線** —— `helper_scripts/maintenance_scripts/agent_governance_s2e_launch_receipts.py`：
`transition-gate` 子命令新增 `--durability-anchor-attestation`（required），
`:238-252` 的呼叫傳入；`validate` 分支同名參數（optional，缺省時該分支只做
`validate_s2e_launch_transition_payload`，維持現行 `STRUCTURAL_PASS_NOT_ADVANCE` 語義）。

### 3.4 歷史檢查（把「單調」變成 git 的性質）

`read_committed_durability_anchor_floor` 內，於回傳前執行：

1. `git log --format=%H --reverse --topo-order <at_commit> -- <floor_path>` 取得所有觸碰該檔的 commit。
2. **祖先鏈**：相鄰兩個 commit 兩兩 `git merge-base --is-ancestor`；不成鏈即 fail
   （避免 merge topology 下「順序」歧義，不依賴 topo-order 的穩定性）。
3. **嚴格遞增**：對每個 commit `git show <sha>:<path>` 解析 floor，
   `floor_generation` 沿鏈嚴格遞增；`launch_id`／兩個 locator 全鏈恆等；
   `state == "GENESIS_ARMED"` 只允許出現在鏈的**第一個** commit。
4. 最後一份必須逐位元組等於 `at_commit` 讀到的那份。

成本：LW1-LW5 全程最多 6 個 commit ⇒ ≤6 次 `git show` + ≤5 次 `merge-base`。
**這一步是「genesis 不變成永久後門」的機械保證，也是把 §LW1 的「外部 monotonic counter」
從敘述變成執法的那一步。**

### 3.5 genesis 邊界

- **檔案不存在 ≠ genesis**。讀不到 floor 一律 fail-closed。genesis 的信號是**已 commit 的
  `state="GENESIS_ARMED"` 且 `floor_generation == 0`**，這份檔案必須在 W0 發行**之前**由
  operator 走 PR commit（新增 packet 動作項，見 §7.2）。
- 想第二次進 genesis，必須 commit 一份把 `floor_generation` 退回 0 的 floor ⇒ §3.4 步驟 3
  當場 fail。想繞過 §3.4，必須 rewrite git history 讓舊 floor commit 不再是新 `source_head`
  的祖先 ⇒ `_is_ancestor`（`:596-603`）與 `_git_binding_errors`（`:444-457`）當場 fail。
  **兩條獨立偵測，皆不需要任何私鑰即可執行。**
- genesis 的 anchor 仍須 `generation == 1 / previous == null`（§3.3(a).5），且該值一經
  issuance 就被 §3.3(b).2 釘死。

### 3.6 replay 邊界（明確界定「本設計擋什麼、不擋什麼」）

| 攻擊 | 是否被擋 | 機制 |
|---|---|---|
| 刪 ledger 尾部、重簽 `gen=1/prev=null`（P1-1 原始 PoC） | **擋** | §3.3(a).3 對 floor 嚴格大於 |
| 重放舊的合法 anchor（世代 ≤ floor） | **擋** | 同上 ⇒ 只能得 `EXTERNAL_VERIFICATION_PENDING` |
| 換一份較舊的 predecessor authority 配新 candidate | **擋** | §3.3(b).1-2 綁 git 上唯一 floor |
| 跨 launch_id 重放 | **擋** | floor path 由 `LAUNCH_ID` 導出 + `floor.launch_id` + entry digest 已含 `launch_id` + SSHSIG namespace 分離 |
| 跨 branch：在 sibling branch 上從同一 floor 各推進一次 | **部分**。同一台 host 上由 `.git` common dir 的 single-use consumption ledger（`aiml_gate_receipt_s2e_consumption.py:573-580`）擋；跨 host 併發是**具名殘留**，需 LW2+ 的 registry 能力落地才封閉 |
| 同一 writer 的 coherent rewrite（保持世代前進地改寫） | **擋，但靠 §4／§5**，不靠本節 | 需同時取得 trade-core 的 anchor key 與 `ncyu-nas` 的 replica key ⇒ 2-of-2，且兩把 key 在兩台實體機器（operator 2026-08-03 裁決，§5.3） |
| 非相鄰世代之間的 ledger 內部改寫（gap 內） | **不擋，且本設計不宣稱擋** | 見下 |

**關於「gap 內不宣稱」**：anchor attestation 的 TTL ≤10 分鐘（`MAX_ATTESTATION_TTL:56`），
驗證失敗與重試都會產生新的 append，因此 pinned 兩點之間必然可能有未被釘住的條目。要為 gap
提供「link path」證明是**假的安全性**——中間條目的 `entry_digest` 無原像可驗，任何人都能編一條
從 floor 走到任意新 head 的路徑。因此本設計**只在相鄰世代宣稱 hash 連結**，其餘只宣稱單調。
E1 不得把這條寫成「hash chain 完整性已驗證」。

---

## 四、項目二 · replica 自己的 key identity、trust root 與簽章

### 4.1 契約形狀

`s2e_durability_anchor_attestation_v1.schema.json` 的 `$defs.replica_readback`（現 `:51-65`）
整段取代為：

| 欄位 | 說明 |
|---|---|
| `schema_version` | const `s2e_offhost_replica_readback_v1` |
| `replica_locator` | pattern 同 `offhost_replica_locator`，且必須與外層逐字相等 |
| `replica_host_fingerprint` | `^SHA256:[A-Za-z0-9+/]{43}$`，replica **host key** 指紋（非 signer key 指紋） |
| `observed_anchor_locator` | replica 端讀到的 anchor locator |
| `replica_generation` / `replica_previous_head_digest` / `replica_entry_digest` / `replica_head_digest` | replica 端自己回讀到的四個值 |
| `observed_at` / `expires_at` | replica **自己的** freshness window |
| `signer` | `role: OFFHOST_REPLICA_READBACK_ATTESTOR`，identity `aiml-s2e-offhost-replica-attestor-v1`，namespace `arcane-equilibrium-aiml-s2e-offhost-replica`，`key_generation`／`anchor`／`key_fingerprint` 同既有 signer 形制 |
| `signed_core_digest` / `signature` | SSHSIG，簽章覆蓋除這兩欄外的全部 readback 欄位 |

三個 `const: true` 旗標**刪除**（§6）。

**簽章巢狀語義（必須寫進註解）**：replica 先簽 readback core，anchor 再把整份 readback 納入
自己的 signed bytes（`_signed_bytes:220-231` 天然涵蓋）。因此 anchor 簽章證明「我引用的就是
這份 replica 證言」，replica 簽章證明「我在我自己的時間窗看到這個 head」。**兩把簽章對同一個
head 各自負責 ⇒ §LW1「單一簽章不能防 rollback」不再被違反。**

### 4.2 trust root 與 key／host 歸屬（operator 2026-08-03 裁決）

**replica 私鑰與簽章動作歸屬 `ncyu-nas`（tailnet `100.77.15.17`，linux）。trade-core root 不得持有
replica 私鑰。** 驗證端（trade-core）只讀公鑰形式的 trust root。

已複驗的基礎設施事實：

| 事實 | 來源 |
|---|---|
| `ncyu-nas` 100.77.15.17 / linux / online 存在於同一 tailnet | **PA 於 Mac 端 `tailscale status` 直接複驗（2026-08-03）** |
| trade-core 目前無任何 NAS 掛載（`mount` 僅 kernel `nfsd on /proc/fs/nfsd`；`/etc/fstab` 無 nfs/cifs/smb 條目） | PM read-only 觀察 |
| `ssh trade-core → ssh ncyu-nas:22` = **Connection refused**（非 timeout，主機在、網路通、無 SSH listener） | PM read-only 觀察 |

⇒ **`ncyu-nas` 上的可執行簽章路徑目前不存在**，這是一個新的具名 provisioning 前置（§4.4），
與三支未實作的 root-owned producer 能力同一級：**不擋 source 工作，擋 receipt 發射**。

新增 fixed host path（安裝在 trade-core，內容只有公開資料）：

```
/etc/arcane-equilibrium/aiml/s2e-offhost-replica-trust-root-v1.json
```

`schema_version = "s2e_offhost_replica_trust_root_v1"`、
`attestor_class = "OFFHOST_APPEND_ONLY_REPLICA_READBACK_V1"`；
`public_key` 為在 `ncyu-nas` 上產生、私鑰從未離開該機的 ed25519 公鑰；
`host_fingerprint` 為 **`ncyu-nas` 的 SSH host key 指紋**（非 signer key 指紋）。

**依賴順序（不可顛倒）**：`ncyu-nas` 的 SSH listener 不存在 ⇒ 拿不到它的 host key 指紋
⇒ replica trust root 的 `host_fingerprint` 欄位無法填真值。因此 §4.4 的新前置必須先於
replica trust root 安裝。**任何情況下不得填佔位指紋**（那正是 7 個
`RECOVERY_*_TRUST_ROOT_FINGERPRINT` 佔位值造成的既有問題，見 provisioning prompt `:36-48`）。
若 operator 選擇非 SSH 的簽章傳輸，設計要求等價的**可由第三方視角外部核對的 host identity**；
選哪一種是 operator 決定點，E1 不得自行發明。

`_read_trust_root`（`aiml_gate_receipt_s2e_external_evidence.py:97-186`）**不改邏輯**，
只加一個 keyword-only 參數 `extra_fields: frozenset[str] = frozenset()`，
`:161` 的 `set(profile) != _TRUST_ROOT_FIELDS` 改為與 `_TRUST_ROOT_FIELDS | extra_fields` 比對，
並在 `:172` 的 expected 迴圈後追加對 extra field 的 pattern 檢查。

- durability anchor trust root 追加 `host_fingerprint`（**新增欄位**，見 §5）。
- replica trust root 使用 `_TRUST_ROOT_FIELDS + {"host_fingerprint"}`。
- predecessor registry 與 receipt signer trust root **不變**（欄位集合維持 9／既有）。

新增 loader `_load_offhost_replica_trust_root()`，形制照抄 `:189-210` 兩個既有 loader。

### 4.3 驗證接線（`validate_s2e_durability_anchor_attestation:438-528`）

在現行 `:488-498` readback 段位置，改為：

1. `readback.replica_locator == attestation.offhost_replica_locator`；
   `readback.observed_anchor_locator == attestation.anchor_locator`。
2. 四個回讀值逐一等於 anchor 側對應值：`replica_generation == anchor_generation`、
   `replica_previous_head_digest == previous_anchor_head_digest`、
   `replica_entry_digest == anchor_entry_digest`、`replica_head_digest == anchor_head_digest`。
   （**副本是同一條 ledger 的忠實鏡像**，不是獨立計數器；獨立性來自「第二把 key + 第二個 host」，
   不是來自第二個計數器。這個選擇讓 floor 只需釘一組值，見 §3.1。）
3. `_freshness_errors(readback, now=now, label="durability anchor replica readback")`
   —— **直接重用 `:342-358`**，即得 ≤10min 上界、`observed < expires`、
   `observed <= now < expires` 的**下界**。**這一步同時補回 P2-3 的 TTL 淨回歸**。
4. 保留 `:500-506` 的順序檢查（anchor 不得早於 readback），語義不變。
5. `_signature_errors`（`:361-397`）**重用**，`profile_loader=_load_offhost_replica_trust_root`，
   對象是 readback 子物件；`_signed_bytes` 對 readback 亦適用（排除三個 digest/signature 欄位的
   規則相同，但欄位名不同 ⇒ 需把 `_signed_bytes:220-231` 的排除集合改成參數化，
   預設維持現值，replica 傳入 `{"signed_core_digest", "signature"}`）。
6. `_distinct_fingerprint_errors`（`:400-415`）**重用**：subject = replica profile，
   peers = anchor profile + S2E receipt signer profile。三把 key 兩兩不同指紋。
   同時把 `:517-521` 現有呼叫的 peers 補上 replica profile（雙向）。
7. `replica_host_fingerprint` 規則見 §5。

### 4.4 連鎖：packet 前置數 14 → **16**

`helper_scripts/maintenance_scripts/agent_governance_s2e_lw1_action_packet.py`：

- `_PATH_PREREQUISITES`（`:58-114`）新增第 11 列
  `("OFFHOST_REPLICA_TRUST_ROOT", str(OFFHOST_REPLICA_TRUST_ROOT_PATH), "ROOT_OWNED_EXACT_0644_JSON_TRUST_PROFILE")`。
- `_SERVICE_PREREQUISITES`（`:118-134`）新增第 4 列
  `("OFFHOST_REPLICA_READBACK_SIGNER_CAPABILITY", "operator-config:offhost-replica-readback-signer",
  "OFFHOST_ROOT_OWNED_SIGNER_ON_SEPARATE_HOST_REACHABLE_FROM_TRADE_CORE_PRIVATE_KEY_NEVER_ON_ANCHOR_HOST")`。
  這是 `ncyu-nas` 上的簽章能力＋可達傳輸（現況 SSH:22 refused），**與既有的
  `OFFHOST_APPEND_ONLY_REPLICA` 是兩件事**：後者是副本儲存與複寫路徑，前者是「誰在第二台機器上
  用第二把 key 簽回讀證言」。合併會讓兩個獨立的失敗模式共用一個狀態欄位。
- **11 path + 4 service = `16` blocked prerequisites。**
- `EXPECTED_ACTION_IDS`（`:137-144`）新增兩項 ⇒ 共 **8** 項：
  `COMMIT_GENESIS_ARMED_DURABILITY_ANCHOR_FLOOR`（§3.5 的 PR 動作）、
  `PROVISION_OFFHOST_REPLICA_READBACK_SIGNER`（`ncyu-nas` 側）。
- `tests/structure/test_agent_governance_s2e_lw1_action_packet.py:116` 的 `== 14` → `== 16`。
- **committed artifact 必須重生**：
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_lw1_external_prerequisite_action_packet.json`
  與 `2026-08-02--s2e_lw1_readonly_inventory.json`（inventory 的 `fixed_path_statuses` key set
  由 `EXPECTED_PATHS` 執法，`:187-193`）。這正是 E4 §六指出的「artifact stale 到用自己的
  validator 跑都 FAIL 而 CI 全綠」，本次不得再犯。
- provisioning prompt（`docs/CCAgentWorkSpace/Operator/2026-08-02--s2e_lw1_tier1_provisioning_session_prompt.md`）：
  **10 把 → 11 把**（表格新增第 11 列 replica trust root）、`:43-44`「9 把裡有 7 把」→「11 把裡有 7 把」、
  `:50` 標題「Phase A — 9 把 keypair」→ 11 把、`:90` 「9 個 public key」→ 11、
  `:107-118` JSON profile 段「2 個」→ **3 個**且需說明 anchor／replica 兩份多一個
  `host_fingerprint` 欄位（欄位集合 10 個，registry 仍 9 個）、`:16`「Tier 1 下 3 項作廢」
  與 `:147/150` 的數字一併修正（複核 P2-5 已列，本次一次改完）。
  另需三項**新增內容**：
  - **A0 custody 決定新增一條硬邊界**：第 11 把（replica）的 keypair **必須在 `ncyu-nas` 上產生**，
    私鑰不得傳輸、不得出現在 trade-core、不得出現在 chat／報告／packet。
    這條與其餘 10 把的「operator 自選存放位置」不同，**不是決定點，是約束**。
  - **A4 新增 anchor／replica 兩份 trust root 的 `host_fingerprint` 取值來源**：
    anchor 取 trade-core 的 SSH host key 指紋，replica 取 `ncyu-nas` 的。
  - **A5 驗收新增一步，且必須從第三方視角執行**：以 `ssh-keyscan` **從 Mac（而非從 trade-core）**
    取兩台機器的 host key 指紋，逐字比對兩份 trust root 的 `host_fingerprint`。
    從 trade-core 取值等於讓被檢查的一方自己產出檢查證據，該證據不成立。

---

## 五、項目三 · `offhost_replica_locator` 的 host 獨立性

### 5.1 裁決：綁**獨立 host fingerprint**，不採 loopback/localhost 黑名單

規則（落在 `validate_s2e_durability_anchor_attestation` 的 §4.3 步驟 7）：

1. `readback.replica_host_fingerprint == replica_trust_root.host_fingerprint`
   （trust root 的值＝`ncyu-nas` 的 SSH host key 指紋，見 §4.2）。
2. `anchor_attestation` 側新增 `anchor_host_fingerprint`（schema 新欄位），
   必須 `== durability_anchor_trust_root.host_fingerprint`（＝trade-core 的）。
3. `anchor_host_fingerprint != replica_host_fingerprint`，否則
   `"durability anchor replica host identity is not independent from the anchor host"`。
4. 兩個 locator 都由 §3 的 committed floor 釘死，攻擊者無法逐份切換副本目標。

### 5.2 為什麼黑名單不夠（必須寫進 PR 說明）

`offhost_replica_locator` 前綴之後是自由字串（`:43` + schema pattern `:34-39`）。
黑名單 `{localhost, 127.0.0.1, ::1, 0.0.0.0}` 對真實攻擊面零效果：
`trade-core`、其 Tailscale IPv4、任一指向本機的 DNS 名、或同一台機器上的第二個目錄路徑，
全部不在黑名單內而仍是同一台 host。**對自由文字做否定列舉無法判定 host identity**，
只會產生「已檢查」的假象——這正是 §LW1 想禁止的那類自證。

host fingerprint 路線勝出的理由是**可外部核對**：指紋是一個公開值，可由第三方視角
（Mac）以 `ssh-keyscan` 對真實的第二台機器取得並逐字比對，因此把「副本是否真的在別台機器上」
從**不可查證的命名**變成**可查證的公開斷言**，並落到 provisioning A5 的 read-only 驗收步驟
（§4.4）。黑名單沒有任何對應的可核對物。

### 5.3 代碼線／provisioning 線的精確分界（operator 2026-08-03 裁決後改寫）

初版本節把 custody 分離寫成「只能由 operator 書面承擔」。operator 已裁決 replica 私鑰與簽章
動作歸屬 `ncyu-nas`，因此**分離從書面承擔升級為結構事實**，但分界線必須寫精確，不得含糊帶過。

**代碼能執法到這一條線（全部機械、全部 fail-closed）**：

1. readback 帶自己的 SSHSIG，由 `/etc/arcane-equilibrium/aiml/s2e-offhost-replica-trust-root-v1.json`
   這個固定 root-owned 路徑的公鑰驗證（沿用 `_read_trust_root:97-186` 的 TOCTOU 防護）。
2. replica／anchor／receipt signer 三把 key 的 `key_fingerprint` 兩兩不同（`_distinct_fingerprint_errors:400-415`）。
3. `anchor_host_fingerprint != replica_host_fingerprint`，且各自等於其 trust root 宣告值（§5.1）。
4. 兩個 locator 由 committed floor 釘死，不可逐份切換（§3.1）。
5. replica 有自己的 ≤10min window，且 anchor 不得早於 readback（§4.3.3-4）。
6. head／generation／entry／previous 四值由兩把 key 分別覆蓋簽署（§4.1、§4.3.2）。

**這一條線之後由 provisioning 承擔（代碼不可證，且任何代碼都不可能證）**：

- **私鑰實際存放在哪台機器**。驗證端跑在 trade-core 上，它無法區分「replica 私鑰在 `ncyu-nas`」
  與「replica 私鑰在 trade-core、trust root 填了一個造假的 host fingerprint」。
  這不是本設計的缺陷，是**任何**在受檢主機上執行的驗證器的資訊論上界。
- 承擔形式**不是**口頭聲明，而是三個可核對物：(a) keypair 在 `ncyu-nas` 上產生、私鑰從不傳輸
  （A0 硬邊界，§4.4）；(b) 兩個 host fingerprint 由 **Mac 端** keyscan 取得並逐字比對
  （A5，§4.4）；(c) `OFFHOST_REPLICA_READBACK_SIGNER_CAPABILITY` 是 packet 上的 blocking
  前置，未達成則 receipt 根本不能發射。

**E3 若再攻這一點時的正確答覆**（E1／PM 直接引用，不要自行改寫）：

> §LW1 的兩條否定條款針對的是**單一 writer**。修法後，一次 rollback 需要同時滿足三件事：
> ①在 GitHub main 上 merge 一份倒退的 anchor floor（或改寫 git history，而後者會讓既發 receipt
> 釘死的 commit SHA 不可達，`_git_binding_errors:444-457` 與 `_is_ancestor:596-603` 當場 fail）；
> ②持有 trade-core 的 anchor key；③持有 `ncyu-nas` 的 replica key。
> 只取得 trade-core root（＝spec 所指的那個「同一 writer」）**得不到 `VERIFIED`**：他可以
> coherent rewrite 自己的 ledger，但拿不到第二台機器對改寫後 head 的簽章，
> `validate_s2e_durability_anchor_attestation` 回傳非空 errors ⇒ `EXTERNAL_VERIFICATION_PENDING`。
> 因此「單一簽章不能防 rollback」與「同一 writer coherent rewrite 只能得 `UNVERIFIED`」
> **結構上成立**。殘留是「兩台機器同時被攻陷 + GitHub 寫入權」的三重複合場景，
> 那已不在 spec 這兩條款的語義範圍內，且本設計不宣稱防禦它。

**仍然具名未解**（不得因上述而抹掉）：跨 host 的併發推進（§3.6 表末列）——
single-use consumption ledger 在 `.git` common dir，是 host-local 的。

---

## 六、項目四 · `const: true` 反模式的處置

**裁決：三個旗標（`ack` / `entry_present` / `latest_generation_matches`）刪除，不改形。**

deletion test 逐一：

| 旗標 | 新形制下由誰承擔 | 結論 |
|---|---|---|
| `ack` | 「存在一份通過驗證的 replica SSHSIG」本身就是 ACK，且不可自我宣告 | 刪 |
| `entry_present` | `replica_entry_digest == anchor_entry_digest`（§4.3.2） | 刪 |
| `latest_generation_matches` | `replica_generation == anchor_generation` 且 `replica_head_digest == anchor_head_digest`（§4.3.2） | 刪 |

改成 `{"type": "boolean"}` 是**錯的選項**：那等於保留一個由 writer 自填、且已被更強的等值檢查
完全覆蓋的欄位，只會讓 `:488-495` 那段死碼「復活成冗餘碼」，並在 signed core 裡多三個可被
攻擊者用來製造歧義的自由位元。

副作用（正向）：`aiml_gate_receipt_s2e_external_evidence.py:488-495` 這段**不可達死碼消失**，
取而代之的是 §4.3 全部可達、且逐條有具名錯誤訊息的檢查——這正是複核 §六第 4 項
「斷言必須釘具體錯誤訊息」得以成立的前提。

---

## 七、其他裁決

### 7.1 `EXTERNAL_WORM_V1` 是否接回 `launch.py:1160`：**不接回，改為具名 typed 拒絕**

- **不接回的理由**：`external_sink` 三件套（intent/result/ack）已在 `209793b70` 刪除。
  把 enum 值放行而背後沒有任何 evidence validator，得到的是「宣告了一個不參與驗證的
  adapter」——與 P2-1 是同一種病（正本裡固化一句假話），而不是選言的修復。
  §LW1 的選言是「實作**可以**用 WORM **或**用 trusted-host SSHSIG」，不是「兩支都必須接線」。
- **要做的**：`aiml_gate_receipt_s2e_launch.py:1158-1163` 的錯誤訊息改為具名
  `"carrier immutable readback adapter EXTERNAL_WORM_V1 has no admitted evidence validator in this generation"`，
  並保留 carrier schema enum 的兩支（schema 層維持選言）。日後真的採購 S3 Object Lock 時，
  拿到的是精確指路而非靜默拒絕；擴充形態是 typed adapter dispatch，屬 LW-scope 新工作，
  不在本次 remediation。
- **順帶修 P2-1**：`aiml_gate_receipt_s2e_review.py:765-772` 的 predicate id
  `EXTERNAL_WORM_IMMUTABLE_READBACK_VALID` 與 `required_adapter: "EXTERNAL_WORM_V1"`
  改為 `DURABILITY_ANCHOR_IMMUTABLE_READBACK_VALID` / `TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1`，
  evidence schema 名一併改為 `s2e_review_durability_anchor_requirement_v1`。
  這是 lineage 誠實問題（CLAUDE.md「不得偽造 lineage／evidence」），不是可選項。

### 7.2 committed floor 的 review 面

`aiml_gate_receipt_s2e_review.py:47` 的 `S2E_REVIEW_BASE_PATHS` 追加 floor 檔路徑一列，
使 reviewer 簽名的 `source_blob_manifest` 逐位元組釘住 floor。成本一行，
關掉「review 與 transition 之間 floor 被換掉」這條縫。

### 7.3 P1-4 的 regression 形狀（複核 §六第 4 項）

`tests/structure/test_agent_governance_s2e_launch_receipts.py` 內，對
`:1158-1174`（carrier 四欄）與 `:1481-1492`（review 五欄）**逐欄**各一個 negative case：
篡改該欄 ⇒ 斷言**逐字**錯誤訊息出現在 errors 內（禁用 `assert errors`）。合計 9 個 case。
另對 §3.3(b) 五條規則與 §3.4 三種歷史違規（非祖先鏈／世代不遞增／第二個 `GENESIS_ARMED`）
各一個 case。**全部用相對時鐘或凍結時鐘，禁硬編日期**（`feedback_test_fixture_wallclock_timebomb`）。

新測試一律放進**既有四個測試檔**，不新增測試檔——`s2e_review_test_argv`（`:494-511`）
的 argv 是 code-owned 清單，新增檔案會連鎖改動 review predicate。

### 7.4 600 秒 hot-handoff（operator 2026-08-03 裁決：本輪一併修）

#### 7.4.1 來源調查：**是缺陷，不是刻意的 hot handoff**

不假設、逐個 commit 查過來源（`git log -S` 複驗）：

1. **`23064edba`（2026-07-30，`feat(aiml): verify S2E receipt issuance`）** 引入
   `issued_at < expires_at`、`≤600s`、`issued_at <= evaluated_at < expires_at` 三條。
   關鍵事實：**該 commit 的檔案裡還沒有 `validate_s2e_launch_predecessor_authority`**
   （`git show 23064edba:...launch.py | grep predecessor_authority` 為空）。
   當時 `validate_s2e_launch_acceptance_review_bundle` 的**唯一**消費者是 issuance。
   在那個語境下「review bundle 必須在發行當下新鮮」是**正確且必要**的：它擋的是
   把幾個月前的 reviewer 簽章拿來發今天的 receipt。**這是刻意的，而且對。**
2. **`929395f7d`（同日，`fix(aiml): enforce authenticated S2E launch gates`）** 才新增
   `validate_s2e_launch_predecessor_authority`，並讓它重用同一個 bundle 驗證器去驗
   **前一份已發行、digest 已被釘死的歷史 bundle**。
3. **`4ab2eb5d3`（同日，`fix(aiml): close adversarial S2E launch gaps`）＝決定性證據**：
   這個 commit 為了同一個重用情境**特地新增了 `require_current_generation` 參數**，
   並在 predecessor authority 呼叫點傳 `False`（現行 `:799`）。也就是說，
   **作者當時已經認知到「歷史 bundle 不該被拿去比對 current-generation 狀態」**，
   但只鬆綁了 HEAD／clean 檢查，**漏了同一性質的 wall-clock 檢查**。

⇒ 裁決：`≤600s` 的**存在**是刻意的；把它施加在 predecessor 的歷史 bundle 上是
`4ab2eb5d3` 那次鬆綁**漏做一半**。修法方向不是「放寬窗」，是**把 `4ab2eb5d3` 未完成的
那一半補完**。

#### 7.4.2 缺陷的真實範圍比初版報告的更大

不只 bundle。`validate_s2e_launch_predecessor_authority:782-820` 對四個歷史／現時混雜的
artifact 一律傳 `now=now`：

| artifact | 性質 | 現行 | 應然 |
|---|---|---|---|
| `acceptance_review_bundle` | **歷史**：digest 被 predecessor receipt 釘死，重發即改變 receipt payload digest ⇒ 物理上不可重鑄 | wall-clock 檢查 ⇒ 600s 後永久死鎖 | 免除 wall-clock |
| `review_durability_anchor_attestation` | **歷史**：值被 bundle 的 `durability_anchor_binding` 釘死（`:1481-1492`），同樣不可重鑄 | 同上（`_freshness_errors:342-358`） | 免除 wall-clock |
| `carrier_attestation` + `carrier_governed_capture_record` | **現時**：不被任何已發 receipt 的 digest 釘死，驗證時可重新產生（`:1093-1096` 甚至會 re-execute） | wall-clock 檢查 | **保持** wall-clock |
| `carrier_durability_anchor_attestation` | **現時**：與 carrier 同批重鑄 | wall-clock 檢查 | **保持** wall-clock |

判準只有一句：**該 artifact 是否被某份已發行 receipt 的 digest 釘死。被釘死的不可重鑄，
對它做 wall-clock 檢查必然在時間推移後變成死鎖；未被釘死的可重鑄，必須維持 wall-clock。**

#### 7.4.3 修法

與既有 `require_current_generation` **完全對稱**，不發明新機制：

1. `validate_s2e_launch_acceptance_review_bundle`（`:1224-1235` 簽名）新增
   keyword-only `require_current_freshness: bool = True`。
   `:1361-1372` 的時間段拆成兩半：
   - **恆檢查（時間無關的結構性上界）**：`issued_at < expires_at`、
     `(expires_at - issued_at) <= 600s`。一份宣稱十年有效窗的 bundle **任何情況下**都被拒。
   - **僅 `require_current_freshness=True` 時檢查**：`issued_at <= now < expires_at`。
2. `validate_s2e_durability_anchor_attestation`（`aiml_gate_receipt_s2e_external_evidence.py:438-443`）
   新增同名參數，`_freshness_errors:342-358` 內作同樣的兩段拆分
   （replica readback 的 window 亦同步，見 §4.3.3）。
3. 呼叫點：`validate_s2e_launch_predecessor_authority` 對
   `acceptance_review_bundle` 與 `review_durability_anchor_attestation` 傳
   `require_current_freshness=False`；**carrier 側四項一律不傳（維持 True）**。
   candidate 側（`issue_s2e_launch_receipt:1603-1613`）**一律不傳（維持 True）**。
4. 參數命名刻意與 `require_current_generation` 同前綴，讓兩者在同一個呼叫點並列可見；
   E1 不得把它們合併成一個 flag——它們鬆綁的是兩個不同的不變量，合併會讓未來的
   reviewer 無法分辨哪一個被關掉了。

#### 7.4.4 為什麼**不會**打開新的 replay 窗（這是本修法最容易出事的地方）

**核心句：本修法不加長任何窗。`≤600s`／`≤10min` 的窗長上界對每一份 artifact（含歷史件）
維持不變；被移除的只有「now 落在窗內」這個謂詞，且只對「被 digest 釘死、物理上不可重鑄」
的兩份 artifact 移除。**

歷史件的抗重放由三個**時間無關且更強**的機制承擔，逐條可查：

1. **digest 鏈釘死**：bundle digest 必須等於 `predecessor_receipt.acceptance_review_bundle_digest`
   （`:776-781`）；predecessor 的 payload digest 必須等於 `receipt["predecessor"]`（`:604-605`）；
   chain tail 必須接上（`:725-731`）。⇒ 一份舊 bundle **只能配它自己那份 receipt 出現**。
   「拿舊 bundle 重放」在語義上等於「用真正的前手當前手」——那不是重放，那就是正常鏈。
2. **git floor 釘死**（§3.3(b).1-2）：`a.anchor_generation == floor.floor_generation` 且
   `floor.bound_receipt_payload_digest == predecessor.payload_digest`。要換一份不同的歷史 anchor，
   必須先 merge 一個 commit。
3. **single-use consumption**：`consumed_predecessor_digests` 集合等值執法（`:893-903`）＋
   `.git` common dir 的 single-use slot（`aiml_gate_receipt_s2e_consumption.py:573-580`）。
   同一份 predecessor 不能被消費兩次。

而**現時件全部維持 wall-clock**：candidate 的 bundle、candidate 的 anchor、carrier、
carrier capture、carrier anchor。⇒ **任何一次 Advance 仍然必須有一組當下 ≤10 分鐘內產生的
reviewer 簽章、governed capture 與雙簽 anchor 回讀。**沒有任何路徑可以「只靠舊件」前進。

**刻意不做的事**：不為歷史件設一個較長的 wall-clock 下界（例如 30 天）。任何有限橫距都會在
更長的鏈上重現同一個死鎖，而橫距的數值必然是任意的；正確的時間序性質由 anchor floor 的
嚴格單調（§3.3）承擔，那是**因果序**而非**時鐘序**，不會腐化。

#### 7.4.5 測試形狀

放進 `tests/structure/test_agent_governance_s2e_launch_receipts.py`：

1. 歷史 bundle 的 `issued_at/expires_at` 設在**遠早於凍結 now**（用相對凍結時鐘，**禁硬編日期**，
   `feedback_test_fixture_wallclock_timebomb`）⇒ predecessor authority 驗證通過。
   這一條就是本 P1 的 regression：現行代碼下它必紅。
2. 同一份歷史 bundle 的窗長改成 `601s` ⇒ **必須仍然紅**（證明鬆綁的是謂詞不是上界）。
3. **candidate** 側 bundle 設成過期 ⇒ **必須紅**（證明現時件未被誤鬆綁）。
4. carrier 與 carrier anchor 設成過期 ⇒ **必須紅**（同上，四項各一）。
5. 每一條斷言逐字錯誤訊息，禁用 `assert errors`。

### 8.1 需要 re-emission 的 receipt／ABI

本設計會觸碰以下 **W5-owned path**（`program_code/ml_training/aiml_gate_receipt_wave_w5.py:71-88`）：

| path | 觸碰原因 |
|---|---|
| `program_code/ml_training/aiml_gate_receipt_schema_core.py` | `SCHEMA_FILES` 註冊 `s2e_durability_anchor_floor_v1` |
| `program_code/ml_training/aiml_gate_receipt_validator.py` | 新模組公開面 re-export（§8.3 有行數硬約束） |
| `program_code/ml_training/application_bundle_runtime_closure_v1.json` | `python_modules` 新增 anchor floor 模組 + `schema_resources` 新增 schema + `self_digest` 重算 |

⇒ **必須跑一輪 `w5-emit` re-emission**，且依 `TODO.md:10` 的規則，**同一個 commit 內**同步更新：
`TODO.md` 的 `W5-RECEIPT-BINDING` marker、`docs/execution_plan/ai_ml_landing/PROGRESS.md`
的同名 marker、`tests/structure/test_aiml_w5_receipt_binding_projection.py` 的
`EXPECTED_SOURCE_HEAD`。

**另一個必須一併償還的既有債**：本分支的 `209793b70` 已經改過
`aiml_gate_receipt_schema_core.py` 與 `application_bundle_runtime_closure_v1.json`
（`git show --stat 209793b70` 可複驗），**但沒有 re-emit W5**。本次 remediation 的 re-emission
必須同時涵蓋那一筆，PR 說明要明講「補償上一筆漏發射」，不得默默帶過。

### 8.2 其他必須同步重生的 artifact／投影

| artifact | 原因 |
|---|---|
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_lw1_external_prerequisite_action_packet.json` | **14 → 16**、action ids **8** 項、新 service prerequisite、`packet_digest` 重算 |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_lw1_readonly_inventory.json` | `fixed_path_statuses` key set 由 `EXPECTED_PATHS` 執法（11 條）、`service_statuses` key set 由 `EXPECTED_SERVICE_IDS` 執法（**4 條**，`:194-198`） |
| `docs/CCAgentWorkSpace/Operator/2026-08-02--s2e_lw1_tier1_provisioning_session_prompt.md` | §4.4 全部數字（11 把／3 份 JSON profile）、A0 的 `ncyu-nas` 私鑰硬邊界、A4 兩個 `host_fingerprint` 來源、A5 從 Mac 端 keyscan |
| `docs/execution_plan/ai_ml_landing/receipts/S2E-LW1-LW5/durability-anchor-floor-v1.json` | 新增（`GENESIS_ARMED`，locator 由 operator 提供後 commit） |
| `.codex/schemas/s2e_lw1_operator_action_packet_v1.schema.json` | 若 action id enum 或 prerequisite id enum 為封閉列舉則需同步 |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_external_evidence_downgrade_proposal.md` | 標 superseded（複核 P2-6） |
| `docs/_indexes/document_index.md` | 本設計檔入索引（docs/README.md:174/326） |
| `helper_scripts/SCRIPT_INDEX.md` | 若 CLI 新增旗標需要記錄則同步（不新增腳本，僅旗標） |

**TODO.md / CLAUDE.md 屬 LW1 review path set**（`aiml_gate_receipt_s2e_review.py:164-167`），
一旦改動即改變 LW1 predicate 的 blob evidence——這是預期行為，但 E1 必須知道
review bundle 會因此變值，不可事後才發現。

### 8.3 行數硬約束（不得踩線）

| 檔 | 現行 | 預估 | 約束 |
|---|---|---|---|
| `aiml_gate_receipt_s2e_launch.py` | 1849 | +65~85（含 §7.4 的參數與拆分）⇒ ~1930 | ≤2000 |
| `aiml_gate_receipt_s2e_external_evidence.py` | 614 | +80~100（含 §7.4 的 `_freshness_errors` 拆分）⇒ ~710 | ≤2000 |
| `aiml_gate_receipt_s2e_anchor_floor.py` | — | ~170（新檔） | ≤2000 |
| **`aiml_gate_receipt_validator.py`** | **1986** | **+≤10** | **必須 ≤2000** |

`aiml_gate_receipt_validator.py` 是**紅線**：`aiml_gate_receipt_s2e_review.py:571-612`
的 `_line_policy_evidence` 直接量它的行數，>2000 就強制走
`DOCUMENTED_PRE_EXISTING_EXCEPTION` 分支並要求
`docs/references/2000_line_exception_registry.md` 有閉合條目，否則 LW1 predicate oracle
直接 `raise`。E1 的 re-export 必須寫成**單一 import 區塊、每行多名**，並在 PR 前
`wc -l` 實測。若無法壓在 2000 以下，正確做法是**縮小新模組的公開面**（只 re-export
`validate`/`read` 兩個名字），不是去登記例外。

### 8.4 硬邊界不變

`task_issued_authority_count` 仍 0/9、`admitted_production_effect_receipt_count` 仍 0/6、
`production_runtime_effect_performed_by_task=false`、`runtime_state=UNVERIFIED_NOT_OBSERVED`、
S2 未關、LW2 仍 locked。本設計全部是**純驗證函式 + 一份 committed JSON**，
無 runtime／PG／broker／order／deploy effect。新增的三個 fixed host path 讀取沿用
既有 `_read_trust_root` 的 TOCTOU 防護（複核已評為高品質，不得改動其邏輯）。

---

## 九、給 E1 的實作順序

每一步結束都是合法停點；步與步之間不得合併提交。

1. **schema 先行**：新增 `s2e_durability_anchor_floor_v1.schema.json`；改寫
   `s2e_durability_anchor_attestation_v1.schema.json` 的 `$defs.replica_readback`（§4.1）
   並新增 `anchor_host_fingerprint`（§5.1.2）。註冊進 `schema_core.SCHEMA_FILES`。
   `aiml_gate_receipt_s2e_dispatch.py:48-61` 新增 floor 的 typed
   `EXTERNAL_VERIFICATION_PENDING` 分支。
2. **新模組**：`aiml_gate_receipt_s2e_anchor_floor.py`（§3.2/3.4）。先寫 §3.4 的歷史檢查與
   其 negative test，再寫 floor 規則函式。
3. **external_evidence 側**：`_read_trust_root` 的 `extra_fields` 參數、
   `_signed_bytes` 的排除集合參數化、replica trust root loader、§4.3 全部檢查、
   §5.1 host fingerprint 規則、刪三個 `const: true`（§6）、
   `_freshness_errors` 的窗長／謂詞兩段拆分（§7.4.3.2）。
3b. **600s 修法**（§7.4）：`require_current_freshness` 參數與三個呼叫點的
   True/False 分派；先寫 §7.4.5 的五組測試再改代碼，確認第 1 條在改動前必紅。
4. **launch 側接線**：§3.3 的 (a)(b)(c)(d) 四個落點 + §7.1 的具名拒絕訊息。
   `validate_s2e_launch_transition` 新參數為 keyword-only 且 **required**（不給 default，
   避免出現一條「不傳就不檢查」的靜默路徑）。
5. **CLI**：`agent_governance_s2e_launch_receipts.py` 的 `transition-gate`／`validate` 旗標（§3.3(e)）。
6. **review 側**：§7.1 的 predicate 改名 + §7.2 的 `S2E_REVIEW_BASE_PATHS` 一列。
7. **測試**：§7.3 的全部 case，加上 §4/§5/§6 的 positive+negative。**每個 negative case 斷言
   逐字錯誤訊息。** 四個既有測試檔內完成，不新增檔案。
8. **packet／inventory／prompt**：§4.4 全部；重生兩份 committed artifact 並**用它們自己的
   validator 實跑**確認 errors 為空（E4 §六 (a)(b)(c) 三條形狀）。
9. **floor 創世檔**：commit `GENESIS_ARMED` floor（locator 兩欄需 operator 先提供；未提供前
   以 blocker 停在此步，不得填佔位值）。
10. **W5 re-emission**：`w5-emit` 一輪 + `TODO.md`／`PROGRESS.md` marker +
    `test_aiml_w5_receipt_binding_projection.py:EXPECTED_SOURCE_HEAD`，同一 commit（§8.1）。
11. **收尾**：`wc -l` 四個檔（§8.3 紅線）、`git diff --check`、
    `docs/_indexes/document_index.md` 補列、降級提案標 superseded。

**E1 不得自行擴張的邊界**：不得放寬任何既有硬邊界；不得為了讓測試變綠而給
`validate_s2e_launch_transition` 的新參數加 default；不得把 §3.6 的「gap 內不宣稱」
在註解或 PR 說明裡寫成「hash chain 已完整驗證」；不得把 §7.4 的
`require_current_freshness` 與 `require_current_generation` 合併成一個 flag；
不得為了讓 §7.4 更「安全」而加長任何窗長上界或改動 `600` / `MAX_ATTESTATION_TTL` 的數值；
不得在 replica trust root 填佔位 `host_fingerprint`；不得宣稱 §5.3 的
「私鑰實際位置」已被代碼證明。

---

## 十、被拒絕的替代方案

| 方案 | 拒絕理由 |
|---|---|
| **只在 transition gate 比對 caller 供給的前後兩份 authority**（複核 §六第 1 項的字面最小解） | gate 的兩側都由 caller 提供，等於讓被驗證者自己提供比較基準。必須有一個 code-owned、從 git 讀的 pin，否則 P1-1 只是換了個位置。 |
| **把 anchor head 寫進 receipt schema 欄位**（而非另立 floor 檔） | receipt 的 payload digest 已被大量既有檢查釘住，加欄位等於改動 `s2e_launch_wave_receipt_v1` 與 `s2e_launch_genesis_receipt_v1` 兩份 schema、`launch_payload_digest`、`_pending_candidate_from_issued`、全部既有 fixture 與 `_launch_chain_errors` 的鏈驗證。blast radius 遠大於一份獨立 floor 檔，且仍是 caller 供給的物件（receipt 本身就是 caller 給的檔案），沒有解決根本問題。 |
| **每次 anchor mint 都 commit 一筆 ledger（真 append-only in git）** | anchor TTL ≤10 分鐘，重試必然發生；要求每次 mint 走 PR merge 在操作上不可行，會把 gate 變成永久 blocker。 |
| **為 gap 提供 link-path 證明** | 中間條目的 `entry_digest` 無原像可驗，任何人都能編一條合法路徑。這是**假安全性**，比不做更糟（會誘導後續 reviewer 以為 hash chain 完整）。 |
| **replica locator 用 loopback/localhost 黑名單** | 見 §5.2：對自由文字做否定列舉無法判定 host identity，且無任何可外部核對物。 |
| **replica 三個旗標改成 `{"type": "boolean"}`** | 見 §6：被更強的等值檢查完全覆蓋，只會把死碼變冗餘碼，並在 signed core 多三個可製造歧義的自由位元。 |
| **replica 使用自己獨立的 generation 計數器** | 副本是同一條 ledger 的鏡像；獨立計數器會讓 floor 需要釘兩組值、讓「兩者該不該相等」變成一個新的歧義面，而換不到任何額外的安全性（獨立性來自第二把 key 與第二台 host，不是第二個計數器）。 |
| **接回 `EXTERNAL_WORM_V1` 成為執行期選言** | 見 §7.1：背後沒有 evidence validator，接回等於再固化一句假話。 |
| **把新邏輯塞進 `aiml_gate_receipt_s2e_launch.py`** | 1849 行 + git 讀取 + 歷史走訪會逼近 2000 行門檻；且會把 git 子程序面帶進 `external_evidence.py` 這個目前純 attestation 的模組，破壞模組邊界。 |
| **（600s）把窗長從 600s／10min 加長** | 直接加長舊 bundle 與舊 anchor 的可用期＝真的打開 replay 窗，正是 operator 點名最容易出事的那條路。任何有限橫距都會在更長的鏈上重現同一死鎖，數值必然任意。 |
| **（600s）讓 predecessor 的 bundle 可重鑄** | bundle digest 進 receipt payload digest，重鑄即改變 predecessor 的 `payload_digest`，連鎖打斷 `receipt["predecessor"]`、chain tail、consumption slot 三處綁定。等於把整條鏈的抗重放基礎拆掉來換一個時鐘問題。 |
| **（600s）為歷史件設一個較長的 wall-clock 下界（如 30 天）** | 見 §7.4.4 末段：橫距任意且必然腐化；正確的序性質是 anchor floor 的因果序，不是時鐘序。 |
| **（replica）把 `OFFHOST_REPLICA_READBACK_SIGNER_CAPABILITY` 併進既有 `OFFHOST_APPEND_ONLY_REPLICA`** | 兩個獨立失敗模式（副本儲存不存在／第二台機器無簽章路徑）共用一個狀態欄位，會讓 packet 無法表達「副本有了但沒人能簽」這個真實中間態。 |

---

## 十一、誠實邊界

- 本設計未執行任何測試、runtime、PG、broker 或 deploy 動作，全部結論來自 source 與 spec 逐行複讀。
- §8.3 的行數為**估算**，E1 必須實測。
- **證據等級分層**：§7.4.1 的三個 commit 來源鏈由 PA 以 `git log -S` / `git show` 直接複驗；
  `ncyu-nas` 的 tailnet 存在由 PA 於 Mac 端 `tailscale status` 直接複驗；
  **trade-core 無 NAS 掛載、`ncyu-nas:22` refused 兩項為 PM read-only 觀察，PA 未自行複驗**
  （PA 未對 trade-core 執行任何 ssh）。E1 在 provisioning 前應重取當下觀察，不得沿用本檔數值。
- §3.6 表格中「跨 host 併發推進」是**具名未解**項，本設計不宣稱解決。
- §5.3 的 custody 分離在 operator 2026-08-03 裁決後為**結構事實**，但「私鑰實際位置」
  仍非代碼可證（見 §5.3 分界線）；本設計只宣稱代碼線內的六條，不宣稱更多。
- 本設計不改變 §LW1 的其他要求（private-penetration guard、recovery intent family、
  dual-lock manifest、kernel-derived identity、2000 行政策），那些仍是 LW1 的獨立 exit 條件。
