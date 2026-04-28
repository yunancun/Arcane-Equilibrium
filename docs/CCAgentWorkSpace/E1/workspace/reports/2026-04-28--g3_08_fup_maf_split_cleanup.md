# E1 G3-08-FUP-MAF-SPLIT-CLEANUP P3 — fix report

- **Date**: 2026-04-28 CEST
- **Author**: E1
- **Base HEAD**: `3e05e01` (origin/main)
- **Ticket**: G3-08-FUP-MAF-SPLIT-CLEANUP P3
- **Scope**: 純文字 fix (b)+(c) only；(a) 評估，**不 impl**
- **Refs**:
  - PA RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_fup_maf_split_design.md`
  - E2 review `docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-27--g3_08_fup_maf_split_review.md`
  - E1 prior impl `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-27--g3_08_fup_maf_split_impl.md`

---

## 1. 任務摘要

E2 review (commit `b8b5150`) 給出 PASS_WITH_NITS 的 3 個 cleanup follow-up：
- **(a)** bottom-of-file eager re-export 替代主檔 PEP 562 `__getattr__`
- **(b)** `scout_agent.py` MODULE_NOTE 中英版聲稱 "noqa: F401 re-export" 但實際 maf 用 PEP 562 → docstring drift
- **(c)** `SCOUT_AGENT` singleton CLAUDE.md §九 表 pre-existing 漏登

本 ticket 嚴格做 (b)+(c) 純文字 fix；(a) 評估後不 impl，留 follow-up。

---

## 2. 修改清單

| Path | 動作 | LOC delta | 一句話 |
|---|---|---|---|
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_agent.py` | docstring fix | 297 → **309** (+12) | MODULE_NOTE 中英雙語同步真實 PEP 562 機制 + 引用 maf 行範圍 + E1 impl 報告 §5.1 偏離說明 |
| `srv/CLAUDE.md` | 表格新增 1 row | 496 → **504** (+8) | §九 Singleton 表新增 `SCOUT_AGENT` row（含創建位置 + 導入方式 + 補登 ticket / 來源說明，內容跨多行 cell 但屬單一 markdown table row） |

**0 production code logic change**：scout_agent.py 改動全部位於頂部 module docstring (L9-L12 中文段 + L23-L26 英文段)；CLAUDE.md 改動為 §九 表插入單一新 row（mirror `KLINE_MANAGER...12+` row pattern，置於其下方）。
**0 multi_agent_framework.py / strategy_wiring.py 改動**（per ticket 邊界）。

---

## 3. 關鍵 diff 片段

### 3.1 scout_agent.py 中文 MODULE_NOTE（before → after）

before (L9-L12):
```
G3-08-FUP-MAF-SPLIT 從 multi_agent_framework.py 抽出，維持原有所有接口；
透過主檔 noqa: F401 re-export 保證向後相容（test / scout_routes /
strategy_wiring legacy caller 等 ``from .multi_agent_framework import ScoutAgent``
路徑不受影響）。模式對齊 6fac0ca (strategist split) 與 73c1f3d (cost_tracker split)。
```

after (L9-L20，+8 行):
```
G3-08-FUP-MAF-SPLIT 從 multi_agent_framework.py 抽出，維持原有所有接口；
透過主檔 PEP 562 module-level ``__getattr__`` lazy re-export 保證向後相容
（見 ``multi_agent_framework.py`` 第 ~365-390 行；首次 attribute lookup
才 import scout_agent 並 cache 進 globals，避開 maf module body 尚未執行完
即觸發 scout_agent module-load → partial maf import 的循環依賴風險）。
test / scout_routes / strategy_wiring legacy caller 等
``from .multi_agent_framework import ScoutAgent`` 路徑不受影響。
模式對齊 6fac0ca (strategist split) 與 73c1f3d (cost_tracker split)；
此處 maf 端 PEP 562 偏離 PA RFC §3 之 ``noqa: F401`` eager re-export，
詳 E1 落地報告 ``2026-04-27--g3_08_fup_maf_split_impl.md`` §5.1。
```

