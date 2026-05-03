# REF-20 Sprint 1 Track B — Rust manifest signature verify path 修補

**Owner：** E1 (Track B 單實例)
**Date：** 2026-05-03
**PA spec：** `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md` §2 Track B + §5 Push Back #3
**根因：** E3-P0-1 CRITICAL — `replay_runner.rs::load_and_verify_manifest` self-sign tautology + key.hex 缺 fail-open
**狀態：** ✅ 6 unit test + 5 helper test + 25 既有 LG-5 pytest + 8 既有 xlang fixture test 全綠。等 E2 審查 + E4 回歸（不自行 commit）

---

## §1 問題病灶

`srv/rust/openclaw_engine/src/bin/replay_runner.rs:386-470` `load_and_verify_manifest`（pre-Sprint-1）：

| 漏洞 | 行 | 性質 |
|---|---|---|
| `signature` + `manifest_hash` 標 `#[allow(dead_code)]` | L345-350 | 從 disk 讀進但不當 verify 輸入 |
| `let signature_hex = signer.sign(canonical_body);` 重簽 | L455 | tautology — 重簽結果與宣告 sig 永遠 byte-equal |
| `signer.verify(canonical_body, &body_hash, &signature_hex, ...)` 對 self-sign 結果 verify | L456-462 | 永遠 PASS（attacker 拿到 signing key 即可造任意 manifest） |
| `if !key_hex_path.exists() { eprintln!(warning); return Ok(manifest); }` | L404-411 | fail-open（無 key.hex 仍視作 verify PASS） |

**攻擊面**：
1. attacker 拿到 `OPENCLAW_REPLAY_SIGNING_KEY` → 造任意 manifest（簽出新 sig + hash）→ 通過 self-sign verify
2. attacker 把 manifest 放在無 sibling `key.hex` 的目錄 → fail-open path 直接 `Ok`

---

## §2 修補方向（PA 簽收）

依 PA Sprint 1 dispatch §2 Track B 與 §5 Push Back #3：

1. **改 verify 輸入為 manifest 自帶 sig/hash**（非 self-sign 結果）
2. **移除 `#[allow(dead_code)]`**（`signature` + `manifest_hash` 升為 verify expected 輸入）
3. **key.hex 缺改 hard error**（fail-closed，封閉 fail-open）
4. **canonical body 路徑**：strip envelope 欄位（`signature` / `manifest_hash` / `signature_key_ref`）+ sorted-keys serde_json::to_vec → byte-equal Python sibling signer
5. **healthcheck `[44]` 配套**：PA push back #3 — V045 running row 的 sibling `key.hex` 存在性 monitor（WARN-only 過渡 gate）

---

## §3 修改清單

### 3.1 `srv/rust/openclaw_engine/src/replay/manifest_signer.rs`（+196 LOC：762→958）

新增公開 surface：

| Item | 用途 |
|---|---|
| `pub const ENVELOPE_KEYS_FOR_SIGNING: [&str; 3]` | 不參與簽名 payload 的 envelope 欄位（`signature`、`manifest_hash`、`signature_key_ref`），與 Python sibling 對齊 |
| `pub fn canonical_body_for_signing(disk_bytes: &[u8]) -> Result<Vec<u8>, serde_json::Error>` | 對單檔 manifest（含 envelope）reproduce 簽名時的 canonical body：(1) parse；(2) strip envelope；(3) sorted-keys + compact serde_json::to_vec |

新增 5 unit test 覆蓋：
- `canonical_strips_envelope_and_sorts_keys`（標準 happy path：亂序輸入 → 標準 sorted compact 輸出）
- `canonical_is_idempotent_on_already_stripped_body`（既有 fixture 不破：已 stripped + alphabetical 鍵序的 body byte-equal in/out）
- `canonical_rejects_non_object`（V3 §5 不變量：array / scalar / 損壞 JSON 全拒）
- `canonical_idempotent_double_apply`（連 apply 兩次 byte-equal）
- `envelope_keys_constant_matches_doc`（const 條目固定為 3 個確切名稱）

### 3.2 `srv/rust/openclaw_engine/src/bin/replay_runner.rs`（+542 LOC：471→1013）

#### `ReplayManifest` struct 變更

```rust
struct ReplayManifest {
    experiment_id: String,
    data_tier: String,
    fixture_uri: String,
    pub signature: String,                    // NEW: was #[allow(dead_code)]
    pub manifest_hash: String,                // NEW: was #[allow(dead_code)]
    #[serde(default)]
    pub signature_key_ref: Option<String>,    // NEW: was #[allow(dead_code)]
    #[serde(default)]
    pub run_id: Option<String>,               // NEW: PA dispatch §2 Track A bridge
}
```

