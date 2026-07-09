# PA — P0 Replay Engine Counterfactual Fix Design（2026-05-11）

**Owner**：PA
**Trigger**：operator 拍板「修 replay engine 讓它能對策略修改做真實 counterfactual validation」。前次 E1 (`a9729bbc4d61a0082` / report `2026-05-11--option_2_replay_engine_validation_v2.md`) 確認真實 Rust binary 跑起來但 6 個 hardcoded 結構性 blocker 讓 replay 無法驗證 Phase 0 / A-Lite / Option 2。
**Scope**：design only — 不寫業務 code。
**Branch**：main HEAD `6adb37ac`（待 head re-check at deploy time）
**改動風險評級**：Tier A **中**；Tier B **高**（觸 strategy 簽名 + DB ingest）
**16 原則合規**：16/16；**DOC-08 §12 9 不變量觸碰**：0；**§四 5 硬邊界觸碰**：0
**forbidden_guard / V3 §6.2 違反**：0（兩 tier 全綠，詳 §5）

---

## 1 任務摘要

修 replay framework，使「同樣 27h 數據 + 同樣 5 策略 + 同樣 25 sym」能 replay 出與 actual 接近的行為（fills, symbols, attribution），並對策略修改（Phase 0 / A-Lite / Option 2 / 未來新策略邏輯）產生可量化 PnL delta。

操作邊界：**不可破** `replay_isolated` feature 與 V3 §6.2 forbidden_guard — 即「不可拉 IPC / lease / dispatch / paper_state mutate / canary_writer / DB writer / bybit_*」。

策略：分 Tier A（緊急 ship） + Tier B（理想態 alpha-coupled），用「同 trait 但 replay-pure 旁路結構」處理跨界。

---

## 2 6 個 Hardcoded 的真實狀態與 fix 難度

| # | Location | 真 hardcoded 還是 wire-up default | Min LOC | 風險 | Tier |
|---|---|---|---|---|---|
| 1 | `runner.rs:1151 is_pinned: true` | 真 hardcoded（build_tick_context 寫死） | ~30 | 低 | A |
| 2 | `runner.rs:1148 position_state: None` | 真 hardcoded；ReplayPaperSnapshot 雖在 mutate 但沒接到 ctx | ~80 | 中 | A |
| 3 | `runner.rs:1145 alpha_surface_ref: EMPTY` | 真 hardcoded；W-AUDIT-8a Phase B/C/D 才會有 panel collector | ~150 (Tier B only) | 高 | **B** |
| 4 | Scanner pinned set | wire-up 缺；Rust 已能讀 `manifest.scanner_config`（config.rs:7-31），但 Python `_build_manifest_jsonb` 從不寫該 key | ~25 Python + 0 Rust | 低 | A |
| 5 | `manifest.strategy_params` null | wire-up 缺；Rust 已能 deserialise (`replay_runner.rs:435-447`)，Python `_fetch_full_chain_strategy_params` 已抓但 `_build_manifest_jsonb` 從不 echo 給 manifest | ~15 Python | 低 | A |
| 6 | Kelly sizer first_event_price anchor | 不是 Kelly bug — `replay_runner.rs:384` 用 `events.first().close` 作所有 symbol 的 snapshot anchor；之後 adapter loop `snap.latest_price = Some(event.close)` 每 event 覆寫，但**首 tick** ETHUSDT 用 ADAUSDT 0.2717 算 P1 cap 仍可能爆量 | ~20 Rust + ~10 Python（per-symbol price registry） | 中 | A |

### 2.1 #1 `is_pinned: true` — 真 hardcoded

`runner.rs:1149-1151` 直接寫 `true`。實際上 scanner_timeline 已存在 `is_active_at(symbol, ts_ms)` API（`scanner_timeline.rs:261`），且 `IsolatedPipeline.scanner_timeline: Option<ReplayScannerTimeline>` 已被 `with_scanner_timeline` 接入。等價 production 邏輯：`SymbolRegistry::is_pinned(symbol)` 對 timeline 而言就是「在 active_symbols cohort 內」+ pinned_symbols 永鎖。

**Fix shape**：build_tick_context 多收一個 `is_pinned: bool` 參數，由 caller 從 `scanner_timeline.latest_cycle_at(ts_ms)` 推算（pinned_symbols ∪ scanner active dynamic-adds）。

### 2.2 #2 `position_state: None` — 真 hardcoded

`PaperPosition` 在 `paper_state::containers`（data struct 純 #[derive(Clone, Serialize)]），TickContext 已直接 import 它（`tick_pipeline/mod.rs:32 use crate::paper_state::PaperPosition`）。**replay 引 PaperPosition data struct 不破 forbidden_guard** — 因為 forbidden_guard 禁的是「PaperState 全 mutate side（DB writer channel + 全域 mutate）」，data container 是同一 module 的純 type 別名。

ReplayPaperSnapshot.positions 已是 `Vec<ReplayPosition>`，apply_fill_open/close 已 mutate（`apply_fill.rs:624-688`）。剩下要做的是：build_tick_context 從 paper_snapshot 查當前 symbol 是否有 position → 若有就構造一個 stack-local PaperPosition borrow 餵 `ctx.position_state`。

### 2.3 #3 `alpha_surface_ref: EMPTY` — wire-up depends on W-AUDIT-8a Phase B/C/D

`EMPTY_ALPHA_SURFACE` 是 Phase A 共識（CLAUDE.md §五 W-AUDIT-8a SPEC PHASE）— production runtime 目前 Tier 2-4 panel collector 也尚未 land；W2 IMPL chain（HEAD `9463f778`）剛 land BTC lead-lag panel 的 Producer，但 strategy on_tick 仍只 cross-asset shadow log。**今日 production runtime 也是 EMPTY_ALPHA_SURFACE 為主**，replay 用 EMPTY 反而與 production 對齊；要餵入 alpha surface 數據必先把 Tier 2/3/4 panel collector 接出來，這是 W-AUDIT-8a 8b/8c/8d 工作，非本任務範圍。

