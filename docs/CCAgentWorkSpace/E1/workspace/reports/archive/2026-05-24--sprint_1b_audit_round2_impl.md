---
report: Sprint 1B audit Bug 1 + Bug 2 — Round 2 fix（E2 RETURN 8 finding 修補）
date: 2026-05-24
author: E1 (Backend Developer, Rust)
phase: Sprint 1B audit IMPL — Round 2 待 E2 review
status: IMPL DONE — cargo build PASS 28.55s + cargo test 4135 PASS / 1 pre-existing FAIL / 5 ignored
parent dispatch:
  - PM Round 2 dispatch（operator prompt 2026-05-24，E2 RETURN 8 finding）
runtime: Mac development（cargo build --release + cargo test --release --workspace --no-fail-fast）
production engine: 未碰
---

# §0. TL;DR

E2 RETURN 8 finding 全 closed，含 3 CRITICAL / 3 HIGH / 3 MEDIUM/LOW。Round 1 baseline 4132 PASS → Round 2 4135 PASS（+3 new test 含 release-mode defence + finding 5 reverse-fire + finding 1 grid short emit via helper）。1 pre-existing flaky FAIL（`layer_2_fence_archive_policy_diagnostic_only` / W2-IMPL-5 stalled / 0 耦合本 IMPL）與 round 1 同。

# §1. 8 Finding 修補對照

| # | Sev | File:Line | 修法 | 狀態 |
|---|---|---|---|---|
| 1 | C | bb_breakout 855 / bb_reversion 324 / ma_crossover/helpers 85 / funding_arb 499 / funding_harvest 517 / grid_trading/signal 345+380 | 8 emit 全改走 `OrderIntent::new_trade(...)`；6 strategy file 連帶清 unused `IntentType` import | closed |
| 2 | C | tick_pipeline/commands.rs 195-216 | submit_external_order 改走 helper（refactor +是 line 210-213 反模式註釋全消） | closed |
| 3 | C | tick_pipeline/on_tick_helpers.rs 173-199 | build_intent 內 if-派生 intent_type（caller is_long=false 不再殘留 OpenLong）+ caller step_4_5_dispatch.rs:1617 註釋對齊 | closed |
| 4 | H | step_4_5_dispatch.rs:1655 + step_6_risk_checks.rs:396 + 578 | grep apply_confirmed_fill 確認**不**回呼 strategy callback → 接受 dispatch-time best-effort；4 處 fallback chain 改 `latest_price → entry_price → 0.0` 對稱（pre-close snapshot entry_price） | closed |
| 5 | H | step_6_risk_checks.rs:578 + 396 | 同 finding 4 + 新 test 反證 buggy_pnl < -50 證 funding_harvest ledger close(0.0) 負巨額（finding 5 RCA） | closed |
| 6 | H | intent_processor/mod.rs:311-326 | validate() dual-layer：debug_assert + release path tracing::warn! telemetry（defence in depth，不阻擋 hot path） | closed |
| 7 | M | orchestrator.rs:361 / mode_state.rs:402 / router.rs:1107 | 3 fixture 誤導注釋改「Round 2 finding 7：本 fixture only — production caller 必走 new_trade helper」+ self-consistent 註明 | closed |
| 8 | M | funding_arb.rs:1183 test fixture | 改走 `new_trade(false, ...)` helper；自動派生 OpenShort，消除 is_long=false/OpenLong 矛盾 living example | closed |
| 9 | L | strategies/mod.rs:154 trait doc | doc 對齊 finding 5 實作：fallback chain `latest_price → entry_price → 0.0`，註明不直接 fallback 0.0 避 funding_harvest ledger 負巨額 | closed |

**11 file 動，淨 +130 LOC**（8 emit 大幅精簡 -100 LOC + helper enforcement note +30 + validate dual-layer +25 + on_tick_helpers 派生 +10 + 4 fallback chain 對稱 +40 + 3 fixture 註釋 +10 + finding 8 改 helper +5 + 新 3 test +110 + 6 import 清理 -6）。

# §2. 關鍵 diff

**Finding 6 validate() dual-layer**（intent_processor/mod.rs:311-340）：

```rust
pub fn validate(&self) {
    let aligned = self.intent_type.is_earn()
        || matches!(
            (self.is_long, &self.intent_type),
            (true, IntentType::OpenLong | IntentType::CloseLong | IntentType::PositionAdjust)
                | (false, IntentType::OpenShort | IntentType::CloseShort | IntentType::PositionAdjust)
        );
    debug_assert!(aligned, "IntentType direction mismatch: ...");
    // Round 2 finding 6：release path 防線 —— warn telemetry 取代 silent passthrough。
    if !aligned {
        tracing::warn!(
            is_long = self.is_long, ?self.intent_type, symbol = %self.symbol, strategy = %self.strategy,
            "IntentType direction mismatch detected at validate() — caller bypassed new_trade helper"
        );
    }
}
```

**Finding 4 + 5 fallback chain 對稱**（step_6_risk_checks.rs:578）：

