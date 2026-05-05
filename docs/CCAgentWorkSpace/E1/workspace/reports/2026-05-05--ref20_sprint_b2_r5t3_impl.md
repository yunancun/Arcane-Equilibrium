# E1 R5-T3 SIGN-OFF — REF-20 Sprint B2

**Status**: IMPLEMENTATION DONE — pending E2 review + E4 regression
**Source HEAD**: Mac/origin sync from `2a69addb` (R5-T1 + R5-T2 已 land 為 dispatch baseline，當前 working tree 加 R5-T3 兩 file change)
**Scope**: 2 file changes — `rust/openclaw_engine/src/replay/runner.rs` 主要 + `rust/openclaw_engine/src/replay/report_writer.rs` test fixture 補 field
**Persistence**: PM persisted E1 inline report per closure protocol.

---

## §1 IsolatedPipeline struct + ReplayPaperSnapshot + ReplayPosition LOC

| Element | LOC change | Note |
|---|---:|---|
| `runner.rs` (whole file) | 676 → 1466 (+790) | 含 +250 LOC inline R5-T3 tests + 雙語 docstring per method |
| `IsolatedPipeline` struct | +30 LOC（3 new field：`strategy_adapter` / `risk_adapter` / `paper_snapshot`） | + bilingual SAFETY 說明 |
| `with_adapter_pipeline` (NEW setter) | +60 LOC | 含 fail-loud snapshot 驗證 + bilingual docstring |
| `execute_synthetic_walker` (extracted) | +75 LOC | byte-equal 保留 R5-T3 前邏輯（proof_1/4/5 e2e 倚賴） |
| `execute_adapter_pipeline` (NEW) | +100 LOC | strategy → risk → apply_fill 主路徑 |
| `process_open_intent` / `process_close_intent` (NEW) | +70 LOC each | Open 走 6-Gate；Close 查 snapshot.get_position |
| `apply_fill_open` / `apply_fill_close` (NEW) | +90 LOC each | open: insert/extend/reduce 三分支；close: realise PnL |
| `build_tick_context` helper (NEW) | +20 LOC | 0 forbidden surface + bilingual SAFETY |
| `ReplayResult.decision_traces` (NEW field) | +5 LOC | `#[serde(default)]` 確保向後兼容序列化 |
| `ReplayError::InvalidSnapshot` (NEW variant) | +15 LOC | 雙語 doc + Display impl |
| 4 inline R5-T3 unit tests | +250 LOC | NaN reject / empty anchor reject / strategy+risk happy / ghost fill on reject |

**ReplayPaperSnapshot / ReplayPosition**：**0 LOC change**（兩 type 已於 R5-T1+T2 round 在 `risk_adapter.rs` 落地；R5-T3 透過 `crate::replay::risk_adapter::{ReplayPaperSnapshot, ReplayPosition}` import 使用，無需修改）。

**File LOC vs CLAUDE.md §九**：runner.rs 1466 < 1500 hard cap，但已超 800 警告線。建議 PM 比照 commands.rs (1343) / scanner/scorer.rs (1437) 先例 accept high-cohesion exception。push back §8.1。

## §2 execute() body 重寫前後對比

**重寫前**（runner.rs 線 437-511，~75 LOC）：
- 直接走 fixture loop + forbidden_guard runtime + 「每新 symbol 1 entry fill + 後續 mark-to-market」synthetic walker
- 0 Strategy 邏輯，0 Risk 評估
- 返回 `Result<(), ForbiddenPathError>`

**重寫後**（runner.rs 線 ~595-635 主入口 + ~640-720 walker + ~722-820 adapter）：
```rust
pub fn execute(&mut self) -> Result<(), ForbiddenPathError> {
    if self.fixtures.is_empty() {
        self.status = ReplayStatus::AbortedFixtureExhausted;
        return Ok(());
    }
    // Sprint B2 R5-T3: dispatch to adapter path or synthetic walker.
    if self.strategy_adapter.is_some() {
        self.execute_adapter_pipeline()
    } else {
        self.execute_synthetic_walker()
    }
}
```

`execute_synthetic_walker` 為**逐字提取**舊邏輯（保 e2e proof_1/4/5）；`execute_adapter_pipeline` 為新真實 strategy + risk pipeline。

## §3 apply_fill_open + apply_fill_close mutation 邏輯