**判斷**：Tier A 不修 #3，accept replay 在這個 axis 與 production runtime 等價（4/5 策略 0 fill 是 alpha-deficient 真實表現的反映，不是 replay bug）。Tier B 等 W-AUDIT-8a Phase B/C/D land 後一起做。

### 2.4 #4 Scanner pinned set wire-up — 0 Rust 改

`bin/replay_runner/config.rs:7-31` 已可從 `manifest.scanner_config` blob deserialise 為 `ScannerConfig`。**問題在 Python 端從不寫該 key**：

- `replay_full_chain_routes.py:1443-1474 _build_manifest_jsonb` 13 個 field 寫入，**沒有 scanner_config**
- `route_helpers.py:892-894 build_default_manifest_payload` 已會「if manifest_jsonb has scanner_config 就 forward」— 但 manifest_jsonb 沒有
- production `settings/risk_control_rules/scanner_config.toml` 是 SoT，operator 已在跑

**Fix shape**：Python `_build_manifest_jsonb` 加 `"scanner_config": _load_production_scanner_config()`，從 TOML deserialise 為 dict 寫入。

### 2.5 #5 `manifest.strategy_params` null — 0 Rust 改

E1 報告 §5.5 證實 PG `SELECT manifest_jsonb->'strategy_params' FROM replay.experiments → empty`。但 `_register_full_chain_experiment` line 1505-1507 已 pass `strategy_params=strategy_params` 給 register handler；register handler 寫進 V049 表，`route_helpers.py:922-928` 在 build_default_manifest_payload 時用 `lookup_replay_config_blob(cur, experiment_id)` 取回注 manifest payload。**這條 path 已存在**。

E1 報告觀察「manifest 是 null」可能源自：(a) `_fetch_full_chain_strategy_params` 返回 None / empty（engine=demo 對應的 PG strategy_params 沒記錄）/ (b) V049 lookup 路徑 caller 漏接 / (c) E1 觀察的 manifest_jsonb 沒 echo（manifest_jsonb 不存 strategy_params 是 by-design — 它存 V049 blob lookup 而非直接 embed）。

**Fix shape**：把 `strategy_params` 與 `risk_overrides` 直接 echo 進 `_build_manifest_jsonb`（不依賴 V049 blob lookup detour）。簡化路徑 + 與 scanner_config 對稱。

### 2.6 #6 Kelly sizer 3 億 ETH intent — first_event_price 錯 anchor

decision_trace 顯示 ETHUSDT 出 `qty: 332065733` 是因為 `replay_runner.rs:384-389 first_event_price = events.first().close`，5 個 strategy subprocess 各跑時 first_event 在 fixture 內混排排序後第一個是 ADAUSDT 0.2717（不是 25 sym 中每 sym 各有 first）。當第一個 tick 處理 ETHUSDT 時 `snap.latest_price` 還是 0.2717 → Gate 2.6 `p1_max_qty = balance × p1_risk_pct / 0.2717 = 10000 × 0.005 / 0.2717 = 184 ETH-equivalent`，但 strategy intent.qty 帶來「sized for $50 risk on $2335 ETH」≈ 0.02 ETH，被 Kelly clamp 後再走 P1 cap...

實際數字 3 億顯示 Kelly compute 路徑也有問題（不只 first_event_price）。讀 `risk_adapter.rs:328` `let price = snapshot.latest_price.unwrap_or(0.0)` 配 `compute_kelly_qty(..., snapshot.balance, price, atr_pct, guardian_qty)`：當 price=0.2717 時 Kelly 算出對應 ADAUSDT-sized qty，但 strategy 端 OrderIntent.qty 已是 ETHUSDT-sized（策略已用真實 ETH price 算）...

**根因**：`build_tick_context` 在 process 每個 event 時，`snap.latest_price = Some(event.close)` 是**全域**單一 `Option<f64>`，不是 per-symbol。當 ADAUSDT event → 設 0.2717 → 下一個 BTCUSDT event 設 64000 → 下一個 ETHUSDT event 設 2335。同一 tick 內如果 strategy 對 ETHUSDT 出 intent，它的 evaluate 用「上一 event 的 price」當 anchor，**錯誤地拿其他 symbol 的價算自己 symbol 的 cap**。

**Fix shape**：ReplayPaperSnapshot 加 `latest_price_by_symbol: HashMap<String, f64>`，evaluate 時用 `snapshot.latest_price_by_symbol.get(&intent.symbol).copied().unwrap_or(0.0)` 取 per-symbol anchor。Tier A 必修。

---

## 3 Tier A Design — Minimum Viable Counterfactual Replay

### 3.1 目標 acceptance

跑同 manifest + 同 27h fixture：
- replay 5 策略 total fills ≥ 80% × actual 277 fills（i.e. ≥ 220 fills）
- replay strategies-with-fills ≥ 3（actual: grid/ma/bb_reversion + unattributed）
- replay symbol cohort overlap ≥ 60%（actual top-10 sym ∈ replay output）
- 跑 Option 2 ON vs OFF 兩次 replay，replay 出**真實 delta**（grid_trading 非 pinned fill 數量 down）
- 跑 Phase 0 stop-bleed ON vs OFF 兩次 replay，bb_reversion / ma_crossover cross-strategy contamination 場景出現

### 3.2 Tier A 改動清單（~210 LOC）

