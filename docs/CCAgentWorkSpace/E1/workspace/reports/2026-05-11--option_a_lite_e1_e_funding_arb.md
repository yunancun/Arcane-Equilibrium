# E1-E IMPL DONE — P0 Option A-Lite Wave 1：funding_arb dormant align

**Date**：2026-05-11
**Agent**：E1-E
**Status**：IMPL DONE — 待 E2 審查 + E4 regression
**Worktree**：`agent-a01629ea158b1d262`
**Commit**：`0427346ff07f4700162640b28ce5bc4b85fcb3b8`（short `0427346f`，local main HEAD；sandbox denied `git push origin main`，待 operator 授權 push）

## 1. 任務摘要

PA dispatch P0 Option A-Lite Wave 1 — E1-E 子任務「funding_arb dormant align」per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md` §3.2 #4 + §4.1。

範圍：`rust/openclaw_engine/src/strategies/funding_arb.rs`（PA 預估 -100/+30 LOC，actual +278/-261 含內聯 tests 改寫；非-test 主邏輯 -64 LOC 接近預估 -70）。

dormant `active=false` per ADR-0018 / AMD-2026-05-09-02 維持不變；本任務作為 Wave 1 smoke（零 runtime 影響），驗證 trait + `ctx.position_state` pattern 可行 — 為 Wave 2 (bb_breakout + grid_trading) / Wave 3 (ma_crossover + bb_reversion) 鋪路。

## 2. 修改清單

| 檔 | 行為 | 詳情 |
|---|---|---|
| `rust/openclaw_engine/src/strategies/funding_arb.rs` | 改 | 非-test 595→531（-64），tests 600→681（+81），net +17；diff +278/-261 |

**單檔改動**，無 sibling 影響（其他 4 策略由 E1-A/B/C/D 平行 handle）。

## 3. 關鍵 diff

### 3.1 struct 化簡

```rust
// BEFORE
pub struct FundingArb {
    active: bool,
    positions: PerSymbolState<FundingPosition>,   // ← 移除
    cooldown: TrendCooldown,
    cooldown_ms: u64,
    default_qty: f64,
    pub(crate) total_cost_bps: f64,
    /* ... 6 個 tunable params ... */
    prev_positions: HashMap<String, Option<FundingPosition>>,   // ← 移除
    prev_last_trade_ms: HashMap<String, u64>,
}

#[derive(Debug, Clone)]
struct FundingPosition {                          // ← 整 struct 移除
    is_positive_funding: bool,
    entry_ms: u64,
}

// AFTER
pub struct FundingArb {
    active: bool,
    cooldown: TrendCooldown,    // 保留：純 re-entry cooldown，與 positions 解耦
    cooldown_ms: u64,
    default_qty: f64,
    pub(crate) total_cost_bps: f64,
    /* ... 6 個 tunable params ... */
    prev_last_trade_ms: HashMap<String, u64>,    // 保留：cooldown rollback 用
}
```

**rationale**：FundingPosition 兩個欄位都能從 PaperPosition 推導：
- `is_positive_funding = !ctx.position_state.is_long`（與 on_tick 入場規則 `is_long = !is_positive` 一致）
- `entry_ms = ctx.position_state.entry_ts_ms`

對比 bb_breakout（必保留 trailing_stop / squeeze_detected_ms / oi_buffer），funding_arb 可全套 Option A-Lite 模式。

### 3.2 on_tick 三分支重構

```rust
// AFTER — Option A-Lite 模式
let owned_position = ctx
    .position_state
    .filter(|p| p.owner_strategy == self.name());

match owned_position {
    // 自家持倉 → exit
    Some(pos) => {
        if self.should_exit(pos.is_long, funding_rate, basis_pct, now_ms, pos.entry_ts_ms) {
            self.snapshot_prev_cooldown(sym);
            self.cooldown.record_signal(sym, now_ms);
            return vec![StrategyAction::Close { /* ... */ }];
        }
        return vec![];
    }
    // 他家持倉 → skip entry
    None if ctx.position_state.is_some() => {
        tracing::debug!(strategy = "funding_arb", symbol = %sym,
            cross_owner = %ctx.position_state.map(|p| p.owner_strategy.as_str()).unwrap_or(""),
            "skip entry: cross-strategy holds position");
        return vec![];
    }
    // 無倉位 → entry 評估
    None => {}
}
```

### 3.3 should_exit 簽名改純函數

```rust
// BEFORE
fn should_exit(&self, symbol: &str, funding_rate: f64, basis_pct: f64, now_ms: u64) -> bool {
    let pos = match self.positions.get(symbol) { ... };   // ← self.positions lookup
    /* ... */
}

