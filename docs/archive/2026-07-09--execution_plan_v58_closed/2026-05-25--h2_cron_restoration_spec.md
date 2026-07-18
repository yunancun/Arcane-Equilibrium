> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# H-2 Cron Restoration Spec — Sprint 2 Evidence Path 復原

**Date**: 2026-05-25
**Author**: PA（Project Architect）
**Severity**: HIGH（Sprint 2 evidence path 半斷）
**Trigger**: E5 audit `2026-05-25--runtime_hygiene_audit_pre_sprint_2.md` §H-2 — 13 OpenClaw cron 2026-05-21 集體標 `DISABLED_OPENCLAW_20260521` 並從未復原
**Reads**: E5 audit + SSH crontab probe + memory `project_2026_05_09_ml_training_cron_weekly` + git log 2026-05-21 ~ 2026-05-22
**Scope**: read-only audit + spec only；operator 動作分階段執行

---

## TL;DR

| # | Cron | Cadence | Sprint 2 阻？ | 復原必要性 | Operator 動作 |
|---|---|---|---|---|---|
| 1 | `counterfactual_daily_cron.sh` | daily 06:00 | **HIGH 阻** | **MUST** | Day -1 enable |
| 2 | `ref21_symbol_universe_snapshot_cron.sh` | hourly @20 | **HIGH 阻** | **MUST** | Day -1 enable |
| 3 | `ml_training_maintenance_cron.sh` | daily 03:17 | **MED 部分阻** | **MUST**（hybrid 含 5 training daily）| Day -1 enable |
| 4 | `edge_label_backfill_cron.sh` | */30 min | **MED 部分阻** | **MUST**（outcome chain）| Day -1 enable |
| 5 | `panel_aggregator_health_cron.sh` | */5 min | LOW observability | SHOULD | Day -1 enable |
| 6 | `wave9_replay_no_live_mutation_watch.sh` | hourly @0 | LOW safety invariant | SHOULD | Day -1 enable |
| 7 | `replay_key_rotation_check.sh` | daily 09:00 | LOW safety | SHOULD | Day 0 enable |
| 8 | `feature_baseline_writer_cron.sh` | daily 04:41 | LOW observability | SHOULD | Day 0 enable |
| 9 | `halt_audit_pg_writer_cron.sh` | every minute | LOW | SHOULD | Day 0 enable |
| 10 | `logrotate-openclaw.conf` | hourly @0 | LOW（engine.log accumulation）| SHOULD | Day 0 enable |
| 11 | `passive_wait_healthcheck_cron.sh` | 6h | LOW（手動可替代）| OPTIONAL | Day 0+ defer |
| 12 | `ref21_market_microstructure_recorder.py` | every minute | LOW（high noise）| **DEFER**（10 symbol × 60s 高 write 負載） | 不復原 |
| 13 | `blocked_symbols_30d_unblock_check_cron.sh` | weekly Sun 04:00 | LOW（30d window 不在 Sprint 2 內 trigger） | DEFER | 不復原 |
| **+1** | `edge_estimate_snapshots_cycle_cron.sh` | hourly @12 | – | **已 active**（唯一沒被 disable）| 無動作 |
| **NEW** | `edge_estimate_snapshots_cycle_cron.sh`（QC EA-2 wrapper 校準）| 同上 | – | **VERIFY**（wrapper commit `70e7b6b1` 已 land 但需 confirm 已 wrapped 進現有 cron）| Day -1 verify |

**Day -1 必跑（4 個 HIGH/MED 阻 Sprint 2 evidence path）**：counterfactual + symbol_universe + ml_training + edge_label_backfill
**Day 0 跟（5 個 LOW SHOULD）**：panel_aggregator + wave9_replay + replay_key + feature_baseline + halt_audit + logrotate
**Defer / 不復原（3 個）**：microstructure（high noise）+ blocked_symbols_30d（window 不 trigger）+ passive_wait（手動可代）

---

