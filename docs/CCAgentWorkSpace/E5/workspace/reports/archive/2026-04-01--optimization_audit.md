# E5 審計報告：全程序優化評估（精簡·性能·可讀性）
# E5 Audit: Full-Program Optimization Assessment
# 日期：2026-04-01
# 對比基準：2026-03-31 E5 優化報告（49 項）
# 評估文件總計：62 個 Python app 文件 + 25 個 local_model_tools 文件 + 20 個前端文件 = 107 個文件

---

## 執行摘要 / Executive Summary

| 類別 | March 31 | April 1 | 變化 |
|------|----------|---------|------|
| 已修復 March 31 問題 | — | 14/49 修復 | +14 |
| 未修復 March 31 問題 | 49 | 35 殘留 | -14 |
| 新發現問題 | — | 19 項 | +19 |
| **當前問題總計** | **49** | **54** | **+5** |

| 優先級 | 數量 |
|--------|------|
| Critical | 1 |
| High | 12 |
| Medium | 26 |
| Low | 15 |

**代碼規模變化：** March 31 ~50,912 行 → April 1 ~67,544 行（+16,632 行，+32.7%）
主要新增：h0_gate.py(832) + truth_source_registry.py(821) + experiment_ledger.py(617) + backtest_engine.py(1209) + evolution_engine.py(539) + 新路由文件 + tab-governance 擴大

---

## 一、March 31 問題修復進度核實（逐項對照）

### 1.1 已修復（14 項）

| # | 原問題 | 原優先級 | 修復確認 |
|---|--------|----------|---------|
| 1 | `pipeline_bridge.py` `set_analyst_agent` 方法重複定義 | Critical | **已修復** — 僅剩 1 個定義（line 226），Batch 9/10 合併完成 |
| 2 | `main_legacy.py` `_compile_for_response` 每次調用 `inspect.signature` | Critical | **已修復** — `_COMPILE_STATE_SIG_CACHE` (WeakKeyDictionary) 已實現（line 668），一次緩存 |
| 3 | `main.py` `openclaw_proxy` 在 async 函數中同步阻塞 `urlopen` | Critical | **已修復** — 已包裝為 `await _asyncio.to_thread(_do_request)`（line 344） |
| 4 | `pipeline_bridge.py:104` `_analyst_agent = None` 雙重初始化 | High | **已修復** — 僅剩 1 個初始化（line 104，統一注釋） |
| 5 | `layer2_engine.py` "not worth" 否定檢測使用字符串 `in` | High | **已修復** — 改為 `_NEGATION_RE.search()` 正則詞邊界匹配（line 307） |
| 6 | `main_legacy.py` `auth_login` 每請求讀 `.env` 文件 | Medium | **已修復** — `_AUTH_CREDENTIALS` 啟動緩存（line 63-83），`settings.api_token` 統一使用（line 4264） |
| 7 | `tab-settings.html` setInterval 倒計時未清理 | Medium | **已修復** — `clearInterval(iv)` 已加入（line 387） |
| 8 | `pipeline_bridge.py` `_json_mod` 別名與函數內 `import json as _json` 重複 | Low | **部分修復** — 頂部 `_json_mod` 保留，函數內仍有 3 處 `import json as _json`（lines 1264, 1796, 1857），不一致仍存在 |
| 9 | `main_legacy.py:4033` `SlowAPIMiddleware` import 遠離頂部 | Medium | **可接受** — 雖未移動，但已加註釋說明位置原因 |
| 10 | `pipeline_bridge.py` `intent.reason` AttributeError 風險 | High | **已修復** — 熱路徑中所有 `.reason` 訪問現在來自有 `reason` 屬性的 verdict 或 H0 result 對象，不再直接訪問 intent.reason |
| 11 | 登入端點速率限制 | P1 security | **已修復** — 5次/分 + IP 鎖定 + asyncio.Lock + 2000 IP 容量上限 |
| 12 | `governance_hub` env var 可禁用治理 | P1 security | **已修復** — OPENCLAW_GOVERNANCE_ENABLED 環境變量已移除 |
| 13 | `_compile_for_response` 函數內 `import inspect` | Low | **已修復** — 隨 `_COMPILE_STATE_SIG_CACHE` 一併修復，inspect 移至模組級 |
| 14 | `main_snapshot_stable.py` 缺少文檔 | Low | **可接受** — 文件頭部 docstring 已清楚標註向後兼容用途 |

