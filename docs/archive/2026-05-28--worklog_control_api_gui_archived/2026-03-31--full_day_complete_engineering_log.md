# 2026-03-31 完整工程日誌（全天綜合記錄）
# Full Day Engineering Log — 2026-03-31
#
# 說明：本文件為全天工作的整合視圖。各部分已有獨立日誌者以「→ 詳見」指引；
#       本文負責補全獨立日誌未涵蓋的部分（Wave 0-3 安全修復、Wave 5/6 Sprint、Phase 2）。
#
# Note: Individual logs exist for some sections; this file serves as the master integration view.

---

## 全天工作總覽

2026-03-31 是本專案迄今最密集的單日工作日。
主要驅動：前一天（3/30）完成的 Round 2 冷酷功能審核 + 7-Agent 全系統審計發現 71 個問題，
其中 4 個 CRITICAL 需立即修復，15 個 P1 需同日完成。

**全天測試演進**：
```
起點：~2200 passed（7-Agent 審計前）
  → 2224 passed（P0 修復完成）
  → 2480+ passed（Wave 1-2 修復）
  → 2539 passed（P1-16 H0 Gate Day 3）
  → 2561 passed（Wave 5 Sprint 0）
  → 2610 passed（Wave 5b）
  → 2631 passed（Wave 6 Sprint 2）
  → 2650 passed（Cleanup Sprint）
  → 2675 passed（Phase 2 Batch 2A）
  → 2700 passed（Phase 2 Batch 2B）
終點：2700 passed
```

**總 Commits（本日）**：約 20+ 個

---

## 一、7-Agent 全系統審計（前置背景）

**審計規模**：71 測試文件 / 2480 測試用例 / 53 app 模組 / 全 HTML/JS/CSS
**審計角色**：E3/E4/E5/CC/A3/PM/PA 7 個並行 Agent + 交叉復驗
**發現問題**：71 項（去重）

| 優先級 | 數量 |
|--------|------|
| P0 CRITICAL | 8 |
| P1 HIGH | 18 |
| P2 MEDIUM | 29 |
| P3 LOW | 16 |

**PA 確認屬實的 4 個 CRITICAL（全部當日修復）**：
1. `/openclaw/{path}` 反向代理無認證（任何人可直接代理到 OpenClaw gateway）
2. `_require_operator_role()` isinstance 類型錯誤（所有治理端點認證失效）
3. `GovernanceHub=None` 時 `submit_order()` fail-open（應 fail-closed）
4. `Guardian=None` 時 `pipeline_bridge.py` fail-open（應 fail-closed）

---

## 二、P0 修復（Wave 0）— commit ec0e794 + c113ab2

### CRITICAL-1：openclaw_proxy 添加認證

**問題**：`/openclaw/{path}` 反向代理直接透傳，任何人無需認證即可訪問 OpenClaw gateway。

**修復**：
```python
# main.py
async def openclaw_proxy(path: str, request: Request, actor = Depends(current_actor)):
    # 1. asyncio.to_thread 避免阻塞事件循環
    # 2. 轉發 Authorization header（token 驗證）
    # 3. 過濾外部 Authorization header（防 SSRF）
    headers = {"Authorization": f"Bearer {settings.api_token}"}
```

### CRITICAL-2：`_require_operator_role()` isinstance 修復

**問題**：
```python
# 錯誤版本（永遠 True，因為 actor 是 AuthenticatedActor dataclass 而非 dict）
if isinstance(actor, dict) and actor.get("role") == "operator":
```

**修復**：
```python
# 正確版本
if not (hasattr(actor, "role") and actor.role == "operator"):
    raise HTTPException(status_code=403, detail="Operator role required")
```
影響：`governance_routes.py` 中 15+ 處屬性訪問點同步修正，補 164 個測試。

### CRITICAL-3：GovernanceHub=None fail-closed

```python
# paper_trading_engine.py submit_order()
if self._governance_hub is None:
    logger.error("submit_order: GovernanceHub not injected — fail-closed")
    return {"error": "governance_hub_unavailable"}  # 拒絕下單
```

### CRITICAL-4：Guardian=None fail-closed

```python
# pipeline_bridge.py
if self._guardian is None:
    logger.error("Guardian not injected — fail-closed, rejecting intent")
    return  # 拒絕處理 intent
```

### P0 附帶修復

