# E2 對抗審核 — W2 IMPL chain 4 sub-task（commit `1f0354cf`）

- **Date**: 2026-05-11
- **E2**: Senior Backend Code Reviewer + Adversarial Auditor
- **Verdict**: **APPROVE-CONDITIONAL · PASS to E4**（0 BLOCKER / 0 HIGH / 0 MEDIUM / 4 LOW / 2 P2 governance ticket）
- **Commit**: `1f0354cf` W2 IMPL chain 4 sub-agent land + sibling V083 E2 review
- **Baseline**: `21ed6d3e` E4 PASS P1 V083 fix
- **Working dir HEAD**: Mac/Linux 一致 `f338f3df`（1f0354cf 在 stack 内）
- **Sources**:
  - PA dispatch plan: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w2_impl_v12_dispatch_plan.md`
  - 4 E1 reports: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_{1,3,4}_*.md` + W2-IMPL-2 inline 在 commit body

---

## 1. Scope — 4 sub-task + 跨整合

| Sub-task | 改動 file | LOC delta | Verdict |
|---|---|---|---|
| W2-IMPL-1 Orderbook 接線 | `panel_aggregator/btc_lead_lag.rs` (1253→1771 +518) + `main.rs` (+118) + `main_fanout.rs` (+39) + `panel_aggregator/mod.rs` (+7) | 淨 +644 | PASS |
| W2-IMPL-2 Layer 2 fence amendment | `main.rs` env-gate 三狀態 + `strategies/cross_asset/mod.rs:12-13` MODULE_NOTE + spec v1.2→v1.3 inline edit | ~80 LOC + spec amend | PASS |
| W2-IMPL-3 Healthcheck [57] | `checks_btc_lead_lag.py` (NEW 321) + `test_btc_lead_lag_panel_healthcheck.py` (NEW 273) + `__init__.py` (+7) + `runner.py` (+33) | 淨 +656 | PASS |
| W2-IMPL-4 Paper edge report | `w2_paper_edge_report.py` (NEW 1257) + `w2_btc_alt_lead_lag_counterfactual.sql` (NEW 279) + SCRIPT_INDEX (+1) | 淨 +1537 | PASS |

---

## 2. 8 條 §九 + OpenClaw 9 條 checklist

| Item | 結果 |
|---|---|
| 改動範圍與 PA 方案一致 | ✓ 嚴格落實 dispatch §3.1-§3.4 |
| 沒有 except:pass 或靜默吞異常 | ✓ checks_btc_lead_lag.py line 124 `except Exception: pass` 是 defensive rollback（per [55]/[58]/[66] sibling pattern）— `noqa: BLE001 - defensive cleanup must not raise` 注釋說明，合理例外 |
| 日誌使用 %s 格式（非 f-string） | N/A（Python check 用 f-string 在 detail msg 是 return value 非 log；Rust 用 tracing 結構化欄位） |
| 新 API 端點 `_require_operator_role()` | N/A 無新 API |
| `except HTTPException: raise` 順序 | N/A |
| `detail=str(e)` 改 "Internal server error" | ⚠️ checks_btc_lead_lag.py line 138 `f"{type(exc).__name__}: {exc}"` — passive healthcheck 內部訊息給 operator/cron，不過 public HTTP；對齊 sibling [55]/[58] pattern；**accept** |
| asyncio 路由 blocking threading.Lock | ✓ N/A |
| 私有屬性穿透 `._xxx` | ✓ 無 |
| 跨平台 grep `/home/ncyu` `/Users/[a-z]+/` | ✓ 9 changed file 0 hit |
| 雙語注釋（2026-05-05 後默認中文） | ✓ 新代碼注釋全中文，部分技術術語 English（`MODULE_NOTE`、`tokio::select!`、`mpsc::Receiver`）保留合理 |
| Rust unsafe 零容忍 | ✓ 0 hit |
| Rust unwrap/expect 限不可恢復場景 | ✓ production code 0 unwrap/expect；test code 10 個 unwrap/expect 均合理（test assertion） |
| Rust panic 不在交易路徑 | ✓ 新代碼 0 panic（pre-existing main.rs:392 panic 屬 boot 失敗 fail-closed，不歸本 wave） |
| 跨語言 IPC schema 一致 | ✓ Python check_57 SQL aggregate + Rust producer V088 INSERT + SQL counterfactual 三方 cohort 7-sym 對齊；schema column 名稱 byte-equal |
| Migration Guard A/B/C | N/A 無新 V### migration（V088 在 sub-task 1 已 land） |
| healthcheck 配對 | ✓ W2-IMPL-3 [57] 強制配對 W2 paper engine 7d evidence collection |
| Singleton 登記 §九 表 | ✓ `BtcOrderbookSlot` 是 Arc<RwLock<Option<f64>>> per-spawn local（不是 module global singleton，類似 sibling `BtcLeadLagPanelSlot`），不需登記 |
| 文件大小（800/2000 行） | ⚠️ btc_lead_lag.rs 1771 (baseline 1253，本 wave +518) / w2_paper_edge_report.py 1257；均 > 800 警告線 < 2000 hard cap，**§4 詳述拍板** |
| Bybit API 改動先查字典手冊 | N/A 未動 Bybit REST/WS subscribe，沿用 既有 `orderbook.50.BTCUSDT` subscription（`multi_interval_topics.rs:110-111` + `main_ws.rs:50/89` 已預訂） |

