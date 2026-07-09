# Sprint 5b 派發計劃（PM · 2026-03-31）

**前置條件**：Sprint 5a E2+E4 通過（commit ccdff73，2576 passed → 5a 完成後當前基線 2594）
**當前測試基準**：2594 collected（2026-03-31 pm pytest --co -q 確認）
**Sprint 5b 目標**：≥ 2600 tests passed

---

## 一、依賴關係分析

```
Sprint 5a 完成（必須）
    │
    ├─ 5b-1：H4 validate_output（strategist_agent.py · _ai_evaluate 後插入）
    │         前置：無（僅需 5a 完成，_ai_evaluate 已存在）
    │
    ├─ 5b-2/6：H5 CostLogger + roi_basis（layer2_cost_tracker.py）
    │         前置：無（layer2_cost_tracker 獨立模塊）
    │         注意：strategist_agent.py 第 480-486 行已有 record_call getattr 探針
    │               新增 record_ollama_call 後，該探針無需改動（兼容設計）
    │
    ├─ 5b-3：apply_ai_consultation stub 替換（main_legacy.py:3881）
    │         前置：無（stub 替換不依賴其他 5b 任務）
    │         注意：_handle_intel() 是同步方法（MessageBus 回調）
    │               apply_ai_consultation 本身也是同步函數（非 async）
    │               替換方案：移除 stub + 標記廢棄 + 指向 /phase2/strategist/intel-log
    │
    ├─ 5b-4：ScoutWorker 後台線程（新建 app/scout_worker.py）
    │         前置：5a-1（Scout→bus.send 鏈路已確認，目前已知代碼存在）
    │         技術注意：
    │           - MarketScanner.scan() 已在 phase2_strategy_routes MARKET_SCANNER 中
    │           - ScoutWorker 的職責是定期調用 MARKET_SCANNER.scan() 並通過 ScoutAgent
    │             將高分機會轉化為 IntelObject（produce_intel() → bus.send → Strategist）
    │           - 進程退出：_stop_event = threading.Event()，外部調用 stop()
    │
    └─ 5b-5：原則 14 集成測試（新建 tests/test_h_chain_integration.py）
              前置：Sprint 5a 完成（需要 H1-H3 鏈路存在）
              執行者：E4 直接執行（不需要 E1 輔助）
```

**關鍵發現（代碼審計）**：
- `_ai_evaluate()` 位於 strategist_agent.py:668，**已有** JSON 解析和 parse error 處理
- H4 validate_output 是在 json.loads 成功後、構造 EdgeEvaluation 前插入顯式驗證步驟
- `layer2_cost_tracker.py` **無** `record_ollama_call` / `get_cost_edge_ratio` / `roi_basis`，需全部新增
- `apply_ai_consultation` stub 在 main_legacy.py:3881，調用點在 :5082
- `MarketScanner.scan()` 存在且功能完整，ScoutWorker 是觸發器包裝層

---

## 二、並行分組（三條流）

```
Sprint 5b 工作流（完全並行啟動）

E1-Gamma 流（估計 4h）：
  串行：5b-1（1.5h）→ 5b-2/6（2.5h）
  原因：5b-1 改動 strategist_agent.py，5b-2/6 改動 layer2_cost_tracker.py，互不干擾
        可並行，但 E1-Gamma 是單人流，串行執行

E1-Delta 流（估計 5h）：
  串行：5b-3（2h）→ 5b-4（3h）
  原因：5b-3 改 main_legacy.py，5b-4 新建 scout_worker.py，互不干擾
        5b-4 需要確認 5a-1 Scout 鏈路，建議 5b-3 先做

E4 獨立流（估計 1.5h）：
  5b-5 完全並行執行（Mock 測試，不依賴 E1 代碼完成）

         [E1-Gamma]           [E1-Delta]           [E4]
         5b-1 (1.5h)         5b-3 (2h)            5b-5 (1.5h)
              ↓                    ↓
         5b-2/6 (2.5h)       5b-4 (3h)
              ↓                    ↓
              ──────────── E2 審查 (1.5h) ────────────
                                  ↓
                         E4 回歸 (2h，目標 ≥ 2600)
```