### 1.2 未修復（35 項）

| # | 原問題 | 原優先級 | 當前狀態 |
|---|--------|----------|---------|
| 15 | `main_legacy.py` 5,113 行單文件（原 4,973 → 增至 5,113） | High | **未修復，持續惡化**（+140 行） |
| 16 | `compile_state` / `stable_compile_state` 邏輯重複 ~170 行 | High | **未修復** |
| 17 | `now_ms()` 兩文件重複定義 + 156 處 `int(time.time()*1000)` 內聯 | High | **惡化**（128→156 處，新文件 +28） |
| 18 | 寫操作 4 行 boilerplate 重複 20+ 次 | High | **未修復**（20 處 `verify_operator_identity` 調用） |
| 19 | `_write_audit_fields` + `_bump_revision` + compile + store 四步序列重複 | Medium | **未修復**（57 處相關調用） |
| 20 | logger f-string 調用 192→182 處 | High | **微改善**（-10），大量殘留（governance_hub 67 處居首） |
| 21 | `on_tick` 方法超長（原 110→132 行） | High | **惡化**（+22 行） |
| 22 | `_process_pending_intents` 方法（原 ~300→462 行） | High | **顯著惡化**（+162 行） |
| 23 | `_check_edge_filter` ~115 行 | Medium | **未修復** |
| 24 | `pipeline_bridge.py` 9 個 setter 重複模式 | Medium | **未修復** |
| 25 | `pipeline_bridge.py:93-112` 外部依賴未文檔化 | High | **未修復** |
| 26 | `main.py:144-153` Monkey patching 無文檔 | Medium | **部分改善** — main_legacy 有 "monkey-patched" 注釋（line 664），但 main.py 無顯式警告 |
| 27 | `_process_pending_intents` 名稱與職責不符 | Medium | **未修復** |
| 28 | `compile_state` 每次 read 做 3 次 O(n) 列表掃描 | High | **未修復** |
| 29 | `_compile_effective_action_permissions` O(n^2) 遍歷 | Medium | **未修復** |
| 30 | `phase2_strategy_routes.py` 模組級初始化 ~140 行 | Medium | **未修復** |
| 31 | `_cleanup_idempotency_cache` O(n log n) 排序 | Medium | **改善** — 加了 fast path（size <= max/2 跳過），但核心 O(n log n) 仍在 |
| 32 | 前端 `api()`/`apiGet()` 三處獨立實現 | High | **未修復** |
| 33 | `TOKEN_KEY` 在 4 處硬編碼 | Medium | **未修復**（console.html:201, login.html:50, trading.html:244, common.js:7） |
| 34 | `baseEnvelope` 硬編碼 `"demo-operator"` | Medium | **未修復**（20 處 `baseEnvelope()` 調用） |
| 35 | `:root` CSS 變量 4 處重複定義 | High | **未修復**（console.html, login.html, trading.html, styles.css） |
| 36 | `console.html` 與 `common.js` 重複的 `getToken()`/`logout()` | High | **未修復**（console.html:201/216 仍保留獨立實現） |
| 37 | `trading.html` 完全獨立認證/API 實現 | High | **未修復** |
| 38 | `app.js` `baseEnvelope` vs `ocEnvelope` | Medium | **未修復** |
| 39 | 時鐘 `setInterval` 重複 | Medium | **未修復** |
| 40 | `trading.html` LightweightCharts 顏色硬編碼 | Low | **未修復** |
| 41 | `tab-governance.html` 大量內聯樣式 | Low | **惡化**（2,129 行，200 處 inline style） |
| 42 | `governance_routes.py` 每請求惰性導入 GOV_HUB | Medium | **未修復** |
| 43 | `governance_routes.py` 三個 `_get_xxx()` 無統一抽象 | Low | **未修復** |
| 44 | `phase2_strategy_routes.py` sys.path 計算不夠穩健 | Low | **惡化**（3 個新文件複製相同模式） |
| 45 | `phase2_strategy_routes.py` 魔法數字 | Low | **部分改善** — 部分常數已有注釋說明 |
| 46 | `PaperStateStore`/`JsonStateStore` 重複模式 | Low | **未修復** |
| 47 | `main_legacy.py:630-667` CONFIG_CHANGE_WHITELIST 冗長 | Low | **未修復** |
| 48 | `main_legacy.py:689-700` `build_snapshot_id` 每次 JSON + SHA256 | Low | **未修復** |
| 49 | `main_legacy.py:4338-4360` `_schedule_restart` bash 字符串拼接 | Low | **未修復** |

