# R-06-v2 Agent Value Delivery — Engineering Worklog

**Date**: 2026-04-13
**Session scope**: G-1 / R-06 → R-06-v2 重新定義 + 全部實施
**Duration**: Single session
**Operator decision**: Direction B (close learning loops) → A (shadow Executor) → evaluate

---

## 1. Background & Problem Statement / 背景與問題陳述

### Original R-06 Plan (rejected)
原始 R-06 計劃是加 Rust→Python IPC plumbing：
- Conductor stub→real IPC handler
- Rust→analyst_evaluate fire-and-forget
- Rust→conductor_evaluate 2min health check
- Rust→scout_scan 從 Rust 觸發掃描

### Deep Analysis Findings (AIE + FA + FM)
Operator 要求 deep think（"確認這個是最優解，由FA和FM確定這就是我們想要的"）。

分析結果：**原始 R-06 是 100% plumbing, 0% value delivery。**

核心發現：

| Finding | Detail |
|---------|--------|
| **Path A 斷裂** | ExecutorAgent `_paper_engine=None`（DEAD-PY-2 刪除），所有 APPROVED_INTENT → `success=False` |
| **Analyst 無消費者** | PatternInsight → TruthRegistry（in-memory），Rust 從不讀取 |
| **Guardian 反饋斷路** | 拒絕裁定不回饋 Strategist，下次決策無學習 |
| **Conductor 零調用** | `dispatch_market_event/resolve_conflict/process_trade_intent` 只有 tests 調用 |
| **原始 IPC = 空管道** | 把管道接到空桶上，不產生任何價值 |

### Architecture: Two Parallel Trading Paths

```
Path A (Python Agent — BROKEN)
  Scout → Strategist → Guardian → Executor(broken) → ✗

Path B (Rust Tick Pipeline — Running)
  5 strategies → IntentProcessor → GovernanceGate → paper_state → fills

Bridge (Working but not improving)
  StrategistScheduler (5min) → IPC → Ollama → param tuning → Rust apply
  (closed loop, but strategies have negative edge)
```

### Learning Loop Gaps

```
Strategist param tuning ──→ Rust strategy params ──→ Trade results
       ↑                                                 │
       │    ✅ StrategistScheduler reads fills metrics     │
       └─────────────────────────────────────────────────┘

Guardian rejections ──→ ??? ──→ Strategist next decision
                        ↑
                  ❌ NO FEEDBACK PATH

Analyst PatternInsight ──→ ??? ──→ Strategy improvement
                            ↑
                     ❌ RUST NEVER READS
```

---

## 2. Decision: Redefine R-06 as "Agent Value Delivery" / 決策：重新定義

Three options were evaluated:

| Direction | Description | Recommendation |
|-----------|-------------|---------------|
| **A** | Fix Executor IPC bridge (make Path A work) | Do as shadow-only |
| **B** | Close learning loops (Analyst+Guardian→Strategist) | **Highest value — do first** |
| **C** | Skip R-06, fix strategies directly | Needs data from B first |

**Final decision**: B → A(shadow) → evaluate

Core logic: 沒有反饋的 Agent 是裝飾品。先讓反饋閉環，再談其他。

---

## 3. Implementation Details / 實施細節

### 3.1 Step 2: Analyst → DB → Strategist Feedback Loop

**Problem**: Analyst produces PatternInsight (winning/losing patterns) but:
- Stored only in TruthSourceRegistry (in-memory Python)
- Rust StrategistScheduler never reads it
- Ollama prompt has no context about what worked/failed

**Solution**:

**V016 Migration** (`sql/migrations/V016__learning_feedback_loop.sql`):
```sql
CREATE TABLE learning.pattern_insights (
    id              SERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    strategy_name   TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    pattern_type    TEXT NOT NULL,     -- 'winning' or 'losing'
    pattern_text    TEXT NOT NULL,
    confidence      REAL NOT NULL DEFAULT 0.5,
    observation_count INT NOT NULL DEFAULT 0,
    engine_mode     TEXT NOT NULL DEFAULT 'demo'
);
-- + 2 indexes: (strategy_name, ts DESC), (engine_mode, ts DESC)
```

