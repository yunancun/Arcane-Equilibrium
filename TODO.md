# OpenClaw TODO — 工作清單

**最後更新**：2026-04-19 23:40（E5-FN-3 loop closure — FUP-d Scout wiring + NIT-1/2/3 非阻塞 cleanup 並行 sub-agent 完成 · 5/5 agent 全綠 + log throttle + 默認分支 test + thread-safety 文檔）
**Engine**：PID 3029633 · binary mtime 2026-04-19 22:32 → 含全部先前 staged 修復（P0-6 永久修復 + P1-7 A INTENT-WRITE-GAP-1 + P1-7 B edge_estimator scheduler + P1-17 Winsorize + LIVE-GATE-BINDING-1 + DYNAMIC-RISK-1 + IPC-SCAN-1c + FILL-CONTEXT-LINKAGE-1 + EXIT-FEATURES-TABLE-1 Phase 1b + Plan N ai_budget dedup + E5-P1/P2 + E5-FN-2/3 + DISPATCH-RETRY-1 + MARKET-KLINES-STALE-1 + DUAL-TRACK Track P T1-T5 骨架 + PIPELINE-SLOT-1 Phase 1-4）+ **EXIT-FEATURES-TABLE-1 Phase 1b GAP-1**（commit `35808e9` apply_confirmed_fill 接線，待流量驗證）
**Python uvicorn**：PID 3029688（4 workers）· started 2026-04-19 22:33 → 含 P0-12 LIVE-GATE-FALLBACK-1 + E5-FN-3 AnalystAgent pilot + PIPELINE-SLOT-1 Phase 4 daemon-thread trigger
**PIPELINE-SLOT-1 live 驗證**：LiveAuthWatcher 22:33 啟動 `env=LiveDemo poll_interval_secs=5`；authorization.json 已由 Manual restart sentinel 清除；等 operator 走 GUI renew → 應 ≤1s 觀察到 Live pipeline 重生
**測試基準線**：Rust engine lib **1631** / bin 38 / core 392 / e2e 35 / reconciler_e2e 19 · Python **2866** passed（+9 E5-FN-3 + 2 DYNAMIC-RISK-STATUS-TEST-SIG-1 修復 83a0475 + 16 WATCHDOG-DNS-CLASSIFY-1 新測）+ audit 4 passed / ml_training 238 passed · **0 pre-existing fail**（DYNAMIC-RISK 已清）
**健康**：demo alive（snapshot age 5.9s） · paper/live 預期 dead（PAPER-DISABLE-1 + 待 renew） · 今日 1 crash（12:25，為 redeploy 前殘留）
**DB 驗證（2026-04-20 00:20）**：market.klines 5 timeframes 在近 1h 寫入 ✅ · trading.intents demo 57 rows/3h ✅（P1-7 A 生效）· **learning.exit_features GAP-1 驗收 ✅ 1.8h 提前結案**（demo 8 close fills / 8 exit_features / coverage_ratio=1.000 / Strategy 6 + FastTrack 2）

> 本文件僅列「待辦/進行中」。已完成 → 文末歸檔索引。詳細設計 → `docs/worklogs/`。
> Compact 後從此文件恢復；第一個 `[ ]` = 起點。CLAUDE.md §三 = 當前狀態快照。
> 條目分級：**P0 阻塞 Live Gate** → **P1 當週活躍** → **P2 下週/Live Gate/QoL** → **P3 長期** → **P4 backlog/條件性**

---

## 🎯 接手三連檢查

```bash
# 1. 引擎存活 + canary + 崩潰數
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status
grep -c "ENGINE_CRASH" /tmp/openclaw/watchdog.log 2>/dev/null || echo "0 crashes"

# 2. git 狀態
git status && git log --oneline -5

# 3. 引擎掛了 → bash helper_scripts/restart_all.sh --engine-only --rebuild
```

---

## 🔴 P0 — 阻塞 Live Gate 關鍵路徑

### P0-2 · LG-1 Demo 21d 觀察期 🕰️
- **起算**：當前 PID 2217378（2026-04-18 20:13 local）
- **解鎖**：≥21d 零事故 + LG-2/3 + provider pricing 正式化
- **語義**：PAPER-DISABLE-1 後 paper 預設不 spawn，LG-1 改以 demo 為觀察基準（Bybit testnet 真 API，價值高於 paper 合成 fill）
- **預估**：3 週連續觀察 → 最早 Live W24 末（~2026-05-23）

### P0-3 · Phase 5 策略 Edge 2w 重評 📊
- **狀態**：推遲到 DUAL-TRACK-EXIT-1 Track P 上線 + P1-10 結構修復後才能乾淨重評
- **理由**：當前 24h audit（demo grid net −$43.36 / ma_crossover −$11.90）大概率仍負 → 需先辨別「策略本身沒 edge」vs「退場規則丟微利造成假負 edge」
- **判斷**：gross edge 翻正 → cost_gate 重啟（JS/DL/cost_gate 機械已接線）；仍負 → 策略重做或 EDGE-P3-1/EDGE-P2 接管

---

## 🎯 DUAL-TRACK-EXIT-1 — 主軸（W23-W27+，supersedes P1-9）

> 物理層最優 + ML 持續優化雙軌退場。Track P = 7 維度啟發式（可解釋下界）；Track L = per-strategy ML exit policy（同特徵集監督學習上界）；Combine Layer = 系統永遠 ≥ Track P。
> **設計日誌**（完整論證/架構/QA 守衛/風險退路 §十 7 項）：`docs/worklogs/2026-04-18--dual_track_exit_design.md`

### Step 0 · W23 Day 1-3 可行性 Sprint ✅（2026-04-18，2/4 綠 + 1/4 黃 + 1/4 紅 → Phase 1 拆 1a/1b）

- [x] **不確定 1 ✅ 綠（機制）**：estimator CLI 跑通 104 cells / demo grand_mean −2214 bps（**P1-15 查明為 28 phantom cells 污染，b0df1b3 修復**；live_demo 7d 乾淨值 −14.97 bps ≈ fee-neutral）；**不可 bind**（P1-14 bind blocker 獨立）
- [x] **不確定 2 🔴 紅**：`decision_features` 是 entry-time snapshot，7 維對齊僅 **1/7 直接**（`atr_pct`）+ 1/7 部分（`persistence_elapsed_ms ≈ entry_age_secs`）；`trading.decision_outcomes.max_favorable/max_adverse` 113k 全 NULL（dead column）；需新建 `learning.exit_features` + Rust exit handler 寫入
- [x] **不確定 3 ✅ 綠**：ma_crossover live_demo **2.23M** / grid_trading live_demo **16.5k**；小樣本（bb_breakout 0 / funding_arb 60 / bb_reversion 609 / grid demo 1.7k / ma_crossover demo 693）強制 P-only
- [x] **不確定 4 🟡 黃**：無 tick 表；kline 1-min 粒度；**且 `market.klines` 自 2026-04-16 21:08 停寫**（停電後管線未恢復，新增 `MARKET-KLINES-STALE-1`）→ fallback #6 事後歸因 audit
- [x] Sprint 產出：`docs/worklogs/2026-04-18-1--dual_track_exit_feasibility.md`

**Step 0 判決**：**NO-GO 原計畫全量 Phase 1**。改拆 Phase 1a（可立即）/ Phase 1b（7 維需累積）。Phase 2 shadow 原 W24 → **實際延後到 W25**。

### 🔴 Step 0 衍生新 TODO 項（Phase 1 前置）

