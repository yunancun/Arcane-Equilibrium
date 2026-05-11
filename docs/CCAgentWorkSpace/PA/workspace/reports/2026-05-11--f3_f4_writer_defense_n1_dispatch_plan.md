# F3/F4 Writer-Side Defense — Sprint N+1 Dispatch Plan

**Author**: PA · **Date**: 2026-05-11 · **HEAD**: `9463f778` (Mac 已三端 sync)
**Scope**: 寫 P1-RCA-1 4-bug chain 的 F3 + F4 producer-side fix（B1 Option B `d4867676` 已 producer-side land，本 plan 是 **writer-side 永久防線**）的 Sprint N+1 schedule + spec deepening + F4 option 拍板
**Posture**: **schedule only**，不啟動 IMPL；本 plan 是給 PM 在 N+1 dispatch 中插入 F3/F4 兩 ticket 的依據
**Status**: READY FOR PM SCHEDULE — F3/F4 已 spec 完成、option 拍板、跨 wave 0 衝突 verify

---

## §0 TL;DR

**F3** = `trading_writer.rs:406-414` 把 WARN「rows still INSERT (fail-soft)」誤導文案改為 ERROR + 文字準確化（移除「fail-soft」「cron backfill will reconcile」字樣，加 cross-ref 到 F1 producer-side fix 與 F2 binary-split isolation）。**Workload**: E1-F3 30min IMPL + 15min E2 review + 15min E4 regression = ~1h 完成；**Schedule**: Sprint N+1 W5 backlog（11 個 P1/P2 ticket 已並行排，F3 是第 12 個 trivial low-risk ticket）。

**F4** = `loop_exchange.rs` 加新分支 `OrderUpdate(status="Filled")` + engine 端 `cum_filled_qty < qty * 0.999` 觸發 **殘量 reconcile**（補一次 `apply_confirmed_fill` 補殘量 + emit `emit_fill_completion_lineage` 補 spine ER）。**PA 拍板採 Option (a) refined = E1 RCA Option A**（Bybit 認 Filled 為 authoritative trigger + 殘量補一次 + idempotency 用 `state.pending_orders.remove` 自然 guard，**不**改 fully_filled gate 0.999 語意、**不**改 epsilon、**不**降到 by-design noise）。**Workload**: E1-F4 1h IMPL + 30min E2 review + 30min E4 regression + 30min manual demo Bybit verify = ~2.5h 完成；**Schedule**: Sprint N+1 W5（與 F3 同 wave，獨立 ticket 並行）。

**跨 wave 0 衝突**：F3+F4 vs W1/W2/W3/W4/W5/W6/W7 全 9 wave 0 file 重疊（grep verify）。

**Deploy 順序**：**F3 + F4 同次 deploy** 建議（合併 1 次 `restart_all --rebuild` 降 ops 成本；E1-F3/E1-F4 兩 sub-agent 並行 IMPL，2.5h 收口）。可拆 2 次 deploy 但無實質好處。

**Risk**：F3 = **TRIVIAL**（0 業務語意變動，純 log message + level）；F4 = **MEDIUM**（觸 reconciliation 邏輯，可能改 fill attribution rate、需要對 W-C Caveat 2 fully_filled spine emit 路徑 align 確認）。

**MAG-085 sign-off**：F3+F4 同次 deploy + 24h verify 後合併 W-E wave closure sign-off（per `2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md` §8.2 建議的 W-E-T4/T5/T6）。

---

## §1 背景 + 為什麼 F3/F4 是「writer-side defense」而非 producer-side fix

### §1.1 F1+F2 已 closed（2026-05-11 earlier）

P1-RCA-1 4-bug chain：
- **F1 (P0)** IPC close path entry_context_id fallback chain — `commands.rs` ~15 LOC closed
- **F2 (P0)** batch_insert binary-split bad-row isolation — `batch_insert.rs` ~50 LOC closed
- **B1 Option B** 隔壁 5/11 commit `d4867676` — V083 producer-side fix（writer 端 fail-soft / synthetic id closed）
- **W2 IMPL chain** FULL CLOSURE `a771226d` + Option A-Lite Wave 1 `ebbcc038` 0 衝突 deploy

**F3 + F4 是剩餘 writer 端永久防線**：

| Fix | 改的層 | 預防 | 為何 N+1 不阻 emergency |
|---|---|---|---|
| F3 | Writer 端 log alert (`trading_writer.rs:406-414`) | F1 fallback chain 失效時 ops 能立即看到 ERROR 而非 WARN | 純 log，不影響業務語意 |
| F4 | Writer/event-consumer 邊界 (`loop_exchange.rs` OrderUpdate `Filled`) | PostOnly partial fill 0.96552/2.9=0.9991 vs Bybit Filled gate epsilon mismatch → ER 不 emit | 不阻當前流量；6 orphan 案例已 occurred 但 occurrence rate 低 |

### §1.2 P1-RCA-1 §5 既有草案 vs 本 plan 加深

PA F1+F2 emergency fix plan `2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md:359-468` 已預草 §5 F3/F4 spec。本 plan **不重寫**草案，只做 4 件深化：

1. **F4 option 拍板**（task 要求 (a)/(b)/(c) 三選一 → PA 拍 Option (a) refined）
2. **F3/F4 跨所有 9 wave 衝突 verify**（草案只 verify F1+F2 vs 3 wave，未 verify F3/F4 vs 全部）
3. **Workload 精確化 + idempotency 設計細節**（草案用 `bybit_reconcile_done` flag 加新 struct field，本 plan 改用 `state.pending_orders.remove` post-emit 自然 idempotent，**0 struct field 改動**）
4. **Schedule 落到 N+1 W5 具體位置 + Deploy 順序建議**（草案只說「T+1d / T+2d」未對齊 Sprint N+1 W### structure）

---

## §2 F3 完整 Spec

### §2.1 改動範圍 + Workload

**File**: `rust/openclaw_engine/src/database/trading_writer.rs:406-414`（line range Read verify 9463f778 HEAD）

