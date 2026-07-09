# W7-4 — 5 策略 Cross-Strategy Position Sync Systemic Audit

**Date**: 2026-05-10
**Owner**: PA
**Scope**: 5 策略 self.positions vs paper_state desync hot-loop 風險 systemic audit；read-only + spec write，不修 code
**Trigger**: PA #3 P1-MA-CROSSOVER audit (`da2d2a46`) §7 警告 systemic risk；W7-3 Option B 補丁 land (`b42731f6`) 後 W7-4 收尾
**Verdict**: **2 HIGH (ma_crossover/bb_reversion) + 1 MEDIUM (bb_breakout) + 1 LOW (grid_trading) + 1 RETIRED-LOW (funding_arb)**

---

## 1. 5 策略 self.positions usage table

| 策略 | position field type | queries_in_entry | rollback_on_reject | sync_on_fill (paper_state→self) | queries `paper_state` (gate 1.5 awareness) | hot-loop guard 額外機制 |
|---|---|---|---|---|---|---|
| `ma_crossover` | `PerSymbolState<bool>` | ✅ `self.positions.get` 決定 entry/exit 分支 | ✅ rollback 到 prev (含 None) | ❌ 無 on_fill 同步 | ❌ 不查 | W7-3 Option B 補丁（已 land 未 deploy）— `on_rejection` 識別 `duplicate_position` 寫入 self.positions |
| `bb_breakout` | `PerSymbolState<BbBreakoutPerSymbolState>` (含 `position: Option<bool>` + squeeze/entry_price/trailing_stop) | ✅ `current_position` 決定 entry/exit | ✅ rollback 整包 PerSymbolState（保留 oi_buffer 例外） | ❌ 無 on_fill 同步 | ❌ 不查 | 無 backoff；但 entry 多閘 (squeeze + expansion + vol + Donchian + persistence + confluence) 自然限頻 |
| `bb_reversion` | `PerSymbolState<bool>` | ✅ `self.positions.get` 決定 entry/exit 分支 | ✅ rollback 到 prev (含 None) | ❌ 無 on_fill 同步 | ❌ 不查 | 無 backoff；但 W-AUDIT-6d #6 MA pair gate fail-closed（MA 未對齊不入場）+ persistence 180s |
| `grid_trading` | `net_inventory: HashMap<String, f64>` + `last_cross_idx` | ✅ `cur_inventory` 決定 Open vs Close 翻轉 | ✅ rollback inventory + cross_idx + last_trade_ms | ✅ `on_close_confirmed_impl` 調 inventory；on_close_skipped 回滾 cross_idx | ❌ 不查 | **M-2 30s `reject_cooldown_until_ms`**（強護欄）+ `on_tick` 開頭遵守 |
| `funding_arb` | `PerSymbolState<FundingPosition>` | ✅ `self.positions.contains_key` 決定 entry/exit 分支 | ✅ rollback prev_positions + cooldown | ❌ 無 on_fill 同步 | ❌ 不查 | 1h cooldown（最長）+ ADR-0018 dormant `active=false` |

---

## 2. Per-strategy systemic risk verdict

### `ma_crossover` — **HIGH (confirmed P1，Option B 已補但 Option A 是治本)**
PA #3 已實證；W7-3 Option B 補丁 `d8697c41` 提供 1-tick defense，W7-2 Option A 治本待 D+1 IMPL。

### `bb_breakout` — **MEDIUM (potential，未實證 hot loop)**
- 用 `BbBreakoutPerSymbolState.position`，rollback 路徑可還原到 None（line 364-372 `prev=None` 分支）→ 跟 ma_crossover 同樣機制可形成 hot loop
- **但**：entry path 必經 6 重 gate（squeeze 45min 窗口 + bandwidth>expansion + vol_ratio>threshold + Donchian breach hard gate (`Hard` mode default) + persistence 60s + confluence score）— 自然限制每秒 reject 頻率
- 真實 hot-loop 觸發條件：squeeze 窗內 + Donchian 持續 breach + 同 symbol 已被 grid_trading 開倉 → 每 60s persistence 一次 → 每分鐘 ~1 reject，非每秒幾十次
- **W6 baseline 0 顯眼 reject burst** = 條件未對齊；但 cross-strategy desync 結構存在，與 ma_crossover 同因
- **影響**：低頻 noise reject + audit pollution；不會像 ma_crossover INXUSDT 11:34 一分鐘 2319 次

