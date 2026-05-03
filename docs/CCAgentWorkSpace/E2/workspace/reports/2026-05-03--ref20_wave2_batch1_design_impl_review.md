# REF-20 Wave 2 Batch 1 — E2 Design + IMPL + Adversarial Review

**Date**: 2026-05-03
**Reviewer**: E2 (Senior Backend Code Reviewer + Adversarial Auditor)
**Verdict**: **CONDITIONAL PASS to E4** — 0 CRITICAL / 0 HIGH / 5 MEDIUM / 4 LOW
**Commits reviewed**:
- `9879eeb` feat(replay-ui): P1 frontend bundle (U1+U7+U9)
- `ce665b0` feat(replay): P2a-S1 signing key cron
- `40ebc19` feat(replay): P2a-S2 manifest_signer + fingerprint fix

**Upstream contracts**:
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §3-§5 §8
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G2/G7/G8/G9/G10 + §5 + §12
- `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md` §2/§7/§8/§9/§11
- `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §2 (5 ambiguity decisions) + §3 + §5

---

## 0. TL;DR

5 task / 3 commits / +5,342 LOC inserted (1,087 frontend + 1,461 cron + 2,794 signer)。所有測試 PASS：

| Test bucket | Count | Result |
|---|---|---|
| Rust unit (replay::manifest_signer) | 10 | PASS |
| Rust integration (xlang fixture) | 8 | PASS |
| Python pytest (manifest_signer xlang) | 13 | PASS |
| Python pytest (S1 cron) | 7 | PASS |
| Sibling regression (live_authorization) | 18 | PASS (0 regression) |
| **Total** | **56** | **56 PASS / 0 FAIL** |

Hard boundary 安全：0 真實 code 改動到 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` / `decision_lease` 等 governance 邊界。0 risk_config / 0 SQL migration / 0 strategy params / 0 TOML 改動。

PASS 條件：5 MEDIUM finding 中 4 條為 stale doc / minor design ambiguity（不 block runtime correctness），1 條為 SQL string interpolation pattern（hardcoded 值無實際 injection 風險，但設計一致性建議）。所有 4 LOW 為 minor cleanup / micro inefficiency。

**E2 整合判定**：可往 E4 推進 regression smoke。E1/E1a/TW retrofit 5 MEDIUM 可在 Wave 2 closure 前的 fix-up 並推或 deferred 到 Wave 3。

---

## 1. 必查項對照表

### 1.1 Frontend bundle (commit 9879eeb)

| 項目 | 結果 |
|---|---|
| `tab-paper.html` parses (HTMLParser) | ✅ 0 error |
| 1 `id="paper-mode-badges"` (no dup) | ✅ 1 element + 1 caller (getElementById) |
| 1 `i18n_zh.js` script tag in tab-paper.html | ✅ 1（line 11） |
| 4 sub-tab nav with 1 active + 3 disabled | ✅ Session active；Replay/Compare/Handoff disabled |
| Mode badge slot rendered (P1 mock seed all unknown/none per UX §7) | ✅ DOMContentLoaded mock seed line 747-758 |
| `execution_confidence='none'` 防認知欺詐 (4 visual signals) | ✅ 灰底 (rgba 139,148,158) + ⚠ icon + bilingual tooltip + 紅外框 (`var(--red)` border + box-shadow) |
| A11y baseline (role=tablist/tab/tabpanel + aria-disabled + focus ring) | ✅ 11 aria-* + role + tabindex attributes |
| XSS-safe (`grep innerHTML.*\${` 0 hit on new code) | ✅ 0 hit (existing `ocExplain()` calls 不在 Wave 2 範圍) |
| Vanilla JS (no React / framework lift) | ✅ pure ES5+/ES2015 |
| 雙語 comment (CLAUDE.md §七) | ✅ MODULE_NOTE EN+中 in i18n_zh.js / common.js / app-paper.js |
| File size: common.js < 1500 / tab-paper.html < 1500 / app-paper.js < 1200 | ✅ 1413 / 778 / 447 |
| 9 i18n 對照表 ≥3 keys each | ✅ 全 9 表（mode_badge 6 dimensions / verdict 7 / disabled_state 13 / etc.） |
| Title bilingual ("模擬重放實驗室 / Paper Replay Lab") | ✅ tab-paper.html line 6 |

### 1.2 S2 backend (commit 40ebc19)

| 項目 | 結果 |
|---|---|
| HMAC-SHA256 algorithm hardcode (V3 §5) | ✅ Rust `Hmac<Sha256>` / Python `hmac.new(..., hashlib.sha256)` |
| Verify order: signature first → manifest hash | ✅ Rust line 432-444 / Python line 428-440；2 unit test 各端 cover |
| 4 fail-mode enum (signature_mismatch / manifest_hash_mismatch / key_missing / key_expired) | ✅ Rust + Python 1:1 enum + audit_label() |
| Fingerprint algorithm aligned with helper script | ✅ Cross-verified by shell smoke `openssl dgst < key.hex` = `da0d3b33336d12fb` = fixture/fingerprint.txt = Python sha256[:16] |
| Cross-language byte-equal HMAC for 3 fixture manifests | ✅ Rust + Python xlang test 3 manifest 完全一致 |
| Test counts: 10 Rust unit + 8 Rust integration + 13 Python pytest = 31 PASS | ✅ 31/31 |
| Sibling regression: live_authorization 18/18 PASS | ✅ 0 regression |
| Forbidden symbol grep on manifest_signer.rs (acquire_lease/ipc_server/build_exchange_pipeline/GovernanceHub/exchange_dispatch) | ✅ 0 actual import；只 `//!` doc-comment "MUST NOT" 紅線聲明 (line 60-65) |
| Key separation invariant: 0 grep hit `auth_signing_key` in S2 module | ✅ 0 hit |
| HMAC key bytes (raw 32) decoupled from fingerprint (file content) | ✅ `key_bytes = hex::decode(key_hex.trim())` vs `fingerprint = sha256(file_content_bytes_with_newline)[:16]` 雙路徑分離 |
| Caller API unchanged (`ManifestSigner::new(path, fingerprint)`) | ✅ 0 production caller existing yet (Wave 3 R20-P2a-S4 first) |
| Bilingual comments | ✅ MODULE_NOTE / docstring / inline 全雙語 |

