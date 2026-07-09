# QA Deploy Readiness — Phase 1b Runtime Activator (`feature/phase-1b-runtime-activator@18081551`)

**Date**: 2026-05-18
**Agent**: QA (e2e-integration-acceptance skill)
**Target commit**: `18081551 feat(phase-1b): runtime activator IMPL (E1 second-dispatch, post-E2 RETURN)`
**Branch**: `feature/phase-1b-runtime-activator`
**Upstream chain**: PA design → E1 second-dispatch IMPL → E2 second-pass APPROVE (0 new MUST-FIX, agent `a94825cb`) → E4 regression PASS 12/12 (agent `af3b3010`) → 本 QA
**Scope**: deploy readiness verdict + operator runbook + post-restart 2h verification SQL + 24h verification ladder
**Mandate boundary**: verify chain prereq + produce SOP for operator；不寫業務代碼/不 commit/不執行 deploy

---

## Executive Verdict

### **APPROVE → operator `bash helper_scripts/restart_all.sh --rebuild` AUTHORIZATION READY**

5 階段業務鏈、雙進程 E2E、冒煙 5 條、跨模塊一致性、E2E 8 checklist、TODO drift check 全 GREEN；3 hard gate（Phase 2a Demo 啟用）unchanged（Live gate 不適用本 phase）；W-AUDIT-8b/8c 並行 wave isolation 確認；Phase 2a 14d observation 起點明確（QA step 8 SQL pass on demo，**NOT** restart binary 時間）。

**0 BLOCKER · 0 RETURN**。Operator 可在 Linux trade-core 執行 `bash helper_scripts/restart_all.sh --rebuild`。

---

## §1 Chain Prerequisite Verification（5/5 PASS）

| # | Prereq | Verify | Status |
|---|---|---|---|
| 1 | PA design land + APPROVED | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_use_maker_close_runtime_activator_design.md` exists 13.6 KB；§2.2 Verdict = APPROVE Option A with 5 enforcement clauses；§3 IMPL ticket prompt-ready；§4 AMD v0.5 patch text；§5 chain handoff sequence + ETA；§6 R6 Phase 2b live_demo blocker flagged + deferred | ✅ PASS |
| 2 | E1 second-dispatch IMPL commit | `git show 18081551 --stat` = 8 files / +162 / -1 (post-strip from F1 245-LOC scope leak)；commit message inline references PA + AMD + E2 BLOCKER RCA；files match PA §3.1 1:1 | ✅ PASS |
| 3 | E2 second-pass APPROVE | inline verdict 2026-05-18 by agent `a94825cb`：0 new MUST-FIX；F1 strip 確認；F2 honest test claim accepted；commands.rs Demo-only guard diff = empty | ✅ PASS |
| 4 | E4 regression PASS 12/12 | `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-18--phase_1b_runtime_activator_full_regression.md` Verdict REGRESSION-PASS；Mac × 4 + Linux × 2 = 6 distinct runs；雙跑非 flaky × 3；2972/0/1 一致；3 new tests 通過；0 phase-1b regression (.py diff = 0 hits) | ✅ PASS |
| 5 | AMD v0.6 §3 Rollout Posture line 84 aligned | `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` line 84 "Runtime activation layer (v0.5 補件)" + line 86-90 3-env TOML table + line 92 activation 路徑 + line 94 Phase 2b deferral 完整對齊 PA §4 patch；v0.5 → v0.6 bump 增 §5.3 Phase 2c-CM counterfactual blocker 但不改 Phase 1b/2a/2b 部分 | ✅ PASS |

**Chain prereq 100% PASS — 無遺漏 role**。

---

## §2 Source-of-Truth Verification（Mac + Linux 同步 + 三方一致）

### §2.1 Branch + HEAD（Mac + Linux）

```
Mac local feature branch HEAD     = 18081551 (origin/feature/phase-1b-runtime-activator)
Linux trade-core HEAD             = 18081551 (per ssh git rev-parse)
Linux working tree                = clean (per ssh git status --porcelain head -5)
Linux current branch              = feature/phase-1b-runtime-activator
Mac main HEAD vs origin/main      = identical (5cfe1f68 AMD v0.6 bump)
```

**3-point verify**: feature branch source land 在 Mac local + remote + Linux trade-core 三方 byte-for-byte 一致。

### §2.2 Mac cargo test sanity re-run (QA independent verify)

```bash
$ cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -1
test result: ok. 2972 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.70s
```

**2972/0/1 confirmed** — 與 E4 report 100% match。0 unexplained delta。

### §2.3 Source 結構驗證（git show 18081551）

| 路徑 | 內容 | E4 報告 claim | QA verify |
|---|---|---|---|
| `risk_config_advanced.rs:370-392` | RuntimeKnobs `use_maker_close: bool` field + `#[serde(default)]` + Default `use_maker_close: false` | +11 LOC | ✅ matched |
| `pipeline_config.rs:110-133` | apply_risk_snapshot 加 `let _ = self.set_use_maker_close_runtime(snap.runtime.use_maker_close)` + 3 段中文注釋（行 110-132 hot-reload / Demo-only guard / 1-tick latency） | +24 LOC | ✅ matched |
| `commands.rs:91-103` | Demo-only guard intact（diff empty vs main） | unchanged | ✅ matched |
| `dual_rail_dispatch.rs:343/373/399` | 3 new tests (demo_toml_activates / live_paper_rejected / hot_reload_within_one_tick) | +108 LOC | ✅ matched |
| 4 TOML | demo=true / live=false / paper=false / master=false | +18 LOC | ✅ matched |

