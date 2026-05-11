# P1-RCA-1 F1+F2 Emergency Fix Dispatch Plan + F3/F4 Schedule

**Author**: PA (project architect)
**Date**: 2026-05-11
**Status**: DRAFT — dispatch plan only, **無業務代碼改動**（E1 才寫 IMPL）
**Working dir HEAD**: `e40b2a76`
**RCA source**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_rca1_orphan_er_missed_fill.md`（E1 RCA `ed6b2619` 已 land）

---

## §0 結論（一句總結）

**F1 + F2 必同次 deploy**：4 並行 sub-agent（E1-F1 + E1-F2 + E2 對抗 review + E4 regression test）約 4-6h workload。緊急 mitigation verdict = **不 drop V083 CHECK constraint**（理由詳 §5）。F3 / F4 分別獨立 E1 30min / 1h 排 N+1 wave。F1 + F2 vs W2 IMPL（`0e88b4a9`）/ E2 P1-1 review（`a45f0978`）/ Phase 3 V091 deploy **三者 0 file 重疊**，可立即派發不必排序。MAG-084 §5 P1-RCA-1 status 升 **BLOCKED**，W-D wave 開新 **W-E wave** 處理（不 reopen W-D）。

---

## §1 F1 — IPC close path entry_context_id fallback chain

### §1.1 真實狀態盤點（E1 RCA 文字 vs 實際 source）

E1 RCA §Fix Plan §F1 假設 IPC close path 完全 **沒設** entry_context_id。**Source 直查 corrects this**：

- `commands.rs:ipc_close_symbol` line 1108-1112（exchange path）**已經**呼叫 `paper_state.get_entry_context_id(symbol).unwrap_or("").to_string()`，但 `unwrap_or("")` 在孤兒倉 hint 平倉（line 1080-1097 fallback）時退到 **empty string**
- `commands.rs:ipc_close_symbol` line 1181-1185（paper path）同樣 `unwrap_or("")`，但 paper path 不寫 `TradingMsg::Fill`（line 1176-1177 註釋確認），不撞 V083
- `commands.rs:execute_position_close` line 747-751 同 pattern，也用 `unwrap_or("")`
- `commands.rs:ipc_close_all` line 947 同 pattern

→ 真實 root cause = **`unwrap_or("")` empty string 路徑 + 孤兒倉 hint 平倉路徑（paper_state 無倉位）**，不是「沒設」。

### §1.2 F1 spec（IMPL ~40-60min）

**改動範圍**（3 callsite + 1 helper）：

| File | Line | 改動 |
|---|---|---|
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 1108-1112 | `ipc_close_symbol` exchange path：把 `unwrap_or("")` 改為 fallback chain |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 747-751 | `execute_position_close`：同樣 fallback chain |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 943-950 | `ipc_close_all`（line 947）：同樣 fallback chain |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 1181-1185 | `ipc_close_symbol` paper path：套同樣 fallback chain（一致性，雖目前不撞 V083）|

**Fallback chain 設計**：

```rust
// F1 fallback chain: entry_context_id 必非空，避免 V083 violation
// 1. paper_state.get_entry_context_id(symbol) → Some(s) ⇒ use s（正常路徑）
// 2. None ⇒ fall back to make_context_id(em, symbol, ts_ms)（孤兒倉 / pre-V017 restored / orphan adopt）
let entry_ctx = self
    .paper_state
    .get_entry_context_id(symbol)
    .map(|s| s.to_string())
    .unwrap_or_else(|| {
        // Synthetic context_id：close fill 沒有對應 entry context（孤兒倉 hint /
        // engine restart 後 in-memory entry_context_id 丟失 / 早期 pre-V017 restored
        // position）。用 deterministic make_context_id 避免 V083 violation；
        // ML training side 透過 strategy_name="risk_close:..."、context_id LIKE 'ctx-%' AND
        // exit_reason=Some(...) 識別此類 close 不可 JOIN 回 entry。
        // 注意：not "unknown_context_id" sentinel — 仍用 make_context_id 格式
        // 保持下游 trace 一致；只是它與 entry 沒有 JOIN 對齊。
        let em = self.pipeline_kind.engine_mode_str();  // demo / live_demo / paper
        crate::tick_pipeline::on_tick_helpers::make_context_id(em, symbol, ts_ms)
    });