### 1.3 S1 cron (commit ce665b0)

| 項目 | 結果 |
|---|---|
| `bash -n` PASS + `python -m py_compile` PASS | ✅ 兩端 PASS |
| pytest 7/7 PASS | ✅ darwin 25.4.0 0.13s |
| Cross-platform (BSD + GNU stat/date dual branch) | ✅ shell line 191-198 stat / line 203-209 date 雙分支 |
| Idempotent (rotation_check daily dedup; cleanup natural dedup via WHERE) | ✅ rotation: `WHERE ts >= date_trunc('day', NOW()) AND payload->>'env'=...`；cleanup: `WHERE status='retired' AND retention_until<NOW()` |
| V042 graceful fallback (rotation_check uses filesystem mtime; cleanup exit 0 + log) | ✅ shell `v042_table_present` probe + Python `_v042_present(cur)` 雙端對齊 |
| Mode 0755 shell / 0644 python | ✅ rotation_check.sh 16472B 0755 / cleanup.py 13764B (default 0644) |
| 0 PG schema mutation (only SELECT + UPDATE on existing rows) | ✅ shell INSERT to learning.governance_audit_log only；Python UPDATE replay.replay_signing_keys + INSERT governance_audit_log |
| Audit row schema reuses V035 governance_audit_log | ✅ 不擴 enum；用 `event_type='audit_write_failed'` slot + payload JSONB carry alert_type |
| Bilingual comments | ✅ 4 MODULE_NOTE block (EN+中) + 雙語 inline |

### 1.4 Cross-Wave 2 Batch 1 整合

| 項目 | 結果 |
|---|---|
| Wave 2 dispatch §2 #2 tokio only `rt-multi-thread + macros` (verify by grep 0 tokio import in S2) | ✅ `grep '^use tokio\|::tokio' manifest_signer.rs` = 0 actual hit；只在 `//!` MODULE_NOTE 提及 |
| Operator 中文 dominant 偏好 reflected in title + i18n_zh + bilingual comments | ✅ tab-paper.html title 中文先；i18n_zh.js operator-facing strings 中文+technical EN |

---

## 2. Adversarial Audit (Attacker Mindset)

### 2.1 Hard boundary scan (任何 live gate mutation 紅旗)

```bash
git diff 9e0c826..40ebc19 -- '*.rs' '*.py' '*.sh' '*.js' '*.html' \
  | grep -nE '^\+.*\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease)'
# Result: 0 hit
```

✅ Wave 2 Batch 1 完全沒有改動 live execution gate。所有提及（包括 commit message / E1 reports / 雙語註釋）皆為 reference / doc-only / "MUST NOT" 紅線聲明，0 actual code mutation。

### 2.2 XSS attack surface

| Surface | 動態插入路徑 | XSS 防護 |
|---|---|---|
| Mode badge HTML（common.js `_ocRenderModeBadgePill`） | `meta.dim_label_en` / `meta.label_en` / `meta.icon` / `meta.tip_en` 全經 `ocEsc()` | ✅ Defense-in-depth |
| Class token (`oc-chip-{variant}` / `data-mode-dim`) | `meta.variant` / `meta.dim` / `meta.state` 經 `ocSanitizeClass()` | ✅ |
| `OpenClawModeBadge.render()` innerHTML | innerHTML 內容由 `_ocRenderModeBadgePill()` 產生（已過濾） | ✅ |
| `OpenClawModeBadge.update()` insertAdjacentHTML | 同上 | ✅ |
| i18n_zh.js dot-path lookup `t_zh()` | `Object.prototype.hasOwnProperty.call` guard + non-string coerce | ✅ Prototype-chain pollution prevented |
| sub-tab nav (tab-paper.html) | Static HTML buttons + `data-i18n` attrs (no dynamic insert) | ✅ |
| `i18n_zh.js` window namespace | `Object.freeze` depth-1 + sub-tables freeze | ✅ Read-only |

### 2.3 Mode badge 認知欺詐 vs UX subdoc §7 Rule 1

UX subdoc §7 規定 `execution_confidence='none'` 必 visually non-actionable，A3 §7.4 #17 強制 4 visual signals：
1. 灰底 (`background: rgba(139,148,158,0.12)`)
2. ⚠ icon
3. 紅外框 (`border: 1px solid var(--red)`)
4. bilingual tooltip

✅ Common.js line 1327-1334 CSS：

```css
.oc-mode-badge[data-confidence-none="1"] {
  background: rgba(139,148,158,0.12);
  color: var(--red);
  border: 1px solid var(--red);
  box-shadow: 0 0 0 1px rgba(248,81,73,0.35) inset;
}
```

