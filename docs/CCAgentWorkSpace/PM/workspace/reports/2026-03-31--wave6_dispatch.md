# PM 派發計劃 — Wave 6 正式啟動
# 日期：2026-03-31
# 作者：PM（Project Manager）
# 依據：PA 架構報告（wave5_architecture_review.md）+ FA 功能驗收（wave5_functional_acceptance.md）+ 代碼審計

---

## 一、Wave 6 背景與啟動依據

### 前置條件確認
- **Wave 5 完成基準**：2610 passed / 18 pre-existing failed
- **系統狀態**：demo_only，live_execution_allowed = false（不變）
- **三方共識**：PM + PA + FA 已就優先順序達成一致

### Wave 6 核心目標

| 目標 | 依據 | 影響 |
|------|------|------|
| 消除 Principle 3 雙重標準 | PA 發現 TD-1，架構缺口 | 原則 3 完整實施 |
| 打通學習管線輸入 | FA 發現 FA-7，BLOCKER | 原則 12 可開始合規 |
| Batch 1B 安全閘補全 | Phase 1 路線圖 | Cooldown 聯動端到端驗證 |

---

## 二、技術細節確認（代碼審計結論）

### TD-1 確認（pipeline_bridge.py）

**問題位置**：`app/pipeline_bridge.py` line 701 `_process_pending_intents()`

**執行路徑分析**：
- Guardian.review_intent() 返回 APPROVED（line 643-650）或 MODIFIED（line 629-642）後
- 直接進入 line 695-700 的 edge filter 和 limit order price 處理
- line 701 `self._engine.submit_order()` — **無任何 acquire_lease() 呼叫**

**可行性確認**：
- `self._governance_hub` 已在 `__init__` line 95 聲明，`set_governance_hub()` 已存在（line 165-167）
- `acquire_lease(intent_id, scope, ttl_seconds)` 簽名已確認（governance_hub.py line 772）
- `_governance_hub` None 時 fail-closed 方向：跳過 lease，直接 submit（向後兼容，兼顧測試覆蓋）
- 插入位置：line 695 的 `category = ...` 行之前，Guardian 批准後、submit 前

**MODIFIED 路徑覆蓋**：MODIFIED 路徑（line 629-642）設定 `_submit_qty` 後，與 APPROVED 路徑合流至同一 submit_order() 呼叫點，插入 lease gate 在兩者合流後即可同時覆蓋兩條路徑。

### FA-7 確認（register_data 缺口）

**現有 register_data 調用點**：
1. `on_tick()` line 347：WS ticker 價格更新 ✅（已存在）
2. `_emit_round_trip()` line 1473：round_trip 完成 ✅（已存在）

**缺口確認**：`_check_stops()` line 839-844 的止損 submit_order 後，未觸發 `_emit_round_trip()` 或直接 `register_data()`。止損成功後 close_pnl 結果未注入 PerceptionPlane。

**修復方向**：確認 `_check_stops()` 止損成功後的回調路徑，確保對稱地調用 `_emit_round_trip()`。

**perception_plane 注入確認**：`set_perception_plane()` 已存在（line 169-171），`_perception_plane` 在 line 96 聲明。需確認 `phase2_strategy_routes.py` 是否已調用 `set_perception_plane()`。

---

## 三、Wave 6 Sprint 結構

### Sprint 0：TD-1（最高優先，P1）

| 項目 | 說明 |
|------|------|
| 任務 | pipeline_bridge `_process_pending_intents()` 補入 `acquire_lease()` |
| 文件行號 | `app/pipeline_bridge.py` line 695（category 行之前） |
| 指派 | E1-Alpha |
| 工時估算 | E1: 1h + E2: 0.5h + E4: 0.5h = 2h total |
| 目標測試數 | ≥ 2615 passed |
| 違反原則 | 原則 3（AI 輸出 ≠ 即時命令）|

**新增測試（E4，Sprint 0）**：
- `test_process_pending_intents_acquire_lease_called`：Guardian APPROVED → acquire_lease() 被調用
- `test_process_pending_intents_lease_fail_closed`：acquire_lease 返回 None → intent 跳過，rejected +1
- `test_process_pending_intents_no_governance_hub`：`_governance_hub=None` → 跳過 lease 直接 submit
- `test_process_pending_intents_modified_also_requires_lease`：MODIFIED 路徑同樣觸發 acquire_lease

工作鏈：E1-Alpha → E2 → E4 → PM 確認 → commit

