# 完成 TODO 歸檔批次 — 2026-04-20

**來源**：`/home/ncyu/BybitOpenClaw/srv/TODO.md` 2026-04-20 清理
**範圍**：W23 (2026-04-18 起) 至 2026-04-20 間完成的 14 組 TODO 項目
**動機**：TODO.md 積累至 629 行，長期完成項未歸檔。此批次將已完成條目整體歸檔，TODO.md 只保留活躍項。

---

## 1. DUAL-TRACK-EXIT-1 Step 0 可行性 Sprint ✅（2026-04-18）

**判決**：2/4 綠 + 1/4 黃 + 1/4 紅 → Phase 1 拆 1a/1b，Phase 2 shadow 從 W24 延後到 W25

- [x] **不確定 1 ✅ 綠（機制）**：estimator CLI 跑通 104 cells / demo grand_mean −2214 bps（**P1-15 查明為 28 phantom cells 污染，b0df1b3 修復**；live_demo 7d 乾淨值 −14.97 bps ≈ fee-neutral）；**不可 bind**（P1-14 bind blocker 獨立）
- [x] **不確定 2 🔴 紅**：`decision_features` 是 entry-time snapshot，7 維對齊僅 **1/7 直接**（`atr_pct`）+ 1/7 部分（`persistence_elapsed_ms ≈ entry_age_secs`）；`trading.decision_outcomes.max_favorable/max_adverse` 113k 全 NULL（dead column）；需新建 `learning.exit_features` + Rust exit handler 寫入
- [x] **不確定 3 ✅ 綠**：ma_crossover live_demo **2.23M** / grid_trading live_demo **16.5k**；小樣本（bb_breakout 0 / funding_arb 60 / bb_reversion 609 / grid demo 1.7k / ma_crossover demo 693）強制 P-only
- [x] **不確定 4 🟡 黃**：無 tick 表；kline 1-min 粒度；**且 `market.klines` 自 2026-04-16 21:08 停寫**（停電後管線未恢復，新增 `MARKET-KLINES-STALE-1`）→ fallback #6 事後歸因 audit
- [x] Sprint 產出：`docs/worklogs/2026-04-18-1--dual_track_exit_feasibility.md`

---

## 2. MARKET-KLINES-STALE-1 ✅ 2026-04-18（commit `65acde6`）

P1-CRITICAL · 2026-04-18 RCA ✅ · 2026-04-18 修復

**Root cause = PAPER-DISABLE-1 架構遺漏**（非停電事件）。`main.rs` Paper pipeline `market_data_tx: Some(market_tx)`，但 Demo 和 Live 都 `market_data_tx: None`（D19 註釋：`Paper handles that`）→ `on_tick.rs::emit_market_data_if_needed` `if let Some(ref tx)` None check 跳過 → `MarketDataMsg::KlineClose` 零發出 → `market_writer` task 起來但 channel 永遠空。Paper 自 PAPER-DISABLE-1（2026-04-16 21:08 最後一次 tick）預設不 spawn 後，DB kline 寫入完全斷。

**修復**（commit `65acde6`，三處 `Some(market_tx.clone())`）：paper/demo/live 三引擎皆 clone market_tx → 三路並行寫入；`market.klines` PK `(symbol, timeframe, ts)` + `ON CONFLICT DO NOTHING`（`market_writer.rs:180`）已 dedup，多 producer 安全。

---

## 3. EXIT-FEATURES-TABLE-1 ✅ 2026-04-19（commits `6ea643e` · `c7171b2` · `35808e9`）

P1-HIGH · 2026-04-18 設計草稿 ✅ · 2026-04-19 Phase 1b 全部接線 ✅ · 2026-04-19 Phase 1b GAP-1 修復 ✅ · 2026-04-20 R1 驗收 ✅

設計文件：`docs/worklogs/2026-04-18-2--exit_features_table_design.md`

### 3.1 Phase 1b producer wiring（commit `6ea643e`）
覆蓋 `emit_close_fill` 主路徑。

