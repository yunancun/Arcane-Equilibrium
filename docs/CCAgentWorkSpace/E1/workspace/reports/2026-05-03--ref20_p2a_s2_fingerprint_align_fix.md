# REF-20 Wave 2 P2a-S2 — Fingerprint Algorithm Surgical Fix-Up

**Date:** 2026-05-03
**Owner:** E1
**Task:** R20-P2a-S2 follow-up — align `compute_key_fingerprint` (Rust + Python) with helper script `generate_replay_signing_key.sh`
**Trigger:** PM Wave 2 Batch 1 integration review found algorithm divergence between helper script (file content + `\n` sha256) and module (raw decoded bytes sha256). 100% `key_missing` runtime fail-mode if not fixed (operator records script fingerprint to 1Password vault; runtime computes module fingerprint to look up archive — two values would never match).
**Spec:** REF-20 V3 §3 G2 + §5 / Helper script line 91/93/111 (`openssl dgst -sha256 -hex < $KEY_FILE | awk '{print $NF}' | cut -c1-16`)
**Sub-agent original report:** `2026-05-03--ref20_p2a_s2_manifest_signer.md` §6.B (sub-agent acknowledged divergence and pushed to runbook fix; PM decision = opposite direction, fix module to match script).

---

## 1. 任務摘要

對 P2a-S2 surgical fix：把 Rust + Python `compute_key_fingerprint` 從「對 raw decoded 32 bytes 做 sha256」改為「對 file content bytes（含 trailing `\n`）做 sha256」，鏡像 helper script 的算法（script 是 operator-facing canonical reference，產 fingerprint 寫入 1Password vault；runtime 必算同一值才能查 V042 archive）。

**核心修正：**
1. `compute_key_fingerprint(key_file_content: &[u8]) -> String` 算法不變（仍是 sha256[:16]），但**輸入語意改變** — 從「decoded raw bytes」改為「file content bytes（含 newline）」。
2. `ManifestSigner::new()` constructor 把 disk read 結果同時用作（a）file content bytes → fingerprint 計算，（b）trim 後 hex decode → HMAC key。兩條 derivation 路徑分離。
3. `from_bytes_for_test` / `new_from_bytes_for_test` 簽名不變（仍接 raw 32 bytes + fingerprint），caller 在整合測試 fixture loader 中以 file content bytes 算 fingerprint 後傳入。
4. Fixture `fingerprint.txt` 從 `4773d12e2371bb93`（舊算法）→ `da0d3b33336d12fb`（新算法 = 對齊 helper script）。
5. 測試 fixture loader（Rust + Python）改 `read_bytes()` / `fs::read()` + 對 file content bytes 算 fingerprint。

**結果：** Script + fixture + module 三者完全對齊，0 sibling regression。

---

## 2. 修改清單（6 file）

| 路徑 | 變更 | 性質 |
|---|---|---|
| `rust/openclaw_engine/src/replay/manifest_signer.rs` | 修 `compute_key_fingerprint` doc + param rename (`key_bytes`→`key_file_content`)；修 `ManifestSigner::new()` constructor 拆兩條 derivation；修 `new_from_bytes_for_test` doc；修 unit test fixture helper `fixture_signer()`；修 `fingerprint_matches_helper_script` test doc | M |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py` | 修 `compute_key_fingerprint` doc + param rename；修 `__init__` constructor 用 `read_bytes()` + 拆兩條 derivation；修 `from_bytes_for_test` doc | M |
| `rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs` | 修 `load_fixture_signer()` 用 `fs::read` 讀 file content bytes | M |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_manifest_signer_xlang_consistency.py` | 修 `fixture_signer` pytest fixture 用 `read_bytes()` | M |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/fingerprint.txt` | 從 `4773d12e2371bb93` → `da0d3b33336d12fb`（新算法值） | M |
| `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/README.md` | 修 fingerprint description 表格 + regenerate snippet（加 openssl one-liner + Python file_content 路徑） | M |

**0 file added / 0 file deleted / 0 module new / 0 dependency added**。

---

## 3. 關鍵 diff（Rust core）

### `compute_key_fingerprint` (Rust)
```rust
// BEFORE: param `key_bytes` 暗示 raw decoded 32 bytes（與 script 不一致）
pub fn compute_key_fingerprint(key_bytes: &[u8]) -> String { ... }

// AFTER: param `key_file_content` 明確語意 + 加大量雙語注釋說明對齊 script
pub fn compute_key_fingerprint(key_file_content: &[u8]) -> String {
    // sha256 over input as-is (不 trim、不 hex decode)
    let mut hasher = Sha256::new();
    hasher.update(key_file_content);
    let digest = hasher.finalize();
    let full_hex = hex::encode(digest);
    full_hex[..16].to_string()
}
```

### `ManifestSigner::new()` constructor (Rust)
```rust
// BEFORE
let raw = fs::read_to_string(&key_path)?;
let key_hex = raw.trim();
let key_bytes = hex::decode(key_hex)?;
let actual_fp = compute_key_fingerprint(&key_bytes);  // ❌ raw decoded bytes

