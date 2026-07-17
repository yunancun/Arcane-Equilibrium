# Public repository hardening record

Date: 2026-07-17

## Confirmed exposure and evidence boundary

The pre-rewrite public graph contains a PostgreSQL dump at
`backups/trading_ai_pre_phase0a_20260404_180411.dump` and a tracked SQLite
coverage database at `.coverage`. The dump contains paper-trading, order,
runtime, audit, and strategy metadata. Repository scans did not confirm a
private key or production credential DSN. They did identify a historical
Anthropic-shaped credential candidate, but a source scan cannot determine
whether it was live or has been revoked. Do not reproduce its value or prefix.
Absence of another finding is not proof that a third party never copied public
history.

History rewriting cannot recall existing clones. GitHub pull-request refs and
cached commit views require a GitHub Support cleanup request after controlled
refs are rewritten.

## Status and closure conditions

| Surface | Current evidence | Closure condition |
| --- | --- | --- |
| Public history | The dump and `.coverage` remain reachable before rewrite; current pre-rewrite tags have not passed the exact-ref gate. | Rewrite controlled refs, remove both paths, apply replacements, and obtain a zero-finding complete ref inventory. |
| Hygiene workflow | The files and tests are remediation candidates in this change, not yet proof of enforcement on `main`. | Merge bootstrap, then record a successful `public repository hygiene gate` run on `main`. The workflow covers `pull_request_target`, pushes to `main`, and the weekly schedule, not every push. |
| CodeQL | Source fixes and proposed dispositions exist; provider closure is pending. | GitHub analyzes merged `main`; resolve or individually dismiss each alert with its evidence. |
| Provider credential | Validity and revocation of the Anthropic-shaped historical candidate are unknown. | The credential owner rotates or revokes it and records provider-side confirmation; until then status is `provider_credential_revocation_pending`. |
| GitHub cached history | A ref rewrite cannot remove pull-request refs, cached views, or server-held unreachable objects. | GitHub Support confirms cleanup; until then status is `external_cleanup_pending`. |
| Owner account | Hardware-key enrollment, active-session review, and PAT inventory/scope/revocation have not been evidenced by this repository audit. | The account owner completes these checks in GitHub and records evidence without copying credential material. |
| Human review | No independent second trusted reviewer has been evidenced. | Add a real second reviewer and obtain review; do not invent an identity or claim CODEOWNERS alone is approval. |
| Runtime | Source state and source checkout hashes do not attest a deployed process. | Use a separately authorized runtime attestation; source sync must not rebuild, restart, access PostgreSQL, or contact a broker. |

## Source controls

After bootstrap is merged and its first `main` run succeeds:

- `public_repo_security_gate.py` scans complete tracked trees, every commit in a
  proposed range, the staged index, or an exact ref inventory. It fails closed
  when the requested inventory is incomplete.
- The separate workflow's stable job name is `public repository hygiene gate`.
  The job is unconditional within that workflow and checks an exact untrusted PR
  head using the trusted base scanner and allowlist; the workflow itself is only
  triggered by `pull_request_target`, pushes to `main`, and the weekly schedule.
- The Git hook runs the native gate before optional Gitleaks defense in depth;
  it is a local control, not proof that every contributor installed it.
- `public_repo_history_replacements.txt` is the versioned filter-repo content
  policy. History rewriting must also remove both database paths with
  `--invert-paths`; the replacement file is not a substitute for path removal.

### Temporary pre-rewrite allowlist

After bootstrap, `.github/public-repo-security-allowlist.json` serves as a
temporary pre-rewrite bridge, not a permanent exception registry. Each entry is
limited to one exact finding fingerprint, rule, and literal path, with an
accountable owner, reason, and ISO expiry date. Invalid, expired, duplicate,
unused, or scope-mismatched entries fail closed. Pull requests use both the
scanner and allowlist from the trusted base checkout; an untrusted head cannot
select its own pair.

The allowlist and its scanner bypass mechanism MUST be removed in the same change as the history rewrite.
A rewritten graph is not clean while any bridge entry or suppression mechanism
remains.

## CodeQL disposition contract

The pre-change inventory contains 88 alerts. The following entries are proposed
remediation or disposition targets, not current provider-confirmed closure.
After a new GitHub analysis of merged `main`, close alerts one by one; no
rule-wide blanket dismissal is allowed.

- Fix in source: 1-35, 41-42, 47, 58, and 78-88.
- `used in tests`: 39-40, 43-46, 48, and 51-56. These are synthetic fixtures or
  assertion-only paths and require the specific source-to-sink note recorded by
  the security review.
- `false positive`: 36-38, 49, 57, and 59-77. These are protocol HMACs,
  non-authentication fingerprints, booleans, paths, fixed metadata, or
  credential variable names; each dismissal requires its individual evidence.
- `won't fix`: 50 only. Linux runtime intentionally consumes owner-only local
  plaintext credential files. The accepted controls are canonical-root and
  filename allowlists, atomic `0600` creation/replacement, `0700` directories,
  symlink rejection, fail-closed permission handling, and no raw value or key
  hint in logs. Residual risk is compromise of the local runtime user or root.

CodeQL closure remains pending until provider analysis of merged `main`; this
document cannot establish that a source fix closed an alert.

## Rewrite and publication invariants

1. Freeze merges and capture exact old branch/tag SHAs plus the active ruleset.
2. Prepare a fresh isolated mirror after the security feature is merged.
3. Remove the two database paths and apply the versioned replacement file.
4. Scan the exact rewritten branch/tag inventory; any finding or missing ref is
   a hard stop.
5. Keep the forensic recovery bundle offline and without a push-capable remote.
6. Publish only explicit refspecs with `--force-with-lease=<ref>:<old-sha>`.
   `--all` and `--mirror` are forbidden.
7. Restore an active, empty-bypass ruleset before any post-publish claim.
8. Ask GitHub Support to purge pull-request refs, cached views, and unreachable
   sensitive objects; until confirmed, status is `external_cleanup_pending`.
9. Recreate Mac and Linux source checkouts from sanitized GitHub history. Never
   merge, rebase, or bulk-cherry-pick the old lineage into the new graph.
10. Keep CodeQL closure, provider revocation, owner account checks, and genuine
    second-human review open until their external evidence is recorded.

The source sync is not runtime attestation: it does not rebuild, restart, access
PostgreSQL, contact a broker, or prove a deployed process is running the source
commit.
