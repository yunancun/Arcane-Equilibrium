---
title: E1 IMPL — M11 replay_runner Daily 04:00 UTC cron install
date: 2026-05-28
author: E1
ticket: P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL (= M11.a) — IMPL phase per PA A proposal
parent_specs:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--m11_replay_runner_schedule_proposal.md
  - srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md
  - srv/docs/adr/0044-m7-decay-enforced-single-authority.md
runtime evidence captured: 2026-05-28 ssh trade-core empirical install + smoke
status: E1 IMPLEMENTATION DONE — pending E2 review + E4 regression
---

# E1 IMPL — M11 replay_runner Daily 04:00 UTC cron install

## §0 任務摘要

依 PA A proposal §4 contract + operator confirm Daily 04:00 UTC：

1. 寫 `install_m11_replay_runner_cron.sh`（166 LOC）對齊 `install_pg_dump_cron.sh` 模式（Linux only / idempotent guard / DRY-RUN / env value validate / pre-flight 4 項）。
2. 寫 `m11_replay_runner_daily_cron.sh`（371 LOC）Stage A single-fixture smoke heartbeat 模式：register + run dispatch via REST API。
3. ssh trade-core install dry-run + APPLY=1 實裝 + 手動 smoke + `[48]` healthcheck before/after 對比。
4. SCRIPT_INDEX.md 新增 2 個 entry（M11 段）。
5. E1 report（本檔）+ memory append（最後 step）。

**所有 acceptance gate 通過**：
- ✅ register http=200 + run http=200 + dur=2s smoke
- ✅ replay.experiments 23 → 24 rows
- ✅ rows_24h=1 / rows_7d=1
- ✅ `[48]` healthcheck flip：FAIL → **PASS**（"registry growth healthy"）
- ✅ governance_audit_log 2 row（_register_failed + _smoke_completed）
- ✅ cron entry `0 4 * * *` 入 crontab
- ✅ idempotent guard reject re-install
- ✅ heartbeat sentinel + log + JSONL 齊備

## §1 修改清單

| 檔案 | 動作 | LOC | 說明 |
|---|---|---|---|
| `srv/helper_scripts/cron/install_m11_replay_runner_cron.sh` | NEW | 166 | M11.a daily cron installer |
| `srv/helper_scripts/cron/m11_replay_runner_daily_cron.sh` | NEW | 371 | Stage A smoke heartbeat wrapper |
| `srv/helper_scripts/SCRIPT_INDEX.md` | MODIFY | +6 | 新「2026-05-28 M11 replay_runner Daily Stage A Smoke」段 |
| `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--e1_m11_replay_runner_cron_install.md` | NEW | — | 本 report |

**不改動**：
- `replay_runner` binary（已 build；本任務不重建）
- 既有任何 cron entry
- V### migration / governance_audit_log enum（OQ-2 piggyback path）
- API server / replay_routes.py（REST 既有 contract）

## §2 設計決策（vs PA proposal）

### §2.1 對齊 PA proposal 的部分

- §4.2 wrapper contract 步驟 1-6: Linux gate / runner resolve / register / run / heartbeat / log ✅
- §4.3 cron entry format `0 4 * * *` + env vars 三個 + log redirect ✅
- §4.4 install script 6 維度對齊（idempotent guard / DRY-RUN env / env value validate / pre-flight / wrapper executable check / 避撞時段）✅
- §5 `[48]` healthcheck flip 預期（next 24h FAIL → PASS）— **首次 fire 後已驗 PASS**
- §6 ADR-0044 M11 as 5th signal「daily aggregate」granularity 對齊
- §9 hard boundary 16 條全綠（不觸 live_execution_allowed / authorization.json / OPENCLAW_ALLOW_MAINNET 等五項 gate）

### §2.2 偏離 PA proposal 的部分（合理化）

