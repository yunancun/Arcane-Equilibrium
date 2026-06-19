# TODO v218 source-sync / passive-watch refresh

## Verdict

PM checkpoint：`TODO.md` masthead 與 §0 source-sync 已從 v216 `61e1a6d2` 修正到 v217 commit `737356a5`；本輪 passive-watch recheck 無新可執行事件，所有相關 gate 保持開啟。

## Evidence

- Mac `srv`: `HEAD=origin/main=737356a5e33e5121c9aa2aa71ce2ba0ddcdc9ffa`.
- Linux `trade-core`: `/home/ncyu/BybitOpenClaw/srv` `HEAD=737356a5e33e5121c9aa2aa71ce2ba0ddcdc9ffa`; dirty state only has unrelated untracked `docs/CCAgentWorkSpace/E1/workspace/reports/vol-event-robust-ruling.md` and `helper_scripts/research/variance_risk_premium/`.
- Watchdog: `engine_alive=true`, demo snapshot age `23.8s`.
- Gate-B latest artifact `/tmp/openclaw/gate_b_watch/gate_b_watch_latest.json` generated `2026-06-19T00:12:01.624466Z`: `status=WATCH_ONLY`, candidate_counts `total=21`, `alertable=0`, `start_now=0`, `schedule=0`, `watch_only=1`, alerts_sent=0.
- flash_dip: `/tmp/openclaw/flash_dip_buy_entry_ts.json` is `{}`; `/tmp/openclaw/flash_dip_death_rate_last_success.json` absent before first scheduled 06:53 CEST natural run.
- L2 memory: cursor is `{"last_success_utc_date": "2026-06-17"}`; day stats for 2026-06-12..17 all `materials_l2=0`, `stored=0`, `dropped=0`.
- Passive healthcheck at `2026-06-19T00:21:31Z` still overall `FAIL`: `[74] close_maker_reject_samples` has attempts=199/postonly=26/max_pending=0; `[56] live_pipeline_active` still fails because live authorization JSON is missing.

## Decision

No probe/autostart/promotion/archive action is authorized from this evidence. Continue waiting for:

- Gate-B fresh `ACTIONABLE_*`.
- flash_dip natural fill and death-rate success evidence.
- L2 first non-empty material day or B3 shadow runtime evidence.
- operator signed live-auth renew.
- E4 review before trusting Stage0R runner outputs.

## Boundary

Docs/TODO + read-only Linux file/healthcheck only. No CI full suite, no deploy/rebuild/restart, no model call, no DB write, no credential/key/secret/runtime/auth/risk/order/trading mutation.
