# CLAUDE_CHANGELOG.md — 開發歷史歸檔

> 從 CLAUDE.md 遷出的 Wave/Sprint/Batch 歷史記錄。新 session 不需要讀此文件，僅供回顧歷史時查閱。
> 最後更新：2026-04-15（EDGE-P3-1 ML-MIT #26 Stage 2 quantile trainer + CQR + ONNX export）

### EDGE-P3-1 ML-MIT #26 — Stage 2 Quantile LGBM + CQR + Per-strategy ONNX Export（2026-04-15 · commit `cdac922`）

**目標**：Lane A 純 Python 訓練管線，與 FA-PHANTOM-2 Rust 修復並行安全（零檔案重疊）；交付 Phase B #3 ONNX loader + CC T2/T7/T18 所需的首個 per-strategy ONNX artifact 能力。

**交付**（5 檔改、10 檔加，2645 insertions）：
- `quantile_trainer.py`（新，~540 行）— q10/q50/q90 三獨立 pinball LGBM + CPCV purge + 策略特定 embargo（funding_arb 3-fold/72h/14d vs 其他 5-fold/24h/7d）+ 指數樣本權重 `w = exp(-days_ago/14)` + tail holdout split（總跨度 < holdout 窗時退回 min_fraction 比例切分）+ linear-QR floor baseline + 1000-bootstrap decile-lift 95% CI + 分位交叉率 + `feature_schema_hash = sha256(version || "|" || names.join("\n"))` 與 Rust FeatureVectorV1 契約一致
- `calibration.py`（擴展）— CQR 單邊 marginal 校準 Romano 2019 + `(n+1)` 有限樣本修正 `q_level = ⌈α·(n+1)⌉/n`：`fit_cqr_offset` / `fit_cqr_trio` / `apply_cqr_to_quantile` / `evaluate_cqr_coverage` / `fit_isotonic_fallback`；舊 isotonic 路徑保留不動
- `onnx_exporter.py`（擴展）— `export_quantile_trio_to_onnx()` 三檔匯出 + POSIX-atomic symlink swap（`tmp.symlink_to → os.replace`）+ per-file 精度 gate `max|LGB-ONNX| < 1e-3` on 1000 random vectors；檔名規範 `edge_predictor_{engine}_{strategy}_{quantile}_{schema}_{date}.onnx` + `_current` symlink 匹配 Rust loader 契約（spec §7.2）
- `quantile_reports.py`（新，~345 行）— 5 硬性 gate（pinball skill > 0.10 / coverage error < 3pp / decile lift CI lower > 1.3 + point ≥ 1.5 / crossing < 1% / LGBM vs linear-QR skill diff ≥ +5pp）+ 樣本量桶（<200 / 200-499 / ≥500）→ should_ship / shadow_only / no_ship 裁決 + 1000 random vector train-serve skew harness；JSON 持久化
- `run_training_pipeline.py`（重構）— `use_quantile_predictor=True` 分支路由 ETL → quantile_train → CQR → acceptance_report → per-quantile ONNX（verdict ≠ no_ship 才匯出）；legacy regression scorer 路徑零行為改變

**測試**（+47，ml_training 135→182 passed）：
- `test_quantile_trainer.py` — 23 tests（embargo 路由 funding_arb / default / 大小寫、權重衰減、pinball/coverage/crossing/decile lift、schema hash 穩定性 + version 差分、tail holdout 邊界 fallback、端到端 lgb-guarded）
- `test_calibration_cqr.py` — 9 tests（CQR 有限樣本公式手動驗證、α 單調、coverage gap 5pp 內收斂、isotonic fallback 單調性）
- `test_quantile_reports.py` — 11 tests（verdict 4 路由、gate 邊界 strict `>`、post-CQR coverage source、linear-QR unavailable 視為 pass、training failure 短路）
- `test_onnx_exporter_quantile.py` — 4 tests（engine_mode / quantile 輸入驗證、end-to-end 精度、symlink swap idempotency）
- 218 passed / 10 skipped（重依賴 lgb/onnxmltools/onnxruntime/sklearn 缺失時 `pytest.importorskip`）/ 0 regression

**解鎖**：Phase B #3 ONNX loader（Rust 側等首個 artifact）· CC T2/T7/T18（train-serve skew + precision）· Stage 3 Shadow mode（#29）

**Handover**：`docs/worklogs/2026-04-15--lane_a_ml_mit_26_trainer_handover.md`（pre-compact 14-section brief，記錄所有設計決策）

### FA-PHANTOM-2 — fast_track held-symbol scoping + sigma gate（2026-04-15）

**發現過程**：G-2 FundingArb 監控 daemon PID 598572 運行 7 小時，progress 停在 0/20 fills。DB 查詢揭露 demo funding_arb 8 次開倉全部在 4-7 秒內被 `risk_close:fast_track` / `risk_check` / `ipc_close_symbol` 秒殺，0 次走到自然 `strategy_close` 出口。engine.log 抓到 `risk_level=Normal` 下 `FAST_TRACK CloseAll fired` 多次，`trigger_symbol=ENJUSDT`（小幣 $0.075 ~ $0.094）。排除 CircuitBreaker / margin_util (已 leverage-aware ≤2%) 後確認唯一觸發源是 `price_drop_pct >= 5.0`。

**根因**：`openclaw_core/src/risk/price_tracker.rs::max_drop_pct()` 掃全部 25+ 觀察幣種 5min 窗口最壞跌幅。小幣 5min 內抖 5% 是常態噪音，所以 fast_track 持續誤觸 CloseAll，**全策略被系統性秒殺**，funding_arb 在 daemon 視角下永遠收不滿 20 個自然出口 fill。與 FA-PHANTOM-1 同類型 bug（fast_track false-positive CloseAll），但根因獨立。

**交付**（3 處協調修改）：
- **`PriceHistoryTracker::worst_drop_for_held(&[String]) -> Option<SymbolDropInfo>`** — 新方法僅掃持倉幣種，附帶 sigma = `|current - mean| / std_dev`（窗口內）。空集合或樣本不足返回 None。舊 `max_drop_pct()` 保留供非 fast_track consumer 使用。
- **`evaluate_fast_track` 新簽名** `(risk_level, held_drop_pct, held_drop_sigma, margin_util)`，分級規則：
  - `CircuitBreaker+` / `margin_util >= 90%` → CloseAll（舊行為，保留）
  - `held_drop_pct >= 15%` → CloseAll（真閃崩兜底，sigma 可能不可用的邊緣情境）
  - `held_drop_pct >= 5% AND sigma >= 3` AND `risk >= Defensive` → CloseAll
  - `held_drop_pct >= 5% AND sigma >= 3` AND `risk < Defensive` → ReduceToHalf（關鍵：Normal 下不再 panic，只半倉）
  - 其他按舊風控梯度（Defensive→ReduceToHalf, Reduced→PauseNewEntries）
- **`tick_pipeline/on_tick.rs`** — 構造 `held_symbols` 清單 → `worst_drop_for_held` → 解包 `(drop_pct, sigma, symbol)` → 傳入 `evaluate_fast_track`。三個 tracing 日誌（CloseAll WARN / ReduceToHalf WARN / PauseNewEntries INFO）全部攜帶新欄位 `held_drop_pct`/`held_drop_sigma`/`held_drop_symbol` 便於日後取證。

**測試** (+17 淨增)：
- `price_tracker::tests` +8 — 空 held 返 None · unheld symbol drop 不觸發（legacy 仍會，分岔驗證）· held drop 正確浮現 · 樣本不足返 None · 多 held 取最大 · 穩定幣 0 跌返 None · 噪音小幣 sigma<3 · 穩定幣突崩 sigma≥3（19 穩定樣本避免 std_dev 被 outlier 自身撐高到 sigma=3.0 邊界）
- `fast_track::tests` +9 — 新簽名全部 arity 更新；新增 FA-PHANTOM-2 regression（6%+sigma=1.5 → NoAction）+ held outlier Normal/Cautious → ReduceToHalf + Defensive → CloseAll + 5%/3σ 邊界 + 15% cliff + 無 drop 訊號 risk-level-only 退化
- `stress_integration` 語義更新 — 舊 `test_flash_crash_closes_all`（8% Normal → CloseAll）改為測新語義的三條路徑，`boundary_exactly_5pct_drop` 重命名為 `boundary_extreme_drop_cliff` 驗 15% 硬線

**計量**：engine lib 1309→1318（+9）；core 372→380（+8）；e2e 35 不變。合計 **Rust 1716 → 1733 passed / 0 failed**。

**Spec 與決策記錄**：`docs/references/2026-04-15--fa_phantom_2_fix_spec.md`（含根因證據鏈、三條修復方向對應表、閾值選擇理由、測試列表、FA-PHANTOM-1 對照）。

**部署**：`restart_all.sh --rebuild` 重建 engine binary；驗證指標為 `grep "FAST_TRACK CloseAll fired.*risk_level=Normal" /tmp/openclaw/engine.log` 應回空（除非真發生 ≥15% 或 5%+3σ 事件），G-2 daemon 接下來幾小時應開始累積 `n_fills`。

---

### EDGE-P3-1 Phase B #4 — RNG seeding + `with_kind` forwards kind to IntentProcessor（2026-04-15）

**背景**：spec §7.3 F9 規定 paper/demo/live 各自以 `seed_for_engine(startup_nanos, kind) = startup_nanos ^ kind_discriminant` 初始化 ε-greedy 的 `SmallRng`。函式本身在 `edge_predictor/gate.rs` 早已實作 + 有單元測試，但 bootstrap 從未呼叫 — `IntentProcessor::new()` 預設 seed=0，三引擎的 ε-greedy 抽樣流完全相同（spec §7.3 F9 失效）。同時發現一個耦合的潛伏 bug：`TickPipeline::with_kind(kind)` 把 kind 寫到 `pipeline.pipeline_kind` 卻從未 forward 給 `pipeline.intent_processor.pipeline_kind` — gate 用的是 IntentProcessor 這份欄位，導致 demo/live 的 gate 全部誤認為 Paper，ε-greedy 在 demo/live 也會嘗試發 `EmitShadowFill`，靠 writer R5 + DB `CHECK (engine_mode='paper')` 才擋下。兩者都屬「設計已就位，bootstrap 缺一個 setter 呼叫」。

**交付**：
- **`TickPipeline::set_predictor_rng_seed(seed: u64)`**（`tick_pipeline/mod.rs`）：純 forwarding wrapper → `intent_processor.set_predictor_rng_seed`。與 `set_shadow_fill_tx` / `set_decision_feature_tx` 同一設計。
- **`TickPipeline::with_kind(kind)`** 加一行 `p.intent_processor.set_pipeline_kind(kind)` — gate 的 `inputs.engine_kind` 這下才真正反映 engine；註解說明為何單一 setter call 同時修復兩個面向（persistence + gate）。
- **`event_consumer/mod.rs`** bootstrap wire（與 7a/7c/store 注入同區塊）：`SystemTime::now()` nanos → `gate::seed_for_engine(nanos, pipeline_kind)` → `pipeline.set_predictor_rng_seed(seed)`。`unwrap_or(0)` 防止 1970 年代容器時鐘異常時 panic（kind discriminant XOR 仍使三引擎得到互異種子）。
- **`IntentProcessor::pipeline_kind()`** 讀取 accessor（pub）+ `predictor_rng_lock_for_tests`（`#[cfg(test)]`）：讓回歸測試可驗證 with_kind forwarding 與 seed 獨立性，不把 private state 洩漏到 non-test API。

**測試** (+2 於 `tick_pipeline::tests`)：
- `test_with_kind_forwards_kind_to_intent_processor` — 三個 `with_kind` 的 pipeline 的 `intent_processor.pipeline_kind()` 必須分別為 Paper/Demo/Live；鎖定 forwarding 不會被未來重構靜默回歸。
- `test_set_predictor_rng_seed_changes_draw_stream` — 兩 pipeline 分別以 `seed_for_engine(123_456_789, Paper)` 和 `seed_for_engine(123_456_789, Demo)` reseed，各抽 64 bit，向量必不相等 — 證明 RNG wiring 實際改變了 Mutex 內的 SmallRng 狀態。

**計量**：lib 1307→1309（+2）；core 372 不變；e2e 35 不變。合計 **Rust 1716 passed / 0 failed**。

**下一步解鎖**：Phase B 剩 #3（ONNX model loader，blocked by ML-MIT #26）。#4 完成後 spec §7.3 F9 完全符合，paper 的 exploration 每次冷啟動後種子隨 wallclock 而異（好的 diversity），demo/live 的 ε-greedy 則被 gate 層直接擋住（不再依賴 writer/DB 兜底）。

### EDGE-P3-1 Step 7b — `ReloadEdgePredictor` plumbing-only（2026-04-15）

**背景**：spec §7.3 Step 7 最後一條 IPC。Python ML-MIT pipeline 將來會把新訓練的 ONNX artifact 寫到磁碟後呼叫此 IPC 讓 Rust 熱換；但 ONNX loader 本體仍卡在 ML-MIT #26（tract/ort feature flag 空殼）。直接等 #26 會讓 IPC 協定長期懸空；直接全做又需要未完成的載入器。**決策**：落 plumbing-only — 協定/handler/validation/tests 全就位，loader 為存根（恆 Err 帶 `awaiting ML-MIT #26` 字樣），capability flag 誠實保持 `False`。#26 交付時換 loader body + 翻 flag + 加 Python route 即可，無協定改動。

**交付**：
- **`PipelineCommand::ReloadEdgePredictor`** variant（`tick_pipeline/mod.rs`）：`engine: String`（白名單 paper/demo/live，作 IPC 路由二次防禦）+ `strategy: String` + `path: PathBuf` + `response_tx: oneshot::Sender<Result<String, String>>`。注釋標記 plumbing-only 與 flag 翻轉時機。
- **`edge_predictor::load_predictor_from_path`** 存根（`edge_predictor/mod.rs`）：`path.exists()` false → 立即 Err（讓路徑錯誤仍可測），存在則 Err `onnx_loader_not_wired: awaiting ML-MIT #26 first ONNX artifact`。注釋指明 #26 交付時的替換步驟。
- **`handle_reload_edge_predictor`**（`event_consumer/handlers.rs`）：engine `.trim()` + 白名單 match（防 Python proxy 殘留換行）→ `pipeline.edge_predictor_store()` 存在性檢查（`None` 直接 Err 避免 loader 成功卻熱換進空引用）→ 呼叫 stub loader → 成功才 `store.swap(strategy, predictor)` + info log。拆為獨立函式以便單元測試免 oneshot 迴圈即可驗。
- **Match arm** 於 `handle_paper_command` 加入 `PipelineCommand::ReloadEdgePredictor => handle_reload + oneshot 回應`。
- **Capability flag 註解** `engine_capabilities_routes._EDGE_P3_IPC_SUPPORT.reload_edge_predictor`：值仍 `False`，註解改為「protocol wired; stays False until ML-MIT #26 replaces the stub loader with real tract/ort backend」。
- **Python route 暫不加**：flag `False` 時無 client 會呼叫；避免寫完整路由卻只能代理 Err。#26 交付時 Python route + flag flip + 實作 loader 同一 PR 落地更清晰。

**測試** (+4 於 `event_consumer::handlers::tests`)：
- `test_reload_edge_predictor_rejects_unknown_engine` — `engine="mainnet"` → Err 含 `invalid engine`。
- `test_reload_edge_predictor_requires_store` — 未 `set_edge_predictor_store` → Err 含 `EdgePredictorStore not wired`。
- `test_reload_edge_predictor_stub_loader_errs` — 接線 store + `NamedTempFile` 確保路徑存在 → 走完整 loader → Err 含 `onnx_loader_not_wired` + `ML-MIT #26`；`store.loaded_count() == 0` 確認未熱換。
- `test_reload_edge_predictor_trims_engine_name` — `engine="  paper\n"` → 白名單仍通過（trim 生效）→ err 走到 loader 路徑而非 invalid engine。

**計量**：lib 1303→1307（+4），其餘集合不變。zero churn on Step 7a/7c/7d/7e/7f 路徑。

**下一步解鎖**：Step 7 IPC 全套協定/實作就位。Stage 2+ 唯一剩下的阻塞仍是 ML-MIT #26 首 ONNX artifact — 屆時 stub loader body 換真、capability flag 翻 True、Python route 加（`POST /api/v1/risk/edge_predictor/reload`，沿用 `ReloadRiskConfig` 的 operator 授權）即完整端到端。

### EDGE-P3-1 Step 7c — `EmitShadowFill` → `learning.decision_shadow_fills` writer（2026-04-15）

