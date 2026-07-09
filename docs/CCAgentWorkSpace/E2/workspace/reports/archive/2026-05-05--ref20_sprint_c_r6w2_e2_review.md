# REF-20 Sprint C R6 W2 — E2 Adversarial Review

**Date**: 2026-05-05
**Reviewer**: E2 (Senior Backend Reviewer + Adversarial Auditor)
**Scope**: R0-T0 `apply_fill.rs` 拆檔 + R6-T3 KellyConfig wire
**Branch**: main (E1 unstaged; pre PM commit + Linux verify)
**E1 Sign-off**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_w2_impl.md`
**HEAD reference**: W1 commit `286252d2` (fee+slippage model + LG-3 pricing_binding)

---

## §1 改動範圍

| File | 操作 | LOC | Status |
|---|---|---:|---|
| `srv/rust/openclaw_engine/src/replay/apply_fill.rs` | NEW | **485** | 新檔 |
| `srv/rust/openclaw_engine/src/replay/runner.rs` | M | 1992 → **1808** (-184) | 抽 4 method + 4 helper + 8 fields → pub(super) + R6-T3 unit tests |
| `srv/rust/openclaw_engine/src/replay/mod.rs` | M | +1 line | `pub mod apply_fill;` |
| `srv/rust/openclaw_engine/src/bin/replay_runner.rs` | M | 1427 → **1461** (+34) | R6-T3 wire |

LOC 對應 E1 sign-off claim 全部一致。

---

## §2 §九 8 條 checklist

| # | Item | 結果 | 證據 |
|---|---|---|---|
| 1 | 改動範圍與 PA 方案一致 | ✅ PASS | E1 sign-off §2 + 實際 `git diff` 比對 — 0 多改 / 0 少改 |
| 2 | 沒有 except:pass 或靜默吞異常 | ✅ N/A | Rust only；0 except:pass；錯誤路徑經 `match` + `Result` 顯式處理 |
| 3 | 日誌使用 %s 格式（非 f-string） | ✅ N/A | Rust only；`eprintln!` 用 Rust format 不是 Python f-string |
| 4 | 新 API 端點 `_require_operator_role()` | ✅ N/A | replay binary 0 新 API 端點 |
| 5 | except HTTPException raise 順序 | ✅ N/A | Rust only |
| 6 | detail=str(e) 已改為 "Internal server error" | ✅ N/A | Rust only |
| 7 | asyncio 中無 blocking threading.Lock | ✅ N/A | Rust only；apply_fill.rs 0 Mutex/RwLock |
| 8 | 無私有屬性穿透 (._xxx) | ✅ PASS | apply_fill.rs 透 `pub(super)` field 同 crate 訪問，外部 crate 0 暴露 |

---

## §3 OpenClaw 9 條 checklist

| # | Item | 結果 | 證據 |
|---|---|---|---|
| 3.1 | 跨平台合規 (`/home/ncyu` / `/Users/[a-z]+`) | ✅ PASS | grep 0 hits across 4 changed files |
| 3.2 | 雙語注釋 (MODULE_NOTE + docstring + inline) | ✅ PASS | apply_fill.rs:1-114 完整 EN+CN MODULE_NOTE；4 method 都有 EN+CN docstring；4 helper 都有 EN+CN docstring + SAFETY 注釋；R6-T3 wire 4 點都有 EN+CN inline 注釋 |
| 3.3 | Rust unsafe / unwrap / panic | ✅ PASS | apply_fill.rs: 0 unsafe / 0 unwrap / 0 panic / 0 expect (僅 `compute_kelly_qty` test 內 `.expect("derived KellyConfig must validate")` — test code only) |
| 3.4 | 跨語言 IPC schema | ✅ N/A | 改動不涉 IPC；apply_fill.rs forbidden surface 列出 0 use of `crate::ipc_server` |
| 3.5 | Migration Guard A/B/C | ✅ N/A | W2 0 V### migration |
| 3.6 | healthcheck 配對 (被動等待 Nd) | ✅ N/A | W2 0 新被動等待 TODO |
| 3.7 | Singleton 登記 §九 表 | ✅ N/A | apply_fill.rs 0 新 singleton；R6-T3 wire 用 stateless KellyConfig struct |
| 3.8 | 文件大小 800/2000 行 | ✅ PASS | runner.rs 1808 < 2000 cap (恢復 192 LOC headroom)；apply_fill.rs 485 < 800 warn (315 LOC headroom)；bin/replay_runner.rs 1461 < 2000 cap (pre-existing 1427 baseline 已 > 800 warn，此 wave +34 仍 < 2000) |
| 3.9 | Bybit API 字典手冊 | ✅ N/A | W2 0 Bybit API 改動 |

---

## §4 對抗反問結果

### Q1: 「runner.rs 1992 → 1808 是 pure refactor 還是 1692 + 116 R6-T3 tests？」

**E1 claim**: 1808 = 1692 (refactor 後) + 116 (3 new R6-T3 unit tests)
**E2 verify**: `git diff 286252d2 -- runner.rs` 顯示 +159 / -343 lines (含註解)；wc 算法 W2 final 1808。E1 沖銷 -300 抽出 + ~+116 test 大致一致。**3 R6-T3 unit test 確存於 runner.rs:1714-1834** (從 grep `test_r6t3_` 找到 3 個 `#[test] fn`)。
**結論**: ✅ PASS — claim 一致

