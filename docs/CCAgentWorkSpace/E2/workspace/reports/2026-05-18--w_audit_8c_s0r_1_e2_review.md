# E2 Adversarial Review — W-AUDIT-8c 8C-S0R-1 SQL Query Template

- **日期**：2026-05-18
- **審查目標**：`origin/feature/w-audit-8c-s0r-1-sql-query-template` HEAD `bd1b2443`
- **單一新檔**：`sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`（+428 LOC）
- **E1 self-report**：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_1_sql_query_self_report.md`
- **PA 設計**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_stage_0r_packet_design.md` §2.3
- **Spec**：`docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md` v0.3
- **Schema**：V002（market.klines, market.liquidations）+ V095（liquidations PK 升級到 (symbol, ts, side, qty, price)）
- **8b 先例**：`sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` + `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py`

## 最終裁決

**RETURN to E1** — 2 CRITICAL（spec 對齊 + sibling 同步）+ 1 HIGH（PA 多檔→單檔契約漂移）+ 4 MEDIUM + 2 LOW

E1-rework needed：**YES**。最重要 finding 是 `notional_pct_floor` 完全缺漏 gate 與 parameter，這直接違反 spec v0.3 §"magnitude_ok"，影響 Stage 0R 的 K_total 構造與 PASS-cell 統計，屬於 alpha-bearing math 漂移而非 cosmetic。

---

## 改動範圍

| File | LOC | 動作 |
|---|---|---|
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` | +428 | 新檔 |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_1_sql_query_self_report.md` | +281 | 新檔（E1 sign-off report） |
| `docs/CCAgentWorkSpace/E1/memory.md` | +320 | E1 memory 追加 |

3 files / +1029 LOC. 改動範圍乾淨，僅本任務 scope。

---

## §5 Multi-session race check

- [x] **5a** `git fetch origin` 已執行；2h 窗內 origin/main 最新 5 commits 全為 docs/governance/QA report（75e29265 / 9a6787ce / eebda658 / 3b5bc59d / 25413e96），與本 SQL 檔零 overlap → PASS
- [x] **5b** `git status --porcelain` 顯示 4 untracked（PA report / 2 QA report / 1 memory file），均為先前 session 殘留與本次 review 無關 → PASS
- [x] **5c** 0 unknown WIP 出現在本 PR diff 內 → PASS
- [x] **5d** review 過程中只讀 + 寫一份 report，未 commit/stash → PASS
- [x] **5e** review 期間 origin/main 0 push → PASS

---

## 8 條 reviewer checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ⚠️ 部分 | 5 deviations E1 documented；本 review 找出第 6 個未 documented critical deviation（notional_pct_floor 缺漏 gate） |
| 沒有 except:pass 或靜默吞異常 | N/A | 純 SQL，無異常 handling |
| 日誌使用 %s 格式（非 f-string） | N/A | 純 SQL |
| 新 API 端點 / `_require_operator_role()` | N/A | 純 SQL，無 endpoint |
| `except HTTPException: raise` 順序 | N/A | 純 SQL |
| `detail=str(e)` → `"Internal server error"` | N/A | 純 SQL |
| asyncio 路由中無 blocking threading.Lock | N/A | 純 SQL |
| 沒有私有屬性穿透 | N/A | 純 SQL |

純 SQL 檔，traditional 8 條多 N/A；改用 OpenClaw 9 條 §3。

---

## OpenClaw 9 條 §3 checklist

