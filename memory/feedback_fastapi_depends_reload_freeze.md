---
name: FastAPI Depends 與 importlib.reload 互動規則
description: 當測試 fixture 需 `importlib.reload(main_legacy)` 重建 STORE/app singleton，必須同步 reload 所有相關 router module，否則 router 內 `Depends(base.current_actor)` 等 frozen callable 仍指向舊 fn obj，dependency_overrides 對不上 → 401
type: feedback
---

# FastAPI Depends + importlib.reload 互動規則

**Rule**：測試 fixture 內 `importlib.reload(main_legacy)` 後，必須立即 `importlib.reload(<route_module>)` 同步重建 router，否則 `Depends(base.current_actor)` 等 frozen callable 永久指向舊 fn obj。

**Why（2026-04-28 SINGLETON-POLLUTION-EXECUTOR-SHADOW-TOGGLE-API + STRATEGIST-PROMOTE-API 揭，commit `cff6959`）**：
- Polluter `test_api_contract.py::build_client::importlib.reload(main_legacy)` 觸發 `base.current_actor` 變新 fn obj
- 但既有 router (e.g. `executor_routes.router`) 內 `Depends(base.current_actor)` 是 **route-build-time frozen callable** — FastAPI 設計語意，不隨 module reload 跟進
- 測試後續 `app.dependency_overrides[base.current_actor=新 fn]` 對不上 frozen 舊 fn obj → 認證 fail → 401 unauthorized → 35 fail (17 executor + 18 promote)

**How to apply（test fixture pattern）**：
```python
def _make_app():
    import importlib
    from app import main_legacy, executor_routes, strategist_promote_routes
    importlib.reload(main_legacy)
    importlib.reload(executor_routes)         # ← 必加
    importlib.reload(strategist_promote_routes)  # ← 必加
    app = main_legacy.app  # 現在 router 內 Depends 已 freeze 到新 fn obj
    app.dependency_overrides[main_legacy.current_actor] = lambda: ...
    return app
```

**對 vs Wave E SINGLETON h_state fix（commit `b579dae`）區別**：
- W3 + h_state SINGLETON 用 **Option B (production sys.modules.get)** 解 CPython `from PKG import SUB` attribute precedence — 是 import indirection 問題
- 本規則解 FastAPI Depends route-build-time freeze — 是 framework 設計語意問題
- **不可混用**：Option B 不適用 Depends freeze（沒有 sys.modules.get 等價解）；Option A reload 也不適用 attribute precedence（reload 本身觸發 polluter）

**Scope（適用範圍）**：所有用 `_make_app() + dependency_overrides[current_actor]` 模式的測試。Grep 揭至少 7 route file 含 `Depends(base.current_actor)`（scout / shadow_fills / live_session_account / risk / strategy_write / attribution / live_trust），目前對應 test file co-resident 89/89 PASS（無 latent Heisenbug），但**未來新測 file 用同 pattern 必先 reload route module**。