**背景**：spec §7.3 Step 7 的 ε-greedy paper exploration 持久化 — 預測器對成本拒絕但探索翻硬幣通過，此時合成「shadow fill」僅供觀測學習，**永不**納入訓練 label 回填（`parquet_etl.py` §5.1 WHERE 以 `close_tag='shadow_fill:epsilon_greedy'` 排除）、永不進 live/demo 真實交易。目前僅 Stage-0 stub handler（log-only），本 step 填完 Rust-direct writer，對稱 Step 7a `DecisionFeatureSnapshot` 的 Option-B（IntentProcessor producer + IPC passthrough 共用同一 writer channel）。

**交付**：
- **Rust writer**（`database/shadow_fill_writer.rs` 新 ~230 行）：`run_shadow_fill_writer` async mpsc drain；`HashMap<context_id, ShadowFillMsg>` flush 前去重（ε-greedy 每 intent 至多一次，但 replay/passthrough 可重發同 id）；`batch_flush_interval_ms` 定時 flush；`flush_shadow_fills` 三道拒絕：DB-RUN-6 `ts_ms=0` epoch 洩漏 + R5 `engine_mode != "paper"` 第二道防線（gate 已保證 is_paper，writer 亦拒避 PG CHECK 失敗計入 pool 失敗閾值）+ malformed JSONB warn+skip；INSERT 11 欄位（context_id/ts/engine_mode/strategy_name/symbol/side/features_jsonb/predicted_q10/predicted_q50/predicted_q90/cost_bps_at_open），`synthetic_*` + `close_tag` **刻意** 不 bind 走 V017 DDL 預設（DDL 漂移時 writer 保持向下相容）。
- **ShadowFillMsg**（`database/mod.rs`）：carrier struct 11 欄 + `#[derive(Debug)]`。
- **side 欄位接線**：`PipelineCommand::EmitShadowFill` variant 加 `side: i8`，`ShadowFillPayload` 加 `pub side: i8`，`edge_predictor_gate` 建構時從 `features.side` 取值（`FeatureVectorV1` 既有欄位），`emit_shadow_fill` 透傳；DB 表既有 `side SMALLINT NOT NULL`，不透傳會 bind 階段報錯。
- **TickPipeline 接線**（`tick_pipeline/mod.rs`）：`shadow_fill_db_tx: Option<Sender<ShadowFillMsg>>` 欄位 + `set_shadow_fill_db_tx`（`debug_assert!` 防雙注入）+ `shadow_fill_db_tx()` getter。
- **Handler 轉實作**（`event_consumer/handlers.rs`）：`EmitShadowFill` 從 Stage-0 log-only stub 轉為 `try_send` off hot path，Full/Closed 丟棄+warn，engine_mode 由 `pipeline.pipeline_kind.db_mode()` 推導（gate 僅 paper 發，但仍計算交 writer R5 防線驗證）；`None` tx 走 fail-soft log 分支。
- **spawn_db_writers** 5→6 tuple（`tasks.rs`）：capacity 1024，對齊 decision_feature。
- **3 `EventConsumerDeps` sites** (`main.rs` paper/demo/live)：paper 為唯一合法 emission 來源（gate guard），demo/live 亦接線作深度防禦日誌（異常洩漏可見於 writer warn log 而非污染 PG）。
- **event_consumer wire**（`mod.rs`）：destructure deps + `set_shadow_fill_db_tx` 注入（對稱 `decision_feature_tx` 模式）。
- **Python capability flag**：`engine_capabilities_routes._EDGE_P3_IPC_SUPPORT.emit_shadow_fill: False → True`。

**測試** (+7)：`test_dedup_keeps_latest`、`test_dbrun6_epoch_zero_detected`、`test_non_paper_engine_mode_rejected_in_carrier`、`test_malformed_jsonb_caught_before_sql`、`test_valid_jsonb_parses`、`test_side_fits_smallint`、`test_insert_sql_locked_columns`（`split_once("INSERT INTO") → split_once("VALUES")` 範圍鎖定，避開註解/docstring 誤報；驗 9 欄位齊全 + `close_tag` 不顯式 bind）。lib 1296→1303，engine-capabilities 6 tests 繼續通過，e2e 35 ok。

**Stage 2+ blocker 狀態**：Step 7 IPC 已完成 5/6（7a/7c/7d/7e/7f）；餘 7b `ReloadEdgePredictor` 可獨立前推，其餘唯一 blocker 仍為 ML-MIT #26 首 ONNX artifact。

### EDGE-P3-1 Step 7f — `GET /api/v1/engine/capabilities` 探針端點（2026-04-15）

**背景**：EDGE-P3-1 §12.3 item 7 的 backward-compat capabilities probe。spec 僅標 `(backward-compat)` 無詳細 schema — 解讀為「端點存在 + 預期 shape 即表示此 build 支援 EDGE-P3-1，舊 build 回 404 讓 client 優雅降級」。刻意保持薄，不重複 `/api/v1/paper/risk/config/engine/{engine}` 的完整 RiskConfig 快照。

**交付**（`program_code/exchange_connectors/bybit_connector/control_api_v1/app/engine_capabilities_routes.py` 新檔 ~180 行 + `main.py` +4 行註冊 + `tests/test_engine_capabilities_routes.py` 新檔 ~180 行）：
- **路由** `/api/v1/engine` prefix，`GET /capabilities`，`Depends(base.current_actor)`（viewer 即可，純讀取探針）。回傳三段：
  - `feature_schema` — `FEATURE_NAMES_V1` 鏡像（`schema_version="v1"`、`dim=17`、`names`）從 `program_code/ml_training/parquet_etl.EDGE_P3_FEATURE_NAMES` 匯入，複用既有 DO-NOT-REORDER 契約避免新增鏡像副本。
  - `ipc_methods` — 本 build 宣告哪些 Step 7 IPC 變體已接線的 bool 字典：`decision_feature_snapshot=True`（7a）· `fsynced_toml_write=True`（7d）· `disable_edge_predictor_all=True`（7e）· `reload_edge_predictor=False`（7b pending）· `emit_shadow_fill=False`（7c pending）· `set_edge_predictor_shadow=False`（v1.3 U1 pending）。唯一防漂移宣告 — 後續 PR 接線時必須同步翻旗。
  - `engines` — per-engine (paper/demo/live) 窄 edge_predictor 視圖（`use_edge_predictor`、`shadow_mode`、`quantile_safety_k`、`require_q10_positive_for_adds`、`exploration_rate`、`fallback_on_error`），經 `get_risk_config` IPC 逐引擎取。
- **Fail-closed 契約**：IPC 不可用（測試、cold boot、engine 崩）仍回 HTTP 200 + `degraded=true` + `reason` 字串（`ipc_unavailable` / `ipc_error:{ExcClass}` / `bad_payload_shape`），靜態部分（feature_schema / ipc_methods）永遠可用。絕不 5xx。模組級 `_IPC_CLIENT` 懶初始化單例（複用 `risk_routes._get_direct_ipc` 樣式）。
- **Envelope** 符合既有慣例：`{"ok": true, "data": {...}, "is_simulated": false, "data_category": "engine_capabilities"}`。
- **6 新 tests**（`test_engine_capabilities_routes.py`）：
  - `test_capabilities_returns_200_without_ipc` — 無 IPC 仍回 200。
  - `test_capabilities_degraded_when_ipc_down` — `degraded=true` + `reason="ipc_unavailable"` + 所有 engines 欄位 None。
  - `test_capabilities_static_payload_present_when_degraded` — schema.names 17 + adx_1h/is_funding_settlement_window 端點 + ipc_methods 完整。
  - `test_capabilities_happy_path_surfaces_engines` — 存根 IPC 回三引擎差異化值（paper use=true/demo=false/live=false + exploration_rate 分流）→ route 正確路由。
  - `test_capabilities_envelope_shape` — ok/is_simulated/data_category + engines 三鍵完整。
  - `test_capabilities_requires_auth` — 無 `dependency_overrides` → 401（`current_actor` 拒絕空 token）。

**測試**：Python **2852→2875 pass / 0 fail / 5 skipped**（control_api_v1 子集 `2452 passed`，含新增 6）。Rust 測試未觸（Step 7f Python-only）。

**為何未新增 Rust IPC**：刻意避免 scope creep。`get_risk_config` IPC（ARCH-RC1 1C-2-C / LIVE-P2-1）已是三引擎完整 RiskConfig 讀取管道；Step 7f 只需薄 wrapper 抽 edge_predictor 窄子集 + 疊靜態宣告。未來若 `ipc_methods` 宣告維護壓力變大，可升級為新 Rust `get_engine_capabilities` IPC 由引擎自報（source of truth 移至 Rust），但 Step 7f 完工時機械漂移風險低（`_EDGE_P3_IPC_SUPPORT` 常數字典每條都註記 commit 號 + spec 條款）。

**下一步**：Step 7 餘 2 條（7b `ReloadEdgePredictor{engine, strategy, path}` IPC + Python route · 7c `EmitShadowFill` Python consumer → `learning.decision_shadow_fills`）。兩條獨立可推。

---

### ORPHAN-ADOPT-1 Phase 2A — 確定性 Adopt 基礎設施（2026-04-15）

**背景**：Phase 1（2026-04-14 merged）+ FUP 側車 mirror 解決了「偵測到但不動」與「引擎自殺」的 bug，但所有真正的外來 orphan 都走 Stage C `SoftConservative` close-everything 降級路徑。Phase 2 原本等 G-1 R-02 AI Strategist（W22-W23）。Phase 2A 是非 agentic sub-option：用既有 `edge_estimates` 表當「某策略會下這個幣種」的確定性代理 — 任一 `KNOWN_STRATEGY` 在 orphan 幣種 shrunk_bps > 0 即 Adopt。edge 正負僅是 per-symbol 指標，方向（long/short）保留交易所回報的原樣，StopManager 管下行。

**交付**：
- **Schema** — `PaperPosition.owner_strategy: String` 必選欄位。strategy-driven fills 寫 `intent.strategy`；`import_positions` + `upsert_position_from_exchange` insert 路徑寫 `"bybit_sync"`；`adopt_orphan` 寫 `ORPHAN_ADOPTED_STRATEGY = "orphan_adopted"`；update 路徑保留既有 owner（ma_crossover 收到 WS 更新不會被改回 bybit_sync）。`apply_fill` 加第 7 個 positional 參數 `owner_strategy: &str`，同向累加 first-write-wins。`#[serde(default)]` 讓 pre-2A snapshot 文件可載入。
- **Stage B2 Adopt 決策** — 新 `OrphanStage::AdoptPositiveEdge` + `OrphanDecision::Adopt { reason, stage, triggering_strategy }`。`handle_orphan()` B1/B2 分支：任一 known strategy 在 `pos.symbol` 有 `shrunk_bps > 0` → Adopt，記下第一命中（per `KNOWN_STRATEGY_NAMES` 順序）為 `triggering_strategy`；否則 `unrealised_pnl > 0` → SoftLockProfit close；否則 Stage C 落入 SoftConservative close（原則 #6 保守優先）。Stage A（liq / CB / notional / scanner universe）嚴格先於 B，安全檢查永不讓步 Adopt。
- **注入路徑** — 新 `PaperState::adopt_orphan(symbol, is_long, qty, entry_price, ts_ms) -> bool`：冪等 · 輸入守衛 · 預填 `latest_prices`（StopManager 立即有 tick）· 用 `positions_insert` helper 寫入（FUP 側車 mirror 自動更新）· 寫 `owner_strategy = ORPHAN_ADOPTED_STRATEGY`。新 `PipelineCommand::AdoptOrphan` fire-and-forget + `event_consumer/handlers.rs` 分派 arm（插入後 force_write snapshot）。新 `dispatch_orphan_adopt(decision, pos, cmd_tx)`（用 `pos.avg_price` 作 adopt entry_price，StopManager 從此點管下行）；與 `dispatch_orphan_close` 都拒錯誤 variant（warn + `return false`）。`position_reconciler/mod.rs:635` 分派分叉依 decision variant。
- **Audit 擴展** — V014 JSONB payload 加 `owner_strategy`（Adopt=`"orphan_adopted"`/Close=null）+ `triggering_strategy`（Adopt=命中策略名/Close=null），下游分析可 join 歸因。
- **測試** — lib 1285→1293 (+8)：5 `orphan_handler.rs`（long Adopt/short Adopt/無正 edge 落 SoftConservative/first-positive-edge wins deterministic/Stage A 優先於 B2）+ 3 `paper_state.rs`（insert + mirror + idempotent 保留 owner + 輸入守衛）。

**測試總數**：lib **1285→1293**（+8）· core 372 · e2e 35 · **total 1692→1700 pass / 0 fail**。

**Deploy**：`bash helper_scripts/restart_all.sh --rebuild`。Adopt 路徑在 `edge_estimates.json` 未 populated OR 無 `KNOWN_STRATEGY` 在 orphan 幣種有正 edge 時仍然 inert（退回 Phase 1 close-only）。

**Phase 2B（未來）**：G-1 R-02 Strategist 在線後，Adopt 規則從「正 shrunk edge」升級為「Strategist would_take(symbol, side)」；`KNOWN_STRATEGY_NAMES` + `EdgeEstimates` probe 降為 fast-path short-circuit，Strategist 為 slow-path 最終裁定。

---

### EDGE-P3-1 Step 7e — `DisableEdgePredictorAll` 完整兩階段 commit + V014 audit（2026-04-15）

**背景**：commit `97777d5` 已落 Step 7e 骨架（介面 + getter + 標準入口函式，語義仍 pre-7e memory-only clear）。本 commit 填上完整兩階段邏輯 + V014 audit + 3 新測試，kill-switch 於 operator 下令後必須保證「即使引擎立刻崩潰，重啟仍讀到 `use_edge_predictor=false`」—disk-first fail-abort 語義。

**交付**（`event_consumer/handlers.rs` +180 / -40，不觸骨架範圍外檔）：
- **兩階段 commit 邏輯**（`disable_edge_predictor_all_impl`）：
  - Stage 1 — 預算 next `RiskConfig`（`edge_predictor.use_edge_predictor = false`）+ `validate()` → `write_toml_atomic_fsynced(&next, persist_path)` disk-first；寫盤失敗立即 reject 且不觸及記憶體，避免「disk 舊 + 記憶體新」的半啟用殘局。
  - Stage 2 — `ConfigStore::apply_patch(Operator, mutate, validate)` ArcSwap 把同一 mutation 套到 live config；Stage 2 失敗（只有 lock poison）時 disk 已是 authoritative 新副本，重啟自動對齊 + warn log 提示 operator。
  - Stage 3 — `EdgePredictorStore::clear_all()` 清記憶體 slot，返回清空計數。
  - Fallback — `risk_store` 未接線（測試或未來 stripped-down engine）降級為 memory-only clear，回 `cleared N slots (memory-only)` 讓 caller 區分兩路徑。
- **V014 audit**（fire-and-forget `tokio::spawn`，僅 `audit_pool.is_some()` 時 enqueue）：`event_type='predictor_disabled_all'` / `source='operator'` / `config_name='risk_config'`，payload JSONB `{operator_token_hash(sha256hex), reason, cleared_slots, persisted, engine_mode, stage2_error}`；raw token 永不落盤。`tokio::spawn` 需要 runtime → 測試傳 `audit_pool=None` 跳過 spawn，單元測試無需 tokio。
- **U1 authz**：`operator_token.len() < 32` 立即 reject（未來 HMAC 驗證 hook）；`hash_operator_token()` 用 `sha2::Sha256 + hex::encode` 產生審計專用 hash。
- **3 新測試**（`handlers.rs` tests 模組）：
  - `test_handle_disable_edge_predictor_all_rejects_short_token` — 9 字符 token → Err("too short")；slot 不觸動（reject 先於 `clear_all`）。
  - `test_handle_disable_edge_predictor_all_memory_only_when_store_unwired` — `set_risk_store()` 不呼叫 → risk_store=None → memory-only clear 路徑；訊息含 "memory-only"。
  - `test_handle_disable_edge_predictor_all_writes_toml_stage1` — 接線 `ConfigStore::new(RiskConfig { use_edge_predictor: true, ..default }).with_toml_persist(tempdir)` → call handler → 驗 TOML 檔內容含 `use_edge_predictor = false`、in-memory snapshot `use_edge_predictor == false`、pred_store slot 清空、回應訊息含 `persisted=false`。
- **`handle_paper_command` DisableEdgePredictorAll arm**：延用共用 `disable_edge_predictor_all_impl`，以 `db_mode="paper"` + `audit_pool=None` 呼叫，保留 legacy test path + 避免單元測試需要 tokio runtime。

**測試**：lib **1293→1296**（+3 Step 7e）· core 372 · e2e 35 · **total 1700→1703 pass / 0 fail**。