```

**為什麼不用 sentinel `"unknown_context_id"`**：
- E1 RCA 提出兩 option（fail-closed reject vs sentinel），PA verdict = **deterministic synthetic make_context_id**：
- (a) 不破下游 ML JOIN 期望 schema（`ctx-{em}-{symbol}-{ts}` 格式）
- (b) 不阻塞 IPC close（fail-closed reject 會卡 IPC close → 倉位繼續暴露，違反原則 5「生存 > 利潤」）
- (c) Telemetry-friendly：ML side `WHERE strategy_name LIKE 'risk_close:%' AND NOT EXISTS (SELECT 1 FROM trading.fills f2 WHERE f2.context_id = f.entry_context_id AND f2.exit_reason IS NULL)` 可 detect synthetic
- (d) 與 trading_writer 既有 `NULL on empty` 邏輯（line 486-490）不衝突，仍非空字串

**Acceptance criteria**：
1. F1 deploy 後，新生成的 IPC close fills 100% `entry_context_id` 非空 + 非 `""`
2. `observability.fills_entry_context_id_health` 24h close fills `null_ratio < 5%`（PASS gate）
3. V083 CHECK violation `chk_fills_close_has_entry_context_id_v083` log 觸發 0 次/h（baseline ~30+次/h burst window）
4. Existing test pack（commands.rs + paper_state）全 GREEN（baseline 不退化）

**Test plan**（3 unit + 1 integration）：

| Test | File | Scenario | Expected |
|---|---|---|---|
| `test_ipc_close_symbol_entry_ctx_present` | `commands.rs` 內 #[cfg(test)] | paper_state 有 entry_context_id `"ctx-demo-BTCUSDT-1000"` → IPC close | dispatch request `context_id == "ctx-demo-BTCUSDT-1000"` |
| `test_ipc_close_symbol_entry_ctx_missing_synthetic` | 同 | paper_state.set_entry_context_id 未呼叫（empty） → IPC close | dispatch request `context_id == "ctx-{em}-BTCUSDT-{ts_ms}"`（synthetic make_context_id 格式）|
| `test_ipc_close_symbol_orphan_hint_synthetic` | 同 | paper_state 無倉位 + hint_is_long=Some(true) + hint_qty=Some(0.5) | dispatch request `context_id == "ctx-{em}-BTCUSDT-{ts_ms}"`（synthetic）|
| `tests/v083_constraint_compliance.rs` (新) | `rust/openclaw_engine/tests/` | mock TradingMsg::Fill 3 case（normal + synthetic + null）走 batch_insert chunked dry-run（mock PG）| 3 case 全 PASS V083 CHECK（沒有 empty string entry_context_id）|

### §1.3 F1 E2 對抗 review 重點

1. **fallback chain ordering**：先 paper_state.get_entry_context_id（正路）→ fallback synthetic（異路），不可顛倒（顛倒會把所有正常路徑都打 synthetic）
2. **engine_mode 取得方式**：`self.pipeline_kind.engine_mode_str()` vs `pipeline.effective_engine_mode().to_string()` — 兩個都可，但 `pipeline_kind` 來自 `PipelineKind` enum 是穩定字串（paper/demo/live），`effective_engine_mode` 是 runtime substitution（live_demo / paper）；F1 用後者更精確（per 24h `engine_mode` 字段含 `live_demo`）
3. **ts_ms 一致性**：3 callsite 都需從 `openclaw_core::now_ms()` 拿，與 dispatch request 的 paper_fill_ts 同源（不可一個 now_ms 一個 event.ts_ms）
4. **make_context_id pub(crate) 暴露**：on_tick_helpers.rs:110 是 `pub(crate)`，commands.rs 同 crate 可呼叫；E2 grep `use crate::tick_pipeline::on_tick_helpers::make_context_id;` 確認 import 加齊

---

## §2 F2 — batch_insert binary-split bad-row isolation

### §2.1 真實狀態盤點

`batch_insert.rs:run_chunks` line 184-225 確認：

```rust
for chunk in rows.chunks(chunk_rows) {
    let mut qb = build_chunk(chunk);
    match qb.build().execute(pg).await {
        Ok(r) => { ... },
        Err(e) => {
            failed_chunks = failed_chunks.saturating_add(1);
            warn!(table, error, "batch_insert failed");
            // ← 整個 chunk 全部 reject，rows.skip 沒 isolation
        }
    }
}
```

**E1 RCA §Fix Plan §F2 設計正確**：binary-split recurse 是最小破壞性、可 fail-loud 同時 isolate bad row 的設計。

### §2.2 F2 spec（IMPL ~1.5-2h）

**改動範圍**：

| File | 改動 |
|---|---|
| `rust/openclaw_engine/src/database/batch_insert.rs` | (1) 加 `binary_split_isolate` 內部 async helper; (2) `run_chunks` 失敗分支呼叫 binary_split_isolate; (3) 加 `BatchInsertOutcome.bad_rows: usize` 欄位（記錄被 skip 的 single-bad-row 數）; (4) 加 5 個 unit test |

**Binary-split 演算法 spec**：

```rust
/// F2 (2026-05-11): bad-row isolation via binary-split recurse.
/// 當 chunk INSERT 失敗時，遞迴拆半重試直到定位 single bad row → log + skip。
/// 避免「1 個 bad row 拖整 chunk reject」造成持續 fill loss。
///
/// 設計考量：
/// 1. 終止條件：chunk.len() == 1 → log + skip + 回傳 (Ok, 1 bad)
/// 2. 拆半語意：mid = len / 2；左半 [0..mid] + 右半 [mid..len]
/// 3. 重試 build_chunk(half) — caller 提供的 build_chunk 必須是 stateless（已是）
/// 4. async boxed recurse：Rust async fn 直接遞迴會撞 infinite-size future，
///    用 BoxFuture (`Box::pin(async move { ... })`) 包裝
/// 5. 失敗時 log row content（PII-safe — trading data 內無 PII；fill_id +
///    symbol + strategy_name + exit_reason 足夠 trace constraint violation）
/// 6. 成功時 bookkeeping：rows_affected += sub.rows_affected
///                      bad_rows += sub.bad_rows
///                      failed_chunks 不增（因為 split 後個別 chunk 成功）
async fn binary_split_isolate<T, F>(
    pg: &PgPool,
    pool: &DbPool,
    table: &str,
    rows: &[T],
    build_chunk: &mut F,
    depth: usize,
) -> BatchInsertOutcome
where
    T: std::fmt::Debug,  // for bad-row log（caller 已對 T 滿足，trading.fills row 是 TradingMsg::Fill enum 有 Debug derive）
    F: for<'a> FnMut(&'a [T]) -> QueryBuilder<'a, Postgres>,
{
    if rows.is_empty() {
        return BatchInsertOutcome { rows_affected: 0, failed_chunks: 0, bad_rows: 0 };
    }
    if rows.len() == 1 {
        // Single row — retry one more time; if still fail, log + skip。
        // 單行 — 再試一次；仍失敗則 log + skip 計入 bad_rows。
        let mut qb = build_chunk(rows);
        match qb.build().execute(pg).await {
            Ok(r) => BatchInsertOutcome {
                rows_affected: r.rows_affected(),
                failed_chunks: 0,
                bad_rows: 0,
            },
            Err(e) => {
                let _ = pool.record_failure();
                warn!(
                    target: "batch_insert_bad_row_isolated",
                    table = table,
                    error = %e,
                    row_debug = ?rows[0],   // T: Debug 觸發 trading.fills row dump
                    depth = depth,
                    "F2 bad-row isolated and skipped after binary-split / F2 binary-split 定位 bad row 並跳過"
                );
                BatchInsertOutcome { rows_affected: 0, failed_chunks: 0, bad_rows: 1 }
            }
        }
    } else {
        let mid = rows.len() / 2;
        let left = &rows[..mid];
        let right = &rows[mid..];
        // 先試左半
        let mut left_qb = build_chunk(left);
        let left_outcome = match left_qb.build().execute(pg).await {
            Ok(r) => {
                pool.record_success();
                BatchInsertOutcome { rows_affected: r.rows_affected(), failed_chunks: 0, bad_rows: 0 }
            }
            Err(_) => {
                Box::pin(binary_split_isolate(pg, pool, table, left, build_chunk, depth + 1)).await
            }
        };
        // 再試右半
        let mut right_qb = build_chunk(right);
        let right_outcome = match right_qb.build().execute(pg).await {
            Ok(r) => {
                pool.record_success();
                BatchInsertOutcome { rows_affected: r.rows_affected(), failed_chunks: 0, bad_rows: 0 }
            }
            Err(_) => {
                Box::pin(binary_split_isolate(pg, pool, table, right, build_chunk, depth + 1)).await
            }
        };
        BatchInsertOutcome {
            rows_affected: left_outcome.rows_affected.saturating_add(right_outcome.rows_affected),
            failed_chunks: 0,  // binary_split 內已 isolated；外層 run_chunks 不再計 failed_chunks
            bad_rows: left_outcome.bad_rows.saturating_add(right_outcome.bad_rows),
        }
    }
}
```

**`run_chunks` 失敗分支呼叫**：

```rust
async fn run_chunks<T, F>(...) -> BatchInsertOutcome
where
    T: std::fmt::Debug,  // NEW: 為 binary_split_isolate 的 row_debug log
    F: ...,
{
    let mut total_affected: u64 = 0;
    let mut failed_chunks: usize = 0;
    let mut bad_rows: usize = 0;  // NEW
    for chunk in rows.chunks(chunk_rows) {
        let mut qb = build_chunk(chunk);
        match qb.build().execute(pg).await {
            Ok(r) => { ... },
            Err(e) => {
                warn!(
                    target: "batch_insert_chunk_failed_invoking_split",
                    table = table,
                    error = %e,
                    chunk_size = chunk.len(),
                    "batch_insert chunk failed — invoking binary-split isolation / 批量插入失敗 — 啟動 binary-split 隔離"
                );
                let sub = Box::pin(binary_split_isolate(pg, pool, table, chunk, build_chunk, 0)).await;
                total_affected = total_affected.saturating_add(sub.rows_affected);
                bad_rows = bad_rows.saturating_add(sub.bad_rows);
                // failed_chunks 不增（已 split 處理）
            }
        }
    }
    BatchInsertOutcome { rows_affected: total_affected, failed_chunks, bad_rows }
}
```

**`BatchInsertOutcome` 加欄位**：

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BatchInsertOutcome {
    pub rows_affected: u64,
    pub failed_chunks: usize,
    pub bad_rows: usize,  // NEW: F2 binary-split isolation 後跳過的 single-bad-row 數
}

impl BatchInsertOutcome {
    pub fn all_ok(&self) -> bool {
        self.failed_chunks == 0 && self.bad_rows == 0
    }
    pub fn has_skipped_rows(&self) -> bool {  // NEW
        self.bad_rows > 0
    }
}
```

