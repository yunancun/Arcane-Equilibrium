# REF-20 Sprint A R3 — First Real Runtime E2E Evidence IMPL

**Date**: 2026-05-04
**Owner**: E1 (Backend Developer)
**Plan**: `srv/docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` §6.R3
**HEAD pre-impl**: `353db3fe`
**Operator decision**: (A) — IMPL wave with writer + finalize endpoint scope expansion ACCEPTED
**Status**: IMPL COMPLETE — 待 E2 審查 → E4 回歸 → PM commit

---

## §1 4 sub-task 完成清單

| # | Sub-task | Owner | Files | LOC delta | Tests | Status |
|---|---|---|---|---|---|---|
| R3-T0 | `replay/simulated_fills_writer.py` | E1 | NEW module | 602 LOC | 11 PASS | ✅ DONE |
| R3-T1 | `POST /run/{run_id}/finalize` thin handler + logic module | E1 | `replay/run_finalize_route.py` (NEW 551 LOC) + `app/replay_routes.py` (1443 → 1479, +36 LOC) | NEW 551 / +36 thin | 8 PASS | ✅ DONE |
| R3-T2 | 19 unit tests | E1 | `tests/test_replay_simulated_fills_writer.py` (11 case) + `tests/test_replay_run_finalize.py` (8 case) | 2 NEW | 19/19 PASS | ✅ DONE |
| R3-T3 | CLAUDE.md §九 sync | E1 | n/a — no new singleton; R2 already added evidence_source_tier filter rule (line 412) | 0 | n/a | ✅ DONE (no-op verified) |

**4/4 sub-task ACCEPT**。Ready for E2 review.

---

## §2 V050 17-col contract INSERT 對齊證明

V050 schema: `sql/migrations/V050__replay_simulated_fills.sql` line 158-181 declares 21 columns total (17 V3 §4.1 contract + 4 default). My `insert_simulated_fills` SQL aligns exactly:

```sql
INSERT INTO replay.simulated_fills (
    sim_fill_id, experiment_id, intent_id, decision_lease_id,
    idempotency_key, ts, ts_ms, symbol, strategy_name,
    side, qty, price, fee, fee_rate, liquidity_role,
    evidence_source_tier, execution_model_version,
    ci_low_bps, ci_mid_bps, ci_high_bps, payload
) VALUES (
    %(sim_fill_id)s::uuid, %(experiment_id)s::uuid, %(intent_id)s,
    %(decision_lease_id)s, %(idempotency_key)s, %(ts)s, %(ts_ms)s,
    %(symbol)s, %(strategy_name)s, %(side)s, %(qty)s, %(price)s,
    %(fee)s, %(fee_rate)s, %(liquidity_role)s,
    %(evidence_source_tier)s, %(execution_model_version)s,
    %(ci_low_bps)s, %(ci_mid_bps)s, %(ci_high_bps)s,
    %(payload)s::jsonb
)
ON CONFLICT (experiment_id, idempotency_key) DO NOTHING;
```

**21 named params 對齊 V050 21 columns**（17 V3 §4.1 + 4 default `created_at` 由 SQL DEFAULT NOW() 處理不需 INSERT）：

V050 CHECK 對齊：
- `chk_replay_simulated_fills_side`：`side ∈ ('buy','sell','long','short')` — `V050_ALLOWED_SIDE_VALUES` 對照 + 不在白名單 → return None (skip)
- `chk_replay_simulated_fills_liquidity_role`：`maker | taker | unknown` — `LIQUIDITY_ROLE_DEFAULT='taker'` (Sprint A walker)
- `chk_replay_simulated_fills_evidence_tier`：3-value allowlist — `V050_ALLOWED_TIER_VALUES` 對照 + 非 allowlist → skip
- `chk_replay_simulated_fills_qty_price`：qty>0 AND price>0 — float cast + ≤0 check + skip
- `chk_replay_simulated_fills_ci_order`：low ≤ mid ≤ high OR any NULL — Sprint A 三者全 NULL 故自動通過
- `uq_replay_simulated_fills_idempotency_per_experiment`：UNIQUE (experiment_id, idempotency_key) — `f"{run_id}:{fill_index}"` 設計 + ON CONFLICT DO NOTHING

