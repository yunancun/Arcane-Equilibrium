# PA 設計 — 幽靈倉位記帳 bug 定位 + 修復 + 對賬告警

- 日期：2026-06-07
- 角色：PA（只設計與定位，不寫實作碼）
- 標的事故：TONUSDT demo 模式幻影 LONG（2026-06-06，28548 筆假快照，遮蔽真實 +5% 行情）
- 風險評級：**極高**（核心熱路徑倉位記帳；影響 demo / live_demo / 真 live 全部模式）
- 結論：**不自動部署**。本文交 E1 實作 + E4 驗證 + operator sign-off gated。

---

## 0. 一句話定位

幻影 LONG 不是 `apply_fill` 算錯，而是 **WS `PositionUpdate` 與 `Fill` 兩條訊息對同一份 `PaperState`
倉位 map 亂序雙寫**：Bybit 平倉時先推 `position(size=0)`→ 引擎 `upsert_position_from_exchange` 把 short
移除（flat）→ 隨後 close 的 `Buy` `Fill` 才到 → `apply_fill` 在 map 找不到既有倉 → 落入「開新倉」分支 →
把那筆**平倉 Buy 開成了反向 LONG**（entry=平倉價 1.5744、qty=平倉量 437.3，指紋完全吻合）。
reconciler 因為對賬軸接的是「Bybit 自我快照跨輪 diff」而非「本地帳 vs Bybit」，結構性盲視這個本地幻影。

---

## 1. 確切 bug 位置（file:line）與資料鏈路

### 1.1 倉位帳本與 snapshot 來源鏈路（demo / live_demo / live 共用同一本）

```
Bybit private WS (order/execution/position/wallet 四 topic，demo/testnet/mainnet 全訂閱)
   │  bybit_private_ws.rs:713  self.environment.private_ws_topics()
   ▼
ExecutionListener  (startup/private_ws.rs:113  ExecutionListener::new(priv_rx))
   │  兩個回調共用同一個 exchange_event_tx（unbounded channel，startup/private_ws.rs:95）：
   │    on_position_update → ExchangeEvent::PositionUpdate(pos)   (startup/private_ws.rs:143-162)
   │    on_fill           → ExchangeEvent::Fill(exec)             (startup/private_ws.rs:167-179)
   │  ★ 兩條訊息的相對順序 = Bybit WS 推送順序，引擎不保序、不關聯。
   ▼
event_consumer::loop_exchange::handle_exchange_event  (event_consumer/loop_exchange.rs:96)
   ├── Fill 分支 (:104-410)        → pipeline.apply_confirmed_fill_with_close_maker_audit (:266)
   │                                   → commands.rs:702 paper_state.apply_fill(symbol,is_long,qty,...)
   └── PositionUpdate 分支 (:531-569) → pipeline.paper_state.upsert_position_from_exchange (:550)
   ▼
PaperState.positions: HashMap<String, PaperPosition>   (paper_state/mod.rs:93)
   ▼
GAP-7 emit_periodic_snapshots  (tick_pipeline/on_tick_helpers.rs:700)
   │  每 1000 ticks 遍歷 paper_state.positions() → TradingMsg::PositionSnapshot
   │  engine_mode = self.effective_engine_mode()  (:724)  ← 'demo' 標籤來源
   ▼
database/trading_writer.rs:645  INSERT INTO trading.position_snapshots(...engine_mode)
```

→ 幻影 LONG 一旦進入 `PaperState.positions`，GAP-7 每 1000 ticks 就照寫一筆 snapshot，
直到引擎卡死/重啟。28548 筆假快照即此來源。

### 1.2 有問題的邏輯：`apply_fill` 對「無既有倉位」的平倉 fill 開成反向新倉

`rust/openclaw_engine/src/paper_state/fill_engine.rs:276-385`（`apply_fill`）

```rust
// fill_engine.rs:295
if let Some(pos) = self.positions.get(symbol) {
    if pos.is_long != is_long {
        // 平倉分支：close_qty = pos.qty.min(qty)，remaining 判斷歸 flat —— 邏輯本身正確
        ...
    } else {
        // 同向加倉 —— 正確
    }
}
// fill_engine.rs:364-385  ★ BUG 暴露點：
// Opening new position (no existing position for this symbol)
self.positions_insert(symbol, PaperPosition {
    is_long,                       // = true（Buy）
    qty,                           // = 437.3（平倉量）
    entry_price: fill_price,       // = 1.5744（平倉價）
    ...
});
```