### apply_fill_open
三分支：
1. **Same-symbol same-direction extend**：rare path（Gate 1.5 應已拒同向加倉）；qty 加總 + 加權平均 entry_price = `(pos.entry × pos.qty + fill_price × new_qty) / total_qty`
2. **Same-symbol opposite-direction reducing**：
   - `qty >= pos.qty`：完整 close + remove，realise per-unit PnL = `(fill - entry)` for long / `(entry - fill)` for short
   - `qty < pos.qty`：partial reduce + 留剩餘倉，realise PnL on partial qty
3. **Fresh open**：push new ReplayPosition（symbol/is_long/qty/entry_price=fill_price）

### apply_fill_close
- 找 position by symbol → remove
- PnL realisation 公式：`(fill - entry) * qty` for long；`(entry - fill) * qty` for short
- `snap.balance += realised_per_unit * pos.qty`
- self.balance mirror 更新

**Sprint A baseline fee=0.0**（CLAUDE.md §三 一致）；Sprint C R6 引入 maker/taker 費率時改此處。

## §4 Fail-loud snapshot construction (F-3 fix)

`with_adapter_pipeline` setter 兩條 fail-loud：

```rust
if !snapshot.balance.is_finite() {
    return Err(ReplayError::InvalidSnapshot {
        reason: format!("balance must be finite f64, got {}", snapshot.balance)
    });
}
if snapshot.latest_price.is_none() && snapshot.positions.is_empty() {
    return Err(ReplayError::InvalidSnapshot {
        reason: "latest_price is None and positions is empty — caller must seed at least one"
    });
}
```

**理由**：
- NaN balance：router.rs/paper_state silent bypass Gate 1.6（`NaN <= 0.0` 為 false），需 fail loud
- 空 latest_price + 空 positions：Gate 2.6 P1 cap = `balance * p1_risk_pct / price` 在 price=0.0 fallback 至 kelly_qty，silent bypass，需 fail loud

新增 4 inline R5-T3 test 中 2 條 (`adapter_pipeline_rejects_nan_balance_snapshot` + `adapter_pipeline_rejects_empty_anchor_snapshot`) 覆蓋。

## §5 forbidden_guard runtime trip 保留證明（E2 §7 #3）

兩 path 都接 forbidden_guard runtime trip：
- `execute_synthetic_walker` line ~656：action="on_event:{symbol}@{ts_ms}"（**逐字** R5-T3 前同邏輯，proof_4 通過）
- `execute_adapter_pipeline` line ~745：action="on_tick:{symbol}@{ts_ms}"（新增；inline test 4 條 ghost-fill 用 single_event fixture 隱含覆蓋此 path 的 guard call）

**驗證**：
```
$ cargo test --release --features replay_isolated -p openclaw_engine --test replay_runner_e2e
proof_4_forbidden_path_trip_via_env_aborts_run ... ok
```

## §6 Proof 4 + Proof 5 e2e test 不退證明

```
running 6 tests
test proof_3_fixture_missing_returns_typed_error ... ok
test proof_2_invalid_manifest_signature ... ok
test proof_1_happy_path_synthetic_fixture ... ok
test proof_helper_signed_manifest_round_trip ... ok
test proof_4_forbidden_path_trip_via_env_aborts_run ... ok
test proof_5_baseline_vs_candidate_two_runs ... ok

test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

**proof_1**：fills.len()==1（單 symbol synthetic fixture，synthetic walker path）— 通過
**proof_4**：forbidden trip via env → AbortedForbidden + abort_reason — 通過
**proof_5**：baseline ≡ candidate net_pnl < 1e-9 — 通過

## §7 cargo build + 54+ replay test + 6 e2e + 414+ symbol + xlang

### cargo build
```
cargo build --release --bin replay_runner --features replay_isolated
   Finished `release` profile [optimized] target(s) in 11.86s
```

### replay:: 全套
```
test result: ok. 58 passed; 0 failed; 0 ignored; 0 measured; 2420 filtered out; finished in 0.00s
```
（54 R5-T1+T2 baseline + 4 NEW R5-T3 = 58）

### Full lib regression
```
test result: ok. 2474 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```
（與 R5-T1+T2 baseline 同數）

### e2e
```
test result: ok. 6 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

### Symbol audit
```
[replay_runner_symbol_audit] symbol count: 478
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected (478 symbols scanned)
```
（414 baseline + 64 R5-T1+T2 = 478；R5-T3 新增 method 全 `pub(super)` / private fn 不 export，故 478 vs E2 review 478 一致）

