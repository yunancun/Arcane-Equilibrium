# OpenClaw TODO — 工作清單

**最後更新**：2026-04-24（**EDGE-DIAG-1 Phase 1+2+4 + EDGE-DIAG-1-FUP-IPC 完成** 於 02:06 CEST `--rebuild` 後 runtime live，commits `5b0908b` + `1a53400`；Phase 3 passive-wait 至 clean n≥200 ~2026-05-01；承襲 P0-13/14/15 三項結案歸檔 → `docs/archive/2026-04-24--completed_todo_batch.md` + 2026-04-23 WS-RETIRE-1 + DEDUP-PY-RUST A+B+C+D + INFRA-PREBUILD-1 A+B；PASSIVE-WAIT-HEALTHCHECK-1 check [11] daily cron 06:00 UTC）
**Engine**：PID **884467** · binary mtime **2026-04-24 02:06:24** · baseline HEAD `1a53400`（含 EDGE-DIAG-1-FUP-IPC 7 exit.* IPC 熱重載；承襲 WS-RETIRE + DEDUP A+B+C+D + INFRA-PREBUILD A+B + P0-13/14 + TRACK-P-V2-SWAP-1 + TICK-PIPELINE-MOD-SPLIT-1 + T4 + EDGE-P2-3 PostOnly + DECISION-OUTCOMES fix 等）
**Python uvicorn**：PID **884519**（4 workers）· 2026-04-24 02:06 CEST `--rebuild` 隨 engine 重啟；包含 P0-14 B JS proxy cells（43→135）+ P0-12 LIVE-GATE-FALLBACK-1 + E5-FN-3 + PIPELINE-SLOT-1 承襲
**PIPELINE-SLOT-1 live 驗證**：LiveAuthWatcher 跑中 `env=LiveDemo poll_interval_secs=5`；`authorization.json` 未簽（operator 待決定 live 啟動時機）
**測試基準線**：Rust engine lib **1939**（Mac + Linux release；2026-04-23 session 累積 +104 vs 1835 baseline）/ bin 38 / core 392 / e2e 35 / reconciler_e2e 19 · pytest **2996 / 0 fail / 1 skipped** · `tick_pipeline/mod.rs` **1012** 行（§七 1200 硬上限符合）

**健康**（post-rebuild 2026-04-23）：demo alive · paper disabled（PAPER-DISABLE-1 預期）· live not alive（auth 未簽預期）· 0 panics
**21d demo 時鐘**：起算 2026-04-16 22:16 local（P0-9 STABILITY-1 RCA 穩定點），目前 ~7d；計劃性 rebuild 不重置；目標 21d 解鎖最早 **2026-05-07**

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

### ✅ P0-13 / P0-14 / P0-15 三連 — 2026-04-22 23:35 CEST 部署 + 2026-04-23 24h+ runtime 驗收 PASS → **2026-04-24 歸檔 `docs/archive/2026-04-24--completed_todo_batch.md`**

- **P0-13** ATR-SCALE-BUG-1（`ff694e8`）：atr_pct demo 24h avg 0.243（預期 0.05-0.5 ✅）· giveback_atr_norm 1.108（預期 0.3-3.0 ✅）· phys_lock 24h=21（pre-fix 7d=0）
- **P0-14** EDGE-ESTIMATES-MISS-1（A `2484263` + B `9710ff9`）：Gate 1 `missing_edge_fallback_bps=-10.0` fallback pathway live；`edge_estimates.json` 162/162 cells；healthcheck [4] FAIL → PASS · [7] WARN → PASS
- **P0-15** COST-EDGE-DEPRECATION-MICRO-PROFIT-GAP-1（doc fix `2330360`）：§1-§2 文檔更正完成；§3 edge baseline 重跑併入 P0-3（PostOnly 1w 窗 ~2026-04-28 解鎖）
- **後續追蹤項（非 P0）**：`learning.exit_features.est_net_bps` 寫入時 100% NULL write-side gap — Gate 1 決策流已獨立工作（21 phys_lock fires），不阻 runtime；另案獨立 RCA

### 🔧 健康檢查基礎設施 / Healthcheck infra

- ✅ **PASSIVE-WAIT-HEALTHCHECK-1** 2026-04-22 commit `edc4a21` — 新 `helper_scripts/db/passive_wait_healthcheck.py`，單命令 READ-ONLY 檢查 7 個關鍵 pipeline（close_fills / label_backfill / exit_features_writer / phys_lock / micro_profit / trailing_stop / edge_estimates freshness）。Exit 1 = silent-dead 自動偵測。**2026-04-22 首跑結果：FAIL [4] + WARN [5][7]**（符合 P0-13/14/15 預期）。建議 operator cron 每 6h 自動跑。
- ✅ **CLAUDE.md §七 新規則** 2026-04-23 commit `b0b47b5` — 已加「被動等待 TODO 必附 healthcheck」4 條規則 + 3 情境例（21d demo / 7d replay / 1w PostOnly）。E2 必查 policy。

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

- ✅ **全章節結案**（5/5，2026-04-22）— 歸檔 `docs/archive/2026-04-22--step_0_derived_todo_batch.md`。內含：MARKET-KLINES-STALE-1（`65acde6`）/ EXIT-FEATURES-TABLE-1（`6ea643e`+`c7171b2`+`35808e9`）/ 2026-04-21 批次 14 項（另檔 `2026-04-21--completed_todo_batch.md`）/ TRACK-P-V2-SWAP-1（`306993e`）/ TICK-PIPELINE-MOD-SPLIT-1（`3d67a99`）。後續阻塞解除：Phase 1b Track P 待部署（operator 決定）+ counterfactual audit 校準 `ExitConfig` 非線性 giveback 參數。

### Phase 1a · W23 Day 4-7（Step 0 後立即啟動，不阻於 7 維）

**軌道 2 P1-7 解阻塞（完全不阻塞，優先推進）**：
- ✅ **A** 2026-04-18 commit `2a36a3f`（歸檔 §4）— Rust exchange 分支補 `persist_intent`；demo 29 intents / 32 Approved verdicts = 90.6% ratio 驗收。live_demo 驗證 pending（operator 重簽 `authorization.json` 後）。
- ✅ **B** 2026-04-19 commit `23b14ef`（歸檔 §5）— `edge_estimator_scheduler.py` daemon + routes；live_demo grand_mean −8.46 bps（n_cells=28）；僅寫檔，未 bind cost_gate（待 P1-16 ✅ + grand_mean>−50 + ≥2 策略 shrunk>0）。
- [ ] **C** `run_training_pipeline.py` 首跑 grid_trading（**範圍限 grid_trading 單策略 PoC**，詳 §P1-13 SAMPLE-FLOOR-GAP-1；ma_crossover ~380 RT / funding_arb ~38 RT / bb_reversion 1 RT / bb_breakout 0 RT 均低於 QA 守衛 ≥1000/策略閘口，Phase 1 其他策略走 Track P only；用 decision_features 17 維做 entry-decision 模型，不等 exit_features）→ 產 `models/demo/grid_trading_entry_policy_v20260425.onnx`
  - **2026-04-23 Target 改 grid_trading pooled（跨 symbol）**（commit pending — `PipelineConfig.symbol` Optional + `--symbol` 改 optional/`ALL` + per-strategy pooled readiness view + pooled/per-symbol 測試）：原逐 symbol 目標 `demo grid_trading BLURUSDT 47/200` 冷凍 3.5d（策略 2026-04-20 起停交易 BLURUSDT，輪動到 PENGUUSDT 15 / SPKUSDT 11 等）→ 單一 symbol 永遠到不了 200；改 **pooled** 跨所有 grid_trading demo symbol 合計 ~200+ labels 可立即訓練。模型架構 symbol-agnostic（17 feature 無 symbol_embedding，train_quantile_trio 只吃 feature/label matrix），pooled 安全。Per-symbol 路徑保留（為未來 ma/bb 單策略高 RT symbol 用）。`phase1a_c_readiness.py` 新加 Per-strategy pooled view 回答「總量夠不夠訓練」，per-slice view 保留。
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
- ✅ `peak_reached_ts_ms` 欄位加到 `PaperPosition`（含 legacy migration）2026-04-19 EXIT-FEATURES-TABLE-1 Phase 1b FUP 完成（`paper_state/containers.rs:85` 已驗證）

**Phase 1a 完成標準**：P1-7 A/B/C 部署 + `edge_estimates.json` 每小時自動刷新 + `trading.intents` live/live_demo 開始有 rows + 第一個 ONNX artifact + Track P 骨架灰度 ≥48h `exit_source=Physical` 正常

### Phase 1b · W24（exit_features 累積）

- ✅ `learning.exit_features` 表建立 + Rust exit handler 寫入 — 2026-04-19 EXIT-FEATURES-TABLE-1（`database/exit_feature_writer.rs` + `exit_feature_tx` channel @ `tasks.rs:446`，`INSERT INTO learning.exit_features` 運作中）
- [ ] 累積 ≥1 週 exit_features 資料（W24 全週）— 2026-04-19 起算，預計 2026-04-26 滿一週
- [ ] 7 維度規則 bind 真實閾值（取代 Phase 1a 骨架預設）— 待資料量足夠 + counterfactual replay audit 校準（見 Phase 2 軌道 1）

**Phase 1b 完成標準**：≥2 策略 exit_features 累積 ≥1000 rows + 7 維閾值可由資料 calibrate

### Phase 2 · W25（原 W24，延後 1 週）— Track L shadow + P1-10 並行