| Task | File | LOC | 並行可性 |
|---|---|---|---|
| **T1** is_pinned wire | `rust/openclaw_engine/src/replay/runner.rs` + new helper in `replay_runner/config.rs` | ~30 | parallel with T2, T3, T4 |
| **T2** position_state wire | `rust/openclaw_engine/src/replay/runner.rs` (build_tick_context) | ~50 | parallel with T1, T3, T4 |
| **T3** scanner_config wire (Python) | `program_code/.../replay_full_chain_routes.py` `_build_manifest_jsonb` + new `_load_production_scanner_config()` helper | ~25 | parallel with T1, T2, T4 |
| **T4** strategy_params + risk_overrides echo (Python) | `program_code/.../replay_full_chain_routes.py` `_build_manifest_jsonb` | ~15 | parallel with T1, T2, T3 |
| **T5** per-symbol price anchor | `rust/openclaw_engine/src/replay/risk_adapter.rs` + `apply_fill.rs` 同步 update | ~50 | depends on T2 (same struct) |
| **T6** acceptance test pack | `tests/replay_counterfactual_tier_a.rs` 新檔 + 既有 `runner_tests.rs` 加 3 test | ~40 | rebase 等 T1-T5 land |

**Total**：~210 LOC。

### 3.3 各 Task 詳細 BEFORE/AFTER

#### T1 is_pinned wire

**BEFORE**（`runner.rs:1126-1153`）：
```rust
fn build_tick_context<'a>(
    event: &'a MarketEvent,
    inputs: &'a ReplayTickInputs,
) -> TickContext<'a> {
    TickContext {
        // ...
        is_pinned: true,  // hardcoded
    }
}
```

**AFTER**（concept）：
```rust
fn build_tick_context<'a>(
    event: &'a MarketEvent,
    inputs: &'a ReplayTickInputs,
    is_pinned: bool,                // ← 新參數
    position_state: Option<&'a PaperPosition>,  // ← 新參數 (T2)
) -> TickContext<'a> {
    TickContext {
        // ...
        position_state,
        is_pinned,
    }
}

// caller (`execute_adapter_pipeline`):
let is_pinned = self
    .scanner_timeline
    .as_ref()
    .map(|tl| tl.is_active_at(&event.symbol, event.ts_ms))
    .unwrap_or(true);  // 無 timeline 保留 true（synthetic walker 路徑）
```

對齊 production `step_4_5_dispatch.rs symbol_registry.is_pinned(symbol)`：scanner_timeline 已包含 pinned_symbols 永鎖 + active rotation，`is_active_at` 是等價語意。`unwrap_or(true)` 維持 synthetic walker proof_1/4/5 e2e byte-equal。

#### T2 position_state wire

**核心 invariant**：replay 內 position 由 `ReplayPaperSnapshot.positions: Vec<ReplayPosition>` 維護；要餵入 `ctx.position_state: Option<&'a PaperPosition>`，需在 build_tick_context 內把 ReplayPosition 構造成 stack-local `PaperPosition` 借用。

**BEFORE**：`build_tick_context` 寫 `position_state: None`，replay 中 ma_crossover/bb_reversion 的 `ctx.position_state.is_some()` cross-strategy guard 永遠 skip → false-negative，無法重現 attack 場景。

**AFTER**（concept）：
```rust
// 在 execute_adapter_pipeline 內 per-event，先構造 owned PaperPosition：
let stack_pp: Option<crate::paper_state::PaperPosition> = self
    .paper_snapshot
    .as_ref()
    .and_then(|snap| snap.get_position(&event.symbol))
    .map(|rp| crate::paper_state::PaperPosition {
        symbol: rp.symbol.clone(),
        is_long: rp.is_long,
        qty: rp.qty,
        entry_price: rp.entry_price,
        best_price: rp.entry_price,
        entry_fee: 0.0,
        entry_ts_ms: event.ts_ms.max(0) as u64,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: rp.owner_strategy.clone(),  // ← T2.5
        entry_notional: rp.qty * rp.entry_price,
        max_favorable_pnl_pct: 0.0,
        max_favorable_ts_ms: 0,
        // ...其餘 field default
    });
let pp_ref: Option<&crate::paper_state::PaperPosition> = stack_pp.as_ref();
let ctx = build_tick_context(event, &tick_inputs, is_pinned, pp_ref);
```

**子任務 T2.5（同 PR）**：`ReplayPosition` 新增 `pub owner_strategy: String` field（apply_fill_open 寫 `intent.strategy.clone()`，apply_fill_close 不改）。這是讓 cross-strategy attribution 在 replay 內可重現的關鍵。

**Lifetime 約束**：`stack_pp` 必須與 ctx 同 iteration scope 構造 + 釋放（NLL per-iteration），與 production `tick_pipeline/mod.rs:739-746` 設計對齊。

#### T3 scanner_config wire (Python)

**BEFORE**：`replay_full_chain_routes.py:1443-1474 _build_manifest_jsonb` 不寫 scanner_config。

**AFTER**（concept）：
```python
def _load_production_scanner_config() -> dict[str, Any]:
    """Read settings/risk_control_rules/scanner_config.toml and dict-ify for manifest."""
    base = Path(os.environ.get("OPENCLAW_BASE_DIR", ""))
    toml_path = base / "settings" / "risk_control_rules" / "scanner_config.toml"
    if not toml_path.exists():
        return {}  # 退 Rust replay_default_scanner_config()
    import tomllib  # py3.11+；或 fallback 到 toml lib
    with open(toml_path, "rb") as f:
        return tomllib.load(f)

# _build_manifest_jsonb 內加：
manifest["scanner_config"] = _load_production_scanner_config()
```

