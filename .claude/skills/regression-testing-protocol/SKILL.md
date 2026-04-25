---
name: regression-testing-protocol
description: 回歸測試 SOP — 測試基準線追蹤、不刪測試遮蓋失敗、並發測試、跨語言浮點 1e-4 容差、SLA <1ms 壓測、mock 不掩蓋邏輯、Rust + Python 雙引擎測試。E4 agent 主用。
allowed-tools: Read, Grep, Glob, Bash
---

# Regression Testing Protocol（回歸測試手冊）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- E4 收到 E2 通過的 PR → commit 前必跑（強制工作鏈，CLAUDE.md §八）
- 「跑測試」「驗證 fix 沒破壞其他」「測試數有沒有回退」
- 新功能落地前的 baseline 確認
- Rust `cargo test` + Python pytest 雙引擎同步

## ★ 核心原則

1. **基準線不可回退**：passed 數 < baseline = BLOCKER
2. **不允許刪測試使測試通過**：發現失敗 → 修代碼，不修測試
3. **Mock 不掩蓋真實邏輯**：mock 只 stub IO 邊界，不 stub 業務邏輯
4. **跨語言浮點 1e-4 容差**：Python ↔ Rust 同輸入差異 ≥ 1e-4 = bug
5. **跑兩遍**：第一次過 ≠ 真綠（race / flaky）；第二次同樣綠才算

## 1. 當前測試基準線（**動態，每次審計前重跑命令拿，不信本表寫死數字**）

| 引擎 | 命令 | 解讀 |
|---|---|---|
| Python pytest | `cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest tests/ -q --tb=short \| tail -5` | passed / failed 數 |
| Rust engine lib | `cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 \| tail -5` | passed / failed 數 |
| Rust integration | `cd /Users/ncyu/Projects/TradeBot/srv/rust && OPENCLAW_TEST_PG="..." cargo test --release -p openclaw_engine 2>&1 \| tail -5` | 需 PG |

**baseline 規則**（CLAUDE.md §九）：
- 任何 commit 不可降低 passed 數
- 任何 commit 不可增加 pre-existing failed 數
- 數字以**改動前最後一次 baseline run** 為準（不信本 skill 內任何寫死數字）

⚠️ Mac 端：整合測試打真實 Bybit 會 fail by design（`*.dev_disabled_*` secret slot；CLAUDE.md §七 Mac dev-only 模式）。Rust release 基準 → `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` 取真實值。

## 2. Python pytest 標準命令

```bash
# 從 srv root 跑（重要：絕對 import）
cd /Users/ncyu/Projects/TradeBot/srv
python3 -m pytest tests/ -q --tb=short

# 或從 control_api_v1 內（部分 test 路徑要求）
cd program_code/exchange_connectors/bybit_connector/control_api_v1/
python3 -m pytest tests/ -q --tb=short
```

**Mac dev-only 注意（CLAUDE.md §七）**：
- 部分整合測試打真實 Bybit → 3 secret slot rename 為 `*.dev_disabled_*` → 預期 fail-closed by design
- mock-based unit test 不受影響
- Reproduce release 基準 `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"`

## 3. Rust cargo test 標準命令

```bash
# Lib 測試（fastest）
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo test --release -p openclaw_engine --lib

# 含集成測試（需 PG）
OPENCLAw_TEST_PG="postgres://..." cargo test --release -p openclaw_engine
```

## 4. 測試類型與覆蓋要求

### 4.1 Unit test
- 每個新 E1 改動必須有對應 unit test
- 邊界值 + 正常路徑至少各 1
- 修復安全問題必須有「修復後攻擊路徑測試通過」

### 4.2 Integration test
- 跨模塊調用鏈（如 Strategist → IPC → Rust engine）
- 連 PG 的測試（含 hypertable / migration）
- Bybit demo / paper API 整合（Mac 端 dev_disabled 跳過）

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
- H0 Gate < 1ms 延遲
- Tick path < 0.3ms
- IPC round-trip < 5ms
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

## 8. 工作流（10 步）

1. **讀 E2 通過的 diff**
2. **跑全量 Python pytest**（從 srv root，srv 子目錄）
3. **跑 Rust cargo test --release**
4. **驗 passed >= baseline + failed <= pre-existing**
5. **新增測試 cover 邊界 + 並發 + 安全**
6. **mock 審查**（沒 mock 業務邏輯）
7. **浮點一致性**（如改 indicator / 計算）
8. **SLA 壓測**（如改 hot path）
9. **跑兩遍**（驗證非 flaky）
10. **記錄測試數變化**（commit message 含 baseline 變動）

## OpenClaw 特定核心

- **強制工作鏈**：E2 → E4 不可跳，包括 P0 緊急（CLAUDE.md §八）
- **Mac dev_disabled secret slots**：整合測試打真實 Bybit fail-closed by design
- **絕對 import**：從 srv root 跑或加 PYTHONPATH，避免 `from program_code.…` ImportError
- **engine PID 變動**：`cargo test` 不影響 runtime engine（Mac 端 engine_alive=false 是預期）
- **passive_wait_healthcheck.py**：cron 6h 跑，被動等待 TODO 必有對應 check
- **跨語言浮點 1e-4 容差**：indicator 計算（ATR / BB / Sharpe）必驗
- **SLA 硬限**：H0 Gate < 1ms / Tick path < 0.3ms / IPC < 5ms
- **commit 即 push**（CLAUDE.md §七 git 自動化）
- **failed 不可增**：17 pre-existing 是上限，新增 = BLOCKER

## 反模式（見即 BLOCKER）

- 刪測試使 passed 增加
- 改 assertion value 而非修代碼
- mock 業務邏輯（不只 IO）
- 「跑一次過了所以綠」（沒測 race）
- skip / xfail 大量測試（看是否合理）
- 浮點比較用 `==` 沒容差
- 並發測試用單 task（fake concurrent）
- SLA 不跑取單一次數值
- commit 但 baseline 沒記錄變動
- failed 數增加但 commit message 沒解釋

## 輸出格式

```markdown
# E4 Regression Test Report — <commit> · <date>

## Test 結果
| 引擎 | passed | failed | baseline | delta |
| Python pytest | | | 2555 | |
| Rust cargo test (lib) | | | 1980 | |
| Rust integration | | | varies | |

## 新增測試
| 文件 | tests count | scope (邊界/並發/安全) |

## Mock 審查
| Test | mock 內容 | OK? |

## 浮點一致性（如改 indicator）
| 函數 | py | rust | 相對誤差 | OK? |

## SLA 壓測（如改 hot path）
| Path | p50 | p95 | p99 | 目標 |

## 跑兩遍結果
1st run: passed=X / failed=Y
2nd run: passed=A / failed=B
flaky? Y/N

## 結論
PASS / FAIL（具體 BLOCKER）

## 退回 E1 修復清單（如 FAIL）
1. <具體 test + 失敗原因>
```
