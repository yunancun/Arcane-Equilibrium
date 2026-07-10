# GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 Queue

Updated: 2026-07-10T13:48:32Z
Goal status: `ACTIVE`
Current item: `WP1-ARTIFACT-CHURN-CONTROL`
WP1 checkpoint: code `c080c552b`, state
`SOURCE_READY_RUNTIME_GATE_PENDING`; the unauthorized disposable local-PG
probe is retracted and cannot satisfy runtime acceptance.
Source plus durable RCA reached Mac/origin at `e3228cdba`; the fresh gate must
still bind the live HEAD observed after this state-only correction.
Evidence binding: `baseline_state_packet.json` SHA-256
`30c10a497f02794525ce6e1d70972829bde7942a6a0bb181e36a13e308400b60`,
evidence-delta SHA-256
`0ab0b80f307951108d0cf5edd3bb5940cb936bd093081c37c6d90e874e52ec28`.
Every row inherits this baseline until it records a newer distinct evidence hash.
Pre-checkpoint drift recheck: Mac/origin advanced to `a84917fd9`; Linux remained
clean at `1a3ecdd57`. The two intervening commits are GUI-only and do not touch
ALR runtime/source/service/migration paths. Runtime actions remain gated on
fresh alignment.

Allowed nonterminal transitions are `ACTIVE -> ADVANCED -> ACTIVE`,
`ACTIVE -> DEFER_EVIDENCE -> ROTATE -> ACTIVE`, `ACTIVE -> REJECT -> ROTATE ->
ACTIVE`, `ACTIVE -> ROLLBACK -> RCA -> ACTIVE`, and `ACTIVE -> STOP -> RCA ->
ACTIVE`. `TRAIN`, `CHALLENGER_ACCEPT`, and `ROLLBACK` describe isolated ALR
challenger state only. None grants serving, trading, parameter-apply, or order
authority.

