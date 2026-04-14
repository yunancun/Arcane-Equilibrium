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