**為何兩階段非純 apply_patch**：spec §8.8 F3b 要求 disk-first — `apply_patch` 內建 `maybe_persist` 是 fail-soft（寫盤失敗只 warn，ArcSwap 仍 commit），對 kill-switch 語義不夠嚴格（operator 意圖是「再也不讓它啟用」，寫盤失敗後必須中止而非吞錯）。因此 Stage 1 用直接的 `write_toml_atomic_fsynced` + fail-abort，Stage 2 才走 `apply_patch`（此時 disk 已有 authoritative 副本，ArcSwap 失敗也有磁碟 fallback）。

**audit 設計**：token 永不落 raw。即便 Postgres 被入侵/洩漏，審計表只有 sha256 hash，無法 replay token；log 只寫 `token_len` + `reason` + `cleared_slots` + `engine_mode` 足以溯源 operator 意圖。

**已知限制**：跨三引擎（paper/demo/live）原子 disable 未實現 — 若 operator 要全局 kill，需 Python 側 fan-out 三次 IPC 呼叫；任一引擎失敗由 Python 決定補救/回滾。Rust 側只保證單引擎 3-stage 原子。

**下一步**：Step 7b `ReloadEdgePredictor{engine, strategy, path}` IPC + Python route · Step 7c `EmitShadowFill` Python consumer → `learning.decision_shadow_fills` · Step 7f `GET /api/v1/engine/capabilities`。三條獨立可推。

---

### EDGE-P3-1 Step 7e skeleton — `DisableEdgePredictorAll` 骨架（2026-04-15 · commit `97777d5`）

**背景**：Step 7d 交付 `write_toml_atomic_fsynced` 耐久性證明；本 commit 是 Step 7e 的**骨架**（非完整兩階段 commit + audit），為了讓 Phase 2A 能獨立以清潔 commit 落地，把 Step 7e 的 wire-up 拆出來先行。完整兩階段 commit + V014 audit row 仍 FIXME，留待下一 Step 7e commit 完成。

**骨架交付**（5 files +156 / -28）：
- **`tick_pipeline/mod.rs`**：`PipelineCommand::DisableEdgePredictorAll` 從 `{response_tx}` 擴為 `{operator_token, reason, response_tx}`；U1 授權 envelope（Python proxy 填 per-session UUID，Rust 側 `len>=32` 檢查，未來 HMAC 驗證 hook）；`reason` = operator 填 free-text 審計原因。新增 `TickPipeline::risk_store()` getter。docstring 展開 Stage 1 TOML fsync → Stage 2 ArcSwap → Stage 3 clear_all + V014 audit 語義。
- **`config/store.rs` + `config/mod.rs`**：`ConfigStore::persist_path() -> Option<&Path>` getter；`write_toml_atomic_fsynced` 從 `pub(crate)` 升 `pub` 並於 `config` 模組重新導出。
- **`event_consumer/handlers.rs`**：新 `pub fn handle_disable_edge_predictor_all(operator_token, reason, response_tx, pipeline, _db_mode, _audit_pool)` 標準入口 — **當前行為是 pre-7e memory-only clear + len>=32 token 檢查**（FIXME 標記完整兩階段 commit + audit writeback 未接線）。共用 `disable_edge_predictor_all_impl` 讓 `handle_paper_command` 單元測試路徑與生產 dispatcher 路徑共享同一份邏輯源。
- **`event_consumer/mod.rs`**：dispatcher 在 pipeline_cmd_rx 分支 match 截獲 `DisableEdgePredictorAll` 變體 → `handle_disable_edge_predictor_all(..)` 完整簽名呼叫；其餘變體走 `handle_paper_command`。

**為何拆骨架**：原始 combined WIP 含 Phase 2A adopt + Step 7e 完整兩階段 + 3 新測試。為讓 Phase 2A 能以清潔 commit review，先把 Step 7e 的介面擴展 + getter + handler 入口拆成骨架 commit，完整兩階段邏輯與測試留給下一 commit（FIXME 明確標記）。

**測試**：lib test count 不變 baseline（`test_disable_edge_predictor_all_clears_slots` 更新加 `operator_token`+`reason` 欄位後仍通過 memory-only fallback）。

**下一步**：Step 7e 完成 commit = 填 `_db_mode`/`_audit_pool` 的 FIXME：Stage 1 `write_toml_atomic_fsynced(risk_config, persist_path)` fail-abort → Stage 2 `ConfigStore::apply_patch(Operator, ...)` → Stage 3 `EdgePredictorStore::clear_all()` → V014 `predictor_disabled_all` audit row（token sha256 + reason + cleared_slots + engine_mode，fire-and-forget `tokio::spawn`）+ 3 新回歸測試（reject short token / memory-only fallback / Stage 1 TOML 落盤）。

---

### EDGE-P3-1 Step 7d — `write_toml_atomic_fsynced` SIGKILL durability 回歸（2026-04-15）

**背景**：Step 7e kill-switch 兩階段 commit 要落盤 `use_edge_predictor=false` 的 TOML 狀態；若程序在 OS page-cache 未刷時崩潰/被殺，狀態會丟 → 半啟用殘局。`write_toml_atomic_fsynced()` helper（`config/store.rs:261-291`）於 Phase A 已實作（tmp fsync → rename → 父目錄 fsync），但耐久性只靠 roundtrip unit test 間接驗證。本 step 補齊 spec **T23 / CC #13** 要求的 SIGKILL 對抗測試 —「helper 返回後，進程立刻 SIGKILL，TOML 內容必須已落盤」。

**交付**（1 file +130）：
- **`config/store.rs` tests 模組尾端**：新增 `test_write_toml_atomic_fsynced_survives_sigkill`（`#[cfg(unix)]`）。
  - **測試模式**：`current_exe()` 自我 spawn + env-var 閘控 child 分支（`OPENCLAW_FSYNC_SIGKILL_CHILD`）。Child = 寫 TOML（`use_edge_predictor=false` / `shadow_mode=false` / `note`）→ 寫 marker 檔標記 helper 已返回 → 進入 500ms-sleep idle loop 等死。Parent = 以 `Command::new(current_exe())` + `survives_sigkill` substring filter + `stdout/stderr = Stdio::null()` spawn self，poll marker（10s 超時 + 先殺後 panic 以避免 zombie），`Child::kill()`（unix 上對應 SIGKILL）+ `wait()` 回收，讀檔驗三個 assert（兩個 flag + note field）+ 驗 `.toml.tmp` 伴隨檔 rename 後消失。
  - **為何 substring filter 不用 `--exact`**：`--exact` 要求完整模組路徑（`config::store::tests::test_...`）；模組一移就壞。用 `survives_sigkill` 這個跨 crate 唯一的尾綴 substring 更穩。
  - **為何 `#[cfg(unix)]` 閘控**：Windows 無 SIGKILL 語義，部署目標 linux + macOS 皆 unix。

**測試**：lib **1285→1286**（+1 T23）· core 372 · e2e 35 · **total 1692→1693 pass / 0 fail**。新測試單獨跑 ~50ms（child spawn + poll + SIGKILL + reap）。

**未覆蓋**：T23 spec 附帶「CI 跑 `strace -e fsync` 驗證 syscall 觸發」屬 CI 層檢證，非 Rust 測試層責任（已記錄待 DevOps CI 加 job）。`test_disable_all_survives_sigkill` 整合測試（CC #13 整合級，涵蓋 `DisableEdgePredictorAll` 完整流程）屬 Step 7e 範圍（handler 目前僅 `clear_all()` 不寫 TOML；Step 7e 會接兩階段 commit + 用本 helper）。

**下一步**：Step 7e `DisableEdgePredictorAll` 兩階段 commit（U4）+ V014 `observability.engine_events` audit row，會首次把本 helper 接到實際 kill-switch handler。

---

### EDGE-P3-1 Step 7a — DecisionFeatureSnapshot Rust-direct writer（2026-04-15 · commit d73addb）

**背景**：EDGE-P3-1 Stage 0 需即刻採集 17 維訓練特徵至 `learning.decision_features`（V017 table），但 `use_edge_predictor=false` 仍是預設狀態 — 意味著 gate 走 legacy JS shrinkage 路徑，**不能**靠 predictor 已啟用路徑順帶寫。決策：**Option B**（Rust-direct writer + passthrough IPC 變體）— writer 直寫 DB 繞過 Python consumer（Step 7c 才走 Python），IPC 變體保留做日後 Python 端可選擇消費的跳板。

**交付**（11 files +899/-21）：
- **`edge_predictor/features.rs`**：凍結 `FEATURE_NAMES_V1: &[&str; 17]` + `FEATURE_SCHEMA_VERSION = "v1"`，`feature_schema_hash()` / `feature_definition_hash()` 以 `OnceLock` 緩存 sha256 首 16 hex（Stage 0 兩 hash 相同；Stage 2 ML-MIT 才分離）。6 unit tests（確定性 / 長度 / 非空 / version 常量 / getter 一致 / 名單完整）。
- **`database/mod.rs` + `database/decision_feature_writer.rs`（新 250 行）**：`DecisionFeatureMsg` 10 欄 struct + `run_decision_feature_writer()` async 迴圈（mpsc drain → HashMap dedup by context_id → `flush_features()` 拒絕 `ts_ms=0`（DB-RUN-6 對齊）+ 一次 `serde_json::from_str` JSONB 校驗 + `INSERT INTO learning.decision_features ... ON CONFLICT (context_id) DO NOTHING`）。6 unit tests（dedup / epoch-0 拒絕 / 畸形 JSONB / 合法 parse / SMALLINT side 轉型 / SQL 欄位鎖）。
- **`tick_pipeline/mod.rs`**：新增 `PipelineCommand::DecisionFeatureSnapshot { 10 fields }` 變體 + `TickPipeline.decision_feature_tx: Option<Sender<DecisionFeatureMsg>>` + `set_decision_feature_tx()` 同時傳 IntentProcessor（producer）+ 存本地供 handler 讀取（IPC passthrough），`debug_assert!` 防雙注入。
- **`intent_processor/mod.rs`**：`emit_decision_feature_snapshot()` 於 `evaluate_predictor_gate()` **頂端**呼叫（**早於 `use_edge_predictor` 短路檢查**），僅 `features: Some + context_id: 非空` 時發射。`ts_ms=0` 源頭略過；`try_send` best-effort（full/closed → warn+drop）；tx 未接線 → 靜默 no-op。採集路徑不受 predictor 啟用/禁用狀態影響。
- **`event_consumer/{types,mod,handlers}.rs`**：`EventConsumerDeps.decision_feature_tx` 欄位 + `run_event_consumer` destructure + wire-up 呼叫（`set_shadow_fill_tx` 後） + handler 匹配臂（讀 `pipeline.decision_feature_tx()` 構 msg → `try_send` → Full/Closed warn、no-tx info）。3 handler 穿透測試。
- **`tasks.rs`**：`spawn_db_writers` 4→5 tuple，新增 `channel(1024)` + `run_decision_feature_writer` spawn。Pool 不可用時早 return 5-tuple of None。
- **`main.rs`**：5-tuple destructure + paper/demo/live 三個 `EventConsumerDeps` 構造點注入 `decision_feature_tx.clone()`。
- **`intent_processor/tests.rs`**：4 新發射測試（預測器禁用仍發射 / 空 context_id 不發射 / None features 不發射 / ts_ms=0 不發射）。

**測試**：lib **1264→1285**（+21：6 hash + 6 writer + 3 handler + 4 emission + 2 零碎）· core 372 · e2e 35 · **total 1671→1692 pass / 0 fail**。

**下一步**：Step 7b `ReloadEdgePredictor` IPC（Python route 沿用 `ReloadRiskConfig` 授權）· Step 7c `EmitShadowFill` Python consumer（Option B 對照處理，寫 `learning.decision_shadow_fills`，DB CHECK `engine_mode='paper'`）· Step 7d-7f（`write_toml_atomic_fsynced` / `DisableEdgePredictorAll` 兩階段 / `GET /capabilities`）。5 條餘項可獨立前推，不 blocked。真 unblock = ML-MIT #26 首 ONNX。

### ENGINE-HEAL — 引擎自癒 4 Fix（2026-04-14）

**背景**：2026-04-14 事故 — Rust 引擎靜默死亡 18 分鐘無自動重啟、無死前日誌、ws tick 死前 14+ 分鐘已斷但進程仍「存活」。**交付 4 道 fix**：**Fix 1 panic hook**（`main.rs` L55-108，`std::panic::set_hook` 捕 thread id/location/payload/backtrace + flush → tracing::error，覆蓋所有 tokio worker & std thread，結構化輸出）；**Fix 3 crash-only**（`run_pipeline_crash_only<F>()` 包 paper/demo spawn + Live thread catch_unwind 後補 `live_cancel.cancel()`，任一 panic → 廣播 `Crashed(kind)` + cancel 全局 → ordered shutdown → exit，**不嘗試 isolate 繼續**）；**Fix 4 WS tick stale 自救**（`main.rs` L1108-1155，30s 週期檢查 `shared_last_tick_ms`，age > 120_000ms 且 last!=0 → `cancel.cancel()`，業務層存活斷言防殭屍進程）；**Fix 2 watchdog 自動重啟 + 4 道保險**（`engine_watchdog.py` + `stop_all.sh` + `restart_all.sh`）：(1) `fcntl.flock(/tmp/openclaw/watchdog.lock, LOCK_EX|LOCK_NB)` 多實例防重入 (2) `/tmp/openclaw/engine_maintenance.flag` operator 意圖守則（stop_all.sh 建，restart_all.sh 清）(3) SIGTERM-first + 5s graceful + SIGKILL fallback 避免寫 paper_state.json 中途被殺留損毀 tmp (4) 指數退避 [60,120,300,600,3600]s + `MAX_CONSECUTIVE_FAILURES=5` 熔斷寫 `canary_events.jsonl`。**Bonus**：`rotate_engine_log()` mv 舊 engine.log 到 `/tmp/openclaw/engine_logs/engine-<epoch>.log` 保留 10 份 — Phase 0 發現 `restart_all.sh` 之前用 `>` truncate 是事故放大器，**沒它任何事故都會沒死因**。**決策**：D1 全部 crash-only 含 Live（isolate 會讓三引擎共享的 `RiskConfigStore` 污染帶病繼續交易）· D2 WS stale 120s（60s 誤報太多，worst case ~3min zombie 可接受）· D3 Phase 0 medium（30min 讀 journalctl + grep exit 路徑）。**驗證**：Rust lib 1144 + core 366 + e2e 33 = **1543** pass · 0 fail（與 pre-fix baseline 一致）· watchdog 8/8 unit checks · `bash -n` clean。**留尾**：運行中引擎仍 pre-fix binary（operator 需 `restart_all.sh --rebuild` 部署） · Task #8 殭屍 `openclaw-trading-api.service` 1074+ 次 restart 循環 · env 可覆蓋 stale threshold / per-tier threshold / metric export 為 Phase 2。Worklog：`docs/worklogs/2026-04-14--engine_self_healing.md` + KnownIssue：`docs/known_issues/2026-04-14--ws_stale_detector.md`。

### WP-F/UX-07~10 術語統一 + Live 雙態註解（2026-04-14 · commit 19a84da）

**背景**：GUI 11 個 tab 對 Paper / Demo / Live / Session 有 4+5+6+5 個中文變體共用（纸上交易 / 模拟交易 / 模拟引擎 / 测试引擎 / Bybit Demo 执行引擎 / Demo 引擎 / 实盘交易 / Session Halted / Paper Trading Session / AI 推理会话 / 交易会话 …），tab bar label vs 內部 `<title>` 11 個中僅 1 個一致。**規範字典**：`Paper 模拟` / `Demo 演示` / `Live 实盘` 全域統一；Tab bar `中文 English` 雙語格式。**Session 語境消歧**：Paper Trading Session → Paper 会话；Demo Session Controls → Demo 会话控制；AI 推理会话 / Session History → AI 推理 / AI 推理历史；Session Halted → 交易暂停 Trading Halted；governance 交易会话 → 授权租约 Lease。**Pass-4 Live 槽雙態註解**（Phase 6 Live-Demo 虛擬 key 設計）：tab-live.html L178-188 新增雙語資訊區塊，明確「Live 槽可填入 Mainnet API 或 Live-Demo 虛擬 key（後者跑 Demo 服務器但走 Live 代碼路徑），兩者統一走 Live 最嚴標準（紫色主題 / Global Mode Gate / 二次確認 / 完整風控棧）」；tab-settings.html L773 Live-Demo key 卡片補 `⚠ Live-Demo 等同 Live 待遇` 行。**執行**：3 sub-agent 平行派發（Group A console+system+strategy+risk 4 檔 / B ai+governance+settings+live+governance-tab.js 5 檔 / C paper+demo+learning+monitoring+phase4+app.js+common.js 7 檔）+ 主會話 E2 補修 legacy `index.html`（`legacy_routes.py` 仍 serve）。console.html `BUILD_TS` `20260410.live-ui-v2` → `20260414.ux07-unify-v1` 強制 iframe 緩存刷新。**零後端改動**：所有 JSON API 鍵 / CSS class / 函數名 / endpoint / data-\* 屬性未觸碰，純展示層。16 文件 +160/-143 行。E2 grep sweep 確認無 user-visible 殘留舊詞（僅 JS/CSS 註釋保留）。

