# MM Fee-Path Actionability

日期：2026-06-20
角色：PM
範圍：artifact-only MM fee-path diagnosis；不改 strategy、risk、order、auth。

## 結論

上一批已把 MM no-profit 主因改成 cost wall：sample-gated gross edge 存在，但 current fee 後 net 仍負。這批把「lower-fee path」再拆成可執行性判斷，避免把 VIP fee scenario 誤讀成可立即盈利路徑。

最新 runtime 顯示：

- first clearing standard tier：`VIP5`
- clearing maker fee：`1.0bp/side`
- break-even maker fee：`1.135bp/side`
- current maker fee：`2.0bp/side`
- 30d capacity proxy notional：`$868,925.56`
- VIP5 30d volume gap：`$249,131,074.44`
- volume multiplier needed：`287.712`
- asset gap：`$2,000,000`
- actionability status：`STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED`
- operator action required：`do_not_treat_lower_fee_case_as_actionable_at_current_scale`

所以 lower-fee scenario 是一條 business/capital path，不是目前可執行的 strategy/probe/promotion path。

## 變更

- `program_code/research/microstructure/fee_path.py`
  - 新增 `business_path_actionability`。
  - 把 current fee、break-even fee、first clearing tier、volume gap、volume multiplier、asset gap 轉成 explicit actionability status。
  - 保留原 `status`，避免破壞既有 consumers。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - MM primary blocker extra fields now include `business_path_actionability_status` and `business_path_operator_action_required`。
  - Fee/scale secondary blocker now includes the same actionability object.
- Tests
  - Fee-path unit tests cover scale/capital gated, current-fee-clears, and no-break-even cases.
  - Alpha-discovery fixture asserts MM blocker exposes the actionability status.

## Runtime Evidence

MM verdict latest status line:

- Source: `/tmp/openclaw/logs/recorder_mm_verdict.log`
- status-line sha256: `3f63d2f3146bd307d2a4ba3c0e06af07af868fb93cc0b4fb2308d968fb0abbf1`
- `ts_utc`: `2026-06-20T18:11:40Z`
- `fee_path_feasibility.business_path_actionability.status`: `STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED`
- first clearing tier: `VIP5`
- clearing tier maker fee: `1.0bp/side`
- break-even maker fee: `1.135bp/side`
- volume gap: `$249,131,074.44`
- volume multiplier needed: `287.712`
- asset gap: `$2,000,000`

Alpha discovery latest:

- Path: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- sha256: `7cf13df4d64cb27521da26139916fb1a3a052f4db22f3ba0a1398d8adab0f882`
- `created_at_utc`: `2026-06-20T18:11:46.010364+00:00`
- MM blocker class: `cost_wall`
- MM primary blocker: `gross_edge_below_current_fee_no_current_fee_walk_forward_positive`
- `business_path_actionability_status`: `STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED`
- `business_path_operator_action_required`: `do_not_treat_lower_fee_case_as_actionable_at_current_scale`

## Verification

Mac:

- `python3 -m pytest -q program_code/research/tests/test_mm_fee_path_feasibility.py` -> `3 passed`
- `env PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `25 passed`
- `python3 -m pytest -q helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` -> `11 passed`
- `python3 -m py_compile program_code/research/microstructure/fee_path.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- `git diff --check`

Linux selective sync:

- `env PYTHONPATH=/home/ncyu/BybitOpenClaw/srv python3 -m pytest -q /home/ncyu/BybitOpenClaw/srv/program_code/research/tests/test_mm_fee_path_feasibility.py` -> `3 passed`
- Alpha focused tests -> `25 passed`
- py_compile / targeted diff-check passed

Runtime smoke:

- Ran read-only `recorder_mm_verdict_cron.sh`
- Ran artifact-only `alpha_discovery_throughput_cron.sh`

## Boundary

This batch wrote source/tests/docs and `/tmp/openclaw` status artifacts only. It did not write PG tables, run migrations, call Bybit private/signed/trading endpoints, rebuild/restart engine/API, or mutate credential/auth/risk/order/strategy state.

## Next Trigger

Do not treat lower-fee MM as actionable at current scale. The next useful MM route remains one of:

- real lower-fee/rebate eligibility proof followed by cross-window/cross-regime MM review, or
- a new low-friction signal family that clears current-fee train/holdout gates.
