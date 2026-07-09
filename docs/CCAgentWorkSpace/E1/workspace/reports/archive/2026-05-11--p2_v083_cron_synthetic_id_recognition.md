# E1 IMPL DONE — P2 V083 cron synthetic id recognition

**日期 / Date**：2026-05-11
**Agent**：E1
**Commit**：`396328d0`（Mac 本地）
**Branch**：main（本地 commit；push 被 sandbox 阻擋 — 見 §7）

## 1. 任務摘要

P1 V083 修復（`d4867676`）為 `risk_close:ipc_close_symbol` 等 orphan close path 加 synthetic id `orphan_recovery_ctx:{symbol}:{ts_ms}` 滿足 V083 NOT NULL CHECK。但 ML training data 完整性要求 close fill 的 `entry_context_id` 必為真 entry 的 `context_id`（不是 synthetic）。

當前 cron deployed 版本（Path 1，commit `dc8b7ffe` HEAD）strict 要求 `entry.strategy_name = c.strategy_name`，**100% miss**（Linux PG empirical 13:14 cron run：candidates=27 matched=0）。

本 P2 IMPL 加 Path 2 backfill SQL，**不限 strategy_name** 識別並升級 synthetic id 為真 entry context_id。

## 2. 修改清單

| 檔案 | 變更類型 | 行變化 |
|---|---|---|
| `program_code/ml_training/edge_label_backfill.py` | +Path 2 SQL + 擴展 dataclass + 兩路 backfill function | +192 |
| `program_code/ml_training/tests/test_edge_label_backfill.py` | +7 P2 pytest case + 既有 test fixture 加 Path 2 mock | +234 |

文件大小：`edge_label_backfill.py` 921→1113 LOC（< 2000 hard cap，§九）。

## 3. 關鍵 diff

### 3.1 SQL — Path 2 unblocks orphan-adopt close fills

**`_BACKFILL_FILL_SYNTHETIC_CONTEXT_SQL`**（新增，在 `_BACKFILL_FILL_ENTRY_CONTEXT_SQL` 之後）：

```sql
WITH synthetic_close_fills AS (
    SELECT f.fill_id, f.ts, f.symbol, f.strategy_name, f.engine_mode, f.side
    FROM trading.fills f
    WHERE f.entry_context_id LIKE 'orphan_recovery_ctx:%%'
      AND f.exit_reason IS NOT NULL  -- close fill only
      AND f.engine_mode = ANY(%(engine_modes)s)
      AND f.ts > (now() - (%(window_days)s || ' days')::interval)
      AND (f.strategy_name IS NULL OR f.strategy_name NOT LIKE 'unattributed:%%')
    ORDER BY f.ts DESC
    LIMIT %(batch_limit)s
),
matched_entries AS (
    SELECT c.fill_id AS close_fill_id, c.ts AS close_ts,
        (SELECT entry.context_id
         FROM trading.fills entry
         WHERE entry.entry_context_id IS NULL
           AND entry.exit_reason IS NULL
           AND entry.engine_mode = c.engine_mode
           -- NOTE: 不限 strategy_name —— risk_close orphan adopt
           AND entry.symbol = c.symbol
           AND entry.side <> c.side
           AND entry.ts < c.ts
           AND entry.ts > (c.ts - INTERVAL '7 days')
           AND (entry.strategy_name IS NULL OR entry.strategy_name NOT LIKE 'unattributed:%%')
         ORDER BY entry.ts DESC LIMIT 1) AS matched_entry_context_id
    FROM synthetic_close_fills c
)
UPDATE trading.fills f
SET entry_context_id = m.matched_entry_context_id
FROM matched_entries m
WHERE f.fill_id = m.close_fill_id
  AND f.ts = m.close_ts
  AND m.matched_entry_context_id IS NOT NULL
RETURNING f.fill_id, f.entry_context_id
```

關鍵設計差別 vs Path 1：
- WHERE clause：`entry_context_id LIKE 'orphan_recovery_ctx:%'`（vs Path 1 `IS NULL`）
- entry lookup：**不限定** `entry.strategy_name = c.strategy_name`（vs Path 1 strict 等號）
- 其他 safety guards 完全一致（7d window / opposite side / audit row filter / unique match by NOT NULL）

### 3.2 Python — dataclass + function 擴展

`FillEntryContextBackfillResult` 加 3 個 P2 buckets:
```python
matched_synthetic_count: int = 0      # P2: synthetic id → real context_id 成功改寫數
candidate_synthetic_count: int = 0    # P2: synthetic id close fill 候選池大小
not_matched_synthetic_count: int = 0  # P2: 候選池但無對應 entry（留 synthetic）
```

