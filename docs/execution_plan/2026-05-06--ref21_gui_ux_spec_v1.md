# REF-21 Replay GUI / UX Spec V1

**Date:** 2026-05-06  
**Status:** Draft companion spec for REF-21 V1.2  
**Owner:** PM  
**Co-review:** A3 + TW  
**Parent:** `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md`

---

## 0. Purpose

This spec isolates Replay GUI requirements from the engine governance plan.
Default UI must be simple enough for operator iteration while preventing the
mistake that a replay is a live/demo action or verified trading signal.

Until R3 exists, the default GUI must not present full-chain replay as runnable.
The provisional R1 dataset endpoint is hidden unless
`OPENCLAW_REPLAY_PREPARE_ENABLED=1` and the operator is in an R1 hardening
session.

---

## 1. Default Replay Panel

Primary title:

```text
7D Full-Chain Replay
```

Persistent badge:

```text
SIMULATION ONLY - no orders, no lease, no live writes
```

Required controls:

- time range: default `Last 7 days`,
- engine snapshot:
  - `Demo config snapshot`,
  - `Live config snapshot (simulation only, no orders)`,
- universe preset:
  - `Current scanner config`,
  - `Pinned only`,
  - `Top N dynamic`,
  - `Custom symbols` only in Advanced,
- starting balance:
  - default to selected snapshot equity if available,
  - otherwise `10,000 USDT assumed` with visible assumption badge,
- run button:
  - disabled until R3 is available,
  - enabled label after R3: `Run 7D Full-Chain Replay`.

No manifest JSON, fixture URI, experiment ID, or run ID is shown in default mode.

---

## 2. Feature Flag States

| State | UI Behavior |
|---|---|
| `OPENCLAW_REPLAY_PREPARE_ENABLED=0` | Full-chain dataset prepare controls hidden; default panel says engine is in design/hardening. |
| `OPENCLAW_REPLAY_PREPARE_ENABLED=1` and R3 unavailable | Show Advanced-only `Prepare Dataset` action with R1 hardening warning. |
| R3 available and feature enabled | Show default run action after healthcheck and auth pass. |
| Auth missing | Show locked state, no request body preview. |

The UI must not silently call `/api/v1/replay/full-chain/prepare` from the
default panel.

---

## 3. Progress, Cancel, And Time Estimate

Replay run states:

```text
idle -> validating -> building dataset -> scanning -> replaying -> finalizing -> complete
idle -> validating -> failed
... -> cancelling -> cancelled
```

Required UI elements:

- progress bar with current phase,
- elapsed time,
- estimated remaining time after first phase,
- cancel button after dataset validation,
- retry button only for terminal failed/cancelled states,
- duplicate-click protection while a manifest hash is running.

Cancellation must map to a terminal run state, not an ambiguous failure.

---

## 4. Result Summary

Primary metrics:

- post-fee return: show both `%` and `bps`,
- net PnL in quote currency,
- max drawdown,
- trade count,
- reject count,
- confidence badge,
- source-tier badge,
- data-quality warning count.

Confidence badge mapping:

| Tier / Flag | Badge |
|---|---|
| `IN_SAMPLE_SANDBOX` | In-sample sandbox |
| `IN_SAMPLE_EDGE_CURRENT` | Current-edge leakage warning |
| `S2_OPTIMISTIC_BOUND` | S2 optimistic bound |
| `S1_CALIBRATED` | S1 calibrated |
| `VERIFIED_REPLAY_ADVISORY` | Verified advisory |

Verdict mapping:

| Verdict | UI Label |
|---|---|
| `reject` | Reject |
| `defer_data` | Need better data |
| `defer_reality` | Needs demo/live validation |
| `research_only` | Research only |
| `demo_candidate` | Demo candidate, approval required |

The UI must not display `live_approved` from replay.

---

## 5. Error States

Each error state shows:

- reason code,
- plain-language summary,
- whether retry is safe,
- whether partial artifacts exist,
- next operator action.

Required mappings:

- `replay_full_chain_prepare_disabled`,
- Bybit 429 / 5xx,
- missing market data,
- fixture corrupt/missing,
- disk full,
- DB unavailable,
- scanner snapshot unavailable,
- edge snapshot unavailable,
- forbidden-path audit failed,
- MLDE/Dream timeout,
- cancellation complete.

---

## 6. Advanced Tab

Advanced contains:

- current REF-20 register/run/finalize controls,
- single-symbol smoke path,
- manifest JSON editor with validation,
- fixture URI view restricted to allowlisted schemes,
- experiment/run/report IDs,
- artifact links,
- R1 `Prepare Dataset` action when the feature flag is enabled.

Advanced entry should be visible but visually secondary in the Replay tab.

---

## 7. Agent Quota UI

When agent exploration is enabled, UI must show:

- actor / agent principal,
- current per-minute quota,
- batch K cap,
- operator override state if any,
- last batch status,
- cancellation control.

Agent runs must never expose direct parameter-apply controls in Replay.

---

## 8. Layout And Navigation

Replay is a top-level tab, separate from Paper. Paper remains optional behind
settings if retained.

The existing sidebar card labels remain:

- `Live`,
- `Demo`.

Replay is not a Paper subtab. Advanced Replay is nested inside Replay.

---

## 9. Acceptance

GUI acceptance requires:

1. default panel cannot call the provisional prepare endpoint while flag is off,
2. simulation-only badge is visible on desktop and mobile,
3. Live config snapshot label always includes "simulation only, no orders",
4. progress/cancel/retry states are visible and stable,
5. all B12 error codes map to bounded UI states,
6. Advanced contains manifest/fixture controls without cluttering default path,
7. source-tier and confidence badges match engine report values,
8. duplicate-click protection prevents duplicate run launch,
9. agent quota UI is present before exploration endpoints ship,
10. screenshots across desktop/mobile show no overlapping text or hidden critical
    warnings.