#### `load_and_verify_manifest` rewrite

| 階段 | 新行為 |
|---|---|
| key.hex 缺 | `return Err("manifest_signer_key_missing: ...")` 而非 `eprintln + Ok` |
| canonical body | `canonical_body_for_signing(raw.as_bytes())` 而非 `raw.as_bytes()` |
| 完整性 sanity gate | `compute_body_hash(canonical_body) == manifest.manifest_hash` 否則 `manifest_hash_mismatch` 路徑 fail（在 `signer.verify` 之前） |
| verify 輸入 | `signer.verify(canonical_body, &manifest.manifest_hash, &manifest.signature, &fp, &archive)` — disk-supplied sig/hash 為 expected，非重簽結果 |
| fingerprint 解析 | 優先用 `manifest.signature_key_ref`（audit chain marker），否則 fallback 磁碟 key 自算 fingerprint |

#### `#[cfg(test)] mod tests`（新增 6 test）

| Test | 覆蓋 |
|---|---|
| `happy_path_full_manifest_verifies` | 寫合法 single-file manifest + sibling key.hex → verify Ok |
| `fail_mode_a_tautology_defense_body_drift` | 簽完後改 body 1 字 + 不更 sig/hash → `manifest_hash_mismatch`（pre-Sprint-1 self-sign 路徑會 silent pass） |
| `fail_mode_b_key_hex_missing_hard_errors` | 不寫 key.hex → `manifest_signer_key_missing` 而非 `Ok` |
| `fail_mode_c_signature_tampered_signature_mismatch` | 簽名第 1 byte 改寫，body + hash 仍對 → `signature_mismatch`（hash gate 不誤觸） |
| `fail_mode_d_declared_hash_tampered_manifest_hash_mismatch` | declared hash 第 1 byte 改寫 → `manifest_hash_mismatch` 由 sanity gate 抓到 |
| `canonical_body_byte_equal_to_python_sibling` | 對 single-file manifest 算 canonical body → byte-equal 預期 sorted compact 結果（Python sibling 對齊驗證） |

### 3.3 `srv/helper_scripts/db/passive_wait_healthcheck/checks_governance.py`（+159 LOC：747→906）

新增 `check_44_replay_manifest_key_presence(cur) -> tuple[str, str]`（PA push back #3）：
- 讀 V045 `replay.run_state` `status='running'` row + `output_path`
- 對每 row 檢查 `<output_path>/key.hex` 是否存在
- V045 表缺 → PASS-skip（避免 Sprint 1 rollout 順序差錯誤判 FAIL）
- 全部 in-flight 都有 → PASS
- 1+ 缺 → WARN（過渡 gate；Track B 部署後新啟動 fail-closed，舊 in-flight 可能 pre-date deploy；V042 archive Wave 6+ 取代運維契約）
- V045 query 例外 → FAIL（DB drift 訊號）

### 3.4 `srv/helper_scripts/db/passive_wait_healthcheck/__init__.py` + `runner.py`

- `__init__.py`：export + `__all__` 加 `check_44_replay_manifest_key_presence`
- `runner.py`：cursor block 註冊（`[43]` 之後）+ `_RUNNER_DESCRIPTION` 加 `[44]` 條目 + `main()` docstring 內 ID 列表加 `[44]`

---

## §4 關鍵 diff（節錄）

### 4.1 verify path 反轉

```rust
// PRE-SPRINT-1 (DELETED, fail-open tautology):
let canonical_body = raw.as_bytes();
let body_hash = compute_body_hash(canonical_body);
let signature_hex = signer.sign(canonical_body);  // self-sign
signer.verify(canonical_body, &body_hash, &signature_hex, &fp, &archive)
// → recomputed sig over body == body's own sig trivially → never fails

// SPRINT-1 TRACK B (FAIL-CLOSED):
let canonical_body = canonical_body_for_signing(raw.as_bytes())?;  // strip + sort
let actual_body_hash = compute_body_hash(&canonical_body);
if actual_body_hash != manifest.manifest_hash {
    return Err("manifest_hash_mismatch: ...");  // sanity gate (in-band)
}
signer.verify(
    &canonical_body,
    &manifest.manifest_hash,    // disk-supplied, NOT recomputed
    &manifest.signature,        // disk-supplied, NOT recomputed
    &verify_fingerprint,
    &archive,
)
// → tautology closed. Sig must match HMAC over canonical body + match disk-stored sig.
```

