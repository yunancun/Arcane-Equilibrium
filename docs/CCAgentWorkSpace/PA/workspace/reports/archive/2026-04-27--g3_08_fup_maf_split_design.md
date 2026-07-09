# PA RFC — G3-08-FUP-MAF-SPLIT P1 · ScoutAgent Extraction

- **Date**：2026-04-27 CEST
- **Author**：PA (Project Architect)
- **Tier / Ticket**：G3-08-FUP-MAF-SPLIT (P1)
- **HEAD baseline**：`9e21a7f7`
- **Trigger**：`multi_agent_framework.py` 1190 LOC，`§九` 1200 hard cap 僅 10 LOC 餘裕；G3-08 Phase 4 已完成 (`b67b0a8`)，下一個觸該檔的 PR 前必拆。
- **Pattern reference**：`6fac0ca` (strategist split, Method A) + `73c1f3d` (cost_tracker split, Method A)
- **Status**：Design DONE — 待 PM approve → 派 E1（單 sub-agent 寫碼）

---

## 1. 背景與動機

### 1.1 觸發條件
- `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py` 1190 LOC
- §七 800 警告線早已逾越；§九 1200 硬上限剩 **10 LOC 餘裕**
- G3-08 Phase 4 已陸續加 `get_scout_snapshot` (24 LOC) + `record_scan` (15 LOC) + 3 hook + 雙語注釋；任何下個 PR (例如 Phase 5 Layer 2 推理 hook) 必撞硬牆
- PA G3-08 Phase 4 RFC §5.1 已預告：拆 ScoutAgent (~190 LOC) → `app/scout_agent.py`，與 Strategist (`6fac0ca`) / cost_tracker (`73c1f3d`) 同 Method A

### 1.2 已驗證 Sibling Pattern
- **`6fac0ca`** (strategist 1200→792 + 3 sibling)：Method A — 16 method 從主檔搬到 3 sibling，主檔保留 1-line delegator + `noqa: F401` re-export 區塊。下游 28 檔 / test 0 修改通過。
- **`73c1f3d`** (cost_tracker 930→540 + 3 sibling)：同 Method A，14 method 委派；test patch path 升級 4 site (因 `_invalidate_h_state_async` import 隨之遷出)。本 RFC 採對稱簡化版 (見 §6)。

### 1.3 上層 RFC 銜接
- PA G3-08 Phase 4 5-Agent RFC `2026-04-27--g3_08_phase4_5agent_design_rfc.md` §5.1 列舉 5 agent 切割面已含 ScoutAgent；本 P1 只執行其中 Scout 一塊（其他 4 agent 已就地落 hook，不需要拆檔）
- E1 Phase 4 Sub-task 4-5 報告 `2026-04-27--g3_08_phase4_5agent_design_rfc.md` 不存在（`b67b0a8` commit 直接落地 `multi_agent_framework.py`）；本 RFC 補上 Scout 抽出步驟。

---

## 2. 切割面設計

### 2.1 目標檔案配置

| File | 變更 | LOC（估計） | 內容 |
|---|---|---|---|
| `app/multi_agent_framework.py` | 主檔瘦身 | **1190 → ~990** | enum + dataclass + MessageBus + Conductor + arbitration + AgentInfo + 16-line re-export 區塊 + ScoutAgent class delegator (見 §3) |
| `app/scout_agent.py` | **NEW** | ~210 | ScoutConfig + ScoutAgent class (full body) + 雙語 MODULE_NOTE |
| `app/strategy_wiring.py` | 1 line import 升級 | 0 淨變 | `from .multi_agent_framework import ScoutAgent, MessageBus, ScoutConfig` → `from .scout_agent import ScoutAgent, ScoutConfig` (`MessageBus` 留 maf) |
| `app/scout_routes.py` | **0 改動**（透過 maf re-export） | 0 | 現 import 維持 `from .multi_agent_framework import (..., ScoutAgent, ...)` 透過 §3 re-export 解析 |

### 2.2 切割邊界（要搬到 `scout_agent.py` 的內容）

主檔 multi_agent_framework.py 第 369–613 行（Scout block 共 245 LOC）：

