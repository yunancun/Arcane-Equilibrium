# E1 — Phase 2 promote contract/wiring 修復（E2 FAIL + QC FAIL 八項）

- **Date:** 2026-06-17 · **Role:** E1 · **Status:** IMPLEMENTATION DONE_WITH_CONCERNS（待 E2 re-review）
- **Driver:** adversarial review confirmedFindings[]（2C/0R 全數），route↔handler IPC 契約分叉被 mock 掩蓋
- **不可 commit**：等 E2 審查 → E4 回歸 → PM。

## 任務摘要
route（E1-C）與 handler（E1-A）並行建構時 IPC 契約分叉、測試 mock 掉 IPC 使 mismatch shipped。
我同時持有兩側，對齊到單一契約並以真 contract test 鎖死。**純函數 promotion_criteria.rs 邏輯零改動**（grep 證新檔 ?? 未被我編輯，10-step + tag() 小寫全在）。

## IPC-契約裁決 = **Option A**
route 算齊所有 metric（active_symbols + cost 參數 + boundary + soak + tuned）傳入；engine 只自查 edge cell。
**理由**：`demo_boundary_violation_count` 需查 demo realized drawdown（DB query）、`active_symbols` 需讀
strategy_params_live + scanner_config 兩份 TOML——sync IPC handler 內無 DB pool / 無 tomllib reader，
不可達；route（async + get_pg_conn + tomllib）是唯一能算齊的層。engine 端保留「必須與 live cost_gate 看
同一記憶體 snapshot」的 edge cell 自查（freshness/runtime_field 一致）。

## 修改清單
**Rust（4 檔，皆與並行 session WIP 零重疊）**
- `rust/openclaw_engine/src/edge_estimates.rs` — 新 `load_promotion_edge`（載 live-grade `edge_estimates_live_demo.json`）+ 2 測試（缺檔→空 / 讀 *_live_demo 非 demo 檔）。
- `rust/openclaw_engine/src/main.rs` — `PROMOTION_EDGE_SLOT` 改注入 **獨立 live-grade holder**（非共用 scanner demo holder）。
- `rust/openclaw_engine/src/ipc_server/dispatch.rs` — cost-wall fallback 1.0/0.2→1.3/0.3（具名 const）+ fee_bps=+INF；handler/slot docstring 訂正為 Option A + live-grade 實況；新 `#[cfg(test)] mod` 斷言 fallback const == risk_config_live.toml `[slippage]`（include_str! parse，drift 即紅）。
- `rust/openclaw_engine/src/strategist_scheduler/mod.rs` — `promote_params_to_live()` doc 標 forward-risk 0-caller stub（Fix 8，無功能改動）。

**Python（route + contract + tests）**
- `app/strategist_promote_contract.py`（**新**）— 單一契約來源：CRITERIA_OUTGOING_KEYS / ELIGIBLE_TOKEN（小寫）/ is_eligible / response per-cell 鍵。route + test 共 import。
- `app/strategist_promote_routes.py` — Fix 1（`_resolve_active_symbols` allowed∩`[universe].pinned` / `_load_live_cost_model` `[slippage]` SSOT / `_compute_demo_boundary_violation_count` demo drawdown vs `[limits]` LIVE envelope / `_build_criteria_ipc_params` 發完整契約 / `_evaluate_criteria` Option A 簽名）；Fix 2（`is_eligible` 小寫比對 + `_criteria_input_from_payload` 讀真鍵）；Fix 3（promote IPC 成功後重讀 get_strategy_params{live} 取完整 set 存 promoted_params_json）。
- `tests/test_strategist_promote_phase2.py` — mock 改 REAL handler shape（小寫 + per_cell）；+TestIpcContractKeysAndCasing（Fix 4：parse 真 Rust handler source 抽 params.get 鍵集 == 契約常數 == route emit；verdict casing）；+TestPromotedFullSetReRead（Fix 3）；+TestRealConfigResolution（不 mock 走真 TOML）。
- `tests/test_strategist_promote_api.py` — `_criteria_ipc` 改小寫+真 shape；2 個 5-gate 測加 `_patch_contract_helpers`。