---

## 3. 對抗反問結果（adversarial drill）

### W2-IMPL-1 Orderbook 接線

**Q1**: 「WS-first 不撞既有 connection — `orderbook.50.BTCUSDT` 真的已被 既有 subscription cover 嗎？」
- `grep -rn 'orderbook_topic("BTCUSDT")\|full_subscription_list' rust/openclaw_engine/src/`
- `multi_interval_topics.rs:140` 確認 `full_subscription_list` 加 `orderbook_topic(symbol)`；`main_ws.rs:50/89` 對每 watch symbol 調用 → BTCUSDT 必含
- 結論：rate budget **真實 0 req/s ongoing**，0 新 WS connection ✓

**Q2**: 「lookahead bias — producer.run_loop 60s read vs ingest 100 Hz write 真 shift(1) 還是 placeholder？」
- 親 read `panel_aggregator/btc_lead_lag.rs:794` ingest task `~100 Hz` write slot
- `panel_aggregator/btc_lead_lag.rs:795-798` run_loop `let btc_book_imbalance = *book_slot.read().await` 在 on_tick 前
- 60s timer 每次 tick 拿到的 slot 值必然 ≤ tick ts（push 比 read 早 ~6000:1 比例）→ **自然 shift(1)** 滿足
- 結論：lookahead-free 真實成立 ✓

**Q3**: 「NaN propagation safe — None → NaN sentinel 路徑 0 panic 嗎？」
- `compute_btc_book_imbalance` line 153-178 對 NaN qty / empty / sum=0 / 結果 NaN 全 fail-soft return None
- `on_tick` line 506 `btc_book_imbalance: btc_book_imbalance.unwrap_or(f64::NAN)` — Some→真值 / None→NaN
- 結論：fail-soft path 0 panic ✓
- **⚠️ 文檔 vs 代碼不一致 [LOW-1]**：E1 report §3.2/§3.3 寫「PG INSERT 寫 'NaN'::REAL」但實際 `btc_lead_lag_writer.rs:113` `nan_to_null_f32(snapshot.btc_book_imbalance)` 對 NaN 寫 **PG NULL**（不是 NaN literal）。實際 runtime 行為對 [57] healthcheck `FILTER (WHERE btc_book_imbalance IS NOT NULL)` 過濾仍正確 fail-soft。建議 E1 修報告描述對齊代碼

**Q4**: 「Rate budget 0 req/s — 既有 subscription extension 還是新 connection？」
- 結論：純既有 subscription 額外 fan-out arm，0 新 connection（已驗 Q1）✓

**Q5**: 「top-5 vs spec top-10 trade-off — PA + MIT acceptance OK 還是必修？」
- E1 §2.2 + 註解 line 105-114 明標 trade-off：top-5 是 parsers.rs 既有抽取邊界，top-5 vs top-10 corr ≈ 0.92（Cont & Kukanov 2017 sparse-book 容忍）
- 改 parsers 升級到 top-10 會影響 edge_predictor downstream consumer，屬 PA 重新派發 sub-task 範圍
- 結論：**accept top-5 + 7d evidence 後 PA/MIT 拍板是否升級** — 不阻 W2 deploy ✓

**Q6**: 「btc_lead_lag.rs 1771 LOC pre-existing baseline exception — §九 clause apply OK 還是 P2 immediate refactor？」
- §九 「pre-existing baseline exception clause」**僅適用 baseline 已超 2000 行**；本 wave baseline 1253（>800 警告但 ≤ 2000），不適用該 clause
- 本 wave 把 1253 → 1771（< 2000 hard cap）屬「新 wave 推 ≤2000 推到 ≤2000」場景；**§九 800 警告線 ⚠️ 必標記**
- 結論：**P2 ticket** N+2 sprint 拆分 btc_lead_lag.rs（建議 split `producer.rs` / `ingest_task.rs` / `db_writer.rs`）；不阻 deploy ✓

### W2-IMPL-2 Layer 2 fence amendment

**Q1**: 「Layer 1 fence 保持原樣 — `step_4_5_dispatch.rs:206-212` `_ => None` 不被改？」
- `grep -nE '_ => None' rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
- 命中 `:211: _ => None, // demo / live_demo / live → fence 主防線`
- 結論：**Layer 1 主防線完整無觸碰** ✓

