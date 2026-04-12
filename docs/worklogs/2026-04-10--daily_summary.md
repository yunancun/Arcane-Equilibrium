# 2026-04-10 Daily Summary

## 完成項目 / Completed

### ML Pipeline Remediation（commit `7178059`）
- S0-S3/S5 全部可執行項完成（DB writer 驗證、PG 連接、ML views、feature 管線）
- S4（Teacher-Student/LinUCB）和 S6（Calibration/ONNX）需引擎數據累積，後續工作
- Python ml_training 135 passed

### Signal Diamond Phase 1-4 + Fix Round
- V015 Migration：8 交易表加 `engine_mode` 列
- Rust DB Writers 加 `engine_mode` 寫入
- ModeState per-mode 狀態管理 + IPC `set_trading_mode()` 雙向 swap
- 9 gaps 全修：AddMode/SwitchMode IPC、Python mode-aware 參數化
- +5 Rust tests

### 大量 Live/Demo GUI 修復（commits `326a191` → `b4b68c7`）
- 平倉按鈕（per-symbol + 全部平倉）for live/demo/paper
- Sidebar `refreshSidebar()` 改用 live/session/status
- SM-1 治理授權統一（max_position_usd 從 Rust RiskConfig 讀取）
- DEAD-PY-2：~4500 行 Python 死代碼清除（bridge/strategies/ProtectiveOrderManager/交易方法）
- DEAD-PY-3：~23k 行 + ~151 文件清理

### Phase 6 Reconciler 自動降級（commit `a83d73a`）
- 6-RC-1~5,7,8,9,10 完成：漂移→escalation→hybrid 恢復
- +27 tests，872 engine lib + 365 core pass

### W19+W20 安全與治理（commit `a83d73a`）
- G-3 IPC HMAC-SHA256 認證 + G-5 Rate Limiting
- OC-3/6-RC-6 Reconciler 告警
- SEC-04/06/13 E3 深度審查 PASS
- 6-01~03 漸進放權管線

## 測試基準線 / Test Baseline
- Rust engine lib: 879 + core 365
- Python: 2792 passed

## 決策 / Decisions
- Signal Diamond 設計：共享市場數據 + per-mode intents/fills/positions
- Python 層完全無交易邏輯（DEAD-PY-2 後僅 API 橋接 + GUI 路由 + 工具）
