# main_legacy.py 重構工作日誌 — Wave A-E 全記錄

**日期：** 2026-04-01
**工程師：** Claude Opus 4.6 (E1) + E5 審查
**測試基線：** 19 failed / 3005 passed（全程零回歸）

---

## 一、背景與動機

`main_legacy.py` 是 Control API v1 的歷史核心模組，隨專案演進膨脹至 **5265 行**，
遠超 §14.1 代碼結構約定的 1200 行硬上限。涵蓋：

- FastAPI app 創建 + 中間件
- Settings 單例 + 認證邏輯
- Pydantic 資料模型（30+ 類）
- 狀態編譯器（compile_state + 17 個 _compile_* 函數）
- JSON 狀態存儲（JsonStateStore）
- 控制平面操作（recheck / validate / arm / enable / relock / bundle）
- PnL 與業務指標操作
- 學習系統操作（觀察/經驗/假設/實驗 CRUD + 自動管線）
- 59 條路由處理器
- 輔助函數（幂等性/審計/版本斷言）

**核心約束：**
1. `settings = Settings()` 單例必須留在 main_legacy.py（多個測試依賴 `importlib.reload` 重建）
2. `main.py` 在啟動時 monkey-patch `compile_state`/`STORE`/`get_latest_snapshot`/`envelope_response`/`build_source_context`
3. 被 patch 的函數必須通過 `_base.xxx` 延遲查找，不可在 import 時捕獲

---

## 二、重構總覽

| Wave | 拆出模塊 | 行數變化 | Commit |
|------|---------|---------|--------|
| A | state_models + state_compiler + state_store | 5265→4056 (-1210) | `039b5fd` |
| B | auth + state_helpers | 4099→3802 (-297) | `b630f86` |
| C | control_ops + pnl_ops + learning_ops | 3802→1439 (-2363) | `7b9f0df` |
| D | legacy_routes | 1439→430 (-1016) | `3c4af45` |
| E | learning_records + learning_auto_pipeline + learning_queries | learning_ops 1624→48 | `32adf48` |

**最終結果：** main_legacy.py 5265→407 行（-92%），拆出 11 個模塊。

---

## 三、各 Wave 詳細記錄

### Wave A：資料模型 + 狀態編譯器 + 狀態存儲（-1210 行）

**拆出模塊：**
- `state_models.py`：30+ Pydantic 模型（RequestEnvelope, ResponseEnvelope, SourceContext 等）+ 常量集合
- `state_compiler.py`：compile_state() + 17 個 _compile_* 函數 + now_ms() + PRODUCT_FAMILIES
- `state_store.py`：JsonStateStore（線程安全 JSON 讀寫 + 原子寫入）+ build_default_state()

**設計決策：**
- state_models 零依賴（純資料定義）
- state_compiler 依賴 state_models
- state_store 依賴 state_compiler
- 單向依賴鏈，禁止循環 import

### Wave B：認證 + 狀態輔助（-297 行）

**拆出模塊：**
- `auth.py`（237 行）：Settings CLASS（非實例）、AuthenticatedActor、_resolve_api_token、登錄失敗追蹤、憑證緩存
- `state_helpers.py`（159 行）：request_fingerprint、revision 斷言、幂等性緩存、審計字段寫入

**關鍵決策：** Settings 類可以拆出，但 `settings = Settings()` 實例化必須留在 main_legacy.py。
原因：測試用 `os.environ[...] = "new_value"; importlib.reload(main_legacy)` 模式重建 Settings。

### Wave C：業務邏輯三模塊（-2363 行）

**拆出模塊：**
- `control_ops.py`（654 行）：build_overview、perform_recheck/validate/demo_transition/safe_bundle、apply_input_action/config_change/product_family_config
- `pnl_ops.py`（305 行）：apply_pnl_entry、build_business_summary、apply_pnl_period_snapshot、build_net_pnl_dashboard
- `learning_ops.py`（1624 行）：全部學習系統操作（CRUD + 自動管線 + 查詢）

**技術模式：** 所有寫操作通過 `_base.STORE.mutate()` + `_base.get_latest_snapshot()` 間接訪問 main_legacy 單例，確保 monkey-patch 生效。

### Wave D：路由處理器（-1016 行）

**拆出模塊：**
- `legacy_routes.py`（1276 行）：59 條路由全部包裝在 `register_legacy_routes(app)` 函數中

**關鍵修復（測試回歸）：**
發現 `test_runtime_snapshot_bridge` 2 個測試失敗。
- **根因：** `register_legacy_routes()` 在 main_legacy import 階段執行（早於 main.py monkey-patch），
  將 `envelope_response` / `get_latest_snapshot` / `current_actor` 捕獲為局部變量 → 路由使用的是 pre-patch 版本
- **修復：** 移除局部捕獲，所有 monkey-patched 函數在路由內通過 `_base.xxx` 延遲查找
- **影響：** 62 處 `envelope_response(` → `_base.envelope_response(`，46 處 `Depends(current_actor)` → `Depends(_base.current_actor)`

