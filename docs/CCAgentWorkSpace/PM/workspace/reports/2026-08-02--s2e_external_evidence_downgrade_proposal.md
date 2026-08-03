# S2E external-evidence 契約降級提案（待 operator 裁決）

> **SUPERSEDED（2026-08-03）——本檔保留為決策史，不得當作現行事實引用。**
> 三處已被後續證據推翻或取代：
> 1. **§五的「blocker 14 → 11」是錯的。** 總數維持 **14**，改變的是組成（付費外部
>    custody 3→0、待實作 root-owned 能力 1→3）。原估漏算「取代外部服務的 host 側能力
>    本身也要寫」。更正正本＝`2026-08-02--s2e_tier1_durability_anchor_implementation.md` §三。
> 2. **本提案的核心論證「實作比它自己的 spec 更嚴」不成立。** 2026-08-03 三路獨立對抗
>    複核（E2/E3/E4）全 FAIL：據以降級的 §LW1 選言第二支，全文要求 monotonic
>    counter/head 必須**外部**、明寫**單一簽章不能防 rollback**、且**同一 writer 可
>    coherent rewrite 時只能得 `UNVERIFIED`**——落地的 Tier 1 實作三條逐字違反。
>    誤讀源＝`TODO.md` 的摘要投影漏抄「外部」二字。全文＝
>    `2026-08-03--s2e_tier1_adversarial_review_fail.md`。
> 3. **後續路徑已由 operator 於 2026-08-03 裁定**：不退回 Tier 0，改為修成真的合 spec；
>    replica 第二把簽章真的放第二台機器 `ncyu-nas`。設計正本＝
>    `docs/execution_plan/ai_ml_landing/design/S2E-LW1-tier1-remediation.md`。

日期：2026-08-02
狀態：`SUPERSEDED_BY_2026_08_03_REMEDIATION`（原狀態 `PROPOSAL_AWAITING_OPERATOR_RATIFICATION`
於 2026-08-02 獲 operator 採納為 Tier 1，其實作隨後於 2026-08-03 複核 FAIL）— 本文不是
已採納設計，未改任何 source。
來源：operator 於 LW1 blocker 判斷中選定路徑 B。
基準 head：`097c879b9`（worktree clean）；LW1 implementation checkpoint=`e68966670`；
blocker packet=`sha256:c13142b4…d5809`（14/14 blocking）。

---

## 一、最重要的發現：實作比它自己的 spec 更嚴

`docs/execution_plan/ai_ml_landing/design/S2E-launch-wave-specs.md` §LW1 對 anchor 的
規定是一個**選言**：

> anchor 必須使用 append-only/WORM，**或**使用同時綁獨立 key identity、外部 monotonic
> counter/append-only head、trusted freshness window、latest-generation immutable readback
> 的 trusted-host SSHSIG，單一簽章不能防 rollback

實作只收下第一支，而且再收窄成 AWS 專屬：

- `aiml_gate_receipt_s2e_external_evidence.py:40` — `aws:s3-object-lock-attestor:` 硬前綴
- 同檔 `:485` — `object_lock_mode != "COMPLIANCE"` 直接 fail
- `:396` — `local`／`fixture`／`memory`／`test` scheme 一律判為 local evidence 拒收

也就是說，**回到 spec 第二支不是安全性降級，是撤掉實作單方面加上的收窄**。而第二支所需
的四個成分，三個已經在現有 source 裡：獨立 key identity（`_distinct_fingerprint_errors`）、
external monotonic head（predecessor registry 的 `registry_generation` +
`previous_registry_head_digest` 鏈）、trusted freshness window（`MAX_ATTESTATION_TTL`
10 分鐘）。只缺 latest-generation immutable readback 的 host 側等價實作。

## 二、三個外部服務各自買到什麼（逐項拆解，不是打包）

