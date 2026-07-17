# Security Policy

## Supported version

Only the current `main` branch receives security fixes. Historical branches and
tags are unsupported. The pre-rewrite tag set has not passed the exact-ref
public-history hygiene gate and must not be described as clean. After the
controlled history rewrite, retain only refs that pass the rewritten inventory
scan.

## Reporting a vulnerability

Do not open a public issue for a vulnerability or a suspected credential leak.
Use GitHub's private vulnerability reporting form:

<https://github.com/yunancun/Arcane-Equilibrium/security/advisories/new>

Include the affected commit or path, reproduction steps, impact, and any known
mitigation. Do not include real credentials, account data, trading records, or
other third-party data in the report.

## Repository controls

The dedicated `public repository hygiene gate` workflow is introduced by the
public-repository hardening change. It becomes an enforced current control only
after that change is merged and its first `main` run succeeds. Its triggers are
`pull_request_target`, pushes to `main`, and a weekly schedule; it does not scan
every branch push. The job scans for database artifacts and magic, private-key
headers, embedded-credential DSNs, provider-shaped tokens, and JWTs.

Branch rules, CodeQL, secret scanning, push protection, and local hooks are
defense in depth. Source remediation is not CodeQL closure until GitHub analyzes
merged `main`, and none of these controls authorizes publishing sensitive
fixtures or runtime exports.

Runtime credentials must remain outside Git. The supported Linux deployment
source contract stores Bybit credentials in owner-only local files: directories
are `0700`, files are atomically created and replaced as `0600`, and symlink or
permission-hardening failures are rejected. This is an explicit local
file-secret risk acceptance, not permission to commit or log a credential.
Source synchronization alone does not prove that a deployed runtime uses that
source or that these controls are active.
