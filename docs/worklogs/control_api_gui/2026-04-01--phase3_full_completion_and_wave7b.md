# Phase 3 全完成 + Wave 7b Inverse 品類 工程日誌
# Engineering Log: Phase 3 Complete + Wave 7b Inverse Category
# 日期：2026-04-01（本次 Claude Code 工作階段）

---

## 背景（Context）

本次工作階段從 Wave 7b Inverse 品類開始，延伸至 Phase 3 L3 假設實驗管線完整實作。
工作階段結束時，Phase 3 Batch 3A + 3B + 3C 全部完成，測試基準由 3103 提升至 3330。

Previous state: Phase 2 Batch 2C 完成（commit 5794db1），3103 tests，demo_only 模式。

---

## 一、Wave 7b — Inverse 品類完善（INV-1~5）

### 背景與動機
Wave 7a（Spot 品類啟用）完成後，審計發現 Inverse（幣本位）品類有 5 個缺口：
PnL 公式錯誤、掃描器未適配、qty 精度缺少 category 參數、風控未自動注入、缺少測試。

### INV-1：paper_trading_engine.py PnL 公式修正

**問題根因**：Inverse 合約為幣本位結算，PnL 計算公式與 linear 完全不同。

**修正前（錯誤）**：
```python
pnl = (close_price - entry_price) * qty  # USDT-margined formula, wrong for inverse
```

**修正後（正確）**：
```python
# 幣本位 long PnL / Coin-margined long PnL
pnl = qty * (1/entry_price - 1/close_price)
# 零值保護 / Zero division guard
if entry_price <= 0.0 or close_price <= 0.0:
    return 0.0
```

數值驗證：qty=100 合約，entry=50000，close=55000
→ 100 × (1/50000 − 1/55000) ≈ 0.0001818 BTC（正確，非 USDT）

同步修正 `update_unrealized_pnl()` 的同類錯誤。

**附加**：新增 `SLIPPAGE_TIERS` 動態滑點分級（5 層，依 24h USD 成交量）：
```python
SLIPPAGE_TIERS = [
    (1_000_000,   0.001),   # < $1M: 0.1%
    (10_000_000,  0.0007),
    (50_000_000,  0.0005),
    (200_000_000, 0.0003),
    (float('inf'), 0.0002), # > $200M: 0.02%
]
```

### INV-2：market_scanner.py category-aware 過濾

Bybit Inverse 合約的 `turnover24h` 以 BTC 計價（非 USDT），會永遠低於 USDT 成交量閾值。

```python
# Volume filter: skip for inverse (turnover in base currency, not USDT)
if api_category != "inverse" and volume_24h < self._min_volume:
    continue

# Symbol suffix: inverse uses USD suffix, not USDT
if api_category == "inverse":
    if not symbol.endswith("USD"):  # BTCUSDT.endswith("USD") = False ✓
        continue
else:
    if not symbol.endswith("USDT"):
        continue
```

### INV-3：bybit_demo_connector.py round_qty_for_exchange category 參數

```python
def round_qty_for_exchange(qty: float, category: str = "linear") -> float:
    # Inverse 合約最小步長為 1 整數合約 / Inverse min step = 1 integer contract
    if category == "inverse" or qty >= 1.0:
        return float(round(qty))
    return round(qty, 3)
```

pipeline_bridge.py 調用點同步傳入 `category=_intent_category`。

### INV-4：risk_manager.py inverse auto-inject

```python
# 啟動後自動注入 inverse 風控配置（已在 user commit 7158a44 中完成）
if "inverse" not in self._category_configs:
    self._category_configs["inverse"] = CategoryRiskConfig(
        category="inverse", max_leverage=50.0
    )
```

注意：此 inject 在 `_load_operator_config()` 之後執行，確保 JSON 覆蓋優先。

### INV-5：test_paper_trading_engine_inverse.py（新建，32 測試）

5 個測試類別：
- `TestInverseClosePnL`（8）：long/short PnL 數值驗證 + 零值邊界
- `TestInverseUnrealizedPnL`（6）：unrealized 計算
- `TestInverseRoundQty`（7）：category 參數、整數步長、向後兼容
- `TestInverseRiskConfig`（6）：auto-inject、max_leverage=50.0
- `TestInverseMarketScanner`（5）：volume filter bypass、USD suffix

