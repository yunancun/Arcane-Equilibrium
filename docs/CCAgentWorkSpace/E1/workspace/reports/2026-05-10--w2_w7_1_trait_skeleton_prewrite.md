# Sprint N+1 D+0 Trait Skeleton Prewrite — W2 BtcLeadLagPanel + W7-1 TickContext.position_state

- **Spec source**:
  - PA #1：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md` §7
  - PA #3：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p1_ma_crossover_duplicate_intent_audit.md` §6 Option A
- **Owner chain**：PA spec → **E1 IMPL（本報告）** → 待 PM 21:30 sign-off → commit
- **Date**：2026-05-10
- **Status**：**NOT COMMITTED, NOT DEPLOYED** — 留 PM 統一 commit + push

---

## 1. 任務摘要

Sprint N+1 D+0 預寫 trait skeleton，二合一範圍：

**Tier 1 必達（W2 BtcLeadLagPanel）**：
- 新增 `BtcLeadLagPanel` struct typedef 到 `srv/rust/openclaw_core/src/alpha_surface.rs`
- `AlphaSurface<'a>` 加 `pub btc_lead_lag: Option<&'a BtcLeadLagPanel>,` 一行
- `tier1_only()` / `empty()` / `EMPTY_ALPHA_SURFACE` 三 constructor 加 `btc_lead_lag: None,`
- 新增 1 test：`btc_lead_lag_default_none()`
- MODULE_NOTE 末尾加 W2 paper-only fence 設計段
- `slots.rs` 加 W1 funding_curve / W1 oi_delta_panel / W2 btc_lead_lag 三個 anchor comment
- `step_4_5_dispatch.rs` 加 W1/W2 surface field assignment anchor comment

**Tier 2 try-best（W7-1 TickContext.position_state）— 完成**：
- `TickContext<'a>` 加 `position_state: Option<&'a PaperPosition>` 欄位
- `step_4_5_dispatch.rs` 為每個 strategy iteration 取 read-only handle，使用 `ctx.clone()` 覆寫 per-iteration
- `replay/runner.rs` `build_tick_context` 加 `position_state: None,`（replay 模式無 paper_state context）
- 28 個 test callsite bulk-patch（11 檔）

**目的**：W1 + W2 五個 E1 sub-agent N+1 IMPL 之前完全並行 0 file 重疊（trait shape 預先 commit；新 struct 預先 typedef；slot/dispatch insertion anchor 預留）。

---

## 2. 修改清單（16 files / +182 / -2）

### Tier 1 — alpha_surface.rs + slots.rs + dispatch anchor（4 files）

| 路徑 | 動作 | LOC |
|---|---|---|
| `rust/openclaw_core/src/alpha_surface.rs` | 新增 BtcLeadLagPanel struct + AlphaSurface field + 3 constructor + 1 test + MODULE_NOTE 末段 | +98 / -0 |
| `rust/openclaw_engine/src/ipc_server/slots.rs` | 加 3 個 panel slot anchor comment（W1 funding_curve / W1 oi_delta_panel / W2 btc_lead_lag） | +18 / -0 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 加 W1/W2 surface field assignment anchor comment + position_state per-iteration wire（屬 Tier 2） | +27 / -1 |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | TickContext 加 position_state 欄位（屬 Tier 2） | +10 / -1 |

### Tier 2 — TickContext.position_state callsite patch（12 files）

| 路徑 | 動作 | LOC |
|---|---|---|
| `rust/openclaw_engine/src/replay/runner.rs` | build_tick_context 加 `position_state: None,` | +3 / -0 |
| `rust/openclaw_engine/src/replay/strategy_adapter.rs` | StubStrategy ctx helper +1 | +1 / -0 |
| `rust/openclaw_engine/src/orchestrator.rs` | mock ctx helper +1 | +1 / -0 |
| `rust/openclaw_engine/src/strategies/funding_arb.rs` | 3 ctx 構造處 +3 | +3 / -0 |
| `rust/openclaw_engine/src/strategies/bb_breakout/tests.rs` | 4 helpers | +4 / -0 |
| `rust/openclaw_engine/src/strategies/bb_breakout/tests_oi.rs` | 2 helpers | +2 / -0 |
| `rust/openclaw_engine/src/strategies/bb_breakout/tests_p1_11.rs` | 1 helper | +1 / -0 |
| `rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` | 5 helpers | +5 / -0 |
| `rust/openclaw_engine/src/strategies/grid_trading/tests.rs` | 2 helpers | +2 / -0 |
| `rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` | 5 helpers | +5 / -0 |
| `rust/openclaw_engine/src/strategies/ma_crossover/tests_a1_a2_maker.rs` | 3 helpers | +3 / -0 |
| `rust/openclaw_engine/tests/stress_integration.rs` | make_ctx | +1 / -0 |