### `bb_reversion` — **HIGH (potential，與 ma_crossover 同結構)**
- 用 `PerSymbolState<bool>`，`prev_position` rollback 到 None（line 348-355）— **跟 ma_crossover 一模一樣**
- entry path gate 較少：persistence 180s + RSI 30/70 + bb.percent_b 邊界 + W-AUDIT-6d MA pair（fail-closed）+ confluence
- `cooldown_ms` default **600_000ms (10 min)** — 比 ma_crossover (5 min) 強，但 cooldown rollback 後也會回 None → desync hot loop 觸發後**每秒 reject 與 ma_crossover 同等量級**
- **真實風險**：bb_reversion 同 symbol 跟 grid_trading 共用時，若 RSI 在 oversold + percent_b<0 持續且 MA 對齊（W-AUDIT-6d 通過），與 ma_crossover INXUSDT 同模式發生
- **W6 0 顯眼**：reversion 入場條件比 ma_crossover 苛刻（需 RSI 極端 + bb 極端 + MA 對齊），實證未撞但結構性風險高

### `grid_trading` — **LOW (M-2 backoff 已護)**
- 有 `net_inventory` 而非 boolean position；router gate 1.5 看 paper_state symbol-level，所以 grid 自己重複下單會被擋 → 但 grid 本身會被擋的場景**已被 M-2 backoff (30s) 和 churn breaker (default off) 吸收**
- **on_rejection** 會 arm `reject_cooldown_until_ms = emit_ts + 30s`，**signal.rs 開頭 `if ctx.timestamp_ms < until { return vec![] }`** — hot loop 結構性不可能
- 兩個策略反向（grid 開倉 → ma_crossover 撞 grid）：grid 不會撞 paper_state（先開倉的一方），ma_crossover 撞但是 ma_crossover 的問題（HIGH 案例）
- **結論**：grid_trading 本身不會 hot loop，但 grid_trading 是「污染源」（先開倉佔用 paper_state slot）；治本仍是讓其他策略查 paper_state，不是改 grid

### `funding_arb` — **RETIRED-LOW (ADR-0018 dormant + 1h cooldown)**
- `active = false` (default `new()` line 77)；ADR-0018 已退休
- 1h cooldown + 結構性低頻（funding 8h cycle）
- 即使不 dormant、不 cooldown，funding_rate 變化頻率 8h 一次 → entry path 被 `funding_threshold` + `compute_edge>0` + `basis<entry_max` 三閘自然限制每天 max ~3 次 evaluate
- **不需 P2 ticket**，已在 W-AUDIT-8a §3 Phase A `declared_alpha_sources` 對齊保留

---

## 3. W7-2 fix pattern（給 D+1 ma_crossover 用，可推廣）

### 設計（對齊 PA #3 §6 Option A）

**Trait skeleton 已 land** (`c9fb0b8f`)：
- `TickContext.position_state: Option<&'a PaperPosition>`（line 721）
- `step_4_5_dispatch.rs:219` 暫填 `None`（per-iteration borrow pattern 待 W7-2 接線）

**W7-2 IMPL 任務（兩處）**：

1. **`step_4_5_dispatch.rs` per-iteration borrow wire**（pseudo-code，~10 LOC）：
   ```rust
   for strategy in active_strategies.iter_mut() {
       let mut ctx_for_strategy = ctx.clone();  // ctx 是 Copy/Clone-able？需確認
       ctx_for_strategy.position_state = self.paper_state.get_position(sym);
       let actions = strategy.on_tick(&ctx_for_strategy, &alpha_surface);
       // ... existing dispatch
   }
   ```
   - **關鍵**：在 strategy on_tick 完，paper_state 才被 mutable borrow（mirror_insert / apply_fill），所以 immutable get_position 在前完全可行
   - **borrow checker safe**：`PaperPosition` 在 `paper_state.positions: HashMap<String, PaperPosition>`，`.get(sym)` 回 `Option<&PaperPosition>` — `&'a PaperPosition` 生命周期綁 `ctx` 一個 tick