---

## 二、精簡性評估（Dead Code / 冗餘邏輯）

### [Medium] NEW-S1: `backtest_engine.py` 重複 `_compute_sma`/`_compute_ema`/`_compute_rsi` 純函數

**位置：** `backtest_engine.py:370-404`
**問題：** `_compute_sma`, `_compute_ema`, `_compute_rsi` 三個純函數與 `indicators/moving_averages.py` 中的 `compute_sma`/`compute_ema` 以及 `indicators/rsi.py` 中的 `compute_rsi` 功能完全相同，構成代碼重複。

**理由：** backtest_engine 聲明遵循原則 7 隔離，不引入 live 模組依賴。但這些指標函數本身是純函數（無副作用），隔離的是引擎框架（IndicatorEngine），而非純計算函數。

**建議：** 在 `indicators/` 包中提供一個 `indicators.pure` 子模組（純函數，零副作用，零狀態），backtest_engine 從此導入。這樣既保留原則 7 隔離又消除重複。

---

### [Medium] NEW-S2: 三個新路由文件重複 sys.path 5 層 dirname 模式

**位置：** `backtest_routes.py:52-61`, `evolution_routes.py:56-68`, `experiment_routes.py:58-70`
**問題：** 每個文件各自計算 5 層 `os.path.dirname` 並修改 `sys.path`，邏輯完全相同。加上原有的 `phase2_strategy_routes.py`，共 4 處重複。

**建議：** 提取為公共函數 `_ensure_program_code_on_path()` 放在 `__init__.py` 或一個專門的 `_path_setup.py` 中，所有路由文件調用一次即可。

---

### [Low] NEW-S3: `audit_persistence.py` 8 處 `except Exception:` 無日誌

**位置：** `audit_persistence.py:174, 197, 212, 241, 262, 269, 280, 522`
**問題：** 8 處 `except Exception:` 捕獲後靜默忽略（pass 或 return None），無日誌記錄。雖然持久層 fail-open 是合理的設計選擇（不阻塞交易），但完全靜默使調試困難。

**建議：** 至少添加 `logger.debug` 級別的異常記錄。

---

### [Low] NEW-S4: `pipeline_bridge.py` 函數內 `import json as _json` 3 處殘留

**位置：** `pipeline_bridge.py:1264, 1796, 1857`
**問題：** 頂部已有 `import json as _json_mod`，函數內仍有 3 處局部 `import json as _json`。兩個別名不一致。

**建議：** 統一使用 `_json_mod`，刪除函數內局部導入。

---

## 三、性能評估（I/O / 並發 / 記憶體）

### [Critical] NEW-P1: `backtest_engine.py:787-792` — 每 bar 複製整個 OHLCV 數據（O(n^2) 總複雜度）

