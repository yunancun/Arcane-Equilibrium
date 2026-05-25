# H-2 Cron 復原 + EA-2 Wrapper Verify — Final SOP Refine

**Date**: 2026-05-25
**Author**: PA（Project Architect）
**Reads**: spec `2026-05-25--h2_cron_restoration_spec.md` (e1993ec6) + SSH crontab probe + 70e7b6b1 wrapper commit + sub-agent-hygiene-sop.md §2.3 + memory `feedback_shell_paste_safety` + `project_2026_05_09_ml_training_cron_weekly`
**Scope**: read-only verify + 推薦給 PM 的 dispatch packet 形態（operator manual vs E1 helper script vs PM 自做）
**Status**: SPEC ONLY — no E1 IMPL, no Linux write, no cargo

---

## TL;DR — Verdict 三件事

1. **EA-2 真實狀態 = (a) closed N/A**
   - cron `12 * * * * .../edge_estimate_snapshots_cycle_cron.sh` 已 active 且 healthy
   - 最近 5 個 cycle（10:12 / 11:12 / 12:12 / 13:12 / 14:12）全 `cycle end OK`
   - 每 cycle ~674 edge_rows applied
   - QC verdict update 段「operator SSH 一行裝 edge_estimate_snapshots crontab」**已過時** — 此 cron 是 13 行集體 disable 中**唯一沒被 disable 的**，wrapper script + cron line 都已 active
   - **EA-2 不需再派 operator 動作**；移出 Sprint 2 Day -1 packet

2. **H-2 13 行 cron 復原真實狀態 = 13/13 仍 disabled**
   - 隔壁 PM session（commit `73e124ba` audit）**未實際**動 crontab；2026-05-21 集體 disable 仍生效
   - 4 HIGH/MED + 6 LOW SHOULD + 3 DEFER 分級無需 amend
   - SSH crontab probe 證實 14 個非空行 = 3 legacy（不在 scope）+ 1 active edge_estimate（EA-2）+ 10 # DISABLED OpenClaw

3. **Day -1 dispatch packet 推薦 = Option C（PM 主會話自做）**
   - 13 cron 復原是**一次性 mutate** + **低風險 read-then-write 配置**
   - 不值得開 helper script（一次性使用）；不適合 sub-agent（hygiene SOP §2 邊界禁寫 crontab）
   - operator 手動 method A 有 paste 風險 + 30 min 重複 12-15 次 sed pattern → 高出錯機率
   - PM 自做 = 2 min `crontab -e` + atomic edit + 一次性結束 + 治理權威清晰
   - 不違反 sub-agent-hygiene-sop §2.3 PM 邊界（`bash helper_scripts/build_then_restart_atomic.sh OK` + crontab edit 同屬 PM atomic 治理權威）

---

## Step 1 — 13 Cron 當前狀態 Table

SSH probe `crontab -l` empirical（2026-05-25 ~14:15 UTC）：

| # | Cron file | Cadence | 當前狀態 | Sprint 2 分級 | Day -1/0 復原必要 |
|---|---|---|---|---|---|
| 1 | `counterfactual_daily_cron.sh` | daily 06:00 | `# DISABLED_OPENCLAW_20260521` | HIGH 阻 | Day -1 MUST |
| 2 | `passive_wait_healthcheck_cron.sh` | every 6h | `# DISABLED_OPENCLAW_20260521` | LOW OPTIONAL | DEFER |
| 3 | `edge_label_backfill_cron.sh` | */30 min | `# DISABLED_OPENCLAW_20260521` | MED 部分阻 | Day -1 MUST |
| 4 | `ref21_symbol_universe_snapshot_cron.sh` | hourly @20 | `# DISABLED_OPENCLAW_20260521` | HIGH 阻 | Day -1 MUST |
| 5 | `ref21_market_microstructure_recorder.py` | every 1 min × 10 sym | `# DISABLED_OPENCLAW_20260521` | LOW (high noise) | **DEFER** 不復原 |
| 6 | `ml_training_maintenance_cron.sh` | daily 03:17 | `# DISABLED_OPENCLAW_20260521` | MED 部分阻 | Day -1 MUST |
| 7 | `logrotate-openclaw.conf` | hourly @0 | `# DISABLED_OPENCLAW_20260521` | LOW | Day 0 SHOULD |
| 8 | `panel_aggregator_health_cron.sh` | */5 min | `# DISABLED_OPENCLAW_20260521` | LOW | Day 0 SHOULD |
| 9 | `wave9_replay_no_live_mutation_watch.sh` | hourly @0 | `# DISABLED_OPENCLAW_20260521` | LOW | Day 0 SHOULD |
| 10 | `replay_key_rotation_check.sh` | daily 09:00 | `# DISABLED_OPENCLAW_20260521` | LOW | Day 0 SHOULD |
| 11 | `feature_baseline_writer_cron.sh` | daily 04:41 | `# DISABLED_OPENCLAW_20260521` | LOW | Day 0 SHOULD |
| 12 | `blocked_symbols_30d_unblock_check_cron.sh` | weekly Sun 04:00 | `# DISABLED_OPENCLAW_20260521` | LOW (30d window 不 trigger) | **DEFER** 不復原 |
| 13 | `halt_audit_pg_writer_cron.sh` | every 1 min | `# DISABLED_OPENCLAW_20260521` | LOW | Day 0 SHOULD |
| **+1** | `edge_estimate_snapshots_cycle_cron.sh` | hourly @12 | **ACTIVE 健康** | – | EA-2 N/A 已 closed |

