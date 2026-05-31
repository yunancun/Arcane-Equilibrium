# MIT V104 真檔 Gate 2b Idempotency Double-Apply Dry-Run

**Date**: 2026-05-30
**Trigger**: P0-LG-3 部署前強制 gate；E1-T4 寫出 V104 真檔（branch `feature/lg3-t4` @ `45a23068`，worktree `/tmp/wt-lg3t4`），規則「真檔必須重跑 dry-run，不可沿用 2026-05-27 candidate 9/9」
**Method**: ssh trade-core → docker exec trading_postgres psql -U trading_admin -d trading_ai；全程 BEGIN/ROLLBACK 絕不 COMMIT
**Real file**: `sql/migrations/V104__supervised_live_audit.sql` 416 LOC / sha256 `afceb98e9baf80a4a73e9aa4862f72a13e0bbb3a1ad5e91dde85e95f6e1ce39f`（local + PG container 逐 byte 一致）
**PG**: PostgreSQL 16.11 (aarch64) / TimescaleDB present

---

## 結論先行：APPROVE（含 1 個已自我清理的 dry-run 衛生事故記錄 + 1 個 deferred cross-branch check）

V104 真檔 Gate 2b idempotency double-apply **0 RAISE / 0 ERROR / 0 EXCEPTION**，兩個 round 全 NOTICE-skip，"all guards PASS" ×2。9-query reflection 9/9 PASS。drift 防護 PASS（只新增 V104，未動任何既有 migration）。Guard A 三段全部 empirical 驗證有效（part 1 missing-prereq RAISE / part 2 column-count-drift RAISE / part 3 forbidden-ML-column detection 邏輯正確）。`_sqlx_migrations` max 仍 = 115 未污染，prod 還原至 pre-audit 精確狀態。

**V104 真檔可進部署。**

兩個非阻塞註記（見 §6）：
1. **dry-run 衛生事故（已清理）**：Guard A part 1 negative test 因 script 漏 `\set ON_ERROR_STOP on`，RENAME governance_audit_log 自動 commit 洩漏 `governance_audit_log_tmp_mit`（空表 0 row）；已用 guarded DO-block 安全 drop，prod 還原。**這是 MIT 測試手法 bug，不是 V104 缺陷**。
2. **cross-branch 一致性 check（item 3）DEFERRED**：T1 的 `SmAction.as_str()` 17 值源碼**目前不存在於任何 ref**（lg3-t1 branch tip = base，wt-lg3t1 工作樹無 SmAction / 無 enum string / test `sm_action_strings_match_v104_check_enum` 找不到）。SQL 端逐字比對無 T1 對照物可比。V104 的 17-enum 已被提取為 canonical baseline 供 T1 落地後核對。

---

## §1 真檔 provenance 確認（非 candidate）

| 項 | 值 |
|---|---|
| branch | `feature/lg3-t4` |
| commit | `45a23068` "LG-3 T4: V104 supervised_live_audit migration (real file)" |
| worktree | `/tmp/wt-lg3t4` |
| LOC | 416 |
| sha256（local） | `afceb98e9baf80a4a73e9aa4862f72a13e0bbb3a1ad5e91dde85e95f6e1ce39f` |
| sha256（PG container copy） | `afceb98e...`（逐 byte 一致）|
| base 是否已有 V104 | **ABSENT**（`git cat-file -e cc6c54d0:...V104 = ABSENT`，與 PA reality-check 一致）|

header line 11 自述「MIT 2026-05-27 dry-run（手寫 candidate）... 本檔為真檔，待 MIT Gate 2b 重跑」— 確認本次審的是真檔。

## §2 Drift 防護（item 4）— PASS

`git diff cc6c54d0 feature/lg3-t4 -- sql/migrations/`：
```
A	sql/migrations/V104__supervised_live_audit.sql
1 file changed, 416 insertions(+)
```
**只新增 V104，0 既有 V0xx/V1xx 被改**。base 既有 V100/101/102/103/105/106/107/108/109/110 — V104 是 V103↔V105 之間的 free hole（sqlx 按 version sort 補洞合法，不觸發既有 checksum drift）。**無 BLOCKER**。

## §3 Idempotency Double-Apply（item 2 核心 load-bearing gate）

