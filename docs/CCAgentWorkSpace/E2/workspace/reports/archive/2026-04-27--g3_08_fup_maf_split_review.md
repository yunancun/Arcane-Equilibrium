# E2 PR Adversarial Review — G3-08-FUP-MAF-SPLIT (commit `b8b5150`)

- **Date**: 2026-04-27 21:42 UTC
- **Reviewer**: E2
- **Subject**: ScoutAgent extraction from `multi_agent_framework.py` to `scout_agent.py`
- **Base HEAD**: `9e21a7f7`
- **PA RFC**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_fup_maf_split_design.md`
- **E1 Report**: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-27--g3_08_fup_maf_split_impl.md`

---

## 1. 改動範圍

| File | 動作 | LOC delta | Notes |
|---|---|---|---|
| `multi_agent_framework.py` | refactor | 1190 → 966 (-224) | ScoutConfig + ScoutAgent class block 移出，原位置改 PEP 562 `__getattr__` 區塊 |
| `scout_agent.py` | NEW | +297 | ScoutConfig + ScoutAgent class full body + 雙語 MODULE_NOTE |
| `strategy_wiring.py` | 0 改動 | 0 | per RFC §4.3，符合 |
| `scout_routes.py` | 0 改動 | 0 | per RFC §2.1，符合 |
| 6 test files | 0 改動 | 0 | per RFC §5.2，符合 |
| `TODO.md` | 1 條目 status update | +5 / -2 | 範圍外但合理 |

LOC drift vs PA 預估：
- 主檔 1190 → 966（PA 估 957，差 +9）
- scout_agent 297（PA 估 ~210，差 +87，因 docstring/雙語注釋移入完整版而非精簡版）

兩者均在合理範圍。`§七` 800 警告線：scout_agent (297) 通過；maf (966) 仍在 800-1200 警告區（PR 後改善 224 LOC，方向正確）。

---

## 2. 與 PA RFC 的偏離 — 已主動分析

### 2.1 偏離點：PEP 562 lazy re-export 取代 `noqa: F401` eager re-export

**PA RFC §3** 規定：
```python
from .scout_agent import (  # noqa: F401 — re-export for backward compatibility
    ScoutAgent,
    ScoutConfig,
)
```
放在主檔 ScoutAgent 原位置（line 360 區段）。

**E1 實作（commit `b8b5150` line 365–390）**：
```python
def __getattr__(name: str):  # noqa: D401 — PEP 562 lazy re-export
    if name in ("ScoutAgent", "ScoutConfig"):
        from . import scout_agent as _scout_module
        value = getattr(_scout_module, name)
        globals()[name] = value
        return value
    raise AttributeError(...)
```

**E1 偏離理由（report §5.1）**：scout_agent 在 module-load 期需 `from .multi_agent_framework import (AgentMessage, AgentRole, DataQualityLevel, EventAlert, IntelObject, MessageBus, MessageType, SentimentScore)`，若 maf eager 在 line 360 處再 import scout_agent → 循環 import → maf module body 尚未執行完，scout_agent 拿到 partial maf → ImportError。

**E2 對抗驗證**：
1. **循環依賴 confirmed**：scout_agent.py:43-52 確實在 module-load 期需 8 個 maf 內部符號，全部位於 maf 第 1-360 行（enum/dataclass/MessageBus）。若 maf line 360 處嘗試 eager import → Python `from ... import` 機制取得正在 build 的 maf module，partial state 缺後段定義，但實測 scout_agent 需要的全在前段（會通過？）。實測：因 `from .scout_agent import ...` 觸發 scout_agent.py module body → scout_agent 對 maf 做 `from .multi_agent_framework import (...)` → 拿到 maf partial module，所需符號實際已在 maf 前段定義完，**理論上應該成功**。E1 報告稱 ImportError 出現需更精確 reproduce。
2. **更乾淨替代方案**：把 eager `from .scout_agent import ScoutAgent, ScoutConfig` 放在 maf **檔尾**（line 966 後），確保 maf module body 完全執行完才觸發 scout_agent module-load。maf body 從未引用 ScoutAgent class（grep `ScoutAgent\|ScoutConfig` 在 maf 只命中 docstring 文字 + `__getattr__` 條件分支），**bottom-of-file eager import 完全可行**。
3. **PA RFC §3 漏算**：PA 假設 mirror `6fac0ca` (strategist) 模式即可，但 strategist class 留在 strategist_agent.py 且 maf **不** re-export strategist（test 直接 `from app.strategist_agent import StrategistAgent`），故 strategist case 根本沒有 maf-eager-re-export-causes-cycle 場景。本 RFC 將整 class 從 maf 搬出 + 仍要從 maf re-export 回去，是新場景，PA 未充分分析依賴方向。

**結論**：E1 PEP 562 解法 **functionally correct**，6 套 286 tests 全綠。但 **bottom-of-file eager re-export** 是更 idiomatic、無 magic 的替代。當前實作可接受 → LOW 而非 HIGH。