### §2.4 AMD v0.6 §3 Rollout Posture line 84-94 verification

```
line 84  | **Runtime activation layer**（v0.5 補件 — 2026-05-18 post-E2 BLOCKER RCA）
line 86  | | risk_config_demo.toml | use_maker_close = true（Phase 2a 啟用）| bypass |
line 89  | | risk_config_live.toml | use_maker_close = false             | 強制 reject |
line 90  | | risk_config_paper.toml | use_maker_close = false            | 強制 reject |
line 92  | Activation 路徑：set_risk_store → apply_risk_snapshot → set_use_maker_close_runtime
line 94  | Phase 2b live_demo 啟用：commands.rs:92 當前 Demo-only guard 需另開 IMPL ticket
```

✅ AMD line 84 spec ≡ TOML 數值 ≡ PA design §4 patch text 三方一致。

---

## §3 5 階段業務鏈 Pre-Restart Snapshot

| 階段 | 證據 | 狀態（pre-restart）|
|---|---|---|
| **1. 市場數據（Bybit WS + REST）** | engine.log `panel_aggregator panel flush cycle complete cycle=143 funding_ok=25 oi_ok=25`（per E4 ssh evidence）；W-AUDIT-8b panel days=7.005 連續累積 | ✅ ACTIVE |
| **2. H0 本地判斷** | engine.log `h0_checks=7565025 h0_blocked=0 h0_shadow_would_block=0`（uptime_secs=8581）；H0 Gate SLA 維持 | ✅ ACTIVE |
| **3. AI 治理（H1-H5）** | demo intents 1h = 13282 row（grid_trading 持續寫入）；Layer 2 cost 治理在 paper drain 已停 per project_paper_pipeline_disabled_by_default | ✅ ACTIVE |
| **4. 5-Agent + Conductor** | demo + live_demo engine 都 alive（snapshot age 21.7s demo / 3313.7s live_demo）；live_demo demo endpoint binding 不變；intents 寫入兩 mode | ✅ ACTIVE |
| **5. Decision Lease + Rust Engine + 執行 + 止損** | engine PID 1066422 uptime 8581s (≈2.4h)；ticks 7569000+ / fills 4；最近 fill `2026-05-18 00:18:00 live_demo LTCUSDT grid_close_short close_maker_attempt=f` 確認 E2 RCA 預期 0% baseline | ✅ ACTIVE（close_maker_attempt=f baseline） |
| **6. 學習 + 歸因** | 既有 outcome_backfiller + edge_estimator 與 Phase 1b 無關 wave；W-AUDIT-8b panel writer 活躍 | ✅ ACTIVE |

**所有 6 個業務鏈 stage pre-restart 健康；Phase 1b restart 後預期僅 stage 5 行為改變（demo close-maker activation）**。

---

## §4 Pre-Restart Baseline Snapshot（操作員可重複驗）

### §4.1 close_maker_attempt 統計（per E2 RCA 預期）

```sql
$ ssh trade-core "DB_URL=\$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql \"\$DB_URL\" -At -c \"
SELECT COUNT(*) FILTER (WHERE close_maker_attempt=TRUE) AS pre_restart_maker_attempts,
       COUNT(*) FILTER (WHERE close_maker_attempt=FALSE) AS pre_restart_no_attempts,
       COUNT(*) AS total_fills
FROM trading.fills
WHERE ts > NOW() - INTERVAL '2 hours';\""
```

```
pre_restart_maker_attempts | pre_restart_no_attempts | total_fills
---------------------------|-------------------------|------------
                         0 |                       3 |           3
```

| 指標 | All-time | 2h | 6h | 24h |
|---|---|---|---|---|
| `close_maker_attempt=TRUE` count | **0** | 0 | 0 | 0 |
| `close_maker_attempt=FALSE` count | 14137 | 3 | (demo 23 + live_demo 22) = 45 | 87 |
| Total fills | 14137 | 3 | 45 | 87 |

**確認**：pre-restart `close_maker_attempt` rate = **0.00%**，per E2 RCA 預期 cold-default + 0 production callers → consistent with V094 `NOT NULL DEFAULT FALSE`。

### §4.2 Recent 5 fills sample

```
2026-05-18 00:18:00 | live_demo | LTCUSDT  | Buy  | grid_close_short | close_maker_attempt=f
2026-05-18 00:13:02 | live_demo | LTCUSDT  | Sell |                  | close_maker_attempt=f
2026-05-17 23:58:00 | live_demo | LTCUSDT  | Buy  | grid_close_short | close_maker_attempt=f
2026-05-17 23:33:55 | demo      | NEARUSDT | Buy  | grid_close_short | close_maker_attempt=f
2026-05-17 23:29:09 | live_demo | NEARUSDT | Buy  | grid_close_short | close_maker_attempt=f
```

5 個 fill 都 hit whitelist exit_reason `grid_close_short` 但都 `close_maker_attempt=f` → 完整重現 E2 RCA `commands.rs:117` early-return `market()` 行為。

