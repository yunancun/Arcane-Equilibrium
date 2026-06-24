# False-Negative Review Approval Durability

Date: 2026-06-24

本輪修的是 bounded Demo review chain 的「授權前置證據耐久性」。

## What Changed

`false_negative_operator_review.py` 現在支援 `--existing-operator-review-json`。當 cron 用 default `--decision defer` 例行刷新時，如果 latest 已經有 fresh / aligned / no-authority 的 `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`，它會保留這個 approval，而不是覆蓋成 pending。

但 preserve 不是放寬 gate。以下情況都不保留：

- current candidate packet 帶任何 authority-bearing 欄位；
- current candidate packet 不 fresh / not ready；
- existing approval stale；
- existing approval 的 side-cell 或 rank 不匹配；
- existing approval 自己帶 runtime/probe/order authority、Cost Gate lowering、promotion evidence。

E2/E4 找到一個初版問題：preserve branch 早於 current packet authority gate。已修成必須先通過 `authority_preserved and packet_ready` 才能 preserve。

## Why It Matters

這讓 `grid_trading|AVAXUSDT|Sell` 的 false-negative preflight approval 不會被定時 defer refresh 抹掉。它保護的是 review progress，不是 order/probe authority。

可 apply live 的 Demo 經驗需要穩定、可重建的 evidence chain；不能讓 cron 把 operator-reviewed artifact 退回 pending，也不能讓舊 approval 掩蓋新的 authority violation。

## Verification

- operator-review + false-negative preflight focused: `7 passed`
- changed cron static: `15 passed`
- cron static bundle: `18 passed`
- full Cost Gate policy: `90 passed`
- profitability + alpha runtime tests: `98 passed`
- bounded authorization/touchability/placement: `26 passed`
- `py_compile`, `bash -n`, `git diff --check`: passed
- artifact smoke:
  - normal default-defer + fresh existing approval -> approval preserved, no authority
  - authority-bearing current packet + existing approval -> `AUTHORITY_BOUNDARY_VIOLATION`, no preserve

No Bybit call, no PG write, no crontab edit, no service restart, no order/probe authority, no live, no Cost Gate lowering.

PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--false_negative_review_approval_durability.md`
