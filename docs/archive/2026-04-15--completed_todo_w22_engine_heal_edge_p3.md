# 已完成 TODO 歸檔 — 2026-04-15（W22 ENGINE-HEAL + EDGE-P3-1 + GUI Fills）

> 自 `TODO.md` 於 2026-04-15 重整時切出。條目依主題分組，commit 為權威出處。
> 來源檔 snapshot：TODO.md commit `c51d10b` 之後的狀態。

---

## 🔧 ENGINE-HEAL 事故 follow-up 全數結清

2026-04-15 04:03 CEST 引擎 Fix 4 WS stale self-cancel 後空窗 7h10m，揭露 watchdog 未 daemon 化 + canary 同步寫盤拖死 event loop。FUP-1/2/3 + FIX-PHASE1 一條龍處理。

- **ENGINE-HEAL-FUP-1** ✅ watchdog systemd user unit 化（commit `933dd60`）
  - `~/.config/systemd/user/openclaw-watchdog.service`：`Type=simple` + `Restart=always` + `RestartSec=5` + `StartLimitBurst=5/60s`
  - `StandardOutput=append:/tmp/openclaw/watchdog.log`；`WorkingDirectory=/home/ncyu/BybitOpenClaw/srv`
  - `loginctl enable-linger ncyu` → 跨重啟存活；遷移後 PID 684057（PPID=1983 `systemd --user`）
  - flock `LOCK_EX|LOCK_NB` 單例 + `RESTART_BACKOFF_SECONDS=[60,120,300,600,3600]` + `MAX_CONSECUTIVE_FAILURES=5` circuit-break

- **ENGINE-HEAL-FUP-2** ✅ 根因調查完成（commit `33a1bb9`）
  - **TODO 原敘述更正**：非一秒 8,445 條，而是 ~2h 內 15+ 波段累積 8,446 條
  - **主因**：canary JSONL 在 `event_consumer/mod.rs:890-896` 以無 buffer `std::fs::File` + `writeln!` 在 `event_rx.recv()` select arm 同步寫盤；live ~280 ticks/sec × 2.5KB ≈ 700 KB/sec 同步 syscall + canary 檔 100GB+ FS cache 壓力 → consumer loop 卡 120s → Fix 4 觸發
  - **加劇**：live fan-out channel 512 vs paper/demo 1024（無設計理由）
  - **非因**：337 條 `fills flush failed`（V017 schema 未 apply）併發但不相關
  - worklog: `docs/worklogs/2026-04-15--engine_2000_stall_postmortem.md`

- **ENGINE-HEAL-FIX-PHASE1** ✅ R1+R2+FUP-3 合併（commit `5d5ec13`）
  - R1 canary 寫盤 → bounded mpsc 專用 tokio 任務 + `BufWriter` + size rotation
  - R2 live fan-out channel 512 → 1024 對稱化
  - FUP-3 `OPENCLAW_DISABLE_CANARY_DUMP=1` 全關 + `OPENCLAW_CANARY_ROTATE_MB`（預設 1024）+ `OPENCLAW_CANARY_MAX_ROTATED`（預設 3）
  - 驗收：1262 + 372 + 35 = 1669 cargo tests 0 fail
  - 部署：`restart_all.sh --rebuild`（commit `f57d421` worklog）

- **ENGINE-HEAL-FIX-PHASE1 FUP-A** ✅ canary_writer warn 節流（commit `6c73b60`）
  - `canary_writer` handle 加 `total_dropped: Arc<AtomicU64>` + `last_warn_ms: Arc<AtomicU64>`
  - `TrySendError::Full` 分支遞增計數器 + 1Hz CAS 節流 warn（避免 warn 自身變 log flood）
  - engine lib 1262 → 1264

- **ENGINE-HEAL-FIX-PHASE1 FUP-B** ✅ Full 分支單元測試（commit `6c73b60`）
  - `try_send_full_branch_drops_and_counts`：1-slot 通道驗證 Full 分支非阻塞 + 計數器單調 + clone 共享 Arc
  - `warn_throttle_caps_at_one_hz`：節流窗口測試

- **ENGINE-HEAL-DEPLOY** ✅（commit `7aa8e1c`）
  - PID 403560 binary mtime 2026-04-15 01:55，含 ENGINE-HEAL Fix 1/3/4 + FA-PHANTOM-1 leverage-aware margin + FUP-8 Phase 1/2 全數到位
  - DB 驗證：paper intents `submitted_qty` 真實 sized（0.47~31742），`is_sentinel=false`

