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
   — 14 項 blocker 的機器正本（Tier 1 下 3 項作廢，見提案 §五）。
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
不能先裝完才發現對不上。9 把裡有 7 把受此影響；另 2 把（兩個 JSON trust profile）只做自洽檢查
（`key_fingerprint` 必須等於從 `public_key` 導出的值），不需要改 source。

重新釘 fingerprint **是正常的 provisioning 收尾，不是放寬 gate**：釘死公鑰指紋的目的是防止有人
事後換掉 trust root，而現在釘的是佔位值。但改動必須在 PR 說明裡明講「以 operator 實際產生的
公鑰取代未經驗證的佔位常數」，並附 7 個新 fingerprint。

## 3. Phase A — 9 把 keypair（現在可做）

### A0 先讓 operator 決定 private key custody（決定點，不要替他決定）

7 個 recovery 能力＋2 個簽章身分各自一把獨立 ed25519 私鑰。這些私鑰**目前沒有消費者**
（`attest-v2` 等能力尚未實作），所以要先講明：現在產＝先有一批暫時沒人用的私鑰。
請 operator 明確指定存放位置與保護方式（例如 trade-core 上 root-only 目錄、或離線保管），
並把決定寫進本 session 的收尾報告（只記位置與保護方式，不記內容）。
若 operator 選擇延後，合法做法是**只做 A1 的兩個 JSON profile**，7 把 .pub 等能力實作時再產。

### A1 產生（operator 執行，逐把）

九個目標，identity／namespace 全部由 source 固定，不可自選：

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

> **Tier 1 落地後更新(2026-08-02)**:原本是 9 把,現在是 **10 把** —— 外部 WORM provider trust
> root 被換成 host 側 durability anchor trust root(第 10 列)。三個 JSON profile 的
> `attestor_class` 現為 `S2E_RECEIPT_SIGNER_V1`／`HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1`／
> `HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1`;正本在
> `program_code/ml_training/aiml_gate_receipt_s2e_external_evidence.py` 的
> `_load_*_trust_root()`,務必逐欄從 source 讀。

**你要做的**：逐一從 source 讀出上表「見 source」的實際字串填滿，不要抄本表的省略欄。
產生一律 `ssh-keygen -t ed25519`，每把獨立、無 passphrase 與否由 operator 決定，
私鑰路徑由 A0 的決定給定。

### A2 回報（operator 貼給你）

9 個 public key（`ssh-ed25519 AAAA…` 一行）與對應
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
- **2 個 JSON profile**（`_read_trust_root`，`aiml_gate_receipt_s2e_external_evidence.py:94-183`）：
  owner uid **必須是 0**、mode **必須剛好 `0644`**、非 symlink、`st_nlink == 1`、≤16 KB、
  UTF-8 嚴格 JSON 且**不得有重複 key**，欄位集合必須**完全等於**這 9 個（多一個少一個都失敗）：
  `schema_version`、`signer_identity`、`signature_namespace`、`algorithm`、`key_generation`、
  `anchor`、`public_key`、`key_fingerprint`、`attestor_class`。
  固定值：`algorithm="SSH-ED25519"`、`key_generation="independent_off_repo_ed25519_v1"`、
  `anchor="fixed_off_repo_public_trust_root_v1"`；`key_fingerprint` 必須等於由 `public_key` 導出的值。
  predecessor registry 的 `schema_version="s2e_predecessor_registry_trust_root_v1"`、
  `attestor_class="EXTERNAL_APPEND_ONLY_PREDECESSOR_REGISTRY_V1"`；receipt signer 的
  `schema_version="s2e_receipt_signer_trust_root_v1"`，其欄位集合另見
  `aiml_gate_receipt_s2e_launch.py:340-360`（含 `governed_pytest_provider_profile_id`，與上表不同，
  **必須逐欄從 source 讀，不要套用 registry 的欄位表**）。

指令給 operator 時一律**單行**，一次一個檔，不要串成一大段。

### A5 驗收（你做，read-only）

透過 `ssh trade-core` 逐檔驗：`stat` 出 uid/mode/nlink、`file` 確認非 symlink、
`ssh-keygen -lf` 比對 fingerprint 與 A3 釘入的常數是否逐字相同、JSON 以 `python3 -c` 嚴格解析並
比對欄位集合。**任何一項不符就明講不符，不要四捨五入成通過。**

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
A0 custody 決定（只記位置與保護方式）、9 項逐檔實測狀態、A3 的 PR 連結與 7 個新 fingerprint、
未完成項與原因、以及明確聲明本 session 沒有 production effect。

**誠實邊界**：Phase A 全綠也**不代表** LW1 exit。它只把 14 項 blocker 降到剩
`attest-v2` 能力（未實作）＋ Phase B 兩項。W0 genesis 與 LW1 receipt 仍未發、LW2 仍 locked、
S2 仍未關閉。不要在任何報告裡把 Phase A 完成寫成 wave 前進。