**Total**：16 files / +182 / -2

---

## 3. 關鍵 diff

### 3.1 BtcLeadLagPanel struct typedef（PA #1 §2 對齊）

```rust
// rust/openclaw_core/src/alpha_surface.rs
/// BtcLeadLagPanel — Sprint N+1 W2 BTC→Alt 跨資產 lead-lag panel（候選 C
/// W-AUDIT-8c 落地版 stub）。
///
/// 來源（Sprint N+1 W2 IMPL）：BTCUSDT 1m kline → lead signal（return / volume /
/// orderbook imbalance over N=60-300s window）→ Python writer 寫
/// `panel.btc_lead_lag_panel`（V088 migration；retention 14d）。
///
/// **執行邊界（Sprint N+1 W2 paper-only）**：本 wave Strategy 只在 paper engine
/// mode 接此 panel；demo / live_demo / live → `AlphaSurface.btc_lead_lag = None`
/// （fence 由 `tick_pipeline/on_tick/step_4_5_dispatch.rs` engine_mode gate
/// 主防線實施，trait 端不知此 fence；策略消費端 `surface.btc_lead_lag.is_none()`
/// → skip 即可，不需查 engine_mode）。BUSDT cohort 排除（per ADR-0018）。
///
/// **Lead-lag 信號契約**：`btc_lead_return_pct` 必為 strict `shift(N)` 不含
/// current bar（避免 look-ahead bias，per `feedback_indicator_lookahead_bias`）。
/// `lead_window_secs` 三檔之一（60 / 120 / 300）；`alt_xcorr` 為 rolling 1h
/// cross-correlation；`alt_expected_dir` 三值（−1 / 0 / +1）。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct BtcLeadLagPanel {
    /// Cohort alt symbols（不含 BTCUSDT；BUSDT 排除 per ADR-0018）。
    pub alt_symbols: Vec<String>,
    /// BTC lead signal：N 秒 return（strict shift(N) 禁含 current bar）。
    pub btc_lead_return_pct: f64,
    /// BTC lead window seconds（60 / 120 / 300 三檔之一）。
    pub lead_window_secs: u32,
    /// 各 alt symbol 對 BTC lead signal 的 cross-correlation（rolling 1h）。
    pub alt_xcorr: Vec<f64>,
    /// 各 alt symbol 預期 mean reversion / momentum direction（−1 / 0 / +1）。
    pub alt_expected_dir: Vec<i8>,
    pub snapshot_ts_ms: i64,
    pub source_tier: String,
}
```

### 3.2 AlphaSurface 加 btc_lead_lag field

```rust
pub struct AlphaSurface<'a> {
    // ... 既有 9 field 不動 ...

    // ── Sprint N+1 W2 — 跨資產 lead-lag panel（paper-only） ──
    /// BTC→Alt lead-lag panel 引用（**paper-only**；fence 由 step_4_5_dispatch
    /// engine_mode gate 實施，demo / live_demo / live 永遠 None）。
    pub btc_lead_lag: Option<&'a BtcLeadLagPanel>,
}
```

### 3.3 TickContext 加 position_state field（PA #3 Option A）