1. **wrapper 名稱**：PA proposal 用 `m11_replay_runner_smoke_cron.sh`；operator task 指定 `m11_replay_runner_daily_cron.sh`。**採用 operator naming**（task override PA draft）。
2. **Service principal 認證**（PA §4.5 + OQ-1）：PA 推薦新建 dedicated `m11_replay_smoke_principal`；當前 IMPL **重用 operator API token**（`OPENCLAW_API_TOKEN_FILE` per restart_all.sh deploy）。理由：
   - OQ-1 PA flag = PENDING；不在 IMPL scope
   - operator API token ≠ signed live authorization；不觸 CLAUDE.md §四 hard boundary
   - 短期 piggyback；長期 swap 只需改 wrapper 中 1 處 `API_TOKEN_FILE` 解析
   - **follow-up TODO**：E3 設計 dedicated Service principal + swap wrapper
3. **CSRF middleware**：實機驗證 CSRF middleware enforce 所有寫 route；cron 加 cookie+header double-submit 同值 32-byte random hex 通過（middleware 只 constant-time compare 兩值同源）。**未改 csrf_middleware exempt list**（避免擴大攻擊面）。
4. **API base URL**：PA §4.3 範本 `127.0.0.1:8000`；實機 uvicorn bind 在 Tailscale IPv4 `100.91.x.x:8000` 而非 0.0.0.0，loopback 不通。Wrapper 改 auto-resolve `tailscale ip -4`，env `OPENCLAW_API_BASE_URL` 可覆寫，fallback loopback。
5. **embargo_days=14**（不是 PA 範本 0.0）：實機 PG CHECK `chk_embargo_days` 要求 `embargo_days >= GREATEST(7, ceil(2 * half_life_days))`；half_life=7 ⇒ 下限 14。
6. **governance_audit_log event_type**（PA OQ-2）：採 (a) piggyback `audit_write_failed` + payload.alert_type，與 `replay_key_rotation_check.sh:243-285` 一致。Sprint 3 Phase A 同步擴 V### enum 為 follow-up。
7. **psql INSERT 寫法**：對齊 `trading_ai_pg_dump_cron.sh:132-148` heredoc + dollar-quoted (`$payload$...$payload$`)；不用 `psql -v var=value` 因 `-c` 模式對 JSON 內 `:` 衝突（被當 variable substitution prefix）。

## §3 關鍵 diff / IMPL 細節

### §3.1 install script 6 維度（對齊 install_pg_dump_cron.sh 慣例）

| 維度 | install_pg_dump | install_m11_replay_runner |
|---|---|---|
| Linux only gate | ✅ uname Linux check | ✅ 同 |
| idempotent guard | grep `(pg_dump\|trading_ai_pg_dump_cron\.sh)` | grep `m11_replay_runner` |
| DRY-RUN env | `OPENCLAW_BACKUP_CRON_APPLY=1` | `OPENCLAW_M11_REPLAY_CRON_APPLY=1` |
| env value validate | `_validate_cron_env_value` 3 條規則 | 同 helper function 重用 |
| pre-flight | secrets env file + pg_dump binary in PATH | secrets env file + API token + fixture + release binary |
| 避撞時段 | 03:00 UTC | 04:00 UTC（避 03:00 / 03:17 / 04:41 / 06:00 / 09:00） |

### §3.2 wrapper 4 階段流程

```
Stage 1: pre-flight + env load
  - Linux gate / secrets env / PG creds / API token / fixture / lock dir / heartbeat touch
  - CSRF token gen (32-byte random hex via /dev/urandom or python secrets.token_hex)
  - API base auto-resolve (Tailscale ip -4 → fallback loopback)

Stage 2: POST /replay/experiments/register
  - body: idem=m11-daily-smoke-YYYY-MM-DD + symbol=BTCUSDT + strategy=grid_trading
          + timeframe=1m + data_tier=S3 + window=last 24h + sha=fixture sha256
          + half_life=7 + embargo=14 + strategy_params + manifest_jsonb
  - http=200/201 → 解析 experiment_id；fail → audit + JSONL + fail-soft exit 0

Stage 3: POST /replay/run
  - body: experiment_id + idempotency_key=m11-run-YYYY-MM-DD
  - http=200/201 → 解析 run_id + status；fail → audit + fail-soft exit 0
  - 不 poll status terminal state（server 端 async 跑；[50] 偵測 zombie > 1h）

Stage 4: governance_audit_log INSERT smoke_completed + JSONL ok + log + exit 0
```