### QoL-1 PaperState 重啟還原 + QoL-3 PyO3 統一部署（2026-04-14 · commits 22a0b36+ea25844 · c510388+dc2eec3）

**QoL-1**：引擎重啟後 `paper_state.total_realized_pnl / total_fees / trade_count` 歸零導致 GUI 累計 PnL 卡片失真。**方案**：`PaperState::restore_from_db(pool, engine_mode)` 按 `engine_mode` 從 `trading.fills` 聚合（`COALESCE(SUM(fee),0)` / `COALESCE(SUM(realized_pnl),0)` / `COUNT(*) FILTER (WHERE realized_pnl <> 0)` — 只數 close leg 避免 open/close 雙記）；`apply_restored_counters()` 純函數 helper 重建 `balance = initial_balance + pnl_sum - fees_sum`。新增 `event_consumer/paper_state_restore.rs`（81 行）fail-soft glue（None pool → info / SQL err → warn / 成功 → info with values，引擎永遠能啟動）。三引擎按 `engine_mode` 隔離：demo=-3.49/29.11/254 · paper=-14.40/58.21/333 · live=0/0/0 重啟驗證 PASS。**QoL-3**：`maturin develop` 一次一個 venv 容易漏，每個 venv 觸發完整編譯。**方案**：`helper_scripts/build_pyo3.sh`（285 行）改用 `maturin build` 生 wheel → `pip install --force-reinstall --no-deps` 雙寫 `~/.venv` + `control_api_v1/.venv`。跨平台：`stat -c/-f` dual fallback / bash 4 guard / `mktemp -d -t`。Exit codes 0 ok / 1 args / 2 build / 3 install / 4 verify。`restart_all.sh` 新增 `--rebuild` 旗標（任意位置），build 失敗 exit 2 不啟動服務。**Scope 注意**：`--rebuild` 只重建 PyO3 `.so`，**不重建** `openclaw-engine` binary。**執行**：git worktree 隔離兩 E1 平行完成，QoL-3 先合（純腳本零運行風險）→ QoL-1（需 rebuild + restart）。E4：engine lib 1136 → **1144**（+8 來自 `apply_restored_counters` helper + fail-soft glue unit tests）·Rust 總計 1535 → **1543**。Worklog：`docs/worklogs/2026-04-14--qol_1_and_qol_3_delivery.md`。

### ORPHAN-ADOPT-1 Phase 1 — Reconciler 孤兒主動平倉（2026-04-14）

**背景**：Reconciler seed 完成後對 orphan 倉（Bybit 有倉、baseline 無追蹤）「偵測但不動作」，只有 burst ≥5 drifts 連續 2 cycles → CircuitBreaker + CloseAll 才清。單個 orphan 會留在交易所自生自滅（無止損、funding 累積）直到 operator 手動干預。**交付**：新增 `position_reconciler/orphan_handler.rs`（~350 行 + 11 unit tests）純函數 `handle_orphan(ctx) -> OrphanDecision`，按 A1→A4→B1→default 順序評估：A1 距強平 < 10% / A2 已 CB / A3 名義 > `max_order_notional_usdt`（0=disabled）/ A4 不在 scanner active universe / B1 五策略 shrunk_bps 全非正且 unrealised > 0 → SoftLockProfit / default → SoftConservative。**執行**：Phase 1 所有 decision 走 `PipelineCommand::CloseSymbol { symbol, hint_is_long, hint_qty }` reduce_only，dispatch 失敗回退 drift 讓 Phase 6 升級階梯兜底。**防 spam**：`ReconcilerState.pending_orphan_closes: HashMap<String, u64>` + 2 分鐘 TTL dedup + opportunistic GC。**Per-engine 接線**：`main.rs` `build_orphan_cfg(engine_key)` closure factory 按 engine 綁 `PerEngineRiskStores.select()` + `SymbolRegistry` + `EdgeEstimates` Arc，`spawn_position_reconciler` 多 `orphan_handler_config: Option<OrphanHandlerConfig>` 參數（None=disabled）。`run_position_reconciler` 重構：直接調 `pos_mgr.get_positions()` 保留 raw `Vec<PositionInfo>`（需 liq/mark/unrealised 三字段），`process_orphans()` helper 在 drift classification 後、`evaluate_actions` 前過濾處理。**Audit**：V014 event `orphan_handled`，config_name `reconciler.orphan_handler`。**Phase 2 延後**：真實 Adopt 路徑（合成 StrategyId + paper_state 注入 + StopManager 綁定）等 G-1 R-02 Strategist Agent；`OrphanDecision::Adopt` enum variant + `OrphanStage::SoftAdoptEligible` 分支已預留。**測試**：58 reconciler tests（47 pre-existing + 11 新 orphan_handler unit tests）+ 1136 engine lib + 366 core + 33 e2e = 1535 Rust pass · 0 fail。

### OC-5 FundingArb Complete + WP-F GUI Quick Wins（2026-04-13）

**OC-5 FundingArb** — Full `on_tick()` implementation replacing stub. **Data pipeline**: `index_price: Option<f64>` added to PriceEvent → WS tickers `indexPrice` extraction → `TickPipeline.index_prices` HashMap cache → `TickContext.index_price`. **Strategy logic** (~280 lines): entry evaluation (funding_threshold + edge calculation with amortized costs + basis risk check via `|perp/index - 1|` + H0/cooldown/position guards) → direction (positive rate → short, negative → long) → confidence scaling (capped 0.6) → RC-04 rejection rollback. Exit on rate flip / basis breach / max hold. 22 new tests. TOML configs: paper/demo `active=true` (relaxed thresholds), live `active=false` (conservative). **WP-F GUI**: D-01 `applyAIAdvice()` → clipboard copy; AH-05 `btn-apply-ai` element added to tab-risk.html; UX-06 loading state for all `saveProviderKey()` (6 buttons) + `saveAIConfig()` in tab-ai.html. `tick_pipeline/mod.rs` compacted to stay under 1200-line limit. E2 PASS. E4: 1105 lib + 33 e2e = 1138 Rust · 0 fail.

### R-06-v2 Agent Value Delivery — Learning Loop Closure（2026-04-13）

**Deep analysis rejected original R-06** (100% plumbing, 0% value) → redefined as R-06-v2 "Agent Value Delivery". **Step 2: Analyst→DB→Strategist feedback** — `persist_analyst_feedback()` writes winning/losing patterns to new `learning.pattern_insights` table; `get_feedback_section()` reads patterns + Guardian rejection stats → appended to Strategist Ollama prompt. **Step 3: Guardian rejection stats** — queries existing `trading.risk_verdicts` JOIN `trading.intents` for per-strategy reject_rate (Rust already writes verdicts). **Step 1: Executor IPC bridge** — `_paper_engine=None` (broken since DEAD-PY-2) → `_execute_via_ipc()` fallback to Rust engine `SubmitOrder`; `_shadow_mode=True` default (log only, no actual trade, avoids Path A/B conflict). **Step 4: Conductor stub→real** — `_handle_conductor()` now calls real `Conductor.get_agent_health()` + degraded agent detection (was static "maintain_current"). **New files**: `ai_service_feedback.py` (~170 lines) + `V016__learning_feedback_loop.sql`. ai_service.py 1195→1195 lines (net 0 via docstring compaction). executor_agent.py +115 lines (513→628). **Not done**: fire-and-forget IPC, Conductor health polling, Rust→scout_scan (all zero-value). E4: 1091 Rust lib · 2852 Python · 0 fail.

### EDGE-P2-1 Close Fill Labeling Fix（2026-04-13）

**Root cause**: `emit_close_fill()` unconditionally wrapped ALL close fills with `strategy_name: format!("risk_close:{reason}")` — including strategy-driven closes. This inflated the apparent risk-forced exit count (327/435 in demo), making it impossible to distinguish strategy exits from risk checks. **Fix**: `close_tag` parameter is now written directly as `strategy_name` — callers pass prefixed tags: `strategy_close:*` / `risk_close:*` / `stop_trigger:*`. order_id changed from `risk_close_{em}_…` to neutral `close_{em}_…`. `realized_edge_stats.py` updated to recognize all three prefixes. Diagnostic SQL script added: `helper_scripts/db/close_fill_analysis.sql`. 5 files changed. E4: 1091 lib + 33 e2e = 1124 Rust · 0 fail.

### G-SR-1 Session 7 — C1-C2 Agent 接線 + PM 端到端驗收 COMPLETE（2026-04-13）

**C1 Analyst wiring** — `_handle_analyst()` 從 stub 升級為接入 AnalystAgent.analyze_trade()：IPC trade_data → TradeRecord 構建 → asyncio.to_thread() L1 分析 → 返回 strategy_metrics + strategy_rankings；agent 不可用時 stub fallback。**C2 Scout wiring** — `_handle_scout()` 接入 ScoutAgent.get_recent_intel()/get_recent_alerts()：IntelObject/EventAlert 序列化為 JSON-safe dicts + symbol 過濾；agent 不可用時 stub fallback。**Injection** — `create_ai_service_listener()` 新增注入 ANALYST_AGENT + SCOUT_AGENT from strategy_wiring（fail-open）。conductor_evaluate 仍為 stub（W23+ R-06）。MODULE_NOTE 精簡（bilingual 合併 -36 行）。ai_service.py 1080→1195 行（+115 net，MODULE_NOTE 精簡抵消新增）。**PM 驗收 6/6 PASS**：(1) PersistenceTracker 3 策略 check()/clear()/Close 免檢 (2) Grid 趨勢冷卻 ADX+Hurst 1x-6x (3) Confluence 4 分量 65 分 + qty 調整 (4) Strategist DB→IPC→Ollama→validate 全鏈路 (5) Guardian L1 分類+MessageBus 中繼 (6) C1-C2 注入+真實調用+fallback。**G-SR-1 計劃全部完成**（7 Sessions，Phase A+B+C）。E4: 1086 lib + 33 e2e = 1119 Rust · 2852 Python · 0 fail。

### G-SR-1 Phase B Session 6 — B2+B3+B4 Agent 真實接線（2026-04-13）

**B2 ai_service.py stub→real wiring** — `_handle_strategist()` 接入 Ollama param tuning（build prompt from metrics + current_params + param_ranges → JSON param recommendations，asyncio.to_thread 非阻塞）；`_handle_guardian()` 接入 Ollama event classification（risk_level low/medium/high/critical + assessment，informational only NOT trade blocking）；OllamaClient lazy singleton + fail-closed（unavailable→retain current params / input severity）。**B3 Rust IPC enhancement** — `evaluate_cycle()` 移動 `fetch_current_params()` 至 IPC 前，`current_params` + `param_ranges` 包含在 `strategist_evaluate` 負載，Python 可基於上下文做更好推薦。**B4 Guardian L1 MessageBus relay** — high/critical 事件通過 MessageBus 中繼給 Strategist（fail-open）；`create_ai_service_listener()` 注入 `MESSAGE_BUS` from strategy_wiring。ai_service.py +350 行（730→1080）；strategist_scheduler.rs +22 行（692→714）。B-E2 10/10 PASS · B-E4 1083+33=1116 Rust · 2852 Python · 0 fail · B-E5 PASS。

### G-SR-1 Signal Tightening Phase A Session 1+2（2026-04-13）

**Phase A S1: A0 基礎模組提取** — `grid_helpers.rs` 純函數提取（build_linear_levels/build_geometric_levels/nearest_grid_idx/compute_ou_step/rebalance）+ `confluence.rs` 共享模組（PersistenceTracker + compute_score 4 分量 65 分制 + score_to_qty_pct 5 段平滑插值 + ConfluenceConfig 三配置 trend/reversion/breakout）。

**Phase A S2: A0-c + A1 + A2 + A3** — A0-c：3 策略 TOML Params struct 加 confluence 字段（serde(default) backward compat）+ build_confluence_config() + StrategyFactory 接線 + R4-7 update_params rebuild。A1：PersistenceTracker.check() 時間制過濾器接入 ma_crossover/bb_reversion/bb_breakout entry path（MA/BBR 120s, BBB 60s），close 免檢 + clear() 清理。A2（提前實施）：weighted confluence scoring（trend 25/20/12/8, reversion 15inv/30/10/10, breakout qty-only 10% 底線），冷啟動 adx&&rsi None→全倉退化，min_notional guard。A3：Grid trend-adaptive cooldown（ADX 60% + Hurst 40%, 1x-6x 動態倍率，3 TOML 參數）。修復：bb_reversion 測試加 ADX 數據、dead `make_entry_intent()` 刪除、stress test pub 可見性、BbBreakoutParams TOML struct 補齊。Engine lib 934→1024 tests（+90），e2e 29→33（+4）= 1057 total, 0 fail。

### 04-12 審計修復 Wave 2：14 角色報告逐一核實 + 代碼修復（2026-04-12）

**A3 GUI 可用性審計全修** (commit `fd0bc45`)：CRITICAL×2 + MAJOR×14 + MINOR×18 + SUGGESTION×2 一次性全修。關鍵：Live/Demo/Paper 持倉「平倉」按鈕確認流程 + 空狀態提示 + 響應式間距 + 按鈕排列一致性。

**QC 量化審計全修** (commit `e03421f`)：Session 3.3+3.3b — 12 hardcoded 參數移至 TOML + 7 risk gap 修補 + 10 action items 全部解決。

**P2 FIX-08 超限文件拆分** (commit `50d7a4b`)：12+ 超過 1200 行硬上限的文件拆分（governance_routes / strategy_ai_routes / paper_trading_routes / strategy_read_routes / strategy_wiring / experiment_routes / live_session_routes / evolution_routes / backtest_routes）。

**P2 FIX-23/34/35/57** (commit `0de58bb`)：FundingArb 策略註冊 + outcome backfiller DDL + budget sync 修復。

**E3+CC 安全/合規修復** (commit `f8685bf`)：5 fixes + 2 報告更新 — Cookie secure flag + HMAC edge cases + error disclosure。

**E5+MIT 報告核實** (commit `c73a3f2`)：5 code fixes + 2 report corrections — 補漏 push_capped 缺失 + budget tracker sync。

**E5 審計收尾** (commit `6e2a01e`)：3 remaining items implemented + P-08 test fixed。

**FA 審計修復** (commit `d16ed08`)：3 orphan Rust files 刪除（batch_order_manager/leverage_token_client/spot_margin_client）+ handlers.rs 拆分 handlers_config.rs + PIPELINE_BRIDGE 死碼清理。

**AI-E 審計報告校正** (commit `4d427f5`)：18 inaccuracies corrected（3 Serious / 8 Medium / 7 Light — 均為報告錯誤非代碼 bug）。

**BB Bybit API 審計驗收** (commit `50a4b1e`)：7/7 P1 全部關閉 — 最終核實 worklog。

### E5 Performance Optimization — 23 items（2026-04-12）

P-01 `push_capped<T>()` ring buffer utility（13+ 重複消除）· P-02 PriceEvent 5 structured fields · P-03 hot-path structured reads · P-04 `now_ms()` utility · P-05 `is_stale()` utility · P-06 WS subscriptions Vec→HashSet O(1) · P-08 `TickContext<'a>` zero-copy borrowed refs（5 strategies + orchestrator）· P-09 Arc<RiskConfig> bind-once · P-10 parallel async DB flush `tokio::join!` 7 tables · S-01 confidence clamp · S-02 ring-buffer dedup（+E2 residuals）· S-03 `build_intent()` · S-04 timestamp centralize（+E2 residual）· R-01~R-05 naming（`ShadowOrderRequest`→`OrderDispatchRequest` 等）· D-01/D-03 dead method removal。P-07 skipped（WS SDK managed）· S-05 skipped（fail-closed）· D-02 deferred（HashMap removal post-migration）。17 files changed, +563/-899, net -336。E4: 934+366+27 = 1327 pass 0 fail。

### 審計 P2 Batch A+B：10 項快速修復（2026-04-12）

