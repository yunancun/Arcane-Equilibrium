# PA 技術設計 — IBKR P1 fingerprint-only SecretSlotLoader

- 日期：2026-07-09
- 角色：PA（design-only，不寫實現體）
- 授權來源：`docs/governance_dev/amendments/2026-07-08--AMD-2026-07-08-01-ibkr-phase2-external-contact-readonly.md`（Accepted）；母決策 ADR-0048
- 消費既有型別（不新造）：`rust/openclaw_types/src/ibkr_phase2_runtime.rs :: IbkrSecretSlotContractV1`
- 落點 crate：`openclaw_engine`（**絕不** `openclaw_types`，net-free guard）
- 狀態：DONE_WITH_CONCERNS（設計完整、E1 可照做；殘留 2 個需 E3/Operator 拍板的運行時開放問題 — 見 §12）
- 血緣：承 PA memory `2026-07-08 IBKR stock_etf real read-only backend 可行性設計`（型別權威 scaffold 已 90% 建好，缺產真值的 runtime）

---

## 0. 一句話裁決

P1 是一個**結構高度同構 P0 risk-policy loader** 的純載入器：`stat` `$OPENCLAW_SECRETS_DIR/external/ibkr/{readonly,paper,live}/` 三槽，只算兩個 sha256 指紋，產出一條可通過 `IbkrSecretSlotContractV1::validate()` 的 contract leg，**不接 matrix live-eval、不碰 IPC/Python/DB、live 槽保持 absent**。P0 已把「純 loader + env wrapper + OnceLock + denied fallback」四件套教科書化（`handlers/stock_etf.rs:408-468`），P1 照抄該模式即可，blast radius 極小（0 熱檔改動）。

明文零逃逸的論證**成立**（§2.3）；指紋算法能與其他腿對齊的**充要條件**是：把 fingerprint 計算抽成 engine 內單一 `pub(crate)` 純函數，P1 建、P5 復用（同一函數＝同一輸入＝同一輸出），而非各腿各自實現（§5）。

---

## 1. 路徑解析

### 1.1 兩件事必須分清（AMD Secret Boundary 的關鍵區分）

- **允許**：用 env var 定位 secrets **base dir**（全系統定位機制，與 bybit `authorization_path()` 同性質）。
- **禁止**：env var 作為**凭证材料**來源（AMD Invariant 6 + `env_var_credential_fallback_denied`）。

設計把這兩件事在代碼與型別層同時釘死：base-dir 解析走 env；contract 的 `env_var_credential_fallback_denied` 欄位**恒為常量 `true`**（不從任何輸入推導），loader 永不從任何 env var 讀 account id / credential 內容。

### 1.2 純 loader 收 base dir 參數（可測、繞全域）

```rust
// 純載入器：收 external/ibkr base dir（其下含 readonly/ paper/ live/ 子目錄）。
// 為什麼收 dir 而非讀 env：把「路徑解析」與「stat+hash+組裝」拆開，讓 tempdir
// 測試能確定性驗三槽 posture，繞過進程級 OnceLock 與 OPENCLAW_SECRETS_DIR 全域
// （避免與同 binary 其他 env-mutating 測試搶 env → order-fragile；drawdown_revoke 教訓）。
pub(crate) fn load_ibkr_secret_slot_contract_from_base(
    ibkr_base: &std::path::Path,
) -> Result<IbkrSecretSlotContractV1, String>;
```

- `ibkr_base` = `.../external/ibkr`；loader 內 `ibkr_base.join("readonly")` / `join("paper")` / `join("live")`。
- **要 stat 的兩槽**：`readonly`、`paper`。**要證明 absent 的槽**：`live`。

### 1.3 env-resolving wrapper（沿 live_authorization + drawdown_revoke fallback，跨平台）

```rust
// 解析 external/ibkr base，沿用 authorization_path() 同一 env/HOME 約定，
// 不硬編碼平台路徑（跨平台可攜；USERPROFILE fallback for Windows）。
fn resolve_ibkr_secrets_base() -> Option<std::path::PathBuf> {
    // 1) OPENCLAW_SECRETS_DIR 設定 → PathBuf::from(dir).join("external").join("ibkr")
    // 2) 否則 $HOME (or $USERPROFILE) / "BybitOpenClaw" / "secrets" / "external" / "ibkr"
}
```

