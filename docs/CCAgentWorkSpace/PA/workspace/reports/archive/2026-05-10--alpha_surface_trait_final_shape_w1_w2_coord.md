# AlphaSurface Trait Final Shape — Sprint N+1 W1+W2 並行 IMPL 避撞 Spec

**Author**: PA
**Date**: 2026-05-10
**Scope**: Sprint N+1 W1 (Phase B Tier 2 panel collector) + W2 (A4-C BTC→Alt Lead-Lag) 並行 IMPL 之前對 `srv/rust/openclaw_core/src/alpha_surface.rs` 預先拍板 trait final shape，避免 D+3-D+5 多 E1 sub-agent 同時動同一檔 trait 撞 git merge 衝突。
**Read-only**: 本 report 是 design only，PA D+0 自己 commit trait skeleton；W1/W2 E1 不直接動 trait file 結構，只填 producer / writer 業務邏輯。

---

## §1 現有 trait shape Summary

**File**: `srv/rust/openclaw_core/src/alpha_surface.rs` (505 行，2026-05-10 02:02 land)

W-AUDIT-8a Phase A 已 land 完整 trait + 全 4 Tier struct typedef：

| 區段 | Line range | 已 land 內容 |
|---|---|---|
| `AlphaSourceTag` enum (10 variants) | 43-80 | 含 W2 將用的 `CrossAsset` / W1 將用的 `FundingSkew` + `OiDeltaPanel` |
| Tier 2 stub structs | 110-166 | `FundingCurveSnapshot` (118-131), `BasisCurveSnapshot` (139-148), `OIDeltaPanel` (155-166) **已完整定義 field**，W1 不需新增 type |
| Tier 3 stub structs | 168-232 | `OrderflowFeatures`, `LiquidationPulse` (dormant) |
| Tier 4 stub structs | 234-299 | `EventAlert`, `RegimeTag`, `SentimentPanel` |
| `AlphaSurface<'a>` bundle | 305-338 | 含 `funding_curve` / `basis_curve` / `oi_delta_panel` field — **W1 panel 不需加新 field，只 wire producer 進 None→Some** |
| Constructor + tests | 340-505 | `tier1_only` / `empty()` / `EMPTY_ALPHA_SURFACE` static |

**5 既存策略 declare 樣式**（已在 commit `b6ed4975` 落地）：
- `ma_crossover/strategy_impl.rs:37-40` → `&[Ta1m]`
- `grid_trading/mod.rs:320-322` → `&[Ta1m]`
- `bb_breakout/mod.rs:295-300` → `&[Ta1m, Ta5m, OiDeltaPanel]` (**唯一已 declare Tier 2 tag 的策略**)
- `bb_reversion/mod.rs:338` → `&[Ta1m, Ta5m]` (推測，未實讀)
- `funding_arb.rs:349-352` → `&[Ta1m]` (funding_arb 已 retire by ADR-0018，但 trait declare 仍存)

`Strategy::on_tick(ctx, surface)` 簽名升級已 land (`strategies/mod.rs:96-100`)；`TickContext.alpha_surface_ref: &'a AlphaSurface<'a>` 已 wire (`tick_pipeline/mod.rs:713`)。

---

## §2 3 個新 variant 定義（Rust enum syntax）

W1 + W2 **不新增 enum variant**——`FundingSkew` + `OiDeltaPanel` + `CrossAsset` 已在 `AlphaSourceTag` enum 預留。

但 **W2 BtcAltLeadLag 需要新 panel struct**（`CrossAsset` tag 是 generic family，`BtcAltLeadLag` 是其下第一個具體 panel；MIT 候選 C-1 留 W-AUDIT-8c 真接 generic 跨資產 panel）：

