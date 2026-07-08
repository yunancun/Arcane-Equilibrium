# PM Report - NEAR Buy Bounded-Probe Plan Materialization BB Approved

Status: `READY_FOR_BOUNDED_DEMO_FINAL_WINDOW`

Candidate: `ma_crossover|NEARUSDT|Buy`

BB returned `APPROVE_FOR_PM_SAME_WINDOW_PLAN_MATERIALIZATION_RECHECK` for the exact request `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_bounded_probe_plan_materialization_bb_request.json`.

BB report:

`docs/CCAgentWorkSpace/BB/workspace/reports/2026-07-08--profit_first_near_buy_bounded_probe_plan_materialization_bb_review.md`

BB report sha: `b730fdf6ddeaf823d230aba4e77e68ede96ae99fa3d78216a28e4402a9db97a3`

The approved next step is only PM same-window plan materialization recheck. This checkpoint does not write canonical `bounded_demo_probe_soak_plan.json`, does not overwrite `_latest`, does not enable runtime adapter/writer, and does not authorize Bybit call, Decision Lease, order/probe/cancel/modify, DB/PG action, Cost Gate lowering, live/mainnet, or proof/promotion.

## Reviewed Artifacts

- E3 report sha `bb03bcc9d911ad17bff674720f81bb1785061393f6187f51d7ea2f1131cc4ed8`, verdict `APPROVE_FOR_PM_BB_PLAN_MATERIALIZATION_REVIEW`.
- BB request sha `05d27a0419954905faf82a3e02c59d10814d399d6f52149c5b55a13b6d3ba89c`.
- Operator authorization packet sha `0e075af5b0a5ef8b3e343caffe7ab3608bbb45cf418600c5cf689e3c5e5e7124`, candidate `ma_crossover|NEARUSDT|Buy`, expires `2026-07-09T00:12:30.886090+00:00`.
- Plan inclusion review sha `5e08595c3b009741e3ede221d7ce96c233864d6ddb1f434797b1c105249305fc`, status `PLAN_INCLUSION_PREVIEW_READY_NO_ADMISSION`.
- Construction preview sha `d4561891a8ddaf318923be31043591033413a58ff66ef2a8acb842b7e79a2981`, qty `508.5`, limit `1.8719`, notional `951.86115`.
- Canonical soak plan remains old ETH sha `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823`.

## Next Machine Stage

Perform PM same-window source/runtime/hash/candidate/expiry recheck. If every check is still stable, the later materialization action may only copy the exact reviewed `plan_preview` atomically into canonical `bounded_demo_probe_soak_plan.json` with a hash record. That action still grants no order authority by itself.
