# 1C-3-A Gap Analysis — Python RiskManager Live Surface

**Date:** 2026-04-07
**Status:** Analysis only, no code mutation
**Supersedes §2 of** `2026-04-07--arch_rc1_1c3_scope.md` (caller list was incomplete)

---

## 1. Corrected Live Surface (grep-verified)

### Production callers (non-test)

| File | Line | Expression | Classification |
|---|---|---|---|
| `paper_trading_engine.py` | 1029 | `check_order_allowed` | **DEAD** (Rust IntentProcessor is live post-RRC-1) |
| `paper_trading_engine.py` | 1378/1402/1475/1525 | `record_fill_result` | **DEAD** (Rust paper_state) |
| `paper_trading_engine.py` | 1379/1404/1476/1526 | `clear_trailing_stop` | **DEAD** |
| `paper_trading_engine.py` | 1492 | `record_market_prices_for_portfolio_risk` | **DEAD** |
| `paper_trading_engine.py` | 1493 | `check_positions_on_tick` | **DEAD** (Rust evaluate_positions) |
| `paper_trading_engine.py` | 1554/1566 | `config.max_session_drawdown_pct` | **KEEP** (read, covered by `get_risk_config`) |
| `paper_trading_engine.py` | 1579/1846/1928 | `get_risk_state_for_persistence` | **KEEP** (read) |
| `bridge_core.py` | 294 | `_price_tracker` | **MIGRATE** to standalone `atr_tracker.py` |
| `paper_trading_wiring.py` | 54/392/400 | `set_portfolio_risk_control`/`set_governance_hub`/`set_change_audit_log` | **DEAD** → no-op stubs |

**Correction vs scope doc §2:** the heavy caller is `paper_trading_engine.py`, not `paper_trading_wiring.py`. `bridge_stats.py` does not call risk_manager — original scope doc was wrong on this.

### GUI write surface (`app/risk_routes.py`)

| Line | Expression | Covered by existing IPC? |
|---|---|---|
| 136 | `rm.get_full_config()` | ✅ `get_risk_config` (returns full snapshot) |
| 159/209 | `rm.config.to_dict()` | ✅ `get_risk_config` |
| 160 | `rm.update_global_config(updates)` | ✅ `patch_risk_config` |
| 219/235 | `rm.get_category_config(cat)` | ✅ derive client-side from snapshot |
| 237 | `rm.update_category_config(cat, updates)` | ✅ `patch_risk_config` (nested patch) |
| 250/375 | `rm.get_status()` | ❌ **GAP** — runtime state (cooldown, consec_losses) |
| 320 | `rm.agent_params.to_dict()` | ❌ **GAP** — runtime overlay, not in RiskConfig |
| 321 | `rm.agent_adjust(updates)` | ✅ `patch_risk_config` (with `source: "agent"`) |
| 361 | `rm.reset_cooldown()` | ❌ **GAP** — runtime state mutation |

---

## 2. Identified Gaps

### Gap A — `get_status` / runtime state read
`rm.get_status()` returns cooldown flag, consecutive_losses count, session drawdown, etc. These are **runtime state** not stored in `RiskConfig`. Currently Rust owns the authoritative state in `paper_state` / `risk_governor`.

**Options:**
1. New IPC `get_risk_runtime_status` → returns `{in_cooldown, consec_losses, session_dd_pct, ...}`
2. Client-side shim that returns stubbed values (breaks GUI Risk tab status widget)

**Recommendation:** Option 1 — small (~50 line Rust handler reading from existing state).

### Gap B — `agent_params` overlay
Python's `agent_params` is a separate object from `config` that stores agent-adjusted overrides. Post-RRC-1, `patch_risk_config` with `source: "agent"` is the write path, but there's no "read just the agent-adjusted fields" endpoint.

**Recommendation:** `get_risk_config` response could be extended to include `{config, version, agent_overrides: [field_names]}` — OR accept that GUI shows full effective config without distinguishing agent-set vs operator-set fields. **Decision: defer to 1C-3-C** (check if GUI actually needs this distinction; if not, drop).

### Gap C — `reset_cooldown` mutation
Engine-state mutation (clear consecutive_losses counter). Not a Config patch.

**Recommendation:** New IPC `reset_risk_cooldown` (~30 line Rust handler). Low priority — can stub client-side with warning log initially.