注意 ScannerConfig Rust 端 deserialise via `serde_json::from_value::<ScannerConfig>(...)`，TOML 與 JSON 在 nesting / key 命名應對齊 serde rename rules（production runtime 已驗證）。**E2 必查**：tomllib 讀出來的 dict 經 json serde → Rust ScannerConfig 是否 byte-equal 對齊。

#### T4 strategy_params + risk_overrides echo (Python)

**BEFORE**：`_build_manifest_jsonb` 不寫 strategy_params / risk_overrides；V049 blob lookup detour 是備援但 E1 觀察不可靠。

**AFTER**（concept）：
```python
def _build_manifest_jsonb(
    *,
    # ... existing params
    strategy_params: Optional[dict[str, Any]] = None,  # ← 新參數
    risk_overrides: Optional[dict[str, Any]] = None,   # ← 新參數
) -> dict[str, Any]:
    manifest = {
        # ... existing fields
    }
    manifest["scanner_config"] = _load_production_scanner_config()  # T3
    if strategy_params is not None:
        manifest["strategy_params"] = strategy_params
    if risk_overrides is not None:
        manifest["risk_overrides"] = risk_overrides
    return manifest

# Caller `post_replay_full_chain_run` line 1651：
manifest_jsonb = _build_manifest_jsonb(
    # ... existing
    strategy_params=strategy_params,  # 已 fetch at line 1092
    risk_overrides=risk_overrides,    # 已 fetch at line 1093
)
```

V049 detour 路徑保留為 backward compat（不刪除 `route_helpers.py:922-928` lookup）— 但新路徑直接 echo 進 manifest 是更顯式可靠的方式。

#### T5 per-symbol price anchor

**BEFORE**：`ReplayPaperSnapshot.latest_price: Option<f64>` 全域單一；evaluate 中 `let price = snapshot.latest_price.unwrap_or(0.0)` 對所有 intent 用同 anchor。

**AFTER**（concept）：
```rust
// risk_adapter.rs:
pub struct ReplayPaperSnapshot {
    pub balance: f64,
    pub drawdown_pct: f64,
    pub positions: Vec<ReplayPosition>,
    pub latest_price: Option<f64>,  // 保留作 fallback（snapshot validation）
    pub latest_price_by_symbol: std::collections::HashMap<String, f64>,  // ← 新增
    // ...其餘 unchanged
}

// evaluate (risk_adapter.rs:328):
let price = snapshot
    .latest_price_by_symbol
    .get(&intent.symbol)
    .copied()
    .or(snapshot.latest_price)  // fallback for backward compat
    .unwrap_or(0.0);
```

執行端（`runner.rs:987` 內 `snap.latest_price = Some(event.close)`）改為：
```rust
if let Some(snap) = self.paper_snapshot.as_mut() {
    snap.latest_price = Some(event.close);  // 保留作 last-touched fallback
    snap.latest_price_by_symbol
        .insert(event.symbol.clone(), event.close);  // ← 新增
}
```

Validation（`runner.rs:660-681 with_adapter_pipeline`）：保留 `latest_price.is_none() && positions.is_empty() → InvalidSnapshot`，但更精確 fail-loud 是檢查 `latest_price_by_symbol.is_empty() && positions.is_empty()` — E2 review point。

#### T6 acceptance test pack

新檔 `tests/replay_counterfactual_tier_a.rs`，3 個 acceptance test：
1. `test_replay_is_pinned_reflects_scanner_timeline` — manifest 帶 `scanner_config` BTCUSDT pinned + ETHUSDT dynamic-add，BTCUSDT event `ctx.is_pinned=true`、ETHUSDT event `ctx.is_pinned=false`
2. `test_replay_position_state_reflects_open_position` — apply_fill_open(BTCUSDT, ma_crossover) 後下一個 BTCUSDT event 的 `ctx.position_state.is_some()` 且 `owner_strategy == "ma_crossover"`
3. `test_replay_per_symbol_price_anchor` — mixed ADAUSDT + ETHUSDT events，evaluate ETHUSDT intent 用 ETHUSDT price 不用 ADAUSDT price

`runner_tests.rs` 加 3 個 unit test：
- `build_tick_context_threads_is_pinned`
- `build_tick_context_threads_position_state_borrow_lifetime`
- `latest_price_by_symbol_falls_back_to_global`

### 3.4 E1 派發計劃

5 個 E1 並行（不重疊 file）：

| Sub-agent | Task | File | Est | Dependency |
|---|---|---|---|---|
| E1-A | T1 + T2 + T2.5 | `replay/runner.rs` + `replay/risk_adapter.rs` (struct add `owner_strategy`) | 3h | independent |
| E1-B | T3 + T4 | `replay_full_chain_routes.py` | 2h | independent |
| E1-C | T5 | `replay/risk_adapter.rs` (HashMap) + `replay/apply_fill.rs` (update site) + `bin/replay_runner.rs` (snapshot init) | 2h | rebase after E1-A struct change |
| E1-D | T6 acceptance test | `tests/replay_counterfactual_tier_a.rs` + `replay/runner_tests.rs` | 2h | rebase after E1-A + E1-C land |
| E1-E | docs + release notes | `docs/CCAgentWorkSpace/E1/...` reports | 1h | last |

**冲突管理**：E1-A 與 E1-C 都動 `risk_adapter.rs` ReplayPaperSnapshot struct — E1-A 先（純 field add T2.5 + 不動 evaluate），E1-C 後 rebase 加 latest_price_by_symbol。`runner.rs` 只 E1-A 動。`apply_fill.rs` 只 E1-C 動。

### 3.5 E2 重點審查 3 點

