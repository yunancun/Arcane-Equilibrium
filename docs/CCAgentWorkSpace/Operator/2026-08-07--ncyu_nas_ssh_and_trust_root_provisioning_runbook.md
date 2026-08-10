# ncyu-nas SSH listener ＋ 11 個信任根 provisioning runbook

- 日期：2026-08-07
- 承接：`docs/CCAgentWorkSpace/Operator/2026-08-02--s2e_lw1_tier1_provisioning_session_prompt.md`
- 規格來源：本檔所有 identity／namespace／欄位集合／固定值**逐欄從 source 讀出**（見 §9 引用行號），
  不是抄 2026-08-02 prompt 的表。兩處與該 prompt 不同的地方在 §9 具名列出。
- 效果上限：本輪的 repo 效果只有「改 7 個 fingerprint 常數（走 PR）」。所有 `/etc` 與 DSM 寫入由
  operator 自己執行。production effect 0/6 不變。

---

## 0. 本輪實測事實（2026-08-07，Mac 本地；`LOCAL_REPRODUCIBLE`）

| 事實 | 值 | 取得方式 |
|---|---|---|
| `ncyu-nas` 機型 | Synology **DS1621xs**（DSM） | `curl -I http://100.77.15.17:5000/` → `Server: DS1621xs` |
| 開放埠 | 80／443／5000／5001 通；22 於 **2026-08-07 由 operator 在 DSM 開啟**（先前無 listener） | `nc -z` → succeeded；`SSH-2.0-OpenSSH_8.2` |
| **ncyu-nas ED25519 host fp** | **`SHA256:wGVNyQWkhVCDvTBf6+Yx4TRXfN1Ow0Q/8NUZ7kdAS8U`** ← 第 11 個信任根的 `host_fingerprint` | Mac 端 `ssh-keyscan -t ed25519 100.77.15.17` |
| ncyu-nas ECDSA / RSA host fp | `SHA256:Xh/ZEX/V8QK/TqT6NIJA0krWuY3pE3IF/saFQ8DjbA4` ／ `SHA256:NsclkaC+E3eoPSdXx+AwFUnvxLxrxaRn3abpQw1D2j0` | 同上 |
| trade-core ED25519 host fp | `SHA256:HZoyVB/cI+eKXX0Vx+U7NlZ1axni5QUydNMJX4Yli9E` | Mac 端 `ssh-keyscan -t ed25519 trade-core`，與 `known_hosts` 既有紀錄一致 |
| trade-core ECDSA / RSA host fp | `SHA256:ON/nfwEw5D4a+fP7CFnYGq/a5QdGRxpTtUC1fEhxQRE` ／ `SHA256:2kP/8YFG2J38IMoh3ud7YkdQhyGk2tR2p2b3BiFWdgU` | 同上 |
| governed pytest lock digest | `sha256:9dd3f850d58cb13242decda314e81add25e68f652311094704bc44106a64fcd3` | `git show HEAD:.codex/providers/governed_pytest_v1/lock.json \| shasum -a 256`；該檔全史只有 1 次 commit（`b34fa9eb5`），值穩定 |
| 佔位 fingerprint 常數 | 共 **7 個**：6 個在 `agent_governance_s2_5_recovery.py:81,87,93,100,106,112`，第 7 個在 `aiml_gate_receipt_s2_5_host_capture.py:55` | 全 repo grep，`tests/` 外無其他 pin 點 |

**「開 SSH」的正確做法因此是 DSM Control Panel 的服務開關，不是改 `/etc/ssh/sshd_config`。**

### 0.1 一個會擋到 A5 的實測缺口（需要你決定怎麼補）

本 session 的 Mac →`trade-core` SSH **不通**：

```
debug1: Offering public key: /Users/ncyu/.ssh/id_ed25519 ED25519 SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ
ncyu@trade-core: Permission denied (publickey).
```

順帶一提：該指紋恰等於 `agent_governance_aiml_trusted_host.py:78` 的
`EXPECTED_EXECUTION_SIGNER_FINGERPRINT`（governed capture 的執行簽章身分）。

