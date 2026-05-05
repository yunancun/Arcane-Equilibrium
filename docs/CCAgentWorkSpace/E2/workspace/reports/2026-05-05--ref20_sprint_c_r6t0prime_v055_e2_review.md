# E2 PR Adversarial Review — REF-20 Sprint C R6-T0' V055 retrofit

**Date**: 2026-05-05
**Reviewer**: E2 (Adversarial)
**HEAD**: `85c94d63` (Mac/Linux/origin synced; 4 unstaged file pending PM commit)
**Source**: E1 sign-off `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md`

---

## Round 1 Verdict: RETURN-TO-E1 — 5 finding (2 CRITICAL + 1 HIGH + 2 MEDIUM)

## Round 1 改動範圍

| 檔 | 變動 | LOC |
|---|---|---:|
| `sql/migrations/V055__verify_replay_evidence_function_full_insert.sql` | NEW | 693 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_v055_evidence_insert_fix.py` | NEW | 860 |
| `sql/migrations/REF-20_RESERVATION.md` | +6/-3（V055 row + v1.10 entry） | n/a |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md` | NEW | 376 |

git status clean — 4 file 對齊 E1 sign-off §6（無多餘 staged/untracked）。

---

## Round 1 — 8 條 §九 既有 checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | PASS（V055/test/reservation/sign-off 4 file 對齊 §13.1） |
| 沒有 except:pass 或靜默吞異常 | **WARN** — V055:520 `EXCEPTION WHEN OTHERS THEN ROLLBACK + RAISE NOTICE + RETURN`（FINDING H-1 詳） |
| 日誌使用 %s 格式 | N/A（SQL + test，無 production logger） |
| 新 API 端點有 _require_operator_role | N/A（無 API 改動） |
| except HTTPException 在 except Exception 之前 | N/A |
| detail=str(e) 已改 "Internal server error" | N/A |
| asyncio 路由中沒有 blocking threading.Lock | N/A |
| 沒有私有屬性穿透（._xxx） | PASS |

---

## Round 1 — OpenClaw 9 條 §3 checklist

| Item | 狀態 |
|---|---|
| 跨平台 grep `/home/ncyu`/`/Users/[a-z]+` | PASS（V055 SQL 0 hit；test:561 唯一命中是 detection regex 自身，false positive，符 §10） |
| 雙語注釋（CLAUDE.md §七） | PASS（MODULE_NOTE / docstring / inline / COMMENT ON FUNCTION 四層皆雙語） |
| Rust unsafe 零容忍 | N/A（純 SQL + Python） |
| 跨語言 IPC 邊界 | N/A |
| Migration Guard A/B/C | **PARTIAL FAIL**（Guard A 三段檢查邏輯有 bug — FINDING C-2 詳；Guard B/C N/A 純 function retrofit） |
| healthcheck 配對 | N/A（V055 retrofit 不引入新被動等待 TODO） |
| Singleton 登記 §九 表 | N/A |
| 文件大小 800/1200 | PASS（V055=693 / test=860 / sign-off=376，全 < §九 2000 cap；test 860 接近 800 warning 但仍 < 2000） |
| Bybit API | N/A |

---

## Round 1 對抗反問結果（保留作 round 2 baseline）

### Q1: E1 說「16 PASS / 2 SKIPPED」— 真實覆蓋了 V055 SQL 嗎？

**A**: **沒有**。Python `_mock_verify_and_insert` (test:129-212) 是純 in-memory dict capture，line 206-210 把 args 灌進 `_row_capture` dict — **不模擬 PG INSERT，不撞 schema 缺 column 的錯誤**。16 PASS 全部 mock-only 結果，0 真實 PG 驗證。test_v055_writes_4_metadata_columns_in_insert 只驗 SQL **靜態文字**含 4 column 名，不驗 column 是否真實存在於表。

→ FINDING C-1（CRITICAL）+ FINDING M-1（MEDIUM mock 不防真錯）

### Q2: V055 INSERT line 321-369 寫 `expires_at` column — 此 column 真實存在於 `learning.mlde_shadow_recommendations` 表嗎？

**A**: **不存在**。grep 整個 `srv/sql/migrations/V*.sql`：
- V031:402-431 CREATE TABLE — 0 `expires_at`
- V038/V039/V040 ADD evidence_source_tier — 0 `expires_at`
- V051:201-203 ADD `replay_experiment_id` UUID + `manifest_hash` BYTEA — **0 `expires_at`**
- V049:305 ADD `expires_at` 是在 `replay.experiments` 表（不同表）
- V046:161 ADD `expires_at` 是在 `replay.report_artifacts` 表（不同表）
- V055 自己 line 173-176 RAISE「expires_at must exist (added by upstream migration) before V055 retrofit」— **沒有任何 upstream migration 加它**

V3 §4.2 spec line 181-187 明確只列 3 column 加給 `learning.mlde_shadow_recommendations`：`evidence_source_tier` / `replay_experiment_id` / `manifest_hash`。**V3 spec 從未要求 `expires_at` column 加到此表**。

V036 docstring (line 195-204) 提「expires_at / replay_experiment_id / manifest_hash / evidence_source_tier columns 由 V038-V040 retrofit 後實際物理存在」是 V036 PR1 期望，但**V038-V040 + V051 final reality 只加 3 column 物理存在，缺 `expires_at`**。E1 沿用 V036 docstring 4-column 字面但**沒實際驗證 schema**。

→ FINDING C-1（CRITICAL）

### Q3: V055 Guard A line 447 用 `position(...)` 子串檢測 PG arg signature drift — 真實 PG 13+ 輸出格式對齊 expected substring 嗎？

**A**: **不對齊**。`pg_get_function_arguments(oid)` 真實輸出含 arg name + DEFAULT clause。

→ FINDING C-2（CRITICAL）

### Q4-Q7：詳見 round 1 報告（保留）。

---

## Round 1 Findings 總表

| # | 嚴重性 | 位置 | 描述 | 修法建議 |
|---|---|---|---|---|
| C-1 | CRITICAL | V055:170-176, 321, 343, 367 + V055:550-560 等 4 path SELECT | `learning.mlde_shadow_recommendations.expires_at` column **不存在** | 改 V055 INSERT 不寫 expires_at（V036 verify portion 4 仍保留 TTL hard check，但 row body 只寫 3 column；TTL 取自 replay.experiments via FK lookup） |
| C-2 | CRITICAL | V055:447 | Guard A arg signature substring 比對在真 PG 13+ 不可能匹配 | 改 Guard A 用 `pg_get_function_identity_arguments(oid)` |
| H-1 | HIGH | V055:504-525 | EXCEPTION WHEN OTHERS silent skip 反模式 | 移除 silent skip；path 1 real_outcome 拆出；保留 SAVEPOINT/ROLLBACK normal path |
| M-1 | MEDIUM | sign-off §5 | sign-off 文字宣稱 acceptance PASS 但實質 mock-only | 訂正 §5；增 sign-off condition；E4 regression 模板 |
| M-2 | MEDIUM | V055:504-519 | stub `replay.experiments` INSERT minimal subset 未實證 | 對 V049 22 col 跑 `\d replay.experiments` 抽 NOT NULL 全列 |

---

## Round 1 結論

**RETURN-TO-E1** — 5 finding 全必修（2 CRITICAL + 1 HIGH + 2 MEDIUM）。**不允許 PASS to E4**。

---

# ─────────────────────────────────────────────────────────────────────────
# Round 2 Review (E2 re-verify after E1 round 2 fix)
# ─────────────────────────────────────────────────────────────────────────

**Date**: 2026-05-05
**Source**: E1 round 2 sign-off `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md` §13 (round 2 append)
**E1 round 2 deliverables**:
- V055 SQL 825 LOC (round 1 693 → +132 LOC, mainly C-2 identity_arguments + H-1 SAVEPOINT block restructure + M-2 V049 strict invariants)
- Python test 1102 LOC (round 1 860 → +242 LOC, +4 round 2 adversarial tests)
- Round 2 sign-off §13 appended (579 LOC total)

**E1 push back accepted**: REF-20_RESERVATION.md v1.10 entry 描述「INSERT body 加 4 column」+「graceful skip」+「16 PASS / 2 SKIPPED」需訂正為「3 column」+「移除 graceful skip」+「20 PASS / 2 SKIPPED」by PM at commit time（multi-session race 守則 per `feedback_git_commit_only_for_metadoc.md`）。

---

## Round 2 Verdict: **RETURN-TO-E1 round 3** — 1 NEW CRITICAL finding

E1 round 2 修了 5 round 1 findings 全部，但**新引入 1 CRITICAL bug** 在 fix M-2 過程中（stub minimal subset 用了不存在的 column）。

---

## Round 2 改動範圍

