# 2026-04-15 Daily Summary

EDGE-P3-1 Realized Edge Predictor spec v1.0→v1.4 四輪演化 + Stage 0/Phase A/A6 Rust 接線落地（1664 engine lib pass）· ENGINE-HEAL-FUP-2 post-mortem + FIX-PHASE1 offload canary write + FUP-A/B throttle + watchdog systemd 正式化 + 122GB→519MB rotation 首次壓測 · ORPHAN-ADOPT-1 FUP 引擎自殺根因修復 + Phase 2A deterministic adopt 基礎設施 · GUI P&L 可視化 Step 1 三 tab 統一 · Lane A ML-MIT #26 trainer 交接備忘。

## 完成項目 / Completed

---

### 1. EDGE-P3-1 — 規格 v1.0→v1.4 + Stage 0/Phase A/A6 Rust 接線

#### 1.1 Spec 四輪演化（commit `9141e08`）

**規格文件**：`docs/references/2026-04-15--edge_predictor_spec.md`（816 → **1101 行**）

**演化軌跡**：
```
v1.0 ─ round-1 ─→ v1.1 ─ round-2 (F1-F10) ─→ v1.2 ─ round-3 (U1-U4 + M1) ─→ v1.3 ─ round-4 GREEN ─→ v1.4 reality align
```

| 輪次 | 審查者 | 主要產出 |
|---|---|---|
| Round-1 | QC + QA | v1.1 初版整合（約 800 行）|
| Round-2 | QC + QA + ML-MIT + AI-E 四路平行 | **7 共識 must-fix**（F1-F7）+ F8-F10 補強（816 → 1019 行）|
| Round-3 | 同上 | AI-E YELLOW：U1-U3 real gaps（讀 Rust 源碼反驗）+ U4 + M1 Mac CI（1019 → 1101 行）|
| Round-4 | AI-E covering review | **GREEN — Stage 0 開工許可** |

**F1-F10 關鍵修復**：
- **F1** grid_trading VWAP merge vs 其他策略 qty-weighted blend label 口徑統一
- **F2** §7.3 pseudocode `load_for()` 順序（改在 `age_seconds()` 之前）
- **F3a** `disagreed` NULL 污染 → `COALESCE` · **F3b** `DisableEdgePredictorAll` 持久化 `RiskConfig.toml` + fsync
- **F4** `learning.decision_shadow_fills` 新表 + `CHECK (engine_mode='paper')` 雙閘（三審一致）
- **F5** T1..T22 具名測試 · **F6** Live/Demo fallback 首次即 P2 · **F7** CHANGELOG 不誤宣稱 slippage feature
- **F8** Cargo feature `compile_error!` 互斥 · **F9** RwLock guard drop discipline + `SmallRng` per-engine 種子 · **F10** runbook 路徑明文

**U1-U4 + M1**（AI-E 直讀 Rust 源碼找出的 spec-vs-reality 差異）：
- **U1** `RevokeExecutionAuthority` 是 Python-layer 概念非 Rust IPC → auth envelope 明拆 Python `_EXECUTION_AUTHORITY_OVERRIDE` + Rust `operator_token` UUID v4 len≥32
- **U2** 讀 `config/store.rs:231-244` 發現 `write_toml_atomic()` 無 `File::sync_all()` / 無父目錄 fsync → 新 helper `write_toml_atomic_fsynced()` + CC #13 `strace -e fsync` 驗證
- **U3** `emit_shadow_fill_ipc()` IPC 形狀未定義 → `PipelineCommand::EmitShadowFill { context_id, strategy, symbol, features_jsonb, prediction, cost_bps, ts_ms }`
- **U4** 多引擎 TOML partial-failure 兩階段提交（stage 1 全 fsync / stage 2 全 swap）
- **M1** CI tuple `aarch64-apple-darwin` 顯式要求（operator 確認部署目標 M5 Ultra/Max），排除 `aarch64-unknown-linux-gnu`

**副產物 memory**：`~/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/project_mac_deployment_target.md` 新增（Apple Silicon Mac 未來部署目標），MEMORY.md 索引同步。

**v1.4 reality-alignment 5 處**（Stage 0 pre-flight 發現）：
- **R1** `learning.decision_context_snapshots` → 改用 `trading.*` 命名空間（實際 V003:40）
- **R2** 復用 `fills.context_id` 不可行（`emit_close_fill` 在 `tick_pipeline/mod.rs:1025` 用 `make_context_id(em, symbol, ts_ms)` 合成 close-time 新 id，復用=100% JOIN mismatch）→ 加新列 `entry_context_id TEXT NULL`
- **R3** `audit.events` → 實際用 V014 `observability.engine_events` append-only hypertable
- **R4** `ON CONFLICT (context_id) DO NOTHING` hypertable 複合 PK `(context_id, ts)` → 複合鍵
- **R5** `disagreed GENERATED ALWAYS AS ... STORED` TimescaleDB 2.x 不支援 → 普通 BOOLEAN + Rust 寫入時計算