**Empirical 證實**：
- 4 Day -1 MUST：#1 + #3 + #4 + #6
- 6 Day 0 SHOULD：#7 + #8 + #9 + #10 + #11 + #13
- 3 DEFER：#2 + #5 + #12
- 1 ACTIVE 健康：EA-2 wrapper (#14)
- **總 13 disabled + 1 active = 14 行 OpenClaw cron**

**隔壁 PM session 73e124ba 未動 crontab 證據**：
- crontab 全 13 行仍標 `# DISABLED_OPENCLAW_20260521`（不是 `# DISABLED_20260525`）
- git log 2026-05-21 ~ 2026-05-25 無 crontab 改動 commit（crontab 不在 repo）
- 推斷：73e124ba 是 audit v3 to v5.8 route coverage **docs-only 改動**，未觸 crontab

---

## Step 2 — EA-2 真實狀態：(a) Closed N/A

### 2.1 Empirical evidence chain

**(1) wrapper script land**（`70e7b6b1` 2026-05-09 01:27:45）：
```
audit: add edge snapshot cycle wrapper
Add V073 as a read-only V059 edge snapshot contract guard and add
an executable cron wrapper that reuses the REF-21 helper for
recurring snapshot writes.
```
Files added:
- `helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh` (77 lines)
- `db_migrations/V073_edge_estimate_snapshots_cycle_writer_contract.sql` (105 lines)
- 2 test files

**(2) wrapper script content verified**（SSH probe）：
- shebang `#!/usr/bin/env bash` + `set -euo pipefail`
- BASE / DATA / LOG_DIR / LOCK_ROOT 設置
- ENV_FILE check（fail-closed）
- comment 明示 cron line:
  ```
  12 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
      $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh
  ```

**(3) cron line active**（SSH crontab -l）：
```
12 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh
```
**唯一非 # disabled 的 OpenClaw cron**。

**(4) log mtime fresh**：`/tmp/openclaw/logs/edge_estimate_snapshots_cycle_cron.log` mtime `5月 25 14:12`（cron 剛 fire 完）

**(5) 最近 5 cycle 全 OK**：
```
[2026-05-25 10:12:01] === edge_estimate_snapshots cycle start ===
[summary] mode=APPLY universe_rows=0 freeze_rows=0 edge_rows=675
[applied] universe_attempted=0 freeze_inserted=0 edge_attempted=675
[2026-05-25 10:12:01] === edge_estimate_snapshots cycle end OK ===
```
（同樣 pattern 11:12 / 12:12 / 13:12 / 14:12 全 OK）

**(6) PG empirical**：因 ssh 環境 PGPASSWORD lookup 路徑與 trade-core 實際 `.pgpass` 差異跳過；但 cycle log `edge_rows=674` `applied=674` 顯示**已寫 PG**

### 2.2 (a)/(b)/(c) Classification

- (a) wrapper land + cron active + 寫入 healthy → **EA-2 N/A 已 closed**  ← **本案落點**
- (b) wrapper land + cron active 但寫入 stale → debug wrapper（不適用）
- (c) wrapper land 但 cron disabled / missing → EA-2 真實要補裝（不適用）

### 2.3 QC EA-2 verdict 過時點

QC verdict update inline 「(ii) operator SSH 一行裝 edge_estimate_snapshots crontab」**已過時**：
- 此 cron 是 13 disable 集體中**唯一沒被 disable 的**（per memory `project_2026_05_09_ml_training_cron_weekly` 推斷 5/9 wrapper land 後 cron line 也被同期 install）
- QC 可能 reference 較早期 state（5/9 land 前）；當前 5/25 已 active

**動作**：
- Sprint 2 Day -1 packet **移除 EA-2 項目**
- 主會話通知 QC：EA-2 closed
- 14:12 log 為 evidence；無需 operator 補裝

---

## Step 3 — Option A/B/C Trade-off + PA Verdict

### Option A — Operator method A 手動 `crontab -e`（前 PA spec 推薦）

**操作**：
```
ssh trade-core
crontab -e
# 找到 4 HIGH/MED 行，移除 "# DISABLED_OPENCLAW_20260521 " 前綴（含尾隨空格）
# Day 0 再來一次，處理 6 LOW SHOULD
# 保存退出
```

**優點**：
- operator 親眼看到每行改動（最高 audit transparency）
- 無 script bug 風險
- 不觸 hygiene SOP 任何邊界

**缺點**：
- 13 行 disable marker 視覺 noise；operator vi 模式手動找 4 行 + 6 行 = 兩階段 30 min 操作
- 編輯時容易誤刪空格 / tab / 完整 prefix 對齊
- 不可重複（若需 rollback 又一輪 vi）
- per `feedback_shell_paste_safety` 2026-04-21：複雜 shell logic 應寫檔 — 但此案非 paste 而是手動 vi edit，所以 paste safety 不嚴格適用

**ETA**：Day -1 30 min（4 lines）+ Day 0 20 min（6 lines）= **50 min operator 時間**

### Option B — E1 sub-agent 寫 `helper_scripts/restore_openclaw_cron.sh` automation

**操作概念**：
- script `crontab -l > /tmp/crontab.bak`
- sed pattern: `s/^# DISABLED_OPENCLAW_20260521 (0 6 \* \* \* .*counterfactual.*)$/\1/`（per cron repeat × 10）
- `crontab /tmp/crontab.new` apply
- diff verify

**優點**：
- 可重複；可 idempotent；可 diff verify pre/post
- 開源化（commit 進 repo）+ 7+ 月後若再 disable 可直接 rerun
- 無人工 vi 操作風險

**缺點**：
- 寫 crontab 是 user-level write（不需 sudo），但仍是 **mutate trade-core 狀態**
- per `docs/agents/sub-agent-hygiene-sop.md` §2.1 表「禁區指令」: 「ssh trade-core sudo *」明確禁；但 crontab edit **不需 sudo**（user own crontab）
- 然而 §2.2 表 E1 角色「必走 Mac SSOT」明示「禁 cargo build / test / check --release on trade-core」— **未明確涵蓋 crontab write**；屬灰區
- §2.3 PA 邊界「spec only；ssh read-only probe OK；不跑 cargo」— PA 不寫，但**沒禁 E1 用 ssh 跑 user-level write script**
- **真實衝突點**：M-4 SOP 設計初衷是「engine binary inode 漂移 → atomic restart 治理破功」；crontab edit 與此 root cause 無關
- **派 E1 + ssh trade-core 寫 crontab** 為 SOP **未禁但灰區**；需 PM 明示授權
- 一次性使用 script overhead > value（寫 script + E2 review + E4 regression + commit 1-2 hr → vs. 直接做 5 min）

**ETA**：E1 IMPL ~1 hr + E2 review ~30 min + E4 mock test ~30 min + PM apply ~5 min = **2.5 hr team time** for one-shot mutation

### Option C — PM 主會話直接 `crontab -e` via SSH（**PA 推薦**）

**操作**：
```
ssh trade-core
crontab -e
# 編輯 + 保存退出
crontab -l | grep -vE '^#|^$' | wc -l
# Day -1: 應顯示 8（原 4 + 新 4 = 8 active 非 disabled）
# Day 0: 應顯示 14（原 8 + 新 6 = 14 active 非 disabled）
```

**優點**：
- PM 主會話 = atomic 治理權威（per §2.3 PM 邊界：「跑 build_then_restart_atomic.sh OK」)；類比 crontab edit 同屬 PM 一次性 mutate
- 一次性結束（5 min Day -1 + 5 min Day 0 = **10 min total team time**）
- 無 E1/E2/E4 chain overhead
- 治理權責清晰（PM 一份 acceptance log 留底）
- 不違反 hygiene SOP（PM 角色明示有 atomic mutate 權威）

