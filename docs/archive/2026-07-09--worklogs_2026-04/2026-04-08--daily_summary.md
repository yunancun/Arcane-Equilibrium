---
date: 2026-04-08
type: daily-summary
session_continuity: 接 4/7 斷網 session（已整合原 session_resume_notes 要點）
scope: ARCH-RC1 1C-3（全部）+ 1C-3-F + 1C-4 wrap + GUI fake-success Wave 1/2 + post-1C-4 cleanup + DEAD-PY-1 plan
---

# 2026-04-08 Daily Summary — ARCH-RC1 1C-3 / 1C-3-F / 1C-4 全量 SHIPPED

## 完成項目 / Completed

### 1. Session 接手 + state 撈回（從 4/7 斷網 transcript）
- 撈回 6 個關鍵點：測試基準線（725→740，engine lib 731→740 +9，Python +2）/ 三層防護架構 / operator 風控能力表 / cooldown known-limit / 1C-3-D 真實範圍 / 接手決策
- TODO.md 同步：基準線更新 / 1C-3-D scope 補全 / 1C-4 加 cooldown PG 持久化
- **決策**：走 (b) 路徑 — 先 E2 review 三個未審 commit 再開 1C-3-D（符合 `feedback_workflow_e2_e4_mandatory`）

### 2. E2 review 三個未審 commit
- Sub-agent 產出 `docs/audits/2026-04-08--e2_review_1c3_bbc.md`
- 結論：1C-3-B (`8447fbf`) APPROVED_WITH_NITS · 1C-3-C (`c6fcd13`) APPROVED_WITH_NITS · 1C-3-B-2 (`9f46b06`) CHANGES_REQUIRED
- 必修：M-1 (test gap) · M-2 (audit hole) · N-5 (payload shape)

### 3. 1C-3-D M-1 fix — `f8772c0`
- `event_consumer/tests.rs` +220 行；8 個 real guard tests via `handle_paper_command` + `tokio::sync::oneshot::channel()` + `rx.blocking_recv()`
- 之前 governor manual override 守衛只有 path-level coverage
- engine lib 740 → 748

### 4. 1C-3-D M-2 + N-5 fix — `a1cf772`
- `spawn_governor_audit_row` 簽名重構：5-positional → `(audit_pool, event_type, payload: serde_json::Value)`
- Rejected governor overrides 也寫 V014（new event types `governor_*_rejected`，payload 含 `result` + `error`）

### 5. 1C-3-D 主體 — `144f46f`（approach A：aggressive cull）
- `risk_manager.py` **1633 → 53 行**（-97%）
  - 僅保留 `REGIME_TIME_MULTIPLIERS` 常量 + `RiskManager(RiskViewClient)` 薄子類
  - deprecated 行為走 RiskViewClient 內建 no-op stub
- `paper_trading_wiring.py` 移除三個 RiskManager 注入點
- 刪除 9 檔 ~6900 行純 Python 風控/H0/Engine 測試（邏輯已 100% 在 Rust 748 tests 覆蓋）
- conftest 移除 4 個 risk fixtures；`test_portfolio_risk_control_injected` 重寫為驗證 wiring singleton
- **+46 / -7882 = 淨 -7836** · 14 files
- **User 決策**：直接確認「A」—「乾淨優於 backwards-compat hack」，拒絕 `**_legacy_kwargs` 方案

### 6. 1C-3-E F-mini 收尾 — `d8fb7f2`
- `bridge_core.py:294` 死引用清除（`_engine.risk_manager._price_tracker`）
- 6 個 1C-3-C skipped TestRiskRoutes 隨 1C-3-D `test_risk_manager.py` 整檔 cull 一起消失
- 三小修：`paper_trading_routes.py` -4 dead imports · `risk_routes.py::unhalt_session` -deprecated mutate block · `paper_trading_wiring.py::_h0_db_probe` PAPER_STORE.read → os.stat

