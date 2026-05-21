# ADR 0025: Track-Based Strategy Attribution

Date: 2026-05-20 (v3 — 2nd reviewer audit corrections incorporated)
Status: Accepted-pending-commit

## Context

AMD-2026-05-20-01 introduced dual-track architecture. ADR-0025 v1 (morning)
used fabricated table names; v2 (afternoon, 1st reviewer audit) corrected
to 9 real tables. v3 (later afternoon, 2nd reviewer audit) further expands
to 12 real tables after deeper inspection.

2nd reviewer audit 2026-05-20 critique #1: v2's "9 real tables" missed 3
critical attribution surfaces:

- `trading.signals` — `Strategy.on_tick` emits signals that may not become
  intents (gated by Strategist / Guardian). Without `track` on signals,
  per-track signal-rate attribution is impossible.
- `trading.decision_outcomes` — ML label table (1m/5m/1h/4h/24h forward
  returns); Track B hypothesis evaluation requires per-track labels.
- `trading.risk_verdicts` — Guardian APPROVED/REJECTED/MODIFIED rows;
  without `track`, per-track Guardian veto-rate attribution impossible.

These three tables are **not deferrable**. Deferred (joinable via
`agent.decision_objects`): `agent.decision_edges`,
`agent.decision_state_changes`, `agent.execution_idempotency_keys`.

## Decision

Introduce `strategy_track` PG enum + Rust `Track` enum as first-class
attribution dimension. **12 existing tables + 2 new tables receive `track`
column**.

```sql
CREATE TYPE strategy_track AS ENUM (
    'direct_exploit',  -- Track A: hand-coded Rust, cash flow priority
    'asds_factory',    -- Track B: schema-only in N+1-N+3 (hypothesis ledger)
    'baseline'         -- Track C: frozen textbook, A/B baseline
);
```

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Track {
    #[serde(rename = "direct_exploit")]  DirectExploit,
    #[serde(rename = "asds_factory")]    AsdsFactory,
    #[serde(rename = "baseline")]        Baseline,
}
```

### V101 Attribution Targets (verified via grep `sql/migrations/V*.sql`)

| # | Table | Schema | Real Time Column | Primary Key | Backfill |
|---|---|---|---|---|---|
| 1 | `trading.fills` | trading | `ts TIMESTAMPTZ` | `(fill_id, ts)` | `baseline` |
| 2 | `trading.intents` | trading | `ts TIMESTAMPTZ` | `(intent_id, ts)` | `baseline` |
| 3 | `trading.orders` | trading | `ts TIMESTAMPTZ` | `(order_id, ts)` | `baseline` |
| 4 | `trading.signals` | trading | `ts TIMESTAMPTZ` | `(signal_id, ts)` | `baseline` (NEW v3) |
| 5 | `trading.decision_outcomes` | trading | (none — context_id PK) | `context_id` | `baseline` (NEW v3) |
| 6 | `trading.risk_verdicts` | trading | `ts TIMESTAMPTZ` | `(verdict_id, ts)` | `baseline` (NEW v3) |
| 7 | `trading.position_snapshots` | trading | `ts TIMESTAMPTZ` | `(symbol, side, ts)` | `baseline` |
| 8 | `learning.lease_transitions` | learning | `ts_ms BIGINT` + `created_at TIMESTAMPTZ` | — | `baseline` |
| 9 | `learning.strategy_trial_ledger` | learning | (table-specific) | — | `baseline` |
| 10 | `learning.cost_edge_advisor_log` | learning | (table-specific) | — | `baseline` |
| 11 | `agent.ai_invocations` | agent | (table-specific) | — | `baseline` |
| 12 | `agent.decision_objects` | agent | `created_at TIMESTAMPTZ` | `(object_id)` | `baseline` |
| NEW-1 | `learning.hypotheses` | learning | `created_at TIMESTAMPTZ` | `hypothesis_id UUID` | (CHECK = `asds_factory`) |
| NEW-2 | `learning.hypothesis_preregistration` | learning | `registered_at TIMESTAMPTZ` | `preregistration_id UUID` | (CHECK = `direct_exploit`) |

**Time column heterogeneity**: 3 patterns coexist:
- `ts TIMESTAMPTZ` (all `trading.*` except decision_outcomes)
- `created_at TIMESTAMPTZ` (`agent.decision_objects`,
  `learning.hypotheses`)
- `ts_ms BIGINT` epoch ms (`learning.lease_transitions`)

V102 indexes MUST match per-table real time column. No assumption of
uniform `fill_ts` / `emitted_at` etc. (those don't exist).

**Computed metric note**: `trading.fills` has NO `net_edge_bps` column.
v4.2 P&L views compute it as:

```sql
((realized_pnl - fee) / NULLIF(qty * price, 0)) * 10000 AS net_edge_bps
```

### Backfill Strategy

Backfill all existing rows to `baseline` (current 5 textbook strategies
are the only active strategies pre-v4.2). Specific backfill predicate
options:

- `WHERE track IS NULL` — universal, idempotent
- `WHERE strategy_name IN ('grid_trading', 'bb_breakout', 'bb_reversion',
  'ma_crossover', 'funding_arb')` — explicit, defensive for tables with
  `strategy_name`

`trading.decision_outcomes` has no `strategy_name` direct column; backfill
joins via `context_id` → `decision_context_snapshots` → strategy. PA
dispatch confirms join validity before V101 deploy.

### Guardian Check 6 Status

Guardian per-track envelope check **is NOT yet implemented in N+1-N+2**.
v4.2 §1.10 governance hygiene: spec text "待 V102 + risk_config_*.toml
[track_budgets] schema land 後實作". Until then, envelope enforcement is
manual operator review via SQL views.

### Cross-Track Interactions (unchanged from v2)

Per AMD-2026-05-20-01 §6 + AMD-2026-05-20-03: Track A and Track B share
infrastructure but never modify each other's strategies at runtime. LLM
never writes Rust. Conflict resolution: Direct Exploit priority; Track B
intent marked `BLOCKED_CROSSTRACK`.

## Consequences

- **3 additional tables** in V101 scope (`signals`, `decision_outcomes`,
  `risk_verdicts`).
- **Time column heterogeneity** forces per-table-tailored V102 indexes;
  no generic templates.
- **`trading.decision_outcomes` backfill** requires `context_id` JOIN to
  resolve strategy; PA dispatch verifies join.
- **V101 IMPL LOC ~ +150** (3 new tables × ~50 LOC backfill + index).
- **Guardian check 6** stays "TBD" through N+1-N+2; SQL-view-based manual
  review is interim solution.
- All other consequences from v2 remain.

## Implementation Anchors

- Rust enum: `openclaw_types/src/track.rs` (new)
- Migration: V101 + V102 v3 spec — see `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`
- Guardian check 6: deferred; spec language updated.
- GUI tabs (progressive): N+1 SQL views + REST endpoint only; N+2
  summary tab after 14d data.

## Reviewer Audit Trail

- v1 (morning): fabricated table names; reviewer audit #1 caught.
- v2 (afternoon, 1st audit fix): 9 real tables verified by grep.
- **v3 (later afternoon, 2nd audit fix)**: 3 additional tables
  (`signals`, `decision_outcomes`, `risk_verdicts`) added; real time
  columns verified per-table; computed metric `net_edge_bps` clarified
  as view-only.
- 2nd reviewer audit critique #1 + #2 accepted in full.