2. **`ma_crossover/strategy_impl.rs` entry path query**（~15 LOC）：
   ```rust
   // None 分支（line 141 內，confluence/persistence/higher_tf gate 後、make_intent_with_qty 前）
   if let Some(existing) = ctx.position_state {
       // paper_state 已有同 symbol 倉位（不論哪個策略開的）→ skip
       // 同時 sync self.positions 避免下次再進 entry path
       self.positions.insert(ctx.symbol.to_string(), existing.is_long);
       return vec![];  // skip entry，不發 intent
   }
   ```
   - 關鍵效果：第一次 desync 撞到也只走 1 tick + 0 intent，下 tick 已進 Some 分支（exit logic）
   - **保留** W7-3 Option B 補丁作為冗餘（reason 字串契約 fallback）— 對齊 PA #3 §8 重點 2

### 推廣到其他策略（Sprint N+2 候選）

| 策略 | Apply W7-2 pattern | LOC est | 注意 |
|---|---|---|---|
| `bb_breakout` | ✅ 推薦，None 分支 line 522 內加 ctx.position_state check | ~20 | sync 整包 PerSymbolState 較複雜（需 entry_price/trailing_stop 從 paper_state 推算或 None） |
| `bb_reversion` | ✅ **強烈推薦**，與 ma_crossover 同因，None 分支 line 449 內 | ~15 | sync `positions: PerSymbolState<bool>` 直接寫 is_long |
| `grid_trading` | ⚠️ **可選**，但 inventory 結構與 boolean position 不對齊 | ~30+ | 需設計：paper_state 有同 symbol 倉位但反方向時 grid 是否該繼續 cross signal？建議延後到 G6/W-AUDIT-8a Phase B 再考慮 |
| `funding_arb` | ❌ 不需，dormant + 1h cooldown 已護 | 0 | retired |

---

## 4. P2 ticket list refinement

### 既有 dispatch v3.4 §3.5 W5 list

| Ticket | 修改建議 |
|---|---|
| **P2-BB-BREAKOUT-POSITION-SYNC** | **保留，降為 MEDIUM**；fix scope = ~20 LOC ctx.position_state query + sync 整包 PerSymbolState；不阻 W5 IMPL，可 Sprint N+2 |
| **P2-BB-REVERSION-POSITION-SYNC** | **保留，升為 HIGH**；fix scope = ~15 LOC，與 ma_crossover W7-2 同模板，建議 D+3-5 W5 一併 IMPL |

### 新增建議

| Ticket | 級別 | 理由 |
|---|---|---|
| **無新 grid_trading P2** | — | M-2 backoff 結構性護欄已生效；inventory model 與 boolean position 不對齊，硬塞 W7-2 pattern 反而引入複雜度 |
| **無新 funding_arb P2** | — | dormant + 1h cooldown，零實際風險 |

### Spec 整合

W7-2 IMPL 完成後，建議**同 Wave 開 P2-BB-REVERSION-POSITION-SYNC** sub-task 用同一 step_4_5_dispatch.rs:219 wire pattern + bb_reversion 策略端 query — 兩策略共用 trait skeleton，邊際成本 ~15 LOC + 3 unit tests。

---

## 5. on_rejection RC-04 5 策略對比

| 策略 | rollback target on `prev=None` | hot-loop risk |
|---|---|---|
| `ma_crossover` | `self.positions.remove(sym)` → 回 None → entry path | **HIGH（已實證）** |
| `bb_breakout` | `self.symbols.remove(sym)` （或保留 oi_buffer） → position=None → entry path | MEDIUM（gate 多自然限頻） |
| `bb_reversion` | `self.positions.remove(sym)` → 回 None → entry path | **HIGH（結構同 ma_crossover）** |
| `grid_trading` | rollback inventory + cross_idx + **last_trade_ms** + arm M-2 reject_cooldown_until_ms 30s | LOW（M-2 護欄） |
| `funding_arb` | `self.positions.remove(sym)` → 回 None → entry path 但 1h cooldown 在前 | LOW（cooldown + dormant） |

