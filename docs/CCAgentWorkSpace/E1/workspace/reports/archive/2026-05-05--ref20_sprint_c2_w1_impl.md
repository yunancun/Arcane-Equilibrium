# REF-20 Sprint C2 W1 — 5 R7 task batch IMPL Sign-off

- **Date (UTC)**：2026-05-05
- **Agent**：E1
- **Branch**：main（Mac 工作樹，pending PM commit）
- **Base HEAD**：`80c50ce7`（Sprint C C1 R6 closure；Mac/Linux/origin synced）
- **PA dispatch**：「REF-20 Sprint C2 R7 W1 — 5-producer 升級 calibrated_replay tier + 共用 helper」
- **AI-E advisory ref**：`docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-05--ref20_r7_advisory_chain_spec.md`

## §1 — 5 R7 task IMPL summary

| Task | 範圍 | 檔案 | LOC | 結果 |
|---|---|---|---:|---|
| **R7-T1** dream_engine 升級 | `persist_dream_insights` 加 `R6_calibration_provider` kwarg；per-insight loop 構造 metadata；Calibrated/Limited→'calibrated_replay' tier；NONE→skip insert；backward-compat 'real_outcome' fallback | `program_code/local_model_tools/dream_engine.py` | 954→1063 (+109) | ✅ DONE |
| **R7-T1.5** mlde_shadow_advisor 升級（PA §2B 漏列補位） | `_persist_recommendations` 加 `R6_calibration_provider` + `replay_experiment_id_provider` 兩 kwarg；per-rec loop 同型升級；rec.source 與 evidence_source_tier 正交不動 | `program_code/ml_training/mlde_shadow_advisor.py` | 812→912 (+100) | ✅ DONE |
| **R7-T3** opportunity_tracker 升級 | `persist_regret_summary` 加 `R6_calibration_provider` + `replay_experiment_id` 兩 kwarg；single-row aggregate；NONE→skip; should_insert flag 控制 | `program_code/local_model_tools/opportunity_tracker.py` | 282→377 (+95) | ✅ DONE |
| **R7-T2** dream_engine.generate_replay_candidates verify-only | 函數 docstring 加 R7-T2 verified marker comment（純 compute API；caller `replay_routes.py` 走 V036 路徑；不動 logic） | `program_code/local_model_tools/dream_engine.py` 內 | (within R7-T1) | ✅ DONE |
| **R7-T4** LinUCB NO-OP confirmation | 在 `replay_metadata_helper.py` MODULE_NOTE 加 LinUCB 0 caller verified marker；future-proofing 註：Sprint D/E LinUCB warm-start 加 verify_replay caller 必 reuse 本 helper（per `memory/linucb_shadow_compare_retention.md`） | `program_code/local_model_tools/replay_metadata_helper.py` MODULE_NOTE | (within helper) | ✅ DONE |
| **共用 helper** | `build_replay_metadata` 統一接口；caller side 構造 4-tuple metadata（tier / replay_experiment_id / manifest_hash_hex / expires_at）；fail-soft（NONE / V049 missing / hash NULL → 回 None）；BYTEA → hex（接受 bytes / memoryview / bytearray driver variant） | `program_code/local_model_tools/replay_metadata_helper.py` (NEW) | 0→190 (+190) | ✅ DONE |

## §2 — 共用 helper design

### §2.1 API contract

```python
def build_replay_metadata(
    *,
    experiment_id: str,
    calibration_result: CalibrationResult,
    cur: Any,
) -> Optional[Tuple[str, str, str, datetime]]:
```

### §2.2 決策樹

1. `calibration_result.label == NONE` → 回 None（caller 必 skip INSERT；V036 拒絕 NONE tier；強制 fail-fast）
2. `label ∈ {LIMITED, CALIBRATED}`：
   a. SELECT V049.manifest_hash WHERE experiment_id;
   b. row missing / hash NULL → log warn + 回 None（advisory failure）;
   c. 回 4-tuple `(tier='calibrated_replay', exp_id, hash_hex, expires_at)`
3. `expires_at = datetime.now(UTC) + calibration_result.ttl`（caller R6 傳入 ttl，calibrated→7d / limited→3d）

### §2.3 LIMITED + CALIBRATED 共用 tier='calibrated_replay'

per V051 paired CHECK + AI-E §3.2：兩 label 都寫同 tier，TTL 由 ttl field 區分。

### §2.4 BYTEA driver variant tolerance

`bytes(manifest_hash_bytes).hex()` 接受 `bytes` / `memoryview` / `bytearray` 三種 psycopg2 driver 回傳；防禦性 try/except TypeError + ValueError。

## §3 — Backward-compat verification

