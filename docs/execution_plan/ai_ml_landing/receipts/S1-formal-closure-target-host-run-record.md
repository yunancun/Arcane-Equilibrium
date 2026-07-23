# S1 Formal Closure — Real Target-Host Effect Run Record (Wave C)

> **Superseded (2026-07-23, PR #114 findings fix).** This is the pre-fix Wave C run
> record. The three Codex findings added a structured `verifier_capture_digest` field
> to `target_host_effect_result_v1`, which changes `target_host_effect_receipt_digest`,
> so the `receipt_digest`/`choice`/`attempt` digests pinned below **no longer
> re-derive**. A fresh run record with the new field + a governed distinct-verifier
> `command_capture_v2` (now required by the closure) is produced by the S1-closure-fix
> runtime rerun on branch `agent/aiml-s1-closure-p1p2-fixes`. Treat the digests here as
> historical.

**Date**: 2026-07-23. **Host**: `trade-core` (Linux, non-root uid=1000). **Branch**:
`agent/aiml-s1-formal-closure`. **Effect class**:
`TARGET_HOST_DISPOSABLE_RUNTIME_PROBE`. **Evidence assurance**: real seam verdicts
are `PLATFORM_OR_EXTERNAL_ATTESTED` via on-host observation + a distinct verifier
(design §3); the embedded `command_capture_v2` is a **structural anchor**
(`structural_reference_only=true`) — the probe cannot be governed-captured because
`capture-command` intentionally env-strips `AIML_TARGET_HOST_PROBE` (fixed decision
#4, not weakened). A **fully-attested trusted PASS additionally requires the
operator SSHSIG** (operator-gated, §Pending).

## What ran

The real bounded probe was driven through the Wave-B1 apply orchestrator
`agent_governance_target_host_apply.apply_target_host_probe_effect` under an
**intent-derived** authorization gate (a validated
`target_host_disposable_runtime_probe_intent_v1` — NOT a bare user-set env var),
then a **distinct** verifier (`s1fc_independent_verifier` ≠ applier
`s1fc_apply_actor`) attached its own real on-host residue observation via
`attach_distinct_verifier_postcheck`.

## Authoritative result (from the persisted bound effect result)

| Field | Value |
|---|---|
| `effect_status` | `TARGET_HOST_DISPOSABLE_PROBE_PASS` |
| `adapter_id` | `target_host_disposable_runtime_probe_adapter_v1` |
| `receipt_digest` (dedicated result self-digest) | `sha256:e2b838e8123f6c56794dc636767f63a27215d306024d99c8070119c0858ad89a` |
| `choice_receipt_digest` = choice `self_digest` | `sha256:447ab474ff24897fbdef5e98decc3b2a2c7a061793d1c163c81250e297cf835b` |
| structural `command_capture_v2` anchor digest | `sha256:22b5a5e5eee3a952080e2b3350f3c3f4398e7d24da7e3bb3604ee926b4477f96` (`structural_reference_only=true`) |
| `selection.binding` | **`BINDING`** (after the distinct-verifier attach) |
| `selection.final_choice` | `content_addressed_fixed_path` |
| `selection.oci_selectable` | `false` (OCI every seam `NON_SATISFIABLE_NON_ROOT` — boundary-driven non-selection) |
| `evidence_class` | `PLATFORM_OR_EXTERNAL_ATTESTED` |
| `host_identity.observed_host` == `expected_host` | `trade-core` == `trade-core` (real `os.uname().nodename`, fail-closed on mismatch) |
| fixed-path seams | 8/8 `PASSED_TARGET_HOST` (start_stop, cgroup, network_denial=seccomp, native_lib=compiled-unique-soname, immutable_closure, failure_rollback=bundle-pinned, pg_identity=real disposable initdb → 42501, independent_postcheck via the distinct verifier) |

Validation: the strict effect lane
`validate_target_host_effect_result(..., require_success=True)` returned `[]`
(rejects a STRUCTURAL_ONLY / bare-digest receipt — this is a real attested PASS);
the central `validate_aiml_artifact` returned `[]` for both the applier and the
bound result.

## Boundary + cleanliness

Strictly non-root, user-scope only, disposable, under `/run/user/1000`; no
production PG/deploy/broker/order/live effect; prod PG `127.0.0.1:5432` untouched.
Complete teardown with an independent residue sweep: 0 real postmasters, 0
`aiml-probe*` user units, 0 throwaway dirs after the run. OCI is
`NON_SATISFIABLE_NON_ROOT` (no rootless OCI on-host; not selected).

## Durable governance chain (producer-generated, validator-passed)

| Artifact | Producer | Validator | Digest |
|---|---|---|---|
| `target_host_effect_result_v1` (bound) | `agent_governance_target_host_apply.apply_target_host_probe_effect` + `attach_distinct_verifier_postcheck` | `validate_target_host_effect_result` (strict, `require_success=True`) + central `validate_aiml_artifact` → both `[]` | `sha256:e2b838e8…858ad89a` |
| `learning_runtime_choice_receipt_target_host_v1` (embedded) | `build_target_host_choice_receipt` | central `validate_aiml_artifact` (structure-only branch) → `[]` | `sha256:447ab474…97cf835b` |
| `aiml_landing_session_attempt_v1` | `agent_governance_target_host_apply.build_target_host_landing_attempt` | central `validate_aiml_artifact` (additive S1+ branch; rejects the S0.* family) → `[]` | `sha256:5f174e05…2e0e191e`; `closure_binding.effect_receipt_digest` = the effect result above |

The producers + central validator are the Wave-A/B implementation (adversarially
reviewed: E2 HONEST/no-P0-P1, E3 security-cleared, E4 coverage-adequate). No
hand-assembled JSON substitutes any producer or validator.

**`closure_packet_v1`**: a fully-attested PASS closure cannot be produced/validated
offline — the standalone CLI performs structure/integrity checks only and cannot
authenticate PASS (CLAUDE.md Typed Authority Matrix). The `closure_binding` above
carries a placeholder `closure_packet_digest` until the trusted-host step (below)
mints the attested closure. The chain up to the durable attempt + validated
real-effect receipt is complete; the closure PASS is gated on §Pending item 1.

## Pending (operator-gated — required for a fully-attested `S1_CLOSED`)

1. **S1 target-host SSHSIG signer** public-key + fingerprint (the S1 signer
   profile consts are reserved placeholders; a real trusted-host signature over the
   evidence bundle — binding source head / host identity / intent digest / effect
   result / capture digest / cleanup postcheck / time / verifier identity — is the
   out-of-band operator step, exactly like S0.3's `aiml-trusted-finalize`).
2. **External S3 Object-Lock WORM** config for the S1.2A source adapter — endpoint
   + region + Object-Lock-enabled bucket + retention (COMPLIANCE for the terminal
   bucket) + a **non-secret** credential channel identifier (IAM role / short-lived
   STS / named profile — never a key).

Absent these, the honest terminal is
`S1_ENGINEERING_CLOSED_EXTERNAL_WORM_BINDING_PENDING`.
