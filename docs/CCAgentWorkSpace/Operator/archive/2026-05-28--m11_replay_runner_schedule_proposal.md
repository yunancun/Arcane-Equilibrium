---
title: M11 `replay_runner` 排程提案 — Cadence Option Matrix + 推薦
date: 2026-05-28
author: PA
ticket: P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL（per TODO v77 §1.7 / operator decision [4]=b）
scope: 排程治理建議；不寫 runner 代碼；不自啟 cron；待 operator 拍板
status: PROPOSAL-DRAFT pending operator decision
parent specs:
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md
  - srv/docs/adr/0044-m7-decay-enforced-single-authority.md
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md
  - srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md
  - srv/docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md
  - srv/docs/adr/0007-mac-dev-linux-runtime-split.md（隱含；cron Linux-only）
hard boundaries verified:
  - 不觸 live_execution_allowed / OPENCLAW_ALLOW_MAINNET / authorization.json / live_reserved
  - replay_runner 為 ReplayProfile::Isolated（V3 §6.2 三層 fail-closed guard 強制）
  - 不寫 trading state / 不繞 Decision Lease / 不發 Bybit order intent
runtime evidence captured: 2026-05-28 ssh trade-core empirical PG reflection
---

# M11 `replay_runner` 排程提案

## §0 TL;DR

| 推薦 | 一句話 |
|---|---|
| **Daily 04:00 UTC (Stage A: smoke heartbeat mode)** | 解 `[48]` healthcheck FAIL + 為 Sprint 2 Wave 3 stage0_ready 累積 evidence，PG IO 可忽略（~5 MB/30d），不阻 ADR-0038 Sprint 3 IMPL 後升級到 full nightly cohort |

- **拒絕 hourly / 6h**：ADR-0038 line 244 明文 reject「Hourly replay 替代 nightly」；6h 同理（PG IO + fixture pull + binary spawn 成本不對等收益）
- **拒絕 on-demand-only**：違反 ADR-0038 Decision 5「continuous nightly hygiene」設計；`[48]` 永久 FAIL；Sprint 2 Wave 3 出口 6 Reject gate 之一無法收齊
- **`[48]` healthcheck 變 PASS**：daily cadence land 後 **次日 24h 內** PASS（rows_24h ≥ 1 即不 WARN；rows_7d ≥ 1 即 PASS）

---

## §1 排程問題分裂為兩層 — Stage A vs Stage B

### §1.1 為什麼必須分層

當前 runtime 狀態（2026-05-28 ssh trade-core empirical）：

```
replay.experiments: 23 rows / last 2026-05-11 / 17d stale
replay.run_state:   23 rows / 17 completed + 6 failed + 0 zombie
replay.report_artifacts: 17 rows / 62 KB total
replay.simulated_fills:  46 rows
table sizes:        experiments 352 kB / run_state 96 kB / artifacts 80 kB / fills 600 kB
per-run footprint:  ~50 kB（含 jsonb 7527 B avg + indexes + fills × 2/run avg）
```

當前 `replay_runner` binary 是 **single-manifest execution model**（per `replay_routes.py:355` POST `/experiments/register` → `/run` flow + `replay_runner.rs:285-289` `cli::parse_cli_args` → `load_and_verify_manifest`）：

- **每次 invoke 只跑 1 個 manifest**（pre-registered experiment_id）
- **per-run wall clock**: ~30s-2min（synthetic_btcusdt.json fixture 5-symbol smoke）
- **per-run PG write**: 1 row experiments + 1 row run_state + 1+ row artifacts + N row simulated_fills

ADR-0038 + M11 spec §2.1 設計的「nightly continuous」是 **full cohort wrapper**（5 strategy × N symbol = 125+ replay run 在 4h budget 內）— **此 wrapper 不存在**，per `docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md` §10.3「Phase A Sprint 3 W15-18 IMPL pending」。

**結論**：排程提案必須分 Stage A（當前 binary 的 smoke heartbeat）vs Stage B（Sprint 3 Phase A land 後的 full nightly）。本 proposal 主推 Stage A；Stage B 給治理路徑但不在本決策範圍。

### §1.2 Stage A vs Stage B 對齊

| 維度 | Stage A（當前可行，本提案範圍） | Stage B（Sprint 3 Phase A land 後） |
|---|---|---|
| 觸發物 | 單一 fixture manifest（synthetic_btcusdt.json）+ Operator-signed `replay:write` actor 或同等 service principal | nightly wrapper script（`m11_nightly_replay.sh` Phase A IMPL 待寫）iterate 5 strategy × N symbol |
| 每次 runs/night | 1 | ~125（5 strategy × 25 symbol） |
| Wall clock | < 2 min | < 4h（per M11 spec §2.2 budget） |
| PG row/night | ~1 experiments + 1 run_state + 1-2 artifacts + 1-2 fills ≈ **~50 kB/night** | ~125 × 50 kB ≈ **~6.3 MB/night**（加 V107 divergence row）|
| 出生條件 | 此 proposal 拍板 + cron install | ADR-0038 + M11 spec Sprint 3 Phase A IMPL complete + V107 land |
| 治理權重 | governance call（agent 不自啟）+ Service principal 認證；屬 hygiene；不直接驅動 P0-EDGE-1 | ADR-0038 自動 hygiene + M7 5th signal + M3 HEALTH_WARN escalate + M11 → M7 14d persistent CRITICAL → strong candidate；驅動 Sprint 3+ 全鏈 |
| 必須 Service principal？ | YES — `/experiments/register` 走 `_replay_limiter.limit("10/minute")` 並 `_require_replay_write(actor)`；cron 必有合法非 operator-interactive 身份 | YES — 同前 + Sprint 3 IMPL 設計 |

