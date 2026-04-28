# G3-08-FUP-STRATEGIST-DELEGATOR-SLIM P3 — strategist_agent.py LOC slim

**日期**：2026-04-28
**Owner**：PA + E1 合一執行（worktree pattern，不 commit）
**基底 HEAD**：`3e05e01`（origin/main）
**Ticket**：G3-08-FUP-STRATEGIST-DELEGATOR-SLIM P3 — lift 16 BWD-compat 1-line delegators + body 搬遷至 sibling 以維持 §九 800 行警告線

---

## 摘要 / Summary

`strategist_agent.py` 從 **933 LOC → 782 LOC**（減 151 行 / -16.2%），降至 §九 800 警告線之下。

| 檔案 | 變動前 | 變動後 | Delta |
|---|---|---|---|
| `strategist_agent.py` | 933 | **782** ✅ | -151 |
| `strategist_edge_eval.py` | 376 | 488 | +112（吸收 `_produce_intents`）|
| `strategist_weights.py` | 224 | 224 | 0 |
| `strategist_cognitive.py` | 278 | 349 | +71（吸收 `record_trade_outcome`）|
| **合計** | 1811 | 1843 | +32（淨成本 = sibling docstring + import 開銷）|

---

## 1. 為何不能單純照 spec「lift 16 delegators 為 sibling stub」

**Spec 原始建議**：「sibling 直接定義 fn，strategist_agent.py 透過 `from .strategist_<sibling> import <fn>` re-export」

**實測阻擋**：22 處 test 程式碼依 `agent.method` 為 **bound method** 的 contract（典型 `agent._evaluate_edge = MagicMock(wraps=agent._evaluate_edge)`）。

- 純 `from .x import _evaluate_edge` 只在 module namespace 暴露 callable；**class 屬性 `StrategistAgent._evaluate_edge` 會消失** → instance lookup `agent._evaluate_edge` 拋 `AttributeError` → `MagicMock(wraps=...)` 取不到原 method。
- 範例 callsite：
  ```
  test_strategist_agent.py:250: agent._evaluate_edge = MagicMock(wraps=agent._evaluate_edge)
  test_strategist_agent.py:299: agent._evaluate_edge = MagicMock(wraps=agent._evaluate_edge)
  test_strategist_agent.py:411: agent._evaluate_edge = mock_eval
  test_strategist_agent.py:471: agent._evaluate_edge = mock_eval_sync
  test_strategist_agent.py:599: agent._evaluate_edge = lambda _intel: positive_eval
  test_strategist_agent.py:639: agent._evaluate_edge = lambda _intel: positive_eval
  ```

**結論**：16 delegator 的 class-level `def` **必須留**；解 LOC 的真正工具是「壓縮每個 delegator 至 1-line」+「搬大塊 body 至 sibling」。

---

## 2. 實際抽出設計（3 軸）

### 軸 A：Delegator 1-line 化（16 + 4 H1/H4 + 4 cognitive + record_trade_outcome 共 25 method）

`def name(self, ...) -> T: return _x_name(self, ...)` 取代原 4-line `def + docstring + return + blank`，**header 區段 docstring 統一說明**「為何留這個薄包裝」。每 method 省 ~3 lines × 25 ≈ ~75 lines。

範例：
```python
# Before (4 lines × 16):
def set_budget_manager(self, budget_manager: Any) -> None:
    """Backward-compatible delegator to strategist_weights / 向後兼容委託"""
    return _sw_set_budget_manager(self, budget_manager)

# After (1 line):
def set_budget_manager(self, budget_manager: Any) -> None: return _sw_set_budget_manager(self, budget_manager)  # noqa: E704
```

`# noqa: E704` 抑制 pycodestyle「statement on same line as def」警告（E5 既有規範允許薄 delegator 此用法）。

### 軸 B：`_produce_intents` body lift → `strategist_edge_eval.py`

`_produce_intents` 80 行 body 搬到 `strategist_edge_eval.py`（與 `_evaluate_edge` 同 sibling，語意上 evaluation → intent production 連續）。主檔保留 1-line delegator。

