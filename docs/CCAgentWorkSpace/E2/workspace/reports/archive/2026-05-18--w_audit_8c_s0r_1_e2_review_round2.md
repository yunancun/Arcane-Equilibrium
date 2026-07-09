# E2 Round 2 Adversarial Review — W-AUDIT-8c 8C-S0R-1 SQL Query Template

- **日期**：2026-05-18
- **審查目標**：`origin/feature/w-audit-8c-s0r-1-sql-query-template` HEAD `381d89a0`（round 1 為 `bd1b2443`）
- **Worktree 路徑**：`/Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/e1-s0r-1-r2`
- **Round 1 review**：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8c_s0r_1_e2_review.md`（RETURN，2 CRIT + 2 HIGH + 4 MED + 2 LOW）
- **PA HIGH-2 arbitration**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_s0r_1_high_2_boundary_leak_arbitration.md`（verdict D：entry_mid/exit_mid 取 open-only，`>=` 維持）
- **E1 self-report v2**：`.claude/worktrees/e1-s0r-1-r2/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_1_sql_query_self_report.md`（Round 1 + Round 2 delta appended）
- **審查模式**：focused validation（不是 fresh review；只驗 round-1 must-fix list 是否落地 + 有無 regression）

## 最終裁決

**APPROVE — Ready for E4 regression**

Round-1 全部 must-fix（2 CRIT + 2 HIGH + 2 LOW + MIT MUST-LAND + MIT 3 SHOULD-FIX）已正確落地；3 個 round-1 MED 未獨立解決但 MED-1 部分透過 sibling split 結構變化納入；MED-2 / MED-3 / MED-4 是 deferred items 不阻 E4。0 個新 regression 引入；0 個新 CRIT/HIGH issue。

---

## 改動範圍

| File | 動作 | 行數 變化 |
|---|---|---|
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` | 重寫主檔 | 428 → 352（-76） |
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql` | NEW | +53 |
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql` | NEW | +156 |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_1_sql_query_self_report.md` | R2 delta appended | +167 |

`git diff --stat bd1b2443..381d89a0 -- sql/queries/`：3 files / 307 insert / 174 delete。Scope 乾淨；無 V### / Rust / Python / auth / live state 變動。

---

## §5 Multi-session race check（強制）

- [x] **5a** `git fetch origin` 已執行；origin/main 最近 5 commits 全為 Phase 1b calibration docs / harness IMPL（2b65d3f1 / d2286c05 / 34af2d2e / 5df39d13 / 8d8a0123），與本 PR `sql/queries/` 0 overlap → PASS
- [x] **5b** `git status --porcelain` 顯示 4 modified memory.md（E2/E4/MIT/PA）+ 11 untracked report files（PA / QA / BB / Operator reports），全部為先前 session 留下與本次 review scope 無關；無 leftover SQL file → PASS
- [x] **5c** 0 unknown WIP 出現在本 PR file scope（`sql/queries/`）→ PASS
- [x] **5d** review 過程只讀 + 寫單一 report；未執行 commit / stash 操作 → PASS
- [x] **5e** review 期間 origin/main 0 sibling push 進入本 PR file scope → PASS

---

## Per-Finding 結案狀態（round 1 must-fix list）

### [CRIT-1] `notional_pct_floor` gate 完全缺漏 → **CLOSED**

**驗證**：
- ✅ 第 11 個 param `%(notional_pct_floor)s` 加入主檔 header（line 31）+ sibling cluster_n_eff header（line 29）
- ✅ E1 採「兩層 CTE」分層做法（`trigger_with_pct` → `trigger_candidates`）解決 percent_rank() 不能在 WHERE 直接用的限制
- ✅ `trigger_with_pct` (features.sql line 189-214) 計算 `percent_rank() OVER (PARTITION BY symbol ORDER BY cluster_notional_5m ROWS BETWEEN 288 PRECEDING AND CURRENT ROW) AS notional_pct_24h`
- ✅ `trigger_candidates` (features.sql line 216-237) WHERE 加入 `AND twp.notional_pct_24h >= %(notional_pct_floor)s::float8`（第 3 行 gate）
- ✅ MODULE_NOTE deviation #6 documented（features.sql line 118-120）
- ✅ 三層 magnitude gate rationale 解釋清楚（line 227-230）：「cluster_notional_floor_usd 排太小，notional_pct_floor 排相對歷史平庸，side_dominance_floor 排方向不主導」

