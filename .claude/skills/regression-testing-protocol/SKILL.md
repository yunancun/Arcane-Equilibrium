---
name: regression-testing-protocol
description: E4 agent 主用：跑回歸/驗收測試、報告測試計數、新增或改動測試檔、或測試結果與基準線有出入時必讀。
allowed-tools: Read, Grep, Glob, Bash
---

# Regression Testing Protocol（回歸測試手冊）

> Authority 使用 `.codex/agent_registry_v1.json` typed matrix。測試證明
> implementation behavior；runtime observation、active state、normative policy
> 分屬不同 class，不能用某一類結果覆蓋另一類 denial。

`SRV`=倉庫根（Mac: `~/Projects/TradeBot/srv`；Linux: `~/BybitOpenClaw/srv`）。

## 何時觸發

- Source Implementation 經獨立 E2 review 後，E4 負責 relevant regression evidence
- 「跑測試」「驗證 fix 沒破壞其他」「測試數有沒有回退」
- 新功能落地前的 baseline 確認
- Rust `cargo test` + Python pytest 雙引擎同步

## ★ 核心原則

1. **基準線不可回退**：passed 數 < baseline = BLOCKER
2. **不允許刪測試使測試通過**：發現失敗 → 修代碼，不修測試
3. **Mock 不掩蓋真實邏輯**：mock 只 stub IO 邊界，不 stub 業務邏輯
4. 跨語言浮點 1e-4 容差：Python ↔ Rust 同輸入差異 ≥ 1e-4 = bug
5. **重跑按風險**：critical、已失敗、known-flaky、release gate 才要求第二遍；
   其他 exact signature 綠證據不做儀式性重跑

## 1. 當前測試基準線（動態，每次審計前重跑命令拿，不信寫死數字）

| 引擎 | 命令 | 解讀 |
|---|---|---|
| Python pytest | `cd $SRV && python3 -m pytest tests/ -q --tb=short \| tail -5` | passed / failed 數 |
| Rust engine lib | `cd $SRV/rust && cargo test --release -p openclaw_engine --lib 2>&1 \| tail -5` | passed / failed 數 |
| Rust integration | `cd $SRV/rust && OPENCLAW_TEST_PG="..." cargo test --release -p openclaw_engine 2>&1 \| tail -5` | 需 PG |

**baseline 規則**：
- 任何 commit 不可降低 passed 數
- 任何 commit 不可增加 pre-existing failed 數
- Baseline 來自 exact source/diff/toolchain/env signature 的前後結果；不以 E4
  memory 的舊 passed count 當當前真相

**Mac dev-only 注意**（唯一正本段）：
- 部分整合測試需 external/runtime surface 時，source suite 只證明 source；
  另由正確 Adapter/OPS/QA 取得 runtime evidence
- Delegated E4 的 Rust build/test/check 全在 Mac；Linux cargo 一律禁止

## 2. Python pytest 標準命令

```bash
# 從 srv root 跑（重要：絕對 import）
cd $SRV
python3 -m pytest tests/ -q --tb=short

# 或從 control_api_v1 內（部分 test 路徑要求）
cd program_code/exchange_connectors/bybit_connector/control_api_v1/
python3 -m pytest tests/ -q --tb=short
```

## 3. Rust cargo test 標準命令

```bash
# Lib 測試（fastest）
cd $SRV/rust
cargo test --release -p openclaw_engine --lib

# 含集成測試（需 PG）
OPENCLAW_TEST_PG="postgres://..." cargo test --release -p openclaw_engine
```

## 4. 測試類型與覆蓋要求

### 4.1 Unit test
- 每個新 E1 改動有對應 unit test
- 邊界值 + 正常路徑至少各 1
- 修復安全問題需有「修復後攻擊路徑測試通過」

### 4.2 Integration test
- 跨模塊調用鏈（如 Strategist → IPC → Rust engine）
- 連 PG 的測試（含 hypertable / migration）
- Bybit demo / paper API 整合（Mac 端 dev_disabled 跳過，見 §1）

### 4.3 Property-based test (proptest)
- Rust 狀態機轉換窮舉
- 序列化 / 反序列化往返（serde round-trip）
- IPC schema 隨機 fuzzing

### 4.4 Concurrency test
- asyncio 多 task 並發呼同 path
- 兩個 worker 同時跑 reconciler
- shared singleton 並發訪問
- threading + asyncio 邊界

### 4.5 SLA / 壓測
- SLA 閾值唯一正本見 performance-profiling skill（本檔不重述數字）
- 測 N=10000 次取分位（p50 / p95 / p99）

### 4.6 Cross-language consistency
- 相同 input 在 Python 和 Rust 下指標值差異 < 1e-4
- 例：ATR / BB band / Sharpe 計算

## 5. Mock 安全規則

