# P2-BASIS-PANEL-INFRA — Basis Panel 資料管線 IMPL spec

**Date**: 2026-05-29
**Author**: PA
**Status**: PA DESIGN — IMPL-ready（cheap-derived verdict）
**Scope**: A1 funding_short_v2 candidate Stage 0R 前置 — basis（期現價差）point-in-time 持久化管線
**Trigger**: A1 spec line ~45 entry gate `basis_pct < 0.3%`；A1/A2 Stage 0R runner spec v2 標記 `basis_panel_infra_missing` → A1 BLOCKED draft_only
**Constraint**: design + read-only ssh probe；不 IMPL；leak-free point-in-time writer

---

## §1 資料源可行性裁決 — **CHEAP-DERIVED**（with 1 critical caveat）

### §1.1 Verdict

**CHEAP-DERIVED**，但**非「直接衍生既有 PG column」的最 cheap form**。正確路徑 = **新 panel aggregator + V115 table，basis 由 WS PriceEvent stream 即時衍生計算**（mirror funding_curve / oi_delta pattern）。

理由：basis 的兩個輸入（perp last_price + index_price）**都已在 runtime WS event stream 內**，但**既有 `market.market_tickers` 的持久化值是壞死的（值=0），不能直接 derive**。

### §1.2 已 ingest 什麼（證據）

| 輸入 | runtime 狀態 | 證據 |
|---|---|---|
| **perp last_price** | ✅ 活躍、新鮮、值正確 | `market.market_tickers` 1.3s staleness；WS `tickers.{symbol}` → parser `last_price` → `PriceEvent.last_price` |
| **index_price** | ⚠️ WS stream **有**（snapshot frame），但 PG **持久化壞死** | parser `parsers.rs:254` 解析 `indexPrice` + `.filter(p>0)` → `PriceEvent.index_price: Option<f64>`；in-memory cache `step_4_5_dispatch.rs:180` 只在 `Some(ip)` 時更新 → **strategy 即時路徑可用**；但 PG 寫入路徑 `step_0_fast_track.rs:128` 用 `event.index_price.unwrap_or(0.0)` 逐 frame 寫 → delta frame 無 indexPrice → 寫 0 |
| **mark_price** | ❌ parser 根本不解析（`PriceEvent` 無 `mark_price` field）；PG 寫死 0.0（`step_0_fast_track.rs:127 // not available in PriceEvent yet`） | `price.rs:31-95` PriceEvent 無 mark_price；`market_writer.rs:322` 寫的是 step_0 傳入的 hardcoded 0.0 |

**PG 實證（ssh trade-core，full table 47.7M rows since 2026-04-05）**：
```
index_price>0:  6,142,013 / 47,706,716  (12.9% — 只有 snapshot frame 帶 indexPrice)
mark_price>0:     207,012 / 47,706,716  (0.43% — 實質壞死)
近 2h:         index_price NONNULL 102043/102043 但 BTC/ETH 取樣值全 = 0
basis from market_tickers: NULL（除零，mark=0 index=0）
PG basis table/column: 0 hit（panel schema 只 btc_lead_lag/funding_rates/oi_delta）
```

### §1.3 為何 cheap（非 heavy）

- **不需新增 index price 採集**：index_price 已在 WS `tickers.{symbol}` stream，parser 已解析，`PriceEvent.index_price` 已存在。
- **不需新增 mark price 採集**：basis 定義對齊 strategy 後（見 §2）用 **last vs index**，不需 mark。
- heavy form（需新加 REST `get_index_price_klines` 採集器或新 WS topic）**不適用** — 資料源都已在 hot stream。
- 唯一 infra 缺口 = **point-in-time 持久化層**（A1 Stage 0R 是 offline replay，需歷史 basis 序列，不能靠 in-memory cache）。market_tickers 的 index_price 因 per-frame unwrap_or(0) 壞死，不能 backfill。

### §1.4 Caveat（E2/MIT 必查）