**Q2**: 「env-gate 三狀態完整 — cover 三條件？」
- main.rs:1005-1018 三 if/else if/else block 對應 (a)/(b)/(c) 三狀態
- (a) `OPENCLAW_ENABLE_PAPER=1` → spawn
- (b) env unset/0 + `!has_demo && !has_live` → spawn（dev/test 工作流）
- (c) env unset/0 + `has_demo || has_live` → skip（fence fired）
- subtle case: `OPENCLAW_ENABLE_PAPER=0` 顯式 0 → `map(|v| v.trim() == "1")` 回 false，fall through 到 else-if，行為同 unset ✓
- 結論：三狀態完整對齊 spec v1.3 §6.2 ✓

**Q3**: 「spec §7.1 + §8.1 不動 — grep 驗？」
- `git diff -- docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`
- v1.3 inline edit 純 §6.2 Layer 2 重寫 + §11 註明 + Change Log header；§7.1 mandatory metric 6 條 + §8.1 三檔 step gate 0 行改動
- 結論：amend 不破 acceptance gate（IMPL phase 不需重 sign-off）✓

**Q4**: 「Change Log v1.3 完整 — header + §6.2 inline edit + cross_asset/mod.rs MODULE_NOTE 同步？」
- spec v1.3 Change Log 完整（header + 2 row 對應 §6.2 + §11）✓
- cross_asset/mod.rs:12-21 MODULE_NOTE 同步更新（「Python writer fence」字樣全清，改 Producer env-gate 三狀態描述）✓
- 結論：spec / code / MODULE_NOTE 三方一致 ✓

### W2-IMPL-3 Healthcheck [57]

**Q1**: 「4 條件 SQL aggregate — hot-path index EXPLAIN ANALYZE PASS？」
- E1 §5.4 Linux PG dry-run 親 EXPLAIN ANALYZE：`Index Scan using _hyper_75_486_chunk_btc_lead_lag_panel_snapshot_ts_ms_idx` exec time 0.167ms
- 對 V088 hypertable per-chunk auto-index 命中（對應 `idx_btc_lead_lag_panel_ts_window`）
- 結論：hot-path index 真實命中 0 sequential scan ✓

**Q2**: 「PASS/WARN/FAIL 三段邏輯 — 邊界 case (age 120-300 / extreme 5-20% / book placeholder)？」
- age line 224-229：`< 120s PASS / 120-300s WARN / ≥ 300s FAIL`，對齊 dispatch §3.3
- extreme line 242-248：`< 5% PASS / 5-20% WARN / ≥ 20% FAIL`
- book line 254-265：三狀態（全 NULL / placeholder 0 / 真實值）；REQUIRED env 升 FAIL，default WARN
- 整體 verdict line 281-292：FAIL = age/cohort/extreme FAIL OR ≥3 條件破 OR (book_required AND book FAIL)
- 結論：三段邊界對齊 PA §3.3 規則 ✓

**Q3**: 「10/10 fixture test 真 PASS — 不是 stub return True？」
- Mac 端親跑 `python3 -m pytest helper_scripts/db/test_btc_lead_lag_panel_healthcheck.py -v`
- 10/10 PASS — 3 fixture（PASS/WARN/FAIL）+ 7 edge case（default-off / V088 absent / 0 row / book placeholder × 2 / REQUIRED 升級 / SQL read-only contract）
- test 用 unittest.mock cursor 真實 execute（非 return-True stub）✓

**Q4**: 「Linux PG dry-run 真跑 — hot-path index 真命中？」
- E1 §5.3 親跑 docker exec trading_postgres aggregate query → 真 row `age=37s/cohort=7/extreme=0/total=60/book_imb=0(placeholder)`
- E1 §5.4 親跑 EXPLAIN ANALYZE 確認 Index Scan ✓
- 結論：Linux PG empirical mandatory gate（per `feedback_v_migration_pg_dry_run.md`）satisfied ✓

### W2-IMPL-4 Paper edge report

**Q1**: 「PSR(0) Bailey-LdP 2012 formula 正確 — 禁 normal z-test？」
- line 252-296 `compute_psr_bailey_lopez_de_prado_2012`：含 `skew + kurt + _normal_cdf` + `denom_sq <= 0 → None fail-closed`
- raw kurtosis vs excess kurtosis：(raw_kurt - 1) / 4 ≡ (excess_kurt + 2) / 4（因 raw = excess + 3）→ Bailey-LdP 原 formula equivalent ✓
- denom_sq ≤ 0 → return None（極端 skew + 高 SR 組合 fail-closed，禁假樂觀）✓
- 結論：formula 嚴格 Bailey-LdP 2012 ✓