**為何選 strategist_edge_eval.py 而非 weights**：intent 構建依 `evaluation` 結果（`evaluation.source` / `evaluation.confidence` / `evaluation.reason`），與 edge eval 是 producer/consumer 關係，組合度高；`weights` sibling 只承載 weight 計算，並非派發層。

新 import：`AgentMessage / AgentRole / MessageType / TradeIntent` 加進 `strategist_edge_eval.py`（原本只 import IntelObject）。

### 軸 C：`record_trade_outcome` body lift → `strategist_cognitive.py`

`record_trade_outcome` 55 行 body（含完整雙語 docstring + fail-open try/except）搬到 `strategist_cognitive.py`，與 `tick_cognitive_modulator` 同檔（前者寫 `_stats["consecutive_losses"]`，後者讀 → 凝聚度高）。

主檔保留 1-line delegator + 2-line bilingual context comment（解釋為何 wiring point 在這裡，避免讀者誤以為刪錯）。

---

## 3. E2 NIT-1 LOW 附帶修復：`_handle_intel` 5 early-return hook

E2 4-1 audit NIT-1 LOW：原 `_invalidate_h_state_async` 只在「成功評估完」+「intent 派發後」fire；5 個 early-return（emergency / empty payload / parse error / relevance skip / age skip）silent，h_state cache 對拒絕事件失明。

修復：每個 early-return 加一行 `_invalidate_h_state_async("agent.strategist.<reason>")`。env=0 時 no-op，零負擔；env=1 時讓 Rust h_state cache poller 早一拍感知 strategist tick 已發生但被拒絕，避免「intel_received 動了，stats 卻 stale」的狀態誤導。

5 hint reason key：
- `agent.strategist.emergency_discard`
- `agent.strategist.empty_payload`
- `agent.strategist.parse_error`
- `agent.strategist.relevance_skip`
- `agent.strategist.age_skip`

---

## 4. 副作用識別

| 改動 | 影響面 | 風險評級 | 緩解 |
|---|---|---|---|
| 16 delegator 壓縮為 1-line | 純 cosmetic；method body 等價 | 極低 | 既有 22 處 test patch + `agent.method = MagicMock(wraps=...)` 全綠 |
| `_produce_intents` body lift | `_handle_intel` 唯一 caller；test 無直接 patch | 低 | bound-method delegator 保留；25 strategist test 全綠 |
| `record_trade_outcome` body lift | `strategy_wiring.py` callback + `test_g8_01_fup_losses_wiring.py` 直呼 `agent.record_trade_outcome(net_pnl)` | 低 | bound-method delegator 保留；LOSSES-WIRING 8 test 全綠 |
| 5 early-return `_invalidate_h_state_async` 新增 | h_state cache 提示頻率↑（env=1 時）；env=0 / 測試環境 no-op | 極低 | hint 純 fire-and-forget，內部 try/except 完整吞例外 |

**未涉**：API schema / Rust IPC / SQL schema / asyncio-threading 邊界 / 治理 SM / Decision Lease / Authorization / 16 根原則任一條 / DOC-08 §12 9 條安全不變量任一條 / §四 硬邊界任一項。

---

## 5. Mac pytest 結果

### Spec 指定 6 檔聚合
```
PYTHONPATH=. ./venvs/mac_dev/bin/pytest \
    test_strategist_agent.py test_strategist_audit_wiring.py \
    test_strategist_cognitive_w1_fix.py test_g8_01_fup_losses_wiring.py \
    test_cognitive_modulator_coverage.py test_strategist_cognitive_integration.py -q
→ 98 passed in 0.14s ✅
```

### 廣度回歸（strategist | h_chain | batch7 | truth_source | batch9 | strategist_stress）
```
→ 251 passed, 2869 deselected, 17 warnings in 1.18s ✅
```

LOSSES-WIRING（Wave A `aced662`）+ SINGLETON-FIX（W1 cognitive）+ tick_cognitive_modulator（G8-01 W1 FIX-B）三大既有接線完整保留驗證。

---

