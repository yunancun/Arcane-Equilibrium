# Operator Brief - AEG-S3 Execution Realism + Gate-B Watch

Date: 2026-06-12
Code checkpoint: `c35f8425`

## Done

- Added artifact-only `aeg_s3_event_execution_realism` adapter.
- It turns matched execution observation JSONL rows into canonical
  `execution_realism.json` for `listing_fade` / `funding_revive`.
- `oi_delta` remains fail-closed because basket samples do not have one event symbol.
- No CI, deploy, rebuild, DB write, auth, order, risk, or trading mutation.

Verification:

- Mac focused AEG regression: `88 passed`.
- Linux smoke: `4 passed`.
- compileall OK; forbidden runtime/DB/Bybit route grep had no hits.

## Gate-B Timing

Gate-B is not "wait 24h from now".

- Once a real PreLaunch / conversion / listing transition window exists, one isolated
  probe attempt is 24h.
- If no real transition happens inside that attempt, verdict is
  `INCONCLUSIVE_NO_TRANSITION`; not usable alpha evidence.
- Therefore the real wait is: next valid Bybit listing/conversion window + 24h probe,
  not a fixed calendar duration.

## Current Bybit Check

Checked official Bybit new listing announcements and public market REST on 2026-06-12.

- Latest derivatives listings on the announcement page/API are 2026-06-09:
  `AAOIUSDT`, `IRENUSDT`, `ONDSUSDT`, `QNTXUSDT`, `CTRUSDT`.
- They are already "Trading is now open" / listed. They are not future Gate-B capture
  windows.
- Live `instruments-info?category=linear&status=PreLaunch` currently returns
  `BPUSDT` only.
- `BPUSDT` has `launchTime=2026-03-16T05:45:14Z` and
  `curAuctionPhase=ContinuousTrading`; this is an old pre-market contract, not today's
  new opening.

Actionable watch target:

- Watch for `BPUSDT` conversion-to-standard announcement, or the next new
  Pre-Market / PreLaunch listing announcement.
- Existing Bybit announcement sentinel cron is already installed (`7,37 * * * *`) and
  alert-only. This is the first tripwire; do not auto-trigger trading or production
  collector behavior from it.

## Start Gate-B Only When

- A fresh Pre-Market / PreLaunch / conversion announcement appears, or live public
  REST shows a new `PreLaunch` symbol near transition.
- Isolated `aeg_gate_b_probe` can run without production WS/scanner/strategy/DB/order/auth.
- BTC control WS liveness remains healthy.
- The probe can collect `capture_lag.jsonl`, `markout.jsonl`, `verdict.json`, and
  manifest artifacts.

Next mainline step: keep Gate-B event-triggered via announcements/public REST, while
parallel execution-realism waits for `>=30` matched empirical observations.