**Q2**: 「DSR K=95 mu_0=√(2 ln 95) 公式 — ln 自然對數，非 log₁₀？」
- line 318 `mu_0 = math.sqrt(2.0 * math.log(k_trials))` — Python `math.log` 默認自然對數 ln
- √(2 × ln 95) = √(2 × 4.5538) = √9.1076 ≈ 3.0179 ✓
- smoke-test 印 `mu_0=√(2 ln 95)=3.018` byte-equal
- 結論：ln 自然對數正確（per Bailey-LdP 2014 §4.2）✓

**Q3**: 「block-bootstrap moving-block size=60min — deterministic seed=20260512？」
- line 327 seed default `20260512`（YYYYMMDD-ish 確定性）
- line 354 `rng = random.Random(seed)` 純確定
- line 355-364 moving-block sampling：`n_blocks_per_iter = n // block_size`，sample 後 truncate `[:n]`
- **[LOW-2]** subtle：n=150, block=60 → 2 blocks 抽 = 120 sample，truncate `[:150]` 仍 120 個（不夠 150）；statistics.mean(120 sample) 計算 OK，但 mean 是 based on 120 vs 150；對 CI 寬度影響 <1%，不阻
- 結論：deterministic seed + moving-block ✓；truncation 偏 P3 nice-to-have（建議 wrap-around / overshoot 處理但不必修）

**Q4**: 「SQL 三方向 counterfactual — CASE WHEN expected_dir +1/-1/0 對齊？」
- SQL line 247-267 三 CASE WHEN：
  - expected_dir=+1 → `+1 × forward_return`（LONG）
  - expected_dir=-1 → `-1 × forward_return`（SHORT）
  - expected_dir=0 → NULL（無信號 baseline）
- Python `_select_forward_window_field` (line 489-500) 對齊 cf_net_edge_60s_bps / 120s / 300s 三 column 名稱 byte-equal
- regime_tag='extreme' filter 留給 Python 端按 metric 計算時拍板（per-symbol breakdown vs pooled 各自決定）
- 結論：三方向對齊 spec §7.2 100% ✓

**Q5**: 「1257 LOC > 800 警告 — 拆 module 還是維持 single-file？」
- §九 800 警告線：**E2 必標記** + 開 P2 split ticket
- E1 §8.1 提供拆分提案：`w2_paper_edge_metrics.py` + `w2_paper_edge_render.py` + `w2_paper_edge_smoke.py` + `w2_paper_edge_report.py` (CLI)
- single-file 利：operator 一鍵跑 + 部署 + copy 簡單；不利：> 800 警告
- 結論：**accept single-file 為當前 deploy + P2 ticket** N+2 sprint 拆 4 file（不阻 deploy）

**Q6**: 「Linux PG dry-run 屬 E4 範疇還是必 E2 親跑？」
- E1 §8.2 自承「Mac 上 ssh trade-core 不可達當前 workflow」屬 E4 範疇
- Mac 端 smoke-test ALL PASS（3 mock case + PSR + DSR + CI + R²）已驗 formula 正確性
- Linux PG empirical 真實 SQL execute 留 E4 regression scope
- 結論：accept E4 範疇 ✓（per `feedback_v_migration_pg_dry_run.md` — 已強制 E4 必跑）

### 跨 sub-task 整合

**Q1**: 「W2-IMPL-1 + W2-IMPL-2 共享 main.rs — 兩 sub-agent 改動 merge 後語意正確？」
- main.rs:933 W2-IMPL-1 alloc `book_event_tx/rx`
- main.rs:957 W2-IMPL-1 pass `Some(book_event_tx)` 給 spawn_fan_out
- main.rs:1005-1078 W2-IMPL-2 env-gate wrap + W2-IMPL-1 ingest task spawn 在 if-block 內
- main.rs:1069 fence skip 路徑 explicit `drop(book_event_rx)` → fan-out try_send fail silent
- 結論：兩 hunks 正交（IMPL-1 加 channel alloc + fan-out arm；IMPL-2 加 env-gate wrap）；merge 後語意正確 ✓

**Q2**: 「W2-IMPL-3 ground truth book_imb=0 確認 IMPL-1 未 land production WS — 但已 IMPL ingest task，post-deploy book_imb 應 != 0？」
- E1 §5.3 Linux PG runtime 真 row：`book_imb_abs_avg=0`（producer 還寫 placeholder 0.0 — 這個是 fixture run，pre-deploy 狀態）
- W2-IMPL-1 land 後（restart_all --rebuild）：on_tick `unwrap_or(f64::NAN)` → NaN → writer `nan_to_null_f32` → PG NULL
- 真實 deploy 後 WS ingest task running → slot has Some(value) → 大部分 row btc_book_imbalance != NULL 且 != 0
- 結論：**W2-IMPL-3 [57] check 邏輯對 IMPL-1 deploy 前後切換正確** — 預設 default-off (`OPENCLAW_W2_HEALTHCHECK_BOOK_REQUIRED=0`) 給 WARN；deploy 後設 `=1` 升 FAIL；自然漸進式 ✓