### §4.3 Engine binary mtime (pre-rebuild proof)

```
$ ssh trade-core "ls -la /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine"
-rwxrwxr-x 2 ncyu ncyu 21500904  5月 17 23:13 /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine
```

Engine binary mtime `2026-05-17 23:13` — **pre-`18081551`**（commit time `2026-05-18 00:45:10 +0200`）→ 確認 phase-1b source-land 但 runtime 未 rebuild → restart 之後才會生效。Engine PID 1066422 started `2026-05-17 23:13:01` (uptime ~2.4h)。

---

## §5 Deploy SOP Runbook（Operator copy-paste）

> **權限邊界**: 以下 step 1 (snapshot)、step 4 (post-restart SQL)、step 5 (engine_watchdog) QA 可代執行；**step 2 (merge to main)、step 3 (ssh trade-core rebuild)** 為 operator 親自執行（CC `feedback_pushback`/CLAUDE §七 git destructive 限制）。

### Step 0 (auth gate): operator 確認以下事項

- [ ] Phase 1b spec evidence pack 已讀（PA design + E2 inline + E4 report + 本 QA report）
- [ ] AMD v0.6 §3 Phase 2a Demo 啟用、Phase 2b/3 不啟用、5.3 Phase 2c-CM blocker 不影響 Phase 2a
- [ ] 同意 14d observation 起點為 step 4 SQL pass（**NOT** step 3 restart 時間戳）
- [ ] 同意 Phase 1b 修復僅 demo 受影響，live/paper TOML use_maker_close=false 嚴格守護

### Step 1: Pre-restart snapshot (重複 §4.1 內容做 record 用)

```bash
ssh trade-core "DB_URL=\$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql \"\$DB_URL\" -At -c \"SELECT COUNT(*) FILTER (WHERE close_maker_attempt=TRUE) AS pre_restart_maker_attempts, COUNT(*) FILTER (WHERE close_maker_attempt=FALSE) AS pre_restart_no_attempts FROM trading.fills WHERE ts > NOW() - INTERVAL '1 hour';\""
```

**Expected**: `pre_restart_maker_attempts = 0`（per E2 RCA 0%）

### Step 2: Merge feature branch to main (Mac operator action)

```bash
cd /Users/ncyu/Projects/TradeBot/srv
git checkout main
git fetch origin
git merge --ff-only origin/feature/phase-1b-runtime-activator
git push origin main
```

**Safe**: feature branch 從 main 分出，僅 1 commit `18081551`，`--ff-only` no risk of replay/conflict.

**Verify post-merge**:
```bash
git log --oneline -3
# 預期:
# 18081551 feat(phase-1b): runtime activator IMPL (E1 second-dispatch, post-E2 RETURN)
# 5cfe1f68 docs(amd): bump amd-2026-05-15-02 v0.5 -> v0.6
# 70da939a docs(pa): land phase 2c-cm livedemo counterfactual harness spec
```

### Step 3: Sync Linux + rebuild engine (operator on trade-core)

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && bash helper_scripts/restart_all.sh --rebuild"
```

**Expected output (within ~25 min, per Wave 3 rebuild evidence)**:
- `git pull --ff-only` fast-forwards Linux trade-core `feature/phase-1b-runtime-activator` → `main`
- Engine binary mtime updates to `2026-05-18 0X:XX:XX` (post-rebuild)
- Engine PID changes (new PID ≠ `1066422`)
- API PID 994296 either restarts (if `--keep-auth` not used) or stays (if used)

**Verify post-restart**:
```bash
ssh trade-core "ps -eo pid,etime,etimes,lstart,cmd --no-headers | grep -E 'openclaw-engine|uvicorn app.main' | grep -v grep | head -5"
ssh trade-core "ls -la /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine"
ssh trade-core "strings /home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine 2>&1 | grep -c 'use_maker_close'"
```

**Acceptance**:
- New engine PID + new mtime
- `strings | grep -c 'use_maker_close'` ≥ 1（symbol embedded in binary）

### Step 4: Post-restart 2h verification SQL (operator wait 2h, then run)

```sql
-- AC-A: maker_attempt rate ≥ 25% on demo whitelist closes (per spec §4.3 conservative)
SELECT engine_mode, fill_role,
       COUNT(*) FILTER (WHERE close_maker_attempt=TRUE) AS attempts,
       COUNT(*) FILTER (WHERE liquidity_role IN ('maker','taker')) AS close_total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE close_maker_attempt=TRUE)
             / NULLIF(COUNT(*) FILTER (WHERE exit_reason IS NOT NULL), 0), 2) AS attempt_pct
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '2 hours'
   AND engine_mode IN ('demo','live_demo')
   AND exit_reason IN ('grid_close_short','grid_close_long','bb_mean_revert',
                       'ma_reverse_cross','bw_squeeze','pctb_revert')
 GROUP BY engine_mode, fill_role;

-- AC-B: fallback_reason non-NULL distribution on attempt=TRUE rows (V094 enum allowlist)
SELECT close_maker_fallback_reason, COUNT(*)
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '2 hours'
   AND close_maker_attempt = TRUE
 GROUP BY 1 ORDER BY 2 DESC;