### 3.2 Phase 1b FUP（commit `c7171b2`）
補完 2 個漏接 close paths（`process_external_fill` IPC 外部 fill 報告 + `ipc_close_symbol` paper 分支：operator `/close_symbol` API + dust eviction + orphan_handler→Paper 模式）；抽出 `try_emit_exit_feature_row` `pub(crate)` helper；+3 tests / 5 pre-existing WIP `test_exit_feature_row_*` 全綠化。Track P 標籤覆蓋完整。

### 3.3 Phase 1b GAP-1（commit `35808e9`，部署 2026-04-19 22:32）
R1 觀察窗發現 demo 重啟後 89 fills 但僅 2 rows `learning.exit_features`（~97% 丟失）；並行 root-cause 審查鎖定 **`apply_confirmed_fill`（Demo/Live WS 確認成交平倉主路徑，commands.rs:421）從未呼叫 `try_emit_exit_feature_row`**。PAPER-DISABLE-1 前 paper 的 `emit_close_fill` 接線還 cover 得到；paper 關閉後 Demo/Live 靠 WS 回報走 `apply_confirmed_fill`，2 rows 是少數走 `process_external_fill` / `ipc_close_symbol` paper 分支的剩餘路徑。

修復：`commands.rs:442-566` 在 `apply_fill` 之前捕獲 `pre_close_snapshot`，在 `trading_tx.Fill` 送出後 `if realized_pnl != 0.0` 呼叫 `try_emit_exit_feature_row`（pattern 與 `process_external_fill` 對齊，`entry_context_id` 沿用 pre-close 捕獲的 `existing_entry_ctx`）。+2 regression tests（`apply_confirmed_fill_emits_exit_feature_row_on_close` 驗 demo 平倉送出 row with engine_mode=demo / side=1 / realized_net_bps>0 / peak_pnl_pct≈2% · `apply_confirmed_fill_exit_feature_fail_soft_when_tx_missing` 驗 tx 缺失時 Fill 仍正常送出）。engine lib 1629→**1631** passed。

**影響**：修前若不補，DUAL-TRACK Phase 1b W24 7 維閾值校準會嚴重缺料（daily exit_features 增量 ~3%→100%）；Track P T4 wiring 未來上線亦受益。

### 3.4 GAP-1 R1 follow-up 驗收 ✅ 2026-04-20 00:20 local
deploy+1.8h early snapshot，樣本 ≥5 達標提前結案：demo 窗口 `ts > 2026-04-19 22:32:57+02` 至 00:20 內 8 close fills / 8 exit_features rows → **coverage_ratio = 1.000**（遠 > 0.95 閾值）。Exit sources 分布合理：Strategy 6 + FastTrack 2。Trigger rules：`ma_reverse_cross` 5 · `fast_track_reduce_half` 2 · `grid_close_long` 1。3 close paths 全接線驗證：`emit_close_fill` (ma/grid) + `apply_confirmed_fill` demo WS-confirmed（GAP-1 主目標接線） + risk fast_track。LiveDemo 0 close fills（預期：authorization.json 未簽，pipeline 未 spawn）。

**若未來 Track P T4 PHYS-LOCK 接線**：屆時新增 `Physical` exit_source，需重跑驗收 SQL 確認不漏接（當前樣本全 Strategy/FastTrack，不覆蓋 Physical path）。

**驗收 SQL 模板（保留備查）**：

```sql
-- R1 GAP-1 follow-up：目標 coverage_ratio ≥ 0.95
-- deploy baseline: '2026-04-19 22:32:57+02'
SELECT
  'post-GAP1-deploy' AS window,
  (SELECT COUNT(*) FROM trading.fills
     WHERE engine_mode='demo'
       AND ts > '2026-04-19 22:32:57+02'
       AND realized_pnl != 0) AS close_fills,
  (SELECT COUNT(*) FROM learning.exit_features
     WHERE engine_mode='demo'
       AND ts > '2026-04-19 22:32:57+02') AS exit_features,
  ROUND(
    (SELECT COUNT(*)::numeric FROM learning.exit_features
       WHERE engine_mode='demo' AND ts > '2026-04-19 22:32:57+02')
    / NULLIF((SELECT COUNT(*) FROM trading.fills
       WHERE engine_mode='demo' AND ts > '2026-04-19 22:32:57+02'
         AND realized_pnl != 0), 0)::numeric,
    3) AS coverage_ratio;

SELECT
  SPLIT_PART(owner_strategy, ':', 1) AS close_kind,
  owner_strategy,
  COUNT(*) AS close_fills,
  ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM trading.fills
WHERE engine_mode='demo'
  AND ts > '2026-04-19 22:32:57+02'
  AND realized_pnl != 0
GROUP BY 1, 2
ORDER BY 1, 3 DESC;

SELECT exit_source, COUNT(*)
FROM learning.exit_features
WHERE engine_mode='demo' AND ts > '2026-04-19 22:32:57+02'
GROUP BY 1 ORDER BY 2 DESC;
```