**證明它記成反向倉而非 flat**：那筆 17:03 的 `Buy 437.3 @ 1.5744` 是平掉 short 的 reduce/close 單。
但 `apply_fill` 收到它時，`self.positions.get("TONUSDT")` 已是 `None`（short 已被先到的
`PositionUpdate(size=0)` 移除，見 §1.4）。於是 `if let Some(pos)` 不成立 → 直接落到 :364 開新倉 →
產生 `is_long=true, qty=437.3, entry_price=1.5744` 的 LONG。**指紋（entry=short exit 價、qty=short qty）
與事故完全一致。** `apply_fill` 沒有任何旗標能知道這是一筆 reduce/close 而非新開倉。

### 1.3 第二寫入源：`upsert_position_from_exchange` 對 size=0 直接 remove

`rust/openclaw_engine/src/paper_state/fill_engine.rs:87-155`（`upsert_position_from_exchange`）

```rust
// fill_engine.rs:98
if size == 0.0 {
    return self.positions_remove(symbol).is_some();   // ★ 把 short 移除 → flat
}
```

由 `event_consumer/loop_exchange.rs:531-569` 的 `PositionUpdate` 分支呼叫；Bybit 平倉後推 `side="None"`
→ :545 `effective_size=0.0` → `upsert_position_from_exchange(size=0)` → `positions_remove`。
**這是 B-1 Phase 2 引入的第二寫入源**（原本 `PaperState` 是純 fill 累積帳，B-1 額外把 WS 倉位狀態也
upsert 進來），它與 `apply_fill` 競爭同一份 `positions` map。

### 1.4 競態：close fill 看到的 `was_open` 落空，把幻影當新倉血緣

`rust/openclaw_engine/src/tick_pipeline/commands.rs:686`（`apply_confirmed_fill_with_close_maker_audit`）

```rust
// commands.rs:686
let was_open = self.paper_state.get_position(symbol).is_none();   // ★ 此時已 None（short 被先 remove）
...
let realized_pnl = self.paper_state.apply_fill(...);              // → 開出 LONG，realized_pnl=0.0
...
// commands.rs:710
if was_open && realized_pnl == 0.0 {
    // 把這筆「平倉 Buy」當成新開倉，寫 entry_context_id —— 幻影 LONG 被賦予正規開倉血緣
    self.paper_state.set_entry_context_id(symbol, &ctx_pre);
}
```

`realized_pnl == 0.0`（因為走了開新倉分支）→ close fill 被完整偽裝成一筆乾淨的新開倉，
連 `entry_context_id` 都正規寫入，下游無從察覺。

### 1.5 因果順序鐵證（為何平倉時 PositionUpdate 會先於 Fill）

- 兩條訊息走**同一個 unbounded channel**（`startup/private_ws.rs:95` `exchange_event_tx`），
  `handle_exchange_event` 逐條串行處理，**完全保留 Bybit 的推送順序**。
- Bybit V5 private WS 平倉時通常**同批或先推 `position` snapshot（成交後狀態 size=0）**，
  再推 `execution`（成交明細）；引擎側不做「先 Fill 後 Position」的重排或關聯。
- 一旦本批是 `position(size=0)` 在前：short 被 remove → 緊接的 close `Buy` `Fill` 落空 → 開出 LONG。
  這是**確定性可重現的競態**，不是偶發 corruption。

### 1.6 附帶發現（同檔，獨立次要 bug，順帶修）

`apply_fill` 平倉分支 `close_qty = pos.qty.min(qty)`（fill_engine.rs:299）：當 `qty > pos.qty`（真翻倉，
成交量大於既有反向倉）時，`remaining=0` 移除舊倉，但**餘量 `qty - pos.qty` 被丟棄，不會建反向新倉**。
PM 需求 #4 點明「只有成交量 > 既有反向倉量時才翻倉並用餘量建新倉」——目前**完全沒實作翻倉**，餘量靜默
吞掉。one-way 模式下交易所不會單筆既平且反開，故歷史未爆；但屬正確性缺口，修復一併補上（見 §4）。

