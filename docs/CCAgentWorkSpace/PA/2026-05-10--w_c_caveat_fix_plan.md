# W-C MAG-082 Caveat 1+2 Fix Plan + No-24h Verification Protocol

**Date**: 2026-05-10
**Author**: PA
**Trigger**: QA `2026-05-10--w_c_signoff_audit.md` 裁決 CONDITIONAL_PASS；operator Option B（先修再 sign-off）+ 拒絕重等 24h
**Scope**: Caveat 1（`agent.decision_state_changes` 0 row）+ Caveat 2（ExecutionReport.payload 全 stub）+ [55] 升級 + 短窗驗證協議
**Authority**: 本 plan 是技術設計，**不 commit**、**不啟動 E1**、**不改 TODO.md/CLAUDE.md**

---

## 0. TL;DR

| 項 | 結論 |
|---|---|
| 根因 1（state_changes 0 row） | producer code 在但 **0 caller** — `put_state_transition` 只有 trait/impl/test 引用。Spine 5 種 object 的 lifecycle SM emit 完全沒接線。`learning.lease_transitions`（V054）是 **不同** SM（SM-02 lease），不能取代 Spine 自己的 5 object SM。 |
| 根因 2（ExecutionReport stub） | `runtime_shadow::emit_entry_lineage` 在 `step_4_5_dispatch.rs:614 / :878` intent dispatch 後立刻 emit，此時尚未成交 → `filled_qty: Some(0.0)` + `liquidity_role: "unknown"` 是 **by-design stub**（status=`"shadow_planned"`）。**缺第二 emit**：成交 confirmed 後沒人補 row。 |
| 修復策略 | （1）E1-W-C-FIX-1 在 5 object 已知 lifecycle 邊界補 `put_state_transition` caller（emit_entry_lineage 內部 + apply_confirmed_fill 內部）；（2）E1-W-C-FIX-2 新增 `emit_fill_completion_lineage` 在 `loop_exchange.rs` fully_filled 區塊呼叫；（3）E1-W-C-FIX-3 在 `checks_agent_spine.py` 加 `bad_report_value_quality` 新指標。 |
| Historical 51h stub rows | **留著加 quality_metrics 標記**（Option α），不 backfill。理由見 §2.4。 |
| 短窗驗證 | unit test PASS + 30min post-deploy sample（state_changes 累積率 ≥ 5/min + 新 ExecutionReport real-fill ≥ 90% + trading.fills 對抗 join）→ QA re-audit。**取代 24h** 的邏輯：51h 量已累；改的是 producer correctness，短窗證 correctness 修好即可，不需重新證量。 |
| 並行度 | E1-W-C-FIX-1 + FIX-2 + FIX-3 **全 3 並行**（不同檔不同層）。 |
| 風險評級 | 中。hot path 影響 < 1ms（put_state_transition 是 mpsc try_send，與既有 emit_entry_lineage 同機制）。LiveDemo restart 30s 中斷可接受。 |
| 硬邊界觸碰 | 0。寫 read-only schema 寫入；不動 lease 授權/live_reserved/max_retries/Mainnet gate；shadow mode runtime unchanged。 |

---

## 1. Caveat 1 修復方案 — `agent.decision_state_changes` 接 producer

### 1.1 RCA 確認

```
grep -rn 'put_state_transition' rust/openclaw_engine/src/  →  4 命中
  store.rs:52   trait declare
  store.rs:68   DisabledAgentSpineStore impl (stub)
  store.rs:105  ChannelAgentSpineStore impl (real，self.try_send(StateTransition(_)))
  tests.rs:495  unit test 自我驗證

grep -rn 'INSERT INTO agent.decision_state_changes' …  →  1 命中
  agent_spine_writer.rs:237  flush_state_transitions() SQL，由 mpsc consume

caller 真實數 = 0
```

**根因**：Sprint 2 Track E 寫 producer + writer 時就沒接 callsite。`AgentSpineMsg::StateTransition` channel arm 在 writer.rs:51 已 ready 但永遠收不到訊息。

### 1.2 DDL / Schema 變動

**無需 DDL**。`agent.decision_state_changes` 表 V064 已存在；schema 包括 `(ts, transition_id, object_id, object_type, from_state, to_state, engine_mode, trigger, details)`；hypertable + 2 index OK；CHECK constraint：
- `object_type IN ('strategy_signal','strategist_decision','guardian_verdict','execution_plan','execution_report','analyst_insight')`
- `to_state` 非空，`engine_mode` 非空

**重要邊界**：CHECK 不允許 `'decision_lease'` 作為 object_type。**SM-02 lease lifecycle 已在 `learning.lease_transitions`（V054）寫**，不要混進 Spine state_changes。Spine 寫的是 **Spine 自己的 5 種 object 的 lifecycle SM**。

### 1.3 接入點清單（5 object × N transition）

Spine 5 object 在 `emit_entry_lineage` 內由 1 個事件**同時建立**（signal+decision+verdict+plan+report 5 objects 全在同 ts_ms 寫入）。所以接入點分兩階段：

**Stage A — 建立期 transitions（在 `emit_entry_lineage` 末尾，5 條 transitions）**

每個新 object 寫 1 條 `from_state=NULL, to_state=<initial state>` transition：