| 服務 | 防的攻擊 | 機制實質 | 需要 AWS 嗎 |
|---|---|---|---|
| append-only predecessor registry（distinct custody） | 重放 predecessor receipt 換第二個 successor（wave transition double-spend / rollback） | `slot_id` + `GRANTED_ONCE` + `conflicting_grant_absent` + generation/head hash chain | **否**。是 hash chain＋獨立 key custody，與後端是誰無關 |
| external WORM destination（S3 Object Lock COMPLIANCE） | **operator/root 本人事後刪改已發出的 receipt** | COMPLIANCE mode 保留期內連 AWS root 帳號都刪不掉 | 是（此形式） |
| WORM provider attestor（第三份 custody） | caller 偽造 S3 的 append/readback 結果 | 見 `:411` docstring：「Require authenticated provider proof above **caller-injected** S3 results」 | 只在有 #2 時才存在 |

**關鍵結構**：#3 的存在理由完全是為了撐住 #2。S3 的結果是 caller 注入的，所以需要第三方
簽證它。**拿掉 #2，#3 自動消失** —— 這是一次去掉兩個服務，不是一個。

## 三、決定性論證：#2 防的攻擊者，不在本系統的威脅模型內

LW1 這一輪全部的加固（含 `e68966670` 那個最後 P1）防的是同一個攻擊者：
**trade-core 上同 UID 的非特權程式偽造 source/host/process/clock 事實**。這個威脅是真的、
值得防，因為那台機器最終會持有交易授權。

但 COMPLIANCE-mode WORM 防的是**另一個攻擊者：系統擁有者本人事後改寫歷史**。這是
anti-repudiation 控制，它需要一個「relying party」—— 一個不信任 operator、且會去驗這條
receipt chain 的外部對象（監管、外部稽核、對手方）。

**本系統目前沒有這樣的對象。** 這是單一 operator 自有系統，receipt chain 的唯一消費者就是
operator 自己與其 agent。一個沒有 relying party 的 anti-repudiation 控制，防的是一個不存在
的爭議。

而且威脅模型上更直接的一點：如果 trade-core root 被攻陷，攻擊者已經同時持有 Bybit live
credentials 與 Rust 執行授權 —— **他已經拿到錢了，audit trail 的完整性是損失清單裡最不重要
的一項**。為了保護「已經輸掉的那一局的紀錄」而長期付三個外部 custody 的帳，代價與收益不成比例。

## 四、成本是經常性的，不是一次性的

- `MAX_ATTESTATION_TTL = 10 分鐘`（`:53`）＋ `retain_until` 必須晚於 `expires_at`（`:503`）
  ⇒ **每次發 receipt 都要三個外部服務在 10 分鐘窗內活著回應**。LW2–LW5 每一段、以及任何
  head 變更後的重發，都要再付一次。這是長期營運依賴，不是一次性設定。
- COMPLIANCE 物件在保留期內不可刪 ⇒ 儲存費用在寫入當下就鎖死，且**不可逆**。
- 撞 Root Principle 14（「baseline 系統必須能在沒有外部付費服務下運作」）。依 Typed Authority
  Matrix，這是 `normative_policy` 對 `implementation_contract` 的跨類衝突：該讓步的是
  implementation contract。此衝突在此正式 emit 為 CONFLICT。

## 五、三個方案

### Tier 0（現狀，不建議）
三個外部服務、AWS COMPLIANCE。blocker 14/14，其中 3 項要付費外部 custody。

### Tier 1（**建議**）— 回到 §LW1 spec 第二支
1. **保留** predecessor registry 的全部語義（single-use、generation/head chain、獨立 key
   custody、10 分鐘 freshness），後端改為 trade-core 上 root-owned、與 receipt signer 不同
   key custody 的 append-only capability + monotonic head 檔。
2. **移除** external WORM destination 與 WORM provider attestor 兩個服務，及其 trust root。
3. **durability 的替代**：receipt 與 head chain 以 append-only 方式複寫到 NAS（已有硬體，
   10GbE），做 off-host 副本；readback 由 root-owned readback capability 簽證
   latest-generation。滿足「離開產生它的主機」而不需付費服務。

效果：**blocker 14 → 11，且 11 項全部變成免費、host 側、可逆、operator 一次 root session
可完成**（9 項是 `ssh-keygen` + `install -m 0644 -o root`；1 項是 host-local registry
capability；1 項是 `attest-v2`，見下方「誠實邊界」）。

> **更正（2026-08-03）：上段的 14 → 11 是錯的。** 總數維持 14，改變的只有組成；
> 且 Tier 1 的**開發量比 Tier 0 大**（待實作 root-owned 能力 1→3）。詳見本檔開頭
> SUPERSEDED 標註第 1 點。

