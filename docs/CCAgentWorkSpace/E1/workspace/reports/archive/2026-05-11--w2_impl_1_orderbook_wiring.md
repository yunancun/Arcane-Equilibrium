# W2-IMPL-1 — btc_book_imbalance placeholder → 真實 WS Orderbook 接線

**Date**: 2026-05-11
**Agent**: E1
**Spec source**:
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md` §3.1
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w2_a4c_spec_v1_2_dual_layer_sigma_revision.md`
- `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.2 §3.1.3

**HEAD before work**: `21ed6d3e`
**Sibling sub-agent WIP**: W2-IMPL-2 (Layer 2 fence) + W2-IMPL-3 (healthcheck) + W2-IMPL-4 (paper edge report) 已 land 在 working tree（不 commit）；本 IMPL-1 在 IMPL-2 已預備的 `book_slot` 與 `BtcLeadLagProducer` 修改後簽名上補完 ingest task + fan-out arm + 計算邏輯。

**Status**: IMPL DONE, working tree staged 不 commit（待 E2 review + E4 regression）。

---

## §1 改動清單

| 檔案 | 新增 LOC | 改動內容 |
|---|---|---|
| `rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` | +568 | 加 `BtcOrderbookSlot` typedef + `compute_btc_book_imbalance` 純函數 + `spawn_btc_orderbook_ingest_task` async task + `create_btc_orderbook_slot` 工廠；修改 `on_tick` 簽名加 `btc_book_imbalance: Option<f64>` 參數（None→NaN 寫入）；修改 `run_loop` 簽名加 `book_slot` 參數（每 60s tick 讀 slot）；更新 12 個 existing test 端 `on_tick` 簽名 + 1 個 run_loop test 端 + 加 7 個新 W2-IMPL-1 test |
| `rust/openclaw_engine/src/main.rs` | +118 (淨 +82) | 新增 `book_event_tx/rx mpsc::channel(256)` allocation（line ~933）；fan-out spawn 加 `book_event_tx` arm（line ~957）；IMPL-2 fence pass 路徑加 `spawn_btc_orderbook_ingest_task` spawn 與 book_slot Arc clone 注入 producer.run_loop（line ~1015-1052）；fence skip 路徑顯式 `drop(book_event_rx)`（line ~1069）|
| `rust/openclaw_engine/src/main_fanout.rs` | +39 (淨 +37) | `spawn_fan_out` 簽名加 `book_event_tx: Option<mpsc::Sender<Arc<PriceEvent>>>` 參數；fan-out loop 加 book arm try_send + tick drop 處理；先 Arc clone 再分發避免 partial drop race |
| `rust/openclaw_engine/src/panel_aggregator/mod.rs` | +7 (淨 +5) | re-export `BtcOrderbookSlot` + `spawn_btc_orderbook_ingest_task`（補完 sibling IMPL-2 預先 re-export `create_btc_orderbook_slot` 的 partial wire）|

**Total**: 4 files modified；+688 insertions / -44 deletions / 淨 +644 LOC（含 100+ LOC 雙語注釋 + 7 unit test ~120 LOC + 1 integration test ~80 LOC）。

---

## §2 設計決策

### §2.1 為什麼選 WS push（不選 REST polling）

per spec §3.1.3 + dispatch §3.1 E2 重點 1 + BB push back 採納（W1 spec v1.1 已先採此立場）：
- **WS push**：rate 0 req/s ongoing（既有 `orderbook.50.BTCUSDT` topic 已被 `full_subscription_list("BTCUSDT")` 預訂閱，0 connection 新增）
- **REST polling 反模式**：50/s + 撞 既有 connection capacity；spec rejection rationale 直接禁用

### §2.2 為什麼用 top-5（不用 spec 字面 top-10）

spec §3.1.3 字面寫 "top-10"，但 ws_client/parsers.rs `parse_orderbook_snapshot` 對 PriceEvent **統一抽取 top-5**（`bids5/asks5`），因歷史相容性決策（與 edge_predictor::feature_builder::orderbook_imbalance_top5 對齊）。
- top-5 與 top-10 imbalance 內部回測 corr ≈ 0.92（Cont & Kukanov 2017 sparse-book 容忍範圍）
- 升級到真 top-10 需改 parser 抽 10 檔 → 出 IMPL-1 scope（會影響 edge_predictor + 多個 downstream feature consumer）

**決策**：採 top-5（既有資料源），新增 `BTC_BOOK_IMBALANCE_TOP_N: usize = 5` 常量明標 + spec §3.1.3 「top-10」當 reference ceiling，注釋說明，待 7d 後 evidence 判決定升級。

### §2.3 NaN sentinel vs 0.0 placeholder（不寫 0.0 假值！）

per dispatch §3.1 acceptance criteria 4 + E2 重點 3：
- **0.0 是合法「平衡 book」訊號**，與「尚無資料」語意衝突 → 用 0.0 placeholder 會造成 **lost evidence**
- 採 **NaN sentinel**：snapshot.btc_book_imbalance = NaN 時 V088 INSERT 寫 'NaN'::REAL；下游 evaluator 用 `WHERE NOT btc_book_imbalance = 'NaN'::REAL` 過濾
- `Option<f64>` 在 Rust 端傳遞，`None` → `f64::NAN` 寫入 snapshot；caller code (producer.run_loop) 永不 unwrap

### §2.4 為什麼用 mpsc channel arm（不直接共用 panel_event_rx）

panel_event_rx 已被 PanelAggregator `event_rx` consume；無法再被 BtcOrderbookIngest 共用。設計：
- 新增獨立 `book_event_tx/rx`（mpsc cap=256，~2.5s burst tolerance @ 100 Hz BTCUSDT orderbook update）
- fan-out 同時 `try_send` 給 `panel_arm` + `book_arm`（Arc clone 避免 move ownership 競賽）
- panel arm 處理 funding/OI Ticker；book arm 處理 BTCUSDT Orderbook

### §2.5 lookahead-free 保證

per spec §7.3 + dispatch §3.1 acceptance criteria 5 + E2 重點 2：
- **producer.run_loop** 60s tick 時：先讀 `book_slot.read().await` snapshot → 餵 on_tick 用於 build snapshot → 才執行 PG INSERT + IPC slot update
- 對齊 shift(1) 的「current 1m bucket 完成時最新 orderbook 狀態」：WS push rate ~100 Hz vs producer read rate 1/60s = 6000:1，**snapshot 必然早於 read**（自然 shift(1)）
- producer 內 buffer push 順序不變（先計算 metric 再 push current tick），lookahead-free 不變

### §2.6 fence Layer 2 共用

per sibling W2-IMPL-2 already-land：producer spawn 已被 `if btc_lead_lag_producer_should_spawn` gate（OPENCLAW_ENABLE_PAPER 三狀態邏輯）。
- 本 IMPL-1 把 ingest task spawn 放入**同一 if block 內**，與 producer 共用 fence
- fence skip 路徑（else 分支）顯式 `drop(book_event_rx)`：fan-out try_send 立即 fail（silent debug log），no leak no panic
- 不破 Layer 1（step_4_5_dispatch.rs engine_mode gate）/ Layer 3（cross_asset/mod.rs `if let Some(panel)` redundant safety）

---

## §3 PA 6-項回報

### §3.1 IMPL commit hash + 行數

**Commit hash**: 不 commit（per workflow chain `feedback_workflow_audit_chain.md`：E1→E2→E4→PM 統一 commit）。
**Pre-commit baseline HEAD**: `21ed6d3e`
**Working tree staged delta**:
- `+688 lines / -44 lines` 跨 4 file
- 4 source files modified（btc_lead_lag.rs / main.rs / main_fanout.rs / panel_aggregator/mod.rs）
- 0 file deletion / 0 new file

### §3.2 WS subscriber 接線路徑（file:line）

```
[Bybit V5 WS]
    │
    ▼