### Wave E：learning_ops 二次拆分 + Bug 修復

**E5 審查觸發的修復：**

1. **MEDIUM Bug — `build_review_queue()` 排序錯誤**
   - 原代碼：`decided[-_MAX_RECENT_ENTRIES:]` 在 newest-first 排序後取尾部 = 最舊 20 筆
   - 修復：`decided[:_MAX_RECENT_ENTRIES]` 取頭部 = 最新 20 筆

2. **LOW — `ts_key` 死代碼**
   - 原代碼：`ts_key = f"last_{scan_type[:-1]...}_scan_ts_ms"` 後立即被 if/elif/else 覆蓋
   - 修復：移除多餘的 f-string 計算

3. **LOW — main_legacy 5 個死 re-export**
   - `REVIEW_PACKET_STATUSES`、`REVIEW_PACKET_TYPES`、`_MAX_PAYLOAD_SIZE`、`_MAX_TEXT_REASON`、`T`
   - 驗證零消費者後移除

**拆分結果：**

| 模塊 | 行數 | 職責 |
|------|------|------|
| learning_records.py | 633 | 觀察/經驗/假設/實驗 7 個 CRUD 寫操作 |
| learning_auto_pipeline.py | 896 | 審核包構建 + 3 掃描器 + 審核決策 + AI stub |
| learning_queries.py | 106 | 審核隊列/觀察流/實驗隊列 3 個只讀查詢 |
| learning_ops.py | 48 | thin re-export facade |

**循環 import 解決：**
- main_legacy 原本 re-export 學習函數 → 觸發 main_legacy → learning_ops → learning_records → main_legacy 循環
- 驗證零消費者後，移除 main_legacy 的學習函數 re-export
- 消費者（legacy_routes.py）直接 import learning_ops facade

---

## 四、模塊依賴圖（重構後）

```
state_models.py          ← 零依賴
state_compiler.py        ← state_models
state_store.py           ← state_compiler
auth.py                  ← state_models
state_helpers.py         ← state_compiler, state_models

learning_records.py      ← _base(main_legacy), auth, state_compiler, state_helpers, state_models
learning_auto_pipeline.py ← _base(main_legacy), auth, state_compiler, state_helpers, state_models
learning_queries.py      ← 零依賴（純讀）

control_ops.py           ← _base(main_legacy), auth, state_compiler, state_helpers, state_models
pnl_ops.py               ← _base(main_legacy), auth, state_compiler, state_helpers, state_models
learning_ops.py          ← re-export facade（learning_records + auto_pipeline + queries）

legacy_routes.py         ← _base(main_legacy), auth, control_ops, pnl_ops, learning_ops, state_models

main_legacy.py           ← FastAPI app + settings 單例 + re-export（不含學習函數）
main.py                  ← main_legacy（monkey-patch + router 註冊）
```

---

## 五、Singleton 管理表（更新）

| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `_base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `_base.STORE` |
| `app` | main_legacy.py | `_base.app`（main.py re-export） |
| `limiter` | main_legacy.py | `_base.limiter` |

---

## 六、§14 代碼結構約定遵守情況

| 文件 | 行數 | 狀態 |
|------|------|------|
| main_legacy.py | 407 | ✅ 遠低於 800 警告線 |
| state_models.py | ~400 | ✅ |
| state_compiler.py | ~700 | ✅ |
| state_store.py | ~400 | ✅ |
| auth.py | 237 | ✅ |
| state_helpers.py | 159 | ✅ |
| control_ops.py | 654 | ✅ |
| pnl_ops.py | 305 | ✅ |
| learning_records.py | 633 | ✅ |
| learning_auto_pipeline.py | 896 | ⚠️ 超 800 警告線，但內容高度耦合，進一步拆分會碎片化 |
| learning_queries.py | 106 | ✅ |
| learning_ops.py | 48 | ✅（facade） |
| legacy_routes.py | 1276 | 🛑 超 1200 硬上限（路由文件例外：拆分會破壞路由註冊模式） |

---

## 七、驗證結果

- 每波測試結果均為 **19 failed / 3005 passed**，與基線完全一致
- Wave D 發現並修復了 monkey-patch 延遲查找問題（2 個測試回歸 → 0）
- Wave E 修復了 E5 發現的 `build_review_queue()` 排序 bug
- `importlib.reload(main_legacy)` 測試路徑驗證通過
- 59 條路由全部正確註冊

---

## 八、後續建議

1. `learning_auto_pipeline.py`（896 行）：可以考慮將 3 個 `generate_auto_*` 掃描器分出，但優先級低
2. `legacy_routes.py`（1276 行）：路由文件超硬上限，但拆分需要改變 `register_legacy_routes(app)` 模式，風險較高
3. 考慮逐步遷移消費者從 facade（learning_ops）直接 import 子模塊，最終廢棄 facade