**look-ahead bias 檢查**：`ROWS BETWEEN 288 PRECEDING AND CURRENT ROW` 含 current row。引用 `feedback_indicator_lookahead_bias.md` 標準：「rolling(N).max() 含 current bar → breach=current 是 N-bar max → 必然 mean-revert」。但本案是 **percent rank** 而非 max/min；含 current row 表示「自己在 288 桶中的排名」用於 magnitude gate 是設計目的本身（spec v0.3 §magnitude_ok 要求「相對自身歷史 ≥ 0.90/0.95/0.98 分位」），這是 `cluster_notional_floor_usd` 的相對版補充 gate，**不是 leak-free indicator failure**。current 包含自己是合理的，否則「自己是否高分位」這個 question 無解。不違反 lookahead bias 原則。

### [CRIT-2] Sibling n_eff helper 與主查詢 trigger 樣本不一致 → **CLOSED**

**驗證**：
- ✅ `cluster_n_eff.sql` 6 CTE 鏡像主檔 4 CTE 部分（raw_buckets / density_gated / trigger_with_pct / trigger_candidates）+ 2 新 CTE（ordered / new_cluster_flag）
- ✅ Sibling `trigger_candidates` WHERE clause（cluster_n_eff.sql line 118-120）三層 gate **與主檔完全一致**：
  ```
  WHERE twp.side_dominance_ratio >= %(side_dominance_floor)s::float8
    AND twp.cluster_notional_5m  >= %(cluster_notional_floor_usd)s::float8
    AND twp.notional_pct_24h     >= %(notional_pct_floor)s::float8
  ```
- ✅ Sibling raw_buckets / density_gated SELECT 結構與 main 1:1（同 columns / 同 aggregation / 同 dominant_side CASE）
- ✅ Sibling param set（8 個）是 main param set（11 個）嚴格子集：drops `cost_bps` / `horizon_min` / `quiet_window_sec`（這 3 個只在 main forward_returns + final_signals 用），語義正確
- ✅ Sibling `trigger_candidates` SELECT 只投影 3 個 column（`symbol, dominant_side, bucket_end_ts`），下游 `ordered` / `new_cluster_flag` 都只 reference 這 3 個，無 broken column reference

**對抗反問**：若 caller 只在 main 提供 `notional_pct_floor=0.95` 但 sibling 漏給此參數？
- A：psycopg2 named-param 對缺 key 會 raise `KeyError` → fail-fast；不會 silent default → OK

### [HIGH-1] PA 多檔 → 單檔 sentinel-split 契約漂移 → **CLOSED**

**驗證**：
- ✅ 3 個獨立 .sql 檔，檔名匹配 S0R-3 CLI loader 契約：
  - `w_audit_8c_liquidation_cluster_stage0r_features.sql` (352 LOC) — main 5-CTE
  - `w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql` (53 LOC) — sibling #1
  - `w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql` (156 LOC) — sibling #2
- ✅ sqlparse smoke 驗證每檔 = exactly 1 statement，每檔 `;` count = 1，每檔 `-- @SIBLING:` sentinel 數 = 0
- ✅ 消除 round-1 silent failure mode：psycopg2 `cur.execute()` 對單一 statement 檔可以正確返回 cursor description
- ✅ E1 self-report §R2.5 + features.sql MODULE_NOTE line 127-129 都記載 split decision rationale + 下游 Python loader 改三次獨立 `cur.execute()` 載入

**對抗反問**：3 檔可能反向引入 transactional inconsistency（main + sibling 跑在不同 read snapshot 看到不同 trigger row）？
- A：對 Stage 0R replay 而言 acceptable — `market.liquidations` 是 append-only 寫入（V095 PK include ts），window 是 `window_days` 內的歷史資料，PA 設計階段已接受 read-snapshot consistency 不需強 serializable。若下游 caller 需嚴格一致，應在 caller 包 BEGIN/COMMIT — 是 caller 責任不在本 SQL scope → OK

### [HIGH-2] `quiet_window_sec=0` + bar-boundary partial leak → **CLOSED**（per PA verdict D）

**驗證**：
- ✅ PA arbitration verdict D 完整套用：
  - `entry_mid = k_entry.open::float8`（features.sql line 278）— 非 `(open+close)/2`
  - `exit_mid = k_exit.open::float8`（features.sql line 280）— 非 `(open+close)/2`
  - LATERAL `SELECT ts, open`（lines 282 + 292）— close column 移除（之前 round 1 是 `SELECT ts, open, close`）