1. **PaperPosition stack-local borrow lifetime**：T2 在 execute_adapter_pipeline 內構造 `let stack_pp: Option<PaperPosition>` 然後 `let pp_ref: Option<&PaperPosition>` 餵 ctx。必須驗證 lifetime 對齊 `ctx` scope，per-iteration NLL 釋放後不影響下一 iteration 的 `apply_fill_open/close` mutate borrow `snap`。E2 必跑 `cargo build --features replay_isolated` 確認 borrow checker 過；如不過要 review 是否 owned T1 by 改 TickContext field 改 owned 而非 borrowed（最後手段，避免）。

2. **Scanner config TOML→JSON byte-equal**：T3 用 tomllib 讀 TOML → Python dict → JSON serialize → Rust serde_json deserialise → ScannerConfig。E2 必對齊 production 已啟用的 scanner_config.toml 與 Rust ScannerConfig serde rename rules — 若 TOML 有 snake_case + Rust expects camelCase 會 fail。建議寫一個 byte-equal 對齊 unit test（Python 端 fixture + Rust 端 parse round-trip）。

3. **per-symbol anchor backward compat**：T5 加 `latest_price_by_symbol` 但保留 `latest_price`。E2 必確認所有讀 `latest_price` 的 callsite（risk_adapter evaluate / apply_fill 4 處 / report_writer 1 處）改用 `latest_price_by_symbol.get(symbol).or(latest_price)` 或明確的 fallback chain。**Worst case**：忘改某 callsite → 該 callsite 還用 last-touched price 造成 silent semantic drift。建議 grep `\.latest_price\b` 全部標 TODO 並 PR 內逐個驗證。

---

## 4 Tier B Design — Full Counterfactual（理想態）

### 4.1 觸發條件

不建議現在做。Tier B 的 alpha_surface 真值依賴 W-AUDIT-8a Phase B/C/D land：
- Phase B Tier 2 panel collector：funding_curve / oi_delta / btc_lead_lag（W2 land 一部分，btc_lead_lag W2 已 D+0 但 strategy on_tick 只 shadow log）
- Phase C Tier 3 microstructure：orderflow / liquidation_pulse
- Phase D Tier 4 information flow：event_alerts / regime_tag / sentiment_panel

Tier B 要把上述 panel 從 production runtime DB 或 fixture 端 reconstruct 成 historical snapshot 餵 replay。**最早可開工時點 = W-AUDIT-8a Phase B/C/D IMPL DONE**，per CLAUDE.md §三 估 Sprint N+2 末 / N+3 初。

### 4.2 Tier B 額外改動（~500 LOC）

| # | Item | LOC |
|---|---|---|
| B1 | AlphaSurface historical snapshot loader（從 PG `panel.*` 表 + replay window 重建） | ~200 |
| B2 | `with_alpha_surface_timeline` builder + `IsolatedPipeline.alpha_surface_timeline` 欄位 | ~80 |
| B3 | build_tick_context 加 `alpha_surface_ref` per-event lookup（從 timeline binary search） | ~50 |
| B4 | Manifest schema 加 `alpha_surface_source: 'tier_2_panels_only' | 'all_tiers'` enum + validation | ~30 |
| B5 | Python 端 `_build_manifest_jsonb` 加 panel.* snapshot range references + 不過大 inline blob | ~50 |
| B6 | acceptance test：alpha_surface ON 對應策略產生 fills 數量增 | ~50 |
| B7 | E2 review + benchmark（panel collector 大量加 in-memory cost vs 60s replay budget） | ~40 |

**風險**：Tier B 觸 `crate::panel_aggregator` 或 `openclaw_core::alpha_surface` collector — collector 本身可能拉 PG writer / IPC subscriber 等 forbidden surface。需先做 boundary audit 確認 `AlphaSurface` data struct（pure data）vs `AlphaSurfaceCollector`（含 mutate side）的拆分線。可能需要新增 `replay_compatible_alpha_loader` mod 走唯讀 PG read-only path。

---

## 5 forbidden_guard / V3 §6.2 對齊驗證

### 5.1 Tier A 變動逐項對 7 條 forbidden surface check

| Surface | T1 is_pinned | T2 position_state | T3/T4 manifest | T5 anchor | T6 test |
|---|---|---|---|---|---|
| Decision Lease acquire/release | not touched | not touched | not touched | not touched | not touched |
| IPC server start | not touched | not touched | not touched | not touched | not touched |
| WS client start | not touched | not touched | not touched | not touched | not touched |
| Exchange dispatch | not touched | not touched | not touched | not touched | not touched |
| DB writer channel use | not touched | not touched | not touched (寫 manifest 是 register handler 既有路徑) | not touched | not touched |
| Live/demo config mutate | not touched | not touched | not touched (manifest 是 replay-only) | not touched | not touched |
| Advisory write outside PL/pgSQL | not touched | not touched | not touched (V049 既有 path) | not touched | not touched |

**T2 對 `crate::paper_state::PaperPosition` 引用合規性**：
- 既有 fact：`tick_pipeline/mod.rs:32 use crate::paper_state::{PaperPosition, PaperState}` — `PaperState` 是 forbidden（DB writer + 全域 mutate），但 `PaperPosition` 是 `paper_state::containers.rs` 純 data struct（`#[derive(Debug, Clone, Serialize, Deserialize)]`）。
- 替代方案：若 E2 嚴格認為「from crate::paper_state import anything = 違反」，可請 E1-A 改 `crate::paper_state::containers::PaperPosition` 顯式 path（同型別，不同 import sugar）→ 強調用的是 container 不是全 module。
- **建議**：Tier A 用既有 import path `crate::paper_state::PaperPosition`（與 TickContext 對稱），E2 review 時驗證 forbidden_guard 機制是否 trip。**enforce_at_runtime 不檢查 use 路徑**（read-only env var + magic file marker），所以 import 本身不會 trip — 但 PA boundary allowlist §5 forbidden deps 是文件約定，E2 要 check `nm` symbol audit 不報新增 paper_state mutator symbol。

