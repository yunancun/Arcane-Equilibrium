# REF-20 Sprint 3 Track I — Linux Deploy Operator Runbook

**日期**：2026-05-03
**狀態**：Ready for operator action
**前置**：Sprint 1+2+3 Track H 全 closed（commit `dbcf845b` 三端同步）
**整合**：取代 `2026-05-03--ref20_final_closure_and_deploy_guidance.md` Phase B-G（後者基於 Wave 1-9 closure，本 runbook 含 Sprint 1+2+3 cumulative + cold audit fix-up + V049-V054 完整 chain）

---

## 0. 前置確認 / Pre-flight Check

### 三端同步狀態（執行前先驗）

```bash
# Mac 端
cd /Users/ncyu/Projects/TradeBot/srv && git log --oneline -3
# 期望 HEAD = dbcf845b

# Linux 端
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -3"
# 期望 HEAD = dbcf845b
```

### 已 land 的 Sprint 1+2+3 commits 總覽

| Commit | 範圍 |
|---|---|
| `edf33c0` | Sprint 1（5 P0 security + V049-V053 schema）|
| `5184990` | AMD-2026-05-03-01 Wave 7 amendment |
| `dbcf845b` | Sprint 3 Track H Decision Lease retrofit + V054 |

### Track I 預期影響面

- **Linux PostgreSQL**：apply 19 個新 V### migration（V036-V054）
- **Linux engine binary**：cargo --release rebuild（含 replay_runner 新 binary + Decision Lease facade）
- **Linux Python uvicorn**：restart 載入新 routes（replay_routes.py + governance_lease_bridge.py + ipc_client.py）
- **Linux cron**：install 新 cron（signing key rotation + artifact prune + wave9 KPI/incident + healthcheck）
- **Linux env vars**：set OPENCLAW_REPLAY_SIGNING_KEY / OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0 / OPENCLAW_LEASE_PYTHON_IPC_ENABLED
- **Predicted runtime change**：feature flag 默認 OFF → **production 0 行為改動**（accept-in-tree + deploy-time gate retained）

---

## Phase A — Mac dev pre-deploy 驗證（再驗一次）

```bash
cd /Users/ncyu/Projects/TradeBot/srv

# A.1 Python pytest（cold reality SSOT）
python3 -m pytest --tb=no -q 2>&1 | tail -5
# 期望：3431 PASS / 1 fail (pre-existing E4-P0-1) / 10 skip

# A.2 Rust workspace
cd rust/openclaw_engine && cargo test --release --workspace 2>&1 | tail -5
# 期望：3132 PASS / 2 fail (pre-existing E4-P0-2) / 3 ignored

# A.3 Track H specific 63 PASS
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_lease_bridge.py \
  -v 2>&1 | tail -5
# 期望：44 PASS

# A.4 V054 Mac dev real-PG idempotent dry-run
psql -d openclaw_test -f sql/migrations/V054__lease_transitions_audit_writer.sql && \
psql -d openclaw_test -f sql/migrations/V054__lease_transitions_audit_writer.sql 2>&1 | tail -10
# 期望：0 RAISE EXCEPTION（idempotent）
```

**通過 A.1-A.4 才繼續 Phase B**。任何 fail → 退回 Sprint 3 Track H E1 retrofit。

---

## Phase B — Linux PostgreSQL Migration Apply（19 個 V###，**順序敏感**）

> ⚠️ **DBA 級謹慎**：每步 verify 後才下一步。中間任何 fail 必停止 + 通報 PM。

```bash
ssh trade-core
cd ~/BybitOpenClaw/srv
git status --porcelain  # 必空（0 unstaged）
git log --oneline -3    # HEAD 必 dbcf845b
```

### B.1 Sprint 1 Wave 3 P2a-S4（V036 → producer switch → V037）

