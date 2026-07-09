# REF-20 Sprint B — Task DAG Design (R4 UI Enable + R5 Real Decision/Risk Replay Path)

**Date**: 2026-05-05
**Author**: PA (Project Architect)
**Status**: design ready (read-only; no IMPL, no commit)
**Sprint context**:
- Sprint A closed-with-real-evidence (HEAD `0ad79f67` per CLAUDE.md §三; 8-commit chain `c1ab7ea9..2531c011`).
- Plan §6.R3 acceptance 4 表 row > 0 真實達成（experiments=4 / run_state=4 / report_artifacts=1 / simulated_fills=1）。
- 6-layer blocker chain (placeholder sig / DEVNULL silent-dead / SHA env / spawn race / signing key not provisioned / poll-grace exit=0 mis-classified) 全排除。
- replay_routes.py 1500 LOC EXACT cap（0 margin）— Sprint B 第一手必先處理 LOC 預算。
- Plan §11 explicit limitations：A4 actual strategy path / A5 actual risk path / A6 fee-aware PnL / A7 confidence honesty / A8 UI usable / A10 ML-Dream advisory boundary 全 Sprint B-D scope。

**PM 派發 scope**：R4 (UI enable) + R5 (real decision/risk replay path) — 但 R6 (fee calibration) **不在 Sprint B**（plan §9 Sprint C scope）。

---

## §0. Push back（PA 意見書）— Sprint B 必須拆成 B1+B2 兩個獨立 sprint

> **PM 須先回答此 push back，再採後續 task DAG**。

PA 評估後**強烈建議 Sprint B 不應一次涵蓋 R4+R5**。原因如下：

| # | 證據 | 風險 |
|---|---|---|
| 1 | R5 涉及「extract or gate pure components 使既有 strategy / risk 可被 replay 呼叫但無 live side effects」（plan §6.R5 task 2）。**這是 Rust 端 5 strategy + IntentProcessor pipeline 的 architectural refactor**。任一動作出錯會破 Live hot path。 | 極高 — 觸 GovernanceHub SM / IntentProcessor router / 5 strategy 任一接縫。 |
| 2 | 既有 Rust IntentProcessor `process_with_features()`（`intent_processor/router.rs` line 184）有 8 個 Gate（1.0 governance auth → 1.4 lease → 1.5 dup → 1.6 negative balance → 2.0 Guardian → 2.5 Kelly → 2.6 P1 cap → 2.7 admission），耦合 `paper_state` mutable global、`canary_writer`、`bybit_rest_client`、`governance_core::GovernanceCore`、`risk_checks::check_order_allowed`。**抽 pure decision path 不是 1 sprint 工作**。 | 極高 — workplan §4 Wave 4 R20-P2b-T1 已留 ambiguity for PM。 |
| 3 | 既有 `replay_runner` runner.rs `IsolatedPipeline` 刻意**不**接 `IntentProcessor`（runner.rs line 21-45 module note 明寫「不接 intent_processor / tick_pipeline / ipc_server / governance_hub」）。理由：V3 §6.2 forbidden list 把 `paper_state` mutable global、`canary_writer` DB writer、`database::DecisionFeatureMsg` writer channel 全列禁。任何「真實 IntentProcessor 路徑」都需要先解決 §6.2 forbidden list 與 V3 §6.1「可共用 strategy/risk 模塊」之間的張力。 | 極高 — 直接破 V3 §6.2 = symbol audit fail-loud。 |
| 4 | replay_routes.py 1500 LOC EXACT cap → R4 增 ~150-200 LOC 不可能塞，必先拆 sub-router；R5 端的 evidence schema 改動可能再增 100 LOC。**LOC 預算單一 sprint 已破**。 | 高 — pre-existing 1500 baseline exception clause 無法套用（不是 pre-existing violation）。 |
| 5 | R5 acceptance "A known parameter delta changes replay decisions in a controlled fixture" 的 fixture 設計需 QC 介入（confluence score / persistence elapsed 等 ML feature snapshot 需要方法論確認）。1 sprint 內串到 QC 已緊。 | 中 — 工時鏈長。 |
| 6 | Sprint A 8-commit chain 顯示「即使簡單 IMPL 也會出 6-layer blocker chain」。R4+R5 至少 2-3 倍 Sprint A 複雜度，blocker 鏈條風險倍增。 | 中 — 歷史模式。 |

**PA 建議切分**：

```
Sprint B1 (1.5-2 day): R4 UI Enablement（單純 UI gate to /health endpoint）
                     + replay_routes.py LOC 預算釋放（拆 thin handler 到 sub-router）

Sprint B2 (3-5 day): R5 Real Decision/Risk Replay Path
                     先做 grid_trading + ma_crossover pilot
                     不做 funding_arb / bb_breakout / bb_reversion（C wave 補完）
```

**若 PM 仍堅持單一 Sprint B 涵蓋 R4+R5**：本 report §1-§10 仍適用，但 §7 task DAG 假設 PA push back 被 accept；§7 末尾附「PM override 路徑」說明若不拆會增加哪些 risk。

> **PA 報告其餘章節先以 B1=R4 / B2=R5 為基礎**。PM 拍板後再依結果回讀。

---

## §1. R4 (UI Enable) — Strategy Call Graph 不適用，跳到 Risk Call Graph 也不適用

R4 純 frontend 改動。讀 §3 R4 設計即可，本節 (§1, §2) 對 R4 略過。

## §1A. Strategy Call Graph Inventory — 5 Strategy 真實接線

**真實檔案位點**：`rust/openclaw_engine/src/strategies/`（中已 split 過，遵 §九 1500 LOC cap）

### grid_trading（唯一 net positive 策略，~7 modules）

| 子模組 | LOC | 角色 | Replay 純度 |
|---|---:|---|---|
| `grid_trading/mod.rs` | 348 | struct + Strategy trait impl thin delegators + `compute_grid_confidence` + 8 const | **混雜** — `Strategy::on_tick`（thin）+ `compute_grid_confidence`（pure） |
| `grid_trading/signal.rs` | (~360 estimated, file in repo) | `on_tick_impl` 主 dispatch — 含 cross detection / OU spacing refresh / cooldown / dispatch BUY/SELL | **可純化但需重構** — 走 `&mut self` mutable + 派發 `Vec<StrategyAction>` |
| `grid_trading/grid_layout.rs` | ~190 | OU step calc / health check / rebalance / nearest_grid_idx | **可純化** — 純 in-mem state，無 IPC / DB |
| `grid_trading/position_mgmt.rs` | ~110 | trend cooldown / `on_external_close` / `on_close_confirmed` / `on_close_skipped` / `on_rejection` | **可純化** — 純 callback，無 IPC / DB |
| `grid_trading/constructors.rs` | ~280 | `new` / `new_geometric` / `new_adaptive*` / `set_fee_rate` / `update_params` / `get_params` | **純** |
| `grid_trading/params.rs` | ~250 | `GridTradingParams` + `Default` + `StrategyParams` impl | **純** |
| `grid_trading/tests.rs` | ~620 | 36 unit test | (test only) |
| `grid_helpers.rs` | 640 | `build_levels` 等 | **純** — 已 split 為 helper |
| `confluence.rs` | 811 | persistence/confluence score | **純** — 已 split |
| `maker_rejection.rs` | 216 | maker reject category | **純** |

**Inputs to `on_tick(&mut self, ctx: &TickContext<'_>)`**:
- `&TickContext` (line `tick_pipeline/mod.rs:665`):
  - `symbol: &str`, `price: f64`, `timestamp_ms: u64`, `indicators: Option<&IndicatorSnapshot>`, `signals: &[Signal]`
  - `h0_allowed: bool`, `funding_rate: Option<f64>`, `index_price: Option<f64>`, `open_interest: Option<f64>`
  - `best_bid: Option<f64>`, `best_ask: Option<f64>`, `tick_size: Option<f64>`
- 全部 OHLCV / pricing / indicator — **0 live state，0 IPC，0 DB**