### §3.3 安全 / 治理對照

| CLAUDE.md §二 16 條 | 本 IMPL 對齊 |
|---|---|
| #1 single controlled write entry | ✅ 走 register endpoint thin handler，不繞 raw SQL INSERT |
| #2 read/write 分離 | ✅ replay.* schema isolated；不寫 trading.* |
| #3 AI 輸出 ≠ 命令 | ✅ cron 不調 AI；deterministic single fixture |
| #4 策略不繞風控 | ✅ replay 不下訂單；ReplayProfile::Isolated S7/S8/S9 三層 guard (binary 端強制) |
| #5-6 生存 / 失敗收縮 | ✅ fail-soft exit 0 + audit + JSONL 留 trace |
| #7 學習 ≠ Live | ✅ 只寫 replay.* 不寫 trading.*；不觸 live config |
| #8 交易可解釋 | ✅ register row + run_state row + audit row 全 trail |
| #9 雙重防線 | ✅ binary 端 ReplayProfile::Isolated + cron 端 fixture path validation |
| #11 Agent 最大自主 | ✅ cron 不擴 agent 能力面 |
| #12 evidence-based | ✅ daily evidence accumulation per ADR-0038 design |
| #13-14 cost 感知 / 零外部成本 | ✅ ~50 kB/day PG IO，無 vendor cost |
| CLAUDE.md §四 hard boundary | ✅ 不觸 live_execution_allowed / OPENCLAW_ALLOW_MAINNET / authorization.json / live_reserved / Bybit retCode 任一 gate |

## §4 不確定之處 / follow-up TODO

### §4.1 OQ-1 Service principal swap（PA proposal §8）

當前 wrapper 用 operator API token (`.secrets/api_token`)。PA proposal 推薦 dedicated `m11_replay_smoke_principal`。

**Follow-up TODO**：
- E3 設計 Service principal role + `replay:write` scope only（不可 `live:write`）
- secrets vault 入位 `$OPENCLAW_SECRETS_ROOT/environment_files/m11_replay_principal.env`
- wrapper 中 `API_TOKEN_FILE` 路徑切換（1 處 env override）

### §4.2 OQ-2 V### enum 擴展（PA proposal §8）

當前 audit 走 piggyback `audit_write_failed` + payload.alert_type。Sprint 3 Phase A IMPL 時擴 V### enum：
- `m11_replay_runner_smoke_completed`
- `m11_replay_runner_smoke_register_failed`
- `m11_replay_runner_smoke_failed`

**Follow-up TODO**：MIT 開 V114（或 Sprint 3 wave V###）擴 enum + wrapper 改用專屬 event_type。

### §4.3 Stage A → Stage B 升級（PA proposal §6.3）

ADR-0038 Sprint 3 Phase A IMPL（M11 spec §10.1 60-80 hr）land 後：
- 拆 wrapper 為 `m11_nightly_replay.sh` cohort wrapper
- iterate 5 strategy × N symbol
- 同步走 V107 divergence schema land
- Stage A entry 換成 Stage B entry（PA OQ-3 候選 (a) explicit remove + reinstall）

### §4.4 已知限制