---

## §2 Cadence 選項矩陣（Stage A 範圍）

評估維度（per ticket 要求 + ADR-0038 + V58 PA verdict）：

1. PG IO 持續成本（INSERT/sec + disk write）
2. M11 evidence 累積速率（estimated rows/day）
3. `replay.experiments` 增長預估 30d / 90d（rows + bytes）
4. PG storage cost（含 4 表 + index + WAL）
5. 與 M7 decay 互動 cadence（per ADR-0044 Decision 2 M11 as 5th signal + 14d window）
6. 對 Sprint 2 Wave 3 stage0_ready 影響（D+18~D+21 evidence 累積）

### §2.1 Option A — On-Demand（operator 手動 / sub-agent dispatch only）

| 維度 | 預估 |
|---|---|
| PG IO/day | ~0（除非 operator/agent 觸發）|
| Evidence 累積 | 0 rows/day baseline；spike-on-need pattern |
| 30d rows | ~5-10（基於 17d 歷史 23 rows 推算 0.7-1.4 row/day operator pattern；考慮 backlog 後上限）|
| 30d 增量 | ~50-250 kB |
| 90d 增量 | ~150-750 kB |
| 與 M7 互動 | **缺失** — M11 設計為 5th decay signal（per ADR-0044 line 74 「`daily_divergence_aggregate_30d`」），on-demand 不滿足「daily」aggregate window；M7 4 主 signal 仍可獨立 trigger（per ADR-0044 line 174 mitigation）但 M11 signal 永遠 stale → Sprint 3+ Phase B M11 ↔ M7 hookup 無 data feed |
| Sprint 2 Wave 3 影響 | **❌ FAIL gate** — stage0_ready 6 Reject gate 之一「M11 runner cron」（per TODO §1.7 P1 entry line 184）明示「需 M11 runner cron」；on-demand 不算 cron schedule |
| `[48]` healthcheck | 永久 FAIL（除非 7d 內 operator/agent 手觸 ≥ 1 次） |
| 風險 | 嚴重 ops 心智負擔 — operator 每 7d 必跑 ≥ 1 次否則 FAIL 灰塵堆積 |
| 適用情境 | 不適用為 baseline；可作 Stage A → Stage B 過渡前最後手段 |

**Verdict**：REJECT — 與 ADR-0038 持續 hygiene 設計矛盾 + Sprint 2 Wave 3 出口阻塞。

### §2.2 Option B — Hourly（每小時 1 run）

| 維度 | 預估 |
|---|---|
| PG IO/day | 24 × ~50 kB = ~1.2 MB/day write |
| Evidence 累積 | 24 rows/day（experiments）+ 24 × 1-2 artifacts + 24 × 1-2 fills |
| 30d rows | ~720 experiments / ~1080 fills / ~720 artifacts |
| 30d 增量 | ~36 MB（含 4 表 + index + WAL ~2× → ~72 MB 實際）|
| 90d 增量 | ~108 MB（實際 ~216 MB 含 WAL）|
| 與 M7 互動 | hourly granularity 超過 ADR-0044 M11 signal 「daily aggregate」設計；signal 過於精細 → 30d window 內 720 個 datapoint 增加噪音不增加 power |
| Sprint 2 Wave 3 影響 | ✅ PASS gate（過量滿足）|
| `[48]` healthcheck | PASS（rows_24h ≥ 1 = ≥ 23 過量）|
| 風險 | (a) **ADR-0038 line 244 明文 REJECT** —「Hourly replay 替代 nightly (a) 4h budget × 24 = 96h/d 不可能 (b) IPC 通量 + L2 cost 不合理 (c) hourly granularity 對 day-level strategy decay 不必要」；(b) PG shared_buffers 4-8GB 競爭風險（per `project_hardware_constraints`）；(c) advisory lock 撞 panel_aggregator/wave9 等既有 hourly cron |
| 適用情境 | 不適用 |

**Verdict**：REJECT — ADR-0038 明文 REJECT；governance breach。

### §2.3 Option C — 6h（4 run/day）

| 維度 | 預估 |
|---|---|
| PG IO/day | 4 × ~50 kB = ~200 kB/day write |
| Evidence 累積 | 4 rows/day |
| 30d rows | ~120 experiments / ~180 fills / ~120 artifacts |
| 30d 增量 | ~6 MB（實際 ~12 MB 含 WAL）|
| 90d 增量 | ~18 MB（實際 ~36 MB）|
| 與 M7 互動 | 6h cadence 仍超 daily aggregate；M7 30d window 內 120 datapoint 不增加 power |
| Sprint 2 Wave 3 影響 | ✅ PASS gate（充分滿足）|
| `[48]` healthcheck | PASS |
| 風險 | (a) 不違反 ADR-0038 line 244 hourly REJECT 字面 — 但延伸精神不對齊（M11 為 daily hygiene 設計）；(b) 4× daily 沒帶來 4× evidence value — M11 design `daily_divergence_aggregate_30d` 是 1-day grain；(c) cron 4 個 entry 增加維運面 |
| 適用情境 | 過度設計；不推 |