### Forbidden import grep on runner.rs
```
$ grep -nE 'use crate::(paper_state|canary_writer|database|ipc_server|governance_hub|live_authorization|decision_lease|bybit_rest_client|bybit_private_ws)' runner.rs
(no output — 0 hit)
```

### Cross-platform grep
```
$ grep -nE '/home/ncyu|/Users/[a-z]+/' runner.rs
(no output — 0 hit)
```

### xlang_consistency（驗證限制）
**Mac 端無 venv/pytest**（CLAUDE.md §六：Mac 是開發機，runtime 在 Linux）。**未實際在本 session 跑 Linux Python xlang test**（avoiding pre-review push to origin）。**邏輯推論**：R5-T3 0 改動 `manifest_signer.rs`（Rust）+ 0 改動 `manifest_signer.py`（Python），xlang test 邏輯上不可能退化。Rust 端 manifest_signer 15 inline test 全 PASS（含 fingerprint_matches_helper_script cross-language anchor）。E4 regression 階段 push 至 Linux 後 run pytest 再給 final confirmation。

## §8 git status sign-off-clean

```
$ git status --short
 M rust/openclaw_engine/src/replay/report_writer.rs    ← R5-T3 test fixture 補 decision_traces field
 M rust/openclaw_engine/src/replay/runner.rs            ← R5-T3 主檔
?? docs/architecture/multi_agent_rework_2026-05-05/    ← sibling session 範圍，**非** R5-T3
```

對應 R5-T3 範圍**僅 2 modified file**，clean。

## §9 Push back to PM (3 items)

### §9.1 dispatch §11.1 LOC estimate +200 vs reality +790 — bilingual + 邊界擴展

dispatch §11.1 估 runner.rs +200 LOC；實際 +790 LOC。**Root cause**：
1. 接 strategy + risk + snapshot 三 Optional pair 觸發雙語 SAFETY/不變量 docstring 全部翻倍（CLAUDE.md §七 強制）
2. dispatch §6 設計需 7 個新 method（with_adapter_pipeline / execute_synthetic_walker / execute_adapter_pipeline / process_open_intent / process_close_intent / apply_fill_open / apply_fill_close）+ build_tick_context helper + ReplayError::InvalidSnapshot；每 method 必中英對照
3. dispatch §9 要求 inline test，新增 4 個 R5-T3 test ~250 LOC 計入 file LOC（與 R5-T1+T2 §8.2 同 push back 模式）

**PM decision needed**：
- Option A：accept 1466 LOC（< 1500 hard cap，類比 commands.rs 1343 / scanner/scorer.rs 1437 high-cohesion exception；觸 800 警告線但不破 §九）
- Option B：拆檔 — 把 `apply_fill_*` + `process_*_intent` 抽成 `runner_apply.rs` sibling module；耗 0.5 task 但 LOC 回 ~1000

建議 Option A：runner.rs 內聚性高（adapter wire + state mutation 同責任），拆檔反而要 7 method 來回 import。

### §9.2 ReplayResult.starting_balance 沿用 DEFAULT_STARTING_BALANCE 而非 snapshot.balance

`with_adapter_pipeline` 把 snapshot.balance 鏡射至 self.balance（用於 mark-to-market），但 `into_result` 的 `pnl_summary.starting_balance` 仍硬編 `DEFAULT_STARTING_BALANCE = 10_000.0`，避免破 既有 e2e proof_1/5 對 starting_balance==10_000 的隱含期待。

**未來破壞性升級**：R5-T4 CLI 接此 API 後，可考慮加 `IsolatedPipeline.adapter_starting_balance: Option<f64>` 欄位，`into_result` 回 `adapter_starting_balance.unwrap_or(DEFAULT_STARTING_BALANCE)`。屬 R5-T4 / R5-T5 範圍 push back。

### §9.3 R5-T3 inline test `last_action` 對 multi-event fixture 易破

原想 `adapter_pipeline_records_ghost_fill_on_risk_reject` 用 multi-event synthetic_events()，但 last_action 被後續 ETHUSDT@3 event 覆蓋（fresh open passes Gate 1.5）。改用 single_event fixture。

**啟示**：R5-T7 acceptance test 寫 ghost-fill scenario 時須注意 last_action 是 single-shot semantic（非 cumulative）；建議 acceptance 測 fills array 而非 last_action_label。

## §10 預留問題給 R5-T4/T5/T6/T7

