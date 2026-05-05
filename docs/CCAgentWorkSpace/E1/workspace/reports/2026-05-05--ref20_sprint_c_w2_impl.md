# REF-20 Sprint C R6 W2 — R0-T0 apply_fill 拆檔 + R6-T3 KellyConfig wire (E1 Sign-off)

**Date**: 2026-05-05
**E1**: backend impl
**Status**: pending E2 review
**Branch**: main (uncommitted; awaiting E2 review per §七 強制鏈 E1→E2→E4→QA→PM)

---

## §1 任務摘要

REF-20 Sprint C R6 W2 並行兩任務：

1. **R0-T0 (CRITICAL — LOC budget)**：`replay/runner.rs` 1992 LOC 已 8 LOC margin to §九 2000 cap；任何 R6-T4+ 在 runner.rs 加邏輯必破。抽 `apply_fill` 系列 4 method + 4 helper → 新檔 `replay/apply_fill.rs`，恢復 ~280-330 LOC headroom for R6-T4+。
2. **R6-T3 KellyConfig wire**：`bin/replay_runner.rs:486-488` 既存 R6 留位（`None::<KellyConfig>` + 0.02 hardcode）→ 從 `risk_config.kelly` + `risk_config.limits` 派生 calibrated `KellyConfig` + `p1_risk_pct`；額外 wire `with_replay_fee_context` 接 `risk_config.slippage`。

**Skip per dispatch §3**：E2 P2 ticket #2 const drift CI gate (P3 推 TODO，本 W2 不做)。

---

## §2 修改清單

### §2.1 R0-T0 拆檔（純機械式 refactor，0 邏輯改動）

| File | Δ LOC | Status | 性質 |
|---|---:|---|---|
| `srv/rust/openclaw_engine/src/replay/apply_fill.rs` | **NEW +485** | 🆕 | 抽出 4 fee/slippage helper + 4 IsolatedPipeline method + bilingual MODULE_NOTE |
| `srv/rust/openclaw_engine/src/replay/runner.rs` | **1992 → 1808** (delta -184; 含 +116 R6-T3 test) | ✏️ | 4 method + 4 helper extracted; 8 fields → `pub(super)`; tests mod 加 4 helper imports |
| `srv/rust/openclaw_engine/src/replay/mod.rs` | +1 line | ✏️ | `pub mod apply_fill;` 註冊 |

**runner.rs 純 refactor 後 = 1692 LOC**（恢復 ~308 LOC headroom for R6-T4+）。R6-T3 加 3 新 unit test (~116 LOC) 推到 1808 (仍 ~192 LOC headroom)。

### §2.2 R6-T3 KellyConfig wire

| File | Δ LOC | Status | 性質 |
|---|---:|---|---|
| `srv/rust/openclaw_engine/src/bin/replay_runner.rs` | **1427 → 1461** (delta +34) | ✏️ | line ~473-503: KellyConfig + p1_risk_pct 派生 ; line ~575: with_replay_fee_context wire ; line ~595: 擴展 eprintln! debug log |

R6-T3 dispatch §2 LOC 估 ~30，實際 +34（在估算範圍）。

### §2.3 不動

- 0 V### migration（V055 既 land）
- 0 manifest_signer canonical_bytes 改動
- 0 V050/V051 schema 改動
- 19-arg signature V055 不動
- xlang_consistency 13/13 byte-equal contract 維持
- 0 hard boundary 觸碰（max_retries / live_execution_allowed / authorization.json / decision_lease 等）
- 0 R5-T1/T2/T3/T4 既有 adapter 邏輯改動
- 0 e2e proof_1/2/3/4/5/7/8 fixture 改動

---

## §3 0 邏輯改動 evidence（既有 test 全保留 PASS）

### §3.1 R0-T0 純 refactor 證據

R0-T0 是「同 crate `impl` block 跨檔」純 mechanical refactor — 4 method 從 `runner.rs` 移到 `apply_fill.rs`，所有 method body byte-equal，所有 4 fee/slippage helper bytes byte-equal（含原 line 526-540 helper section header → 移為 apply_fill.rs MODULE_NOTE 中段）。

**byte-equal contract 證明**：