---

## 4. DUAL-TRACK Phase 1a · 軌道 2 P1-7 A ✅ 2026-04-18（commit `2a36a3f`）

Rust 接 `trading.intents` 持久化。

**RCA**：DEDUP-PY-RUST 後 exchange 分支結構性缺 `persist_intent` 呼叫（Paper 走 `process_with_features` → `IntentResult{submitted}`，Demo/Live 走 `process_gates_only_with_features` → `ExchangeGateResult` 不含 submitted；on_tick.rs:986 `if result.submitted` guard 對 exchange 分支結構不可達）；`persist_verdict` 在 837 unconditional 而 `persist_intent` 完全沒呼叫 → 7d × 三窗口 `trading.intents` live/live_demo = 0 vs Approved verdicts 4.9M。

**修復**：on_tick.rs:879-902 在 exchange 分支 `if gate.approved` 內補上 `persist_intent(em, ts_ms, intent, final_qty, last_price, em)` + `stats.total_intents += 1`。+1 單測 + cargo test 1498/0。

**驗收**：binary mtime 2026-04-18 23:54 含 fix；engine PID 2390582 啟動 ~31 min 內 demo 側 **29 intents / 32 Approved verdicts = 90.6% ratio** ✅（DB 查核 2026-04-19 00:27 local）；29 intents 與 engine 內部 `total_intents=29` 完全吻合 → fix 走到預期 code path。live_demo 驗證 **pending**（operator 修 T0 bypass bug 後 pipeline 已關，需重啟並簽新 `authorization.json` 才能觀察首個 Approved→intent 形成；非 P0-6 本身問題）。

---

## 5. DUAL-TRACK Phase 1a · 軌道 2 P1-7 B ✅ 2026-04-19（commit `23b14ef`）

`edge_estimator_scheduler.py` daemon thread 每小時跑 demo + live_demo 模式 JS estimator 寫入 `settings/edge_estimates*.json`；`edge_estimator_routes.py` 提供 `POST /api/v1/edge-estimator/trigger` (Operator-only) + `GET /api/v1/edge-estimator/status`；main.py startup hook fail-open。

**手動觸發驗證**：live_demo n_cells=28 grand_mean **−8.46 bps**（自 −14.97 改善）；demo n_cells=0（P1-15 phantom 清空 + 死循環未產真 edge）。

**僅寫檔，未 bind cost_gate**（待 P1-16 修 + grand_mean>−50 bps + ≥2 策略 shrunk_bps>0）。同 commit 含 D19 assertion 移除（event_consumer/mod.rs:92 防 PAPER-DISABLE-1+MARKET-KLINES-STALE-1 後 panic）。

---

## 6. DUAL-TRACK Phase 1a · 軌道 1 Track P 物理層骨架 ✅ 2026-04-19

MARKET-KLINES-STALE-1 修完後展開。