### 7. GUI Fake-Success Wave 1 — `5a824d8`
- **Task #1（P0 盤點）**：16 route 模組 · 93 POST/PATCH endpoints 分類（**R** Rust-IPC 11 / **PR** 混合 3 / **P** Python-only ~70 含 ~12 P0「該到 Rust」/ **D** dead 8）
- **Task #3（risk 寫後驗證 + 顯示刷新）**：
  - `tab-risk.html` 翻轉 `rStop ?? gc` → `gc ?? rStop`（fresh ConfigStore IPC 優先於滯後 snapshot）
  - `risk_view_client._patch()` 加寫後驗證：snapshot prev_version → patch → refresh → version 沒前進則 raise → bubble 5xx
- **Task #4（雙引擎 stop 按鈕）**：`paper_trading_routes.py` 加模組級 sticky `_USER_STOPPED` 標誌（Rust 只有 Pause/Resume 無 native Stop），status API 見 paused + sticky → 報 "stopped"
- **Task #2（Mode control）重新歸類**：深挖確認 Rust `TradingMode` 是**冷參數**、Python `global_execution_mode_switch` 才是 operator 授權平面，原「fake success」分類錯誤，**架構本來就對**；實際症狀待用戶實測

### 8. GUI Fake-Success Wave 2 + P1 Per-Trade Risk Rust 接線
- **Risk tab fake-success 全套修復**：`tab-risk.html:798` 少讀一層 `cfg = (d.data && d.data.config) || d.data || {}`；`consecutive_loss_cooldown_minutes` Pydantic float→int（Rust u32 序列化帶 `.0` 失敗）
- **P1 Per-Trade Risk → Rust 架構級修復**（原 `DEFAULT_P1_RISK_PCT = 0.02` 寫死）：
  - `risk_config.rs::GlobalLimits` 加 `per_trade_risk_pct` + default 0.02 + validate [0.0001, 0.20]
  - `intent_processor.rs::update_risk_config()` 接 `set_p1_risk_pct()` tick-level hot-reload
  - `risk_view_client._GLOBAL_TO_RUST` 加 mapping + 單位換算（value > 1 → /100）
  - `risk_routes.py` flat builder `p1_risk_pct = limits.per_trade_risk_pct * 100`
  - `tab-risk.html` 砍掉 localStorage hack，改讀 `gc.p1_risk_pct`
- **驗證端到端**：GUI POST 8% → Python /100 → Rust 0.08 → tick hot-reload → notional $19.52 → $77（4× 提升符合 2%→8%）
- **發現結構性瓶頸（非 bug）**：cost_gate EV/fee 與 size 無關（qty 約掉），當前 BTC 低波動 EV/fee=0.22× 不可能過 k_small=3.0 閾值，結構上調 P1 無效

### 9. 1C-3-F 徹底退場 Python paper engine — `accf625` / `8ff93e0` / `de1ec69`
**F-a — Rust submit_paper_order IPC RPC**（`accf625`）：
- `tick_pipeline.rs::PaperSessionCommand::SubmitOrder` variant + `submit_external_order()` (~150 行)，走 IntentProcessor 全 gate（governance/Guardian/Kelly/P1/cost gate），Order ID `ext-{symbol}-{ts_ms}`
- `event_consumer/handlers.rs` SubmitOrder 分支 · `ipc_server.rs` `submit_paper_order` JSON-RPC + 5s timeout
- `event_consumer/tests.rs` 4 e2e tests（happy/paused/no_price/invalid_side）+ 1C-3-D 4 個 guard tests 統一 `authorize()` helper
- engine lib 748 → **752**

**F-b — shadow_decision_builder rewire**（`8ff93e0`）：
- `ipc_client.py::submit_paper_order` async wrapper
- `shadow_decision_builder.py` 砍 `paper_trading_engine` import，常量內聯，`ShadowDecisionConsumer.__init__` 改吃 `EngineIPCClient`，`consume()` 改 async
- `layer2_engine.py:669` `await self._shadow_consumer.consume(...)`
- `layer2_routes.py::_build_shadow_consumer()` helper

