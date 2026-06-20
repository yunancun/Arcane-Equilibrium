# MM Fee-Path Feasibility

Date: 2026-06-20
Owner: PM-local focused monitor/reducer pass
Scope: read-only research/monitoring status; not a promotion verdict

## Verdict

The maker path is fee-sensitive, but the standard VIP path is much farther than VIP1.

v252 found one sample-gated cell that barely turns positive only around a `1.0bp/side` maker fee, with break-even at `1.028bp/side`. v253 joins that break-even with current local 30d fill capacity and Bybit's standard derivatives VIP ladder. The first standard tier that clears the break-even is **VIP5** (`1.0bp/side`), not VIP1-4.

Current local 30d fills capacity proxy from the Linux isolated smoke:

| Metric | Value |
|---|---:|
| fills | 1,553 |
| total notional | $871,107.04 |
| maker fills | 845 |
| maker notional | $496,419.84 |
| effective fee | 3.6688 bps |

VIP5 standard criteria from Bybit's current public fee docs are roughly `$250M/30d` derivatives volume or `$2M` asset balance. The current local volume proxy is `0.348%` of that VIP5 volume threshold (`286.991x` multiplier needed). This proxy is not mainnet eligibility proof because it includes local demo/live_demo/live bot capacity.

## Evidence

- v252 artifact: `/tmp/openclaw/research/fillsim/fillsim_fee_sensitivity_smoke_20260620T093904Z.json`
- v252 artifact sha256: `33020cceaff59b47ae121dc270c7602c3a4540958eff497ac24975387ef9b5f2`
- v253 Linux isolated smoke dir: `/tmp/openclaw_mm_fee_path_smoke_20260620T095339Z`
- Fee-path status: `STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED`
- Break-even maker fee: `1.028bp/side`
- Fee reduction still needed from current `2.0bp/side`: `0.972bp/side`
- First clearing standard VIP tier: `VIP5`, maker fee `1.0bp/side`

Official Bybit references rechecked on 2026-06-20:

- Bybit Trading Fee Structure: https://www.bybit.com/en/help-center/article/Trading-Fee-Structure
- Bybit Benefits of the VIP Program: https://www.bybit.com/en/help-center/article/Benefits-of-the-VIP-Program
- Bybit Market Maker Incentive Program: https://www.bybit.com/en/help-center/article/Introduction-to-the-Market-Maker-Incentive-Program

## Implementation

Added `program_code/research/microstructure/fee_path.py`:

- Pure reducer, no network calls, no account lookup, no promotion decision.
- Preserves stable output schema even when no break-even cell exists.
- Emits `standard_vip_tiers` rows with fee-clear flags and volume/asset threshold gaps.
- Marks capacity as a local proxy, not VIP eligibility evidence.

Updated `helper_scripts/cron/recorder_mm_verdict_cron.sh`:

- Adds read-only `fee_capacity_30d` SQL summary over `trading.fills`.
- Adds `fee_path_feasibility` to the daily status JSON.
- Keeps the existing read-only boundary: no strategy flag, no order path, no trading/market table writes.

## PM Read

The fee lever is a business/capital/institutional path, not a near-term engineering fix. The current actionable engineering direction remains:

- stronger pre-fill signal/regime filters that raise edge-before-fees above the current cost wall;
- more L1-covered regime days for fill realism;
- formal QC/MIT/AI-E review only if a candidate survives sample, fee, and cross-regime gates.

Operator path, if pursued separately:

- verify actual account fee on Bybit `My Fee Rate`;
- decide whether asset balance / volume scale / Bybit BD / institutional MM application is realistic;
- treat MM rebates as application-reviewed terms, not an automatic ladder outcome.

## Validation

Mac:

- `python3 -m pytest -q program_code/research/tests/test_mm_fee_path_feasibility.py helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` -> 14 passed
- `python3 -m py_compile program_code/research/microstructure/fee_path.py`
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- `git diff --check -- ...` clean

Linux `trade-core`:

- same 14 focused tests passed
- `fee_path.py` py_compile passed
- recorder MM `bash -n` passed
- focused diff-check clean
- isolated read-only MM verdict smoke produced `fee_path_feasibility.status=STANDARD_VIP_TIER_CAN_CLEAR_BUT_SCALE_OR_CAPITAL_GATED`

## Boundary

No production fill_sim replacement, no engine/API restart, no rebuild, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation. This is not promotion proof.