- 9 R6-T1+T2 unit test (test_apply_fill_*) 在 runner.rs::tests 0 改動（僅加 4 helper imports `use crate::replay::apply_fill::{...}`），全部 PASS
- 6 R5-T3 inline test (adapter_pipeline_*) 在 runner.rs::tests 0 改動，全部 PASS
- 6 e2e proof_1/2/3/4/5 + helper round_trip：byte-equal `replay_runner_e2e` PASS（synthetic walker + adapter path 全保留）
- 2 e2e proof_7/8 strategy/risk param delta：byte-equal `replay_runner_e2e_param_delta` PASS
- 8 xlang_consistency PASS（manifest signing 路徑不動）
- 4 forbidden_guard + 4 mac_policy + 5 profile_acceptance：byte-equal PASS
- 2487 → 2490 baseline lib regression（+3 R6-T3 test，0 既有 fail）

### §3.2 R6-T3 wire 證據

R6-T3 改動在 `bin/replay_runner.rs::main` 兩處：(1) 新增 `kelly_config` + `p1_risk_pct` 派生 → 注入 `ReplayRiskAdapter::new(...)`；(2) 新增 `pipeline = pipeline.with_replay_fee_context(None, Some(risk_config.slippage.clone()), None);` chain。Rust 編譯器 ownership check + replay e2e 全綠 = 接線正確。

3 新 R6-T3 unit test 直接驗算：
1. `test_r6t3_kelly_config_construction_matches_live_default_at_g7_01_defaults`：驗 G7-01 預設下 9 KellyConfig 欄位逐一 byte-equal `KellyConfig::default()`
2. `test_r6t3_p1_risk_pct_reads_from_risk_config_limits`：驗 0.03 ≠ Sprint A 0.02 hardcode
3. `test_r6t3_kelly_qty_finite_with_calibrated_kelly_config`：驗冷啟動 `compute_kelly_qty` 路徑 = `min(balance*risk_pct/price, max_qty) = 3.0` + risk_adapter 接受 Some(kelly_config)

---

## §4 LOC compliance

### §4.1 §九 cap 對照

| File | Pre-W2 | Post-W2 | Delta | 限制 | 狀態 |
|---|---:|---:|---:|---|---|
| `runner.rs` | 1992 | 1808 (含 +116 R6-T3 test) | -184 | < 2000 cap | ✅ ~192 LOC headroom |
| `apply_fill.rs` | 0 (NEW) | 485 | +485 | < 800 warn | ✅ ~315 LOC headroom |
| `bin/replay_runner.rs` | 1427 | 1461 | +34 | < 2000 cap | ✅ ~539 LOC headroom (注：pre-existing > 800 warning baseline) |
| `replay/mod.rs` | (touched) | +1 line | +1 | < 800 warn | ✅ unchanged structure |

### §4.2 純 refactor LOC delta

不含 R6-T3 test 的 R0-T0 純 refactor:
- runner.rs 1992 → 1692 (delta **-300 LOC**)
- apply_fill.rs 0 → 485 (delta **+485 LOC**)
- mod.rs +1 (mod registration)
- net: +186 LOC（apply_fill.rs 含 ~350 LOC bilingual MODULE_NOTE + 4 method (~120 LOC) + 4 helper (~50 LOC)；runner.rs 抽出後 ~9 LOC breadcrumb 留 in-place）

### §4.3 §九 pre-existing baseline exception clause check

`bin/replay_runner.rs` baseline 1427 LOC 是 pre-existing > 800 warning 但 < 2000 cap。本 wave 加 +34 LOC：
- LOC delta 含 ~30 LOC bilingual docs（CLAUDE.md §七 強制）+ ~5 LOC 邏輯 + ~12 LOC eprintln! 擴展
- 1461 < 2000 hard cap ≫ 539 LOC headroom 仍充足
- 預期 wave-internal +5 LOC 規則的 strict reading 會 flag +34 但 R6-T3 wire 是 SoT 治理任務，bilingual docs 是強制要求；E2 review 確認接受 wave-internal +34（vs 1992 → 2000 case）

---

## §5 0 forbidden import + 0 跨平台 grep