**位置：** `backtest_engine.py:787-792`
**問題：** 在 `_simulate` 主循環中，每個 bar 都執行：
```python
ohlcv_slice = {
    key: arr[: bar_idx + 1]
    for key, arr in ohlcv_data.items()
    if isinstance(arr, list)
}
indicators = _compute_indicators_pure(ohlcv_slice)
```
這為 OHLCV 的每個鍵（通常 5-6 個：open/high/low/close/volume/timestamp）創建一個新列表切片。對於 N 根 bar 的回測，總記憶體分配為 O(N^2)，每次切片操作是 O(bar_idx)。

在 EvolutionEngine 的 50 組合 grid search 中，此問題被放大 50 倍。

**影響：** 對 1000 根 bar 的回測，約分配 ~3M 個列表元素（5 keys * 500K slices）。在 4h 時間框架 1 年回測（2190 bars）中更為嚴重。

**建議：** 使用 `_BacktestKlineAdapter` 模式（文件中已定義但未在 `_simulate` 中使用）：維持索引而非切片，讓 `_compute_indicators_pure` 接收完整數據 + 截止索引。或者直接傳入完整數組並讓指標函數接受 `end_idx` 參數。

---

### [High] NEW-P2: `truth_source_registry.py` — 無 claim 上限，`_claims` dict 可無限增長

**位置：** `truth_source_registry.py:332`
**問題：** `self._claims: Dict[str, PatternClaim] = {}` 無大小限制。雖然有 TTL 過期機制（`is_expired()`），但過期 claim 僅在查詢時被跳過，從未實際從 dict 中移除。長期運行（數月）後可累積數萬已過期但未清理的 claim 對象。

**影響：** 記憶體緩慢洩漏 + `get_active_claims()` 遍歷時線性掃描已過期條目。

**建議：** 添加定期清理：在 `register_claim()` 或定時器中清理 `is_expired()` 為 True 的條目。設置上限（如 MAX_CLAIMS = 5000），超限時清理最舊/已過期條目。

---

### [High] NEW-P3: `experiment_ledger.py` — 無 hypothesis 上限，`_hypotheses` dict 可無限增長

**位置：** `experiment_ledger.py:239`
**問題：** 與 truth_source_registry 相同：`self._hypotheses: Dict[str, Hypothesis] = {}` 無大小限制。已結案（CONFIRMED/REFUTED/EXPIRED）的假設從未清理。

**建議：** 添加 MAX_HYPOTHESES 上限（如 2000）+ 定期清理已結案且超過 TTL 的條目。

---

### [High] NEW-P4: `_compute_indicators_pure` 每次調用從頭計算 EMA — O(n) 且無緩存

**位置：** `backtest_engine.py:407-480`
**問題：** `_compute_indicators_pure` 每次調用都從 `close` 陣列的第一個元素開始計算 SMA/EMA/RSI。在 `_simulate` 中每 bar 調用一次，且每次傳入 `close[:bar_idx+1]`，導致 EMA 的指數加權平均從頭重算。

**影響：** 單獨看每次調用是 O(n)，但疊加切片複製（NEW-P1），總複雜度為 O(n^2)。

**建議：** 使用增量計算模式：保存前一個 bar 的 EMA 值，每個新 bar 只需 O(1) 更新。

---

### [Medium] NEW-P5: `_process_pending_intents` 方法 462 行，持有鎖的範圍過大

**位置：** `pipeline_bridge.py:466-928`
**問題：** 這個方法的大部分邏輯在 `with self._lock:` 內部執行（包括 Guardian 調用、Ollama edge filter 等潛在的 I/O 操作）。鎖持有時間過長可能影響 `on_tick` 的響應。

**建議：** 收窄鎖範圍：在鎖內只收集 intents 和讀取共享狀態，解鎖後執行 Guardian/edge filter/執行等 I/O 密集操作。

---

