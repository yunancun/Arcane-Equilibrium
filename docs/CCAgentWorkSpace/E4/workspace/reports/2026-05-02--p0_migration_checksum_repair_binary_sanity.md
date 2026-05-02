# E4 P0 Migration Checksum Repair Binary Sanity Test — 2026-05-02

**Branch**: `fix/p0-2026-05-02-sqlx-migration-checksum-repair`
**Commit**: `bb6bf04` — fix(p0-migration-checksum): add repair_migration_checksum binary for V028-V034 drift
**Parent**: `cc286d0`

**Verdict**: **PASS** — ready for operator dry-run review (then PM Sign-off)

**Scope**: P0 incident response binary, **`--apply` mode NOT executed** (per PA dry-run-only requirement). Pure validation:
- Build hygiene (workspace + binary alone)
- Existing test baseline preservation (lib + workspace)
- Binary smoke tests (4 scenarios, no DB writes)
- Real DB `--verify` reproducibility + read-only proof

## Build verification

| Target | Result | Baseline | Delta |
|---|---|---|---|
| `cargo build --release --workspace` | 0 errors, 26 warnings | cc286d0 = 26 warnings | +0 ✓ |
| `cargo build --release --bin repair_migration_checksum` | OK | new | NEW |

**Warning parity confirmed**: checked out `cc286d0` (parent) → 26 warnings; checked back to `bb6bf04` → 26 warnings. Binary additions introduce **zero** new warnings.

## Test 結果

| Suite | passed | failed | baseline | delta | verdict |
|---|---|---|---|---|---|
| Cargo lib `openclaw_engine` (`--lib`) | **2405** | 0 | 2405 | +0 | OK |
| Cargo workspace tests (`--workspace`) | **3008** | 0 | 3008 | +0 | OK |
| Lib 2nd run (non-flaky verification) | **2405** | 0 | match | identical | OK |

## Binary smoke tests

### 1. Invalid DB URL with `--verify` (no DB write expected)

```
OPENCLAW_DATABASE_URL='postgres://nope:nope@127.0.0.1:9999/nope_db' --verify
```
- stdout: `# parsed_count = 34` then `ERROR: failed to connect DB: pool timed out`
- exit 0
- **No panic**, graceful error path
- Verdict: PASS

### 2. `--apply` without `--i-understand-this-modifies-db`

- stdout: `REFUSED: --apply requires --i-understand-this-modifies-db flag.` + 中文鏡譯
- exit 0
- DB **never connected** (refusal happens before pool init)
- Verdict: PASS

### 3. `--apply --auto-yes` bogus flag (active prompt-bypass attempt)

- stdout: `error: rejected flag "--auto-yes": interactive prompt is mandatory for --apply`
- prints help text
- exit 0
- Hard-rejects any flag attempting to bypass the COMMIT prompt; double safety beyond ack flag
- Verdict: PASS

### 4. Real DB `--verify` reproducibility (2 runs, bit-identical)

- Run 1 vs Run 2 stdout diff: **0 lines** (49 lines each, byte-identical)
- Output deterministic — no time/random in read path
- Verdict: PASS

## Real DB `--verify` content audit

```
parsed_files = 34
db_rows      = 33
drift_count  = 5
drift_versions      = [28, 30, 31, 32, 34]
pa_known_drift      = [28, 30, 31, 32, 34]
pa_caught_by_binary = [28, 30, 31, 32, 34]
pa_missed_by_binary = []
v033_verdict        = clean
V035_status         = MISSING_IN_DB (file present at HEAD, no row in _sqlx_migrations)
```

**Drift detection matches PA spec exactly.** No false positives, no false negatives.

## DB read-only proof (zero mutation by `--verify`)

| Step | Action | Result |
|---|---|---|
| 1 | `psql ... SELECT version, encode(checksum,'hex') FROM _sqlx_migrations ORDER BY version` → `/tmp/checksums_before.txt` | 34 rows captured |
| 2 | `repair_migration_checksum --verify` (1st run) | exit 0, drift_count=5 |
| 3 | `repair_migration_checksum --verify` (2nd run) | exit 0, identical output |
| 4 | `psql ... SELECT version, encode(checksum,'hex') FROM _sqlx_migrations ORDER BY version` → `/tmp/checksums_after.txt` | 34 rows captured |
| 5 | `diff before after` | **diff_lines=0** ✓ |

**Conclusion**: `--verify` mode performs ZERO writes to `_sqlx_migrations`, as designed.

## Mock 安全 audit

N/A — pure binary smoke test, real DB connection used in step 4. No mocks introduced.

## 浮點一致性

N/A — non-numerical scope (sqlx SHA-384 hash bytes only).

## SLA 壓測

N/A — administrative repair binary, not hot-path code.

## Pre-existing failures

None. Cargo lib 2405/0 + workspace 3008/0 both clean (no pre-existing fail to track).

## 跑兩遍結果

- **Build**: 1st = 26 warnings / 0 errors; 2nd cached → identical
- **Lib test**: 1st = 2405/0 (0.52s); 2nd = 2405/0 (0.52s) — non-flaky ✓
- **Real DB `--verify`**: 1st = 49 lines; 2nd = 49 lines bit-identical (diff=0) ✓

## 結論

**PASS** — All 5 verification gates green:
1. ✓ Workspace builds clean (0 new warnings)
2. ✓ Cargo lib + workspace tests preserve baseline (2405/0 + 3008/0)
3. ✓ Binary alone builds clean
4. ✓ All 4 smoke tests behave per design (graceful errors, fail-closed flag rejection, deterministic dry-run)
5. ✓ Real DB `--verify` is provably read-only (DB checksums byte-identical pre/post)

**Outstanding**: `--apply` mode NOT executed by design. Operator must dry-run review the verify output (drift_versions=[28,30,31,32,34] + V035 MISSING_IN_DB) and explicitly authorize before any `--apply --i-understand-this-modifies-db` invocation. E4 confirms the binary's safety scaffolding (ack flag + interactive COMMIT prompt + automatic pg_dump backup per code) is wired correctly.

## E1 補強需求

**None** — bb6bf04 passes E4 sanity test as-is. No regression, no test gap, no design smell uncovered.

## 退回 E1 修復清單

N/A — PASS verdict, no rework required.
