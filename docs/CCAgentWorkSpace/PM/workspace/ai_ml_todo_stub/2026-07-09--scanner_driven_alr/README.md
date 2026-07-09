# Scanner-Driven ALR AI/ML Todo Stub

Date: 2026-07-09
Owner: PM
Status: `ACTIVE_STUB`
Maturity label: `ALR_P0_SOURCE_ONLY_TARGET_INTAKE`
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

This directory is the durable AI/ML work stub for scanner-driven active learning.
It is intentionally separate from root `TODO.md`: this stub is a PM-owned AI/ML
roadmap queue and is not root TODO authority unless PM explicitly imports a row.

## Scope

This stub authorizes source-only Codex engineering for the AI/ML ALR roadmap.
It does not authorize runtime SSH, service restart/rebuild, PG read/write, IPC
listener/writer, Bybit REST/WS public/private calls, Decision Lease acquisition,
adapter/writer enablement, order/probe/cancel/modify, `_latest` overwrite, Cost
Gate change, proof/promotion, live/mainnet, cron/daemon/launchd/systemd/sidecar,
or scheduler changes.

Hard stop: ALR P0/P1 means source-only, offline, local-artifact engineering. It
is not trading P0/P1, Demo final-window work, runtime prep, bounded probe work,
or order-capable work. It does not inherit any current root `TODO.md` candidate,
standing Demo authorization, prior no-order approval, or previous Bybit public
GET approval.

The loop in `startup_prompt.md` is a foreground Codex source-development loop.
It may repeat local source/test/report/commit iterations inside a session. It is
not a runtime loop, background service, hidden scheduler, scanner cadence change,
or autonomous trading actor.

## Source Reports

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-09--scanner_driven_autonomous_learning_runtime_engineering_plan.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp5_completion_assessment.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_autonomous_completion_loop_design.md`

## Files

| File | Purpose |
|---|---|
| `manifest.json` | Machine-readable stub metadata and hard-boundary summary. |
| `queue.md` | Ordered AI/ML ALR work queue with acceptance and next actions. |
| `boundaries.md` | Proof, scanner, model, LLM, runtime, and file-scope boundaries. |
| `loop_contract.md` | Foreground Codex loop states, stop logic, dispatch, and static checks. |
| `retention_guardian_contract.md` | P0 dry-run cleanup and protected-artifact contract. |
| `startup_prompt.md` | Copy-paste prompt for a new Codex session. |

## Non-Negotiable Interpretation

Scanner artifacts are intake evidence only. `OpportunityCandidate`, final score,
registry rows, decay events, no-order artifacts, and no-fill artifacts are not
orders, risk verdicts, trade permission, profit proof, or runtime authority.

Do not call Bybit REST or WS, public or private. Do not install, start, connect
to, or use official exchange MCP tools; MCP material is reference/taxonomy only
unless a future ADR/AMD plus exact `PM -> E3 -> BB` scope authorizes it.

P0 target scoring optimizes `expected_value_of_information`, not expected trade
PnL. Without candidate-matched proof packets and reward ledger evidence, any
after-cost field is `hypothesis_prior` or null, with `edge_claim_allowed=false`.

`EMIT_ARTIFACT` means a source artifact was emitted. It does not mean learning
closure, model maturity, proof, promotion, serving authority, runtime authority,
or trading authority.