**Verdict**：REJECT（弱）— 對齊 ADR-0038 spirit；6h 對 1-day grain signal 是過度頻繁。

### §2.4 Option D — Daily（推薦 / 04:00 UTC）★ 主推

| 維度 | 預估 |
|---|---|
| PG IO/day | 1 × ~50 kB = ~50 kB/day write |
| Evidence 累積 | 1 row/day（experiments）+ 1-2 artifacts + 1-2 fills |
| 30d rows | ~30 experiments / ~45 fills / ~30 artifacts |
| 30d 增量 | ~1.5 MB（實際 ~3 MB 含 WAL）|
| 90d 增量 | ~4.5 MB（實際 ~9 MB） |
| 與 M7 互動 | **完美對齊** — ADR-0044 Decision 2 M11 「daily_divergence_aggregate_30d」per design；daily cadence = M7 30d signal window 內 30 個 datapoint；Stage B IMPL 後直接接 M11 → M7 ingest queue |
| Sprint 2 Wave 3 影響 | ✅ PASS gate；D+18~D+21 期間累積 ~18-21 row 充分 evidence Sprint 2 Wave 3 stage0_ready 出口收齊 6 Reject gate 之 M11 runner cron 項 |
| `[48]` healthcheck | **PASS 次日內**（per `checks_replay_maintenance.py:415` 規則：rows_7d ≥ 1 PASS；rows_24h ≥ 1 不 WARN）|
| 風險 | (a) **single-fixture rollover** — 當前 Stage A 只跑 1 個 synthetic_btcusdt.json，per-day 信號弱（vs Stage B 125 run/day）；mitigation = Stage A 是 hygiene baseline，evidence value 在「runner alive」非「strategy alpha drift」；(b) cron entry +1 維運（極小成本）|
| 推薦時段 | **04:00 UTC** — 避開 03:00 pg_dump（30 min 視窗）+ 03:17 ml_training_maintenance（per cron table）+ 04:41 feature_baseline_writer；04:00-04:30 視窗無撞 |
| 適用情境 | **本 proposal 主推** |

**Verdict**：APPROVE — Stage A 最佳 cadence；對齊 ADR-0038 nightly hygiene + ADR-0044 daily aggregate；最低 PG cost；解 `[48]` + Sprint 2 Wave 3 出口；Stage B IMPL 後可無痛升級。

### §2.5 矩陣總結

| Option | PG IO/day | 30d rows | 30d MB | 90d MB | M7 對齊 | Sprint 2 Wave 3 | `[48]` healthcheck | ADR-0038 合規 | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| A. On-demand | ~0 | ~5-10 | < 0.25 | < 0.75 | ❌ | ❌ FAIL | 永久 FAIL | ❌ 違反 continuous hygiene | REJECT |
| B. Hourly | ~1.2 MB | ~720 | ~36 | ~108 | ❌ noise | ✅ | PASS | ❌ line 244 明文 REJECT | REJECT |
| C. 6h | ~200 kB | ~120 | ~6 | ~18 | ⚠️ over | ✅ | PASS | ⚠️ spirit 不對齊 | REJECT（弱）|
| **D. Daily 04:00 UTC** | **~50 kB** | **~30** | **~1.5** | **~4.5** | **✅ ADR-0044 對齊** | **✅** | **✅ 次日 PASS** | **✅** | **APPROVE ★** |

PG IO scale parity check（trading_ai DB 4-8GB shared_buffers）：
- Option D daily write 50 kB ≪ panel_aggregator_health_cron（每 5 min 跑）/ halt_audit_pg_writer（每 1 min）write 量
- 30d 累積 1.5 MB 對 ~50+ GB hot data 是 0.003% 級增長；忽略不計

---

## §3 推薦 cadence + 拍板理由

### §3.1 推薦

**Daily 04:00 UTC（單一 synthetic_btcusdt.json fixture；Service principal 認證；advisory-lock guard 沿用 `/run` 既有 P2b PG path）**

### §3.2 為什麼

1. **完整解決 4 個顯性問題**：
   - `[48]` healthcheck FAIL → 次日 PASS（per `checks_replay_maintenance.py` 7d ≥ 1 rule）
   - Sprint 2 Wave 3 stage0_ready 出口 6 Reject gate 之「M11 runner cron」項 GREEN（per TODO §1.7 P1 entry line 184）
   - `replay_runner` binary alive proof — 證明 Wave 3 P2b-S7/S8/S9 三層 fail-closed guard chain 在 production 持續可走（per replay_runner.rs:225-276）
   - ADR-0044 Decision 2 M11 as 5th decay signal 「daily aggregate」對齊（per ADR-0044 line 74）

