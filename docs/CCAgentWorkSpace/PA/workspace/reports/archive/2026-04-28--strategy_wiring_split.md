# STRATEGY-WIRING-SPLIT P2 — PA+E1 Report

**Date**: 2026-04-28
**Triangle合一**: PA design + E1 impl + sanity test
**Base HEAD**: `54b9add` (origin/main)
**Scope**: `strategy_wiring.py` only — 0 production behavior change

---

## 1. Outcome

**LOC**: `strategy_wiring.py` 1060 → **784** (≤800 target hit, **-276 LOC / -26%**)
**New siblings**: 2 (`strategy_wiring_h_state.py` 133 LOC, `strategy_wiring_scanner.py` 338 LOC)
**Total**: 1060 → 1255 (+195 net for sibling boilerplate / docstrings, 0 logic delta)
**CLAUDE.md §九 rows updated**: 2 (`_H_STATE_INVALIDATOR` row 467 + 新 row `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER`)
**Mac pytest**: 143/143 PASS (0.45s) — 6 critical wiring suites all green
**Smoke**: 25 module-level singletons all reachable as `app.strategy_wiring.<name>` attributes (verified via direct attribute lookup)

---

## 2. Investigation findings

### Functional clusters identified (1060 LOC)
1. Header / module note / shared instance init (KLINE / IND / SIG / ORCH / TRADE_ATTR) — ~110 LOC, **kept** (foundational, all later blocks depend on)
2. Scout + MessageBus + Conductor + 5-Agent (Strategist / Guardian / Analyst / Executor) — ~440 LOC, **kept** (init order rigid, audit_callback wiring + ExecutorConfigCache + cognitive_modulator + LOSSES-WIRING all interleaved)
3. **H State Invalidator (G3-08 Phase 1C)** — ~80 LOC, **EXTRACTED** to `strategy_wiring_h_state.py`
4. PaperLiveGate / AI Consultation / Telegram / Grafana / DemoSync — ~60 LOC, kept (small, tightly coupled to surrounding wiring)
5. **Market Scanner + AutoDeployer + ScoutWorker + Auto-Observation + scout_routes wire** — ~225 LOC, **EXTRACTED** to `strategy_wiring_scanner.py`
6. Auto-start market feed constant + APR01-P0-1 TruthSourceRegistry inject — ~40 LOC, kept (small leaf)
7. Router decl + validators + envelope + `__all__` — ~85 LOC, kept (interface contract)

### Caller surface (broad — 11 modules import singletons via 4 patterns)
- `from .strategy_wiring import (X, Y, Z)` — `strategy_read_routes` / `strategy_write_routes` / `strategy_ai_routes` / `phase2_strategy_routes` / `backtest_routes`
- `from .strategy_wiring import *` — `phase2_strategy_routes` (line 17)
- `from .strategy_wiring import X` (lazy inside fn) — `ai_service` (4 sites)
- `sys.modules.get("app.strategy_wiring")` + `getattr(_sw, "STRATEGIST_AGENT", None)` — `h_state_collectors` (5 agent lookups) + `h_state_query_handler` (cost_tracker lookup) + 2 test modules patch via `sys.modules + setattr`

**Critical contract**: Singletons MUST appear as `app.strategy_wiring.<NAME>` module attributes. Re-import / function-return-bind preserves this.

---

## 3. Design decisions

### Sibling 1: `strategy_wiring_h_state.py` (133 LOC, leaf cluster)
- Top-level executable code (mirrors original): env-gated `init_h_state_invalidator()` call, fail-closed default `None`
- Exposes `_H_STATE_INVALIDATOR` symbol; strategy_wiring.py does `from .strategy_wiring_h_state import _H_STATE_INVALIDATOR` at original sequence position (after Batch 11 ExecutorAgent, before Batch 12 PaperLiveGate)
- Why top-level (not function): no dependency injection needed — only reads `os.environ["OPENCLAW_H_STATE_GATEWAY"]` + imports `h_state_invalidator` module