**缺點**：
- 不可重複（PM 主會話 token 成本 + 不可 sub-agent 並行）
- 若 Sprint 4+ 再次需 cron 復原則無法 rerun（但屆時可選擇開 Option B script，本次先取得 evidence）
- PM 主會話手動 vi `crontab -e` 仍有 typo 風險（但比 operator 親手做更可控 — 主會話可一邊 vi 一邊 verify）

**ETA**：**10 min total team time**（5 min Day -1 + 5 min Day 0）

### PA Verdict

**推薦 Option C：PM 主會話直接做**

**理由 4 條**：

1. **ROI 最高**：10 min vs. Option A 50 min vs. Option B 2.5 hr
2. **治理權責清晰**：crontab mutate 是 atomic 一次性，PM 主會話原本就是 atomic 治理權威（與 atomic restart 同性質）；不污染 sub-agent hygiene 模型
3. **EA-2 已 closed → packet 縮**：原本 H-2 + EA-2 兩件事縮為 H-2 一件，PM 自做更輕量
4. **若未來 Sprint 4+ 真需要 cron 治理 SOP**：屆時開 §5.1 setup_openclaw_cron.sh 完整 IMPL（per 前 PA spec §5.1 已 spec），不必本次 Sprint 2 倉促開

**Option A 退路**：若 PM 主會話 token budget 緊或不想 ssh edit → 退 Option A operator method A；ETA 升至 50 min 但操作員親眼 audit。