---

## 三、每個任務的具體派發指令

---

### 【E1-Gamma · Task 1】5b-1：H4 AI 輸出驗證（validate_output）

**文件**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`

**插入位置**：`_ai_evaluate()` 方法（line 668），在 `json.loads(text)` 成功後、`EdgeEvaluation(...)` 構造前

**具體實現**：

```python
# H4 AI Output Validation / H4 AI 輸出驗證
# 原則 6：validate_output 失敗必須 fallback heuristic，不可 allow-all
def _validate_ai_output(self, result: dict, intel: IntelObject) -> EdgeEvaluation | None:
    """
    H4 output validation gate — called immediately after AI JSON parse.
    H4 輸出驗證閘門 — 在 AI JSON 解析成功後立即調用。

    Returns None if valid (caller proceeds to build EdgeEvaluation).
    Returns fallback EdgeEvaluation if invalid (CC 原則 6 fail-closed).
    """
    # Rule 1: result must be non-empty dict
    # 規則 1：結果必須為非空字典
    if not result or not isinstance(result, dict):
        logger.warning("H4 validate_output: empty or non-dict result, fallback heuristic")
        return _heuristic_evaluate(intel, self.config)

    # Rule 2: 'has_edge' field must exist and be bool-coercible
    # 規則 2：'has_edge' 字段必須存在且可轉為布林值
    if "has_edge" not in result:
        logger.warning("H4 validate_output: missing 'has_edge' field, fallback heuristic")
        return _heuristic_evaluate(intel, self.config)

    # Rule 3: confidence must be float in [0.0, 1.0]
    # 規則 3：confidence 必須為 [0,1] 範圍內的浮點數
    try:
        confidence = float(result.get("confidence", -1))
    except (TypeError, ValueError):
        confidence = -1.0
    if not (0.0 <= confidence <= 1.0):
        logger.warning(
            "H4 validate_output: confidence=%.2f out of [0,1], fallback heuristic", confidence
        )
        return _heuristic_evaluate(intel, self.config)

    return None  # validation passed / 驗證通過
```

在 `_ai_evaluate` 的 `result = json.loads(text)` 之後插入：
```python
# H4 output validation / H4 輸出驗證
_h4_fallback = self._validate_ai_output(result, intel)
if _h4_fallback is not None:
    with self._lock:
        self._stats["heuristic_evaluations"] += 1
    return _h4_fallback
```

**CC 強制要求**：
- 驗證失敗必須返回 `_heuristic_evaluate(intel, self.config)`，不得 return `EdgeEvaluation(has_edge=True, ...)`
- 原則 6：失敗默認收縮

**測試要求**（E1-Gamma 必須新增，E4 驗收）：
在 `tests/test_strategist_agent.py` 新增至少 4 個測試：
1. `test_h4_validate_empty_result` → 空 dict → heuristic fallback
2. `test_h4_validate_missing_has_edge` → 缺少 has_edge → heuristic fallback
3. `test_h4_validate_confidence_out_of_range` → confidence=1.5 → heuristic fallback
4. `test_h4_validate_passes_valid_output` → 正常 JSON → EdgeEvaluation 正常構造

**估計**：1.5h（含測試）

---

### 【E1-Gamma · Task 2】5b-2/6：H5 CostLogger + ROI disclaimer

**文件**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py`

**新增三個方法**（加在 `Layer2CostTracker` 類末尾）：