---

## 2. 為何有本地帳？demo vs live_demo 是否不同？

### 2.1 為何用本地帳而非每 tick 拉 Bybit

- **所有 PipelineKind（Paper/Demo/Live）都用同一個 `PaperState` 作倉位帳本**：
  `tick_pipeline/pipeline_ctor.rs:52  paper_state: PaperState::new(balance)`（無模式分支）。
- snapshot、止損 best_price 追蹤、unrealized PnL、Kelly/動態風險、exit features 全部讀 `paper_state`。
  每 tick 拉 Bybit REST 不可行（rate-limit + 延遲 + SLA）。本地帳是 hot-path 的必要設計。
- `position_manager.rs`（`get_positions` Bybit 拉取）**只給 reconciler 對賬用**，不是 snapshot 來源。
  → **更正 PM prompt 推測**：「live_demo 疑似走 Bybit 拉取」不成立；snapshot 對**所有模式**都來自
  `PaperState`。差別只在 reconciler 額外輪詢 Bybit 比對，而比對軸接錯（§3）。

### 2.2 demo vs live_demo（風險面關鍵）

| 維度 | demo（PipelineKind::Demo） | live_demo（PipelineKind::Live + demo/testnet env） |
|---|---|---|
| 倉位帳本 | `PaperState` | `PaperState`（**相同**） |
| WS 雙寫（Fill + PositionUpdate） | 是 | 是（**相同**，private_ws.rs 不分 kind） |
| snapshot 來源 | `paper_state.positions()` | `paper_state.positions()`（**相同**） |
| reconciler | 有（tasks.rs:839 spawn） | 有 |

→ **此 bug 不是 demo 專屬。live_demo 與未來真 live 走完全相同的雙寫路徑，同樣會產生幻影**。
真 live 下幻影更危險：遮蔽「已空倉」→ 引擎以為持倉 → 不重新進場 / 對幻影派平倉空轉 → 卡死。
（事故 ② 的 00:25:55 卡死即此。）這是把風險評級定為**極高**的根據。

### 2.3 Python 是否有對應帳本？

`grep` `control_api` 全域：**無任何** `apply_fill` / `upsert_position` / 累積倉位邏輯，**也不讀
`trading.position_snapshots`**。倉位帳是 **Rust 單一權威**，Python 只是 GUI/控制面。
→ **無跨語言帳本需同步。修復是純 Rust，無 Python parity 工作。**

---

## 3. 為何 position_reconciler 沒抓到 7.4 小時背離（reconciler-miss 結論）

**結論：reconciler 在跑、範圍覆蓋 demo，但對賬軸接錯——它比的是「Bybit 上一輪 vs Bybit 這一輪」，
從不比「本地 `PaperState` vs Bybit」。幻影只活在 `PaperState`，在 reconciler 視野外，結構性盲視。**

鐵證：
1. `reconcile_once` / cycle loop 的 `baseline` 與 `current` **都來自 `fetch_current_view` →
   `pos_mgr.get_positions(Bybit)`**（mod.rs:296-304、:438、:470）。兩個都是 Bybit truth。
2. `classify(baseline, current)`（mod.rs:174-200）：`Ghost = (Some(_), None)` 意為
   「reconciler 的 Bybit baseline 有、這輪 Bybit 沒有」。TON 在 17:03 後 Bybit 一直 flat →
   每輪 `baseline` 被 seed 成 flat、`current` 也 flat → `classify(None, None) = Match` → **永不 drift**。
3. reconciler **確實有讀 `paper_state` 鏡像** `engine_positions_mirror`（mod.rs:826-829），但用途是
   **S-1：在 verdict 已是 Ghost 之後，用 mirror 取本地方向 `is_long` 去派平倉**（mod.rs:856、:910
   `dispatch_ghost_converge`）。`process_ghosts` 第一行 `if !matches!(verdict, Ghost) { continue }`
   （mod.rs:838）——**mirror 只是 Ghost 收斂的「方向來源」，不是「偵測來源」**。drifts 裡根本沒有 TON，
   mirror 即使有 `TON=long` 也永不被檢視。
4. warmup + 6-RC-9 staleness reseed（mod.rs:487-494）會週期性把 `current`（flat）adopt 成 baseline，
   進一步保證 baseline 永遠跟著 Bybit flat。