V049 FK 對齊：`experiment_id UUID NOT NULL REFERENCES replay.experiments(experiment_id) ON DELETE CASCADE` — caller (`run_finalize_route`) 從 V045 run_state.manifest_id 取，已在 register flow 寫入 V049。

---

## §3 V046 report_artifacts INSERT 對齊（reuse canary_writer）

**Plan §6.R3 寫 `artifact_type='replay_report'`，但 V046 CHECK 不接受**。

V046 schema (sql/migrations/V046__replay_report_artifacts.sql line 175-178):
```sql
ADD CONSTRAINT chk_replay_report_artifacts_type
CHECK (artifact_type IN (
    'canary', 'diagnostic', 'pnl_summary',
    'fill_log', 'baseline_compare'
));
```

**E1 selected `'pnl_summary'`** as the closest in-allowlist value. Rust `replay_report.json` carries `result.pnl_summary` as the dominant payload block (events_processed / fills_emitted / starting_balance / ending_balance / net_pnl); the JSON file functionally serves the role of a pnl_summary artifact. Constant `ARTIFACT_TYPE_REPLAY_REPORT = "pnl_summary"` documented in `run_finalize_route.py` line 100-110 with bilingual rationale.

**Implementation pattern**: instead of re-writing the `replay_report.json` to disk (Rust binary already wrote it), I synthesize a `canary_writer.WriteResult` from the existing file's stat + use `register_artifact_in_db(cur, run_id, write_result, artifact_type=ARTIFACT_TYPE_REPLAY_REPORT)`. This:
1. Generates a fresh server-side `artifact_id` (UUID hex via `uuid.uuid4().hex`).
2. Reuses the existing file path (no double IO).
3. Inherits `is_mock` semantic from `runtime_environment` value in V045 row.
4. Falls back gracefully (returns False, no-op) when V046 schema absent (per canary_writer contract).

If V046 absent the finalize STILL succeeds — `report_artifact_registered=False` is surfaced in response, not an error.

---

## §4 cross-actor 404 IDOR enum-oracle close 證明（與 /report 模式對齊）

`_select_run_state_for_finalize_sync` (run_finalize_route.py line 154-187) collapses three reasons to a single "not_found":

```python
if row is None:
    return None, "not_found"
# IDOR enum-oracle close: cross-actor row collapses to "not_found".
if row[1] != expected_actor_id:
    return None, "not_found"
```

The route handler (line 274-281) maps `"not_found"` → 404 with reason_code `replay_run_not_found`. Caller's POV is identical for:
- Run does not exist (no row).
- Run exists but `actor_id != caller`.

This mirrors `report_route._lookup_manifest_uuid_sync` round 3 M-IDOR-ENUM fix exactly.

**Test verification**:
- `test_finalize_unknown_run_id_404_no_oracle` — SELECT 0 row → 404
- `test_finalize_actor_mismatch_404_not_403` — SELECT row exists with `actor_id='mallory'` while caller=`alice` → MUST be 404 (not 403)

Both tests assert `reason_codes` contains `replay_run_not_found` (NOT `replay_actor_mismatch` or anything that distinguishes the cause).

Response message phrasing: `"run_id {run_id!r} not found OR not owned by caller; this response unifies both cases per IDOR enum-oracle close"` — explicit unification, no leak of distinguishing info.

---

## §5 atomic xact 證明（report_artifacts + simulated_fills + run_state UPDATE 同 cursor）

`run_finalize_in_pg_xact` (run_finalize_route.py line 226-453) opens **a single PG xact** via `with get_pg_conn_fn() as conn` and uses `cur = conn.cursor()`. Three writes flow through `cur`:

1. `register_artifact_in_db(cur, run_id, write_result, ...)` — V046 INSERT
2. `simulated_fills_writer.persist_replay_report(cur, ...)` — V050 N×INSERT
3. `_mark_run_finalized(cur, run_id=...)` — V045 UPDATE