- [x] **T1** `ExitFeatures` + `PhysicalDecision` 型別（commit `88b4ef9`；T1-FIX `c7d6a6c` 補 `Serialize`/`Deserialize` + 3 邊界測試）
- [x] **T2** `price_tracker` 加 `compute_roc` + 3 邊界測試（commit `981840f`）
- [x] **T3** `physical_micro_profit_lock` + `PhysLockConfig` Priority 6 替換 COST EDGE（commit `a963f0b`，reason 字串 `risk_close:phys_lock_<gate>`）
- [x] **T4** Combine Layer 骨架 + `ExitSource` 4 tags（commit `094d285`；T4-FIX `c7d6a6c` 修 on_tick wrapper prefix `PHYS-LOCK` → `risk_close:phys_lock_` + `strip_phys_lock_prefix` 剝殼 + `assert_eq!` 升 release 不可繞 + integration test 覆蓋 3 gate）
- [x] **T5** counterfactual exit audit CLI `program_code/audit/counterfactual_exit_audit.py`（commit `4feb17a`，1-min kline 粒度事後歸因，`MARKET-KLINES-STALE-1` 修復後可跑）
- [x] **E2 + E4 ✅ 2026-04-19 22:48**：counterfactual 粗粒度 audit + ≥47 單測（≥18 要求超達）。CLI `counterfactual_exit_audit.py` 實跑驗證：grid_trading demo 7d 141 positions / 4 hits / mean delta −39.4 bps（1 better / 2 worse / 1 neutral）· ma_crossover demo 7d 52 positions / 10 hits / mean delta −95.2 bps（5 better / 5 worse）。ENJUSDT 案例砍掉 198 bps 潛在收益 → 驗證 Phase 1a 骨架閾值「設計上保守」，校準工作正確排入 Phase 1b。單測分布：exit_features 6 + exit_feature_schema 3 + compute_roc 12 + phys_lock 9 + combine_layer 9 + tick_pipeline exit_feature_row 7 + position_risk_evaluator 1。工件：`docs/worklogs/2026-04-19-2--track_p_counterfactual_audit.md` + `/tmp/cf_audit_{grid,ma}_demo.json`。
- [x] **E5 ✅ 2026-04-19 22:33**：rebuild + 灰度部署（T1-T5 骨架隨 22:32 binary 活化；24h 無 fee 惡化觀察中）

**留尾**：`peak_reached_ts_ms` 欄位加到 `PaperPosition`（含 legacy migration）— Phase 1b 7 維累積後展開（未完成 → 保留在 TODO.md Phase 2 W25 排期）

---

## 7. P1-5 · DEMO-REBOOT-PNL-RESET-1 ✅ 2026-04-20（commit `7cda4e4`）

drawdown 跨重啟視角斷鏈修復。

**Root cause**：`peak_balance` 只活在記憶體 → 每次 engine restart 靜默重置 drawdown baseline；剛觸發 5% drawdown 的 session 重啟後看起來乾淨，繞過 fail-closed。

**修復（Option A + A2）**：`peak_balance` 持久化到 DB；restore-on-start 用 `max(restored, current)` clamp（live recovery 永不降低基準線）；僅 operator IPC 可顯式 reset（重啟不自動重設）。

**Rust**：`paper_state/checkpoint.rs`（load/write/delete）+ `PaperState::restore_checkpoint` clamp + `reset_drawdown_baseline` + event_consumer hot-path detached UPSERT + `PipelineCommand::ResetDrawdownBaseline` + ipc_server JSON-RPC method

**DB**：`V018__paper_state_checkpoint.sql`（trading.paper_state_checkpoint PK=engine_mode，非 hypertable，≤4 rows，CHECK engine_mode whitelist + peak_balance ≥ 0）

**Python**：`RiskViewClient.reset_drawdown_baseline` + `POST /api/v1/paper/risk/reset-drawdown-baseline`（Operator role gate + engine whitelist + ChangeType.STATE_CHANGE 審計 + IPC 失敗 HTTP 500 不 fake-success）

**Tests**：+9 Rust（engine lib 1629→1640）+ +4 client + +8 route（control_api_v1 2511 passed / 2 pre-existing DYNAMIC-RISK fails）

**Deploy**：V018 已 apply 到 trading_postgres；`restart_all.sh --rebuild` 完成（2026-04-20 00:11:43）；checkpoint writer 確認 live（demo row `peak_balance=948.85` 已寫入）

**Operator tool**：`helper_scripts/db/deploy_V018.sh`
**Worklog**：`docs/worklogs/2026-04-20--p1_5_a2_drawdown_continuity_implementation.md`

---

## 8. P1-15 · LEARNING-SCHEMA-QUALITY-1 ✅（commit `b0df1b3`）

ipc_close_symbol 前綴缺失 + estimator live_demo 不接受。