**注意**：`T: Debug` bound 對 trading.fills writer 是滿足的（`TradingMsg::Fill` 有 `Debug` derive，per `database/messages.rs`）；對 batch_insert 其他 caller（market_writer ticker / spine writer）也都用 derive Debug 的 row type。E2 必查所有 batch_insert callsite。

### §2.3 F2 Acceptance criteria

1. V083 violation 不再阻塞同 chunk 其他 row INSERT
2. 模擬 chunk 含 1 bad row + 121 good row → bad row skip + 121 good row INSERT 成功
3. trading_writer pending_rows 從 6 orphan + 2 IPC close = 8 row reject 變成 2 IPC close row skip + 6 orphan + 後續 row 全寫入
4. `binary_split_isolate` 遞迴深度 ≤ log2(chunk_rows) = ~7 for 122 row chunk（max stack frame 風險可控）
5. `cargo test --release -p openclaw_engine --lib batch_insert` 全 GREEN

### §2.4 F2 Test plan（5 unit + 1 integration）

| Test | Scenario | Expected |
|---|---|---|
| `binary_split_all_good_chunk` | 4-row chunk 全部 good | (Ok, 4 affected, 0 bad)，不觸 split path |
| `binary_split_single_bad_mid_chunk` | 8-row chunk 中第 3 row 違 CHECK（mock）| (Ok, 7 affected, 1 bad)，log target `batch_insert_bad_row_isolated` 觸發 1 次 |
| `binary_split_multi_bad_rows` | 16-row chunk 第 3+11 row 違 CHECK | (Ok, 14 affected, 2 bad)，log target 觸發 2 次 |
| `binary_split_zero_row_edge` | 0-row chunk | (Ok, 0 affected, 0 bad)，不觸 split |
| `binary_split_recurse_depth_safe` | 128-row chunk 1 bad row | depth ≤ 7，stack 不爆 |
| `tests/v083_chunk_isolation_integration.rs`（新）| mock PG schema with V083 CHECK + 122-row trading.fills chunk 含 2 IPC close empty entry_context_id | 2 row skip + 120 row 寫入；`pending_rows` 從 2 變 0 next flush |

