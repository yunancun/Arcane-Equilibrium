---
report: PA — close-maker-first refactor 技術驗證 + spec outline
date: 2026-05-15
author: PA agent
mode: design verification (no code/config mutation)
trigger: 主會話派工，3 輪第三方對抗審核後收斂方案 PA 復驗
status: READY-FOR-SPEC（with 1 NEEDS-PROBE on rate-limit; 0 BLOCKED-BY-1B-4.2）
---

# Close-Maker-First Refactor — PA Verdict + Spec Outline

## 0. TL;DR

- **Verdict**: **READY-FOR-SPEC**。Entry-side 接線已驗 production-grade，close-side 是 ~10 行 dispatch 改 + ~150 LOC strategy_params + state machine 已存在可重用。沒有真實 1B-4.2 依賴（resting_orders.rs 是 **paper-only**，exchange close 路徑與它正交）。
- **核心 finding**：**close 路徑 hard-code `None` 是治理決策，不是技術限制**。`commands.rs:792-797` 的注釋「EDGE-P2-3 Phase 1a entry-only scope」白紙黑字標明範圍是 Phase 1a 的 scope-limiting 而非 plumbing 不夠。下游 IPC（`dispatch.rs:411-746`）已完整支援 `order_type/limit_price/time_in_force/maker_timeout_ms` 四欄位（透過 `OrderDispatchRequest` → `CreateOrderRequest`）。`PendingOrder` 結構 mirror 全鏈條（`dispatch.rs:475-497`），`pending_sweep::classify_pending_sweep` 已內建 PostOnly 超時 cancel + ack grace + partial fill tighten（`pending_sweep.rs:53-96`）。
- **Risk 結構**：高風險僅 1 個（dispatch 點白名單分類器 + bb_breakout `trailing_stop` 分類歧義），中風險 2 個（reject reclassify routing + reject_cooldown 跨入場/平倉污染），其餘低。
- **NEEDS-PROBE**：close-side maker 加上後 5s sweep cycle 內若大量 timeout cancel → REST cancel rate-limit 競爭 entry-side cancel（Order group 20 r/s）。需 dry-run 量化 demo 25 symbol 同時掛中比率。

---

## 1. 已驗代碼事實

| 主題 | 事實 | 文件:行 |
|------|------|--------|
| Close dispatch 結構 | `OrderDispatchRequest` 含 maker_timeout_ms/order_type/limit_price/time_in_force 四欄位 | tick_pipeline/mod.rs:613, commands.rs:778-816 |
| Close 寫 None 的位置 | 三處 close dispatcher：`execute_position_close` (778) / `ipc_close_all` (940) / `ipc_close_symbol` (1123) | commands.rs |
| 下游 IPC 消化 | `dispatch.rs:508` 已 `OrderType::Limit if eq_ignore_ascii_case("limit")`；`tif/limit_price` 行 514-515 forward 完整；reduce_only=true (516) | dispatch.rs:504-538 |
| Pending sweep 已支援 maker close | `classify_pending_sweep` 不分 is_close，只看 `time_in_force == PostOnly` + `maker_timeout_ms` | pending_sweep.rs:53-76 |
| Cancel-by-link-id 路徑 | `cancel_resting_maker_order` 走 `OrderManager::cancel_by_link_id_raw` (idempotent) | pending_sweep.rs:117-150 |
| Maker reject 分類已 typed | `MakerRejectionCategory::{PostOnlyCross/SelfCancel/FokCancel/TooManyPending/Other}` | maker_rejection.rs:43-72 |
| Entry maker 算法 | `compute_post_only_price(is_long, MakerPriceInputs{last_price, best_bid, best_ask, tick_size}, offset_bps, buffer_ticks)` → Option<f64>；strict-skip when no BBO 或 crossed book | common/maker_price.rs:77-177 |
| BBO 來源 | `PriceEvent.bid_price/ask_price` (price.rs:41-43)；`TickContext.best_bid/best_ask` mirror；execute_position_close 收 `&PriceEvent` 即有 BBO | mod.rs:723-727, price.rs:41 |
| tick_size 來源 | `instrument_cache: Option<Arc<InstrumentInfoCache>>` 已在 TickPipeline 持有；`InstrumentInfoCache::get(symbol)` → `Option<SymbolSpec>` 含 tick_size | mod.rs:801, instrument_info.rs:44/409 |
| Resting_orders.rs 性質 | **paper-only** infrastructure；MODULE_NOTE 行 1-23 明示「Paper-only PostOnly limit orders」；exchange close maker 與此正交 | paper_state/resting_orders.rs:1-23 |
| Whitelist reason 來源 | grid_close_{short/long}：signal.rs:316/348；bb_mean_revert：bb_reversion/mod.rs:629；ma_reverse_cross：ma_crossover/strategy_impl.rs:349；pctb_revert/bw_squeeze：bb_breakout/mod.rs:952/956；phys_lock_gate4_giveback/stale_roc_neg：exit_features/v2.rs:351/359/455 | (各檔) |
| trigger_tag 命名 schema | `strategy_close:{reason}` vs `risk_close:{reason}`（含 `risk_close:phys_lock_gate4_*` / `risk_close:TRAILING STOP ...`） | helpers_close_tags.rs:101-141, helpers.rs:38-90 |
| Tests.rs 影響面 | grid_trading/tests.rs:211/849/1058/1122 共 4 個 assert + ma_crossover 3 個 + bb_reversion 2 個 + bb_breakout 1 個 = 共 10 個 reason-string assert | grep verified |
| reject_cooldown 現狀 | grid_trading/signal.rs:154-158 `reject_cooldown_until_ms`：entry-side 強制 cooldown；close-side 沒分流，會被同 cooldown 阻塞（**真實 bug**） | signal.rs:152-158 |

