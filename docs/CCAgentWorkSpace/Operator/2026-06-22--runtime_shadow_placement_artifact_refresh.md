# Operator Note: Runtime Shadow Placement Artifact Refresh

Date: 2026-06-22
Runtime source: `5b25a5e1`

Linux runtime artifacts were refreshed after v418 source sync. This was artifact-only and read-only except for local `/tmp/openclaw` report files.

Operational meaning:

- Demo is still accumulating order evidence: 6 recent Demo/live_demo orders were reviewed.
- It is not accumulating fill-backed learning evidence: fills are still 0.
- Root cause for this sample is placement, not missing BBO: all 6 orders were deep passive no-touch; max best-touch gap was `1530.6074bp`.
- The near-touch shadow repair would submit 6/6 observed orders, reduce max initial touch gap to `58.2092bp`, and 4/6 would later be crossed by BBO.
- Candidate-matched order count is still 0, so this is mechanical touchability evidence, not alpha proof.
- `alpha_discovery_runtime_killboard_v9` now sets top task to `bounded_probe_placement_repair`.

Do not lower Cost Gate globally from this evidence. The next runtime-changing step requires separate operator authorization: patch the bounded Demo authority path to use fresh BBO, maker-side near-touch post-only limits, and skip-and-record when gap exceeds `75bp`.

After that, promotion still requires candidate-matched order-to-fill, fill/fee/slippage, matched blocked-control, bounded result-review, and execution-realism evidence.

No CI was run, no cron was installed, no env was changed, no service was restarted, no PG write occurred, no Bybit trading/private call was made, and no probe/order authority or promotion proof was granted.