**軌道 1 Track P 物理層**（2026-04-21 post-rebuild 狀態）：
- ✅ **基礎設施**：`peak_reached_ts_ms` 欄位（PaperPosition + legacy migration）+ `price_tracker.compute_roc(symbol, lookback_ms)` 2026-04-19 EXIT-FEATURES-TABLE-1 Phase 1b FUP（5 + 15 tests）
- ✅ **v2 pure fn** 2026-04-21 commit `aee96b9`：`exit_features::physical_micro_profit_lock_v2` + `ExitConfig` 7 欄位 + `non_linear_giveback_fn`（linear decay + floor bound）+ 31 單測（Gate 1 Hold 語意對齊設計）
- ✅ **v1 Gate 1 Lock→Hold hotfix A** 2026-04-21 commit `d0f0c21`：3 tests rename + assert 反轉；對齊設計意圖
- ✅ **T4 runtime 接線** 2026-04-21 commit `e95c779`：替換 `tick_pipeline/on_tick.rs:1677` `|_| None` 為實際 closure；Priority 6 每 tick 評估；已在 20:44 CEST `--rebuild` 部署
- ✅ **Combine Layer 骨架**（INFRA-PREBUILD-1 Part A，2026-04-23 commits `6226b38`/`419bd34`/`83ece53`/`66b061f`/`74b678a`）— V021 migration（`trading.fills.exit_source` + `learning.decision_shadow_exits` hypertable）/ `shadow_exit_writer.rs` 全鏈接線 tasks→main→event_consumer→pipeline / `ExitConfig.shadow_enabled` flag（三 TOML，default false）/ `combine_layer::build_ml_inference_shadow` mock + `helpers::emit_shadow_exit_observation` / step_6 PHYS-LOCK path shadow-aware emit / `TradingMsg::Fill.exit_source` + trading_writer INSERT 寫入 / passive_wait_healthcheck [8] `check_shadow_exit_ratio` silent-dead guard。**Phase 1a 完全 dormant**（flag OFF → 0 emit、0 DB 行、fills.exit_source 除 PHYS-LOCK 外全 NULL）。operator Phase 2 啟動時 TOML/IPC flip `shadow_enabled=true` 即 live，無需 rebuild。engine lib **1905 passed**（baseline 1835 → 1905，+70）。
- [ ] **counterfactual replay audit**（demo 7d tick-level，Mac 做不了，待 Linux sub-agent 或 Operator）→ 校準 v2 `ExitConfig` 3 個非線性 giveback 參數（base/slope/floor）
- ✅ **`TRACK-P-V2-SWAP-1`** 2026-04-22 commit `306993e`：Priority 6 v1 linear → v2 non-linear + ExitConfig 熱重載（詳 Step 0 衍生項結案條目）
- [ ] **E5**：v2 swap 後 24h 灰度驗 fee 無惡化才收緊閾值

- ⚠️ Combine Layer 啟用 `ml_override_high=2.0`（不可達）+ `learning.decision_shadow_exits` 寫入 — **骨架 ready（INFRA-PREBUILD-1 A）**，改寫為「operator 將 `risk_config_demo.toml [exit] shadow_enabled = true`（或 IPC patch_risk_config）即觸發」。flip 後以 `helper_scripts/db/passive_wait_healthcheck.py` [8] 觀察 24h 是否有 row。
- [ ] 每日對比 P vs L 一致性（target ≥60%）→ 校準 `ml_confirm_threshold / ml_override_high / ml_veto_low`。shadow 啟用後用 `SELECT disagreed, COUNT(*) FROM learning.decision_shadow_exits GROUP BY 1` 比對。
- ✅ 每筆 `trading.fills` 寫入 `exit_source` 欄位（INFRA-PREBUILD-1 A，commit `66b061f`）— Phase 1a PHYS-LOCK → `Physical`，其他 close + 所有 open → NULL；Phase 2 shadow 啟動後 `decision_shadow_exits` 記錄 Hybrid/ML/Disabled 分布，fills 表仍只記實際採用決策（Phase 3+ Track L live 才會出現非 Physical）。
- [ ] **並行 P1-10** grid 過度交易 + ma_crossover R:R 不對稱（比 ML 重要 5 倍）

**完成標準**：shadow 一致性 ≥60% + P1-10 fee 佔比 <50% + 不對稱倍數 ≤1.5×

### Phase 3 · W26-W27（原 W25-W26，連帶延後）— Track L 灰度開啟

- [ ] `ml_override_high` 0.95 → 0.85 → 0.75（每階 1-2 週，需 Hybrid net edge 顯著 > P-only, p<0.1, n≥200 才下調）
- [ ] Hold-out control 5-10% 永跑 P-only（feedback bias 對照）

**完成標準**：`ml_override_high=0.75` 穩定 ≥1 週 + 累積 net edge 正向

### Phase 4 · W28+（原 W27+，連帶延後）— 持續優化常態

- ⚠️ 週 retraining cron + model registry + canary deployment — **model registry 骨架 ready（INFRA-PREBUILD-1 Part B，2026-04-23 commits `3c3a030`/`91288f1`/`9f6d4c5`/`061cb19`/`01085a6`）**：V023 `learning.model_registry` 表 + Python writer `model_registry.py`（hook 到 `run_training_pipeline.py` stage 5.5）+ Rust 讀 helper `ml::registry::resolve_latest_production_artifact` + `/api/v1/ml/model_registry|model_info|model_promote` (Operator gate) + canary rules draft `docs/references/2026-04-23--model_canary_promotion_rules_draft.md` + healthcheck [9] `check_model_registry_freshness`。**Phase 4 剩餘**：週 retraining cron driver（讀閾值 → 呼 `/model_promote`）+ Rust OnnxModelManager 整合 registry（目前只讀 symlink；需在 Phase 3+ SIGHUP handler 補呼 resolve_latest_production_artifact）。
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

### 🟡 EDGE-DIAG-1 · 2026-04-23 · Edge investigation infra（P1，主軸）

**動機（operator 2026-04-23）**：P0-14 B 部署後 healthcheck [4] 揭露 v2 Gate 1 在當前 edge 環境是 by-design noop —— 全 135 cells `shrunk_bps = -4.30 < floor 5.0`（v2.rs:292-294 hard short-circuit）→ Gate 4 (giveback lock) 永遠到不了 → phys_lock 7d=0 不是 bug 是設計。Operator 進一步擔憂「EDGE-P2-3 PostOnly 修復後 edge 很可能仍是負」（grid BLURUSDT 24h gross −0.008/RT vs fee −5.4/RT，PostOnly 降 fee ~9 bps/雙側，net 仍可能 −0.5 bps/RT 量級）。若 PostOnly 後仍負 → 證明策略結構性沒正 edge → 整個 phys_lock + MICRO-PROFIT 鎖利層全是 noop → 系統只剩 trailing/dynamic 兩個被動止損層，本質是「逐步少賠」非「累積邊際正利」。

**核心矛盾**：當前設計假設「策略有正 edge → 退場層幫鎖利」；真實是「策略無正 edge → 退場層只能減損失」。等 edge 翻正才允許 Lock 在沒有 edge 翻正路徑時是死循環。

**短期 · 對照實驗**（今天執行；零 rebuild 成本）：
- [x] **2026-04-23 部署**：`risk_config_demo.toml` 加 `[exit] missing_edge_fallback_bps = 10.0`（> floor 5.0）
- 預期效果：sync-label 倉位（grand_mean 來源、`est_net_bps=None`）→ Gate 1 過 → 進 Gate 2-4 評估；grid/ma cells（raw `shrunk_bps=-4.30`）→ 仍走 Gate 1 Hold（對照組）
- 24-48h 後對比：sync-label 組 phys_lock fire 後 net **vs** 同組 trailing/dynamic 平均
  - 若 sync-label fire 後 net 更好 → 證明「鎖利機制有效，只是需要弱先驗繞過 Gate 1」→ 永久放開 fallback / 重評 floor
  - 若 sync-label fire 後 不如被動止損 → 證明「v2 設計在當前 edge 環境就是錯的」→ EDGE-P2-3 後也別期待 phys_lock 有用，整個 Track P 物理層需重評

**中期 · Edge discovery diagnostic suite**（24-48h 內可建）：

新建 `helper_scripts/db/edge_diagnostics.sh`，把 healthcheck 從「pipeline 活著嗎」升級到「edge 為何負，在哪裡漏」5 張表：

| # | 表 | 答的問題 |
|---|---|---|
| 1 | (engine_mode, strategy, symbol) 24h **gross / fee / slippage / net** 拆解，按 net 排序 | 哪些 (策略×symbol) 是 edge 黑洞？哪些有救？ |
| 2 | 7d 連續 net < 0 的 symbol kill-list candidate | 該下架哪些 symbol？ |
| 3 | **Counterfactual exit replay**：對 7d close_fills，模擬「在 peak − 0.3 ATR 鎖定」net 改善值 | phys_lock 真開了會贏嗎？（pure SQL/Python on `learning.exit_features`，零部署）→ ✅ 2026-04-23 `helper_scripts/db/counterfactual_exit_replay.py`（Linux trade-core 執行；`--cost-model both` 雙模型並列，proxy 代數退化保留 sanity check、fee_only 為經驗有效模型；`--include-funding-arb` opt-in；v2 non-linear + Gate 1/2/3 parity 為 FUP） |
| 4 | **holding time × net edge** 分桶（30s/5m/30m/2h/8h+） | 最佳持倉長度多少？是不是該強制 max_hold？ |
| 5 | cells `shrunk_bps` 7d trend + 距 floor 的 gap | EDGE-P2-3 部署後是否真在收斂？多久能過 floor？ |

#3 是回答「PostOnly 後 edge 仍負怎辦」的關鍵 — 若 counterfactual 顯示 phys_lock 鎖也救不了，**整個 DUAL-TRACK Track P 物理層需要重新評估**，不是調參數的事。

**執行順序**：短期實驗已部署 → 等 24-48h 樣本 → 並行寫 #3 counterfactual replay → #3 結果驅動 #1/2/4/5 是否做。
- Operator 執行：`ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/counterfactual_exit_replay.py --days 7 --cost-model both"` → 讀 VERDICT（`fee_only` 模型為主）

**2026-04-24 Phase 1+2 完成 + 主要 findings**（QC/FA/FM/PM 多角色審議 + 2 輪 adversarial review）：

✅ **Phase 1 完成 commit `5cabfd9`** — 加 5 flag + 168-LoC sibling `counterfactual_v2_parity.py`：
  - `--v2-parity` (v2 4-Gate + 7 sensitivity overrides) · `--exclude-close-tag '%risk_close:%'` 默認 ON（FA category-error）· `--split-window` 4-bucket (pre-T3 / T3-T4-vacuum / post-T4-pre-P013 / **post-P013-clean**) · `--bootstrap-ci` + `--per-strategy-median` + `--trimmed-mean-pct` · `--peak-sanity-histogram`
  - script 684 → 1235 行（略超 §九 1200 soft warn，sibling 分拆後合 1403；bilingual MODULE_NOTE + exhaustive CLI help 所致，進一步 trim FUP）

✅ **Phase 2 完成 2026-04-24 23:00 UTC** — v2-parity + 4-bucket rerun on 7d window 揭露：

| Bucket | n | cf_fired | improv_avg (bps) | actual_avg (bps) |
|---|---:|---:|---:|---:|
| pre-T3 | 0 | 0 | — | — |
| T3-T4-vacuum (4/19–4/21) | 89 | 76 | **+239.64** | +9.21 |
| post-T4-pre-P013 (4/21–4/22 21:35) | 14 | 11 | +60.06 | −22.31 |
| **post-P013-clean** (4/22 21:35+, ~30h) | **74** | **37** | **+11.95** | −3.72 |
| **ALL pooled** | 177 | 124 | +155.77 | +1.31 |