> **2026-08-08 更正並關閉。** 本節原本斷定「該公鑰未被 trade-core 授權」。**那個診斷是錯的。**
> 真因是 `~/.ssh/id_ed25519` 有 passphrase，而 `ssh-agent` 內無任何 identity，
> `BatchMode=yes` 不能提示 passphrase，於是同一個 `Permission denied (publickey)`
> 被誤讀成授權問題。證偽事實：operator 在互動 shell 用**同一把 key、同一個路徑**輸入
> passphrase 後即連線成功（四頭 probe 那次），代表該 key 一直都在 trade-core 的
> `authorized_keys` 內。
>
> 解法是 `ssh-add --apple-use-keychain ~/.ssh/id_ed25519`（comment 顯示為
> `trade-core-admin`），執行後 PM 的非互動 ssh 立即可用。
>
> **教訓**：`Permission denied (publickey)` 在 `BatchMode` 下同時涵蓋「金鑰未授權」與
> 「金鑰無法解鎖」兩種完全不同的成因，不可只憑該訊息斷定是前者；先看 `ssh-add -l`。

因此 §7 的 A5 已由 PM 自行執行（見 §7.1），不再是 operator 自報。

### 0.2 一個必須先講的既有問題（承 prompt §2）

7 個 `RECOVERY_*_TRUST_ROOT_FINGERPRINT` 是 2026-07-30 `f17a8a819` 寫死的**佔位值**，對應公鑰在
repo 內外都不存在，且測試一律 `monkeypatch` 掉它們，所以**從未對真實金鑰驗過**。
你新產的金鑰指紋一定對不上。因此順序必須是
**產金鑰 → 回報公鑰 → 改 source 重新釘（PR）→ 安裝 → 驗收**，不能先裝完才發現對不上。

重新釘**不是放寬 gate**：釘死指紋是為了防止事後換掉 trust root，而現在釘的是佔位值。

---

## 1. Step 1 — 在 DSM 開 SSH（你做，我不代做）

這是主機的安全設定變更，由你在 DSM 執行。

1. 瀏覽器開 `https://100.77.15.17:5001/`（或 `http://100.77.15.17:5000/`），
   以 **administrators 群組**的帳號登入。
2. **Control Panel → Terminal & SNMP → Terminal** 分頁 → 勾選 **Enable SSH service**，
   Port 保持 **22**（`ssh-keyscan` 與 TODO 的 `ncyu-nas:22` 都假設 22）→ **Apply**。
3. DSM 7 的 root 直接登入是停用的：用 administrators 帳號登入後 `sudo -i` 取得 root。
4. **Control Panel → Security → Protection** 的 **Auto Block 維持開啟**，不要為了方便關掉。

### 1.1 建議的收斂（不是必要，但強烈建議）

DSM 的 SSH 開關沒有「只綁某個介面」的選項，勾下去等於 22 對**所有**介面開。建議：

- **Control Panel → Security → Firewall**：若防火牆已啟用，為 TCP 22 加一條
  **來源限 `100.64.0.0/10`**（tailnet 的 CGNAT 段）的 allow，其餘 deny。
  Mac（100.77.153.53）與 trade-core（100.91.109.86）都在此段內，本 runbook 全部步驟不受影響。
- **注意一個我無法從外部確認的點**：DSM 防火牆規則是綁網路介面的，若它的 profile 沒列出
  `tailscale` 介面，這條規則對 tailnet 流量可能不生效。若是這種情況，退而確認：
  路由器**沒有**把 22 轉發到 NAS，且 Auto Block 開著。請你在 UI 裡實際看一眼再回報。

### 1.2 為什麼不用 Tailscale SSH 取代

Tailscale SSH 不提供傳統的 `/etc/ssh/ssh_host_*` host key，`ssh-keyscan` 取不到穩定指紋。
而本任務第 11 個信任根的 `host_fingerprint` **必須**是可從 Mac 端 `ssh-keyscan` 逐字核對的
真實 SSH host key 指紋（§6.4）。所以這裡要的是 DSM 真正的 sshd。

---

## 2. Step 2 — 我驗收 listener 並取 NAS host fingerprint（read-only，我做）

你 Apply 後告訴我，我從 Mac 跑：

```bash
ssh-keyscan -T 8 -t ed25519 100.77.15.17 | ssh-keygen -lf -
```

取得的 ED25519 指紋就是第 11 個信任根要填的 `host_fingerprint`。
**這一步必須在 Mac 上做，不能在 trade-core 或 NAS 上取**：被檢查的機器不能產出自己的檢查證據。

---

## 3. Step 3 — 私鑰 custody（你已裁決 2026-08-07）

