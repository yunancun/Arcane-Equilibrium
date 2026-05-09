# C-A6 Runtime Apply Checklist — DSR/PBO Evidence Pipeline

**Status**：source/test CLOSED 2026-05-09；**runtime apply PENDING**（operator authorize 後執行）
**Owner**：E1-D Day 5-7 W2（task b — source-side only，**不執行 ops apply**）
**Reference**：`P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON`（TODO §10 + §11）
**AMD source**：4-agent v3 BB session（QC/FA/MIT 共識，DSR penalty quantification 由 W-AUDIT-6d mid-G 6 polishing #6 land）
**Local commit base**：`26b7186d`（HEAD; W1 Sprint N+0 first-pass closure）
**Date**：2026-05-09

---

## 1. Source/Test Closure 確認 / Source Closure Verification

本次 sub-agent 任務 **不再做** source/test 改動。以下三項 land 狀態屬 prior commit；本任務僅做 verification 與 runtime apply checklist 撰寫，0 mutation。

| Item | Land Status | Verify |
|---|---|---|
| V079 migration | source land；DB **PENDING** apply（max=78） | `git log --oneline sql/migrations/V079__promotion_evidence_trial_ledger.sql` |
| `program_code/ml_training/promotion_evidence.py` | IMPL ready | `python3 -m pytest program_code/ml_training/tests/test_promotion_evidence.py -v` 4 passed |
| V079 migration tests | passing | `python3 -m pytest tests/migrations/test_v079_promotion_evidence_trial_ledger.py -v` 2 passed |
| `edge_estimator_scheduler._run_promotion_evidence_push()` | IMPL wired (line 600-640) | `grep -n promotion_evidence edge_estimator_scheduler.py` 8 命中 |

**Mac local pytest 6 passed (re-verified 2026-05-09 by E1-D W2 task b)**：
```
tests/migrations/test_v079_promotion_evidence_trial_ledger.py::test_v079_adds_promotion_evidence_report_columns PASSED
tests/migrations/test_v079_promotion_evidence_trial_ledger.py::test_v079_creates_strategy_trial_ledger_for_persisted_trial_sharpes PASSED
program_code/ml_training/tests/test_promotion_evidence.py::test_build_strategy_promotion_evidence_uses_real_raw_series PASSED
program_code/ml_training/tests/test_promotion_evidence.py::test_push_updates_gate_with_trial_sharpes_and_pbo_returns PASSED
program_code/ml_training/tests/test_promotion_evidence.py::test_push_without_stress_exposure_is_honest_fail_closed_not_fake_pass PASSED
program_code/ml_training/tests/test_promotion_evidence.py::test_push_persists_trial_ledger_and_reports_when_v079_exists PASSED
```

---

## 2. V079 Schema Summary（不重述全文）

**Migration**：`sql/migrations/V079__promotion_evidence_trial_ledger.sql`

兩動作（idempotent additive only）：
1. `ALTER TABLE learning.promotion_pipeline ADD COLUMN IF NOT EXISTS demo_selection_bias_report JSONB`
2. `ALTER TABLE learning.promotion_pipeline ADD COLUMN IF NOT EXISTS demo_tail_risk_report JSONB`
3. `CREATE TABLE IF NOT EXISTS learning.strategy_trial_ledger (...)` — append-only audit table for trial Sharpes
4. `CREATE INDEX idx_strategy_trial_ledger_strategy_mode_ts` + `idx_strategy_trial_ledger_family_ts`

**0 destructive ops**（per CHECK constraint + IF NOT EXISTS guards）。

**Audit chain**：
- promotion_evidence push → `learning.promotion_pipeline.demo_selection_bias_report` / `demo_tail_risk_report` (JSONB)
- 每次 cycle 寫一筆 → `learning.strategy_trial_ledger`（observed_sharpe / n_observations / candidate_key / source）

---

## 3. Pipeline Wiring（已 land，0 改動）