### Gap D — ATR strategy (`_price_tracker`)
`bridge_core.py:294` reads `self._engine.risk_manager._price_tracker` for ATR calculation.

**Verified in scope doc §5:** Rust already has its own `PriceHistoryTracker` in `tick_pipeline.rs` (RRC-1-C). The Python tracker is only consumed by this one bridge line.

**Options:**
1. Extract `PriceHistoryTracker` → `atr_tracker.py` standalone utility, wire `bridge_core.py` to its own instance (lift-and-shift, no IPC)
2. New IPC `get_atr_pct(symbol)` endpoint reading Rust-side tracker

**Recommendation:** Option 1 — simpler, no new Rust surface, ATR is a pure computation. The Python bridge already receives price ticks so it can populate its own tracker.

---

## 3. Final Migration Plan (refined)

### New IPC endpoints needed (1C-3-B Rust side, ~2h)
- `get_risk_runtime_status` — returns `{in_cooldown, consec_losses, session_dd_pct, session_pnl, last_loss_ts_ms}`
- `reset_risk_cooldown` — clears cooldown counter, returns new status

Both are small, additive, don't touch ConfigStore. Can be built alongside 1C-3-B.

### RiskViewClient method map (refined)

```python
class RiskViewClient:
    # Reads (cached snapshot via get_risk_config)
    @property
    def config(self) -> dict: ...
    def get_full_config(self) -> dict: ...   # alias for .config
    def get_category_config(self, cat: str) -> dict: ...
    def get_risk_state_for_persistence(self) -> dict: ...

    # Runtime state (new IPC get_risk_runtime_status)
    def get_status(self) -> dict: ...

    # Writes (patch_risk_config)
    def update_global_config(self, updates: dict) -> dict: ...
    def update_category_config(self, category: str, updates: dict) -> dict: ...
    def agent_adjust(self, updates: dict) -> dict: ...  # source="agent"

    # Runtime mutation (new IPC reset_risk_cooldown)
    def reset_cooldown(self) -> dict: ...

    # Deprecated no-op stubs
    def check_order_allowed(self, *a, **kw): return (True, "")
    def check_positions_on_tick(self, *a, **kw): return []
    def record_fill_result(self, *a, **kw): pass
    def clear_trailing_stop(self, *a, **kw): pass
    def record_market_prices_for_portfolio_risk(self, *a, **kw): pass
    def set_governance_hub(self, *a): pass
    def set_change_audit_log(self, *a): pass
    def set_portfolio_risk_control(self, *a): pass
```

### ATR
`PriceHistoryTracker` → `atr_tracker.py` (lift-and-shift, ~150 lines, 0 logic change). `bridge_core.py` and any other caller instantiates its own.

---

## 4. Updated Effort Estimate

| Sub-batch | Content | Estimate |
|---|---|---|
| 1C-3-A | **THIS doc** | ✅ done |
| 1C-3-B | RiskViewClient + atr_tracker.py + 2 new IPC endpoints (runtime_status, reset_cooldown) | +2h → ~6h |
| 1C-3-C | Migrate risk_routes.py | ~3h |
| 1C-3-D | Migrate paper_trading_engine.py (5 dead call sites) + bridge_core.py + paper_trading_wiring.py setters + 10 test files | ~5-6h |
| 1C-3-E | Cleanup shim + docs | ~2h |

**Total: 18-21h** (close to original estimate; 2 new small IPC endpoints add modest time).

---

## 5. Open Questions for Next Session Start

1. Does GUI Risk tab distinguish "agent-set" vs "operator-set" fields visually? If yes, need `agent_overrides` in IPC payload. If no, drop Gap B.
2. Is `get_status()` called on every GUI render (needs caching) or only on button click? Affects whether runtime_status IPC needs rate-limiting.

Resolve by reading `risk_routes.py` + frontend calls in 1C-3-B kickoff.

---

## 6. Ready for 1C-3-B

Next concrete actions (do not execute this session):
1. Implement Rust `get_risk_runtime_status` + `reset_risk_cooldown` IPC handlers
2. Create `risk_view_client.py` skeleton per §3 method map
3. Extract `atr_tracker.py` from `risk_manager.py` lines 125-272
4. Write 8-12 unit tests