### R5-T4 (CLI integration)
1. 接 CLI args 後構造 ReplayStrategyAdapter + ReplayRiskAdapter 並 call `with_adapter_pipeline`
2. fixture builder 端跑 IndicatorEngine 一次（PA design §13 line 691）；R5-T4 fixture_loader.rs 升級 schema_version 2 含 indicator pre-compute output
3. `event.indicators` Some 後，build_tick_context 傳 `Some(&snapshot.atr_14)` 等
4. snapshot 從 manifest body 構造（balance / 既有 inventory）

### R5-T5 (Python writer)
1. `simulated_fills_writer.py` 寫入 `replay.simulated_fills` table（V050 schema 17 col）
2. `evidence_source_tier IN ('synthetic_replay','calibrated_replay','counterfactual_replay')` 不可作 ML training（CLAUDE.md §九 既登記）
3. ReplayResult JSON 多 `decision_traces` 欄位需 Python writer 對應 schema（payload jsonb 內存）

### R5-T6 (acceptance fixture)
1. R5-T7 plan §6.R5 acceptance：跑兩 manifest（grid_count=10 vs 20）+ 同 fixture → fills count delta + decision_traces[0].actions_emitted[0].intent_signature delta（A4 parameter-delta proof）
2. fixture 必保證 fill ≥1（PA §5.1 確認）+ 不走 Gate 1.5/1.6（用 fresh balance + empty positions）

### R5-T7 (acceptance test)
1. `tests/replay/test_replay_*_smoke.rs` ~200 LOC 含 baseline-vs-candidate cross-language proof
2. 走 spawn binary path（非 lib API direct call），含 manifest signing + key fingerprint round-trip
3. 與 Sprint A precedent 對齊（R3 round 6 final smoke E2E + R8/R9 sentinel）

### 共通
- runner.rs 1466 LOC 已超 800 警告線；R5-T4/T5/T6 任一 task 若再加 LOC 會更逼近 1500 hard cap，建議 R5-T4 階段同步評估拆檔 (Option B in §9.1)

---

## §11 治理對照

- **CLAUDE.md §二 16 條**：✓ 都遵守（單一寫入口 unaffected / 讀寫分離 unaffected / Decision Lease unaffected / Live boundary unaffected / EarnedTrust unaffected）
- **CLAUDE.md §三 真實狀態**：✓ R5-T3 0 改動 trading.* 任一 table；0 改動 18 blocker 任一 gap；0 改動 5 策略 fill 數據
- **CLAUDE.md §四 硬邊界**：✓ 都遵守（max_retries=0 unaffected / live_execution_allowed unaffected / authorization.json path unaffected）
- **CLAUDE.md §七 雙語注釋**：✓ 7 新 method + 1 helper 全中英對照（MODULE_NOTE / docstring / SAFETY / inline 不變量）
- **CLAUDE.md §七 跨平台**：✓ runner.rs 0 路徑硬編碼
- **CLAUDE.md §九 LOC**：⚠ 1466 < 1500 hard cap 但超 800 警告線 — 已 push back §9.1 PM decision
- **CLAUDE.md §九 Singleton 登記**：✓ R5-T3 0 新 singleton（adapter pair 為 instance-level field，非 global）
- **V3 §6.1 + §6.2 + §6.3**：✓ 0 forbidden import on runner.rs；adapter 內部 import path 與 R5-T1+T2 audit GREEN 一致
- **V3 §12 #10 forbidden runtime trip**：✓ proof_4 不退；adapter path 也接 forbidden_guard::enforce_at_runtime
- **V3 §12 #11 execution_confidence='none'**：✓ into_result 仍 hardcode `"none".to_string()`（adapter path 不影響）
- **V3 §12 #12 fail-closed**：✓ snapshot 構造 + with_adapter_pipeline 兩處 fail-loud
- **dispatch §強制規範 1-12**：✓ 全遵守（不動 R0/R1/R2/R3 cleared / 不接 forbidden imports / Strategy+Risk adapter 由 caller 構造 / owned not Arc<Mutex> / fail-loud snapshot / proof_4 + proof_5 不退 / bilingual / 跨平台 / LOC < 1500 / 不 commit / 不動 fixture_loader.rs / 不動 simulated_fills_writer.py）

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_b2_r5t3_impl.md`）**

(Per dispatch §sign-off — parent agent reads E1's final assistant message; PM persisted to .md file.)