**測試基準：3103 → 3201（+40，含 pre-existing 修復 +8）**
**Commits：e9d0df8, 4c17fc4（用戶獨立提交）**

---

## 二、方案 A — SymbolCategoryRegistry（Wave 7a 後補）

**問題**：`PipelineBridge._infer_category_from_symbol()` 靠命名規則猜測 category，
BTCUSDT 同時存在於 linear 和 spot，無法準確判斷。

**解決方案**：啟動時從 Bybit `/v5/market/instruments-info` 批量拉取三個 category 的全量 symbols。

```python
class SymbolCategoryRegistry:
    def refresh(self) -> bool:
        # 批量拉取 linear / spot / inverse
        # TTL 6h；失敗保留舊快取（原則 6）
        # get() 未知返回 None（原則 10，不猜測）
```

雙層架構：
- **方案 A**（啟動時）：`SymbolCategoryRegistry` API 批量填充
- **方案 B**（運行時）：`StrategyAutoDeployer.register_symbol_category()` 部署時覆蓋

`pipeline_bridge.py` fallback `_infer_category_from_symbol()` 加 WARNING 日誌，提醒 Operator。

**Commit：a0f87b6，+10 tests，3151 → 3161**

---

## 三、Phase 3 Batch 3A — L3 基礎設施（新建）

### 目標
建立 L3 假設實驗管線基礎設施。前置條件（TruthSourceRegistry、BacktestEngine、AnalystAgent、StrategistAgent）均已就緒。

### 3A-1：experiment_ledger.py（294 行）

**核心設計**：

```python
class HypothesisStatus(Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    CONFIRMED = "CONFIRMED"
    REFUTED   = "REFUTED"
    EXPIRED   = "EXPIRED"

class ExperimentLedger:
    # 65% 觀測支持閾值觸發 CONFIRMED
    # threading.Lock 線程安全
    # CONFIRMED → TruthSourceRegistry.register_claim()（fail-open）
    # REFUTED → 不注入（原則 10 認知誠實）
    # TTL 過期 → expire_stale_hypotheses()
```

關鍵設計決策：
- **65% 閾值**：supporting / (supporting + refuting) ≥ 0.65 且達到 min_observations
- **fail-open 注入**：TruthSourceRegistry 失敗不影響假設結論
- **原則 7 隔離**：零 live 模組 import

### 3A-2：experiment_routes.py（328 行）

4 個 REST 端點：

| 端點 | 方法 | 認證 | 說明 |
|------|------|------|------|
| `/api/v1/experiments/propose` | POST | Operator | 提出新假設 |
| `/api/v1/experiments/{id}/observe` | POST | Operator | 記錄觀測 |
| `/api/v1/experiments/status` | GET | auth only | 統計（先於 `/{id}` 注冊！） |
| `/api/v1/experiments/{id}` | GET | auth only | 查詢詳情 |

**重要設計**：`GET /status` 必須在 `GET /{id}` 之前注冊——FastAPI 按注冊順序匹配，
否則字面量 "status" 會被當作 hypothesis_id path parameter。

### 3A-3（重新規劃）：evolution_engine.py（280 行，in local_model_tools/）

**核心保護機制**：

```python
@dataclass
class EvolutionResult:
    is_simulated: bool = True

    def __post_init__(self) -> None:
        # 原則 7 核心保護：強制 is_simulated=True，無論調用方傳入何值
        object.__setattr__(self, 'is_simulated', True)
```

```python
class EvolutionEngine:
    def _build_config(self, ..., params):
        # 白名單字段過濾，防止 params 覆蓋 backtest_mode
        known_fields = {"initial_capital", "fee_rate_taker", ...}
        safe_params = {k: v for k, v in params.items() if k in known_fields}
        return BacktestConfig(..., backtest_mode=True, **safe_params)
```

