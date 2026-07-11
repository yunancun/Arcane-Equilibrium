---
name: fastapi-depends-importlib-reload
description: "測試 fixture reload/purge main_legacy 重建 STORE/app singleton 的兩個陷阱——(1) reload 後須同步 reload router module 否則 Depends(current_actor) frozen callable 指舊 fn→401；(2) `del sys.modules['app.X']` 會被 CPython 父包屬性捷徑架空、清理形同虛設，正解是就地刷新 env 派生態"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 41e83cea-19c7-4408-a9e4-7af48856c20b
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

---

**深化：`del sys.modules` 被父包屬性捷徑架空（2026-07-10，SNAPSHOT-STABLE-ENTRYPOINT-TEST-ISOLATION，commit `dbc6a936c`）**

上方 Option B 提到的 CPython `from PKG import SUB` attribute precedence 不只影響 production import indirection，**也讓測試 fixture 的 `del sys.modules['app.X']` 清理形同虛設**——這是一個會潛伏很久的 test-isolation 反模式。

- **機制**：`test_snapshot_stable_entrypoint.py::build_client` 刪 4 個 sys.modules 條目後 re-import，但 fresh `main.py` 的 `from . import main_legacy` 命中父包屬性捷徑——只要 `app` 包物件上殘留舊 `main_legacy` 屬性就直接返回舊模組，**連 sys.modules 都不回填**，del 等於沒做。`del sys.modules` 不保證重生子模組。
- **後果**：先行 app-touching 測試檔在 collection 期（`OPENCLAW_API_TOKEN`/`OPENCLAW_STATE_FILE` 未設）凍結的隨機 token / 預設 state 檔的 `settings`/`STORE` singleton 洩漏進來 → 401 或 snapshot 身份 order-dependent 漂移（solo 恆過、與任一先行者同跑恆敗）。
- **正解 = 就地刷新 env 派生態**：`base.settings = base.Settings()` / `base.STORE = base.JsonStateStore(state_file_path)` / `mark_compile_dirty()`，而非依賴 del/reload。settings singleton 本就設計住 main_legacy（reload-safe 契約，見 `auth.py` MODULE_NOTE），定向 rebind 比 reload 更省——避開 reload 再生 FastAPI app 的副作用。
- **不要盲目擴大 sys.modules 刪除**：~40 個 route/ops 模組在模組層 `from . import main_legacy as base` 凍結指向單一實例。擴大刪除輕則 inert、重則把該實例劈成新舊兩半（讀路徑 401 / 讀寫分家 409），還會波及主圖外被別的測試 collection 期綁定的模組（strategist_agent 字串 patch 落到重生模組而舊 class 仍呼舊函數；conftest 對 db_pool 的進程級 prod-DB 封鎖被拆）。
- **教訓**：斷言 test isolation 有效前，先 probe `id(module)` 或 fresh env 派生值，別假設 `del sys.modules` / `importlib.reload` 一定重生了你以為的東西。與本檔上半（Depends freeze）是同一 reload/freeze 家族的兩個不同機制面，[[feedback_evidence_discipline_under_degraded_tools]] 的「build-SHA≠git-commit / 讀 source 全文再下判斷」同源。
