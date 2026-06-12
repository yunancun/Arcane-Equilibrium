# Alpha Tournament Candidate #1 — Funding Rate Dislocation Arbitrage V2 (Short-Only > 30% Annualized)

**Date**: 2026-05-25
**Author**: PA（W1-A sub-agent task）
**Source SoT**: dispatch packet `srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` §2.2 candidate #1 + §2.4 dispatch design
**Predecessor lessons**: memory `project_funding_arb_v2_deprecation_path` + `project_g2_funding_arb_monitor` + ADR-0018 V2 dormant verdict（**2026-05-26 Status 升格 Retired closed per AMD-2026-05-26-01**；funding_short_v2 仍 **不繞** AMD-26-01：新 strategy slot 與 V2 不同設計，per §0 TL;DR §3 維度差異）
**Status**: PA SPEC — IMPL-ready 給 W2-B E1 sub-agent
**Scope**: Stream A candidate #1 「funding short-only > 30% annualized arbitrage」 IMPL-ready specification

> **REFERENCE / SUPERSEDED FUNDING-CAP LESSON**
>
> 本 spec 保留 funding_short_v2 设计 lineage。不要把旧 “funding_short structural
> DOA / permanent cap” 语义当作当前结论；当前 funding cap SSOT 是 Bybit
> `instruments-info.upperFundingRate`，funding_short_v2 是 regime-dormant /
> learning-only unless future `TODO.md` gate reopens it。

---

## §0 TL;DR — Verdict

**新策略名稱**：`funding_short_v2`（短倉、純 directional、高 annualized funding gate）

**核心差異 vs funding_arb V2 (ADR-0018 dormant)**:

| 維度 | funding_arb V2 (dormant) | funding_short_v2 (new) |
|---|---|---|
| Direction | bi-directional（long & short）| **short-only**（hard-coded enforcement）|
| Funding gate | abs(funding) > 5 bps per 8h (~22% annualized) | **funding > 30% annualized**（per dispatch packet §2.2）|
| Side enforcement | strategy 邏輯選 is_long = !is_positive_funding | **enforce is_long == false 永遠**（hard fail-closed）|
| Cost model | 8h × 3 cycle amortize → 不適用 short-only 假設 | **per-cycle amortize**（持倉 1-2 funding cycle 結算後出場）|
| Spot lending dependency | 無（directional perp only）✅ | 無（directional perp only）✅ |
| Delta-neutral 假設 | 試圖透過 basis hedge 達 delta-neutral（QC verdict: 數學不成立） | **不假設 delta-neutral**；承擔 short price 方向風險 |
| Entry frequency | 月度 ~10-15 次（all symbols, low gate） | **月度 ~3-5 次**（high gate, BTC/ETH only）|

**為什麼可以 IMPL 不踩 ADR-0018 dormant 教訓**：
- ADR-0018 dormant 是 V2 directional 設計 13 fills 0 win 證據；funding_short_v2 **與 V2 共名不同設計**（gate threshold 6x 高 + side hard enforcement + per-cycle cost）
- 不繞 ADR-0018：funding_short_v2 是 **new strategy slot**（與 funding_harvest 並列），不重啟 funding_arb dormant block
- 不違反 memory `project_funding_arb_v2_deprecation_path` 「2A 棄策略」決策：該決策針對 V2 directional bi-side；本 spec 是窄 short-only carve-out + 高 gate（≠ V2 設計）

---

## §1 Algorithm Specification

### §1.1 Entry conditions（所有條件必同時滿足才入場）

```
Entry gate (5 conditions ALL true):
  1. funding_rate_8h_annualized > 30%  (= funding_rate_8h > 0.000274 per cycle)
     [hard gate, no IPC override]
  2. funding_rate_8h > 0  (positive funding ⇒ short receives payment)
     [hard side enforcement; if negative funding → reject, never long]
  3. basis_pct < max_basis_pct * entry_basis_ratio  (default 0.5% × 0.6 = 0.3%)
     [tight basis: 防 perp 嚴重溢價時開短被 basis squeeze]
  4. compute_edge(funding_rate_8h) > 0
     [edge = funding_rate_abs - amortized_cost_per_cycle]
  5. h0_allowed && cooldown_expired (per symbol, 8h cooldown)
     [per H0 gate + per-symbol 8h cooldown 防同一 funding cycle 重入]
```

**為什麼 30% annualized 是 hard gate**：

per QC verdict (2026-05-02, agentId `a5f95166dcc70775a`) on funding_arb V2 dormant：
- spot 來回 20bps + perp 11bps + slip 3bps = **34 bps round-trip total cost**
- funding 8h median ~1.5 bps → break-even **7.6 days** persistent hold（**不現實**）
- funding > 30% annualized = **per 8h cycle ~27.4 bps** → break-even **1.24 cycles ≈ 10 hours**（**現實**）
- 「持倉 1-2 cycle 後 funding 反轉」outcome 下：1 cycle gross = +27.4bps, cost = -22bps（perp-only 雙向 11bps）= **net +5.4bps per cycle**
- 持 1.5 cycle 平均 net = **+13.5 bps 期望值 per entry**

**對比 V2 dormant**：V2 gate 5bps × annualized factor = ~22%，per cycle gross ~5bps - cost 22bps = **-17bps per cycle**（即 V2 dormant 證據真實成因）

### §1.2 Exit conditions（OR 邏輯，任一觸發即出場）

