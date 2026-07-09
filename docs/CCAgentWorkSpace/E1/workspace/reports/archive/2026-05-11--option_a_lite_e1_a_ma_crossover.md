# E1 IMPL DONE — P0 Option A-Lite E1-A：ma_crossover position state SSoT 重構

**Date**: 2026-05-11
**Agent**: E1-A
**Spec source**: PA Option A-Lite plan (`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md`) §3.2 #1 + §4.1 + §8.1 + §8.2 + §9
**Sibling reference**: bb_reversion Phase 0 hot-fix commit `77a52796`
**Branch**: `worktree-agent-a6625ba20ee9efbea` (staged, NOT committed — pending E2 + E4 + PM bundle merge)
**Repo HEAD pre-impl**: `77a52796` (P0 Phase 0 hot-fix deployed PID 1872218)

---

## §1 任務摘要

PA Option A-Lite RCA：22:08 May 10 watchdog Auto restart 後 cross-strategy mass scalp，root trigger 為 W7-2「sync self.positions = paper_state.is_long」把 cross-strategy 倉位升級為「我認為我擁有」→ 下個 tick 走 exit 分支 → bb_reversion 寬 exit zone mass close grid/ma 開的單。

E1-A 範圍：將 ma_crossover 本地 `positions: PerSymbolState<bool>` 完全移除，由 `ctx.position_state` 作為 SSoT。on_tick 用 `owner_strategy == self.name()` filter 區分 self-owned vs cross-strategy，cross-strategy 持倉時 entry path 主動 backoff（不發 entry、不誤觸 exit）。同步退役 W7-2 entry sync block / W7-3 on_rejection duplicate_position 1-tick 防衛 / W7-5 part 1 on_fill / W7-5 part 2 import_positions — 上述功能由 owner_strategy gate 全涵蓋。

**0 跨策略連動**：僅動 ma_crossover/。bb_reversion / bb_breakout / grid_trading / funding_arb 留 E1-B / E1-C / E1-D / E1-E sibling waves。

---

## §2 修改清單 / Files changed

| File | LOC delta | 變更類型 |
|---|---|---|
| `rust/openclaw_engine/src/strategies/ma_crossover/mod.rs` | -15 / +10 | 移除 `positions` field + `prev_position` field + `PerSymbolState` import；雙語注釋說明 SSoT 改造 |
| `rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | -190 / +89 | on_rejection 化簡為 cooldown rollback only；on_external_close 移除 positions.remove；on_fill / import_positions 改用 trait default no-op；on_tick match 改為 `ctx.position_state.filter(owner)` |
| `rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` | -481 / +241 | 移除 W7-2/W7-3/W7-5 test block（10 tests）；改寫 entry+exit sequence tests（4 tests）以注入 ctx.position_state；新增 8 acceptance tests |
| `rust/openclaw_engine/src/strategies/ma_crossover/tests_a1_a2_maker.rs` | -85 / +60 | 4 A1 tests 改寫以注入 self-owned paper_state position；新增 `make_paper_position_a1` helper |
| **Total** | **+400 / -771 net -371 LOC** | 4 files (Rust only，0 Python / 0 SQL / 0 schema 改動) |

LOC sanity（CLAUDE.md §九 800 警告 / 2000 硬限）：

| 檔 | 改造前 | 改造後 | 狀態 |
|---|---|---|---|
| mod.rs | 452 | 452 | <800 ✓ |
| strategy_impl.rs | 454 | 353 | <800 ✓ |
| tests.rs | 1177 | 936 | >800 warn / <2000 hard cap ✓（test file 大量 acceptance + helper） |
| tests_a1_a2_maker.rs | 589 | 630 | <800 ✓ |
| helpers.rs | 271 | 271 | 不動 |
| config.rs | 89 | 89 | 不動 |

---

## §3 關鍵 diff

### 3.1 mod.rs — struct + new() 簡化

```rust
// BEFORE
use super::common::{ConfidenceBuilder, PerSymbolState, TrendCooldown};

pub struct MaCrossover {
    active: bool,
    positions: PerSymbolState<bool>,                  // ← 移除
    cooldown: TrendCooldown,
    ...
    prev_position: HashMap<String, Option<bool>>,     // ← 移除
    prev_last_trade_ms: HashMap<String, u64>,         // ← 保留供 cooldown rollback
    ...
}