- ✅ 欄位名 `entry_mid` / `exit_mid` **保留**（下游 Python `_compute_gross_bps()` contract lock）
- ✅ `ts >=`（非 strict gt）保留 — per PA verdict D rationale，spec line 231 「next available tradable mark」語意
- ✅ MODULE_NOTE 加 HIGH-2 verdict D 中文 rationale（features.sql line 82-97）含 boundary case 解釋 + non-boundary case 對稱性論述
- ✅ Deviation #7 加入 MODULE_NOTE deviation list（line 121-122）
- ✅ Sibling `cluster_n_eff.sql` 不涉 entry/exit_mid（只算 n_clusters_60m）；不需鏡像此 fix → 正確 scope

**grep 驗證**：`grep -E '\(open[[:space:]]*\+[[:space:]]*close\)'` 在 3 個 SQL 檔 = 0 actual hit（只剩 MODULE_NOTE 中說明「為什麼移除」的文字 references）→ 無殘留舊邏輯。

### [MIT MUST-LAND] E1 self-report 持久化 → **CLOSED**（with operational caveat）

**驗證**：
- ✅ Self-report 存在於 worktree branch HEAD：`.claude/worktrees/e1-s0r-1-r2/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_1_sql_query_self_report.md`
- ✅ Round 2 delta appended（line 285-447），10 subsections（R2.1 ~ R2.11）涵蓋 round-1 結果 / 修改清單 / CRIT-1/CRIT-2/HIGH-1/HIGH-2/MIT 3 SHOULD-FIX 各別 rationale / Mac sqlparse smoke / governance compliance / operator next steps
- ⚠️ **Operational caveat**：Self-report **未在主 working tree** `srv/docs/CCAgentWorkSpace/E1/workspace/reports/` 出現 — 因為它在 feature branch worktree（per worktree convention 預期；merge 到 main 才會 land 主樹）。Round-2 prompt 描述「file present at `srv/docs/...`」字面意義可被解讀為主樹；實際語義是「self-report 應存在於該 logical path（含 branch HEAD）」— 滿足。

### [MIT SHOULD-FIX 1] pg_typeof cast guard → **CLOSED**（doc-only deferred）

**驗證**：
- ✅ features.sql MODULE_NOTE 「依賴」段（line 80）明確標註 market.liquidations 的 qty/price 為 `real`（V002 + V095）
- ✅ E1 self-report §R2.7 SHOULD-1 解釋：runtime cast guard 為 caller-side concern，建議 S0R-3 wire 加 `cur.execute("SELECT pg_typeof(qty), pg_typeof(price) FROM market.liquidations LIMIT 1")` runtime assert
- ✅ 不在本 SQL scope，下游 S0R-3 wire 處理 — 合理 deferred

### [MIT SHOULD-FIX 2] 288 PRECEDING semantic doc → **CLOSED**

**驗證**：
- ✅ trigger_with_pct CTE 註釋（features.sql line 195-196）明確解釋「ROWS BETWEEN 288 PRECEDING：24h × 12 5m桶/h = 288 行；非時間窗，是行數窗（sparsity 高時實際時間跨度可能 > 24h）」
- ✅ MODULE_NOTE deviation #3（line 106-110）補述「per-symbol sparsity 高時（如 POLUSDT 1 trigger/day），實際 288-row 跨度可能 > 24h；下游 Python 用此欄位做 cluster 稀有度估計，semantic 為『相對自身過去 288 個曾觸發桶的 magnitude rank』」

### [MIT SHOULD-FIX 3] LATERAL ORDER BY 保護 invariant → **CLOSED**

**驗證**：
- ✅ forward_returns CTE 註釋（features.sql line 257-260）明確標註「MIT SHOULD-3 保護：ORDER BY ts ASC LIMIT 1 依賴 TimescaleDB ChunkAppend chunk-order-aware planner 早期終止（empirical Linux PG dry-run 已驗 Custom Scan Order: klines.ts）；future planner regression 若失此 order 可能掃全 chunk，請勿移除 ORDER BY」

### [LOW-2] `expected_dir CASE` 無 ELSE clause → **CLOSED**

