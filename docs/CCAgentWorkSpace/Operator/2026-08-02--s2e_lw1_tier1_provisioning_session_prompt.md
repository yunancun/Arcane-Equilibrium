# S2E-LW1 Tier 1 provisioning 輔導 session — 開場 prompt

**用法**：開新 session，把本檔全文貼上，或說「讀 `docs/CCAgentWorkSpace/Operator/2026-08-02--s2e_lw1_tier1_provisioning_session_prompt.md` 並依此執行」。

---

你是這個 session 的執行助手，任務是**輔導 operator 完成 S2E-LW1 Tier 1 的 host 側 provisioning**。
operator 有 trade-core 的 root，你沒有。你負責：查證精確規格、產生要貼的指令、read-only 驗收、
以及需要改 source 時自己改。**你不得代替 operator 執行任何 root 寫入。**

## 0. 先讀（不要憑記憶做事）

1. `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_external_evidence_downgrade_proposal.md`
   — Tier 1 降級提案，operator 已於 2026-08-02 裁決**採納 Tier 1**。
2. `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_lw1_external_prerequisite_action_packet.json`
   — **16 項** blocker 的機器正本（12 個 fixed path ＋ 4 個 service）。**無任何一項作廢**：降級提案 §五 曾寫「Tier 1 下 3 項作廢／14→11」，該說法已於 2026-08-03 更正並標為 superseded，總數從未減少，改變的只有組成。
3. `helper_scripts/maintenance_scripts/agent_governance_s2_5_recovery.py:45-115`
   — 7 個 recovery 能力的 signer identity／namespace／固定路徑／**已釘死的 fingerprint 常數**。
4. `program_code/ml_training/aiml_gate_receipt_s2e_launch.py:46-48, 265-360`
   — S2E receipt signer trust root 的路徑與 profile 期望值。
5. `program_code/ml_training/aiml_gate_receipt_s2e_external_evidence.py:25-60, 94-183`
   — predecessor registry trust root 的 profile 期望值與檔案權限檢查。

## 1. 硬安全邊界（不可違反）

- **private key 絕不進入 repo、prompt、chat、報告、packet。** 你不得索取、不得代為產生後回貼、
  不得寫進任何檔案。public key 與 fingerprint 不是機密，可以正常貼。
- 你不得 deploy／restart／改 PG／碰 broker／下單。本 session 的 effect 上限是：改 source（走 PR）
  ＋ read-only `ssh trade-core` 驗收。
- 所有 `/etc` 寫入由 operator 自己在 trade-core 上跑。你只產生指令並解釋每個參數。
- 本 session 結束時 `task_issued_authority_count` 必須仍是 0/9、production effect 0/6。
- main 直推禁止；source 改動走 feature branch → PR → `gh` merge。

## 2. 你必須先講清楚的一件事（不要跳過）

`agent_governance_s2_5_recovery.py` 裡 7 個 `RECOVERY_*_TRUST_ROOT_FINGERPRINT` 常數是
**2026-07-30 `f17a8a819` 那次 source-only commit 寫死的，對應的公鑰在 repo 內外都不存在**，
而且測試一律 `monkeypatch` 掉這些常數（見 `tests/structure/test_agent_governance_s2_5_recovery.py:58-88`、
`tests/structure/s2_5_testkit.py:114`），所以**它們從未對真實金鑰驗過**。

後果：operator 新產的金鑰 fingerprint 一定對不上這 7 個常數。所以順序必須是
**產金鑰 → 回報公鑰 → 改 source 重新釘 fingerprint（PR）→ 安裝 → 驗收**，
不能先裝完才發現對不上。11 把裡有 7 把受此影響；另 4 把（四個 JSON trust profile）只做自洽檢查
（`key_fingerprint` 必須等於從 `public_key` 導出的值），不需要改 source。

重新釘 fingerprint **是正常的 provisioning 收尾，不是放寬 gate**：釘死公鑰指紋的目的是防止有人
事後換掉 trust root，而現在釘的是佔位值。但改動必須在 PR 說明裡明講「以 operator 實際產生的
公鑰取代未經驗證的佔位常數」，並附 7 個新 fingerprint。

## 3. Phase A — 11 把 keypair（現在可做）

### A0 先讓 operator 決定 private key custody（決定點，不要替他決定）

7 個 recovery 能力＋4 個簽章身分（receipt signer／predecessor registry／durability anchor／off-host replica readback）各自一把獨立 ed25519 私鑰。這些私鑰**目前沒有消費者**
（`attest-v2` 等能力尚未實作），所以要先講明：現在產＝先有一批暫時沒人用的私鑰。
請 operator 明確指定存放位置與保護方式（例如 trade-core 上 root-only 目錄、或離線保管），
並把決定寫進本 session 的收尾報告（只記位置與保護方式，不記內容）。

