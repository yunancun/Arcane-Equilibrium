# OpenClaw TODO — 工作清單

**最後更新**：2026-04-21（兩個 commits：(1) DUAL-TRACK-EXIT-1 Phase 1b Track P v2 非線性 giveback pure fn ✅ commit `aee96b9` — `physical_micro_profit_lock_v2` + `ExitConfig` + 31 單測；QC 反轉 Gate 1 語意 `edge <= floor → Hold`；(2) **GATE1-REVERSAL-1 hotfix A ✅** — v1 `risk_checks.rs` Priority 6 Gate 1 同步反轉 Lock → Hold 對齊設計意圖，3 tests rename + assert 反轉；engine lib **1816 passed / 0 failed** 不變。`GATE1-REVERSAL-1` 剩餘下一波：符號統一 + Priority 6 整體替換 v1 → v2 + ConfigStore 綁定 + replay 校準。先前：2026-04-20 EDGE-P2-2 Phase A `381c542` + EDGE-P2-3 Phase 1B-4.3/1B-5/FUP-4 全部結案；14 個完成項批量歸檔 → `docs/archive/2026-04-20--completed_todo_batch.md`）
**Engine**：PID 3029633 · binary mtime 2026-04-19 22:32 → 含全部先前 staged 修復（P0-6 永久修復 + P1-7 A INTENT-WRITE-GAP-1 + P1-7 B edge_estimator scheduler + P1-17 Winsorize + LIVE-GATE-BINDING-1 + DYNAMIC-RISK-1 + IPC-SCAN-1c + FILL-CONTEXT-LINKAGE-1 + EXIT-FEATURES-TABLE-1 Phase 1b + Plan N ai_budget dedup + E5-P1/P2 + E5-FN-2/3 + DISPATCH-RETRY-1 + MARKET-KLINES-STALE-1 + DUAL-TRACK Track P T1-T5 骨架 + PIPELINE-SLOT-1 Phase 1-4）+ **EXIT-FEATURES-TABLE-1 Phase 1b GAP-1**（commit `35808e9` apply_confirmed_fill 接線，待流量驗證）
**Python uvicorn**：PID 3029688（4 workers）· started 2026-04-19 22:33 → 含 P0-12 LIVE-GATE-FALLBACK-1 + E5-FN-3 AnalystAgent pilot + PIPELINE-SLOT-1 Phase 4 daemon-thread trigger
**PIPELINE-SLOT-1 live 驗證**：LiveAuthWatcher 22:33 啟動 `env=LiveDemo poll_interval_secs=5`；authorization.json 已由 Manual restart sentinel 清除；等 operator 走 GUI renew → 應 ≤1s 觀察到 Live pipeline 重生
**測試基準線**：Rust engine lib **1816**（+25 DUAL-TRACK-EXIT-1 Phase 1b v2 / Mac debug 跑出；Linux release 待 `--rebuild` 後驗證）/ bin 38 / core 392 / e2e 35 / reconciler_e2e 19 · Python **2866** passed（+9 E5-FN-3 + 2 DYNAMIC-RISK-STATUS-TEST-SIG-1 修復 83a0475 + 16 WATCHDOG-DNS-CLASSIFY-1 新測）+ audit 4 passed / ml_training 238 passed · **0 pre-existing fail**（DYNAMIC-RISK 已清）

> engine lib 1631 → 1770（+139）→ 1791（+21）差距 = 1B-4.1/4.2 · 1B-5 gate · 3 FUPs · 1B-4.3 funding drag · 1B-5 hot-reload · FUP-4（9 commits `0febdc3..a93dbda`）+ **EDGE-P2-2 Phase A + FUP #1-#7 `381c542`**（+13 OI tests + 8 FUP tests）。當前 engine binary PID 3029633（mtime 2026-04-19 22:32）**不含** `bd1a429` + `a2a791b` + `a93dbda` + `381c542`，下次 `--rebuild` 才會進入 runtime。
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

### Step 0 · W23 Day 1-3 可行性 Sprint ✅ 2026-04-18（歸檔 `docs/archive/2026-04-20--completed_todo_batch.md` §1）

**判決**：2/4 綠 + 1/4 黃 + 1/4 紅 → Phase 1 拆 1a/1b；Phase 2 shadow 原 W24 → **延後到 W25**。Sprint 產出 `docs/worklogs/2026-04-18-1--dual_track_exit_feasibility.md`。

### 🔴 Step 0 衍生新 TODO 項（Phase 1 前置）

- ✅ **MARKET-KLINES-STALE-1** 2026-04-18 commit `65acde6`（歸檔 §2）— paper/demo/live 三引擎 `market_data_tx` 並行化，DB kline 寫入恢復。
- ✅ **EXIT-FEATURES-TABLE-1** 2026-04-19 commits `6ea643e` · `c7171b2` · `35808e9`（歸檔 §3）— Phase 1b 全部接線 + GAP-1 `apply_confirmed_fill` 補接線 + R1 驗收 coverage=1.000 / 8 of 8 demo 平倉。Phase 1b 累積 ≥1 週 exit_features 後可校準 7 維閾值。**若未來 Track P T4 PHYS-LOCK 接線**：需重跑驗收 SQL 確認不漏接 `Physical` exit_source。
- [ ] **DECISION-OUTCOMES-DEAD-1**（P2）：`trading.decision_outcomes` 113k 條 `max_favorable/max_adverse` 全 NULL，寫入管線斷；可沿用此表取代 exit_features 或確認徹底 dead；RCA 決定方向。