`edge_estimator_scheduler._run_promotion_evidence_push(mode, js_results)` 流程：
1. **Mode gate**：僅 `demo` engine_mode 觸發 push（line 611 `demo_only_promotion_evidence` early-return）
2. **Lazy import**：`from ml_training.promotion_evidence import push_promotion_evidence_from_js_results`
3. **Real-series source**：James-Stein shrinkage edge series + realized strategy candidate returns
4. **Side-effect controlled**：
   - `update PromotionGate` when injected
   - persist `learning.promotion_pipeline.{demo_selection_bias_report, demo_tail_risk_report}`
   - persist `learning.strategy_trial_ledger` row per cycle
5. **No mutation**：trading params / auth / order / live-mode 全 0 改動

**Cron schedule**：edge_estimator_scheduler 每小時 cycle（leader-elected via `flock $OPENCLAW_DATA_DIR/edge_scheduler.lock`，uvicorn --workers 4 single-leader 強制）。

---

## 4. Runtime Apply Steps（**operator authority — 不在本 sub-agent scope**）

> 以下步驟為 operator 執行清單；本 sub-agent **不執行** ops apply（per task spec）。

### 4.1 V079 apply（Linux runtime）

```bash
# Step 1：on Linux trade-core，apply V079 migration via auto-migrate env-gate
# 步驟 1：Linux trade-core 上，由 auto-migrate env-gate apply V079
ssh trade-core "cd ~/BybitOpenClaw/srv && \
    OPENCLAW_AUTO_MIGRATE=1 bash helper_scripts/restart_all.sh --keep-auth --rebuild"
```

**操作說明**：
- `OPENCLAW_AUTO_MIGRATE=1`：opt-in env var；engine 啟動時 DbPool 連線後 + writer 啟動前呼叫 `MigrationRunner::run_if_enabled()` 跑 sqlx migrate
- `--keep-auth`：保留現有 LiveDemo authorization（避免 session reset）
- `--rebuild`：重建 engine binary + PyO3，確保 Rust V079 hash 對齊

### 4.2 Verify migration applied

```bash
# Step 2：on Linux，via psql 驗 _sqlx_migrations 表 max ≥ 79
# 步驟 2：Linux 上 psql 驗證
ssh trade-core "docker exec openclaw-postgres psql -U postgres -d openclaw -c \
    \"SELECT max(version) FROM _sqlx_migrations\""

# 預期輸出 / Expected output:
# max
# -----
#    79
# (1 row)
```

### 4.3 24h cron fire 驗證 → `[Xc] ml_training_cron_active` PASS

```bash
# Step 3：24h 後驗 cron 已 fire + edge_estimator_scheduler 真寫入
# 步驟 3：24h 後驗 cron 已 fire + edge_estimator_scheduler 真寫入

# 3a：strategy_trial_ledger 有 row
ssh trade-core "docker exec openclaw-postgres psql -U postgres -d openclaw -c \
    \"SELECT count(*) AS rows, max(ts) AS last_push \
      FROM learning.strategy_trial_ledger\""

# 3b：promotion_pipeline 有 demo_selection_bias_report
ssh trade-core "docker exec openclaw-postgres psql -U postgres -d openclaw -c \
    \"SELECT strategy_name, \
             demo_selection_bias_report IS NOT NULL AS has_dsr_report, \
             demo_tail_risk_report IS NOT NULL AS has_tail_risk_report \
      FROM learning.promotion_pipeline \
      ORDER BY strategy_name\""

# 3c：[Xc] ml_training_cron_active healthcheck PASS
ssh trade-core "cd ~/BybitOpenClaw/srv && \
    bash helper_scripts/db/passive_wait_healthcheck.sh"
```

**期望成功標誌 / Expected success marker**：
- `learning.strategy_trial_ledger` rows ≥ 1（24h 內至少 1 cycle 寫入）
- `learning.promotion_pipeline.demo_selection_bias_report IS NOT NULL` for ≥ 1 strategy
- `learning.promotion_pipeline.demo_tail_risk_report IS NOT NULL` for ≥ 1 strategy
- passive_wait_healthcheck `[Xc] ml_training_cron_active` 返回 PASS（cron 24h 內已 fire）