- [x] **MARKET-KLINES-STALE-1**（P1-CRITICAL · 2026-04-18 RCA ✅ · 2026-04-18 修復 commit `65acde6`）：**Root cause = PAPER-DISABLE-1 架構遺漏**（非停電事件）。`main.rs` Paper pipeline `market_data_tx: Some(market_tx)`，但 Demo 和 Live 都 `market_data_tx: None`（D19 註釋：`Paper handles that`）→ `on_tick.rs::emit_market_data_if_needed` `if let Some(ref tx)` None check 跳過 → `MarketDataMsg::KlineClose` 零發出 → `market_writer` task 起來但 channel 永遠空。Paper 自 PAPER-DISABLE-1（2026-04-16 21:08 最後一次 tick）預設不 spawn 後，DB kline 寫入完全斷。**修復**（commit `65acde6`，三處 `Some(market_tx.clone())`）：paper/demo/live 三引擎皆 clone market_tx → 三路並行寫入；`market.klines` PK `(symbol, timeframe, ts)` + `ON CONFLICT DO NOTHING`（`market_writer.rs:180`）已 dedup，多 producer 安全。**部署**：待 `restart_all.sh --rebuild`（與 bd45e90 / c7171b2 / E5-P1/P2 同批）。
- [x] **EXIT-FEATURES-TABLE-1**（P1-HIGH · 2026-04-18 設計草稿 ✅ · 2026-04-19 Phase 1b 全部接線 ✅ · 2026-04-19 Phase 1b GAP-1 修復 ✅）：`docs/worklogs/2026-04-18-2--exit_features_table_design.md`。Phase 1b producer wiring（commit `6ea643e`）覆蓋 `emit_close_fill` 主路徑；Phase 1b FUP（commit `c7171b2`）補完 2 個漏接 close paths（`process_external_fill` IPC 外部 fill 報告 + `ipc_close_symbol` paper 分支：operator `/close_symbol` API + dust eviction + orphan_handler→Paper 模式）；抽出 `try_emit_exit_feature_row` `pub(crate)` helper；+3 tests / 5 pre-existing WIP `test_exit_feature_row_*` 全綠化。Track P 標籤覆蓋完整。
    - **Phase 1b GAP-1（2026-04-19 修復 commit `35808e9`，2026-04-19 22:32 部署上線）**：R1 觀察窗發現 demo 重啟後 89 fills 但僅 2 rows `learning.exit_features`（~97% 丟失）；並行 root-cause 審查鎖定 **`apply_confirmed_fill`（Demo/Live WS 確認成交平倉主路徑，commands.rs:421）從未呼叫 `try_emit_exit_feature_row`**。PAPER-DISABLE-1 前 paper 的 `emit_close_fill` 接線還 cover 得到；paper 關閉後 Demo/Live 靠 WS 回報走 `apply_confirmed_fill`，2 rows 是少數走 `process_external_fill` / `ipc_close_symbol` paper 分支的剩餘路徑。修復：`commands.rs:442-566` 在 `apply_fill` 之前捕獲 `pre_close_snapshot`，在 `trading_tx.Fill` 送出後 `if realized_pnl != 0.0` 呼叫 `try_emit_exit_feature_row`（pattern 與 `process_external_fill` 對齊，`entry_context_id` 沿用 pre-close 捕獲的 `existing_entry_ctx`）。+2 regression tests（`apply_confirmed_fill_emits_exit_feature_row_on_close` 驗 demo 平倉送出 row with engine_mode=demo / side=1 / realized_net_bps>0 / peak_pnl_pct≈2% · `apply_confirmed_fill_exit_feature_fail_soft_when_tx_missing` 驗 tx 缺失時 Fill 仍正常送出）。engine lib 1629→**1631** passed。**影響**：修前若不補，DUAL-TRACK Phase 1b W24 7 維閾值校準會嚴重缺料（daily exit_features 增量 ~3%→100%）；Track P T4 wiring 未來上線亦受益。
    - [x] **GAP-1 R1 follow-up 驗收 ✅ 2026-04-20 00:20 local（deploy+1.8h early snapshot，樣本 ≥5 達標提前結案）**：demo 窗口 `ts > 2026-04-19 22:32:57+02` 至 00:20 內 8 close fills / 8 exit_features rows → **coverage_ratio = 1.000**（遠 > 0.95 閾值）。Exit sources 分布合理：Strategy 6 + FastTrack 2。Trigger rules：`ma_reverse_cross` 5 · `fast_track_reduce_half` 2 · `grid_close_long` 1。3 close paths 全接線驗證：`emit_close_fill` (ma/grid) + `apply_confirmed_fill` demo WS-confirmed（GAP-1 主目標接線） + risk fast_track。LiveDemo 0 close fills（預期：authorization.json 未簽，pipeline 未 spawn）。**不需等 10:30 正式窗口**——樣本 ≥5 且 coverage = 100% 已滿足全部驗收準則。**若未來 Track P T4 PHYS-LOCK 接線**：屆時新增 `Physical` exit_source，需重跑驗收 SQL 確認不漏接（當前樣本全 Strategy/FastTrack，不覆蓋 Physical path）。

        ```sql
        -- R1 GAP-1 12h follow-up：目標 coverage_ratio ≥ 0.95
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

        -- 分 owner_strategy 看 exit kind 分布（方便排查漏接 path）
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

        -- exit_source 分布（若 Track P T4 wiring 上線，Physical 會出現）
        SELECT exit_source, COUNT(*)
        FROM learning.exit_features
        WHERE engine_mode='demo' AND ts > '2026-04-19 22:32:57+02'
        GROUP BY 1 ORDER BY 2 DESC;
        ```

        **驗收準則**：
        - ✅ `coverage_ratio ≥ 0.95` → GAP-1 修復生效，勾掉此 follow-up、task #6 關閉
        - ⚠️ `0.80 ≤ coverage_ratio < 0.95` → 找剩餘漏接 path；對照 exit_source / owner_strategy 分布定位
        - ❌ `coverage_ratio < 0.80` → 修復未生效或有更大架構遺漏，reopen RCA + 檢查 binary mtime 是否為 22:32:57

        **其他觀察指標**（同一 window 跑）：
        - 12h 內 demo close fill 數應 ≥ 5（驗證 demo 真的在交易）
        - R:R 不對稱：`AVG(realized_pnl WHERE pnl>0)` vs `AVG(ABS(realized_pnl) WHERE pnl<0)` 比值 → 看 P1-10 路徑是否自然收斂
        - 若 close fill 數 < 3，延長觀察到 24h 後再判

    - Phase 1b 累積 ≥1 週 exit_features 後可校準 7 維閾值（見 Phase 1b §83）。
- [ ] **DECISION-OUTCOMES-DEAD-1**（P2）：`trading.decision_outcomes` 113k 條 `max_favorable/max_adverse` 全 NULL，寫入管線斷；可沿用此表取代 exit_features 或確認徹底 dead；RCA 決定方向。

### Phase 1a · W23 Day 4-7（Step 0 後立即啟動，不阻於 7 維）

**軌道 2 P1-7 解阻塞（完全不阻塞，優先推進）**：
- [x] **A ✅ 2026-04-18 commit 2a36a3f · 2026-04-19 部署+實測驗證**：Rust 接 `trading.intents` 持久化。RCA：DEDUP-PY-RUST 後 exchange 分支結構性缺 `persist_intent` 呼叫（Paper 走 `process_with_features` → `IntentResult{submitted}`，Demo/Live 走 `process_gates_only_with_features` → `ExchangeGateResult` 不含 submitted；on_tick.rs:986 `if result.submitted` guard 對 exchange 分支結構不可達）；`persist_verdict` 在 837 unconditional 而 `persist_intent` 完全沒呼叫 → 7d × 三窗口 `trading.intents` live/live_demo = 0 vs Approved verdicts 4.9M。修復：on_tick.rs:879-902 在 exchange 分支 `if gate.approved` 內補上 `persist_intent(em, ts_ms, intent, final_qty, last_price, em)` + `stats.total_intents += 1`。+1 單測 + cargo test 1498/0。**驗收**：binary mtime 2026-04-18 23:54 含 fix；engine PID 2390582 啟動 ~31 min 內 demo 側 **29 intents / 32 Approved verdicts = 90.6% ratio** ✅（DB 查核 2026-04-19 00:27 local）；29 intents 與 engine 內部 `total_intents=29` 完全吻合 → fix 走到預期 code path。live_demo 驗證 **pending**（operator 修 T0 bypass bug 後 pipeline 已關，需重啟並簽新 `authorization.json` 才能觀察首個 Approved→intent 形成；非 P0-6 本身問題）。
- [x] **B ✅ 2026-04-19 commit 23b14ef**：`edge_estimator_scheduler.py` daemon thread 每小時跑 demo + live_demo 模式 JS estimator 寫入 `settings/edge_estimates*.json`；`edge_estimator_routes.py` 提供 `POST /api/v1/edge-estimator/trigger` (Operator-only) + `GET /api/v1/edge-estimator/status`；main.py startup hook fail-open。**手動觸發驗證**：live_demo n_cells=28 grand_mean **−8.46 bps**（自 −14.97 改善）；demo n_cells=0（P1-15 phantom 清空 + 死循環未產真 edge）。**僅寫檔，未 bind cost_gate**（待 P1-16 修 + grand_mean>−50 bps + ≥2 策略 shrunk_bps>0）。同 commit 含 D19 assertion 移除（event_consumer/mod.rs:92 防 PAPER-DISABLE-1+MARKET-KLINES-STALE-1 後 panic）。
- [ ] **C** `run_training_pipeline.py` 首跑 grid_trading（用 decision_features 17 維做 entry-decision 模型，不等 exit_features）→ 產 `models/demo/grid_trading_entry_policy_v20260425.onnx`
  - **2026-04-19 結構性阻塞已解除**：原 RCA — `learning.decision_features` 3.36M rows 與 `trading.fills.entry_context_id` 3514 rows JOIN **0 overlap**，`edge_label_backfill.py` 找不到任何可標籤的 fills；root cause = decision_features.context_id 訊號時刻用 `event.ts_ms`，exchange-confirmed fill 用 WS `exec_ts`（漂移 100-500ms），同 `make_context_id(em,sym,ts_ms)` formula 不同 ts_ms → 不同字串。**FILL-CONTEXT-LINKAGE-1（commit `bd45e90`）已修**：訊號時刻 context_id 端到端傳遞（`OrderDispatchRequest.context_id` + `PendingOrder.context_id` 新欄位 → `apply_confirmed_fill(...,signal_context_id:&str,...)` 新參數）；3 close-dispatch sites 帶 `paper_state.get_entry_context_id(symbol)`；+2 regression tests（`apply_confirmed_fill_preserves_signal_context_id` 斷言訊號 id 寫入 + `_falls_back_when_signal_id_empty`）；engine lib 1560→1564 passed。
  - **2026-04-19 晚間進度（收尾準備）**：
    - ✅ (1) 部署完成 — binary mtime 22:32（bd45e90 on PID 3029633）
    - ✅ (3) 首次成功 backfill — `demo` 130 labels（grid 88 / ma_crossover 42）+ `live_demo` 8 labels（grid 4 + ma 2 + 其他 2）；`edge_label_backfill.py` 擴展接受 `live_demo`（原僅 paper/demo/live）
    - ✅ ML 依賴全裝 — `/home/ncyu/.venv` 新增 lightgbm 4.6 / onnx 1.21 / onnxmltools 1.16 / skl2onnx 1.20 / onnxruntime 1.24 / scikit-learn 1.8 / pyarrow 23 / shap 0.51 / duckdb 1.5 等 12 套；`requirements-ml.txt` 補登 `onnxmltools` + `skl2onnx`
    - ✅ pipeline 工具鏈 smoke test 通過 — `--dry-run --strategy grid_trading --engine-mode demo --use-quantile-predictor` 全 6 stages（etl→labels→quantile_train→cqr_calibration→acceptance_report→onnx_export）綠；產出三 ONNX artifact（q10/q50/q90）+ `_current` symlinks + acceptance report 於 `/tmp/openclaw/models/`
    - ✅ 自動化接線 — `edge_estimator_scheduler.py::_run_cycle` 每小時先跑 `backfill_labels(mode)` 再跑 JS；backfill/JS 任一失敗 fail-open 不阻斷另一條；live_demo 首 8 labels 即由此路徑寫入
    - ✅ 就緒監控 — `helper_scripts/db/phase1a_c_readiness.py` 輸出逐 (engine_mode × strategy × symbol) 已 labeled 數 + 24h 速率 + 到 200 的 ETA；**目前最大切片 `demo grid_trading BLURUSDT` 47 labels，ETA ≈78h**（24h 速率外推，不含 MICRO-PROFIT 改動影響）
  - **剩餘阻塞（唯一）**：資料量 — 最大 (strategy × symbol) slice 47/200；預期 ~3-5 天自然累積過 200（demo grid BLURUSDT 最先達標）。不含 LiveDemo 追料（`authorization.json` 未簽，LiveDemo pipeline 拒啟，無新 fills）
  - **下一步**：(5) 等 `phase1a_c_readiness.py` 出現 `Slices already ≥200: 1` 再跑 `run_training_pipeline.py --strategy grid_trading --symbol BLURUSDT --engine-mode demo --use-quantile-predictor` 產首個有意義 ONNX；(6) operator 按需重簽 `authorization.json` 讓 live_demo 也開始累料