2. **零治理風險**：
   - replay_runner 在 ReplayProfile::Isolated 下強制（V3 §6.2 三層 guard）；不可觸 Decision Lease / IPC / 訂單 / live config（per replay_runner.rs:31-43 forbidden dep list）
   - 不繞 live_execution_allowed / OPENCLAW_ALLOW_MAINNET / authorization.json / live_reserved（CLAUDE.md §四 五項 gate 均不觸）
   - Cron run-as 是 Service principal 加 `replay:write` permission，**非 operator-interactive**；audit chain 走 `_emit_audit_stub event_type=replay_run_started`（per replay_routes.py:421）

3. **PG cost 邊際**：30d 1.5 MB / 90d 4.5 MB；可忽略不計（對齊 §2.4 risk note）

4. **Stage B 無痛升級**：當 ADR-0038 + M11 spec Sprint 3 Phase A IMPL land（per M11 spec §10.1 60-80 hr），daily cron 升級為 nightly cohort wrapper；cron entry 結構保持，差異只在 wrapper script 內 iterate；本 proposal cron pattern 設計直接支持

5. **ADR-0038 line 244 明文 REJECT 排除 hourly**；Option B 自動出局

6. **6h cadence over-engineered**：ADR-0044 line 74 設計「daily aggregate」是 day-grain；6h 4× 不帶 4× value

### §3.3 拍板邊界（給 operator 看的 trade-off）

| 選 daily 失去的 | 補償 |
|---|---|
| 不能 sub-day 級即時偵測 runner death | watchdog 已監 engine alive（per TODO §0 runtime）；replay_runner 是 batch job 非 always-on |
| 不在 hourly window 累積 Stage B 過渡前的高頻 sample | 對齊 ADR-0044 day-grain 設計；Stage B IMPL 後自然 5 strategy × N symbol = 125/night 高頻 |
| Sprint 2 Wave 3 D+18 前累積 ~18 row vs hourly ~432 row 少 | M11 「runner cron alive」evidence value 在 ≥ 5 row 即充分；不缺 datapoint |

| 選非 daily 失去的 | |
|---|---|
| 選 on-demand → 永久 healthcheck FAIL + Sprint 2 Wave 3 出口阻塞 |
| 選 hourly → 違反 ADR-0038 governance + PG IO 過度 |
| 選 6h → 對齊 spirit 弱 + ops 維運面增加 4× 但 value 持平 |

---

## §4 Cron 寫入範本（per `install_pg_dump_cron.sh` + `replay_key_rotation_check.sh` 既有 pattern）

### §4.1 設計原則

對齊 4 個既有 cron pattern 慣例（per `helper_scripts/cron/install_pg_dump_cron.sh:25-32` + `replay_key_rotation_check.sh:91-97`）：

1. **跨平台守門**：`uname -s` Linux only；Mac dev refuse exit 2（per CLAUDE.md §六 Mac engine not running expected）
2. **idempotent guard**：existing cron entry detected → refuse install（force operator explicit remove）
3. **env value validation**：reject 含 cron 特殊字 `%` / space / control / quote / backslash / `$` / backtick（per `install_pg_dump_cron.sh:75-94` MED-3 防 cron parsing corruption）
4. **DRY-RUN default**：除非 `OPENCLAW_M11_REPLAY_CRON_APPLY=1` 否則只 print 不寫 crontab
5. **path validation**：`$WRAPPER` 必 executable；`replay_runner` binary 必 release path（`rust/target/release/replay_runner` per `route_helpers.resolve_replay_runner_bin()` priority chain）
6. **避撞時段**：04:00 UTC 避開 03:00 pg_dump / 03:17 ml_training / 04:41 feature_baseline_writer / 06:00 counterfactual_daily_cron（per current `crontab -l` empirical 2026-05-28）
7. **heartbeat sentinel**：sibling cron 寫 `${OPENCLAW_DATA_DIR}/cron_heartbeat/m11_replay_runner_smoke.last_fire`（per `replay_key_rotation_check.sh:91-97` 「P1-CRON-INSTALL-WAVE-1」pattern；給未來 `[??]` cron heartbeat healthcheck）

### §4.2 Wrapper script signature（不 IMPL；只描述 contract）

待 IMPL 檔案：`helper_scripts/cron/m11_replay_runner_smoke_cron.sh`

```
# Contract（spec; not code）：
#   1. Linux-only platform gate
#   2. Resolve replay_runner binary via route_helpers priority chain
#      (rust/target/release/replay_runner > debug > workspace alt)
#   3. Service principal authentication（via _replay_rate_limit_key actor_id;
#      see replay_routes.py:351 _require_replay_write）
#   4. POST /api/v1/replay/experiments/register with synthetic fixture manifest
#      (in-tree synthetic_btcusdt.json per restart_all.sh:672)
#   5. POST /api/v1/replay/run with returned experiment_id
#   6. Poll /api/v1/replay/run/{run_id}/status until status in (completed/failed/cancelled)
#      with timeout = 5 min (single-fixture smoke << 4h Stage B budget)
#   7. heartbeat touch ${OPENCLAW_DATA_DIR}/cron_heartbeat/m11_replay_runner_smoke.last_fire
#   8. log to ${OPENCLAW_DATA_DIR}/logs/m11_replay_runner_smoke.cron.log
#   9. exit 0 on completed / exit 1 on failed/timeout
#  10. governance_audit_log INSERT event_type='m11_replay_smoke_completed'
#      OR 'm11_replay_smoke_failed' with payload {run_id, exit_code, wall_clock_seconds}
```