| 檔 | Round 1 LOC | Round 2 LOC | Diff |
|---|---:|---:|---:|
| `sql/migrations/V055__verify_replay_evidence_function_full_insert.sql` | 693 | 825 | +132 |
| `program_code/.../tests/replay/test_v055_evidence_insert_fix.py` | 860 | 1102 | +242 |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md` | 376 | 579 | +203（§13 round 2 append） |
| `sql/migrations/REF-20_RESERVATION.md` | +6/-3 | unchanged | 0（E1 push back PM commit 時統一改） |

git status clean (modulo round 1 + round 2 unstaged file)。

---

## Round 2 — 8 條 §九 checklist re-check

| Item | Round 1 | Round 2 | 變化 |
|---|---|---|---|
| 改動範圍與 PA 方案一致 | PASS | PASS | 無變動 |
| 沒有 except:pass 或靜默吞異常 | WARN | **PASS** | H-1 fix verified — 0 'EXCEPTION WHEN OTHERS' in active code (4 hits 全為 comment 描述 fix；test_v055_no_silent_skip_in_guard_a uses _strip_sql_comments()) |
| 日誌使用 %s 格式 | N/A | N/A | — |
| 新 API 端點有 _require_operator_role | N/A | N/A | — |
| except HTTPException 在 except Exception 之前 | N/A | N/A | — |
| detail=str(e) 已改 | N/A | N/A | — |
| asyncio blocking threading.Lock | N/A | N/A | — |
| 沒有私有屬性穿透 | PASS | PASS | — |

---

## Round 2 — OpenClaw 9 條 §3 checklist re-check

| Item | Round 1 | Round 2 | 變化 |
|---|---|---|---|
| 跨平台 grep | PASS | PASS | V055 SQL 0 hit；test:630 唯一命中是 detection regex 自身 (false positive, accepted) |
| 雙語注釋 | PASS | PASS | round 2 fix 區段全雙語 |
| Rust unsafe | N/A | N/A | — |
| 跨語言 IPC | N/A | N/A | — |
| Migration Guard A/B/C | PARTIAL FAIL (C-2) | **PASS** | C-2 fix 用 pg_get_function_identity_arguments PG 9.4+ canonical + strict equality；0 substring noise |
| healthcheck 配對 | N/A | N/A | — |
| Singleton 登記 §九 表 | N/A | N/A | — |
| 文件大小 800/1200 | PASS | PASS | V055=825 / test=1102 全 < §九 2000 cap；test 1102 仍 < 2000 cap |
| Bybit API | N/A | N/A | — |

---

## Round 2 對抗反問結果

### Q1（round 2 §1）: 你說 V055 已不寫 expires_at — INSERT statement 哪行確認？

**A**: **PASS**。
- V055:386-407 INSERT INTO learning.mlde_shadow_recommendations (...) 列 17 column (V036 16 + V055 retrofit 3)，**0 `expires_at` 字面**
- V055:407-431 VALUES (...) 列 17 表達式 (含 `p_replay_experiment_id::UUID` + `decode(p_manifest_hash, 'hex')`)，**0 `p_expires_at` value forward**
- V055:135-141 preflight 移除 expires_at column existence check (round 1 line 173-176 已刪)
- V055:386-407 INSERT block 三 round 2 V055 retrofit 注釋（line 403-406 中英對照）標記「3 replay metadata columns (V036 PR3)」
- COMMENT ON FUNCTION (V055:445-464) 明確說明「INSERT body forwards 3 replay metadata columns」+「p_expires_at is validated as input but NOT persisted」雙語對照
- Test `test_v055_does_not_write_expires_at_column` (line 714-755) PASS — uses word-boundary regex 過濾 `p_expires_at` (function arg) 與 `expires_at` (column)，0 column-name 匹配

V055 round 2 verify portion (4) 仍保留 TTL hard check (V055:342-356 byte-equal V036:177-191)，input validation 路徑不退化。

→ Round 2 C-1 fix verified。

### Q2（round 2 §2）: 你說 Guard A 改用 identity_arguments — 此函數 PG 13+ 行為實際是什麼？是否 byte-equal V036?

**A**: **PASS（with PG runtime 真值待 E4 確認）**。
- V055:527 `SELECT lower(pg_get_function_identity_arguments(p.oid)) INTO v_identity_args` — PG 9.4+ canonical API
- V055:496 `v_expected_identity_args TEXT := 'text, text, text, text, text, double precision, double precision, integer, jsonb, boolean, boolean, text, text, text, text, timestamp with time zone, text, text, text';` — 19 type list
- V055:533 `IF v_identity_args <> v_expected_identity_args THEN` — strict equality（**不是** position() substring）
- 對抗驗：手 craft V036 `DEFAULT 'real_outcome'` → `DEFAULT NULL` 變動 → identity_arguments **不含 DEFAULT clause** → Guard A 不觸發 RAISE（DEFAULT 改動非 signature drift；正確）
- 對抗驗：手 craft V036 第 13 arg type `text` → `varchar` → identity_arguments 第 13 段不對齊 → Guard A 觸發 RAISE EXCEPTION（正確 fail-loud）
- Test `test_v055_function_existence` PASS — assert `pg_get_function_identity_arguments` + strict equality `v_identity_args <> v_expected_identity_args`（line 259-318，verified at SQL parse layer）

**E1 round 2 sign-off §13.7 點 4 注**：Linux PG 13/14/15/16 的 `pg_get_function_identity_arguments` 輸出格式假設 ' '+',' separated lower-case，E4 regression Step 4 必驗 byte-by-byte。E2 接受此假設（PG 9.4+ canonical API 全版本一致 per official docs）。

→ Round 2 C-2 fix verified（Mac SQL parse layer；Linux PG 真值 E4 regression Step 4 確認）。

### Q3（round 2 §3）: 你說 silent skip 已刪 — 如何證明任何 path（4-tier smoke 各 INSERT）失敗都會 RAISE 而非 RETURN？

**A**: **PASS**。
- V055:600-795 SAVEPOINT block 結構（DO $$ ... BEGIN ... END $$）：
  - V055:612 `SAVEPOINT v055_smoke;`
  - V055:614-649 path 1 real_outcome（不依賴 FK，獨立可跑）— **拆出 stub experiment INSERT 之外**（per round 2 H-1 fix）
  - V055:651-687 stub `replay.experiments` INSERT — **0 EXCEPTION block 包圍**；任何 NOT NULL drift / FK violation / type mismatch → 自然 propagate 到 outer DO $$ block
  - V055:689-789 path 2-4（calibrated/synthetic/counterfactual）— **0 EXCEPTION block 包圍**
  - V055:793 `ROLLBACK TO SAVEPOINT v055_smoke;` — normal path（4 row INSERT 完成後）
- 對抗驗：grep `EXCEPTION WHEN OTHERS` in V055 SQL — 4 hit **全為 comment 描述 fix**（V055:564 / 572 / 658 / 664）；test_v055_no_silent_skip_in_guard_a 用 _strip_sql_comments() 過濾 comment → 0 hit → PASS
- 對抗驗：手 craft V051 paired CHECK violation 場景 — V055 path 2-4 INSERT 無 EXCEPTION block 包圍 → CHECK violation 自然 RAISE → outer DO $$ block 失敗 → psql apply 端 fail-loud（CLAUDE.md §九 SQL 等價）

→ Round 2 H-1 fix verified。

### Q4（round 2 §4）: 你說 V049 NOT NULL set 已實證 — 真實 line 282-307 跑 grep 看到的是什麼?

**A**: **PASS（V049 source 實證）**。
- V049:283-307 ADD COLUMN 18 行：全 `ADD COLUMN IF NOT EXISTS <name> <type>,` 形式 — **0 inline NOT NULL constraint**
- V049:418-433 conditional NOT NULL CHECK：`chk_replay_experiments_engine_sha_linux` only when `runtime_environment='linux_trade_core'` — round 2 stub 用 `'mac_dev_smoke_test_only'` bypass
- V049:339-341 `chk_replay_experiments_runtime_env`：CHECK 2-value enum (`'linux_trade_core'`, `'mac_dev_smoke_test_only'`) NULL OK — round 2 stub 顯式設定 `'mac_dev_smoke_test_only'` PASS
- V049 base unconditional NOT NULL（V041 stub + V049 retrofit）：
  1. `experiment_id UUID PRIMARY KEY NOT NULL` (V041 stub TEXT PK + V049 ALTER TYPE UUID)
  2. `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` (V041 stub)
- Test `test_v055_v049_source_not_null_invariant` (line 908-933) PASS — regex grep V049 source for `ADD COLUMN IF NOT EXISTS\s+\w+\s+\w+(?:\s+\w+)*\s+NOT NULL` → 0 命中 → 證明 V049 ADD COLUMN 18 個全 NULLABLE
- Test `test_v055_v049_not_null_set_documented` (line 847-905) PASS — driver test 抽 V055 stub INSERT column list，assert `runtime_environment` + `experiment_id` + `'mac_dev_smoke_test_only'` 全在

→ Round 2 M-2 fix partial verified（V049 source NOT NULL invariant proven；但 stub minimal subset 仍含 phantom column — 見 NEW finding C-3）。

### Q5（round 2 §5）: Mac pytest 22 PASS 是否真有 cover 上述 fix 全部?哪 case 對應哪 finding?

**A**: **PASS（mock-only static-parse 層；0 PG 真實 deploy 驗證）**。

E2 在 Mac 上重跑 pytest（`python3 -m pytest .../test_v055_evidence_insert_fix.py -v`）：

```
collected 22 items

test_v055_function_existence                                         PASSED [4%]   # round 2 C-2 (identity_arguments + strict equality)
test_v055_real_outcome_path                                          PASSED [9%]
test_v055_calibrated_replay_path                                     PASSED [13%]
test_v055_synthetic_replay_path                                      PASSED [18%]
test_v055_counterfactual_replay_path                                 PASSED [22%]
test_v055_v051_paired_check_still_enforced                           PASSED [27%]
test_v055_v036_ttl_check_still_enforced                              PASSED [31%]
test_v055_idempotent_apply                                           PASSED [36%]
test_v055_bilingual_module_note                                      PASSED [40%]
test_v055_no_user_home_path_hardcoded                                PASSED [45%]
test_v055_no_hard_boundary_columns_touched                           PASSED [50%]
test_v055_no_trading_or_live_mutation                                PASSED [54%]
test_v055_writes_3_metadata_columns_in_insert                        PASSED [59%]   # round 2 C-1（取代 round 1 _4_metadata_）
test_v055_does_not_write_expires_at_column                           PASSED [63%]   # round 2 NEW C-1 (negative assertion)
test_v055_signature_byte_equal_v036                                  PASSED [68%]
test_v055_4_path_smoke_in_guard_a                                    PASSED [72%]
test_v055_no_silent_skip_in_guard_a                                  PASSED [77%]   # round 2 NEW H-1
test_v055_v049_not_null_set_documented                               PASSED [81%]   # round 2 NEW M-2
test_v055_v049_source_not_null_invariant                             PASSED [86%]   # round 2 NEW M-2
test_v055_live_pg_real_outcome_row_body                              SKIPPED[90%]   # OPENCLAW_TEST_LIVE_PG=1 opt-in
test_v055_live_pg_calibrated_replay_row_body                         SKIPPED[95%]   # OPENCLAW_TEST_LIVE_PG=1 opt-in
test_v055_mock_mode_test_count_summary                               PASSED [100%]

