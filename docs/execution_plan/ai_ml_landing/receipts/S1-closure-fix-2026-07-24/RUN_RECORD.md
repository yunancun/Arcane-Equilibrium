# S1 Formal Closure — Authenticated Target-Host Run Record

**Date**: 2026-07-24
**Host**: `trade-core` (Linux, non-root uid 1000)
**H_effect**: `f6e0099523de93e11986947bf673cea6e5209639`
**Branch / PR**: `agent/aiml-s1-closure-p1p2-fixes` / PR #115
**Effect class**: `TARGET_HOST_DISPOSABLE_RUNTIME_PROBE`

## Outcome

The fresh target-host effect, complete governance closure, and operator SSHSIG
all passed. The durable state emitted by the fixed finalizer is
`S1_CLOSURE_AUTHENTICATED_PENDING_MERGE`; `S1_CLOSED` is deliberately withheld
until PR #115 receives an exact-head Codex review, all required CI is green, and
that exact head is merged.

- S1.5 contribution: all six real disposable component classes were freshly
  rerun at the exact H_effect with byte-identical source/schema; each performed
  apply → exact rollback → independent postcheck; status `PASS`,
  digest `sha256:cb96671598707d4dd3ca6b4284106bf8b19baf4ff259e6c9a0bcdeca04ef7cdf`.
- S1.6 target-host effect: all eight fixed-path seams
  `PASSED_TARGET_HOST`; `binding=BINDING`;
  `final_choice=content_addressed_fixed_path`;
  effect digest `sha256:1a0fde065ae4b95bb390e66b65be472a6e560f8f3d76135be6bc0c7c2b25a91c`.
- Host identity: observed and expected host are both `trade-core`.
- Cleanup: zero unit, cgroup, netns, temporary-directory, or disposable-PG
  residue; production PostgreSQL `:5432` was not touched.
- Closure: `closure_packet_v1` trusted finalization `PASS`, no errors;
  closure digest
  `sha256:52842fdfe6237e25d939d738eb54c2a79fdca5c87ec2577da304b83127282180`.
- Operator authentication: the canonical trusted-execution bundle was signed
  through the current SSH agent under identity
  `aiml-s1-target-host-operator-v1` and namespace
  `arcane-equilibrium-aiml-s1-target-host`. Independent `ssh-keygen -Y verify`
  passed against fingerprint
  `SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ`.

## Causal execution

The run used a detached throwaway worktree at the exact committed H_effect;
the Linux runtime `main` checkout stayed clean and untouched.

1. A real S1.5 `effect_seams_ready_receipt_v1` was produced from the six
   committed disposable component-effect harnesses.
2. Linux emitted one exact typed intent. The operator key signed that
   intent/source head under the separate
   `arcane-equilibrium-aiml-s1-target-host-apply` namespace before any effect.
3. Before the effect, OPS node `ops_preflight` ran the exact signed observer
   command; its complete stdout is the load-bearing governed
   `command_capture_v2`. The same signed intent authorized the isolated
   `python3 -E` child executor. The parent process never opened
   `AIML_TARGET_HOST_PROBE`.
4. The child exercised start/stop, cgroup isolation, network denial,
   native-library loading, immutable closure persistence, rollback/cleanup, and
   real disposable-PG identity.
5. After the effect, distinct OPS node `ops_postcheck` performed the residue
   sweep inside its own exact signed observer command and produced a different
   governed capture. The closure cross-binds effect-result
   `verifier_capture_digest`, postcheck digest, capture `record_digest`, and the
   exact zero-residue stdout projection.
6. The finalizer retained the true historical PA/CC/E3 provider-call digests
   and timestamps, built a workflow wave that owns every mandatory reviewer
   fragment, and signed the complete DAG/closure packet. Closure freshness is
   evaluated at the bundle's signed `issued_at`, not at a caller-appended time.

The historical provider calls are not represented as fresh replays. Their
limitation is load-bearing in `review_provenance.json`; the current
artifact-only head still requires the separate exact-head Codex merge review.

## Adversarial closeout findings

The final whole-suite regression, a deliberately mistyped SHA, historical
receipt replay, and exact-head CI caught four
additional P1s before publication:

1. The direct-caller Context inventory bounded only the number of matches, not
   the byte length of each preview. A generated closure receipt could therefore
   inject a single 250 KB JSON line into every standard review Context and make
   `call_allowed=false`. Commit `43735ff3d` byte-bounds inline match previews
   while retaining `manifest_digest` and `text_digest` over the complete
   original bytes. The reproduced Context fell from 69,152 to 12,985 planned
   tokens and remained admissible.