- 與 AMD 字面 `$OPENCLAW_SECRETS_DIR/external/ibkr/...` 一致。
- **注意（open question，見 §12-Q1）**：bybit `authorization_path()` 把 `OPENCLAW_SECRETS_DIR` 當作 `secret_files/bybit` 根直接用；AMD 對 IBKR 是 `OPENCLAW_SECRETS_DIR/external/ibkr`（當作 secrets 根）。兩者對「`OPENCLAW_SECRETS_DIR` 指向哪」的假設不同。loader **按 AMD 字面**解析；E3/Operator 必須確認 trade-core 上 `OPENCLAW_SECRETS_DIR` 實值，使「loader 解析路徑 == E3 建槽路徑」，否則 loader 永遠在錯目錄找到「全 absent」（fail-closed 安全，但功能失效，且會產出**假的 live-absent**）。

---

## 2. fingerprint-only 語義（E3 關鍵項）

### 2.1 `secret_slot_fingerprint`（sha256）對哪些字節取哈希

**裁決**：對 **paper 槽的 canonical 描述符**取 sha256（不是 readonly、不是聚合兩槽）。理由見 §5——P5 session attestation 的 paper session 只能對「它正在用的那一槽」重算指紋；聚合 readonly+paper 會與 P5 對不齊。

描述符（確定性字節串，只含 metadata + 內容摘要，**無明文**）：

```
"ibkr_secret_slot_v1\n"
"paper\tpresent=<bool>\tdir_mode=<0oNNN>\n"
  for each 常規檔 in paper/ (按檔名 ASCII 升序):
    "<filename>\tmode=<0oNNN>\tsha256=<hex(內容)>\n"
```

- `sha256=<hex(內容)>`：讀入檔案 raw bytes → `Sha256` → `hex::encode` → 立即丟棄 raw bytes。描述符裡只有摘要，**明文不入描述符**。
- 綁定真實憑證字節 → 憑證輪替 / 竄改 → 指紋變 → triangulation 可偵測。
- **符號連結（symlink）一律 fail-closed 拒絕**（防 TOCTOU / 目錄逃逸）；只處理 regular file。
- `hex::encode(Sha256 digest)` 恒為 64 lowercase hex → **by construction** 通過 `validate()` 的 `is_sha256_hex`。

> 政策備選（若 CC/E3 要求嚴格「slot fingerprint 不讀內容、僅 stat」）：把描述符每檔的 `sha256=<hex>` 換成 `len=<file_len>`（stat 取長度，不讀內容）。這是描述符 builder 的單點改動（一行），設計把該政策收斂在 builder 一處。**PA 建議採內容摘要版**（tamper-evidence 更強；account_id 反正要讀，已無「零讀取」可言）。CC 確認點見 §11-E2③。

### 2.2 `account_fingerprint_hash`（sha256）的輸入

- 材料：paper 槽內指定檔 `account_id`（單一 token = IBKR paper 帳號，如 `DU1234567`）。
- 讀入明文 → **正規化** → sha256 → hex。
- **正規化（P1/P5 必須共用同一函數，見 §5）**：`account_id.trim().to_ascii_uppercase()`。trim 去尾換行，uppercase 統一大小寫（IBKR 帳號為大寫英數）。
- account_fingerprint_hash 一律**源自 paper 槽的 account_id**（contract 只有一個此欄位；paper 是 `validate()` 要求 PresentHashed 的權威操作槽）。

### 2.3 明文零逃逸論證（是否成立：**成立**）

| 環節 | 誰持有明文 | 生命週期 | 是否逃逸 |
|---|---|---|---|
| 讀 account_id | pure loader 內局部 `let account_id: String` | 函數 scope 內；讀入後立即算 `account_fingerprint_hash(&account_id)` 與（可選）內容摘要，隨即出 scope drop | 否 |
| 讀 credential 檔內容（供 §2.1 內容摘要） | 局部 `Vec<u8>`/`String` | 同上，hash 後即 drop | 否 |
| 寫入 struct | struct 只有 enum/bool/64-hex String 欄位 | — | **結構性不可能**：無任何欄位型別可容納明文 |
| IPC/DB/log | P1 不接 IPC/DB；log 只輸出 posture enum + bool + 64-hex 指紋 | — | 否 |

