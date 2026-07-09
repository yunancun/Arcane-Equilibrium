# P1/P2 Sequential Closeout — 2026-05-15

Scope completed in order:

1. `P1-FILL-LINEAGE-MONITOR`
2. `P1-STARTUP-BURST-MITIGATION`
3. `P1-V083-HALT-SESSION-CTX`
4. `P1-W6-5-ML-METRICS`
5. `P1-AUDIT-PERF-5`
6. `P1-AUDIT-AI-UX-7`
7. `P2-N2-1 btc_lead_lag.rs`

## Results

- Agent-spine channel monitor added through Rust IPC method
  `get_agent_spine_channel_metrics` and `[55]` healthcheck fail-soft monitor.
  The monitor reports initial send failures separately from final loss.
- Startup-burst mitigation raised the bounded agent-spine channel capacity from
  8192 to 32768 through a named constant and kept the existing retry/loss
  semantics intact.
- V083 current-log follow-up is closed from this task scope: current engine log
  grep had no `chk_fills_close_has_entry_context_id_v083` / `halt_session`
  hits. A full healthcheck run still has unrelated `[42b]` and `[56]` FAILs.
- W6-5 is implemented as a report-only ML utility. It supports 1/15, 1/100,
  1/170, 1/300, and 1/500 sample-weight ratios with 5-fold walk-forward
  purge+embargo metrics: RMSE CI, IS/OOS gap, cross-fold consistency, PSI+KS,
  and cost_gate distribution shift. It does not deploy a production cron or
  mutate scorer artifacts.
- W-AUDIT-5 F-20 damaged dump cleanup completed on `trade-core` by deleting
  the damaged Trash directories. Dirty `/tmp/tradebot_mag*` repos were preserved
  because both contain uncommitted work.
- W-AUDIT-7 F-07/CEA env is verified operationally: provider store has Anthropic
  configured, engine/API process env has nonzero `ANTHROPIC_API_KEY`, and both
  `OPENCLAW_COST_EDGE_ADVISOR=1` and `OPENCLAW_H_STATE_GATEWAY=1` are present.
  No extra restart was performed because the running processes already carry the
  target env.
- `btc_lead_lag.rs` was split into root re-export plus focused implementation
  files: `producer.rs`, `ingest.rs`, `snapshot.rs`, and `db_writer.rs`.
  Implementation files are all under 500 LOC; public re-export paths remain
  stable.

## Verification

- `python3 -m pytest helper_scripts/db/test_agent_spine_healthcheck.py -q`
- `cargo test -p openclaw_engine --lib test_dispatch_agent_spine_channel_metrics`
- `cargo test -p openclaw_engine --lib channel_metrics_returns_stable_shape`
- `cargo test -p openclaw_engine --lib method_registry`
- `cargo test -p openclaw_engine --lib fill_completion_burst_with_configured_cap_no_drop`
- `python3 -m pytest program_code/ml_training/tests/test_sample_weight_sensitivity.py -q`
- `cargo test -p openclaw_engine --lib btc_lead_lag --no-fail-fast`

## Residuals

- True-live remains blocked by alpha/LG/ops gates.
- Stage 1 demo remains blocked because A4-C RCA is closed no-revive and no
  eligible Stage 0R cohort exists.
- C1 liquidation topic proof remains running separately under PID `4100789` on
  `trade-core`.