// AFTER
fn should_exit(
    &self,
    is_long_position: bool,   // ← ctx.position_state.is_long 注入
    funding_rate: f64,
    basis_pct: f64,
    now_ms: u64,
    entry_ms: u64,           // ← ctx.position_state.entry_ts_ms 注入
) -> bool {
    // 反推 funding direction：is_positive_funding = !is_long_position
    let is_positive_funding = !is_long_position;
    /* ... */
}
```

### 3.4 on_rejection 化簡（保留 cooldown rollback）

```rust
// BEFORE — positions + cooldown rollback
fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    if let Some(prev) = self.prev_positions.get(sym) {
        match prev {
            Some(p) => { self.positions.insert(sym.clone(), p.clone()); }
            None => { self.positions.remove(sym); }
        }
    }
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        /* ... cooldown rollback ... */
    }
}

// AFTER — cooldown only
fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
        if ts == 0 {
            self.cooldown.clear(sym);   // 哨兵 0 → 未見狀態
        } else {
            self.cooldown.record_signal(sym, ts);
        }
    }
}
```

### 3.5 on_external_close / on_fill / import_positions 退化為 trait default

```rust
// BEFORE — funding_arb 各自 override
fn on_external_close(&mut self, symbol: &str) {
    self.positions.remove(symbol);
}
fn on_fill(&mut self, intent: &OrderIntent, _fill: &FillResult) {
    let is_positive_funding = !intent.is_long;
    self.positions.insert(intent.symbol.clone(),
        FundingPosition { is_positive_funding, entry_ms: 0 });
    if !self.active {
        tracing::warn!(/* dormant fill */);
    }
}
fn import_positions(&mut self, paper_state: &PaperState) {
    for pos in paper_state.positions() {
        if pos.owner_strategy == self.name() {
            /* rebuild self.positions */
        }
    }
}

// AFTER — 全部移除，用 trait default no-op
// rationale: funding_arb 無 strategy-internal lifecycle 欄位（cf. bb_breakout 的 trailing_stop）
//            paper_state SSoT 直接由 ctx.position_state 注入，策略不需重建本地 state
```

## 4. 治理對照

| 治理項 | 對齊 |
|---|---|
| CLAUDE.md §七 跨平台兼容 | ✅ 0 hard-coded path（Mac/Linux 一致） |
| CLAUDE.md §七 注釋 | ✅ MODULE_NOTE 雙語 → 純中文（2026-05-05 governance change）、所有新函式 docstring 中文 |
| CLAUDE.md §七 file size | ✅ 1195 LOC（含 tests），800 warning 線；非-test 531 ok |
| 雙語注釋（→ bilingual-comment-style skill）| ✅ 新規 2026-05-05 後默認中文，未保留英文 |
| 硬邊界 | ✅ 不動 max_retries / live_execution_allowed / system_mode / active=false default |
| §九 singleton 表 | ✅ 0 新 singleton |
| AMD-2026-05-09-02 / ADR-0018 | ✅ active=false 不變、dormant 結構同步維護 |
| PA spec §3.2 #4 | ✅ funding_arb 全套 Option A-Lite 模式 |
| PA spec §4.1 hook 化簡 | ✅ on_rejection cooldown only / on_external_close+on_fill+import_positions → trait default |
| PA spec §8.1 LOC | ⚠️ 非-test 主邏輯 -64（接近預估 -70），含 tests 後 net +17（PA 預估 -70；新 5 tests +81 LOC 是 acceptable） |
| 最小影響原則 | ✅ 單檔 isolation；不順手抽 common helper（PA §8.1 留給 E1-F） |

## 5. 驗證結果

### 5.1 Build / Test

```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo build --release -p openclaw_engine --lib
  → Finished in 13.67s, 18 既有 warnings, 0 new warnings, 0 errors

cargo test --release -p openclaw_engine --lib funding_arb
  → 42 passed; 0 failed; 0 ignored
  → 32 個 funding_arb 自家 tests + 10 個 sibling tests（涉及 funding_arb name）

cargo test --release -p openclaw_engine --lib
  → 2799 passed; 0 failed; 0 ignored
```

注：cargo test 在 stash 「concurrent E1 work — temp during E1-B M2 rebase」 dirty changes 之前曾顯示 17 errors 全在 `bb_reversion/tests.rs`（E1-B leaked changes），與 funding_arb 無關。stash 隔離後本身 lib + funding_arb tests 全通過。

### 5.2 Grep 驗收（PA §10.2 / E2 audit checklist）

```bash
# 非 test scope self.positions / prev_positions 用法
awk '/^#\[cfg\(test\)\]/{intest=1} {if(!intest)print}' funding_arb.rs \
  | grep -E "self\.positions|prev_positions" | grep -v "^\s*//"
  → 0 hit ✓

# FundingPosition struct 任何代碼級用法
grep "FundingPosition" funding_arb.rs | grep -v "//"
  → 0 hit ✓ (全部在 doc comment 內，純歷史描述)