論證要點：
1. **結構層保證**：`IbkrSecretSlotContractV1` 全部欄位皆 enum / bool / 定長 hex String。明文（account id / credential 內容）**沒有欄位可落腳**。即使 E1 手誤，也無處寫入。
2. **常量保證**：`secret_content_serialized` / `account_id_serialized` 由 loader **恒設常量 `false`**（不從輸入推導）；配合 §8-T7 序列化子串斷言測試（輸出 JSON 不得含已知測試明文），運行層再驗一道。
3. **持有點唯一**：明文只在 pure loader 的讀取步驟以局部變數存在，讀→hash→出 scope。無跨函數傳遞、無回傳、無捕獲。
4. **Drop / zeroize**：workspace **目前無 `zeroize` 依賴**（已查 `rust/Cargo.toml`）。威脅模型為本機 owner-only 檔 + 受信引擎進程，預設 drop（不歸零堆）風險 LOW。**建議**（defense-in-depth，非 blocker）：讀 account_id 用一個小 RAII wrapper，於 `Drop` 內 `for b in buf.as_mut_vec() { *b = 0 }` 手動歸零，避免引入新 crate；若 operator 願加 `zeroize` 則更乾淨。此為 E1 可選硬化，E2 覆核。

### 2.4 owner-only 權限校驗（仿 persistence.rs `mode() & 0o777`）

- **合規位**：槽**目錄** = `0o700`（owner rwx，需 x 才能 traverse）；槽內**檔** = `0o600`（owner rw）。
- 判定：`meta.permissions().mode() & 0o777`；目錄須 `== 0o700`、檔須 `== 0o600`。任一 group/other 位非零 → `owner_only_permissions=false` → blocker `OwnerOnlyPermissionsMissing`，且該槽 posture 不得標 `PresentHashed`。
- `#[cfg(unix)]` gate（`std::os::unix::fs::PermissionsExt`）。**非 unix（僅 Windows，非部署目標）**：無法驗權限 → fail-closed，`owner_only_permissions=false` + posture `Unknown` + typed reason `permission_check_unsupported_platform`。trade-core（Linux）與未來 Mac 皆 unix，實務不觸發。

---

## 3. live-absent 證明 + 三槽 posture 完整判定表

### 3.1 live 槽三態

| live 目錄狀態 | `live_slot_posture` | `live_secret_absent_or_empty` | validate() 結果 |
|---|---|---|---|
| 不存在 | `LiveAbsentOrEmpty` | `true` | 通過此項 |
| 存在但空（無 regular file 憑證材料） | `LiveAbsentOrEmpty` | `true` | 通過此項 |
| 存在且含憑證材料 | `LivePresentDenied` | `false` | **fail-closed**：`LiveSlotPresentOrUnknown` + `LiveSecretAbsentOrEmptyNotProven` 兩 blocker |

- live 槽**永不讀內容、永不算指紋**（僅列目錄判有無 regular file）。
- live 槽的 posture / bool **絕不進入** §2.1 的 fingerprint 描述符。

### 3.2 三槽完整判定表

| 槽 | 磁碟狀態 | posture | 對 contract 的影響 |
|---|---|---|---|
| readonly | 不存在 | `Missing` | validate() **接受**（`{PresentHashed, Missing}` 皆合法）；不進 fingerprint |
| readonly | 存在 + owner-only + 有材料 | `PresentHashed` | 接受 |
| readonly | 存在 + 權限過寬 | `Unknown` | fail-closed：`ReadonlySlotPostureInvalid` + `OwnerOnlyPermissionsMissing` |
| paper | 不存在 | `Missing` | fail-closed：`PaperSlotMissingOrUnhashed`；`secret_slot_fingerprint`＝""（不捏造）|
| paper | 存在 + owner-only + 有 account_id | `PresentHashed` | 接受；算 fingerprint + account_fingerprint_hash |
| paper | 存在 + 權限過寬 | `Unknown` | fail-closed：`PaperSlotMissingOrUnhashed` + `OwnerOnlyPermissionsMissing` |
| paper | 存在但無 account_id 檔 | `Unknown`（或 Missing）| fail-closed：`AccountFingerprintHashInvalid`（hash＝""）+ `PaperSlotMissingOrUnhashed` |
| live | 見 §3.1 | — | — |

