# W-AUDIT-4b-M2 IMPL — fill writer entry_context_id INSERT trigger + V083

**Agent**: E1-B Day 5-7 W2
**Date**: 2026-05-09
**Branch**: main
**W1 HEAD baseline**: `26b7186d` (e4-regression: Sprint N+0 second-pass PASS)
**Status**: IMPL DONE — 待 E2 review → E4 regression → PM 統一 push

## 任務摘要

W-AUDIT-4b-M2 是 ML 三斷層第二層（M1=producer / M2=fill writer / M3=negative
label）。M1 (E1-E `4a90966a`) 已 land producer side decision_features intent-only
emit；M2 是 **fill writer side enforcement + V083 NOT VALID CHECK + cron
backfill 三件套**。

### Root Cause（per task spec MIT 2026-05-09 PG 直查）
24h 175 fills 中只 67 個有 entry_context_id (38%)，致 edge_label_backfill
EXISTS join 99% 失敗 → `learning.decision_features.label_filled_at` 大量 NULL
→ ML training pool 缺正樣本 → attribution_chain_ok ratio 不可恢復。

具體分布：
- **ENTRY fills (open path)**：設計上 `entry_context_id = NULL`（it IS the entry，
  edge_label_backfill SQL 用 `WHERE entry_context_id IS NULL  -- entry row` 識別）。
  這是 BY DESIGN，**不需要修**。
- **CLOSE fills**：應該攜 entry's context_id 但偶有空，原因：
  - paper_state.entry_context_id 在 engine restart 後丟（in-memory）
  - orphan adopt / 被外部 pipeline 開倉、未經 4 個 set_entry_context_id
    call site 之一
  - 部分 IPC close path 漏設

### 修復策略（per task spec 選 Rust writer-side enforcement 路線）
1. **Rust writer-side enforcement**（trading_writer.rs::flush_fills）：在 batch
   INSERT 前掃 buffer，count close fills (`exit_reason.is_some()`) 缺
   `entry_context_id` 的列 → emit aggregated WARN log（含 first violation
   sample）+ 仍 INSERT（fail-soft，避免 producer 卡死）。
2. **V083 NOT VALID CHECK**：對 new INSERT 強制
   `exit_reason IS NULL OR entry_context_id IS NOT NULL`；NOT VALID 不掃
   historical row（保 175 行歷史中 NULL close fills 不被 break）。M2 觀察期
   7d 後若全綠可 ALTER VALIDATE CONSTRAINT 強化歷史。
3. **Backfill cron 升級**：`edge_label_backfill_cron.sh` 加 Step 1（fill
   entry_context_id 回填）必先於 Step 2 label backfill。Step 1 邏輯：對
   close fill 缺 entry_context_id 的列，依 same `(strategy_name, engine_mode,
   symbol, opposite-side)` 找最近 entry fill 的 context_id 補入。
4. **observability view**：V083 加 `observability.fills_entry_context_id_health`
   24h close fills NULL ratio 監控（PA spec 95% target）。

## 修改清單

| 路徑 | 動作 | LOC |
|---|---|---|
| `sql/migrations/V083__fills_entry_context_id_close_check.sql` | 新建 | +287 |
| `rust/openclaw_engine/src/database/trading_writer.rs` | 加 helper + WARN log + 7 unit test | +250 |
| `program_code/ml_training/edge_label_backfill.py` | 加 `backfill_fill_entry_context_id()` + CLI flag `--backfill-fill-entry-context-id` | +200 |
| `program_code/ml_training/tests/test_edge_label_backfill.py` | 加 `TestBackfillFillEntryContextId` class（12 test）| +247 |
| `helper_scripts/cron/edge_label_backfill_cron.sh` | MODULE_NOTE 升級 + Step 1 wire | +57 / -6 |

**5 files changed / +1035 insertions / -6 deletions**（不含既有 V082/V083
guard 模板抄錄）

## 關鍵 diff