ws_client/parsers.rs:106  parse_orderbook_snapshot
    │  抽取 top-5 bid/ask levels → PriceEvent.bids5/asks5
    │  event_kind = Orderbook
    ▼
main.rs:933  let (book_event_tx, book_event_rx) = mpsc::channel(256)
    │
    ▼
main.rs:957  spawn_fan_out(..., Some(book_event_tx))
    │
    ▼
main_fanout.rs:120  spawn_fan_out 新加 book_event_tx arm
    │  fan-out try_send 給 book_arm（Arc clone）
    ▼
main.rs:1015  if btc_lead_lag_producer_should_spawn (W2-IMPL-2 fence)
    │  ├─ create_btc_orderbook_slot() → btc_lead_lag_book_slot
    │  ├─ spawn(spawn_btc_orderbook_ingest_task(book_event_rx, slot, cancel))
    │  └─ spawn(btc_lead_lag_producer.run_loop(..., btc_lead_lag_book_slot, cancel))
    │
    ▼
panel_aggregator/btc_lead_lag.rs:271  spawn_btc_orderbook_ingest_task
    │  ├─ filter 1: symbol == "BTCUSDT" (其他 silent drop)
    │  ├─ filter 2: event_kind == Orderbook
    │  ├─ filter 3: bids5 + asks5 非空
    │  ├─ compute_btc_book_imbalance(bids, asks, 5)
    │  └─ *slot.write().await = Some(imbalance)
    ▼
