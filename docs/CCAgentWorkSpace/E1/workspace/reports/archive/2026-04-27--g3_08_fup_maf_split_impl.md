# E1 報告 — G3-08-FUP-MAF-SPLIT P1 落地

- **Date**：2026-04-27 CEST
- **Author**：E1（Backend Developer）
- **PA RFC**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_fup_maf_split_design.md`
- **HEAD baseline**：`9e21a7f7` → **commit `b8b5150`**
- **Status**：DONE — 待 E2 review → E4 regression → PM Sign-off

---

## 1. 任務摘要

**Operator 意圖白話重述**：將 `multi_agent_framework.py`（1190 LOC，§九 1200 硬上限剩 10 LOC）中的 `ScoutAgent` + `ScoutConfig` 整類抽到新檔 `scout_agent.py`，**0 production behavior 變更**、**0 test 改動**、**0 `strategy_wiring.py` 改動**，透過主檔 re-export 維持向後相容。模式對齊 `6fac0ca` (strategist split) 與 `73c1f3d` (cost_tracker split)。

**完成狀態**：✅ 全部達成 + 處理一個 PA RFC 未預見的 cycle-import 邊界（PEP 562 lazy `__getattr__` 解之，見 §5）。

---

## 2. 修改清單

| Path | 動作 | 行數 | 說明 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py` | 修改 | 1190 → **966**（-224） | 移除 6-line `_invalidate_h_state_async` import block + 13-line ScoutConfig + 1-line `BaseAgent` import + 227-line ScoutAgent class；插入 25-line PEP 562 `__getattr__` lazy re-export block |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_agent.py` | NEW | **297** | MODULE_NOTE 雙語 docstring + imports + ScoutConfig + ScoutAgent class（內容逐字搬出，0 邏輯改動） |

**0 改動**：`strategy_wiring.py` / `scout_routes.py` / `executor_agent.py` / `strategist_agent.py` / `strategist_models.py` / `base_agent.py` / `analyst_agent.py` / `guardian_agent.py` / `ai_service_dispatch.py` / `strategist_edge_eval.py` / `strategist_cognitive.py` / `ai_service.py` / 6 套 test 全 0 改動。

---

## 3. 關鍵 diff

### 3.1 主檔 maf 移除（39-44 + 369-612）

舊 `multi_agent_framework.py` line 39-44（`_invalidate_h_state_async` import）整段隨 ScoutAgent 遷出。

舊 line 369-612（§4 Scout Agent block 共 244 行）= ScoutConfig dataclass + `from .base_agent import BaseAgent` + `class ScoutAgent(BaseAgent)` 整類，全搬至 `scout_agent.py`。

### 3.2 主檔 maf 新增 re-export（line 362-385）

```python
# ─────────────────────────────────────────────
# 4. Scout Agent (EX-06 §3) — moved to scout_agent.py for §九 LOC budget
# ─────────────────────────────────────────────
# G3-08-FUP-MAF-SPLIT: ScoutConfig + ScoutAgent moved to dedicated scout_agent.py
# (per PA RFC). Re-export so existing call-sites (test files, scout_routes.py,
# strategy_wiring.py legacy callers, ai_service.py docstring refs) continue to
# work via ``from .multi_agent_framework import ScoutAgent, ScoutConfig`` path.
# G3-08-FUP-MAF-SPLIT：ScoutConfig + ScoutAgent 遷至 scout_agent.py（per PA RFC）。
# 透過 re-export 維持既有呼叫點（test、scout_routes、strategy_wiring 舊 caller、
# ai_service docstring）的 ``from .multi_agent_framework import ScoutAgent`` 路徑可用。
#
# 為避免「scout_agent → maf → scout_agent」循環 import（scout_agent 在 module
# load 期需 from .multi_agent_framework import 諸 enum/dataclass），這裡用 PEP 562
# module-level ``__getattr__`` 延遲解析：當且僅當外部首次 attribute lookup
# (``maf.ScoutAgent`` / ``from maf import ScoutAgent``) 時才 import scout_agent，
# 此時 maf module body 已執行完，所有 enum/dataclass 全部 ready。
# To avoid the ``scout_agent -> maf -> scout_agent`` circular import (scout_agent
# needs maf's enums/dataclasses at module load time), we use PEP 562 module-level
# ``__getattr__`` for lazy resolution: scout_agent is imported only on first
# attribute lookup, by which point maf's module body has fully executed.
def __getattr__(name: str):  # noqa: D401 — PEP 562 lazy re-export
    if name in ("ScoutAgent", "ScoutConfig"):
        from . import scout_agent as _scout_module  # local import breaks cycle
        value = getattr(_scout_module, name)
        globals()[name] = value  # cache so subsequent lookups skip __getattr__
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### 3.3 sibling scout_agent.py（架構截錄）

