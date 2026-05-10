# W-AUDIT-8a Phase B Tier 2 Panel Collector Spec — Sprint N+1 W1 PA Spec Phase v1

**Author**: PA (project architect)
**Date**: 2026-05-10
**Phase**: W1 Spec phase Day 1-2 — PA W1-spec deliverable（BB B-3 rate-limit budget review 並行；D+1 PA + BB final review）
**Scope**: Sprint N+1 W1 W-AUDIT-8a Phase B Tier 2 panel collector — funding_curve writer (B-1) + oi_delta_panel writer (B-2) + AlphaSurface consumer 驗收 (B-4)。Spec 拍板後直接派 W1 IMPL E1 sub-agent；D+5-D+6 land + E2/E4 review。
**Reference dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.1 W1
**Reference trait coord**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md`
**Reference trait skeleton commit**: HEAD `c9fb0b8f` (PA D+0 land — `FundingCurveSnapshot` + `OIDeltaPanel` typedef + `AlphaSurface.{funding_curve,oi_delta_panel}` field + slot insertion anchors)
**Reference alpha surface**: `srv/docs/execution_plan/2026-05-09--w_audit_8a_alpha_surface_foundation_spec.md` §2.3 Tier 2.1 / 2.3

---

## §1 Background + Scope

### 1.1 Why W1 Phase B now

W-AUDIT-8a Phase A 已 land 全 4 Tier struct typedef + `Strategy::on_tick(ctx, surface)` 接口升級（HEAD `b6ed4975`）。Phase A 階段 `AlphaSurface.funding_curve` / `AlphaSurface.oi_delta_panel` 永遠 `None`（trait 預留 field 但 caller 不 wire）。bb_breakout 已 declare `OiDeltaPanel` tag (`mod.rs:295-300`) 但 silent fallback（surface.oi_delta_panel = None → skip）。

W1 Phase B 的目標：把 `funding_curve` + `oi_delta_panel` 從 stub typedef 升級為**真實 wire panel**。Producer = Python writer pulls Bybit V5 endpoint → 寫 PG `panel.*` table；Consumer = Rust IPC slot pull latest snapshot → `step_4_5_dispatch` 構造 `AlphaSurface` borrow → Strategy `on_tick` 真實消費。

bb_breakout 在 W1 land 後**真實 consume `OiDeltaPanel`**；OI panel unavailable 時 fail-closed 寫 `evaluation_outcome='oi_panel_unavailable'` 入 `learning.decision_features_evaluations`（V082），**不再 silent dormant**。對齊 P1-BB-BREAKOUT-FAIL-CLOSED-1 (dispatch v3.3 §3.5)。

### 1.2 W1 Scope

| 子任務 | Owner E1 | 範圍 |
|---|---|---|
| **B-1** | E1-α | funding_curve writer + V085 + Rust `FundingCurvePanelSlot` + dispatch wire |
| **B-2** | E1-β | oi_delta_panel writer + V087 + Rust `OIDeltaPanelSlot` + dispatch wire |
| **B-3** | BB sub-agent (並行) | Bybit V5 rate-limit budget review；output 給本 spec D+1 final review |
| **B-4** | E1-γ | AlphaSurface consumer 驗收：bb_breakout `OiDeltaPanel` 真實 consume + fail-closed 寫 `oi_panel_unavailable` |

**out of scope**：basis_curve（Tier 2.2 Bybit demo 不支援 spot lending，fence by ADR-0018）、Tier 3 Microstructure、Tier 4 Information flow。

### 1.3 W1 vs W2 對比

| 維度 | W1 (Phase B Tier 2 panel) | W2 (A4-C BTC→Alt Lead-Lag) |
|---|---|---|
| Engine mode | demo + live_demo + live | **paper-only**（fence by `step_4_5_dispatch.rs` engine_mode gate）|
| Rationale | Phase B 是 production foundation；funding/OI 是 well-known signal，無 paper-only 理由 | A4-C 是 fast-track exploration；7d paper edge gate 才升 demo |
| Consumer | bb_breakout 真 consume + 5 策略可選 declare | ma_crossover + grid_trading shadow log only（C-IMPL-3 不直接 trade）|
| Edge gate | 無（直接接 production；evidence 由 healthcheck `[40]` realized_edge 觀察）| ≥ +5 bps paper avg_net 才 promote N+2 demo |

---

## §2 B-1 funding_curve writer Spec

### 2.1 Bybit V5 Endpoint + Rate Budget

**Primary endpoint**: `GET /v5/market/tickers?category=linear&symbol={SYMBOL}` — 含 `fundingRate` + `nextFundingTime` field（per `layer2_tools_g3_07.py:312-314` 既有 pattern）。

**Alternative**: `GET /v5/market/funding/history?category=linear&symbol={SYMBOL}&limit=1` — 純 funding history（不含 next_funding_time）。

**選擇**：用 `tickers` endpoint。一次 GET 拿 funding rate + next_funding_time + 其他 ticker field（mark_price / index_price 給未來 W-AUDIT-8c basis 預留）。

**Rate budget（待 BB B-3 final）**：
- Bybit V5 public endpoint rate limit: ~600 req/min per IP（`tickers` 是 public，無簽名）
- 25 symbol × 1 req per 60s = 25 req/min → **4.2% budget**
- 安全緩衝：B-3 BB review 確認 production traffic 無其他 caller 用此端點搶 budget

**Cohort 25 symbol**（per W2 spec §2.2 + Phase B production scope）：
- Active strategy 25-symbol union：grid_trading active set ∪ ma_crossover active set ∪ bb_breakout active set
- 動態源：讀 `strategy_params_demo.toml` + `strategy_params_live.toml` 取 active=true 策略的 `symbols` 並 union
- **Excluded**：BUSDT (ADR-0018 funding_arb retire)、`strategy_blocked_symbols_freeze.json` 列入的 BSBUSDT / PRLUSDT / ZBTUSDT / FARTCOINUSDT 等
- W1 IMPL 期間 cohort 固定 25 個 hardcoded snapshot（D+0 PM 確認最終 list）；後續 W-AUDIT-8c generic 跨資產 panel 再做 dynamic cohort discovery

### 2.2 PG Table V085 Schema

```sql
-- V085__funding_rates_panel.sql
-- W-AUDIT-8a Phase B Tier 2.1 funding curve panel
-- 對齊 srv/rust/openclaw_core/src/alpha_surface.rs:127-140 FundingCurveSnapshot