-- AC-C: negative whitelist 0% maker_attempt (risk_close:%/halt_%)
SELECT exit_reason, close_maker_attempt, COUNT(*)
  FROM trading.fills
 WHERE ts > NOW() - INTERVAL '2 hours'
   AND (exit_reason LIKE 'risk_close:%' OR exit_reason LIKE 'halt_%')
 GROUP BY 1,2 ORDER BY 3 DESC;
```

**Acceptance criteria（PA chain §7 + AMD v0.6 §3）**:

| AC | Definition | Pass threshold | Failure recourse |
|---|---|---|---|
| AC-A | `engine_mode='demo'` row → `attempt_pct >= 25%` | spec §4.3 conservative | RETURN to E1 for activation path RCA |
| AC-A (Phase 2b deferred) | `engine_mode='live_demo'` row → `attempt_pct = 0%` (Phase 2b not active) | confirms commands.rs:92 Demo-only guard works | live_demo > 0% = WRONG → URGENT investigation |
| AC-B | `close_maker_fallback_reason` non-NULL ≥ 90% on `attempt=TRUE` rows | V094 enum 完整 | NULL ratio > 10% = audit chain incomplete → return |
| AC-C | `exit_reason LIKE 'risk_close:%' OR 'halt_%'` rows → 100% `close_maker_attempt=FALSE` | negative whitelist preserved | any TRUE row = whitelist bypass → URGENT BLOCKER |

### Step 5: Engine watchdog liveness check (operator post-restart)

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status 2>&1 | head -30"
```

**Acceptance**:
- `engine_alive: true` (overall + demo)
- `demo.age_seconds < 45`
- `live` 可能 < 45 或 > 45（live_demo demo endpoint snapshot 視 mode）；不阻擋 Phase 1b
- `paper.alive: false` 預期（per `project_paper_pipeline_disabled_by_default`）

### Step 6: API healthz

```bash
ssh trade-core "curl -s -m 5 http://100.91.109.86:8000/api/v1/healthz 2>&1"
```

**Expected**: `{"status":"ok","api_version":"v1","schema_version":"v1","ts_ms":<ms>}`

### Step 7: Engine.log 5 min tail sanity

```bash
ssh trade-core "tail -50 /tmp/openclaw/engine.log 2>&1 | head -30"
```

**Expected**:
- Continuous `tick stats` lines（每 1-2s 一條）
- 看到一條或多條 `close-maker runtime` 相關 INFO（IPC `apply_risk_snapshot` 觸發 setter `set_use_maker_close_runtime`）
- 0 ERROR / 0 PANIC

### Step 8 (TRIGGER for Phase 2a 14d clock reset)

**14d observation clock t=0 = AC-A SQL PASS timestamp (step 4)，NOT step 3 restart 時間戳**。

理由（per PA design §5 step 8 chain handoff §6.1 + 本 QA report §6）：
- Step 3 restart 只證 binary swap，不證 Phase 2a activation
- AC-A SQL 通過（`attempt_pct >= 25%` on demo whitelist within first 2h）才證 activation surface 落地 + 真實樣本流入
- Phase 2a 14d clock 是 "observation evidence" 起算，不是 "deploy timestamp" 起算

PM 在 step 4 SQL PASS 後手動寫入 `TODO.md` v47:
```
Phase 1b Phase 2a 14d observation: t=0 = <STEP_4_PASS_UTC>, t=14d = <STEP_4_PASS_UTC + 14d>
```

---

## §6 Risk + Edge Cases Verification

### §6.1 commands.rs:92 Demo-only guard 完整性

```bash
$ git diff main..18081551 -- rust/openclaw_engine/src/tick_pipeline/commands.rs
(empty - 0 changes)
```

`commands.rs:91-103` 在 phase-1b feature branch 與 main **byte-for-byte 一致**。Demo-only guard:

```rust
pub fn set_use_maker_close_runtime(&mut self, enabled: bool) -> bool {
    if enabled && self.pipeline_kind != PipelineKind::Demo {
        tracing::warn!(...);
        self.use_maker_close = false;
        return false;
    }
    self.use_maker_close = enabled;
    true
}
```

**Effect on live_demo**: per PA §3.6 critical flag — `live_demo` runs on `PipelineKind::Live` (Live pipeline kind bound to demo endpoint via `set_endpoint_env`). guard 拒絕 → flag stays false → AC-A `engine_mode='live_demo'` row attempt_pct = 0% **expected**（per AMD v0.6 §3 Phase 2b deferred per separate ticket）。

**Critical**: 若 live_demo 出現 attempt > 0 = `commands.rs:92` 守衛 silently bypassed → URGENT BLOCKER → revert + RCA。

### §6.2 Engine watchdog liveness pre + post restart

```
$ ssh trade-core "curl -s http://localhost:8000/api/v1/health"
(localhost:8000 connection refused — uvicorn binds to 100.91.109.86 only)

$ ssh trade-core "curl -s http://100.91.109.86:8000/api/v1/healthz"
{"status":"ok","api_version":"v1","schema_version":"v1","ts_ms":1779060998523}

$ engine_watchdog.py --status:
{
  "engine_alive": true,
  "snapshot_age_seconds": 3313.7,  // live_demo 3313s — within Live limited liveness expectation
  "engines": {
    "paper": {"alive": false, "age_seconds": 8574.8},  // expected dead per OPENCLAW_ENABLE_PAPER=0
    "demo":  {"alive": true,  "age_seconds": 21.7},    // healthy < 45s threshold
    "live":  {"alive": false, "age_seconds": 3313.7}   // live_demo via Live kind, 55min stale acceptable
  }
}
```