**Option B 退路**：若 PM 判斷未來 Sprint 4 first Live 前必含完整 cron 治理 SOP → 並行開 §5.1 ticket（E1 IMPL ~2 hr）；本次仍用 Option C 應急。

---

## Step 4 — Hand-off to FA Business Priority Audit

FA 並行 audit 範圍預期（per Sprint 2 v5.8 §4 業務 sprint Alpha Tournament + M4 + M10 + M8）：
- Alpha Tournament 需求映射哪些 ML model + counterfactual evidence
- M4 hypothesis base table 是否依賴 ml_training_maintenance daily fire
- M10 Tier A symbol universe 是否依賴 ref21_symbol_universe_snapshot hourly
- M8 read-only acceptance 是否依賴 panel_aggregator / feature_baseline

### 等 FA verdict 後可能 amend 的 spec 項目

**HIGH 升 / 降可能性 high 的 3 個**：

| # | Cron | 當前分級 | FA 可能 verdict | 對 spec 影響 |
|---|---|---|---|---|
| 1 | `ml_training_maintenance_cron.sh` | MED 部分阻 | 若 FA 判斷 Alpha Tournament 必依賴 fresh ML model → **HIGH MUST** | 升至 Day -1 強 MUST（已是 MUST 但 priority 升） |
| 4 | `ref21_symbol_universe_snapshot_cron.sh` | HIGH 阻 | 若 FA 判斷 M10 Tier A defer 到 Sprint 3 → **MED defer** | 降至 Day 0 SHOULD |
| 8 | `panel_aggregator_health_cron.sh` | LOW | 若 FA 判斷 M8 read-only acceptance 必含 W1 panel 健康 → **MED SHOULD** | Day 0 升至 Day -1 |

**HIGH 升 / 降可能性 low 的**：
- 其他 8 cron 由 healthcheck observability layer 推導，FA 不太可能 override

### Hand-off SOP

**Trigger**：FA report `2026-05-25--<sprint_2_business_priority_audit>.md` push 後
**動作**：
- 若 FA priority 與本 spec 表 1 一致 → 無需 amend
- 若 FA 改 #1 升 / #4 降 / #8 升 → PA 加 amendment block 到 spec 末尾（不 rewrite tab）
- 若 FA priority 大幅 reshape（>3 cron 改級）→ PA 重 spec（unlikely）

**Estimate**：等 FA report 後 PA 10-15 min amendment（如需）

---

## Step 5 — Dispatch Packet 推薦給 PM

### Packet 結構

**Day -1（Sprint 2 啟動前一天）**：