```python
# H5 Ollama Cost Tracking / H5 Ollama 成本追蹤
# 原則 13：AI 資源成本感知 — 雖 Ollama 免費，仍記錄調用次數與延遲以計算 cost_edge_ratio
def record_ollama_call(
    self, model: str, duration_ms: float, prompt_tokens: int
) -> None:
    """
    Record a local Ollama call for tracking purposes.
    記錄一次本地 Ollama 調用（免費模型，計次+延遲追蹤）。

    Does not charge USD cost since Ollama is free (原則 14: 零外部成本可運行).
    不計 USD 費用，因為 Ollama 免費（原則 14）。
    Cost tracking failure must NEVER block trading — wrapped in try/except.
    成本追蹤失敗絕不阻塞交易。
    """
    try:
        raw = self._read_raw()
        today_key = self._today_key()
        if "ollama_calls" not in raw:
            raw["ollama_calls"] = {}
        day_calls = raw["ollama_calls"].setdefault(today_key, [])
        day_calls.append({
            "model": model,
            "duration_ms": round(duration_ms, 1),
            "prompt_tokens": prompt_tokens,
            "ts_ms": int(time.time() * 1000),
        })
        # Keep only last 1000 per day to prevent unbounded growth
        # 每天最多保留 1000 條記錄，防止無限增長
        if len(day_calls) > 1000:
            raw["ollama_calls"][today_key] = day_calls[-1000:]
        self._write_raw(raw)
    except Exception:
        pass  # cost tracking must never block / 成本追蹤絕不阻塞

def get_ollama_summary(self) -> dict[str, Any]:
    """
    Return Ollama call summary with ROI disclaimer.
    返回 Ollama 調用摘要，含 ROI 免責聲明。

    CC 原則 10：所有 AI ROI 相關 API 必須標記 roi_basis。
    所有 paper/simulation 環境的 ROI 標記為 'paper_simulation_only'。
    """
    try:
        raw = self._read_raw()
        today_key = self._today_key()
        today_calls = raw.get("ollama_calls", {}).get(today_key, [])
        total_calls = sum(len(v) for v in raw.get("ollama_calls", {}).values())
        avg_duration_ms = (
            sum(c["duration_ms"] for c in today_calls) / len(today_calls)
            if today_calls else 0.0
        )
        return {
            "today_call_count": len(today_calls),
            "total_call_count": total_calls,
            "avg_duration_ms_today": round(avg_duration_ms, 1),
            "roi_basis": "paper_simulation_only",  # CC 原則 10
        }
    except Exception:
        return {"today_call_count": 0, "total_call_count": 0, "roi_basis": "paper_simulation_only"}

def get_cost_edge_ratio(self) -> dict[str, Any]:
    """
    Return cost-edge ratio placeholder with ROI disclaimer.
    返回 cost-edge ratio 佔位，含 ROI 免責聲明。

    原則 13：cost_edge_ratio ≥ 0.8 → 建議關倉。
    當前為 paper_simulation_only，數值僅供參考。
    CC 原則 10：roi_basis 必須標記。
    """
    adaptive = self.get_adaptive_state()
    roi_7d = adaptive.roi_7d
    cost_edge_ratio = None
    if roi_7d is not None:
        # Simple ratio: roi / (ai_spend if ai_spend > 0 else 1)
        cost_edge_ratio = round(roi_7d / max(adaptive.ai_spend_7d_usd, 0.001), 4)
    return {
        "cost_edge_ratio": cost_edge_ratio,
        "roi_7d_usd": roi_7d,
        "ai_spend_7d_usd": adaptive.ai_spend_7d_usd,
        "roi_basis": "paper_simulation_only",  # CC 原則 10
        "note": (
            "ROI is based on paper trading simulation only. "
            "Live PnL not available. / "
            "ROI 基於紙面交易模擬，不代表真實盈虧。"
        ),
    }
```

**CC 強制要求**：
- 所有三個方法都必須包含 `roi_basis: "paper_simulation_only"` 鍵（原則 10）
- `record_ollama_call` 必須有 try/except 包裹，失敗不阻塞（原則 14）