20 passed, 2 skipped in 0.02s
```

**真實對應**：
- Round 2 C-1 fix → test_v055_writes_3_metadata_columns_in_insert + test_v055_does_not_write_expires_at_column（2 test）
- Round 2 C-2 fix → test_v055_function_existence (assert identity_arguments + strict equality)
- Round 2 H-1 fix → test_v055_no_silent_skip_in_guard_a (grep `_strip_sql_comments()` for 'EXCEPTION WHEN OTHERS')
- Round 2 M-2 fix → test_v055_v049_not_null_set_documented + test_v055_v049_source_not_null_invariant（2 test）

**但**：
- 0 test 驗 V055 stub INSERT 對 replay.experiments 的 column 名是否真實存在於 V049 schema（FINDING C-3 BLIND SPOT）
- M-2 driver test (line 873-905) **只 grep** stub INSERT column list 是否含 `runtime_environment` + `experiment_id` + 字串 `'mac_dev_smoke_test_only'`，**未對 V049 source 做 cross-validation 確認所有 stub column 都實存**
- 真 PG schema deploy validation 仍 deferred 到 E4 regression Step 6+7 (OPENCLAW_TEST_LIVE_PG=1)

→ Round 2 mock-layer cover 4 round 2 fix；新引入 phantom column issue（C-3）mock test 0 cover 是 mock 層本質限制（per round 1 M-1 finding，仍適用）。

---

## Round 2 NEW Findings 總表

### FINDING C-3（NEW CRITICAL）— stub INSERT 用了不存在的 `actor_id` column

| 嚴重性 | 位置 | 描述 |
|---|---|---|
| **CRITICAL** | V055:671-687（stub INSERT to replay.experiments）+ E1 sign-off §12 點 1 + §13.1 M-2 fix 描述 | V055 round 2 stub `INSERT INTO replay.experiments (experiment_id, actor_id, status, created_at, half_life_days, embargo_days, runtime_environment) VALUES (...)` line 673 引用 **`actor_id` column 不存在於 `replay.experiments` 表**：grep `srv/sql/migrations/V*.sql` for `actor_id`：V045:199 `actor_id TEXT NOT NULL` 是 `replay.run_state` 的 column；V044/V052 引用 `replay.run_state.actor_id`；**V041/V049 任一 ADD COLUMN 都未加 actor_id 給 replay.experiments**；V049 真實 22 col schema 用 `created_by TEXT` (V049:284) 標 actor，**不是 `actor_id`**。Linux deploy V055 必撞 PG error `column "actor_id" of relation "experiments" does not exist`。E1 自承 round 1 §12 點 1 寫「`INSERT INTO replay.experiments (experiment_id, actor_id, status, created_at, half_life_days, embargo_days)`」是混淆 `replay.run_state.actor_id`（V045）與不存在的 `replay.experiments.actor_id`，round 2 fix M-2 直接複用 round 1 stub structure 加 runtime_environment 但**未 audit `actor_id` 實存性**。E1 round 2 §13.1 M-2 fix 描述 "stub minimal subset = experiment_id + actor_id (V041 4-col 之外，但 V049 line 284 ADD; 為 nullable per V049 source)" — **factually 錯**：V049 line 284 ADD 是 `parent_experiment_id` 不是 `actor_id`。Round 2 Mac mock test M-2 driver (test_v055_v049_not_null_set_documented) 只 grep stub INSERT column list 是否含 `runtime_environment`/`experiment_id`，0 cross-validation 確認 stub column 實存於 V049 schema。 |

**修法建議**：
- 改 stub INSERT 移除 `actor_id` column；用 V049 真實 `created_by TEXT NULLABLE` (V049:284) 標 actor，OR 直接刪除（V049 ADD COLUMN 全 NULLABLE 不需 supply）
- V055 round 3 stub INSERT minimal column set：
  ```sql
  INSERT INTO replay.experiments (
      experiment_id,           -- V041 PK NOT NULL
      created_at,              -- V041 NOT NULL DEFAULT NOW() (此處顯式 supply 規避 default time skew)
      half_life_days,          -- V041 NULLABLE
      embargo_days,            -- V041 NULLABLE
      runtime_environment,     -- V049 conditional NOT NULL bypass (mac_dev_smoke_test_only)
      created_by,              -- V049 NULLABLE (取代不存在的 actor_id)
      status                   -- V049 NULLABLE 5-value enum
  ) VALUES (
      v_test_experiment_id,
      now(),
      14.0,
      14,
      'mac_dev_smoke_test_only',
      'v055_smoke_test',
      'created'
  );
  ```
- 新增 test `test_v055_stub_columns_exist_in_v049` 對 V049 source cross-validate stub INSERT 每 column 都存在於 V049 ADD COLUMN list / V041 base table list（防 future round 重犯）
- 修 sign-off §13.1 M-2 fix description 訂正「actor_id」→「created_by (V049:284 ADD COLUMN)」

**為何 round 1 E2 沒 catch**：round 1 E2 finding M-2 標的是「stub INSERT NOT NULL set 未實證」+ 建議「跑 `\d replay.experiments` 抽 NOT NULL set 全列」。Round 1 E2 假設 stub column 名都正確，只審 NOT NULL 完整性。**Round 2 E2 對抗反問 §4「真實 line 282-307 跑 grep 看到的是什麼」深挖到 V049 source 才發現 stub column `actor_id` 與 V049 真實 column 名不一致**。E2 round 1 dedicated NOT NULL 完整性，E2 round 2 dedicated column 名實存性 — 兩 round 不同對抗角度（accepted multi-round audit limitation）。

**E1 不確定 → 應 push back**：E1 round 1 §12 點 1 + round 2 §13.7 點 1-3 多次自承「不確定 V049 22-col schema 真實 NOT NULL set」+「stub `runtime_environment='mac_dev_smoke_test_only'` 在 Linux deploy 端是否被 V049 healthcheck 視為 invalid env」+「Round 2 修補的 `pg_get_function_identity_arguments` 輸出格式」— 但**沒 push back 到 PA / PM 要求 PG live smoke 才 sign-off**。E1 round 2 sign-off 仍 deliver Mac pytest static-parse PASS 當作 acceptance evidence。違 CLAUDE.md §七 P0-PROCESS-1 工作鏈精神（fail-closed validation 原則）+ §七 「Sign-off 必檢 git status clean」+ §八「6. 自主 bug 修復：收到 bug 直接修；指 log/錯誤/失敗測試再解」隱含「validate before sign-off」要求。

---

## Round 1 Findings 5 個 re-verify 結果

| # | Round 1 Finding | Round 2 Status |
|---|---|---|
| C-1 | expires_at column 不存在於 mlde_shadow_recommendations | **FIXED** — V055:386-431 INSERT body 0 expires_at；V055:135-141 preflight 0 expires_at check；test_v055_does_not_write_expires_at_column PASS |
| C-2 | Guard A position() substring 在 PG 13+ false positive | **FIXED** — V055:527 `pg_get_function_identity_arguments` + V055:533 strict equality；test_v055_function_existence PASS |
| H-1 | EXCEPTION WHEN OTHERS silent skip 反模式 | **FIXED** — V055:600-795 SAVEPOINT block 0 EXCEPTION block (4 EXCEPTION WHEN OTHERS hit 全為 comment 描述 fix)；path 1 拆出 stub experiment INSERT 之外；test_v055_no_silent_skip_in_guard_a PASS |
| M-1 | sign-off §5 文字訂正 + acceptance condition | **FIXED** — sign-off §13.4 訂正 mock-only 文字；§13.5 列 7-step E4 regression command 含 OPENCLAW_TEST_LIVE_PG=1 |
| M-2 | V049 NOT NULL set 對齊 stub minimal subset | **PARTIAL FIXED, NEW BUG INTRODUCED (C-3)** — V049 NOT NULL set documented + cross-validated；但 stub INSERT 用了不存在的 `actor_id` column |

---

## Round 2 結論

**RETURN-TO-E1 round 3** — 1 NEW CRITICAL finding (C-3)。

E1 round 2 修了 round 1 5 findings 全部，**Round 1 4/5 fix 完美 verified**（C-1 + C-2 + H-1 + M-1）。**M-2 fix 過程中新引入 1 phantom column bug**（stub INSERT 用 `actor_id` 不存在於 replay.experiments）。Linux deploy V055 必撞 PG error。

E2 對抗反問 §4 深挖 V049 真實 line 282-307 後發現 `actor_id` column 不存在；E1 round 2 sign-off §13.1 M-2 fix description 自身 factually 錯（指 V049 line 284 ADD 是 actor_id，但實是 parent_experiment_id）。Mac mock test M-2 driver 0 cross-validate stub column 實存性（mock layer 本質限制）。

---

## Round 2 退回 E1 round 3 修復清單

### CRITICAL（必修，修完才能重 E2 round 3）

1. **FINDING C-3** — V055:671-687 stub INSERT 移除 `actor_id`（不存在 column），改用 `created_by`（V049:284 NULLABLE）OR 直接刪除（V049 全 NULLABLE 不需 supply）。對應修改：
   - V055 line 671-687 stub INSERT block 改 column list（移 actor_id；補 created_by OR 完全刪除 actor_id 列）
   - V055 line 651-668 stub INSERT 旁的 round 2 fix 注釋 同步訂正
   - sign-off §13.1 M-2 fix description 訂正「actor_id (V041 4-col 之外，但 V049 line 284 ADD)」→「created_by (V049 line 284 ADD COLUMN, NULLABLE)」OR 移除「actor_id」字眼
   - Python test 新增 `test_v055_stub_columns_exist_in_v049` cross-validate stub INSERT column list 對 V049 source ADD COLUMN list + V041 base column list 全 ⊆（防 round 4+ 重犯）
   - sign-off §13.7 round 2 不確定之處 點 4 訂正

### Round 2 fix 全 verified, no further action needed

- C-1 (3 column INSERT): VERIFIED
- C-2 (identity_arguments strict equality): VERIFIED
- H-1 (no silent skip): VERIFIED
- M-1 (sign-off §13.4 + §13.5 訂正): VERIFIED

### REF-20_RESERVATION.md ledger 訂正（PM action at commit time）

E1 round 2 push back 接受：v1.10 entry 描述「INSERT body 加 4 column」+「graceful skip 4-tier smoke」+「16 PASS / 2 SKIPPED」需訂正為「3 column」+「移除 silent skip」+「20 PASS / 2 SKIPPED」by PM at commit phase（multi-session race 守則）。

E2 round 2 verdict 不單方面 commit ledger 改動。PM 接手 commit 時統一改。

---

## Round 2 重 E2 round 3 條件

E1 修完 C-3 finding（含 sign-off §13.1 M-2 description 訂正）後：
- 重新 sign-off 報告（appended §14 round 3 fix description）
- E2 round 3 review 重跑（重點 = §13.1 M-2 stub column 實存性 verify + 新 test_v055_stub_columns_exist_in_v049 PASS）
- 若 round 3 fix 結束 0 NEW finding → APPROVE-FOR-E4 → E4 regression Linux SSH bridge apply OPENCLAW_TEST_LIVE_PG=1 跑 23/23 PASS（22 + 1 new test）

**注**：E2 round 3 不需重審 round 2 已 verified C-1/C-2/H-1/M-1（除非 round 3 改動觸發 cross-cutting regression）。

---

E2 ROUND 2 REVIEW DONE: report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_e2_review.md`; verdict: RETURN-TO-E1 round 3; findings: 1 NEW CRITICAL (C-3 phantom column actor_id); pending E1 round 3 fix; PM action: REF-20_RESERVATION ledger 訂正 deferred to commit phase

---

# ─────────────────────────────────────────────────────────────────────────
# Round 3 Review (E2 re-verify after E1 round 3 C-3 fix)
# ─────────────────────────────────────────────────────────────────────────