## 1. SSH Crontab Empirical State（2026-05-25）

### 1.1 Active cron（4 行；3 legacy + 1 OpenClaw）

```cron
5 0 * * * /home/ncyu/srv/helper_scripts/maintenance_scripts/daily_cost_snapshot.sh
*/5 * * * * python3 /home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_readonly_status_writer.py
*/5 * * * * bash /home/ncyu/srv/helper_scripts/cron_observer_cycle.sh
12 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh
```

**觀察**：
- 前 3 行 path 為 `/home/ncyu/srv/` — 非當前 BybitOpenClaw repo；legacy 不在本 sprint scope
- 第 4 行 = 唯一存活 OpenClaw cron（edge_estimate_snapshots）— confirm 已 wrapped per QC EA-2 wrapper commit `70e7b6b1`（wrapper 應已 land 進 cron path）

### 1.2 Disabled OpenClaw cron（13 行）

全標 `# DISABLED_OPENCLAW_20260521`，cron daemon **完全略過**（# 注釋）。E5 audit 已詳列；本 spec 不再 paste。

### 1.3 Git history 對應

2026-05-21 ~ 2026-05-22 git log：
- `1639506f docs(sprint-4-wave-b-m1)`: Singleton Registry SSOT
- `188f244a feat(gates): cost_gate_moderate ...`
- `4d4ff99f fix(sprint-4-wave-b-round2)`

**無 disable cron commit** — crontab 改動 **不在 repo**。
**推斷動機**：2026-05-21 LG-1 P0 closure 觀察期 + OPENCLAW_DATA_DIR 路徑切換期間消 noise（per E5 audit 推斷）。
**治理盲點**：未在 TODO/memory 留復原計劃 → 4 day stale 才被 healthcheck 跑出來。

---

## 2. 逐項分析 + 復原必要性

### 2.1 HIGH（Day -1 MUST）

#### 2.1.1 `counterfactual_daily_cron.sh`（daily 06:00）

**Cron 行（待 enable）**：
```cron
0 6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/counterfactual_daily_cron.sh
```

**用途**：每日 06:00 跑 counterfactual replay（pre/post promotion 比對；alpha attribution）
**Sprint 2 阻？**：**是** — v5.8 §4 業務 Sprint 2 含 Alpha Tournament，4 day stale counterfactual evidence 不可信
**healthcheck 影響**：[11] FAIL 92.6h（4 day stale）
**復原風險**：低；只跑一次 daily 06:00；db schema 必 V### apply（per E5 audit replay_manifest_registry 不存在 M-3，但 counterfactual cron 不依賴此表）
**Verify SOP**：Day -1 enable → 06:00 自動觸發 → 07:00 SSH 跑 `ssh trade-core 'tail -50 /tmp/openclaw/logs/counterfactual_daily_cron.log'` 驗成功
**ETA**：operator 30s（crontab -e 取消注釋）

#### 2.1.2 `ref21_symbol_universe_snapshot_cron.sh`（hourly @20）

**Cron 行（待 enable）**：
```cron
20 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh
```

**用途**：每小時 @20 拉 Bybit symbol universe snapshot（perp/spot symbol 列表）
**Sprint 2 阻？**：**是**（若 M10 Tier A 真進 Sprint 2）— symbol universe 不更新會 miss 新上線 symbol；現 87h stale
**healthcheck 影響**：[53] FAIL 87h
**復原風險**：低；read-only Bybit REST；不寫 PG（snapshot file only）
**Verify SOP**：enable → 下一個 :20 自動觸發 → SSH 驗 `ls -la /tmp/openclaw/symbol_universe_snapshot/` mtime 近 1h
**ETA**：operator 30s

#### 2.1.3 `ml_training_maintenance_cron.sh`（daily 03:17）

**Cron 行（待 enable）**：
```cron
17 3 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw $HOME/BybitOpenClaw/srv/helper_scripts/cron/ml_training_maintenance_cron.sh
```

