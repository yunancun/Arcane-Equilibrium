# FA — Deep-Dive: Source vs Runtime Drift (Audit Direction #1, Phase 5 深挖)

- **Date**: 2026-05-30 (session rolled to 2026-05-31 mid-run)
- **Role**: FA (Functional Auditor) — cold, adversarial, READ-ONLY
- **Baseline (code)**: frozen `187704f6`; stated source delta since = ZERO (later commits docs-only `[skip ci]`; concurrent session churning working tree — ignored per dispatch)
- **Working-tree HEAD (Mac) observed**: `3f805a61` (docs churn; ignore per instructions)
- **Linux runtime HEAD observed**: `cc6c54d0`
- **Scope**: Go one level DEEPER than first-pass FA (`2026-05-30--FA--full_chain_functional_gap_dead_code_audit.md`) on Direction #1 — obtain the **EMPIRICAL Linux runtime evidence** the first pass DEFERRED (MIT could not run PG SELECTs; non-interactive ssh had empty `DATABASE_URL`). **This deep-dive obtained that evidence.**

> **ENV note**: Heavy intermittent tool flakiness this session (some batches silently dropped output; one `ls` of a non-existent dir cascade-cancelled a parallel batch; first `psql` attempts hit a wrong role). Every load-bearing datapoint below was re-run until it returned on a CLEAN, self-consistent batch (binary sha / PID / HEAD identical across ≥2 batches; PG numbers captured on a single clean `docker exec` with markers + RC=0). No finding shipped from a single flaky read.

---

## DEEPER VERDICT: **CONFIRMED-CLEAN — with full empirical runtime evidence across ALL 4 items. No NEW finding.**

All four DEEPER TASK axes are now **empirically measured on the Linux runtime** and **agree with the ledger**:

1. **`_sqlx_migrations` max = 115, 107 successful rows, 0 failed** — applied set matches source `sql/migrations/` exactly (no applied-not-in-source, no authored-source-not-applied; the only gaps are the known free holes / rollback-variant numbers). ✅
2. **`basis_panel` = 35,775 rows, 25 distinct symbols, latest row age ≈ 50s** — actively accumulating at the claimed ~25-symbol / 60s-flush cadence; **NOT stale**. ✅
3. **Deployed binary sha256 prefix = `e9f01569`**, build commit **`ec995160` is a real commit (basis/V115) AND a proven ancestor of Linux HEAD `cc6c54d0`**, with the entire `ec995160..cc6c54d0` delta being **docs-only (`[skip ci]`, zero non-doc files)** → **no code source-ahead-of-runtime**. ✅
4. **No DOC/TODO claim contradicted by runtime** — every measurable ledger claim (binary sha, PID 251791, build commit, V115 applied / max=115, basis_panel 25-sym live) **matches**. ✅

This is the runtime half the first pass deferred; combined with the first pass's source-level P0=0/P1=0, Direction #1 (Source vs Runtime Drift) is **CLEAN with evidence**.

---

## EMPIRICAL RUNTIME EVIDENCE (FACT — direct Linux telemetry via read-only `ssh trade-core`)

### Item 1 — `_sqlx_migrations` applied ledger vs source → **CLEAN (FACT)**

Cmd: `ssh trade-core 'docker exec trading_postgres psql -U trading_admin -d trading_ai -tAc "<SELECT>"'` (role resolved from `docker exec trading_postgres printenv POSTGRES_USER` = `trading_admin`; DB `trading_ai`).

| Probe | Result |
|---|---|
| `SELECT max(version), count(*) FILTER (WHERE success)` | **`115\|107`** → max applied = **115**, **107** successful rows |
| `SELECT version FROM _sqlx_migrations WHERE NOT success` | **empty** → **0 failed migrations** |
| `SELECT string_agg(version …) WHERE success` | `1..21, 23..41, 43..80, 82..103, 106, 107, 109, 112, 113, 114, 115` (gaps at **22, 42, 81, 104, 105, 108, 110, 111**) |

