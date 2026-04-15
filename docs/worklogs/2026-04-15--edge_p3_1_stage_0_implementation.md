# 工程日誌 — EDGE-P3-1 Stage 0 實施
# Engineering Log — EDGE-P3-1 Stage 0 Implementation

**日期**：2026-04-15
**Session**：post-compact（承接 spec v1.0→v1.3 四輪審查 session）
**Commit**：`1366054 feat(edge-p3-1): Stage 0 kickoff — spec v1.4 + V017 + entry_context_id threading`
**前置 commit**：`9141e08 docs(edge-p3-1): evolve spec v1.0→v1.3 through 3 rounds of review`
**角色**：主會話 = PM+Conductor+FA+AI-E 合一；無 sub-agent 派發（機械性實施，不需並行）
**測試基準線變更**：engine lib 1144 → 1158（+14）· core lib 372（不變）· engine e2e 35（不變）· 0 fail

---

## 1. 任務目標 / Objective

把 spec v1.3 pre-flight 發現的 5 處 spec-vs-reality 衝突落地為 v1.4，並同窗口完成 V017 migration + Rust `entry_context_id` 串接 + 回歸測試，為 EDGE-P3-1 Realized Edge Predictor 的 label 生產管線奠定資料契約。

**硬性約束**（ML-MIT + AI-E 共同警告）：V017 與 Rust 必須同窗口落地，否則新列 100% NULL，等同於被推翻的 R2 Option A 方案（silent label loss）。

## 2. 背景 / Context

EDGE-P3-1 目標是用 quantile LightGBM 預測「此筆單在當前市場條件下的實現 edge」取代 `shrunk_bps` James-Stein shrinkage。Stage 0 的交付物是把決策快照（features）與實現 fill（label）可靠 JOIN 起來的資料管線。

pre-flight 階段（2026-04-15 早會話）審查 spec v1.3 §5.1 / §7.3 / §8.8 vs 實際程式碼 / DB schema，找到 5 處會導致資料污染或 migration 失敗的衝突：

| # | 衝突 | 裁定 | 來源 |
|---|---|---|---|
| R1 | spec 要 `learning.decision_context_snapshots`，實際表在 `trading.*`（V003:40） | 用 trading.* 命名空間 | 三角色一致 |
| R2 | spec 提議復用 `trading.fills.context_id`（V003:283），但 `emit_close_fill` 在 `tick_pipeline/mod.rs:1025` 用 `make_context_id(em, symbol, ts_ms)` 合成**新的** close-time id — 復用會 100% 不匹配 | 加新列 `entry_context_id TEXT NULL` | ML-MIT + AI-E 推翻 FA 提議 |
| R3 | spec 提 `audit.events`，實際有 V014 `observability.engine_events` append-only hypertable（4 writer 已用） | 用 engine_events + event prefix | FA + AI-E |
| R4 | `ON CONFLICT (context_id) DO NOTHING` 對 hypertable 會 DDL-time 失敗 — 複合 PK 是 `(context_id, ts)` | 複合鍵 | FA |
| R5 | `disagreed BOOLEAN GENERATED ALWAYS AS (...) STORED` 在 TimescaleDB 2.x hypertable+compression 不支援 | 普通 BOOLEAN + Rust 寫入時計算 | AI-E + ML-MIT |

## 3. 實施順序 / Execution Order

Operator「開工」批准後，post-compact session 按以下順序機械式實施：

1. **Spec v1.3 → v1.4 CHANGELOG 補丁**（5 處 reality-alignment）
2. **V017 SQL migration**（新表 + ALTER + index + CHECK）
3. **Rust `PaperPosition.entry_context_id` 串接**（paper_state + emit_close_fill + 全部 Fill 發射點）
4. **整體回歸**（`cargo check` + 8+2 新回歸測試 + 全套 `cargo test`）

pre-compact 已完成步驟 1（5 處 CHANGELOG）。此 log 主要記錄步驟 2-4。

## 4. 步驟細節 / Step-by-Step

### 4.1 V017 SQL migration（步驟 2）

檔案：`sql/migrations/V017__edge_predictor_tables.sql`（新建）

- **新表** `learning.decision_features`（PK `context_id`，14 欄）— Stage 0 推理時特徵快照 + 回填 label
- **新表** `learning.decision_shadow_fills`（BIGSERIAL PK + CHECK `engine_mode='paper'`）— ε-greedy shadow fill 訓練樣本
- **ALTER** `trading.decision_context_snapshots` ADD 7 欄（predicted_q10/q50/q90/predictor_decision/shrinkage_decision/disagreed BOOLEAN/predict_latency_us）
- **ALTER** `trading.fills` ADD `entry_context_id TEXT NULL` + partial index `WHERE entry_context_id IS NOT NULL`
- 索引 `idx_dcs_predicted_q50` 用 plain `CREATE INDEX IF NOT EXISTS`（**非** CONCURRENTLY，因其不能在 transaction 內）；inline 註記「DCS 流量低，pre-predictor rollout 階段短暫鎖表可接受；若未來 traffic 提升，以手動 `CREATE INDEX CONCURRENTLY` 替換」