| object_type | object_id 取自 | to_state | trigger |
|---|---|---|---|
| `strategy_signal` | `signal.signal_id` | `"emitted"` | `"runtime_signal_emit"` |
| `strategist_decision` | `decision_id` | `"approved_open"` | `"runtime_decision_emit"` |
| `guardian_verdict` | `verdict.verdict_id` | `"approved"` | `"runtime_verdict_emit"` |
| `execution_plan` | `plan.order_plan_id` | `"shadow_planned"` | `"runtime_plan_emit"` |
| `execution_report` | `report.execution_report_id` | `"shadow_planned"` | `"runtime_report_emit"` |

**檔案 + 行**：`rust/openclaw_engine/src/agent_spine/runtime_shadow.rs`，在 `emit_entry_lineage` 函式 `try_send(... ExecutionIdempotencyKey ...)`（line 274-278）之後、回傳 accepted 之前，加 5 條 `SpineStateTransition::new(...)` 並 `try_send(tx, AgentSpineMsg::StateTransition(t), "state_transition")`。

**Stage B — 變更期 transitions（成交完成後在 `loop_exchange.rs` 加，2 條 transitions per fill）**

| object_type | from_state | to_state | trigger |
|---|---|---|---|
| `execution_plan` | `"shadow_planned"` | `"shadow_executed"` | `"runtime_fill_confirmed"` |
| `execution_report` | `"shadow_planned"` | `"shadow_filled"` | `"runtime_fill_confirmed"` |

**檔案 + 行**：`rust/openclaw_engine/src/event_consumer/loop_exchange.rs:234-260` `fully_filled` 區塊內，與 Caveat 2 的 `emit_fill_completion_lineage` 同 commit。

**注意 partial fill**：不寫 transition（會炸量；MAG-082 evidence 只需證 SM 接線真實，不需逐個 partial）。可選優化（不在 fix scope）：partial fill 寫 `details.partial_fill_count` 但不換 state。

### 1.4 engine_mode 標籤

對齊現有 emit_entry_lineage 的 `input.engine_mode`（已是 `'demo'` / `'live_demo'` 字串）；transition.engine_mode 直接傳同字串，無需轉換。

### 1.5 Hot path 影響評估

- `emit_entry_lineage` 增 5 個 `try_send`（單 channel mpsc 非阻塞），單次成本約 50-200 ns，可忽略
- `loop_exchange.rs` `fully_filled` 區塊增 2 個 `try_send` + 一個新 emit 函式呼叫；fully_filled 本就是低頻事件（24h ~86 row），絕對 ns 級成本
- channel full 時 fallback warn log（與既有 try_send 行為一致）
- **不阻塞 H0 / IntentProcessor / Risk SM**

### 1.6 風險清單

| 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|
| `transition_id` collision（5 object 同 ts_ms 同 trigger）| 低 | 重複 row | `stable_id` 已含 `object_id` + `to_state` + `trigger` + `ts_ms`，不會撞；`ON CONFLICT (transition_id, ts) DO NOTHING` 二重保護 |
| channel full → 訊息漏 | 低 | metric 短暫 < 100% | 既有 warn log；E4 監控 |
| paper engine 也跑 emit_entry_lineage → 寫 paper transitions | 中 | 污染 spine data | emit_entry_lineage 已過濾 `engine_mode IN ('demo','live_demo')`（runtime_shadow.rs:43），paper 不會走到 |

---

## 2. Caveat 2 修復方案 — ExecutionReport real-fill propagation

### 2.1 RCA 確認

`emit_entry_lineage`（runtime_shadow.rs:183-213）在 intent dispatch **後立刻 emit** ExecutionReport，此時尚未成交：
- `filled_qty: Some(0.0)` ← 沒成交，當然 0
- `liquidity_role: "unknown"` ← 還不知道是 maker/taker
- `status: "shadow_planned"` ← 明確標 planned 而非 filled

**這是 by-design stub**（report 在 plan 同時建立，給 lineage chain 結構完整）。Caveat 2 真正的 gap **不是 stub row 是 bug**，而是 **缺第二 emit**：成交確認後沒有任何 caller 補一條真實 row 進 Spine。

`trading.fills` 在 `loop_exchange.rs:213 apply_confirmed_fill(...)` 同 path 內由 `pipeline.intent_processor.persist_fill(...)` 寫入；真實 `liquidity_role`、`filled_qty`、`fee_bps` 都已計算（`loop_exchange.rs:193`，`exec_qty`、`fee_rate_used`、`slippage_bps` 全 ready）。

### 2.2 設計選項（3 個 + 推薦）

#### Option α（推薦）— 寫第二 ExecutionReport row 表示「real fill」

**設計**：在 `loop_exchange.rs:234-260` `fully_filled` 區塊內新增 `emit_fill_completion_lineage(...)`，**寫一條新的 ExecutionReport** 帶真實值：
- 新 `execution_report_id = stable_id("report", &[em, order_plan_id, "shadow_filled"])` ← suffix 從 `"shadow_planned"` 改 `"shadow_filled"`
- 新 `idempotency_key = "shadow_execution_report_filled:{em}:{order_plan_id}"`（不同於 stub 的 `shadow_execution_plan:...`）
- 新 row `filled_qty = po.cum_filled_qty`, `liquidity_role = liquidity_role from fill_helpers`, `avg_fill_price`, `slippage_bps`, `fees_paid`, `fee_bps` 全帶
- 新 `status = "shadow_filled"`, `payload.shadow_lineage_only = true`, `payload.shadow_planned_report_id = <stub report_id>` cross-ref
- 同次 emit 一條 `SpineEdge`：`from = order_plan_id, to = filled_report_id, edge_type = executed_by_filled`（**新 edge_type**），讓 [55] healthcheck 新指標 `bad_report_value_quality` 從 `executed_by_filled` edge 抓 real-fill report

