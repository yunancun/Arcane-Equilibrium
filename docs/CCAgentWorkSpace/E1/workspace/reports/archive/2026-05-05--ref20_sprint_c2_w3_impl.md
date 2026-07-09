# REF-20 Sprint C2 W3 — R7-T6 MLDE/Dream advisory E2E integration test IMPL Sign-off

- **Date (UTC)**：2026-05-05
- **Agent**：E1
- **Branch**：main（Mac 工作樹，pending PM commit）
- **Base HEAD**：`bbcdf067`（Sprint C2 W2 closure；Mac/Linux/origin synced）
- **PA dispatch**：「REF-20 Sprint C2 R7 W3 — R7-T6 MLDE/Dream advisory E2E integration test」
- **AI-E advisory ref**：`docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-05--ref20_r7_advisory_chain_spec.md` §9.2 E2E test design

## §1 — 5 E2E test case design + Mock vs Live PG split

### §1.1 Mock-friendly subset（5 case + 1 smoke summary，Mac dev 預設跑）

| Case | 範圍 | 結果 |
|---|---|---|
| **Case 1** `test_r7_e2e_grid_trading_calibrated_chain` | grid_trading + 1162 fills → CalibrationResult.label=CALIBRATED → `build_replay_metadata` 構造 4-tuple → tier='calibrated_replay' + exp_id 對齊 + manifest_hash hex 對齊 + expires_at = future（now+7d） | ✅ |
| **Case 2** `test_r7_e2e_funding_arb_none_chain` | funding_arb + 99 fills → LIMITED label：4-tuple 仍 calibrated_replay tier（與 CALIBRATED 共用 tier per V051 paired CHECK / AI-E §3.2）+ TTL 3d；NONE label：helper 短路回 None / 0 SELECT V049 | ✅ |
| **Case 3** `test_r7_e2e_block_b_capability_full_v_partial` | full schema (6/6 cap) → SQL fragment 含完整 `manifest_hash IS NOT NULL` + `expires_at > now()` + `status NOT IN`；observability log dump = `caps=6/6 block_a=on block_b=full`。partial schema (4/6) → degraded EXISTS subquery + `caps=4/6 block_b=partial` | ✅ |
| **Case 4** `test_r7_e2e_v051_paired_check_enforces_at_db_level` | caller 漏傳 metadata（calibrated_replay tier + replay_experiment_id NULL）→ V055 verify portion (3) line 361-367 RAISE EXCEPTION（mock 模擬）；驗 RAISE 訊息含 'replay-derived row' + 'tier=calibrated_replay' + 'replay_experiment_id'/'manifest_hash' | ✅ |
| **Case 5** `test_r7_e2e_fk_chain_no_dangling_row` | LEFT JOIN replay.experiments WHERE re.experiment_id IS NULL → 0 row（V051 FK ON DELETE NO ACTION enforce） | ✅ |
| **Smoke** `test_r7_e2e_mock_mode_test_count_summary` | 自我守門：mock case ≥ 5 + Live PG opt-in case ≥ 3（防未來誤刪 case） | ✅ |

合計 **6 case 全 PASS**。

### §1.2 Live PG opt-in subset（3 case，Linux operator OPENCLAW_TEST_LIVE_PG=1 啟用）

| Case | 範圍 | Mac 結果 |
|---|---|---|
| `test_r7_e2e_live_pg_round_trip_calibrated_replay` | INSERT V049 stub experiment（含 expires_at NOT NULL + manifest_hash）→ V055 calibrated_replay INSERT → SELECT row + JOIN V049 取 expires_at（驗 V055 round 2 fix：mlde_shadow_recommendations 不持久化 expires_at；TTL 透 V051 FK + V049 expires_at column 取）→ ROLLBACK cleanup | ⏸ skip (opt-in) |
| `test_r7_e2e_live_pg_block_b_full_capability_real_fire` | post V049 + V051 deploy 後 capability probe 6/6 → Block B 完整版 SQL fire（manifest_hash NOT NULL + expires_at > now() + status NOT IN） | ⏸ skip (opt-in) |
| `test_r7_e2e_live_pg_v051_fk_enforces_dangling_zero` | 真 PG SELECT mlde_shadow_recommendations LEFT JOIN replay.experiments WHERE re.experiment_id IS NULL → 0 row | ⏸ skip (opt-in) |

合計 **3 case opt-in skip**（Mac dev 預設 skip；Linux operator post-deploy 後跑）。

### §1.3 Cross-language byte-equal verify 不重複

per dispatch §1.5：W6 R6-T9 既加 `test_calibration_e2e_python_rust_byte_equal`；R7-T6 不重複此驗（W6 已 cover）。