### 3.3 live-absent 可信度（運行時 caveat，非 P1 tempdir 範疇）

「live absent」claim 只在 **base dir 正確**時可信。若 loader 找錯 base（§12-Q1），三槽全 absent，`live_secret_absent_or_empty` 會**錯誤**報 true。防線：以 readonly/paper 為**正控**——當 readonly 或 paper 被看見為 present，證明 base dir 正確，此時 live-absent 才可信。P1 tempdir 測試不受此影響（dir 由測試給定）；此為 P5/G4 runtime 整合關注點，設計在此標記，並建議 P5 attestation 對「三槽全 absent」保守處理（無法區分「對的目錄空」與「錯的目錄」→ fail-closed）。

---

## 4. 產出 `IbkrSecretSlotContractV1` 欄位逐一映射

| 欄位 | 來源 | 值 |
|---|---|---|
| `contract_id` | 常量 | `IBKR_SECRET_SLOT_CONTRACT_ID`（"ibkr_secret_slot_contract_v1"）|
| `source_version` | 常量 | `1` |
| `contract_present` | 常量（loader 成功產出時）| `true`（denied fallback 時 `false`）|
| `readonly_slot_posture` | stat readonly | 見 §3.2 |
| `paper_slot_posture` | stat paper | 見 §3.2 |
| `live_slot_posture` | 列 live 目錄 | 見 §3.1 |
| `secret_slot_fingerprint` | §2.1 sha256(paper 描述符) | 64-hex；失敗＝"" |
| `account_fingerprint_hash` | §2.2 sha256(normalize(paper/account_id)) | 64-hex；失敗＝"" |
| `owner_only_permissions` | §2.4 目錄 0o700 + 檔 0o600 | bool |
| `env_var_credential_fallback_denied` | 常量 | `true`（結構性，永不從 env 讀憑證）|
| `secret_content_serialized` | 常量 | `false` |
| `account_id_serialized` | 常量 | `false` |
| `live_secret_absent_or_empty` | §3.1 | bool |

- loader 產出後**由呼叫端**跑 `contract.validate()` 取 verdict（validate() 是既有 gate，P1 不重造判定）。

---

## 5. 三角校驗中的定位 + 指紋對齊機制（最大架構關注點）

### 5.1 P1 只產一條腿

`FeatureFlagSecretAuthMatrixV1`（`ibkr_feature_flag_secret_auth.rs`）的三方/四方校驗需要：
- `secret_slot_fingerprint` 三方一致：**secret_slot_contract**（P1）∧ session_attestation（P5）∧ envelope。
- `account_fingerprint_hash` 四方一致：**secret_slot_contract**（P1）∧ phase2_gate_artifact.api_session_topology（P2）∧ session_attestation（P5）∧ envelope。

**P1 只產 `secret_slot_contract` 這一條腿。** P2（gate artifact）、P5（session_attestation）、envelope **尚不存在**。因此：
- **P1 loader 輸出獨立可測**（`.validate()` 即完整驗收），**但尚未接入 live matrix 評估**。
- P1 **不 wire** `FeatureFlagSecretAuthMatrixV1`、**不呼** `validate_operation`、**不建** envelope、**不 enable** 任何 flag。

### 5.2 對齊的充要條件：單一共用純函數

指紋能否與其他腿對齊，取決於各腿是否對**同一輸入**用**同一算法**。保證方式＝**把指紋算法抽成 engine 內單一 `pub(crate)` 純函數，P1 建、P5 復用**，而非各腿各自實現：

```rust
// 落在 P1 新模組內，pub(crate) 供 P5 attestation producer 復用。
pub(crate) fn ibkr_account_fingerprint_hash(account_id: &str) -> String;   // sha256(trim+upper)
pub(crate) fn ibkr_paper_slot_fingerprint(paper_slot_dir: &Path) -> Result<String, String>; // §2.1 描述符
```