```bash
# B.1.1 V036 verify_function + GRANT
psql -d openclaw -f sql/migrations/V036__replay_evidence_source_guard.sql
# verify
psql -d openclaw -c "SELECT 'V036 OK' WHERE EXISTS (SELECT 1 FROM information_schema.routines WHERE routine_name='verify_replay_evidence_and_insert');"

# B.1.2 Producer switch verify (4 producer call)
# E.g. dream_engine.py / opportunity_tracker.py / mlde_shadow_advisor.py / mlde_demo_applier.py
# 必先 restart Python services 載入 commit dbcf845b 帶的 producer 切換
bash helper_scripts/restart_all.sh  # NO --rebuild flag（Rust binary 暫不重建，下面 Phase C 才做）

# B.1.3 Smoke 1-2 hours，verify INSERT via verify function PASS（cron 跑）
# 觀察 logs/openclaw_uvicorn.log 看 4 producer 都進 verify_replay_evidence_and_insert path

# B.1.4 V037 REVOKE PUBLIC INSERT
psql -d openclaw -f sql/migrations/V037__replay_evidence_revoke_public_insert.sql
# verify
psql -d openclaw -c "SELECT has_table_privilege('public', 'learning.mlde_shadow_recommendations', 'INSERT') AS public_can_insert;"
# 期望：public_can_insert = false
```

### B.2 Sprint 1 Wave 3 P2a-S6（V038 → V039 backfill → V040 healthcheck → V040 finalize）

```bash
# B.2.1 V038 add_evidence_source_tier
psql -d openclaw -f sql/migrations/V038__add_evidence_source_tier.sql

# B.2.2 V039 backfill（**注意 GUC 環境變數**）
PGOPTIONS="-c replay.migration_env=linux_trade_core" psql -d openclaw -f sql/migrations/V039__backfill_evidence_source_tier.sql

# B.2.3 V040 healthcheck（read-only 0 NULL row 驗）
psql -d openclaw -f sql/migrations/V040_healthcheck.sql
# 必 0 NULL row，才放下一步

# B.2.4 V040 finalize NOT NULL + CHECK
psql -d openclaw -f sql/migrations/V040__finalize_evidence_source_tier.sql
```

### B.3 Sprint 1 Wave 5 P3a-Q2（V041 OOS embargo）

```bash
psql -d openclaw -f sql/migrations/V041__replay_oos_embargo_enforcement.sql
```

### B.4 Sprint 1 Track D（V049-V052 schema 補造 + FK redirect）

```bash
# B.4.1 V049 replay_experiments 22 col + EXCLUDE GIST + Guard A/B/C
psql -d openclaw -f sql/migrations/V049__replay_experiments.sql

# B.4.2 V050 replay_simulated_fills 17 col + FK V049
psql -d openclaw -f sql/migrations/V050__replay_simulated_fills.sql

# B.4.3 V051 mlde_recommendations 雙路 CHECK
psql -d openclaw -f sql/migrations/V051__mlde_recommendations_replay_columns.sql

# B.4.4 V052 preflight + V052 FK redirect
psql -d openclaw -f sql/migrations/V052_preflight.sql
# 必驗 5 probe 全綠（dangling 0 / FK present / PK type uuid），才放下一步
psql -d openclaw -f sql/migrations/V052__replay_run_state_artifacts_fk_redirect.sql
```

### B.5 Sprint 1 Track C V053（governance_audit_log enum extension race-free）

```bash
psql -d openclaw -f sql/migrations/V053__governance_audit_log_replay_event_types.sql
# verify enum 13 values
psql -d openclaw -c "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'chk_event_type';"
```

### B.6 Sprint 1+2 既有 Wave 6/8/9 V###（V043 + V044 + V045-V048）

```bash
# replay schema bootstrap
psql -d openclaw -c "CREATE SCHEMA IF NOT EXISTS replay;"

# Wave 4 P2b-T2/T3
psql -d openclaw -f sql/migrations/V045__replay_run_state.sql
psql -d openclaw -f sql/migrations/V046__replay_report_artifacts.sql

# Wave 6 P4-Q5
psql -d openclaw -f sql/migrations/V043__replay_mlde_replay_veto_log.sql

# Wave 8 P6-S14（**注意 V044 enum DROP+ADD 有 race，P2-AUDIT-7 ticket 修方案待 deploy 後**）
psql -d openclaw -f sql/migrations/V044__replay_handoff_idempotency_unique.sql

# Wave 9（V047/V048 plain table，1y retention 0 設 → P2-WAVE-9-V047-V048-RETENTION）
psql -d openclaw -f sql/migrations/V047__replay_business_kpi_snapshots.sql
psql -d openclaw -f sql/migrations/V048__replay_audit_incident_summaries.sql
```

### B.7 Sprint 3 Track H V054（Decision Lease audit writer + hypertable）

