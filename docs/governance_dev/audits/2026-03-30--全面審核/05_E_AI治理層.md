# Batch E：AI 治理層（H0-H5）
# Batch E: AI Governance Layer Verification

**審查時間：** 2026-03-30
**狀態：** ✅ 完成
**結論：** Decision Lease 和 H0 gate 完整；ThoughtGate/H1-H5 AI 調用鏈在 win_rate < 20% 條件下被合法跳過

---

## E1：H0 本地判斷完整性

✅ **代碼確認正確**

```python
# governance_hub.py:512-561 is_authorized()
def is_authorized(self) -> bool:
    if not self._enabled or self._mode == GovernanceMode.FROZEN:
        return False
    # TTL cache check（lock-free hot path）
    # → check authorization_sm.get_effective()
    effective_auths = self._authorization_sm.get_effective()
    return len(effective_auths) > 0
```

- **Fail-closed：** 未啟用或 FROZEN 狀態立即返回 False
- **TTL 緩存：** 熱路徑無鎖優化，減少競態
- **四個 gate：** freshness / health / eligibility / risk_envelope 均在 H0 本地執行

---

## E2：ThoughtGate 路由邏輯

⚠️ **合法跳過（非失效）**

決策：`win_rate < 20%` 前不接入 AI 咨詢（CLAUDE.md 已記錄）。

```python
# 當前狀態
should_call_ai = false  # 合法 no-call 路徑
route_plan = "route_skip"
```

- `should_call_ai=false` 是合法的 observation terminal path，不是失敗
- ThoughtGate 在 main_legacy.py 中有引用（lines 3099, 3824-3826）
- AI 調用鏈完整性取決於 win_rate > 20% 後的接入，當前無需驗證

---

## E3：Decision Lease shadow mode

✅ **代碼確認正確**

```python
# decision_lease_state_machine.py:53-70
class LeaseState(str, Enum):
    DRAFT = "DRAFT"
    REGISTERED = "REGISTERED"
    ACTIVE = "ACTIVE"
    BRIDGED = "BRIDGED"
    FROZEN = "FROZEN"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"
    REJECTED = "REJECTED"
    CONSUMED = "CONSUMED"

TERMINAL_STATES = frozenset({REVOKED, EXPIRED, REJECTED, CONSUMED})
```

- 9 狀態 FSM，20+ 合法狀態轉移
- BRIDGED ≠ 訂單已提交（shadow-only 語義）
- 每次轉移發出 `lease_transition` 審計對象
- `decision_lease_emitted = False`（系統硬狀態，無租約實際發出）

---

## E4：AI cost tracking

✅ **代碼確認正確**

```python
# paper_trading_engine.py:1691-1703
total_ai_cost = sum(
    p.get("holding_cost", {}).get("ai_cost_attributed_usd", 0.0)
    for p in state["positions"].values()
)
pnl["total_ai_cost"] = total_ai_cost
pnl["net_paper_pnl"] = realized + unrealized - total_fees - total_ai_cost
```

- B1 修復：從 `positions[].holding_cost.ai_cost_attributed_usd` 匯總（此前永遠是 0.0）
- AI 稅率表（risk_manager.py lines 49-55）：dormant=$0/h, low=$0.003/h, medium=$0.01/h, high=$0.05/h, critical=$0.10/h
- **當前值：** total_ai_cost = $0（0 持倉，0 fills）

---

## E5：Win rate gate

✅ **代碼確認正確**

```python
# learning_tier_gate.py:438-444
if target_tier == LearningTier.L2 and current == LearningTier.L1:
    if self._state.observation_count < 500:
        reasons.append(f"insufficient_observations:{self._state.observation_count}/500")
    if self._state.win_rate < 0.20:
        reasons.append(f"low_win_rate:{self._state.win_rate:.2%}/20.00%")
    return len(reasons) == 0, reasons
```

- L2 升級條件：**500+ observations + win_rate > 20%**
- 當前 win_rate = 0%（0 round_trips），L2 gate 完全鎖定
- AI 咨詢不被調用 → 合法設計決策

---

## 結論

AI 治理層架構設計完整。當前系統處於：
- H0 gate：啟用，fail-closed
- Decision Lease：shadow-only，無租約發出
- AI 調用：合法跳過（win_rate < 20%，read_only 模式）
- AI 成本追踪：代碼就緒，等待有 fills 後生效
