# E1 — P2-ORDERS-INTENT-ID-WRITER-GAP-1 implementation

Date: 2026-05-19
Role: E1
Worktree: `/Users/ncyu/Projects/TradeBot/srv`
Scope: Mac source/test only（operator 2026-05-19 授權；不部署 Linux / 不
mutate runtime）。
Ticket: P2-ORDERS-INTENT-ID-WRITER-GAP-1（TODO.md line 473，wave 1.5 backlog）

## 1. 任務摘要

E3 baseline 2026-05-15 commit `b98706d5` 揭露 7d **1394 demo + 1021 live_demo
orders** 之 `trading.orders.intent_id` 100% NULL，導致 `trading.intents →
trading.orders` JOIN 失效、Guardian-pass-rate 業務 KPI 無法計算。

RCA → 是 **writer 漏接**：schema 自 V003 起已有 `intent_id TEXT` NULL 欄位，
但 Rust pipeline `OrderDispatchRequest → PendingOrder → TradingMsg::Order →
flush_orders INSERT` 全鏈條從未攜帶此欄。本 PR 補齊 plumbing 並維持
fail-loud 原則（writer 端不合成 fake id）。

## 2. Root Cause（chosen hypothesis）

**(a) Rust OMS writer 不在 INSERT 列含 intent_id**（dispatch §「likely root cause」清單）。

關鍵證據：
- `rust/openclaw_engine/src/database/trading_writer.rs:748` INSERT 列表為
  `(ts, order_id, symbol, side, order_type, time_in_force, qty, strategy_name,
  category, is_paper, status, engine_mode)` — 12 欄，無 intent_id。
- `rust/openclaw_engine/src/database/mod.rs:452` `TradingMsg::Order` enum
  variant 共 11 個 field（order_id/ts_ms/symbol/side/order_type/time_in_force/
  qty/strategy_name/is_close/engine_mode），同樣**無 intent_id**。
- `OrderDispatchRequest`（`tick_pipeline/mod.rs:613`）有 context_id 但**無
  intent_id**。
- `PendingOrder`（`event_consumer/types.rs:51`）同樣**無 intent_id**。

但所有 entry path 的 intent_id 構造仍 deterministic：`make_intent_id(em,
intent.symbol, event.ts_ms)`（`on_tick_helpers.rs:141`），與同 tick 寫入
`trading.intents.intent_id` byte-equal — 只是這個 id 在 dispatch 後從未被
保留到 OrderDispatchRequest 後續鏈。

`sql/migrations/V003__trading_agent_tables.sql:222` 已宣告 `intent_id TEXT,
                   -- 邏輯 FK → intents` — schema 自始 nullable，writer 端
omit 即得 NULL。修法為純 plumbing，無需 V### migration。

排除 (b)/(c)/(d)：
- (b) Python persist_order：本案路徑全 Rust，Python 不參與 trading.orders 寫
- (c) Rust→Python IPC drop：trading.orders 寫由 Rust 直連 PG，無 IPC 中轉
- (d) client-side 生成但未持久化：intent_id 不是 client-side 生成，是
  Rust 內部 deterministic 函數

## 3. 修改清單（Plumbing chain）

入場 entry path：strategy → IntentProcessor → OrderDispatchRequest →
PendingOrder → TradingMsg::Order → flush_orders → trading.orders.intent_id。