**重大發現**：
1. **FA H3 MICRO-PROFIT vacuum hypothesis ✅ 強確認** — vacuum +239 bps / clean +12 bps = **20x**；**+223 bps 首跑結果 90% 是 vacuum contamination**，不是 phys_lock 真實效益
2. **PM P0-13 ATR pollution hypothesis ✅ 確認** — post-T4-pre-P013 +60 / clean +12 = 5x；ATR scale bug 另疊 5x 放大（pre-fix `atr_pct` 下 scale 100-1000x，`giveback_atr_norm` 上 scale 200-400x）
3. **真實 clean signal = +11.95 bps/exit** (37 fires, 89.2% pos) — 方向對但 magnitude 遠低於 FM 預測 (+250-450 bps)
4. **orphan_frozen clean window = 0 rows**（FA 強 fit 候選無 clean 資料；outlier HIGHUSDT +3551 Δ 在 vacuum bucket）
5. **Option A `missing_edge_fallback=10.0` 已 deploy 且 loaded**（TOML mtime 20:07 < engine start 21:12，B1 驗證），Gate 1 fallback 對 sync-label 已生效
6. **QC 揭露**：CLAUDE.md §三「`ExitConfig` hot-reload 可調」claim **過期** — IPC handler 無 `exit.*` 欄位，實際需 TOML + `--rebuild`（新 P2 debt EDGE-DIAG-1-FUP-IPC）

### 🟡 EDGE-DIAG-1 後續（Phase 3 延後 / Phase 4 active）

- [ ] **Phase 3（延後，等資料）** — strategy-scoped Gate 1 fallback 部署決策
  - **前提條件**（必須 ALL 滿足才進）：(a) post-P013-clean bucket ≥ 200 rows pooled，或 per-strategy ≥ 50 cf_fired；(b) ma_crossover + grid_trading bootstrap 95% CI lo > 0；(c) orphan_frozen clean 樣本 ≥ 20 rows（FA 強 fit 候選必須獨立驗證）
  - **當前**（2026-04-24）：clean rows 74（grid 44 / ma 24 / bb 2 / orphan 0 / bb_breakout 0）遠不足；按 ~2.5 rows/h 速率，至 200 rows 預估 ≥ 5 天（~2026-05-01）
  - **healthcheck**（CLAUDE.md §七 強制）：`passive_wait_healthcheck.py` check [10] `check_counterfactual_clean_window_growth`（下 Phase 4 實作）
  - **Kill switch**：未來部署後用 `ssh trade-core "sed -i 's/missing_edge_fallback_bps = 10.0/missing_edge_fallback_bps = -10.0/' settings/risk_control_rules/risk_config_demo.toml && bash helper_scripts/restart_all.sh --rebuild"`；< 60s 可逆需先解 EDGE-DIAG-1-FUP-IPC

- [x] **Phase 4 ✅ 2026-04-24 commit `5b0908b`** — daily cron counterfactual monitor live
  - `check_counterfactual_clean_window_growth` as `passive_wait_healthcheck.py` check **[11]**（[10] 被 intents_writer_ratio 佔用，取 next free id）
  - Cron `0 6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/counterfactual_daily_cron.sh` 已 install 於 Linux trade-core（idempotent dedupe）
  - 每日 06:00 UTC 跑 `counterfactual_exit_replay.py --days 2 --v2-parity --split-window --cost-model fee_only --bootstrap-ci --per-strategy-median --trimmed-mean-pct 5`，stdout + JSON 寫 `$OPENCLAW_DATA_DIR/audit/counterfactual_daily_cron.log` + `audit/daily/YYYYMMDD.json`
  - Phase 3 auto-gate: check [11] 回 **PASS** 當 `n_rows >= 200 AND grid_trading.cf_fired >= 50 AND ma_crossover.cf_fired >= 50 AND orphan_frozen.n_rows >= 20`
  - 302 LoC (healthcheck fn 152 + cron wrapper 122 + SCRIPT_INDEX 1)，零 runtime 風險
  - **對齊 CLAUDE.md §七 強制規則「被動等待 TODO 必附 healthcheck」**（2026-04-23 新增）— Phase 3 deferral 是典型被動等待，Phase 4 本質即該規則要求的 check function

- [ ] **EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC（P3 backlog，Task 5 agent 2026-04-24 flagged）** — `ExitConfig.shadow_enabled` 也缺 IPC hot-reload 路徑
  - 現狀：CLAUDE.md §三 另一句「`shadow_enabled=false ... flip TOML 即啟，無須再 rebuild`」與先前 `missing_edge_fallback_bps` claim 同類錯誤（ArcSwap 無 file-watch path，本質需 IPC patch）
  - 修：加 `exit_shadow_enabled: Option<bool>` 到 EDGE-DIAG-1-FUP-IPC 已建立的 7-field 套件；~5 LoC 延伸 + 1 test
  - 優先級 P3：非 blocker，Phase 2 Combine Layer shadow 要 flip `true` 時才需要（operator 尚未決定 Phase 2 start）

- [x] **EDGE-DIAG-1-FUP-IPC（P2，QC round 1 揭露）** ✅ 2026-04-24 — `ExitConfig` 加 IPC hot-reload 路徑
  - 現狀：`rust/openclaw_engine/src/ipc_server/handlers/risk.rs:42-138` IPC `update_risk_config` 只暴露 21 legacy fields，**零個 `exit.*`**；`ConfigStore<RiskConfig>` 用 ArcSwap 但僅 bootstrap load，無 SIGHUP 路徑。CLAUDE.md §三「`missing_edge_fallback_bps` hot-reload 可調」claim 過期。
  - 修：加 7 個 `exit.*` 欄位到 `IpcRiskUpdate` struct + handler parse → `ConfigStore::apply_patch` + `with_toml_persist`（~15 LoC + 1 test）；同步更正 CLAUDE.md §三
  - **價值**：Phase 3 部署後任何 fallback 調整 < 60s 可逆（非 rebuild ~3 min）
  - **優先級**：P2；非 blocker；做在 Phase 3 前更安全
  - 估 ~1d
  - **完成**：`PipelineCommand::UpdateRiskConfig` + `ipc_server/handlers/risk.rs` + `event_consumer/handlers/risk.rs` + `risk_store.apply_patch`（validate() 全或無 rollback）；+2 regression tests（round-trip + validate-reject）；CLAUDE.md §三 sentence 已更正

**關聯**：P0-3 Phase 5 edge 重評（前置）· P1-10 EDGE-P2-3 PostOnly 1w 觀察（並行）· DUAL-TRACK Phase 1b counterfactual replay audit（已列）· §P1-14 EDGE-ESTIMATE-BIND-BLOCKED-1（cells 翻正前提）

**檔案/工件**：
- `settings/risk_control_rules/risk_config_demo.toml` `[exit]` section
- `rust/openclaw_engine/src/exit_features/v2.rs:104-126` Gate 1 fallback design
- 對照數據 SQL：`SELECT engine_mode, strategy_name, COUNT(*), AVG(net_pnl_bps) FROM trading.fills WHERE ts > now() - interval '24 hours' AND engine_mode='demo' AND strategy_name LIKE 'risk_close:phys_lock_%' GROUP BY 1,2;` vs `'risk_close:TRAILING%'`

### ✅ P1-19 · BACKFILL-LABELS-STALLED-1 — 結案 2026-04-22（duplicate of P1-10）

**判決**：不是 pipeline bug，是上游 P1-10 STRATEGY-ASYMMETRY-1 的症狀。RCA worklog `docs/worklogs/2026-04-22--backfill_labels_stalled_rca.md` §7-§9。

**實證驗證**（2026-04-22 22:15 CEST operator 授權跑 psql）：
- demo 24h close_fills = 14，**entry_context_id 100% 填充（14/14）** → **H1 證偽**（FILL-CONTEXT-LINKAGE-1 Rust 鏈健康）
- backfill 實寫 7d timeline：139 → 24 → 44 → 14，線性對齊 close_fills → **H2 證偽**（無 silent fail-open）
- demo close_fills 4 日軌跡 199 → 31 → 54 → 14（2026-04-19 起每日 85% 驟降）→ **H3 命中**（策略自我收斂，fee drag + ~~MICRO-PROFIT-FIX-1 narrow-band 壓制入場~~ 🔴 **2026-04-22 P0-15 部分推翻**：MICRO-PROFIT narrow-band gate 在 T3 deprecation 被連帶註解、無 runtime 實作，「壓制入場」機制實際不存在；H3 主因純為 fee drag / R:R 結構問題，不含 MICRO-PROFIT 影響）
- 按當前 14 labels/day/2 主 slice 速率，BLURUSDT 47→200 需 **~22 天**（非原估 3-5d）

**連帶 P1-7 C 影響**：ONNX 訓練延後至 **2026-04-28+**（由 P1-10 EDGE-P2-3 PostOnly 1w 觀察結果決定入場量是否回升）。P1-7 C 進入被動等待，無獨立 unblock 路徑。

**附帶產出**（3 個 P2 可觀測性 TODO，獨立於 H3 判決）：見 §P2 新增項 RESTART-ALL-UVICORN-LOG-1 / EDGE-SCHEDULER-LEADER-1 / SCHEDULER-FAILURE-OBSERVABILITY-1。

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
- **下一步**：(1) ~~grid cooldown audit~~ ✅ 結案 — 已補 TOML hygiene，cadence 無 bug，問題在 fee drag (2) ✅ **ma_crossover SL/TP 比率 audit 2026-04-22**（`docs/worklogs/2026-04-22--p1_10_ma_crossover_sl_tp_audit.md`）— ma_crossover 無策略層 SL/TP，SL/TP 由 `risk_checks::check_position_on_tick` 全策略共用；take_profit_enforced 三環境全 false（無硬 TP）；核心假設 = **demo `trailing_distance_pct=3.5` 相對 ATR 1-1.5% 過寬** → winner peak +1% 給回 3.5% 變 −2.5% loss 才出場。推遲 TOML 改動至 counterfactual replay 驗證（spec Appendix C 新增 trailing scan `{2.0, 2.5, 3.0, 3.5}`）(3) EDGE-P2-3 maker order 列為 P1-10 grid 唯一結構出路
- **與 DUAL-TRACK Phase 2 並行**：兩者修好 P0-3 才能乾淨重評；ma_crossover 若 2.54× 不能收斂到 ≤1.5× 應 disable 或等 R-02 Strategist 重評

#### 🧠 2026-04-19 推進推理鏈（compact-safe，survive-compact 用）

**⚠️ 起因**：2026-04-19 15:37 redeploy 後重查 R:R 不對稱，追蹤到以下結構事實：