FIX-21 lib.rs 3 孤立模組移除（batch_order_manager/leverage_token_client/spot_margin_client）· FIX-38 CLAUDE.md §九 Singleton 表補登 6 項（_pool/DEFAULT_LEASE_TTL_CONFIG/_backtest_engine/_scheduler/_evolution_engine/_ledger）· FIX-41 Bearer Token panel 死碼清除（index.html/app-gui.js/app-review.js/styles.css）· FIX-44 tab-learning/monitoring/strategy 加載失敗狀態 UI · FIX-45 Live tab 刷新 30s→15s · FIX-46 tab-risk.html 已達標（510 行，無需拆分）· FIX-51 3 DEPRECATED 文件移至 archive/ · FIX-53 docs/README.md 補 4 子目錄索引 · FIX-54 CHANGELOG 缺失 commit 補錄 · FIX-56 Layer2 定價日期 2026-03-27→04-12。

### PNL-FIX-1/2 + 3 項重要中間修復（2026-04-12）

**PNL-FIX-1** (commit `2a422fa`)：`on_tick.rs` 5 條 close 路徑誤用 `event.last_price` 跨 symbol 平倉 → 改用 per-symbol latest_price。**PNL-FIX-2** (commit `cbb4e45`)：`emit_close_fill` 寫 `fee: 0.0` → 所有平倉路徑收真實費用。**Circuit Breaker 修復** (commit `6ae6e1b`)：3 fixes 防止誤觸 CB + spam。**EA-Persist** (commit `0255a35`)：execution_authority 統一至 T0 trust persistence。**Paper/Demo Session Split** (commit `986d724`)：Paper/Demo 獨立 session 控制。

### 3E-ARCH 中間修復合集（2026-04-11~12）

(commit `d670759`) cross-pipeline DB ID 碰撞修復 — ID 嵌入 engine_mode。(commit `f6e7afc`) paper_state 啟動時從交易所快照 seed。(commit `b5e45f7`+`8e08c34`) private WS topic 環境感知修復。(commit `152d1f6`) demo DCP topic 移除 + live worker_threads 2→4。(commit `660cb75`) scanner/deployed 顯示 Rust active symbols。(commit `87bbe66`) live-gui 條件單顯示 + per-engine session/metrics。(commit `9853845`) paper-metrics 改用 Rust 權威 balance/peak。(commit `35272d3`) IPC 所有命令加顯式 engine 參數修復跨引擎路由。(commit `56c648f`) paper_only 模式 + cost_gate 冷啟動探索。(commit `15203f6`) 動態 is_exchange_mode 防 live WS 覆寫 paper state。(commit `326a191`) 移除 handlePaperAction 硬編碼 initial_balance:10000。(commit `2473efb`+`6bafa4e`) demo/live GUI 平倉路由修復。

### 審計 P2 Rust 7 項修復（2026-04-12 · commit `84f00eb`）

FIX-24 bb_reversion RSI 閾值 30/70→TOML 可配 + ParamRange agent-adjustable · FIX-25 grid_trading fee_rate 字段取代硬編碼常量 · FIX-26 bb_breakout squeeze bool→時間戳 30min 過期 · FIX-27 kelly_sizer 負 edge 拒絕（0.0）非 fallback · FIX-28 intent_processor account_leverage 字段 · FIX-31 PriceEventKind typed enum（Trade/Orderbook/Ticker/Liquidation/PriceLimit/AdlNotice/RestPoll）+ 向後兼容 metadata 雙路徑 · FIX-33 event_consumer exec_id 去重 O(n)→O(1) HashSet+VecDeque。15 files changed, +199/-194。E4: 965+366+27+29+2852 = 4239 pass。

### 全程序鏈審計 P0+P1 全修 + 二輪驗證 + CONCERN 修復（2026-04-12）

**Session 1 (P0 8/8)**：FIX-03 FastTrack ReduceToHalf/PauseNewEntries 實現 · FIX-04 真實 price_drop/margin_util · FIX-09 ocEsc 單引號 · FIX-10 IPC HMAC Live 強制 · FIX-13 edge_estimates +14 tests · FIX-14 REST fail-closed +7 tests · FIX-15 三管線並發 +1 test · FIX-19 execFee taker_fee_rate 估算。

**Session 2 (P1 18/18)**：FIX-05 correlated_exposure_pct 實現 · FIX-06 grid_levels TOML→runtime · FIX-07 OU theta non-OU fallback · FIX-11 Cookie secure auto-detect · FIX-16 startup +5 tests · FIX-17 ConfigStore 並發 +2 tests · FIX-18 Price=0 +2 tests · FIX-20 pre_check_order 刪除 · FIX-22 MlSwitches 4 死欄位刪除 · FIX-29 on_tick 1307→1186 行 · FIX-30 symbol.clone 審查（文檔結論）· FIX-32 risk_config 借用 · FIX-39/40 Danger Zone + 策略刪除 openConfirmModal · FIX-47/48 REFERENCE/KNOWN_ISSUES 更新 · FIX-52 SCRIPT_INDEX 全面重寫 · FIX-55 API paths verified。

**二輪嚴格驗證**：8 組並行 agent 逐行讀碼，26/26 PASS。發現並修復 3 CONCERN：(1) **FIX-03b** ReduceToHalf 缺 `dispatch_close_order()` — Live 模式下本地狀態與交易所倉位脫節 **[HIGH]** → 已補 dispatch；(2) **FIX-19b** 單一 fee rate 近似所有 symbol → 改用 `intent_processor.fee_rate(&symbol)` per-symbol 3 級解析；(3) **FIX-16b** 2/5 tests trivially passing → 替換為 semver 驗證 + env valid/invalid/negative/zero。

**KNOWN_ISSUES**：TRADE-2 → RESOLVED（Rust 同步 tick 無競態）· TRADE-4 → RESOLVED（Rust 每筆 fill 獨立 exec_qty）· 統計修正 OPEN 9 / RESOLVED 15。

965 engine lib + 5 bin + 29 e2e = 999 tests · 0 failures。

### Earned-Trust TTL Ladder + Audit Trail 時間戳修復（2026-04-12）

(1) **Audit Trail 時間戳修復**：`tab-governance.html` JS 讀 `r.timestamp` 改為 `r.when_ms || r.when*1000`，修復 Audit Trail 時間欄永遠顯示 `'--'` 的 bug。(2) **Earned-Trust 授權 TTL 階梯**：新增 `earned_trust_engine.py`（715 行）— T0(24h)/T1(72h)/T2(168h)/T3(360h) 四層階梯，連續乾淨天數晉升，中途降級即時標記（session 繼續），T3 最多自動續期 1 次後強制 Operator 全面審查；新增 `live_trust_routes.py`（484 行）— 3 端點（GET trust-status / POST renew / POST renew-review）；`live_session_routes.py` 新增 session start/stop 鉤子 + `_grant_execution_authority_internal()` 內部輔助；`main.py` 注冊 `live_trust_router`；`tab-live.html` 新增 Trust Status Bar（tier badge + 倒計時 + 續期卡 + T3 全面審查面板）+ 完整 JS（loadTrustStatus / openTrustRenewCard / submitRenew / submitFullReview）。53 新測試 pass。E4: 2852 Python passed。

### Phase 6 PM 驗收 PASS + TODO 歸檔整理（2026-04-12）

6-09~13 最終驗收週期完成。E4: 935 engine lib + 366 core + 18 e2e + 32 promotion = 1351 passed / 0 failed / 0 warnings。E2: Reconciler 0 BLOCKER 0 MAJOR（pre_escalation_level 文檔建議 MINOR）· Promotion Pipeline 0 BLOCKER 0 MAJOR（governance_routes 超限 pre-existing）。QA: 三引擎存活 + 雙 Reconciler 運行 + baseline seeded + API auth enforced。E5: stress PASS。Phase 6 路線圖狀態從 🟡 升為 ✅。TODO.md 歸檔：晚間 Audit BLOCKERs（B-1/B-2/M-1~4）+ Phase 6 驗收詳情移入 `docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`；3E-ARCH 折疊內容移除（已有專屬歸檔）；排期表更新 W19-21 ✅；Gap 索引標記 G-3/G-5/G-9 完成。

### GUI 指標 DB 降級 + 顯示修復 4 項（2026-04-12）

(1) Live engine badge 顯示「已暫停」— `get_live_session_status()` 改用 `get_engine_snapshot()` 讀頂層 `paper_paused`。(2) Performance Metrics 全 0 — 新增 `fetch_fills_from_db(engine_mode)` DB 降級讀取，paper 1336 fills / demo 68 fills 正確顯示。(3) Live 掛單 Price/Status 顯示 "--" — `OrderInfo` 新增 `trigger_price` 欄位 + JS snake_case 兼容。(4) Demo 夏普比率硬編碼 N/A — 改為從 round-trip PnL 計算。worklog: `docs/worklogs/2026-04-12--gui_metrics_db_fallback_and_display_fixes.md`。935 engine lib + 366 core + 22 paper_metrics pass。

### 3E-ARCH GUI 路由修復：Paper tab 顯示 Live 引擎數據（2026-04-11）

3E-ARCH 上線後 Paper GUI tab 顯示 ~$612 餘額且持倉表為空，實際 paper 引擎是 ~$9941 / 9 倉位。**根因**：`main.rs:563-708` `is_primary` 優先序為 Live > Demo > Paper（`paper.is_primary = !has_live && !has_demo` / `live.is_primary = true`），三引擎並行時 Live 寫入 compat `pipeline_snapshot.json`；而 Python `RustSnapshotReader.get_paper_state()` / 多數 helper 預設讀 compat 檔，因此 paper 路由全部讀回 Live 數據。**On-disk 驗證**：四份檔案內容正確獨立，bug 純粹在 Python 路由層。**修復**：(1) `ipc_state_reader.py` `get_paper_state(mode/engine)` 預設透過 `get_engine_snapshot("paper")` 讀 `pipeline_snapshot_paper.json`；`get_snapshot()` 新增可選 `engine=` 參數（保持預設讀 compat 以維持單元測試 / 單引擎部署兼容）。(2) `paper_trading_routes.py` 9 個 call site 改為顯式 `engine="paper"` / `mode="paper"` + `is_engine_available("paper")` 取代 `is_available()`（涵蓋 session/status、positions、pnl、orders、fills、metrics、export、market-feed/status、shadow/decisions、audit-trail、resume）。(3) `risk_routes.py` 3 個 call site 改 `engine="paper"`（風控儀表板讀 paper 引擎 drawdown/balance/gate stats）。(4) `strategy_read_routes.py` intent reader 改 `mode="paper"`。(5) `live_session_routes.py` fills 降級分支改 `mode="live"`。**回歸測試**：`test_ipc_state_reader.py` 新增 `TestPerEngineRouting`（6 tests）覆蓋三引擎並存路由矩陣，使用 11111.11/22222.22/33333.33 三組哨兵餘額（class 級常數 + docstring 標明刻意用假數值）。**驗證**：21/21 ipc_state_reader + 39/39 ipc_integration + 80/80 paper_live_gate/paper_metrics passed。Reader 直接讀真實 `/tmp/openclaw/pipeline_snapshot_*.json`：`get_paper_state()` 預設返回 9941.47 / 9 倉位（之前是 612.95 / 0 倉位）。

### 3E-ARCH 持久化修復：with_kind() 漏設 pipeline_kind 字段（2026-04-11）

MEGA-BLOCKER-0 commit 0f3af65 留尾 bug：`TickPipeline::with_kind()` 只設 `governance` 不設 `pipeline_kind`，三個引擎全部留在 `with_balance()` 預設的 `PipelineKind::Paper`，導致 demo/live event_consumer 在 `kind_tag = pipeline.pipeline_kind.db_mode()` 時都返回 `"paper"`，三引擎 StateWriter 搶寫同一份 `paper_state.json` / `pipeline_snapshot_paper.json`，產生大量 `state rename failed` ERROR；watchdog 因此誤報 demo/live "not_running"。**修復**：`tick_pipeline/mod.rs:683` `with_kind()` 補一行 `p.pipeline_kind = kind`。**回歸測試**：`test_with_kind_sets_pipeline_kind_field` 鎖定三個 variant。**驗證**：重啟後 `pipeline_snapshot_paper.json` / `pipeline_snapshot_demo.json` / `pipeline_snapshot_live.json` 三檔案各自獨立寫入（balance 10000/793.97/612.95 對應 Paper 默認/Demo Bybit/LiveDemo Bybit），watchdog 三引擎全 alive，0 persistence errors。930 engine lib pass（+1 regression test）。

### 3E-ARCH L3 審計修復：e2e 測試 + 21 warning 清零 + 防御性加固（2026-04-11）

L3 全面審計（PM/PA/FA/CC/E3/E4/E5/MIT/QC 9 角色並行）發現並修復所有問題。**P0**：`stress_integration.rs` 6 個編譯錯誤修復（StrategyAction enum 適配 + IntentProcessor 5th arg GovernanceProfile）。**P2 防御性加固**：(1) event_consumer D19 安全斷言（交易所管線禁止寫入 market/feature DB）；(2) 快照去抖間隔按引擎錯開（Paper 5s/Demo 5.5s/Live 4.5s）避免 I/O 爭用；(3) IPC `extract_engine_tx` 無 engine 參數時 debug 提示；(4) startup.rs 憑證記憶體持留文檔化；(5) fan-out channel buffer 非對稱設計文檔化。**P3 代碼清潔**：21 cargo warning 全部清除 — 6 unused imports + 6 unused variables + 4 unreachable patterns（sector 重複分類）+ 2 dead methods（`cost_gate_k` #[allow] / `make_exit_intent` 刪除）+ 2 never-read fields + 1 unused inner import。**INFO**：Python ipc_client.py `mode` → `engine` 參數重命名語義修正。0 warnings / 929 lib + 366 core + 29 e2e + 2792 Python = 4116 tests passed。

### 3E-ARCH MEGA-BLOCKER-0：真正三引擎獨立並行（2026-04-11 · commit e012faa）

完成原始 3E-ARCH Phase C（3E-10.1）設計中未實現的「三個獨立 spawn」。**startup.rs**：新增 `ExchangePipelineBindings` struct + `build_exchange_pipeline()` 按 API key 獨立構建每條交易所管線（DCP/auto-margin/fee/balance/Private WS 全封裝）；刪除 `determine_primary_kind()` / `detect_available_pipelines()` / `fetch_exchange_balance()`。**main.rs**：刪除「primary+alongside」二管線模型，改為三獨立 spawn（Paper 永遠啟動 + Demo 條件 + Live 條件 D17 OS thread）；`Vec<Sender>` 動態扇出取代固定 primary+paper 雙通道；三獨立 IPC cmd channels 全填充 `EngineCommandChannels`；D23 per-exchange Reconciler（Live + Demo 各自獨立）；有序 shutdown Live→Demo→Paper。2 files, +482/-469 行。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase G 殘留修復：M-3/M-4 + 8 MINOR（2026-04-11 · commit 910d2bc）

M-3：`on_tick.rs:497,616` GovernanceProfile hardcoded → `self.pipeline_kind.governance_profile()`（Demo 現用 Validation cost_gate）。M-4：Live pipeline 線程加 `catch_unwind` + panic → `Crashed` 廣播 + health=Down；shutdown JoinError panic 記錄而非靜默丟棄。m-1：`handle_get_state()` 合併 2 次 snapshot 讀取為 1 次。m-2：`std::ptr::eq` → `primary_label()` 字串比對。m-3：`determine_primary_kind()` 3→1 次調用。m-5：`.unwrap()` → `.expect()` with context。m-8：`AuditWriter` 新建檔案 chmod 0600。殘留僅 M-1/M-2 文件大小監控。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase G: 9 角色重審 PASS（2026-04-11 · commit de222bd）

Phase A-F 修復完成後重跑 9 角色並行 E2 審查（E2/FA/PA/QC/BB/MIT/E3/E4/E5）。結果：**9/9 PASS — 0 BLOCKER / 4 MAJOR（非阻塞）/ 10 MINOR**。原 10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0 全部確認修復。測試基線：929 engine lib + 366 core + 18 e2e = 1313 passed / 0 failed / 0 ignored。4 殘留 MAJOR：handlers.rs 1195 行近上限、on_tick.rs 1172 行、GovernanceProfile hardcoded（TODO 3E-2b）、無 catch_unwind 包裹 pipeline（Live 前修）。審計報告：`docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`。

### 3E-E2 Phase F: 5 超限文件拆分（2026-04-11 · commit 26b9926）

BLOCKER-9：5 個超 1200 行硬上限文件拆分為目錄模組。tick_pipeline.rs 3907→mod.rs(1122)+on_tick.rs(1172)+commands.rs(708)+tests.rs(930)。ipc_server.rs 3223→mod.rs(975)+handlers.rs(1195)+tests.rs(1058)。main.rs 2243→main.rs(930)+startup.rs(716)+tasks.rs(488)。intent_processor.rs 1785→mod.rs(493)+gates.rs(204)+router.rs(499)+tests.rs(597)。position_reconciler.rs 1397→mod.rs(617)+escalation.rs(351)+tests.rs(438)。22 files changed, 11645 insertions(+), 11707 deletions(-)。929 lib + 366 core + 18 e2e pass。