**Date**: 2026-05-05
**Source**: E1 round 3 sign-off `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md` §14 (round 3 append, 820 LOC total — round 2 579 → +241)
**E1 round 3 deliverables**:
- V055 SQL 879 LOC (round 2 825 → +54 LOC: stub INSERT phantom 移除 -2 line + 雙語 fix 注釋 +56)
- Python test 1271 LOC (round 2 1102 → +169 LOC: NEW `test_v055_stub_columns_exist_in_v049` 162 LOC + count summary update)
- Round 3 sign-off §14 appended (LOC 583-816)
- E1 memory.md round 3 lessons append (5237 → 5285)

**E1 push back 接受性 verdict（per dispatch §5）**:
1. **V049 真實 ADD COLUMN count = 25 (not 18)**: ACCEPTED — PM closure 階段統一 update PA dispatch + E2 round 1+2 review report 標稱「18」→「25」。E2 round 3 footnote 此 fact 但**不 RETURN**（per dispatch instruction）。
2. **stub INSERT status='created' vs smoke 語意**: ACCEPTED — round 3 不擴大範圍，future ticket scope。

---

## Round 3 Verdict: **PASS to E4** — 0 new finding

E1 round 3 fix 完整修了 C-3 phantom column bug 且 round 1+2 5 個 fix 全保留 0 regression。E2 round 3 re-verify 確認：
- C-3 fix verified: V055 stub INSERT 0 phantom column (active SQL 0 hit on `actor_id`，21 hit 全為 round 3 fix 雙語 doc comments)
- New cross-validation test 真實 file-read parsing (非 hardcoded fixture)，6-step 邏輯 + adversarial sanity inline + dual phantom guard
- Round 1+2 5 fix 全保留 (C-1 + C-2 + H-1 + M-1 + M-2)
- 邊界守則 0 violation (0 V036/V037/V049/V050/V051 modify / 0 manifest_signer canonical_bytes 改 / 0 跨平台路徑硬編碼)
- LOC 全 < §九 2000 cap (V055=879, test=1271)
- Mac pytest 23/21/2 真實重跑 verified

**Findings: 0**

---

## Round 3 改動範圍

| 檔 | Round 2 LOC | Round 3 LOC | Diff | 變動類別 |
|---|---:|---:|---:|---|
| `sql/migrations/V055__verify_replay_evidence_function_full_insert.sql` | 825 | **879** | +54 | C-3 fix: stub INSERT phantom 移除 + round 3 雙語 fix 注釋 |
| `program_code/.../tests/replay/test_v055_evidence_insert_fix.py` | 1102 | **1271** | +169 | C-3 fix: new test_v055_stub_columns_exist_in_v049 case (164 LOC) + summary count update |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md` | 579 | **820** | +241 | §14 round 3 fix appendix (583-816) |
| `sql/migrations/REF-20_RESERVATION.md` | unchanged | unchanged | 0 | E1 邊界守則 — PM commit 時統一處理 |

git status (round 3 verified, expected unstaged):
```
M docs/CCAgentWorkSpace/E1/memory.md
M docs/CCAgentWorkSpace/E2/memory.md  (E2 round 1+2 自身)
M sql/migrations/REF-20_RESERVATION.md  (round 1+2 v1.10 line 仍存在)
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md
?? docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_e2_review.md
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_v055_evidence_insert_fix.py
?? sql/migrations/V055__verify_replay_evidence_function_full_insert.sql
```

---

## Round 3 — 8 條 §九 checklist re-check

| Item | Round 2 | Round 3 | 變化 |
|---|---|---|---|
| 改動範圍與 PA 方案一致 | PASS | **PASS** | 對齊 dispatch §1 邊界 (C-3 fix only, 0 V036/V037/V049/V050/V051 modify) |
| 沒有 except:pass 或靜默吞異常 | PASS | **PASS** | 0 'EXCEPTION WHEN OTHERS' in active code post-strip-comment (4 hits 全 fix-doc comments) |
| 日誌使用 %s 格式 | N/A | N/A | — |
| 新 API 端點 _require_operator_role | N/A | N/A | — |
| except HTTPException 在 except Exception 之前 | N/A | N/A | — |
| detail=str(e) 已改 | N/A | N/A | — |
| asyncio blocking threading.Lock | N/A | N/A | — |
| 沒有私有屬性穿透 | PASS | PASS | — |

---

## Round 3 — OpenClaw 9 條 §3 checklist re-check

| Item | Round 2 | Round 3 | 變化 |
|---|---|---|---|
| 跨平台 grep `/home/ncyu`/`/Users/[a-z]+` | PASS | **PASS** | V055 SQL 0 hit；test:643 唯一命中是 detection regex 自身 (false positive accepted) |
| 雙語注釋 (CLAUDE.md §七) | PASS | **PASS** | round 3 fix 區段全雙語 (V055:589-639 round 3 fix block 中英對照；test:949-980 docstring 中英對照) |
| Rust unsafe | N/A | N/A | — |
| 跨語言 IPC | N/A | N/A | — |
| Migration Guard A/B/C | PASS | **PASS** | C-2 fix preserved (pg_get_function_identity_arguments 2 hits + 0 substring drift API hits) |
| healthcheck 配對 | N/A | N/A | — |
| Singleton 登記 §九 表 | N/A | N/A | — |
| 文件大小 800/1200 | PASS | **PASS** | V055=879 / test=1271 全 < §九 2000 cap (test 1271 ≥ 800 warn line, accepted; V055 879 ≥ 800 warn line, accepted)  |
| Bybit API | N/A | N/A | — |

---

## Round 3 對抗反問結果（dispatch §6 5 條）

### Q1: 你說 V055 stub INSERT 0 actor_id — grep 真實 0 hit?

**A**: **PASS**.
- Active SQL grep `actor_id`: V055 整檔 21 hit，**0 hit 在 active code 區**（line 727-741 stub INSERT block）+ 21 hit **全為 round 3 fix 雙語 doc comments** (line 590-637 + 703-723)
- E2 round 3 自跑 Python parse: stub INSERT column set = `{experiment_id, status, created_at, half_life_days, embargo_days, runtime_environment}` — 與 round 3 expected 6-col set byte-equal match, 0 actor_id
- Round 3 stub INSERT 6 col vs round 2 7 col：移除 `actor_id` column reference + 對應 `'v055_smoke_test'` VALUES 位置（per E1 round 3 §14.1 選 A 修法 diff 確認）

### Q2: 你說 cross-validation test 真實 parse V049/V041 source — 是 hardcoded list 還是 file read?

**A**: **PASS** (real file read).
- `V049_PATH = _MIGRATIONS_DIR / "V049__replay_experiments.sql"` (test:120) — 真實 file system read 走 `_read_sql(V049_PATH)` (test:982)
- `v049_add_col_pattern = re.compile(r"ADD COLUMN IF NOT EXISTS\s+(\w+)")` finditer (test:1010-1015) — 真實 regex parse V049 source
- `v041_base_columns = {"experiment_id", "half_life_days", "embargo_days", "created_at"}` (test:1030-1035) — V041 base 4-col **是 hardcoded** (E1 round 3 §14.2 點 3 自承「V041 source 結構穩定，hardcode acceptable per minimal change」)；E2 round 3 verdict: V041:81-86 base CREATE TABLE structure 純 stub bootstrap (4-col only)，hardcode 是合理 trade-off (V041 改動極罕見；若 V041 變動會 break 多 layer 不只此 test)，accepted
- 對抗驗：E2 round 3 自寫 Python 模擬 phantom (重 inject `actor_id`) → set difference catch — 行為與 test 內 (5) adversarial inline sanity 對齊；fail-loud verified

### Q3: Round 1+2 5 fix 全保留 — round 3 沒不小心 regress 任一?

**A**: **PASS** (5/5 preserved, +1 new C-3 fix = 6 total).

| Fix | Round 3 verify 方法 | 結果 |
|---|---|---|
| **C-1** (round 2): expires_at column 不寫 mlde_shadow_recommendations | E2 round 3 自跑 Python parse INSERT body：`expires_at in column list = False` + `p_expires_at in VALUES list = False` | ✅ PASS |
| **C-2** (round 2): identity_arguments + strict equality | E2 round 3 grep post-strip-comment: `pg_get_function_identity_arguments` = 2 hits (V055:527 + 注釋 1)；`pg_get_function_arguments` (substring drift API) = 0 hit | ✅ PASS |
| **H-1** (round 2): EXCEPTION WHEN OTHERS silent skip 移除 | E2 round 3 grep post-strip-comment: `EXCEPTION WHEN OTHERS` = 0 hit (raw 4 hit 全 in fix-doc comments) | ✅ PASS |
| **M-1** (round 2): sign-off §13.4 mock-only 訂正 + §13.5 7-step E4 command | E1 round 3 §14.6.5 自核對 round 2 §13.4/§13.5 不動；本檔 round 3 不檢視非改動 §13 | ✅ PASS (delegated) |
| **M-2** (round 2): V049 NOT NULL set documented | E2 round 3 grep stub INSERT 仍含 `runtime_environment` + `mac_dev_smoke_test_only` value | ✅ PASS |
| **C-3** (round 3 NEW): phantom column actor_id 移除 | E2 round 3 自跑 stub INSERT parser：`{experiment_id, status, created_at, half_life_days, embargo_days, runtime_environment}` 6-col, 0 actor_id | ✅ NEW PASS |

### Q4: Mac pytest 23 collected — 哪 case 對應 round 3 新加？哪 case 對應 round 1+2 fix?

**A**: **PASS** (E2 round 3 自跑 verified — 23 collected / 21 PASS / 2 SKIPPED).

E2 round 3 在 Mac 重跑 (`python3 -m pytest .../test_v055_evidence_insert_fix.py -v --no-header`):
```
collected 23 items
... (20 PASS + 1 NEW + 2 SKIPPED) ...
21 passed, 2 skipped in 0.03s
```

**真實對應**:
- Round 1 既有 16 test (function existence + 4 path + idempotent + bilingual + cross-platform + hard boundary + trading mutation + writes_4_metadata 等)
- Round 2 NEW 4 test:
  - `test_v055_does_not_write_expires_at_column` (C-1)
  - `test_v055_no_silent_skip_in_guard_a` (H-1)
  - `test_v055_v049_not_null_set_documented` (M-2 driver)
  - `test_v055_v049_source_not_null_invariant` (M-2 cross)
- Round 3 NEW 1 test: `test_v055_stub_columns_exist_in_v049` (C-3 cross-validation)
- Round 1 retained 1 SKIP + Round 2 added 1 SKIP = 2 SKIPPED (live PG opt-in OPENCLAW_TEST_LIVE_PG=1)
- Round 3 0 SKIP 增加

### Q5: LOC 879 + 1271 — round 3 +變動真的合理 minimal? round 3 fix 預期 ~3-5 SQL + ~30-50 test，實 +54 SQL + +169 test 是否過大？

**A**: **PASS** (within reason; well-justified for the 6-step + adversarial sanity test design).

- **V055 SQL +54 LOC breakdown**:
  - stub INSERT block: -2 LOC (移除 `actor_id` column row + `'v055_smoke_test'` VALUES row, both 1 line each)
  - Round 3 fix bilingual comments: +56 LOC (V055:589-639 round 3 fix 雙語注釋 50 LOC + V055:703-723 stub block 旁的 round 3 fix 雙語注釋 +14 LOC，扣除部分既有注釋 -8 LOC = 約 +56)
  - Net: +54 LOC ≈ 預期 ~3-5 行核心 fix + ~50 行雙語對照注釋 (CLAUDE.md §七 強制)

- **Python test +169 LOC breakdown**:
  - NEW test `test_v055_stub_columns_exist_in_v049`: 164 LOC (測 line 949-1112)
    - Docstring (bilingual): 31 LOC
    - 6-step body logic + numbered comments: 53+80 = 133 LOC
    - Includes adversarial sanity inline (step 5) + explicit positive (step 6) + phantom guard reaffirm
  - Test count summary update: ~5 LOC (line 1263-1265 round 2 → round 3 訂正)
  - Net: +169 LOC ≈ 預期 ~30-50 minimal 1-step → 實 ~164 with 6-step + adversarial sanity inline + 完整中英對照
- **E2 round 3 verdict**: 不過度設計 (test 必要 6-step 是 dispatch §6.2 explicit binding); 雙語 docstring 是 §七 強制；adversarial sanity inline (step 5) 防 future weakening 是 PA explicit dispatch ask；accepted

E1 §14.7 點 4 自承「inline adversarial sanity 是雙重保險防止未來 weakening」+「E2 round 3 review 若 push back『拆 adversarial 為獨立 test』也接受」— **E2 round 3 不 push back 拆**，理由：
- inline pattern 與「test 自身契約 = phantom-detection logic 工作」高度耦合，分離只增 file size
- 既有 test_v055_v049_source_not_null_invariant + test_v055_v049_not_null_set_documented 也採 mixed driver+adversarial pattern (round 2 既有 N=2 case 採此模式)，此 round 3 NEW test 與 round 2 既有 design 一致
- 拆分風險：分離後若獨立 sanity test 被誤 deprecated，主測試 weakening 不會被 catch (現 inline 設計 main test 失敗 = sanity 也失敗)
- accepted as design choice

---

## Round 3 — V049 ADD COLUMN count drift footnote (per dispatch §5)

E1 round 3 §14.7 點 1 push back: V049 真實 ADD COLUMN count = **25**（不是 PA dispatch §「真相」 + E2 round 1+2 review 標稱的 18）。E2 round 3 自跑 awk-grep V049:282-307 = `parent_experiment_id / created_by / runtime_environment / git_sha / engine_binary_sha / strategy_config_sha256 / risk_config_sha256 / timeframe / data_tier / execution_confidence / calibration_train_window_start / calibration_train_window_end / oos_label_window_start / oos_label_window_end / candidate_window_start / candidate_window_end / oos_embargo_seconds / total_candidates_K / manifest_jsonb / manifest_hash / manifest_signature / signature_key_ref / expires_at / status / output_policy_jsonb` = **25 columns** confirmed。

**E2 round 3 verdict (per dispatch §5 instruction)**: ACCEPT push back; PM closure 階段統一 update。**E2 round 3 NOT RETURN** — 此 fact 為 doc label drift，不影響 round 3 fix 真實性 (test logic 用 `len(v049_add_columns) >= 18` 是下界，>= 25 也 PASS — 既能 catch round 3 設計意圖也對未來 V049 ADD COLUMN 增加保持 forward-compat)。

**Self-inconsistency footnote (E2 round 3 不退回，但 footnote)**: E1 round 3 V055 SQL line 591/623/718 + test line 945/953/969/1009 內 round 3 fix 雙語注釋仍寫「V049 line 282-307 18 ADD COLUMN list」。此「18」與 E1 自己 §14.7 push back 揭露的真實「25」不一致。**E2 round 3 verdict**: doc-label-only drift, test logic 用 `>= 18` 不依賴此 label，**不 RETURN**；建議 PM closure 階段同 update PA dispatch + E2 review 一起 update V055 注釋 + test 注釋的「18」→「25」。或留 stale label + 在 ledger 清楚標明（per E1 push back §14.7 點 1 立場）。

**E2 round 3 不擴大 round 4 RETURN 範圍**：dispatch §5 explicit「accept E1 push back，footnote 此 fact 但不 RETURN」。E2 round 3 honor dispatch boundary。

---

## Round 3 Findings 0 個

E2 round 3 review 0 finding。

---

## Round 3 結論

**PASS to E4** — 0 finding。

E1 round 3 fix 完美修 C-3 phantom column bug，round 1+2 5 fix 全保留 0 regression，邊界守則 0 violation，LOC 全 < §九 2000 cap，Mac pytest 23/21/2 真實 verified。

E2 round 3 verdict 不 RETURN E1 round 4。**APPROVE-FOR-E4 regression**。

E4 regression 必跑 (per E1 round 2 §13.5 7-step + round 3 §14 binding):
1. Linux SSH bridge: `cd ~/BybitOpenClaw/srv && git pull --ff-only origin main`
2. `psql trading_ai -f sql/migrations/V055__verify_replay_evidence_function_full_insert.sql` (apply)
3. `psql trading_ai -f sql/migrations/V055__verify_replay_evidence_function_full_insert.sql` (idempotent re-run)
4. Verify `pg_get_function_identity_arguments` 真實 PG 13/14/15/16 byte-equal output
5. `OPENCLAW_TEST_LIVE_PG=1 OPENCLAW_TEST_DSN=... python3 -m pytest .../test_v055_evidence_insert_fix.py -v` → 23 PASS (real PG path)
6. Verify Guard A 4-tier post-INSERT smoke RAISE NOTICE 出現 + ROLLBACK clean
7. Verify Linux deploy 端 V055 stub INSERT 真實 6-col 與 V049 schema 對齊 (現 25-col schema, 0 phantom)

PM action (closure phase, post E4 PASS):
- REF-20_RESERVATION ledger v1.10 entry 訂正 (4 col → 3 col / graceful skip 移除 / 16 PASS → **21 PASS** [round 3 update])
- V049 ADD COLUMN count update: PA dispatch + E2 round 1+2 docs 標「18」→「25」（option a）OR 留 stale label + 此 review report footnote 引用 (option b)；E1 立場 = option b 最小變動

---

E2 ROUND 3 REVIEW DONE: report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_e2_review.md`; verdict: **PASS to E4**; findings: 0; pending E4 regression (Linux SSH bridge OPENCLAW_TEST_LIVE_PG=1 跑 23 PASS); PM action (closure phase): REF-20_RESERVATION ledger v1.10 entry 訂正 (4 col → 3 col / graceful skip 移除 / 16 PASS → **21 PASS**) + V049 ADD COLUMN count 18 → 25 update (PA dispatch + E2 round 1+2 docs) at commit phase

