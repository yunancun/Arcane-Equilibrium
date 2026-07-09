# ALR Source Boundary

Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

Hard stop: ALR P0/P1 is source-only, offline, local-artifact engineering. It
grants no runtime, trading, exchange, Bybit, official MCP, PG, IPC, cron,
daemon, service, Decision Lease, adapter/writer, order/probe, Cost Gate,
live/mainnet, proof, or promotion authority.

## Evidence Taxonomy

| Class | May Rank Learning Target | May Affect Reward/Edge | Notes |
|---|---:|---:|---|
| `scanner_intake` | yes | no | `OpportunityCandidate`, final score, registry rows, decay events. |
| `no_order_gate` | yes | no | BBO, Decision Lease availability, preflight, no-order/no-fill diagnostics. |
| `execution_touchability` | yes | no | Touchability and gate readiness diagnostics only. |
| `candidate_matched_outcome` | yes | yes | Requires candidate-matched order/fill/reconstruction evidence and cost fields. |
| `promotion_proof` | yes | yes | Requires accepted proof packet, reward ledger, controls, repeat or OOS evidence, and effect review. |

Scanner output, artifact counts, `_latest` artifacts, no-order BBO/Decision
Lease windows, touchability/preflight packets, released leases, cleanup fills,
unattributed fills, and no-fill rows may rank learning targets or identify proof
gaps. They must never populate `reward`, `proof_passed`,
`edge_claim_allowed`, `promotion_ready`, or `candidate_profit_proven`.

## Objective

P0 target scoring optimizes `expected_value_of_information` under bounded risk.
It does not optimize expected trade PnL. If no candidate-matched proof packet
exists, after-cost EV fields must be null or explicitly labeled
`hypothesis_prior`, with `edge_claim_allowed=false` and
`proof_status=HYPOTHESIS_ONLY`.

`STOP_NO_EDGE` is allowed only after proof-ready candidate-matched outcomes plus
controls and repeat/OOS evidence show non-positive conservative after-cost lower
confidence bound. Missing proof is `DEFER_EVIDENCE`, not no edge.

## Model And LLM Boundary

P0 ALR is source-only target intake and artifact emission. It is not model
training, not model serving, not online learning, not proof, not runtime
authority, and not autonomous trading maturity.

All target scoring/ranking that can affect `next_action` must be deterministic
or traditional statistical code with replayable inputs. LLM output may only be
stored under `advisory_refs` with `not_authority=true`.

LLM, L1, L2, DreamEngine, and Teacher outputs must not:

- set or modify `target_score`, `proof_status`, `reward_value`,
  `maturity_status`, or `promotion_status`;
- write or update ProofPacket, RewardLedger, Decision Lease, Guardian,
  RiskConfig, SymbolRegistry, `_latest`, `_current`, registry serving authority,
  or runtime config;
- trigger DB/PG writes, IPC, Bybit REST/WS, private reads, orders/probes, Cost
  Gate changes, live/mainnet, or model reloads;
- satisfy evidence, proof, loss-control, runtime, E3/BB, or operator
  authorization gates.

## Runtime And Exchange Boundary

Stop with `BLOCKED_BOUNDARY` if any P0/P1 work introduces or requires:

- cron, crontab, daemon, sidecar, background loop, launchd, systemd, watchdog,
  scheduler, `while True`, task spawn, or sleep loop;
- runtime SSH, service restart/rebuild, deploy, environment mutation, secret
  read, or credential handling;
- PG read/write/DDL/migration, Timescale policy mutation, or database
  connection;
- IPC listener/writer, Decision Lease acquisition, adapter/writer enablement,
  or engine socket use;
- Bybit REST/WS public or private contact, private/account REST, private WS,
  order create/amend/cancel/modify/cancel-all, fee-rate private reads, any
  endpoint under `/v5/order`, official exchange MCP install/start/connect/use,
  official MCP credential/private read/order path, order-shape admission, or
  trading permission;
- scanner runtime changes, scanner cadence/subscription changes,
  `SymbolRegistry` overload, `TradingMsg`, route score mutation, or order
  dispatch path;
- `_latest` overwrite, symlink promotion, model reload, model serving
  promotion, Cost Gate change, proof promotion, live/mainnet, or physical
  delete.

Future runtime or exchange scope requires `PM -> E3 -> BB -> PM` with exact
scope. This stub does not grant that scope.

Do not work around the stop by using public REST, official MCP, cached
credentials, existing standing auth, prior no-order approvals, prior Bybit public
GET approvals, or current trading P0 candidate context.

## Changed-File Allowlist For P0

P0 implementation may add or modify only focused source-only AI/ML files such as:

- `program_code/ml_training/*alr*`
- `program_code/ml_training/*learning_target*`
- `program_code/ml_training/*arbiter*`
- `program_code/ml_training/*proof*bridge*`
- `program_code/ml_training/*reward*bridge*`
- `program_code/ml_training/*retention_guardian*`
- `program_code/ml_training/tests/test_*alr*`
- `program_code/ml_training/tests/test_*learning_target*`
- `program_code/ml_training/tests/test_*retention_guardian*`
- dated PM/Operator reports and state/effect/work-item JSON artifacts

Do not touch scanner runtime, cron wrappers, systemd/launchd files, runtime
scripts, migrations, IPC clients, exchange connectors, order/risk authority,
or model registry promotion paths in P0.
