# E1-C IMPL DONE — bb_breakout 策略 P0 Option A-Lite 重構

**日期**：2026-05-11
**任務**：bb_breakout strategy 本地 position state 部分重構為 paper_state SSoT
**Spec**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md` §3.2 #2 + §4.2 + §8.1 + §9 #2
**Branch**：`worktree-agent-ad8cba6fb054ce892`
**Files changed**：
- `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs`（+105 / -154 net -49 LOC）
- `rust/openclaw_engine/src/strategies/bb_breakout/tests.rs`（+207 / -225 net -18 LOC）

## 任務摘要

按照 PA 設計（Option A-Lite）對 `bb_breakout` 策略執行 P0 重構：移除 `BbBreakoutPerSymbolState.position` 欄位，position direction 改由 `ctx.position_state`（paper_state SSoT）承載並加 `owner_strategy == self.name()` filter。**保留** entry_price / trailing_stop / squeeze_detected_ms / oi_buffer 四個 strategy-internal 欄位（PA §7 BLOCKER #1）。

PA report §9 重點 1「exit gate owner_strategy 必查」已落實：on_tick 在 entry/exit 分支前用 `.filter(|p| p.owner_strategy == self.name())` 確保只對本策略擁有的倉位走 exit logic；cross-strategy 倉位 + bb_breakout exit signal → 0 actions（acceptance test 涵蓋）。

## 修改清單

### `mod.rs`

| 區段 | 變更 |
|---|---|
| `BbBreakoutPerSymbolState` struct (line 45-71) | 移除 `pub position: Option<bool>` 欄位；docstring 補 P0 Option A-Lite 緣由與保留欄位語義 |
| `position_of()` accessor (原 line 250-255) | **移除**（語義已破壞，position SSoT 在 paper_state） |
| `on_external_close` (line 295-309) | 不再清 `st.position`，但仍清 entry_price / trailing_stop（lifecycle 強耦合）；保留 squeeze_detected_ms / oi_buffer（與倉位解耦）|
| `on_fill` (line 311-326) | **改為 no-op**（position SSoT 已歸 paper_state；entry_price/trailing_stop 由 entry path 寫）|
| `import_positions` (line 328-350) | 只還原 `entry_price`（trailing math 起點）；不再寫 position field；owner_strategy filter 保留 |
| `on_rejection` (line 352-395) | 移除 W7-3 Option B duplicate_position sync 區塊；保留 RC-04 rollback（entry_price/trailing_stop/squeeze_detected_ms/cooldown）+ oi_buffer 活快照 |
| `on_tick` (line 535-918) | 移除 W7-2 Option A entry block 內 `st.position = Some(...)`；用 `ctx.position_state.filter(owner_strategy == "bb_breakout").map(is_long)` 取代 `self.symbols.get(sym).and_then(|s| s.position)`；移除 entry path 結尾 `st.position = Some(is_long)` 與 exit path 結尾 `st.position = None` |

### `tests.rs`

| 測試 | 變更 |
|---|---|
| 新 helper `make_owned_paper_position(symbol, is_long)` | 構建 `PaperPosition { owner_strategy: "bb_breakout" }`，供「entry 後驗 exit」測試注入 |
| `test_atr_trailing_stop_long_exit` / `_short_exit` | 改寫：移除 `position_of()` 斷言；第二+第三 tick 注入 owned paper_state |
| `test_regime_exit` | 改寫：移除 `position_of()` 斷言；第二 tick 注入 owned paper_state |
| `test_pctb_revert_exit` / `test_bw_squeeze_exit` | 改寫：移除 `position_of()` 斷言；第二 tick 注入 owned paper_state |
| `test_phase_b_anti_persistent_triggers_regime_shift_exit` / `_random_walk_triggers_regime_shift_exit` / `_unknown_regime_string_treated_as_random` | 改寫：第三 tick 注入 owned paper_state |
| `test_bbb_on_fill_updates_per_symbol_state_position` → `test_bbb_on_fill_is_no_op_for_strategy_state` | 重寫成 P0 Option A-Lite 不變式驗證（on_fill no-op） |
| `test_bbb_bootstrap_imports_paper_state_positions` → `test_bbb_bootstrap_imports_paper_state_entry_price_only` | 重寫成 P0 Option A-Lite 不變式（entry_price 還原，position field 不存在）|
| W7-3 Option B duplicate_position sync tests（原 #1 #2） | **刪除**（sync 路徑已移） |
| W7-3 Option B fallback tests（原 #3 #4） | 改寫成 RC-04 rollback regression（無 W7-3 sync 階段） |
| W7-2 Option A test #1 / #2 / #3 | 重寫成 P0 Option A-Lite cross-strategy gate + owned exit acceptance（4 tests）|

### 新增 acceptance tests（PA §5.3 自癒契約）

1. **`test_bbb_does_not_close_cross_strategy_position_on_exit_signal`** —
   核心 acceptance：cross-strategy（owner="grid_trading"）持有 LONG BTC，bb.percent_b=0.5
   落在 bb_breakout 的 pctb_revert exit zone [0.2, 0.8]，**必 0 Close**。對應 22:08 mass
   scalp 事件的根因防護（PA §9 重點 1）。
2. **`test_bbb_emits_close_on_owned_position_with_exit_signal`** —
   ower="bb_breakout" 持倉 + exit signal → 必 emit Close（owner_strategy gate 不誤殺本策略）。

## 關鍵 diff

### `BbBreakoutPerSymbolState` struct

```rust
// BEFORE
pub(crate) struct BbBreakoutPerSymbolState {
    pub position: Option<bool>,            // ← 移除
    pub squeeze_detected_ms: Option<u64>,  // ← 保留
    pub entry_price: Option<f64>,          // ← 保留
    pub trailing_stop: Option<f64>,        // ← 保留
    pub oi_buffer: VecDeque<(u64, f64)>,   // ← 保留
}

