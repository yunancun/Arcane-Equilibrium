# E1 LG-5-IMPL-1 ROUND 2 — CRITICAL spec drift fix

**Date**: 2026-05-02
**Agent**: E1 (Backend Developer)
**Wave**: LG-5 Wave 1 task #2 of 2 — round 2 (after E2 adversarial review)
**Spec**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md` §2.2 line 140 + MIT MF-M3

---

## 1. CRITICAL spec drift root cause

Round 1 enrichment 寫到了錯的表：
- 把 5 個新 sub-key 寫到 `learning.mlde_shadow_recommendations`（透過 `_insert_live_candidate`）
- 但 consumer (`GovernanceHub.review_live_candidate`) 讀的是 `learning.mlde_param_applications` filter `engine_mode='live' AND status='candidate' AND application_type='live_promotion_candidate'`
- 該 row 由 `_apply_one()` 的 `_record_application(...)` 寫入，round 1 payload 還是 bare 2-key
- 結果：consumer 對所有新 candidate 永遠 defer / reject `schema_unknown`

## 2. Fix design：single SoT helper

新增 `_build_live_candidate_payload(cur, *, source_row, application_id, application_type, patch, strategy_name)`：

- 統一構造 LG-5 §2.1 producer payload（schema_version + 5 sub-key）
- 兩處 writer 共用：
  - `_insert_live_candidate` 寫 `mlde_shadow_recommendations`（audit / monitoring 路徑，保留向後相容）
  - `_apply_one` 的 `_record_application(...)` payload arg 寫 `mlde_param_applications`（consumer 真正讀的表）
- 兩 writer 1:1 同步，下次 schema change 只動一處

## 3. MEDIUM fix：realized_window n_strategy_fills 不再硬編 0

`_compute_demo_realized_window(cur, strategy_name=None)` 簽名擴展：
- 第二參數 `strategy_name: Optional[str] = None`（向後相容）
- 內部呼叫 `_compute_demo_sample_count_strategy_cell` 填寫 `n_strategy_fills`
- RFC §3 R3 直接讀此欄位判斷 `n_strategy_fills < 100 → defer`

## 4. 修改清單

| path | 動作 | 行數 delta | 說明 |
|---|---|---|---|
| `srv/program_code/ml_training/mlde_demo_applier.py` | 修改 | 1272 → 1374 (+102) | 新 `_build_live_candidate_payload` helper + `_compute_demo_realized_window` 簽名擴展 + `_insert_live_candidate` 重構為呼叫 helper + `_apply_one` 第二處 `_record_application` payload 改用 helper |
| `srv/program_code/ml_training/tests/test_mlde_demo_applier.py` | 修改 | 443 → 775 (+332) | 3 新測試：cost_baseline fail-soft on SQL exception / record_application payload matches LG-5 contract / round-trip param_applications table；2 處 monkeypatch lambda 簽名修正（`_compute_demo_realized_window`）|

## 5. 驗證結果

| 測試 | 結果 |
|---|---|
| `pytest program_code/ml_training/tests/test_mlde_demo_applier.py -q` | **15 passed** (round 1 12 + 新 3) |
| `pytest program_code/ml_training/tests/test_mlde_shadow_advisor.py -q` | **5 passed** |
| `pytest program_code/exchange_connectors/.../control_api_v1/tests/ -q --ignore=integration` | **3256 passed / 10 skipped** baseline preserved |
| `wc -l mlde_demo_applier.py` | 1374 < 1500 ✅ |
| `git diff --check` | 0 whitespace ✅ |
| `grep '/home/ncyu\|/Users/[^/]+' mlde_demo_applier.py` | 0 hit ✅ |
| 雙語注釋 | helper docstring 中英對照 + inline 注釋雙語 ✅ |

## 6. 邊界 case 決策

1. **雙處 caller 共用 helper 風格**：選用 `_build_live_candidate_payload` 純建構（不寫 DB），各 writer 自己呼 SQL，理由：(a) helper 不知道目標表結構，(b) `_record_application` 已是現成 INSERT path，重用避免重複 SQL，(c) 兩處 SQL 不同表，硬抽到 helper 內反而耦合。
2. **strategy_name 傳遞鏈**：
   - `_apply_one` 從 `row.get("strategy_name")` 取，傳給 `_build_live_candidate_payload(strategy_name=...)`
   - helper 再傳給 `_compute_demo_realized_window(cur, strategy_name)` 與 `_compute_demo_sample_count_strategy_cell(cur, strategy_name)`
   - 兩處 helper 對 `None` / 空字串 short-circuit 回 0，保 fail-soft
3. **保留 `mlde_shadow_recommendations` 寫入**：未刪 round 1 加的 enrichment，理由 PA spec 明示「audit / monitoring 路徑可能依賴；雙寫意圖需 PA confirm，不在本 round scope」。
4. **`_compute_demo_realized_window` 簽名向後相容**：第二參數 default `None`，現有 round 1 test (`test_lg5_helpers_return_well_formed_dicts...`) 不修可運作；只更新 monkeypatch lambda 簽名（接受可選 `_strategy=None`）。
5. **3 新 unit test 不依賴真實 DB**：採 monkeypatch 4 helper + 模擬 cursor，跨平台 Mac/Linux 都可跑；不需 Linux Postgres。

## 7. 不確定之處

1. **`mlde_shadow_recommendations` 雙寫**：PA spec 明示保留，但長期是否需要 deprecate 該寫入路徑（consumer 不讀）→ 未來 wave 評估，**不在 round 2 scope**。
2. **Consumer (IMPL-2) 適配**：consumer 端 `GovernanceHub.review_live_candidate` 由 sibling/後續 task 實作；本 round 只保證 producer payload 滿足 contract。
3. **Production cycle latency**：每筆 candidate 建構新 payload 需 7-8 個 SELECT；high-rate 16-cand cycle 加 ~80-160ms；若撞牆 follow-up cache（非 spec 要求）。

## 8. 治理對照

| 規則 | 編號 | 符合？ |
|---|---|---|
| AI 輸出 != 即時命令 | CLAUDE.md §二 #3 | ✅ payload enrich 不繞 consumer |
| 失敗默認收縮 | CLAUDE.md §二 #6 | ✅ helper fail-soft；schema mismatch consumer fail-closed |
| 可解釋 | CLAUDE.md §二 #8 | ✅ source_demo_application_id 可反查；source_healthchecks 標記 [33][40] |
| 跨平台兼容 | CLAUDE.md §七 ★★ | ✅ 0 path hardcoded |
| 雙語注釋 | CLAUDE.md §七 | ✅ 新 helper 中英對照 docstring + inline |
| 文件大小 | CLAUDE.md §九 | ⚠️ 1374 < 1500 hard cap，>800 warning（pre-existing；split 屬未來 wave） |
| 不擴大範圍 | E1 工作規則 | ✅ V001-V035 / governance_hub / TOML / RFC 全未動 |
| 硬邊界 | CLAUDE.md §四 | ✅ 0 觸碰 |

## 9. Operator 下一步

1. **E2 round 2 review**：重點確認：
   - Helper SoT 設計合 consumer-side contract
   - 兩處 writer 1:1 payload sync
   - `n_strategy_fills` 不再硬編 0
   - 3 新測試覆蓋 fail-soft / contract / round-trip
2. **E4 regression**：Mac 已驗 15 + 5 + 3256 全綠；Linux runtime 待 IMPL-2 ship 後跑真 demo cycle 驗 PG JSONB column。
3. **PM 統一收 wave**：等 E2 round 2 PASS + E4 regression → PM 統一 commit + push。E1 不自行 commit。