2. The target-host driver accepted caller `--source-head` without comparing it
   to the worktree it executed. Commit `102b1bb85` requires an exact lowercase
   40-hex match to a completely clean target-host `HEAD` before any effect.
   Mismatch, tracked-dirty, untracked-dirty, abbreviated, and noncanonical
   negative tests all fail closed.
3. The finalizer persisted the run-start instant as `evaluated_at`, although
   the Context sources were materialized later. Commit `e6572b96e` moved the
   timestamp after trusted finalization; the later exact-head review correctly
   found that a caller-local timestamp still was not authenticated. The final
   repair in H_effect evaluates S1 at the SSHSIG-bound bundle `issued_at`.
4. The replay regression's original filename did not match the required
   governance CI glob, while the complete governance gate hit a hard five-
   minute ceiling and was cancelled. Commit `45a854fa6` places the regression
   under the required glob and locks a 10-minute job ceiling with a static
   contract test.

The exact-head adversarial review then found five further P1 forge paths, all
closed in source commit `f6e009952` with load-bearing negatives:

1. A caller-created checksum capsule could open the child gate. The child now
   requires the source-pinned operator SSHSIG over the exact intent/source
   head, and rejects a self-resealed root or launcher substitution.
2. A structurally governed but unrelated command could back the applier's host
   claim. The effect validator now requires the exact signed `ops_preflight`
   observer and complete safe-host stdout.
3. The residue claim was derived outside the verifier capture. The declared
   `ops_postcheck` command now performs the sweep itself, and closure validates
   its exact zero-residue stdout against the attached residue evidence.
4. The earlier caller-local replay time was not signed. The bundle's
   SSHSIG-bound `issued_at` is now the only S1 evaluation instant.
5. The effect receipt could substitute for reviewer evidence. Every mandatory
   non-OPS reviewer now cites the authenticated workflow wave that owns its
   exact fragment digest.

The earlier `6febd9d1e`, `45a854fa6`, and rejected mistyped-head generations
are superseded; none is the final S1 closure. Both S1.5 and S1.6 effects and
both operator signatures were freshly emitted at the H_effect above.

## Durable artifacts

- Producer inputs: `effect_seams_ready_receipt.json`, `intent.json`,
  `operator_authorization.json` plus `.sig`,
  `applier_capture.json`, `preflight_capture.json`,
  `preflight_observation.json`,
  `applier_effect_result.json`, `verifier_capture.json`,
  `upgraded_effect_result.json`, `residue_observation.json`,
  `final_residue_sweep.json`, `host_identity.json`, `run_meta.json`, and
  `run_summary.json`.
- Governance: `review_provenance.json`,
  `S1-closure-context-artifact-v1.json`,
  `S1-closure-workflow-call-manifest-v1.json`,
  `S1-closure-workflow-wave-record-v1.json`, and
  `S1-closure-packet-v1.json`.
- Authentication and landing:
  `S1-closure-trusted-execution-bundle-v1.json` plus `.sig`,
  `S1-landing-session-attempt-v1.json`, and
  `S1-closure-finalization-result-v1.json`.

Key finalization digests:

- workflow wave:
  `sha256:e43edb47e809243282bebb87a95289f453181f0d5f8d3528b681f3c346300f68`
- trusted bundle:
  `sha256:81860f0dfd78954847209fcb05db317bf8063742c7d7b7accd5dbd4bad521d6c`
- signature bytes:
  `sha256:ee455990a1dd6247f547296bc1803e755d03031352c037d71b073fdc4d16b8e7`
- landing attempt:
  `sha256:74b87c966c041a6c569f5a55c10a8f2a71c9e7f0a11930646ce4e6cd23befa35`
- finalization:
  `sha256:8f26a57373faa5a2b20ed566837736e6ce6e3189d6e117b5112edf8b9f9cff71`

## Boundary and final transition

All nine AIML authority grants remain false. This work created no production
runtime, build, PostgreSQL, migration, deploy, ML5/ML6, broker, order, or live
authority. External S3 Object-Lock execution remains S8.6 and is not an S1
blocker.

The only remaining transition is repository publication: exact-head review,
required CI, PR #115 merge, and three-way source synchronization. After those
checks pass, the ledger may move from
`S1_CLOSURE_AUTHENTICATED_PENDING_MERGE` to `S1_CLOSED` and open the S2 ready
pool `S2.0 ∥ S2.2A ∥ S2.3`.
