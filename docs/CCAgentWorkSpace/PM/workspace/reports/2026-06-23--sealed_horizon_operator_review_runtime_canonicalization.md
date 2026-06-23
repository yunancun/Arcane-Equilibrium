# Sealed Horizon Operator Review Runtime Canonicalization

- Date: 2026-06-23
- Scope: artifact-only alpha/runtime profitability loop
- Boundary: no PG write, no Bybit call, no order/probe authority, no runtime/auth/risk/config mutation, no global Cost Gate lowering, no promotion proof

## Change

`alpha_discovery_throughput_cron.sh` now resolves the latest sealed-horizon learning evidence from the canonical lane path or historical profitability-refresh fallback, then writes a canonical no-authority operator-review preview:

- `cost_gate_learning_lane/sealed_horizon_operator_review_latest.json`
- `cost_gate_learning_lane/sealed_horizon_operator_review_latest.md`

The cron always uses `cost_gate_learning_lane.sealed_horizon_operator_review --decision defer` and intentionally omits `--operator-id` and `--typed-confirm`, so this refresh can only produce a pending/defer review surface. It cannot approve preflight or open bounded demo probe authority.

## Runtime Interface

`profitability_path_scorecard.py` now accepts `--sealed-horizon-operator-review-json` and mirrors the artifact into:

- top-level answers: present, pending, approved, runtime-authority flags
- ranked path evidence: status, decision, approval, blocking gates, authority flags, edge snapshot fields
- artifact summaries

`runtime_runner.py` now summarizes `sealed_horizon_operator_review_latest.json` into the Cost Gate arm and killboard, including source freshness, decision, approval status, side-cell, and authority flags.

## Why It Matters

The previous runtime next move correctly identified `sealed_horizon_probe_preflight.operator_sealed_horizon_review_recorded` as the root blocker, but the canonical lane directory did not contain the operator review artifact. That made the loop depend on an operator or agent remembering a historical `/tmp/openclaw/profitability_refresh/...` path.

This change makes the blocked-signal learning path observable in one canonical runtime surface. It supports the long-term profitability loop by preserving evidence for rejected signals, surfacing the pending review state, and keeping future bounded demo probes tied to explicit side-cell/horizon evidence instead of global Cost Gate lowering.

## Verification

- `python3 -m pytest helper_scripts/cron/tests/test_alpha_discovery_throughput_cron_static.py helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py -q`
- `python3 -m pytest helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_alpha_discovery_throughput.py -q`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_sealed_horizon_operator_review.py -q`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
- `bash -n helper_scripts/cron/alpha_discovery_throughput_cron.sh`
- `git diff --check`
- isolated artifact-only alpha cron smoke under `/tmp/openclaw-codex-alpha-review-smoke`