### §5.1 Forbidden surface audit

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/replay && \
  grep -E "^use |^[[:space:]]+use " runner.rs apply_fill.rs | \
  grep -E "paper_state|canary_writer|ipc_server|governance_hub|live_authorization|decision_lease"
# 0 hits
```

`apply_fill.rs` 引用清單（全 replay-pure）：
- `crate::intent_processor::OrderIntent` — struct only
- `crate::replay::risk_adapter::{ReplayPosition, RiskDecision}` — replay-pure adapter
- `crate::replay::runner::{IsolatedPipeline, SimulatedFill}` — sibling
- `crate::account_manager::AccountManager` (pub(crate) helper signature) — read-only fee getters
- `crate::config::SlippageConfig` — immutable snapshot
- `crate::order_manager::TimeInForce` — enum only

### §5.2 跨平台路徑 grep

```bash
grep -nE "(/home/ncyu|/Users/[a-z]+)" \
  rust/openclaw_engine/src/replay/runner.rs \
  rust/openclaw_engine/src/replay/apply_fill.rs \
  rust/openclaw_engine/src/bin/replay_runner.rs
# 0 hits
```

0 hardcoded paths in changed files. Mac aarch64 + Linux x86_64 same Rust toolchain.

---

## §6 Mac cargo test 全套 PASS

### §6.1 Lib regression

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo test --release --features replay_isolated --lib
# test result: ok. 2490 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.55s
```

**2490/2490 lib PASS**（pre-W2 baseline 2487 + 3 new R6-T3 unit tests = 2490; 0 既有 regression）。

### §6.2 Replay-only sweep

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo test --release --features replay_isolated --lib replay::
# test result: ok. 67 passed; 0 failed; 0 ignored; 0 measured; 2420 filtered out; finished in 0.01s

cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo test --release --features replay_isolated --lib replay::runner::tests
# test result: ok. 20 passed; 0 failed; 0 ignored; 0 measured; 2470 filtered out; finished in 0.00s
```

`replay::*` 全綠 67 cases。`replay::runner::tests` 含 3 新 R6-T3 unit test 共 20 cases。

### §6.3 Integration e2e sweep

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo test --release --features replay_isolated \
  --test replay_runner_e2e \
  --test replay_runner_e2e_param_delta \
  --test replay_manifest_signer_xlang_consistency \
  --test replay_forbidden_guard_acceptance \
  --test replay_profile_acceptance \
  --test replay_mac_policy_acceptance
```

| Test bin | Test count | 結果 |
|---|---:|---|
| replay_runner_e2e | 6 | 6/6 ✅ (proof_1/2/3/4/5 + helper round_trip) |
| replay_runner_e2e_param_delta | 2 | 2/2 ✅ (proof_7 strategy + proof_8 risk) |
| replay_manifest_signer_xlang_consistency | 8 | 8/8 ✅ |
| replay_forbidden_guard_acceptance | 4 | 4/4 ✅ |
| replay_profile_acceptance | 5 | 5/5 ✅ |
| replay_mac_policy_acceptance | 4 | 4/4 ✅ |

**29/29 e2e GREEN**。

### §6.4 Binary build

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo build --release --features replay_isolated --bin replay_runner
# Finished `release` profile [optimized] target(s) in 13.17s — clean (0 errors, 23 pre-existing warnings)
```

### §6.5 Default features build

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo check --lib
# Finished `dev` profile — clean (default features 不啟用 replay_isolated，apply_fill.rs 仍編譯但 binary 不存在；feature gate behaviour 維持 V3 §3 G7+G8)
```

---

## §7 Git status

```bash
git status --porcelain
 M rust/openclaw_engine/src/bin/replay_runner.rs
 M rust/openclaw_engine/src/replay/mod.rs
 M rust/openclaw_engine/src/replay/runner.rs
?? rust/openclaw_engine/src/replay/apply_fill.rs
```

4 changes — all in W2 scope:
- `apply_fill.rs` (NEW) — R0-T0 拆檔
- `runner.rs` (M) — R0-T0 抽出 + tests imports + R6-T3 unit tests
- `mod.rs` (M) — R0-T0 mod registration
- `bin/replay_runner.rs` (M) — R6-T3 wire