**用途**：5 training（linucb / scorer / quantile / mlde shadow / mlde demo） + 5 audit（thompson / optuna / cpcv / dl3 / weekly_report）daily fire
- **per memory `project_2026_05_09_ml_training_cron_weekly` 修正**：是 hybrid 不是 weekly；5 audit weekday=6 gate（週日跑），5 training daily fire（per-strategy MIN_SAMPLES=200 4/5 策略不過 grid 374 PASS 為主）
**Sprint 2 阻？**：**部分** — Alpha Tournament 若依賴 ML model（如 LinUCB allocator）則 4 day stale model 影響
**healthcheck 影響**：observability（ml 模型 4 day stale）
**復原風險**：中；training script 跑 ~30-60 min；佔 CPU；3:17 AM low traffic OK
**Verify SOP**：enable → 隔日 03:17 觸發 → 04:30 SSH 驗 `tail -100 /tmp/openclaw/logs/ml_training_maintenance.log` + `psql -c "SELECT MAX(updated_at) FROM learning.linucb_models;"` 應 < 24h
**ETA**：operator 30s
**PA 補充**：本 cron 跑時若 engine restart 並行 → 可能 cargo race（per M-4 hygiene SOP）；建議 03:17 avoid 與 atomic restart 重疊（restart_all.sh 平常不在 03:00 跑）

#### 2.1.4 `edge_label_backfill_cron.sh`（*/30 min）

**Cron 行（待 enable）**：
```cron
*/30 * * * * $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_label_backfill_cron.sh
```

**用途**：30min cadence backfill outcome label（fills → outcome_* 字段填充）
**Sprint 2 阻？**：**部分** — outcome chain 是 edge 估計 source；4 day stale 影響 edge_estimator 收斂（已有 [13] PASS = scheduler 健康，但 label backfill 缺失 = scheduler 沒 fresh data 算）
**healthcheck 影響**：edge label drift
**復原風險**：低；read PG fills → UPDATE outcome_*；冪等
**Verify SOP**：enable → 30 min 內觸發一次 → SSH 驗 `psql -c "SELECT COUNT(*) FROM learning.decision_outcomes WHERE outcome_pnl IS NOT NULL AND updated_at > NOW() - INTERVAL '1 hour';"` 應 > 0
**ETA**：operator 30s

### 2.2 MED/LOW SHOULD（Day -1 / Day 0 enable）

#### 2.2.1 `panel_aggregator_health_cron.sh`（*/5 min）

**Cron 行（待 enable）**：
```cron
*/5 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/panel_aggregator_health_cron.sh >>/tmp/openclaw/logs/panel_aggregator_health_cron.cron.log 2>&1
```

**用途**：每 5 min 跑 panel aggregator health（W1 BB WS-first 之 Rust `panel_aggregator` 健康監控）
**Sprint 2 阻？**：否 — observability only；但 W1 已 deploy（per memory N+1 D+0），無此 cron = panel 健康狀態不明
**healthcheck 影響**：[75] 3.61d stale
**復原風險**：低；read panel state file → format → write log
**ETA**：operator 30s

#### 2.2.2 `wave9_replay_no_live_mutation_watch.sh`（hourly @0）

**Cron 行（待 enable）**：
```cron
0 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh >>/tmp/openclaw/logs/wave9_replay_no_live_mutation_watch.cron.log 2>&1
```

**用途**：每小時驗 replay 過程不 mutate live state（safety invariant）
**Sprint 2 阻？**：否 — invariant check；但 Sprint 2 若含 nightly_replay 任務則必跑
**healthcheck 影響**：[76] 3.65d stale
**復原風險**：低；read-only check
**ETA**：operator 30s

#### 2.2.3 `replay_key_rotation_check.sh`（daily 09:00）

**Cron 行（待 enable）**：
```cron
0 9 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_rotation_check.sh >>/tmp/openclaw/logs/replay_key_rotation_check.cron.log 2>&1
```

