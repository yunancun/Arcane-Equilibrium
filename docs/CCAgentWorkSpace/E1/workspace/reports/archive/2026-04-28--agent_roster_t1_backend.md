# E1 — Agent Roster T1 後端 (`/api/v1/agents/roster`)

**日期**：2026-04-28  
**Operator 任務來源**：Plan `aa-nifty-walrus.md` Wave T1（後端，與 T3 前端並行）  
**狀態**：✅ 實作完成，待 E2 審查 / E4 回歸  
**Branch**：未 commit（E1 規定）

---

## 1. 任務摘要

實作 Agent 追蹤視圖後端 MVP — 新 endpoint `GET /api/v1/agents/roster` 聚合 5 個 runtime Agent（Scout/Strategist/Guardian/Executor/Analyst）狀態給 GUI Learning Cockpit 子分頁使用。Strategist 的 `summary_zh` 採後端結構化組句（plan §"後端配合" UX A 級合約）。

完成項目：
1. ✅ 新 `app/agents_routes.py` 實作 endpoint + 5 卡片 builder + Strategist `_compose_summary_zh()` helper
2. ✅ `main.py` 註冊 `agents_router`（對齊既有 router 註冊樣式）
3. ✅ `tests/test_agents_routes.py` 8 個 unit test：happy path / PG outage / singleton missing / summary_zh 模板（評估中 / 預算耗盡 / 無 raw JSON 洩漏）/ Executor offline 文案 / statement_timeout 常量 / grep INSERT/UPDATE/DELETE = 0
4. ✅ Auth 對齊既有 `/strategist/history` — `Depends(base.current_actor)` viewer 即可
5. ✅ statement_timeout = 2s（每個 PG cursor 設 `SET LOCAL`）

---

## 2. 修改清單

| 檔案 | 動作 | 行數 | 說明 |
|---|---|---|---|
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/agents_routes.py` | 新增 | 775 | Agent Roster 路由模組（純讀，含 5 card builder + Strategist 中文組句 helper） |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/main.py` | 修改 | +13 | 加 `from .agents_routes import agents_router` + `app.include_router(agents_router)` 含雙語注釋區塊 |
| `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agents_routes.py` | 新增 | 460 | 8 個 unit test 覆蓋 happy / fail-closed / 模板契約 |

**檔案大小**：`agents_routes.py` 775 行（< 800 §九 警告線；spec 寫 < 400，超出主因為 6 個 card builder + 完整雙語 docstring 加總；MODULE_NOTE 已縮減過一次）

**新 SQL migration**：**無**（沿用 V010 `idx_ai_usage_log_scope_time(scope, time DESC)` 索引；`trading.intents` / `risk_verdicts` 是 daily-chunk hypertable 自動 partition prune by `ts`，今日窗口僅 1 chunk）

---

## 3. 關鍵 diff

### 3.1 endpoint 主體（agents_routes.py:643-720）
```python
@agents_router.get("/roster")
async def get_agents_roster(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    response_ts = datetime.now(timezone.utc).isoformat()
    today_costs_by_role, cost_err = _fetch_today_costs_by_role()
    today_by_strategy, today_intent_total, intent_err = _fetch_today_intent_counts_by_strategy()
    today_verdicts, verdict_err = _fetch_today_risk_verdict_counts()

    degraded = any(err is not None for err in (cost_err, intent_err, verdict_err))
    reason = cost_err or intent_err or verdict_err
    scan_interval_s = _get_cognitive_scan_interval_s()

    cards = [
        _build_scout_card(today_costs_by_role, today_intent_total, scan_interval_s),
        _build_strategist_card(today_costs_by_role, today_intent_total, today_verdicts, scan_interval_s),
        _build_guardian_card(today_costs_by_role, today_verdicts),
        _build_executor_card(today_costs_by_role, today_intent_total),
        _build_analyst_card(today_costs_by_role, scan_interval_s),
    ]
    return {
        "ok": True,
        "data": {"ts": response_ts, "agents": cards, "scan_interval_s": scan_interval_s,
                 "degraded": degraded, "reason": reason},
        "is_simulated": False, "data_category": "agents_roster",
    }
```