**未驗證項**：migration runner 類型（flyway / sqlx-migrate / 自訂）不明 — 本次僅確保 SQL 語法正確，`psql --set ON_ERROR_STOP=1` 風格 transactional 友好。

### 4.2 Rust 串接策略（步驟 3）

**問題**：`apply_fill` 有 40+ call site，改簽名會炸測試與產品程式碼。

**裁決**：新增 `PaperPosition.entry_context_id: String`（`#[serde(default)]` 向下相容 pre-V017 快照），不動 `apply_fill` 簽名；產品碼在 open 後以 setter 標記。

#### 4.2.1 `paper_state.rs`
- `PaperPosition` struct 加 `entry_context_id: String`（欄位位置在 `unrealized_pnl` 後）
- `PaperState::set_entry_context_id(symbol, &str)` — 空字串是 no-op，避免 accumulate 路徑擦掉 id
- `PaperState::get_entry_context_id(symbol) -> Option<&str>` — 讀回（`""` 視為 None）
- 3 處 struct literal 補 `entry_context_id: String::new()`（L315 `import_positions` / L384 `upsert_position_from_exchange` 新增分支 / L602 `apply_fill` 開新倉分支）

#### 4.2.2 `database/mod.rs`
`TradingMsg::Fill` 加 `entry_context_id: String` 欄位（緊接 `context_id` 後、`engine_mode` 前）。

#### 4.2.3 `database/trading_writer.rs`
- `FILL_BATCH_MAX` 註解 14→15 欄；測試斷言同步（`* 14` → `* 15`；4681 → 4369 max）
- INSERT 欄位列 + destructure + push_bind 加 `entry_context_id`
- 空字串以 `None::<String>` 寫入（DB 層 NULL，避免訓練時污染）；非空走 `Some(...)`
- 2 處測試 struct literal 補 `entry_context_id: String::new()`

#### 4.2.4 `tick_pipeline/mod.rs::emit_close_fill`
- 簽名加第 8 參數 `entry_context_id: &str`（雙語 docstring 說明「caller 應在 close 前 capture」）
- Fill emission 內 `entry_context_id: entry_context_id.to_string()`

#### 4.2.5 `tick_pipeline/on_tick.rs`（7 close 路徑 + 1 open 路徑）

| 行 | 路徑 | 取得 ectx 方式 |
|---|---|---|
| L190 | `risk_close:fast_track_reduce_half`（部分平倉） | `get_entry_context_id` before `reduce_position` |
| L272 | `risk_close:fast_track`（全平） | capture before `close_position_at_symbol_market` |
| L302 | h0-blocked stops | capture before close |
| L410 | paused stops | 本次新增 capture block |
| L908 | `strategy_close` | `pos.entry_context_id.clone()`（pos 已借用） |
| L1051 | `risk_close` | capture before close |
| L1092 | `halt_session` | capture before close |
| L726 | strategy open（apply_fill 後） | 新增 stamp：`was_open = get_position().is_none()`（pre-fill）+ `realized_pnl == 0.0` → stamp `make_context_id(em, symbol, ts_ms)` |

**關鍵設計**：`make_context_id` 是決定性函數（同 em/symbol/ts_ms → 同 id），所以 open 時 stamp 的 id 會與未來 Fill row 的 context_id 完全一致 — 為訓練 JOIN 提供強鍵。

#### 4.2.6 `tick_pipeline/commands.rs`

`place_order_command`（L131+）與 `apply_confirmed_fill`（L342+）採同一模式：
```
was_open = get_position().is_none()         ← pre-fill
existing_entry_ctx = get_entry_context_id() ← pre-fill（可能為空）
realized_pnl = apply_fill(...)
if was_open && realized_pnl == 0.0 {
    set_entry_context_id(symbol, make_context_id(em, symbol, ts_ms))
}
fill_entry_ctx = if realized_pnl != 0.0 { existing_entry_ctx } else { "" }
tx.send(Fill { entry_context_id: fill_entry_ctx, ... })
```

**三態消歧**：
- `was_open=true, realized==0` → 新開倉，stamp
- `was_open=false, realized!=0` → 平倉，用 existing_entry_ctx
- `was_open=false, realized==0` → 累倉，不動（空字串 setter 是 no-op 保護）

### 4.3 `store.rs` write_toml_atomic_fsynced 輔助（步驟 3 附帶）

AI-E #27 round-3 U2 發現 `write_toml_atomic` 只 rename 不 fsync — 在 kill-switch（`DisableEdgePredictorAll`）語境下，rename metadata 若未落盤、機器在 crash window 內斷電 → 看似寫入但實際丟失。

新增 `write_toml_atomic_fsynced`：
1. 寫 tmp 檔 + `sync_all()` on tmp file
2. `rename(tmp, target)`
3. `open(parent)` + `sync_all()` on parent dir — 確保 rename metadata 落盤

非 critical caller 繼續用 `write_toml_atomic` 免每寫 fsync 代價。耐久性由 CC #13 regression `test_disable_all_survives_sigkill`（Stage 1+ 待實作）權威驗證。

### 4.4 回歸測試（步驟 4）

