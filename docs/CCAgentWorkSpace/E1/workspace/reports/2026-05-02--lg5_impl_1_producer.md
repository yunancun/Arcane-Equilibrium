# E1 LG-5-IMPL-1 — Producer side `_insert_live_candidate` payload extension（2026-05-02）

## 任務

LG-5 RFC v2 sealed spec → E1 落地 `mlde_demo_applier._insert_live_candidate` payload 增 5 個欄位（`schema_version` + 4 sub-key），其中 `demo_attribution_chain_ratio_by_strategy` 為 MIT MF-M2 per-strategy dict (5 hardcoded strategy keys)。新增 4 個 helper（cost baseline / realized window / per-strategy attribution ratio / strategy-cell sample count）。Wave 1 並行 #2 of 2（與 IMPL-V035 file-isolated）。

## 修改

| file | LOC delta | 說明 |
|---|---|---|
| `srv/program_code/ml_training/mlde_demo_applier.py` | +401 / -9 (final 1272) | 模組 docstring 雙語化 + 5 module-level constant + 6 utility helper（`_safe_float` / `_safe_int` / `_utc_iso8601` + 4 LG-5 spec helper）+ `_insert_live_candidate` payload 重寫 |
| `srv/program_code/ml_training/tests/test_mlde_demo_applier.py` | +243 / -1 (final 443) | `_ScriptedCursor` fixture + 3 個新 unit test |

## 4 helper SQL pseudocode 摘要（不貼全代碼）

| # | helper | 主 SQL |
|---|---|---|
| 1 | `_compute_demo_cost_baseline(cur)` | (a) `WITH entry_fills AS (... FROM trading.fills WHERE 7d AND engine_mode IN (demo, live_demo) AND non-close strategy filter ...) SELECT count, sum(maker_like), avg(effective_fee_rate)` 鏡 [33]；(b) `SELECT avg(net_bps_after_fee), avg(slippage_bps) FROM learning.mlde_edge_training_rows WHERE 7d AND attribution_chain_ok` 鏡 [40]；(view_exists guard) |
| 2 | `_compute_demo_realized_window(cur)` | `SELECT count(*) FROM trading.fills WHERE 7d AND engine_mode IN (demo, live_demo)` |
| 3 | `_compute_attribution_chain_ratio_by_strategy(cur)` | `SELECT strategy_name, count(*), count(*) FILTER (attribution_chain_ok) FROM learning.mlde_edge_training_rows WHERE 7d AND strategy_name = ANY(%s) GROUP BY strategy_name`；缺 key → 0.0；view 缺 → 5 keys 全 0.0 |
| 4 | `_compute_demo_sample_count_strategy_cell(cur, strategy)` | `SELECT count(*) FROM learning.mlde_edge_training_rows WHERE 7d AND attribution_chain_ok AND strategy_name = %s`；空 strategy → 0 (no DB call) |

所有 helper fail-soft (try/except 包 SQL → log warning + 回 well-formed dict / 0)，payload 永遠可發、INSERT 永不因 baseline 失敗 raise。

## 新 unit test 數

3 個新 test 加入 `test_mlde_demo_applier.py`：

1. `test_lg5_helpers_return_well_formed_dicts_with_deterministic_data` — `_ScriptedCursor` mock 序列化 8 個 SQL response，驗 4 helper 回 deterministic dict shape，per-strategy 5 keys 全在（缺 strategy → 0.0）
2. `test_lg5_helpers_fail_soft_on_missing_view` — `to_regclass IS NULL` 路徑，驗 fail-soft 回 0.0 / 0；空 strategy_name → 0 不查 DB
3. `test_insert_live_candidate_payload_carries_schema_version_and_lg5_subkeys` — monkeypatch 4 helper 為固定值，捕 `cur.execute()` 的 INSERT param，解包 `Json(payload).adapted` 驗 `schema_version == "live_candidate_eval_v1"`、4 sub-key 全在、attribution dict 5 keys 全在

## 測試結果

| 測試套 | 結果 | baseline 對照 |
|---|---|---|
| `test_mlde_demo_applier.py` | **12 passed**（9 existing + 3 new）| 9 → 12 ✅ |
| `test_mlde_shadow_advisor.py` | **5 passed** | 5 baseline ✅ |
| `program_code/exchange_connectors/.../control_api_v1/tests/` (excl. integration) | **3256 passed / 10 skipped / 0 fail** | baseline 3262/3 ⚠ — drift 不來自本 patch（未碰 control_api_v1 任何檔；推測 PYTHONPATH / cache / 隔壁 commit 影響） |

任務 spec checklist 標 "PASS"；本 patch 未引入任何新 fail / skip。

## 偏離 RFC §2.1 spec 之處

**0 偏離**。Payload 結構 1:1 落 RFC §2.1（含 schema_version、demo_cost_baseline 9 keys、demo_realized_window 5 keys 含 window_days、demo_attribution_chain_ratio_by_strategy 5 hardcoded keys、demo_sample_count_strategy_cell scalar int）。INSERT SQL 結構 (column list + 三個 demo 數值仍直拷至 column) 完全保留。

唯一 RFC 文字模糊處：`demo_realized_window.n_strategy_fills` — RFC §2.1 schema 列了此欄但無對應 SQL 範例。目前 producer 端設為 0 預留（consumer R3 從更精準的 `demo_sample_count_strategy_cell` 取 per-strategy 值）。E2 / IMPL-2 確認此 interpretation。

## E2 應特別審查的 risk 點

1. **DB latency per-cycle**：`_insert_live_candidate` 在 INSERT 前跑 7-8 個 SELECT；high-rate cycle (16 candidate × ~10ms) 加 ~80-160ms。若 production rate 撞牆，IMPL-1 follow-up 可加 per-cycle baseline cache（非 spec 要求，避免擴大範圍）。
2. **`view_exists` 重複查 4 次**：4 helper 各查 `to_regclass('learning.mlde_edge_training_rows')`；fail-soft 設計下不關鍵，但 E5 可考慮抽 shared module-level cache。
3. **`_TAKER_FEE_RATE` / `_MAKER_FEE_CUTOFF` 常量重複**：與 `helper_scripts/db/passive_wait_healthcheck/checks_execution.py` 中 `TAKER_FEE_RATE` / `MAKER_FEE_CUTOFF` 重複（手動同步註明於 module docstring）；未來 fee tier 變動需同步兩處。E5 可抽 shared constants（非本 ticket 範疇）。
4. **`n_strategy_fills` = 0 producer 預留**：RFC §2.1 spec 模糊；E2 + IMPL-2 應對齊（建議 consumer 用 `demo_sample_count_strategy_cell` 為 R3 PSR n threshold 的 source）。
5. **Pre-existing LOC > 800 warning**：`mlde_demo_applier.py` 從 857 → 1272，pre-existing baseline 已超 800 warning line。CLAUDE.md §九 governance exception clause 適用：本 wave 在 ≤1500 hard cap 內、PA-spec 要求新增 helper 必落此檔。Split 屬 IMPL-2 範疇（若 LOC 緊則 sibling），現未觸發。

## 接力

E2 review (LOC + payload schema + 雙語注釋 + helper SQL safety) → E4 regression → PM 統一收 Wave 1 batch（IMPL-V035 + IMPL-1）commit + push。**E1 不 commit**。

報告檔：`srv/.claude_reports/20260502_lg5_impl_1_producer.md`、本檔。