### 3E-E2 Phase E: 25 blocker tests（2026-04-11 · commit e0a7451）

BLOCKER-10：補 25 個 blocker 測試覆蓋 D2（startup barrier）、D6（cross-engine events + PipelineHealth）、D15（global notional cap 8 tests）、D23（snapshot versioning 3 tests）。929 engine lib + 366 core + 18 e2e pass。

### 3E-E2 Phase D: Architecture hardening（2026-04-11 · commit e04c974）

3 BLOCKER + 4 MAJOR：BLOCKER-2（D6 三級故障收縮 EngineEvent/PipelineHealth/broadcast）、BLOCKER-3（D15 全局名義值上限 AtomicU64 + check_global_notional_cap）、BLOCKER-4（D17 Live 獨立 runtime std::thread + worker_threads(2)）、MAJOR-2（startup barrier oneshot 60s timeout）、MAJOR-3（有序 shutdown WS→IPC→primary→paper 10s）、MAJOR-5（IPC audit log）、MAJOR-7（snapshot schema_version 2.0.0 + written_at_ms）。

### 3E-E2 Phase B+C: Per-engine TOML + TradingMode deletion（2026-04-11 · commit 41d5a71）

BLOCKER-8（per-engine TOML params）+ MAJOR-4（TradingMode 殘留清除）+ 3E-10.1~10.7（DB dedup / channel rename / D12 audit / Python env var / config 橋接刪除）。`TradingMode` enum 從 Rust 完全刪除（僅保留 config 反序列化過渡）。PerEngineRiskStores + StrategyFactory::create_for_engine()。

### 3E-E2 Phase A: Quick fixes（2026-04-11 · commit a1c3291）

BLOCKER-5（hmac.compare_digest constant-time）、BLOCKER-6（5 處 std::sync::RwLock→parking_lot::RwLock）、BLOCKER-7（API key save lock 串行）、MAJOR-1（StateWriter chmod 0600 + regression test）。

### 3E-5+7+8: Per-engine snapshots + Python cleanup + API key conflict + Paper GUI（2026-04-11）

**3E-5 (S10) Rust**: `DualStateWriter` wrapper in persistence.rs — per-engine snapshot files (`pipeline_snapshot_{paper|demo|live}.json`) + compat `pipeline_snapshot.json` for primary. `EventConsumerDeps` gains `is_primary: bool`. event_consumer derives filename from `pipeline_kind.db_mode()`. +2 tests (DualStateWriter writes both / no-compat).
**3E-5 (S10) Python**: `_get_trading_mode_from_engine()` → `_get_live_engine_kind()` (live routes always query live/demo engine, no single-mode assumption). `ipc_state_reader.py` rewritten: per-engine cache system, `get_engine_snapshot(engine)`, `get_active_engines()`, `is_engine_available(engine)`, backward-compat primary fallback. `paper_trading_routes.py`: `trading_mode` → `pipeline_kind` in session status response. `strategy_ai_routes.py`: docstring updates.
**3E-7 (S11)**: `settings_routes.py` save_api_key: cross-slot conflict detection — same API key cannot be used by two pipelines (409 response). Checks demo↔live/live_demo pairs.
**3E-8 (S11)**: `engine_watchdog.py`: multi-snapshot monitoring — checks all 4 snapshot files, system alive if ANY engine is fresh. `get_watchdog_status()` returns per-engine status. `tab-paper.html`: Initial Balance input field next to Start button (GUI-configurable, fallback to Demo balance). `POST /api/v1/paper/config` endpoint: persists `initial_balance_usdt` to `settings/paper_config.toml`. `GET /api/v1/paper/config` reads it back.
**Files**: persistence.rs (+32), event_consumer/{mod,types,handlers,tests}.rs, main.rs, ipc_state_reader.py, live_session_routes.py, paper_trading_routes.py, strategy_ai_routes.py, settings_routes.py, engine_watchdog.py, tab-paper.html. **Tests**: 896 engine lib + 366 core + 2792 Python passed.

### 3E-3+4: IPC EngineCommandChannels + TradingMode→PipelineKind cleanup（2026-04-11）

**3E-3 (S8)**：`EngineCommandChannels` struct 取代單一 `pipeline_cmd_tx`。Paper/Demo/Live 各自獨立命令通道。`extract_engine_tx()` helper 按請求 `engine` 參數路由。`handle_set_system_mode_broadcast()` 廣播到所有管線。`add_engine_mode`/`switch_engine_mode` IPC handler 移除 + `PipelineCommand::AddMode`/`SwitchMode` 移除。main.rs 接線：primary_cmd_tx + paper_alongside_cmd_tx → EngineCommandChannels。
**3E-4 (S9)**：`PipelineSnapshot.trading_mode` → `pipeline_kind: PipelineKind`（serde rename 向後兼容）。TickPipeline `trading_mode` field → `pipeline_kind`。mode_states/active_modes/set_trading_mode/add_mode 等多模式基礎設施整體移除。event_consumer runtime TradingMode 引用全部替換為 PipelineKind。config/mod.rs TradingMode 保留（`#[deprecated]`）供 config 反序列化過渡使用。5 個死測試移除，1 個新測試。
**文件**：ipc_server.rs（+60/-80）、tick_pipeline.rs（-180 mode switching）、pipeline_types.rs、event_consumer/mod.rs、handlers.rs、main.rs。
**測試**：894 engine lib（-4 死測試 +1 新）+ 366 core pass。

### 3E-2b-β+γ: Per-engine private WS + reconciler engine label（2026-04-11）

**D21**：`spawn_private_ws_supervisor()` 提取為可重用函數。每交易所管線獨立 BybitPrivateWs + ExecutionListener。日誌含 `engine=` 欄位區分管線。原 inline 130 行 → 函數式結構 `PrivateWsBindings` struct + helper function。
**D23**：`run_position_reconciler()` 新增 `engine_label: String` 參數。V014 audit payload 加 `"engine"` 欄位，區分多對帳器輸出。`spawn_reconcile_audit()` + `spawn_action_audit()` + `dispatch_action()` 全部加 label 參數。
**Ordered shutdown**：Paper-alongside handle 加入 shutdown 等待序列。Private WS handles 通過 CancellationToken 自行退出。
**文件**：main.rs（private WS 提取 +80/-130）、position_reconciler.rs（+15 engine_label 貫穿）。
**測試**：898 lib + 18 e2e pass（無新增，重構保守）。

### 3E-2b-α: Pipeline spawn skeleton + bounded fan-out + parking_lot + DB pool（2026-04-11）

**D25**：`default_pool_max()` 5→20，支撐 3 pipeline + 2 reconciler + scanner 並行。
**D12**：`parking_lot::RwLock` 替換跨管線共享的 `std::sync::RwLock`（EdgeEstimates in main.rs/scanner, InstrumentInfoCache）。非中毒語義，避免單管線 panic 級聯崩潰。
**D10/D20**：有界扇出（bounded fan-out）— 單一 WS event_rx → `Arc<PriceEvent>` 廣播到 N 管線。Paper 1024、Demo 1024、Live 512 buffer。`try_send` 延遲檢測。
**Spawn skeleton**：Paper 管線始終啟動。Demo/Live 管線根據 TradingMode 條件啟動（interim，3E-4 改為直接讀 API key）。Paper-alongside 獨立 pipeline_cmd 通道 + risk_level 原子量。共享 DB writer 通道。
**文件**：main.rs（+120/-50）、instrument_info.rs（parking_lot）、scanner/runner.rs（parking_lot）、database/mod.rs（pool max）、event_consumer/types.rs（Arc<PriceEvent>）、order_manager.rs（test fix）、tick_pipeline.rs（+2 fan-out tests）、Cargo.toml×2（parking_lot dep）。
**測試**：898 lib + 18 e2e pass（+2 新 fan-out tests）。

### system_mode GUI→Rust 同步 + 3E-ARCH 計劃 + GridTrading multi-symbol（2026-04-11）

**system_mode 同步**（6 文件實現）：
- `tick_pipeline.rs`：新增 `SystemMode` 枚舉（live_reserved/demo_reserved/shadow_only/observe_only/design_only），`system_mode` 字段，on_tick gate，`set_system_mode()` 方法（自動平倉 + 暫停 paper）
- `pipeline_types.rs`：`PipelineSnapshot` 新增 `system_mode: String`
- `event_consumer/handlers.rs`：`SetSystemMode` handler arm
- `ipc_server.rs`：`set_system_mode` IPC 命令，`get_state` 改從快照讀 system_mode（移除硬編碼 "demo_only"）
- `ipc_client.py`：`sync_ipc_call()` 同步 IPC 輔助函數
- `control_ops.py`：`apply_config_change` 後 push system_mode 到 Rust（盡力而為）
- `live_session_routes.py`：session status 新增 `system_mode` 字段

**GridTrading multi-symbol 修復**（pre-existing 未修復項）：
- 新增 `template_bounds: Option<(f64, f64)>` 字段，3 個構造函數補齊
- 2 個測試適配 HashMap 索引（lines 1053-1055, 1071）

**3E-ARCH 計劃文件**：
- `docs/references/2026-04-11--three_engine_parallel_arch_plan.md`（PM+PA+FA 三角色分析）
- TODO.md 更新：3E-ARCH 段落 + W22 排期 + 關鍵路徑

**測試基線**：engine lib 879 + e2e 18 + Python 2792 / 0 fail

### Multi-Symbol Position Tracking Refactor（2026-04-11）

**問題**：4 策略各持單一全局 `position: Option<bool>`，理論併發上限僅 4 倉，遠低於風控 `open_positions_max=25`。

**修復**：
- MaCrossover / BbReversion / BbBreakout / GridTrading 全部改為 `HashMap<String, bool>` per-symbol 追蹤
- GridTrading `new()` / `new_geometric()` 移除硬編碼 `"BTC"` key + 預填 grid，改為 `template_bounds` 延遲初始化
- `on_tick` 首次收到 symbol 時：有 template_bounds 用模板邊界，否則 ±10% adaptive
- 生產路徑 `new_adaptive()` 行為不變
- 7 個測試適配延遲初始化

**容量**：理論上限 4 → 100（4 策略 × 25 symbols），實際受風控 `open_positions_max` / `max_same_direction` 約束。

**測試基線**：engine lib 879 + e2e 18 / 0 fail

---

### W21 6-04~08 Phase 6 驗收（2026-04-11）

**6-04 集成測試**（reconciler_e2e.rs +11 場景，7→18）：
- S7: MinorDrift 不重設 clean cycle 計數器（對比 MajorDrift 重設）
- S8: SideFlip → Cautious（完整 handler 鏈路）
- S9: Ghost → Cautious（完整 handler 鏈路，E2 P0 fix）
- S10: Per-symbol 30min 冷卻阻止重複升級
- S11: 全局 5min 冷卻限制快速連續升級（含過期後放行）
- S12: 多級恢復全程 Defensive → Reduced → Cautious → Normal
- S13: REST 失敗漸進三階段（10→Cautious / 30→Reduced / 60→Defensive / 已達目標→跳過）
- S14: Floor rule 阻止恢復低於 pre_escalation_level（原 scenario 7 重編號）

**6-05 壓測**：
- Rust S1: 100 cycle 快速漂移/清除交替 — 狀態一致，max Cautious
- Rust S2: 50 symbols 同時漂移 → CB + CloseAll
- Rust S3: 20 輪 handler 快速升降 — 無死鎖
- Rust S4: 1000 次 evaluate_actions 性能 < 100ms
- Python 5 場景：10 線程並發 register/promote（==1 成功）/冪等/100 策略批量 <1s/並發 metrics

**6-06 sync_commit 驗證 PASS**：
- global `ALTER DATABASE SET synchronous_commit = 'on'`（V006:90）已保護 orders/fills
- MIT/CC/FA 三方確認：per-session 分層優化歸 WP Backlog（當前安全方向偏保守正確）

**6-07~08 EvolutionEngine**：
- 保留（不 deprecate）— 用於 DL/AI agent 學習
- EvolutionEngine = 參數網格搜索優化，PromotionPipeline = 策略生命週期管理，職能不重疊

**6-RC-6 TODO 一致性修復**：6-RC 段標記與 W19 段對齊（`[x]`）

**E2 修復 3 項**：
- P0: Ghost scenario 補完整 handler 鏈路驗證
- P1: Python 並發 promote 斷言從 `>= 1` 改 `== 1`（防漏 lock bug）
- P1: Rust make_writer() temp 路徑加 thread id 防並行碰撞

**測試基線**：engine lib 879 + e2e 18 / Python 2792 / 0 fail

### W20 安全審查 + 漸進放權 + CC 合規（2026-04-10）

**SEC-04/06/13 + G-9 E3 深度審查**
- SEC-04（SQL injection）：全 parameterized queries，PASS
- SEC-06（token in JSON）：已修復為 HttpOnly cookie，PASS
- SEC-13（u32 truncation）：已修復為 saturating cast，PASS
- G-9（HMAC dead import）：NOT dead — `hmac.compare_digest()` 用於 auth token 驗證（L171），PASS

**WP-CC/P9 — 交易所雙軌止損接線（原則 #9）**
- `event_consumer/mod.rs`：StopRequest channel consumer 從 log-only 升級為調用 `PositionManager.set_trading_stop()`
- Paper 模式無 client 時優雅跳過；Demo/Live 調用 Bybit `POST /v5/position/trading-stop`
- Fail-closed：API 失敗時 warn 但本地 StopManager 繼續保護

**WP-CC/FS-1 — market_data_client tests 提取**
- `market_data_client/mod.rs` 從 1083→742 行（低於 800 警告線）
- 18 tests 提取至獨立 `tests.rs`，全部通過

**WP-CC/BI-1 — MODULE_NOTE 雙語補全**
- 12 個 Rust 文件補全 MODULE_NOTE（EN+中文）header

**WP-CC/SM-1 — Singleton 合規確認**
- 審計確認無未登記 singleton

**6-01~03 — 策略漸進放權管線**
- 新增 `promotion_pipeline.py`（~640 行）：PromotionGate class
  - 5 階段：LEARNING → PAPER_SHADOW → DEMO_ACTIVE → LIVE_PENDING → LIVE_ACTIVE
  - Paper 畢業門檻：14d + 100 trades + PnL≥0% + DD<10% + Sharpe>0.5
  - Demo 畢業門檻：21d + 200 trades + DD<8% + Sharpe>0.8 + slippage<15bps + reliability>95%
  - LIVE_ACTIVE 必須 operator 顯式審批（APPROVED/REJECTED/EXTEND）
  - Thread-safe（Lock）+ audit callback + DB 序列化 round-trip
- 3 API endpoints 加入 `governance_routes.py`：
  - `GET /promotion-pipeline/status` — 查詢管線狀態
  - `POST /promotion-pipeline/promote` — 晉升（含畢業門檻預檢）
  - `POST /promotion-pipeline/operator-decision` — Operator 審批
- 27 tests（5 classes：StateMachine/GraduationGates/LiveApproval/Audit/Serialization）

**E2 審查修復**
- P1：`register_strategy()` 返回 copy 而非 mutable ref
- P1：JSON API endpoints 不對 lookup key 做 html.escape（避免 key 不匹配）
- P1：lazy singleton 加 threading.Lock 修復 TOCTOU race
- P2：capital_pct/max_leverage 加類型+範圍驗證

**測試基準線**：Rust engine lib 879 / Python 2787 passed / 0 fail

### W19 安全補強：G-3 IPC 認證 + OC-3/6-RC-6 告警（2026-04-10 · commit W19）

**G-3 / SEC-08 — IPC HMAC-SHA256 認證**
- Rust `ipc_server.rs`：新增 `verify_ipc_token()`（常數時間 `mac.verify_slice`）+ `handle_connection()` auth 區塊：`OPENCLAW_IPC_SECRET` 存在時第一條消息必須是 `__auth` JSON-RPC；時間戳 ±30s 防重放；所有失敗路徑立即斷開
- Python `ipc_client.py`：新增 `_authenticate()` 方法；`import hmac as _hmac_lib` + `hashlib`；`_try_connect()` 在 `_connected=True` 後調用；auth 失敗 fail-closed（關閉連接 + return False）；無 env var 時跳過（向後兼容）
- Python `ipc_client.py`：新增 `get_risk_runtime_status()` 方法（OC-3 輪詢基礎）

**G-5 — API Rate Limiting 全局覆蓋驗證**
- 確認 `main_legacy.py:304-307` `default_limits=[120/min]` + `SlowAPIMiddleware` 已覆蓋全部 214 路由
- Gap 審計誤判（PA 以為只有 3 個路由有 decorator，實際 default_limits 已全局生效）
- Login 端點保留更嚴格的 5/min decorator