- P1 與 P5 皆在 `openclaw_engine` crate（連接器 Rust-owned），故共用 `pub(crate)` 函數天然可行。
- **對齊鐵則**：`account_fingerprint_hash`（P1，源自 slot）要等於 `account_fingerprint`（P5，源自 IBKR `reqAccountSummary` 回傳帳號），前提是**兩者對帳號 id 做同一正規化 + 同一 sha256**。P5 必須把 IBKR 回傳的帳號字串餵進同一 `ibkr_account_fingerprint_hash`。這是**跨腿契約**，設計在 §5.2 用「共用函數」把它從「約定」升級為「代碼強制」。
- **殘留對齊風險**（見 §12-Q2）：若 slot 內 `account_id` 字串（正規化後）與 IBKR 回傳的帳號字串不完全相同（前綴/格式差異），四方 hash 對不齊。此非 P1 能單獨消除——需 E3 建槽時 account_id **恰為** IBKR 回傳帳號的原樣 token。P1 用 tempdir 測試釘死正規化語義（§8-T8）；真對齊在 P5/G4 runtime 驗。

---

## 6. 模塊落點（同構 P0 四件套）

新增單一 engine 模組（**不放 openclaw_types**）：

- 檔：`rust/openclaw_engine/src/ibkr_secret_slot_loader.rs`
- lib.rs：`pub mod ibkr_secret_slot_loader;`（插在 `drawdown_revoke` / `live_authorization` 附近，維持字母序附近即可）

模組內四件套（逐一對應 P0 `handlers/stock_etf.rs:396-468`）：

| P0 對應 | P1 對應 |
|---|---|
| `static STOCK_ETF_RISK_POLICY: OnceLock<Result<..,String>>` | `static IBKR_SECRET_SLOT_CONTRACT: OnceLock<Result<IbkrSecretSlotContractV1, String>>` |
| `load_stock_etf_risk_policy_from_dir(dir)` 純 loader | `load_ibkr_secret_slot_contract_from_base(ibkr_base)` 純 loader（§1.2）|
| `load_stock_etf_risk_policy()` env wrapper | `load_ibkr_secret_slot_contract()`（呼 `resolve_ibkr_secrets_base()`，§1.3）|
| `stock_etf_risk_policy()` OnceLock+warn-once | `ibkr_secret_slot_contract()` OnceLock+warn-once |
| `denied_stock_etf_risk_policy_fallback()` | `denied_ibkr_secret_slot_contract_fallback()`（§7）|

外加 §5.2 兩個 `pub(crate)` 指紋純函數（同檔或內部子 module）+ §2.1 描述符 builder（政策單點）。

- **不接 dispatch / 不接 IPC / 不接 Python**（scope 邊界，§5.1）。OnceLock cache 供未來（P5/healthcheck）取用，但 P1 本身不放任何 caller wiring——設計提供函數，caller 由後續 phase 接。

---

## 7. fail-closed 全表（絕不捏造 PASS 指紋）

| 觸發 | loader 回傳 | posture / 欄位 | 結果 |
|---|---|---|---|
| base dir 無法解析（env/HOME 皆缺）| `Err` → 呼叫端用 denied fallback | 全 fail-closed 方向 | validate() reject |
| base dir 不可讀（I/O / 權限）| `Err` → denied fallback | 同上 | reject |
| paper 槽存在但讀 account_id I/O 失敗 | `Ok(contract)` | `account_fingerprint_hash=""`；paper posture `Unknown` | reject（`AccountFingerprintHashInvalid`）|
| paper 槽不存在 | `Ok(contract)` | paper `Missing`；fingerprint="" | reject（`PaperSlotMissingOrUnhashed`）|
| 權限過寬 | `Ok(contract)` | `owner_only_permissions=false` | reject（`OwnerOnlyPermissionsMissing`）|
| live 槽含材料 | `Ok(contract)` | `LivePresentDenied` / `false` | reject（`LiveSlotPresentOrUnknown`）|
| 槽內含 symlink | `Err` → denied fallback | — | reject |