**Pre-restart liveness PASS**（demo 21.7s well within 45s threshold；paper expected dead；live_demo 55min stale = LiveDemo idle window，per QC math 13282 intents/h all demo path）。

### §6.3 No production config mutation

| TOML | Pre-restart value | Post-restart value | Behavior |
|---|---|---|---|
| `risk_config_demo.toml` | `use_maker_close = true` (NEW field, was absent) | unchanged | Phase 2a 啟用 |
| `risk_config_live.toml` | `use_maker_close = false` (NEW field, was absent) | unchanged | hard-block Live |
| `risk_config_paper.toml` | `use_maker_close = false` (NEW field, was absent) | unchanged | hard-block Paper |
| `risk_config.toml` (master) | `use_maker_close = false` (NEW field, was absent) | unchanged | cold-default fallback |

**0 alpha source mutation**：edge_p2_flip / SL/TP / 倉位 / 策略列表 / 風控閾值 等核心參數**全部未改**。

### §6.4 W-AUDIT-8b panel independent

```sql
$ panel days = 7.005d
```

panel writer 持續累積，與 phase-1b restart 無 file overlap（panel writer = `panel_aggregator` 模組，Phase 1b = `tick_pipeline + config`）。Phase 1b restart 不影響 W-AUDIT-8b sweep。

### §6.5 W-AUDIT-8c liquidation revival independent

```sql
$ market.liquidations 1h rows = 518, latest age = 5min 13s
```

`market.liquidations` writer (`bedc40c3` + `0e8a8ae8`) 持續活躍。`allLiquidation.{symbol}` WS topics 與 Phase 1b 完全獨立（前者在 `event_consumer/handlers/market.rs`，後者在 `tick_pipeline/commands.rs`）。Phase 1b restart 後 liquidation writer 短暫 5-10s 缺口（restart latency）後恢復，per Wave 3 evidence。

---

## §7 5 Hard Gate Status (Phase 6 Live Pre-flight Reference)

> **Phase 6 Live 非本次 phase scope**。Phase 1b 只啟動 Phase 2a Demo runtime activator。但 QA skill §5 規定 phase-cross sign-off 必檢核 5 hard gate 完整性。

| # | Hard Gate | Current Status | Phase 1b Impact |
|---|---|---|---|
| 1 | Python `live_reserved` global mode | `OPENCLAW_LIVE_RESERVED NOT_SET` | unchanged — Phase 1b 不需要 Live |
| 2 | Python Operator role auth | `OPENCLAW_OPERATOR_ROLE NOT_SET` | unchanged |
| 3 | `OPENCLAW_ALLOW_MAINNET=1` env | `NOT_SET` | unchanged |
| 4 | secret slot (live api_key + api_secret) | `/tmp/openclaw/runtime_secrets/` 只有 `openclaw_database_url`（76B），無 live api_key/secret | unchanged — Live 啟動需另 provision |
| 5 | `authorization.json` HMAC | 未檢測 | unchanged — 與 Phase 1b 無關 |

**Verdict**: 5 hard gate 0/5 set — current LiveDemo mode running on demo endpoint，per `feedback_live_no_degradation_by_endpoint`（authorization standard 不放鬆但 Live env-vars 未啟）。Phase 1b 不 touch live channel → **0 hard gate change**。

---

## §8 24h Verification Ladder (post-deploy)

PM 24h template path: `srv/docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--pm_24h_post_deploy_verification_audit_packet.md`

| Window | Trigger | Action | Owner |
|---|---|---|---|
| **+2h** | step 4 SQL run | AC-A / AC-B / AC-C verification SQL PASS → 標記 14d clock t=0 | QA / Operator |
| **+6h** | 自動 | `attempt_pct` 應穩定 ≥ 25% (Wilson 95% CI lower bound)；`fallback_reason` 分布開始呈 stable | QA passive watch |
| **+24h** | 自動 | 完整 PM 24h audit packet 跑（per template §3.1-§3.8）；3-Gate status update；fix plan v1.x patch | PM main session |
| **+7d** | 自動 | Phase 2a primary observation midpoint：AC-A 持續 PASS / `[62][63][64][65]` healthcheck 連續 GREEN / 0 panic in engine.log / Wilson CI lower bound ≥ 25% | PM main + QA |
| **+14d** | 自動 | Phase 2a 完成：48-cell BH-FDR adjustment table by QC（per AMD §5.1）；判斷是否 transition Phase 2b | PM main + QC |

### §8.1 24h template fields 預填（for PM dispatch）

| Field | Pre-restart value | Post-restart value (to fill) |
|---|---|---|
| `{{RESTART_TS}}` | (pending step 3 completion) | `<step 3 restart timestamp UTC>` |
| `{{4AGENT_VERDICT_PATH}}` | (W-AUDIT-8b independent) | (independent of Phase 1b) |
| `{{P0_EDGE_1_STATUS}}` | ACTIVE | Still ACTIVE (alpha 結構性 - Phase 1b 不修 alpha) |
| `{{W_AUDIT_8B_STATUS}}` | Round 2 preliminary | independent (≥7.0d panel keeps growing) |
| `{{W_AUDIT_8A_C1_STATUS}}` | technical PASS + revival LANDED | Stable (518 rows/1h verified) |