---

# ─────────────────────────────────────────────────────────────────────────
# Round 5 Review (E2 re-verify after E1 round 5 design pivot — drop in-migration smoke)
# ─────────────────────────────────────────────────────────────────────────

**Date**: 2026-05-05
**HEAD**: `622fd3e0` (Mac/Linux/origin synced; 4 unstaged file pending PM commit)
**Source**: E1 round 5 sign-off `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md` §16 (round 5 design pivot append)
**E1 round 5 deliverables**:
- V055 SQL 715 LOC (round 4 913 → -198 LOC: drop in-migration 4-tier post-INSERT smoke per PL/pgSQL constraint)
- Python test 1316 LOC ≠ E1 reported 1265 (sign-off §16.6 標 1265，**實際 1316**；E2 wc -l 驗；§round-5.6 §round-5.LOC 訂正)
- Round 5 sign-off §16 appended (1192 LOC total — E2 round 3 baseline 820 → +372)
- E1 memory.md round 5 lessons append (5237 → 5389 — actual; sign-off declared 5336 → 5389 +53)

**Round 4 → 5 hotfix history**：
- Round 4 hotfix `622fd3e0` 修 PG 16 empirical `pg_get_function_identity_arguments` 含 arg name (signature drift 假陽性)，**通過** Linux PG 16 deploy 的 line 539 expected_string assert
- Round 5 在 round 4 fix 後**新撞** PG 硬限制：PL/pgSQL DO block 拒 explicit `SAVEPOINT name` / `ROLLBACK TO SAVEPOINT name`（line 883 fail）→ E1 採設計修正路線（drop in-migration smoke entirely）

---

## Round 5 Verdict: **RETURN-TO-E1 round 6** — 1 NEW CRITICAL finding (C-4)

E1 round 5 design pivot **正確**（PL/pgSQL constraint 確實阻擋 in-migration savepoint，drop smoke + 遷至 sibling test 是合理 fix）。但設計遷移過程中**漏審 sibling test 自身的 stub INSERT** — `test_v055_live_pg_calibrated_replay_row_body` line 1252 仍含 round 2-3 已知的 phantom column `actor_id`。round 3 fix C-3 在 V055 SQL 內已修，但同等 phantom 在 sibling test 內 **alive**。

**Round 5 design pivot 的核心矛盾**：E1 §16.4 明說「4-tier path verification migrated to Python sibling test under OPENCLAW_TEST_LIVE_PG=1」是 round 5 的 coverage migration substitute — 即 sibling test 取代 in-migration smoke 成為**主要** live PG verification path。但 sibling test 的 calibrated_replay live_pg case 在 Linux PG 16 OPENCLAW_TEST_LIVE_PG=1 跑時必撞 `column "actor_id" of relation "experiments" does not exist` → coverage migration 名義成立但**實**等於 0 真實 calibrated_replay live PG verification，等同 round 5 把 in-migration smoke 換成 broken sibling test。

E2 round 5 verdict: **RETURN-TO-E1 round 6**。1 NEW CRITICAL finding（C-4 sibling stub phantom column carry-over）。

---

## Round 5 改動範圍

