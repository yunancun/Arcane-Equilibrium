# E4 Regression — Wave 3 G8-02 Python↔Rust ExecutorAgent decision parity (2026-04-26)

## 任務範圍

驗 E1 在 Wave 3 第二波交付的 G8-02：
- 新增 `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_decision_parity.py`（503 行）
- 新增 `srv/.../tests/fixtures/executor_parity_cases.yaml`（838 行 / 70 case）
- E1 自報 5 passed / 2 skipped / agree=70/70 (100%)

驗證範圍：(1) testfile 結果 (2) 相鄰 test 退化 (3) baseline 對照 (4) fixture sanity (5) mock vs 真邏輯 (6) synthetic case 真實感

---

## 1. Test 結果

| 引擎 | passed | failed | baseline (TODO §10) | delta |
|---|---|---|---|---|
| **Rust engine lib (release)** | 2138 | 0 | 2138 / 0 fail | ±0 / ±0 |
| **Python pytest control_api_v1（含 G8-02）** | 2754 | 35 | 2749 / 35 (no-G8-02 driven) | **+5 / ±0** |
| **Python pytest control_api_v1（不含 G8-02）** | 2749 | 35 | — | reference |
| **G8-02 testfile 獨立** | 5 | 0 | new | +5 (+2 skipped) |

第二次跑 G8-02：5 passed + 2 skipped 不變 — **不 flaky**。

注意：CLAUDE.md §九 列「pytest 3056 baseline」是全 srv `tests/`，本任務驗證的是 `control_api_v1/tests/` 子集。子集 baseline 由我本次重跑取得 = 2749 passed / 35 failed (pre-existing)。

### 35 pre-existing failed 來源 ALL CLEAR

35 failed 全集中在兩檔：
- `test_executor_shadow_toggle_api.py`（17 fail）
- `test_strategist_promote_api.py`（18 fail）

**獨立跑兩檔 → 35 全 PASS**：
- `pytest test_executor_shadow_toggle_api.py` → 17 passed
- `pytest test_strategist_promote_api.py` → 18 passed
- 兩檔合跑 → 35 passed
- G8-02 + 兩檔合跑 → **40 passed + 2 skipped**

→ pre-existing **test ordering pollution**，與 G8-02 無關。**不在本次 BLOCKER 範圍**，但建議 PM 開新 ticket（control_api_v1 全量 vs 子集 fail rate 差異）追究 root cause（推測：某 module-scope fixture 或 import side-effect mutate 全局 STORE / shadow_mode_provider singleton）。

---

## 2. 新增測試覆蓋

| 文件 | passed / skipped | scope |
|---|---|---|
| test_executor_decision_parity.py | 5 / 2 | shadow_mode boundary 70 case，cap/pct deferred markers |

### 細項
- `test_fixture_loaded_correctly` — 70/30 golden/40 synthetic 數量 sanity + case_id 唯一性
- `test_golden_fixtures_agree_rate` — 30 golden 必 100% agree（手選邊界）
- `test_synthetic_replay_agree_rate` — 40 synthetic 必 100% agree（決定性 seed）
- `test_overall_agree_rate_ge_95pct` — 70 case ≥ 67/70 binary
- `test_disagreements_logged` — 不一致時 5 個 diagnostic 欄位完整
- `test_per_symbol_cap_parity_deferred` — pytest.skip("G3-08 deferred")
- `test_max_position_pct_parity_deferred` — pytest.skip("G3-08 deferred")

新增測試嚴謹度 OK（邊界 + 中心 + skip-marker 文檔化 deferred 範圍）。

---

## 3. Fixture YAML sanity check

| 檢查 | 結果 |
|---|---|
| 70 case 全載入 | PASS（grep `case_id:` = 70）|
| 30 golden + 40 synthetic_replay | PASS（grep `source: golden` = 30, `source: synthetic_replay` = 40）|
| case_id 全唯一 | PASS（test_fixture_loaded_correctly 內 assert）|
| YAML 結構完整（首/末無截斷） | PASS（line 1 header / line 837 expected_decision: submit / line 838 EOF expected_reason: live_intent_passthrough）|
| Required field（case_id/source/config/intent/expected_decision/expected_reason）每筆全有 | PASS（_load_cases() __getitem__ 直取，缺欄會 KeyError）|

**注意**：E1 報告寫 661 行，實測 838 行（差 177 行）。建議 E1 下次自查 fixture 行數。**非 BLOCKER**。

---

## 4. Mock / 真邏輯邊界 — **WARN**

### 4.1 是否「mock vs mock trivially agree=100%」？

