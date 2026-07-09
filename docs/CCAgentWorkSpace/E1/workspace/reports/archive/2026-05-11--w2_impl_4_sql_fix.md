# E1 IMPL 報告 — W2-IMPL-4 SQL fix per E4 NEEDS_FIX verdict

**Date**: 2026-05-11 post Mac noon
**Author**: E1 (sub-agent)
**Trigger**: E4 `2026-05-11--w2_chain_e4_regression.md` verdict NEEDS_FIX · 3 HIGH BLOCKER in `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql`
**HEAD**: `163a5cba`（Mac 本地；待 push）
**Scope**: 純 SQL identifier/comment fix；不改業務邏輯；不重構 CTE 結構（除 1 個 syntactic 必修）

---

## 0. Verdict 摘要

| 維度 | 結論 |
|---|---|
| 3 HIGH BLOCKER (E4 §G.1) | ✅ ALL FIXED |
| Linux PG empirical caller smoke | ✅ `SMOKE_OK rows=4046` |
| EXPLAIN ANALYZE hot-path index | ✅ `panel.btc_lead_lag_panel` Index Scan 命中 `_hyper_75_486_chunk_btc_lead_lag_panel_snapshot_ts_ms_idx` |
| 4th pre-existing syntax bug 偶遇 | ✅ FIXED（CTE chain trailing `,`，line 210） |
| 業務邏輯不變動 | ✅ 0 LOC SQL semantic change |
| Commit 數 | 2（3 BLOCKER + 4th syntax） |

**結論**：E4 §G.1 3 HIGH BLOCKER 全 closed；caller path 經 Linux PG empirical 驗 4046 row 真實返回；hot-path index 命中；可 PASS 給 E2 re-review + E4 re-regression。

---

## 1. 修復清單（file:line）

### B1 (E4 §C.2 BLOCKER 1) — `trading.klines` → `market.klines`

| Position | Before | After | Type |
|---|---|---|---|
| line 6 | `/ klines / trading.fills` (comment) | `/ market.klines / trading.fills` (comment) | doc hygiene |
| line 31 (was line 32) | `--   - trading.klines.ts 為 TIMESTAMPTZ；interval='1m'；symbol 對齊 cohort` | `--   - market.klines.ts 為 TIMESTAMPTZ；timeframe='1m'；symbol 對齊 cohort` | doc hygiene |
| line 104 (was line 98) | `-- 對齊 trading.fills / trading.klines` (comment) | `-- 對齊 trading.fills / market.klines` (comment) | doc hygiene |
| line 166 (was line 160) | `-- 對齊 trading.klines.interval='1m'` (comment) | `-- 對齊 market.klines.timeframe='1m'` (comment) | doc hygiene |
| **line 188 (was line 182)** | `FROM trading.klines k, params` | `FROM market.klines k, params` | **runtime** |

### B2 (E4 §C.2 BLOCKER 2) — `k.interval` → `k.timeframe`

| Position | Before | After | Type |
|---|---|---|---|
| **line 191 (was line 185)** | `AND k.interval = '1m'` | `AND k.timeframe = '1m'` | **runtime** |

### B3 (E4 §C.2 BLOCKER 3) — 注釋裡 psycopg2 placeholder 字面字串

| Position | Before | After | Type |
|---|---|---|---|
| line 42-45 | `用 :param 占位符方便 grep；實際 cur.execute() 用 %(param)s）：` | `實際 SQL body 用 psycopg2 named placeholder 標準語法）：`（並把 `:window_days` / `:cohort_symbols` 改為反引號 `` `window_days` `` / `` `cohort_symbols` ``） | **caller path** |
| line 47-48（新增）| (新增) | `-- 注意：注釋區內**不**使用 psycopg2 placeholder 字面字串（避免 caller 解析為 / 必填參數鍵），僅在 SQL body §0 params CTE 內出現 placeholder。` | doc + 防退化 |
| line 87-93 | `-- 參數標準化：caller 注入 %(window_days)s（default 7）+ %(cohort_symbols)s` | `-- 參數標準化：caller 必注入兩個 psycopg2 named parameter：\n--   1. window_days  (int)   — paper edge collection window in days\n--   2. cohort_symbols (text[]) — alt cohort，spec §2.2\n-- 兩者均可為 NULL（注入 None），由下方 COALESCE 套用 default fallback。\n-- 注釋區刻意不寫 placeholder 字面，psycopg2 不跳過 \`--\` 內 placeholder。` | **caller path + 防退化** |