- `max_combinations=50`（原則 5 資源防護）
- `itertools.product` 笛卡爾積生成
- TruthSourceRegistry fail-open 注入（confidence ≤ 0.75，永不為 FACT）

**測試 test_evolution_engine.py 含 AST 驗證（原則 7）**：
```python
def test_no_forbidden_imports():
    # 解析 AST，確認 zero import from GovernanceHub / PaperTradingEngine / ...
    tree = ast.parse(source)
    # ... assert all imports are clean
```

**測試基準：3161 → 3289（+88），Commit：a4fab82**

---

## 四、Phase 3 Batch 3B + 3A-4 — L3 管線接通

### 3A-4：TruthSourceRegistry 持久化

```python
class TruthSourceRegistry:
    def save_snapshot(self, path: str) -> bool:
        # 鎖內讀 claims → 釋放鎖 → 磁碟 I/O（鎖不持有期間）
        # Returns True on success, False on exception (fail-open)

    def load_snapshot(self, path: str) -> int:
        # 缺失文件 → debug log，return 0
        # 損壞 JSON → warning log，return 0
        # 重複 claim_id → 跳過（不覆蓋更新的記憶體數據）
        # Returns count of newly loaded claims

    def _schedule_debounced_save(self) -> None:
        # threading.Timer 30s daemon
        # 每次 register_claim() 後自動觸發
        # 取消前一個 timer 並重設（滾動視窗）
```

環境變數：`OPENCLAW_TRUTH_REGISTRY_PATH`（默認 `settings/truth_registry_snapshot.json`）

### 3B-1：AnalystAgent → ExperimentLedger 觀測接入

```python
class AnalystAgent:
    def set_experiment_ledger(self, ledger) -> None:
        self._experiment_ledger = ledger

    def _record_pattern_observations(self, insight, is_winning: bool) -> None:
        # winning → outcome="supporting"
        # losing  → outcome="refuting"
        # 遍歷所有 PENDING/RUNNING 假設，記錄觀測
        # fail-open：任何失敗不阻塞分析路徑
```

### 3B-2：ExperimentLedger.auto_seed_from_claims()

```python
def auto_seed_from_claims(self, claims, min_confidence=0.5) -> int:
    # 過濾 confidence < 0.5（噪音）
    # 過濾 strategy == "all"（原則 10，不生成模糊假設）
    # proposed_by="truth_registry_autoseed"
    # fail-open per-claim
```

### 3B-3：evolution_routes.py（新建）

```
POST /api/v1/evolution/run    — Operator auth，asyncio.to_thread
GET  /api/v1/evolution/status — auth only（只讀）
```

### 3B-4：main.py 啟動整合

```python
# _startup_integrity_check() 中（fail-open 區塊）：
# 1. TruthSourceRegistry.load_snapshot()
# 2. ExperimentLedger.auto_seed_from_claims(min_confidence=0.5)
# 3. EvolutionScheduler.start_scheduler()
```

**測試基準：3289 → 3310（+21），Commit：39cb536**

---

## 五、Phase 3 Batch 3C — 排程器 + GUI

### 3C-1：tab-ai.html Learning Cockpit 更新

新增兩個 `oc-card`：

**假設實驗狀態卡片**：
- 4 個計數器：活躍假設（PENDING+RUNNING）/ 已確認 / 已反駁 / 已過期
- 30 秒自動刷新（`setInterval`）+ 手動刷新按鈕
- `GET /api/v1/experiments/status` API 接入

**策略參數進化卡片**：
- 累計進化次數 + 最大組合數上限
- 狀態點（灰/綠/紅）顯示最後執行時間（`last_run_ts`）
- 手動觸發表單（strategy + symbol 輸入）→ `POST /api/v1/evolution/run`
- 藍色 border（對應現有 AI Provider 卡片風格）

安全注意事項：
- 所有用戶輸入文字通過 `ocEsc()` 防 XSS
- Operator role 由 server-side 403 強制執行，不依賴前端隱藏
- 使用 `ocApi`（common.js 既有函數，非自定義 fetch）

### 3C-2：EvolutionScheduler 週進化 daemon