- `layer2_engine.py`：negation 詞邊界正則（"not worth" 被 "worth" 子串誤判為正面）
- `layer2_engine.py`：`intent.reason` getattr 安全訪問（AttributeError 防護）
- `pipeline_bridge.py`：重複方法 `set_analyst_agent` 合併
- `paper_trading_engine.py`：7 個測試文件補 mock GovernanceHub

---

## 三、Wave 0 P1 修復

### P1-11：ollama_client max_retries = 0
```python
max_retries = 0  # CLAUDE.md 硬邊界：不重試，Operator 視重試為欺騙
```

### P1-15：layer2_tools subprocess 安全
```python
subprocess.run(["tool", "--", *args], ...)  # -- 分隔符防止參數注入
# 輸出截斷至 4096 chars
```

### P1-14：Shell 腳本日誌路徑
```bash
# 修復前：/tmp/restart.log（符號鏈接攻擊風險）
# 修復後：PROJECT_DIR/logs/restart.log
```

### P1-12：auth_login 憑證讀取緩存
```python
# 修復前：每次請求讀取文件（I/O + 競態）
# 修復後：啟動時一次性載入到 _cached_credentials，永不再讀磁碟
```

### P1-5：governance_routes 日誌注入防護
```python
def _sanitize_log(s: str) -> str:
    return s.replace("\n", "\\n").replace("\r", "\\r")[:200]
# 7 個日誌點套用 _sanitize_log()
```

---

## 四、Wave 1 — DI 統一 + HTTPException 穿透

### PA-4.3：26 處 Depends 統一化

```python
# 修復前：各端點用不同方式取 actor（重複邏輯、不一致）
# 修復後：統一 _current_actor helper + Depends(current_actor)
async def _current_actor(token: str = Depends(oauth2_scheme)) -> AuthenticatedActor:
    ...

@router.get("/status")
async def get_status(actor = Depends(current_actor)):  # 統一
    ...
```
影響：governance_routes.py 26 處 `Depends(current_actor)` 統一化。

### HTTPException 穿透

```python
# 修復前（異常被吞）：
try:
    ...
except Exception:
    raise HTTPException(500, ...)

# 修復後（HTTPException 透傳）：
try:
    ...
except HTTPException:
    raise  # 不攔截
except Exception:
    raise HTTPException(500, "Internal server error")
```

---

## 五、Wave 2 — 安全修復批次

| 修復項 | 內容 |
|--------|------|
| P0-8 | main_legacy.py `_COMPILE_STATE_SIG_CACHE` id(fn) 鍵值（每次 inspect.signature 改為緩存）|
| P1-1 | auth_login 速率限制 5次/分 + IP 鎖定 15 分鐘（5 次失敗後）`_login_fail_counts` |
| P1-13 | trading.html 7 處 `innerHTML` XSS → `ocEsc()` 包裝 |
| P1-2 | governance_hub `OPENCLAW_GOVERNANCE_ENABLED` env var 移除（治理不可通過環境變量禁用）|
| P1-6 | pipeline_bridge 65 個測試（`tests/test_pipeline_bridge.py`）|
| P1-8 | ws_listener 50 個測試（reconnect / on_close / on_error 全覆蓋）|
| P1-9 | demo_connector 41 個 HMAC `_sign()` 測試 |
| P1-18 | pipeline_bridge 並發死鎖分析 + 17 個測試（確認 on_tick 先釋放鎖再調用 downstream，無真實死鎖）|

**兩次 commit：ec0e794（16 files P0+Wave0-2 第一批）· c113ab2（10 files paper_engine + pipeline_bridge）**

---

## 六、Wave 3a — P0 新發現（commit c6a8845）

審計後發現新 P0 問題：

### P0-NEW-1：`/reconcile` 缺少 Operator 角色驗證

```python
# governance_routes.py trigger_manual_reconciliation()
_require_operator_role(actor)  # 新增
logger.info("reconcile triggered by %s", _sanitize_log(actor.actor_id))
```

### P0-NEW-2：logger 參數順序確認

檢查確認 `request_authorization` 中 `auth_id` 和 `actor.actor_id` 參數順序正確，無需修改。

### P0-NEW-3：27 處 `detail=str(e)` 改為通用訊息

```python
# 修復前（洩漏 Python 異常路徑）：
raise HTTPException(500, detail=str(e))

# 修復後：
logger.error("...", exc_info=True)
raise HTTPException(500, detail="Internal server error")
```
影響：governance_routes.py 18+ 處 + 其他路由文件共 27 處。