- trade-core 側 10 把：`/etc/arcane-equilibrium/private/`，目錄 `0700 root:root`，
  每把私鑰 `0600 root:root`，**無 passphrase**。
  理由（你的裁決）：未來的消費者是 root-owned producer（`attest-v2`／anchor／registry），
  必須能無人值守簽章；passphrase 會把成本推遲到那三支能力實作時。
- 第 11 把（off-host replica readback）：**在 `ncyu-nas` 上 `ssh-keygen`，永不離開該機**，
  trade-core 的 root 不得持有。這是 2026-08-03 的硬邊界，不是建議——若兩把私鑰都在 trade-core，
  持 root 者同時是 anchor writer 與自己副本的唯一證人，§LW1 的 rollback／coherent-rewrite 論證就仍被違反。
  **代碼證不了私鑰在哪台機器**，它只能執法「兩個指紋不等」；其餘由這條 provisioning 事實承擔。

> **殘留風險（具名）**：持有 trade-core root 者即持有那 10 把私鑰。2-of-2 的支點只有第 11 把。

---

## 4. Step 4 — 產生 11 把 keypair（你執行）

### 4.1 trade-core 建目錄（3 行）

```bash
sudo install -d -m 0700 -o root -g root /etc/arcane-equilibrium/private
```

```bash
sudo install -d -m 0755 -o root -g root /etc/arcane-equilibrium/trust
```

```bash
sudo install -d -m 0755 -o root -g root /etc/arcane-equilibrium/aiml
```