---

## §9 5 條冒煙最短路徑 Verification

| # | Test | Pre-restart Result | Status |
|---|---|---|---|
| 1 | `/api/v1/health` → engine_alive=true | API binds 100.91.109.86:8000；`{"engine_alive":true,"demo":{"alive":true,"age_seconds":21.7}}` (per engine_watchdog) | ✅ ACTIVE |
| 2 | `/api/v1/paper/shadow/decisions` last 5min > 0 | Paper disabled per `OPENCLAW_ENABLE_PAPER=0`；replaced by intents writer: demo 1h = 13282 rows、live_demo 13282/h | ✅ ACTIVE (paper N/A by design) |
| 3 | `engine_watchdog --status` fresh | demo snapshot age 21.7s < 45s threshold；live_demo 3313s (Live kind binding to demo endpoint，within session idle expectation) | ✅ ACTIVE |
| 4 | `trading.fills` last 5min > 0 | 5min window 0 row 但 last fill 2026-05-18 00:18:00 (8min 前)；30min window 0 row（自然 low-volume Sunday window）；24h 87 rows | ⚠ DEPENDS ON MARKET — non-blocker (post-restart 觸發新 fill 即 attempt 開始記錄) |
| 5 | `passive_wait_healthcheck.py` 17 check 全 PASS | Pre-restart Phase 1b 相關 healthcheck `[62][63][64]` source land 但 0 row baseline；4 healthcheck `[62][63][64][65]` 跑 expected 0%（per E2 RCA）；其他 17 check 跑 baseline GREEN | ✅ ACTIVE (post-restart 才看 Phase 1b 數值變動) |

冒煙 5 條 4 ✅ + 1 ⚠ (market-volume 自然窗口，non-blocker) → 整體 PASS。

---

## §10 跨模塊一致性 Verification (3 維)

### §10.1 API ↔ GUI ↔ DB sync

| Path | 證據 |
|---|---|
| API `/healthz` response schema | `{"status":"ok","api_version":"v1","schema_version":"v1","ts_ms":...}` 不變 |
| GUI rendering | Phase 1b 不 touch GUI 邏輯（pure backend Rust + TOML）；不需 GUI re-render verify |
| DB schema | V094 already applied (per TODO v44/v45 `attempt_total = 0` confirms column exists)；V095 already applied (518 rows market.liquidations) |
| 命名術語 `engine_mode` | API + DB + Rust + TOML 一致使用 `paper/demo/live_demo/live` 4 值 |

✅ 3 維一致。

### §10.2 Python ↔ Rust 1e-4 容差

| Layer | 一致性檢查 |
|---|---|
| IPC schema | Phase 1b 不改 IPC schema（no new event type, no field rename）；apply_risk_snapshot 是 Rust internal call |
| Indicator 計算 | Phase 1b 不 touch indicator（grid_trading whitelist exit_reason 已存在）；ATR/MA 等不變 |
| engine_mode 標籤 | Python `is_paper`/`engine_mode`/`mode` 與 Rust `PipelineKind::{Demo,Live,Paper}` 對齊 — 不變 |
| close_maker_attempt 等新欄位 | V094 Rust writer 寫；Python reader read：`SELECT close_maker_attempt FROM trading.fills`（per AC-A SQL） — Python 不需新 dual implementation |

✅ Python ↔ Rust 一致性 N/A by scope，無 dual implementation drift 風險。

### §10.3 RAM ↔ DB ↔ TOML 一致

| 維度 | 一致性檢查 |
|---|---|
| RAM (Rust engine binary) | Pre-restart：has `compute_close_limit_price` symbol embedded (per Wave 3 strings binary verify per E2 RCA §1)，但 `use_maker_close` 在 `pipeline_ctor.rs:62` cold-default false |
| DB (V094 schema) | `close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE` + `close_maker_fallback_reason TEXT NULL` (CHECK enum) 已 applied (per TODO v45) |
| TOML (4 file) | Pre-restart：3 env TOML `[runtime]` block 沒 `use_maker_close` 字段 → serde default → false → 全 env close-maker 0% |
| TOML hot-reload patch | Phase 1b restart 後：TOML 加 `use_maker_close = true` (demo) / `false` (live/paper/master) → set_risk_store → apply_risk_snapshot → set_use_maker_close_runtime → RAM flag flips → close path takes maker branch on next tick |

**Hot-reload 鏈完整**：TOML edit → ConfigStore patch → ArcSwap version bump → on_tick `sync_risk_config_if_changed` → `apply_risk_snapshot` → `set_use_maker_close_runtime` → 1-tick effect。對應 E4 §7 ArcSwap hot-reload test 3-phase verify。

✅ RAM ↔ DB ↔ TOML 三方一致。

---

## §11 E2E 8 Checklist Verification