- **E4-HYG-1** ✅（commit `0762006`）
  - `openclaw_core/tests/golden_extreme.rs:161` 加 `trailing_activation_pct: None`，`activation_pct` 默認 = `trail_pct` 2%
  - `cargo test -p openclaw_core` 372 pass 0 fail；engine lib 無迴歸

---

## 🚨 FA-PHANTOM-2 誤平倉根治

- **FA-PHANTOM-2 fix** ✅（commit `348a9c5`，spec `docs/references/2026-04-15--fa_phantom_2_fix_spec.md`）
  - **問題**：G-2 daemon 7h 0/20 fills 揭露 `max_drop_pct()` 掃全部 25+ 觀察幣種，任一小幣 5min 內抖 5% 即觸發 CloseAll → demo FA 8 次開倉 4-7 秒內全被 `risk_close:fast_track` 秒殺，0 次自然出口
  - **修復 3 處**：
    1. `PriceHistoryTracker::worst_drop_for_held(held_symbols)` + sigma 新方法
    2. `evaluate_fast_track` 新簽名 `(level, held_drop_pct, held_drop_sigma, margin_util)` + 分級升級規則：15% 無條件 CloseAll · 5%+3σ+Defensive+ CloseAll · 5%+3σ+<Defensive ReduceToHalf · 其他按舊梯度
    3. `on_tick.rs` 改傳 held 信號 + WARN 攜帶診斷字段
  - engine lib 1309 → 1318 (+9) · core 372 → 380 (+8)

- **FA-PHANTOM-1-FUP-7** ✅ operator 選 C（註釋 90% fail-safe）
  - `fast_track.rs:39-57` +19 行註釋說明：(a) 90% 是 Bybit MMR 物理常數不可 auto-scale；(b) margin_utilization_pct 已是 leverage-aware；(c) 當前高槓桿配置下不觸發是刻意兜底；(d) 反 pattern 警告不要為「看起來死碼」降閾值
  - 純註釋改動

---

## 🧠 EDGE-P3-1 Realized Edge Predictor — Stage 0 + Phase A + Phase B #1/2/4/5 + Step 7 全套 IPC

規格 `docs/references/2026-04-15--edge_predictor_spec.md`（v1.4，1101 行 · CC 13 項 · T1-T23 命名測試）。

### Stage 0 kickoff（commit `1366054`）
- spec v1.4 reality-alignment + V017 migration + entry_context_id threading

### Phase A — Rust gate 接線（3 commits）
- **A1-A4** ✅（commit `8c1f234`）— `edge_predictor/` 模組骨架 + `gate.rs` pure function + `IntentProcessor` 整合
- **A5** ✅（commit `3753ede`）— `feature_builder.rs` 13/17 features + `FeatureVectorV1` 穿透
- **A6** ✅（commit `a23b268`）— confluence + persistence features 從 OrderIntent plumb 入 feature_builder

### Phase B — bootstrap + backend + 同步機制（4/5 完成，#3 blocked on artifact）
- **#1 bootstrap** ✅（commits `c9416d0` + `0fcf449`）— main.rs 構造 `PerEnginePredictors` → 三引擎 Deps + `set_edge_predictor_store` 同步 IntentProcessor + debug_assert 防雙注入
- **#2 backend audit** ✅（commit `3dd845c`）— spec §7.1 tract-first / ort-fallback + Stage 2 precision-fail runbook：`docs/audits/2026-04-15--edge_predictor_backend_selection.md`
- **#4 RNG seeding** ✅（commit `a8426a9`）— `gate::seed_for_engine(startup_nanos, pipeline_kind)` 入 IntentProcessor；配套修 `TickPipeline::with_kind` 未 forward kind bug；+2 tests；lib 1307 → 1309
- **#5 pipeline_cmd_tx wire** ✅（commit `4dcf65a`）— `EventConsumerDeps.pipeline_cmd_tx` + `set_shadow_fill_tx` 三引擎注入，`EmitShadowFill` 脫離 fail-soft

