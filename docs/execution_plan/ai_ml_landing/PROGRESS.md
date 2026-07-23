# AI/ML Landing Progress Ledger

**Program**: `AIML-LONG-LIVED-LANDING-V2`
**Ledger version**: 4
**Updated**: 2026-07-23
**Overall state**: `PROGRAM_ADOPTED` · S1 source-complete on review branch
`agent/aiml-s1-landing` (S1.1-S1.6 all `DONE_WITH_EXTERNAL_EVIDENCE_PENDING`);
not yet merged and not yet a PM-declared `EFFECT_SEAMS_READY` ledger gate.
S1 formal-closure effect seam (target-host probe) landed via PR #114
(`7d78765a2`); its 3 post-merge Codex findings (2×P1 + 1×P2) are now fixed on
branch `agent/aiml-s1-closure-p1p2-fixes` (`af2491300`, source-complete) — see the
newest ledger event. The external S3 Object-Lock **effect** is `S8.6`, not an S1
blocker; the only remaining S1-closure gate is the out-of-band operator SSHSIG.
**Adopted source generation**: reviewed head
`1a933fcc28e9f7341e023b5d401c479957c14c5f`, merged as
`fed223bebd278c50b0ab3330980e66441a30c9ed`
**Program-adoption receipt**:
`docs/execution_plan/ai_ml_landing/receipts/S0.3-program-adoption-receipt-v1.json`
(`sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b`)
**Attested finalization evidence**:
`docs/execution_plan/ai_ml_landing/receipts/S0.3-program-adoption-finalization-attestation-v1.json`
plus `.sig`, and `S0.3-trusted-execution-bundle-v1.json` plus `.sig`; both
signatures verify against the adopted source trust root.
**S1 review branch**: `agent/aiml-s1-landing` atop main `5362fdd4b`; six
source-complete session commits — S1.1 `3c0b7fb2f`, S1.2 `d12f84632`,
S1.4 `7d0befd86`, S1.3 `08789982e`, S1.5 `0b2805a4d`, S1.6 `0e8e9fd9d` — each
passing its per-session role chain (E2/E4/CC/E3/OPS/QA + fix rounds) plus a
cross-session review round (PA integration / CC whole-body / FA spec-compliance
all PASS). Not yet merged or pushed.
**Next gate**: the Sprint-1 exit `EFFECT_SEAMS_READY` is substantively composed
on `agent/aiml-s1-landing` by S1.5 (`effect_seams_ready_receipt` scope
`S1.5_CONTRIBUTION`) + S1.6 (`learning_runtime_choice_receipt_v1`, final choice
`content_addressed_fixed_path`, BINDING), but it is PENDING (a) the exact-head
merge and (b) the Linux CI / trusted-host test attestation; it is NOT yet a
PM-declared `EFFECT_SEAMS_READY` ledger gate. After merge + Linux green, the
next Sprint is S2 with READY pool `S2.0 ∥ S2.2A ∥ S2.3`.
**Canonical boundary**: S0 is closed and all six S1 sessions are source-complete
and reviewed on the branch, but every S1 effect is disposable (`DISPOSABLE_ONLY`
/ `DISPOSABLE_APPLY_ROLLBACK_POSTCHECK` / `TARGET_HOST_DISPOSABLE_RUNTIME_PROBE`)
with evidence class `LOCAL_REPRODUCIBLE` (real disposable proof on Mac dev:
42501/28P01, os.replace/chmod, python3 -I), and the platform-attested (Linux
trusted-host / CI) test attestation is still OWED — the S1 receipts are emitted
disposably, not committed as JSON. All nine authority grants remain false; there
is still no runtime, build, PostgreSQL, migration, deploy, ML5/ML6, broker or
order authority, and source adoption is not runtime readiness.

## Ledger Contract

`TODO.md` owns active priority. Immutable `session_attempt_v1` and
`closure_packet_v1`/Report Sink records own authoritative Session outcomes; this
file is their repo-resident projection and resume index. Update a row only with
the exact branch/PR/head and completion receipt. Preserve prior outcomes in the
row notes or append a dated ledger event; do not silently rewrite failed
evidence. A later Session consumes only valid, scope-compatible, hash-bound
dependency generations.

Allowed status:

```text
PLANNED | READY | IN_PROGRESS | SOURCE_READY | RECOVERY_REQUIRED | BLOCKED | BLOCKED_STALE_EVIDENCE | NOT_APPLICABLE_NO_CANDIDATE |
DONE | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | SUPERSEDED
```

Required closure fields for a `DONE` row:

- `(session_id, landing_scope_id, cohort_epoch, attempt)` or `PROGRAM` template;
- `platform_scope`, `policy_surface_id`, exact covered decision cells and
  evidence-environment promotion edges;
- exact branch, reviewed head, PR/merge head and owned path manifest;
- route/DAG digest, explicit node IDs/classes/permissions/path ownership/
  predecessors and builder -> E2 -> E4 plus post-build semantic review;
- focused/local validation and CI classifier digest, selected workflows, exact
  head, invocation count and failure fingerprints;
- classifier-derived `required_effects`, Adapter ID, actor node, rollback and
  distinct postcheck node, including a typed `NONE` when no effect is possible;
- completion receipt hash, validity class, causal-time edges and next dependency.

Before work, W0 CAS-creates the attempt with owner lease epoch/expiry/heartbeat,
branch/worktree, baseline/checkpoint, path manifest and dependency generations.
Lease expiry moves to `RECOVERY_REQUIRED`; only CAS adoption/finalization can
resume or close it.