```rust
// ── 新增（PA D+0 trait skeleton）：BTC-Alt 跨資產 lead-lag panel struct ──
//
// 來源（W2 IMPL）：BTCUSDT 1m kline → lead signal（return / volume / orderbook
// imbalance over N=60-300s window）→ Python writer 寫 panel.btc_lead_lag_panel
// （V088 migration；retention 14d）
//
// 範圍（W2 paper-only）：本 wave Strategy 只在 paper engine mode 接此 panel；
// demo / live_demo / live → AlphaSurface.btc_lead_lag = None（fence by
// IntentRouter / Orchestrator，詳 §5）
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BtcLeadLagPanel {
    /// Cohort alt symbols（不含 BTCUSDT）；BUSDT 排除（ADR-0018）
    pub alt_symbols: Vec<String>,
    /// BTC lead signal：N 秒 return（lead window strict shift(N)，禁含 current bar）
    pub btc_lead_return_pct: f64,
    /// BTC lead window seconds（60 / 120 / 300 三檔之一）
    pub lead_window_secs: u32,
    /// 各 alt symbol 對 BTC lead signal 的 cross-correlation（rolling 1h）
    pub alt_xcorr: Vec<f64>,
    /// 各 alt symbol 預期 mean reversion / momentum direction（−1 / 0 / +1）
    pub alt_expected_dir: Vec<i8>,
    pub snapshot_ts_ms: i64,
    pub source_tier: String,
}
```

**AlphaSurface bundle 需加新 field**（PA D+0 trait skeleton 唯一一處結構性改動）：

```rust
pub struct AlphaSurface<'a> {
    // ... 既有 9 field (Tier 1-4) 不動 ...

    // ── 新增（W2 paper-only）：BTC→Alt lead-lag cross-asset panel ──
    pub btc_lead_lag: Option<&'a BtcLeadLagPanel>,
}
```

`tier1_only()` / `empty()` / `EMPTY_ALPHA_SURFACE` 三 constructor 加 `btc_lead_lag: None` 一行；`Default` impl 自動繼承。

---

## §3 Producer Hook Signature

**現狀**：trait 內**沒有顯式 producer trait**——producer = collector 寫 PG，consumer = `tick_pipeline` 在 `step_4_5_dispatch` 從 IPC slot pull panel snapshot 構造 `AlphaSurface` borrow，傳給 `Strategy::on_tick`。

**W1 + W2 producer 不需新 trait**，但須 follow 既有 pattern：

