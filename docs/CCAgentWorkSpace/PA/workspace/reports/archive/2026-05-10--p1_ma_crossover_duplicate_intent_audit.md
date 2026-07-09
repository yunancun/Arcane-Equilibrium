# P1-MA-CROSSOVER-DUPLICATE-INTENT — Audit Report

**Date**: 2026-05-10
**Owner**: PA
**Scope**: read-only root-cause audit；不修 bug，fix 留 D+3-5 W5 IMPL phase
**Trigger**: W6 baseline (post-V082 3.5h) ma_crossover INXUSDT live_demo duplicate_position reject 2331 次
**Verdict**: **Hypothesis A 變體（cross-strategy position state 盲區）= confirmed root cause，confidence HIGH**

---

## 0. TL;DR

ma_crossover 用 `self.positions: HashMap<String, bool>` 追蹤**自己策略**的倉位，不查 paper_state；router gate 1.5 用 `paper_state.get_position(symbol)` 做 **symbol-level（不分策略）** dedup。當 grid_trading 在同 symbol 上先開倉（INXUSDT 11:29 SHORT 1810），ma_crossover 看不見，於是每 tick 持續發 entry intent 撞 gate 1.5，infinite loop 直到自己 KAMA cross 反向或 cooldown 觸發。**`on_rejection` rollback 把 strategy.positions 還原到 `prev_position`（None），讓無限迴圈持續**。

實證：11:34:00 一分鐘內 reject 2319 次（每秒 30-50 次，遠超 KAMA cross 物理頻率）；INXUSDT 7d 內**只有 grid_trading**真實成交（11 fills），ma_crossover **0 fills**。

---

## 1. Entry Signal Logic Summary

**File**: `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:75-282` (`on_tick`)

四步流程（cooldown gate → ADX gate → KAMA/SMA cross → confluence/persistence）。`positions` 分支（line 140 `match self.positions.get(ctx.symbol).copied()`）：

- **None 分支（line 141-234）**：entry path — 計算 `signal: Option<bool>`（fast>slow=Long, fast<slow=Short），通過 confluence/persistence/higher_tf gate 後 `make_intent_with_qty()`，若 Some 就 push `StrategyAction::Open(intent)` + **第 230 行** `self.positions.insert(ctx.symbol, is_long)`
- **Some 分支（line 235-281）**：exit path — 反向 cross 累積 ER-scaled persistence 才發 `StrategyAction::Close`

**關鍵設計**：strategy 內部 `positions` 是該策略「以為自己開了什麼」的本地 cache，**完全不查 paper_state.positions**。

---

## 2. Position State 接線

**Strategy-side**: `MaCrossover.positions: HashMap<String, bool>`（mod.rs 結構體）— 純內部 cache，writes 在第 230 行 (Open)、277 行 (Close)、49/52 行 (on_rejection rollback)、70 行 (on_external_close)。
**Router-side**: `paper_state.positions: HashMap<String, PaperPosition>`（paper_state/mod.rs:93）— **symbol-level singleton，無 strategy 維度**；writes 在 `proactive_mirror_insert` (step_4_5_dispatch.rs:697-700) + WS fill confirm。

**Desync vector**：兩個 source of truth 互不同步。當 strategy A 開倉，paper_state 記 strategy A 的倉位；strategy B 的內部 `positions` 不知道，仍以為該 symbol flat。

**RC-04 on_rejection 加速 desync**（line 44-65）：
```rust
fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
    let sym = &intent.symbol;
    if let Some(prev) = self.prev_position.get(sym) {
        match prev {
            Some(b) => self.positions.insert(sym.clone(), *b),
            None    => self.positions.remove(sym),  // ← 關鍵：reject 後還原到 None
        }
    }
    // ... cooldown 也回滾
}
```
被 router 拒絕後，strategy.positions **不更新成「paper_state 真實狀態」**，而是 rollback 到 mutation 前（None）。下個 tick 又進 entry path。

---

## 3. duplicate_position Guard 設計

**File**: `srv/rust/openclaw_engine/src/intent_processor/router.rs:228-241` (Gate 1.5, `process_with_features`) + 同邏輯 `process_gates_only_with_features` line 739-751。

```rust
// Gate 1.5: Reject same-direction duplicate (prevent fee drain)
if let Some(existing) = paper_state.get_position(&intent.symbol) {
    if existing.is_long == intent.is_long {
        return rejected(DuplicatePosition { ... });
    }
}
```

