# Operator Note: AVAX / SUI / FIL Matched-Control Design

Date: 2026-06-26 07:22 CEST

本輪結論：AVAX 的 future proof 只能用同 side-cell 的 matched controls 和候選匹配 fill lineage。SUI/FIL 可以當 research controls，但不能當 AVAX 的盈利 proof。

核心邊界：

- AVAX 仍是 current P0 bounded Demo candidate。
- SUI/FIL 不是 bounded candidates，除非未來重開 P0 candidate selection。
- 任何 future AVAX outcome review 必須有 candidate-matched admissions/outcomes、fees/slippage、maker/taker、BBO、order/fill/intent/risk/source lineage，且不能有 proof-exclusion reason。
- SUI/FIL 只能用來檢查 AVAX 是否一枝獨秀或低價 grid 家族效應，不能用來 promotion、Cost Gate proof、或繞過同 side-cell proof。

下一個 blocker 回到 `P0-BOUNDED-PROBE-AUTHORIZATION`，但它仍是 `BLOCKED_BY_RUNTIME_AUTHORIZATION`，直到出現有效 AVAX-scoped auth 或 exact typed confirm 並通過 E3/BB review。

本輪沒有 Bybit order/cancel/modify、PG write、runtime mutation、service/crontab/env mutation、Cost Gate/cap/risk mutation、probe/order/live authority 或 profit proof claim。