### [Medium] NEW-P6: `governance_hub.py` 67 處 f-string logger 調用

**位置：** `governance_hub.py` 全文
**問題：** 單個文件有 67 處 `logger.xxx(f"...")` 調用，在治理檢查的熱路徑上（每筆交易都經過）構成不必要的字符串格式化開銷。

**建議：** 至少將 `logger.debug(f"...")` 改為 `logger.debug("%s ...", ...)` 格式。`logger.info/warning` 在熱路徑上也建議改用 % 格式。

---

## 四、可讀性評估（複雜度 / 命名 / 一致性）

### [High] NEW-R1: `_process_pending_intents` 462 行 — 項目中最大的單方法

**位置：** `pipeline_bridge.py:466-928`
**問題：** 從 March 31 的 ~300 行增長到 462 行。此方法同時處理：intent 收集、H0 Gate 檢查、Guardian 評審、L1 edge filter、Demo 同步、qty 圓整、OMS 提交、止損注冊、ExecutorAgent 路由、round-trip 記錄等 10+ 個職責。最深嵌套超過 7 層。

**建議：** 拆分為子方法：
- `_collect_intents()` — 從 StrategistAgent + 訂閱消息收集
- `_gate_intent(intent)` — H0 + Guardian + edge filter
- `_submit_approved_intent(intent, verdict)` — OMS + Demo + 止損
- `_post_execution_hooks(intent, result)` — round-trip + 學習

---

### [High] NEW-R2: `submit_order` 內部 `mutator` 函數 341 行

**位置：** `paper_trading_engine.py:1291-1632`
**問題：** `submit_order` 方法的內嵌 `mutator` 函數達 341 行，處理訂單匹配、持倉更新、PnL 計算、Demo 同步、學習觸發等多重職責。

**建議：** 提取為獨立的 `_match_and_fill()`、`_update_position()`、`_sync_demo_on_fill()` 子方法。

---

### [High] NEW-R3: `tick` 方法 278 行 + 內嵌 `mutator` 262 行

**位置：** `paper_trading_engine.py:1690-1968`
**問題：** `tick` 方法的 `mutator` 函數處理價格更新、PnL 計算、止損/止盈、trailing stop、Demo 平倉同步等。單一嵌套函數超過 260 行。

**建議：** 與 NEW-R2 相同，拆分為子步驟。

---

### [Medium] NEW-R4: `_handle_intel` 246 行

**位置：** `strategist_agent.py:416-662`
**問題：** 策略師的核心消息處理方法達 246 行，包含：intel 解析、regime 檢查、策略匹配、AI 諮詢、intent 生成、weight 調整等。

**建議：** 拆分為 `_parse_intel()`、`_evaluate_strategies()`、`_generate_intents()` 子方法。

---

### [Medium] NEW-R5: `governance_hub.py` `_on_risk_escalation` 168 行 + `_on_reconciliation_mismatch` 183 行

**位置：** `governance_hub.py:1264-1432, 1434-1617`
**問題：** 兩個事件處理方法各超過 160 行，處理多種升級/對帳情境。

**建議：** 按事件類型拆分為子方法。

---

### [Medium] NEW-R6: `h0_gate.py:check()` 方法 95 行 — 可接受但可改善

**位置：** `h0_gate.py:305-400`
**問題：** check() 方法 95 行，但結構清晰（5 個子檢查依序調用），每個子檢查本身只有 10-15 行。嵌套不深。

**建議：** 當前可接受。若後續新增子檢查，建議改為 chain-of-checks 模式。

---

### [Low] NEW-R7: `evolution_engine.py:run_evolution` 158 行

**位置：** `evolution_engine.py:198-356`
**問題：** Grid search 主循環 + 結果排序 + TruthSourceRegistry 注入。邏輯較為線性，嵌套不深。

**建議：** 可考慮將結果處理（排序 + 注入）拆為 `_process_results()` 子方法。