### §2.5 F2 E2 對抗 review 重點

1. **`Box::pin` recurse pattern**：async fn 直接遞迴 → infinite-size future compile error；必用 `Box::pin(async move {...})`；E2 grep `Box::pin(binary_split_isolate` 確認
2. **stack depth bounded**：max depth = ceil(log2(chunk_rows))；chunk_rows ≤ MAX_CHUNK_ROWS = 10_000 → depth ≤ 14；safe
3. **`T: Debug` bound 不破現有 caller**：grep `batch_insert_chunked` callsite，每個 T 必有 Debug；market_writer / trading_writer / spine_writer 已 verify
4. **`pool.record_failure()` 計帳邏輯**：原 run_chunks 每失敗 +1 record_failure；F2 後改為「整 chunk fail → invoke split」+「split 內 single bad row → +1 record_failure」；E2 必確認 record_failure count 對齊（單 bad row 也算 1 failure，不 zero out 健康閾值）
5. **log content security**：`row_debug = ?rows[0]` debug-format TradingMsg::Fill — 含 fill_id / symbol / strategy_name / exit_reason，PII-safe（trading data 沒 PII），但 E3 必查不洩 API key（既有 TradingMsg::Fill 不含 key 已驗）

---

## §3 F1 + F2 必同次 deploy（不可分次）

### §3.1 為何同次 deploy（兩面理由）

**Scenario A**：F1 single deploy + F2 沒 deploy
- F1 修了 IPC close path，所有 IPC close fills 100% 帶 entry_context_id ✓
- 但 batch_insert 仍無 bad-row isolation
- 風險：**其他** writer path（strategy close / risk_close:hard_stop / risk_close:trailing_stop / risk_close:time_stop / orphan adopt path）任一 producer 漏 entry_context_id → 仍會撞 V083 reject 整 chunk
- 7 個 close path（grep `risk_close:`）只修了 IPC close 1 個，其他 6 個（hard_stop / trailing_stop / time_stop / partial_reduce / fast_track / strategy_close)未必 cover
- → 同樣 fill loss 風險未消除

**Scenario B**：F2 single deploy + F1 沒 deploy
- F2 isolate bad rows，2 IPC close row skip + 6 orphan + 其他 row 全寫入 ✓
- 但 F1 仍 IPC close 漏 entry_context_id → 持續 generate bad rows
- 風險：每次 IPC close 都觸發 `batch_insert_bad_row_isolated` WARN log + `bad_rows` counter 累積
- 觀測噪音：72h 內 hundreds of bad-row log，confuse healthcheck signal-to-noise
- Telemetry pollution：`observability.fills_entry_context_id_health.null_ratio` 持續 ≥ 30% FAIL

**結論**：F1 + F2 必同次 deploy（**單一 restart_all --rebuild 同次生效**），無 single deploy intermediate state。

### §3.2 Deploy sequence（PM 拍板執行）

1. PM 派 4 並行 sub-agent（E1-F1 + E1-F2 + E2 對抗 review + E4 regression test）
2. E1-F1 + E1-F2 並行 commit（兩個 sub-agent 改不同 file：`commands.rs` vs `batch_insert.rs`，0 file 重疊）
3. E2 對抗 review 兩個 IMPL（讀 commit hash，給 GREEN/RED verdict）
4. E4 regression test：`cargo test --release -p openclaw_engine --lib` + `--lib batch_insert` + `--lib commands` 全 GREEN
5. PM sign-off + ssh trade-core `cd ~/BybitOpenClaw/srv && git pull --ff-only && bash helper_scripts/restart_all.sh --rebuild --keep-auth`
6. Deploy verify（30min 觀察窗口）：
   - 6h 內 V083 CHECK violation 計數 0（baseline ~30+/h burst window）
   - `observability.fills_entry_context_id_health.null_ratio` 24h < 5%
   - `pending_rows` 觀測平均 < 5（baseline burst window 持續 100+）
   - `batch_insert_bad_row_isolated` log target 觸發 < 5次/h（若大量觸發 → F1 fallback chain 仍漏 path，回滾）

