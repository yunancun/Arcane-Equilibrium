# E1-D IMPL DONE — P0 Option A-Lite grid_trading cross_strategy_holds gate

**日期**：2026-05-11
**Branch**：`worktree-agent-ae9241f31ad50ac82`
**Commit**：`07045e99`
**Author**：E1 (Backend Developer)
**Status**：IMPL DONE，待 E2 審查 + E4 regression

## 1. 任務摘要

執行 PA §3.2 #3 + §7 BLOCKER #2 + §9 #3 規範：grid_trading entry path 加 `cross_strategy_holds` skip gate，**不動** `net_inventory` 任何 read/write。

**核心問題**：grid_trading 的 `net_inventory: HashMap<String, f64>` 累積 grid level qty（-2/-1/0/+1/+2），paper_state 不含此資訊不能搬到 SSoT（PA §7 BLOCKER #2）。但 grid 仍是 mass scalp 受害者，需在 entry path 加 gate 防 ma/bb_reversion/bb_breakout 已開的 paper_state 倉位讓 grid 誤判 inventory。

**gate 邏輯**：若 `ctx.position_state` 的 `owner_strategy` 不在 {"grid_trading", "bybit_sync", "orphan_adopted"} 三者之一，且 `would_open=true` → 提早 return `vec![]`，不進入 buy/sell dispatch、不寫 `net_inventory`、不更新 `last_trade_ms`。

## 2. 修改清單

| 檔 | LOC 改動 | 改動類型 |
|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/grid_trading/signal.rs` | +35 / -0 | entry path 插入 gate（10 LOC code + 25 LOC bilingual 注釋） |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/tests.rs` | +173 / -0 | 4 new tests + 1 helper + 1 ctx-with-position helper + section comment block |
| **Total** | **+208 / -0** | 0 行刪除，純加法 |

**未動**（per task constraint）：
- `grid_trading/mod.rs`（net_inventory field 0 動）
- `grid_trading/position_mgmt.rs`（on_external_close / on_fill 0 動）
- `grid_trading/grid_layout.rs` / `constructors.rs` / `params.rs`（0 動）
- 其他 4 策略文件（0 動）

## 3. 關鍵 diff

### 3.1 signal.rs gate（插入於 line 161-162 之間）

```rust
let would_open =
    (is_down_cross && cur_inventory >= 0.0) || (is_up_cross && cur_inventory <= 0.0);

// OPTION-A-LITE-E1D (2026-05-11)：cross-strategy paper_state holding 防 race。
// grid_trading 的 net_inventory 是 grid-level 累積（-2/-1/0/+1/+2 layered qty），
// 必須保留本地累積（PA §7 BLOCKER #2：paper_state 不含 grid-level 資訊）。
// 但若 paper_state 已有非 grid 來源（ma_crossover / bb_reversion / bb_breakout 等）
// 開的倉位，grid 的 would_open 路徑會誤觸發新入場，導致 cross-strategy
// mass scalp 混合（如 strategy=grid_trading + exit_reason=bb_mean_revert）。
// 解法：在 entry path 偵測非 grid owner 倉位即 skip new entry；接受的合法 owner
// 為 "grid_trading"（自己）/ "bybit_sync"（boot 後 sync）/ "orphan_adopted"
// （PA §7 #5 watch：視為未知 owner，下次 fill 自然 re-attribute）。
// 不動 net_inventory / on_external_close / on_fill 等任何 read/write 路徑。
let cross_strategy_holds = ctx
    .position_state
    .filter(|p| {
        let owner = p.owner_strategy.as_str();
        owner != "grid_trading" && owner != "bybit_sync" && owner != "orphan_adopted"
    })
    .is_some();
if would_open && cross_strategy_holds {
    // SAFETY 不變量：unwrap 安全 — cross_strategy_holds=true 蘊含
    // ctx.position_state.is_some() 為真（filter 對 None 永遠回 None）。
    let owner = ctx
        .position_state
        .map(|p| p.owner_strategy.as_str())
        .unwrap_or("unknown");
    debug!(
        strategy = "grid_trading",
        symbol = sym,
        owner = owner,
        "skip grid new entry: cross-strategy paper_state position holds \
         / grid 新開倉跳過：cross-strategy paper_state 已持倉"
    );
    return vec![];
}

if would_open && self.blocked_symbols.contains(sym) {
    // ... existing blocked_symbols gate unchanged
```

**設計考量**：
- 用 `Option::filter` + `is_some()` pattern 避開 unwrap 風險（PA pseudocode 用 `.unwrap()` 我用 `.map().unwrap_or("unknown")` 提高 defensive）
- debug log 含 owner 名稱供 runtime 排查
- 雙語 fallback：log 中文 + 英文，搭配 SAFETY 不變量注釋

### 3.2 tests.rs 4 個新 tests

