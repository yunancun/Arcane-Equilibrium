# G3-08-FUP-ANALYST-SPLIT P2 — analyst_agent.py sibling extract

**日期**：2026-04-28
**Owner**：PA + E1 合一執行（worktree pattern，不 commit）
**基底 HEAD**：`8a5973f`（origin/main）
**Ticket**：G3-08-FUP-ANALYST-SPLIT P2 — extract sibling from analyst_agent.py 944 LOC > 800 warn

---

## 摘要 / Summary

`analyst_agent.py` 從 **944 LOC → 781 LOC**（減 163 行 / -17.3%），降至 §九 800 警告線之下。
抽出 **2 個 sibling 模組**：

| 檔案 | LOC | 內容 |
|---|---|---|
| `analyst_agent.py` | **781** ✅ | AnalystAgent class + lifecycle + L1 + L2 + 接線 callbacks |
| `analyst_records.py` | 142 | `TradeRecord` / `PatternInsight` / `AnalystConfig` 純 dataclasses |
| `analyst_pattern_claims.py` | 264 | `KNOWN_STRATEGIES` / `extract_strategy_from_pattern` / `register_pattern_claims` / `record_pattern_observations` 純函式 helpers |
| **合計** | 1187 | （原 944 → 1187，+243 行為 sibling docstring + import 開銷） |

**0 行為變更** — 純位置 refactor，所有 dataclass 欄位/預設值/property/序列化、所有 fail-open 語意、所有 lock 邊界、所有 audit 事件、`_KNOWN_STRATEGIES` class-level 屬性、`_extract_strategy_from_pattern` staticmethod、`_register_pattern_claims` / `_record_pattern_observations` instance method 簽名 100% 對齊原始實作。

---

## 1. 抽出設計

### Sibling 1：`analyst_records.py`（142 LOC）

**內容**：3 個 dataclass + module docstring。

- `TradeRecord`（U-05 fees + param_snapshot 欄位完整保留，`is_win` / `net_pnl` property + `to_dict()`）
- `PatternInsight`（uuid factory + 序列化欄位）
- `AnalystConfig`（環境變數 `ANALYST_L2_MIN_OBS` 讀取保留）

**動機**：100% self-contained，無對 AnalystAgent 內部 state 依賴。

### Sibling 2：`analyst_pattern_claims.py`（264 LOC）

**內容**：模式聲明登記 / observation 記錄純函式 helpers。

- `KNOWN_STRATEGIES`（module-level frozenset，原 `AnalystAgent._KNOWN_STRATEGIES`）
- `extract_strategy_from_pattern(pattern_text)`（原 `_extract_strategy_from_pattern` staticmethod）
- `register_pattern_claims(*, insight, n_obs, truth_registry, experiment_ledger, logger)`
- `record_pattern_observations(*, experiment_ledger, insight, is_winning, logger)`

**動機**：純 stateless helpers — 只讀 `insight` 屬性、`n_obs` int snapshot、`truth_registry` / `experiment_ledger` 注入物件；不接觸 AnalystAgent 任何 instance state（`self._lock` / `self._records` / `self._stats`），可完全 stateless 化。

### `analyst_agent.py`（781 LOC）保留

- AnalystAgent class 本體 + `__init__` + lifecycle + `on_message` 路由
- L1：`analyze_trade` / `compute_strategy_metrics` / `get_strategy_rankings` / `get_regime_metrics`
- L2：`analyze_patterns` / `_run_l2_analysis` / `_ai_pattern_analysis` / `_statistical_pattern_analysis`
- 接線：`set_strategist_loss_callback` / `set_truth_registry` / `set_experiment_ledger`
- Status：`get_analyst_snapshot` / `get_stats` / `get_latest_insight`
- LOSSES-WIRING（Wave A `aced662`）callback 機制完整保留：`_strategist_loss_callback` instance attr + `analyze_trade` 中的 `try/except` fail-open 呼叫 + `set_strategist_loss_callback` setter

### BWD-compat 機制（4 條）

1. **Re-export dataclass**：`from .analyst_records import AnalystConfig, PatternInsight, TradeRecord` + `__all__` 導出 → `from app.analyst_agent import TradeRecord` 等所有既有 import 完全不破。
2. **Class-level 屬性別名**：`AnalystAgent._KNOWN_STRATEGIES = KNOWN_STRATEGIES` → 任何讀 class attribute 的 caller 取得 identical frozenset。
3. **Static method delegator**：`AnalystAgent._extract_strategy_from_pattern(s)` → `extract_strategy_from_pattern(s)`，1-line 委派。
4. **Instance method delegator**：`AnalystAgent._register_pattern_claims(insight)` 與 `AnalystAgent._record_pattern_observations(insight, is_winning)` → 取 `len(self._records)` snapshot + 注入 `self._truth_registry` / `self._experiment_ledger` 後委派至 sibling helper，fail-open 語意完全一致。

