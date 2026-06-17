# Phase 2 E1-C — strategist promote route enhancement (待 E2)

- Date: 2026-06-17 · Role: E1 (Backend) · Wave: E1-C (Python route)
- Source of truth: `docs/execution_plan/2026-06-17--intelligent-param-adjusting-agent-master-spec.md` §2.0-§2.12 (§2.10 E1-C)
- Status: IMPL DONE, Mac self-test green; NOT committed (chain E1→E2→E4→PM)

## 任務摘要
在既有 `strategist_promote_routes.py`（已 wired，已 5-gate + Phase-0 token）疊加 Phase 2 的四個結構性閘 + net-new demote。**ENHANCEMENT 非 greenfield**：不重建 route、不接 `promote_params_to_live` Rust stub（繞 chokepoint+token）。SHARED CONTRACT 名：IPC `evaluate_promotion_criteria`（唯讀豁免 token）/ 表 `learning.strategist_promotions` / flag `OPENCLAW_STRATEGIST_PROMOTION_ENABLED`（default-OFF）。E1-A/B 實作 contract，E1-C 對 spec contract 編程 + 測試 mock。

## 修改清單
- `app/strategist_promote_routes.py`（+~850 行，778→1628）：
  - MODULE_NOTE 更新（標 Phase 2 ENHANCEMENT 四點 + 不接 stub）；移除「strategist_promotions 表 NOT created here」的過時段。
  - 模塊常數 + `_promotion_enabled()`（flag，只認字面 "1"，鏡 strategy_write_routes）。
  - §2.4 helper：`_diff_tuned_param_names`（direction allowlist 輸入）、`_fetch_demo_soak_metrics`（soak wall-clock / since-change / 21d demo fills；trading.fills schema 校正見下）、`_evaluate_criteria`（唯讀 IPC evaluate_promotion_criteria，雙形信封容忍，fail-closed）、`_capture_pre_promotion_snapshot`（§2.5 步驟①）。
  - §2.6 helper：`_insert_promotion_audit`（同步 fail-closed INSERT，`%s::jsonb`+json.dumps，commit/rollback，失敗 raise）、`_fetch_promotion_row`、`_as_param_dict`。
  - `post_strategist_promote` apply 路徑：Step 4a flag gate（live→409 promotion_disabled）→ Step 4b criteria gate（pre-snapshot+soak+tuned-diff→IPC→非 Eligible 409 criteria_not_met，0 IPC promote，denied audit best-effort）→ 既有 5-gate → 既有 token+IPC → Step 7 同步 fail-closed audit（INSERT 失敗→500 audit_write_failed loud）。
  - 新 `DemoteRequest` + `POST /demote`（同 router auto-wire）：flag+operator+取 promote row+precondition guard（canonical 比對 current-live vs promoted_params_json→409 live_changed_since_promotion）+preview(confirm=false)+5-gate+token+IPC 還原**完整** pre set+同步 fail-closed demote audit。`_params_canonically_equal` 復用 live_patch_token.canonical_json。
- `tests/test_strategist_promote_phase2.py`（新，14 test）。
- `tests/test_strategist_promote_api.py`（改 2 collateral live-apply test：flag ON + method-routed IPC + criteria Eligible + mock insert，保留它們測 5-gate 鏈的原意；§2.8 文檔化行為改變）。

## 關鍵 diff / 設計決策
- **§2.4.G 取 edge 路徑**：選「engine 自查」（首選）——route 只傳 strategy + soak/fills metric + tuned_param_names，engine 自查 live EdgeEstimates snapshot + cost wall + boundary-vs-LIVE-envelope。route **不**硬編 12/7（SSOT 在 Rust）、**不**回 demo_boundary_violation_count（交 engine 自查 live risk_config）。
- **fail-closed 順序**：flag→pre-snapshot（抓不到→503）→soak metric（DB 失敗→503）→criteria IPC（失敗→503 criteria_evaluation_unavailable，無 verdict 不放行）→非 Eligible→409。**無證據一律不促升**。
- **demote 裁決 B（EXACT）**：送回完整 pre-promotion typed set → Rust typed deserialize 整 struct 還原行為。demote audit row 的 pre/post 反向記（pre=被回滾掉的 promoted set，promoted=還原後的 pre set）。
- **trading.fills schema 校正（spec 未明，親查 V021/V033）**：欄名 `strategy_name`（非 `strategy`）、時間欄 `ts` timestamptz（非 `ts_ms`）→ soak fills 用 `ts >= now() - INTERVAL '21 days'`。

## 治理對照
- 硬邊界：0 觸碰 max_retries/live_execution_allowed/execution_authority/system_mode；5-gate 邏輯與 token-mint 邏輯**只驗不改**（已正確）；0 RiskConfig 觸碰（全程 update_strategy_params strategy-param sink）。
- 不接 promote_params_to_live stub（P7 learning 不自動改寫 live；promote/demote 唯一觸發=operator confirm=true route）。
- criteria IPC 唯讀（不入 LIVE_WRITE_METHODS，token 豁免）；flag default-OFF=只收緊永不放寬（POLICY-2 fail-loud 姿態）。
- 0 hardcoded user path（grep 自證）；JSONB/INSERT 走既有 project 慣例。
- 無新 migration（E1-B 負責 V###）；無新 secret；無新 singleton（minter 無狀態既有）。

## 測試與 mutation bite（Mac，venvs/mac_dev py3.12）
- phase2(14) + promote_api(20) = **34 passed** isolated。
- mutation A/B 全紅還原綠：①neuter flag gate→flag-OFF 測紅；②criteria 視全 Eligible→Reject+Pending 測紅；③swallow audit-fail→audit-500 測紅；④disable demote precondition→precondition 測紅。
- test_api_contract.py 11 fail = pre-existing（單跑亦紅，403 在 recheck/input/evolution/scout 路由，與 strategist_promote 0 關，importlib.reload 跨 test 排序污染，既有 fixture 已註）。

## 不確定之處 / 待 follow-up
- **依賴 E1-A IPC verdict shape** `{verdict: "Eligible"|"Pending"|"Reject", reason, criteria_input}`。我按 spec §2.4.E 契約編程；若 E1-A 落地的鍵名不同需對齊（E4 端到端驗）。
- **依賴 E1-B 表 schema** `learning.strategist_promotions`（§2.7 欄名）。我的 INSERT 欄序鏡像 §2.6 schema；E1-B 釘死後 E4 Linux PG 親查 row 真落 + criteria_input_json 完整。
- **檔案大小**：strategist_promote_routes.py 778→1628 行，超 800 review 門檻（未達 2000 hard cap）。約半是 bilingual docstring。**建議 follow-up**：criteria-query helpers + demote 可 extract 到 sibling `strategist_promote_helpers.py`。本批守 surgical-change 不主動拆，標 review-attention。

## Operator / 下一步
- E2 對抗審（§2.11 四點 + grep 無第二 live caller 繞 criteria）。
- E4 Linux 真 Live engine：criteria 在 0-validated-cell 回 Pending（誠實標 §2.9）/ promote+demote 往返 byte-equal / precondition-fail 409 / strategist_promotions row 親查 / IPC 簽名與 E1-A 對齊 / double-apply（E1-B migration）。
