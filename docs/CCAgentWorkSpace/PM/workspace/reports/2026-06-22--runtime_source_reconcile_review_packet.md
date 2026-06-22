# Runtime Source Reconcile Review Packet

## 結論

2026-06-22 的 Mac-side read-only remote probe against target `1f15818f` 顯示：

- runtime `trade-core` HEAD：`917be4cc9a3d3549328155f1863d42400c70267f`
- runtime `origin/main`：`1401848b5f61136051d2b623c71dbad006a99459`
- local/GitHub target：`1f15818f77fbd0a2fb8bb10048e50913966a00cb`
- runtime target object：不可用
- runtime dirty/untracked：56
- content-equivalent to target：43
- review-required：13

處置建議：13 條 review-required path 均可進入 operator-approved target-wins reconcile；其中唯一 runtime-only report 已在本 checkpoint 以格式清理版本納入 repo。這不授權 runtime fetch/pull/reset/clean/stash、cron install、DB write、Bybit call、Cost Gate lowering 或 demo probe/order authority。

## Review Path Disposition

| Path | Probe class | Review finding | Recommendation |
|---|---|---|---|
| `TODO.md` | tracked dirty differs | runtime copy is shorter/stale active-state doc | target wins |
| `docs/CCAgentWorkSpace/PM/memory.md` | tracked dirty differs | runtime copy is shorter/stale PM memory | target wins |
| `docs/CLAUDE_CHANGELOG.md` | tracked dirty differs | runtime copy is shorter/stale changelog | target wins |
| `helper_scripts/SCRIPT_INDEX.md` | tracked dirty differs | runtime copy is shorter/stale script index | target wins |
| `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py` | tracked dirty differs | local target has additional Cost Gate learning state symbol `_cost_gate_learning_lane_state`; no remote-only symbols found | target wins |
| `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` | tracked dirty differs | local target has newer demo learning summaries and learning-worklist helpers; no remote-only symbols found | target wins |
| `helper_scripts/research/tests/test_alpha_discovery_throughput.py` | tracked dirty differs | local target has newer trusted-source, replay-history, and demo-learning test coverage; no remote-only symbols found | target wins |
| `helper_scripts/db/audit/cost_gate_reject_counterfactual.py` | untracked conflicts with target | local target has newer multi-horizon/profit-ranking helpers; no remote-only symbols found | target wins |
| `helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py` | untracked conflicts with target | local target includes horizon-stability coverage absent from runtime copy; no remote-only symbols found | target wins |
| `helper_scripts/research/cost_gate_learning_lane/__init__.py` | untracked conflicts with target | same one-line package marker except formatting hash drift | target wins |
| `helper_scripts/research/cost_gate_learning_lane/policy.py` | untracked conflicts with target | local target has newer profit-opportunity ranking and probe-row helpers; no remote-only symbols found | target wins |
| `helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py` | untracked conflicts with target | runtime has old `test_alpha_discovery_surfaces_cost_gate_learning_probe_ready`; local target has successor probe-ready assertions plus broader v2 review/outcome coverage | target wins |
| `docs/CCAgentWorkSpace/E1/workspace/reports/vol-event-robust-ruling.md` | untracked not in target | runtime-only 45-line read-only E1 report, already referenced by TODO | preserved in repo; target formatting may replace runtime copy |

## Evidence Used

- Remote probe JSON artifact: `/tmp/runtime_source_remote_reconcile_plan_1f15818f.json`
- Remote probe generated at: `2026-06-22T01:30:49.923575+00:00`
- Probe status: `REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE`
- Runtime file analysis: remote/local line counts and top-level Python symbols showed local target is a strict newer source surface for the code/test files, except the old runtime-only test name that is superseded by newer target assertions.

## Post-v373 Probe Note

After this report and the cleaned vol-event report were pushed, a follow-up read-only probe against target `609718e077c1a768debd9e1d6e470aebd7bcde40` still returned `REVIEW_REQUIRED_BEFORE_REMOTE_RECONCILE`: runtime HEAD `917be4cc`, runtime `origin/main` `1401848b`, runtime target object unavailable, 56 dirty/untracked paths, 43 content-equivalent paths, and 13 review-required paths. The only classification shift is that `vol-event-robust-ruling.md` is now a target path conflict instead of a target-absent runtime-only file because the repo copy normalizes trailing whitespace.

## Next Operator-Gated Step

After operator approval, make the target commit available on `trade-core`, preserve any explicitly requested runtime-local artifacts, then perform source reconcile and rerun the remote/direct planner before installing the demo-learning crons. Until that happens, demo-learning stack remains absent and Cost Gate learning cannot be trusted as continuously accumulating evidence.