**F-c/d/e — Python 紙盤引擎徹底刪除**（`de1ec69`）：
- `app/paper_trading_engine.py` **2248 行** 全刪
- 13 個 paper-engine-specific test 文件刪除 + conftest paper engine fixtures 整塊刪
- `PAPER_STORE = None` / `ENGINE = None` 維持 stub（3 個生產消費者全部已 `if ENGINE is not None` 短路）
- pytest 回歸：2944 → **2694 passed / 21 pre-existing fail / 0 regression**（-250 來自被刪 13 檔 250 個 case）

### 10. 1C-4 wrap — `f882473`
- Position Reconciler 基礎 · NewsPipeline Rust pipeline 完整（scheduler spawn 留 A2）· Governor cooldown PG 持久化落地 · 熱重載 e2e 驗收 · E2/E4/QA 全綠
- engine lib 752 → **767**

### 11. Post-1C-4 cleanup — `8554779` / `967f420` / `d10becc`
- **`8554779` 1C-3-D 留尾**：RiskViewClient 9 個 deprecated stub 方法 + helper + test 刪除；strategy_wiring `_RISK_MGR_REF.set_h0_gate` 注入區塊刪除；17 個 `.smbdelete*` Samba ghost 檔清除（~700KB）
- **`967f420` DEAD-PY-1 plan**：sub-agent 掃描 ~42 候選項 → 4-phase plan（Phase 1 SAFE-DELETE ~2h / Phase 2 CHECK-ROUTES ~1h / Phase 3 STALE-COMMENT ~3h / Phase 4 GUI ~1h，risk LOW，非阻塞）
- **`d10becc` 主檔瘦身**：CLAUDE.md 363→348 / TODO.md 237→218 / README.md 368→301 = **-139 行 (-14%)**；narrative 遷至 `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

### 12. 用戶 3 個確認問題驗證
1. **止損引擎** ✅ 唯一 Rust：`openclaw_core/src/stop_manager` + `paper_state.check_stops` + `tick_pipeline` 消費
2. **學習引擎** ⚠️ 部分接上：LearningConfig 熱重載 + IPC patch 可寫，Phase 4.1 Claude Teacher consumer loop 已 spawn，但 LearningConfig → 學習動作閉環尚未連通
3. **新聞引擎** ⚠️ 接好沒開動：`NewsPipeline::run_once` 完整實現 + `NewsContextSnapshot` + `GuardianHaltCheckImpl` wire 進 guardian/governance，**缺 60s scheduler spawn**（A2 任務，等 4-09 router 決策）

## 測試基準線 / Test Baseline

| 層 | 開始 | 結束 | Δ |
|---|---|---|---|
| Rust engine lib | 740 | **767** | +27 |
| Rust core | 387 | 387 | 0 |
| Rust types | 27 | 27 | 0 |
| Rust ml_training | 35 | 35 | 0 |
| Python control_api | 2944 passed / 22 fail | **2694 passed / 21 pre-existing fail** | -250 test (刪檔) · -1 baseline fail |

22→21 pre-existing failures：19× `test_grafana_data_writer` mock 環境 + `test_paper_trading.py::test_session_start_via_api` 401（已隨 paper_trading_engine 刪除消失）+ `test_is_stale_initially`。全部已 baseline stash 對照驗證 byte-for-byte 一致。

## 關鍵決策 / Decisions

1. **接手策略走 (b)**：先 E2 review 三個未審 commit，再開 1C-3-D（避免在未審代碼上堆大改）
2. **1C-3-D approach A**：aggressive cull 9 個測試檔（Rust 748+ tests 已 100% 覆蓋風控邏輯，Python 測試只是死代碼）
3. **乾淨優於 backwards-compat hack**：用薄子類而非 `**_legacy_kwargs` kwargs-swallowing
4. **P1 per_trade_risk_pct 到 Rust**：GUI localStorage hack → Rust ConfigStore 權威，tick-level hot-reload
5. **Task #2 Mode control 重新歸類**：Rust `TradingMode` 冷參數、Python `global_execution_mode_switch` 是 operator 授權平面，非 fake-success，架構本來就對
6. **PAPER_STORE / ENGINE 留 None stub**：3 個生產消費者已 `if ENGINE is not None` 短路，物理刪除反增改動面

## 1C-3 風控收編軌跡（最終）

```
1A 前：      Python RiskManager 1633 + 6 套 Rust 並行 = 7 套
1A：         刪 3 套確認死碼
1C-1：       1 Rust Config 權威 + Python RiskManager 1633（待空殼化）
1C-2-F：     1 Config 權威 + 5 engines 同步熱重載
1C-3-D：     1 Rust ConfigStore 權威 + 53 行 Python RiskViewClient shim
1C-3-E F-mini：邊角死代碼清除（bridge_core / routes imports / PAPER_STORE.mutate / H0 probe）
1C-3-F：     Python paper_trading_engine 2248 行徹底退場 → Rust openclaw_engine 三模式唯一引擎
1C-4：       Reconciler + News + Governor cooldown PG 持久化 + e2e
```

## 三層防護架構（1C-3-B-2，operator manual governor override 安全邊界）

1. **IPC layer** (`handlers.rs`)：`reason_code` 白名單 `{false_positive, root_cause_fixed, accept_risk}` · 單步限制 · 24h cooldown（per-reason）· CircuitBreaker & ManualReview 從 IPC 不可解鎖
2. **SM layer** (`risk_gov.rs`)：`lookup_rule` transition table 校驗 · `min_hold_time_ms` 5 min
3. **Audit layer** (`ipc_server.rs`)：V014 `engine_events` 寫 `{from_tier, to_tier, reason_code, notes}`

## Operator 風控能力表

```
clear_consecutive_losses     — 隨時，無風險（per-symbol counter 重置）
force_governor_tier_tighter  — 隨時往更嚴方向，單步、無冷卻
force_governor_tier_looser   — 帶 reason_code、24h cooldown、單步、CB/MR 鎖死
```

## Known limitation（已在 1C-4 解決）
- ~~Governor tier override cooldown 當前 in-memory only，引擎重啟重置~~ → 1C-4 `f882473` PG 持久化落地

## Commits（本日 11 個）

| Hash | 摘要 |
|---|---|
| `f8772c0` | test(engine): ARCH-RC1 1C-3-D M-1 — real guard tests |
| `a1cf772` | feat(ipc): ARCH-RC1 1C-3-D M-2 + N-5 — audit rejected overrides |
| `144f46f` | feat(python): ARCH-RC1 1C-3-D — RiskManager 收編為 53 行 shim |
| `d8fb7f2` | fix(py): 1C-3-E F-mini — dead references + imports cleanup |
| `5a824d8` | fix(gui): kill 2 fake-success bugs — risk display + dual-engine stop |
| `3688225` | fix(risk-gui): wire GUI stop-loss fields to Rust IPC correctly |
| `36d2533` | fix(strategy): wire activate/pause/stop to Rust set_strategy_active IPC |
| `accf625` | feat(ipc): 1C-3-F F-a — Rust submit_paper_order RPC |
| `8ff93e0` | refactor(py): 1C-3-F F-b — shadow_decision_builder IPC rewire |
| `de1ec69` | refactor(py): 1C-3-F F-c/d/e — delete paper_trading_engine.py (2248) + 13 test files |
| `f882473` | feat(engine): 1C-4 wrap — Reconciler + News + Governor PG + e2e |
| `8554779` | cleanup(py): 1C-3-D tail — RiskViewClient stubs + Samba ghost files |
| `967f420` | docs(todo): DEAD-PY-1 4-phase plan |
| `d10becc` | docs(main): trim CLAUDE/TODO/README -139 lines + narrative archive |

## 參考 / References
- 1A→1C-4 narrative archive：`docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`（被 CLAUDE.md §三指向）
- 1C-3/1C-4 narrative archive：`docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