**測試要求**（E1-Gamma 新增 4 個測試）：
1. `test_record_ollama_call_happy_path` → 調用後 get_ollama_summary().today_call_count == 1
2. `test_record_ollama_call_does_not_raise_on_error` → mock _write_raw 拋出異常，方法不傳播
3. `test_get_ollama_summary_roi_basis` → roi_basis == "paper_simulation_only"
4. `test_get_cost_edge_ratio_roi_basis` → roi_basis == "paper_simulation_only"

**估計**：2.5h（含測試）

---

### 【E1-Delta · Task 1】5b-3：apply_ai_consultation stub 替換

**文件**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py`

**當前位置**：line 3881 `def apply_ai_consultation(...)` — line 5082 調用點

**決策**（PA 指導）：
`apply_ai_consultation` 是 Learning Cockpit 的 Review Queue AI 諮詢功能，與 H 鏈（Strategist intel 路徑）不同層次。
直接接入 `strategist_agent._handle_intel()` 在語義上不正確。
**正確做法**：標記廢棄 + 更新 stub 說明 + 在回應中指向現有的 `/phase2/strategist/intel-log`

```python
def apply_ai_consultation(
    envelope: RequestEnvelope, actor: AuthenticatedActor, packet_id: str
) -> tuple[dict[str, Any], str]:
    """
    [DEPRECATED — 功能已由 H 鏈接管 / Function superseded by H-chain]

    AI 諮詢功能已整合至 H1-H5 治理鏈（StrategistAgent）。
    直接接入路徑：/phase2/strategist/intel-log（查看已評估情報）

    本函數保留兼容性，不再產出新 stub 回應。
    This function is retained for compatibility; no longer produces stub responses.
    新代碼請直接讀取 StrategistAgent 的 intel 評估日誌。
    New code should read StrategistAgent evaluation log directly.
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)

    queue = snapshot.get("learning_state", {}).get("records", {}).get("review_queue", [])
    target_pkt = None
    for pkt in queue:
        if pkt.get("packet_id") == packet_id:
            target_pkt = pkt
            break
    if target_pkt is None:
        raise HTTPException(status_code=404, detail={"reason_codes": ["review_packet_not_found"]})

    return {
        "audit_ref": None,
        "data": {
            "packet_id": packet_id,
            "consultation_status": "superseded_by_h_chain",
            "h_chain_path": "/phase2/strategist/intel-log",
            "message": (
                "AI 諮詢功能已由 H1-H5 治理鏈（StrategistAgent）接管。"
                "請使用 /phase2/strategist/intel-log 查看最新情報評估結果。"
                "/ AI consultation is now handled by H1-H5 chain (StrategistAgent). "
                "Use /phase2/strategist/intel-log for latest evaluations."
            ),
            "deprecated": True,
        },
        "snapshot": snapshot,
    }, "success"
```

**CC 強制要求**：
- 函數不得刪除（保留兼容性，調用點 :5082 仍需正常工作）
- 改動後必須調用點 :5082 的測試仍通過

**測試要求**（E1-Delta 確認現有測試仍通過）：
搜索 `tests/` 中所有包含 `apply_ai_consultation` 的測試，確認修改後不破壞

**估計**：2h（含驗證）

---

### 【E1-Delta · Task 2】5b-4：ScoutWorker 後台定時掃描線程

**新建文件**：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_worker.py`

**設計**：
```python
"""
MODULE_NOTE
===========
EN: ScoutWorker — Background daemon thread that periodically triggers MarketScanner.scan()
    and converts high-score opportunities into IntelObjects for the Strategist pipeline.
    Principle 11: Agent operates autonomously within P0/P1 boundaries.
    Principle 14: Zero external cost — uses local scanner only.

