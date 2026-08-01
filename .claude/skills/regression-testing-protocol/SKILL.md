---
name: regression-testing-protocol
description: E4 agent 主用：跑回歸/驗收測試、報告測試計數、新增或改動測試檔、或測試結果與基準線有出入時必讀。
allowed-tools: Read, Grep, Glob, Bash
---

# Regression Testing Protocol（回歸測試手冊）

> Authority 使用 `.codex/agent_registry_v1.json` typed matrix。測試證明
> implementation behavior；runtime observation、active state、normative policy
> 分屬不同 class，不能用某一類結果覆蓋另一類 denial。
> 以內建知識為底：測試類型學（unit/integration/property/concurrency）、mock 原理、pytest/cargo 通識不在本檔重述；本檔只列本專案的偏離、教訓與 SSOT 指針。

`SRV`=倉庫根（Mac: `~/Projects/TradeBot/srv`；Linux: `~/BybitOpenClaw/srv`）。

## 何時觸發

- Source Implementation 經獨立 E2 review 後，E4 負責 relevant regression evidence
- 「跑測試」「驗證 fix 沒破壞其他」「測試數有沒有回退」
- 新功能落地前的 baseline 確認；Rust `cargo test` + Python pytest 雙引擎同步

## ★ 核心原則

1. **基準線不可回退**：passed 數 < baseline = BLOCKER
2. **不允許刪測試使測試通過**：發現失敗 → 修代碼，不修測試
3. **Mock 只 stub IO 邊界**（HTTP / PG / fs / 時間 / 隨機），不 stub 業務邏輯、計算函數、IPC 協議邏輯
4. 跨語言浮點 1e-4 容差：Python ↔ Rust 同輸入差異 ≥ 1e-4 = bug（ATR / BB / Sharpe 必驗）
5. **重跑按風險**：critical、已失敗、known-flaky、release gate 才要求第二遍；其他 exact signature 綠證據不做儀式性重跑

## 1. 當前測試基準線（動態，每次審計前重跑命令拿，不信寫死數字）

| 引擎 | 命令 | 解讀 |
|---|---|---|
| Python pytest | `cd $SRV && python3 -m pytest tests/ -q --tb=short \| tail -5` | passed / failed 數 |
| Rust engine lib | `cd $SRV/rust && cargo test --release -p openclaw_engine --lib 2>&1 \| tail -5` | passed / failed 數 |
| Rust integration | `cd $SRV/rust && OPENCLAW_TEST_PG="..." cargo test --release -p openclaw_engine 2>&1 \| tail -5` | 需 PG |

部分 test 路徑要求從 `program_code/exchange_connectors/bybit_connector/control_api_v1/` 內跑 pytest。

**baseline 規則**：
- 任何 commit 不可降低 passed 數、不可增加 pre-existing failed 數
- Baseline 來自 exact source/diff/toolchain/env signature 的前後結果；不以 E4 memory 的舊 passed count 當當前真相

**Mac dev-only 注意**（唯一正本段）：
- 部分整合測試需 external/runtime surface 時，source suite 只證明 source；另由正確 Adapter/OPS/QA 取得 runtime evidence
- Delegated E4 的 Rust build/test/check 全在 Mac；Linux cargo 一律禁止

## 2. 工作流

1. 讀 acceptance、E2 verdict、diff、direct callers 與 test impact。
2. 先跑最小能 falsify change 的 focused test。
3. 依 dependency/reach 擴至 relevant module/cross-language/regression suite。
4. 新增缺少的邊界、並發、安全或 intent test；不寫 business code。
5. 審 mock、浮點、SLA、PG/runtime evidence scope 是否誠實。
6. critical/failed/known-flaky/release gate 才做第二遍或 independent recheck。
7. 產 content-addressed evidence capsule，標 EXECUTED/REUSED/SKIPPED/FAILED。
8. 回 immutable `role_fragment_v1` with `payload_kind=test_fragment_v1`；不寫 E4 memory/report。

## 3. 測試覆蓋 checklist（專案 delta，壓縮版）

- **Unit**：每個新 E1 改動有對應 unit test；邊界值 + 正常路徑至少各 1；修復安全問題需有「修復後攻擊路徑測試通過」
- **Integration**：跨模塊調用鏈（Strategist → IPC → Rust engine）；連 PG 測試（含 hypertable / migration）；Bybit demo / paper API 整合（Mac 端 dev_disabled 跳過，見 §1）
- **Property-based（proptest）**：Rust 狀態機轉換窮舉；serde round-trip；IPC schema 隨機 fuzzing
- **Concurrency**：asyncio 多 task 併發呼同 path；兩 worker 同跑 reconciler；shared singleton 並發訪問；threading + asyncio 邊界

## OpenClaw 特定核心

- Mac dev_disabled secret slots：見 §1（fail-closed by design）
- 絕對 import：從 srv root 跑或加 PYTHONPATH，避免 `from program_code.…` ImportError
- engine PID 變動：`cargo test` 不影響 runtime engine（Mac 端 engine_alive=false 是預期）
- passive_wait_healthcheck.py：cron 6h 跑，被動等待 TODO 有對應 check
- SLA 硬限：閾值見 performance-profiling（唯一正本）；壓測取分位（p50/p95/p99），不取單一次數值
- 測試 fixture 禁硬編日期（memory `feedback_test_fixture_wallclock_timebomb`）：日期腐化型 time-bomb 會 commit 當日綠隔日紅；fixture 一律相對時鐘或凍結時鐘
- **failed 不可增**：以同一 evidence signature 的 before/after 或可重跑 baseline 判斷；舊 memory 數字不具 freshness

## Cross-Skill 互引（避免重述）

- **E4 vs QA**：本 skill 證 source/test；只有任務宣稱 E2E/runtime business outcome 時才加 `e2e-integration-acceptance` QA
- **PR review 前置**：本 skill 跑前 E2 對抗審查走 `pr-adversarial-review`；E4 不做 code review

## 反模式（見即 BLOCKER）

- 刪測試使 passed 增加；改 assertion value 而非修代碼
- mock 業務邏輯（不只 IO）
- critical/race/flaky/release surface 未做所需重跑或 independent recheck
- skip / xfail 大量測試（看是否合理）
- 浮點比較用 `==` 沒容差；並發測試用單 task（fake concurrent）
- SLA 不跑取單一次數值
- evidence signature 或 baseline provenance 缺失
- failed 數增加但 closure fragment 沒解釋

## 輸出格式

`role_fragment_v1` 的 `payload_kind=test_fragment_v1` 至少包含：work status、gate verdict、source/dirty/untracked/
command/selected tests/toolchain/lock/OS/arch/env/config/runtime/auth signature、
passed/failed/skipped/error、EXECUTED/REUSED、expiry、flaky/critical 狀態、mock/
浮點/SLA concerns、evidence refs、退回 E1 的具體失敗、next action。