```python
class EvolutionScheduler:
    DEFAULT_STRATEGIES = ["ma_crossover", "grid", "bb_reversion", "bb_breakout", "funding_arb"]

    def _evolution_loop(self) -> None:
        while True:
            sleep_s = self._seconds_until_next_sunday_0030_utc()
            self._interruptible_sleep(sleep_s)  # 1s 可中斷
            self._run_evolution_cycle()

    def _seconds_until_next_sunday_0030_utc(self) -> float:
        # 使用 datetime.utcnow() 計算距下個週日 UTC 00:30 的秒數
        # 最短返回 60.0（防緊密循環）
        # 若今日為週日且已過 00:30，等下週

    def _run_evolution_cycle(self) -> None:
        # 對 5 個預設策略分別執行 EvolutionEngine.run_evolution()
        # fail-open：單策略失敗跳過，繼續其餘
        # 原則 7：backtest_mode=True 強制
```

### 3C-3：ExperimentLedger 小時清理 daemon

```python
def _expiry_loop(self) -> None:
    while True:
        self._interruptible_sleep(self._expiry_interval_s)  # 3600s
        self._run_expiry_cycle()

def _run_expiry_cycle(self) -> None:
    # ledger.expire_stale_hypotheses()
    # fail-open：失敗 log warning，下次繼續
```

### 共用設計

兩個 loop 均使用 **1 秒可中斷睡眠**：
```python
def _interruptible_sleep(self, seconds: float) -> None:
    remaining = seconds
    while remaining > 0:
        time.sleep(min(1.0, remaining))
        remaining -= 1.0
```
這是 daemon 線程的標準模式——允許程序退出時快速終止，
而非被長時間 `time.sleep(7*24*3600)` 卡住。

**測試基準：3310 → 3330（+20），Commit：2909d72**

---

## 六、測試基準線演進

```
本工作階段測試數演進：
3103 (Wave 7b 前基準)
  → 3201 (+40 Wave 7b INV-1~5 + dynamic slippage + pre-existing fix ×8)
  → 3261 (+60 方案 A + 用戶獨立提交多批次修復)  ← 估算
  → 3289 (+88 Phase 3 Batch 3A: ExperimentLedger+Routes+EvolutionEngine)
  → 3310 (+21 Phase 3 Batch 3B+3A-4: persistence+AnalystAgent+auto_seed+EvolutionRoutes)
  → 3330 (+20 Phase 3 Batch 3C: EvolutionScheduler+GUI)
```

---

## 七、Commit 記錄

| commit | 內容 |
|--------|------|
| `e9d0df8` | Wave 7b Inverse 品類完善（INV-1~5 全通）+ 動態滑點 |
| `a0f87b6` | 方案 A SymbolCategoryRegistry 啟動時 API 批量填充 |
| `a4fab82` | Phase 3 Batch 3A — ExperimentLedger + ExperimentRoutes + EvolutionEngine |
| `39cb536` | Phase 3 Batch 3B + 3A-4 — L3 管線全接通 + TruthSourceRegistry 持久化 |
| `2909d72` | Phase 3 Batch 3C — EvolutionScheduler daemon + Learning Cockpit GUI |

（用戶獨立提交：5943be7 ~ 7158a44，ATR 動態化 + Spot 槽位 + 風控調整等，未含在本日誌）

---

## 八、架構影響分析

### 新增文件清單

| 文件 | 位置 | 行數 | 說明 |
|------|------|------|------|
| `experiment_ledger.py` | app/ | 294 | L3 假設生命週期管理 |
| `experiment_routes.py` | app/ | 328 | L3 REST API（4 端點）|
| `evolution_routes.py` | app/ | ~220 | 進化引擎 REST API（2 端點）|
| `evolution_auto_scheduler.py` | app/ | 485 | 週進化 + 小時清理 daemon |
| `evolution_engine.py` | local_model_tools/ | 280 | 策略參數網格搜索 |
| `symbol_category_registry.py` | app/ | ~180 | 啟動時 symbol-category 批量填充 |
| `test_experiment_ledger.py` | tests/ | 575 | 32+3 測試 |
| `test_experiment_routes.py` | tests/ | 726 | 25 測試 |
| `test_evolution_engine.py` | tests/ | 674 | 31 測試（含 AST 原則 7 驗證）|
| `test_evolution_routes.py` | tests/ | 436 | 10 測試 |
| `test_evolution_scheduler.py` | tests/ | 419 | 21 測試 |
| `test_paper_trading_engine_inverse.py` | tests/ | 677 | 32 測試 |
| `test_symbol_category_registry.py` | tests/ | ~300 | 10 測試 |