### 4.2 fail-open → fail-closed

```rust
// PRE-SPRINT-1:
if !key_hex_path.exists() {
    eprintln!("...");
    return Ok(manifest);                       // ← fail-open vulnerability
}

// SPRINT-1 TRACK B:
if !key_hex_path.exists() {
    return Err("manifest_signer_key_missing: ...".into());  // ← fail-closed
}
```

---

## §5 治理對照（CLAUDE.md §七）

| 項目 | 狀態 | 證據 |
|---|---|---|
| 雙語 MODULE_NOTE EN/中 | ✅ | `manifest_signer.rs::ENVELOPE_KEYS_FOR_SIGNING` + `canonical_body_for_signing` 中英對照；`replay_runner.rs::ReplayManifest` 與 `load_and_verify_manifest` 全雙語 docstring；6 unit test 中英對照註釋 |
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ 0 hit | `grep -rE '/home/ncyu\|/Users/[^/]+' <changed files>` returns nothing |
| 硬邊界 0 觸碰 | ✅ 0 hit | `max_retries / live_execution_allowed / execution_authority / system_mode / OPENCLAW_ALLOW_MAINNET / authorization.json` 全部 0 |
| 0 SQL mutate | ✅ | `INSERT/UPDATE/DELETE/TRUNCATE` 只在註釋出現（DELETED / DB INSERT 為文檔）；healthcheck 純 SELECT |
| 0 `live_*` mutate | ✅ | 無 |
| 文件 ≤1500 行 hard cap | ✅ | replay_runner 1013 / manifest_signer 958 / checks_governance 906 / runner 757；皆超 800 警告但 ≤1500 hard cap |
| `cargo test --release --features replay_isolated --tests` | ✅ ALL GREEN | 2454 + 58 + 6 + 7 + 12 + 5 + 3 + 19 + 4 + 4 + 8 + 5 + 6 + 4 + 35 + 3 + 5 + 2 + 3 = 2,643 test 全綠（其中 35 個 lib test 含 manifest_signer 15 + replay_runner 6） |
| `cargo clippy --release --bin replay_runner --features replay_isolated` | ✅ 0 warning（限 my diff 範圍） | 預先 openclaw_core 的 too_many_arguments lint 是 pre-existing |
| `nm target/release/replay_runner` forbidden symbol | ✅ 0 hit | trading_writer / live_execution / live_authorization::write / build_exchange_pipeline / acquire_lease / place_order / ipc_server / bybit_private_ws / ws_client 全 0 |
| Healthcheck 配套 | ✅ | `[44] check_44_replay_manifest_key_presence` 註冊 + `_RUNNER_DESCRIPTION` 更新 + import path 通過 |
| 既有 LG-5 healthcheck pytest 25 個 | ✅ 25/25 PASS | `pytest helper_scripts/db/test_lg5_healthchecks.py -x -q` |
| 既有 xlang consistency 8 test | ✅ 8/8 PASS | `cargo test --release --test replay_manifest_signer_xlang_consistency` |

---

## §6 不確定之處 / 待 E2 / E4 review 點

### 6.1 Pre-existing baseline exception clause（CLAUDE.md §九）

`replay_runner.rs` 從 471 → 1013 行（+542），超過 800 警告線但 ≤ 1500 hard cap。新增的 542 行是：
- ~80 行雙語注釋（`load_and_verify_manifest` rewrite 對照 PA spec）
- ~80 行 `ReplayManifest` struct 雙語 doc + 4 新欄位
- ~380 行 `#[cfg(test)] mod tests`（6 fail-mode unit test + 3 helper fn + 雙語對照）

**E2 review point**：是否該抽 unit test 到 `tests/replay_runner_verify_path.rs`（integration test）— 但 test fns 依賴 `super::load_and_verify_manifest` private fn。可選做法：
- (a) 把 `load_and_verify_manifest` 改成 `pub`（破 binary encapsulation）
- (b) 抽到 `crate::replay::manifest_load` 公開 module
- (c) 維持 `#[cfg(test)] mod tests` 在 binary 內（CLAUDE.md §九 1500 hard cap 內可接受）

E1 預設 (c)；E2 / E4 認為 (b) 更乾淨可後續處理。

### 6.2 V042 SQL-backed key archive 時序（PA push back #3）