**用途**：每日 09:00 驗 replay key 未過期（safety）
**Sprint 2 阻？**：否
**復原風險**：低；read-only key file mtime check
**ETA**：operator 30s

#### 2.2.4 `feature_baseline_writer_cron.sh`（daily 04:41）

**Cron 行（待 enable）**：
```cron
41 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/feature_baseline_writer_cron.sh >>/tmp/openclaw/logs/feature_baseline_writer_cron.cron.log 2>&1
```

**用途**：每日 04:41 寫 34-dim feature baseline（drift detection 用）
**Sprint 2 阻？**：否 — observability；但若 Sprint 2 含 drift event 偵測則必跑
**復原風險**：低
**ETA**：operator 30s

#### 2.2.5 `halt_audit_pg_writer_cron.sh`（every minute）

**Cron 行（待 enable）**：
```cron
*/1 * * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/halt_audit_pg_writer_cron.sh
```

**用途**：每分鐘將 halt audit log 副本寫 PG（observability channel）
**Sprint 2 阻？**：否
**復原風險**：中；高頻 PG write（60 次/h）；engine PG pool 已配 32 接 OK
**ETA**：operator 30s

#### 2.2.6 `logrotate-openclaw.conf`（hourly @0）

**Cron 行（待 enable）**：
```cron
0 * * * * /usr/sbin/logrotate -s /home/ncyu/logrotate-openclaw.state /home/ncyu/logrotate-openclaw.conf
```

**用途**：每小時 logrotate（engine.log > 1GB 切割）
**Sprint 2 阻？**：否 — 4 day engine.log 已 ~100MB 仍可承受；但若 Sprint 2 多 wave high-traffic 可能漲快
**復原風險**：低；rotate 不中斷 engine（engine 用 append + reopen 邏輯）
**ETA**：operator 30s

### 2.3 DEFER / 不復原（3 個）

#### 2.3.1 `passive_wait_healthcheck_cron.sh`（6h）

**動機**：用 sub-agent / 主會話手動 ssh 跑可替代；6h cadence cron noise > 主動觸發 value
**Defer 風險**：低；主會話 dispatch 前必 fresh healthcheck rerun
**OPTIONAL**：若 Sprint 2 進入 long-running 階段（>24h 無人值守）可考慮 enable

#### 2.3.2 `ref21_market_microstructure_recorder.py`（every minute, 10 symbol）

**動機**：每分鐘 × 10 symbol = 14400 row/day microstructure write；high noise；Sprint 2 不需此粒度
**Defer 風險**：observability gap（micro-structure regime detection 失準）；但 Sprint 2 業務 sprint 不直接消費此資料
**DEFER**：等 Sprint 4+ first Live 或 M12 maker-vs-taker stage 才需

#### 2.3.3 `blocked_symbols_30d_unblock_check_cron.sh`（weekly Sun 04:00）

**動機**：30d window unblock check；Sprint 2 持續 ~3 week 不會 trigger 30d；無 immediate value
**Defer 風險**：低；30d cycle 內無 symbol 自動 unblock
**DEFER**：Sprint 4+ first Live 前必 enable

---

## 3. Operator 動作指引

### 3.1 Day -1 必跑（4 個 HIGH/MED 阻 Sprint 2）

**方法 A：crontab -e 手動編輯（推薦，原子操作）**

```
ssh trade-core
crontab -e
# 找到 13 個 DISABLED_OPENCLAW_20260521 行
# 對下列 4 個 line 移除 "# DISABLED_OPENCLAW_20260521 " 前綴（連同空格）：
#   counterfactual_daily_cron.sh
#   ref21_symbol_universe_snapshot_cron.sh
#   ml_training_maintenance_cron.sh
#   edge_label_backfill_cron.sh
# 保存退出
crontab -l | grep -vE '^# DISABLED' | grep -v '^#' | wc -l
# 應顯示 8 行（原 4 + 新 enable 4）
```

**方法 B：sed one-liner（風險：可能誤刪其他 # DISABLED 行）**

