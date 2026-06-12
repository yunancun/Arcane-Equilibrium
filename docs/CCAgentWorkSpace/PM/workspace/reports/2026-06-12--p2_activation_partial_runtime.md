# P2 批次激活 partial runtime report — owed #2-#6

日期：2026-06-12  
執行角色：PM(default)  
runtime：Linux `trade-core`，repo `/home/ncyu/BybitOpenClaw/srv`

## Verdict

`PARTIAL-DONE / BLOCKED`。

- DONE：owed #3 Bybit 公告哨兵 cron 已安裝並手動單跑驗證。
- DONE：owed #4 Polymarket artifact-only daily cron 已安裝並手動單跑驗證。
- BLOCKED：owed #2 V138+V139 prod migration 未套用；因 active P5-SM 48h soak 尚未完成，且 migration 唯一路徑需要 engine restart。
- BLOCKED：owed #5/#6 L2 記憶層激活依賴 V139，未執行 B1/B2/B3。

## Ground Truth

- Mac/origin/Linux 均在 `main e91057ef` 且 Linux `git pull --ff-only` = already up to date。
- prompt 內預期 `61803917` 是祖先，不是當前 head；`61803917..HEAD` 只新增 operator prompt、AEG-S3 event breadth 相關檔與 TODO/memory 更新，未改 P2 activation scripts / V138 / V139 / V140。
- prod `_sqlx_migrations` head = `137`；V138/V139 仍 pending。
- V138/V139/V140 檔案 SHA256 Mac=Linux：
  - V138 `1403e9b5efcb093b8ce95a2d9e64b8dd5617f93557dc8c5d0d03452a18dc1cfd`
  - V139 `da37c52d692ad15e2e06a76f46f5fb1818879ed91b51aa79c08ec8a669db1a16`
  - manual V140 `5b53d64bbd9526a64963d7b936af454a84bd3280fb54c5024e1912d8d24307eb`
- `repair_migration_checksum --verify` read-only check：applied versions 1..137 `drift_count=0`; V138/V139 = `MISSING_IN_DB`。

## Completed

### 階段 C — BB 公告哨兵

- dry-run installer OK；實際 installed crontab：
  `7,37 * * * * ... bybit_announcement_sentinel_cron.sh ...`
- scratch dry-run single call：50 items, 50 new, 0 alerts, baseline flood guard OK。
- prod data-dir manual run：50 items, 0 new, 0 alerts, malformed=0。
- state file：`/tmp/openclaw/bybit_announcements_state.json`, seen=50。

### 階段 D — Polymarket artifact-only axis

- dry-run installer OK；實際 installed crontab：
  - active daily `41 4 * * * ... polymarket_axis_cron.sh daily ...`
  - hourly `#7 * * * * ... polymarket_axis_cron.sh hourly-topn ...` 保持註釋停用。
- manual daily run OK：
  - run_id `daily-20260612T090806Z`
  - run_dir `/tmp/openclaw/polymarket_axis_runs/daily-20260612T090806Z`
  - http_requests=78
  - snapshot_rows=6100
  - unique_events=3559
  - errors=0
  - manifest `point_in_time=true`, `git_dirty=false`

## Blocker

階段 A 需要透過 `OPENCLAW_AUTO_MIGRATE=1` 重啟 engine 觸發 auto-migrate；repo 內未暴露獨立 migrate subcommand，手動 `psql -f` 會繞過 `_sqlx_migrations`，不可用。

目前 P5-SM soak 還在 active：

- `basic_system_services.env`：`OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1`、`OPENCLAW_SM_IPC_CANARY_ENABLED=1`。
- engine/API alive。
- full passive healthcheck 於 `2026-06-12T09:11:13Z` 顯示 `[82] lease_ipc_soak_window` = FAIL/accumulating：`window=31.2h < 48h`, probes=934。

依 TODO 與 P5-SM row，soak 期應避免 restart；因此未執行 V138/V139 apply，也未執行依賴 V139 的 B1/B2/B3。

## Next

P5-SM soak gate 到期並通過後，低風險順序：

1. 再跑 `repair_migration_checksum --verify` 與 prod head check。
2. 將 `OPENCLAW_AUTO_MIGRATE=1` 持久寫入 runtime env，使用 `restart_all.sh --engine-only --keep-auth` 或等效最小 restart 觸發 V138→V139，完成後還原 `OPENCLAW_AUTO_MIGRATE=0`。
3. 驗 head=139、V139 兩表 0 rows、CHECK/Guard/DELETE revoke 探針。
4. 再執行 B1/B2/B3；若不 pull `bge-m3`，保留 FTS-only，B3 pipeline flag 仍需 operator 明確確認。
