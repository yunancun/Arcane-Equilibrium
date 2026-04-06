# helper_scripts/ — 腳本索引 (Script Index)

本目錄存放 OpenClaw 系統的維護、啟動、CI 輔助腳本。

---

## 腳本列表 (Scripts)

- `restart_all.sh` — 一鍵重啟 Rust 引擎 + API server（支援 `--engine-only` / `--api-only` 選項）
- `cron_daily_report.sh` — 每日自動採集 Paper Trading 指標並推送 Telegram 報告（Cron UTC 0:00 觸發）
- `cron_observer_cycle.sh` — 每 5 分鐘執行完整 Observer 循環並自動橋接到 runtime snapshot
- `start_paper_trading.sh` — API server 就緒後自動啟動 Paper Trading（可由 systemd ExecStartPost 或 cron @reboot 呼叫）
- `schema_diff.py` — CI 類型一致性檢查：比對 Python shared_types 與 Rust golden JSON schema，防止 Python/Rust 類型漂移
- `golden_dataset_gen.py` — 生成 Rust↔Python 指標交叉驗證黃金數據集（確定性合成 OHLCV + 13 個指標 Python 參考值，輸出 JSON）
