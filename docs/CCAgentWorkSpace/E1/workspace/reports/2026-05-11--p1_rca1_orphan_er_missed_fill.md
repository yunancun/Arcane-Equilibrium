# P1-RCA-1 — W-D MAG-083 R-1 orphan ER + missed entry fill RCA

**Date (UTC)**: 2026-05-11
**Author**: E1 (Backend Developer)
**Triggered by**: W-D MAG-083 QA audit (`388e04b2`, file `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--w_d_mag083_qa_audit.md`) R-1
**Window**: deploy_ts `2026-05-11T00:01:55+00:00` + 72-78 min (burst 01:13-01:14 UTC)
**Mode**: Read-only RCA + fix plan (no code change in this ticket)

---

## Verdict

**SYSTEMIC — fix plan required**

6 orphan ER (grid_trading, DOT/SUI/ARB/ETC × demo/live_demo, deploy+72-73min) **不是** Bybit-side noise，**也不是** trading_writer dispatch race / Bybit multi-exec event。Root cause = **V083 NOT VALID CHECK constraint 與 IPC close-fill emit path 不對齊，導致 trading_writer batch INSERT 整個 hyperchunk reject，6 個 entry fills 卡在 buffer 直到 engine restart shutdown 全丟**。

1 missed entry fill (ETCUSDT live_demo grid_trading qty=2.8/2.9) **不是** 同根因，是獨立第 4 個 bug：**PostOnly partial fill 0.999 fully_filled gate + Bybit-side Filled status reconciliation gap，導致 ER emit_fill_completion_lineage 未觸發**。

| # | Bug | 影響範圍 | Severity |
|---|---|---|---|
| **B1** | V083 NOT VALID CHECK reject 整 hyperchunk | **6 orphan ER + 所有 burst window 內 trading.fills 不寫** | P0 — 系統性 |
| **B2** | `fill-writer-entry-context-missing` WARN 文案誤導（說 "rows still INSERT (fail-soft)" 但實際 PG reject 整 chunk） | 開發者 / operator 看不到資料丟失 | P1 — 觀測性 |
| **B3** | PostOnly partial fill 0.999 gate vs Bybit Filled status 不一致 | **1 missed entry fill ER**（殘量 3.45% 不觸發 fully_filled） | P1 — 邊界 case |
| **B4** | ER status `shadow_filled` literal 在真實 demo/live_demo path 也寫，命名誤導 | reviewer 誤判 lineage 性質（與本次 RCA 無關，順手記） | P3 — 命名 |

---

## 證據鏈（從 QA report R-1 反推至 root cause）

### 1. QA report R-1 原始 finding

> **R-1**: deploy+72-73min 4-min burst window 集中 6 orphan ER (DOT/SUI/ARB/ETC × demo/live_demo, grid_trading) + 1 missed entry fill。Orphan ER 的 fill_id 在 trading.fills 找不到（含去 `bybit-` 前綴）。QA 判 non-systemic。

### 2. 6 orphan ER 細節（已驗證）

```
ER timestamp (UTC) | engine_mode | symbol  | order_id              | fill_id_uuid                              | filled_qty | role
01:13:37.288       | demo        | ETCUSDT | oc_1778462014481_5    | 1d1b1400-f03e-4239-a0ba-a7cfb4c771f7      | 9.4        | maker
01:14:04.359       | live_demo   | SUIUSDT | oc_1778462043738_11   | f9a2e70f-32a0-4658-a84e-25d5abf28b8a      | 20.0       | maker
01:14:12.034       | live_demo   | ARBUSDT | oc_1778462043528_10   | e8b55558-662e-4e33-a4bc-5ef91269285c      | 206.6      | maker
01:14:12.035       | demo        | ARBUSDT | oc_1778462043528_11   | f3f527e9-7447-44e5-a631-7e9a322072b3      | 652.1      | maker
01:14:13.638       | demo        | SUIUSDT | oc_1778462043258_10   | 60b11ae7-02d1-4777-bd84-73594eb9cb75      | 70.0       | maker
01:14:17.885       | live_demo   | DOTUSDT | oc_1778462042146_9    | 8d7f6352-d982-4d28-b600-08766cc25a57      | 21.5       | maker
```

ER metadata 全部 `status=shadow_filled` / `no_order_authority=true` / `shadow_lineage_only=true`，與 2 個 matched ER（01:16:50.719/720）metadata 完全相同 → metadata 上不能區隔 orphan vs matched。差異**只在** trading.fills 有沒有對應 row。

### 3. trading.orders + order_state_changes 證實這些 order 真實提交、真實 Filled