ZH: ScoutWorker — 後台 daemon 線程，定期觸發 MarketScanner.scan()
    並將高分機會轉為 IntelObject 注入 Strategist 管線。
    原則 11：Agent 在 P0/P1 邊界內完全自主運行。
    原則 14：零外部成本 — 僅使用本地掃描器。
"""
```

**核心結構**：
```python
class ScoutWorker:
    def __init__(
        self,
        market_scanner,           # MarketScanner instance
        scout_agent,              # ScoutAgent instance
        interval_seconds: int = 1800,   # 30min default
        min_score: float = 0.6,         # only produce intel for high-score opps
    ):
        self._scanner = market_scanner
        self._scout = scout_agent
        self._interval = interval_seconds
        self._min_score = min_score
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._stats = {"runs": 0, "intel_produced": 0, "errors": 0}
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start background daemon thread / 啟動後台 daemon 線程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,    # daemon=True: 進程退出時自動停止，無需顯式 join
            name="scout-worker",
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal worker to stop / 通知 Worker 停止"""
        self._stop_event.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_stats(self) -> dict:
        with self._lock:
            return dict(self._stats)

    def _loop(self) -> None:
        """Main loop — run scan every interval / 主循環 — 每隔 interval 執行一次掃描"""
        while not self._stop_event.wait(self._interval):
            self._run_once()

    def _run_once(self) -> None:
        """Execute one scan cycle / 執行一次掃描週期"""
        try:
            if self._scanner is None or self._scout is None:
                return
            opps = self._scanner.scan()
            with self._lock:
                self._stats["runs"] += 1
            for opp in opps:
                if opp.score >= self._min_score:
                    self._scout.produce_intel(
                        source="scout_worker_scan",
                        content=f"MarketScanner opportunity: {opp.symbol} score={opp.score:.2f}",
                        symbols=[opp.symbol],
                        relevance_score=min(opp.score, 0.95),
                        metadata={"score": opp.score, "source": "periodic_scan"},
                    )
                    with self._lock:
                        self._stats["intel_produced"] += 1
        except Exception:
            logger.exception("ScoutWorker scan error / ScoutWorker 掃描異常")
            with self._lock:
                self._stats["errors"] += 1
```

**進程退出機制**：
- `daemon=True` 保證進程退出時線程自動終止（最重要）
- `_stop_event.wait(interval)` 替代 `sleep`，支持快速響應 `stop()` 調用
- 測試可調用 `stop()` 後等待線程結束

**接入點**（`phase2_strategy_routes.py` 啟動時注入）：
在 `MARKET_SCANNER.start()` 之後：
```python
from .scout_worker import ScoutWorker
SCOUT_WORKER = ScoutWorker(MARKET_SCANNER, SCOUT_AGENT, interval_seconds=1800)
SCOUT_WORKER.start()
```

**測試要求**（E1-Delta 新增至少 5 個測試，新建 `tests/test_scout_worker.py`）：
1. `test_scout_worker_start_stop` → start() → is_running()==True → stop() → thread exits
2. `test_scout_worker_produces_intel_for_high_score` → mock scan() → high score opp → produce_intel called
3. `test_scout_worker_skips_low_score_opps` → score < min_score → produce_intel NOT called
4. `test_scout_worker_handles_scanner_error` → scan() raises → no exception propagated → errors stat incremented
5. `test_scout_worker_daemon_thread` → thread.daemon == True

**E2 重點審查**：ScoutWorker 線程安全（_lock 覆蓋 _stats 所有讀寫）

**估計**：3h（含測試 + 接入）

---

### 【E4 · Task 1】5b-5：原則 14 集成測試

**新建文件**：`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h_chain_integration.py`

**設計思路**：
Mock `OllamaClient.is_available()=False` → 驗證 Strategist 使用 heuristic 路徑 → 確認 TradeIntent（或 no intent）產出，系統不崩潰（AC-2）

**測試清單**（目標 ≥ 10 個，保守估計 6 個）**：

```python
# 測試 1：Ollama 不可用 → 系統退化到 L0（heuristic），不崩潰
def test_principle14_ollama_unavailable_system_degrades_gracefully():
    """Principle 14: system must function without any external AI calls / 原則 14：無外部 AI 也能運行"""
    with patch.object(OllamaClient, "is_available", return_value=False):
        agent = StrategistAgent(...)
        msg = _make_intel_message(relevance=0.8)
        agent._handle_intel(msg)  # must not raise
        stats = agent.get_stats()
        assert stats["heuristic_evaluations"] >= 0  # either evaluated or filtered