```bash
# **要求 TimescaleDB extension（如未裝先 CREATE EXTENSION timescaledb;）**
psql -d openclaw -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
# V054 含 BEGIN+LOCK TABLE ACCESS EXCLUSIVE+COMMIT race-free pattern
psql -d openclaw -f sql/migrations/V054__lease_transitions_audit_writer.sql

# verify hypertable + 7 lease event_type
psql -d openclaw -c "SELECT * FROM _timescaledb_catalog.hypertable WHERE table_name='lease_transitions';"
psql -d openclaw -c "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'chk_event_type';"
# 期望 enum 含 7 lease event_type
```

### B.8 Migration 完成 verify

```bash
psql -d openclaw -c "SELECT MAX(version) AS max_v FROM _sqlx_migrations;"
# 期望：max_v = 54
psql -d openclaw -c "SELECT COUNT(*) AS replay_tables FROM information_schema.tables WHERE table_schema='replay';"
# 期望：replay_tables ≥ 7
```

**Phase B 完成標誌**：max_v = 54 + replay schema ≥ 7 tables + 0 RAISE。

---

## Phase C — Linux Engine Binary Build + Deploy

### C.1 cargo --release 全 build（含 replay_runner 新 binary）

```bash
cd ~/BybitOpenClaw/srv/rust
cargo build --release --bin openclaw_engine --bin replay_runner
# 預期 ~3-5 min
ls -la target/release/openclaw_engine target/release/replay_runner
```

### C.2 nm symbol audit（驗 replay_runner 0 forbidden symbol）

```bash
cd ~/BybitOpenClaw/srv
bash helper_scripts/ci/replay_runner_symbol_audit.sh
# 期望：exit 0 PASS（0 forbidden class hit）
```

### C.3 Signing key generate（如未生成）

```bash
sudo -u openclaw bash helper_scripts/operator/generate_replay_signing_key.sh paper
# 記錄 fingerprint 到 1Password
# 設 OPENCLAW_REPLAY_SIGNING_KEY env var 在 openclaw runtime profile
```

---

## Phase D — Env Var + Cron Install

### D.1 Env var 配置（**Decision Lease feature flag 默認 OFF**）

在 Linux openclaw runtime（systemd unit 或 .env 檔）加：

```bash
# Sprint 3 Track H Decision Lease retrofit feature flag
export OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0  # default OFF（Phase 5 P0-EDGE-2 後 flip）
export OPENCLAW_LEASE_PYTHON_IPC_ENABLED=0   # 同 above

# Sprint 1 Track A spawn argv schema
# (no env var needed — Track A spawn argv 對齊已在 commit dbcf845b code 中)

# Sprint 1 Track C release profile gate
export OPENCLAW_RELEASE_PROFILE=live  # 強制 boot guard raise 阻止 OPENCLAW_REPLAY_VERIFY_TEST_KEY

# Sprint 1 Track B signing key
export OPENCLAW_REPLAY_SIGNING_KEY=<from 1Password>  # 90d rotation
```

### D.2 Cron install

```bash
crontab -e
```

加入：

```
# Sprint 1 Wave 2 P2a-S1 signing key 90d rotation + 180d retention
0  9 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_rotation_check.sh
30 9 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_key_archive_cleanup.py

# Sprint 1 Wave 3 P2a-S5 artifact prune (6h)
0 */6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/replay_artifact_prune.py

# Sprint 1 Wave 9 14d gradient observation
0  * * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh
0  6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/wave9_business_kpi_collector.py
30 6 * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/cron/wave9_audit_incident_scan.py

# Sprint 1+3 Healthcheck [44] [45] [46]（passive_wait_healthcheck.py 跑這 3 條）
*/15 * * * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/passive_wait_healthcheck.py --check 44,45,46
```

### D.3 Verify cron 載入

```bash
crontab -l | grep -E 'replay|wave9|healthcheck'
# 期望 ≥7 行
```

---

## Phase E — Application Restart（**含 --rebuild**）

```bash
cd ~/BybitOpenClaw/srv
bash helper_scripts/restart_all.sh --rebuild  # **必加 --rebuild** 載入新 Rust binary + PyO3
```

預期：
- engine PID 換新（cargo build 過後新 binary）
- uvicorn 重啟載入新 routes（governance_lease_bridge / ipc_client / replay_routes）
- pipeline_bridge 重連 IPC（含 lease facade）

### E.1 Verify restart 成功

```bash
# Engine alive
ps aux | grep openclaw_engine | grep -v grep

# Uvicorn alive
ps aux | grep uvicorn | grep -v grep

# Engine watchdog
python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status
# 期望：engine_alive: true / status: healthy
```