| Item | 狀態 | 備註 |
|---|---|---|
| 跨平台 grep（禁 /home/ncyu / /Users/[^/]+） | ✅ PASS | SQL 檔本身 0 hit；E1 self-report §6.A 行 143 有 `cd /home/ncyu/Projects/TradeBot/srv` 但屬於 MIT prep 文檔不是 production code，屬 acceptable |
| 注釋規範（中文為主） | ✅ PASS | E1 MODULE_NOTE + inline 全中文；保留技術名詞英文（LATERAL / percent_rank / DOMINANT_SIDE_RATIO / cor-side） |
| Rust unsafe 零容忍 | N/A | 純 SQL |
| 跨語言 IPC schema 一致 | ⚠️ HIGH | 看 [HIGH-1] PA 多檔→單檔 sentinel-split 契約漂移 |
| Migration Guard A/B/C | N/A | 非 V### migration（read-only query） |
| healthcheck 配對 | N/A | 非被動等待 TODO |
| Singleton 登記 | N/A | 無 singleton |
| 文件大小 800/2000 行 | ✅ 428 LOC | 遠低於 800 警戒；E1 self-report 解釋 ~150 LOC PA 估算 vs 428 LOC 實際差距為 verbose 中文 MODULE_NOTE + sibling materialized + double newlines |
| Bybit API 改動 | N/A | 0 API 改動 |

---

## 對抗反問結果

### Q1：「你說『nominal_pct_24h percentile 是 PA 17280 typo 的 fix』— 但 spec v0.3 §magnitude_ok 第 191 行明確要求 `notional_percentile_24h >= notional_pct_floor` 作為 gate。你 SQL 計算了 percentile 卻沒應用 gate，也沒納入 10 個 parameter 列表。怎麼解？」

**E1 回答推測**（self-report §3 + §4 deviation #5 沒提及）：未答；spec 對齊缺漏。

**評估**：CRITICAL。spec K_total 公式（spec line 264）明確 `3 notional_pct_floor` 是 11_664 grid 維度之一。E1 SQL 缺漏此 gate → Stage 0R replay 永遠跑「無 notional_pct_floor 過濾」版本 → 比較 PASS-cell 時 over-trigger → 統計噪音膨脹 → DSR 估計偏向悲觀（更多 lookbacks）但 avg_net_bps 估計偏向被 dilution。**屬於 alpha-impacting math drift**，非 hygiene。

### Q2：「你說 `>= bucket_end_ts + quiet_window` 是 strict as-of join — 但 spec line 229 寫 'forward returns start **after** the decision timestamp'，PA design line 261 寫 'at OR after'，且 PA line 653 對應 'MUST be ≥ ... quiet_window=0 special case test for boundary correctness'。你採 `>=` 在 quiet_window=0 + bucket_end_ts 落於 1m kline 邊界（如 12:34:00.000）時有沒有 leak？」

**評估**：HIGH。具體 scenario：
- bucket_end_ts = 12:34:00 整（剛好 minute boundary，liquidation 發生在 12:34:00）
- entry_anchor = 12:34:00 + 0 = 12:34:00
- `k_entry.ts >= 12:34:00` 命中 12:34:00 kline（其 close ts 是 12:34:59）
- entry_mid = (open at 12:34:00 + close at 12:34:59) / 2
- close at 12:34:59 包含 liquidation 後 59 秒的 price action，已含 reversion 訊號 → entry_mid 偏向 reversion，gross_bps **underestimated**

修法 option：
- (a) 強制 `quiet_window_sec > 0`（最簡單，spec 0/30/60 sweep 中 0 cell 不適用）
- (b) `ts > bucket_end_ts + quiet_window`（strict gt 而非 gte）
- (c) 改用 close-only 而非 (open+close)/2（與 8b precedent 一致）
- (d) PA spec amend：明確說明 mid 入場含 bar 內 partial leak，視為 noise floor

E1 自己 §6.D Sanity invariants 寫 `entry_ts >= bucket_end_ts (no leakage)` — 「無 leak」是錯的，bar-boundary case 有 partial leak。

### Q3：「你說 sentinel-split 是 8b precedent — 但 8b 是 single statement 純檔。`-- @SIBLING:NAME` 是你發明的新契約。S0R-2 owner 沒讀 self-report §8 直接 `cur.execute(file_content)` 會怎樣？」

**評估**：HIGH。psycopg2 `cur.execute()` 支援 multi-statement，但只回傳最後一個 statement 的 `cur.description`/`fetchall()`。若 S0R-2 不 sentinel-split，會 silently 只拿到 sibling #2 的 n_clusters_60m 結果，主查詢 features 全失。**Silent failure mode**，沒有 schema mismatch error。

