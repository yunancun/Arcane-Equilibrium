# PA Design — P0 Option A SSoT Refactor 評估報告

**日期**：2026-05-11
**Author**：PA (Project Architect)
**Operator 問題**：22:08 watchdog Auto restart 後，5 策略本地 `self.positions` 清空，與 paper_state 從 Bybit re-sync 拿回真實倉位脫鉤；多策略 same-tick race + bb_reversion 寬 exit zone 觸發 cross-strategy mass scalp（grid 開、bb_reversion 平、close_tag=bb_mean_revert）。
**Operator 決策**：採用 Option A 單一方案，消除策略本地 position state，全部以 paper_state 為 SSoT。

## TL;DR — 給 Operator 的核心結論

**結論：Option A 有未預見的嚴重副作用，不能 atomic 部署。建議分層止血 + 限縮 Option A 範圍**

| 子問題 | go/no-go | 理由 |
|---|---|---|
| 5 策略統一消除 self.positions | ❌ **NO-GO** | grid_trading 用 `net_inventory: HashMap<String, f64>` 累積 qty（-2/-1/0/+1/+2 grid level），**paper_state 沒有 grid-level 累積資訊**，無法用 paper_state.qty 取代；bb_breakout 的 `entry_price + trailing_stop` 與 position lifecycle 強耦合，paper_state 沒提供 entry_price 給策略用。直接套 Option A 會破 grid_trading 訊號邏輯 + bb_breakout trailing-stop math。 |
| ma_crossover + bb_reversion 改用 paper_state | ⚠️ **CONDITIONAL GO** | 兩策略 `positions: PerSymbolState<bool>` 純粹是 direction marker，**可**直接以 `ctx.position_state` 取代。但**必同時**改 exit gate：加 `ctx.position_state.owner_strategy == self.name()` 才能 exit，否則 W7-2 同 bug 仍會出現（exit 分支被 cross-strategy 倉位觸發）。 |
| bb_breakout state 化簡 | ⚠️ **CONDITIONAL GO** | 移除 `BbBreakoutPerSymbolState.position`，改查 `ctx.position_state`；但 `entry_price / trailing_stop / squeeze_detected_ms / oi_buffer` 必保留（strategy-internal state）。新增 `owner_strategy` gate。 |
| grid_trading 不動 self.net_inventory | ✅ **GO with TWEAK** | net_inventory 是 grid level 累積，不能搬到 paper_state；但加 `ctx.position_state.owner_strategy == "grid_trading"` gate 在 entry path（防 ma/bb 寫過的 paper_state 倉位觸發 grid 認為已有 inventory）。 |
| funding_arb（dormant） | ✅ **GO as part of bb_reversion wave** | active=false 但結構需保持與 sibling 一致，避免 future re-enable 時帶舊 bug。 |
| **緊急止血**（≠ Option A） | ✅ **IMMEDIATE-GO** | **強烈建議先做**：bb_reversion 縮 exit_pctb_lower 從 0.2 → 0.05 + exit_pctb_upper 0.8 → 0.95，並 hot-fix on_tick 加 owner_strategy gate。30 分鐘可部署，救 operator 連續虧損。 |

**confidence go/no-go = 65% NO-GO atomic Option A**；推薦的「Option A-Lite」（ma_crossover + bb_reversion 改 paper_state SSoT + bb_breakout 加 owner_strategy gate + grid_trading 加 owner_strategy gate）= 85% GO。

**E1 IMPL 預估時間**：Option A-Lite 全套 5-7 小時（含測試遷移）；緊急止血 hot-fix 30 分鐘獨立。

**發現副作用清單**：見 §7（共 8 項，3 項 BLOCKER，5 項 watch）。

---

## 1. 5 策略 audit table