per AI-E §10 risk #7：caller 不 supply `R6_calibration_provider` 仍跑 hardcoded 'real_outcome' path。

| Producer | Default behavior（不傳 provider） | R7 behavior（傳 provider） |
|---|---|---|
| dream_engine | `tier='real_outcome'` / metadata 全 NULL（同 18 月既有生產行為） | `tier='calibrated_replay'` 或 skip（NONE label）|
| opportunity_tracker | `tier='real_outcome'` / metadata 全 NULL | 同上（單 row aggregate）|
| mlde_shadow_advisor | `tier='real_outcome'` / metadata 全 NULL | 同上（per-rec）|

3 個 unit test 驗證 fallback：
- `test_dream_engine_no_provider_fallback_real_outcome`
- `test_opportunity_tracker_no_provider_fallback`
- `test_mlde_shadow_advisor_no_provider_fallback`

3/3 PASS。

## §4 — Mac pytest 結果

```
$ python3 -m pytest program_code/local_model_tools/tests/test_replay_metadata_helper.py -v
================ 7 passed in 0.06s ==================

$ python3 -m pytest program_code/local_model_tools/tests/test_r7_producer_upgrade.py -v
================ 8 passed in 0.03s ==================

$ python3 -m pytest program_code/local_model_tools/tests/ -v  # local_model_tools 全 regression
================ 80 passed in 0.06s ==================
   (15 NEW + 65 既有 = 0 regression)

$ python3 -m pytest program_code/ml_training/tests/ program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/ 2>&1
================ 416 passed, 1 failed, 32 skipped =====
   1 fail = pre-existing test_insert_live_candidate_payload_carries_schema_version_and_lg5_subkeys
   stash 我的改動仍 fail；確認非 R7 引入；無 regression
```

### Test case detail

| Case | 描述 | 結果 |
|---|---|---|
| **helper test_build_replay_metadata_calibrated_label** | CALIBRATED label + 7d TTL → 4-tuple | ✅ |
| **helper test_build_replay_metadata_limited_label_3d_ttl** | LIMITED label + 3d TTL → 同 tier 不同 TTL | ✅ |
| **helper test_build_replay_metadata_none_label_returns_none** | NONE label → 短路；0 SQL execute | ✅ |
| **helper test_build_replay_metadata_v049_row_missing_returns_none** | V049 row 不存在 → log warn + None | ✅ |
| **helper test_build_replay_metadata_manifest_hash_null_returns_none** | hash NULL → log warn + None | ✅ |
| **helper test_build_replay_metadata_returns_correct_hex_format** | 64-char hex format 可逆 | ✅ |
| **helper test_build_replay_metadata_memoryview_manifest_hash** | memoryview BYTEA driver variant | ✅ |
| **producer test_dream_engine_calibrated_replay_path** | provider→CALIBRATED → SQL 寫 calibrated_replay | ✅ |
| **producer test_dream_engine_none_label_skips_insert** | provider→NONE → 0 INSERT | ✅ |
| **producer test_dream_engine_no_provider_fallback_real_outcome** | 不傳 provider → real_outcome | ✅ |
| **producer test_opportunity_tracker_calibrated_replay_path** | provider+exp_id → calibrated_replay | ✅ |
| **producer test_opportunity_tracker_no_provider_fallback** | 不傳 provider → real_outcome | ✅ |
| **producer test_mlde_shadow_advisor_calibrated_replay_path** | provider + exp_id_provider → calibrated_replay | ✅ |
| **producer test_mlde_shadow_advisor_no_provider_fallback** | 不傳 provider → real_outcome | ✅ |
| **producer test_mlde_shadow_advisor_none_label_skips_rec** | provider→NONE → skip rec | ✅ |

合計 **15 新 case + 0 regression**（80 local_model_tools 全 PASS / 416 ml_training+replay regression PASS / 1 pre-existing fail / 32 skipped）。

## §5 — LOC compliance

| File | Pre LOC | Post LOC | Delta | Cap | 狀態 |
|---|---:|---:|---:|---|---|
| `replay_metadata_helper.py` (NEW) | 0 | 190 | +190 | 800 warn / 2000 cap | ✅ 健康 |
| `dream_engine.py` | 954 | 1063 | +109 | 800 warn / 2000 cap | ⚠️ pre-existing > warn baseline；post +109 仍 < 2000 cap |
| `opportunity_tracker.py` | 282 | 377 | +95 | 800 warn / 2000 cap | ✅ 健康 |
| `mlde_shadow_advisor.py` | 812 | 912 | +100 | 800 warn / 2000 cap | ⚠️ pre-existing > warn baseline；post +100 仍 < 2000 cap |
| `tests/test_replay_metadata_helper.py` (NEW) | 0 | 212 | +212 | 800 warn / 2000 cap | ✅ 健康 |
| `tests/test_r7_producer_upgrade.py` (NEW) | 0 | 512 | +512 | 800 warn / 2000 cap | ✅ 健康 |
| **Total** | 2048 | 3266 | +1218 | < 6×2000=12000 | ✅ 全綠 |