| Line range | 元件 | 動作 |
|---|---|---|
| 369–381 | `ScoutConfig` dataclass | **MOVE** to scout_agent.py |
| 383 | `from .base_agent import BaseAgent` | **MOVE** (主檔不再需要 BaseAgent) |
| 386–612 | `class ScoutAgent(BaseAgent)` | **MOVE**（含 produce_intel / produce_event_alert / record_scan / get_recent_intel / get_recent_alerts / get_stats / get_scout_snapshot 7 method） |
| 39–44 (import) | `from .h_state_invalidator import invalidate_async as _invalidate_h_state_async` | **MOVE**（隨 produce_intel / produce_event_alert / record_scan 三 hook 遷出） |

### 2.3 主檔保留（不動）

- 第 1–46 行：MODULE_NOTE + future imports + logging + uuid + threading（**保留**：MessageBus / Conductor / arbitrate_conflict / dataclasses 全用得到）
- 第 47–356 行：enums + 5 dataclasses (AgentMessage / IntelObject / EventAlert / TradeIntent / RiskVerdict) + VALID_ROUTES + MessageBus class
- 第 615–693 行：ArbitrationResult + arbitrate_conflict
- 第 696–721 行：AgentInfo dataclass
- 第 724–1190 行：Conductor class (full)

### 2.4 Sibling 檔內 imports（精確）

```python
# scout_agent.py imports
from __future__ import annotations
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from .base_agent import BaseAgent
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async
from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    DataQualityLevel,
    EventAlert,
    IntelObject,
    MessageBus,
    MessageType,
    SentimentScore,
)

logger = logging.getLogger(__name__)  # logging import too
```

依賴方向：`scout_agent.py → multi_agent_framework.py`（單向，不會循環）。
注意：MessageBus 不可以遷出，Conductor 等用得到 + scout_routes 等也直接 import maf。

---

## 3. 主檔 Re-export 區塊（鏡 strategist_agent.py:96–125）