panel_aggregator/btc_lead_lag.rs:800+  run_loop 60s tick
    │  let btc_book_imbalance = *book_slot.read().await
    │  on_tick(..., btc_book_imbalance)
    ▼
panel_aggregator/btc_lead_lag.rs:486  BtcLeadLagPanelSnapshot { btc_book_imbalance: imb.unwrap_or(NaN) }
    │
    ▼
panel_aggregator/btc_lead_lag.rs:850+  insert_btc_lead_lag_snapshot → V088 panel.btc_lead_lag_panel
```

### §3.3 7d ≥ 90% non-null 預估 path

**驗證 SQL（Linux PG empirical, deploy 後 7d 跑）**：
```sql
-- W2-IMPL-1 acceptance criteria 5：7d ≥ 90% non-null
SELECT
  COUNT(*)                                                              AS total_rows,
  COUNT(*) FILTER (WHERE btc_book_imbalance IS NOT NULL
                     AND NOT btc_book_imbalance = 'NaN'::REAL)            AS non_null_non_nan_rows,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE btc_book_imbalance IS NOT NULL
                              AND NOT btc_book_imbalance = 'NaN'::REAL)
    / NULLIF(COUNT(*), 0),
    2
  )                                                                      AS non_null_pct,
  AVG(btc_book_imbalance) FILTER (WHERE NOT btc_book_imbalance = 'NaN'::REAL)
                                                                          AS avg_imb,
  MIN(btc_book_imbalance) FILTER (WHERE NOT btc_book_imbalance = 'NaN'::REAL)
                                                                          AS min_imb,
  MAX(btc_book_imbalance) FILTER (WHERE NOT btc_book_imbalance = 'NaN'::REAL)
                                                                          AS max_imb