**部分屬實，但設計上明文告知**。需向 PM push back 說清楚 G8-02 究竟驗了什麼。

#### Python 側（真實 runtime）
`_drive_python_decision()` 真跑：
- `ExecutorConfigCache._inject_snapshot_for_tests()` 注入 snapshot（**繞過** IPC socket）
- `ExecutorAgent.__init__(shadow_mode_provider=cache.shadow_mode_provider())` 真實 ctor
- `agent.execute_order()` → `_execute_via_ipc()` 真實 dispatch logic
- `_execute_via_ipc()` 內部判 `provider() True/False` → `ExecutionReport.error == "shadow_mode"` vs 真送 `submit_order` IPC（`paper_trading_routes._ipc_command` 用 `_IpcCallRecorder` 記錄）
- → **shadow_mode_provider lambda chain 真跑**，符合 PA RFC Q2 與 G3-03 Phase B（`feedback_executor_config_cache` singleton）的設計閉環。

→ Python 側不算 mock 業務邏輯。

#### Rust 側（**reference spec，非 Rust runtime**）
`_reference_decide()` 是**純 Python function** 寫的 spec：
```python
if bool(shadow_mode):
    return ("block_shadow", "shadow_mode")
return ("submit", "live_intent_passthrough")
```

**完全不打 Rust 引擎**：
- 沒 `cargo run --bin openclaw_engine`
- 沒 `IPC dispatch` 到 `intent_processor`
- 沒驗 Rust `RiskConfig.executor` schema 的真實 deserialize 行為
- 沒驗 Rust 端在 `shadow_mode=true` 時如何處理 SubmitOrder

#### testfile 自己的免責聲明（line 35-40）
> "Reference spec contract: Both sides observe the same `RiskConfig.executor` snapshot. The reference spec (`_reference_decide`) implements the documented semantics — it is *not* a re-implementation of Rust runtime, **it *is* the schema's intent**."

→ 設計**意圖明確**：本測試是「Python runtime vs RiskConfig schema 語義意圖」的對齊驗證，**不是** Python ↔ Rust 真實 runtime parity。後者屬 G3-08。

### 4.2 為何 70 case 100% agree 是 trivially true

只判一個 bool（shadow_mode）：兩邊都「if shadow_mode → block_shadow else → submit」。

`max_position_pct` / `per_symbol_position_cap` 的 70 case 都被刻意設計為**不 gate**（Wave-3 scope），所以 noise 不會打到 agree 計算。golden_15 description 自己寫「shadow=false · qty above cap · Python still submit (Rust catches)」承認這點。

→ **agree=100% 是邏輯上的必然**，不是 statistical confidence。把 95% binary threshold 寫進 test 是 future-proof（將來 shadow_mode 邏輯增複雜時的 regression 邊界）。

### 4.3 真實 Rust parity gap

**Wave 3 G8-02 並未驗證的**：
1. Rust `intent_processor` 在收到 SubmitOrder + `shadow_mode=true` 時的行為（reject vs noop vs log）
2. Rust `RiskConfig.executor` 從 TOML deserialize 後 default 值是否與 Python `ExecutorRuntimeConfig` default 一致
3. IPC `patch_risk_config` 推 `shadow_mode=true` 後 Rust 端 ArcSwap 切換時序
4. `per_symbol_position_cap` / `max_position_pct` 兩側真實 gate 行為（**deferred 到 G3-08**）

→ 未來 G3-08 必須 cargo test 端配對驗（`tests/executor_parity_test.rs` + `bin/openclaw_engine` 啟動 + IPC dispatch + 比 reference yaml）。

### 4.4 評級
**WARN（不 fail）** — 設計意圖、scope 限制、deferred markers 都 honest 文檔化；test 結構正確；但 PM 必須清楚理解 **G8-02 ≠ true Rust runtime parity**，僅是 Python runtime 與 schema spec 對齊驗證。先前 Wave 3 dispatch report 的「Python↔Rust ExecutorAgent decision parity」標題用詞偏 oversell。

---

## 5. Synthetic case 真實感 — **WARN**

40 synthetic case（synthetic_01~40）並**非真實 record-replay**：
- 不是從 `decision_outcomes` table dump 出來的歷史 row
- YAML 注釋 line 23 寫「mock seeded random, deterministic via fixed seed」— 但實際 file 是手寫的（隨機分佈 BTCUSDT / ETHUSDT / SOLUSDT / ATOMUSDT 等 ~20 symbol，shadow_mode true/false 各半）
- 沒有 timestamp / fill_price / pnl 等 replay 必須的歷史欄位

→ 「synthetic_replay」**用詞 misleading**。實質是「procedurally generated boundary cases」，與 golden 主要差別只在數量分散。