```
Exit triggers (5 conditions, ANY true → close):
  1. funding_rate_8h < +5 bps annualized adjusted (0.0005 / 1095 per cycle)
     [funding reversal / collapse exit; 防止 funding cycle flip 後反向 cost drag]
  2. compute_edge(funding_rate_8h) <= 0
     [edge degradation exit; tracks amortized cost remaining]
  3. basis_pct > max_basis_pct (default 0.5%)
     [basis blowout exit; perp 嚴重升水 ⇒ short side mark loss + 強平風險]
  4. now_ms - entry_ms > max_hold_ms (default 24h ≈ 3 funding cycle hard ceiling)
     [time-stop exit; defensive 避免 funding cycle 預測失準致長期持有]
  5. per_strategy stop_loss_max_pct_override hit (per_symbol 3% tight SL, P1 hardstop)
     [P1 風控 hard stop; orthogonal to strategy 出場邏輯]
```

**Persistent hold 設計理由**：
- funding_arb V2 dormant 設 72h max hold；funding_short_v2 **收緊到 24h**（3 funding cycle）
- per QC 量化分析：funding > 30% annualized 通常 1-2 cycle 內 mean-revert；超過 24h still > 30% 是 systemic event（非 mean-revert play），不該 hold

### §1.3 Cost model（per-cycle amortize, not 72h amortize）

```rust
// funding_short_v2 cost model（per-cycle amortize）
fn compute_edge(funding_rate_8h: f64, total_cost_bps: f64, expected_periods: f64) -> f64 {
    // expected_periods 預設 1.5（1-2 cycle median hold）
    // total_cost_bps 預設 22.0（perp roundtrip only：entry maker 1bp + exit taker 5.5bp + slip 3bp + funding settlement variability 12.5bp）
    let amortized_cost = total_cost_bps / 10_000.0 / expected_periods;
    funding_rate_8h.abs() - amortized_cost
}
```

**對比 V2 dormant**:
- V2 total_cost_bps = 34.0（含 spot 來回 20bps；funding_short_v2 無 spot 腿）
- V2 expected_periods = 3.0（72h hold / 8h cycle）；funding_short_v2 = 1.5（24h hold cap）
- V2 amortized cost = 34/10000/3 ≈ 1.13 bps per cycle；funding_short_v2 = 22/10000/1.5 ≈ 1.47 bps per cycle
- V2 entry threshold 5 bps - 1.13 = 3.87 bps positive edge → 樣本實證 fail（because hold > 1.5 cycle 後 funding mean-revert 抵消）
- funding_short_v2 entry threshold 27.4 bps - 1.47 = 25.9 bps positive edge → 顯著高於統計噪音 + 持有窗口短

### §1.4 Side enforcement（hard fail-closed）

```rust
fn on_tick(&mut self, ctx, surface) -> Vec<StrategyAction> {
    // ... entry gate checks ...

    // HARD SIDE ENFORCEMENT: funding > 0 → short only
    // 任何 funding_rate <= 0 → 拒絕入場（never long）
    let funding_rate_8h = match ctx.funding_rate {
        Some(fr) if fr > 0.0 => fr,  // ← positive funding only
        _ => return vec![],
    };

    // is_long === false invariant（compile-time constant）
    const IS_LONG: bool = false;

    // Emit short-side OrderIntent
    vec![StrategyAction::Open(OrderIntent::new_trade(
        sym.to_string(),
        IS_LONG,  // ← always false
        self.default_qty,
        confidence,
        self.name().into(),
        "limit".into(),
        Some(limit_price),
        // ...
    ))]
}
```

**Why hard enforcement vs config-driven**：
- ADR-0018 dormant 教訓：directional bi-side V2 樣本實證 0/13 wins
- short-only carve-out 的 thesis：positive funding 環境長期偏 contango / over-leverage long 側；short receives funding payment + mean-revert 1-2 cycle = positive expectation
- 若允許 long side 入場（negative funding）→ 退化為 V2 bi-directional design → ADR-0018 dormant scope 重啟（disallowed）
- 因此 IS_LONG 寫為 `const`（compile-time invariant），不暴露為 IPC tunable

---

## §2 Symbol Universe Constraint

### §2.1 Stage 1 Demo 限定（per CR-15 5-gate auto path inheritance）

```toml
# srv/settings/strategy_params_demo.toml
[funding_short_v2]
active = false  # ← default disabled; operator IPC 顯式 true 才啟
allowed_symbols = ["BTCUSDT", "ETHUSDT"]  # ← Stage 1 hard constraint
# Stage 2+ 擴 high-volume major（SOLUSDT, BNBUSDT）；Stage 3+ 才開 ALT
# alt symbols funding rate 異質性大（ALT funding > 30% 可能是 fake spike），需更多樣本驗證
```

**Why BTC/ETH only**：
- BTC/ETH funding rate 流動性 deep；> 30% annualized funding spike 統計上是 squeeze event（high-conviction signal）
- ALT funding > 30% 可能是 thin orderbook artefact；需 Stage 2+ 樣本累積 + per-symbol gate 校準
- 對齊 dispatch packet §2.x BTC/ETH pairs DRAFT 1 candidate（cohort focus 一致）

### §2.2 Cohort intersection with ref21_symbol_universe

per ADR-0021 + 既有 cron `ref21_symbol_universe @20`：
- BTC/ETH 為 universe top-tier；funding_short_v2 cohort = `["BTCUSDT", "ETHUSDT"]`
- 不依賴 ref21 動態 universe（cohort hard-coded in TOML）
- 對齊 funding_harvest Stage 1 BTCUSDT-only pattern（per `srv/rust/openclaw_engine/src/strategies/funding_harvest/mod.rs:74`）

---

## §3 Risk Configuration TOML Spec

### §3.1 strategy_params_demo.toml block

