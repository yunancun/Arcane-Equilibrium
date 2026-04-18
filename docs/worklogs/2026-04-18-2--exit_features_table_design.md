# EXIT-FEATURES-TABLE-1 — Schema + Rust 接線設計草稿

**日期**：2026-04-18
**作用域**：DUAL-TRACK-EXIT-1 Phase 1b 前置 / Step 0 不確定 2 修復
**狀態**：設計草稿，待 E2 審查 + operator 批

---

## 背景

Step 0 不確定 2 結果：`learning.decision_features` 是 entry-time snapshot（17 個 entry 市場特徵），DUAL-TRACK Track P 需要的是 exit-time position trajectory（peak/giveback/ROC 是自開倉起 tick 軌跡的量）。兩者是完全不同維度。

現有相關表：
- `trading.fills` — 只有 entry/exit 價格、qty、fee、pnl，無 peak trajectory
- `trading.decision_outcomes` — 有 `max_favorable / max_adverse` **但 113k rows 全 NULL**（dead column）
- `trading.fills.details` jsonb — 24h 100% NULL

**決策**：新建 `learning.exit_features` 表，不沿用 decision_outcomes（理由：decision_outcomes 是 Phase 5 realized-edge 背填作業專用，schema 是 N-minute forward returns，不適合 peak tracking；且該表已 dead，沿用會混淆）。

---

## 目標 7 維度（自 DUAL-TRACK 設計）

| # | 欄位 | 型態 | 語意 | 來源 |
|---|---|---|---|---|
| 1 | `est_net_bps` | real | 退場時的 **估計 net edge**（bps）| 從 JS edge_estimates + 當時 cost_gate 計算 |
| 2 | `peak_pnl_pct` | real | 自開倉以來 **max favorable** pnl 百分比 | Rust `PaperPosition.max_favorable_pnl_pct`（新欄位）|
| 3 | `atr_pct` | real | 當時 ATR / price | `price_tracker.atr_pct(symbol)` |
| 4 | `giveback_atr_norm` | real | (peak - current) / ATR — 歸一化的回吐幅度 | derive 自 peak + current + atr |
| 5 | `time_since_peak_ms` | bigint | 自 peak 達到以來的毫秒數 | derive 自 `peak_reached_ts_ms`（新欄位）|
| 6 | `price_roc_short` | real | 短時間窗 (默認 300ms) 的 price rate-of-change | `price_tracker.compute_roc(symbol, 300)`（新 fn）|
| 7 | `entry_age_secs` | real | 自 entry 以來的秒數 | derive 自 position.opened_ts_ms |

---

## DDL 草稿

```sql
-- File: sql/migrations/V_YYYYMMDD__exit_features.sql
-- Owner: trading_admin

CREATE TABLE IF NOT EXISTS learning.exit_features (
    -- Identity / 身份
    context_id      text                     NOT NULL,   -- 與 decision_features 對齊的 context_id
    ts              timestamp with time zone NOT NULL,   -- exit 時刻
    engine_mode     text                     NOT NULL,   -- 'paper' | 'demo' | 'live_demo' | 'live'
    strategy_name   text                     NOT NULL,
    symbol          text                     NOT NULL,
    side            smallint                 NOT NULL,   -- 1=long / -1=short

    -- 7-dim Track P features (all nullable for forward compatibility)
    est_net_bps         real,
    peak_pnl_pct        real,
    atr_pct             real,
    giveback_atr_norm   real,
    time_since_peak_ms  bigint,
    price_roc_short     real,
    entry_age_secs      real,

    -- Exit meta / 退場元數據
    exit_source         text,   -- 'Physical' | 'Hybrid' | 'ML-shadow' | 'TimeStop' | 'HardStop' | ...
    exit_trigger_rule   text,   -- 具體觸發規則名（Phase 1a 列為 'PHYS-LOCK' / 'COST-EDGE' 等）
    realized_net_bps    real,   -- 真正成交的 net bps（對照 est_net_bps 的 ex-post label）

    -- Provenance / 來源可追溯
    feature_schema_version text NOT NULL DEFAULT 'v1.0',
    feature_schema_hash    text NOT NULL,  -- 欄位結構 hash（drift 檢測用）

    PRIMARY KEY (context_id)
);

CREATE INDEX idx_exit_features_strategy_mode_ts
    ON learning.exit_features (strategy_name, engine_mode, ts DESC);
CREATE INDEX idx_exit_features_ts
    ON learning.exit_features (ts DESC);
CREATE INDEX idx_exit_features_symbol_ts
    ON learning.exit_features (symbol, ts DESC);

-- TimescaleDB hypertable（與 decision_features 對稱）
SELECT create_hypertable('learning.exit_features', 'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

COMMENT ON TABLE learning.exit_features IS
    'DUAL-TRACK-EXIT-1 Track P feature labels. Written on every position exit by Rust paper_state::close_position path.';
```