| 策略 | 本地 position state 結構 | 是否能直接以 paper_state 取代？ | 阻礙 |
|---|---|---|---|
| `ma_crossover` | `positions: PerSymbolState<bool>` | ✅ Yes | direction marker only |
| `bb_reversion` | `positions: PerSymbolState<bool>` | ✅ Yes | direction marker only |
| `bb_breakout` | `symbols: PerSymbolState<BbBreakoutPerSymbolState{ position, entry_price, trailing_stop, squeeze_detected_ms, oi_buffer }>` | ⚠️ Partial | position 可取代；其他 4 欄位**必須**保留（trailing-stop math 來源） |
| `grid_trading` | `net_inventory: HashMap<String, f64>` 累積 qty + `last_cross_idx: HashMap<String, usize>` | ❌ No | net_inventory = grid level signed sum，**不是 boolean**；paper_state 不含 grid-level 累積 |
| `funding_arb` | `positions: PerSymbolState<FundingPosition>` + `prev_positions` + `prev_last_trade_ms` | ⚠️ Dormant | active=false（W-AUDIT-6 retired），結構保留但 wave 內統一 |

### 1.1 W7 family 重複疊加碼盤點

5 策略累積的「自己治自己 race」防護碼：

| 防護碼 | 位置 | 觸發點 | 狀態 |
|---|---|---|---|
| W7-2 Option A (entry-path) | ma_crossover/strategy_impl.rs:264-288, bb_reversion/mod.rs:549-570, bb_breakout/mod.rs:617-647 | `ctx.position_state.is_some()` → sync self.positions + skip | **本次 RCA 的真正 trigger** |
| W7-3 Option B (on_rejection) | ma_crossover/strategy_impl.rs:64-99, bb_reversion/mod.rs:367-404, bb_breakout/mod.rs:407-441 | rejection reason 含 "duplicate_position: already LONG/SHORT" → sync + early return | 1-tick defense，W7-2 之後其實 dead code |
| W7-5 part 1 (on_fill) | ma_crossover/strategy_impl.rs:128-153, bb_reversion/mod.rs:431-449, bb_breakout/mod.rs:328-347, grid_trading/mod.rs:343, funding_arb.rs:388-413 | real fill confirmed → sync self.positions 為 fill direction | redundant 給 entry-path eager mutate 加保險 |
| W7-5 part 2 (import_positions) | 全 5 策略 override，filter `pos.owner_strategy == self.name()` | bootstrap 後從 paper_state 重建 self.positions | cold-start desync 防護 |

**關鍵觀察**：W7-2 「entry-path 同步 self.positions = paper_state.is_long」是這次 mass scalp 的**真正起點**。W7-2 之前，cross-strategy 倉位讓 bb_reversion 持續撞 router gate（每秒幾百次 reject），**但永不進 exit 分支**，所以不會 mass close。W7-2「修好」reject hot loop 後，反而把策略升級成「我認為我擁有所有 cross-strategy 倉位」→ exit zone 觸發 → mass close → cross-strategy attribution mix。

---

## 2. paper_state 介面契約

### 2.1 現有 public API（`paper_state/accessor.rs`）

```rust
pub fn positions(&self) -> Vec<&super::containers::PaperPosition>;
pub fn get_position(&self, symbol: &str) -> Option<&super::containers::PaperPosition>;  // O(1)
pub fn position_exit_snapshot(&self, symbol: &str) -> Option<PositionExitSnapshot>;
pub fn position_count(&self) -> usize;
pub fn positions_mirror(&self) -> Arc<parking_lot::RwLock<HashMap<String, bool>>>;
```

`PaperPosition` 含：`symbol, is_long, qty, entry_price, entry_notional, entry_ts_ms, owner_strategy, entry_context_id` 等。

### 2.2 ctx.position_state 既有注入

`tick_pipeline/on_tick/step_4_5_dispatch.rs:304-306`：

```rust
let position_state = self.paper_state.get_position(sym);  // ← any owner, not self-filtered
let mut iter_ctx = ctx.clone();
iter_ctx.position_state = position_state;
let strategy_actions = strategy.on_tick(&iter_ctx, &alpha_surface);
```

**現狀**：`ctx.position_state` 已是「any owner 視角」（不過濾 owner_strategy）。Option A 的關鍵是**策略要會用 owner_strategy 區分 self vs cross-strategy**。

### 2.3 是否需要新加 paper_state helper？