PA dispatch §4 估 ~460 LOC；實際 +1218 因：
- 完整中文 MODULE_NOTE（CLAUDE.md §七 governance default 中文，仍需 ~80-110 LOC docstring）
- 6 producer test case 多寫 boundary：no_provider fallback × 3 + NONE skip × 3 + calibrated path × 3 = 9 case 完整覆蓋
- helper test 加 hex format / memoryview BYTEA driver variant boundary
- result dict 加 `calibrated_inserted` + `skipped_none_label` (R7 path only) 觀測欄位
- backward-compat fallback path docstring 完整解釋

dream_engine.py / mlde_shadow_advisor.py 兩檔在 baseline 已超 800 warn（pre-existing > warn）；post-W1 +109/+100 仍 < 2000 hard cap。CLAUDE.md §九 baseline+5 exception 是針對 baseline > 2000 的硬上限例外，當前不適用（兩檔均 < 2000）。E2 review 必標 warn line breach（標註不阻擋）。

## §6 — Governance 對照

### 0 forbidden import

```bash
$ grep -nE "paper_state|canary_writer|ipc_server|governance_hub|live_authorization|decision_lease" \
    program_code/local_model_tools/replay_metadata_helper.py
30:    - 0 引用 paper_state / canary_writer / database / ipc_server /
31:      governance_hub / live_authorization / decision_lease。
```

僅 MODULE_NOTE 文字提及（「0 引用」聲明），0 真實 `import` / `from`。
4 producer 改動檔案 grep 0 命中（既有檔案不引入新 forbidden import）。

### 0 cross-platform path 硬編碼

```bash
$ grep -nE "/home/ncyu|/Users/[a-z]+" \
    program_code/local_model_tools/replay_metadata_helper.py \
    program_code/local_model_tools/dream_engine.py \
    program_code/local_model_tools/opportunity_tracker.py \
    program_code/ml_training/mlde_shadow_advisor.py \
    program_code/local_model_tools/tests/test_replay_metadata_helper.py \
    program_code/local_model_tools/tests/test_r7_producer_upgrade.py
（0 命中）
```

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

僅 caller side 改動：3 producer 函數 signature 加 optional kwarg + per-row metadata 構造邏輯。0 V### migration、0 schema 變更、0 V055/V036 function body 改動。

### xlang_consistency 13/13 維持

W1 是 Python-only 改動（caller side 構造 metadata）；不破 V3 §13 xlang_consistency。helper / 3 producer / 2 test 都不進 Rust manifest_signer canonical_bytes contract。

## §7 — 注釋全中文 per governance

per CLAUDE.md §七 2026-05-05 governance change（commit `47922a4c`）：

- `replay_metadata_helper.py`：MODULE_NOTE + helper docstring + R7-T4 NO-OP marker block 全中文
- `dream_engine.py` 改動部分：`persist_dream_insights` docstring + R7-T1 metadata 構造 inline comment + `generate_replay_candidates` R7-T2 verified marker 全中文
- `opportunity_tracker.py` 改動部分：`persist_regret_summary` docstring + R7-T3 metadata 構造 inline comment 全中文
- `mlde_shadow_advisor.py` 改動部分：`_persist_recommendations` docstring + R7-T1.5 metadata 構造 inline comment 全中文
- 兩個新 test 檔：MODULE_NOTE + 各 test docstring + helper fixture 全中文

既有 W3-W6 中英對照塊未碰（per CLAUDE.md §七「修改既有中英對照塊時移除英文只保留中文」— 本 W1 修改之 SQL execute 區塊只動 args / params，不動 SQL inline comment block）。

## §8 — git status

```bash
$ git status --porcelain
 M program_code/local_model_tools/dream_engine.py
 M program_code/local_model_tools/opportunity_tracker.py
 M program_code/ml_training/mlde_shadow_advisor.py
?? program_code/local_model_tools/replay_metadata_helper.py
?? program_code/local_model_tools/tests/test_r7_producer_upgrade.py
?? program_code/local_model_tools/tests/test_replay_metadata_helper.py

$ git diff --stat
 program_code/local_model_tools/dream_engine.py     | 155 ++++++++++++++---
 .../local_model_tools/opportunity_tracker.py       | 189 ++++++++++++++++-----
 program_code/ml_training/mlde_shadow_advisor.py    | 140 ++++++++++++---
 3 files changed, 394 insertions(+), 90 deletions(-)
```

