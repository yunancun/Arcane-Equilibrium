# OpenClaw TODO — 工作清單

**最後更新**：2026-04-18 22:30 local
**Engine**：PID 2217378 · binary mtime 20:13 → 含 P0-6 永久修復 + LIVE-GATE-BINDING-1 + DYNAMIC-RISK-1 + IPC-SCAN-1c
**Python uvicorn**：自 04-16 未重啟 → **下次重啟即生效 P0-12 LIVE-GATE-FALLBACK-1**
  - 重啟後驗證：(1) GUI Close All Positions response 應含 `rest_fallback:true, errors:null` (2) engine.log 出現 `LIVE-GATE-FALLBACK-1: IPC close_all_positions channel unavailable ... (REST fallback — live pipeline not authorized)` (3) `python3 -c "from openclaw_core import BybitClient; print([(p['symbol'], p.get('size')) for p in BybitClient(environment='live_demo').get_positions('linear') if float(p.get('size') or 0) > 0])"` 應為空
**測試基準線**：Rust engine lib **1454** / core 380 / e2e 35 / reconciler_e2e 19 · Python **2898** passed / ml_training 182 passed

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

### Step 0 · W23 Day 1-3 可行性 Sprint（4 不確定全綠才推 Phase 1）

- [ ] **不確定 1**：`python -m program_code.ml_training.james_stein_estimator` 跑通 + 寫入 `settings/edge_estimates.json` non-empty → 機制 ✅ 但 grand_mean −2214 bps 不可 bind（P1-14）
- [ ] **不確定 2**：`decision_features` schema 對齊 7 維度（`est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs`）→ 至少 5/7 直接 derive
- [ ] **不確定 3**：per-strategy 樣本 ≥10k（至少 2 策略；`SELECT strategy, COUNT(*) FROM learning.decision_features WHERE engine_mode IN ('demo','live_demo') GROUP BY strategy`）→ fills RT 遠低閘口，Track L 範圍限縮（P1-13）
- [ ] **不確定 4**：tick-level price history 可重放 7d → 否則改「事後歸因 audit」（peak-to-exit 軌跡分析，非逐 tick replay）
- [ ] Sprint 產出：`docs/worklogs/2026-04-18-N--dual_track_exit_feasibility.md`（N=1/2/3）

### Phase 1 · W23 Day 4-7 — Track P 實作 + P1-7 解阻塞 A/B/C 並行

**軌道 1 Track P 物理層**：
- [ ] `peak_reached_ts_ms` 欄位加到 `PaperPosition`（含 legacy migration）
- [ ] `price_tracker` 加 `compute_roc(symbol, lookback_ms)`
- [ ] 7 維度規則 in `risk_checks.rs`（Priority 6 替換現有 COST EDGE，重命名 `PHYS-LOCK`）+ ConfigStore hot-reload
- [ ] Combine Layer 骨架（Track L 缺失時等同 P-only）
- [ ] E2 + E4：counterfactual replay audit（demo 7d）+ ≥18 單測（spike-wick 不誤觸 / 長期 winner 不誤砍 / 波動率歸一化邊界 / hot-reload / 早期寬容 / ML 缺席退化）
- [ ] E5：rebuild + 灰度部署（保守閾值，24h 無 fee 惡化才收緊）

**軌道 2 P1-7 解阻塞**：
- [ ] **A** Rust 接 `trading.intents` 持久化（定位 DEDUP-PY-RUST Tier A stub 點 + 補 Rust 寫入 + 單測）
- [ ] **B** `james_stein_estimator` scheduler 啟用（每小時 cron + IPC hot-trigger）→ 僅寫檔，不 bind Rust cost_gate 直到 P1-10 修復 + grand_mean 翻正（P1-14）
- [ ] **C** `run_training_pipeline.py` 首跑 grid_trading → 產 `models/demo/grid_trading_exit_policy_v20260425.onnx`

**Phase 1 完成標準**：Track P 灰度 ≥48h `exit_source=Physical` 正常 + `edge_estimates.json` 每小時刷新 + 第一個 ONNX artifact + `trading.intents` live/live_demo 開始有 rows

### Phase 2 · W24 — Track L shadow + P1-10 並行

- [ ] Combine Layer 啟用 `ml_override_high=2.0`（不可達），只寫 `learning.decision_shadow_fills`
- [ ] 每日對比 P vs L 一致性（target ≥60%）→ 校準 `ml_confirm_threshold / ml_override_high / ml_veto_low`
- [ ] 每筆 `trading.fills` 寫入 `exit_source` 欄位（Physical / Hybrid-shadow / ML-shadow）
- [ ] **並行 P1-10** grid 過度交易 + ma_crossover R:R 不對稱（比 ML 重要 5 倍）

**完成標準**：shadow 一致性 ≥60% + P1-10 fee 佔比 <50% + 不對稱倍數 ≤1.5×

### Phase 3 · W25-W26 — Track L 灰度開啟

- [ ] `ml_override_high` 0.95 → 0.85 → 0.75（每階 1-2 週，需 Hybrid net edge 顯著 > P-only, p<0.1, n≥200 才下調）
- [ ] Hold-out control 5-10% 永跑 P-only（feedback bias 對照）

**完成標準**：`ml_override_high=0.75` 穩定 ≥1 週 + 累積 net edge 正向

### Phase 4 · W27+ — 持續優化常態

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
| **P1-4 首個 ONNX export** | 併入 Phase 1 Prereq C | 從此只在本章節推進 |
| **P1-7 A+B+C** | 併入 Phase 1 軌道 2 | P1-7 殘留 D Teacher / LinUCB / Bayesian / RL |
| **P1-10 STRATEGY-ASYMMETRY-1** | W24 並行，比 ML 重要 5× | P1-10 獨立追蹤工作項 |
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

