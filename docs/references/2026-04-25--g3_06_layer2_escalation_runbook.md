# G3-06 Layer 2 Autonomous Escalation Rules — Operator Runbook
**Date**: 2026-04-25 · **Phase**: A (scaffolding only) · **Status**: DEFAULT-OFF

---

## Why this exists / 為何需要本模組

Per `memory/project_layer2_agent_design.md`, OpenClaw 的 AI 推理分三層：

- **L0** Deterministic gates（H0 / Guardian / cost_gate）— always on, zero cost
- **L1** Local LLM（Ollama / LM Studio / Haiku triage）— ~$0.01 / 次
- **L2** Cloud LLM（Claude Sonnet / Opus）— ~$0.50–$2.00 / 次

升級條件先前是散落的 heuristic（H1 ThoughtGate complexity ≥ 0.3 / model_router 0.5/0.8 cutoff / layer2_engine L1 triage prompt 等）。G3-06 把「**何時**升級」這條獨立決策正式化為純函數模組，方便單元測試 + 可配置 + 可審計。

Phase A 只交付模組 + 配置 + tests；**不接 hot path**（multi_agent_framework decision dispatch 不變）。

---

## Module / 模組

`program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_escalation.py`

```python
from app.layer2_escalation import (
    EscalationTier,            # L0_DETERMINISTIC | L1_LOCAL_LLM | L2_CLOUD_LLM
    EscalationDecision,        # target_tier + reasons + budget_estimate_usd
    LayerEscalationConfig,     # thresholds + enabled flag
    decide_escalation_tier,    # pure function (context, config) -> EscalationDecision
    tier_rank,                 # tier ordering helper
)
```

純函數無副作用，無 IO，安全直接調用。

---

## Decision rules / 決策規則

當 `config.enabled=True` 時：

1. **Default L0** — 任何缺值 / 不滿足任何升級條件 → L0
2. **L1 trigger** — 任一即升 L1：
   - `signal_strength ≥ l1_signal_min` (default 0.5)
   - `position_notional_usdt ≥ l1_position_min_usdt` (default $50)
3. **L2 trigger** — 全部滿足才升 L2：
   - L1 已觸發
   - `agent_uncertainty_flag == True`（L1 自報「我不知道」）
   - 至少一個重大訊號：
     - `position_notional_usdt ≥ l2_position_min_usdt` (default $500)
     - `cost_edge_ratio ≥ l2_cost_edge_max` (default 0.8 — DOC-01 #13)
     - `news_severity_recent ≥ l2_news_severity_min` (default 0.7)
   - `recent_l2_calls_24h < l2_calls_24h_cap` (default 10)
   - `l2_budget_remaining_usd ≥ l2_min_budget_usd` (default $0.50)
4. **Hard ceilings**（fail-closed）：上限或預算不足 → 強降回 L1，reasons 帶
   `budget_cap_*` 明文。

---

## Configuration / 配置

### Default OFF（Phase A safety contract）

```python
cfg = LayerEscalationConfig()      # enabled=False
decide_escalation_tier({...}, cfg) # always returns L0 + reason="escalation_disabled"
```

### Env override

```bash
export OPENCLAW_L2_ESCALATION_ENABLED=1
export OPENCLAW_L2_ESCALATION_L1_SIGNAL_MIN=0.5
export OPENCLAW_L2_ESCALATION_L1_POSITION_MIN=50
export OPENCLAW_L2_ESCALATION_L2_POSITION_MIN=500
export OPENCLAW_L2_ESCALATION_L2_COST_EDGE_MAX=0.8
export OPENCLAW_L2_ESCALATION_L2_NEWS_MIN=0.7
export OPENCLAW_L2_ESCALATION_L2_CALLS_CAP=10
export OPENCLAW_L2_ESCALATION_L2_MIN_BUDGET=0.50

cfg = LayerEscalationConfig.from_env()   # picks up overrides above
```

未設或亂格式（e.g. `=not_a_number`）→ 自動 fallback 到 dataclass 預設值並 warning log。

---

## Verification / 驗證

```bash
# Mac (after import path setup)
python3 -c "from program_code.exchange_connectors.bybit_connector.control_api_v1.app.layer2_escalation import decide_escalation_tier; print('OK')"

# Tests (Mac or Linux, from control_api_v1/)
python3 -m pytest tests/test_layer2_escalation.py -x -q
# Expected: 21 passed
```

Linux baseline: pytest 3056 → expected **3077** (3056 + 21 new tests).

---

## Phase B / 後續

當 operator 同意展開 G3-06 Phase B 時：

1. 在 `multi_agent_framework.py::Conductor.decide()` 之前插入一次
   `decide_escalation_tier(...)` 呼叫，根據 `target_tier` 路由到 L0 / L1 / L2 引擎。
2. 把 `decision.reasons` 寫進現有 `audit_callback`（已有 5 agent 接線）
3. 把 `decision.budget_estimate_usd` 寫進 `Layer2CostTracker.record_call`
4. 在 GUI Learning Cockpit 加 escalation reasoning 視圖

不在 Phase A 範圍。Phase A 完成判定 = 模組 + tests + 本 runbook 落地，預設關閉，pytest 綠。

---

## Constraints respected / 約束遵守

- ✅ 不動 hot path（multi_agent_framework.py / strategist_agent.py / executor_agent.py 全未碰）
- ✅ 不動 Rust
- ✅ 不動 G3-02/03/04/05/10 / G4-* / G7-* / G5-* 已 commit 的工作
- ✅ DEFAULT-OFF / pass-through 預設保留現行行為
- ✅ Phase A 邊界：rules 模組 + config + tests only