**判斷依據**：完全 symbol-level，**不看 strategy 維度**。設計意圖（comment：「prevent fee drain」）是「同方向同 symbol 重複下單浪費手續費」— 這在**單策略 + symbol whitelist 不重疊**的設計假設下合理；**不是** by-design 的「pyramiding 拒絕」。

**Pyramiding 並非 by-design 允許**：strategy_impl.rs 第 235 Some 分支只走 exit，不走 add；MaCrossoverParams 也沒 pyramid_max_legs 之類字段（PA memory 2026-04-26 RFC 確認）。所以 **router gate 1.5 沒設計處理「跨策略同 symbol 競爭」**，這是 architectural gap。

---

## 4. INXUSDT-Specific Market 條件

實證（4h 內 INXUSDT 1m close-to-close diff，via SQL）：
- 價格 0.0146-0.0158 USD（極低絕對價格，bps 噪音放大）
- 1m 價格變動 ±5 to ±400 bps，typical ±30-100 bps；**沒有「每分鐘 KAMA 反向 cross 50 次」的物理可能**
- 11:29-12:24 整體下跌約 7% → 趨勢市場，ADX 應通過，**ma_crossover SHORT signal 持續存在**

→ INXUSDT 不是 abnormal vol；**reject burst 不是 cross 頻率太高造成的，是策略 vs paper_state desync 後的 hot loop**。

---

## 5. Hypothesis Verdict

| H | 內容 | Verdict | 證據 |
|---|------|---------|------|
| A | 每 tick 不 dedup | **PARTIALLY CONFIRMED**（變體）| ma_crossover dedup 自己 OK，但**看不見其他策略開的倉**，cross-strategy 不 dedup |
| B | by-design pyramiding 但邊界錯 | **REJECTED** | strategy 設計就是 1 symbol 1 leg，無 pyramid 字段；router gate 1.5 無 pyramiding awareness |
| C | INXUSDT 高 vol 高頻 cross | **REJECTED** | 4h vol 正常，11:34 一分鐘 2319 次 reject 是 hot loop，不是真實 signal frequency |
| D | timing race close→position | **REJECTED** | 11:39 grid 才 close，但 reject burst 11:34 已開始 5 分鐘；非 race，是 grid 開倉 (11:29) 後 5 min ma_crossover signal 才成熟 |

**最終 root cause（HIGH confidence）**：
> ma_crossover 的 `self.positions` 不知道 paper_state 裡有 grid_trading 的同 symbol 倉位。當兩個策略共用 symbol（INXUSDT 同跑 demo），先開倉的策略寫 paper_state，後 signal 的策略每 tick 撞 gate 1.5，配合 `on_rejection` rollback strategy.positions 形成 infinite reject hot loop（5 分鐘 ~2300 次，CPU 浪費 + DB 寫 verdict + 發 IPC events）。

**為什麼只 INXUSDT 顯眼**：grid_trading 在 INXUSDT 上有持倉時間長（5-10 min/cycle 反覆 SHORT）且 ma_crossover 在同 symbol 一旦 ADX/cooldown gate 通過就持續發 SHORT（趨勢市場 KAMA<SMA 持續成立）— 兩條件同時滿足。其他 symbol 要嘛 grid 也跑但 ma cross signal 沒對齊，要嘛 ma 跑但 grid 沒持倉。

---

## 6. Fix Scope 建議（D+3-5 W5 IMPL Phase）

**Scope 限定 ma_crossover 模組（per dispatch v3.1）**：

**Option A — strategy 端 query paper_state（推薦，最小改動）**
- ma_crossover.on_tick 進 entry path 前查 `ctx` 提供的 `paper_state.get_position(ctx.symbol)`
- 如果 paper_state 已有同 symbol 倉位（不論哪個策略開的）→ skip entry，不發 intent
- 需要：`TickContext` 加 `position_state: Option<&PaperPosition>` 或類似 read-only handle
- 副作用：**改 TickContext signature 影響 5 個策略**（bb_breakout / bb_reversion / grid_trading / funding_arb / ma_crossover）→ 派發前 PA 必審所有策略 on_tick 對齊
- 預估 LOC：~50 (ma_crossover) + ~30 (TickContext + tick_pipeline call site)

**Option B — on_rejection 識別 duplicate_position 並 sync strategy.positions（補丁式）**
- on_rejection 第 44 行加分支：if reason starts_with "duplicate_position" → 解析 `existing_is_long` 寫入 `self.positions`
- 立即終結 hot loop（下 tick 進 exit path）
- 副作用：依賴 reason 字串格式（rejection_coding.rs:148 byte-identical 契約），任何後續 reason 改寫會破壞
- 預估 LOC：~20 (ma_crossover.on_rejection)