// AFTER
use super::common::{ConfidenceBuilder, TrendCooldown};

pub struct MaCrossover {
    active: bool,
    // P0 Option A-Lite (2026-05-11)：本策略不再維護本地 position state。
    // `self.positions` 已移除，由 `ctx.position_state` 作為 SSoT。
    cooldown: TrendCooldown,
    ...
    // P0 Option A-Lite (2026-05-11)：prev_position 移除（rollback 對象消失）。
    prev_last_trade_ms: HashMap<String, u64>,
    ...
}
```

### 3.2 strategy_impl.rs — on_tick match owner_strategy gate

```rust
// BEFORE
match self.positions.get(ctx.symbol).copied() {
    None => {
        if let Some(existing) = ctx.position_state {
            self.positions.insert(ctx.symbol.to_string(), existing.is_long);  // W7-2 sync
            return vec![];
        }
        // entry path (RC-01 + RC-02 + signal + persistence + confluence + intent emit)
        // ... self.positions.insert(ctx.symbol.to_string(), is_long); ← eager mutate
    }
    Some(is_long) => {
        // exit path (reverse cross + exit persistence)
        // ... self.positions.remove(ctx.symbol); ← post-close clean
    }
}

// AFTER
let owns: Option<bool> = ctx.position_state
    .filter(|p| p.owner_strategy == self.name())
    .map(|p| p.is_long);

match owns {
    None if ctx.position_state.is_some() => {
        // Cross-strategy 持倉 → 主動 backoff
        tracing::debug!(target: "ma_crossover", symbol = %ctx.symbol,
            "skip entry: cross-strategy paper_state position holds (P0 Option A-Lite owner gate)");
        return vec![];
    }
    None => {
        // entry path — unchanged business logic（self.positions.insert 移除，cooldown record 保留）
    }
    Some(is_long) => {
        // exit path — unchanged business logic（self.positions.remove 移除）
    }
}
```

### 3.3 strategy_impl.rs — on_rejection / on_external_close 簡化

```rust
// BEFORE on_rejection: ~58 行 W7-3 duplicate_position reason 解析 + RC-04 rollback
// AFTER  on_rejection: ~15 行 cooldown rollback only

fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        if ts == 0 {
            self.cooldown.clear(sym);
        } else {
            self.cooldown.record_signal(sym, ts);
        }
    }
}

// BEFORE on_external_close: positions.remove + persistence.clear + exit_persistence.clear
// AFTER  on_external_close: persistence.clear + exit_persistence.clear（positions field 已消失）

fn on_external_close(&mut self, symbol: &str) {
    self.persistence.clear(symbol);
    self.exit_persistence.clear(symbol);
}

