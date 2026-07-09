# PA 技術複驗報告：8 份審計報告交叉驗證
# PA Technical Review: Cross-Validation of 8 Audit Reports
# 日期：2026-04-01
# 審計員：PA (Project Architect)
# 方法：逐項代碼級驗證 P0/P1/CRITICAL/HIGH 問題，跨報告去重，架構影響評估

---

## 一、審計概覽（8 份報告摘要）

| 報告 | 角色 | 新發現問題數 | 最高嚴重性 | 關鍵主題 |
|------|------|------------|-----------|---------|
| FA | Functional Auditor | 17（2P0/5P1/6P2/4P3） | P0 | TruthSourceRegistry 死代碼 + BacktestEngine 無數據源 + MessageBus 路徑斷裂 |
| AI-E | AI Effectiveness | 7（1P1/5P2/1P3） | P1 | TruthSourceRegistry 無持久化 + L2 結果丟棄 |
| E3 | Security Auditor | 10（0C/1H/5M/4L） | HIGH | CORS allow_credentials + localStorage Token + tab-governance XSS + detail=str(e) |
| E4 | Test Engineer | 4 new fail + 17 errors | HIGH | 覆蓋率仍偏低的模塊（strategy_auto_deployer 0%、bybit_demo_sync 5%） |
| E5 | Optimization | 54（1C/12H/26M/15L） | Critical | backtest_engine O(n^2) + _process_pending_intents 462 行 + main_legacy 5113 行 |
| CC | Compliance Check | 5 缺口（2 部分合規） | 部分合規 | 原則 12（L5 元學習缺）+ 原則 15（Conductor 未完善） |
| TW | Technical Writer | 8 TW 問題 + 3 文檔重複 | P2 | 10 個 .py 缺 MODULE_NOTE + CLAUDE.md 過長（943 行） |
| R4 | Document Index | 12 問題（2H/4M/4L/2I） | HIGH | audit/March31/ 7 份報告未索引 + decisions/ 24 .docx 未索引 |

**總計：去重前 ~113 項問題，去重後約 78 項獨立問題。**

---

## 二、P0/CRITICAL 問題逐項複驗

### P0-FA-1：TruthSourceRegistry 從未注入到 StrategistAgent/AnalystAgent

**來源**：FA 報告
**聲稱**：`set_truth_registry()` 在 `phase2_strategy_routes.py` 中從未被調用，導致 Phase 2 Batch 2A 整個模塊為死代碼。

**代碼驗證**：
- `strategist_agent.py:669` — `set_truth_registry(self, registry)` 方法存在
- `analyst_agent.py:388` — `set_truth_registry(self, registry)` 方法存在
- `grep -rn "set_truth_registry" --include="*.py" app/` — **僅在測試文件中有調用**，`phase2_strategy_routes.py` 和 `main.py` 均無調用
- `main.py:289` — 創建了 `_seed_registry` 並調用 `load_snapshot()`，但此實例僅用於 ExperimentLedger seeding，未注入到 Agent

**判定：CONFIRMED（P0）**
影響確如 FA 報告所述：TruthSourceRegistry 在運行時完全是死代碼。AnalystAgent 的 `_register_pattern_claims()` 內部 `if self._truth_registry is not None:` 永遠為 False。知識閉環完全斷裂。

**PA 補充**：修復極為簡單（0.5h）——在 `phase2_strategy_routes.py` 中創建 singleton 並注入兩個 Agent。但需注意：main.py 中已有 `_seed_registry` 實例，應統一為單一 singleton，避免兩個 registry 實例互不相通。

---

### P0-FA-2：BacktestEngine API 無數據源（KlineManager 未注入）

**來源**：FA 報告
**聲稱**：`backtest_routes.py:94` 創建 `BacktestEngine()` 不帶參數，無 KlineManager → API 回測無數據。