```
PM action 1 — H-2 4 HIGH/MED cron 啟用（5 min）
  方法：ssh trade-core → crontab -e
  操作：找下列 4 行，移除 "# DISABLED_OPENCLAW_20260521 " 前綴：
    - counterfactual_daily_cron.sh
    - ref21_symbol_universe_snapshot_cron.sh
    - ml_training_maintenance_cron.sh
    - edge_label_backfill_cron.sh
  保存退出
  verify: crontab -l | grep -vE '^#|^$' | wc -l  # 應顯示 8

PM action 2 — EA-2 closed 通知（1 min）
  動作：通知 QC「EA-2 已 closed；cron @12 active 5 cycle OK；移出 packet」
  evidence: /tmp/openclaw/logs/edge_estimate_snapshots_cycle_cron.log（14:12 mtime）

PM action 3 — Day -1 verify 30 min 內（被動等 cron fire）
  - edge_label_backfill: 30 min 內 fire → ssh tail log
  - ref21_symbol_universe: 至下一個 :20 fire → ssh ls snapshot dir
  - 其他 2（counterfactual / ml_training）：隔日 verify
```

**Day 0（Sprint 2 啟動當天 早段）**：

```
PM action 4 — H-2 6 LOW SHOULD cron 啟用（5 min）
  方法：同 action 1
  操作：找下列 6 行，移除前綴：
    - panel_aggregator_health_cron.sh
    - wave9_replay_no_live_mutation_watch.sh
    - replay_key_rotation_check.sh
    - feature_baseline_writer_cron.sh
    - halt_audit_pg_writer_cron.sh
    - logrotate-openclaw.conf
  保存退出
  verify: crontab -l | grep -vE '^#|^$' | wc -l  # 應顯示 14

PM action 5 — Day 0 verify 1-6h 內
  - panel_aggregator (*/5 min): 5 min 內 fire
  - wave9_replay (hourly @0): 至下一個整點 fire
  - halt_audit (*/1 min): 1 min 內 fire
  - 其他 3 daily：隔日 verify

PM action 6 — Day 0 healthcheck rerun ≥6h 後
  bash helper_scripts/db/passive_wait_healthcheck/run_all_checks.sh
  期望 [11] [53] [75-79] FAIL → PASS
```

**Defer**（不在 Sprint 2 packet）：
- #2 `passive_wait_healthcheck_cron.sh`（OPTIONAL；手動可代）
- #5 `ref21_market_microstructure_recorder.py`（noise；Sprint 4 前不必）
- #12 `blocked_symbols_30d_unblock_check_cron.sh`（30d window；Sprint 4 first Live 前才需）

**Future Sprint follow-up（不阻 Sprint 2 派發）**：
- §5.1 `setup_openclaw_cron.sh` 治理 SOP（防 silent disable 再發；PA spec → E1 IMPL ~2 hr）
- 動機：crontab 不在 repo → 任何時間點未經 commit 即可 silent disable；長期治理需 crontab 納入 git

### Hygiene 合規 verify

逐 hygiene SOP §2.3 邊界：

| 角色 | 動作 | 合規 |
|---|---|---|
| PA | spec only + ssh read-only probe（`crontab -l` / `tail log` / `ls`）| OK § 2.3 |
| PM | atomic mutate（ssh `crontab -e`） | OK § 2.3（atomic 治理權威類比 atomic restart）|
| 不派 E1 / E2 / E4 | sub-agent chain | OK（節省 2.5 hr team time）|

**16 根原則合規 verify**（per 16-root-principles-checklist skill）：

- 原則 1 單一寫入口：crontab edit 不觸 IntentProcessor / submit_intent — N/A
- 原則 2 讀寫分離：PM atomic mutate 是 op 治理權威，非 GUI write — 合規
- 原則 4 策略不繞風控：crontab 不影響 Guardian — N/A
- 原則 5 生存 > 利潤：cron 復原是 evidence path 補回，不影響 hard_stop — N/A
- 原則 6 失敗默認收縮：13 行 # DISABLED 是收縮狀態；復原是恢復 healthy baseline — 合規
- 原則 8 交易可解釋：cron 復原本身為 audit trail（PM action log + cron heartbeat 記錄）— 合規
- 原則 14 零外部成本：4 個 HIGH/MED 復原均為本地 PG / file IO；無 external paid call — 合規