Track B 完成後狀態：
- dev / fixture 路徑：`tests/fixtures/replay_manifest_signer/` 8/8 xlang test PASS（既有 stripped-body fixture 仍 happy path 不破）
- production 路徑：sibling key.hex 必須由 operator 手動部署到每個 V045 run 的 `output_path`；`[44]` healthcheck 監測這個契約
- V042 SQL archive land 後（Wave 6+，ETA ≥2026-05-15）：`load_and_verify_manifest` 改用 SQL-backed `KeyArchive` impl，sibling key.hex 路徑可降級

**E2 / E4 review point**：是否該在 Track B 同 commit 加一個 `OPENCLAW_REPLAY_KEY_ARCHIVE_BACKEND=sibling_keyhex` 的 env-gate？這樣 V042 land 後可 cleanly 切到 SQL backend 不破 backwards compat。當前選擇是 hardcoded sibling fallback；如果 PA / E2 認為 env-gate 為 W1-prep 必要，下一輪補。

### 6.3 Track A 寫 fixture 的 byte-equal 對齊（PA E2 必查 #1）

我已驗證 Mac dev (aarch64-apple-darwin) `serde_json::to_vec(&Value)` byte-equal Python `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')`（見 §3.1 第 5 個 unit test `canonical_body_byte_equal_to_python_sibling`）。

**Track A E1 必對齊的 invariant**：
- Python `_write_manifest_fixture(...)` 對 stripped body 必用 `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)`
- `ensure_ascii=False` 是關鍵 — Python 默認 `True` 會 escape 非 ASCII，Rust 不會 → byte 不等
- 寫 disk 時 envelope 三欄位（`signature` / `manifest_hash` / `signature_key_ref`）可任意位置插入 full manifest，不影響 Rust 端 verify（因為 strip 後 re-canonicalize）

**E4 review point**：跨 track integration smoke 必含 Track A + Track B 共用一份完整 manifest fixture（real Python sign + Rust verify path）以驗證 byte-equal 不變量在真實工作流中成立。

### 6.4 fail mode (a) tautology defense 細節

我的 (a) 測試模擬 attacker 在簽完後改 body 1 字（`fixtures/x/` → `fixtures/ATTACKER_PATH/`），觀察 verify 路徑的反應。預期是 `manifest_hash_mismatch` 由 sanity gate 抓到（因為 body 改了，canonical body hash drift 發生在 hash gate 之前 trip signer.verify 之前）。

**為什麼不是 `signature_mismatch`？** 因為我們的 `compute_body_hash(canonical_body)` 是對「重 canonicalize 後的新 body」算的，body 改了 → canonical body 改 → hash 改 → declared hash（disk 上仍是原始 hash）對不上 → sanity gate 先抓到。

如果 attacker 同時改 body + 改 disk 上的 manifest_hash 來 bypass sanity gate？那 signer.verify 第二輪會發現 body 對應的 HMAC 對不上 disk sig → `signature_mismatch`。

如果 attacker 同時改 body + manifest_hash + signature（三齊改）？那 attacker 必須有 signing key — 此時防線退到 V042 archive（key 註冊 + status 管理）；attacker 拿到 retired/expired key → archive lookup 走 `KeyExpired` fail-mode；attacker 拿到 active key → 守不住（這是 HMAC 本身的限制，需要 KMS / HSM 才能進一步）。

E2 review point：(a) 測試覆蓋 attacker 中等能力（拿到 disk 但無 key），不覆蓋 attacker 高等能力（拿到 active key）。後者是 V042 的職責，Track B 範圍不該擴大。

### 6.5 Healthcheck `[44]` 的 status filter

我用 `status='running'` 而非也包含 `status='starting'`：
- `status='starting'`：V045 row 已 INSERT 但 subprocess 還沒 spawn → key.hex check 過早（Track A 的 `_write_manifest_fixture` 寫 sequence 是 INSERT V045 → write fixture → spawn → UPDATE 'running'，所以 `starting` 期間 fixture 可能還沒寫到 disk）
- `status='running'`：subprocess 已 spawn 並 verified manifest 通過（沒通過會 exit non-zero → UPDATE 'failed' 而非 'running'）

**E4 review point**：是否該也檢查 `'starting'` 但 ts > 5 min 的 row？這會抓到「Python INSERT V045 但 fixture writer 卡住沒寫 key.hex」的 race。當前選擇是不抓（因為 Track A spawn poll 1.5s 後若仍 starting 已視為 failed），E4 認為該擴可後續加。