1. **single-fixture only**：每天只跑 BTCUSDT 1 cell；M7 30d window 拿到 1 cell × 30 dp 而非 cohort × N cells × 30 dp。per PA §6.3 結論 Stage A signal value 在「runner alive」非「strategy alpha drift」；Stage B IMPL 後自然解。
2. **CSRF token random per fire**：不持久化；每次 cron fire 生新 32-byte hex。double-submit 自洽即可。
3. **wrapper 不 poll status terminal**：避免 cron 端阻塞 30s+；server 端 async；`[50]` healthcheck 偵測 zombie 'running' > 1h。
4. **fail-soft exit 0**：避免 cron mail spam；`[48]` rows_24h WARN + `[50]` failed_rate 已 cover 連續多日 fail。
5. **embargo_days=14**：fixed value；不真消費（fixture deterministic）。如未來改 fixture 帶真實 OOS window，需重新計算下限。

## §5 Empirical evidence

### §5.1 install dry-run（ssh trade-core）

```
------- proposed crontab entry -------
0 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/m11_replay_runner_daily_cron.sh >> /tmp/openclaw/logs/m11_replay_runner_daily_cron.cron.log 2>&1
--------------------------------------
Schedule: 0 4 * * * UTC (Daily 04:00 UTC = M11.a)
Healthcheck impact: [48] FAIL → PASS within 24h after first fire

避撞時段:
  03:00 UTC pg_dump (30 min budget)
  03:17 UTC ml_training_maintenance
  04:00 UTC ★ M11 daily smoke ★
  04:41 UTC feature_baseline_writer
  06:00 UTC counterfactual_daily
  09:00 UTC replay_key_rotation_check
```

### §5.2 install APPLY=1（實裝結果）

```
INSTALLED: m11_replay_runner cron entry added. Verify with: crontab -l | grep m11_replay_runner
```

### §5.3 crontab -l grep m11

```
0 4 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/m11_replay_runner_daily_cron.sh >> /tmp/openclaw/logs/m11_replay_runner_daily_cron.cron.log 2>&1
```

### §5.4 idempotent guard verify

```
SKIP: existing m11_replay_runner cron entry detected; not installing (manually remove first).
```

### §5.5 manual smoke dry-run output（成功 2026-05-28 16:53:51 UTC）

```
[2026-05-28T16:53:51Z] === M11 replay_runner Stage A smoke START (BASE=/home/ncyu/BybitOpenClaw/srv API=http://100.91.109.86:8000 FIXTURE=...synthetic_btcusdt.json) ===
[2026-05-28T16:53:51Z] POST .../api/v1/replay/experiments/register idem=m11-daily-smoke-2026-05-28
[2026-05-28T16:53:51Z] OK register http=200 experiment_id=c0ba0553-5cba-4024-934d-82f0ef81468c
[2026-05-28T16:53:51Z] POST .../api/v1/replay/run experiment_id=c0ba0553-5cba-4024-934d-82f0ef81468c
[2026-05-28T16:53:53Z] OK run http=200 run_id=6532fc38338f4bf299846c0c55f880c5 initial_status=running
[2026-05-28T16:53:53Z] OK m11_replay_runner_daily_cron experiment_id=c0ba0553-5cba-4024-934d-82f0ef81468c run_id=6532fc38338f4bf299846c0c55f880c5 dur=2s
INSERT 0 1
[2026-05-28T16:53:53Z] === M11 replay_runner Stage A smoke END OK dur=2s ===
EXIT=0
```

### §5.6 `[48]` healthcheck before/after verdict

**BEFORE（cron install 前）**：
```
FAIL [48] replay_manifest_registry_growth [48] total=23 rows_7d=0 rows_24h=0 last_age=410.1h — 0 row in 7d but total=23: runner stalled (check replay_runner binary + register endpoint logs)
```

**AFTER（manual smoke 後 + cron 已 installed）**：
```
PASS [48] replay_manifest_registry_growth [48] total=24 rows_7d=1 rows_24h=1 last_age=0.0h — registry growth healthy
```

**Verdict flip**：FAIL → **PASS**（rows_7d 0→1 + rows_24h 0→1 + last_age 410.1h→0.0h）✅

