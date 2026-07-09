# P0-AIML-ALR-BOUNDARY-PACKET

## Metadata

| Field | Value |
|---|---|
| Work item | `P0-AIML-ALR-BOUNDARY-PACKET` |
| Status | `BOUNDARY_VALIDATED_WITH_CONCERNS` |
| Date | `2026-07-09` |
| Owner chain | `PM -> CC -> FA -> PA -> PM` |
| Boundary label | `SOURCE_ONLY_OFFLINE_P0_P1` |
| Output path | `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/boundary_packet.md` |
| Repo head observed | `a923893ef04629ed50f41352285c7347327e9195` |
| Docs-only flag | `true` |

## Authority Statement

This packet is docs/state/report integration only. It is `NOT_APPLIED` and is
not an accepted ADR, AMD, TODO mutation, runtime authorization, proof artifact,
promotion artifact, trading permission, or root-TODO import.

This packet does not grant authority to edit `docs/adr/`, `docs/amd/`, root
`TODO.md`, migrations, runtime config, code outside the selected ALR scope, or
any runtime/exchange surface. Any future move from this packet into ADR, AMD,
root TODO, migration, runtime, or exchange scope requires a new explicit PM
scope and the role chain required by the repo rules.

## Boundary Label

`SOURCE_ONLY_OFFLINE_P0_P1` means foreground Codex source-development only:
local source/docs/tests/reports/artifacts that run once, exit, and grant no
runtime or trading authority.

This ALR P0/P1 lane is not trading P0/P1, not Demo final-window work, not bounded
probe work, not an order-capable path, and not a background runtime actor.

## Acceptance Boundary

The selected row is accepted only when this boundary packet exists, preserves
the hard denials below, and records the ALR work item/effect/state artifacts.

Acceptance is limited to this target packet plus the PM-owned ALR stub status
update and PM/Operator reports. It does not accept or apply any ADR/AMD text,
does not import this stub into root `TODO.md`, and does not authorize source
code implementation beyond the next explicitly selected queue row.

## Scanner Boundary

Scanner artifacts are intake evidence only. `OpportunityCandidate`,
`final_score`, registry rows, decay events, scanner snapshots, no-order
artifacts, no-fill artifacts, touchability packets, preflight packets, cleanup
fills, and unattributed fills may rank learning targets or identify proof gaps.

They must not populate reward, proof, edge, promotion, RiskConfig, Decision
Lease, order-shape admission, trade permission, runtime authority, or profit
proof fields.

The fixed rule is:

```text
scanner = evidence
scanner != authority
scanner != proof
scanner != reward
scanner != order permission
```

## ADR-0035 Separation

ALR P0 is not an ADR-0035 streaming online update. It is not ModelClient
activation, model hot-path mutation, RL policy writing, online learner writes,
model reload, serving promotion, or autonomous trading maturity.

ALR P0 may define deterministic or traditional statistical offline scoring over
sealed inputs. It may not mutate model weights, runtime parameters, exchange
state, proof state, or serving authority.

## P0 Source-Only Denials

The following surfaces are denied for this packet and for ALR P0/P1 unless a
future exact PM scope changes them:

| Surface | Status |
|---|---|
| `docs/adr/` mainline ADR write | denied |
| `docs/amd/` or governance mainline AMD write | denied |
| root `TODO.md` import or mutation | denied |
| migrations, DDL, Timescale policy, PG read/write | denied |
| runtime SSH, restart, rebuild, deploy, service/env mutation | denied |
| cron, daemon, launchd, systemd, sidecar, scheduler, hidden background loop | denied |
| IPC listener/writer, engine socket, Decision Lease acquisition | denied |
| adapter/writer enablement, order-shape admission | denied |
| Bybit REST/WS public or private contact | denied |
| official exchange MCP install, start, connect, credential read, private read, or order path | denied |
| order, probe, cancel, modify, cancel-all, fee-rate private read, `/v5/order` | denied |
| Cost Gate change, proof promotion, model serving promotion | denied |
| `_latest` overwrite, symlink promotion, model reload | denied |
| physical delete, move, rename, chmod, prune/apply execution | denied |
| live, mainnet, tiny-live, capital/VIP/MM-program decisions | denied |