+ Common.js line 1096 entry:
```js
none: { variant: 'bad', icon: '⚠', label_en: 'None', label_zh: '無',
        tip_en: 'Execution confidence=none — result is NOT actionable',
        tip_zh: '執行可信度為「無」— 結果不可作為實盤依據',
        danger: true },
```

`danger: true` 觸發 `dangerAttr = ' data-confidence-none="1"'` (line 1180) → CSS 紅外框 light up。aria-label 含 `(warning, not actionable)` (line 1191) for screen reader accessibility。

4 visual signals 全 covered。

### 2.4 HMAC forgery (client-supplied signature reject)

V3 §5 不變量：「server-side only / client supplied signature: rejected」。

S2 設計：
- `ManifestSigner::sign()` 是 server-side helper，caller 必持 signer instance 才能簽
- `verify()` 接 `signature_hex: &str` 但**重算 expected_sig** (`self.sign(canonical)`) 與 caller-supplied byte 比對 → forge 必失敗
- Constant-time eq 防 timing oracle (Rust `constant_time_eq` / Python `hmac.compare_digest`)

✅ Forgery attack surface 不存在 — 僅有正確 key 持有者能 produce 通過的 signature。

### 2.5 Key archive lookup race (V042 absent fallback)

V042 (`replay.replay_signing_keys`) Wave 3 R20-P2a-S4 才 land。Wave 2 Batch 1 設計：

- shell `v042_table_present()` probe：falls back to filesystem mtime + 90d 規則
- Python `_v042_present(cur)`：if False → graceful exit 0 + log
- Rust `KeyArchive trait` + `InMemoryKeyArchive`：unit test 用 in-memory；production caller (Wave 3 R20-P2a-S4) 會 plug-in SQL-backed impl

✅ Fail-closed not fail-open：
- shell V042 absent → mtime > NOW-83d → ALERT (exit 1)；mtime > NOW-90d → ALERT；fallback 仍是 fail-closed
- Python V042 absent → exit 0 with log（不 crash 但也不假冒 success；log 顯示「graceful exit; cron will become useful once V042 lands」）
- Rust verify() Step 1 `archive.lookup_status() → None` → `KeyMissing` fail-mode（fail-closed）

### 2.6 Cron false positive (rotation_check ALERT 觸發條件邊界)

shell:
```bash
ROTATION_DAYS=90
ALERT_THRESHOLD_DAYS=7
DAYS_REMAINING=$((DELTA_SECS / 86400))
if [[ $DAYS_REMAINING -le $ALERT_THRESHOLD_DAYS ]]; then  # ALERT
```

邊界測試：
| `mtime`（天前） | `due_at`（mtime+90d 後天） | `days_remaining` | 觸發 ALERT? | 預期 |
|---|---|---|---|---|
| 0 (剛 rotate) | +90d | 90 | ❌ | OK |
| 83d ago | +7d | 7 | ✅ | ALERT (≤7d) |
| 84d ago | +6d | 6 | ✅ | ALERT |
| 90d ago | 0 (just due) | 0 | ✅ | ALERT |
| 91d ago | -1 (past) | -1 | ✅ | ALERT (already overdue) |

Pytest 4 cases cover：file missing / mtime within grace / mtime past due / SECRETS_DIR missing。實測 PASS。

✅ Off-by-one 風險已 cover：`<=` operator 包含 boundary (DAYS_REMAINING=7)；`-1` past due 也 ALERT。

### 2.7 Test coverage holes (4 fail-mode 全 Rust + Python 對應；verify-order 邊界)

| Fail mode | Rust unit | Rust integration | Python pytest |
|---|:-:|:-:|:-:|
| `signature_mismatch` | ✅ | ✅ | ✅ |
| `manifest_hash_mismatch` | ✅ | ✅ | ✅ |
| `key_missing` | ✅ | ✅ | ✅ |
| `key_expired` | ✅ (含 Compromised status alias) | ✅ | ✅ |
| Verify-order: signature before hash (both tampered) | ✅ | ✅ | ✅ |
| Verify-order: archive gates before signature (both correct) | ✅ | ✅ | ✅ |
| Retired status still verifies (180d window) | ✅ | (cover by happy + retired test) | ✅ |
| Cross-language byte-equal HMAC for 3 fixtures | (cover by integration) | ✅ | ✅ |

✅ 8 unique test scenarios × 3 buckets = 24 logically-distinct cases，全 PASS。

### 2.8 Symbol leakage (manifest_signer.rs 是否誤 import live engine 模組)

```bash
grep -nE '^use\s' rust/openclaw_engine/src/replay/manifest_signer.rs
```

```rust
use hmac::{Hmac, Mac};
use sha2::{Digest, Sha256};
use std::fs;
use std::path::PathBuf;
```

✅ 4 actual `use` statements — 全為 std + crypto crate；0 reference to engine internals (`crate::ipc_server` / `crate::governance` / `crate::dispatch` / `crate::lease` 等)。

### 2.9 Cross-platform path scan

```bash
grep -E '/home/ncyu|/Users/[^/]+/' rust/openclaw_engine/src/replay/manifest_signer.rs \
  rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_manifest_signer_xlang_consistency.py \
  helper_scripts/cron/replay_key_rotation_check.sh \
  helper_scripts/cron/replay_key_archive_cleanup.py
```

唯一命中：
```
program_code/.../tests/replay/test_manifest_signer_xlang_consistency.py:
  # 不硬編碼 `/Users/ncyu/...` 或 `/home/ncyu/...`（CLAUDE.md §七 跨平台守則）。
```