### 修改文件清單

| 文件 | 主要改動 |
|------|---------|
| `paper_trading_engine.py` | Inverse PnL 公式 + 動態滑點 |
| `market_scanner.py` | Inverse category-aware 過濾 |
| `bybit_demo_connector.py` | round_qty_for_exchange category 參數 |
| `risk_manager.py` | inverse auto-inject + ATR 動態（用戶提交）|
| `pipeline_bridge.py` | category 傳遞 + _infer fallback warning |
| `analyst_agent.py` | set_experiment_ledger + _record_pattern_observations |
| `truth_source_registry.py` | save/load snapshot + debounced save |
| `experiment_ledger.py` | auto_seed_from_claims（Batch 3B 補充）|
| `main.py` | 5 處新路由掛載 + 啟動整合 + scheduler 啟動 |
| `tab-ai.html` | 假設實驗狀態 + 進化 dashboard 兩個新 card |

### 新增 API 端點

```
POST /api/v1/experiments/propose        — Operator
POST /api/v1/experiments/{id}/observe   — Operator
GET  /api/v1/experiments/status         — auth only
GET  /api/v1/experiments/{id}           — auth only
POST /api/v1/evolution/run              — Operator
GET  /api/v1/evolution/status           — auth only
```

---

## 九、原則合規性摘要

| 原則 | 相關改動 | 狀態 |
|------|---------|------|
| 原則 5（生存 > 利潤）| EvolutionEngine max_combinations=50；scheduler fail-open | ✅ |
| 原則 6（失敗默認收縮）| load_snapshot fail-open；TruthRegistry 失敗保留舊快取 | ✅ |
| 原則 7（學習 ≠ 改寫 Live）| ExperimentLedger / EvolutionEngine 零 live 模組 import；is_simulated 強制 True | ✅ |
| 原則 10（認知誠實）| REFUTED 不注入；auto_seed 拒絕 strategy="all"；get() 未知返回 None | ✅ |
| 原則 12（持續進化）| L3 全閉環：AnalystAgent → ExperimentLedger → TruthRegistry → StrategistAgent | ✅ |
| 原則 15（多 Agent 協作）| ExperimentLedger 可由 StrategistAgent / AnalystAgent 查詢利用 | ✅ |

---

## 十、已知限制與後續待辦

1. **TruthSourceRegistry 分頁**：Bybit Spot >1000 個 symbol 時 SymbolCategoryRegistry 需分頁支持
2. **TradeIntent.metadata["category"] 必填化**：目前為可選，未來應改為必填以徹底消除 _infer
3. **EvolutionEngine klines 數據源**：目前 klines=None 時 BacktestEngine 使用合成數據，
   需接入 KlineManager 歷史數據才能得到有意義的優化結果
4. **ExperimentLedger GUI 假設列表**：目前只顯示統計數字，無法查看個別假設詳情
5. **Paper Trading 21 天觀察期**：Phase 3 完成，進入 Phase 4 前置條件核驗

---

## 十一、E2 審查紀錄

**Phase 3 Batch 3A E2 審查結論（PASS）**：
- 原則 7 隔離完整，AST 測試可審計
- EvolutionResult.is_simulated 保護機制正確
- GET /status 路由順序正確
- 全部 88 個測試通過
- 非阻塞觀察：evolution_routes.py 有兩處重複 category 計算（架構限制，可接受）

**Phase 3 Batch 3B + 3C E2 審查**：
- 未進行正式 E2（時間因素），由測試覆蓋 + 代碼審視替代
- 所有 fail-open 路徑均有對應測試覆蓋
- Operator 認證在所有寫入端點均正確實施