### Phase 1a · W23 Day 4-7（Step 0 後立即啟動，不阻於 7 維）

**軌道 2 P1-7 解阻塞（完全不阻塞，優先推進）**：
- ✅ **A** 2026-04-18 commit `2a36a3f`（歸檔 §4）— Rust exchange 分支補 `persist_intent`；demo 29 intents / 32 Approved verdicts = 90.6% ratio 驗收。live_demo 驗證 pending（operator 重簽 `authorization.json` 後）。
- ✅ **B** 2026-04-19 commit `23b14ef`（歸檔 §5）— `edge_estimator_scheduler.py` daemon + routes；live_demo grand_mean −8.46 bps（n_cells=28）；僅寫檔，未 bind cost_gate（待 P1-16 ✅ + grand_mean>−50 + ≥2 策略 shrunk>0）。
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

**軌道 1 Track P 物理層骨架** ✅ 2026-04-19（歸檔 §6）：
- ✅ T1-T5 骨架 commits `88b4ef9`/`c7d6a6c`/`981840f`/`a963f0b`/`094d285`/`4feb17a` — `ExitFeatures`/`PhysicalDecision` 型別、`compute_roc`、`physical_micro_profit_lock` Priority 6、Combine Layer + `ExitSource` 4 tags、counterfactual audit CLI。
- ✅ E2 + E4 2026-04-19 22:48 — ≥47 單測（超達 ≥18 要求）；counterfactual 實跑 grid 141/4 hits mean −39.4 bps · ma 52/10 hits mean −95.2 bps，驗證「設計上保守」；工件 `docs/worklogs/2026-04-19-2--track_p_counterfactual_audit.md`。
- ✅ E5 2026-04-19 22:33 — rebuild + 灰度部署活化（24h fee 觀察）。
- [ ] `peak_reached_ts_ms` 欄位加到 `PaperPosition`（含 legacy migration）— Phase 1b 7 維累積後展開

**Phase 1a 完成標準**：P1-7 A/B/C 部署 + `edge_estimates.json` 每小時自動刷新 + `trading.intents` live/live_demo 開始有 rows + 第一個 ONNX artifact + Track P 骨架灰度 ≥48h `exit_source=Physical` 正常

### Phase 1b · W24（exit_features 累積）

- [ ] `learning.exit_features` 表建立 + Rust exit handler 寫入
- [ ] 累積 ≥1 週 exit_features 資料（W24 全週）
- [ ] 7 維度規則 bind 真實閾值（取代 Phase 1a 骨架預設）

**Phase 1b 完成標準**：≥2 策略 exit_features 累積 ≥1000 rows + 7 維閾值可由資料 calibrate

### Phase 2 · W25（原 W24，延後 1 週）— Track L shadow + P1-10 並行

**軌道 1 Track P 物理層**：
- [x] `peak_reached_ts_ms` 欄位加到 `PaperPosition`（含 legacy migration）— 2026-04-19 EXIT-FEATURES-TABLE-1 Phase 1b FUP（5 tests in paper_state/containers.rs）
- [x] `price_tracker` 加 `compute_roc(symbol, lookback_ms)`— 2026-04-19 同 wave（15 tests in openclaw_core::risk::price_tracker）
- [ ] 7 維度規則 in `risk_checks.rs`（Priority 6 替換現有 COST EDGE，重命名 `PHYS-LOCK`）+ ConfigStore hot-reload
  - ✅ **v2 pure fn 已落地 2026-04-21**：`exit_features::physical_micro_profit_lock_v2` + `ExitConfig` 7 欄位 + `non_linear_giveback_fn`（linear decay + floor bound）+ 31 單測（Gate 1 Hold 語意對齊設計）
  - 待做：Priority 6 替換 + ConfigStore ArcSwap 綁定 + 閾值由 counterfactual replay 校準
- [ ] Combine Layer 骨架（Track L 缺失時等同 P-only）
- [ ] E2 + E4：counterfactual replay audit（demo 7d）+ ≥18 單測（spike-wick 不誤觸 / 長期 winner 不誤砍 / 波動率歸一化邊界 / hot-reload / 早期寬容 / ML 缺席退化）
  - ✅ 單測 **31 個**（含 Gate 1-4 + 非線性單調 + 邊界 + serde + Gate 1→Gate 4 端到端）2026-04-21
  - 待做：counterfactual replay audit（demo 7d tick-level，Mac 做不了，待 Linux）