**Workload**: ~10 LOC（純文案 + log level + import `tracing::error!` 已存在）+ 1 unit test（mock 觸發 logged ERROR target）

**Sub-agent**: E1-F3 單派 30min IMPL；E2-F3 read-only review 15min；E4-F3 cargo test regression 15min。**Total**: ~1h workload。

### §2.2 改動代碼 spec

**BEFORE** (line 406-414):

```rust
warn!(
    target: "fill-writer-entry-context-missing",
    close_fills_missing_entry_ctx = missing_entry_ctx,
    batch_total = buf.len(),
    sample = ?sample,
    "W-AUDIT-4b-M2: close fills with empty entry_context_id detected — \
     rows still INSERT (fail-soft); cron backfill will reconcile / \
     偵測到 close fill 缺 entry_context_id — 仍寫入並由 cron 回填補齊"
);
```

**AFTER F3**:

```rust
error!(
    target: "fill-writer-entry-context-missing",
    close_fills_missing_entry_ctx = missing_entry_ctx,
    batch_total = buf.len(),
    sample = ?sample,
    "F3 (N+1 W5, 2026-05-1X): close fills with empty entry_context_id detected. \
     V083 CHECK constraint will REJECT this chunk; F2 binary-split will isolate \
     bad rows (counted at trading_writer.batch_insert.bad_rows). Producer-side \
     defense lives in F1 (commands.rs IPC close fallback chain) + B1 \
     (d4867676 writer fail-soft synthetic id). If this fires after N+1 deploy, \
     either F1 regressed or new producer path bypassed entry_context_id wiring. \
     Cron backfill CANNOT reconcile a CHECK-rejected row. / \
     偵測到 close fill 缺 entry_context_id。V083 CHECK 將拒此 chunk；F2 binary-split \
     會隔離 bad row（記入 trading_writer.batch_insert.bad_rows counter）。 \
     producer 端防線：F1（commands.rs IPC close fallback chain）+ B1（d4867676 \
     writer fail-soft synthetic id）。若 N+1 deploy 後仍觸發 → F1 退化或新 producer \
     path 漏接線。cron 無法補救被 CHECK 拒絕的 row。"
);
```

### §2.3 Acceptance Criteria（必須 4/4 PASS）

| # | Acceptance | Verify 方法 |
|---|---|---|
| AC-F3-1 | log level = ERROR（不再 WARN）；下游 alert SQL 可 grep `level=ERROR target="fill-writer-entry-context-missing"` | `cargo test trading_writer::tests::test_entry_ctx_missing_logs_error` + 部署後 grep `engine_logs/*.log` |
| AC-F3-2 | 文案準確：不再含「rows still INSERT」「fail-soft」「cron backfill will reconcile」誤導字樣 | code review grep |
| AC-F3-3 | grep target name `fill-writer-entry-context-missing` **保持不變**（下游 alert SQL/log aggregator 已 hard-code 此 target，破壞 = 破 alert chain） | E2 必 verify target str 一致 |
| AC-F3-4 | cargo test trading_writer baseline 不退化（既有 N 個 test 全 PASS） | E4 regression |

### §2.4 E2 重點 review 3 點

1. **ERROR vs WARN level 邊界**：本案應該 ERROR（V083 violation = producer bug + data loss potential = user-visible alert），WARN 只適合 dev observation。
2. **不破 grep target string**：`fill-writer-entry-context-missing` 字面值是 contract（外部 alert SQL 依賴），不可隨意 rename。
3. **`tracing::error!` macro 與 `tracing::warn!` 相同 API（無 import 差異）**，但 trading_writer.rs 頂部須確保 `use tracing::{error, warn, info};` 已含 `error`。grep verify。

### §2.5 Risk 評估

| 維度 | Risk | 說明 |
|---|---|---|
| 業務語意 | **0** | 不改任何 batch insert / fail-soft 邏輯，純文案 + level |
| Hot path | **0** | log macro 在 sampling 分支，每秒最多執行 1 次（buf.iter 後一次性 log） |
| 跨模塊 | **0** | trading_writer.rs is leaf node；no caller 受 log level 變動影響 |
| 改動風險評級 | **低** | 顯示層改動（log message + level），無邏輯改動，per profile.md 風險評級「低」定義 |

---

## §3 F4 完整 Spec — PA 拍板 Option (a) refined

### §3.1 三 option 對比 + PA verdict

Task 給 3 個修法 option：

| Option | 做法 | PA 評估 |
|---|---|---|
| **(a)** 對齊 epsilon（engine 0.999 → Bybit 0.99 / Bybit > 0.99 認 Filled）| 改 `let fully_filled = po.cum_filled_qty >= po.qty * 0.999;` → `0.99` | ❌ **PA reject** — 0.999 是現有 fully_filled gate 全 path 統一語意（W-C Caveat 2 emit_fill_completion_lineage / pending_sweep::tighten_postonly / OrderStateChange "Filled"/"PartiallyFilled" 全用此 gate）。放寬到 0.99 = 全 path 容忍 1% 殘量 = 模糊「Bybit 已 Filled」vs「engine 端 cum 接近 Filled」邊界 = 增大下游 attribution 噪音 |
| **(b)** OrderUpdate(Filled) 強制 trigger emit_fill_completion_lineage 不問內部 gate | OrderUpdate 報 Filled 一律 emit ER，忽略 cum_filled_qty | ❌ **PA reject** — 跳過 fully_filled gate 等於跳過 W-C Caveat 2 設計的 partial-fill protection（PA §1.3 / §2.3 by-design：partial fill 不 emit ER）。可能在 Bybit WS 順序錯亂下重複 emit ER |
| **(c)** 殘量 reconcile：差量 < 1 tick 視同完成 | 純內部 tolerance：`po.qty - po.cum_filled_qty < instrument.qty_step` 視同 fully_filled | ⚠️ **PA partial accept** — 數學正確但缺乏「Bybit 已 Filled」這個 authoritative 信號。Bybit dust round-up 可能比 1 tick 大；單靠 internal tolerance 無法判別 「真 partial（未完成）vs 真 Filled（Bybit dust）」 |

