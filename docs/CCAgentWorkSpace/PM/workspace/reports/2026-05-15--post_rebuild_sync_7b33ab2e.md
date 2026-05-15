# 2026-05-15 - Post-rebuild Sync 7b33ab2e

## Scope

Operator authorized push / three-side sync / rebuild after the OI-confirmed 5m
feasibility probe.

Boundary: no strategy/risk config mutation, no DB migration, no live auth
renewal, no paper/demo canary launch, and no Stage 1/2 transition.

## Source Sync

Mac, origin, and Linux `trade-core` are synchronized at:

```text
7b33ab2e fix: explain live auth auto revoke and throttle gui polling
```

This includes the prior PM docs checkpoint:

```text
2657621b [skip ci] docs: record oi 5m feasibility probe
```

`7b33ab2e` was already present on origin and local main before Linux rebuild.
Linux `git pull --ff-only` reported already up to date.

## Rebuild

Command run on `trade-core`:

```bash
PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth
```

Result:

- release build completed in `34.41s`;
- engine restarted with PID `4032406`;
- API restarted with PID `4032675`;
- `--keep-auth` warned that signed live authorization was already missing at
  `/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json`;
- no live auth renewal was attempted.

Build warning:

- pre-existing Rust warning: `ma_crossover/helpers.rs::make_intent` unused.

## Post-rebuild Checks

Watchdog after rebuild:

- `engine_alive=true`;
- `demo.alive=true`;
- `paper.alive=true` at the sampled moment;
- `live.alive=false`, with stale live snapshot;
- latest rebuild output also reported `ticks=3352966`, `fills=10`,
  `paused=True`.

Direct healthcheck probes:

| Check | Status | Message |
|---|---|---|
| `[27] intents_counter_freeze` | PASS | `demo: stale=4.7m, 30min_n=16`; `live_demo: stale=143.9m, 30min_n=0 — engine restarted 7.3m ago; intent counter baseline pending`; `live: never produced an intent` |
| `[66] panel_freshness` | PASS | funding and OI delta collectors healthy at ~51s |
| `[67] feature_baseline_readiness` | PASS | 646 active rows / 19 symbols / 34 feature names |

Full passive wrapper note:

- `bash helper_scripts/db/passive_wait_healthcheck.sh --quiet` produced no
  output for more than 5 minutes and was terminated.
- Direct targeted probes above were used instead.

## Verdict

Runtime rebuild loaded the source line, including the `[27]` qty-rounding audit
shape fix, but `P1-INTENT-FREEZE-27` remains **runtime pending** until `[27]`
passes outside fresh-restart grace.

Stage 1 demo micro-canary remains blocked:

- A4-C Stage 0R is still GATE-RED.
- OI-confirmed 5m feasibility probe is underpowered/negative.
- Live authorization is absent and was not renewed.
- True-live remains blocked by LG/OPS/EDGE gates.

Next engineering path remains A4-C revise/archive plus W-AUDIT-8a Phase C/D,
then 8c liquidation and 8b funding skew.