### 3.2 Strategist 後端組句 helper（agents_routes.py:430-475）
```python
def _compose_summary_zh(strategist, *, state, intent_count_today, rejection_count_today) -> str:
    # 狀態優先；budget 耗盡 / 拒絕模式比「評估中」更能反映當前操作現實
    if state == "budget_low":
        return "暂停思考中，今日 AI 思考预算已用完（重置时间 00:00 UTC）"
    if state == "rejecting" and rejection_count_today > 0:
        return f"刚刚否决了交易提案，因为风险预算不够（今日已拒绝 {rejection_count_today} 次）"
    if state == "offline":
        return "等待下一輪掃描"

    recent = _safe_call(_safe_get(strategist, "get_recent_evaluations"), 1) or []
    if recent:
        last = recent[-1] if isinstance(recent[-1], dict) else None
        symbols = last.get("symbols") if last else None
        if isinstance(symbols, list) and symbols:
            symbol = str(symbols[0])
            symbol_short = symbol[:-4] if symbol.endswith("USDT") else symbol
            evaluation = last.get("evaluation") if isinstance(last, dict) else None
            confidence = (
                float(evaluation["confidence"])
                if isinstance(evaluation, dict)
                and isinstance(evaluation.get("confidence"), (int, float))
                else None
            )
            if confidence is not None and confidence > 0.0:
                return f"正在评估 {symbol_short} 信号，因为最近 {intent_count_today} 个交易意图（信心 {confidence:.2f}）"
            return f"正在评估 {symbol_short} 信号，等待更多市场证据"
    return "等待下一轮扫描"
```

### 3.3 statement_timeout per-cursor（agents_routes.py:251-260）
```python
def _set_statement_timeout(cur: Any) -> None:
    """Set statement_timeout=2s on this cursor's transaction / 設 2s 超時保護。

    SET LOCAL reverts at commit/rollback so the timeout never leaks to the
    next pooled request. SET LOCAL 在 commit/rollback 自動還原，不污染 pool。
    """
    cur.execute("SET LOCAL statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))
```

### 3.4 main.py 註冊（main.py:248-261）
```python
from .strategist_promote_routes import strategist_promote_router  # noqa: E402
app.include_router(strategist_promote_router)

# ── Agent Roster Router / Agent 追蹤視圖路由（Plan aa-nifty-walrus T1）──
# Read-only aggregator for the 5 runtime agents (Scout/Strategist/Guardian/
# Executor/Analyst). Backs the GUI Learning Cockpit "AI 团队工作台" sub-section.
# Composes Strategist `summary_zh` server-side so the GUI never templates raw
# JSON (UX A-grade contract per plan §"後端配合"). Pure read; no new SQL
# migration (uses V010 `(scope, time DESC)` index on `learning.ai_usage_log`).
# 只讀聚合 5 個 runtime Agent 給 Learning Cockpit "AI 团队工作台" 子分頁。
# Strategist summary_zh 後端組句（plan §"後端配合" UX A 級合約）；無新 SQL
# migration（沿用 V010 既有索引）。純讀，0 寫入面。
from .agents_routes import agents_router  # noqa: E402
app.include_router(agents_router)
```

---

## 4. 治理對照（CLAUDE.md / 規範）