| 檔 | Round 4 LOC | Round 5 LOC (E2 wc) | E1 reported | Δ vs round 4 | E1 vs E2 |
|---|---:|---:|---:|---:|---|
| `sql/migrations/V055__verify_replay_evidence_function_full_insert.sql` | 913 | **715** | 715 | -198 | match |
| `program_code/.../tests/replay/test_v055_evidence_insert_fix.py` | 1294 | **1316** | 1265 | +22 | **mismatch (+51)** — 見 §round-5.LOC |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md` | 990 | **1192** | 1192 | +202 | match |
| `sql/migrations/REF-20_RESERVATION.md` | unchanged | unchanged | 0 | 0 | (PM closure phase) |

git status:
```
 M docs/CCAgentWorkSpace/E1/memory.md
 M docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_impl.md
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_v055_evidence_insert_fix.py
 M sql/migrations/V055__verify_replay_evidence_function_full_insert.sql
```

4 unstaged file，與 dispatch §「E1 round 5 deliverables 全 unstaged（4 file）」聲明對齊。

---

## §round-5.LOC: Python test LOC mismatch (E1 §16.6 1265 vs E2 wc 1316)

E1 §16.6 LOC table 列 Python test 「1294 → 1265 (-29)」但 E2 自跑 `wc -l` 真實 = **1316**（差 +51）。

對抗驗：
```bash
wc -l program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_v055_evidence_insert_fix.py
```
真實: **1316** (E2 verified at HEAD `622fd3e0`)

E1 §16.6 LOC delta 計算誤差 +51 LOC — 不影響 round 5 design pivot semantic correctness，但 sign-off LOC 數字應準。建議 PM closure 時統一訂正 §16.6 column。**E2 round 5 不單獨 RETURN 此項**（sign-off 文字 fix only，不影響 V055 SQL 或 Python test 邏輯）。LOC 1316 仍 < §九 2000 cap，0 governance violation。

---

## Round 5 — 8 條 §九 checklist re-check

| Item | Round 3 | Round 5 | 變化 |
|---|---|---|---|
| 改動範圍與 PA 方案一致 | PASS | **PASS** | dispatch §1+§2 邊界 0 violation；V036/V037/V049/V050/V051 0 modify；H-1 SAVEPOINT/ROLLBACK 移除路徑乾淨 |
| 沒有 except:pass 或靜默吞異常 | PASS | **PASS** | grep `EXCEPTION WHEN OTHERS` V055 = 0 hit (raw + post-strip-comment 全 0)；H-1 finding 經 drop smoke 自然延續，0 regression |
| 日誌使用 %s 格式 | N/A | N/A | — |
| 新 API 端點 _require_operator_role | N/A | N/A | — |
| except HTTPException 在 except Exception 之前 | N/A | N/A | — |
| detail=str(e) 已改 | N/A | N/A | — |
| asyncio blocking threading.Lock | N/A | N/A | — |
| 沒有私有屬性穿透 | PASS | PASS | — |

---

## Round 5 — OpenClaw 9 條 §3 checklist re-check

| Item | Round 3 | Round 5 | 變化 |
|---|---|---|---|
| 跨平台 grep `/home/ncyu`/`/Users/[a-z]+` | PASS | **PASS** | V055 SQL 0 hit；test:659 唯一命中是 detection regex 自身 (test_v055_no_user_home_path_hardcoded 內，false positive accepted) |
| 雙語注釋 (CLAUDE.md §七) | PASS | **PASS** | round 5 design pivot section 雙語對照 (line 114-151 + 614-674)；Operator note 第 4 點雙語擴展；(REMOVED) breadcrumb 雙語 |
| Rust unsafe | N/A | N/A | — |
| 跨語言 IPC | N/A | N/A | — |
| Migration Guard A/B/C | PASS | **PASS** | Guard A 3 invariant (function existence + pronargs + identity_arguments) 全保留 line 522-612；C-2 fix 不破；Guard A 4-tier post-INSERT smoke drop = design pivot non-violation (sibling test 替代覆蓋) |
| healthcheck 配對 | N/A | N/A | — |
| Singleton 登記 §九 表 | N/A | N/A | — |
| 文件大小 800/1200 | PASS | **PASS** | V055=715 / test=1316 全 < §九 2000 cap (test 1316 ≥ 800 warn line, accepted; V055 715 也 ≥ 800 但 round 5 是 LOC 減)。**注**：round 4 1500→2000 cap 為 OpenClaw governance 2026-05-05 raise，§九 既載 |
| Bybit API | N/A | N/A | — |

---

## Round 5 對抗反問結果（dispatch §6 5 條）

### Q1: 你說 V055 round 5 drop smoke — grep `SAVEPOINT` / `ROLLBACK TO` / `INSERT INTO replay.experiments` 真實 0 hit?

**A**: **PASS（V055 SQL 內 active code 0 hit；doc comments 仍提及 8 hit）**.

```bash
$ grep -nE "INSERT INTO replay\.experiments" V055.sql
(0 hit)

$ grep -nE "EXCEPTION WHEN OTHERS" V055.sql
(0 hit)

$ grep -nE "actor_id" V055.sql
(0 hit)

$ grep -n "SAVEPOINT v055_smoke" V055.sql
(0 hit)

$ grep -n "ROLLBACK TO SAVEPOINT v055_smoke" V055.sql
(0 hit)