> **🔴 2026-04-22 P0-15 推翻第 1 點**：本節原敘述「MICRO-PROFIT-FIX-1 narrow-band gate 正常運作 / 2026-04-20 demo 24 + paper 12 MICRO-PROFIT close 100% 勝率 +$4.68」**經 psql 實測對帳完全錯誤**。真相：`risk_close:COST EDGE%` 7d **只有 35 rows 全集中在 2026-04-18/19 T3 rebuild 之前**，2026-04-20/21/22 **連續 3 天 0 fire**。原「24 筆 MICRO-PROFIT close」是查詢窗口涵蓋 rebuild 前 cached 行為的誤判。詳 `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md` §3.4。
> **影響**：P0-3 Phase 5 edge 重評所依賴的「MICRO-PROFIT 是當前最重要正 edge 安全網」基礎錯誤；退場層實際 2026-04-19 晚 → 2026-04-21 晚 2.5 天完全空窗（7d 只 trailing 7 + dynamic stop 1）。

1. **（2026-04-22 P0-15 推翻；下文為 2026-04-20 錯誤版本，保留供稽核）** ~~legacy COST EDGE block 註解 ≠ 功能退場；MICRO-PROFIT-FIX-1 接手了 Priority 6~~
   - `risk_checks.rs:245-259` 舊 COST EDGE gate block 已註解（DEPRECATED）— ✅ 此句仍對
   - 新 PHYS-LOCK gate（`risk_checks.rs:129-165`）存在但依賴 `exit_features: Option<&ExitFeatures>` — ✅ 仍對
   - `tick_pipeline/on_tick.rs:1456-1474` `evaluate_positions(...)` closure 目前傳 `|_| None` → PHYS-LOCK 永遠拿不到 features → 永遠 Hold — ⚠️ **2026-04-21 commit `e95c779` T4 接線後此 claim 過時**，但 T4 後 Gate 1 est_net_bps 99.1% NULL + P0-13 unit bug 仍讓 PHYS-LOCK 0 fire（看 P0-13/P0-14）
   - ~~**但 MICRO-PROFIT-FIX-1 narrow-band gate（`ratio ≥ 0.20 & pnl ∈ [0.30%, 0.55%]`）正常運作**~~ 🔴 **false** — 該 gate 被 T3 deprecation 一併註解，2026-04-19 T3 rebuild 後沒有 runtime 實作
   - ~~2026-04-20 24h 實測：demo 24 筆 + paper 12 筆 MICRO-PROFIT close~~ 🔴 **false** — 查詢窗口 artifact，實際 04-20 起 0 rows
   - Track P T4 `phys_lock_*` 實測 0 觸發 — ✅ 當時對；2026-04-21 T4 接線後仍 0（P0-13/14 雙 bug 疊加）
   - ~~**原稿 claim「0 條 COST EDGE close」有誤**~~ 🔴 原稿其實接近對（04-20/21/22 確實 0 rows），2026-04-20 修正版本才是誤判

2. **`trailing_activation_pct=0.8` 非 hardcoded**
   - `rust/openclaw_engine/src/config/risk_config.rs:518` `default_trailing_activation_pct() -> 1.0`
   - 三環境 TOML 獨立（已由 `feedback_env_config_independence.md` 記錄）：
     - `risk_config.toml:35 = 1.0` · `risk_config_demo.toml:35 = 0.8` · `risk_config_paper.toml:51 = 0.5` · `risk_config_live.toml:37 = 0.5`
   - **7d DB 查核 `trailing_stop` 觸發次數 = 0** → R:R 不對稱**非** trailing 主因

3. **DB 真實 R:R 不對稱主因（2026-04-20 refined）**：
   - ma_crossover asym 2.54× → 0.88：虧損側已縮小到比獲勝側小；但 win rate 從 64% 跌到 37.8%（37 exits）→ **問題變成「勝率」而非「不對稱」**，Track P T4 加速理由弱化
   - grid_trading asym 1.71× → 2.09× 惡化：fee drag 持續主導；需 P1-10 grid cooldown_ms / min holding time 結構修
   - ~~MICRO-PROFIT-FIX-1 在 `risk_checks.rs` MICRO-PROFIT 分支仍照常觸發，demo 24 + paper 12 closes/24h，100% 勝率 +$12.17 net~~ 🔴 **2026-04-22 P0-15 推翻**：runtime 實測 0 fire（此 claim 為 rebuild 前 cached 查詢 artifact）

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

> 🔴 **2026-04-22 P0-15 推翻**：本表 `risk:cost_edge_micro` 兩行（demo 24 / paper 12）所依據的查詢窗口涵蓋 2026-04-19 T3 rebuild **之前** cached `risk_close:COST EDGE%` 行為；實際 2026-04-20 起 `cost_edge_micro` **0 fire**（7d 35 rows 全集中在 04-18/19 rebuild 前）。MICRO-PROFIT-FIX-1 narrow-band gate 在 T3 deprecation 時被連帶註解、沒有獨立 runtime 實作。表格行保留供稽核（勿刪），下方以 🔴 strikethrough 標明失效，詳見 §P0-15 + `docs/worklogs/2026-04-22--passive_wait_silent_fail_audit.md` §3.3/§3.4。

| engine | kind | n | win_rate | asym | total |
|---|---|---:|---:|---:|---:|
| demo | ma_crossover | 37 | **0.378** | **0.88** | −$6.39 |
| demo | grid_trading | 98 | 0.531 | **2.09** | −$9.72 |
| demo | ~~risk:cost_edge_micro~~ | ~~24~~ | ~~1.000~~ | — | ~~**+$4.68**~~ 🔴 P0-15 推翻（cached artifact，實際 0 fire） |
| demo | risk:trailing | 2 | 1.000 | — | **+$13.22** |
| demo | risk:fast_track | 7 | 0.571 | 1.16 | +$0.59 |
| demo | risk:dynamic_stop | 1 | 0.000 | — | −$10.41 |
| paper | grid_trading | 34 | 0.235 | 1.80 | −$10.80 |
| paper | ~~risk:cost_edge_micro~~ | ~~12~~ | ~~1.000~~ | — | ~~+$7.49~~ 🔴 P0-15 推翻（cached artifact，實際 0 fire） |
| live_demo | ma/grid | 8 | 0.625 | — | +$0.70（樣本太小） |

**關鍵判讀**：
- **ma_crossover asym 2.54× → 0.88 翻轉**（虧損側現在比獲勝側小），但 win rate 64%→37.8% 崩 → R:R 題目變成「勝率問題」非「不對稱問題」。Track P T4 加速理由弱化。
- **grid_trading asym 1.71× → 2.09× 惡化**。fee drag 持續主導，P1-10 grid cooldown audit 仍為 P0-3 edge 重評阻塞。
- **Track P T4 phys_lock 0 觸發**（符合：`on_tick.rs:1456-1474` `evaluate_positions(..., |_| None)` 導致 PHYS-LOCK 拿不到 ExitFeatures，永遠 Hold）。
- 🔴 **2026-04-22 P0-15 推翻** ~~**⚠️ P1-10 推理鏈 §1 「redeploy 後 `trading.fills` 0 條 COST EDGE close」claim 不成立**：24h demo 24 + paper 12 COST EDGE close 真實發生，都是 MICRO-PROFIT-FIX-1 narrow-band `ratio ≥ 0.20 & pnl ≥ 0.30%` 輸出（`risk_checks.rs` MICRO-PROFIT 分支仍寫 `strategy_name="risk_close:COST EDGE:..."` 重用 label）。**Priority 6 未真空**，MICRO-PROFIT gate 吸收了舊 COST EDGE 的 winner-pick 功能（demo +$4.68 / paper +$7.49 / 24 + 12 fills 100% 勝率），是當前最重要的正 edge 來源。~~ — 真相：`risk_close:COST EDGE%` 7d 僅 35 rows 全集中在 T3 rebuild 前，2026-04-20/21/22 連續 3 天 0 fire；原「24 筆 / 12 筆」為查詢窗口涵蓋 rebuild 前 cached 行為的誤判。**推理鏈 §1 原「0 條」claim 其實接近對**（2026-04-20 修正版本才是誤判）。Priority 6 在 T3 rebuild→T4 接線期間真正空窗 2.5 天。
- 🔴 **2026-04-22 P0-15 推翻** ~~**MICRO-PROFIT + trailing combined 輸出**：demo +$18.49 / 24h（+$6.68 fast_track/cost_edge_micro + $13.22 trailing − $10.41 dynamic_stop outlier）。基礎策略 −$16.11 / risk_close +$7.39 → demo 24h 總 net **−$8.72**。~~ — MICRO-PROFIT 部分為 cached artifact；combined 真實值 = trailing +$13.22 − dynamic_stop $10.41 ≈ +$2.81 / 24h，風險層實際只有 trailing + dynamic 兩個被動止損在動（詳 §P0-15）。

**判決**：
1. Track P T4 wiring **按 W24 排期不加速**（asym 已翻、phys_lock 0 fire 符合設計）。
2. P0-3 edge 重評**仍推遲** — grid fee drag + ma win rate collapse 需要 P1-10 結構性修復（grid cooldown_ms + ma SL/TP 重設），而非退場層補救。
3. P1-10 推理鏈 §1 需更正（上方 inline 已改述）；MICRO-PROFIT-FIX-1 label reuse 應註釋到 §二 推理鏈，避免後續誤判。