```rust
// rust/openclaw_engine/src/tick_pipeline/mod.rs
pub struct TickContext<'a> {
    // ... 既有 14 field 不動 ...

    /// Sprint N+1 W7-1：read-only handle 到 paper_state.get_position(symbol)。
    /// PA #3 P1-MA-CROSSOVER §6 Option A — 解 cross-strategy position state 盲區。
    /// `None` = symbol 當前無倉位。strategy on_tick 進 entry path 前查此 handle，
    /// 已有同 symbol 倉位 → fail-closed skip entry，避免無限 reject hot loop。
    /// 借用 scope 與 ctx 同生命週期；ctx 必每 strategy iteration 內構造，避免與
    /// 同 step 後續 `paper_state.proactive_mirror_insert` / `apply_fill` 等
    /// mutable borrow 衝突（NLL per-iteration 釋放）。
    pub position_state: Option<&'a PaperPosition>,
}
```

### 3.4 Per-iteration ctx clone pattern（borrow checker 解法）

```rust
// rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs
let ctx = TickContext {
    // ... 既有 fields ...
    alpha_surface_ref: &alpha_surface,
    // Sprint N+1 W7-1：base ctx position_state default None；真實值由 for-loop
    // 內 per-strategy iteration 從 self.paper_state.get_position(sym) 取
    // 並 Clone ctx 覆寫，避免與後續 paper_state mutable borrow 衝突。
    position_state: None,
};

// for-loop 內：
for strategy in strategies_iter {
    if !strategy.is_active() { continue; }
    crate::orchestrator::Orchestrator::tally_alpha_sources(...);
    // Sprint N+1 W7-1：per-strategy iteration 取 read-only position handle，
    // borrow scope 在本次 strategy.on_tick 結束即釋放，不與後續
    // paper_state.proactive_mirror_insert / apply_fill 等 mutable borrow 衝突。
    // PA #3 Option A — 解 cross-strategy position state 盲區。
    let position_state = self.paper_state.get_position(sym);
    let mut iter_ctx = ctx.clone();
    iter_ctx.position_state = position_state;
    let strategy_actions = strategy.on_tick(&iter_ctx, &alpha_surface);
    // ... 後續 mutation ...
}
```

### 3.5 slots.rs 三 panel insertion anchor

```rust
// =============================================================================
// Sprint N+1 W1 + W2 panel slot insertion anchors
// PA D+0 預留 anchor，避免 W1/W2 五個 E1 sub-agent 並行 IMPL 時撞 line collision
// =============================================================================

// === W1 FundingCurvePanelSlot insertion point ===
// W1 E1-α (B-1) 在此下方加 `pub type FundingCurvePanelSlot = Arc<RwLock<Option<...>>>;`

// === W1 OIDeltaPanelSlot insertion point ===
// W1 E1-β (B-2) 在此下方加 `pub type OIDeltaPanelSlot = Arc<RwLock<Option<...>>>;`

// === W2 BtcLeadLagPanelSlot insertion point ===
// W2 E1-δ (C-IMPL-2) 在此下方加 `pub type BtcLeadLagPanelSlot = Arc<RwLock<Option<...>>>;`
```

---

## 4. 治理對照

### 4.1 PA #1 §7 spec 對照