`market.market_tickers` 既有 index_price 87% 為 0、mark_price 99.6% 為 0 是**獨立的潛在 bug**（column exists, value dead — PA memory phantom-expectation 同類陷阱）。本 spec **不修** market_tickers 寫入路徑（超出 A1 unblock scope，且 market_tickers 是 raw tick 表非 panel）；只用「latest-value cache 跨 snapshot frame」pattern 在新 basis_panel 規避此問題。若 future 要 backfill 歷史 basis（2026-04-05 起）→ market_tickers 不可用 → 只能從 land 日起前向累積（明文標記）。

---

## §2 Basis 公式對齊 A1

### §2.1 SSOT 定義（mirror strategy live path，保 replay parity）

A1 strategy live 路徑實算（`funding_short_v2/mod.rs:155` + `funding_arb.rs:89` 同範式）：
```rust
fn compute_basis_pct(perp_price /* = ctx.price = last_price */, index_price: Option<f64>) -> f64 {
    match index_price { Some(ip) if ip > 0.0 => ((perp_price / ip) - 1.0).abs() * 100.0, _ => f64::MAX }
}
```

**權威 basis 定義（panel writer 必逐位對齊）**：
```
basis_pct = (perp_last_price / index_price - 1.0) * 100.0      // 帶符號（signed），單位 %
basis_pct_abs = basis_pct.abs()                                  // strategy gate 用 abs
```
- 分子 = perp `last_price`（**不是 mark_price** — strategy 用 ctx.price=last_price；replay 必須一致否則 Stage 0R basis 與 live 不可比）
- 分母 = `index_price`（Bybit V5 tickers `indexPrice`，現貨指數）
- A1 entry gate `basis_pct < 0.3%` 語意 = **spot-perp premium 絕對值 < 0.3%**（perp 對指數溢價 < 0.3%，防開短時 perp 嚴重升水被 squeeze）
- 單位：% 不是 annualized basis（A1 是 instantaneous premium gate，非年化 carry；與 funding annualized gate 正交）

### §2.2 fail-closed 不變量

- index_price 缺失或 ≤0 → basis = NULL（panel 寫 NULL，consumer fail-closed 跳過）。**不寫 0**（0 會被誤判為「完美無溢價」反而開倉）。對齊 oi_delta NULL→consumer NaN check fail-closed 範式。
- panel 存 signed basis_pct（保留方向資訊供 future 研究），consumer/Stage 0R runner 取 abs 比 gate。

---

## §3 Schema 設計 — `panel.basis_panel`（V115）

### §3.1 Table schema（mirror funding_rates_panel + oi_delta_panel）

```sql
-- V115__panel_basis_panel.sql
-- panel.basis_panel — perp-index basis point-in-time snapshot（A1 funding_short_v2 Stage 0R 前置）
-- basis_pct = (perp_last_price/index_price - 1)*100；signed；NULL = index 缺失 fail-closed
-- mirror panel.funding_rates_panel (V085) + panel.oi_delta_panel (V087) pattern
CREATE TABLE IF NOT EXISTS panel.basis_panel (          -- Guard A
    snapshot_ts_ms   BIGINT            NOT NULL,
    symbol           TEXT              NOT NULL,
    perp_last_price  DOUBLE PRECISION  NOT NULL,         -- 分子（last_price）
    index_price      DOUBLE PRECISION  NOT NULL,         -- 分母（>0 才寫 row）
    basis_pct        DOUBLE PRECISION  NOT NULL,         -- (last/index-1)*100 signed
    source_tier      TEXT              NOT NULL DEFAULT 'bybit_v5_ws_tickers',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);
-- TimescaleDB hypertable（對齊 sister panel 15-chunk pattern）
SELECT create_hypertable('panel.basis_panel', 'snapshot_ts_ms',
    chunk_time_interval => 86400000,                     -- 1d in ms（BIGINT epoch ms 軸）
    if_not_exists => TRUE);
-- hot-path index（Stage 0R as-of LATERAL 用 ts DESC + symbol）
CREATE INDEX IF NOT EXISTS idx_basis_panel_ts_desc_symbol      -- Guard C
    ON panel.basis_panel (snapshot_ts_ms DESC, symbol);
CREATE INDEX IF NOT EXISTS basis_panel_snapshot_ts_ms_idx
    ON panel.basis_panel (snapshot_ts_ms DESC);
```