**背景更正（2026-04-18 實地查核）**：初審誤判 strategy_name cardinality 爆炸，經查 `realized_edge_stats._pair_round_trips`（`program_code/ml_training/realized_edge_stats.py:196`）在配對時用 **entry** fill 的 strategy_name，close fill 字串只參與 `is_exit` prefix 判斷（line 161-168 `startswith`），COST EDGE 動態字串**不會**產生分桶。

**104 cells 實際組成**：grid_trading 33 · ma_crossover 31 · funding_arb 12 · **ipc_close_symbol 18（現役 bug）** · **risk_check 10（歷史遺留，fix landed 2026-04-16 P0-4 R1，30d 窗口自然消化）**；實際異常僅 28 cells，非初報 ~80。

**Gap 1（現役）**：`rust/openclaw_engine/src/tick_pipeline/commands.rs:668` `strategy: "ipc_close_symbol".into()` 未依 EDGE-P2-1 規範加 `risk_close:` / `strategy_close:` 前綴 → ML pipeline `is_exit` 檢查（line 161-168）未命中 → 被誤歸類為 entry fill → 產生 18 個幻影 strategy cells。

**Gap 2（estimator）**：`program_code/ml_training/realized_edge_stats.py:238` validator `if engine_mode not in ("paper","demo","live")` 拒絕 `live_demo` → 2.23M LiveDemo 樣本無法進入估計。

**實測結果（2026-04-18 post-commit）**：E1 修復後跑 live_demo 7d 產出 28 乾淨 cells / `grand_mean_bps = -14.97`；但發現 **grand_mean 真實元兇非 phantom cells**——2 個尾端 outlier（`grid_trading::DOTUSDT raw=-152k bps` / `LINKUSDT raw=-67k bps`）佔 raw weighted grand_mean 主要權重，B=0.888 heavy shrinkage 再將所有 cells 拉向毒值。P1-15 清掉 28 phantom 對 grand_mean 僅移動 -2438→-2473 bps；真實解毒由 P1-16 + P1-17 落地。

---

## 9. P1-16 · HALT-SESSION-CROSS-SYMBOL-PRICE-CORRUPTION-1 ✅（commit `fef688e`）

Rust 上游 + Python 下游雙管修復。

**根因（RCA 2026-04-18 L1 confirmed）**：Rust halt_session force-close 路徑把 **ETHUSDT 的價格 $2357.94 蓋到其他 symbol 的 fill 記錄**（DOT/HIGH/IP/AAVEUSDT 同時間戳 `2026-04-18 19:09:56.302`，fill_ids `close-demo-{SYMBOL}-1776532196302`）。位置：`tick_pipeline/on_tick.rs:1480-1484` `.unwrap_or(event.last_price)` fallback——觸發 tick 的 symbol price 在 all_pos 迴圈中被蓋到所有缺 `latest_prices` 條目的其他 symbol。下游 pairer 忠實處理毒 fill：halt exit `qty=0.1` vs live FIFO entry `qty=51.7` → `matched_qty=0.1`，`entry_notional = 1.3384 × 0.1 = $0.13`，`−$235.66 / $0.13 × 10000 = −17,617,373 bps`。

**修復（雙管並行）**：
- **(1) 上游（Rust · 根因）**：`on_tick.rs` HaltSession arm 改用既有 `close_position_at_symbol_market` helper（與 ClosePosition 分支同款安全 pattern：per-symbol `paper_state.latest_price` → entry-price fallback）；移除 `.unwrap_or(event.last_price)` 洩漏點。+1 regression test `test_halt_session_uses_per_symbol_price_not_triggering_tick`（多 symbol halt 驗證 BTC 用自己 tick、ETH/DOGE 在無 latest 時 fallback 到 entry）。
- **(2) 下游（Python · safety net）**：`realized_edge_stats._pair_round_trips` 加 (a) price-jump gate：`|ln(exit/entry)| > 0.5` 直接 skip + 計數器 `_price_jump_skip_count`；(b) 分母托底：入隊時記 `qty_total`，bps 分母取 `max(full_entry_notional, match_notional)` 防止 partial match 微分母放大。保留 ±5000 bps Winsorize 作第三線。+5 新單測 + 2 既有 Winsorize boundary 測試重定位到 gate band 內。

