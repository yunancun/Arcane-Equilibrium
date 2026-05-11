# W2 IMPL v1.2 Chain — 5 Sub-Agent Dispatch Plan

**Author**: PA (project architect)
**Date**: 2026-05-11
**Status**: DRAFT — dispatch plan only, **無業務代碼改動**（E1 才寫 IMPL）
**Working dir HEAD**: `073b7fba`
**Spec source**: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`（v1）+ `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w2_a4c_spec_v1_1_qc_5_conditions_revision.md`（v1.1 補強）+ `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w2_a4c_spec_v1_2_dual_layer_sigma_revision.md`（v1.2 補強）

---

## §0 重大發現 — 現實狀態盤點先於 dispatch

operator 任務描述假設 W2 IMPL 還沒開工，但 **Sprint N+1 D+0 pre-dispatch readiness** 階段已把舊 spec §11 4 個 sub-task 大半 land 進 master。本 dispatch plan 重新拆 5 個 sub-agent **以剩餘真實 gap 為核心**，不是 spec §11 4 sub-task 重派一遍。

### §0.1 已 land 部分（不重做）

| 部件 | 路徑 | 狀態 |
|---|---|---|
| Trait skeleton `BtcLeadLagPanel` typedef + `AlphaSurface.btc_lead_lag` field + 3 constructor | `srv/rust/openclaw_core/src/alpha_surface.rs` (650 LOC) | ✅ HEAD `c9fb0b8f` land |
| V088 migration（CREATE SCHEMA panel + CREATE TABLE + Guard A/B/C + TimescaleDB hypertable + retention 14d + integer_now_func + hot-path index） | `srv/sql/migrations/V088__panel_btc_lead_lag_panel.sql` (456 LOC) | ✅ land；Linux PG empirical 待 D+1 deploy 驗 |
| `BtcLeadLagPanelSlot` typedef + ipc_server slot anchor | `srv/rust/openclaw_engine/src/ipc_server/slots.rs:216-239` | ✅ land |
| `BtcLeadLagProducer`（cohort buffer + on_tick + xcorr + regime_tag + run_loop + PG INSERT） | `srv/rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` (1253 LOC) | ✅ land（含 6 stage：BTC kline pull → alt kline pull → on_tick lookahead-free → V088 INSERT → slot write） |
| V088 INSERT writer + `arrays_aligned()` invariant + `exec_single_insert` | `srv/rust/openclaw_engine/src/database/btc_lead_lag_writer.rs` | ✅ land |
| `step_4_5_dispatch.rs` paper-only fence Layer 1（engine_mode match → `_ => None`） | `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:206-211` | ✅ land |
| main.rs BtcLeadLagProducer spawn run_loop + 7-sym alt cohort hardcoded + db_pool inject | `srv/rust/openclaw_engine/src/main.rs:977-996` | ✅ land |
| main_pipelines.rs 三 pipeline（paper/demo/live）BtcLeadLagPanelSlot Arc clone injection | `srv/rust/openclaw_engine/src/main_pipelines.rs:82-88, 393, 507, 644` | ✅ land |
| ma_crossover `declared_alpha_sources += CrossAsset` + on_tick `if let Some(panel) = surface.btc_lead_lag` → `evaluate_shadow_signal` 共用 helper | `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:43, 195` | ✅ land |
| grid_trading 同 pattern | `srv/rust/openclaw_engine/src/strategies/grid_trading/mod.rs:326, 424` | ✅ land |
| `strategies/cross_asset/mod.rs`（共用 5 conditions + step_gate plus15/plus5_15/minus5/no_signal + tracing emit target=`btc_alt_lead_lag_shadow`） | `srv/rust/openclaw_engine/src/strategies/cross_asset/mod.rs` (441 LOC) | ✅ land |
| bb_breakout / bb_reversion **不** declare CrossAsset（spec §5.2 negative path） | `bb_breakout/mod.rs:295-300` 仍 `[Ta1m, Ta5m, OiDeltaPanel]`；`bb_reversion/mod.rs:338` 仍 `[Ta1m]` | ✅ negative check OK |

### §0.2 真實剩餘 gap（W2 IMPL v1.2 chain 任務）

| Gap | 證據 | 重要性 |
|---|---|---|
| **G1 — Orderbook 接線**：`btc_book_imbalance: 0.0` placeholder | `panel_aggregator/btc_lead_lag.rs:113-114, 270-273` 明示「placeholder, 接線留 sub-task 4」 | spec §3.1.3 主信號之一，PG 寫 0.0 = lost evidence |
| **G2 — Layer 2 fence spec amendment**：Producer 改 Rust pull，原 Python writer Layer 2 設計 obsolete | `strategies/cross_asset/mod.rs:12-13` 仍引用「Python writer fence」；無 Python writer 檔（grep 確認）；real fence 變成 Producer 端 env-gate（`OPENCLAW_ENABLE_PAPER`） | spec 與 code 失步 → 後續 reviewer 困惑 |
| **G3 — Healthcheck [57]**：spec §7.1 mandatory metric set 6 條無對應 passive_wait check | `helper_scripts/db/passive_wait_healthcheck.py` grep 無 btc_lead_lag/panel.btc_lead_lag/check_57 | 違反 CLAUDE.md §七「被動等待 TODO 必附 healthcheck」強制規則 |
| **G4 — D+12 paper edge report 工具鏈**：spec §7.2 離線 counterfactual SQL + dual-layer σ + PSR(0) skew/kurt formula + +15/+5-15/<+5 三檔 gate verdict 工具 | grep 無對應 report script；MIT spec §7 強制 metric 6 條無 evaluator | acceptance gate 缺工具 → D+12 沒辦法 land paper edge report |
| **G5 — E2 對抗 PR + E4 cross-language regression test pack**：三層 fence 對抗 + sub-task sign-off pack | grep 無對應 test fixture；無 demo/live 環境 surface.btc_lead_lag must be None empirical assertion | spec §6 + spec §12 acceptance gate |

### §0.3 Spec §11 4 sub-task 對應現狀

| Spec §11 sub-task | Spec 預估 LOC | 現狀 | 結論 |
|---|---|---|---|
| C-IMPL-1 trait extension NO-OP | 0 LOC | ✅ land | done |
| C-IMPL-2 producer + V088 + IPC slot + dispatch wire | ~400 LOC (含 v1.1 補) | ✅ land 1253 LOC（producer 主體）+ V088 + slot + dispatch wire | 主體 done，剩 orderbook 接線 (G1) |
| C-IMPL-3 strategy paper-only shadow | ~80 LOC | ✅ land（ma_crossover + grid_trading + cross_asset/mod.rs 共用 helper） | done |
| C-IMPL-4 paper engine 7d evidence collection | 0 LOC（操作 only） | 待 D+5 paper engine deploy 後跑（**仍未 deploy**，因 orderbook stub + healthcheck 缺失） | blocked by G1+G3+G4 |

→ **W2 IMPL v1.2 chain 真實 scope = 收尾 5 個剩餘 gap (G1-G5)，不是 4 個 spec §11 sub-task 重派**。

---

## §1 5 個 Sub-Agent 拆分（W2 IMPL v1.2 chain）

| Sub-agent | Scope | Workload | 動的 file（不重疊） | 並行/序列 |
|---|---|---|---|---|
| **W2-IMPL-1** | Orderbook 接線 — `btc_book_imbalance` 從 0.0 placeholder 變實值（Bybit V5 `/v5/market/orderbook` top-10 或 WS `orderbook.50.{sym}` topic 取 bid/ask top-10） | 1.5 day | `srv/rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs`（修 `BtcLeadLagPanelSnapshot.btc_book_imbalance` placeholder line 113/271/273 → 真實計算；新加 helper `compute_btc_book_imbalance(bid_top10, ask_top10) → f64`）+ `srv/rust/openclaw_engine/src/main.rs:977-996`（spawn 時 inject `Arc<RwLock<Option<OrderbookSnapshot>>>` slot 或 BookSlot subscriber）+ 1 unit test fixture | 可並行於 IMPL-2/3/4/5（panel_aggregator/btc_lead_lag.rs 改動 line range 100-300，與 IMPL-3 改 line 12-13 註釋 + IMPL-4 改 §7.2 SQL 不重疊；與 W1 IMPL chain 不撞檔） |
| **W2-IMPL-2** | Layer 2 fence spec amendment + Producer env-gate 補強 — Python writer 已 obsolete，Layer 2 改寫 Producer 端 `OPENCLAW_ENABLE_PAPER` env check（demo/live engine fork 時 producer 不 spawn 或 spawn but skip INSERT） | 1 day | `srv/rust/openclaw_engine/src/main.rs:977-996`（spawn 前讀 env，未設 + 偵測 demo/live mode 為 active → spawn skip 或 producer.run_loop 內 demo/live 偵測時跳過 PG INSERT）+ `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`（spec v1.2 → v1.3 inline edit §6.2 Layer 2：「Python writer fence」改為「Producer env-gate fence」，附 amendment 註）+ `srv/rust/openclaw_engine/src/strategies/cross_asset/mod.rs:12-13`（MODULE_NOTE 同步更新） | 可並行；與 IMPL-1 同 file（main.rs 977-996）但改不同 hunk（spawn 邏輯 wrap）；衝突弱 line 隔 |
| **W2-IMPL-3** | Healthcheck [57] btc_lead_lag panel freshness + alpha decay R²(N) — passive_wait check_57 新增 | 1 day | `srv/helper_scripts/db/passive_wait_healthcheck.py`（添加 `check_57()` fn：query `panel.btc_lead_lag_panel` last row age < 120s + regime_tag distribution + alt cohort 7 sym 全覆蓋 + alpha_decay_60s_300s_R2_ratio）+ 對應 SCRIPT_INDEX 更新 | 完全並行；與其他 IMPL 不撞檔 |
| **W2-IMPL-4** | D+12 paper edge report 工具鏈 — 離線 counterfactual SQL evaluator + dual-layer σ + PSR(0) skew/kurt formula + +15/+5-15/<+5 step gate verdict | 2 day | `srv/helper_scripts/reports/w2_paper_edge_report.py`（新檔；跑 spec §7.2 SQL + 算 spec §7.1 mandatory 6 metric：per-symbol gate n≥100+t>2.0, DSR K=95 deflate, PSR(0) skew/kurt, alpha decay regime test, block-bootstrap 95% CI, per-cohort counterfactual delta）+ `srv/sql/queries/w2_btc_alt_lead_lag_counterfactual.sql`（新檔；對齊 spec §7.2）+ MODULE_NOTE 雙語 | 完全並行；新檔不撞既有檔 |
| **W2-IMPL-5** | E2 三層 fence 對抗 + E4 cross-language regression test pack + sub-task sign-off pack | 1.5 day | `srv/rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs`（增加 fence regression unit test：demo/live engine_mode 偵測時 producer.run_loop 是否寫 PG）+ `srv/rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs`（新檔；integration test 三層 fence 對抗：Layer 1 step_4_5_dispatch.rs demo mode → surface.btc_lead_lag must be None；Layer 2 Producer env-gate；Layer 3 cross_asset/evaluate_shadow_signal 收 None panel → no_signal step_gate）+ `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-1X--w2_impl_v12_signoff_pack.md`（最終 sign-off 報告） | 須等 IMPL-1 + IMPL-2 land 後 rebase（因為 test 對 IMPL-1 orderbook 接線 + IMPL-2 env-gate fence 寫 assertion）；與 IMPL-3 / IMPL-4 並行 |

---

## §2 依賴關係

```
W2-IMPL-1 (orderbook 接線, panel_aggregator/btc_lead_lag.rs hunks 100-300)
W2-IMPL-2 (Layer 2 fence amendment, main.rs spawn wrap + spec edit + cross_asset MODULE_NOTE)
W2-IMPL-3 (healthcheck [57], passive_wait_healthcheck.py)
W2-IMPL-4 (D+12 paper edge report 工具鏈, 新 report.py + 新 .sql)

