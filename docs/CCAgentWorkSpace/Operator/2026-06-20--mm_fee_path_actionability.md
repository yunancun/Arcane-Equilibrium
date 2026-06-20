# Operator Note — MM Fee-Path Actionability

日期：2026-06-20

這批是 fee-path 診斷修正，不是交易變更。

MM lower-fee scenario 現在被明確標成 business/capital gate：

- MM verdict status-line sha256 `3f63d2f3146bd307d2a4ba3c0e06af07af868fb93cc0b4fb2308d968fb0abbf1`
- actionability status `STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED`
- first clearing tier `VIP5`
- clearing maker fee `1.0bp/side`
- break-even maker fee `1.135bp/side`
- 30d volume gap `$249,131,074.44`
- volume multiplier needed `287.712`
- asset gap `$2,000,000`

Alpha discovery latest sha256 `7cf13df4d64cb27521da26139916fb1a3a052f4db22f3ba0a1398d8adab0f882` still says `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0. MM top blocker remains `cost_wall:gross_edge_below_current_fee_no_current_fee_walk_forward_positive`, now with `business_path_operator_action_required=do_not_treat_lower_fee_case_as_actionable_at_current_scale`.

Operator implication：do not use the VIP5 lower-fee case as strategy/probe/promotion authority. It requires real account fee verification, capital/scale eligibility, then cross-window/cross-regime MM review.

驗證：Mac/Linux fee-path tests `3 passed`，alpha focused tests `25 passed`，cron static `11 passed`，py_compile、shell syntax、diff-check、MM verdict smoke、alpha discovery smoke passed。邊界：source/test/docs + `/tmp/openclaw` artifact/status writes only；沒有 PG write、Bybit private/signed/trading call、engine/API restart、strategy/risk/order/auth mutation。
