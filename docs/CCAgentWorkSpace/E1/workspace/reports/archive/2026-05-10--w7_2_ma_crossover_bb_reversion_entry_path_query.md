# W7-2 IMPL — ma_crossover + bb_reversion entry path query ctx.position_state

**Date**: 2026-05-10
**Owner**: E1
**Status**: IMPL DONE — NOT COMMITTED, NOT DEPLOYED（PM 21:30 sign-off 後派 deploy）
**Scope**: PA #3 §6 Option A 治本 + W7-4 §3 同 wave bb_reversion apply
**Trigger**: PM 派工 prewrite W7-2 IMPL（D+0 sign-off 後直接收，不需 D+1 重設計）

---

## 0. TL;DR

兩處 strategy 改動，每處增量 entry path 起點查 `ctx.position_state`：
- **ma_crossover**：`strategy_impl.rs:188-218`（None 分支起點 +30 LOC，含 1 條 tracing::debug）
- **bb_reversion**：`mod.rs:449-471`（None 分支起點 +22 LOC，含 1 條 tracing::debug）

7 unit test 全 PASS（4 ma_crossover + 3 bb_reversion）。`cargo build --release --bin openclaw-engine` PASS。`cargo test --lib --release` total 2648/2648 PASS（baseline 2641 + W7-2 新增 7）。

W7-3 Option B 1-tick 防衛（commit `b42731f6`）保留作 reason 字串契約 fallback。

---

## 1. 修改 file + line range

| 檔 | line range | 性質 | LOC |
|---|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | 188-217 (entry None 分支起點 W7-2 check) | new | +30 |
| `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | 449-471 (entry None 分支起點 W7-2 check) | new | +22 |
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` | 833-963 (W7-2 4 test + helper + 1 tracing test rename) | new | +135 |
| `srv/rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` | 1078-1182 (W7-2 3 test + helper) | new | +105 |

無動：TickContext signature（W7-1 已 land）/ router.rs Gate 1.5 / paper_state / W7-3 on_rejection / 其他 3 策略（grid/bb_breakout/funding_arb）。

---

## 2. Code 設計（pseudocode → real diff）

### Part 1: ma_crossover（per PA #3 §6 Option A）

```rust
// strategy_impl.rs:187 match self.positions.get(ctx.symbol).copied()
match self.positions.get(ctx.symbol).copied() {
    None => {
        // ── W7-2 Option A 治本：cross-strategy paper_state 查詢 ──
        if let Some(existing) = ctx.position_state {
            // paper_state 已持倉；同步 self.positions 為 paper_state 真實方向，
            // 下個 tick 直接進 Some(is_long) exit 分支，不再進入 entry path。
            self.positions
                .insert(ctx.symbol.to_string(), existing.is_long);
            tracing::debug!(
                target: "ma_crossover",
                symbol = %ctx.symbol,
                existing_is_long = existing.is_long,
                "skip entry: ctx.position_state present (cross-strategy paper_state holding) — \
                 W7-2 Option A treats as cross-strategy desync, sync self.positions and skip"
            );
            return vec![];
        }

        // 既有 entry path（regime gate / signal / persistence / confluence / make_intent）不動
        if !self.regime_allows_entry(ctx) { return vec![]; }
        // ...
    }
    Some(is_long) => { /* exit path 不動 */ }
}
```

**關鍵**：W7-2 check 在 `regime_allows_entry` 之前，即「cross-strategy desync 是 first-class skip 條件」，比 regime/persistence/confluence 更高優先序 — 因為下游 router gate 1.5 必拒，提前剪枝省 tick 內 ~15-30 步計算。

### Part 2: bb_reversion（per W7-4 §3 同 ma_crossover pattern）