**設計決策**：
- **不存 mark_price**：basis 用 last vs index（§2.1）；mark 在 stream 不可得且非 basis 定義輸入 → 不引入死 column（避 market_tickers 同錯）。
- **NOT NULL on basis_pct + index_price**：fail-closed 在 writer 端 = index≤0 不寫 row（非寫 NULL row）。比 oi_delta 寫 NULL 更嚴（oi delta 是 window 不足；basis 是 input 缺失 = 該 snapshot 無有效 basis，不該入庫污染 replay as-of lookup）。
- **partition** = `snapshot_ts_ms` BIGINT epoch ms，chunk 1d（對齊 sister panel，hypertable 軸是 ms BIGINT 非 timestamptz）。
- **retention/compression**：mirror sister panel（不在本 migration 設；既有 panel 由統一 retention policy 管 — E1 確認 V085/V087 是否帶 compression policy，相同則複製，無則不加，保 surgical）。
- **engine_mode 隔離**：basis 是 market-data（market truth，非 per-engine fills），與 funding_rates_panel/oi_delta_panel 同 — **無 engine_mode column**（panel 是共享 market 平面，三引擎共讀同一 basis snapshot；對齊 sister panel 0 engine_mode column）。

### §3.2 V115 migration Guard + dry-run

- **Guard A**：`CREATE TABLE IF NOT EXISTS`（已含）
- **Guard B**：本 migration 無 type-sensitive ADD COLUMN（全新表）→ N/A
- **Guard C**：`CREATE INDEX IF NOT EXISTS`（已含）
- **`create_hypertable(if_not_exists => TRUE)`** → idempotent
- **Linux PG empirical dry-run MANDATORY**（per memory `feedback_v_migration_pg_dry_run`）：
  - first-apply PASS ≠ re-apply 安全；**必 double-apply** 驗 idempotency（create_hypertable 在已是 hypertable 的表上 re-run 行為 + IF NOT EXISTS index）
  - Mac mock 抓不到 TimescaleDB `create_hypertable` runtime semantic → 必 `ssh trade-core` 跑 V115 兩次
  - 驗 `_sqlx_migrations` checksum 與 file 一致（避 V028/V055/V114 hash drift 教訓）

---

## §4 Writer 設計 — BasisAggregator（mirror funding_curve）

### §4.1 落點與 pattern

新 `rust/openclaw_engine/src/panel_aggregator/basis.rs`（mirror `funding_curve.rs` ~408 LOC，basis 較簡單 ~250-300 LOC）：

```rust
pub struct BasisAggregator {
    cohort: HashSet<String>,                              // hardcoded cohort（含 BTCUSDT/ETHUSDT）
    latest: HashMap<String, (f64, f64)>,                 // sym → (last_price, index_price) latest known
    db_pool: Arc<DbPool>,
}
impl BasisAggregator {
    // caller-driven，PanelAggregator::run event drain 內呼叫
    pub fn on_ticker_update(&mut self, symbol: &str, last_price: f64, index_price: Option<f64>) {
        if !self.cohort.contains(symbol) { return; }
        // index_price 缺失 → 不更新（保留上一已知 index；對齊 funding_curve latest-value cache）
        // last_price 每 frame 更新；index_price 只在 Some 時更新
        match (self.latest.get(symbol), index_price) {
            (_, Some(ip)) if ip > 0.0 => { self.latest.insert(symbol.into(), (last_price, ip)); }
            (Some(&(_, prev_ip)), None) => { self.latest.insert(symbol.into(), (last_price, prev_ip)); }
            _ => {}                                       // 從未收過 index → 不入 cache（fail-closed）
        }
    }
    pub async fn flush(&mut self, snapshot_ts_ms: i64) -> (usize, usize) {
        // 對 cohort 每 sym：若有 (last, index) 且 index>0 → 計 basis_pct → INSERT
        // index 缺 → skip（不寫 NULL row）
        // ON CONFLICT (snapshot_ts_ms, symbol) DO UPDATE — idempotent
    }
}
```