### V083 migration 核心（NOT VALID CHECK）
```sql
ALTER TABLE trading.fills
    ADD CONSTRAINT chk_fills_close_has_entry_context_id_v083
    CHECK (exit_reason IS NULL OR entry_context_id IS NOT NULL)
    NOT VALID;
```

### V083 hot-path partial index（backfill cron 加速）
```sql
CREATE INDEX IF NOT EXISTS idx_fills_entry_lookup_v083
    ON trading.fills (strategy_name, engine_mode, symbol, side, ts)
    WHERE entry_context_id IS NULL;
```

### V083 telemetry view（24h NULL ratio 監控）
```sql
CREATE OR REPLACE VIEW observability.fills_entry_context_id_health AS
WITH window_24h AS (
    SELECT * FROM trading.fills
    WHERE ts > NOW() - INTERVAL '24 hours'
      AND exit_reason IS NOT NULL  -- close fills only
      AND (strategy_name IS NULL OR strategy_name NOT LIKE 'unattributed:%')
)
SELECT engine_mode, COUNT(*), COUNT(entry_context_id),
       COUNT(*) FILTER (WHERE entry_context_id IS NULL) AS null_entry_ctx,
       1.0 - (COUNT(entry_context_id)::DOUBLE PRECISION / COUNT(*)) AS null_ratio
FROM window_24h GROUP BY engine_mode;
```

### Rust writer-side enforcement（trading_writer.rs）
```rust
fn count_close_fills_missing_entry_context_id(buf: &[TradingMsg]) -> usize {
    buf.iter().filter(|msg| {
        if let TradingMsg::Fill {
            exit_reason, entry_context_id, strategy_name, ..
        } = msg {
            let is_close = exit_reason.is_some();
            let is_audit = strategy_name.starts_with("unattributed:");
            is_close && entry_context_id.is_empty() && !is_audit
        } else { false }
    }).count()
}

// In flush_fills(buf):
let missing_entry_ctx = count_close_fills_missing_entry_context_id(buf);
if missing_entry_ctx > 0 {
    let sample = buf.iter().find_map(|msg| { /* ... */ });
    warn!(
        target: "fill-writer-entry-context-missing",
        close_fills_missing_entry_ctx = missing_entry_ctx,
        batch_total = buf.len(),
        sample = ?sample,
        "W-AUDIT-4b-M2: close fills with empty entry_context_id detected — \
         rows still INSERT (fail-soft); cron backfill will reconcile / \
         偵測到 close fill 缺 entry_context_id — 仍寫入並由 cron 回填補齊"
    );
}
```

### Backfill SQL（edge_label_backfill.py）
```python
_BACKFILL_FILL_ENTRY_CONTEXT_SQL = """
WITH close_fills_missing_entry AS (
    SELECT f.fill_id, f.ts, f.symbol, f.strategy_name, f.engine_mode, f.side
    FROM trading.fills f
    WHERE f.entry_context_id IS NULL
      AND f.exit_reason IS NOT NULL
      AND f.engine_mode = ANY(%(engine_modes)s)
      AND f.ts > (now() - (%(window_days)s || ' days')::interval)
      AND (f.strategy_name IS NULL OR f.strategy_name NOT LIKE 'unattributed:%%')
    ORDER BY f.ts DESC
    LIMIT %(batch_limit)s
),
matched_entries AS (
    SELECT c.fill_id AS close_fill_id, c.ts AS close_ts,
        (SELECT entry.context_id FROM trading.fills entry
         WHERE entry.entry_context_id IS NULL
           AND entry.exit_reason IS NULL
           AND entry.engine_mode = c.engine_mode
           AND entry.strategy_name = c.strategy_name
           AND entry.symbol = c.symbol
           AND entry.side <> c.side  -- opposite side
           AND entry.ts < c.ts
           AND entry.ts > (c.ts - INTERVAL '7 days')
           AND (entry.strategy_name IS NULL OR entry.strategy_name NOT LIKE 'unattributed:%%')
         ORDER BY entry.ts DESC LIMIT 1
        ) AS matched_entry_context_id
    FROM close_fills_missing_entry c
)
UPDATE trading.fills f
SET entry_context_id = m.matched_entry_context_id
FROM matched_entries m
WHERE f.fill_id = m.close_fill_id
  AND f.ts = m.close_ts
  AND m.matched_entry_context_id IS NOT NULL
RETURNING f.fill_id, f.entry_context_id
"""
```