---

## 五、新發現問題清單

### Critical（1 項）

| ID | 文件 | 行號 | 問題 | 預估工時 |
|----|------|------|------|---------|
| NEW-P1 | `backtest_engine.py` | 787-792 | 每 bar O(n) 列表切片 → O(n^2) 總複雜度 | 2h |

### High（12 項）

| ID | 文件 | 行號 | 問題 | 預估工時 |
|----|------|------|------|---------|
| NEW-P2 | `truth_source_registry.py` | 332 | _claims 無上限，已過期條目不清理 | 1h |
| NEW-P3 | `experiment_ledger.py` | 239 | _hypotheses 無上限，已結案條目不清理 | 1h |
| NEW-P4 | `backtest_engine.py` | 407-480 | EMA/RSI 每 bar 從頭重算，無增量計算 | 3h |
| NEW-R1 | `pipeline_bridge.py` | 466-928 | _process_pending_intents 462 行超巨方法 | 4h |
| NEW-R2 | `paper_trading_engine.py` | 1291-1632 | submit_order.mutator 341 行 | 3h |
| NEW-R3 | `paper_trading_engine.py` | 1703-1965 | tick.mutator 262 行 | 3h |
| 15 | `main_legacy.py` | 全文件 | 5,113 行單文件（持續惡化） | 16h |
| 17 | 全項目 | 多處 | `int(time.time()*1000)` 156 處內聯 | 2h |
| 20 | 全項目 Python | 多處 | 182 處 logger f-string | 3h |
| 21 | `pipeline_bridge.py` | 333-464 | on_tick 132 行（惡化自 110→132） | 2h |
| 28 | `main_legacy.py` | 1032-1058 | compile_state 3 次 O(n) 列表掃描 | 2h |
| 32 | 前端 JS/HTML | 多處 | 3 處獨立 api()/apiGet() 實現 | 1h |

### Medium（26 項）

| ID | 文件 | 行號 | 問題 | 預估工時 |
|----|------|------|------|---------|
| NEW-S1 | `backtest_engine.py` | 370-404 | SMA/EMA/RSI 純函數與 indicators/ 重複 | 1h |
| NEW-S2 | 3 新路由文件 | 多處 | sys.path 5 層 dirname 重複 4 次 | 30min |
| NEW-P5 | `pipeline_bridge.py` | 466-928 | 鎖持有範圍過大（含 I/O 操作） | 3h |
| NEW-P6 | `governance_hub.py` | 全文件 | 67 處 f-string logger | 1h |
| NEW-R4 | `strategist_agent.py` | 416-662 | _handle_intel 246 行 | 2h |
| NEW-R5 | `governance_hub.py` | 1264-1617 | 兩個 >160 行事件處理方法 | 2h |
| 16 | `main_legacy.py`/`main.py` | 983/28 | compile_state / stable_compile_state 重複 | 2h |
| 18 | `main_legacy.py` | 多處 | 寫操作 4 行 boilerplate 重複 20+ 次 | 4h |
| 19 | `main_legacy.py` | 多處 | _write_audit_fields 四步序列重複 | 3h |
| 22 | `pipeline_bridge.py` | 466-928 | _process_pending_intents 名稱不符職責 | 10min |
| 23 | `pipeline_bridge.py` | 1184-1297 | _check_edge_filter ~115 行 | 1h |
| 24 | `pipeline_bridge.py` | 多處 | 9 個 setter 重複模式 | 1h |
| 26 | `main.py` | 144-153 | Monkey patching 無顯式警告 | 10min |
| 29 | `main_legacy.py` | 835-899 | _compile_effective_action_permissions O(n^2) | 1h |
| 30 | `phase2_strategy_routes.py` | 100-440 | 模組級初始化 ~140 行 | 3h |
| 31 | `main_legacy.py` | 1602-1615 | _cleanup_idempotency_cache 核心仍 O(n log n) | 1h |
| 33 | 前端 4 處 | 多處 | TOKEN_KEY 硬編碼重複 | 30min |
| 34 | `app.js` | 352-364 | baseEnvelope 硬編碼 "demo-operator" | 30min |
| 35 | 前端 4 處 | 多處 | :root CSS 變量重複定義 | 1h |
| 36 | `console.html` | 201/216 | 與 common.js 重複的 getToken/logout | 30min |
| 37 | `trading.html` | 244-298 | 獨立認證/API 未用 common.js | 1h |
| 38 | `app.js` | 352 | baseEnvelope vs ocEnvelope 重複 | 30min |
| 39 | 前端多處 | 多處 | 時鐘 setInterval 重複 | 15min |
| 42 | `governance_routes.py` | 58-78 | 每請求惰性導入 GOV_HUB | 30min |
| 25 | `pipeline_bridge.py` | 93-112 | 外部依賴未文檔化 | 30min |
| 41 | `tab-governance.html` | 全文件 | 2,129 行 + 200 處 inline style | 3h |