主檔 `multi_agent_framework.py` 在 ScoutAgent 原位置（第 369 行區段），用以下 re-export 區塊取代搬出的整段 245 LOC：

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
from .scout_agent import (  # noqa: F401 — re-export for backward compatibility
    ScoutAgent,
    ScoutConfig,
)
```

**關鍵規範**（鏡 `6fac0ca` 模式）：
- `noqa: F401` 必加（lint 不會誤報未用）
- 區塊位置 = 原 ScoutAgent class 所在區段（保留 §4 標題作 docstring 錨點）
- 不需要做進一步 1-line delegator（不像 strategist 16 method；此處是搬整個 class，re-export 即足）

---

## 4. `strategy_wiring.py` 升級

### 4.1 現況（line 110-148）

```python
# Line 110-112
# ── Scout Agent + Message Bus (T2.07: Plan A2 — ScoutAgent as OpenClaw local proxy) ──
# Scout 代理 + 消息总线（T2.07：方案 A2 — ScoutAgent 作为 OpenClaw 本地代理）
from .multi_agent_framework import ScoutAgent, MessageBus, ScoutConfig
```

### 4.2 升級後（推薦但不強制；§3 re-export 可保證 0 修改）

```python
# Line 110-112 升級為 canonical 直接 import（避免未來 IDE auto-import 困惑）
from .multi_agent_framework import MessageBus  # noqa: keep MessageBus from maf
from .scout_agent import ScoutAgent, ScoutConfig
```

### 4.3 決策建議
**0 修改 strategy_wiring.py** — `§3` 的 `noqa: F401` re-export block 已經保證所有 `from .multi_agent_framework import ScoutAgent` 路徑可用。E1 不必動 strategy_wiring.py 也可以通過全測試。

理由：
1. 鏡 `6fac0ca` strategist 的處理 — strategist split 後 strategy_wiring.py 並未升級 import
2. 減少改動 surface (E1 改的檔越少 → E2 review 越快)
3. canonical import 升級可作為下個 cleanup wave 順手做（FUP-MAF-IMPORT-CLEANUP P3）

---

## 5. 105 個 ScoutAgent test references — 0 修改驗證

### 5.1 6 個 test 檔列舉

| Test file | ScoutAgent refs | 修改需求 |
|---|---|---|
| `tests/test_scout_integration.py` | ~30 (含 ScoutConfig + ScoutAgent ctor / lifecycle / produce_intel / produce_event_alert) | **0** — 透過 §3 re-export 解析 |
| `tests/test_scout_audit_wiring.py` | ~15 (audit_callback wiring 測試) | **0** |
| `tests/test_multi_agent_framework.py` | ~25 (ScoutAgent + Conductor + MessageBus 整合) | **0** |
| `tests/test_h_state_query_handler.py` | ~15 (含 `_FakeScout` fixture pattern + `get_scout_snapshot` 測試) | **0** — 但 `from .strategy_wiring import SCOUT_AGENT` 路徑不變 |
| `tests/test_strategist_agent.py` | ~10 (Strategist 端用 ScoutAgent 注入 IntelObject) | **0** |
| `tests/test_batch7_conductor_strategist.py` | ~10 (Conductor + Strategist 整合，借用 Scout 為 producer) | **0** |

### 5.2 為什麼能 0 修改

`6fac0ca` 同樣模式驗證過：strategist split 16 method 移出，下游所有 `app.strategist_agent.<symbol>` patch path 透過 `noqa: F401` re-export 解析，0 test 修改。

本次 ScoutAgent 為 class 級別整搬，更乾淨：
- `from app.multi_agent_framework import ScoutAgent` → re-export 解析 → 拿到的 class 物件即新 `scout_agent.ScoutAgent`
- `app.multi_agent_framework.ScoutAgent` (monkey-patch path) → re-export 也解析 (Python import 機制保證 module attr 與 import statement 結果 identity 一致)

### 5.3 必驗 test list（E1 跑這 6 個 + E4 全套 regression）
- `pytest tests/test_scout_integration.py -v`
- `pytest tests/test_scout_audit_wiring.py -v`
- `pytest tests/test_multi_agent_framework.py -v`
- `pytest tests/test_h_state_query_handler.py -v`
- `pytest tests/test_strategist_agent.py -v`
- `pytest tests/test_batch7_conductor_strategist.py -v`

預期：6 套全綠 / 0 fail。Mac dev-only env 下若 fastapi/integration 缺失導致部分 test deselect，per CLAUDE.md §七 Mac dev-only #2，**屬預期**，不算 fail。

---

## 6. LOC 預算對照

### 6.1 主檔縮減

| 區段 | 動作 | 行數變動 |
|---|---|---|
| Lines 39–44 (`_invalidate_h_state_async` import) | MOVE → scout_agent.py | -6 |
| Lines 369–381 (ScoutConfig dataclass) | MOVE | -13 |
| Line 383 (`from .base_agent import BaseAgent`) | MOVE | -1 (但 strategist_agent 已 import 故不影響全 repo) |
| Lines 386–612 (ScoutAgent class) | MOVE | -227 |
| Re-export 區塊（§3） | INSERT | +14 |

**主檔預期**：1190 - 6 - 13 - 1 - 227 + 14 = **957 LOC**（餘裕 243 LOC，遠超 P1 ≥190 要求）

### 6.2 sibling 預算

| 內容 | LOC |
|---|---|
| MODULE_NOTE 雙語 docstring | 24 |
| imports (含分組) | 18 |
| ScoutConfig dataclass | 13 |
| ScoutAgent class (~227 原行 + 已含雙語) | 227 |
| `logger = logging.getLogger(__name__)` + 空行分隔 | 4 |
| **預期 scout_agent.py 總 LOC** | **~286 LOC** |

### 6.3 LOC drift 預留（per Strategist 教訓）

`6fac0ca` Strategist split 估 710，實際 792（+82, +11.5%）原因 = 雙語注釋 + class boundary docstring 漏估。本 RFC 已預留：
- 主檔 957 → 餘裕 243（即使 +20% drift，仍 < 1200 hard cap，且 < 800 warning）
- sibling 286 → 即使 +20% drift = ~343 LOC，仍 < 800 warning
- **驗收條件**（§9.1）放寬至 ≤ 1010（per prompt 要求 ≤1010），給 +5% drift 緩衝。

### 6.4 Sub-task 對主檔不再加 LOC 的承諾

本 P1 僅做 location-only refactor，0 行 production behavior 變更，因此**不會**像 Phase 4 Sub-task 4-1 (Strategist) 那樣引入 +37 LOC method。E1 嚴禁順手加新 fn / 改 signature / 改 docstring 主軸（per Hard rule §11.4）。

---

## 7. 風險識別

### 7.1 IDE auto-import 困惑（中）
**現象**：split 後同一 class `ScoutAgent` 同時可從 maf re-export + scout_agent canonical import 拿到。VS Code / PyCharm auto-import 可能優先選 maf 路徑（既有檔，先建索引）。
**緩解**：`§3` re-export 已用 `noqa: F401` 標明這是 BWD compat，不是 canonical；新代碼 IDE 任選，runtime 行為一致；下個 cleanup wave 排 FUP-MAF-IMPORT-CLEANUP 統一升級至 `from .scout_agent import` 為 canonical。
**E2 重點**：不在本 PR 強推 import 升級；只驗 6 套 test 全綠。

### 7.2 雙語 docstring drift（低）
**現象**：MODULE_NOTE / docstring / inline comment 中英對照偏移。
**緩解**：sibling MODULE_NOTE 直接複製主檔當前 Scout block 的雙語注釋（line 39–44 + line 369–442 + line 590–612）逐句搬，不重寫；E2 對照原檔 grep -A 對齊。
**E2 重點**：抽 3 段（class docstring / produce_intel docstring / get_scout_snapshot docstring）對照前後 diff，確認逐字未改。

### 7.3 LOC drift +N%（低，已含 §6.3 緩衝）
**現象**：`6fac0ca` 估 710 / 實際 792 (+11.5%) 教訓。
**緩解**：§6.3 已預留 ≥20% drift 後仍達標；驗收 §9.1 用 ≤1010 而非 990 (即 +5% buffer)。

### 7.4 PYI / IDE breakage（低）
**現象**：IDE 對 module attr 可見性靠 import statement，re-export 模式對部分老舊 IDE 索引器可能失效。
**緩解**：`6fac0ca` 已驗證下游 28 檔 + 6 test suite 全綠 — 即現代 Python import 機制 + Pyright/Pylance 完全支援 `noqa: F401` re-export。
**E2 重點**：不驗（已 sibling 驗過 2 次）。

### 7.5 多 CC session memory race（極低，per memory `project_multi_session_memory_race`）
**現象**：本 RFC 寫入時若 Mac/Linux 隔壁 session 同時改 PA memory.md 會被 revert。
**緩解**：本 RFC 寫到 reports/ 而非 memory.md；§10 完成序列規定 PA memory append 在 PM 派單之後，避免 race。

---

## 8. 派發計劃

### 8.1 並行性分析
**非可並行**：本任務動 multi_agent_framework.py 主檔 + 新建 scout_agent.py，工作面集中，**派 1 個 E1** 在 1 worktree 完成。

### 8.2 工時估算
- 切割檔案 + 雙語 docstring 搬：30-45 min
- 6 套 test 跑通：5-10 min
- E1 報告：10 min
- **合計 1 E1 sub-agent**, ~1 hour

### 8.3 強制鏈
`PA RFC (本檔)` → `PM approve` → `@E1` 落地 → `@E2` review (重點：§7.2 雙語對照 + §9 acceptance) → `@E4` 全套 regression (Mac pytest + Linux cargo) → `PM Sign-off`

### 8.4 跳過項
- 不派 `@FA`（純 refactor 0 邏輯）
- 不派 `@QC`（無策略改動）
- 不派 `@CC` 16 原則 audit（純 location-only，0 硬邊界）
- 不派 `@MIT`（無 ML pipeline / DB schema 變動）
- 不派 `@E5` (≥3 task 才強制；本 P1 為單檔切割)

---

## 9. 驗收標準（PM Sign-off 條件）

### 9.1 LOC
- [ ] `wc -l multi_agent_framework.py` ≤ **1010**（≥180 LOC headroom）
- [ ] `wc -l scout_agent.py` ≤ **400**（含 +20% drift 上限）

### 9.2 測試
- [ ] Mac pytest 6 套 全綠：test_scout_integration / test_scout_audit_wiring / test_multi_agent_framework / test_h_state_query_handler / test_strategist_agent / test_batch7_conductor_strategist
- [ ] Linux cargo `cargo test --release -p openclaw_engine --lib` baseline **2252 / 0 不變**（純 Python refactor）
- [ ] Linux pytest multi_agent_framework 既有 58 case 全 pass + scout_agent 創 N 個新（**選項 A：0 新測，純 refactor 不需要新測**；**選項 B：補 1 個 smoke test 驗 `from scout_agent import ScoutAgent` 直接路徑可用** — 推薦選 A，per `73c1f3d` 模式無新測）

### 9.3 行為不變
- [ ] 0 production behavior 變更（grep diff `git diff --stat 9e21a7f7..HEAD` 應只見 multi_agent_framework.py 行刪除 + scout_agent.py NEW + (optional) strategy_wiring.py 1-line import）
- [ ] H state cache invalidate hint emit 點 (`agent.scout.intel_produced` / `agent.scout.alert_produced` / `agent.scout.scan_completed`) 0 變動
- [ ] `get_scout_snapshot` schema 5 fields 0 變動

### 9.4 治理
- [ ] 0 硬邊界觸碰（live_execution_allowed / max_retries / system_mode 全未動）
- [ ] 雙語 MODULE_NOTE / docstring 0 drift（E2 必驗 §7.2）
- [ ] §九 singleton 表 0 新增（無新 module-level 全局可變狀態）

---

## 10. 完成序列

1. **PA**（本檔）寫至 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_fup_maf_split_design.md` ✅
2. **PM** approve / reject（建議 approve — 風險全 §7 標 中/低，模式驗證 2 次）
3. **E1** 落地（用 §11 prompt template 直接派發）
4. **E2** review (重點 §7.2 + §9)
5. **E4** regression (§9.2)
6. **PM Sign-off** + commit + push
7. **PA memory.md** append（PM Sign-off 後，避免 multi-session race）

