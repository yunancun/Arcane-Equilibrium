# S2 Gate-B PreLaunch Phase-Transition Probe Plan

Date: 2026-06-01
Status: PM/BB/MIT prep complete; probe implementation and 24h run still require separate scope
Owner chain: PM -> BB + MIT -> QC -> E1 only after a separate isolated-probe task
Mode: docs/design/read-only. No DB write, migration apply, runtime deploy, auth, order, production collector, strategy linkage, endpoint ingestion, backfill run, alpha scoring, or promotion verdict.

## Verdict

S2 Gate-B should be a 24h isolated, read-only Bybit public-market probe that
empirically verifies PreLaunch phase-transition semantics before any production
listing-capture collector implementation.

The probe may prove connection safety and topic behavior. It does not prove
alpha, does not authorize production collector code, and does not open strategy
intent linkage.

If no real PreLaunch transition occurs during the 24h window, the result is
`INCONCLUSIVE_NO_TRANSITION`, not `PASS_PHASE_TRANSITION`.

## 1. Probe Scope

Allowed REST surface:

```text
GET /v5/market/instruments-info?category=linear&status=PreLaunch&limit=1000
```

The probe must handle pagination and capture for every observed PreLaunch
symbol:

- `launchTime`
- `isPreListing`
- `preListingInfo.curAuctionPhase`
- `preListingInfo.phases`

Allowed public WS topics:

- `kline.1.{PreLaunchSymbol}`
- `publicTrade.{PreLaunchSymbol}`
- `kline.1.BTCUSDT` as control
- `publicTrade.BTCUSDT` as control

Do not include in Gate-B:

- private/order/account/auth endpoints
- production WS connections
- scanner relay topics
- `allLiquidation.*`
- legacy `liquidation.*`
- `price-limit.*`
- `adl-notice.*`
- orderbook topics unless BB opens a separate isolated orderbook probe

## 2. Phase Semantics To Verify

The probe must observe or explicitly fail to observe transitions across:

- `NotStarted`
- `CallAuction`
- `CallAuctionNoCancel`
- `CrossMatching`
- `ContinuousTrading`
- `Finished`

Expected empirical checks:

| Check | Required observation |
|---|---|
| Kline start | Kline data starts no earlier than `CrossMatching`. |
| Public trade start | Public trade data starts at `ContinuousTrading`. |
| Subscribe ack | `success:true` for every allowed topic subscription. |
| Handler support | No `handler not found` for allowed topics. |
| BTC controls | BTCUSDT control topics remain alive and unpoisoned. |
| Parser | Unknown phase or malformed payload is fail-visible. |

## 3. Isolation Contract

Gate-B must run as a standalone probe:

- independent process or script
- independent public WS connection
- no shared `WsTopicChange` channel
- no production `SymbolRegistry` dependency
- no scanner state
- no strategy route judgment
- no Decision Lease or order intent path
- no TOML deployment edits
- no DB writes
- no IPC trade commands
- no auth or order client construction

Abort or fail the probe on:

- `handler not found`
- unexpected `success:false`
- stalled BTC control topics
- parse failure that prevents phase classification
- reconnect loop
- topic poisoning that affects controls

Reason: the current Rust symbol registry has a single active snapshot surface.
Production scanner-added topics can feed strategy context, so Gate-B must stay
outside that path.

## 4. Evidence Artifacts

Recommended artifact root:

```text
/tmp/openclaw/aeg_gate_b_runs/<run_id>/
```

Minimum files:

| File | Purpose |
|---|---|
| `manifest.json` | Run metadata, git sha, dirty flag, start/end, probe version. |
| `rest_phase_poll.jsonl` | Poll observations from `instruments-info`. |
| `ws_control.jsonl` | BTC control-topic liveness and subscribe acks. |
| `ws_messages.jsonl` | PreLaunch topic acks/messages or sampled raw frames. |
| `topic_summary.csv` | Message counts and status by symbol/topic. |
| `phase_transition_summary.json` | Per-symbol phase timeline and semantic checks. |
| `verdict.json` | Final Gate-B verdict and reasons. |

Required JSONL row fields:

```text
run_id, ts_utc, git_sha, git_dirty, probe_version, source, symbol,
endpoint_or_topic, event_type, status, curAuctionPhase, launchTime,
phase_start, phase_end, subscribe_success, ret_code, ret_msg,
handler_not_found, message_count, kline_confirm, volume, trade_count,
btc_control_alive, connection_id_or_seq, error
```

## 5. Verdict Labels

Allowed final labels:

| Label | Meaning |
|---|---|
| `PASS_PHASE_TRANSITION` | A real phase transition was observed and topic semantics matched expectations. |
| `PASS_CONNECTION_ONLY` | Allowed topics and controls stayed safe, but no real transition was observed. |
| `INCONCLUSIVE_NO_TRANSITION` | 24h window had no real transition; semantics remain unproven. |
| `FAIL_TOPIC_REJECTED` | Allowed topic rejected, `handler not found`, or subscribe failure. |
| `FAIL_CONTROL_POISONED` | BTC controls stalled or were affected by probe subscriptions. |
| `FAIL_DOC_SEMANTIC_MISMATCH` | Observed exchange behavior contradicts the expected phase semantics. |

`PASS_CONNECTION_ONLY` is not sufficient for production collector IMPL.

## 6. Capture-Only Collector Boundary

Before any production collector implementation, design must split:

- `capture_only_symbols`
- `trading_symbols`

Allowed production subscription shape after future review:

- WS subscription set may be the union of capture-only and trading symbols.
- Scanner, strategy, intent, Decision Lease, and IPC trade command paths may
  read only `trading_symbols`.

Capture-only symbols must never enter:

- scanner scoring
- strategy route judgment
- Decision Lease
- order intent
- IPC trade commands
- TOML deployment state
- alpha promotion verdicts before the AEG evidence chain is complete

Current code has only one active `SymbolRegistry::snapshot()` surface, so
collector IMPL remains blocked until registry/consumer separation is designed
and reviewed.

## 7. Gates Before Implementation

Before any production listing collector implementation:

1. Gate-B records a real `PASS_PHASE_TRANSITION`, not only connection safety.
2. BB confirms public topic safety, topic limits, subscribe rate discipline,
   reconnect behavior, and no control poisoning.
3. MIT confirms artifact lineage and capture evidence schema.
4. PA confirms capture-only architecture and no strategy leakage.
5. E2 reviews registry and consumer separation.
6. E4 adds tests proving capture-only symbols do not enter strategy intent.
7. PM/operator explicitly opens a scoped implementation task.

Still blocked:

- production collector runtime
- strategy linkage
- DB writes
- new migration
- endpoint ingestion/backfill
- alpha scoring or promotion verdict
- `n>=30` true listing-capture evidence, which requires future forward
  accumulation after a safe collector exists