// on_fill / import_positions 不再 override，使用 Strategy trait default no-op
```

### 3.4 tests.rs / tests_a1_a2_maker.rs

**新增 acceptance tests (tests.rs)**：
- `test_cross_strategy_position_skips_entry` — grid_trading owned LONG → ma_crossover skip
- `test_cross_strategy_position_skips_entry_opposite_direction` — grid SHORT → ma LONG signal still skip
- `test_bybit_sync_owner_treated_as_cross_strategy_skip` — bybit_sync owner 也 skip
- `test_on_tick_proceeds_entry_when_paper_state_is_none` — baseline regression
- `test_self_owned_position_triggers_exit_on_reverse_cross` — owner == "ma_crossover" + reverse cross → Close
- `test_self_owned_position_no_exit_when_aligned` — owner == "ma_crossover" + aligned → no Close
- `test_on_rejection_cooldown_rollback_unseen_sentinel` — prev_last_trade_ms=0 → cooldown.clear
- `test_on_rejection_cooldown_rollback_preserves_prior_ts` — prev_last_trade_ms=50000 → cooldown record original
- `test_on_external_close_mutation_does_not_panic` — confirm persistence/exit_persistence cleanup safe

**改寫 entry+exit sequence tests**：4 tests（`test_exit_on_reverse`、`test_regime_filter_allows_exit`、`test_higher_tf_does_not_block_exit`、+ 4 A1 tests）以注入 `ctx.position_state = Some(&pp)` with `owner_strategy: "ma_crossover"` 觸發 exit branch。

**移除**：10 W7-2/W7-3/W7-5 tests（測試已移除功能）。

---

## §4 治理對照

| CLAUDE.md 條文 | 對應 |
|---|---|
| §七 跨平台兼容 | `grep -E '(/home/ncyu\|/Users/[^/]+)' diff` 0 hits ✓ |
| §七 注釋默認中文 | 2026-05-05 governance change：新注釋僅中文（W7-* 為歷史技術名詞）✓ |
| §七 SQL migration Guard A/B/C | N/A (0 SQL change) |
| §七 被動等待 TODO healthcheck | N/A (純 IMPL，無 passive wait) |
| §七 Sign-off git status clean | `git status` 僅顯示 4 file modified 屬本 PR ✓ |
| §八 強制工作鏈 E1→E2→E4→QA→PM | E1 IMPL DONE → 等 E2 review + E4 regression → PM bundle 5 並行 wave commit ✓ |
| §九 LOC 800/2000 | strategy_impl 353<800 / mod.rs 452<800 / tests.rs 936(>800 warn, <2000 hard cap) ✓ |
| §九 Singleton 登記 | N/A (0 新 singleton) |
| 硬約束 max_retries=0 / live_execution_allowed | N/A (純 strategy logic，無 risk_config / authority 改動) |
| `feedback_workflow_audit_chain.md` | E1 staged not committed；等 E2 + E4 → PM 統一 commit + push ✓ |

### Grep 驗收

```bash
# 1. 無 active self.positions 引用（全在 // 注釋說明歷史）
grep -rn 'self\.positions' rust/openclaw_engine/src/strategies/ma_crossover/ | grep -v "// \|//!\|///" → 0 hits ✓

# 2. 無 active prev_position 引用（全在 // 注釋）
grep -rn '\bprev_position\b' rust/openclaw_engine/src/strategies/ma_crossover/ | grep -v "// \|//!\|///" → 0 hits ✓

# 3. W7-2/W7-3/W7-5 markers 全在歷史注釋（活躍代碼 0 觸發）
grep -rn 'W7-2\|W7-3\|W7-5' rust/openclaw_engine/src/strategies/ma_crossover/ | grep -v "// \|//!\|///" → 0 hits ✓
```

---

## §5 測試結果

```
$ cargo build --release -p openclaw_engine --lib
warning: `openclaw_engine` (lib) generated 18 warnings (pre-existing)
    Finished `release` profile [optimized] target(s) in 41.56s

$ cargo test --release -p openclaw_engine --lib ma_crossover
test result: ok. 63 passed; 0 failed; 0 ignored; 0 measured; 2729 filtered out; finished in 0.00s

$ cargo test --release -p openclaw_engine --lib
test result: ok. 2792 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

- **ma_crossover scope**：63/63 PASS（含 9 P0 Option A-Lite acceptance + 5 改寫 entry+exit + 既有 regime/SNR/Phase B/G7-09c/A1/A2/maker tests）
- **全 lib regression**：2792/0/0 — 0 regression（PA spec target ≥ 2785，超達 +7）
- **新功能 verify**：cross-strategy paper_state position 注入時 ma_crossover 0 actions（acceptance test 通過）

---

## §6 不確定之處

1. **on_external_close persistence cleanup 必要性**：PA spec §4.1 寫 "persistence / exit_persistence 仍需清理（signal-time state，與 position lifecycle 強耦合，無 SSoT 替代）" — 保留。但 W-AUDIT-8a Phase B 完成後 alpha source 可能進一步移動 persistence 到 surface 層；屆時 on_external_close 是否還需要清 persistence 待 reconfirm。本 PR 保守保留 ✓。

2. **`bybit_sync` / `orphan_adopted` owner 視為 cross-strategy**：本 PR 把所有 `owner_strategy != self.name()` 都當 cross-strategy 處理（skip entry）。PA spec §7 #5 列「預設策略視 "bybit_sync" 為 cross-strategy（skip entry, no exit）— 等 next fill 自然 attribute」。**待 review 確認**：
   - **(A)** 接受本 PR 行為 — 保守 skip 整個 symbol，等 owner 翻轉
   - **(B)** 額外 carve-out：bybit_sync owner 在 cold-start 後第一次 ma_crossover signal 觸發時「領養」此倉位（owner_strategy 改寫 SSoT）
   - 我傾向 **(A)** — 不主動領養 orphan 是 fail-closed 原則（避免誤接 grid 等其他策略平倉途中的轉移）