### Q2: 「apply_fill.rs 485 LOC 構成？多少業務 / 多少 docstring / 多少 inline test?」

**E2 verify** (Read apply_fill.rs 1-486 全檔):
- Line 1-111: bilingual MODULE_NOTE = ~110 LOC
- Line 113-115: 3 use statement = 3 LOC
- Line 117-138: 2 helper section header + DEFAULT_*_FEE_RATE constants = ~22 LOC
- Line 140-199: 3 helper docstring + body = ~60 LOC
- Line 201-204: section divider = 4 LOC
- Line 206-461: `impl IsolatedPipeline { 4 method + docstring }` = ~256 LOC
- Line 462-486: trailing R0-T0 boundary 注釋 = ~25 LOC
- 0 inline test (sign-off §6 explicit: tests stay in runner.rs)

**結論**: ✅ PASS — 業務 method body ~250 LOC + helper ~80 LOC + bilingual docs ~110 LOC + boundary notes ~25 LOC = 465 LOC（剩 ~20 LOC blank line）

### Q3: 「R6-T3 3 unit test 是 PR3 既有 KellyConfig pattern 還是 fresh design？」

**E2 verify** (Read runner.rs:1700-1834):
- `test_r6t3_kelly_config_construction_matches_live_default_at_g7_01_defaults`: field-by-field equality 9 fields — fresh design 但對齊 sign-off §3.2 #1
- `test_r6t3_p1_risk_pct_reads_from_risk_config_limits`: `assert!(p1_risk_pct == 0.03)` + `assert!(!= 0.02 baseline)` — fresh design
- `test_r6t3_kelly_qty_finite_with_calibrated_kelly_config`: cold-boot `compute_kelly_qty` + `ReplayRiskAdapter::new` Some(kelly_config) acceptance — fresh design

**對齊 9 W1 R6-T1+T2 unit test 同 pattern**：所有 12 test 走 `tests` mod + `super::*` import + 顯式 G7-01 default + bilingual docstring。

**結論**: ✅ PASS — fresh design 完全對齊 PR3/W1 testing pattern

### Q4: 「W2 0 邏輯改動 — 那為何 cargo lib test 從 2487 變 2490 (+3)？」

**E1 claim**: +3 = 3 new R6-T3 unit test，純 refactor 不應改 既有 test 數
**E2 verify**: `cargo test --release --features replay_isolated --lib` 跑出 `2490 passed; 0 failed` ✓；`cargo test --release --features replay_isolated --lib replay::runner::tests::` 跑出 `20 passed; 0 failed`，含 9 W1 `test_apply_fill_*` + 3 W2 `test_r6t3_*` + 8 background。
**結論**: ✅ PASS — +3 test ≠ regression，對應 R6-T3 新 wire

### Q5: 「Linux PG dry-run 跨度 — V055 lesson 還適用嗎？」

**E2 evaluate**: V055 lesson form = 「V### migration must Linux PG dry-run before E1 IMPL design」。W2 是 Rust 改動，**不涉 V### migration / PG SQL** → V055 form 不直接適用。但 V055 lesson 推 form 「Mac mock layer ≠ enough，Linux empirical 必驗」**仍適用** — 原因：Linux x86_64 vs Mac aarch64 cargo target 行為差（雖罕見，但歷史 Tokio + serde 過 cross-platform endian/ABI bug）。
**結論**: ✅ PASS — Linux SSH cargo verify 在 PM commit 後仍強制（per CLAUDE.md §七 強制鏈 + V055 lesson form-extension）

