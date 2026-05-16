# Cron Reconcile — MIT-P0-2 vs P0-V3-CRON-NOT-INSTALLED

## 一、任務摘要

12-Agent audit (2026-05-16) PM signoff §reprioritization #2 要求 PA reconcile：
- **MIT-P0-2** claim：「6/12 ML cron scripts not installed」
- **P0-V3-CRON-NOT-INSTALLED**（TODO §10:323）claim：「F-08 5 ML cron `17 3 * * *` installed and 24h fire verified」DONE 2026-05-09

兩條看似衝突。本 reconcile via `ssh trade-core "crontab -l"` + `ls helper_scripts/cron/` 對齊真實狀態。

## 二、修改清單

- 本 report：`/Users/ncyu/Projects/TradeBot/srv/.claude_reports/20260516_cron_reconcile_p0v3_mit_p02.md`（新建）
- TODO §11.3 將加 P1-CRON-INSTALL-WAVE-1 ticket（後續同 commit）
- 不直接 `crontab -e`（install cron = affect shared infrastructure，CLAUDE.md §「Executing actions with care」需 operator 確認）

## 三、關鍵 diff / 真實狀態

### 3.1 Linux trade-core 真實 crontab（10 條 active）

| Schedule | Path | 屬於 helper_scripts/cron/? |
|---|---|---|
| `5 0 * * *` | `helper_scripts/maintenance_scripts/daily_cost_snapshot.sh` | ❌ legacy path |
| `*/5 * * * *` | `program_code/.../bybit_readonly_status_writer.py` | ❌ |
| `*/5 * * * *` | `helper_scripts/cron_observer_cycle.sh` | ❌ legacy |
| `0 6 * * *` | `helper_scripts/db/counterfactual_daily_cron.sh` | ❌ |
| `0 */6 * * *` | `helper_scripts/db/passive_wait_healthcheck_cron.sh` | ❌ |
| `*/30 * * * *` | `helper_scripts/cron/edge_label_backfill_cron.sh` | ✅ |
| `20 * * * *` | `helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh` | ✅ |
| `* * * * *` | `helper_scripts/cron/ref21_market_microstructure_recorder.py` | partial (py not sh) |
| `17 3 * * *` | `helper_scripts/cron/ml_training_maintenance_cron.sh` | ✅ (**P0-V3 F-08 wrapper**) |
| `0 * * * *` | `logrotate -s logrotate-openclaw.state ...` | ❌ system |

### 3.2 `helper_scripts/cron/` 11 個 wrapper script 真實 install 狀態

| # | Script | Installed? | Purpose | Recommend install? |
|---:|---|:---:|---|:---:|
| 1 | `blocked_symbols_30d_unblock_check_cron.sh` | ❌ | W5-E1-C P1-DYNAMIC-UNBLOCK 週日 04:00 UTC writes `governance.unblock_candidates` | ✅ YES (P1) |
| 2 | `edge_estimate_snapshots_cycle_cron.sh` | ❌ | V059 hourly snapshot 補 daemon | 🟡 MAYBE |
| 3 | `edge_label_backfill_cron.sh` | ✅ `*/30 * * * *` | label backfill | — |
| 4 | `feature_baseline_writer_cron.sh` | ❌ | W-AUDIT-4b apply baseline writer; P1-WA4B-INSERT-1 手動跑修了 | ✅ YES (P1) |
| 5 | `mlde_shadow_recommendations_retention_cron.sh` | ❌ | REF-20 Sprint D R8: prune replay-derived 30d / real_outcome 90d | ✅ YES (P2) |
| 6 | `ml_training_maintenance_cron.sh` | ✅ `17 3 * * *` | **F-08 5 ML wrapper**: thompson/optuna/cpcv/dl3_foundation/weekly_report | — |
| 7 | `outcome_backfiller_live_cron.sh` | ❌ | V074 live-lane outcome backfill | ⏸ DEFER (live blocked) |
| 8 | `panel_aggregator_health_cron.sh` | ❌ | W-AUDIT-8a Phase B Tier 2 health 5min freshness | ✅ YES (P1) |
| 9 | `ref21_symbol_universe_snapshot_cron.sh` | ✅ `20 * * * *` | symbol universe snapshot | — |
| 10 | `replay_key_rotation_check.sh` | ❌ | 90d HMAC key rotation daily alert | ✅ YES (P1) |
| 11 | `wave9_replay_no_live_mutation_watch.sh` | ❌ | REF-20 Wave 9 acceptance gate hourly watcher | ✅ YES (P1) |