**優點**：
- 完全 additive，**0 改動** `ON CONFLICT (object_type, idempotency_key) DO NOTHING` 語意 → 不需動 V064 schema
- 兩條 row 並存即「事件流水」（planned + filled），是 audit-friendly pattern
- stub row 仍可用作 routing intent 證據；filled row 提供 attribution 證據
- **與 W-D MAG-083 reviewer 看到的證據鏈 compatible**：reviewer 透過 `executed_by_filled` edge 抓真實 fill row（new query path），同時保留 lineage chain 結構

**缺點**：
- 24h row 數量 ~翻倍（97 → ~180 per mode；不痛癢，目前 spine 24h 870 objects 規模）
- 需新增 `DecisionEdgeType::ExecutedByFilled` variant + V064-or-later migration 加 CHECK enum（**或** 用既有 `executed_by` edge type 加 `details.fill_completion = true` 區分）

**Migration 抉擇**：
- **A（推薦）**：用既有 `executed_by` edge type + `details.fill_completion = true` JSON 標記 → **0 migration** + 0 CHECK 變動
- B：新增 `executed_by_filled` enum → V### migration（ALTER TYPE ADD VALUE 或 ALTER TABLE DROP/ADD CHECK）

**推薦 A**：與 V### migration governance（PG dry-run mandatory + ALTER VALIDATE）相比，JSON details 標記成本接近 0；[55] healthcheck 篩 real-fill row 用 `WHERE edge_type = 'executed_by' AND (details->>'fill_completion')::boolean IS TRUE` 即可。

#### Option β — 更新原 ExecutionReport row（DO UPDATE）

**設計**：改 `agent_spine_writer.rs:162` `ON CONFLICT DO NOTHING` → `ON CONFLICT DO UPDATE SET payload = EXCLUDED.payload`，然後 `loop_exchange.rs` 用同樣 `execution_report_id` re-emit。

**棄用**：違反 Spine 設計哲學（typed lineage = append-only event log）；hypertable + ON CONFLICT DO UPDATE 在 partition 邊界 PG 可能有 corner case；對 audit pack 不友好（reviewer 看到 row 變了就懷疑被改），**不推薦**。

#### Option γ — dual-write trading.fills + agent.decision_objects 同 transaction

**設計**：在 `trading_writer.rs` fill INSERT 同 transaction 內 INSERT agent.decision_objects + edges。

**棄用**：耦合 trading.fills hot path 與 Spine writer；trading_writer 是 actor 模型不開 cross-table transaction；違反 Spine fail-soft 哲學（spine 寫死不可阻塞 fill 寫入），**不推薦**。

### 2.3 接入點清單（Option α）

**新增**：`rust/openclaw_engine/src/agent_spine/runtime_shadow.rs` 新增 `emit_fill_completion_lineage` 函式，簽名與 emit_entry_lineage 並列。輸入：

```rust
pub struct FillCompletionLineageInput<'a> {
    pub order_plan_id: &'a str,       // 由 caller 從 PendingOrder→stable_id 推；或 cross-table query
    pub decision_id: &'a str,         // 同上
    pub symbol: &'a str,
    pub engine_mode: &'a str,
    pub strategy: &'a str,
    pub ts_ms: u64,                   // exec_ts
    pub filled_qty: f64,              // po.cum_filled_qty
    pub avg_fill_price: f64,          // exec_price
    pub fees_paid: f64,               // exec_fee
    pub fee_bps: Option<f64>,         // fee_rate_used * 10000.0
    pub slippage_bps: Option<f64>,    // slippage_bps from helper
    pub liquidity_role: &'a str,      // "maker" | "taker" from fill_liquidity_role
    pub fill_latency_ms: Option<u64>, // fill_latency_ms
    pub exchange_exec_id: &'a str,    // exec.exec_id
    pub stub_report_id: &'a str,      // cross-ref to shadow_planned row
}
```

**呼叫點**：`rust/openclaw_engine/src/event_consumer/loop_exchange.rs:259-261` `if fully_filled { ... }` block 第一行（remove pending_orders 之前），呼叫 `emit_fill_completion_lineage(pipeline.agent_spine_tx.as_ref(), pipeline.agent_spine_mode, FillCompletionLineageInput { ... })`。

**`order_plan_id` 取得問題（關鍵）**：

PendingOrder 沒有 order_plan_id 鏡射欄位（grep verified）。兩個選項：

- **A1（推薦）**：在 `PendingOrder` struct 加新欄位 `pub order_plan_id: Option<String>`（emit_entry_lineage 同步計算 stable_id 後注入），完美 propagate
- **A2**：runtime 重算 `stable_id("plan", &[em, decision_id, verdict_id])` — 但 decision_id 也沒 PendingOrder 欄位，需重算 `stable_id("decision", &[em, signal_id])`，signal_id 也需要重算 → cascading 重算，每步都吃 PendingOrder.context_id 但 context_id 不等於 signal_id（spine 用獨立 stable_id 體系）→ **不可行**