**New module** (`ai_service_feedback.py`, 205 lines):
- `persist_analyst_feedback(strategy, symbol, metrics, engine_mode)`:
  - Called from `_handle_analyst()` after `AnalystAgent.analyze_trade()`
  - Extracts win_rate / avg_pnl from metrics → derives winning/losing patterns
  - Writes to `learning.pattern_insights`
  - Fail-open: DB errors never block analysis IPC

- `get_feedback_section(strategy, days=7)`:
  - Called from `_handle_strategist()` before Ollama prompt
  - Queries `learning.pattern_insights` for recent patterns (LIMIT 8)
  - Queries `trading.risk_verdicts` JOIN `trading.intents` for reject_rate
  - Returns formatted text appended to Ollama prompt
  - Fail-open: DB errors → empty string

**ai_service.py changes** (+5 lines net):
```python
# In _handle_analyst, after analyze_trade():
from .ai_service_feedback import persist_analyst_feedback
await asyncio.to_thread(persist_analyst_feedback, record.strategy, symbol, metrics)

# In _handle_strategist, before Ollama call:
from .ai_service_feedback import get_feedback_section
fb = await asyncio.to_thread(get_feedback_section, strategy)
if fb:
    prompt += "\n\n" + fb
```

### 3.2 Step 3: Guardian Rejection Feedback to Strategist

**Problem**: Guardian rejects intents via Rust H0 gate, but Strategist doesn't know.

**Solution**: No new writes needed! Rust already writes to `trading.risk_verdicts`:
- IntentProcessor → governance check → `TradingMsg::RiskVerdict` → `flush_verdicts()` → DB
- Fields: `verdict` (Approved/Modified/Rejected), `reason`, `engine_mode`
- Linked to `trading.intents` via `intent_id` (which has `strategy_name`)

`get_feedback_section()` queries:
```sql
SELECT COUNT(*) AS total,
       COUNT(*) FILTER (WHERE rv.verdict = 'Rejected') AS rejected,
       array_agg(DISTINCT rv.reason) FILTER (WHERE rv.verdict = 'Rejected' ...) AS reasons
FROM trading.risk_verdicts rv
JOIN trading.intents i ON rv.intent_id = i.intent_id ...
WHERE i.strategy_name = %s AND rv.ts > now() - interval '7 days'
```

Output in Strategist prompt:
```
Guardian rejection rate: 42.1% (8/19 intents rejected)
  Top rejection reasons: max_drawdown_exceeded; correlation_limit
  NOTE: High rejection rate — consider more conservative parameters.
```

### 3.3 Step 1: Executor IPC Bridge (shadow-only)

**Problem**: `ExecutorAgent._paper_engine = None` since DEAD-PY-2 (commit de1ec69, 2026-04-08).
Every `APPROVED_INTENT` → `success=False, error="No paper engine available"`.

**Solution** (`executor_agent.py`, +115 lines):

New method `_execute_via_ipc()`:
- When `_paper_engine is None` → calls `_execute_via_ipc()` instead of failing
- Class attribute `_shadow_mode: bool = True` (default)

**Shadow mode (default)**:
```python
logger.info("Executor IPC shadow: intent=%s %s %s qty=%.6f", ...)
report = ExecutionReport(
    success=True, error="shadow_mode",
    metadata={"execution_path": "ipc_shadow"},
)
```
- Logs the intent
- Returns shadow "success" report
- **No actual order placed** — avoids Path A/B position conflicts