### Step 7 — IPC 全套（5/6 完成，7b Python 路徑等 #26 artifact）
- **Step 7a DecisionFeatureSnapshot** ✅（commit `d73addb`）— Option B Rust-direct writer + passthrough IPC；`FEATURE_NAMES_V1` + schema/definition hash OnceLock；`decision_feature_writer.rs` async drain+dedup+DB-RUN-6 reject+`ON CONFLICT DO NOTHING`；lib 1264 → 1285 (+21)
- **Step 7b ReloadEdgePredictor 🟡 plumbing-only**（commit `72c028f`）— protocol + stub loader + handler + 4 tests；flag 仍 False；**Python route 暫不加**（等 ML-MIT #26 ONNX artifact）
- **Step 7c EmitShadowFill writer** ✅（commit `b469448`）— Option-B Rust-direct writer + passthrough IPC；`learning.decision_shadow_fills` + DB-RUN-6 epoch-0 reject + R5 `engine_mode=="paper"` 第二道防線；lib 1296 → 1303 (+7)
- **Step 7d SIGKILL durability** ✅（commit `a110892`）— `write_toml_atomic_fsynced()` helper + `test_write_toml_atomic_fsynced_survives_sigkill`（T23 CC #13）；`#[cfg(unix)]` 閘控；lib 1285 → 1286
- **Step 7e DisableEdgePredictorAll** ✅（commits `97777d5` + `01113a2`）— 兩階段 commit：Stage 1 disk-first `write_toml_atomic_fsynced` → Stage 2 `ConfigStore::apply_patch` ArcSwap → Stage 3 `EdgePredictorStore::clear_all()`；V014 `predictor_disabled_all` audit + operator_token hash；+3 tests；lib 1293 → 1296
- **Step 7f engine capabilities** ✅（commit `b88107f`）— `GET /api/v1/engine/capabilities` backward-compat probe；`feature_schema` + `ipc_methods` + per-engine edge_predictor 窄視圖；IPC 不可用仍 200 + `degraded=true`；+6 tests

### PA #63 Parquet ETL
- **#63 parquet_etl 擴展** ✅（commit `7f89add`）— `load_training_data()` 讀 `learning.decision_features` + JSONB → 17 列矩陣 + `EDGE_P3_FEATURE_NAMES` 順序凍結 + `export_decision_features_parquet()` reproducibility 逃生艙 + 4 新測試

### ML-MIT #26 Lane A — 訓練管線交付（commit `cdac922`）
- **#26 quantile LGBM 訓練管線** ✅ Lane A 純 Python 交付：
  - `quantile_trainer.py`：q10/q50/q90 pinball LGBM + CPCV + embargo carve-out + exp 樣本權重 + tail holdout + linear-QR floor + decile-lift bootstrap CI + schema hash
  - `calibration.py`：CQR 單邊 marginal + Romano 2019 有限樣本修正
  - `onnx_exporter.py`：三分位匯出 + POSIX-atomic symlink + per-file 1e-3 精度 gate
  - `quantile_reports.py`：5 gate + 樣本量桶 → ship/shadow/no_ship 裁決 + train-serve harness
  - `run_training_pipeline.py`：quantile 分支路由
  - **+47 tests**（ml_training 135 → 182 passed）
  - ONNX metadata_props stamp（commit `ba7b083`）：9 frozen `edge_p3_*` keys 寫入 ONNX bytes，Rust tract loader Slice 2 將 gate 在 `feature_schema_hash` parity

---

## 🏗️ ORPHAN-ADOPT-1 Phase 2A — 確定性 Adopt

- **ORPHAN-ADOPT-1 Phase 2A** ✅（commit `800633c`）
  - `PaperPosition.owner_strategy` 必選欄位 + `apply_fill` 7-arg 簽名（first-write-wins）
  - `OrphanStage::AdoptPositiveEdge` + `OrphanDecision::Adopt` Stage B2 = 任一 `KNOWN_STRATEGY` 在 orphan.symbol 上 `shrunk_bps > 0` 即 Adopt
  - `PaperState::adopt_orphan(...)` 冪等 + 輸入守衛 + `latest_prices` 預設 + `positions_insert` FUP 側車 mirror
  - `PipelineCommand::AdoptOrphan` + `event_consumer::handlers` 分派 + `dispatch_orphan_adopt`
  - V014 audit payload 擴 `owner_strategy` + `triggering_strategy`
  - +8 tests；lib 1285 → 1293