```rust
// mod.rs:448 match self.positions.get(ctx.symbol).copied()
match self.positions.get(ctx.symbol).copied() {
    None => {
        // ── W7-2 Option A 治本：cross-strategy paper_state 查詢（同 ma_crossover）──
        if let Some(existing) = ctx.position_state {
            self.positions
                .insert(ctx.symbol.to_string(), existing.is_long);
            tracing::debug!(
                target: "bb_reversion",
                symbol = %ctx.symbol,
                existing_is_long = existing.is_long,
                "skip entry: ctx.position_state present (cross-strategy paper_state holding) — \
                 W7-2 Option A treats as cross-strategy desync, sync self.positions and skip"
            );
            return intents; // intents=Vec::new() 已在 line 447 初始化
        }

        // 既有 G-SR-1 A1 signal 計算 + persistence + W-AUDIT-6d MA pair gate 不動
        let signal: Option<bool> = if bb.percent_b < 0.0 && rsi < self.rsi_oversold { ... };
        // ...
    }
    Some(_is_long) => { /* exit path（mean revert）不動 */ }
}
```

**對齊性**：與 ma_crossover 同模板（target / message / sync 邏輯一致），唯一差別是 return 型 `intents` (bb_reversion 已先初始化 Vec::new()) vs `vec![]` (ma_crossover 尚未初始化 intents 變數)。

---

## 3. Unit tests

### ma_crossover (4 test, tests.rs:833-963)

| test name | scenario | assertion |
|---|---|---|
| `test_on_tick_skips_entry_when_paper_state_has_other_strategy_position` | ctx.position_state=Some(SHORT, owner=grid_trading) + ma signal=LONG | 0 actions + self.positions[BTC]=Some(false) |
| `test_on_tick_proceeds_entry_when_paper_state_is_none` | ctx.position_state=None + valid LONG signal | 1 entry intent (baseline regression — W7-2 不誤殺) |
| `test_on_tick_exit_path_unchanged_by_w7_2_check` | step1 入場 LONG → step2 reverse cross + ctx.position_state=Some(LONG) | step2 走 Some(true) exit 分支 → 1 Close intent reason="ma_reverse_cross"（W7-2 check 在 None 分支內，exit path 不受影響） |
| `test_on_tick_w7_2_logs_skip_reason_via_state_sync` | first cross-strategy desync tick | 0 intent + sync 為 SHORT + HashMap size=1（O(1) insert） |

### bb_reversion (3 test, tests.rs:1078-1182)

| test name | scenario | assertion |
|---|---|---|
| `test_bbr_on_tick_skips_entry_when_paper_state_has_other_strategy_position` | ctx.position_state=Some(SHORT, grid) + oversold long signal | 0 actions + sync 為 SHORT |
| `test_bbr_on_tick_proceeds_entry_when_paper_state_is_none` | ctx.position_state=None + oversold long signal | 1 long entry intent (baseline) |
| `test_bbr_on_tick_w7_2_logs_skip_reason_via_state_sync` | first desync tick | 0 intent + sync + size=1 |

### Helper

兩處 test file 各自加 `make_paper_position(...)` / `make_paper_position_bbr(...)` helper 構造 `PaperPosition`（owner_strategy="grid_trading" 模擬 grid 已開倉場景）。`PaperPosition` 是 plain data struct，public field 直接 fill（無 builder），引用直接 `Some(&pp)` 對齊 `&'a PaperPosition` lifetime。

---

## 4. cargo build + test 結果

### cargo build
```
$ cd srv/rust/openclaw_engine && cargo build --release --bin openclaw-engine
    Finished `release` profile [optimized] target(s) in 23.92s
```
PASS（無 W7-2 引入 warning；既有 18 lib + 2 bin warnings 為 pre-existing dead_code 與本任務無關）。

### cargo test --lib --release -p openclaw_engine
```
test result: ok. 2648 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.57s
```
- baseline pre-W7-2 = 2641（per dispatch v3.7 Sprint N+1 D+0 spec）
- W7-2 新增 = 7（4 ma_crossover + 3 bb_reversion）
- Total = 2648 PASS

**首次跑出現 7 個 persistence/config::io filesystem race failure（parallel test 順序敏感）→ 2nd run 全 PASS（2648/2648）；確認非 W7-2 引入的 regression**：
- failure 集中於 `persistence::tests::test_three_pipeline_concurrent_writes` 等寫 disk 的 test
- `--test-threads=1` 跑 26 test 全 PASS
- 與 ma_crossover/bb_reversion code path 無關

