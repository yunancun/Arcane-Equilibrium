# E5 Runtime Hygiene Audit — Pre Sprint 2 Dispatch

**Date**: 2026-05-25 02:30 UTC（Linux trade-core 採 CEST = UTC+2）
**Scope**: read-only audit of trade-core runtime before v5.8 §4 Sprint 2 派發
**Author**: E5（Optimization Engineer）
**Reads**: PM 2026-05-25 sprint_1a_1b_recheck + TODO §5 P1/P2/P3 queue + Linux runtime SSH probes
**Constraint**: 不改業務代碼；不寫操作；只列修法 + 排優先級

## TL;DR

| ID | Issue | Severity | LOC est | Owner | 阻 Sprint 2 派發? |
|---|---|---|---|---|---|
| **H-1** | `build_then_restart_atomic.sh` FD 200 flock leak → 當前 engine PID 374287 仍持鎖；下次 atomic restart 會 self-block | **CRITICAL** | 5-10 (restart_all.sh) | E1 直接 IMPL | **是** — 阻所有 Sprint 2 Linux deploy（rebuild 必經 atomic） |
| **H-2** | 13 個 OpenClaw cron 在 2026-05-21 集體 `DISABLED_OPENCLAW_20260521` 並從未復原 → counterfactual/symbol_universe/replay_manifest/cron_heartbeat 全 4 day stale；多項 healthcheck 真實 root cause = 此 | **HIGH** | 0 code，1-3 cron 配置 | PA 決定哪些重啟 + operator `crontab -e` | **部分** — 若 Sprint 2 任務依賴 counterfactual / symbol_universe / replay_manifest 證據則阻；單純策略 IMPL 不阻但 evidence 殘缺 |
| **H-3** | edge_estimates.json **path mismatch**：cron 寫 `srv/settings/edge_estimates.json`（live），healthcheck [7] 讀 `/tmp/openclaw/edge_estimates.json`（不存在）→ healthcheck 永久 FAIL 但 estimator 健康 | **HIGH** | 1-2 (healthcheck path) 或 cron 加 symlink | E1 直接 IMPL（healthcheck path 對齊較安全） | 否 — 但 evidence loop 失真，PM 看 healthcheck 會誤判 estimator 死 |
| **M-1** | `/tmp/openclaw/watchdog_status.json` missing — watchdog daemon 跑（PID 2936560）但無 status file；`--status` 從 snapshots fallback | **MED** | 10-30 (engine_watchdog.py writer) | E1 直接 IMPL | 否 — 已 logged P2-WATCHDOG-STATUS-JSON-WRITER |
| **M-2** | h_state pipeline_snapshot `h_states={}, agent_states={}` — Phase 2 h1/h3 producer regression（per healthcheck [20]） | **MED** | unknown (需先 RCA) | PA spec → E1 IMPL | 否 — 但若 Sprint 2 含 H1/H3 dependent 任務則阻 |
| **M-3** | `learning.replay_manifest_registry` 表完全不存在 → healthcheck [48] 永久 FAIL on 不存在的表 | **MED** | 1-3 (healthcheck reclassify 或 spec V### migration) | PA 決定 reclassify or land V###；E1 IMPL | 否 — 觀察性指標，不阻業務 |
| **M-4** | Sub-agent dispatch SOP 漏洞 — E4 / E1 / QA sub-agent 仍可 ssh trade-core 跑 `cargo test --release` 觸 multi-session race；本 sprint 已第 3 次發生 | **MED** | ~30 (prompt template + script guard) | PA spec sub-agent template + 主會話 enforce | 否 — 但 Sprint 2 多 wave 並行高機率第 4 次發生 |
| **L-1** | post-M3 chain integrity 96.77%（<99% target），risk_close:ipc_close_symbol 0% chain attribution | **LOW** | unknown | 觀察 | 否 |
| **L-2** | close_maker_reject_samples FAIL [74] / WARN [70] Wilson NEUTRAL_LOW_SAMPLE 多 stratified weak cells | **LOW** | 0 code — 等樣本累積 | 觀察 | 否 |

**3 阻 deploy 級**（H-1）+ **partial 阻**（H-2）+ **misleading evidence**（H-3）→ 建議 Sprint 2 Day -1 派 1 並行 wave 修 H-1/H-2/H-3，其他項 Sprint 2 內並行或 defer。

---

## 1. 詳細分析

### H-1. FD 200 flock 繼承 leak（**CRITICAL，live blocker confirmed**）

#### Root cause

```
restart_all.sh:535  nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 &
```

`nohup ... &` 沒任何 FD 關閉，**engine 繼承父 shell 全部 open FD**，包括：
- `build_then_restart_atomic.sh:68` `exec 200>"$LOCK_FILE"` 開的 FD 200（flock build window）
- 父 shell 進入 atomic script 後 exec restart_all.sh → engine 從 atomic script 那邊繼承 fd 200

注釋 `build_then_restart_atomic.sh:31` 寫「lock 在 script exit 時由 kernel 自動釋放（exec 200>FILE + flock -n 200）」**與實際行為不符** — engine 是 atomic script 的孫子進程，FD 200 被 engine 持續持有，script exit 不會釋放 lock 因為 lock 還在 kernel inode 上由 engine fd refcount 撐著。

#### Runtime evidence（2026-05-25 02:30 UTC）

```
$ fuser /tmp/openclaw/build_window.lock
/tmp/openclaw/build_window.lock: 374287

$ ls -la /proc/374287/fd/200
l-wx------ ... 200 -> /tmp/openclaw/build_window.lock
```

current engine PID 374287（自 Action 3 OPENCLAW_ALLOW_MAINNET 設置以來），**此刻** 仍持有 build_window.lock 的 FD 200。

#### 影響

- 下次跑 `bash helper_scripts/build_then_restart_atomic.sh` → Phase 1 `flock -n 200` **立即 fail**（已被同 inode 上另一 FD 持有）→ exit 1
- workaround = `kill -TERM 374287` 才釋放（破壞 atomic 語意：unlock-before-restart）
- Sprint 2 deploy（含 W1 BB WS-first + W7-1 + W7-3 已 ready 待 deploy）**全阻**
- 已在本 sprint Action 3 第二輪 atomic re-alignment 中親歷一次（per E1 sub-agent `ae7b207c` carry-over）

#### 修法

**Option A（推薦）**：`restart_all.sh:535` spawn engine 加 FD close
```bash
# 改前：
nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 &

# 改後（推薦）：
nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 0<&- 200<&- &
```

- LOC = 1（加 `0<&- 200<&-`）
- 效果：engine 不繼承 stdin + 不繼承 FD 200 → atomic script exit 時 kernel 真正釋放 lock
- 風險：低；engine 從不讀 stdin（service-mode），原本繼承的 FD 200 也只是治理用

**Option B（保險 belt-and-suspenders）**：再加 `build_then_restart_atomic.sh` 在 spawn 後 explicit `flock -u 200`
```bash
# Phase 5 結束後加：
flock -u 200
```
- 額外 LOC = 1
- 缺點：與 line 31 注釋「lock 在 script exit 時由 kernel 自動釋放」二度 redundant，要更新注釋

**ETA**：~30 min（含 Mac smoke test 用 `bash -n` + Linux ssh dry-run）
**Owner**：E1 直接 IMPL（修法明確，PA spec 不必要）
**阻 Sprint 2**：是；本項是 Day -1 必修

#### Audit checklist 反思（E5 對未來 perf review SOP 補充）

- spawn 子進程的 FD inherit 應視為**默認危險**：所有 `nohup`/`setsid`/`exec` 必 explicit close stdin + 治理用 FD
- 注釋 claim 「kernel 自動釋放」必驗 `fuser` / `lsof` 對齊 inode 持有方
- shell script 內治理 FD（flock / advisory lock）必聲明 child 繼承策略

---

### H-2. 13 OpenClaw cron 集體 disabled（**HIGH，Sprint 2 evidence 半斷**）

#### Root cause

`crontab -l` 顯示 13 個 OpenClaw cron 全標 `# DISABLED_OPENCLAW_20260521`：

| Cron | 用途 | healthcheck 影響 |
|---|---|---|
| `counterfactual_daily_cron.sh` | daily 6am counterfactual replay | [11] FAIL 92.6h |
| `passive_wait_healthcheck_cron.sh` | 6h cron 自跑 healthcheck | 治理盲點：no auto-fire history |
| `edge_label_backfill_cron.sh` | 30min outcome 標 backfill | edge label drift |
| `ref21_symbol_universe_snapshot_cron.sh` | hourly @20 symbol universe snapshot | [53] FAIL 87h |
| `ref21_market_microstructure_recorder.py` | every minute microstructure | observability gap |
| `ml_training_maintenance_cron.sh` | 3am 17 ml retrain | ml 模型 stale |
| `logrotate-openclaw.conf` | hourly logrotate | engine.log 4 day 累積 ~100MB |
| `panel_aggregator_health_cron.sh` | 5min panel aggregator health | [75] 3.61d stale |
| `wave9_replay_no_live_mutation_watch.sh` | hourly invariant | [76] 3.65d stale |
| `replay_key_rotation_check.sh` | daily 9am | [77] 3.73d stale |
| `feature_baseline_writer_cron.sh` | daily 4:41am | [78] 3.91d stale |
| `blocked_symbols_30d_unblock_check_cron.sh` | weekly Sun 4am | [79] heartbeat missing |
| `halt_audit_pg_writer_cron.sh` | every minute halt audit PG writer | halt audit gap |

唯一活著：`12 * * * * edge_estimate_snapshots_cycle_cron.sh`（V059 snapshot 寫入，log 連續每小時跑無中斷）。

#### Git history 對照

2026-05-21 ~ 2026-05-22 git log：
- `1639506f docs(sprint-4-wave-b-m1)`: Singleton Registry SSOT
- `188f244a feat(gates): cost_gate_moderate 加 low-sample 深負 arm`
- `4d4ff99f fix(sprint-4-wave-b-round2)`

**未見「disable cron」commit** — 可能是 operator 手動 `crontab -e` 改動，未 commit 到 repo（crontab 本身不在 git 內）。disable 動機推測：
- 2026-05-21 LG-1 P0 closure（SLA carve-out audit）期間 cron noise 干擾觀察
- OPENCLAW_DATA_DIR=/tmp/openclaw 路徑切換期間統一暫停
- 但 **未在 TODO 或 memory 留復原計劃** — 治理盲點

#### 影響分級

| Cron | 復原必要性 | Sprint 2 阻？ |
|---|---|---|
| `counterfactual_daily_cron` | **HIGH** — Sprint 2 Alpha Tournament 若用 counterfactual evidence 必需 | 阻 |
| `ref21_symbol_universe_snapshot` | **HIGH** — M10 Tier A symbol universe 依賴 | 阻（若 M10 Tier A 真進 Sprint 2）|
| `ml_training_maintenance` | **MED** — 5 training + 5 audit daily（per memory 2026-05-09）；ml 模型 4 day stale 影響 ML-driven decision | 部分阻 |
| `panel_aggregator_health` + `wave9_replay_no_live_mutation_watch` + `replay_key_rotation_check` | **MED** — observability + safety invariant | 觀察 |
| `feature_baseline_writer` | **MED** — 34-dim baseline drift events 不啟動 | 觀察 |
| `passive_wait_healthcheck_cron` | **LOW** — 主會話手動 ssh 跑可替代 | 不阻 |
| `logrotate` | **LOW** — engine.log 累積 ~100MB 仍可承受 | 不阻 |
| `ref21_market_microstructure_recorder` | **LOW** — 1min recorder 高頻 noise | 不阻 |
| `edge_label_backfill` | **MED** — outcome 標 backfill 30min cadence | 部分阻 |
| `halt_audit_pg_writer` | **LOW** — halt audit 副本 channel | 不阻 |
| `blocked_symbols_30d_unblock` | **LOW** — 30d window 不會在 Sprint 2 內 trigger | 不阻 |

#### 修法

**Phase 1（必須）**：PA spec 列出哪些 cron 是 Sprint 2 evidence path
- 然後 operator `crontab -e` 去掉 `# DISABLED_OPENCLAW_20260521` 前綴
- 或 PA 決定哪些 cron 已 deprecated（per `project_ml_training_maintenance_cron_hybrid` memory 確認 ml_training 是 daily 不是 weekly）需審視復原必要性

**Phase 2（治理）**：將 crontab 納入 git
- `helper_scripts/setup_openclaw_cron.sh`（生成期望 crontab 並 diff 當前），讓 disable 動作必經 commit
- 補 ETA：~2 hr (setup script + diff verify)

**ETA Phase 1**：~30 min（operator 動作）；Phase 2：~2 hr（PA + E1）
**Owner**：PA spec 復原清單 → operator 手動 + E1 setup_openclaw_cron.sh IMPL
**阻 Sprint 2**：部分；建議 Day -1 復原 HIGH 級 4 個（counterfactual / symbol_universe / ml_training / edge_label_backfill）

---

### H-3. edge_estimates.json path mismatch（**HIGH，誤導性 evidence**）

#### Root cause

- **edge cron 寫入路徑**：`/home/ncyu/BybitOpenClaw/srv/settings/edge_estimates.json`（2026-05-25 00:29:08 mtime live）
- **healthcheck [7] 讀取路徑**：`/tmp/openclaw/edge_estimates.json`（**不存在**）

cron log（healthy 每小時跑）：
```
[2026-05-25 00:12:01] === edge_estimate_snapshots cycle start ===
[v059] /home/ncyu/BybitOpenClaw/srv/settings/edge_estimates.json: asof=2026-05-24T18:03:53 cells=382
```

healthcheck rerun 結果：
```
FAIL [7] edge_estimates_freshness         edge_estimates.json age 124 min — scheduler 可能掛了
PASS [13] edge_estimator_scheduler_fresh  age=2.1h, cells=118 (via _meta.n_cells=118) — full G1-01 recovery target met
```

[7] 跟 [13] **報告矛盾結論**：[7] FAIL「scheduler 掛了」；[13] PASS「full G1-01 recovery target met」。雙路徑分歧暴露 path mismatch。

#### 影響

- PM / sub-agent 看 [7] FAIL 會誤判 estimator 死 → 浪費 sprint cycles 派 sub-agent debug 健康的 cron
- 本 audit user prompt 列「[7] 117 min scheduler 可能掛了」即為此誤判
- Evidence loop 完整性：healthcheck 是 PM dispatch 的 source of truth；混入虛假 FAIL 是治理 noise

#### 修法

**Option A**：改 healthcheck 讀路徑（最安全）
- `helper_scripts/db/passive_wait_healthcheck/checks_ipc_edge.py:353-444` 把 edge_estimates.json path 改為 `srv/settings/edge_estimates.json`
- LOC = 1-2（path constant 替換）

**Option B**：cron 加 symlink
- `edge_estimate_snapshots_cycle_cron.sh` 結束時加 `ln -sf "$BASE/settings/edge_estimates.json" /tmp/openclaw/edge_estimates.json`
- LOC = 1
- 缺點：兩路徑都需維護；symlink 在 reboot 後 /tmp 重建會掉

**Option C**：刪 [7] check（依靠 [13] scheduler_fresh 替代）
- [13] 已涵蓋 scheduler + cells + age + leader lock + cell 量
- 但 [7] 是 G1-01 audit 歷史遺留 quick win，operator 可能不願刪

**推薦**：Option A — 改 path 對齊 cron 真實寫入位置，is single source of truth。

**ETA**：~30 min（含 grep 所有 healthcheck 參照 + Linux SSH dry-run）
**Owner**：E1 直接 IMPL（修法明確）
**阻 Sprint 2**：否；但建議 Day -1 修以避免 PM 看 healthcheck 浪費判斷力

---

### M-1. `/tmp/openclaw/watchdog_status.json` missing（**MED**）

#### 已 logged

TODO §5 `P2-WATCHDOG-STATUS-JSON-WRITER` 已 entry。watchdog daemon PID 2936560 跑，`engine_watchdog.py --status` 返 JSON from snapshots，但 file 本身不存在。

#### 修法

**Option A**：`engine_watchdog.py` 加 periodic write 到 `$DATA_DIR/watchdog_status.json`
- LOC ~20-30（main loop 每 poll cycle write file）
- 期望 file 內容：`{engine_alive, snapshot_age, last_check_ts, ...}`

**Option B**：移除 healthcheck 對 `watchdog_status.json` 的期望（reclassify 為 deferred）
- LOC ~5（healthcheck check 改 return PASS-deferred）
- 缺點：失去 watchdog 死後最後狀態的 forensic value

**推薦**：Option A — watchdog 是 critical safety component，file 化最後狀態 forensic 有用。

**ETA**：~2-4 hr
**Owner**：E1 直接 IMPL（修法 already specced in TODO entry）
**阻 Sprint 2**：否；defer 到 Sprint 2 內並行

---

### M-2. h_state h1/h3 producer regression（**MED，silent**）

#### Runtime evidence

```
$ cat /tmp/openclaw/pipeline_snapshot_demo.json | python3 -c "..."
h_states: []
agent_states keys count: 0
```

healthcheck [20]：
```
WARN [20] h_state_gateway_freshness       stub regressed from Phase 2 shape (version=0, h_states_keys=[], expected ⊇ {'h1','h3'}, missing=['h1', 'h3'], agent_states_keys=0) — H1/H3 producer regression? check Phase 2 wiring (commits 9120948 + f2ed286)
```

engine log 顯示大量 `invalidate_h_state` IPC dispatch（每秒多次）— consumer 在跑，但 **producer 沒寫**進 snapshot。

#### 影響

- 若 Sprint 2 含「H1/H3-dependent feature/strategy」則直接失效（如某些 cross-asset signal、execution micro lane）
- 若不含則 silent observability gap，不阻

#### 修法

- 需 PA 先 RCA：(a) producer thread 死了？(b) snapshot write path 漏 h_states？(c) ipc invalidate 衝突 producer?
- 後 E1 IMPL fix

**ETA**：RCA 1-2 hr + IMPL unknown（取決於 root cause）
**Owner**：PA spec + E1 IMPL
**阻 Sprint 2**：否；除非 PM 確認 Sprint 2 含 H1/H3-dep 任務

---

### M-3. `learning.replay_manifest_registry` 表不存在（**MED**）

#### Runtime evidence

```sql
SELECT count(*) FROM learning.replay_manifest_registry;
ERROR:  relation "learning.replay_manifest_registry" does not exist
```

但 healthcheck [48] 期望此表存在並查 `rows_24h` / `rows_7d`：
```
FAIL [48] replay_manifest_registry_growth — total=23 rows_7d=0 rows_24h=0 last_age=321.8h — runner stalled
```

healthcheck 顯示 `total=23` 是 SQL fail 後的某 default? 或 healthcheck script 自有 placeholder。需 grep healthcheck code 確認。

#### 影響

- healthcheck [48] 永久 FAIL — 治理 noise（同 H-3 性質）
- replay runner stall 不一定真死 — 因為表不存在，無法判斷

#### 修法

**Option A**：land 真實 V### migration 建表
- LOC ~30-50（CREATE TABLE + 索引 + Guard A）
- 需 PA spec table schema

**Option B**：healthcheck [48] reclassify deferred-no-table
- LOC ~5
- 失去 replay runner 觀察性

**推薦**：先 Option B 不阻；後續 PA 視 replay 整體治理決定是否真建表。

**ETA**：Option B ~30 min
**Owner**：PA 決定 + E1 IMPL
**阻 Sprint 2**：否

---

### M-4. Sub-agent dispatch SOP hygiene（**MED，重發概率高**）

#### 已 logged

TODO §5 `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC` 已 entry。E4 / E1 / QA sub-agent 仍可獨立決定跑 `cargo test --release` 在 Linux 上，本 sprint 已第 3 次觸 race（Phase 1a 前 / Phase 1a 後 / Action 3 後）。

#### 影響

- Sprint 2 多 wave 並行（per memory 2026-05-10 D+0 readiness 9 wave）→ 第 4 次發生概率高
- 每次發生 = engine PID binary inode 漂移 = atomic deploy 治理破功

#### 修法

**Phase 1**：PA spec `docs/agents/sub-agent-hygiene-sop.md`
- 規定 sub-agent ssh trade-core 不可獨立跑 cargo test
- 必經 `build_then_restart_atomic.sh` 或標 carry-over

**Phase 2**：主會話 sub-agent dispatch prompt template 加 hygiene 警示
- E4 / E1 / QA 各 prompt template 加 § cargo race avoidance

**Phase 3（防呆）**：`cargo` wrapper script 在 trade-core
- `~/bin/cargo` 檢查 engine PID + atomic lock state → 不安全時拒絕 build

**ETA**：Phase 1+2 ~1 hr；Phase 3 ~2 hr
**Owner**：PA spec + 主會話 prompt template update
**阻 Sprint 2**：否；但建議 Day -1 完成 Phase 1+2

---

### L-1. post-M3 chain integrity 96.77%（**LOW**）

healthcheck [65]：
```
WARN [65] chain_integrity_post_audit_4b_m3 [65] post-M3 chain ratio = 96.77% (n=650, in_df=629)
per_strategy_drift: ma_crossover=107/115 (93.0%); risk_close:ipc_close_symbol=0/12 (0.0%)
```

`risk_close:ipc_close_symbol=0/12` 是 100% chain attribution miss — silent class。但 ma_crossover 93% 接近 95% 閾值，是 evidence completeness 微弱問題。

**修法**：observability 任務，不在本 audit scope；建議 E2 / FA cross-check chain wiring。

---

### L-2. close_maker_reject_samples 樣本不足（**LOW**）

healthcheck [74]：
```
FAIL [74] close_maker_reject_samples — demo: attempts=44, postonly_reject_samples=4, max_pending_samples=0, verdict=FAIL
```

樣本不足是 demo flow 自然狀態，不是 hygiene bug；等樣本累積即可。建議 PM 在 Sprint 2 內觀察樣本 7d trend。

---

## 2. 跨 issue 共通 root cause 模式

### Pattern A：2026-05-21 集體 disable 事件

**現象**：13 cron 同日同 prefix（`DISABLED_OPENCLAW_20260521`）disable + cron heartbeat 4 file 全停在 5-21
**推斷**：operator 手動 `crontab -e` 一次性 disable（可能是 LG-1 P0 closure 觀察期間消 noise）
**治理盲點**：
- 未 commit 到 git（crontab 不在版控）
- 未在 TODO / memory 留復原計劃
- 4 day 後（5-25）才被 PM healthcheck 跑出來發現

**根治建議**：crontab 納入 git via `helper_scripts/setup_openclaw_cron.sh`（H-2 Phase 2）

### Pattern B：FD inheritance 治理盲點

**現象**：H-1 FD 200 leak + 過去 sprint 多次 atomic restart 觸 cargo race
**根因**：shell script 內 spawn 子進程默認 inherit 全 FD；治理 FD（flock / pipe lock）沒 explicit close
**治理建議**：所有 `nohup`/`exec`/`&` spawn 必 audit FD inherit；本項已暴露在 H-1 修法內。可加入 E5 sign-off SOP checklist。

### Pattern C：path / schema 期望與實際偏離（治理 noise）

**現象**：H-3（edge_estimates path mismatch）+ M-3（replay_manifest_registry 表不存在）共同性質
**根因**：healthcheck 規格與 cron / migration / writer 實際路徑分歧後未對齊
**治理建議**：healthcheck check 在 land 前必驗 SQL/path 在 Linux PG / FS 上真實存在；治理新加 healthcheck SOP「先 ssh trade-core 驗 source-of-truth path / table，再 land check」

### Pattern D：Sub-agent 治理 SOP 漏洞

**現象**：M-4 第 3 次 cargo race + Sprint 2 多 wave 並行高機率第 4 次
**根因**：sub-agent prompt template 沒 enforce hygiene；sub-agent 在 ssh 環境內無圍欄
**治理建議**：PA spec sub-agent hygiene SOP + 主會話 prompt template 加警示

---

## 3. 優先級 ranked + Sprint 2 派發建議

### Day -1（必修，阻 Sprint 2 派發）

1. **H-1 FD 200 leak fix**（E1 ~30 min；修 restart_all.sh:535 加 `0<&- 200<&-`）— 阻所有 deploy
2. **H-3 edge_estimates path mismatch**（E1 ~30 min；修 healthcheck path）— 修後 PM dispatch evidence loop 乾淨
3. **H-2 Phase 1 cron 復原**（operator 動作 ~30 min；PA 先 spec 4 個 HIGH 級復原清單：counterfactual / symbol_universe / ml_training / edge_label_backfill）

**Day -1 總投資**：E1 ~1 hr + PA ~30 min + operator ~30 min = 2 hr 並行 → Sprint 2 Day 0 deploy 路徑乾淨

### Sprint 2 內並行（不阻派發）

4. **M-1 watchdog_status.json writer**（E1 ~2-4 hr；TODO 已 entry）
5. **M-4 sub-agent hygiene SOP Phase 1+2**（PA + 主會話 ~1 hr）— 必在 Sprint 2 Day 0 派任何 sub-agent 前 land prompt template
6. **H-2 Phase 2 setup_openclaw_cron.sh**（PA + E1 ~2 hr）— 防再發
7. **M-3 healthcheck [48] reclassify**（PA + E1 ~30 min）— 治理 noise

### Defer / observe

8. **M-2 h_state h1/h3 RCA**（除非 Sprint 2 含 H1/H3-dep 任務）
9. **L-1 chain integrity 96.77%** observe，PA 評估是否升級
10. **L-2 close_maker_reject_samples** 等樣本累積

---

## 4. Sprint 2 派發 readiness 評估

**結論**：建議 PM 在派 Sprint 2 前 **Day -1 修 3 項（H-1/H-2 Phase 1/H-3）**，否則：
- Sprint 2 第一個 sub-agent 跑 atomic restart 會被 self-block（H-1 真實阻 deploy）
- Sprint 2 sub-agent 看到 healthcheck 多項 FAIL 會誤判系統死 → 浪費 dispatch budget 派 debug 健康組件（H-3 + H-2 disabled crons）
- Sprint 2 Alpha Tournament 若需 counterfactual / symbol_universe evidence → 4 day stale 不可信（H-2 cron disabled）

**Sprint 2 Day 0 派發 OK 條件**：
- [ ] H-1 commit + atomic restart 一次驗 lock 真釋放（`fuser /tmp/openclaw/build_window.lock` empty post-script-exit）
- [ ] H-3 commit + healthcheck rerun [7] PASS
- [ ] H-2 Phase 1 復原 4 HIGH cron + 1h 內各觸發一次寫入 verify
- [ ] M-4 Phase 1+2 prompt template land

**Day -1 並行可派**：4 sub-agent
- 1 E1：H-1 + H-3 IMPL（兩個都是 1-2 LOC，可同 sub-agent）
- 1 PA：H-2 cron 復原 spec + M-4 sub-agent hygiene SOP spec
- 1 operator action：H-2 crontab 復原 + M-4 prompt template update
- 1 E1：M-1 watchdog_status.json IMPL（可入 Sprint 2 day 0 並行）

---

## 5. 附錄：Audit 過程證據

### A. Runtime probe sequence

```
ssh trade-core
  ↓ proc-exe SHA check → MATCH (PM report stale, drift 已 resolved)
  ↓ FD 200 inheritance check → LEAK confirmed (374287 holds /tmp/openclaw/build_window.lock)
  ↓ watchdog status → daemon PID 2936560 running, /tmp/openclaw/watchdog_status.json missing
  ↓ healthcheck full run → 7 FAIL + 6 WARN + 多 PASS
  ↓ crontab -l → 13 OpenClaw cron 全 DISABLED_OPENCLAW_20260521
  ↓ edge cron log → healthy hourly writes to srv/settings/ (not /tmp/openclaw/)
  ↓ pipeline_snapshot demo → h_states=[], agent_states={}
  ↓ replay_manifest_registry → table does not exist
  ↓ fuser /tmp/openclaw/build_window.lock → 374287 confirmed
```

### B. 與 user prompt 對照修正

| User prompt 列 | Audit verify 結果 |
|---|---|
| proc-exe drift / SHA mismatch | ✅ **已 resolved**（per Action 3 E1 sub-agent ae7b207c re-alignment；current SHA `b005bb00...` match）|
| /tmp/openclaw/watchdog_status.json missing | ✅ confirmed |
| FD 200 inherit corner case | ✅ confirmed **此刻 active**（374287 持鎖） |
| sub-agent SOP cargo race | ✅ confirmed（per TODO entry，本 sprint 已 3 次發生）|
| FAIL [7] edge_estimates 117min | ✅ confirmed 124 min — 但 root cause **不是 scheduler 掛**，是 **path mismatch**（srv/settings/ vs /tmp/openclaw/） |
| FAIL [11] counterfactual 92.4h | ✅ confirmed 92.6h — root cause = cron disabled |
| FAIL [16] strategist_cycle wedged | ❌ healthcheck **已自修為 PASS**（Demo unbound by design） |
| FAIL [48] replay_manifest_registry | ✅ confirmed — **表完全不存在**（M-3） |
| FAIL [53] symbol_universe_recorder | ✅ confirmed — cron disabled |
| FAIL [56] live_pipeline_active auth missing | ✅ confirmed — **expected**（OP-1 operator blocked，非 hygiene bug） |
| FAIL [74] close_maker_reject_samples | ✅ confirmed — 樣本不足，**等 Sprint 2 累積**（L-2） |
| WARN [70] close_maker_fill_rate | ✅ confirmed — Wilson low sample（L-2） |
| WARN [75-79] cron heartbeat stale | ✅ confirmed — root cause = cron disabled |

### C. 額外發現（user prompt 未列）

- WARN [20] h_state_gateway_freshness **h1/h3 producer regression**（M-2）
- WARN [65] post-M3 chain integrity 96.77% < 99%（L-1）
- bybit_endpoint file = "demo" 在 live slot 中（已 logged P1-OP1，等 OP-1 觸發）

---

## 6. E5 memory append（追加教訓）

新教訓（將追加到 E5 memory）：
1. **FD inherit 治理盲點是高危反模式**：shell script spawn 子進程默認繼承全 FD；治理用 flock / pipe lock 必 explicit close otherwise child 持鎖代替 script
2. **Crontab 不在 git** 是治理 silent class；operator 手改 → 4 day 後才被 healthcheck 跑出來。建議：crontab 必走 setup script + git diff verify
3. **healthcheck path / schema 期望需與 source-of-truth runtime 對齊**：land 前必 ssh trade-core 驗 path / table；否則永久 FAIL 製造治理 noise
4. **Sub-agent ssh trade-core 環境無圍欄**：cargo race / FD inherit / 治理 SOP 都需 prompt template 級 enforcement，不能依賴 sub-agent self-discipline
5. **Healthcheck 內雙路徑分歧自我矛盾**（H-3 case [7] FAIL vs [13] PASS）是 hygiene gap detector — 設計 healthcheck 時應避免單一現象多 check 分歧

---

**Report END**

E5 OPTIMIZATION REPORT: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-25--runtime_hygiene_audit_pre_sprint_2.md`