PA design §2.3 將 3 個查詢呈現為 3 個獨立 code block，沒明確要求合併 1 檔。E1 自行決定合併 + 發明 sentinel 規範，屬於 contract drift 應退 PA 確認，或 split 成 3 個 .sql 檔（main + sibling_panel_coverage + sibling_cluster_n_eff）。

### Q4：「`(0.6 * sum(qty*price))` 在 dominant_side CASE 出現 4 次 + sibling #2 又 4 次（共 8 次）— 重複計算 sum aggregation，PG planner 會 optimize 還是 evaluate 8 次？對 12_096 rows × 32 symbols × 7d panel 影響？」

**評估**：MEDIUM 效能。PG GROUP BY 內 aggregation 通常 planner 會 cache aggregation，但 CASE WHEN inside SELECT list 每一次出現都會被當作 expression evaluation。對 raw_buckets 結果 ~10k-100k rows 級別應該可接受，但 EXPLAIN ANALYZE 應驗證沒 quadratic blowup。可重構 raw_buckets 加 `(long_notional, short_notional, total_notional)` intermediate columns + 後續 CTE 用這些 alias，會更乾淨且 plan 更穩定。**MEDIUM**，效能與可讀性次要 issue。

### Q5：「`market.klines` 在 entry / exit LATERAL 都 filter `timeframe='1m'`。如果某 symbol 的 1m kline 在 bucket_end_ts + horizon 時間點缺資料（C1 採集 gap），entry_ts 仍是「最近一根」可能是幾小時後。LIMIT 1 不會抓錯嗎？」

**評估**：MEDIUM。具體：若 12:34 後 12:35-15:00 都缺 1m kline，entry_ts = 15:00，entry_mid 是 15:00 kline 的 mid。這 entry 與 bucket_end_ts 已差 2.5h，entirely不同 market regime。E1 沒加 upper bound（如 `ts <= bucket_end_ts + INTERVAL '1 hour'`）。

下游 Python `_kline_miss_rate()` 不會 catch — 因為 LATERAL **回傳了**一筆，只是時間差過大。應加 entry_age_min / exit_age_min 欄位讓 Python 過濾（>5min 視為 stale）。**MEDIUM**，影響 false-negative 統計。

### Q6：「`entry_mid = (k_entry.open + k_entry.close) / 2.0` 用 mid；8b precedent line 125-129 用 close-to-close。哪個對？」

**評估**：PA 設計 §2.3 line 263 寫 `(k_entry.open + k_entry.close) / 2.0` — PA 明確要 mid，E1 follow PA。**OK** (PA contract decision, deferred to PA)，但與 8b 不一致應有 cross-spec rationale。E1 在 SQL comment line 195-198 解釋 8c 1-15min 短 horizon 對 open gap 更敏感，是 reasonable 但未經 PA endorsed 的 rationale。**LOW**。

### Q7：「Spec line 230 'replay must dedupe by `(symbol, dominant_side, floor(ts/300_000))` plus a **5m cooldown** to avoid double-counting near-bucket-edge events'。你的主查詢沒 5m cooldown，t=12:30 與 t=12:35 連續 2 桶若都觸發，都進 final_signals，會被 Python 視為 2 個獨立 trigger。怎麼處理？」

**評估**：MEDIUM。E1 主查詢輸出 raw 5m bucket level rows（無 cooldown），sibling #2 用 60m gap 計算 cluster-aware n_eff 來補償自相關。語意上 Python 可區分 trigger count（主查詢）與 n_eff（sibling #2）。但 spec wording 明確要求 5m cooldown 已在 SQL 層 applied，不是 Python compensation。**MEDIUM** — 與 spec wording 不完全對齊但 functionally 可接受（autocorr discount 補償）。應 PA 確認此 split 是否 acceptable contract。