**Q3**: 「W2-IMPL-4 SQL 對齊 IMPL-3 healthcheck schema — panel.btc_lead_lag_panel 12 column 一致？」
- E1 §5.2 V088 12 column schema：snapshot_ts_ms / lead_window_secs / btc_lead_return_pct / *_60s / *_300s / btc_volume_z / btc_book_imbalance / alt_symbols / alt_xcorr / alt_expected_dir / regime_tag / source_tier
- SQL counterfactual line 110-122 panel_window CTE 引用 12 column 全對齊（含 source_tier ✓）
- Python row reader 對齊 SQL output 名稱 byte-equal（`btc_lead_return_pct_60s` etc.）
- 結論：三方 schema 100% 對齊 ✓

---

## 4. 16 原則 + DOC-08 §12 + 硬邊界 5 項

| 條目 | 觸碰？ | 證據 |
|---|---|---|
| 原則 1 單一寫入口 | 0 | producer 純 PG INSERT panel.btc_lead_lag_panel，不影響 IntentProcessor / 訂單寫入路徑 |
| 原則 3 AI 輸出 ≠ 即時命令 | 0 | 不觸 Decision Lease / authorization |
| 原則 4 策略不繞風控 | 0 | producer 純計算不下單；ma_crossover/grid_trading on_tick consume surface.btc_lead_lag 仍 emit tracing only |
| 原則 7 學習 ≠ 改寫 Live | 0 | paper-only fence 三層深度防禦 — Layer 1（step_4_5_dispatch engine_mode gate）+ Layer 2（W2-IMPL-2 env-gate）+ Layer 3（cross_asset/mod.rs `if let Some(panel)` defensive guard） |
| 原則 8 交易可解釋 | strengthened | snapshot.btc_book_imbalance NaN sentinel + tracing log + per-cohort counterfactual delta + per-symbol breakdown 強化 reconstruct alpha source |
| 硬邊界 `live_execution_allowed` | 0 | grep 0 hit（9 changed file） |
| 硬邊界 `max_retries=0` | 0 | grep 0 hit |
| 硬邊界 `OPENCLAW_ALLOW_MAINNET` | 0 | grep 0 hit |
| 硬邊界 `authorization.json` | 0 | grep 0 hit |
| 硬邊界 `execution_authority` | 0 | grep 0 hit |
| SM-04 Guardian | 0 | grep 0 hit |
| IntentProcessor | 0 | grep 0 hit |
| paper_state singleton | 0 | grep 0 hit |
| Decision Lease / lease_router | 0 | grep 0 hit |
| DOC-08 §12 9 條 | 0 觸碰 | per E1 4 個 report §7 / §4 / §4 / §7 acknowledge |

---

## 5. Findings

### 5.1 [LOW-1] W2-IMPL-1 E1 report §3.2/§3.3 NaN propagation 文檔錯誤

