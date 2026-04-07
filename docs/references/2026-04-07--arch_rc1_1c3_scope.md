# ARCH-RC1 1C-3 Scoping — Python RiskManager 空殼化

**Date:** 2026-04-07
**Status:** Scoped, not started
**Predecessor:** 1C-2-A/B/C/D/E SHIPPED (Rust ConfigStore + IPC writes + V014 audit + legacy migration)
**Successor:** 1C-4 (Position Reconciler + e2e + E2/E4/QA)

---

## 1. Goal

Reduce `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_manager.py` from **1633 lines → ~200 lines** of pure IPC view client. Eliminate Python as a parallel risk authority. Live surface becomes:

- **Reads**: `get_risk_config` IPC → cached snapshot → typed accessors
- **Writes**: `patch_risk_config` IPC (forwards GUI/API mutations to Rust)
- **No business logic**: every check / decision moves to Rust (already happens — Python copy is mostly dead post-RRC-1)

---

## 2. Current Live Surface (grep-verified, production code only)

`risk_manager.X` instance method calls outside risk_manager.py:

| Method | Caller(s) | Migration target |
|---|---|---|
| `check_order_allowed` | `paper_trading_wiring.py`, `bridge_stats.py` | DEAD — Rust `IntentProcessor::check_order_allowed` is the live path post-RRC-1. Python callers are dead branches kept for graceful degradation. → Delete callers or make them no-ops returning `(True, "")` |
| `check_positions_on_tick` | `paper_trading_wiring.py` | DEAD — Rust `evaluate_positions` is live post-RRC-1 Phase C. → Delete |
| `clear_trailing_stop` | `paper_trading_wiring.py` | DEAD — trailing state lives in Rust `paper_state`. → Delete |
| `config` (property) | `bridge_stats.py`, `routes/risk_routes.py`, etc | **KEEP** as IPC-cached read |
| `get_risk_state_for_persistence` | snapshot/recovery | **KEEP** as IPC-cached read |
| `record_fill_result` | `paper_trading_wiring.py` | DEAD — fills logged in Rust. → Delete |
| `record_market_prices_for_portfolio_risk` | tick path | DEAD — Rust pipeline owns prices. → Delete |
| `_price_tracker` (private attr) | `paper_trading_wiring.py` for ATR | **MIGRATE** — either expose Rust ATR via IPC or keep as in-process utility (separate from RiskManager) |

**Module-global setup** (`main.py` boot):
- `RISK_MANAGER.set_governance_hub(...)` — DEAD (Rust GovernanceCore is live)
- `RISK_MANAGER.set_change_audit_log(...)` — DEAD (V014 engine_events writes from Rust IPC handler)
- `RISK_MANAGER.set_portfolio_risk_control(...)` — DEAD (Rust pipeline owns)

**GUI write surface** (`routes/risk_routes.py`):
- `update_global_config({...})` — must forward to `patch_risk_config` IPC
- `update_category_config(cat, {...})` — forward to `patch_risk_config` IPC  
- `agent_adjust({...})` — forward to `patch_risk_config` IPC (with `source: "agent"`)

---

## 3. Proposed New `RiskViewClient` (≤ 200 lines)

```python
class RiskViewClient:
    """ARCH-RC1 1C-3: thin IPC view of authoritative Rust RiskConfig.
    Read = cached snapshot from get_risk_config (refresh every N seconds or on demand).
    Write = forwards to patch_risk_config IPC; on success refreshes cache."""

    def __init__(self, ipc_client: IpcClient, refresh_interval_s: float = 5.0): ...

    # ── Reads (cached) ──
    @property
    def config(self) -> dict: ...  # full snapshot
    def effective_stop_loss_pct(self, category: str = "linear") -> float: ...
    def effective_max_leverage(self, category: str = "linear") -> float: ...
    def get_risk_state_for_persistence(self) -> dict: ...

    # ── Writes (forward to patch_risk_config) ──
    def update_global_config(self, updates: dict) -> dict: ...
    def update_category_config(self, category: str, updates: dict) -> dict: ...
    def agent_adjust(self, updates: dict) -> dict: ...

    # ── DEPRECATED no-op stubs (return safe defaults, log WARN once) ──
    def check_order_allowed(self, *a, **kw): return (True, "")
    def check_positions_on_tick(self, *a, **kw): return []
    def record_fill_result(self, *a, **kw): pass
    def clear_trailing_stop(self, *a, **kw): pass
    def record_market_prices_for_portfolio_risk(self, *a, **kw): pass
    def set_governance_hub(self, *a): pass
    def set_h0_gate(self, *a): pass
    def set_change_audit_log(self, *a): pass
    def set_portfolio_risk_control(self, *a): pass
```