#### 4.4.1 `paper_state.rs::tests`（8 新 test）
- `test_entry_context_id_default_empty_on_open` — apply_fill 開倉後 id 為 None
- `test_set_entry_context_id_on_fresh_open` — setter 寫入、getter 讀回
- `test_set_entry_context_id_ignores_empty` — 空字串 no-op，不擦掉既有 id
- `test_entry_context_id_survives_accumulate` — 同方向加倉保留首次 open 的 id
- `test_entry_context_id_cleared_after_close` — close_position 後 getter → None
- `test_entry_context_id_partial_close_preserves_id` — 部分平倉（qty < pos.qty）倖存腿保留 id
- `test_setter_on_missing_symbol_is_noop` — 對無持倉 symbol setter 靜默 no-op
- `test_pre_v017_snapshot_deserializes_with_empty_entry_context_id` — 缺欄位的 legacy JSON 仍可 deserialize，欄位預設 ""

#### 4.4.2 `tick_pipeline/tests.rs`（2 新 test）
- `test_emit_close_fill_threads_entry_context_id` — caller 傳入的 id 原樣寫入 Fill
- `test_emit_close_fill_accepts_empty_entry_context_id` — 空字串接受，不 panic

## 5. 測試結果 / Test Results

| Suite | Baseline | After | Result |
|---|---|---|---|
| `openclaw_engine --lib` | 1144 | **1158** (+14) | ✅ 0 fail |
| `openclaw_core --lib` | 372 | 372 | ✅ 0 fail |
| `openclaw_engine --tests` (e2e + stress) | 33+35 | 35 | ✅ 0 fail |

**+14 breakdown**：8 新 paper_state tests + 2 新 tick_pipeline tests + 4 pre-compact 新增（未追蹤到具體來源，推測來自 v1.3 work / 其他 session）。

**已知 pre-existing 問題**（非 P0，與本次改動無關）：
- `openclaw_engine --bin openclaw-engine` 在並行執行時 `test_paper_balance_from_env_missing` 會 fail（env var race condition），`--test-threads=1` 即通過 — 與 stage 0 無關
- `openclaw_core/tests/golden_extreme.rs` 缺 `StopConfig.trailing_activation_pct` 欄位（pre-existing，stash 驗證無關）

## 6. 關鍵設計決策 / Key Decisions

| 決策 | 替代方案 | 為何選此 |
|---|---|---|
| **新欄位** `fills.entry_context_id`（而非復用 `context_id`） | Option A: 復用 context_id（spec v1.3 原案） | ML-MIT+AI-E 查 `tick_pipeline/mod.rs:1025`，`emit_close_fill` 用 `make_context_id(em, symbol, ts_ms)` 合成 close-time 新 id — 復用 = 100% JOIN mismatch = silent label loss |
| **setter/getter pattern**（不改 apply_fill 簽名） | 改 apply_fill 加 optional context_id 參數 | 40+ call site 成本過高；setter 隔離變更 |
| **`#[serde(default)]`** for entry_context_id | 強制 migration 填欄位 | 舊快照重啟時仍可 restore；欄位默認 `""` = None 語義 |
| **決定性 `make_context_id`** 作為 open-stamp | UUID | open-time stamp 必須與 close-time Fill 的 context_id 一致（同公式）才能訓練 JOIN |
| **`String::new()` ≡ SQL NULL**（writer 空字串→None） | 允許空字串寫入 | 訓練 JOIN 條件 `entry_context_id IS NOT NULL` 才能排除開倉 Fill |
| **plain `CREATE INDEX`** 而非 CONCURRENTLY | CONCURRENTLY | migration runner 類型未知；CONCURRENTLY 不能在 transaction 內；DCS 流量低、短暫鎖可接受 |
| **單一 commit** 覆蓋 spec + SQL + Rust | 拆多 commit | ML-MIT+AI-E hard constraint：必須同窗口落地避免 silent NULL |

## 7. 未解 / 後續 / Follow-ups

**Stage 1 待做**（blocked by 本次 commit）：
- Task #25 PA — `parquet_etl.py` 補實現 + train 觸發器 + 與 LinUCB 共存
- Task #26 ML-MIT — quantile LGBM + CQR + CPCV + isotonic calibration（blocked by #25）
- Task #27 AI-E — Rust `edge_predictor/` module + PyO3 ONNX runtime + `cost_gate` 接入（部分 helper 本次已落地）
- Task #28 CC — 13 項必查 + T1-T23 regression（blocked by #27）

**Housekeeping（非阻塞）**：
- spec §7.1 補 `ort` macOS dylib bundling 提醒
- CC #13 regression 加 strace Linux-only 註記
- V017 deployment 需由 operator 或 DBA 明確觸發；本次 commit 只是把檔案放進版本控制
- CONCURRENTLY index rebuild 作為未來 housekeeping（若 DCS 流量升）

**留給下一個 session**：
- 觀察 V017 在哪個環境先 apply（demo vs paper vs live）、觀察頭 24h 的 `entry_context_id NOT NULL` 比例（預期 paper+demo 接近 100%，除異常 open 路徑）
- 若 NOT NULL 比例 < 95%，需回查是否有漏掉的 Fill 發射點

## 8. 檔案清單 / Changed Files

**Commit `1366054` · 13 files · +980 / -53 lines**