- MODULE_NOTE 雙語（中 + 英），補一句「Extracted from multi_agent_framework.py per G3-08-FUP-MAF-SPLIT;...」per PA RFC §11
- imports：`logging` + `dataclasses.dataclass` + `typing.{Any, Callable, Dict, List, Optional}` + `.base_agent.BaseAgent` + `.h_state_invalidator.invalidate_async as _invalidate_h_state_async` + `.multi_agent_framework.{AgentMessage, AgentRole, DataQualityLevel, EventAlert, IntelObject, MessageBus, MessageType, SentimentScore}`
- `@dataclass class ScoutConfig:` — 5 字段，逐字搬
- `class ScoutAgent(BaseAgent):` — 含 7 method (`__init__` / `produce_intel` / `produce_event_alert` / `record_scan` / `get_recent_intel` / `get_recent_alerts` / `get_stats` / `get_scout_snapshot`)，逐字搬，雙語注釋零 drift
- 3 個 `_invalidate_h_state_async("agent.scout.{intel,alert,scan}_*")` emit 點字串保留 bit-identical
- `get_scout_snapshot` 5-field schema 保留 bit-identical (`intel_produced` / `alerts_produced` / `scans_completed` / `intel_log_size` / `alert_log_size`)

---

## 4. 治理對照（CLAUDE.md §二 + DOC-08）

| 項 | 狀態 | 證據 |
|---|---|---|
| 16 根原則 | 0 觸碰 | 純 location refactor，0 邏輯動 |
| 硬邊界（§四） | 0 觸碰 | grep `live_execution_allowed / max_retries / system_mode / execution_authority` 0 hit |
| §七 跨平台 | ✅ | 0 路徑硬編碼新增；0 systemd 依賴 |
| §七 雙語注釋 | ✅ | sibling 直接搬主檔現有雙語段；MODULE_NOTE 補來源說明 1 句中 + 1 句英 |
| §九 文件大小 | ✅ | maf 1190 → **966** (≤1010 ✓ 餘裕 234)；scout_agent 297 (≤400 ✓) |
| §九 singleton 登記 | ✅ | 0 新 singleton |
| §九 模塊依賴方向 | ✅ | scout_agent → maf 單向（runtime call 期）；maf → scout_agent 走 lazy `__getattr__`，無 module-load-time 循環 |
| §九 monkey-patch 安全 | ✅ | `maf.ScoutAgent is scout_agent.ScoutAgent` identity 驗證通過（test patch path 仍解析） |
| 雙語 docstring drift | ✅ | 直接逐字搬 maf line 369-612 進 scout_agent.py，0 重寫 |

評級：A

---

## 5. 不確定之處 / 偏離 PA RFC 處

### 5.1 PA RFC §3 / §11 預設 maf eager `from .scout_agent import ScoutAgent, ScoutConfig` — 實際發生循環 import

**現象**：PA RFC §3 與 §11 prompt template 給的 re-export 範例是：
```python
from .scout_agent import (  # noqa: F401 — re-export for backward compatibility
    ScoutAgent,
    ScoutConfig,
)
```

實測 → `ImportError: cannot import name 'ScoutAgent' from partially initialized module ... (most likely due to a circular import)`。