#### 1.2 Stage 0 Kickoff — V017 + entry_context_id 串接（commit `1366054`）

**硬性約束**（ML-MIT + AI-E 共同警告）：V017 與 Rust 必須**同窗口落地**，否則新列 100% NULL = silent label loss。

**SQL migration** `sql/migrations/V017__edge_predictor_tables.sql`：
- 新表 `learning.decision_features`（PK `context_id`，14 欄）
- 新表 `learning.decision_shadow_fills`（BIGSERIAL PK + CHECK `engine_mode='paper'`）
- ALTER `trading.decision_context_snapshots` ADD 7 欄（predicted_q10/q50/q90/predictor_decision/shrinkage_decision/disagreed BOOLEAN/predict_latency_us）
- ALTER `trading.fills` ADD `entry_context_id TEXT NULL` + partial index

**Rust 串接策略**：`apply_fill` 有 40+ call site，改簽名成本過高 → 用 `PaperPosition.entry_context_id: String`（`#[serde(default)]` 向下相容 pre-V017 snapshot）+ setter/getter pattern。

**核心設計**：`make_context_id(em, symbol, ts_ms)` 是決定性函數 → open 時 stamp 的 id 與未來 Fill row 的 `context_id` 完全一致，為訓練 JOIN 提供強鍵。

**三態消歧**（`commands.rs::place_order_command` / `apply_confirmed_fill`）：
- `was_open=true, realized==0` → 新開倉 stamp
- `was_open=false, realized!=0` → 平倉用 existing_entry_ctx
- `was_open=false, realized==0` → 累倉不動（空字串 setter 是 no-op 保護）

**`on_tick.rs` 7 close 路徑 + 1 open stamp 全覆蓋**：fast_track_reduce_half / fast_track / h0-blocked stops / paused stops / strategy_close / risk_close / halt_session / strategy open。

**附帶 AI-E U2 落地**：`write_toml_atomic_fsynced` helper（寫 tmp + fsync + rename + open parent + fsync parent）。

**測試結果**：engine lib **1144 → 1158**（+14）· core 372 · e2e 35 · 0 fail · 13 files · +980/-53 lines。

#### 1.3 Phase A — Predictor Gate Wiring（commits `8c1f234` + `3753ede`）

**A1 TOML schema**：`EdgePredictor` struct 8 字段，**預設 `use_edge_predictor=false`**（部署時零行為改變）

**A2 PipelineCommand 3 variants**：
- `SetEdgePredictorShadow { strategy, shadow }` per-strategy toggle
- `DisableEdgePredictorAll` kill-switch（呼叫 `EdgePredictorStore::clear_all()`）
- `EmitShadowFill { context_id, strategy, features_jsonb, ... }` ε-greedy 訓練樣本

**A3 `edge_predictor/gate.rs`（新）**：純函數 `edge_predictor_gate()` 按 §7.3 F2 正確順序：
```
feature sanity(all_in_range) → load_for(strategy) → staleness → predict()
→ monotone rearrangement → cost margin → ε-greedy(paper only) → q10-add guard
```
Outcome: `Accept / Reject / RejectAdd / ShadowFill / Fallback`。`seed_for_engine(kind)` 確定性 per-engine `SmallRng` seed 避免三引擎 RNG 共享污染。

**A4 IntentProcessor**：`process_with_features()` / `process_gates_only_with_features()` 新入口（保留舊 `process()` 不改，29 call site 成本過高）。政策層：
- `use_edge_predictor=false` → fall-through JS gate
- `shadow_mode=true` → observe + metric + fall-through
- `Accept` → 短路通過 · `Reject/RejectAdd` → 短路拒絕
- `ShadowFill` → 發 `EmitShadowFill` IPC + fall-through
- `Fallback` → 按 `fallback_on_error` 政策路由

**A5 Feature Builder**（`edge_predictor/feature_builder.rs` 383 行 + 11 tests）：
- **Regime 5**：adx_1h / bb_width_pct / atr_pct / funding_rate / realized_vol_1h
- **Microstructure 3**：basis_bps / orderbook_imbalance_top5 / spread_bps
- **Strategy 3**：confluence_score / persistence_elapsed_ms（A5 階段 zeroed 佔位）/ side (±1)
- **Position 3**：notional_pct_of_bal / concurrent_positions / same_direction_cnt
- **Time 3**：tod_sin / tod_cos / is_funding_settlement_window（Bybit 8h 窗口最後 15min）

**`FeatureVectorV1::to_jsonb()` hand-rolled**（17 key 固定 schema）：NaN/Inf → `null`（Postgres JSONB 要合法 JSON），下游 `WHERE feature IS NOT NULL` 自然排除。

**`on_tick.rs` 兩 call-site 串接**：Exchange branch L627 + Paper branch L703 對稱走 `process_with_features()`。

**Phase A 測試**：engine lib 1158 → **1249**（+91）· 0 fail。

#### 1.4 Phase A6 — Strategy-Side Feature Plumbing（commit `a23b268`）