```
order_id                | t (UTC)    | em        | status        | filled_qty
oc_1778462014481_5      | 01:13:34   | demo      | Working       | NULL    (initial submit)
oc_1778462014481_5      | 01:13:37   | demo      | Filled        | 9.4     ← 真實 fully_filled exchange-side
oc_1778462043258_10     | 01:14:03   | demo      | Working       | NULL
oc_1778462043258_10     | 01:14:13   | demo      | Filled        | 70.0
...（共 6 個 order 全 Filled state）
```

→ engine 確實處理 fully_filled、確實呼叫 emit_fill_completion_lineage 寫 ER（line `emit_fill_completion_lineage` at `loop_exchange.rs:283`）。

### 4. trading.fills 在 burst window **完全 0 row**

```
WHERE ts >= '2026-05-11 01:13 UTC' AND ts < '2026-05-15 UTC' → 0 row
WHERE ts >= '2026-05-11 01:13 UTC' AND ts < '2026-05-11 01:17 UTC' → 0 row
```

對比 burst window 前後：
- 01:12:53.154 (last fill before burst) — `bybit-...HYPEUSDT` Filled qty=0.69
- **01:12:53 → 01:16:19 (3min 26s gap with 0 trading.fills row)**
- 01:16:19.028 (first fill after burst) — `bybit-79bdb071...ETCUSDT` qty=2.8

### 5. engine_logs/engine-1778462140.log smoking gun

該 engine instance 起 `2026-05-11T01:12:57.155 UTC`，stop `2026-05-11T01:15:40.842 UTC`（cover 整個 burst window）：

```
2026-05-11T01:13:04.488407Z WARN openclaw_engine::database::batch_insert: 
  batch_insert failed / 批量插入失敗 
  table="trading.fills" 
  error=error returned from database: 
    new row for relation "_hyper_35_422_chunk" 
    violates check constraint "chk_fills_close_has_entry_context_id_v083"

2026-05-11T01:13:04.488407Z WARN openclaw_engine::database::trading_writer: 
  trading_writer flush incomplete — retaining buffer for retry 
  table="trading.fills" pending_rows=2 rows_affected=0 failed_chunks=1
```

**該 WARN 每 2 秒 retry 一次，從 01:13:04 持續到 01:15:40 engine shutdown，全部 fail（rows_affected=0）。** 期間 6 個 entry fills (01:13:37 - 01:14:17) 加入 buffer 但同樣被同一 chunk constraint reject。Engine shutdown 時 buffer 內全部 drop（trading_writer.rs L91-106 final flush 也 fail）。

### 6. V083 constraint definition

`sql/migrations/V083__fills_entry_context_id_close_check.sql` 落地：

```sql
ALTER TABLE trading.fills ADD CONSTRAINT chk_fills_close_has_entry_context_id_v083 
    CHECK (exit_reason IS NULL OR entry_context_id IS NOT NULL) NOT VALID;
```

語意：close fill (`exit_reason IS NOT NULL`) 必須有 `entry_context_id`。NOT VALID 不掃歷史，只對 INSERT 生效。

### 7. Bad row identification

WARN log 自 0.5s 前就出來：
```
W-AUDIT-4b-M2: close fills with empty entry_context_id detected — 
rows still INSERT (fail-soft); cron backfill will reconcile
close_fills_missing_entry_ctx=2 batch_total=2 
sample=Some("fill_id=bybit-0ca53225-77dc-47d4-9195-b52fd2a576f6 
            symbol=HYPEUSDT strategy=risk_close:ipc_close_symbol 
            engine_mode=demo exit_reason=Some(\"ipc_close_symbol\")")
```

兩條 IPC close fills（HYPEUSDT × demo + HYPEUSDT × live_demo）`exit_reason="ipc_close_symbol"` 但 `entry_context_id=""`（empty）。**IPC close path 沒有設 entry_context_id**，違反 V083 constraint。

**WARN 文案 "rows still INSERT (fail-soft)" 完全錯誤** — PG 是 row-level constraint，但 sqlx 批量 INSERT 走「single VALUES clause」整批 reject。實測 rows_affected=0 證明整個 122-row hyperchunk 都被 reject。

### 8. 1 missed entry fill 細節

`bybit-79bdb071-16a6-4cd4-a985-f60452e3d103` (ETCUSDT live_demo qty=2.8 order_id=oc_1778462176961_8) — trading.fills 有 row 但 agent.decision_objects 無對應 ER。