```rust
// 舊：self.paper_state.latest_price(sym).unwrap_or(0.0)
// 新：pre-close snapshot entry_price + chain
let entry_price_snap = self.paper_state.get_position(sym).map(|p| p.entry_price).unwrap_or(0.0);
// ...close...
let close_px_for_cb = if let Some(...) = close_result { ... } else {
    self.paper_state.latest_price(sym).unwrap_or(entry_price_snap)
};
```

**Finding 1 grid short emit via helper**（grid_trading/signal.rs:380）：

```rust
// 舊：let intent = OrderIntent { is_long: false, ..., intent_type: IntentType::OpenShort, ... };
// 新：
let intent = OrderIntent::new_trade(
    ctx.symbol.to_string(), false, self.qty_per_grid, conf, self.name().into(),
    order_type, limit_price, None, None, time_in_force, maker_timeout_ms,
);
```

# §3. cargo build + cargo test 結果

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release --workspace` | **PASS 28.55s**（2 pre-existing dead_code warning，0 new） |
| 新 3 test 個別 | `cargo test --release -p openclaw_engine --lib intent_processor::tests::order_intent_validate_release_path / grid_short_emit_via_new_trade` + `strategies::funding_harvest::tests_synthetic::dispatch_fallback_entry_price` | **3/3 PASS** |
| funding_harvest 全 | `cargo test --release -p openclaw_engine --lib strategies::funding_harvest` | **67 PASS / 0 FAIL**（+1 new = dispatch_fallback 反證） |
| **全工作區** | `cargo test --release --workspace --no-fail-fast` | **4135 PASS / 1 FAIL（pre-existing flaky）/ 5 ignored**（baseline 4132 → 4135 +3 new test） |

1 FAIL = `layer_2_fence_archive_policy_diagnostic_only`（tests/btc_lead_lag_panel_fence_integration.rs:300）：W2-IMPL-5 stalled sub-agent collateral，**與本 IMPL 0 耦合**（0 動 panel_aggregator / 0 動 main.rs / 0 動 env-var 解析），與 round 1 同款 pre-existing 債務。

# §4. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 live_execution_allowed / execution_authority / system_mode / max_retries / production engine / V### SQL ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文；觸及既有 bilingual block 不主動清；無 emoji；6 strategy file 連帶清 unused IntentType import 是 finding 1 修法的編譯期副作用 ✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 review；不自行 commit；不派下游 sub-agent ✓ |
| **§九 Code Structure Guardrails** | step_4_5_dispatch.rs 1788 LOC（< 2000；本 IMPL +6）；step_6_risk_checks.rs 633 LOC（< 800）；intent_processor/mod.rs +25 release defence ✓ |
| **bilingual-comment-style** | Round 2 finding 補注全中文；保留既有英文 doc 段（pre-existing P1-16 / EXIT-FEATURES 等）✓ |
| **反模式 self-check（finding 提出視角）** | (a) 0 strategy emit 殘留 inline literal ✓ (b) 0 production caller 殘留寫死 OpenLong ✓ (c) build_intent 內派生 ✓ (d) fallback chain 4 處全對稱 ✓ (e) validate() release path 有 warn 防線 ✓ (f) fixture 注釋全更新 ✓ (g) test fixture self-consistent ✓ (h) trait doc 對齊實作 ✓ |

# §5. 真實 Round 2 工時 vs E2 預估

- E2 預估 2 hr
- 實際 Round 2 工時 ≈ 1.5 hr：
  - 起跑 ground truth 掃 8 finding 當前 state（30 min）
  - 8 finding edit（45 min，含 helper enforcement + fallback chain + dual-layer validate）
  - 3 new test 撰寫 + 單跑驗證（15 min）
  - 全工作區 cargo test final verify（10 min）
  - 本 report 撰寫（10 min）

# §6. 不確定之處 / Push back

**0 push back**。8 finding 全 closed，無 operator 決策懸念：
- Finding 6 release path 採方案 (a) warn telemetry（保 hot path 不 panic + 不阻擋 + 留 telemetry trace）— 折衷 fail-soft；若 PA/E2 認為 release 須完全 fail-closed reject，需 IntentResult 加 reject path 屬大改 scope，不在本 round 2 範圍。
- Finding 7 採「per-file fixture 注釋對齊」非「cross-file 抽 helper」— 後者違 surgical changes 原則（會引 cross-mod helper crate）。

# §7. Operator 下一步

1. **PM 派 E2 Round 2 review**（focus 8 finding closure verify + 3 new test reverse-fire validity）。
2. **E2 Round 2 預估 1 hr**（per prompt §「E2 round 2 review 預估另派 1 hr」）。
3. **E4 regression** 預估 1.5 hr，對齊 baseline 4135 PASS / 1 pre-existing FAIL。
4. **不 commit + 不 deploy + 不 restart engine**：per dispatch §「不 deploy / 不 restart engine」明示。

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-24--sprint_1b_audit_round2_impl.md`）**