---

## 七、Wave 3b — P1 新發現（commit 2eda4ec）

| 修復項 | 內容 |
|--------|------|
| P1-NEW-1 | openclaw_proxy 過濾 Authorization header（用戶 Token 不透傳 Gateway）|
| P1-NEW-2 | `_COMPILE_STATE_SIG_CACHE` id(fn) → `weakref.WeakKeyDictionary`（防 GC id 重用誤判）|
| P1-NEW-3 | `_login_fail_counts` 加 `asyncio.Lock` + 2000 IP 容量上限（防並發競態 + OOM）|
| P1-NEW-4 | auth_login token 來源統一為 `settings.api_token`（消除磁碟重讀）|
| P1-NEW-5 | openclaw_proxy 異常補 `logger.warning`（不洩漏細節）|
| P1-NEW-6 | `OPENCLAW_GATEWAY_HOST` 改模組頂層緩存 `_OC_HOST`（避免每請求讀 env）|
| P1-NEW-7 | `layer2_engine._session_lock` `threading.Lock` → `asyncio.Lock`（異步安全）|

---

## 八、Wave 3c — P1 深度修復（commit bf75254）

### P1-4：Decision Lease TTL 修復

```python
# governance_hub.acquire_lease()
# 修復前：expires_at_ms 從未傳入，TTL 從未生效
lease = DecisionLease(
    ...,
    expires_at_ms=int(time.time() * 1000) + TTL_MS,  # 修復：TTL 實際生效
)
# TOCTOU 保護：先檢查再取得 → 改為原子操作
```

### P1-10：Perception Plane register_data() 零調用

新增 3 個測試確認 `register_data()` 在 PipelineBridge tick 路徑中被正確調用。

### P1-17：GovernanceHub is_authorized() 鎖外讀取

```python
# 修復前（TOCTOU）：
result = self.is_authorized()  # 讀取後鎖可能已改變

# 修復後（先賦局部變量）：
with self._rlock:
    auth_level, expires_at = self._auth_level, self._lease_expires_at
# 鎖外使用局部變量，防止 None unpack 競態
```

---

## 九、P1-16 H0 Gate 確定性門控（feature/p1-16-h0-gate-deterministic）

→ **詳見**：此為 Wave 3c 後的重點獨立 feature，分三天完成。

**Day 1（commit 3ccd982）**：
- `app/h0_gate.py`（651 行）：5 個確定性 check
  - freshness check（<1ms 實時時間戳）
  - health check（CPU/Memory/DB probe）
  - eligibility check（symbol 是否符合交易條件）
  - risk envelope check（P0/P1/P2 風控）
  - cooldown check（LRU 1000 條目上限）
- 37 個測試，SLA 驗證：實測 <5μs，SLA 要求 <1ms ✅

**Day 2（commit 5d53619）**：
- `H0HealthWorker`：背景 psutil 採樣線程（daemon + 可中斷睡眠 + db_probe_fn 可注入）
- 40 個新測試：health×12 / risk×12 / cooldown×8 / SLA timeit×2 / worker×6
- 1000 次 timeit 壓測：blocked + allowed 路徑均 <0.5ms avg ✅

**Day 3（commit 2ed20f0）**：
- `paper_trading_routes.py`：H0Gate singleton + H0HealthWorker daemon 啟動
- `pipeline_bridge.py`：`set_h0_gate()` + `on_tick()` price_ts 更新 + `_process_pending_intents()` warn-only 前置門
- `governance_routes.py`：`GET /governance/h0-gate/status` 只讀端點
- `risk_manager.py`：`set_h0_gate()` + cooldown 事件 push
- `phase2_strategy_routes.py`：H0Gate 注入 PipelineBridge + RiskManager
- 18 個集成測試（pipeline/routes/risk × warn-only/503/push 全覆蓋）

**H0 Gate 設計原則**：DOC-02 要求 <1ms 確定性門控。
所有 check 為純函數，無 I/O，無鎖爭用，只讀本地狀態。

---

## 十、Wave 4 Security + P2/P3 批次

→ **詳見**：`2026-03-31--wave4_p2p3_security_audit_fixes.md`