| File | Scope |
|---|---|
| `TODO.md` | Stage 0 狀態更新（v1.4 GREEN → 開工中）|
| `docs/references/2026-04-15--edge_predictor_spec.md` | v1.3 → v1.4 CHANGELOG（5 reality-alignment 裁定）|
| `docs/worklogs/2026-04-15--edge_predictor_spec_v1_to_v1_3.md` | pre-compact 四輪審查完整過程（239 行）|
| `sql/migrations/V017__edge_predictor_tables.sql` | **新** 2 表 + 2 ALTER + index |
| `rust/openclaw_engine/src/config/store.rs` | `write_toml_atomic_fsynced` helper（AI-E U2）|
| `rust/openclaw_engine/src/database/mod.rs` | `TradingMsg::Fill` 加 `entry_context_id` |
| `rust/openclaw_engine/src/database/trading_writer.rs` | Fill writer INSERT + batch 參數重算 |
| `rust/openclaw_engine/src/ipc_server/tests.rs` | struct literal 補欄位 |
| `rust/openclaw_engine/src/paper_state.rs` | `PaperPosition.entry_context_id` + getter/setter + 8 新測試 |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | place_order_command + apply_confirmed_fill 串接 |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | `emit_close_fill` 簽名 + Fill emission |
| `rust/openclaw_engine/src/tick_pipeline/on_tick.rs` | 7 close 路徑 + 1 open stamp |
| `rust/openclaw_engine/src/tick_pipeline/tests.rs` | 3 舊 test 補新參數 + 2 新 test |

## 9. 驗收 / Sign-off

- [x] Spec v1.3→v1.4 reality-alignment 全 5 項落入 CHANGELOG
- [x] V017 SQL 檔案存在並語法正確
- [x] Rust 全數 4 個產品 Fill 發射點（+1 close helper）皆串接 `entry_context_id`
- [x] `cargo check -p openclaw_engine` 綠
- [x] `cargo test -p openclaw_engine --lib` 1158 pass / 0 fail
- [x] `cargo test -p openclaw_engine --tests` 35 pass / 0 fail
- [x] `cargo test -p openclaw_core --lib` 372 pass / 0 fail
- [x] 8+2 新回歸測試全過
- [x] pre-V017 snapshot serde 向下相容驗證（`test_pre_v017_snapshot_deserializes_with_empty_entry_context_id`）
- [x] Commit `1366054` 落地，訊息含 R1-R5 裁定摘要 + co-landing 約束說明

**Stage 0 實施 COMPLETE**。#25/#27 可並行啟動 Stage 1。

---

# Phase A — Predictor Gate Wiring（2026-04-15 post-compact）

**Commits**：
- `8c1f234 feat(edge-p3-1): wire edge_predictor gate into IntentProcessor (Phase A)` — A1-A4
- `3753ede feat(edge-p3-1): plumb FeatureVectorV1 into on_tick gate (Phase A5)` — A5

**測試基準線變更**：engine lib 1158 → **1249**（+91）· core lib 372（不變）· engine e2e 33+35 → **35**（合併；e2e 本次不變）· 0 fail
- A4 landing：+77（EdgePredictor config TOML / PipelineCommand variants / gate.rs 邊界測試 / IntentProcessor rng seed + shadow policy dispatch）
- A5 landing：+14（2 to_jsonb 回傳 + 11 feature_builder + 1 on_tick wiring assertion）

**角色**：主會話 = PM+Conductor+AI-E 合一；無 sub-agent

## 1. 目標 / Objective

Stage 0 Phase A 的交付物：**讓 edge predictor gate 在產線真正被諮詢**。v1.4 spec §7.3 / §7.4 規範了 gate 的 ordering 與 IntentProcessor 整合點，但 A1-A4 落地完後 `features=None` 會讓新路徑短路回到舊 JS shrinkage — 需要 A5 把 `FeatureVectorV1` 從已有的 runtime context 組出來餵進去，gate 才算真正上線（即使 `use_edge_predictor=false` 預設不啟用，代碼路徑也必須先 reachable）。

## 2. A1-A4 Wiring（Commit `8c1f234`）

### A1 RiskConfig TOML
- `EdgePredictor` struct 8 字段：`use_edge_predictor`（預設 false → 產線默認仍走 JS shrinkage）· `shadow_mode`（true=觀察模式，不實施拒絕）· `quantile_safety_k`（cost margin 乘數）· `require_q10_positive_for_adds`（加倉 guard）· `fallback_on_error`（enum: `ShrinkageGate / RejectAll`）· `exploration_rate`（ε-greedy，paper only）· `retrain_cadence_seconds` · `model_max_age_seconds`
- `EdgePredictorFallback` enum，snake_case TOML serde

### A2 PipelineCommand
- 3 新 variants：
  - `SetEdgePredictorShadow { strategy, shadow: bool }` — per-strategy shadow toggle
  - `DisableEdgePredictorAll` — kill-switch，呼叫 `EdgePredictorStore::clear_all()`
  - `EmitShadowFill { context_id, strategy, features_jsonb, ... }` — ε-greedy branch 寫 `learning.decision_shadow_fills`
- `BoxedEdgePredictor` newtype 手寫 Debug impl（derive(Debug) on dyn trait 不可行）
- `EdgePredictorStore::clear_all() -> usize` kill-switch 回報清除數量