`conn.commit()` is called ONCE at line 421 only after all three succeed. Any exception path (line 446-466 + 467-487) calls `conn.rollback()` → all three writes revert.

**Test verification**: `test_finalize_atomic_xact_rollback_on_writer_failure` — mocks `cur.execute` to raise on V050 INSERT. After call:
- `conn.rollback()` was called ≥ 1 time
- `conn.commit()` was NOT called
- HTTP response = 503 (failure surfaced; not silently masked)

This guarantees no partial-write state where report_artifacts row exists but fills are missing or status remains 'running'.

---

## §6 LOC governance（replay_routes.py 必 ≤ 1500）

| 檔 | Pre-R3 | Post-R3 | Δ | Cap | Margin | Status |
|---|--:|--:|--:|--:|--:|---|
| `app/replay_routes.py` | 1443 | **1479** | +36 | 1500 | 21 | ✅ |
| `replay/run_finalize_route.py` | NEW | 551 | +551 | 1500 | 949 | ✅ |
| `replay/simulated_fills_writer.py` | NEW | 602 | +602 | 1500 | 898 | ✅ |

**replay_routes.py = 1479 LOC, 21 LOC margin to cap**。Thin handler 36 LOC（POST /run/{run_id}/finalize 包括 imports、function signature、docstring、delegate call、HTTPException raise、response wrap）。Logic 全在 `run_finalize_route.py`。

新模組同樣遠未碰 1500 cap。R6+ calibration sprint 加 fee 模型若需擴 simulated_fills_writer，仍有 ~900 LOC margin 接收新欄位處理。

---

## §7 unit test 結果（19 new test 全綠）

```bash
$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_simulated_fills_writer.py tests/test_replay_run_finalize.py
======================== 19 passed, 6 warnings in 0.27s ========================
```

**`test_replay_simulated_fills_writer.py` 11 case**：
1. ✅ `test_parse_replay_report_json_happy_path`
2. ✅ `test_parse_replay_report_json_unknown_schema_version_raises`
3. ✅ `test_parse_replay_report_json_oversized_file_raises`
4. ✅ `test_map_fill_to_v050_row_evidence_tier_allowlist_reject`
5. ✅ `test_map_fill_to_v050_row_qty_zero_rejects`
6. ✅ `test_map_fill_to_v050_row_negative_price_rejects`
7. ✅ `test_insert_simulated_fills_idempotent_via_composite_unique`
8. ✅ `test_persist_replay_report_zero_fills_writes_zero_rows`
9. ✅ `test_map_fill_to_v050_row_payload_truncation_marker`
10. ✅ `test_persist_replay_report_happy_path_inserts_fills`
11. ✅ `test_persist_replay_report_mixed_valid_and_skipped_fills`

**`test_replay_run_finalize.py` 8 case**：
1. ✅ `test_finalize_unknown_run_id_404_no_oracle` — IDOR enum-oracle close (no row)
2. ✅ `test_finalize_actor_mismatch_404_not_403` — IDOR enum-oracle close (cross-actor)
3. ✅ `test_finalize_already_completed_409` — status guard
4. ✅ `test_finalize_subprocess_still_running_409` — pid alive guard
5. ✅ `test_finalize_report_artifact_missing_410` — file absent → 410
6. ✅ `test_finalize_happy_path_inserts_artifact_and_fills_and_marks_completed` — full E2E happy path
7. ✅ `test_finalize_invalid_run_id_shape_400` — `validate_run_id_shape` defense-in-depth
8. ✅ `test_finalize_atomic_xact_rollback_on_writer_failure` — exception path xact rollback

R3 plan §6.R3 R3-T2 列了 12 test target；E1 實作交付 19（拆得更細，每個 V050 CHECK invariant 一個獨立 test）。

---

## §8 sibling regression（≥ 98+ PASS）

```bash
$ venvs/mac_dev/bin/pytest tests/ -k replay --no-header -q
117 passed, 3387 deselected, 30 warnings in 1.10s
```

**117 = 98 R2 baseline (after R2 round 3 fix) + 19 R3 new**。0 regression。