---

## Phase F — 5 e2e Smoke Tests

> 重點：驗 Sprint 1 解封的 spawn argv schema 真實在 Linux 跑通 + Decision Lease feature flag default OFF 0 行為改動

### F.1 Replay Manifest Health（Sprint 1 Track B 驗）

```bash
curl http://localhost:8000/api/v1/replay/health/signature
# 期望：{"signature_check": "PASS", "key.hex_present": true}
```

### F.2 Replay Run（Sprint 1 Track A spawn argv 解封驗）

```bash
# 用 fixture manifest 跑一條
curl -X POST http://localhost:8000/api/v1/replay/run \
  -H "Content-Type: application/json" \
  -d '{"manifest_path": "fixtures/sample_manifest.json", "actor_id": "operator_smoke"}'
# 期望：{"run_id": "...", "status": "running", "subprocess_pid": <真實 pid>}

# Verify replay_runner subprocess 真起來（不再是 fake-success status='running' 但 process 已 exit）
ps aux | grep replay_runner | grep -v grep
# 期望：1 個 process alive

# 等 ~30s 看完成狀態
curl http://localhost:8000/api/v1/replay/status/<run_id>
# 期望：status='done' + V045 row 存在 + V046 artifact 存在
```

### F.3 Wave 6 Advisory Chain（V043 mlde_replay_veto_log 寫入驗）

```bash
# 觸發一次 advisory cycle（具體路徑按 dream_engine schedule）
psql -d openclaw -c "SELECT COUNT(*) FROM replay.mlde_replay_veto_log WHERE created_at > NOW() - INTERVAL '1 hour';"
# 期望：≥1 row（advisory 真寫）
```

### F.4 Wave 8 Typed-Confirm Handoff（V044 idempotency 驗）

```bash
# operator 跑一次 demo handoff（typed confirm `HANDOFF <experiment_id>`）
# 略具體 UI 步驟，從 Paper Tab → Bounded Demo Handoff modal
# 完成後 verify
psql -d openclaw -c "SELECT COUNT(*) FROM replay.handoff_requests WHERE created_at > NOW() - INTERVAL '1 hour';"
# 期望：≥1 row
```

### F.5 Wave 9 KPI Cron First Run（V047/V048 寫入驗）

```bash
# 等 06:00 UTC（cron schedule）OR 手動觸發
python3 helper_scripts/cron/wave9_business_kpi_collector.py
psql -d openclaw -c "SELECT COUNT(*) FROM replay.business_kpi_snapshots;"
# 期望：≥1 row（cron 第一次跑寫進）

python3 helper_scripts/cron/wave9_audit_incident_scan.py
psql -d openclaw -c "SELECT COUNT(*) FROM replay.audit_incident_summaries;"
# 期望：≥1 row（如有 high-severity audit incident，否則 0）
```

**Phase F 完成標誌**：F.1-F.5 都 PASS，Sprint 1 Track A 「spawn argv broken」根因真實解封。

---

## Phase G — Decision Lease Retrofit Verify（**flag default OFF 期間驗 facade 在但 0 enforce**）

```bash
# G.1 Lease facade 真在 governance_core
psql -d openclaw -c "SELECT COUNT(*) FROM learning.lease_transitions WHERE created_at > NOW() - INTERVAL '24 hours';"
# 期望（flag OFF 期間）：可以 0（router gate short-circuit）
# 期望（flag ON 後 24h）：≥1 row（amendment AC-1）

# G.2 Engine_mode tag 真實 emit（HIGH-1 retrofit Option C-improved 驗）
psql -d openclaw -c "SELECT DISTINCT engine_mode FROM learning.lease_transitions;"
# 期望：含 'live_demo' / 'live' / 'paper' / 'demo'（不再永遠 'demo'）

# G.3 healthcheck [44] [45] [46]
python3 helper_scripts/db/passive_wait_healthcheck.py --check 44 --verbose
# [44] check_replay_manifest_key_presence: PASS（key.hex 存在）
python3 helper_scripts/db/passive_wait_healthcheck.py --check 45 --verbose
# [45] check_replay_run_state_failed_rate: WARN/PASS（V042 archive land 前 100% failed 是 expected）
python3 helper_scripts/db/passive_wait_healthcheck.py --check 46 --verbose
# [46] check_lg234_frontend_stability: 0 record（LG-2/3/4 frontend 0% IMPL）
```