## 治理對照（CLAUDE.md §七）

| 條目 | 對應 |
|---|---|
| **跨平台兼容性** | V083 純 PG-side；Python 路徑用 module path 不硬編碼；shell 用 `OPENCLAW_BASE_DIR` |
| **注釋規範** | 新代碼默認中文（2026-05-05 governance change）；既有 inline 中英對照保留不主動清 |
| **Guard A/B/C** | V083 含 Guard A（schema）+ A2（columns）+ B（type check）+ C（hot-path partial index 對齊）|
| **Idempotency** | `IF NOT EXISTS` for CHECK + `CREATE INDEX IF NOT EXISTS` + DO $$ EXISTS-skip pattern；CREATE OR REPLACE VIEW；NOT VALID CHECK 第二次跑 NOTICE-only skip |
| **Linux PG dry-run** | **未跑**（Mac sandbox 拒絕 production read） — 必由 E4 / operator 接手 |
| **800/2000 行限制** | trading_writer.rs 1149 → 1399 行（+250；< 2000 hard cap）；V083 286 行 |
| **MODULE_NOTE 雙語** | V083 / 新 helper / 新 backfill function 含 MODULE_NOTE（中文為主） |
| **NOT VALID 不破歷史** | 對齊 task spec「不破 historical fills CHECK」 |

## 不確定之處（需 E2 審查時 push back）

1. **Linux PG V083 dry-run 未驗證**：Mac sandbox permission 拒絕直接 trade-core
   PG access。E4 必須在 Linux trade-core shell 直接跑兩次 dry-run 驗證
   idempotency（NOTICE-only / 0 RAISE）。建議命令：
   ```bash
   bash helper_scripts/db/passive_wait_healthcheck.sh --quiet  # confirms PG 可達
   # 然後直接 psql -f sql/migrations/V083__*.sql 兩次
   ```

2. **`backfill_fill_entry_context_id` window_days=30 的 7d entry lookup
   sub-window**：cron run 用 `--fill-entry-context-window-days 30` 掃過去 30d
   close fills；inner LATERAL `INTERVAL '7 days'` 限定 entry fill 必在 close
   fill 前 7 天內。如有 strategy 持倉 > 7d（罕見但 funding_arb 歷史有過），
   matched_entry_context_id 會是 NULL 跳過 → 留 NULL by abandoned cron 處理。
   E2 確認 7d window 是否合理或需放寬。

3. **`opposite-side` JOIN 條件 entry.side <> c.side**：對齊 paper trading
   semantic（entry Buy → close Sell；entry Sell → close Buy）。如有
   `Take Profit + Buy back` 等場景可能 mismatch 但 funding_arb 已退役、其他
   策略 follow Buy-Sell 對稱。E2 + QC 確認 strategy taxonomy 對齊。

4. **W-AUDIT-8a Phase A WIP race**：主工作樹有 concurrent E1（`E1-C`）的
   `strategies/mod.rs::on_tick` signature 升級 WIP，導致 cargo check fail。
   我用 isolated worktree at W1 HEAD `26b7186d` 驗證自己 IMPL（pristine
   state，cargo test 2632/2632 PASS）。**E2 審查時須在 main 工作樹 8a Phase A
   完工後（trait 升級 + 5 策略 declare 後）重跑** cargo test 確認 M2 不破。