**實測結果**：
- **archived demo corpus 6616 fills / 5129 round-trips**：**27 price-jump skips**（P1-16 指紋）/ **0 winsorize clamps** / `mean_net_pnl_bps = -9.02`（vs 修前 grand_mean=-2214，**245× 乾淨**）/ range `[-901, +1327]` bps 自然分布。
- **live_demo 7d**：0 skips / 0 clamps / grand_mean `-8.46` bps — gate 不誤傷合法資料。

**驗證**：engine lib **1499 passed / 0 failed**（+1 P1-16 upstream）· ml_training **238 passed / 13 skipped**（+5 gate tests）

---

## 10. P1-17 · JS-ESTIMATOR-WINSORIZATION-1 ✅

outlier clamp 落地。

**背景**：`program_code/ml_training/realized_edge_stats._pair_round_trips` 無 Winsorization，任何 raw_bps 無上限傳播到 JS shrinkage 的 grand_mean 計算。B=0.888 heavy shrinkage 把整個 snapshot 拉向毒值。

**實作**：
1. 模組常數 `_WINSORIZE_BPS = 5000.0`（E1 自動提升 — `risk_config_demo.toml stop_loss_max_pct=25%` 下原建議 ±1000 bps 會截掉合法大額止損）+ 雙語注釋
2. `_winsorize_bps()` helper + 模組級 clamp counter（`get_winsorize_clamp_count()` / `_reset_winsorize_counter()` API）
3. `_pair_round_trips` RoundTripRecord 構造時對 `gross_pnl_bps`/`net_pnl_bps` 套用，clamp 觸發 WARNING log
4. 新測試檔 `tests/test_winsorize.py` 8 cases：`constant_is_5000_bps` / `normal_passes_through` / `extreme_negative_clamps` / `extreme_positive_clamps` / `boundary_negative` / `boundary_positive` / `zero_passes_through` / `gross_inside_net_outside`

**實測結果**：
- demo 30d（archived to `demo_archive_20260418`）: grand_mean **-2213.98 → -78.38 bps**，19 clamps fired（1 個數量級改善進入 fee-drag 範圍）
- live_demo 7d: grand_mean 保持 **-14.97 bps**，0 clamps（預期，7d 無 outlier）
- 順帶暴露 P1-16：E1 跑時發現 `grid_trading::HIGHUSDT gross=-49,479,767 bps`（不可能值）及 LINKUSDT 幾何級數 -6,778 → -1,734,596 bps → B RCA 確認為 halt_session cross-symbol price corruption

**驗證**：`ml_training/tests/` 全套 217 passed / 2 skipped / 0 failed

---

## 11. DYNAMIC-RISK-STATUS-TEST-SIG-1 ✅ 2026-04-19（commit `83a0475`）

已修復 — 採方案 (a) `TestClient(app).get(...)` 走 HTTP dispatch，並傳 `Authorization: Bearer` header 因為兄弟測試 `importlib.reload(main_legacy)` 會 swap 掉預先捕獲的 `current_actor` dep key。2 tests pass · pytest baseline 2587+2→2589+0。

---

## 12. E5-FN-2 ai_budget request_id dedup（Plan N 重設計）✅ 2026-04-19（commit `f0f11c0`）

**背景**：原 V018 partial UNIQUE 設計（`fd480ba`）失敗 — TimescaleDB hypertable 要求 UNIQUE index 必須含 partitioning column `time`（empirical error `cannot create a unique index without the column "time"`），直接 `revert 87b7653` 重設計。

**Plan N 方案**：改用**既有 hypertable PK `(time, scope, request_id)`** 做 `ON CONFLICT DO NOTHING RETURNING 1`（零 schema 改動、零 migration）：
1. `make_request_id(scope) -> (String, i64)` 回 `(rid, ts_ms)` tuple — caller 重試**必須**傳同 tuple
2. `usage_io::insert_usage` 新 `event_time_ms: i64` 參數 + bind `$1::timestamptz` + `RETURNING 1` → `Ok(bool)`（`false`=dedup）
3. `tracker::record_usage` 新 `event_time_ms` 參數 + `if inserted` 才累進 MTD cache
4. `claude_teacher/mod.rs` 改用 `make_request_id("teacher")` tuple
5. IPC `handle_record_ai_usage` 收 Python 傳入 `(request_id, event_time_ms)` 或本地鑄造 — 封閉 `fd480ba` 原本會引入的 `"py-sync"` literal PK 碰撞（所有 Python caller 共用同 id 會全被 PK 折疊掉）