### A3 edge_predictor/gate.rs（新）
- `edge_predictor_gate(...) -> PredictorGateOutcome` 純函數：按 §7.3 F2 **正確順序**：feature sanity（`all_in_range`）→ `load_for(strategy)` → staleness check（`age_seconds > model_max_age_seconds`）→ `predict()` → monotone rearrangement → cost margin（`q50 - k*(q50-q10) > cost`）→ ε-greedy（paper only）→ q10-add guard
- Outcome enum：`Accept / Reject(reason) / RejectAdd(reason) / ShadowFill / Fallback(FallbackReason)`
- `seed_for_engine(kind) -> u64` 確定性 per-engine SmallRng seed，避免三引擎共享同一 RNG 狀態
- `FallbackReason` enum：`NoModel / SchemaHashMismatch / DefinitionHashMismatch / Stale / InferenceFailed / InvalidPrediction / FeatureInvalid`

### A4 intent_processor/mod.rs
- `IntentProcessor` 多帶 `Arc<EdgePredictorStore>` + `parking_lot::Mutex<SmallRng>`（interior mutability for `&self`）+ `PipelineKind` + `Option<Sender<PipelineCommand>>`（shadow-fill emit channel）
- `process_with_features()` / `process_gates_only_with_features()` 新入口：保留舊 `process()` 簽名不變（29 call sites 不動）
- `evaluate_predictor_gate()` 政策層：
  - `use_edge_predictor=false` → None → fall-through JS gate
  - `shadow_mode=true` → observe + metric，fall-through JS gate
  - `Accept` → 短路通過，跳過 JS gate
  - `Reject/RejectAdd` → 短路拒絕
  - `ShadowFill` → 發 `EmitShadowFill` IPC + fall-through
  - `Fallback` → 按 `fallback_on_error` 政策路由

## 3. A5 Feature Plumbing（Commit `3753ede`）

### 3.1 新檔：`edge_predictor/feature_builder.rs`（383 行）

`build_feature_vector(intent, event, indicators, atr_value, paper_state) -> FeatureVectorV1`

| Feature group | 取得源 | 備註 |
|---|---|---|
| Regime 5（adx_1h / bb_width_pct / atr_pct / funding_rate / realized_vol_1h） | `IndicatorSnapshot` · `PriceEvent.funding_rate` · `atr_value` 參數 | bandwidth 從 `(upper-lower)/mean` 轉 % |
| Microstructure 3（basis_bps / orderbook_imbalance_top5 / spread_bps） | `PriceEvent.index_price / bid_price / ask_price / bids5 / asks5` | `bids5/asks5` 缺席時 `orderbook_imbalance_top5=0`（僅 Orderbook event 帶此值） |
| Strategy 3（confluence_score / persistence_elapsed_ms / side） | **zeroed 佔位符**（A6+ 由策略層填）+ `intent.is_long ? +1.0 : -1.0` | side 現在已接 |
| Position 3（notional_pct_of_bal / concurrent_positions / same_direction_cnt） | `PaperState.balance()` / `.positions()` | zero-balance 走 NaN-safe 分支 |
| Time 3（tod_sin / tod_cos / is_funding_settlement_window） | `event.ts_ms` | Bybit 8h 窗口最後 15 min → flag=1 |

**防禦性 clamp**：每個 f32 都走 `clamp_f32(v, lo, hi)`，caller 保證 `all_in_range` **不可能** 失敗 — upstream indicator drift 不會讓 gate feature sanity 直接 reject。

**11 新 test** 覆蓋：full context / cold-start / extreme clamping / orderbook from bids5/asks5 / spread_bps / zero-balance NaN safety / side ±1 / ToD at midnight+noon / funding window flag（7:50 in / 7:30 out）/ same_direction_cnt from `import_positions` / atr_value override

### 3.2 `FeatureVectorV1::to_jsonb()`

手寫 JSONB serializer（避免 hot-path serde dep），17 key 全列：
```rust
#[inline]
fn json_f32(v: f32) -> String {
    if v.is_finite() { format!("{}", v) } else { "null".into() }
}
```
NaN/Inf → `null` 讓下游 Postgres JSONB parser 不 fail。**2 新 test**：roundtrip via `serde_json::Value` 驗證 key 完整性 + NaN/Inf emit null 驗證。

### 3.3 on_tick.rs 串接（兩個 call site）

**Exchange branch（L627）**：
```rust
let features = crate::edge_predictor::feature_builder::build_feature_vector(
    intent, event, indicators.as_ref(), atr_value, &self.paper_state,
);
let context_id = make_context_id(em, &intent.symbol, event.ts_ms);
let gate = self.intent_processor.process_gates_only_with_features(
    intent, &self.governance, &self.paper_state, atr_value,
    self.pipeline_kind.governance_profile(),
    Some(&features), Some(&context_id), event.ts_ms,
);
```

**Paper branch（L703）** 對稱走 `process_with_features()`。

### 3.4 intent_processor/mod.rs shadow-fill closure

`evaluate_predictor_gate()` 內把佔位的 `|| "{}".to_string()` 換成 `|| features.to_jsonb()`。**惰性**：只有 ε-greedy branch 才付 JSONB 序列化成本。

## 4. 測試結果 / Test Results