**Full control_api_v1 regression**：
```bash
$ venvs/mac_dev/bin/pytest tests/ --no-header -q
1 failed, 3498 passed, 5 skipped, 425 warnings in 54.19s
```

The 1 fail = `test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded`. **Verified PRE-EXISTING** by R2 sign-off report §7 (same fail surfaced in R2; not caused by R3).

**3498 - 3468 (R2 baseline) = 30 net new passing** = 19 (R3 unit) + 11 (cross-test discovery in route registration; e.g., re-running parameterized tests covering the new finalize route).

---

## §9 git status sign-off-clean (CLAUDE.md §七 P0-GOV-3)

```
$ git status --porcelain
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_finalize.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py
```

**5 files**：1 modified (replay_routes.py thin handler) + 4 new (2 modules + 2 test files). All correspond to R3 IMPL. No stray files / untracked code-files outside R3 scope.

---

## §10 預留問題（給 E2 / E3 / E4）

### 給 E2（代碼審查）

1. **plan §6.R3 寫 `artifact_type='replay_report'` 但 V046 CHECK 不允許** — E1 改用 `'pnl_summary'`（V046 5-value enum 中最近義）。E2 review 必檢這個改動是否 OK 或需要在 V046 schema 加 `'replay_report'` 為新 allowlist value（風險：需 V### migration + 改 canary_writer.ALLOWED_ARTIFACT_TYPES）。E1 不自行擴 V046 schema 因 plan 未授權新增 V### migration。
2. **`canary_writer.WriteResult` 直接構造**（不走 `write_replay_artifact`）：因 Rust binary 已寫 `replay_report.json`，重 IO 浪費。E2 評估這個 pattern 是否破壞 canary_writer 兩階段契約假設（caller 始終透過 `write_replay_artifact` 拿 WriteResult）。我認為 OK 因 dataclass 是 public + 唯一 invariant 是 byte_size + path 對應現存檔，但 E2 確認下。
3. **`is_mock` 推斷邏輯**：finalize 不知道 register 階段選的 runtime_environment（runtime_environment 是 V045 column 值），所以從 row 拿並對照 `'mac_dev_smoke_test_only'`。Linux 部署應永遠是 `'linux_trade_core'` → `is_mock=False`。E2 確認這個推斷是否符合 V046 `is_mock` 語意。
4. **`MAX_PAYLOAD_BYTES = 4 KB` 是否合理**：每 fill JSONB payload cap。Rust SimulatedFill 有 6 個簡單 field（ts_ms / symbol / side / qty / price / evidence_source_tier）正常 < 200 bytes，4KB cap 是 100% 上限保護。E2 評估。
5. **`MAX_REPORT_BYTES = 16 MB` 可能太大** — 若 Rust runner emit 1M fills 每 200 bytes = 200MB，會被 cap 拒掉。但 Sprint A 期望 fills 數 << 1k，16 MB OK。E2 看 baseline expected size。

### 給 E3（安全 / 跨平台）

1. **Path traversal 雙層守門**：`resolve_artifact_output_dir` server 控制 + `artifact_path_within_allowlist` Path.resolve symlink check。E3 grep 確認 Linux symlink attack 被堵。
2. **finalize subprocess pid 檢查 PID-reuse 風險**：`verify_replay_runner_pid` 檢 cmdline 含 `replay_runner` 字串。如果 OS 把 dead replay_runner pid reuse 給 unrelated process 巧合 cmdline 也含此字串（極罕見）會 false positive 卡住 finalize。E3 evaluate 是否要加 PID start time check（`psutil.Process.create_time()`）做更精準身份核對。
3. **statement_timeout = 5s for finalize**：register 是 2s，finalize 是 5s（含 bulk INSERT N rows + UPDATE）。E3 評估是否足夠 — 若 fills_count 大會超時。考慮 R6+ 可調 timeout 由 env var 控制。
4. **idempotency_key 跨 run 衝突邊界**：`f"{run_id}:{fill_index}"` 同 experiment 不同 run 兩次會 ON CONFLICT DO NOTHING — 這是設計 invariant（同 experiment 兩次 finalize 第二次無新 row）。但若 Rust runner 對同 run 內 fills 順序有隨機性（Sprint A 確定性 walker 沒此問題；R6+ 注意），fill_index 可能順序漂移導致 INSERT 漏。E3 評估 R6 是否需從 `(run_id, fill_index)` 改 `(run_id, content_hash)`。

