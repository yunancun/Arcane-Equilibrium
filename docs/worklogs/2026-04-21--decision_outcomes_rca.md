# DECISION-OUTCOMES-DEAD-1 RCA — reframed as ATTEMPT-LOG-NOT-DEAD

**日期**：2026-04-21
**作者**：PM+Conductor 主會話 + R4（general-purpose research sub-agent）
**原 TODO 條目**：`TODO.md` L62「`trading.decision_outcomes` 113k 條 `max_favorable/max_adverse` 全 NULL，寫入管線斷；可沿用此表取代 exit_features 或確認徹底 dead；RCA 決定方向。」

---

## 一、RCA 結論（一句話）

**`decision_outcomes` 不是 dead。**Rust `outcome_backfiller` writer 活躍已 spawn，113k 行 `max_favorable/max_adverse` NULL 是**症狀不是 bug**，根因 = 上游 `market.klines` 歷史稀疏（MARKET-KLINES-STALE-1 2026-04-18 只修 forward-going，歷史未回填）；下游 `linucb_trainer.py` / `linucb_shadow_compare.py` 仍 JOIN 取 label，**絕不能刪**。

從 **P2「RCA 決定方向」降級為 P3 doc-only reframe**：TODO 改名 `ATTEMPT-LOG-NOT-DEAD`、消費者對 NULL 的認知由 operator 文檔澄清、等 MARKET-KLINES-STALE-1 歷史補齊後自動受益，無需動 writer。

---

## 二、RCA 事實清單（檔案:行號背書）

### 2.1 Schema 與設計意圖

| 欄位 | 型別 | NULL | 出處 |
|---|---|---|---|
| `context_id` | TEXT PK | — | `sql/migrations/V003__trading_agent_tables.sql:107-123` |
| `outcome_1m/5m/1h/4h/24h` | REAL | nullable | V003:110-114 |
| `max_favorable` / `max_adverse` | REAL | nullable | V003:115-116 |
| `backfilled_ts` | TIMESTAMPTZ | nullable | V003:117 |
| `engine_mode` | TEXT NOT NULL DEFAULT 'paper' | — | `V015__engine_mode_separation.sql:64-68`（header 註明「No writer exists yet」— 2026-04-13） |

**設計意圖**（V003:103-106 header）：「分離表避免 UPDATE 壓縮 chunk」—— `decision_context_snapshots` 是 hypertable，`decision_outcomes` 是普通表專門給**事後 5 min cron 回填**。所有 `outcome_*` 都是 **label**（非 feature）。

### 2.2 唯一寫入器（Rust）

- `rust/openclaw_engine/src/database/outcome_backfiller.rs:40-121` — `run_backfill_cycle`：
  - 同一 INSERT 寫 **全部 8 欄**（含 `max_favorable` + `max_adverse` + `backfilled_ts=NOW()`），L94-107
  - `ON CONFLICT (context_id) DO NOTHING`
  - 後續 `UPDATE trading.decision_context_snapshots SET outcome_backfilled = TRUE` L112-114
  - CTE 篩選 pending：`outcome_backfilled = FALSE AND last_price IS NOT NULL AND last_price > 0 AND ts < NOW() - INTERVAL '25 hours'` `LIMIT 200`
- `rust/openclaw_engine/src/database/outcome_backfiller.rs:128-152` — 5 min tick loop
- `rust/openclaw_engine/src/tasks.rs:584-589` — `spawn_outcome_backfiller`
- `rust/openclaw_engine/src/main.rs:873` — **實際 main 內 spawn caller ✅**

**Python `INSERT INTO trading.decision_outcomes` grep**：**0 件**。

**結論**：唯一 writer = Rust backfiller；spec 會寫齊 8 欄；path 已在 engine 啟動時 spawn。

### 2.3 `max_favorable / max_adverse` 斷鏈 RCA

- Rust writer 設計上一 INSERT 寫齊 8 欄
- 但若 LATERAL 子查詢對應的 `market.klines` 資料**稀疏/不存在**，`(high - last_price) / last_price`、`(low - last_price) / last_price` 全返 NULL → INSERT 成功，但 **5 個 outcome + 兩個 excursion 同步為 NULL**
- `market.klines` 在 2026-04-16 21:08 停寫至 2026-04-18（`docs/archive/2026-04-20--completed_todo_batch.md:21-27` MARKET-KLINES-STALE-1）— forward-going 已修復，歷史空洞未回填
- 結果：`backfilled_ts IS NOT NULL`（backfiller 跑過） + `outcome_1h IS NULL`（無 kline 資料） → `outcome_backfilled = TRUE` 成為「已嘗試」標記，非「資料完整」

**未驗證假設（需 Linux DB）**：
```sql
SELECT
  COUNT(*) AS total,
  COUNT(max_favorable)  AS mf_non_null,
  COUNT(outcome_1h)     AS o1h_non_null,
  COUNT(backfilled_ts)  AS bt_non_null,
  engine_mode,
  MIN(backfilled_ts), MAX(backfilled_ts)
FROM trading.decision_outcomes
GROUP BY engine_mode;
```
預期：
- `bt_non_null ≈ total`（backfiller 跑過）→ 證實路徑正確，writer 活躍
- `o1h_non_null ≪ total` 且 `mf_non_null ≪ total` → 證實 klines 稀疏導致 NULL
- `engine_mode` 分布：多數 'paper'（V015 default + PAPER-DISABLE-1 前累積），少量 'demo' / 'live_demo'

**若 `bt_non_null = 0`** → 113k 來自未知 writer（不在當前 repo grep 範圍），需 `git log -- sql/migrations program_code/` 歷史查被刪 Python script。