// AFTER
let raw = fs::read_to_string(&key_path)?;
let file_content_bytes = raw.as_bytes().to_vec();      // ← 給 fingerprint
let key_hex = raw.trim();
let key_bytes = hex::decode(key_hex)?;                 // ← HMAC key (32 bytes)
let actual_fp = compute_key_fingerprint(&file_content_bytes);  // ✅ file content
```

### Python `__init__` constructor
```python
# BEFORE
raw = key_path.read_text(encoding="utf-8").strip()    # ← 已 strip
key_bytes = bytes.fromhex(raw)
actual_fp = compute_key_fingerprint(key_bytes)        # ❌ raw decoded bytes

# AFTER
file_content_bytes = key_path.read_bytes()            # ← 含 trailing \n
raw = file_content_bytes.decode("utf-8").strip()
key_bytes = bytes.fromhex(raw)                        # ← HMAC key (32 bytes)
actual_fp = compute_key_fingerprint(file_content_bytes)  # ✅ file content
```

### Fixture `fingerprint.txt`
```
- 4773d12e2371bb93  (舊：sha256 over raw 32 bytes)
+ da0d3b33336d12fb  (新：sha256 over file content bytes 含 \n)
```

---

## 4. 治理對照（CLAUDE.md §七 + V3 §5 invariant）

### 跨平台兼容性（§七 強制）
- ✅ 0 hardcoded `/home/ncyu` 或 `/Users/<name>` literal 進 source（grep 1 hit 是 §七 規則例外的 Chinese rule explanation comment）
- ✅ Rust integration test 用 `env!("CARGO_MANIFEST_DIR")` 推導 fixture path（不變）
- ✅ Python test 三層 fallback 不變（`OPENCLAW_REPLAY_FIXTURE_DIR` env var → `OPENCLAW_BASE_DIR` → relative）

### 雙語注釋（§七 強制）
- ✅ `compute_key_fingerprint` 函數 doc 大量擴充中英對照（含 algorithm reference 到 script 行號）
- ✅ `ManifestSigner::new()` doc 加 invariant 雙語塊「HMAC key vs fingerprint 兩條獨立 derivation」
- ✅ `new_from_bytes_for_test` / `from_bytes_for_test` doc 加 caller 注意事項雙語
- ✅ unit test `fingerprint_matches_helper_script` 整段注釋重寫，明寫對齊 script + 為何重要
- ✅ 新增 inline 雙語注釋說明 file_content_bytes 語意

### 硬邊界守則（§七）
- ✅ `max_retries / live_execution_allowed / execution_authority / system_mode` 0 hit
- ✅ `auth_signing_key` 0 hit on modified files（V3 §5 separation invariant 守住）
- ✅ `GovernanceHub / ipc_server / build_exchange_pipeline / decision_lease` 0 production code hit

### LOC budget（§九）
- ✅ Rust manifest_signer.rs **761** LOC（697→761，+64 LOC for 注釋擴充）< 800 warn / 1500 hard
- ✅ Python manifest_signer.py **443** LOC（396→443，+47 LOC for 注釋擴充）< 800 warn
- ✅ 不需 §九 singleton 登記（無新 singleton）

### V3 §5 invariant 守則
- ✅ Algorithm = HMAC-SHA256（不變）
- ✅ Server-side only signing（不變）
- ✅ Key path hardcode `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`（不變）
- ✅ Verify order: signature first, manifest hash second（不變，所有 verify-order test 仍 PASS）
- ✅ 4 fail-mode audit label 不變
- ✅ **新增**：fingerprint algorithm 與 helper script 對齊（V3 §5 contract 沒明寫此細節，但 R20-P0-T8 helper script 是 operator-facing canonical reference 必須對齊）

---

## 5. 驗證

### Test command 結果（4 條全 PASS）

```
cargo test -p openclaw_engine --lib replay::manifest_signer::
  → 10/10 PASS  ✅

cargo test -p openclaw_engine --test replay_manifest_signer_xlang_consistency -- --nocapture
  → 8/8 PASS    ✅

pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_manifest_signer_xlang_consistency.py -v
  → 13/13 PASS  ✅

cargo test -p openclaw_engine --lib live_authorization
  → 18/18 PASS  ✅ (sibling regression 0 break)