---

## §5 Mac cargo test 真跑驗證

E2 跑 (Read tool output):

```
cargo test --release --features replay_isolated --lib
=> test result: ok. 2490 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out

cargo test --release --features replay_isolated --test replay_runner_e2e
=> test result: ok. 6 passed; 0 failed

cargo test --release --features replay_isolated --test replay_runner_e2e_param_delta
=> test result: ok. 2 passed; 0 failed

cargo test --release --features replay_isolated --test replay_manifest_signer_xlang_consistency
=> test result: ok. 8 passed; 0 failed

cargo test --release --features replay_isolated --test replay_forbidden_guard_acceptance
=> test result: ok. 4 passed; 0 failed

cargo test --release --features replay_isolated --test replay_profile_acceptance
=> test result: ok. 5 passed; 0 failed

cargo test --release --features replay_isolated --test replay_mac_policy_acceptance
=> test result: ok. 4 passed; 0 failed

cargo test --release --features replay_isolated --lib replay::runner::tests::
=> test result: ok. 20 passed; 0 failed (含 9 R6-T1+T2 + 3 R6-T3 + 8 adapter/synthetic_walker tests)
```

**Mac 端 2490 lib + 29 e2e + 20 runner::tests 全綠，對應 E1 sign-off claim 完全一致** ✓

---

## §6 Byte-equal contract 驗證 (R0-T0 純 refactor 證明)

### §6.1 4 helper byte-equal

`diff <(W1 runner.rs:526-608) <(W2 apply_fill.rs:117-199)` 結果僅 3 處差異：

```
39c39
< fn replay_fee_rate_for_tif(
---
> pub(crate) fn replay_fee_rate_for_tif(
63c63
< fn replay_slippage_bps_for_tif(
---
> pub(crate) fn replay_slippage_bps_for_tif(
81c81
< fn apply_slippage_to_price(reference_price: f64, slippage_bps: f64) -> f64 {
---
> pub(crate) fn apply_slippage_to_price(reference_price: f64, slippage_bps: f64) -> f64 {
```

**3 處差異全是 visibility widening**（fn → pub(crate) fn）— 必要：runner.rs::tests 透過 `use crate::replay::apply_fill::{...}` import 需要 pub(crate)；不擴大公開 API（pub(crate) ⊂ crate-internal）✓

**body byte-equal** ✓ — 0 邏輯改動

### §6.2 4 method byte-equal

`diff <(W1 runner.rs:963-1242) <(W2 apply_fill.rs:207-461)` 結果差異：

1. `fn` → `pub(super) fn` × 4 method (visibility widening；crate-internal 機制) ✓
2. `apply_fill_close` docstring 微改（W1 「`SimulatedFill` row 層捕獲」→ W2 「`process_close_intent` row 層捕獲」）— **doc clarification**，0 邏輯改動 ✓
3. W1 此區塊還含 `into_result` method（line 1213+），未抽出 — 對齊 sign-off §1 boundary（lifecycle method 仍留 runner.rs）✓

**body byte-equal** ✓ — 0 邏輯改動

### §6.3 4 SimulatedFill push site 一致性

驗 apply_fill.rs 含 4 push site:

| Site | Line | 場景 | qty | fee | fee_rate | slippage_bps | liquidity_role |
|---|---|---|---|---|---|---|---|
| `process_open_intent` Accepted | 259-270 | 真 fill | `final_qty` | `final_qty * fill_price * fee_rate` | derived | derived | derived |
| `process_open_intent` Rejected | 282-293 | ghost row | `0.0` | `0.0` | derived | derived | derived |
| `process_close_intent` | 348-359 | close 真 fill | `pos.qty` | `pos.qty * fill_price * fee_rate` | derived | derived | derived |
| `execute_synthetic_walker` (留 runner.rs) | (W1 baseline) | synthetic | unchanged | unchanged | unchanged | unchanged | unchanged |

4 push site 對應 sign-off §3.1 #4。Synthetic walker push site 留 runner.rs（per sign-off §1 boundary）✓

### §6.4 manifest_signer.rs 0 byte change

`git diff 286252d2 -- rust/openclaw_engine/src/replay/manifest_signer.rs` = 0 lines ✓ → xlang_consistency 13/13 byte-equal contract 維持