**PA 拍板**：**Option (a) refined = E1 RCA Option A** — 用 `OrderUpdate(status="Filled")` 為 authoritative trigger，殘量補一次 `apply_confirmed_fill` + emit ER，**保留 0.999 gate 語意不變**。

### §3.2 拍板理由（4 點）

1. **「交易所即真實」原則**（CLAUDE.md §二 原則 9 災難保護衍生）：Bybit 端 `order_status=Filled` 是 authoritative truth。engine 端 0.999 gate 是 internal accounting；當兩者衝突，**信 Bybit** 是 conservative path。
2. **不放寬 fully_filled gate 語意**：0.999 在 OrderStateChange Filled vs PartiallyFilled 分流、pending_sweep tighten_postonly 都用同一閾值。F4 不應為了解 6 orphan case 而推倒全 path 統一假設。
3. **idempotency 用 `pending_orders.remove` 自然 guard**：原 PA §5.2 草案加 `bybit_reconcile_done: bool` struct field 屬於 over-engineering。F4 在 `state.pending_orders.remove(&order.order_link_id)` 後同 order_link_id 不會再進此分支 → 自然 idempotent。**0 PendingOrder struct field 改動**。
4. **與 W-C Caveat 2 fully_filled spine emit 路徑對齊**：F4 也呼叫 `emit_fill_completion_lineage`，stub_report_id 在 F4 path 標記 `:bybit_reconcile` suffix（reviewer audit 可區分）。Spine writer 端不需改 schema，純 stub_report_id 字面差異。

### §3.3 改動範圍 + Workload

**File**: `rust/openclaw_engine/src/event_consumer/loop_exchange.rs`

**Insert 位置**: line ~365-460 `OrderUpdate(order)` 分支內，現有 `if status == "Cancelled" || status == "Rejected" || status == "Deactivated"` 條件區塊之外加新分支 `else if status == "Filled"`（line ~459 附近、`state.pending_orders.remove` 之前）。

**Workload**: ~40-50 LOC（新分支 IMPL）+ 2 unit test（mock OrderUpdate Filled with cum < gate / 已 fully_filled 不 double-emit）+ 1 manual demo Bybit verify。

**Sub-agent**: E1-F4 1h IMPL；E2-F4 read-only review 30min；E4-F4 cargo test regression 30min；E5-F4 manual demo Bybit verify 30min（觸發實際 PostOnly partial fill 觀察）。**Total**: ~2.5h workload。

### §3.4 改動代碼 spec（精煉版）

在 `loop_exchange.rs` `Some(ExchangeEvent::OrderUpdate(order))` 分支內，**現有** terminal-status (Cancelled/Rejected/Deactivated) handling 之**外**加新 branch：