## 6. 16 根原則合規

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ 不涉 | StrategistAgent shadow=True 預設，本 refactor 0 觸碰寫入口 |
| 3 | AI ≠ 即時命令 | ✅ 保留 | shadow path / MessageBus 派發 / Guardian 介入流程 100% 保留 |
| 4 | 不繞風控 | ✅ 不涉 | 未動 RiskConfig 任一欄位 |
| 6 | 失敗默認收縮 | ✅ 強化 | record_trade_outcome / tick_cognitive_modulator / _produce_intents 三處 fail-open / fail-closed try/except 全保留；新增 5 early-return hint 為純診斷，不改 fail policy |
| 7 | 學習 ≠ 改寫 Live | ✅ 不涉 | TruthRegistry / CognitiveModulator / 學習平面隔離維持 |
| 8 | 可解釋 | ✅ 強化 | 5 early-return 補 h_state hint → 拒絕事件可被 Rust cache 追蹤；audit event 名 + payload 100% 對齊原 |
| 11 | Agent 自主權 | ✅ 不涉 | 認知門檻調製 / 模型路由 / 預算 gate 路徑全保留 |
| 13 | AI 成本感知 | ✅ 保留 | H5 Ollama call 紀錄 + cost_tracker / cognitive 連動完整保留 |

**硬邊界**：0 觸碰（未改 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` / `decision_lease_emitted` 任一處；max_retries=0 fail-closed 邊界透過 `_evaluate_edge` 路徑於 sibling 內保留）。

---

## 7. BWD-compat invariant 驗證

| 機制 | 狀態 | 驗證 |
|---|---|---|
| `StrategistAgent._evaluate_edge` class attr | ✅ 1-line delegator | `MagicMock(wraps=agent._evaluate_edge)` 5 處 callsite 全綠 |
| `agent._produce_intents` bound method | ✅ 1-line delegator | `_handle_intel` 內 `self._produce_intents(intel, evaluation)` callsite 透通 |
| `agent.record_trade_outcome(net_pnl)` | ✅ 1-line delegator | LOSSES-WIRING 8 callsite + AnalystAgent callback 透通 |
| `patch("app.strategist_agent._invalidate_h_state_async")` | ✅ re-export 不變 | `test_strategist_agent.py:1106` 唯一 module-level patch 全綠 |
| `from app.strategist_agent import StrategistAgent, StrategistConfig, EdgeEvaluation, _heuristic_evaluate` | ✅ 透過 strategist_models re-export | 22 處 test import 全綠 |

---

## 8. 完成檢查清單

- [x] LOC 達標：`strategist_agent.py` 933 → **782**（≤800 首選達成，距 770 acceptable line 12 行內）
- [x] 16 delegator 壓縮 1-line + 9 額外 method（4 H1/H4 + 4 cognitive + record_trade_outcome）同步壓縮
- [x] 2 method body lift：`_produce_intents` → strategist_edge_eval / `record_trade_outcome` → strategist_cognitive
- [x] E2 4-1 NIT-1 LOW：`_handle_intel` 5 early-return 補 `_invalidate_h_state_async` hint
- [x] 雙語注釋（中英對照 module / class / method-level docstring + 新增 fn docstring）
- [x] BWD-compat：bound-method delegator 完整保留 + re-export 透通 + class attr 不消失
- [x] LOSSES-WIRING（Wave A）+ SINGLETON fix（W1）+ G8-01 W1 FIX-B tick_cognitive_modulator 接線不破
- [x] Mac pytest spec 6 檔：98/98 ✅ / 廣度回歸 251/251 ✅
- [x] 0 production behavior change（純位置 refactor + 純診斷 hint 新增）
- [x] §四 硬邊界 0 觸碰

---

## 9. Operator 後續

- 本 ticket 為 worktree pattern，**不 commit**（per spec Step 5）。
- §九 singleton 表 / §九 文件大小規則無變動，CLAUDE.md 無需同步。
- 後續若 `strategist_agent.py` 再次膨脹接近 800：下一個自然抽出單位為
  - **status snapshot 三件套**（`get_stats` / `get_h4_snapshot` / `get_strategist_snapshot` ≈ 70 行）→ 可抽至 `strategist_status.py` 新 sibling
  - 或 **`__init__` 內 stats dict 預設值** → 抽至 `strategist_models.py` module-level constant，ctor 改 `_DEFAULT_STATS.copy()`

— PA Project Architect, 2026-04-28