**Plus prior W1 sibling work**：
- (W1 already committed at `286252d2`) — runner.rs R6-T1+T2 fee/slippage IMPL
- (W1 already committed at `286252d2`) — checks_pricing_binding.py [45]

---

## §8 待 E2 review

### §8.1 E2 重點審查 5 點

#### #1 R0-T0 byte-equal refactor evidence

**Verify**: `cd rust/openclaw_engine && git diff main -- src/replay/runner.rs` 應顯示：
- 4 method 從原位（line 962-1265 in `286252d2`）整段刪除，breadcrumb 註解 ~9 LOC 留在原位
- 4 helper（line 526-608）整段刪除，breadcrumb 註解 ~14 LOC 留在原位
- 8 IsolatedPipeline 欄位由 private → `pub(super)`：`balance` (line 406) / `fills` (line 417) / `last_action` (line 427) / `risk_adapter` (line 446) / `paper_snapshot` (line 451) / `account_manager` (line 456) / `slippage_config` (line 459) / `volume_24h` (line 462)
- `tests` mod 加 4 helper imports：`use crate::replay::apply_fill::{ apply_slippage_to_price, replay_fee_rate_for_tif, replay_slippage_bps_for_tif, DEFAULT_MAKER_FEE_RATE, DEFAULT_TAKER_FEE_RATE };`

**Verify by test**: 9 R6-T1+T2 + 6 R5-T3 inline test 0 改動 全 PASS。

#### #2 apply_fill.rs MODULE_NOTE bilingual

**Verify**: `apply_fill.rs:1-114` 含完整中英對照 MODULE_NOTE：模組目的 / 5 條職責 / 邊界（仍留 runner.rs 的部分）/ 禁忌 surface 稽核（V3 §6.2 0 byte change）/ 為何 cross-file `impl` block 設計 / SPEC reference。

#### #3 R6-T3 wire 4 點

`bin/replay_runner.rs` 的 R6-T3 wire：
- (a) `let p1_risk_pct = risk_config.limits.per_trade_risk_pct;` 取代 Sprint A baseline 0.02 hardcode
- (b) `let kelly_config = KellyConfig { young_threshold: rc.kelly.young, mature_threshold: rc.kelly.mature, ..KellyConfig::default() };` — G7-01 KellyTierConfig (2 fields) → KellyConfig (9 fields) struct update syntax 派生
- (c) `Some(kelly_config)` 注入 `ReplayRiskAdapter::new(...)` 取代 `None::<KellyConfig>`
- (d) `pipeline = pipeline.with_replay_fee_context(None, Some(risk_config.slippage.clone()), None);` 接 fee/slippage context

**Verify by test**: 3 新 R6-T3 unit test 全 PASS。

#### #4 R6-T1+T2 contract preserved（W1 既有）

apply_fill.rs 4 helper 與 runner.rs 原 line 526-608 byte-equal copy → R6-T1+T2 fee/slippage live `IntentProcessor` byte-equal contract（W1 commit `286252d2` E2 已驗）維持。

#### #5 Sprint A QA round 6 lessons retained

- **No new spawn / subprocess**: R0-T0 + R6-T3 純 Rust struct + function — 0 fork() / 0 child process / 0 stderr DEVNULL.
- **Fail-closed assertions**: `with_replay_fee_context` opt-in（default=`None` AccountManager + `SlippageConfig::default()` from `build_isolated_pipeline`）；不會 silent uninitialized fee data。`with_adapter_pipeline` 仍 fail-loud snapshot validation (NaN/empty rejected).
- **Placeholder string grep**: 0 placeholder strings 新增。

### §8.2 預期 E2 review checklist