### §4.2 接線（mirror funding_curve 既有 wire）

- `panel_aggregator/mod.rs`：`PanelAggregator` struct 加 `basis_aggregator: BasisAggregator` field + `basis_mut()` accessor（mirror funding_curve/oi_delta 雙 accessor）。
- `PanelAggregator::run` event drain（mod.rs:334 run loop）：Ticker variant 已 dispatch funding_rate + open_interest，**加一行** `self.basis_aggregator.on_ticker_update(&sym, evt.last_price, evt.index_price)`。
- 60s flush timer arm：加 `self.basis_aggregator.flush(snapshot_ts_ms).await`（與 funding_curve/oi_delta 同 snapshot_ts_ms，60s cadence；FLUSH_INTERVAL_SECS 既有常數）。
- **latest-value cache 是關鍵**：因 index_price 只在 snapshot frame 到（~1/8 frame），cache 跨 frame 保留 last-known index → 每 60s flush 為 cohort 全 sym（收過 ≥1 index snapshot 者）寫一 row。完全對齊 funding_curve mod.rs:125-130 既有 cache 範式（funding 同樣 sparse）。

### §4.3 leak-free（point-in-time，無 look-ahead）

- basis 是**純 snapshot 計算**：`(last_price_at_t / index_price_at_t - 1)`，無 rolling window、無 shift、無未來 bar。結構性無 look-ahead（同 A1 spec §5.1 對 index_price 的論證：即時 snapshot，非 rolling stat）。
- snapshot_ts_ms = flush 時刻（60s boundary）；cache 持的是「該時刻為止的 latest-known」值，**不含未來資訊**。
- ON CONFLICT DO UPDATE：同 snapshot_ts_ms 重 flush 覆寫同值（idempotent，無時序污染）。
- Stage 0R as-of lookup 用 `snapshot_ts_ms <= signal_ts_ms` LATERAL（A1 runner 端責任）→ 嚴格過去，不取未來 basis。Writer 不引入 bias；as-of 正確性在 runner SQL（A1/A2 runner spec v2 已定 LATERAL as-of pattern）。

### §4.4 cohort 一致性（避 self-imposed scarcity，PA memory line 4567 教訓）

- BasisAggregator cohort **必須 ≥ A1 cohort（BTC/ETH）∪ baseline 採樣 cohort**。建議直接用 funding_curve/oi_delta 既有 25-sym cohort（同一 `cohort_symbols` 來源），保 Stage 0R baseline 採樣率對齊，避免 8b round-1 RED（primary n=7 vs baseline n=39181）同類陷阱。
- E1 用 `PanelAggregator::new` 既有 `cohort_symbols` 參數，**不另建 cohort list**（單一 SSOT）。

---

## §5 A1 unblock 路徑

basis_panel land + 累積資料後，A1 Stage 0R runner cohort（現 stub `draft_only(basis_panel_infra_missing)`）接法：

1. **A1 runner SQL（a1_funding_short_metrics.py，per A1/A2 runner spec v2）**：basis as-of LATERAL join 改指 `panel.basis_panel`：
   ```sql
   LEFT JOIN LATERAL (
     SELECT basis_pct FROM panel.basis_panel b
     WHERE b.symbol = f.symbol AND b.snapshot_ts_ms <= f.signal_ts_ms
     ORDER BY b.snapshot_ts_ms DESC LIMIT 1
   ) bp ON TRUE
   ```
   entry gate replay：`ABS(bp.basis_pct) < 0.3`（對齊 A1 spec line 45 `basis_pct < max_basis_pct × entry_basis_ratio = 0.5 × 0.6 = 0.3`）。
