# Bounded Probe Authority-Path Preview Wiring

日期：2026-06-23
Source commit：`24fcb351` (`[skip ci] Wire bounded probe placement preview`)
Linux runtime source：`/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `24fcb351` and verified

## 結論

本次把 v423 的 no-authority `bounded_probe_near_touch` Adapter 接到 eligible Demo/LiveDemo Cost Gate reject path，但只產生 placement preview evidence，不提交 order、不授權 probe、不降低 Cost Gate。

Canonical Linux readiness artifact 已刷新：

- Generated：`2026-06-23T10:39:48.399485+00:00`
- Status：`AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- Adapter present：`true`
- Authority-path wiring present：`true`
- Missing required patch seams：`[]`
- Probe authority：`false`
- Order authority：`false`

## Source Changes

- `rust/openclaw_engine/src/bounded_probe_near_touch.rs`
  - 新增 `BoundedProbeOptionalBboPlacementRequest`
  - 新增 `post_only_near_touch_from_optional_bbo_or_skip`
  - 缺 bid/ask/tick/observed time 時 fail closed 為 `MissingFreshBbo`
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`
  - eligible Cost Gate reject 後計算 near-touch placement preview
  - preview 結果傳入 demo-learning-lane writer
  - 未建立 `OrderDispatchRequest`，未提交 Bybit order
- `rust/openclaw_engine/src/demo_learning_lane_writer.rs`
  - 新增 `record_reject_event_with_placement`
  - 保留舊 `record_reject_event` 行為
- `rust/openclaw_engine/src/demo_learning_lane_ledger.rs`
  - admission ledger row 可帶 `bounded_probe_placement`
  - `bounded_probe_attempt` 標記 `would_submit_if_authorized`
  - `order_submission_performed=false`
  - skip path 記錄 `bounded_probe_touchability_block`
- readiness scanner/tests 更新為檢查 optional-BBO dispatch seam。

## Verification

Mac:

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q ...`：18 passed
- `python3 -m py_compile ...`：pass
- `cargo test -p openclaw_engine bounded_probe_near_touch --lib`：9 passed
- `cargo test -p openclaw_engine demo_learning_lane --lib`：23 passed
- `cargo test -p openclaw_engine step_4_5_dispatch --lib`：7 passed
- `git diff --check`：pass
- Source readiness fixture：`AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`

Linux:

- Source fast-forwarded clean to `24fcb351`
- Python related bounded suite：18 passed
- `cargo test -p openclaw_engine bounded_probe_near_touch --lib`：9 passed
- `cargo test -p openclaw_engine demo_learning_lane --lib`：23 passed
- `cargo test -p openclaw_engine step_4_5_dispatch --lib`：7 passed
- Canonical `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_authority_patch_readiness_latest.{json,md}` refreshed

## Profitability Read

這一步不是「放寬 cost gate」；它是把 future operator-authorized bounded Demo probe 所需的 evidence hook 補上。

目前系統已知道：

- demo 有 order evidence，但沒有 fill-backed learning evidence
- 現有 passive order 太深，無法有效學習 execution edge
- near-touch shadow repair 可提高 mechanical touchability
- 但仍缺 candidate-matched fill/fee/slippage 和 matched-control proof

v424 的價值是：下一次 operator 授權 bounded Demo probe 時，系統能對每個被 Cost Gate 擋掉的 eligible signal 記錄「如果授權會如何 near-touch 下單」或「為何仍不可觸碰」。這讓後續 alpha/edge 學習能追溯到 side-cell、BBO freshness、touch gap、fills、fees、slippage 與 matched controls。

## Boundary

No CI run. No PG query/write/schema migration. No Bybit private/signed/trading call. No deploy/rebuild/restart. No crontab install. No env/auth/risk/order/strategy/runtime mutation. No global Cost Gate lowering. No probe authority. No order authority. No promotion proof.

## Next Gate

1. Operator review static patch readiness.
2. Separate operator authorization before any bounded Demo probe order.
3. After authorized probe: collect candidate-matched order-to-fill, fill/fee/slippage lineage.
4. Compare with matched blocked controls and execution-realism review before any Cost Gate change.
