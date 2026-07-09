# AI/ML ALR Work Queue

This queue is compact by design. Each row must be actionable without rereading
the full report body. All rows have boundary label `SOURCE_ONLY_OFFLINE_P0_P1`:
source CLIs, tests, reports, and artifacts only.

| ID | P | Status | Owner Chain | Acceptance | Latest Evidence | Next Action |
|---|---:|---|---|---|---|---|
| `P0-AIML-ALR-BOUNDARY-PACKET` | 0 | `ACTIVE` | `PM -> CC -> FA -> PA -> PM` | `SOURCE_ONLY_OFFLINE_P0_P1`; write `boundary_packet.md` in this stub directory as PM boundary packet only. It must pin scanner=evidence, ALR P0 is not ADR-0035 online update, P0 source-only denials, proof taxonomy, root TODO location decision, fixed ADR/AMD proposal text, and stop states. Do not write `docs/adr/` or any AMD/governance mainline file unless a future explicit PM scope authorizes that target. P0/P1 done means source CLIs/tests/artifacts only; exchange-facing or order-capable outcome is P2+ exact-scope `PM -> E3 -> BB`. | 2026-07-09 PM ALR plan plus adversarial audit. | Write and commit `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/boundary_packet.md`, or stop `STOP_BOUNDARY_PACKET_MISSING`. |
| `P0-AIML-ALR-CONTROLLER-CONTRACTS` | 0 | `WAITING_BOUNDARY` | `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` | `SOURCE_ONLY_OFFLINE_P0_P1`; define `alr_work_item_v1`, `alr_effect_review_v1`, and `alr_loop_state_packet_v1`; selector emits first unblocked row; tests cover `ADVANCED`, `ADVANCED_WITH_CONCERNS`, `DEFER_EVIDENCE`, `ROTATED`, `STOP_NO_EDGE`, `STOP_RETENTION_RISK`, and `BLOCKED_BOUNDARY`. | 2026-07-06 autonomous loop state-packet pattern. | Implement after boundary packet. |
| `P0-AIML-ALR-LEARNING-TARGET-ARBITER` | 0 | `WAITING_CONTROLLER` | `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` | `SOURCE_ONLY_OFFLINE_P0_P1`; single-shot CLI emits `learning_target_runtime_v1` under explicit `--out`; input snapshot manifest is hash-bound; stale `_latest` is rejected; scanner/no-order/artifact-count evidence cannot become proof; objective is `expected_value_of_information`. | 2026-07-09 PM ALR P0-A plan, QC audit. | Implement after controller contracts. |
| `P0-AIML-ALR-OUTCOME-BRIDGE` | 0 | `WAITING_ARBITER` | `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` | `SOURCE_ONLY_OFFLINE_P0_P1`; consumes only `proof_packet_v1` and `reward_ledger_v1`; missing candidate-matched orders/fills, actual fees/slippage/funding, reconstruction, controls, proof-exclusion pass, repeat evidence, or OOS evidence returns `DEFER_EVIDENCE`. | 2026-07-09 PM ALR P0-B plan, QC audit. | Implement after arbiter. |
| `P0-AIML-ALR-RETENTION-GUARDIAN-DRY-RUN` | 0 | `WAITING_CONTROLLER` | `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` | `SOURCE_ONLY_OFFLINE_P0_P1`; emits `retention_guardian_dry_run_v1`; transitive reference graph is hash-bound; proof/dispute/audit/lineage/negative examples are protected; unknown refs fail closed; no delete, move, chmod, symlink, PG, cron, apply, or prune wrapper. | 2026-07-09 PM ALR P0-C plan, MIT audit. | Implement after controller contracts, or in parallel only with disjoint files. |
| `P1-AIML-ALR-LOCAL-RUNNER` | 1 | `DEFERRED_P0` | `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` | `SOURCE_ONLY_OFFLINE_P0_P1`; explicit foreground helper composes P0 CLIs and emits state packets; no cron/daemon/launchd/systemd/sidecar/IPC/PG/runtime. | 2026-07-09 PM ALR P1-A plan. | Defer until P0 rows are green. |
| `P1-AIML-ALR-PERSISTENCE-DESIGN` | 1 | `DEFERRED_P0` | `PM -> CC -> FA -> PA -> PM` | `SOURCE_ONLY_OFFLINE_P0_P1`; ADR/AMD/spec only; no migration creation/apply/backfill; includes V### reservation, rollback, Linux PG dry-run plan, and append-only provenance contract. | 2026-07-09 PM ALR P1-B plan. | Defer until P0 rows are green. |
| `P1-AIML-ALR-STAT-SELECTOR-BASELINE` | 1 | `DEFERRED_P0` | `PM -> QC -> MIT -> AI-E -> PM`, then implementation chain | `SOURCE_ONLY_OFFLINE_P0_P1`; offline deterministic/statistical selector with frozen universe, pre-registered split, retained non-selected candidates, matched controls/negative cells, regime labels, walk-forward/OOS separation, uncertainty, and interpretable ranking. No LLM authority, RL, streaming update, serving promotion, or runtime mutation. | 2026-07-09 AI-E and QC audits. | Defer until P0 contracts and proof bridge are green. |

Do not use the current trading P0 candidate context, standing Demo authorization,
prior no-order public GET approval, prior BB exact-scope approval, operator
review-ready artifacts, or cached exchange credentials as authorization for
these AI/ML rows.

## Loop Selection Rule

Select the first row whose status is `ACTIVE`, then the first row whose waiting
condition is satisfied. Implement one row per iteration, write effect review and
state packet, make a narrow green checkpoint commit, then re-read this queue and
continue until P0 rows are done or a stop state fires.