### 4.2 trade-core 產 10 把（每行一把）

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2-5-recovery-operator-v1 -f /etc/arcane-equilibrium/private/s2-5-recovery-authorization
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2-5-recovery-anchor-owner-v1 -f /etc/arcane-equilibrium/private/s2-5-recovery-anchor
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2-5-recovery-anchor-readback-verifier-v1 -f /etc/arcane-equilibrium/private/s2-5-recovery-anchor-readback
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2-5-recovery-consumption-ledger-v1 -f /etc/arcane-equilibrium/private/s2-5-recovery-consumption
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2-5-recovery-actor-attestor-v1 -f /etc/arcane-equilibrium/private/s2-5-recovery-actor-capture
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2-5-recovery-independent-verifier-v1 -f /etc/arcane-equilibrium/private/s2-5-recovery-verifier-capture
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2-5-recovery-host-capture-attestor-v1 -f /etc/arcane-equilibrium/private/s2-5-recovery-host-capture
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2e-receipt-signer-v1 -f /etc/arcane-equilibrium/private/s2e-receipt-signer
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2e-predecessor-registry-attestor-v1 -f /etc/arcane-equilibrium/private/s2e-predecessor-registry
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2e-durability-anchor-attestor-v1 -f /etc/arcane-equilibrium/private/s2e-durability-anchor
```

### 4.3 ncyu-nas 產第 11 把（SSH 開通後，在 NAS 上執行）

存放位置必須是**專用共享資料夾內**的 root-only 子目錄。

> **2026-08-07 更正**：本節原本建議 `/volume1/arcane-equilibrium/private`（刻意放在共享資料夾
> *之外*，理由是不被 SMB／AFP 匯出）。**那是錯的**——NAS 的 SSH 登入橫幅明說
> `Data should only be stored in shared folders. Data stored elsewhere may be deleted when the
> system is updated/restarted.` 第 11 把私鑰依硬邊界永不離開該機，被 DSM 更新刪掉等於
> 2-of-2 支點要整個重做。改用共享資料夾，匯出風險改由「權限全部設為無存取」＋
> root-only `0700` 子目錄承擔。

實測 volume：`/volume1`、`/volume2` 皆存在（2026-08-07）。以下以 volume1 為例。

DSM 建立共享資料夾（**控制台 → 共享文件夹 → 新增**）：

- 名稱 `arcane-equilibrium`，位置 volume1
- 勾「隱藏網上鄰居中的此共享資料夾」
- **不要勾加密**：加密的共享資料夾重開機後不會自動掛載，未來 root-owned producer 的
  無人值守簽章會直接卡死
- 權限設定：**所有使用者都設為「無存取權限」**（含 `yunancun`）

```bash
sudo install -d -m 0700 -o root -g root /volume1/arcane-equilibrium/private
```

```bash
sudo ssh-keygen -q -t ed25519 -N '' -C aiml-s2e-offhost-replica-attestor-v1 -f /volume1/arcane-equilibrium/private/s2e-offhost-replica
```

### 4.4 安裝 7 個 `.pub`（trade-core，每行一個）

```bash
sudo install -m 0644 -o root -g root /etc/arcane-equilibrium/private/s2-5-recovery-authorization.pub /etc/arcane-equilibrium/trust/s2-5-recovery-authorization.pub
```

```bash
sudo install -m 0644 -o root -g root /etc/arcane-equilibrium/private/s2-5-recovery-anchor.pub /etc/arcane-equilibrium/trust/s2-5-recovery-anchor.pub
```

```bash
sudo install -m 0644 -o root -g root /etc/arcane-equilibrium/private/s2-5-recovery-anchor-readback.pub /etc/arcane-equilibrium/trust/s2-5-recovery-anchor-readback.pub
```

```bash
sudo install -m 0644 -o root -g root /etc/arcane-equilibrium/private/s2-5-recovery-consumption.pub /etc/arcane-equilibrium/trust/s2-5-recovery-consumption.pub
```

```bash
sudo install -m 0644 -o root -g root /etc/arcane-equilibrium/private/s2-5-recovery-actor-capture.pub /etc/arcane-equilibrium/trust/s2-5-recovery-actor-capture.pub
```

```bash
sudo install -m 0644 -o root -g root /etc/arcane-equilibrium/private/s2-5-recovery-verifier-capture.pub /etc/arcane-equilibrium/trust/s2-5-recovery-verifier-capture.pub
```

```bash
sudo install -m 0644 -o root -g root /etc/arcane-equilibrium/private/s2-5-recovery-host-capture.pub /etc/arcane-equilibrium/trust/s2-5-recovery-host-capture.pub
```

四個 JSON 先**不要**建立——要等我在 §6 產生逐位元組正確的內容。

---

## 5. Step 5 — A2 回報（你貼給我，公開資訊）

11 個公鑰與指紋。trade-core 側一行取得全部：

```bash
sudo sh -c 'for f in /etc/arcane-equilibrium/private/*.pub; do echo "== $f"; cat "$f"; ssh-keygen -lf "$f"; done'
```

NAS 側：

```bash
sudo sh -c 'f=/volume1/arcane-equilibrium/private/s2e-offhost-replica.pub; cat "$f"; ssh-keygen -lf "$f"'
```

**私鑰絕不貼**。公鑰與指紋不是機密。

---

## 6. Step 6 — 我做的兩件事

### 6.1 A3 source PR（重新釘 7 個 fingerprint）

改 7 個常數為 A2 的真值，**不改任何驗證邏輯**，既有 monkeypatch 測試維持原樣：

| # | 檔案:行 | 常數 |
|---|---|---|
| 1 | `helper_scripts/maintenance_scripts/agent_governance_s2_5_recovery.py:81` | `RECOVERY_AUTHORIZATION_TRUST_ROOT_FINGERPRINT` |
| 2 | 同上 `:87` | `RECOVERY_ANCHOR_TRUST_ROOT_FINGERPRINT` |
| 3 | 同上 `:93` | `RECOVERY_ANCHOR_READBACK_TRUST_ROOT_FINGERPRINT` |
| 4 | 同上 `:100` | `RECOVERY_CONSUMPTION_TRUST_ROOT_FINGERPRINT` |
| 5 | 同上 `:106` | `RECOVERY_ACTOR_CAPTURE_TRUST_ROOT_FINGERPRINT` |
| 6 | 同上 `:112` | `RECOVERY_VERIFIER_CAPTURE_TRUST_ROOT_FINGERPRINT` |
| 7 | `program_code/ml_training/aiml_gate_receipt_s2_5_host_capture.py:55` | `RECOVERY_HOST_CAPTURE_TRUST_ROOT_FINGERPRINT` |

（2026-08-02 prompt 說「7 個在 `agent_governance_s2_5_recovery.py`」，實測是 6＋1 兩個檔。）

### 6.2 產生 4 個 JSON 的逐位元組內容

我在 Mac scratchpad 產生，你 `scp` 過去再 `install`。**你不要手打指紋**——`key_fingerprint`
必須逐字等於由 `public_key` 導出的值，手打是這批佔位常數當初的出錯方式。

```bash
scp <我給的檔> trade-core:/tmp/
```

```bash
sudo install -m 0644 -o root -g root /tmp/s2e-receipt-trust-root-v1.json /etc/arcane-equilibrium/aiml/s2e-receipt-trust-root-v1.json
```

（其餘三個同形，路徑見 §6.3 表。）

### 6.3 11 個目標的完整規格（逐欄從 source 讀出）

| # | 安裝路徑 | signer_identity | signature_namespace | 私鑰產生於 |
|---|---|---|---|---|
| 1 | `/etc/arcane-equilibrium/trust/s2-5-recovery-authorization.pub` | `aiml-s2-5-recovery-operator-v1` | `arcane-equilibrium-aiml-s2-5-recovery` | trade-core |
| 2 | `…/trust/s2-5-recovery-anchor.pub` | `aiml-s2-5-recovery-anchor-owner-v1` | `arcane-equilibrium-aiml-s2-5-recovery-anchor` | trade-core |
| 3 | `…/trust/s2-5-recovery-anchor-readback.pub` | `aiml-s2-5-recovery-anchor-readback-verifier-v1` | `arcane-equilibrium-aiml-s2-5-recovery-anchor-readback` | trade-core |
| 4 | `…/trust/s2-5-recovery-consumption.pub` | `aiml-s2-5-recovery-consumption-ledger-v1` | `arcane-equilibrium-aiml-s2-5-recovery-consumption` | trade-core |
| 5 | `…/trust/s2-5-recovery-actor-capture.pub` | `aiml-s2-5-recovery-actor-attestor-v1` | `arcane-equilibrium-aiml-s2-5-recovery-actor-capture` | trade-core |
| 6 | `…/trust/s2-5-recovery-verifier-capture.pub` | `aiml-s2-5-recovery-independent-verifier-v1` | `arcane-equilibrium-aiml-s2-5-recovery-verifier-capture` | trade-core |
| 7 | `…/trust/s2-5-recovery-host-capture.pub` | `aiml-s2-5-recovery-host-capture-attestor-v1` | `arcane-equilibrium-aiml-s2-5-recovery-host-capture` | trade-core |
| 8 | `…/aiml/s2e-receipt-trust-root-v1.json` | `aiml-s2e-receipt-signer-v1` | `arcane-equilibrium-aiml-s2e-receipts` | trade-core |
| 9 | `…/aiml/s2e-predecessor-registry-trust-root-v1.json` | `aiml-s2e-predecessor-registry-attestor-v1` | `arcane-equilibrium-aiml-s2e-predecessor-registry` | trade-core |
| 10 | `…/aiml/s2e-durability-anchor-trust-root-v1.json` | `aiml-s2e-durability-anchor-attestor-v1` | `arcane-equilibrium-aiml-s2e-durability-anchor` | trade-core |
| 11 | `…/aiml/s2e-offhost-replica-trust-root-v1.json` | `aiml-s2e-offhost-replica-attestor-v1` | `arcane-equilibrium-aiml-s2e-offhost-replica` | **ncyu-nas** |

### 6.4 四個 JSON 的欄位集合（**四份互不相同**，多一欄少一欄都 fail closed）

共同固定值：`algorithm="SSH-ED25519"`、`key_generation="independent_off_repo_ed25519_v1"`、
`anchor="fixed_off_repo_public_trust_root_v1"`；`key_fingerprint` 必須等於由 `public_key` 導出的值。

| # | 欄位數 | 欄位集合 | `schema_version` | `attestor_class` |
|---|---|---|---|---|
| 8 receipt signer | **10** | 基礎 9 欄**去掉 `attestor_class`**，加 `governed_pytest_provider_profile_id`、`governed_pytest_provider_lock_sha256` | `s2e_receipt_signer_trust_root_v1` | **無此欄** |
| 9 predecessor registry | **9** | 基礎 9 欄 | `s2e_predecessor_registry_trust_root_v1` | `HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1` |
| 10 durability anchor | **10** | 基礎 9 欄 ＋ `host_fingerprint` | `s2e_durability_anchor_trust_root_v1` | `HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1` |
| 11 off-host replica | **10** | 基礎 9 欄 ＋ `host_fingerprint` | `s2e_offhost_replica_trust_root_v1` | `OFFHOST_APPEND_ONLY_REPLICA_READBACK_V1` |

基礎 9 欄（`_TRUST_ROOT_FIELDS`）：`schema_version`、`signer_identity`、`signature_namespace`、
`algorithm`、`key_generation`、`anchor`、`public_key`、`key_fingerprint`、`attestor_class`。

#8 另兩欄的值：`governed_pytest_provider_profile_id="code_owned_git_wheels_no_site_v1"`、
`governed_pytest_provider_lock_sha256="sha256:9dd3f850d58cb13242decda314e81add25e68f652311094704bc44106a64fcd3"`。

`host_fingerprint` 兩欄（**2026-08-07 已實測定值**，均由 Mac 端 `ssh-keyscan` 取得，非在被檢查的機器上算）：

- #10 durability anchor ＝ trade-core ED25519 `SHA256:HZoyVB/cI+eKXX0Vx+U7NlZ1axni5QUydNMJX4Yli9E`
- #11 off-host replica ＝ ncyu-nas ED25519 `SHA256:wGVNyQWkhVCDvTBf6+Yx4TRXfN1Ow0Q/8NUZ7kdAS8U`

已驗：形制符合 `_SSH_FINGERPRINT_PATTERN`；兩者不等（驗證端逐字比對）；
#11 不落在 trade-core 的 host key 集合內（`aiml_gate_receipt_s2e_external_evidence.py:648`）——
以 keyscan 可見的 ed25519／ecdsa／rsa 三把逐一比對。
**殘留**：keyscan 只看得到 sshd 實際提供的 key，若 trade-core 的 `/etc/ssh` 另有未提供的
`ssh_host_*.pub`，它會落在驗證端的 local 集合卻不在本次比對範圍內；等 §0.1 的 SSH 存取解決後
以 `ls /etc/ssh/ssh_host_*.pub` 補一次完整比對。

#### 三個容易踩的形制陷阱

1. **JSON 的 `public_key` 不能帶 comment。** `ssh_public_key_fingerprint()` 以第一個空白切兩段，
   且第二段內**不得再有空白**；`ssh-keygen` 產出的 `.pub` 尾端有 `-C` 註解，必須只取前兩欄。
   （7 個 `.pub` 檔則相反：`_read_fixed_recovery_public_key` 取 `parts[:2]`，帶註解無妨。）
2. **四個 JSON 的 mode 必須剛好 `0644`、owner uid 必須是 0**（`!=` 判定，不是位元遮罩），
   `st_nlink == 1`、非 symlink、≤16 KB、UTF-8 嚴格 JSON 且不得有重複 key。
3. **7 個 `.pub` 的條件不同**：regular file、`st_nlink == 1`、非 symlink、
   owner uid ∈ {0, 執行者}、`mode & 0o022 == 0`（不得 group/world writable）、
   size 16–4096 bytes、純 ASCII、首欄必須是 `ssh-ed25519`。

---

## 7. Step 7 — A5 驗收（read-only；受 §0.1 限制）

```bash
sudo sh -c 'for f in /etc/arcane-equilibrium/trust/*.pub; do stat -c "%n uid=%u mode=%a nlink=%h size=%s" "$f"; ssh-keygen -lf "$f"; done'
```

```bash
sudo sh -c 'for f in /etc/arcane-equilibrium/aiml/*.json; do stat -c "%n uid=%u mode=%a nlink=%h size=%s" "$f"; python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(sorted(d))" "$f"; done'
```

逐項比對：`.pub` 指紋 vs §6.1 釘入的常數；JSON 欄位集合 vs §6.4 的表。
**任何一項不符就明講不符，不四捨五入成通過。**

### 7.1 A5 執行結果（2026-08-08，**全項 PASS**）

**證據等級：`LOCAL_REPRODUCIBLE`（PM 自行執行的 read-only 遠端讀取）。**
PM 以 `ssh trade-core` 直接讀回全部 11 個檔的 `stat`／`sha256sum`／`ssh-keygen -lf`
與 `/etc/ssh/ssh_host_*.pub`，再以 repo 常數與本地產出位元組機器比對，15/15 PASS。
無需 `sudo`：`trust/` 為 0755、四個 JSON 為 0644，全部 world-readable；
`private/`（0700）未被讀取，本節不觸及任何私鑰。

> **本節先前記為 `operator-reported` 並已於同日更正。** 首輪由 operator 執行並貼回，
> 因為當時誤判 PM 無 SSH 存取（見 §0.1 的更正）。`ssh-add` 之後 PM 重跑同一組檢查，
> 逐值與 operator 首輪回報**完全一致**——即該次自報本身是準確的，改變的只有證據等級。
> 仍**不是** `PLATFORM_OR_EXTERNAL_ATTESTED`：PM 自跑的遠端讀取仍非平台證明。

| 檢查 | 結果 |
|---|---|
| 11 檔皆 `regular file`、`st_nlink == 1`（非 symlink） | PASS |
| 7 個 `.pub`：uid=0、mode 644（`& 0o022 == 0`）、size 112–128 ∈ [16,4096] | PASS |
| 4 個 JSON：uid **剛好** 0、mode **剛好** 0644、size 583–680 ≤ 16 KB | PASS |
| 7 個 `.pub` 指紋 vs §6.1 釘入常數（檔名集合亦 7/7 無多無缺） | PASS |
| 4 個 JSON sha256 vs PM 產出位元組 | PASS |
| anchor host fp 確為 trade-core 本機 key | PASS |
| replica host fp **不在** trade-core 本機 host key 集合內 | PASS |
| 兩個 host fp 不等 | PASS |

四個 JSON 的基準 digest：

```
63c88036d3def7b8db2ea609cce8984ca14da06b915d823311850f8eacaf764b  s2e-durability-anchor-trust-root-v1.json
f15b4a426fcc29953d307a5e1f7399a4f579db761c7aff47234de18b1916f1d3  s2e-offhost-replica-trust-root-v1.json
7a16fbd087cd62638937f40b40e5c942b99b4de3542fb8715d9bc0a5a3b0407d  s2e-predecessor-registry-trust-root-v1.json
b4a382ab6d3caeb83ae1e3068d694290434cf5492f02c823c86e76800015bfd3  s2e-receipt-trust-root-v1.json
```

**§6.4 的 keyscan 殘留已關閉**：`/etc/ssh/ssh_host_*.pub` 實測恰為 ECDSA／ED25519／RSA 三把，
與 Mac 端 keyscan 所見完全一致，沒有「sshd 未提供但存在於本機集合」的第四把。

### 7.2 A3 回歸測試

`tests/structure/` 的 `-k "s2_5 or s2e"`：**816 passed / 0 failed / 0 skipped / 0 error**
（4702 deselected，14m33s，exit 0）。焦點兩檔另跑 109 passed。
**證據等級 `LOCAL_REPRODUCIBLE`（Mac 本地），非 closure-admissible 強 PASS。**

### 7.3 發布與三端 source sync（2026-08-08）

PR [#181](https://github.com/yunancun/Arcane-Equilibrium/pull/181) 以 `--merge`
（非 squash/rebase）＋`--match-head-commit d8cb6a79b…` 合入，merge commit
`2f9b6cde45e43a7cda8bfe0a57ddb6bd2faea064`。CI 10 passed / 0 failed，未解 review thread 0。

`.codex/SYNC.md` §5／§6 之後三個 git head 全等，且**皆由 PM 直接讀取**：

| 側 | HEAD |
|---|---|
| Mac canonical `/Users/ncyu/Projects/TradeBot/srv` | `2f9b6cde4…`（`main-post-sync` guard PASS，dirty 0） |
| 真 `origin/main`（`git ls-remote`） | `2f9b6cde4…` |
| Linux `/home/ncyu/BybitOpenClaw/srv` | `2f9b6cde4…`（branch `main`，dirty 0） |

**具名偏差**：§1–§3 的 `git_loop_guard.py` `start`／`checkpoint`／`publish`／`post-push`
四個 phase 未執行，writer lease 未 acquire。§4 的 exact-head merge 有合規執行。
這是被跳過的步驟，不是通過的步驟。

**四頭 probe 判 `INDETERMINATE`**，原因是第四頭讀不到而非 git 不同步：
`four_head_reconcile_probe.py:447` 在 `engine_full is None` 時直接短路回傳，
**走不到** `:459` 的三 git 頭相等判斷。附帶指出 §7 分類表的缺口：
`SOURCE_ONLY_DRIFT` 與 `HALF_DEPLOY_REBUILD_REQUIRED` 都預設 engine build SHA 可讀，
「引擎根本沒部署」沒有對應類別。

### 7.4 sync 期間發現的 runtime 事實（未處理，非本輪範圍）

trade-core 上（2026-08-08 PM 實測，read-only）：

| 項目 | 觀測 |
|---|---|
| `openclaw_engine` 進程 | 無 |
| systemd unit | 完全沒有——engine 由 `restart_all.sh` 起為普通進程，非 systemd 管理，故此項為預期 |
| `openclaw_engine` binary | `find /home/ncyu/BybitOpenClaw -name openclaw_engine` 無結果，未建置 |
| `var/openclaw/engine.log` mtime | **2026-07-18 03:23** |
| FastAPI control plane | 運行中，`100.91.109.86:8000`，4 workers |
| `helper_scripts/canary/engine_watchdog.py` | 運行中約 22 天，`--stale-threshold 45` |

即控制面與 watchdog 都活著，但 Rust 引擎自 2026-07-18 起未運行且 binary 未建置；
watchdog 22 天未使該狀態成為可見告警。考量此期間為 source-only 階段
（production effect 0/6、runtime 全程標 dormant），引擎停置**可能**是預期的——
本檔不對此下判斷。rebuild／restart 屬獨立授權 effect，本輪未執行亦未提議執行。

---

## 8. 誠實邊界

- 本 runbook 全部完成也**不等於 LW1 exit**。它把 16 項前置降到剩：`attest-v2`、durability anchor、
  predecessor registry **三支 root-owned producer 未實作**，＋ Phase B 的 NAS append-only 複寫路徑。
- W0 genesis 與 LW1 receipt 仍發不出；LW2 仍 locked；S2 未關閉；九項 authority 全 false；
  production effect 0/6。**不要在任何報告裡把本輪完成寫成 wave 前進。**
- 那三支 producer 另有一個尚未解的設計前置：驗證面若以 root 讀 `ncyu` 所有的工作樹，
  git 會 `dubious ownership` 而整條 floor 永久 REJECTED，且**差異 uid 拓撲目前沒有受支援的放行路徑**
  （`safe.directory` 出口已於 PR #178 review 判定不成立且不予重開）。真解在設計層：
  驗證面改從 code-owned 的 bare view 取事實。
- **具名長期風險**：`s2e-offhost-replica-trust-root-v1.json` 的 `host_fingerprint` 釘死 NAS 的
  SSH host key。DSM 重大升級／重置若重建 host key，該信任根即失效並 fail closed；
  修法是重新 provisioning 那一個檔，不是放寬比對。

---

## 9. Source 引用（本檔每個值的出處）

| 內容 | 出處 |
|---|---|
| #1–#6 identity／namespace／路徑／佔位指紋 | `helper_scripts/maintenance_scripts/agent_governance_s2_5_recovery.py:45-113` |
| #7 同上 | `program_code/ml_training/aiml_gate_receipt_s2_5_host_capture.py:45-56` |
| `.pub` 檔案硬性條件 | 同檔家族的 `_read_fixed_recovery_public_key`，`agent_governance_s2_5_recovery.py:300-327` |
| #8 欄位集合與期望值 | `program_code/ml_training/aiml_gate_receipt_s2e_launch.py:58-76, 307-340` |
| #9–#11 identity／namespace／路徑／`attestor_class`／`schema_version` | `program_code/ml_training/aiml_gate_receipt_s2e_external_evidence.py:24-63, 299-334` |
| JSON 共同欄位／固定值／檔案條件 | 同檔 `:64-79, 199-296` |
| `host_fingerprint` 形制與 local-host 排除 | 同檔 `:80, 124-169, 638-648, 772-779` |
| 指紋導出演算法 | `helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py:169-181` |
| governed pytest provider profile／lock path | `helper_scripts/maintenance_scripts/agent_governance_pytest_provider.py:6-9`；digest 計算 `agent_governance_command_capture_v2.py:492-495` |

### 與 2026-08-02 prompt 的兩處差異（具名）

1. prompt §A3 稱 7 個 fingerprint 常數都在 `agent_governance_s2_5_recovery.py`；
   實測是該檔 6 個 ＋ `aiml_gate_receipt_s2_5_host_capture.py` 1 個。
2. prompt §A4 對 #8 receipt signer 只說「欄位集合另見 launch.py」；本檔補明它
   **沒有 `attestor_class` 欄**——照基礎 9 欄寫會直接吃到 `fields are not exact`。
