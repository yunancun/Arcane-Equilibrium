# E1 報告 — [38] grid_trading_lifecycle_drift healthcheck 落地

**日期**：2026-04-29
**任務**：把 MIT 設計的 healthcheck [38] 落到 `passive_wait_healthcheck/checks_execution.py`，補 TODO 被動等待條目。三 drift 指標（lifetime ratio / fee burn / re-entry rate）+ V017 entry_context_id JOIN 配對 + fail-soft（DB unreachable / 0 row 不 FAIL）。
**完成狀態**：完成，待 E2 審查 + E4 trade-core regression。
**詳細報告**：`srv/.claude_reports/20260429_193847_e1_grid_lifecycle_healthcheck_38_landing.md`

---

## 修改清單（簡）

| 檔案 | 動作 | LOC |
|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_execution.py` | 加 9 threshold 常量 + `check_grid_trading_lifecycle_drift` + 雙語 banner | 648 → 951 |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | import + `__all__` 條目 | 137 → 148 |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | cursor block 註冊 + `_RUNNER_DESCRIPTION` + `main()` docstring inventory | 552 → 572 |
| `TODO.md` | 背景線程表 + Wave 3 被動等待時間表 | 686 → 701 |

## 驗收（Mac dev）

- `python3 -m py_compile` 3 modified files 全綠
- 39 check 函數全 importable（[1]-[37] 0 regression + [38] 新增）
- 10-scenario offline mock smoke：missing-table WARN / demo n=0 PASS-skip / live n<5 PASS-skip / healthy PASS / lifetime WARN 0.4 / lifetime FAIL 0.2 / fee_burn FAIL 2.0 / re-entry FAIL 0.75 / re-entry delta WARN / PG error fail-soft → **全 10 通過**
- 9 threshold constants 與 spec 完全一致

**未在 trade-core 跑首次 cron**：operator 政策禁 commit + 禁 scp 到 /tmp，需 PM 統一 commit + push 後驗。

## 邊界遵守

- 0 改 trading 業務代碼
- 0 改 SQL schema / 0 新 migration
- 0 改 risk_config / strategy_params / Rust / GUI
- 0 改 §四 硬邊界
- 0 hardcoded `/home/ncyu` `/Users/...` 路徑
- 純 SELECT-only DB 查詢

## 設計亮點

- **MIT 原版 f-string 嵌套 bug 預修**：`f"{x:.2f if x is not None else 0:.2f}"` Python 3.12 不接受；落地時 pre-format 為 `_str` 變數
- **多層 fail-soft**：`cur.connection.rollback()` → `to_regclass` 存在性 → aggregate 查詢 try/except → `n < 5` PASS-skip → `fee_burn_demo=0` 防 None div
- **配對策略**：V017 `trading.fills.entry_context_id` 反向 JOIN + `row_number() = 1` 取 partial_tp 首次 close
- **3 indicator 嚴重度聚合**：每 indicator 獨立 push `severities`，max severity → final verdict；FAIL message 順帶帶 WARN suffix

## 不確定點

詳見 `.claude_reports/...` §5。摘要：
- cron 第一次 verdict 預期 PASS 或 WARN（不預期 FAIL）；FAIL = 真實 grid 失控
- partial_tp 取首次 close 是否最具代表（vs last close / max realized_pnl close）
- 未實測 EXPLAIN ANALYZE，建議 E4 trade-core 跑一次釘 worst case

## E2 / E4 必驗

- E2：SQL 安全 / cursor lifecycle / 雙語 / cross-platform / §九 line cap
- E4：trade-core EXPLAIN ANALYZE 兩個 query / 連 3 次 cron verify / regression [1]-[37]