| Suite | Pre-Phase-A | Post-A4 | Post-A5 | Δ |
|---|---|---|---|---|
| `openclaw_engine --lib` | 1158 | 1235 | **1249** | +91 |
| `openclaw_core --lib` | 372 | 372 | 372 | 0 |
| `openclaw_engine --tests`（e2e + stress） | 35 | 35 | 35 | 0 |
| **總計** | 1565 | 1642 | **1656** | +91 |

**cargo build**：乾淨（6 pre-existing warnings 不變）
**cargo check**：PASS

## 5. 關鍵設計決策 / Key Decisions

| 決策 | 替代方案 | 為何選此 |
|---|---|---|
| **Additive API**（`process_with_features` 新入口，舊 `process` 不改簽名） | 改 `process()` 加 optional 參數 | 29 call site 成本過高；新/舊路徑並存直到遷移完成 |
| **`use_edge_predictor=false` 預設** | 預設 true + `shadow_mode=true` | 部署時零行為改變；operator 需明確切開關才走新路徑 |
| **Clamp-to-range in builder**（caller 保證 `all_in_range`） | builder 不 clamp，讓 gate sanity check 攔截 | `clamp_f32` 是廉價 `max(min(v, hi), lo)`；invariant #12 成為「事實上不可達」的雙保險 |
| **Hand-rolled `to_jsonb()`**（無 serde） | `serde_json::to_string` | 17 key 固定 schema，手寫 format 比 serde 輕；lazy closure 只在 shadow branch 付代價 |
| **NaN/Inf → `null`** 而非 `0.0` / 跳過 key | 寫 `NaN`（不合法 JSON） | Postgres JSONB parser 要合法 JSON；下游分析時 `WHERE feature IS NOT NULL` 自然排除 |
| **`confluence_score` / `persistence_elapsed_ms` zeroed 佔位** | 從策略內部 state 爬取 | 這兩個 feature 只有策略層有 — 走 OrderIntent 加字段是 A6+ 工作（FUP-8 OrderIntent schema 擴充同步做）|
| **Per-engine deterministic RNG seed**（`seed_for_engine`） | 共享 SmallRng | 三引擎共享 RNG 會讓 paper/demo/live 的 ε-greedy 相互干擾（雖然 live `exploration_rate=0` 不走分支），乾淨地隔離 |

## 6. 後續 / Phase B Handoff

**Phase A COMPLETE**。產線狀態：
- ✅ Gate 在 hot path 被諮詢（每 intent 都建 features + 呼叫 `process_with_features`）
- ✅ 預設 `use_edge_predictor=false` → fall-through JS shrinkage，**零行為改變**
- ✅ Kill-switch IPC `DisableEdgePredictorAll` 可用
- ✅ Shadow-fill JSONB payload 串通（等 Stage 2 模型載入時可直接寫 `learning.decision_shadow_fills`）

**Phase B 範疇**（A6+，#27 AI-E 後半）：
1. **Strategy-side feature plumbing**：`confluence_score` + `persistence_elapsed_ms` 從 5 策略（MA/BBR/BBB/Grid/FundingArb）穿透到 `OrderIntent`；FUP-8 Phase 3 的 OrderIntent schema 擴充（加 `edge/funding_rate/basis/regime`）同步合流做
2. **Predictor 實例注入**：Stage 2（ML-MIT 交付 ONNX artifact）之後，Bootstrap 時掃 `settings/models/{strategy}-v{N}.onnx` → 填 `EdgePredictorStore::swap()`；需要 `tract_backend` / `ort_backend` feature flag 選一（F8 互斥 compile_error 已就位）
3. **CC 13 項必查 + T1-T23 regression**（#28）：Phase A4/A5 已落的部分可開始 sub-set 驗證；完整 23 條等 backend + strategy features 完成

**Blocked on**：
- #27 後半（backend + strategy features）→ #28 CC 審查 → #29 Shadow 14d → #30 paper promote → #31 demo promote
- FUP-8 Phase 3（OrderIntent schema 擴充）與 A6 合流

## 7. 檔案清單 / Changed Files

### Commit `8c1f234` · 19 files · +1956 / -18 lines

| File | Scope |
|---|---|
| `rust/openclaw_engine/src/config/risk_config.rs` | `EdgePredictor` + `EdgePredictorFallback` TOML |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | 3 `PipelineCommand` variants |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | `edge_predictor_store: Option<Arc<EdgePredictorStore>>` field |
| `rust/openclaw_engine/src/edge_predictor/mod.rs` | `BoxedEdgePredictor` newtype + `clear_all()` |
| `rust/openclaw_engine/src/edge_predictor/gate.rs` | **新** pure gate function + seeds + outcomes |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | RNG + PipelineKind + shadow policy dispatch |
| `rust/openclaw_engine/src/event_consumer/**` | 3 command handlers |
| `rust/openclaw_engine/src/main.rs` | bootstrap wiring |
| 其他 test/helper | struct literal 補欄位 |

### Commit `3753ede` · 5 files · +518 / -7 lines