### 局部 W7-2 spec test 跑（驗 7 test 全 PASS）
```
$ cargo test --lib --release -p openclaw_engine -- skips_entry_when_paper_state proceeds_entry_when_paper_state w7_2 exit_path_unchanged_by_w7_2_check
test result: ok. 7 passed; 0 failed
```

### 局部全 ma_crossover + bb_reversion test
```
$ cargo test --lib --release -p openclaw_engine -- strategies::ma_crossover strategies::bb_reversion
test result: ok. 101 passed; 0 failed; 0 ignored; 0 measured; 2547 filtered out
```
含 W7-3 既有 4 test（test_on_rejection_*）+ W7-2 新增 7 test + 既有 90 test。

---

## 5. PA #3 Option A + W7-4 §3 對照

### PA #3 §6 Option A 對照（治本路徑）

| PA #3 規格項 | 本 IMPL 對照 |
|---|---|
| 「ma_crossover.on_tick 進 entry path 前查 `ctx` 提供的 `paper_state.get_position(ctx.symbol)`」 | ✅ entry None 分支起點查 `ctx.position_state`（W7-1 已 wire） |
| 「如果 paper_state 已有同 symbol 倉位（不論哪個策略開的）→ skip entry，不發 intent」 | ✅ `if let Some(existing) = ctx.position_state { ... return vec![]; }` |
| 「需要：TickContext 加 `position_state: Option<&PaperPosition>` 或類似 read-only handle」 | ✅ 已由 W7-1 trait skeleton land；step_4_5_dispatch.rs:287-289 per-iteration borrow wire |
| 「副作用：改 TickContext signature 影響 5 個策略 → 派發前 PA 必審所有策略 on_tick 對齊」 | ✅ 5 策略 on_tick 已對齊（W7-1 land 時 PA 已審）；本任務僅消費既有 field |
| 「預估 LOC：~50 (ma_crossover) + ~30 (TickContext + tick_pipeline call site)」 | ✅ 實際 +30 LOC ma_crossover code（不含 test） |

### W7-4 §3 推廣對照

| W7-4 規格項 | 本 IMPL 對照 |
|---|---|
| 「W7-2 IMPL 任務（兩處）— step_4_5_dispatch.rs per-iteration borrow wire」 | ✅ 已在 W7-1 trait skeleton 同 commit (`c9fb0b8f`) land；本任務只用消費端 |
| 「ma_crossover/strategy_impl.rs entry path query (~15 LOC)」 | ✅ 實 +30 LOC（多含 tracing::debug + 雙語注釋） |
| 「保留 W7-3 Option B 補丁作為冗餘」 | ✅ on_rejection 內 W7-3 Option B 邏輯不動（commit `b42731f6`） |
| 「W7-5 same-Wave optional：bb_reversion 同 pattern apply」 | ✅ 本 IMPL 同 wave 完成（W7-4 §3/§6 推薦提早結 P2-BB-REVERSION-POSITION-SYNC） |
| 「邊際成本 ~15 LOC + 3 unit tests」 | ✅ 實 +22 LOC + 3 test（多含 1 條 tracing::debug + 對齊雙語注釋） |
| 「W-AUDIT-6d MA pair gate 互動需 E2 重點審」 | ✅ W7-2 check 在 W-AUDIT-6d MA gate 之前（None 分支起點），先 skip 即不觸 MA gate；無互動衝突 |

---

## 6. 已知不確定 / E2 重點

### E2 必審

1. **W7-2 + W7-3 共存契約（W7-4 §7 重點 3）**：W7-2 在 entry None 分支起點 sync self.positions → 下 tick 走 Some 分支不撞 router gate 1.5 → W7-3 on_rejection 不會被觸發 happy path。但若上游 sync 失敗（e.g. step_4_5_dispatch.rs:287 paper_state.get_position 回 None 但下游 router gate 1.5 仍見到 paper_state 倉位 — 理論上不可能，但若有 race / 分區同步），W7-3 仍是最後一道防線。**E2 確認 W7-2 land 後不可拿掉 W7-3**。