---

## 11. E1 Prompt Template（直接複製給 sub-agent）

```
G3-08-FUP-MAF-SPLIT P1 — 落地 ScoutAgent 抽出

## 任務
將 multi_agent_framework.py 中 ScoutAgent + ScoutConfig 整搬到新檔 scout_agent.py，
維持 0 production behavior 變更 + 0 test 修改 (透過 noqa: F401 re-export)。

## RFC 路徑
srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_fup_maf_split_design.md

## File paths
- 主檔（修改）：srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py
- NEW：srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_agent.py
- strategy_wiring.py：**不動**（per RFC §4.3）

## Cut points（精確）
從 multi_agent_framework.py 搬出的內容：
1. Lines 39–44：`from .h_state_invalidator import invalidate_async as _invalidate_h_state_async` import block (含雙語注釋)
2. Lines 369–381：`ScoutConfig` dataclass + 雙語 comment header「## 4. Scout Agent (EX-06 §3)」上方 5 行
3. Line 383：`from .base_agent import BaseAgent`
4. Lines 386–612：`class ScoutAgent(BaseAgent)` 整類

scout_agent.py 內 imports（精確 list per RFC §2.4）：
- threading / time / uuid / dataclasses / enum / typing / logging
- `.base_agent.BaseAgent`
- `.h_state_invalidator.invalidate_async as _invalidate_h_state_async`
- `.multi_agent_framework`：AgentMessage / AgentRole / DataQualityLevel /
  EventAlert / IntelObject / MessageBus / MessageType / SentimentScore

## Re-export block（在主檔原 ScoutAgent 區位置插入，per RFC §3）
```python
# ─────────────────────────────────────────────
# 4. Scout Agent (EX-06 §3) — moved to scout_agent.py for §九 LOC budget
# ─────────────────────────────────────────────
# G3-08-FUP-MAF-SPLIT: ScoutConfig + ScoutAgent moved to dedicated scout_agent.py
# (per PA RFC). Re-export so existing call-sites continue to work via
# ``from .multi_agent_framework import ScoutAgent, ScoutConfig`` path.
# G3-08-FUP-MAF-SPLIT：ScoutConfig + ScoutAgent 遷至 scout_agent.py（per PA RFC）。
# 透過 re-export 維持既有呼叫點 ``from .multi_agent_framework import ScoutAgent``
# 路徑可用。
from .scout_agent import (  # noqa: F401 — re-export for backward compatibility
    ScoutAgent,
    ScoutConfig,
)
```

## Sibling 雙語 MODULE_NOTE（scout_agent.py 開頭）
直接複製主檔當前 Scout 區段的雙語 docstring（line 369–442 + line 590–612），
不重寫。MODULE_NOTE 加一句：
- 中：「G3-08-FUP-MAF-SPLIT 從 multi_agent_framework.py 抽出，維持原有所有
  接口；透過主檔 noqa: F401 re-export 保證向後相容。」
- 英：「Extracted from multi_agent_framework.py per G3-08-FUP-MAF-SPLIT;
  all interfaces preserved; backward compatibility via noqa: F401 re-export
  in main file.」

## Test files to verify (must pass on Mac)
1. tests/test_scout_integration.py
2. tests/test_scout_audit_wiring.py
3. tests/test_multi_agent_framework.py
4. tests/test_h_state_query_handler.py
5. tests/test_strategist_agent.py
6. tests/test_batch7_conductor_strategist.py

## Acceptance criteria
- multi_agent_framework.py LOC ≤ 1010（per RFC §9.1）
- scout_agent.py LOC ≤ 400
- 上述 6 套 pytest 全綠（Mac dev-only fastapi 缺失導致 deselect 不算 fail）
- cargo lib +0（純 Python 變更，預期 baseline 2252/0 不變 — 留 E4 在 Linux 跑）
- 0 strategy_wiring.py 改動（per RFC §4.3，順手不動）
- 0 test 改動
- 0 production behavior 改動

## Hard rules（per E1 規範）
- 不順手加 method / 改 signature / 改 docstring 主軸
- 不動 Rust / TOML / helper_scripts / TODO.md / CLAUDE.md / memory/*（除 E1 自己 memory.md）
- 雙語注釋每處保留（CLAUDE.md §七 強制）
- 不擅自升 strategy_wiring.py import 為 canonical（留 FUP cleanup wave 做）

## 提交
單 commit 含 2 file change（maf 主檔 + scout_agent.py NEW），訊息：
```
refactor(scout): G3-08-FUP-MAF-SPLIT — ScoutAgent extracted to scout_agent.py

