# Operator Brief — IBKR Stock/ETF 方案對抗性檢查

日期：2026-06-29

PM 跑了 CC / FA / PA / E3 / QC / MIT 六角色對抗性審查。結論一致：

- 方向有效：IBKR `stock_etf_cash` paper/shadow research lane 值得探索。
- 只批准 Phase 0 ADR/spec。
- 不批准 Phase 1+ 實作、IBKR API、secret slot、paper order、GUI runtime enablement、6-8 週 evidence clock、任何 IBKR live/tiny-live。

PM 已把主要 blocker 回補進主計劃：

- IBKR API/session baseline 未選定。
- IBKR paper 是 order-capable broker-paper surface，不是 harmless read-only。
- 需要 Rust lane-scoped IPC/order lifecycle，不能復用現有 Bybit/Paper `submit_paper_order`。
- Python IBKR connector 必須 no-write。
- DB evidence contract 需要 DDL-level schema。
- feature flag / secret / live-slot absence 必須 machine-checkable。
- GUI lane selector 只能 display/filter，不能成為 authority。
- 6-8 週 evidence clock 必須有 frozen universe、benchmark、cost model、hypothesis、sample-size、paper/shadow divergence、PSR/DSR 或等價統計 gate。

PM SIGN-OFF: CONDITIONAL — Phase 0 only。

下一步如果繼續：只開 Phase 0 ADR/spec packet；不碰 runtime。