| spec §7 要求 | 結果 |
|---|---|
| 新增 BtcLeadLagPanel struct typedef (~25 LOC) | ✓ ~30 LOC（含完整 doc） |
| AlphaSurface<'a> 加 `pub btc_lead_lag: Option<&'a BtcLeadLagPanel>,` | ✓ |
| tier1_only() 加 `btc_lead_lag: None,` | ✓ |
| empty() 加 `btc_lead_lag: None,` | ✓ |
| EMPTY_ALPHA_SURFACE static 加 `btc_lead_lag: None,` | ✓ |
| Default impl 自動繼承 | ✓（既有 impl Default for AlphaSurface<'static> 委派 empty()） |
| 新增 1 test：btc_lead_lag_default_none() | ✓（含 panel borrow lifetime acceptance check） |
| MODULE_NOTE 末段加 W2 paper-only fence 段 | ✓ |
| slots.rs 加 3 anchor comment | ✓ |
| step_4_5_dispatch.rs 加 W1/W2 anchor comment | ✓ |

### 4.2 PA #3 §6 Option A 對照（Tier 2 成功）

| Option A 要求 | 結果 |
|---|---|
| TickContext 加 `position_state: Option<&PaperPosition>` 或類似 read-only handle | ✓ |
| 改 TickContext signature 影響 5 個策略 | 5 策略 on_tick 簽名不變，**只動 ctx field**，5 策略未被破 |
| step_4_5_dispatch.rs 對齊新欄位 | ✓ per-iteration clone pattern 解 borrow conflict |
| ~50 (ma_crossover) + ~30 (TickContext + tick_pipeline call site) | ma_crossover 0 LOC（W7-1 trait skeleton 不動 strategy on_tick body）+ ~10 (TickContext) + ~28 (callsite patch) = ~38 LOC（小於 spec 估計） |

### 4.3 PA #3 §8 重點 3 警告（borrow checker risk）— 結果

> **paper_state.get_position()** 在 strategy on_tick 是否會違反 borrow checker（paper_state 已被 step_4_5_dispatch 同層 borrow）

**結果**：未撞牆。設計上因 `ctx.clone()` per-iteration pattern：
- `ctx` 主結構建構時 `position_state: None`，無 paper_state immutable borrow
- 進 for-loop 才 `let position_state = self.paper_state.get_position(sym);`，借用 scope = `iter_ctx` 整個 strategy.on_tick 呼叫
- iteration 結束 borrow 自然釋放，下游 `self.paper_state.proactive_mirror_insert / apply_fill / ...` mutable borrow 暢通
- Rust NLL 在 single-iteration scope 內正確判定 disjoint

### 4.4 §7 跨平台 / §九 LOC cap / §九 singleton

| 對照項 | 結果 |
|---|---|
| §七 跨平台路徑 | ✓ 0 硬編碼路徑 |
| §七 雙語注釋 | ✓ 新代碼默認中文（per 2026-05-05 governance）；既有英文注釋不主動清 |
| §九 singleton table | N/A（無新 singleton；W1/W2 sub-agent IMPL 時會新增 PanelSlot 須登記） |
| §九 LOC cap | alpha_surface.rs 506→604（ <2000 cap）；slots.rs 163→181；step_4_5_dispatch.rs 1431→1457；mod.rs 1155→1164 — 全 <2000 cap |
| Bybit API 字典 | N/A（trait skeleton 無 Bybit endpoint touch；W1/W2 collector IMPL 時要查） |

### 4.5 16 根原則合規

| 原則 | 結果 |
|---|---|
| 1 單一寫入口 | ✓ trait skeleton 不寫入路徑 |
| 4 不繞風控 | ✓ 0 GovernanceHub / SM-04 touch |
| 7 學習 ≠ 改寫 Live | ✓ paper-only fence 由 step_4_5_dispatch engine_mode gate 主防線實施（trait 不知 fence） |
| 8 交易可解釋 | ✓ panel snapshot field 含 source_tier + snapshot_ts_ms 可追溯 |
| 硬邊界 5 項 | ✓ 0 touch live_execution_allowed / max_retries=0 / OPENCLAW_ALLOW_MAINNET / decision_lease / authorization.json |

---

## 5. 不確定之處 / Cross-wave concerns

### 5.1 Tier 2 LOC 超 dispatch 估計

dispatch 估計 ~85 LOC，實際 +180 LOC。原因：
- BtcLeadLagPanel struct 含完整 doc + 8 field，~30 LOC（spec 估 25 LOC）
- TickContext field doc + position_state 設計注釋 ~10 LOC
- 28 個 test callsite bulk-patch 各 +1 line = ~28 LOC（dispatch 未估計，只說「改 TickContext signature 影響 5 個策略」）
- 兩處 anchor comment 各 ~18 / 13 LOC（dispatch 未明列）

請 PM 接受此 LOC 略超估計（仍遠小於 W7 完整 IMPL 預估的 ~50+30 LOC × 5 策略 = ~400 LOC）。

### 5.2 Tier 2 完成後 W7-1 是否仍需 W7 sprint？

dispatch v3.1 W7 留「PA 統一審 5 策略 lifetime」。本 D+0 預寫只完成 trait skeleton + per-iteration borrow pattern + 28 callsite mechanical patch；**未動 5 策略 on_tick body 內 entry path 的 `if let Some(pos) = ctx.position_state` consumer code**。

W7 sprint 仍需：
1. 各策略 on_tick entry path 加 `if let Some(_) = ctx.position_state { return vec![]; }` skip 邏輯（5 處）
2. 與 W7-3 ma_crossover on_rejection duplicate_position sync（commit `d8697c41`）的協同設計（避免雙寫 cross-strategy state）
3. PA 對 5 策略 lifetime 的統一審查（particularly bb_breakout / bb_reversion / grid_trading / funding_arb / ma_crossover 各自的 prev_position cache 是否仍需要）

### 5.3 Multi-session race / 工作樹混合

`git status --short` 顯示 3 個非我修改的檔（`docs/CCAgentWorkSpace/MIT/memory.md` / `memory/MEMORY.md` / `memory/project_2026_05_09_ml_training_cron_weekly.md`）+ 2 個 untracked report file 來自其他並行 session。我未動這些檔，PM commit 時請按需選擇 stage（建議只 stage 我的 16 個 Rust file）。

---

## 6. Acceptance summary

```
cargo check --release -p openclaw_core    → PASS（0 error / 0 warning）
cargo check --release -p openclaw_engine  → PASS（0 error / 18 pre-existing warnings）
cargo build --release -p openclaw_engine --bin openclaw-engine → PASS

