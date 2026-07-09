# REF-20 Wave 3 R20-P2a-S4 — DB role REVOKE/GRANT 3-PR sequence + verify_replay_evidence_and_insert PL/pgSQL

**日期 / Date：** 2026-05-03
**Owner：** E1 (sub-agent, Wave 3 batch 3A parallel S4 task)
**契約上游 / Upstream contract：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 3 R20-P2a-S4 row + §7.1 風險 #3
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G3/G4/G5 + §4.2 #4
- `sql/migrations/REF-20_RESERVATION.md` V036 / V037
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_insert_paths_grep.md` (P0-T6 surgical change list)

**Mode：** WRITE (file artifacts only); 0 actual REVOKE / GRANT 在 Mac dev env 執行；deploy 由 operator 在 Linux trade-core 手動完成。
**Mode (EN):** WRITE (file artifacts only); zero actual REVOKE/GRANT executed on Mac dev env; deploy is operator-driven on Linux trade-core.

---

## 0. TL;DR

- V036 + V037 SQL migration 檔產出 (含 Guard A 驗證 + 雙語注釋 + idempotent re-run safe)
- 4 producer code 全切換到 `learning.verify_replay_evidence_and_insert()`：dream_engine / opportunity_tracker / mlde_shadow_advisor / mlde_demo_applier
- 4 producer Python AST compile clean; 0 直接 INSERT 殘留
- 12 pytest cases (10 PASSED in mock-mode + 2 SKIPPED via env-gate live PG path)
- LG-5 §2.1 schema_version payload 路徑 + 27 row engine_mode='live' audit trail 全保留 (HIGH risk producer #4 mlde_demo_applier)
- 0 SECURITY DEFINER (V3 §4.2 #4 禁) — function 為 SECURITY INVOKER
- V038-V040 (sibling sub-agent S6 task) 已 landed；本 S4 task 不重複作業域
- E2 + E3 + MIT + FA review-ready

---

## 1. 任務摘要 / Task summary

PM dispatched Wave 3 Batch 3A (4 parallel)。S4 對 `learning.mlde_shadow_recommendations` 寫入路徑加 verified function gate + REVOKE INSERT FROM PUBLIC，防止任何不經 verified function 的 INSERT。

**3-PR sequence (V3 §4.2 #4 + §3 G5 + workplan §7.1 風險 #3 嚴格要求拆 3 PR 防止 break live demo write)：**

| PR# | 內容 | 本 task 交付 | 部署位置 |
|---|---|---|---|
| **PR1** | V036 verify_replay_evidence_and_insert function + GRANT EXECUTE | ✅ V036 file artifact | Linux trade-core operator deploy |
| **PR2** | 4 producer code 切換 | ✅ 同 commit 內 (與 V036 一起) | code deploy via restart_all |
| **PR3** | V037 REVOKE INSERT FROM PUBLIC | ✅ V037 file artifact | Linux trade-core operator deploy (PR2 deploy + 驗證後) |

本 task 一次性交付 V036 + V037 + 4 producer 切換；**0 actual REVOKE 在 Mac dev env 執行**；執行時序由 operator 控制。

---

## 2. 修改清單 / File changes

### 2.1 V036 / V037 SQL migration

| File | 行數 | 用途 |
|---|---:|---|
| `sql/migrations/V036__replay_evidence_source_guard.sql` | 354 | NEW — verify function (PL/pgSQL SECURITY INVOKER) + Guard A + GRANT EXECUTE TO PUBLIC + replay_writer_role |
| `sql/migrations/V037__replay_evidence_revoke_public_insert.sql` | 221 | NEW — REVOKE INSERT FROM PUBLIC + GRANT INSERT TO replay_writer_role + REVOKE EXECUTE FROM PUBLIC + post-deploy verification |

### 2.2 4 producer code 切換

| File | Line range | Change | Risk |
|---|---|---|---|
| `program_code/local_model_tools/dream_engine.py` | 343-403 | direct INSERT → verified function call + try/except wrap + per-row reject log | LOW |
| `program_code/local_model_tools/opportunity_tracker.py` | 230-282 | direct INSERT → verified function call + try/except wrap + global reject log | LOW |
| `program_code/ml_training/mlde_shadow_advisor.py` | 296-365 | direct INSERT → verified function call + per-row reject log（保留 rec.source/rec.recommendation_type/rec.engine_mode 變量） | MEDIUM |
| `program_code/ml_training/mlde_demo_applier.py` | 1188-1276 | direct INSERT → verified function call（保留 hardcoded 'live' engine_mode + 'ml_shadow' source + LG-5 §2.1 schema_version payload） | HIGH |

### 2.3 Test fixture

| File | 行數 | 用途 |
|---|---:|---|
| `tests/migrations/test_v036_v037_replay_evidence_guard.py` | 482 | NEW — 12 test cases (10 mock-mode PASSED + 2 live PG SKIPPED) |

### 2.4 Ledger update

`sql/migrations/REF-20_RESERVATION.md` — V036/V037 status 從 reserved → land 2026-05-03 (E1 sub-agent)；revision history append v1.1。

---

## 3. 關鍵 diff / Key change rationale

### 3.1 V036 verified function 設計

```sql
CREATE OR REPLACE FUNCTION learning.verify_replay_evidence_and_insert(
    p_engine_mode TEXT, p_symbol TEXT, p_strategy_name TEXT, p_source TEXT,
    p_recommendation_type TEXT, p_expected_net_bps DOUBLE PRECISION,
    p_confidence DOUBLE PRECISION, p_sample_count INTEGER,
    p_payload JSONB, p_applied BOOLEAN, p_requires_governance BOOLEAN,
    p_created_by TEXT,
    p_evidence_source_tier TEXT DEFAULT 'real_outcome',
    p_replay_experiment_id TEXT DEFAULT NULL,
    p_manifest_hash TEXT DEFAULT NULL,
    p_expires_at TIMESTAMPTZ DEFAULT NULL,
    p_decision_lease_id TEXT DEFAULT NULL,
    p_context_id TEXT DEFAULT NULL,
    p_intent_id TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY INVOKER
```

**5 條 validation logic：**
1. `evidence_source_tier ∈ {real_outcome, calibrated_replay, synthetic_replay, counterfactual_replay}` — RAISE EXCEPTION on miss
2. `source ∈ {ml_shadow, dream_engine, opportunity_tracker, linucb}` — RAISE on miss (與 V031 schema CHECK 對齊)
3. real_outcome ⇒ `replay_experiment_id IS NULL AND manifest_hash IS NULL`；replay-derived ⇒ both NOT NULL (V3 §4.2 compound CHECK)
4. replay-derived row ⇒ `expires_at NOT NULL AND > now()` (manifest TTL contract)
5. INSERT ... RETURNING id (V031 既有 CHECK 自動繼承)

**為何 SECURITY INVOKER (非 DEFINER)：** V3 §4.2 #4 要求保留既有 producer 寫 real_outcome row 的合法路徑。SECURITY DEFINER 會 bypass 下層 role grant — V037 REVOKE PUBLIC INSERT 後，INVOKER 確保 caller 自己的角色是真實授權閘 (replay_writer_role 是唯一 GRANTed 給 INSERT 的角色)。

**Guard A：** function existence + arg signature 19 args 驗證 (post-CREATE) — 防 CREATE OR REPLACE 後 signature drift。

**Idempotent：** local psql -f V036 ... × 2 → CREATE OR REPLACE 再次命中相同 signature → Guard 不 RAISE。

### 3.2 V037 REVOKE / GRANT 設計

```sql
REVOKE INSERT ON learning.mlde_shadow_recommendations FROM PUBLIC;
GRANT INSERT ON learning.mlde_shadow_recommendations TO replay_writer_role;

REVOKE EXECUTE ON FUNCTION learning.verify_replay_evidence_and_insert(...) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ... TO replay_writer_role;
```

**Guard A pre-check：**
- V036 `verify_replay_evidence_and_insert` function 存在 (RAISE if missing)
- `replay_writer_role` 存在 (RAISE if missing)
- WARNING (非 RAISE)：role 0 members + PUBLIC INSERT 仍存在 → operator 可能忘了 GRANT login role

**Post-deploy verification：**
- PUBLIC 不再有 INSERT (RAISE if leak)
- replay_writer_role 確實有 INSERT (RAISE if grant 失敗)

**Idempotent：** REVOKE 在 grant 不存在時 no-op (Postgres semantics)；可 V037 重跑。

**Operator deploy 順序強制 inline 在 V037 header (PR1 + PR2 + PR3 三步)：**
1. V036 land
2. PR2: 4 producer code 切換 (operator MUST 在 V037 前 GRANT replay_writer_role TO `<producer login role>` for each producer connection role)
3. V037 land

違反順序的後果 (寫入 V037 header)：若 PR2 producer 未切換即 V037 → producer 直接 INSERT 全 fail-closed (permission denied) → live demo write 全部斷流；FUP-1 LG-5 reviewer pipeline break。

### 3.3 4 producer 切換策略

統一 pattern：
```python
try:
    cur.execute(
        "SELECT learning.verify_replay_evidence_and_insert(%s, %s, ...)",
        (...)
    )
    inserted += 1
except psycopg2.Error as exc:
    # function reject: log and continue (producer 不 crash)
    logger.warning(...)
```

**特別保留 (mlde_demo_applier HIGH risk)：**
- `engine_mode='live'` hardcoded：per V3 §4.2 P0-T7 classification + dispatch §2 #2 PM clarify，27 row 既有 `engine_mode='live'` 全屬 `evidence_source_tier='real_outcome'` legacy LG-5 audit trail，不是 replay-derived
- `source='ml_shadow'` hardcoded：LG-5 contract
- `recommendation_type='experiment_plan'` hardcoded：LG-5 contract
- `_build_live_candidate_payload` helper 注入 LG-5 §2.1 `schema_version` payload — 此 helper 邏輯不變動，本 function 不解構或重建 payload；下游 `mlde_param_applications` FK 回 `mlde_shadow_recommendations.id` 路徑保留 (sibling CC commit 463890d Lg5_review_consumer 依賴)

---

## 4. 治理對照 / Governance crosswalk

### V3 §12 acceptance binding

| # | Acceptance | 本 task 狀態 |
|---|---|---|
| **#5** evidence_tier_completeness | function 強檢 `evidence_source_tier ∈ allowlist`；real_outcome 為 default 但允許 NULL→default 路徑；NOT NULL CHECK 由 V038-V040 retrofit (sibling task) | partial — function side ready；DB side 等 V038-V040 |
| **#6** replay_source_guard | V036 function ALLOW + V037 PUBLIC REVOKE 雙閘；4 producer 全走 verified path | full — pending operator deploy |
| **#7** registry_fk dangling: 0 | function 不創 FK；FK 規則由 V038-V040 + replay schema 補完 | N/A this task |

### CLAUDE.md §七 + §九 對照

| 規則 | 本 task 對應 |
|---|---|
| 跨平台 (路徑不硬編碼) | ✅ 0 `/Users/...` 或 `/home/ncyu/...`；grep clean |
| 雙語注釋 | ✅ V036 / V037 / 4 producer / test 全中英對照；MODULE_NOTE 模式（function COMMENT 中英；inline 中英） |
| SQL migration Guard A/B/C | ✅ V036 Guard A (function + arg signature)；V037 Guard A (V036 prereq + role + post-deploy verify)；Guard B/C N/A (無 ALTER COLUMN / 無 hot-path index) |
| Idempotent | ✅ V036 CREATE OR REPLACE；V037 REVOKE no-op semantics |
| Singleton 登記 | N/A — 本 task 無新 singleton |
| Sign-off git status clean | task report 寫入後 commit 前由 PM 驗 |

### 硬約束（CLAUDE.md §四 + §三 18 blocker）

- max_retries / live_execution_allowed / execution_authority / system_mode：**0 動**
- LG-5 §2.1 schema_version：**保留 verbatim**（mlde_demo_applier `_build_live_candidate_payload` 路徑 0 變動）
- ws_client / ipc_server / live_authorization import：**0 import 新增**
- SECURITY DEFINER：**0 使用** (V3 §4.2 #4 禁)
- live demo write 寫入路徑：本 PR 不 break (PR1 + PR2 階段 PUBLIC EXECUTE 仍開放，V037 land 才收緊)

---

## 5. 不確定之處 / Unknowns

### 5.1 Operator deploy 時須補做的事

V037 deploy 前，operator 必對每個 Python producer 連線角色執行：
```sql
GRANT replay_writer_role TO trading_app;       -- 主 Python writer role (示意；實際 role 名待 operator 確認)
GRANT replay_writer_role TO openclaw_app_role; -- if used
-- ... etc.
```

**V037 Guard A 會 WARN（非 RAISE）若 replay_writer_role 0 members + PUBLIC INSERT 仍存在**。但 operator 若直接 V037 而忘了上述 GRANT → producer 切換後仍 fail-closed (permission denied)。建議 V037 land 前 healthcheck:
```sql
SELECT count(*) FROM pg_auth_members am JOIN pg_roles r ON r.oid = am.roleid WHERE r.rolname = 'replay_writer_role';
-- 預期 ≥ 1 (一個或多個 producer login role)
```

### 5.2 V036 function arg 與 V031 schema column 對應

V036 function arg 包含 4 個尚未物理存在於 V031 schema 的 column：
- `evidence_source_tier`
- `replay_experiment_id`
- `manifest_hash`
- `expires_at`

這 4 個 column 由 V038-V040 (sibling sub-agent task R20-P2a-S6) retrofit 物理 land。V036 function 在這 4 column physical exist 之前：
- function 接受 args 並驗證
- INSERT statement 不寫這 4 個 column (V036 inline comment block 4 已說明)
- 對 row shape 而言 = V031 既有 column 寫法不變 (PR1 of 3-PR sequence non-breaking)

V038-V040 land 後須有後續 task 升級 INSERT statement 寫入這 4 col；當前不在本 task 範圍。**E2 review 時可能會 catch 此「function arg 接受但暫不寫入」設計**，請 PM clarify 是 acceptable interim state (per workplan §4 Wave 3 R20-P2a-S4 row 將 V036 與 S6 切分作不同 task 即承認此 transitional state)。

### 5.3 LG-5 reviewer pipeline 影響

mlde_demo_applier `_insert_live_candidate` 切換後：
- `cur.execute("SELECT learning.verify_replay_evidence_and_insert(...)")` 不顯式 RETURNING id
- LG-5 sibling CC `463890d` Lg5_review_consumer 從 `mlde_shadow_recommendations` drain 時依 `(applied=false, requires_governance=true)` filter，不依賴 INSERT RETURNING
- consumer 真正讀的 audit row 由 `_apply_one` 的 `_record_application(...)` 寫入 `mlde_param_applications` (此處未動)

→ **預期影響：0**。但 E4 regression 應驗 27 既有 row baseline (deploy 前) vs 切換後 24h 新生成 row 的 schema 等價。

### 5.4 V036 不接受 `'mlde_advisor'` source alias

dispatch §A 列出 source allowlist 含 `mlde_advisor`，但 V031 schema CHECK 限定 source ∈ {linucb, ml_shadow, dream_engine, opportunity_tracker} (無 `mlde_advisor`)。本 V036 function 對齊 V031 CHECK；4 producer 中 mlde_shadow_advisor 寫入 source 為 `'ml_shadow'`（非 `'mlde_advisor'`），與 verified function 接受清單一致。如後續發現 producer pipeline 真實有 `'mlde_advisor'` 字面值寫入需求，應 PM clarify 後 V031 + V036 同時擴展 allowlist。

### 5.5 mlde_demo_applier Cursor return value handling

切換前 INSERT 不 RETURNING；切換後 verified function `RETURNS BIGINT`。若上層 caller 依賴 `cur.lastrowid` 或 `cur.fetchone()` 解析 id → 行為改變。**已驗：當前 mlde_demo_applier `_insert_live_candidate` 上層 caller `_apply_one` 不 fetch (line 1367 直接接 await)；`_insert_live_candidate` 自身也不取 cur return**。

但若 PM 後續想用 verified function 的 RETURNING id 重連 LG-5 audit chain，可在 `_insert_live_candidate` 後加 `cur.fetchone()[0]`。當前不在本 task 範圍。

---

## 6. Operator 下一步 / Next steps for operator

1. **PM E2 + E3 + MIT + FA review** 本 task 5 個 file artifact + 1 ledger update + 1 report
2. **E4 regression**：
   - 跑 `pytest tests/migrations/test_v036_v037_replay_evidence_guard.py -v` (預期 10 PASS + 2 SKIP)
   - 跑 `python3 -c "import ast; ast.parse(...)"` 對 4 producer (已驗 clean)
   - cross-platform path grep `grep -E '(/home/ncyu|/Users/[^/]+)' V036 V037 test 4_producer` (已驗 clean)
3. **PM commit + push**（commit message 草案見 §7）
4. **operator Linux trade-core deploy 順序：**
   - **Step 1**: psql -f V036 (function + role + GRANT EXECUTE TO PUBLIC + replay_writer_role)
   - **Step 2**: restart_all 部署 4 producer code 切換 (commit included)；觀察 12-24h，驗 healthcheck `mlde_replay_source_guard` baseline 維持 WARN，row count distribution 不漂移 (±5%)
   - **Step 3 prep**: 對每個 Python producer 連線角色執行 `GRANT replay_writer_role TO <login_role>;`；驗 `\du replay_writer_role` 顯示 ≥1 member
   - **Step 4**: psql -f V037 (REVOKE + GRANT + post-deploy verify)
   - **Step 5**: healthcheck `mlde_replay_source_guard` 升 PASS；12-24h continuous monitoring

5. **Linux 端 live PG test (optional, V3 §12 #6 acceptance)：**
   ```bash
   OPENCLAW_TEST_LIVE_PG=1 OPENCLAW_TEST_DSN=postgresql://... \
     pytest tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v037_revoke_public_insert_denied -v
   OPENCLAW_TEST_LIVE_PG=1 OPENCLAW_TEST_DSN=postgresql://... \
     pytest tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v037_verified_function_succeeds_with_role -v
   ```

---

## 7. PM commit message draft

```
feat(replay): V036/V037 evidence_source_guard 3-PR sequence + 4 producer switch (Wave 3 P2a-S4)

REF-20 Wave 3 R20-P2a-S4: DB role REVOKE/GRANT 3-PR sequence file artifacts +
verify_replay_evidence_and_insert() PL/pgSQL function (SECURITY INVOKER).

Changes:
- sql/migrations/V036__replay_evidence_source_guard.sql (NEW, PR1)
  PL/pgSQL function with 5 validation logic + Guard A + GRANT EXECUTE TO
  PUBLIC + replay_writer_role + idempotent CREATE ROLE.
- sql/migrations/V037__replay_evidence_revoke_public_insert.sql (NEW, PR3)
  REVOKE INSERT FROM PUBLIC + GRANT replay_writer_role + REVOKE EXECUTE FROM
  PUBLIC + Guard A pre-check + post-deploy verification.
- 4 producer switched to verified function call (PR2):
  * dream_engine.persist_dream_insights (LOW risk)
  * opportunity_tracker.persist_regret_summary (LOW risk)
  * mlde_shadow_advisor._persist_recommendations (MEDIUM risk; rec.source 變量保留)
  * mlde_demo_applier._insert_live_candidate (HIGH risk; LG-5 §2.1 schema_version
    + hardcoded engine_mode='live'/source='ml_shadow' verbatim)
- tests/migrations/test_v036_v037_replay_evidence_guard.py (NEW, 12 cases)
  10 mock-mode PASSED (V036 ALLOW × 3 + V036 REJECT × 6 + smoke); 2 SKIPPED
  (live PG, opt-in via OPENCLAW_TEST_LIVE_PG=1).
- sql/migrations/REF-20_RESERVATION.md V036/V037 status reserved → land.

Operator deploy order on Linux trade-core (V037 header inline):
  1. psql -f V036
  2. Code restart for 4 producer switch + observe 12-24h
  3. GRANT replay_writer_role TO <each Python producer login role>
  4. psql -f V037
Skipping order will fail-close all live demo writes (permission denied).

V3 §12 acceptance:
- #5 evidence_tier_completeness: function-side ready
- #6 replay_source_guard: full (pending operator deploy)
- #7 registry_fk: N/A this task

Hard constraint compliance:
- 0 SECURITY DEFINER (V3 §4.2 #4 禁)
- 0 mlde_demo_applier LG-5 audit row 邏輯改動
- 0 ws_client/ipc_server/live_authorization import
- 0 cross-platform path hardcoding

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 8. Verification artifacts

```
$ pytest tests/migrations/test_v036_v037_replay_evidence_guard.py -v
============================= test session starts ==============================
collected 12 items

tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_allow_real_outcome_valid PASSED [  8%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_allow_dream_engine_real_outcome PASSED [ 16%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_allow_replay_derived_with_metadata PASSED [ 25%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_reject_invalid_tier PASSED [ 33%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_reject_invalid_source PASSED [ 41%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_reject_real_outcome_with_replay_metadata PASSED [ 50%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_reject_replay_derived_without_metadata PASSED [ 58%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_reject_replay_derived_expired_ttl PASSED [ 66%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v036_reject_replay_derived_null_ttl PASSED [ 75%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v037_revoke_public_insert_denied SKIPPED [ 83%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_v037_verified_function_succeeds_with_role SKIPPED [ 91%]
tests/migrations/test_v036_v037_replay_evidence_guard.py::test_mock_mode_test_count_summary PASSED [100%]

======================== 10 passed, 2 skipped in 0.01s =========================
```

```
$ python3 -c "import ast; ast.parse(open('<each producer>').read())"
dream_engine OK
opportunity_tracker OK
mlde_shadow_advisor OK
mlde_demo_applier OK
```

```
$ grep -E '/home/ncyu|/Users/[^/]+' V036 V037 test 4_producer
(0 hits)

$ grep -n 'INSERT INTO learning.mlde_shadow_recommendations' 4_producer
(0 hits)

$ grep -n 'verify_replay_evidence_and_insert' 4_producer
(15 hits across 4 files — verified switch complete)
```

---

## 9. 雙語注釋合規 / Bilingual comment compliance (CLAUDE.md §七)

| 檔案 | MODULE_NOTE / docstring | inline 雙語 | 合規 |
|---|---|---|---|
| V036 SQL | header 中英對照 + function COMMENT 中英 + 5 條 RAISE detail 中英 | DO block + Guard A 中英對照 | ✅ |
| V037 SQL | header 中英對照 + Operator deploy order 中英 | Step 1/2/3 中英 + post-deploy verify 中英 | ✅ |
| dream_engine.py | switch 段落中英對照 | function call args 注釋（中英） | ✅ |
| opportunity_tracker.py | switch 段落中英對照 | function call args 注釋 | ✅ |
| mlde_shadow_advisor.py | switch 段落中英對照（rec.source 變量說明中英） | function call args 注釋 | ✅ |
| mlde_demo_applier.py | docstring + LG-5 schema_version 段落中英 | function call args 注釋 | ✅ |
| test_v036_v037_replay_evidence_guard.py | module docstring 中英 + class docstring 中英 + 每 case docstring 中英 | mock validation logic 中英對照 | ✅ |

---

## 10. 修訂歷史 / Revision history

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1 | 2026-05-03 | E1 (sub-agent, R20-P2a-S4) | V036 + V037 + 4 producer switch + 12 pytest cases + ledger update |