**結論：用 A1**。E1-W-C-FIX-2 同時動 4 處：
1. `event_consumer/types.rs:PendingOrder` 加 3 個 Option 欄位（`order_plan_id` / `decision_id` / `verdict_id`），預設 None 不破既有測試
2. `tick_pipeline/on_tick/step_4_5_dispatch.rs:614` emit_entry_lineage 後注入 ids 到 PendingOrder 建構（兩處 callsite line 614 + line 878）
3. `agent_spine/runtime_shadow.rs` 加 `emit_fill_completion_lineage`
4. `event_consumer/loop_exchange.rs:259` 加呼叫

### 2.4 Historical 51h stub rows 處理 — **留著加 quality_metrics 標記**

**選項對比**：

| 選項 | 描述 | 利 | 弊 |
|---|---|---|---|
| a | 留著加 `quality_metrics.shadow_planned_only = true` 標記 | 0 風險；保留 audit trail | bad_report_value_quality 在 24h 內仍包含舊 stub（影響 metric 過渡期） |
| b | SQL 補寫 backfill 從 trading.fills 拉 | 全部 row 修齊 | 跨表 update 風險；2555 row × 5 cols = 大寫；不對齊「append-only event log」原則 |
| c | 保持不動只修新 row | 0 風險 | bad_report_value_quality 短期含舊 stub |

**推薦 a**：與 c 等價（不動既有 row），但**新指標 query 在 d+0 後加 24h 過濾** — `WHERE created_at > <fix deploy_ts>` 自動排除 historical stub。a 比 c 多一條 governance trail（在新 healthcheck message 標 "value_quality cutoff = deploy_ts"）。

具體做法：
- **不寫 backfill SQL**
- 新 [55] `bad_report_value_quality` query 加 `AND created_at > '$DEPLOY_TS'::timestamptz`（DEPLOY_TS 從 env var `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS` 讀取，env 缺則用 24h 滑動窗 fallback）
- W-D MAG-083 reviewer 看到 [55] message 含 `value_quality_cutoff=<ts>` 即理解語意

### 2.5 W-D MAG-083 reviewer compatibility

修復後 reviewer 看到的證據鏈差異：

| 證據點 | 修前 | 修後 |
|---|---|---|
| chains 完整性 | 174/174 PASS | 174/174 PASS（不變） |
| chains_with_lease | 174/174 'bypass'（PASS by-design）| 同（不變） |
| chains_with_report | 174/174 stub | 174/174 stub **+ N real-fill rows**（新） |
| bad_report_quality | 0（key existence）| 0（不變） |
| bad_report_value_quality（新）| N/A | 0 within window |
| chains_with_real_fill_report（新）| N/A | ≥ X% within window |
| decision_state_changes 24h | 0 | ≥ 5 × chains（5 object 建立 transitions × N chains）+ 2 × fills（變更 transitions × M fills）|

**reviewer 需要的解讀更新**：MAG-083 audit pack 應包含「Caveat 1+2 fixed 後新證據點」的明確段落，由 PM 在 audit pack template 內預設章節。**不破 MAG-083 整體判斷邏輯**，只是新加 2 個 PASS 條件。

---

## 3. [55] healthcheck 升級

### 3.1 新指標 `bad_report_value_quality`

**位置**：`srv/helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py` `_complete_chain_counts` 函式（line 156-200 區段）。

**新 SQL（並列既有 bad_report_quality 計算）**：

```sql
-- 新增：value-realism check
count(DISTINCT filled_report.object_id) FILTER (
    WHERE filled_report.object_id IS NOT NULL
      AND filled_report.created_at > %s::timestamptz  -- DEPLOY_TS cutoff
      AND (
        (filled_report.payload->>'filled_qty')::numeric <= 0
        OR filled_report.payload->>'liquidity_role' NOT IN ('maker','taker')
      )
)::int AS bad_report_value_quality,

count(DISTINCT filled_report.object_id) FILTER (
    WHERE filled_report.object_id IS NOT NULL
      AND filled_report.created_at > %s::timestamptz
      AND (filled_report.payload->>'filled_qty')::numeric > 0
      AND filled_report.payload->>'liquidity_role' IN ('maker','taker')
)::int AS chains_with_real_fill_report
```

**join 新增**（在現有 `LEFT JOIN agent.decision_objects report` 之後）：

```sql
LEFT JOIN agent.decision_edges filled_report_edge
  ON filled_report_edge.from_object_id = c.order_plan_id
 AND filled_report_edge.edge_type = 'executed_by'
 AND (filled_report_edge.details->>'fill_completion')::boolean IS TRUE
LEFT JOIN agent.decision_objects filled_report
  ON filled_report.object_id = filled_report_edge.to_object_id
 AND filled_report.object_type = 'execution_report'
 AND filled_report.engine_mode = c.engine_mode
 AND filled_report.created_at > now() - (%s::text || ' minutes')::interval
```

### 3.2 新指標 `state_changes_24h`（Caveat 1 對應）

並列加：

```sql
-- 新增：state_changes 累積數
SELECT count(*)::int FROM agent.decision_state_changes
WHERE engine_mode = ANY(%s)
  AND ts > now() - (%s::text || ' minutes')::interval
```

寫成獨立 helper 或在 `check_55_*` 同個 cur.execute 內額外查（推薦獨立 helper，避免 query 過長）。

### 3.3 PASS 判定升級

**新閾值**（追加到既有判定）：