---

## 2. 副作用識別

| 改動 | 影響面 | 風險評級 | 緩解 |
|---|---|---|---|
| 提取 dataclass 至 sibling | 6 個既有 test + `strategy_wiring.py` + `ai_service_dispatch.py` import | 低 | re-export 保 import 路徑 + `is` identity 驗證通過 |
| 提取 pattern_claims helpers 至 sibling | `_register_pattern_claims` 由 `_ai_pattern_analysis` + `_statistical_pattern_analysis` 內部呼叫，無外部 caller | 低 | instance method delegator 保 patch / mock 兼容 |
| `_KNOWN_STRATEGIES` 移為 module-level | class-level 屬性讀取（如 `AnalystAgent._KNOWN_STRATEGIES`） | 極低 | class-level alias 保留，identity check 通過 |
| `_extract_strategy_from_pattern` 移為 module-level | staticmethod 呼叫（如 `AnalystAgent._extract_strategy_from_pattern(...)`） | 極低 | staticmethod delegator 保留 |

**不涉**：API schema / Rust IPC / SQL schema / asyncio-threading 邊界 / 治理 SM / Decision Lease / 16 根原則任一條 / DOC-08 §12 9 條安全不變量任一條 / §四 硬邊界任一項。

---

## 3. Mac pytest 結果

```
# Spec 指定主測試
PYTHONPATH=. pytest control_api_v1/tests/test_analyst_agent_unit.py -q
→ 22 passed in 0.03s

# 擴展 analyst-touching 回歸（6 檔聚合）
PYTHONPATH=. pytest [analyst_unit + analyst_registry + g8_01_fup_losses_wiring +
                    truth_source_registry + agent_audit_bridge +
                    batch9_perception_analyst_integration] -q
→ 146 passed in 0.10s

# Keyword 廣度回歸（analyst | pattern | losses | experiment_ledger）
PYTHONPATH=. pytest control_api_v1/tests/ -q -k "..."
→ 166 passed, 2954 deselected, 12 warnings (pre-existing pydantic v2)
```

LOSSES-WIRING（Wave A `aced662`）的 Strategist→Analyst 雙向接線測試（`test_g8_01_fup_losses_wiring.py`）全綠 → callback 機制完整保留驗證通過。

---

## 4. 16 根原則合規

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ 不涉 | 純 read-only 分析模組 |
| 3 | AI ≠ 即時命令 | ✅ 不涉 | Analyst 不下單 |
| 4 | 不繞風控 | ✅ 不涉 | 未動 RiskConfig |
| 6 | 失敗默認收縮 | ✅ 保留 | 所有 fail-open 語意（`_register_pattern_claims` / `_record_pattern_observations` / `_strategist_loss_callback`）原樣搬遷，例外仍 log+吞下 |
| 7 | 學習 ≠ 改寫 Live | ✅ 保留 | `register_pattern_claims` 仍只操作 TruthSourceRegistry + ExperimentLedger 學習平面 |
| 8 | 可解釋 | ✅ 保留 | 所有 `self._audit(...)` 呼叫位置與 payload 完全一致 |

**硬邊界**：0 觸碰（未改 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` / `decision_lease_emitted` 任一處）。

---

## 5. 完成檢查清單

- [x] LOC 達標：`analyst_agent.py` 944 → **781**（≤800 首選達成）
- [x] 2 sibling 抽出：`analyst_records.py`（142）+ `analyst_pattern_claims.py`（264）
- [x] 雙語注釋（中英對照 module docstring + 函數 docstring）
- [x] BWD-compat：re-export + class-level alias + staticmethod / instance method delegators
- [x] LOSSES-WIRING callback 接線完整保留（Wave A `aced662` 不破）
- [x] Mac pytest test_analyst_agent_unit.py：22/22 ✅
- [x] 擴展回歸（6 檔）：146/146 ✅
- [x] Keyword 廣度回歸（analyst|pattern|losses|experiment_ledger）：166/166 ✅
- [x] BWD-compat invariant 驗證（`is` identity / class attr alias / staticmethod delegator）
- [x] 0 production behavior change（純位置 refactor，無邏輯變動）

---

## 6. Operator 後續

- 本 ticket 為 worktree pattern，**不 commit**（per spec Step 5）。
- §九 singleton 表 / §九 文件大小規則無變動，CLAUDE.md 無需同步。
- 後續若 `analyst_agent.py` 再次膨脹接近 800，下一個自然抽出單位為 **L2 pattern analysis**（`_ai_pattern_analysis` + `_statistical_pattern_analysis` ≈ 130 LOC，可抽至 `analyst_l2_pattern.py`）。

— PA Project Architect, 2026-04-28