---

## §7 Operator 下一步

1. **E2 review**：閱讀 `replay_runner.rs:436-666`（rewrite L386-470 段）+ `manifest_signer.rs::canonical_body_for_signing` + 6 unit test → 確認雙語 / 跨平台 / 0 forbidden symbol / verify 輸入正確
2. **E4 回歸**：
   - `cd srv/rust/openclaw_engine && cargo test --release --features replay_isolated --tests` → 全綠（含 35 lib test + 8 xlang fixture）
   - `nm target/release/replay_runner | grep -iE "trading_writer|live_execution|...|build_exchange_pipeline"` 0 hit
   - `python3 -m pytest srv/helper_scripts/db/test_lg5_healthchecks.py -q` 25/25 PASS
   - 跑一次 `python3 srv/helper_scripts/db/passive_wait_healthcheck.py` 看 `[44]` row 出現（V045 缺 → PASS-skip；V045 在 + 0 running row → PASS vacuous true）
3. **PM 統一 commit + push**（CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM）：
   - 我**未** commit。等 E2 sign-off + E4 回歸通過。
   - PM commit 時更新 `.codex/MEMORY.md`（如有）+ `docs/CLAUDE_CHANGELOG.md` + Linear `OpenClaw 62-Finding Remediation` 父 issue（PA issue REF-20 Sprint 1 Track B sub-bullet）。
4. **Track A E1**（並行進行中）必對齊 §6.3 byte-equal invariant：
   - Python sign 用 `json.dumps(stripped_body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')`
   - 寫 disk 時可保留 envelope 欄位（Rust 端會 re-strip）
5. **V042 SQL-backed archive task**（Wave 6+，未排程）：
   - 屬 PA Wave 6+ task，非 Sprint 1 範圍
   - V042 land 前，operator runbook：每個 `output_path` 必放一個 `key.hex`（healthcheck `[44]` 監測）
6. **healthcheck `[44]` cron 啟用**：
   - 已自動掛入 `passive_wait_healthcheck.py` cursor 區塊（cron `0 */6 * * *` 自動跑）
   - 不需額外 cron 設定

---

## §8 完成度自查（PA dispatch §4 改點清單）

| PA dispatch §4 改點 | 狀態 |
|---|---|
| 改點 #1：移除 `signature` + `manifest_hash` `#[allow(dead_code)]`（L345-361） | ✅ |
| 改點 #2：`if !key_hex_path.exists()` 從 `eprintln + Ok` → `Err` hard error（L386-411） | ✅ |
| 改點 #3：刪除 `signer.sign(canonical_body)` self-sign + 改 verify 用 manifest 自帶 `signature` + `manifest_hash`（L448-470） | ✅ |
| 改點 #4：tests mod 4 fail-mode（signature_mismatch + hash_mismatch + key_missing + happy）+ canonical body xlang test | ✅ 6 test（4 fail-mode + happy + xlang sanity） |

**PA E2 必查 3 點**：
| 點 | 狀態 | 證據 |
|---|---|---|
| `compute_body_hash(raw.as_bytes())` 與 Python sibling canonicalisation byte-equal | ✅ | 我 verified `canonical_body_for_signing` 取代 `raw.as_bytes()`；Mac/Linux serde_json byte-equal Python sorted-keys compact（test `canonical_body_byte_equal_to_python_sibling` 鎖定） |
| `manifest.signature` hex string verify 內部 `hex::decode` 失敗 mode | ✅ | manifest_signer::verify 對 sig 內部以 `_constant_time_eq` byte 比較不重 hex decode；hex::decode 失敗在 `compute_key_fingerprint`/key load 路徑回 `manifest_signer_key_invalid_hex`（test fail_mode_b 旁系覆蓋） |
| 不破壞 `tests/fixtures/replay_manifest_signer/` 既有 fixture | ✅ | xlang_consistency 8/8 仍 PASS（`canonical_body_for_signing` 對 stripped body 是 noop） |

**PA push back #3 healthcheck 配套**：
| 點 | 狀態 |
|---|---|
| `helper_scripts/db/passive_wait_healthcheck.py` 加 `check_replay_manifest_key_presence()` | ✅ check_44_replay_manifest_key_presence at checks_governance.py:440 |
| 對 V045 status='running' row 檢查 sibling key.hex；缺 → WARN | ✅ |

---

E1 IMPLEMENTATION DONE: 待 E2 審查 (report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_b_manifest_verify.md)