2. **stub 解除條件**：runner 偵測 `panel.basis_panel` 有 ≥1 cohort row 覆蓋 replay window → 從 `draft_only(basis_panel_infra_missing)` 轉 runnable；無覆蓋 → 仍 draft_only（標 `basis_data_window_insufficient` 而非 infra_missing，語意精確）。
3. **前向累積限制（明文）**：basis_panel 只能從 land 日前向累積（market_tickers 歷史壞死不可 backfill — §1.4）。A1 Stage 0R 首次有效 replay window = land 後累積期。**這是 cheap-derived 的代價**：不能即時對歷史 funding spike 做 basis-gated replay，需等前向資料。
4. **不影響 A1 strategy live path**：strategy 即時 basis 用 in-memory `index_prices` cache（已可用），basis_panel 純為 offline Stage 0R replay 服務。兩路徑用同一 basis 公式（§2.1）保 parity。

---

## §6 Parallel-complete 可行性裁決 + 工時

### §6.1 裁決：**本 session 可完成 IMPL（cheap-derived，無 heavy infra）**

cheap-derived 成立 → 無需新採集器 → IMPL 範圍 = 1 V### migration + 1 Rust aggregator + wire 3 點。全 Rust + SQL，無 Python/GUI/IPC schema 改動，硬邊界 0 觸碰。可在本 session chain 完成 land。

**但 A1 Stage 0R verdict 本 session 不可達**（§5.3）：basis_panel land 後需前向累積資料，A1 runner 首次有效 replay 在累積期後。本 session 交付 = **infra land + A1 runner SQL 接線（指向 basis_panel）**，A1 Stage 0R 實跑 verdict 是後續（依累積窗，與 candidate demo fills 累積同屬等待期，不阻 infra closure）。

### §6.2 LOC + 工時估

| 切片 | 內容 | LOC | owner |
|---|---|---|---|
| **B-1** | V115 migration（table + hypertable + index + Guard A/C） | ~30 SQL | E1 |
| **B-2** | `basis.rs` BasisAggregator（struct + on_ticker_update + flush + tests）| ~250-300 Rust | E1 |
| **B-3** | `panel_aggregator/mod.rs` wire（field + accessor + run-loop dispatch 1 行 + flush arm 1 行）| ~30-40 Rust | E1 |
| **B-4** | A1 runner SQL 接線（a1_funding_short_metrics.py basis LATERAL 指 basis_panel + stub 解除條件）| ~40-60 Python | E1 / E1b |
| **總計** | | **~350-430 LOC** | |

**工時**：PA design done（本報告）→ MIT V115 PG dry-run（double-apply）~1-2hr → E1 IMPL B-1~B-4 ~3-5hr → E2 review ~1-2hr → E4 regression（cargo test + ssh PG 實寫驗 60s flush 出 row）~1-2hr。**總 ~6-11hr，本 session 可串行 land**（B-2/B-4 可並行：B-2 Rust aggregator 與 B-4 Python runner SQL 文件不重疊；B-1 先行解鎖 B-2 flush 目標表 + B-4 LATERAL 目標表）。

### §6.3 派發計劃

```
PA(本報告) → MIT(V115 PG dry-run double-apply, chain hard gate)
           → E1a: B-1 V115 + B-2 basis.rs + B-3 wire（串行，B-1→B-2→B-3 同一 Rust crate）
           ∥ E1b: B-4 a1_funding_short_metrics.py basis LATERAL（Python，與 E1a 文件 0 重疊，並行）
           → E2 review → E4 regression（ssh PG 實寫驗）→ QA → PM
```
B-4 可與 B-2/B-3 並行（Python vs Rust，零文件衝突；B-4 只依賴 V115 表 schema 確定，MIT dry-run 後即可）。

### §6.4 副作用清單

