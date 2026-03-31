# CC 合規審查報告：Wave 5 B 方案（多 Agent 正式落地 + H1-H5 接通）

**審查員**：CC（Compliance Checker）
**日期**：2026-03-31
**審查基礎**：PM 計劃（wave5_plan_b_multiagent.md）+ PA 技術設計（wave5_tech_design.md）+ FA Gap 分析（wave5_gap_analysis.md）
**16 條根原則來源**：DOC-01 §5.1–§5.16 + CLAUDE.md §二

---

## 整體評級

```
整體評級：條件通過（有兩個強制前置條件，不修復不得啟動 Sprint 5a）
```

---

## 16 條根原則逐條審查

### 原則 1：單一寫入口

**狀態：⚠️ 需要確認**

計劃中 Strategist shadow=False 後，TradeIntent 產生路徑為：
```
StrategistAgent._handle_intel() → TradeIntent
  → Guardian.review_intent()
    → acquire_lease()
      → PipelineBridge._process_pending_intents()
        → submit_order()
```

PA 技術設計描述此路徑最終仍通過 `submit_order()` 執行，即唯一寫入口設計意圖正確。

**但 FA-G-05 發現**：ExecutorAgent 存在另一條路徑直接調用 `submit_order()`，且**未通過** `acquire_lease()`。如果 ExecutorAgent 的 APPROVED_INTENT 處理路徑在 Wave 5 後可被觸發，則出現**兩條執行路徑**：一條有 Decision Lease，一條沒有。

**結論**：在 G-05 修復前，Strategist shadow=False 會引入原則 1 違反風險。

---

### 原則 2：讀寫分離

**狀態：✅ 計劃合規**

Wave 5 的修改集中在 StrategistAgent / H1-H5 推理鏈，不涉及 GUI 讀寫邊界的更改。OpenClaw sidecar 僅作 audit_callback（write-once 日誌），不影響讀寫隔離。

---

### 原則 3：AI 輸出 ≠ 即時命令

**狀態：❌ 硬違反（FA-G-05，必須在 Sprint 5a 前修復）**

**違反位置**：`executor_agent.py` 第 281 行
```python
result = self._paper_engine.submit_order(
    symbol=symbol, side=side, order_type=order_type, qty=qty, ...
)
```

ExecutorAgent 在接收到 APPROVED_INTENT 後，**直接調用 submit_order()**，中間沒有調用 `governance_hub.acquire_lease()`。即使 Intent 已被 Guardian 批准（APPROVED_INTENT 標記），原則 3 要求的完整鏈為：

```
AI 輸出 → Decision Lease（帶時效、可撤銷）→ 本地複核 → 執行
```

Guardian.review_intent() 是批准邏輯（是否值得執行），Decision Lease 是授權時效控制（何時可以執行）。兩者語義不同，不可互相替代。

**CC 立場**：這是原則 3 的**硬違反**，不是部分合規問題。計劃中提到 Guardian 門控已 fail-closed，但 Guardian 批准 ≠ Decision Lease。兩個機制必須串聯。

**必須修復**：Sprint 5a 前，ExecutorAgent 的執行路徑中必須插入 `acquire_lease()` → 若 lease 取得失敗則 REJECT（fail-closed）。

---

### 原則 4：策略不能繞過風控

**狀態：✅ 計劃設計合規**

PA 技術設計明確規定：TradeIntent → Guardian.review_intent() → acquire_lease() → 執行。Guardian 已 fail-closed（pipeline_bridge.py 行 659-662 確認）。Wave 5 不改變此路徑。

**但依賴 G-05 修復**：如果 ExecutorAgent 直接路徑存在，策略通過 ExecutorAgent 可繞過 Guardian → 違反原則 4。

---

### 原則 5：生存 > 利潤

**狀態：✅ 計劃合規**

H1 ThoughtGate 設計為 blocking gate，在有 AI 調用的路徑上增加評估。H0 Gate 改為 blocking 後更強化此原則。stop-loss 邏輯不在 Wave 5 修改範圍。

---

### 原則 6：失敗默認收縮