### 5.2 V3 §12 acceptance preservation

- #10 forbidden trip aborts run：T1-T5 不影響 forbidden_guard::enforce_at_runtime 邏輯，proof_4 acceptance test 不變
- #11 Isolated profile 唯一可受：T1-T5 全於 IsolatedPipeline 內，不擴大 profile 接受面
- #14 cross-language byte-equal：T1-T5 改 replay runner 行為；不影響 live `intent_processor::router` 路徑。但 replay byte-equal 與 live byte-equal 是兩條 invariant，replay 內部從「broken byte-equal pre-Phase 0 / A-Lite / Option 2」改為「reflect Phase 0 / A-Lite / Option 2 真實 delta」**就是目的**，符合 plan §6.R5 acceptance A4 parameter-delta proof spirit。

### 5.3 §四 5 硬邊界 0 觸碰

| 硬邊界 | Tier A 觸碰? |
|---|---|
| `live_execution_allowed` | 不觸 — replay isolated subprocess，永不打 Bybit |
| `decision_lease_emitted` | 不觸 — replay 跳 Gate 1.4 by design（risk_adapter MODULE_NOTE §1） |
| `max_retries = 0` | 不觸 — replay 不下單 |
| `OPENCLAW_ALLOW_MAINNET=1` | 不觸 — replay 不需 Bybit credentials |
| `live_reserved` system_mode | 不觸 — replay binary 不檢查 system_mode |

---

## 6 副作用識別

### 6.1 對既有 replay test 的影響

- **proof_1 / proof_4 / proof_5 e2e（synthetic walker path）**：T1 加 `is_pinned: bool` 參數 — 但 synthetic walker 路徑（runner.rs:840 `execute_synthetic_walker`）**不呼叫** `build_tick_context`（它直接 push SimulatedFill），所以 byte-equal 保證不破。
- **R5-T7 cross-language parameter delta test**：Tier A 改變 risk_adapter Kelly anchor 行為 — 期待 cross-language 1e-4 對齊仍成立**因為 live 端 router.rs 是 per-symbol price anchor 為主**（IntentProcessor.compute_kelly_qty 用 `paper_state.get_position(intent.symbol).map(|p| p.entry_price).or(latest_tick_price)`）。實際上 Tier A 把 replay anchor 對齊 live anchor，理應**更綠** cross-language equivalence。E4 必跑此 test 確認。

### 6.2 對 V045 manifest_jsonb hash 的影響

T3 + T4 加 fields 到 `manifest_jsonb` → register handler 計算 `sha256(canonical(manifest_jsonb))` 的結果會變。`replay.experiments.manifest_hash` 不變式（V045 + Sprint 1 Track A 簽名 verification）不破，因為 manifest_signer 端 `compute_manifest_canonical_bytes` 從 manifest_jsonb 整體 hash — 新 fields land 後**所有新 register 的 experiment 都會帶新 hash**，與既有歷史 experiment 不衝突（histidx by experiment_id 而非 hash）。

**E2 必查**：register handler `ReplayExperimentRegisterRequest` Pydantic schema 是否限制 manifest_jsonb top-level keys — 若有 whitelist 需同步加 `scanner_config / strategy_params / risk_overrides`。

### 6.3 對 V049 detour path 的影響

V049 `_replay_strategy_params` / `_replay_risk_overrides` blob lookup 仍走（`route_helpers.py:922-928`），與 T4 並存。**順序問題**：若 manifest_jsonb 直接 echo 與 V049 lookup 對同 key 衝突，目前 build_default_manifest_payload code 是「先讀 manifest，後 V049 覆寫」，T4 改後 V049 仍會覆寫 manifest。建議 T4 PR 同改 `route_helpers.py:922-928` 為「if manifest_jsonb has key, skip V049 lookup」（避免 silent re-write）。

### 6.4 對 historical replay run 的影響

既有 experiment 不會被 retroactively 改；只有 T3/T4 land 後**新**觸發的 `/full-chain/run` 才會帶新 fields。歷史 5 個 run（E1 報告 §4.3）保留作 baseline 比對工件。

---

## 7 風險評估

| 風險 | Likelihood | Impact | Mitigation |
|---|---|---|---|
| T2 lifetime borrow checker fail | 中 | 高（阻 ship） | E1-A 在第一個 build 跑 `cargo check --features replay_isolated`；若 fail 改 owned PaperPosition by-value into TickContext（最後手段） |
| T3 scanner TOML JSON serde mismatch | 中 | 中 | E1-B 必寫 round-trip test：load TOML → Python dict → JSON → Rust ScannerConfig deserialise → compare 各 field |
| T5 callsite forgotten | 低 | 中 | grep `\.latest_price\b` 列舉並逐個 review |
| forbidden_guard trip from new path | 極低 | 高（阻 ship） | E1-A 跑既有 `tests/replay_forbidden_guard_acceptance.rs` + nm symbol audit |
| 改動破 R5-T7 cross-language test | 低 | 中 | E4 regression 必跑 R5-T7；若失敗 RCA per-symbol anchor 差異 |
| W-AUDIT-8a Phase B/C/D 未 land 限制 Tier A acceptance bar | 中 | 低 | Tier A acceptance §3.1 只要求「Option 2 ON/OFF 真實 delta + Phase 0 cross-strategy contamination 可重現」，**不**要求 5/5 策略全 fill — alpha-deficient 策略仍可 0 fill（與 actual baseline 對齊） |

**總體風險評級**：**中**（純 isolated subprocess + adapter path 改造，0 動 hot path / 0 動 lease / 0 動 authorization）。

---

## 8 Tier A vs Tier B 推薦

**強烈建議 ship Tier A 先**：

