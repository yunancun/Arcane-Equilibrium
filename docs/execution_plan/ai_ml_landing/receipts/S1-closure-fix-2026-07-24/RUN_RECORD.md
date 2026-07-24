# S1 Formal Closure — Authenticated Target-Host Run Record

**Date**: 2026-07-24
**Host**: `trade-core` (Linux, non-root uid 1000)
**H_effect**: `6e1ea957af35544a844f704978366d11aa6c2364`
**Branch / PR**: `agent/aiml-s1-closure-p1p2-fixes` / PR #115
**Effect class**: `TARGET_HOST_DISPOSABLE_RUNTIME_PROBE`

## Outcome

The fresh target-host effect, complete governance closure, and operator SSHSIG
all passed. The durable state emitted by the fixed finalizer is
`S1_CLOSURE_AUTHENTICATED_PENDING_MERGE`; at emission time `S1_CLOSED` was
deliberately withheld until exact-head review, green CI and merge. Those later
publication gates subsequently passed, so the composite Sprint state is now
`S1_CLOSED`; see “Publication closeout” below. The signed finalization bytes
remain immutable.

- S1.5 contribution: all six real disposable component classes were freshly
  rerun at the exact H_effect with byte-identical source/schema; each performed
  apply → exact rollback → independent postcheck; status `PASS`,
  digest `sha256:19498ba4303df77eb102e259526ec04a19c665673716280818ec5d0103b60a37`.
- S1.6 target-host effect: all eight fixed-path seams
  `PASSED_TARGET_HOST`; `binding=BINDING`;
  `final_choice=content_addressed_fixed_path`;
  effect digest `sha256:0a0d050b8b555b1f8d627937c52a91a7bb0c132364fa8f78b0ccd640b64a89bb`.
- Host identity: observed and expected host are both `trade-core`.
- Cleanup: zero unit, cgroup, netns, temporary-directory, or disposable-PG
  residue; production PostgreSQL `:5432` was not touched.
- Closure: `closure_packet_v1` trusted finalization `PASS`, no errors;
  closure digest
  `sha256:e110598b83123f60881e982156913944de37bdf1bab1fdaabdc31c2b567e3dbc`.
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
receipt replay, and exact-head CI caught five
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
5. The exact-head Linux gate then proved that the inline Context harness itself
   exceeded Linux `ARG_MAX` when passed through `node -e`; 1,091 tests passed
   before that process failed to start. Commit `6e1ea957a` feeds the same large
   generated harness through stdin, adds the Linux-safe regression path, and
   raises the complete governance job ceiling from 10 to 20 minutes. This
   changes no production workflow or authority.

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

The earlier `6febd9d1e`, `45a854fa6`, `f6e009952`, and rejected mistyped-head
closure generations are superseded; none is the final S1 closure. Both S1.5
and S1.6 effects and both operator signatures were freshly emitted at the
H_effect above.

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
  `sha256:cbc5d36984d0edbabc3a112c0c36f86f333a24acbf16e45c5c73a2efa4383a42`
- trusted bundle:
  `sha256:cdbed2fcacfa26f93d5c6a0a8e36f604df8b6fb28bbf5793d9a0baceea9bd0b7`
- signature bytes:
  `sha256:bd84abf880954177c6d23367ac2c6ca907003eaad22e044ad0bb16193727635e`
- landing attempt:
  `sha256:b572eb279056b4647c93cdad5333de9ff9ecaaeb559e8b181e6e73538a429e1e`
- finalization:
  `sha256:68bbced3a100c9e52e9f0845e600cce0552b1b67cf3a11d925f4b537dee86d6c`

## Publication closeout

All nine AIML authority grants remain false. This work created no production
runtime, build, PostgreSQL, migration, deploy, ML5/ML6, broker, order, or live
authority. External S3 Object-Lock execution remains S8.6 and is not an S1
blocker.

Repository publication completed after this immutable signed generation:

- Direct Codex reviewed exact PR head
  `da8e54148a60fc7be38fe5844cf85b28b293a044` and found
  P0/P1/P2=`0/0/0`.
- Every exact-head CI and CodeQL job passed; the repaired development-agent
  governance gate completed in 8m27s, schema-consumer in 6m30s, and the IBKR
  lane in 6m9s. Open code-scanning alerts and unresolved review threads were
  both zero.
- PR #115 merged with exact-head matching as
  `22876b16d3b00fcaafa4f2f46ae02b1c08c60b3b`.

The signed finalization artifact correctly remains
`S1_CLOSURE_AUTHENTICATED_PENDING_MERGE`: it recorded the state at emission
time and is not rewritten after signing. The later exact-head review, green CI
and merge evidence satisfy that artifact's declared publication predicate, so
the composite Sprint state is now **`S1_CLOSED`** and the S2 ready pool is
`S2.0 ∥ S2.2A ∥ S2.3`.