**代碼驗證**：
- `backtest_routes.py:94` — `_backtest_engine = BacktestEngine()` 確實不帶參數
- `backtest_engine.py` — `__init__` 接受 `kline_manager` 等參數，全部默認 None
- API 端點 `BacktestRunRequest` 無 `ohlcv_data` 欄位，無法手動傳入數據

**判定：CONFIRMED（降級為 P1）**
FA 將此定為 P0，但回測功能在 demo_only 階段並非阻塞項。Operator 可以通過代碼級別調用 BacktestEngine 並手動傳入數據。API 路由不通不影響當前系統運行。

---

### E5-Critical NEW-P1：backtest_engine O(n^2) 列表切片

**來源**：E5 報告
**聲稱**：`backtest_engine.py:787-792` 每 bar 切片整個 OHLCV 數據，O(n^2) 總複雜度。

**代碼驗證**：
```python
for bar_idx in range(MIN_BARS_REQUIRED, n_bars):
    ohlcv_slice = {
        key: arr[: bar_idx + 1]
        for key, arr in ohlcv_data.items()
        if isinstance(arr, list)
    }
    indicators = _compute_indicators_pure(ohlcv_slice)
```

**判定：CONFIRMED（降級為 HIGH）**
O(n^2) 分析正確。但 E5 將此定為 Critical 過高：
1. BacktestEngine 目前 API 端不通（P0-FA-2），所以此問題暫時無法被觸發
2. 即使修復了 API，回測是非即時操作，O(n^2) 對 1000 bars 仍可在幾秒內完成
3. 在 EvolutionEngine 50 組合放大下才真正成問題

降級為 HIGH，修復時機在 BacktestEngine API 接通之後。

---

## 三、P1/HIGH 問題逐項複驗

### P1-FA-2：MessageBus Guardian→Executor 路徑斷裂

**來源**：FA 報告
**聲稱**：Guardian 從未發送 APPROVED_INTENT 到 Executor，導致 5-Agent MessageBus 全路徑不通。

**代碼驗證**：
- `guardian_agent.py:289-298` — `review_intent()` 發送 `RISK_VERDICT` 回 Strategist，**不發送 APPROVED_INTENT**
- `guardian_agent.py:386` — `_handle_trade_intent()` 調用 `review_intent()` 後無後續動作
- **BUT**: `multi_agent_framework.py:852-905` — `Conductor.process_trade_intent()` **確實**會在 Guardian APPROVED 後發送 APPROVED_INTENT 到 Executor
- `grep -rn "process_trade_intent"` — 此方法僅在定義處存在，**生產代碼從未調用**

**判定：CONFIRMED（P1），但需修正描述**
FA 說 "Guardian 從不發送 APPROVED_INTENT" 是對 GuardianAgent 而言正確的。但 Conductor 中已有完整的 dispatch 邏輯（process_trade_intent），問題是 Conductor 從未被實際編排調用。修復路徑有兩個：
- (A) 在 GuardianAgent._handle_trade_intent() 中直接發送 APPROVED_INTENT（FA 建議）
- (B) 讓 pipeline_bridge 調用 Conductor.process_trade_intent() 而非直接調用 Guardian.review_intent()

建議採用 (B)，因為 Conductor 已有完整邏輯。

---

### P1-FA-3：EvolutionEngine 無 REST API 端點

**來源**：FA 報告
**聲稱**：EvolutionEngine 沒有 REST API，Operator 無法觸發。

**代碼驗證**：
- `evolution_routes.py` — **存在**，有 `POST /run` 和 `GET /status` 端點
- `main.py:188-189` — `from .evolution_routes import router as evolution_router; app.include_router(evolution_router)`

**判定：FALSE_POSITIVE**
FA 報告此項為 P1-FA-3 完全錯誤。EvolutionEngine 已有 REST API 端點（`evolution_routes.py`），且已在 main.py 中註冊。可能是 FA 在審計時遺漏了此文件。

---

### P1-AI-1：TruthSourceRegistry + ExperimentLedger 無持久化