**狀態：⚠️ 需要明確規範**

**H1 Ollama 調用超時場景**：PA 設計要求 L1 Ollama 在 `_handle_intel()` 中同步執行（有 timeout）。但計劃中**未明確規定超時後的行為是 BLOCK 還是 ALLOW**。

CC 立場：根據原則 6，H1 Ollama 超時的預設行為必須是：
- **保守路徑**：超時 → 降級到 L0 啟發式評估（_heuristic_evaluate()）並標記 `confidence="heuristic"`
- **不可接受**：超時 → 允許執行（這等同於 Ollama 故障後系統變得更激進）

DOC-08 §12 安全不變量：「Ollama 崩潰 → 退化到 L0，不停止交易」— 但退化後使用 L0 規則評估，而非無限制放行。

**計劃需補充**：Sprint 5a 任務中必須明確 H1 timeout 行為規範，E2 審查時必須核實 timeout 後走 _heuristic_evaluate() 而非 allow-all。

---

### 原則 7：學習 ≠ 改寫 Live

**狀態：✅ 不受影響**

Wave 5 不涉及學習管線修改，L2 學習層隔離不受影響。

---

### 原則 8：交易可解釋

**狀態：✅ 計劃強化此原則**

PA 設計 TradeIntent 帶 `{ai_confidence, model_used, cost_usd}` metadata，可重建每筆交易的推理路徑。H5 CostLogger 同步記錄。這是正向強化。

---

### 原則 9：交易所災難保護

**狀態：✅ 不受影響**

Wave 5 不修改 StopManager 和交易所條件單邏輯。

---

### 原則 10：認知誠實

**狀態：⚠️ 輕度違反（FA-G-10，需在 Sprint 5b 內修復）**

**違反位置**：layer2_cost_tracker.py 的 AI ROI 計算基於 paper PnL（模擬值），但 API 回傳時未標記此為模擬值。

**FA-G-10 發現**：GUI tab-ai.html 顯示的「AI ROI」實際上是用紙面交易模擬 PnL 計算的，這不符合原則 10 要求的「事實/推斷/假設明確區分」。

**CC 要求**：Sprint 5b 前，所有涉及 AI ROI / cost_edge_ratio 的 API 回應必須附加：
```json
"roi_basis": "paper_simulation_only",
"roi_disclaimer": "基於模擬 PnL，非真實盈虧"
```

---

### 原則 11：Agent 最大自主權

**狀態：✅ 計劃強化此原則**

H1-H5 接通後 Agent 自主決策路徑更完整，P0/P1 硬邊界（H0 Gate + Guardian）保持，在邊界內 Agent 自主空間擴大。

---

### 原則 12：持續進化

**狀態：⚠️ 部分改善**

當前 memory.md 記錄此原則為「未實施」。Wave 5 後 AI 調用有成本記錄，但 L2 模式發現自動化（Phase 2 計劃）仍不在 Wave 5 範圍。

評估為「改善但未完成」，不構成新違反。

---

### 原則 13：AI 資源成本感知

**狀態：✅ 計劃強化此原則（但依賴 G-01 修復）**

B-MVP-5（Ollama 調用追蹤）接通後，L1 調用次數有記錄。cost_edge_ratio 計算已實現。

**但 G-01 問題**：每日硬上限 $15.0 vs DOC-08 §4 規定 $2.00，如果不修復，在超過 $2.00 但未達 $15.00 時系統不會觸發 blocked，違反成本感知目的。

---

### 原則 14：零外部成本可運行

**狀態：✅ 計劃合規（含降級鏈）**

PA 技術設計：
```
H2 超預算 → 降級到 L1
Ollama 崩潰 → 退化到 L0（DOC-08 §12 安全不變量）
雲端 API 不可用 → 退化到 L1
```

MessageBus 作為內部通信主通道，OpenClaw 作為 sidecar（fire-and-forget）。OpenClaw 故障不阻塞交易路徑。

**但需要集成測試確認**（FA AC-2）：Mock is_available()=False 時，全流程在 L0 模式下可運行。

---

### 原則 15：多 Agent 協作