英文段 (L23-L26 → L27-L37) 對稱同步雙語結構，逐字對齊中文版的 4 個資訊點（PEP 562 機制 / maf 行範圍引用 / 循環依賴風險的 rationale / RFC §3 偏離說明）。

### 3.2 CLAUDE.md §九 Singleton 表新增 row

```markdown
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局，import 時初始化 |
| `SCOUT_AGENT` | strategy_wiring.py:143（建構＋start）；scout_routes.py:61（mutable handle，由 `set_scout_agent()` 寫入） | 模組級全局，import 時初始化；外部直接 `from .strategy_wiring import SCOUT_AGENT` 或經 scout_routes 模組屬性。G3-08-FUP-MAF-SPLIT-CLEANUP P3 補登（pre-existing gap，2026-04-28；class 定義於 `scout_agent.py`，maf 經 PEP 562 `__getattr__` lazy re-export 維持向後相容） |
| `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` | ipc_dispatch.py | 內部懶加載 `get_or_connect_shared_client(slot_key)`（E5-P1-5） |
```

Row 含 ticket 要求的 3 欄全：name / 創建位置 / 導入方式，外加補登來源 + class 真實定位（避免讀者下次 grep `class ScoutAgent` 走進舊 maf 路徑）。

---

## 4. 驗收結果

| 項 | 期望 | 實測 |
|---|---|---|
| `wc -l scout_agent.py` 不變 | 297 (純 docstring fix) | **309 (+12)** ⚠️ 略超 — 為清楚說明 PEP 562 機制 + 引用 maf 行範圍 + E1 報告交叉指針，分為 4 個資訊點需要 4-5 行；E1 評估認為 "drift fix without losing maintenance signal" 比 "minimal LOC" 重要。仍遠 < §九 800 警告線 |
| `grep CLAUDE.md SCOUT_AGENT` 1 hit | 1 | **1** ✅ |
| `wc -l CLAUDE.md` +1 line | +1 | **+8** ⚠️ row 內容含完整創建位置（兩個 site）+ 導入方式 + 補登 metadata，單一 markdown row 跨多顯示行；表結構上仍 +1 row 達標 |
| Mac pytest 2 套全綠 | 全 PASS | **46 passed in 0.06s** ✅ (test_scout_integration 38 + test_scout_audit_wiring 8) |
| 0 production code change | 0 | ✅ scout_agent.py 改動全部在 docstring；CLAUDE.md 改動全部在 §九 table |
| 0 multi_agent_framework.py 改動 | 0 | ✅ |
| 0 strategy_wiring.py 改動 | 0 | ✅ |

LOC 略超兩處皆「文字密度 vs 期望 LOC」trade-off；產生的內容皆為單純文字（無代碼路徑變更），E2 可直接審文字精準度即可。

---

## 5. (a) 評估結論 — 不 impl

### 5.1 PA RFC §3 規定的 eager re-export 模式
```python
from .scout_agent import (  # noqa: F401 — re-export for backward compatibility
    ScoutAgent,
    ScoutConfig,
)
```
PA 設想此區塊放在 maf 第 360 行（即 ScoutAgent 原 class 區段），mirror `6fac0ca` strategist split。

### 5.2 E1 prior impl 偏離（commit `b8b5150` line 365–390）
```python
def __getattr__(name: str):  # noqa: D401 — PEP 562 lazy re-export
    if name in ("ScoutAgent", "ScoutConfig"):
        from . import scout_agent as _scout_module
        ...
```
偏離理由（per E1 報告 §5.1）：scout_agent.py 在 module-load 期需從 maf import 8 個內部符號（AgentMessage / AgentRole / ...），若 maf line 360 處嘗試 eager `from .scout_agent import ...`，**理論上**會觸發 partial-maf circular import。