## 治理對照
- 硬邊界：未碰 max_retries / live_execution_allowed / execution_authority / system_mode / authorization.json。5-gate 決策權威仍在 Python。
- Fix 5 顯著性 bar：promote 閘改讀 **live-grade**（PSR≥0.975/DSR≥0.95/oos_n≥60/wf≥3）`edge_estimates_live_demo.json`（producer 已寫此檔）；scanner/demo cost_gate 仍讀 demo-grade `edge_estimates.json`（隔離不變）。25-sym live 決策不再建在 demo bar。
- Fix 8：root #1 單一寫入口 / #4 不繞風控——doc 明標 in-process channel 繞 chokepoint+token，0 production caller，新 caller=BLOCKER。
- fail-closed：active 解析失敗 / cost model 讀失敗 / boundary DB 失敗 → 一律保守（[] / None→503 / boundary=1）。
- 跨平台：新 config 路徑用 OPENCLAW_BASE_DIR + parents[5]（實測=srv），0 hardcoded user path（grep 證）。
- 新檔 strategist_promote_contract.py 無 mutable singleton（純常數），無需登記。

## 測試結果 + bite 證明
- **Python**：promote phase2 + api 兩套 **41 passed**（38 原 + 3 新 real-config）。flag-OFF/paper/preview byte-identical 子集綠。
- **Bite（mutation A/B 親證）**：① route 送 `strategy_name`（原 bug）→ contract key-set test 紅；② 契約 ELIGIBLE_TOKEN 改大寫 → verdict-casing test 紅；③ promoted_params 還原成 PARTIAL source → full-set test 紅；④ pinned lookup 改回 top-level → real-config test 紅。還原皆綠。
- **Rust**：`cargo build` lib+bin 在一致狀態下綠；我 4 檔 **0 compile error**（grep 證）。**Rust unit-test 全跑 BLOCKED**：並行 session 的 reprice_count / maker_markout_bps / CLOSE_MAKER_* WIP 跨 event_consumer / tick_pipeline / database / panel_aggregator 不完整，lib-test 間歇不可編譯（錯誤全在他人檔，零在我檔）。我暫時補欄驗證仍撞其函數簽名 refactor（CloseMakerFillAudit arity），故 byte-identical 還原他人檔（diff stat 對齊證）後停手。Rust unit-test 權威跑歸 E4 clean tree（Linux）。

## 不確定之處 / Operator 下一步（concerns）
1. **Rust unit-test 未能在 Mac 親跑**（並行 session 髒樹不可編譯，非我引入）→ E4 須在 clean checkout 跑 `cargo test -p openclaw_engine --lib`（promotion_criteria 23 + 新 edge_estimates 2 + 新 dispatch cost-wall-fallback 1）。
2. **Fix 5 live-grade 檔 runtime 依賴**：`edge_estimates_live_demo.json` 由 producer（edge_estimator_scheduler engine_mode='live_demo'）寫；須確認該 cron/scheduler 在 runtime 真有跑寫此檔，否則 promote 閘永遠空 holder→Pending（fail-closed 安全，但不是預期的「有 validated edge 即可促升」）。E4/operator 確認 live_demo producer 活躍 + 檔存在。
3. **demote 既有測試**（test_demote_restores_complete_pre_promotion_set）pre/promoted 本就 full set，Fix 3 的生產非對稱由新 TestPromotedFullSetReRead 覆蓋。
4. boundary baseline 沿用 trading_true_metrics 的 10000 USDT 固定 baseline（per-engine 真 equity 未接）；E4/QC 可評估是否需真 equity。

## 已驗（Mac advisory）
- 真 TOML 解析：cost_model fee_bps=21.0/mult=1.3/floor=0.3/ttl=172800；funding_harvest active=['BTCUSDT']；grid_trading active=[]（無 allowed_symbols，正確 Reject）；boundary 讀 [limits] 12/7 + Mac 無 PG→1 fail-closed。