- [ ] E5：rebuild + 灰度部署（保守閾值，24h 無 fee 惡化才收緊）
- [~] **GATE1-REVERSAL-1 (P1，2026-04-21)** — 部分完成（hotfix A 已 commit）+ 剩餘下一波
  - ✅ **hotfix A 完成 2026-04-21**：v1 `risk_checks::physical_micro_profit_lock` Gate 1 `edge < floor → Lock` 反轉為 `→ Hold`（對齊 v2 + 設計文檔 §三 L108-111 + operator 意圖「防止剛有大於 fee 的微利就套離場」）；3 tests rename + assert 反轉（risk_checks 2 + position_risk_evaluator 1）；`phys_lock_gate1_low_edge` reason v1 不再 emit，下游 parse 路徑向後兼容保留；engine lib 仍 1816 passed / 0 failed
  - **Linux 端部署後觀察**：`--rebuild` 後 2-3d 對比 demo 平均持倉時長 / 單筆 close 盈利分佈 / Phase 5 edge 指標；`phys_lock_gate1_low_edge` 新 fills 應歸 0
  - **剩餘下一波 Priority 6 替換時做**：(1) 統一符號 Gate 1 `<` → `<=` / Gate 4b `>` → `>=` 對齊設計 (2) 把 Priority 6 從 v1 `physical_micro_profit_lock` + `PhysLockConfig` 切換為 v2 `exit_features::physical_micro_profit_lock_v2` + `ExitConfig` (3) ConfigStore ArcSwap 綁定 `ExitConfig` 支持 hot-reload (4) 非線性 giveback 3 參數（base/slope/floor）由 counterfactual replay（demo 7d）校準 (5) 下游 `on_tick.rs` t4_fix + `tick_pipeline::infer_source` + Python `parse_exit_tag` 的 `phys_lock_gate1_low_edge` 分支評估何時清理（需所有含此 tag 的歷史 fills 歸檔或過期後）

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

### ✅ P1-5 · DEMO-REBOOT-PNL-RESET-1 2026-04-20 commit `7cda4e4`（歸檔 §7）
- `peak_balance` 持久化（V018 `trading.paper_state_checkpoint`）+ restore clamp `max(restored, current)` + `reset_drawdown_baseline` IPC。封死「重啟洗 drawdown」fail-closed 繞過路徑。demo row `peak_balance=948.85` 已寫入；worklog `docs/worklogs/2026-04-20--p1_5_a2_drawdown_continuity_implementation.md`。

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
- **✅ 2026-04-20 grid cooldown audit（下一步 §1 結案）**：cooldown 健康、不是 cadence 問題，歸因 **per-trade fee drag**（結構性問題）
  - **Code path**：`GridTradingParams.cooldown_ms` serde default=60_000 ms；A3 trend-adaptive boost 1x-6x（`grid_trading.rs:517-542` `compute_trend_adjusted_cooldown`）
  - **TOML hygiene**：E5-P2-4 把 TOML 路徑打通（`strategies/mod.rs:993` `gt.cooldown_ms = p.grid_trading.cooldown_ms`）但三個 `strategy_params_*.toml::[grid_trading]` 仍缺 explicit `cooldown_ms` → 靜默走 serde default
  - **實測驗證（demo 24h BLURUSDT, 46 entries）**：min gap 120.3s / p10 123.7s / avg 471.8s → 60s base × 2x trend boost 生效；**0.7s「min gap」是先前混查 entry+close 的 artifact**（grid 平倉→反向開倉瞬間），entry-only 最小 120s 正常
  - **BLURUSDT 24h 結構**（47 entries + 46 closes = 93 grid fills）：fees **$2.48** / gross PnL **-$0.35** → **net -$2.83**；每 RT 需 ~$0.054 fee vs 實測 gross -$0.008/RT → **結構性 edge 問題，非 cadence**
  - **修復**：`strategy_params_{demo,paper,live}.toml::[grid_trading]` 補 explicit `cooldown_ms = 60000` + 中英註釋（零行為改動，純 hygiene，暴露先前隱式 default 讓 operator/audit 可見）
  - **拒絕 simple cooldown bump**：把 60s 提到 300s 雖可減 5x 交易頻率但同比例減 pnl/fee → net 不改善（gross edge 仍負）。真正修復方向 = EDGE-P2-3 maker order 降 fee 6.5 bps→~1 bps 或放棄 grid 策略改走更有 edge 的 entry
- **下一步**：(1) ~~grid cooldown audit~~ ✅ 結案 — 已補 TOML hygiene，cadence 無 bug，問題在 fee drag (2) ma_crossover SL/TP 比率 audit（ATR mult / R:R gate）(3) EDGE-P2-3 maker order 列為 P1-10 grid 唯一結構出路
- **與 DUAL-TRACK Phase 2 並行**：兩者修好 P0-3 才能乾淨重評；ma_crossover 若 2.54× 不能收斂到 ≤1.5× 應 disable 或等 R-02 Strategist 重評

#### 🧠 2026-04-19 推進推理鏈（compact-safe，survive-compact 用）

**⚠️ 起因**：2026-04-19 15:37 redeploy 後重查 R:R 不對稱，追蹤到以下結構事實：