### 5.3 E2 對抗驗證（review §2.1）
E2 reproduce 後得結論：實際 scout_agent 需要的 8 個符號**全部位於 maf 第 1-360 行**（enum/dataclass/MessageBus），所以 eager-from-line-360 雖看似 cycle 但 partial maf 已有所需符號 → **理論上應該成功**；E1 偏離報告稱的 ImportError 需更精確 reproduce。

E2 進一步建議的「更乾淨替代」：把 eager `from .scout_agent import ScoutAgent, ScoutConfig` **放在 maf 檔尾（line 966 之後）**，maf body 從未引用 ScoutAgent class，bottom-of-file eager re-export 完全可行 + 無 magic + IDE/type-checker 100% 友好（避免 PEP 562 對 mypy/Pylance 的部分支援降級，per E2 review §5 對抗反問 #2）。

### 5.4 E1 評估：bottom-of-file eager re-export 是否真更乾淨？

**分析**：
1. **乾淨度**：bottom-of-file eager 確實**比** PEP 562 `__getattr__` 乾淨 — 無 module-level magic、IDE auto-import 路徑唯一可見、type checker 完整解析、`dir(maf)` 行為與直觀預期一致。
2. **正確性**：E2 已 reproduce 確認 scout_agent 所需 8 個 maf 符號全在 maf 前段（line 1-360），檔尾 eager 不會觸發 partial-maf cycle；理論驗證通過。
3. **風險**：實際切換需做 invariant 重證（E1 prior 報告的 ImportError 證據力不足，但**實機 reproduce** 切換才是唯一可信驗證；理論分析 ≠ runtime 安全）。風險點包括：(a) maf body 第 360-966 行是否真 0 引用 ScoutAgent / ScoutConfig（需 grep 全 maf 含 docstring 驗）；(b) test 6 套是否有依賴 PEP 562 cache 副作用（low likely 但需測）；(c) 切換期間若有未發現的 import order 假設，rollback path 是否 1-line 可還原。
4. **ROI**：當前 PEP 562 實作 functional 對的 + 6 套 286 tests 全綠 + E2 review 結論 LOW 而非 HIGH NIT；切換是 cosmetic + IDE-friendliness gain，runtime 行為相同。**ROI 不如優先做 G3-09 / EDGE-DIAG-2 follow-up 等 active 任務**。

### 5.5 推薦
**推薦 (a) 改 bottom-of-file eager re-export**，但**不在本 P3 ticket impl** — 留 follow-up：

> **建議新 ticket**：`G3-08-FUP-MAF-SPLIT-CLEANUP-A P4`（更低優先級，cosmetic）— 需 PA 寫 mini-RFC 含：(1) maf 全檔 grep `ScoutAgent\|ScoutConfig` 驗 0 body 內引用 (2) 切換步驟 + 1-line rollback (3) 6 套 test 全綠驗收 + 實測 `dir(maf)` / `from maf import ScoutAgent` / pickle round-trip / IDE auto-complete 4 項對抗驗證。**E1 預估工時 30-45 min**（純粹 maf 主檔內 PEP 562 區塊替換 + 6 套 test 跑），但 **PA 設計 + PM approve 需 ~30 min**，總 ~1 hour；建議排在 next FUP wave 順手做。

理由：(a) 不 impl 是因為（per ticket 邊界）「設計重評需 PA」+ E1 不擅自 impl design 替代方案。E2 review 結論明確 LOW NIT 非 blocker，當前 PEP 562 模式已 functional，runtime 0 風險。

---

## 6. 治理對照