**Sprint 4a（commit a2f4c70）**：P2-NEW-1/2/6
**Sprint 4b（commit 6c80bc9）**：P2-NEW-3/4 + P3-TECH-1/2/3（SQL 全參數化 + Token 恆定時間比較）
**Sprint 4c（commit 448f1e7）**：P2-NEW-7/8
**Sprint 4d（commit 9cc134a）**：FA-2/3/4（功能審計修復）
**Sprint 4e（commit 87c2651）**：P2-NEW-9 + P2-NEW-5

**安全評級改善**：CRITICAL 0 / HIGH 0 / MEDIUM 2 / LOW 3（已知安全問題清零）

---

## 十一、GUI Tab 重構 + Ollama 優化

→ **詳見**：`2026-03-31--gui_tab_restructure_ollama_optimization.md`

**重點摘要**：
- Paper+Demo 合併為「測試交易」子 Tab（iframe 包裝器）
- 新增「實盤交易」鎖定佔位 Tab（tab-live.html）
- 11 Tab 重排（系統→實盤鎖→測試→K線→策略→風控→AI→學習→治理→監控→設定）
- Ollama `think=False` 修復：9B 8.7s→1.9s，27B 21s→9.9s
- 9B / 27B 模型分工（快速路徑 / 複雜任務）
- 後台市場流改為服務啟動即常駐（不依賴 Paper 會話）

---

## 十二、Position Sizing 重構

→ **詳見**：`2026-03-31--position_sizing_dynamic_qty_rebalancer.md`

**核心改動**：
- `risk_per_trade_pct`：2% → 3%（每筆最大虧損 = 總額 3%）
- `max_symbols`：10 → 25（最多同時部署 25 個幣種）
- qty 公式：`risk_amount / (stop_loss_pct × entry_price)` 每次下單重算
- 智能資本再分配：槽位滿時評估持倉保留價值，關閉弱倉投入高分新機會

---

## 十三、Paper/Demo 同步修復

→ **詳見**：`2026-03-31--paper_demo_sync_fixes.md`

**3 個 CRITICAL 修復**：
1. `_check_stops()` 止損同步平 Demo 倉位（`reduce_only=True`）
2. Demo 下單失敗從 debug→WARNING + "DIVERGED" 標記 + stats 追蹤
3. `governance_hub.reconcile()` 參數名 `demo_state→remote_state` + dataclass→dict

**根因**：`paper_trading_engine.py` 有兩條內部平倉路徑繞過 PipelineBridge，
`risk_auto_close` 路徑和 `tp_sl_triggered` 路徑從未通知 Demo，導致持倉分歧永久積累。

---

## 十四、Wave 5 Sprint — H 鏈全接通

### Wave 5 Sprint 0（commit d57ed05）

**G-05（原則 3 硬違反修復）**：
```python
# executor_agent.py submit_order() 前缺少 acquire_lease()
lease = self._governance_hub.acquire_lease(intent_id, actor)
if lease is None:
    logger.error("Failed to acquire Decision Lease — fail-closed")
    return None
order_result = self._trading_api.submit_order(...)
```

**G-01**：`DEFAULT_DAILY_HARD_CAP_USD` 15.0 → 2.0（DOC-08 §4 對齊）

### Wave 5 Sprint 5a（commit ccdff73）

**5a-1**：Scout→Strategist bus.send 鏈路端到端驗證（`intel_received` stats）

**5a-2**：H0 Gate warn-only → blocking
```python
# pipeline_bridge.py
if not self._h0_gate.check_all():
    self._stats["intents_h0_blocked"] += 1
    continue  # fail-closed，不處理此 intent
```

**5a-3**：H1 ThoughtGate MVP
```python
class ThoughtGate:
    BUDGET_LIMIT = 10      # 每週期最多 10 次 AI 調用
    COMPLEXITY_THRESHOLD = 0.3  # 低複雜度直接 heuristic
    COOLDOWN_S = 300       # 同 symbol 5 分鐘冷卻
```

**5a-4**：StrategistAgent `shadow=False` 正式切換
（前置條件：G-05 + H0 blocking + Guardian 確認，三個條件全部就緒）

**5a-5**：H2 預算門控（`Layer2CostTracker` 注入 StrategistAgent）

**5a-6**：H3 ModelRouter
```
complexity < 0.5  → L1 9B（~1.9s）
0.5 ≤ c < 0.8    → L1 27B（~9.9s）
c ≥ 0.8           → L2（Claude）
```

### Wave 5 Sprint 5b（commit 9478c00）