### P1-11 · BB-BREAKOUT/REVERSION-DORMANT-1 — Bollinger 家族 AND 條件過嚴
- **範圍（2026-04-24 擴展，吸收原 P1-12）**：同時覆蓋 `bb_breakout.rs` + `bb_reversion.rs`，兩者同為 BB 家族 AND-chain signal gating 過嚴，demo 產量嚴重不足。
- **bb_breakout 根因**：`bb_breakout.rs:457-518` 入場 5 重 AND（squeeze → expansion → volume → Donchian → persistence）+ 時序要求過嚴；14d demo 0 fills。
- **bb_reversion 根因**：BB squeeze + mean-reversion 兩個 AND 條件下 demo 14d **僅 8 signal → 12 intents → 5 fills（阻擋率 37.5% 來自 liquidity / timing，非 Guardian）**；signal 產量本身太低使樣本不足以做統計學習（P1-13 SAMPLE-FLOOR-GAP-1 的 bb_reversion 1 RT 數據反映此結構）。
- **下一步**：
  - (1) 🟡 **Phase 1 完成 2026-04-24 + self-audit 修正** — sweep `helper_scripts/research/bb_breakout_threshold_sweep.py`（5 symbols × 14d × 64 combos pooled）：
    - **Self-audit 修 3 bug**（commits `def9018` / `c370ffa` / `d9e86c7` / `b689eab`）：B1 F1 wording 反了 · B2 F2 top edge 未測統計顯著 · B3 Python FIX-26 parity 錯（每 bar 覆寫 timer）。詳 `.claude_reports/20260424_022414_p1_11_findings_verified_after_selfaudit.md`。
    - **驗證中發現 F4 真 Rust bug** — **FIX-26-DEADLOCK-1**：`squeeze_detected_ms` 過期後無清除路徑；首次 squeeze 窗口無入場 → symbol **永久 dormant**。是 bb_breakout 14d 0 fills **第一層真正根因**。修：Rust commit `bcc5401` 加 expiry auto-clear + 3 regression tests；engine lib 1956 → **1976 passed / 0 failed**。**下次 `restart_all.sh --rebuild` 生效後** 預期 bb_breakout 脫離 permanent-dormant。
    - **驗證後 findings**：
      - **F1（CONFIRMED 措辭修）**：1m BB bandwidth q=0.99 僅 0.014，production `expansion_bw=0.04` 從不達成（不是 squeeze_bw 問題，bandwidth 100% 低於 0.03 反而使 squeeze 永遠觸發；卡在 expansion）
      - **F2（signals≠edge 方向成立但未達 95%）**：top sharpe combo n=20 fwd30=+0.150% tstat=1.35 → 未達 95%；top count n=211 fwd30=-0.022% tstat=-0.57。信號多≠edge 好但需更大樣本才能 confirm top-edge。
      - **F3（CONFIRMED + 達 95-99% 顯著）**：post-fix sweep `breach_diff_tstat` 在 top sharpe 三個 combo 達 **-3.10 到 -3.20**（>99%）；`0.0025/0.011/1.2` 達 **-2.21**（>97%）。**`DonchianMode::Score +bonus on breach` 方向確定錯**，正解是 Off 或反轉 bonus 符號。
  - (1) ⬜ **Phase 2 backlog**：(a) 擴 20+ symbols × 30-60 days 追 95% top-edge 顯著 (b) 加 fee model (round-trip 11 bps taker) (c) persistence + cooldown 模擬 (d) F3 深驗 — ADX regime 拆分，決定改 Score 方向或推 Off default (e) rescale Conservative/Aggressive profile 值為 1m-realistic
  - (2) ✅ **2026-04-24 commit `0528d96`+`38a14ca`** Donchian AND→Score/Off — `DonchianMode::{Hard, Score, Off}` enum；Hard 預設 bit-identical 基線；熱重載 + validate + 14 tests。**F3 證偽 Score +bonus 方向；Phase 2 驗證後建議改 Off 為 production default 或反轉 bonus 符號。**
  - (3) ✅ **2026-04-24 commit `0528d96`+`38a14ca`** aggressive/conservative A/B — `BbBreakoutProfile::{Conservative, Balanced, Aggressive}` enum + `for_profile()` helper；`Balanced == default()` 測試固化；**3 profile 種子值在 1m 下皆不可觸發（F1）— Phase 2 (e) 需 rescale。**
- **狀態**：(1) Phase 1 🟡 完成含 self-audit 修 3 bug + 發現並修 F4 Rust deadlock / (1) Phase 2 ⬜ backlog / (2)(3) ✅ code 完成但 F3 暗示 Score 方向錯。**下次 `--rebuild` 部署 FIX-26-DEADLOCK-1**，預期 bb_breakout 脫離 permanent-dormant；operator observe 1w 看實際 fill 數。若要同時軟化 Donchian，**建議 `DonchianMode::Off`** 而非 Score（F3 證偽 Score +bonus 方向）。
- **Followup**：bb_reversion 尚未拆 sibling（`bb_reversion.rs` 單檔 1143 行）+ 未加 profile — (2)+(3) 類似改造可在 `bb_reversion` 落地但目前 scope 只做 bb_breakout，另列獨立條目或併入 E5-P2-4c 邊緣拆分。
- **優先級**：P1 低 — 不緊急但影響 Phase 5 策略多樣性與 ML 樣本池。

### ✅ P1-12 · BB-REVERSION-BLOCKED-1 — **2026-04-23 反轉結案 · 2026-04-24 gap audit 收尾**
- **原判**：~~24h live_demo 66 筆 decision_features 但 0 fills（14d demo 僅 2 筆），100% 被下游擋，下一步 trace risk_verdicts + engine.log~~
- **實測反轉（commits `4520823` + `81cde54` + `025dd17` + 2026-04-24 gap fix）**：
  - **當前 14d demo bb_reversion**：8 df → 8 rv **全 Approved** → **12 intents**（df=8；多出 4 筆為 exit/retry intents）→ 5 fills / 3 entry 未成交。阻擋率 = 3/8 = **37.5%（非 100%）**，且 Guardian 層無任何阻擋。
  - **原「66 筆」數字來源**：實際是 **2026-04-17 live_demo 609 筆**（TODO 記的 66 是早期 snapshot），全 rv Approved 但 `trading.intents` 0 rows。
  - **意外發現 — 根因非 bb_reversion**：同日 **demo 1755 orders / 0 intents**、**live_demo 190 orders / 0 intents** — **4/17 trading.intents writer 全表 silent outage**，橫跨全策略全 engine_mode。4/16-4/19 live_demo intents 幾乎全斷，4/20+ 恢復（4/23 demo 266 intents / 339 orders ratio 0.78 ∈ healthy baseline 0.70-0.87）。
- **歸類**：bb_reversion 當前並無阻擋問題；「14d 8 signal」是 **signal generation 量級問題**（BB squeeze + reversion 兩個 AND 條件下 demo 14d 產量本來就低），**已正式納入 §P1-11（本次更名 BB-BREAKOUT/REVERSION-DORMANT-1）** signal threshold audit scope。
- **防復發**：commit `4520823` 新增 `passive_wait_healthcheck.py` check [10] `intents_writer_ratio`，**2026-04-24 gap audit 升級為 per-mode（demo + live_demo 同時覆蓋）**，任一 mode orders>0+intents=0 即 FAIL；ratio<0.3 → WARN（baseline 0.70-0.87）；paper 排除（PAPER-DISABLE-1 opt-in）。commit `81cde54` 補防禦式 rollback 避免前 check tx poisoning。Live 驗證 per-mode 輸出（live_demo 當前 quiet → skip；demo ratio 0.78 PASS）。
- **報告**：`.claude_reports/20260423_233644_p1_12_reversal_postmortem.md`
- **Gap-audit 2026-04-24** 掃出 3 gaps 已修：(Gap1 ✅) [10] 擴展至 demo+live_demo per-mode；(Gap2 ✅) P1-11 條目本體擴 scope 吸收 bb_reversion；(Gap3 ✅) df=8/intents=12 數字校正。
- **接棒項**：bb_reversion signal threshold audit → 已併入 §P1-11；intents writer 4/17 事件對應特定 commit → 不追 cold case（已恢復 ≥7 天、healthcheck 把關）。

### P1-13 · SAMPLE-FLOOR-GAP-1 — per-strategy round-trip 樣本低於 ML 訓練閘口

| engine | grid_trading | ma_crossover | funding_arb | bb_reversion | bb_breakout |
|---|---:|---:|---:|---:|---:|
| demo+live_demo fills | 2,492 | 762 | 77 | 2 | 0 |
| 估計 RT | ~1,200 | ~380 | ~38 | 1 | 0 |

- **現象**：Step 0 不確定 3 audit — `trading.fills` 配對 RT 遠低於 QA 守衛「≥1000/策略」；僅 grid_trading 勉強過閘
- **影響**：DUAL-TRACK Phase 1 Track L 範圍限 grid_trading 單策略 PoC；ma_crossover/bb_*/funding_arb 延後，累積期間 Track P only
- **下一步**：(1) ✅ 2026-04-23 DUAL-TRACK Phase 1 軌道 2 C 範圍聲明已更新限 grid_trading 單策略 PoC（TODO §Phase 1a 軌道 2 C 首行附 scope note，列出 ma_crossover/funding_arb/bb_reversion/bb_breakout RT 均低於 1000 閘口的依據） (2) 每週 per-strategy 樣本 audit 判斷加入時點（條件：per-strategy RT ≥1000 + P0-3 edge 判決後再入訓練池）
- **關聯**：DUAL-TRACK Step 0 不確定 3 / Phase 1 軌道 2 C · QA 守衛 #1 · 風險退路 #5

### P1-14 · EDGE-ESTIMATE-BIND-BLOCKED-1 — JS estimator snapshot edge 不足以 bind cost_gate
- **現象**：Step 0 不確定 1 驗證 `settings/edge_estimates.json` 首次寫入成功（104 cells · demo `grand_mean −2214 bps`）。**更正（2026-04-18 b0df1b3 P1-15 修復後）**：原 −2214 bps 受 28 phantom cells（18 `ipc_close_symbol::*` + 10 `risk_check::*`）污染，非可信 reading；live_demo 7d 乾淨 baseline `grand_mean −14.97 bps` ≈ fee-neutral，落在典型 fee-drag 範圍
- **問題**：當前 snapshot 未達 bind threshold（需 ≥2 策略 shrunk_bps>0 且 grand_mean > −50 bps），hot-reload 進 Rust cost_gate 仍會抑制過多 intent
- **根因**：cells 層級 edge 仍偏負/不穩定的結構原因 = P1-10（grid fee 74% + ma_crossover 2.54× R:R 不對稱），非 estimator 機制缺陷；污染部分已由 P1-15 消除
- **下一步**：(1) DUAL-TRACK Phase 1 軌道 2 B 僅啟 scheduler 寫檔 + PG UPSERT，**不綁定** Rust cost_gate 讀取 (2) P1-10 修復落地後重跑 estimator 觀察 grand_mean 走勢 (3) 條件啟動 bind：grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0（fee-drag 範圍可接受，catastrophic-negative 才禁 bind）
- **阻塞**：不阻 Live；阻 DUAL-TRACK Phase 1 軌道 2 B 完成判定 + Phase 5 cost_gate 重啟
- **關聯**：P1-10 STRATEGY-ASYMMETRY-1（必要前置）· DUAL-TRACK Phase 1 軌道 2 B · P0-3 Phase 5 edge 重評

---

## 🟢 P2 — 下週 / Live Gate / QoL

### Session 2026-04-23 Review Follow-up (QC/FA/FM/E4 audit)

**4 人獨立 review commit d9bd451** — 0 BLOCKER + 5 MAJOR 已修 6 項（P0+P1），3 項延後。