### 4.4 Failure rollback

如 step 4.1 後 engine 啟動失敗 → fall back：
```bash
# unset auto-migrate + manual apply via 老路徑
ssh trade-core "cd ~/BybitOpenClaw/srv && \
    unset OPENCLAW_AUTO_MIGRATE && \
    bash helper_scripts/linux_bootstrap_db.sh --apply && \
    bash helper_scripts/restart_all.sh --keep-auth"
```

---

## 5. Acceptance Criteria（runtime apply 完成判據）

| # | Criterion | How to verify |
|---|---|---|
| 1 | V079 schema applied | `_sqlx_migrations` max ≥ 79 |
| 2 | `learning.strategy_trial_ledger` table exists | `to_regclass('learning.strategy_trial_ledger') IS NOT NULL` |
| 3 | `learning.promotion_pipeline` 兩 JSONB 欄位 added | `information_schema.columns WHERE column_name IN ('demo_selection_bias_report','demo_tail_risk_report')` row=2 |
| 4 | edge_estimator_scheduler 真寫入 | `learning.strategy_trial_ledger` row growth 每 cycle +1（小時 cron） |
| 5 | promotion_evidence push fired | `learning.promotion_pipeline.demo_selection_bias_report IS NOT NULL` ≥ 1 strategy |
| 6 | `[Xc] ml_training_cron_active` PASS | passive_wait_healthcheck.sh 返 0 + 該 line 標 PASS |

**Tier**：source/test = 70%；runtime apply 後 = 100%。

---

## 6. PM Follow-up Flag

**警示**：本 sub-agent task **嚴格 source-side only**：
- 未執行 V079 apply
- 未執行 cron install
- 未執行 engine restart
- 0 DB modification
- 0 ops mutation

ops 動作 (4.1 / 4.2 / 4.3) 待 operator separately authorize。本 task acceptance 僅含：
- (a) `[58]` healthcheck IMPL + pytest PASS（13/13）
- (a) `[58]` 已加入 passive_wait_healthcheck.py active list
- (b) C-A6 runtime apply checklist 文件 land
- (b) source/test 仍綠（V079 + promotion_evidence 6 passed re-verified）

---

## 7. 驗證 0 DB Modification

本 sub-agent 跑過命令清單（純 read / mock pytest）：
- `grep` / `find` / `wc` — read-only filesystem ops
- `python3 -m pytest helper_scripts/db/test_canary_stage_invariant_healthcheck.py` — mock cursor，無 DB connect
- `python3 -m pytest tests/migrations/test_v079_promotion_evidence_trial_ledger.py` — psycopg2 import test，**未** connect Linux PG（Mac 無 PG service）
- `python3 -m pytest program_code/ml_training/tests/test_promotion_evidence.py` — 純 unit test，無 DB
- `python3 -c "from helper_scripts.db.passive_wait_healthcheck import runner"` — import test，無 DB
- `python3 -m helper_scripts.db.passive_wait_healthcheck --help` — argparse only，無 DB

**0 PG connection / 0 INSERT/UPDATE/DELETE / 0 DDL 提交**。

---

## 8. Sign-off Pointers

- `[58]` healthcheck IMPL：
  - `helper_scripts/db/passive_wait_healthcheck/checks_canary_stage_invariant.py` (425 LOC)
  - `helper_scripts/db/passive_wait_healthcheck/runner.py` (3 hunks added: import + cursor invocation + 2 description blocks)
  - `helper_scripts/db/test_canary_stage_invariant_healthcheck.py` (465 LOC, 13 unittest cases)

- C-A6 runtime apply checklist：
  - 本文件 `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--c_a6_runtime_apply_checklist.md`

- 待 E2 review → E4 regression → PM 統一 commit + push origin（per CLAUDE.md §七 強制鏈）。