```

### Shell smoke test：script vs fixture 一致

```bash
$ openssl dgst -sha256 -hex < rust/openclaw_engine/tests/fixtures/replay_manifest_signer/key.hex \
    | awk '{print $NF}' | cut -c1-16
da0d3b33336d12fb

$ cat rust/openclaw_engine/tests/fixtures/replay_manifest_signer/fingerprint.txt | tr -d '\n'
da0d3b33336d12fb

RESULT: PASS — script fingerprint == fixture fingerprint == module-computed fingerprint
```

### Fingerprint before/after 對比

| 對象 | 舊 fingerprint | 新 fingerprint |
|---|---|---|
| Module `compute_key_fingerprint(decoded_32_bytes)` | `4773d12e2371bb93` | n/a (input semantics 改了) |
| Module `compute_key_fingerprint(file_content_bytes)` | n/a | `da0d3b33336d12fb` |
| Helper script `openssl dgst < key.hex` | `da0d3b33336d12fb` | `da0d3b33336d12fb`（不變，本來就對） |
| Fixture `fingerprint.txt` | `4773d12e2371bb93` | `da0d3b33336d12fb`（同步更新） |

**結論：** Module 對齊 script。Operator 寫入 1Password vault 的 fingerprint（script 算）與 runtime 查 V042 archive 用的 fingerprint（module 算）現在一致 → 修復 100% `key_missing` runtime fail-mode 風險。

### Cross-language byte-equal HMAC 驗證

3 個 fixture manifest 的 golden signature 不變（HMAC tag 與 fingerprint 算法獨立 — HMAC 用 raw 32 bytes，fingerprint 用 file content bytes，兩條 derivation 無耦合）。Rust + Python sign 結果仍 byte-equal：

```
manifest_1.json  Rust+Python sign() = a208547718a2e2925311380c928f42e36c21b0b3cedf780d8b773d25f1bd35d3 ✅
manifest_2.json  Rust+Python sign() = c5426d518edfffa4dc405cb5b8d393ae3aafdfd7a6ea95c04ae7e76c1b7a43c1 ✅
manifest_3.json  Rust+Python sign() = a986f4f7c56cb702c810461db69abd25bcf377f22c2869b58a9316fb965a71de ✅
```

Tolerance: 0 bytes（不變）。

---

## 6. 不確定之處 / Ambiguity（給 E2 + E3 review）

### A. Test code 是否 hardcode 過舊算法的 expected fingerprint？

**答**：否。Test code 沒 hardcode `4773d12e2371bb93` literal，所有 expected value 都從 `fingerprint.txt` fixture 讀（`fs::read_to_string("fingerprint.txt").trim()`）。改 fixture 後 test 自動對齊。Rust unit test `FIXTURE_KEY_HEX` const 仍是 `00112233...eeff`（key 內容不變），新算法在 `fixture_signer()` helper 中 inline 算 fingerprint。

### B. `from_bytes_for_test` / `new_from_bytes_for_test` 簽名是否需改？

**沒改**。簽名仍 `(key_bytes: Vec<u8>, fingerprint: String)`。理由：
- HMAC key 永遠是 raw 32 bytes（與 fingerprint 來源無關），這語意正確
- fingerprint 是 caller-precomputed value（從 file content bytes / fixture / 1Password 取），constructor 不重算 — 這個契約沒變
- 整合測試只需在 fixture loader 中改 `compute_key_fingerprint(file_content)` 而非 `compute_key_fingerprint(decoded_bytes)`

替代設計（拒絕）：把 constructor 簽名改成 `(file_content_bytes, fingerprint)` 然後內部 derive HMAC key — 會逼測試方多做一次 hex decode + 改變 production caller pattern（pa-S4 SQL archive impl 預期傳 raw 32 bytes 而非 file content）。當前設計更穩。

### C. 是否需更新 helper script？

**沒改**。PM 指示「helper script 是 source of truth, fix module to match」。Script 算法本來正確，現在 module 對齊它，runbook §3.2 step 2/3 操作員流程不需改（operator 仍跑 `bash generate_replay_signing_key.sh demo` → script 印 fingerprint → operator 寫入 1Password → runtime 從同 fingerprint 查 V042 archive 命中）。

**Sub-agent 原 §6.B push back（建議改 runbook+script 對齊 module）已 supersede**。本 commit 直接解決 runtime fail-mode，0 runbook/script churn。

### D. Production caller 是否需動？

**沒 production caller 需動**。Wave 2 P2a-S2 是 standalone module；目前 0 production code 呼叫 `ManifestSigner::new()`（Wave 3 R20-P2a-S4 SQL archive impl + R20-P2b-S7 isolated runner 才會接線）。本 fix 只改 internal derivation；caller-facing API（`new(path, fingerprint)` / `sign(canonical)` / `verify(...)`) 100% 不變。

### E. Python integration test fixture loader 用 `read_bytes()` 是否 cross-platform safe？

**安全**。Mac + Linux 都讀同一 `key.hex`（`printf '%s\n'` 寫的 65 bytes：64 hex + LF）。Windows 不在範圍（CLAUDE.md 跨平台範圍 = Mac + Linux），所以不擔心 CRLF。如未來支援 Windows 需在 fixture loader 加 `b"\r\n" → b"\n"` normalization，但這不在本 commit 範圍。

---

## 7. PM commit message draft

```
fix(replay): align manifest_signer fingerprint with helper script (Wave 2 P2a-S2 follow-up)