1. **import 斷裂**：`PanelAggregator` 加 field → 既有 `PanelAggregator::new` caller 需傳 cohort（已有 `cohort_symbols` 參數，0 新增）。grep 確認 `PanelAggregator::new` 唯一 caller（panel_aggregator/mod.rs 自身 + main 接線）。
2. **mock 測試**：basis.rs 自帶 unit test（mirror funding_curve tests）；`PanelAggregator::run` 既有 test（mod.rs:545+）需加 basis dispatch 斷言。無跨模塊 mock 脆弱點（aggregator 是新增，不改既有簽名）。
3. **asyncio/threading**：basis flush 在既有 `PanelAggregator::run` tokio task 內，無新 runtime 邊界。
4. **API schema**：0 改動（panel 不暴露 API；A1 runner 是 offline script）。
5. **Rust↔Python IPC**：0 改動（basis_panel 是 PG 表，A1 runner 直讀 PG，不走 IPC slot）。**注意**：本 spec **不**加 `BasisPanelSlot` IPC slot（funding_curve/oi_delta 有 slot 是因 strategy hot-path 經 AlphaSurface 讀；A1 basis strategy 已用 ctx.index_price 即時算，basis_panel 純為 offline replay → 不需 AlphaSurface slot，省一整套 IPC wire）。

### §6.5 E2 重點審查 3 點

1. **basis 公式 replay parity** — `basis.rs` flush 計算 `(last/index-1)*100` 必與 `funding_short_v2/mod.rs:155` strategy live 公式逐位一致（grep 兩處公式對照）；分子必 = last_price 非 mark_price（否則 Stage 0R 與 live 不可比）。
2. **fail-closed: index≤0 不寫 row** — grep flush 邏輯確認 index_price≤0 / 缺失 → skip（不寫 0、不寫 NULL row）；latest-value cache 確認「從未收過 index 的 sym 不入 cache」（避寫假 basis）。
3. **V115 idempotency** — MIT double-apply 證據必附（create_hypertable re-run + IF NOT EXISTS index + checksum 一致）；確認無 market_tickers 寫入路徑被順手改（surgical，本 spec 不修 market_tickers 壞死 column）。

---

## §7 硬邊界 + 16 原則合規

- **硬邊界 0 觸碰**：basis_panel 是純 market-data 持久化（讀 WS stream 寫 PG），不碰 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / lease / 訂單寫入。
- **原則 1/2（單一寫入口 / 讀寫分離）**：panel writer 是 read-only market-data sink，不寫交易狀態。A1 runner read-only 讀 basis_panel。
- **原則 6（失敗默認收縮）**：index 缺失 → 不寫 row（fail-closed）；consumer 取不到 basis → A1 gate fail-closed 跳過入場。
- **原則 10（認知誠實）**：§1.4（market_tickers 壞死）+ §5.3（前向累積限制）+ §6.1（A1 verdict 本 session 不可達）明文標記為事實邊界，非掩蓋。
- **原則 14（零外部成本）**：basis 全從既有 Bybit WS stream 衍生，無新外部依賴。

---

## §8 References

- A1 spec: `docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md` §1.1 line 45 / §5.1
- A1/A2 Stage 0R runner spec v2: `docs/execution_plan/specs/2026-05-29--a1a2-stage0r-candidate-runner-spec.md`（basis_panel infra gap 標記源）
- sister panel writer pattern: `rust/openclaw_engine/src/panel_aggregator/funding_curve.rs`（V085）+ `oi_delta.rs`（V087）+ `mod.rs`（run loop / cache / flush）
- WS parser: `rust/openclaw_engine/src/ws_client/parsers.rs:254`（indexPrice extract）
- PriceEvent: `rust/openclaw_types/src/price.rs:31`（無 mark_price field）
- market_tickers 壞死寫入路徑: `rust/openclaw_engine/src/tick_pipeline/on_tick/step_0_fast_track.rs:127-128`
- migration latest: V114 → **新 = V115**
- memory: `feedback_v_migration_pg_dry_run`（double-apply mandatory）/ `feedback_indicator_lookahead_bias` / `feedback_new_code_rust_first`

---

**PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/specs/2026-05-29--basis-panel-infra-spec.md`**
