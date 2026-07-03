# 7 條 structure/GUI/安全 static 測試紅診斷修復 — 2026-07-03

任務來源：E4 2026-07-03 盤點（`docs/CCAgentWorkSpace/E4/workspace/reports/2026-07-03--part2_post_approval_drift_gate_regression.md`），7 條 pre-existing red at clean HEAD，逐條考古歸因後修對的一側。

## 任務摘要

7 條中 **6 條歸因 B（測試 stale，生產側經審查演進）→ 更新測試到現狀**；**1 條歸因 C（#5，需真拆 3 個 Rust 引擎熱檔 ~1300 行）→ 不動手，scoped 建議交 PM**。零生產代碼改動；未削弱任何安全/治理斷言意圖，未放寬任何上限值。

## 逐條歸因與證據

| # | 測試 | 歸因 | 證據 commit | 修法 |
|---|---|---|---|---|
| 1 | `test_confirm_modal_a11y_static.py::test_common_confirm_modal_has_dialog_a11y_and_focus_trap` | **B** | `ae71575e8` (2026-05-19, P2-COMMON-JS-LOC split common.js 2198→4 檔) | confirm modal 整段（a11y 屬性+focus trap）移入 `common-modals.js`；測試改讀該檔，9 條斷言字串全數不變、逐一驗證仍在 |
| 2 | `test_prompt_modal_static.py::test_common_js_exposes_custom_prompt_modal` | **B** | 同 `ae71575e8` | `openPromptModal` 移入 `common-modals.js`；改讀取來源，4 條斷言不變 |
| 3 | `test_strategy_action_visual_isolation_static.py::test_common_css_defines_action_risk_zones` | **B** | 同 `ae71575e8` | 拆檔後內容分兩處：9 個風險分區 CSS marker 仍在 `common.js`（斷言不動）；`"paper-stop-all"` 預設表 / `typeof actionName === 'object'` / `confirmBtn.className` 應用邏輯在 `common-modals.js`（改讀 modals）。斷言字串全不變 |
| 4 | `test_strategy_action_visual_isolation_static.py::test_live_stop_emergency_and_close_actions_are_visually_separated` | **B** | `9bf4fd62d` (2026-05-19, P2-TAB-LIVE-JS-EXTRACT 抽 tab-live.html 內聯 script 2171→543 LOC) | 靜態危險分區標記留 `tab-live.html`；動態 row 平倉按鈕（`oc-row-close-action` @tab-live.js:814）與 `openConfirmModal({`/兩個 `confirmClass` 移入 `tab-live.js`。測試按歸屬拆雙來源；原生 `confirm(` 禁令**擴至兩檔都斷言**（強化非削弱；驗證兩檔現皆無 lowercase `confirm(`） |
| 5 | `test_event_consumer_split_static.py::test_event_consumer_hot_files_stay_split_under_limit` | **C** | 分檔基線 `3cff1005a` (2026-05-09)；其後 `a90ffc7b3`/`f5c175ab5`/`66f063ccb`/`feb18c520` (至 2026-06-25) 累積增長 | **不動手**。dispatch.rs 1108（超 308）、dispatch_tests.rs 1008（超 208）、loop_handlers.rs 1541（超 741），三檔全綠才過，總搬遷 ~1300 行引擎熱檔代碼，遠超 ~200 行最小拆分預算；且需 Linux cargo build+全 lib test，與 IMPL-A 髒檔（lib.rs/tick_pipeline）同倉在製。上限 800 未放寬 |
| 6 | `test_new_vuln_3_4_security_static.py::test_cookie_secure_auto_treats_https_proxy_hints_as_fail_closed` | **B**（非生產回歸） | `65e784376` (2026-05-27, OPS-1 wave2-3, P1-OPS-1-PROXY-HEADER-SPOOF-RISK；E2+A3+CC 三方審查通過)；測試 `cfadc339c` (2026-05-09) 早於此 | fail-closed 行為**沒有被改掉，而是升級**：proxy header 從無條件信任改為 `OPENCLAW_TRUST_PROXY_HEADERS=1` 顯式 opt-in（未 opt-in 時直連 8000 偽造 X-Forwarded-* 對安全判定零影響，`request.url.scheme` 為唯一真相；opt-in 後 HTTPS hint 一律標 Secure）。測試重寫為雙分支：未 opt-in 斷言 spoof 免疫（新增），opt-in 斷言原 4 條 hint 全保留。把生產改回無條件信任 = 撤銷已審查 P1 安全修復，不採 |
| 7 | `test_v072_feature_baseline_writer_static.py::test_writer_cli_defaults_to_dry_run_and_requires_apply_ack` | **B** | `19fa94fc4` (2026-05-14, 4b ML INSERT env gate) | 拒絕訊息由 `--apply requires --i-understand-this-modifies-db` 改寫為 `apply mode requires --i-understand-this-modifies-db or {FEATURE_BASELINE_APPLY_ENV}=1`（新增 `OPENCLAW_FEATURE_BASELINE_APPLY=1` 第二條顯式 ack 路徑）。fail-closed 意圖不變：`Mode::DryRun` 默認、無 ack 即拒、`--yes/--force` 自動 ack 旗標仍被拒（feature_baseline_writer.rs:118-122/138-141）。測試更新訊息並**加釘** env gate 常量與 rejected-flag 訊息兩條新斷言 |

