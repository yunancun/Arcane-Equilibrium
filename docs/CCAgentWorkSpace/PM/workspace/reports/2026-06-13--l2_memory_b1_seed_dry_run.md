# 2026-06-13 — L2 memory B1 seed dry-run

## Verdict

`PASS-DRY-RUN / APPLY-NOT-EXECUTED`.

B1 dry-run completed after V139 activation. This step did not write DB rows and did not enable any L2 memory runtime flags.

## Scope

Executed:

- inspect `seed_agent_memory.py` contract
- run Linux `seed_agent_memory.py --dry-run`
- verify V139 object exists and `agent.agent_memory` stayed empty
- run focused source verification for the seed CLI

Not executed:

- `seed_agent_memory.py --apply`
- manual V140
- `OPENCLAW_L2_MEMORY_PIPELINE=1`
- `OPENCLAW_L2_MEMORY_CRON_APPLY=1`
- `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`
- model calls
- Gate-B probe
- rebuild/restart

## Runtime baseline

- Host: Linux `trade-core`
- Repo head: `5036c9673b990fee43220cb432e3e6107914f0e3`
- SQL head: V139, success=true
- `agent.agent_memory`: exists
- `agent.agent_memory` rows before/after dry-run: `0`
- `agent.lessons WHERE lesson_type='dead_mode'`: `6`

## Dry-run command

```bash
cd /home/ncyu/BybitOpenClaw/srv
python3 helper_scripts/memory/seed_agent_memory.py --dry-run
```

Saved artifact:

- run id: `l2_memory_b1_seed_dry_run_20260613T161740Z`
- log: `/tmp/openclaw/l2_memory_b1_seed_dry_run_20260613T161740Z.log`
- sha256: `f06a301a97f012dbe8a9a5030e266cc0652e35b61e55aaf3b134493667023950`

Dry-run summary:

- A source `agent.lessons lesson_type='dead_mode'`: deferred by design because dry-run opens 0 DB connections.
- B source `memory/MEMORY.md`: 93 candidate rows.
- Sensitive/allowlist skip list: 6 rows.
- Idempotency anchor: `record_id = mem:seed:sha12(content)`.
- Apply path would use `INSERT ... ON CONFLICT DO NOTHING`.

Skipped rows:

```text
project_2026_06_11_five_repo_subagent_token_eval.md  reason=sensitive_keyword:token
reference_ultracode_full_audit.md                    reason=prefix_not_whitelisted
reference_remote_access.md                           reason=prefix_not_whitelisted
reference_restart_script.md                          reason=prefix_not_whitelisted
reference_external_tools.md                          reason=prefix_not_whitelisted
feedback_external_tool_authority.md                  reason=excluded_section:External tool authority
```

Post-run DB verification:

```text
agent_memory_rows_after|0
```

## Focused verification

- Linux `python3 -m py_compile helper_scripts/memory/seed_agent_memory.py`: PASS
- Mac focused pytest: `./venvs/mac_dev/bin/python -m pytest helper_scripts/memory/test_seed_agent_memory.py -q` -> `39 passed`

## Notes

The dry-run intentionally does not preview the 6 A-source `agent.lessons` rows because opening DB connections in dry-run is forbidden by the seed CLI contract. The read-only count was checked separately through `psql`.

The next step is an operator decision:

- allow `seed_agent_memory.py --apply` as a bounded DB write, or
- keep B1 at dry-run and move to manual V140 / pipeline planning later.
