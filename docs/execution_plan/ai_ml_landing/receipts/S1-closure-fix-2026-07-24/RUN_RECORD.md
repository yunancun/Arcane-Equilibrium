# S1 Formal Closure — Authenticated Target-Host Run Record

**Date**: 2026-07-24
**Host**: `trade-core` (Linux, non-root uid 1000)
**H_effect**: `45a854fa6638aa0be677a2b705f42fe8f417ac95`
**Branch / PR**: `agent/aiml-s1-closure-p1p2-fixes` / PR #115
**Effect class**: `TARGET_HOST_DISPOSABLE_RUNTIME_PROBE`

## Outcome

The fresh target-host effect, complete governance closure, and operator SSHSIG
all passed. The durable state emitted by the fixed finalizer is
`S1_CLOSURE_AUTHENTICATED_PENDING_MERGE`; `S1_CLOSED` is deliberately withheld
until PR #115 receives an exact-head Codex review, all required CI is green, and
that exact head is merged.

- S1.5 contribution: the still-fresh receipt for six real disposable component
  classes was revalidated against byte-identical source/schema; each had
  performed apply → exact rollback → independent postcheck; status `PASS`,
  digest `sha256:ab63d9db3682e94be195446e4e4d9a586d1ef327427547d88347d934914b140f`.
- S1.6 target-host effect: all eight fixed-path seams
  `PASSED_TARGET_HOST`; `binding=BINDING`;
  `final_choice=content_addressed_fixed_path`;
  effect digest `sha256:9f8f40b15598822544f0dd8618429ae3c6c2ac2b153d8b3acd70094b73fffd99`.
- Host identity: observed and expected host are both `trade-core`.
- Cleanup: zero unit, cgroup, netns, temporary-directory, or disposable-PG
  residue; production PostgreSQL `:5432` was not touched.
- Closure: `closure_packet_v1` trusted finalization `PASS`, no errors;
  closure digest
  `sha256:eeef47cca1bcbfd44fb917759539b6afd06610669ec65a3be9e30b27a1f46de1`.
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
2. Before the effect, OPS node `ops_preflight` produced its own governed
   `command_capture_v2`.
3. The typed intent authorized the isolated `python3 -E` child executor. The
   parent process never opened `AIML_TARGET_HOST_PROBE`.
4. The child exercised start/stop, cgroup isolation, network denial,
   native-library loading, immutable closure persistence, rollback/cleanup, and
   real disposable-PG identity.
5. After the effect, distinct OPS node `ops_postcheck` performed the residue
   sweep and produced a different governed capture. The closure cross-binds
   effect-result `verifier_capture_digest`, postcheck digest, and capture
   `record_digest`.
6. The finalizer retained the true historical PA/CC/E3 provider-call digests
   and timestamps, used the fresh preflight/postcheck capture timestamps, built
   the complete workflow DAG and `closure_packet_v1`, signed its exact
   trusted-execution bundle, and ran the fixed S1 trusted-host validator.

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
   the Context sources were materialized later. A PASS result could therefore
   fail when replayed at its own durable time. Commit `e6572b96e` captures the
   receipt timestamp only after trusted finalization and adds a load-bearing
   ordering regression. Both immediate trusted-host validation and replay at
   the persisted `evaluated_at` now pass.
4. The replay regression's original filename did not match the required
   governance CI glob, while the complete governance gate hit a hard five-
   minute ceiling and was cancelled. Commit `45a854fa6` places the regression
   under the required glob and locks a 10-minute job ceiling with a static
   contract test.

The earlier `6febd9d1e` signed generation and the rejected mistyped-head attempt
are superseded; neither is the final S1 closure. The exact-head S1.6 producer
effect and operator signature were rerun after all four P1 fixes at the
H_effect above; the still-fresh S1.5 receipt was independently revalidated
against unchanged source/schema before consumption.

## Durable artifacts

- Producer inputs: `effect_seams_ready_receipt.json`, `intent.json`,
  `applier_capture.json`, `preflight_capture.json`,
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
  `sha256:14b2bbf4725293e030264e2dd92a3534bc7a667848fbfce5e8ddf70d24ffb93d`
- trusted bundle:
  `sha256:c9c7756940fb2493c14a6e45261b236fcb40c1e72697696e1172cb4d8cefe359`
- signature bytes:
  `sha256:3ab69e6211127937441ab8d574bf78142ac6c551b6968020b5dc1210d0cf0c19`
- landing attempt:
  `sha256:e2522fe13952fa4203fa3ecc9609cbce3db04bb1e01a16daa9753c0e3ed0243a`
- finalization:
  `sha256:ed6635c44cae7e7e758e4dfa419e505ebfe111158abed48280ae7450b80b58a0`

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