# 測試 2：Ollama 不可用 → heuristic_evaluations 計數器增加
def test_principle14_ollama_down_uses_heuristic_path():
    with patch.object(OllamaClient, "is_available", return_value=False):
        agent = StrategistAgent(...)
        msg = _make_intel_message(relevance=0.9, sentiment="positive")
        agent._handle_intel(msg)
        assert agent.get_stats()["heuristic_evaluations"] > 0

# 測試 3：Ollama 崩潰（judge_edge raises） → fallback heuristic，不傳播異常
def test_principle14_ollama_exception_falls_back_to_heuristic():
    with patch.object(OllamaClient, "is_available", return_value=True):
        with patch.object(OllamaClient, "judge_edge", side_effect=ConnectionError("timeout")):
            agent = StrategistAgent(...)
            msg = _make_intel_message(relevance=0.9)
            agent._handle_intel(msg)  # must not raise
            assert agent.get_stats()["errors"] > 0

# 測試 4：Ollama 不可用 → 不影響 H0 Gate（鏈路不中斷）
def test_principle14_h0_gate_unaffected_by_ollama_down():
    # 只有 H1-H5 降級，H0 本地確定性門控不受影響
    from app.h0_gate import H0Gate
    gate = H0Gate()
    verdict = gate.evaluate(...)
    assert verdict is not None  # H0 always returns verdict regardless of Ollama

# 測試 5：FA AC-2 — Ollama 不可用時，交易鏈路完整性（heuristic intent 仍可產出）
def test_fa_ac2_trading_chain_intact_without_ollama():
    """FA AC-2: Trade chain must not break when AI unavailable"""
    with patch.object(OllamaClient, "is_available", return_value=False):
        agent = StrategistAgent(config=StrategistConfig(shadow=False, min_confidence=0.3))
        # inject message bus to capture TRADE_INTENT
        bus = MessageBus()
        agent.bus = bus
        captured = []
        bus.subscribe(AgentRole.GUARDIAN, lambda m: captured.append(m))
        msg = _make_intel_message(relevance=0.9, sentiment="positive")
        agent._handle_intel(msg)
        # Either intent produced or no edge — but no crash
        # Chain is "not broken" = no exception + system continues

# 測試 6：Ollama 恢復後系統正常切換回 AI 路徑
def test_principle14_ollama_recovery_resumes_ai_path():
    agent = StrategistAgent(...)
    mock_ollama = MagicMock()
    mock_ollama.is_available.side_effect = [False, True]  # first down, then up
    mock_ollama.judge_edge.return_value = MagicMock(success=True, text='{"has_edge":true,"confidence":0.7,"reason":"test"}')
    agent._ollama = mock_ollama
    # First call → heuristic
    agent._handle_intel(_make_intel_message(relevance=0.9))
    assert agent.get_stats()["heuristic_evaluations"] >= 1
    # Second call → AI (if conditions met)
    agent._handle_intel(_make_intel_message(relevance=0.9))
    # ai_evaluations might be 0 if H1 skips, but no error
