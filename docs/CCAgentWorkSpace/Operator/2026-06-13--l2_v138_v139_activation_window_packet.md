# 2026-06-13 — L2 V138/V139 activation window packet

## 判定

`READY-FOR-OPERATOR-WINDOW / NOT EXECUTED`。

`[82]` 已不再阻擋 V138/V139；現在只差你明確批准一個低風險 engine restart / auto-migrate window。本文件是操作包，不是已執行記錄。

## 現狀

- Linux source head：`de92f879d297696a34b932d9a448bc00867a69f7`。
- prod `_sqlx_migrations`：head `137`，`all_success=true`，count `120`。
- `repair_migration_checksum --verify`：`drift_count=0`；V138/V139 都是 `MISSING_IN_DB`。
- V138/V139 目標物件都還不存在：`research.pre_registered_hypotheses`、`research.alpha_wealth_ledger`、`research.alpha_wealth_debit_state`、`agent.agent_memory`、`agent.agent_memory_embedding_meta`。
- `OPENCLAW_AUTO_MIGRATE=0`；L2 memory / alpha wealth activation flags 都 OFF/未設。
- `[83]-[89]` Linux 真 DB preflight：`SUMMARY: ALL PASS`。
- Gate-B latest 仍是 `WATCH_ONLY`，不應阻礙 V138/V139，但也不代表 listing alpha 可以晉升。

## 不可做的路徑

不要用 `psql -f` 手套 V138/V139；這會繞過 `_sqlx_migrations`，後續 migration state 會變成曖昧狀態。

唯一推薦路徑是：暫時把 `OPENCLAW_AUTO_MIGRATE=1` 寫入 runtime env，跑 `restart_all.sh --engine-only --keep-auth`，讓 engine 啟動時的 `MigrationRunner` 套用 V138/V139，完成後立刻把 `OPENCLAW_AUTO_MIGRATE` 還原成 `0`。

## 需要你批准後才執行

完整命令與 post-check 在 PM report：

`docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-13--l2_v138_v139_activation_window_packet.md`

預期結果：

- `_sqlx_migrations` head 137 → 139。
- V138/V139 objects 存在。
- checksum drift 仍 0。
- `agent.agent_memory` 初始 0 rows。
- `[83]-[89]` 仍 PASS / PASS-skip。
- engine watchdog alive/fresh。

## 不一起打包

本 window 不包含 manual V140、agent memory seed、L2 memory cron flag-on、embedding backfill、E2E true model call、Gate-B isolated probe。這些都是後續單獨批准項。