**denied fallback**（`denied_ibkr_secret_slot_contract_fallback()`，仿 `denied_stock_etf_risk_policy_fallback` 哲學：NEVER fabricate permissive）：
- `contract_id` + `source_version=1`（可識別）；`contract_present=false`；三槽 posture `Unknown`；`secret_slot_fingerprint=""`、`account_fingerprint_hash=""`；`owner_only_permissions=false`；`live_secret_absent_or_empty=false`（不能證 absent → 未證 → fail-closed）；`env_var_credential_fallback_denied=true`、`secret_content_serialized=false`、`account_id_serialized=false`（安全方向常量）。→ `validate()` 產一堆 blocker、`accepted=false`。**永不產出 accepted=true 的假 PASS。**

---

## 8. E4 測試策略（Linux cargo，tempdir，仿 foundation_status_fixtures.rs 純 loader 範式）

全部走 `load_ibkr_secret_slot_contract_from_base(tmp)` 純 loader + tempdir，**不動 OPENCLAW_SECRETS_DIR 全域**；少數 env-wrapper 測試才 `crate::test_env_lock::guard()` 串行（drawdown_revoke 教訓）。權限測試 `#[cfg(unix)]`。

| # | fixture | 斷言 |
|---|---|---|
| T1 | paper(0o700 dir,0o600 account_id) + readonly(present) + live(absent) | `validate().accepted==true`；postures PresentHashed/PresentHashed/LiveAbsentOrEmpty；兩指紋 `is_sha256_hex` |
| T2 | live 槽含 1 檔 | `live_slot_posture==LivePresentDenied`；`live_secret_absent_or_empty==false`；reject 含 `LiveSlotPresentOrUnknown` |
| T3 | readonly absent + paper present | readonly posture `Missing`；`validate().accepted==true`（readonly Missing 合法）|
| T4 | paper dir 0o755（group/other 可讀）| `owner_only_permissions==false`；paper posture 非 PresentHashed；reject 含 `OwnerOnlyPermissionsMissing` |
| T5 | paper 槽 absent | paper posture `Missing`；`secret_slot_fingerprint==""`；reject 含 `PaperSlotMissingOrUnhashed` |
| T6 | paper present 但無 account_id 檔 | `account_fingerprint_hash==""`；reject 含 `AccountFingerprintHashInvalid`；loader 不捏值 |
| T7 | account_id 內容="DUPLAINTEXT123" | `serde_json::to_string(&contract)` **不含** "DUPLAINTEXT123"；`account_fingerprint_hash==sha256("DUPLAINTEXT123")`；`account_id_serialized==false`、`secret_content_serialized==false` |
| T8 | 對齊/正規化 | `ibkr_account_fingerprint_hash("du1234567\n")==ibkr_account_fingerprint_hash("DU1234567")==` 預計算 sha256("DU1234567")（證 P5 復用同函數得同 hash）|
| T9 | 決定性 | 同 fixture 連載兩次 → 兩指紋逐字相同 |
| T10 | symlink | paper 內放 symlink → `Err` → 呼叫端 denied fallback → reject |
| T11 | denied fallback | 直接斷言 `denied_ibkr_secret_slot_contract_fallback().validate().accepted==false` 且無假 PASS |

- **E1 完成不需真實槽**：以上全 tempdir 模擬；真 readonly/paper 槽保持 absent（§9）。

---

## 9. 授權邊界標注（交回 PM 決策）

| 工作 | 責任鏈 | 是否需真實槽 |
|---|---|---|
| (a) loader 設計 / 實現 / tempdir 測試 | **E1 → E2 → E4**（Linux cargo）| **不需**。tempdir 模擬全 posture；live 槽在真檔系統**必須保持 absent** |
| (b) readonly/paper 槽真實凭证材料創建（owner-only account_id 檔於 trade-core）| **E3 → BB → Operator** | 是（真憑證）|

- (a) 與 (b) **解耦**：E1 可在**無任何真實槽**下把代碼寫完測完；(b) 的建槽動作獨立、之後才發生。P1 sign-off 鏈＝E1→E2→E4，另 E3→BB→Operator 負責建槽（AMD gated sequence P1 行）。

---

