# E2 Adversarial Review — LG5-W3-FUP-3-CRON-ENV

- Date: 2026-05-02
- Reviewer: E2
- Branch: main (uncommitted, awaiting E2 review)
- Files in scope (3):
  - `helper_scripts/cron/edge_label_backfill_cron.sh` (134 → 196, +62)
  - `helper_scripts/cron/test_edge_label_backfill_cron_env.py` (NEW, 211 LOC)
  - `docs/healthchecks/2026-05-02--lg5_health_checks.md` (+18)
- Verdict: **PASS to E4 cron re-smoke**

## Context

E4 Linux smoke for FUP-2 Fix 1+2 reported real cron run `psycopg2.OperationalError: fe_sendauth: no password supplied`.
Root cause: `edge_label_backfill_cron.sh` ran in cron's barebones env (no shell rc, no login env)
without `OPENCLAW_DATABASE_URL` or `POSTGRES_*`. Downstream `edge_label_backfill.py:_open_conn`
fell into the empty-password POSTGRES_* branch and psycopg2 rejected.

## A. PG creds sourcing

| Item | Status |
|---|---|
| Source from `$SECRETS_ROOT/environment_files/basic_system_services.env` | OK |
| `$SECRETS_ROOT` defaults to `$HOME/BybitOpenClaw/secrets` | OK |
| Grep 5 keys (USER/PASS/DB/HOST/PORT) | OK |
| HOST/PORT fallback `127.0.0.1` / `5432` | OK |
| Exit 2 + FATAL when env file missing | OK (script:117-120) |
| Exit 2 + FATAL when creds incomplete | OK (script:139-142) |
| Export `OPENCLAW_DATABASE_URL=postgresql://redacted@HOST:PORT/DB` | OK (script:143) |
| `mkdir -p "$LOG_DIR"` placed BEFORE first FATAL `tee -a "$LOG"` | OK (script:85, comment lines 81-84) |

## B. Sibling pattern alignment

| Item | Status |
|---|---|
| Truly mirrors `linux_bootstrap_db.sh:41-45` 5-key pattern | OK |
| Improvement over sibling: `\|\| true` + `${VAR:-default}` two-stage fallback | OK + IMPROVED |
| Choice over `passive_wait_healthcheck_cron.sh:43-44` 2-line hardcoded | JUSTIFIED (sibling hardcodes user/db/host/port = slot-coupled) |

E1 self-report flagged a real gap in `linux_bootstrap_db.sh` literal `|| echo '127.0.0.1'` fallback:
that pattern fails when `grep '^POSTGRES_HOST=' file` matches but value is empty (no fallback fires).
The two-stage `|| true` + `${VAR:-default}` correctly handles both grep-miss AND grep-hit-but-empty.

## C. Unit tests (4/4 PASS, 0.54s)

| Test | Status |
|---|---|
| `test_wrapper_exists_and_syntax_clean` | PASS |
| `test_env_file_missing_exits_2_with_fatal` | PASS |
| `test_env_file_creds_incomplete_exits_2_with_fatal` | PASS |
| `test_env_file_complete_exports_database_url` | PASS |

Mock python3 via PATH shadow + echoes `$OPENCLAW_DATABASE_URL` to wrapper log = real validation
that export reaches downstream subprocess (not just shell-level set).

## D. Healthcheck doc

| Item | Status |
|---|---|
| "Pairs with" section adds PG sourcing note | OK |
| Operator deploy section warns "DO NOT inline POSTGRES_*" | OK |
| Aligns with wrapper actual behaviour | OK |

## E. No regression

| Item | Status |
|---|---|
| Existing 25 lg5_health_checks tests untouched | OK (no Python imports of cron wrapper) |
| W1/W2/W3/FUP-1/Fix 1/Fix 2 code 0 changes | OK (`git status --porcelain` only 3 files) |
| Wrapper backward-compat (BASE/DATA/BATCH/log behaviour preserved) | OK (only ts() moved up + new sourcing block + `mkdir -p "$LOG_DIR"` early) |
| `edge_label_backfill_cron` callers grep | 0 caller in code (only docs); safe |

## F. Cross-platform + LOC + bilingual + secret