**5b-1**：H4 AI 輸出驗證
```python
def _validate_ai_output(output: dict) -> bool:
    confidence = output.get("confidence", -1)
    if not (0.0 <= confidence <= 1.0):
        return False  # fail-closed → fallback to heuristic
```

**5b-2/6**：H5 CostLogger（`record_ollama_call` + `roi_basis:"paper_simulation_only"` 雙端 marker）

**5b-3**：`apply_ai_consultation()` DEPRECATED
```python
warnings.warn("apply_ai_consultation is deprecated; use H1-H5 chain", DeprecationWarning)
```

**5b-4**：ScoutWorker daemon 線程（30min 週期，1s 可中斷睡眠，`start()` 冪等）

**5b-5**：原則 14 集成測試（Mock Ollama crash → L0 fallback → 交易鏈路不中斷）

---

## 十五、Wave 6 Sprint — 原則 3/12 補全

### Wave 6 Sprint 0（commit aafb18b）

**TD-1**：`pipeline_bridge._process_pending_intents()` 補入 `acquire_lease()`

發現 `pipeline_bridge.py` 中還有一個 intent 處理路徑也繞過了 Decision Lease，
與 G-05 同性質的原則 3 架構缺口。

```python
# 修復前：直接 submit_order
# 修復後：
lease = self._hub.acquire_lease(intent_id, actor)
if lease is None:
    continue  # fail-closed
result = self._trading_api.submit_order(...)
```

fail-open/closed 矩陣：
- hub=None → fail-open（降級環境允許）
- lease=None → fail-closed（不下單）
- 異常 → fail-closed

### Wave 6 Sprint 1a（commit 8f123a7）

**FA-7**：`_check_stops()` 止損路徑補 `_emit_round_trip()`
```python
# 止損觸發平倉時，同步寫入學習觀察（原則 12：每筆交易可學習）
def _check_stops(self, ...):
    if stop_triggered:
        self._emit_round_trip(...)  # 新增：學習管線接通
        self._close_position(...)
```

**P1-1 修復**：`rejected_reason` 守衛——訂單被拒時不注入虛假學習信號

### Wave 6 Sprint 1b（commit 8f123a7）

- **1B-1**：H0 cooldown 聯動 smoke test（5 個）
- **1B-2**：`/governance/h0-gate/status` 新增 `freshness_age_ms` + `freshness_score` + `data_quality_warn_only`
- **TD-3**：H5 cost_tracker 靜默異常 → `logger.warning`（靜默失敗不可接受）
- **TD-4**：`_h1_cooldown` LRU cap（1000 條目，過期清理）

### Wave 6 Sprint 2（commit 43dd2f5）

| 修復項 | 內容 |
|--------|------|
| P2-6/7/8 | RiskManager qty≤0/price≤0 fail-closed 守衛 + 5 邊界測試 |
| P2-12 | pipeline_bridge 雙源 truncation 測試（intents_capped_includes_both_sources）|
| P2-15 | strategist collect exception 回退 orchestrator 測試 |
| P2-12/15 xfail | TestGuardianNoneFailClosed 3 個過時 xfail 標記移除 |
| TD-2 | StrategistAgent `collect_pending_intents()` DEPRECATED |
| FA-8 | tab-ai.html `cost_edge_ratio` None 安全處理（`?? / !== null + 0.8 閾值對齊原則 13`）|

### Cleanup Sprint（commit 973c595）

| 修復項 | 內容 |
|--------|------|
| CS-1 | `governance_routes.py` `data_quality_warn_only: True → False`（H0 實際 fail-closed 已久，文檔不一致）|
| CS-2 | `GovernanceHub.is_globally_enabled()` 公開方法（7 處 `_enabled` 直接訪問 → 公開 API）|
| CS-3 | `main.py` `_startup_integrity_check()`（Hard deps → RuntimeError；Soft deps → warning）+ 6 測試 |
| CS-4 | `test_message_bus_load.py`（11 負載測試，文件化 ISSUE-1 無界列表 + ISSUE-2 鎖內 subscriber）|

---

## 十六、Phase 2 Batch 2A — TruthSourceRegistry（commit cf7ef5d）

### 設計背景

原則 12（持續進化）要求系統從交易行為自動學習。
需要一個形式化的認知級別體系，不能讓 AI 自我評估為 FACT。

### truth_source_registry.py（新建）