**軌道 1 Track P 物理層骨架（MARKET-KLINES-STALE-1 修完後）** ✅ 2026-04-19：
- [x] T1 `ExitFeatures` + `PhysicalDecision` 型別（commit `88b4ef9`；T1-FIX `c7d6a6c` 補 `Serialize`/`Deserialize` + 3 邊界測試）
- [x] T2 `price_tracker` 加 `compute_roc` + 3 邊界測試（commit `981840f`）
- [x] T3 `physical_micro_profit_lock` + `PhysLockConfig` Priority 6 替換 COST EDGE（commit `a963f0b`，reason 字串 `risk_close:phys_lock_<gate>`）
- [x] T4 Combine Layer 骨架 + `ExitSource` 4 tags（commit `094d285`；T4-FIX `c7d6a6c` 修 on_tick wrapper prefix `PHYS-LOCK` → `risk_close:phys_lock_` + `strip_phys_lock_prefix` 剝殼 + `assert_eq!` 升 release 不可繞 + integration test 覆蓋 3 gate）
- [x] T5 counterfactual exit audit CLI `program_code/audit/counterfactual_exit_audit.py`（commit `4feb17a`，1-min kline 粒度事後歸因，`MARKET-KLINES-STALE-1` 修復後可跑）
- [ ] `peak_reached_ts_ms` 欄位加到 `PaperPosition`（含 legacy migration）— Phase 1b 7 維累積後展開
- [x] **E2 + E4 ✅ 2026-04-19 22:48**：counterfactual 粗粒度 audit + ≥47 單測（≥18 要求超達）。CLI `counterfactual_exit_audit.py` 實跑驗證：grid_trading demo 7d 141 positions / 4 hits / mean delta −39.4 bps（1 better / 2 worse / 1 neutral）· ma_crossover demo 7d 52 positions / 10 hits / mean delta −95.2 bps（5 better / 5 worse）。ENJUSDT 案例砍掉 198 bps 潛在收益 → 驗證 Phase 1a 骨架閾值「設計上保守」，校準工作正確排入 Phase 1b。單測分布：exit_features 6 + exit_feature_schema 3 + compute_roc 12 + phys_lock 9 + combine_layer 9 + tick_pipeline exit_feature_row 7 + position_risk_evaluator 1。工件：`docs/worklogs/2026-04-19-2--track_p_counterfactual_audit.md` + `/tmp/cf_audit_{grid,ma}_demo.json`。
- [x] **E5 ✅ 2026-04-19 22:33**：rebuild + 灰度部署（T1-T5 骨架隨 22:32 binary 活化；24h 無 fee 惡化觀察中）

**Phase 1a 完成標準**：P1-7 A/B/C 部署 + `edge_estimates.json` 每小時自動刷新 + `trading.intents` live/live_demo 開始有 rows + 第一個 ONNX artifact + Track P 骨架灰度 ≥48h `exit_source=Physical` 正常

### Phase 1b · W24（exit_features 累積）

- [ ] `learning.exit_features` 表建立 + Rust exit handler 寫入
- [ ] 累積 ≥1 週 exit_features 資料（W24 全週）
- [ ] 7 維度規則 bind 真實閾值（取代 Phase 1a 骨架預設）

**Phase 1b 完成標準**：≥2 策略 exit_features 累積 ≥1000 rows + 7 維閾值可由資料 calibrate

### Phase 2 · W25（原 W24，延後 1 週）— Track L shadow + P1-10 並行

**軌道 1 Track P 物理層**：
- [ ] `peak_reached_ts_ms` 欄位加到 `PaperPosition`（含 legacy migration）
- [ ] `price_tracker` 加 `compute_roc(symbol, lookback_ms)`
- [ ] 7 維度規則 in `risk_checks.rs`（Priority 6 替換現有 COST EDGE，重命名 `PHYS-LOCK`）+ ConfigStore hot-reload
- [ ] Combine Layer 骨架（Track L 缺失時等同 P-only）
- [ ] E2 + E4：counterfactual replay audit（demo 7d）+ ≥18 單測（spike-wick 不誤觸 / 長期 winner 不誤砍 / 波動率歸一化邊界 / hot-reload / 早期寬容 / ML 缺席退化）
- [ ] E5：rebuild + 灰度部署（保守閾值，24h 無 fee 惡化才收緊）

- [ ] Combine Layer 啟用 `ml_override_high=2.0`（不可達），只寫 `learning.decision_shadow_fills`
- [ ] 每日對比 P vs L 一致性（target ≥60%）→ 校準 `ml_confirm_threshold / ml_override_high / ml_veto_low`
- [ ] 每筆 `trading.fills` 寫入 `exit_source` 欄位（Physical / Hybrid-shadow / ML-shadow）
- [ ] **並行 P1-10** grid 過度交易 + ma_crossover R:R 不對稱（比 ML 重要 5 倍）

**完成標準**：shadow 一致性 ≥60% + P1-10 fee 佔比 <50% + 不對稱倍數 ≤1.5×

### Phase 3 · W26-W27（原 W25-W26，連帶延後）— Track L 灰度開啟

- [ ] `ml_override_high` 0.95 → 0.85 → 0.75（每階 1-2 週，需 Hybrid net edge 顯著 > P-only, p<0.1, n≥200 才下調）
- [ ] Hold-out control 5-10% 永跑 P-only（feedback bias 對照）

**完成標準**：`ml_override_high=0.75` 穩定 ≥1 週 + 累積 net edge 正向

### Phase 4 · W28+（原 W27+，連帶延後）— 持續優化常態

- [ ] 週 retraining cron + model registry + canary deployment
- [ ] 月 CPCV 驗證 + drift 檢測
- [ ] 整合 G-7 Teacher / Symbol Embedding / Regime LSTM

### QA 守衛（避免 ML 變賭博）

- [ ] 每策略樣本 < 1000 → 永遠 P-only（bb_breakout 首當其衝）
- [ ] 嚴禁 random split（CPCV 時序）
- [ ] Hold-out 5-10% 永不受 ML 影響
- [ ] 每日 Brier score 超閾值自動降級
- [ ] Feature drift 7 維度每日對 baseline > 2σ 報警
- [ ] IPC 一條命令 `ml_override_high=2.0` rollback

### 🔗 與其他 TODO 的依賴/去重關係

| TODO | 關係 | 分工 |
|---|---|---|
| **P1-9 原案** | 完全取代 | Supersedes，原 P1-9 已從 active 移除 |
| **P1-4 首個 ONNX export** | 併入 Phase 1a 軌道 2 C | 從此只在本章節推進 |
| **P1-7 A+B+C** | 併入 Phase 1a 軌道 2 | P1-7 殘留 D Teacher / LinUCB / Bayesian / RL |
| **P1-10 STRATEGY-ASYMMETRY-1** | Phase 2 · W25 並行，比 ML 重要 5× | P1-10 獨立追蹤工作項 |
| **P0-3 Phase 5 edge 重評** | 推遲到 P1-10 + Track P 都上線後 | P0-3 timing 依本章節進度 |
| **G-7 Teacher** | Phase 4 整合 | G-7 W23 正常排，不阻前 3 Phase |
| **G-6 ML edge 噪音** | P1-7 B 解阻塞後自然解 | 等 B 完成 |

### ⚠️ 風險與退路（任一觸發 → 啟動對應 fallback）

1. **Step 0 任一不確定紅** → 重整設計（TODO 層新增，worklog 無對應）
2. **Phase 1 Track P replay net edge < 0** → 不上線，改 Tier B（per-strategy native TP）
3. **Phase 2 shadow 一致性 < 60%** → 特徵集不夠 / 模型過簡 / 樣本不足，補齊再推 Phase 3
4. **Phase 3 Hybrid edge < P-only** → rollback `ml_override_high=2.0`，Track L 回 shadow
5. **Per-strategy ML 過擬合 grid_trading** → 每策略獨立訓練；小樣本（bb_breakout 0、bb_reversion 66/d）強制 P-only 不進訓練池
6. **Counterfactual replay 完全失敗**（Step 0 不確定 4 紅）→ 轉「事後歸因 audit」（peak-to-exit 軌跡分析），Phase 1 replay 驗收標準放寬
7. **Hold-out control edge 顯著 > ML-active** → ML 存在 feedback bias / 資料洩漏，暫停訓練查因（QA 守衛 #3 常態監控）

---

## 🟡 P1 — 當週活躍

### P1-5 · DEMO-REBOOT-PNL-RESET-1 — drawdown 跨重啟視角斷鏈 ✅ 2026-04-20（commit `7cda4e4`）
- **Root cause**：`peak_balance` 只活在記憶體 → 每次 engine restart 靜默重置 drawdown baseline；剛觸發 5% drawdown 的 session 重啟後看起來乾淨，繞過 fail-closed
- **修復（Option A + A2）**：`peak_balance` 持久化到 DB；restore-on-start 用 `max(restored, current)` clamp（live recovery 永不降低基準線）；僅 operator IPC 可顯式 reset（重啟不自動重設）
- **Rust**：`paper_state/checkpoint.rs`（load/write/delete）+ `PaperState::restore_checkpoint` clamp + `reset_drawdown_baseline` + event_consumer hot-path detached UPSERT + `PipelineCommand::ResetDrawdownBaseline` + ipc_server JSON-RPC method
- **DB**：`V018__paper_state_checkpoint.sql`（trading.paper_state_checkpoint PK=engine_mode，非 hypertable，≤4 rows，CHECK engine_mode whitelist + peak_balance ≥ 0）
- **Python**：`RiskViewClient.reset_drawdown_baseline` + `POST /api/v1/paper/risk/reset-drawdown-baseline`（Operator role gate + engine whitelist + ChangeType.STATE_CHANGE 審計 + IPC 失敗 HTTP 500 不 fake-success）
- **Tests**：+9 Rust（engine lib 1629→1640）+ +4 client + +8 route（control_api_v1 2511 passed / 2 pre-existing DYNAMIC-RISK fails）
- **Deploy**：V018 已 apply 到 trading_postgres；`restart_all.sh --rebuild` 完成（2026-04-20 00:11:43）；checkpoint writer 確認 live（demo row `peak_balance=948.85` 已寫入）
- **Operator tool**：`helper_scripts/db/deploy_V018.sh`
- **Worklog**：`docs/worklogs/2026-04-20--p1_5_a2_drawdown_continuity_implementation.md`

