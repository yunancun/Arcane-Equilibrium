# REF-21 P0-REF21-5 Operator Brief

**Status:** CLOSED on 2026-05-06.

已補上 V061：`replay.calculate_promotion_metrics(...)` 現在是非 stub 的
SECURITY DEFINER calculator。它從 replay 自己的 experiment / simulated fill
/ historical edge snapshot row 重建 promotion metrics，不再信任 replay
producer 自報的 promotion 結果。

驗證已跑：

- Mac migration static tests：`11 passed`
- `git diff --check`：passed
- Linux `trade-core` transaction dry-run：V057-V061 + replay test data 在同一
  transaction 內 apply/insert/execute，結果 `eligible=true`、`fail_reasons=[]`、
  `PBO=0`、bootstrap q50 `1000` resamples，最後 `ROLLBACK`

P0-REF21-5 已解除。REF-21 目前仍被兩件事卡住：

- P0-REF21-6：真正的 `/api/v1/replay/full-chain/run`
- P0-REF21-7：replay dedicated Bybit public client + 50 req/s rate/IP isolation