CREATE SCHEMA IF NOT EXISTS panel;

CREATE TABLE IF NOT EXISTS panel.funding_rates_panel (
    snapshot_ts_ms     BIGINT      NOT NULL,
    symbol             TEXT        NOT NULL,
    funding_rate_bps   DOUBLE PRECISION NOT NULL,
    next_funding_ms    BIGINT      NOT NULL,
    source_tier        TEXT        NOT NULL DEFAULT 'bybit_v5_public',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

-- Guard A: 既存表 schema 對齊驗證（per CLAUDE.md §七 Guard A）
-- Guard B: 型別敏感欄位 ADD COLUMN 前驗 data_type（本 wave 全新表，N/A）
-- Guard C: hot-path 索引選用 pg_get_indexdef() 比對

-- TimescaleDB hypertable, 1d chunk
SELECT create_hypertable(
    'panel.funding_rates_panel',
    'snapshot_ts_ms',
    chunk_time_interval => 86400000,
    if_not_exists => TRUE
);

-- Retention 14d
SELECT add_retention_policy(
    'panel.funding_rates_panel',
    INTERVAL '14 days',
    if_not_exists => TRUE
);

-- Hot-path index: 最新 N 秒 snapshot lookup
CREATE INDEX IF NOT EXISTS idx_funding_panel_ts_desc_symbol
    ON panel.funding_rates_panel (snapshot_ts_ms DESC, symbol);
```

**Schema 對齊 trait field**（critical）：
- `funding_rate_bps` (DOUBLE PRECISION) → `FundingCurveSnapshot.funding_rates_bps: Vec<f64>`
- `next_funding_ms` (BIGINT) → `FundingCurveSnapshot.next_funding_ms: Vec<i64>`
- `snapshot_ts_ms` (BIGINT) → `FundingCurveSnapshot.snapshot_ts_ms: i64`
- `source_tier` (TEXT) → `FundingCurveSnapshot.source_tier: String`
- 25 row per snapshot_ts_ms（每 symbol 一 row）；Rust IPC slot pull 時 GROUP BY 最新 snapshot_ts_ms 構造 Vec 並對齊 `symbols[i]`

### 2.3 Python Writer

**File**: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/funding_curve_writer.py`

**Pattern**（既有 `layer2_tools_g3_07.py:298-380` httpx + Bybit envelope parsing pattern）：

```python
async def funding_curve_writer_loop(stop_event: asyncio.Event) -> None:
    """W-AUDIT-8a Phase B B-1 funding curve panel writer.

    每 60s 拉一次 25-symbol cohort funding rate + next_funding_time，
    寫 panel.funding_rates_panel。Cohort = grid_trading ∪ ma_crossover ∪
    bb_breakout active=true symbols（已 exclude BUSDT + frozen list）。
    """
    cohort = _load_cohort_symbols()  # 25 symbol from active strategy params
    cycle_interval_s = 60
    while not stop_event.is_set():
        cycle_start_ts = int(time.time() * 1000)
        snapshot_rows = []
        for symbol in cohort:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(
                        f"{bybit_public_base_url()}/v5/market/tickers",
                        params={"category": "linear", "symbol": symbol},
                    )
                if resp.status_code != 200:
                    logger.warning(f"funding_curve_writer: {symbol} HTTP {resp.status_code}")
                    continue
                data = resp.json()
                if data.get("retCode") != 0:
                    continue
                ticker = data["result"]["list"][0]
                snapshot_rows.append({
                    "snapshot_ts_ms": cycle_start_ts,
                    "symbol": symbol,
                    "funding_rate_bps": float(ticker["fundingRate"]) * 10000,
                    "next_funding_ms": int(ticker["nextFundingTime"]),
                    "source_tier": "bybit_v5_public",
                })
            except Exception as e:
                logger.warning(f"funding_curve_writer: {symbol} {e}")
                continue
        # Batch write 25 rows
        if snapshot_rows:
            await _batch_insert(snapshot_rows)
        # Wait remainder of cycle
        elapsed = (int(time.time() * 1000) - cycle_start_ts) / 1000
        await asyncio.sleep(max(0, cycle_interval_s - elapsed))
```

**Spawn point**：`main_legacy.py` startup hook（既有 grafana_data_writer spawn 同 pattern）。

**Failure modes**：
- 單 symbol HTTP fail → `continue` skip，不阻塞其他 symbol
- 整 cycle 0 row → log WARN，下一 cycle 再試
- DB insert fail → log ERROR，不 raise
- Stop event set → graceful exit

### 2.4 Rust IPC Slot

**File**: `srv/rust/openclaw_engine/src/ipc_server/slots.rs`（PA D+0 已預留 anchor `// === W1 FundingCurvePanelSlot insertion point ===` line 170）

```rust
/// W-AUDIT-8a Phase B B-1: late-injected slot for FundingCurveSnapshot panel.
///
/// MODULE_NOTE (中)：funding_curve panel collector spawn 在 IPC server detach
///   後（Python writer 寫 PG → Rust 端 puller 拉 PG）。Slot 用
///   `Arc<RwLock<Option<FundingCurveSnapshot>>>` 讓 main.rs late-inject。
///   None = uninitialized，dispatch step_4_5 取 None → surface.funding_curve
///   = None → declared 此 tag 的策略 fail-closed 寫
///   evaluation_outcome='funding_panel_unavailable'。
pub type FundingCurvePanelSlot =
    Arc<RwLock<Option<crate::alpha_surface::FundingCurveSnapshot>>>;
```

**Puller**：另一新模組 `panel_puller.rs`（W1 IMPL 留 E1）— 每 30s 從 PG 拉最新 snapshot_ts_ms 對應 25 row → 構造 `FundingCurveSnapshot` → write slot Some。Latest snapshot age 由 `snapshot_ts_ms` 決定。

### 2.5 step_4_5_dispatch wire

**File**: `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`（PA D+0 已預留 anchor）

```rust
let funding_curve_snapshot = self.funding_curve_slot.read().await.clone();
let funding_curve = funding_curve_snapshot.as_ref();  // Option<&FundingCurveSnapshot>

let surface = AlphaSurface {
    // ... existing fields ...
    funding_curve,
    // ... oi_delta_panel: 同模式（B-2 加） ...
};
```

**Freshness gate**：W1 簡化版 — Puller 拉時若 latest snapshot_ts_ms 距 now > 300s（FAIL threshold）→ 寫 None，不寫 stale snapshot。30s WARN threshold 留 healthcheck `[57]`（新加 funding_curve_panel_freshness check）監測。

---

## §3 B-2 oi_delta_panel writer Spec

### 3.1 Bybit V5 Endpoint + Rate Budget

**Primary endpoint**: `GET /v5/market/open-interest?category=linear&symbol={SYMBOL}&intervalTime={5min|15min|1h}&limit=1`（per `layer2_tools_g3_07.py:316-323` 既有 pattern）。

**三檔 interval 同步拉**：5min / 15min / 1h 三個 interval 各一個 GET，每 symbol 共 3 GET。

**Rate budget（待 BB B-3 final）**：
- 25 symbol × 3 interval × 1 req per 60s = 75 req/min → **12.5% budget**
- 加 funding_curve B-1 共 100 req/min → **16.7% budget**
- 安全緩衝：B-3 BB review 確認 production 無其他 caller 搶 budget；若超 → 30s cycle interval 改 90s

### 3.2 PG Table V087 Schema

```sql
-- V087__oi_delta_panel.sql
-- W-AUDIT-8a Phase B Tier 2.3 OI delta panel
-- 對齊 srv/rust/openclaw_core/src/alpha_surface.rs:164-175 OIDeltaPanel
-- 注意：trait field 是 5m/15m/1h（NOT 1m/5m/15m）

CREATE SCHEMA IF NOT EXISTS panel;

CREATE TABLE IF NOT EXISTS panel.oi_delta_panel (
    snapshot_ts_ms      BIGINT       NOT NULL,
    symbol              TEXT         NOT NULL,
    oi_delta_5m_pct     DOUBLE PRECISION,  -- nullable: 5m window 不足
    oi_delta_15m_pct    DOUBLE PRECISION,
    oi_delta_1h_pct     DOUBLE PRECISION,
    oi_abs              DOUBLE PRECISION NOT NULL,
    source_tier         TEXT         NOT NULL DEFAULT 'bybit_v5_public',
    PRIMARY KEY (snapshot_ts_ms, symbol)
);

SELECT create_hypertable(
    'panel.oi_delta_panel', 'snapshot_ts_ms',
    chunk_time_interval => 86400000, if_not_exists => TRUE
);
SELECT add_retention_policy(
    'panel.oi_delta_panel', INTERVAL '14 days', if_not_exists => TRUE
);
CREATE INDEX IF NOT EXISTS idx_oi_panel_ts_desc_symbol
    ON panel.oi_delta_panel (snapshot_ts_ms DESC, symbol);
```

**Schema 對齊 trait field**（critical, **schema 與 task scope 描述不一致已校正**）：
- task scope 寫 `oi_delta_1m / 5m / 15m`，但 trait 定義是 `oi_delta_5m_pct / 15m_pct / 1h_pct`（per `alpha_surface.rs:164-175`）。spec **以 trait 為準**。
- 1m delta 不需要：1m 噪音太高，5m/15m/1h 才是 informational tier。
- `oi_abs` (DOUBLE PRECISION) → `OIDeltaPanel.oi_abs: Vec<f64>`

### 3.3 Python Writer

**File**: `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/oi_delta_panel_writer.py`

**Pattern**（同 §2.3 funding_curve_writer + 三 interval 並行）：

```python
async def oi_delta_panel_writer_loop(stop_event: asyncio.Event) -> None:
    cohort = _load_cohort_symbols()
    cycle_interval_s = 60
    while not stop_event.is_set():
        cycle_start_ts = int(time.time() * 1000)
        snapshot_rows = []
        for symbol in cohort:
            try:
                # 三 interval 並行拉
                async with httpx.AsyncClient(timeout=5.0) as client:
                    tasks = [
                        client.get(f"{bybit_public_base_url()}/v5/market/open-interest",
                                   params={"category": "linear", "symbol": symbol,
                                           "intervalTime": iv, "limit": 2})
                        for iv in ("5min", "15min", "1h")
                    ]
                    responses = await asyncio.gather(*tasks, return_exceptions=True)
                # parse 三 response 算 delta = (latest - prev) / prev * 100
                deltas = {}
                for iv_label, resp in zip(("5m", "15m", "1h"), responses):
                    if isinstance(resp, Exception) or resp.status_code != 200:
                        deltas[iv_label] = None
                        continue
                    data = resp.json()
                    if data.get("retCode") != 0:
                        deltas[iv_label] = None
                        continue
                    rows = data["result"]["list"]
                    if len(rows) < 2:
                        deltas[iv_label] = None
                        continue
                    latest = float(rows[0]["openInterest"])
                    prev = float(rows[1]["openInterest"])
                    deltas[iv_label] = (latest - prev) / prev * 100 if prev > 0 else None
                    if iv_label == "5m":
                        oi_abs = latest
                snapshot_rows.append({
                    "snapshot_ts_ms": cycle_start_ts,
                    "symbol": symbol,
                    "oi_delta_5m_pct": deltas["5m"],
                    "oi_delta_15m_pct": deltas["15m"],
                    "oi_delta_1h_pct": deltas["1h"],
                    "oi_abs": oi_abs,
                    "source_tier": "bybit_v5_public",
                })
            except Exception as e:
                logger.warning(f"oi_delta_panel_writer: {symbol} {e}")
                continue
        if snapshot_rows:
            await _batch_insert(snapshot_rows)
        elapsed = (int(time.time() * 1000) - cycle_start_ts) / 1000
        await asyncio.sleep(max(0, cycle_interval_s - elapsed))
```

### 3.4 Rust IPC Slot + Dispatch

**File**: `slots.rs`（PA D+0 anchor `// === W1 OIDeltaPanelSlot insertion point ===` line 174）

```rust
pub type OIDeltaPanelSlot =
    Arc<RwLock<Option<crate::alpha_surface::OIDeltaPanel>>>;
```

**step_4_5_dispatch wire** 同 §2.5 pattern（OPanel struct vs FundingCurveSnapshot 差異僅 type）。

**Freshness gate**：30s WARN / 300s FAIL（同 funding_curve）。

---

## §4 B-4 AlphaSurface Consumer 驗收（bb_breakout fail-closed）

### 4.1 bb_breakout 真實 consume `OiDeltaPanel`

**Current state**: bb_breakout 已 declare `OiDeltaPanel` tag (`mod.rs:295-300`)，但 `on_tick` 內**未真實 consume `surface.oi_delta_panel`**——還在用既有 `oi_buffer` per-symbol 自己 maintain 的 OI 序列。

**W1 land 後 IMPL**（B-4 E1-γ）：
- bb_breakout `on_tick` 加 `surface.oi_delta_panel` 真實 consume 邏輯
- 用 `oi_delta_5m_pct[i]` / `oi_delta_15m_pct[i]` 替代部分 internal buffer
- internal `oi_buffer` 保留作 fallback（panel unavailable 時 degrade）→ 留 W-AUDIT-8d 才完全移除

### 4.2 Fail-closed 寫 `oi_panel_unavailable`

**觸發 condition**：
1. `surface.oi_delta_panel.is_none()` — slot 未初始化或 puller stale > 300s
2. `surface.oi_delta_panel.is_some()` 但 `symbols` Vec 不含當前 tick 的 symbol — cohort drift
3. `surface.oi_delta_panel.is_some()` 但對應 symbol 的 `oi_delta_5m_pct` is NaN — Bybit endpoint 短暫 404

**處理**：
- bb_breakout `on_tick` early return 不 emit `StrategyAction`
- 寫 `learning.decision_features_evaluations` row：
  - `evaluation_outcome = 'oi_panel_unavailable'`（V082 enum 加新值；E2 review 必檢 V082 enum 列表）
  - `evidence_source_tier = 'panel_fail_closed'`
  - `strategy_name = 'bb_breakout'`
  - `symbol`, `engine_mode`, `ts_ms`
- 不 fallback to internal `oi_buffer`（fail-closed semantics）

**對齊 P1-BB-BREAKOUT-FAIL-CLOSED-1**：dispatch v3.3 §3.5 P1 list 已預留此 ticket；W1 land 同步 close。

### 4.3 5 策略 declare 表（B-4 E1-γ 必確認）

| Strategy | Phase A declared | W1 land 後 declared | W1 真實 consume? |
|---|---|---|---|
| ma_crossover | `[Ta1m]` | 不變（Phase A 留 W2 加 `CrossAsset`） | NO |
| grid_trading | `[Ta1m]` | 不變（W2 加 `CrossAsset`） | NO |
| bb_breakout | `[Ta1m, Ta5m, OiDeltaPanel]` | 不變 | **YES (B-4)** |
| bb_reversion | `[Ta1m, Ta5m]` | 不變 | NO |
| funding_arb | `[Ta1m]`（已 retire by ADR-0018） | 不變（active=false 但 trait declare 保留） | NO（active=false） |

W1 不擴 declare scope；ma_crossover / grid_trading 加 `CrossAsset` 在 W2 IMPL；bb_reversion 加 `OiDeltaPanel` 留 W-AUDIT-8d 評估。

---

## §5 B-3 Bybit V5 Rate-Limit Budget（BB sub-agent 並行）

**Out of PA scope**；BB sub-agent 並行跑 D+1 deliverable。BB review 出 final 後 PA 整合本 spec §2.1 + §3.1 budget table。

**BB review checklist**（PA dispatch BB 用）：
- 25 symbol × 1 funding_curve req/60s = 25 req/min → 確認 4.2% budget 可承受
- 25 symbol × 3 OI interval × 1 req/60s = 75 req/min → 確認 12.5% budget 可承受
- 加總 100 req/min → 16.7% production budget；確認無其他 production caller（grafana_data_writer / market_regime / layer2_tools_g3_07 / live_session_endpoints）撞 budget
- 若超 → 推薦 cycle interval 改 90s（保險到 120s）
- 若 Bybit V5 文檔顯示 funding/OI rate limit 與 tickers 不同（per-endpoint quota）→ BB output 給最終 limit number

---

## §6 Sub-agent 分工 + 衝突避撞

**核心策略**：PA D+0 trait skeleton + slots.rs / step_4_5_dispatch.rs anchor 已 land（HEAD `c9fb0b8f`）。W1 三個 E1 sub-agent **完全並行 0 file 重疊**。

| Sub-agent | Files (不重疊) | 關鍵交付 |
|---|---|---|
| **W1 E1-α (B-1)** | `app/funding_curve_writer.py` (新) + `sql/migrations/V085__funding_rates_panel.sql` (新) + `slots.rs` (在 anchor `// === W1 FundingCurvePanelSlot insertion point ===` 下方加 `FundingCurvePanelSlot` typedef) + `tick_pipeline/on_tick/step_4_5_dispatch.rs` (在對應 anchor 下方加 surface.funding_curve assignment) + `panel_puller.rs` (新) + `main.py` writer spawn hook + `passive_wait_healthcheck.py` 加 `check_57_funding_curve_panel_freshness()` | 25-symbol funding rate panel writes PG + Rust slot pull + surface field populated + healthcheck [57] PASS |
| **W1 E1-β (B-2)** | `app/oi_delta_panel_writer.py` (新) + `sql/migrations/V087__oi_delta_panel.sql` (新) + `slots.rs` (anchor `// === W1 OIDeltaPanelSlot insertion point ===` 下方加 `OIDeltaPanelSlot` typedef) + `step_4_5_dispatch.rs` (對應 anchor) + `panel_puller.rs` (B-1 已建則加 OI puller fn) + `main.py` writer spawn hook + `passive_wait_healthcheck.py` 加 `check_58_oi_delta_panel_freshness()` | 25-symbol OI delta panel writes PG + Rust slot pull + surface field populated + healthcheck [58] PASS |
| **W1 E1-γ (B-4)** | `bb_breakout/mod.rs` `on_tick` 真實 consume `surface.oi_delta_panel` + fail-closed evaluation_outcome 寫入 + `sql/migrations/V086__decision_features_evaluations_oi_unavailable_outcome.sql` (新；V082 evaluation_outcome enum 加 `'oi_panel_unavailable'` value via Guard A 對齊 check) | bb_breakout 真實 consume + fail-closed lineage 完整 + V082 enum 對齊 |

**衝突點全部消除**：
- `slots.rs` E1-α + E1-β 各加 typedef，PA D+0 anchor 隔離；E1-γ 不動 slots.rs
- `step_4_5_dispatch.rs` E1-α + E1-β 各加 surface field assignment，anchor 隔離；E1-γ 不動 dispatch
- V### migration 編號 V085 / V086 / V087 預先 reserved；V088 留 W2 BtcLeadLagPanel
- `panel_puller.rs` E1-α 先建 framework，E1-β 加 OI puller fn（同 file 但不同 fn，git merge 友善）；如 E1-α / E1-β D+3-D+5 並行寫，PA dispatch 時要求 E1-β 等 E1-α push 後才 pull rebase
- `passive_wait_healthcheck.py` E1-α + E1-β 各加 `check_57_*` / `check_58_*` 不同 fn；可同 commit cycle 內合併

**E2 重點審查 3 點**：
1. **V085 / V087 schema 對齊 trait struct field**（critical）：grep `funding_rate_bps`（NOT `funding_rate`）+ grep `oi_delta_5m_pct / 15m_pct / 1h_pct`（NOT `1m / 5m / 15m`）。schema 與 trait 名稱嚴格匹配，否則 Rust IPC slot pull 解 PG row 構造 `FundingCurveSnapshot` / `OIDeltaPanel` 會 NULL 失敗。
2. **V086 V082 enum 對齊**：bb_breakout 寫 `evaluation_outcome='oi_panel_unavailable'` 必須在 V082 enum 列表內。E2 grep V086 是否 ADD value to V082 evaluation_outcome enum check + 是否 backward-compat（既有 row 不變）。Guard A 必驗 enum 已存在則 NO-OP。
3. **bb_breakout fail-closed 路徑無 silent fallback**：grep `bb_breakout/mod.rs` `on_tick` 內 `if surface.oi_delta_panel.is_none()` 路徑必走 fail-closed（write evaluation + early return），**禁止 fallback to internal `oi_buffer`**。internal buffer 保留 W-AUDIT-8d 處理。

---

## §7 Risk + 16 原則合規

### 7.1 Backward compat
- `FundingCurveSnapshot` / `OIDeltaPanel` struct typedef 在 Phase A 已 land；W1 不改 struct shape，只 wire producer
- `AlphaSurface.{funding_curve, oi_delta_panel}` field 在 Phase A 已存在；W1 從 None → Some
- bb_breakout `on_tick` 加新邏輯但保留 `oi_buffer` fallback 路徑（暫時，留 W-AUDIT-8d 完全移除），**不 break existing test**
- E4 regression：5 策略全 retest + bb_breakout 跑 demo 24h surface.oi_delta_panel = Some 路徑 + paper engine 跑 surface.oi_delta_panel = None 路徑（fail-closed evaluation_outcome 寫入驗）

### 7.2 16 原則合規（CLAUDE.md §二 + skill checklist）

| # | 原則 | W1 影響 | 狀態 |
|---|---|---|---|
| 1 | 單一寫入口 | panel writer 只寫 `panel.*` schema；不寫 trading 路徑 | ✅ |
| 2 | 讀寫分離 | producer 寫 PG，consumer 讀 PG（slot pull）；無 GUI 寫入 | ✅ |
| 3 | AI 輸出 ≠ 命令 | bb_breakout 用 panel data 計算 signal，仍走 SM-04 Guardian | ✅ |
| 4 | 策略不繞風控 | bb_breakout intent 仍經 Guardian；fail-closed 是 pre-Guardian gate | ✅ |
| 5 | 生存 > 利潤 | OI panel unavailable → fail-closed 不開新倉 | ✅ |
| 6 | 失敗默認收縮 | panel stale > 300s → slot None → fail-closed | ✅ |
| 7 | 學習 ≠ 改寫 Live | panel data 寫 `panel.*` 學習平面；live 路徑只讀 | ✅ |
| 8 | 交易可解釋 | `evaluation_outcome='oi_panel_unavailable'` lineage 完整 | ✅ |
| 9 | 災難保護 | bb_breakout existing hard_stop / trailing 不變 | ✅ |
| 10 | 認知誠實 | spec 區分「BB B-3 review pending」+「task scope 校正：5m/15m/1h NOT 1m/5m/15m」 | ✅ |
| 11 | Agent 最大自主 | bb_breakout 在 P0/P1 內完全自主 | ✅ |
| 12 | 持續進化 | OI panel 為策略提供新 alpha source；evaluation_outcome 為 ML training data | ✅ |
| 13 | AI 成本感知 | panel writer 是 free public endpoint，無 AI 成本 | ✅ |
| 14 | 零外部成本可運行 | Bybit V5 public endpoint 免費 | ✅ |
| 15 | 多 Agent 協作 | bb_breakout 真實 consume，5 Agent 通信不變 | ✅ |
| 16 | 組合級風險 | 25-symbol cohort funding/OI panel 提供組合視角 | ✅ |

### 7.3 DOC-08 §12 9 條安全不變量
本 wave **不動** lease / authorization / audit / reconciler / mainnet env / Bybit retCode / fail-closed semantic / live_reserved 任何路徑 → 全 9 條不變量無關 → ✅

### 7.4 硬邊界 5 項
本 wave **不動** `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease_emitted` / `authorization.json` → 全 5 項無關 → ✅

### 7.5 已知 risk + 緩解

| Risk | 等級 | 緩解 |
|---|---|---|
| Bybit V5 rate budget 超限 → throttle | 中 | BB B-3 review final + cycle interval 60s→90s fallback |
| V082 evaluation_outcome enum 加 `oi_panel_unavailable` 破既有 query | 低 | V086 ADD VALUE TO ENUM IF NOT EXISTS + Guard A 驗對齊 |
| bb_breakout 真實 consume 後 demo edge 變化（向上或向下） | 中 | E4 regression demo 24h baseline 對比 + 4-agent loss audit framework 可重跑 |
| panel_puller stale snapshot > 300s 但 slot 未及時 None | 中 | freshness check 在 puller 內，每 30s 自檢；healthcheck [57]/[58] 監測 |
| schema field name 不對齊 trait struct field（task scope 已校正） | **極高** | E2 強制 grep verify；本 spec §2.2 §3.2 已明確列名 |

---

## §8 D+1 PA + BB Final Review Checklist

D+1 BB B-3 deliverable 出後，PA 整合本 spec：
1. §2.1 + §3.1 rate budget table 替換 BB 確認 number
2. 若 BB 推薦 cycle interval 改 90s → §2.3 + §3.3 writer code 更新
3. §6 sub-agent dispatch 派 W1 E1-α + E1-β + E1-γ
4. 通知 PM 本 spec final 後 push commit + 派發 W1 IMPL

---

## §9 一句總結

**W1 IMPL 範圍縮為 producer (Python writer + V### + Rust slot puller) + dispatch wire (anchor 下方加 1 line) + bb_breakout 真實 consume + fail-closed evaluation_outcome lineage；trait shape 0 改動（PA D+0 已 land HEAD `c9fb0b8f`）；schema 對齊 trait field（task scope 已校正 5m/15m/1h NOT 1m/5m/15m + funding_rate_bps NOT scalar funding_rate）；bb_breakout fail-closed 寫 `oi_panel_unavailable` 入 V082 evaluation_outcome enum (V086 ADD VALUE)；3 個 E1 sub-agent 完全並行 0 file 重疊；16 原則 + DOC-08 §12 + 硬邊界 5 項全 0 觸碰；BB B-3 rate budget review 並行 D+1 final integration。**

---

**Spec end. PA W1 next action**: D+1 BB B-3 review out → PA integrate → push spec final → dispatch W1 E1-α/β/γ 三 sub-agent；D+5-D+6 land + E2/E4 review；W1 land 後 ≥ 24h 再進 W3 Stage 1（dispatch v3.3 §5.1 已記）。

PA SPEC DONE: report path: srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md