cargo test --lib --release -p openclaw_core   → 433 PASS / 0 FAIL（+1 new test btc_lead_lag_default_none）
cargo test --lib --release -p openclaw_engine → 2640 PASS / 0 FAIL（baseline 維持）
cargo test --release -p openclaw_engine --test stress_integration → 35 PASS / 0 FAIL
cargo test --release -p openclaw_engine --test replay_runner_e2e  → 6 PASS / 0 FAIL
  含 proof_5_baseline_vs_candidate_two_runs PASS（byte-identical replay 維持）
```

**NOT COMMITTED, NOT DEPLOYED** — modify file 留 PM 21:30 sign-off 後 commit + push。

---

## 7. PM 下一步

1. **PM sign-off + commit**：建議單一 commit 內容：
   - 16 個 Rust file（per `git diff --stat -- 'rust/'` 列表）
   - **不**包含 docs/CCAgentWorkSpace/MIT/memory.md / memory/MEMORY.md / memory/project_2026_05_09_ml_training_cron_weekly.md（其他並行 session WIP）
   - **不**包含 untracked 的 `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md` / `docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_rfc_qc_questions_self_answer.md`（其他 session 寫的 report）
   - 但**必含**本 sign-off report `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w2_w7_1_trait_skeleton_prewrite.md`（untracked）
2. **不部署**：trait skeleton 純架構性 LOC，runtime 行為 0 變化（cargo test --lib 2640 PASS 證明）；待 W1/W2/W7 IMPL sub-agent 全部 land 後再 `restart_all.sh --rebuild`
3. **W1/W2 sub-agent 派發**：N+1 W1+W2 五個 E1 sub-agent 完全並行 0 file 重疊
   - W1 E1-α (B-1)：funding_curve_writer + V085 + slots.rs 加 FundingCurvePanelSlot anchor 下方 + step_4_5_dispatch surface field
   - W1 E1-β (B-2)：oi_delta_panel_writer + V087 + slots.rs anchor + dispatch field
   - W2 E1-γ (C-IMPL-1)：BtcLeadLagPanel typedef 驗收 + 寫 W2 spec 對照表（**本預寫已完成 typedef，C-IMPL-1 NO-OP**）
   - W2 E1-δ (C-IMPL-2)：lead-lag producer + V088 + slots.rs anchor + dispatch field（含 paper-only engine_mode gate）
   - W2 E1-ε (C-IMPL-3)：strategy paper-only 接收（ma_crossover + grid_trading declare CrossAsset tag + on_tick shadow log）
4. **W7-1 sub-agent 派發**：trait skeleton 已 land + per-iteration borrow pattern 已驗，W7 sprint 只需：
   - 5 策略 on_tick entry path 加 `if let Some(_) = ctx.position_state { return vec![]; }` 5 處
   - PA 統一審 5 策略 lifetime + W7-3 on_rejection duplicate_position sync 協同

E1 IMPLEMENTATION DONE: 待 E2 審查（report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w2_w7_1_trait_skeleton_prewrite.md`）