---

## 3. CLAUDE.md §九 8 條 checklist

| Item | 狀態 | Notes |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ PASS | 偏離點已 §2 詳述，functionally equivalent |
| 沒有 except:pass / 靜默吞異常 | ✅ PASS | 0 except 改動 |
| 日誌使用 %s 格式（非 f-string） | ✅ PASS | 0 log call 新增 |
| 新 API 端點有 _require_operator_role() | ✅ N/A | 0 endpoint 新增 |
| except HTTPException: raise 在 except Exception 之前 | ✅ N/A | 0 try/except 新增 |
| detail=str(e) → "Internal server error" | ✅ N/A | 0 HTTPException raise |
| asyncio 路由中沒有 blocking threading.Lock | ✅ PASS | scout_agent 用 `self._lock` (BaseAgent 提供) 與既有同 |
| 沒有私有屬性穿透（._xxx） | ✅ PASS | `_intel_log/_alert_log/_stats/_lock/_audit` 全 ScoutAgent 自身或 BaseAgent 繼承 |

---

## 4. OpenClaw 9 條特殊 checklist

| Item | 狀態 | Notes |
|---|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ PASS | 兩檔 0 命中 |
| 雙語注釋（MODULE_NOTE + docstring + inline） | ✅ PASS | scout_agent 完整中英 MODULE_NOTE，所有 method docstring 雙語 |
| Rust unsafe / unwrap | ✅ N/A | Python only |
| 跨語言 IPC schema 一致 | ✅ PASS | `get_scout_snapshot` 5-field 全 int，與 Rust `HashMap<String, i64>` 對齊（per RFC §2.5），bit-identical 保留 |
| Migration Guard A/B/C | ✅ N/A | 0 SQL change |
| healthcheck 配對（被動等待 TODO） | ✅ N/A | 非被動等待類 TODO |
| Singleton 登記 §九 表 | ⚠️ PRE-EXISTING GAP | `SCOUT_AGENT` (scout_routes.py:61) 從未在 §九 表註冊，本 PR 未引入新 singleton（class 位置變更不影響 singleton 表結構），不阻擋本 PR |
| 文件大小 800/1200 行 | ✅ PASS | maf 966（800-1200 警告區，方向 correct -224）；scout_agent 297（< 800） |
| Bybit API 改動 | ✅ N/A | 0 Bybit API change |

---

## 5. 對抗反問

1. **「PEP 562 lazy re-export 真能 cover 6 套 test 全部 import pattern？」**
   驗證方法：實跑 6 套 → 286 / 286 PASS（test_scout_integration 38 + test_scout_audit_wiring + test_multi_agent_framework + test_h_state_query_handler 共 169 + test_strategist_agent + test_batch7_conductor_strategist 共 79）。`from app.multi_agent_framework import (ScoutAgent, ScoutConfig)` 直接觸發 PEP 562 → 正確解析，identity 為新 `app.scout_agent.ScoutAgent`。
   實測 Python：`maf.ScoutAgent is scout_agent.ScoutAgent → True`（commit log 已 claim，E2 reproduce 確認）。
   pickle round-trip：通過（`__class__.__module__ == 'app.scout_agent'`）。
   `dir(maf)`：首次 lookup 後 cache 進 globals，`dir()` 顯示 `ScoutAgent`。

2. **「IDE/PyLance/mypy 看不到 ScoutAgent？」**
   PEP 562 對 type checker 的支援不一：mypy 0.910+ 識別模組級 `__getattr__`，PyCharm/VS Code Pylance 部分支援但 import auto-complete 可能漏標。**Workaround**：scout_agent.py 直接 import（PA RFC §4.2 推薦但 §4.3 不強制）。對下游無 breakage，type narrowing 部分降級可接受。**LOW INFO**。

3. **「替代方案：抽 shared types 到第 3 個檔（agent_base.py）」**
   理論可行，但 cost 高：需移 5 個 enum + 4 個 dataclass + MessageBus 共 ~360 LOC 至 agent_base.py，且 maf 與 5 agent 全部 import 路徑要改。當前 PEP 562 magic 的代價遠低於拆 base 檔；**不推**。
   **更乾淨替代**：eager `from .scout_agent import ScoutAgent, ScoutConfig` 放在 maf **檔尾**（line 966 後）。maf body 從未引用 ScoutAgent class。此方案無 magic、IDE 友好、無 cycle。**作為 follow-up 建議**，本 PR 不阻擋。

4. **「3 hint emit 字串 bit-identical？」**
   確認 ✅：`agent.scout.intel_produced` / `agent.scout.alert_produced` / `agent.scout.scan_completed` 全部 1:1 保留，scout_agent.py:182/239/257 對應原 maf 位置。grep 驗證。