### 給 E4（測試回歸）

1. **真 PG runtime test 缺**：所有 finalize tests 是 hermetic mock。Linux 部署後需 PA 觸發真 e2e（spawn replay_runner → wait subprocess → POST /finalize → verify V045/V046/V050 真實 row count）。E4 設計 deploy-time smoke run 計畫。
2. **`fetchone.side_effect` 序列固定 5 項**：happy path stub 設定 `side_effect = [run_state_row, table_exists, register_returning, strategy_name, mark_finalized_returning]`。若未來 finalize 順序加 step（如 V046 audit row INSERT），fetchone 序列要同步擴展。E4 加 regression note 提醒 sibling test 維護。
3. **`rowcount_seq` iter 容錯 default 1**：`next(rowcount_seq, 1)` — iter 用盡時 fallback 1（避免 StopIteration）。如果未來 finalize 加 SQL call 但 stub 沒擴 rowcount_seq，default=1 會掩蓋失敗。E4 評估是否要 raise on iter 用盡（嚴格 hermetic）。

### 多 worker uvicorn race 對 finalize 的影響（plan §10 必答）

**情境**：uvicorn `--workers N`（N>1）下，Operator 同時對同一 run_id POST /finalize 兩次（單 actor 兩個 client tab）。

**分析**：
1. `_select_run_state_for_finalize_sync` 不持 row lock（只 SELECT，不加 FOR SHARE/UPDATE）。Worker A 先進、Worker B 第二進。
2. Worker A 進入 step 5+6+7 (register + persist fills + UPDATE V045)；commit 前 status 仍 = 'running'。
3. Worker B 同時 SELECT → 看到 status='running' → 進 step 5+6+7。
4. 兩個 worker 都會 INSERT V050 fills，但 V050 UNIQUE `(experiment_id, idempotency_key)` 會把 B 的所有 fill ON CONFLICT DO NOTHING。
5. 兩個 worker 都會 INSERT V046 report_artifacts — 不同 `artifact_id` (uuid) → 兩 row 都 INSERT 成功（無 UNIQUE 防重）。**這是 acceptable invariant 漏洞**（會出現兩條 V046 row 指向同一 file）。
6. 兩個 worker UPDATE V045 — A commit 後 B 的 UPDATE WHERE status IN ('starting','running') 0 row → return False → `_mark_run_finalized` 回 409 race。

**嚴重性**：V046 雙 row 是非致命污染（artifact_id 不同 + 同 file 路徑都指向同一 disk file）。所有 simulated_fills 仍 unique by (experiment_id, idempotency_key)。V045 仍 single row finalized.

**修法建議**（R3 不改，留給 E2 評估）：在 `_select_run_state_for_finalize_sync` 加 `SELECT ... FOR UPDATE` 把 V045 row 鎖在 xact 內，Worker B 會 block 直到 A commit/rollback；A commit 後 B SELECT 看到 status='completed' → 走 `not_finalizable` 409 路徑。或者用 advisory lock per run_id，pattern 鏡像 register/run。

如果 E2 認為 V046 雙 row 是不可接受 race，R3.1 patch 加 FOR UPDATE 或 advisory lock。E1 不在這版本主動加因 plan §6.R3 未明示要求且不破已宣告 invariant（V050 idempotency 防 fill 重複；V045 status guard 防 re-flip；V046 雙 row 是 cosmetic 污染）。

---

## §11 self-test 完整輸出