**Outputs**:
- `Vec<StrategyAction>` — `Open(OrderIntent)` 或 `Close { symbol, confidence, reason }`
- `OrderIntent` (line `intent_processor/mod.rs:60`)：純 data，0 side effect

**Conclusion**: grid_trading 的 `on_tick` ≈ pure function over `(IndicatorSnapshot, prices, signals, internal mutable state)` → `Vec<StrategyAction>`。**理論上 replay 可直接呼叫**。實踐障礙見下文。

### ma_crossover (~451 LOC mod + 5 sibling)

| 子模組 | 角色 | Replay 純度 |
|---|---|---|
| `ma_crossover/mod.rs` | struct + Strategy trait impl thin | 混雜 |
| `ma_crossover/strategy_impl.rs` | `on_tick` 主 dispatch | **可純化** |
| `ma_crossover/config.rs` | params/runtime config | 純 |
| `ma_crossover/helpers.rs` | helper functions | 純 |
| `ma_crossover/tests*.rs` | unit + maker-aware tests | (test only) |

**Inputs/Outputs**：同 Strategy trait — 純 OHLCV-only。

### bb_breakout (~855 LOC mod + 4 sibling)
- 6 modules（`mod.rs` / `params.rs` / `runtime_params.rs` / `tests.rs` / `tests_oi.rs` / `tests_p1_11.rs`）
- `on_tick` 純 OHLCV + indicators
- **特殊**：含 OI delta tracking（per-symbol buffer），需要 historical OI window

### bb_reversion (~487 LOC mod + 2 sibling)
- 3 modules（`mod.rs` / `params.rs` / `tests.rs`）
- `on_tick` 純 OHLCV + indicators

### funding_arb (1042 LOC monolith)
- **單檔**未 split（1042 LOC < §九 1500 cap）
- **特殊**：依賴 `funding_rate` + `index_price`，需要 funding rate snapshot 以 replay
- V2 棄策略路徑（commit `a19797d`，2026-05-02 funding_arb_v2_deprecation_path）— **B2 pilot 不必涵蓋**

### Module-level Singleton 重置需求（CLAUDE.md §九 第 12-row registry）

`strategy_wiring.py:143` 有 12+ singleton（`KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` / `SCOUT_AGENT` 等）。但這些是**Python control_api_v1 端**的 singleton。

**Rust 端**：
- `strategies::registry::StrategyFactory` 是工廠模式，不是 singleton
- 各 strategy 是 `Box<dyn Strategy>` instance — **可重新 build**

**Replay 端不需 reset Python singleton**（replay_runner 是獨立 Rust 子行程，**0 Python import**）。

### Strategy Trait 接口適合 replay？

| 接口 | replay 端 | 障礙 |
|---|---|---|
| `name()` / `is_active()` / `set_active()` | ✅ 純 | 無 |
| `on_tick(&mut self, &TickContext) -> Vec<StrategyAction>` | ✅ 純 | 無（trait 簽名 0 副作用） |
| `on_rejection(&mut self, &OrderIntent, reason)` | ✅ 純 callback | replay 端 mock 拒絕原因即可 |
| `on_fill(&mut self, &OrderIntent, &FillResult)` | ✅ 純 callback | replay 端 mock 模擬 fill 結果 |
| `update_params_json` / `get_params_json` / `param_ranges_json` | ✅ 純 | 無 |
| `set_conf_scale` | ✅ 純 | 無 |

**結論**：Strategy trait **本身就是 replay-ready**。問題不在 strategy 端，**在 IntentProcessor 端**。

---

## §2. Risk Call Graph Inventory — Pipeline 真實接線

**核心檔案**：

### `intent_processor/router.rs` (1028 LOC) — `IntentProcessor::process_with_features()` (line 184)

8 個 Gate，從上到下：

| Gate | 副作用 | Replay 是否 reachable |
|---|---|---|
| 1.0 Governance authorization (`is_authorized()`) | **讀 Live config** | 需 mock 為 `true` |
| 1.4 **Decision Lease** (`acquire_lease_for_gate_1_4`) | **副作用** — 寫 SM-02 state machine + V054 audit | 必跳過（V3 §6.2 + plan §4 hard boundary） |
| 1.5 Duplicate position check | **讀 paper_state.get_position** | 需 mock paper_state |
| 1.6 Negative balance guard | **讀 paper_state.balance** | 需 mock paper_state |
| 2.0 Guardian.review (`guardian.review`) | **讀 RiskConfig + portfolio context** | 純函數 — replay 可直接呼叫 |
| 2.5 Kelly sizer (`compute_kelly_qty`) | **讀 trade_stats + RiskConfig** | 純函數 — replay 可直接呼叫 |
| 2.6 P1 hard cap (`balance * p1_risk_pct / price`) | **讀 paper_state.balance** | 純算術 — 0 副作用 |
| 2.7 Admission risk check (`check_order_allowed`) | **讀 paper_state + RiskConfig** | 純函數 — replay 可直接呼叫 |
| Post-2.7: Cross-engine notional cap, OMS dispatch | **副作用** — 寫 paper_state + canary_writer + IPC | 必跳過 |

### Decision lease 在 replay 路徑的處理（plan §4 hard boundary）

ReplayProfile::Isolated 已在 `profile.rs::requires_lease()` line 212 強制 `false`。但 R5 IMPL 必須處理：
1. `governance_core::GovernanceCore::acquire_lease()` 不能被 replay-side 呼叫；
2. 若 R5 共用 `IntentProcessor::process_with_features`，必須 short-circuit Gate 1.4；
3. PM 已 sign-off `AMD-2026-05-02-01` Path A — feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF（CLAUDE.md §三）→ **production 路徑短路 Gate 1.4 不取 lease**。
4. **但**：R5 不能依賴 flag OFF（Sprint 3 Track I 已 deploy `dbcf845b`，flag 任何時候可被 operator flip）。R5 必須自己短路 — 透過 `ReplayProfile::Isolated.requires_lease() == false` 注入到 `process_with_features` decision 邏輯。

### 純函數可重用清單

| 函數 | 檔案 | replay 端可直接呼叫？ |
|---|---|---|
| `Guardian::review(&check, &ctx)` | `openclaw_core::guardian` | ✅ 純函數（讀 RiskConfig snapshot） |
| `compute_kelly_qty(cfg, stats, balance, price, atr_pct, qty)` | `ml/kelly_sizer.rs` | ✅ 純函數 |
| `check_order_allowed(qty, price, balance, exposure_pct, ...)` | `risk_checks.rs:113` | ✅ 純函數 |
| `check_position_on_tick(...)` | `risk_checks.rs:201` | ✅ 純函數（用於 exit/stop/PHYS-LOCK） |
| `apply_governor_order_constraints(governance, is_reducing, qty, existing_qty)` | `intent_processor/router.rs:121` | ⚠️ 讀 `governance.risk.snapshot_level()` — 需 mock GovernanceCore |
| `per_strategy_symbol_rejection(config, intent, is_reducing)` | `intent_processor/router.rs:152` | ✅ 純函數（讀 RiskConfig） |

**結論**：所有 risk gate 邏輯都是 pure function on `(RiskConfig snapshot, intent, position state snapshot)`。**Replay 可重用**，**但** wrap 它的 `IntentProcessor::process_with_features` 是 stateful，無法直接呼叫。

---

## §3. R4 (UI Enable) 設計 — 純 frontend，1.5d 工

### R4 改動範圍

| 檔案 | 當前狀態 | R4 改後 |
|---|---|---|
| `app/static/tab-paper.html:101-105` | `aria-disabled="true" data-disabled="true"` 硬編 | 移除靜態 disabled，改 JS 動態 readiness gating |
| `app/static/tab-paper.html:286-294` | `<div id="subtab-replay-disabled-card"></div>` 唯一內容 | 改 5-state container（empty / running / failed / completed / degraded）+ confidence badge slot |
| `app/static/app-paper.js` | 814-823 行硬 render `OpenClawDisabledStateCard` | 加 `/api/v1/replay/health` probe → state machine + render |