### Q8：「`COUNT(DISTINCT symbol)` 在 panel coverage sibling 沒 cohort filter — 若 market.liquidations 有非 cohort 25-sym 之外的舊資料（如 C1 採集前測試殘留），earliest_ts 會被拉低，span_days 過高，gate 假 PASS。」

**評估**：MEDIUM。Sibling #1 line 322-326 raw stats 全 panel，line 327-331 cohort 過濾 stats。Gate 邏輯應該用 cohort 過濾後 stats 而非 raw — 但 SQL 都回傳了，下游 Python 自己選用。**MEDIUM**：建議在 SQL 內把 span_days 也加 cohort 過濾版本（`span_days_cohort`）讓 Python 清晰選擇。

### Q9：「`expected_dir CASE` 沒 ELSE — 若上游 density_gated 過濾失效或被未來改動繞過 'mixed' filter，expected_dir = NULL，下游 net_bps 計算返回 NULL，silently dropped。應加 ELSE 0 + Python upstream 顯式報錯。」

**評估**：LOW. CTE 2 line 149 明確 filter `dominant_side IN ('long_liquidated', 'short_liquidated')`，所以 CTE 3 不會收到 mixed。但作為 defensive coding 應加 `ELSE NULL` 顯式 marker 或讓 PG raise（unrealistic for production query）。**LOW**.

### Q10：「`bucket_5m_epoch BIGINT` 是 **秒** epoch（floor(epoch/300)*300）；8b precedent 用 `signal_ts_ms BIGINT` 是 **毫秒**。S0R-3 CLI 切回填參數時若混用 ms/s 會錯。你選秒 vs ms 的判斷？」

**評估**：LOW. E1 選秒（與 Rust LiquidationPulseAggregator WINDOW_5M_MS 的 ms 文化不一致，但與 SQL `extract(epoch FROM ts)` 自然 unit 一致）。為 S0R-3 unblock：**E2 verdict = 秒（seconds）**，文檔即可 `bucket_5m_epoch * 1000` 轉 ms 如需。**LOW**，需明確 contract 簽 S0R-2/S0R-3.

---

## Findings 總表

### CRITICAL

#### [CRIT-1] `notional_pct_floor` gate 完全缺漏

**位置**：`sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` CTE 3 lines 168-185；sibling #2 trigger_candidates lines 389-398；parameter list lines 19-35

**證據**：
- Spec v0.3 line 191：`magnitude_ok = ... AND notional_percentile_24h >= notional_pct_floor AND ...`
- Spec v0.3 line 215：`notional_pct_floor: 0.90 / 0.95 / 0.98` 是 sweep axis
- Spec v0.3 line 264：`3 notional_pct_floor` 是 K_total = 11_664 的維度之一
- E1 SQL CTE 3 WHERE clause（line 182-184）只有 `side_dominance_floor` + `cluster_notional_floor_usd`，**無 notional_pct_floor**
- E1 SQL parameter list（lines 19-35 + self-report §3）10 個 param，**無 `notional_pct_floor`**
- Sibling #2 同樣缺漏

**為什麼 CRITICAL**：
- 直接違反 spec v0.3 magnitude_ok 定義
- Stage 0R 永遠跑「無 notional_pct_floor 過濾」版本 → over-trigger（多了 3× 應被 percentile gate 剔除的 cluster）
- DSR 計算與 PASS-cell 統計都會被 dilution
- 是 alpha-bearing math drift 不是 cosmetic — 直接影響策略 promotion 決策

**修法**：
1. Parameter list 加第 11 個 `%(notional_pct_floor)s DOUBLE PRECISION — 0.90/0.95/0.98 sweep`
2. CTE 3 WHERE clause 加 `AND percent_rank() OVER (...) >= %(notional_pct_floor)s::float8`
   - 注意：percent_rank 在 WHERE 不能直接用（window function evaluation timing）；需 wrap 一層 subquery 或加 HAVING-like CTE
   - 推薦：把 trigger_candidates 拆兩層，先計算 notional_pct_24h，再 WHERE percent_rank
