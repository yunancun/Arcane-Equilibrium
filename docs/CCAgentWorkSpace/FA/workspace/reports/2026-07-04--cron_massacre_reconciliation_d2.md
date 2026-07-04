# P0-2 Cron 屠殺全量對帳 + D2 決策表 — 2026-07-04

Bound role: FA（Functional Auditor）· skill: spec-compliance · 任務=修復前置取證/設計 wave
Scope: 06-27 crontab 70→空→5 置換事件全鏈還原 + 33 被殺 lane 逐條分類 + D2 恢復決策表 + F12 + mutation 治理規則草案（P0-2④）
Evidence base: trade-core journalctl（保留至 2026-03）、/tmp/openclaw 快照鏈、~/BybitOpenClaw/var/openclaw 遷移後 log、Mac repo `srv`（多 session 髒樹，本任務零代碼修改）、PM/E4/FA 既有報告。runtime 全程 read-only。

## Verdict: DONE — 70 行原文 100% 還原;屠殺=06-27 15:59:33Z 單次無記錄 REPLACE 清空;33 條 active lane 被殺,32 條至今仍死;分類=誤刪(高置信),非有意退役

---

## 一、事件全鏈還原(FACT,逐條帶錨)

時間全為 trade-core 本地 CEST(UTC+2);journal 錨 = `journalctl _COMM=crontab`。

| # | 時刻 | 事件 | 證據 |
|---|---|---|---|
| 1 | 06-27 00:45 | 70 行候選檔落地(路徑截斷 workaround) | `/tmp/openclaw/crontab_e29c96cc.txt` sha256=8403678a…(=PM 報告 `2026-06-27--standing_demo_false_negative_preflight_runtime_sync_apply.md:12` crontab_post);該報告 :73 記錄 `/usr/bin/crontab` 長路徑截斷失敗先例 |
| 2 | 06-27 日間 | 至少 8 次合法 pin-sync REPLACE,每次 70 行保持,全部留 before/after 快照 | `/tmp/openclaw/runtime_source_sync_*/crontab.{before,after,installed}` 系列;journal REPLACE 15:00:05/15:16:39/15:30:37/15:52:45 等 |
| 3 | 06-27 16:07:21 | **最後一次合法安裝(last-known-good)**:70 行,pins→`451be917` | journal `crontab[3996016] REPLACE`;manifest `/tmp/openclaw/runtime_source_sync_gui_risk_cap_authorization_20260627T140803Z/runtime_sync_manifest.json` `crontab_line_count=70` |
| 4 | 06-27 17:57:59 | standing-auth 1556Z session 寫 preview | `/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.preview_20260627T1556Z.json` |
| 5 | **06-27 17:59:33** | **屠殺:`crontab[4048696] (ncyu) REPLACE`——裝入空表。無 before/after 快照、無 manifest、無報告承認** | journal 06-27 17:59:33;18:00:01 `cron RELOAD`;1 分鐘 lane halt_audit 最後執行 17:59:01(`var/openclaw/logs/halt_audit_pg_writer_cron.log` 尾行) |
| 6 | 06-27 18:00 → 06-29 20:44 | **crontab 空表 ~50.7h,journal 零 REPLACE** | journal 該窗口無事件;06-29 audit 記錄「Runtime `crontab -l` was empty」(`PM/workspace/reports/2026-06-29--learning_engine_completion_engineering_plan.md:34`) |
| 7 | 06-29 20:44:01-20:44:05 | 4 次 REPLACE = `install_demo_learning_stack_crons.sh` 裝回 4 條 demo-learning stack(pin `f2a827c2`,該 commit 20:38:14 才生成) | journal 4 連 REPLACE;快照 `/tmp/openclaw/session_loop_state_20260629T_runtime_followup/crontab_before_ml_training_restore_20260629T184440Z.txt`(4 行) |
| 8 | 06-29 20:44:40 | ml_training 恢復 → 5 行 | journal `crontab[924650] REPLACE`;快照 crontab_before_expected_head_repin_20260629T185015Z.txt(5 行) |
| 9 | 06-29 20:50-21:07 | 5 次 repin(終態後至 06-30 pin `00a78d92`) | journal + session_loop_state 快照系列 |
| 10 | 07-04 16:40 窗口 | 5 條改 env(`var/openclaw`)+pin `3a050b60`;裝回 passive_wait_healthcheck(13,43)+announcement sentinel(7,37) → 現 7 行 | `crontab -l` 實測;備份 `~/BybitOpenClaw/var/crontab_backup_20260704T_pre_window.txt` |

