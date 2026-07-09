# G-01 修復報告：AI 每日硬上限 $15.0 → $2.0

**日期**：2026-03-31
**執行人**：E1（Backend Developer）
**任務編號**：G-01（Sprint 0 BLOCKER）

---

## 修改文件清單

### 1. `app/layer2_types.py`（行 57-60）
- **原值**：`DEFAULT_DAILY_HARD_CAP_USD = 15.0`
- **新值**：`DEFAULT_DAILY_HARD_CAP_USD = 2.0`
- **額外**：在常量定義旁新增中英雙語注釋說明來源（DOC-08 §4 + 根原則 5）

### 2. `app/layer2_cost_tracker.py`（MODULE_NOTE，行 11 + 行 21）
- **不在原規格中，但發現後一併修正**（保持注釋與代碼一致性）
- 行 11：`$15/天` → `$2/天，DOC-08 §4`
- 行 21：`$15/day, absolute` → `$2/day, absolute, per DOC-08 §4`

### 3. `app/static/tab-ai.html`（4 處，含 1 處額外發現）
| 行號 | 位置 | 舊值 | 新值 |
|------|------|------|------|
| 335 | `saveAIConfig()` fallback | `|| 15` | `|| 2` |
| 359 | budget display fallback（**額外發現**） | `|| 15` | `|| 2` |
| 426 | config summary 日硬上限顯示 | `|| 15` | `|| 2` |
| 441 | input field 預填 | `|| 15` | `|| 2` |

**未修改**（非 AI 預算）：
- 行 430：`cfg.max_iterations || 15`（最大迭代次數預設值，保持不動）
- 行 445：`cfg.max_iterations || 15`（同上，保持不動）

### 4. `tests/test_layer2.py`（行 201）
- **原斷言**：`assert d["daily_hard_cap_usd"] == 15.0`
- **新斷言**：`assert d["daily_hard_cap_usd"] == 2.0`

---

## 額外發現

1. **`layer2_cost_tracker.py` MODULE_NOTE**：中英兩處 `$15/day` 硬編碼在原規格中未列出，但屬於同一問題的注釋層面，已一併修正。

2. **`tab-ai.html` 第 359 行**：budget display fallback `|| 15` 原規格未列入，屬於 AI 預算顯示相關，已一併修正。

3. **測試脆弱性觀察**：`test_layer2.py` 第 201 行直接硬寫 `15.0` 而非引用 `DEFAULT_DAILY_HARD_CAP_USD` 常量，導致常量變更時測試可能不同步。建議未來改為 `assert d["daily_hard_cap_usd"] == DEFAULT_DAILY_HARD_CAP_USD`。

---

## 測試結果

```
tests/test_layer2.py: 79 passed, 0 failed (9.65s)
```

所有 79 個 layer2 測試通過，無迴歸。

---

## 合規確認

- 違反：DOC-08 §4（AI 每日預算 $2.00），DOC-08 §12 安全不變量
- 根原則 5（生存 > 利潤）：$15 上限是規定值的 7.5 倍，存在 AI 成本失控風險
- 修復後：代碼實際行為與設計文件一致