PA RFC Q2 原話我沒讀到，但從 fixture 結構看可能是 PA 對「synthetic_replay」的定義較寬鬆（procedurally seeded sufficient）。**不 BLOCKER 但建議 PM 跟 PA 校齊術語**。

評級：**WARN** — 把「synthetic_replay」當 statistical strong evidence 的 PM 可能會誤判 confidence；視為「補強 boundary coverage 的 procedurally generated cases」則 OK。

---

## 6. SLA + 浮點 1e-4 容差

- G8-02 不涉 cross-language float（純 Python pytest，binary decision string）→ N/A
- G8-02 不涉 hot path（`execute_order` 已有自己 latency budget，本測 mocked IPC）→ N/A

---

## 7. 跑兩遍結果

| run | passed | skipped | failed |
|---|---|---|---|
| 1st (G8-02 standalone) | 5 | 2 | 0 |
| 2nd (G8-02 standalone) | 5 | 2 | 0 |
| 3rd (G8-02 + shadow_toggle + strategist_promote 組合) | 40 | 2 | 0 |

flaky? **N**

---

## 8. 結論

### **E4 Pass with conditions**

#### Pass 理由
- G8-02 5 passed + 2 skipped 確認，agree=70/70 (100%)
- 不退 baseline：control_api_v1 子集 +5 passed / ±0 failed / Rust engine lib 2138 / 0 fail 不變
- 35 pre-existing failed 與 G8-02 無關（test ordering pollution，獨立 + 組合 + 與 G8-02 同跑均 PASS）
- Fixture sanity 全 PASS（70/30/40 計數 + 結構 + 唯一性）
- Mock 邊界設計上 honest 文檔化（cache snapshot inject 繞 IPC socket / `_ipc_command` 用 recorder / business logic 真跑）
- Deferred markers（per_symbol_cap / max_position_pct）pytest.skip 標明 G3-08 範圍
- 跑兩遍同綠，不 flaky

#### Conditions（建議 PM 在合併前明文釐清）

1. **G8-02 標題用詞校準** — 不是 Python↔Rust **runtime** parity，是 Python runtime ↔ Rust schema **spec** parity（reference impl 是 Python 寫的 schema intent，不打 Rust 引擎）。Wave 3 close-out 報告 / TODO 條目應加註此限制，避免下游誤判 confidence。

2. **「synthetic_replay」術語校準** — 40 case 並非真實 `decision_outcomes` dump，是 procedurally generated boundary cases。PA RFC Q2 若已定義為廣義 synthetic OK，可保留；若 PA 原意是真 replay 則需與 PA 對齊（推測前者）。

3. **真 Rust runtime parity = G3-08 待辦** — 必須有 cargo `tests/executor_parity_test.rs` 起 engine + IPC dispatch + 比對 reference yaml。G3-08 close 才算 ExecutorAgent 整鏈 parity 真綠。

4. **35 pre-existing failed root cause** — control_api_v1 全量跑 35 fail / 子集獨立跑 0 fail 是 test isolation bug，建議 PM 開新 ticket（推測 module-scope fixture 或 STORE / shadow_mode_provider singleton mutation）。**不阻擋 G8-02 commit**，但長期不修 → CI green 永遠是「不全量跑」+ false confidence。

5. **E1 fixture 行數自報誤差** — 報 661，實 838。下次 fixture 提交時 PA/E2 對 self-report 行數做最低 sanity check。

#### 退回 E1 修復清單
**無**。G8-02 testfile 結構正確，覆蓋設計合理，文檔化 deferred 範圍乾淨。Conditions 1~4 是 PM 層面溝通 / 後續 ticket，非 E1 重做事項。

---

## 9. baseline 變動記錄（PM commit message 用）

```
G8-02 ExecutorAgent decision parity test landed.

Python pytest control_api_v1 baseline:
  before:  2749 passed / 35 failed (pre-existing isolation pollution)
  after:   2754 passed / 35 failed
  delta:   +5 passed / ±0 failed (G8-02 5 passed + 2 skipped deferred markers)

Rust engine lib (release):
  before:  2138 / 0 fail
  after:   2138 / 0 fail
  delta:   ±0 (G8-02 不動 Rust 代碼)

G8-02 scope: Python runtime ↔ Rust schema spec parity
  shadow_mode wired (70 case agree=100%);
  per_symbol_position_cap / max_position_pct deferred to G3-08.

35 pre-existing failed: test_executor_shadow_toggle_api.py + test_strategist_promote_api.py
  (test ordering pollution, all PASS standalone, unrelated to G8-02).
```