---

## §4 緊急 mitigation 評估（operator 拍板）

### §4.1 兩 option 對比

| Option | 利 | 弊 |
|---|---|---|
| **A — DROP V083 CHECK 直到 F1+F2 deploy** | 立即停止 fill loss（burst window 風險消除） | 放寬 W-AUDIT-4b-M2 設計目標；ML training pool 重新進 bad rows；observability.fills_entry_context_id_health view 失效 |
| **B — 不 drop，accept 持續 fill loss until F1+F2 deploy** | 維持 W-AUDIT-4b-M2 設計強度；ML training pool 仍 clean | 4-6h workload 期間仍可能 burst fill loss（per RCA window 3min 26s with 0 trading.fills row）|

### §4.2 PA verdict = **Option B（不 drop V083）**

**理由**：

1. **時間窗口短**：F1+F2 4-6h workload + 1h E2 + 1h E4 + 1h deploy verify = total ~7-9h；vs DROP CHECK 後再 reapply NOT VALID 也要 1-2h（需新 V### migration + cleanup history rows）
2. **burst window 罕見**：RCA 證據顯示 burst 集中在 engine restart cascade + V083 deploy_ts 後 72-73min，不是常態（24h baseline 觀察是 normal）
3. **ML training pool 保護**：W-AUDIT-4b-M2 V083 是為 protect attribution chain；DROP 後 1-2 天 ML training pool 重新進 stub rows → attribution_chain_ok ratio drop → 影響後續 alpha decision
4. **DROP 後再 reapply 高風險**：需要新 V093 migration ADD CONSTRAINT NOT VALID + 等下次 deploy；中間若有 dirty rows 進入 → VALIDATE 永遠 fail
5. **F1 fallback chain 已 fail-soft**：即使 F2 deploy 短暫滯後，F1 deploy 後 IPC close fills 100% non-empty → V083 violation 自動消除

**Option A trigger 條件**（PA 提出 escalation gate）：若 F1+F2 IMPL 撞硬阻塞 ≥ 24h 不能 deploy，則 operator escalate 到 Option A（DROP + 加 V093 reapply schedule）。當前無此情況。

---

## §5 F3 / F4 Schedule（P1 獨立 ticket，不阻 F1+F2 emergency）

### §5.1 F3 — `fill-writer-entry-context-missing` WARN 文案修正 + 升 ERROR level

**Scope**: `rust/openclaw_engine/src/database/trading_writer.rs:406-414`（line range 已 grep verify）

**改動**（~10 LOC）：

```rust
// BEFORE (line 406-414)
warn!(
    target: "fill-writer-entry-context-missing",
    close_fills_missing_entry_ctx = missing_entry_ctx,
    batch_total = buf.len(),
    sample = ?sample,
    "W-AUDIT-4b-M2: close fills with empty entry_context_id detected — \
     rows still INSERT (fail-soft); cron backfill will reconcile / \
     偵測到 close fill 缺 entry_context_id — 仍寫入並由 cron 回填補齊"
);

// AFTER F3
error!(
    target: "fill-writer-entry-context-missing",
    close_fills_missing_entry_ctx = missing_entry_ctx,
    batch_total = buf.len(),
    sample = ?sample,
    "F3 (2026-05-1X): close fills with empty entry_context_id detected — \
     batch INSERT will be REJECTED by V083 CHECK constraint until producer-side \
     fix lands (F1). With F2 binary-split isolation, individual bad rows are \
     skipped (logged via batch_insert_bad_row_isolated). Cron backfill cannot \
     reconcile — producer path must populate entry_context_id at emit time. / \
     偵測到 close fill 缺 entry_context_id — 在 producer 端修復（F1）之前 \
     batch INSERT 將被 V083 CHECK 拒絕；F2 binary-split 已隔離單筆 bad row。 \
     Cron backfill 無法補救 — producer 路徑必須在 emit 時填入 entry_context_id。"
);
```

**Workload**: single E1 30min（純文字 + log level + import `tracing::error` 加齊）

**Acceptance**: log level = ERROR + 文案精確（不再說 fail-soft / cron reconcile）；test：mock 觸發路徑驗 ERROR log

**E2 review 重點**：
- ERROR vs WARN 邊界 — ERROR 是 user-visible alert，WARN 是 dev observation；F3 此處應 ERROR（V083 違反是 producer bug + data loss potential）
- 不破既有 grep target name `fill-writer-entry-context-missing`（下游 alert SQL 可能 grep 此 target）

**Schedule**: N+1 wave，獨立 ticket，不阻 F1+F2

### §5.2 F4 — PostOnly partial vs Bybit Filled reconciliation

**Scope**: `rust/openclaw_engine/src/event_consumer/loop_exchange.rs:357+`（`OrderUpdate(status=Filled)` 分支）

**改動**（~30-40 LOC）：

在 `loop_exchange.rs:365-460` `OrderUpdate` 分支 `status == "Cancelled" || status == "Rejected"` 條件之外，加新 branch：