Class-specific invalidity recursively demotes all dependent attempts.
`CURRENT_STATE_TTL` expiry and explicit retroactive compromise/revocation do;
natural expiry of already consumed `EFFECT_TIME_AUTHORITY` does not invalidate
its `IMMUTABLE_CONSUMED_EFFECT`. `IMMUTABLE_LINEAGE` fails only on hash/causality
break. No generic scope template can be `DONE`; it must first be instantiated.

## Current Sessions

| Sprint | Session | Work package | Scope template | Dependencies | Required role route template | Status | Completion receipt | Required effect | Sync / CI policy |
|---:|---|---|---|---|---|---|---|---|---|
| 0 | S0.1 | Integrate current origin/main, preserve TODO union, publish V2 documents | PROGRAM | none | PM -> PA -> TW -> R4 -> QA -> PM | DONE | `docs/execution_plan/ai_ml_landing/receipts/S0.1-planning-documents-published-v1.json`<br>`sha256:8fc9417f984025deabdc1b83ace95921ccfff1acb26a1b29243fc0a0a5ba79ad` | `NONE` | PR #100 lineage: base `96d26245068cbfbc8d60e73fb8eb82c4109b0d40`, head `35b4d1e4091b7dc34af248f51f512f2d8d51e9b0`, merge `cfb3a4040ffb2974192c53609b72e7afba4a845d`; at S0.1 closure the reconciled Mac/GitHub/Linux source head was `c2f5a2e26e422d56b8ec9b540d7f36bea9a0be54`; merge remains an ancestor of the adopted generation |
| 0 | S0.2 | Accept ADR-0049/AMD serving/retraining/rollback/no-broker authority | PROGRAM | S0.1 | PM -> PA -> CC/E3 -> R4 -> QA -> PM | DONE | `docs/execution_plan/ai_ml_landing/receipts/S0.2-serving-authority-receipt-v1.json`<br>`sha256:0115dbd3dc62d84e183aae5a28cbfd252eb45ecee51a652d8a4a155f14dfb41a` | `NONE` | Accepted source-policy commit `f325b4dfdafd1979197c8a9e6450efeaf85e091c`; its immutable receipt was consumed by the completed S0.3 finalizer |
| 0 | S0.3 | Scope/attempt/effect governance, terminal-sink contract and GitHub admin attestation | PROGRAM | S0.1, S0.2 | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/MIT/R4 -> QA -> PM | DONE | `docs/execution_plan/ai_ml_landing/receipts/S0.3-program-adoption-receipt-v1.json`<br>`sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b`<br>producer-signed finalization attestation + trusted execution bundle in the same directory | `EXTERNAL_READONLY_ATTESTATION` | PR #104 source landing; PR #106 forge-resistance hardening merge `afa7eb2e97d6ab975709d4472b12f7397ee03bfb`; PR #107 live PR projection merge `0cdd3537ead94675a4d0033df5bbcbf5d33b1b16`; PR #108 Linux fixture repair reviewed head `1a933fcc28e9f7341e023b5d401c479957c14c5f`, merge `fed223bebd278c50b0ab3330980e66441a30c9ed`. Seven authenticated review fragments, git ancestry/blob verification, live GitHub policy attestation and Linux governed E4 `275/275` passed before trusted-host issuance; repo-resident SSHSIG evidence independently binds the PASS result to this receipt and lineage. |
| 1 | S1.1 | LR0A PG read-only identity Adapter | PROGRAM | PROGRAM_ADOPTED | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | source/disposable `pg_readonly_identity_receipt_v1`<br>branch `agent/aiml-s1-landing` @ `3c0b7fb2f`; evidence class `LOCAL_REPRODUCIBLE` (real 42501/28P01); disposably emitted, Linux attestation owed | `DISPOSABLE_ONLY` | Migration/ACL CI if touched; no production PG |
| 1 | S1.2 | LR0B typed effects, governance wiring and terminal WORM sink Adapter | PROGRAM | PROGRAM_ADOPTED | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | effect-contract/governance/sink receipt (terminal WORM sink CONTRACT_ONLY -> implemented flip)<br>branch `agent/aiml-s1-landing` @ `d12f84632`; evidence class `LOCAL_REPRODUCIBLE`; disposably emitted, Linux attestation owed | `DISPOSABLE_ONLY` | Protected/deploy workflow CI if touched |
| 1 | S1.3 | Host UID/PG role/auth/socket ACL/secret lifecycle contracts | PROGRAM | S1.1, S1.2 | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | `identity_acl_contract_receipt_v1`<br>branch `agent/aiml-s1-landing` @ `08789982e`; evidence class `LOCAL_REPRODUCIBLE`; disposably emitted, Linux attestation owed | `DISPOSABLE_ONLY` | Disposable PG + migration/ACL CI |
| 1 | S1.4 | LR0C offline OCI vs fixed-path candidate proof | PROGRAM | PROGRAM_ADOPTED | PM -> PA -> E1 -> E2 -> E4 -> CC/OPS -> QA -> PM | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | runtime-candidate receipts: `runtime_candidate_receipt_v1` ×2 + `runtime_candidate_comparison_v1` (final_choice const null)<br>branch `agent/aiml-s1-landing` @ `7d0befd86`; evidence class `LOCAL_REPRODUCIBLE` (real python3 -I); disposably emitted, Linux attestation owed | `DISPOSABLE_ONLY` | Runtime/build CI on stable head |
| 1 | S1.5 | Per-component Adapter plus remote/platform observation seam | PROGRAM | S1.1-S1.4 | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | `effect_seams_ready_receipt_v1` (`sprint_gate_scope` const `S1.5_CONTRIBUTION`; matrix `adapter_binding_status` flip)<br>branch `agent/aiml-s1-landing` @ `0b2805a4d`; evidence class `LOCAL_REPRODUCIBLE` (real os.replace/chmod apply/rollback/postcheck); disposably emitted, Linux attestation owed | `DISPOSABLE_APPLY_ROLLBACK_POSTCHECK` | Stable-head deploy CI; no production apply |
| 1 | S1.6 | Target-host isolated disposable runtime probes and final choice | PROGRAM | S1.4, S1.5 | PM -> Adapter actor -> distinct OPS/CC/E3 -> QA -> PM | DONE_WITH_EXTERNAL_EVIDENCE_PENDING | `learning_runtime_choice_receipt_v1` (final_choice `content_addressed_fixed_path`, BINDING; oci_selectable false; production_running_attested false)<br>branch `agent/aiml-s1-landing` @ `0e8e9fd9d`; evidence class `LOCAL_REPRODUCIBLE` (real python3 -I disposable probes); disposably emitted, Linux attestation owed | `TARGET_HOST_DISPOSABLE_RUNTIME_PROBE` | Cleanup postcheck; no production running claim |
| 2 | S2.0 | Bootstrap production PG observer role/auth/ACL only | PROGRAM | EFFECT_SEAMS_READY | PM -> external admin Adapter -> distinct OPS/E3 -> QA -> PM | PLANNED | observer-bootstrap effect/postcheck | `PG_OBSERVER_BOOTSTRAP` | Exact intent; no migration/writer |
| 2 | S2.1 | LR0 evidence/quiescence/static guards | PROGRAM | S2.0, S1.6 | PM -> OPS/E3 -> E1 -> E2 -> E4 -> QA -> PM | PLANNED | quiescence/static-guard receipt | `QUIESCE_FENCE` | Typed intent; no general CI |
| 2 | S2.2A | LR1 scoped compatibility source implementation | PROGRAM | S1.6 | PM -> PA -> E1 -> E2 -> E4 -> QA -> PM | PLANNED | source compatibility receipt | `NONE` | Narrow Python local-first; exits SOURCE_READY |
| 2 | S2.2B | LR1 runtime revalidation of exact S2.2A manifest | PROGRAM | S2.5, S2.2A@SOURCE_READY | PM -> independent OPS/E4 -> QA -> PM | PLANNED | `ingestion_compatibility_receipt_v1` | `REMOTE_READONLY` | Only row that issues LR1 runtime DONE |
| 2 | S2.3 | LR2 sealed immutable runtime build/trust chain | PROGRAM | S1.3, S1.6 | PM -> PA -> E1 -> E2 -> E4 -> CC/OPS -> QA -> PM | PLANNED | sealed build receipt | `NONE` | Runtime/build CI; not running attestation |
| 2 | S2.4 | Credential/PG/unit/install effects and component restore | PROGRAM | S2.0, S2.1, S2.2A@SOURCE_READY, S2.3 | PM -> OPS preflight -> E3 -> Adapter -> distinct OPS -> QA -> PM | PLANNED | per-component effect/postcheck receipts | `CREDENTIAL_PG_UNIT_INSTALL` | Intermediate exact-head sync first |
| 2 | S2.5 | Running attestation, watchdog-last recovery, observer/dead-man and rollback | PROGRAM | S2.4 | PM -> OPS/E3 -> E4 -> QA -> PM | PLANNED | runtime attestation/recovery receipt | `WATCHDOG_ROLLBACK_TEST` | Platform-attested; no CI without source change |
| 3 | S3.1A | LR3 durable queue/controller/worker source implementation | PROGRAM | S2.3 | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | PLANNED | queue source receipt | classifier-derived PG/service source | Migration/ACL/runtime CI; exits SOURCE_READY |
| 3 | S3.1B | LR3 runtime queue/controller/worker verification | PROGRAM | S2.5, S3.1A@SOURCE_READY | PM -> independent OPS/E4 -> QA -> PM | PLANNED | `queue_recovery_receipt_v1` | `REMOTE_READONLY` | Only row that issues LR3 runtime DONE |
| 3 | S3.2 | LR4 loss-aware Scanner gap/drop-SLO handoff | landing_scope_id instance | S2.5, S3.1B | PM -> PA -> E1 -> E2 -> E4 -> QC/OPS -> QA -> PM | PLANNED | loss-aware Scanner receipt | classifier-derived engine deploy | Rust CI if Scanner changes |
| 3 | S3.2A | Pre-filter universe/PIT/reason/choice/policy/RNG/propensity persistence | landing_scope_id instance | S3.2 | PM -> QC/MIT -> E1 -> E2 -> E4 -> QA -> PM | PLANNED | universe/selection receipt | classifier-derived PG/engine effect | Rust/migration CI as classified |
| 3 | S3.3 | LR5 physical retention/backpressure/deleter/restore | PROGRAM | S2.5, S3.1B | PM -> PA -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | PLANNED | retention apply/per-object receipts | `RETENTION_APPLY_RESTORE` | Destructive fixtures before apply |
| 3 | S3.4 | LR6 faults, independent observer and 72h/two-cycle soak | landing_scope_id instance | S3.1B, S3.2, S3.2A, S3.3 | PM -> distinct OPS observer -> E4 -> QA -> PM | PLANNED | `foundation_ready_receipt_v1` | `FAULT_INJECTION_OBSERVE` | Platform-attested; no CI without change |
| 4 | S4.1 | ML0 scope/policy surface/cell coverage/environment/cohort baseline | landing_scope_id instance | FOUNDATION_READY | PM -> QC/MIT -> OPS read-only -> QA -> PM | PLANNED | `scope_cohort_receipt_v1` | `PG_READONLY` | No CI; LR0A only |
| 4 | S4.2 | ML1 full universe/propensity/exploration portfolio | landing_scope_id instance | S3.2A, S4.1 | PM -> E1 -> E2 -> E4 -> QC/MIT/AI-E -> QA -> PM | PLANNED | `target_portfolio_receipt_v1` | `NONE` | Narrow Python local-first |
| 4 | S4.3 | ML2 bitemporal labels/proof/reward revisions | landing_scope_id instance | S4.1, S4.2 | PM -> E1 -> E2 -> E4 -> QC/MIT -> QA -> PM | PLANNED | `label_revision_receipt_v1` | classifier-derived PG effect | Migration CI if schema changes |
| 4 | S4.4 | ML2A loaded-row PIT matrix, revision IDs, feature vectors and parity | landing_scope_id instance | S4.3 | PM -> E1 -> E2 -> E4 -> QC/MIT/AI-E -> QA -> PM | PLANNED | `pit_dataset_receipt_v1` | `NONE` | Rust CI if parity code changes |
| 5 | S5.1 | ML3 trusted host and qualified-only reproducible fit | landing_scope_id instance | S4.4 | PM -> E1 -> E2 -> E4 -> QC/MIT/AI-E/CC/OPS -> QA -> PM | PLANNED | `trusted_fit_result_receipt_v1` | `FIT_ARTIFACT_REGISTRY_WRITE` | Runtime/build/serving CI |
| 5 | S5.2 | ML4 action authority lattice, holdout ledger and adversarial OOS | landing_scope_id instance | S5.1 | PM -> E1 -> E2 -> E4 -> QC/MIT/AI-E -> QA -> PM | PLANNED | `oos_action_policy_receipt_v1` | `NONE` | Statistical fixtures; Rust CI if contract changes |
| 5 | S5.3 | ML5 qualified registry writer, legacy fail-close and shadow server | landing_scope_id instance | S5.2 + serving authority | PM -> E1 -> E2 -> E4 -> PA/QC/CC/OPS -> QA -> PM | PLANNED | registry/shadow receipt | `REGISTRY_SHADOW_ACTIVATION` | Migration/serving CI |
| 6 | S6.1 | Rust IntentProcessor + EdgePredictorStore consumer and ORT/runtime proof | landing_scope_id instance | S5.3 + serving authority | PM -> E1 -> E2 -> E4 -> PA/QC/CC/OPS -> QA -> PM | PLANNED | `real_consumer_receipt_v1` | `CONSUMER_CANARY_ROLLBACK` | Rust/serving CI |
| 6 | S6.2 | Consumer-ACK activation and legacy writer retirement | landing_scope_id instance | S6.1 | PM -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | PLANNED | single-path activation receipt | `MODEL_ACTIVATION_SWAP` | Migration/serving CI |
| 6 | S6.3 | ML6 mechanical harness plus optional economic causal design | landing_scope_id instance | S5.2, S6.2 | PM -> E1 -> E2 -> E4 -> QC/MIT/AI-E/E3/BB -> QA -> PM | PLANNED | causal-design readiness receipt | `NONE` | Rust CI if policy code changes; no broker effect |
| 6 | S6.4 | Bounded Demo mechanical integration and optional economics | Demo promotion edge instance | S6.3 + fresh authority | PM -> E3 -> BB -> Adapter/runtime -> distinct OPS/QC -> QA -> PM | PLANNED | mechanical + optional economic receipts | `BYBIT_DEMO_POLICY_EFFECT` | Intermediate sync/runtime attestation first; no live |
| 7 | S7.1 | Natural controller G2 evaluation and ModelOps SLO/actions | landing_scope_id instance | S6.4 | PM -> E1 -> E2 -> E4 -> QC/MIT/AI-E/OPS -> QA -> PM | PLANNED | `generation_2_receipt_v1` | `NONE` or fresh gated model activation | New forward data; serving CI if changed |
| 7 | S7.2 | Encrypted off-host DR, clean restore, key/corruption/RPO/RTO | landing_scope_id instance | FOUNDATION_READY + platform components; trading branch also S7.1 | PM -> E1 -> E2 -> E4 -> CC/E3/OPS -> QA -> PM | PLANNED | `dr_restore_receipt_v1` | `ISOLATED_DR_RESTORE` | No production overwrite |
| 7 | S7.3 | Seven unattended days, independent observer and natural workload | landing_scope_id instance | S7.2 + platform components | PM -> distinct OPS observer -> QA -> PM | PLANNED | `continuous_operation_receipt_v1` | `OBSERVE_ALERT_TEST` | No CI unless source changes |
| 7 | S7.4 | ML9 causal-time landing candidate manifest | landing_scope_id instance | S7.1-S7.3 | PM -> QC/MIT/AI-E/CC/E3/OPS -> QA -> PM | PLANNED | `aiml_landing_manifest_v1` / candidate only | `NONE` | Current runtime receipts only; no terminal state |
| 7 | S7.NC | No-eligible-candidate platform candidate validator | landing_scope_id instance | FOUNDATION_READY, S3.2A, S4.2 no-eligible, S7.2, S7.3 | PM -> independent QC/OPS -> QA -> validator | PLANNED | `aiml_platform_no_candidate_candidate_v1` | `REMOTE_READONLY` | Candidate-only Sessions become N/A, never DONE; P1 remains open |
| 8 | S8.1 | Stabilize and freeze release-candidate head | PROGRAM + instantiated scopes | S7.4 or S7.NC | PM -> builders/reviewers as needed -> QA -> PM | PLANNED | release-candidate freeze receipt | classifier-derived | No publication until all fixes integrated |
| 8 | S8.2 | Exact-head full audit/review/required CI/admin-policy attestation | frozen candidate | S8.1 | PM -> PA/QC/MIT/AI-E/CC/E3/OPS/R4 -> QA -> PM | PLANNED | exact-head final audit receipt | `EXTERNAL_READONLY_ATTESTATION` | Any head change returns S8.1 |
| 8 | S8.3 | Exact-head merge | PROGRAM | S8.2 accepted | PM publication lane -> QA | PLANNED | merge receipt | `GIT_PUBLICATION` | Match reviewed head; no closure write pending |
| 8 | S8.4 | Final Mac/GitHub/Linux ff-only sync, four-head, deploy if digest changed | PROGRAM | S8.3 | PM -> OPS -> Adapter if required -> distinct OPS/QA | PLANNED | final source/deploy receipt | `SOURCE_SYNC` plus classified deploy | No force/reset/stash/clean |
| 8 | S8.5T | Trading AIML runtime attestation including registry ACK/loaded model | landing_scope_id instance | S8.4, S7.4 | PM -> independent OPS/E3/QC -> QA -> PM | PLANNED | `aiml_final_runtime_attestation_v1` profile TRADING | `REMOTE_READONLY` | Source sync is not runtime proof |
| 8 | S8.5NC | No-candidate platform attestation proving no model/promotion/consumer/order authority | landing_scope_id instance | S8.4, S7.NC | PM -> independent OPS/E3/QC -> QA -> PM | PLANNED | `aiml_final_runtime_attestation_v1` profile NO_CANDIDATE | `REMOTE_READONLY` | Platform/runtime health without trading evidence |
| 8 | S8.6 | Trading final reconcile, WORM append and readback validator | landing_scope_id instance | S7.4, S8.5T | PM -> independent QA/OPS/QC -> sink actor -> distinct readback verifier | PLANNED | immutable trading terminal receipt + ACK | `TERMINAL_RECEIPT_APPEND` | No repo write after; only source of trading landing state |
| 8 | S8.NC | No-candidate final reconcile, WORM append and readback validator | landing_scope_id instance | S7.NC, S8.5NC | PM -> independent QA/OPS/QC -> sink actor -> distinct readback verifier | PLANNED | platform terminal receipt + ACK | `TERMINAL_RECEIPT_APPEND` | Platform state only; P1/ML5-ML10 remain incomplete |