**Real mode (operator opt-in, `_shadow_mode = False`)**:
```python
from .paper_trading_routes import _ipc_command
ipc_params = {
    "symbol": symbol, "side": side, "qty": qty,
    "order_type": order_type,
    "strategy": f"agent_executor:{intent_id[:12]}",
}
result = await _ipc_command("submit_order", ipc_params)
```
- Routes to Rust IPC server `SubmitOrder` → `PipelineCommand::SubmitOrder`
- Goes through same governance + risk pipeline as Rust-originated intents
- Tagged with `agent_executor:` prefix for attribution
- Sync→async bridge handles both running loop and no-loop contexts

**Decision: Keep shadow=True** — Phase 5 PAUSED, all strategies negative edge. Opening real mode would produce conflicting positions from two paths, both losing money. Revisit after strategy edge is fixed.

### 3.4 Step 4: Conductor stub→real

**Problem**: `_handle_conductor()` returned static `{"action": "maintain_current"}` regardless of input.

**Solution** (`ai_service.py`, net 0 lines via docstring compaction):

```python
# Before (stub):
return {"action": "maintain_current", "source": "ai_service_stub"}

# After (real):
health = await asyncio.to_thread(self._conductor.get_agent_health)
status = await asyncio.to_thread(self._conductor.get_status)
degraded = [k for k, v in health.items() if v.get("stale")]
action = "scale_down" if len(degraded) > 2 else "maintain_current"
return {
    "action": action, "agent_health": health,
    "agents_running": status.get("agents_running", 0),
    "degraded_agents": degraded,
    "source": "conductor_real",
}
```

Conductor injected in `create_ai_service_listener()`:
```python
from .strategy_wiring import CONDUCTOR
conductor = CONDUCTOR
# ... passed to AIService(conductor=conductor)
```

Fallback: if Conductor not available → returns stub response (same as before).

---

## 4. Files Changed / 變更文件清單

| File | Action | Lines | Description |
|------|--------|-------|-------------|
| `sql/migrations/V016__learning_feedback_loop.sql` | NEW | 44 | `learning.pattern_insights` table + indexes |
| `app/ai_service_feedback.py` | NEW | 205 | DB write/read for feedback loop + prompt section |
| `app/ai_service.py` | MODIFIED | 1195 (net 0) | Analyst persist + Strategist feedback + Conductor real + inject |
| `app/executor_agent.py` | MODIFIED | 628 (+115) | `_execute_via_ipc()` shadow/real bridge |
| `tests/test_batch11_executor_exchange.py` | MODIFIED | +3 | test_07 updated for shadow mode |
| `tests/test_executor_agent_unit.py` | MODIFIED | +3 | test_no_engine updated for shadow mode |
| `TODO.md` | MODIFIED | +6 | R-06 → R-06-v2 completion entry |
| `docs/CLAUDE_CHANGELOG.md` | MODIFIED | +3 | Changelog entry |
| `docs/references/2026-04-13--r06_deep_analysis_agent_value.md` | EXISTS | 137 | Deep analysis draft (saved earlier) |

---

## 5. Test Results / 測試結果

| Suite | Count | Status |
|-------|-------|--------|
| Rust engine lib | 1091 | ✅ 0 fail |
| Rust e2e | 33 | ✅ 0 fail |
| Python | 2852 | ✅ 0 fail |
| Import verification | ✅ | AIService + feedback module |
| Executor shadow test | ✅ | Manual + unit test |

### Test changes:
- `test_07_no_paper_engine_fail_closed` → `test_07_no_paper_engine_ipc_shadow`
  - Old: expected `success=False, "No paper engine"`
  - New: expected `success=True, error="shadow_mode", metadata.execution_path="ipc_shadow"`
- Same pattern in `test_no_engine_fails` → `test_no_engine_ipc_shadow`

### E2 Code Review: PASS
- Security (SQL injection/XSS): PASS — psycopg2 parameterized queries
- Hardcoded paths: PASS — no `/home/ncyu` in new code
- Bilingual comments: PASS — all new functions/modules have EN+中
- File limits: WARN — ai_service.py at 1195/1200 (pre-existing, flagged)
- Fail-closed/open: PASS — execution path fail-closed, feedback writes fail-open