`to_dict()` 保留 cron 舊版 `matched` / `candidates` 鍵（不破回歸），新加：
- `matched_real` / `candidates_null`（Path 1，無歧義鍵）
- `matched_synthetic` / `candidates_synthetic` / `not_matched_synthetic`（Path 2）

`backfill_fill_entry_context_id()` 內部新增第二段 cursor.execute 跑 Path 2 + count + matched 統計。`batch_limit_hit` 任一 path 命中即 True（cron 下次再跑訊號）。

CLI 不需新 flag — `--backfill-fill-entry-context-id` 開關保留同義，內部自動跑兩 path；`--dry-run` 流向 rollback 不變。

### 3.3 cron output 變化（log 訊息）

```
# BEFORE (Path 1 only)
matched=0 candidates=27

# AFTER (Path 1 + Path 2)
matched_real=N candidates_null=M matched_synthetic=K candidates_synthetic=W not_matched_synthetic=V
```

## 4. 治理對照

| 規則 | 狀態 |
|---|---|
| CLAUDE.md §七 跨平台 — 不硬編 path | ✅ 沿用既有 `_get_conn()` env-based DSN |
| CLAUDE.md §七 SQL migration Guard A/B/C | N/A（本 task 純 Python，無新 .sql migration） |
| CLAUDE.md §七 注釋默認中文 | ✅ Path 2 SQL + dataclass + function 中文注釋；歷史中英對照保留 |
| CLAUDE.md §七 sign-off 必檢 git clean | ⚠️ 本地 `M docs/CCAgentWorkSpace/E2/memory.md` 和 Rust 文件遺留 — 不在本 task 範圍，未 staged，commit `--only` 隔離 |
| CLAUDE.md §九 文件大小 800/2000 | ✅ edge_label_backfill.py 1113 LOC（< 2000 hard cap） |
| CLAUDE.md §九 singleton 登記 | ✅ 無新 singleton |
| §八「最小影響」原則 | ✅ 只動兩個檔案；其他 untracked Rust/E2 文件不 stage 不 touch |
| `feedback_v_migration_pg_dry_run.md` (V055 教訓) | ✅ 本 task 純 Python 邏輯但已用 Linux PG empirical SELECT-mode dry-run（§5） |
| 雙語 MODULE_NOTE | ✅ Path 2 SQL 頂部 MODULE_NOTE 中英對照（背景 / 設計 / 安全保證 / Acceptance） |

## 5. PG empirical dry-run（SELECT-mode）

**前置：sandbox 阻擋 push 與 scp，無法在 Linux 跑改後 Python module。改用 SELECT-mode raw SQL 等價驗證 Path 2 SQL 邏輯。**

### 5.1 Synthetic id pool count（Linux runtime 2026-05-11 13:30 UTC）

```sql
SELECT engine_mode, COUNT(*) AS total_synthetic_close_fills,
       COUNT(*) FILTER (WHERE ts > NOW() - INTERVAL '30 days') AS in_30d_window,
       COUNT(*) FILTER (WHERE ts > NOW() - INTERVAL '7 days') AS in_7d_window
FROM trading.fills
WHERE entry_context_id LIKE 'orphan_recovery_ctx:%'
  AND exit_reason IS NOT NULL
GROUP BY engine_mode;
```

```
 engine_mode | total | 30d | 7d
-------------+-------+-----+----
 demo        |     2 |   2 |  2
 live_demo   |     2 |   2 |  2
```

**4 個 synthetic close fills 全在 30d/7d 內。**

### 5.2 Path 2 dry-run（SELECT-mode 模擬 UPDATE 而不執行）

```sql
WITH synthetic_close_fills AS (
    SELECT f.fill_id, f.ts, f.symbol, f.strategy_name, f.engine_mode, f.side,
           f.entry_context_id AS current_synthetic_id
    FROM trading.fills f
    WHERE f.entry_context_id LIKE 'orphan_recovery_ctx:%'
      AND f.exit_reason IS NOT NULL
      AND f.engine_mode IN ('demo', 'live_demo')
      AND f.ts > (now() - INTERVAL '30 days')
),
matched_entries AS (
    SELECT c.fill_id, c.symbol, c.side, c.strategy_name AS close_strat,
           (SELECT entry.context_id FROM trading.fills entry
            WHERE entry.entry_context_id IS NULL AND entry.exit_reason IS NULL
              AND entry.engine_mode = c.engine_mode AND entry.symbol = c.symbol
              AND entry.side <> c.side
              AND entry.ts < c.ts AND entry.ts > (c.ts - INTERVAL '7 days')
            ORDER BY entry.ts DESC LIMIT 1) AS matched_entry_ctx,
           ... matched_entry_strategy
    FROM synthetic_close_fills c
)
SELECT ..., CASE WHEN matched_entry_ctx IS NOT NULL THEN 'MATCH' ELSE 'NO_ENTRY' END
FROM matched_entries;
```