## 修改清單（全部 tests/ 側，零生產檔）

1. `tests/structure/test_confirm_modal_a11y_static.py` — 讀 `common-modals.js`（+注釋記 ae71575e8）
2. `tests/structure/test_prompt_modal_static.py` — 讀 `common-modals.js`
3. `tests/structure/test_strategy_action_visual_isolation_static.py` — #3 拆 common.js/common-modals.js 雙來源；#4 拆 tab-live.html/tab-live.js 雙來源 + `confirm(` 禁令覆蓋兩檔
4. `tests/structure/test_new_vuln_3_4_security_static.py` — 主測試重寫為 OPS-1 契約雙分支；`test_cookie_secure_explicit_disable_still_overrides_auto` 補 `TRUST_PROXY_HEADERS=1` 讓「顯式 disable 覆蓋可信 hint」斷言真被行使（原本 trust 未設時第二條斷言 trivially true）
5. `tests/test_v072_feature_baseline_writer_static.py` — 更新拒絕訊息 + 加釘 env gate 常量與 --force 拒絕訊息

## 驗證

- 前：任務範圍 7 failed（full scope `tests/structure/ + tests/test_v072...` = **7 failed / 376 passed**）
- 後：`python3 -m pytest tests/structure/ tests/test_v072_feature_baseline_writer_static.py -q --import-mode=importlib` = **1 failed / 382 passed**；唯一紅 = #5（C 類，本任務裁定不動手）。無新紅
- 7 條目標 id 單獨跑：6 passed / 1 failed（#5）
- `py_compile` 5 個改動 py 檔 OK；`git diff --check` OK；未改任何 js/css/html/rust，故無需 node --check
- 硬約束遵守：未碰 standing_envelope 兩檔、rust/ 髒檔、memory/、TODO.md、cost_gate_learning_lane/；rust 考古僅用 git log/show 與唯讀 grep；不 commit

## #5 scoped 建議（交 PM 裁決，開獨立 PA ticket）

按既有 `loop_exchange.rs` 先例（子檔 + `pub(super) use super::X::fn;` 相容 re-export，mod.rs 掛 `mod`）：

- `dispatch.rs` 1108→~790：抽 retcode 分類簇（`classify_dispatch_error`/`classify_business_retcode`/`noop_is_*`/`close_dup_is_idempotent_success`，約 L210-525 ~315 行）成 `dispatch_retcode.rs`，一刀達標
- `dispatch_tests.rs` 1008→<800：對應 retcode 測試搬 `dispatch_retcode_tests.rs`（沿用既有 `#[path = "..."]` include 模式）
- `loop_handlers.rs` 1541→<800：需兩刀 — `handle_pipeline_command`（L659-886 ~228 行）抽 `loop_pipeline_command.rs` + `handle_tick_event`（L907-EOF ~634 行）抽 `loop_tick.rs`
- 驗收要求：Linux `cargo build --release` + 全 lib test 基線比對；建議排在 IMPL-A（tick_pipeline/lib.rs 髒檔）merge 之後避免交錯

## 不確定之處

- 並行 session 同期在改 `tests/structure/test_stock_etf_*_split_static.py` 與 `tests/test_spike_cross_lang_rust_binding.py`（mtime 07-03 02:38-02:40，非本人改動，按多 session 協議未碰）；本任務 5 檔與其零重疊，全套 suite 綠含彼側
- #6 的姿態選擇（信任 gate > 無條件 hint 信任）是複述 OPS-1 已審查決策而非本人新裁；若 operator 認為 TLS 反代部署漏設 `OPENCLAW_TRUST_PROXY_HEADERS=1` 的殘餘風險值得再議，屬 PM/E3 層重開，不在本 ticket

## Operator/PM 下一步

1. E2 審查本 5 檔測試側改動 → E4 回歸
2. #5 裁決：是否開 PA ticket 按上述三刀拆分（等 IMPL-A merge 後）
