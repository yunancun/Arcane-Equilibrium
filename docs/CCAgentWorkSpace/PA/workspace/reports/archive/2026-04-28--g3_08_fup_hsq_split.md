# G3-08-FUP-HSQ-SPLIT P2 — h_state_query_handler.py sibling extraction

**Date**: 2026-04-28
**Mode**: PA + E1 + sanity test 三角合一（主會話授權）
**Base HEAD**: `8a5973f` (origin/main)
**Worktree**: `/Users/ncyu/Projects/TradeBot/srv` (no commit per instruction)

## 背景

Wave E SINGLETON fix（commit `b579dae`）為 `_collect_h_snapshots` + `_collect_agent_snapshots` 加入 dual `sys.modules.get` pattern (+33 LOC, 28 雙語 rationale)。`h_state_query_handler.py` 從 826 → 859 LOC，超過 CLAUDE.md §九 800 LOC 警告線。E2 SINGLETON review LOW-1 推薦抽 sibling `h_state_collectors.py`（含 `_collect_h_snapshots` + `_collect_agent_snapshots`）。本 ticket 為 G3-08-FUP-HSQ-SPLIT P2（Phase 4 ~900 LOC 預估的延續）。

## 設計決策

**Sibling 命名**：`h_state_collectors.py`（per E2 推薦，與 `cost_edge_advisor_boot.py` split pattern 同源）

**抽出範圍**（4 函式）：
- `_collect_h_snapshots`（含 SINGLETON fix sys.modules.get @ line 358）
- `_collect_agent_snapshots`（含 SINGLETON fix sys.modules.get @ line 502）
- `_safe_snapshot`
- `_safe_snapshot_self`

**保留於 handler**（envelope assembly + schema）：
- `build_h_state_full_response`（公開 API）
- Schema 常數（`_PHASE2_VERSION` / `_PHASE1_FALLBACK_VERSION` / `_H_BUCKET_KEY` / `_AGENT_BUCKET_KEY` / `_GATEWAY_ENV_VAR` / `_GATEWAY_ENABLED_VALUE`）
- `_is_gateway_enabled` env-gate helper
- 完整 MODULE_NOTE 雙語

**Re-export 策略**（delegator pattern）：
handler 頂部 `from .h_state_collectors import _collect_agent_snapshots, _collect_h_snapshots, _safe_snapshot, _safe_snapshot_self`（noqa: F401），所有既有 `from app.h_state_query_handler import _safe_snapshot`（測試共 ~50+ patch sites）零修改繼續工作。

**SINGLETON fix 保護**：sys.modules.get pattern 與兩 collector 一同原子搬移，新 sibling 內**逐行保留**完整 28 行雙語 rationale（含 G3-08-PHASE-FUP-IMPORT-PATH-LEAK 註解標識）。test_h_state_query_handler.py:322 `_install_fake_strategy_wiring` dual patch fixture 機制不變。

## 實作

| 檔案 | Before | After | Δ |
|---|---|---|---|
| `h_state_query_handler.py` | 859 LOC | **452 LOC** | -407 |
| `h_state_collectors.py` (新) | — | **547 LOC** | +547 |
| 合計 | 859 | 999 | +140 (含新模組 docstring overhead) |

**Targets met**：
- handler ≤ 800 (首選): ✅ 452 (47% under)
- sibling ≤ 800: ✅ 547 (32% under)

## Verification

### Mac pytest 既有 h_state tests（critical）
```
test_h_state_query_handler.py: 90 passed in 0.04s
```

### Same-session test（critical for SINGLETON fix integrity）
```
test_api_contract.py + test_h_state_query_handler.py: 108 passed in 1.42s
```
**108/108 PASS**，與 split 前 baseline 完全一致 — Wave E SINGLETON `sys.modules.get` 邏輯隨 fn 移後仍生效，`importlib.reload(main_legacy/main)` 後 fixture 仍可有效 patch。

