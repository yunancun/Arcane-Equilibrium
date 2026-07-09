# P1-CRON-INSTALL-WAVE-1 — crontab Install Recipe (2026-05-18)

Status: **Operator-gated deploy** — E1 has authored 5 cron heartbeat
healthchecks `[75]`-`[79]` and added start-time `touch` sentinels to all 5
cron wrappers, but **the crontab entries themselves are NOT installed by
this dispatch**. Operator must run the install commands below on
`trade-core` after independent review.

## Scope

5 cron wrappers — source / test complete, crontab not yet installed:

| Wrapper | Schedule (proposed) | Cadence | Healthcheck slot | Sentinel mtime threshold |
|---|---|---|---|---|
| `panel_aggregator_health_cron.sh` | `*/5 * * * *` | 5 min | `[75]` | 7 min |
| `wave9_replay_no_live_mutation_watch.sh` | `0 * * * *` | hourly | `[76]` | 75 min |
| `replay_key_rotation_check.sh` | `0 9 * * *` | daily 09:00 | `[77]` | 25 h |
| `feature_baseline_writer_cron.sh` | `41 4 * * *` | daily 04:41 | `[78]` | 25 h |
| `blocked_symbols_30d_unblock_check_cron.sh` | `0 4 * * 0` | weekly Sun 04:00 | `[79]` | 8 days |

Sentinel root: `${OPENCLAW_DATA_DIR:-/tmp/openclaw}/cron_heartbeat/`.

## Design notes

- **Touch-at-start (not -at-end)** — `wave9_replay_no_live_mutation_watch.sh`
  ends with `exec python3 - <<PYEOF` (the shell process is replaced; no
  command after `exec` runs). Touch-at-start uniformly means
  "cron was triggered by the scheduler", which is what the healthcheck
  cares about. Whether the workload succeeded is reported by each cron's
  own log / exit code.
- **WARN-by-default** — `[75]`-`[79]` return WARN when a sentinel is missing
  or stale. Cron infra is **not promotion-blocking**. Set
  `OPENCLAW_CRON_HEARTBEAT_REQUIRED=1` if you want strict fail-closed mode.
- **No real workload run from Mac** — author authorization is source/test
  only. The smoke verifying the touch behavior used an isolated temp
  `OPENCLAW_DATA_DIR` with deliberately invalid `OPENCLAW_SECRETS_ROOT` so
  no PG / engine state was touched.

## Pre-install verification (run on `trade-core`)

```bash
# All 5 wrappers parse and are executable.
for f in /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/panel_aggregator_health_cron.sh /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_rotation_check.sh /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/feature_baseline_writer_cron.sh /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/blocked_symbols_30d_unblock_check_cron.sh; do bash -n "$f" && ls -la "$f"; done
```

```bash
# Verify the heartbeat directory is writable.
test -w "${OPENCLAW_DATA_DIR:-/tmp/openclaw}" || echo FAIL_DATA_DIR_NOT_WRITABLE
```

```bash
# Confirm no existing crontab entry for these wrappers (avoid duplicates).
crontab -l 2>/dev/null | grep -E "(panel_aggregator_health|wave9_replay_no_live_mutation|replay_key_rotation|feature_baseline_writer|blocked_symbols_30d_unblock)" || echo NO_EXISTING_ENTRIES
```

## Install — one-liner per wrapper (paste-safe)

**Each install command appends ONE line to the operator's existing crontab
without touching other entries.** All five lines use literal absolute paths
(cron does not expand shell variables) and set `OPENCLAW_BASE_DIR` /
`OPENCLAW_DATA_DIR` inline so the wrapper resolves paths regardless of the
cron job's HOME / PATH environment.

```bash
crontab -l 2>/dev/null | (cat; echo "*/5 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/panel_aggregator_health_cron.sh >>/tmp/openclaw/logs/panel_aggregator_health_cron.cron.log 2>&1") | crontab -
```

```bash
crontab -l 2>/dev/null | (cat; echo "0 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh >>/tmp/openclaw/logs/wave9_replay_no_live_mutation_watch.cron.log 2>&1") | crontab -
```

```bash
crontab -l 2>/dev/null | (cat; echo "0 9 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_rotation_check.sh >>/tmp/openclaw/logs/replay_key_rotation_check.cron.log 2>&1") | crontab -
```

```bash
crontab -l 2>/dev/null | (cat; echo "41 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/feature_baseline_writer_cron.sh >>/tmp/openclaw/logs/feature_baseline_writer_cron.cron.log 2>&1") | crontab -
```

```bash
crontab -l 2>/dev/null | (cat; echo "0 4 * * 0 OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/blocked_symbols_30d_unblock_check_cron.sh >>/tmp/openclaw/logs/blocked_symbols_30d_unblock_check_cron.cron.log 2>&1") | crontab -
```

Verify install:

```bash
crontab -l | grep -E "(panel_aggregator|wave9_replay_no_live|replay_key_rotation|feature_baseline_writer|blocked_symbols_30d_unblock)"
```

## Post-install verification

```bash
# Wait one cycle of the fastest cron (~6 minutes), then check sentinels.
ls -la /tmp/openclaw/cron_heartbeat/
```

```bash
# Run the passive-wait healthcheck; [75]-[79] should report PASS for any
# cron whose first cycle has fired, WARN for those still pending first fire.
cd /home/ncyu/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -E "\[(75|76|77|78|79)\]"
```

## Rollback

If a cron entry fires unwanted side-effects, remove just that entry:

```bash
crontab -l | grep -v "panel_aggregator_health_cron.sh" | crontab -
```

(replace the wrapper name with the one being rolled back; the line-grep
boundary is the absolute wrapper path).

## Author / Sign-off

- E1 author: source / test land 2026-05-18, no deploy actions
- E2 review: pending
- E4 regression: pending
- Operator gate (crontab install on trade-core): pending after E2 + E4