```rust
// 既有：terminal cancel/reject 處理（line ~365-458）
if !order.order_link_id.is_empty() {
    if state.pending_orders.get_mut(&order.order_link_id).is_some() {
        let status = &order.order_status;
        // ... 既有 log
        if status == "Cancelled" || status == "Rejected" || status == "Deactivated" {
            // ... 既有 terminal handling（保留不變）
            state.pending_orders.remove(&order.order_link_id);
        } else if status == "Filled" {
            // ─────────────────────────────────────────────────────
            // F4（2026-05-1X）：PostOnly partial vs Bybit Filled 殘量 reconciliation
            //
            // 背景：6 orphan ER missing 案例（P1-RCA-1 §3.4）— PostOnly entry
            // cum_filled_qty = 0.96552 / qty = 2.9 → ratio = 0.999067 PASS Bybit
            // 端 Filled（Bybit dust round-up）但 engine 端 cum_filled_qty < qty *
            // 0.999 → fully_filled gate 不過 → emit_fill_completion_lineage 從
            // 未觸發 → spine ER 缺失。
            //
            // F4 PA verdict：保留 0.999 gate 語意不變，用 Bybit OrderUpdate
            // (status=Filled) 為 authoritative trigger 補殘量。
            //
            // 設計考量：
            // 1. trigger 條件：status=Filled + PendingOrder 存在 + cum_filled_qty
            //    < qty * 0.999（engine 端尚未自然 fully_filled）
            // 2. 殘量 residual_qty = qty - cum_filled_qty
            // 3. residual_price = po.avg_fill_price（若已有 partial fill）
            //    或 Bybit OrderUpdate.price.parse()（若完全沒成交過 — 罕見邊界）
            // 4. idempotency：post-reconcile 立即 state.pending_orders.remove(
            //    &order.order_link_id) → 同 order_link_id 不再進此分支
            // 5. ER stub_report_id 標 `:bybit_reconcile` suffix 供 reviewer 區分
            // ─────────────────────────────────────────────────────
            let po_snapshot_opt = state.pending_orders.get(&order.order_link_id).cloned();
            if let Some(po) = po_snapshot_opt {
                let fully_filled_engine = po.cum_filled_qty >= po.qty * 0.999;
                if !fully_filled_engine && po.qty > 0.0 {
                    let residual_qty = po.qty - po.cum_filled_qty;
                    let residual_price = if po.cum_filled_qty > 0.0 {
                        // 已有 partial fill：用既有 avg as proxy（Bybit dust 通常
                        // 在 avg±tick_size 範圍內，精確度足夠 attribution）
                        // 注意：PendingOrder 沒有 avg_fill_price 欄位；改用 OrderUpdate.price
                        order.price.parse::<f64>().unwrap_or(0.0)
                    } else {
                        // 完全沒成交過（罕見）：用 OrderUpdate.price（Bybit 提供）
                        order.price.parse::<f64>().unwrap_or(0.0)
                    };
                    let exec_ts = openclaw_core::now_ms();

                    if residual_price > 0.0 {
                        // 補一次 apply_confirmed_fill 把殘量結清 paper_state
                        pipeline.apply_confirmed_fill(
                            &po.symbol,
                            po.is_long,
                            residual_qty,
                            residual_price,
                            0.0,        // fee = 0（Bybit dust 通常 0 fee；fee_rate Some(0)）
                            exec_ts,
                            &po.strategy,
                            &po.context_id,
                            &po.order_link_id,
                            Some(0.0),  // fee_rate_override
                            po.reference_price,
                            po.reference_ts_ms,
                            po.reference_source.as_deref(),
                            None,       // slippage_bps = None（dust 不算 slippage）
                            Some("maker"),  // liquidity_role = maker（PostOnly path）
                            None,       // fill_latency_ms
                            Some(&format!("bybit-reconcile-{}", po.order_link_id)),
                        );
                        snapshot_writer.force_write(&pipeline.snapshot());

                        // emit OrderStateChange Filled（補 PartiallyFilled→Filled lifecycle row）
                        if let Some(tx) = order_tx {
                            let em = pipeline.effective_engine_mode().to_string();
                            let _ = crate::database::try_send_trading_msg(
                                tx,
                                crate::database::TradingMsg::OrderStateChange {
                                    order_id: po.order_link_id.clone(),
                                    ts_ms: exec_ts,
                                    from_status: Some("PartiallyFilled".into()),
                                    to_status: "Filled".into(),
                                    filled_qty: Some(po.qty),  // full qty after reconcile
                                    avg_price: Some(residual_price),
                                    reason: Some(format!(
                                        "f4_bybit_reconcile: engine_cum={} bybit_filled \
                                         residual={:.6} (W-AUDIT-4b post-RCA P1-RCA-1 F4)",
                                        po.cum_filled_qty, residual_qty,
                                    )),
                                    engine_mode: em,
                                },
                                "order_state_f4_reconcile",
                            );
                        }

                        // emit spine ER（W-C Caveat 2 fully_filled path 同 pattern）
                        if let (Some(plan_id), Some(decision_id), Some(stub_id)) = (
                            po.spine_order_plan_id.as_deref(),
                            po.spine_decision_id.as_deref(),
                            po.spine_stub_report_id.as_deref(),
                        ) {
                            let em_str = pipeline.effective_engine_mode().to_string();
                            // stub_report_id 加 `:bybit_reconcile` suffix 供 reviewer audit
                            let reconcile_stub_id = format!("{}:bybit_reconcile", stub_id);
                            crate::agent_spine::runtime_shadow::emit_fill_completion_lineage(
                                pipeline.agent_spine_tx_ref(),
                                pipeline.agent_spine_mode_ref(),
                                crate::agent_spine::runtime_shadow::FillCompletionLineageInput {
                                    order_plan_id: plan_id,
                                    decision_id,
                                    symbol: &po.symbol,
                                    engine_mode: em_str.as_str(),
                                    strategy: &po.strategy,
                                    ts_ms: exec_ts,
                                    filled_qty: po.qty,
                                    avg_fill_price: residual_price,
                                    fees_paid: 0.0,
                                    fee_bps: Some(0.0),
                                    slippage_bps: None,
                                    liquidity_role: Some("maker"),
                                    fill_latency_ms: None,
                                    exchange_exec_id: &format!(
                                        "bybit-reconcile-{}", po.order_link_id
                                    ),
                                    stub_report_id: reconcile_stub_id.as_str(),
                                    order_link_id: Some(po.order_link_id.as_str()),
                                },
                            );
                        }

                        tracing::warn!(
                            order_link_id = %order.order_link_id,
                            symbol = %po.symbol,
                            engine_cum = po.cum_filled_qty,
                            bybit_qty = po.qty,
                            residual_qty = residual_qty,
                            residual_price = residual_price,
                            "F4: Bybit reports Filled but engine cum < qty * 0.999 — \
                             reconciled residual + emitted spine ER / \
                             F4: Bybit 報 Filled 但 engine 端 < 0.999 — 已補殘量 + emit spine ER"
                        );
                    } else {
                        // residual_price 無法解析 — log only，不寫殘量
                        tracing::error!(
                            order_link_id = %order.order_link_id,
                            symbol = %po.symbol,
                            engine_cum = po.cum_filled_qty,
                            bybit_qty = po.qty,
                            bybit_price = %order.price,
                            "F4: Bybit reports Filled with unparseable price — \
                             cannot reconcile residual / Bybit 報 Filled 但 price 無法解析"
                        );
                    }

                    // Idempotency: post-reconcile 立即移除 pending order
                    state.pending_orders.remove(&order.order_link_id);
                }
                // 若 fully_filled_engine = true → 既有 ExecutionUpdate path 已處理
                // emit + remove，此分支 no-op skip
            }
        }
    }
}
```

**LOC 估計**：~50-60 LOC（含中英注釋 ~25 LOC + 邏輯 ~25-35 LOC）。

### §3.5 Acceptance Criteria（必須 6/6 PASS）

| # | Acceptance | Verify 方法 |
|---|---|---|
| AC-F4-1 | mock OrderUpdate(status="Filled") + PendingOrder cum_filled_qty=0.96552/qty=2.9 → 觸發 reconcile path：apply_confirmed_fill 被呼叫一次補殘量 + emit OrderStateChange Filled + emit spine ER（stub_report_id 含 `:bybit_reconcile` suffix）| `cargo test event_consumer::loop_exchange::tests::test_f4_postonly_residual_reconcile` |
| AC-F4-2 | double-emit 防護：同 order_link_id 第二次 OrderUpdate Filled → pending_orders.get 回 None → 不再進 reconcile branch（idempotent）| `cargo test ...::test_f4_idempotent_after_remove` |
| AC-F4-3 | 不破現有 fully_filled path：ExecutionUpdate(Fill) 完整成交至 cum >= 0.999 → 走原 line 200-307 path，F4 分支 fully_filled_engine=true → no-op skip | `cargo test ...::test_f4_skip_when_already_fully_filled` |
| AC-F4-4 | residual_price=0（unparseable）→ tracing::error! log 但不寫殘量、不 remove pending_order（讓 timeout sweep 處理）| 同 mock 測試含 invalid price branch |
| AC-F4-5 | manual demo Bybit verify：實際 PostOnly entry partial fill → F4 path 觸發 → trading.fills 新增殘量 row + spine ER count +1 + healthcheck `[55] agent_decision_spine_lineage` chains_with_real_fill 增加 | Linux demo runtime 觀察 30min + SQL count diff |
| AC-F4-6 | cargo test event_consumer + agent_spine + tick_pipeline baseline 不退化 | E4 regression full run |