不推薦 — Day -1 必跑用手動 edit，避免 sed pattern 誤觸其他 disabled marker。

### 3.2 Day 0 跟（5 個 LOW SHOULD）

同方法 A — 對下列 5 行移除前綴：
- `panel_aggregator_health_cron.sh`
- `wave9_replay_no_live_mutation_watch.sh`
- `replay_key_rotation_check.sh`
- `feature_baseline_writer_cron.sh`
- `halt_audit_pg_writer_cron.sh`
- `logrotate-openclaw.conf`

### 3.3 補裝 edge_estimate_snapshots wrapper（QC EA-2，2 min）

**Context**：wrapper commit `70e7b6b1` 5/9 land 但 cron 從未裝。先 verify 當前是否已 wrapped：

```bash
ssh trade-core 'cat /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh | head -20'
```

**Case A**：wrapper script 內含 EA-2 校準邏輯（grep 'EA-2' 或 'wrapper' 或 leader_lock）→ 無動作（已 wrapped）
**Case B**：wrapper script 是 simple call → land EA-2 校準邏輯到此 script（不在本 spec scope；另開 ticket）
**動作**：operator SSH probe + 視 case 決定（2 min）

---

## 4. Verify SOP（復原後 1h 內）

### 4.1 Cron 觸發驗

```bash
ssh trade-core 'date && crontab -l | grep -vE "^#|^$" | wc -l'
# 應顯示 8（Day -1 後）或 14（Day 0 後）
```

### 4.2 各 cron 寫入驗（按 cadence）

| Cron | 等待時間 | 驗證指令 |
|---|---|---|
| `edge_label_backfill_cron.sh` | 30 min | `ssh trade-core 'ls -lat /tmp/openclaw/logs/edge_label_backfill*.log \| head -3'` |
| `ref21_symbol_universe_snapshot_cron.sh` | 至下一個 :20 | `ssh trade-core 'ls -lat /tmp/openclaw/symbol_universe_snapshot/ \| head -3'` |
| `panel_aggregator_health_cron.sh` | 5 min | `ssh trade-core 'tail -20 /tmp/openclaw/logs/panel_aggregator_health_cron.cron.log'` |
| `halt_audit_pg_writer_cron.sh` | 1 min | `ssh trade-core 'psql -c "SELECT COUNT(*) FROM learning.halt_audit_log WHERE written_at > NOW() - INTERVAL 5 MINUTE;"'` |
| `counterfactual_daily_cron.sh` | 隔日 06:00 後 | `ssh trade-core 'tail -50 /tmp/openclaw/logs/counterfactual_daily_cron.log'` |
| `ml_training_maintenance_cron.sh` | 隔日 03:17 後 | `ssh trade-core 'tail -100 /tmp/openclaw/logs/ml_training_maintenance.log'` + `psql -c "SELECT MAX(updated_at) FROM learning.linucb_models;"` |
| `wave9_replay_no_live_mutation_watch.sh` | 至下一個整點 | `ssh trade-core 'tail -20 /tmp/openclaw/logs/wave9_replay_no_live_mutation_watch.cron.log'` |
| `replay_key_rotation_check.sh` | 隔日 09:00 | `ssh trade-core 'tail -20 /tmp/openclaw/logs/replay_key_rotation_check.cron.log'` |
| `feature_baseline_writer_cron.sh` | 隔日 04:41 | `ssh trade-core 'tail -20 /tmp/openclaw/logs/feature_baseline_writer_cron.cron.log'` |
| `logrotate-openclaw.conf` | 至下一個整點 | `ssh trade-core 'cat /home/ncyu/logrotate-openclaw.state \| grep "openclaw"'` |

### 4.3 Healthcheck rerun（復原後 ≥6h）

```bash
ssh trade-core 'bash /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck/run_all_checks.sh 2>&1 | grep -E "(FAIL|WARN)" | head -30'
```