---

## 2. 技術 risk 評估（per item）

| Item | Risk | 理由 |
|------|------|------|
| Dispatch 點白名單分類器 | **HIGH** | 三個 close dispatcher（commands.rs:778/940/1123）全部需加分類邏輯；trigger_tag 是 free-text；新增 bug 若白名單錯漏 → 整條 close path 退回 market（fail-soft，但 PnL 效果丟）|
| `bb_breakout trailing_stop` 分類歧義 | **HIGH** | 策略 reason `trailing_stop`（mod.rs:910/919，bb_breakout 內 chandelier ratchet）vs risk envelope `risk_close:TRAILING STOP: ...`（risk_checks 出血止損）共用同 keyword；白名單必須區分 — 主會話 spec 明示「TRAILING STOP keep market」應指後者（risk envelope），但 bb_breakout 自己的 trailing_stop 也是策略決策範疇，**建議保守 keep market**，理由：trailing_stop fire 時價格已突破止損線，maker 限價回頭追會 stale|
| reject_cooldown cross-side 污染 | **MEDIUM** | grid_trading 的 `reject_cooldown_until_ms` 是 per-symbol，entry-side maker reject 會凍住同 symbol close-side。設計上 close 不應被 entry reject 退避影響 — 需獨立 `reject_cooldown_entry/close`|
| Rate-limit 競爭 | **MEDIUM** (NEEDS-PROBE) | Demo 25 symbol grid 同時掛中 close maker，5s sweep cycle 若 timeout 集中 → cancel API 突發。Bybit Order group 20 r/s；需 dry-run 量化最壞情境|
| state machine pending close + 新 trigger | **MEDIUM** | 已有 `pending_close_symbols` HashSet (commands.rs:820)；新 risk trigger 進來在 step_6_risk_checks.rs:377-379 直接 `if pending_close_symbols.contains → continue`。但 trailing_stop fire 時 pending maker 還沒成交 — 需要 fast-escalate（取消 pending maker → 立刻 market）|
| Test assert 修改 | **LOW** | 10 個 reason-string assert，但 reason 字串本身不變（仍 "grid_close_long"），新增 maker dispatch 不破現有 assert；只有新增 maker-specific test 約 6-8 個|
| 1B-4.2 依賴 | **LOW** | 完全無依賴。1B-4.2 在 paper_state，exchange close maker 走 dispatch.rs → Bybit limit order，獨立路徑|