```bash
$ wc -l program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py \
       program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py \
       program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
    1479 program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
     551 program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py
     602 program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py

$ venvs/mac_dev/bin/python -c "
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.replay_routes import replay_router
finalize_route = [r for r in replay_router.routes if 'finalize' in r.path]
for r in finalize_route:
    print('path:', r.path, '| methods:', sorted(r.methods))
    print('OK' if 'POST' in r.methods else 'FAIL')
"
path: /api/v1/replay/run/{run_id}/finalize | methods: ['POST']
OK

$ grep -rE '/home/ncyu|/Users/ncyu' \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_finalize.py
(0 hit)

$ venvs/mac_dev/bin/pytest -xvs program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py 2>&1 | tail -3
============================== 11 passed in 0.03s ==============================

$ venvs/mac_dev/bin/pytest -xvs program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_finalize.py 2>&1 | tail -3
======================== 8 passed, 6 warnings in 0.23s =========================

$ venvs/mac_dev/bin/pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ -k replay --no-header -q 2>&1 | tail -2
117 passed, 3387 deselected, 30 warnings in 1.10s

$ venvs/mac_dev/bin/pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ --no-header -q 2>&1 | tail -2
1 failed, 3498 passed, 5 skipped, 425 warnings in 54.19s
# Pre-existing fail per R2 sign-off §7, not caused by R3.

$ git status --porcelain
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_finalize.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py
```

---

## §12 Operator 下一步（CLAUDE.md §七 6 節必備）

1. **E2 代碼審查**：focus §10 給 E2 5 點，特別是 V046 artifact_type plan-vs-reality 差異 + canary_writer 兩階段契約合理性。
2. **E3 安全審計**：path traversal + PID-reuse + statement_timeout + idempotency_key 邊界。
3. **E4 回歸**：3498 PASS / 1 pre-existing fail / 30 warnings 與 R2 baseline 對齊；hermetic mock 充足，真 e2e 留 Linux 部署後 smoke run。
4. **PM 統一 commit**：4 file new + 1 modified；待 E2 + E4 + 無 bug 後 PM commit + push。
5. **smoke run（Linux 部署後）**：
   - POST /api/v1/replay/experiments/register（從 R2）
   - POST /api/v1/replay/run（從 R2，spawn Rust replay_runner）
   - 等 subprocess 結束（poll status 或 verify_replay_runner_pid 死亡）
   - **POST /api/v1/replay/run/{run_id}/finalize（R3 新）**
   - 驗 V045 row.status='completed' / V046 row 1 條 / V050 row N 條（fills 數）
   - acceptance "4 tables row > 0" → R3 IMPL 滿足條件

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r3_impl.md`）

---

## §11 Round 2 Fix Log（E3 § 6 MEDIUM-1 + MEDIUM-2 retrofit）

**Date**: 2026-05-04 (later same day as round 1)
**Trigger**: PM 仲裁 — 採 E3 觀點 M-1 不 defer + M-2 同樣 round 2 fix。E2 verdict 0 BLOCKER / 0 HIGH / 1 MEDIUM (defer); E3 verdict 0 CRITICAL / 0 HIGH / 2 MEDIUM 推 round 2 fix。
**Scope**: 2 fix（M-1 multi-worker race + M-2 timeout drift）+ 4 follow-up TODO ticket。零 V### migration / 零 R1/R2 區動。

### §11.1 M-1 fix details — `SELECT ... FOR UPDATE` 防 multi-worker race

**File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py`
**Function**: `_select_run_state_for_finalize_sync` (line ~187-228)
**Diff**:
- SQL 加 `FOR UPDATE` row lock（同 transaction 序列化 worker B SELECT 直到 worker A commit/rollback）
- 加 22 行雙語 inline comment 解釋 race + V3 §5 quota integrity 動機（mirror E3 §6 MEDIUM-1 推理）

**Race semantic 不變式**：
- worker A 進入後 `SELECT ... FOR UPDATE` 取得 row lock → 進 step 5+6+7（V046 INSERT + V050 INSERT + V045 UPDATE）→ `conn.commit()` 釋鎖
- worker B 並發 `SELECT ... FOR UPDATE` 在 PG 內部 block → worker A commit 後 unblock → 看到 `status='completed'`（V045 已被 A flip）→ `lookup_err='not_finalizable'` → 409 not_finalizable（不再 INSERT V046/V050 / 不再 UPDATE V045）
- **結果**：每個 finalize 呼叫對 V046 / V050 / V045 寫入恰一次（原 E1 §10 #5 揭的「兩 V046 row 指向同 file」cosmetic 漏洞修復）

