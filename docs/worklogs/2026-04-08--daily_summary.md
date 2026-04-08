---
date: 2026-04-08
type: daily-summary
session_continuity: 接 4/7 斷網 session（worklog `2026-04-08--session_resume_notes.md`）
---

# 4/8 Daily Summary — ARCH-RC1 1C-3 全部 SHIPPED

## 完成項

### 1. Session 接手 + state 撈回
- 從 4/7 斷網 jsonl transcript 撈回 6 個關鍵點（測試基準線 / 三層防護 / operator 風控能力表 / cooldown known-limit / 1C-3-D 真實範圍 / 接手決策）
- 寫入 `docs/worklogs/2026-04-08--session_resume_notes.md`
- TODO.md 同步：基準線 725→740 / 1C-3-D scope 補全 / 1C-4 加 cooldown PG 持久化

### 2. E2 review 三個未審 commit
- E2 sub-agent 後台執行，產出 `docs/audits/2026-04-08--e2_review_1c3_bbc.md`
- 結論：1C-3-B (8447fbf) APPROVED_WITH_NITS / 1C-3-C (c6fcd13) APPROVED_WITH_NITS / 1C-3-B-2 (9f46b06) CHANGES_REQUIRED
- 必修：M-1 (test gap) · M-2 (audit hole) · N-5 (payload shape)

### 3. 1C-3-D M-1 fix — `f8772c0`
- `event_consumer/tests.rs` +220 行
- 8 個 real guard tests via `handle_paper_command` + `tokio::sync::oneshot::channel()` + `rx.blocking_recv()`
- 之前 governor manual override 守衛只有 path-level coverage
- engine lib 740 → 748

### 4. 1C-3-D M-2 + N-5 fix — `a1cf772`
- `spawn_governor_audit_row` 簽名重構：5-positional → `(audit_pool, event_type, payload: serde_json::Value)`
- Rejected governor overrides 也寫 V014（new event types `governor_*_rejected`，payload 含 `result` + `error`）
- engine 748 持續綠燈

### 5. 1C-3-D 主體 — `144f46f` (approach A: aggressive cull)
- `risk_manager.py` **1633 → 53 行** (-97%)
  - 只剩 `REGIME_TIME_MULTIPLIERS` 常量 + `RiskManager(RiskViewClient)` 薄子類
  - 子類建構不需 ipc_client，所有 deprecated 行為走 RiskViewClient 內建 no-op stub
- `paper_trading_wiring.py` 移除三個 RiskManager 注入點
- 刪除 9 檔 ~6900 行純 Python 風控/H0/Engine 測試
- conftest 移除 4 個 risk fixtures
- `test_integration_phase2::test_portfolio_risk_control_injected` 重寫為驗證 wiring singleton
- **+46 / -7882 = 淨 -7836** · 14 files

### 6. 文檔同步
- CLAUDE.md §三 加 1C-3 SHIPPED 大條目 · §十一 one-liner 改寫
- TODO.md 1C-3-D 全部標記完成 · 1C-3-E 留尾條目補上
- CLAUDE_CHANGELOG.md 加 1C-3 全 session 條目（含風控收編軌跡終局）

## 關鍵決策

1. **接手策略**：走 (b) 路徑 — 先 E2 review 三個未審 commit，再開 1C-3-D（避免在未審代碼上堆大改）。符合 `feedback_workflow_e2_e4_mandatory`。
2. **Approach A vs B**：1C-3-D 主體確認走 approach A（aggressive cull 9 個測試檔），而非 approach B（保留 stub 兼容層）。User 直接確認「A」。原因：Rust 748 tests 已 100% 覆蓋風控邏輯，保留 Python 測試只是死代碼。
3. **「乾淨優於 backwards-compat hack」**：User 早先拒絕 `**_legacy_kwargs` 方案（"我希望你做的更乾淨一點"），所以用 `RiskManager(RiskViewClient)` 簡單薄子類而非 kwargs-swallowing。

## 測試變化

| 層 | Before | After | Δ |
|---|---|---|---|
| Rust engine lib | 740 | **748** | +8 (M-1) |
| Rust core | 387 | 387 | 0 |
| Rust types | 27 | 27 | 0 |
| Python control_api | ~2944 (delta noise from 17 risk module tests deleted/added) | **2944 passed / 22 pre-existing fail / 1 skipped** | 0 regression caused |

22 pre-existing failures 已用 `git stash` 對照驗證 byte-for-byte 與 baseline 一致。

## 風控收編軌跡終局

```
1A 前：     7 套並行（Python RiskManager 1633 + 6 套 Rust）
1A 後：     4 套（刪 3 套確認死碼）
1C-1 後：   1 Rust Config 權威 + Python RiskManager 1633（待空殼化）
1C-2-F 後： 1 Config 權威 + 5 engines 同步熱重載
1C-3-D：    1 Rust ConfigStore 權威 + 53 行 Python RiskViewClient shim
```

## 遺留問題（下一個 session 起點 = 1C-3-E）

1. `paper_trading_engine.py` ~15 個 `engine.risk_manager.X` 死路徑（ENGINE = None since RC-10 的 disabled engine 自身清理）
2. `bridge_core.py:294` `self._engine.risk_manager._price_tracker` 死引用
3. 6 個 1C-3-C 留下的 skipped `TestRiskRoutes` 重寫
4. `PAPER_STORE.mutate` 拆分：session_halted 不再 Python 並行寫，從 Rust snapshot 派生
5. 評估是否進一步刪 `RiskManager` 子類符號，讓 paper_trading_wiring 直接 import RiskViewClient
6. **1C-4 必做**：Governor tier override cooldown PG 持久化（live 前必須，目前 in-memory，引擎重啟即重置）

## 接手指令（下一個 session）

1. 讀 CLAUDE.md §三 確認 1C-3 全部 SHIPPED 狀態
2. 讀 TODO.md 找第一個 `[ ]` — 應為 **1C-3-E 留尾收尾** 或 **1C-4 收尾**
3. Rust workspace 跑 `cargo test --workspace --exclude openclaw_pyo3` 確認 748 仍綠（pyo3 link 環境問題已知，跳過）
4. Python 跑 `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ -q` 應為 2944 passed / 22 failed (與 baseline 一致)
5. 若選 1C-3-E：先 grep `engine.risk_manager` 確認死路徑範圍，再做 paper_trading_engine 清理；6 個 TestRiskRoutes 重寫可參考 RiskViewClient 的 IPC mock 模式
6. 若選 1C-4：優先 Governor tier override cooldown PG 持久化（V014 已有 schema，可加 V015 cooldown_state 表）

## Commits

- `f8772c0` test(engine): ARCH-RC1 1C-3-D M-1 — real guard tests for operator governor override
- `a1cf772` feat(ipc): ARCH-RC1 1C-3-D M-2 + N-5 — audit rejected governor overrides, fix payload
- `144f46f` feat(python): ARCH-RC1 1C-3-D — RiskManager 收編為 53 行 RiskViewClient shim