| Item | Status |
|---|---|
| LOC 196 < 800 warn line | OK |
| `/home/ncyu` / `/Users/<name>` hardcoded path grep | 0 hit |
| `$HOME/BybitOpenClaw/secrets` fallback works on both Mac + Linux | OK |
| Bilingual MODULE_NOTE + inline | OK (every English block has Chinese mirror) |
| `set -x` / `echo $PG_PASS` / `cat ENV_FILE` grep | 0 hit |
| FATAL message lists key names only (no values leaked) | OK |
| `OPENCLAW_DATABASE_URL` export only to child process env (cron mailer cannot see) | OK |

## G. Robustness edge cases (E2 self-probe)

| Case | Behaviour | Verdict |
|---|---|---|
| ENV file `export KEY=value` format drift | grep `^POSTGRES_PASSWORD=` does not match → PG_PASS empty → FATAL exit 2 | OK (fail-closed) |
| ENV file `KEY="quoted_value"` | grep + cut keeps literal quotes → DSN contains literal `"` → psycopg2 loud raise | LOW informational; sibling has same behaviour; Linux real env file confirmed pure `KEY=value` format via ssh |
| POSTGRES_HOST really absent on Linux real env file | fallback `127.0.0.1` fires correctly | OK (verified via ssh trade-core) |
| ENV file 0644 readable | wrapper has no permission requirement (cron user can read) | OK (operator setup standard 0640) |
| Wrapper sources file via `grep` (not `source`) | shell injection from env file values impossible | OK (DSN string interpolation safe; values quoted by shell parameter expansion) |

## Adversarial questions raised + answered

1. **Q**: Mock python3 echoes `$OPENCLAW_DATABASE_URL` to log — real python3 won't, so log secret leak in test only?
   **A**: Confirmed only test-fixture behaviour. Production python3 module does not echo env. No leak in real cron run.

2. **Q**: Format drift to `export KEY=value` would silently break — caught?
   **A**: Probed live; FATAL exit 2 fires correctly because grep regex `^POSTGRES_PASSWORD=` does not match `^export POSTGRES_PASSWORD=`. Fail-closed verified.

3. **Q**: HOST fallback `${PG_HOST:-127.0.0.1}` — does it differ from sibling literal `|| echo '127.0.0.1'` materially?
   **A**: Yes, materially better. Sibling fails open if grep match but value blank (e.g., `POSTGRES_HOST=` with empty RHS). E1's two-stage fallback handles both cases. Verified by code trace.

4. **Q**: Does the FATAL `tee -a "$LOG"` work when LOG_DIR doesn't exist yet?
   **A**: Caught and fixed. `mkdir -p "$LOG_DIR"` placed at line 85, BEFORE any FATAL branch (script comment lines 81-84 explicitly explain). Tested in `test_env_file_missing_exits_2_with_fatal`: log created and FATAL written.

5. **Q**: Is the wrapper now testable on Mac dev (not just Linux)?
   **A**: Yes. 4/4 tests run on Mac in 0.54s; hermetic env via `subprocess.run(env=...)` with `mock_bin` PATH shadow. Real PG not required.

## Findings

| Severity | Location | Description | Action |
|---|---|---|---|
| (none) | | | |

## Conclusion

**PASS to E4 cron re-smoke**. All checks green; sibling alignment correct + improved on a real
sibling corner-case bug; 4/4 new unit tests pin the new behaviour; 0 regression to existing 25
lg5_health_checks tests; no secret leak vector; cross-platform safe.

E1 made a senior-level judgment call by mirroring the more complete sibling
(`linux_bootstrap_db.sh:41-45`) instead of the slot-coupled 2-liner
(`passive_wait_healthcheck_cron.sh:43-44`), AND improved on the sibling's grep-hit-but-empty
fallback corner case. Adversarial probes (format drift / quoted values / HOST absent / mkdir
ordering / mock leak) all pass.

E4 next: re-run real cron smoke on Linux trade-core with operator-installed
crontab `*/30 * * * * $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_label_backfill_cron.sh`,
verify `[43] label_backfill_freshness` healthcheck flips PASS within ~30 minutes.