### P1-6 · DEMO-BYBIT-SYNC-ORPHAN-1 — bybit_sync 倉位策略動不了 + Demo 死循環殘留
- **現象**：6 個 owner_strategy=bybit_sync（DOTUSDT/NEARUSDT/BLESSUSDT/ENAUSDT/AAVEUSDT/BTCUSDT）非本輪策略開
- **死循環機制**（Demo 殘留；Live_Demo 因 T0 bypass 關閉後暫不適用）：correlated exposure 70% > limit 65% → 0 new opens → 0 fills → seeded positions 無活躍策略 emit Close → exposure 不降 → 永遠超限。`risk_gate: correlated exposure 69-70% >= limit 65%` engine.log 證據；Guardian 17.8k Rejected verdicts `direction_conflict`
- **狀態**：P1-8 FUP `retriage_synthetic_owner` tick-level 已自主接管中，觀察一週（起算 2026-04-17）
- **若不消化**（一週後仍卡）後備方案：
  - 方案 A：查 `grep ORPHAN /tmp/openclaw/engine.log` + ORPHAN-ADOPT-1 Phase 2A adopt logic 是否處理 bybit_sync 來源
  - 方案 B：臨時調 `correlated_exposure_max_pct` 65→75 解死鎖（IPC hot-reload）
  - 方案 C：ORPHAN-ADOPT-1 Phase 2B 補 orphan close path（前置 G-1 R-02 Strategist）
- **注意**：`correlated_exposure_max_pct` config TOML=60.0 但 runtime=65.0（GUI hot-reload 修改過）

### P1-7 · LEARNING-PIPELINE-DORMANT-1 — 半殼學習管線
- **數據累積層 ✅**：`learning.decision_features` 1.65M rows · `risk_verdicts` 24h 1.54M
- **edge_estimates.json writer/reader 鏈 ✅（手動）**：2026-04-18 20:24 首次寫入 29 KB / 104 cells / demo `grand_mean=-2214 bps`（**P1-15 查明受 28 phantom cells 污染，b0df1b3 修復**；live_demo 7d 乾淨 baseline −14.97 bps ≈ fee-neutral）；Rust startup 加載進 cost_gate。**缺 scheduler + hot-reload**（詳 §P1-14 bind blocker）
- **下游消費仍 dormant ❌**：`experiment_ledger_snapshot.json` 結構異常 · 21 個 learning schema 表存在無 consumer · ONNX 0 artifact
- **A/B/C 已併入 DUAL-TRACK Phase 1**（不再此處追蹤）
- **此處殘留**：D Teacher（G-7 W23）/ LinUCB / Bayesian posterior / RL transitions 全休眠
- **阻 Phase 5 edge 收斂**，不阻 Live

### P1-10 · STRATEGY-ASYMMETRY-1 — grid 過度交易 + ma_crossover R:R 不對稱

| engine | strategy | n_exits | net | 勝率 | 不對稱倍數 |
|---|---|---:|---:|---:|---:|
| demo | grid_trading | 747 | **−$43.36** | 59% | 1.71× |
| demo | ma_crossover | 135 | **−$11.90** | 64% | **2.54×** |
| live_demo | grid_trading | 405 | −$5.67 | 66% | 1.72× |
| live_demo | ma_crossover | 102 | +$0.79 | 67% | 1.21× |

- **核心問題 1**：grid demo fee $31.43 = gross loss 74%；747 exits/24h = 31 筆/h 過度交易
- **核心問題 2**：ma_crossover demo 不對稱 2.54×（勝 $0.19 / 虧 $0.47），勝率 64% 仍負 edge
- **下一步**：(1) grid `cooldown_ms` 或 min holding time（`grid_trading.rs` 掛單節奏 audit）(2) ma_crossover SL/TP 比率 audit（ATR mult / R:R gate）
- **與 DUAL-TRACK Phase 2 並行**：兩者修好 P0-3 才能乾淨重評；ma_crossover 若 2.54× 不能收斂到 ≤1.5× 應 disable 或等 R-02 Strategist 重評

#### 🧠 2026-04-19 推進推理鏈（compact-safe，survive-compact 用）

**⚠️ 起因**：2026-04-19 15:37 redeploy 後重查 R:R 不對稱，追蹤到以下結構事實：

1. **legacy COST EDGE 已死但 Track P T4 未接線 → Priority 6 真空態**
   - `risk_checks.rs:245-259` 舊 COST EDGE gate block 已註解（DEPRECATED）
   - 新 PHYS-LOCK gate（`risk_checks.rs:129-165`）存在但依賴 `exit_features: Option<&ExitFeatures>`
   - `tick_pipeline/on_tick.rs:1456-1474` `evaluate_positions(...)` closure 目前傳 `|_| None` → PHYS-LOCK 永遠拿不到 features → 永遠 Hold
   - 結果：舊 COST EDGE 不再砍 winner（好），但新 PHYS-LOCK 無法啟動（Priority 6 空轉）
   - DB 驗證：redeploy 後 `trading.fills` 0 條 COST EDGE close，證明舊路徑徹底死

2. **`trailing_activation_pct=0.8` 非 hardcoded**
   - `rust/openclaw_engine/src/config/risk_config.rs:518` `default_trailing_activation_pct() -> 1.0`
   - 三環境 TOML 獨立（已由 `feedback_env_config_independence.md` 記錄）：
     - `risk_config.toml:35 = 1.0` · `risk_config_demo.toml:35 = 0.8` · `risk_config_paper.toml:51 = 0.5` · `risk_config_live.toml:37 = 0.5`
   - **7d DB 查核 `trailing_stop` 觸發次數 = 0** → R:R 不對稱**非** trailing 主因

3. **DB 真實 R:R 不對稱主因**：redeploy 前舊 COST EDGE 在 pnl +0.30~0.33% 近 100% 勝率斬 winner，虧損側放任跑到 stop_loss；redeploy 後 COST EDGE 死，但 PHYS-LOCK 未接 → 當前進入「沒有微利退場」的短暫窗口

**路線決策（user 已批 2026-04-19）**：

- **R1 先**（零成本，24-48h）：觀察 post-redeploy R:R / fee-drag / 退場分布，確認舊 COST EDGE 死後的自然 edge 軌跡
- **A**（接受）：MICRO-PROFIT-FIX-1 / COST EDGE / PHYS-LOCK 為主軸；下一步由 R1 決定
- **C**（延後）：`trailing_activation_pct` 調 1.5-2.0% + 縮 trailing_distance，**必須** MICRO-PROFIT 修完再動
- **B**（駁回，見 `feedback_env_config_independence.md`）：統一 paper/live/demo TOML 被駁回，三環境故意獨立

**Track P T4 wiring blocker（Phase 1b W24 排期中）**：
- `ExitFeatures` 8 欄位（`exit_features.rs:18-36`）需 builder：`est_net_bps` / `peak_pnl_pct` / `current_pnl_pct` / `atr_pct` / `giveback_atr_norm` / `time_since_peak_ms` / `price_roc_short` / `entry_age_secs`
- 需新增 `peak_reached_ts_ms` 到 `PaperPosition`（legacy migration），見 §DUAL-TRACK Phase 2 Track P 第 82 行
- **決策**：不搶進度，R1 觀察後若 R:R 持續惡化再考慮加速 T4 wiring；否則按 W24 排期

**R1 觀察 SQL 模板**（每 6h 跑，對比 redeploy 前 24h baseline）：
```sql
-- post-redeploy exit-kind distribution (redeploy_utc='2026-04-19 13:37')
SELECT engine_mode, strategy_name,
       SPLIT_PART(owner_strategy,':',1) AS close_kind,
       COUNT(*), ROUND(AVG(realized_pnl)::numeric,4) AS avg_pnl,
       ROUND(SUM(realized_pnl)::numeric,2) AS total_pnl
FROM trading.fills
WHERE ts_ms >= EXTRACT(EPOCH FROM TIMESTAMP '2026-04-19 13:37+00')*1000
  AND owner_strategy LIKE '%close%' OR owner_strategy LIKE 'risk_close%'
GROUP BY 1,2,3 ORDER BY 1,2,4 DESC;
```

**R1 驗收指標**：
- 若 24h 後 R:R demo ma_crossover ≤1.5× 自然收斂 → Track P T4 不急，按 W24
- 若 R:R 仍 >2.0× 或 fee-drag 惡化 → 加速 Track P T4 為 P1-critical
- 若 redeploy 後 `risk_close:phys_lock_*` 數 > 0 → T4 已部分活化（檢查程式碼走查）

### P1-11 · BB-BREAKOUT-DORMANT-1 — 5 重 AND 14d 0 fills
- **根因**：`bb_breakout.rs:457-518` 入場 5 重 AND（squeeze → expansion → volume → Donchian → persistence）+ 時序要求過嚴
- **下一步**：(1) 閾值 offline backtest（squeeze 0.025 / expansion 0.035 / volume 1.2）(2) Donchian AND→OR/score (3) 考慮 aggressive/conservative 分拆 A/B
- **優先級**：P1 低 — 不緊急但影響 Phase 5 策略多樣性