5. **fill_writer 端 WARN log 在 0 violation 時無輸出**：`if missing_entry_ctx > 0`
   早 return 防 spam；但 healthcheck 可能誤以為 writer 沒在跑。telemetry view
   `observability.fills_entry_context_id_health` 是 source of truth，log 只是
   debug aid。E2 評估是否需 INFO log 每 N 個 batch 寫 healthy heartbeat。

6. **V082 / V083 編號連續性**：V080 (E1-A T2)、V082 (E1-E M1)、V083 (本 M2)。
   V081 已被 V082 跳過（M1 takeover 號）；V084 (concurrent E1 M3) 與本 M2 互
   不依賴。E2 確認 sqlx_migrations 順序不漏跑。

## Operator 下一步

1. **E2 代碼審查**：
   - V083 schema lock + Guard A/A2/B/C + NOT VALID CHECK 設計合理性
   - Rust writer-side enforcement helper 邏輯（aggregated WARN log + sample
     extraction）+ 7 unit test 覆蓋是否充分
   - Backfill SQL 8 invariant（entry_context_id IS NULL / opposite-side / 7d
     window / audit row filter / target keyed by fill_id+ts / NULL stay）
   - 12 pytest M2 class 覆蓋 vs PA spec 95% target 模擬正確
2. **E4 回歸**：
   - **Linux PG V083 dry-run × 2**（idempotency PASS = NOTICE-only 0 RAISE）
   - cargo test --release 全套（在 W-AUDIT-8a Phase A 完工後跑）
   - pytest test_edge_label_backfill.py + test_decision_features_intent_only_emit.py
     全 PASS
   - Linux trade-core 啟動後 24h 監控 `observability.fills_entry_context_id_health`
     null_ratio 趨勢（baseline 38% NULL → 目標 < 5% NULL）
3. **PM 統一 commit + push**：等 E2 + E4 通過後 push 至 origin。task spec 明確
   要求「commit + push origin main 自動執行」— 我直接 commit + push 並通知 PM。
4. **後續 wave 工作（不是本 commit）**：
   - 7d 後 V083 NOT VALID → VALIDATE CONSTRAINT 升級（next migration V08x）
   - new healthcheck `[新-fills_entry_ctx_health]` 加 passive_wait/runner.py
     讀 `observability.fills_entry_context_id_health` view（PASS<5% / WARN
     5-30% / FAIL>=30%）
   - 24h passive observation：`label_filled_at IS NULL` ratio 從 99%→<10%

## 驗證證據

| 驗證 | 結果 |
|---|---|
| Mac cargo check（isolated worktree at `26b7186d`）| PASS（17 pre-existing warning，0 error）|
| cargo test trading_writer:: | 10/10 PASS（7 NEW M2 + 3 existing）|
| cargo test --lib (full) | 2632/2632 PASS（在 isolated worktree at W1 HEAD）|
| pytest test_edge_label_backfill.py | 40/40 PASS（12 NEW M2 class + 28 existing）|
| pytest 全 ml_training/tests/ | 409 passed / 31 skipped / 0 failed |
| V083 SQL syntax static check | Guard A/A2/B/C 全在；NOT VALID 在；CHECK idempotent；telemetry view |
| Linux PG V083 dry-run #1 | **未跑**（Mac sandbox permission 拒；E4 接手）|
| Linux PG V083 dry-run #2（idempotency） | **未跑**（同上）|
| 主工作樹 cargo check | FAIL（W-AUDIT-8a Phase A WIP from concurrent E1；非我 scope）|

## 注意事項

- **本 wave commit 自動 push origin main**（task spec 明示 + auto-mode 啟用）
- **commit message**: `e1-b-w2: W-AUDIT-4b-M2 fill writer entry_context_id INSERT trigger + V083`
- **不動 TODO.md / CLAUDE.md**（per task spec）

---

E1 IMPLEMENTATION DONE: 待 E2 審查 + E4 Linux PG dry-run + 24h
observability monitor（report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_4b_m2_fill_writer_entry_context_id.md`）
