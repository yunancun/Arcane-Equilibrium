# E1 — W2 V088 panel.btc_lead_lag_panel SQL skeleton 預寫

**日期**：2026-05-10
**性質**：W2 A4-C BTC→Alt Lead-Lag spec v1.2 SQL skeleton；NOT_RUN · NOT_DEPLOYED · NOT_COMMITTED（permission 攔截，commit + push 留 operator）
**前置**：
- Spec：`srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` (v1.2)
- 預留：V088 per memory `project_2026_05_10_sprint_n1_d0_readiness.md`
- 模板：V086 W6-3c (`87da03b7`) + sibling V085 funding_curve / V087 oi_delta_panel
- Guard 模板：`sql/migrations/templates/schema_guard_template.sql`

---

## §1 任務摘要

預寫 V088 SQL migration skeleton：
- CREATE SCHEMA panel（W-AUDIT-8a Phase B Tier 2 namespace, 對齊 V085/V087 sibling）
- CREATE TABLE panel.btc_lead_lag_panel（12 column per-snapshot vector layout）
- TimescaleDB hypertable (chunk_time_interval = 1 day in ms, BIGINT 時間維度)
- Retention 14d (paper-only window)
- Hot-path index (snapshot_ts_ms DESC, lead_window_secs)
- Guard A/B/C 三層 + idempotency
- 12 column COMMENT ON 完整覆蓋 + 1 SCHEMA + 1 TABLE COMMENT

PM sign-off 後 D+1 W2 V088 IMPL phase E1-δ (C-IMPL-2) 直接收（修小細節 + Linux PG dry-run + producer Python writer + Rust IPC slot），不需 E1 從零寫。

## §2 修改清單

| Path | LOC | Status |
|---|---|---|
| `srv/sql/migrations/V088__panel_btc_lead_lag_panel.sql` | 414 | NEW · STAGED · NOT_COMMITTED · NOT_DEPLOYED · NOT_RUN |

無既有檔修改。

## §3 結構（acceptance criteria 對照）

| Criterion | Status | 證據 |
|---|---|---|
| **(1) V088 SQL file land 在指定 path** | PASS | `srv/sql/migrations/V088__panel_btc_lead_lag_panel.sql` 414 LOC |
| **(2) 12 column 全列對齊 spec §4.1** | PASS | 完整 list verified by grep（snapshot_ts_ms / lead_window_secs / btc_lead_return_pct / btc_lead_return_pct_60s / btc_lead_return_pct_300s / btc_volume_z / btc_book_imbalance / alt_symbols / alt_xcorr / alt_expected_dir / regime_tag / source_tier）|
| **(3) 3 column (60s/300s shadow + R²(N) decay support) 必含** | PASS | `btc_lead_return_pct_60s REAL` / `btc_lead_return_pct_300s REAL` / lead_window_secs PK column 支撐 R²(N=60/120/300) decay curve evaluate |
| **(4) idempotency check** | PASS | CREATE SCHEMA IF NOT EXISTS · CREATE TABLE IF NOT EXISTS · create_hypertable if_not_exists=TRUE · add_retention_policy if_not_exists=TRUE · CREATE INDEX IF NOT EXISTS · COMMENT ON 可重跑覆蓋 |
| **(5) Guard A/B/C 完整** | PASS | Guard A (12 column shape verify) line 86-117 · Guard B (3 type check: real/real/text) line 184-217 · Guard C (index column DESC + lead_window_secs) line 247-265 |
| **(6) Hypertable + Retention** | PASS | chunk_time_interval = 86400000 ms (1 day) · retention `INTERVAL '14 days'` · 條件判斷 TimescaleDB extension 不存在則 plain table fallback |
| **(7) 5 conditions 對齊欄位齊備** | PASS | condition #3 (60s/300s shadow column R²(N) decay curve evidence) ✓ / condition #5 (regime_tag column + 'normal' DEFAULT，§7.2 evaluate FILTER 用) ✓ |
| **(8) DO/END $$ balanced + BEGIN/COMMIT pair** | PASS | DO: 6 / END: 6 · BEGIN: 1 / COMMIT: 1 |
| **(9) 跨平台兼容（無硬編碼路徑）** | PASS | grep `/Users/[^/]+/` + `/home/[a-z]+/` 0 命中 |
| **(10) Sign-off report** | PASS | 本 report |

## §4 12 column 對照 spec v1.2 §4.1