### §4.3 Cron entry 範本（給 install script 寫）

```
# 04:00 UTC daily — M11 replay_runner Stage A smoke heartbeat
# 04:00 UTC 每日 — M11 replay_runner Stage A 煙霧心跳
0 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/m11_replay_runner_smoke_cron.sh >> /tmp/openclaw/logs/m11_replay_runner_smoke_cron.cron.log 2>&1
```

### §4.4 Install script 範本（per `install_pg_dump_cron.sh` 慣例）

待 IMPL 檔案：`helper_scripts/cron/install_m11_replay_runner_smoke_cron.sh`

關鍵分歧 vs pg_dump install：

| 行為 | install_pg_dump_cron.sh | install_m11_replay_runner_smoke_cron.sh |
|---|---|---|
| guard regex | `(pg_dump\|trading_ai_pg_dump_cron\.sh)` | `m11_replay_runner_smoke_cron` |
| WRAPPER 路徑 | `trading_ai_pg_dump_cron.sh` | `m11_replay_runner_smoke_cron.sh` |
| 預期 schedule | `0 ${HOUR} * * *` env-configurable | `0 4 * * *` fixed（4 UTC 避撞）|
| audit event_type | `pg_dump_completed/_failed` | `m11_replay_smoke_completed/_failed`（**注意** V035 enum 可能不含；先用 `audit_write_failed` piggyback per `replay_key_rotation_check.sh:243-247` MED-1 pattern，後續走 V### enum 擴 ticket）|
| pre-flight | `pg_dump` binary in PATH + secrets env file | replay_runner binary release path in candidate chain（per RUNNER_BINARY_CANDIDATE_PATHS）+ secrets env file + Service principal token 存在 |
| DRY-RUN env | `OPENCLAW_BACKUP_CRON_APPLY=1` | `OPENCLAW_M11_REPLAY_CRON_APPLY=1` |

`install_*.sh` contract 由 E1 IMPL 時對齊 `install_pg_dump_cron.sh` 行 75-128 模板，差異僅在上表 6 維度；本 proposal 不直接寫腳本。

### §4.5 Service principal 認證設計

per `replay_routes.py:355 _require_replay_write(actor)` + `replay_routes.py:349 @_replay_limiter.limit("10/minute", key_func=_replay_rate_limit_key)`：

- cron 不能 reuse operator interactive session token（per CLAUDE.md hard boundary：signed live authorization 不可手寫）
- 需新 Service principal 角色（e.g., `m11_replay_smoke_principal`）with `replay:write` permission only；不可 `live:write`
- credentials 走 secrets vault（per `OPENCLAW_SECRETS_ROOT/environment_files/`）
- E3 sign-off 必要；本 proposal 標 dependency（不在範圍內 IMPL）

---

## §5 `[48] replay_manifest_registry_growth` healthcheck 影響預估

### §5.1 當前 FAIL 條件回顧

per `helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py:348-428`：

```python
REGISTRY_7D_PASS_MIN_ROWS: int = 1
REGISTRY_24H_WARN_MIN_ROWS: int = 0  # 0 row in 24h = WARN

# FAIL：rows_7d < 1 AND total_rows >= 2 → runner stalled
# WARN：rows_24h <= 0（quiet day）
# PASS：rows_24h >= 1 AND rows_7d >= 1
```

當前狀態（2026-05-28 empirical）：
- total = 23
- last_age = 407h（17.0d）
- rows_7d = 0
- rows_24h = 0
- → **FAIL「0 row in 7d but total=23: runner stalled」**

### §5.2 Daily cadence land 後狀態 timeline

| 時點 | rows_7d | rows_24h | last_age | 狀態 |
|---|---|---|---|---|
| Cron land 前 | 0 | 0 | 407h+ | FAIL |
| Cron land 後 D+0（首次 04:00 UTC fire）| 1 | 1 | < 24h | **PASS**（rows_7d ≥ 1 + rows_24h ≥ 1）|
| D+1 | 2 | 1 | < 24h | PASS |
| D+7 | 7 | 1 | < 24h | PASS |
| D+30 | 7（滾動 7d 窗）| 1 | < 24h | PASS |

### §5.3 結論

**`[48]` 在 cron 首次成功 fire 後（即 install 後第一個 04:00 UTC，最遲 24h 內）變 PASS**；持續 PASS 條件 = daily fire 不中斷（cron alive + replay_runner alive + register endpoint accept manifest + run 不 hang）。

二級保護：cron heartbeat sentinel `cron_heartbeat/m11_replay_runner_smoke.last_fire` mtime（per `replay_key_rotation_check.sh:91-97` pattern）— 若 cron 不 fire（systemd cron service down 等），mtime 滯後可由 `[77] cron_heartbeat` 既有/未來健康 check 偵測（per `feature_baseline_writer_cron.sh` 同 pattern）。