3. Sibling #2 同步加此 gate（先需要算 notional_pct_24h，目前 raw_buckets 沒算 → 需 enrich sibling #2 的 CTE）
4. 文檔同步：MODULE_NOTE 加參數說明，sibling #2 doc 加 gate 已套
5. Self-report §3 / §4 補 deviation #6 + 修正論述

**Owner**：**E1-rework**（spec 對齊 + 結構性 SQL refactor，超出 typo/lint 範疇）

---

#### [CRIT-2] Sibling #2 n_eff helper 與主查詢 trigger_candidates 不一致

**位置**：Sibling #2 lines 355-388（raw_buckets）+ 389-398（trigger_candidates）

**證據**：
- Sibling #2 raw_buckets 沒計算 `notional_pct_24h`（line 355-388 缺少對應 window function）
- Sibling #2 trigger_candidates（line 389-398）即使要加 notional_pct_floor gate，目前 source CTE 也沒這欄位
- 主查詢 trigger_candidates（line 152-185）computes `notional_pct_24h` via percent_rank window
- 兩個 CTE「trigger_candidates」名相同但內容不同 → semantic divergence
- 即使無 [CRIT-1]，這 divergence 依然 break n_eff 與 main 之間的「同樣樣本」假設

**為什麼 CRITICAL**：n_eff cluster-aware 估計依賴「主查詢 trigger 與 sibling 計算的 cluster 是同一批」，分歧會讓 n_eff/n 比例失真，DSR penalty 計算扭曲。是 [CRIT-1] 連動 issue 但獨立 surface。

**修法**：與 [CRIT-1] 一併修；確保 sibling #2 raw_buckets + trigger_candidates 與主查詢結構嚴格鏡像（同 CTE shape、同 gate set）。建議 refactor：把共用部分提取為 macro-comment 範本，或合併 main 與 sibling #2 為單一 query 用 multi-CTE 同時輸出 features + n_clusters_60m（cost only 50-100 LOC 額外）。

**Owner**：**E1-rework**（同 CRIT-1）

---

### HIGH

#### [HIGH-1] PA 多檔 → 單檔 sentinel-split 契約漂移

**位置**：lines 300-353（sibling sentinel markers `-- @SIBLING:PANEL_COVERAGE_CHECK` + `-- @SIBLING:CLUSTER_N_EFF_HELPER`）

**證據**：
- PA design §2.3 line 174-298 將主查詢、sibling #1、sibling #2 呈現為 **3 個獨立 markdown code block**
- PA 沒明確要求合併 1 檔
- E1 self-report §8 line 232-239 規範 regex split：`re.split(r'^-- @SIBLING:([A-Z_]+)\n', sql_full, flags=re.MULTILINE)`
- 8b precedent 是 **single statement** 純檔；E1 sentinel-split 是新發明契約
- psycopg2 `cur.execute(multi_stmt)` 會跑 all statements 但只回 last 一個 description — 若 S0R-2 不 sentinel-split → **silent failure**，主查詢 features 全失但無 schema mismatch error

**為什麼 HIGH**：
- 契約漂移 + silent failure mode + 沒 PA endorse
- S0R-2 chain 任一新 owner 沒讀 self-report §8 直接執行 = data loss without alarm
- 修法簡單：拆 3 個 .sql 檔
  - `w_audit_8c_liquidation_cluster_stage0r_features.sql`（main only）
  - `w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql`
  - `w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql`

**修法**：
- (a) 拆 3 檔（推薦，與 8b 風格一致 + 0 silent failure 風險）
- (b) 保留 1 檔 + sentinel split，需 PA 明確 endorse 並在 S0R-2 wire 強制添加 contract check（檢測 sibling count == 2，否則 raise）

**Owner**：建議 **E1-rework** option (a) 或 PA chain 補 contract amend option (b)

---

#### [HIGH-2] `quiet_window_sec=0` + bar-boundary bucket_end_ts 的 partial leak

**位置**：lines 227-247（forward_returns LATERAL `ts >= bucket_end_ts + quiet_window`）