**不需要新方法**。`ctx.position_state.owner_strategy == self.name()` 就能直接做 self 視角判斷。`get_position()` 已是 O(1) HashMap lookup，不需 `has_any_position` separate API。

---

## 3. Option A vs Option A-Lite 設計對比

### 3.1 純 Option A（operator 提的方案）— 評為不可行

**Operator 假設**：`AFTER`：
```rust
match self.paper_state_owned_position(ctx, ctx.symbol) {
    Some(pos) => { /* exit logic — only fires on positions I own */ }
    None if !ctx.paper_state_has_any_position(ctx.symbol) => { /* entry logic — skip if anyone owns */ }
    None => { /* cross-strategy occupied, skip entry */ }
}
```

**問題**：
1. **grid_trading 的 net_inventory 是累積 qty，不是 boolean**。`paper_state.get_position(sym).qty` 是 absolute qty，不知道是「grid 累積到 level 3」還是「ma 開的單筆倉」。grid signal 邏輯 `net_inventory < 0 → close_short`、`>0 → close_long` 完全依賴本地累積。**用 paper_state 取代 → grid signal 邏輯破**。
2. **bb_breakout 的 trailing_stop 計算依賴本地 entry_price**：`new_stop = ctx.price - atr * mult`，並 ratchet「stop 只升不降」。paper_state.entry_price 可能是其他策略開的（不適用 trailing math），且 paper_state 不存 trailing_stop。**移除 BbBreakoutPerSymbolState → trailing-stop 邏輯消失**。

### 3.2 Option A-Lite（PA 推薦）

**核心觀點**：「self.positions 是 SSoT」這個 framing 太宏觀。真正的 RCA bug 不是「策略持有 position state」，而是「策略 exit gate 沒查 owner_strategy」。修最小可行：

**1. ma_crossover + bb_reversion + funding_arb 改用 ctx.position_state 為 boolean direction marker，移除 self.positions**

```rust
// BEFORE (ma_crossover/strategy_impl.rs:264)
match self.positions.get(ctx.symbol).copied() {
    None => { /* entry */ }
    Some(is_long) => { /* exit */ }
}

// AFTER
let owns = ctx.position_state
    .filter(|p| p.owner_strategy == self.name())  // ← critical owner_strategy gate
    .map(|p| p.is_long);
match owns {
    Some(is_long) => { /* exit — owner-filtered */ }
    None if ctx.position_state.is_some() => {
        // cross-strategy holds; skip entry
        tracing::debug!(/* cross-strategy occupancy */);
        return vec![];
    }
    None => { /* entry — no one owns */ }
}
```

**消除欄位**：`positions: PerSymbolState<bool>`, `prev_position: HashMap<String, Option<bool>>`, `prev_last_trade_ms` 中與 rollback 相關的部分。
**消除函數**：`on_rejection` 中所有 `self.positions.insert/remove`，`import_positions`，`on_external_close` 中 positions.remove，`on_fill` 中 positions.insert（W7-5 part 1）。
**保留**：`cooldown`, `persistence`, `prev_last_trade_ms`（cooldown rollback 用，與 positions 解耦），`exit_persistence`。

**2. bb_breakout 部分化簡**

```rust
// BEFORE
let current_position = self.symbols.get(sym).and_then(|s| s.position);

// AFTER
let current_position = ctx.position_state
    .filter(|p| p.owner_strategy == self.name())
    .map(|p| p.is_long);

// Exit/Entry path 用 current_position 判斷分支；
// trailing_stop/entry_price/squeeze_detected_ms/oi_buffer 仍走 self.symbols（保留）
```

**消除欄位**：`BbBreakoutPerSymbolState.position`（剩 entry_price/trailing_stop/squeeze_detected_ms/oi_buffer）。
**保留欄位**：trailing-stop math 需要的 4 個欄位。
**新增**：bb_breakout 平倉時不只清 `st.position = None`，要清 `st.entry_price + trailing_stop` 維持原行為。

**3. grid_trading 不動 net_inventory**

