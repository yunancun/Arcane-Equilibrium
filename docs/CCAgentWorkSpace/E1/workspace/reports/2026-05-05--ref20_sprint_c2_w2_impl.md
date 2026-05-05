# REF-20 Sprint C2 W2 — 3 R7 task batch IMPL Sign-off

- **Date (UTC)**：2026-05-05
- **Agent**：E1
- **Branch**：main（Mac 工作樹，pending PM commit）
- **Base HEAD**：`fc3c6f19`（Sprint C2 W1 closure；Mac/Linux/origin synced）
- **PA dispatch**：「REF-20 Sprint C2 R7 W2 — capability test + FK chain audit + lookup reuse audit (3 task batch)」
- **AI-E advisory ref**：`docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-05--ref20_r7_advisory_chain_spec.md` §11.1 W2 spec

## §1 — R7-T5 evidence_filter capability probe test

### §1.1 Test design

per dispatch §1.1 + AI-E §9.3 + MIT §1.1 6-key 4-gate spec：6 case + 3 observability test。

| Case | 描述 | Capability state | 結果 |
|---|---|---|---|
| **Case 1** Full capability (6/6 true) | Block B 完整版含 manifest_hash NOT NULL + expires_at > now() + status NOT IN | all true | ✅ |
| **Case 2** Partial capability | replay_experiments_has_expires_at=False → fallback FK existence-only gate | column 在 stub 缺 | ✅ |
| **Case 3** Block A only | has_replay_experiment_id=False → 含 evidence_source_tier allowlist + 0 Block B | tier 在 / FK 不在 | ✅ |
| **Case 4** Top-level fail-soft | has_evidence_source_tier=False → SQL empty string (legacy schema) | 0 column | ✅ |
| **Case 5** Cycle stale check | capability re-probed each cycle，無 cache (per MIT §1.3) | 1 cycle=3 probe / 2 cycle=6 probe | ✅ |
| **Case 6** Real PG smoke (OPENCLAW_TEST_LIVE_PG=1 opt-in) | live PG fixture verify Block B 真 fire | live PG | ⏸ skip (opt-in) |
| **Bonus** observability_log full | caps=6/6 + block_a=on + block_b=full | all true | ✅ |
| **Bonus** observability_log partial | caps=4/6 + block_a=on + block_b=partial | column 在 stub 缺 | ✅ |
| **Bonus** observability_log legacy skip | caps=0/6 + block_a=skip + block_b=skip | 0 column | ✅ |

合計 **9 test (8 PASS + 1 opt-in skip)**。

### §1.2 _ProbeCursor 重用 + probe_call_count 計

W2 設一個 `_ProbeCursor` mock 含三段 probe response queue + `probe_call_count` counter。每次 `cur.execute(...)` 對非 mlde_shadow_recommendations SELECT 增 counter；驗 1 cycle = 3 probe call（column probe / regclass / experiments column probe），2 cycle 同 cursor = 6 probe call（無 cache）。

對齊 source_filter test 的既有 mock pattern。

## §2 — R7-T7 FK chain SQL acceptance + observability log

### §2.1 Part A — FK chain SQL acceptance test

per dispatch §1.2 + AI-E §9.4：3 acceptance SQL + 1 contract doc + 2 real PG smoke opt-in。

| Test | 描述 | 結果 |
|---|---|---|
| **A10-1** paired CHECK SQL acceptance | 驗 SQL 結構含 calibrated_replay/synthetic_replay/counterfactual_replay tier IN + replay_experiment_id IS NULL OR manifest_hash IS NULL | ✅ |
| **A10-2** TTL hard check via JOIN | 驗 SQL **必經 JOIN** replay.experiments.expires_at（不直查 msr.expires_at）— per dispatch §1.2 注意：mlde_shadow_recommendations 表本無 expires_at column | ✅ |
| **A10-3** FK lineage validation | 驗 SQL 用 LEFT JOIN replay.experiments + re.experiment_id IS NULL 檢 FK orphan | ✅ |
| **contract doc consistency** | 驗 A10-1/A10-2/A10-3 三 SQL 對齊 V051 paired CHECK semantic | ✅ |
| **real PG smoke** (opt-in) | live PG 跑 3 acceptance SQL → 0 violation | ⏸ skip (opt-in) |
| **mlde_shadow_recommendations.expires_at NOT exist** (opt-in) | 驗 W6 R6-T9 「expires_at column 不存在」事實 | ⏸ skip (opt-in) |

合計 **6 test (4 PASS + 2 opt-in skip)**。

### §2.2 Part B — observability log per MIT §1.5

修 `mlde_demo_applier_evidence_filter.py::fetch_pending_sql_and_params`：在 SQL 構造 end 加 1-line INFO log dump：