**✅ 已修**（commit `d9bd451`）：
- QC-2: `_record_cycle_event` payload-build 包進最外層 try/except（兌現 fail-soft docstring 契約）
- QC-3: CLAUDE.md §九 singleton 表補 `_scheduler` / `_scheduler_lock` / `_LEADER_LOCK_FD` / `_LEADER_LOCK_PATH`
- FA-1: `gather_strategy_metrics` 加 `debug_assert!(tune_target == Demo)` 防 Live tune 無聲 SQL miss（`effective_engine_mode` 寫 `"live_demo"` 但 `db_mode()` 回 `"live"`，Phase 5+ STRATEGIST-TUNE-TARGET-CONFIG-1 需擴 IN 多值前 debug_assert 先擋）
- FA-2: `/status` + `/trigger` 對 non-leader worker 讀 flock sentinel 誠實回 `{started: True, is_leader: False, leader_pid: N}`，原回 `{started: False}` 致 monitoring dashboard 誤報 3/4 worker scheduler 死
- E4-2: `test_backfill_fail_js_ok_records_backfill_error_class` 補 backfill-fail + JS-ok asymmetric scenario
- E4-4: `test_pipeline_kind_db_mode_demo_is_lowercase_snake` 釘 `db_mode()` 返 `"demo"` 小寫防漂移
- 測試：engine lib 1850 → **1851 passed**，Python obs+leader 11 → **12 passed**

**✅ 本 session 已閉合**（commit `b0b47b5` + FA-BLOCKER fix）：
- ✅ **E4-1** commit `b0b47b5` + 補強 — `helpers.rs` +3 regression test：(a) `no_new_literal_risk_close_format_outside_helpers_rs` 掃 `format!("risk_close:{..}")` literal (b) `no_new_literal_risk_close_phys_lock_outside_helpers_rs` 掃 bare `"risk_close:phys_lock_..."` literal（FA post-commit audit BLOCKER 補）(c) `build_risk_close_tag_is_idempotent` 契約 idempotency 固化。
- ✅ **E4-5** commit `b0b47b5` — `ipc_server/tests.rs` +6 handler e2e test（3 handler × 2 path），byte-identity 斷言 3 條錯誤訊息。
- ✅ **E4-3** commit `b0b47b5` — `test_leader_lock.py` +4 test / +7 parametrize（mkdir fail / open fail / env 非 `"0"` 4 值 / `_reset_for_tests` idempotent）。Shutdown primitive 延後 → 見下 `SCHEDULER-SHUTDOWN-PRIMITIVE-1`。
- ✅ **Cross-gap Grafana/SQL pattern 掃描** commit `b0b47b5` B1 audit — docs/scripts/grafana/sql/program_code/settings 全空；Rust executable 只 helpers.rs test 斷言 + risk_checks.rs 單一 emission 點；其他 4 hits 為 doc comment 無 runtime 影響。0 code 改動。

**✅ 2026-04-23 post-audit closeout（3 commits + 1 post-hoc split）**：
- ✅ **STRATEGIST-PARAMS-PERSIST-1** commit `f1f7403` + post-hoc split — V019 migration `learning.strategist_applied_params` + scheduler `persist_applied_params()` + engine startup `load_latest_applied_params()` restore loop。fail-soft：pool=None/SQL 失敗/channel 關閉/handler 拒絕均 warn + continue，engine 正常啟動退化 TOML baseline。**部署順序必須**：(1) psql 跑 V019 migration → (2) `restart_all.sh --rebuild`（反序 engine warn spam 但非致命）。engine lib Mac+Linux 1862 passed。post-hoc `strategist_scheduler.rs` 1342 → `strategist_scheduler/{mod.rs 1166, persist.rs 235}` split（§九 1200 硬限合規）。Phase 5+ 接棒見 STRATEGIST-AUTO-PROMOTE-CRITERIA-1 + STRATEGIST-HISTORY-OBSERVABILITY-1 條目。
- ✅ **SCHEDULER-SHUTDOWN-PRIMITIVE-1** commit `abc85c0` — event-based shutdown primitive：`__init__` 加 `_stop_event: Event` + `_thread` handle / `_loop` 改 `Event.wait(timeout)` / 新 `shutdown(join_timeout=5.0)` 冪等 method / `_reset_for_tests` 呼 shutdown 清 daemon thread。生產路徑 Event.wait(60) ≈ time.sleep(60) 行為等效；pytest teardown race 解決。+3 regression test，Mac Python scheduler 19 → 22 passed。FA H1 自承 `_started` 非對稱 reset → shutdown 後同 instance 無法重啟，production 無此 path 不觸發。
- ✅ **IPC-SERVER-TESTS-SPLIT-1** commit `585be97` — `ipc_server/tests.rs` 1847 → `ipc_server/tests/` 11 sibling（max 343、min 67，全 ≤ 800 soft warn），按 topical area 切（dispatch/snapshot/risk/strategy/phase4/config/budget/teacher/scanner/risk_update/mod）。shared fixtures 集中 `mod.rs`，topical-only fixtures 隨 test 留 sibling。55 tests 逐字保留，pre/post Mac+Linux 1860 → 1862 對帳一致（+2 來自 T1 非本 split 引入）。§九 1200 硬限合規。

**⬜ 新延後（Phase 5+ 硬依賴，由 post-commit FA review 識別）**：
- ✅ **STRATEGIST-PERSIST-TIE-BREAK-1（FA H1）** 2026-04-23 — V020 migration `sql/migrations/V020__strategist_applied_params_tie_break.sql` DROP+CREATE `idx_strategist_applied_engine_strategy_ts` 末加 `, id DESC`；`persist.rs::load_latest_applied_params` SQL `ORDER BY ... applied_at_ms DESC, id DESC`。+1 property test `test_load_sql_has_id_desc_tie_break`。engine lib 1865 → 1866。**部署**：`psql -f V020__...sql`（純 index 重建無 data 動，可與 V019 獨立跑）。
- [ ] **STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1（P2，FA H2，Phase 5+ 前置）** — `persist_applied_params` fail-soft 導致 runtime 已 tune 但 audit 表無 row → 下次 restart 這筆 tune 靜默丟失，違反 §二 原則 8「交易可解釋」。當前 fail-soft 為 pragmatic 選擇（DB 斷時不阻 in-memory tune），缺**補償機制**。**修**：(a) persist fail 累積 `warn!` + counter（e.g., new Prometheus metric `strategist_persist_fail_total`） (b) Phase 5+ AUTO-PROMOTE-CRITERIA-1 讀 counter，非零時促升輪次**拒絕計數**（避免 audit-hole 污染穩定計數器）。~1d。
- ✅ **STRATEGIST-PERSIST-TEST-BROADEN-1（QC M2）** 2026-04-23 — persist.rs +3 SQL property test（`test_load_sql_has_distinct_on_and_desc_order` / `test_load_sql_selects_expected_columns_and_filters_engine_mode` / `test_persist_sql_has_all_seven_audit_columns_and_placeholders`）。用 `include_str!("persist.rs")` compile-time embed + 空白正規化，防 SQL 關鍵子句（DISTINCT ON / ORDER BY DESC / 7 欄 INSERT / $1..$7 placeholder）被後續重構誤改。**無法在 Mac 層覆蓋**的真 SQL semantic test（schema 不存在錯誤 / 多 row 排序 / round-trip）需 Linux CI `sqlx::test` + Docker PG integration harness（**新 FUP `STRATEGIST-PERSIST-INTEGRATION-TEST-1` P3 登記延後**）。

### 可觀測性（P1-19 RCA 副產品，2026-04-22 新開）
- ✅ **RUST-DOUBLE-PREFIX-1** 2026-04-23 commit `46a9cad` — 採 Option B：`step_6_risk_checks.rs` 單一 emission 點新增 `build_risk_close_tag` helper（already 含 `risk_close:` 則直用，否則 wrap）。不選 A 因 `strip_phys_lock_prefix` + helpers 既有 test 依賴 PHYS-LOCK reason 帶顯式前綴。+2 regression tests（`phys_lock_reasons_do_not_double_prefix` / `non_phys_lock_reasons_get_single_prefix`）。`passive_wait_healthcheck.py` pattern 收回嚴格 `'risk_close:phys_lock_%'`（留容錯會遮蔽 regression）。engine lib Linux release 1837 → **1839** / 0 failed。**Runtime 待 `--rebuild` 部署**，deploy 後 `trading.fills.strategy_name` 單前綴生效、healthcheck [4] 從 double-prefix 容錯觀察模式恢復嚴格 invariant 檢查。
- ✅ **STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1** 2026-04-23 commit `a0730db` — 採「一步到位」架構（Demo 訓練 + Live 促升，Phase 5+ 路線），不選簡單 paper→demo 替換。**根因精修**：不是 mpsc channel 關閉，而是 paper drain task (`main.rs:1143`) 收到 `GetStrategyParams` 命令後直接丟棄 → 內層 oneshot `response_tx` drop → `params_rx.await` 返 `RecvError` 假報 "channel closed"。**實作**：（1）`StrategistScheduler` 新增 `tune_target: PipelineKind` + `promote_cmd_tx: Option<...>` 欄位；ctor `assert!` panic-reject Paper（啟動 fail-fast 好過 runtime 沈默降級）（2）新 `promote_params_to_live(strategy, params_json)` method — 對 Live channel 送 `UpdateStrategyParams` + await oneshot response；本 PR **不自動調用**，Phase 5+ 疊加 IPC 觸發器或 N 輪穩定 criteria 即可啟用，不需重構（3）`gather_strategy_metrics` SQL 加 `WHERE engine_mode = $tune_target.db_mode()` 對齊 tune target，取代原跨引擎混查（4）`main.rs` 改傳 `demo_cmd_tx` 為 tune target + `PipelineKind::Demo` + `live_cmd_tx` 為 optional promote；`demo_cmd_tx=None` 時完全不 spawn scheduler（單行 info 退場）。+6 regression test（ctor reject Paper / Demo without promote / Demo with Live promote / promote err when no channel / promote 端到端 mock handler 驗命令形狀 + await / promote handler err 傳播）。engine lib Mac + Linux release 1839 → **1845 passed / 0 failed**。下次 `--rebuild` 部署後 engine.log 不再噴每 5 min 3 行 channel-closed spam，真實 scheduler 失敗（AI service down 等）才顯露。Phase 5+ 需補 `POST /api/v1/strategist/promote` route 觸發器或 scheduler 內自動 criteria（stub interface 已備）。報告 `.claude_reports/20260423_144135_strategist_sched_channel_paper_orphan.md`。
- ✅ **RESTART-ALL-UVICORN-LOG-1** 2026-04-23 commit `cc36323` — `restart_api()` L208-233 uvicorn 改 `nohup ... > "$DATA_DIR/api.log" 2>&1 &` + `echo "    PID: $!"`，對齊 engine 塊 L197-201 模式。`bash -n` + Linux 部署 lint 均 OK。下次 `--rebuild` 後 `api.log` 恢復更新，API error/traceback 可追。
- ✅ **EDGE-SCHEDULER-LEADER-1** 2026-04-23 commit `f32629c` — 採 fcntl.flock 單機選舉（原 TODO 提「env=1 只讓 worker 0」不可行：uvicorn workers 共享相同 env 無法區分 worker 0）。`_acquire_leader_lock()` 用 `O_CREAT|O_RDWR` + `LOCK_EX|LOCK_NB` 於 `$OPENCLAW_DATA_DIR/edge_scheduler.leader.lock`，fd 存 module global 至 process exit 由 OS 自動釋放（含 SIGKILL）→ crashed leader 不阻塞下次選舉。`start_scheduler()` 回傳改 `Optional[...]`，非 leader 直接 return None（無 instance/thread/cycle）。Sentinel 檔寫 leader PID 便 operator debug。env=0 保留為 opt-out 通道（測試 / 單 worker dev）。+7 pytest（單進程 first-call 勝 + 冪等 + env=0 opt-out + 雙進程 fork sibling 持鎖 → 本進程非 leader + leader exit 重新選舉）。Mac 7/7 + Linux 合跑 scheduler suite 32/32 無回歸。下次 `--rebuild` 後生效：4 worker 中僅 1 個 spawn scheduler daemon + 寫 edge_estimates；`observability.engine_events` 心跳從 4x 降為 1x。`GET /status` 在非 leader worker 回 `{"started": False}`，`POST /trigger` 25% 命中 leader（uvicorn round-robin，operator 重試即可；worker 間代理為 FUP 候選）。
- ✅ **SCHEDULER-FAILURE-OBSERVABILITY-1** 2026-04-23 commit `3be2b9d` — 方案 Y（重用 `observability.engine_events`）勝 X（新表）：零 migration、V014 既有 schema 覆蓋、`event_type` 已有 index、operator 查詢效能好。`_run_cycle` finally block per-mode 寫一行 `event_type='scheduler_ok'/'scheduler_fail'`，payload 含 reason/mode/status/duration_ms/error_class/error_msg/backfill_error_class/n_cells/grand_mean_bps。Fail-soft：writer 任何異常吞下 + `logger.warning` 不阻主循環。+4 pytest（正常 ok / backfill 失敗仍 ok / JS 失敗 fail / pool 不可達不阻塞），Linux 合跑 scheduler 測試 25 passed 無回歸。下次 `--rebuild` 後生效：`SELECT payload->>'mode', payload->>'status' FROM observability.engine_events WHERE event_type LIKE 'scheduler_%' ORDER BY ts_ms DESC` 即可查心跳。