> **硬邊界（operator 2026-08-03 裁決，不是建議）：第 11 把（off-host replica readback）的
> 私鑰必須在 `ncyu-nas` 上產生、且永不離開該機；trade-core 的 root 不得持有它。**
> 這是整個 2-of-2 的**唯一**支點：若兩把私鑰都在 trade-core，持有 root 的人同時是 anchor
> writer 與它自己副本的唯一證人，§LW1「單一簽章不能防 rollback」「同一 writer 可 coherent
> rewrite 只能得 `UNVERIFIED`」就仍然被違反——2026-08-03 的兩輪對抗複核都是卡在這一點。
> 代碼能執法的到「兩個指紋不等」為止，**私鑰實際在哪台機器，代碼證不了**，只能由這條
> provisioning 事實承擔。因此：**在 `ncyu-nas` 上 `ssh-keygen`，不要在別處產生後複製過去。**
>
> 已知前置缺口（PM 2026-08-03 實測）：`ncyu-nas`（100.77.15.17，linux）在 tailnet 上，但
> `trade-core → ncyu-nas:22` 是 **Connection refused**——主機在、網路通、**沒有 SSH listener**。
> 所以第 11 把在 `ncyu-nas` 開得出簽章路徑之前無法產生，這是一個具名 blocking 前置
> （`OFFHOST_REPLICA_READBACK_SIGNER_CAPABILITY`），與三支未實作的 root-owned producer 同級。
若 operator 選擇延後，合法做法是**只做 A1 的四個 JSON profile**，7 把 .pub 等能力實作時再產。

### A1 產生（operator 執行，逐把）

11 個目標，identity／namespace 全部由 source 固定，不可自選：

| # | 安裝路徑 | signer_identity | signature_namespace |
|---|---|---|---|
| 1 | `/etc/arcane-equilibrium/trust/s2-5-recovery-authorization.pub` | `aiml-s2-5-recovery-operator-v1` | `arcane-equilibrium-aiml-s2-5-recovery` |
| 2 | `/etc/arcane-equilibrium/trust/s2-5-recovery-anchor.pub` | `aiml-s2-5-recovery-anchor-owner-v1` | 見 source `:48-50` |
| 3 | `/etc/arcane-equilibrium/trust/s2-5-recovery-anchor-readback.pub` | 見 source `:51-56` | 見 source `:51-56` |
| 4 | `/etc/arcane-equilibrium/trust/s2-5-recovery-consumption.pub` | 見 source `:57-62` | `arcane-equilibrium-aiml-s2-5-recovery-consumption` |
| 5 | `/etc/arcane-equilibrium/trust/s2-5-recovery-actor-capture.pub` | `aiml-s2-5-recovery-actor-attestor-v1` | `arcane-equilibrium-aiml-s2-5-recovery-actor-capture` |
| 6 | `/etc/arcane-equilibrium/trust/s2-5-recovery-verifier-capture.pub` | `aiml-s2-5-recovery-independent-verifier-v1` | `arcane-equilibrium-aiml-s2-5-recovery-verifier-capture` |
| 7 | `/etc/arcane-equilibrium/trust/s2-5-recovery-host-capture.pub` | 見 `aiml_gate_receipt_s2_5_host_capture.py:39-52` | 同左 |
| 8 | `/etc/arcane-equilibrium/aiml/s2e-receipt-trust-root-v1.json` | `aiml-s2e-receipt-signer-v1` | `arcane-equilibrium-aiml-s2e-receipts` |
| 9 | `/etc/arcane-equilibrium/aiml/s2e-predecessor-registry-trust-root-v1.json` | `aiml-s2e-predecessor-registry-attestor-v1` | `arcane-equilibrium-aiml-s2e-predecessor-registry` |
| 10 | `/etc/arcane-equilibrium/aiml/s2e-durability-anchor-trust-root-v1.json` | `aiml-s2e-durability-anchor-attestor-v1` | `arcane-equilibrium-aiml-s2e-durability-anchor` |
| 11 | `/etc/arcane-equilibrium/aiml/s2e-offhost-replica-trust-root-v1.json` | 見 source `_load_offhost_replica_trust_root()` | 同左 |

