# REF-20 Wave 2 P2a-S2 — HMAC Manifest Signer (Rust + Python)

**Date:** 2026-05-03
**Owner:** E1
**Task:** R20-P2a-S2 — HMAC sign+verify module（Rust + Python 雙端，4 fail-mode）
**Workplan:** [`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`](../../../../execution_plan/2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 2
**Dispatch:** [`docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md`](../../../../execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md)
**Spec:** V3 §3 G2 + §5 (HMAC-SHA256, 4 fail-mode audit, server-side only, verify order: signature first then hash)
**Runbook:** [`docs/runbooks/replay_signing_key_rotation.md`](../../../../runbooks/replay_signing_key_rotation.md) §6 (4 fail-mode handling)
**Acceptance binding:** V3 §12 #2 — `signature_verify` 4 fail-mode unit test

---

## 1. 任務摘要

實作 REF-20 Paper Replay Lab 的 server-side HMAC-SHA256 manifest 簽名模組（Rust 正規 + Python 鏡像），並用 in-tree fixture 強制跨語言 byte-equal HMAC 不變量。

**核心交付：**
1. **Rust 模組** `rust/openclaw_engine/src/replay/manifest_signer.rs`（697 LOC）
2. **Python 鏡像** `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py`（396 LOC）
3. **Cross-language fixture** `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/`（11 file：1 key + 1 fingerprint + 3 manifest body + 3 golden sig + 3 golden hash + README）
4. **Rust integration test** `tests/replay_manifest_signer_xlang_consistency.rs`（285 LOC，8 test）
5. **Python integration test** `tests/replay/test_manifest_signer_xlang_consistency.py`（416 LOC，13 test）

**4 fail-mode 各 1 unit test PASS（雙端）：**
- `signature_mismatch`（HMAC byte mismatch）
- `manifest_hash_mismatch`（body 與 declared hash 不符，signature 仍對）
- `key_missing`（fingerprint 不在 archive）
- `key_expired`（fingerprint 在 archive 但 status ∈ {expired, compromised}）

**V3 §5 verify-order invariant 強制：** 先 signature 後 manifest hash（同時 tamper 兩者必先報 SignatureMismatch）。

---

## 2. 修改清單

| 路徑 | 變更 | LOC |
|---|---|---|
| `rust/openclaw_engine/src/replay/manifest_signer.rs` | NEW | 697 |
| `rust/openclaw_engine/src/replay/mod.rs` | M (+11) | 28 → 39 |
| `rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs` | NEW | 285 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/key.hex` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/fingerprint.txt` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_1.json` | NEW | 1 (54 bytes) |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_1.sig` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_1.hash` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_2.json` | NEW | 1 (91 bytes) |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_2.sig` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_2.hash` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_3.json` | NEW | 1 (80 bytes) |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_3.sig` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/manifest_3.hash` | NEW | 1 |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/README.md` | NEW | 56 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/__init__.py` | NEW | 43 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py` | NEW | 396 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_manifest_signer_xlang_consistency.py` | NEW | 416 |

**TOTAL: 7 source/code file（含 mod.rs M）+ 11 fixture file = 18 file changed**

---

## 3. 關鍵 diff（Rust core）

```rust
// V3 §5 4 fail-mode 枚舉
pub enum SignatureFailMode {
    ManifestHashMismatch,
    SignatureMismatch,
    KeyMissing,
    KeyExpired,
}

// V3 §5 verify-order invariant: 先 signature 後 manifest hash
pub fn verify<A: KeyArchive>(
    &self,
    manifest_canonical: &[u8],
    manifest_declared_hash: &str,
    signature_hex: &str,
    fingerprint: &str,
    archive: &A,
) -> Result<(), SignatureFailMode> {
    // Step 1: archive lookup gate (KeyMissing if absent)
    let status = match archive.lookup_status(fingerprint) {
        Some(s) => s,
        None => return Err(SignatureFailMode::KeyMissing),
    };
    // Step 2: archive status gate (KeyExpired if !permits_verify)
    if !status.permits_verify() {
        return Err(SignatureFailMode::KeyExpired);
    }
    // Step 3: signature first (V3 §5 順序不變量)
    let expected_sig = self.sign(manifest_canonical);
    if !constant_time_eq(expected_sig.as_bytes(), signature_hex.as_bytes()) {
        return Err(SignatureFailMode::SignatureMismatch);
    }
    // Step 4: manifest hash second
    let actual_body_hash = compute_body_hash(manifest_canonical);
    if !constant_time_eq(
        actual_body_hash.as_bytes(),
        manifest_declared_hash.as_bytes(),
    ) {
        return Err(SignatureFailMode::ManifestHashMismatch);
    }
    Ok(())
}
```

Python 鏡像：`raise ValueError(SignatureFailMode.X.value)`，caller catch + `e.args[0]` 對 4 個字串 label 比對寫 audit row。

---

## 4. 治理對照（CLAUDE.md §七 + V3 §5 invariant）

### 跨平台兼容性（§七 強制）
- ✅ 0 hardcoded `/home/ncyu` 或 `/Users/<name>` literal in source（1 hit on Chinese rule explanation comment in test，符合 §七 rule 1 例外）
- ✅ Python test 用 `OPENCLAW_REPLAY_FIXTURE_DIR` env var 覆寫 + `OPENCLAW_BASE_DIR` fallback + dev relative path 三層 fallback
- ✅ Rust integration test 用 `env!("CARGO_MANIFEST_DIR")` 推導 fixture path
- ✅ Mac + Linux 均可跑

### 雙語注釋（§七 強制）
- ✅ 6 個新檔每一個都有 MODULE_NOTE 雙語 block
- ✅ 所有 `pub fn` / `def` / class / `impl` 都有 docstring + inline 雙語注釋
- ✅ 4 fail-mode enum variant 各有雙語注釋（為什麼存在 + audit label + 觸發條件）
- ✅ verify-order invariant 雙語注釋明寫「先 signature 後 hash」+ 反例

### 硬邊界守則（§七）
- ✅ `max_retries / live_execution_allowed / execution_authority / system_mode` 0 hit
- ✅ `auth_signing_key` 0 hit on new files（V3 §5 separation invariant 守住）
- ✅ `GovernanceHub / ipc_server / build_exchange_pipeline / decision_lease` 0 production code hit（2 hit on negation doc comments declaring red-line）

### LOC budget（§九）
- ✅ Rust manifest_signer.rs **697** LOC < 800 warn / 1500 hard
- ✅ 其他新檔均 < 500 LOC
- ✅ 不需 §九 singleton 登記（ManifestSigner 是 instance class，非 module-level mutable global）

### V3 §5 invariant 守則
- ✅ Algorithm = HMAC-SHA256（hardcode）
- ✅ Server-side only signing（無 client-supplied sig 接受路徑）
- ✅ Key path hardcode `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`
- ✅ Verify order: signature first, manifest hash second（雙端 unit test 強制 + integration test 強制）
- ✅ 4 fail-mode audit label 不變：`signature_mismatch / manifest_hash_mismatch / key_missing / key_expired`

### Wave 2 dispatch §2 ambiguity #2 守則
- ✅ tokio 不 import（替代：完全同步邏輯，本模組無 async primitive）
- ✅ 無 fixture loader / IPC / dispatch / live exchange 依賴

---

## 5. 驗證

### Rust（cargo）
```
cargo check -p openclaw_engine --tests           → PASS（0 new warning）
cargo test --lib replay::manifest_signer::       → 10/10 PASS
cargo test --test replay_manifest_signer_xlang_consistency  → 8/8 PASS
cargo test --lib live_authorization              → 18/18 PASS（sibling 0 regression）
```

### Python（pytest）
```
pytest tests/replay/test_manifest_signer_xlang_consistency.py -v   → 13/13 PASS
```

### Cross-language byte-equal HMAC 驗證
```
Fixture key (32 bytes) → sha256[:16] fingerprint = 4773d12e2371bb93

manifest_1.json (54 bytes)
  Rust   sign() → a208547718a2e2925311380c928f42e36c21b0b3cedf780d8b773d25f1bd35d3
  Python sign() → a208547718a2e2925311380c928f42e36c21b0b3cedf780d8b773d25f1bd35d3
  ✅ byte-equal

manifest_2.json (91 bytes)
  Rust   sign() → c5426d518edfffa4dc405cb5b8d393ae3aafdfd7a6ea95c04ae7e76c1b7a43c1
  Python sign() → c5426d518edfffa4dc405cb5b8d393ae3aafdfd7a6ea95c04ae7e76c1b7a43c1
  ✅ byte-equal

manifest_3.json (80 bytes)
  Rust   sign() → a986f4f7c56cb702c810461db69abd25bcf377f22c2869b58a9316fb965a71de
  Python sign() → a986f4f7c56cb702c810461db69abd25bcf377f22c2869b58a9316fb965a71de
  ✅ byte-equal
```
**Tolerance: 0 bytes（HMAC-SHA256 byte-exact，非 1e-4 浮點容差）**

---

## 6. 不確定之處 / Ambiguity（給 E2 + E3 review）

### A. KeyArchive trait 設計選擇（V042 未 land 處置）
- 採 trait/ABC 抽象 + ship `InMemoryKeyArchive` for unit test，待 Wave 3 R20-P2a-S4 落地 SQL-backed impl
- 替代設計：直接 hardcode SQL query 進 manifest_signer.rs，但這會強迫 Wave 2 P2a-S2 阻塞等 V042 — 違反 Wave 2 dispatch 並行原則
- E2 review 焦點：trait signature `lookup_status(fingerprint) -> Option<KeyStatus>` 是否足夠 future-proof（Wave 3 SQL impl 可能需要 `last_used_at` / `last_verified_count` etc）— 我傾向不擴 signature，這些 metadata 走 audit row 寫入而非 lookup return value

### B. fingerprint algorithm 雙向對齊
- helper script `generate_replay_signing_key.sh` line 91/93/111 算 SHA256 over **file contents**（含 `\n`）
- 本實作算 SHA256 over **raw 32 bytes**（hex decode 後）
- 兩者結果不同
- 設計選擇：本實作的 raw bytes fingerprint 為內部 invariant（V042 archive row 也存此值）
- E3 review 焦點：runbook §3.2 step 2 操作員 1Password 紀錄的 fingerprint 該用哪一個算法？我建議統一成 raw bytes fingerprint（runbook 改 + helper script 第 111 行的 NEW_FP 算法改），同 commit 不做以避免擴大 diff
- **建議：E3 在 review 時加 task ticket 給 R20-P2a-S1 sub-agent / 修 runbook，不阻塞 P2a-S2 land**

### C. `#[doc(hidden)] pub fn new_from_bytes_for_test`
- 第一輪用 `#[cfg(test)]` 但 integration test link 看不到 → 改 `#[doc(hidden)]`
- 替代設計：用 `cfg(any(test, feature = "test_helpers"))` + 顯式 feature flag → 更嚴格但需要 Cargo.toml 改
- E2 review 焦點：是否要求改成 feature flag？我建議目前 doc(hidden) 足夠（生產 caller 看不到 + 文件不出現 + naming `_for_test` 後綴清楚標 intent）

### D. Verify-order test cover invariant 範圍
- 加了「同時 tamper sig + hash」test（必先報 SignatureMismatch）
- 加了「archive gate before sig gate」test（KeyMissing/KeyExpired 必先報）
- 沒有「step 4 路徑 isolation」test（即「sig 對但 hash 不符」單獨 case）— 但這個 case 是 `fail_mode_manifest_hash_mismatch_with_fixture` 的設計意圖，已覆蓋
- E2 review 焦點：是否需加更多 order-permutation test？我傾向當前覆蓋足夠（4 fail-mode × 1 + verify-order × 2 = 6 test，加 happy path = 7，足以證 invariant）

### E. Python `_constant_time_eq` 實作
- 用 stdlib `hmac.compare_digest`（已 audit 過）
- E3 security review 焦點：是否需要自己 hand-roll？我反對，stdlib 是正確選擇

---

## 7. Operator 下一步

### 強制工作鏈
1. **E2 code review**（必跑）：對齊 Rust + Python implementation pair（特別注意 verify-order 雙端對齊 + 4 fail-mode label string 一致）
2. **E3 security review**（必跑）：HMAC-SHA256 algorithm 強制 / constant-time compare / key separation invariant / fingerprint algorithm 一致性
3. **E4 regression test**（必跑）：跑 Linux 端 Rust full test suite + Python control_api_v1 full test suite，確認 0 regression
4. **PM sign-off + commit + push**（PM 統一）

### Commit message draft
```
feat(replay): manifest_signer Rust+Python HMAC-SHA256 module + 4 fail-mode tests (Wave 2 P2a-S2)

REF-20 Wave 2 R20-P2a-S2 — server-side HMAC-SHA256 manifest signer for
the Paper Replay Lab. Implements V3 §3 G2 + §5 contract with 4 fail-mode
audit (signature_mismatch / manifest_hash_mismatch / key_missing /
key_expired) and verify-order invariant (signature first, manifest hash
second).

Cross-language byte-equal HMAC tag verified via in-tree fixture (1 key +
3 manifest bodies + golden sigs/hashes); Rust + Python sign() produce
identical hex tags for the same canonical bytes. Tolerance: 0 bytes
(HMAC byte-exact, not 1e-4 floating-point IPC tolerance).

KeyArchive trait/ABC abstracts V042 replay_signing_keys lookup; ships
InMemoryKeyArchive for Wave 2 unit testing. Wave 3 R20-P2a-S4 will land
SQL-backed impl without changing this module.

NOT in scope: archive INSERT (V042 reserved), cron rotation (R20-P2a-S1),
FastAPI route wiring (R20-P2a-S3), GovernanceHub/Decision Lease coupling
(red-line).

Tests:
- cargo test --lib replay::manifest_signer:: → 10/10 PASS
- cargo test --test replay_manifest_signer_xlang_consistency → 8/8 PASS
- pytest tests/replay/test_manifest_signer_xlang_consistency.py → 13/13 PASS
- live_authorization sibling test 18/18 PASS (0 regression)

V3 §12 acceptance #2 binding: signature_verify 4 fail-mode unit test PASS

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

### 後續 Wave 工作
- Wave 3 **R20-P2a-S4** sub-agent：用本模組的 trait + Rust SQL DbPool 實作 SQL-backed `KeyArchive`（讀 V042 `replay.replay_signing_keys`），同時實作 `verify_replay_evidence_and_insert()` PL/pgSQL function。**不需修本模組**。
- Wave 3 **R20-P2b-S7** sub-agent：在 isolated `replay_runner` binary 內 wire `ManifestSigner::verify()` 到 startup gate（V3 §6.2 fail-closed）+ 5 min ticker re-verify wiring。**不需修本模組**。
- **R20-P0-T8 follow-up（runbook 改）**：建議 R20-P2a-S1 sub-agent / runbook owner 評估是否將 helper script 第 111 行 NEW_FP 算法改成 raw bytes 版本，與本模組對齊（不阻塞 P2a-S2 land）。

---

E1 IMPLEMENTATION DONE: 待 E2 + E3 審查 + E4 回歸（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_p2a_s2_manifest_signer.md`）