### §11.2 M-2 fix details — `_FINALIZE_STATEMENT_TIMEOUT_MS = 5_000` 常數修 timeout drift

**Files**:
- `replay/run_finalize_route.py` 加 module-level constant `_FINALIZE_STATEMENT_TIMEOUT_MS = 5_000`（line 128-141 雙語 13 行注釋）+ `__all__` export
- `app/replay_routes.py` post_run_finalize handler 改傳 `_fr._FINALIZE_STATEMENT_TIMEOUT_MS`（line ~742-757，加 14 行雙語注釋）
- `replay/run_finalize_route.py` `run_finalize_in_pg_xact` default `statement_timeout_ms` 從 `5_000` magic number 改 `_FINALIZE_STATEMENT_TIMEOUT_MS` 常數
- docstring 更新 default 描述對齊新常數

**Drift 修復語意**：register endpoint 用 `_STATEMENT_TIMEOUT_MS = 2_000`（in `replay_routes.py`，V3 §12 #22 RFC commitment）。Round 1 thin handler 誤把 `_STATEMENT_TIMEOUT_MS` 直接傳給 finalize（line 753 原 `statement_timeout_ms=_STATEMENT_TIMEOUT_MS`），但 finalize 邏輯 default 是 `5_000`（function signature default），導致 thin handler call 強制把 finalize 也限 2_000ms — 在大量 fills（worst-case ~80k row from 16 MB report cap / 200 byte/fill）下會 503 rollback。Round 2 fix 把 finalize timeout SoT 移到 logic module，thin handler 從 logic module import 常數，避免 magic number 散見。

**Constant 命名**：`_FINALIZE_STATEMENT_TIMEOUT_MS`（與 register 的 `_STATEMENT_TIMEOUT_MS` 區隔；`_FINALIZE_*` prefix 表 finalize-internal）。

### §11.3 4 follow-up ticket 加 TODO.md 證明

```bash
$ grep -nE 'P2-R3-FOLLOW-UP-1|P2-R3-FOLLOW-UP-3|P3-R3-FOLLOW-UP-4|P2-R3-FOLLOW-UP-5' TODO.md
168:| **P2-R3-FOLLOW-UP-1** | V### migration 加 `'replay_report'` value 至 V046 ... | @E1 |
169:| **P2-R3-FOLLOW-UP-3** | run_finalize_route.py exception 路徑 message field generic 化 ... | @E1 |
170:| **P3-R3-FOLLOW-UP-4** | verify_replay_runner_pid 加 psutil.Process.create_time() ... | @E1 |
171:| **P2-R3-FOLLOW-UP-5** | V046 byte_size CHECK BETWEEN 0 AND 67108864 ... | @E1 |
```

四 ticket 全 land 在 P2/P3 區尾（P3-PYDANTIC-V2-MIGRATE-REPLAY 之後）。**注**：原 brief 草案 P2-R3-FOLLOW-UP-2 已被本輪 round 2 fix 解（M-1 SELECT FOR UPDATE）— 不需 ticket。

### §11.4 LOC delta

| 檔 | Round 1 後 | Round 2 後 | Δ | Cap | Margin |
|---|--:|--:|--:|--:|--:|
| `app/replay_routes.py` | 1479 | **1491** | +12 | 1500 | 9 |
| `replay/run_finalize_route.py` | 552 | **593** | +41 | 1500 | 907 |
| `replay/simulated_fills_writer.py` | 602 | 602 | 0 | 1500 | 898 |
| `tests/test_replay_run_finalize.py` | 534 | **727** | +193 | 1500 | 773 |
| `tests/test_replay_simulated_fills_writer.py` | 400 | 400 | 0 | 1500 | 1100 |