```rust
// F4 (2026-05-1X): PostOnly partial 殘量 reconciliation
// 當 Bybit OrderUpdate 報 status=Filled 但 engine 端 PendingOrder cum_filled_qty < qty * 0.999
// （fully_filled gate 未過），補一筆 synthetic apply_confirmed_fill 把殘量結清。
// 避免 emit_fill_completion_lineage 從未觸發 → orphan ER missing。
//
// 設計考量：
// 1. 僅 status==Filled + PendingOrder 存在 + cum_filled_qty < qty * 0.999 觸發
// 2. 殘量 residual_qty = qty - cum_filled_qty；price = po.avg_fill_price 或 event last_price
// 3. 標記 strategy_name 為 "{po.strategy}:bybit_reconcile" 區分 synthetic
// 4. idempotency：用 PendingOrder.bybit_reconcile_done flag 或 exchange_exec_id="bybit-{order_link_id}-reconcile" 防止 double-emit
} else if status == "Filled" {
    if let Some(po) = state.pending_orders.get_mut(&order.order_link_id) {
        let fully_filled_gate = po.cum_filled_qty >= po.qty * 0.999;
        if !fully_filled_gate && !po.bybit_reconcile_done {
            let residual_qty = po.qty - po.cum_filled_qty;
            let recon_price = if po.cum_filled_qty > 0.0 {
                po.avg_fill_price  // 用既有 avg 殘量補
            } else {
                event.last_price  // 完全沒成交過 → 用 event price（罕見 edge case）
            };
            // 同 fully_filled branch 的 emit + apply_confirmed_fill
            // pipeline.apply_confirmed_fill(...)
            // crate::agent_spine::runtime_shadow::emit_fill_completion_lineage(...)
            po.bybit_reconcile_done = true;
            tracing::warn!(
                order_link_id = %order.order_link_id,
                symbol = %order.symbol,
                residual_qty = residual_qty,
                cum_filled_qty = po.cum_filled_qty,
                total_qty = po.qty,
                "F4: Bybit reports Filled but engine cum < 0.999 — reconcile residual \
                 / F4: Bybit 報 Filled 但 engine 端 < 0.999 — 補殘量"
            );
            state.pending_orders.remove(&order.order_link_id);
        }
    }
}
```

需要在 `PendingOrder` struct（`event_consumer/state.rs` 或類似）加 `bybit_reconcile_done: bool` 欄位（default false）。

**Workload**: single E1 1h（IMPL + 2 unit test + 1 manual demo Bybit verify）

**Acceptance**:
1. mock OrderUpdate(Filled) 觸發 reconcile path → trading.fills 寫成功 + ER emit
2. double-emit 防護：第二次同 order_link_id status=Filled → skip（po 已從 pending_orders.remove 不再觸發）
3. 不破現有 fully_filled path（fully_filled_gate=true 走原路）

**E2 review 重點**：
- idempotency key 設計：bybit_reconcile_done flag vs exchange_exec_id 防止 emit_fill_completion_lineage double-emit；E2 必確認 ER stub_report_id 不會被重用
- `po.avg_fill_price` 計算：grep `event_consumer/state.rs::PendingOrder` 結構 verify 有此欄位
- 與 W-C Caveat 2 修復（fully_filled spine 4 id emit）對齊 — F4 synthetic reconcile 要 emit 還是 short-circuit？PA 建議 emit（with reconcile tag in stub_report_id）

**Schedule**: N+1 或 N+2 wave，獨立 ticket，不阻 F1+F2

---

## §6 跨 Wave 衝突檢查

### §6.1 F1+F2 vs W2 IMPL（`0e88b4a9` dispatch plan）

| 比對軸 | F1+F2 | W2 IMPL | 結論 |
|---|---|---|---|
| File scope | `commands.rs` + `batch_insert.rs` | `panel/btc_lead_lag.rs` + `passive_wait_healthcheck.py` + `w2_paper_edge_report.py` + new SQL + `main.rs` (line 977-996) | **0 file 重疊** |
| sub-agent | E1-F1 / E1-F2 | E1-IMPL-1/2/3/4/5 | **0 sub-agent 重疊**（兩組獨立派） |
| deploy timing | F1+F2 同次 restart_all --rebuild | W2 IMPL D+5 同次 restart_all | **不衝突**（F1+F2 deploy 先 / W2 後；或 W2 先 / F1+F2 後均可） |
| schema migration | F2 改 batch_insert outcome struct（內部 type，非 PG schema）| V088 panel.btc_lead_lag_panel 已 land | **不衝突** |

### §6.2 F1+F2 vs E2 P1-1 review（`a45f0978` in-flight）

| 比對軸 | F1+F2 | E2 P1-1 | 結論 |
|---|---|---|---|
| File scope | `commands.rs` + `batch_insert.rs` | spine_ids / runtime_shadow / step_4_5_dispatch（READ-ONLY review） | **0 file 重疊** |
| operation type | E1 IMPL（write） | E2 review（READ-ONLY） | **不衝突** |
| 結論 | 完全並行可能 |

### §6.3 F1+F2 vs Phase 3 V091 deploy（D+1 evening + D+2 ALTER VALIDATE）

| 比對軸 | F1+F2 | V091 | 結論 |
|---|---|---|---|
| Schema scope | F2 改 batch_insert outcome struct（Rust type）；F1 改 commands.rs 邏輯（無 schema 動） | V091 `learning.decision_features.reject_reason_code` + `close_reason_code` row-level CHECK NOT VALID | **0 schema 重疊**（V083 trading.fills vs V091 learning.decision_features 不同 schema namespace） |
| Migration order | F2 不寫 V### migration；F1 不寫 V### migration | V091 已 land migration file `V091__decision_features_reject_close_mutex_check.sql` | **F1+F2 deploy 先 / V091 ALTER VALIDATE 後 是優選**（V091 ALTER VALIDATE 鎖 learning.decision_features 期間 F2 batch_insert 對 trading.fills 無影響） |
| Producer-side fix | F1 是 trading.fills 的 producer-side fix | V091 ALTER VALIDATE 不需 producer 改動（per W-AUDIT-4b 已 producer-side 預先寫 reject_reason_code / close_reason_code） | **不衝突** |