## Ledger Events

| Time | Session | Event | Evidence |
|---|---|---|---|
| 2026-07-23 | S1-formal-closure-fix | `S1_PR114_FINDINGS_FIXED_SOURCE_COMPLETE` — closes the three Codex findings that PR #114 merged before review completed (2×P1 + 1×P2), plus the S1 signing decision and the CI-selection gap. **P1 postcheck binding**: `validate_target_host_effect_binding` no longer accepts a bare `source==ops_postcheck` label — a PASS closure now requires the distinct-verifier UPGRADED effect result (structured `verifier_capture_digest` non-null; applier self-run alone cannot close), an ops_postcheck bound to the verifier's own governed `command_capture_v2` (structural+self-digest integrity, distinct role/node/process/capture from the applier), a clean residue observation (nonzero fails closed), `source_head`/`host`/`observed_at` bound to the receipt, a three-way digest cross-check, and acceptance binding all three evidence ids. **P1 process-global auth**: applier no longer mutates parent `os.environ[AIML_TARGET_HOST_PROBE]` — the real runner passes an intent-derived authorization capsule over a one-time stdin pipe to an isolated `python3 -I` child (new `agent_governance_target_host_child_apply.py`) that re-validates and opens the gate only in its own env; direct/expired/tampered/replayed/host-mismatch all fail closed. **P2 WORM**: readback + dedup now require observed `retain_until` ≥ approved (tz-normalized). **Signing (Amendment A1 §6)**: S1 profile reuses the S0.3 trust root under the domain-separated S1 identity+namespace (placeholders removed; no second key). S1.2A external-CAPABLE source adapter is complete; the external S3 Object-Lock **effect** (real bind/append/readback) is **S8.6**, NOT an S1 blocker; an S3 config is no longer required to close S1. `S1_ENGINEERING_CLOSED_EXTERNAL_WORM_BINDING_PENDING` is superseded — the only remaining S1-closure gate is the out-of-band operator SSHSIG over the target-host execution bundle (its private key is on neither Mac nor trade-core). Nine authorities false; source_adoption_only; no runtime/broker/order. | Branch `agent/aiml-s1-closure-p1p2-fixes`; source commit `af2491300` (base `origin/main` `7d78765a2`). +38 focused tests across `test_target_host_effect_adapter.py` / `test_target_host_apply_orchestrator.py` / `test_terminal_receipt_external_sink.py` / `test_agent_governance_aiml_trusted_host.py` + new `test_agent_governance_target_host_child_apply.py`; full local `tests/structure/` green (2138 passed, 6 skipped). Design: `docs/execution_plan/ai_ml_landing/design/S1.6B-real-target-host-probe.md` §11. Independent E2/E3/E4/CC review + Linux bounded-probe rerun + `closure_packet_v1` follow this event. |
| 2026-07-23 | S1-formal-closure | `S1_FORMAL_GOVERNANCE_CLOSURE_ENGINEERING_COMPLETE` (Waves A-C). The S1.6B target-host probe is now a fully closure-admissible effect seam: central-validator registration of `learning_runtime_choice_receipt_target_host_v1` (structure-only offline; STRICT attested at the effect/closure lane), additive `aiml_landing_session_attempt_v1` (own validator; rejects the S0.* family), a `target_host_probe` route class + `target_host_disposable_runtime_probe_adapter_v1` + typed intent + dedicated `target_host_effect_result_v1`, an intent-derived apply orchestrator (probe auth from a validated intent, NOT a user env var), a distinct (role+process+capture) verifier, an SSHSIG S1 signer profile (reuse `_verify_ssh_signature`; S0.3 byte-identical; real key operator-gated), and the S1.2A S3-Object-Lock external-CAPABLE WORM source adapter (fail-closed w/o creds; AWS-secret smuggling closed; non-destructive readback). A REAL bounded non-root disposable probe ran on `trade-core` through the orchestrator → binding=**BINDING** (8/8 fixed-path seams real; OCI NON_SATISFIABLE), evidence_class=PLATFORM_OR_EXTERNAL_ATTESTED, observed_host==expected==trade-core, **zero residue** (prod PG :5432 untouched). The real effect result + choice receipt + `aiml_landing_session_attempt_v1` are producer-generated + central-validator PASS. Frozen S0.3 classifier digest byte-identical (`sha256:1cf8c021…d0ddbc`); nine authorities false; source_adoption_only. Terminal: **`S1_ENGINEERING_CLOSED_EXTERNAL_WORM_BINDING_PENDING`** — a fully-attested `S1_CLOSED` is gated on TWO operator inputs (the S1 target-host SSHSIG signer key + signing, and the external S3 Object-Lock config), emitted as one `external_verification_pending` request. | Branch `agent/aiml-s1-formal-closure`: Wave A `d942d6fc3`, Wave B `9ea6be9b9`; design `docs/execution_plan/ai_ml_landing/design/S1-formal-closure-wave-a.md`; run record `docs/execution_plan/ai_ml_landing/receipts/S1-formal-closure-target-host-run-record.md` (effect receipt `sha256:e2b838e8…`, choice `sha256:447ab474…`, attempt `sha256:5f174e05…`). PA design → CC/E2 architecture gate → E1 builds → E2/E3/E4 hard-edge reviews → fix rounds; repair plan Amendment A1 + delivery-protocol S1.2A/S8.6 WORM split. |
| 2026-07-23 | S1.6B | `S1.6_TARGET_HOST_ATTESTATION_REAL_ON_TRADE_CORE`. Closes the "Linux attestation OWED" on the S1.6 runtime choice (Codex PR review: S1.6 had made a BINDING choice from a Mac-local disposable stand-in without the real target-host probe). The real non-root probe ran on `trade-core`: **7/8 fixed-path seams `PASSED_TARGET_HOST` on genuine kernel evidence** (`start_stop`, `cgroup_resource_isolation`, `network_denial`, `native_lib_loading`, `immutable_closure_persistence`, `failure_rollback_cleanup`, `pg_identity`=real disposable initdb cluster → 42501); `independent_postcheck` is DEFERRED by design in the applier receipt and earns PASS via a distinct verifier's clean residue sweep → `content_addressed_fixed_path` is **BINDING** on real target-host evidence; OCI stays `NON_SATISFIABLE_NON_ROOT`. Executing the probe for real surfaced that three as-designed primitives are blocked by the host policy `apparmor_restrict_unprivileged_userns=1` (Ubuntu 24.04; no `newuidmap`) — each was swapped to a real non-root primitive that preserves the seam's essential property (no forced PASS): network_denial `bwrap --unshare-net`→**seccomp** `SCMP_ACT_ERRNO(ENETUNREACH)` differential; cgroup OOM read-race fixed (`OOMPolicy=continue` + child-hog OOM-killed while main survives → real `oom_kill`); native_lib copy-a-system-lib→**compile a unique-soname `.so`** + maps-origin + callable symbol(=42), with a direct-load fallback since bwrap mount-isolation is AppArmor-blocked. Independent **E2** adversarial review (reproduced on trade-core) confirms all three are HONEST real-effect proofs — every fabrication/absent-mechanism/no-baseline path honestly DEFERs; prod PG :5432 untouched; zero residue after every run. Two honest closure obstacles recorded for follow-up: (a) `session_attempt_v1` is schema-pinned to S0.3 (const `AIML-S0.3-GOVERNANCE-ADOPTION`) so the durable-attempt record for S1.6B is `task_execution_admissions_v1`, not a literal `session_attempt_v1`; (b) governed `capture-command` env-strips `AIML_TARGET_HOST_PROBE`/`XDG_RUNTIME_DIR`, so it attests the source/structural layer (`LOCAL_REPRODUCIBLE`) — the real seams are `PLATFORM_OR_EXTERNAL_ATTESTED` via on-target run + distinct OPS on-host observation (design §3), a different assurance class. Nine authority grants remain false; no production PG/deploy/runtime/broker/order occurred; `source_adoption_only` unchanged. | Branch `agent/aiml-s1.6b-real-probe` — harness+3-seam-fix `e98d743fb`, E2-P3 cleanup `17f259dd8`; design `docs/execution_plan/ai_ml_landing/design/S1.6B-real-target-host-probe.md` §10; on-target pytest `tests/structure/test_agent_governance_target_host_probe_on_target.py` 5 passed (incl. explicit cgroup + native-lib PASS), Mac logic suite 64 passed; E2 verdict: HONEST real-effect proofs, no P0/P1, only P3 cosmetic (all fixed). Pending: exact-head PR → Linux CI → merge. |
| 2026-07-23 | S1.1-S1.6 | `S1_SOURCE_COMPLETE_ON_REVIEW_BRANCH`. All six Sprint-1 sessions are source-complete and committed on branch `agent/aiml-s1-landing` (atop main `5362fdd4b`). Each session passed its full per-session role chain (E2/E4/CC/E3/OPS/QA) with fix rounds, plus one cross-session adversarial review round — PA integration PASS, CC whole-body constitutional PASS, FA spec-compliance PASS. The digest-binding dependency chain is coherent and the frozen S0.3 classifier digest is byte-unchanged (`PROGRAM_ADOPTED` intact); the only frozen-surface edits were S1.2's legitimate terminal-sink CONTRACT_ONLY -> implemented flip and S1.5's matrix `adapter_binding_status` flip, both reality-reflecting with forge-resistance unchanged. Every S1 effect is disposable (DISPOSABLE_ONLY / DISPOSABLE_APPLY_ROLLBACK_POSTCHECK / TARGET_HOST_DISPOSABLE_RUNTIME_PROBE) and evidence class is `LOCAL_REPRODUCIBLE` (real 42501/28P01, os.replace/chmod, python3 -I on Mac dev); the platform-attested Linux trusted-host / CI test attestation is OWED and the S1 receipts are emitted disposably (not committed JSON like S0.3). The Sprint-1 exit `EFFECT_SEAMS_READY` is substantively composed by S1.5 (`effect_seams_ready_receipt` scope `S1.5_CONTRIBUTION`) + S1.6 (`learning_runtime_choice_receipt_v1`, final_choice `content_addressed_fixed_path`), but it is NOT yet a PM-declared ledger gate — it will be declared only after the exact-head merge and a green Linux CI/trusted-host attestation. Nine authority grants remain false; no production PG/deploy/runtime/broker/order occurred; `source_adoption_only` is unchanged. | Branch `agent/aiml-s1-landing` commits — S1.1 `3c0b7fb2f`, S1.2 `d12f84632`, S1.4 `7d0befd86`, S1.3 `08789982e`, S1.5 `0b2805a4d`, S1.6 `0e8e9fd9d`; per-session E2/E4/CC/E3/OPS/QA PASS + cross-session PA/CC/FA PASS; frozen S0.3 receipt digest `sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b` byte-unchanged; branch not yet merged/pushed — next step is the three-way sync (push -> exact-head PR -> Linux CI attestation -> exact-head merge -> ff-only), where the merge head and platform attestation land. |
| 2026-07-22 | S0.3 | `PROGRAM_ADOPTED` issued on Linux `trade-core` after the final P1 repairs and exact-generation adversarial closeout. A PR #110 P1 then correctly required independently verifiable durable finalization evidence; the producer-signed finalization attestation, trusted execution bundle and both SSHSIG sidecars were persisted and bound to the receipt/closure/source/GitHub digests. This closes S0 and opens `S1.1 ∥ S1.2 ∥ S1.4`; it does not claim runtime readiness or grant any runtime/effect/trading authority. | PR #106 merge `afa7eb2e97d6ab975709d4472b12f7397ee03bfb`; PR #107 merge `0cdd3537ead94675a4d0033df5bbcbf5d33b1b16`; PR #108 reviewed head `1a933fcc28e9f7341e023b5d401c479957c14c5f`, merge `fed223bebd278c50b0ab3330980e66441a30c9ed`; E2/E4/CC/E3/MIT/R4/QA PASS with no P0/P1/P2; Linux governed E4 `275/275`; finalizer closure `sha256:27f7b0041a418298ef49943f6f37283b603fce38f48f67f9a825f249f2615c63`; receipt `sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b`; persisted-signature regression `tests/structure/test_agent_governance_aiml_trusted_host.py` |
| 2026-07-21 | S0.3 | Source implemented + merged: scope/attempt/receipt/effect schemas (7), fail-closed `aiml_gate_receipt_validator.py`, Registry/router/closure integration, `terminal_receipt_sink_v1` contract-only (owner S1.2), and a strict GitHub repo-policy attestation contract. `SOURCE_READY`, not `PROGRAM_ADOPTED` — the receipt emission is a separate trusted-host step. | PR #104 merge `b945fe0f8db6bdf5f93657b3c404025ade4f2de4`, reviewed head `d6dd1f98470ddea7c1941fe572aa6f89071cf09d`; 8/8 required GitHub checks green; 7-role review (E2/E4/CC/E3/MIT/R4/QA) all PASS after E2-P1 (bind changed governance file) + E4-P1x3 (lock crown-jewel invariants) fixes were re-verified |
| 2026-07-21 | S0.3 | Independent Codex PR review found 3 verified P1 forge-resistance gaps on the adoption gate (reviewer bindings self-supplied not tied to authenticated fragments; no reviewed_head->merge_head ancestry proof; writer lease forced on the read-only finalization). All 3 fixed per PA minimum-coherent design and re-verified; the gate is now genuinely forge-resistant and (correctly) requires trusted-host attestation to mint `PROGRAM_ADOPTED`. | Hardening commit `d6dd1f98470ddea7c1941fe572aa6f89071cf09d`; re-review CC/E3/E2 PASS, E4 code-PASS-quality (CONCERNS only on Mac governed-attestation provenance -> Linux follow-up). See coverage debt below |
| 2026-07-21 | S0.2 | Accepted the advisory-serving source-policy authority after repairing and exactly rechecking three P1 blockers, source-policy QA acceptance, and final R4 cold review. Historical AMD bytes are unchanged. Effect is `NONE`; no ML5/ML6 implementation, runtime or Program adoption is claimed. | `docs/execution_plan/ai_ml_landing/receipts/S0.2-serving-authority-receipt-v1.json` (`sha256:0115dbd3dc62d84e183aae5a28cbfd252eb45ecee51a652d8a4a155f14dfb41a`); accepted head `f325b4dfdafd1979197c8a9e6450efeaf85e091c` |
| 2026-07-21 | S0.1 | Exact PR #100 publication and current three-source lineage reconciled; S0.1 is `DONE`. This immutable-lineage receipt grants no runtime, build or Program-adoption authority; S0.2 is next. | `docs/execution_plan/ai_ml_landing/receipts/S0.1-planning-documents-published-v1.json` (`sha256:8fc9417f984025deabdc1b83ace95921ccfff1acb26a1b29243fc0a0a5ba79ad`); current source `c2f5a2e26e422d56b8ec9b540d7f36bea9a0be54` |
| 2026-07-20 | PROGRAM | Four targeted correction-verification lenses accepted V2 after the no-candidate final-attestation branch was separated from trading attestation. Planning coverage is accepted; no implementation state advanced. | `ACCEPT_V2_FOR_PROGRAM_ADOPTION` |
| 2026-07-20 | S0.1 | Live read-only remote recheck found planning base `b486c071...` behind GitHub/local `origin/main=96d262450...` by seven commits; `TODO.md` overlaps. Integration is deferred to S0.1 and must preserve the unrelated IBKR delta. | `SOURCE_DRIFT_REQUIRES_CURRENT_HEAD_INTEGRATION` |
| 2026-07-20 | PROGRAM | Post-draft cold review rejected premature adoption/landing, coarse scope, impossible TTL overlap, effect-classification bypass and final-head drift; templates were reworked. No implementation state advanced. | `REWORKED_AWAITING_FINAL_ADVERSARIAL_ACCEPTANCE` |
| 2026-07-20 | PROGRAM | Initial V2 ledger designed in isolated planning worktree. No implementation, publication, runtime or effect occurred. | `PROGRAM_ADOPTION_REQUIRED` |