REF-20 Wave 2 R20-P2a-S2 surgical fix-up. Root-cause: helper script
`generate_replay_signing_key.sh` line 91/93/111 computes fingerprint as
sha256 over key file content bytes (including trailing `\n` from
`printf '%s\n'`); the original module implementation computed sha256 over
raw decoded 32 bytes. Operator records script fingerprint to 1Password
vault; runtime computes module fingerprint to look up V042 archive — two
values would never match, leading to 100% `key_missing` runtime fail-mode.

Fix: change `compute_key_fingerprint(key_file_content)` semantics to
sha256 over file content bytes (mirrors `openssl dgst -sha256 -hex
< $KEY_FILE`). Constructor `ManifestSigner::new()` now derives HMAC key
(decoded 32 raw bytes) and fingerprint (sha256 over file content) on two
independent paths from the same disk read. Test fixture
`fingerprint.txt` regenerated from `4773d12e2371bb93` →
`da0d3b33336d12fb` to match new algorithm.

API contract unchanged: `new(path, fingerprint)` / `sign(canonical)` /
`verify(...)` signatures stable; HMAC tag computation byte-identical
(uses raw 32 bytes, decoupled from fingerprint derivation). 0 production
caller affected (none exist yet; Wave 3 R20-P2a-S4 SQL archive impl will
be the first).

Tests:
- cargo test -p openclaw_engine --lib replay::manifest_signer:: → 10/10 PASS
- cargo test -p openclaw_engine --test replay_manifest_signer_xlang_consistency → 8/8 PASS
- pytest tests/replay/test_manifest_signer_xlang_consistency.py → 13/13 PASS
- cargo test --lib live_authorization → 18/18 PASS (sibling 0 regression)
- shell smoke: openssl dgst < key.hex == fingerprint.txt == da0d3b33336d12fb ✅

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 8. Operator 下一步

### 強制工作鏈（CLAUDE.md §七 + §八）

1. **E2 code review**（必跑）— 焦點：
   - HMAC key derivation vs fingerprint derivation 兩條獨立路徑正確分離（無互相污染）
   - `compute_key_fingerprint` 新 param name `key_file_content` 語意清楚
   - 雙端 docstring 對齊（中英對照覆蓋同一語義）
   - 0 production caller 受影響（Wave 3 R20-P2a-S4 SQL archive 未 land 不會撞）
   - Sibling test `live_authorization` 18/18 仍 PASS

2. **E3 security review**（建議跑）— 焦點：
   - fingerprint algorithm 對齊 script 不引入新攻擊面（仍 sha256[:16]，仍 16 hex chars，碰撞概率仍 ~1/2^64）
   - HMAC key 仍是 raw 32 bytes（256-bit），不變
   - V3 §5 key separation invariant 仍守住（auth_signing_key vs replay_signing_key 0 共用）

3. **E4 regression test**（隱式 via xlang test + sibling test 已跑）— 雙端 byte-equal HMAC 不變量仍守住

4. **PM sign-off + commit + push**（PM 統一）

### 後續 Wave 工作（未變）

- Wave 3 **R20-P2a-S4** sub-agent：用本模組 trait + Rust SQL DbPool 實作 SQL-backed `KeyArchive`（讀 V042 `replay.replay_signing_keys`）；同時實作 `verify_replay_evidence_and_insert()` PL/pgSQL function。**不需修本模組**。
- Wave 3 **R20-P2b-S7** sub-agent：在 isolated `replay_runner` binary 內 wire `ManifestSigner::verify()` 到 startup gate + 5 min ticker re-verify wiring。**不需修本模組**。

### Runbook 確認（無需動）

`docs/runbooks/replay_signing_key_rotation.md` §3.2 step 2/3 操作員流程 = 跑 `bash generate_replay_signing_key.sh <env>` → script 印 fingerprint → operator 寫入 1Password vault。**Runbook 描述 fingerprint 來源 = script 算的值**（這已是事實），所以 runbook 不需改 — 模組現在對齊它了。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_p2a_s2_fingerprint_align_fix.md`）