```
IF state_changes_24h <= 0:
    return BLOCKED_STATE_CHANGES_EMPTY
IF bad_report_value_quality > 0:
    return BLOCKED_REPORT_VALUE_QUALITY
IF chains_with_real_fill_report < complete_chains * 0.5:
    # 觀察期門檻：>= 50% chains 有 real-fill report（保守起步）
    return WARN_REAL_FILL_PROPAGATION_PARTIAL
```

**為何 50% 不 90%**：MAG-082 24h window 中 174 chains 對應 86 真實 fills（trading.fills 24h）→ 期望 ratio = 86/174 ≈ 49.4%（unfilled intents 是 cancel / reject 的合法 outcome，不應強制 90%）。push back 給 operator：如要更嚴 90%，需先驗 chains 與 fills 真實對應比例。

### 3.4 Message format

```
agent decision spine lineage proof healthy; MAG-082 readiness=LINEAGE_READY_NOT_WINDOW_PASS
  window=1440m modes=demo,live_demo
  objects=870/2555 edges=696/2044 idempotency=174/511
  types=strategy_signal=174,strategist_decision=174,guardian_verdict=174,execution_plan=174,execution_report=174
  chains=174 chains_with_idempotency=174 chains_with_lease=174 chains_with_report=174
  bad_report_quality=0 bad_report_value_quality=0
  chains_with_real_fill_report=86 (49.4%)
  state_changes_24h=1392 (5 build × 174 chains + 2 change × 86 fills)
  value_quality_cutoff=2026-05-11T<deploy_ts>+02
```

### 3.5 Required state（fix 後）

| 指標 | Required | 理由 |
|---|---|---|
| `bad_report_value_quality` | 0 | 新 fill rows 應 100% real |
| `chains_with_real_fill_report` ≥ 50% of complete_chains | ≥ 87/174 | 真實 fill ratio 是 49.4% baseline；50% 容差 |
| `state_changes_24h` ≥ 5 × complete_chains | ≥ 870 | 每 chain 5 object × 1 build transition |

---

## 4. 短窗驗證協議（取代 24h 重等）— **核心**

### 4.1 為何短窗夠

24h 是 evidence accumulation 量需求；現在 W-C 已累 51h（870 objects + 174 chains + 100% lineage chain）→ **量已過閾值**。
caveat 修正改的是 producer correctness：
- Caveat 1 = 接 5 條 callsite（type-safe Rust）
- Caveat 2 = 加 1 個 emit fn + propagate 3 個 Option 欄位

→ 改的是 **wiring** 不是 **量**。短窗能證 wiring correctness（每分鐘累幾條），不需要重新證 24h 量。

**reviewer-friendly 邏輯**：MAG-083 audit pack 內加段落「Caveat 1+2 wiring delta verified at <deploy+30min>；historical 51h lineage chain 不變」即可。

### 4.2 (a) Unit test PASS 條件

| Test | 期望 |
|---|---|
| `runtime_shadow::emit_entry_lineage_emits_5_state_transitions` | 確認 5 個 SpineStateTransition msg 進 channel；object_type 各對 |
| `runtime_shadow::emit_fill_completion_lineage_writes_real_fill` | mock fill input → 確認 ExecutionReport 帶真實 filled_qty/liquidity_role；transition 2 條（plan + report） |
| `runtime_shadow::emit_fill_completion_lineage_disabled_in_paper` | engine_mode='paper' → 0 emit |
| `loop_exchange::handle_exchange_event_emits_fill_completion_on_fully_filled` | mock pipeline + 完整成交 → emit_fill_completion_lineage 被呼叫一次 |
| `loop_exchange::handle_exchange_event_does_not_emit_on_partial_fill` | partial fill → 不 emit fill_completion |
| `checks_agent_spine::value_quality_check_filters_pre_cutoff_rows` | mock row created_at < cutoff → bad_report_value_quality 不計 |
| `checks_agent_spine::value_quality_check_passes_real_fill_rows` | mock row filled_qty > 0 + role='maker' → 算 chains_with_real_fill_report |
| `checks_agent_spine::value_quality_check_fails_stub_rows` | mock row filled_qty=0 + role='unknown' AND created_at > cutoff → bad_report_value_quality=1 |

PASS 條件：**8/8 unit tests GREEN**（E4 跑 cargo test + pytest）。

### 4.3 (b) Post-deploy 短窗 sample（30 min 為主，60 min 為退守）

**N = 5 個 callsite 接入（5 strategy_signal/decision/verdict/plan/report build transition）+ 1 個 fill completion emit fn**

| 指標 | 目標 | 期望時間到達 |
|---|---|---|
| `agent.decision_state_changes` row count > 0 | 立即（deploy + 1 min）| deploy+1min |
| `state_changes` rate ≥ 5/min | 持續 30 min | deploy+30min |
| `chains_with_real_fill_report` ≥ X% | X = 30%（前 30 min 較少 fill）→ 50%（穩態 24h）| deploy+30min |
| `agent.decision_objects` ExecutionReport with `payload->>'filled_qty'::numeric > 0` count > 0 | 立即（首個 fill 觸發）| deploy+~5min（demo fill rate ~50/24h ≈ 2/h） |
| `trading.fills` ↔ `agent.decision_objects` 對抗 join：每筆新 fill 必 join 到 1 row real-fill ExecutionReport | 100% | deploy+30min |

**對抗 SQL（運維手動跑）**：