## S0.3 Trusted-Host Finalization (completed)

Linux `trade-core` completed the production finalization on 2026-07-22 against
reviewed head `1a933fcc28e9f7341e023b5d401c479957c14c5f` and merge head
`fed223bebd278c50b0ab3330980e66441a30c9ed`:

1. All seven mandatory roles (E2/E4/CC/E3/MIT/R4/QA) supplied authenticated
   PASS fragments for the same final generation; the final reviews had no
   P0/P1/P2 finding.
2. The trusted source verifier proved reviewed-head ancestry and exact blobs;
   the external verifier observed the live GitHub ruleset. Linux governed E4
   passed `275/275` after the two-line portable fixture-mode repair in PR #108.
3. The production finalizer returned `PASS` with no errors, closure digest
   `sha256:27f7b0041a418298ef49943f6f37283b603fce38f48f67f9a825f249f2615c63`,
   and issued `program_adoption_receipt_v1` digest
   `sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b`.
4. Independent verification is durable in repo: the exact producer-signed
   finalization statement is
   `S0.3-program-adoption-finalization-attestation-v1.json` + `.sig`, and its
   signed input index is `S0.3-trusted-execution-bundle-v1.json` + `.sig`.
   `test_persisted_s03_finalization_evidence_is_independently_verifiable`
   rechecks both SSHSIGs against the public key/fingerprint/identity/namespace
   pinned in the adopted `agent_governance_aiml_trusted_host.py`, and binds the
   receipt bytes/self-digest, closure digest, source heads, review generation,
   GitHub attestation and all-false authority limits.