```toml
# srv/settings/strategy_params_demo.toml — Sprint 2 W2-B IMPL append
# funding_short_v2 — Alpha Tournament Candidate #1（per Sprint 2 dispatch packet §2.2）
# Sprint 2 demo-only; live deployment 須 5-gate green + P0-EDGE-1 closure
# 與 funding_arb V2 (ADR-0018 dormant) + funding_harvest (Stage 1 BTCUSDT delta-neutral) 並列
# 為第三個 funding-related strategy slot；short-only directional thesis
[funding_short_v2]
active = false                                # default disabled fail-closed
cooldown_ms = 28_800_000                      # 8h cooldown per symbol（1 funding cycle）
allowed_symbols = ["BTCUSDT", "ETHUSDT"]      # Stage 1 限定 BTC/ETH only
funding_threshold_annualized = 0.30           # 30% annualized hard gate
funding_exit_annualized = 0.05                # exit when funding < 5% annualized（hysteresis）
max_basis_pct = 0.5                           # exit basis > 0.5%
entry_basis_ratio = 0.6                       # entry basis < 0.5% × 0.6 = 0.3%
max_hold_ms = 86_400_000                      # 24h hard time-stop（3 funding cycle）
total_cost_bps = 22.0                         # perp roundtrip + slip（無 spot 腿）
expected_periods = 1.5                        # 1-2 cycle median hold（per QC 量化分析）
```

### §3.2 risk_config_demo.toml per_strategy block

```toml
# srv/settings/risk_control_rules/risk_config_demo.toml — Sprint 2 W2-B IMPL append
# funding_short_v2 Stage 1 per-strategy override block。
# - enabled=false：與 strategy_params_demo.toml [funding_short_v2].active=false 雙保險
# - max_concurrent_positions=2：BTC + ETH 各 1 倉位
# - stop_loss_max_pct_override=3.0：單筆 short 最大 SL 3%（緊於 default 8% per memory project_funding_arb_v2_deprecation_path 1B 3% tight SL 範式）
# - take_profit_max_pct_override=2.0：funding-driven 短倉 TP 不需大；2% 即觸 partial close
# - trailing_activation_pct_override=1.0：1% 浮盈啟動 trailing
# - trailing_distance_pct_override=0.5：trailing 距離 0.5%（緊跟以鎖 funding cycle 部分收益）
[per_strategy.funding_short_v2]
enabled = false
max_concurrent_positions = 2
stop_loss_max_pct_override = 3.0
take_profit_max_pct_override = 2.0
take_profit_enforced_override = true
trailing_activation_pct_override = 1.0
trailing_distance_pct_override = 0.5
```

**Why tight SL 3%**：
- per memory `project_funding_arb_v2_deprecation_path` BUSDT 1B decision：funding strategy demo 限 3% tight SL（避一單吞 30 cycle funding）
- funding_short_v2 single-leg short：3% SL = absolute USD ~$3 per $100 notional（小樣本損失可接受）
- 對齊 funding_harvest Stage 1 stop_loss_max_pct_override = 5.0（funding_harvest 雙腿 → 容錯更寬；funding_short_v2 單腿 → 更緊）

### §3.3 Position sizing（per memory `feedback_position_sizing` 3% risk/trade + Kelly）

per Rust IntentProcessor risk sizing path：
- `default_qty = 1e9` sentinel triggers Kelly/risk sizing in IntentProcessor
- Kelly sizing 用 strategy edge estimate（funding_threshold 30% annualized → per-cycle expected return ~15-25 bps for high-conviction win）
- 3% account risk per trade × SL 3% → notional ≈ account_balance × 1.0（i.e. 100% notional per single position）
- max_concurrent_positions = 2 ⇒ total exposure ≤ 200% notional（每倉位實際 80-150 USD based on Stage 1 typical demo balance）

---

## §4 5-Gate Auto Path Inheritance Contract（per CR-15）

### §4.1 IMPL-time invariants（all 5 gates must hold for live deployment）

| Gate | funding_short_v2 inheritance | IMPL responsibility |
|---|---|---|
| **5-gate-A**: Python `live_reserved` | 不繞；只有 live_reserved=true 才能 live entry | 不需 funding_short_v2 內 IMPL；外層 IntentProcessor 強制 |
| **5-gate-B**: Python Operator role | 不繞；HMAC signed authorization 為入 live 前置 | 不需 funding_short_v2 內 IMPL |
| **5-gate-C**: `OPENCLAW_ALLOW_MAINNET=1` | 不繞 | 不需 funding_short_v2 內 IMPL |
| **5-gate-D**: Valid secret slot | 不繞；Bybit live API key 為 IntentProcessor 前置 | 不需 funding_short_v2 內 IMPL |
| **5-gate-E**: Signed `authorization.json` matching env | 不繞 | 不需 funding_short_v2 內 IMPL |

**funding_short_v2 内部 invariant**：
- `active = false` default in TOML（per §3.1）
- `enabled = false` default in risk_config（per §3.2）
- live entry path 必經 `IntentProcessor.submit_intent` → Guardian → Decision Lease → P1/P2 risk envelope（**no bypass**）
- Stage 1 demo 階段 5-gate-A/B/C/E 仍須 green（per ADR-0004 LiveDemo no-degradation；demo engine_mode 仍走 live-grade auth）

### §4.2 LAL inheritance（per ADR-0034）

- funding_short_v2 不引入新 LAL；經 LAL 1 intra-strategy reparam（cooldown_ms / funding_threshold_annualized 可 Strategist agent IPC tune）
- IPC tune 路徑：`update_strategy_params { strategy: "funding_short_v2", params: {...} }` → validate → ArcSwap 熱更新
- `active = false → true` 是 LAL 2 cross-strategy reweight（per AMD-2026-05-21-01）；Sprint 2 demo 階段 operator 顯式 IPC active=true 才啟（**不**走 auto-activate path）