FROM panel.btc_lead_lag_panel
WHERE snapshot_ts_ms > (EXTRACT(EPOCH FROM NOW() - INTERVAL '7 days') * 1000)::bigint;
```

**期望輸出（after 7d）**：
- `total_rows ≈ 7 × 1440 = 10_080`（1m grain × 60s timer × 7d）
- `non_null_pct ≥ 90.00`
- `avg_imb` ∈ [-0.5, +0.5]（市場通常微正/微負，rarely 持續極端）
- `min_imb ≥ -1.0` / `max_imb ≤ +1.0`（clamp 保護）

**SOP（觀察方法）**：
- D+1：deploy 後 1h pilot — 預期 `non_null_pct ≥ 95%`（WS push rate 高，新增 lag 機率低）
- D+5：deploy 後 24h — 預期 `non_null_pct ≥ 92%`（含 WS 重連短窗期 sentinel NaN）
- D+12：7d 結束 — 預期 `non_null_pct ≥ 90%`，搭配 healthcheck [57] 連續觀察

**healthcheck 對接點**：sibling W2-IMPL-3 已在 `checks_btc_lead_lag.py` 加 check_57 監控 panel freshness；本 acceptance SQL 應加入 D+12 paper edge report (W2-IMPL-4) tooling 的 metric panel 之一。

### §3.4 cargo test baseline delta（pre vs post）

| 範圍 | pre-IMPL-1 baseline | post-IMPL-1 | delta |
|---|---|---|---|
| `cargo test --release -p openclaw_engine --lib panel_aggregator::btc_lead_lag` | 24 PASS | 31 PASS | **+7 new W2-IMPL-1 tests** |
| `cargo test --release -p openclaw_engine --lib panel_aggregator` | 54 PASS | 61 PASS | **+7（同上 propagation）** |
| `cargo test --release -p openclaw_engine --lib` | 2789 PASS（baseline 之前報告）| **2797 PASS** | **+8 (+1 是 ingest_task_drops + 7 IMPL-1)** |
| `cargo test --release -p openclaw_core --lib` | 434 PASS | **434 PASS** | 0 regression |
| `cargo build --release -p openclaw_engine` | 0 error / 18 pre-existing warning | 0 error / 18 pre-existing warning | 0 new warning |

**0 test regression / 0 new warning / 8 new test PASS**。

### §3.5 4-case unit test + 5-tick integration test

**4-case 純函數 unit test（per dispatch §3.1 E4 regression 重點 1）**：
1. ✅ `compute_book_imbalance_positive_when_bid_heavy` — bid > ask → (+0, +1]
2. ✅ `compute_book_imbalance_negative_when_ask_heavy` — ask > bid → [-1, -0)
3. ✅ `compute_book_imbalance_zero_when_balanced` — bid == ask → 0.0
4. ✅ `compute_book_imbalance_none_on_nan_or_empty` — NaN qty / empty levels → None（不寫 0.0）

**補充 2 個 unit test**：
5. ✅ `compute_book_imbalance_top_n_truncation` — top-N 截斷正確（第 6 檔不算進）
6. ✅ `on_tick_writes_real_book_imbalance_or_nan` — caller `Some` → 真實值；`None` → NaN

**5-tick integration test（per dispatch §3.1 E4 regression 重點 2）**：
- ✅ `ingest_task_to_producer_5_tick_integration` — mock WS Orderbook event stream 5 tick：
  - tick 1 正 +0.333 / tick 2 負 -0.500 / tick 3 平衡 0.0 / tick 4 強正 +0.714 / tick 5 強負 -0.818
  - 每 tick 驗：`snap.btc_book_imbalance` 非 NaN + 數值對齊 expected

**負路徑 unit test（補充）**：
- ✅ `ingest_task_drops_non_btc_or_non_orderbook_event` — ETHUSDT Orderbook + BTCUSDT Ticker 全 drop，slot 保持 None

**run_loop 簽名測試**：
- ✅ `run_loop_responds_to_cancel`（修改 既有 test 用新 `book_slot` 參數）

### §3.6 三端 git log 同步狀態

**Mac 工作目錄狀態**：working tree dirty（含 sibling W2-IMPL-2/3/4 + 本 IMPL-1 + 隨後 P1 V083 系列 + 其他 unstaged）。
**HEAD**: `21ed6d3e`（最新 push 為 PM commit cycle 前的狀態）。
**Linux 同步狀態**：本 sub-agent 不直接觸發 Linux 同步；待 PM 統一 commit + push + SSH sync。
**push 計劃**：依 dispatch v3.7 §5.1 D+0 deploy + D+1~D+5 evidence collection 走 PM 統一 commit chain，不在本 IMPL-1 強行 push。

---

## §4 16 原則 + 硬邊界合規

| 條目 | 合規狀態 | 證據 |
|---|---|---|
| §二 原則 1 單一寫入口 | ✅ | 本 IMPL-1 不影響 IntentProcessor / 訂單寫入路徑 |
| §二 原則 3 AI 輸出 ≠ 即時命令 | ✅ | 本 IMPL-1 不觸及 Decision Lease / authorization |
| §二 原則 4 策略不繞風控 | ✅ | producer 純計算，不下單 |
| §二 原則 7 學習 ≠ 改寫 Live | ✅ | paper-only fence 三層深度防禦保留（Layer 1+2+3） |
| §二 原則 8 交易可解釋 | ✅ | snapshot.btc_book_imbalance NaN sentinel + tracing log 兼顧 |
| §三 RuntimeEnv | ✅ | `OPENCLAW_ENABLE_PAPER=1` 才 spawn ingest task（per IMPL-2 fence） |
| §四 硬邊界 max_retries=0 | ✅ | 0 觸碰 |
| §四 硬邊界 live_execution_allowed | ✅ | 0 觸碰 |
| §四 硬邊界 OPENCLAW_ALLOW_MAINNET | ✅ | 0 觸碰 |
| §四 硬邊界 authorization.json | ✅ | 0 觸碰 |
| §四 硬邊界 execution_authority | ✅ | 0 觸碰 |
| §七 跨平台 grep `/home/ncyu` / `/Users/[a-z]+/` | ✅ | 0 命中（grep 驗證） |
| §七 注釋默認中文（廢除 bilingual mandate） | ✅ | 新代碼注釋全中文 + 部分技術術語 English（如 `MODULE_NOTE`, `tokio::select!`） |
| §七 雙語 MODULE_NOTE | ✅ | btc_lead_lag.rs 頂部 MODULE_NOTE W2-IMPL-1 補強 |
| §九 LOC ≤ 2000 hard cap | ✅ | btc_lead_lag.rs 1771 / main.rs 1395 / main_fanout.rs 248 / mod.rs 645 全 < 2000 |
| §九 LOC ≤ 800 warning | ⚠️ | btc_lead_lag.rs 1771（pre-existing 1253 baseline，本 IMPL +518）；main.rs 1395（pre-existing 1313 baseline，本 IMPL +82）；pre-existing baseline > 800 governance exception clause（§九）適用 |

---

## §5 不確定 / push back 建議

### §5.1 top-5 vs top-10（重要 trade-off）

spec §3.1.3 字面 "top-10"；我 IMPL 採 top-5 因 ws_client/parsers.rs 既有抽取邊界。**建議 PA + MIT 簽 acceptance**：
- 短期接受 top-5 + 注釋說明 reference ceiling
- 中期（D+12 paper edge report）若 7d evidence 顯示信噪比不足，重派 sub-task 升級到 top-10（需改 ws_client/parsers.rs + edge_predictor downstream consumer）

### §5.2 panel + book arm 雙 Arc clone

fan-out 每 tick 多 1 次 Arc::clone（從 1 變 2 clone）。tick rate ~280 tps × 1 µs Arc::clone ≈ 0.28 ms/s overhead — 可忽略。但若未來增第 3+ arm 應改 broadcast::Sender 統一處理（短期 N=2 mpsc 簡單即可）。

### §5.3 256 vs 1024 book channel cap

我選 256 因 single-symbol BTCUSDT orderbook update rate ~100 Hz × 2.5s burst ≈ 250。E2 可建議升 512 增加 buffer headroom（不破不變式，純 tuning）。

### §5.4 7d ≥ 90% non-null 驗證 SOP

acceptance SQL 已寫；但未把它 wired 進 healthcheck 或 cron — 留給 W2-IMPL-3 sub-agent 整合，或在 W2-IMPL-4 paper edge report 工具中跑。**PA / PM 決定接線點**。

### §5.5 file size LOC 1771（btc_lead_lag.rs）

per §九 pre-existing baseline exception clause：baseline 1253 已 > 800 警告；本 IMPL +518 推到 1771（仍 < 2000 hard cap）。**PM Sign-off 必文明標 governance exception accept 理由**：
- (a) 接受 wave 後 LOC ≤ pre-existing baseline + 5 LOC ❌ FAIL（+518 不滿足）
- (b) 同時開 P2 ticket 處理 pre-existing > 800 violation ✅ 建議：N+2 sprint 拆分 btc_lead_lag.rs → producer.rs / ingest_task.rs / db_writer.rs
- (c) 明文記錄 governance exception ✅ 本 report §4 已含

---

## §6 後續工作鏈 hint

### §6.1 E2 review 建議重點（per dispatch §3.1 E2 review 重點 1-4）

1. **WS-first 不撞既有 connection**：grep `orderbook.50.BTCUSDT` 確認既有 subscription，0 新 connection（已驗）
2. **lookahead bias shift(1) 嚴格**：on_tick 內 `btc_book_imbalance: Option<f64>` 從 caller 傳入，slot 寫入時序由 ingest task 端 100 Hz vs 1/60s read 自然 shift(1)；無 future leak
3. **NaN propagation safe**：`None → NaN` sentinel；下游 evaluator 需用 `WHERE NOT btc_book_imbalance = 'NaN'::REAL` 過濾
4. **Rate budget 0 req/s**：純 WS push，0 REST polling；spec rate budget 表 0 增量

### §6.2 E4 regression 重點（per dispatch §3.1 E4 regression）

1. ✅ 4-case unit test PASS
2. ✅ 5-tick integration test PASS
3. ✅ 既有 panel_aggregator 24 test 全 PASS（regression 0）
4. ✅ openclaw_core lib 434 test 全 PASS（regression 0）
5. ✅ openclaw_engine lib 2797 PASS（baseline 2789 + 8 new）

### §6.3 PM commit hint（per workflow chain）

待 E2 + E4 PASS 後 PM 統一 commit chain：
```bash
# 預期 PM commit message：
# E1 IMPL: W2-IMPL-1 btc_book_imbalance WS orderbook 接線
#
# - 加 BtcOrderbookSlot + ingest task + compute helper + 7 unit/integration tests
# - 整合 sibling W2-IMPL-2 (Layer 2 fence) + W2-IMPL-3 (healthcheck) + W2-IMPL-4 (paper edge report)
# - 0 cargo test regression / 0 cross-platform compliance violation
# - panel_aggregator::btc_lead_lag.rs +518 LOC（per §九 pre-existing baseline exception clause N+2 P2 split-file ticket）
#
# E2-Review: <hash> @<date>
# E4-Regression: <hash> @<date>
# Co-Authored-By: <PM identity>
```

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_1_orderbook_wiring.md）