| 檔 | 修改 | LOC delta |
|---|---|---|
| `rust/openclaw_engine/src/database/mod.rs` | `TradingMsg::Order` 增 `intent_id: Option<String>` 欄 + 16 行中文 doc | +17 |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | `OrderDispatchRequest` 增 `pub intent_id: Option<String>` + 7 行中文 doc | +8 |
| `rust/openclaw_engine/src/event_consumer/types.rs` | `PendingOrder` 增 `pub intent_id: Option<String>` + 4 行中文 doc | +5 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 2 處 producer：exchange entry 帶 Some(make_intent_id(em, symbol, event.ts_ms))；paper shadow 同帶 | +24 |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 4 處 close-path producer（execute_position_close / close_maker fallback / ipc_close_all / ipc_close_symbol）全 `intent_id: None` | +12 |
| `rust/openclaw_engine/src/event_consumer/dispatch.rs` | `PendingOrder` 鏡射 `intent_id: req.intent_id.clone()` | +5 |
| `rust/openclaw_engine/src/event_consumer/loop_handlers.rs` | 2 處：`TradingMsg::Order` 帶 `po.intent_id.clone()`；dispatch-failed close fallback 重建 `PendingOrder { intent_id: None }` | +9 |
| `rust/openclaw_engine/src/database/trading_writer.rs` | `ORDER_COLS` 12 → 13；INSERT 列表加 `intent_id` 欄；destructure 加 `intent_id`；`push_bind(intent_id.as_deref())` | +10 |
| 測試 fixtures（6 檔） | 既有 PendingOrder / OrderDispatchRequest 構造補 `intent_id` 欄（多為 None，1 處 Some 代表性值） | +24 |
| **新測試** `pending_registration_order_type_tests.rs` | 5 條 P2-WRITER-GAP regression：entry/close path/PostOnly/Clone/dispatch_failed | +124 |

**合計：~+238 LOC**；無刪除；無 V### migration（schema 早於 V003 已 OK）。

## 4. 關鍵 diff（最核心 4 點）

### 4.1 TradingMsg::Order 新增 intent_id

```rust
// database/mod.rs:452-477
Order {
    // ... existing fields ...
    engine_mode: String,
    /// P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：策略入場意圖 id。
    /// 邏輯 FK → trading.intents.intent_id（V003 起即存在但寫入器漏接）。
    ///
    /// 賦值原則（嚴格 fail-loud，不在 writer 端合成以免遮蓋上游 bug）：
    /// - 入場 entry order：Some(make_intent_id(em, intent.symbol,
    ///   event.ts_ms))，與同 dispatch tick trading.intents.intent_id byte-equal。
    /// - 平倉 close order / IPC close / orphan：None（無對應 strategy intent，
    ///   保 NULL 為誠實表述）。
    intent_id: Option<String>,
},
```

### 4.2 Producer（entry path）

```rust
// tick_pipeline/on_tick/step_4_5_dispatch.rs:~903（exchange entry）
let send_result = tx.send(OrderDispatchRequest {
    // ... existing ...
    spine_stub_report_id: Some(spine_stub_report_id),
    // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：entry path 帶
    // intent_id，與同 tick 寫入 trading.intents 的 id byte-equal。
    intent_id: Some(make_intent_id(em, &intent.symbol, event.ts_ms)),
});
```

### 4.3 Writer INSERT

```rust
// database/trading_writer.rs:748-789
// P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：增 intent_id 欄
// （V003 起 schema 即有 TEXT NULL，但 writer 自始未綁定）。
let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
    "INSERT INTO trading.orders \
     (ts, order_id, symbol, side, order_type, time_in_force, qty, strategy_name, \
      category, is_paper, status, engine_mode, intent_id) ",  // ← 加 intent_id
);
qb.push_values(chunk.iter(), |mut b, msg| {
    if let TradingMsg::Order {
        // ... existing ...
        engine_mode,
        intent_id,  // ← 加 destructure
    } = msg {
        // ... existing binds ...
        b.push_bind(engine_mode.as_str());
        b.push_bind(intent_id.as_deref());  // ← Option<&str> → SQL TEXT NULL
    }
});
```

### 4.4 ORDER_COLS bump（PG 65535 bind limit guard）

```rust
// database/trading_writer.rs:189-191
// P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：12 → 13；新增 intent_id 欄。
const ORDER_COLS: usize = 13;
```

既有單元測試 `test_batch_limits_under_pg_param_max` 自動覆蓋驗證
`chunk_rows_for_columns(13) * 13 <= 65535`（5042 * 13 = 65546 — 注意，
chunk_rows clamp 機制需手算驗證）。實際 `chunk_rows_for_columns(13) = 5041`
（floor(65535/13)），5041 * 13 = 65533 ≤ 65535 — pass。