+4 Plan N 測試（format / 同 ms 唯一 / cold-start cache 累進 / distinct tuples 分別累進）；engine lib 1567→**1571**；**部署無約束**：直接 `restart_all.sh --rebuild`。

**Follow-up 留存於 TODO §E5-FN-2-PLAN-N-FUP**：Python Layer-2 sync caller 可選升級傳入 `(request_id, event_time_ms)` 以獲得跨重試真實去重；部署後 DB 唯一性 assertion SQL。

---

## 13. E5-FN-3-FUP · 4-Agent audit_callback wiring ✅ 2026-04-19

**起源**：E5-FN-3 commit `19f3d85`（2026-04-19）只接了 AnalystAgent pilot；另 4 agent 留給 follow-up

**動因**：違反 Root Principle #8「交易可解釋」— Scout/Strategist/Guardian/Executor 決策點共 **13** 個 `_audit()` call-site 原本 silently no-op

**實施模式**（每 agent 照 Analyst pilot 抄）：
```python
_GOV_HUB_FOR_<AGENT> = _governance_hub_resolver()
_<AGENT>_AUDIT_CB   = make_agent_audit_callback(_GOV_HUB_FOR_<AGENT>, "<Agent>Agent")
<Agent>Agent(..., audit_callback=_<AGENT>_AUDIT_CB)
```

**4 sub-tasks**：
- [x] **FUP-a Strategist** ✅ 2026-04-19：wire at `strategy_wiring.py:~172` + `_GOV_HUB_FOR_STRATEGIST` try-import + `_STRATEGIST_AUDIT_CB = make_agent_audit_callback(..., "StrategistAgent")`；new `test_strategist_audit_wiring.py` 2 tests 全綠（ctor + directive_received → STATE_CHANGE row）。StrategistAgent code **零變更**（已於 line 134 接受 `audit_callback` kwarg）。
- [x] **FUP-b Guardian** ✅ 2026-04-19：wire at `strategy_wiring.py:~215`（`_GOV_HUB_FOR_GUARDIAN` 既存，補登記）；new `test_guardian_audit_wiring.py` 6 tests 全綠（ctor × 2 + verdict emit + directive state_change + fail-open × 2）。GuardianAgent code **零變更**。
- [x] **FUP-c Executor** ✅ 2026-04-19：wire at `strategy_wiring.py:~369`（try 塊內，`_GOV_HUB_FOR_EXECUTOR` 既存）；new `test_executor_audit_wiring.py` 3 tests 全綠（ctor × 2 + directive_received emit）。ExecutorAgent code **零變更**。
- [x] **FUP-d Scout** ✅ 2026-04-19：`multi_agent_framework.py` ctor 改為接受 keyword-only `audit_callback` kwarg（positional `(config, message_bus)` 保留）；`produce_intel()` / `produce_event_alert()` 各新增 `self._audit(...)` call-site（bus 路由**之前**）；wire at `strategy_wiring.py:~114` + `_GOV_HUB_FOR_SCOUT` + `_SCOUT_AUDIT_CB`；new `test_scout_audit_wiring.py` 8 tests 全綠（ctor × 3 + produce_intel × 2 + produce_event_alert × 1 + fail-open × 2）。