1. **（2026-04-20 修正）legacy COST EDGE block 註解 ≠ 功能退場；MICRO-PROFIT-FIX-1 接手了 Priority 6**
   - `risk_checks.rs:245-259` 舊 COST EDGE gate block 已註解（DEPRECATED）
   - 新 PHYS-LOCK gate（`risk_checks.rs:129-165`）存在但依賴 `exit_features: Option<&ExitFeatures>`
   - `tick_pipeline/on_tick.rs:1456-1474` `evaluate_positions(...)` closure 目前傳 `|_| None` → PHYS-LOCK 永遠拿不到 features → 永遠 Hold
   - **但 MICRO-PROFIT-FIX-1 narrow-band gate（`ratio ≥ 0.20 & pnl ∈ [0.30%, 0.55%]`）正常運作**，close 時 `strategy_name` 仍寫 `risk_close:COST EDGE:...` 舊 label → DB grep `COST EDGE` 會命中 MICRO-PROFIT 輸出
   - 2026-04-20 24h 實測：demo 24 筆 + paper 12 筆 MICRO-PROFIT close，**100% 勝率 / +$4.68 / +$7.49**，是當前最重要的正 edge 安全網
   - Track P T4 `phys_lock_*` 實測 0 觸發（符合 ExitFeatures=None 設計）
   - **原稿 claim「0 條 COST EDGE close」有誤** — 是 prefix label 相同造成歸類問題，並非 Priority 6 空轉

2. **`trailing_activation_pct=0.8` 非 hardcoded**
   - `rust/openclaw_engine/src/config/risk_config.rs:518` `default_trailing_activation_pct() -> 1.0`
   - 三環境 TOML 獨立（已由 `feedback_env_config_independence.md` 記錄）：
     - `risk_config.toml:35 = 1.0` · `risk_config_demo.toml:35 = 0.8` · `risk_config_paper.toml:51 = 0.5` · `risk_config_live.toml:37 = 0.5`
   - **7d DB 查核 `trailing_stop` 觸發次數 = 0** → R:R 不對稱**非** trailing 主因

3. **DB 真實 R:R 不對稱主因（2026-04-20 refined）**：
   - ma_crossover asym 2.54× → 0.88：虧損側已縮小到比獲勝側小；但 win rate 從 64% 跌到 37.8%（37 exits）→ **問題變成「勝率」而非「不對稱」**，Track P T4 加速理由弱化
   - grid_trading asym 1.71× → 2.09× 惡化：fee drag 持續主導；需 P1-10 grid cooldown_ms / min holding time 結構修
   - MICRO-PROFIT-FIX-1 在 `risk_checks.rs` MICRO-PROFIT 分支（`pnl ∈ [0.30%, 0.55%]`）仍照常觸發，demo 24 + paper 12 closes/24h，100% 勝率 +$12.17 net → Priority 6 **未空轉**

**路線決策（user 已批 2026-04-19）**：

- **R1 先**（零成本，24-48h）：觀察 post-redeploy R:R / fee-drag / 退場分布，確認舊 COST EDGE 死後的自然 edge 軌跡
- **A**（接受）：MICRO-PROFIT-FIX-1 / COST EDGE / PHYS-LOCK 為主軸；下一步由 R1 決定
- **C**（延後）：`trailing_activation_pct` 調 1.5-2.0% + 縮 trailing_distance，**必須** MICRO-PROFIT 修完再動
- **B**（駁回，見 `feedback_env_config_independence.md`）：統一 paper/live/demo TOML 被駁回，三環境故意獨立

**Track P T4 wiring blocker（Phase 1b W24 排期中）**：
- `ExitFeatures` 8 欄位（`exit_features.rs:18-36`）需 builder：`est_net_bps` / `peak_pnl_pct` / `current_pnl_pct` / `atr_pct` / `giveback_atr_norm` / `time_since_peak_ms` / `price_roc_short` / `entry_age_secs`
- 需新增 `peak_reached_ts_ms` 到 `PaperPosition`（legacy migration），見 §DUAL-TRACK Phase 2 Track P 第 82 行
- **決策**：不搶進度，R1 觀察後若 R:R 持續惡化再考慮加速 T4 wiring；否則按 W24 排期

**R1 觀察 SQL 模板**（每 6h 跑，對比 redeploy 前 24h baseline）：`strategy_name` 既是 entry 策略也是 close reason（無 owner_strategy 欄位）。查詢改用 `strategy_name LIKE 'strategy_close:%'` / `'risk_close:%'` / `'stop_trigger:%'` / `'ipc_%'` 等 prefix，見下方 2026-04-20 R1 實跑 SQL（24h bucket by strategy_kind）。

**R1 驗收 ✅ 2026-04-20 00:55 local（24h 窗口實測，redeploy 2026-04-19 22:32 local）**：

| engine | kind | n | win_rate | asym | total |
|---|---|---:|---:|---:|---:|
| demo | ma_crossover | 37 | **0.378** | **0.88** | −$6.39 |
| demo | grid_trading | 98 | 0.531 | **2.09** | −$9.72 |
| demo | risk:cost_edge_micro | 24 | 1.000 | — | **+$4.68** |
| demo | risk:trailing | 2 | 1.000 | — | **+$13.22** |
| demo | risk:fast_track | 7 | 0.571 | 1.16 | +$0.59 |
| demo | risk:dynamic_stop | 1 | 0.000 | — | −$10.41 |
| paper | grid_trading | 34 | 0.235 | 1.80 | −$10.80 |
| paper | risk:cost_edge_micro | 12 | 1.000 | — | +$7.49 |
| live_demo | ma/grid | 8 | 0.625 | — | +$0.70（樣本太小） |