**結論**：RC-04 rollback 到 None 的設計**4/5 策略共用**（grid_trading 例外用 inventory + M-2）。Hot loop 風險的差別**不是 RC-04 設計**而是「entry path 之後的 reject backoff 機制」：
- grid_trading 有 M-2 30s — LOW
- 其他 4 策略無 M-2 — 全靠 entry path gate 限頻

**派生建議（Sprint N+2 候選）**：考慮為 ma_crossover/bb_breakout/bb_reversion/funding_arb 引入「strategy 通用 reject backoff」（class-level 或 trait default），對齊 grid_trading M-2 模式。但這是設計題，不是當前 W7-4 scope。

---

## 6. W7-4 dispatch update 建議

給 PM 整合 dispatch v3.5（如有 v3.4→v3.5）：

### W7 task chain（D+1 起）

1. **W7-2 ma_crossover Option A IMPL** (PA + E1, 1 day)
   - step_4_5_dispatch.rs:219 per-iteration borrow wire (~10 LOC)
   - ma_crossover/strategy_impl.rs None 分支 query ctx.position_state (~15 LOC)
   - 保留 W7-3 Option B 補丁作為 reason 字串契約 fallback
   - **增量範圍對齊本 audit §3**

2. **W7-4 已完成（本報告）** — verdict 揭露 + P2 list refinement

3. **W7-5 same-Wave optional**（建議與 W7-2 同 IMPL phase）：**bb_reversion 同 pattern apply**
   - 與 W7-2 相同模板，邊際成本 ~15 LOC + 3 unit tests
   - 治理 P2-BB-REVERSION-POSITION-SYNC 提早結
   - 風險：bb_reversion W-AUDIT-6d MA pair gate 互動（fail-closed）需 E2 重點審

### Sprint N+2 候選（延後）

- P2-BB-BREAKOUT-POSITION-SYNC (~20 LOC)：MEDIUM 風險，等 ma_crossover/bb_reversion 治本再看效果
- 「strategy 通用 reject backoff」trait default：設計題，不阻當前任務

---

## 7. E2 重點審查 3 點（W7-2 IMPL 期）

1. **`TickContext` clone 成本**：per-iteration clone 整個 ctx 在 5 策略 × 25 symbol × 1Hz 的成本評估 — `TickContext` 含 `&'a` references，clone 是 shallow copy 應在 ns 級，但需 E4 micro-bench 1000 burst 確認
2. **`paper_state.get_position` borrow scope**：確認 `&self.paper_state.get_position(sym)` 在 strategy on_tick 完之前 paper_state 不被 mutable borrow（step_4_5_dispatch.rs 後續 `proactive_mirror_insert` / `apply_fill` 在 strategy on_tick 之後）— 已驗證可行（PA #3 §8 重點 3 已預警）
3. **W7-3 Option B + W7-2 Option A 共存**：兩條補丁同時生效時，Option A 在 entry path query 後 self.positions 已 sync，Option B 的 reason 字串解析 fallback 不會被觸發（happy path 已不會撞 gate 1.5）— 但 reason 字串契約若被破壞，Option B 仍是最後一道防線。E2 須確認共存無衝突，**不可在 W7-2 land 後拿掉 Option B**

---

## Evidence Files

- `srv/rust/openclaw_engine/src/strategies/ma_crossover/{mod,strategy_impl}.rs`
- `srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs` (single file, 886 LOC)
- `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` (577 LOC)
- `srv/rust/openclaw_engine/src/strategies/grid_trading/{mod,signal,position_mgmt}.rs`
- `srv/rust/openclaw_engine/src/strategies/funding_arb.rs`
- `srv/rust/openclaw_engine/src/tick_pipeline/mod.rs:721` (TickContext.position_state W7-1)
- `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:219` (None 暫填，待 W7-2 wire)
- PA #3 audit: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md`
- W7-1 trait skeleton commit: `c9fb0b8f`
- W7-3 Option B 補丁 commit: `d8697c41`
- W7-3 review chain commit: `b42731f6`

---

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_systemic_position_sync_audit.md