**OC-3 + 6-RC-6 — Reconciler governor tier 分級告警**
- `paper_trading_wiring.py`：新增 `reconciler_alert_monitor()` 協程 + 加入 `__all__`
  - 每 30s 輪詢 `get_risk_runtime_status` IPC
  - CIRCUIT_BREAKER / MANUAL_REVIEW → 🛑 P0 alert
  - CAUTIOUS / REDUCED / DEFENSIVE → ⚠️ P1 alert
  - NORMAL 恢復 → ✅ INFO
  - 使用 `asyncio.to_thread` 包裹同步 `ALERT_ROUTER.alert_system`（避免阻塞事件循環）
  - `prev_tier=None` 初始化跳過啟動虛假告警
- `main.py`：startup handler 以 `asyncio.create_task()` 啟動監控（fail-open，不阻斷啟動）

**測試結果**：Rust 879 passed · Python 2760 passed (0 fail · 5 skipped)

### 全系統審計 + Gap 計劃（2026-04-10 · PM/PA/FA/CC）

**背景**：PM/PA/FA/CC 四角色對 Rust engine + Python 控制層 + ML pipeline 進行嚴格完成度審計，發現文檔宣稱「~100%」但實際完成度 72-75%。

**關鍵發現**：
- H1-H5 AI 治理層 5 個 agent handler 全為 stub（ai_service.py），AI 判決層無效
- FundingArb.on_tick() 永遠返回 vec![]（第 5 個策略不產生信號）
- API 203 個路由無全局 Rate Limiting
- HMAC dead import、Calibration.py 骨架
- 以上均未出現在原 TODO.md

**動作**：10 個 gap（G-1~G-10）全部入 TODO.md Gap 索引，排入 W19~W23；CLAUDE.md §十更新排期；最早 Live 日期修正為 W23 末（2026-05-16）。

---

### DB Fresh-Start Reset（2026-04-10 · commit 3acb9cc）

**背景**：開發過程中積累了大量噪音數據（52.9M signals、18.3M decision_context_snapshots、3.6K fills 等），PH5-VERIFY-1 觀察期需要乾淨數據基準。

**執行**：`helper_scripts/db/fresh_start_reset.py --execute` — 71,298,138 行開發噪音清除，耗時 <2s（TimescaleDB chunk drop）。

**保留**：所有 `market.*` 表（klines 44K / market_tickers 1.4M / ob_snapshots / funding_rates 等）完整保留。

**影響**：
- PH5-VERIFY-1 觀察期從 2026-04-10 重新起算（原計劃 2026-04-11 `--days 3` → 改為 `--days 2`）
- JS-1 滾動重跑排程：2026-04-11 `--days 2` → 04-12 `--days 3` → 04-17 `--days 7` → 每週滾動

---

### Python OMS 刪除 + Rust DB 訂單/裁決寫入（2026-04-10 · commit 4cab87c）

**Track A — Rust DB writers**: `TradingMsg::Order` + `OrderStateChange` + `RiskVerdict` 三 variant 加入 `database/mod.rs`；`trading_writer.rs` 新增 `flush_orders` / `flush_order_state_changes` / `flush_verdicts`（INSERT 至 `trading.orders` + `order_state_changes` + `risk_verdicts`）；`event_consumer/mod.rs` 在 pending_reg / Fill / Cancelled / Rejected 四點 emit DB 寫入；`tick_pipeline.rs` 三點 emit RiskVerdict。

**Track B — Python OMS 刪除**: `oms_state_machine.py`（693行）+ `test_oms_state_machine.py`（449行）刪除；`governance_hub.py` 移除 `set_oms_sm` / `get_oms_orders` / `_handle_oms_reconciliation` + OMS reconciliation trigger；`governance_routes.py` GET /oms/orders → stub 空列表 + 遷移說明；`paper_trading_wiring.py` 移除 OMS TTL auto-cancel；`conftest.py` 移除 OMS fixtures + helper；tests 更新。

**結果**: Rust 872 lib tests ✅ / Python 2372 passed / 1 pre-existing fail。

---

### Phase 6: 6-RC-7 e2e 集成測試 + 6-RC-8 Live Blocker 解除（2026-04-10）

**6-RC-7**: `tests/reconciler_e2e.rs` — 7 個端到端場景：(1) MajorDrift→Cautious full chain (2) persistent 3 cycles→Defensive (3) burst 5+→CB+CloseAll (4) recovery Cautious→Normal (clean cycles + wall-clock) (5) CB de-escalation blocked (6) REST failure streak→Cautious (7) floor rule prevents over-recovery。`event_consumer::handlers` 模組升為 pub 供集成測試驅動。`TickPipeline::trading_mode` 升為 `pub(crate)` 修復跨模組訪問。

**6-RC-8**: Reconciler 自動降級功能完整（6-RC-1~5,7,9,10），不再構成 Live 隱含阻塞。唯一排除項：6-RC-6（多通道告警，阻塞 OC-3）。

---

### DEAD-PY-2 大型 Python 死代碼清除（2026-04-10 · commit TBD）

~4500 行 Python 死代碼刪除。Python 層完全無交易邏輯。

**Phase A — PipelineBridge 全刪**：`bridge_core.py`（807）/ `bridge_agents.py`（928）/ `bridge_stats.py`（825）/ `pipeline_bridge.py`（807）全刪。`strategy_wiring.py` 移除全部 Bridge wiring；`paper_trading_wiring.py` / `governance_routes.py` / `main.py` 清理所有引用。`main.py` 移除 SymbolCategoryRegistry→PipelineBridge 背景初始化塊。

**Phase B — Python 策略類全刪**：`strategies/{ma_crossover,bollinger_reversion,funding_rate_arb,grid_trading,bb_breakout}.py` 全刪。`strategy_auto_deployer._deploy_strategy()` stubbed to no-op（DEPRECATED R-07）。

**Phase C — ProtectiveOrderManager 全刪**：`protective_order_manager.py` 刪除。`paper_trading_wiring.py` `PROTECTIVE_ORDER_MANAGER = None`。

**Phase D — BybitDemoConnector 瘦身**：763→~95 行。刪除全部交易方法（BybitDemoConnector 類本身），僅保留 `round_qty_for_exchange()` + `round_price_for_exchange()` 兩個純工具函數。

**Phase E — Tests 清理**：11 個死 test 文件完全刪除（~7000 行）；10+ 個 test 文件外科手術刪除 dead class/method；startup integrity + strategy routes 更新適配 DEAD-PY-2。

**E4**：872 Rust lib + 2427 Python passed（1 pre-existing fail）。

### Phase 6: Reconciler Auto-Contraction（自動降級）（2026-04-10）

**6-RC-1~5,9,10 complete** — Position Reconciler 從 AUDIT-ONLY 升級為自動動作層：漂移→風控收緊（降級）→引擎行為限制→漂移消失→自動恢復。

**risk_gov.rs**：+`RiskInitiator::Reconciler` + `RiskEvent::ReconcilerDrift/RestFailure/Recovery` + `reconciler_escalate_to()`/`reconciler_de_escalate_to()` 便捷方法 + transition rules（CB/MR 不可自動恢復）。+5 tests。

**position_reconciler.rs**：`ReconcilerState`（drift_streak/clean_cycles/cooldowns/pre_escalation_level） + `ReconcilerAction` enum（Escalate/DeEscalate/CloseAll） + `evaluate_actions()` pure function：≥5 burst→CB+CloseAll / persistent ≥3 cycles→Defensive / single→Cautious + per-symbol 30min + global 5min cooldown + hybrid recovery（clean cycles + wall-clock）。`filter_dust()` 6-RC-5（1.5×minQty）。Staleness 6-RC-9（>10min→reseed）。REST failure 6-RC-10（≥10→Cautious）。+17 tests。

**tick_pipeline.rs**：+`ReconcilerEscalate`/`ReconcilerDeEscalate` PaperSessionCommand variants。

**handlers.rs**：+2 command handlers（parse tier → reconciler_escalate/de_escalate → force snapshot）。

**main.rs**：`Arc<AtomicU8>` shared_risk_level 接線：main.rs 創建 → event_consumer 每次 handle_paper_command 後寫入 → reconciler 閉包讀取。

**event_consumer/types.rs + mod.rs**：`shared_risk_level: Option<Arc<AtomicU8>>` 加入 EventConsumerDeps。

**tests**：872 engine lib + 365 core = 1237 all pass（+27 new: 17 reconciler + 5 risk_gov + 5 handler）。

**觸發矩陣**：MinorDrift→no action / MajorDrift/Orphan/Ghost/SideFlip→Cautious / persistent ≥3→Defensive / burst ≥5→CB+CloseAll / REST fail ≥10→Cautious。

**恢復矩陣**：Cautious→Normal: 30 cycles+15min / Reduced→Cautious: 20+10min / Defensive→Reduced: 20+10min / CB/MR: operator only。MinorDrift 不重設 clean cycle。Floor rule：不低於 pre_escalation_level。

**排除**：6-RC-6（多通道告警，阻塞 OC-3）、6-RC-7（e2e 整合測試）、6-RC-8（live blocker）。

---

### Signal Diamond Phase 3+4 Fix Round — Mode Switch + IPC Commands（2026-04-10）

**P0: `set_trading_mode()` state swap** — 替換原 2 行 setter 為完整雙向 `std::mem::swap` 實現：`sync_direct_to_mode_state(old)` 保存舊模式 → `load_mode_state_to_direct(new)` 載入新模式。切換 paper↔demo↔live 時保留各自的 PaperState/IntentProcessor/GovernanceCore/consecutive_losses/session_halted/pending_close。同模式切換為 no-op。新模式自動 `add_mode()` 以當前餘額初始化。

**P2: PaperSessionCommand 擴展** — 新增 `AddMode { mode, balance, response_tx }` 和 `SwitchMode { mode, response_tx }` variants。`event_consumer/handlers.rs` 完整處理：pipeline 操作 + force snapshot write + oneshot response。`ipc_server.rs` 註冊 `add_engine_mode` / `switch_engine_mode` RPC（嚴格 enum match，3s timeout）。

**P3: Python IPC 層** — `ipc_client.py` `get_paper_state(mode=)` 傳遞 `{"engine": mode}` 參數；新增 `get_mode_snapshot()` / `get_active_modes()`。`ipc_state_reader.py` mode-aware lookup + `_MODE_ALIASES` fallback（"paper"↔"paper_only"）。`live_session_routes.py` 所有 IPC call 帶 `{"engine": "live"}`。

**P1 架構決策** — 同時多模式 on_tick 需 per-mode 策略實例（grid/bb_breakout 有內部狀態如 net_inventory）。當前架構支持模式**切換**（state preservation），真正同時執行為 Phase 5+ 工作。

**ModeStateSnapshot** — `mode_state.rs` 新增 IPC 序列化結構體。`PipelineSnapshot.mode_snapshots: HashMap<String, ModeStateSnapshot>` 對主模式讀 direct fields、次模式讀 mode_states。`TradingMode` 加 `Hash` derive。

**測試** — +5 新測試（preserve state / same-mode noop / add_mode+snapshot / pipeline_snapshot / consecutive_losses roundtrip）。**E2 PASS WITH WARNINGS**（僅 file size pre-existing）。**E4: 850 Rust lib / 3 integration / 2692 Python pass, 1 pre-existing fail**。

### SM-1 live 授權統一 + Governance 修復（2026-04-10 · commits 4815386 / 435e613）

**問題 1 — max_position_usd 硬編碼**：`governance_hub.grant_paper_authorization()` scope 中 `max_position_usd: 10000` 為字面量。修復：新增 `max_position_usd: float = 10_000.0` 參數；`post_session_reauth` 改 async，IPC 讀取 Rust `RiskConfig.limits.max_order_notional_usdt`，>0 時覆蓋預設值。

**問題 2 — SM-1 live 授權從未 ACTIVE**：`_submit_live_governance_request()` 只走到 PENDING_APPROVAL，Operator role + live_reserved 雙重門控從未完成 SM-1 批准。修復：(a) `_submit_live_governance_request()` 在 `submit_for_approval` 後立即 `approve()`，使 live auth DRAFT→PENDING→ACTIVE，並 invalidate HUB cache；(b) 新增 `_revoke_live_governance_auth()` — 撤銷所有 mode=live 的 SM-1 auth（ACTIVE/RESTRICTED/PENDING/DRAFT → REVOKED）；(c) `grant_execution_authority()` 同步調用 `_submit_live_governance_request()`；(d) `revoke_execution_authority()` + `post_live_session_stop()` 同步調用 `_revoke_live_governance_auth()`；(e) `governance_hub.get_status()` 多授權並存時優先顯示 `mode=live` 授權。

**效果**：live session start → 治理中心顯示 `mode: live / execution: live_submit / approved_by: <actor>`；stop/revoke → 恢復 `paper only`（若 paper auth 仍有效）；drawdown halt → FROZEN（不變）。2676 Python tests pass。

### Live/Demo GUI 平倉按鈕 + Sidebar mode 修復（2026-04-10 · commits c370cd1 / bfc3cea / 81a0acb）

**Sidebar 修復**：`console.html refreshSidebar()` 改用 `/api/v1/live/session/status` 替代 `governance/status`，正確讀取 `trading_mode` / `execution_authority` / `session.session_state`；live 且 granted 時顯示紫色 mode + `auth: granted`，否則顯示 `Live_Ready`。

**後端新端點**：(a) `POST /api/v1/live/positions/{symbol}/close` — IPC `close_position`，Operator role，session 繼續；(b) `POST /api/v1/live/close-all-positions` — IPC `close_all_positions`，session 繼續；(c) `POST /api/v1/strategy/demo/positions/{symbol}/close` — PyO3 `get_positions` 查 qty/side → `place_order reduce_only=True`；(d) `POST /api/v1/strategy/demo/close-all-positions` — `_close_all_demo_positions()`。

**前端**：live/demo 持倉表各行末尾加「平倉」按鈕（confirm dialog + `ocPost`）；Positions section header 加「全部平倉」按鈕；移除 control bar 原有重複「關閉所有倉位」按鈕；paper tab 同步加「全部平倉」；`_normalize_execution()` 處理 Rust snake_case→Bybit camelCase（execQty/execPrice/execFee）。2280 Python tests pass。

### Signal Diamond Multi-Engine Data Separation — Phase 1-4 Complete（2026-04-10）

**Phase 1: V015 Migration** — `sql/migrations/V015__engine_mode_separation.sql` adds `engine_mode TEXT NOT NULL DEFAULT 'paper'` to 8 trading tables + nullable on `agent.ai_invocations`. Indexes `(engine_mode, ts DESC)`. `trading.signals` untouched (shared). DEPRECATED comments on `is_paper` columns.

**Phase 2a: Rust DB Writers** — `TradingMsg::Intent/Fill/PositionSnapshot` + `DecisionContextMsg` gain `engine_mode: String`. `trading_writer.rs` flush functions write `engine_mode` column; `is_paper` derived as `engine_mode != "live"` (backward-compat Grafana). `context_writer.rs` flush adds `$26 = engine_mode`. `TradingMode::db_mode()` canonical mapping: PaperOnly→"paper", Demo→"demo", Live→"live".

**Phase 3: ModeState Extraction** — New `mode_state.rs`: `ModeState` struct (PaperState + IntentProcessor + GovernanceCore + risk_store + ring buffers + consecutive_losses + session/pause flags + pending_close + exchange_seq) + `ModeStateSnapshot` for IPC. `TickPipeline` gains `mode_states: HashMap<TradingMode, ModeState>` + `active_modes: Vec<TradingMode>`. Primary mode bridge: `mode_snapshot()` reads from direct fields for primary mode, ModeState for secondary. `PipelineSnapshot.mode_snapshots` added. `TradingMode` gets `Hash` derive.

**Phase 4: IPC + Python** — Rust `ipc_server.rs`: `get_paper_state` accepts optional `engine` param (default "paper"); new `get_mode_snapshot` and `get_active_modes` methods. Python `ipc_state_reader.py`: `get_paper_state(mode=)` with `mode_snapshots` lookup + alias handling; new `get_mode_snapshot()`, `get_active_modes()`, mode-aware `get_recent_intents/fills()`. `live_session_routes.py`: all IPC calls pass `{"engine": "live"}`.

845 Rust lib tests pass. 2692 Python tests pass (1 pre-existing fail).

### Live-Demo 槽位 + Live/Paper Metrics 修復 + DB Signal Diamond 規劃（2026-04-10 · commit 25b5d73）