### R4 任務分解（3 task）

**R4-T1 backend-readiness gated subtab activation**
- **檔案**：`tab-paper.html:101-105`
- **LOC**：~10 LOC（移 attr）
- **動作**：移除 `aria-disabled="true" data-disabled="true"`；保留 `data-subtab="replay"` 與 `id="subtab-btn-replay"`；button title/i18n key 改寫為「Backend health pending — see badge」
- **副作用**：app-paper.js sub-tab navigation 函式（`activatePaperSubTab` line 299-371）原本 disabled check 走 `data-disabled="true"` 短路（line 333-335）。改為 R4-T2 的 readiness state 短路。
- **Risk**：低（純 attribute 改動）

**R4-T2 readiness probe + 5-state machine**
- **檔案**：`app-paper.js`（新加 ~60-80 LOC，可放 `OpenClawReplaySubtab` namespace）
- **LOC**：~80 LOC
- **動作**：
  - 加 `pollReplayBackendReadiness()` 函式：`fetch('/api/v1/replay/health')` → 解析 `wiring_status` ('ready' / 'degraded' / 'binary_missing')
  - State machine 5 態：`empty / running / failed / completed / degraded`
  - On tab activate：probe → if not ready → render disabled state with reason badge；if ready → render run form (R4-T3)
  - Periodic poll（30s interval）在 tab active 時 — degrade 自動透出
- **副作用**：與 `_OC_PAPER_SUBTAB_LS_KEY = "paper_active_subtab"` 持久化交互（line 299）— 即使 last-active=replay，下次 load 仍須先 probe，**禁止無 probe 直 active**。
- **Risk**：中（涉 sub-tab 持久化交互；E2 必查）

**R4-T3 confidence/data tier/fee model render slots**
- **檔案**：`app-paper.js`（再加 ~40 LOC）+ `tab-paper.html`（新增 ~20 LOC HTML）
- **LOC**：~60 LOC（HTML+JS 跨檔分散）
- **動作**：
  - HTML：在 #subtab-replay 內加 4 cell 區（execution_confidence / data_tier / fee_model / calibration_status）+ 1 status timestamp
  - JS：on selected experiment_id → fetch `/api/v1/replay/report/{id}` → render 4 cell
  - **重要**：`evidence_source_tier='synthetic_replay'` 必顯示為 "execution_confidence: NONE"（CLAUDE.md §九 既登記 non-training surface）
- **副作用**：呼叫 `/api/v1/replay/report/{id}`（既 ship in `replay/report_route.py`）— 0 backend 改動。
- **Risk**：低

**R4-T4 UI tests + manual smoke checklist**
- **檔案**：`tests/static/...` 或 `tests/control_api/test_paper_subtab_readiness.py`（estimate）
- **LOC**：~150 LOC（Python integration test or playwright e2e）
- **動作**：mock /health 三 state（ready / degraded / binary_missing）→ DOM assert subtab disabled/enabled state 正確
- **副作用**：純 test，0 production 風險
- **Risk**：低

### R4 關鍵副作用識別

1. **sub-tab persistence race**：若 last-active=replay 但 backend now degraded，必須先 probe → 不可信任 localStorage（line 299）。E2 必查 `activatePaperSubTab` 流程。
2. **Banner i18n key reuse**：disabled_state UI 既有 `disabled_state.p2_backend_pending` i18n key — 不要新增 i18n key（避免 i18n 表膨脹）。
3. **`/api/v1/replay/health` 已 ship**（replay_routes.py line 1275-1338，Sprint A R1-T3 commit `c1ab7ea9`）— R4 純 consume，0 backend 改動。

### R4 acceptance（per plan §6.R4）

- ✅ Replay tab is enabled only when backend health is green
- ✅ UI never labels current smoke replay as calibrated（execution_confidence='none'）
- ✅ No manual order controls reappear（subtab 不出現舊 manual submit/cancel button）
- ✅ Empty / running / failed / completed / degraded 5 state 全有對應 UI

### R4 LOC 預算（純 frontend，0 影響 replay_routes.py 1500 cap）

| File | Δ LOC | Total |
|---|---:|---:|
| `tab-paper.html` (909 → ~929) | +20 | 929 |
| `app-paper.js` (447 → ~587) | +140 | 587 |
| `tests/...` (new) | +150 | 150 |

R4 **不動 replay_routes.py**，cap 風險 0。

---

## §4. R5 (Real Decision/Risk Replay Path) — Adapter 設計

### §4.1 ReplayStrategyAdapter 設計

**目的**：讓 5 strategy 的 `on_tick` 能在 replay binary 內呼叫，**不**透過 IntentProcessor / IPC / DB。

**設計選擇**：Rust trait wrapper（**不**新加 trait，直接複用 `Strategy` trait）。

```rust
// 新檔：rust/openclaw_engine/src/replay/strategy_adapter.rs
// （新 module，~150 LOC est.）

use crate::replay::profile::ReplayProfile;
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;

pub struct ReplayStrategyAdapter {
    /// 策略 instance — 與 live engine 同一型別
    strategy: Box<dyn Strategy>,
    profile: ReplayProfile,
    /// 紀錄每個 on_tick 的 input snapshot + output trace
    pub decision_trace: Vec<DecisionTraceEntry>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub struct DecisionTraceEntry {
    pub ts_ms: i64,
    pub symbol: String,
    pub strategy_name: String,
    pub indicator_snapshot_summary: Option<String>,
    pub actions_emitted: Vec<StrategyActionTrace>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub enum StrategyActionTrace {
    Open {
        intent_signature: String,  // canonical hash of OrderIntent
        confidence: f64,
        is_long: bool,
        qty: f64,
    },
    Close {
        symbol: String,
        confidence: f64,
        reason: String,
    },
}

impl ReplayStrategyAdapter {
    pub fn new(strategy: Box<dyn Strategy>, profile: ReplayProfile) -> Result<Self, ReplayError> {
        // V3 §6.2 fail-closed
        if profile.requires_lease() {
            return Err(ReplayError::NonIsolatedProfile { found: profile });
        }
        Ok(Self { strategy, profile, decision_trace: Vec::new() })
    }

    pub fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let actions = self.strategy.on_tick(ctx);
        // 紀錄 trace
        let action_traces = actions.iter().map(|a| match a {
            StrategyAction::Open(intent) => StrategyActionTrace::Open {
                intent_signature: compute_intent_signature(intent),
                confidence: intent.confidence,
                is_long: intent.is_long,
                qty: intent.qty,
            },
            StrategyAction::Close { symbol, confidence, reason } => StrategyActionTrace::Close {
                symbol: symbol.clone(),
                confidence: *confidence,
                reason: reason.clone(),
            },
        }).collect();
        self.decision_trace.push(DecisionTraceEntry {
            ts_ms: ctx.timestamp_ms as i64,
            symbol: ctx.symbol.to_string(),
            strategy_name: self.strategy.name().to_string(),
            indicator_snapshot_summary: ctx.indicators.map(summarize_indicators),
            actions_emitted: action_traces,
        });
        actions
    }

    pub fn into_trace(self) -> Vec<DecisionTraceEntry> { self.decision_trace }
}

fn compute_intent_signature(intent: &OrderIntent) -> String {
    // canonical hash for parameter-delta proof
    // sha256(symbol|is_long|strategy|order_type|conf:.4f|qty:.4e)
}

fn summarize_indicators(snap: &IndicatorSnapshot) -> String {
    // 簡短 debug summary，避免 trace 爆記憶體
}
```

**關鍵**：
1. **沿用 `Strategy` trait** — 0 trait 改動，5 strategy 0 修改即可被 wrap。
2. **Box<dyn Strategy>** 接受任何 strategy（grid_trading / ma_crossover / bb_breakout / bb_reversion / funding_arb）。
3. **0 副作用契約**：adapter 內無 DB / IPC / Lease。trace 為純 in-memory `Vec`。
4. **profile guard**：constructor 強制 `Isolated` profile（fail-closed）。