```python
# 計算 capability dump（caps_count / block_a_label / block_b_label）
caps_count = sum(1 for v in caps.values() if v)
logger.info(
    "evidence_filter capability dump: caps=%d/6 block_a=%s block_b=%s",
    caps_count, block_a_label, block_b_label,
)
```

block_b 三段判斷：
- `full` = 4 個 FK 能力全 true（NOT NULL + manifest_hash + expires_at + status）
- `partial` = FK column 在但 stub 缺 expires_at/status（degraded existence-only gate）
- `skip` = replay_experiment_id column 未 land OR has_evidence_source_tier=False（完全 fallback）

3 caplog test 驗 full / partial / legacy skip 三 state 各觸發 1 條正確 INFO log。

### §2.3 LOC delta

`mlde_demo_applier_evidence_filter.py`：291 → 324 LOC（+33；含中文 inline comment ~9 LOC + 邏輯 ~10 LOC + logger.info ~6 LOC + 空行）。0 邏輯改 SQL 結構 / 0 改 caller signature。

## §3 — R7-T8 lookup_replay_config_blob reuse audit

### §3.1 Test design + W1 push back accept context

per dispatch §1.3：W1 sign-off §9.4 揭 helper 直接 SELECT V049.manifest_hash 而非 reuse `lookup_replay_config_blob`（後者只取 manifest_jsonb 內 strategy_params / risk_overrides 兩 blob，無 manifest_hash key）。

R7-T8 **不強要求 reuse 既有 helper** — 改驗 manifest_hash 取值邏輯一致性 across 4 producer + finalize_route。

| Test | 描述 | 結果 |
|---|---|---|
| **helper_uses_independent_select_pattern** | W1 模式 A：helper 含 SELECT manifest_hash（OR reuse helper 兩種 PASS） | ✅ |
| **helper_select_uses_experiment_id_predicate** | helper SELECT 必透 experiment_id WHERE clause + LIMIT 1 | ✅ |
| **finalize_route_uses_consistent_lookup_pattern** | finalize_route 含 SELECT FROM replay.experiments + trading.fills | ✅ |
| **dream_engine_no_inline_manifest_hash_select** | producer 端不應 inline SELECT manifest_hash（全走 helper） | ✅ |
| **opportunity_tracker_no_inline_manifest_hash_select** | 同上 | ✅ |
| **mlde_shadow_advisor_no_inline_manifest_hash_select** | 同上 | ✅ |
| **dream_engine_imports_helper** | producer import build_replay_metadata helper（R7-T1） | ✅ |
| **opportunity_tracker_imports_helper** | 同上（R7-T3） | ✅ |
| **mlde_shadow_advisor_imports_helper** | 同上（R7-T1.5） | ✅ |
| **helper_module_docstring_documents_w1_design_decision** | helper docstring 至少提 lookup_replay_config_blob 名（提示讀者 W1 push back accept） | ✅ |

合計 **10 test 全 PASS**。

### §3.2 _repo_root() pattern

test 用 `Path(__file__).resolve().parents[6]` 算 repo root（從 `tests/replay/` 反推；穩跨 Mac / Linux 平台）。完全 grep static analysis，不依 PG runtime / 不 import 真實 producer module。

## §4 — Mac pytest 結果

```
$ python3 -m pytest program_code/ml_training/tests/test_evidence_filter_capability.py -v
================ 8 passed, 1 skipped in 0.02s ==================

$ python3 -m pytest program_code/ml_training/tests/test_advisory_lineage_fk.py -v
================ 4 passed, 2 skipped in 0.01s ==================

$ python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_lookup_replay_config_blob_reuse.py -v
================ 10 passed in 0.02s ==================

$ python3 -m pytest program_code/ml_training/tests/test_evidence_filter_capability.py program_code/ml_training/tests/test_advisory_lineage_fk.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_lookup_replay_config_blob_reuse.py program_code/ml_training/tests/test_mlde_demo_applier_source_filter.py -v
================ 33 passed, 3 skipped in 0.04s =====
   (W2 22 PASS + 既有 12 source_filter regression GREEN + 3 opt-in skip = 0 regression)

$ python3 -m pytest program_code/ml_training/tests/ program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/ program_code/local_model_tools/tests/ 2>&1
================ 1 failed, 518 passed, 35 skipped, 10 warnings in 3.58s ====
   1 fail = pre-existing test_insert_live_candidate_payload_carries_schema_version_and_lg5_subkeys
   stash 我的 W2 改動仍 fail；確認非 W2 引入；無 regression
```

合計 **22 新 test (8+4+10) + 0 regression**（518 ml_training+replay+local_model_tools 全 PASS / 1 pre-existing fail / 35 skipped）。

## §5 — LOC compliance