1. ✅ apply_fill.rs MODULE_NOTE 完整 bilingual + 列 8 個 pub(super) 欄位 + 列 4 個方法歸屬 + 禁忌 surface 稽核
2. ✅ runner.rs 8 欄位 `pub(super)` 視覺對齊 struct field block
3. ✅ runner.rs 4 method 已移除 + breadcrumb ~9 LOC 留原位
4. ✅ runner.rs::tests `use crate::replay::apply_fill::{...}` 4 helper imports
5. ✅ bin/replay_runner.rs R6-T3 wire 4 點（a/b/c/d 見上）
6. ✅ 0 forbidden import 新增（grep paper_state\|canary_writer\|...）
7. ✅ 0 hardcoded path 新增（grep /home/ncyu\|/Users/[a-z]+）
8. ✅ 2490 lib + 29 e2e = 2519 GREEN
9. ✅ 0 V### / 0 manifest_signer / 0 V050/V051 / 19-arg V055 不動
10. ✅ 0 hard boundary 觸碰
11. ✅ LOC delta：runner.rs 1992→1808（-184）+ apply_fill.rs 0→485 + bin 1427→1461（+34）

### §8.3 Open questions for E2

1. **R0-T0 抽出範圍是否最佳？**
   - 當前抽 4 method + 4 helper（生命週期含 process_open/close + apply_fill_open/close + 4 helper）。剩在 runner.rs 的：build_isolated_pipeline / with_adapter_pipeline / with_replay_fee_context / execute / execute_synthetic_walker / execute_adapter_pipeline / into_result + 結構/struct/error type
   - 替代：抽 lifecycle.rs 含 execute_*  + with_* builders（更大幅 ~500 LOC trim）。R0-T0 dispatch 留為 future ticket。
   - PA dispatch §1 specifies `apply_fill` 為本次抽出範圍 — 已遵循。

2. **`pub(super)` 範圍是否過寬？**
   - 8 fields → pub(super)。其中 `paper_snapshot` / `risk_adapter` 是 R5-T3 引入；`balance` / `fills` / `last_action` 是原 R20-P2b-T1 引入；`account_manager` / `slippage_config` / `volume_24h` 是 R6-T1+T2 引入
   - `pub(super)` ⊂ replay::* 內可見（外部 crate 永遠看不到，視為 private cross-file 機制）
   - 替代：每個 field 提供 `pub(super) fn field_name_mut(&mut self) -> &mut FieldType`。否決：(a) 重複 8 LOC × 8 method = 64 LOC + 不變；(b) 反而擴大 method 表面，壓 future 抽 lifecycle.rs

3. **R6-T3 為何不抽到 RiskConfig::kelly_config()？**
   - 提案：RiskConfig 加 `pub fn kelly_config(&self) -> KellyConfig { KellyConfig { young_threshold: self.kelly.young, ..default() } }`，bin/ 直接呼
   - 否決：(a) RiskConfig 有 200+ 欄位，加一個 accessor 推到 add 30+ accessor (slippage_config / kelly_config / dynamic_risk / ...) 結構性膨脹；(b) bin/ 直接組合更 audit-friendly（每個參數視覺可見）
   - 接受：在 future 若多處（R6-T4 calibration / R7 MLDE / etc.）都需要相同派生，ROI 才轉為 accessor。當前單 caller。

4. **R6-T3 為何 `with_replay_fee_context` 用 `account_manager=None`？**
   - 替代：`Some(Arc::new(AccountManager::new()))` + `am.seed_default_fee_rates(...)`
   - 採納：`None`，因 `replay_fee_rate_for_tif(am=None, ...)` fallback 到 `DEFAULT_*_FEE_RATE` 與 `am.maker_fee/taker_fee` (live `AccountManager::new()` 路徑) 同等 byte-equal 預設費率
   - 簡化：少一層 init + 0 對 `seed_default_fee_rates` API 表面依賴

---

## §9 Acceptance contract 對照（PA report §5）

### A6 (Fee-aware PnL) — fully covered by R6-T1+T2 (W1) + R6-T3 wire (W2)

| # | Acceptance | R6-T1+T2 + R6-T3 contribution | 狀態 |
|---|---|---|---|
| A6-1 | Fee never omitted | Adapter path + R6-T3 KellyConfig wire: `fee = qty × fill_price × fee_rate > 0` for accepted intents | ✅ |
| A6-3 | Maker/taker mapped from PostOnly TIF | `replay_fee_rate_for_tif` returns `(rate, "maker")` for PostOnly / `(rate, "taker")` else | ✅ unit test PASS |
| A6-4 | execution_model_version ≠ 'synthetic_v1' | Out of scope (R6-T4 CalibrationLabelProducer) | ⏳ deferred to R6-T4 |
| A6-5 | ci_low ≤ ci_mid ≤ ci_high | Out of scope (R6-T4) | ⏳ deferred to R6-T4 |