## 5. 治理對照

| 規約 | 對照 |
|---|---|
| `max_retries=0` 不可改 | 未動 |
| `live_execution_allowed` / `execution_authority` / `system_mode` | 未動 |
| `unsafe` / `unwrap()` / `expect()`（non-test） | 未引入 |
| 跨平台 grep（無硬編碼路徑） | 未引入 |
| 新 singleton | 未引入 |
| V### migration | 未引入（schema 自 V003 已 OK） |
| 文件 800/2000 行 | trading_writer.rs +10 後 1499 行 < 2000 |
| 注釋默認中文 | 所有新增 8 處 inline doc + 5 個 test 全中文 |
| MODULE_NOTE | 既有 module 未新增；未涉及新檔 |
| Writer-side fake id 合成 | **禁止**（dispatch §「no synthesize on writer side」）：所有 close path 一律 `None`，不憑空合成 |
| fail-closed | close path NULL 是誠實表述；entry path 漏接 future bug 會立即在 NULL 比率反映 |

## 6. 驗證

- `cargo check -p openclaw_engine --release` → green（10.5s）
- `cargo test -p openclaw_engine --release --lib` → **2998 passed / 0 failed
  / 1 ignored**
- `cargo test -p openclaw_engine --release pending_registration_order_type_tests`
  → **23 passed / 0 failed**（18 既有 + 5 新增）
- `cargo test -p openclaw_engine --release trading_writer` → 12 passed
- `cargo test -p openclaw_engine --release pending_sweep` → 16 passed
- `cargo test -p openclaw_engine --release event_consumer` → 177 passed
- `cargo test -p openclaw_engine --release dispatch` → 101 passed
- `cargo test -p openclaw_engine --release dual_rail` → 24 passed
- `pytest program_code/.../tests/ -k "orders or oms or persist_order"` →
  19 passed / 1 fail（**pre-existing**，stash 對照同 fail，與本 PR 無關）

新增 5 條 regression test（`pending_registration_order_type_tests.rs`）：

1. `test_handle_pending_registration_propagates_entry_intent_id` — entry path
   PendingOrder.intent_id=Some(...) → TradingMsg::Order.intent_id 必同值
2. `test_handle_pending_registration_close_path_intent_id_stays_none` —
   is_close=true & PendingOrder.intent_id=None → Order.intent_id 必為 None
   （釘住「writer 不合成 fake id」原則）
3. `test_handle_pending_registration_postonly_carries_intent_id` — PostOnly
   limit 也傳 intent_id（覆蓋 maker 路徑）
4. `test_pending_order_clone_preserves_intent_id` — derive(Clone) 必複製
   intent_id（pending_orders.insert(.clone()) 依賴此）
5. `test_dispatch_failed_close_maker_synthetic_pending_order_has_no_intent_id`
   — dispatch-failed close-maker 重建 PendingOrder 走 type check：未來若
   loop_handlers.rs:424 漏 intent_id 欄位編譯失敗（型別系統守門）

## 7. Backfill 設計備忘（已寫，不執行）

寫了一份 backfill design memo（path 下方），含：
- 候選 JOIN 邏輯（5s 視窗 + strategy/symbol/em 嚴格匹配 + ROW_NUMBER 最早匹配）
- SQL 草稿（SELECT-only / UPDATE 草稿均含 `DO NOT EXECUTE` 警語）
- 風險清單（multi-match pollution / TimescaleDB chunk lock / strategy
  normalisation drift）
- 推薦執行流程（MIT review → operator → E2 review → staging dry-run → 分批
  + audit log）

需 operator + MIT review 才能立 P2-ORDERS-INTENT-ID-BACKFILL-1 獨立 ticket
執行。建議：writer fix 部署後至少 24h 監測（coverage_pct ≥ 95%）再決定。