If implementation, review, or operator wording appears to need one of these
surfaces, the loop must stop before tool use with `BLOCKED_BOUNDARY` or the more
specific stop state listed below.

## Proof Taxonomy

| Class | May rank target | May affect reward/edge | Boundary |
|---|---:|---:|---|
| `scanner_intake` | yes | no | Opportunity/ranking/decay evidence only. |
| `no_order_gate` | yes | no | BBO, released Decision Lease windows, no-order/no-fill diagnostics, and gate-readiness evidence only. |
| `execution_touchability` | yes | no | Touchability/preflight/placement diagnostics only. |
| `candidate_matched_outcome` | yes | yes | Requires candidate-matched orders/fills, actual fees/slippage/funding where applicable, reconstruction, controls, proof-exclusion pass, and source lineage. |
| `promotion_proof` | yes | yes | Requires accepted ProofPacket, RewardLedger, controls, repeat or OOS evidence, and effect review. |

Cleanup fills, unattributed fills, no-fill rows, released no-order leases,
stale `_latest` artifacts, scanner scores, and artifact counts are never reward,
edge, proof, promotion, or runtime authorization.

## P0 Scoring Semantics

P0 target scoring optimizes `expected_value_of_information`, not expected trade
PnL. The scoring question is which source-only learning target is worth
investigating next under bounded evidence value and proof gaps.

If candidate-matched ProofPacket and RewardLedger evidence is missing:

- after-cost EV fields must be `null` or explicitly labeled
  `hypothesis_prior`;
- `edge_claim_allowed=false`;
- proof status must be `HYPOTHESIS_ONLY` or `DEFER_EVIDENCE`;
- `STOP_NO_EDGE` is not allowed.

`STOP_NO_EDGE` is allowed only after proof-ready candidate-matched outcomes plus
controls and repeat/OOS evidence show a non-positive conservative after-cost
lower confidence bound.

## Model Boundary

ALR P0/P1 grants no model training, model serving, online learning, proof
authority, runtime authority, trading authority, or promotion authority.

Any ranking that affects `next_action` must be deterministic or traditional
statistical code over replayable inputs. LLM, L1, L2, DreamEngine, and Teacher
outputs may only appear under `advisory_refs` with `not_authority=true`.

Those advisory refs cannot set `target_score`, `proof_status`, `reward_value`,
`maturity_status`, `promotion_status`, runtime decisions, trading decisions, or
Cost Gate decisions.

## RetentionGuardian P0 Boundary

RetentionGuardian P0 is a dry-run manifest only. It may classify and propose,
but it cannot delete, move, rename, chmod, update symlinks, overwrite `_latest`,
write PG, change Timescale policy, call prune/apply scripts, or perform
runtime/network/Bybit/IPC/cron/daemon actions.

The following are protected by default:

- proof, RewardLedger, order, fill, fee, slippage, reconstruction, audit, and
  lineage artifacts;
- dispute, unknown-reference, negative-example, no-order, no-fill, cleanup,
  unattributed, proof-excluded, failed-gate, blocked-gate, and `ROTATED`
  artifacts;
- report-linked, TODO-linked, ADR/AMD-linked, OOS/control/repeat, source hash,
  and provenance artifacts.

Unknown refs fail closed to `STOP_RETENTION_RISK`.

## Root TODO Location Decision

This queue remains under:

`docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/`

Root `TODO.md` remains the active blocker truth for the project. This ALR stub is
PM-owned AI/ML source-development state and is not root TODO authority unless PM
explicitly imports a row in a future scoped change after reading the TODO
maintenance standard.

The current row does not import root `TODO.md` because it is a boundary packet,
not an active runtime/trading queue update.

## Fixed ADR/AMD Proposal Text