**根因**：`scout_agent.py` 在 module-load 期需 `from .multi_agent_framework import {AgentMessage, AgentRole, ...}`（class definition `class ScoutAgent(BaseAgent)` 與 type annotation 都要這些 symbol），而 maf 一旦 eager `from .scout_agent import ...` → 兩 module 互相 wait → 失敗。

PA RFC §3 比照 strategist 模式 — 但 strategist split 中「sibling 是被 strategist_agent re-export」**不是** maf re-export，方向相反，沒這個問題。本任務 scout_agent 與 maf 的關係更類似「maf 是父，scout_agent 是子」要回頭 re-export 子 → 必有 cycle。

**處置**：採用 PEP 562 `module.__getattr__`（Python 3.7+ 標準；無外部依賴）做 lazy re-export，外部首次 `from maf import ScoutAgent` 時才 import scout_agent，此時 maf body 已 evaluate 完。Identity check 通過：

```python
from app.scout_agent import ScoutAgent
from app.multi_agent_framework import ScoutAgent as MafScoutAgent
assert ScoutAgent is MafScoutAgent  # ✅ PASS
```

**範圍判斷**：屬於「PA RFC 預設方案 + 解決一個 RFC 未預見的技術障礙」，**不擴大 scope**（仍為 location-only refactor，0 邏輯動，6 套 test 全綠驗證 BWD 100% 兼容）。E2 重點審查：cycle-import 解法是否被認可，或建議改用其他模式（例如 maf 內 `import scout_agent` 後 `ScoutAgent = scout_agent.ScoutAgent`，但這仍會循環因為 import statement 本身觸發載入）。

### 5.2 跨平台風險

無。純 Python module 內部重組，無路徑 / OS / systemd 依賴變動。

### 5.3 測試覆蓋判斷

PA RFC §5.3 指定 6 套 test 全綠 = 充分（含 105 個 ScoutAgent reference）。Mac dev-only 環境下 286 passed / 0 failed / 5 warnings（warnings 為 layer2_cost_tracker `record_ollama_call()` deprecation，與本 refactor 無關，先前已存在）。Linux pytest 同邏輯預期一致；E4 跑 cargo regression 預期 unchanged（純 Python，0 Rust 變動）。

---

## 6. Operator 下一步

1. **E2 審查重點**（per PA RFC §12 + §5.1 偏離）：
   - 雙語 docstring drift：對比 `git show b8b5150 -- ...scout_agent.py` 與 baseline `git show 9e21a7f7:.../multi_agent_framework.py` 的 369-612 段，確認逐字未改
   - 行為不變：3 invalidate hint emit 點字串 (`agent.scout.{intel,alert,scan}_*`) + `get_scout_snapshot` 5-field schema bit-identical
   - PEP 562 lazy `__getattr__` 解法是否認可（vs PA RFC 預設 eager re-export）
   - re-export 區位置正確 + `noqa: F401` 等價說明（這裡用 `# noqa: D401` for `__getattr__` docstring style）
2. **E4 regression**：跑 Linux pytest 同 6 套 + cargo `cargo test --release -p openclaw_engine --lib` 確認 baseline 不變（純 Python，預期 0 Rust 影響）
3. **PM Sign-off + push**（CLAUDE.md §七 強制鏈：E1 → E2 → E4 → QA → PM 統一 push）
4. 已驗證項目（無需 operator 親自跑）：
   - Mac pytest 6 套 286 passed / 0 failed
   - `from maf import ScoutAgent` identity 驗證通過
   - `wc -l` LOC 達標：maf 966 / scout_agent 297
   - `git diff --stat` 確認只 2 file 變動

---

## 7. 後續 follow-up（建議放 backlog）

- **G3-08-FUP-MAF-IMPORT-CLEANUP P3**：將 `strategy_wiring.py:112` / `scout_routes.py:37-46` 的 `from .multi_agent_framework import ScoutAgent, ScoutConfig` 升級為 canonical `from .scout_agent import ScoutAgent, ScoutConfig`，移除 maf 的 `__getattr__` lazy re-export 包袱（可降低 IDE auto-import 困惑、移除 PEP 562 hack）。

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-27--g3_08_fup_maf_split_impl.md`）**