```sql
-- 對抗：每筆新 fill 必有對應 real-fill ExecutionReport
WITH new_fills AS (
    SELECT context_id, entry_context_id, engine_mode, ts as fill_ts
    FROM trading.fills
    WHERE ts > '<deploy_ts>'::timestamptz
      AND engine_mode IN ('demo','live_demo')
),
real_reports AS (
    SELECT object_id, payload->>'fill_id' as fill_id, engine_mode, created_at
    FROM agent.decision_objects
    WHERE object_type = 'execution_report'
      AND (payload->>'filled_qty')::numeric > 0
      AND payload->>'liquidity_role' IN ('maker','taker')
      AND created_at > '<deploy_ts>'::timestamptz
)
SELECT
    count(nf.*) as new_fills_n,
    count(rr.object_id) as matched_reports_n,
    count(nf.*) - count(rr.object_id) as missed_n
FROM new_fills nf
LEFT JOIN real_reports rr ON rr.engine_mode = nf.engine_mode
WHERE nf.fill_ts > '<deploy_ts>'::timestamptz;
```

**期望**：`missed_n = 0`，否則 fail-closed 重新 deploy。

### 4.4 (c) 為什麼短窗夠 — push back-ready 論證

如果 operator/reviewer 質疑「為什麼不重等 24h」：

1. **24h window 的功能**是「證 lineage chain 在多個小時、多種 market regime、跨重啟下都能累積」— 這 51h 已證
2. **caveat 修正的功能**是「修 producer call gap」— 是 deterministic code wiring fix，不是 statistical sampling fix
3. **30min sample 證的是**：新 producer call 真有被執行（state_changes 累積率 > 0）+ 新 ExecutionReport 真有真值（cross-join trading.fills）
4. **歷史 51h evidence chain 100% complete 不會消失**：[55] 仍 PASS LINEAGE_READY；W-D 證據 baseline 不退步
5. **MAG-083 audit pack 內**明確列「Caveat 1+2 wiring fixed at deploy+0；30min post-deploy short-window verification PASS at deploy+30；historical 51h lineage chain unchanged」 → reviewer 看完整 evidence trail

### 4.5 (d) 風險 vs benefit

| 風險 | 描述 | Mitigation |
|---|---|---|
| 30 min 內未觸發 fill | demo fill rate ~50/24h ≈ 2/h，30min 內可能 0 fill | 改 60 min 為退守；如 60min 仍無 → 等到首個 fill 為止（最多 +2-3h），不重等 24h |
| `state_changes` 累積率 < 5/min | 表示 5 callsite 漏接 1-2 個 | E2 重 review；E4 重跑 unit test 找 missing transition |
| post-deploy 期間恰逢市場空窗 | 與 24h 重等同樣 risk（24h 也可能遇到空窗）| 與 24h 重等同樣處理：等到首個 chain 累積 |
| stub row 在 24h 滾出視窗前混入 metric | cutoff query 已 mitigate | env var DEPLOY_TS 必設；E2 必查 [55] message 含 cutoff 值 |

**Benefit**：相比 24h 重等，短窗節省 23-23.5h critical path 時間；W-D 可在 deploy+2-4h 內 sign-off（取決於 first fill 等待）。

---

## 5. E1 並行任務拆分

### Task E1-W-C-FIX-1 — Caveat 1: put_state_transition wiring（Rust）

**Estimated LOC**: ~80-120 LOC（純 add）
**Files**:
- `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs`：在 `emit_entry_lineage` 末尾加 5 條 `SpineStateTransition::new(...)` + `try_send`
- `rust/openclaw_engine/src/event_consumer/loop_exchange.rs:259`：在 fully_filled block 加 2 條 transition emit（與 FIX-2 共 commit）
- `rust/openclaw_engine/src/agent_spine/tests.rs`：加 3 個 unit test（5 transitions / disabled mode / partial fill no-emit）

**Acceptance**:
- 5 SpineStateTransition 在 emit_entry_lineage 末尾發送
- 2 SpineStateTransition 在 fully_filled 路徑發送
- 3 unit test PASS
- cargo build 0 warning

**Dependencies**:
- 與 E1-W-C-FIX-2 **同檔（loop_exchange.rs）**：建議由同 E1 sub-agent 接走 FIX-1+FIX-2（合併 task）；或拆 commit chain 但同 sub-agent
- 與 E1-W-C-FIX-3 **完全獨立**

### Task E1-W-C-FIX-2 — Caveat 2: real-fill propagation（Rust）

