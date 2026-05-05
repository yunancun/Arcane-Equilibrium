# REF-21 Full-Chain Replay Scope Correction

**Date:** 2026-05-06  
**Role:** PM  
**Status:** Design baseline landed, no runtime change

## Context

Operator clarified that current Replay is still too complex and too narrow. The
real requirement is not single-symbol strategy smoke. It is a fast equivalent of
7 days of full system data accumulation after strategy or program edits.

Required chain:

```text
scanner -> active symbol universe -> strategies -> intent/risk -> execution simulation -> exits -> fee-net edge report
```

## PM Judgment

The concern is valid. REF-20 Quick Replay can shorten narrow parameter smoke
tests, but it does not answer scanner / universe / lifecycle / portfolio edge
questions. Treating it as "7d equivalent" would be misleading.

PM created REF-21 as the corrected scope:

- default Replay becomes one-click 7D full-chain replay,
- current single-symbol workflow remains Advanced / smoke,
- S2 public data is the immediate zero-cost path,
- S1 recorder becomes the fidelity upgrade path,
- MLDE / DreamEngine consume verified replay evidence but remain advisory
  components, not replay-only engines.

## Files

- `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md`
- `docs/execution_plan/2026-05-XX--ref21_s1_recorder_spec_placeholder.md`
- `docs/execution_plan/README.md`
- `docs/README.md`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`

## Next Implementation Chain

Recommended chain for code work:

```text
PM -> PA -> QC -> MIT -> E1 -> E2 -> E4 -> QA -> PM
```

First implementation wave should be R1:

- full-chain manifest mode,
- multi-symbol S2 dataset builder,
- scanner input snapshots,
- bounded API route and tests.