| # | Column | Type | Spec § alignment | Notes |
|---|---|---|---|---|
| 1 | `snapshot_ts_ms` | BIGINT NOT NULL | §4.1 row 1 | hypertable partition key, 1m grain epoch ms |
| 2 | `lead_window_secs` | INT NOT NULL | §4.1 row 2 | 主信號固定 120, PK 含此 column 為 future per-N 主信號分 row 預留 |
| 3 | `btc_lead_return_pct` | REAL | §4.1 row 3 | bps, 主信號 N=120, per §3.1.1 strict shift(N) |
| 4 | `btc_lead_return_pct_60s` | REAL | §4.1 row 4 | bps, N=60 shadow value (v1.1 condition #3 R²(N) decay curve evidence) |
| 5 | `btc_lead_return_pct_300s` | REAL | §4.1 row 5 | bps, N=300 shadow value (v1.1 condition #3) |
| 6 | `btc_volume_z` | REAL | §4.1 row 6 | per §3.1.2, rolling 1h baseline shift(1) |
| 7 | `btc_book_imbalance` | REAL | §4.1 row 7 | per §3.1.3, Bybit V5 orderbook top-10 |
| 8 | `alt_symbols` | TEXT[] NOT NULL | §4.1 row 8 | cohort symbol list per §2.2 7-symbol |
| 9 | `alt_xcorr` | REAL[] | §4.1 row 9 | per §3.2 主 N=120, 與 alt_symbols 同序 |
| 10 | `alt_expected_dir` | SMALLINT[] | §4.1 row 10 | −1/0/+1 per §3.3, 與 alt_symbols 同序 |
| 11 | `regime_tag` | TEXT NOT NULL DEFAULT 'normal' | §4.1 row 11 | v1.1 §9 condition #5, 'normal'/'extreme' |
| 12 | `source_tier` | TEXT NOT NULL DEFAULT 'cross_asset_btc_lead_lag' | §4.1 row 12 | 固定值, writer 強制 |

## §5 dual-layer σ schema 注意事項（per spec v1.2 §7.1 acceptance prerequisite）

V088 schema 本身**不直接**存 σ_60/σ_120/σ_300 (raw market σ)，因為這些是 evaluate 時從 source data (BTCUSDT 1m forward-return realized σ) 算出來的 derived metric。但 schema 必支撐 **D+12 paper edge report** 的 dual-layer σ acceptance 計算：

1. **L1 raw market σ (per MIT C-3 verify)** — σ_60=4.54 / σ_120=6.28 / σ_300=10.08 bps：
   - 不在 V088 schema, 由 BTCUSDT 1m kline source data 算 forward-return σ
   - V088 必支撐：`btc_lead_return_pct_60s` / `btc_lead_return_pct_300s` shadow columns 提供 N=60/120/300 三檔對照, 供 D+12 R²(N) decay curve evidence 計算（per §7.1 metric 4）

2. **L2 net edge σ_net=50-80 bps (EDGE-DIAG-1 baseline)** — paper edge gate threshold power calculation：
   - 不在 V088 schema, 由 paper engine fill 對齊 shadow log 反算 counterfactual net edge
   - V088 必支撐：`alt_expected_dir` SMALLINT[] 提供「if-followed-lead」counterfactual entry direction, 供 §7.2 SQL `(if-followed-lead net_edge) − (TA1m baseline net_edge)` 反算（per §7.1 metric 6 per-cohort-symbol counterfactual delta）

3. **PSR(0) ≥ 0.95 skew/kurt-aware formula 強制 (v1.2)** — 不影響 V088 schema, 是 D+12 evaluate phase 計算 metric

V088 schema 設計**不需修改**承載 σ 任何層（spec v1.2 §7.1 prerequisite condition 4 已明說「MIT C-3 D+1 σ verify 已交付，W2 IMPL 直接收」），但 60s/300s shadow column 是 dual-layer 支撐基礎；E2 review 必驗 3 columns 全在。

## §6 治理對照

| 項目 | Status | 證據 |
|---|---|---|
| CLAUDE.md §七 SQL migration Guard A/B/C 強制 | PASS | 3 個 Guard block (A/B/C) |
| CLAUDE.md §七 idempotency 強制 | PASS | 全 DDL 含 IF NOT EXISTS / if_not_exists=TRUE / DO block guard |
| CLAUDE.md §七 Linux PG dry-run mandatory | DEFERRED | D+1 W2 V088 IMPL phase E1-δ 必跑 Linux PG empirical query 兩次驗 idempotent + create_hypertable + retention 實 land 驗證 (per `feedback_v_migration_pg_dry_run`); Mac mock 不夠 |
| CLAUDE.md §七 注釋默認中文 | PASS | 新檔注釋默認中文 (per `feedback_chinese_only_comments` 2026-05-05); 有少數 inline 英文 (canonical SQL keyword + technical term + 對齊 V086 模板既有英文 docstring 風格) |
| CLAUDE.md §九 文件 800 行警告 | PASS | 414 LOC, 在 800 警戒線下 |
| 不擴大 PA spec 範圍 | PASS | 12 column 全對齊 spec §4.1 + 設計 PRIMARY KEY/index/retention 對齊 spec 文字; 無 順手優化 |
| 不修既有 V### migration | PASS | 純新建 V088 file |
| Sibling V085 / V087 panel.* CREATE SCHEMA pattern 對齊 | PASS | 改用 `CREATE SCHEMA IF NOT EXISTS panel;` 一行（縮 14 LOC, 對齊 V085 line 81 + V087 line 111 既有 sibling pattern） |
| 跨平台 grep 0 硬編碼路徑 | PASS | grep `/Users/[^/]+/` + `/home/[a-z]+/` 0 命中 |

## §7 不確定之處 / D+1 IMPL 階段需 E2 review 補充

1. **constraint name 命名約定**：本 file index name 用 `idx_btc_lead_lag_panel_ts_window`。需 E2 確認對齊 sibling V085 funding_curve / V087 oi_delta_panel 的 index naming pattern（如有 sibling 已 land 不同 pattern, 統一改）。
2. **chunk_time_interval = 86400000 ms (1 day) 是否 oversize？** 1m grain × 1440 row/day = 1440 row/chunk 不算大，按 sibling V006 既有 panel/market 1 day chunk pattern 設定。若 D+1 dry-run 發現 chunk size 不適（過大 compress 慢 / 過小 chunk 太多），需 E2 review 調整。
3. **alt_symbols / alt_xcorr / alt_expected_dir 三 array 同序對齊**：schema 層 PG array 不能 enforce length-equality cross-column → 必標明 application 層 invariant 於 COMMENT (line 290-292 已明)。D+1 W2 E1-δ 寫 btc_lead_lag_writer.py 必驗 array length 一致性，否則 downstream Strategy on_tick 會 index out of bounds 風險。
4. **Producer + Rust IPC slot deploy timing**：V088 schema land 與 Python btc_lead_lag_writer.py / Rust BtcLeadLagPanelSlot deploy 必同 wave；本 file 不含 producer 部分（W2 E1-δ scope）。E2 必驗 deployment runbook 含 atomic deploy step（schema 先 + writer 後）。
5. **N+2 promote demo 後 retention 升 30d**：如 D+12 paper edge report PASS +15 bps gate → N+2 demo IMPL 必新建 V### migration ALTER TABLE 升 retention 14d → 30d；本 V088 為 paper-only 階段預設。

## §8 Operator 下一步

1. **PM 21:30 UTC sign-off**：審本 V088 SQL skeleton + 對照 spec v1.2 §4.1 + sibling V085/V087 pattern
2. **Sign-off PASS 後 commit + push**：
   - V088 file 已 staged（CC commit/push permission 攔截，等 operator 統一觸發）
   - Commit message：`feat(V088): panel.btc_lead_lag_panel SQL skeleton NOT_RUN [skip ci]`（per task instruction）
   - Push to main：operator 決定（V085/V087/V088 panel.* sibling 三 commit 一起 push 較整齊）
3. **D+1 W2 V088 IMPL phase**（per spec §11 + §8.3 simplified path）：
   - W2 E1-δ (C-IMPL-2) Linux PG dry-run V088 (跑兩次驗 idempotent + create_hypertable + retention 實 land 驗證)
   - W2 E1-δ IMPL btc_lead_lag_writer.py (per spec §4.2) + Rust BtcLeadLagPanelSlot (slots.rs) + step_4_5_dispatch surface field assignment + paper-only engine_mode gate
   - W2 E1-ε (C-IMPL-3) IMPL ma_crossover/grid_trading declared_alpha_sources += CrossAsset + on_tick shadow log only (paper engine only, per spec §5.1)
   - E2 review (Guard A/B/C 完整性 + 3 array 同序對齊 application 層 invariant + Linux PG dry-run report + Layer 1 paper-only fence default → None grep verify per §12 #1)
   - E4 regression test
   - PM commit + deploy
4. **D+5 paper engine deploy 後跑 7d**
5. **D+12 paper edge report land**（含 §7.1 mandatory metric 6 條 + dual-layer σ acceptance + PSR(0) skew/kurt formula 計算 + +15 bps gate power verification σ_net=50/80 bps 兩 case 並列）

---

## §9 NOT_COMMITTED · NOT_DEPLOYED · NOT_RUN 標記

- **NOT_COMMITTED**: V088 file 已 staged（git add 完成）但 commit 被 CC permission system 攔截（commit/push to main bypass PR review 觸發保護）。Operator 需 22:30 UTC sign-off 後手動觸發 `git commit + push`。
- **NOT_DEPLOYED**: 未跑 `psql -f V088__*.sql`，無 DB schema 改動
- **NOT_RUN**: 無 `cargo test` / 無 `pytest` / 無任何 runtime exec
- **PM sign-off 條件**: 等 21:30 UTC sign-off 窗口；PM 對照本 report + V088 file 內容 + sibling V085/V087 panel.* pattern 一致性做最後 verdict

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w2_v088_btc_lead_lag_panel_sql_skeleton_prewrite.md）