### §4.2 ReplayRiskAdapter 設計

**目的**：讓 8 個 Gate 的 risk 邏輯能在 replay binary 內呼叫，**不**透過 GovernanceCore / IntentProcessor 主路徑。

**設計選擇**：替換 IntentProcessor，**重做** mini-pipeline（不共用 router.rs 主函式）。

```rust
// 新檔：rust/openclaw_engine/src/replay/risk_adapter.rs
// （新 module，~250 LOC est.）

use crate::config::RiskConfig;
use crate::intent_processor::OrderIntent;
use crate::risk_checks::check_order_allowed;
use openclaw_core::guardian::{Guardian, ExistingPosition, PortfolioContext, TradeIntentCheck, Verdict};

pub struct ReplayRiskAdapter {
    guardian: Guardian,
    risk_config: RiskConfig,
    p1_risk_pct: f64,
    kelly_config: Option<KellyConfig>,
}

#[derive(Debug, Clone, serde::Serialize)]
pub enum RiskDecision {
    Accepted {
        final_qty: f64,
        verdict: String,    // "Approved" / "Modified"
        guardian_score: f64,
        kelly_qty: f64,
        p1_max_qty: f64,
    },
    Rejected {
        gate: String,       // "1.5_dup" / "1.6_neg_balance" / "2.0_guardian" / "2.7_admission" / etc.
        reason: String,
    },
}

impl ReplayRiskAdapter {
    pub fn evaluate(
        &self,
        intent: &OrderIntent,
        replay_paper_state: &ReplayPaperState,  // 純 in-mem snapshot，§4.3 定義
        atr: f64,
    ) -> RiskDecision {
        // Mini-pipeline 復刻 router.rs:184-455
        // 跳過：Gate 1.0 governance auth (永遠 true) + Gate 1.4 lease
        // 復刻：Gate 1.5 / 1.6 / 2.0 / 2.5 / 2.6 / 2.7

        // Gate 1.5 dup
        if let Some(existing) = replay_paper_state.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return RiskDecision::Rejected {
                    gate: "1.5_dup".into(),
                    reason: format!("DuplicatePosition existing_is_long={}", existing.is_long),
                };
            }
        }

        // Gate 1.6 negative balance
        if replay_paper_state.balance() <= 0.0 && replay_paper_state.get_position(&intent.symbol).is_none() {
            return RiskDecision::Rejected {
                gate: "1.6_neg_balance".into(),
                reason: format!("InsufficientBalance balance={}", replay_paper_state.balance()),
            };
        }

        // Gate 2.0 Guardian
        let positions = replay_paper_state.positions();
        let ctx = PortfolioContext { drawdown_pct: replay_paper_state.drawdown_pct(), positions };
        let check = TradeIntentCheck { /* ... */ };
        let guardian_result = self.guardian.review(&check, &ctx);
        match guardian_result.verdict {
            Verdict::Rejected => return RiskDecision::Rejected {
                gate: "2.0_guardian".into(),
                reason: guardian_result.reasons.join("; "),
            },
            _ => {}
        }

        // Gate 2.5 Kelly + Gate 2.6 P1 cap + Gate 2.7 admission
        // ... 復刻 router.rs:359-455
    }
}

pub struct ReplayPaperState {
    /// In-mem snapshot — 0 IPC / DB
    balance: f64,
    positions: HashMap<String, PaperPosition>,
    drawdown_pct: f64,
}

impl ReplayPaperState {
    pub fn apply_fill(&mut self, intent: &OrderIntent, decision: &RiskDecision, fill_price: f64) { /* ... */ }
    pub fn balance(&self) -> f64 { self.balance }
    pub fn drawdown_pct(&self) -> f64 { self.drawdown_pct }
    pub fn get_position(&self, symbol: &str) -> Option<&PaperPosition> { /* ... */ }
    pub fn positions(&self) -> Vec<ExistingPosition> { /* ... */ }
}
```

**關鍵**：
1. **不共用 IntentProcessor::process_with_features** — 復刻 8 Gate 的 4 個（1.5 / 1.6 / 2.0 / 2.5 / 2.6 / 2.7），**跳過** 1.0/1.4。
2. **共用** Guardian / `check_order_allowed` / `compute_kelly_qty` — 直接 import 使用，0 重複實作。
3. **`ReplayPaperState`** 是 **純 in-mem struct**，**不**接 `crate::paper_state::PaperState`（V3 §6.2 forbidden — DB writer channel）。
4. **0 副作用契約**：evaluate 是 `&self`，不 mutate；mutation 走 `apply_fill`，純 in-mem。

### §4.3 與既有 Strategy + Pipeline 的關係（不衝突）

| 既有 module | replay 端 | 衝突？ |
|---|---|---|
| `crate::strategies::*` | 直接 `Box<dyn Strategy>` 重用 | 無 |
| `crate::intent_processor::IntentProcessor` | **不用** — 重做 mini-pipeline | 0 衝突（V3 §6.2 forbidden 已豁免） |
| `crate::paper_state::PaperState` | **不用** — 改 `ReplayPaperState` | 0 衝突（V3 §6.2 #5 #15 forbidden） |
| `openclaw_core::guardian::Guardian` | 直接 import 使用 | 無 |
| `risk_checks::check_order_allowed` | 直接 import 使用 | 無 |
| `ml::kelly_sizer::compute_kelly_qty` | 直接 import 使用 | 無 |
| `tick_pipeline::TickContext` | 直接 import 使用 | 無（純 borrow struct） |

---

## §5. Parameter-Delta Proof 設計（acceptance A4 / A5）

### §5.1 Strategy parameter delta（A4）

**Fixture**：同一 manifest（同 fixture_uri / window_start_ms / window_end_ms），但兩 ID 不同 strategy_config_sha256。

```python
# tests/replay/test_strategy_param_delta.py
def test_grid_trading_param_delta_changes_decisions(replay_client, demo_actor):
    # baseline: grid_count=10
    baseline_payload = {**fixture_manifest, "strategy_params": {"grid_count": 10}}
    baseline_exp_id = replay_client.register(baseline_payload).json()["experiment_id"]

    # candidate: grid_count=20
    candidate_payload = {**fixture_manifest, "strategy_params": {"grid_count": 20}}
    candidate_exp_id = replay_client.register(candidate_payload).json()["experiment_id"]

    # /run both
    baseline_run = replay_client.run(baseline_exp_id)
    candidate_run = replay_client.run(candidate_exp_id)

    # Assert: simulated_fills 不同
    baseline_fills = pg_query("SELECT side, qty, price FROM replay.simulated_fills WHERE experiment_id=%s ORDER BY ts_ms", [baseline_exp_id])
    candidate_fills = pg_query(... [candidate_exp_id])
    assert baseline_fills != candidate_fills, "Strategy param delta did NOT change replay decisions"
    assert len(candidate_fills) >= 2 * len(baseline_fills), "grid_count=20 應該有更多 fill"
```

### §5.2 Risk parameter delta（A5）

**Fixture**：同 strategy_config_sha256，但兩 ID 不同 risk_config_sha256（如 `position_size_max_pct=2` vs `=10`）。

```python
def test_risk_param_delta_changes_reject_pattern(replay_client, demo_actor):
    # baseline: position_size_max_pct=2 (tight)
    baseline_payload = {**fixture_manifest, "risk_overrides": {"position_size_max_pct": 2.0}}
    baseline_exp_id = ...

    # candidate: position_size_max_pct=10 (loose)
    candidate_payload = {**fixture_manifest, "risk_overrides": {"position_size_max_pct": 10.0}}
    candidate_exp_id = ...

    baseline_run = replay_client.run(baseline_exp_id)
    candidate_run = replay_client.run(candidate_exp_id)

    # Assert: rejected pattern 不同
    baseline_rejects = pg_query("""
        SELECT payload->>'rejected_gate' AS gate, COUNT(*)
        FROM replay.simulated_fills
        WHERE experiment_id=%s AND payload->>'risk_decision'='rejected'
        GROUP BY gate
    """, [baseline_exp_id])
    candidate_rejects = pg_query(... [candidate_exp_id])
    assert sum(baseline_rejects) > sum(candidate_rejects), "tight risk should reject more intents"
```