A5 的 `confluence_score` 和 `persistence_elapsed_ms` 以 0.0 佔位 — A6 把真值從策略內部 state 穿透到 `OrderIntent` → `feature_builder`。

**OrderIntent schema 擴充**：
```rust
#[serde(default)] pub confluence_score: Option<f32>,
#[serde(default)] pub persistence_elapsed_ms: Option<u64>,
```
Option + default 三理由：跨版本 IPC 兼容 / 語意忠實（Grid/FundingArb 無 confluence 用 `None` 比 `0.0` 誠實）/ 零前向污染。

**`PersistenceTracker::elapsed_ms()` 只讀訪問器**：現有 `check()` 既更新 state 又返回 bool，A6 需不改 state 讀取「信號開始後多久」。

**5 策略填值**：
| 策略 | confluence_score | persistence_elapsed_ms |
|---|---|---|
| MaCrossover / BbReversion / BbBreakout | `score as f32` | `elapsed_ms(symbol, ts_ms)` |
| GridTrading / FundingArb | `None` | `None` |

**Builder 雙保險 clamp**：`clamp_f32(confluence, 0.0, 65.0)` · `clamp_f32(persistence, 0.0, 3_600_000.0)` — 策略理論上已合規，builder 再夾一次防禦 `all_in_range` invariant #12。

**21 fixture 站點批次更新**（`intent_processor/tests.rs` ×13 / `mode_state.rs` ×1 / `orchestrator.rs` ×2 / `strategies/mod.rs` ×1 / `stress_integration.rs` ×4）：用 Python regex 一次 run 完成。

**測試增量**：engine lib 1249 → **1257**（+8）· 合計 **1664 pass / 0 fail**。

#### 1.5 Lane A — ML-MIT #26 Trainer 交接備忘

**文件**：`docs/worklogs/2026-04-15--lane_a_ml_mit_26_trainer_handover.md`（本 session 未動手，compact 後新 session 照此備忘直接開工）

**Why 現在做不等數據**：FA-PHANTOM-2 修復前 demo 無 clean labels，但 trainer 代碼用合成資料單元測試即可驗證正確性；不提前寫好，trainer 是那個窗口期的下一個瓶頸。

**新增文件規劃**（純 Python，不觸 Rust）：
- `quantile_trainer.py` ~400 行：三分位 LightGBM (q10/q50/q90) + CPCV + sample weight exponential decay + floor baseline（linear QR）
- `calibration.py` 擴展 ~150 行：CQR offset (Romano et al. 2019) + isotonic fallback
- `onnx_exporter.py` 擴展 ~80 行：per-quantile ONNX 匯出 + `_current` symlink + precision < 1e-3 驗證
- `quantile_reports.py` ~200 行：§6.2 六項驗收指標 + should_ship / shadow_only / no_ship 三檔結論
- `run_training_pipeline.py` 擴展：`use_quantile_predictor=True` 分支

**驗收門檻**（spec §6.2）：pinball skill > 0.10 · coverage error < 3pp · decile lift 1000-bootstrap 95% CI 下界 > 1.3 · quantile crossing < 1% · LGBM vs linear QR ≥ +5pp · train-serve skew < 1e-3 · 樣本量閘 n≥500 prod / 200-499 shadow / <200 無模型。

**funding_arb carve-out**：embargo=72h × 5-fold 導致每 fold ~100 樣本，Stage 2 按當時樣本量改 3-fold 或擴窗 60d。

---

### 2. ENGINE-HEAL — FUP-2 Post-Mortem + FIX-PHASE1 + FUP-A/B + watchdog systemd

#### 2.1 Post-Mortem（`2026-04-15--engine_2000_stall_postmortem.md`）

**TL;DR**：Fix 4 (WS-stale 120s watchdog) 在 02:03:05.327Z 觸發，原因是 live consumer 已**持續 ~2 小時**掉 tick（**非 TODO 宣稱的一次性 8,445 條**）。根因 = **同步檔案 I/O 在 live event loop 熱路徑**（canary JSONL writer 無 buffering），加上非對稱 channel sizing（live 512 vs paper/demo 1024）。

**TODO.md 敘事更正**：02:00 那次爆發只是 **464 drops**；總計 8,446 分散於 **15+ 個離散爆發窗口** 跨 118 分鐘。真實模式是**慢性反覆欠容量**，非單次急性事件。

**Root cause 定位**（`event_consumer/mod.rs:878-990`）：select-arm 在 `event = event_rx.recv()` 分支內做：
1. `pipeline.on_tick(&ev)` — CPU 正常
2. **Canary write（L889-897）**：`writeln!(f, ...)` 對 `&std::fs::File`（無 `BufWriter`、無 `tokio::fs::File`）同步 syscall，每 tick 2-3 KB JSON，~280 ticks/s 跨 25 symbols = **~700 KB/sec 序列化 + syscall**
3. `audit_writer.append()` — 低頻但同模式

