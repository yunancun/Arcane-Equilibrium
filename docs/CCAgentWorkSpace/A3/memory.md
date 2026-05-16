# A3 Memory — 工作記憶

## 項目上下文（2026-04-24）

- 當前狀態：Live_Ready ⚠️（0 真實 live 流量，engine PID 884467）
- engine lib：1980 passed（+39 vs 2026-04-23 baseline）
- 系統模式：live_reserved（門控 5 項，Rust 可驗證 4 項）
- 主路徑：P0-2 21d demo → EDGE-DIAG-1 Phase 3 → Live（最早 W24 末 ~2026-05-23）

## 工作記憶

### 2026-04-24 GUI 完整審查發現

**Top 3 最關鍵問題**：
1. **Paper Tab 手動下單是 NO-OP**（tab-paper.html:148-162 + 231-241）— submitOrder/cancelOrder 硬編碼為 ocToast('已禁用')，UI 渲染但不發請求。違反 memory `feedback_no_dead_params.md`
2. **Live Tab 用 browser-native `confirm()` / `prompt()`**（tab-live.html:1059, :600）— Live 平倉/授權續期用原生彈窗，無 warning 樣式，Firefox 可禁用此 API
3. **Demo close-all silent-fail**（tab-demo.html:798-804）— openDemoCloseAllDialog() 觸發 `Cannot read properties of null` JS 錯誤，控制台報錯，modal 從未定義

**GUI 根路徑**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/`

**發現總數**：62 項（死/半死 endpoint 8 · 設計 18 · 反人類 15 · 可優化 16 · 無障礙 5）

**Memory 盤點對照**（`project_gui_write_paths_inventory.md`）：
- R (Rust IPC) 抽驗正確
- **新類別**：前端 JS 層假按鈕（非後端 fake-success）— Paper submitOrder
- **新類別**：silent-fail（模態框元素缺失）— Demo close-all

**改進 vs 2026-03-31**：
- ✅ Demo/Feed/Scanner 已從可點按鈕改為 status span
- ✅ Risk Tab P0/P1/P2 顏色不再誤導
- ✅ Live dashboard 從 placeholder 補全
- ⚠️ 新退步：Live Tab Trust Renewal 用 prompt()；API Key 混入 Settings Tab

### 常用檢查路徑（下次啟動免重複探索）

**所有 Tabs**（13 個 HTML + 5 個 JS）：
```
console.html / index.html / login.html（shell + 2 entry）
tab-system / tab-live / tab-demo / tab-paper / tab-strategy /
tab-risk / tab-ai / tab-learning / tab-governance / tab-monitoring /
tab-settings / tab-phase4（11 tabs）
```

**Python routes**（對應 onclick endpoints）：
- `paper_trading_routes.py` - `/api/v1/paper/*`
- `live_session_routes.py` - `/api/v1/live/*`
- `risk_routes.py` - `/api/v1/risk/*`（Rust IPC）
- `strategy_ai_routes.py` + `strategy_write_routes.py` - `/api/v1/strategy/*`
- `control_legacy_routes.py` - `/api/v1/control/*`, `/api/v1/system/scheduled-restart`
- `learning_legacy_routes.py` - `/api/v1/learning/*`
- `governance_routes.py` + `governance_extended_routes.py` - `/api/v1/governance/*`

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-03-31 | 首次 GUI 可用性評估（42 項） | `reports/2026-03-31--a3_gui_usability_report.md` |
| 2026-04-24 | 完整 GUI 審查（62 項 + Top 10） | `reports/2026-04-24--gui_comprehensive_audit.md` |
| 2026-05-16 | P1-PORTFOLIO-RESTING-EXPOSURE-1 對抗審 APPROVE 9/10（2 WARN advisory，leverage chain semantic drift + test coverage gap） | `reports/2026-05-16--p1_portfolio_resting_exposure_a3_adversarial_review.md` |
| 2026-05-16 | W-AUDIT-8a C1 v2 harness 對抗審 APPROVE-CONDITIONAL 7.5/10 — 2 CRITICAL (UTC midnight 00:00:30+ 延遲 24h bug + checkpoint write 非 atomic jq race) + 3 WARN (oneliner paste-safety + max-restart 語意歧義 + checkpoint JSON 膨脹) + 4 ADV，24h proof 前必修兩 CRITICAL | `reports/2026-05-16--w_audit_8a_c1_v2_harness_a3_adversarial_review.md` |