時間線（從 engine.log 重建）：
```
01:16:17.461 PendingOrder registered qty=2.9 ETCUSDT live_demo PostOnly maker
01:16:17.634 dispatched 
01:16:19.114 confirmed fill applied qty=2.8 / 2.9 → trading.fills row 寫成功
01:16:19.117 internal判定: 2.8 < 0.999 × 2.9 = 2.8971 → PartiallyFilled
01:16:19.117 OrderUpdate WS: status=Filled (Bybit 內部已 Filled)
01:16:25.912 PostOnly maker timeout 取消 → REST cancel
01:16:26.086 REST cancel reject: "order not exists or too late to cancel"
01:17:25.920 60s grace expired → 刪 pending tracker
```

→ Bybit 端認為 Filled，engine 端認為 PartiallyFilled。`fully_filled` 條件 `cum_filled_qty >= qty * 0.999` 從未過，所以 `emit_fill_completion_lineage` 從未觸發。`trading.order_state_changes` 終態也是 `PartiallyFilled` 而非 `Filled`（log 內部說 Filled 但這個 status 沒寫 transition）。

---

## 三個 suspect 驗證結論

### suspect 1: trading_writer dispatch race — REFUTED

- 6 orphan ER 都在同一 engine instance (PID 跑於 1778461977 epoch 起的進程) + 同一 trading_writer task
- ER 寫 spine writer，fills 寫 trading_writer，**兩個獨立 mpsc channel**（commands.rs:617 trading_tx vs commands.rs:283 agent_spine_tx）
- 沒有 race condition；apply_confirmed_fill 順序在 emit_fill_completion_lineage 之前
- 證據：`confirmed fill applied` log 在 burst window 內**確實**為 6 orphan 各印 1 次（01:13:37 / 01:14:04 / 01:14:12 / 01:14:12 / 01:14:13 / 01:14:17）。

### suspect 2: Bybit multi-exec event — REFUTED

- 6 orphan filled_qty 全為「order 全部 qty」（9.4 / 20 / 206.6 / 652.1 / 70 / 21.5），cum_qty 不需要 partial fill series
- `quality_metrics.exchange_exec_id` 是單一 UUID，不是 series 的最後一個
- trading.order_state_changes 顯示「Submitted → Working → Filled」乾淨 transition，不是 Bybit multi-exec

### suspect 3: fully_filled edge path — PARTIAL (REFUTED for 6 orphan + CONFIRMED for 1 missed)

- 6 orphan: fully_filled 條件確實過了（cum_filled_qty / qty = 1.0 對所有 6 個 order），emit_fill_completion_lineage 確實被觸發；rule out
- 1 missed: fully_filled gate `0.999` 確實是邊界，2.8 / 2.9 = 0.96552 << 0.999 → PartiallyFilled → 不 emit ER；但 Bybit 端認為 Filled → engine 端 partial state 鎖死

→ **本 RCA 的 root cause 是 #4 第四 suspect（不在 QA 三 suspect 列表）：DB CHECK constraint × batch_insert fail-loud-but-not-actually-soft**

---

## File + line referenced

| 角色 | 路徑:行 | 內容 |
|---|---|---|
| V083 SQL constraint | `sql/migrations/V083__fills_entry_context_id_close_check.sql` | 加 `chk_fills_close_has_entry_context_id_v083` NOT VALID CHECK：`CHECK (exit_reason IS NULL OR entry_context_id IS NOT NULL)` |
| writer warn 誤導 | `rust/openclaw_engine/src/database/trading_writer.rs:406-414` | 文案說 "rows still INSERT (fail-soft); cron backfill will reconcile" 但 PG row-level constraint 實際把整個 chunk reject |
| batch_insert per-chunk fail | `rust/openclaw_engine/src/database/batch_insert.rs:197-220` `run_chunks` | `for chunk in rows.chunks(chunk_rows) { qb.build().execute(pg).await }` — 整個 chunk 走 `INSERT ... VALUES (...), (...), (...)` 一條 statement，任一 row violate constraint = 整 chunk fail，buffer 不 drain |
| flush_fills | `rust/openclaw_engine/src/database/trading_writer.rs:360-460` | call `batch_insert_chunked` 後 `outcome.rows_affected == 0` → 整 buf 保留 |
| flush retain | `rust/openclaw_engine/src/database/trading_writer.rs:89-106` `loop` flush_timer.tick 每 2s 重試，無 bad-row isolation/backoff/dead-letter |
| IPC close path entry_context_id 缺 | `rust/openclaw_engine/src/tick_pipeline/commands.rs` `ipc_close_symbol` / `execute_position_close` (待 grep 精確 line) | 寫 close fill 時 `entry_context_id=""`，違反 V083 |
| fully_filled gate | `rust/openclaw_engine/src/event_consumer/loop_exchange.rs:234` | `let fully_filled = po.cum_filled_qty >= po.qty * 0.999;` — 2.8/2.9=0.96552 不過閾 |
| PostOnly partial path | `rust/openclaw_engine/src/event_consumer/pending_sweep.rs` `tighten_postonly_entry_after_partial` | 縮短 maker_timeout 但 not reconcile Bybit Filled status |
| OrderUpdate(Filled) 分支 | `rust/openclaw_engine/src/event_consumer/loop_exchange.rs:357+` | 處理 status update 但無 fallback「if Filled and PendingOrder.cum_filled_qty < qty, apply 殘量」 |