**三個複合因素**：
- Live 4 worker threads，任一 thread 阻塞 I/O 就少 25% CPU
- Canary file 已 **~42M lines / ~100GB+**，filesystem cache pressure 非零
- Live **512-slot** fan-out channel 飽和時間是 paper/demo 1024 的一半

**Fix 4 量測的是 consumer 健康而非 WS 健康**：`shared_last_tick_ms` 在 consumer arm 更新；stall_ms=135,201 表示 consumer 135s 沒拉到單一 tick，完全 consistent with consumer loop blocked on sync I/O。

**V017 schema mismatch**（337 `entry_context_id does not exist` warn）是**並行 observability gap 非 contributor**：`flush_fills` 清空 buffer on error 不 back-pressure upstream。但揭露部署次序問題：engine binary 含 entry_context_id code 比 V017 applied 先走（02:03 crash 時 V017 尚未 apply，09:09Z 才 apply）。

#### 2.2 FIX-PHASE1 — Offload Canary Write（commit `5d5ec13`）

**R1 全 offload**：bounded `mpsc::channel::<String>(4096)` → 專用 tokio task + `BufWriter::with_capacity(64KB, file)` + size rotation（`OPENCLAW_CANARY_ROTATE_MB=1024` 預設）。Event loop 分支變 `try_send → warn on full`（與 `trading_tx` 同 pattern）。0 syscalls on hot path。

**R2 Symmetric channel**：Live fan-out **512 → 1024**（一行改，對稱化 paper/demo）。

**Deferred**：R3a worker_threads 4→6（等 R1+R2 telemetry）· R3b consumer 架構拆分（large refactor）· R4 separate `producer_last_tick_ms` metric（需 R1 先 bed in）。

#### 2.3 FUP-A/B — Warn Throttle + Full Branch Tests（commit `6c73b60`）

E2 審查 GREEN 但兩條 nit 未阻塞合併：持續壓力下 `try_send` 每次 `warn!` 自身成為 log flood；缺 `TrySendError::Full` 分支單元測試。

**FUP-A**：`CanaryWriterHandle` 加 `Arc<AtomicU64>` pair：
- `total_dropped`：單調遞增（跨 clone 共享）
- `last_warn_ms`：CAS gate 決定本次是否有資格 log
- `WARN_THROTTLE_MS = 1000`：多執行緒競爭同窗口最多一人勝出
- warn 消息內嵌 `total_dropped` — 運維看到的是**累積丟棄數**（單調）而非單次事件

**FUP-B** 兩新測試：
- `try_send_full_branch_drops_and_counts`：1-slot mpsc，4 次 try_send 走 Full 分支，counter=3，clone handle 再 try_send counter=4（驗證 Arc clone 語意）
- `warn_throttle_caps_at_one_hz`：`should_emit_warn()` 首呼 true、立即二呼 false

**E4-HYG-1**（同 commit `0762006`）：`rust/openclaw_core/tests/golden_extreme.rs:161` 補齊 `StopConfig.trailing_activation_pct: None`（`51f6744` 引入新欄位時漏更新此測試），core 從編譯失敗恢復至 372 pass。

#### 2.4 FIX-PHASE1 Binary 部署（14:55 PID 693387）

**關鍵證據**：rebuild 瞬間 `/tmp/openclaw/engine_results.jsonl` 從 **122GB 重置為 519MB**（6 分鐘後 584MB）→ 首次真實運行時驗證 `5d5ec13` 的 bounded mpsc + BufWriter + size rotation 承諾。

**記憶庫誤導修正**：`feedback_restart_rebuild_flag_scope.md` 原 name「只重 PyO3 不重 engine binary」已過時（2026-04-14 FA-PHANTOM-1 修復後 `--rebuild` 同時重建兩者）→ 本 session 差點誤導決策走雙步驟 `cargo build && --engine-only`，及時 grep 腳本驗證才發現記憶過時。frontmatter + body 同步更新。

#### 2.5 ENGINE-HEAL-FUP-1 — Watchdog systemd 正式化

**事故鏈**：02:03 Fix 4 self-cancel → 02:03→09:13 **空窗 7h10m**（watchdog daemon 從未部署，`restart_all.sh:187` 只跑一次性 `--status`）→ operator 09:13 手動重啟 → 11:31 臨時 nohup PID 592881（跨重啟不存活）→ 14:25 升級 systemd user unit 正式結清。

**前置條件驗證**（先 audit 代碼再動手，避免重複造輪子）：
- `loginctl show-user ncyu` → `Linger=yes` ✅
- `engine_watchdog.py:508` 已有 `fcntl.flock LOCK_EX|LOCK_NB` 單例保護
- `engine_watchdog.py:523` `SIGTERM/SIGINT` handler 優雅釋放 flock
- `RESTART_BACKOFF_SECONDS = [60,120,300,600,3600]` 已實作
- `MAX_CONSECUTIVE_FAILURES = 5` circuit-break 已實作
- `RESTART_COMMAND = ["bash", "helper_scripts/restart_all.sh", "--engine-only"]` 已實作