2. **`PerSymbolState<bool>::insert(String, bool)` API 對齊**：bb_reversion `positions` 是 `PerSymbolState<bool>`，`.insert(sym.to_string(), is_long)` 同 ma_crossover `HashMap<String, bool>::insert` 簽名（`per_symbol_state.rs:50` 確認 `pub fn insert(&mut self, symbol: String, value: S) -> Option<S>`）。E2 確認 hot reload 不踩到 `set_duration` 等其他 PerSymbolState API（本 IMPL 不動）。

3. **borrow scope**：`ctx.position_state: Option<&'a PaperPosition>` 的 lifetime `'a` 與 ctx 一致；本 IMPL 內 `let Some(existing) = ctx.position_state` 後 immediately 取 `existing.is_long`（Copy bool），不持有引用跨 await / async boundary，無 borrow checker 風險（`cargo build` 已驗）。

### 不確定（請 E2 / E4 確認）

- **debug log volume**：`tracing::debug!` 在 INXUSDT 11:34 hot loop 場景下假設 W7-2 land 前的 2319 reject/min 已被 sync 後 1-tick 終結，理論 log volume 從 2319/min → 1/min（peak desync onset only）。若 W7-2 sync 後仍偶發（e.g. paper_state 倉位 race window 1-2 ms 內被 close + 新 strategy 開 entry），可能 burst log。E4 deploy 後可觀察 24h debug log 體量決定是否降為 trace level。
- **persistence/config::io 7 failure 確認非 regression**：本次 cargo test 第二輪全 PASS（2648/2648）。已用 `--test-threads=1` 個別跑也 PASS。判定 baseline filesystem race transient，不阻 W7-2 sign-off。

---

## 7. NOT COMMITTED, NOT DEPLOYED 標記

按 PM 派工：
- **NOT COMMITTED**：本 IMPL 改動仍 local (uncommitted)；commit 留 PM 21:30 sign-off 後
- **NOT DEPLOYED**：未 push、未 ssh trade-core、未 restart_all
- 待 D+0 sign-off 後同 W7-1 + W7-3 + W2 trait skeleton 一次 `restart_all --rebuild --keep-auth` 部署

---

## 8. Operator 下一步

1. **PM sign-off W7-2 IMPL**（21:30 UTC 窗口內）— 對照本 report §5 PA #3 + W7-4 規格項，確認 7 test 全 PASS、cargo build 綠、無 regression
2. **派 E2 review**（per CLAUDE.md §八 強制 E1→E2 chain）— 重點 §6 三點
3. **派 E4 regression**（per CLAUDE.md §八 強制 E2→E4 chain）— 跑 ma_crossover + bb_reversion subset + 全 lib test 確認 baseline + 7 = 2648 PASS
4. **D+0 21:30 後**：commit W7-2 + W7-1 + W7-3 + W2 trait skeleton 同 wave 一次 deploy 到 Linux trade-core（per dispatch v3.7 Sprint N+1 D+0）
5. **D+1 起**：W7-2 land 後 24h passive watch INXUSDT live_demo 的 ma_crossover duplicate_position reject rate（若 W7-2 工作則應 ≈ 0 或 < 1/min vs W6 baseline 2319/min）

---

## Evidence Files

- 本 report：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_2_ma_crossover_bb_reversion_entry_path_query.md`
- PA audit (Option A spec)：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`
- W7-4 systemic audit (bb_reversion HIGH risk + same-pattern recommendation)：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_systemic_position_sync_audit.md`
- W7-1 trait skeleton commit（已 land NOT DEPLOYED）：`c9fb0b8f`
- W7-3 Option B 1-tick defense commit（已 land NOT DEPLOYED）：`b42731f6`
- 修改檔（uncommitted）：
  - `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:188-217`
  - `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs:449-471`
  - `srv/rust/openclaw_engine/src/strategies/ma_crossover/tests.rs:833-963`
  - `srv/rust/openclaw_engine/src/strategies/bb_reversion/tests.rs:1078-1182`

---

E1 IMPLEMENTATION DONE: 待 E2 審查 + E4 regression（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_2_ma_crossover_bb_reversion_entry_path_query.md）