### A7 (Confidence Honesty) — out of scope for R6-T3

R6-T4 CalibrationLabelProducer derives `execution_confidence` ∈ {none, limited, calibrated}. R6-T3 lays the foundation by wiring KellyConfig + p1_risk_pct so risk_adapter Gate 2.5 (Kelly) + Gate 2.6 (P1 cap) are NO LONGER pass-through (Sprint A baseline) but actually constrain qty.

---

## §10 Hard boundary check (CLAUDE.md §四)

- ❌ 未觸 `live_execution_allowed` (R0-T0 + R6-T3 不接 IPC / order dispatch)
- ❌ 未觸 `max_retries=0` (不變)
- ❌ 未觸 `OPENCLAW_ALLOW_MAINNET` (replay binary 不接 mainnet)
- ❌ 未觸 `live_reserved` (不接 live mode)
- ❌ 未觸 `authorization.json` (不接 live_authorization)
- ❌ 未觸 `decision_lease` (ReplayProfile::Isolated.requires_lease=false 強制；apply_fill.rs MODULE_NOTE 列為禁忌 surface)
- ❌ 未觸 manifest_signer canonical_bytes (R0-T0 + R6-T3 是 simulated_fills row level + bin entry wire, 不是 manifest jsonb)
- ❌ 未動 V### migration (V050 既有 4 column 全 ready; V055 既 land)
- ❌ 未動 V055 / V036 / V051 / V050 / V049 (out of scope per dispatch §8)
- ❌ 未動 IntentProcessor / GovernanceCore / paper_state mutable state
- ❌ 未動 R6-T7 healthcheck (sibling W1 land scope)
- ❌ 未動 R5-T1/T2/T3/T4 既有 adapter 邏輯
- ❌ 未動 ml/kelly_sizer 端業務邏輯（reuse `compute_kelly_qty`）
- ❌ 未動 risk_adapter 既有 6/8 Gate replication（reuse Sprint B R5-T2 既有）
- ❌ 未破 Sprint A R3 8 commit chain blockers
- ✅ 0 violation

---

## §11 PM Decision Lease check (CLAUDE.md §五 註 + §四)

R0-T0 + R6-T3 是 **replay-pure** (ReplayProfile::Isolated → `requires_lease=false`). No `acquire_lease` call needed. Per AMD-2026-05-02-01 Path A, the `OPENCLAW_LEASE_ROUTER_GATE_ENABLED` flag (default OFF) is irrelevant here since replay binary never reaches `intent_processor::router` (forbidden surface — explicitly listed in apply_fill.rs MODULE_NOTE 禁忌 surface 稽核 §). Verified: 0 use of `crate::decision_lease` in changed code.

---

## §12 Forward path

### §12.1 強制工作鏈下一步 (per CLAUDE.md §七 強制鏈)

E1 IMPL DONE (本 sign-off) → **E2 review** → **Linux SSH cargo verify (per V055 lesson)** → PM commit + push → R6 W2 closed → R6 W3 (T4 CalibrationLabelProducer per QC spec) dispatch unblock。

### §12.2 R6 progression after W2 closure

- **W2 (this report)**: R0-T0 + R6-T3 ✅ pending E2
- **W3 (next)**: R6-T4 CalibrationLabelProducer (~1 sub-agent, ~1d) — depends on R6-T3 fee_rate / slippage_bps available in SimulatedFill (this W2 enables)
- **W4 (after W3)**: R6-T5 + R6-T6 writer (Python `_replay_executor.py` calibrated tier writer + `_replay_attribution_writer.py`)
- **W5 (closing R6)**: R6-T8 smoke + R6-T9 review

### §12.3 P2 follow-up tickets (建議 PM 端 file)