→ 即「偵測 Bybit 自我跨輪變化」與「偵測本地帳 vs Bybit 背離」是**兩條不同的對賬軸**，reconciler 只做了
前者。本 bug 屬後者，故 7.4 小時零告警。這正是「止血告警」要補的軸（§5）。

**Call-path grep proof**（reconciler 偵測軸不含 paper_state 完整倉位）：
- `fetch_current_view` 唯一資料源 = `pos_mgr.get_positions`（grep mod.rs，0 個 `paper_state.positions(`
  caller 在偵測路徑）。
- `engine_positions_mirror` 全 caller = mod.rs:827 / :646（取方向）+ orphan_handler dispatch，
  **0 個用於「掃 mirror 找 Bybit 無對應」的偵測**。

---

## 4. 修復設計（surgical，Rust-first，最小改動）

修復分**根因修**（消除亂序雙寫）與**正確性補強**（reduce/close 演算法 + 翻倉餘量）。

### 4.1 根因修（首選，必做）— 消除 PositionUpdate 對倉位 map 的破壞性寫入

**問題本質**：`apply_fill`（fill 累積）與 `upsert_position_from_exchange`（WS 倉位 upsert）是**兩個無序
競爭的寫入源**。Bybit `execution` 流本身已是倉位變動的權威來源（每筆成交都帶 side/qty/closedSize），
WS `position` 流只應作**對賬/校驗**，不應**主動 remove/翻轉**本地 fill 帳。

**設計選擇（推薦 Option A）**：

- **Option A（推薦，最小且根治）**：把 `PositionUpdate` 對 `PaperState` 的角色從「authoritative 寫入」
  降為「**advisory 校驗 + 收斂**」。具體：
  - `event_consumer/loop_exchange.rs:531-569` `PositionUpdate` 分支**不再呼叫
    `upsert_position_from_exchange` 去 add/flip/remove**。改為呼叫一個新的
    **只讀比對 helper**（如 `paper_state.reconcile_against_exchange(symbol, is_long, size, avg_price)`）：
    - Bybit `size==0` 且本地有倉 → **記錄背離 + 走既有 `converge_exchange_zero_close` 收斂路徑**
      （commands.rs:1267，已存在、已測、是 exchange-zero 收斂的正規入口），而非裸 `positions_remove`。
    - Bybit `size>0` 且方向/qty 與本地不符（超閾值）→ 告警（§5），收斂交給 reconciler / 既有路徑。
  - 倉位的**唯一 mutating 來源變回 `apply_fill`**（execution 流）。`apply_fill` 收到 close `Buy` 時
    short 還在 map → 正確走平倉分支歸 flat。**競態消失。**
  - `import_positions`（B-1 Phase 2 啟動種倉，fill_engine.rs:44）保留——那是 cold-start 從交易所
    snapshot 播種，無競態（啟動時無 in-flight fill）。

- **Option B（次選，治標）**：保留雙寫，但在 `apply_fill` 加 `is_reduce_only: bool` 旗標
  （由 `PendingOrder.is_close` 推導，loop_exchange.rs:266 傳入）。當 `is_reduce_only==true` 且本地
  無既有倉位 → **不開新倉，記為「孤兒平倉」audit 並 no-op**（reduce-only 永遠不該開倉）。
  - 缺點：仍有兩個寫入源、仍需處理 PositionUpdate 先到把倉 remove 的情況（reduce-only fill 落空後
    no-op，至少不再產生幻影 LONG，但會漏記真實 PnL，需配合 §4.2）。屬「防止幻影」但不根治雙寫。

**PA 裁決**：推薦 **Option A**。理由：(1) 根治「兩寫入源亂序」這個 class，而非只堵 TON 這一例；
(2) 復用既有 `converge_exchange_zero_close`（已測收斂路徑），不新增收斂語義；(3) 符合 Root Principle 8
（交易可重建）——倉位變動只有 execution 一條真相線，可重放。Option B 留作 fallback / 防禦縱深
（即使做了 A，§4.3 的 reduce-only guard 仍值得作為第二道防線）。

### 4.2 reduce/close fill 正確演算法（用淨額 + closedSize 完全平倉歸 flat）