| 維度 | Tier A | Tier B |
|---|---|---|
| LOC | ~210 | ~700 (A + B) |
| E1 days | ~1.5（5 並行 sub-agent 同步） | ~5（含 B7 review） |
| 風險 | 中 | 高 |
| 解 #1 #2 #4 #5 #6 | ✅ | ✅ |
| 解 #3 alpha_surface_ref | ❌ accept by-design | ✅ |
| W-AUDIT-8a 依賴 | 0 | Phase B/C/D land |
| 可立即驗證今日修復（Option 2 / Phase 0 / A-Lite） | ✅ | ✅（但等 N+2 末/N+3 初） |
| 對齊 production runtime alpha 狀態 | ✅（production 今日也 EMPTY） | ✅（pre-warm） |

**Tier A 後續路徑**：
- Sprint N+1 D+1 ship Tier A
- Sprint N+1 D+2 跑 Option 2 ON/OFF + Phase 0 ON/OFF + A-Lite 4-combo replay，量化 PnL delta
- Sprint N+2 等 W-AUDIT-8a Phase B/C/D land 後規劃 Tier B
- Sprint N+3 ship Tier B 完整 5-tier alpha surface 接入

---

## 9 16 原則 + DOC-08 §12 合規驗證

| 原則 | Tier A 對齊 |
|---|---|
| 1 單一寫入口 | ✅ replay 不下單 |
| 2 讀寫分離 | ✅ replay isolated subprocess，0 寫 production state |
| 3 AI ≠ 即時命令 | N/A (replay 不涉 AI runtime) |
| 4 策略不繞風控 | ✅ replay 仍走 6-Gate risk_adapter |
| 5 生存 > 利潤 | ✅ Tier A 不改 risk gate 順序 |
| 6 失敗默認收縮 | ✅ Tier A 各 wire-up 缺值 fallback 到 default（pinned=true / position=None / scanner=default / strategy_params=default） |
| 7 學習 ≠ 改寫 Live | ✅ replay 是學習平面 |
| 8 交易可解釋 | ✅ Tier A 加 decision_trace 完整度（per-symbol anchor + position_state 對齊 live） |
| 9 災難保護 | N/A |
| 10 認知誠實 | ✅ §2-4 區分「真 hardcoded / wire-up 缺 / accept by-design」三類 |
| 11 Agent 最大自主 | N/A |
| 12 持續進化 | ✅ Tier A 是 evolution acceptance（plan §6.R5 A4 parameter-delta proof spirit） |
| 13 AI 成本感知 | N/A |
| 14 零外部成本可運行 | ✅ replay 0 外部成本 |
| 15 多 Agent 協作 | N/A |
| 16 組合級風險 | ✅ Tier A 修 per-symbol anchor 強化組合級風險 attribution（Gate 2.6 P1 cap 不再用 cross-symbol anchor） |

**DOC-08 §12 9 不變量**：T1-T6 全 0 觸碰（replay 不觸 lease / auth / fills writer / Bybit / Authorization / reconciler / live boundary）。

**§四 5 硬邊界**：T1-T6 全 0 觸碰（無 live_execution / lease emit / retry / OPENCLAW_ALLOW_MAINNET / live_reserved 改動）。

---

## 10 不確定之處 + Operator 決定點

1. **T3 production scanner_config.toml dict-ify ：使用 tomllib (py3.11) vs toml package？** Linux runtime python version 確認 — 若 < 3.11 用 `tomli` 套件，但 requirements.txt 可能未列。E1-B 任務內先驗 python version 並 push back operator 若需新增依賴。

2. **T5 latest_price_by_symbol 與 trade_stats 對齊**：trade_stats Kelly 統計也是 per-symbol；當前 `ReplayPaperSnapshot.trade_stats: Option<TradeStats>` 全域單一。Tier A 是否同改 `trade_stats_by_symbol: HashMap<String, TradeStats>`？建議 **不在 Tier A 改** — 因 actual baseline trade_stats 累積在 PaperState 也是 mixed approximation，per-symbol trade_stats 是 Tier B alpha-coupled 範疇。

3. **forbidden_guard nm symbol audit threshold**：若 E1-A 引入 `crate::paper_state::PaperPosition` 觸發 nm audit alert — operator 決定是否接受（既有 TickContext 已有此 import，按精神 replay 應一致），還是要求 E1-A 把 PaperPosition 抽到 `openclaw_core::position` 公共 crate（重 refactor，可能不在本 sprint 預算）。

4. **Tier B 觸發條件**：W-AUDIT-8a Phase B/C/D 預估 N+2 末 / N+3 初 land — operator 確認是否同意 Tier B defer 到該點，或現在就規劃 panel reconstruction 平行（風險：W-AUDIT-8a 設計可能變、replay loader 要 refactor）。

5. **acceptance §3.1 量化門檻**：「replay fills ≥ 80% × actual」是初步建議 — 實測可能因 alpha-deficient 5 策略而 actual 本身只 6-fill（bb_reversion 主 driver），Tier A replay 預期 4-7 fills 是合理範圍。建議 **第一次 Tier A run 後再校準** ratio，不卡死門檻。

---

## 11 治理對照

| 規範 | Tier A 對齊 |
|---|---|
| CLAUDE.md §一 玄衡定位 | ✅ |
| §二 16 原則 | ✅ 16/16 |
| §四 硬邊界 5 條 | ✅ 0 觸碰 |
| §五 架構總覽 | ✅ replay 是 isolated subprocess，不動 main pipeline |
| §七 跨平台 | ✅ T3 用 OPENCLAW_BASE_DIR 環境變數，0 硬編碼 |
| §七 注釋 | ✅ Tier A 新代碼默認中文 |
| §七 SQL migration | N/A |
| §八 工作流（PA → E1 並行 → E2 → E4） | ✅ §3.4 派發 |
| §九 文件大小 2000 | ✅ runner.rs 1175 LOC + ~80 = 1255（OK） / risk_adapter.rs 562 + ~50 = 612（OK） |
| forbidden_guard / V3 §6.2 | ✅ 詳 §5 |
| V3 §12 #10/#11/#14 | ✅ 詳 §5.2 |
| Mac → Linux 部署可逆性 | ✅ Tier A 不引新平台特定 API |