---

## Fix plan（systemic — 由 PA 後續分配 E1 ticket）

### F1 (P0) — IPC close path 必須帶 entry_context_id

**Root**: V083 constraint 是正確設計（要求 close fill 攜 entry_context_id 以利 ML attribution）；違反者是 IPC close path。

**Fix**: 在 `commands.rs:ipc_close_symbol` / `execute_position_close` close path 內，從 `paper_state.get_entry_context_id(symbol)` 取 entry_context_id，沒拿到時用 `make_context_id(em, symbol, ts_ms)` fallback；確保 `TradingMsg::Fill.entry_context_id` 非空。

預期 LOC: ~10-15 LOC + 1 unit test。

### F2 (P0) — batch_insert 必須有 bad-row isolation

**Root**: 一個 bad row 不能讓整 batch（最多 122 row）全 drop。

**Fix**: `database/batch_insert.rs` 加 retry-with-binary-split 邏輯：整 chunk INSERT 失敗時，split 成兩半遞迴重試，最終定位到 single bad row 並 skip（log + telemetry counter）。**或**直接改 per-row INSERT 在 fail-soft fallback path 內。

預期 LOC: ~30-50 LOC + 2 unit tests + 1 integration test。

**緊急 mitigation**: 觀察期內可考慮把 V083 constraint `DROP` 直到 F1 部署生效。但這會放寬 close-fill quality gate（W-AUDIT-4b-M2 設計目標），需 PM 衡量是否值得。建議 F1 + F2 同次 deploy 而不是先 drop。

### F3 (P1) — fill-writer-entry-context-missing WARN 文案修正

**Root**: WARN 文案「rows still INSERT (fail-soft)」誤導開發者，實際 PG batch reject 整 chunk。

**Fix**: 改 WARN 文案為「close fills with empty entry_context_id will be **rejected by V083 CHECK constraint** — batch INSERT will fail until producer side fixes entry_context_id propagation」並考慮升 ERROR level。

預期 LOC: ~5 LOC（純文字 + log level）。

### F4 (P1) — PostOnly partial vs Bybit Filled reconciliation

**Root**: Bybit 端認為訂單 Filled (full 2.9 qty)，但 engine 端 cum_filled_qty 停在 2.8 → fully_filled gate (0.999) 未過 → ER 不 emit。

**Fix options**:

**Option A**: 在 `loop_exchange.rs` `OrderUpdate(status=Filled)` 分支內，加 fallback：若該 order 對應 PendingOrder 存在且 cum_filled_qty < qty，呼叫 `apply_confirmed_fill` with 殘量 (qty - cum_filled_qty)，並 emit_fill_completion_lineage 一次。需要 protect against double-emit（idempotency key 或 already-handled flag）。

**Option B**: 把 fully_filled gate 從 `>= qty * 0.999` 改成 `>= qty - tick_size`（用 instrument 最小 tick）。

**Option C**: 純 documenting — accept "Bybit 端 dust 殘量被歸入 last fill" 為 by-design noise，把 R-1 missed entry fill 改判 Bybit-noise。但這只能解 1 missed，不能解 6 orphan。

建議: Option A — 它最 conservative 不放寬 fully_filled 語意。

預期 LOC: ~20-30 LOC + 2 unit tests + 1 manual test against demo Bybit。

---

## 額外觀察（不在 fix plan，但 reviewer brief 應提）

### O1 - QA report 中 PID 1597560 etime 78min 是 ps snapshot 過時

實際情況：engine 在 burst window 期間經歷 **3 次 restart**：
- engine-1778460833 (00:53:53 UTC → 01:13:00.5 UTC, ~19min)
- engine-1778461977 (01:12:57.125 UTC → 01:15:40.842 UTC, ~3min) ← **cover burst window 的 instance**
- engine-1778462140 (01:15:40 UTC → 現任，PID 1647446 03:15 CEST)