`[47] replay_runner_binary` 已 PASS（per `helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py:267-340` Linux-only check + 當前 `rust/target/release/replay_runner` 存在），不受 cron land 影響。

`[50] replay_run_state_health`（zombie 'running' 偵測）：daily 1 run cadence 對 zombie cap > 1h 不會觸發（single run 預期 < 2 min）。但 fixture broken / signing key drift / network issue 連續觸 6 個 failed status → 7d failed_rate > 10% PASS / > 20% FAIL；本 proposal 不額外處理該風險（既有 `[50]` 已 cover）。

---

## §6 Cross-Ref M7 Decay — Cadence 影響 M11 5th Signal Quality

### §6.1 ADR-0044 Decision 2 引用

per ADR-0044 line 74 + M7 design spec：

> | **E: M11 Replay Divergence** (ingest as 5th) | `daily_divergence_aggregate_30d > divergence_threshold` | 30d | M11 source |

關鍵：**「daily aggregate」是 M11 → M7 ingestion contract**。

### §6.2 Cadence 對 M7 signal 影響

| Cadence | M7 30d aggregate window 內 datapoint | 對 M7 signal power 影響 |
|---|---|---|
| On-demand | < 5（稀疏）| 樣本不足；M7 4 主 signal 仍可獨立 trigger，但 M11 第 5 signal 永遠 NaN/insufficient |
| 6h | 120 | 過密；對 1-day grain divergence 拆分過細 → 增加噪音不增加 power；M7 計算端可能需 sub-sample down to daily |
| **Daily** | **30** | **完美對齊 spec；30 個 dp / 30d window；M7 直接走 daily aggregate；signal power 最大化** |
| Hourly | 720 | 同 6h；過密 + ADR-0038 line 244 REJECT |

### §6.3 Stage A vs Stage B 差異

**Stage A（本 proposal）**：daily 1 run（single fixture）→ M11 → M7 ingest 是「Per (strategy, asset, day)」aggregate；當前 binary fixture cover BTCUSDT 1 個 cell；M7 30d window 內只看 BTCUSDT 1 cell（不充分 cohort coverage）。

**Stage B（Sprint 3 Phase A IMPL after）**：nightly cohort 5 strategy × N symbol；M11 → M7 daily aggregate 變成 「per (strategy, asset) × N cells × 30d」 = 完整 M7 detector 設計 input。

**結論**：Stage A daily cadence **不影響 M7 detector cadence contract**（仍是 daily aggregate；只是 cohort cell 數量稀疏）；Stage B IMPL 後從 1 cell 升為 125 cell，無需改 M7 端設計。

### §6.4 反模式（不可選）

- **若選 hourly / 6h**：M11 → M7 ingest 端需 sub-sample down to daily aggregate before feed M7；增加 IPC + Python 端聚合代碼；違反 ADR-0044 Decision 2 簡潔契約
- **若選 on-demand**：M11 5th signal 永遠 stale；M7 detector 多 source confirm（per ADR-0044 line 76 「Signal 連續 5 trading day confirmation OR 多 signal 同時 trigger」）少 1 source；4 主 signal 仍工作但 H-11 反向 attack mitigation 弱化（per M11 spec §7.2 14d persistent CRITICAL → M7 strong candidate）

---

## §7 Rollback Path — 若 cadence 證明過密造成 PG 壓力

### §7.1 監控指標（決定是否 rollback）

| 指標 | 來源 | 閾值 |
|---|---|---|
| PG `shared_buffers` cache hit ratio 退化 | `pg_stat_database.blks_hit / (blks_hit + blks_read)` | < 99% 持續 7d → 考慮 rollback |
| `replay.experiments` 表 size 異常增長 | `pg_total_relation_size('replay.experiments'::regclass)` | > 50 MB / 30d（vs 預估 1.5 MB；33× 偏差）→ 立即調查 |
| run_state zombie 'running' > 1h | `[50]` healthcheck | 連續 3 日 WARN → cadence 不適配 binary 真實 wall clock |
| cron fire interval drift | heartbeat sentinel mtime | > 26h 持續 2 cycle → systemd cron health issue（與 cadence 無關但同 mitigation path）|
| trading_ai PG 總 size 增長率 | `pg_database_size('trading_ai')` | > 100 MB/day（vs 預估 +50 kB）→ replay 不是主因但需 cross-investigate |

### §7.2 Rollback 三級階梯

**Level 1（最小衝擊）— 降頻 daily → twice-weekly**

```bash
# 編輯 crontab，從 `0 4 * * *` 改為 `0 4 * * 1,4`（週一 + 週四 04:00 UTC）
crontab -l | sed 's|^0 4 \* \* \* \(.*m11_replay_runner_smoke_cron\)|0 4 * * 1,4 \1|' | crontab -
```

影響：`[48]` healthcheck rows_7d = 2 仍 PASS；rows_24h 在非 fire 日 = 0 = WARN（不 FAIL）；可接受。

**Level 2（中等衝擊）— 停 cron 改 on-demand**

```bash
# disable cron entry
crontab -l | grep -v m11_replay_runner_smoke_cron | crontab -
# `[48]` 回 FAIL；屬於可接受短期狀態
```