$ grep -n "SAVEPOINT" V055.sql
115/131:  -- (註解，雙語對照 PL/pgSQL constraint)
619/640/644-645/664: (round 5 design pivot section 雙語注釋)
```

V055 SQL 8 個 SAVEPOINT 字串全在 design pivot doc comments 內，0 active SQL；V055 SQL 0 active stub INSERT；0 actor_id 殘留。

### Q2: Round 1-4 6 finding 全保留 — round 5 drop block 過程沒誤刪 Guard A 三段?

**A**: **PASS** (6/6 preserved; +0 new degradation in V055 SQL).

| Fix | Round 5 verify 方法 | 結果 |
|---|---|---|
| **C-1** (round 2): expires_at column 不寫 mlde_shadow_recommendations | E2 round 5 grep V055 INSERT body line 422-471：3 column (`evidence_source_tier` / `replay_experiment_id` / `manifest_hash`) 在；0 `expires_at` column 字面在 INSERT body | ✅ PASS |
| **C-2** (round 2): identity_arguments + strict equality | grep V055 line 597 `pg_get_function_identity_arguments` + line 603 `<>` strict equality + round 4 hotfix expected_string with-arg-names 格式 line 543-551 | ✅ PASS |
| **C-3** (round 3): no phantom column actor_id | V055 SQL 0 actor_id hit (round 5 drop stub block，phantom 隨之自然消失於 V055 SQL 內) | ✅ PASS in V055 SQL（但 sibling test 仍含，見 C-4 NEW finding） |
| **H-1** (round 2): no silent skip | V055 SQL 0 EXCEPTION WHEN OTHERS hit；drop smoke entirely → 不引入 EXCEPTION block → H-1 自動延續 | ✅ PASS |
| **M-1** (round 2): sign-off mock-only doc | E1 round 5 §16.5 explicit「sibling test 4 path 是 mock-only 鏡射；live PG 真實 INSERT only test_v055_live_pg_*」 | ✅ PASS |
| **M-2** (round 2): V049 NOT NULL set documented | V049 source still has 25 ADD COLUMN all NULLABLE; sibling test_v055_v049_source_not_null_invariant 仍 PASS | ✅ PASS (相關 stub 隨 round 5 design pivot 移除，但 V049 schema doc 仍 documented) |
| **R4 hotfix** (round 4): expected_string with-arg-names | V055 line 543-551 v_expected_identity_args 含 `p_engine_mode text, p_symbol text, ..., p_intent_id text` 19 token | ✅ PASS |

Guard A 三段（line 552-612）全保留：
- Line 553-563 function existence check
- Line 565-577 pronargs = 19 check
- Line 579-609 identity_arguments byte-equal V036（含 round 4 fix expected_string format）

V055 INSERT body line 422-471 全保留 (3 column 寫入 + 17 column total 對齊 V036)。

### Q3: 4 SQL static-parse test 升級是否真實對齊 round 5 現實 — case 命名是否仍語意一致?

**A**: **PASS for assertion logic** + **PARTIAL FAIL for naming consistency**.

E1 round 5 升級的 4 test：
1. `test_v055_idempotent_apply` (line 585) — round 5 加 0 SAVEPOINT v055_smoke + 0 ROLLBACK TO SAVEPOINT v055_smoke 殘留檢查 ✅ assertion 對齊 round 5 現實
2. `test_v055_4_path_smoke_in_guard_a` (line 828) — 整 test 升級為 verify round 5 design pivot section 雙語 + 0 SAVEPOINT 殘留 + 4 sibling test name reference + OPENCLAW_TEST_LIVE_PG env reference + 4 tier 字串仍在 doc comments ✅ assertion 對齊
3. `test_v055_v049_not_null_set_documented` (line 939) — 升級為 0 stub INSERT INTO replay.experiments 殘留 + Round 5 design pivot section 在 file header ✅ assertion 對齊
4. `test_v055_stub_columns_exist_in_v049` (line 1036) — 升級為 0 stub INSERT 殘留 + actor_id phantom column 從根 eliminated（V055 SQL 內）+ V049/V041 schema parse 仍可解析 ✅ assertion 對齊

**PARTIAL FAIL — 命名不一致**：
- `test_v055_4_path_smoke_in_guard_a` (line 828) 名 contains `smoke_in_guard_a` 但 round 5 已 drop in-migration smoke；E1 自承 (line 829-861 docstring)「本 test (round 5 升級) 改驗 V055 SQL ... 0 SAVEPOINT v055_smoke 殘留」— 名稱與實際 assertion 矛盾 (Guard A round 5 不再有 smoke)；E1 round 5 §16.5 修法表格亦標明「整 test 升級驗 round 5 design pivot section ...」未重命名
- `test_v055_v049_not_null_set_documented` (line 939) — 名為「v049_not_null_set_documented」但 round 5 升級後 assertion 的核心是「0 stub INSERT 殘留 + design pivot section 存在」，與「V049 NOT NULL set」語意已脫節
- `test_v055_stub_columns_exist_in_v049` (line 1036) — 名為「stub_columns_exist_in_v049」但 round 5 後 V055 SQL 0 stub INSERT，本 test assertion 主要驗「0 stub INSERT 殘留 + V049/V041 schema parse 仍可解析（為 sibling test 保留）」，與「stub columns exist in v049」語意半矛盾（test 自身也 explicit 不再有 stub）

E2 round 5 verdict on naming: dispatch §2 explicit「如 E2 應 push back 重命名 (如 `test_v055_no_in_migration_smoke_round5_pivot` 或 `test_v055_smoke_dropped_per_pl_pgsql_constraint`)」— E1 round 5 未重命名是 minor governance debt，但 E1 sign-off §16.5 explicit 自承 trade-off「最小改動原則」。**E2 round 5 評估**：命名 drift 是 LOW severity finding（assertion logic 仍 valid，未來閱讀者透過 docstring 可理解 round 5 升級語意），E2 round 5 **不單獨 RETURN 命名 issue**（per E2 LOW severity rule = 退回 OR E2 直修；考慮命名 drift 涉 4 test rename + impact summary count test，由 E1 round 6 一併處理較乾淨）。

→ Round 5 4 test 升級 logic 對齊 PASS；命名 LOW debt 建議 E1 round 6 順手 rename 或派 P3 ticket 後續處理。

### Q4: Python sibling test 4 path case 在 OPENCLAW_TEST_LIVE_PG=1 是否真有 INSERT + SELECT + 4 column verify (而非 mock-only)?

**A**: **CRITICAL FAIL** — round 5 design pivot's coverage migration premise 真實**有缺**.

**對抗驗 1：4 hermetic path test 真實是 mock-only**
- `test_v055_real_outcome_path` (line 332-370): `_mock_verify_and_insert(...)` Python mirror，`_row_capture` dict capture，**0 真 PG INSERT**
- `test_v055_calibrated_replay_path` (line 378-418): 同上 mock pattern
- `test_v055_synthetic_replay_path` (line 426-463): 同上 mock pattern
- `test_v055_counterfactual_replay_path` (line 471-508): 同上 mock pattern
- 4 case 預設 Mac 跑 + Linux 跑 全用 mock — **不需** OPENCLAW_TEST_LIVE_PG=1 就跑（Mac pytest round 5 baseline 4 case PASS 是 mock layer），與 dispatch §3 描述「OPENCLAW_TEST_LIVE_PG=1 真 PG INSERT」不符

**對抗驗 2：live_pg case 真實只 cover 2 tier (real_outcome + calibrated_replay)；不是 dispatch §3 binding 的 4-tier**
- `test_v055_live_pg_real_outcome_row_body` (line 1163): 真 PG INSERT real_outcome path；**clean** (不需 stub experiment 因 real_outcome 不寫 exp_id+hash)
- `test_v055_live_pg_calibrated_replay_row_body` (line 1217): 真 PG INSERT calibrated_replay path + 內部 stub experiment INSERT；**有 C-3 phantom column actor_id bug 在 line 1252**（**詳 FINDING C-4 NEW**）
- **0 synthetic_replay 真 PG case + 0 counterfactual_replay 真 PG case**

dispatch §3 binding 「每 case 確實 INSERT + SELECT + 4 column verify（不只 mock，含真 PG 真 INSERT under OPENCLAW_TEST_LIVE_PG=1）」**未真實達成**：
- 4 hermetic case 全 mock（不需 OPENCLAW_TEST_LIVE_PG=1）
- 2 live_pg case 之一 broken (calibrated_replay 撞 actor_id)，另一 (real_outcome) clean
- 0 synthetic_replay live PG case + 0 counterfactual_replay live PG case

**E1 round 5 §16.4 表格 misleading**：
> | Test name | 覆蓋 path | INSERT + SELECT row body 對齊 args |
> | `test_v055_real_outcome_path` | real_outcome | tier='real_outcome' + ... |

§16.4 表格說 4 hermetic case「INSERT + SELECT row body 對齊 args」— 但實際 4 case 是 **mock-only INSERT + mock _row_capture 對齊**，**不是真 PG INSERT + SELECT**。E1 §16.4 表格 wording 與 mock layer 實況有 gap，建議訂正為「mock-only INSERT + _row_capture 對齊」+ 補列「真 PG INSERT 只 2 case (real_outcome live_pg + calibrated_replay live_pg)」+ 加「synthetic_replay live_pg + counterfactual_replay live_pg 為 round 5 design pivot 後仍缺的 binding gap」P2 ticket 提案。

→ **C-4 NEW (CRITICAL)** + Q4 揭露 round 5 coverage migration shortfall（實際真 PG live coverage = 2 tier；dispatch §3 binding 4-tier）

### Q5: LOC 715 對 round 4 913 = -198 — 是否合理 (drop smoke 預估 ~200 LOC)?

**A**: **PASS** (within reason; -198 vs predicted -300; gap +102 LOC reasonable for design-pivot bilingual doc additions).

E1 §16.6 自承「dispatch §1 預期 V055 913 → ~600 (-300)。實際 -198 因加 round 5 design pivot 雙語 section（70 LOC）+ Operator note 雙語擴展（10 LOC）+ (REMOVED) breadcrumb 註解（30 LOC）」。

E2 round 5 對抗驗：
- Round 4 913 → round 5 715 = -198 LOC
- Drop smoke 真實救 ~270 LOC actual code（line 615-672 round 4 4-tier smoke + stub INSERT + 4 path SELECT + EXCEPTION block + ROLLBACK TO SAVEPOINT — 全 drop）
- Add round 5 design pivot bilingual section ~70 LOC (line 114-151 file header + 614-674 inline section)
- Add round 5 design pivot Operator note 第 4 點雙語 ~12 LOC (line 689-714)
- Net: -270 + 70 + 12 = **-188 LOC** (誤差 +10 LOC 為 Format/blank 細節差，可接受)

E1 §16.6 預估 -270 + 110 = -160；實際 -198；gap +38 LOC = E1 預估略 conservative；E2 round 5 接受作 reasonable engineering estimate。**0 隱性新 logic** 引入。

V055 LOC 715 < §九 2000 cap (large headroom)；test LOC 1316 < §九 2000 cap (large headroom)。

→ Round 5 LOC delta within reason，0 governance violation。

---

## Round 5 NEW Findings 總表

### FINDING C-4（NEW CRITICAL）— sibling test live_pg stub INSERT phantom column carry-over

| 嚴重性 | 位置 | 描述 |
|---|---|---|
| **CRITICAL** | `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_v055_evidence_insert_fix.py:1252` (within `test_v055_live_pg_calibrated_replay_row_body` 1217-1296) | Round 5 design pivot 將 4-tier post-INSERT path verification 由 in-migration smoke 遷至 sibling Python test (E1 §16.4 explicit binding)；live_pg 路徑是 round 5 後 calibrated_replay tier 的**唯一**真 PG verification surface (4 hermetic case 是 mock-only)。但 line 1252 stub INSERT 仍含 round 2-3 已知 phantom column `actor_id`：`INSERT INTO replay.experiments (experiment_id, actor_id, status, created_at, half_life_days, embargo_days, runtime_environment) VALUES (...)`。Round 3 fix C-3 修了 V055 SQL 內 stub block actor_id phantom，但同 phantom 在 sibling test live_pg 路徑**仍 alive**。E1 round 5 §16.4 自描述「4-tier path verification migrated to Python sibling test under OPENCLAW_TEST_LIVE_PG=1」— Linux PG 16 跑 OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN env，line 1252 INSERT 必撞 PG `column "actor_id" of relation "experiments" does not exist`（V049 line 282-307 ADD COLUMN list 真實命名 `created_by` line 284，V045:199 actor_id 是 `replay.run_state` 表 column、與 `replay.experiments` 無關）。E2 round 3 finding C-3 揭發此 phantom 後，round 3 sign-off § 14.6.2 + V055 SQL line 707 stub INSERT block 已修，但**未同步審 sibling test 自身的 stub INSERT**。Round 5 design pivot 將 coverage 遷至 sibling test，提升 sibling test 從「Mac dev 取代 doc」到「round 5 後唯一 calibrated_replay 真 PG verification path」— phantom column risk 從 V055 SQL「migration deploy 端」遷至 sibling test「Linux E4 regression 端」未隨之 catch + fix。Round 5 design pivot 有效性實證**0 calibrated_replay live_pg verification 真實成立**（round 5 §16.5 自表「sibling test 4 path 已等價覆蓋」名義成立但實際被 phantom column carry-over 蝕空）。同時 E1 round 5 §16.5 自相矛盾於 line 1042 docstring「round 5 (2026-05-05): in-migration ... drop ... actor_id phantom column risk goes away with stub INSERT removal」— **但 stub INSERT removal 只發生於 V055 SQL，sibling test 內 stub INSERT 仍 alive**。 |

**對抗驗證真實性 (E2 round 5 自跑)**：

```bash
$ grep -n "actor_id" .../test_v055_evidence_insert_fix.py | tail -1
1252:                        experiment_id, actor_id, status, created_at,

$ sed -n '1248,1265p' .../test_v055_evidence_insert_fix.py
                # via runtime_environment='mac_dev_smoke_test_only'
                cur.execute(
                    """
                    INSERT INTO replay.experiments (
                        experiment_id, actor_id, status, created_at,
                        half_life_days, embargo_days, runtime_environment
                    ) VALUES (
                        %s, 'v055_live_smoke', 'created', now(),
                        14.0, 14, 'mac_dev_smoke_test_only'
                    )
                    ON CONFLICT (experiment_id) DO NOTHING
                    """,
                    (test_exp_id,),
                )