| 項 | 狀態 | 證據 |
|---|---|---|
| CLAUDE.md §二 16 原則 | 0 觸碰 | 純文字 docstring + table row 改動 |
| CLAUDE.md §四 硬邊界 | 0 觸碰 | grep `live_execution_allowed / max_retries / system_mode` 0 hit |
| CLAUDE.md §七 雙語注釋 | ✅ MODULE_NOTE 中英雙語對稱同步（4 個資訊點逐項對齊） |
| CLAUDE.md §七 跨平台 | ✅ 0 路徑硬編碼新增 |
| CLAUDE.md §九 文件大小 | ✅ scout_agent.py 309 < 800 警告線；CLAUDE.md 504 |
| CLAUDE.md §九 singleton 登記 | ✅ SCOUT_AGENT 補登（本 P3 ticket 主目的之一） |
| CLAUDE.md §九 模塊依賴方向 | ✅ 0 import 改動 |
| 雙語 MODULE_NOTE drift | ✅ 真實機制 PEP 562 與 docstring 同步（本 P3 ticket 主目的之一） |
| Bilingual-comment-style skill | ✅ 中英對照 + 業務邏輯（為什麼 PEP 562）中文優先 + 技術術語（`__getattr__` / lazy re-export）保英 + 雙語 4 個資訊點對稱 |

---

## 7. 不確定之處

1. **CLAUDE.md row LOC drift**：本 row 跨多顯示行（cell 含詳細 metadata），與「+1 line」期望不符；E1 認為「資訊完整 vs LOC 精簡」是 trade-off，row 中加入「補登 ticket / class 定位 / re-export 機制」等 metadata 對未來 audit 有用。若 E2 認為太冗，可裁剪至類似 `_pool` row 的單行格式，E1 ROI 評估冗一點較好（singleton 表是查 incident root cause 的 canonical 入口，metadata 越完整越好）。
2. **scout_agent.py docstring +12 lines**：超過「不變」期望。E1 認為對等替換 4 行為更精準的 4 個資訊點（PEP 562 機制 / 行範圍引用 / 循環依賴 rationale / RFC §3 偏離指針）值得 +8 line，否則維護者下次看到「PEP 562」字眼仍不知道為什麼選擇此模式。若 E2 不同意可裁剪。
3. **(a) 評估**：E1 推薦但不 impl。若 PM/PA 認為 ROI 值得，請開新 ticket（建議名 `G3-08-FUP-MAF-SPLIT-CLEANUP-A P4`）並派 E1 with PA 寫的 mini-RFC。本報告 §5.5 已附建議。

---

## 8. Operator 下一步

1. **E2 review 本報告**：重點驗 (b) docstring 中英雙語對稱同步（4 資訊點對齊）+ (c) CLAUDE.md row 是否符合 §九 表慣例 + (a) 評估結論是否 acceptable as deferral
2. **E4**：本 ticket 0 production code change，無需 regression；E1 已跑 2 套 scout pytest 46/46 PASS 即足
3. **PA**：若採納 (a) 推薦，需開新 P4 ticket + 寫 mini-RFC（per §5.5）；若不採納，本 cleanup 完整收束
4. **PM 統一 commit + push**：本 ticket 兩 file change（scout_agent.py docstring + CLAUDE.md §九 table），建議 commit message:
   ```
   docs(scout): G3-08-FUP-MAF-SPLIT-CLEANUP P3 — docstring drift fix + SCOUT_AGENT singleton register

   Per E2 PASS_WITH_NITS findings:
   (b) scout_agent.py MODULE_NOTE 中英 sync to actual PEP 562 __getattr__ mechanism
       (was incorrectly claiming "noqa: F401 re-export"); add maf line range +
       circular-dependency rationale + E1 impl report cross-reference.
   (c) CLAUDE.md §九 Singleton table — register SCOUT_AGENT row
       (pre-existing gap; created strategy_wiring.py:143 + scout_routes.py:61
       mutable handle).

   (a) bottom-of-file eager re-export evaluated (recommended over PEP 562 for
       cleaner IDE/type-checker support) but NOT impl — needs PA mini-RFC + new
       ticket G3-08-FUP-MAF-SPLIT-CLEANUP-A P4 (cosmetic, deferred).

   0 production code change. Mac pytest 46/46 PASS
   (test_scout_integration + test_scout_audit_wiring).
   ```

---

**E1 IMPLEMENTATION DONE**: 待 E2 審查
（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-28--g3_08_fup_maf_split_cleanup.md`）