- **ORPHAN-ADOPT-FUP reconciler self-kill 抑制** ✅（commit `1677e3c`）
  - 反向連動問題：adopt 後 reconciler 把剛收養的 position 當 orphan 再砍一次
  - 修復：PaperState mirror 同步 `positions_insert` 讓 reconciler 視野對齊

---

## 🖥️ GUI 修復（2026-04-15 下半場）

### Fills PnL 鏈
- **recent_fills ring buffer 缺失** ✅（commits `1df0d70` + `2206cc2`）
  - `emit_close_fill` 增 `stats.total_fills` 寫 DB，**從不** push `recent_fills` → `pipeline_snapshot.recent_fills=[]` 但 DB 有幾百筆
  - Fix 1：`emit_close_fill` push `TimestampedFill`，`is_long` 反轉（position side → closing order side）
  - Fix 2：移除 `on_tick.rs` strategy_close 分支原本的重複 push（rf=33 vs tf=25 的謎底）
  - +2 回歸測試

- **closedPnl Rust → GUI 貫通** ✅（commit `00f1c57`）
  - Rust `ExecutionInfo` 加 `closed_pnl: f64`；`parse_execution_list` 以 `f64_field(item, "closedPnl")` 讀取
  - Python `_normalize_execution` 補 `closedPnl` 映射（用 `is None` 判斷，避免 0.0 開倉腿被 `or` 誤 fallback 到 `realized_pnl`）
  - `live/fills` endpoint 接同 normalizer

- **Orders camelCase normalize** ✅（commit `fa254e0`）
  - Rust `get_active_orders()` 回 snake_case，GUI 過濾讀 camelCase → 表格全空
  - 修：`tab-demo.html` 用 `_normalize_execution` 同型別 helper；`regular_count / conditional_count` 用 `Untriggered` 狀態計數

- **per-fill PnL 欄 + cumulative-PnL 放大圖** ✅（commit `8e06c54`）

### 腳本與重啟
- **fresh_start.sh + clean_restart.sh paper_state 修復** ✅（commit `63563d0`）
  - 新 `helper_scripts/fresh_start.sh`：clean_restart + DB 全清（PnL/手續費/勝率/經驗數據）；保留市場數據/model_registry/linucb archive/budget
  - 修 `clean_restart.sh`：不再歸檔 `paper_state.json`（paper 純虛擬，archive 掉冷啟動用 demo wallet 當 initial_balance + QoL-1 從 trading.fills 還原 realized/fees → 造成虛假 -$266.88 顯示虧損）
  - 更新 `README.md` + `SCRIPT_INDEX.md`：新增「常用腳本」5 類 + 快速對照表

---

## 📊 FUP-8 Phase 2 — Paper sentinel 根治

- **Paper sentinel 根治** ✅
  - `IntentResult` 加 `approved_qty: f64` 字段，`process()` 在成功路徑暴露 Kelly+P1 sizing 後的 `final_qty`
  - `on_tick.rs:721` 改傳 `result.approved_qty` 給 `persist_intent`
  - paper `submitted_qty` 現在記錄真實 sized qty（非 1e9 sentinel）
  - +2 測試 `test_fup8_phase2_approved_qty_{exposed_on_success,zero_on_rejection}`
  - **剩餘**：OrderIntent 加 `edge/funding_rate/basis/regime` 欄位 → 等 G-1 Strategist 接通

---

## 相關 worklog / audit 索引

- `docs/worklogs/2026-04-15--engine_2000_stall_postmortem.md` — Fix 4 觸發上游根因
- `docs/worklogs/2026-04-15--engine_self_healing.md`（延伸 2026-04-14）— ENGINE-HEAL 全程
- `docs/worklogs/2026-04-15--edge_predictor_spec_v1_to_v1_3.md` — 規格四輪演化
- `docs/worklogs/2026-04-15--fix_phase1_fup_ab_session.md` — FUP-A/B + E4-HYG-1
- `docs/audits/2026-04-15--edge_predictor_backend_selection.md` — tract-first / ort-fallback
- `docs/references/2026-04-15--edge_predictor_spec.md` v1.4 — 規格權威（1101 行）
- `docs/references/2026-04-15--fa_phantom_2_fix_spec.md` — PHANTOM-2 修復 spec