```

對 V049 ADD COLUMN list cross-validate：
```sql
-- V049 line 282-307 ADD COLUMN 25 columns: parent_experiment_id, created_by, runtime_environment, ..., status, output_policy_jsonb
-- 0 actor_id in V049 schema
```

→ Linux PG 16 OPENCLAW_TEST_LIVE_PG=1 跑 `test_v055_live_pg_calibrated_replay_row_body` 必失敗於 stub INSERT step (line 1244-1261)，無法進到 verify_replay_evidence_and_insert call (line 1263-1273) → calibrated_replay tier 真 PG verification 等於 0。

**修法建議 (E1 round 6 必修)**：

修 line 1251-1261 stub INSERT 移除 `actor_id` 改用 `created_by` 對齊 V049:284 真實 column name：
```python
cur.execute(
    """
    INSERT INTO replay.experiments (
        experiment_id, created_by, status, created_at,
        half_life_days, embargo_days, runtime_environment
    ) VALUES (
        %s, 'v055_live_smoke', 'created', now(),
        14.0, 14, 'mac_dev_smoke_test_only'
    )
    ON CONFLICT (experiment_id) DO NOTHING
    """,
    (test_exp_id,),
)
```
（同 round 3 V055 SQL 內 stub fix 的修法）

順手檢查 + 同步修：
1. Line 1247-1248 Round 2 fix 注釋訂正：「stub 含 V049 conditional NOT NULL bypass via runtime_environment='mac_dev_smoke_test_only'」訂正為「(round 6 fix per round 5 E2 finding C-4): stub 用 V049:284 真實 column `created_by` (V045:199 `replay.run_state.actor_id` 與此表無關)」雙語雙保險
2. **新加** synthetic_replay live_pg case 與 counterfactual_replay live_pg case（dispatch §3 binding「4 case」+ round 5 §16.4 「Python sibling test 4 path 已等價覆蓋」claim 完整兌現）。預估 ~80-100 LOC 新增，仍 < §九 2000 cap。
   - Option A（推薦）：派 round 6 一併補上
   - Option B：作 round 5 P2 ticket 補做（dispatch §6.4 binding 仍未完整滿足；建議不採此 option）

**為何 round 1-4 沒 catch**：
- Round 1-4 E2 finding 全聚焦 V055 SQL 內 stub INSERT 的 phantom（C-3）
- Sibling test stub INSERT line 1244-1261 是 **round 2 加的** (per round 2 sign-off §13.3 「4-tier sibling test cases」block)，與 V055 SQL stub INSERT 同期 land
- Round 3 fix C-3 在 V055 SQL 內 land 但**未 cross-check sibling test 內同等 stub INSERT 是否帶 phantom**
- Round 4 hotfix 純解 expected_string format drift，不觸 stub
- Round 5 design pivot 把 V055 SQL stub INSERT 整段 drop（stub 隨 smoke 一起移除），但**從未 audit sibling test 自身的 stub INSERT 是否同等乾淨**
- E1 round 5 §16.5 line 1042 自承「actor_id phantom column risk goes away with stub INSERT removal」— 此聲明只 apply V055 SQL，未 verify sibling test (E1 自身盲點)

**E2 round 5 認為**：round 5 design pivot 邏輯 sound (drop in-migration smoke + 遷至 sibling test 解 PL/pgSQL constraint 是合理 fix)，但 **coverage migration 的「驗收條件」設計不完整** — round 5 sign-off binding 應加「sibling test 內所有 stub INSERT cross-validate against V049 schema」步驟才能保 round 5 design pivot 的 coverage promise 真實成立。E1 round 6 必同時 fix line 1252 + 補 missing 2 tier (synthetic / counterfactual) live_pg case 才完整兌現 round 5 design pivot 的 coverage migration claim。

---

## Round 1-4 + Round 4 hotfix Findings 6 個 re-verify 結果

| # | Finding | Round 5 Status | 證據 |
|---|---|---|---|
| C-1 | expires_at column 不寫 mlde_shadow_recommendations | **VERIFIED PASS** | V055 INSERT body line 422-471 仍 3 column；0 expires_at 字面 |
| C-2 | identity_arguments + strict equality | **VERIFIED PASS** | line 597-609 strict equality 仍在 |
| C-3 | no phantom column actor_id (V055 SQL) | **VERIFIED PASS in V055 SQL** ✅ + **REGRESSED in sibling test** (NEW C-4 finding) | V055 SQL 0 actor_id；sibling test line 1252 actor_id alive |
| H-1 | no silent skip | **VERIFIED PASS** | drop smoke 後 0 EXCEPTION block (auto-extended fix) |
| M-1 | sign-off §13 訂正 | **VERIFIED PASS** | E1 round 5 §16.5 mock-only doc 對齊 |
| M-2 | V049 NOT NULL set documented | **VERIFIED PASS** | 25 ADD COLUMN 全 NULLABLE；test_v055_v049_source_not_null_invariant 仍 PASS |
| Round 4 hotfix | expected_string with-arg-names | **VERIFIED PASS** | line 543-551 with-arg-names format 保留 |

---

## Round 5 Findings 1 個

### CRITICAL (1)
- **C-4 (NEW)**: sibling test `test_v055_live_pg_calibrated_replay_row_body` line 1252 stub INSERT 仍含 phantom column `actor_id` (round 3 fix C-3 在 V055 SQL 已修但未同步 sibling test)；round 5 design pivot 把 calibrated_replay tier 真 PG verification 路徑遷至此 sibling test，phantom carry-over 等於 round 5 「sibling test 等價覆蓋」claim 在 calibrated_replay tier 失效 + Linux PG OPENCLAW_TEST_LIVE_PG=1 跑必撞 PG error；同時 round 5 design pivot 後缺 synthetic_replay + counterfactual_replay live_pg case，dispatch §3 binding「4 case INSERT + SELECT + 4 column verify under OPENCLAW_TEST_LIVE_PG=1」實際只 2 case (real_outcome live_pg + calibrated_replay live_pg) 且 後者 broken。

### LOW (governance debt, optional fix)
- 4 升級 SQL static-parse test 命名與 round 5 assertion 語意不完全一致（如 `test_v055_4_path_smoke_in_guard_a` 仍用「smoke_in_guard_a」字眼但 round 5 已 drop in-migration smoke）— E2 round 5 不 RETURN 此項，建議 E1 round 6 順手 rename 或派 P3 ticket。

---

## Round 5 結論

**RETURN-TO-E1 round 6** — 1 NEW CRITICAL finding (C-4)。

E1 round 5 design pivot 邏輯正確（PL/pgSQL constraint 確實 + drop smoke 是合理 fix），V055 SQL 內所有 round 1-4 + round 4 hotfix 6 fix 完整保留 0 regression。但 sibling test 自身的 stub INSERT 未隨 round 3 V055 SQL fix 同步修，round 5 design pivot 把 coverage 遷至 sibling test 後 phantom column risk 從 V055 SQL「deploy 端」**遷移**至 sibling test「E4 regression 端」未 catch。

直接結果：
- Linux PG 16 跑 OPENCLAW_TEST_LIVE_PG=1 `test_v055_live_pg_calibrated_replay_row_body` **必失敗於** stub INSERT step
- Round 5 §16.4 表格描述 4 path 「等價覆蓋」實質為 mock-only (4 hermetic case) + 2 live_pg case + 1 broken (calibrated)
- dispatch §3 binding「4 case INSERT + SELECT + 4 column verify under OPENCLAW_TEST_LIVE_PG=1」未完整達成：實際 = 2 live_pg case (1 clean + 1 broken)，0 synthetic_replay + 0 counterfactual_replay live_pg case

E2 round 5 對抗反問 §4 真實揭發此 coverage migration shortfall。E1 round 6 必同時 fix line 1252 + 補 2 missing live_pg tier case 才完整兌現 round 5 design pivot 的 coverage migration claim。

---

## Round 5 退回 E1 round 6 修復清單

### CRITICAL (必修，修完才能重 E2 round 6)

1. **FINDING C-4 — sibling test stub INSERT phantom column修復**
   - File: `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_v055_evidence_insert_fix.py`
   - Line 1252 INSERT INTO replay.experiments stub:
     ```python
     # 改前：
     INSERT INTO replay.experiments (
         experiment_id, actor_id, status, created_at,
         half_life_days, embargo_days, runtime_environment
     )
     # 改後：
     INSERT INTO replay.experiments (
         experiment_id, created_by, status, created_at,
         half_life_days, embargo_days, runtime_environment
     )
     ```
   - Line 1247-1248 round 2 fix 注釋同步訂正（標明 round 6 fix per round 5 E2 C-4）

2. **FINDING C-4 補完 — 補 synthetic_replay + counterfactual_replay live_pg case**
   - 新加 `test_v055_live_pg_synthetic_replay_row_body` (預估 ~50 LOC，patterns 對齊 calibrated_replay live_pg)
   - 新加 `test_v055_live_pg_counterfactual_replay_row_body` (預估 ~50 LOC，patterns 同上)
   - 兩 case 走相同 stub experiment INSERT (with `created_by` not `actor_id`) + verify_replay_evidence_and_insert call + SELECT 3 column verify pattern
   - test_v055_mock_mode_test_count_summary docstring 內 23 collected 訂正為 25 collected (4 → 6 live_pg case 升)

### LOW (optional governance debt, can defer to round 6 順手 fix or P3 ticket)

- 4 round 5 升級 test 命名訂正為 round 5-friendly 名（如 `test_v055_no_in_migration_smoke_round5_pivot`），E1 round 6 可順手 rename 或派 P3 ticket 後續處理

### Round 4 hotfix + Round 1+2+3 5 fix 全 verified, no further action

- C-1 (3-col INSERT): VERIFIED
- C-2 (identity_arguments strict equality): VERIFIED
- C-3 (no phantom column in V055 SQL): VERIFIED in V055 SQL（但 sibling test 同等 phantom 仍在，見 C-4）
- H-1 (no silent skip): VERIFIED
- M-1 (sign-off §13/§14/§16 mock-only doc): VERIFIED
- M-2 (V049 NOT NULL set documented): VERIFIED
- Round 4 hotfix (expected_string with-arg-names format): VERIFIED

### REF-20_RESERVATION.md ledger 訂正（PM action at commit time）

E1 round 5 不修 ledger（dispatch §「不動」邊界）。PM closure phase 統一更新：
- v1.10 entry 「INSERT body 加 4 column」→「INSERT body 加 3 column」
- v1.10 entry 「graceful skip 4-tier smoke」→「round 5 design pivot drop 4-tier smoke entirely (PL/pgSQL constraint)；4-tier path verification 遷至 Python sibling test under OPENCLAW_TEST_LIVE_PG=1」
- v1.10 entry 「16 PASS / 2 SKIPPED」→「23 PASS / 2 SKIPPED」（round 6 fix 後升 25 PASS / 2 SKIPPED）
- v1.10 entry V049 ADD COLUMN「18」→「25」(round 3 push back 已揭，round 5 確認)
- 加 v1.11/v1.12 entry 標 round 4 hotfix + round 5 design pivot 兩條 line item

---

## Round 5 重 E2 round 6 條件

E1 修完 C-4 finding + 補 2 missing live_pg case 後：
- 重新 sign-off 報告（appended §17 round 6 fix description）
- E2 round 6 review 重跑（重點 = sibling test stub INSERT cross-validation against V049 schema + 25 collected pytest baseline）
- 若 round 6 fix 結束 0 NEW finding → APPROVE-FOR-E4 → E4 regression Linux SSH bridge apply OPENCLAW_TEST_LIVE_PG=1 跑 25/23/2 PASS（含新 2 live_pg case）

**注**：E2 round 6 不需重審 round 5 已 verified 的 6 fix（C-1/C-2/C-3-V055/H-1/M-1/M-2/round 4 hotfix），除非 round 6 改動觸發 cross-cutting regression。

---

E2 ROUND 5 REVIEW DONE: report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_c_r6t0prime_v055_e2_review.md`; verdict: **RETURN-TO-E1 round 6**; findings: **1 NEW CRITICAL (C-4 sibling test stub phantom column carry-over + missing 2 live_pg tier case)**; pending E1 round 6 fix; PM action (closure phase): REF-20_RESERVATION ledger v1.10 entry 訂正 (4 col → 3 col / graceful skip → round 5 design pivot / 16 PASS → **25 PASS** post round 6 / V049 ADD COLUMN count 18 → 25) at commit phase
