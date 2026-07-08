# IBKR External Verification Preflight Status

Generated at: 2026-07-08T10:36:42Z
Role: PM local and Linux read-only preflight
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Source head: `05ce5543e`

## Verdict

`STOP_EXTERNAL_VERIFICATION_PREREQUISITES_ABSENT`

The IBKR source/no-contact engineering packet is synchronized and locally verified, but the system is not ready for a ready-demo path that performs IBKR external contact. The remaining blockers are operator/runtime prerequisites, not source implementation gaps.

## Three-Way Sync Evidence

- Mac `HEAD`: `05ce5543e`
- Mac `origin/main`: `05ce5543e`
- Linux `HEAD`: `05ce5543e`
- Linux `origin/main`: `05ce5543e`
- Linux status: `## main...origin/main`
- Commit synchronized before this preflight: `05ce5543e Add IBKR dual-engine no-contact packet`

## Completed Engineering Evidence

The no-contact IBKR dual-engine packet is committed and synchronized:

- API-absent deterministic engineering fixture.
- Python connector skeleton/readiness contract.
- Dual-engine paper-shadow and live-grade boundary templates.
- PM and Operator reports for L8G/L8H closure and no-contact infrastructure.
- Broker settings templates remain blocked by default and secret-free.

Focused Python verification passed before sync:

```text
python3 -m pytest -q \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_api_absent_engineering.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_skeleton.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_ibkr_connector_action_matrix.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_python_no_write_static_guard.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_stock_etf_surface_coverage_static_guard.py

32 passed in 0.40s
```

Focused Rust contract verification now passes with the explicit stable toolchain:

```text
RUSTC=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustc \
/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test \
  --manifest-path rust/Cargo.toml \
  -p openclaw_types \
  --test ibkr_phase2_gate_acceptance \
  --test ibkr_phase2_runtime_acceptance \
  --test ibkr_phase2_artifact_acceptance \
  --test ibkr_phase2_policy_acceptance \
  --test ibkr_non_bybit_api_allowlist_acceptance \
  --test ibkr_paper_lifecycle_acceptance \
  --test ibkr_feature_flag_secret_auth_acceptance \
  --test stock_etf_ibkr_readonly_probe_request_acceptance \
  --test stock_etf_ibkr_readonly_probe_result_import_request_acceptance

95 passed
```

Focused engine Stock/ETF verification also passes:

```text
RUSTC=/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/rustc \
/Users/ncyu/.rustup/toolchains/stable-aarch64-apple-darwin/bin/cargo test \
  --manifest-path rust/Cargo.toml \
  -p openclaw_engine stock_etf

32 passed; 0 failed; 4309 filtered out; command exited 0
```

Tooling note: `/Users/ncyu/.cargo/bin/rustup` is still a broken symlink to `/opt/homebrew/bin/rustup-init`, but this is no longer a hard verification blocker for this lane because the explicit stable cargo/rustc binaries work.

## Linux Read-Only Preflight Evidence

The Linux probe was metadata-only. It did not start IB Gateway/TWS, did not open any IBKR socket, did not inspect secret content, did not create credential files, did not run an MCP server, did not submit a paper order, and did not touch live paths.

Linux repo state:

```text
repo_head=05ce5543e
repo_origin=05ce5543e
repo_status=## main...origin/main
```

Runtime process and port posture:

```text
ibkr_processes_found=0
ibkr_ports_found=0
```

Candidate secret slots are absent:

```text
secret_dir_absent=/home/ncyu/BybitOpenClaw/secrets/external/ibkr
secret_dir_absent=/home/ncyu/BybitOpenClaw/secrets/ibkr
secret_dir_absent=/home/ncyu/BybitOpenClaw/var/openclaw/secrets/external/ibkr
```

Candidate Phase2 artifacts under `~/BybitOpenClaw/var/openclaw` are old copied source templates, not immutable PASS artifacts:

```text
2026-06-30T23:12 ~/BybitOpenClaw/var/openclaw/downstream_bounded_auth_refresh_20260630T211852Z/source_origin_main/settings/broker/ibkr_external_surface_gate.toml
2026-06-30T23:12 ~/BybitOpenClaw/var/openclaw/downstream_bounded_auth_refresh_20260630T211852Z/source_origin_main/settings/broker/ibkr_phase2_gate_artifact.template.toml
2026-06-30T23:12 ~/BybitOpenClaw/var/openclaw/downstream_bounded_auth_refresh_20260630T211852Z/source_origin_main/settings/broker/ibkr_phase2_policies.toml
2026-06-30T23:12 ~/BybitOpenClaw/var/openclaw/downstream_bounded_auth_refresh_20260630T211852Z/source_origin_main/settings/broker/ibkr_phase2_runtime_contracts.toml
```

## Remaining Blockers

The following are still absent and cannot be fabricated by source-only engineering:

- Immutable sealed `phase2_ibkr_external_surface_gate_v1` PASS artifact.
- Accepted IBKR paper or read-only credential slot evidence, fingerprint-only and without secret serialization.
- Accepted loopback IB Gateway/TWS paper topology evidence.
- Accepted IBKR session attestation with startup time, expiry, data tier, account fingerprint hash, and entitlement record.
- Operator credential/session/manual approval for the first read-only healthcheck.

## Ready-Demo Assessment

Not fully ready-demo if the demo requires real IBKR connectivity, live IBKR paper session proof, or first read-only healthcheck.

Ready-demo only for the no-contact/source-controlled demo surface:

- It can show the source fixture, blocked readiness posture, external-surface gate status, denied write/live boundaries, and no-contact dual-engine design.
- It cannot honestly demonstrate real IBKR API connectivity or paper-session health until the runtime/operator prerequisites above exist.

## Next Allowed Action

Resume Phase2 only after operator provides or attests all runtime prerequisites without exposing secrets:

1. Paper or read-only IBKR session approval under ADR-0048 and AMD-2026-06-29-01.
2. Secret-slot metadata evidence with live slot absent or empty, owner-only permissions, no env fallback, and fingerprint-only status.
3. Loopback IB Gateway/TWS paper topology evidence on the approved paper port.
4. Session attestation and entitlement records.
5. Sealed PM/Operator-reviewed Phase2 PASS artifact with `ibkr_call_performed=false`.

Only then should PM dispatch the first read-only IBKR healthcheck. Until then, proceeding would cross the pre-contact gate.