```python
class CognitiveLevel(Enum):
    HYPOTHESIS  = 1   # 系統推測，置信度最低
    INFERENCE   = 2   # 基於觀測的推論
    OBSERVATION = 3   # 直接觀測結果
    FACT        = 4   # 確定事實（AI 輸出永遠不能達到此級別）

class PatternClaim:
    pattern_text: str
    evidence_source: str
    observation_count: int
    confidence: float  # AI 輸出上限 0.85，永不為 FACT
    applies_to_regime: str
    applies_to_strategy: str
    ttl_seconds: int   # 依 evidence_source 類型設定

class TruthSourceRegistry:
    # threading.Lock 線程安全
    # TTL 過期自動清除
    # register_claim() / get_claim() / get_active_claims()
    # to_snapshot() / load_snapshot() 序列化（Phase 3A-4 完成）
```

### 原則 7 隔離設計

TruthSourceRegistry 屬於學習平面，完整與 Live 平面隔離：
- 不 import GovernanceHub / PaperTradingEngine / PipelineBridge
- 學習平面的數據改變不直接修改 live 配置（只更新 strategy_preference_weights）
- 重啟後 registry 清零（Phase 3A-4 前），確保不意外復原過期的推斷

### AnalystAgent 整合

```python
# AnalystAgent.set_truth_registry() + _register_pattern_claims()
def _register_pattern_claims(self, insight: AnalysisInsight) -> None:
    for pattern in insight.winning_patterns:
        self._truth_registry.register_claim(
            pattern_text=pattern,
            evidence_source="ai_analysis",
            observation_count=1,
            confidence=min(0.85, insight.confidence),  # AI 上限
            applies_to_regime=insight.regime,
            applies_to_strategy=self._extract_strategy_from_pattern(pattern),
        )
```

### StrategistAgent 整合

```python
# _apply_pattern_insight() — claim → strategy_preference_weights ±10%
def _apply_pattern_insight(self, claim: PatternClaim) -> None:
    strategy = claim.applies_to_strategy
    current_weight = self._strategy_preference_weights.get(strategy, 1.0)
    delta = +0.10 if "losing" not in claim.pattern_text else -0.10
    self._strategy_preference_weights[strategy] = max(0.1, min(3.0, current_weight + delta))
```

**46 個測試，A1-A8 驗收標準全通過**

---

## 十七、Phase 2 Batch 2B — BacktestEngine MVP（commit cf7ef5d）

### 設計原則

- **完全純函數**：同樣輸入永遠同樣輸出，無副作用
- `backtest_mode=False` → `ValueError`（防止生產配置誤用）
- <30 bars → 警告結果（不崩潰）
- Sharpe = 0.0 邊界保護（除零防護）

### BacktestConfig + BacktestResult

```python
@dataclass
class BacktestConfig:
    symbol: str
    timeframe: str
    strategy_name: str
    initial_capital: float = 10000.0
    fee_rate_taker: float = 0.00055
    fee_rate_maker: float = 0.0002
    slippage_bps: float = 5.0
    position_size_pct: float = 0.1
    stop_loss_pct: float = 0.03
    backtest_mode: bool = False  # 必須顯式設為 True

@dataclass
class BacktestResult:
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    final_capital: float
    ...
```

### _BacktestKlineAdapter

為確保原則 7 隔離，BacktestEngine 不直接使用 KlineManager（live 模組），
而是通過 `_BacktestKlineAdapter` 適配器（no-op register，只提供接口）。

```python
class _BacktestKlineAdapter:
    """KlineManager 的回測適配器 / Backtest adapter for KlineManager interface"""
    def register(self, *args, **kwargs) -> None:
        pass  # no-op in backtest mode
```

**57 個測試，B1-B9 驗收標準全通過**

---

## 十八、全天 Commit 清單