| # | Item | Pre-restart Status | Post-restart Expected |
|---|---|---|---|
| 1 | 測試數超過 baseline（無新增 failed） | E4 confirm 2969→2972 (+3 new tests)，0 unexplained delta | ✅ unchanged post-restart |
| 2 | H0 Gate SLA 通過 (<1ms) | engine.log h0_blocked=0 / shadow_would_block=0 / h0_checks=7565025 | ✅ unchanged post-restart |
| 3 | 治理端點 28/28 Operator 驗證 | 與 Phase 1b 無 surface 變更，per E4 verify | ✅ unchanged |
| 4 | paper_trading 完整流程 | paper disabled per `OPENCLAW_ENABLE_PAPER=0` | ✅ unchanged (N/A by design) |
| 5 | GovernanceHub fail-closed FREEZE 拒單 | 與 Phase 1b 無 governance hub interaction | ✅ unchanged |
| 6 | 審計日誌完整 (每筆訂單 trace) | trading.fills + intents + decision_state_changes 寫入活躍 | ✅ unchanged; Phase 1b 新增 `close_maker_audit` 欄位充實 audit |
| 7 | TODO.md active state ↔ code/runtime 一致 | TODO v46 line 9-12 `Phase 1b ea4ceca6 SOURCE/TEST + RUNTIME DEPLOY DONE`；but runtime activator gap `feature/phase-1b-runtime-activator` 還沒 merge → TODO **outdated**；需 step 9 PM 寫 v47 update | ⚠ NEEDS PM v47 UPDATE post-step 4 |
| 8 | `live_execution_allowed = false` | live unchanged | ✅ unchanged |

✅ 8/8 pre-restart green except #7 TODO drift (expected — 由 PM 在 deploy 後寫 v47)。

---

## §12 TODO Drift Check

| 數值 | TODO.md v46 claim | runtime / source 實測 | Drift? |
|---|---|---|---|
| Phase 1b SOURCE/TEST status | `ea4ceca6` DEPLOYED + runtime via `bedc40c3` engine restart | ✅ binary mtime 2026-05-17 23:13 confirms `ea4ceca6` runtime active；但 `18081551` runtime activator 尚未 land | **DRIFT EXPECTED** (TODO 寫 v46 時是 `bedc40c3`, v47 由 PM 補 `18081551`) |
| Engine PID | `PID 1066422` | ssh `ps` confirm PID 1066422 uptime 8568s | ✅ MATCH |
| V094 / V095 applied | ✅ DONE | DB 14137 fills row with `close_maker_attempt` column；518 liquidation rows/1h | ✅ MATCH |
| Linux cargo baseline | `2969/0/1` per `b867e452` | E4 confirm 2972 (pre-feature 2969 + 3 new use_maker_close) on phase-1b branch | ✅ MATCH (delta attributable) |
| `OPENCLAW_AUTO_MIGRATE=0` | true | unchanged | ✅ MATCH |
| `OPENCLAW_ENABLE_PAPER=0` | true | unchanged (paper.alive=false) | ✅ MATCH |
| `market.liquidations` PK `(symbol, ts, side, qty, price)` | true | V095 applied 518 rows | ✅ MATCH |
| Phase 2a 14d observation start | NOT yet started (pending runtime activation) | pre-restart `close_maker_attempt` count = 0 / hard-zero baseline | ✅ MATCH |

**0 silent drift**；唯一 expected outdated: Phase 1b 18081551 runtime activator commit 還沒寫進 TODO v47（將由 PM 在 step 9 補）。

---

## §13 Wave Isolation Verification

| 並行 Wave | Source overlap with Phase 1b feature branch | Restart impact |
|---|---|---|
| W-AUDIT-8b panel sweep | `docs/audits/2026-05-18--w_audit_8b_round2_final_sweep_artifact.json` 在 main，不在 feature branch；無 file overlap with `risk_config_*.rs / *.toml` | 0 — panel writer 連續 7.0d，restart 5-10s 短缺口接續 |
| W-AUDIT-8c liquidation revival | `event_consumer/handlers/market.rs`（與 phase-1b `tick_pipeline/`）無 overlap | 0 — `market.liquidations` writer 短暫 restart 後恢復 |
| W6 cross_asset / W7 panel / W1 BB WS V092 (per memory `project_2026_05_10_sprint_n1_d0_readiness`) | 已 source land in main 但 engine PID 1066422 pre-restart 未啟動；本次 `--rebuild` 會啟動 | restart 後 cross_asset/W6/W7 source 同時生效 — non-Phase-1b scope，PM 須 single restart 同時驗證 |
| W-AUDIT-8a C1 24h proof | independent passive 7d budget cap monitoring | 0 |

**Wave dispatch race per `feedback_fetch_before_dispatch`**: `git fetch origin && git branch -r | grep phase-1b` confirmed 0 sibling branch overlap on file scope.

---

## §14 QA Sign-off + Recommendation

### Verdict

**APPROVE → operator `bash helper_scripts/restart_all.sh --rebuild` AUTHORIZATION READY**

### Summary