// AFTER
pub(crate) struct BbBreakoutPerSymbolState {
    pub squeeze_detected_ms: Option<u64>,
    pub entry_price: Option<f64>,
    pub trailing_stop: Option<f64>,
    pub oi_buffer: VecDeque<(u64, f64)>,
}
```

### on_tick 分支判斷

```rust
// BEFORE
let current_position = self.symbols.get(sym).and_then(|s| s.position);
match current_position {
    None => { /* entry */ }
    Some(is_long) => { /* exit */ }
}

// AFTER — owner_strategy gate（PA §9 重點 1）
let current_position = ctx
    .position_state
    .filter(|p| p.owner_strategy == self.name())
    .map(|p| p.is_long);
match current_position {
    None => {
        if ctx.position_state.is_some() {
            // cross-strategy 持倉，skip entry（避免 mis-calibrate trailing）
            return vec![];
        }
        // entry path
    }
    Some(is_long) => { /* exit path — 只對本策略倉位生效 */ }
}
```

### Entry path 結尾（移除 st.position 寫入）

```rust
// BEFORE
let st = self.symbols.get_or_init(sym);
st.position = Some(is_long);    // ← 移除
st.squeeze_detected_ms = None;
self.cooldown.record_signal(sym, ctx.timestamp_ms);
st.entry_price = Some(ctx.price);
if let Some(atr_res) = &ind.atr_14 { ... st.trailing_stop = Some(stop); }