---

### Sprint 1a：FA-7（阻塞 Phase 2，前置 Sprint 0）

| 項目 | 說明 |
|------|------|
| 任務 | pipeline_bridge position_close 事件補入 register_data() |
| 文件行號 | `app/pipeline_bridge.py`，`_check_stops()` 止損成功後 line ~850+ |
| 指派 | E1-Beta |
| 工時估算 | E1: 1.5h + E2: 0.5h + E4: 1h = 3h total |
| 目標測試數 | ≥ 2620 passed |
| 違反原則 | 原則 12（持續進化）|

**前置**：Sprint 0 完成後（同一文件，避免 merge 衝突）

**新增測試（E4，Sprint 1a）**：
- `test_perception_plane_register_data_on_stop_close`
- `test_perception_plane_register_data_on_tick_close`
- `test_perception_plane_register_data_on_intent_close`

工作鏈：（Sprint 0 完成後）E1-Beta → E2 → E4 → PM 確認 → commit

---

### Sprint 1b：Batch 1B（可與 1a 並行，不同文件）

| 任務 | 文件 | 指派 | 工時 |
|------|------|------|------|
| 1B-1：Cooldown 聯動 smoke test（5 個測試）| 新建 test 文件 | E4 | 2h |
| 1B-2：H0Gate freshness API 擴充 | `governance_routes.py` | E1-Gamma | 1.5h |
| TD-3：H5 cost_tracker except → logger.warning | `strategist_agent.py ~485` | E1-Gamma | 15m |
| TD-4：_h1_cooldown LRU cap（上限 1000）| `strategist_agent.py` | E1-Gamma | 30m |

**目標測試數**（Sprint 1b 完成後）：≥ 2630 passed

工作鏈：E4（1B-1）‖ E1-Gamma（1B-2+TD-3+TD-4）並行 → E2（E1-Gamma 改動）→ E4 回歸 → PM 確認 → commit

---

### Sprint 2：P2 批次（Sprint 1a+1b 完成後，~20h）

| 任務 | 文件 | 指派 | 工時 | 前置 |
|------|------|------|------|------|
| P2-6/7/8：RiskManager 邊界測試 | `risk_manager.py` | E1-Alpha + E4 | 6h | 無 |
| P2-12/15：pipeline_bridge 邊界 | `pipeline_bridge.py` | E1-Beta + E4 | 4h | Sprint 1a 完成後 |
| TD-2：廢棄 StrategistAgent collect 路徑 | `pipeline_bridge.py` + `strategist_agent.py` | E1-Alpha | 3h | Sprint 0 完成後 |
| FA-8：GUI cost_edge_ratio None 處理 | `tab-ai.html` / JS | E1a | 1h | 無 |

**目標測試數**（Sprint 2 完成後）：≥ 2650 passed

---

## 四、測試目標里程碑

| Sprint | 完成後目標 | 累積新增 |
|--------|----------|---------|
| Sprint 0 | 2615 passed | +5 |
| Sprint 1a | 2620 passed | +10 |
| Sprint 1b | 2630 passed | +20 |
| Sprint 2 | 2650 passed | +40 |

---

## 五、風險記錄

| 風險 | 等級 | 緩解措施 |
|------|------|---------|
| TD-1 lease gate 影響 MODIFIED 路徑 | MEDIUM | E2 重點審查兩條路徑合流點 |
| FA-7 register_data 線程安全 | MEDIUM | E2 確認 PerceptionPlane 加鎖 |
| Sprint 1a 和 Sprint 0 同文件衝突 | LOW | 強制前後順序，不並行 |
| TD-2 廢棄路徑副作用 | MEDIUM | E4 全量回歸確認現有測試不破壞 |

---

## 六、關鍵決策記錄

- **_governance_hub=None 時不 fail-closed**：pipeline_bridge 直接路徑允許在無 governance_hub 時跳過 lease（向後兼容測試覆蓋，PaperTradingEngine 自身有 GovernanceHub gate 兜底）
- **Sprint 0 和 1a 不並行**：兩者均修改 pipeline_bridge.py，強制順序執行避免 merge 衝突
- **M-of-N 繼續移出**：用戶確認 demo_only 模式單 Operator，不在 Wave 6 範圍
- **P3 GUI 術語友好化繼續推遲**：Wave 6 不包含，等用戶明確要求

---

*PM — 2026-03-31*
*下一份報告：Sprint 0 完成確認後*