**關鍵判讀**：
- **ma_crossover asym 2.54× → 0.88 翻轉**（虧損側現在比獲勝側小），但 win rate 64%→37.8% 崩 → R:R 題目變成「勝率問題」非「不對稱問題」。Track P T4 加速理由弱化。
- **grid_trading asym 1.71× → 2.09× 惡化**。fee drag 持續主導，P1-10 grid cooldown audit 仍為 P0-3 edge 重評阻塞。
- **Track P T4 phys_lock 0 觸發**（符合：`on_tick.rs:1456-1474` `evaluate_positions(..., |_| None)` 導致 PHYS-LOCK 拿不到 ExitFeatures，永遠 Hold）。
- **⚠️ P1-10 推理鏈 §1 「redeploy 後 `trading.fills` 0 條 COST EDGE close」claim 不成立**：24h demo 24 + paper 12 COST EDGE close 真實發生，都是 MICRO-PROFIT-FIX-1 narrow-band `ratio ≥ 0.20 & pnl ≥ 0.30%` 輸出（`risk_checks.rs` MICRO-PROFIT 分支仍寫 `strategy_name="risk_close:COST EDGE:..."` 重用 label）。**Priority 6 未真空**，MICRO-PROFIT gate 吸收了舊 COST EDGE 的 winner-pick 功能（demo +$4.68 / paper +$7.49 / 24 + 12 fills 100% 勝率），是當前最重要的正 edge 來源。
- **MICRO-PROFIT + trailing combined 輸出**：demo +$18.49 / 24h（+$6.68 fast_track/cost_edge_micro + $13.22 trailing − $10.41 dynamic_stop outlier）。基礎策略 −$16.11 / risk_close +$7.39 → demo 24h 總 net **−$8.72**。

**判決**：
1. Track P T4 wiring **按 W24 排期不加速**（asym 已翻、phys_lock 0 fire 符合設計）。
2. P0-3 edge 重評**仍推遲** — grid fee drag + ma win rate collapse 需要 P1-10 結構性修復（grid cooldown_ms + ma SL/TP 重設），而非退場層補救。
3. P1-10 推理鏈 §1 需更正（上方 inline 已改述）；MICRO-PROFIT-FIX-1 label reuse 應註釋到 §二 推理鏈，避免後續誤判。

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

### ✅ P1-15 LEARNING-SCHEMA-QUALITY-1 2026-04-18 commit `b0df1b3`（歸檔 §8）
- `commands.rs:668` 加 `risk_close:ipc_close_symbol` 前綴 + `realized_edge_stats.py:238` allowlist 加 `live_demo`。清 28 phantom cells（18 ipc + 10 risk_check），live_demo grand_mean −14.97 bps。真實 grand_mean 毒源由 P1-16/17 解。

### ✅ P1-16 HALT-SESSION-CROSS-SYMBOL-PRICE-CORRUPTION-1 2026-04-18 commit `fef688e`（歸檔 §9）
- 雙管修復：(Rust) `on_tick.rs` HaltSession 改用 `close_position_at_symbol_market` helper，斷絕 triggering tick 價格跨 symbol 汙染；(Python) `_pair_round_trips` 加 price-jump gate `|ln(exit/entry)| > 0.5` skip + 分母托底 `max(entry_notional_full, match_notional)`。demo 6616 fills → 5129 pairs，27 skips / 0 clamps / mean **−9.02 bps**（vs 修前 −2214，**245× cleaner**）；engine lib 1499 / ml_training 238 passed。

### ✅ P1-17 JS-ESTIMATOR-WINSORIZATION-1 2026-04-18（歸檔 §10）
- `_WINSORIZE_BPS=5000` + `_winsorize_bps()` helper + clamp counter；demo 30d archived grand_mean **−2214 → −78.38 bps**（19 clamps）。P1-16 上游修好後 Winsorize 退為 safety net 第三線。ml_training 217 passed。

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
- ✅ **LLM-ABC-MIGRATION-1** 2026-04-20 — 5 call-site 遷至 `local_llm_factory.get_local_llm_client()`（`ai_service.py` / `strategy_wiring.py` / `layer2_engine.py` / `layer2_routes.py` / `layer2_tools.py`）。新 `app/local_llm_factory.py` + `LMStudioShimClient` 暴露 OllamaClient-shape 介面（`.generate/.chat/.classify/.judge_edge/.is_available[_async]/.config/.model`）回傳 `OllamaResponse`，call-site 0 parsing 變動。`LOCAL_LLM_PROVIDER=ollama`(預設)/`lm_studio` 切換，未知值 fallback Ollama。17 個新 pytest（env 切換/heavy 變體/surface 對齊/fail-soft HTTP/classify & judge_edge 代理/singleton 語義）+ 11 個既有 patch-target 更新 + 1 訊息文案對齊。變數名 `_OLLAMA_CLIENT`/`OLLAMA_CLIENT` 保留 §九 grep 穩定。grep 驗證：business code 0 `import OllamaClient`。**Mac operator 設 `LOCAL_LLM_PROVIDER=lm_studio`+`LM_STUDIO_BASE_URL` 即可不裝 Ollama 跑 Layer 2。**