### Live Gate
- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking, W23）
- [ ] **LG-3** provider pricing table 正式綁定（W23）
- [ ] **LG-4** M 章 Supervised Live Gate（W24）
- [ ] **LG-5** N 章 Constrained Autonomous Live（W24）
- [ ] **G-4 / SEC-21** Cookie `secure=True`（HTTPS 部署後，W24）

### AI Layer 接通（W23）
- [ ] **G-7** ClaudeTeacher 啟用（`consumer_loop.rs enabled=false`，前置 21d demo + G-3 IPC auth ✅）
- [ ] **G-10** Calibration.py 整合（isotonic → `run_training_pipeline.py` + ECE < 0.05）
- ✅ **LLM-ABC-MIGRATION-1** 2026-04-20（CLAUDE.md 里程碑索引）— 5 call-site 遷至 `local_llm_factory`；`LOCAL_LLM_PROVIDER=lm_studio` 即可不裝 Ollama 跑 Layer 2。

### QoL & 設計債
- [ ] **QoL-2** Demo AI cost 追蹤（`tab-demo.html` 硬編碼 'N/A'，依賴 G-1 H1-H5）
- [ ] **DUST-EVICTION GUI 曝光**（P1-8 FUP）：log-only 觀察滿一週後（起算 2026-04-17）→ GUI 曝光 `dust_frozen` / `orphan_frozen` 倉位給 operator 日報；`paper_state.rs` 已有 `TriageOutcome.dust_frozen` 計數器
- [ ] **LEARNING-COCKPIT-NO-IPC-1** Learning 8 端點走 Python state_store 非 Rust IPC（設計債，等 G-7/G-10 後再議；不阻 Live，原則 #7 學習平面與 Live 隔離）
- ✅ **E5-P1-5-FUP** 2026-04-23 commit `b5fa443` — 挑 `budget.rs` (10 hits) + `risk.rs` (16 hits) 當示範，替換 20 處內嵌手寫解包成 `param_extractor::require_*` / `optional_*`；移除檔案級 `#![allow(dead_code)]`；保留 4 個未採用 fn 的函數級 allow + 雙語 `TODO(E5-P1-5-FUP-2)` 註明採用條件。+5 單測 (`require_str` happy/error + `optional_u64` × 3)。engine lib 1845 → **1850 passed / 0 failed**。`strategy.rs` / `governance.rs` 未替換為 scope 控制。
- ✅ **E5-P1-4-FUP** 2026-04-23 commit `3d1f764` — 選 (b) 刪除：`call_ollama_timed` 於 business code 0 call sites + 0 imports；唯一理論接線點 `strategist_agent._ai_evaluate` 若接會靜默排除 prompt 構建違反 docstring 契約；Analyst / Guardian 無計時 pattern，無跨 agent 統一需求 → YAGNI。
- ✅ **E5-P1-8-FUP** 2026-04-23 commit `139c65b` — `from_guardian_review` 折疊入主 impl + 第二 block 整段刪除。classification helpers (5 方法) 的 `#[allow(dead_code)]` 保留：grep 確認唯一呼叫點在 test module 內，無 production consumer；加統整 TODO 註記記錄 3 個候選接線點 (`strategy_ai_routes.py` / `learning.exit_features` tagger / `retriage_synthetic_owner`)。Public API 零影響；engine lib 1845 → 1845（refactor-only）。
- ✅ **E5-P2-4b** 2026-04-23（實測比 TODO 記錄更重：bb_breakout 2412 / grid_trading 1729 / strategies/mod 1762）— 3 檔並行 sibling-child-module split：
  - `bb_breakout/` 5 檔（mod 703 / params 398 / runtime_params 105 / tests 695 / tests_oi 577）；42 tests 逐字保留
  - `grid_trading/` 7 檔（mod 322 / params 165 / constructors 231 / grid_layout 133 / position_mgmt 155 / signal 241 / tests 696）；36 tests 逐字保留
  - `strategies/` 4 新 sibling（mod 168 / params 152 / strategy_params 798 / registry 208 / tests 552）；`pub mod <strategy>;` + `StrategyAction` / `Strategy` trait / re-exports 留在 mod.rs
  零邏輯改動，cargo test 1862 → 1866 (strategies module 280/280 綠，C2 補 +3 SQL property test + C1 新 +1 tie-break test)。
- ✅ **E5-P2-4c ma_crossover** 2026-04-23 commit `5b61e64` — `strategies/ma_crossover.rs` 1835 → `strategies/ma_crossover/` 6 sibling（mod 406 / config 81 / helpers 218 / strategy_impl 285 / tests 536 / tests_a1_a2_maker 463，max 536 < 800 soft warn）。Zero-logic sibling-child-module split，pattern mirrors TICK-PIPELINE-MOD-SPLIT-1 (`3d67a99`)：原檔保 types/struct/ctor + mod decls，impl blocks 移 sibling `impl super::MaCrossover { ... }`。engine lib **1942 passed / 0 failed**（baseline 1939 → 1942，+3 來自其他 commits，非 split）。§九 1200 硬上限合規。
- [ ] **E5-P2-4c bb_reversion（P3 邊緣）** — `strategies/bb_reversion.rs` 1143 行（soft-warn 邊緣，未觸硬上限）。同 sibling-child-module pattern 拆；優先級低，ma_crossover 拆完後獨立工作項。~1h。

#### E5 已決議（CANCEL / CLOSED / DEFERRED — 不是待辦，是決策記錄）

> **體例**：這批條目**不再作 checkbox TODO 追蹤**；保留作審計溯源用，改用 bullet。重啟條件 = bullet 內明確觸發事件。避免混在 `[ ]` 清單裡造成「長期 pending」錯覺。

- · **E5-P1-CANCEL-P1-6** — `h0_gate.py` vs `paper_live_gate.py` pipeline 抽象經 sub-agent 實測 0 真實共用，cancel。**重啟條件**：未來出現第三個類似 gate 時（2026-04-19 CHANGELOG Wave 1）。
- · **E5-P1-CANCEL-P1-7** — `PipelineCommand` dispatch-match 已由 P1-3 進一步 by-domain 拆完，原任務前提過時 cancel。**接棒任務**：`tick_pipeline/commands.rs` 836 LOC helper impl 切 `commands/{orders,governor,close}.rs` 已排 E5-P2-X（新排非本項）。
- · **E5-P1-2-DEFERRED** — `main.rs` bootstrap 拆分按 E5 audit 建議「觀察穩定性再拆」延後。**重啟條件**：Live 對後 operator 覆蓋（P0-9 停電 RCA 後唯一未重組模塊）。
- · **E5-P2-1-DEFERRED** — `PipelineCommand` enum reorg 暫延，與 P2-6 共爭 `tick_pipeline/mod.rs`。**重啟條件**：EXIT-FEATURES-TABLE-1 落地後衝突面可重評估。
- · **E5-P2-2-CLOSED** — `onnx_inference` consolidate 優化前提已由 EDGE-P3-1 Phase B Step 7b `OrtPredictor.input_name: String` load-time cache 滿足；`ml/model_manager.rs` 仍 stub。**重啟條件**：ort 真接線 + 出現第二個 session 時（2026-04-19 Wave 2）。
- · **E5-P2-6-DEFERRED** — `tick_pipeline/fill_context_builder.rs` 抽取暫延。**重啟條件**：EXIT-FEATURES-TABLE-1 operator WIP 落地後（2026-04-19 defer）。
- · **E5-P2-7-CLOSED** — `claude_teacher/directive_handler` 抽取 cancel（R6 cohesion invariant + FIX-08 fixtures 已拆 + denylist/helpers/apply_* 1-to-1 耦合無外部消費者）。**重啟條件**：新增第 5 種 directive 或跨 directive 共享 veto 邏輯。
- · **E5-P2-8-CLOSED** — Python `learning_batch_writer` cancel（control_api 唯 1 個 `INSERT INTO learning.*`；ml_training 11 writer 寫 distinct schema 無共用 row shape；真實批寫重複已由 E5-P0-4 Rust `batch_insert.rs` 處理）。**重啟條件**：出現新的跨寫入器共享 row shape 時。
- · **E5-FN-1-CANCEL** — audit §七.7.1「live_authorization.verify 同步但 main.rs 首次 re-verify 在 5 min 後有窗口」evidence-based 證偽：`startup.rs:467-494` `build_exchange_pipeline` 已同步 `load_and_verify(env)`，失敗即 `return None` 拒絕 spawn；5 min ticker 只是 mid-session revoke detector（2026-04-19）。
- ✅ **E5-FN-2 Plan N** 2026-04-19（歸檔 `docs/archive/2026-04-20--completed_todo_batch.md` §12）— 用既有 hypertable PK 取代 V018 partial UNIQUE；零 schema/migration。
- [ ] **E5-FN-2-PLAN-N-FUP** — Plan N 部署後 follow-up：(a) ⬜ Python Layer-2 sync caller 可選升級為傳入 `(request_id, event_time_ms)` 以獲得跨重試的真實去重（目前 IPC handler 本地鑄造時每次 retry 會被當新 row — 仍不會雙重計費本地 caller 自己，但失去跨 Python 重試保護）；(b) ✅ 2026-04-23 `make_request_id_with_rng()` 新測試友好 variant（`pub(crate)`，生產路徑 `make_request_id()` 薄 forward 到 `thread_rng()`）；`test_make_request_id_unique_within_same_ms` 改 seeded `StdRng::seed_from_u64(0xDEADBEEF)` 消除 ~1/2^32 CI flake；(c) ⬜ 部署後 `SELECT time, scope, request_id, COUNT(*) FROM learning.ai_usage_log GROUP BY 1,2,3 HAVING COUNT(*) > 1 LIMIT 5;` 應永遠 0 rows（PK 保證）— 延後 post-deploy verification。