### 2.4 與 `exit_features` 的關係

| 特性 | `decision_outcomes` | `exit_features` |
|---|---|---|
| Key | `context_id`（PK） | `(context_id, ts)` |
| 粒度 | 每個 decision context 一行 | 每個 position close fill 一行 |
| 時機 | decision 後 25h+ cron 回填 | 平倉 fill 瞬間寫 |
| 性質 | Entry-anchored forward return **label**（1m/5m/1h/4h/24h） | Exit-anchored 7 維 trajectory **feature** |
| 用途 | LinUCB reward / scorer training label | Track P 物理退場規則 / Track L ML training |

**語意正交**，不互相取代。Operator 2026-04-18 設計時已明確拒絕沿用：`docs/worklogs/2026-04-18-2--exit_features_table_design.md:15-18`「decision_outcomes 是 Phase 5 realized-edge 背填作業專用，不適合 peak tracking；且該表已 dead，沿用會混淆」— **此「dead」判斷是當時 RCA 前的誤判，本次 RCA 更正為 NOT DEAD**。

### 2.5 下游 consumers

- `program_code/ml_training/linucb_trainer.py:215` — JOIN 取 `outcome_1h` 作 LinUCB reward
- `program_code/ml_training/linucb_shadow_compare.py:188` — JOIN 取 label
- `program_code/ml_training/weekly_report_generator.py` — read-only
- `program_code/ml_training/parquet_etl.py` — read-only
- `sql/migrations/V005__indexes_views.sql:261-282` — `learning.scorer_training_features` VIEW

**全部 consumer 本來就 `WHERE outcome_1h IS NOT NULL`**（自然跳過 NULL 行），不受兩欄 NULL 影響。

---

## 三、情境評估（agent RCA §F 原文對照）

| 情境 | 工程量 | 前置 | 風險 | 建議 |
|---|---|---|---|---|
| **1. Fix 回填品質** | ~30 LOC（`outcome_backfilled` enum 'pending/attempted/complete'+ VIEW WHERE clause + linucb consumer SQL 更新） | 需先補 `market.klines` 歷史 gap（否則 fix 也無用） | 改 enum 語意影響 V005 VIEW + linucb_trainer SQL | 🟡 P2 但**不急**（等 klines 歷史補齊才有實際收益） |
| **2. DROP TABLE 廢棄** | — | — | **破壞 LinUCB 訓練管線** | 🔴 **明確不建議** |
| **3. Reframe doc-only** | ~0 LOC + worklog + memory + TODO 更新 | 無 | 無（純語意澄清） | 🟢 **採納** |

---

## 四、本 session 落地（情境 3 執行）

1. ✅ 本 worklog 文件（RCA 詳細記錄）
2. ✅ `TODO.md` L62 reframe：`DECISION-OUTCOMES-DEAD-1` → `ATTEMPT-LOG-NOT-DEAD-1`，`[ ]` → `[~]` 標記「RCA 完成、reframed doc-only、等 Linux DB SQL 驗證」
3. ✅ 新 memory `project_decision_outcomes_not_dead.md`（避免未來 session 再誤判 dead）
4. ✅ `.claude_reports/20260421_134918_decision_outcomes_rca.md`（task report）

**不做**（刻意留）：
- V003 schema header 加註 `max_favorable/max_adverse may be NULL`：需動 migration file 才乾淨，且實際 schema 註釋在 header block，改既有 migration 不恰當；留給未來 V016+ migration 順帶補（或接受 worklog + memory 已足夠文檔化）
- Fix 回填品質（情境 1）：等 `market.klines` 歷史 gap 補齊判斷是否值得做
- 通知 linucb consumer：consumer 本來就 `WHERE outcome_1h IS NOT NULL`，NULL 行自然過濾，無行為需改

---

## 五、Operator 下一步

### Linux trade-core 端一次性驗證

執行 §2.3 SQL，確認：
- [ ] `bt_non_null ≈ total` ✓ → backfiller 活躍、本 RCA 結論成立
- [ ] `o1h_non_null ≪ total` ✓ → klines 稀疏是 NULL 根因
- [ ] `engine_mode` 分布：多 'paper'、少 'demo/live_demo'

若全部 ✓ → 可將 TODO 從 `[~]` 改 `[x]` 結案（reframed 為 ATTEMPT-LOG-NOT-DEAD-1）。
若任一 ✗ → 有未知 writer，回 git log 挖歷史。

### 後續追蹤（低優先級）

- 若 `market.klines` 歷史 gap 日後補齊 → `outcome_backfiller` 自動受益，無需動 code
- 若 LinUCB 正式上線且 `outcome_1h IS NOT NULL` 樣本仍不足 → 再評估情境 1 fix

---

## 六、附錄：關鍵檔案路徑索引

- **Schema**：`sql/migrations/V003__trading_agent_tables.sql:107-123`、`V015__engine_mode_separation.sql:64-68`、`V999__exit_features.sql:24-53`
- **Writer**：`rust/openclaw_engine/src/database/outcome_backfiller.rs:40-152`
- **Spawn**：`rust/openclaw_engine/src/tasks.rs:584-589`、`rust/openclaw_engine/src/main.rs:873`
- **Read consumers**：`program_code/ml_training/linucb_trainer.py:215`、`linucb_shadow_compare.py:188`
- **VIEW**：`sql/migrations/V005__indexes_views.sql:261-282`
- **設計決策歷史**：`docs/worklogs/2026-04-18-2--exit_features_table_design.md:15-18`（2026-04-18 時誤判 dead，本 RCA 更正）
- **MARKET-KLINES-STALE-1 修復紀錄**：`docs/archive/2026-04-20--completed_todo_batch.md:21-27`