```rust
// AFTER (grid_trading/signal.rs:160)
let cross_strategy_holds = ctx.position_state
    .filter(|p| p.owner_strategy != "grid_trading" && p.owner_strategy != "bybit_sync")
    .is_some();
let would_open = (is_down_cross && cur_inventory >= 0.0) || (is_up_cross && cur_inventory <= 0.0);
if would_open && cross_strategy_holds {
    debug!(symbol = sym, "skip grid new entry: cross-strategy position holds");
    return vec![];
}
// rest unchanged
```

**理由**：grid 的 net_inventory 是 grid 自己的「我認為我累積到哪個 level」，不應該被 ma/bb 開的倉位干擾。但**不能**用 ctx.position_state 取代 net_inventory（不同 semantics）。

**4. funding_arb（dormant）**

維持結構與 ma_crossover/bb_reversion 同步（移除 self.positions），避免 future re-enable 時帶 cross-strategy bug；活躍邏輯仍 dormant 不觸發。

---

## 4. on_rejection / on_external_close / on_fill / import_positions 化簡

### 4.1 ma_crossover + bb_reversion

| Hook | BEFORE | AFTER |
|---|---|---|
| `on_rejection` | W7-3 Option B duplicate_position sync + W7-3 fallback rollback prev_position | **no-op**（self.positions 不存在）。cooldown rollback 仍保留：`self.prev_last_trade_ms` 還原 cooldown（與 positions 解耦） |
| `on_external_close` | `self.positions.remove(symbol)` | **no-op** |
| `on_fill` (W7-5 part 1) | `self.positions.insert(intent.symbol, intent.is_long)` | **no-op**（paper_state.apply_fill 已寫入，策略下 tick 自然從 ctx.position_state 讀） |
| `import_positions` (W7-5 part 2) | filter `pos.owner_strategy == self.name()` → rebuild self.positions | **no-op**（策略下 tick 自然從 ctx.position_state 讀） |

**LOC 估算**：每策略移除約 80-120 LOC（W7-2 entry block + W7-3 rejection block + W7-5 兩 part + prev_position field 相關 lifecycle）。

### 4.2 bb_breakout

| Hook | BEFORE | AFTER |
|---|---|---|
| `on_rejection` | `BbBreakoutPerSymbolState.position = ...` sync + prev_state rollback | **only rollback non-position fields**（entry_price/trailing_stop/squeeze_detected_ms/oi_buffer 仍需 rollback） |
| `on_external_close` | `st.position = None` + 其他清空 | **clear entry_price + trailing_stop**（保持 lifecycle 一致）；不動 squeeze_detected_ms（squeeze 是 entry 訊號狀態，與 position 解耦） |
| `on_fill` (W7-5 part 1) | `st.position = Some(intent.is_long)` | **no-op for position**；entry_price/trailing_stop 在 entry path 已寫 |
| `import_positions` | rebuild self.symbols.position from paper_state | **no-op for position**；entry_price/trailing_stop 無 paper_state 對應，bootstrap 後第一次 tick re-entry 時才寫 |

### 4.3 grid_trading

| Hook | BEFORE | AFTER |
|---|---|---|
| `on_rejection` | rollback `net_inventory, last_cross_idx, last_trade_ms` | **不變**（rollback 是必要的） |
| `on_external_close` | reset `net_inventory[sym] = 0.0` | **不變** |
| `on_fill` | currently inventory 在 cross signal 已寫，on_fill confirmed log only | **不變** |
| `import_positions` | rebuild net_inventory（owner_strategy == "grid_trading" filter）| **不變**（grid 必須知道自己 level） |

**新增**：entry path 加 cross_strategy_holds gate（§3.2 #3）。

---

## 5. 測試遷移

### 5.1 現有測試數

| 檔 | tests | 受影響 |
|---|---|---|
| ma_crossover/tests.rs | 93 | ~50 直接 mock self.positions / prev_position |
| ma_crossover/tests_a1_a2_maker.rs | 38 | ~5 |
| bb_reversion/tests.rs | 95 | ~45（含 W7-2/W7-3/W7-5 7 個 test 直接驗 self.positions sync） |
| bb_breakout/tests.rs | 96 | ~30（position-related） |
| bb_breakout/tests_oi.rs | 28 | ~2 |
| bb_breakout/tests_p1_11.rs | 42 | ~5 |
| grid_trading/tests.rs | 88 | ~10（加 cross_strategy gate test） |
| funding_arb（檔內）| ~30 | ~15 |
| **Total** | **~510** | **~162 受影響** |