5. **「5-field schema 完全沒動？」**
   ✅ scout_agent.py:312-332 `get_scout_snapshot` 5 field 全 `int(...)` 包裝：intel_produced / alerts_produced / scans_completed (counters) + intel_log_size / alert_log_size (gauges)。Rust `AgentState.stats: HashMap<String, i64>` 對齊 invariant 保留。

6. **「`maf.ScoutAgent is scout_agent.ScoutAgent` identity？」**
   ✅ E2 實測 reproduce 通過。PEP 562 cache 寫入 maf globals 後，後續 `from maf import ScoutAgent` 與 `from scout_agent import ScoutAgent` 拿到同一 class object。

7. **「strategy_wiring SCOUT_AGENT singleton 註冊 CLAUDE.md §九 是否需更新？」**
   `SCOUT_AGENT` 從未在 §九 singleton 表登記（pre-existing gap，非本 PR 引入）。class 位置變更不改變 singleton 創建者（scout_routes.py:61）。本 PR 不擴大此 gap，不阻擋。建議單開 P3 ticket 補登 SCOUT_AGENT + 其他未登記 singleton。

---

## 6. Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| LOW (NIT) | `scout_agent.py:45,59` (MODULE_NOTE 中英) | docstring 聲稱 "noqa: F401 re-export"，但實際 maf 用 PEP 562 `__getattr__`。讀者依此 grep maf 找 `noqa: F401` 將 mismatch 真實機制 → 維護混淆。 | Edit: docstring 改為「PEP 562 module-level `__getattr__` lazy re-export」，並引用 maf line 380-390 註解。同步修中英版。 |
| LOW (NIT) | `scout_agent.py:54` `logger = logging.getLogger(__name__)` | `logger` 定義但 0 usage（grep `logger\.` = 0 hit）；`logging` import 也僅為宣告 logger 用。Pre-refactor maf 同樣風格，非新引入；E1 移轉時保留沒主動清理。 | 保留現狀（與 maf 風格一致）OR Edit: 刪除 `import logging` + `logger = ...`（精簡 2 LOC）。E2 不強制。 |
| INFO | maf.py:380-390 PEP 562 `__getattr__` 區塊 | E1 偏離 PA RFC §3 採 PEP 562 lazy 是 **functional 對的選擇**，但更乾淨替代 = 把 eager `from .scout_agent import ScoutAgent, ScoutConfig` 放在 maf **檔尾**（line 966 後）。maf body 從未引用 ScoutAgent class。此方案無 magic、IDE 友好、避免 PEP 562 cache→`dir()` 副作用。 | 建議開 follow-up ticket `G3-08-FUP-MAF-SPLIT-CLEANUP P3`：(a) 把 PEP 562 改為 bottom-of-file eager re-export (b) 修 scout_agent.py docstring。本 PR 不強制。 |
| INFO | CLAUDE.md §九 singleton 表 | `SCOUT_AGENT` (scout_routes.py:61) pre-existing 未登記，本 PR 未引入新 singleton。class 位置變更不影響 singleton 表結構。 | 建議單開 P3 ticket 補登 SCOUT_AGENT 至 §九 表（non-blocking）。 |

**0 CRITICAL / 0 HIGH / 0 MEDIUM**。

---

## 7. 測試實證（E2 reproduce）

| Suite | passed | failed | runtime |
|---|---|---|---|
| `tests/test_scout_integration.py` | 38 | 0 | 0.06s |
| `tests/test_scout_audit_wiring.py` + `test_multi_agent_framework.py` + `test_h_state_query_handler.py` | 169 | 0 | 0.07s |
| `tests/test_strategist_agent.py` + `tests/test_batch7_conductor_strategist.py` | 79 | 0 | 0.12s |
| **Total** | **286** | **0** | **~0.25s** |

與 E1 報告聲稱完全一致。Mac dev-only env 下無 fastapi/integration deselect 影響。

---

## 8. 結論

**Verdict**: **PASS_WITH_NITS** to E4

理由：
- ✅ 6 套 286 tests 全綠（E2 reproduce 一致）
- ✅ 0 production behavior change（3 hint emit + 5-field schema bit-identical）
- ✅ 8 條 §九 checklist 全 pass / N/A
- ✅ 9 條 OpenClaw 特殊 checklist 全 pass / N/A（singleton 表 gap 為 pre-existing）
- ✅ 雙語注釋齊備
- ✅ 跨平台 clean
- ⚠️ 2 LOW NITs（docstring drift + unused logger）+ 1 INFO 設計替代（PEP 562 vs bottom-of-file eager）— 可作 P3 cleanup ticket，**不阻擋進 E4**

E4 可進行 full regression。建議 PA 開 `G3-08-FUP-MAF-SPLIT-CLEANUP P3` ticket 收 2 NIT + 設計替代（FUP 而非阻擋本 PR）。

---

## 9. 退回 E1 修復清單

無 — 本 PR 不退回。NIT 與 INFO 改 PA backlog ticket 處理。

---

**E2 REVIEW DONE**: PASS_WITH_NITS · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-27--g3_08_fup_maf_split_review.md`