**Diff applied vs source `ls sql/migrations/` (FACT):** the applied set's gaps are fully explained by the source tree:
- **V022, V042** — source has no `V022__`/`V042__` *applied* file (V017_rollback / V040_healthcheck / V052_preflight are helper variants, not numbered applied migrations); the canonical sequence simply skips these — consistent.
- **V104, V105, V108, V110, V111** — **free holes** (never authored; V104/V105 = the v85-corrected free holes; V108/V110/V111 reserved-but-unwritten per Sprint 1A specs). Source `ls` has no file for them either.
- **V081** absent in both (source jumps V080→V082).
- Every authored source file V001…V115 (minus the above holes) **is present and `success=true`**. ⇒ **No applied-not-in-source row; no authored-source-not-applied row; 0 failed.** Applied max (115) == source max (115). **No migration drift.**

### Item 2 — `basis_panel` accumulation/freshness → **CLEAN, accumulating (FACT)**

Cmd: `… psql -U trading_admin -d trading_ai -tAc "SELECT count(*), count(DISTINCT symbol), (extract(epoch from now())*1000)::bigint - max(snapshot_ts_ms) FROM panel.basis_panel"` → **`35775|25|50415`**

| Metric | Value | Verdict |
|---|---|---|
| row count | **35,775** | substantial accumulation since V115 land |
| distinct symbols | **25** | exactly the ~25-symbol cohort the v84/v85 ledger claims |
| latest row age | **50,415 ms ≈ 50.4 s** | within the **60 s flush** cadence → **FRESH, actively writing** |

⇒ The basis_panel writer (`panel_aggregator/basis.rs`, first-pass FA Task 2) is **genuinely flushing in production** at the designed cadence — not a wired-but-idle writer. The first-pass FA P3-1 ("basis_panel writer live but A1-replay *consumer* freshness unproven") is **narrowed**: the **writer** side is now runtime-proven (25 sym / ~50s age / 35.7k rows). The only residue of P3-1 is the *offline-replay consumer* having actually read these rows — orthogonal to drift, owned by MIT (A1 Stage 0R replay run).

### Item 3 — Deployed binary identity & source-ahead → **CLEAN (FACT)**

| Probe | Value | Verdict |
|---|---|---|
| `ps -o pid,etime,cmd -p 251791` | PID **251791**, ELAPSED **23:46:27**, `rust/target/release/openclaw-engine` | engine live, ~23h46m uptime |
| `sha256sum .../target/release/openclaw-engine` | **`e9f015696f795b976fd1ce51577476427249de28e5088aadbc6b9915e9301d20`** | prefix **`e9f01569`** ✅ matches dispatch SHARED FACT |
| `stat -c %y` binary mtime | **2026-05-30 00:21:58 +0200** | built ~23h before probe; consistent with uptime |
| `git cat-file -t ec995160` / `git log -1` | `commit` / **`ec995160 feat(panel): basis_panel infra (V115 + BasisAggregator writer) — A1 prerequisite`** | `ec995160` real commit; subject = the V115/basis build the binary should contain |
| Linux `git rev-parse HEAD` | **`cc6c54d0`** ; Mac HEAD **`3f805a61`** | Mac docs-ahead of Linux |
| `docker ps` | **`trading_postgres` / `timescale/timescaledb:latest-pg16`** | PG container |

### Item 3b — Build-commit ancestry & code-source-ahead → **CLEAN (FACT)**

| Probe | Value | Verdict |
|---|---|---|
| `git merge-base --is-ancestor ec995160 cc6c54d0` | **ANCESTOR_YES** | build commit IS an ancestor of Linux HEAD |
| `git log --oneline ec995160..cc6c54d0` | **8 commits, every one `[skip ci]` docs** (incl. frozen `187704f6`, v85 fix `8d1890a8`, `d9128e22`, `14361a66`, `fe8393e2`, `9c3d5593`, `cc6c54d0`, `e63a00e0`) | all post-build commits = documentation |
| `git diff --stat ec995160..cc6c54d0` | **`15 files changed, 1814 insertions(+), 11 deletions(-)`** — only `TODO.md` + `docs/**` + `*/memory.md` + spec/report `.md` | zero source files |
| non-doc filter on `git diff --name-only` | **EMPTY** | **NO .rs/.sql/.py/.toml changed since build commit** |