multi_agent_framework.py 1190 → ~957 LOC (target ≤1010 per PA RFC §9.1)
scout_agent.py NEW (~286 LOC).

Pure location-only refactor per PA RFC
docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_fup_maf_split_design.md
- 0 production behavior change
- 0 test modification (BWD compat via noqa: F401 re-export in maf)
- 0 strategy_wiring.py change (per RFC §4.3)
- 6 test suites green: test_scout_integration / test_scout_audit_wiring /
  test_multi_agent_framework / test_h_state_query_handler /
  test_strategist_agent / test_batch7_conductor_strategist

Pattern: mirrors 6fac0ca (strategist split) + 73c1f3d (cost_tracker split).
H state cache invalidate hints (intel/alert/scan) preserved bit-identically.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

不要 push（per CLAUDE.md §七 強制鏈：commit 後等 E2 + E4 + PM 統一 push）。
報告寫到 srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-27--g3_08_fup_maf_split.md
```

---

## 12. E2 重點審查 3 點

1. **§7.2 雙語 docstring drift** — diff 對照搬出前 (multi_agent_framework.py:39-44, 369-612) vs 搬入後 (scout_agent.py)，確認逐字未改；MODULE_NOTE 唯一新加 1 句說明來源（中 + 英各 1 行）。
2. **§9.3 行為不變** — `git diff --stat` 應只見 2 file 變動；invalidate hint 三 emit 點 (`agent.scout.intel_produced` / `agent.scout.alert_produced` / `agent.scout.scan_completed`) 字串 0 變動；`get_scout_snapshot` 5-field schema (intel_produced / alerts_produced / scans_completed / intel_log_size / alert_log_size) 0 變動。
3. **§3 re-export block 位置正確** — `noqa: F401` 必加；ScoutAgent + ScoutConfig 兩個都 re-export；其他 sibling 從 maf import 的符號 (AgentRole / IntelObject 等) 不應誤搬。

---

## 13. 副作用清單（per PA profile §41-46）

對每個改動問：
1. **其他模塊是否 import 這個檔？** — 是。`scout_routes.py` (3 import) / `strategist_models.py` (1 import) / `executor_agent.py` (1 import) / `base_agent.py` (1 TYPE_CHECKING import) / `strategist_cognitive.py` (1 import) / `strategy_wiring.py` (3 places) / `h_state_query_handler.py` (1 SCOUT_AGENT path) / `ai_service.py` (docstring only) — **全部不需修改**（透過 §3 re-export 解析）。
2. **改動函數在哪些 test mock？** — `tests/test_h_state_query_handler.py` 用 `_FakeStrategist` / `_FakeScout` fixture pattern，不直接 patch ScoutAgent class 內部；其他 5 套用真 ScoutAgent ctor 整合測試。**0 mock 路徑斷裂風險**。
3. **是否涉及 asyncio/threading 混用邊界？** — `_invalidate_h_state_async` 為 fire-and-forget daemon thread + asyncio.new_event_loop pattern (CLAUDE.md §九 singleton 表 `_H_STATE_INVALIDATOR` 區段)。本 split 0 動 invalidator 內部，只搬 import 與 emit 點 (3 處 `_invalidate_h_state_async("agent.scout.*")` 字面字串)。**0 線程模型變動**。
4. **是否改動 API response schema？** — 否。`get_scout_snapshot` 5-field dict 0 動；scout_routes.py REST endpoint 0 動。
5. **是否觸 RustEngine ↔ Python IPC schema？** — 否。h_state_query_handler.py 對 Rust 的 schema 0 動 (Phase 1A `AgentState.stats: HashMap<String, i64>` slot 已備、5-field dict 0 變)；本 split 純 Python 內部 module 邊界。

---

## 14. 治理對照（CLAUDE.md §二 + DOC-08 §12）

| 項 | 狀態 | 證據 |
|---|---|---|
| 16 根原則 | 0 觸碰 | 純 location refactor |
| 硬邊界（§四） | 0 觸碰 | grep `live_execution_allowed / max_retries / system_mode` 0 hit |
| DOC-08 §12 9 條安全不變量 | 0 影響 | ScoutAgent 不在 lease / order submission / authorization path |
| §七 跨平台 | ✅ | 0 路徑硬編碼新增；0 systemd 依賴 |
| §七 雙語注釋 | ✅ | sibling 直接搬主檔現有雙語段 |
| §九 文件大小 | ✅ | 1190→957 + sibling 286，均 < 800 警告線 |
| §九 singleton 登記 | ✅ | 0 新 singleton（沿用 Phase 1C `_H_STATE_INVALIDATOR`） |
| §九 模塊依賴方向 | ✅ | scout_agent → multi_agent_framework 單向 |
| §九 monkey-patch 安全 | ✅ | re-export 模式保證 `app.multi_agent_framework.ScoutAgent` patch path 仍解析 |

評級：**A**（16/16 + 9/9 + 0 硬邊界）
判定：**Approve**

---

## 15. PA Memory append 草稿（PM Sign-off 後寫）

```
- [G3-08-FUP-MAF-SPLIT (2026-04-27)](archive/2026-04-27--g3_08_fup_maf_split.md)
  multi_agent_framework.py 1190 → ~957 + scout_agent.py NEW (~286)；ScoutAgent
  整類抽出；0 test / 0 strategy_wiring.py / 0 production behavior 改動；透過
  noqa: F401 re-export 維持 BWD compat；模式 = 6fac0ca strategist + 73c1f3d
  cost_tracker；6 test suite 全綠 + cargo lib 不變。
```

---

**RFC DONE**：等 PM approve → 派 E1（per §11 prompt template）

> PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_fup_maf_split_design.md