---

## Phase H — Sprint 4 14d Gradient Observation 起算

### H.1 記錄 window start ts

```bash
echo "REF-20 Sprint 4 14d gradient observation window start: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> docs/execution_plan/2026-05-03--ref20_wave9_pm_sign_off_template.md
git add docs/execution_plan/2026-05-03--ref20_wave9_pm_sign_off_template.md
git commit -m "chore(ref20): start 14d gradient observation window"
git push origin main
```

### H.2 Wave 9 cron 自動跑 14 天

期望（每天累積）：
- 14d 0 trading.* WHERE source LIKE 'replay_%'（amendment §12 #14 replay_no_live_mutation continuous）
- 14d 0 high-severity governance_audit_log incident
- Daily KPI snapshot 完整（V047 + V048 row）

### H.3 14 天後 Wave 9 PM sign-off 7-item checklist

per [`2026-05-03--ref20_wave9_pm_sign_off_template.md`](2026-05-03--ref20_wave9_pm_sign_off_template.md)：

1. ✅ Wave 1-8 closed（已完）
2. ✅ V### migrations applied（Phase B 完）
3. ✅ Decision Lease retrofit AMD-2026-05-02-01 deploy verified（flag default OFF accept-in-tree；Phase 5 flip 後完整 verify）
4. ⏳ 14d replay_no_live_mutation 0 violation（Phase H 採集中）
5. ⏳ 14d governance_audit_log 0 high-severity incident（Phase H 採集中）
6. ⏳ Business KPI 7d/14d snapshot 完整（Phase H 採集中）
7. ✅ E2 + E4 + MIT + FA + QA review sign-off（Sprint 1+2+3 全 chain）

完成 7/7 → REF-20 P6 closure 簽章 + Sprint 4 close。

---

## Rollback Plan（任何 Phase fail）

### 通用 rollback

1. **Phase B fail**：每個 V### migration 各自設計為 forward-only ALTER；如 V0XX fail 後續 V0XX+1 不能跑。手動 fix V0XX SQL 後重跑（idempotent 設計，不會 RAISE 第二次）。

2. **Phase C cargo build fail**：
   ```bash
   cd ~/BybitOpenClaw/srv/rust && cargo clean && cargo build --release  # 完整重建
   ```

3. **Phase E restart fail**：
   ```bash
   bash helper_scripts/clean_restart.sh  # 清 socket + flag + 重啟
   ```

4. **Phase F e2e smoke fail（spawn argv 仍 broken？）**：
   - Verify Track A E1 修補真在 dbcf845b commit：`git show dbcf845b -- program_code/.../replay/route_helpers.py | grep 'manifest <fixture'`
   - 如不在 → ssh trade-core git pull 漏（重 pull）
   - 如在 → 退回 PM dispatch E1 follow-up 看 Linux runtime 行為差異

5. **Phase G Decision Lease retrofit failed**（如真有 P0-GOV-1 retrofit 行為異常）：
   - flag 默認 OFF，0 行為改動，**不需 rollback**
   - 等 P0-EDGE-2 結論後再 flip flag canary 24h

---

## 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | PM | Sprint 3 Track I deploy runbook v1；含 Sprint 1+2+3 cumulative deploy 步驟 + Track H Decision Lease retrofit feature flag 灰度 + V054 hypertable + 19 V### migration 順序 |

---

## Cross-References

- **Sprint 1 unified commit**：`edf33c0`（5 P0 security + V049-V053）
- **Sprint 2 deliverables**：`aa9343c` + `5184990` + `ab25a2a`...`984ee5d` + `35c07190` + `114f681c`
- **Sprint 3 Track H**：`dbcf845b`（Decision Lease retrofit + V054）
- **AMD-2026-05-02-01**：`docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- **AMD-2026-05-03-01**：`docs/governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md`
- **PA Sprint 2 Track E partition design**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md`
- **Wave 9 PM sign-off template**：`docs/execution_plan/2026-05-03--ref20_wave9_pm_sign_off_template.md`
- **舊 final closure deploy guidance**：`docs/execution_plan/2026-05-03--ref20_final_closure_and_deploy_guidance.md`（取代）

**Track I IMPL phase complete in tree.** Operator 親手執行 Phase A-H 後 Sprint 4 14d gradient observation 自動起算。