| Layer | Component | W1 funding_curve | W1 oi_delta_panel | W2 btc_lead_lag |
|---|---|---|---|---|
| Python writer | `program_code/.../market/<panel>_writer.py` | 新增 (E1 派發) | 新增 (E1 派發) | 新增 (E1 派發) |
| PG table | `panel.<name>` (V### migration) | V085 funding_rates_panel | V087 oi_delta_panel | V088 btc_lead_lag_panel |
| Rust IPC slot | `rust/openclaw_engine/src/ipc_server/slots.rs` (新 slot) | `FundingCurvePanelSlot` | `OIDeltaPanelSlot` | `BtcLeadLagPanelSlot` |
| Rust pull | `tick_pipeline/on_tick/step_4_5_dispatch.rs` | snapshot pull → `surface.funding_curve = Some(&snap)` | 同 | 同（**含 paper-only fence**） |

**Producer Hook 統一形態**（PA D+0 trait skeleton **不**寫此 hook，只在 `alpha_surface.rs` MODULE_NOTE 文件化），E1 IMPL 各自寫：

```rust
// 各 panel slot 統一 trait（不在 alpha_surface.rs，而在 ipc_server/slots.rs）
pub trait PanelSlot: Send + Sync {
    type Snapshot: Default + Clone;
    /// 從 IPC payload 解 + 更新 latest snapshot
    fn ingest(&self, payload: &[u8]) -> Result<(), SlotError>;
    /// 取最新 snapshot 引用（lifetime 綁 slot self）
    fn latest(&self) -> Option<&Self::Snapshot>;
    /// Freshness check：snapshot age vs threshold
    fn is_fresh(&self, now_ms: i64, threshold_ms: i64) -> bool;
}
```

**為什麼不在 alpha_surface.rs**：保持 `openclaw_core` zero-IPC dependency；slot 接 ipc_server crate，core trait 維持 borrow-only。

---

## §4 Consumer Interface（Strategy `on_tick` 接收）

**Strategy ctor declare**（既有 W-AUDIT-8a Phase A 已落）：

```rust
fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
    const TAGS: &[AlphaSourceTag] = &[
        AlphaSourceTag::Ta1m,
        AlphaSourceTag::CrossAsset,    // W2 ma_crossover + grid_trading 加此
    ];
    TAGS
}
```

**Strategy on_tick 消費**（**W2 paper-only**；W1 panel 留 demo+live）：

```rust
fn on_tick(&mut self, ctx: &TickContext<'_>, surface: &AlphaSurface<'_>) -> Vec<StrategyAction> {
    // ... existing TA1m logic ...

    // W2 paper-only consume（fence 由 surface.btc_lead_lag 決定，None → 跳過）
    if let Some(panel) = surface.btc_lead_lag {
        // shadow log only（C-IMPL-3 不直接 trade）
        log::info!(
            target: "btc_alt_lead_lag_shadow",
            "symbol={} btc_lead={:.4} window={} expected_dir={:?}",
            ctx.symbol, panel.btc_lead_return_pct, panel.lead_window_secs,
            panel.alt_expected_dir.get(/* lookup index */ 0)
        );
        // **不**改 actions，純 evidence 收集
    }

    actions
}
```

**契約鎖死**（既有 trait MODULE_NOTE line 25-29 已寫）：策略若 declare `CrossAsset` 但 `surface.btc_lead_lag.is_none()` → fail-closed 跳過自身 alpha source；**禁** fallback 到 TA1m。

---

## §5 Paper-only Fence 機制設計（W2 核心）

**Why**：W2 fast-track 直接 paper IMPL，但 ma_crossover + grid_trading 在 demo + live_demo engine mode 也跑。若 BtcAltLeadLag panel 在 demo engine 也 wire 進 surface → ma_crossover demo edge baseline 會被污染（demo 是 5 策略 baseline 數據源）。

**Fence layer**（三層深度防禦）：

### Layer 1 — `step_4_5_dispatch.rs` engine_mode gate（推薦主防線）

`tick_pipeline/on_tick/step_4_5_dispatch.rs` 構造 `AlphaSurface` 時**讀 `pipeline.effective_engine_mode()`**：

```rust
let btc_lead_lag = match self.effective_engine_mode() {
    "paper" => self.btc_lead_lag_slot.latest(),
    _ => None,  // demo / live_demo / live → 永遠 None
};
let surface = AlphaSurface {
    // ... other fields ...
    btc_lead_lag,
};
```

**為什麼這裡而非 IntentRouter**：W2 C-IMPL-3 只 shadow log 不 trade，IntentRouter 不會被觸發；fence 必須在 surface 構造處。

### Layer 2 — Python writer 也做 paper-only fence

`btc_lead_lag_writer.py` 啟動時讀 `OPENCLAW_ENABLE_PAPER` env；若未設 + 偵測 demo/live engine 為 active → writer 不啟動或只寫 placeholder row。**避免 PG table 累積 demo 期樣本污染**。

### Layer 3 — Strategy 端 defensive guard（可選，已被 §4 contract 覆蓋）

`ma_crossover` / `grid_trading` 內部 if `surface.btc_lead_lag.is_none()` → skip。Fence 1 已保證 demo/live 永遠 None，此 guard 是 redundant safety。

**不推薦的反模式**：
- 在 trait 內加 `#[cfg(paper_only)]` — Rust feature gate 會破 binary 統一性
- 在 `AlphaSourceTag::CrossAsset` 加 `paper_only: bool` 字段 — 違反 `AlphaSourceTag` enum 簡單聲明性原則（spec §2.1 enum 變更必經 ADR）

---

## §6 W1 + W2 Sub-agent 分工避撞 Plan

**核心策略**：**PA D+0 一個 commit 把 trait skeleton 全寫死**，W1 + W2 IMPL 並行時不再動 `alpha_surface.rs` 結構，只填 producer slot / writer / 策略消費端。

| Sub-agent | Scope | 動的 file（不重疊） |
|---|---|---|
| **PA D+0** | trait skeleton commit | `srv/rust/openclaw_core/src/alpha_surface.rs` (+ `BtcLeadLagPanel` struct + `AlphaSurface.btc_lead_lag` field + 3 constructor 加一行) |
| **W1 E1-α (B-1)** | funding_curve writer + V085 | `program_code/.../market/funding_curve_writer.py` (新) + `sql/migrations/V085__funding_rates_panel.sql` (新) + `rust/openclaw_engine/src/ipc_server/slots.rs` (加 `FundingCurvePanelSlot`) + `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` (一行 `funding_curve: self.funding_slot.latest()`) |
| **W1 E1-β (B-2)** | oi_delta_panel writer + V087 | `program_code/.../market/oi_delta_panel_writer.py` (新) + `sql/migrations/V087__oi_delta_panel.sql` (新) + `slots.rs` (加 `OIDeltaPanelSlot`) + `step_4_5_dispatch.rs` (一行 `oi_delta_panel: self.oi_slot.latest()`) |
| **W2 E1-γ (C-IMPL-1)** | trait extension **NO-OP**（PA 已 commit） | **無檔可動** — C-IMPL-1 範圍縮減為 BtcLeadLagPanel typedef 驗收 + struct field 對齊 producer schema (寫 `srv/docs/execution_plan/2026-05-1X--a4c_btc_alt_lead_lag_spec.md` 對照表) |
| **W2 E1-δ (C-IMPL-2)** | lead-lag producer + V088 | `program_code/.../market/btc_lead_lag_writer.py` (新) + `sql/migrations/V088__btc_lead_lag_panel.sql` (新) + `slots.rs` (加 `BtcLeadLagPanelSlot`) + `step_4_5_dispatch.rs` (**含 paper-only engine_mode gate** §5 Layer 1) |
| **W2 E1-ε (C-IMPL-3)** | strategy paper-only 接收 | `ma_crossover/strategy_impl.rs` (declare `CrossAsset` tag + on_tick shadow log) + `grid_trading/mod.rs` (同) — **bb_breakout / bb_reversion / funding_arb 不動** |

**衝突點全部消除**：
- `alpha_surface.rs` 只 PA D+0 動一次，3 E1 sub-agent 之後不再 touch
- `slots.rs` 三個 sub-agent 各加一個 slot struct（PA D+0 在 `slots.rs` 預留 `// W1 funding_curve slot here` / `// W1 oi_delta slot here` / `// W2 btc_lead_lag slot here` 三個 anchor comment，3 sub-agent 在各自 anchor 下方 insert，避免 line collision）
- `step_4_5_dispatch.rs` 三個 sub-agent 各加一行 surface field assignment（同樣 anchor pattern）
- 三個 V### migration 編號 V085 / V087 / V088 預先 reserved，W6 V086 同窗也已預留

**E2 重點審查 3 點**：
1. **W2 paper-only fence Layer 1 是否真的 gate**：`step_4_5_dispatch.rs` 加的 `match engine_mode` 必須 default → None（不是 default → Some），E2 grep verify
2. **`AlphaSurface.btc_lead_lag` 加 field 後 `tier1_only()` / `empty()` / `EMPTY_ALPHA_SURFACE` 三 constructor 全部更新**——漏一個會破 backward compat（既有 callsite 用 `..AlphaSurface::empty()` spread pattern 會編譯失敗）
3. **panel slot freshness check threshold**：funding_curve 30s WARN / 300s FAIL（spec §2.3 Tier 2.1）；oi_delta 同；btc_lead_lag 推薦 60s WARN / 600s FAIL（lead-lag 信號比 funding 容忍度高，但不能太 stale）

---

## §7 D+0 PA 預先 Commit Trait Skeleton 範圍

**單一 commit 內容**（PA D+0 by 11:30 UTC，dispatch 派發 W1+W2 sub-agent 之前）：

1. `srv/rust/openclaw_core/src/alpha_surface.rs`：
   - 新增 `BtcLeadLagPanel` struct typedef (~25 LOC，§2 上方)
   - `AlphaSurface<'a>` 加 `pub btc_lead_lag: Option<&'a BtcLeadLagPanel>,` 一行
   - `tier1_only()` constructor 加 `btc_lead_lag: None,`
   - `empty()` constructor 加 `btc_lead_lag: None,`
   - `EMPTY_ALPHA_SURFACE` static 加 `btc_lead_lag: None,`
   - `Default` impl 自動繼承（無需手動）
   - 新增 1 test：`btc_lead_lag_default_none()` 確認
   - MODULE_NOTE 末尾加一段：「W2 BtcLeadLagPanel paper-only fence 由 `tick_pipeline/on_tick/step_4_5_dispatch.rs` engine_mode gate 實施，trait 端不知此 fence；策略消費端 `surface.btc_lead_lag.is_none()` → skip 即可，不需查 engine_mode」

2. `srv/rust/openclaw_engine/src/ipc_server/slots.rs`：
   - 加三個 anchor comment：`// === W1 FundingCurvePanelSlot insertion point ===` / `// === W1 OIDeltaPanelSlot insertion point ===` / `// === W2 BtcLeadLagPanelSlot insertion point ===`

3. `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`：
   - 同 anchor comment 三處

**Commit message** (PA D+0)：
```
PA: Sprint N+1 W1+W2 alpha_surface trait skeleton (BtcLeadLagPanel + insertion anchors)

W1 + W2 將並行動 alpha_surface.rs / slots.rs / step_4_5_dispatch.rs，PA 預先 commit
trait final shape skeleton + insertion anchor comment 避免 sub-agent 撞 git merge。
W2 BtcLeadLagPanel typedef + AlphaSurface.btc_lead_lag field + 3 constructor。
W1 funding_curve / oi_delta_panel field 早 W-AUDIT-8a Phase A 已 land。
參考：srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md
```

**之後**：W1 + W2 五個 E1 sub-agent **完全並行**，0 file 重疊（最多 step_4_5_dispatch.rs / slots.rs 同 file 加 line，但 anchor 隔離；E4 regression 跑全 PG migration 順序驗）。

---

## §8 Risk + Dependency Check

### §8.1 Backward compat with Phase A 5 既存策略
- **無 break**：`AlphaSurface.btc_lead_lag` 是新加 Optional field，既有 5 策略 declare 不含 `CrossAsset` tag → 不會 query；新增 field 在 struct 末尾不破 Phase A test。
- **`AlphaSurface::empty()` const fn**：Rust const fn 限制下 `Option::None` 可在 const context；新增 field 不破 `tier1_only` const 約束。
- **驗證**：PA D+0 commit 後 `cargo test --lib --release -p openclaw_core` 全 9 test PASS（4 既有 alpha_surface test + 5 新 panel + tier1 test）。

### §8.2 W-AUDIT-9 graduated canary state machine 衝突
- **不衝突**：W-AUDIT-9 在 `governance_core.rs` + `canary_stage_log` 表，與 alpha_surface 完全解耦；W3 Stage 1 cohort 觀察用 W1 panel 數據是讀單向，trait shape 變化不影響 canary state transition logic。
- **時序依賴**：W1 land 後 ≥24h 再進 W3 Stage 1（dispatch §5.1 已記）；不是 trait 衝突。

### §8.3 Hypertable / TimescaleDB partition 設計建議
**MIT 必審**（W1 V085/V087 + W2 V088 三 panel migration）：

| Table | Hypertable? | Chunk interval | Retention | 索引 |
|---|---|---|---|---|
| `panel.funding_rates_panel` | YES (TimescaleDB) | 1 day | 14d (drop_chunks policy) | `(snapshot_ts_ms DESC, symbol)` covering |
| `panel.oi_delta_panel` | YES | 1 day | 14d | `(snapshot_ts_ms DESC, symbol)` |
| `panel.btc_lead_lag_panel` | YES | 1 day | 14d (paper-only 期短，未來 demo 升 30d) | `(snapshot_ts_ms DESC, lead_window_secs)` |

**理由**：三 panel 都是 time-series 且 query pattern 是「最新 N 秒 snapshot」+「歷史 14d backfill」；TimescaleDB hypertable + chunk_time_interval=1d 是標準 pattern (V050 simulated_fills + V082 decision_features 同 pattern)。Retention 14d 對齊 spec §2.3 Tier 2.1 (funding_rates_panel) + §2.3 Tier 2.3 (oi_delta_panel)。BtcLeadLagPanel paper-only 期不需長期，14d 足夠 paper edge evaluation window；如 N+2 promote demo IMPL，再延 30d。

### §8.4 16 根原則合規（CLAUDE.md §二 + skill checklist）
- **原則 1 單一寫入口**：trait 不寫入路徑，consumer 在 step_4_5_dispatch 構造 borrow-only surface → ✅
- **原則 4 不繞風控**：BtcAltLeadLag paper-only fence Layer 1 + W2 C-IMPL-3 純 shadow log 不 trade → 不觸碰 SM-04 Guardian → ✅
- **原則 7 學習 ≠ 改寫 Live**：paper engine fence + Python writer fence + Strategy `if let Some` guard 三層 → demo/live engine 完全 None → 5 策略 demo edge baseline 不污染 → ✅
- **原則 8 交易可解釋**：panel snapshot 寫 PG (`source_tier` field) + Strategy on_tick shadow log 含 `lead_window_secs` + `expected_dir` → 可 reconstruct alpha source 來源 → ✅
- **DOC-08 §12 9 條安全不變量**：本 trait 不動 lease / authorization / audit / reconciler / mainnet env / Bybit retCode 任何路徑 → 全 9 條不變量無關 → ✅
- **硬邊界 5 項**：本 trait 不動 `live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `decision_lease` / `authorization.json` → 全 5 項無關 → ✅

### §8.5 已知 risk + 緩解
| Risk | 等級 | 緩解 |
|---|---|---|
| W2 fence Layer 1 漏 engine_mode check → demo 污染 | 高 | E2 強制 grep `effective_engine_mode` in step_4_5_dispatch.rs；E4 跑 demo engine 24h regression 驗 `surface.btc_lead_lag` 永遠 None |
| AlphaSurface 加 field 破 EMPTY_ALPHA_SURFACE static 編譯 | 中 | PA D+0 commit 內含 cargo build verify；CI 必 PASS 才 push |
| V088 panel hypertable retention drop_chunks policy 漏設 → PG 滿 | 中 | MIT 審 migration template 必含 `add_retention_policy('panel.btc_lead_lag_panel', INTERVAL '14 days')` |
| Lead window strict shift(N) 漏 → look-ahead bias | **極高** | PA spec C-1 強制 `feedback_indicator_lookahead_bias` 引用；QC C-2 review 必對照 `rolling(N).max()` 反模式；MIT C-3 leak detection 必跑 |
| `CrossAsset` enum tag 對應多個未來 panel（W-AUDIT-8c BTC-Alt + 跨對 correlation）→ tag 粒度太粗 | 中 | 接受；W-AUDIT-8c 真接 generic 跨資產 panel 時拆 `BtcAltLeadLag` 為獨立 enum variant（ADR 觸發） |

---

## §9 一句總結

**PA D+0 一個 commit 把 `BtcLeadLagPanel` typedef + `AlphaSurface.btc_lead_lag` field + 3 constructor + slots/dispatch anchor 全寫死，W1 + W2 五個 E1 sub-agent 之後完全並行 0 file 重疊 0 git merge 衝突；W2 paper-only fence 在 `step_4_5_dispatch.rs` engine_mode gate 主防線 + Python writer + Strategy guard 三層深度防禦；trait shape 與 W-AUDIT-8a Phase A backward compat 0 break；16 原則 + DOC-08 §12 不變量 + 硬邊界 5 項全 0 觸碰。**

---

**Report end. PA D+0 next action**: by 11:30 UTC commit trait skeleton per §7；by 12:00 UTC dispatch W1 + W2 五個 E1 sub-agent 並行；by D+5 全 IMPL E2 review。

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md