**驗證**：
- ✅ `trigger_with_pct.expected_dir` CASE 加入 `ELSE NULL` defensive marker（features.sql line 206-207），含解釋註釋：「LOW-2 defensive：density_gated 已 filter mixed，此處不應達；ELSE NULL 是防未來 refactor 繞開 mixed filter」

### [LOW-1] entry_mid 用 mid vs 8b close-only inconsistency → **CLOSED**（subsumed by HIGH-2 verdict D）

PA verdict D 改 entry/exit 為 open-only 後，與 8b close-to-close 仍非 1:1 鏡像（8c 採 open-to-open）但 PA arbitration §3 解釋：8c 短 horizon 1-15m + bucket_end_ts 對齊性使 open-to-open 是更合理選擇。MODULE_NOTE 已捕捉此 cross-spec rationale。→ subsumed by HIGH-2 closure。

---

## Round-1 MED 未獨立修復（不阻 E4）

| MED | 狀態 | E2 判斷 |
|---|---|---|
| [MED-1] Sibling panel coverage cohort 過濾 | 部分結構性化 — split-3-files 後 panel_coverage.sql 仍同 round 1 計算 raw `total_rows/distinct_symbols/earliest_ts/latest_ts/span_days` + cohort_observed/cohort_coverage_pct；無 `*_cohort` 變體欄位 | E2 同意 deferred — 下游 Python 可選擇用 `cohort_observed >= 7` 替代 `span_days >= 7` 做更嚴格 gate；contract 不破壞 |
| [MED-2] LATERAL 無 upper-bound | 未修 | Deferred — C1 採集穩定後此 case 應少見；E1 self-report 未承諾本 round 修；對 S0R-2 stale entry 過濾推到 Python 層為合理 trade-off；建議下游 Python 加 `entry_ts - bucket_end_ts > 5min` warning |
| [MED-3] Spec 5m cooldown | 未修 | Deferred — PA 設計 contract sibling #2 n_eff 補償替代 5m cooldown 是 accepted；spec wording 待 PA 仲裁是否 amend spec wording |
| [MED-4] dominant_side CASE 重複 sub-aggregation | 未修 | Deferred — MIT round 1 PG dry-run 實測 < 30s 已通過；E1 自評「不重構，保持簡單」是合理 trade-off |

E2 對 round-2 self-report §R2 未提及 MED-1/2/3/4 明示處理的態度：**APPROVE**。Round-1 review 已將 MED 標為「建議修，可併到 rework round」未強制；E1 round 2 將精力集中在 2 CRIT + 2 HIGH + LOW-2 + MIT 3 SHOULD-FIX 是合理優先級。

---

## Regression Check（round-2 changes 未引入新 issue）

| Item | 狀態 | 驗證 |
|---|---|---|
| 5 CTE 結構 → 6 CTE（含 trigger_with_pct） | ✅ 合理擴展 | features.sql CTE 序列：raw_buckets → density_gated → trigger_with_pct → trigger_candidates → forward_returns → final_signals。新拆出的 trigger_with_pct 是 CRIT-1 必要結構（percent_rank 不能在 WHERE 直接用）|
| BB cor-side mapping（Buy=long-liq, Sell=short-liq）in CTE 1 | ✅ preserved | features.sql line 144-147 + 152-167：Buy → long_notional/long_event_count/long_liquidated；Sell → short_notional/short_event_count/short_liquidated；mixed → 後續 filter |
| Bybit cor-side `expected_dir` CASE: Buy → +1, Sell → −1, NULL else | ✅ correct | features.sql line 203-208：`'long_liquidated' THEN +1 / 'short_liquidated' THEN -1 / ELSE NULL`；密度 gate 已 filter mixed |
| `mixed` 桶仍正確過濾 | ✅ | features.sql line 187 `AND dominant_side IN ('long_liquidated', 'short_liquidated')` |
| `date_trunc('day', bucket_end_ts)` UTC 語義 | ✅ | features.sql line 346 `date_trunc('day', fr.bucket_end_ts)::date AS day_bucket`；PG `date_trunc` 默認 session timezone，但 `bucket_end_ts` 是 TIMESTAMPTZ 內部 UTC → trunc 結果與 session tz 有關。**Subtle caveat**：若 PG session tz = `Asia/Hong_Kong`，date_trunc 會用 HKT 對日；若需嚴格 UTC，應 `date_trunc('day', bucket_end_ts AT TIME ZONE 'UTC')`。此為 round-1 既有議題未升級為 finding（spec 未強制 UTC）；下游 Python `report.py` 應確保 PG session tz 設置一致。不阻 E4 |
| `notional_pct_24h` 用 `ROWS BETWEEN 288 PRECEDING` 沒被誤改 17280 | ✅ | features.sql line 212 + cluster_n_eff.sql line 108 都是 288 |
| psycopg2 `%(name)s` named-param style 一致 | ✅ | 3 檔全用 named-param；features.sql 含 11 個 real param（不含 `%(name)s` 那是 doc 解釋）+ panel 2 個 + sibling 8 個 |
| `>=` boundary semantic 維持（per PA verdict D）| ✅ | features.sql line 286 + 296 都是 `ts >= tc.bucket_end_ts + ...`；不是 strict gt |
| LATERAL SELECT 縮窄到 `(ts, open)` | ✅ | features.sql line 282 + 292 都是 `SELECT ts, open`；close 移除 |
| 跨平台路徑（禁 /home/ncyu / /Users/[^/]+）| ✅ 0 hit | 3 SQL 檔 grep 全乾淨 |
| 中文 MODULE_NOTE + inline comment | ✅ | 3 檔 MODULE_NOTE + inline 全中文；技術詞保留英文（LATERAL / percent_rank / ChunkAppend / cor-side / DOMINANT_SIDE_RATIO） |
| 文件大小（800 / 2000 line cap）| ✅ | 最大 features.sql 352 LOC 遠低於 800 警戒；分檔後每檔都更乾淨 |