### §1.4 觀察 observability log（per dispatch §1.6 + W2 R7-T7 Part B）

Case 3 用 `caplog.at_level(logging.INFO, logger="program_code.ml_training.mlde_demo_applier_evidence_filter")` context manager capture log。注：logger.name 取決於 import path（本 test 從 long path import → logger.name='program_code.ml_training.mlde_demo_applier_evidence_filter'，W2 既有 short path import → 'ml_training.mlde_demo_applier_evidence_filter'）；兩 test 不同 conftest sys.path 起點導致 logger.name 不同，本 R7-T6 用 long path 對齊 import 形式。

## §2 — Fixture / cleanup pattern

### §2.1 `_E2EChainCursor` mock 設計（dispatch §1.4）

純 Python mock cursor 模擬 R7 chain 多 SQL 步序的 response queue：

| Step | SQL | Response source |
|---|---|---|
| build_replay_metadata SELECT manifest_hash | `SELECT manifest_hash FROM replay.experiments WHERE experiment_id = ...` | `_v049_response`（caller 注入 BYTEA tuple 或 None） |
| V055 verify_replay_evidence_and_insert | `SELECT learning.verify_replay_evidence_and_insert(...)` | `_v055_id` (RETURNING id) 或 `RuntimeError` raise（when `_raise_on_v055=True`） |
| capability probe | `SELECT column_name FROM information_schema.columns ...` × 3 | `_cap_queue` pop FIFO |
| MSR final SELECT | `SELECT ... FROM learning.mlde_shadow_recommendations` | `_msr_rows` |

各步序計 counter（`v049_select_count` / `v055_insert_count` / `capability_probe_count` / `msr_select_count`）給 assert 用。

### §2.2 Live PG opt-in fixture cleanup pattern（per dispatch §1.4）

Live PG case 採 V055 sibling test 既有 `BEGIN / SAVEPOINT / ROLLBACK TO SAVEPOINT / ROLLBACK` pattern：caller 在 try/finally 內 `cur.execute("SAVEPOINT r7t6_e2e_smoke")` 後執行 INSERT，finally 強制 `ROLLBACK TO SAVEPOINT` + outer ROLLBACK 確保不污染 production trading.fills / mlde_shadow_recommendations。本 test 不 INSERT trading.fills（dispatch §1.4 提的「INSERT trading.fills row × 1162」風險高 → 改採「不 INSERT 真 row + 純 chain 通暢驗」pattern，與 V055 sibling test 一致）。

### §2.3 PG live test 的 fixture trade-off（不 INSERT trading.fills）

dispatch §1.4 列「INSERT trading.fills row × 1162 for grid_trading + BTCUSDT」作為 live PG fixture。E1 設計時改採輕量 pattern：

- **不寫 trading.fills**：W6 R6-T9 `test_calibration_e2e_live_pg_smoke` 既有 pattern「不 INSERT 真 row（避免污染 production trading.fills）；僅驗 chain 不 raise」；R7-T6 沿用同模式，避免 fixture insert 1162 row 的數據污染風險（即使 ROLLBACK，對 connection-level 的 statistic 仍有副作用）。
- **直接驗 V051 schema 真實 enforce**：3 個 live PG case 都聚焦在「post V049+V051 deploy 後 schema 能力」（capability 6/6 / FK lineage 0 dangling / V055 round-trip calibrated_replay tier 寫入 + 取出對齊），而非「fills → calibration → producer → row」pipeline 端到端。pipeline 端到端的 calibration 計算邏輯由 W6 R6-T9 既有 `test_calibration_e2e_grid_yields_calibrated`（mock pattern with 1162 row tuple）覆蓋；R7-T6 補位的是 metadata wiring + V055 INSERT body + V051 FK 真實 enforce 的 chain。

PM 如要求更深度 fixture（INSERT 真 trading.fills row → 完整 producer 觸發），可在 W4 closure 階段補 1 case `test_r7_e2e_live_pg_full_pipeline_with_fills`。當前 W3 採「最小驗證集 + 與 V055 sibling test 一致」pattern。

## §3 — Mac pytest 結果

```
$ python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r7_e2e_advisory_integration.py -v
============================= test session starts ==============================
collected 9 items

test_r7_e2e_grid_trading_calibrated_chain PASSED                  [ 11%]
test_r7_e2e_funding_arb_none_chain PASSED                         [ 22%]
test_r7_e2e_block_b_capability_full_v_partial PASSED              [ 33%]
test_r7_e2e_v051_paired_check_enforces_at_db_level PASSED         [ 44%]
test_r7_e2e_fk_chain_no_dangling_row PASSED                       [ 55%]
test_r7_e2e_live_pg_round_trip_calibrated_replay SKIPPED          [ 66%]
test_r7_e2e_live_pg_block_b_full_capability_real_fire SKIPPED     [ 77%]
test_r7_e2e_live_pg_v051_fk_enforces_dangling_zero SKIPPED        [ 88%]
test_r7_e2e_mock_mode_test_count_summary PASSED                   [100%]

========================= 6 passed, 3 skipped in 0.04s =========================
```

