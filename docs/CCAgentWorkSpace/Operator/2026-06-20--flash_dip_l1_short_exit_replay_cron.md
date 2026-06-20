# 2026-06-20 -- FlashDip L1 Short-Exit Replay Cron

PM source report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-20--flash_dip_l1_short_exit_replay_cron.md`.

Runtime change: installed Linux user cron at `31 6 * * *` to run `helper_scripts/cron/flash_dip_l1_short_exit_replay_cron.sh`.

Boundary: read-only PG plus local `/tmp/openclaw` artifact/log writes only. No engine/API restart, no rebuild, no strategy parameter change, no order/auth/risk/runtime mutation, and no Bybit private/signed/trading call.

Current smoke: latest artifact sha256 `67670804402a58eee6f02e2dd1e3da590d7bfc806ebca5dbc71744688e3f48ee`; verdict remains `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE` because the current candidate window has trades but no L1 rows for APT/ATOM/AVAX.
