# 2026-06-13 — L2 memory B2 seed apply

## Verdict

`PASS-APPLY / FLAGS-STILL-OFF`.

After operator approval, B2 executed `seed_agent_memory.py --apply` on Linux and seeded V139 `agent.agent_memory`.

## Scope

Executed:

- Linux `seed_agent_memory.py --apply`
- post-apply DB verification
- focused source tests
- passive `[83]-[89]` healthcheck

Not executed:

- manual V140
- `OPENCLAW_L2_MEMORY_PIPELINE=1`
- `OPENCLAW_L2_MEMORY_CRON_APPLY=1`
- `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`
- `OPENCLAW_L2_MEMORY_RECALL=shadow|1` (B3 recall flag; not executed)
- model calls
- Gate-B probe
- CI
- rebuild/restart

## Baseline

- Host: Linux `trade-core`
- Repo head before apply: `859a7bce31c513512a66aacd2880ebd86357c849`
- SQL head: V139, success=true
- `agent.agent_memory` before apply: `0`
- `agent.lessons WHERE lesson_type='dead_mode'`: `6`

## Apply command

```bash
cd /home/ncyu/BybitOpenClaw/srv
python3 helper_scripts/memory/seed_agent_memory.py --apply
```

Saved artifact:

- run id: `l2_memory_b2_seed_apply_20260613T163835Z`
- log: `/tmp/openclaw/l2_memory_b2_seed_apply_20260613T163835Z.log`
- sha256: `4b050252c803b193862d3758cf01d1ebb17fd907371369201e05f6764393a02c`

Apply summary:

```text
A source rows: 6
B source rows: 93
inserted: 99
already_present: 0
skipped by sensitive/allowlist rules: 6
VERIFY-en hits: 5
VERIFY-zh hits: 5
exit: 0
```

## Post-apply DB verification

```text
head|139|success=true
agent_memory_total|99
scene|seed:dead_mode|6
scene|seed:memory_index|93
mem_type_priority|incident|p70|59
mem_type_priority|rule|p80|34
mem_type_priority|rule|p90|6
source_lesson|6
source_memory_topic|93
status_active|99
embedding_pending_true|99
duplicate_record_ids|0
seed_batch_2026_06_11|99
```

Flags remain off/unset:

```text
OPENCLAW_L2_MEMORY_PIPELINE=<unset>
OPENCLAW_L2_MEMORY_CRON_APPLY=<unset>
OPENCLAW_L2_MEMORY_EMBED_BACKFILL=<unset>
OPENCLAW_L2_MEMORY_RECALL=<unset>
```

## Verification

- Linux `python3 -m py_compile helper_scripts/memory/seed_agent_memory.py`: PASS
- Mac focused pytest: `./venvs/mac_dev/bin/python -m pytest helper_scripts/memory/test_seed_agent_memory.py -q` -> `39 passed`
- Linux passive healthcheck `[83]-[89]`: `SUMMARY: ALL PASS`
  - `[88]` PASS-skip because `OPENCLAW_L2_MEMORY_PIPELINE != 1`
  - `[89]` PASS-skip because `OPENCLAW_L2_MEMORY_EMBED_BACKFILL != 1`
- Linux engine process remained alive: PID `3607315`

## Notes

The apply path is bounded to `agent.agent_memory` inserts with `ON CONFLICT DO NOTHING`. This run did not enable any memory pipeline or recall behavior. Seeded rows are stored but dormant until the separate pipeline/recall/model gates are approved.

The psql collation warning (`database "trading_ai" has no actual collation version`) was observed before and after apply; it is not specific to B2 and did not block the operation.

## Remaining gates

- manual V140 pgvector readiness/apply decision
- L2 memory pipeline flag-on
- cron apply
- embedding backfill
- E2E true model call
- P2p sentinel / P5 feedback-quality-GUI
