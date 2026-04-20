---
name: Rust migration complete (R-07 PASS)
description: Rust 引擎完全接管熱路徑，R-07 Go/No-Go 7/7 PASS，Python V2 已停用，唯一執行引擎
type: project
---

Rust 遷移於 2026-04-04 全部完成並通過 Go/No-Go。

**Why:** R-00~R-07 開發完成 → 7 天 canary → 7/7 PASS → R-CUT 全部執行（RC-01~RC-15 + IPC-01~06）→ Python PaperTradingEngine 完全停用（ENGINE=None）。Rust 為唯一 tick 處理引擎、唯一 Bybit WS 連接，零重複系統。

**How to apply:**
- 不要再提「canary mode」或「Go/No-Go pending」— 全部已通過
- 不要再修 Python `paper_trading_engine.py` / V2 策略，那條路死了
- 新策略/風控/模型一律寫在 `rust/openclaw_engine` 或 `rust/openclaw_core`
- Python 端只剩 control_api（FastAPI）+ ml_training + GUI，是 thin layer
- 重啟用 `bash helper_scripts/restart_all.sh`

**Key locations:**
- Rust: `rust/openclaw_core/` + `rust/openclaw_engine/` + `rust/openclaw_types/`
- PyO3 橋接：`rust/openclaw_pyo3/`（39 個方法暴露給 Python）
- Test baseline 隨 phase 變動，每次接手讀 TODO.md 頂部