在 `apply_fill`（fill_engine.rs:295-385）強化既有平倉分支，使其符合 PM #4 的淨額語義：

```
給定 fill (is_long, qty)：
  若本地有同向倉  → 同向加倉（既有邏輯，不變）
  若本地有反向倉 pos：
      close_qty = min(qty, pos.qty)
      結算 close_qty 的 PnL（既有）
      remaining_pos = pos.qty - close_qty
      若 remaining_pos > eps → 減倉（既有，部分平倉）
      否則 → 完全平倉歸 flat（既有）
      ★ 新增翻倉：overflow = qty - close_qty
        若 overflow > eps（成交量 > 既有反向倉量，真翻倉）→
            用 overflow 以 fill_price 建反向新倉（is_long 方向，entry=fill_price）
  若本地無倉：
      ★ Option A 下：close fill 不會再落空（PositionUpdate 不再先 remove）。
        但為防禦，仍保留：若此 fill 是 reduce-only（§4.3）→ no-op + audit，不開倉。
        若是 genuine 開倉 fill → 開新倉（既有 :364，正確）。
```

關鍵不變量：
- **reduce-only / close fill 在本地無反向倉時，永不開新倉**（防幻影，§4.3）。
- **完全平倉（closedSize == 既有倉量）→ 必歸 flat**，不留殘餘（既有 `remaining > 1e-12` 已處理，
  保留；dust evict T2a 保留）。
- **翻倉只在 `qty > pos.qty` 時用餘量建反向倉**，且 entry=fill_price（補 §1.6 缺口）。

### 4.3 reduce-only guard（防禦縱深，建議與 A 同做）

`apply_confirmed_fill_with_close_maker_audit`（commands.rs:659）已能從 `loop_exchange.rs:266` 的
`po`（PendingOrder）拿到 `po.is_close`。建議把 `is_close`（reduce-only 語意）一路傳進 `apply_fill`，
在「本地無倉」分支判定：reduce-only fill 落空 → 不開倉 + 記 `unattributed/orphan_close` audit。
這樣即使 Option A 有任何遺漏路徑，也絕不會再開出幻影反向倉。**這是 fail-closed（Root Principle 6）。**

### 4.4 跨語言一致性

無。Python 無倉位帳本（§2.3）。純 Rust 改動。

---

## 5. 對賬告警設計（補「本地帳 vs Bybit」這條缺失的軸）

**目標**：週期性比對「`PaperState` 本地帳 vs Bybit `/v5/position/list`」，在 **qty / side / 有無** 背離時
告警。最大化復用既有 reconciler，不新建基礎設施。

### 5.1 接入點（複用 reconcile cycle，零新 task）

reconciler 主迴圈每 30s（`RECONCILE_INTERVAL_SECS`）已經：(a) 拉到 `current`（Bybit truth，mod.rs:470）、
(b) 持有 `engine_positions_mirror`（paper_state 鏡像）。**告警偵測就加在 mod.rs:528 之後**
（drifts 分類完、orphan/ghost 處理之外），新增一段獨立的 **phantom 偵測**：

```
for (symbol, local_view) in engine_mirror_snapshot:        # 本地帳有
    bybit = current.get(symbol|side)
    若 bybit 不存在 或 bybit.size == 0:                     # Bybit 無 / flat
        → PHANTOM 背離：本地有倉、交易所無 → 告警 + audit
    否則若 side 不符 或 |qty 差| 超閾值:
        → MISMATCH 背離 → 告警 + audit
```

這條軸與既有 Ghost 偵測**互補**：既有 Ghost 比「reconciler Bybit baseline vs Bybit」；
新軸比「paper_state mirror vs Bybit current」。**新軸不依賴 reconciler 自己的 baseline**，
故能抓到 baseline 永遠 flat 的 TON 幻影。

### 5.2 mirror 需帶 qty（小幅升級）

現 `engine_positions_mirror` 只有 `(symbol → is_long)`（paper_state/mod.rs:122）。PM 要 qty 背離，
需把 mirror 值從 `bool` 升為輕量 `struct { is_long: bool, qty: f64 }`（或新增平行 `mirror_qty` map）。