### 5.1 何時 OK mock
- 外部 IO（HTTP API、PG connection、file system）
- 時間（patch `datetime.now()`）
- 隨機（patch `random.random()`）

### 5.2 何時 NOT OK mock
- 業務邏輯（如 mock RiskManager.should_allow → 不知是否真的算）
- 計算函數（mock indicator → 不知公式對不對）
- IPC 協議邏輯（mock 整個 IPC client → 不知 protocol 對不對）

### 5.3 反模式
```python
# 反例：mock 業務邏輯
@patch('app.risk_manager.RiskManager.should_allow', return_value=True)
def test_strategy(mock_allow):
    # 永遠通過，無法測 RiskManager 邏輯

# 正例：mock IO，留業務邏輯真跑
@patch('app.bybit_rest_client.BybitClient.place_order', return_value=fake_response)
def test_strategy(mock_order):
    # RiskManager 真跑，只 mock 外部 API
```

## 6. 浮點一致性測試（Rust ↔ Python）

```python
def test_atr_consistency():
    df = load_test_klines("BTCUSDT_1m_100bars.csv")
    
    py_atr = python_indicators.atr(df, 14)
    rust_atr_list = ipc_client.compute_atr(df.to_dict(), 14)
    
    for py, rs in zip(py_atr, rust_atr_list):
        assert abs(py - rs) / abs(py) < 1e-4, f"ATR mismatch: py={py}, rs={rs}"
```

容差 1e-4 = 相對誤差 0.01%。crypto 1m 級別下足夠（價格波動 > 1bps）。

## 7. 並發測試範例

```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_governance_concurrent_lease_request():
    gov_hub = GovernanceHub()
    
    async def request():
        return await gov_hub.acquire_lease("symbol1", "strategy1")
    
    # 100 個並發 lease request
    results = await asyncio.gather(*[request() for _ in range(100)])
    
    # 只有 1 個 acquire 成功
    success = sum(1 for r in results if r.granted)
    assert success == 1, f"Expected 1 lease grant, got {success}"
```

## 8. 工作流

1. 讀 acceptance、E2 verdict、diff、direct callers 與 test impact。
2. 先跑最小能 falsify change 的 focused test。
3. 依 dependency/reach 擴至 relevant module/cross-language/regression suite。
4. 新增缺少的邊界、並發、安全或 intent test；不寫 business code。
5. 審 mock、浮點、SLA、PG/runtime evidence scope 是否誠實。
6. critical/failed/known-flaky/release gate 才做第二遍或 independent recheck。
7. 產 content-addressed evidence capsule，標 EXECUTED/REUSED/SKIPPED/FAILED。
8. 回 immutable `role_fragment_v1` with `payload_kind=test_fragment_v1`；不寫 E4 memory/report。

## OpenClaw 特定核心

- Mac dev_disabled secret slots：見 §1（fail-closed by design）
- 絕對 import：從 srv root 跑或加 PYTHONPATH，避免 `from program_code.…` ImportError
- engine PID 變動：`cargo test` 不影響 runtime engine（Mac 端 engine_alive=false 是預期）
- passive_wait_healthcheck.py：cron 6h 跑，被動等待 TODO 有對應 check
- 跨語言浮點 1e-4 容差：indicator 計算（ATR / BB / Sharpe）必驗
- SLA 硬限：閾值見 performance-profiling（唯一正本）
- **failed 不可增**：以同一 evidence signature 的 before/after 或可重跑
  baseline 判斷；舊 memory 數字不具 freshness

## Cross-Skill 互引（避免重述）

- **E4 vs QA**：本 skill 證 source/test；只有任務宣稱 E2E/runtime business
  outcome 時才加 `e2e-integration-acceptance` QA
- **PR review 前置**：本 skill 跑前 E2 對抗審查走 `pr-adversarial-review`；E4 不做 code review

## 反模式（見即 BLOCKER）

- 刪測試使 passed 增加
- 改 assertion value 而非修代碼
- mock 業務邏輯（不只 IO）
- critical/race/flaky/release surface 未做所需重跑或 independent recheck
- skip / xfail 大量測試（看是否合理）
- 浮點比較用 `==` 沒容差
- 並發測試用單 task（fake concurrent）
- SLA 不跑取單一次數值
- evidence signature 或 baseline provenance 缺失
- failed 數增加但 closure fragment 沒解釋

## 輸出格式

`role_fragment_v1` 的 `payload_kind=test_fragment_v1` 至少包含：work status、gate verdict、source/dirty/untracked/
command/selected tests/toolchain/lock/OS/arch/env/config/runtime/auth signature、
passed/failed/skipped/error、EXECUTED/REUSED、expiry、flaky/critical 狀態、mock/
浮點/SLA concerns、evidence refs、退回 E1 的具體失敗、next action。