**新 unit** `~/.config/systemd/user/openclaw-watchdog.service`（與 `openclaw-gateway.service` 同路徑，符合慣例，**不在 repo 內**）：
```ini
Type=simple
WorkingDirectory=/home/ncyu/BybitOpenClaw/srv
ExecStart=/usr/bin/python3 helper_scripts/canary/engine_watchdog.py \
  --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --poll-interval 2
Restart=always
RestartSec=5
TimeoutStopSec=30
KillSignal=SIGTERM
StandardOutput=append:/tmp/openclaw/watchdog.log
```

**遷移**：`kill -TERM 592881` → `systemctl --user daemon-reload` → `enable --now` → 新 PID 678153 PPID=1983（systemd --user）非 PPID=1 孤兒 · flock 正確轉交 · boot symlink 建立。

**不做 kill -9 engine 壓測**：會打斷 G-2 daemon + 活倉位；單例/退避邏輯在 commit `4e09c09` Fix 2 已單元測試過，systemd Restart=always 是成熟 proven 機制。

---

### 3. ORPHAN-ADOPT-1 — FUP 引擎自殺修復 + Phase 2A 接管基礎設施

#### 3.1 FUP — Engine Self-Kill Root-Cause Fix

**現象**：Phase 1 deployment 後 ~3 小時窗口 demo 策略自主新開 85 entries / reconciler reaper 平倉 76 closes（~89% ratio）· funding_arb 7 entries / 0 natural exits 全被 reaper 收掉 · 平均每倉存活 30–60s。G-2 daemon 停滯 root cause = 此 bug。

**根因**：`position_reconciler::process_orphans()` 30 秒輪詢週期的 REST snapshot 對比「上一輪 baseline」，產生 `DriftVerdict::Orphan` = 「當前 Bybit snapshot 有、上一輪 baseline 沒有」。**baseline 的「上一輪」在時間上落後於策略剛剛送出並 fill 的新倉**：
```
t=0s:    baseline 空
t=5s:    策略 fire intent → Bybit 成交 → paper_state.apply_fill()
t=30s:   reconciler cycle → REST snapshot 看到新倉 → baseline 沒有 → classify Orphan
t=30.1s: process_orphans() 未做 cross-check → dispatch CloseSymbol
t=30.5s: 引擎平掉自家剛成交的倉
```

**Option B 根治**（operator 明示「B 從根本上修」）：

**Side-car mirror pattern**：`PaperState` 掛 `positions_mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>`（symbol → is_long）。Writer = PaperState 本身（apply_fill / upsert / close_position / reduce_position / import_positions / reset 六路徑全同步）；Reader = `OrphanHandlerConfig.engine_positions_mirror`（reconciler cycle 開頭 snapshot 一次）。同 Arc 在 reconciler spawn 時建立，`EventConsumerDeps.positions_mirror` 在 `run_event_consumer()` 內 `set_positions_mirror(...)` 注入。

**Suppression 時機**：`process_orphans()` cycle 頂層 snapshot 一次，逐個 Orphan 檢查 `tracked_is_long == expected_is_long` → `continue`（**完全丟棄 verdict**，連 `evaluate_actions` 也看不到）。Suppression 發生在 dedup stamp 與 dispatch **之前**：不下平倉單、不登記 dedup、不產生 drift 證據給 `evaluate_actions()` 不升級 RiskLevel。

**為何不直接讀 `PaperState.positions`**：`PaperState` 是 `TickPipeline` 欄位，reconciler 跑背景 task，直接借用違反 `&mut self` 獨占律。Side-car Arc + parking_lot RwLock 非毒化、tokio await-safe、test 可獨立構造。

**Reset 指令保 Arc**：`PipelineCommand::Reset` 替換 PaperState 時 `let shared_mirror = pipeline.paper_state.positions_mirror(); ... set_positions_mirror(shared_mirror);` 保留同一 Arc，clear 但不斷連。

**測試**（2 新）：
- `orphan_suppressed_when_engine_owns_position` 正向（mirror 塞 BTCUSDT Long + raw Buy → kept.is_empty() / pending_orphan_closes 空）
- `orphan_dispatched_when_engine_side_mismatches` 反向保底（mirror Long + raw Sell → 正常 Stage C `SoftConservative` → CloseSymbol）

**結果**：engine lib 1266 pass / position_reconciler 60 pass · Delta +319 / -10（8 files）。

#### 3.2 Phase 2A — Deterministic Adopt Infrastructure

**背景**：Phase 1 + FUP 解決「detect-but-do-nothing orphan」與「engine self-kill」，但**真正外部來源孤兒**仍走 Stage C `SoftConservative` close-everything。Phase 2 原本 deferred 等 G-1 R-02 AI Strategist 提供「同方向信號」語義；Phase 2A 是非 agentic sub-option：**用 `edge_estimates` 作為客觀 deterministic proxy**。

