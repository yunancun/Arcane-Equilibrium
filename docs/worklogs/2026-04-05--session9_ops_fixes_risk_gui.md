# 2026-04-05 Session 9 — Operational Fixes + Risk GUI Completion

## Summary

Three production bugs fixed (signals overflow, BTC/ETH qty=0, timestamps=0).
Full risk control GUI audit: 1 bug fixed + 7 missing controls added.
QA analysis: multi-position hedging deferred (Bybit net-position default).

---

## Part 1: Three Operational Bugs Fixed

### Bug 1: Signals Flush Overflow (P0)
- **Symptom:** `signals flush failed: too many arguments for query: 87296`
- **Root Cause:** Batch INSERT exceeded PostgreSQL's 65535 parameter limit
- **Fix:** `trading_writer.rs` — all 4 flush functions chunked with safe limits
  - signals: 5000 rows (8 cols × 5000 = 40000 params)
  - intents: 5000 rows (10 cols)
  - fills: 4000 rows (12 cols)
  - positions: 5000 rows (8 cols)
- **Verification:** 45K signals flushed in 2 minutes, zero errors

### Bug 2: BTC/ETH Paper Fill qty=0 (P0)
- **Symptom:** `paper fill skipped: qty=0 after rounding symbol=BTCUSDT`
- **Root Cause:** P1 2% cap → $1000 × 0.02 / $67K = 0.0003 BTC → rounds to 0 (min_qty=0.001)
- **Fix:** `tick_pipeline.rs` — min_qty fallback when qty rounds to 0
  - Guard: min_qty × price ≤ 10% of balance
  - Paper-only (doesn't affect exchange mode)
- **Verification:** BTC 0.001 + ETH 0.01 fills immediately after restart

### Bug 3: last_tick_ms=0 + features updated_ts_ms=0 (P1)
- **Symptom:** Snapshot stats show `last_tick_ms: 0`, features table all zeros
- **Root Cause:** WS parsers (trade, kline, orderbook) used `unwrap_or(0)` for timestamps
- **Fix:** `ws_client.rs` — unified `now_ms()` fallback with `SystemTime::now()`
  - Applied to parse_trade_item, parse_kline_item, parse_orderbook_snapshot
  - Consolidated ticker's inline SystemTime into same helper
- **Verification:** last_tick_ms = real timestamp, features = real timestamps

---

## Part 2: Risk GUI Audit + Completion

### Bug Fix: Trailing Stop Not Saved
- `saveRiskConfig()` had input field `in-trailing` but didn't include it in POST body
- Fixed: now sends `trailing_stop_pct` with null-for-disable semantics

### 7 New GUI Controls Added

| Control | Section | API Field | IPC Push | Default |
|---------|---------|-----------|----------|---------|
| P1 Per-Trade Risk | Position Sizing | p1_risk_pct | → fraction (/100) | 3% |
| Max Single Position | Position Sizing | max_single_position_pct | Python-only | 20% |
| Max Total Exposure | Position Sizing | max_total_exposure_pct | Python-only | 100% |
| Max Same-Direction | Position Sizing | max_same_direction_positions | → Guardian | 3 |
| ATR Multiplier | Stop Manager | atr_multiplier | → Rust | 2.0x |
| Cooldown Trigger Count | Loss Cooldown | consecutive_loss_cooldown_count | Python-only | 3 |
| Cooldown Duration | Loss Cooldown | consecutive_loss_cooldown_minutes | Python-only | 30 min |
| H0 Shadow Mode | H0 Gate | h0_shadow_mode | → Rust | true |

### 3 New GUI Sections
1. **仓位控制与曝险 / Position Sizing & Exposure** — 4 controls
2. **连续亏损保护 / Loss Cooldown Settings** — 2 controls
3. **H0 Gate / H0 入场门控** — 1 toggle with immediate save

### Each Control Includes
- Chinese + English label
- Functional description
- Consequence of too-high / too-low values
- Current value display panel

### Files Modified
- `tab-risk.html` — HTML controls + JS save/load + explainers
- `risk_routes.py` — GlobalConfigUpdate model + IPC push mapping
- `ipc_client.py` — h0_shadow_mode parameter added

---

## Part 3: QA Analysis — Multi-Position Hedging

**Decision: NOT recommended for current phase.**

- Bybit Linear Perpetual default = net position mode
- Hedge mode requires `setPositionMode(mode=3)` + `positionIdx` in orders
- OrderDispatch doesn't support positionIdx yet
- Phase 4+ suggestion: strategy isolation (key by `(symbol, strategy_name)`)

---

## Part 4: E5+E2+PA+FA Review

- **P0: 0** — No blockers
- **P1: 1** — Missing Save button on Position Sizing card → fixed
- **P2: 2** — className CSS bug → fixed, dead `_U` sentinel → removed

---

## Stats

```
Commits this session: TBD (pre-compact)
Rust modified: 3 files (trading_writer.rs, tick_pipeline.rs, ws_client.rs)
Python modified: 2 files (risk_routes.py, ipc_client.py)
HTML modified: 1 file (tab-risk.html)
New tests: 1 (batch limit assertion)
Tests: 376 openclaw_engine + 29 integration = 405 Rust pass

New GUI controls: 8 (7 missing + 1 bug fix)
New GUI sections: 3
API fields added: 5 (to GlobalConfigUpdate)
IPC parameters added: 1 (h0_shadow_mode to Python client)

Engine: running, 3 bugs fixed, data flowing to all 9+ tables
Signals: flush overflow resolved, zero data loss
Fills: BTC/ETH now trading via min_qty fallback
Timestamps: all parsers use SystemTime fallback
```

## Pending / Next Steps
- Phase 4 (W13-15): Claude Teacher + LinUCB + News + DL-3
- Data accumulation: fills growing, need 30K+ for meaningful ML training
- EXT-1 implementation: exchange-as-truth mode (10 tasks pending)
- Paper/Demo logic: being modified in parallel session