### Tier 2（最小，不建議）
只留固定 trust roots + `attest-v2`，拿掉 registry。**會失去 wave transition 的 double-spend／
rollback 防護** —— 而那正是本輪唯一真正對到威脅模型的外部控制，且它本來就不需要 AWS。
省的錢是零，失去的是真的。不建議。

## 六、Tier 1 降級後具體失去什麼（不粉飾）

1. **失去對「root 被攻陷後偽造整條鏈」的抵抗。** Tier 0 的兩份 custody 在不同信任域，
   root 攻陷仍偽造不了；Tier 1 兩份 custody 都在 trade-core 上，root 攻陷即全失守。
   接受理由見 §三（root 攻陷時錢已經沒了）。
2. **失去對 operator 本人事後改寫的抵抗。** 明確接受：沒有 relying party。
3. **git 不能拿來頂替 WORM。** 必須誠實記錄：本 repo 的 main 在 2026-07-16 曾以
   `filter-repo` 全史重寫過。所以「git/GitHub 是我們的 append-only ledger」在本專案是
   經驗上為假的說法，不可作為降級理由。durability 要靠 §五 Tier 1 第 3 點，不是靠 git。

## 七、可逆性（回到 Tier 0 的代價）

Tier 1 **不改 contract 形狀**：attestation 物件、distinct-fingerprint 要求、freshness window、
monotonic head、immutable readback 五項語義全部保留，只換 durability anchor 的**後端類別**。
因此日後要升回 Tier 0：只需重新開放 locator allowlist ＋ provision AWS 側，不需重新架構；
且 Tier 1 期間發出的 receipt 在 Tier 0 下仍可驗。降級不製造不可逆債。

反向的不可逆性在 Tier 0 那邊：一旦寫入 COMPLIANCE 物件，保留期內無法回收。

## 八、治理警示（必須明講）

Tier 1 會**反轉 `d3a21f4e4` 那個 Codex P2 的修法** —— 該修法把 `file:`／`unix:` 等本地
backend 從 provider locator 排除。那個修法在「provider 必須是外部的」這個前提下是正確的。
Tier 1 改的是前提，不是繞過修法。

但這在形狀上與「悄悄放寬 gate」難以區分，而那正是整套治理要防的失效模式。因此：

- 本降級**只能**由 operator 明確裁決落帳（AMD 或等價決定），不得由 agent 自行認定。
- 落帳時必須同時記錄：撤銷的是哪一條實作收窄、保留了哪五項語義、以及 §六 三項具名失去。
- 負向 mutation 測試不是刪除，是改為斷言「host-local registry locator 接受、任意其他
  scheme 仍拒」，維持等量覆蓋。

## 九、誠實邊界

- **`attest-v2` 不在本提案的降級範圍內。** `/usr/local/libexec/arcane-equilibrium/
  s2-5-recovery-host-capture-attest-v2` 在 repo 內只有消費端契約
  （`aiml_gate_receipt_s2_5_host_capture.py:39-43` 與 schema `const`），**沒有實作、沒有
  installer**。無論 Tier 0 或 Tier 1，它都要被寫出來，是剩餘 blocker 裡唯一的真開發項。
  packet 把它列成一行 `ABSENT`，低估了它。
- 本提案未執行任何 runtime／PG／broker／order effect，未 provision 任何東西，未改 source。
  `task_issued_authority_count` 與 production effect 計數不變（0/9、0/6）。
- 未經 subagent 對抗複核；本文為 PM 直接讀 source 後的分析，結論可由上列行號自行復算。

## 十、裁決請求

請 operator 裁：**採 Tier 1 / 維持 Tier 0 / 採 Tier 2**。

採 Tier 1 後我可接的 source work（不需外部服務、不需你的 root）：
1. locator/allowlist 與 durability-anchor validator 改寫（`aiml_gate_receipt_s2e_external_evidence.py`
   為主，含 schema 與等量負向覆蓋）。
2. `attest-v2` 的 spec 與實作。

需要你親手做的只剩：9 把 keypair 產生與安裝、host-local registry 的 root 安裝、NAS 複寫路徑。