---

## 3. Whitelist 技術可行性 per exit_reason

| exit_reason | 來源 | 技術可行 | 推薦 algorithm | 理由 |
|------|------|----------|----------------|------|
| `grid_close_short` / `grid_close_long` | grid_trading/signal.rs:316/348 | ✅ | A（BBO ± buffer），與入場一致 | grid 平倉是 mean-revert 信號，maker 等回價合理 |
| `bb_mean_revert` | bb_reversion:629 | ✅ | A | 反向 sigma 觸發 mean-revert，maker 等更明顯 mean-revert |
| `ma_reverse_cross` | ma_crossover:349 | ✅ | A | MA 反向交叉，maker 等回價合理 |
| `pctb_revert` | bb_breakout:952 | ✅ | A | %B 回中軌：弱反轉訊號，maker 風險可控 |
| `bw_squeeze` | bb_breakout:956 | ✅ | A | BW 壓縮：volatility 塌陷，maker timeout 短一點 |
| `phys_lock_gate4_giveback` | exit_features/v2.rs:351/455 | ⚠️ | A 變體：價偏好我方 2-3 tick（peak 保護）| Gate 4 giveback 是 peak ATR 退潮，價回頭機率高，**可短 timeout（15-20s）保守觀察**|
| `phys_lock_gate4_stale_roc_neg` | exit_features/v2.rs:359 | ⚠️ | A 變體：價偏好我方 1-2 tick（stale 警示）| ROC 負值且 stale，下一秒 ROC 還可能往下 → maker timeout 必須短（10-15s），timeout 即 market|
| ❌ `trailing_stop`（bb_breakout 內） | bb_breakout:910/919 | ❌ | KEEP MARKET | chandelier 觸發即價已破線，maker 追不上 |
| ❌ `risk_close:HARD STOP: ...` | risk_management | ❌ | KEEP MARKET | 出血止損生存 > 利潤 |
| ❌ `risk_close:TRAILING STOP: ...` | risk_management | ❌ | KEEP MARKET | 同上 |
| ❌ `risk_close:TIME STOP` | risk_management | ❌ | KEEP MARKET | 時間到強制 |
| ❌ `risk_close:fast_track*` | risk_management | ❌ | KEEP MARKET | 緊急退倉 |
| ❌ `risk_close:halt_session*` | risk_management | ❌ | KEEP MARKET | 全停 |
| ❌ `risk_close:cost_edge_ratio` | risk_management | ❌ | KEEP MARKET | 治理層強平 |
| ❌ `risk_close:DRAWDOWN` | risk_management | ❌ | KEEP MARKET | 系統 drawdown |

**8 whitelist + 7+ keep market**（與主會話建議一致；新增 2 個風控變體 `phys_lock_gate4_*` 細化建議；新增 `trailing_stop` 歧義澄清）。

---

## 4. `compute_close_limit_price()` 推薦設計

### 4.1 推薦：**選項 C — 反向複用 entry 邏輯 + per-reason buffer 微調**

```rust
// In strategies/common/maker_price.rs (新增):

pub fn compute_close_limit_price(
    is_close_long: bool,           // 平多 = sell；平空 = buy
    inputs: MakerPriceInputs,      // 來自 PriceEvent.bid/ask + instrument_cache.tick_size
    buffer_ticks: u32,             // per-reason 配置（grid=1, phys_lock_g4=2-3, bw_squeeze=1）
    strategy_name: &str,
    exit_reason: &str,
    symbol: &str,
) -> Option<f64> {
    // 平多 = sell → 反向：站到 ask 之上（同 entry 短倉）
    // 平空 = buy  → 反向：站到 bid 之下（同 entry 多倉）
    // 直接 delegate compute_post_only_price(is_long=!is_close_long, ...)
    compute_post_only_price(
        !is_close_long,            // 反向：close long → sell → !true=false; close short → buy → !false=true
        inputs,
        0.0,                       // close-side 不用 bps fallback（嚴格 BBO）
        buffer_ticks,
        strategy_name,
        symbol,
    )
}
```

