# Bounded Probe Authorization Exact Confirm Gate

Date: 2026-06-24

本輪推進 `P0-BOUNDED-PROBE-AUTHORIZATION` 到一個明確 checkpoint。

## 結論

`grid_trading|AVAXUSDT|Sell` 的 bounded Demo authorization chain 現在上游都 ready：

- false-negative preflight: `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`
- placement repair: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- Rust authority path readiness: `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- bounded authorization latest: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`

我沒有把你的「Demo API 全權授權」直接轉成 probe/order authority object。原因是這條鏈要能後續 apply live，不能模糊掉 exact typed-confirm gate。

## Artifact Generated

生成了一個 fail-closed structured attempt：

`/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_structured_attempt_bdp-grid-avax-sell-20260624T0707Z.json`

結果：

- status: `TYPED_CONFIRM_REQUIRED`
- only blocking gate: `typed_confirm_matches`
- requested max probe orders: `1`
- source max probe orders: `3`
- expected phrase: `authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:1:bdp-grid-avax-sell-20260624T0707Z`
- `operator_authorization=null`
- no active runtime order/probe authority
- no Cost Gate lowering
- no live
- no promotion proof

## Why

這是有意保守的。Broad Demo permission 可以讓我自動做 source、artifact、read-only/runtime smoke、review packet；但 bounded probe/order authority 必須保留成 side-cell-specific、限量、可過期、可重建的 exact contract。

下一個安全分支是：

- 要么提供 exact typed-confirm，才可生成 bounded Demo authorization object；
- 要么不授權 probe，轉去 source-only / read-only alpha expansion，例如 MM repeat-window、false-negative candidate friction scorecard、execution realism scoring。