**證據**：
- Spec line 229：`forward returns start **after** the decision timestamp`（强调 after）
- PA design line 261：`first kline mid **at OR after** bucket_end_ts + quiet_window`（PA 寫 OR after 即 `>=`）
- PA design line 653：`MUST be ≥ bucket_end_ts + quiet_window not >; quiet_window=0 special case test for boundary correctness` — PA 自相矛盾（既要 `>=` 又要 quiet_window=0 boundary 對嗎）
- 具體 scenario：bucket_end_ts = 12:34:00.000（exact minute boundary） + quiet_window=0 → `ts >= 12:34:00` 命中 12:34:00 kline → entry_mid = (open at 12:34:00 + close at 12:34:59) / 2 → close at 12:34:59 包含 liquidation event 後 59s 的 price action（含 partial reversion）→ entry_mid biased toward fair value → gross_bps **underestimated** 約 0.5-2 bps（視 reversion magnitude）

**為什麼 HIGH**：
- spec 0/30/60 sweep 中 quiet_window=0 cell 有 partial leak
- 對 5m primary horizon 影響 <5%；對 1m sensitivity horizon 影響可達 10-30%
- 不是 catastrophic leak（不會把 negative edge 變 positive），但偏 systematic
- 是 PA 文檔自相矛盾的 surface — 應 PA 仲裁

**修法**：
- (a) Spec amend：明確說明 mid 入場含 bar 內 partial leak，視為 noise floor；boundary case 例外不修
- (b) E1 改 strict gt：`ts > bucket_end_ts + quiet_window_sec` — 簡單一字之差
- (c) E1 強制 `quiet_window_sec >= 1`：禁止 0 cell；K_total 變 11_664 → 7_776（少 3 axis 變 2 axis）；需 spec 改
- (d) 改 entry 用 open-only：`entry_mid = k_entry.open::float8`；無 mid 平均則無 partial leak

**Owner**：**PA chain 仲裁**（PA design 自相矛盾）+ 若 PA 選 (b)/(c)/(d) → E1-rework

---

### MEDIUM

#### [MED-1] Sibling #1 panel coverage 未一致 cohort 過濾

**位置**：lines 320-333

**證據**：
- `total_rows` / `distinct_symbols` / `earliest_ts` / `latest_ts` / `span_days` / `latest_age_min` 全 panel（無 cohort filter）
- `cohort_observed` / `cohort_coverage_pct` cohort 過濾
- 若 panel 有非 cohort 25-sym 之外舊測試資料，`span_days` 過估，gate `≥7d` 假 PASS
- E1 自己 self-report §6.B 寫「~7d span」但實測值會被非 cohort symbols 拉開

**為什麼 MEDIUM**：影響 panel adequacy gate 判斷正確性，不影響策略 features 計算。

**修法**：加 `earliest_ts_cohort` / `latest_ts_cohort` / `span_days_cohort` 三欄位，下游 Python gate 用 cohort 版本。

**Owner**：**E1-rework**

---

#### [MED-2] LATERAL 無 upper-bound kline lookup → C1 採集 gap 假成功

**位置**：lines 227-247（forward_returns LEFT JOIN LATERAL）

**證據**：
- 若某 symbol 12:34 後 12:35-15:00 1m kline 全缺（C1 採集 gap），entry_ts = 15:00 kline（2.5h 後）
- entry_mid 與 bucket_end_ts 已差 2.5h，已是完全不同 market regime
- LATERAL LIMIT 1 不會回 NULL — 它**找到了**，只是時間差過大
- 下游 Python `_kline_miss_rate()` 無法 catch（沒 miss，只是 stale）

**為什麼 MEDIUM**：影響 false-negative cluster 統計；C1 採集穩定後此 case 應少見，但 historical 7d/14d/28d 窗有 audit-relevant gaps。

**修法**：LATERAL 加 upper bound `AND ts <= tc.bucket_end_ts + INTERVAL '5 minutes'`（entry）/ `+ horizon + 5min`（exit）；或加 `entry_age_min` / `exit_age_min` 欄位讓 Python stale filter。