四個全完全並行（0 file 重疊；唯一弱衝突 = IMPL-1 + IMPL-2 同 main.rs:977-996 hunk，但
改動方向正交：IMPL-1 加 orderbook slot inject、IMPL-2 加 env-gate wrap，merge 階段
PM 在 commit 順序拍板誰先 land，後者 rebase 必和諧）

W2-IMPL-5 (E2 fence 對抗 + E4 regression test) ← rebase 等 IMPL-1 + IMPL-2 land
                                              ← 與 IMPL-3 + IMPL-4 並行
```

**派發節奏**：
- D+0：PM 派 IMPL-1 / IMPL-2 / IMPL-3 / IMPL-4 同時開工（4 並行 sub-agent）
- D+2：IMPL-1 + IMPL-2 push，E2 review 各 fence 對抗 + orderbook 計算正確性
- D+3：PM 派 IMPL-5（rebase IMPL-1 + IMPL-2 head）→ E2 + E4 GREEN gate
- D+5：全 5 sub-task PM sign-off → restart_all --rebuild deploy paper engine
- D+5 → D+12：paper engine 跑 7d，IMPL-4 工具收集 evidence
- D+12：IMPL-4 paper edge report run → PM + QC + MIT 三角 sign-off → N+2 promote decision

---

## §3 每個 Sub-task PA Spec Checklist（acceptance criteria + E2 + E4 重點）

### §3.1 W2-IMPL-1（Orderbook 接線）

**Acceptance criteria**：
1. `btc_book_imbalance` 非 0.0 placeholder，per spec §3.1.3：`(bid_size_top10 - ask_size_top10) / (bid_size_top10 + ask_size_top10)`
2. 數據源用 既有 Bybit V5 `/v5/market/orderbook` REST endpoint（`market_data_client::mod.rs:155`）或既有 WS `orderbook.50.{sym}` topic（`multi_interval_topics.rs:111`）— 選 WS-first 對齊 W1 BB push back（rate budget 0 req/s ongoing）
3. orderbook snapshot 與 1m grain bucketing 對齊（producer on_tick 拿到的是當前 1m bucket 最後一次 snapshot）
4. snapshot 缺失 → `btc_book_imbalance = NaN`（不是 0.0），writer 寫 NULL；下游 evaluator skip
5. PG `panel.btc_lead_lag_panel.btc_book_imbalance` 真實值寫入 7d 樣本 ≥ 90%（非 NULL 非 0.0）

**E2 review 重點**：
1. WS-first vs REST polling 選擇：必須選 WS（per BB review；REST polling 是 over-engineering）
2. lookahead bias 防護：orderbook snapshot 對齊 1m bucket close 必用 `shift(1)` 或 strict close-aligned，禁含 future tick
3. NaN propagation：snapshot.btc_book_imbalance = NaN → writer 寫 NULL（不是 0.0），downstream evaluator FILTER OUT
4. Rate budget：WS subscribe `orderbook.50.BTCUSDT` 已在 既有 connection（grep `orderbook_topic` confirm），不增新 ws connection

**E4 regression 重點**：
1. unit test：`compute_btc_book_imbalance(bid_top10, ask_top10)` 對 4 fixture（正 imbalance / 負 imbalance / 平衡 / NaN edge case）GREEN
2. integration test：mock WS orderbook snapshot stream 跑 5 tick，confirm panel.btc_lead_lag_panel write 5 row btc_book_imbalance 非 0.0/NaN
3. 既有 `panel_aggregator::btc_lead_lag::*` 11 unit test 全 GREEN（不破 IMPL-2/3/4 land）

### §3.2 W2-IMPL-2（Layer 2 fence amendment）

**Acceptance criteria**：
1. spec v1.2 → v1.3 inline edit：§6.2 Layer 2「Python writer fence」改為「Producer env-gate fence」，註明 amendment 原因（producer 從 Python writer 改 Rust pull）
2. main.rs:977-996 BtcLeadLagProducer spawn 前 wrap：env check + engine mode 偵測（has_demo / has_live 兩個 bool 已存在 line 1030-1031）→ 未設 OPENCLAW_ENABLE_PAPER 且 demo/live active 時 spawn 跳過或 run_loop 內 skip PG INSERT
3. cross_asset/mod.rs:12-13 MODULE_NOTE 同步更新（Python writer 字樣全清，改 Producer env-gate）
4. tracing target 字串 `btc_alt_lead_lag_shadow` 永不變（spec §5.1.2 contract）

**E2 review 重點**：
1. fence wrap 不破 trait 端 None default contract：surface.btc_lead_lag 在 paper 仍 = Some(...)；demo/live 仍 = None（IMPL-2 改 producer 不改 fence Layer 1）
2. env-gate 邏輯三狀態：(a) OPENCLAW_ENABLE_PAPER=1 → spawn 正常；(b) OPENCLAW_ENABLE_PAPER 未設 + has_demo / has_live = true → spawn skip 或 run_loop 內 NoOp；(c) OPENCLAW_ENABLE_PAPER 未設 + paper-only → spawn 正常
3. spec edit 不破 spec §7.1 mandatory metric 6 條 + §8.1 三檔 gate（純 §6.2 Layer 2 描述更新，不動 acceptance gate）

**E4 regression 重點**：
1. demo engine 24h 跑（mock test fixture）— `panel.btc_lead_lag_panel` 0 row（producer fence triggered）
2. live_demo engine 24h 跑（mock fixture）— 同 0 row
3. paper engine 24h 跑 — `panel.btc_lead_lag_panel` row 累積 ≥ 1000 / 24h（1m grain × 1440 - 缺失容忍 ~440）

### §3.3 W2-IMPL-3（Healthcheck [57]）

**Acceptance criteria**：
1. `passive_wait_healthcheck.py` 加 `check_57()` fn（check_56 之後）
2. PG query：`SELECT NOW() - to_timestamp(MAX(snapshot_ts_ms)/1000) AS age, COUNT(DISTINCT unnest(alt_symbols)) AS cohort_size, COUNT(*) FILTER (WHERE regime_tag = 'extreme') AS extreme_n, AVG(btc_book_imbalance) AS book_imb_avg FROM panel.btc_lead_lag_panel WHERE snapshot_ts_ms > (EXTRACT(EPOCH FROM NOW() - INTERVAL '1 hour') * 1000)::bigint`
3. PASS 條件：(a) age < 120s；(b) cohort_size = 7（per spec §2.2）；(c) extreme_n / total < 5%；(d) book_imb_avg != 0.0（IMPL-1 完成後）+ != NULL
4. WARN 條件：age 120-300s OR extreme_n / total ∈ [5%, 20%]
5. FAIL 條件：age ≥ 300s OR cohort_size < 7 OR extreme_n / total ≥ 20%
6. Exit 1 if FAIL（silent-dead detection per CLAUDE.md §七）

**E2 review 重點**：
1. PG query 對 timescaledb hypertable 走 hot-path index `idx_btc_lead_lag_panel_ts_window`（EXPLAIN ANALYZE 驗）
2. alpha_decay R²(60/120/300) 計算公式對齊 spec §7.1 metric (4)
3. Healthcheck PASS/WARN/FAIL 三段邊界對齊 spec §7.1 + spec §9 regime guard
4. Linux PG empirical dry-run（per memory `feedback_v_migration_pg_dry_run` 必須）

**E4 regression 重點**：
1. healthcheck Mac 端 mock PG dry-run — PASS / WARN / FAIL 三狀態各對應 fixture row
2. SCRIPT_INDEX.md 更新對應入口
3. cron 註冊（per CLAUDE.md §七 被動等待 + healthcheck pattern）— `OPENCLAW_W2_HEALTHCHECK_ENABLE=1` env opt-in

### §3.4 W2-IMPL-4（D+12 paper edge report 工具鏈）

**Acceptance criteria**：
1. `srv/helper_scripts/reports/w2_paper_edge_report.py` 新檔（~400-500 LOC + MODULE_NOTE 雙語）
2. 跑 spec §7.2 離線 counterfactual SQL 取得 per-symbol entry/exit fill + btc_alt_lead_lag_shadow log alignment
3. 算 spec §7.1 mandatory metric 6 條 + dual-layer σ acceptance (raw market 4.5-10 bps vs net edge 50-80 bps) + PSR(0) skew/kurt formula (Bailey-López de Prado 2012) + +15/+5-15/<+5 三檔 step gate verdict
4. 輸出 `docs/CCAgentWorkSpace/PA/workspace/reports/YYYY-MM-DD--w2_paper_edge_report.md`（D+12 land）+ `latest` symlink
5. `srv/sql/queries/w2_btc_alt_lead_lag_counterfactual.sql` 新檔對齊 spec §7.2 SQL

**E2 review 重點**：
1. SQL 正確：spec §7.2 「if expected_dir=+1 → assume LONG entry; net_edge_bps proxy from forward 30s-300s alt return」必對齊 producer 端 panel.alt_expected_dir 0/+1/-1 三值
2. dual-layer σ：raw market σ 用於 R²(N) baseline；net edge σ 用於 power calculation + PSR(0)；禁混用（per spec v1.2 §7.1 強制條件）
3. PSR(0) skew/kurt formula 強制：`Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))`，threshold ≥ 0.95（禁 normal SR z-test）
4. 三檔 gate：+15 promote N+2 / +5~+15 extend 14d / <+5 revise spec
5. block-bootstrap 95% CI（block_size = 60min, 1000 iter, per QC 5 conditions #4(e)）

**E4 regression 重點**：
1. mock fixture 跑 3 case：(a) gross +20 bps → step_gate=plus15 promote verdict；(b) gross +8 bps → plus5_15 extend verdict；(c) gross -3 bps → minus5 revise verdict
2. 對 cf alignment SQL 跑 PG empirical（Linux）— shadow log target `btc_alt_lead_lag_shadow` row count > 0
3. dual-layer σ 兩 case 並列：σ_net=50 bps → t-stat 2.68 PASS comfortable；σ_net=80 bps → t-stat 1.68 marginal PASS

### §3.5 W2-IMPL-5（E2 fence 對抗 + E4 regression test pack + sign-off）

**Acceptance criteria**：
1. unit test：`panel_aggregator::btc_lead_lag::*` 既有 11 test + 新加 3 test（orderbook from IMPL-1 / env-gate fence from IMPL-2 / regime extreme guard）GREEN
2. integration test 新檔 `tests/btc_lead_lag_panel_fence_integration.rs`：三層 fence 對抗
   - Layer 1 assertion：`step_4_5_dispatch.rs` 模擬 demo / live_demo / live 三 mode → surface.btc_lead_lag must be None
   - Layer 2 assertion：spawn producer with `OPENCLAW_ENABLE_PAPER` unset + has_demo=true → producer skip PG INSERT
   - Layer 3 assertion：`evaluate_shadow_signal` 收 5 condition 全 fail（panel=None edge case + symbol not in cohort + xcorr=NaN + btc_lead_return=NaN + regime=extreme）→ step_gate=`no_signal`
3. cross-language consistency：Python check_57 + Rust producer + SQL evaluator 三方 cohort 7-sym 對齊（per memory `feedback_v_migration_pg_dry_run` Linux PG dry-run 必跑）
4. sign-off pack `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-1X--w2_impl_v12_signoff_pack.md`：5 sub-task 完成清單 + 16 原則 + DOC-08 §12 + 硬邊界 5 項 0 觸碰 verify

**E2 review 重點**：
1. 三層 fence assertion 完整：Layer 1 (engine_mode gate) + Layer 2 (env-gate spawn) + Layer 3 (cross_asset/mod.rs if let Some) 各對應一個 assert，缺一拒簽
2. cross_asset/evaluate_shadow_signal 對 NaN 處理 safe（既有 line 80-90 PartialEq + Default 對 NaN 行為）
3. test 不破 既有 strategies/ma_crossover + grid_trading test
4. file 大小：tests/btc_lead_lag_panel_fence_integration.rs ≤ 800 LOC（CLAUDE.md §九 warning line）

**E4 regression 重點**：
1. `cargo test --lib --release -p openclaw_engine` 全 GREEN（既有 panel_aggregator tests + 新 fence integration test）
2. `cargo test --release -p openclaw_engine --test btc_lead_lag_panel_fence_integration` GREEN
3. cargo test baseline 不退化（既有 `cargo nextest` count 不變或增加，0 test 退化）
4. paper engine 6h smoke：deploy 後 `panel.btc_lead_lag_panel` row 累積 ≥ 250 / 6h + `btc_alt_lead_lag_shadow` tracing log target 出現 ≥ 50 row

---

## §4 Cross-Wave 衝突檢查

### §4.1 vs W1 IMPL chain（5/11 active iterating）

| 比對軸 | W1 IMPL | W2 IMPL | 結論 |
|---|---|---|---|
| Producer | `panel_aggregator/funding_curve.rs` (408 LOC) + `oi_delta.rs` (570 LOC) | `panel_aggregator/btc_lead_lag.rs` (1253 LOC) | **不重疊**（三個 sibling 檔，PA D+0 已預留 anchor） |
| PG table | `panel.funding_rates_panel` (V085) + `panel.oi_delta_panel` (V087) | `panel.btc_lead_lag_panel` (V088) | **不重疊**（三 table sibling） |
| WS topic | `tickers.{sym}` broadcast subscriber（W1 spec v1.1 BB push back 採納） | `orderbook.50.BTCUSDT`（W2-IMPL-1 待 IMPL，已有 既存 `multi_interval_topics::orderbook_topic`） | **不重疊**（不同 topic） |
| Slot | `FundingCurvePanelSlot` + `OIDeltaPanelSlot` | `BtcLeadLagPanelSlot` | **不重疊**（slots.rs anchor 三 insertion point 各佔一段） |
| step_4_5_dispatch wire | `surface.funding_curve = ...` + `surface.oi_delta_panel = ...` | `surface.btc_lead_lag = ...` (paper-only fence) | **不重疊**（三 field 各佔一行；anchor comment 隔離） |
| Fence | demo/live 接 W1 panel（不 fence） | demo/live fence 為 None | **不重疊**（spec 明確分流） |
| W1 funding panel staleness fix / cohort coverage / POLUSDT migration | W1 IMPL chain 隔壁 session in-flight | W2 IMPL 不動 W1 file | **不撞**（PM dispatch ledger sync 即可） |

### §4.2 vs Phase 3 V091 deploy（D+1 evening + D+2 ALTER VALIDATE）

| 比對軸 | V091 | W2 IMPL | 結論 |
|---|---|---|---|
| V091 scope | `learning.decision_features.reject_reason_code` + `close_reason_code` schema-level 互斥 CHECK NOT VALID | `panel.btc_lead_lag_panel` schema 已 V088 land；W2 IMPL 不動 `learning.decision_features` | **不重疊**（V091 改 learning schema，W2 改 panel schema 不同 namespace） |
| 互斥 CHECK constraint | learning.decision_features row-level | panel.btc_lead_lag_panel 不寫 reject/close reason | **不衝突** |
| ALTER VALIDATE 鎖表時序 | D+2 evening 短 lock learning.decision_features | W2 paper engine 跑 7d，不寫 learning.decision_features | **不撞**（W2 producer/strategy 不動該 schema） |

### §4.3 vs P1-RCA-1 + P1-1 並行 sub-agent

| 比對軸 | P1-RCA-1 / P1-1 | W2 IMPL | 結論 |
|---|---|---|---|
| P1-1 ma_crossover duplicate intent fix | 改 `strategies/ma_crossover/strategy_impl.rs` on_rejection rollback / TickContext position handle | W2-IMPL-5 對 strategy_impl.rs 加 fence integration test，**不**改 strategy logic | **弱衝突**（P1-1 land 後 W2-IMPL-5 rebase；merge 階段 PM 排序）；strategy declare CrossAsset 已 land 不改 |
| P1-RCA-1 cross-strategy position state gap 全策略 audit | 寫 audit report；可能改 5 策略 TickContext signature | W2-IMPL-5 test 對 5 策略 signature 寫 fixture | **可能衝突**（若 P1-RCA-1 改 TickContext signature → W2-IMPL-5 test 需 rebase）；PM 排序：P1-RCA-1 先 / W2-IMPL-5 後 |
| 主路徑 | E1 領域，PA 不直接派 | E1 領域，本 plan 派 | **領域不重疊** |

### §4.4 與其他 5/11 active wave 衝突檢查

| Wave | 改動範圍 | 與 W2 衝突 |
|---|---|---|
| W6 RFC verdict + V086 IMPL | learning.decision_features + reject/close reason enum | 不撞（W2 panel namespace 獨立） |
| W7-2/W7-4/W7-5 | strategy_impl.rs cross-strategy desync + spine state propagation | 弱衝突（W2-IMPL-5 test rebase；不阻塞） |
| W3 Stage 1 cohort observation | governance canary_stage_log | 不撞（W2 不動 governance schema） |
| W4 RouterLeaseGuard Drop test | routing/lease_guard.rs | 不撞 |
| W5 三 P1 IMPL（V089 governance canary stage metric seed + V090 governance unblock candidates） | governance namespace | 不撞（W2 panel namespace） |

**全 wave cross-check verdict**：W2 IMPL v1.2 chain 5 sub-agent 與其他 wave 0 file 重疊；唯一弱依賴 = W2-IMPL-5 等 P1-1 / P1-RCA-1 land 後 rebase；PM dispatch 排序即可。

---

## §5 Acceptance Window + 必過 Quality Gate

### §5.1 Acceptance Window 估計

**Optimistic（5 day）**：
- D+0：派 IMPL-1 / 2 / 3 / 4（4 並行）；E2 同步 review schedule 預定
- D+2：IMPL-1 + IMPL-2 push；E2 review 各 1.5h
- D+3：派 IMPL-5（rebase IMPL-1 + IMPL-2 head）；IMPL-3 / 4 同步收尾
- D+4：IMPL-5 push；E2 + E4 review；PM 開始整 sign-off pack
- D+5：deploy paper engine + 7d evidence collection 開始

**Pessimistic（7 day）**：
- IMPL-1 orderbook WS subscriber integration 若撞 既有 connection capacity → +1 day
- IMPL-2 spec amendment 若 BB / MIT review 要求補強 → +1 day

**Paper edge report land**：D+12（IMPL-4 工具 + 7d evidence collection 終點）

### §5.2 必過 Quality Gate

| Gate | 標準 | 違反處置 |
|---|---|---|
| **CC compliance（16 原則 + DOC-08 §12 + 硬邊界 5 項）** | 16/16 + 9/9 + 5/5 全綠（per skill `16-root-principles-checklist`）；W2 paper-only fence 三層深度防禦不可降級 | A 級或 B 級 + 0 BLOCKER；任一 BLOCKER 強制 PM 收回 |
| **E3 security（不寫 secrets / 不破 fail-closed）** | 5 hard gate 全 PASS（per memory Sprint N+1 D+0 readiness E3 ALL PASS）；orderbook WS subscribe 不洩 API key；env-gate 不破 paper-only fence | ≥1 hard gate FAIL → 拒簽 + 重做 |
| **E4 regression** | cargo test baseline 不退化（既有 panel_aggregator + strategies + ipc_server 全 GREEN）；新加 integration test PASS；既有 `cargo nextest` count 不減 | 任一 regression → IMPL-5 rebase + 重跑 |
| **cargo test baseline** | `cargo test --release -p openclaw_engine` + `cargo test --release -p openclaw_core` 全 GREEN | 失敗 = E1 重做 |
| **PG Linux empirical（per `feedback_v_migration_pg_dry_run`）** | check_57 + V088 hypertable + counterfactual SQL 三點 Linux PG dry-run（Mac mock 不夠） | Mac false-pass 是反模式 |
| **Paper edge report（D+12）** | spec §7.1 mandatory metric 6 條全 land + dual-layer σ + PSR(0) skew/kurt + +15/+5-15/<+5 step gate verdict | 缺一拒收，QC + MIT 三角 review |

---

## §6 PA E2 重點審查 3 點（per profile.md 標準輸出）

1. **三層 fence 主防線完整性**：E2 必 grep 三處
   - Layer 1：`step_4_5_dispatch.rs` `match em` default arm 必為 `_ => None`（不是 `_ => Some(...)`）；現狀已 land 但 IMPL-1 / IMPL-2 改動 main.rs 時不可動到此 fence
   - Layer 2：IMPL-2 spawn wrap 必 env check（`OPENCLAW_ENABLE_PAPER` 三狀態完整：set=1 / unset+paper-only / unset+demo|live-active）；漏狀態 → fence 失靈
   - Layer 3：cross_asset/mod.rs `if let Some(panel)` + `evaluate_shadow_signal` 對 None 不可被誤刪（IMPL-5 test 覆蓋率 100% — 三 fence 各對應 1 assert）

2. **Strict shift(N) lookahead-free 嚴格驗**：spec §3.1 + §3.2 + §7.3 強制
   - W2-IMPL-1 orderbook 接線必 `shift(1)` close-aligned（不是 current tick orderbook，因 1m bucket close 是 forward boundary）；rolling-window breach 反模式（per memory `feedback_indicator_lookahead_bias`）禁犯
   - W2-IMPL-4 paper edge report SQL 必對齊 producer 端 `btc_lead_return_pct` strict shift(N) past close 計算；MIT C-3 D+12 review 必跑 leak detection

3. **CC compliance + 硬邊界 5 項 + DOC-08 §12 9 條 0 觸碰**（per skill `16-root-principles-checklist`）：
   - W2 IMPL v1.2 chain 不動 `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease` / `authorization.json`
   - 不動 lease / authorization / audit / reconciler / mainnet env / Bybit retCode 任何路徑
   - 不動 SM-04 Guardian / IntentProcessor / paper_state singleton
   - paper-only fence Layer 1 + Layer 2 + Layer 3 三層守護原則 4（不繞風控）+ 原則 7（學習 ≠ 改寫 Live）

---

## §7 一句總結

**W2 IMPL v1.2 chain 真實 scope 是收尾 5 個剩餘 gap（G1 orderbook 接線 / G2 Layer 2 fence spec amendment / G3 healthcheck [57] / G4 D+12 paper edge report 工具鏈 / G5 E2/E4 對抗 test + sign-off pack）— 不是 spec §11 4 sub-task 重派；Sprint N+1 D+0 pre-dispatch readiness 已把 trait skeleton + V088 + Producer + run_loop + 三 pipeline slot inject + ma_crossover/grid_trading declare CrossAsset + on_tick shadow log + cross_asset/mod.rs 共用 helper 都 land 完；W2-IMPL-1/2/3/4 完全並行 0 file 重疊（唯一弱衝突 main.rs:977-996 兩 hunk 改動方向正交）；W2-IMPL-5 rebase 等 IMPL-1+2；估 5-7 day acceptance window；vs W1 IMPL chain / Phase 3 V091 / P1-RCA-1 / P1-1 全 0 file 重疊；16 原則 + DOC-08 §12 + 硬邊界 5 項 0 觸碰。**

---

**Report end. PA dispatch plan ready. PM 派 5 sub-agent 並行（IMPL-1+2+3+4 D+0 同時起 / IMPL-5 D+3 rebase）後執行 W2 IMPL v1.2 chain。**

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md