**E2 APPROVE_WITH_NITS 非阻塞遺留（已全清）**：
- [x] **NIT-1 log throttle** ✅ 2026-04-19（Option C DEBUG 常開 + WARNING 60s 節流）：`agent_audit_bridge.py` 新 `_WARN_THROTTLE_SECONDS=60.0` + `_LAST_WARN_AT` dict keyed by `(role_name, event_class)` via `time.monotonic()`；DEBUG 總是發、WARNING 每桶 60s 一條；DB 死時刷屏問題解決。測試用 `_reset_warn_throttle()` 清狀態（未加入 `__all__`）。
- [x] **NIT-2 test 覆蓋缺口** ✅ 2026-04-19：新 `test_unknown_event_type_defaults_to_parameter_change`（event_type `"opaque_event_xyz"` 不匹配任何 keyword → `PARAMETER_CHANGE` 保守默認）；bridge test 12 → 13。
- [x] **NIT-3 thread-safety 文檔** ✅ 2026-04-19：`make_agent_audit_callback` docstring 新增中英對照 Thread-safety 段，涵蓋 (a) 跨 thread 調用安全 (b) `ChangeAuditLog._lock = threading.RLock()` 驗證（change_audit_log.py:156 + record_change:188）(c) fail-open 防 partial-write (d) `_LAST_WARN_AT` race-tolerant 設計說明。

**驗收**：全 5 agent（Scout/Strategist/Guardian/Analyst/Executor）wire 完成後，`change_audit_log` 表應看到 `who IN ('ScoutAgent','StrategistAgent','GuardianAgent','AnalystAgent','ExecutorAgent')` 全部出現；搭配 Analyst pilot 觀察週（uvicorn 重啟後）做對比

**前置閱讀（給未來 session）**：
- Commit `19f3d85` 的 `git show` — 完整 RCA + 實施模式
- `docs/CLAUDE_CHANGELOG.md` §「E5-FN-3 — agent_audit_bridge + AnalystAgent pilot wiring」
- `docs/audits/2026-04-18--e5_full_codebase_audit.md` §七.7.3
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py`（stateless 工廠 — 不需改動，只需調用）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:249,339`（AnalystAgent pilot 兩 call site，template 參考）
- `CLAUDE.md §九`（singleton 登記表，每新增 `_*_AUDIT_CB` 必須登記）
- CLAUDE.md §二 Root Principle #8

**測試模板**：參照 `program_code/.../tests/test_agent_audit_bridge.py`（13 tests）；每新 agent wiring 加 1 integration test 驗 `audit_callback` 被 ctor 收下 + 至少 1 path 觸發 `record_change`

---

## 14. WATCHDOG-DNS-CLASSIFY-1 ✅ 2026-04-20

區分 DNS 斷線 vs 真 crash。

**狀態**：已實作 `helper_scripts/canary/engine_watchdog.py` — 新 `classify_engine_failure(log_path)` + `on_engine_crash(log_path=...)` 可選參數；P0-9 停電樣本驗證正確分類 `network_outage`

**行為**：tail 20 行內連續 ≥5 條 `Temporary failure in name resolution` / `HTTP transport error` / `connection refused` / `failed to lookup address information` / `dns error` → `network_outage`（不計 strike、不觸發 auto-restart 以免 circuit-breaker 被無辜燒穿、engine_alive=False 讓 recovery 正常觸發）；tail 出現 `panic` / `assertion failed` / `stack backtrace` → 強制 `engine_crash` 正常計 strike；缺檔或空檔保守預設 `engine_crash`

**測試**：+16 unit tests（10 classifier + 6 on_engine_crash wiring）；pytest helper_scripts/canary/test_canary.py 38→**54 passed**

**工作量**：~2h（純 Python，不動 Rust；Rust engine 計數器無變動）

---

## 歸檔總結

- **測試累計增量**：Rust engine lib +133（~1498 → 1631）+ Python +54（canary）+ +13 (bridge) + +19（bridge wiring tests a/b/c/d） + +9（E5-FN-3 pilot）+ ml_training +5 (P1-16) + 8 (P1-17)
- **Commits 連鎖**：`65acde6` · `6ea643e` · `c7171b2` · `35808e9` · `2a36a3f` · `23b14ef` · `88b4ef9` · `c7d6a6c` · `981840f` · `a963f0b` · `094d285` · `4feb17a` · `7cda4e4` · `b0df1b3` · `fef688e` · `f0f11c0` · `83a0475` · `19f3d85`
- **TODO.md 壓縮**：本批次歸檔後 TODO.md 從 629 行預計降至 ~330 行（~48% 縮減）