**Owner**：**E1-rework**

---

#### [MED-3] Spec 5m cooldown 缺漏

**位置**：CTE 1-3（無 cooldown logic）

**證據**：
- Spec line 230：`replay must dedupe by (symbol, dominant_side, floor(ts/300_000)) plus a **5m cooldown** to avoid double-counting near-bucket-edge events`
- E1 主查詢輸出每個 5m floor bucket 為獨立 trigger；連續 t=12:30 + t=12:35 都觸發會被 Python 視 2 個獨立樣本
- Sibling #2 用 60m cluster gap 做 n_eff 補償，是 alternative compensation

**為什麼 MEDIUM**：spec wording 強調 SQL 層 dedupe，E1 推到 Python 層；functionally 可接受但 contract 漂移。

**修法**：(a) 加 5m cooldown CTE（reject 連續 5m 觸發中後者）；或 (b) PA 明確 endorse 用 sibling #2 n_eff 補償替代 5m cooldown，並 doc 此 contract decision。

**Owner**：**PA chain 確認契約** + 若 (a) → E1-rework

---

#### [MED-4] `dominant_side` CASE 重複 4× sub-aggregation 效能 risk

**位置**：CTE 1 lines 113-130 + sibling #2 lines 361-378

**證據**：`0.6 * sum(qty::float8 * price::float8)` 主 + sibling 各出現 4 次（共 8 次）；`sum(CASE WHEN side='Buy' THEN ... END)` 主 + sibling 各 4 次

**為什麼 MEDIUM**：PG planner 通常 cache aggregation，但 CASE 內 sum 可能 evaluate 多次。對 ~10k rows 影響 <100ms 應 OK 但 EXPLAIN ANALYZE 應驗證。

**修法**：raw_buckets 加中間欄位 `(_total_notional, _long_notional, _short_notional)`，後續 CASE 用 alias；可同時提升可讀性。

**Owner**：**E1-rework**（可與 [CRIT-1] / [CRIT-2] refactor 一同處理）

---

### LOW

#### [LOW-1] `entry_mid` 用 mid vs 8b close-only inconsistency

**位置**：lines 221-225

**證據**：PA 設計 line 263 明確要 mid `(open + close) / 2.0`，E1 follow PA；但 8b precedent 用 close-to-close。E1 SQL comment line 195-198 解釋為「8c 短 horizon 對 open gap 更敏感」是 reasonable rationale 但未經 PA endorsed。

**Owner**：**defer to PA**（PA contract 決定，不需 E1 改）

---

#### [LOW-2] `expected_dir CASE` 無 ELSE clause

**位置**：lines 172-175

**證據**：CTE 2 已 filter mixed；但 defensive coding 應加 ELSE NULL 顯式 marker 防未來 refactor 繞開 mixed filter。

**修法**：加 `ELSE NULL` 顯式。

**Owner**：**E1 obvious typo 級**（E2 可直接 fix）— 但因 [CRIT-1] 已需 E1-rework，併修

---

## 退回 E1 修復清單

**強制修**（CRITICAL / HIGH 必修才能再進 E2）：

1. **[CRIT-1]** 加 `notional_pct_floor` parameter + CTE 3 WHERE gate + sibling #2 同步 gate；參考 spec v0.3 line 191 magnitude_ok 定義；refactor trigger_candidates 為兩層 CTE 因 window function 不能在 WHERE 直接用
2. **[CRIT-2]** Sibling #2 raw_buckets 加 notional_pct_24h 計算 + trigger_candidates 加 gate；確保與主查詢 trigger_candidates 結構嚴格鏡像
3. **[HIGH-1]** Sentinel-split 契約漂移：option (a) 拆 3 個 .sql 檔（推薦，與 8b 一致） OR option (b) 保留並透過 PA chain 補 contract amend

**等 PA 仲裁**（HIGH 但 root cause 在 PA 文檔自相矛盾）：