**狀態：⚠️ 計劃改善（B-MVP-1 修復後）**

當前 Scout→Strategist 情報路徑是死代碼（produce_intel() 只存本地列表，未 bus.send）。B-MVP-1 修復後，MessageBus 正式建立 Scout→Strategist 對象通信。符合原則 15 要求。

---

### 原則 16：組合級風險意識

**狀態：⚠️ 仍未完全實施**

Wave 5 不涉及組合級風控新增功能。此原則繼續標記為「部分合規」（同 memory.md 記錄）。

---

## 兩個 BLOCKER 的 CC 意見

### G-01：每日硬上限 $15.0 vs $2.00

**CC 立場：$2.00 是正確值，$15.0 必須修正**

理由：
1. DOC-08 §12 安全不變量明確規定「AI 每日硬上限不可突破」，且此處的「硬上限」值在 DOC-08 §4 為 $2.00。
2. $15.0 是 $2.00 的 7.5 倍，在 demo_only 模式下可能被誤判為可接受（「只是測試」），但此值進入 Live 後將成為真實成本風險。
3. 原則 5（生存>利潤）要求保守，成本上限應取更嚴格值而非更寬鬆值。
4. DOC-08 §12 安全不變量是**不可突破**的設計約束，不是「建議值」。

**修復方案**：
- `layer2_types.py` 第 58 行：`DEFAULT_DAILY_HARD_CAP_USD = 2.0`（從 15.0 改為 2.0）
- `tab-ai.html` 第 335/426/441 行：預設值同步改為 2.0
- 同步更新測試中所有直接斷言 `15.0` 的用例（test_layer2.py 中涉及 `DEFAULT_DAILY_HARD_CAP_USD` 的斷言）

**G-01 對啟動時序的影響**：此修復可在 Sprint 5a 執行過程中完成（與 G-05 並行），不必是串行阻塞。但**必須在 Sprint 5a commit 中一起提交**，不可留到 5b。

---

### G-05：ExecutorAgent 缺少 Decision Lease

**CC 立場：這是原則 3 的硬違反，必須在 Strategist shadow=False 之前修復**

理由：
1. 原則 3 是「AI 輸出 ≠ 即時命令」，這是系統設計的核心安全機制之一。
2. Guardian.review_intent() 批准的是「這個意圖值得執行」（質量門），acquire_lease() 控制的是「現在可以執行這個意圖」（時效授權）。兩者是不同層次的控制。
3. 沒有 acquire_lease() 的 submit_order() 調用，等同於 AI 輸出直接成為命令，完整繞過了時效控制和可撤銷性。
4. Decision Lease 的 TTL 機制（Wave 3c P1-4 已修復）確保了即使情況在 Guardian 批准後惡化，舊的 lease 也會自動失效。ExecutorAgent 繞過此機制，在極端情況下可能在市場已劇烈波動後仍按舊的 intent 下單。

**修復時序要求**：
- **Sprint 5a 前必須修復**（不是 Sprint 5b）
- 原因：Sprint 5a 包含 `Strategist shadow=False`，這會讓 StrategistAgent 開始產生真實 TradeIntent，並通過 ExecutorAgent 路徑執行。如果 G-05 未修復，第一個 shadow=False 的 intent 就可能直接繞過 Decision Lease。

**修復方案（PA 需確認設計）**：
```python
# executor_agent.py 的 _execute_order() 方法中，在 submit_order() 前插入：
lease = self._governance_hub.acquire_lease(
    intent_id=intent_id,
    requester="executor_agent",
    ttl_seconds=30,
)
if lease is None:
    # fail-closed：lease 取得失敗 → REJECT
    return ExecutionReport(
        intent_id=intent_id, ..., success=False,
        error="governance_lease_acquisition_failed"
    )
```

---

## 審查結論