### P1-12 · BB-REVERSION-BLOCKED-1 — 66 信號產生 100% 被下游擋
- **現象**：24h live_demo 66 筆 decision_features 但 0 fills（14d demo 僅 2 筆）
- **可能阻擋**：confluence / `check_order_allowed` / cooldown 10min / dispatch min_notional / risk_close 秒殺
- **下一步**：(1) 找出 66 筆 intent_id/context_id join `risk_verdicts` + engine.log trace (2) 統計阻擋分佈 (3) 對症處理
- **備註**：P0-6 永久修復後 `rejected_reason` 已 persist 到 `risk_verdicts.reasons` → trace 高效化

### P1-13 · SAMPLE-FLOOR-GAP-1 — per-strategy round-trip 樣本低於 ML 訓練閘口

| engine | grid_trading | ma_crossover | funding_arb | bb_reversion | bb_breakout |
|---|---:|---:|---:|---:|---:|
| demo+live_demo fills | 2,492 | 762 | 77 | 2 | 0 |
| 估計 RT | ~1,200 | ~380 | ~38 | 1 | 0 |

- **現象**：Step 0 不確定 3 audit — `trading.fills` 配對 RT 遠低於 QA 守衛「≥1000/策略」；僅 grid_trading 勉強過閘
- **影響**：DUAL-TRACK Phase 1 Track L 範圍限 grid_trading 單策略 PoC；ma_crossover/bb_*/funding_arb 延後，累積期間 Track P only
- **下一步**：(1) 正式更新 DUAL-TRACK Phase 1 軌道 2 C 範圍聲明限 grid_trading (2) 每週 per-strategy 樣本 audit 判斷加入時點
- **關聯**：DUAL-TRACK Step 0 不確定 3 / Phase 1 軌道 2 C · QA 守衛 #1 · 風險退路 #5

### P1-14 · EDGE-ESTIMATE-BIND-BLOCKED-1 — JS estimator snapshot edge 不足以 bind cost_gate
- **現象**：Step 0 不確定 1 驗證 `settings/edge_estimates.json` 首次寫入成功（104 cells · demo `grand_mean −2214 bps`）。**更正（2026-04-18 b0df1b3 P1-15 修復後）**：原 −2214 bps 受 28 phantom cells（18 `ipc_close_symbol::*` + 10 `risk_check::*`）污染，非可信 reading；live_demo 7d 乾淨 baseline `grand_mean −14.97 bps` ≈ fee-neutral，落在典型 fee-drag 範圍
- **問題**：當前 snapshot 未達 bind threshold（需 ≥2 策略 shrunk_bps>0 且 grand_mean > −50 bps），hot-reload 進 Rust cost_gate 仍會抑制過多 intent
- **根因**：cells 層級 edge 仍偏負/不穩定的結構原因 = P1-10（grid fee 74% + ma_crossover 2.54× R:R 不對稱），非 estimator 機制缺陷；污染部分已由 P1-15 消除
- **下一步**：(1) DUAL-TRACK Phase 1 軌道 2 B 僅啟 scheduler 寫檔 + PG UPSERT，**不綁定** Rust cost_gate 讀取 (2) P1-10 修復落地後重跑 estimator 觀察 grand_mean 走勢 (3) 條件啟動 bind：grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0（fee-drag 範圍可接受，catastrophic-negative 才禁 bind）
- **阻塞**：不阻 Live；阻 DUAL-TRACK Phase 1 軌道 2 B 完成判定 + Phase 5 cost_gate 重啟
- **關聯**：P1-10 STRATEGY-ASYMMETRY-1（必要前置）· DUAL-TRACK Phase 1 軌道 2 B · P0-3 Phase 5 edge 重評

### P1-15 ✅ LEARNING-SCHEMA-QUALITY-1 — ipc_close_symbol 前綴缺失 + estimator live_demo 不接受（commit b0df1b3）
- **背景更正（2026-04-18 實地查核）**：初審誤判 strategy_name cardinality 爆炸，經查 `realized_edge_stats._pair_round_trips`（`program_code/ml_training/realized_edge_stats.py:196`）在配對時用 **entry** fill 的 strategy_name，close fill 字串只參與 `is_exit` prefix 判斷（line 161-168 `startswith`），COST EDGE 動態字串**不會**產生分桶。
- **104 cells 實際組成**：grid_trading 33 · ma_crossover 31 · funding_arb 12 · **ipc_close_symbol 18（現役 bug）** · **risk_check 10（歷史遺留，fix landed 2026-04-16 P0-4 R1，30d 窗口自然消化）**；實際異常僅 28 cells，非初報 ~80。
- **Gap 1（現役）**：`rust/openclaw_engine/src/tick_pipeline/commands.rs:668` `strategy: "ipc_close_symbol".into()` 未依 EDGE-P2-1 規範加 `risk_close:` / `strategy_close:` 前綴 → ML pipeline `is_exit` 檢查（line 161-168）未命中 → 被誤歸類為 entry fill → 產生 18 個幻影 strategy cells。
- **Gap 2（estimator）**：`program_code/ml_training/realized_edge_stats.py:238` validator `if engine_mode not in ("paper","demo","live")` 拒絕 `live_demo` → 2.23M LiveDemo 樣本無法進入估計。
- **下一步**：(1) Rust `commands.rs:668` → `"strategy_close:ipc_eviction"` 或 `"risk_close:ipc_close_symbol"`（後者更保留可追溯性），+1 Rust 單測驗證 `is_exit` 判定 (2) Python `realized_edge_stats.py:238` allowlist 加 `live_demo` + 可選 `IN ('live','live_demo')` 查詢模式（符合 user memory），+1 Python 單測 (3) 重跑 estimator 驗證 `ipc_close_symbol::*` 消失、新增 `live_demo` 快照
- **Scope**：~3 hours，2 檔變更 + 2 單測，**無 schema 改動、無 PG migration、無 `close_reason_tag` 新欄位**
- **不涉及**：`grand_mean_bps=-2213.98`（_meta 內）結構性負 edge 屬 P1-10 範圍，非 schema 問題；B=0.888 heavy shrinkage 把所有 cells 拉向 grand_mean 是 P1-14 bind 阻塞的真正根因
- **阻塞**：不阻 Live；輕阻 P1-14 bind 前置可信度（清掉 18 個 phantom cells 讓 snapshot 可讀性改善）
- **關聯**：P1-10 STRATEGY-ASYMMETRY-1（真正 edge 翻正前置）· P1-14 EDGE-ESTIMATE-BIND-BLOCKED-1 · DUAL-TRACK Phase 1 軌道 2 B
- **實測結果（2026-04-18 post-commit）**：E1 修復後跑 live_demo 7d 產出 28 乾淨 cells / `grand_mean_bps = -14.97`；但發現 **grand_mean 真實元兇非 phantom cells**——2 個尾端 outlier（`grid_trading::DOTUSDT raw=-152k bps` / `LINKUSDT raw=-67k bps`）佔 raw weighted grand_mean 主要權重，B=0.888 heavy shrinkage 再將所有 cells 拉向毒值。P1-15 清掉 28 phantom 對 grand_mean 僅移動 -2438→-2473 bps；真實解毒需 P1-16 + P1-17（見下）。

### P1-16 ✅ HALT-SESSION-CROSS-SYMBOL-PRICE-CORRUPTION-1 — Rust 上游 + Python 下游雙管修復（commit 待填）
- **根因（RCA 2026-04-18 L1 confirmed）**：Rust halt_session force-close 路徑把 **ETHUSDT 的價格 $2357.94 蓋到其他 symbol 的 fill 記錄**（DOT/HIGH/IP/AAVEUSDT 同時間戳 `2026-04-18 19:09:56.302`，fill_ids `close-demo-{SYMBOL}-1776532196302`）。位置：`tick_pipeline/on_tick.rs:1480-1484` `.unwrap_or(event.last_price)` fallback——觸發 tick 的 symbol price 在 all_pos 迴圈中被蓋到所有缺 `latest_prices` 條目的其他 symbol。下游 pairer 忠實處理毒 fill：halt exit `qty=0.1` vs live FIFO entry `qty=51.7` → `matched_qty=0.1`，`entry_notional = 1.3384 × 0.1 = $0.13`，`−$235.66 / $0.13 × 10000 = −17,617,373 bps`。
- **修復（雙管並行）**：
  - **(1) 上游（Rust · 根因）**：`on_tick.rs` HaltSession arm 改用既有 `close_position_at_symbol_market` helper（與 ClosePosition 分支同款安全 pattern：per-symbol `paper_state.latest_price` → entry-price fallback）；移除 `.unwrap_or(event.last_price)` 洩漏點。+1 regression test `test_halt_session_uses_per_symbol_price_not_triggering_tick`（多 symbol halt 驗證 BTC 用自己 tick、ETH/DOGE 在無 latest 時 fallback 到 entry）。
  - **(2) 下游（Python · safety net）**：`realized_edge_stats._pair_round_trips` 加 (a) price-jump gate：`|ln(exit/entry)| > 0.5` 直接 skip + 計數器 `_price_jump_skip_count`；(b) 分母托底：入隊時記 `qty_total`，bps 分母取 `max(full_entry_notional, match_notional)` 防止 partial match 微分母放大。保留 ±5000 bps Winsorize 作第三線。+5 新單測 + 2 既有 Winsorize boundary 測試重定位到 gate band 內。
- **實測結果**：
  - **archived demo corpus 6616 fills / 5129 round-trips**：**27 price-jump skips**（P1-16 指紋）/ **0 winsorize clamps** / `mean_net_pnl_bps = -9.02`（vs 修前 grand_mean=-2214，**245× 乾淨**）/ range `[-901, +1327]` bps 自然分布。
  - **live_demo 7d**：0 skips / 0 clamps / grand_mean `-8.46` bps — gate 不誤傷合法資料。
- **驗證**：engine lib **1499 passed / 0 failed**（+1 P1-16 upstream）· ml_training **238 passed / 13 skipped**（+5 gate tests）
- **待辦**：`--rebuild` 部署 Rust 修復活化上游，Python 下游 commit 後已即時生效（純 pairer 純函數）
- **阻塞解除**：P1-14 bind「極端 outlier 污染」分支徹底關閉（從根因 + safety net 雙重保險）；Phase 5 edge 聚合可信度回復；E5 goodput 恢復 audit 可追溯性
- **關聯**：P1-14 EDGE-ESTIMATE-BIND-BLOCKED-1 · P1-17 JS-ESTIMATOR-WINSORIZATION-1（保留為第三線） · RCA report `task a260701044e092991`

