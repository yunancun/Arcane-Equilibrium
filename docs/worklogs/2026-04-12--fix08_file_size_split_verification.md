# FIX-08 文件大小拆分：完成報告 + 完整性驗證
# FIX-08 File Size Split: Completion Report + Integrity Verification
**日期 / Date**: 2026-04-12
**觸發 / Trigger**: §九 硬上限 1200 行 + 全程序鏈審計 P2 項

---

## 概要 / Summary

12+ 個超限文件拆分為合規大小，分 3 批次執行。拆分後全量測試通過（Python 2852 + Rust engine 965 + Rust core 366 = **4183 tests, 0 fail**）。額外發現並修復 1 個 pre-existing bug（index.html 缺 common.js 引用）。

---

## Batch 1: Rust 文件拆分

| 原始文件 | 行數變化 | 拆出文件 |
|----------|---------|---------|
| `risk_config.rs` | 超限→合規 | `risk_config_defaults.rs` |
| `event_consumer/mod.rs` | 超限→合規 | `event_consumer/handlers.rs` |
| `applier.rs` | 超限→合規 | 已拆分 |

## Batch 2: Python 文件拆分

| 原始文件 | 行數變化 | 拆出文件 | 行數 |
|----------|---------|---------|------|
| `backtest_engine.py` | 1352→1142 | `backtest_types.py` | 239 |
| `signal_generator.py` | 1452→1174 | `signal_engine.py` | 315 |
| `governance_routes.py` | 1914→1172 | `governance_extended_routes.py` | 585 |
|  |  | `governance_promotion_routes.py` | 240 |
| `governance_hub.py` | 1812→1052 | `governance_hub_cascades.py` | 811 |
| `live_session_routes.py` | 1253→1115 | `live_session_governance.py` | 178 |

### Python 拆分技術要點 / Technical Details

- **Re-export 後向兼容**：所有原始文件保留 `from .new_module import X  # noqa: F401` 確保外部 import 路徑不變
- **Side-effect 路由註冊**：`governance_routes.py` 通過 `from . import governance_extended_routes as _ext_routes` 觸發 FastAPI 路由裝飾器註冊
- **Mock 可修補性**：`governance_extended_routes.py` 使用模組級委託（`from . import governance_routes as _gov`）而非直接 import，確保 `unittest.mock.patch` 在測試中生效
- **Mixin 繼承**：`GovernanceHub` 改為繼承 `GovernanceHubStatusCascadeMixin`；`GovernanceMode`/`GovernanceStatus` 移入 cascades 模組避免循環 import

## Batch 3: JS + HTML + Doc 拆分

| 原始文件 | 行數變化 | 拆出文件 | 行數 |
|----------|---------|---------|------|
| `app.js` | 2627→699 | `app-gui.js` | 641 |
|  |  | `app-actions.js` | 264 |
|  |  | `app-learning.js` | 396 |
|  |  | `app-review.js` | 421 |
|  |  | `app-paper.js` | 256 |
| `tab-governance.html` | 2047→477 | `governance-tab.js` | 1579 |
| `tab-risk.html` | 1390→510 | `risk-tab.js` | 889 |
| `CLAUDE_CHANGELOG.md` | 2147→909 | `archive/2026-04-12--changelog_archive_pre_0408.md` | 1247 |

### JS 拆分技術要點

- `index.html` 按依賴順序載入 6 個 `<script>` 標籤（app.js → app-gui.js → ... → app-paper.js）
- `tab-governance.html` / `tab-risk.html` inline `<script>` 提取為外部 `.js` 文件
- 所有拆分檔案的全域函式引用通過 `<script>` 載入順序保證可用性

---

## 完整性驗證 / Integrity Verification

### Python Import 鏈檢查（18 項全 PASS）

| 檢查項 | 結果 |
|--------|------|
| backtest_engine.py re-exports (6 symbols) | ✅ |
| signal_generator.py re-exports (2 symbols) | ✅ |
| governance_routes.py re-exports (15 symbols) | ✅ |
| governance_hub.py re-exports (3 symbols) | ✅ |
| Side-effect route registration (2 imports) | ✅ |
| Mock patchability — module-level delegation | ✅ |
| No circular imports (hub↔cascades, live↔gov) | ✅ |
| `__init__.py` 無需更新 | ✅ |
| 外部代碼無直接 import 新模組 | ✅ |

### JS/HTML 引用檢查（7 項 + 1 修復）

| 檢查項 | 結果 |
|--------|------|
| index.html script 順序正確 | ✅ |
| 跨文件函式引用（app.js 31 全域函式） | ✅ |
| Split 文件間無循環依賴 | ✅ |
| tab-governance.html 無殘留 inline script | ✅ |
| tab-risk.html 無殘留 inline script | ✅ |
| StaticFiles mount 可服務新文件 | ✅ |
| **index.html 缺 common.js** | ⚠️ 修復 |

### 發現並修復：Pre-existing Bug

**問題**：`index.html` 未載入 `common.js`，但 `app.js` 及拆分文件共 35 處調用 `ocEsc()`（定義於 common.js）。此 bug 在拆分前即存在（原始 monolithic app.js 同樣有此問題），但拆分審查過程中發現。

**修復**：在 `index.html` 的 `app.js` 之前添加 `<script src="/static/common.js"></script>`。

---

## 測試基線 / Test Baseline

```
Python:       2852 passed, 5 skipped, 0 failed
Rust engine:   965 passed, 0 failed
Rust core:     366 passed, 0 failed
Total:        4183 passed, 0 failed
```

---

## 文件清單 / File Inventory

**新增 14 個文件**：
- `program_code/local_model_tools/backtest_types.py` (239)
- `program_code/local_model_tools/signal_engine.py` (315)
- `program_code/.../app/governance_extended_routes.py` (585)
- `program_code/.../app/governance_promotion_routes.py` (240)
- `program_code/.../app/governance_hub_cascades.py` (811)
- `program_code/.../app/live_session_governance.py` (178)
- `program_code/.../app/static/app-gui.js` (641)
- `program_code/.../app/static/app-actions.js` (264)
- `program_code/.../app/static/app-learning.js` (396)
- `program_code/.../app/static/app-review.js` (421)
- `program_code/.../app/static/app-paper.js` (256)
- `program_code/.../app/static/governance-tab.js` (1579)
- `program_code/.../app/static/risk-tab.js` (889)
- `docs/archive/2026-04-12--changelog_archive_pre_0408.md` (1247)

**修改 9 個原始文件**（全部 ≤1200 行）：
- `backtest_engine.py` (1142), `signal_generator.py` (1174)
- `governance_routes.py` (1172), `governance_hub.py` (1052), `live_session_routes.py` (1115)
- `app.js` (699), `tab-governance.html` (477), `tab-risk.html` (510)
- `CLAUDE_CHANGELOG.md` (909)

**修改 1 個 HTML 文件**（bug fix）：
- `index.html` (+1 行 common.js script tag)