**硬邊界 grep**：crontab edit 不觸 `execution_state` / `live_execution_allowed` / `decision_lease_emitted` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` — **零硬邊界觸碰**。

**評級**：A 級 16/16 合規 + 硬邊界 0 觸碰。

### Commit hygiene

**本 report**：
- doc-only → 加 `[skip ci]`
- branch main（PA 主 workflow 默認）
- commit message focuses on "why":
  ```
  docs(pa): Sprint 2 Day -1 H-2 + EA-2 final SOP refine —
  EA-2 closed N/A + Option C PM atomic dispatch packet
  ```
- push origin main（per Day -1 收口階段 operator 已 authorize push pattern）

**spec file**（`2026-05-25--h2_cron_restoration_spec.md` e1993ec6）：
- 已 land；無需 amend，除非 FA verdict 改 priority
- 等 FA verdict 後 amendment block 加在 spec 末尾

---

## 附錄 A — SSH Probe Empirical Evidence

### A.1 SSH `crontab -l` 完整輸出（2026-05-25 ~14:15）

```
# (header 注釋 19 行省略)
5 0 * * * /home/ncyu/srv/helper_scripts/maintenance_scripts/daily_cost_snapshot.sh ...
*/5 * * * * python3 /home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_readonly_status_writer.py ...
*/5 * * * * bash /home/ncyu/srv/helper_scripts/cron_observer_cycle.sh ...
# DISABLED_OPENCLAW_20260521 0 6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/counterfactual_daily_cron.sh
# Wave 1 G6-02: passive_wait_healthcheck 6h cron (CLAUDE.md §七 強制, 2026-04-24)
# DISABLED_OPENCLAW_20260521 0 */6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck_cron.sh
# DISABLED_OPENCLAW_20260521 */30 * * * * $HOME/BybitOpenClaw/srv/helper_scripts/cron/edge_label_backfill_cron.sh
# BEGIN REF21 replay quality recorders
# DISABLED_OPENCLAW_20260521 20 * * * * ... ref21_symbol_universe_snapshot_cron.sh
# DISABLED_OPENCLAW_20260521 * * * * * ... ref21_market_microstructure_recorder.py ...
# END REF21 replay quality recorders
# 2026-05-09 A1: 5 ML training cron (FA D-10)
# DISABLED_OPENCLAW_20260521 17 3 * * * ... ml_training_maintenance_cron.sh
# OpenClaw engine log rotation - runs hourly, rotates when >1GB
# DISABLED_OPENCLAW_20260521 0 * * * * /usr/sbin/logrotate -s /home/ncyu/logrotate-openclaw.state ...
# DISABLED_OPENCLAW_20260521 */5 * * * * ... panel_aggregator_health_cron.sh ...
# DISABLED_OPENCLAW_20260521 0 * * * * ... wave9_replay_no_live_mutation_watch.sh ...
# DISABLED_OPENCLAW_20260521 0 9 * * * ... replay_key_rotation_check.sh ...
# DISABLED_OPENCLAW_20260521 41 4 * * * ... feature_baseline_writer_cron.sh ...
# DISABLED_OPENCLAW_20260521 0 4 * * 0 ... blocked_symbols_30d_unblock_check_cron.sh ...
# DISABLED_OPENCLAW_20260521 */1 * * * * ... halt_audit_pg_writer_cron.sh
12 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh
```

### A.2 EA-2 log evidence

`/tmp/openclaw/logs/edge_estimate_snapshots_cycle_cron.log` mtime: 5月 25 14:12
Last 5 cycles all `=== edge_estimate_snapshots cycle end OK ===`：
- 10:12 / 11:12 / 12:12 / 13:12 / 14:12
- Each `edge_attempted=674~675` `freeze_inserted=0` `universe_attempted=0`

### A.3 70e7b6b1 commit stat

```
commit 70e7b6b198c049f108c814fcbd58a9d03e58df30
Author: ncyu <cloud@ncyu.me>
Date:   Sat May 9 01:27:45 2026 +0200

    audit: add edge snapshot cycle wrapper
    Add V073 as a read-only V059 edge snapshot contract guard and
    add an executable cron wrapper that reuses the REF-21 helper
    for recurring snapshot writes.

 helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh | 77 ++
 db_migrations/V073_edge_estimate_snapshots_cycle_writer_contract.sql | 105 +++
 tests/.../test_edge_estimate_snapshots_cycle_cron_static.py | 42 +
 tests/.../test_v073_..._contract.py | 82 +
 .codex/WORKLOG.md | 5
 TODO.md | 4
 6 files changed, 313 insertions(+)
