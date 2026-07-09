# E1 — stress_integration.rs test-invariant drift fix · 2026-05-19

## 任務摘要

E2 RCA（2026-05-19）後修 2 個 pre-existing stress integration test
fails；定性為 **test-invariant drift**（測試沒跟上 fixture 演化），不是
production regression。

| 測試 | 驅動 commit | 失敗原因 |
|---|---|---|
| `stress_bb_reversion_extreme_oversold_bounce` | `6cfd0fcd` (2026-05-11) | P0 Option A-Lite 重構後 exit path 用 `ctx.position_state.owner_strategy == "bb_reversion"` 過濾自家持倉；測試 ctx2 仍傳 `position_state = None`，策略回到 entry path，無法觸發 mean-reversion exit。 |
| `stress_bb_breakout_valid_squeeze_with_volume` | `7a07348b` (2026-05-14) | Phase 8a OI fail-closed gate 要求每個 `on_tick` 都能解析 `oi_panel_delta_5m_pct`；測試傳 `EMPTY_ALPHA_SURFACE.oi_delta_panel = None` 直接走 `oi_panel_unavailable` 提前 `return vec![]`。 |

修法：在 `tests/stress_integration.rs` 加 2 個 helper + 改 2 個 test
fixture，**完全不動 production 邏輯**。

## 修改清單

1 file: `rust/openclaw_engine/tests/stress_integration.rs`
- +69 / -4 LOC（含中文 rationale comments）
- 新增 2 個 helper function + 新增 2 個 use import + 改 2 個 call site

## 關鍵 diff

### Use imports（top of file）
新增 2 行：
```rust
use openclaw_core::alpha_surface::{AlphaSurface, OIDeltaPanel};
use openclaw_engine::paper_state::{PaperPosition, PaperState};  // PaperPosition is new
```

### Helper 1 — make_self_owned_position
```rust
fn make_self_owned_position(
    symbol: &'static str,
    owner: &str,
    is_long: bool,
    entry: f64,
) -> PaperPosition {
    PaperPosition {
        symbol: symbol.to_string(),
        is_long,
        qty: 1.0,
        entry_price: entry,
        best_price: entry,
        entry_fee: 0.0,
        entry_ts_ms: 0,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: owner.to_string(),
        entry_notional: entry,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}
```
Signature 與 E2 template 完全一致；struct fields 對齊 `PaperPosition`
（containers.rs:18-86）全部 13 個欄位 + 中文 rationale doc。

### Helper 2 — fresh_oi_surface
```rust
fn fresh_oi_surface(symbol: &str) -> &'static AlphaSurface<'static> {
    let panel = Box::leak(Box::new(OIDeltaPanel {
        symbols: vec![symbol.to_string()],
        oi_delta_5m_pct: vec![0.02],
        oi_delta_15m_pct: vec![0.02],
        oi_delta_1h_pct: vec![0.02],
        oi_abs: vec![100.0],
        snapshot_ts_ms: i64::MAX / 4,
        source_tier: "test".to_string(),
    }));
    Box::leak(Box::new(AlphaSurface {
        oi_delta_panel: Some(panel),
        ..AlphaSurface::empty()
    }))
}
```
Signature 與 E2 template 完全一致；與 bb_breakout 模組內 `pub(super)`
`fresh_oi_surface()` 同形態（但後者跨 crate 不可見，故重複實作）。
`AlphaSurface::empty()` 已存在於 alpha_surface.rs:658-672 為 `const fn`。

### Call site 1 — bb_reversion exit (lines 488-494 after edit)
```rust
let pp = make_self_owned_position("ETHUSDT", "bb_reversion", true, 2000.0);
let mut ctx2 = make_ctx("ETHUSDT", 2050.0, 700_000, Some(snap2));
ctx2.position_state = Some(&pp);
let intents = strat.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
assert_eq!(intents.len(), 1, "should exit at mean reversion");
```
`entry=2000.0` 對齊 ctx1 fill price；bb_reversion exit 邏輯只看
`percent_b ∈ [0.2, 0.8]` 不看 entry_price，故任何合法 entry_price 都 OK。