### Sibling 2: `strategy_wiring_scanner.py` (338 LOC, leaf cluster)
- **Function-based** (`wire_market_scanner_and_workers(deps)` returns `ScannerWiringResult` dataclass) — chosen over top-level because the cluster needs ORCHESTRATOR / KLINE_MANAGER / PAPER_ENGINE / SCOUT_AGENT / MESSAGE_BUS as inputs (created in strategy_wiring.py earlier). Function injection avoids circular import.
- 4 sub-blocks bundled (all leaf, all fail-open): MarketScanner+AutoDeployer build / ScoutWorker 30-min loop / scout_routes wire / Auto-Observation Writer (DEAD-PY-2 stub)
- strategy_wiring.py binds returned singletons to module attribute (`MARKET_SCANNER = _scanner_result.market_scanner` etc.) preserving downstream `from .strategy_wiring import MARKET_SCANNER` and `getattr(_sw, "MARKET_SCANNER", None)` patterns

### Why these 2 (not 4-5 siblings)?
- Bigger 5-Agent block (~440 LOC) has tightly interleaved init sequence — splitting risks LOSSES-WIRING / cognitive_modulator / audit_callback / ExecutorConfigCache wiring chain breakage. Out of P2 scope (boundary: "嚴格 strategy_wiring.py only — 不擴 scope")
- 2 chosen siblings hit ≤800 target with minimal risk; 1 sibling alone would not (1060 - 80 = 980 still > 800)

---

## 4. Preserved invariants

- **Init order**: H-state singleton imported at original line 553 sequence (between Batch 11 / Batch 12); scanner cluster wired at original line 706 sequence (after PaperLiveGate / Telegram / Grafana, before APR01 TruthSourceRegistry)
- **W1 cognitive ticking** (line 405-415): untouched, still calls `STRATEGIST_AGENT.set_cognitive_modulator()` after Batch 7
- **G8-01-FUP-LOSSES-WIRING** (line 447-490): Analyst → Strategist callback lambda (line 469-471) untouched
- **ExecutorConfigCache + shadow_mode_provider injection** (line 521-538): untouched
- **5 audit_callback wires** (Scout/Strategist/Guardian/Analyst/Executor): untouched
- **TruthSourceRegistry inject** (~948-973): untouched
- **__all__ + router**: untouched
- **DEAD-PY-2 paths**: PIPELINE_BRIDGE = None, Auto-observation no-op pass, DEMO_CONNECTOR = None — all preserved in extracted siblings

## 5. Verification

```
PYTHONPATH=. ./venvs/mac_dev/bin/pytest \
  test_strategist_audit_wiring.py \
  test_h_state_query_handler.py \
  test_g8_01_fup_losses_wiring.py \
  test_strategist_cognitive_integration.py \
  test_executor_shadow_toggle_api.py \
  test_strategist_promote_api.py \
  -q
→ 143 passed in 0.45s
```

Smoke: 25 module-attr lookups via `app.strategy_wiring.<NAME>` all return live singleton instances (or `None` for DEFAULT-OFF env-gated `_H_STATE_INVALIDATOR`).

## 6. Risks + follow-ups

- **None blocking**. Scanner cluster fail-open behavior preserved exactly (each sub-block try/except → singleton=None on any exception, main pipeline continues).
- **Init order subtle dependency**: `wire_market_scanner_and_workers()` call MUST happen after PAPER_ENGINE / ORCHESTRATOR / SCOUT_AGENT / MESSAGE_BUS init AND before `auto_start_market_feed` block — verified by line position (replaces original sequence).
- **Future split candidates** (out of scope, deferred): 5-Agent block (~440 LOC) could go to `strategy_wiring_agents.py` if strategy_wiring.py grows again; would need careful interleaved-callback handling.

## 7. Files changed

```
M  CLAUDE.md                                         # §九 row 467 update + 1 new row
M  app/strategy_wiring.py                            # 1060 → 784 LOC
A  app/strategy_wiring_h_state.py                    # +133 LOC (new sibling)
A  app/strategy_wiring_scanner.py                    # +338 LOC (new sibling)
```

## 8. Singleton table delta (CLAUDE.md §九)

- `_H_STATE_INVALIDATOR` row: wire site updated `strategy_wiring.py:535` → `strategy_wiring_h_state.py` + re-import note
- New row: `MARKET_SCANNER / AUTO_DEPLOYER / _SCOUT_WORKER` → `strategy_wiring_scanner.py` (was previously not登記 — covered by generic "12+ singletons" line; now explicit per Wave E cost_edge_advisor_boot precedent)

---

**PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategy_wiring_split.md**