```

**CC 確認要求**：
- 每個測試必須驗證「系統不拋出異常」（AC-2）
- 必須有至少一個測試驗證 heuristic 路徑被使用（不是 allow-all）

**估計**：1.5h

---

## 四、E2+E4 驗收節點

```
E2 進入條件：E1-Gamma（5b-1+5b-2/6）+ E1-Delta（5b-3+5b-4）均完成
E2 重點審查清單：
  1. H4 validate_output：失敗路徑是否真的走 heuristic（不是 allow-all）
  2. roi_basis 標記：所有三個新方法均有 "paper_simulation_only"
  3. ScoutWorker 線程安全：_lock 覆蓋所有 _stats 讀寫
  4. ScoutWorker daemon=True 確認（防進程無法退出）
  5. apply_ai_consultation：調用點 :5082 測試不破壞
  6. 雙語注釋完整性（MODULE_NOTE + 所有新函數 docstring）

E4 驗收條件：
  - pytest --co -q ≥ 2606 collected（新增：4+4+5+6 = 19 測試）
  - pytest -q ≥ 2600 passed
  - 無新 FAILED（17 pre-existing skip 允許保留）
  - AC-1: H4 validate_output 覆蓋非空/action/confidence 三種失敗場景
  - AC-2: 5b-5 Ollama 崩潰後交易鏈路不中斷（至少一個測試驗證）
  - AC-7: roi_basis 標記出現在所有相關 API 回應
  - AC-8: ScoutWorker daemon 線程進程退出正確停止
```

---

## 五、CC 強制執行確認

| CC 條件 | 覆蓋任務 | 驗收方式 |
|--------|---------|---------|
| 原則 10：roi_basis 標記 | 5b-2/6 三個方法均有 `roi_basis: "paper_simulation_only"` | E4 AC-7 測試 |
| 原則 14：Ollama 崩潰集成測試 | 5b-5 test_h_chain_integration.py ≥ 6 測試 | E4 回歸通過 |
| 原則 6：H4 失敗→heuristic（不可 allow-all） | 5b-1 _validate_ai_output 返回 heuristic fallback | E4 AC-1 測試 |

**額外確認**：
- 原則 5（生存>利潤）：ScoutWorker 錯誤不影響主交易鏈路（5b-4 try/except）
- 原則 8（交易可解釋）：所有新函數有完整 docstring 和中英注釋

---

## 六、工時總計

| 任務 | 執行者 | 估計 |
|------|-------|------|
| 5b-1 H4 validate_output | E1-Gamma | 1.5h |
| 5b-2/6 CostLogger + roi_basis | E1-Gamma | 2.5h |
| 5b-3 apply_ai_consultation 替換 | E1-Delta | 2h |
| 5b-4 ScoutWorker | E1-Delta | 3h |
| 5b-5 原則 14 集成測試 | E4 直接 | 1.5h |
| E2 審查 | E2 | 1.5h |
| E4 回歸 | E4 | 2h |
| **合計** | | **~14h** |

---

## 七、啟動指令（主 Claude 轉發）

### E1-Gamma 啟動指令

```
你是 E1-Gamma（Backend Developer）。按以下順序執行：

【Step 1 - 讀取記憶】docs/CCAgentWorkSpace/E1/memory.md

【Step 2 - 任務 5b-1：H4 validate_output】
文件：program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py
- 在 StrategistAgent 類中新增 _validate_ai_output() 方法（見 sprint5b_dispatch.md §三 Task1 規範）
- 在 _ai_evaluate() 的 json.loads 成功後插入 H4 validation 調用
- 在 tests/test_strategist_agent.py 新增 4 個測試（empty/missing_has_edge/confidence_out_of_range/valid）
- CC 必查：失敗必須 return _heuristic_evaluate()，不得 allow-all

【Step 3 - 任務 5b-2/6：H5 CostLogger】
文件：program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_cost_tracker.py
- 新增 record_ollama_call(model, duration_ms, prompt_tokens)
- 新增 get_ollama_summary() → 含 roi_basis: "paper_simulation_only"
- 新增 get_cost_edge_ratio() → 含 roi_basis: "paper_simulation_only"
- 在 tests/ 目錄對應文件新增 4 個測試
- CC 必查：所有三個方法均有 roi_basis 標記