### §3.6 E2 重點 review 3 點

1. **idempotency 自然 guard 而非 flag**：原 PA §5.2 草案加 `bybit_reconcile_done: bool` struct field 是 over-engineering。F4 用 `state.pending_orders.remove(&order.order_link_id)` post-reconcile 自然 idempotent。E2 必 verify：(a) remove 在 reconcile 完成 **後** 才呼叫；(b) 同 order_link_id 第二次 OrderUpdate 進來 `get` 回 None → skip；(c) 若 ExecutionUpdate(Fill) 與 OrderUpdate(Filled) race 同時到，順序保證來自單一 event loop（loop_exchange.rs:135 channel 序列化）。

2. **stub_report_id `:bybit_reconcile` suffix 不破 spine writer schema**：spine ER table `agent.execution_reports` 的 `execution_report_id` 是 TEXT，無 unique constraint on stub_id 字面，加 suffix 不破 INSERT。但 reviewer audit pack cross-ref 需更新 `[55] healthcheck` query 認識此後綴（**E1-F4 必順帶補 healthcheck script `passive_wait_healthcheck.py` 的 `[55]` 查詢加註此 suffix 為 valid real-fill chain**）。

3. **W-C Caveat 2 alignment**：F4 path 也呼叫 `emit_fill_completion_lineage`，且 4 個 spine id（plan/decision/verdict/stub）依賴 emit_entry_lineage 在 step_4_5_dispatch.rs 已注入。E2 必 verify：F4 reconcile path 的 PendingOrder 來自 `pending_orders.get(&order.order_link_id).cloned()`，cloned PendingOrder 的 4 個 spine_* Option fields 維持 emit_entry_lineage 時注入的值（不是 None / 不是新 generate）。若 4 fields 都 Some → emit ER；若任一 None → skip emit（與 fully_filled path 行為一致 `if let (Some, Some, Some) = (..., ..., ...)`），fail-soft。

### §3.7 Risk 評估

| 維度 | Risk | 說明 |
|---|---|---|
| 業務語意 | **中** | 觸 reconciliation 邏輯（殘量補一次 fill）。改的是 fill attribution 路徑（雖然殘量 < 0.1% qty）。可能影響 healthcheck [40] avg_net_bps 統計 ±0.1 bps（殘量補入 fills 表，下游 attribution writer 把 dust 算入 strategy edge） |
| Hot path | **低** | 觸發頻率低（每 6 orphan / N month），不在 hot path 主迴圈 |
| 跨模塊 | **中** | 影響 trading.fills + agent.execution_reports + agent.execution_plans + trading.order_state_changes 4 表寫入。healthcheck [55] `agent_decision_spine_lineage` 的 chains_with_real_fill count 會緩慢上升（符合 W-C Caveat 2 設計） |
| 改動風險評級 | **中** | per profile.md 風險評級「中」定義「改邏輯但有完整測試覆蓋的模塊」。F4 必須加 3 unit test（AC-F4-1/2/3）+ 1 manual demo verify |

**MAG-082 Caveat 2 SoT 對齊**：F4 reconcile 會增加 chains_with_real_fill count（per `[55]` healthcheck），這是 desired behavior（補回原本 missed 的 ER）。不會破 chains_with_real_fill / chains_total ratio gate；只會把 ratio 從目前低值往上推。

---

## §4 F3+F4 跨 Wave 衝突檢查

### §4.1 vs Sprint N+1 W1-W7 active wave

| Wave | 名稱 | 改動 file 範圍 | F3 衝突 | F4 衝突 | 結論 |
|---|---|---|---|---|---|
| **W1** | W-AUDIT-8a Phase B Tier 2 panel collector（Rust panel_aggregator WS-first） | `rust/openclaw_engine/src/panel_aggregator/*.rs` + 新 panel collector | ✗ 不撞 `trading_writer.rs` | ✗ 不撞 `loop_exchange.rs` | **0 衝突** |
| **W2** | A4-C BTC→Alt Lead-Lag spec + paper IMPL | `rust/openclaw_engine/src/strategies/btc_alt_lead_lag.rs`（新）+ Python writer + new SQL V088 | ✗ | ✗ | **0 衝突** |
| **W3** | W-AUDIT-9 Stage 1 cohort observation | `governance/canary_stage_log.rs` + observability only | ✗ | ✗ | **0 衝突** |
| **W4** | W-AUDIT-3b runtime smoke（RouterLeaseGuard Drop）| `rust/openclaw_engine/src/routing/lease_guard.rs` + test only | ✗ | ✗ | **0 衝突** |
| **W5** | 11 P1/P2 backlog（混合）| 分散 per-ticket | ✗（F3 加入此 wave 為第 12 ticket）| ✗（F4 加入此 wave 為第 13 ticket）| **0 衝突 + F3+F4 加入 W5** |
| **W6** | Reject Reason Metadata + ML Imbalance Handling（V086 schema）| `learning.decision_features` ALTER + Rust ML pipeline + Python writer | ✗（F3 不動 learning namespace）| ✗（F4 寫 trading.fills + agent.* 非 learning） | **0 衝突** |
| **W7** | STRATEGY-POSITION-SYNC（TickContext + 5 strategy signature）| `rust/openclaw_engine/src/strategies/{ma_crossover,grid_trading,bb_breakout,bb_reversion,funding_arb}/*.rs` + `tick_pipeline/*.rs` | ✗（F3 純 writer log）| ✗（F4 在 event_consumer/loop_exchange.rs，與 tick_pipeline 不同模塊）| **0 衝突** |