**Output**:

| close_fill_id | engine | symbol | side | close_strategy | synthetic_id | will_match_entry_strategy | will_update_to_context_id | verdict |
|---|---|---|---|---|---|---|---|---|
| bybit-da6198d4 | live_demo | NEARUSDT | Buy | ma_crossover | `orphan_recovery_ctx:NEARUSDT:1778465695913` | grid_trading | `ctx-live_demo-NEARUSDT-1778347581008` | **MATCH** |
| bybit-aa22a4ff | demo | APTUSDT | Buy | ma_crossover | `orphan_recovery_ctx:APTUSDT:1778465696429` | (no entry in 7d) | (NULL) | **NO_ENTRY** |
| bybit-afe28031 | demo | TONUSDT | Buy | ma_crossover | `orphan_recovery_ctx:TONUSDT:1778497084695` | grid_trading | `ctx-demo-TONUSDT-1778496301238` | **MATCH** |
| bybit-6dce09e0 | live_demo | ATOMUSDT | Buy | ma_crossover | `orphan_recovery_ctx:ATOMUSDT:1778497860110` | ma_crossover | `ctx-live_demo-ATOMUSDT-1778495580057` | **MATCH** |

### 5.3 Path 1 strict-strategy_name miss 驗證（Linux PG）

同樣 SELECT-mode 跑當前 deployed Path 1 SQL（含 `entry.strategy_name = c.strategy_name` strict）→ 抽 5 row sample:

```
            close_fill_id              | close_strategy              | matched | verdict
---------------------------------------+-----------------------------+---------+-------------
 bybit-2dfed075...SAHARAUSDT live_demo | risk_close:ipc_close_symbol | NULL    | PATH1_MISS
 bybit-f68f74fe...NEARUSDT  demo       | risk_close:ipc_close_symbol | NULL    | PATH1_MISS
 bybit-b477bbdc...NEARUSDT  live_demo  | risk_close:ipc_close_symbol | NULL    | PATH1_MISS
 bybit-0e1cc2e3...SAHARAUSDT live_demo | risk_close:ipc_close_symbol | NULL    | PATH1_MISS
 bybit-bde1150b...LINKUSDT  live_demo  | risk_close:ipc_close_symbol | NULL    | PATH1_MISS
```

確認 PA 設計診斷：**100% miss 因為 close_strategy=`risk_close:ipc_close_symbol` 不會有對應「真 entry with same strategy_name」存在**。

### 5.4 預期 production UPDATE 影響數

**3 rows will be UPDATE'd**（4 candidates - 1 NO_ENTRY = 3 MATCH）:

1. `bybit-da6198d4` (NEARUSDT live_demo) → `ctx-live_demo-NEARUSDT-1778347581008`
2. `bybit-afe28031` (TONUSDT demo) → `ctx-demo-TONUSDT-1778496301238`
3. `bybit-6dce09e0` (ATOMUSDT live_demo) → `ctx-live_demo-ATOMUSDT-1778495580057`

**1 row stays synthetic**（APTUSDT no entry in 7d window）— 預期 telemetry view `observability.fills_entry_context_id_health` 持續 WARN 此 row。

Path 1 既有 candidates（27/26 row 27/26 → NULL entry_context_id）**完全不影響**，仍是 100% miss（因 strict strategy_name；該問題另開 ticket 治理）。

## 6. 不確定之處

1. **Path 1 NULL candidates 為何累積到 27**：deployed 後新生的 risk_close close fills 是寫 NULL 還是 synthetic id？P1 修復後新 path 應該都寫 synthetic 才對。可能歷史 V083 deploy 前的 close fills 是 NULL；或某些 path 仍有遺漏。**本 task 不處理 NULL path**（PA 設計範圍只 P2 synthetic id）。
   - 推測：歷史殘留 27 NULL 是 V083 deploy 前累積；新發生的 risk_close 已寫 synthetic id（4 candidates 全 5/11 當天）。
   - 建議：另開 ticket 處理 NULL → 也用 Path 2 不限 strategy_name 邏輯（或合併 Path 1+2 SQL：`(IS NULL OR LIKE 'orphan_recovery_ctx:%')` + 不限 strategy_name）。