`PriceHistoryTracker` (~150 lines, lines 125-272 of risk_manager.py) extracted to `program_code/.../app/atr_tracker.py` as standalone utility — it's a pure in-memory ring buffer with no dependency on RiskManager state.

---

## 4. Sub-batch Breakdown

### **1C-3-A** Gap analysis + IPC surface design (~3h, fresh session start)
- Re-confirm 8 live methods + 3 setters by re-running the grep audit
- For each KEEP method, verify current `get_risk_config` payload covers all needed fields; identify any missing IPC reads
- Decide ATR strategy: in-process Python `PriceHistoryTracker` (simpler) vs new IPC `get_atr_pct` endpoint (cleaner but extra Rust work)
- **Output**: short markdown gap report + final method-by-method migration table
- **No code mutation**

### **1C-3-B** Build `RiskViewClient` + `atr_tracker.py` (~4h)
- New file `risk_view_client.py` (~200 lines)
- Extract `PriceHistoryTracker` → `atr_tracker.py` (lift-and-shift, 0 logic change)
- Unit tests: 8-12 tests covering cache refresh, IPC error fail-soft, write forwarding, deprecated stub no-ops
- **Do NOT touch any importer yet** — new module sits unused

### **1C-3-C** Migrate `risk_routes.py` (FastAPI route) (~3h)
- Switch `RISK_MANAGER` global to `RiskViewClient` instance
- Map 3 GUI write endpoints to new `update_*` methods
- E2 verify GUI Risk-tab still shows correct values
- Run `pytest test_risk_manager.py` etc — expect breakage in tests, fix in 1C-3-D

### **1C-3-D** Migrate remaining importers + delete dead code (~5-6h)
- 4 production files: `paper_trading_wiring.py`, `bridge_stats.py`, plus 2 others
- 10 test files: rewrite to mock `RiskViewClient` or hit new IPC contracts
- Delete `risk_manager.py` body (1633 → 50 lines: just a re-export shim of `RiskViewClient as RiskManager` for backwards-compat imports during transition)
- Run full Python test suite — target 0 regressions
- E2 + E4 + QA review

### **1C-3-E** Final cleanup (~2h)
- Remove the `RiskManager` re-export shim
- Update CLAUDE.md / TODO.md / KNOWN_ISSUES (Python `_save_*config` grep should return 0)
- Memory: update `project_arch_rc1_unified_config.md` "Python 命運" section to mark complete

**Total estimated**: 17-20h pure work (likely 3 sessions across 2-3 days with reviews)

---

## 5. Risks

| Risk | Mitigation |
|---|---|
| `paper_trading_wiring.py` actually uses some "DEAD" methods in a code path I missed | 1C-3-A gap analysis reads ALL call sites with full context, not just grep |
| GUI Risk-tab breaks because IPC payload missing a field | 1C-3-A enumerates every property accessed by `risk_routes.py` against current IPC schema |
| Tests rely on in-process `RiskManager` mutation that no longer works after IPC isolation | 1C-3-D rewrites tests to use a fake IPC client + ConfigStore-equivalent in-memory shim |
| `PriceHistoryTracker` ATR is needed by Rust-side computations but currently lives in Python | Verified: Rust has its own ATR via `PriceHistoryTracker` in `tick_pipeline.rs` (RRC-1-C). Python tracker is only used by dead Python code paths. → 1C-3-A should re-verify |

---

## 6. Out of Scope

- New IPC endpoints beyond what 1C-2-C already shipped (unless 1C-3-A finds a hard gap)
- ATR computation in Rust IPC (defer to Phase 2 unless gap analysis demands)
- Removing the `RiskManager` symbol entirely (re-export shim stays through 1C-3-D, deleted in 1C-3-E)

---

## 7. DoD

- [ ] `risk_manager.py` ≤ 200 lines (or replaced by re-export shim)
- [ ] `grep -r "_save_operator_config\|json.dump.*risk" program_code/` returns 0
- [ ] All Python tests pass (currently 3,348+)
- [ ] GUI Risk-tab loads + edits forward through IPC + values reflect Rust state
- [ ] `routes/risk_routes.py` has zero direct field mutation; all writes go through IPC
- [ ] Memory `project_arch_rc1_unified_config.md` "Python 命運" section marked done