**全 wave verdict**: F3 + F4 vs Sprint N+1 W1-W7 全 9 wave **0 file 重疊**。可獨立 schedule 不必排序。

### §4.2 vs 隔壁已 land producer-side fix（5/11 B1 Option B `d4867676` + W2 IMPL chain `a771226d` + Option A-Lite Wave 1 `ebbcc038`）

| Commit | 改的 file | F3 衝突 | F4 衝突 | 結論 |
|---|---|---|---|---|
| `d4867676`（B1 Option B producer-side V083 fix）| `rust/openclaw_engine/src/database/{batch_insert,trading_writer}.rs` + V083 producer hook | F3 改 `trading_writer.rs:406-414` 是 `d4867676` **之外**的 line range（line 406-414 vs B1 改 V083 producer code path） | ✗ F4 不動 batch_insert / trading_writer | **0 衝突**（F3 line range 與 B1 互補不重疊；F3 PA 已 grep verify line 406-414 在 9463f778 HEAD 上未被 B1 改動） |
| `a771226d`（W2 IMPL chain FULL CLOSURE）| W2 strategy + Python writer + SQL | ✗ | ✗ | **0 衝突** |
| `ebbcc038`（Option A-Lite Wave 1 funding_arb dormant）| `risk_config*.toml` + funding_arb dormant flag | ✗ | ✗ | **0 衝突** |

### §4.3 vs V091 ALTER VALIDATE（decision_features schema）

| 比對軸 | F3 | F4 | V091 | 結論 |
|---|---|---|---|---|
| Schema scope | F3 不寫 V### migration | F4 不寫 V### migration | V091 `learning.decision_features.reject_reason_code` + `close_reason_code` row-level CHECK NOT VALID → VALIDATE | **0 schema 衝突**（V091 動 learning namespace，F3/F4 動 trading + agent namespace） |
| Migration order | N/A | N/A | V091 ALTER VALIDATE 後 deploy | **F3+F4 deploy 與 V091 ALTER VALIDATE 無 sequencing 要求** |

### §4.4 vs MAG-085 future sign-off

per `2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md` §8.2 建議的 W-E wave structure：
- W-E-T1/T2/T3 = F1+F2 emergency（已 closed）
- W-E-T4 = F3（本 plan schedule）
- W-E-T5 = F4（本 plan schedule）
- W-E-T6 = MAG-085 sign-off（W-E closure + 24h verify）

**MAG-085 sign-off** 等待 F3+F4 同次 deploy + 24h passive verify 後合併 W-E wave closure（屬 N+1 W5 後續 ops）。

---

## §5 Schedule — Sprint N+1 W5 推薦插入位置

### §5.1 為何選 W5

per `2026-05-10--sprint_n1_dispatch_draft.md` §2 Wave 結構：W5 = **11 P1/P2 ticket backlog**，性質「mixed」「per-ticket dependency」「完全並行」。F3+F4 性質完全符合：
- F3 = 1 ticket P1 trivial 30min；屬 W5 backlog 第 12 個 ticket
- F4 = 1 ticket P1 medium 1h；屬 W5 backlog 第 13 個 ticket
- 與 W5 既有 11 ticket（V089/V090 等 spec predraft `2026-05-10--w5_three_p1_specs_predraft.md`）無 file 重疊

### §5.2 推薦 Schedule（D = Sprint N+1 day index）

| Day | 動作 | Owner |
|---|---|---|
| D+0 (operator sign-off 後) | 派 W7-2 / W7-4 / W7-5 / W6 RFC verdict / W6 V086 IMPL / W1 IMPL / W2 IMPL / W3 等 W6+W7 / W4 RouterLeaseGuard Drop test / W5 三 P1 IMPL 並行；**F3+F4 不在首日 wave 內**（W5 backlog 第 12/13 ticket）| PM |
| D+2 ~ D+3（W5 backlog cycle）| 派 E1-F3 + E1-F4 並行（兩 sub-agent，2.5h workload）| PM |
| D+2 末 | F3 + F4 push 完成 → 派 E2-F3 + E2-F4 read-only review + E4-F3 + E4-F4 cargo test regression（並行 ~1h） | PM |
| D+2 末（review GREEN gate 後）| PM 整 sign-off pack；ssh trade-core git pull + restart_all --rebuild --keep-auth；30min deploy verify | PM (operator approve) |
| D+3 ~ D+4（24h passive verify）| healthcheck [55] chains_with_real_fill +N / [40] avg_net stable / V083 violation 0 alarm 持續 | passive |
| D+4 | MAG-085 sign-off（W-E wave closure）| PM |

### §5.3 不在 D+0 / D+1 deploy 的理由

D+0 已派 9 wave 並行（W1-W7 + W7-2/4/5 + W6 RFC verdict + W6 V086 + W4 + W5 三 P1）。F3+F4 加入 D+0 會：
1. 增 ops 負擔（restart_all --rebuild 已在 D+0 同次 deploy 6 個 PR ready commit）
2. F4 medium risk 需 manual demo Bybit verify 30min，D+0 sign-off 窗口擠
3. F4 改 fill attribution，可能影響 D+0 deploy 後立即觀察的 [40] avg_net 數字（污染 D+0 deploy baseline 對比）

**推薦** D+2 ~ D+3 cycle（W5 backlog 自然窗口）排 F3+F4，與 W5 其他 P1/P2 ticket 同 wave deploy。

---

## §6 Deploy 順序建議

### §6.1 PA 建議：F3 + F4 同次 deploy（單一 `restart_all --rebuild --keep-auth`）

**理由**：