> **Tier 1 落地後更新(2026-08-02，2026-08-03 remediation 再更新)**:原本 9 把 → Tier 1 的
> 10 把 → 現在 **11 把**。第 10 列取代了外部 WORM provider trust root；**第 11 列是
> 2026-08-03 對抗複核後新增的 off-host replica readback 簽章身分**——複核判定原本的
> 「replica 回讀」由 anchor 自己那把 key 自簽自證，等於沒有第二方，故拆出獨立一把。
> 四個 JSON profile 的 `attestor_class` 正本在
> `program_code/ml_training/aiml_gate_receipt_s2e_external_evidence.py` 的
> `_load_*_trust_root()`,**務必逐欄從 source 讀**,不要抄本表。

**你要做的**：逐一從 source 讀出上表「見 source」的實際字串填滿，不要抄本表的省略欄。
產生一律 `ssh-keygen -t ed25519`，每把獨立、無 passphrase 與否由 operator 決定，
私鑰路徑由 A0 的決定給定。

### A2 回報（operator 貼給你）

11 個 public key（`ssh-ed25519 AAAA…` 一行）與對應
`ssh-keygen -lf <pub>` 的 `SHA256:` fingerprint。**這是公開資訊，可以貼。**

### A3 source 重新釘 fingerprint（你做，走 PR）

把 7 個 `RECOVERY_*_TRUST_ROOT_FINGERPRINT` 換成 A2 回報的真值。
同時檢查是否有其他模組另行釘了同一批指紋（至少 `aiml_gate_receipt_s2_5_host_capture.py` 有一個）。
PR 說明必須含：取代的是未驗證佔位值、7 個新 fingerprint、以及「不改任何驗證邏輯」的聲明。
測試不得為此放寬；既有 monkeypatch 測試維持原樣。

### A4 安裝（operator 執行，root）

檔案硬性條件，任何一項不符即 fail closed：

- **7 個 `.pub`**（`_read_fixed_recovery_public_key`，`agent_governance_s2_5_recovery.py:300-327`）：
  regular file、`st_nlink == 1`、非 symlink、owner uid 0、**不得 group/world writable**
  （`mode & 0o022 == 0`）、size 介於 16–4096 bytes、純 ASCII、內容必須以 `ssh-ed25519 ` 開頭。
- **4 個 JSON profile**（`_read_trust_root`，`aiml_gate_receipt_s2e_external_evidence.py`）：
  owner uid **必須是 0**、mode **必須剛好 `0644`**、非 symlink、`st_nlink == 1`、≤16 KB、
  UTF-8 嚴格 JSON 且**不得有重複 key**，欄位集合必須**完全等於**下列集合（多一個少一個都失敗）。
  E3 round-4 R4-4 更正（2026-08-06）：本段原本只寫「這 9 個」並對四份 profile 一體適用，
  **對其中兩份是錯的**，照著做會直接吃到 `trust root fields are not exact`。
  基礎 9 欄（`_TRUST_ROOT_FIELDS`，`aiml_gate_receipt_s2e_external_evidence.py:68-78`）：
  `schema_version`、`signer_identity`、`signature_namespace`、`algorithm`、`key_generation`、
  `anchor`、`public_key`、`key_fingerprint`、`attestor_class`。
  **durability anchor 與 off-host replica 兩份是 10 欄**：基礎 9 欄再加 `host_fingerprint`
  （`_HOST_FINGERPRINT_FIELDS`，同檔 `:79`；`:305-321` 兩處 `extra_fields=`）。
  predecessor registry 與 receipt signer 不加。
  固定值：`algorithm="SSH-ED25519"`、`key_generation="independent_off_repo_ed25519_v1"`、
  `anchor="fixed_off_repo_public_trust_root_v1"`；`key_fingerprint` 必須等於由 `public_key` 導出的值。
  各份的 `attestor_class` **逐字**（同檔 `:306`、`:321`、`:332`）：durability anchor＝
  `HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1`、off-host replica＝
  `OFFHOST_APPEND_ONLY_REPLICA_READBACK_V1`、predecessor registry＝
  `HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1`。
  （R4-4：本行原寫 predecessor registry 為 `EXTERNAL_APPEND_ONLY_…`，那是 Tier 1 之前的
  舊字串，代碼早已改為 `HOST_…`，照舊字串寫必被 `attestor_class is invalid` 拒。）
  predecessor registry 的 `schema_version="s2e_predecessor_registry_trust_root_v1"`；receipt signer 的
  `schema_version="s2e_receipt_signer_trust_root_v1"`，其欄位集合另見
  `aiml_gate_receipt_s2e_launch.py:340-360`（含 `governed_pytest_provider_profile_id`，與上表不同，
  **必須逐欄從 source 讀，不要套用 registry 的欄位表**）。