**Option C — router gate 1.5 加 strategy-aware logging（觀測補丁，非真修復）**
- 不改邏輯，只在 Gate 1.5 reject 時加 strategy 維度 metric / rate-limit 日誌
- 不解決 hot loop，但減少 DB 寫入
- 預估 LOC：~30 (router.rs)

**PA 推薦：Option A 為治本（架構正確），Option B 作 1-tick 應急防衛**。Option C 只能延遲問題暴露時間，不選。

---

## 7. Risk if Not Fix

**直接影響**：
- DB 浪費：每秒 50 verdict insert × N 小時 = 數萬條 noise verdict（污染 [40] realized_edge audit）
- CPU 浪費：每 tick on_tick 全跑一遍 + intent build + gate evaluate
- IPC noise：reject events 經 trading_tx 流入 Python audit pipeline
- ML feature pollution: W-AUDIT-4b-M3 在 pre_risk reject 也寫 negative label（line 421-443），noise 進 production decision_features

**affected strategies × symbols（推測，需要 IMPL 前 SQL 全 strategy verify）**：
- ma_crossover × {grid_trading 在跑的所有 symbol} × {INXUSDT, BTCUSDT, ETHUSDT, ZECUSDT 等 grid 4 大 symbol}
- bb_breakout / bb_reversion 同樣設計（用 self.positions 不查 paper_state）→ 若跟 grid_trading 共 symbol 也會撞同問題（W6 baseline 沒看到只是 signal 沒對齊）
- W6 baseline 顯示 grid 各 symbol 70-180 reject 是合理 P0/P1 風控 reject；ma_crossover INXUSDT 2331 是 unique pathological pattern，但**潛在 systemic** issue

**嚴重度**：
- **Live**：HIGH — 真 live 下這是無實際倉位的 hot loop 會放大費率 noise + 干擾 risk envelope，且 OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1 下 lease 也會被 acquire 然後 cancel 浪費 SM-02 throughput
- **Demo/live_demo**：MEDIUM — pollute audit + CPU/DB
- **Architectural**：HIGH — Single-strategy assumption 跟 multi-strategy reality 不對齊；若未來想實裝 cross-strategy portfolio coordinator（DOC-01 §16 組合級風險）這個 gap 必修

**建議**：W5 IMPL phase 採 Option A，並由 PA 統一審 5 策略 on_tick TickContext 對齊；W5 同 phase 開 P2 ticket「audit bb_breakout / bb_reversion 是否同樣 hot-loop 風險」。

---

## 8. E2 重點審查 3 點

1. **TickContext signature 變動是否 break 其他 4 策略 on_tick 對齊**（grid_trading / funding_arb 也用 `ctx.indicators` 等 borrow，加新欄位的 lifetime 處理）
2. **on_rejection rollback 邏輯刪除前 audit RC-04 spec**（為什麼一開始要 rollback？是否有 cooldown clear 副作用會被影響）
3. **paper_state.get_position()** 在 strategy on_tick 是否會違反 borrow checker（paper_state 已被 step_4_5_dispatch.rs 同層 borrow）

---

## Evidence Files

- `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` (on_tick + on_rejection)
- `srv/rust/openclaw_engine/src/strategies/ma_crossover/helpers.rs` (make_intent_with_qty)
- `srv/rust/openclaw_engine/src/intent_processor/router.rs:228-241, 739-751` (Gate 1.5)
- `srv/rust/openclaw_engine/src/intent_processor/rejection_coding.rs:143-152` (DuplicatePosition format)
- `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:278-1126` (Open dispatch + on_rejection call)
- `srv/rust/openclaw_engine/src/paper_state/mod.rs:93` (positions HashMap)
- `srv/rust/openclaw_engine/src/paper_state/accessor.rs:190` (get_position)

## Runtime SQL Evidence

- `trading.risk_verdicts` 12h ma_crossover INXUSDT live_demo duplicate_position = 2332，**11:34:00 一分鐘 = 2319，11:35:00 = 12，其餘 0**
- `trading.fills` 24h INXUSDT = grid_trading × 11 (11:29 SHORT 1810 → 11:39 BUY close)；ma_crossover × 0
- `market.klines` INXUSDT 4h 1m close-to-close diff ±5-400bps，無高頻 cross
