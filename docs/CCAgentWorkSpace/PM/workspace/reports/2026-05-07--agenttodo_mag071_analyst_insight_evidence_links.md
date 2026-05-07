# AgentTodo MAG-071 AnalystInsight Evidence Links

Date: 2026-05-07
Owner: PM-local execution
Status: DONE

## Scope

Persist AnalystInsight traceability links so an insight can be traced back to
round-trip IDs, strategy metric IDs, execution reports, or prior insight IDs.

## Implementation

- Updated `AgentSpineClient.publish_analyst_insight()` to write:
  - the AnalystInsight object,
  - the parent `analyzed_by` edge when a parent object is present,
  - one unique `evidence_for` edge from each non-empty `evidence_ref` to the
    AnalystInsight.
- Added `_publish_analyst_evidence_edges()` to keep the edge writing bounded
  and de-duplicated.
- `evidence_for` edge details include evidence ref, evidence index, analyst
  tier, insight type, and insight level.
- Added a regression proving round-trip and strategy-metric evidence IDs are
  linked and repeated refs are de-duplicated.

## Verification

- Mac:
  - `python3 -m py_compile ... agent_contracts.py agent_spine_client.py test_agent_spine_client.py`
  - `python3 -m pytest ... test_agent_spine_client.py test_strategist_decision_v2.py test_strategist_v2_replay_not_scanner_sorting.py -q`
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same py_compile
  - same pytest set
  - same diff check

Focused result: 34 Python tests pass.

## Boundary

- No runtime Analyst emission wiring.
- No Strategist/Guardian behavior change.
- No cloud call.
- No runtime submit path.
- No Rust contract change.
- No rebuild, restart, deploy, DB write, live auth, runtime flag, or trading
  authority change.

## Next

M7 continues with MAG-072 Strategist consumes losing/winning patterns through
typed rules.