### 3.3 Reconcile verdict

**兩條 claim 都對，衡量不同層**：

- **P0-V3-CRON-NOT-INSTALLED DONE 2026-05-09**：指 `ml_training_maintenance_cron.sh` 是 wrapper，內部 dispatch 5 ML training tasks (thompson/optuna/cpcv/dl3_foundation/weekly_report)。`17 3 * * *` 真實 installed + 24h fire 驗。✅ **VERIFIED**
- **MIT-P0-2「6/12 ML cron not installed」**：指 `helper_scripts/cron/` 11 個 wrapper script 中 **8 個未 install**（實際比 6 嚴重）。MIT 的「12」可能含 legacy `maintenance_scripts/` path 或數錯。✅ **CONFIRMED via direct ls + crontab -l**

**結論**：MIT-P0-2 與 P0-V3 不衝突。F-08 5 ML training tasks **是 installed**（via wrapper）；另外 8 個獨立 cron wrapper **是 not installed**。PM signoff 要求的 reconcile 答案 = 兩者都對，描述的是不同層級。

## 四、治理對照

- CLAUDE.md §「Executing actions with care」：「Actions visible to others or that affect shared state ... modifying shared infrastructure ... 需 operator 確認」→ install cron = affect Linux trade-core shared infra
- CLAUDE.md §七「被動等待 TODO 必附 healthcheck」：8 個未 install 中 panel_aggregator_health / wave9_replay_no_live_mutation_watch / replay_key_rotation_check 屬此類，**現狀違反 §七**
- PM signoff §「Operator Actions Required」#4「Approve session dispatch order」涵蓋本批 install 待批准

## 五、不確定之處

1. **MIT 原「12」denominator 來源不確**：grep `helper_scripts/cron/` 只 11 個 `.sh`，加 `.py` (ref21_market_microstructure_recorder.py) 也只 12，但 ref21_market_microstructure_recorder 已 installed `* * * * *`。MIT 可能含 `helper_scripts/maintenance_scripts/` 或 `helper_scripts/db/` 額外 script — 未做窮舉。
2. **edge_estimate_snapshots_cycle_cron.sh** 是否仍需：memory `project_edge_scheduler_stalled` (2026-04-24) 指 edge estimator scheduler 是 daemon，這個 cron 是 V059 補 backfill，可能 dormant。
3. **outcome_backfiller_live_cron.sh** live blocked 期間是否 dry-run install：可能 install + 內部 no-op (live==0 trades) 是合理 hygiene。

## 六、Operator 下一步

1. **核可 P1 install batch**（4 個建議 P1）：
   ```bash
   # 加入 crontab -e（建議 schedule，與既有時段錯開避免 PG burst）：
   */5 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=$HOME/BybitOpenClaw/secrets $HOME/BybitOpenClaw/srv/helper_scripts/cron/panel_aggregator_health_cron.sh >> /tmp/openclaw/logs/panel_aggregator_health.log 2>&1
   0 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh >> /tmp/openclaw/logs/wave9_replay_watch.log 2>&1
   3 4 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=$HOME/BybitOpenClaw/secrets $HOME/BybitOpenClaw/srv/helper_scripts/cron/replay_key_rotation_check.sh >> /tmp/openclaw/logs/replay_key_rotation.log 2>&1
   41 4 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/feature_baseline_writer_cron.sh >> /tmp/openclaw/logs/feature_baseline_writer.log 2>&1
   0 4 * * 0 OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/blocked_symbols_30d_unblock_check_cron.sh >> /tmp/openclaw/logs/blocked_symbols_30d.log 2>&1
   ```
2. **P2 待後續**：mlde_shadow_recommendations_retention（DELETE 操作需獨立批准）+ edge_estimate_snapshots_cycle（確認是否仍需）+ outcome_backfiller_live（等 live unblock）

**Reconcile DONE**：MIT-P0-2 vs P0-V3 兩者真實狀態同框，install 動作交 operator。