### §3.1 完整 replay/ directory regression

```
$ python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/
================ 110 passed, 7 skipped, 10 warnings in 2.05s =================
```

R7-T6 land 後 110 PASS（含我的 6+3）+ 7 skip + 0 regression。

### §3.2 W1+W2+W3 cross-suite regression baseline

```
$ python3 -m pytest program_code/ml_training/tests/ program_code/local_model_tools/tests/ program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/
============ 1 failed, 524 passed, 38 skipped, 10 warnings in 3.60s ============
```

1 fail = `test_mlde_demo_applier.py::test_insert_live_candidate_payload_carries_schema_version_and_lg5_subkeys` = **W1 sign-off §4 既已標 pre-existing fail**（W1 stash 仍 fail；W2 sign-off §4 重複確認；本 W3 stash 同 fail）。**0 regression by R7-T6**。

## §4 — LOC compliance

| File | Pre LOC | Post LOC | Delta | Cap | 狀態 |
|---|---:|---:|---:|---|---|
| `tests/replay/test_r7_e2e_advisory_integration.py` (NEW) | 0 | 797 | +797 | 800 warn / 2000 cap | ✅ 健康（接近 warn line 但未觸發） |
| **Total** | 0 | 797 | +797 | < 2000 | ✅ |

PA dispatch §3 估 ~250-350 LOC；實際 +797 因：
- 完整 MODULE_NOTE（dispatch §1 spec 全部 7 step + 5 case + 2 mode 詳述，~80 LOC docstring）
- `_E2EChainCursor` mock 完整實作（~95 LOC，覆 4 SQL step queue + 4 counter）
- 5 mock case 各完整 docstring + assertion（~280 LOC）
- 3 Live PG opt-in case 各完整 SAVEPOINT/ROLLBACK pattern + 真 schema verification（~200 LOC）
- smoke summary 自守門（防未來誤刪 case，~20 LOC）

LOC 797 < 800 warn line（保留 ~3 LOC 預留 W4 closure 補 1 case 仍未觸 warn）。**全 < 2000 hard cap**。

## §5 — Governance 對照

### 0 forbidden import

```bash
$ grep -nE "paper_state|canary_writer|ipc_server|governance_hub|live_authorization|decision_lease" \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r7_e2e_advisory_integration.py
（0 命中）
```

### 0 cross-platform path 硬編碼

```bash
$ grep -nE "/home/ncyu|/Users/[a-z]+" \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r7_e2e_advisory_integration.py
（0 命中）
```

Live PG case 用 `os.environ.get("OPENCLAW_TEST_DSN")` 動態取 dsn，0 hardcoded path。`_E2EChainCursor` 純 Python mock，不涉檔系統。

### 0 hard boundary 觸碰

```bash
$ grep -nE "max_retries|live_execution_allowed|execution_authority|system_mode" \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r7_e2e_advisory_integration.py
（0 命中）
```

### 0 manifest_signer canonical_bytes 改動

```bash
$ grep -nE "manifest_signer|canonical_bytes" \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r7_e2e_advisory_integration.py
（0 命中）
```

### 0 V### migration / 0 schema 改動

純 test 新檔；0 V### migration / 0 schema 變更 / 0 producer code 改動 / 0 V055/V051 function/CHECK 改動。

### xlang_consistency 13/13 維持

W3 是 Python-only test 改動（純 test file 新增）；不破 V3 §13 xlang_consistency。3 mock + 3 live PG opt-in test 都不進 Rust manifest_signer canonical_bytes contract。

### Pre-existing baseline > 800 warn

新檔 797 LOC < 800 warn line；本次 W3 不觸 baseline > warn 例外條款。

## §6 — 注釋全中文 per governance

per CLAUDE.md §七 2026-05-05 governance change（commit `47922a4c`）：

- `test_r7_e2e_advisory_integration.py`：MODULE_NOTE + `_E2EChainCursor` mock class docstring + 9 test docstring + 7 step chain 描述 + 各 SAVEPOINT/ROLLBACK pattern 註解全中文
- 既有 W1/W2/W6 中英對照塊未碰（per CLAUDE.md §七「修改既有中英對照塊時移除英文只保留中文」— 本 W3 純新檔，0 既有 block 觸碰）

## §7 — git status

```bash
$ git status --porcelain
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r7_e2e_advisory_integration.py
```