### 4.2 各選項對比

| Option | 描述 | 優劣 |
|--------|------|------|
| **A. mid ± tick** | 純對稱對偏好我方 1-2 tick | 簡單；但 mid 在 wide spread 下不穩定 |
| **B. entry level** | grid 用 grid level / bb 用 bb_mid / ma 用 ma_value | 複雜（每策略不同），bb_mean_revert/ma_reverse_cross 不存在「entry level」對偶平倉價 |
| **C. 反向 entry 邏輯**（**推薦**）| `compute_post_only_price(!is_close_long, ...)` + per-reason buffer | 重用 production-tested code，PostOnly 守 BBO 對稱保證不跨 book |

### 4.3 為什麼選 C

1. **單一真相源**：entry-side `compute_post_only_price` 經 G7-09c Phase 1 production 驗證（rejection 100% → 0%，4 天 178 筆 case）；close-side 反向 = 同一邏輯鏡像。
2. **strict-skip 一致**：no BBO / crossed book / tick_size missing → close 同樣返 None，**caller fallback 到 market**（fail-soft 保 close certainty）。
3. **per-reason buffer 容納變體**：不同 reason 對「等多深 maker」需求不同：
   - grid_close_*：buffer_ticks=1（與入場對稱）
   - bb_mean_revert：buffer_ticks=1
   - ma_reverse_cross：buffer_ticks=1
   - pctb_revert / bw_squeeze：buffer_ticks=1（保守）
   - phys_lock_gate4_giveback：buffer_ticks=2（peak 保護，等價更深一點）
   - phys_lock_gate4_stale_roc_neg：buffer_ticks=1，**maker_timeout 短到 10s**（stale ROC 風險已浮現）
4. **fallback 自然 OK**：close-side `None` → 退回 market（與現行 hard-code None 行為等價，不破現行 SLA）

---

## 5. State machine 設計

### 5.1 既有狀態（pending_close_symbols HashSet）

```rust
pending_close_symbols: HashSet<String>      // commands.rs:820
PendingOrder { is_close, time_in_force, maker_timeout_ms, ... }  // event_consumer/types.rs
```

### 5.2 四個 race 場景與設計

| 場景 | 設計 |
|------|------|
| **1. pending close maker + 新 risk trigger (HARD STOP fire)** | **fast-escalate**：在 `step_6_risk_checks.rs:377-379` 移除「`if pending_close_symbols.contains → continue`」改為「**dispatch cancel-by-link-id 對 pending maker → 立刻 market close**」。Bybit 端 cancel idempotent，market 走 reduce_only=true 二級保護。新增 IPC event `CancelAndMarketClose { symbol, reason }` 路由給 `dispatch.rs`。|
| **2. pending close maker + maker timeout** | **重用 pending_sweep.rs::MakerTimeoutCancel**。Sweep 對 `is_close=true` order 同樣 fire MakerTimeoutCancel → REST cancel → **fallback 到 market re-dispatch**（這是行為差異點：entry-side timeout 後策略 re-decide；close-side timeout 後必 fallback market，因為 close 必須執行）。新增 `PendingOrderEvent::CloseMakerTimeoutFallback { symbol, qty, is_long, reason }` 路由給 commands.rs::execute_position_close 用 `order_type:"market"` 重派|
| **3. reject (EC_PostOnlyWillTakeLiquidity)** | 同 entry-side：classify → `PostOnlyCross`；close path 對 PostOnlyCross **直接 fallback 到 market**（不重 quote，因為 BBO 已不允許 passive maker，重 quote 仍會 reject）|
| **4. reject (EC_ReachMaxPendingOrders)** | classify → `TooManyPending`；close path **直接 market**（帳戶背壓 = 不能等）+ 5min global cooldown 對所有 maker 提交（entry + close 都暫停 new maker，但 close 走 market 保 reduce_only 必執行）|