【完成序列】
Step A：更新 docs/CCAgentWorkSpace/E1/memory.md
Step B：存檔至 docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--5b_gamma.md
```

### E1-Delta 啟動指令

```
你是 E1-Delta（Backend Developer）。按以下順序執行：

【Step 1 - 讀取記憶】docs/CCAgentWorkSpace/E1/memory.md

【Step 2 - 任務 5b-3：apply_ai_consultation 替換】
文件：program_code/exchange_connectors/bybit_connector/control_api_v1/app/main_legacy.py:3881
- 將 stub 替換為廢棄說明 + 指向 /phase2/strategist/intel-log（見 sprint5b_dispatch.md §三 Task1 規範）
- 確認調用點 :5082 的測試仍通過
- 不得刪除函數（保留兼容性）

【Step 3 - 任務 5b-4：ScoutWorker 後台線程】
新建：program_code/exchange_connectors/bybit_connector/control_api_v1/app/scout_worker.py
- 實現 ScoutWorker 類（見 sprint5b_dispatch.md §三 Task2 規範）
- daemon=True + stop_event + _lock 線程安全
- 接入：phase2_strategy_routes.py 啟動時注入 SCOUT_WORKER
新建：tests/test_scout_worker.py（至少 5 個測試）
- E2 重點：daemon=True / _lock 覆蓋所有 _stats 讀寫

【完成序列】
Step A：更新 docs/CCAgentWorkSpace/E1/memory.md
Step B：存檔至 docs/CCAgentWorkSpace/E1/workspace/reports/2026-03-31--5b_delta.md
```

### E4 啟動指令（5b-5 原則 14 集成測試）

```
你是 E4（Test Engineer）。按以下順序執行：

【Step 1 - 讀取記憶】docs/CCAgentWorkSpace/E4/memory.md

【Step 2 - 任務 5b-5】
新建：program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h_chain_integration.py
實現至少 6 個測試（見 sprint5b_dispatch.md §三 E4 Task1 規範）：
  - Ollama 不可用 → 系統不崩潰（FA AC-2）
  - Ollama 不可用 → heuristic 路徑被使用（不是 allow-all）
  - Ollama judge_edge 拋出異常 → fallback heuristic
  - Ollama 不可用 → H0 Gate 不受影響
  - Ollama 不可用 → 交易鏈路完整性（FA AC-2）
  - Ollama 恢復 → 系統恢復 AI 路徑
CC 必查：原則 6（失敗→heuristic）+ 原則 14（零外部成本可運行）

【Step 3 - 確認測試基準】
運行 pytest --co -q 確認 collected ≥ 2606
（2594 + 5b-5 的 6 個基準，加上 5b-1/5b-2/5b-4 的 13 個 = 2613+）

【完成序列】
Step A：更新 docs/CCAgentWorkSpace/E4/memory.md
Step B：存檔至 docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--5b_e4.md
```

---

## 八、E2 啟動指令（E1-Gamma + E1-Delta 均完成後）

```
你是 E2（Code Reviewer）。審查 Sprint 5b 所有改動。

重點審查清單：
1. strategist_agent.py _validate_ai_output：失敗路徑必須是 heuristic，不是 allow-all
2. layer2_cost_tracker.py 三個新方法：roi_basis 標記完整
3. scout_worker.py：daemon=True / _stop_event.wait() / _lock 線程安全
4. main_legacy.py apply_ai_consultation：不刪除函數，調用點 :5082 兼容
5. 雙語注釋：MODULE_NOTE + 所有新函數 docstring 中英完整
6. 無 except:pass（cost tracker 的 pass 有文字說明，可接受）
```

---

*PM 備注：Sprint 5b 完成後更新 TODO.md 將 5b-1 至 5b-5 標記為 [x]，測試基準從 2594 更新。*