### §5.3 strategy_config_sha256 / risk_config_sha256 wiring

**現狀**：
- V049 `replay.experiments` 已含 `strategy_config_sha256` + `risk_config_sha256` columns（V049 line 288-289）— Sprint A 已 ship。
- 但 Sprint A `experiment_registry.py:registration` 路徑寫的是空字串或 placeholder（**need verify**）。

**R5 必修**：experiment_registry register 端必接到 manifest_payload 的 `strategy_params` + `risk_overrides` field 計 sha256（**重用** R2-T3 `compute_manifest_canonical_bytes` 的 sort_keys+separators contract）並寫入。

---

## §6. Per-Decision Evidence Schema 設計

### §6.1 不新加 V### migration（PA push back）

**PM open question**：「evidence schema reuse simulated_fills.payload vs 新 table（V0XX migration）？」

**PA 強推 reuse `replay.simulated_fills.payload jsonb`**：

| 選項 | 工時 | 風險 | 可維護性 |
|---|---|---|---|
| A. reuse simulated_fills.payload | 0.5d schema + 1d writer | 低 | 高（jsonb 擴展） |
| B. 新 V055 replay.decision_evidence table | 2d schema + 2d writer + 2d FK | 高（新 FK、新 idempotency、新 retention） | 中 |
| C. 新加 simulated_fills column | 1d schema + 1d migration + V050 col 數變動 17→19 | 中（破 V050 17-col contract） | 低 |

**PA 選 A**：
- `payload jsonb NOT NULL DEFAULT '{}'::jsonb` 已存在（V050 line 179）— 0 schema 改動
- jsonb 擴展不破 17-col contract
- writer 端只需在 `simulated_fills_writer.py:map_fill_to_v050_row` (line 377) 增加 payload 子鍵

**Payload schema 擴展**（reuse `payload jsonb`）：
```json
{
  "decision_evidence": {
    "strategy_decision": {
      "intent_signature": "sha256:...",
      "confidence": 0.85,
      "indicator_snapshot_summary": "atr=0.0142 hurst=mean_reverting bb_bw=0.018",
      "is_long": true,
      "intended_qty": 1.234e-3,
      "intended_price": 65432.10
    },
    "risk_decision": {
      "outcome": "accepted | rejected",
      "rejected_gate": "2.0_guardian | 1.5_dup | 2.7_admission | null",
      "rejected_reason": "leverage 4.5x > limit 3.0x | null",
      "guardian_verdict": "Approved | Modified | Rejected",
      "guardian_score": 0.42,
      "kelly_qty": 1.5e-3,
      "p1_max_qty": 2.0e-3,
      "final_qty": 1.234e-3
    },
    "fill_outcome": {
      "filled_qty": 1.234e-3,
      "fill_price": 65432.10,
      "slippage_bps": 0.0,    // R6 calibrated 後填，B 階段 = 0
      "fee_bps": 0.0          // R6 fee model 後填，B 階段 = 0
    }
  }
}
```

### §6.2 哪些 fill 寫此 payload

- **Accepted intent → simulated fill**：寫 strategy_decision + risk_decision (outcome=accepted) + fill_outcome
- **Rejected intent → "rejected fill"** ：依 V050 schema 設計，simulated_fills 是「per fill」table — rejected intent 沒有 fill。**設計選擇**：
  - 選項 (a)：每個 rejected intent 也寫 `simulated_fills` row，但 `qty=0 price=NaN` + `payload.risk_decision.outcome=rejected`。**問題**：破 V050 NOT NULL 約束（qty / price NOT NULL）。
  - 選項 (b)：rejected intent **不寫** simulated_fills，改在 `replay.run_state.run_summary jsonb`（V045）寫 reject summary。**問題**：失去 per-decision lineage。
  - 選項 (c) **PA 推薦**：rejected intent 寫 simulated_fills，`qty=0.0`（V050 schema 允許 numeric 0），`price` 用 intended_price（intent.limit_price 或 mid price snapshot）。**0 schema 改動**。
- **No intent at tick**：strategy `on_tick` 回 `Vec::new()` — 不寫任何 simulated_fills（per-tick noise 太大）。

### §6.3 V050 fill_index uniqueness

V050 已有 `(experiment_id, fill_index) UNIQUE` 約束（need verify 但 line 179 上下文應有）。**rejected fill 與 accepted fill 共用 fill_index 序列**，順序保證 `(strategy_emit_ts_ms, fill_index)` 單調遞增。

---

## §7. R5 Task DAG + 並行決策

### §7.1 R5 task 分解（Sprint B2 假設 PA push back accept）

| Task | scope | LOC est | 並行？ | 依賴 |
|---|---|---:|---|---|
| R5-T1 | `replay/strategy_adapter.rs` 新 module — `ReplayStrategyAdapter` | +150 (Rust) | ✅ R5-T2 並行 | 0 |
| R5-T2 | `replay/risk_adapter.rs` 新 module — `ReplayRiskAdapter` + `ReplayPaperState` | +250 (Rust) | ✅ R5-T1 並行 | 0 |
| R5-T3 | `replay/runner.rs::IsolatedPipeline::execute` 重寫 — 替換 synthetic walker，整合 T1+T2 | +200 (Rust，replace ~50) | ❌ 序列 | T1+T2 |
| R5-T4 | `bin/replay_runner.rs` 主迴圈 — wire StrategyFactory + ReplayPaperState boot | +50 (Rust) | ❌ 序列 | T3 |
| R5-T5 | `replay/simulated_fills_writer.py::map_fill_to_v050_row` — payload schema 擴展 | +60 (Python) | ✅ T6 並行 | 0 |
| R5-T6 | `replay/experiment_registry.py::register` — strategy_config_sha256 / risk_config_sha256 wire | +40 (Python) | ✅ T5 並行 | 0 |
| R5-T7 | strategy adapter integration test — grid_trading + ma_crossover pilot | +250 (Rust+Python) | ✅ T8 並行 | T1-T6 |
| R5-T8 | parameter-delta proof test — A4 + A5 fixture | +200 (Python) | ✅ T7 並行 | T5-T6 |
| R5-T9 | E2 review pass + E4 regression | (review only) | ❌ 序列 | T1-T8 |

**Wave 結構**：

```
Wave 1（並行 4 tasks）：T1 / T2 / T5 / T6
  T1+T2 同 sub-agent（Rust，同 crate） vs T5+T6 同 sub-agent（Python，同檔／不同檔均可）

Wave 2（序列 2 tasks）：T3 → T4
  必序列；T4 依 T3 重寫的 IsolatedPipeline

Wave 3（並行 2 tasks）：T7 / T8

Wave 4（序列）：T9
```

**E1 派發建議**（4 sub-agent 並行 Wave 1）：
- E1-A: R5-T1 (Rust strategy_adapter.rs) — isolated（新檔）
- E1-B: R5-T2 (Rust risk_adapter.rs) — isolated（新檔）
- E1-C: R5-T5+T6 (Python writer + registry 同檔系，但不同 method) — **不需 isolation**
- 4 並行成本 ~1d wall

**順序成本**：
- Wave 2: T3 0.5d + T4 0.25d
- Wave 3: T7+T8 並行 1d
- Wave 4: T9 0.5d

**總 wall**: 1d (W1) + 0.75d (W2) + 1d (W3) + 0.5d (W4) = **3.25d wall**

### §7.2 PM override 路徑（若 Sprint B 不拆，R4+R5 同 sprint）