### P1-5 · DEMO-REBOOT-PNL-RESET-1 — drawdown 跨重啟視角斷鏈 audit
- **現象**：`/tmp/openclaw/demo_state.json` 本輪 `initial=peak=current=747.56`、`total_realized_pnl=72.68`；但 24h `risk_verdicts` 仍見 91,798 條 `drawdown_breach: 92.2% > 25.0%`
- **問題**：state file 重啟被重 seed → 跨 session drawdown 被遮蔽。設計還是 bug？
- **下一步**：查 `event_consumer/paper_state_restore.rs` + `demo_state.json` 寫入路徑
- **影響**：P0-3 重評期 drawdown 真實軌跡 + 21d 穩定性判斷

### P1-6 · DEMO-BYBIT-SYNC-ORPHAN-1 — bybit_sync 倉位策略動不了 + Demo 死循環殘留
- **現象**：6 個 owner_strategy=bybit_sync（DOTUSDT/NEARUSDT/BLESSUSDT/ENAUSDT/AAVEUSDT/BTCUSDT）非本輪策略開
- **死循環機制**（P0-6 Live_Demo 已解但 Demo 殘留）：correlated exposure 70% > limit 65% → 0 new opens → 0 fills → seeded positions 無活躍策略 emit Close → exposure 不降 → 永遠超限。`risk_gate: correlated exposure 69-70% >= limit 65%` engine.log 證據；Guardian 17.8k Rejected verdicts `direction_conflict`
- **狀態**：P1-8 FUP `retriage_synthetic_owner` tick-level 已自主接管中，觀察一週（起算 2026-04-17）
- **若不消化**（一週後仍卡）後備方案：
  - 方案 A：查 `grep ORPHAN /tmp/openclaw/engine.log` + ORPHAN-ADOPT-1 Phase 2A adopt logic 是否處理 bybit_sync 來源
  - 方案 B：臨時調 `correlated_exposure_max_pct` 65→75 解死鎖（IPC hot-reload）
  - 方案 C：ORPHAN-ADOPT-1 Phase 2B 補 orphan close path（前置 G-1 R-02 Strategist）
- **注意**：`correlated_exposure_max_pct` config TOML=60.0 但 runtime=65.0（GUI hot-reload 修改過）

### P1-7 · LEARNING-PIPELINE-DORMANT-1 — 半殼學習管線
- **數據累積層 ✅**：`learning.decision_features` 1.65M rows · `risk_verdicts` 24h 1.54M
- **edge_estimates.json writer/reader 鏈 ✅（手動）**：2026-04-18 20:24 首次寫入 29 KB / 104 cells / `grand_mean=-2214 bps`；Rust startup 加載進 cost_gate。**缺 scheduler + hot-reload**（詳 §P1-14 bind blocker）
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

### P1-14 · EDGE-ESTIMATE-BIND-BLOCKED-1 — JS estimator snapshot 結構性負 edge 無法 bind cost_gate
- **現象**：Step 0 不確定 1 驗證 `settings/edge_estimates.json` 首次寫入成功（104 cells · grand_mean −2214 bps ≈ −22.14%/RT）
- **問題**：該 snapshot hot-reload 進 Rust `cost_gate_live`/`cost_gate_moderate` 會 100% fail-closed，回退 P0-6 方案 A 解鎖前的死循環
- **根因**：grand_mean 深負結構原因 = P1-10（grid fee 74% + ma_crossover 2.54× R:R 不對稱），非 estimator 機制缺陷
- **下一步**：(1) DUAL-TRACK Phase 1 軌道 2 B 僅啟 scheduler 寫檔 + PG UPSERT，**不綁定** Rust cost_gate 讀取 (2) P1-10 修復落地後重跑 estimator 看 grand_mean 是否翻正 (3) grand_mean>0 且 ≥2 策略 shrunk_bps>0 才開 binding
- **阻塞**：不阻 Live；阻 DUAL-TRACK Phase 1 軌道 2 B 完成判定 + Phase 5 cost_gate 重啟
- **關聯**：P1-10 STRATEGY-ASYMMETRY-1（必要前置）· DUAL-TRACK Phase 1 軌道 2 B · P0-3 Phase 5 edge 重評

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

### WATCHDOG-DNS-CLASSIFY-1 · 區分 DNS 斷線 vs 真 crash
- **背景**：P0-9 RCA 揭露停電誤分類為 ENGINE_CRASH；發生頻率低（年均 ≤3 次）
- **設計**：`engine_watchdog.py` 讀 engine.log 末 N=20 行 → 連續 ≥5 條 `Temporary failure in name resolution` / `HTTP transport error` / `connection refused` → 分類 `network_outage` 不計 strike；`panic` / `assertion` → `engine_crash` 正常 strike
- **工作量**：~2h（純 Python，不動 Rust）

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
| W23 | 05-12~16 | **DUAL-TRACK Step 0 + Phase 1**（Track P + P1-7 A/B/C）· P0-2 LG-1 起算 · G-7 · G-10 · LG-2/3 | ⬜ |
| W24 | 05-19~23 | **DUAL-TRACK Phase 2**（Track L shadow）· **P1-10 並行** · LG-4/5 · SEC-21 · QoL-2 | ⬜ |
| W25-W26 | 05-26~06-06 | **DUAL-TRACK Phase 3**（Track L 灰度）· EDGE-P3-1 產線化 · Phase 5 補強或重做（P0-3 判決後） | ⬜ |
| W27+ | 06-09+ | **DUAL-TRACK Phase 4**（retraining/Teacher/Embedding/Regime LSTM）· G-1 R-06 全 5 agent | ⬜ |

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