**Interpretation:** `e9f01569` (content-hash) ↔ `ec995160` (build commit) is **truthful** — sha matches the deployed binary, `ec995160` resolves to the basis/V115 commit, and it is a proven ancestor of HEAD with a docs-only delta. **The running binary is NOT behind any committed code.** This is exactly the v85-class "phantom deployed commit" failure mode — here it **holds clean**.

---

## DEEPER TASK items — final status

| # | Item | Result |
|---|---|---|
| 1 | `_sqlx_migrations` max + applied list; diff vs source | ✅ **CLEAN (FACT)** — max **115**, 107 ok, **0 failed**; applied set == source set (gaps = known free holes / variants); no drift. |
| 2 | `basis_panel` row count + latest age | ✅ **CLEAN (FACT)** — **35,775 rows / 25 symbols / ~50s age**; accumulating at 60s-flush cadence, not stale. |
| 3 | Binary sha == `e9f01569`? maps to `ec995160`? Mac vs Linux HEAD? source-ahead? | ✅ **CLEAN (FACT)** — sha `e9f01569` ✅; `ec995160` real & ancestor ✅; Mac `3f805a61` vs Linux `cc6c54d0` ✅; **code source-ahead = NONE** (docs-only delta). |
| 4 | Any DOC/TODO claim runtime contradicts? | ✅ **NO CONTRADICTION (FACT)** — TODO §0 line 49 + v85 header (binary `e9f01569` / PID 251791 / built from `ec995160` / V115 applied max=115 / basis_panel 25-sym live) **all match runtime**. The v85 self-correction (`d9128e22` hallucinated "V104 applied" → fixed `8d1890a8`) is the only prior drift and is already closed. |

---

## Findings

| ID | Sev | Path:line | Evidence cmd | Impact | Why real (not FP) | Fix dir | Owner | Verifier |
|---|---|---|---|---|---|---|---|---|
| (none) | — | — | — | — | — | — | — | — |

**No NEW source-runtime-drift finding.** All four axes empirically clean. First-pass FA P3-1 is **narrowed** (writer side now runtime-proven; only offline-replay consumer read remains, orthogonal to drift).

---

## Carried (prior-FACT / SHARED FACT — corroborated this session)

- Source delta since `187704f6` = 0 — **empirically reinforced**: `187704f6` sits inside the `ec995160..cc6c54d0` set which is measured docs-only (zero non-doc files).
- `e9f01569` = content-hash not git commit; build commit `ec995160` — **re-confirmed** (sha match + commit resolves to basis build + ancestor of HEAD).
- V104 `supervised.live_audit` never existed; V103→V106 free holes; self-corrected v85 (`8d1890a8`) — **re-confirmed**: V104/V105 absent from both source `ls` AND applied `_sqlx_migrations` (so the hallucination is dead in runtime too, not just in docs).

---

## Hard-boundary check (spec-compliance)

READ-ONLY upheld: only this report written; no source edit; no deploy/restart/migration/auth/trading/git-commit. All `ssh`/`docker exec` commands were read-only (`ps`/`git`/`sha256sum`/`stat`/`ls`/`docker ps`/`printenv POSTGRES_USER`/`psql -tAc SELECT`); zero mutation. No `execution_state / execution_authority / live_execution_allowed / decision_lease_emitted / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json HMAC` surface touched. **No secret echoed** — `printenv POSTGRES_USER/DB` returns only the non-secret role/db names (`trading_admin`/`trading_ai`); no password, no `DATABASE_URL` value printed. **No BLOCKER.**

---

## Confidence

- Items 1, 2, 3, 3b, 4: **FACT** — each captured on a clean batch with markers + `RC=0`; binary sha/PID/HEAD additionally cross-checked across ≥2 independent batches; PG numbers from a single self-consistent `psql` run (`115|107` + applied list + `35775|25|50415`, all with `RC=0`).
- No INFERENCE or ASSUMPTION load-bearing in the verdict.

---
FA AUDIT DONE: report path: docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-30--FA--deepdive_source_runtime_drift.md — VERDICT: CONFIRMED-CLEAN-with-evidence (all 4 axes empirically measured; sqlx max=115/0-failed, basis_panel 35775 rows/25 sym/~50s age, binary e9f01569 = ec995160 ancestor with docs-only delta = no code source-ahead). No NEW finding.