2. **多 candidate ordering by ts DESC**：取最近 entry 是合理啟發式，但若 entry close 已發生（即另一 close fill 已關了該 entry），仍可能誤匹。當前 SQL 沒考慮 entry 是否「仍開倉」 — 但這在 Path 1 既有 SQL 也沒考慮，本 task 不擴大範圍。

3. **batch_limit_hit 對 Path 2 的語義**：
   - 設 `not_matched_synthetic = min(candidate, batch_limit) - matched_synthetic`。
   - 若 `candidate=100, batch_limit=10, matched=0` → not_matched=10（batch 內處理但無對應 entry）。
   - 真實 not_matched candidates 為 candidate - matched = 100；本欄位反映 batch 內未匹配數，cron 下次重跑會處理剩餘候選池。
   - test_p2_not_matched_capped_by_batch_limit 驗證此語義。

4. **觀察期之後是否合併 Path 1+2 SQL**：本 IMPL 兩路獨立執行可獨立統計，便於 telemetry。觀察 N day 後若兩 path 設計趨近一致，可合併成一個 SQL UNION（CTE OR 條件），但這是 future refactor，不在本 task 範圍。

## 7. Operator 下一步

### 7.1 Push commit 396328d0 到 origin/main（**operator 手動**）

sandbox 阻擋 CC 推 main，但 task 寫「operator 已授權 deploy chain push」。請 operator 手動：
```bash
cd ~/Projects/TradeBot/srv && git push origin main
```

如 main push 被禁可走 PR：
```bash
git push origin HEAD:p2-v083-cron-synthetic-id-recognition
# 然後在 GitHub 開 PR
```

### 7.2 Linux runtime dry-run（push 後）

operator 在 trade-core 端：
```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && \
  OPENCLAW_BASE_DIR=\$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
  OPENCLAW_SECRETS_ROOT=\$HOME/BybitOpenClaw/secrets \
  bash helper_scripts/cron/edge_label_backfill_cron.sh 2>&1 | tail -20"
```

預期 log 訊息：
```
W-AUDIT-4b-M2 + P2 fill entry_context_id backfill result: {
  'matched': 0, 'candidates': 27,           # legacy keys
  'matched_real': 0, 'candidates_null': 27,
  'matched_synthetic': 2, 'candidates_synthetic': 2,
  'not_matched_synthetic': 0,
  'batch_limit_hit': False
}
backfill result: {...}
```

（demo 4 candidates 中 2 個 NEAR + ATOM 屬 live_demo，跑 demo pass 預期 matched_synthetic=2 candidates_synthetic=2；live_demo pass 預期 matched=2 candidates=2，其中 APT 不在 live_demo 故 not_matched=0）

實際數字 + 影響 row 由 operator 觀察後確認。

### 7.3 production UPDATE 授權（dry-run 通過後）

dry-run 確認 matched_synthetic 數 + verdict 後，operator **顯式授權** 即可跑非 dry-run 模式：
- 標準 cron 30min cycle 會自動跑（已含 `--backfill-fill-entry-context-id`）
- 或手動 trigger 一次：`bash helper_scripts/cron/edge_label_backfill_cron.sh`

UPDATE 後驗證：
```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -P pager=off -c \"
SELECT entry_context_id, COUNT(*)
FROM trading.fills
WHERE fill_id IN ('bybit-da6198d4-f6ea-4698-aa07-4f7dd997e2fa',
                  'bybit-afe28031-f24a-4669-bb60-4dd3556d333d',
                  'bybit-6dce09e0-7f21-4588-b37f-081d3566c9c0',
                  'bybit-aa22a4ff-d603-4d3b-bb9f-afda187c4587')
GROUP BY entry_context_id ORDER BY entry_context_id;
\""
```

預期：3 row 變真 ctx-* id，1 row（APT）仍 synthetic。

### 7.4 E2 + E4 對抗審查

- E2：grep `unattributed:` filter 是否完整、SQL safety guards、無新 singleton、無路徑硬編
- E4：跑 47 個 unit test + 4 個 cron-env test 在 Linux 環境（CI/CD pipeline 自動）

### 7.5 telemetry view 收斂監測（dry-run + UPDATE 後）

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -P pager=off -c \"
SELECT * FROM observability.fills_entry_context_id_health;
\""
```

UPDATE 後預期 `null_ratio` 不變（4 個 synthetic id 在計算上仍是「非 NULL」），但下游 ML training（`learning.mlde_edge_training_rows`）的 attribution chain 完整度應上升。

---

**E1 IMPLEMENTATION DONE：待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p2_v083_cron_synthetic_id_recognition.md`）**
