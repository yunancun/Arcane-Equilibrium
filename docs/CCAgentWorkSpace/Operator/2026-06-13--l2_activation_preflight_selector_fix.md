# 2026-06-13 — L2 activation preflight + `[83]-[89]` selector fix

## Verdict

PASS-SOURCE-FIX / RUNTIME-ACTIVATION-BLOCKED-BY-OPERATOR-WINDOW.

`[82]` soak gate is no longer blocking L2/P2 activation. The remaining blocker is an operator-approved low-risk restart / migration apply window for V138 -> V139 and subsequent L2 activation steps.

## Read-only runtime facts

- Linux true DB `[81]/[82]` recheck at `2026-06-13T07:07:32Z`: `[81] PASS`; `[82] PASS`, window `53.1h`, probes `1593`, success rate `1.0000`, zero flag-OFF/regression/fail-streak.
- Live `_sqlx_migrations` head remains `137`, all applied rows success=true.
- V138/V139 objects are still absent: `research.pre_registered_hypotheses`, `research.alpha_wealth_ledger`, `research.alpha_wealth_debit_state`, `agent.agent_memory`, `agent.agent_memory_embedding_meta`.
- L2 runtime rows unchanged for activation gating: `agent.l2_calls=1`, `learning.l2_gate_seam_log=4`, `agent.l2_consequential_marks=0`.
- Runtime flags checked from `basic_system_services.env`: `OPENCLAW_AUTO_MIGRATE=0`; `OPENCLAW_ALPHA_WEALTH_RECONCILER`, `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT`, `OPENCLAW_L2_MEMORY_PIPELINE`, `OPENCLAW_L2_MEMORY_CRON_APPLY`, `OPENCLAW_L2_MEMORY_EMBED_BACKFILL`, Telegram creds all unset.
- Gate-B latest artifact is still `WATCH_ONLY`: 23 candidates, `alertable=0`, `start_now=0`, `schedule=0`, `watch_only=1`.

## Found gap

`helper_scripts.db.passive_wait_healthcheck.runner` had imported and full-run-wired `[83]-[89]`, but `_run_selected_cursor_checks()` still only allowed `[1]`, `[4]`, `[81]`, `[82]`, `[Xb]`. Therefore activation preflight could not run `--check 83 ... --check 89` directly.

`cargo sqlx migrate info` was also unavailable on Linux because `cargo-sqlx` is not installed. This is an environment/tooling gap, not a migration state change.

## Source change

- `helper_scripts/db/passive_wait_healthcheck/runner.py`: add narrow selector support for `[83]`-`[89]`.
- `helper_scripts/db/test_lease_ipc_soak_healthcheck.py`: add routing test covering `[83]`-`[89]`.

## Verification

- `./venvs/mac_dev/bin/python -m pytest helper_scripts/db/test_lease_ipc_soak_healthcheck.py -q` -> `48 passed, 1 skipped`
- `./venvs/mac_dev/bin/python -m pytest helper_scripts/db/passive_wait_healthcheck/test_checks_alpha_wealth_fdr.py helper_scripts/db/test_l2_memory_healthchecks.py -q` -> `32 passed`
- `./venvs/mac_dev/bin/python -m py_compile helper_scripts/db/passive_wait_healthcheck/runner.py helper_scripts/db/test_lease_ipc_soak_healthcheck.py` -> PASS

## Post-sync Linux verification

After Mac -> GitHub -> Linux sync, Linux `trade-core` ran the new narrow selector against the live DB:

```bash
python3 -m helper_scripts.db.passive_wait_healthcheck.runner --check 83 --check 84 --check 85 --check 86 --check 87 --check 88 --check 89
```

Result: `SUMMARY: ALL PASS`.

- `[83]-[86]`: PASS-skip, V138 research FDR tables absent.
- `[87]`: PASS, `sealed_rows_with_post_insert_updates=0`.
- `[88]`: PASS-skip, `OPENCLAW_L2_MEMORY_PIPELINE != 1`.
- `[89]`: PASS-skip, `OPENCLAW_L2_MEMORY_EMBED_BACKFILL != 1`.

## Boundary

No CI. No deploy, rebuild, service restart, migration apply, DB write, auth/risk/order/trading mutation, or model call.

## Next

Before the operator activation window, rerun Linux narrow preflight:

```bash
python3 -m helper_scripts.db.passive_wait_healthcheck.runner --check 83 --check 84 --check 85 --check 86 --check 87 --check 88 --check 89
```

Expected current result before V138/V139 apply: `[83]-[87]` PASS-skip for absent V138 tables / V132 status check, `[88]-[89]` PASS-skip while memory flags remain off. Actual V138/V139 apply still requires an explicit operator window because it is an engine auto-migrate / restart path.