### P1-17 ✅ JS-ESTIMATOR-WINSORIZATION-1 — outlier clamp 落地（commit 待填）
- **背景**：`program_code/ml_training/realized_edge_stats._pair_round_trips` 無 Winsorization，任何 raw_bps 無上限傳播到 JS shrinkage 的 grand_mean 計算。B=0.888 heavy shrinkage 把整個 snapshot 拉向毒值。
- **實作**：(1) 模組常數 `_WINSORIZE_BPS = 5000.0`（E1 自動提升 — `risk_config_demo.toml stop_loss_max_pct=25%` 下原建議 ±1000 bps 會截掉合法大額止損）+ 雙語注釋 (2) `_winsorize_bps()` helper + 模組級 clamp counter（`get_winsorize_clamp_count()` / `_reset_winsorize_counter()` API）(3) `_pair_round_trips` RoundTripRecord 構造時對 `gross_pnl_bps`/`net_pnl_bps` 套用，clamp 觸發 WARNING log (4) 新測試檔 `tests/test_winsorize.py` 8 cases：`constant_is_5000_bps` / `normal_passes_through` / `extreme_negative_clamps` / `extreme_positive_clamps` / `boundary_negative` / `boundary_positive` / `zero_passes_through` / `gross_inside_net_outside`
- **實測結果**：
  - demo 30d（archived to `demo_archive_20260418`）: grand_mean **-2213.98 → -78.38 bps**，19 clamps fired（1 個數量級改善進入 fee-drag 範圍）
  - live_demo 7d: grand_mean 保持 **-14.97 bps**，0 clamps（預期，7d 無 outlier）
  - 順帶暴露 P1-16：E1 跑時發現 `grid_trading::HIGHUSDT gross=-49,479,767 bps`（不可能值）及 LINKUSDT 幾何級數 -6,778 → -1,734,596 bps → B RCA 確認為 halt_session cross-symbol price corruption
- **驗證**：`ml_training/tests/` 全套 217 passed / 2 skipped / 0 failed
- **下一步**：P1-14 bind 門檻判定（grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0）現 demo 仍未達但 live_demo 接近；等新 21d demo 累積（P0-2 清算後）重跑
- **阻塞解除**：P1-14 bind 前置的「極端 outlier 污染」分支已關閉（safety net 啟用）；P1-16 halt_session cross-symbol price corruption 仍為根源阻塞，需獨立修復
- **關聯**：P1-14 · P1-16（互補 — Winsorization 是 safety net，P1-16 從源頭排除錯誤 fill）· DUAL-TRACK Phase 1 軌道 2 B

---

## 🟢 P2 — 下週 / Live Gate / QoL

### Live Gate
- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking, W23）
- [ ] **LG-3** provider pricing table 正式綁定（W23）
- [ ] **LG-4** M 章 Supervised Live Gate（W24）
- [ ] **LG-5** N 章 Constrained Autonomous Live（W24）
- [ ] **G-4 / SEC-21** Cookie `secure=True`（HTTPS 部署後，W24）

### AI Layer 接通（W23）
- [ ] **G-7** ClaudeTeacher 啟用（`consumer_loop.rs enabled=false`，前置 21d demo + G-3 IPC auth ✅）
- [ ] **G-10** Calibration.py 整合（isotonic → `run_training_pipeline.py` + ECE < 0.05）

### QoL & 設計債
- [ ] **QoL-2** Demo AI cost 追蹤（`tab-demo.html` 硬編碼 'N/A'，依賴 G-1 H1-H5）
- [ ] **DUST-EVICTION GUI 曝光**（P1-8 FUP）：log-only 觀察滿一週後（起算 2026-04-17）→ GUI 曝光 `dust_frozen` / `orphan_frozen` 倉位給 operator 日報；`paper_state.rs` 已有 `TriageOutcome.dust_frozen` 計數器
- [ ] **LEARNING-COCKPIT-NO-IPC-1** Learning 8 端點走 Python state_store 非 Rust IPC（設計債，等 G-7/G-10 後再議；不阻 Live，原則 #7 學習平面與 Live 隔離）
- [x] **DYNAMIC-RISK-STATUS-TEST-SIG-1** ✅ 已修復 commit `83a0475` (2026-04-19) — 採方案 (a) `TestClient(app).get(...)` 走 HTTP dispatch，並傳 `Authorization: Bearer` header 因為兄弟測試 `importlib.reload(main_legacy)` 會 swap 掉預先捕獲的 `current_actor` dep key。2 tests pass · pytest baseline 2587+2→2589+0。
- [ ] **E5-P1-5-FUP** — P1-5 JSON-RPC `param_extractor.rs` 目前帶 `#![allow(dead_code)]` 等 handlers.rs 消費。需開工項：掃 `ipc_server/handlers/*.rs` 把內嵌 `as_str()/as_f64()/as_u64()/unwrap_or(default)` 手寫解包替換成 `param_extractor::require_*` / `optional_*`，至少兩個 handler file 當示範，確認 param_extractor.rs 死碼警示可解。E2 nit 追蹤（a4101cb63edc44e93 / af8076b578356a939）。
- [ ] **E5-P1-4-FUP** — `llm_call_wrapper.call_ollama_timed` dead-on-arrival，考慮：(a) 接 StrategistAgent `_evaluate_edge` 手寫 latency 計時（strategist_agent.py 約 918 行）；(b) 若永遠不接，下 commit 刪除 helper。E2 nit（a4101cb63edc44e93）。
- [ ] **E5-P1-8-FUP** — `rejection_coding.rs` 第二 `impl RejectionCode` block（`from_guardian_review` 工廠）可折疊到主 impl；分類 helpers（`is_cost_gate_reject` / `family`）帶 `#[allow(dead_code)]` 等 consumer 接線後移除 allow。E2 nit（a9ccde4552860c973）。
- [ ] **E5-P1-CANCEL-P1-6** — `h0_gate.py` vs `paper_live_gate.py` pipeline 抽象經 sub-agent 實測 0 真實共用，cancel。未來出現第三個類似 gate 時再重開評估（見 2026-04-19 CHANGELOG Wave 1 章節）。
- [ ] **E5-P1-CANCEL-P1-7** — `PipelineCommand` dispatch-match 已在 prior pass 從 `tick_pipeline/` 遷至 `event_consumer/handlers/`（由 P1-3 進一步 by-domain 拆完），原任務前提過時 cancel。真正候選：`tick_pipeline/commands.rs` 836 LOC helper impl 切 `commands/orders.rs` / `commands/governor.rs` / `commands/close.rs` 等 topical submodules（新排 E5-P2-X 非本 E5-P1-7）。
- [ ] **E5-P1-2-DEFERRED** — `rust/openclaw_engine/src/main.rs` bootstrap 拆分依 E5 audit 建議「觀察穩定性再拆」（P0-9 停電 RCA 後唯一未重組模塊）暫不派；operator 可在 Live 對後覆蓋。
- [ ] **E5-P2-4b** — 3 檔超 §九 1200 LOC 硬上限（`strategies/bb_breakout.rs` 1265 / `strategies/grid_trading.rs` 1434 / `strategies/mod.rs` 1442），pre-existing tech debt（非 E5-P2-4 新增）；分檔切：bb_breakout 核心邏輯 vs 進出場工具 vs helpers；grid_trading 網格佈局 vs 持倉管理；strategies/mod.rs registry/factory 拆 `strategies/registry.rs`。(2026-04-19 E5-P2-4 E2 nit 追蹤 a79a2607845253fdb)
- [ ] **E5-P2-2-CLOSED**（資訊）— onnx_inference consolidate 優化前提已由 EDGE-P3-1 Phase B Step 7b `OrtPredictor.input_name: String` load-time cache 滿足；`ml/model_manager.rs` 仍是 stub，待 ort 真接線後若出現第二個 session 再評；audit §九 blueprint 對應行建議下修或刪除。(2026-04-19 Wave 2 CANCEL evidence)
- [ ] **E5-P2-6-DEFERRED** — `tick_pipeline/fill_context_builder.rs` 抽取暫延，等 EXIT-FEATURES-TABLE-1 operator WIP 落地後重新評估衝突面。(2026-04-19 defer evidence)
- [ ] **E5-P2-1-DEFERRED** — PipelineCommand enum reorg 暫延，與 P2-6 共爭 tick_pipeline/mod.rs；同等待 EXIT-FEATURES-TABLE-1 落地。
- [ ] **E5-P2-7-CLOSED**（資訊）— claude_teacher/directive_handler 抽取 cancel：R6 cohesion invariant + FIX-08 fixtures 已拆 + denylist/helpers/apply_* 1-to-1 耦合無外部消費者；未來新增第 5 種 directive 或跨 directive 共享 veto 邏輯時重開。
- [ ] **E5-P2-8-CLOSED**（資訊）— Python learning_batch_writer cancel：control_api 唯 1 個 `INSERT INTO learning.*`，ml_training 11 writer 各寫 distinct schema 無共用 row shape，真實批寫重複已由 E5-P0-4 Rust `batch_insert.rs` 處理。
- [ ] **E5-FN-1-CANCEL**（資訊）— audit §七.7.1「live_authorization.verify 同步但 main.rs 首次 re-verify 在 5 min 後，中間有窗口」聲稱不成立：`startup.rs:467-494` `build_exchange_pipeline` 在 pipeline 構造前已同步 `load_and_verify(env)`，失敗即 `return None` 拒絕 spawn；5 min ticker 只是 mid-session revoke detector。0 lines changed。(2026-04-19 E5-FN-1 evidence-based CANCEL)
- [x] ~~**E5-FN-2-DEPLOY** V018 partial UNIQUE~~ **SUPERSEDED** by Plan N（commit `f0f11c0`，revert `87b7653` of `fd480ba`）：V018 partial UNIQUE 無法 apply on TimescaleDB hypertable（UNIQUE index 必須含 partitioning column `time`），empirical error `cannot create a unique index without the column "time"`。改用**既有** hypertable PK `(time, scope, request_id)` 做 `ON CONFLICT DO NOTHING RETURNING 1` — **零 schema 改動、零 migration**；`make_request_id(scope)` 回 `(rid, ts_ms)` tuple，caller 重試必須傳同 tuple。IPC `handle_record_ai_usage` 收 Python 傳入 `(request_id, event_time_ms)` 或本地鑄造，封閉 fd480ba 原本要引入的 `"py-sync"` literal PK 碰撞。engine lib 1567→1571（+4 Plan N tests）。
- [ ] **E5-FN-2-PLAN-N-FUP** — Plan N 部署後 follow-up：(a) Python Layer-2 sync caller 可選升級為傳入 `(request_id, event_time_ms)` 以獲得跨重試的真實去重（目前 IPC handler 本地鑄造時每次 retry 會被當新 row — 仍不會雙重計費本地 caller 自己，但失去跨 Python 重試保護）；(b) `test_make_request_id_unique_within_same_ms` 為 1 對 mint 對比，flake 機率 ~1/2^32，若 CI 偶發誤報換 seeded RNG；(c) 部署後 `SELECT time, scope, request_id, COUNT(*) FROM learning.ai_usage_log GROUP BY 1,2,3 HAVING COUNT(*) > 1 LIMIT 5;` 應永遠 0 rows（PK 保證）。