### Call site 2 — bb_breakout valid_squeeze
**關鍵發現超出 E2 描述**：squeeze 登記階段（ctx1）也走 OI gate（mod.rs:479），
不止 entry path。所以 ctx1 + ctx2 都必須帶 OI surface。
```rust
let surface = fresh_oi_surface("BTCUSDT");
// ... ctx1 ...
strat.on_tick(&ctx1, surface);
// ... ctx2 ...
let intents = strat.on_tick(&ctx2, surface);
```

## 治理對照

| 治理項 | 對照 |
|---|---|
| 不擴大 PA/E2 範圍 | 只動 stress_integration.rs；不碰 PaperPosition / OIDeltaPanel / AlphaSurface / bb_reversion / bb_breakout |
| 跨平台兼容 | 純 Rust + `Box::leak` 已用模式（test_oi_surface 同形態），無新硬編碼路徑 |
| 注釋規範 | 新增中文 rationale comments 標記 commit + 日期；無中英對照重複 |
| 硬邊界 | 不碰 max_retries / live_execution / authorization；test fixture only |
| Files < 800 LOC | stress_integration.rs 從 ~700 行 → ~770 行，仍在警告線內 |
| Mac 開發 / Linux runtime | 僅 cargo test 驗證，無 Linux runtime side-effect |

## 不確定之處

1. **超出 E2 描述的發現 — ctx1 也需要 OI surface**：E2 只說 ctx2 fail-closed
   line 535；實際 ctx1 在 squeeze 登記前已 fail-closed，導致 ctx2 找不到
   stored squeeze_detected_ms → 不滿足 `in_squeeze` 條件 → 0 intents。
   修法已涵蓋（ctx1 + ctx2 都用 `surface` 變數）。**請 E2 確認此延伸修改
   是否仍在 task scope 內**——技術上仍是「同一個 fail-closed gate」的
   完整 fix，但 LOC 比 E2 預估多 ~5 行。

2. **companion test `stress_bb_breakout_false_squeeze_no_volume` 結構性
   危險**：它 assert `intents.is_empty()`；當前 EMPTY_ALPHA_SURFACE
   fail-closed 剛好滿足，看似 PASS 實則是 coincidental pass。如果未來
   bb_breakout 邏輯改變，這個 test 可能 silently regress。**建議 E2 評估
   是否一併修**（同類 drift），但本 PR 範圍內未動。

3. **bb_reversion 測試 `entry=2000.0` 是 best-effort 推導**：exit 邏輯
   只看 `percent_b`，entry_price 數值不影響 assert 結果；但若未來 exit
   path 加入 PnL 條件（如 min_profit_threshold），這個值需要重新校準。

## Operator 下一步

1. E2 review：確認 ctx1+ctx2 一起改 OI surface 仍在 E2 RCA scope；確認
   companion test `false_squeeze_no_volume` coincidental pass 是否需另開
   follow-up ticket。
2. E4 regression：跑完整 cargo test 包含 lib + integration，確認 0
   regression（Mac 本地驗 = 全綠）。
3. QA：本變更純 test fixture 修，無 production / live / authorization
   side effect，可走 fast lane。
4. PM：E1→E2→E4 通過後統一 commit + push。

## 驗證證據

### 目標 2 tests
```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo test -p openclaw_engine --release --test stress_integration \
  stress_bb_reversion_extreme_oversold_bounce
# → test stress_bb_reversion_extreme_oversold_bounce ... ok
# → 1 passed; 0 failed

cargo test -p openclaw_engine --release --test stress_integration \
  stress_bb_breakout_valid_squeeze_with_volume
# → test stress_bb_breakout_valid_squeeze_with_volume ... ok
# → 1 passed; 0 failed
```

### Full stress_integration
```
cargo test -p openclaw_engine --release --test stress_integration
# → test result: ok. 35 passed; 0 failed; 0 ignored
```

### Full openclaw_engine cargo test
```
cargo test -p openclaw_engine --release --tests
# → all binaries report ok; lib 2999 passed + integration suites all green
# → 0 failures across the entire test surface
```

## 報告

報告路徑：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--stress_test_invariant_drift_fix.md`