### 5.3 transition 圖（close path）

```
[strategy/risk fire close] 
      ↓
  (在 whitelist?)
    Yes ↓             No ↓
[dispatch maker close]     [dispatch market close (今路徑)]
      ↓
  pending_close_symbols.insert + sent_ts
      ↓
  per-tick 5s sweep cycle:
    ├─ filled (WS) → clear pending, exit normal
    ├─ partial fill → tighten_postonly_entry_after_partial **改用 5s 等剩餘**
    ├─ MakerTimeoutCancel (>= maker_close_timeout_ms) → REST cancel → 派 CloseMakerTimeoutFallback → market re-dispatch
    └─ reject WS (PostOnlyCross/TooManyPending) → REST cancel (idempotent) → market re-dispatch
      ↓
  新 risk_close trigger fire 對同 symbol：
    ├─ symbol in pending_close_symbols (已 maker close) → CancelAndMarketClose IPC → cancel maker → market re-dispatch
    └─ 否則正常 risk close 路徑
```

### 5.4 不變式

- close-side 任何 timeout / reject / new trigger fire → **永遠 fallback 到 market**，不允許「死等 maker」。原則 5（生存 > 利潤）。
- 同一 symbol 同時只能有一個 close pending（pending_close_symbols dedup 已保證）。
- close maker_timeout_ms 上限 30s（與 entry-side 45s default 不同，close 更時間敏感）。

---

## 6. Phase 1B-4.2 依賴判斷：**完全無依賴（bypass）**

- `resting_orders.rs` MODULE_NOTE 行 4-23 明示是 **paper-only** infrastructure。
- 1B-4.2 在 paper_state 模擬 PostOnly fill 等待 tick 碰觸限價（線下 backtest 用），用 `RestingFillEvent { Filled / Timedout }` 寫 paper fill。
- Exchange path 完全不經 resting_orders.rs，走的是 dispatch.rs → Bybit REST → WS order/fill event → loop_handlers 處理。
- Close-side maker 添加 = 在 dispatch.rs/commands.rs/pending_sweep.rs 已存在的 plumbing 上接電線，**不需 1B-4.2 land**。
- Healthcheck 影響：1B-4.2 是 paper-side edge estimate 抗 bias 工作，close maker exchange-side 對 paper 模擬影響為 0（paper 沿用「立即 market fill」）。

---

## 7. Spec 文檔大綱（13 章節）

