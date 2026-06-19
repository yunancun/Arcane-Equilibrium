# 2026-06-20 — MM verdict stale guard + cron restore

PM report mirror. Canonical report:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--mm-verdict-stale-guard-cron-restore.md`

Summary:

- Source commit `8411a908` makes stale daily MM verdict artifacts block the killboard instead of appearing as active capture.
- Linux daily `recorder_mm_verdict_cron.sh` was restored at `41 6 * * *`.
- Manual read-only MM run updated maker markout sample count from 3 to 16; latest killboard reads MM as fresh `CAPTURING`, but still below `min_samples=30` and still no positive net-edge symbol.
- No engine/API restart, no DB write, no Bybit private/trading call, no auth/risk/order mutation.