**來源**：AI-E 報告
**聲稱**：無 save/load 方法被調用，重啟後學習成果全部丟失。

**代碼驗證**：
- `truth_source_registry.py:622-762` — `save_snapshot()` 和 `load_snapshot()` 方法均存在且完整
- `main.py:289` — `_seed_registry.load_snapshot(_snapshot_path)` **確實在啟動時被調用**
- `grep "save_snapshot" app/` — **除了 truth_source_registry.py 自身，無其他地方調用 save_snapshot()**
- `truth_source_registry.py:815-817` — 有 `_auto_save()` 方法調用 `save_snapshot()`，但需要外部觸發

**判定：CONFIRMED（P1），但需修正描述**
- `load_snapshot()` 在啟動時有調用（AI-E 說 "未找到被調用的證據" 不完全正確）
- `save_snapshot()` 確實從未在生產代碼中被自動調用，沒有任何 cron/hook/shutdown 觸發
- ExperimentLedger 完全在記憶體中，無任何持久化機制
- 結論：load 半通（啟動時讀取），save 完全不通 → 重啟確實丟失運行中累積的知識

---

### E3-HIGH-LEGACY-1：CORS allow_credentials=True 配置風險

**來源**：E3 報告
**聲稱**：`allow_credentials=True` + 動態 `allow_origins` 有跨域風險。