---

## 12 完成序列

- [x] PA report `2026-05-11--p0_replay_engine_counterfactual_fix_design.md`（本檔）
- [x] PA memory entry 追加（見下節）
- [ ] commit + push（同 PR HEAD next）
- [ ] operator decision on 4 items in §10
- [ ] dispatch 5 sub-agent (E1-A / E1-B / E1-C / E1-D / E1-E) per §3.4
- [ ] E2 review per §3.5 + §6 副作用清單
- [ ] E4 regression：cargo test + R5-T7 cross-language parameter delta
- [ ] deploy Linux PG `--rebuild`（含 cargo build replay_runner binary）
- [ ] 跑 Tier A acceptance：Option 2 ON/OFF + Phase 0 ON/OFF + A-Lite 4-combo replay

---

## 13 PA Memory 追加

```markdown
## P0 Replay engine counterfactual fix design — Tier A v1（2026-05-11）

**觸發**：operator「修 replay engine 讓它能對策略修改做真實 counterfactual validation」；E1 a9729bbc4d61a 報告 6 hardcoded blockers。

**核心發現（PA empirical re-check after E1 report）**：
1. **#1 is_pinned**：真 hardcoded line 1151；scanner_timeline.is_active_at() 已存在；fix ≈ 30 LOC
2. **#2 position_state**：真 hardcoded；ReplayPaperSnapshot.positions Vec 已 mutate（apply_fill_open/close 1648-1745）；fix 需在 build_tick_context 構造 stack-local PaperPosition borrow 餵 ctx，~50 LOC + ReplayPosition 加 owner_strategy 是關鍵 attribution wire
3. **#3 alpha_surface_ref**：production runtime 今日也是 EMPTY（W-AUDIT-8a Phase B/C/D 未 land）— replay 用 EMPTY **反而與 production 對齊**，不是 bug；Tier A 不修，Tier B 等 alpha collector land
4. **#4 scanner_config**：Rust 端 config.rs:7-31 已可從 manifest.scanner_config 讀；Python `_build_manifest_jsonb` 從不寫該 key；fix = Python +25 LOC + 0 Rust
5. **#5 strategy_params**：Rust replay_runner.rs:435 已 deserialise；Python 路徑用 V049 detour（route_helpers.py:922-928）不可靠；fix = Python `_build_manifest_jsonb` 直接 echo +15 LOC
6. **#6 Kelly 3 億 ETH**：根因不是 Kelly bug 是 `ReplayPaperSnapshot.latest_price: Option<f64>` **全域單一 anchor** — 不同 symbol 共用 last-touched price；fix = 加 `latest_price_by_symbol: HashMap<String, f64>` per-symbol anchor，~50 LOC

**Tier A 設計**：~210 LOC，5 sub-agent 並行（E1-A T1+T2 / E1-B T3+T4 / E1-C T5 / E1-D T6 test / E1-E docs）；1.5 E1 days；風險中；forbidden_guard 全綠；16 原則 16/16；DOC-08 §12 0 觸碰；§四 5 硬邊界 0 觸碰。

**Tier B 推遲**：依賴 W-AUDIT-8a Phase B/C/D land；~500 LOC；N+2 末 / N+3 初規劃。

**E2 重點 3**：(1) T2 PaperPosition stack-local borrow lifetime per-iteration NLL；(2) T3 scanner TOML→JSON→ScannerConfig serde rename 對齊；(3) T5 grep `.latest_price` 全 callsite review backward compat

**核心教訓**：
1. **「Hardcoded」誤判 vs「wire-up 缺」**：E1 報告 6 hardcoded 中只有 #1/#2/#3 是真硬 code；#4/#5 是 Rust 端早就支援但 Python 從不寫；#6 是 ReplayPaperSnapshot 結構性局限。PA 真實復查 binary source > E1 categoric 判斷
2. **PaperPosition import 合規邊界**：`paper_state::containers.rs` 是 pure data struct（#[derive(Clone, Serialize)]），TickContext 已直接 import。forbidden_guard 禁的是 `PaperState mutate side`（全域 mutable + DB writer channel），data container 同 module 不同 layer。replay 引 PaperPosition data type 不破 forbidden invariant，但 E2 nm symbol audit 仍要驗
3. **Tier B 不應現在做**：alpha_surface 真值依賴 collector，collector 在 W-AUDIT-8a Phase B/C/D；現在做 Tier B = 重複 work + 設計可能變。Phase A spec 強調 EMPTY_ALPHA_SURFACE 與 production runtime 一致（CLAUDE.md §五 W-AUDIT-8a SPEC PHASE 2026-05-09），Tier A accept 是正確 trade-off
4. **per-symbol anchor 不只 Kelly cap 修正**：對齊 live `router.rs:373` price anchor 邏輯 = 強化 cross-language R5-T7 invariant equivalence，**理論上 replay 更綠**（不是更紅）
5. **§九 2000 LOC cap headroom**：Tier A 改 runner.rs +80 (1175→1255) / risk_adapter.rs +50 (562→612) 都安全；不需 pre-existing baseline exception clause

**完整報告**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_replay_engine_counterfactual_fix_design.md`
```

---

PA DESIGN DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_replay_engine_counterfactual_fix_design.md`
