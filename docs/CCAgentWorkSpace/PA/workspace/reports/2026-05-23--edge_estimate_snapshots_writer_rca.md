# Edge Estimate Snapshots Writer RCA — 5/7 之後 silent stop

**日期**：2026-05-23
**Scope**：找 `learning.edge_estimate_snapshots` 5/7 00:46 後停寫的最小可信根因。

## Root Cause Hypothesis

### 主 hypothesis（極高置信度）

**`learning.edge_estimate_snapshots` 表的 cycle cron wrapper 在 commit `70e7b6b1` (2026-05-09 01:27) 被 land 但從未安裝到 crontab；5/7 00:46 那次寫入是 operator 在 Sprint N+0 期間一次性手動跑 `ref21_backfill_v058_v059.py --apply` 留下的 bootstrap 痕跡，之後無人再跑，故 16 天 staleness。** EdgeEstimatorScheduler 本身 **健康在跑**，只是它寫 `settings/edge_estimates*.json` 檔案（仍是新鮮的），不寫這張 PG 表。

- 證據 A — Code path：`learning.edge_estimate_snapshots` 整個 repo 唯一寫入點是 `srv/helper_scripts/db/ref21_backfill_v058_v059.py:363` (INSERT 在 `insert_edge_snapshots()`)。Rust engine 無寫入 (`grep -rn edge_estimate_snapshots rust/` 空)，`james_stein_estimator.py` 不寫此表。
- 證據 B — Commit message：`70e7b6b1 2026-05-09 01:27 audit: add edge snapshot cycle wrapper`，message 原文 **"no cron installation, DB apply, restart, or runtime mutation was performed"**（PA grep 已驗）。
- 證據 C — Linux crontab：`ssh trade-core 'crontab -l'` **沒有任何 edge_estimate_snapshots_cycle_cron 行**。其餘 OPENCLAW cron 全在 5/21 被 `# DISABLED_OPENCLAW_20260521` 一次性 disable，但此 wrapper 從未被加入過（沒有 disabled 版也沒有 active 版）。
- 證據 D — log file 不存在：`/tmp/openclaw/logs/edge_estimate_snapshots_cycle_cron.log` 不存在於 trade-core（wrapper 若曾跑必 append log，line 17/64-76）。
- 證據 E — Scheduler 本身健康：`SELECT … observability.engine_events WHERE source='edge_estimator_scheduler'` 5/22 23:07 還在跑，status=ok，demo=127 / live_demo=77-79 cells。
- 證據 F — JSON 持續更新：`/home/ncyu/BybitOpenClaw/srv/settings/edge_estimates.json` mtime = **2026-05-23 00:07**（今天），`edge_estimates_live_demo.json` = 5/22 23:06 — scheduler 每 ~3h 寫 JSON。
- 證據 G — 表的 strategy 分布證明非 scheduler 自動寫入：表內 9 個 strategy 含 `dust_frozen / orphan_adopted / orphan_frozen / bybit_sync` 這 4 個系統 sentinel，是 JSON 全量 backfill 的特徵；scheduler 內部只跑 5 真實策略（james_stein），不會產生 sentinel。

### 次 hypothesis（備援，**已被推翻**）

「V073 contract guard 5/9 落地後改了 schema，新寫入因 constraint 違反 silent 失敗」— **不成立**：V073 commit message 自我宣告為 read-only contract guard，diff 看只有 DO $$ EXCEPTION 校驗（不改 schema、不加新 constraint）。且 schema 自 V059 後沒變動（grep `V0[6-9].*edge_estimate_snapshots` 全部都是 SELECT/guard 不是 ALTER）。`engine_events` 觀察 source=edge_estimator_scheduler 從未報 `scheduler_fail`。

## 修復方案 outline（最小 scope）

- **步驟 1**：在 `ssh trade-core` `crontab -e` 加一行（按 wrapper 注釋第 5-6 行建議）：
  ```
  12 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh
  ```
  預期效果：每小時 hh:12 跑一次 wrapper → `ref21_backfill_v058_v059.py --skip-instruments --skip-freeze-log --apply` → `INSERT … ON CONFLICT DO NOTHING` 一次性寫入新 asof_ts 對應的 187 ~ 200 cells。
- **步驟 2**：手動先跑一次驗證：`ssh trade-core 'OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh'` → 看 log + 看 PG `MAX(asof_ts)` 跳到當前 UTC。
- **步驟 3**：24h 後驗證 distinct asof_ts >= 24 + log 持續 "cycle end OK"。
- **Scope 邊界**：只動 crontab 一行 + 一次手動驗證。**不改 V073 / V059 schema / scheduler / JSON writer / Rust 任何代碼**。不擴大到 1B EDGE-DIAG-2 樣本累積、不改 freeze_log、不改 attribution_chain。
- **與 1B 並行可行性**：✅ 完全並行。1B（funding_arb demo active=true 收 EDGE-DIAG-2 樣本）只動 `settings/risk_config_demo.toml` 的 `[strategies.funding_arb] active`；此修復只動 crontab。**零文件重疊**，零 IPC 衝突。

## 還未查清的盲點

- **盲點 1**：5/7 00:46 那次手動跑的觸發者沒有明確 git/log audit trail —— 沒在 git log 找到 commit "manual run ref21_backfill"。推測是 operator 在 Sprint N+0 sign-off 期間（HEAD `b6ed4975` 5/10 之前）跑過，但無 archive 證據。**對修復不影響**（不需要知道是誰跑的，只需要把 cron 接上）。
- **盲點 2**：wrapper 注釋說 "12 * * * *"（每小時 :12 分），但 V073 guard 沒規定 cycle 頻率上限。若 operator 想要 30-min 或日級可調此 cron expression — 留給 operator 決策，不擴 scope 自決。
- **盲點 3**：`70e7b6b1` 為何被設計成 "提交 wrapper 但不裝 cron" — 從 PR/commit body 看是 audit 階段刻意避免立即動 runtime（"no cron installation … was performed"）。**這是已知的 deliberate gap，不是 bug**，但 16 天無人 follow-up 安裝是組織/TODO 追蹤盲點，建議 PM/PA 在後續 TODO 加 owner。

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--edge_estimate_snapshots_writer_rca.md