---

## §5 Look-Ahead Bias Protection（per memory `feedback_indicator_lookahead_bias`）

### §5.1 funding rate 與 basis 不含 look-ahead bias 結構性論證

funding_short_v2 **不**使用 rolling window stats 作 breach signal（不踩 G1-01 Donchian pre-bug pattern）：

| Signal source | look-ahead bias 風險 | mitigation |
|---|---|---|
| `ctx.funding_rate` (8h funding rate) | **無** — Bybit V5 tickers WS 推送的是「下一個 funding window 預估費率」（per `docs/references/2026-04-04--bybit_api_reference.md`）；不是含 current bar 的 rolling stat | ✅ 直接使用 |
| `ctx.index_price` (basis 分母) | **無** — 即時 index price snapshot；非 rolling window | ✅ 直接使用 |
| `compute_edge()` (純函式) | **無** — 不含時序統計；無 look-back | ✅ 直接使用 |
| funding > 30% annualized gate | **無** — 直接比較當前 funding rate 與閾值；非 rolling extreme | ✅ 直接使用 |

**對比 G1-01 Donchian pre-bug**：rolling(N).max() 含 current bar → breach 信號等同「當前 bar 是 N-bar max」mean-reverting selection bias；funding_short_v2 完全不依賴此類 pattern

### §5.2 後續加入 rolling signal 時的強制 SOP（spec invariant）

如 W2-B IMPL 後 Sprint 3+ 對 funding_short_v2 加入 rolling stat（如 funding rate rolling z-score 作 confidence weight）：
- 必並列計算 engine-faithful（含 current bar）+ leak-free（`shift(1)` 排除 current bar）
- **強制 shift(1) 為 production version**（per memory `feedback_indicator_lookahead_bias` checklist）
- Test fixture 必含 leak-free 對比樣本（per CR-6 cross-language fixture harness 1e-4 tolerance）

---

## §6 Rust IMPL Hint — Strategy Struct Skeleton

### §6.1 File location + naming

```
srv/rust/openclaw_engine/src/strategies/funding_short_v2/
  ├── mod.rs           # FundingShortV2 struct + Strategy trait impl
  ├── params.rs        # FundingShortV2Params (TOML schema) + FundingShortV2UpdateParams (IPC)
  └── tests.rs         # unit tests + 1e-4 cross-language fixture
```

**Why dedicated subdirectory (not single .rs)**：對齊 funding_harvest pattern (`srv/rust/openclaw_engine/src/strategies/funding_harvest/`)；strategy 有獨立 params + synthetic state 時用 dir，single-file struct 用 .rs

### §6.2 Struct skeleton（W2-B IMPL 直接引用）