| 規範 | 符合 | 說明 |
|---|---|---|
| §二 16 條根原則 #2（讀寫分離） | ✅ | 純讀，`grep -E ' INSERT \| UPDATE \| DELETE '` 命中 0 |
| §二 #6（失敗默認收縮） | ✅ | PG outage / singleton 缺失 → fail-closed 退到 0 / state="offline" / `degraded=true`；不 5xx |
| §七 跨平台 ★★ #1（路徑不硬編碼） | ✅ | 無 `/home/ncyu`、無 `/Users/[^/]+`；engine_mode 由 env var 讀 |
| §七 雙語注釋強制 | ✅ | MODULE_NOTE 中英對照、每個函數 docstring 中英並列、複雜邏輯 inline 雙語 |
| §七 SQL migration 規範 Guard A/B/C | N/A | 無新 migration |
| §七 被動等待 TODO 必附 healthcheck | N/A | 無被動等待 TODO |
| §九 800 行警告 / 1200 硬上限 | ✅ | agents_routes.py = 775 行（< 800 警告） |
| §九 Singleton 表登記 | ✅ | 無新 module-level singleton（agents_router 是 APIRouter 實例，與其他 router 同源） |
| Plan §"約束 1" 純讀 | ✅ | 0 寫入面 |
| Plan §"約束 2" SQL 走索引 | ✅ | V010 `(scope, time DESC)` 索引 + hypertable 自動 partition prune；無新 migration |
| Plan §"約束 3" 不顯示 H1-H5 raw | ✅ | 不讀 `h_state_snapshots`；`summary_zh` 不曝露 thought_gate raw（含 regression test `test_strategist_summary_zh_no_raw_json_leak`） |
| Plan §"約束 4" statement_timeout=2s | ✅ | 每個 cursor `SET LOCAL statement_timeout = 2000` |
| Plan §"約束 5" Mac 部署兼容 | ✅ | 全 env-derived 路徑；無 Linux-only `/var/lib/...` |
| Plan §"約束 6" 雙語注釋 | ✅ | bilingual-comment-style skill 全規格 |
| Plan §"約束 7" < 400 行 | ⚠️ | 775 行（超 spec），主因 5 個 card builder + 完整雙語 docstring；§九 800 行硬約束仍滿足。可拆 sibling 但會增 import 表面，本 wave 選擇單檔含 6 helper + 5 builder + 1 endpoint。 |

**強制工作鏈**：E1 → 待 **@E2 審查** → **@E4 回歸測試** → **@QA** → PM Sign-off → commit + push（E1 不直接 commit per CLAUDE.md §七）。

---

## 5. 不確定之處

### 5.1 PA spec 路徑 vs 現有 convention
- **Spec**：`app/routers/agents.py`（新建 `routers/` 子目錄）
- **實際**：`app/agents_routes.py`（flat，對齊 30+ 既有 route 檔）
- **理由**：codebase 100% flat 結構（`strategist_history_routes.py` / `executor_routes.py` / `ml_routes.py` / `paper_trading_routes.py`...），單獨為此一檔開 `routers/` 子目錄會造成不一致；E2 審查時若要求改名為 `routers/agents.py` 易於 rename。需 PM/PA 決定（**已標 scope 調整**）。

### 5.2 `_compose_summary_zh()` 位置
- **Spec**：「在 strategist_agent.py 或最自然的位置加 helper」
- **實際**：放在 `agents_routes.py`（API render layer）
- **理由**：strategist_agent.py 已 782 行（接近 §九 800 警告），加 ~30 行會觸線；helper 純為 API 渲染用，與 agent 內部邏輯解耦更清晰；future 若有第二個 caller 再抽到 `strategist_summary.py` sibling。

### 5.3 `agent_<role>` ai_usage_log scope 對應
- **現況**：`ai_budget_config` 只 seed 5 scope（`local_total / platform_hard_cap / agent_teacher / agent_analyst / agent_reserve`），與 5 個 Agent 中**只有 analyst** 對齊。
- **plan 已認可**：「先以 strategy_name 近似 role 對應，找不到對應就 0」
- **實作**：`_fetch_today_costs_by_role()` 用 `WHERE scope LIKE 'agent_%%'`，把回來的 row 按 `scope[len('agent_'):]` 切成 role；對映不上就 0；未來若新增 `agent_strategist` / `agent_guardian` / `agent_scout` / `agent_executor` scope 自動接上，**無 schema 變動**。
- **GUI 行為**：4 個 Agent 卡片 today_cost 顯示 $0.00（plan 認可）。

### 5.4 Heartbeat 計算只覆蓋 Strategist
- **現況**：只有 `StrategistAgent._eval_log` 帶 `timestamp_ms`，Scout / Guardian / Analyst 沒有逐條 freshness 時戳。
- **回退**：Scout 用 `state==RUNNING + intel_produced > 0` 判 active；Guardian 用 `verdict count` 判 frozen/tightening/guarding；Analyst 用 `trades_analyzed > 0` 判 reviewing/waiting。
- **影響**：plan §"Heartbeat 判定" 三色帶（< 1.5x / < 3x / ≥ 3x scan_interval）目前**僅對 Strategist 生效**；其他 4 個 Agent 走簡化二態（active/idle/offline）。E2 / 操作員若要求 4 個 Agent 都有逐條時戳，需在各 Agent 的 `_eval_log` / `_alert_log` / `_close_log` 暴露 `timestamp_ms`，本 wave 不做。