QA report 採信 watchdog 「engine alive 78min」沒對齊 log 起始時間 (`01:15:40 UTC`)。這個 RCA 的 6 orphan 出現在「中間那個 short-lived instance」內。可能還有 #B5 — **engine restart cascade 本身**值得追（為什麼短時間內 2 次 restart）。

### O2 - V083 deploy_ts 與 deploy_ts (00:01:55 UTC) 的差異

V083 migration `applied` 但 IPC close path 並未同時修。R-2 (QA 提的 cross-wave Sprint N+1 D+0/D+1 source-land) 場景：W6-3c V086 / W-AUDIT-4b-M2 V082-V092 已 applied (PG schema 已加 constraint) 但對應的 Rust producer 邏輯**還沒 deploy**（engine 未 restart）→ writer 寫 row 觸發 constraint 不知情。

→ **下次 SQL constraint 部署應 enforce「producer-side fix 必先 deploy 且 verified」才 apply NOT VALID constraint**。

### O3 - `shadow_filled` literal 出現在 demo + live_demo path

`runtime_shadow.rs:466` 寫 ER status = `"shadow_filled"`（hard-coded literal）。但對 demo + live_demo（**真的 exchange-place real order with real fills**），這個 status 字面值誤導 — 它不是「shadow」（即沒下單）的成交，而是「Spine shadow lineage 上的真實成交」。建議 rename 或 doc clarify（不在本 RCA scope）。

---

## 不確定之處 / Uncertain

1. **WARN message 是否 trigger 自 V083 deploy 後立即**：log file 起 01:12:57，未涵蓋 V083 deploy 時點。需要看更早 engine_logs（engine-1778460833 / 1778455753）確認 WARN 是否 V083 deploy 起就持續發生。若是，6 orphan 是「正常觀察 + lag-induced」；若不是，需查 W-AUDIT-4b-M2 cron 是否漏跑導致 entry_context_id 沒回填。

2. ~~**batch_insert 真的整 chunk reject 還是 chunk-of-1 row reject**~~ → **已 confirm**：`trading_writer.rs:429-507` 用 `sqlx::QueryBuilder::push_values` 構造**單一 `INSERT ... VALUES (...), (...), (...)` 多 row statement**。PG row-level CHECK constraint 在 multi-row INSERT 中任一 row 違反 = 整個 statement abort 不會 partial commit。`ON CONFLICT (fill_id, ts) DO NOTHING` 對 unique 有效但對 CHECK 無效（CHECK 在 INSERT prep 階段 evaluate 不是 conflict）。`batch_insert.rs:run_chunks` 中 `qb.build().execute(pg).await` Err 分支只 record_failure() + `failed_chunks += 1`，不對 chunk 內 row 做 isolation。**Fix F2 必要**。

3. **Engine 2 次 restart cascade 原因**：00:53 → 01:12 → 01:15 三 instance。watchdog auto-respawn？operator manual？restart_all script？需查 `/tmp/openclaw/api.log` 或 systemd journal 印證。如果是 watchdog 觸發，可能與本 RCA 有關（trading.fills 卡死導致 healthcheck fail → respawn）。

---

## Operator 下一步

| 動作 | 預期時程 |
|---|---|
| PM consolidate 本 RCA + PA + QC parallel audit（若有），verdict = **SYSTEMIC**，發 fix plan ticket | T+0 |
| PA 分配 F1+F2 為一個 E1 ticket（同次 deploy，避免 F2 沒 deploy 仍卡 trading.fills） | T+0 |
| F3 (warn 文案) 可獨立 P1 ticket | T+1 |
| F4 (PostOnly reconcile) 可獨立 P1 ticket | T+2 |
| 緊急 mitigation 評估：是否在 F1+F2 部署前手動 DROP V083 constraint？ | T+0 operator decide |
| 補 healthcheck：監測 `batch_insert failed` log rate + trading_writer pending_rows > 100 持續 5min 即 alert | F2 deploy 同次 |
| 重 audit MAG-083 R-1 finding：QA 原判 "non-systemic" 改為 SYSTEMIC，MAG-084 §5 P1-RCA-1 status 改 BLOCKED 直至 F1+F2 land | T+0 |

---

## E1 IMPLEMENTATION DONE: 待 E2 審查

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_rca1_orphan_er_missed_fill.md`

**HEAD at RCA start**: `388e04b2`
**SSH verification target**: `trade-core` (Linux runtime)
**Read-only artifacts touched**: engine logs (`/tmp/openclaw/engine_logs/`), agent.decision_objects, trading.fills, trading.orders, trading.order_state_changes
**No code change in this ticket.** Fix plan F1-F4 待 PA 派工。