```rust
// srv/rust/openclaw_engine/src/strategies/funding_short_v2/mod.rs
//! funding_short_v2 — short-only directional funding capture (Sprint 2 Alpha Tournament Candidate #1).
//!
//! MODULE_NOTE：
//!   入場：funding_rate_8h_annualized > 30% AND funding > 0 AND basis < 0.3% AND edge > 0
//!   出場：funding 反轉 / edge ≤ 0 / basis > 0.5% / 24h max hold / 3% SL
//!   方向：**short-only hard enforcement**（const IS_LONG: bool = false）
//!   與 funding_arb V2 (ADR-0018 dormant) 區別：
//!     - V2: bi-directional + 5bps gate + 72h hold + delta-neutral 假設（QC verdict 數學不成立）
//!     - V2: 13 fills 0 win evidence
//!     - funding_short_v2: short-only + 30% annualized gate + 24h hold + 純 directional
//!   Stage 1 Demo BTC/ETH only；Stage 2+ 擴展依據 demo evidence + operator approval。

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

pub mod params;

#[cfg(test)]
mod tests;

pub use params::FundingShortV2Params;

// Hard-coded short-only invariant（compile-time）
const IS_LONG: bool = false;

const FUNDING_SHORT_V2_MAKER_OFFSET_BPS: f64 = 1.0;
const FUNDING_SHORT_V2_MAKER_BUFFER_TICKS: u32 = 1;
const FUNDING_SHORT_V2_MAKER_TIMEOUT_MS: u64 = 45_000;

// funding_rate_8h → annualized 折算（per Bybit V5 8h × 365/8 cycle/year ≈ 1095 cycles/year）
const CYCLES_PER_YEAR: f64 = 1095.0;

pub struct FundingShortV2 {
    active: bool,
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,
    pub allowed_symbols: Vec<String>,
    pub funding_threshold_annualized: f64,  // 0.30 = 30%
    pub funding_exit_annualized: f64,       // 0.05 = 5%
    pub max_basis_pct: f64,
    pub entry_basis_ratio: f64,
    pub max_hold_ms: u64,
    pub total_cost_bps: f64,
    pub expected_periods: f64,
    default_qty: f64,
    prev_last_trade_ms: HashMap<String, u64>,
}

impl FundingShortV2 {
    pub fn new() -> Self {
        Self {
            active: false,
            cooldown: TrendCooldown::new(28_800_000), // 8h
            cooldown_ms: 28_800_000,
            allowed_symbols: vec!["BTCUSDT".into(), "ETHUSDT".into()],
            funding_threshold_annualized: 0.30,
            funding_exit_annualized: 0.05,
            max_basis_pct: 0.5,
            entry_basis_ratio: 0.6,
            max_hold_ms: 86_400_000,  // 24h
            total_cost_bps: 22.0,
            expected_periods: 1.5,
            default_qty: 1e9,  // sentinel → IntentProcessor Kelly sizing
            prev_last_trade_ms: HashMap::new(),
        }
    }

    /// 8h funding rate → annualized 折算
    /// 純函式；負 funding 折算為負 annualized（caller 用於 reject path）
    pub(crate) fn annualized_funding(funding_rate_8h: f64) -> f64 {
        funding_rate_8h * CYCLES_PER_YEAR
    }

    /// Per-cycle edge after amortized cost
    fn compute_edge(&self, funding_rate_8h: f64) -> f64 {
        let amortized_cost = self.total_cost_bps / 10_000.0 / self.expected_periods;
        funding_rate_8h.abs() - amortized_cost
    }

    /// Basis percentage (perp vs index)
    fn compute_basis_pct(perp_price: f64, index_price: Option<f64>) -> f64 {
        match index_price {
            Some(ip) if ip > 0.0 => ((perp_price / ip) - 1.0).abs() * 100.0,
            _ => 0.0,
        }
    }

    /// Exit decision（出場判斷；4 條件 OR）
    fn should_exit(
        &self,
        funding_rate_8h: f64,
        basis_pct: f64,
        now_ms: u64,
        entry_ms: u64,
    ) -> bool {
        let annualized = Self::annualized_funding(funding_rate_8h);
        // 1. funding 反轉 / collapse
        if annualized < self.funding_exit_annualized || funding_rate_8h < 0.0 {
            return true;
        }
        // 2. edge degradation
        if self.compute_edge(funding_rate_8h) <= 0.0 {
            return true;
        }
        // 3. basis blowout
        if basis_pct > self.max_basis_pct {
            return true;
        }
        // 4. time-stop
        if now_ms.saturating_sub(entry_ms) > self.max_hold_ms {
            return true;
        }
        false
    }

    fn snapshot_prev_cooldown(&mut self, sym: &str) {
        self.prev_last_trade_ms
            .insert(sym.to_string(), self.cooldown.last_ms(sym).unwrap_or(0));
    }

    // update_params / get_params / IPC schema 同 funding_arb pattern；W2-B IMPL 對齊
}

impl Strategy for FundingShortV2 {
    fn name(&self) -> &str {
        "funding_short_v2"
    }

    fn is_active(&self) -> bool {
        self.active
    }

    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// 與 funding_arb 同一組 alpha source tag（FundingSkew + Basis）
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::FundingSkew, AlphaSourceTag::Basis];
        TAGS
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        let sym = ctx.symbol;
        let now_ms = ctx.timestamp_ms;

        // Stage 1 cohort gate
        if !self.allowed_symbols.iter().any(|s| s == sym) {
            return vec![];
        }

        // funding_rate must be Some + positive
        let funding_rate_8h = match ctx.funding_rate {
            Some(fr) if fr > 0.0 => fr,
            _ => return vec![],
        };

        let basis_pct = Self::compute_basis_pct(ctx.price, ctx.index_price);

        // Position SSoT 判定（Option A-Lite 範式，per funding_arb）
        let owned_position = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name());

        match owned_position {
            Some(pos) => {
                // Exit 分支
                if self.should_exit(funding_rate_8h, basis_pct, now_ms, pos.entry_ts_ms) {
                    self.snapshot_prev_cooldown(sym);
                    self.cooldown.record_signal(sym, now_ms);
                    return vec![StrategyAction::Close {
                        symbol: sym.to_string(),
                        confidence: 0.8,
                        reason: format!(
                            "funding_short_v2_exit: annualized={:.4} basis={:.3}%",
                            Self::annualized_funding(funding_rate_8h),
                            basis_pct
                        ),
                    }];
                }
                return vec![];
            }
            None if ctx.position_state.is_some() => {
                // Cross-strategy 占用，skip
                return vec![];
            }
            None => {}
        }

        // Entry gate (5 conditions)
        if !ctx.h0_allowed {
            return vec![];
        }
        if !self.cooldown.is_cooled_down(sym, now_ms) {
            return vec![];
        }

        // Gate 1: funding > 30% annualized HARD GATE
        let annualized = Self::annualized_funding(funding_rate_8h);
        if annualized < self.funding_threshold_annualized {
            return vec![];
        }

        // Gate 4: edge > 0
        let edge = self.compute_edge(funding_rate_8h);
        if edge <= 0.0 {
            return vec![];
        }

        // Gate 3: basis tight
        if basis_pct > self.max_basis_pct * self.entry_basis_ratio {
            return vec![];
        }

        // confidence scales with annualized magnitude（30% → 0.4, 60%+ → 0.9）
        let confidence = crate::tick_pipeline::on_tick_helpers::clamp_confidence(
            ((annualized - self.funding_threshold_annualized) / 0.30 + 0.4).clamp(0.4, 0.9),
        );

        let maker_inputs = MakerPriceInputs {
            last_price: ctx.price,
            best_bid: ctx.best_bid,
            best_ask: ctx.best_ask,
            tick_size: ctx.tick_size,
        };

        // SHORT-ONLY: is_long = false (compile-time const)
        let limit_price = match compute_post_only_price(
            IS_LONG,  // ← const false
            maker_inputs,
            FUNDING_SHORT_V2_MAKER_OFFSET_BPS,
            FUNDING_SHORT_V2_MAKER_BUFFER_TICKS,
            self.name(),
            sym,
        ) {
            Some(price) => price,
            None => return vec![],
        };

        self.snapshot_prev_cooldown(sym);
        self.cooldown.record_signal(sym, now_ms);

        vec![StrategyAction::Open(OrderIntent::new_trade(
            sym.to_string(),
            IS_LONG,  // ← const false
            self.default_qty,
            confidence,
            self.name().into(),
            "limit".into(),
            Some(limit_price),
            None,
            None,
            Some(TimeInForce::PostOnly),
            Some(FUNDING_SHORT_V2_MAKER_TIMEOUT_MS),
        ))]
    }

    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    // 其他 trait method 用 default no-op（同 funding_arb Option A-Lite pattern）
}
```