| File | Pre LOC | Post LOC | Delta | Cap | 狀態 |
|---|---:|---:|---:|---|---|
| `tests/test_evidence_filter_capability.py` (NEW) | 0 | 451 | +451 | 800 warn / 2000 cap | ✅ 健康 |
| `tests/test_advisory_lineage_fk.py` (NEW) | 0 | 293 | +293 | 800 warn / 2000 cap | ✅ 健康 |
| `tests/test_lookup_replay_config_blob_reuse.py` (NEW) | 0 | 265 | +265 | 800 warn / 2000 cap | ✅ 健康 |
| `mlde_demo_applier_evidence_filter.py` (M) | 291 | 324 | +33 | 800 warn / 2000 cap | ✅ 健康 |
| **Total** | 291 | 1333 | +1042 | < 4×2000=8000 | ✅ 全綠 |

PA dispatch §3 估 ~250 LOC；實際 +1042 因：
- 完整中文 MODULE_NOTE（CLAUDE.md §七 governance default 中文，每檔 ~30-50 LOC docstring）
- R7-T5 多寫 3 observability log test（per MIT §1.5；共 ~80 LOC）
- R7-T7 Part A 加 contract doc consistency test + W6 R6-T9 expires_at 列不存在交叉驗證
- R7-T8 加 helper docstring 設計決策驗證 + 兩模式接受 PASS 路徑

全 < 800 warn / 全 < 2000 hard cap。

## §6 — Governance 對照

### 0 forbidden import

```bash
$ grep -nE "paper_state|canary_writer|ipc_server|governance_hub|live_authorization|decision_lease" \
    program_code/ml_training/tests/test_evidence_filter_capability.py \
    program_code/ml_training/tests/test_advisory_lineage_fk.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_lookup_replay_config_blob_reuse.py \
    program_code/ml_training/mlde_demo_applier_evidence_filter.py
（0 命中）
```

### 0 cross-platform path 硬編碼

```bash
$ grep -nE "/home/ncyu|/Users/[a-z]+" <new+modified files>
（0 命中）
```

`test_lookup_replay_config_blob_reuse.py` 使用 `Path(__file__).resolve().parents[6]` 動態解析 repo root，不硬編碼任何 user-home path。

### 0 hard boundary 觸碰

```bash
$ grep -nE "max_retries|live_execution_allowed|execution_authority|system_mode" <new+modified files>
（0 命中）
```

### 0 manifest_signer canonical_bytes 改動

```bash
$ grep -nE "manifest_signer|canonical_bytes" <new+modified files>
（0 命中）
```

### 0 V### migration / 0 schema 改動

僅 caller side / test side 改動：3 NEW test file + 1 既有 helper file 加 logger.info 觀測點。0 V### migration、0 schema 變更、0 V055 / V051 / V049 function body 改動、0 manifest_signer canonical_bytes contract 改動。

### xlang_consistency 13/13 維持

W2 是 Python-only 改動（test + observability log）；不破 V3 §13 xlang_consistency。3 test / 1 observability log 都不進 Rust manifest_signer canonical_bytes contract。

### Pre-existing baseline > 800 warn

mlde_demo_applier_evidence_filter.py post-W2 = 324 LOC < 800 warn。本次 W2 不觸 baseline > warn 例外條款。

## §7 — 注釋全中文 per governance

per CLAUDE.md §七 2026-05-05 governance change（commit `47922a4c`）：

- `tests/test_evidence_filter_capability.py`：MODULE_NOTE + 9 test docstring + helper class _ProbeCursor docstring 全中文
- `tests/test_advisory_lineage_fk.py`：MODULE_NOTE + 6 test docstring + 3 SQL build 函數 docstring 全中文
- `tests/test_lookup_replay_config_blob_reuse.py`：MODULE_NOTE + 10 test docstring + helper functions 全中文
- `mlde_demo_applier_evidence_filter.py` 改動部分：R7-T7 Part B inline comment 純中文（per CLAUDE.md §七 「新建/修改的注釋默認只寫中文」）

既有 W3-W6 中英對照塊未碰（per CLAUDE.md §七「修改既有中英對照塊時移除英文只保留中文」— 本 W2 修改 mlde_demo_applier_evidence_filter.py 只在 caller side 加 inline comment + logger.info；既有 docstring + helper docstring 完整保留 bilingual）。

## §8 — git status

```bash
$ git status --porcelain
 M program_code/ml_training/mlde_demo_applier_evidence_filter.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_lookup_replay_config_blob_reuse.py
?? program_code/ml_training/tests/test_advisory_lineage_fk.py
?? program_code/ml_training/tests/test_evidence_filter_capability.py

$ git diff --stat program_code/ml_training/mlde_demo_applier_evidence_filter.py
 .../mlde_demo_applier_evidence_filter.py | 34 ++++++++++++++++++++++
 1 file changed, 34 insertions(+)
```