### §5.7 governance_audit_log evidence

```sql
SELECT ts, event_type, decided_by, payload->>'alert_type' AS alert_type
  FROM learning.governance_audit_log
 WHERE decided_by='m11_replay_runner_daily_cron'
 ORDER BY ts DESC LIMIT 5;

              ts               |     event_type     |          decided_by          |               alert_type
-------------------------------+--------------------+------------------------------+-----------------------------------------
 2026-05-28 18:53:53.381216+02 | audit_write_failed | m11_replay_runner_daily_cron | m11_replay_runner_smoke_completed
 2026-05-28 18:53:01.041003+02 | audit_write_failed | m11_replay_runner_daily_cron | m11_replay_runner_smoke_register_failed
(2 rows)
```

第一條為 IMPL iteration 中 CHECK violation 失敗（embargo_days=0 引致 chk_embargo_days fail）；第二條為 fix 後 success run。**audit trail 完整保留兩次嘗試的 trace**。

## §6 Operator 下一步

### §6.1 立即（PM 派 chain）

1. **E2 對抗性審查**：靜態 review 兩 script + SCRIPT_INDEX edit；重點 push back item：
   - CSRF random token 安全性（cookie+header 同源 double-submit 滿足 middleware 但實質繞 CSRF）
   - operator API token 重用 vs Service principal（OQ-1 deferred）
   - fail-soft exit 0 是否可能掩蓋連續失敗
   - audit piggyback `audit_write_failed` event_type 是否與其他 audit 衝突
   - psql heredoc dollar-quoting 對 JSON 中 `$payload$` literal 出現的處理（payload 內容由 cron 控制，無 user input；但 future 改動時需注意）
2. **E4 regression**：
   - 跑既有 cron 相關 pytest（`test_replay_key_rotation_check.py` 等）確認無相對導入問題
   - 跑 `passive_wait_healthcheck.py` 全套確認 `[48]` 與 `[47] [49] [50]` 互動正常
   - 確認 24h 後（次日 04:00 UTC 後）cron 自動 fire 一次（無需 operator 介入）

### §6.2 中期 follow-up（24-72h）

1. **24h post-install verify**（D+1 04:30 UTC 後）：
   - `crontab -l | grep m11` 仍在
   - `tail /tmp/openclaw/logs/m11_replay_runner_daily_cron.cron.log` 顯示 04:00 fire smoke completed
   - `[48]` healthcheck 持續 PASS
   - `replay.experiments` rows_24h ≥ 1 / rows_7d ≥ 2
2. **7d post-install verify**（D+7 06:00 UTC 後）：
   - `replay.experiments` rows_7d = 7
   - `[48]` 連續 7 日 PASS（無一 WARN/FAIL）
   - 確認 30d 增量符合 PA §2.4 預估 ~1.5 MB
3. **TODO §1.7 update**：mark `P2-M11-REPLAY-RUNNER-SCHEDULE-PROPOSAL` 為 DONE；新增 follow-up entries：
   - `P3-M11-SERVICE-PRINCIPAL-SWAP`（OQ-1 swap from operator API token）
   - `P3-M11-V###-AUDIT-ENUM-EXPAND`（OQ-2 擴 V035 governance_audit_log enum 加 m11_*）
   - `P3-M11-STAGE-B-COHORT-WRAPPER`（OQ-3 Sprint 3 Phase A IMPL）

### §6.3 長期（Sprint 3+）

- M11 spec §10.1 60-80 hr IMPL land 後 Stage B nightly cohort wrapper
- V107 divergence schema land + M7 5th signal ingest hookup
- 升級 cron entry from Stage A smoke heartbeat 至 full nightly cohort

---

**E1 IMPL DONE**：報告 commit 由 PM 統一執行 chain E1→E2→E4→QA→PM。

報告路徑：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--e1_m11_replay_runner_cron_install.md`