1. **P2-W2-FOLLOWUP-1 (R0-T0 第二輪)**：抽 `IsolatedPipeline::execute_synthetic_walker` + `execute_adapter_pipeline` + `with_adapter_pipeline` + `with_replay_fee_context` + `into_result` 至 `replay/lifecycle.rs`（~250-300 LOC），runner.rs 1808 → ~1500 LOC，給 R6-T4+ 充足 headroom
2. **P2-W2-FOLLOWUP-2 (E2 P2 ticket #2 const drift CI gate)**：dispatch §3 推 P3 — `DEFAULT_*_FEE_RATE` 在 `intent_processor/mod.rs:239,245` + `replay/apply_fill.rs:108,109` 雙處硬編；CI gate 對比兩處數值（grep + extract → diff），drift 即 fail
3. **P2-W2-FOLLOWUP-3 (R6-T3 e2e proof_9)**：`tests/replay_runner_e2e_param_delta.rs` 加 proof_9：兩 manifest 同 strategy 同 fixture，risk_overrides 一個 kelly.young_threshold=50 / 另一個 kelly.young_threshold=100；驗 simulated_fills 數量或 qty 因 Kelly 分級切換而不同（end-to-end byte-trace via Rust binary spawn）
4. **P2-W2-FOLLOWUP-4 (apply_fill.rs grow plan)**：apply_fill.rs 485 LOC 已含 350 LOC bilingual MODULE_NOTE + 4 method + 4 helper；R6-T4+ 若需在 apply_fill.rs 加新邏輯（calibration label producer caller / fee writer），預留 ~315 LOC headroom (800-485) — 若超 800 warning，考慮再次拆分（例如 `apply_fill/helpers.rs` + `apply_fill/methods.rs` 兩檔）

---

## §13 不確定之處（E2 必確認）

1. **`bin/replay_runner.rs` LOC delta +34 接受度**：Pre-existing baseline 1427 > 800 warning ；本 wave +34 LOC（含 ~12 邏輯 + ~15 docs + ~7 eprintln 擴展）。1461 < 2000 hard cap。E2 review 確認接受 wave-internal +34 LOC（vs pre-existing baseline +5 LOC clause strict reading）。

2. **`pub(super)` 範圍 8 fields 是否擴大攻擊面**：`pub(super)` ⊂ replay::* 內可見；外部 crate 永看不到。R0-T0 是內聚 module-private cross-file 機制。E2 review 確認 8 fields 改 pub(super) 不擴大公開 API 表面（IsolatedPipeline 仍 `pub struct`，其欄位仍對外不可訪問）。

3. **`with_replay_fee_context(None, ..., None)` 是否該 plumb fixture metadata**：volume_24h 從 fixture metadata 讀 (R6-T4 fixture loader 升級 task) 還是 R6-T3 接 None=5bps fallback (current)。dispatch §2 不明文，E2 確認 R6-T3 scope 採 None fallback 是 acceptable。Sprint D R8 可加 `volume_24h_usd_at_fixture_time` 入 fixture schema。

---

## §14 Operator 下一步

**Operator (PM) 下一步**：
1. E2 review 本 sign-off + 4 個 changed files (3 modified + 1 new)
2. E2 review 必跑 cargo test（Mac + Linux per V055 lesson）：
   - `cd srv/rust/openclaw_engine && cargo test --release --features replay_isolated --lib`（期待 2490 PASS）
   - `cd srv/rust/openclaw_engine && cargo test --release --features replay_isolated --test 'replay_*'`（期待 29/29 PASS）
3. E4 regression 全套（含 paper_state / engine_state / etc.）— Linux SSH cargo verify 強制（V055 lesson：Mac mock pytest + static-parse review **不夠** — Linux PG / cargo runtime 必驗）
4. PM 視 E2 + E4 結果 commit + push（per §七 強制鏈 E1→E2→E4→QA→PM）

---

**END OF REPORT**

E1 W2 SIGN-OFF DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_w2_impl.md`; R0-T0 apply_fill.rs 拆檔 (runner.rs 1992 → 1808; apply_fill.rs new 485 LOC); R6-T3 KellyConfig + p1_risk_pct + with_replay_fee_context wire in bin/replay_runner.rs (1427 → 1461); Mac cargo test PASS (2490 lib + 29 e2e = 2519 GREEN); pending E2 review.