無 unintended drift；4 file 對應 PA dispatch §1.1-§1.3 + §3 預期 IMPL surface（含 NEW 3 test + observability log retrofit）。

## §9 — 不確定之處 → PM 決策

### §9.1 R7-T7 Part B observability log 級別 INFO 是否合適

當前 logger.info 走 stderr / log file。INFO level 可能在 production log 過頻（每 cycle 1 次 = ~24 次/天 per applier instance；多 instance × engine_mode → ~100 lines/day）。

**狀態**：對 cron / log slot 收集 metric 是 P2-R7-W2-FOLLOWUP-2 議題；當前 INFO level 適合 Sprint C2 closure 階段觀測。Sprint D 監控 chain 上線後 PM 可降為 DEBUG 或升 metric 表。

### §9.2 Real PG smoke (Case 6 + A10) 何時跑

3 個 OPENCLAW_TEST_LIVE_PG=1 opt-in test 當前 skip。Linux 部署後 PM/E4 可跑：
```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && OPENCLAW_TEST_LIVE_PG=1 python3 -m pytest program_code/ml_training/tests/test_evidence_filter_capability.py::test_case6_real_pg_smoke_full_block_b_fires program_code/ml_training/tests/test_advisory_lineage_fk.py::test_a10_real_pg_smoke_all_three_invariants_zero_violation program_code/ml_training/tests/test_advisory_lineage_fk.py::test_real_pg_smoke_mlde_shadow_recommendations_no_expires_at_column -v"
```

**狀態**：PA 派發 §6 minimal-loop pattern「W3 全 chain land 後 E4 regression」可能納入此 opt-in PG smoke 跑。

### §9.3 R7-T8 future LinUCB warm-start caller 不涵蓋

當前 R7-T8 grep audit 僅覆蓋 4 producer (dream / opportunity / mlde_shadow / finalize_route)。Future Sprint D/E LinUCB warm-start 加 verify_replay caller 時，本 test 不會自動 catch。建議當 LinUCB warm-start chain land，PM 同 sprint 加 LinUCB import / inline SELECT grep test（per memory `linucb_shadow_compare_retention.md`）。

**狀態**：W2 scope 不擴大；列為 P2-R7-W2-FOLLOWUP-3。

### §9.4 W6 R6-T9 expires_at column verify 是否需 PG 端定期 check

A10-2 test 含 `test_real_pg_smoke_mlde_shadow_recommendations_no_expires_at_column`（opt-in），驗 mlde_shadow_recommendations.expires_at column 確不存在。若未來某 V### migration 意外加此 column，A10-2 SQL 會走錯路徑（本可直查 row-level 但反走 JOIN）→ semantic drift。

**狀態**：建議 PM 將此 opt-in test 納入 Sprint D 監控週期（每 sprint 跑一次 OPENCLAW_TEST_LIVE_PG=1 smoke）；當前 W2 接受 opt-in mode。

## §10 — Operator 下一步

E1 W2 SIGN-OFF 完成；交 PM：

1. **Review 本 report**
2. **Commit + push**（建議 message：`feat(ref20): Sprint C2 R7 W2 — capability test + FK chain audit + lookup reuse audit + observability log`）
3. **Linux pull + pytest**：`ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && python3 -m pytest program_code/ml_training/tests/test_evidence_filter_capability.py program_code/ml_training/tests/test_advisory_lineage_fk.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_lookup_replay_config_blob_reuse.py -v"` 驗 22 PASS + 3 skip（與 Mac 結果一致）
4. **Optional Linux PG smoke**：`OPENCLAW_TEST_LIVE_PG=1` 跑 3 opt-in 對 Linux PG 驗 6/6 capability + 0 FK violation + expires_at column 不存在交叉驗證
5. **C2 W3 dispatch unblock**：E2E integration test 對 R7 全 chain 跑（per AI-E §11.1 W3 task）
6. **CLAUDE.md §三 update**：Sprint C2 R7 W2 land status (3 R7 task land + observability log retrofit)

PA 派發 §6 強制工作鏈：本 W2 採 minimal-loop pattern（純 test + 1 logger.info line + 0 production logic change）；建議 PM 直接 review skip E2，E4 regression 在 W3 全 chain land 後跑。

---

E1 C2 W2 SIGN-OFF DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c2_w2_impl.md`; 3 R7 task land (R7-T5 capability test + R7-T7 Part A FK chain SQL + Part B observability log + R7-T8 reuse audit); ~1042 LOC; 22 new test PASS (8+4+10) + 3 opt-in skip; pending PM commit + Linux verify + W3 dispatch