1. **降 ops 成本**：F3 (~10 LOC) + F4 (~50-60 LOC) 合計 70 LOC，2 個 file 改動，1 次 `restart_all --rebuild` 就能 deploy。拆 2 次 deploy 增加 2 次 engine restart 風險（restart cascade 已是 P1-RCA-1 場景之一，per E1 RCA O1 觀察「3 次 restart in 22min」）。

2. **W-E wave closure semantic**：W-E wave 設計上是「F1+F2+F3+F4 一連串 producer + writer 防線」，整 wave closure sign-off 自然對應「全部 deploy + 24h verify PASS」。F3/F4 拆 2 次 deploy 會延長 W-E wave open 時間。

3. **F3 + F4 互相無依賴**：F3 改 `trading_writer.rs`，F4 改 `event_consumer/loop_exchange.rs`，2 file 0 重疊；E1-F3 + E1-F4 可完全並行 IMPL；deploy 順序無 sequencing constraint。

### §6.2 替代：F3 先 deploy / F4 後 deploy（**不推薦**）

僅在以下情況考慮拆 2 次 deploy：
- F4 在 D+2 IMPL 撞硬阻塞無法 D+3 deploy → F3 可先單獨 deploy（30min IMPL + 15min review + 15min regression + 15min deploy + 15min verify = 1.5h cycle）
- operator 明確要求 risk-isolation（F3 trivial 先 land 觀察 24h 再做 F4）→ 增 1 cycle ops 成本但 risk-isolated

**正常情況 = 一次 deploy**。

### §6.3 Deploy verify checklist（同次部署後 30min）

| Check | Pass criteria |
|---|---|
| engine restart 成功 | `ssh trade-core systemctl status openclaw-engine`（PID 新 + active） |
| F3 ERROR log target 可觀察 | `grep 'ERROR.*fill-writer-entry-context-missing' /tmp/openclaw/engine_logs/*.log`（若無觸發 = OK；若觸發 = F1 退化 alert） |
| F4 reconcile path 不誤觸 | `grep 'F4: Bybit reports Filled but engine cum < qty' /tmp/openclaw/engine_logs/*.log`（首日 < 10 次屬正常邊界；> 50 次 = F4 over-trigger 需 review） |
| trading.fills row count 趨勢 | 30min 內 row count 變化與部署前 trend 一致（F4 reconcile 補殘量 row 屬於既有 fill 表，不應大幅推高 count） |
| healthcheck [55] chains_with_real_fill | 部署後 24h chains_with_real_fill 增加 ≥1（F4 補回原本 missed 的 ER）；ratio chains_with_real_fill / chains_total 不下降 |
| healthcheck [40] avg_net_bps | 24h avg_net_bps 不下降 > 1bps（F4 reconcile dust 殘量補入 attribution，淨影響應 ≤ ±0.1 bps）|

---

## §7 Risk 評估總表

| Fix | Risk Level | 風險點 | Mitigation |
|---|---|---|---|
| **F3** | **TRIVIAL（低）**| 0 業務語意改動；極低概率：grep target string 被 rename 破壞下游 alert SQL | AC-F3-3 要求 target string 不變；E2 必 verify |
| **F4** | **MEDIUM（中）**| (1) reconciliation 邏輯觸 fill attribution rate，per MAG-082 Caveat 2 SoT；(2) 殘量 dust 補入 attribution 可能微幅推 healthcheck [40] avg_net 統計；(3) double-emit risk（已用 pending_orders.remove 自然 guard） | (1) AC-F4-5 manual demo verify + 24h passive watch [40]/[55]；(2) F4 reconcile dust 微小（< 0.1% qty），淨 attribution 影響 ≤ ±0.1 bps；(3) AC-F4-2 idempotent test verify |

### §7.1 16 原則 + DOC-08 §12 + 硬邊界 5 項 compliance check

| 原則/不變量/硬邊界 | F3 影響 | F4 影響 |
|---|---|---|
| 1 單一寫入口 | ✓ 不動 IntentProcessor / submit_intent | ✓ 不動寫入口；F4 補 fill 經 apply_confirmed_fill 走既有寫入路徑 |
| 3 AI ≠ 命令 | ✓ 不動 Decision Lease | ✓ 不動 lease |
| 4 不繞風控 | ✓ 不動 Guardian | ✓ 不動 risk_envelope（F4 補殘量 dust 不觸 risk check） |
| 5 生存 > 利潤 | ✓ ERROR alert 強化 ops 可見性 | ✓ F4 補殘量讓 attribution 正確 = 強化 |
| 6 失敗默認收縮 | ✓ 純 log | ✓ residual_price=0 unparseable → fail-soft（log 不寫殘量、不 remove pending） |
| 7 學習 ≠ 改寫 Live | ✓ | ✓ F4 stub_report_id `:bybit_reconcile` suffix 下游 ML training 可識別 |
| 8 交易可解釋 | ✓ 強化（ERROR 提供更明確 alert）| ✓ F4 reconcile row 寫 reason field `f4_bybit_reconcile: engine_cum=... bybit_filled residual=... (W-AUDIT-4b post-RCA P1-RCA-1 F4)` 可追溯 |
| 9 災難保護 | ✓ | ✓ F4 信 Bybit authoritative 是 conservative |
| 11 Agent 自主 | ✓ 不破硬邊界 | ✓ |
| 12 持續進化 | ✓ ERROR log 為 schema drift signal | ✓ F4 healthcheck [55] count 上升提供 W-C Caveat 2 SoT 改進 |
| DOC-08 §12 安全不變量 9 條 | ✓ 0 觸碰 | ✓ 0 觸碰 |
| 硬邊界 5 項（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / decision_lease_emitted / authorization.json）| ✓ 0 觸碰 | ✓ 0 觸碰 |

**Verdict**: F3+F4 屬 **A 級** compliance — 強化原則 5/6/8/12，零硬邊界觸碰。

---

## §8 4 並行 Sub-Agent 拆派建議