| ID | P | State | Owner chain | Dependencies | Exact acceptance | Gates (`E3/BB`, Operator, runtime mutation) | Effect / retries | Next safe executable action |
|---|---:|---|---|---|---|---|---|---|
| `WP0-GOVERNANCE-BASELINE` | 0 | `DONE` | `PM -> CC -> FA -> PA -> PM` | Operator Goal directive; current source/runtime read-only facts | New stub, G1-G9 matrix, baseline/state/effect packets, root TODO import, ADR-0049 addendum, accepted AMD register entry; old SUI is rotated; NEAR frozen; historical files untouched | `false`, `false`, `false` | Governance reconciliation complete; retry/RCA `0/0` | Do not reselect unless governance semantics change. |
| `WP1-ARTIFACT-CHURN-CONTROL` | 0 | `ACTIVE_SOURCE_READY_RUNTIME_GATE_PENDING` | `PM -> PA -> E1 -> E2 -> E4 -> QA -> PM`; runtime `PM -> E3 -> BB -> PM` | WP0 `DONE`; source checkpoint `c080c552b` | Persist health only on state delta or bounded heartbeat; identical candidate/regime/evidence/blocker hash does not create another DEFER; record actual rows/bytes/cycle and durable health/decision/feedback ratios; heartbeat never triggers training; prove production reduction/no starvation | source/tests `false`; isolated/production PG, apply/restart/soak `true`; Operator `false`; runtime mutation only after fresh exact-head gate | Source/static/unit PASS: focused `70`, ALR `246`, full ML `1302/31 skipped`; baseline health `735 rows/60m`, `1.256 MB/60m`, suppression `0`; unauthorized QA local-PG evidence retracted; retry/RCA `1/1` | Commit durable RCA/state, then issue a fresh non-retroactive exact-head E3/BB packet for controlled isolated-PG regression, ALR-service-only repin/restart, and >=300s production soak. |
| `WP2-CANDIDATE-AWARE-ARBITER` | 0 | `PENDING` | `PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> QA -> PM` | WP1 | Candidate identity includes strategy+version/config hash, symbol, side, horizon, regime, data/evidence context; ranks by distinct-entry `n_eff`, UTC-day/top-day/regime coverage, quality, proof gap, EVI, compute/storage cost, and cooldown; rotates globally | `false` source/tests; `false`; `false` | Current runtime has 364 scanner-novelty candidates, side `NONE`, no horizon/regime; retry/RCA `0/0` | Freeze an arbiter input/output schema and adversarial fixtures; no exchange contact. |
| `WP3-PROOF-REWARD-BRIDGE` | 0 | `PENDING` | `PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> QA -> PM`; future acquisition `PM -> E3 -> BB -> Operator -> PM` | WP2 qualified current candidate | Repository adapter joins PIT manifest -> current candidate -> controlled Rust order/fill -> actual fee/slippage/funding -> reconstruction -> ProofPacket -> RewardLedger -> after-cost label; one chain proves integration, not training sufficiency | source/tests `false`; any Demo/order chain `true,true,true` with exact SHA and same-window Rust/Guardian/Lease/BBO/risk checks | Baseline proof/reward/complete chain `0/0/0`; retry/RCA `0/0` | Implement only read/validation/repository adapters until a fresh exact candidate packet exists. |
| `WP4-ACTUAL-TRAINING-REGISTRY` | 0 | `PENDING` | `PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> QA -> E3 -> BB -> PM` | WP2 eligibility; WP3 qualified labels; fresh migration reservation | New versioned migration (V157 only after fresh collision scan/gate) permits real decision/run kinds without editing V152/V153; actual training writes artifact plus model/data/code/config hashes and isolated challenger registry lineage; `model_training_performed=true` only after real fit | source design/tests `false`; migration creation/apply and runtime `true`; Operator `false`; runtime mutation gated | Baseline actual training/artifact/registry `0/0/0`; retry/RCA `0/0` | Specify migration and registry contracts without creating/applying migration before exact E3/BB gate. |
| `WP5-OOS-DECISION-ENGINE` | 0 | `PENDING` | `PM -> QC -> MIT -> AI-E -> PA -> E1 -> E2 -> E4 -> QA -> PM` | WP4 | Walk-forward plus purge/embargo, hidden OOS, matched controls, negative cells, regime breakdown, stress, leakage/dedup defenses; decisions include `DEFER/ROTATE/TRAIN/REJECT/CHALLENGER_ACCEPT/ROLLBACK/STOP`; all reasons/hash lineage durable | `false` source/tests; `false`; `false` | Baseline hidden OOS/effect decisions `0/0`; retry/RCA `0/0` | Pre-register evaluation and decision-state contracts with mutation-biting fixtures. |
| `WP6-EVENT-DRIVEN-AUTO-EVOLUTION` | 1 | `PENDING` | `PM -> PA -> E1 -> E2 -> E4 -> QA -> E3 -> BB -> PM` | WP1-WP5 | LISTEN/event-driven service, no cron/fixed training; natural cycles, restart recovery, two distinct evidence-delta hashes automatically re-evaluate/retrain/rotate; useful model/evaluation/registry/effect artifacts; safe retention | production service/restart/retention `true`; Operator only for external order evidence; runtime mutation `true` | Service currently active/pin-stale; second-delta evolution unproven; retry/RCA `0/0` | Build isolated event-delta/restart tests first; later open exact deployment gate. |
| `WP7-ADVERSARIAL-FINAL-AUDIT` | 1 | `PENDING` | `PM -> CC -> FA -> QC -> MIT -> AI-E -> PA -> E2 -> E4 -> QA -> E3 -> BB -> PM` | WP1-WP6 | G1-G9 machine evidence, stale/duplicate/no-delta/rollback/restart/resource/retention/authority attacks, three-head alignment, current runtime proof, and 16-root-principles/spec compliance all pass | runtime verification `true`; Operator only if an external effect is required; no automatic authority | Final retry/RCA counters aggregate all WPs | Execute independent audits; terminal only after all G1-G9 PASS. |

## Gate rules

- Pure source/test work follows `PA -> E1 -> E2 -> E4 -> QA`.
- Selection/training/evaluation semantics require `QC -> MIT -> AI-E`.
- Governance, retention, and authority semantics require `CC -> FA -> PA`.
- New migration creation, isolated/production PostgreSQL work, service apply or
  restart, sustained runtime, or retention sweep requires fresh exact-head
  `E3 -> BB -> PM`; production also requires alignment, Guard A/B/C,
  double-apply, rollback, and RM-1 before/after evidence.
- Any Bybit-facing or Demo order action requires fresh `E3 -> BB`, exact
  SHA-bound Operator approval, then same-window current candidate, GUI/Rust
  RiskConfig, equity, Guardian, Decision Lease, BBO/instrument/order shape,
  local and exchange-side disaster protection, audit, and reconstruction.
- Live/mainnet, global Cost Gate lowering, automatic serving/promotion,
  `_latest` overwrite, and protected-evidence deletion are outside this Goal.