| 額外任務 | 工時 |
|---|---|
| LOC 預算 first：拆 replay_routes.py thin handler 到 sub-router | 0.5d（R0-T0） |
| R4 4 task | 1.5d |
| R5 9 task | 3.25d |
| **必序列**：R4 開工前先 R0-T0；R5 開工前 R4 不阻塞（不同檔）但 review 排程衝突 | +0.5d 排程 buffer |

**單 sprint 總 wall**：5.75d — 接近 1 週 sprint 上限。Blocker chain 風險倍增（如同 Sprint A R3 round 6）。

---

## §8. Hidden Risk Audit

### §8.1 replay_routes.py 1500 LOC EXACT cap — Sprint B 第一手必拆

**現狀**：1500 LOC = §九 1500 硬上限 0 margin。**任何**新加 import / 函式 / endpoint 都破。

**R4 / R5 改動會否觸 replay_routes.py？**
- R4：純 frontend，0 改動 replay_routes.py。
- R5-T5/T6：在 `replay/simulated_fills_writer.py` + `replay/experiment_registry.py` 內，0 改動 replay_routes.py。
- R5-T7/T8：純 test，0 改動 replay_routes.py。

**結論**：R4+R5 **理論上**不破 replay_routes.py 1500 cap。**但**：
- 若 PM 後續加任何 endpoint（如 `/api/v1/replay/decision_trace/{exp_id}`），會立刻破。
- **PA 強推 R0-T0 前置任務**：把 replay_routes.py 內 8 個 endpoint 各拆 thin handler 到 `replay/{health,run,verify,list,report,run_finalize}_route.py`（已部分 ship），把 replay_routes.py 本身瘦身回 800-1000 LOC（§九 warning line 800 內）。
- R0-T0 估 0.5-1d wall（純 refactor，0 邏輯改動，但 E2/E4 必嚴審）。

### §8.2 strategy module 之間共享 IndicatorEngine / KlineManager

**Replay 端 strategy 需要 `&IndicatorSnapshot`（TickContext.indicators）**。

**現狀**：
- IndicatorSnapshot 由 `KlineManager → IndicatorEngine` 計算
- Live 路徑：tick_pipeline 內 KLINE_MANAGER 是 mutable singleton
- Replay 端：**不能用** Live KLINE_MANAGER（V3 §6.2 forbidden）

**選項**：
- A. **預計算**：fixture 內含 pre-computed IndicatorSnapshot（fixture builder 端跑 KlineManager 一次寫到 fixture.json）
- B. **Replay 端重算**：fixture 只含 OHLCV，replay binary 內建 mini-IndicatorEngine
- C. **Sprint B2 簡化**：跳過 indicators，給 strategy 一個「無 indicator」TickContext（grid_trading 不依賴 indicators，仍可跑；ma_crossover / bb_breakout / bb_reversion **必需** indicator）

**PA 推薦 A**：fixture builder 端跑 IndicatorEngine 一次 → 寫 IndicatorSnapshot 到 fixture.json events[i].indicators 子鍵。R5-T1/T2 直接讀。
- 0 副作用 — fixture 是不可變 input
- 與 §五 `KlineManager → IndicatorEngine → SignalEngine` 主路徑解耦
- 對 R6 fee calibration 也有利（calibrated fixture 可帶歷史 fill snapshot）

**LOC 影響**：fixture_loader.rs 加 indicators 解析 +30 LOC；R5-T1 無需重算。

### §8.3 ReplayProfile 與 Sprint 1 Track B forbidden_guard 互動

**確認**：
- `forbidden_guard.rs` `enforce_at_runtime(action_label)` 對「acquire_lease / ipc_server / build_exchange_pipeline / canary_writer / database / paper_state / bybit_*」symbol 做 startup 拒絕（compile-time + runtime 雙層）。
- R5-T1 的 `Box<dyn Strategy>` 型別擦除 — strategy 自身**不**呼叫上述 forbidden symbol（已在 §1A 確認）。
- R5-T2 `ReplayRiskAdapter` 直接 import `Guardian / check_order_allowed / compute_kelly_qty` — 三者皆**不**在 forbidden list（V3 §6.2 forbidden 是 `paper_state / canary_writer / DecisionFeatureMsg / bybit_*`）。
- `ReplayPaperState` 是新型別，**不**等於 `crate::paper_state::PaperState` — symbol audit 不會誤判（type name 不同）。

**潛在 risk**：
- 若 R5-T2 不慎 `use crate::paper_state::PaperState;` → symbol audit 會立刻 fail-loud。E2 必查 import 列表。
- 若 R5-T3 `IsolatedPipeline::execute` 不慎 `use crate::canary_writer;` → 同上。

### §8.4 multi-worker uvicorn race（Sprint A R3 round 6 M-1 fix mirror）

**Sprint A R2 round 2 M-1 fix**：`replay.experiments` register endpoint 在多 worker uvicorn 下需 advisory lock + idempotency cache（`experiment_registry.py:_REGISTER_IDEM_CACHE` 雙層）。

**R5 端風險**：
- R5-T6 改 register 端 strategy_config_sha256 / risk_config_sha256 計算 — 不改 lock 邏輯 ✅
- R5-T7/T8 並行測試會多 worker 同時 register — 既有 advisory lock 已防 race ✅
- R5-T3/T4 replay_runner subprocess **不**走 register endpoint，無 race risk ✅

### §8.5 canonical_bytes contract（R5 不應動 manifest_signer）

**R5-T6 register 端寫 strategy_config_sha256 / risk_config_sha256**：
- 計算路徑：`sha256(canonical_bytes(strategy_params))` + `sha256(canonical_bytes(risk_overrides))`
- **必須**重用 `experiment_registry.py:compute_manifest_canonical_bytes` 的 sort_keys+separators+ensure_ascii=False contract（line 416）
- **禁止**重複實作（會破 8/8 cross-language fixture regression test）

**E2 必查**：R5-T6 import `compute_manifest_canonical_bytes` 而非直接 `json.dumps(..., sort_keys=True)`。

### §8.6 跨語言一致性（13/13 invariant 維持）

**xlang_consistency 8/8 fixture regression test** 鎖定 `manifest_signer` Python+Rust HMAC byte-equal。R5 不應動 manifest_signer，但：
- R5-T6 計算 strategy_config_sha256 是 sha256(canonical_bytes)，**不是** HMAC sign。所以**不**走 ManifestSigner 路徑。
- 但 `compute_body_hash` (manifest_signer.py:216) 與 `compute_manifest_canonical_bytes` 的 contract 是同源 — R5 reuse 即可。

### §8.7 Decision Lease retrofit feature flag interaction