### W1+W2+W3 + Strategist regression
```
test_h_state_query_handler.py + test_h_state_invalidator.py + test_h1_thought_gate.py +
test_model_router.py + test_strategist_agent.py + test_strategist_cognitive_integration.py +
test_strategist_audit_wiring.py + test_api_contract.py: 234 passed in 1.66s
```
**234/234 PASS** 零退化。

## 副作用清單（已驗）

1. **Test patch sites**（~50+ `from app.h_state_query_handler import _safe_snapshot[_self]` / `_collect_agent_snapshots`）— ✅ re-export 透明，0 改動
2. **Production callers**（`ai_service_dispatch.py:832` lazy import `build_h_state_full_response`，`passive_wait_healthcheck/checks_derived.py:806`）— ✅ 公開 API 名稱不變
3. **`_install_fake_strategy_wiring` dual patch fixture**（test_h_state_query_handler.py:322 同時 patch sys.modules + parent attribute）— ✅ 仍有效，108 same-session 測試證明
4. **SINGLETON `sys.modules.get` lookup key**（`"app.strategy_wiring"`）— ✅ collector 內字串 literal 完整保留
5. **Module-level logger**（`logger = logging.getLogger(__name__)`）— sibling 用自身 `__name__`（即 `app.h_state_collectors`），DEBUG log 來源更精確（理想副效果，非破壞）

## 邊界遵守

- ✅ 嚴格 `h_state_query_handler.py` only — 0 觸 strategist_agent.py / strategy_wiring.py
- ✅ 0 production behaviour change（純 code move + re-export，函式 body 一字未改）
- ✅ SINGLETON fix sys.modules.get pattern 100% 保留（含 28 行雙語 rationale）
- ✅ test_h_state_query_handler.py / test_api_contract.py / test_strategist_*.py fixture 0 改動
- ✅ 雙語注釋（新模組 MODULE_NOTE + handler split rationale 添加段）
- ✅ 公開 API（`build_h_state_full_response`）schema / signature 不變
- ✅ `__all__` 在兩檔同步維護

## E2 重點審查 3 點

1. **SINGLETON fix 字串 literal 保留**：grep `"app.strategy_wiring"` 在 h_state_collectors.py 應出現 2 次（_collect_h_snapshots line ~158 + _collect_agent_snapshots line ~314），與 split 前 handler 內位置語意相同
2. **Re-export `noqa: F401` 註解**：handler 內 `from .h_state_collectors import` 必須含 `noqa: F401`（Python style checker 否則會誤報 unused import — 這 4 個 symbol 是給下游 test patch site 用的）
3. **MODULE_NOTE 雙語完整性**：新 sibling 含 G3-08-FUP-HSQ-SPLIT P2 來歷完整說明 + 4 函式公開接口表 + 設計約束清單；handler 在原 MODULE_NOTE 內加段說明 split + atomically-moved SINGLETON fix（中英對照）

## 風險評級

**低**（per CLAUDE.md PA profile §改動風險評級）— 顯示層下沉重構，無邏輯改動，完整 234 tests 覆蓋通過，SINGLETON fix integrity 三 layer 驗證（h_state alone 90 / same-session 108 / extended regression 234）。

## Follow-up（如未來 phase 4 進一步擴張）

若 H1+H2+H3+H4+H5 加 H6 / `agent_states` 加第 6 agent → collector 自然在 547 LOC sibling 內擴張，handler 維持 452 LOC 不再受壓。後續若 sibling 觸近 800 LOC → 二度拆 `h_collectors.py` vs `agent_collectors.py`（按 H bucket 與 5-Agent 分線）。

## 結論

PA design + E1 implementation + sanity test 全綠 — `h_state_query_handler.py` 859 → 452 LOC（首選 ≤ 800 達成），新 sibling `h_state_collectors.py` 547 LOC，SINGLETON fix 原子保留，108/108 same-session + 234/234 regression PASS。**0 production 行為改變，0 commit（worktree pattern per instruction）**。

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_08_fup_hsq_split.md