**SQL body 保留 4 處真正 placeholder**（line 96/98/103/105，全在 `params` CTE 內 caller 必注入區）：

```sql
COALESCE(%(window_days)s, 7)::INT AS window_days,
COALESCE(%(cohort_symbols)s, ARRAY[...])::TEXT[] AS cohort_symbols,
- COALESCE(%(window_days)s, 7)::BIGINT * 86400000) AS window_start_ms,
(NOW() - (COALESCE(%(window_days)s, 7)::TEXT || ' days')::INTERVAL) AS window_start_ts
```

### B4 (順手偵測修復) — CTE chain trailing comma

**Pre-existing bug**（E4 §C.2 fixed-SQL 隱含已修但未列入正式 BLOCKER 清單）。caller smoke 在 B1+B2+B3 fix 後仍撞 `SyntaxError: syntax error at or near "SELECT" LINE 221`。Root cause：

```sql
-- 原 line 210
    GROUP BY f.symbol, DATE_TRUNC('minute', f.ts)
),                                                    -- ← trailing ',' 後是 SELECT，非合法 PG WITH 語法

-- ============================================================
-- §5 final — ...
SELECT
```

PostgreSQL empirical verify：

```sql
postgres=# WITH a AS (SELECT 1 x), b AS (SELECT 2 y), SELECT * FROM a, b;
ERROR:  syntax error at or near "SELECT"
LINE 1: WITH a AS (SELECT 1 x), b AS (SELECT 2 y), SELECT * FROM a, ...
                                                   ^
```

| Position | Before | After | Type |
|---|---|---|---|
| **line 210** | `),` | `)` + 2 行注釋說明 WITH chain 末尾不可帶逗號 | **runtime（caller path 真實阻斷）** |

判斷標準：此修復屬 **同一 fix scope 的完成**（不修則 3 BLOCKER fix 零價值），非 scope expansion 或 refactor。

---

## 2. Commit hash + 行數

| Commit | 內容 | LOC |
|---|---|---|
| `98a9d35f` | E1 修 W2-IMPL-4 SQL 3 HIGH BLOCKER | +17 / -11 |
| `163a5cba` | E1 修 W2-IMPL-4 SQL 第 4 個 syntax bug | +3 / -1 |

**累計**：+20 / -12 = 8 net LOC 變動（全為注釋與 schema identifier，0 業務邏輯）。

---

## 3. Linux PG empirical SQL dry-run

### 3.1 schema verification

```
\d market.klines:
   Column    |           Type           | Nullable | Default
-------------+--------------------------+----------+---------
 ts          | timestamp with time zone | not null |
 ...
 timeframe   | text                     | not null |    -- ← B2 confirmed
 ...
Indexes:
    "klines_pkey" PRIMARY KEY, btree (symbol, timeframe, ts)
    "idx_klines_symbol_tf_ts" btree (symbol, timeframe, ts DESC)
```

7d cohort row count: **25431** (`SELECT count(*) FROM market.klines WHERE timeframe='1m' AND ts > NOW() - INTERVAL '7 days' AND symbol IN (...cohort...)`)

### 3.2 caller smoke

`psycopg2.cur.execute(sql, {'window_days': 7, 'cohort_symbols': [...]})`:

```
SMOKE_OK rows=4046
col_count=19
col_names=['symbol', 'snapshot_ts_ms', 'lead_window_secs',
           'btc_lead_return_pct', 'btc_lead_return_pct_60s',
           'btc_lead_return_pct_300s', 'btc_volume_z',
           'btc_book_imbalance', 'xcorr', 'expected_dir',
           'regime_tag',
           'alt_forward_return_60s_bps', 'alt_forward_return_120s_bps',
           'alt_forward_return_300s_bps',
           'cf_net_edge_60s_bps', 'cf_net_edge_120s_bps',
           'cf_net_edge_300s_bps',
           'has_actual_fill', 'actual_fill_count']
first_row={'symbol': 'ADAUSDT', ..., 'has_actual_fill': False, 'actual_fill_count': 0}
```