註釋說明跨平台守則的負例引用 — 不違反規則。Frontend 0 hit / cron 0 hit / Rust 0 hit。

✅ Cross-platform compliant。

### 2.10 Title decision (operator 中文 dominant)

✅ tab-paper.html line 6:
```html
<title>模擬重放實驗室 / Paper Replay Lab</title>
```

中文 dominant 順序，product name aligned with V3 ("Paper Replay Lab")。

---

## 3. Findings (5 MED + 4 LOW; 0 CRITICAL / 0 HIGH)

### 3.1 MEDIUM-1: shell SQL string interpolation (rotation_check.sh:254/262)

**File**: `helper_scripts/cron/replay_key_rotation_check.sh:253-262`

```bash
already_today=$(psql "$OPENCLAW_DATABASE_URL" -tAc \
    "SELECT 1 FROM learning.governance_audit_log WHERE event_type='audit_write_failed' AND ts >= date_trunc('day', NOW()) AND payload->>'alert_type'='replay_key_rotation_due' AND payload->>'env'='${env_name}' LIMIT 1;" \
    ...)
...
psql "$OPENCLAW_DATABASE_URL" -tAc \
    "INSERT INTO learning.governance_audit_log (event_type, decided_by, payload) VALUES ('audit_write_failed', 'replay_key_rotation_check_cron', '${payload}'::jsonb);"
```

**Issue**: `${env_name}` 與 `${payload}` 直接 string interpolation 進 SQL。雖然 `env_name` 來自 `ENVS=(paper demo live)` hardcoded array、`payload` 由 script 內 `printf` 構造，**當前 SQL injection 風險為 0**，但設計與 Python sibling (`replay_key_archive_cleanup.py:130`) 用 parameterized `cur.execute(..., (env_name, status))` 不一致。

**Why MED**: 若未來 `ENVS` 改為動態（從 V042 query / config 讀），會 trivially injectable。

**Fix recommendation (E1)**: 改用 `psql --variable=ON_ERROR_STOP=1 -v env="$env_name" ...` + SQL 內 `:'env'` 形式 (psql 變數 quoting)。或，把這兩 query 移到 helper Python script 用 `psycopg2.execute(..., (env_name,))`。

**Severity**: MEDIUM (defense-in-depth 缺漏，不影響當前 wave 2 batch 1 correctness)。

### 3.2 MEDIUM-2: stale env var name in scaffold (`OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA`)

**File**:
- `rust/openclaw_engine/src/replay/profile.rs:42`
- `rust/openclaw_engine/src/replay/mod.rs:17`

**Issue**: Wave 1 P0-T2/T3 scaffold 仍用舊名 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA`，但 Wave 2 dispatch §2 #1 operator decision 已改名為 `OPENCLAW_REPLAY_MAC_NO_PRIVATE`（14 字、語義清晰）。

dispatch §2 明示「Wave 3 R20-P2b-S9 implement 時用此名 + grep 全 codebase 0 出現舊名」。

**Why MED**: 不 block Wave 2 Batch 1（Mac guard Wave 3 才 implement），但 dispatch §2 已 land 後 scaffold 仍未同步，累積 stale comment debt。

**Fix recommendation (E1)**: Wave 3 R20-P2b-S9 IMPL 開工前必 grep + 替換 2 處（`profile.rs:42` / `mod.rs:17`），同時更新雙語註釋。

**Severity**: MEDIUM (technical debt，Wave 3 R20-P2b-S9 必清)。

### 3.3 MEDIUM-3: Verify path 不驗 caller fingerprint == self.fingerprint

**File**:
- `rust/openclaw_engine/src/replay/manifest_signer.rs:401-447`
- `program_code/.../replay/manifest_signer.py:379-444`

**Issue**: `verify(canonical, declared_hash, sig_hex, fingerprint, archive)` 參數中的 `fingerprint` 用於 archive lookup，但**不驗 `fingerprint == self.fingerprint`**。如果 caller 用錯 signer instance（self.fingerprint=A）但傳了 fingerprint=B（B 在 archive Active），驗證流程：

1. archive.lookup_status(B) → Some(Active) ✅
2. permits_verify ✅
3. self.sign(canonical) 用 self.key_bytes (A 的 key) → expected_sig != caller-supplied sig (B 簽的) → SignatureMismatch

最終是 fail-closed (SignatureMismatch)，**不會誤通過**，但語意上 KeyMissing fail-mode 永遠不會被 trigger 即使 self.fingerprint 不在 archive。

**Why MED**: Module doc comment (line 422-431) 雖明示「caller 必先按 fingerprint 路由到正確 signer instance」，但設計上沒強制；現有 Wave 2 中 0 production caller，但 Wave 3 R20-P2a-S4 (SQL archive lookup) 與 R20-P2b-S7 (isolated runner 整合) 是 first callers — 必須被 caller 紀律強制。

**Fix recommendation (E1, deferred to Wave 3 R20-P2a-S4)**: 在 verify() 開頭加 assertion `if fingerprint != self.fingerprint() { /* return KeyMissing OR error */ }`，明示 contract；或 IMPL Wave 3 SQL archive 時要求每 fingerprint 對應一 ManifestSigner instance（factory pattern），caller-supplied fingerprint == signer's own fingerprint 為前置不變量。

**Severity**: MEDIUM (設計 ambiguity 但 fail-closed 仍守，記錄供 Wave 3 SQL archive integration 時收尾)。

### 3.4 MEDIUM-4: `except Exception: pass` 在 cleanup path (Python)

**File**: `helper_scripts/cron/replay_key_archive_cleanup.py:311, 317`

```python
except Exception as exc:
    log.error("cleanup transaction failed: %s", exc)
    try:
        conn.rollback()
    except Exception:
        pass        # ← line 311
    return 1