---

## Rust 接線（新 msg variant + writer）

### 1. `database/mod.rs` 新增 enum variant

```rust
pub enum LearningMsg {
    DecisionFeature(DecisionFeatureRow),
    ShadowFill(ShadowFillRow),
    // 新增：
    ExitFeature(ExitFeatureRow),
}

pub struct ExitFeatureRow {
    pub context_id: String,
    pub ts_ms: i64,
    pub engine_mode: String,
    pub strategy_name: String,
    pub symbol: String,
    pub side: i16,
    pub est_net_bps: Option<f32>,
    pub peak_pnl_pct: Option<f32>,
    pub atr_pct: Option<f32>,
    pub giveback_atr_norm: Option<f32>,
    pub time_since_peak_ms: Option<i64>,
    pub price_roc_short: Option<f32>,
    pub entry_age_secs: Option<f32>,
    pub exit_source: Option<String>,
    pub exit_trigger_rule: Option<String>,
    pub realized_net_bps: Option<f32>,
    pub feature_schema_version: String,
    pub feature_schema_hash: String,
}
```

### 2. `database/exit_feature_writer.rs`（新檔，沿用 `decision_feature_writer.rs` pattern）

結構完全 mirror `decision_feature_writer.rs`：
- `run_exit_feature_writer(rx, pool, config, cancel)` 主循環
- `flush_exit_features(pool, buf)` QueryBuilder `INSERT INTO learning.exit_features ... ON CONFLICT (context_id) DO UPDATE SET ...`（允許重寫）
- JSONL fallback 同 pattern

### 3. `tasks.rs` `spawn_db_writers` 回傳擴充

```rust
let (exit_feature_tx, exit_feature_rx) = tokio::sync::mpsc::channel(2048);
tokio::spawn(exit_feature_writer::run_exit_feature_writer(
    exit_feature_rx, ef_pool, ef_config, ef_cancel,
));
```
回傳 tuple 加一欄 `Some(exit_feature_tx)`。

### 4. `EventConsumerDeps` 新欄位 `exit_feature_tx: Option<Sender<ExitFeatureRow>>`

**關鍵：三個 pipeline（Paper/Demo/Live）都 clone 此 tx — 不要重蹈 MARKET-KLINES-STALE-1 的 D19 覆轍**。

### 5. `paper_state.rs` 的 `close_position` path 寫入

每筆 `close_fill` 生成時同時生成 `ExitFeatureRow`：

```rust
// pseudo-code in paper_state::close_position / 退場路徑
let exit_row = ExitFeatureRow {
    context_id: position.entry_context_id.clone(),   // 對齊 decision_features
    ts_ms: event.ts_ms,
    engine_mode: self.engine_mode.clone(),
    strategy_name: position.strategy.clone(),
    symbol: position.symbol.clone(),
    side: if position.is_long { 1 } else { -1 },
    est_net_bps: self.cost_gate.est_net_bps(symbol, strategy),
    peak_pnl_pct: Some(position.max_favorable_pnl_pct),      // 新欄位
    atr_pct: self.price_tracker.atr_pct(symbol),
    giveback_atr_norm: derive_giveback(position, current_price, atr),
    time_since_peak_ms: event.ts_ms - position.peak_reached_ts_ms,  // 新欄位
    price_roc_short: self.price_tracker.compute_roc(symbol, 300),    // 新 fn
    entry_age_secs: ((event.ts_ms - position.opened_ts_ms) as f32) / 1000.0,
    exit_source: Some(exit_source_tag.clone()),
    exit_trigger_rule: Some(trigger_rule_name.clone()),
    realized_net_bps: Some(realized_net_bps),
    feature_schema_version: "v1.0".into(),
    feature_schema_hash: EXIT_FEATURE_SCHEMA_HASH_V1_0,
};
if let Some(ref tx) = self.exit_feature_tx {
    let _ = tx.try_send(exit_row);
}
```