```
# Close-Maker-First Refactor Spec v1
1. 背景與動機（demo -110.43 / live_demo -27.31 30d net；entry-side 100% maker 已驗）
2. 範圍與不變式
   2.1 8 whitelist exit_reason
   2.2 7+ keep market reason（含 trailing_stop 歧義澄清）
   2.3 close-side 永遠 fail-soft fallback market（不變式 #1）
3. 配置層設計
   3.1 strategy_params 新增 use_maker_close / maker_close_timeout_ms / maker_close_buffer_ticks
   3.2 per-strategy default 表
   3.3 phys_lock_gate4_* per-reason override（在 ExitConfig 加 maker_close section）
   3.4 5 個 toml 改動位置
4. 代碼層設計
   4.1 compute_close_limit_price() 新增（reuse compute_post_only_price，反向）
   4.2 三個 close dispatcher 改造（execute_position_close / ipc_close_all 不改 / ipc_close_symbol 不改）
       ⚠️ 設計決策：只在 strategy/risk fire close 路徑（execute_position_close）走 maker；IPC explicit close（ipc_close_all/symbol）走 market（operator intent = 立刻平）
   4.3 trigger_tag 白名單分類器 helper `is_close_maker_eligible(trigger_tag: &str) -> bool`
   4.4 PriceEvent.bid/ask → MakerPriceInputs 構造 helper
   4.5 instrument_cache.tick_size 取用點
5. State machine
   5.1 4 race 場景設計（§5 詳述）
   5.2 IPC event 新增 (CancelAndMarketClose, CloseMakerTimeoutFallback)
   5.3 dispatch.rs 端對 CancelAndMarketClose 處理流程
6. Reject 處理
   6.1 maker_rejection.rs 既有 classify 直接重用
   6.2 close-side PostOnlyCross / TooManyPending 路由 → market re-dispatch
   6.3 reject_cooldown 拆分 entry/close per-side（修現存 bug）
7. Timeout & sweep
   7.1 pending_sweep.rs::classify_pending_sweep 對 close 不需改（不變）
   7.2 cancel_resting_maker_order 對 close 不需改（不變）
   7.3 close timeout 對應 PendingOrderEvent 路由 fallback market
8. Healthcheck & observability
   8.1 新增 [62] close_maker_fill_ratio per strategy per env 7d 窗
   8.2 新增 [63] close_maker_reject_rate per env 24h 窗
   8.3 [40] avg_net_bps 對 close-maker fills 分組對比 maker vs market 平均淨 bps
   8.4 trading.fills.exit_reason 加 _maker / _market 後綴？（待 spec phase 決：建議**不加**保 string assert backward-compat，用 order_type 列分流）
9. Test 影響面
   9.1 Existing assert：10 個 reason-string 不破（reason 不變）
   9.2 新增：6-8 個 maker-close unit test（compute_close_limit_price 各 reason、fallback no BBO、reject path、timeout fallback）
   9.3 新增：1 個 integration test 對 dispatch.rs（close limit order forward 完整 order_type/limit_price/tif/maker_timeout_ms）
10. Rollout
   10.1 demo 7d：use_maker_close=true on grid_trading only
   10.2 demo 14d：use_maker_close=true on grid + bb_reversion + ma_crossover
   10.3 demo 21d：full whitelist enable（含 phys_lock_gate4）
   10.4 live_demo 7d mirror（per stage PASS 條件見 §11）
   10.5 live：operator approve only
11. Per-stage PASS 條件
   11.1 close_maker_fill_ratio ≥ 60% (entry-side baseline 90%+)
   11.2 close_maker_reject_rate ≤ 5% per 24h
   11.3 avg_net_bps（maker close）≥ avg_net_bps（market close） + 1.5 bps（fee diff 預期 ~3.5 bps）
   11.4 fallback_to_market_rate ≤ 30%（high = maker 設計失敗）
   11.5 no new HARD STOP fire 上升 vs baseline
12. Risk + mitigation
   12.1 §2 risk table
   12.2 NEEDS-PROBE rate-limit 設計 mitigation：sweep cycle stagger / 限同時 maker close 數
13. 16 原則 + DOC-08 §12 合規
   13.1 原則 5 生存 > 利潤：fail-soft fallback market 保證 close certainty
   13.2 原則 6 失敗默認收縮：no-BBO → return None → market（保守）
   13.3 原則 11 Agent 最大自主：per-strategy use_maker_close 可調，agent 透過 OrderIntent 走治理鏈
   13.4 DOC-08 §12 invariant 1-9 全部保留不變
   13.5 硬邊界 0 觸碰（live_execution_allowed / max_retries=0 / system_mode 不動）
```

---

## 8. 代碼 / 測試影響範圍估計