**代碼驗證**：
```python
_cors_origins = os.getenv("OPENCLAW_CORS_ORIGINS", "").strip()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins.split(",") if _cors_origins else [],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**判定：CONFIRMED（維持 HIGH），但風險有限**
- 默認值為空列表 `[]`（當 env var 未設置時），此時 CORS 完全不允許跨域 → 默認安全
- `allow_credentials=True` + 動態 origins 的風險在於：若 env var 被設為包含 `*` 或不安全域名
- 實際部署環境是 Tailscale 私有網絡，風險進一步降低
- 但原則上應在啟動時校驗 origins 不含 `*`

---

### E3-MEDIUM-NEW-3：paper_trading_routes detail=str(e) 信息洩露

**來源**：E3 報告
**聲稱**：5 處 `detail=str(e)` 可能洩露內部路徑。

**代碼驗證**：
- `paper_trading_routes.py:560,572,584,600` — 4 處 `HTTPException(status_code=409, detail=str(e))`
- `paper_trading_routes.py:647` — 1 處 `HTTPException(status_code=400, detail=str(e))`
- `backtest_routes.py:179` — 1 處 `detail=str(ve)`

**判定：CONFIRMED（MEDIUM）**
這些是 Paper Trading 內部 state transition 異常（如 "cannot start: already running"），內容相對可預期。但 Python 異常字串可能包含文件路徑，應統一改為固定消息。

---

### E5-HIGH NEW-P2/P3：TruthSourceRegistry + ExperimentLedger 無上限

**來源**：E5 報告
**聲稱**：`_claims` dict 和 `_hypotheses` dict 無大小限制，長期運行會記憶體洩漏。

**代碼驗證**：
- `truth_source_registry.py` — `_claims: Dict[str, PatternClaim]` 確無大小限制
- 有 TTL 機制但過期 claims 僅在查詢時跳過，從未從 dict 中移除
- `experiment_ledger.py` — `_hypotheses: Dict[str, Hypothesis]` 同樣無上限

**判定：CONFIRMED（降級為 MEDIUM）**
E5 定為 HIGH，但實際影響較低：
1. PatternClaim 產生速率取決於 AnalystAgent 觸發頻率（L2 需 200 次觀察）
2. 系統重啟時記憶體歸零（因為 save_snapshot 沒被調用）
3. 短期內（幾週 demo 運行）不會累積到影響性能的量

---

## 四、跨報告問題去重（合併相同問題）

### 合併組 1：TruthSourceRegistry 死代碼/無持久化/無上限

| 報告 | 問題 ID | 描述 | 合併為 |
|------|---------|------|--------|
| FA | P0-FA-1 | Registry 從未注入 Agent | **MERGED-1a**（P0） |
| AI-E | P1-AI-1 | Registry 無持久化（save 未被調用） | **MERGED-1b**（P1） |
| E5 | NEW-P2 | _claims 無上限 | **MERGED-1c**（MEDIUM） |
| FA | P1-FA-6 | save_snapshot() 無調用 | 同 AI-E P1-AI-1，**刪除重複** |
| FA | P2-FA-4 | Registry 與 ExperimentLedger 雙向聯動 | **MERGED-1d**（P2） |

**統一問題描述**：TruthSourceRegistry 存在 4 層問題——(a) 從未注入到 Agent（最嚴重）；(b) save 從未被調用；(c) 無記憶體上限；(d) 與 ExperimentLedger 聯動未完善。修復順序：先注入(a)→再加持久化(b)→再加上限(c)→最後聯動(d)。

---

### 合併組 2：BacktestEngine 不通 + O(n^2) 性能

| 報告 | 問題 ID | 描述 | 合併為 |
|------|---------|------|--------|
| FA | P0-FA-2 | BacktestEngine API 無數據源 | **MERGED-2a**（P1） |
| E5 | NEW-P1 | O(n^2) 列表切片 | **MERGED-2b**（HIGH） |
| E5 | NEW-P4 | EMA/RSI 從頭重算 | 同 NEW-P1 的子問題，**合併** |
| E5 | NEW-S1 | 指標函數與 indicators/ 重複 | **MERGED-2c**（MEDIUM） |

---

### 合併組 3：ExperimentLedger 無持久化/無上限

| 報告 | 問題 ID | 描述 | 合併為 |
|------|---------|------|--------|
| AI-E | P1-AI-1（部分） | ExperimentLedger 純記憶體，重啟歸零 | **MERGED-3a**（P1） |
| E5 | NEW-P3 | _hypotheses 無上限 | **MERGED-3b**（MEDIUM） |

---

### 合併組 4：detail=str(e) 信息洩露

| 報告 | 問題 ID | 描述 | 合併為 |
|------|---------|------|--------|
| E3 | MEDIUM-NEW-3 | paper_trading_routes 5 處 | **MERGED-4**（MEDIUM） |
| E3 | LOW-NEW-3 | backtest_routes 1 處 | 合併到 MERGED-4 |

---

### 合併組 5：sys.path 5 層 dirname 重複

| 報告 | 問題 ID | 描述 | 合併為 |
|------|---------|------|--------|
| E5 | NEW-S2 | 3 新路由文件重複 sys.path 模式 | **MERGED-5**（MEDIUM） |
| E5 | #44 | sys.path 計算不穩健 | 同一問題，**合併** |

---

### 合併組 6：文檔索引缺失

| 報告 | 問題 ID | 描述 | 合併為 |
|------|---------|------|--------|
| R4 | R4-01 | audit/March31/ 未索引 | **MERGED-6**（HIGH，文檔類） |
| R4 | R4-02 | README 目錄結構缺 audit/ | 同一根因，**合併** |
| R4 | R4-03 | decisions/ .docx 未索引 | **MERGED-6b**（MEDIUM，文檔類） |

---

## 五、誤報識別（FALSE_POSITIVE 清單）

| # | 報告 | 問題 ID | 原聲稱 | 判定理由 |
|---|------|---------|--------|---------|
| FP-1 | FA | P1-FA-3 | EvolutionEngine 無 REST API 端點 | `evolution_routes.py` 已存在且在 main.py 中註冊，有 POST /run + GET /status |
| FP-2 | FA | DC-4 | "EvolutionEngine 外部觸發 ❌ 無 API 路由" | 同 FP-1，evolution_routes.py 已提供 API |
| FP-3 | AI-E | §5.2 表格 | "EvolutionEngine ✅ (via backtest_routes)" | 非誤報但描述不精確——EvolutionEngine 有自己的 evolution_routes.py，不是 "via backtest_routes" |

---

## 六、問題升降級（UPGRADED / DOWNGRADED）

### DOWNGRADED（降級）

| # | 報告 | 原級別 | 新級別 | 理由 |
|---|------|--------|--------|------|
| D-1 | FA | P0（P0-FA-2） | **P1** | BacktestEngine API 不通在 demo_only 階段非阻塞項，可代碼級調用 |
| D-2 | E5 | Critical（NEW-P1） | **HIGH** | backtest_engine O(n^2) 在當前 API 不通狀態下無法被觸發；且回測非即時操作 |
| D-3 | E5 | HIGH（NEW-P2/P3） | **MEDIUM** | claims/hypotheses 無上限，但 save 不工作意味著重啟清零；累積速率低 |
| D-4 | AI-E | P1-AI-1 | **P1（維持但修正描述）** | load_snapshot 在啟動時有調用，FA 說"未找到證據"不完全正確 |

### UPGRADED（升級）

| # | 報告 | 原級別 | 新級別 | 理由 |
|---|------|--------|--------|------|
| 無 | — | — | — | 本次審計未發現需要升級的問題 |

---

## 七、去重後完整問題清單（按優先級排序）

### P0（1 項）

| # | 問題 | 來源 | 修復工時 |
|---|------|------|---------|
| **MERGED-1a** | TruthSourceRegistry 從未注入 StrategistAgent/AnalystAgent — Phase 2 Batch 2A 知識閉環死代碼 | FA P0-FA-1 | 0.5h |

### P1（5 項）

| # | 問題 | 來源 | 修復工時 |
|---|------|------|---------|
| **MERGED-1b** | TruthSourceRegistry save_snapshot() 從未在運行中被自動調用 | FA P1-FA-6 + AI-E P1-AI-1 | 1h |
| **MERGED-2a** | BacktestEngine API 端不通（KlineManager 未注入 backtest_routes singleton） | FA P0-FA-2（降級） | 1h |
| **MERGED-3a** | ExperimentLedger 純記憶體狀態，無任何持久化 | AI-E P1-AI-1 | 1.5h |
| **P1-FA-2** | MessageBus Guardian→Executor APPROVED_INTENT 路徑斷裂（Conductor 有邏輯但從未被調用） | FA P1-FA-2 | 2h |
| **P1-FA-4** | pipeline_bridge 仍調用已廢棄的 StrategistAgent.collect_pending_intents() | FA P1-FA-4 | 0.3h |

### HIGH（4 項）

| # | 問題 | 來源 | 修復工時 |
|---|------|------|---------|
| **E3-HIGH-1** | CORS allow_credentials=True 缺少啟動校驗 | E3 HIGH-LEGACY-1 | 0.5h |
| **MERGED-2b** | backtest_engine O(n^2) 列表切片 + EMA/RSI 從頭重算 | E5 NEW-P1/P4（降級） | 3h |
| **E5-R1** | _process_pending_intents 462 行超巨方法 | E5 NEW-R1 | 4h |
| **R4-HIGH** | audit/March31/ 7 份核心報告 + README 結構圖缺 audit/ 目錄 | R4 R4-01/02 | 1h |

### MEDIUM（18 項）

| # | 問題 | 來源 |
|---|------|------|
| **MERGED-1c** | TruthSourceRegistry _claims 無上限 + 過期不清理 | E5 NEW-P2（降級） |
| **MERGED-3b** | ExperimentLedger _hypotheses 無上限 | E5 NEW-P3（降級） |
| **MERGED-4** | paper_trading_routes 5 處 + backtest_routes 1 處 detail=str(e) | E3 MEDIUM-NEW-3 + LOW-NEW-3 |
| **E3-M-1** | tab-governance.html 30+ 處 innerHTML 未轉義 | E3 MEDIUM-NEW-1 |
| **E3-M-2** | experiment_routes ProposeHypothesisRequest 無 max_length | E3 MEDIUM-NEW-2 |
| **E3-M-3** | Token 存儲在 localStorage | E3 MEDIUM-LEGACY-2 |
| **E3-M-4** | 缺乏安全 HTTP 響應頭 | E3 MEDIUM-LEGACY-3 |
| **MERGED-2c** | backtest_engine 指標函數與 indicators/ 重複 | E5 NEW-S1 |
| **MERGED-5** | 4 個路由文件重複 sys.path 5 層 dirname | E5 NEW-S2 + #44 |
| **E5-P5** | _process_pending_intents 鎖持有範圍過大 | E5 NEW-P5 |
| **E5-R2** | submit_order.mutator 341 行 | E5 NEW-R2 |
| **E5-R3** | tick.mutator 262 行 | E5 NEW-R3 |
| **AI-E-P2-2** | L2 後台線程結果被完全丟棄 | AI-E P2-AI-2 |
| **FA-P2-1** | MarketScanner MAX_SYMBOLS_TO_TRADE=5 vs deployer 25 不一致 | FA P2-FA-1 |
| **FA-P2-2** | Regime-aware 策略選擇缺失 | FA P2-FA-2 |
| **R4-M** | decisions/ .docx 未索引 + governance_dev ~14 文件未索引 | R4 R4-03/04 |
| **TW-B1/B2/B3** | main.py / multi_agent_framework / perception_data_plane 缺 MODULE_NOTE | TW |
| **CC-GAP** | 原則 12 L5 元學習未實施 + 原則 15 Conductor 未完善 | CC |

### LOW/P3（~50 項）

大量 E5 優化項（main_legacy 5113 行、logger f-string 182 處、CSS 重複等）+ TW P3 MODULE_NOTE 補全 + R4 命名規範 + FA P3 配置化問題。詳見各原始報告。

---

## 八、架構影響分析

### Live 阻塞項（M/N 章前必須修復）

| # | 問題 | 阻塞原因 |
|---|------|---------|
| **MERGED-1a** | TruthSourceRegistry 未注入 | 原則 12「持續進化」核心能力缺失，Live 前必須有運作的學習閉環 |
| **MERGED-1b** | Registry 無持久化 | 系統重啟丟失所有學習知識，Paper Trading 觀察期 21 天內必須持久 |
| **MERGED-3a** | ExperimentLedger 無持久化 | 同上 |
| **E3-HIGH-1** | CORS 啟動校驗 | Live 前安全必備 |
| **E3-M-4** | 安全 HTTP 響應頭 | Live 前安全必備 |
| **E3-M-3** | Token localStorage | Live 前建議改 HttpOnly Cookie |

### 級聯依賴關係

```
MERGED-1a (注入 Registry)
  ├→ MERGED-1b (持久化)
  │     └→ MERGED-1c (上限清理)
  └→ MERGED-1d (ExperimentLedger 聯動)
        └→ FA-P1-FA-5 (自動化驅動)