- **推薦**：把 mirror 升為 `Arc<RwLock<HashMap<String, PhantomMirrorView>>>`，
  `positions_insert/remove/clear`（paper_state/mod.rs:211-230）同步寫 qty。blast radius：
  mirror 既有 consumer 僅 orphan_handler（取 `is_long`）+ reconciler S-1，改 struct 後這兩處取
  `.is_long` 即可，改動極小。
- **次選（更小但資訊弱）**：mirror 不動，告警只報 side + 「本地有/Bybit 無」，qty 從 V014 audit 已有的
  `baseline_qty`/`current_qty` 欄位旁路補（但本地 qty 不在 reconciler 手上 → 只能報 side/有無）。
  PA 傾向推薦版（qty 背離是事故核心特徵，值得這點 mirror 升級）。

### 5.3 告警通道（復用既有，三層）

1. **DB audit（必做）**：復用 `spawn_reconcile_audit` 模式（mod.rs:248），寫
   `observability.engine_events`，`event_type="reconcile_phantom_local"`，
   `source="position_reconciler"`，payload 帶 `{symbol, side, local_qty, bybit_qty, engine}`。
   零新表、零 migration。
2. **canary_events.jsonl（建議）**：事故 ② 的教訓是「宕機 20h 無人知」。phantom 背離應同時
   append 一條到 `$OPENCLAW_DATA_DIR/canary_events.jsonl`（watchdog 既有告警 sink，
   `engine_watchdog.py:78/488`），event 如 `PHANTOM_POSITION_DETECTED`，
   讓既有 GUI-configurable alert（2026-06-05 watchdog alert wiring，`alert_config.json` →
   Telegram/webhook）能轉發。接法：reconciler 經 `canary_writer`（canary_writer.rs:89 `try_send`）
   或 IPC 觸發；具體選型留 E1（傾向直接 append，與 watchdog 同 sink 約定）。
3. **（可選）自動收斂**：phantom 確認後可走 §4.1 的 `converge_exchange_zero_close` 把幻影本地倉移除
   （Root Principle 5/9：survival）。但**首版只告警 + audit，不自動收斂**——避免在根因（§4.1）未上線前
   就動 mutating 路徑。收斂作為 Phase 2，operator sign-off gated。

### 5.4 頻率與防抖

- 頻率：搭 reconcile cycle 30s 一次（足夠；事故持續 7.4h，30s 偵測延遲可接受）。
- 防抖：沿用既有 2-cycle streak 模式（mod.rs:867 `last_ghost_keys`），phantom 連續 2 cycle 才告警，
  避開「Bybit position WS 比 reconciler REST 慢一輪」的瞬時假背離。
- 點查 gate：告警前對 phantom symbol 做單 symbol 點查（復用 `GhostPointQuery` 三分支，mod.rs:882），
  確認 Bybit 真 size==0 才告警，避免主 fetch limit=20 分頁截斷誤報。

---

## 6. 需求 #2 確認（修好 #1 後策略能否重新入場）— #2 是 #1 的下游

**確認：#2（錯過 TON +5%）是 #1（幻影 LONG）的直接下游，無獨立投機邏輯需設計。**

機制：策略入場前會檢查「該 symbol 是否已有倉」（避免重複進場）。幻影 LONG 佔據
`paper_state.positions["TONUSDT"]` → 引擎以為自己持有 long → 不再對 TON 開新倉 → 錯過真實 +5%。
**一旦 §4 修好（close fill 正確歸 flat，不開幻影）**，17:03 後 `paper_state` 對 TON 即為 flat →
策略的「已持倉」檢查放行 → 正常重新評估入場。**#2 隨 #1 自動解決。**

獨立再入場阻塞點排查（無新增）：
- 幻影自身的 trailing（00:00:06 `phys_lock_gate4_giveback`）觸發卻平不掉 → 跨 thread 空轉 → 卡死。
  此空轉也源於幻影存在；#1 修好後不會產生需要平的幻影，空轉消失。
- 不需要、也**明確不設計**任何「複利 / 自動加倉 / 投機補單」邏輯（PM 明示）。修復只恢復「平倉=flat」
  這個正確語義，讓策略回到正常入場判斷。

---

## 7. E1 任務拆解 + E4 測試計劃

### 7.1 E1 拆解（按檔案/函數，標明並行性）