### E5-FN-3-FUP · 4-Agent audit_callback wiring（pattern-extend AnalystAgent pilot）

- **起源**：E5-FN-3 commit `19f3d85`（2026-04-19）只接了 AnalystAgent pilot；另 4 agent 留給 follow-up
- **動因**：違反 Root Principle #8「交易可解釋」— Scout/Strategist/Guardian/Executor 決策點共 **13** 個 `_audit()` call-site 目前 silently no-op
- **前置閱讀（後續 session 接手）**：
  - Commit `19f3d85` 的 `git show` — 完整 RCA + 實施模式
  - `docs/CLAUDE_CHANGELOG.md` §「E5-FN-3 — agent_audit_bridge + AnalystAgent pilot wiring」
  - `docs/audits/2026-04-18--e5_full_codebase_audit.md` §七.7.3
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_audit_bridge.py`（stateless 工廠 — 不需改動，只需調用）
  - `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:249,339`（AnalystAgent pilot 兩 call site，template 參考）
  - `CLAUDE.md §九`（singleton 登記表，每新增 `_*_AUDIT_CB` 必須登記）
  - CLAUDE.md §二 Root Principle #8

- **實施模式**（每 agent 照 Analyst pilot 抄）：
  ```python
  # strategy_wiring.py 模組級（接近 _ANALYST_AUDIT_CB 處）：
  _GOV_HUB_FOR_<AGENT> = _governance_hub_resolver()
  _<AGENT>_AUDIT_CB   = make_agent_audit_callback(_GOV_HUB_FOR_<AGENT>, "<Agent>Agent")
  # ctor call-site：
  <Agent>Agent(..., audit_callback=_<AGENT>_AUDIT_CB)
  ```
  每新增 singleton **同 commit 登記 CLAUDE.md §九**（與 `_ANALYST_AUDIT_CB` 同列格式）。

- **4 sub-tasks**（ID-order 建議）：
  - [x] **FUP-a Strategist** ✅ 2026-04-19（並行 sub-agent · commit 待填）：wire at `strategy_wiring.py:~172` + `_GOV_HUB_FOR_STRATEGIST` try-import + `_STRATEGIST_AUDIT_CB = make_agent_audit_callback(..., "StrategistAgent")`；new `test_strategist_audit_wiring.py` 2 tests 全綠（ctor + directive_received → STATE_CHANGE row）。StrategistAgent code **零變更**（已於 line 134 接受 `audit_callback` kwarg）。
  - [x] **FUP-b Guardian** ✅ 2026-04-19（並行 sub-agent · commit 待填）：wire at `strategy_wiring.py:~215`（`_GOV_HUB_FOR_GUARDIAN` 既存，補登記）；new `test_guardian_audit_wiring.py` 6 tests 全綠（ctor × 2 + verdict emit + directive state_change + fail-open × 2）。GuardianAgent code **零變更**。
  - [x] **FUP-c Executor** ✅ 2026-04-19（並行 sub-agent · commit 待填）：wire at `strategy_wiring.py:~369`（try 塊內，`_GOV_HUB_FOR_EXECUTOR` 既存）；new `test_executor_audit_wiring.py` 3 tests 全綠（ctor × 2 + directive_received emit）。ExecutorAgent code **零變更**。
  - [x] **FUP-d Scout** ✅ 2026-04-19（並行 sub-agent · commit 待填）：`multi_agent_framework.py` ctor 改為接受 keyword-only `audit_callback` kwarg（positional `(config, message_bus)` 保留）；`produce_intel()` / `produce_event_alert()` 各新增 `self._audit(...)` call-site（bus 路由**之前**）；wire at `strategy_wiring.py:~114` + `_GOV_HUB_FOR_SCOUT` + `_SCOUT_AUDIT_CB`；new `test_scout_audit_wiring.py` 8 tests 全綠（ctor × 3 + produce_intel × 2 + produce_event_alert × 1 + fail-open × 2）。

- **測試模板**：參照 `program_code/.../tests/test_agent_audit_bridge.py`（13 tests）；每新 agent wiring 加 1 integration test 驗 `audit_callback` 被 ctor 收下 + 至少 1 path 觸發 `record_change`

- **E2 APPROVE_WITH_NITS 非阻塞遺留**：
  - [x] **NIT-1 log throttle** ✅ 2026-04-19（Option C DEBUG 常開 + WARNING 60s 節流）：`agent_audit_bridge.py` 新 `_WARN_THROTTLE_SECONDS=60.0` + `_LAST_WARN_AT` dict keyed by `(role_name, event_class)` via `time.monotonic()`；DEBUG 總是發、WARNING 每桶 60s 一條；DB 死時刷屏問題解決。測試用 `_reset_warn_throttle()` 清狀態（未加入 `__all__`）。
  - [x] **NIT-2 test 覆蓋缺口** ✅ 2026-04-19：新 `test_unknown_event_type_defaults_to_parameter_change`（event_type `"opaque_event_xyz"` 不匹配任何 keyword → `PARAMETER_CHANGE` 保守默認）；bridge test 12 → 13。
  - [x] **NIT-3 thread-safety 文檔** ✅ 2026-04-19：`make_agent_audit_callback` docstring 新增中英對照 Thread-safety 段，涵蓋 (a) 跨 thread 調用安全 (b) `ChangeAuditLog._lock = threading.RLock()` 驗證（change_audit_log.py:156 + record_change:188）(c) fail-open 防 partial-write (d) `_LAST_WARN_AT` race-tolerant 設計說明。

- **驗收**：全 5 agent（Scout/Strategist/Guardian/Analyst/Executor）wire 完成後，`change_audit_log` 表應看到 `who IN ('ScoutAgent','StrategistAgent','GuardianAgent','AnalystAgent','ExecutorAgent')` 全部出現；搭配 Analyst pilot 觀察週（uvicorn 重啟後）做對比

---

## 🔵 P3 — 長期專項（W25+）

### AI Agent 全 5 鏈路
- [ ] **G-1 / R-06** 5 agent 全 real（Conductor 仍 stub；其他 4 已 R-06-v2 ✅）
- [ ] **FIX-01** H1-H5 AI Agent 接入
- [ ] **FIX-02** Decision Lease Rust 接入
- [ ] **FIX-12** CSP nonce 遷移
- [ ] **FUP-8 Phase 2** OrderIntent 加 edge/funding/basis/regime 欄位（等 Strategist 串線）

### ORPHAN-ADOPT-1 Phase 2B
- [ ] Strategist `would_take(symbol, side)` 升級為終仲裁；`KNOWN_STRATEGY_NAMES`+`EdgeEstimates` probe 降為 fast-path（前置 G-1 R-02）

### G-2 FundingArb 三參數重評（待 R-02 Strategist 上線後）
- [ ] R-02 Strategist 重評：`funding_threshold` / `max_basis_pct (0.5%)` / `total_cost_bps`
- **背景**：v2 n=13 NEGATIVE 結案，13/13 exit 全命中 max_basis_pct 邊界 → 邊界本身可能設錯；MICRO-PROFIT-FIX-1 窄帶對 funding_arb 是錯誤成本模型
- **前置**：G-1 R-02 Strategist 在線 + 提供新 cost model

### Phase 5 補強（等 P0-3 判決後）
- [ ] DL-1 Symbol Embedding · DL-2 Regime LSTM Shadow（5-04~07）
- [ ] JS + Scorer 整合 + correlation_pairs（5-08~09）
- [ ] E2/E4/QC/E5（5-10~13）

### EDGE P2 架構重工
- [ ] **EDGE-P2-2** OI + Liquidation 信號源（給 bb_breakout 加領先信號，Bybit WS `tickers` OI + `liquidation` stream）
- [ ] **EDGE-P2-3** Maker order 支持（5.5 bps → ~1 bps/side；改 IntentProcessor + order_manager + execution layer）

---

## ⚪ P4 — Backlog / Conditional

### IP-DEDUP-1 · IntentProcessor 同幣種重發去抖
- **觸發條件**：P0-3 判決後 edge 仍負 + 重發率仍高才啟動
- **設計**：`HashMap<(symbol, is_long, strategy), (ts_ms, reason)>` + 60s 窗口；只去抖被拒 intent；config `risk.intent_dedup.enabled` + `dedup_window_secs=60`
- **預期**：DF 行數降 95% + cost_gate CPU/DB IO 減少 + counter `intent_dedup_skipped` 透明
- **工作量**：~1d
- **接手指南**：`intent_processor/mod.rs` evaluate_predictor_gate 上游；類似機制參考 `governor_cooldown` / `last_ai_call_time_ms`

### WATCHDOG-DNS-CLASSIFY-1 · 區分 DNS 斷線 vs 真 crash ✅ 2026-04-20
- **狀態**：已實作 `helper_scripts/canary/engine_watchdog.py` — 新 `classify_engine_failure(log_path)` + `on_engine_crash(log_path=...)` 可選參數；P0-9 停電樣本驗證正確分類 `network_outage`
- **行為**：tail 20 行內連續 ≥5 條 `Temporary failure in name resolution` / `HTTP transport error` / `connection refused` / `failed to lookup address information` / `dns error` → `network_outage`（不計 strike、不觸發 auto-restart 以免 circuit-breaker 被無辜燒穿、engine_alive=False 讓 recovery 正常觸發）；tail 出現 `panic` / `assertion failed` / `stack backtrace` → 強制 `engine_crash` 正常計 strike；缺檔或空檔保守預設 `engine_crash`
- **測試**：+16 unit tests（10 classifier + 6 on_engine_crash wiring）；pytest helper_scripts/canary/test_canary.py 38→**54 passed**
- **工作量**：~2h（純 Python，不動 Rust；Rust engine 計數器無變動）

### WP-F GUI / WP-E4 測試 / WP-E5 大文件 / WP-I 文檔
- WP-F/O-xx · AH-08~11（詳 `docs/audits/2026-04-06--consolidated_remediation_report.md` §10.1）
- T-P2-9~11 · T-Q3/Q4/Q7/Q8 · T-I1~I4 tarpaulin/CI 門禁
- `tick_pipeline.rs` 2117 行專屬 session
- R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

### 前 Phase 殘留
- [ ] **2-11** actual training（fills 累積後，與 P1-7 C 同源）
- [ ] **4-06** LinUCB live warm-start（首次 v1→v2 遷移）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [ ] **G-6** Edge JS 滾動重訓 → P1-7 B 解阻塞後自然解
- [ ] **G-8** cost_gate 可信度評估（依 EDGE-P3-1 Stage 2）

### Phase 4-Conditional（觸發後才做）
- [ ] 4-1 PairsTrading（需 3 月協整）· 4-2 Beta Hedging · 4-3 Kalman · 4-5 Mac Studio 遷移 · 4-10 Jump detection

---

## 🗓️ 排期總覽

| 週次 | 日期 | 主要焦點 | 狀態 |
|---|---|---|---|
| W19-W22 | 04-14~05-09 | 基礎設施 / 安全 / Phase 6 / 3E-ARCH / Audit / FUP 全收 | ✅ 歸檔 |
| W22 末 | 04-16~18 | P0-4/0/5/8/9/10/11/12 + DEDUP-PY-RUST + MICRO-PROFIT-FIX-1 + DUST-EVICTION + G-2 NEGATIVE 結案 + P0-6 永久修復 + DYNAMIC-RISK-1 | ✅ 歸檔 |
| W23 | 05-12~16 | **DUAL-TRACK Step 0 ✅**（2/4 綠 + 1/4 黃 + 1/4 紅 → Phase 1 拆 1a/1b）· **Phase 1a**（P1-7 A/B/C + Track P 骨架 + MARKET-KLINES-STALE-1）· P0-2 LG-1 起算 · G-7 · G-10 · LG-2/3 | 🟡 進行中 |
| W24 | 05-19~23 | **DUAL-TRACK Phase 1b**（exit_features 累積 + 7 維 bind 真實閾值）· LG-4/5 · SEC-21 · QoL-2 | ⬜ |
| W25 | 05-26~30 | **DUAL-TRACK Phase 2**（Track L shadow，原 W24 延後）· **P1-10 並行** | ⬜ |
| W26-W27 | 06-02~13 | **DUAL-TRACK Phase 3**（Track L 灰度）· EDGE-P3-1 產線化 · Phase 5 補強或重做（P0-3 判決後） | ⬜ |
| W28+ | 06-16+ | **DUAL-TRACK Phase 4**（retraining/Teacher/Embedding/Regime LSTM）· G-1 R-06 全 5 agent | ⬜ |

**最早 Live**：W24 末（~2026-05-23）— 若 Step 0 任一紅需重整設計，可能延後 1-2 週

---

## 🔍 Gap 索引

| Gap | 描述 | 排期 | 狀態 |
|---|---|---|---|
| G-1 | AI Agent 5 stub | W22 R-02 ✅ · W25+ R-06 full | 🟡 |
| G-2 | FundingArb v2 NEGATIVE 結案 + 三參數待 R-02 重評 | W25+ R-02 後 | ✅ v2 歸檔 / 🔵 P3 重評 |
| G-3 / G-5 / G-9 | IPC auth · Rate Limit · HMAC | W19-20 | ✅ |
| G-4 | Cookie secure=False | W24 | ⬜ |
| G-6 | ML edge 噪音 → P1-7 B 解 | W23 | ⬜ |
| G-7 | ClaudeTeacher | W23 | ⬜ |
| G-8 | cost_gate 可信度 | EDGE-P3-1 後 | ⬜ |
| G-10 | Calibration.py | W23 | ⬜ |
| G-11 | dust silent drift → P1-8 | — | ✅ E1/E4 + FUP |
| G-12 | 微利退場 → DUAL-TRACK-EXIT-1 | W23 Step 0 ~ W27+ | 🟢 |

---

## 📚 已完成歸檔索引

**2026-04-19 PIPELINE-SLOT-1 Phases 1-4**（commits `3005fc0` Phase 1 · `e28f3d8` Phase 2 · `d92f25d` Phase 3 · Phase 4 pending）：
- Phase 1：`pipeline_slot.rs` 物理層抽象（SlotKind / try_spawn / teardown）+ `restart_kind.rs` sentinel（manual vs unattended 區分）+ `restart_all.sh` atomic sentinel write ✅
- Phase 2：auth-fail scope engine-wide → live-only（demo + paper 不再被 auth 過期拉下）+ `spawn_backoff.rs` exponential backoff 1s→60s ✅
- Phase 3：`live_auth_watcher.rs` 4-branch state machine + 5s poll + IPC `trigger_live_auth_recheck` fast path（sub-100ms respawn TTR）+ Python `_trigger_live_auth_recheck_fire_and_forget()` hook 到 renew/revoke ✅
- Phase 4（pending）：E2 F1 threaded-offload FUP（daemon thread 讓 HTTP 回應立即返回）+ 8 新 pytest `test_live_auth_recheck_trigger.py` + ADR `docs/decisions/2026-04-19--pipeline_slot_1_auth_fail_scoping.md`（D1-D4 決策 + 4 替代路徑拒絕）
- 保留：2026-04-14 Fix 3 panic→engine-wide cancel 語義不變；Rust side NO governance state persistence（ADR D4 理由）
- 測試基準線：engine lib 1629 / bin 38 / pytest +8 = 2828 passed
- 詳見 ADR D1-D4 論證

**2026-04-18**（commits `293a808` `1239312` `81a3807` `4de5689` `9bd637a` `b17152f`）：
- P0-6 永久修復（synthetic VerdictInfo 讓 rejected_reason 寫入 `risk_verdicts.reasons`）+ DIAG 移除 ✅ DEPLOYED
- P0-11 LIVE-GATE-BINDING-1（Python↔Rust HMAC `authorization.json` + 5min re-verify）→ Rust 可驗證門控 3→**4** ✅ DEPLOYED
- P0-12 LIVE-GATE-FALLBACK-1（純 Python，REST reduce_only 平倉降級）→ 待 uvicorn 重啟生效
- P0-7 ORDER-SUBMIT-GAP-1 ARCHIVED（RCA 證偽，P0-6 子問題）
- DYNAMIC-RISK-1（Sharpe-aware per-trade risk sizer）+ rustfmt sweep
- IPC-SCAN-1c（scanner opportunities via IPC）
- G-2 funding_arb v2 NEGATIVE 結案 + IPC tunable surface
- 工程日誌：`docs/worklogs/2026-04-18--{live_gate_binding_1,live_gate_fallback_1,dual_track_exit_design,p0_6_*}*.md`

**2026-04-17 SCANNER-GATE + PHANTOM-2-FUP + LIVE-GUARD-1 + STABILITY-1 RCA + DUST-EVICTION**：`docs/archive/2026-04-17--completed_todo_p0_scanner_phantom_live_guard.md`
**2026-04-16 STRATEGY-CLOSE-TAG-FIX + EDGE-P3-1 Phase B #3 + DEDUP-PY-RUST + PAPER-DISABLE-1**：`docs/archive/2026-04-16--completed_todo_strategy_close_tag_edge_p3_dedup.md`
**2026-04-15 W22 ENGINE-HEAL + EDGE-P3-1 + GUI Fills**：`docs/archive/2026-04-15--completed_todo_w22_engine_heal_edge_p3.md`
**2026-04-14 Phantom-Heal + Engine Self-Healing + EDGE**：`docs/archive/2026-04-14--completed_todo_w22_phantom_heal.md`
**2026-04-12 全程序鏈審計**：`docs/archive/2026-04-12--completed_todo_full_program_audit.md`
**W19/W20/Phase 6/3E-E2 Fix Rounds A-G**：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`
**3E-ARCH 三引擎並行**：`docs/archive/2026-04-11--completed_todo_3e_arch.md`
**Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4 收尾**：`docs/archive/2026-04-10--completed_todo_live_gui_dead_py.md`
**ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
**Session 11 之前**：`docs/archive/2026-04-06--completed_todo_archive_l3_phases.md`
**Phase 0/1/2/3 + Rust migration**：`docs/archive/2026-04-04--completed_todo_archive_phase0123_rust.md`
**已知問題清單**：`docs/KNOWN_ISSUES.md`
**Bybit API 字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（≤5）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`，新端點同步更新手冊。
**風控參數修改**：必須透過 IPC `patch_risk_config` 單一通道。

**腳本速查**（詳 `helper_scripts/SCRIPT_INDEX.md`）：
```
改了代碼需部署              → bash helper_scripts/restart_all.sh --rebuild
只想清交易所持倉             → bash helper_scripts/clean_restart.sh --yes
開發告一段落要清 PnL/勝率    → bash helper_scripts/fresh_start.sh --yes
臨時停機 debug              → bash helper_scripts/stop_all.sh
```