| Test | Setup | Verify |
|---|---|---|
| `test_grid_skip_entry_when_cross_strategy_holds_paper_state` | paper_state owner=bb_reversion LONG + down cross | 0 intents + net_inventory 不變 0 |
| `test_grid_accepts_own_inventory_position` | paper_state owner=grid_trading LONG + down cross | 1 LONG Open intent |
| `test_grid_treats_bybit_sync_owner_as_legitimate` | paper_state owner=bybit_sync LONG + down cross | 1 Open intent（gate 不阻擋）|
| `test_grid_treats_orphan_adopted_owner_as_legitimate` | paper_state owner=orphan_adopted LONG + down cross | 1 Open intent（gate 不阻擋）|

包含 helper：
- `make_paper_position_grid(symbol, is_long, owner)`：PaperPosition 全欄位最小可行值構建
- `ctx_with_position(price, ts, &pp)`：TickContext with position_state=Some(&pp) helper

## 4. 治理對照

### 4.1 PA §7 BLOCKER #2 + §9 #3 E2 必查條件

| 條件 | 驗收 |
|---|---|
| net_inventory 任何 read/write 不減少 | ✓ `signal.rs:277,309` 兩處 `.entry().or_insert()` 保留（line 數變化僅因 +35 LOC 插入）；其他 4 檔（mod/position_mgmt/grid_layout/constructors）byte-identical |
| `cross_strategy_holds` / `OPTION-A-LITE-E1D` 在 signal.rs 1+ hit | ✓ 4 hits（1 邏輯 + 3 注釋行） |
| 全 lib test PASS ≥ 2785 | ✓ 2801 passed / 0 failed |
| 不動 exit logic | ✓ Close intent 路徑（line 226-261 close_short / line 261-294 close_long）完全保留 |
| 不動 on_external_close / on_fill | ✓ position_mgmt.rs diff 0 |
| 中文注釋 | ✓ MODULE_NOTE 保留，新增 gate 雙語注釋（OPTION-A-LITE-E1D 中文為主） |

### 4.2 CLAUDE.md §七 + §八 + §九 對照

| 項 | 驗收 |
|---|---|
| 跨平台兼容性（無硬編碼路徑） | ✓ N/A（Rust src，無 path 字面值） |
| 注釋雙語（2026-05-05 後默認中文） | ✓ 中文為主 + 英文 log 訊息 fallback |
| SQL migration | ✓ N/A |
| 被動等待 healthcheck | ✓ N/A |
| Singleton 登記 | ✓ N/A（無新 singleton） |
| 文件 800 行警告 / 2000 行硬上限 | signal.rs +35 → 281 LOC（遠低 800）；tests.rs +173 → 1122 LOC（介於 800 警告 vs 2000 上限，標 warning，未破 cap） |
| 最小影響原則 | ✓ +208 / -0，未順手「優化」任何代碼 |
| 不擴大 PA 範圍 | ✓ 嚴格按 PA §3.2 #3 + §8.1 LOC 預估（task 預估 +20 LOC code，實際 +10 LOC code + 25 LOC 注釋；測試預估 ~3 個，實際 4 個 + 1 helper） |

### 4.3 硬邊界（CLAUDE.md §四）

| 項 | 驗收 |
|---|---|
| max_retries=0 | ✓ 未碰 |
| live_execution_allowed | ✓ 未碰 |
| execution_authority | ✓ 未碰 |
| system_mode | ✓ 未碰 |
| decision lease | ✓ 未碰（grid_trading 是 Rust strategy 層，下游 IntentProcessor + Guardian 走 lease，本變更不影響 lease 路徑） |

## 5. 驗證結果

### 5.1 cargo build

```
cd /Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-ae9241f31ad50ac82/rust
cargo build --release -p openclaw_engine --lib
→ Finished `release` profile [optimized] target(s) in 38.41s
→ 18 warnings (全 pre-existing unused import / dead code，無 my code 觸發)
→ 0 errors
```

### 5.2 cargo test grid_trading focused

```
cargo test --release -p openclaw_engine --lib grid_trading
→ 50 passed; 0 failed; 0 ignored; 2751 filtered out
```

新加 4 個 test 全 PASS：
- `test_grid_skip_entry_when_cross_strategy_holds_paper_state` ... ok
- `test_grid_accepts_own_inventory_position` ... ok
- `test_grid_treats_bybit_sync_owner_as_legitimate` ... ok
- `test_grid_treats_orphan_adopted_owner_as_legitimate` ... ok

### 5.3 cargo test full lib

```
cargo test --release -p openclaw_engine --lib
→ 2801 passed; 0 failed; 0 ignored
→ target ≥ 2785 ✓ (exceeded by 16)
```

### 5.4 E2 grep 驗收