// AFTER
let st = self.symbols.get_or_init(sym);
st.squeeze_detected_ms = None;
self.cooldown.record_signal(sym, ctx.timestamp_ms);
st.entry_price = Some(ctx.price);
if let Some(atr_res) = &ind.atr_14 { ... st.trailing_stop = Some(stop); }
```

## 治理對照

| 治理項 | 狀態 |
|---|---|
| CLAUDE.md §七 雙語注釋（2026-05-05 governance：默認中文）| ✅ 所有新加注釋僅中文；既有中英對照 block 改動時移除英文（如 PerSymbolState struct docstring） |
| CLAUDE.md §七 跨平台路徑硬編碼 | ✅ `grep -E '(/home/ncyu|/Users/[^/]+)' bb_breakout/*.rs` → no hits |
| CLAUDE.md §八「最小影響」 | ✅ 僅動 `bb_breakout/mod.rs` + `tests.rs`；未動 `params.rs` / `runtime_params.rs` / 其他策略；未順手「優化」未要求代碼 |
| CLAUDE.md §九 file size cap (2000 LOC) | ✅ mod.rs 933 行 / tests.rs 1551 行（pre-baseline，已記錄為 high-cohesion test file） |
| CLAUDE.md §九 singleton 管理 | ✅ 未引入新 singleton |
| PA §7 BLOCKER #1（保留 entry_price/trailing_stop/squeeze/oi_buffer）| ✅ 85 hits in mod.rs 保留 |
| PA §9 重點 1（exit gate owner_strategy filter）| ✅ on_tick:549 `.filter(|p| p.owner_strategy == self.name())` |
| PA §9 重點 2（bb_breakout entry_price/trailing_stop 不能被砍）| ✅ struct 內保留；on_external_close / on_rejection 仍會用到 |
| Sprint N+1 W7-1 trait skeleton (`c9fb0b8f`) 兼容 | ✅ `ctx.position_state` 既有 wire 不變；本次只用到 read 端 |

## 不確定之處

1. **`PaperState::new(initial_balance)` 在 test 中的 import path**：用 `crate::paper_state::PaperState`
   通過。**已驗** test 84 passed。
2. **bb_breakout entry path 不再 prev_state.insert position（因 field 不在）**：原 prev_state
   裡舊版含 position；新版 `BbBreakoutPerSymbolState` 結構變了，舊 snapshot 與新 struct 不
   兼容（運行時 prev_state 都是新版 struct 序列化）。**測試確認 rollback 正常**。
3. **Sprint N+1 dispatch v3.7 W7-2/W7-4/W7-5 派發狀態**：本次 P0 Option A-Lite 與這些
   wave 設計可能衝突（W7-* sync 路徑被本次移除）。**建議 PA 在 next wave 派發前 sanity
   check W7-2 spec 是否仍需要**（PA report §9 既有提示「W7-2/W7-3/W7-5 系列 sync 驗證 test
   刪除」）。
4. **`make_paper_position_bbb` 函式 cleanup**：本次新增 `make_owned_paper_position` 與
   `make_cross_strategy_paper_position` 兩個 helper，與原 `make_paper_position_bbb`
   功能重疊但 owner 不同；保留三者供測試明確語義。

## Operator 下一步

1. 等 E2 對 mod.rs + tests.rs 進行對抗性審查（PA §9 三個重點 + 跨平台合規）。
2. 等 E4 跑全 engine regression（`cargo test --release -p openclaw_engine --lib`，
   本地已驗 2796 passed / 0 failed）。
3. PM 統一 commit/push 後，下次 `restart_all --rebuild --keep-auth` 同次部署 5 策略
   一致改造（與 E1-A ma_crossover / E1-B bb_reversion / E1-D grid_trading / E1-E
   funding_arb 組裝為單一 P0 Option A-Lite wave）。
4. Wave 部署後 30 min 觀察：
   - `[40]` realized_edge_acceptance avg_net trend
   - `attribution_chain_ok = 100%`
   - `select count(*) from trading.fills where engine_mode='live_demo' and ts_ms > now() - 30 minutes group by strategy_name, exit_reason` — 確認無 cross-strategy mix
5. 若 Sprint N+1 W7-2/W7-4/W7-5 派發 spec 仍含「sync self.symbols[sym].position」措辭，
   建議 PA 同步更新（本批已從根源移除該欄位）。

## Test 結果

```text
cargo test --release -p openclaw_engine --lib bb_breakout
test result: ok. 84 passed; 0 failed; 0 ignored; 0 measured; 2712 filtered out

cargo test --release -p openclaw_engine --lib
test result: ok. 2796 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```

## Grep 驗收（PA §9 E2 必查）

```text
grep -c "entry_price|trailing_stop|squeeze_detected_ms|oi_buffer" mod.rs → 85 hit（保留 ✓）
grep -n "pub position\b" mod.rs                                       → 0 hit（field 移除 ✓）
grep -n "W7-2|W7-3" mod.rs                                            → 註解 4 處（歷史保留 ✓）
grep -n "owner_strategy" mod.rs                                       → 9 處（核心 gate ✓）
grep -E '(/home/ncyu|/Users/[^/]+)' bb_breakout/*.rs                  → no hits（跨平台合規 ✓）
```

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_c_bb_breakout.md）