**核心規則**：若任一 `KNOWN_STRATEGY` 在 orphan symbol 上有 positive shrunk edge → adopt。Edge sign 是 per-symbol 指標**非方向信號**；exchange-reported side 保留，StopManager 夾下行。

**Schema 擴充**：`PaperPosition` 新增 required `owner_strategy: String`：
- 策略 fill 寫 `intent.strategy`（`ma_crossover` 等）
- `import_positions` + `upsert_position_from_exchange` insert branch 寫 `"bybit_sync"`
- `adopt_orphan` 寫 `ORPHAN_ADOPTED_STRATEGY = "orphan_adopted"`
- upsert update branch **preserves** existing owner — ma_crossover 收到 WS size/avg_price 更新不會被改寫為 `"bybit_sync"`
- `apply_fill` 加第 7 位置參數 `owner_strategy: &str`；同方向 accumulate **first-write-wins**
- `#[serde(default)]` 確保 pre-Phase-2A snapshot 可載入

**Orphan decision — Stage B2 adopt rule**：新 `OrphanStage::AdoptPositiveEdge`；`handle_orphan()` B1/B2 變：
1. 任一 known strategy `shrunk_bps > 0` → **B2 Adopt**（記錄首個 per `KNOWN_STRATEGY_NAMES` order 作 `triggering_strategy` PnL 歸因）
2. 否則 `unrealised_pnl > 0` → B1 `SoftLockProfit` close（不變）
3. 否則 Stage C `SoftConservative`（原則 #6）

Stage A（liq distance / CB / notional cap / scanner universe）嚴格先於 B — safety check 永不讓位給 adopt。

**Injection path** — `PaperState::adopt_orphan(symbol, is_long, qty, entry_price, ts_ms) -> bool`：
- Idempotent 同方向已持倉 → no-op
- Reject `qty ≤ 0` / 非 finite / `entry_price ≤ 0`
- Seed `latest_prices` 讓 StopManager 有立即 tick
- 呼叫 `positions_insert` helper → FUP side-car mirror 自動更新，防下輪 reconcile 重 classify

**`PipelineCommand::AdoptOrphan`** fire-and-forget + handler arm → `paper_state.adopt_orphan(...)` + 成功 insert 強制寫 snapshot。

**`dispatch_orphan_adopt(decision, pos, cmd_tx)`** 與 `dispatch_orphan_close` 並列；用 `pos.avg_price`（Bybit per-position avg cost）作 adoption `entry_price`。兩 dispatcher 拒絕錯誤 decision variant 並 warn + `return false`（無 silent misroute）。

**Audit 擴展**：V014 JSON payload 加 `owner_strategy`（adopt=`"orphan_adopted"`/close=`null`）+ `triggering_strategy`（adopt=正 edge 策略名/close=`null`），下游 analytics 可直接歸因無需 parse `reason` text。

**測試**（8 新）：
- `orphan_handler.rs` 5：Long/Short adopt / no positive edge 落入 SoftConservative（strict `>0` 非 `>=0`）/ 多正 edge first by KNOWN_STRATEGY_NAMES order / Stage A liq_close precedence over B2
- `paper_state.rs` 3：`test_adopt_orphan_inserts_and_mirrors` / `test_adopt_orphan_idempotent_same_direction` / `test_adopt_orphan_rejects_invalid_inputs`

**Side-effect**：`PipelineCommand::DisableEdgePredictorAll` WIP（Step 7e hardening）在 working tree，為 unblock build 加最小 handler + `FIXME(Step 7e)` pointer + len≥32 token 檢查；完整 two-phase commit + audit writeback 仍 pending。

**測試結果**：`cargo test --lib` 1285 → **1293**（+8）· e2e 35 · core 372 = **1700 total / 0 fail**（vs prior 1692）。

---

### 4. GUI P&L 可視化 Step 1 — PnL 欄 + 拉高 trend + 三模式統一

#### 4.1 背景

Operator 反映 Paper tab 成交歷史「最近 50 筆」看不出哪筆賺虧、無每日曲線或百分比。

**後端審計四點現況**：
1. **Paper `/api/v1/paper/fills`**：Rust `TimestampedFill` struct 僅 `timestamp_ms/symbol/is_long/qty/price/fee/strategy` — **沒有 `realized_pnl`**。前端 `f.realized_pnl || 0` fallback 永遠為 0
2. **DB `trading.fills`** 早有 `realized_pnl`（real 欄位），按 `engine_mode` 分區（V015）。近 7 日 paper 1443 closes / demo 599 closes
3. **Demo/Live fills endpoint** 直透 Bybit v5 `closedPnl`（string）
4. **Paper 已有 sparkline** `tab-paper.html:77-82` 但 height=48 被壓扁，Demo/Live 無此元件

**兩階段方案**：Step 1 純前端 + 一次 Python 端點改寫，零 Rust 改動零引擎重啟；Step 2（未做）新增 `/api/v1/{mode}/daily-pnl` 聚合端點 + Chart.js equity curve。