5. The receipt has `source_adoption_only=true` and all nine authority grants
   false. The present ledger/docs commit is a post-emission projection and a
   descendant of the receipt's merge generation; it is deliberately not a
   recursive precondition of the already-issued receipt.

## Accepted Coverage Debt (S0.3 review, non-blocking)

Deferred P2 hardening from the 7-role review (fail-closed or forward-looking;
none affect the merged gate's forge-resistance):

- E2 P2: `validate_*` raise instead of return on malformed classification / deep
  graph (fail-closed in the wired path); `agent_governance_schema.py` not bound
  in the adoption governance manifest (host under same repo/CI protection).
- E3 P2: `GITHUB_SECRET_LIKE_RE` prefix-only + attestation-only scan; shared
  manifest path pattern weaker than `_s0_3_owned_path` (both non-exploitable).
- MIT P2: `landing_scope_v1` should bind `intent_position_effect_class` before
  the ML5 serving schema (not in the S0.3 bundle; owner S4/S5).
- QA P2: keep the receipt review-binding cross-check (now implemented via the
  enforced closure path in the hardening).
- R4 P3: the dependency-receipt schema's generic `uniqueItems` does not itself
  enforce unique `session_id`; the S0.3 validator/finalizer still requires the
  exact S0.1 and S0.2 dependency bindings, so this is not an adoption bypass.