## 10. 降級 / rollback 路徑（PA 硬性要求）

- **本質 additive、零狀態**：P1 只新增 1 檔 + lib.rs 1 行 mod 宣告 + 1 test 檔。無 DB migration（AMD Invariant 8：read-only 階段無 migration）、無 schema、無 IPC、無 flag 翻轉、無 Python。
- **runtime 降級**：loader 任何失敗＝denied fallback（§7），contract `accepted=false`，下游（未來 matrix）fail-closed 拒授權。**無 fail-open 路徑**。
- **rollback**：`git revert` 該 commit（移除 1 檔 + lib.rs 1 行 + test）。因 P1 **不接任何 caller**（OnceLock cache 無人讀、無 IPC route），移除**零下游斷裂**——這是 P1 作為 scaffold-only leg 的結構性優勢。
- **kill posture**：即使 loader 誤入生產且被誤呼，其輸出經 `validate()` 只會 reject（fail-closed），不會 enable 任何路徑；live 槽保持 absent 是額外結構防線。

---

## 11. E2 重點審查 3 點

1. **明文零逃逸（最高優先）**：逐字驗 pure loader 內 account_id / credential 內容**只以局部變數存在、hash 後即出 scope**；struct 無欄位可容明文；`secret_content_serialized` / `account_id_serialized` 為**常量 false**（非推導）；T7 序列化子串斷言存在且真的能抓到明文洩漏。檢查是否有意外 `Debug`/`log`/`tracing` 把明文帶出（log 只准 posture/bool/64-hex）。
2. **live-absent 不可 fail-open**：驗 live 槽含材料時**必**走 `LivePresentDenied` + `live_secret_absent_or_empty=false`；驗「三槽全 absent」不會被誤當成合法 PASS（paper Missing 必 reject）；denied fallback 的 `live_secret_absent_or_empty=false`（不能證 absent＝未證）。
3. **指紋算法單點 + 政策單點**：驗 `secret_slot_fingerprint` / `account_fingerprint_hash` 由**單一 `pub(crate)` 純函數**產（供 P5 復用，不得在別處複製算法）；§2.1 內容摘要 vs metadata-only 政策收斂在描述符 builder 一處（CC 若要求嚴格 stat-only，此處一行可切）；`hex::encode` lowercase 保證 `is_sha256_hex` by construction。

---

## 12. 需 PM / E3 / Operator 拍板的開放問題

- **Q1（E3/Operator，運行時路徑）**：trade-core 上 `OPENCLAW_SECRETS_DIR` 實值是什麼？必須使 `resolve_ibkr_secrets_base()` 解析結果 == E3 建 readonly/paper 槽的實際路徑。bybit 慣例（`OPENCLAW_SECRETS_DIR`＝`secret_files/bybit` 根）與 AMD 字面（`OPENCLAW_SECRETS_DIR/external/ibkr`）對此 env 的假設不同。**不確認會導致 loader 永遠在錯目錄看到全 absent（安全但功能失效 + 假 live-absent）**。P1 tempdir 測試不受影響，但 P5/G4 runtime 前必解。
- **Q2（E3/Operator，槽檔佈局 + 對齊）**：
  - paper 槽內 account id 檔的**檔名**（設計預設 `account_id`）與**內容格式**（單一 token = IBKR paper 帳號原樣，無多餘 token/行）。E3 建槽必須照此，否則 §5.2 四方 hash 對不齊。
  - readonly 槽是否與 paper **同一 IBKR 帳號**？contract 只有一個 `account_fingerprint_hash`（源自 paper）。若 readonly 是不同帳號，P1 不 fail（只 hash paper），但語義需 Operator 確認 readonly 不指向 live 帳號（live-ness 由 P5 `account_fingerprint_is_live` 判，非 P1）。
- **Q3（CC，指紋政策）**：`secret_slot_fingerprint` 採「內容摘要」（PA 建議，tamper-evidence 強）或嚴格「stat-only（mode+len，不讀憑證內容）」？描述符 builder 單點可切（§2.1 備選）。
- **Q4（Operator，可選硬化）**：是否引入 `zeroize` crate（新 workspace dep）做明文歸零，或接受「無新 dep + 手動 Drop 歸零」（PA 建議後者，威脅模型 LOW）。