**PA 建議 deploy 順序**：F1+F2 先 deploy（緊急止血）→ V091 ALTER VALIDATE 後 deploy（per W-D 排程）。

### §6.4 F1+F2 vs 其他 active wave

| Wave | 改動範圍 | 衝突 |
|---|---|---|
| W6 RFC verdict + V086 IMPL | learning.decision_features + reject/close reason enum | 0 重疊（F1+F2 不動 governance namespace） |
| W7-2/4/5 strategy cross-strategy desync | strategy_impl.rs / agent_spine | 0 重疊（F1+F2 不動 strategy_impl.rs） |
| W3 Stage 1 cohort | governance.canary_stage_log | 0 重疊 |
| W4 RouterLeaseGuard Drop test | routing/lease_guard.rs | 0 重疊 |
| W5 三 P1 IMPL（V089/V090）| governance namespace | 0 重疊 |
| W1 funding panel staleness fix（已 deploy `4b267dff`）| panel_aggregator/funding_curve.rs | 0 重疊 |

**全 wave verdict**：F1+F2 vs 11 active wave **0 file 重疊**；可立即派發不必排序。

---

## §7 4 並行 Sub-Agent 拆派建議

| Sub-agent | Scope | Workload | 動的 file | 並行/序列 |
|---|---|---|---|---|
| **E1-F1** | IPC close path entry_context_id fallback chain | 40-60min | `rust/openclaw_engine/src/tick_pipeline/commands.rs`（4 callsite 改 + 3 unit test） | 完全並行（與 E1-F2 不撞檔） |
| **E1-F2** | batch_insert binary-split bad-row isolation | 1.5-2h | `rust/openclaw_engine/src/database/batch_insert.rs`（加 binary_split_isolate helper + 修 run_chunks + 5 unit test） + `tests/v083_chunk_isolation_integration.rs` 新檔 | 完全並行（與 E1-F1 不撞檔） |
| **E2 對抗 review** | F1+F2 IMPL 對抗 review | 1h | READ-ONLY review on F1+F2 commit hash | 需等 F1+F2 push 後（rebase 2 commit） |
| **E4 regression test** | cargo test baseline 不退化 + V083 violation 0 alarm + integration test | 1h | cargo test --release -p openclaw_engine --lib + --lib batch_insert + --lib commands + tests/ integration | 需等 F1+F2 push 後 |

### §7.1 Dispatch sequence（PM 執行）

**T+0**：
- PM 派 E1-F1 + E1-F2 並行（兩個 sub-agent 同時開工）

**T+2-3h**（F1 + F2 push 完成後）：
- PM 派 E2 對抗 review（讀 F1+F2 commit hash）
- PM 派 E4 regression test（cargo test 全 baseline）

**T+4-5h**（E2 + E4 GREEN gate 後）：
- PM 整 sign-off pack
- ssh trade-core git pull + restart_all --rebuild --keep-auth
- 30min deploy verify（V083 violation 0 / fills_entry_context_id_health PASS / pending_rows < 5）

**T+5-7h**：F1+F2 deploy 完成 + verification 觀察 30min PASS → 收口

**T+1d (N+1)**：F3 30min IMPL + 30min E2/E4 + ship
**T+2d (N+1 or N+2)**：F4 1h IMPL + 1h E2/E4 + 1h manual demo Bybit verify + ship

---

## §8 MAG-084 §5 P1-RCA-1 Status Update 建議

### §8.1 PA verdict

**§5 P1-RCA-1 status 升 BLOCKED**（per E1 RCA verdict SYSTEMIC）：

- 原 MAG-084 §5 P1-RCA-1 status：`P1 follow-up`（QA `388e04b2` 判 non-systemic）
- 修正 status：**`BLOCKED until F1+F2 deploy + 24h verify`**
- 理由：E1 RCA 已 confirm 4-bug chain + V083 CHECK reject 整 hyperchunk + fill loss 3min 26s window；non-systemic 判定錯誤

### §8.2 W-D wave reopen vs 開新 W-E wave

**PA 建議 = 開新 W-E wave**（不 reopen W-D）：

**理由**：

1. **W-D 已 closed**（MAG-083/084 三角 audit sign-off `2026-05-11--w_d_mag084_signoff.md`）；reopen 會破 closure semantic
2. **P1-RCA-1 root cause 跨 wave**：F1 改 commands.rs（tick_pipeline）+ F2 改 batch_insert.rs（database）→ scope 比 W-D 原 W-C Stage 2 (Agent Spine shadow lineage) 廣
3. **緊急性差異**：W-E wave **emergency** classification（P0 fill loss）vs W-D wave 是 evidence collection；運作 SLA 不同
4. **歷史可追溯**：W-D 收口 caveat 3 deferred + Caveat 1+2 fix 已歷史化；W-E 開新 wave 更清楚記載 RCA → fix plan → deploy → verify chain