### 5.2 遷移策略

| Test 類別 | 處理 |
|---|---|
| `s.positions.insert(...)` 設前置條件 → 改 `paper_state` mock | 改寫 約 100 tests |
| W7-2/W7-3/W7-5 系列 sync 驗證 test | **刪除**（功能消失） |
| Cooldown / persistence / signal logic test | 保留不動 |
| Cross-strategy desync test | 增 1-2 個 acceptance test（§6） |
| Mock helper | 新增 `mock_ctx_with_position(symbol, owner, is_long)` helper 在 strategies/common/ |

**新 helper signature**：
```rust
pub fn mock_ctx_with_paper_position(
    ctx_base: TickContext<'_>,
    symbol: &str,
    owner_strategy: &str,
    is_long: bool,
    qty: f64,
) -> TickContext<'_> { ... }
```

### 5.3 race 自癒 acceptance test

```rust
#[test]
fn cross_strategy_race_self_heals_after_one_rejection() {
    // Setup: 2 strategies (ma + bb_reversion) same-tick signal LONG BTCUSDT
    // Step 1: paper_state empty, both emit Open intents
    // Step 2: router accepts ma_crossover (first), rejects bb_reversion (duplicate_position)
    // Step 3: paper_state.apply_fill writes ma_crossover position
    // Step 4: next tick — ctx.position_state for bb_reversion = ma_crossover position
    //         (cross-strategy)
    // Verify: bb_reversion.on_tick returns 0 actions (skip entry, not exit) for next 100 ticks
    // Verify: 無重複 reject, 無 cross-strategy exit
}

#[test]
fn bb_reversion_does_not_close_grid_position_on_pctb_zone() {
    // Setup: paper_state has grid_trading LONG BTCUSDT, owner_strategy="grid_trading"
    // Tick: bb.percent_b = 0.5 (在 bb_reversion exit zone [0.2, 0.8])
    // Run bb_reversion.on_tick
    // Verify: 0 Close actions emitted（owner_strategy != bb_reversion, skip exit）
}
```

---

## 6. 部署順序 + risk 分級

### 6.1 緊急止血（**強烈建議先做，不等 Option A-Lite IMPL**）

**Phase 0 — 30 分鐘 hot-fix（停損優先，operator 連續虧損 9h+）**：

| Hot-fix | LOC | 風險 | 效果 |
|---|---|---|---|
| bb_reversion exit zone 從 [0.2, 0.8] 縮到 [0.45, 0.55]（textbook 0.5 ± 0.05）| ~3 LOC TOML edit | 低（strategy_params_demo.toml）| 立即降低 mass close 概率（exit 機會 70% → 10%）|
| bb_reversion on_tick 加 owner_strategy gate（不等 SSoT 重構）| ~10 LOC | 中 | 從根源阻 cross-strategy mass close |

**部署**：bash + TOML edit + restart_all --rebuild --keep-auth，**不需要重訓任何 ML model**。

### 6.2 Option A-Lite 部署 wave 設計

**選項 A：分 3 wave**
- Wave 1（最低風險先）：funding_arb（dormant，active=false，無 runtime impact）→ 驗證 trait + ctx.position_state 改動可行
- Wave 2（中風險）：bb_breakout（active=true demo only）+ grid_trading（加 cross_strategy_holds gate，最小改動）
- Wave 3（高風險）：ma_crossover + bb_reversion atomic 部署

**選項 B：atomic 5 策略一次部署**
- pros：避免 3 wave 期間「部分策略改了，部分沒改」的 hybrid state；blast radius 一次性 contained
- cons：blast radius 大，rollback 整個 binary