**Estimated LOC**: ~180-250 LOC
**Files**:
- `rust/openclaw_engine/src/event_consumer/types.rs:PendingOrder`：加 `order_plan_id` / `decision_id` / `verdict_id` 三 `Option<String>` 欄位
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:614 / :878`：emit_entry_lineage 後注入 3 個 id 到 PendingOrder
- `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs`：新增 `emit_fill_completion_lineage` + `FillCompletionLineageInput`
- `rust/openclaw_engine/src/event_consumer/loop_exchange.rs:259-261`：fully_filled block 加 `emit_fill_completion_lineage(...)` 呼叫
- `rust/openclaw_engine/src/agent_spine/tests.rs`：加 3 unit test
- 其他既有測試 fixture：`PendingOrder` 新 3 field 預設 None

**Acceptance**:
- emit_fill_completion_lineage 寫一條新 ExecutionReport row（filled_qty/liquidity_role/avg_fill_price 全帶真實值）
- 寫一條新 SpineEdge `executed_by + details.fill_completion=true`
- 寫 2 條 SpineStateTransition（plan + report）
- engine_mode='paper' 0 emit
- partial fill 0 fill_completion emit
- 3 unit test PASS
- 既有 emit_close_fill / loop_exchange tests 不破

**Dependencies**:
- 與 FIX-1 同檔 loop_exchange.rs → 合併同 sub-agent
- 與 FIX-3 完全獨立

### Task E1-W-C-FIX-3 — [55] healthcheck value-realism check（Python）

**Estimated LOC**: ~80-120 LOC
**Files**:
- `srv/helper_scripts/db/passive_wait_healthcheck/checks_agent_spine.py`：
  - `_complete_chain_counts` SQL 加 2 column（`bad_report_value_quality`, `chains_with_real_fill_report`）+ 2 LEFT JOIN（filled_report_edge + filled_report）
  - 加新 helper `_state_changes_count(cur, modes, window_minutes) -> int`
  - `check_55_*` 整合新指標到 detail message + PASS 判定
  - env var `OPENCLAW_AGENT_SPINE_VALUE_QUALITY_CUTOFF_TS` 讀取（缺則用 24h window fallback）
- 對應測試（如有 mock PG fixture）：3 個 unit test（value_quality_filters_cutoff / passes_real_fill / fails_stub_rows）

**Acceptance**:
- 新指標 SQL 正確（手動跑 against Linux PG 驗證 row count 合理）
- env var cutoff 邏輯正確
- message format 含新指標
- PASS 判定升級正確
- 既有 [55] PASS condition 不破

**Dependencies**:
- 與 FIX-1+FIX-2 **完全獨立**（不同檔不同層）
- 可並行甚至先派發；reach acceptance 需 FIX-1+FIX-2 deploy 後 30 min real data

### 並行序列

```
D+0 09:00-15:00  E1-FIX-1+FIX-2 (合併 Rust sub-agent) ─┐
                                                       ├─ E2 review + E4 regression
D+0 09:00-12:00  E1-FIX-3 (Python sub-agent)          ─┘   ↓
                                                       D+0 17:00 sign-off + deploy
                                                           ↓
                                                       D+0 17:30 post-deploy short-window check (30min)
                                                           ↓
                                                       D+0 18:00 QA re-audit + W-D dispatch