---

## 0 個新 Issues Discovered

對 round-2 修改逐項對抗反問後 0 個新 issue：

- **Q1**：trigger_with_pct CTE 加 percent_rank 是否影響 main query plan / runtime？
  → A：MIT round 1 PG dry-run 實測 4-24ms（well under 30s）；round 2 拆兩層後額外 CTE 是邏輯 layer，PG planner 通常 inline；MIT round 2 dry-run 會再驗

- **Q2**：sibling `cluster_n_eff.sql` 加 percent_rank 後 plan 是否仍可早期終止？
  → A：sibling 不用 LATERAL 不用 ORDER BY + LIMIT 1，沒有「ChunkAppend 早期終止」依賴；percent_rank 是 window function 必然 scan full partition，與 round 1 對應的部分沒區別

- **Q3**：3 檔分離後 caller 用 3 個 cur.execute 跑 — 是否有 transactional consistency 風險？
  → A：append-only window 場景下 acceptable；spec 未強制 strict serializable；若需要由 caller 包 BEGIN/COMMIT

- **Q4**：features.sql 6 CTE vs round 1 self-report 提的 5 CTE — 是否 misaligned with documentation？
  → A：MODULE_NOTE line 72-76 + line 76「5 CTE 順序 → 6 CTE」描述（含 trigger_with_pct）— 文檔與實作一致；E1 self-report §R2.3 也明確說「CTE 計數從 5 變 6」

- **Q5**：sibling `cluster_n_eff.sql` `SELECT symbol, dominant_side, bucket_end_ts FROM trigger_with_pct` — 是否漏 column projection？
  → A：sibling 下游只需這 3 個 column（ordered + new_cluster_flag + final GROUP BY），projection 是設計級窄化；無 broken reference

- **Q6**：3 個檔之間如果 caller 用同一個 connection 但忘記 `BEGIN`，是否 snapshot 不一致？
  → A：本檔 read-only；append-only window；不阻 E4

---

## 對抗反問結果

### Q1：「`trigger_with_pct.percent_rank()` ROWS BETWEEN 288 PRECEDING AND CURRENT ROW 含 current row — 不是 lookahead bias 嗎？參考 `feedback_indicator_lookahead_bias.md`」

**評估**：`feedback_indicator_lookahead_bias.md` 的反模式是「`rolling(N).max()` 含 current bar → breach=current 是 N-bar max → 必然 mean-revert」— 那是因為使用「breach 訊號 = current 高過自己」做 entry 決策，自相關必然產生負 returns。本案不同：percent_rank 用於 magnitude gate（「自己在 288 桶中是否相對稀有」），spec v0.3 §magnitude_ok 設計目的就是「相對自身歷史 high percentile」做 trigger gate。current 含自身是 question 的本質（否則「自己是否 high percentile」這個 question 無解）。**不違反 lookahead bias 原則**。