| File | Scope |
|---|---|
| `rust/openclaw_engine/src/edge_predictor/feature_builder.rs` | **新** 383 行 + 11 tests |
| `rust/openclaw_engine/src/edge_predictor/features.rs` | `to_jsonb()` + `json_f32()` + 2 tests |
| `rust/openclaw_engine/src/edge_predictor/mod.rs` | `pub mod feature_builder` |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | shadow closure 換成 `features.to_jsonb()` |
| `rust/openclaw_engine/src/tick_pipeline/on_tick.rs` | L627 + L703 call-site plumbing |

## 8. 驗收 / Sign-off

- [x] A1 TOML schema + default `use_edge_predictor=false`
- [x] A2 3 `PipelineCommand` variants + handlers
- [x] A3 pure `edge_predictor_gate()` 按 §7.3 F2 順序
- [x] A4 `IntentProcessor` 多入口 + shadow policy dispatch（舊 `process()` 不改）
- [x] A5 `build_feature_vector()` 13/17 features（confluence/persistence/orderbook 佔位）
- [x] A5 `FeatureVectorV1::to_jsonb()` + NaN/Inf → null + 2 tests
- [x] A5 `on_tick.rs` 兩個 call-site 串接
- [x] 產線預設零行為改變（`use_edge_predictor=false` fall-through JS gate）
- [x] `cargo build` 乾淨 / `cargo check` PASS
- [x] 1249 lib + 372 core + 35 e2e = **1656** pass / **0 fail**
- [x] Commits `8c1f234` + `3753ede` 落地，訊息含 A1-A5 裁定摘要

**Phase A COMPLETE**。進入 Phase B（A6+ strategy-side features + FUP-8 schema 合流）等 #27 AI-E 後半工作展開。

---

# Phase A6 — Strategy-Side Feature Plumbing（2026-04-15 補）

## A6.1 目標 / Scope

Phase A5 在 `build_feature_vector()` 把 slot #9 `confluence_score` 和 slot #10 `persistence_elapsed_ms` 以 `0.0` 佔位 — feature 管線通了但**資料是假的**。A6 的任務：把這兩個值從各策略內部 state 真實穿透到 `OrderIntent`，再到 `feature_builder`，讓 Phase B gate 啟用後看到的是策略真正的決策時快照。

**範圍定界**：
- 3 有 confluence 的策略（MA / BBR / BBB）填真值
- 2 無 confluence 的策略（Grid / FundingArb）顯式 `None`
- 合成意圖（close 路徑、IPC 派發）顯式 `None`
- 產線零行為改變（gate 仍 `use_edge_predictor=false`）

## A6.2 OrderIntent schema 擴充

**選項**：Option-field 加 `#[serde(default)]` vs 必填字段

採用 Option + default 的理由：
1. **跨版本 IPC 兼容** — Python/GUI 側若送舊格式 OrderIntent，新 Rust 反序列化仍成功（視為 None）
2. **語意忠實** — Grid/FundingArb 沒有 confluence，用 `None` 表示「不適用」比 `0.0` 更誠實（0 是合法分數）
3. **零前向污染** — 不強迫未來可能新增的策略種類都得有 confluence 概念

```rust
pub struct OrderIntent {
    // ... 既有欄位 ...
    #[serde(default)]
    pub confluence_score: Option<f32>,
    #[serde(default)]
    pub persistence_elapsed_ms: Option<u64>,
}
```

## A6.3 PersistenceTracker 只讀訪問器

現有 `check()` 既做 state 更新又返回通過與否 — A6 需要**不改 state**讀取「信號開始後多久」。新增：

```rust
pub fn elapsed_ms(&self, symbol: &str, now_ms: u64) -> Option<u64> {
    self.state.get(symbol).map(|&(_dir, first_ts)| now_ms.saturating_sub(first_ts))
}
```

**呼叫時機**：策略的 entry 分支在 `check()` 回傳 true 後才呼叫 `elapsed_ms()` — 此時保證 `≥ min_persistence_ms`。放在 `check()` 後讀而非內化到 check 返回值是為了：
- 不改動既有 check API 的所有呼叫點
- 測試可以獨立斷言 `elapsed_ms()` 行為（不依賴 check 路徑）

## A6.4 5 策略的 entry-site 填值策略

| 策略 | confluence_score | persistence_elapsed_ms |
|---|---|---|
| MaCrossover | `score.map(\|s\| s as f32)` | `persistence.elapsed_ms(symbol, ts_ms)` |
| BbReversion | 同上 | 同上 |
| BbBreakout | 同上 | 同上 |
| GridTrading | `None` | `None` |
| FundingArb | `None` | `None` |

Grid 是 price-level 機械式下單，無信號融合；FundingArb 是費率套利，沒有 persistence 概念（是 snapshot 決策）。顯式 `None` 而非 `Some(0.0)`，讓下游 feature builder 的 `unwrap_or(0.0)` 語意清晰：「無此概念」而非「分數為零」。

## A6.5 Builder 防禦性 clamp

策略理論上會產出合規範圍的值，但 A6 在 builder 再 clamp 一次：

```rust
let confluence_score = clamp_f32(intent.confluence_score.unwrap_or(0.0), 0.0, 65.0);
let persistence_elapsed_ms = clamp_f32(
    intent.persistence_elapsed_ms.unwrap_or(0) as f32, 0.0, 3_600_000.0,
);
```

