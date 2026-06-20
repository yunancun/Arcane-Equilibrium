# 2026-06-20 FillSim Cost-Wall Instrumentation

PM added cost-wall fields to `fill_sim.py` and verified them with a fresh-L1 trade-core smoke. This did not touch the order path, auth, risk, engine runtime, production DB, or production fill_sim report.

Runtime temp artifact:

- `/tmp/openclaw/research/fillsim/fillsim_cost_wall_smoke_20260620T003611Z.json`
- 15min fresh-L1 window
- `l1_rows_post_filter=194305`
- `crossed_after_filter=0`
- `l1_max_age_hours=0.001`

Current-regime read:

- back-of-queue fill_only: half_spread `0.841bp`, adverse@15 `2.206bp`, net maker@15 `-5.365bp`, requires about `0.682bp/side` maker rebate to break even.
- front-of-queue fill_only: half_spread `0.835bp`, adverse@15 `1.631bp`, net maker@15 `-4.796bp`, still requires about `0.398bp/side` maker rebate to break even.

Conclusion: the current MM blocker is structural fee/adverse-selection cost wall, not just stale L1 or pessimistic queue position. This is still a single-regime diagnostic, not CP-3 go/no-go or promotion proof.

Follow-up: daily `recorder_mm_verdict_cron.sh` now emits the same break-even/fee-shortfall/rebate fields using live maker markout spread capture plus fill_sim adverse selection. Alpha discovery `arms_raw` preserves `cost_wall_summary`; action gates are unchanged.

Linux smoke after selective deploy: manual read-only MM verdict status at `2026-06-20T00:45:49Z` reported best `ARBUSDT` net `-0.1437bp` with fee shortfall `0.1437bp`, but sample was only `n_maker_fills=1`; BTC/ETH still require rebate. No promotion proof.