**屠殺方式判定**:journal 記 REPLACE 而非 DELETE → 不是 `crontab -r`,是「餵入空內容的安裝」。機制候選(ASSUMPTION,無法再收斂):`crontab -` 吃到空 stdin,或 `crontab <檔>` 吃到空/截斷檔(#1 有同日截斷先例)。行為人=Codex 時代 agent session;17:59:33 距 1556Z standing-auth session 最後產物僅 95 秒,但該 session 報告(`2026-06-27--false_negative_packet_refresh_standing_auth_materialized.md:85`)明文自稱「no env/crontab mutation」——**journal 與 boundary 聲明矛盾**(同 session 漏報、或並行 session 所為,證據不足以二選一)。與所有合法 mutation 不同,此次獨缺快照/manifest → 分類 **誤刪(confidence: high)**;全倉零退役決策記錄,且 06-29 重裝僅覆蓋自家 4 條、無任何恢復其餘 33 條的嘗試,佐證非有意退役。

## 二、70 行原文與傷亡清點(FACT)

- **原文 100% 還原**:`/tmp/openclaw/runtime_source_sync_gui_single_position_cap_guard_20260627T125640Z/crontab.after_pin_fix`(sha256 前綴 `5c4565b682d2`,70 行,pins=`a9436c8a`)。與 last-known-good(#3,pins=`451be917`)僅差 pin 字面;pins 在 D2 全部按部署時 HEAD 重派生,故此差異不影響恢復。副本已存 conductor scratchpad,全文結構:23 行 header 註釋 + 6 行行內註釋 + 3 行 `DISABLED_OPENCLAW_20260521` + **38 條 active**。
- **傷亡帳**:38 active − 4(demo-learning stack 06-29 重裝)− 1(ml_training 06-29 恢復)− 1(announcement sentinel 07-04 窗口恢復)= **32 條至今仍死**。
- **對既有報告的修正**(誠實糾錯):
  1. FA 07-03 F2 稱「~12 producer crons」→ 實際被殺 33、仍死 32(當時僅以 log 檔名反推,低估)。
  2. PA plan P0-2 將 passive_wait_healthcheck 列為被殺 → **錯**:它自 2026-05-21 即被 `DISABLED_OPENCLAW_20260521` 註釋停用(70 行版 line 28),屠殺前就不跑;07-04 窗口是「升級性重啟用」(新 module 路徑+30 分頻率)而非「裝回」。
  3. engine_watchdog 從來不是 cron,是 systemd unit `openclaw-watchdog.service`(現 enabled+active,MainPID 3160326,16:40:44 起)——屠殺對它無影響。真正的 watchdog 事故軸在 P0-1(cgroup 連坐),與本案無關。

**07-03 03:02 無記錄 engine 重啟 ≠ 本案**:TODO P0-1 已溯源為 watchdog systemd cgroup 自愈,與 crontab 屠殺為兩件獨立無記錄 mutation。

## 三、間接損害量化(FACT,支撐 D2 優先級)

| 損害 | 證據 | 斷供時長 |
|---|---|---|
| **PG 每日備份斷供** | `/home/ncyu/pg_backups` 最新=`trading_ai_2026-06-27.dump`(03:14,13.5GB),其後零新檔 | 7 天(進行中) |
| 審計鏡像斷(DOC-06/07 面) | halt_audit(1min)最後 17:59:01、canary(2min)最後 17:58 | 7 天 |
| engine log rotation 停 | `/home/ncyu/logrotate-openclaw.state` mtime 06-27 17:00 | 7 天 |
| 學習 producer 斷供 | edge_label_backfill 17:30 / edge_estimate 17:12 / daily_kline 06-27 05:29 後全凍(`var/openclaw/logs/` mtime) | 7 天 |
| flash_dip 觀測族斷(唯一活躍成交通道的監測) | flash_dip_touchability 17:17 等 4 lane | 7 天 |
| alpha 軸全斷 | alpha_discovery/adpe/polymarket×2/leadlag/deribit/vol_event | 7 天 |
| 隱患:alpha_discovery log 無界 | `var/openclaw/logs/alpha_discovery_throughput_cron.log` = **1.47GB** 無 rotation | 恢復前置條件 |

## 四、F12 收口(FACT)

E4 F12 稱「兩個 cron log 0-byte,head-gated cron 行為未驗」。實測:**5 條倖存 lane 的 crontab 層 `.cron.log` 全部 0-byte**(demo_learning_evidence 06-24 00:07 / sealed_horizon 06-24 00:22 / cost_gate 06-24 00:27 / healthcheck 06-24 00:32 / ml_training 06-30 03:17),非兩個——E4 抽樣低估。**原因=良性**:各 wrapper 內部 `>> "$LOG"` 顯式寫自身 `<lane>_cron.log`/`<lane>.log`(例 `helper_scripts/cron/cost_gate_learning_lane_cron.sh:672,680`),crontab 層重定向收不到任何輸出;`.cron.log` 僅在 wrapper 於內部重定向建立前失敗時才會有內容,0-byte 反而證明無 pre-redirect 失敗。**行為已驗活**:內部 log 07-04 17:07(evidence)/17:22(sealed)/17:29(cost_gate)/17:32(healthcheck)/03:32(ml_training)均有新寫入 → 5/5 lane 遷移後正常。

## 五、三條快恢復驗證(任務 §4)

| lane | 腳本在 repo | 依賴 | 現狀 | 確切 cron 行/unit |
|---|---|---|---|---|
| bybit_announcement_sentinel | `helper_scripts/cron/bybit_announcement_sentinel_cron.sh` + `install_bybit_announcement_sentinel_cron.sh` ✅ | 公網 announcement API(read-only) | **已裝回且活**:07-04 17:37 `round done items=50` | `7,37 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/bybit_announcement_sentinel_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/bybit_announcement_sentinel_cron.cron.log 2>&1`(=現行第 7 行,已驗) |
| passive_wait_healthcheck(含 PROFIT-1 哨兵[90]) | `helper_scripts/db/passive_wait_healthcheck/runner.py` ✅ | PG(runtime_secrets url file 已遷 var) | **已裝回且活**:07-04 17:14 log 更新;SUMMARY=FAIL 是**正確行為**(如實指出其餘 cron 未裝=監測復明);TODO 記手測 90+ 檢查跑通、[90] PASS | `13,43 * * * * cd /home/ncyu/BybitOpenClaw/srv && OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_DATABASE_URL="$(cat /home/ncyu/BybitOpenClaw/var/openclaw/runtime_secrets/openclaw_database_url)" python3 -m helper_scripts.db.passive_wait_healthcheck.runner >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/passive_wait_healthcheck.cron.log 2>&1`(=現行第 6 行,已驗) |
| engine_watchdog | `helper_scripts/engine_watchdog.py`(systemd 形態) | systemd user unit | **非 cron**;`openclaw-watchdog.service` enabled+active(16:40:44 起,MainPID 3160326) | 無 cron 行;驗收=`systemctl --user is-active openclaw-watchdog.service`=active |

## 六、逐條分類 + D2 決策表(任務 §2/§3)

分類口徑:`有意退役`(有決策記錄)/`誤刪`(屠殺連坐,無退役記錄)/`superseded`(功能被更新形態取代)/`未知`。**32 條仍死 lane 全部屬「誤刪」(confidence high,全倉零退役記錄)**,其中 2 條同時是 superseded-legacy(建議借機正式退役)。腳本存在性已逐一驗(30/30 wrapper 在 repo;`bybit_readonly_status_writer.py` 已遷至 `program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/`,舊 cron 指向的 legacy `/home/ncyu/srv` 佈局)。

**Env 統一規則(operator 已裁決)**:`OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw`;log 重定向 → `…/var/openclaw/logs/`;所有 wrapper 已驗 `${OPENCLAW_DATA_DIR:-/tmp/openclaw}` 形態(如 `edge_label_backfill_cron.sh:76`、`trading_ai_pg_dump_cron.sh:46`、`halt_audit_pg_writer_cron.sh:21`、`counterfactual_daily_cron.sh:57`),env 必須顯式給、不得依賴默認。**pin 值**:下表寫 `3a050b60` 為當前值;E1 安裝時必須以 `git -C ~/BybitOpenClaw/srv rev-parse --short HEAD` 重派生(P1-4 pin-by-reference 同批)。

### Tier 0 — 資料保全/審計,建議無爭議即批(4 條)

| lane | 分類 | 理由 |
|---|---|---|
| trading_ai_pg_dump | 誤刪 | PG 全庫每日備份,斷 7 天=不可逆風險面 |
| logrotate-openclaw | 誤刪 | engine log 無界成長;E1 需先驗 conf 內路徑對齊遷移後佈局 |
| halt_audit_pg_writer | 誤刪 | DOC-06/07 audit PG 鏡像(1min) |
| canary_audit_pg_writer | 誤刪 | ENGINE-AUDIT-VISIBILITY backstop(2min);canary_events.jsonl 唯一消費者 |

```crontab
0 3 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets OPENCLAW_BACKUP_ROOT=/home/ncyu/pg_backups OPENCLAW_BACKUP_RETENTION_DAYS=30 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/trading_ai_pg_dump_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/trading_ai_pg_dump_cron.cron.log 2>&1
0 * * * * /usr/sbin/logrotate -s /home/ncyu/logrotate-openclaw.state /home/ncyu/logrotate-openclaw.conf
*/1 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/halt_audit_pg_writer_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/halt_audit_pg_writer_cron.cron.log 2>&1
*/2 * * * * cd /home/ncyu/BybitOpenClaw/srv && OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_DATABASE_URL_FILE=/home/ncyu/BybitOpenClaw/var/openclaw/runtime_secrets/openclaw_database_url /usr/bin/python3 helper_scripts/canary/canary_audit_pg_writer.py >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/canary_audit_pg_writer.cron.log 2>&1
```

### Tier 1 — 學習/風控/監測 producer,建議恢復(14 條)

全部分類=誤刪。edge_label_backfill+edge_estimate=學習 label/cost_gate 邊際數據上游;daily_kline=V141 kline guardrail 依賴(P2-11 雙盲之一);counterfactual=Phase 4 反事實 lane;ref21=符號宇宙快照;gate_b_watch=listing 探針(與 announcement sentinel 配套);panel/feature_baseline/recorder_health/recorder_mm_verdict/fill_sim/wave9/replay_key/m11=風控與 replay 健康面。

```crontab
*/30 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/edge_label_backfill_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/edge_label_backfill_cron.cron.log 2>&1
12 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/edge_estimate_snapshots_cycle_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/edge_estimate_snapshots_cycle_cron.cron.log 2>&1
29 5 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/daily_kline_backfill_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/daily_kline_backfill_cron.cronout.log 2>&1
0 6 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/counterfactual_daily_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/counterfactual_daily_cron.cron.log 2>&1
20 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/ref21_symbol_universe_snapshot_cron.cron.log 2>&1
12,42 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/gate_b_watch_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/gate_b_watch_cron.cron.log 2>&1
*/5 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/panel_aggregator_health_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/panel_aggregator_health_cron.cron.log 2>&1
41 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/feature_baseline_writer_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/feature_baseline_writer_cron.cron.log 2>&1
0 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/wave9_replay_no_live_mutation_watch.cron.log 2>&1
0 9 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_rotation_check.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/replay_key_rotation_check.cron.log 2>&1
0 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/m11_replay_runner_daily_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/m11_replay_runner_daily_cron.cron.log 2>&1
23 6 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/recorder_health_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/recorder_health_cron.cronout.log 2>&1
41 6 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/recorder_mm_verdict_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/recorder_mm_verdict_cron.cronout.log 2>&1
5 6 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/fill_sim_refresh_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/fill_sim_refresh_cron.cronout.log 2>&1
```

### Tier 2 — flash_dip 觀測族(唯一活躍成交通道的監測),建議恢復(4 條)

分類=誤刪。flash_dip_buy 是現階段唯一有 fills 的策略;其 touchability/death_rate/execution_realism/exit_replay 監測斷供=在盲飛。

```crontab
17 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_touchability_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/flash_dip_touchability_cron.cronout.log 2>&1
53 6 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_death_rate_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/flash_dip_death_rate_cron.cronout.log 2>&1
29 6 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_execution_realism_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/flash_dip_execution_realism_cron.cronout.log 2>&1
31 6 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_l1_short_exit_replay_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/flash_dip_l1_short_exit_replay_cron.cronout.log 2>&1
```

### Tier 3 — research/alpha 軸,恢復但 operator 可按 token/資源預算裁剪(8 條)

分類=誤刪。按 06-13 搜索空間結論+06-14 非常規數學 mandate,這些是 alpha 發現面;斷供 7 天=進化環節斷供。**alpha_discovery 恢復前置=log rotation(現 1.47GB)**。

```crontab
*/15 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_EXPECTED_SOURCE_HEAD=3a050b60 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/alpha_discovery_throughput_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/alpha_discovery_throughput_cron.cronout.log 2>&1
*/30 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw HOME=/home/ncyu /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/adpe_runner_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/adpe_runner.cron.log 2>&1
41 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_POLYMARKET_QUERY_SET=v2 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_axis_cron.sh daily >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/polymarket_axis_cron.cron.log 2>&1
7,22,37,52 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_POLYMARKET_QUERY_SET=v2 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_axis_cron.sh hourly-topn >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/polymarket_axis_cron.cron.log 2>&1
2,17,32,47 * * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_POLYMARKET_LEADLAG_QUERY_SET=v2 OPENCLAW_POLYMARKET_LEADLAG_MIN_POINTS=30 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/polymarket_leadlag_ic_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/polymarket_leadlag_ic_cron.cron.log 2>&1
17 5 * * * cd /home/ncyu/BybitOpenClaw/srv && OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw PYTHONPATH=/home/ncyu/BybitOpenClaw/srv/helper_scripts/research:/home/ncyu/BybitOpenClaw/srv /usr/bin/python3 -m deribit_vol_axis.cli --mode daily >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/deribit_vol_axis.cron.log 2>&1
0 */2 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw /home/ncyu/BybitOpenClaw/srv/helper_scripts/research/order_flow_alpha/vol_event_trigger.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/vol_event_trigger.cron.log 2>&1
23 5 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets OPENCLAW_L2_MEMORY_PIPELINE=1 OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1 /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/l2_memory_distill_cron.sh >> /home/ncyu/BybitOpenClaw/var/openclaw/logs/l2_memory_distill_cron.cron.log 2>&1
```

### Tier 4 — 建議借機正式退役(2 條,需 operator 一句話 ack)

| lane | 分類 | 理由 |
|---|---|---|
| bybit_readonly_status_writer(*/5) | 誤刪+superseded-legacy | 指向 legacy `/home/ncyu/srv` 舊佈局(`scripts/` 子目錄);現 repo 同名檔在 `readonly_observer_pipeline/`,由現行棧供狀態。不恢復=不損失現行功能;正式退役需記錄 |
| cron_observer_cycle(*/5) | 誤刪+superseded-legacy | 同上,log 寫 legacy `log_files/`。腳本仍在現 repo 但 cron 指 legacy checkout |

### 既有 DISABLED / 從未安裝(記錄在案,不屬本次恢復)

- `DISABLED_OPENCLAW_20260521` ×3:passive_wait_healthcheck 6h 版(已被 07-04 新版取代)、ref21_market_microstructure_recorder、blocked_symbols_30d_unblock_check —— 屠殺前即停,維持退役,補「owner=operator/退役日 2026-05-21」記錄。
- residual_stage0r_preflight:從未進 crontab(FA 07-03 F12,flag 默認 0)——獨立 dormant 決策,不混入 D2。

### 06-29 重裝引入的兩處 env drift(現行 7 行仍帶,D2 同批修)

1. **ml_training 行丟失 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1`**:70 行版 line 35 有、06-29 恢復版起消失 → residual alpha producer PART1-3(2026-06-05 flag-ON 部署)自 06-29 被靜默降級為 OFF。修:恢復該 env(QC 確認無新反對意見後)。
2. **cost_gate 行丟失 `OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON=…`**:06-26 E3 審批的 wiring(`2026-06-27--standing_demo_loss_control_envelope_runtime_materialization_apply.md:26`)被 06-29 重裝抹掉。修:併 P1-1 over-gate 統一設計批(standing envelope 路徑現應為 `/home/ncyu/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`),不單獨零敲碎打。

## 七、P0-2④ crontab mutation 治理規則(草案,交 PM/CC 落 DOC-06 側)

1. **正本入 repo**:新增 `helper_scripts/cron/crontab.trade-core.template`(per-host 正本;pin 欄位用 `{{HEAD}}` 佔位),隨代碼走 review。live crontab 只是它的 render 產物。
2. **唯一安裝入口**:新增 `helper_scripts/cron/install_crontab_from_repo.sh`:(a) render pins=`git rev-parse --short HEAD`;(b) `crontab -l` 快照+diff;(c) before/after/diff/manifest 落**持久路徑** `~/BybitOpenClaw/var/openclaw/crontab_mutations/<UTC>Z/`(本案教訓:快照在 /tmp 也能活下來純屬僥倖);(d) **shrink-guard**:新表 active 行數 < 現表 50% 時拒絕,除非 `OPENCLAW_CRONTAB_ALLOW_SHRINK=1` 顯式豁免——直接封殺本事故類型;(e) 空表/空 stdin 一律拒絕。
3. **變更留檔強制**:manifest 必含 actor/session-id、reason、pre/post sha256、行數 delta;引用進當次 session 報告。報告中「no crontab mutation」boundary 聲明必須附 `journalctl _COMM=crontab --since <window>` 查核結果(本案證明該查核零成本且決定性)。
4. **持續巡檢**:passive_wait_healthcheck 增檢查項「live crontab sha vs repo 正本 render sha」,不一致 >24h = FAIL(現有 WARN 升級);journal 出現無對應 manifest 的 REPLACE = FAIL。
5. **DOC-06 對齊**:crontab REPLACE 屬 runtime mutation,納入 append-only 變更審計序列(與 CC P3「runtime mutation 紀錄規則」條合併,含 07-03 03:02 watchdog 自愈類)。

## 八、驗收標準(Operator 視角,E4 可直接執行)

- **A1 恢復完整性**:D2 批准集合裝回後,`crontab -l` 非註釋行數=批准數;每條 lane 在 2× 自身週期內於 `var/openclaw/logs/` 產生新寫入(mtime 前進)。
- **A2 備份復活**:恢復後 24h 內 `/home/ncyu/pg_backups` 出現新 `trading_ai_<date>.dump`。
- **A3 監測復明**:passive_wait_healthcheck SUMMARY 由 FAIL 轉 PASS(missing-cron WARN 清零);哨兵[90] 維持 PASS。
- **A4 mutation 可追溯**:每次安裝在 journal 恰有對應 REPLACE,且 `var/openclaw/crontab_mutations/` 有同刻 manifest;裝回批次的 session 報告引用 manifest 路徑。
- **A5 shrink-guard 生效**:對 30+ 行 live 表嘗試安裝 3 行表 → installer 無豁免 flag 時拒絕(負向測試)。
- **A6 pin 派生**:安裝產物中所有 `EXPECTED_HEAD`/`EXPECTED_SOURCE_HEAD` == 安裝時 `git rev-parse --short HEAD`,無手寫字面。
- **A7 drift 修復**:ml_training 行含 `OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1`(若 QC 無新反對);cost_gate standing-auth env 依 P1-1 統一設計結論處置並留檔。

## 九、業務鏈影響(對齊 e2e 分段)

| 環節 | 屠殺影響 | 恢復後預期 |
|---|---|---|
| 掃描/數據 | daily_kline/ref21 斷 → kline guardrail 雙盲 | V141 復明 |
| 學習 | edge_label/edge_estimate/counterfactual 斷 7 天(45%→事實上更低) | producer 復供,45%→55% 路徑重開 |
| 進化 | alpha 軸全斷(20% 的上游) | 發現面恢復 |
| 審計(DOC-06/07) | halt/canary PG 鏡像斷+PG 備份斷=不可逆風險 | T0 修復即閉 |
| 止損/下單 | 無直接影響(engine 內部,不依賴 cron) | — |

## 十、殘留不確定(誠實聲明)

1. 屠殺行為人的 session 級身份:journal 只有 PID,無 cmdline/parent 存證;1556Z session 嫌疑最大但其報告自稱未動 crontab——**無法終判,亦無需終判**(治理規則②③使之不可復發,比追責更有價值)。
2. 屠殺用的具體命令形態(`crontab -` 空 stdin vs 空檔案):ASSUMPTION,不影響任何 D2 決策。
3. last-known-good(pins=451be917)與還原正本(pins=a9436c8a)僅差 pin 字面(INFERENCE,基於兩者間 journal 僅 pin-sync 類 REPLACE);D2 全部重派生 pin,故零影響。
4. Tier 1/3 個別 lane 的當前業務價值(如 adpe 在 ADPE no-op 結論後、m11 replay 現狀)未逐一重估——恢復=回到屠殺前現狀;逐 lane 價值重估屬 P2-10 token 稅批,不在本案範圍。

FA AUDIT DONE: report path: docs/CCAgentWorkSpace/FA/workspace/reports/2026-07-04--cron_massacre_reconciliation_d2.md