影響：`[48]` rows_7d = 0 後 7d FAIL；Sprint 2 Wave 3 stage0_ready gate 阻塞需 operator review；M7 5th signal disabled。

**Level 3（極端 — 完整 stop + roll back schema）**

```bash
# stop cron + clean replay.* aged rows
crontab -l | grep -v m11_replay_runner_smoke_cron | crontab -
ssh trade-core 'psql -h 127.0.0.1 -p 5432 -U trading_admin -d trading_ai' <<SQL
BEGIN;
-- 保留最近 7d artifacts；其餘 cleanup
DELETE FROM replay.simulated_fills WHERE EXISTS (
  SELECT 1 FROM replay.run_state rs
  WHERE rs.run_id = simulated_fills.run_id
    AND rs.created_at < NOW() - INTERVAL '7 days'
);
DELETE FROM replay.report_artifacts WHERE created_at < NOW() - INTERVAL '7 days';
DELETE FROM replay.run_state WHERE created_at < NOW() - INTERVAL '7 days';
COMMIT;
SQL
```

影響：保留 schema + recent rows；釋放 storage；只在 Level 1+2 都不夠時動用；屬 ops dev/cold-restart 級操作。

### §7.3 Rollback 觸發條件總結

| Symptom | Level |
|---|---|
| PG cache hit < 99% > 7d | L1（降頻）|
| run_state failed_rate > 20% > 7d（fixture rotting）| L2（disable，調查 root cause）|
| replay.* 表 > 100 MB（10× 預估）| L2 + investigate |
| trading_ai PG > 5GB shared_buffers 邊界 | L3 + operator urgent review |
| Sprint 3 Phase A IMPL land 後 Stage B 上線 | **N/A — 升級非 rollback**；daily 直接由 Stage B wrapper 取代 |

### §7.4 為什麼 rollback 不太可能觸發

- Daily cadence 30d 增量 ~1.5 MB；對 4-8 GB shared_buffers 是 0.02-0.04% 級；PG IO 完全可忽略
- 既有 hourly cron（panel_aggregator_health 每 5 min；halt_audit_pg_writer 每 1 min）每天寫量遠超 daily replay；運維面已驗無 PG IO 壓力
- replay_runner ReplayProfile::Isolated 嚴格 fail-closed；不會洩漏到 live state；最壞情境 = 多個 failed run（`[50]` failed_rate WARN），不會傷 PG schema

---

## §8 Open Questions（給 operator 拍板時注意）

### OQ-1 — Service Principal 創建路徑

當前 `_require_replay_write(actor)` 設計面向 operator-interactive session；cron 用的 non-interactive Service principal 創建走哪條路徑？

**候選**：
- (a) E3 設計新 `m11_replay_smoke_principal` role + 寫入 `OPENCLAW_SECRETS_ROOT/environment_files/m11_replay_principal.env`
- (b) reuse 既有 `replay_key_rotation_check_cron` audit identity（per `replay_key_rotation_check.sh:280` `decided_by='replay_key_rotation_check_cron'`）
- (c) 走 systemd service unit + `User=ncyu` 但限制 capability

**建議起點**：(a) 顯式 Service principal；E3 sign-off；不 reuse 既有 audit identity 避免 audit trail 混淆。本 proposal 不裁定，留 PM + E3 review 時決。

### OQ-2 — `m11_replay_smoke_completed` event_type 是否擴 V035 enum

per `replay_key_rotation_check.sh:243-247` MED-1 retrofit comment 顯示 V035 governance_audit_log enum 不含「replay_key_rotation_alert」事件，piggyback `audit_write_failed`；m11 smoke 同樣 face this。

**候選**：
- (a) 同 piggyback `audit_write_failed` event_type + payload 帶 `alert_type='m11_replay_smoke_*'`
- (b) Sprint 3 Phase A IMPL 同步走 V### enum 擴 ticket
- (c) 新 V### proposal land enum 擴展 before cron install

**建議起點**：(a) piggyback 短期；(b) Sprint 3 Phase A 同步走。本 proposal mark dependency。

### OQ-3 — Stage A → Stage B 過渡時 cron entry 是否需 idempotent guard 改寫

Stage A `m11_replay_runner_smoke_cron.sh` vs Stage B `m11_nightly_replay.sh`（per M11 spec §13 reference）兩腳本名稱不同；install guard regex `m11_replay_runner_smoke_cron` 不會擋 Stage B install。

**候選**：
- (a) Stage B install 時 explicit refuse if Stage A entry exists；要求 operator 顯式 remove Stage A
- (b) Stage B 自動 replace Stage A entry（atomic crontab rewrite）
- (c) Stage A 維持與 Stage B 並存（cron 兩 entry，evidence 雙寫）

**建議起點**：(a) 對齊既有 `install_pg_dump_cron.sh:57-61` 慣例；ops governance 清晰。

---

## §9 Hard Boundary Compliance Confirmation

per CLAUDE.md §四 + §二 16 原則 + replay_runner.rs:225-276 三層 guard chain：