### QoL & 設計債
- [ ] **QoL-2** Demo AI cost 追蹤（`tab-demo.html` 硬編碼 'N/A'，依賴 G-1 H1-H5）
- [ ] **DUST-EVICTION GUI 曝光**（P1-8 FUP）：log-only 觀察滿一週後（起算 2026-04-17）→ GUI 曝光 `dust_frozen` / `orphan_frozen` 倉位給 operator 日報；`paper_state.rs` 已有 `TriageOutcome.dust_frozen` 計數器
- [ ] **LEARNING-COCKPIT-NO-IPC-1** Learning 8 端點走 Python state_store 非 Rust IPC（設計債，等 G-7/G-10 後再議；不阻 Live，原則 #7 學習平面與 Live 隔離）
- ✅ **DYNAMIC-RISK-STATUS-TEST-SIG-1** 2026-04-19 commit `83a0475`（歸檔 §11）— `TestClient(app).get(...)` 走 HTTP dispatch + `Authorization: Bearer` header 規避兄弟測試 `importlib.reload` swap。2 tests pass。
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
- ✅ **E5-FN-2 Plan N** 2026-04-19 commit `f0f11c0`（revert `87b7653`；歸檔 §12）— 用既有 hypertable PK `(time, scope, request_id)` + `ON CONFLICT DO NOTHING RETURNING 1` 取代 V018 partial UNIQUE（TimescaleDB hypertable 不接受不含 partitioning column 的 UNIQUE index）。零 schema/migration。
- [ ] **E5-FN-2-PLAN-N-FUP** — Plan N 部署後 follow-up：(a) Python Layer-2 sync caller 可選升級為傳入 `(request_id, event_time_ms)` 以獲得跨重試的真實去重（目前 IPC handler 本地鑄造時每次 retry 會被當新 row — 仍不會雙重計費本地 caller 自己，但失去跨 Python 重試保護）；(b) `test_make_request_id_unique_within_same_ms` 為 1 對 mint 對比，flake 機率 ~1/2^32，若 CI 偶發誤報換 seeded RNG；(c) 部署後 `SELECT time, scope, request_id, COUNT(*) FROM learning.ai_usage_log GROUP BY 1,2,3 HAVING COUNT(*) > 1 LIMIT 5;` 應永遠 0 rows（PK 保證）。

### 跨平台 / Mac 部署準備

#### PYO3-ELIMINATE-1 · PyO3 surface 歸零（3 phase）📦
- **動機**：Mac (M5 Max) 本地開發 + Linux 部署短期雙軌 → 未來 M5 Ultra 完整遷移。PyO3 cdylib 是**唯一**跨平台 ABI 耦合點；消除後 Rust binary + Python source 完全正交，CI wheel pipeline 可關閉。符合憲法 §一 #2 讀寫分離（PyO3 實質繞過 IPC 邊界）。
- **盤點結果**（2026-04-20 grep `#[pyclass]` / `from openclaw_core`）：
  - `openclaw_pyo3` crate 共 1426 LOC / 3 暴露對象
  - `ContextDistiller` + `NotableEvent`（228 LOC）— **0 Python call sites** 💀
  - `HedgingEngine` + `HedgeRecommendation` + `Position`（285 LOC）— **0 Python call sites** 💀
  - `BybitClient`（bybit_bridge/ ~880 LOC）— **3 call sites**：`strategy_ai_routes.py:46` / `live_session_routes.py:220` / `helper_scripts/clean_restart_flatten.py:35`
- **前置**：無阻塞，可隨時啟動。**不阻 Live Gate**（Mac 遷移是 Live 後長期工作）。

**Phase 1 · 刪死代碼（~30 min，零風險）✅ 2026-04-20（待 commit）**
- [x] 刪除 `rust/openclaw_pyo3/src/context_distiller.rs`（228 LOC）
- [x] 刪除 `rust/openclaw_pyo3/src/hedging_engine.rs`（285 LOC）
- [x] 從 `rust/openclaw_pyo3/src/lib.rs` #[pymodule] 移除對應 `add_class` 註冊（5 行）
- [x] 驗證：`cargo build -p openclaw_pyo3 --release` 綠（16.12s，warnings 為預存 openclaw_engine dead_code）
- [x] pytest 全量綠（合併 Phase 2 一起跑）
- [x] commit `a84ecdb`：`refactor(pyo3): PYO3-ELIMINATE-1 Phase 1 — drop dead ContextDistiller + HedgingEngine (513 LOC, 0 call sites)`

**Phase 2 method surface 實測**（2026-04-20，Python 實際使用的 BybitClient method）：
- **Read-only（9）**：`has_credentials()` `base_url()` `instrument_count()` `refresh_balance()` `refresh_instruments(category)` `get_instrument(symbol)` `get_positions(category)` `get_active_orders(category)` `get_executions(category, limit)`
- **Write（3）**：`round_qty(symbol, qty)` · `place_order(...)` (LIVE-GATE-FALLBACK-1 reduce_only close) · `BybitClient(environment=...)` ctor
- **決策**：Option A httpx — `place_order` reduce_only 必須繞過引擎走 REST（根原則 #6），其他 11 個 method 一起走 httpx 保持接口一致；IPC 方案會破壞緊急平倉路徑的「繞過引擎」語意。

