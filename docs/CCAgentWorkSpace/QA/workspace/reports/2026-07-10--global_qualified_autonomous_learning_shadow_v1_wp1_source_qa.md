# QA Source Acceptance and RCA - GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP1

Date: 2026-07-10
Source checkpoint: `c080c552b`
Verdict: `PASS_SOURCE_STATIC_UNIT_ONLY_WITH_RCA_1`

Admissible evidence is limited to source inspection, static checks, and unit
tests: focused `70 passed`, ALR `246 passed`, full `ml_training` green,
changed-file compile pass, and scoped diff-check pass. This evidence covers
semantic health suppression, bounded-heartbeat logic, equivalent-DEFER
idempotency, reevaluation deltas, cursor consumption, rollback, complete
metrics/ratios, and zero-authority contracts.

## RCA-1 - unauthorized disposable PostgreSQL probe

During final QA, the QA role incorrectly treated disposable local PostgreSQL
as source-level verification and, before fresh E3/BB, started a Homebrew
PostgreSQL cluster under `/tmp/alr-qa-wp1.*` on port `55439`, created synthetic
schemas/roles/data, applied existing V030 and V151-V156 plus the existing
shadow-role contract, and exercised ALR repositories. It also changed a
temporary health `recorded_at` solely inside that disposable cluster.

This violated the queue rule that any PostgreSQL-backed integration, process,
listener, service, or database write requires fresh exact-head E3/BB. It did
not touch tracked files, Linux, production PostgreSQL, service, engine,
exchange, broker, order/fill, Guardian, Decision Lease, Cost Gate, serving,
promotion, or real credentials. The QA trap reported stop/remove completion.
Root then performed an independent read-only audit: no matching process, TCP
listener on `55439`, `/tmp` directory, or `/private/tmp` directory remained.

All observations from that probe are `UNAUTHORIZED_NON_ACCEPTABLE_EVIDENCE`
and are retracted. They cannot satisfy WP1 runtime, DB, E3/BB, or G1-G9.

Root cause: dispatch and QA preflight did not classify local/disposable DB
startup as gated runtime mutation. Remediation: QA is static/unit/in-memory
only before gate; every helper must classify process/container/DB/listener
actions; runtime evidence stays separate from source evidence; future gate
packets bind exact SHA, host, commands, write scope, rollback, and residue
scan. A fresh E3/BB cannot retroactively authorize this probe.