### 5.5 跨平台風險
- **無**：所有路徑都從 env / context manager / sys.modules 解析。Mac dev session（fastapi 未裝）無法本地執行 pytest，已透過 `python3 -c "ast.parse"` 驗證 3 檔語法 OK。

### 5.6 測試覆蓋判斷
- **8 個 unit test 涵蓋**：happy path / PG outage / singleton 缺失 / 4 種 summary_zh 模板（評估中 / 預算耗盡 / Executor offline / 無 JSON 洩漏）/ statement_timeout 常量 / grep 寫入面 = 0。
- **未覆蓋**：(a) Strategist `rejecting` state 模板（`rejected > produced * 2` 條件 + `rejection_count_today > 0` 文案）— plan 範例之一，建議 E4 補測；(b) `slow` heartbeat 邊界（lag 在 [1.5x, 3x) scan_interval）；(c) Guardian frozen 文案；(d) 大型 cursor result 集 fetchall() 不會 OOM（但 GROUP BY scope/strategy/verdict 限制 row 數 ≤30，實際無風險）。

---

## 6. Operator 下一步

### 6.1 審查重點
1. **@E2 審查**：(a) `agents_routes.py` 6 helper + 5 card builder + 1 endpoint 結構是否清晰可維護 (b) Strategist `_compose_summary_zh` 模板是否符合 plan §"動詞+對象+因為短句" (c) 確認 `grep -E 'INSERT|UPDATE|DELETE'` 唯三命中為 MODULE_NOTE 敘述（純讀契約） (d) 確認檔名 `agents_routes.py` vs spec 的 `routers/agents.py` —— 同意 flat 還是要改 (e) §七 雙語注釋全覆蓋
2. **@E4 回歸**：(a) `pytest test_agents_routes.py` 8 test 全綠 (b) 啟動 uvicorn → `curl /api/v1/agents/roster` smoke test，確認 200 + 5 cards (c) 既有 strategist_history / executor / scout 等 router 不受新 router 註冊影響（main.py 順序變動）
3. **@QA**：本任務無 Phase / Wave 等級重要性，可省

### 6.2 Mac CC 已透過 SSH bridge 做的驗證
- ❌ `cargo test`：本 wave 無 Rust 改動，跳過
- ❌ `psql`：本 wave 無新 migration，跳過
- ❌ `pytest`：Mac 端 fastapi 未裝；只跑 `python3 -c "ast.parse"` 驗 3 檔語法 OK
- ❌ engine log：無 runtime 改動

### 6.3 Linux 端 operator 需親自動手
- 無 high-risk 授權項；E2/E4 通過後 PM 統一 commit + push + Linux `git pull --ff-only`，無須 `--rebuild`（純 Python 加路由，uvicorn worker reload 即生效）。

### 6.4 後續工作（不在本 wave）
- T3（前端）：`tab-learning.html` Agent 追蹤視圖 sub-section + JS（其他 E1 並行做）
- Phase 2：`/api/v1/agents/cognitive/usage_summary` endpoint + pipeline_flow SVG 資料源
- 若 PA 堅持 `routers/agents.py` 路徑：`mv agents_routes.py routers/agents.py` + 加 `routers/__init__.py` + 改 main.py import 路徑

---

## 7. Skill 對照（bilingual-comment-style）

| 檢查項 | 結果 |
|---|---|
| MODULE_NOTE 模組目的（中 + 英對照） | ✅ |
| 每個新函數 docstring（中 + 英） | ✅ |
| inline 業務邏輯「為什麼」中文優先 | ✅ |
| 技術術語保持英文（asyncio / SET LOCAL / FastAPI / EMA） | ✅ |
| 不變量 / SAFETY 雙語 | ✅（`_set_statement_timeout` SET LOCAL 不變量雙語注釋） |
| TODO/FIXME 含中文上下文 | N/A（本檔無 TODO） |
| 反模式（純英文長段 / 純中文無技術詞 / 抽象「處理數據」） | 全避開 |
