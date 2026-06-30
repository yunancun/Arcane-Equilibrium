# PM Checkpoint - IBKR Stock/ETF Release/Tiny-Live Contract Hardening

日期：2026-06-30
角色：PM(default)
範圍：ADR-0048 / AMD-2026-06-29-01 Phase 5 release packet and future tiny-live ADR discussion gate

## Verdict

`DONE_WITH_CONCERNS_NO_RUNTIME_AUTHORITY`

This checkpoint hardens the final Phase 0 named-contract surfaces that can gate
paper/shadow release and any future tiny-live ADR discussion. Both contracts now
require exact manifest contract identity plus source-version alignment instead
of accepting any non-empty fixture id.

## Changed

- Added exported `STOCK_ETF_RELEASE_PACKET_CONTRACT_ID`.
- `StockEtfReleasePacketV1` now requires `packet_id == stock_etf_release_packet_v1`
  and `source_version == 1`.
- Added exported `STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID`.
- `TinyLiveAdrEligibilityV1` now requires
  `contract_id == tiny_live_adr_eligibility_v1` and `source_version == 1`.
- The Phase 0 manifest validator now consumes the shared release/tiny-live
  contract constants.
- Default-blocked release and tiny-live templates now expose `source_version = 0`
  and still fail closed.
- Acceptance tests now reject old `_fixture` ids and wrong source versions.

## Boundary

No IBKR contact, no IBKR healthcheck, no IB Gateway/TWS startup, no secret
read/create/serialization, no connector runtime, no collector, no evidence-clock
start, no scorecard writer, no DB apply, no GUI lane authority, no paper order,
no tiny-live, no live, and no Bybit live execution behavior change.

Passing `tiny_live_adr_eligibility_v1` can still only open a future ADR
discussion. It cannot authorize IBKR tiny-live/live execution.

## Verification

Focused verification:

```bash
cargo test -p openclaw_types --test stock_etf_release_packet_acceptance --test stock_etf_tiny_live_eligibility_acceptance --test stock_etf_phase0_manifest_acceptance
```

Result: `21 passed`.

Full package:

```bash
cargo test -p openclaw_types
```

Result: `35` unit/golden + `176` integration/acceptance + `0` doc-tests passed.

Additional checks:

```bash
rustfmt --check openclaw_types/src/stock_etf_release_packet.rs openclaw_types/src/stock_etf_tiny_live_eligibility.rs openclaw_types/src/stock_etf_phase0_manifest.rs openclaw_types/tests/stock_etf_release_packet_acceptance.rs openclaw_types/tests/stock_etf_tiny_live_eligibility_acceptance.rs openclaw_types/tests/stock_etf_phase0_manifest_acceptance.rs
git diff --check
```

Both passed.

## Next Gate

First IBKR contact remains blocked until real secret/topology evidence and an
immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact exist. A real
Phase 5 release packet still requires actual paper/shadow window evidence,
role reports, DQ/scorecard artifacts, archive proof, kill/disable cleanup proof,
and final shakedown evidence.
