# CI Audit Scripts

CI-time audit scripts that enforce REF-20 / REF-21 contract boundaries on
compiled artifacts. These run as defense-in-depth on top of compile-time
feature gates and runtime profile guards.

## Components

| File | Purpose |
|---|---|
| `check_stable_id_duplication.sh` | W-D MAG-083 P1-1 follow-up — fast grep guard that fails CI if Rust source outside the canonical Agent Spine helper/caller files reintroduces literal `stable_id` seed formatting (`format!("{}:{}:{}:{}"...`) with stable-id-like variable names. |
| `replay_runner_symbol_audit.sh` | REF-20 Wave 3 R20-P2b-S10 — `nm` / `objdump` symbol grep on `replay_runner` release binary; verifies zero forbidden symbol class (Decision Lease / IPC server / exchange pipeline / Bybit connector / live auth write / order placement / DB writer). Cross-platform (macOS BSD nm + Linux GNU nm). |
| `test_replay_runner_symbol_audit.sh` | Mock-based bash test harness for the audit script (5 cases: clean / forbidden hit / nm absent / binary missing / multi-class hit). |

## Three-Layer Defense

REF-20 V3 §3 G7/G8 mandates three independent isolation layers for the
`replay_runner` binary; this directory hosts L3:

| Layer | Mechanism | Owner | Land point |
|---|---|---|---|
| L1 compile-time | Cargo `replay_isolated` feature gate + `[[bin]] required-features` | `Cargo.toml` | Wave 1 R20-P0-T2 |
| L2 runtime | `ReplayProfile::Isolated` enum guard + `enforce_isolated_or_panic()` | `rust/.../replay/profile.rs` | Wave 3 R20-P2b-S7 |
| **L3 binary symbol** | **`nm` / `objdump` symbol grep on stripped release artifact** | **`replay_runner_symbol_audit.sh`** | **Wave 3 R20-P2b-S10 (this dir)** |

Any single layer breach shall be rejected; **all three** must pass.

## `check_stable_id_duplication.sh` Usage

```bash
bash helper_scripts/ci/check_stable_id_duplication.sh
```

Exit code `0` means no duplicated literal seed pattern was found. Exit code
`1` means at least one non-canonical Rust file contains the guarded
`format!("{}:{}:{}:{}"...` signature together with stable-id-like identifiers;
the output lists offending files and line numbers.

This check is wired into `.github/workflows/ci.yml` as
`stable_id duplication guard`.

## `replay_runner_symbol_audit.sh` Usage

```bash
# Default: build replay_runner --release --features replay_isolated, then audit
bash helper_scripts/ci/replay_runner_symbol_audit.sh

# Skip rebuild (use existing binary)
SKIP_BUILD=1 bash helper_scripts/ci/replay_runner_symbol_audit.sh

# Override binary path (for CI matrix with prebuilt artifacts)
REPLAY_RUNNER_BIN=/path/to/replay_runner \
    bash helper_scripts/ci/replay_runner_symbol_audit.sh
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | AUDIT PASS — no forbidden symbol detected |
| 1 | AUDIT FAIL — at least one forbidden symbol class hit |
| 2 | BUILD FAIL — `cargo build` returned non-zero |
| 3 | NM NOT FOUND — `nm` toolchain absent on `$PATH` (or unsupported OS) |
| 4 | BINARY NOT FOUND — expected `target/release/replay_runner` missing |

### Cross-platform behavior (per Wave 2 dispatch §2 ambiguity #5)

| OS | `uname -s` | nm flags | CI priority |
|---|---|---|---|
| macOS (aarch64-apple-darwin / Apple Silicon) | `Darwin` | `nm -gU` (BSD: external + defined only) | **primary** |
| Linux (x86_64 / linux-arm64) | `Linux` | `nm --extern-only --defined-only` (GNU binutils) | secondary |
| Other | other | exit 3 (fail-closed; no false-PASS) | n/a |

Apple llvm-nm also accepts GNU flags, but we use BSD-style on Darwin for
compatibility with raw BSD nm shipped on classic macOS toolchains.

### Forbidden symbol classes

Source: PA boundary report §6.1 + V3 §6.2 + 16 root principles §4.

```text
acquire_lease | release_lease            # Decision Lease (16#3)
GovernanceHub                            # Python lease bridge
ipc_server::* | ipc_dispatch | ipc_handler   # JSON-RPC pipeline (16#1, 16#2)
build_exchange_pipeline                   # exchange bootstrap (16#1)
decision_lease | DecisionLease            # lease.rs API
exchange_dispatch                         # live order routing
bybit_(rest|ws|api)                       # exchange connectors
live_authorization | _write_signed_live_authorization  # CLAUDE §4 hard
place_order | cancel_order | amend_order  # single write entry §1
canary_writer::write | database::writer   # DB writer channels
```

Any hit ≥ 1 → exit 1 with sample log line per class (top-5).

## CI Integration Examples

### GitHub Actions

```yaml
name: replay_runner_symbol_audit
on:
  pull_request:
    paths:
      - 'rust/openclaw_engine/**'
      - 'helper_scripts/ci/replay_runner_symbol_audit.sh'

jobs:
  audit:
    strategy:
      matrix:
        os: [macos-14, ubuntu-22.04]   # macOS primary, Linux secondary
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: dtolnay/rust-toolchain@stable
      - name: Run replay_runner symbol audit
        run: bash helper_scripts/ci/replay_runner_symbol_audit.sh
```

### Cron / scheduled

```bash
# Daily 03:00 audit on Linux trade-core (cron)
0 3 * * * cd $OPENCLAW_BASE_DIR && \
    bash helper_scripts/ci/replay_runner_symbol_audit.sh \
        >> $OPENCLAW_DATA_DIR/logs/replay_runner_audit.log 2>&1
```

### Pre-commit hook (optional, dev only)

```bash
# .git/hooks/pre-commit (after Rust changes)
if git diff --cached --name-only | grep -qE 'rust/openclaw_engine/'; then
    SKIP_BUILD=0 bash helper_scripts/ci/replay_runner_symbol_audit.sh \
        || { echo 'replay_runner symbol audit FAIL — fix before commit'; exit 1; }
fi
```

## Test Harness Usage

```bash
bash helper_scripts/ci/test_replay_runner_symbol_audit.sh
```

Expected output:

```
=== replay_runner_symbol_audit.sh test harness ===
T1 clean_symbols → exit 0 PASS
T2 acquire_lease hit → exit 1 PASS
T3 nm absent → exit 3 PASS
T4 binary missing → exit 4 PASS
T5 multi-class hit → exit 1 PASS
PASS: 5 / FAIL: 0 / total: 5
ALL TESTS PASS
```

The harness mocks `nm` via shim binary in a tmpdir, so it does **not**
trigger the slow `cargo build --release` step (~30-60s on Mac M-series).
Real binary verification belongs to the CI matrix; this harness only
proves audit logic correctness for known symbol input fixtures.

## Spec References

- V3 contract: `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
  §3 G7/G8 + §6.1/§6.2 + §12 #8
- Workplan: `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`
  §4 Wave 3 R20-P2b-S10
- PA boundary report: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md`
  §6 (symbol allowlist)
- Wave 2 dispatch decisions: `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md`
  §2 #5 (macOS primary / Linux secondary)
