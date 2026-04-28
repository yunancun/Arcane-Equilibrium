# PA+E1 合一 — SINGLETON-POLLUTION-EXECUTOR-SHADOW-TOGGLE-API + STRATEGIST-PROMOTE-API combined fix

**Date**: 2026-04-28 CEST
**HEAD**: `739af3c` (origin/main)
**Mode**: PA design + E1 implementation + sanity test 三角合一（main session 授權）
**Verdict**: **2 ticket fixed, 17→0 + 18→0 fail；全 same-session reproducible；0 production code 改動。**

---

## §1 TL;DR (≤200 字)

兩 ticket 同 sibling-pollution **family**（polluter 都是 `test_api_contract.py::build_client` 內 `importlib.reload(main_legacy)`），但 root cause **不同表現**：W3 SINGLETON 是 `from PKG import SUB` attribute precedence；本 wave 是 **FastAPI `Depends(base.current_actor)` route-build-time freeze**。`importlib.reload(main_legacy)` 後 `current_actor` 是新 function obj，但 `executor_routes.executor_router` / `strategist_promote_router` 的 `Depends()` 持的是 reload 前的舊 callable。`dependency_overrides[base.current_actor=新]` 對不上 router 內 frozen 的舊 → override 失效 → 401 unauthorized → 17+18 fail。**Fix = test fixture `_make_app` 內 `importlib.reload(executor_routes / strategist_promote_routes)` 重建 router，使其 Depends 重新 freeze 到 reload 後新 callable**。0 production code 改動（FastAPI freeze Depends 是標準語意，非 bug）。Option A only，無 Option B 必要。完整 control_api_v1 baseline 38 fail → 3 fail（剩 phase2_routes 3 個明確 out-of-scope per ticket bound）。

---

## §2 Reproducibility evidence

### §2.1 Baseline 確認 17+18 fail 真實數字

```bash
# 隔離跑 — 全綠
PYTHONPATH=. ./venvs/mac_dev/bin/pytest \
  test_executor_shadow_toggle_api.py test_strategist_promote_api.py -v
# → 35 passed in 0.30s

# 與 polluter 同跑 — 35 fail
PYTHONPATH=. ./venvs/mac_dev/bin/pytest \
  test_api_contract.py test_executor_shadow_toggle_api.py test_strategist_promote_api.py
# → 35 failed, 18 passed (test_api_contract 18 PASS + executor 17 fail + strategist 18 fail)

# 全 control_api_v1 baseline
PYTHONPATH=. ./venvs/mac_dev/bin/pytest control_api_v1/tests/ -q
# → 38 failed, 3077 passed (35 我的 scope + 3 phase2_routes out-of-scope)
```

### §2.2 Bisect 找 polluter — 確認與 W3 SINGLETON 同來源

`test_api_contract.py:16` `build_client()` 內：
```python
from app import main_legacy as legacy_module
importlib.reload(legacy_module)
from app import main as main_module
importlib.reload(main_module)
```

`importlib.reload(main_legacy)` rebind module 內每個 def — `current_actor` 變新 function obj。但 sys.modules["app.executor_routes"] 已 cache，不會 re-evaluate module-level code → `executor_router` 內 `Depends(base.current_actor)` 持的仍是 reload 前 callable。

### §2.3 Mechanism 直驗 — failing test trace

```
TestEngineWhitelist.test_invalid_engine_returns_400
  AssertionError: 401 != 400
```

401 = `current_actor` 走 token 驗證 path（dependency_overrides 沒 match），無 token → `HTTPException(401, "missing or invalid auth")`。確認 override 失效非 route 邏輯 bug。

---

## §3 Root cause 分析（與 W3 SINGLETON 比較）

| 項 | W3 SINGLETON (h_state_query) | 本 wave (executor + strategist) |
|---|---|---|
| Polluter | `test_api_contract.py importlib.reload(main_legacy + main)` | **同** |
| 機制 | CPython `from PKG import SUB` attr precedence — `app.strategy_wiring` attr 鎖定真模組 | FastAPI `Depends(callable)` route build 期 freeze callable obj，reload 換新 obj 後 frozen 仍指舊 |
| 是否 production bug | NO（fail-soft contract 認可 sys.modules.get pattern） | **NO**（Depends freeze 是 FastAPI 設計語意，非 bug） |
| Fix Option | Option B（production sys.modules.get）+ Option A（test dual-patch） | **Option A only**（test reload sub-module）— Option B 不適用 |
| ETA | 1.5-2h | **0.5h**（更輕量） |

**為什麼 Option B 不適用**：
- W3 case：production code `from . import strategy_wiring as _sw` 改 `sys.modules.get` 是純 lookup path 改動，runtime 等價。
- 本 wave：production code `Depends(base.current_actor)` 改成 `Depends(lambda: base.current_actor(...))` 會破壞 FastAPI 依賴注入 introspection（FastAPI 需要看 `current_actor` signature 來 inject `request` / `Header`），或得改成 wrapper class — 都是 **for testing only 而動 production**，違反「最小改動」原則。
- Test fixture `importlib.reload(executor_routes)` 內聚於 test code，0 production 風險。

---

## §4 Fix 實作 (Option A — test fixture)

### §4.1 改動清單