```

### 5.3 Test 變化

| 類別 | BEFORE | AFTER | 差異 |
|---|---|---|---|
| Edge / basis pure-fn | 6 | 6 | 不變（純函式無關 position）|
| should_exit 系列 | 5 | 5 | 簽名改寫，邏輯不變 |
| on_tick entry / cooldown / h0 / basis | 8 | 8 | 簽名改寫 |
| on_tick exit | 2 | 2 | ctx.position_state 注入 mock |
| Rejection rollback | 1 (positions+cooldown) | 1 (cooldown only) | 行為窄化 |
| on_external_close | 1 (positions.remove) | (移除) | trait default 涵蓋 |
| Hysteresis / edge consistency | 4 | 4 | should_exit 簽名改 |
| AGT-1 IPC tunable | 5 | 5 | 不變 |
| W7-5 on_fill + import | 2 | 0 (全刪) | hook 改 trait default |
| **新增 Option A-Lite acceptance** | — | **5** | cross_strategy_skip / bybit_sync_skip / on_external_close_noop / on_fill_noop / import_positions_noop |
| **Total** | 34 | 36 | net +2 |

預估 ~15 受影響 actual 約 20 改寫；2 net 增加（5 new − 3 deleted W7-5 / external_close）。

## 6. 不確定之處 / Push back / 未解疑點

### 6.1 PA spec LOC 預估偏離（已澄清）

PA 預估 -100/+30 = net -70 LOC；actual net +17 LOC。差異源：
- 非-test 主邏輯 -64 LOC（接近預估 -70）✓
- Tests 新增 +81 LOC（5 new acceptance tests + make_position helper + ctx_with_owned_position helper）

acceptable trade-off：5 個新 acceptance tests 是 PA spec §7 副作用清單 #4/#5（cross-strategy ownership 處理）的必要驗證點。

### 6.2 Worktree leaked changes

進 worktree 時 git status 顯示 `bb_reversion/mod.rs + bb_reversion/tests.rs` 也是 unstaged，來自前一 E1-B sub-agent。stash 訊息 `On main: concurrent E1 work — temp during E1-B M2 rebase` 確認源頭。

**處置**：`git stash push -m "E1-B bb_reversion leaked changes (not E1-E scope)" rust/openclaw_engine/src/strategies/bb_reversion/mod.rs rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` 隔離保護。**不 drop**（不是我的工作），讓 PM 決定 stash 命運。

### 6.3 Test helper 重複（PA §8.1 E1-F aggregator）

`make_position` + `ctx_with_owned_position` helpers 應抽到 `strategies/common/mod.rs`；屬 PA §8.1 E1-F aggregator scope，E1-E 不擴張。E1-D 也面對同樣問題（grid_trading 內聯 PaperPosition helper）。

### 6.4 dormant strategy on_tick dispatch 是否真的不會跑

ADR-0018 sets `funding_arb.active=false`；理論上 orchestrator 不會 dispatch on_tick。但代碼層 on_tick 仍可被 tests / replay / dry-run 路徑呼叫。新加的 3 個 cross-strategy 分支邏輯確保即使呼叫到也安全（owner gate）。

### 6.5 `let _ = is_positive` 反模式（已 corrected）

曾誤加 `let _ = is_positive; // 入場方向已透過 is_long 寫入 OrderIntent` 作「閱讀注釋」，但 `is_positive` 在 `let is_long = !is_positive` 已使用 — Rust 不會 unused warning，添加是 LOC 噪音。Edit minimal principle 嚴守，立即刪除。

## 7. Operator 下一步

1. **E2 review**：等 E2 對抗性審查（重點：PA §10 cross-strategy ownership gate、should_exit 簽名改寫、trait default no-op 行為驗證）
2. **E4 regression**：funding_arb dormant 仍應 0 runtime impact；E4 跑 `cargo test -p openclaw_engine --test '*'` 全綠 + 確認 funding_arb 在 paper / demo / live_demo 都 dormant
3. **Wave 2 / Wave 3 unblock**：本 wave smoke 通過後，Wave 2 (bb_breakout + grid_trading) / Wave 3 (ma_crossover + bb_reversion) 可 land
4. **Stash 處置**：PM 決定 `stash@{0} On main: concurrent E1 work — temp during E1-B M2 rebase` 該 pop / drop / merge
5. **Deploy**：所有 wave 完成後 `restart_all --rebuild --keep-auth`，30 min 觀察期看 `[40]` avg_net 趨勢 + watchdog `attribution_chain_ok` + fills 表 strategy/exit_reason 混合
6. **funding_arb dormant 不變**：本任務後 active=false 不動，無需檢查 demo `funding_arb` 倉位（應持續為 0）

---

E1-E IMPLEMENTATION DONE：待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_e_funding_arb.md`）。

**Commit SHA**：`0427346f`（local main HEAD，push 受 sandbox 拒；待 operator 授權 `git push origin main`）