finally:
    try:
        conn.close()
    except Exception:
        pass        # ← line 317
```

**Issue**: CLAUDE.md §九 規定「沒有 except:pass 或靜默吞異常」。雖然這兩處在 cleanup / error path（rollback 失敗 fallback / conn close 失敗 fallback），且 main flow 已 log + return 1，仍違反字面 §九。

**Why MED**: Cleanup path 的 silent swallow 在工程上常被視為合理 fallback，但 §九 硬性禁止；應改為 log + continue。

**Fix recommendation (E1)**:
```python
except Exception as rollback_exc:
    log.warning("conn.rollback() also failed (cleanup race): %s", rollback_exc)
# ↑ replace `pass` with explicit log
```

**Severity**: MEDIUM (governance §九 字面 violation，但 cleanup 路徑 worst-case 風險低)。

### 3.5 MEDIUM-5: stale `// REF-20 R20-P1-U9 i18n hook` 註釋仍指向 EN inline 文案

**File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/common.js:1184-1189`

```js
var dimLabel = ocEsc(meta.dim_label_en);  // REF-20 R20-P1-U9 i18n hook
var stateLabel = ocEsc(meta.label_en);    // REF-20 R20-P1-U9 i18n hook
var icon = ocEsc(meta.icon);
var tipEn = meta.tip_en || '';
var tipZh = meta.tip_zh || '';
var titleText = tipEn + (tipZh ? ' / ' + tipZh : '');  // REF-20 R20-P1-U9 i18n hook
```

**Issue**: 註釋說「REF-20 R20-P1-U9 i18n hook」表示這些位置應該是 hook 點 — 預期 U9 完成後改為從 `t_zh(...)` 取中文，但 U9 已 land（commit 9879eeb 同 commit），這些位置仍直接用 `meta.dim_label_en` / `meta.label_en`，**沒實際 hook 進去**。

mode badge 仍用 EN-only label 顯示（除了 `tipZh` 已 concat 進 title attribute）。

**Why MED**: 用戶看到的 mode badge label 是 EN ("Data Tier: Real" / "Exec Confidence: None")，未對齊 operator 中文 dominant 偏好。設計 ambiguity 在於 task dispatch 沒明確 P1 階段 mode badge label 要中文 dominant 還是僅 tooltip 中文，commit message 自承「i18n hook tooltip 文案此版本 EN inline + 中文輔助；REF-20 R20-P1-U9 將以 i18n_zh.js 對照表替換」— 但 U9 land 後也沒換。

**Fix recommendation (E1a/TW Wave 2 closure 前)**:
- 選項 A: 在 `_ocRenderModeBadgePill()` 加邏輯：若 `window.OpenClawI18n_zh` 存在，從 `mode_badge.<dim>.<state>` lookup 中文 label，fallback `meta.label_en`。
- 選項 B: 移除「i18n hook」comment 與更新 commit message 自承「P1 mode badge 為 EN dominant，i18n_zh.js 主要服務 disabled state / verdict / handoff phrase 等其他 surface」。

**Severity**: MEDIUM (operator-facing UX consistency；不 block runtime correctness)。

### 3.6 LOW-1: console.html 載入 i18n_zh.js 為 redundancy

**File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/console.html:10`

console.html 是 main shell（iframe SPA wrapper），**不直接 hook t_zh()** — `OpenClawI18n_zh` 僅在 tab-paper.html iframe context 內被 hook（`data-i18n` attrs）。

每個 iframe 有自己的 window，所以 console.html 載 i18n_zh.js 等於 +10KB asset load 但 0 utility（除非未來其他 tab 也加 i18n 需求）。

**Fix recommendation (LOW)**: 移除 console.html line 10 `<script src="/static/i18n_zh.js"></script>`；保留 tab-paper.html 內的（後者真正使用）。或，保留 console.html load 但加 comment 解釋「Future-proofing for cross-tab i18n share」。

**Severity**: LOW (~10KB 多餘 asset load，無功能影響)。

### 3.7 LOW-2: console.html `+4L` commit message 描述 vs 實際 `+3L`

**File**: commit `9879eeb` message vs `git diff` numstat

Commit message 寫「console.html (+4L): load i18n_zh.js after common.js」，實際 diff 顯示 `+3L`。Minor docstring drift。

**Severity**: LOW (commit message 描述精度，不 block；不需 retro-fix)。

### 3.8 LOW-3: i18n_zh.js comment line 78 提及 emoji

**File**: `program_code/.../static/i18n_zh.js:77-80`

```js
// 'none' 字串內含 ⚠️ emoji 為 task spec 對齊；CSS 仍須加灰底+紅邊+tooltip
execution_confidence: {
  none: '無信心 ⚠️',
```

CLAUDE.md 系統提示 "Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked."

