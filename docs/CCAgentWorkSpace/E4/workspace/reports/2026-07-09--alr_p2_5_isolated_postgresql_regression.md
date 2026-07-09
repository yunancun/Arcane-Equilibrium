# E4 Isolated PostgreSQL Regression - ALR P2-5

Date: 2026-07-09
Verdict: `PASS`

A disposable PostgreSQL 16 instance applied V030 through V153 and the reviewed
shadow role contract. The real `alr_shadow` role reconciled eight scanner rows,
created one first P2-4 target, appended one absent-evidence P2-5 feedback row,
created one feedback-rotation edge, and selected a second target.

Results: two statistical runs, one deferred feedback record, one rotation edge,
zero boundary blocks, false exchange/trading/proof/serving/promotion authority,
and denied UPDATE on `learning.alr_outcome_feedback_events`. The container was
removed. No production state changed in this regression.
