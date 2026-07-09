# Operator Summary: Scanner-Driven ALR Statistical Selector Baseline

Date: 2026-07-09
Status: `DONE`
Boundary: `SOURCE_ONLY_OFFLINE_P0_P1`

Completed `P1-AIML-ALR-STAT-SELECTOR-BASELINE`.

New:

- `program_code/ml_training/alr_stat_selector_baseline.py`
- `program_code/ml_training/tests/test_alr_stat_selector_baseline.py`

The selector now provides:

- `alr_stat_selector_snapshot_v1` input contract
- `alr_stat_selector_baseline_v1` output contract
- explicit `--snapshot` and `--out` invocation only
- frozen-universe, pre-registered split, controls, negative cells, regime
  labels, walk-forward/OOS, and retained-non-selected requirements
- raw candidate/control OOS statistical scoring with shrinkage, uncertainty,
  and conservative lower confidence bound
- deterministic ranking and tie-breaks
- hash-bound input/output
- `_latest` rejection for paths and source/path/ref/alias carriers
- authority contamination blocking
- proof-gated `STOP_NO_EDGE`

Role chain:

- QC audit: done with source-only concerns carried into design
- MIT audit: done with manifest/fail-closed requirements carried into design
- AI-E audit: done with no LLM/RL/serving/runtime authority
- PA design: pass with source-only helper scope
- E1 implementation and E2 rework
- E2 final gate: PASS
- E4 final gate: PASS
- QA final gate: ACCEPT

Verification:

- focused pytest: `20 passed`
- adjacent selector/arbiter/controller pytest: `95 passed`
- ALR helper regression pytest: `159 passed`
- py_compile: PASS
- git diff check: PASS

Non-blocking concerns carried forward:

- `proof_exclusion` exact subfield schema is still broad.
- `_latest` rejection is source/path/ref/alias-carrier based, not every generic
  carrier shape.

Boundary unchanged: no runtime, PG, IPC, Bybit, official MCP, Decision Lease,
order/probe, Cost Gate, `_latest`, serving, proof/promotion, delete/apply,
cron/daemon/scheduler, service/env, or live/mainnet authority.

Next source-only step: P2 readiness audit packet. Runtime/exchange/proof/order
work remains blocked unless future exact-scope PM -> E3 -> BB authorization is
granted.