### §6.3 StrategyFactory registration（registry.rs append）

```rust
// srv/rust/openclaw_engine/src/strategies/registry.rs — append after funding_harvest block
// funding_short_v2 — Sprint 2 Alpha Tournament Candidate #1
let mut fsv2 = funding_short_v2::FundingShortV2::new();
fsv2.cooldown_ms = p.funding_short_v2.cooldown_ms;
fsv2.cooldown.set_duration(p.funding_short_v2.cooldown_ms);
fsv2.allowed_symbols = p.funding_short_v2.allowed_symbols.clone();
fsv2.funding_threshold_annualized = p.funding_short_v2.funding_threshold_annualized;
fsv2.funding_exit_annualized = p.funding_short_v2.funding_exit_annualized;
fsv2.max_basis_pct = p.funding_short_v2.max_basis_pct;
fsv2.entry_basis_ratio = p.funding_short_v2.entry_basis_ratio;
fsv2.max_hold_ms = p.funding_short_v2.max_hold_ms;
fsv2.total_cost_bps = p.funding_short_v2.total_cost_bps;
fsv2.expected_periods = p.funding_short_v2.expected_periods;
fsv2.set_active(p.funding_short_v2.active);
strategies.push(Box::new(fsv2));
```

Also append `pub mod funding_short_v2;` to `srv/rust/openclaw_engine/src/strategies/mod.rs` use list + `funding_short_v2` to `use super::{...}` in `registry.rs`.

### §6.4 strategies/params.rs append（FundingShortV2Params TOML schema）

```rust
// srv/rust/openclaw_engine/src/strategies/params.rs — append
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FundingShortV2Params {
    pub active: bool,
    pub cooldown_ms: u64,
    pub allowed_symbols: Vec<String>,
    pub funding_threshold_annualized: f64,
    pub funding_exit_annualized: f64,
    pub max_basis_pct: f64,
    pub entry_basis_ratio: f64,
    pub max_hold_ms: u64,
    pub total_cost_bps: f64,
    pub expected_periods: f64,
}

impl Default for FundingShortV2Params {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: 28_800_000,
            allowed_symbols: vec!["BTCUSDT".into(), "ETHUSDT".into()],
            funding_threshold_annualized: 0.30,
            funding_exit_annualized: 0.05,
            max_basis_pct: 0.5,
            entry_basis_ratio: 0.6,
            max_hold_ms: 86_400_000,
            total_cost_bps: 22.0,
            expected_periods: 1.5,
        }
    }
}

// Append funding_short_v2 field to StrategyParamsConfig struct + serde default
```

---

## §7 14d Demo Data Accumulation Hook（per CR-6 + AC-S2-A-2）

### §7.1 Attribution chain（per ADR-0025 track-based strategy attribution）

funding_short_v2 fills 經 `trading.fills` 寫入：
- `strategy_name = "funding_short_v2"`
- `track = 'direct_exploit'`（per V101 strategy_track ENUM + ADR-0026：hand-coded Rust strategy 必 = `direct_exploit`，Track A bypass CPCV；非新 track 命名空間）
- `engine_mode IN ('demo', 'live_demo', 'live')`（per ADR-0005 engine_mode tag）

attribution_chain_ok rate 預期 100%（per Sprint N+0 closure 2026-05-10 attribution_chain_ok fix 經驗）

**Empirical V101 ENUM verified**（2026-05-25 SSH read-only probe）：
```
SELECT enum_range(NULL::strategy_track);
=> {direct_exploit, asds_factory, baseline}
```
非 `alpha_short_carry`（不存在 ENUM 命名空間）。

### §7.2 14d demo SQL bucket-split monitor

```sql
-- Sprint 2 W2-F QA 14d daily evidence accumulation
-- per AC-S2-A-2 minimum bar n_fills ≥ 30
WITH funding_short_v2_demo AS (
  SELECT
    DATE(filled_at AT TIME ZONE 'UTC') AS trade_date,
    symbol,
    COUNT(*) AS n_fills,
    AVG(net_pnl_bps) AS avg_net_bps,
    -- Wilson CI lower bound（z=1.96 for 95% CI）
    (AVG(net_pnl_bps) - 1.96 * STDDEV(net_pnl_bps) / SQRT(COUNT(*))) AS wilson_lower_bps
  FROM trading.fills
  WHERE strategy_name = 'funding_short_v2'
    AND engine_mode IN ('demo', 'live_demo')
    AND filled_at > NOW() - INTERVAL '14 days'
  GROUP BY trade_date, symbol
)
SELECT
  trade_date,
  SUM(n_fills) AS total_fills,
  AVG(avg_net_bps) AS avg_net_bps_overall,
  MIN(wilson_lower_bps) AS wilson_lower_overall_bps
FROM funding_short_v2_demo
GROUP BY trade_date
ORDER BY trade_date DESC;
```

### §7.3 DRAFT writeback to V103 EXTEND hypotheses（per AC-S2-A-4）