**理由**：
- `all_in_range()` invariant #12 是 fail-closed sanity — 若哪天新策略計算 confluence 時 off-by-one 輸出 65.5，寧可 builder clamp 而不是 gate 跳起來
- `clamp_f32` 成本：單一 `max(min(...))`，熱路徑可忽略
- **雙保險**：builder clamp + gate `all_in_range` — 一條都不應該成為實戰中的救命防線，但兩條在位比一條穩

## A6.6 21 處測試 fixture 批次更新

OrderIntent 加字段，所有用 struct literal 建 fixture 的地方都會 E0063 失敗。站點清單：

| 檔案 | 站點數 |
|---|---:|
| `intent_processor/tests.rs` | 13 |
| `mode_state.rs` | 1 |
| `orchestrator.rs` | 2 |
| `strategies/mod.rs` | 1 |
| `tests/stress_integration.rs` | 4 |
| **合計** | **21** |

手工 21 次 Edit 太脆；用 Python regex：`limit_price: <expr>,\n<indent>}` 前插入兩個 `None`。一次 run 完成 + build 即驗證。

## A6.7 測試增量

engine lib：**1249 → 1257（+8）**

新增：
- `feature_builder` +4：`test_confluence_none_means_zero` / `test_confluence_some_propagates_through` / `test_confluence_clamped_above_65` / `test_persistence_zero_is_valid`
- `confluence::tests` +4：`elapsed_ms_none_before_signal` / `elapsed_ms_tracks_since_onset` / `elapsed_ms_resets_on_direction_flip` / `elapsed_ms_none_after_signal_disappears`

core lib: 372（不變）· e2e: 35（不變）· 總和 **1664 pass / 0 fail**

## A6.8 檔案清單 / Commit `a23b268` · 15 files · +273 / -16

| File | Scope |
|---|---|
| `rust/openclaw_engine/src/intent_processor/mod.rs` | OrderIntent +2 Option fields (`#[serde(default)]`) |
| `rust/openclaw_engine/src/strategies/confluence.rs` | `PersistenceTracker::elapsed_ms()` + 4 tests |
| `rust/openclaw_engine/src/strategies/ma_crossover.rs` | `make_intent_with_qty` 擴 2 param，entry 填值 |
| `rust/openclaw_engine/src/strategies/bb_reversion.rs` | `make_entry_intent_with_qty` 擴 2 param |
| `rust/openclaw_engine/src/strategies/bb_breakout.rs` | inline literal 填 score + persistence |
| `rust/openclaw_engine/src/strategies/grid_trading.rs` | 2 literal → `None, None` |
| `rust/openclaw_engine/src/strategies/funding_arb.rs` | 1 Open literal → `None, None` |
| `rust/openclaw_engine/src/tick_pipeline/on_tick_helpers.rs` | `build_intent()` → `None, None` |
| `rust/openclaw_engine/src/tick_pipeline/commands.rs` | IPC OpenPosition → `None, None` |
| `rust/openclaw_engine/src/edge_predictor/feature_builder.rs` | 讀 intent + clamp + 4 regression tests |
| `rust/openclaw_engine/src/intent_processor/tests.rs` | 13 fixture 補欄位 |
| `rust/openclaw_engine/src/mode_state.rs` | 1 fixture 補欄位 |
| `rust/openclaw_engine/src/orchestrator.rs` | 2 fixture 補欄位 |
| `rust/openclaw_engine/src/strategies/mod.rs` | 1 fixture 補欄位 |
| `rust/openclaw_engine/tests/stress_integration.rs` | 4 fixture 補欄位 |

## A6.9 Phase B 剩餘工作（精簡）

A6 完成後，Phase B 只剩：

1. **Backend 選擇** — `tract_backend` / `ort_backend` feature flag 擇一（F8 互斥 `compile_error!` 已在）；Stage 2 ML-MIT 交付 ONNX 後才能做實質驗證
2. **Stage 2 模型載入** — Bootstrap 掃 `settings/models/{strategy}-v{N}.onnx` → `EdgePredictorStore::swap()`；schema v1.4 checksum 比對
3. **CC 13 項必查 + T1-T23 regression**（#28）— 含 A5/A6 feature quality 驗證
4. **Shadow mode 14d**（#29）→ paper promote 7d（#30）→ demo promote（#31）

**原 Phase B 第 1 項（strategy-side features）已由 A6 吸收完畢**。

## A6.10 驗收 / Sign-off

- [x] OrderIntent 2 Option fields + `#[serde(default)]`
- [x] `PersistenceTracker::elapsed_ms()` 無副作用訪問器 + 4 tests
- [x] MA / BBR / BBB entry site 填真值；Grid / FundingArb + 合成意圖 None
- [x] `feature_builder` 讀 intent + 雙保險 clamp + 4 regression tests
- [x] 21 fixture 站點批次補欄位（scripted）
- [x] engine lib 1249 → 1257 · 1664 pass / 0 fail
- [x] 產線零行為改變（gate 仍 `use_edge_predictor=false`）
- [x] Commit `a23b268` 落地，訊息含 A6 全部裁定

**Phase A + A6 COMPLETE**。Phase B 只剩 backend 選擇 + 模型載入 + CC 審查 + shadow/paper/demo 升遷管道。