| 原則 | 本 proposal cron 行為 | 合規 |
|---|---|---|
| 1 單一寫入口 | cron 不創 trade 寫入口；走既有 `/replay/run` thin handler | ✅ |
| 2 讀寫分離 | replay_runner Isolated profile；只讀 fixture + 寫 replay.* schema；不寫 live state | ✅ |
| 3 AI 輸出 ≠ 命令 | cron 不調用 AI 推理；single fixture deterministic replay | ✅ |
| 4 策略不繞風控 | replay 不下訂單；ReplayPaperSnapshot + ReplayRiskAdapter 隔離 | ✅ |
| 5 生存 > 利潤 | daily cadence 最低 PG cost；不依賴 vendor optionality | ✅ |
| 6 失敗默認收縮 | exit code != 0 不 retry；Bybit retCode 路徑 N/A（Isolated profile 無 Bybit call）| ✅ |
| 7 學習 ≠ Live | cron 只寫 replay.* 不寫 trading.*；不觸 live config | ✅ |
| 8 交易可解釋 | run_state + report_artifacts 全 audit trail；`_emit_audit_stub` per route | ✅ |
| 9 雙重防線 | ReplayProfile::Isolated（compile-time）+ forbidden_guard（runtime）+ mac_policy_guard（host-aware）三層 | ✅ |
| 11 Agent 最大自主 | cron 不擴 agent 能力面；只是 binary 自動 invoke | ✅ |
| 12 Evidence-based | M11 設計就是 evidence accumulation；cadence 選擇基於實證 PG size + ADR 邊界 | ✅ |
| 13 Cost 感知 | daily cadence ~50 kB/day; ~$0 cost；不增加 AI call cost | ✅ |
| 14 零外部成本 | replay 用 self-hosted PG 無 vendor API（per ADR-0038 Decision 1）| ✅ |
| 16 Portfolio > 孤立 trade | Stage A 1 cell × daily；Stage B 升級 portfolio cohort；cadence 設計支持升級 | ✅ |

**Hard boundaries（CLAUDE.md §四）**：
- `live_execution_allowed` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / `live_reserved` 五項 gate **均不觸**
- LiveDemo 路徑不涉及（replay 不走 demo endpoint，走 in-process Isolated）
- Bybit retCode 路徑不涉及（不調 Bybit）
- `execution_authority` denylist 不涉及

**16 條全綠 + 0 硬邊界違反 → A 級合規**。

---

## §10 Cross-References

| 文件 | 對應段落 |
|---|---|
| `srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md` | Decision 1 + 5；line 244 hourly REJECT；§Decision 5 4h budget |
| `srv/docs/adr/0044-m7-decay-enforced-single-authority.md` | Decision 2 line 74 M11 as 5th signal「daily_divergence_aggregate_30d」 |
| `srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md` | §10.1 Phase A 60-80 hr IMPL pending；§2.1 nightly architecture |
| `srv/helper_scripts/db/passive_wait_healthcheck/checks_replay_maintenance.py` | `[48]` PASS/WARN/FAIL 規則 line 348-428 |
| `srv/helper_scripts/cron/install_pg_dump_cron.sh` | install script 範本（idempotent guard / DRY-RUN / env validation） |
| `srv/helper_scripts/cron/replay_key_rotation_check.sh` | cron pattern（heartbeat sentinel / lock / log / audit piggyback） |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` | `/experiments/register` + `/run` thin handler；`_require_replay_write` |
| `srv/rust/openclaw_engine/src/bin/replay_runner.rs` | Wave 3 P2b-S7/S8/S9 三層 guard；Wave 4 main flow |
| `srv/TODO.md` §1.7 / §1.7 v77 ticket P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL | 本 ticket source |
| `srv/TODO.md` §1.7 v77 ticket P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH | Sprint 2 Wave 3 stage0_ready 6 Reject gate 之一「M11 runner cron」 |
| memory `project_hardware_constraints` | 4-8 GB PG shared_buffers 硬約束（與本 proposal 1.5 MB/30d 對比驗收）|
| memory `feedback_v_migration_pg_dry_run` | Linux PG empirical 紀律（本 proposal 走 ssh trade-core 實證）|

---

## §11 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| PA | DRAFTED | 2026-05-28 | Cadence matrix + 推薦 daily 04:00 UTC + Stage A/B 分層 + 範本 + rollback path |
| PM | PENDING | — | 16 原則 + Sprint 2 Wave 3 stage0_ready impact + ADR-0044 對齊 final check |
| operator | PENDING | — | **拍板 cadence（A/B/C/D）+ OQ-1 Service principal 路徑**；本 proposal 不自啟 cron |
| E3 | PENDING | — | Service principal 創建 + secrets vault 入位（OQ-1）|
| E1 | PENDING | — | `m11_replay_runner_smoke_cron.sh` + `install_m11_replay_runner_smoke_cron.sh` IMPL（per §4.2-4.4 contract）|
| MIT | PENDING（optional）| — | V### enum 擴展 ticket if OQ-2 chooses path (b)/(c) |
| QA | PENDING | — | cron 4 場景 acceptance（首次 fire / idempotent re-install / install on existing entry / Mac refuse exit 2）|
| FA | PENDING | — | Stage A → Stage B 升級路徑 OQ-3 治理對齊 |

---

**END M11 `replay_runner` 排程提案**