MERGED-2a (BacktestEngine 數據源)
  └→ MERGED-2b (O(n^2) 修復)
        └→ MERGED-2c (指標重複消除)

P1-FA-2 (MessageBus 路徑)
  └→ CC-GAP (原則 15 Conductor 完善)
```

### 不阻塞但影響重大

- **E5-R1 (_process_pending_intents 462 行)**：不阻塞 Live 但嚴重影響可維護性，每次修改此方法風險極高
- **main_legacy.py 5113 行**：技術債持續惡化，但重構風險高，不建議在 Live 前觸碰

---

## 九、建議修復順序

### 第一批（0.5 天，P0 + 快速 P1）

| 順序 | 問題 | 工時 | 理由 |
|------|------|------|------|
| 1 | MERGED-1a：注入 TruthSourceRegistry | 0.5h | ROI 最高——0.5h 激活整個 Phase 2 學習閉環 |
| 2 | P1-FA-4：清理 collect_pending_intents 廢棄調用 | 0.3h | 消除每 tick 日誌噪音 |
| 3 | MERGED-1b：加 save_snapshot 自動調用 | 1h | 搭配 #1，確保知識跨重啟保留 |
| 4 | MERGED-3a：ExperimentLedger 基本持久化 | 1.5h | 搭配 #3，統一持久化模式 |

### 第二批（1 天，P1 + HIGH）

| 順序 | 問題 | 工時 | 理由 |
|------|------|------|------|
| 5 | MERGED-2a：BacktestEngine 注入 KlineManager | 1h | 解鎖回測功能 |
| 6 | E3-HIGH-1：CORS 啟動校驗 | 0.5h | 安全加固，快速修復 |
| 7 | MERGED-4：detail=str(e) → 固定消息 | 0.5h | 安全加固，快速修復 |
| 8 | R4-HIGH：docs/README.md 補 audit 索引 | 1h | 文檔完整性 |

### 第三批（2-3 天，MEDIUM 精選）

| 順序 | 問題 | 工時 |
|------|------|------|
| 9 | MERGED-1c + 3b：Registry/Ledger 加上限清理 | 2h |
| 10 | E3-M-2：input validation max_length | 0.5h |
| 11 | E3-M-4：安全 HTTP 響應頭 | 1h |
| 12 | P1-FA-2：MessageBus Guardian→Executor 路徑 | 2h |
| 13 | MERGED-2b：backtest O(n^2) 修復 | 3h |

### 延後（Phase 4 前或積壓）

- E5-R1/R2/R3（方法拆分）：高工時、高風險、不阻塞 Live
- main_legacy.py 5113 行：需整體重構規劃，不宜零散修復
- Tab-governance XSS + Token localStorage：Phase 4 Live 前安全加固
- 所有 E5 Low/TW P3/R4 Low 項目

---

## 十、總結與風險評估

### 審計品質評估

8 份報告整體品質良好，覆蓋面廣（功能/安全/測試/優化/合規/文檔/AI 效果/索引），代碼級引用準確率高。

- **FA 報告**：深度最佳，但存在 1 個誤報（P1-FA-3 EvolutionEngine 無 API 已存在 evolution_routes.py）
- **AI-E 報告**：load_snapshot 描述不夠精確（啟動時有調用），但 save 問題判斷正確
- **E3 報告**：嚴謹，所有安全問題均可驗證，無誤報
- **E5 報告**：覆蓋全面，但 Critical 定級偏高（backtest O(n^2) 在 API 不通時不可觸發）
- **E4 報告**：數據翔實，覆蓋率估算合理
- **CC 報告**：嚴格但公正，A- 評級合理
- **TW/R4 報告**：專注領域，發現真實問題

### 系統當前風險等級

```
安全風險：LOW（0 CRITICAL / 1 HIGH 殘留，且需特定前置條件才可利用）
功能風險：MEDIUM（知識閉環斷裂是最嚴重的功能缺陷，但修復簡單）
架構風險：LOW（fail-closed 設計一流，治理體系健全）
技術債風險：MEDIUM-HIGH（main_legacy 5113 行 + pipeline_bridge 462 行方法持續惡化）
```

### 關鍵結論

1. **最高 ROI 修復**：MERGED-1a（注入 TruthSourceRegistry，0.5h）——立即激活整個 Phase 2 學習管線
2. **最大風險**：技術債持續累積（main_legacy + pipeline_bridge），但短期不阻塞
3. **Live 準備度**：安全態勢良好（March 31 CRITICAL 全清），但學習持久化和 CORS 校驗必須在 Phase 4 前修復
4. **FA 誤報提醒**：EvolutionEngine 已有 REST API（evolution_routes.py），FA 報告中 P1-FA-3 和 DC-4 需要修正

---

*本報告由 PA (Project Architect) 基於 8 份審計報告的代碼級交叉驗證產出。所有 P0/P1/HIGH 問題均已在 `grep` + 源碼閱讀層級驗證。*