### 6. `PaperPosition` 新增 tracking 欄位

`paper_state.rs` struct:
- `max_favorable_pnl_pct: f32`（每 tick 更新：`max(self.max_favorable_pnl_pct, current_unrealized_pnl_pct)`）
- `peak_reached_ts_ms: i64`（當 max_favorable 刷新時同步更新）

**Migration**：legacy positions（引擎重啟遺留）默認 `max_favorable_pnl_pct = 0.0`, `peak_reached_ts_ms = opened_ts_ms`。首次 tick 後自然修正。

### 7. `price_tracker` 新 fn `compute_roc(symbol, lookback_ms) -> Option<f32>`

Rolling buffer of (ts_ms, price)；`(current_price - price_at_lookback) / price_at_lookback`；buffer 容量按 lookback 最大值配置（建議 2s = 2000ms 可覆蓋所有合理 ROC 窗口）。

---

## 測試

- `database/exit_feature_writer.rs` 單測：msg round-trip / NaN sanitize / fallback switch / ON CONFLICT upsert
- `paper_state.rs` 單測：
  - close 觸發寫 ExitFeatureRow（+≥3 test cases：long win / short win / stop_loss）
  - `max_favorable_pnl_pct` 追蹤（tick → peak → giveback 三階段）
  - `peak_reached_ts_ms` 邊界（entry 即 peak / peak 後 drawdown / 反覆創新高）
- `price_tracker` 單測：`compute_roc` 邊界（lookback > buffer, lookback = 0, symbol 無歷史）
- Integration test：三個 pipeline（Paper/Demo/Live）各關一倉，DB 看到 3 rows

預估 15-20 新單測。

---

## Migration / 部署順序

1. 寫 V_YYYYMMDD 遷移 + apply 到 docker PG
2. 加 Rust 代碼（LearningMsg variant、writer、tasks.rs、EventConsumerDeps）
3. `paper_state.rs` 加欄位 + 寫入 hook
4. `price_tracker.rs` 加 compute_roc
5. E2 + E4 + E5
6. `restart_all.sh --rebuild` 部署
7. 觀察 24h：DB `learning.exit_features` 有 rows 來自所有 active pipeline

**與 Phase 1a 的時序關係**：
- EXIT-FEATURES-TABLE-1 schema DDL + writer 骨架 **Phase 1a 可做**（不阻塞 P1-7 A/B/C）
- `paper_state.rs` 新欄位 + 寫入 hook 是 **Phase 1a 軌道 1** 的一部分
- 資料累積 **Phase 1b 全週**
- 7 維閾值 calibrate + Track P rule bind **Phase 1b 末**

---

## 預估工作量

| 項目 | 行數 | 時間估計 |
|---|---|---|
| Migration SQL | ~50 | 30 min |
| `ExitFeatureRow` + `LearningMsg::ExitFeature` | ~60 | 1h |
| `exit_feature_writer.rs` | ~250（mirror decision_feature_writer）| 3h |
| `tasks.rs` + `EventConsumerDeps` wiring | ~40 | 1h |
| `paper_state.rs` 新欄位 + tracking + write hook | ~100 | 2h |
| `price_tracker.rs` `compute_roc` | ~60 | 1h |
| 單測（15-20） | ~400 | 4h |
| E2/E4/E5 | — | 2h |
| **合計** | **~960 行** | **~14h（1.75 工作日）** |

---

## 風險

1. **Legacy positions migration**：重啟時恢復的 positions 無 peak tracking 歷史。預設 `peak_reached_ts_ms = opened_ts_ms` 會讓 `time_since_peak_ms` 初始值偏大，首次真實 tick 後修正。
2. **Schema drift**：`feature_schema_hash` 強制每次 schema 改動 bump version；訓練端以 hash 匹配。
3. **Partition growth**：每筆 exit 一 row，demo 每日 ~1k exits → 年增 ~365k rows 可控；TimescaleDB 7d chunk + 可加 retention policy（90d compression / 1y drop）到 V006 timescale_policies 遷移。
4. **realized_net_bps 計算時序**：exit 當下算得出（entry/exit 價 + fee），不需 backfill。decision_outcomes 的問題（需要 N-minute forward 等待）在 exit_features 不存在。