**建議 W-E wave structure**：

| Track | 內容 | Owner | Workload |
|---|---|---|---|
| W-E-T1 | F1 IPC close entry_context_id fallback chain | E1-F1 | 40-60min |
| W-E-T2 | F2 batch_insert binary-split bad-row isolation | E1-F2 | 1.5-2h |
| W-E-T3 | F1+F2 同次 deploy + 30min verify | PM (operator approve) | 1h |
| W-E-T4 | F3 WARN→ERROR + 文案修正 | E1-F3 | 30min |
| W-E-T5 | F4 PostOnly partial reconciliation | E1-F4 | 1h |
| W-E-T6 | MAG-085 sign-off（W-E wave closure + 24h verify）| PM | 1h |

**最終 verdict 留 operator 拍板**（W-D reopen vs W-E 新 wave）。

---

## §9 PA E2 重點審查 3 點（per profile.md 標準輸出）

### §9.1 fallback chain 不可顛倒 + ts_ms 一致性

F1 改 4 callsite 必統一 pattern：
```rust
let entry_ctx = self.paper_state.get_entry_context_id(symbol)
    .map(|s| s.to_string())
    .unwrap_or_else(|| make_context_id(em, symbol, ts_ms));
```
- 正路（has entry_ctx）優先；fallback synthetic 在後
- `em` 取 `pipeline.effective_engine_mode()`（不是 `pipeline_kind`，後者沒區分 live vs live_demo）
- `ts_ms` 與 dispatch request `paper_fill_ts` 同源

### §9.2 Binary-split recurse safety + bookkeeping correctness

F2 改 batch_insert 必驗：
- `Box::pin(async move {...})` 包 recurse（async fn 直接遞迴 → infinite-size future）
- `T: Debug` bound 對所有 caller verify（market_writer / trading_writer / spine_writer 都 derive Debug）
- `pool.record_failure()` count 對齊：single bad row → +1 failure；其他 split 內成功 → 不破舊 health 閾值
- `BatchInsertOutcome.bad_rows` 新欄位下游不破（grep `all_ok` callsite）
- failed_chunks vs bad_rows 語意分離：failed_chunks 是 hard 失敗（PG unreachable / connection lost），bad_rows 是 isolated single bad row；不可混算

### §9.3 16 原則 + DOC-08 §12 + 硬邊界 5 項 0 觸碰

F1+F2 對照 CLAUDE.md §二 16 原則：

| 原則 | F1+F2 影響 | verdict |
|---|---|---|
| 1 單一寫入口 | 不動 IntentProcessor / submit_intent | ✓ |
| 3 AI≠命令 | 不動 Decision Lease | ✓ |
| 4 不繞風控 | 不動 Guardian / risk_envelope | ✓ |
| 5 生存>利潤 | F1 fallback chain 確保 IPC close 不被 V083 reject → 倉位可平 → 強化生存原則 | ✓ 強化 |
| 6 失敗默認收縮 | F2 bad-row isolation 是 fail-soft skip + log，不擴大失敗範圍 | ✓ |
| 7 學習 ≠ 改寫 Live | F1 synthetic context_id 標記下游 ML training 可識別 | ✓ |
| 8 交易可解釋 | F1 synthetic context_id deterministic `ctx-{em}-{symbol}-{ts}` 可追溯 | ✓ |
| 9 災難保護 | 不動 hard_stop / liquidation_buffer | ✓ |
| 11 Agent 自主 | 不破 P0/P1 硬邊界 | ✓ |
| 12 持續進化 | F2 bad-row log 提供 schema drift signal | ✓ 強化 |

DOC-08 §12 安全不變量 9 條 0 觸碰（不動 lease / authorization / audit / reconciler / mainnet env / Bybit retCode / fail-closed 路徑）。

硬邊界 5 項（CLAUDE.md §四）0 觸碰（不動 live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / decision_lease_emitted / authorization.json）。

**Verdict**: F1+F2 屬 **A 級** compliance — 強化原則 5/6/8/12，零硬邊界觸碰。

---

## §10 一句總結

**F1（IPC close entry_context_id fallback chain，40-60min ~15 LOC + 3 test）+ F2（batch_insert binary-split bad-row isolation，1.5-2h ~50 LOC + 5 test + 1 integration）必同次 restart_all --rebuild 部署。緊急 mitigation = 不 drop V083 CHECK（F1 fallback chain 已 fail-soft，4-6h workload 內 IPC close 自動 100% 非空，DROP CHECK 反而破 W-AUDIT-4b-M2 設計）。F3 / F4 獨立 P1 ticket N+1 / N+2 schedule。F1+F2 vs W2 IMPL / E2 P1-1 review / V091 deploy 0 file 重疊可立即派發。MAG-084 §5 P1-RCA-1 status 升 BLOCKED，建議開新 W-E wave 處理（不 reopen W-D）。16 原則 + DOC-08 §12 + 硬邊界 5 項 0 觸碰，屬 A 級 compliance 強化原則 5/6/8/12。**

---

**Report end. PA dispatch plan ready. PM 派 E1-F1 + E1-F2 並行（T+0 同時起）→ E2 對抗 + E4 regression（T+2-3h）→ 同次 restart_all --rebuild deploy（T+4-5h）→ 30min verify（T+5-6h）→ F3/F4 N+1 schedule。**

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_rca1_f1_f2_emergency_fix_plan.md