| 文件 | 改動性質 | 預估 LOC | 風險 |
|------|---------|----------|------|
| `strategies/common/maker_price.rs` | 新增 `compute_close_limit_price()` | +25 | 低（reuse） |
| `strategies/strategy_params.rs` | 新增 3 field × 5 strategy + default | +60 | 低 |
| `strategies/{grid_trading,bb_reversion,ma_crossover,bb_breakout}/{mod.rs,config.rs}` | 配置 forward | +60 | 低 |
| `tick_pipeline/commands.rs::execute_position_close` | 白名單分類器 + maker dispatch path | +80 | **HIGH**（必經 E2 + A3 + E4） |
| `tick_pipeline/commands.rs::resolve_close_maker_inputs` (新 helper) | PriceEvent + instrument_cache 構造 MakerPriceInputs | +30 | 低 |
| `tick_pipeline/on_tick/step_6_risk_checks.rs` | pending_close_symbols race 改 fast-escalate | +40 | **HIGH** |
| `event_consumer/types.rs` PendingOrderEvent | 新增 CloseMakerTimeoutFallback / CancelAndMarketClose 2 variant | +25 | 中 |
| `event_consumer/dispatch.rs` / `event_consumer/loop_handlers.rs` | 處理新 PendingOrderEvent 變體 | +60 | 中 |
| `helpers_close_tags.rs::is_close_maker_eligible` (新 helper) | whitelist classifier + tests | +50 | 中 |
| `risk_checks.rs / pipeline_helpers.rs` | reject_cooldown_close 拆分（修現存 bug） | +30 | 中 |
| `4 settings/risk_config*.toml` | use_maker_close defaults | +5 each | 低 |
| Tests: integration + unit | 8 新 unit + 1 integration + 0 fix 既有 | +400 | 中 |
| Healthcheck `[62] [63]` | passive_wait_healthcheck 新 check | +120 | 低 |

**Total ~ 985 LOC**（Rust ~575 / TOML ~20 / Tests ~400 / Healthcheck ~120）

**3-5 E1 並行**：
- E1-A：compute_close_limit_price + strategy_params + 5 策略 forward（並行）
- E1-B：execute_position_close 白名單 + dispatch + is_close_maker_eligible（**序列**：基礎依賴）
- E1-C：state machine 改造 step_6_risk_checks + PendingOrderEvent + dispatch.rs handlers（依 B）
- E1-D：reject_cooldown_close 拆分 + tests（並行 B）
- E1-E：4 toml + healthcheck [62] [63]（並行）

預估 7-9 E1-day（含 E2 + A3 + E4 兩輪審查），1-2 sprint W 內可 ship。

---

## 9. 技術 verdict

**READY-FOR-SPEC**

理由：
1. ✅ Entry-side maker plumbing 完整 production-tested（PostOnly compute / rejection classify / pending_sweep timeout + cancel + ack grace / partial fill tighten / IPC 全鏈條 forward）
2. ✅ Close-side dispatch path 結構已完整支援 4 個 maker 字段（commands.rs:778-816 / dispatch.rs:474-538），只是 hard-code `None`
3. ✅ State machine 既有 pending_close_symbols + PendingOrder 結構足以支撐，需要 +2 IPC event variant + 1 race fast-escalate path
4. ✅ 1B-4.2 完全不依賴（paper-only 正交）
5. ✅ Tests.rs 影響面有限（10 reason-string assert，新增 maker-specific 不破現有）
6. ✅ 硬邊界 0 觸碰，DOC-08 §12 invariant 全保留，16 原則合規（原則 5/6/11 強化）

**唯一 NEEDS-PROBE**：rate-limit cancel API 突發。建議 spec phase 加 dry-run 量化：demo 25 symbol grid 7d close fill 203 筆 / 7d ≈ 1.2/h，sweep 突發風險低。但仍建議 spec 寫入 mitigation：「sweep cycle 同 5s 內 cancel API 並發 > 10 即降頻 retry」。

**spec 起草路徑**：建議 PM 派 PA spec phase（1d）→ QC + MIT + BB 三角 review（1d）→ PA v2 incorporate（0.5d）→ Wave 派 E1×3-5 並行 IMPL（5-7d）→ E2+A3+E4 對抗審（2d）→ demo rollout（7d）。

**Confidence**：
- HIGH for: 已驗代碼事實（§1 全 grep + 文件直讀），whitelist 推薦（§3 每 reason 來源驗證），compute_close_limit_price 設計（§4 reuse 已 production-tested），1B-4.2 無依賴判斷（§6 MODULE_NOTE 直讀），spec outline 13 章節結構
- MEDIUM for: rate-limit NEEDS-PROBE，state machine fast-escalate IPC event 設計（需 spec phase 與 E2 對抗確認），bb_breakout trailing_stop 歧義裁決
- LOW for: 0 — 所有不確定處皆已明示

---

## Report path
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md