```

**並行度 = 3 sub-agent**（FIX-1+FIX-2 合 1 個 / FIX-3 獨立 1 個 / 預備 1 個 buffer）。

---

## 6. E2 review 重點 + E4 regression 必跑項

### E2 必查（4 點）

1. **hot path SLA**：emit_entry_lineage 增 5 try_send / loop_exchange 增 1 emit_fn + 2 try_send → bench 對比，confirm < 50us 延遲增（既有 emit_entry_lineage baseline ~ 20us）
2. **`unsafe` / `unwrap()` 0 命中**：grep FIX-1+FIX-2 diff
3. **dual-write race**：`stable_id("report", &[em, plan_id, "shadow_planned"])` vs `stable_id("report", &[em, plan_id, "shadow_filled"])` → 必須產生不同 id（單元測驗證）；`idempotency_key` 兩 row 必須不同
4. **`engine_mode` 過濾**：emit_fill_completion_lineage 必複用 emit_entry_lineage 的 `matches!(engine_mode, "demo" | "live_demo")` 過濾邏輯 — paper 模式不可 emit

### E4 regression 必跑（5 項）

1. **cross-language 1e-4 浮點一致性**：FIX-2 改 PendingOrder + emit fn，跨 Python IPC 不影響
2. **SLA pressure test**：1000 intent/sec 模擬 + fully_filled rate 200/sec → SLA budget < 1ms
3. **Unit tests**：FIX-1 (3) + FIX-2 (3) + FIX-3 (3) = 9 test 全 GREEN
4. **既有 emit_entry_lineage 測試不破**：runtime_shadow_lineage_emits_complete_demo_chain / runtime_shadow_lineage_is_disabled_for_unscoped_modes
5. **既有 loop_exchange tests 不破**：emit_close_fill / apply_confirmed_fill 4 test

---

## 7. 風險表

| # | 風險 | 機率 | 影響 | Mitigation |
|---|---|---|---|---|
| 1 | hot path SLA 超標 | 低 | spike H0 latency | E2 review + E4 bench；既有 try_send 機制不阻塞 |
| 2 | LiveDemo 30s 中斷 | 100% | runtime gap | restart_all --rebuild --keep-auth 已有；deploy_ts 記錄；30min post-check window 內 |
| 3 | PendingOrder 加 3 field break 既有 test fixture | 中 | unit test fail | 全設 Option<String>=None；E4 跑 cargo test 必先驗 |
| 4 | W-D MAG-083 reviewer 看到新證據結構懵 | 中 | sign-off 延誤 | PM 在 MAG-083 audit pack template 內預設「Caveat 1+2 fix delta」章節（PA 不寫 MAG-083 audit pack） |
| 5 | 30min 短窗無 fill 觸發 | 中 | 短窗無法 verify Caveat 2 fix | 退守 60min；如仍無，等到首 fill 為止；historical evidence chain 不退步 |
| 6 | env var DEPLOY_TS cutoff 漏設 | 低 | 新指標被舊 stub 污染 | E2 grep cutoff env var；deploy SOP 必設 |
| 7 | 5 transitions 太多寫量 | 低 | spine writer 過載 | 5 × 174 chains/day = 870 row/day；spine 表規模 870/day vs 870 objects/day 同數量級，不過載 |
| 8 | partial fill 不寫 transition 漏 evidence | 低 | metric 略低估 | partial fill 寫 details.partial_fill_count 但不換 state；可選優化（不在 fix scope） |
| 9 | Spine writer mpsc channel 容量爆 | 低 | warn log + drop msg | 既有 channel 容量足；FIX-1+FIX-2 增 emit rate ~10%，遠低於 channel capacity |
| 10 | 5 stage_signal 等 object 的 to_state 命名衝突 | 低 | 未來 reviewer 困惑 | 命名穩定：`emitted` / `approved_open` / `approved` / `shadow_planned` / `shadow_filled`，與既有 ExecutionReport.status 對齊 |

### 硬邊界 + 16 原則 check

| 項 | 檢查結果 |
|---|---|
| `live_execution_allowed` | 0 觸碰（仍 fail-closed） |
| `max_retries = 0` | 0 觸碰 |
| `OPENCLAW_ALLOW_MAINNET` | 0 觸碰 |
| `live_reserved` | 0 觸碰 |
| `authorization.json` | 0 寫入（只讀） |
| 原則 1 單一寫入口 | unchanged（IntentProcessor 不動） |
| 原則 3 AI ≠ 命令 | unchanged（emit lineage 不下單） |
| 原則 4 不繞風控 | unchanged（不動 Guardian） |
| 原則 7 學習 ≠ 改寫 Live | 強化（更完整的 audit log） |
| 原則 8 交易可解釋 | **強化**（state_changes 補齊 + real-fill ExecutionReport 補齊） |
| DOC-08 §12 9 安全不變量 | 0 觸碰 |
| §三 W-C / MAG-082 row | 不改（PM 待 fix 部署後另起 commit 改） |

---

## 8. PM 待跑配對動作（不在 PA 範圍）

1. 派發 E1-W-C-FIX-1+FIX-2+FIX-3（按 §5 並行序列）
2. E2 review + E4 regression
3. Sign-off → deploy（`bash helper_scripts/restart_all.sh --rebuild --keep-auth`）+ 記錄 deploy_ts
4. 短窗驗證 30 min（運維跑 §4.3 表 + §4.3 對抗 SQL）
5. QA re-audit（QA 重跑 sign-off audit 確認 Caveat 1+2 PASS + 新指標 GREEN）
6. operator W-C → WINDOW_PASS 手動 sign-off（governance file `2026-05-11--w_c_window_pass_signoff.md`）
7. W-D MAG-083 audit pack dispatch（template 加 Caveat 1+2 fix delta 章節）
8. CLAUDE.md §三 W-C row update（CONDITIONAL_PASS → DONE post-fix）+ TODO §4.1 W-C 標 ✅
9. MAG-083 reviewer brief（不寫 MAG-083 內容）

---

## 9. 完成標準（PA 自評）

| 項 | 完成 |
|---|---|
| Caveat 1+2 RCA 確認（PG empirical + grep producer/caller verify）| ✅ |
| 3 個修復選項對比 + 推薦 + 理由 | ✅ |
| Historical 51h stub rows 處理（3 option 對比 + 推薦 a）| ✅ |
| W-D MAG-083 compatibility 證據鏈差異表 | ✅ |
| [55] healthcheck 升級 SQL + message format + PASS 判定 | ✅ |
| 短窗驗證協議 4 段（unit + 短窗 + 為何 + 風險）| ✅ |
| E1 並行任務拆分（3 task / 並行序列圖）| ✅ |
| E2 review 重點 + E4 regression 清單 | ✅ |
| 風險表 + 16 原則 + 硬邊界 + DOC-08 §12 check | ✅ |
| 不寫 feature code / 不 commit / 不啟動 E1 | ✅ |

---

## 10. 核心教訓 + 設計哲學備忘

1. **Spine state_changes 是 Spine 自己的 SM，不是 lease SM**：V064 CHECK 列舉的 6 object_type 不含 `decision_lease`；SM-02 lease 5-state 已在 `learning.lease_transitions`（V054）獨立記錄。重複層級會 chk 違規 + 治理混亂。
2. **stub row 是 by-design 不是 bug**：emit_entry_lineage 在 intent dispatch 後立刻 emit ExecutionReport 是「為了 chain 結構完整」，real-fill 是後續事件流水。修法是 **加新 row 不改舊 row**（append-only event log 哲學）。
3. **PendingOrder 不持 spine_id 是接線盲區**：FILL-CONTEXT-LINKAGE-1 已示範把 signal-time context_id 鏡射到 PendingOrder（為了 trading.fills.entry_context_id 對齊）；對 spine 應做同樣動作（order_plan_id / decision_id / verdict_id 鏡射）。E5 後續 P2 candidate：把所有 SoT id 統一 propagate 到 PendingOrder。
4. **24h vs 短窗的本質差異**：24h 證量；短窗證 wiring correctness。Caveat 修正改的是後者，不需要重等前者。
5. **healthcheck keyspace 檢查 ≠ 語意檢查**：`bad_report_quality` 只查 key existence 是設計 v1 limitation。`bad_report_value_quality` 才是真正的 evidence guard。所有 healthcheck 都應同時設計 key + value 兩層 gate。

---

**Report path**: `srv/docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`

**PA DESIGN DONE**
