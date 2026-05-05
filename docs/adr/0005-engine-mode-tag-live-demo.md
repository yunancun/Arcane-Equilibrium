---
status: accepted
date: 2026-04-16
---

# DB engine_mode tag distinguishes 'live' (mainnet) from 'live_demo'

Since 2026-04-16, `TickPipeline::effective_engine_mode()` writes one of `paper / demo / live / live_demo / live_testnet` to all DB tables (`trading.fills`, `trading.intents`, `learning.decision_features`, etc.) based on both `PipelineKind` and `BybitEnvironment`. Earlier code (`pipeline_kind.db_mode()`) tagged LiveDemo fills as `'live'`, so 43k pre-cutoff rows labelled `live` are actually LiveDemo data.

## Consequences

ML / edge filters must use `engine_mode IN ('live','live_demo')` to cover history. The 43k legacy rows were deliberately not backfilled to preserve audit continuity — any tooling that needs a "true mainnet" filter must combine `engine_mode='live'` with a date floor past the cutover.