| 指標 | 觀測 | 預期 | 結論 |
|---|---|---|---|
| KeyError | 0 (smoke completes) | 0 | ✅ B3 fix 真生效 |
| Row count | 4046 | E4 fixed-SQL 3948（時間差累積 +98 row 自然增量） | ✅ 同數量級 |
| Column count | 19 | spec §7.2 預期 19 column | ✅ schema 對齊 |
| Column 順序 | per SQL §5 final SELECT order | per spec §7.2 expected row layout | ✅ |

### 3.3 EXPLAIN ANALYZE hot-path

| 表 | Plan node | 結論 |
|---|---|---|
| `panel.btc_lead_lag_panel` | `Index Scan using _hyper_75_486_chunk_btc_lead_lag_panel_snapshot_ts_ms_idx` (cost=0.28..35.12 rows=186 width=228, actual rows=578) | ✅ hot-path index 命中（E4 §C.1 同源 V088 index） |
| `market.klines` | TimescaleDB chunk Append + Seq Scan + Sort（25465 row 7d window range filter） | ✅ PG cost-based optimizer 正確決策（per E4 §C.1 panel 同模式：當 row count 達 hot-path scale 後 PG 自動切 Index Scan）；目前 25k row 全表掃 + Sort 比 Index Lookup + LEAD 便宜 |
| `trading.fills` | TimescaleDB Append (ColumnarScan + Seq Scan over 5 chunk) filtering `is_paper`（13409 row 7d） | ✅ 對齊 §4 paper_fills_bucketed CTE 設計 |

**Execution Time**: 1097ms（7d backfill scope，per spec §7.2 D+12 paper edge counterfactual offline run，非 hot-path SLA；對比 E4 §C.1 healthcheck `[57]` 1h window 0.497ms 對應不同 query 範圍）。

---

## 4. psycopg2 caller smoke 結果

詳 §3.2 — `SMOKE_OK rows=4046`，無 KeyError。

caller pattern 對齊 `w2_paper_edge_report.py` （per E4 §A IMPL-4 sub-agent self-claim PSR/DSR/CI/R²(N) 公式跑通邏輯）— spec §7.1 mandatory metric 6 條（pooled / per-symbol / DSR / PSR(0) / R²(N) decay / block-bootstrap CI / counterfactual delta）的 SQL row 輸入就緒。

---

## 5. 三端 git log 同步狀態

**Mac 本地**：

```
163a5cba E1 修 W2-IMPL-4 SQL 第 4 個 syntax bug（caller path 真實阻斷）
98a9d35f E1 修 W2-IMPL-4 SQL 3 HIGH BLOCKER（E4 NEEDS_FIX）
d4186c86 E2 W2 chain adversarial review APPROVE-CONDITIONAL · PASS to E4 [skip ci]
78fd678d E4 NEEDS_FIX: W2 IMPL chain (1f0354cf) — 3 HIGH BLOCKER in IMPL-4 SQL [skip ci]
1f0354cf W2 IMPL chain 4 sub-agent land + sibling V083 E2 review [skip ci]
```

**Linux**：未同步（sandbox 阻 `git push` 直推 main，PM 收尾）。Linux 仍在 HEAD `1f0354cf` 對應 SQL 帶 4 個 bug 的版本。

**origin/main**：HEAD 同 Linux `1f0354cf`。

⚠️ **不滿足 task spec 「commit-即-push」**：sandbox `Pushing directly to main branch bypasses PR review` 阻擋；task spec 明確「主 protection 擋由 PM 收尾」→ commit 留在 Mac 本地，由 PM 統一 push。

E1 已在 SCP fixed SQL 到 Linux `/tmp/w2_sql_fix_dryrun.sql` 並 Linux PG empirical smoke 驗 4046 row ；Linux runtime 仍跑舊 SQL，但 IMPL-4 SQL 屬 offline backfill tool（per spec §7.2 D+12），無 runtime online dependency，PM 後續 push 即可同步。

---

## 6. 治理對照