指令給 operator 時一律**單行**，一次一個檔，不要串成一大段。

**`host_fingerprint` 兩欄的取值來源（2026-08-03 新增，不可自己編）**：durability anchor 與
off-host replica 兩份 trust root 各要填一個 `host_fingerprint`，且**兩者必須不等**（驗證端
逐字比對）。取值必須是真實的 SSH host key 指紋：anchor 側＝`trade-core` 的、replica 側＝
`ncyu-nas` 的。**不得填佔位值**——`agent_governance_s2_5_recovery.py` 那 7 個從未對真實金鑰
驗過的 `RECOVERY_*_FINGERPRINT` 佔位常數，正是這麼來的（見本文 §2），不要重蹈。

### A5 驗收（你做，read-only）

透過 `ssh trade-core` 逐檔驗：`stat` 出 uid/mode/nlink、`file` 確認非 symlink、
`ssh-keygen -lf` 比對 fingerprint 與 A3 釘入的常數是否逐字相同、JSON 以 `python3 -c` 嚴格解析並
比對欄位集合。**任何一項不符就明講不符，不要四捨五入成通過。**

**兩個 `host_fingerprint` 必須從 Mac 端 `ssh-keyscan` 核對，不要在 trade-core 上取。**
被檢查的那台機器不能產出自己的檢查證據——在 trade-core 上算出來的「trade-core 指紋」，
對「這兩份 trust root 是不是同一個 root 寫的」這個問題沒有任何證明力。從 Mac 分別
`ssh-keyscan` 兩台，再與兩份 JSON 內的宣告值逐字比對。若 `ncyu-nas` 仍無 SSH listener
（A0 的已知前置缺口），**這一步就做不了，據實記為未完成，不要用 trade-core 的值代替。**

## 4. Phase B — host-local anchor／registry 能力 ＋ NAS 複寫

**契約已落地**（2026-08-02 Tier 1）：`aiml_gate_receipt_s2e_external_evidence.py` 現在只接受
`host:append-only-durability-anchor:*`、`replica:offhost-append-only:*`、
`registry:host-append-only:*` 三個 locator class，並要求 append-only monotonic head
＋ off-host latest-generation 回讀。

但**能力本體仍未實作**：durability anchor 與 predecessor registry 這兩支 root-owned 產生器，
與 `attest-v2` 同一級,repo 內只有驗證端契約。因此 Phase B 的可做／不可做是：

- **可做**：NAS 上的 append-only 複寫路徑與保留策略（operator 決定實際掛載點與 locator 尾綴）。
- **不可做**：安裝 anchor／registry 能力 —— 它們還沒被寫出來。

若 operator 在本 session 要求安裝這兩支能力，請說明它們尚未實作並停在這裡，
**不要自行發明** 產生器的形制、argv 或簽章流程。

## 5. 收尾

產出一份 session 報告放 `docs/CCAgentWorkSpace/Operator/`，內容：
A0 custody 決定（只記位置與保護方式）、11 項逐檔實測狀態、A3 的 PR 連結與 7 個新 fingerprint、
未完成項與原因、以及明確聲明本 session 沒有 production effect。
（R4-4：「9 項」是 Tier 1 之前的舊數；現行為 11 個檔／16 項前置＝12 path＋4 service。）

**若驗證端與 repo 不同 uid**（root-owned producer 讀 `ncyu` 所有的 repo）：git 會
`fatal: detected dubious ownership` 而整條 floor 讀取永久 REJECTED。這是**正確的
fail-closed**，不是 bug。放行只能由 operator 寫進 **root 自己的** protected config：

```
git config --system --add safe.directory /home/ncyu/TradeBot/srv
```

代碼**不會**再自己帶 command 域的 `safe.directory`（E3 round-4 R4-1：那等於接受 repo
的 local config，而 `git status` 會執行其中的 `core.fsmonitor`／`filter.*.clean`，
於是寫得了 `.git/config` 的非 root 使用者能以 root 執行任意程式）。這條屬三支
root-owned producer 能力的 provisioning 事實，不是新增的 machine 前置——那三支本來就
blocking，receipt 現在一樣發不出。

**誠實邊界**：Phase A 全綠也**不代表** LW1 exit。它只把 16 項 blocker 降到剩
`attest-v2` 能力（未實作）＋ Phase B 兩項。W0 genesis 與 LW1 receipt 仍未發、LW2 仍 locked、
S2 仍未關閉。不要在任何報告裡把 Phase A 完成寫成 wave 前進。