**Schema 真相**（per V100 base + V103 EXTEND actual spec `srv/docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md`）：
- 目標 table = `learning.hypotheses`（**非** `learning.m4_hypotheses_extended` — 該 table 不存在）
- V103 EXTEND 6 column 為 ALTER ADD 到 `learning.hypotheses`：
  1. `hypothesis_source_module` (TEXT, 3 enum: `M4_AUTO`/`OPERATOR`/`HISTORIC`)
  2. `leakage_scan_pass` (BOOLEAN, DEFAULT FALSE)
  3. `bonferroni_corrected_p` (NUMERIC(10,8), [0,1])
  4. `replicability_score` (NUMERIC(5,4), [0,1])
  5. `decision_lease_draft_id` (UUID)
  6. `cowork_review_status` (TEXT, 4 enum: `NONE`/`PENDING`/`APPROVED`/`REJECTED`)

per CR-6 minimum bar 6 attribute 對映 V103 EXTEND column：
- N ≥ 30 → `learning.hypotheses.min_sample_size` (V100 base column)
- Bonferroni p < 0.05/K（K = 2 個新 candidate → α = 0.025）→ V103 `bonferroni_corrected_p`
- effect size ≥ 0.2（Cohen's d for net_pnl_bps mean）→ V103 `replicability_score` (composite)
- 6mo sub-period stability（Sprint 2 結束時不可達）→ V103 `replicability_score` (composite)
- leakage scan pass → V103 `leakage_scan_pass`
- cluster K silhouette 5-fold CV（funding_short_v2 不分 cluster → `single-cluster` pass）→ V103 `replicability_score` (composite)

W2-F MIT post-IMPL audit 寫 V103 EXTEND DRAFT row（**正確 schema**）：
```sql
INSERT INTO learning.hypotheses (
  -- V100 base 6 column required
  strategy_name,
  state,                       -- per V100 11-value ENUM；DRAFT 階段 = 'draft'
  hypothesis_text,
  null_hypothesis,
  acceptance_criteria,
  min_sample_size,             -- N (per CR-6 minimum bar #1)
  max_drawdown_pct,
  -- V103 EXTEND 6 column
  hypothesis_source_module,    -- 'M4_AUTO' for Sprint 2 alpha candidate
  leakage_scan_pass,           -- per CR-6 #5
  bonferroni_corrected_p,      -- per CR-6 #2; K=2 → α=0.025
  replicability_score,         -- composite (#3 effect + #4 subperiod + #6 cluster)
  decision_lease_draft_id,     -- per LAL 3 STRATEGY_TRIAL lease UUID
  cowork_review_status         -- DEFAULT 'NONE' Sprint 2 不啟 Cowork
) VALUES (
  'funding_short_v2',
  'draft',                     -- Sprint 2 draft；Sprint 3+ operator click 升 'preregistered'
  'Funding rate > 30% annualized + short-only directional capture (Sprint 2 Alpha Tournament Candidate #1)',
  'Mean net_pnl_bps in demo over 14d <= 0',
  '14d demo avg_net_pnl_bps > 5 + Wilson CI lower > 0 + n_fills ≥ 30',
  /* n_fills */ ?::int,
  3.0,                         -- per_strategy SL 3% 對齊 strategy_params
  'M4_AUTO',
  /* leakage_scan_pass */ TRUE,
  /* bonferroni p */ ?::numeric(10,8),
  /* replicability composite */ ?::numeric(5,4),
  /* lease_draft_id */ ?::uuid,
  'NONE'
);
```

**W2-B E1 IMPL 必 honor**：
- 不可寫 `learning.m4_hypotheses_extended`（該 table 不存在）
- 不可寫 W1-A 原 spec 虛構 column（`attribute_n` / `attribute_p_value` / `attribute_effect_size` / `attribute_subperiod_stable` / `attribute_graveyard_flag` / `attribute_cluster_silhouette`）
- 必走 V100 base + V103 EXTEND actual 6 column
- W2-E E2 review grep `m4_hypotheses_extended` / `attribute_n` / `attribute_p_value` 必 0 hit

---

## §8 Acceptance Criteria

| AC | 內容 | Verification path |
|---|---|---|
| **AC-S2-A-C1-1** | funding_short_v2 strategy struct land in Rust + StrategyFactory registered + TOML schema active | W2-B E1 IMPL DONE + cargo test |
| **AC-S2-A-C1-2** | `IS_LONG` 為 `const false`（compile-time short-only invariant）| `grep -n 'const IS_LONG' src/strategies/funding_short_v2/mod.rs` 必出現且 = false |
| **AC-S2-A-C1-3** | funding_threshold_annualized = 0.30 default（hard 30% gate）| TOML + struct default 對齊 |
| **AC-S2-A-C1-4** | allowed_symbols Stage 1 = ["BTCUSDT", "ETHUSDT"]；non-cohort silent skip | unit test: ALTUSDT funding > 30% 不入場 |
| **AC-S2-A-C1-5** | should_exit 4 條件 OR 邏輯（funding < exit / edge ≤ 0 / basis > max / time-stop）| unit test 各條件獨立觸發 close |
| **AC-S2-A-C1-6** | 14d demo accumulation hook works（fills 寫入 + bucket-split SQL fire）| W2-F QA 14d empirical |
| **AC-S2-A-C1-7** | n_fills ≥ 30 per cohort over 14d（per CR-6 minimum bar）| Sprint 2 末 W3-A review |
| **AC-S2-A-C1-8** | 14d avg_net > 5bps + Wilson CI lower > 0（Sprint 3+ verdict path）| Sprint 3+ Stage 0R verdict |
| **AC-S2-A-C1-9** | DRAFT writeback to V103 hypotheses（per AC-S2-A-4）| W2-F MIT audit |
| **AC-S2-A-C1-10** | 5-gate 0 觸碰（per §4.1 + grep diff）| E2 review grep `live_reserved\|max_retries\|live_execution_allowed` |