**Phase 2 · `BybitClient` 3 call sites Python 化 ✅ 2026-04-20（待 commit + E2 審）**
- [x] 先分析 3 call sites 實際調用的 `BybitClient` 方法集（12 methods + 1 `cancel_order` 盤點；spec 詳見 `docs/worklogs/2026-04-20--pyo3_eliminate_phase2_migration_spec.md`）
- [x] 決策：Python httpx 重寫（理由：`place_order` reduce_only 必須繞引擎走 REST，所有 method 統一走 httpx 最一致；無 WS 需求）
- [x] 實作：`program_code/.../app/bybit_rest_client.py` 914 行（457 code + 357 doc + 140 blank）+ 40 unit tests（0.53s 綠）
- [x] Parity harness：`tests/test_bybit_rest_client_parity.py` 23 tests（15 Mode B passed + 8 Mode A skip 因 PyO3 cdylib 未裝 venv）+ 8 Bybit V5 fixtures
- [x] 3 call sites 遷移完成：`strategy_ai_routes.py`（singleton factory 重命名 `_RUST_BYBIT_CLIENT` → `_BYBIT_CLIENT`）· `live_session_routes.py:220` · `helper_scripts/clean_restart_flatten.py`
- [x] grep `from openclaw_core` 生產代碼 0 match（剩 docs/spec/archive/Rust 內部 `rust/openclaw_core` crate ref — 預期）
- [x] pytest control_api 全量 **2647 passed / 6 skipped / 0 failed**（63.50s）
- [x] E2 對抗性審查 APPROVE_WITH_NITS（0 CRITICAL，見 `docs/audits/2026-04-20--pyo3_eliminate_phase2_e2_review.md`）
- [x] commit `0f8220b`：`refactor(connector): PYO3-ELIMINATE-1 Phase 2 — migrate BybitClient callers to httpx`

**Phase 3 · 拆 crate + 清工具鏈 ✅ 2026-04-20（待 commit）**
- [x] 刪整個 `rust/openclaw_pyo3/` 目錄（`git rm -rf`，8 檔 ~918 LOC）
- [x] `rust/Cargo.toml` 移除 `openclaw_pyo3` member
- [x] `rust/Cargo.toml` 移除 workspace `pyo3` 依賴
- [x] 刪 `helper_scripts/build_pyo3.sh`（`git rm`）
- [x] 修 `helper_scripts/clean_restart.sh` / `fresh_start.sh` `SRC_DIRS` 移除 `openclaw_pyo3/src`
- [x] 修 `helper_scripts/restart_all.sh --rebuild` 移除 `rebuild_pyo3()` function + 呼叫（只剩 `cargo build --release -p openclaw_engine`）
- [x] 更新 `README.md`（架構圖 4→3 crates、亮点、build 表移除、restart_all 旗標說明）+ `SCRIPT_INDEX.md` + CLAUDE.md §九 singleton 表（`_RUST_BYBIT_CLIENT` → `_BYBIT_CLIENT`）
- [x] 驗證：`cargo build --release -p openclaw_engine` 11.14s 綠 + `cargo test --lib` 1791 passed / 0 failed + pytest bybit_rest_client 58 passed / 5 skipped
- [x] commit `9b691a0`：`chore(rust): PYO3-ELIMINATE-1 Phase 3 — drop openclaw_pyo3 crate + build pipeline`

**完成標準**：
- `cargo.toml` 零 pyo3 依賴
- `rg '#\[pyclass\]|from openclaw_core'` 零結果
- CI matrix 無 maturin/wheel step
- engine lib + pytest 基準線不回退
- Mac 上 `cargo build` 僅產 binary，無 .so/.dylib

**遷移收益量化**：
- 移除 1426 LOC PyO3 code
- 移除 `maturin` / `cibuildwheel` 跨平台 wheel 管道需求
- CI build time 估計 -2~3 min（省掉 pyo3 cdylib link）
- Mac 跨平台阻力：PyO3 wheel cross-compile（唯一硬骨頭）→ 消失

**風險與退路**：
- Phase 1：零風險（刪的是 0 call site 代碼）
- Phase 2 風險：httpx 與 Rust `reqwest` 在 Bybit V5 簽名/timeout/retry 行為差異 → 退路 = 改走 IPC（Rust 側邏輯無改動）
- Phase 3 風險：清理遺漏（script 殘留 PyO3 路徑）→ 退路 = CI 會立即爆

### ✅ E5-FN-3-FUP · 全 5 Agent audit_callback wiring 2026-04-19（歸檔 §14）
- FUP-a Strategist / FUP-b Guardian / FUP-c Executor / FUP-d Scout 全 4 agent 接 audit_callback + 3 NITs（log throttle 60s / unknown event_type default / thread-safety 文檔）全綠；新測 2+6+3+8=19 integration tests。5 agent 完成後 `change_audit_log` 可驗 `who IN ('ScoutAgent','StrategistAgent','GuardianAgent','AnalystAgent','ExecutorAgent')`。

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
- 🟢 **EDGE-P2-2** OI + Liquidation 信號源（給 bb_breakout 加領先信號）
  - [x] **OI signal — bb_breakout confluence 調製（Phase A）** — WS `tickers.openInterest` 解析 + `PriceEvent.open_interest` 欄位 + 每 symbol 滾動 buffer + `oi_delta_pct` → `confluence_score` ±bonus（預設 `enable_oi_signal=false`，與基線 bit-identical）；E2 7 findings 全修：#1 dedup + #2 on_rejection 保留 buffer + #3 `oi_min_delta_pct` noise floor + #4 TOML factory validate_oi fallback + #5 window 上限 600000ms + #6 ts monotonic guard + #7 bonus 典型區間 docstring；engine lib **1791 passed**（baseline 1770 +21）
  - [ ] **Liquidation signal — Phase B（待 OI signal demo 驗證後啟動）**