The following blocks are `NOT_APPLIED`. They are fixed proposal text only for a
future explicit PM/CC/FA/PA or PM/E3/BB scope. They are not accepted ADR/AMD
content and do not mutate governance state.

### AMD Proposal Text - NOT_APPLIED

```text
Operator accepts replacing the AI/ML scheduler/report-loop direction with a
scanner-driven active-learning ALR direction. ALR P0 remains source-only,
offline, single-shot artifact CLI work. It grants no runtime, trading,
exchange, PG, IPC, cron, daemon, service/env, Decision Lease, Cost Gate, order,
probe, proof, promotion, live/mainnet, official MCP, or delete/apply authority.
```

### ADR Proposal Text - NOT_APPLIED

```text
ALR consumes scanner evidence without changing ADR-0017: scanner output remains
evidence, not execution authority. ALR P0 is not ADR-0035 streaming online model
update. ALR proof comes only from candidate-matched after-cost outcomes bound by
ProofPacket and RewardLedger contracts. LLM outputs are advisory-only refs with
not_authority=true. Retention starts with dry-run reference graph, quarantine
classification, and tombstone proposal; physical delete is out of scope.
```

## JSON Artifacts

This iteration emits:

- `alr_work_item_v1`
- `alr_effect_review_v1`
- `alr_loop_state_packet_v1`

The artifacts must keep all runtime, exchange, trading, serving, proof,
promotion, deletion, root TODO, and ADR/AMD application authority flags false.

## Stop States

| State | Trigger |
|---|---|
| `BLOCKED_BOUNDARY` | Work needs runtime, PG, IPC, exchange, official MCP, Decision Lease, order/probe, scheduler, service/env mutation, model serving, promotion, Cost Gate, live/mainnet, `_latest` overwrite, or delete authority. |
| `DEFER_EVIDENCE` | Candidate-matched fills/fees/slippage/funding, reconstruction, controls, proof-exclusion pass, repeat evidence, or OOS evidence are missing. |
| `HYPOTHESIS_ONLY` | A target can be ranked for investigation but cannot claim edge. |
| `STOP_NO_EDGE` | Proof-ready evidence shows non-positive conservative after-cost lower confidence bound. Missing proof cannot use this state. |
| `STOP_RETENTION_RISK` | Cleanup touches proof, dispute, audit, lineage, unknown reference, negative example, no-fill/no-order, cleanup/unattributed, proof-excluded, failed, blocked, or `ROTATED` risk. |
| `STOP_DISPATCH_BLOCKED` | Required role-chain dispatch tooling is unavailable. |
| `ROTATED` | Source head, candidate id, input hash, auth/envelope, or referenced artifact drifted and cannot be re-intaken source-only. |
| `DONE` | All P0 rows are implemented, verified, effect-reviewed, state-packeted, and committed. |

## Unblock Rule

This packet sets `BOUNDARY_VALIDATED_WITH_CONCERNS` for the ALR stub only. The
concern is that ADR/AMD proposal text must remain visibly `NOT_APPLIED`.

It unblocks the next source-only queue row,
`P0-AIML-ALR-CONTROLLER-CONTRACTS`, only for controller contract source/docs/test
work under `SOURCE_ONLY_OFFLINE_P0_P1`. It does not unblock runtime,
exchange-facing, order-capable, proof/promotion, cleanup apply, ADR/AMD
mainline, root TODO, or migration work.

## Verification Checklist

For this row, PM must verify:

- `python3 -m json.tool .../manifest.json` passes;
- required boundary terms are present in this packet;
- `git diff --check` passes on ALR stub and PM/Operator report artifacts;
- changed files are limited to the ALR stub, PM report artifacts, and Operator
  summary;
- no root `TODO.md`, `docs/adr/`, `docs/amd/`, migrations, runtime config,
  code, runtime/exchange, PG, IPC, MCP, scheduler, service/env, `_latest`,
  proof/promotion, or delete/apply surface changed.
