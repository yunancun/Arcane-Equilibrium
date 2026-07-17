# Public history rewrite attestation

Date: 2026-07-17

## Scope

The public repository history was rewritten under an explicit, bounded
maintenance window. The rewrite removed the tracked database artifacts
`backups/trading_ai_pre_phase0a_20260404_180411.dump` and `.coverage` from all
reachable history and replaced credential-bearing DSNs and provider-token
shapes with inert redactions.

The rewritten public refs immediately before this attestation were:

- `main`: `e3c9fcddf868f1b8a4b734b89ffcf41ac3e948d9`
- `agent/ibkr-w6-s1-contract-details`: `4f646652c72040017487a46b12d1a7a9992ee304`
- `agent/p0c-public-only-runtime-profile-v1`: `1422db64561c73b35eb709ee7b30b02a5715dcb0`
- `gui-baseline-2026-07-09`: `03d283436d5d25e58c43a1d8d4e5cfe588bddb74`

## Recovery and protection

Before mutation, an owner-only complete four-ref Git bundle was created and
verified. Its SHA-256 is
`bd207920de2fad05b2e08c8302c4066137e1ff51e06921035aa57f712beb7cce`.
The bundle and exact pre-rewrite ref/ruleset snapshots are outside the public
workspace with owner-only permissions and no configured remote.

The branch and tag rulesets were disabled only for their exact ref update
windows and restored in a failure-safe finalizer. Post-window verification
showed active enforcement and zero bypass actors.

## Verification

- Native public-repository gate: all four rewritten refs, empty allowlist,
  zero findings.
- Gitleaks: 5,238 reachable commits and 165.82 MB scanned, zero findings after
  recording 49 exact historical `generic-api-key` false-positive fingerprints.
  Those fingerprints were individually reviewed as inert test values, hash
  prefixes, idempotency keys, or prose tokens; no rule-wide suppression exists.
- Functional regression: 810 passed, 1 skipped, 4 expected failures; adjacent
  isolated package: 22 passed.
- Affected Rust regression: 2 passed, 4,682 filtered out.
- Applied migration checksum manifest: current-tree validation passed. The
  one-time force-push diff comparison correctly failed closed because the old
  and rewritten histories have no merge base; this ordinary descendant PR
  establishes the new hosted-CI lineage without changing migration bytes.

## Effect boundary

This operation changed public Git source history and repository governance
only. It did not build, restart, or deploy services; mutate runtime, database,
broker, credential slots, environment, or risk configuration; or grant order
authority.

GitHub pull-request refs, forks, caches, and third-party clones are outside Git
ref rewrite authority and require provider/owner follow-up where applicable.