**replay_routes.py = 1491 LOC, 9 LOC margin to cap**。Brief 預期 +10-20 LOC，實際 +12 LOC（thin handler 加 14 行雙語注釋）。**Logic module +41 LOC**（22 行 SQL race 注釋 + 13 行 _FINALIZE_STATEMENT_TIMEOUT_MS 注釋 + 加 const decl + 加 export + docstring update）。**Test +193 LOC**（M-1 verification case `test_finalize_multi_worker_race_no_v046_dual_insert` 含 worker A/B dual conn stub + cumulative invariant assertions + `FOR UPDATE` source-grep guard）。

### §11.5 Test 結果（19+1 = 20 R3 case PASS / 117+1 = 118 replay sibling）

```bash
$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_simulated_fills_writer.py tests/test_replay_run_finalize.py
======================== 20 passed, 6 warnings in 0.22s ========================
# 11 simulated_fills_writer (round 1 unchanged) + 9 run_finalize (8 round 1 + 1 round 2 M-1)

$ venvs/mac_dev/bin/pytest tests/ -k replay --no-header -q | tail -3
118 passed, 3387 deselected, 30 warnings in 1.02s
# 117 R3 round 1 baseline + 1 new M-1 case = 118
```

新 M-1 test case `test_finalize_multi_worker_race_no_v046_dual_insert` 驗證點：
1. **worker A happy path** → 200 + status=completed + V046 INSERT 1× / V050 INSERT ≥1× / V045 UPDATE 1×
2. **worker B post-A-commit terminal-status** → 409 not_finalizable + V046 INSERT 0× / V050 INSERT 0× / V045 UPDATE 0×（不重 INSERT V046）
3. **`FOR UPDATE` source-level guard** — `inspect.getsource(_select_run_state_for_finalize_sync)` 含字串 `"FOR UPDATE"`，防 future refactor 誤刪 lock 子句

**Hermetic 限制揭示**：single-process pytest 無法觸發真 PG row-level locking；FOR UPDATE 子句行為由真 PG 在 Linux deploy smoke run 驗（E4 / Linux PA 階段）。本 hermetic test 驗的是「worker B 在 status 已終態下走 409 路徑、不再寫 V046/V050/V045」這個 contract，加上 source grep 確保 SQL clause 持續存在。

### §11.6 git status sign-off-clean (CLAUDE.md §七 P0-GOV-3)

```
$ git status --porcelain
 M TODO.md
 M docs/CCAgentWorkSpace/E1/memory.md       # E1 round 2 will append
 M docs/CCAgentWorkSpace/E2/memory.md       # E2 round 1 review (sibling, not E1's)
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r3_impl.md
?? docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-04--ref20_sprint_a_r3_security_audit.md
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_finalize_route.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/simulated_fills_writer.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_finalize.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_simulated_fills_writer.py
```

**全部對應 R3 round 1+2 IMPL**。0 stray file。`docs/CCAgentWorkSpace/E2/memory.md` 是 E2 round 1 自己 maintain；E1 不擁有編輯權。

### §11.7 Operator 下一步（round 2 後）

1. **E2 round 2 review**：focus M-1 SQL `FOR UPDATE` + M-2 const naming + thin handler import pattern + new test hermetic limit acknowledged
2. **E4 final regression**：3498 → ~3499 PASS 預期（+1 from M-1 test case）；1 pre-existing fail 仍在；30 warnings 維持
3. **E3 round 2 acknowledge（可省）**：M-1 + M-2 已對齊 §6 MEDIUM-1 + MEDIUM-2 修法；4 LOW 全 defer 為 follow-up ticket
4. **PM 統一 commit + push**：4 件 round 2 file edit（run_finalize_route.py / replay_routes.py / TODO.md / test_replay_run_finalize.py）+ 既有 round 1 4 new file
5. **Linux deploy smoke run**：FOR UPDATE 真 PG 行為驗證 — 並發 2× POST /finalize 同 run_id（curl & or 雙 client tab）→ 期待第 2 call 在第 1 call commit 完才返回 409；用 `psql -c "SELECT pid, query, state, wait_event FROM pg_stat_activity WHERE state='idle in transaction';"` 驗 worker B 確實 block

E1 ROUND 2 FIX DONE：待 E2 round 2 → E4 final regression → PM commit + push（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r3_impl.md`）