**PA 推薦**：**選項 A 分 3 wave**。理由：
1. funding_arb dormant 是純 trait-level 驗證，零 runtime impact，可作為 smoke
2. Wave 2 改 bb_breakout/grid_trading（小改動）讓 binary 端到端 build pass，驗證 W7-* hook removal 不破其他模塊
3. Wave 3 atomic ma + bb_reversion（changeset 最大）有前面 wave smoke 鋪墊
4. Operator 已連續虧損 9h+，**Phase 0 緊急 hot-fix 與 Wave 1 並行做**，hot-fix 30 分鐘可下，Wave 1 funding_arb dormant 驗證可同時跑

### 6.3 是否一次性 atomic 部署

不推薦。理由：4757 LOC 跨 8 個 file 的 changeset 同次 commit 風險過高，rollback 困難。但**hot-fix 必須先下**，不等 Option A-Lite。

---

## 7. 副作用清單（極重要 — operator 擔心多 gate 副作用，這節是 push back 主軸）

| # | 副作用 | 嚴重度 | 對策 |
|---|---|---|---|
| 1 | **bb_breakout entry_price + trailing_stop 必須保留 strategy 端** | **BLOCKER** | Option A-Lite 設計：移除 BbBreakoutPerSymbolState.position 但保留其餘 4 欄位 |
| 2 | **grid_trading net_inventory 是 grid-level 累積，paper_state 不含此資訊** | **BLOCKER** | grid_trading 不動 net_inventory；只加 cross_strategy_holds gate |
| 3 | **on_external_close 對 strategy-internal state（trailing_stop/squeeze/oi_buffer/grid level）的 cleanup 仍需要** | **BLOCKER** | 保留 on_external_close override（不只是 no-op）；清 lifecycle 強耦合的本地 state |
| 4 | **owner_strategy 在 multi-fill 情境變動**：grid_trading 開 LONG，被 router_close 平掉，重新被 ma_crossover 開 LONG → paper_state.owner_strategy = "ma_crossover"。bb_reversion 之前 tick 看到 "grid_trading" 跳過 exit，下 tick 看到 "ma_crossover" 仍跳過 exit（正確）。但若 bb_reversion 自己這時 emit Open，paper_state 仍 "ma_crossover" owner → bb_reversion 的 cross_strategy gate skip entry → bb_reversion 永遠進不去這個 symbol。 | 中 | 設計為 acceptable trade-off：cross-strategy 持倉時 strategy 主動 backoff；symbol 真釋放後（close）自動恢復 entry。記憶體中 1-2 tick gap acceptable |
| 5 | **ctx.position_state.owner_strategy == "bybit_sync" / "orphan_adopted" 的處理**：boot 後 bybit_sync 寫的倉位 owner = "bybit_sync" 不對應任何策略；策略應該視為「未知 owner」如何處理？ | 中 | 預設策略視 "bybit_sync" 為 cross-strategy（skip entry, no exit）— 等 next fill 自然 attribute |
| 6 | **paper_state.get_position O(1) HashMap vs self.positions.get O(1) HashMap 性能**：理論 0 差，實際 ctx.position_state 是 borrow，不需第二次查詢 | 低 | 0 性能 regression；測試確認 cargo bench |
| 7 | **paper_state inner lock 不存在**（PaperState 是 owned by TickPipeline，&mut self exclusive borrow）；策略 on_tick 透過 ctx.position_state borrow 是 read-only，無 contention | 低 | NLL 已 per-iteration 釋放 borrow（step_4_5_dispatch.rs:300-307 註解確認）|
| 8 | **测試 LOC 變動 162/510 = 32%，未發現的 mock dependence 可能在 IMPL 階段暴露** | 中 | E1 IMPL 第一步先跑 `cargo test -p openclaw_engine --no-run` 找 mock test 失敗清單，E4 regression 階段再 fix |

**結論**：移除策略本地 state 「全靠 paper_state SSoT」**不可行**（#1 #2 #3 BLOCKER）。Option A-Lite 是唯一可行路徑。

---

## 8. E1 IMPL 完整 spec

### 8.1 File 改動清單