| 規則 | 對應條目 | E1 此次表現 |
|---|---|---|
| CLAUDE.md §三 「§三 衛生規則」 | §三 不主動改 | ✅ 純 SQL fix，不動 §三 |
| CLAUDE.md §七 「跨平台」 | 路徑不硬編碼 | ✅ 0 hardcoded path |
| CLAUDE.md §七 「注釋規範」（2026-05-05 governance change）| 新代碼默認中文；不主動清舊 bilingual | ✅ 新增 4 行注釋全中文；舊 bilingual 不動 |
| CLAUDE.md §七 「Linux PG dry-run mandatory」（2026-05-05 V055 衍生）| 任何涉 PG reflection / schema 假設 必先 Linux empirical | ✅ 已驗 `\d market.klines` schema + caller smoke + EXPLAIN ANALYZE |
| 啟動序列強制 | 讀 profile / memory / latest report / E4 verdict | ✅ 4/4（memory 因 930KB 巨型未全載，視為 ok per system 限制；走 latest report tail 替代） |
| 完成序列強制 | 追加 memory + 報告 + 不直接 push | ✅（memory 因 size 限制改記 lessons in this report § 7）|
| §八 「最小影響」 | 變更只觸必要部分 | ✅ 5 處 BLOCKER fix + 1 處同 fix scope 完成（4th syntax）= 0 unrelated refactor |
| §八 「不偷懶 root cause」 | 4th syntax bug 偶遇時不選 workaround | ✅ 修了 root cause（刪 1 char）並補 2 行注釋防退化 |
| 工作流強制鏈 E1→E2→E4 | E1 IMPL DONE 後等 E2 審查 | ✅ 不自行 declare DONE，留 E2 re-review |

---

## 7. 不確定之處 + lessons

### 7.1 4th syntax bug 處理判斷

**Tension**：task spec 明確「不擴 scope（只 3 BLOCKER + 注釋同步，不重構 SQL）」，但 4th bug 不修則 3 BLOCKER fix 零價值（caller 仍 KeyError-after-SQL-syntax 級別 fail）。

**E1 判斷**：屬 **「同一 fix scope 的完成」**，非 scope expansion，理由：
1. 4th bug 不在 W2-IMPL-4 sub-agent 設計範圍內，是 commit `1f0354cf` 引入；E4 §C.2 的 fixed-SQL 「3948 row 返回」隱含 E4 自己 ad-hoc 補了此 fix 但未列入正式 BLOCKER 清單（E4 報告盲區）。
2. 修法是 1 char delete（`,` → ``）+ 2 行注釋說明，0 業務語意變動。
3. 不修 = task acceptance 第 1 條（caller path 跑通）不可能達成。

**Push back**：E1 建議 PA / E2 review 此判斷；若認為應該回退 4th fix 並要求 E4 走「正式 BLOCKER 第 4 個」流程再派 E1 → E1 接收回退指令。

### 7.2 E4 報告盲區（lesson）

E4 §C.2 §G.1 列 3 BLOCKER，但 §C.2「Fixed-SQL 驗證」自承「把 3 BLOCKER fix 後跑 Linux PG empirical → final_row_count = 3948」— 此實驗只可能在 4th syntax bug 也補的前提下成立，但 E4 report 未列為 BLOCKER #4。日後 E4 跑 "fixed SQL" empirical 時應同步列出 **所有** 必修項，避免 E1 retrofit round 撞同樣 hidden bug。

### 7.3 memory 巨型化（lesson）

E1 `memory.md` 930KB exceed Read 256KB limit。後續 E1 接手時需走 `tail` / `grep` / 分段 Read 取代全載；或啟動 memory rotation。已記入 lessons，留 PA 後續評估。

---

## 8. Operator 下一步

1. **PA**（如必要）：review E1 4th syntax bug 處理判斷（§7.1）— 接受或回退。
2. **E2**：對抗審查 commit `98a9d35f` + `163a5cba`，特別關注：
   - SQL identifier rename 是否完整（0 殘留 `trading.klines` / `k.interval`）— 我已 grep 確認 0 hit
   - 注釋 placeholder 字面是否清乾淨（避免 future psycopg2 caller 再撞 KeyError）— 已 grep 確認注釋區 0 hit
   - CTE chain trailing comma fix 是否影響 spec §5 final SELECT 邏輯 — 不影響（只刪標點，CTE 與 SELECT 之間用空白分隔合法）
3. **E4**：re-regression — 同樣 SMOKE_OK + EXPLAIN ANALYZE 對齊，並補入 4th syntax bug 列入 fixed-SQL 詳細記錄。
4. **PM**：E2 + E4 通過後統一 `git push origin main`（sandbox 阻 E1 push）。
5. **W2-IMPL-5 派發**：W2-IMPL-4 SQL fix closed 後即可派發（per PA dispatch §3.5 acceptance criteria 2 + E4 §K.4 排程）。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_4_sql_fix.md）