- 🟡 **EDGE-P2-3** Maker order 支持（5.5 bps → ~1 bps/side）
  - [x] **Phase 1A** PostOnly maker 入場管線（grid_trading demo/paper；live off）— `24f28a1` `7178d63`
  - [x] **Phase 1B-1** `BybitRetCode` enum + `cancel_order_by_link_id` helper — `16b69fa`
  - [x] **Phase 1B-2** WS `rejectReason` 捕獲 + 分類（僅 observability）— `86b568f`
  - [x] **Phase 1B-3** `maker_limit_timeout_ms` + `PendingOrder` order_type/tif + sweep cancel — `4c35616` `89805e7`
  - [x] **Phase 1B-4.1/4.2** Paper resting-limit queue + touch-based Limit fill + 3 bias guards — `0febdc3` `6b02e49`
  - [x] **Phase 1B-5** `maker_net_edge` metric + **MakerKpi gate**（Cold/Healthy/Degraded）— `1c79c6b`
  - [x] **3 FUPs** — `a3744fa`（clear_resting_limit_orders 重置 maker_stats）· `bf75986`（KPI staleness window 時間衰減）· `94810b4`（Kahan summation + cancel route 統一 via 1B-1 helper）
  - [x] **Phase 1B-4.3** funding drag（bias guard #3）— `bd1a429`（PostOnly draft 打標 `funding_rate_at_submit`；sweep 分類 FillPartial 時若 `|rate| > threshold` 且逆向持倉 → FundingDragSkip 保留掛單；bias #1 same-tick Keep 優先）
  - [x] **Phase 1B-5 hot-reload** `MakerKpiConfig` 閾值 via ConfigStore — `a2a791b`（IPC 寫入面 + `sync_maker_kpi_config_if_changed` tick 頂部 sync + IntentProcessor 熱重載；零重啟）
  - [x] **E2 APPROVE_WITH_NITS + 5 FUP tests** — `a93dbda`（N1 `MakerKpiConfig::validate()` 4 不變量 + N2 `#[serde(default)]` on `funding_rate_at_submit` 升級安全 + N3 `deny_unknown_fields` 拼錯即失敗；FUP T1-T3/T5-T8/T10 共 8 新測試；engine lib 1762 → **1770 passed**）
  - [ ] **Phase 2+** live endpoint 啟用 · 其他策略（bb_breakout / ma_crossover / funding_arb）接 PostOnly · learning integration

---

## ⚪ P4 — Backlog / Conditional

### IP-DEDUP-1 · IntentProcessor 同幣種重發去抖
- **觸發條件**：P0-3 判決後 edge 仍負 + 重發率仍高才啟動
- **設計**：`HashMap<(symbol, is_long, strategy), (ts_ms, reason)>` + 60s 窗口；只去抖被拒 intent；config `risk.intent_dedup.enabled` + `dedup_window_secs=60`
- **預期**：DF 行數降 95% + cost_gate CPU/DB IO 減少 + counter `intent_dedup_skipped` 透明
- **工作量**：~1d
- **接手指南**：`intent_processor/mod.rs` evaluate_predictor_gate 上游；類似機制參考 `governor_cooldown` / `last_ai_call_time_ms`

### ✅ WATCHDOG-DNS-CLASSIFY-1 2026-04-20（歸檔 §13）
- `engine_watchdog.py` 新增 `classify_engine_failure()` + `on_engine_crash(log_path=...)` — tail 20 行連續 ≥5 條 DNS/HTTP transport 錯誤 → `network_outage`（不計 strike，不 auto-restart）；`panic`/`assertion`/`backtrace` → `engine_crash`。+16 unit tests，canary 38→54 passed。封死 P0-9 停電事件誤重置 21d 時鐘。

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

**2026-04-20 批次歸檔**（14 項）：`docs/archive/2026-04-20--completed_todo_batch.md`
- Step 0 可行性 Sprint · MARKET-KLINES-STALE-1 · EXIT-FEATURES-TABLE-1 Phase 1b + GAP-1 · P1-7 A(`2a36a3f`)/B(`23b14ef`) · Track P T1-T5 骨架（6 commits）· P1-5 DRAWDOWN-RESET(`7cda4e4`)· P1-15(`b0df1b3`) · P1-16(`fef688e`) · P1-17 Winsorize · DYNAMIC-RISK-STATUS(`83a0475`) · E5-FN-2 Plan N(`f0f11c0`) · WATCHDOG-DNS-CLASSIFY-1 · E5-FN-3-FUP 全 5 agent audit wiring + 3 NITs

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