| 檔 | 預估改動 LOC | 主要改動 |
|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | -120 / +40 | 移除 self.positions / prev_position；加 owner_strategy gate |
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/mod.rs` | -15 / +0 | 移除 positions/prev_position field + import |
| `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | -150 / +50 | 同 ma_crossover；exit zone gate 加 owner_strategy |
| `srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs` | -80 / +30 | 移除 PerSymbolState.position；保留 entry_price/trailing_stop/squeeze/oi_buffer；exit 加 owner_strategy gate |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/signal.rs` | -0 / +20 | 加 cross_strategy_holds gate；不動 net_inventory |
| `srv/rust/openclaw_engine/src/strategies/funding_arb.rs` | -100 / +30 | dormant 仍同步 trait 化簡 |
| `srv/rust/openclaw_engine/src/strategies/mod.rs` | -20 / +5 | Strategy trait 改動：`import_positions` default no-op 不變；W7-5 doc 重寫成「strategies should NOT track position state locally」|
| `srv/rust/openclaw_engine/src/strategies/common/mod.rs`（如有）| +30 | 新增 test mock helper `mock_ctx_with_paper_position` |
| 5 個 `tests.rs` + `tests_*.rs` | ~162 tests 改寫，~30 W7-* tests 刪除 | mock 改用 ctx.position_state + paper_state mock |
| `srv/settings/strategy_params_demo.toml` | ~5 LOC | bb_reversion exit_pctb_lower=0.45, exit_pctb_upper=0.55（Phase 0 hot-fix）|

**Total LOC**：約 -485 / +205 net -280 LOC + 162 tests 改寫。

### 8.2 E1 並行派發設計

| E1 instance | 工作 | 阻塞關係 |
|---|---|---|
| **E1-A** | ma_crossover refactor + tests | 獨立 |
| **E1-B** | bb_reversion refactor + tests | 獨立 |
| **E1-C** | bb_breakout refactor + tests | 獨立 |
| **E1-D** | grid_trading add cross_strategy_holds gate + tests | 獨立 |
| **E1-E** | funding_arb dormant align + tests | 獨立 |
| **E1-F**（aggregator）| strategies/mod.rs Strategy trait doc 更新 + strategies/common 新增 mock helper | E1-A/B 完成後 merge | 

並行最大度 5（5 個 isolation worktree），加 E1-F merge wave。

### 8.3 部署 SOP

```bash
# Phase 0 hot-fix（30 min 內，先做）
ssh trade-core "vim ~/BybitOpenClaw/srv/settings/strategy_params_demo.toml"
# 改 bb_reversion exit_pctb_lower=0.45 exit_pctb_upper=0.55
ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --keep-auth"

# Wave 1 funding_arb dormant smoke（無 runtime impact）
# E1-E 完成 → E2/E4 → push → ssh restart_all --rebuild --keep-auth

# Wave 2 bb_breakout + grid_trading
# E1-C + E1-D 完成 → E2/E4 → merge → push → restart