```
整體評級：條件通過

修改前提條件（必須修復後才能啟動 Sprint 5a）：
1. G-05【硬阻塞】ExecutorAgent._execute_order() 必須在 submit_order() 前插入
   governance_hub.acquire_lease()，失敗時 fail-closed REJECT。
   違反：原則 3（AI 輸出≠命令）+ 原則 1（單一寫入口）
   負責：PA 確認設計 → E1 實現 → E2 審查 → E4 回歸

2. G-01【硬阻塞】DEFAULT_DAILY_HARD_CAP_USD 必須從 15.0 改為 2.0（對齊 DOC-08 §4）
   違反：DOC-08 §12 安全不變量 + 原則 5（生存>利潤，保守優先）
   負責：E1 修改 layer2_types.py + tab-ai.html，同步更新測試
   時序：與 G-05 並行執行，Sprint 5a commit 時必須一起提交

計劃執行中必須遵守的條件（Sprint 5a-5b 進行中）：
1. 原則 6（失敗默認收縮）：Sprint 5a 的 H1 ThoughtGate 實現中，Ollama 調用超時
   必須走 _heuristic_evaluate()（L0 保守評估），不可 allow-all。
   E2 審查時必須確認 timeout handler 路徑。

2. 原則 10（認知誠實）：Sprint 5b 的 H5 CostLogger 接入時，涉及 AI ROI 的
   API 回應必須附加 roi_basis: "paper_simulation_only" 標記。

3. 原則 14（零外部成本）：Sprint 5b 後，E4 必須補充集成測試：
   Mock Ollama is_available()=False → 確認全流程在 L0 模式下可運行（對應 FA AC-2）。

建議關注點（不阻塞但需注意）：
1. 原則 16（組合級風險）仍未實施。Wave 5 接通後，多品種同時產生 TradeIntent 的
   組合曝險不受監控。建議在 Phase 2 規劃時將此列為前置條件評估。

2. MessageBus 同步回調阻塞風險（PA E2 重點審查第 2 點）：
   bus.send() 在 on_tick 主線程中同步調用，如果 StrategistAgent.on_message() 耗時長
   （H1 Ollama 調用），可能阻塞整個 tick 處理。
   PA 建議的 asyncio.to_thread 包裝是否已在設計中，E2 審查時需確認。

3. max_pending_intents=50 上限：650 符號全掃後 shadow=False 產生大量 TradeIntent，
   PM 已識別為 HIGH 風險。E4 需要專門的壓力測試：650 符號 × 信號觸發率 → 確認
   上限生效且系統不降級。
```

---

## 附錄：16 條原則合規狀態快照（Wave 5 後預期）

| # | 原則 | 當前 | Wave 5 後預期 | 條件 |
|---|------|------|--------------|------|
| 1 | 單一寫入口 | ✅ | ✅ | G-05 修復後 |
| 2 | 讀寫分離 | ✅ | ✅ | - |
| 3 | AI 輸出≠命令 | ⚠️ 部分 | ✅ | G-05 修復後 |
| 4 | 策略不繞風控 | ✅ | ✅ | G-05 修復後 |
| 5 | 生存>利潤 | ✅ | ✅ | G-01 修復後 |
| 6 | 失敗默認收縮 | ✅ | ✅ | H1 timeout 需明確 |
| 7 | 學習≠改寫 Live | ✅ | ✅ | - |
| 8 | 交易可解釋 | ✅ | ✅ | 強化 |
| 9 | 災難保護 | ✅ | ✅ | - |
| 10 | 認知誠實 | ⚠️ 部分 | ⚠️ → ✅ | Sprint 5b roi_basis 標記 |
| 11 | Agent 最大自主 | ✅ | ✅ | 強化 |
| 12 | 持續進化 | ❌ 未實施 | ⚠️ 部分 | Phase 2 才完整 |
| 13 | AI 成本感知 | ⚠️ 部分 | ✅ | G-01 修復後 |
| 14 | 零外部成本 | ✅ | ✅ | 需集成測試確認 |
| 15 | 多 Agent 協作 | ⚠️ 部分 | ✅ | B-MVP-1 修復後 |
| 16 | 組合級風險 | ❌ 未實施 | ❌ | Phase 2 才規劃 |

預期評級：B→A-（若 G-01/G-05 修復 + Sprint 5b 完成後）