Backfill memo: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--p2_orders_intent_id_backfill_design_memo.md`

## 8. 不確定 / 求 review 點

1. **paper shadow 路徑 intent_id**：step_4_5_dispatch.rs:~1386 paper-only
   shadow 帶 `intent_id: Some(make_intent_id(em, ...))`；但 paper_only path
   `is_primary=false`，**不註冊 PendingOrder**（dispatch.rs:531 `if
   req.is_primary` gate），故不會寫入 trading.orders（writer 只在
   `handle_pending_registration` 觸發）。current shadow 路徑帶值純為一致性 +
   防禦未來 shadow 路徑升級為追蹤。E2 若認為「未實際寫入則應 None」可改回
   None，無功能差異。

2. **commands.rs：external_intent path（IPC submit_external_order）**：此路徑
   在 commands.rs:300+ 是 IPC 觸發單筆 paper fill 模擬，emit 順序為
   Intent + Fill **不 emit TradingMsg::Order**（無 trading.orders row），
   故無 plumbing 缺失。本 PR 不動此路徑。

3. **ORDER_COLS 13 vs 65535 limit**：手算 5041 * 13 = 65533 ≤ 65535 OK；
   既有 `test_batch_limits_under_pg_param_max` 自動覆蓋（已 pass）。

4. **TimescaleDB chunk impact**：本 PR 只改 writer 行為 + schema 既有，沒有
   ALTER TABLE / CREATE INDEX；deploy 重啟 engine 即生效，無 schema
   migration race。

5. **GUI / Python downstream**：grep `intent_id` 在 Python 端確認沒有
   reader 對 `orders.intent_id` 做嚴格 NOT NULL 預設（既有 1394 + 1021 NULL
   多日跑沒爆 → 表 Python 端已 fault-tolerant on NULL）。本 PR 未動 Python。

## 9. Operator 下一步

1. 等 E2 review：尤其 §4 4 處關鍵 diff + §8 paper shadow 設計選擇
2. E4 regression：本 PR `cargo test --lib` 2998 PASS；E4 自跑 integration
   tests
3. PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）
4. Linux deploy：純 Rust engine 改動 → `restart_all.sh --rebuild` 後生效；
   無 schema migration 步驟
5. Post-deploy 24h 觀測：query coverage_pct（見 backfill memo §5）；達標
   後再決定 backfill

## 10. 關鍵教訓（將追加至 memory.md）

1. **schema vs writer 解離 audit**：V003 起 schema 早就 ready，但 writer
   12 欄 INSERT 列表自始遺漏 intent_id；type system 不會 catch 「schema 有
   欄但 INSERT 漏」這類 nullable-column drift。Lesson = audit table-level
   `information_schema.columns` 必對齊 codebase grep `INSERT INTO <table>`
   列表逐欄比對。

2. **deterministic id 重建**：`make_intent_id(em, symbol, ts_ms)` 是 pure
   function，同 tick 寫多次得 byte-equal id；entry path 修法即「同 tick 用
   同三元組重算」即可，無需新存儲。Lesson = id factory pure function 設計
   讓 plumbing gap 可零成本補回。

3. **fail-loud over fake-id**：dispatch §「no synthesize on writer side」是
   關鍵紅線；close path NULL 是正確語意（無 strategy intent 對應），合成 fake
   id 會永遠遮蓋 future close-path bug。Lesson = audit/補救要保留信號，
   不能用「pad to non-null」掩蓋本質。

4. **PendingOrder 構造多點**：6 處 PendingOrder 構造（pending_sweep / loop_handlers
   x 2 / tests/mod / dispatch / tests fixtures）必同步加欄；compile error 是
   守門。Lesson = 新增 struct 欄即用編譯器強制掃描 caller，比 grep `PendingOrder {`
   更穩。

5. **既存 ORDER_COLS 邊界 test 自動覆蓋**：`test_batch_limits_under_pg_param_max`
   定義了 PG bind limit 紅線；改 ORDER_COLS 12→13 即 test 自動 reverify，無
   需新測。Lesson = 邊界守門 test 設計得當，加一欄=零成本。