| commit | 時序 | 內容 |
|--------|------|------|
| ec0e794 | 早 | P0 CRITICAL×4 + Wave 0-2 第一批（16 files）|
| c113ab2 | 早 | paper_engine + pipeline_bridge P0/P1 修復（10 files）|
| c6a8845 | 上午 | Wave 3a P0-NEW-1/2/3 |
| 2eda4ec | 上午 | Wave 3b P1-NEW-1~7 |
| bf75254 | 上午 | Wave 3c P1-4/P1-10/P1-17 |
| 3ccd982 | 上午 | P1-16 H0 Gate Day 1（h0_gate.py + 37 tests）|
| 5d53619 | 下午 | P1-16 H0 Gate Day 2（H0HealthWorker + 40 tests）|
| 2ed20f0 | 下午 | P1-16 H0 Gate Day 3（接入 pipeline/routes/risk，18 tests）|
| 03a5b29 | 下午 | P1-16 merge to main |
| a2f4c70 | 下午 | Wave 4 Sprint 4a P2-NEW-1/2/6 |
| 6c80bc9 | 下午 | Wave 4 Sprint 4b P2-NEW-3/4 + P3-TECH-1/2/3 |
| 448f1e7 | 下午 | Wave 4 Sprint 4c P2-NEW-7/8 |
| 9cc134a | 下午 | Wave 4 Sprint 4d FA-2/3/4 |
| 87c2651 | 下午 | Wave 4 Sprint 4e P2-NEW-9 + P2-NEW-5 |
| 8223eb9 | 下午 | Wave 5a Position Sizing 重構 |
| （user） | 下午 | Wave 5b Paper/Demo 同步修復 |
| d57ed05 | 傍晚 | Wave 5 Sprint 0：G-05 + G-01 |
| ccdff73 | 傍晚 | Wave 5 Sprint 5a：H0 blocking + H1/H2/H3 |
| 9478c00 | 傍晚 | Wave 5 Sprint 5b：H4/H5 + ScoutWorker |
| aafb18b | 晚 | Wave 6 Sprint 0：TD-1 pipeline_bridge acquire_lease |
| 8f123a7 | 晚 | Wave 6 Sprint 1a+1b：FA-7 + Cooldown + TD-3/TD-4 |
| 43dd2f5 | 晚 | Wave 6 Sprint 2：P2-6/7/8 + TD-2 + FA-8 |
| 973c595 | 深夜 | Cleanup Sprint：CS-1~4 |
| cf7ef5d | 深夜 | Phase 2 Batch 2A + 2B（TruthSourceRegistry + BacktestEngine）|

---

## 十九、重要設計決策記錄

### 為什麼 H0 Gate 必須在 <1ms 完成？

DOC-02 規定 H0 為「確定性本地判斷」，不允許任何 I/O 或 AI 調用。
交易系統的 `on_tick()` 每秒可能被調用數百次，若 H0 有任何 I/O 延遲，
會直接阻塞整個 tick 處理路徑。
解決方案：H0 只讀取記憶體中的預計算值（health worker 背景更新）。

### 為什麼 TruthSourceRegistry AI 上限是 0.85？

原則 10（認知誠實）：AI 輸出是推斷，永遠不是 FACT。
0.85 是 INFERENCE 級別的最高置信度，留出空間表達「高信心但仍有不確定性」。
FACT 級別（1.0）保留給可直接從市場數據驗證的客觀事實。

### 為什麼 BacktestEngine 需要 `_BacktestKlineAdapter`？

若 BacktestEngine 直接使用 KlineManager，測試時需要模擬整個 KlineManager 依賴樹。
更重要的是：原則 7 要求學習平面與 live 平面隔離。
通過 Adapter 設計，BacktestEngine 可在無 live 依賴的情況下完整運行。

### 為什麼 Decision Lease 出現在兩個地方（G-05 + TD-1）？

ExecutorAgent 和 PipelineBridge 是兩條平行的下單路徑：
- ExecutorAgent：Agent 主動觸發的下單
- PipelineBridge：Intent 佇列處理的下單

兩條路徑都需要 acquire_lease()。G-05 修復了 ExecutorAgent，TD-1 修復了 PipelineBridge。
這是架構設計中「兩個入口」模式的代價——每個入口都必須獨立實施所有安全控制。

---

## 二十、3/31 結束時系統狀態

```
測試：2700 passed（+503 vs 3/31 開始）
路由：150+ 條
H 鏈：H0-H5 全部接通（H0 <1ms 確定性門控，H1-H5 AI 治理）
原則 3：ExecutorAgent + PipelineBridge 雙路徑均已有 acquire_lease()
原則 12：止損路徑 + Intent 路徑均觸發學習觀察
學習管線：TruthSourceRegistry + BacktestEngine 就緒（運行時接通待 Batch 2C）
安全評級：0 CRITICAL / 0 HIGH / 2 MEDIUM / 3 LOW
```

**下一步（4/1 開始）**：Phase 2 Batch 2C — 接通 _register_pattern_claims + BacktestEngine API + 決策權重