**期望**：
- [11] counterfactual: FAIL → PASS（24h 內復原）
- [53] symbol_universe: FAIL → PASS（2h 內）
- [75-79] cron heartbeat stale: WARN → PASS（24h 內）
- 其他 disabled cron 對應的 healthcheck 應同步 PASS

---

## 5. 治理 follow-up（Sprint 2 內並行；不阻 Sprint 2 派發）

### 5.1 `helper_scripts/setup_openclaw_cron.sh`（防再發）

**目的**：crontab 納入 git；disable / enable 必經 commit；防 2026-05-21 silent 4-day 戰術 disable 再發
**ETA**：~2 hr（PA spec + E1 IMPL）
**功能**：
- 生成期望 crontab 列表 → 與 `crontab -l` diff
- 不一致時打 warn + 提示 operator 動作（不自動 apply 改 crontab）
- 配合 healthcheck [75-79] 之 cron heartbeat 監控

**owner**：PA 開 spec → E1 IMPL
**Sprint 2 阻？**：否；觀察治理

### 5.2 OPENCLAW_DATA_DIR 路徑審計（per E5 Pattern A 推斷）

**動機**：2026-05-21 集體 disable 可能與 OPENCLAW_DATA_DIR 路徑切換有關；若是則部分 cron path 可能已陳舊
**動作**：對 13 cron 路徑驗 OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR / OPENCLAW_SECRETS_ROOT 仍正確
**owner**：E5 sub-task；Day 0 並行 ~30 min

---

## 6. 風險評估

| 風險 | 機率 | 影響 | Mitigation |
|---|---|---|---|
| Enable cron 後 ml_training 跑時與 engine restart 並行 → cargo race | 低 | 中 | 03:17 AM 為 low-traffic；engine restart 避開 03:00-04:00 即可 |
| counterfactual_daily_cron.sh 06:00 跑 V### apply 失敗 | 低 | 低 | replay_manifest_registry 表不存在但 counterfactual 不依賴此表（M-3 獨立） |
| halt_audit_pg_writer */1 min 高頻 PG write 撐爆 pool | 低 | 低 | engine PG pool 32 接；60 row/h write 微不足道 |
| symbol_universe_snapshot 同時與 engine startup 拉 instruments-info race | 低 | 低 | snapshot 寫 file path 與 engine snapshot path 不同（後者在 /tmp/openclaw/instruments） |
| Operator 誤刪其他 # DISABLED 行 | 中 | 低 | 用方法 A 手動 edit；不用 sed |
| ml_training_maintenance 跑時 engine 用 GPU 衝突 | 低 | 低 | 訓練 CPU-based；無 GPU 衝突 |

---

## 7. PA 派 E1 IMPL 範圍（非本 spec scope；遺留下一步）

本 spec 為 **operator action spec**，無 E1 IMPL 任務。後續若 §5.1 setup_openclaw_cron.sh 派發：
- 並行 1 sub-agent E1：~2 hr setup script + diff verify
- 並行 1 sub-agent E1：~1 hr healthcheck path / table 對齊（per H-3 / M-3）

---

## 8. 結論

**Sprint 2 Day -1 派發 readiness**：
- [ ] Operator 30 min 完成 4 個 HIGH/MED cron enable（counterfactual + symbol_universe + ml_training + edge_label_backfill）
- [ ] Operator 2 min verify EA-2 wrapper（edge_estimate cron 已 wrapped）
- [ ] PA 派 E1 H-1 FD 200 leak fix + H-3 healthcheck path fix（已 specced in E5 audit）
- [ ] Day 0 enable 6 個 LOW SHOULD cron
- [ ] Day 0 跑 healthcheck rerun 驗各項 PASS

**Defer**：microstructure / blocked_symbols_30d / passive_wait healthcheck cron

**根治治理**：Sprint 2 內並行 setup_openclaw_cron.sh + crontab 納入 git；防 silent disable 再發

---

**Report END**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--h2_cron_restoration_spec.md`