### 跨平台 / Mac 部署準備

- ✅ **PYO3-ELIMINATE-1 全 3 Phase** 2026-04-20（歸檔於 `docs/archive/2026-04-20--completed_todo_batch.md`）— 總移除 1426 LOC PyO3 code，Mac `cargo build` 僅產 binary 無 .so/.dylib。

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

### Phase 5+ Strategist Demo→Live 促升（STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 2026-04-23 `a0730db` 疊加）

**前置已就緒**：`StrategistScheduler::promote_params_to_live(strategy, params_json)` method 已實作、`promote_cmd_tx: Option<UnboundedSender<PipelineCommand>>` 已接線；當 `authorization.json` 簽完 Live channel 到位即 `Some(_)`，單測 Mac + Linux 1845/0 failed。

- [ ] **STRATEGIST-PROMOTE-TRIGGER-1** — 補 promote 觸發器。**路徑**：(1) Python 新 `POST /api/v1/strategist/promote { strategy: str, params_json: str }` route，Operator-only auth；(2) 新 Rust IPC command `PromoteStrategistParams { strategy, params_json, response_tx }` 由 Python 傳入；(3) `main.rs` ctor 保存 `scheduler: Arc<StrategistScheduler>` 讓 IPC handler 可呼 `scheduler.promote_params_to_live(...)`；(4) 驗證：strategy 名稱在 registry、params_json 是合法 JSON、Live engine 已綁（`has_promote_channel()` 為 true，否則回 409）；(5) 記 `observability.engine_events { event_type='strategist_promote_ok'/'fail' }` + `learning.strategist_promotions` 審計表（含 from_params/to_params/ts）。~1d 含 route + IPC command + 測試。

- [ ] **STRATEGIST-AUTO-PROMOTE-CRITERIA-1** — 自動促升（可選，operator 預設關閉）。**criteria 建議**：demo 上此 strategy 連 **N=10** 輪 `evaluate_cycle` 全部：(a) `validate_recommendation` 通過且 (b) 應用後 demo 的 drawdown 無越界 (`peak_balance - current_balance < max_drawdown_pct`) 且 (c) 應用後 AI recommend delta 收斂到 ≤±5%（代表 param 已穩定）。scheduler 內部持 per-strategy 計數器，達 criteria 自動呼 `promote_params_to_live()`。**Kill-switch**：`OPENCLAW_STRATEGIST_AUTO_PROMOTE=0`（default）/ `=1` 啟用 + optional IPC `patch_strategist_config { auto_promote: bool, criteria_rounds: u32 }`。**對抗性驗證**：需 Live hold-out control（隨機 5-10% strategy 不接促升），每月對比 promoted-params Live edge vs control Live edge 確認非 feedback bias。~2-3d 含 criteria 計數器 + hold-out control + 整合測試。

- [ ] **STRATEGIST-TUNE-TARGET-CONFIG-1** — `tune_target` 運行時可配置（非啟動時 hardcode Demo）。當前 `main.rs:907` 傳 `PipelineKind::Demo` 固定；Phase 5+ 若需要切到 Live 做短期 live tune（不建議但有 argument）或測試環境用 Paper（重新啟用），需加 IPC `patch_strategist_config { tune_target: "demo" | "live" }` + scheduler 動態 swap cmd_tx。注意：swap 需保證 in-flight cycle 完成不跨引擎。**優先級低**，目前 Demo 固定是正確路線。~1d。

- [x] **STRATEGIST-HISTORY-OBSERVABILITY-1 (backend)** ✅ 2026-04-23 commit `6faa3cb` — 3 read-only endpoints 綁 `learning.strategist_applied_params`（V019+V020，不是原 TODO 誤寫的 `strategist_promotions`；後者不存在，`strategist_applied_params` 已含 `source`/`prev_params_json`/`params_json` 為嚴格超集）：`GET /api/v1/strategist/history` / `/history/summary` / `/history/{id}/effect`（附 `trading.fills` 7d net/win/count join，live row 自動 widen live+live_demo）；pytest 17/17 passed；pg-down safe-degrade；503 行 route + 459 行測試；restart_all.sh（無 --rebuild）即生效。TRIGGER-1 完成後 `source='manual_promote'` 自動納入，無須再動 schema。

- [ ] **STRATEGIST-HISTORY-OBSERVABILITY-1 (GUI)** — backend endpoints 已 live（`6faa3cb`），GUI tab 待實作：最近 N 個 promote/auto-tune 事件列表 + source 分佈 summary 卡 + 單筆點開看 before/after param diff + 7d edge effect（呼 `/history/{id}/effect`）。~0.5d GUI。建議新增「Strategist History」tab 或併入既有 Learning Cockpit / Strategy tab。待 P1-7 C 訓練管線解阻塞後價值最大（屆時 promote 頻率會上升）。

### EDGE P2 架構重工
- 🟢 **EDGE-P2-2** OI + Liquidation 信號源（給 bb_breakout 加領先信號）
  - ✅ **Phase A OI signal** 2026-04-20 commit `381c542` — bb_breakout confluence 調製；WS `tickers.openInterest` + `oi_delta_pct` → `confluence_score` ±bonus，預設關（bit-identical）；E2 7 findings 全修；engine lib 1770 → **1791**。
  - [ ] **Phase B Liquidation signal**（待 OI signal demo 驗證後啟動）
- 🟡 **EDGE-P2-3** Maker order 支持（5.5 bps → ~1 bps/side）
  - ✅ **Phase 1A → 1B-5 + 3 FUPs + hot-reload + E2 + Phase 2+ (a/b)** 2026-04-18~21（commits 15+ commits；最終 merges `f5f4dc2` + `8280132` 把 PostOnly 擴展到 bb + ma）— PostOnly maker 入場管線覆蓋 grid/ma/bb 三策略（demo/paper=true, live=false）；`MakerKpiConfig` Cold/Healthy/Degraded gate + ConfigStore 熱重載；funding drag bias guard；engine lib 1762 → 1827。**Runtime 已在 2026-04-21 20:44 `--rebuild` 部署**。
  - [ ] **Phase 2+ (c)** live endpoint 啟用 · funding_arb 接 PostOnly · learning integration（待 demo/paper accumulate ≥1w 驗正效果）

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

**2026-04-24 批次歸檔**（3 項 P0 三連）：`docs/archive/2026-04-24--completed_todo_batch.md`
- P0-13 ATR-SCALE-BUG-1(`ff694e8`) · P0-14 EDGE-ESTIMATES-MISS-1(A `2484263` + B `9710ff9`) · P0-15 COST-EDGE-DEPRECATION-MICRO-PROFIT-GAP-1(doc fix `2330360`)；2026-04-22 23:35 CEST 同部署 + 2026-04-23 24h+ runtime 驗收 PASS（phys_lock 21 fires / atr_pct avg 0.243 / giveback 1.108 / edge_estimates 162/162 cells）

**2026-04-21 批次歸檔**（14 項）：`docs/archive/2026-04-21--completed_todo_batch.md`
- DECISION-OUTCOMES-* 三連（engine_mode tagging + outcome_* JOIN null + observability doc-close）· TRACK-P-T4-WIRING-1 主軸解阻塞（`e95c779` + 20:44 CEST runtime 部署）· DUAL-TRACK-EXIT-1 Phase 1b Track P v2 pure fn(`aee96b9`) · GATE1-REVERSAL-1 hotfix A(`d0f0c21`) · EDGE-P2-3 Phase 2+ (b) bb + ma PostOnly · EXIT-FEATURES-SPLIT-1(`3a9b988`) · ON-TICK-SPLIT-1(`bfedb56`，sub-agent) · AI-SERVICE-CLIENT-ENV-RACE-1(`580304a`) · CANARY-WRITER-ENV-RACE-1(`d454c17`，sub-agent) · TICK-PIPELINE-MOD-UNUSED-IMPORTS-1(`c164cb6`，sub-agent) · 20:44 CEST `restart_all.sh --rebuild` 部署

**2026-04-20 批次歸檔**（14 項）：`docs/archive/2026-04-20--completed_todo_batch.md`
- Step 0 可行性 Sprint · MARKET-KLINES-STALE-1 · EXIT-FEATURES-TABLE-1 Phase 1b + GAP-1 · P1-7 A(`2a36a3f`)/B(`23b14ef`) · Track P T1-T5 骨架（6 commits）· P1-5 DRAWDOWN-RESET(`7cda4e4`)· P1-15(`b0df1b3`) · P1-16(`fef688e`) · P1-17 Winsorize · DYNAMIC-RISK-STATUS(`83a0475`) · E5-FN-2 Plan N(`f0f11c0`) · WATCHDOG-DNS-CLASSIFY-1 · E5-FN-3-FUP 全 5 agent audit wiring + 3 NITs · PYO3-ELIMINATE-1 全 3 Phase（`a84ecdb`/`0f8220b`/`9b691a0` — 1426 LOC 移除）

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