---

## §9 對抗式 Review Focus（W2-E E2 + W2-F MIT post-IMPL audit 重點）

1. **Side enforcement hard invariant grep** — `grep -n 'IS_LONG' src/strategies/funding_short_v2/` 必出現 const + true 永不出現
2. **funding > 30% annualized gate 不被 silent override** — IPC `update_params` validate 強制 `funding_threshold_annualized >= 0.20`（floor at 20% 防 operator/agent IPC 誤設低於 break-even）
3. **5-gate inheritance integrity** — diff grep `execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|live_reserved`；0 hit 是預期
4. **ADR-0018 不繞** — funding_arb V2 dormant block 不動；funding_short_v2 是並列 new slot（W2-E grep `funding_arb` block 不變）
5. **黑名單 method 0 hit** — `grep -nri 'hmm|markov_switching|garch' src/strategies/funding_short_v2/` 必 0 hit（per ADR-0036 Decision 1）
6. **Look-ahead bias scan** — funding_short_v2 不引入 rolling window stat；若 W2-B IMPL 加 rolling z-score → 強制並列 leak-free shift(1) 對比（per memory `feedback_indicator_lookahead_bias`）
7. **Cross-language fixture harness 1e-4 tolerance**（per H-18）— funding_short_v2 Python 對應測試 fixture（Strategist agent IPC simulation）必 1e-4 對齊 Rust output

---

## §10 References

- dispatch packet: `srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` §2.2 candidate #1
- memory: `project_funding_arb_v2_deprecation_path` (2A 中期棄策略路徑) / `project_g2_funding_arb_monitor` (G-2 v2 NEGATIVE) / `feedback_position_sizing` (3% risk/trade) / `feedback_indicator_lookahead_bias` (rolling shift(1) 強制) / `feedback_demo_loose_live_strict_policy` (demo 學習料源 / live fail-closed)
- ADR-0018 funding_arb V2 dormant decision
- ADR-0036 §Decision 1 HMM/Markov-switching/GARCH 黑名單
- ADR-0038 M11 self-hosted PG historical source（與本 strategy 無直接互動，但 Sprint 3 M11 replay 對 funding_short_v2 fills 適用）
- ADR-0034 Decision Lease LAL（funding_short_v2 IPC tune 走 LAL 1；active=false→true 走 LAL 2）
- ADR-0024-lite Cowork operator-assistant（funding_short_v2 active=true 必 operator 顯式 IPC 觸發，**不**走 Cowork auto-trigger）
- ADR-0005 engine_mode tag (`live_demo` for demo with live grade auth)
- v5.8 §11.5 5-Gate Auto Path Inheritance Hard Invariant
- CR-15 5-gate auto path inheritance contract
- CR-6 M4 hypothesis miner minimum bar 6 attribute
- existing strategy IMPL reference: `srv/rust/openclaw_engine/src/strategies/funding_harvest/mod.rs` (Stage 1 BTCUSDT pattern + annualized funding 計算範式)
- existing strategy IMPL reference: `srv/rust/openclaw_engine/src/strategies/funding_arb.rs` (Option A-Lite Strategy trait pattern + position_state 三分支)
- skills: `quant-strategy-design`, `math-model-audit`, `crypto-microstructure-knowledge`

---

## §11 Conclusion

**funding_short_v2 IMPL-ready verdict**: **READY for W2-B E1 IMPL**

- 4 conditions all met: algorithm spec ✅ / TOML spec ✅ / Rust struct skeleton ✅ / AC + adversarial review focus ✅
- 不踩 ADR-0018 dormant 教訓（短 short-only + 30% gate + 24h hold ≠ V2 directional + 5bps + 72h）
- 不繞 5-gate / Decision Lease（per §4.1 + 1-3 IS_LONG const + per_strategy override 雙保險）
- 不引入 look-ahead bias（funding_rate / index_price 為即時 snapshot，非 rolling window stat）
- 不踩 ADR-0036 黑名單（無 HMM / GARCH 依賴）

**派發 readiness**：W2-B E1 sub-agent 可直接 IMPL；W2-E E2 review 對抗式檢查 6 點 + W2-F MIT post-IMPL audit 14d empirical evidence。

---

**Report END**

PA SPEC DONE: spec path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md`

---

## Changelog
- 2026-05-25 v1.1: inline amend by PA per W2-A 2 CRITICAL catch + PM Option A decision
  - §7.1 strategy_track `'alpha_short_carry'` → `'direct_exploit'` (per V101 ENUM empirical verified `{direct_exploit, asds_factory, baseline}` + ADR-0026 hand-coded Rust = direct_exploit)
  - §7.3 INSERT target table `learning.m4_hypotheses_extended` → `learning.hypotheses` (V100 base + V103 EXTEND actual schema per `2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md`)
  - §7.3 INSERT 6 column 名稱 (`attribute_n` / `attribute_p_value` / `attribute_effect_size` / `attribute_subperiod_stable` / `attribute_graveyard_flag` / `attribute_cluster_silhouette`) → V103 EXTEND 6 real column (`hypothesis_source_module` / `leakage_scan_pass` / `bonferroni_corrected_p` / `replicability_score` / `decision_lease_draft_id` / `cowork_review_status`)
  - 加 W2-E E2 review grep guard: `m4_hypotheses_extended` / `attribute_n` / `attribute_p_value` / `alpha_short_carry` 必 0 hit
  - W2-A finalize report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2a_alpha_tournament_pre_spec_finalize.md`
  - W2-B E1 IMPL dispatch verdict: NEEDS-MORE-DESIGN → DISPATCH-READY
