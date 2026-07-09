# G3-08 Phase 4 Split Combined Design RFC — Strategist + cost_tracker

**Date**: 2026-04-26 CEST
**Author**: PA (Project Architect)
**Trigger**: PM Tier 9 Track 1 dispatch (per PM Tier 8 sign-off `e5f1b2d` § 6 follow-ups #1 + #2)
**Scope**: 兩個 Python 模塊的 sibling split design：
1. `strategist_agent.py` 1200/1200 §九 hard cap exact-touch（MED, hard pre-condition for Phase 4 5-Agent Strategist sub-task）
2. `layer2_cost_tracker.py` 930 LOC §七 警告區 +130（LOW, plan ahead with Strategist split）

**Output state**: design only — 無生產代碼改動 / 無 cargo build / 無 pytest. Output ＝ 本 RFC 11 節 + 兩個 self-contained E1 prompt template.

**Hard rules respected**: 不寫實作碼 / 不動 `app/strategist_agent.py` 或 `app/layer2_cost_tracker.py` 業務碼 / 不動 QA / Operator / 隔壁 session WIP（PA memory.md modified、Operator strkusdt + PA workspace strkusdt 兩處 WIP unchanged）.

---

## § 1. 背景

### 1.1 Tier 8 finding 重述

E2 Tier 8 batch review (`84da817`) + Tier 8 Track 4 supplemental review (`2e02afb`) 揭發 2 個 §九/§七 LOC 隱形地雷：

| Finding ID | Severity | 檔 | Current LOC | §七 / §九 狀態 |
|---|---|---|---|---|
| **T8-MED-1** | 🟠 MED | `strategist_agent.py` | **1200** | exact-touch §九 1200 hard cap |
| **T8T4-LOW-1** | 🟢 LOW | `layer2_cost_tracker.py` | **930** | §七 800 警告線 +130（headroom 270 至 §九）|

獨立驗證（PA 本次 RFC 開工前）：
```
$ wc -l srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/{strategist_agent,layer2_cost_tracker}.py
    1200 strategist_agent.py
     930 layer2_cost_tracker.py
```

### 1.2 為何 plan ahead 同 wave 處理

| 理由 | 解釋 |
|---|---|
| **時序 unblock 路徑** | strategist split = Phase 4 5-Agent Strategist sub-task **hard pre-condition**；cost_tracker split = G3-09 cost_edge_ratio implementation 預期 +50-100 LOC 後即觸 §九 1200。兩者不解 = Wave 4 主軸全堵 |
| **同類性質** | 兩者均 Python 模塊 split + sibling pattern；同套 PA design template、同套 E1 prompt template 套路；分兩次 RFC 浪費 PA + 主會話 context |
| **caller 影響低** | Caller import: strategist 1 個 / cost_tracker 3 個（grep verified §1.3）；test reference 數高但 import 集中（`from app.<module> import <SymbolList>` 一條），split 採 `pub use` re-export 模式可零下游影響 |
| **既有 sibling 模式成熟** | strategist_agent.py 已執行過 §14.1 sibling refactor（h1_thought_gate / h4_validator / model_router / strategist_models / strategist_fast_channel 5 sibling 共 1213 LOC），本次只擴 sibling list 不創造新 pattern |

### 1.3 caller 影響獨立 grep verified

```
$ grep -rn 'from .strategist_agent\|from \.strategist_agent\|import strategist_agent' srv/program_code/
srv/.../app/model_router.py:10:  零循環依賴：只依賴標準庫 + typing，不 import strategist_agent。  # 文檔行非實 import
srv/.../app/strategy_wiring.py:154:from .strategist_agent import StrategistAgent, StrategistConfig

$ grep -rn 'from .layer2_cost_tracker\|from \.layer2_cost_tracker\|import layer2_cost_tracker' srv/program_code/
srv/.../app/layer2_engine.py:65:from .layer2_cost_tracker import Layer2CostTracker
srv/.../app/layer2_routes.py:42:from .layer2_cost_tracker import Layer2CostTracker
srv/.../app/strategy_wiring.py:161:    from .layer2_cost_tracker import Layer2CostTracker
```

Test references:
```
$ grep -rn 'strategist_agent\|StrategistAgent\|StrategistConfig\|EdgeEvaluation' srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ | wc -l
189
$ grep -rn 'layer2_cost_tracker\|Layer2CostTracker' srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/ | wc -l
26
```

關鍵 test patch path（**必保留**）:
- `app.layer2_cost_tracker._invalidate_h_state_async` (test_layer2.py:375, 399, 525, 551 + test_h_state_query_handler.py)
- `app.h1_thought_gate._invalidate_h_state_async` (test_h1_thought_gate.py:207) — 既有 sibling 已採此 patch path 模式
- 所有 test `from app.strategist_agent import ...` 或 `from app.layer2_cost_tracker import ...` 路徑

**結論**：split **必走 namespace re-export**（`from .<sibling> import *` + `__all__` 控制 facade），保證 `app.strategist_agent.<Symbol>` / `app.layer2_cost_tracker.<Symbol>` 全部下游 callsite 零變動。

### 1.4 § 14.1 既有 sibling pattern reference（PA 採此模板）

strategist_agent.py 已歷一輪 §14.1 refactor（commit 序列在 G2-G3 期間）：

| Sibling | LOC | Role |
|---|---|---|
| `strategist_agent.py` (orchestrator) | 1200 | StrategistAgent 編排層 + intent 產出 |
| `strategist_models.py` | 167 | EdgeEvaluation / StrategistConfig / `_heuristic_evaluate` / `_parse_sentiment` (re-exported `noqa: F401`) |
| `strategist_fast_channel.py` | 93 | `build_emergency_intents` 快速通道 intent 構建 |
| `h1_thought_gate.py` | 368 | H1 ThoughtGate 確定性閘門 |
| `h4_validator.py` | 103 | H4 stateless validator |
| `model_router.py` | 482 | H3 ModelRouter + L2 background |

**要點**：
- 主檔 `strategist_agent.py` 從歷史 ~2000 LOC 減至 1200，但 G3-08 Phase 3 Sub-task 3-2 H4 silent gap fix +32 LOC（`71faf4c`）後 exact-touch 1200。**第二輪拆分必要**。
- 既有 sibling 全採 `from .<sibling> import <symbol>` 直接 import 模式，**非** namespace re-export — 為什麼下游不破？因為 `strategist_models.py` 已將其符號 `# noqa: F401 — re-export for backward compatibility` 重導出至 `strategist_agent.py` namespace（line 73-78），下游 `from app.strategist_agent import EdgeEvaluation` 仍解析得到。
- 本 RFC 的拆分必延續此 re-export 模式：新 sibling 內定義 + 主檔加 `from .<new_sibling> import *` 或 `from .<new_sibling> import (...)  # noqa: F401`，保 1200 拆分後 callsite 零變動。

---

## § 2. strategist_agent.py 全文 audit + logical grouping

### 2.1 結構盤點（grep based, 1200 LOC verified）

```
class StrategistAgent (line 88) — main class
├── ctor + class attrs (88-237) — 150 LOC
├── start/stop (243-252) — 10 LOC
├── on_message dispatch (256-274) — 19 LOC
├── _handle_intel ★ huge core (276-472) — 197 LOC ← 主編排邏輯
├── _produce_intents (474-551) — 78 LOC
├── _handle_risk_verdict (555-558)
├── _handle_pattern_insight (560-564)
├── _handle_directive (566-575) — 10 LOC
├── set_budget_manager (579-593) — 15 LOC
├── set_truth_registry (595-604) — 10 LOC
├── _apply_pattern_insight (606-633) — 28 LOC
├── get_strategy_weight (635-665) — 31 LOC
├── _apply_regime_weights (667-694) — 28 LOC
├── _apply_l2_weight_update (696-720) — 25 LOC
├── _build_route_context (724-746) — 23 LOC
├── _evaluate_edge_l1_5 (748-767) — 20 LOC
├── _process_knowledge_update (769-797) — 29 LOC
├── _build_prompt_context ★ AI prompt (801-888) — 88 LOC
├── _evaluate_edge (892-913) — 22 LOC
├── _ai_evaluate ★ Ollama call (915-1005) — 91 LOC ← H4 PASS counter 在此
├── collect_pending_intents [DEPRECATED] (1009-1022) — 14 LOC
├── _h1_check_budget [BWD compat delegator] (1028-1030)
├── _h1_complexity_score [BWD compat delegator] (1032-1034)
├── _h1_check_cooldown [BWD compat delegator] (1036-1038)
├── _validate_ai_output [BWD compat delegator] (1040-1042)
├── _h3_route_model [BWD compat delegator] (1044-1048)
├── handle_fast_channel (1052-1099) — 48 LOC ← V2 emergency mode
├── clear_emergency_mode (1101-1110) — 10 LOC
├── set_cognitive_modulator (1114-1126) — 13 LOC
├── _apply_cognitive_modulation (1128-1152) — 25 LOC
├── get_stats (1160-1178) — 19 LOC
├── get_h4_snapshot (1182-1195) — 14 LOC ← G3-08 Phase 3 Sub-task 3-2
└── get_recent_evaluations (1197-1200) — 4 LOC
```

### 2.2 Logical grouping（按職責 split candidate）

| Group | Methods | LOC | 內聚理由 |
|---|---|---|---|
| **A. Core orchestrator** | ctor + start/stop + on_message + _handle_intel + _produce_intents + _handle_risk_verdict + _handle_pattern_insight + _handle_directive | ~480 | StrategistAgent 主編排 — message dispatch + intel→intent 主流；BWD compat 必須在主類別 |
| **B. Edge evaluation** | _evaluate_edge + _ai_evaluate + _evaluate_edge_l1_5 + _build_prompt_context + _process_knowledge_update + _build_route_context | ~270 | Ollama / Claude AI 評估邏輯 + prompt 構建 + knowledge_update 寫回 TSR |
| **C. Strategy weights / regime** | set_budget_manager + set_truth_registry + _apply_pattern_insight + get_strategy_weight + _apply_regime_weights + _apply_l2_weight_update | ~125 | 策略偏好權重 + regime 權重 + Truth Registry 注入 |
| **D. Cognitive + fast channel** | handle_fast_channel + clear_emergency_mode + set_cognitive_modulator + _apply_cognitive_modulation | ~95 | V2 雙軌（快速通道 emergency mode + 認知調製器整合）|
| **E. Status / snapshot** | get_stats + get_h4_snapshot + get_recent_evaluations + collect_pending_intents (deprecated) | ~50 | Observability accessors + DEPRECATED collect |
| **F. BWD compat delegators** | _h1_check_budget + _h1_complexity_score + _h1_check_cooldown + _validate_ai_output + _h3_route_model | ~25 | 5 個 thin wrapper 委託到既有 sibling，向後兼容外部 caller |

LOC 合計 480+270+125+95+50+25 = ~1045 + 共用 import + class header 155 LOC ≈ 1200 verified.

### 2.3 拆分機會評估

| Group | 拆 sibling 友好度 | 主要難點 |
|---|---|---|
| A | 否 — 主類別必留 | StrategistAgent 必須是單一 class，Group A 是其本質骨架 |
| **B** | ★★★★ | 6 個 method 自成內聚 — Ollama 調用 + prompt 構建 + L1.5 + knowledge_update 寫 TSR；只引用 self._ollama / self.cost_tracker / self._truth_registry / self._budget_manager / self._stats / self._lock / self._last_knowledge_update + utils — 可 sibling-child-module pattern (`impl StrategistAgent` 像 Rust)，Python 用 `def _evaluate_edge(self, ...)` 拆成 module-level function 接 `self` |
| **C** | ★★★ | 6 method 內聚 — 但 `set_budget_manager` 呼叫 `self._model_router.set_budget_checker`（強耦合），`_apply_pattern_insight` 走 self._truth_registry；可拆但需注意 `self._model_router` access pattern |
| **D** | ★★★ | 4 method 內聚 — handle_fast_channel 呼叫 `build_emergency_intents` 已是 sibling import；可拆 |
| E | ★ | LOC 太低（50），不值得單獨拆檔 |
| F | ★★ | 25 LOC 但 5 個 thin wrapper —— 可作為「BWD compat sibling」與 §14.1 `strategist_models.py` 同模式 |

### 2.4 拆分路徑識別

**狀態變數使用矩陣**（哪些 sibling 需要哪些 instance attr）:

| Attr | A core | B edge_eval | C weights | D cognitive | E status |
|---|---|---|---|---|---|
| `self._lock` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `self._stats` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `self.config` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `self.bus` | ✅ | - | - | - | - |
| `self._ollama` | - | ✅ | - | - | - |
| `self.cost_tracker` | - | ✅ | - | - | - |
| `self._h1_gate` | ✅ (handle_intel) | - | - | - | - |
| `self._model_router` | ✅ (handle_intel) | - | ✅ (set_budget_manager) | - | ✅ (get_stats) |
| `self._budget_manager` | - | ✅ (l1_5) | ✅ | - | - |
| `self._truth_registry` | - | ✅ (proc_kn) | ✅ | - | - |
| `self._strategy_preference_weights` | ✅ (produce_intents) | - | ✅ | - | ✅ (get_stats) |
| `self._current_regime` | ✅ (handle_intel) | ✅ (build_prompt) | ✅ | - | - |
| `self._eval_log` | ✅ | - | - | - | ✅ |
| `self._max_eval_log` | ✅ | - | - | - | - |
| `self._pending_intents` | ✅ | - | - | ✅ (handle_fast) | ✅ |
| `self._normal_queue` | - | - | - | ✅ | ✅ |
| `self._emergency_mode` | ✅ (handle_intel) | - | - | ✅ | ✅ |
| `self._cognitive_modulator` | ✅ (handle_intel) | ✅ (build_prompt) | - | ✅ | ✅ |
| `self._last_knowledge_update` | - | ✅ | - | - | - |
| `self._h1_cooldown` | - | - | - | - | - |

**結論**：B (edge eval) + C (weights) + D (cognitive/fast) 三組最具內聚 + 最少 cross-attr overlap，是 sibling 候選首選。

---

## § 3. strategist_agent.py 拆分方案 A/B/C 對比

### 3.1 Method A — Sibling-helper 模塊化（推薦）

採 §14.1 既有 sibling 模式延伸：拆 B/C/D 三組為 sibling **module-level function**（接 `self` 為第一參數），非新 class；主檔 `strategist_agent.py` 保留 StrategistAgent class 骨架但 method 委託 `self._funcname = lambda: <sibling>.do_thing(self, ...)` 或更簡單 — `def method(self, ...): return <sibling>.do_thing(self, ...)`.

**Sibling list**:

| Sibling | 內容 | 預估 LOC |
|---|---|---|
| `strategist_agent.py` (主檔) | class StrategistAgent ctor + start/stop + on_message dispatch + _handle_intel + _produce_intents + 3 message handler + status accessors + BWD compat delegators + sibling re-exports | **~470** |
| `strategist_edge_eval.py` (新 sibling) | edge_evaluate / ai_evaluate / evaluate_edge_l1_5 / build_prompt_context / process_knowledge_update / build_route_context — 全 module-level function 接 `agent: 'StrategistAgent'` 參數 | **~280** |
| `strategist_weights.py` (新 sibling) | set_budget_manager / set_truth_registry / apply_pattern_insight / get_strategy_weight / apply_regime_weights / apply_l2_weight_update — module-level | **~140** |
| `strategist_cognitive.py` (新 sibling) | handle_fast_channel / clear_emergency_mode / set_cognitive_modulator / apply_cognitive_modulation — module-level | **~110** |
| `strategist_models.py` (既有, 不動) | EdgeEvaluation / StrategistConfig / _heuristic_evaluate / _parse_sentiment | 167 |
| `strategist_fast_channel.py` (既有, 不動) | build_emergency_intents | 93 |
| `h1_thought_gate.py` (既有, 不動) | H1ThoughtGate | 368 |
| `h4_validator.py` (既有, 不動) | validate_ai_output | 103 |
| `model_router.py` (既有, 不動) | ModelRouter | 482 |

**主檔 LOC 預估校正**：
```
ctor + class attrs:        150
start/stop + on_message:    30
_handle_intel:             197
_produce_intents:           78
3 message handlers:         25
status accessors (4):       50
BWD delegators (5):         25
sibling re-exports (new):   20
import header + docstring:  60
全副:                      ~635 → 主檔 ~470 (extracted ~165 LOC of weights/cognitive/edge_eval surface)
```

修正：實際 _handle_intel **不能拆** 因 attr cross-reference 複雜（每個 path 都觸 `self._h1_gate`/`self._model_router`/`self._stats`/`self._eval_log`/`self._strategy_preference_weights`）。但 _ai_evaluate / _build_prompt_context / _evaluate_edge_l1_5 / _process_knowledge_update / _build_route_context 5 method（共 ~270 LOC）可拆出去。

修正後預估:
- 主檔 = 1200 - (270 edge eval + 110 cognitive + 140 weights) + ~30 委託 = **~710**
- `strategist_edge_eval.py` = ~280 (含 module-level function 接 `agent` + docstring + `_ai_evaluate` 大宗)
- `strategist_weights.py` = ~140
- `strategist_cognitive.py` = ~110

主檔 **~710 LOC**，仍超 §七 800 警告線？— 否，710 < 800 √。但若要 hard cap 餘地多預留 50 LOC headroom 給 Phase 4 5-Agent get_<agent>_snapshot()，主檔需 < 750。**達標**。

**Pros**:
- 100% 沿襲 §14.1 既有模式，無新 pattern 學習成本
- 下游 `from app.strategist_agent import StrategistAgent, StrategistConfig, EdgeEvaluation` 零破壞（主檔加 `from .strategist_edge_eval import *  # noqa: F401`）
- E2 spot-check readability 風險低 — module-level function 比 class method 更易閱讀
- E1 工時可控 ~3-4h 落地（沿襲 G5-04 ai_service.py split 經驗）

**Cons**:
- 4 sibling 增加檔案數 — 但與 §14.1 既有 9 sibling 已成模式無實質負擔
- module-level function 接 `agent` 第一參數的 「pseudo-method」風格 vs class method 風格混用 — 加 docstring 即可消化

### 3.2 Method B — Class-level helper sibling（次選）

拆 B/C/D 為各自 class（`StrategistEdgeEvaluator` / `StrategistWeights` / `StrategistCognitive`），inject 到 StrategistAgent ctor，原 class method 委託 helper class instance。

**Pros**:
- 100% pure OO（method-on-class）
- 單元測試 helper class 較易（無需 mock entire StrategistAgent）

**Cons**:
- ★ 嚴重 — 與 §14.1 既有 5 sibling 全 module-level 模式不一致
- ★ 嚴重 — 新增 4 ctor injection point + class lifecycle 管理（既有 H1ThoughtGate / ModelRouter 兩個 ctor 注入已有，再加 3 個 = 5 個 sub-component class，過度 OO 化）
- 下游 `agent._evaluate_edge(...)` 需改為 `agent._edge_evaluator.evaluate_edge(...)` — BWD compat delegator 多一層
- LOC 預估高於 A（每 helper class 多 ~30 LOC class boilerplate）

### 3.3 Method C — Comment-only segmentation（拒絕）

不拆檔，加 `# === SECTION X: ... ===` 大型 region 標記 + 內部 visual hierarchy。

**Pros**:
- 0 工時 0 風險

**Cons**:
- ★ FATAL — strategist_agent.py 1200 LOC = §九 hard cap exact，**任何 +1 LOC 都觸發 silent §九 violation**
- ★ FATAL — Phase 4 5-Agent 必加 ~30-60 LOC（5 個 get_<agent>_snapshot()）；G3-09 cost_edge_ratio 在 strategist_agent 邊側可能加 +10-30 LOC
- 主檔 LOC ceiling 已 cap，無法承受任何 additive feature

**結論**：C 不解決 PM dispatch 真實問題（hard pre-condition for Phase 4）。

### 3.4 推薦 Method A

**Recommend Method A — 4 sibling pattern**:
- 主檔 ~710 LOC（< §七 800，留 ~90 LOC headroom for Phase 4 5-Agent）
- 3 新 sibling: `strategist_edge_eval.py` (~280) + `strategist_weights.py` (~140) + `strategist_cognitive.py` (~110)
- 既有 5 sibling 不動（h1_thought_gate / h4_validator / model_router / strategist_models / strategist_fast_channel）
- 全採 `from .<new_sibling> import *  # noqa: F401` re-export，下游 callsite 零變動
- E1 工時 ~3-4h，沿襲 G5-04 ai_service split 模式

---

## § 4. strategist_agent.py 完整 sibling list + LOC 預估

### 4.1 拆分後 sibling list

| File | Existing/New | LOC（前）| LOC（後）| Δ |
|---|---|---|---|---|
| `strategist_agent.py` (主檔) | Existing | 1200 | **~710** | -490 |
| `strategist_edge_eval.py` | **NEW** | 0 | **~280** | +280 |
| `strategist_weights.py` | **NEW** | 0 | **~140** | +140 |
| `strategist_cognitive.py` | **NEW** | 0 | **~110** | +110 |
| `strategist_models.py` | Existing (不動) | 167 | 167 | 0 |
| `strategist_fast_channel.py` | Existing (不動) | 93 | 93 | 0 |
| `h1_thought_gate.py` | Existing (不動) | 368 | 368 | 0 |
| `h4_validator.py` | Existing (不動) | 103 | 103 | 0 |
| `model_router.py` | Existing (不動) | 482 | 482 | 0 |
| **TOTAL** | | **2413** | **~2453** | +40 |

LOC 總和淨增 ~40（docstring 跨 sibling 重複 + import header 重複）— 可接受。

### 4.2 主檔 vs sibling 預估校正

```
主檔 (strategist_agent.py ~710 LOC):
  ├── header + import block + docstring     ~80
  ├── class attrs + ctor                   ~150
  ├── start / stop / on_message dispatch   ~30
  ├── _handle_intel (核心編排，不拆)       ~200
  ├── _produce_intents                      ~80
  ├── 3 message handlers                    ~25
  ├── set_budget_manager (delegator only)   ~10
  ├── set_truth_registry (delegator only)   ~10
  ├── status accessors (4 method)           ~60
  ├── BWD compat delegators (5 method)     ~25
  ├── sibling re-exports                    ~10
  ├── 雙語 inline comment                   ~30
  TOTAL                                    ~710

strategist_edge_eval.py (~280 LOC):
  ├── header + import block                 ~40
  ├── _evaluate_edge fn                     ~30
  ├── _ai_evaluate fn (含 H4 path)         ~110
  ├── _evaluate_edge_l1_5 fn                ~25
  ├── _build_prompt_context fn              ~95
  ├── _process_knowledge_update fn          ~30
  ├── _build_route_context fn               ~25
  ├── 雙語 docstring + inline                ~25
  TOTAL                                    ~280

strategist_weights.py (~140 LOC):
  ├── header + import block                 ~30
  ├── set_budget_manager fn                 ~20
  ├── set_truth_registry fn                 ~12
  ├── _apply_pattern_insight fn             ~30
  ├── get_strategy_weight fn                ~30
  ├── _apply_regime_weights fn              ~30
  ├── _apply_l2_weight_update fn            ~25
  ├── 雙語 docstring + inline                ~10
  TOTAL                                    ~140

strategist_cognitive.py (~110 LOC):
  ├── header + import block                 ~30
  ├── handle_fast_channel fn                ~50
  ├── clear_emergency_mode fn               ~12
  ├── set_cognitive_modulator fn            ~15
  ├── _apply_cognitive_modulation fn        ~25
  ├── 雙語 docstring + inline                ~10
  TOTAL                                    ~110
```

### 4.3 主檔 method 委託 pattern（範例）

主檔保留 method shape 但 body 委託 sibling:

```python
# === In strategist_agent.py 主檔 ===
from .strategist_edge_eval import (  # noqa: F401 — re-export for back-compat
    _build_prompt_context as _se_build_prompt_context,
    _evaluate_edge as _se_evaluate_edge,
    _ai_evaluate as _se_ai_evaluate,
    _evaluate_edge_l1_5 as _se_evaluate_edge_l1_5,
    _process_knowledge_update as _se_process_knowledge_update,
    _build_route_context as _se_build_route_context,
)
from .strategist_weights import (  # noqa: F401 — re-export for back-compat
    _apply_pattern_insight as _sw_apply_pattern_insight,
    get_strategy_weight as _sw_get_strategy_weight,
    _apply_regime_weights as _sw_apply_regime_weights,
    _apply_l2_weight_update as _sw_apply_l2_weight_update,
)
from .strategist_cognitive import (  # noqa: F401
    handle_fast_channel as _sc_handle_fast_channel,
    clear_emergency_mode as _sc_clear_emergency_mode,
    set_cognitive_modulator as _sc_set_cognitive_modulator,
    _apply_cognitive_modulation as _sc_apply_cognitive_modulation,
)

class StrategistAgent(BaseAgent):
    # ...
    def _ai_evaluate(self, intel: IntelObject) -> EdgeEvaluation:
        """Backward-compatible delegator to strategist_edge_eval / 向後兼容委託"""
        return _se_ai_evaluate(self, intel)
    # ... etc
```

**重點**：保留主檔 `_ai_evaluate(self, ...)` method 簽名（test 層 `agent._ai_evaluate(...)` 仍可呼）+ 主檔重 import sibling 函式 alias 為私名 `_se_*` / `_sw_*` / `_sc_*` 避 namespace 衝突。

**替代簡化**：用 monkey-patch 風格 `StrategistAgent._ai_evaluate = _se_ai_evaluate` 直接綁 sibling 函式為 method（更省主檔 LOC，但 test isolation 較差）。E1 落地時擇一。

### 4.4 Test cov 對齊驗證

```
test_strategist_agent.py 既有 import (line 37):
  from app.strategist_agent import StrategistAgent, StrategistConfig

test_strategist_agent.py 內局部 import (line 320, 372, 409, 465, 572, 590, 632, 685):
  from app.strategist_agent import EdgeEvaluation
  from app.strategist_agent import StrategistAgent, StrategistConfig, EdgeEvaluation
```

**保證**：拆分後主檔 namespace 仍含 `StrategistAgent` (class) + `StrategistConfig` (re-export from strategist_models) + `EdgeEvaluation` (re-export from strategist_models) → 0 test import 變動。

```
test_h1_thought_gate.py:32:
  from app.h1_thought_gate import H1ThoughtGate  # 既有 sibling test 已示範模式

test_h1_thought_gate.py:207:
  with patch("app.h1_thought_gate._invalidate_h_state_async") as mock_inv:
```

**Phase 4 / G3-09 follow-up test pattern 預期**：未來 test 可直接 `from app.strategist_edge_eval import _ai_evaluate` 個別 unit test，無需 spawn entire StrategistAgent class — split 提升 testability。

---

## § 5. layer2_cost_tracker.py 全文 audit + logical grouping

### 5.1 結構盤點（grep based, 930 LOC verified）

```
module-level:
├── _default_cost_state() (69-84)       — default state factory ~16
class Layer2CostTracker (87) — main class
├── ctor (95-112)                        — 18 LOC
├── _load (116-127)                      — 12 LOC
├── _apply_state (129-155)               — 27 LOC
├── _save (157-171)                      — 15 LOC
├── _read_raw (173-181)                   — 9 LOC
├── _today_key (185-186)                  — 2 LOC
├── get_daily_spend (188-198)             — 11 LOC
├── get_today_total_usd (200-202)        — 3 LOC
├── check_daily_budget (204-216)         — 13 LOC
├── get_effective_session_budget (218-235)— 18 LOC
├── get_h2_snapshot ★ (243-295)          — 53 LOC ← G3-08 Phase 3 Sub-task 3-1
├── get_h5_snapshot ★ (297-378)          — 82 LOC ← G3-08 Phase 3 Sub-task 3-3
├── record_claude_cost ★ (382-428)       — 47 LOC ← H2 + H5 dual invalidate hint
├── record_search_cost (430-457)         — 28 LOC ← H5 invalidate hint
├── _add_daily_claude_cost (459-466)     — 8 LOC
├── _sync_to_rust_budget (468-502)       — 35 LOC ← FIX-57 IPC fire-and-forget
├── _add_daily_search_cost (504-511)     — 8 LOC
├── _increment_daily_session_count (513-520)— 8 LOC
├── _write_raw (522-535)                 — 14 LOC
├── record_session (539-549)             — 11 LOC
├── get_sessions (551-555)               — 5 LOC
├── get_session_by_id (557-563)          — 7 LOC
├── backfill_pnl_attribution (567-579)   — 13 LOC
├── recalculate_adaptive ★ (583-646)     — 64 LOC ← 7d ROI 計算 + adaptive multiplier
├── get_adaptive_state (648-649)         — 2 LOC
├── get_pricing (653-654)                 — 2 LOC
├── update_pricing (656-674)             — 19 LOC
├── get_config (678-679)                  — 2 LOC
├── update_config (681-688)              — 8 LOC
├── get_cost_summary ★ (692-732)         — 41 LOC ← API 響應大宗
├── record_call (736-799)                — 64 LOC ← unified entry point
├── record_ollama_call [DEPRECATED] (803-831)— 29 LOC
├── get_ollama_stats (833-858)           — 26 LOC
├── get_cost_edge_ratio (860-896)        — 37 LOC
├── check_session_budget (900-902)       — 3 LOC
├── check_daily_hard_cap (904-907)       — 4 LOC
└── reset_today_costs (909-922)          — 14 LOC
```

### 5.2 Logical grouping

| Group | Methods | LOC | 內聚理由 |
|---|---|---|---|
| **A. Core / persistence** | _default_cost_state + ctor + _load + _apply_state + _save + _read_raw + _today_key + _write_raw | ~120 | 主類別 + 持久化 — 必留主檔 |
| **B. Daily budget** | get_daily_spend + get_today_total_usd + check_daily_budget + get_effective_session_budget + check_daily_hard_cap | ~50 | 每日預算讀取 + 計算（H2 SSOT 來源）|
| **C. Cost recording** | record_claude_cost + record_search_cost + _add_daily_claude_cost + _add_daily_search_cost + _sync_to_rust_budget + _increment_daily_session_count + record_call + record_ollama_call (deprecated) + reset_today_costs | ~180 | Claude / Perplexity / Ollama 成本記錄 + IPC 同步 + 去年成本歸零 |
| **D. Session management** | record_session + get_sessions + get_session_by_id + backfill_pnl_attribution | ~36 | Session 歷史 CRUD |
| **E. Adaptive budget** | recalculate_adaptive + get_adaptive_state + get_cost_edge_ratio | ~103 | 7d ROI 計算 + cost_edge_ratio（G3-09 解阻點）|
| **F. Pricing + config** | get_pricing + update_pricing + get_config + update_config | ~31 | Pricing table + config CRUD |
| **G. H state snapshots** | get_h2_snapshot + get_h5_snapshot | ~135 | G3-08 Phase 3 H2 + H5 hot-path snapshot accessors |
| **H. Summary + ollama stats** | get_cost_summary + get_ollama_stats + check_session_budget | ~70 | API 響應 + Ollama 統計 |

LOC 合計 120+50+180+36+103+31+135+70 = ~725 + 共用 import + class header 200 LOC ≈ 930 verified.

### 5.3 拆分機會評估

| Group | 拆 sibling 友好度 | 主要難點 |
|---|---|---|
| A | 否 | 主類別必留 |
| B | ★★ | 強耦合 self._config / self._adaptive 讀，但邏輯短（50 LOC）— 拆檔 ROI 低 |
| **C** | ★★★★ | 9 method 內聚 — record_* + IPC sync + daily increment；只引用 self._lock / self._pricing / self._ollama_stats / self._config + helpers — H 提示 hook 與 cost record 緊密耦合（_invalidate_h_state_async 在 record_claude_cost / record_search_cost 末尾），拆出 sibling 可保 hint 邏輯內聚 |
| D | ★ | 36 LOC，太短不值得拆 |
| **E** | ★★★ | 3 method 內聚 — recalculate_adaptive + get_adaptive_state + get_cost_edge_ratio；G3-09 cost_edge_ratio implementation 預期擴此區（+50-100 LOC），sibling 為 future-proof |
| F | ★ | 31 LOC，太短 |
| **G** | ★★★ | 2 method 內聚（H2 + H5 snapshot）— 共用 schema parity 設計 + 雙語 docstring 是大宗（135 LOC 中 ~80 是 docstring）；可拆但需注意 patch path `app.layer2_cost_tracker._invalidate_h_state_async` 必保留（test 26 reference） |
| H | ★ | 不單獨拆 |

---

## § 6. layer2_cost_tracker.py 拆分方案 A/B/C 對比

### 6.1 Method A — 3-sibling cost_recording / adaptive / hot_state_snapshots（推薦）

| Sibling | 內容 | 預估 LOC |
|---|---|---|
| `layer2_cost_tracker.py` (主檔) | class Layer2CostTracker ctor + persistence + daily budget + session mgmt + pricing/config + summary + sibling re-exports | **~480** |
| `layer2_cost_recording.py` (新 sibling) | record_claude_cost / record_search_cost / _add_daily_*_cost / _sync_to_rust_budget / _increment_daily_session_count / record_call / record_ollama_call (deprecated) / reset_today_costs + invalidate hint | **~210** |
| `layer2_adaptive.py` (新 sibling) | recalculate_adaptive / get_adaptive_state / get_cost_edge_ratio | **~120** |
| `layer2_h_state_snapshots.py` (新 sibling) | get_h2_snapshot + get_h5_snapshot + 雙語 docstring 大宗 | **~150** |

**主檔 LOC 預估**：
```
header + import + docstring:           90
_default_cost_state factory + class header: 50
ctor:                                  20
persistence (_load/_apply_state/_save/_read_raw/_write_raw): 80
daily budget (5 method):               50
session mgmt (4 method):               40
pricing + config (4 method):           35
summary + ollama_stats (3 method):     70
BWD compat delegators (record_call等多入口可能保留): ~25
sibling re-exports + helpers:          20
TOTAL                                ~480
```

主檔 480 LOC well under §七 800 警告線（headroom 320 LOC for G3-09 cost_edge_ratio future expansion）。

**Sibling LOC 預估**:
```
layer2_cost_recording.py (~210):
  ├── header + import                    ~30
  ├── record_claude_cost (含 H2 + H5 hint) ~50
  ├── record_search_cost (含 H5 hint)    ~30
  ├── _add_daily_claude_cost              ~10
  ├── _add_daily_search_cost              ~10
  ├── _sync_to_rust_budget                ~40
  ├── _increment_daily_session_count       ~10
  ├── record_call                         ~70
  ├── record_ollama_call (deprecated)     ~30
  ├── reset_today_costs                   ~15
  ├── 雙語 docstring + inline             ~15
  TOTAL                                  ~210 (含 wrappers)

layer2_adaptive.py (~120):
  ├── header + import                    ~30
  ├── recalculate_adaptive                ~70
  ├── get_adaptive_state                  ~5
  ├── get_cost_edge_ratio                 ~40
  ├── 雙語 docstring + inline             ~15
  TOTAL                                  ~120

layer2_h_state_snapshots.py (~150):
  ├── header + import                    ~30
  ├── get_h2_snapshot (含 53 LOC docstring) ~60
  ├── get_h5_snapshot (含 82 LOC docstring) ~85
  ├── 雙語 docstring + inline             ~10
  TOTAL                                  ~185 → 修正 ~150 (壓縮 docstring sharing)
```

實際 sibling LOC 修正：snapshot sibling 145-185 LOC 區間，視 docstring 是否壓縮。

**G3-09 cost_edge_ratio future-proof**：
- G3-09 implementation 預期 +50-100 LOC（演算法 + Rust hot-path 路由 + IPC 接口）
- 落地點 = `layer2_adaptive.py` (sibling)，不擾主檔
- sibling 後 LOC ~120 → ~220（仍 < 警告線）

**Test patch 路徑保留**：
```python
# test_layer2.py:375 (Sub-task 3-1 originally tested H2 hint emission):
with patch("app.layer2_cost_tracker._invalidate_h_state_async") as mock_inv:
  ...
  cost_tracker.record_claude_cost(session, 100, 200, "sonnet")
  assert ("h2.budget_consumed",), ...
```

問題：split 後 `_invalidate_h_state_async` 在 `app.layer2_cost_recording`（不在 `app.layer2_cost_tracker`），test patch path 會失效。

**解決方案**（必入 prompt template）:
1. **Recommended**: 主檔 import + re-export `_invalidate_h_state_async` (`from .layer2_cost_recording import _invalidate_h_state_async  # noqa: F401`) — patch path 仍指 `app.layer2_cost_tracker._invalidate_h_state_async` 但實際 reference 在 sibling — 但這 **不能正確 patch** sibling 的呼叫點（Python patch 需 patch import 點，非定義點）
2. **Alternative**: test 同步更新 patch path 為 `app.layer2_cost_recording._invalidate_h_state_async` — E1 prompt 必含此 test patch 升級

E1 採 Alternative — 同步更新 26 test reference。grep 工作量小（4-5 patch site）。

**Pros**:
- 100% 沿襲 §14.1 既有模式
- 主檔 ~480 LOC 餘 320 LOC headroom（足以容納 G3-09 + Phase 4-5 snapshot 擴展）
- sibling 內聚清晰：cost recording 集中 / adaptive 集中 / H state snapshots 集中
- E1 工時 ~3-4h 落地

**Cons**:
- Test patch path 升級（4-5 patch site，10 min E1 工作量）
- 4 sibling 增加檔案數 — 與 §14.1 既有 9 sibling 模式對齊無實質負擔

### 6.2 Method B — 2-sibling 大塊化（次選）

只拆 2 sibling: `layer2_cost_recording.py` 含 cost recording + adaptive + h_state snapshots（~480 LOC）, 主檔留剩餘 ~480 LOC。

**Pros**:
- 較少 sibling 檔案（2 vs 4）
- 主檔 LOC 同 Method A

**Cons**:
- ★ sibling 檔 480 LOC 接近 §七 800 警告線 — Phase 4 + G3-09 後即觸警告區，**不解決 plan-ahead 目標**
- 內聚性差 — adaptive logic 與 cost recording 不必綁
- 後續再拆 = 2 階段 wave 工作

### 6.3 Method C — Comment-only segmentation（拒絕）

930 LOC 仍未超 §九 1200 hard cap，可只加 region comment 不拆檔。

**Pros**:
- 0 工時 0 風險
- Pre-G3-09 也無觸 §九 hard cap 風險

**Cons**:
- ★ 不解 PM Tier 8 sign-off 真實目標：plan ahead with Strategist split
- ★ G3-09 cost_edge_ratio implementation +50-100 LOC + Phase 4 snapshot 持續擴 = 6 個月內必撞 §九 hard cap，到時 emergency split 風險高
- ★ 既有 docstring 在 get_h5_snapshot（82 LOC）和 get_h2_snapshot（53 LOC）兩處 = 135 LOC 雙語 docstring 集中於 snapshot 區域，不拆 = 主檔 readability 降低

### 6.4 推薦 Method A

**Recommend Method A — 4-sibling pattern**:
- 主檔 ~480 LOC（well under §七 800，留 320 headroom for G3-09 + Phase 4 expansion）
- 3 新 sibling: `layer2_cost_recording.py` (~210) + `layer2_adaptive.py` (~120) + `layer2_h_state_snapshots.py` (~150)
- E1 工時 ~3-4h，沿襲 G5-04 ai_service split 模式
- Test patch path 升級 4-5 site（部分 prompt template）

---

## § 7. layer2_cost_tracker.py 完整 sibling list + LOC 預估

### 7.1 拆分後 sibling list

| File | Existing/New | LOC（前）| LOC（後）| Δ |
|---|---|---|---|---|
| `layer2_cost_tracker.py` (主檔) | Existing | 930 | **~480** | -450 |
| `layer2_cost_recording.py` | **NEW** | 0 | **~210** | +210 |
| `layer2_adaptive.py` | **NEW** | 0 | **~120** | +120 |
| `layer2_h_state_snapshots.py` | **NEW** | 0 | **~150** | +150 |
| `layer2_engine.py` | Existing (不動) | ? | unchanged | 0 |
| `layer2_routes.py` | Existing (不動) | ? | unchanged | 0 |
| `layer2_types.py` | Existing (不動) | ? | unchanged | 0 |
| `layer2_tools.py` | Existing (不動) | ? | unchanged | 0 |
| `layer2_escalation.py` | Existing (不動) | ? | unchanged | 0 |
| **TOTAL Δ** | | **930** | **~960** | +30 |

LOC 淨增 ~30（docstring 跨 sibling 重複 + import header 重複）— 可接受。

### 7.2 主檔 sibling re-export pattern

```python
# === In layer2_cost_tracker.py 主檔 ===
from .layer2_cost_recording import (  # noqa: F401 — re-export for back-compat
    record_claude_cost as _r_record_claude_cost,
    record_search_cost as _r_record_search_cost,
    record_call as _r_record_call,
    record_ollama_call as _r_record_ollama_call,
    reset_today_costs as _r_reset_today_costs,
)
from .layer2_adaptive import (  # noqa: F401
    recalculate_adaptive as _a_recalculate_adaptive,
    get_adaptive_state as _a_get_adaptive_state,
    get_cost_edge_ratio as _a_get_cost_edge_ratio,
)
from .layer2_h_state_snapshots import (  # noqa: F401
    get_h2_snapshot as _h_get_h2_snapshot,
    get_h5_snapshot as _h_get_h5_snapshot,
)

class Layer2CostTracker:
    # ... persistence + daily budget + session mgmt + pricing/config + summary 留主檔
    
    def record_claude_cost(self, session, input_tokens, output_tokens, model_tier):
        """Backward-compatible delegator to layer2_cost_recording / 向後兼容委託"""
        return _r_record_claude_cost(self, session, input_tokens, output_tokens, model_tier)
    
    def get_h2_snapshot(self):
        """Backward-compatible delegator to layer2_h_state_snapshots / 向後兼容委託"""
        return _h_get_h2_snapshot(self)
    # ... etc
```

### 7.3 Test patch path 升級

```python
# === Old test pattern (test_layer2.py + test_h_state_query_handler.py) ===
with patch("app.layer2_cost_tracker._invalidate_h_state_async") as mock_inv:
  cost_tracker.record_claude_cost(session, 100, 200, "sonnet")
  ...

# === New test pattern (after split) ===
with patch("app.layer2_cost_recording._invalidate_h_state_async") as mock_inv:
  cost_tracker.record_claude_cost(session, 100, 200, "sonnet")
  ...
```

E1 grep 4-5 site（test_layer2.py:375, 399, 525, 551 + test_h_state_query_handler.py 對應 site）並更新 patch path。

### 7.4 G3-09 cost_edge_ratio implementation 落地點

**Sibling**：`layer2_adaptive.py`
**理由**:
- `get_cost_edge_ratio()` 已在此 sibling
- G3-09 演算法擴展（含 cap binding / cost_edge_ratio threshold check）= adaptive logic 的延伸
- Rust hot-path 整合（Phase 3 Sub-task 3-3 H5 已 wired，G3-09 = read path 上層）
- 預期 +50-100 LOC → sibling LOC ~120 → ~220（仍 < 警告線）

---

## § 8. 撞檔風險矩陣

### 8.1 Strategist split + cost_tracker split 同 wave 並行 vs 序列

**並行 dispatch（Track A + Track B 同時派 2 E1）**:

| 共享檔案 | 撞檔風險 |
|---|---|
| `app/strategist_agent.py` | Track A only — 0 撞 |
| `app/layer2_cost_tracker.py` | Track B only — 0 撞 |
| 4 新 sibling (Track A) | 全 NEW，0 撞 |
| 3 新 sibling (Track B) | 全 NEW，0 撞 |
| `tests/test_strategist_agent.py` | Track A only — 0 撞 |
| `tests/test_layer2.py` | Track B only — 0 撞 |
| `tests/test_h_state_query_handler.py` | **Track A + Track B 都需 grep validation** ★ |
| `tests/test_strategist_audit_wiring.py` | Track A spillover risk（agent fixtures share infra）★ |
| `app/strategy_wiring.py` | Track A + Track B 都 import — 但只 grep 確認 BWD compat 無變動，不 edit ★ |

**結論**：並行 OK，但 PM 編排時 prompt template **必明確聲明** Track A / Track B 各自不動共享 test 檔（測試只新增 sibling 內單測，不擾既有 fixture）。

**序列 dispatch（先 A 後 B 或反之）**:
- Track A 先（hard pre-condition for Phase 4） → 落地 `e_<hash>` → 派 Track B → ETA 慢 ~50% but 0 撞檔
- Track B 先（無人 ahead-of-need 時序需求） → 不推薦（A 是 hard pre-condition，B 可拖延）

**PM 編排建議**: **並行 dispatch**（同 PM Tier 派發，Track A worktree + Track B worktree 各 isolation）— 但 Track A 必先 push first（PM merge 順序），確保 Phase 4 unblock 路徑優先。

### 8.2 isolation 需求

| Track | isolation 需求 | 理由 |
|---|---|---|
| Track A (Strategist split) | **YES — worktree** | 主檔 1200 LOC 改動大宗 + 4 sibling 新增 + test patch path 同步；與 Track B 獨立但工作面積大 |
| Track B (cost_tracker split) | **YES — worktree** | 主檔 930 LOC 改動 + 3 sibling 新增 + 4-5 test patch path 升級；與 Track A 獨立但同 wave 並行避免 main branch 雙改競態 |

**沿用 §六 動態 isolation 派工準則**：「並行 ≥2 sub-agent 操作不重疊檔 → NOT isolation」— 但本案兩 track **改動面積各超 600 LOC**（不只是「不重疊」），且涉及 test 多個 patch path 升級，per-invocation isolation 安全。

### 8.3 下游 caller import 影響

**Strategist split 後**:
- `strategy_wiring.py:154 from .strategist_agent import StrategistAgent, StrategistConfig` — **0 變動**（主檔 namespace 仍含這 2 symbol）
- `tests/test_strategist_agent.py 8 import call` — **0 變動**（含 `EdgeEvaluation` re-export from strategist_models 已既有）

**cost_tracker split 後**:
- `layer2_engine.py:65 from .layer2_cost_tracker import Layer2CostTracker` — **0 變動**
- `layer2_routes.py:42 from .layer2_cost_tracker import Layer2CostTracker` — **0 變動**
- `strategy_wiring.py:161 from .layer2_cost_tracker import Layer2CostTracker` — **0 變動**
- `tests/test_layer2.py 26 reference` — **0 變動 except 4-5 patch path**

### 8.4 multi-session race 防護

當前 git status:
```
M docs/CCAgentWorkSpace/PA/memory.md          # 隔壁 PA WIP — 不動
?? docs/CCAgentWorkSpace/Operator/2026-04-26--strkusdt_dust_spiral_rca.md  # 隔壁 untracked — 不動
?? docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md  # 隔壁 untracked — 不動
```

**本 RFC commit 用 `git commit --only`** 隔離隔壁 WIP（per memory `feedback_git_commit_only_for_metadoc`）：
```bash
git add docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase4_split_plan.md
git commit --only docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase4_split_plan.md
git push origin main
```

**注意**：PA memory.md 追加未在本 commit（隔壁 PA session 可能正改寫此檔）。為遵守 multi-session 協議，本 PA agent 完成序列追加 memory.md **單獨** 一次 `git commit --only docs/CCAgentWorkSpace/PA/memory.md` 並 push（兩次 commit，避免合併 commit 中 memory.md 與 RFC 雙改）。

---

## § 9. E1 prompt template Part A — Strategist split

**Self-contained ready-to-paste**（PM 下次 session 0 額外 context）。

```
═══════════════════════════════════════════════════════════════════════════════
@E1 G3-08-PHASE-4-STRATEGIST-SPLIT — Strategist Agent 4-sibling Split
═══════════════════════════════════════════════════════════════════════════════

## 背景
PM Tier 8 sign-off `e5f1b2d` follow-up #1 (MED, hard pre-condition for Phase 4 5-Agent
Strategist sub-task)：strategist_agent.py 1200 LOC = §九 hard cap exact-touch；任何
+1 LOC = silent §九 violation。Phase 4 Strategist sub-task 加任何 LOC 必先拆檔。

## 必讀
1. PA design RFC: docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase4_split_plan.md
   - §2 strategist_agent.py 全文 audit + logical grouping
   - §4 完整 sibling list + LOC 預估
2. 既有 §14.1 sibling reference (參考模式):
   - app/strategist_models.py (167 LOC, re-export pattern)
   - app/strategist_fast_channel.py (93 LOC, module-level fn pattern)
   - app/h1_thought_gate.py (368 LOC, class-based sibling)

## 工作範圍
拆 strategist_agent.py 1200 LOC 為 1 主檔 + 3 新 sibling，採 Method A (per RFC §3.4):

A1. 創建 app/strategist_edge_eval.py (~280 LOC)
    - 移入 6 method (現有 strategist_agent.py 內) 為 module-level fn 接 `agent: 'StrategistAgent'` 第一參數:
      * _evaluate_edge (line 892-913)
      * _ai_evaluate (line 915-1005)
      * _evaluate_edge_l1_5 (line 748-767)
      * _build_prompt_context (line 801-888)
      * _process_knowledge_update (line 769-797)
      * _build_route_context (line 724-746)
    - 加 雙語 MODULE_NOTE + import header (含 from typing import TYPE_CHECKING + if TYPE_CHECKING: from .strategist_agent import StrategistAgent)

A2. 創建 app/strategist_weights.py (~140 LOC)
    - 移入 6 method 為 module-level fn:
      * set_budget_manager (line 579-593)
      * set_truth_registry (line 595-604)
      * _apply_pattern_insight (line 606-633)
      * get_strategy_weight (line 635-665)
      * _apply_regime_weights (line 667-694)
      * _apply_l2_weight_update (line 696-720)
    - 加 雙語 MODULE_NOTE + import header

A3. 創建 app/strategist_cognitive.py (~110 LOC)
    - 移入 4 method:
      * handle_fast_channel (line 1052-1099)
      * clear_emergency_mode (line 1101-1110)
      * set_cognitive_modulator (line 1114-1126)
      * _apply_cognitive_modulation (line 1128-1152)
    - 加 雙語 MODULE_NOTE + import header

A4. 修改 app/strategist_agent.py (1200 → ~710 LOC)
    - 在 import block 加 3 個 sibling re-export (per RFC §4.3):
      ```python
      from .strategist_edge_eval import (  # noqa: F401
          _evaluate_edge as _se_evaluate_edge,
          _ai_evaluate as _se_ai_evaluate,
          _evaluate_edge_l1_5 as _se_evaluate_edge_l1_5,
          _build_prompt_context as _se_build_prompt_context,
          _process_knowledge_update as _se_process_knowledge_update,
          _build_route_context as _se_build_route_context,
      )
      from .strategist_weights import (  # noqa: F401
          set_budget_manager as _sw_set_budget_manager,
          set_truth_registry as _sw_set_truth_registry,
          _apply_pattern_insight as _sw_apply_pattern_insight,
          get_strategy_weight as _sw_get_strategy_weight,
          _apply_regime_weights as _sw_apply_regime_weights,
          _apply_l2_weight_update as _sw_apply_l2_weight_update,
      )
      from .strategist_cognitive import (  # noqa: F401
          handle_fast_channel as _sc_handle_fast_channel,
          clear_emergency_mode as _sc_clear_emergency_mode,
          set_cognitive_modulator as _sc_set_cognitive_modulator,
          _apply_cognitive_modulation as _sc_apply_cognitive_modulation,
      )
      ```
    - 替換主檔 16 method body 為 1-line delegator:
      ```python
      def _ai_evaluate(self, intel: IntelObject) -> EdgeEvaluation:
          """Backward-compatible delegator to strategist_edge_eval / 向後兼容委託"""
          return _se_ai_evaluate(self, intel)
      ```
    - 主檔保留: ctor + class attrs + start/stop + on_message + _handle_intel + _produce_intents
      + 3 message handler + status accessors (4) + BWD compat delegators (5) + 3 個 1-line
      delegator group (16 個)
    - 主檔 LOC 目標: ~710 (well under §七 800 警告線)

A5. 不動 test files (per RFC §4.4):
    - test_strategist_agent.py: 既有 import `from app.strategist_agent import StrategistAgent,
      StrategistConfig, EdgeEvaluation` 仍 work（主檔 namespace 含三者）
    - 任何 patch path 改動: 非必要 — 既有 patch 用 `app.strategist_agent.<symbol>`，主檔
      delegator 仍是 active patchable surface

## 完成標準
1. wc -l app/strategist_agent.py → ~710 (well < 800)
2. wc -l app/strategist_edge_eval.py → ~280
3. wc -l app/strategist_weights.py → ~140
4. wc -l app/strategist_cognitive.py → ~110
5. pytest tests/test_strategist_agent.py → green (既有 41 test 全綠)
6. pytest tests/test_strategist_audit_wiring.py → green
7. pytest tests/test_h_state_query_handler.py → green (52 test 全綠)
8. pytest tests/test_batch7_conductor_strategist.py → green
9. cargo lib (Linux) → 不變 (Phase 3 baseline 2212/0; Track A 純 Python)
10. grep 'from app.strategist_agent import' tests/ → 全部仍有效解析
11. grep 'StrategistAgent\|StrategistConfig\|EdgeEvaluation' app/ → 全 callsite 仍 work

## 工時預估
~3-4h E1 + 1-1.5h E2 review + 1-2h E4 regression = 5-7h 全鏈

## Hard rules
- ❌ 不破壞 test patch path (`app.strategist_agent.<symbol>` 全保留)
- ❌ 不改業務邏輯（純 file structure refactor）
- ❌ 不動 helper_scripts / Rust / docs (除 PR description)
- ✅ commit 一次（4 sibling + 主檔同 commit），便於 E2 review
- ✅ commit message 明示 LOC 變化: "1200 → ~710" + "+3 sibling NEW"
- ✅ 雙語 MODULE_NOTE / docstring 必含

## 高風險警告（E2 必查 3 點）
1. ★ Method body 委託後 `self.cost_tracker` / `self._stats` / `self._lock` 在 sibling fn
   裡仍能正確 access — 因 sibling fn 第一參 `agent` 是 StrategistAgent instance
2. ★ Re-export `noqa: F401` 不可漏 — 主檔 namespace 必須仍能解析所有 BWD compat symbol
3. ★ E2 spot-check `_handle_intel` (197 LOC 主編排，**不拆**) readability NOT degraded

═══════════════════════════════════════════════════════════════════════════════
```

---

## § 10. E1 prompt template Part B — cost_tracker split

**Self-contained ready-to-paste**（PM 下次 session 0 額外 context）。

```
═══════════════════════════════════════════════════════════════════════════════
@E1 G3-08-PHASE-4-COST-TRACKER-SPLIT — Layer2CostTracker 4-sibling Split
═══════════════════════════════════════════════════════════════════════════════

## 背景
PM Tier 8 sign-off `e5f1b2d` follow-up #2 (LOW, plan ahead with Strategist split)：
layer2_cost_tracker.py 930 LOC 超 §七 800 警告線 +130；G3-09 cost_edge_ratio 預期
+50-100 LOC + Phase 4-5 snapshot 持續擴 → 6 個月內必撞 §九 1200 hard cap。

## 必讀
1. PA design RFC: docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase4_split_plan.md
   - §5 layer2_cost_tracker.py 全文 audit + logical grouping
   - §7 完整 sibling list + LOC 預估
2. 既有 §14.1 sibling reference: 同 Track A

## 工作範圍
拆 layer2_cost_tracker.py 930 LOC 為 1 主檔 + 3 新 sibling，採 Method A (per RFC §6.4):

B1. 創建 app/layer2_cost_recording.py (~210 LOC)
    - 移入 9 method 為 module-level fn 接 `tracker: 'Layer2CostTracker'` 第一參數:
      * record_claude_cost (line 382-428, 含 H2 + H5 dual invalidate hint)
      * record_search_cost (line 430-457, 含 H5 invalidate hint)
      * _add_daily_claude_cost (line 459-466)
      * _sync_to_rust_budget (line 468-502)
      * _add_daily_search_cost (line 504-511)
      * _increment_daily_session_count (line 513-520)
      * record_call (line 736-799, unified entry point)
      * record_ollama_call (line 803-831, deprecated wrapper)
      * reset_today_costs (line 909-922)
    - 移入 module-level: `_invalidate_h_state_async` import (從 .h_state_invalidator)
    - 加 雙語 MODULE_NOTE + import header

B2. 創建 app/layer2_adaptive.py (~120 LOC)
    - 移入 3 method 為 module-level fn 接 `tracker` 第一參數:
      * recalculate_adaptive (line 583-646)
      * get_adaptive_state (line 648-649)
      * get_cost_edge_ratio (line 860-896)
    - 加 雙語 MODULE_NOTE + import header
    - **G3-09 future-proof**: docstring 註明此 sibling 是 cost_edge_ratio threshold check
      / cap binding 演算法後續實裝點

B3. 創建 app/layer2_h_state_snapshots.py (~150 LOC)
    - 移入 2 method:
      * get_h2_snapshot (line 243-295, 含 53 LOC 雙語 docstring)
      * get_h5_snapshot (line 297-378, 含 82 LOC 雙語 docstring)
    - 加 雙語 MODULE_NOTE + import header
    - 注意 docstring 內 line ref（如 `rust/openclaw_engine/src/h_state_cache/types.rs:58-72`）
      在 sibling 中引用方式不變

B4. 修改 app/layer2_cost_tracker.py (930 → ~480 LOC)
    - 在 import block 加 3 個 sibling re-export (per RFC §7.2):
      ```python
      from .layer2_cost_recording import (  # noqa: F401
          record_claude_cost as _r_record_claude_cost,
          record_search_cost as _r_record_search_cost,
          record_call as _r_record_call,
          record_ollama_call as _r_record_ollama_call,
          reset_today_costs as _r_reset_today_costs,
          # private helpers (used by sibling) NOT re-exported
      )
      from .layer2_adaptive import (  # noqa: F401
          recalculate_adaptive as _a_recalculate_adaptive,
          get_adaptive_state as _a_get_adaptive_state,
          get_cost_edge_ratio as _a_get_cost_edge_ratio,
      )
      from .layer2_h_state_snapshots import (  # noqa: F401
          get_h2_snapshot as _h_get_h2_snapshot,
          get_h5_snapshot as _h_get_h5_snapshot,
      )
      ```
    - 替換主檔 14 method body 為 1-line delegator
    - 主檔保留: ctor + persistence (load/save/_apply_state/_read_raw/_write_raw)
      + daily budget (5 method) + session mgmt (4 method) + pricing/config (4 method)
      + summary + ollama_stats + check methods + delegators
    - 主檔 LOC 目標: ~480 (well under §七 800; ~320 LOC headroom for G3-09 + Phase 4)

B5. 升級 test patch path (per RFC §7.3, 4-5 site):
    - tests/test_layer2.py:375 → patch path "app.layer2_cost_tracker._invalidate_h_state_async"
      改為 "app.layer2_cost_recording._invalidate_h_state_async"
    - tests/test_layer2.py:399 → 同
    - tests/test_layer2.py:525 → 同
    - tests/test_layer2.py:551 → 同
    - tests/test_h_state_query_handler.py 對應 site → grep verify (可能 0 site，看 test 結構)
    - 不動 test 邏輯 — 純 patch path 更新

## 完成標準
1. wc -l app/layer2_cost_tracker.py → ~480 (well < 800)
2. wc -l app/layer2_cost_recording.py → ~210
3. wc -l app/layer2_adaptive.py → ~120
4. wc -l app/layer2_h_state_snapshots.py → ~150
5. pytest tests/test_layer2.py → green (既有 82 test + 之前 +15 H5 test 全綠)
6. pytest tests/test_h_state_query_handler.py → green (52 test 全綠)
7. pytest tests/test_layer2_escalation.py → green
8. pytest tests/test_strategist_agent.py → green (cost_tracker injection path 不變)
9. cargo lib (Linux) → 不變 (Phase 3 baseline 2212/0; Track B 純 Python)
10. grep 'from .layer2_cost_tracker import' app/ → 3 site 仍解析正確
11. grep 'Layer2CostTracker' tests/ + app/ → 全 callsite 仍 work
12. patch path grep verify: `_invalidate_h_state_async` 在 layer2_cost_tracker namespace 已不存在
    （sibling 內），test patch path 全升級

## 工時預估
~3-4h E1 + 1-1.5h E2 review + 1-2h E4 regression = 5-7h 全鏈

## Hard rules
- ❌ 不破壞 cost_tracker SSOT — STRATEGIST_AGENT.cost_tracker singleton 仍 active
- ❌ 不改業務邏輯（純 file structure refactor）
- ❌ 不動 helper_scripts / Rust / docs (除 PR description)
- ✅ commit 一次（4 sibling + 主檔 + test patch path 同 commit），便於 E2 review
- ✅ commit message 明示 LOC 變化: "930 → ~480" + "+3 sibling NEW" + "test patch path 升級"
- ✅ 雙語 MODULE_NOTE / docstring 必含

## 高風險警告（E2 必查 3 點）
1. ★ `_sync_to_rust_budget` 內部用 `import threading; import asyncio` 動態 import 是 hot-path
   — sibling 拆出後仍走 module-level fn，不破壞既有 daemon-thread fire-and-forget pattern
2. ★ `record_claude_cost` 末尾 dual invalidate hint (`h2.budget_consumed` + `h5.claude_cost_recorded`)
   保留 emit order 不變 — Sub-task 3-3 RFC §6 + §8.2 thread safety contract 不可破
3. ★ Test patch path 升級必 grep `_invalidate_h_state_async` 全 site 確保 0 漏改 — 漏改 = test
   patch 失效 silent pass 是反 #6 fail-closed 風險

═══════════════════════════════════════════════════════════════════════════════
```

---

## § 11. Phase 4 5-Agent + G3-09 cost_edge_ratio dependency unblock 路徑

### 11.1 Strategist split unblock Phase 4 Strategist sub-task

**Phase 4 5-Agent state events 設計**（per PM Tier 8 sign-off § 8 next-step）:
- 5 agents = Strategist / Guardian / Analyst / Executor / Scout
- 鏡 Phase 3 per-module sub-task split pattern（Sub-task 4-1 Strategist / 4-2 Guardian / etc.）
- 每 sub-task 預期加 ~30-60 LOC 到對應 agent class（get_<agent>_snapshot() + invalidate hooks）

**Strategist sub-task 預期改動**:
- 加 `get_strategist_snapshot(self) -> Dict[str, Any]` method 到 `app/strategist_agent.py`（~30-60 LOC）
- 接 invalidate hook 到 `_handle_intel` / `_produce_intents` 等熱路徑（~10-20 LOC）
- LOC 預估 +40-80 LOC

**未拆檔 vs 拆檔影響**:
- 未拆: 主檔 1200 + 80 = **1280 LOC** → §九 1200 hard cap **violation**（必拒派發）
- 拆後: 主檔 ~710 + 80 = **~790 LOC** → 仍 < §七 800 警告線 √

**Phase 4 Strategist sub-task ready-to-deploy 條件**:
1. ✅ Track A (G3-08-PHASE-4-STRATEGIST-SPLIT) commit landed + E2 PASS
2. ✅ 主檔 LOC < 750（足以容納 +40-80 LOC 而不觸警告線）
3. ✅ Test cov: tests/test_strategist_agent.py 全綠（baseline 不變）
4. ✅ PA Phase 4 5-Agent design RFC 完成（鏡 Phase 3 §6 prompt template，詳 PM next session 派發）

### 11.2 cost_tracker split unblock G3-09 cost_edge_ratio

**G3-09 cost_edge_ratio implementation 設計**（per PM Tier 8 sign-off § 8 next-step）:
- PA design RFC 階段（待 PM 下 wave 派發）
- E1 落地階段（演算法 + Rust hot-path 整合 + IPC 接口）

**Implementation 預期改動**:
- `app/layer2_adaptive.py`（拆後 sibling）+ `get_cost_edge_ratio()` 擴展（threshold check + cap binding logic）= ~50-100 LOC
- Rust hot-path consumer（`rust/openclaw_engine/src/governor/...`）= ~30-60 LOC
- IPC 接口（cost_edge_ratio query + threshold patch）= ~20-40 LOC

**未拆檔 vs 拆檔影響**:
- 未拆: 主檔 930 + 100 = **1030 LOC** → 觸 §九 1200 hard cap 距離縮至 170 LOC（Phase 4-5 snapshot 加完即破）
- 拆後: sibling `layer2_adaptive.py` 120 + 100 = **~220 LOC** → 仍 < §七 800 警告線 √

**G3-09 ready-to-deploy 條件**:
1. ✅ Track B (G3-08-PHASE-4-COST-TRACKER-SPLIT) commit landed + E2 PASS
2. ✅ Sibling `layer2_adaptive.py` < 200 LOC（足以容納 +50-100 LOC）
3. ✅ Test patch path 升級全 done（test_layer2.py 不破）
4. ✅ PA G3-09 cost_edge_ratio design RFC 完成（待 PM 下 wave 派發）

### 11.3 Phase 4 + G3-09 派發時序圖

```
Wave N (本 RFC 推薦時序):
  ┌─────────────────────────────────────────────────────────────┐
  │ T+0:  PM 派發 Track A + Track B 同 wave 並行（worktree）       │
  │ T+5h: Track A E1 commit landed                                 │
  │ T+5h: Track B E1 commit landed                                 │
  │ T+7h: E2 review Track A + Track B (1.5h each)                  │
  │ T+9h: E4 regression Track A + Track B (1-2h each)              │
  │ T+10h: PM Sign-off — 兩 split commit merged                    │
  └─────────────────────────────────────────────────────────────┘

Wave N+1 (Phase 4 5-Agent + G3-09 並行):
  ┌─────────────────────────────────────────────────────────────┐
  │ T+0:  PM 派發 PA Phase 4 5-Agent design RFC                   │
  │ T+0:  PM 派發 PA G3-09 cost_edge_ratio design RFC (並行)      │
  │ T+1d: PA 兩 RFC 完成                                          │
  │ T+1d: PM 派發 5 sub-task (4-1 Strategist + 4-2-5 其他 4 agent) │
  │       + G3-09 implementation                                   │
  │ T+5d: 全鏈 E1 + E2 + E4 完成                                  │
  └─────────────────────────────────────────────────────────────┘
```

### 11.4 沒做的事 / 不在範圍

- ❌ 沒寫 split 實作代碼（per Hard rules，PA = design only）
- ❌ 沒派 sub-agent（純 PA RFC，主 agent 串行讀+寫）
- ❌ 沒設計 Phase 4 5-Agent 詳細 sub-task split（待 PM 下 wave 派發 PA）
- ❌ 沒設計 G3-09 cost_edge_ratio 演算法（待 PM 下 wave 派發 PA）
- ❌ 沒擴範圍到其他 §七 警告區檔案（如 healthcheck.py 2286 / helpers.rs 1315 — 屬 G5 backlog）

---

## § 12. PA 結論

| 項 | 結論 |
|---|---|
| **Strategist split** | Method A 4-sibling pattern（主檔 ~710 + 3 新 sibling: edge_eval ~280 / weights ~140 / cognitive ~110）|
| **cost_tracker split** | Method A 4-sibling pattern（主檔 ~480 + 3 新 sibling: cost_recording ~210 / adaptive ~120 / h_state_snapshots ~150）|
| **撞檔風險** | 並行 dispatch with worktree isolation — 兩 track 物理隔離 0 撞，PM 編排 Track A 先 push 確保 Phase 4 unblock 路徑優先 |
| **下游影響** | Strategist callsite 0 變動 / cost_tracker callsite 0 變動 / test 4-5 patch path 升級（cost_tracker only） |
| **工時** | Track A 5-7h 全鏈 / Track B 5-7h 全鏈，並行下整 wave ~10h wall-clock |
| **Phase 4 unblock** | ✅ Track A 完即可派 Phase 4 Strategist sub-task（主檔 LOC ~710 + 80 = 790 < §七 800）|
| **G3-09 unblock** | ✅ Track B 完即可派 G3-09 cost_edge_ratio implementation（sibling LOC 120 + 100 = 220 < §七 800）|

### 16 原則對照

| # | 原則 | 對 split 影響 |
|---|---|---|
| 1 單一寫入口 | n/a — 純 file refactor，無交易 path 改動 |
| 2 讀寫分離 | n/a |
| 3 AI ≠ 命令 | n/a |
| 4 策略不繞風控 | n/a |
| 5 生存 > 利潤 | n/a |
| 6 失敗默認收縮 | ✅ test patch path 升級 = E1 必 grep 全 site，漏 = silent test pass 是反 #6 風險 — Hard rule §10.B5 已明示 |
| 7 學習 ≠ 改 Live | n/a |
| 8 可解釋 | ✅ split 不影響 audit log path |
| 9 災難保護 | n/a |
| 10 認知誠實 | ✅ docstring 中 `roi_basis="paper_simulation_only"` 標記在 H5 snapshot 拆出後仍保留（layer2_h_state_snapshots.py） |
| 11 Agent 自主 | n/a |
| 12 持續進化 | n/a |
| 13 AI 成本感知 | ✅ Track B 是 G3-09 cost_edge_ratio implementation 的 hard pre-condition，直接強化 #13 |
| 14 零外部成本 | n/a |
| 15 多 Agent 協作 | ✅ Track A 是 Phase 4 5-Agent state events 的 hard pre-condition，直接強化 #15 |
| 16 組合風險 | n/a |

### 硬邊界（CLAUDE.md §四）對照

- ❌ **0 觸碰** live_execution_allowed / max_retries / decision_lease_emitted / OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json — 兩 split 純 file structure refactor
- ❌ **0 觸碰** 5 真實 live 門控 — 不影響 secret slot / Operator role / live_reserved global mode

### DOC-08 §12 9 條安全不變量對照

- ✅ 全 9 條保留 — 兩 split 不改 pre-trade audit / lease / fills 路徑 / 風控降級 / authorization / OPENCLAW_ALLOW_MAINNET / Bybit fail-closed / Reconciler / Operator role

---

**PA Sign-off**: design RFC 完成，ready for PM 下 wave 派發。Track A + Track B 並行 dispatch with worktree isolation 推薦。

**PA timestamp**: 2026-04-26 CEST