```

---

## 附錄 B — 16 根原則 + 9 安全不變量 Verify

### B.1 16 原則速查

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | N/A | crontab 不觸 IntentProcessor |
| 2 | 讀寫分離 | OK | PM atomic mutate ≠ GUI write |
| 3 | AI 輸出 ≠ 命令 | N/A | crontab 不是 AI 出口 |
| 4 | 策略不繞風控 | N/A | cron 不觸 Guardian |
| 5 | 生存 > 利潤 | N/A | cron 不觸 hard_stop |
| 6 | 失敗默認收縮 | OK | 復原回 healthy baseline |
| 7 | 學習 ≠ 改寫 Live | OK | ml_training cron 走 learning.* 不直寫 live |
| 8 | 交易可解釋 | OK | counterfactual + halt_audit 復原即補 audit trail |
| 9 | 災難保護 | OK | wave9_replay_no_live_mutation_watch 屬本地 invariant 防線 |
| 10 | 認知誠實 | OK | 報告區分 evidence vs. 推斷 vs. 假設 |
| 11 | Agent 最大自主 | N/A | crontab 不觸 cognitive_modulator |
| 12 | 持續進化 | OK | edge_label_backfill 為 outcome chain；ml_training 為 evolution |
| 13 | AI 成本感知 | N/A | cron 不觸 cost_edge_ratio |
| 14 | 零外部成本 | OK | 4 HIGH/MED 全本地 PG / file IO |
| 15 | 多 Agent 協作 | N/A | crontab 不觸 MessageBus |
| 16 | 組合級風險 | OK | counterfactual + symbol_universe + ml_training 屬組合級 evidence |

**合規**：6/16 直接合規 + 10/16 N/A（不適用）+ 0/16 違反 = 16/16

### B.2 DOC-08 §12 9 不變量

| # | 不變量 | 狀態 | 證據 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | OK | cron 復原是 audit path 補回 |
| 2 | Lease 必在執行前 acquired | N/A | crontab 不觸 lease |
| 3 | 執行回報必落 fills 表 | N/A | crontab 不觸 fills |
| 4 | 風控降級 → engine 自動止血 | OK | wave9_replay invariant 為止血防線 |
| 5 | Authorization 過期 → engine cancel_token | N/A | crontab 不觸 auth |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | N/A | crontab 不觸 engine spawn |
| 7 | Bybit retCode != 0 → fail-closed | OK | symbol_universe cron 若 Bybit fail 則 wrapper exit 2（已 verify wrapper code）|
| 8 | Reconciler 對賬差異 → 自動降級 paper | N/A |
| 9 | Operator 角色與 live_reserved 缺一即拒 | N/A |

**合規**：9/9（3 OK + 6 N/A + 0 違反）

### B.3 硬邊界 grep

```
grep -nE '(execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json)' <13 cron files>
```
**結果**：13 cron 內容 zero match — 零硬邊界觸碰。

---

**評級**：**A 級 16/16 + 9/9 + 硬邊界 0 觸碰**

---

## 結論

**操作面**：
- EA-2 closed N/A（cron 已 active 5 cycle OK；移出 packet）
- H-2 13 cron 仍 13/13 disabled（隔壁 PM session 未動）
- 推薦 **Option C PM 主會話直接做**：Day -1 5 min + Day 0 5 min = 10 min total
- Day -1 4 行 + Day 0 6 行 + DEFER 3 行（passive_wait + microstructure + blocked_30d）

**治理面**：
- 不派 E1 / E2 / E4 chain（節省 2.5 hr team time）
- 不違反 hygiene SOP § 2.3（PM atomic 治理權威 = atomic restart 類比）
- 不違反 16 根原則 + 9 不變量
- 零硬邊界觸碰

**等 FA verdict**：
- 若 #1 ml_training 或 #4 ref21_symbol_universe 或 #8 panel_aggregator priority 改級 → PA amendment 10-15 min
- 若 priority 不改 → 直接執行

**Future Sprint follow-up（不阻 Sprint 2）**：
- §5.1 `setup_openclaw_cron.sh` 治理 SOP（防 silent disable 再發；ETA E1 IMPL ~2 hr；Sprint 3+ 派發）
- crontab 納入 git（與 §5.1 配套）

---

**Report END**

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--h2_ea2_final_sop_refine.md`