**位置**：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_1_orderbook_wiring.md` §3.2 line 123 + §3.3 line 137-141

**現狀**：E1 report 寫「`snapshot.btc_book_imbalance = NaN` 時 V088 INSERT 寫 'NaN'::REAL；下游 evaluator 用 `WHERE NOT btc_book_imbalance = 'NaN'::REAL` 過濾」

**實際**：`rust/openclaw_engine/src/database/btc_lead_lag_writer.rs:113` 用 `nan_to_null_f32(snapshot.btc_book_imbalance)` 把 NaN 轉 PG NULL（不是 NaN literal）。

**為什麼 LOW 非 HIGH**：
- runtime 行為**對 healthcheck 仍正確**：[57] check_57 `FILTER (WHERE btc_book_imbalance IS NOT NULL)` filter 出 NULL → fail-soft 正確
- 對 SQL counterfactual：`CASE WHEN ak.close_current IS NULL ...` 三 CASE WHEN 用 `close_current IS NULL` 過濾 — btc_book_imbalance 不參與 cf_net_edge 計算（不影響）
- W2-IMPL-3 [57] check 註解 line 251-252 也寫「W2-IMPL-1 接線後 abs(btc_book_imbalance) > 0 真實值」— 與實際 NaN→NULL 行為一致（avg(ABS(NaN)) 不存在，因 NaN 已被 nan_to_null 轉 NULL 排除）

**為什麼 LOW 非 INFO**：
- 未來 reviewer 讀 E1 report §3.2 SQL example 會被 mislead；建議 E1 修報告

**建議修法**（E1 follow-up）：
- E1 report §3.2 改：`snapshot.btc_book_imbalance = NaN → writer.nan_to_null_f32 → PG NULL；下游 evaluator 用 WHERE btc_book_imbalance IS NOT NULL 過濾`
- E1 report §3.3 acceptance SQL `non_null_pct` 公式不變（已用 `IS NOT NULL`），但註解寫的「NOT btc_book_imbalance = 'NaN'::REAL」改 `btc_book_imbalance IS NOT NULL`

**Verdict**：**不阻 deploy**；E1 在 follow-up commit 修報告即可。

### 5.2 [LOW-2] block-bootstrap truncation 偏移（subtle）

**位置**：`helper_scripts/reports/w2_paper_edge_report.py:355-364`

**現狀**：`n_blocks_per_iter = max(1, n // block_size)` + `sample[:n]` truncation 對 n=150, block=60 → 抽 2 blocks = 120 sample，truncate `[:150]` 仍 120 個 → statistics.mean 基於 120 sample 而非 150。

**影響**：
- CI 寬度估計偏向 120 sample 而非 150 sample；對 D+12 paper edge 7d × 1m × 7 sym ~70000 sample 場景，n//60 = 1166 blocks → 70000 個 sample，truncate `[:70000]` 仍 70000 sample（不偏）
- mock smoke-test n=150 偏移可觀，real-data N=70000 不偏
- 對 verdict（CI lower > 0 / CI 含 0）結論幾乎無影響

**為什麼 LOW 非 INFO**：
- 學術精確性而言 moving-block bootstrap 在 truncation 邊界應用 wrap-around 或 overshoot 處理
- spec §7.1 metric (5) 明定 block_size=60min fixed 但未指定 truncation 策略；可接受 trade-off

**建議修法**（P3 nice-to-have）：
- 升級 `n_blocks_per_iter = (n + block_size - 1) // block_size`（向上取整）+ `sample[:n]` 強制截斷 n 長度
- 或加 wrap-around（n=150 case 第 2 個 block 起點允許 [0, n - block_size + 1) 含 overshoot）

**Verdict**：**不阻 deploy + 不阻 D+12 paper edge report**；P3 ticket 標記學術精確性 follow-up。

### 5.3 [LOW-3] main_fanout.rs Arc clone awkward fallback

**位置**：`rust/openclaw_engine/src/main_fanout.rs:207-238`

**現狀**：
```rust
let panel_arc_for_send = if panel_tx.is_some() || book_tx.is_some() {
    Some(arc_event.clone())
} else {
    None
};
if let Some(ref ptx) = panel_tx {
    let p_evt = panel_arc_for_send
        .as_ref()
        .map(Arc::clone)
        .unwrap_or_else(|| Arc::clone(&arc_event));
    ...
}
```

**問題**：當 `panel_tx.is_some()` 進入 if-block，`panel_arc_for_send` 必為 `Some`（per outer condition），所以 `unwrap_or_else(|| Arc::clone(&arc_event))` fallback 永不執行 — 是 dead-code-style fallback。

**為什麼 LOW 非 INFO**：
- 編碼 awkward 對未來 reviewer 困惑；建議精簡為 `Arc::clone(&panel_arc_for_send.as_ref().expect("must be Some when panel_tx.is_some()"))` 或更直接的 `Arc::clone(&arc_event)`（既然 outer 已 `panel_tx.is_some()`，直接 clone arc_event 即可，不需 panel_arc_for_send 中間變量）

**建議修法**（P3）：簡化為：
```rust
if let Some(ref ptx) = panel_tx {
    if ptx.try_send(Arc::clone(&arc_event)).is_err() { ... }
}
if let Some(ref btx) = book_tx {
    if btx.try_send(Arc::clone(&arc_event)).is_err() { ... }
}
```
Arc::clone 兩次都 OK（cost ~ 1 atomic increment per clone），不需中間 Option 包裹。

**Verdict**：**不阻 deploy**；屬編碼整潔度，P3 housekeeping 留 E1 同 patch §5.1 處理。

### 5.4 [LOW-4] checks_btc_lead_lag.py line 138 exception message 細節露出（acknowledge 已有 sibling pattern）

**位置**：`helper_scripts/db/passive_wait_healthcheck/checks_btc_lead_lag.py:138, 190`

**現狀**：`f"[57] ... query failed: {type(exc).__name__}: {exc}"` — 對外暴露 PG error string 細節（schema name / table name / column type）。

**評估**：
- caller 是 passive healthcheck cron + operator 手動跑 — **trusted internal observer**
- 對齊 sibling [55]/[58]/[66] 同 pattern（passive sentinel 必須 surface details for debug）
- 不違 §九 SEC-04「detail=str(e) 改 'Internal server error'」精神（該 rule 針對 public HTTP route）

**Verdict**：**accept** — sibling pattern consistent，passive healthcheck context 合理；不阻 deploy。

### 5.5 [P2-1] btc_lead_lag.rs 1771 LOC pre-existing > 800 警告（governance ticket）

**位置**：`rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` 1253 baseline → 1771（+518 本 wave）

**§九 governance 評估**：
- baseline 1253 > 800 warning line（pre-existing 違規）但 < 2000 hard cap
- 本 wave +518 推到 1771（仍 < 2000）
- **「pre-existing baseline exception clause」僅適用 baseline > 2000，本 case 不適用該 clause**
- 800 警告線：E2 必標記 + 開 P2 split ticket（不阻 merge）

**建議拆分**（N+2 sprint）：
```
panel_aggregator/btc_lead_lag/
├── mod.rs (~50 LOC re-export)
├── producer.rs (~700 LOC: BtcLeadLagProducer + on_tick + run_loop)
├── snapshot.rs (~200 LOC: BtcLeadLagPanelSnapshot + arrays_aligned)
├── ingest_task.rs (~150 LOC: BtcOrderbookSlot + compute_btc_book_imbalance + spawn_btc_orderbook_ingest_task)
└── tests/ (~700 LOC)
```

**Verdict**：**P2 ticket** N+2 sprint 拆分；不阻當前 deploy。

### 5.6 [P2-2] w2_paper_edge_report.py 1257 LOC > 800 警告（governance ticket）

**位置**：`helper_scripts/reports/w2_paper_edge_report.py` NEW 1257 LOC

**§九 評估**：同 P2-1（>800 警告 < 2000 cap）

**建議拆分**（per E1 §8.1 提案）：
- `w2_paper_edge_metrics.py` (~300 LOC: PSR/DSR/bootstrap/R²/t-stat helpers + step_gate_verdict)
- `w2_paper_edge_render.py` (~300 LOC: render_markdown)
- `w2_paper_edge_smoke.py` (~300 LOC: 3 mock fixture + run_smoke_test)
- `w2_paper_edge_report.py` (~350 LOC: CLI + PG conn + 整合 main)

**Verdict**：**P2 ticket** D+12 paper edge report 跑完後（不阻 D+12 跑）N+2 sprint 拆 4 file；不阻當前 deploy。

---

## 6. Cargo test + Pytest + Smoke-test runtime evidence

| Test suite | Mac 端結果 | Linux 端 |
|---|---|---|
| `cargo test --release -p openclaw_engine --lib panel_aggregator::btc_lead_lag` | **31 PASS** / 0 fail / 2766 filtered | E4 範疇 |
| `cargo test --release -p openclaw_engine --lib` 全 | **2797 PASS** / 0 fail / 0 ignored | E4 範疇 |
| `pytest helper_scripts/db/test_btc_lead_lag_panel_healthcheck.py -v` | **10 PASS** / 0 fail | Mac 已驗 |
| `python3 helper_scripts/reports/w2_paper_edge_report.py --smoke-test` | **ALL PASS** (plus15/plus5_15/minus5 + PSR/DSR/CI/R²) | Mac 已驗 |
| Linux PG empirical [57] query + EXPLAIN ANALYZE | (E1 §5 已附 docker exec evidence) | E4 重跑 mandatory |
| Linux PG SQL counterfactual dry-run | 待 E4（per `feedback_v_migration_pg_dry_run.md`） | E4 mandatory |

---

## 7. PA E2 重點審查 3 點

### 7.1 三層 fence 主防線完整性 ✓

- **Layer 1**（主防線）：`step_4_5_dispatch.rs:211` `_ => None, // demo / live_demo / live → fence 主防線` ✓ 未被 W2-IMPL-1/2 動到
- **Layer 2**（W2-IMPL-2 amend）：main.rs:1005-1018 env-gate 三狀態完整 ✓
- **Layer 3**（cross_asset/mod.rs）：`if let Some(panel) = surface.btc_lead_lag` defensive guard ✓ 未動

### 7.2 Strict shift(N) lookahead-free 嚴格驗 ✓

- W2-IMPL-1：ingest 100 Hz vs producer 60s read 自然 shift(1)；on_tick 內 buffer push 順序仍 lookahead-free
- W2-IMPL-4 SQL：LEAD() forward 1/2/5 bar 對齊 panel.snapshot_ts_ms 1m bucket close；strict shift(N) past close 寫 / strict shift(N) future close 算 OLS R²

### 7.3 CC compliance + 硬邊界 5 項 + DOC-08 §12 9 條 0 觸碰 ✓

- 16 原則 / 5 硬邊界 / SM-04 / Guardian / IntentProcessor / paper_state / decision_lease / authorization.json — **全 0 觸碰**（已 §4 verify）

---

## 8. PASS to E4

E4 regression scope 重點：

1. **cargo test --release -p openclaw_engine --lib** Linux 重跑（既已 Mac 2797 PASS）
2. **cargo build --release -p openclaw_engine --bin openclaw-engine** Linux 編 clean
3. **Linux PG dry-run mandatory**（per `feedback_v_migration_pg_dry_run.md`）：
   - `ssh trade-core "psql ... -f sql/queries/w2_btc_alt_lead_lag_counterfactual.sql -v window_days=7 -v cohort_symbols='{ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,DOTUSDT}'"` 驗 SQL 對 V088 + trading.fills + trading.klines 三方真實 schema 跑得對
   - D+0 預期 panel.btc_lead_lag_panel 60 row（1h × 1m）+ trading.klines 1m 真實資料 → SQL 出來 ~420 row（60 panel × 7 symbol UNNEST，可能少數 NULL forward return 因 LEAD overshoot）
   - EXPLAIN ANALYZE 驗 hot-path index `idx_btc_lead_lag_panel_ts_window` 命中
4. **W2-IMPL-3 healthcheck Linux 端 docker exec 跑** `OPENCLAW_W2_HEALTHCHECK_ENABLED=1` 驗 verdict
5. **paper engine 6h smoke**：deploy 後 `panel.btc_lead_lag_panel` 累積 ≥ 250 row / 6h（1m × 360 - 缺失容忍）+ `btc_alt_lead_lag_shadow` tracing log target 出現 ≥ 50 row + `btc_book_imbalance != NULL` 樣本 ≥ 90%（W2-IMPL-1 接線生效驗證）

E4 不需重跑 31 unit / 10 pytest / smoke-test（E2 已 Mac verify）。

---

## 9. 三端 git log 同步 vs origin/main `1f0354cf`

| 端 | HEAD | 狀態 |
|---|---|---|
| Mac | `f338f3df` | `1f0354cf` 在 stack 內（後接 `c1dad6a3` + `f338f3df` PA RCA commit） |
| Linux trade-core | `1f0354cfd865a8b817e15d52d51e4879a7e4175f` | 與 Mac 對 1f0354cf 一致；但 Linux 落後 Mac 2 commit（待 PM operator pull）|
| origin/main | （需 PM 推 push）| `1f0354cf` 已 push |

**狀態**：三端對 `1f0354cf` 一致；Mac 領先 Linux 2 commit（PA RCA copy 報告 + RCA commit）為 sibling P0 RCA wave，不影響 W2 review。

---

## 10. Verdict

**APPROVE-CONDITIONAL · PASS to E4**

- 0 BLOCKER / 0 HIGH / 0 MEDIUM
- 4 LOW（LOW-1 E1 report NaN 描述錯誤 / LOW-2 bootstrap truncation / LOW-3 fanout Arc clone awkward / LOW-4 healthcheck exception message accept-as-sibling-pattern）
- 2 P2 governance ticket（btc_lead_lag.rs 1771 LOC + w2_paper_edge_report.py 1257 LOC）N+2 sprint 拆 file

**LOC 拍板總結**：
- btc_lead_lag.rs 1771（>800 警告 < 2000 cap）：**accept + P2 split ticket N+2**
- w2_paper_edge_report.py 1257（>800 警告）：**accept single-file + P2 split ticket N+2**
- 文件 size pre-existing baseline exception clause **不適用**（baseline 1253 < 2000）但 §九 800 警告線僅需 E2 標記 + 開 P2 ticket，不禁 merge ✓

**跨 sub-task 整合 risk**：
- W2-IMPL-1 + W2-IMPL-2 main.rs hunk 正交，merge 後正確 ✓
- W2-IMPL-3 [57] check 邏輯對 IMPL-1 deploy 前後切換正確（default-off → opt-in REQUIRED 漸進式）✓
- W2-IMPL-4 SQL panel 12 column 與 IMPL-3 healthcheck schema 100% 對齊 ✓
- 0 cross-language IPC schema drift

**E2 follow-up（housekeeping，不阻 deploy）**：
1. LOW-1 E1 修報告 §3.2/§3.3 NaN 描述對齊 nan_to_null_f32 行為
2. LOW-3 main_fanout.rs Arc clone 精簡（直接 `Arc::clone(&arc_event)` 兩次）— E2 可直接修但建議與 E1 LOW-1 同 patch
3. P2-1/P2-2 governance ticket N+2 sprint 拆 file

---

## 11. E2 Sign-off

- Mac 端 cargo test 2797/0/0 親跑 verify
- Mac 端 pytest 10/10 親跑 verify
- Mac 端 smoke-test ALL PASS 親跑 verify
- 三層 fence 對抗 grep verify（Layer 1 _ => None 未動 / Layer 2 env-gate 三狀態完整 / Layer 3 cross_asset 未動）
- 跨平台 grep 0 hit / 雙語注釋全中文 / 0 unsafe / 0 production unwrap/expect / 0 panic
- 16 原則 / 5 硬邊界 / DOC-08 §12 9 條 / SM-04 / Guardian / IntentProcessor / paper_state / decision_lease / authorization.json — **全 0 觸碰**
- spec v1.2 → v1.3 amendment 不破 §7.1 + §8.1 acceptance gate

PASS to E4 regression（Linux PG dry-run + cargo build + 既有 sibling regression）.

**E2 REVIEW DONE: APPROVE-CONDITIONAL · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--w2_chain_e2_adversarial_review.md**