### Low（15 項）

| ID | 文件 | 行號 | 問題 | 預估工時 |
|----|------|------|------|---------|
| NEW-S3 | `audit_persistence.py` | 多處 | 8 處 except Exception 靜默忽略 | 30min |
| NEW-S4 | `pipeline_bridge.py` | 1264/1796/1857 | 3 處局部 json 導入與頂部不一致 | 10min |
| NEW-R6 | `h0_gate.py` | 305-400 | check() 95 行（可接受，監控中） | — |
| NEW-R7 | `evolution_engine.py` | 198-356 | run_evolution 158 行 | 1h |
| 40 | `trading.html` | 317-345 | Charts 顏色硬編碼 | 30min |
| 43 | `governance_routes.py` | 58-93 | _get_xxx() 無統一抽象 | 30min |
| 44 | 4 路由文件 | 多處 | sys.path 計算不穩健 | 1h |
| 45 | `phase2_strategy_routes.py` | 280-283 | 魔法數字 | 15min |
| 46 | `paper_trading_engine.py`/`main_legacy.py` | — | StateStore 重複模式 | 2h |
| 47 | `main_legacy.py` | 630-667 | CONFIG_CHANGE_WHITELIST 冗長 | 30min |
| 48 | `main_legacy.py` | 689-700 | build_snapshot_id 每次 JSON + SHA256 | 1h |
| 49 | `main_legacy.py` | 4338-4360 | _schedule_restart bash 拼接 | 1h |
| 8 | `pipeline_bridge.py` | 37/1264/1796/1857 | _json_mod vs _json 不一致 | 10min |
| 14 | `main_snapshot_stable.py` | — | 僅向後兼容標註 | 5min |
| 9 | `main_legacy.py` | 4033 | SlowAPIMiddleware import 位置 | 5min |

---

## 六、按文件分類的完整問題索引

### `main_legacy.py`（5,113 行，18 個問題）
15(H), 16(M), 17(H), 18(M), 19(M), 20(H partial), 28(H), 29(M), 30(M partial), 31(M), 47(L), 48(L), 49(L), 9(L)

### `pipeline_bridge.py`（1,937 行，10 個問題）
NEW-P5(M), NEW-R1(H), NEW-S4(L), 8(L), 20(H partial), 21(H), 22(H), 23(M), 24(M), 25(M)

### `paper_trading_engine.py`（2,056 行，4 個問題）
NEW-R2(H), NEW-R3(H), 17(H partial), 46(L)

### `governance_hub.py`（1,889 行，3 個問題）
NEW-P6(M), NEW-R5(M), 20(H partial)

### `governance_routes.py`（1,928 行，2 個問題）
42(M), 43(L)

### `backtest_engine.py`（1,209 行，3 個問題）
NEW-P1(C), NEW-P4(H), NEW-S1(M)