| 任務 | 檔案 / 函數 | 內容 | 並行 |
|---|---|---|---|
| **T1（根因，linchpin）** | `paper_state/fill_engine.rs::apply_fill` + 新 helper `reconcile_against_exchange` | 強化平倉分支（淨額 + 翻倉餘量 §4.2）；新增「本地無倉時 reduce-only fill 不開倉」guard（§4.3，需 T2 傳旗標）；新增只讀 advisory 比對 helper | 與 T3 部分並行；T2 依賴其簽名 |
| **T2** | `event_consumer/loop_exchange.rs::handle_exchange_event` PositionUpdate 分支(:531-569) + Fill 分支傳 `is_close`(:266) | Option A：PositionUpdate 不再 `upsert`（add/flip/remove），改呼 advisory helper + 對 size=0 走 `converge_exchange_zero_close`；Fill 分支把 `po.is_close` 傳入 apply_fill 鏈 | 依賴 T1 helper 簽名（serial-after-T1 簽名定稿） |
| **T3** | `tick_pipeline/commands.rs::apply_confirmed_fill_with_close_maker_audit`(:659) + `apply_confirmed_fill`(:617) | 增 `is_close: bool` 參數，透傳到 `apply_fill`；`was_open && realized==0` 分支在 reduce-only 落空時不寫 entry_context_id | 與 T1 並行（不同檔） |
| **T4** | `paper_state/mod.rs` mirror 升級(:122,:211-230) + `position_reconciler/orphan_handler.rs::OrphanHandlerConfig`(:198) consumer 取 `.is_long` | mirror 值 `bool` → `PhantomMirrorView{is_long,qty}`；同步 insert/remove/clear；既有 consumer 改取 `.is_long` | 與 T1/T3 並行（不同檔，僅 reconciler 取值處需同步改） |
| **T5** | `position_reconciler/mod.rs` cycle loop(:528 後) | 新增 phantom 偵測軸（§5.1）：mirror vs Bybit current，2-cycle streak + 點查 gate + 寫 `observability.engine_events` phantom audit + canary append | 依賴 T4（mirror 帶 qty）；serial-after-T4 |

並行波次：
- **Wave 1（並行）**：T1（簽名先定）、T3、T4。
- **Wave 2（serial）**：T2（待 T1 helper 簽名）、T5（待 T4 mirror）。

檔案重疊檢查：T1=fill_engine.rs；T2=loop_exchange.rs；T3=commands.rs；T4=paper_state/mod.rs +
orphan_handler.rs（取值行）；T5=position_reconciler/mod.rs。**互不重疊**（T4 與 T5 都碰 reconciler
但 T4 只改 orphan_handler 取值處、T5 改 mod.rs cycle，可協調或令 T4→T5 serial 同一 E1）。

### 7.2 E4 測試計劃（fill 應用單元測試，1e-? 精度）

新增/擴充 `paper_state/tests.rs` 與 `event_consumer/tests/`：

1. **平倉到 flat**：open short 437.3@1.5929 → apply close Buy 437.3@1.5744 → 斷言 positions 為空（flat）、
   realized_pnl = (1.5929-1.5744)*437.3（short 盈利，1e-9 容差）。
2. **部分減倉**：open short 100 → apply Buy 40 → 斷言 short 剩 60、entry 不變、realized = 40 對應 PnL。
3. **真翻倉（qty > 既有反向倉，§4.2 新邏輯）**：open short 100@1.6 → apply Buy 150@1.5 →
   斷言：short 平掉、**新建 long 50@1.5**（餘量 50）、realized = (1.6-1.5)*100。
   （補 §1.6 缺口的回歸守衛。）
4. **★ 17:03 情境回歸測試（核心，必含）**：模擬 Bybit 平倉訊息**亂序**——先送
   `PositionUpdate(side=None,size=0)` 再送 `Fill(Buy 437.3@1.5744, is_close=true)` →
   斷言：positions 對 TONUSDT 為 **flat（不是 LONG）**、realized_pnl 記在 short close 上、
   **不產生任何 long 倉**、**不寫幻影 entry_context_id**。這是把 bug 釘死的 golden test。
5. **reduce-only fill 落空 no-op（§4.3）**：本地無倉 → apply `Fill(Buy, is_close=true)` →
   斷言 no-op（不開倉）+ 記 orphan_close audit。