但本 case ⚠️ 是 task spec aligned (UX subdoc §7 / A3 §7.4 #17 4 visual signals 第 2 個)，**operator 已 explicit request** in dispatch。允許。

**Severity**: LOW (false positive；emoji 是 spec 強制，符合 explicit request 例外)。

### 3.9 LOW-4: Wave 2 Batch 1 後 `submitOrder/cancelOrder` grep 仍 4 hit

**File**: `tab-paper.html:287, 365, 367, 585`

V3 §12 #19 acceptance check：`grep submitOrder/cancelOrder` 0 hit on Paper Replay Lab surface。

當前 baseline：
- tab-paper.html: 4 hit (含 `function submitOrder()` / `function cancelOrder(orderId)` 已 fail-closed `ocToast('已禁用 ...')` + 1 button + 1 caller)
- app-paper.js: 1 hit (`async function submitPaperOrder()`)

**Wave 2 Batch 1 不負責清這個** — U3 (移除 manual submit/cancel) 是 Wave 4 task (per workplan §4 Wave 4 表)。Wave 2 dispatch §5 Exit Criteria 也只說「ground truth pre-flight」記錄基線。

**Severity**: LOW (預期內 deferred，記錄供 Wave 4 U3 closure 比對)。

---

## 4. CLAUDE.md §九 8-Item Checklist

| # | Item | 結果 |
|---|---|---|
| 1 | 改動範圍與 PA 方案一致 | ✅ 5 task 範圍對齊 workplan §4 Wave 2 + dispatch §3 |
| 2 | 沒有 except:pass 或靜默吞異常 | ⚠ 2 hit cleanup path（MED-4） |
| 3 | 日誌使用 %s 格式（非 f-string） | ✅ 0 logging f-string hit |
| 4 | 新 API 端點有 _require_operator_role()（如寫入操作） | N/A (no FastAPI route in Wave 2 Batch 1; S3 routes Wave 3) |
| 5 | except HTTPException: raise 在 except Exception 之前 | N/A (no FastAPI in scope) |
| 6 | detail=str(e) 已改為 "Internal server error" | N/A (no FastAPI in scope) |
| 7 | asyncio 路由中沒有 blocking threading.Lock | N/A (no asyncio in S2 module; Python sync only) |
| 8 | 沒有私有屬性穿透（._xxx） | ✅ Python signer 用 `_key_bytes`/`_fingerprint` private + `@property fingerprint` getter；caller 0 穿透 |

---

## 5. OpenClaw 9-Item Checklist

| # | Item | 結果 |
|---|---|---|
| 1 | 跨平台 grep（禁 `/home/ncyu` / `/Users/[^/]+`） | ✅ 1 hit in test docstring（負例引用，合規） |
| 2 | 雙語注釋（→ `bilingual-comment-style`） | ✅ MODULE_NOTE / docstring / inline 全雙語 |
| 3 | Rust unsafe 零容忍 / unwrap 限不可恢復場景 / panic 不在交易路徑 | ✅ 0 unsafe；test fixture 用 `unwrap()` 合規；prod path `.expect("HMAC-SHA256 accepts any key size")` 在 invariant 已被 constructor 驗證後（合規） |
| 4 | 跨語言 IPC schema 一致 + serde 型別安全 | N/A (no IPC in S2; cross-language is HMAC byte-equal contract, verified by 3 fixture xlang test) |
| 5 | Migration Guard A/B/C（V023 silent-noop 教訓） | N/A (no SQL migration in Wave 2 Batch 1; V042 reserved Wave 3) |
| 6 | healthcheck 配對（被動等待 TODO 必附 check） | N/A (no passive-wait TODO added) |
| 7 | Singleton 登記 §九 表 | N/A (no new singleton; static factory + module-level only) |
| 8 | 文件大小 800/1500 行 | ✅ all files < 800 except common.js 1413 < 1500（pre-existing baseline approaching cap） |
| 9 | Bybit API 改動先查字典手冊 | N/A (no Bybit API change) |

---

## 6. 對抗反問結果

| Q | E1/E1a 答 | E2 評估 |
|---|---|---|
| 「你說『測試通過』— 跑了哪些 test？mock 了什麼？真實邏輯有跑嗎？」 | 56 PASS：10 Rust unit + 8 Rust integration + 13 Python pytest + 7 cron pytest + 18 sibling regression。Rust unit 用 `InMemoryKeyArchive` mock V042 archive；其他用真實 disk fixture (`key.hex` + 3 manifests)。 | ✅ 接受 — 雖 V042 mock 但 archive 邏輯在 Wave 3 才 land；所有當前可驗 path 都用 fixture/integration。 |
| 「你說『沒副作用』— `grep -r ManifestSigner` 結果？」 | 僅 manifest_signer.rs (def) + test fixtures + tests (caller)。0 production caller existing；Wave 3 R20-P2a-S4 (SQL archive) + R20-P2b-S7 (isolated runner) 是 first integrators。 | ✅ 接受 — git grep 確認 0 production import；caller 對齊 dispatch §3.4 Wave 3 timeline。 |
| 「你說『race 不可能』— shell vs Python cron 同時跑會怎樣？」 | shell 有 `mkdir LOCK_DIR` 互斥（line 108-114）；Python 用 PG transaction `with conn:`（implicit row lock via UPDATE ... RETURNING）。兩 cron 不同檔不同職責，無共享 mutable state。 | ✅ 接受 — shell SW-006 lock pattern + Python PG row lock 雙層防護。 |
| 「你說『edge case 已處理』— mtime=NOW (剛 rotate) / mtime > NOW (clock drift) / 0-byte key file 各跑？」 | 4 pytest case cover：file_missing / mtime_within_grace / mtime_past_due / SECRETS_DIR_missing。0-byte / clock-skew 未顯式覆蓋但 `len(raw) != 64` 邏輯會 reject 0-byte。 | ⚠ 部分 — 顯式 0-byte case 未 cover；建議 Wave 3 補一個 pytest case 驗 `replay_signing_key length 0 != expected 64`。 |
| 「你說『規格一致』— V3 §5 第幾行對應你哪行 code？」 | V3 §5 line "verification order: verify signature first, then manifest hash" → manifest_signer.rs line 386-447 (verify method) + test `verify_order_signature_before_hash` line 702-734。 | ✅ 接受 — verify-order test 顯式驗 signature 先 hash 後。 |

---

## 7. 退回 E1 / E1a / TW 修復清單

### 必修（不 block Wave 2 Batch 1 closure，但 Wave 3 R20-P2a-S4/S7 開工前必清）

1. **MED-2 stale env var name** — `profile.rs:42` + `mod.rs:17` 改 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` → `OPENCLAW_REPLAY_MAC_NO_PRIVATE` + 雙語註釋同步。Owner: E1 (Wave 3 R20-P2b-S9 implement 第一步)。
2. **MED-3 verify caller fingerprint contract** — 設計選擇 (a) `verify()` 加 assertion / (b) Wave 3 SQL archive caller-side enforce factory pattern。Owner: E1 (Wave 3 R20-P2a-S4 IMPL 階段 PR review)。

### 建議修（Wave 2 closure 前 fix-up commit）

3. **MED-1 shell SQL parameterization** — `replay_key_rotation_check.sh:254/262` 改用 `psql -v env="$env_name"` + `:'env'` 形式。Owner: E1。
4. **MED-4 except: pass cleanup path** — `replay_key_archive_cleanup.py:311/317` 改用 explicit log + continue。Owner: E1。
5. **MED-5 mode badge i18n hook** — 選 (a) 在 `_ocRenderModeBadgePill()` 加 `window.OpenClawI18n_zh` lookup OR (b) 移除「i18n hook」comment + 更新 commit message。Owner: E1a + TW (worktree merged)。

### Optional cleanup（不影響 closure）

6. **LOW-1 console.html i18n_zh.js redundant load** — 移除 line 10 OR 加 comment 解釋 future-proofing。Owner: E1a。
7. **LOW-2 commit message `+4L` vs `+3L` drift** — 不需 retro-fix（commit messages frozen）。
8. **LOW-3 emoji in i18n_zh.js** — false positive，accept as-is。
9. **LOW-4 submitOrder/cancelOrder grep baseline** — Wave 4 R20-P1-U3 closure 時清。

---

## 8. 整體 Sign-off Statement

**Verdict**: **CONDITIONAL PASS to E4 Linux regression smoke**

Wave 2 Batch 1 三 commit (9879eeb + ce665b0 + 40ebc19) 通過 56 個自動化測試 + 0 hard boundary mutation + 0 cross-platform path 違規 + 完整雙語註釋。fingerprint align fix (4773d12e2371bb93 → da0d3b33336d12fb) cross-verified vs helper script + fixture + Python sha256 三方完全一致；HMAC-SHA256 server-side sign + verify 雙端 byte-equal；4 fail-mode + verify-order invariant + key separation 全 covered。

設計面有 5 個 MEDIUM finding（多為 Wave 3 closure 前必清的 contract / parameterization / stale comment / except: pass 衛生問題）+ 4 LOW（minor cleanup）。**無 CRITICAL / HIGH 阻塞 finding**。

E4 可以開工跑 Linux PG end-to-end regression：
1. ssh trade-core 執行 cargo test --lib replay::manifest_signer + cargo test --test replay_manifest_signer_xlang_consistency (Linux x86_64 binary 一致性)
2. ssh trade-core 跑 Python pytest test_manifest_signer_xlang_consistency.py（Linux Python 與 Mac Python 對 fixture 應產出 byte-equal HMAC）
3. ssh trade-core 跑 helper_scripts/cron/test_replay_key_*.py 7 case（Linux GNU stat/date 分支驗證）
4. ssh trade-core 跑 cargo test --lib live_authorization 18 case（sibling regression baseline）
5. Frontend smoke：手動在 Linux trade-core http://192.168.50.43/console.html 開 Paper tab 切換 4 sub-tabs（Session active；Replay/Compare/Handoff disabled with phase tooltip）+ open DevTools console 驗 0 JS error + 1 mock seed call。

5 MEDIUM 列為 Wave 2 closure 前 fix-up clearance，不 block E4 regression smoke 並行進行。

---

## 9. 對 Batch 2 (U2/U4/U5/U6/U8) 派發 prerequisite 建議

Wave 2 dispatch §3.2 列 Batch 2 為「U1 land 後派 sub-tab 內容 (U2/U4/U5/U6) + S1 backend」。U1 (commit 9879eeb) 已 land 提供 `#subtab-{session,replay,compare,handoff}` 4 個 div + sub-tab nav shell，**Batch 2 prerequisite GREEN**。

派發前建議：

1. **派 4 個 sub-agent (U2/U4/U5/U6) 全 worktree isolation**（per dispatch §3.4）— 4 task 都改 `tab-paper.html`，並行操作必 isolation 防 git conflict。
2. **U2 (Session 內容遷入) 必先驗 baseline behavior**：當前 tab-paper.html line 148-149 既有 Session content (Account Balance / PnL Overview / Positions / Orders / Performance Metrics / Fill History / Shadow Decisions / Manual Submit) 仍在 #subtab-session 之外。U2 把它們搬進 div#subtab-session 必驗：
   - 搬遷後 GUI 切換 Session sub-tab 顯示完整內容；切換 Replay/Compare/Handoff 顯示 disabled placeholder。
   - 7 個 `loadXxx()` 函數仍能正確 hook DOM ID（搬遷不破壞 element id）。
   - localStorage `paper_active_subtab` round-trip 仍 work。
3. **U4/U5/U6 disabled placeholder** 用 i18n_zh.js `disabled_state` 表 lookup（已存在），但 mode badge i18n hook 未實裝（MED-5）— 建議 U2/U4/U5/U6 派發時併同 MED-5 fix（要不 PM 決定 P1 階段 mode badge label EN dominant，要不 i18n hook 真做進去）。
4. **U8 (Disabled state component)** 是 shared helper — 必先確認其 spec：是否抽到 common.js？提供 `OpenClawDisabledState.render(elementId, gateKey)` API？由 U4/U5/U6 caller 使用？派發時 PM 必 final clarify。

派發前 cross-platform check：Batch 2 並行 4 sub-agent worktree，**Mac CC 派發後立即 ssh trade-core git fetch**（避免 sibling CC 已開過分支）。

派發前 hard prereq verify：
- ✅ U1 / U7 / U9 land (Batch 1 已完成)
- ✅ 5 ambiguity decisions (dispatch §2)
- ⚠ Batch 1 5 MED finding 修還是 deferred — PM 建議 deferred 到 Wave 2 closure，避免 block Batch 2 派發節奏。

---

## 10. Lessons Learned (E2 memory candidates)

### Lesson 23: Cross-language byte-equal HMAC contract 必走 fixture-based xlang test

S2 Rust `manifest_signer.rs` + Python `manifest_signer.py` 用 in-tree `tests/fixtures/replay_manifest_signer/` 的 `key.hex` + `manifest_{1,2,3}.json` + `manifest_*.sig` + `manifest_*.hash` 為 ground truth。Rust integration test 載 fixture 算 HMAC 驗 sig file；Python pytest 載同 fixture 算 HMAC 驗 sig file → 雙端對同一輸入產出同一 byte sequence 才能信「跨語言一致」。

對抗反問必驗：fixture sig file 是 source of truth (predetermined byte sequence)，Rust + Python 各自獨立計算後**都對齊 fixture**，而不是 Rust 算完餵給 Python 的 round-trip（後者會 mask 「兩端各自實作有偏差但偏差正好抵消」）。

### Lesson 24: Fingerprint align fix (helper script vs runtime) 是常見「operator-facing vs runtime」chasm

S2 fingerprint 算法 BEFORE/AFTER：
- BEFORE: `sha256(decoded_raw_32_bytes)[:16] = 4773d12e2371bb93`
- AFTER: `sha256(file_content_with_trailing_newline)[:16] = da0d3b33336d12fb` (matches `openssl dgst < key.hex`)

Operator 用 `openssl dgst -sha256 -hex < key.hex | awk '{print $NF}' | cut -c1-16` 寫入 1Password vault；runtime 必算同一 byte sequence 才能查 V042 archive。**Helper script 是 source of truth (operator-facing)**，runtime 必 align — 反之就 100% `KeyMissing` 失敗。

對抗反問必驗：fingerprint 算法在 3+ 端（operator 1Password / runtime Rust / runtime Python / fixture）必字面一致；任一端漂移 = 整 chain breaks。E2 review 必跑 `openssl dgst < fixture/key.hex` 對齊 `fixture/fingerprint.txt` 對齊 Python `compute_key_fingerprint(file_bytes_with_newline)` 對齊 Rust `compute_key_fingerprint(file_bytes_with_newline)`。

### Lesson 25: V042 graceful fallback 設計準則 — fail-closed 不 fail-open

V042 (`replay.replay_signing_keys`) 尚未 land。Wave 2 Batch 1 cron 設計：
- shell V042 absent → mtime 路徑 fail-closed (任何 mtime > NOW-83d 即 ALERT exit 1)
- Python V042 absent → graceful exit 0 + log（不 crash 但也不假冒 success）
- Rust verify() archive 沒 fingerprint → KeyMissing fail-mode (fail-closed)

對抗反問必驗：每個 graceful fallback 路徑必證 **決策路徑仍 fail-closed**（Python exit 0 加 log 是「等 V042 land 再有用」不是「假冒 OK」；shell mtime 路徑仍 ALERT；Rust archive lookup miss 仍 KeyMissing）。任何 fallback 不能讓 verify 假冒通過或讓 rotation alert 漏報。

### Lesson 26: dispatch §2 ambiguity decisions 落地必 grep 同步

Wave 2 dispatch §2 #1 operator decision 改名 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` → `OPENCLAW_REPLAY_MAC_NO_PRIVATE`，但 Wave 1 P0 scaffold（commit 06d360a / land before dispatch §2）仍用舊名於 `profile.rs:42` + `mod.rs:17`。Operator decision land ≠ scaffold 自動同步；E2 review 必 grep 4 places：
- `git grep OPENCLAW_REPLAY_MAC` 全 codebase
- `git grep -E 'rt-multi-thread\|tokio'` for #2
- `git grep -E 'canonical_config_parser\|crate::config'` for #3
- `git grep -E 'requires_lease' rust/openclaw_engine/src/replay/` for #4
- `git grep -E 'nm -gU\|nm --extern-only'` for #5

任一處還用舊名 = MEDIUM finding，Wave 3 IMPL 階段必清。