```bash
# net_inventory hits（per file，agent worktree vs baseline 對比）
constructors.rs: 3 (unchanged ✓)
mod.rs:          12 (unchanged ✓)
position_mgmt.rs: 10 (unchanged ✓)
signal.rs:        11 (+2 comments, 0 read/write 變化 ✓)
tests.rs:         26 (+7，6 hits 在 4 新 test assertion `g.net_inventory.get("BTC")` 純 read，1 hit comment)
TOTAL:            62 (baseline 53，+9 全屬 comment + test read，無新 write/insert/remove)

# net_inventory mutation paths（baseline vs my worktree）
signal.rs baseline:    line 242 + 274（2 hits, .entry().or_insert）
signal.rs my worktree: line 277 + 309（2 hits, .entry().or_insert，line 數僅因 +35 LOC 插入位移）
DIFF: 0 mutation paths changed ✓

# cross_strategy_holds / OPTION-A-LITE-E1D marker
signal.rs: 4 hits（line 163 comment + 173 logic + 180 logic + 181 comment） ✓
```

### 5.5 file-scope 驗收

```
diff baseline vs my worktree:
- signal.rs:        +35 / -0  (我加 gate)
- tests.rs:        +173 / -0  (我加 4 test + helper)
- mod.rs:          identical
- position_mgmt.rs: identical
- grid_layout.rs:   identical
- constructors.rs:  identical
- params.rs:        identical
```

完全符合任務 file scope。

## 6. 不確定之處

1. **PA pseudocode 接受 owner 是 `{"grid_trading", "bybit_sync"}` 2 個（line 160）；task dispatch 加 `"orphan_adopted"` 第 3 個**。
   - 我採用 task dispatch 的 3-owner 版本（PA §7 #5 watch 明確說 orphan_adopted 視為未知 owner 接受為合法）
   - 若 E2 認為 PA pseudocode 才是 SSoT 而非 task spec，請 push back，我會移除 orphan_adopted 接受

2. **gate 位置：放在 `would_open` 計算後、`blocked_symbols` gate 前**。
   - 理由：would_open 是必要前提條件（close 不需 skip），先算清楚再 gate；blocked_symbols 是策略治理本端 list，應在 cross-strategy 體系外
   - alternative：放在 nearest_grid_idx 計算前可省 nearest_grid_idx 開銷，但會增加 race 機率（gate fail 後仍寫 last_cross_idx），故 reject

3. **debug log owner unwrap_or("unknown") 是 defensive**。
   - PA pseudocode 用 `.unwrap()` — 我評估為若 cross_strategy_holds=true 邏輯上 ctx.position_state 必 Some，但 unwrap 仍危險（程式碼演進後 filter 變更可能破不變量）；defensive `.map().unwrap_or("unknown")` 0 runtime cost 更安全
   - E2 若認為過度防禦可改回 `.unwrap()`

4. **PaperPosition test helper 重複**：bb_breakout / bb_reversion / 現在 grid_trading 都有自己的 `make_paper_position_*` helper。
   - 應該抽到 `strategies/common/mod.rs` 但 task scope 限制 + PA §8.1 提到 common helper 由 E1-F aggregator 統合，故本 task 保留 local helper

5. **Parent repo 收到我意外寫入的副本（已 revert）**：Edit tool 的 absolute path 被我寫成主 repo 而非 worktree。發現後 `git checkout --` 還原，verify clean。**沒造成 contamination**，但暴露 worktree 工作模式下絕對路徑陷阱，已記入 memory。

## 7. Operator 下一步

1. **派 E2** 對抗性審查（重點 §9 #3 三條 + 我提的 5 個不確定）
2. **派 E4** regression（跑 full lib test 2801/2801 + 加跑 grid_trading 焦點 50/50 + benchmark `cargo bench paper_state_get_position`）
3. 等 E1-A / E1-B / E1-C / E1-E 其他 wave 同步完成後 PA 統合 wave 部署
4. 部署前 30 min 觀察 [40] avg_net + watchdog attribution_chain_ok + fills 分組計數（PA §8.3）

## 8. Wave 部署依存（per PA §6.2 選項 A）

E1-D 屬 Wave 2（中風險），與 E1-C (bb_breakout) 並行；先有 E1-E (funding_arb dormant) Wave 1 smoke 驗證 trait 改動可行，再進 Wave 2。

我的 E1-D commit `07045e99` 在 `worktree-agent-ae9241f31ad50ac82` branch。PA / PM 等其他 E1 instance 完成後 cherry-pick 或 merge wave。

## 附錄 A — 修改 file 完整 grep 證據

```
$ grep -n 'cross_strategy_holds\|OPTION-A-LITE-E1D' \
    rust/openclaw_engine/src/strategies/grid_trading/signal.rs
163:        // OPTION-A-LITE-E1D (2026-05-11)：cross-strategy paper_state holding 防 race。
173:        let cross_strategy_holds = ctx
180:        if would_open && cross_strategy_holds {
181:            // SAFETY 不變量：unwrap 安全 — cross_strategy_holds=true 蘊含

$ grep -n 'net_inventory\.\(insert\|remove\|entry\)' \
    rust/openclaw_engine/src/strategies/grid_trading/signal.rs
277:                *self.net_inventory.entry(sym.to_string()).or_insert(0.0) += self.qty_per_grid;
309:                *self.net_inventory.entry(sym.to_string()).or_insert(0.0) -= self.qty_per_grid;
```

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--option_a_lite_e1_d_grid_trading.md）