# Wave 3 ma_crossover + bb_reversion atomic
# E1-A + E1-B + E1-F 完成 → E2/E4 → merge → push → restart --rebuild --keep-auth
```

每 wave 部署後 30 min 觀察期：
- `[40]` realized_edge_acceptance avg_net trend
- watchdog `attribution_chain_ok` 100% maintained
- `select count(*) from trading.fills where engine_mode='live_demo' and ts_ms > now() - 30 minutes group by strategy_name, exit_reason`  → 確認無 grid+bb_mean_revert 混合

---

## 9. E2 / E4 重點審查 3 點

對抗 E2 reviewer 必看的 3 個盲區：

1. **exit gate owner_strategy 必查**：5 策略中 exit path 都要驗證 `ctx.position_state.owner_strategy == self.name()`，否則 bug 完全沒治。E2 grep `match.*position_state` 或 `Some(is_long)` exit branch 必含 owner check。
2. **bb_breakout entry_price/trailing_stop lifecycle 不能被砍**：E2 grep `BbBreakoutPerSymbolState` 必保留 entry_price/trailing_stop/squeeze_detected_ms/oi_buffer。Position 移除但其餘四 field 不能動。
3. **grid_trading net_inventory 不能被砍**：E2 grep `net_inventory` 必保留所有 read + write。E1-D 工作只是加 cross_strategy_holds gate，不重構 net_inventory。

E4 regression 必跑：
- `cargo test -p openclaw_engine --test '*'` 全綠（162 改寫 tests + 2 新 race 自癒 acceptance test）
- 5 策略 paper-mode smoke：開倉 → cross-strategy ctx visible → exit skip → cooldown not leaked
- benchmark：`cargo bench paper_state_get_position` 確認無 regression（O(1) HashMap）

---

## 10. 風險評估 + 最終 go/no-go

### 10.1 評估矩陣

| 維度 | 純 Option A（operator 提）| Option A-Lite（PA 推薦）| 緊急 hot-fix（Phase 0）|
|---|---|---|---|
| 可行性 | ❌ grid + bb_breakout 阻 | ✅ 已驗 5 策略 audit | ✅ 純 TOML + owner_strategy gate |
| 風險評級 | 極高（架構級重寫）| 高（5 策略 5-7h IMPL）| 低（30 min TOML + 10 LOC）|
| 救火即時性 | ❌ 7h+ 無法救 9h 虧損 | ⚠️ wave 部署 1-2d | ✅ 30 min 止血 |
| Rollback 成本 | 全 binary | 每 wave 獨立 rollback | TOML revert |
| 預估 IMPL 工時 | 不可行 | 5-7h（5 E1 並行）| 30 min |
| Confidence | 65% NO-GO | 85% GO | 95% GO |

### 10.2 最終建議

**立即執行（30 min 內，Phase 0 hot-fix）**：
1. bb_reversion exit_pctb_lower/upper 收窄到 [0.45, 0.55]
2. bb_reversion on_tick 加 `ctx.position_state.owner_strategy == "bb_reversion"` exit gate（直接 patch，不等 SSoT 重構）
3. ssh restart_all --rebuild --keep-auth
4. 30 min 觀察 [40] avg_net + fills 分組計數

**後續執行（Wave 1-3，5-7h IMPL + 1-2d 漸進部署）**：
Option A-Lite 5 策略統一加 owner_strategy gate + 移除 ma/bb_reversion/funding_arb 的 self.positions（純 boolean direction marker），保留 bb_breakout strategy-internal state + grid_trading net_inventory。

**Operator 你要回我**：
1. ✅ / ❌ Phase 0 hot-fix 30 min ship？
2. ✅ / ❌ Option A-Lite 5 策略 wave 部署？或 ❌ 你還是要堅持純 Option A，那我們需要設計 paper_state 新增 grid_level/trailing_stop columns（再 +2-3d 工作量）？
3. ✅ / ❌ E1 5 並行派發？

---

## 附錄 A — RCA 補強

**Operator 已驗 RCA**：22:08 May 10 watchdog Auto restart 後 self.positions 清空 + paper_state re-sync 真實倉位 + multi-strategy race + bb_reversion 寬 exit zone 觸發 mass scalp。

**PA 補強發現**：
1. **W7-2 sync self.positions 自己是 bug trigger**：W7-2「治本 cross-strategy desync」反而把策略升級成「我認為我擁有所有 cross-strategy 倉位」→ 下 tick 走 exit 分支 → bb_reversion 寬 exit zone mass close
2. **emit_close_fill owner attribution**：`pipeline_helpers.rs:222-226`，`db_strategy_name = exit_snapshot.owner_strategy`（paper_state 真實 owner = grid_trading）+ `db_exit_reason = bb_mean_revert`（從 close intent reason）→ 解釋為何 fills 表出現 strategy=grid_trading + exit_reason=bb_mean_revert 的混合 row。
3. **可重現條件**：任何 2+ 策略 same-tick 對同 symbol 都有 entry signal + 一個 fill + 另一個 W7-2 sync。22:08 觸發是因為 restart 同時清空 5 策略，「same-tick race window」放大到 first-tick-post-restart 全部 25 symbols 同時暴露。

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md