### `truth_source_registry.py`（821 行，1 個問題）
NEW-P2(H)

### `experiment_ledger.py`（617 行，1 個問題）
NEW-P3(H)

### `strategist_agent.py`（994 行，1 個問題）
NEW-R4(M)

### `evolution_engine.py`（539 行，1 個問題）
NEW-R7(L)

### `h0_gate.py`（832 行，1 個問題）
NEW-R6(L)

### `phase2_strategy_routes.py`（1,541 行，2 個問題）
30(M), 45(L)

### `main.py`（352 行，1 個問題）
26(M)

### `audit_persistence.py`（1 個問題）
NEW-S3(L)

### `backtest_routes.py` + `evolution_routes.py` + `experiment_routes.py`（1 個共同問題）
NEW-S2(M)

### 前端文件（11 個問題）
32(H), 33(M), 34(M), 35(H), 36(H), 37(H), 38(M), 39(M), 40(L), 41(M), trading.html/console.html/app.js/common.js

---

## 七、改進建議（不改功能的前提下）

### 緊急（1-2 天內）
1. **NEW-P1: backtest_engine O(n^2) 切片** — 改為索引模式（已有 `_BacktestKlineAdapter` 可重用）
2. **NEW-P2/P3: 無限增長 dict** — 為 TruthSourceRegistry 和 ExperimentLedger 添加 MAX_SIZE + 定期清理
3. **前端認證統一**（#32/#33/#36/#37）— 統一使用 common.js 的 ocApi/ocGetToken

### 短期（1 週內）
4. **NEW-P4: 增量指標計算** — 保存前 bar 的 EMA/RSI 狀態，每 bar O(1) 更新
5. **NEW-S1: 純函數指標提取** — indicators/pure.py 共享模組
6. **NEW-S2: sys.path 統一** — 提取為公共函數
7. **#20: logger f-string** — 至少優先修復 governance_hub(67處) 和 pipeline_bridge 熱路徑

### 中期（1 個月內）
8. **#15: main_legacy.py 拆分** — 最大技術債，持續惡化中
9. **NEW-R1: _process_pending_intents 拆分** — 462 行超巨方法
10. **NEW-R2/R3: paper_trading_engine mutator 拆分** — 341 行 + 262 行
11. **前端 CSS 統一**（#35）— 刪除 :root 變量重複

### 長期
12. **#16: compile_state 合併** — 消除最大邏輯重複
13. **#18/#19: 寫操作 boilerplate 提取** — 輔助函數模式
14. **PipelineBridge DI 改造** — setter → 構造函數

---

## 八、與 March 31 報告的差異總結

**改善：**
- 3 個 Critical 問題全部修復（set_analyst_agent 重複、inspect.signature 每次調用、openclaw_proxy 阻塞 I/O）
- auth_login 磁盤 I/O 已改為啟動緩存
- setInterval 洩漏已修復
- 安全相關問題（速率限制、治理環境變量）已修復

**惡化：**
- `main_legacy.py` 從 4,973→5,113 行（+140 行）
- `_process_pending_intents` 從 ~300→462 行（+162 行）
- `on_tick` 從 ~110→132 行（+22 行）
- `int(time.time()*1000)` 從 128→156 處（+28，新文件帶入）
- sys.path 重複從 1→4 處（3 個新路由文件複製）
- `tab-governance.html` 持續膨脹（200 處 inline style）

**新風險：**
- backtest_engine O(n^2) 性能問題（新增模組，可能在 EvolutionEngine 使用中放大）
- truth_source_registry 和 experiment_ledger 無界 dict（長期運行記憶體風險）
- 純函數指標重複（backtest_engine vs indicators/）

---

*評估覆蓋文件總計：62 個 Python app 文件 + 25 個 local_model_tools Python 文件 + 20 個前端文件（HTML/JS/CSS）= 107 個文件，約 67,544 行代碼*
*E5 Optimization Engineer / 2026-04-01*