---

## 13. 代碼足跡與持續開發成本

- **新增檔**：`rust/openclaw_engine/src/ibkr_secret_slot_loader.rs` ~ 180–260 LOC（四件套 + 2 指紋純函數 + 描述符 builder + denied fallback + 可選 Drop-zeroize wrapper）。
- **新增測試**：`ibkr_secret_slot_loader` tests（同檔 `#[cfg(test)] mod` 或 `tests/` 掛點，仿 foundation_status_fixtures）~ 200–300 LOC（T1–T11）。
- **改動熱檔**：**無**。僅 `rust/openclaw_engine/src/lib.rs` +1 行 mod 宣告（非熱路徑）。0 dispatch / 0 IPC / 0 Python / 0 SQL。
- **blast radius**：極小。P1 不接任何 caller，OnceLock cache 無讀者，rollback 零斷裂（§10）。
- **持續開發成本**：P5 復用 §5.2 兩個 `pub(crate)` 指紋函數 → P5 attestation producer 不重造算法、天然對齊。描述符 builder 政策單點 → 未來調整（如加 credential 檔類型）改一處。
- **讀碼成本**：等效方案中，「同構 P0 四件套 + 共用指紋純函數」讀碼成本最低（E1 有現成範本 `handlers/stock_etf.rs:396-468` 可對照），優於把 loader 塞進 handlers/stock_etf.rs（後者已含 P0 loader，混入 P1 會膨脹該檔且耦合 IPC handler 語境）。故選獨立 `ibkr_secret_slot_loader.rs` 模組。

---

## 14. E1 派工建議切分

P1 slice 小且檔零重疊，**建議單 E1 一波完成**（不值得多 E1 並行，拆分協調成本 > 收益）：

- **E1（單一）**：`ibkr_secret_slot_loader.rs`（§6 四件套 + §5.2 指紋函數 + §2.1 描述符 builder + §7 denied fallback）+ lib.rs mod 宣告 + §8 T1–T11 測試。
- 依賴：無（消費既有 `IbkrSecretSlotContractV1`；`sha2`/`hex` workspace 已備）。
- 若 PM 堅持並行，唯一可切點＝「指紋純函數 + 描述符 builder（含 T7/T8/T9 明文/對齊/決定性測試）」為 E1-A，「stat/posture/loader 四件套 + T1–T6/T10/T11」為 E1-B，但兩者同檔 → 需先約定檔內佈局否則撞行，**淨收益為負，不建議**。

---

## STATUS: DONE_WITH_CONCERNS

- **設計要點**：P1＝同構 P0 四件套的純 loader（新檔 `ibkr_secret_slot_loader.rs`，0 熱檔改動），stat readonly/paper 兩槽 + 證 live absent，只算 `secret_slot_fingerprint`(paper 槽描述符,含內容摘要) 與 `account_fingerprint_hash`(normalize(paper/account_id))，產一條可過 `IbkrSecretSlotContractV1::validate()` 的 leg，**不接 matrix/IPC/Python/DB、不 enable flag、live 保持 absent**。fail-closed 全表＋denied fallback 保證絕不捏 PASS。
- **最大風險**：(1) 明文零逃逸論證**成立**（結構層無欄位可容明文 + 常量 false + 局部即毀 + T7 斷言）；殘留 LOW 風險僅「預設 drop 不歸零堆」，建議手動 Drop 歸零。(2) 指紋能否與其他腿對齊——**能，但充要條件是抽單一共用純函數（P1 建 P5 用）**；真對齊的殘留變數是「slot account_id 字串 == IBKR 回傳帳號原樣」，非 P1 可單獨消除，需 E3 建槽照契約（Q2）。
- **待拍板**：Q1 OPENCLAW_SECRETS_DIR 運行時實值（否則假 live-absent）、Q2 槽檔佈局+對齊、Q3 指紋政策（內容摘要 vs stat-only）、Q4 是否引 zeroize。
- **E1 派工**：單 E1 一波（檔零重疊，拆分負收益）。

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-09--ibkr_p1_secret_slot_loader_tech_design.md