---

## 6. Architecture After R-06-v2 / R-06-v2 後的架構

### Learning loops: BEFORE vs AFTER

```
BEFORE:
  Strategist ←── fills metrics ──── Rust trades
  Strategist ←── (nothing) ──────── Analyst patterns
  Strategist ←── (nothing) ──────── Guardian rejections

AFTER:
  Strategist ←── fills metrics ──────────── Rust trades       (existing)
  Strategist ←── learning.pattern_insights ── Analyst patterns (NEW: Step 2)
  Strategist ←── trading.risk_verdicts ────── Guardian rejects (NEW: Step 3)
```

### Agent IPC handler status

| Handler | Before R-06-v2 | After R-06-v2 |
|---------|---------------|---------------|
| `strategist_evaluate` | REAL (Ollama) | REAL + feedback-enriched prompt |
| `guardian_check` | REAL (Ollama L1) | Unchanged |
| `analyst_evaluate` | REAL (C1 AnalystAgent) | REAL + DB persistence |
| `scout_scan` | REAL (C2 ScoutAgent) | Unchanged |
| `conductor_evaluate` | **STUB** | **REAL** (agent health + degradation) |

### Executor path

```
BEFORE:
  APPROVED_INTENT → ExecutorAgent → _paper_engine=None → FAIL (always)

AFTER:
  APPROVED_INTENT → ExecutorAgent → _execute_via_ipc()
    → shadow_mode=True  → LOG + shadow report (default)
    → shadow_mode=False → Rust IPC SubmitOrder → paper_state (operator opt-in)
```

---

## 7. What Was NOT Done (by design) / 明確不做的

| Item | Reason |
|------|--------|
| Rust→Python fire-and-forget IPC | Pure plumbing, Analyst already called via C1 |
| Conductor health check polling (2min) | GUI already has `/governance/agents/health` endpoint |
| Rust→scout_scan trigger | Rust Scanner already independent; Python Scout via MessageBus |
| `_shadow_mode = False` | Phase 5 PAUSED, strategies negative edge, Path A/B conflict risk |

---

## 8. Remaining Work & Dependencies / 後續工作

| Item | Priority | Dependency |
|------|----------|------------|
| Executor `_shadow_mode=False` | P2 | Strategy edge repair (Phase 5 resume) |
| Analyst L2 PatternInsight (deeper analysis) | P2 | More fills data + Ollama L2 model |
| Conductor IPC caller in Rust | P3 | Not urgent — no production use case yet |
| `learning.pattern_insights` retention policy | P3 | 30d manual cleanup → automate later |

---

## 9. Key Decisions / 關鍵決策記錄

1. **R-06 scope redefinition**: 原始 plumbing → value delivery。依據：AIE 分析顯示所有 IPC 管道對端為空。
2. **Python-side DB reads for feedback**: 選擇 Python query DB 而非 Rust 發送 IPC payload 擴展。原因：不改 IPC 契約、複雜度集中一處、Python 已有 db_pool。
3. **Shadow mode default True**: 修復架構斷裂但不開啟交易。原因：Phase 5 PAUSED + negative edge + 雙路衝突風險。
4. **Guardian: no new writes**: Rust 已寫 `risk_verdicts`，直接查詢即可。省去 Python Guardian 改動（且 Path A Guardian 因 Executor 斷裂幾乎無調用）。
5. **Conductor: thin dispatch**: 返回真實 health data + 退化偵測，但不加複雜編排邏輯（無生產調用者）。

---

## 10. One-line Status / 一句話狀態

> R-06-v2 COMPLETE: 學習閉環已關閉（Analyst→DB→Strategist + Guardian reject_rate）、Executor IPC 橋接就緒（shadow 默認）、Conductor real。1091 Rust + 2852 Python = 0 fail。V016 migration 已執行。