### 3a. baseline（Q1）— 重要發現：table 已存在於 prod
```
sqlx_max=115 / count=105
V104_in_sqlx=ABSENT（V104 未註冊到 sqlx）
V103=t / V105=t（free hole 確認）
lease_transitions=true / governance_audit_log=true（Guard A part1 prereq 滿足）
timescaledb=true
supervised_live_audit=true ← table 已實體存在（21 col / 4 CHECK / hypertable / 6 idx / comp+ret job / 0 row）
```
解讀：V104 schema **先前已手動 apply**（`psql -f` 路徑，未走 sqlx），故 sqlx 註冊缺。這使本 dry-run 成為最嚴格的「re-apply against fully-built schema」測試。為涵蓋 CREATE path，另跑 fresh-path（drop-in-tx + double-apply）。

### 3b. Existing-path double-apply（BEGIN → V104 ×2 → ROLLBACK）
- Round 1：NOTICE relation already exists, skipping（CREATE TABLE / CREATE INDEX）+ create_hypertable already a hypertable + compression/retention already present + **all guards PASS**
- Round 2：完全相同 NOTICE-skip + **all guards PASS**
- `grep -icE "ERROR|EXCEPTION|FATAL" = 0` / `all guards PASS = 2` / ROLLBACK done

### 3c. Fresh-path double-apply（BEGIN → DROP CASCADE → V104 ×2 → ROLLBACK）
- Round 1（CREATE path）：`CREATE TABLE`×1 + `CREATE INDEX`×4 + "enabled compression (segmentby=session_id)" + "added compression policy (30 days)" + "added retention policy (90 days)" + **all guards PASS**
- Round 2（freshly-created 上 re-apply）：NOTICE already exists skipping + "compression already enabled; skipping" + "compression policy already present; skipping" + "retention policy already present; skipping" + **all guards PASS**
- `grep -icE "ERROR|EXCEPTION|FATAL" = 0` / `all guards PASS = 2`
- 唯一 WARNING：`column "event_id" should be used for segmenting or ordering` — TimescaleDB informational hint，V104 header line 44-45 已記載，segmentby=session_id 是 LG-3 hot-read 正確設計，**非 error**。

**Gate 2b verdict：double-apply 兩路徑均 0 RAISE，全 NOTICE-skip，V083/V084 NOTICE-skip gold standard 一致 → IDEMPOTENT PASS。**

## §4 9-Query Reflection（fresh-applied 狀態，BEGIN/ROLLBACK）

| # | 驗項 | 期望 | 實測 | Verdict |
|---|---|---|---|---|
| Q1 | column count | 21 | col_count=21 | PASS |
| Q2 | CHECK constraint | 4（action/result/engine_mode/ts_ms）| check_count=4，4 conname 全在 | PASS |
| Q3 | action enum | 17 | action_enum_n=17 | PASS |
| Q4 | hypertable 7d chunk | 604800000000 µs | chunk_interval_us=604800000000 | PASS |
| Q5 | compression segmentby | session_id | segmentby=session_id | PASS |
| Q6 | compression policy | 30 days | comp_after=30 days | PASS |
| Q7 | retention policy | 90 days | drop_after=90 days | PASS |
| Q8 | 4 named index | 4 | named_idx_n=4 | PASS |
| Q9 | forbidden ML col | 0 | forbidden_ml_col_n=0（non-training surface invariant 達成）| PASS |
| — | table FQN | learning.supervised_live_audit | table_fqn=learning.supervised_live_audit | PASS |

**9/9 PASS。**

## §5 Guard A 三段有效性（item 2 子項，empirical negative test）

| Guard | 測法 | 結果 | Verdict |
|---|---|---|---|
| A part 1（prereq）| tx 內 RENAME governance_audit_log away 後 apply | `ERROR: V104 Guard A part 1: prerequisite missing (lease_transitions=true / governance_audit_log=false)` + ROLLBACK | RAISE 有效 |
| A part 2（21-col allowlist）| tx 內 CREATE 22-col 表後 apply | `ERROR: V104 Guard A part 2: column count = 22 (expected 21). Schema drift detected.` | RAISE 有效（fail-loud 最早攔截）|
| A part 3（forbidden ML col）| 直接驗 detection SQL（21-col 含 signal_id）| `A3_detects_forbidden=signal_id`（→ IF v_forbidden IS NOT NULL RAISE）| 偵測邏輯正確 |