### Q2：「sibling cluster_n_eff 計算 `n_clusters_60m` 用 60min gap，但主檔 trigger 是 5m bucket — 60min 內可能有 12 個 5m trigger，sibling 卻只算 1 個 cluster。`n_eff` < `n_trigger` 必然，這個比例會在 DSR penalty 怎用？」

**評估**：DSR formula 用 `n_eff` 做 sample size 補償（adjusted for autocorrelation）。`n_eff < n_trigger` 是預期：60min 內連續觸發具強自相關，視為「同一 cluster 重複 sampling」是統計上合理。PA design §2.4 + R2.4 + cluster_n_eff.sql MODULE_NOTE 都解釋此設計。**OK**

### Q3：「3 檔之間 caller 跑 main + sibling，若 ＋ 1ms 間有新 liquidation 寫入 `market.liquidations`，main 與 sibling 看到的 trigger row 數量會不一致 — n_eff/n 統計失真嗎？」

**評估**：對 Stage 0R replay 而言，window 是 7d/14d/28d，1ms 差距比例 < 0.001%，sampling 噪音 dominate；不阻 E4。若需要絕對一致應由 caller 包 `BEGIN ISOLATION LEVEL REPEATABLE READ` — 不在本 SQL scope。**OK**

### Q4：「`date_trunc('day', bucket_end_ts)` 不顯式指定 UTC — PG session tz 若是 HKT 會用 HKT 對日。下游 Python max_day_share 計算單日集中度地板（≤ 25%）會不會因為 tz 不一致而 across reports 比較失真？」

**評估**：subtle issue but **round-1 既有**未升級 finding；spec 未強制 UTC；下游 Python `report.py` 應確保 PG session tz 設置 statement-level（`SET TIME ZONE 'UTC';`）或 caller 顯式 cast `bucket_end_ts AT TIME ZONE 'UTC'`。E2 round 2 不引此為新 finding（round 1 也未提）— 但可記錄為「**LOW（doc-only deferred）**」待 S0R-3 wire 處理。

### Q5：「`expected_dir CASE` 加 ELSE NULL 後若未來 refactor 繞開 density_gated mixed filter（如 caller 直接接 raw_buckets 跑），expected_dir = NULL 會傳到 gross_bps formula — 但 features.sql line 335-337 已加 `WHEN entry_mid IS NOT NULL AND ... AND exit_mid IS NOT NULL AND ... THEN ... ELSE NULL` — expected_dir 是否真的 propagate NULL？」

**評估**：expected_dir 是 INT NULL 流到 final_signals 後 line 337 公式 `10000 × expected_dir × (exit_mid - entry_mid) / entry_mid`：當 expected_dir = NULL，整個 expression = NULL（PG NULL semantics）→ gross_bps = NULL → net_bps = NULL → 下游 Python `_kline_miss_rate()` 會 catch as miss/NULL。**Defensive fallback OK**

---

## 結論

**APPROVE → E4 regression Ready**

E1 round 2 改動正確、徹底、無 regression：
- 2 CRIT 全 closed（notional_pct_floor gate + sibling mirror）
- 2 HIGH 全 closed（split-3-files + PA verdict D open-only）
- 1 LOW closed（expected_dir ELSE NULL）
- MIT MUST-LAND closed（self-report at branch HEAD with R2 delta）
- MIT 3 SHOULD-FIX closed（pg_typeof doc / 288 semantic doc / LATERAL ORDER BY invariant doc）
- 4 round-1 MED deferred（合理優先級，不阻 E4）
- 0 新 CRIT / HIGH / regression
- §5 race check 5 條全 PASS

下一步：
1. ✅ E2 round-2 review report → 本檔
2. → **PM dispatch MIT round 2 Linux PG empirical dry-run x2**：3 檔分別 execute + trigger_candidates 加 notional_pct_floor 後 row count（vs round 1）+ main query plan 仍 < 30s + sibling cluster_n_eff 與主查詢 trigger row count 嚴格一致
3. → **PM dispatch E4 regression**（與 MIT round 2 並行 OK；可同時 launch）
4. PM merge to main 待 E2 round-2 + MIT round-2 + E4 三方 APPROVE

---

E2 ROUND 2 REVIEW DONE: **APPROVE** · report path: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8c_s0r_1_e2_review_round2.md`
