# Bounded Demo Probe Soak Enablement

## Status

`DONE_WITH_CONCERNS`: Demo-only bounded probe soak is enabled and verified, but no candidate-matched order/fill evidence has appeared yet.

## Source Changes

- `26b150e8` wires admitted bounded Demo probe drafts into the order dispatch channel after the admission ledger row is flushed.
- `d09bd5cd` teaches the readiness scanner to recognize the final-window writer dispatch path.
- `628ad3e7` forwards `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` through `restart_all.sh`.
- `bb15288b` lets plan-inclusion consume current-candidate public quote construction artifacts.

Focused verification passed locally and on `trade-core`: Rust writer/dispatch tests, readiness scanner tests, restart static tests, plan-inclusion tests, `py_compile`, `bash -n`, and `git diff --check` where applicable.

## Runtime Materialization

- Runtime source: `bb15288bfbae91ed06b84a0d3f62dcb1b210063c`, clean.
- Engine PID: `4136267`.
- Binary sha: `d7c80ec9367e41d1b4309495b4498a9cf8e43ff3011160dca5dbfe17d201cecf`; `/proc/$PID/exe` matches disk.
- Env: `OPENCLAW_ALLOW_MAINNET=0`, `OPENCLAW_ENABLE_PAPER=0`, `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1`, `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1`.
- Plan override: `/tmp/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json`, sha `91812ebc4b0eda5874d001a3a3376689c1e07fb561a83bf32c9c3ff9cfb1592a`.
- Plan-inclusion review: `/tmp/openclaw/bounded_demo_probe_plan_inclusion_for_soak_20260627T201741Z/plan_inclusion_review.json`, sha `9527fb8efa89949041565c7e0301393d9f37cbd82981a19a6df353d7763a6dbc`.
- Materialization manifest: `/tmp/openclaw/bounded_demo_probe_soak_materialization_20260627T201940Z.json`, sha `ae407136a4fd39ecae5700eb644115482b5d38f9644840d4cd8c3cead17b7723`.
- Post-restart verification: `/tmp/openclaw/bounded_demo_probe_soak_post_restart_verification_20260627T202221Z.json`, sha `624caaec66b6df7756b51600cc00963d5874fe176419ab9a9309bf217fc982ef`.
- Session state: `/tmp/openclaw/session_loop_state_20260627T193909Z_fast_demo_probe_runner/session_loop_state_final_v660.json`, sha `06881f0151f0c67364398744206da7518444307c1101f9822da2f26b9d6c7196`, status `DONE_WITH_CONCERNS`.

## Current Evidence

The plan-inclusion gate passed all checks. Adapter-off dry-run remains `ADAPTER_DISABLED`; adapter-on hypothetical is `ADMIT_DEMO_LEARNING_PROBE`. The running plan carries bounded auth `standing-demo-9bd754050eb38514`, candidate `grid_trading|AVAXUSDT|Sell`, max 2 probe orders, GUI/Rust RiskConfig cap lineage, and `main_cost_gate_adjustment=NONE`.

The post-restart soak observation is still waiting: `total_intents=0`, `total_fills=0`, ledger sha unchanged, and no order/fill/fee/slippage/reconstruction/after-cost review exists yet.

## Monitoring

Created heartbeat automation `openclaw-bounded-demo-probe-soak-monitor`, every 90 minutes for about 72 hours. It must refresh auth/plan only through standing auth -> bounded authorization -> plan-inclusion gates, or collect candidate-matched fill evidence if it appears.

## Boundaries

Demo only. No live/mainnet, no global Cost Gate lowering, no Guardian/risk/Decision Lease/Rust authority bypass, no L2 direct authority, and no profit proof until candidate-matched fills with fee/slippage/reconstruction and after-cost review exist.