Guard A part 2 在 column-count 不符時最早 RAISE（22≠21），故 part 3 在 count-drift 場景被遮蔽（正確的 fail-loud 排序）；part 3 detection SQL 已以 isolated logic test 證明能捕捉 signal_id/ml_label/training_label/feature_vector。Guard C 的 4-CHECK + action-17-enum + hypertable + 4-index 後驗在每個 round 末以 "all guards PASS" NOTICE 證明通過。

4 CHECK constraint 逐字（PG existing table，與真檔 byte 對照一致）：
- action：17-enum 同序（request_registered ... session_closed）
- result：(ok, rejected, forced)
- engine_mode：(live, live_demo) — 拒 paper（LiveDemo 不降級硬邊界）
- ts_ms > 0

## §6 兩個非阻塞註記

### 6a. dry-run 衛生事故（自我造成，已清理）
Guard A part 1 negative test 的 script 漏 `\set ON_ERROR_STOP on`，`RENAME learning.governance_audit_log TO governance_audit_log_tmp_mit` 在 V104 RAISE 前被自動 commit，洩漏空表 `governance_audit_log_tmp_mit`（0 row / 1 idx）。real governance_audit_log 同時存在（0 row / 2 idx，完整）。已用 guarded DO-block（驗 real 存在 + tmp 為 0 row 才 drop）安全 drop。
post-cleanup 最終驗：`gov_tmp_leaked=f` / `any_mit_leak_tables=NONE` / `gov_real_exists=t` / `gov_real_idx_n=2` / `gov_real_rows=0`。**prod 還原至 pre-audit 精確狀態，無殘留。**
**這是 MIT 測試手法 bug（負向 Guard test 改 prod prereq 表必須包 savepoint + ON_ERROR_STOP；更佳是純 to_regclass 邏輯測不動真表），不是 V104 缺陷。**

### 6b. cross-branch 一致性（item 3）DEFERRED — T1 SmAction 源碼不存在
- `lg3-t1` branch tip == base（`cc6c54d0..feature/lg3-t1` 無 commit）
- wt-lg3t1 工作樹：`grep SmAction / request_registered / sm_action_strings_match_v104` 全 0 hit
- main HEAD：同樣 0 hit
→ T1 的 `SmAction.as_str()` 17 值與 test 目前尚未落地任何 ref；SQL 端逐字比對**無對照物**。
V104 canonical 17-enum baseline（供 T1 落地後核對，順序即 as_str() 必須輸出順序）：
```
request_registered, approval_granted, approval_rejected, expired_pre_auth,
auth_file_observed, auth_file_invalid, lease_acquired, lease_released,
auth_recheck_fail, drawdown_breach, drawdown_close_complete, kill_api,
kill_ipc, session_max_duration, reconcile_force_close,
illegal_transition_attempted, session_closed
```
**建議**：T1 IMPL DONE 時，MIT 重跑 item 3 逐字比對；T1 自帶 test `sm_action_strings_match_v104_check_enum` 是必要但不充分（MIT 仍須 SQL 端獨立 cross-check）。

## §7 _sqlx_migrations 未污染最終確認
| 時點 | max | count | V104 registered |
|---|---|---|---|
| dry-run 前 | 115 | 105 | ABSENT |
| 全部 round + negative test + cleanup 後 | 115 | 105 | ABSENT |

V104 正式 apply 是 deploy 時 sqlx 的事（count → 106，max 仍 115，version-sort 補洞）。
**sqlx checksum drift 提醒**（per `project_2026_05_02_p0_sqlx_hash_drift`）：因 supervised_live_audit table 已手動先建（sqlx 未註冊），deploy 時 `OPENCLAW_AUTO_MIGRATE=1` 走 sqlx 會把 V104 註冊；V104 SQL 全 idempotent（已驗）→ apply 安全 NOTICE-skip。**若 V104 file 在本 dry-run 後又被 edit，必跑 `bin/repair_migration_checksum --target V104`。**

---

**Sign-off**: MIT V104 真檔 Gate 2b **APPROVE** — double-apply 0 RAISE / 9-query 9/9 PASS / drift 防護 PASS / Guard A 三段有效 / prod 未污染。
**Pending（非阻 V104 部署）**: item 3 cross-branch SmAction 比對待 T1 落地後重跑。

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-30--v104_real_file_gate2b_dry_run.md
