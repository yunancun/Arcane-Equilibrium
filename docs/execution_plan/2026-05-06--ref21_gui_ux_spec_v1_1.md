# REF-21 Replay GUI / UX Spec V1.1

**Date:** 2026-05-06  
**Status:** Active GUI companion spec / R4 blocked  
**Owner:** PM  
**Co-review:** A3 + TW  
**Parent:** `2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md`  
**Supersedes:** `2026-05-06--ref21_gui_ux_spec_v1.md`

---

## 0. PM Decision

GUI V1 moved Replay out of Paper and added simulation-only language. V1.1 adds
the missing R4 gates: feature-flag behavior, second confirmation, 12-tab
navigation consistency, accessibility, i18n, agent quotas, and sign-off SOP.

R4 cannot begin until this spec is reviewed by A3 + TW and PM sign-off is
recorded with a clean git status.

---

## 1. Navigation Contract

Replay is a top-level tab:

- not nested under Paper,
- not hidden behind Paper enablement,
- Advanced Replay is nested inside Replay,
- sidebar cards remain `Live` and `Demo`,
- global 12-tab navigation naming must stay consistent with `CLAUDE.md §五`
  and the current console tab dictionary.

Paper, if retained, is optional behind settings and is not a PnL authority.

---

## 2. Default Panel States

| Engine Availability | Feature Flag | Default Panel |
|---|---|---|
| R3 unavailable | any | Disabled run button; design/hardening state. |
| R3 available | prepare flag off | Full run allowed only if runner healthcheck passes; prepare action hidden. |
| R3 unavailable | `OPENCLAW_REPLAY_PREPARE_ENABLED=1` | Advanced-only `Prepare Dataset`, with R1 warning. |
| auth missing | any | Locked state; no request preview. |

The default panel must never call `/api/v1/replay/full-chain/prepare`.

---

## 3. Required Controls

Default controls:

- time range default `Last 7 days`,
- engine snapshot:
  - `Demo config snapshot`,
  - `Live config snapshot (simulation only, no orders)`,
- universe preset:
  - `Current scanner config`,
  - `Pinned only`,
  - `Top N dynamic`,
- starting balance:
  - actual selected snapshot equity if available,
  - fallback `10,000 USDT assumed` badge,
- run button disabled until R3 healthcheck is green.

Advanced-only controls:

- custom symbols,
- manifest JSON editor,
- fixture URI,
- experiment/run/report IDs,
- R1 dataset prepare when flag is enabled.

---

## 4. Second Confirmation And Cooldown

Second confirmation is required when:

- user selects `Live config snapshot`,
- R3 result verdict is `demo_candidate`,
- operator overrides agent K cap,
- operator enables R1 dataset prepare flag.

Confirmation text must include:

```text
SIMULATION ONLY - no orders, no Decision Lease, no live writes
```

Cooldown:

- duplicate run with same manifest hash is blocked while active,
- same actor cannot launch more than one default full-chain run per 30 seconds,
- Advanced dataset prepare follows backend limiter and shows remaining cooldown.

---

## 5. Progress And Cancellation

States:

```text
idle -> validating -> building_dataset -> scanning -> replaying -> finalizing -> complete
idle -> validating -> failed
... -> cancelling -> cancelled
```

UI requirements:

- progress phase label,
- elapsed time,
- estimated remaining time after dataset phase,
- cancel button after validation,
- retry only on terminal `failed` or `cancelled`,
- cancellation terminal state must show whether artifacts were kept or deleted.

---

## 6. Result And Badge Mapping

Primary metrics:

- post-fee return `%` and `bps`,
- net PnL in quote currency,
- max drawdown,
- trade count,
- reject count,
- confidence badge,
- source-tier badge,
- data-quality warning count.

Tier badges:

| Engine Value | Badge |
|---|---|
| `IN_SAMPLE_SANDBOX` | In-sample sandbox |
| `IN_SAMPLE_EDGE_CURRENT` | Current-edge leakage warning |
| `S2_OPTIMISTIC_BOUND` | S2 optimistic bound |
| `S1_CALIBRATED` | S1 calibrated |
| `VERIFIED_REPLAY_ADVISORY` | Verified advisory |

Verdict labels:

| Verdict | UI |
|---|---|
| `reject` | Reject |
| `defer_data` | Need better data |
| `defer_reality` | Needs demo/live validation |
| `research_only` | Research only |
| `demo_candidate` | Demo candidate, approval required |

Replay UI must never display `live_approved`.

---

## 7. Error Mapping

Each error state must show reason code, plain-language summary, retry safety,
partial-artifact status, and next action.

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
- cancellation complete,
- promotion rejected by negative edge,
- promotion rejected by missing approval signature.

---

## 8. Agent Quota UI

Before exploration endpoints ship, UI must show:

- actor / agent principal,
- current per-minute quota,
- batch K cap,
- override reason if any,
- current batch state,
- cancel control,
- last promotion state and approver roles.

Replay UI must not include direct parameter-apply controls.

---

## 9. Accessibility And I18n

Acceptance:

- desktop and mobile screenshots for default, advanced, progress, error, and
  result states,
- no overlapping warning text,
- simulation-only badge visible without scrolling,
- keyboard navigation for run/cancel/retry/advanced,
- ARIA labels for progress and result badges,
- Chinese and English labels fit without truncating critical warnings,
- color is not the only signal for risk/confidence.

---

## 10. Sign-Off SOP

Before R4 implementation:

1. A3 reviews layout and operator workflow.
2. TW reviews Chinese/English copy and tab dictionary consistency.
3. PM checks `git status --short` is clean before sign-off.
4. PM records sign-off path in `docs/CCAgentWorkSpace/PM/workspace/reports/`.
5. Any GUI implementation PR includes screenshots and static asset tests.

---

## 11. Acceptance

R4 acceptance requires:

1. default panel cannot call the provisional prepare endpoint,
2. simulation-only badge visible on desktop/mobile,
3. live snapshot label includes "simulation only, no orders",
4. progress/cancel/retry states stable,
5. all V1.3 B12/B13 error/promotion failures mapped,
6. Advanced contains manifest/fixture controls without cluttering default path,
7. tier/confidence badges match engine values,
8. duplicate-click and cooldown protections work,
9. agent quota UI exists before agent endpoints ship,
10. accessibility/i18n checks pass,
11. screenshots show no text overlap or hidden critical warnings.