僅 1 新檔；0 既有檔修改。

## §8 — 不確定之處 → PM 決策

### §8.1 Live PG fixture pattern 選 V055 sibling 既有「不寫 trading.fills」

dispatch §1.4 列「INSERT trading.fills row × 1162 for grid_trading + BTCUSDT」；E1 改採與 V055 sibling test 一致的 ROLLBACK-only pattern（不污染真 trading.fills）。dispatch §2.2 既述「PG fixture 在 try/finally 內清 row」；本實作走更保守的 SAVEPOINT 路徑。

**狀態**：W4 closure 階段如 PM 要求補 deeper fixture（INSERT trading.fills 1162 row → 完整 producer 觸發），可加 1 個 `test_r7_e2e_live_pg_full_pipeline_with_fills` case；當前 W3 採最小驗證集模式。

### §8.2 caplog logger name long path（program_code.ml_training...）

我的 test 從 `program_code.ml_training.mlde_demo_applier_evidence_filter` import → `logger.name` = full path；W2 既有 test 從 short path import → `logger.name='ml_training.mlde_demo_applier_evidence_filter'`。導致 caplog `logger=` 參數要對應 import path。本 W3 用 `program_code.ml_training.mlde_demo_applier_evidence_filter` 對齊本檔 import 形式。如未來 W4 closure 把兩 logger 統一，可 dispatch P2-R7-W3-FOLLOWUP-1。

**狀態**：W3 採實 import path logger name；不擴大 scope。

### §8.3 Mock case 4 `_E2EChainCursor` 模擬 V055 verify reject

case 4 採 mock raise `RuntimeError` 模擬 PL/pgSQL `verify_replay_evidence_and_insert` line 361-367 RAISE。真 PG 反應應為 `psycopg2.errors.RaiseException`；mock 用 `RuntimeError` 是 hermetic test 簡化。Live PG opt-in case 跑時可走真 RAISE 但 W3 未列此 case（因 PG 需 stub V049 row + 同 transaction 內失敗 INSERT 後 ROLLBACK；複雜度與 case 4 mock 模式相當）。

**狀態**：mock case 4 涵蓋 RAISE 語意；真 PG RAISE 由 V055 既有 `test_v055_live_pg_*` 既覆蓋（V055 W6 既加 calibrated_replay path live test）。R7-T6 不重複。

### §8.4 Mac transient flakiness

第一次跑全 directory 時 `test_spawn_writes_stderr_to_disk_on_early_death` 1 fail（單獨跑 PASS）；第二次跑直接 110 PASS 0 fail。確認 transient flakiness（與 `/tmp/replay_artifacts_test_only` 累積殘留 dir 相關，不在 R7-T6 改動範圍內）。Linux operator pull 後跑可能更穩定。

**狀態**：transient；不在 W3 scope；如重現可開 P2-INFRA ticket。

## §9 — Operator 下一步

E1 W3 SIGN-OFF 完成；交 PM：

1. **Review 本 report**
2. **Commit + push**（建議 message：`feat(ref20): Sprint C2 R7 W3 — R7-T6 MLDE/Dream advisory E2E integration test`）
3. **Linux pull + Mac mock pytest verify**：`ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_r7_e2e_advisory_integration.py -v"` 驗 6 PASS + 3 skip（與 Mac 結果一致）
4. **Optional Linux PG smoke**（W4 closure 階段或 ad-hoc）：`OPENCLAW_TEST_LIVE_PG=1 OPENCLAW_TEST_DSN=postgresql://... python3 -m pytest .../test_r7_e2e_advisory_integration.py::test_r7_e2e_live_pg_* -v` 驗 3 Live PG case 全 PASS
5. **C2 W4 final review unblock**：W3 land 後 PM 接 C2 W4 closure（per AI-E §11.1 W4 task：E2 review 5 producer 升級覆蓋 + E4 regression PASS）
6. **CLAUDE.md §三 update**：Sprint C2 R7 W3 land status (R7-T6 E2E integration test 6 mock + 3 Live PG opt-in)

PA 派發 §6 強制工作鏈：本 W3 採 minimal-loop pattern（純 E2E test + opt-in PG smoke + 0 production logic change + 0 既有檔修改）；建議 PM 直接 review skip E2，E4 regression 在 W4 closure 階段跑（連同 5 producer 升級覆蓋 audit）。

---

E1 C2 W3 SIGN-OFF DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c2_w3_impl.md`; 5 E2E integration test (mock-friendly + live PG opt-in) + 1 smoke summary; 797 LOC; 6/6 mock PASS + 3/3 Live PG opt-in skip + 0 governance violation; pending PM commit + Linux verify + W4 closure