#### 4.2 改動

**`common.js` 兩共用 helper（+75 行）**：
- **`ocPnlCell(raw)`**：`|pnl|<0.0001` 或非數 → 灰 `—`；正 → 綠 `+x.xxxx`；負 → 紅 `-x.xxxx`；接受 number 或 string（`parseFloat` 處理 Bybit string `closedPnl`）
- **`ocPnlTrend(lineId, labelId, fills, zeroLineId)`**：fallback 鏈 `realized_pnl || closedPnl || pnl || 0`；最舊在左最新在右；y 軸 `[min(series, 0), max(series, 0)]` **強制包含 0**；傳 `zeroLineId` 自動調虛線零基準；最終值決定線色

**Paper/Demo/Live 三 tab 統一**：
- 表頭加 `<th>盈亏 / PnL</th>` colspan 7→8（所有 empty/loading/error row）
- 每筆渲染 `ocPnlCell(f.realized_pnl || f.closedPnl)`
- **Paper** SVG height 48→120 / viewBox `0 0 400 120` / stroke-width 1.5→2 / 新增 `<line>` 虛線零線 / 刪除原 inline `updatePnlSparkline()` 改呼叫 `ocPnlTrend(...)`
- **Demo/Live** PnL Overview 卡片底部新增 SVG 塊（同規格，ID prefix `demo-pnl-*` / `live-pnl-*`）
- **Live 行為變更**：`refreshPage()` 現在每 15s 無條件呼叫 `loadFills()` 讓 trend chart 保持即時（Bybit `v5/execution/list` 15s 一次成本可忽略）；表格本身仍折疊懶加載

**`paper_trading_routes.py:596` `/api/v1/paper/fills` 改寫（+43 行）**：
- **原行為**：Rust IPC 讀 `recent_fills`（in-memory ring buffer 50 上限）
- **新行為**：優先 PG `trading.fills WHERE engine_mode='paper' ORDER BY ts DESC LIMIT ?`，Rust IPC 降為 DB 不可用時備援
- **理由**：DB 由 Rust `trading_writer` 同步寫，延遲 μs 級與 in-memory 等效；DB 有 `realized_pnl` 而 Rust struct 沒；**避免 Rust rebuild**（14:55 剛 rebuild，避免二度擾動 G-2 daemon）
- 欄位映射：`ts` → `timestamp_ms` / `side` "Buy/Sell" 直透 + `is_long = (side=="Buy")` fallback / `category` 按 symbol 後綴推斷
- Response 包 `source: "pg_trading_fills"` 方便 DevTools 驗證

#### 4.3 部署與驗證

- `restart_all.sh --api-only` → uvicorn PID 857922
- Rust 引擎無變動（PID 693387 繼續 FIX-PHASE1 binary）
- Watchdog / G-2 daemon / canary rotation 皆未受影響

**已知未解**：用戶硬刷後 Paper tab 仍顯示全 `—`（高機率 browser cache）。接手時 DevTools Network 檢查 `source` 欄位即可判別（`pg_trading_fills` 表示走新路徑，`rust_engine` 表示 DB pool 有問題）。

---

## 測試基準線 / Test Baseline

| Suite | 進入本日 | 離開本日 | Δ |
|---|---|---|---|
| `openclaw_engine --lib` | 1144 | **1293** | +149 |
| `openclaw_core --lib` | 372（短暫 E4-HYG-1 編譯失敗） | 372 | ±0 |
| `openclaw_engine --tests` (e2e) | 35 | 35 | 0 |
| **合計** | 1551 | **1700** | +149 |

Python 2852 pass 不變（Lane A ML-MIT #26 尚未動手；Step 1 GUI 無後端測試增量）。

---

## 關鍵決策 / Decisions

1. **EDGE-P3-1 Stage 0 V017 與 Rust 必須同窗口落地**（ML-MIT + AI-E 硬約束）— 分開部署 = 新列 100% NULL = silent label loss，等同被推翻的 R2 Option A
2. **新欄位 `fills.entry_context_id` 而非復用 `context_id`** — `emit_close_fill` 用 `make_context_id(em, symbol, ts_ms)` 合成 close-time 新 id，復用 = 100% JOIN mismatch
3. **Phase A `use_edge_predictor=false` 預設** — 部署時零行為改變，operator 需明確切開關才走新路徑
4. **Hand-rolled `to_jsonb()` 不用 serde** — 17 key 固定 schema，lazy closure 只在 shadow branch 付代價，NaN/Inf → `null` 下游 JSONB 合法
5. **OrderIntent 新 feature 用 Option + `#[serde(default)]`** — 跨版本 IPC 兼容 + 語意忠實（Grid/FundingArb 無 confluence 用 `None` 比 `0.0` 誠實）
6. **ENGINE-HEAL 採 R1 全 offload 而非 BufWriter 半吊子** — Canary JSONL 是診斷，必須永不影響 runtime
7. **Canary warn 用 `Arc<AtomicU64>` CAS 1Hz throttle + 單調累積 counter** — 兩個 atomic 分離關注點避免 counter 語意被 log cadence 污染
8. **ORPHAN-ADOPT FUP 用 side-car mirror 而非直接借 `PaperState.positions`** — reconciler 背景 task 借用違反 `&mut self` 獨占律；parking_lot RwLock 非毒化 tokio await-safe
9. **Suppression 發生在 dedup stamp 與 dispatch 之前** — 不下平倉單、不登記 dedup、不產生 drift 證據給 evaluate_actions 升級 RiskLevel
10. **Phase 2A 用 `edge_estimates` 作 deterministic proxy 而非等 G-1 R-02 AI Strategist** — 解除 Phase 2 blocking；Strategist 落地後可升級為「would_take 語義」fast-path/slow-path 分層
11. **GUI Step 1 走 PG 旁路而非 Rust struct 補欄位** — 避免 Rust rebuild 二度擾動 G-2 daemon；DB 已有權威欄位，μs 級延遲等效 in-memory
12. **Watchdog 升級 systemd user unit 不做 kill -9 壓測** — 會打斷 G-2 + 活倉位；單例/退避邏輯 `4e09c09` 已單元測試過，systemd Restart=always 成熟 proven