6. **PositionUpdate advisory 不破壞 fill 帳（Option A）**：open short via fill → 送
   `PositionUpdate(size>0, 同向)` → 斷言本地倉**不被 upsert 覆蓋**（entry/best_price 保留）；
   送 `PositionUpdate(size=0)` → 斷言走 converge 路徑（mock cmd_tx 收到 close）而非裸 remove。
7. **reconciler phantom 偵測（T5）**：mock `current`(Bybit)=flat、`engine_mirror`=有 TON long →
   斷言：2-cycle streak 後寫 `reconcile_phantom_local` audit + canary 事件；
   單 symbol 點查回 `StillHasPosition` 時**不**告警（防分頁假背離）。
8. **跨語言一致性**：N/A（Python 無倉位帳本，§2.3）。不需 1e-4 對賬。

回歸：跑 `cargo test -p openclaw_engine`（fill_engine / event_consumer / position_reconciler
既有測試套件）+ Linux `cargo test` authoritative regression（Mac 過不等於 Linux 過，memory 教訓）。

---

## 8. 風險

| 風險 | 說明 | 緩解 |
|---|---|---|
| **核心熱路徑（極高）** | `apply_fill` / `PositionUpdate` 是每筆成交都過的 mutating 路徑，改錯會影響所有倉位記帳、PnL、止損 best_price | 嚴格 bit-exact 保留既有算術順序（fill_engine MODULE_NOTE 要求）；只在「本地無倉 reduce-only」「翻倉餘量」「PositionUpdate advisory」三處改語義；E4 golden test #4 釘死回歸 |
| **三模式全覆蓋（極高）** | 修改影響 demo / live_demo / 真 live（共用 PaperState，§2.2）。真 live 下記帳錯 = 真錢風險 | 三引擎獨立驗（CLAUDE 3E-ARCH，禁只驗 demo 就 PASS）；E2 必查 live 路徑；先 demo soak 再考慮 live_demo |
| **Option A 行為變更** | PositionUpdate 從 authoritative 降為 advisory，改變 B-1 Phase 2 既有語義；若某路徑依賴 WS upsert 補倉（如 fill 漏接時靠 position WS 補），降級後可能漏倉 | 保留 `import_positions` cold-start 種倉；保留 `converge_exchange_zero_close` 收斂；E2 審查「是否有 fill 漏接靠 PositionUpdate 兜底」的場景；若有，Option B（reduce-only guard）作 fallback |
| **mirror 升級 blast radius（中）** | mirror 值改 struct，orphan_handler + reconciler S-1 取值處需同步 | grep 確認 mirror consumer 僅 2 處（已驗）；改 `.is_long` 即可；T4 單 E1 一致改完 |
| **告警誤報（中）** | Bybit position WS 比 reconciler REST 慢一輪 → 瞬時「本地有/Bybit 無」假背離 | 2-cycle streak + 單 symbol 點查 gate（§5.4），與既有 Ghost 收斂同防抖 |
| **未自動收斂（低，by-design）** | 首版只告警不自動移除幻影 → 若根因修有遺漏，幻影仍會短暫存在直到下次重啟 | 根因修（§4.1）上線後幻影不再產生；告警是縱深防線；自動收斂列 Phase 2 operator-gated |
| **硬邊界** | **無觸碰**。不改 live_execution_allowed / max_retries / system_mode / authorization；不加隱藏 retry；reduce-only guard 是 fail-closed（Root Principle 6）；不繞 Guardian/lease | — |

---

## 9. E2 必查 3 點

1. **Option A 是否漏掉「fill 漏接靠 PositionUpdate 兜底」場景**：grep 確認除 cold-start 外，是否有
   依賴 `upsert_position_from_exchange` 的 add/flip 來補本地帳的合法路徑；若有，需保留或改走 advisory+告警。
2. **`apply_fill` 翻倉餘量新邏輯的 bit-exact**：確認新增的 overflow 建倉不改既有平倉/加倉分支的算術順序，
   PnL / entry_notional / 加權均價數值不漂移。
3. **三模式（尤其真 live）路徑一致性**：確認 `is_close` 旗標在 live 路徑也正確傳遞、reduce-only guard 在
   live 下不會誤擋 genuine 開倉、phantom 告警在 live engine_label 下正確標記。

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-07--phantom-position-fill-bug-design.md