**現狀**（CLAUDE.md §三）：
- AMD-2026-05-02-01 Path A LAND（commit `dbcf845b`）
- feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` default OFF
- ~05-15 P0-EDGE-2 後 operator action flip canary 24h

**R5 風險**：
- 若 R5-T2 ReplayRiskAdapter **不**走 IntentProcessor::process_with_features 主函式，**不**經 router.rs Gate 1.4 — flag flip ON/OFF 對 replay 路徑均**無影響**。
- 若 R5-T2 **誤用** GovernanceCore::acquire_lease → 即使 ReplayProfile::Isolated，也會被 facade 短路為 LeaseId::Bypass（不破，但 audit log 會誤增 row）。

**E2 必查**：R5-T2 不 `use openclaw_core::governance_core::GovernanceCore`（理由：Guardian 已從 governance_core 解耦，replay 只需 Guardian）。

---

## §9. Hidden Risk: Cross-Language Boundary

### §9.1 Strategy 邏輯在 Rust，replay 跑在 Rust binary subprocess

**現狀**：
- Live strategy = Rust（`crate::strategies::*`）
- Live IntentProcessor = Rust
- Live Pipeline = Rust（`tick_pipeline/mod.rs`）
- replay_runner = 獨立 Rust binary（`bin/replay_runner.rs`）
- Python control_api_v1 spawn replay_runner subprocess（`route_helpers.py::spawn_replay_runner`）

**R5 設計**：
- ReplayStrategyAdapter / ReplayRiskAdapter 在 **Rust 端**（與 strategy module 同 crate）
- Python 不需重做 strategy / risk 邏輯
- Python 端只需：在 register 計 sha256 + 在 simulated_fills_writer 解析 payload + 寫 PG

### §9.2 跨語言一致性風險（與 Sprint 1 Track B 既有 8/8 test 對齊）

| 跨語言 contract | 影響 |
|---|---|
| canonical_bytes（manifest sign） | R5 reuse，0 風險 |
| sha256(strategy_config) | R5 新加，需測 Python+Rust 算同一 sha（**E4 必加 fixture test**） |
| simulated_fills payload jsonb | Rust 寫入 → Python 讀出 → PG 存。jsonb 自 native，無 encoding bug |

**R5-T6 sha256 跨語言 test**：
```python
# tests/replay/test_config_sha_xlang.py
def test_strategy_config_sha_python_matches_rust():
    canonical_input = {"grid_count": 10, "spacing_mode": "geometric"}
    py_sha = hashlib.sha256(json.dumps(canonical_input, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    # Rust 端寫一支 helper binary 產生同 input 的 sha → assert 一致
    rust_sha = subprocess.run(["target/debug/test_canonical_sha", "..."]).stdout.decode().strip()
    assert py_sha == rust_sha, f"xlang sha mismatch: py={py_sha} rust={rust_sha}"
```

### §9.3 ReplayProfile 跨 Rust/Python 一致性

**現狀**：ReplayProfile 是 Rust enum（`profile.rs:115`）。Python 端不接 ReplayProfile（Python 只 spawn binary）。

**R5 假設**：replay 走 Isolated profile（plan §4 hard boundary）。binary 端在 main 用 `fail_closed_assert_isolated` 強制（profile.rs:316）。Python 端不需感知。

**E2 必查**：R5-T4 `replay_runner main` 第一行調 `profile.fail_closed_assert_isolated().expect(...)`（Wave 3 既 ship）— 0 退化。

---

## §10. Sprint B Acceptance（per plan §6 + §11）

### §10.1 R4 acceptance（plan §6.R4）

| # | acceptance | 證據 |
|---|---|---|
| R4-A1 | Replay tab is enabled only when backend health is green | `/health` mock 三 state DOM assert |
| R4-A2 | UI never labels current smoke replay as calibrated | UI render execution_confidence='none' badge for synthetic_replay |
| R4-A3 | No manual order controls reappear | DOM grep no `submit-order` button visible |
| R4-A4 | 5 state（empty / running / failed / completed / degraded）UI 全有對應 | playwright e2e 5 fixture |

### §10.2 R5 acceptance（plan §6.R5 + §11 A4/A5）

| # | acceptance | 證據 |
|---|---|---|
| R5-A1 | A known parameter delta changes replay decisions in a controlled fixture（A4） | §5.1 strategy delta test |
| R5-A2 | A known risk limit delta changes pass/reject outcomes（A5） | §5.2 risk delta test |
| R5-A3 | Replay output includes both accepted and rejected decision records | simulated_fills.payload.risk_decision.outcome ∈ {'accepted','rejected'} 各 ≥1 row |
| R5-A4 | No forbidden live symbols appear in nm / runtime guard checks | replay_runner_symbol_audit.sh 0 hit on `acquire_lease|ipc_server|build_exchange_pipeline|canary_writer|paper_state` |
| R5-A5 | signal_id 在 replay output | simulated_fills.payload.decision_evidence.strategy_decision.intent_signature ≠ NULL |
| R5-A6 | rejected reason 在 replay output | simulated_fills.payload.decision_evidence.risk_decision.rejected_reason ≠ NULL（rejected case） |

---

## §11. LOC 預算 + 拆檔策略

### §11.1 LOC 估算（per task）

| File | Δ LOC | Notes |
|---|---:|---|
| `tab-paper.html` | +20 | R4 frontend |
| `app-paper.js` | +140 | R4 frontend |
| `tests/...html_smoke` | +150 | R4 test |
| `replay/strategy_adapter.rs` (new) | +150 | R5-T1 |
| `replay/risk_adapter.rs` (new) | +250 | R5-T2 |
| `replay/runner.rs` | +200 (replace 50 stub) | R5-T3 |
| `bin/replay_runner.rs` | +50 | R5-T4 |
| `replay/simulated_fills_writer.py` (602→662) | +60 | R5-T5 |
| `replay/experiment_registry.py` (985→1025) | +40 | R5-T6 |
| `tests/replay/test_strategy_param_delta.py` (new) | +100 | R5-T7-A4 |
| `tests/replay/test_risk_param_delta.py` (new) | +100 | R5-T7-A5 |
| `tests/replay/test_decision_evidence_payload.py` (new) | +100 | R5-T7-evidence |
| `tests/replay/test_config_sha_xlang.py` (new) | +50 | R5-T7-xlang |
| `tests/replay/test_replay_strategy_adapter_smoke.rs` (new) | +200 | R5-T7-rust |
| `tests/replay/test_replay_risk_adapter_smoke.rs` (new) | +200 | R5-T7-rust |
| **Total** | **+1810 LOC** | (~80 src + ~1300 test 比例正常) |

### §11.2 §九 1500 LOC cap 衝突檢查

| 檔案 | pre-Sprint B | post-Sprint B | 警告/硬上限 |
|---|---:|---:|---|
| `replay_routes.py` | 1500 | 1500 | 🛑 **硬上限 EXACT** — R4/R5 不破，但**剩餘 0 margin**，下次 wave 會破 |
| `route_helpers.py` | 1498 | 1498 | ⚠️ baseline+5 margin（Sprint A R3 round 6 PA design 已記） |
| `manifest_signer.py` | 757 | 757 | warning(800) 內 |
| `experiment_registry.py` | 985 | **1025** | warning(800) 已破，但 < 1500 硬上限 |
| `simulated_fills_writer.py` | 602 | **662** | warning(800) 內 |
| `tab-paper.html` | 909 | **929** | warning(800) 已破，< 1500 |
| `app-paper.js` | 447 | **587** | warning(800) 內 |
| 新檔（Rust） | 0 | **400-600** | 各檔 < 800 warning |

**結論**：R4+R5 **不**直接破 §九 1500 硬上限，但 `replay_routes.py` 已在 cap 邊緣。**PA 強推 R0-T0**（拆 thin handler）作為 Sprint B 第一手任務（即使 PM 不拆 B1+B2 也建議做）。

### §11.3 R0-T0 拆檔策略（PA 強推）

**目的**：把 replay_routes.py 從 1500 LOC 瘦身回 800-1000 LOC，給 R5 + 後續 Sprint C/D 留 LOC 空間。

**8 endpoint 已拆部分 / 未拆**：
- ✅ 已拆：`/health/signature` → `health_route.py`（need verify）
- ✅ 已拆：`/manifest/verify` → `manifest_signer.py`（need verify）
- ✅ 已拆：`/run/finalize` → `run_finalize_route.py` (593 LOC)
- ✅ 已拆：`/report/{id}` → `report_route.py` (506 LOC)
- ❌ 未拆（仍在 replay_routes.py 內）：`/run` / `/list` / `/health` / `/{id}/status`

**R0-T0 動作**：把 `/run` / `/list` / `/health` / `/{id}/status` 各抽到 `replay/{run,list,health,status}_route.py` thin handler（每檔 ~150-300 LOC，replay_routes.py 變 router 註冊 + import shim ~400 LOC）。

**LOC 影響**：replay_routes.py 1500 → ~400 (router only)。新增 4 檔各 ~250 LOC 平均。

**E2/E4 風險**：純 refactor 0 邏輯改動，但 import 拓撲 + uvicorn route 註冊順序敏感。E2 必對比 pre-/post- diff route registration 順序 byte-equal。

---

## §12. PM Open Questions

### Q1: Sprint B 拆 B1+B2，還是堅持單一 sprint 涵蓋 R4+R5?

**PA 推薦**：拆 B1（R4 + R0-T0）+ B2（R5 grid_trading + ma_crossover pilot）。

**若 PM 拒拆**：必同步 accept R0-T0 作為 Sprint B 第一手 task；**且** Sprint B wall budget 至少 6d（不含 review buffer）。

### Q2: R5 IMPL 在 Rust 還是 Python?

**PA 答**：**Rust**（強推）。

理由：
- Strategy 全 Rust（`crate::strategies::*` 5 module）
- Risk 全 Rust（`Guardian` / `check_order_allowed` / `compute_kelly_qty`）
- replay_runner 已是 Rust binary
- Python 端僅做 manifest register + simulated_fills writer + UI

若用 Python 端 wrap → 必跨 IPC（PyO3）→ 違反 V3 §6.2「不接 ipc_server」 → 直接 fail。

### Q3: 5 strategy 全做 vs 先 grid_trading + ma_crossover pilot?

**PA 答**：**pilot first**。

理由：
- grid_trading 是唯一 net positive — 最有價值先驗證
- ma_crossover 是 7d net negative -5.09 — 第二有價值（測 risk delta）
- bb_breakout live_demo 14d 0 fires（FIX-26-DEADLOCK-1）— sample 不足，Sprint C
- bb_reversion 7d 7 fills — sample 太少，Sprint C
- funding_arb V2 棄策略路徑（commit `a19797d`）— 不必涵蓋

### Q4: evidence schema reuse `simulated_fills.payload jsonb` vs 新 V055 table?

**PA 答**：**reuse simulated_fills.payload jsonb**（§6.1 詳述）。

理由：0 schema 改動 / 0 FK / 0 retention 新增。

### Q5: rejected intent 寫不寫 simulated_fills?

**PA 答**：**寫**，`qty=0.0` + `price=intended_price`。

理由：保 per-decision lineage；不破 V050 17-col contract。

### Q6: indicators 預計算 vs replay 端重算 vs Sprint B2 簡化跳過?

**PA 答**：**fixture builder 預計算寫到 fixture.json**（§8.2 詳述）。

理由：與 Live KlineManager → IndicatorEngine 路徑解耦；ma_crossover/bb_breakout 不能跳過 indicators。

### Q7: 是否同 sprint 加 R6 fee model（plan §9 是 Sprint C scope）?

**PA 答**：**不加**。

理由：plan §9 已切 Sprint C；R6 涉 calibration 數據（demo/live_demo 歷史 fill）+ QC 數學審計，不適合與 R5 並行。R5 階段 fee_bps=0、slippage_bps=0 為 acceptable（acceptance A6 在 Sprint C 才驗）。

### Q8: 是否疊 Decision Lease feature flag flip canary?

**PA 答**：**NO**。

理由：CLAUDE.md §三 既登 `~05-15 P0-EDGE-2 後 operator action`。Sprint B 改動完全不觸 lease 路徑（§8.7 已驗），疊上來反而增加 deploy window 風險。

### Q9: R5 acceptance test 是否需 QC 介入（fixture 數學）?

**PA 答**：**1h soft consult**（非強制）。

理由：parameter delta 證明本身是純功能性 (input → output 變了就算過)，不涉 calibration 數學。但若 PM/QC 要求「delta 值需有經濟意義（例如 grid_count 10→20 應致 fill 增 X%）」就需 QC 拍板。**PA 默認 functional delta 即可**。

### Q10: R5 IMPL 是 wholesale replace synthetic walker，還是 feature flag opt-in?

**PA 答**：**wholesale replace**。

理由：synthetic walker 已是 R5 的 placeholder；不需 dual-track（會增加 LOC + maintenance 負擔）。但 R5-T3 實作必加 fail-closed：若 replay binary 收到 fixture 沒 strategy_config_sha256 → fail-loud（**禁** silent fallback to synthetic walker）。

---

## §13. PA Sign-off Readiness（report 用）

**Hard boundary check**（CLAUDE.md §四）：
- ❌ 未觸 `live_execution_allowed`（R5 完全不接 IPC / order dispatch）
- ❌ 未觸 `max_retries=0`（不變）
- ❌ 未觸 `OPENCLAW_ALLOW_MAINNET`（replay binary 不接 mainnet）
- ❌ 未觸 `live_reserved`（不接 live mode）
- ❌ 未觸 `authorization.json`（不接 live_authorization）
- ❌ 未觸 `decision_lease`（ReplayProfile::Isolated.requires_lease=false 強制）
- ✅ 0 violation

**Root principle check**（16 條）：
- ✅ 16/16 — 加強 #1（單一寫入口：replay 物理上不寫 trading.*）+ #2（讀寫分離：feature gate）+ #3（AI ≠ 命令：replay 是 advisory）+ #4（策略不繞風控：ReplayRiskAdapter 復刻 8 Gate 跳過 lease/auth）+ #6（失敗默認收縮：profile fail-closed assert）+ #7（學習 ≠ 改寫 Live：replay 衍生只入 replay.* 不入 learning.*）+ #8（交易可解釋：每 decision 進 simulated_fills.payload）。

**E2/E4 重點審查 3 點**（per profile.md §47-49）：
1. **R5-T1/T2 import audit**：`grep -E "use crate::(paper_state|canary_writer|ipc_server|bybit|governance_hub|live_authorization)" replay/strategy_adapter.rs replay/risk_adapter.rs` 0 hit。
2. **R5-T3 IsolatedPipeline::execute 0 silent fallback**：synthetic walker 路徑徹底刪；fixture 缺 strategy_config_sha256 → fail-loud。
3. **R5-T6 canonical bytes contract reuse**：experiment_registry register 端用 `compute_manifest_canonical_bytes` 而非自寫 `json.dumps(..., sort_keys=True)`。

---

## §14. 結論 + Operator decision needed

### Sprint B 推薦切分

```
Sprint B1（1.5-2d wall）：
  - R0-T0: replay_routes.py 拆 thin handler（必前置）
  - R4: UI Enable
Sprint B2（3-5d wall）：
  - R5: grid_trading + ma_crossover pilot
  - 不做：bb_breakout / bb_reversion / funding_arb（Sprint C 補完）
```

### PM Decision Required

1. ✅ Accept B1+B2 切分（PA 強推）
2. ⚠️ Reject 切分，single Sprint B 涵蓋 R4+R5（接 §7.2 PM override 路徑成本）
3. 其他切分提案

**PA 建議**：選 (1)。

**派發前 sub-agent fetch 提醒**（feedback_fetch_before_dispatch.md）：派發 R5-T1/T2 前 `git fetch && git branch -r | grep -E "(replay|sprint_b)"` 確認無 sibling CC 已開 feature branch。

---

## §15. Appendix — File Inventory Quick Ref

### R4 改動檔案
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/app-paper.js`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/...html_smoke`（new）

### R5 改動檔案
- `rust/openclaw_engine/src/replay/strategy_adapter.rs`（new）
- `rust/openclaw_engine/src/replay/risk_adapter.rs`（new）
- `rust/openclaw_engine/src/replay/runner.rs`（rewrite execute）
- `rust/openclaw_engine/src/bin/replay_runner.rs`（wire StrategyFactory）
- `rust/openclaw_engine/src/replay/mod.rs`（pub mod 新加）
- `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py`
- `tests/replay/*`（new — 6 file）

### R0-T0 拆檔（PA 強推）
- `app/replay_routes.py`（1500 → ~400）
- `replay/run_route.py`（new）
- `replay/list_route.py`（new）
- `replay/health_route.py`（new）
- `replay/status_route.py`（new）

### Reference docs
- Plan V1: `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md`
- Plan V3: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
- Sprint A R3 round 6 design: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_task_dag.md`
- AMD-2026-05-02-01: `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`

---

**END OF REPORT**

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md