4. **[HIGH-2]** quiet_window_sec=0 + bar-boundary partial leak：等 PA 選 (a)/(b)/(c)/(d) 後 E1 跟修

**建議修**（MEDIUM，可併到 rework round）：

5. **[MED-1]** Sibling #1 加 `*_cohort` 欄位
6. **[MED-2]** LATERAL 加 upper bound 或 age 欄位
7. **[MED-3]** PA 確認 5m cooldown contract decision
8. **[MED-4]** raw_buckets refactor 中間欄位 + 後續 CTE 用 alias

**LOW（可 round-trip 處理）**：

9. **[LOW-1]** 8b close-only inconsistency：PA contract decision，不需改
10. **[LOW-2]** `expected_dir CASE` 加 `ELSE NULL`

---

## Unblock 給 S0R-3

S0R-3 CLI 開放契約問題的 E2 verdict（per prompt）：

1. **psycopg2 binding 風格**：**`%(name)s` named-param style 確認**（8b precedent + E1 follow）。S0R-3 wire 用 `cur.execute(sql, {"window_days": ..., "symbols": list(symbols), ...})` 模式即可，psycopg2 自動 `text[]` 轉換。E1 SQL 有顯式 `::text[]` cast 屬於 redundant defensive 寫法，無需移除也不影響 S0R-3。
2. **`bucket_5m_epoch` units**：**秒（seconds）確認**。E1 用 `(floor(extract(epoch FROM ts) / 300.0))::bigint * 300` 自然 unit。S0R-3 若需 ms 對齊 Rust LiquidationPulseAggregator WINDOW_5M_MS 文化，自行 `* 1000` 轉換即可。S0R-3 owner 應在 CLI doc 中明確標註此單位避免混淆 8b 的 `signal_ts_ms`。

**重要警示給 S0R-3 owner**：若 S0R-1 RETURN 後 E1 採 [HIGH-1] option (a) 拆 3 檔，S0R-3 CLI 載入路徑需相應改為載 3 個 .sql 檔。先別把 sentinel-split 寫死。

---

## E2 Reflection

1. **對抗第一原則奏效**：E1 self-report §4 列出 5 個 documented deviation，看似 thorough；但對抗反問 Q1 直接打中第 6 個 undocumented critical deviation（spec line 191 magnitude_ok 漏 `notional_pct_floor` gate）。Lesson：E1 self-report 的「我已對齊 spec」聲明必須逐項對 spec 原文比對，不能信 E1 摘要。
2. **PA 文檔自相矛盾要 surface**：HIGH-2 的 PA design line 261 `>=` vs PA design line 653 `quiet_window=0 boundary correctness` 是 PA 沒處理乾淨的 ambiguity。E1 follow PA literal 寫了 `>=` 而沒問。E2 對抗反問捕捉到此 ambiguity，退回 PA 仲裁是正確 escalation。
3. **Silent failure mode 比 schema mismatch 更危險**：HIGH-1 sentinel-split contract drift 不會 raise PG error — 下游若沒讀 self-report §8 會 silently drop 主查詢 features。這類 contract decision 應拆檔（structural 防呆）優於 in-doc 約定（文檔防呆）。
4. **「優化」claim 必驗**：E1 deviation #4 寫「LATERAL <30s 必要優化」，但沒 EXPLAIN ANALYZE 證據；MIT chain 需實測驗證。E2 review 不接受效能 claim 無 benchmark。
5. **跨 chain unblock 是 E2 職責一環**：S0R-3 兩個 contract 問題（psycopg2 binding + bucket epoch units）E2 review 都能順手 verdict，避免 S0R-3 反向 ping S0R-1 owner。
6. **Race check §5 全 PASS**：本次 review 期間無 sibling push，但 2h 窗檢查時看到 origin/main 最近 5 commits 全 docs/governance，再次驗證 §5a 例行檢查價值。

---

E2 REVIEW DONE: **RETURN to E1** · report path: `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--w_audit_8c_s0r_1_e2_review.md`