3. **持倉中加倉場景**：當 `ctx.position_state.is_some()` 且 `owner_strategy == "ma_crossover"` 時，進入 `Some(is_long)` exit 分支。如果 fast/slow signal 仍同方向（aligned），exit 不觸發 → 0 actions emitted。**這意味著 ma_crossover 改造後不再「自動加倉」** — 之前 entry path 的 `self.positions.insert` 寫入 LONG，下個 tick 走 entry 分支再 emit Open（如 cooldown 過了）。改造後第二筆 entry 撞 owner gate skip entry，需等 paper_state 清倉。E2 評估這是否破壞既有「同向加倉」場景。
   - 我傾向：**Acceptable trade-off** — 預期 ma_crossover entry cooldown 5min + min_persistence 180s，加倉場景在 paper-shadow 數據中發生率低；exit 仍正常觸發（reverse cross）。但需 E4 跑 paper-mode smoke 確認生產 fill 模式無 regression。

4. **cooldown rollback 仍依賴 `prev_last_trade_ms`**：與 positions 解耦的 cooldown state，PA spec §3.2 / §4.1 都明確要保留。本 PR 保留 ✓。

---

## §7 Operator 下一步

### 立即（並行 wave 完成後）

1. **PM 派 E2 review**（per CLAUDE.md §八 強制工作鏈）：
   - owner_strategy gate 邏輯一致性 vs spec §3.2 #1
   - LOC budget vs §九（tests.rs 936 在 warn line >800，待 E2 確認 acceptable）
   - 跨平台 grep 驗收（已 0 hits）
   - 新 8 acceptance tests 覆蓋 PA §5.3 契約是否完整

2. **PM 派 E4 regression**：
   - `cargo test --release -p openclaw_engine --lib` 全 2792 PASS ✓ pre-verified
   - paper-mode smoke：cross-strategy 場景無 actions（owner gate 生效）

3. **PM 等 E1-B/C/D/E/F 全完成後 bundle commit**（per Option A-Lite Wave 3 推薦：atomic 5 策略 deploy）：
   - E1-A (本 PR)：ma_crossover ✓
   - E1-B：bb_reversion 完整 SSoT 化（Phase 0 已 deployed，需擴充 field 移除）
   - E1-C：bb_breakout（保留 entry_price + trailing_stop + squeeze + oi_buffer）
   - E1-D：grid_trading（加 cross_strategy_holds gate，不動 net_inventory）
   - E1-E：funding_arb dormant 結構對齊
   - E1-F：strategies/mod.rs Strategy trait doc + common/ mock helper

### 中期（Sprint N+2 / N+3）

4. **W-AUDIT-8a Phase B/C/D**：alpha surface tier 2-4 wire up 後重新審視 ma_crossover 是否需要 persistence 移動至 surface 層
5. **paper-mode 7d 觀察**：cross-strategy 持倉場景下 ma_crossover backoff 是否有 false-negative（誤跳過合理 entry）

### 不要做

- **不 deploy** 本 PR 單獨 — 5 策略 + F bundle atomic deploy（PA §6.3）
- **不 commit** by E1 — 等 E2 + E4 PASS 後 PM 統一 commit + push
- **不改 cooldown / persistence / confluence / ma_pair 邏輯**（per prompt scoped）
- **不擴大** scope 至兄弟策略檔（E1-B...F 各自負責）

---

## §8 Cross-platform / 跨平台

- 0 user-home 絕對路徑（`grep '/home/ncyu\|/Users/[^/]*ncyu'` → 0 hits）
- 0 Linux-only 依賴新增
- 0 platform-specific API call
- Mac dev / Linux runtime 同源 ✓

---

E1 IMPLEMENTATION DONE: 待 E2 + E4 並行核驗 + PM bundle 5 並行 wave（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_a_ma_crossover.md`）