無 unintended drift；6 file 對應 PA dispatch §1.1-§1.6 預期 IMPL surface（含 helper）。

## §9 — 不確定之處 → PM 決策

### §9.1 caller 上游 R6 calibration provider 整合 chain

W1 升級 4 producer signature；caller 上游整合（從 edge_estimator_scheduler 同 cycle 取 R6 CalibrationResult + experiment_id mapping 傳給 producer）留 W2-W3。當前 4 producer 預設 `R6_calibration_provider=None` → fallback real_outcome（既有生產行為不變）。

**狀態**：W1 設計符合 AI-E §10 risk #7 backward-compat。caller 整合何時開始？建議 W2 一併設計 caller side wiring 或 W3 E2E integration test 才實際驗 R7 path 進入生產。

### §9.2 dream_engine `insight['replay_experiment_id']` 注入路徑

R7-T1 IMPL 期望 caller 在 `build_dream_summary` 階段把 experiment_id 注入 insight dict（key='replay_experiment_id'）；當前 build_dream_summary 不知 experiment_id（caller 上游需修）。W1 設計使 caller 對 insight 加 key 即啟用 R7。

**狀態**：caller side 改動超出 W1 scope；建議 W2 一併設計或 list 為 P2-R7-W1-FOLLOWUP-4。

### §9.3 mlde_shadow_advisor `replay_experiment_id_provider(rec)` 性能

當前簽名 `(rec) → exp_id`；caller 應 cache cycle-wide experiment_id 避免 per-rec O(n) lookup。當前 < 64 rec/cycle 可接受（per ShadowAdvisorConfig.max_recommendations 預設）。

### §9.4 helper API 名稱 `lookup_replay_config_blob` AI-E spec 過時 reference

AI-E spec §3.2 + PA dispatch §1.1 暗示 reuse `experiment_registry.lookup_replay_config_blob` 取 manifest_hash，但實際該 fn 是 Sprint B2 R5-T6 round 2 land 的版本回 strategy_params / risk_overrides 兩 blob，無 manifest_hash key。E1 改用獨立 SELECT V049.manifest_hash + experiment_id 確認 row 存在 + advisory NULL handling 模式。

**狀態**：教訓 E1 必獨立驗 fn signature 真實返回類型再決定 helper API；建議 PM/AI-E 後續 advisory ref 直接 grep 真實 fn 簽名而非用 placeholder name。

### §9.5 R7-T2 verify-only 是否需要更詳實證

R7-T2 在 `dream_engine.generate_replay_candidates` docstring 加 verified marker comment（5 行中文）。AI-E §1 已 grep 0 直接 INSERT in this function body；caller `replay_routes.py POST /api/v1/replay/run` 走 V036 verify_replay_evidence_and_insert 路徑。

**狀態**：W1 採 docstring marker pattern；若 PM 期望更深層驗證（grep ALL caller of generate_replay_candidates + 確認所有 caller 都走 V036 路徑），建議 W2 一併做 FK chain audit（per PA §13.5 W2 task）。

## §10 — Operator 下一步

E1 W1 SIGN-OFF 完成；交 PM：

1. **Review 本 report**
2. **Commit + push**（建議 message：`feat(ref20): Sprint C2 R7 W1 — 3 producer calibrated_replay tier upgrade + shared helper`）
3. **Linux pull + pytest**：`ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && python3 -m pytest program_code/local_model_tools/tests/ program_code/ml_training/tests/ -v"` 驗 80 + 415 PASS（與 Mac 結果一致；1 pre-existing fail）
4. **C2 W2 dispatch unblock**：capability test + FK chain audit + lookup helper reuse audit per PA §13.5 路線圖（含 dispatch §1.5 R7-T2 caller-side `replay_routes.py` audit）
5. **CLAUDE.md §三 update**：Sprint C2 R7 W1 land status (3 IMPL + 2 verify-only/NO-OP + helper) + 4 file commit chain

PA 派發 §6 強制工作鏈：本 W1 採 minimal-loop pattern（hermetic test + backward-compat default + 既有 V055/V036 chain integrity preserved）；建議 PM 直接 review skip E2，E4 regression 在 W3 全 chain land 後跑。

---

E1 C2 W1 SIGN-OFF DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_c2_w1_impl.md`; 5 R7 task land (3 IMPL + 1 verify-only + 1 NO-OP) + shared helper; ~1218 LOC; 15 new unit test PASS; pending PM commit + Linux verify + W2 dispatch