| Sub-agent | Scope | Workload | 動的 file | 並行/序列 |
|---|---|---|---|---|
| **E1-F3** | `trading_writer.rs:406-414` WARN→ERROR + 文案準確化 | 30min | `rust/openclaw_engine/src/database/trading_writer.rs`（10 LOC 改 + 1 unit test） | 完全並行（與 E1-F4 不撞檔） |
| **E1-F4** | `loop_exchange.rs` OrderUpdate(Filled) 殘量 reconcile + spine ER emit | 1h | `rust/openclaw_engine/src/event_consumer/loop_exchange.rs`（~50-60 LOC 改 + 3 unit test）+ `helper_scripts/db/passive_wait_healthcheck.py` `[55]` query 加 `:bybit_reconcile` suffix 認識（~10 LOC） | 完全並行（與 E1-F3 不撞檔） |
| **E2 對抗 review** | F3+F4 IMPL 對抗 review | 30-45min | READ-ONLY review on F3+F4 commit hash | 需等 F3+F4 push 後 |
| **E4 regression test** | cargo test trading_writer + event_consumer + agent_spine baseline 不退化 + healthcheck [55] query 仍能識別 reconcile ER | 30-45min | cargo test --release -p openclaw_engine --lib | 需等 F3+F4 push 後 |

### §8.1 Dispatch Sequence（PM 執行，D+2 W5 backlog cycle）

**T+0**：
- PM 派 E1-F3 + E1-F4 並行（兩個 sub-agent 同時開工 2.5h）

**T+1.5h ~ T+2h**（F3 + F4 push 完成後）：
- PM 派 E2 對抗 review（讀 F3+F4 commit hash）
- PM 派 E4 regression test（cargo test 全 baseline + healthcheck [55] query 驗）

**T+2.5h**（E2 + E4 GREEN gate 後 + E5 manual demo verify 30min）：
- PM 整 sign-off pack
- ssh trade-core git pull + restart_all --rebuild --keep-auth
- 30min deploy verify（F3 ERROR 不誤觸 / F4 reconcile path 不 over-fire / trading.fills row count 趨勢正常）

**T+3h**：F3+F4 deploy 完成 + verification 觀察 30min PASS → 入 24h passive watch

**T+24h**：MAG-085 sign-off（W-E wave closure）— healthcheck [55] chains_with_real_fill +N / [40] avg_net stable / V083 violation 0 alarm 全 PASS

---

## §9 7 交付物對照（task 要求）

| 交付物 | 本 plan 對應 |
|---|---|
| 1. dispatch plan commit hash + 行數 | 待 PA push 後 fill；本 plan ~XX 行（pending git diff stat） |
| 2. F3 spec acceptance criteria | §2.3 AC-F3-1 ~ AC-F3-4 共 4 條 |
| 3. F4 spec acceptance criteria + PA 拍板 option (a/b/c) | §3.5 AC-F4-1 ~ AC-F4-6 共 6 條；PA 拍板 = **Option (a) refined = E1 RCA Option A**（保留 0.999 gate + OrderUpdate(Filled) 為 authoritative trigger + 殘量補一次 + pending_orders.remove 自然 idempotent）。理由詳 §3.2 |
| 4. 跨 wave 衝突 verify | §4.1 ~ §4.4，9 active wave + 隔壁 land producer-side + V091 + MAG-085 future 全 0 衝突 |
| 5. Schedule N+1 W### 推薦 | §5.1 ~ §5.3：**W5 backlog 第 12+13 ticket**，D+2 ~ D+3 cycle，**不在 D+0 首日 deploy 窗口** |
| 6. Deploy 順序建議 | §6.1：**F3 + F4 同次 deploy**（單一 `restart_all --rebuild --keep-auth`）— 降 ops 成本 + W-E wave closure semantic + 0 sequencing constraint |
| 7. F3/F4 risk 評估 | §7：F3 = TRIVIAL（純 log）；F4 = MEDIUM（reconciliation 觸 fill attribution，已 mitigate AC-F4-5 manual demo verify + 24h passive watch） |

---

## §10 一句總結

**F3（trading_writer.rs:406-414 WARN→ERROR + 文案準確化，30min ~10 LOC + 1 unit test）+ F4（loop_exchange.rs OrderUpdate(Filled) 殘量 reconcile，1h ~50-60 LOC + 3 unit test + 1 manual demo verify）排 Sprint N+1 W5 backlog（第 12+13 ticket），D+2~D+3 cycle，2 sub-agent E1-F3 + E1-F4 並行 2.5h workload，F3+F4 同次 restart_all --rebuild --keep-auth deploy（不拆 2 次）。PA 拍板 F4 = Option (a) refined（保留 0.999 gate 語意 + Bybit OrderUpdate(Filled) 為 authoritative trigger + 殘量補 apply_confirmed_fill + emit_fill_completion_lineage with `:bybit_reconcile` stub_report_id suffix + pending_orders.remove 自然 idempotent，0 PendingOrder struct field 改動）。跨 W1-W7 全 9 wave + 隔壁 producer-side fix + V091 + MAG-085 全 0 file 衝突。F3 = TRIVIAL risk；F4 = MEDIUM risk（fill attribution rate 觸動已 AC-F4-5 manual demo verify + 24h passive watch [40]/[55] mitigate）。16 原則 + DOC-08 §12 + 硬邊界 5 項 0 觸碰，屬 A 級 compliance 強化原則 5/6/8/12。MAG-085 sign-off = D+4 W-E wave closure（F1+F2+F3+F4 整 4-bug chain）。**

---

**Report end. PA dispatch plan ready. PM 於 Sprint N+1 W5 backlog cycle（D+2~D+3）派 E1-F3 + E1-F4 並行（T+0 同時起）→ E2 對抗 + E4 regression + E5 manual demo verify（T+1.5h-2.5h）→ F3+F4 同次 restart_all --rebuild deploy（T+2.5h）→ 30min verify（T+3h）→ 24h passive watch（T+3h ~ T+27h）→ MAG-085 W-E wave closure sign-off（T+27h, D+4）。**

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--f3_f4_writer_defense_n1_dispatch_plan.md