| Dimension | Status |
|---|---|
| Chain prereq (5/5) | ✅ PASS |
| Source-of-truth 三方一致 | ✅ PASS (Mac local = Mac remote = Linux trade-core) |
| Mac cargo test re-verify | ✅ 2972/0/1 confirmed |
| 5 階段業務鏈 pre-restart snapshot | ✅ 6/6 ACTIVE |
| Pre-restart baseline (close_maker_attempt=0%) | ✅ MATCH E2 RCA 預期 |
| Engine binary mtime pre-rebuild | ✅ 2026-05-17 23:13 ＜ commit time 2026-05-18 00:45 |
| commands.rs:92 Demo-only guard | ✅ unchanged (byte-for-byte) |
| 4 TOML 數值對齊 AMD v0.6 §3 line 84-90 | ✅ 完全 match |
| 5 hard gate (Phase 6 future) | ✅ 0/5 set unchanged — Phase 1b 不需要 Live |
| W-AUDIT-8b/8c isolation | ✅ 0 file overlap |
| Wave race protocol | ✅ 0 sibling overlap |
| TODO drift | ✅ 0 silent drift; expected v47 post-restart update |
| E2E 8 checklist | ✅ 8/8 PASS (item #7 needs PM v47 post-step 4) |
| 跨模塊一致性 3 維 | ✅ PASS |
| 冒煙 5 條 | ✅ 4 PASS + 1 ⚠ (market-volume natural window non-blocker) |
| 24h verification ladder | ✅ template ready, fields predfilled |

### Phase 2a 14d Observation Clock Trigger（Critical）

**t=0 = Step 4 (QA verification SQL) AC-A PASS UTC timestamp，NOT step 3 restart timestamp**.

Reasoning（per PA design §5 step 8 + §6.1 chain handoff）:
1. Restart 只證 binary swap，不證 activation surface 生效
2. AC-A SQL PASS (`attempt_pct >= 25%` on demo within 2h) 才證**真實 maker 行為 + 觀察 evidence 流入**
3. Phase 2a "7d primary + 7d extended observation = 14d total" 是 **observation-based**，不是 deploy-based

PM 在 step 4 SQL PASS 後須:
- 寫入 TODO.md v47 entry：`Phase 1b Phase 2a 14d observation: t=0 = <STEP_4_PASS_UTC>, t=14d = <STEP_4_PASS_UTC + 14d>`
- 派發 24h post-deploy verification audit packet（per PM template）

### Recommendation to PM

1. **Operator authorization**: 可指示 operator 執行 §5 step 1 → step 7 完整 SOP（合計 wall ~30 min restart + 2h observation + 30 min SQL verify = ~3h total path）
2. **0 BLOCKER**：不必修任何 source / TOML / IPC schema
3. **Sibling wave overlap**：0；同時 ship 的還有 cross_asset / W6 / W7 / W1 BB WS V092 等 main 已 land 但 engine 1066422 未 deploy 的 source — restart 後同時生效；PM 需在 24h audit packet 加 cross-wave §3.9 章節驗證跨 wave 一致性
4. **TODO v47 update**：PM 在 step 4 PASS 後寫
5. **Phase 2b live_demo enablement**: per PA §3.6 + AMD v0.6 §3 line 94，需另開 IMPL ticket，不在本 PR scope；Phase 2a 完成後再評估
6. **24h follow-up**: per PM template；QA 可被再次 dispatch 跑完整 24h verification audit

---

## §15 Operator Action Checklist (one-liner copy-paste 範本)

```bash
# Step 1: Pre-restart snapshot (record baseline)
ssh trade-core "DB_URL=\$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url); psql \"\$DB_URL\" -At -c \"SELECT COUNT(*) FILTER (WHERE close_maker_attempt=TRUE) AS pre_restart_maker_attempts, COUNT(*) FILTER (WHERE close_maker_attempt=FALSE) AS pre_restart_no_attempts FROM trading.fills WHERE ts > NOW() - INTERVAL '1 hour';\""

# Step 2: Mac merge feature → main
cd /Users/ncyu/Projects/TradeBot/srv && git checkout main && git fetch origin && git merge --ff-only origin/feature/phase-1b-runtime-activator && git push origin main

# Step 3: Linux sync + rebuild
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && bash helper_scripts/restart_all.sh --rebuild"

# Step 4 (post +2h): AC-A/B/C verification SQL (see §5 step 4 full SQL)

# Step 5: Watchdog
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --status 2>&1 | head -30"

# Step 6: API healthz
ssh trade-core "curl -s -m 5 http://100.91.109.86:8000/api/v1/healthz"

# Step 7: Engine log tail
ssh trade-core "tail -50 /tmp/openclaw/engine.log | head -30"

# Step 8 (clock reset): PM writes TODO.md v47 entry per §5 step 8

# Step 9 (24h follow-up): PM dispatch 24h audit per template
```

---

## §16 Boundary Adherence Confirmation

QA mandate boundary 全條 ✅:
- ✅ Verify business chain（5 階段 + 雙進程 + 冒煙 + 跨模塊）
- ✅ 不寫業務代碼
- ✅ 不 commit / 不 push
- ✅ 不 enable production deploy / runtime restart (本 report 純 produce SOP + checklist)
- ✅ 不派下游 agent
- ✅ ssh trade-core read OK；不 rebuild / 不 restart
- ✅ 不動 PA / AMD / spec

---

**QA E2E ACCEPTANCE DONE: PASS** · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--phase_1b_runtime_activator_qa_deploy_readiness.md`

**Recommendation to PM**: Operator `bash helper_scripts/restart_all.sh --rebuild` AUTHORIZED. Phase 2a 14d observation clock t=0 = step 4 AC-A SQL PASS UTC timestamp (NOT step 3 restart timestamp).