---

## 遺留項 / Remaining

1. **GUI Step 2**（非阻塞）：`/api/v1/{mode}/daily-pnl` 端點 + Chart.js equity curve
2. **Rust `TimestampedFill` struct 補 `realized_pnl`**（非阻塞）：Python 旁路已可用，下次 Rust rebuild 機會順手補
3. **ORPHAN-ADOPT Phase 2A → Strategist upgrade**（G-1 R-02 W22-W23）：positive shrunk edge 升級為「Strategist would_take(symbol, side)」語義
4. **DisableEdgePredictorAll Step 7e 完整 two-phase commit + audit writeback**（Phase 2A 帶入 FIXME pointer）
5. **CSP 噪音**（operator 提但未處理）：`common.js:282` CoinGecko 違反 `connect-src 'self'`
6. **V017 NOT NULL ratio 觀察**：頭 24h `entry_context_id NOT NULL` 應接近 100%（paper+demo），<95% 回查漏掉的 Fill 發射點
7. **canary rotation 首次壓力測試**（20 分鐘窗口）：確認是「重命名保留 `.1/.2`」還是「truncate 覆寫」
8. **G-2 daemon progress 文件時間戳未刷新**：`ts_utc` 停在 12:47:55，但 PID 598572 存活；progress 只在 fill 事件更新，n_fills=0 無觸發非假死
9. **Lane A Trainer** 未動手（純 Python，compact 後新 session 照備忘開工）
10. **Lane B Phase B #3 ONNX loader + Step 7b flip** blocked by Lane A 首 artifact
11. **AI-E Round-4 兩 YELLOW-nit**：§7.1 Stage 2 ort macOS `libonnxruntime.dylib` bundling 提醒 + CC #13 strace Linux-only 註記
12. **Round-2 未採納 17 項**：`recent_slippage_bps_ewma` feature、CPCV fold 數討論、online learning 支線等（v1.2 CHANGELOG 未採納段）

---

## Commits

- **EDGE-P3-1**：`9141e08` spec v1.0→v1.3 (+864/-353) · `1366054` Stage 0 v1.4 + V017 + entry_context_id threading (13 files, +980/-53) · `8c1f234` Phase A A1-A4 (19 files, +1956/-18) · `3753ede` Phase A5 (5 files, +518/-7) · `a23b268` Phase A6 (15 files, +273/-16)
- **ENGINE-HEAL**：`5d5ec13` FIX-PHASE1 offload canary write · `6c73b60` FUP-A/B throttle + Full branch tests · `0762006` E4-HYG-1 core test hygiene
- **ORPHAN-ADOPT**：engine self-kill root-cause fix (+319/-10, 8 files) · Phase 2A deterministic adopt (implemented, merged pending)
- **GUI**：P&L 可視化 Step 1 (5 files src + 1 worklog, single commit)

---

## 一句話狀態 / One-Line Status

> 2026-04-15：engine lib **1293** + core 372 + e2e 35 = **1700 pass / 0 fail**（+149 vs 1551）· EDGE-P3-1 spec v1.0→v1.4 GREEN + Stage 0/Phase A/A6 Rust 接線落地（gate 熱路徑可諮詢、`use_edge_predictor=false` 預設零行為改變）· ENGINE-HEAL 慢性 2h 掉 tick post-mortem + FIX-PHASE1 offload canary write + warn throttle + watchdog systemd 正式化 + 122GB→519MB rotation 首次驗證 · ORPHAN-ADOPT FUP 引擎自殺根因修復（side-car mirror）+ Phase 2A deterministic adopt 基礎設施（edge_estimates proxy）· GUI P&L Step 1 三 tab 統一（common.js helper + PG 旁路）· Lane A Trainer 交接備忘就緒等 FA-PHANTOM-2 ship。