**`settings_routes.py`**：新增 `live_demo` 虛擬槽位（validate via demo server → 寫入 live path；operator 可用 Demo 帳號完整測試 live 路徑，換 key 時零代碼改動）。**`tab-settings.html`**：3 API key 卡片（Demo / Live-Demo / Live）+ peek 遮罩按鈕 + dialog overlay CSS 修復 + 槽位上下文警示。**`live_session_routes.py`**：新增 `GET /api/v1/live/metrics` 端點。**`paper_trading_routes.py`**：`/metrics` 端點修復（呼叫 `compute_full_metrics()`，返回完整 trade_metrics / drawdown_metrics / holding_period_metrics / sharpe_ratio，修復所有指標顯示 "--"）。**`tab-live.html`**：Performance Metrics 區塊（10 個指標卡，30s 刷新）。**`DB_TODO.md`**（新文件）：Signal Diamond 多引擎數據隔離規劃（5 階段實施）。840 Rust lib tests pass。

### Live 縮倉監控 + OPENCLAW_ALLOW_MAINNET 鎖移除（2026-04-10 · commit 25b5d73）

**Rust `bybit_rest_client.rs`**：移除 `OPENCLAW_ALLOW_MAINNET=1` env var guard（9 行），保留主網 warn 日誌；更新 `config/mod.rs` TradingMode::Live docstring + `main.rs` 注釋。840 Rust lib tests pass。

**`live_session_routes.py`**：新增 `_live_contraction_monitor()` async 後台 task — 每 5 分鐘輪詢引擎 `peak_balance + bybit_sync_balance/balance`，計算 session 回撤；`CONTRACTION_WARN_PCT=5.0%` → 警告日誌；`CONTRACTION_HALT_PCT=15.0%` → 撤銷 `execution_authority` + `close_all_positions` IPC + `_freeze_live_governance_auth()`；新增 `_freeze_live_governance_auth()` 凍結 GovernanceHub 中 mode=live 授權（審計留痕）；`post_live_session_start` 啟動 monitor task + 初始化 `_live_contraction_state="normal"`；`post_live_session_stop` 取消 task + 重置狀態；`post_live_session_resume` 重啟 monitor task；`get_live_session_status` 加入 `contraction{}` 字段（state/warn_pct/halt_pct/drawdown_pct/peak_balance/current_balance）。

**`tab-live.html`**：控制欄新增 `#live-contraction-badge`：normal 時隱藏；warned 時顯示黃色警告 + 回撤 %；halted 時顯示紅色 + 禁用 Start 按鈕。

### Gov-P1 + Live_Ready 全阻隔移除（2026-04-10 · commit 045e79c）

**`live_session_routes.py`**：`post_live_session_start` 自動授予 `execution_authority = "granted"`（雙重門控 Operator 角色 + live_reserved 已足夠，不再需要額外 grant 步驟）；`post_live_session_stop` 重置 `_EXECUTION_AUTHORITY_OVERRIDE = None`（fail-closed）；`post_live_session_resume` 移除舊 execution_authority 硬鎖，改為 global_mode 二次確認 + 重授；新增 `_submit_live_governance_request()` — live session start 時向 GovernanceHub 提交 PENDING 授權申請（非阻塞，審計留痕，Operator 可在治理頁確認）。

**`tab-live.html`**：`checkLiveEngineStatus()` detail 行邏輯修改 — active 時顯示 `mode | authority`，idle 時只顯示 `mode`（消除 `authority: not_granted` 噪音）。

**`CLAUDE.md`**：§四 `execution_authority = "auto_granted_on_start"` + 硬錯誤清單更新；§三 Runtime 狀態更新為 Live_Ready ✅ 全阻隔已移除；§十一 一句話更新。

**测试**：840 Rust lib pass · 2280 Python pass · 1 pre-existing fail 不變。

### Live GUI Phase 5 — 紫色主題 + 擴展儀表板 + Global Mode Gate（2026-04-10 · commit c392220）

**tab-live.html**：CSS 全面紅→紫（warn-bar/control-bar/accent borders → rgba(168,85,247,..)）；Account Balance 卡片組（total equity / available / wallet balance / margin used = equity - available）；PnL Overview 卡片組（unrealized large + realized from cumRealisedPnl sum + net PnL）；持倉表新增 Leverage 列；成交記錄折疊區（懶加載 `/api/v1/live/fills`，展開時觸發）；active badge `oc-chip-bad` → `oc-chip-live`；緊急停止按鈕保持紅色。

**tab-system.html**：`live_reserved` 按鈕邊框/圖標 🔴→🟣 + 紫色；`updateModeBtns` chip `oc-chip-bad`→`oc-chip-live`；MODE_CONFIRM warn-box 紅→紫；loadOverview metric class `red`→`purple`（新增 `.purple { color: #a855f7 }` CSS class）；模式升级路径顏色紅→紫。

**live_session_routes.py**：`_get_global_mode_state()` 讀 STORE `global_runtime.derived.global_mode_state`；`post_live_session_start` 新增 409 gate（global mode 必須含 'live'）；`GET /api/v1/live/fills` 新端點（PyO3 `get_executions` + fallback）。

**common.js**：`oc-chip-live` 紫色 chip CSS class（rgba(168,85,247,..)）。

**console.html**：live mode mc-val 顏色改為 `#a855f7` inline style；BUILD_TS → `20260410.live-ui-v2`。

### Live GUI Phase 4 — 授權 gate + PyO3 真實數據 + _ipc_command 修復（2026-04-10 · commit af392c2）

**live_session_routes.py**：`_EXECUTION_AUTHORITY_OVERRIDE` 記憶體覆蓋（重啟清空 fail-closed）；`_get_execution_authority()` 先查 override 再走 governance；`_ipc_command()` 3 bug 修復（錯誤 import / 未 connect / 未 disconnect）；`_get_rust_client_safe()` helper；`POST /api/v1/live/execution-authority/grant` + `/revoke`（operator-only）；live session start 接受 `demo` mode（demo key 測試）；`GET /api/v1/live/balance|positions|orders` 改為 PyO3 BybitClient 優先（真實帳戶數據），IPC 降級。

**tab-live.html**：lock screen 加「Grant Execution Authority」按鈕；dashboard 加「撤銷授權」按鈕；`grantLiveAuthority()` / `revokeLiveAuthority()` JS；balance 解析支援 PyO3 snake_case + Bybit camelCase 雙格式 + unrealized PnL；positions 移除 `p.position` 嵌套（Bybit 扁平格式）；orders 使用真實 Bybit 欄位（orderId/price/orderType/orderStatus）。

E4：840 Rust + 2280 Python passed，1 pre-existing fail。

### Live_Ready 狀態切換 + live 端點上線（2026-04-10 · commit 09a5d02）

CLAUDE.md §四 hard limits 更新：移除 `system_mode=demo_only` / `execution_state=disabled` 硬限制。新 Live 技術門控：OPENCLAW_ALLOW_MAINNET=1 + live API keys + execution_authority=granted（三條件全滿足才真實接入主網）。

新增 3 個實盤端點（`live_session_routes.py`）：`GET /api/v1/live/balance` / `/live/positions` / `/live/orders`，全部走 IPC `get_paper_state`，引擎不可用時優雅降級。

`tab-live.html`：`loadDashboardData()` 呼叫 live 端點（非 demo）；訂單表完整接線（原 LIVE-P1-3 stub）；phase badge 更新為 "✅ Live_Ready"。

`main.rs` 啟動 banner：`demo_only | Execution: disabled` → `Live_Ready | Execution: operator-gated`。

---

### L3 嚴格審計 + 2 bug 修復（2026-04-10 · commit ed26346）

4 路並行 agent 審計 LIVE-P0/P1/P2 所有層次：Rust ipc_server/main、Python risk_routes/live_session、GUI tab-risk/live/settings、LIVE-P1 Rust TradingMode。

**CRITICAL: live_session_routes._ipc_command() 三重斷線**（Python C-1/C-2/C-3）— 原碼 import `get_ipc_client`（不存在）、從未 connect()、從未 disconnect()；所有 live session 端點靜默返回 HTTP 503。修復：EngineIPCClient + connect/call/finally disconnect（同 paper_trading_routes 模式）。

**C2: in-tp-enabled checkbox dirty-tracking 缺失**（GUI）— checkbox 用 change 事件但不在 _RISK_INPUT_IDS forEach 裡；修復：加獨立 change 監聽器。

已驗證乾淨：Rust TradingMode match 窮舉、OPENCLAW_ALLOW_MAINNET 硬鎖、key slot routing、per-engine whitelist、p1_risk_pct 轉換。已確認設計決策（非 bug）：TOML 無磁盤 hot-reload、risk_store 啟動鎖定、tab-live stub 前置條件、execution_authority Python-only guard。

E4：840 Rust lib / 2280 Python + 1 pre-existing fail — 無回歸。

---

### LIVE-P2-1/P2-2/P2-3 per-engine RiskConfig separation（2026-04-10 · commit 006d905）

**LIVE-P2-1 Rust PerEngineRiskStores**:
- New `PerEngineRiskStores` struct bundles 3 `Arc<ConfigStore<RiskConfig>>` (paper/demo/live); replaces single Optional field
- `IpcServer.risk_stores: Option<PerEngineRiskStores>`; `set_config_stores()` takes full struct
- IPC `get_risk_config`/`patch_risk_config` accept optional `engine` param, route to correct store (default paper fail-safe)
- `main.rs`: `load_unified_configs()` loads 3 TOML files with env var overrides; legacy fallback `risk_config.toml` → paper if `risk_config_paper.toml` absent
- `async_main()` selects correct store by `TradingMode` for `EventConsumerDeps.risk_store`
- New TOML: `risk_config_paper.toml`, `risk_config_demo.toml` (same as paper); `risk_config_live.toml` (conservative: leverage 10x, position 5%, drawdown 5%, daily_loss 3%)

**LIVE-P2-2 GUI per-engine tab**:
- `tab-risk.html`: engine selector card (Paper/Demo/Live); live warning banner; confirmation modal before live saves
- `_selectedRiskEngine` state; `loadRiskConfigForEngine()` calls new per-engine endpoint; `_engineSaveUrl()` routes saves; `_wrapLiveSave()` intercepts live saves

**Python per-engine endpoints** (`risk_routes.py`):
- `GET /api/v1/paper/risk/config/engine/{engine}` — direct IPC, bypasses RiskViewClient version tracking
- `POST /api/v1/paper/risk/config/engine/{engine}/global` — direct IPC patch with engine routing
- `_ALLOWED_ENGINES` whitelist prevents path injection

**E2+E4**: zero review issues; 840 Rust lib tests / 2280 Python + 1 pre-existing fail pass.

---

### SEC-05 innerHTML XSS + WP-F/AH-06 risk-tab dirty-tracking（2026-04-10 · commits 19b40dc + b7b7651）

**SEC-05 innerHTML XSS remediation** across GUI:
- `app.js`: `safeText()` now delegates to `ocEsc()` (covers ~20+ call sites at once); 15+ individual `ocEsc()` wraps for paper positions/orders/fills, market feed, learning feed, cost breakdown, risk envelope
- `app.js` supplement (b7b7651): 4 badge/label function fallbacks escaped — `confidenceBadge`, `statusBadge`, `reviewStatusBadge`, `reviewTypeLabel`
- `cards/linucb_card.html`: `ocEsc()` on regime names, arm_id, shadow champion/challenger/decision
- `tab-ai.html`: `ocEsc()` on Kelly strategy keys and tier labels
- Remaining files (tab-governance, tab-settings, tab-system, tab-live, console) audited — already properly escaped or use hardcoded data only

**WP-F/AH-06 risk-tab form overwrite fix**:
- `tab-risk.html`: `_riskFormDirty` flag set on any input event across 16 risk form fields
- `loadRiskConfig()` skips populating inputs when dirty flag is true
- Flag cleared after successful save in all 3 save functions
- Replaces inadequate `document.activeElement` guard that only protected focused element

### A2 NewsPipeline Scheduler + DEAD-PY-1 Complete + 1C-4 Close（2026-04-10）

**A2 NewsPipeline 60s scheduler** wired into `main.rs`:
- 3 providers: CryptoPanic (free tier, 28min self-throttle) + CoinTelegraph RSS + Google News RSS
- 4-09 triple-route NewsRouter: Guardian halt check + regime buffer + learning context sink
- Gated by `LearningConfig.switches.news_pipeline_enabled` (hot-reloadable via ConfigStore)
- Follows existing fee_rate/instrument refresh tokio::spawn pattern with cancel token
- ~95 lines added to `main.rs`

**DEAD-PY-1 whitelist UI removal** (WP-CLEANUP-WHITELIST-UI):
- `tab-governance.html`: removed HTML card + modal + CSS + JS vars/functions + init + explainers (−220 lines)
- `governance.js`: removed 3 dead API wrapper functions (−19 lines)
- All whitelist references eliminated; backend already returns HTTP 410 Gone

**1C-4 final verification**: E2 code review + E4 regression (838 Rust lib / 2692 Python passed / 1 pre-existing fail) + doc sync

### LIVE-P0-1/P0-2/P0-3 — API key mgmt + live page rewrite（2026-04-10 · commit c680ffd）

- `settings_routes.py` (new): GET/POST /api/v1/settings/api-key/{slot}  
  Slot whitelist → HMAC validation → write + chmod 600 → masked hint only  
- `main.py`: registered settings_router  
- `tab-settings.html`: API key management card for demo/live slots  
- `tab-live.html`: full rewrite — dynamic prereq checklist (10 checks, live API queries) + dashboard framework (lock overlay / unlocked with PnL metrics / positions table / emergency stop)  
- Tests: 2692 passed / 1 pre-existing fail (unchanged)

### ML Pipeline Audit Gap Fixes（2026-04-10）

Cold audit of all ML_TODO completed items found 3 real issues + 4 pre-existing test failures:

**Fixes**:
1. `cpcv_validator.py` — `model_name`/`model_version` now parameterized through `validate_cpcv()` (was hardcoded `"lightgbm_scorer"`/`"v1"`)
2. `bybit_demo_sync.py` — `_get_conn()` now prefers db_pool, fallback to direct `psycopg2.connect()`; `_release_conn()` returns to pool or closes
3. `test_phase4_routes.py` — 4 "no PG" tests now mock `db_pool.get_conn` (were broken by previous db_pool migration but not caught)
4. `test_bybit_demo_sync.py` — 2 tests updated to assert `_release_conn` instead of `conn.close`
5. ML_TODO.md archived to `docs/worklogs/2026-04-10--ml_pipeline_remediation_complete.md`, removed from root

**Test baselines**: control_api 2678 passed / 1 pre-existing fail · ml_training 135 passed / 6 skipped

---

### ML Pipeline Remediation — S0-S3+S5（2026-04-10）

基於 2026-04-09 DB R/W + ML Pipeline 全面審計完成大規模修復。

**Rust cost_gate 統一（S1）**：
- `intent_processor.rs`：5-tier slippage lookup、ATR% 正規化、win_rate 加權門檻（`fee_bps / max(0.3, wr) * 1.3`）
- `edge_estimates.rs`：`CellEstimate` struct（win_rate, n_trades, std_bps）、`get_cell()` + `load_from_str()`
- 838 lib tests pass（基準 835→838，+3 new: slippage_tier, js_win_rate, atr_pct）

**ML 推理管線（S2）**：
- `parquet_etl.py`：加時間窗口過濾 `WHERE updated_ts_ms >= start_epoch_ms`
- `label_generator.py`：修復 zero-ATR floor（`np.quantile` on empty array）+ 2 test fixes
- FeatureCollector 已接線確認（審計報告過時）

**參數優化管線（S3）**：
- `optuna_optimizer.py`：`_persist_suggestion()` → `learning.ml_parameter_suggestions`（V004 DDL 已上線）
- `cpcv_validator.py`：`_persist_cpcv_result()` → `learning.cpcv_results`
- Thompson Sampling：確認為 (A) offline 工具，`bayesian_posteriors` UPSERT 已存在

**DB 基礎設施（S5）**：
- `db_pool.py`（NEW）：`ThreadedConnectionPool`（min=2, max=10），singleton + env var 可配
- `grafana_data_writer.py` + `strategy_read_routes.py` + `phase4_routes.py`：全部委託到 db_pool
- `strategy_read_routes.py`：DB 失敗返回 HTTP 503（非 200 空數據）
- `/api/v1/health/db` endpoint：連接池統計 + SELECT 1 探測
- 2692 Python tests pass（基準 2678→2692），1 pre-existing fail · 160 ML tests pass（基準 135→160）

---

> **歸檔**：2026-04-08 ~ 04-09 條目已移至 `docs/archive/2026-04-13--changelog_archive_0408_0409.md`。
> 2026-03-30 ~ 04-07 條目見 `docs/archive/2026-04-12--changelog_archive_pre_0408.md`。