| 檔案 | 改動 | 行數 |
|---|---|---|
| `tests/test_executor_shadow_toggle_api.py:106-127` | `_make_app` 加 `importlib.reload(executor_routes)` + 雙語 docstring 註解 root cause | +24 -2 |
| `tests/test_strategist_promote_api.py:79-100` | `_make_app` 加 `importlib.reload(strategist_promote_routes)` + 雙語 docstring | +22 -2 |
| **TOTAL** | 純 test 端，0 production | +42 -4 |

### §4.2 Diff 核心片段（rep）

```python
def _make_app(actor: _FakeActor) -> FastAPI:
    """...雙語 docstring 解釋 sibling-pollution root cause..."""
    import importlib
    from app import executor_routes as _executor_routes_mod
    importlib.reload(_executor_routes_mod)  # rebuild router → fresh Depends freeze

    app = FastAPI()
    app.include_router(_executor_routes_mod.executor_router)
    from app import main_legacy as base
    app.dependency_overrides[base.current_actor] = lambda: actor
    return app
```

雙語 docstring per `feedback_bilingual_comment_style`，明確記錄 root cause + W3 對應 + 為何不動 production。

---

## §5 Verify

### §5.1 17→0 + 18→0 (隔離 + same-session)

```bash
# 隔離跑
pytest test_executor_shadow_toggle_api.py test_strategist_promote_api.py -v
# → 35 passed in 0.30s

# Critical same-session (with polluter)
pytest test_api_contract.py test_executor_shadow_toggle_api.py test_strategist_promote_api.py
# → 53 passed (was 35 failed + 18 passed)
```

### §5.2 既有 regression（W1+LOSSES+W2+W3+SINGLETON）

```bash
pytest test_h_state_query_handler.py test_strategist_cognitive_integration.py test_api_contract.py
# → 116 passed
```

### §5.3 完整 control_api_v1 baseline

```bash
pytest control_api_v1/tests/ -q
# Pre-fix:  38 failed, 3077 passed
# Post-fix:  3 failed, 3112 passed (剩餘 phase2_routes 3 個 out-of-scope per ticket bound)
```

### §5.4 跨平台

純 Python `importlib.reload` + FastAPI 標準 API，Mac/Linux 行為一致。Linux 端推論同樣可重現 17→0 + 18→0（建議 main session push 後 ssh trade-core 驗證一遍）。

---

## §6 邊界遵守

| 邊界 | 狀態 |
|---|---|
| 嚴格 2 ticket only | ✅ 不修 phase2_routes |
| 不修第 4 ticket | ✅ 未發現其他同 pattern file（grep `Depends(base.current_actor)` 全 codebase 確認 routes 內全是 production-time consistent，僅 test fixture 受 reload 影響） |
| 0 production code 改動 | ✅ 僅 2 test 檔 |
| 工作目錄 | ✅ `/Users/ncyu/Projects/TradeBot/srv` 主 repo（per ticket directive） |
| 不 commit | ✅ worktree pattern，return 主會話 |

---

## §7 主會話 follow-up

1. **Commit + push**：主會話統一 commit 兩 test 檔改動 + 本 PA report；建議 commit message:
   ```
   fix(test): resolve executor_shadow_toggle + strategist_promote 35 fail under sibling reload pollution

   Root cause family: same as W3 SINGLETON (test_api_contract importlib.reload(main_legacy)),
   different mechanism: FastAPI `Depends(base.current_actor)` freeze at route-build-time,
   reload rebinds main_legacy.current_actor to new fn obj but frozen Depends still points
   to old → dependency_overrides match fails → 401 instead of expected status.

   Fix: _make_app reloads executor_routes / strategist_promote_routes so router rebuilds
   with fresh Depends freeze. 0 production code change (Depends freeze is FastAPI design,
   not bug). Option A only (test fixture); Option B not applicable.
   ```
2. **Linux verify**：`ssh trade-core "cd ~/BybitOpenClaw/srv && pytest control_api_v1/tests/test_executor_shadow_toggle_api.py control_api_v1/tests/test_strategist_promote_api.py control_api_v1/tests/test_api_contract.py -q"` 期望 53 passed
3. **TODO update**：閉合本兩 ticket；剩餘 phase2_routes 3 fail 維持 P4 Mac-only 待新 ticket
4. **Memory log**：補一條 `feedback_fastapi_depends_reload_freeze.md` 記錄 FastAPI Depends freeze 與 importlib.reload 互動模式 — 未來新 test fixture 用 `_make_app` pattern 必須先 reload sub-module（避免下次再現）

---

## §8 結論

| 項 | 結論 |
|---|---|
| 17 fail (executor_shadow_toggle) | **17→0** ✅ |
| 18 fail (strategist_promote) | **18→0** ✅ |
| Same-session 3-file（含 polluter） | 35 fail → 0 fail ✅ |
| 完整 control_api_v1 baseline | 38 fail → 3 fail（剩 phase2_routes out-of-scope） ✅ |
| Production code 改動 | **0** |
| Test code 改動 | 2 file, +42 -4 |
| W1+W2+W3+SINGLETON regression | 116 passed ✅ |
| Commit 狀態 | worktree only，待主會話 commit + push |
| Out-of-scope 標記 | phase2_routes 3 fail（P4 Mac-only） |

PA+E1 DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--singleton_sibling_fix_executor_promote.md`