---

## §7 Hard boundary check (CLAUDE.md §四)

| Boundary | 狀態 | 證據 |
|---|---|---|
| `live_execution_allowed` | ✅ 0 觸碰 | apply_fill.rs MODULE_NOTE 列為禁忌 surface |
| `max_retries=0` | ✅ 0 觸碰 | 0 IMPL 改動 |
| `OPENCLAW_ALLOW_MAINNET` | ✅ 0 觸碰 | replay binary 不接 mainnet |
| `live_reserved` | ✅ 0 觸碰 | 不接 live mode |
| `authorization.json` | ✅ 0 觸碰 | 不接 live_authorization |
| `decision_lease` | ✅ 0 觸碰 | apply_fill.rs forbidden surface 列出 0 use of `crate::decision_lease`；ReplayProfile::Isolated requires_lease=false |
| `manifest_signer canonical_bytes` | ✅ 0 觸碰 | manifest_signer.rs 0 byte change |
| V### migration | ✅ 0 觸碰 | W2 0 V### file 修改 |
| V055 / V036 / V051 / V050 / V049 | ✅ 0 觸碰 | per sign-off §10 |
| IntentProcessor / GovernanceCore / paper_state mutable state | ✅ 0 觸碰 | apply_fill.rs forbidden surface explicitly禁 |

---

## §8 Findings

| # | 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|---|
| 1 | LOW | E1 sign-off §1 module note | 文中 claim helper 採 `pub(super)`，實作為 `pub(crate)` (apply_fill.rs:137-138/155/179/197)。`pub(crate)` ⊂ crate-internal 比 `pub(super)` ⊂ replay::* 寬一點點，但仍不擴大公開 API。文檔 vs code 微誤差。 | doc-only：sign-off 後續若 commit 提及 visibility，更正為 `pub(crate)`。**不退 E1**。 |
| 2 | LOW | E1 sign-off §8.1 #3(b) | 文中寫 `young: rc.kelly.young, mature: rc.kelly.mature`，實作 (bin/replay_runner.rs:486-489) 為 `young_threshold: risk_config.kelly.young_threshold, mature_threshold: risk_config.kelly.mature_threshold`。Doc shorthand 不對應 Rust struct field 全名。 | doc-only：sign-off 文中欄位名應採完整 `young_threshold` / `mature_threshold`。**不退 E1**。 |

**0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW (純 doc-clarification, 0 code action 必要)**

---

## §9 結論

### Verdict: **PASS to PM commit + Linux SSH cargo verify**

**理由**:
- §九 8 條 + OpenClaw 9 條 checklist 全綠
- byte-equal contract 三層驗證 PASS（4 helper / 4 method / 4 push site）
- 對抗 §6 5 條反問全 PASS
- Mac cargo lib 2490 + 29 e2e + 20 runner::tests 全綠
- 0 hard boundary 觸碰 / 0 forbidden surface / 0 跨平台路徑硬編
- 0 V### migration / 0 manifest_signer 改動 / xlang_consistency 13/13 維持
- 2 finding 全屬 LOW doc-clarification（sign-off 文 vs code 微小誤差），不阻 commit
- bilingual MODULE_NOTE + docstring + inline 注釋 全到位（CLAUDE.md §七 強制）

### 接 PM commit + Linux verify

PM 接手:
1. `git add` apply_fill.rs (NEW) + runner.rs + mod.rs + bin/replay_runner.rs (4 files)
2. Commit message 採 `feat(ref20): Sprint C R6 W2 — R0-T0 apply_fill.rs 拆檔 + R6-T3 KellyConfig wire`
3. 同 commit 加 E1 sign-off + E2 review report (此檔)
4. Push origin/main
5. SSH bridge: `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only && cd rust/openclaw_engine && cargo test --release --features replay_isolated --lib 2>&1 | tail -3"` 期 `2490 passed; 0 failed`
6. Linux 確認後 → R6 W2 closed → R6 W3 dispatch (T4 CalibrationLabelProducer per QC spec) unblock

### Sub-agent 接手禁忌

- 0 邏輯改動由 E1 round 2 (本 review 0 BLOCKER)
- 2 LOW finding 屬 doc-only，**不必** commit 前修；PA 後續 PR 順帶帶上即可
- 任何 PM commit 後 Linux verify 失敗 → 必回 E1 (per V055 lesson form-extension)

---

**END OF REPORT**
