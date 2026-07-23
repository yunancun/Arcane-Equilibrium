# S1 Formal-Closure Fix — Real Target-Host Effect Run Record

**Date**: 2026-07-24 · **Host**: `trade-core` (Linux, non-root uid=1000) ·
**Source head (H_effect)**: `7fa7ce05ec77edd6dc6457e199f3415497b95b0c` ·
**Branch**: `agent/aiml-s1-closure-p1p2-fixes` · **Effect class**:
`TARGET_HOST_DISPOSABLE_RUNTIME_PROBE`.

This run exercises the **PR #114 findings-fix** generation end-to-end on the real
target host: the isolated `python3 -E` child-executor authorization path (P1 #2),
the distinct-verifier governed `command_capture_v2` postcheck binding (P1 #1), and
the reproducible driver `helper_scripts/maintenance_scripts/aiml_s1_closure_target_host_run.py`.
It was run from a throwaway detached `git worktree` at the exact committed head — the
runtime `main` checkout was never touched.

## What ran

`aiml_s1_closure_target_host_run.py` built an admitted typed
`target_host_disposable_runtime_probe_intent_v1` (fresh clock, real `self_digest`,
`expected_host=trade-core`, throwaway root under `$XDG_RUNTIME_DIR`), then:

1. `apply_target_host_probe_effect` (**real** runner) → the isolated `python3 -E`
   child (sanitized allowlist env, no gate) validated the intent-derived
   authorization capsule and opened `AIML_TARGET_HOST_PROBE` **only in its own env**,
   ran `run_target_host_probe`, and returned canonical JSON — the parent process
   never held the gate.
2. A **distinct** OPS verifier (`s1fc_independent_verifier` ≠ applier
   `s1fc_apply_actor`) ran a real on-host residue sweep (`independent_postcheck_on_host`)
   and produced a **real governed** `command_capture_v2` via the OPS `capture-command`
   path.
3. `attach_distinct_verifier_postcheck` upgraded the effect result to **BINDING**,
   carrying the structured `verifier_capture_digest`.

## Result — all 8 fixed-path seams PASSED_TARGET_HOST

| Seam | Verdict |
|---|---|
| start_stop | `PASSED_TARGET_HOST` |
| cgroup_resource_isolation | `PASSED_TARGET_HOST` |
| network_denial | `PASSED_TARGET_HOST` |
| native_lib_loading | `PASSED_TARGET_HOST` |
| immutable_closure_persistence | `PASSED_TARGET_HOST` |
| failure_rollback_cleanup | `PASSED_TARGET_HOST` |
| pg_identity | `PASSED_TARGET_HOST` (real disposable initdb cluster → 42501 SET ROLE denial) |
| independent_postcheck | `PASSED_TARGET_HOST` (distinct verifier clean residue sweep) |

- `effect_status` = `TARGET_HOST_DISPOSABLE_PROBE_PASS`; `binding` = **`BINDING`**;
  `final_choice` = `content_addressed_fixed_path`; OCI stays `NON_SATISFIABLE_NON_ROOT`.
- `observed_host` == `expected_host` == `trade-core`.
- **Zero residue**: no `aiml-probe*` / `aiml_s1fc_*` / `aiml_s16b_pg_*` units or dirs
  after the run; the disposable cluster was socket-only (`listen_addresses=''`),
  **production PG `127.0.0.1:5432` untouched**.
- Nine AIML authorities remain false; no production PG write, deploy, broker, order,
  or live effect. `source_adoption_only` unchanged.

## Persisted producer artifacts (this directory)

`intent.json`, `applier_effect_result.json`, `upgraded_effect_result.json`,
`applier_capture.json`, `verifier_capture.json`, `residue_observation.json`,
`final_residue_sweep.json`, `host_identity.json`, `run_meta.json`,
`run_summary.json`, plus the reconstructed `closure_binding.json` and the offline
`closure_verification.json`.

Key digests:
- effect result `receipt_digest`: `sha256:00e7fedb49cc0b2be2c7edbad5d67033b12b7fa71671f6e43ce48a0fe58a85e6`
- structured `verifier_capture_digest` == the verifier `command_capture_v2` `record_digest`
  (bound three ways: effect result ↔ ops_postcheck ↔ capture — see `closure_binding.json`).

## Offline mechanical re-verification (Mac, `closure_verification.json`)

Re-running the offline validators on the portable artifacts:
`validate_target_host_effect_result(require_success=True)` = **PASS**;
`validate_governed_command_capture(verifier_capture)` = **PASS**;
`validate_target_host_effect_binding(...)` = **PASS**. Per CLAUDE.md, offline
structural acceptance is **not** authentication — a fully-attested closure PASS
additionally requires the operator out-of-band SSHSIG below.

## Remaining gate — one operator out-of-band signing action

The only step left for `S1_CLOSED` is the operator SSHSIG over the trusted
execution bundle, using the **existing S0.3 signer key** (private key on neither
Mac nor `trade-core`; no new key). Precise action:

- Build a `trusted_execution_bundle_v1` (fresh `issued_at`/`expires_at` within the
  15-minute TTL) with **one entry** of kind `effect_adapter_result_v1`,
  `subject_digest` = `artifact_digest` =
  `sha256:00e7fedb49cc0b2be2c7edbad5d67033b12b7fa71671f6e43ce48a0fe58a85e6`, under
  `signer_identity=aiml-s1-target-host-operator-v1`,
  `signature_namespace=arcane-equilibrium-aiml-s1-target-host`,
  `signer_fingerprint=SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ` (the S0.3
  trust root), binding the task/context/dag digests.
- Sign its canonical bytes with the S0.3 private key:
  `ssh-keygen -Y sign -f <s0.3-private-key> -n arcane-equilibrium-aiml-s1-target-host`.
- Commit `S1-closure-fix-trusted-execution-bundle-v1.json` + `.sig` here; then the
  closure `closure_packet_v1` PASS is authenticated and S1 reaches `S1_CLOSED`.

Until then the honest terminal is **`BLOCKED_OPERATOR_SIGNING_ACTION`**: all internal
work, the real effect, and all artifacts are complete; only the existing private
key's out-of-band signature remains.
