# G8-01 認知自適應 e2e RFC — CognitiveModulator coverage + StrategistAgent integration

- **作者**：PA（Project Architect）
- **日期**：2026-04-27 CEST
- **HEAD**：`9e21a7f7`
- **狀態**：Plan only — 不寫實作代碼，純 design + E1 prompt template
- **改動風險評級**：**中**（純測試 + 1 production hot-fix；無 hard-boundary 觸碰）
- **依賴前置**（硬阻塞）：
  - G3-08 Phase 4 (`b67b0a8`) ✅ — H1-H5 + 5-Agent envelope `/api/v1/h_state/full` 10-bucket live
  - PM 2026-04-26 scope reframe ✅ — 從「OpportunityTracker / DreamEngine + 80+ cov」改為「**CognitiveModulator ≥85% line cov + StrategistAgent integration**」
- **解阻 後續**：
  - G3-09 cost_edge_advisor cross-agent 訂閱（與 5-Agent stats 相關性）
  - 未來 GUI 6-pane dashboard（H1-H5 + 5-Agent 同 IPC pull）

---

## §0 TL;DR — 200 字 summary

CognitiveModulator 確認 **live wired**（`strategy_wiring.py:404-415` 自動實例化注入 STRATEGIST_AGENT），但 grep 揭兩個阻塞性 bug：(1) `_apply_cognitive_modulation` + `strategist_edge_eval` 呼叫 `modulator.get_current_params()`，**該方法不存在**（modulator 只有 `get_all_params()`），try/except 靜默吞 → 永遠回 default；(2) `modulator.update(...)` **production code 0 caller**，permanent 卡在 base value（`confidence_floor=0.60`/`qty_ceiling=1.0`）。**結論：CognitiveModulator 邏輯 dead code**，違反 `feedback_no_dead_params`。E4 派發前必先派 E1 修這兩 bug（FIX-A method rename + FIX-B 新增 update tick），否則 ≥85% line cov 測的全是 dead branch。RFC 拆 3 工作組（FIX → unit cov → integration），E2 對抗審 + E4 雙端綠後 deliver。

---

## §1 Cognitive_Modulator live grep 證據（核心發現）

### 1.1 注入路徑 LIVE

```
strategy_wiring.py:407   from local_model_tools.cognitive_modulator import CognitiveModulator
strategy_wiring.py:408   _cognitive_modulator = CognitiveModulator()
strategy_wiring.py:409   STRATEGIST_AGENT.set_cognitive_modulator(_cognitive_modulator)
```

實例化 + 注入路徑無條件執行，每次 uvicorn boot 必跑。`STRATEGIST_AGENT` getter 正常回 truthy（`get_strategist_snapshot.cognitive_modulator_connected = 1`，per `strategist_agent.py:823`）。

### 1.2 兩個 BLOCKER bug（CognitiveModulator 邏輯 dead）

**BUG-A：method-name mismatch**
```python
# Real API (cognitive_modulator.py:186):
def get_all_params(self) -> dict[str, Any]:

# Caller 1 (strategist_cognitive.py:160):
params = agent._cognitive_modulator.get_current_params()   # AttributeError → silent except

# Caller 2 (strategist_edge_eval.py:191):
cog_params = agent._cognitive_modulator.get_current_params()  # AttributeError → silent except
```
兩 caller 皆裹 `try/except`（`strategist_cognitive.py:164-169` + `strategist_edge_eval.py:197`），AttributeError 被吞 → return defaults `(min_confidence, 1.0)`。Cognitive floor / qty ceiling **永不生效**。

**BUG-B：update() 永不被呼叫**
```bash
$ grep -rn "modulator.update\|cognitive_modulator.update" --include="*.py"
# 0 hits in production code
```
`CognitiveModulator.update(consecutive_losses, weekly_net_pnl, regret_data, dream_data)` 為唯一狀態演化入口，無 caller → modulator 永遠卡在 ctor base value：`confidence_floor=0.60`, `qty_ceiling=1.0`, `stoploss_mult=1.0`, `scan_interval=1800`, `update_count=0`。

**結論**：CognitiveModulator 形似 live，實則 fully dormant。違反根原則 #11 衍生準則「認知調製 ≠ 能力限制」與 `feedback_no_dead_params`「Agent 可調參數必須真實被發現/調整/持久化」。

### 1.3 風險評級

直接派 E4 寫「CognitiveModulator ≥85% line cov」測試 = 測試 dead code 的純粹數值覆蓋率，與 production 行為無耦合。**E2 必 reject**。**MUST-FIX-FIRST**：FIX-A + FIX-B，否則整個 G8-01 變偽合規。

---

## §2 Coverage 現況（baseline TBD by E4）

PA Mac-only env，未跑 pytest（per Mac dev-only 模式 §七 #2 ）。E4 在 Linux 跑 baseline 命令：

```bash
cd ~/BybitOpenClaw/srv && pytest \
  --cov=program_code/local_model_tools/cognitive_modulator \
  --cov-report=term-missing \
  -q
```

**預期 baseline**：~10-25% line cov（class skeleton 被 import 即執行 `__init__` lines；無任何 test 直接呼叫 `update()` / `_compute_*`）。E4 第一個 commit 的 PR 描述必附實測 baseline（Linux output）。

**目標**：≥85% line cov；branch cov 不強制（193 LOC 無複雜分支樹，line cov 達標時 branch ≥75%）。

---

## §3 設計：3 工作組 + 文件 plan

### 3.1 工作組 W1：FIX cognitive_modulator BUG-A + BUG-B（production 改動）

**Risk-A（method rename）**：兩個選項——
- **Option α（PA 推）**：caller 改 `get_current_params()` → `get_all_params()`（2 處：`strategist_cognitive.py:160` + `strategist_edge_eval.py:191`）。理由：modulator API 已有 `get_all_params`，rename caller 影響面小、無 schema 變動、E2 grep 易驗。
- Option β：modulator 加 `get_current_params` 為 `get_all_params` 的 alias。理由：caller 數可能擴張時 future-proof。**否決**：當前 caller 數 = 2，且 alias 同 SSOT 兩名稱違反 §九「禁止子模塊創建未登記的全局可變狀態」精神（雖非 singleton 但同類氣味）。

**Risk-B（新增 update tick）**：StrategistAgent 在何時呼 `update()`？三選項——
- **Option γ（PA 推）**：`StrategistAgent.handle_intel()` 入口加 lightweight tick — 從 `self._stats` 取 `consecutive_losses`/`weekly_net_pnl` proxy（參考既有 H4 caller-side stats pattern）+ `regret_data={}`/`dream_data={}` 傳 placeholder。pros：caller-side、符合 Phase 3 Sub-task 3-2 H4 pattern；cons：consecutive_losses / weekly_pnl 來源待設計。
- Option δ：新增 `cognitive_tick_scheduler` daemon thread（類比 `edge_estimator_scheduler` daemon，每 60s 跑一次 `update()`）。pros：與信號流解耦；cons：新 singleton 須登記 §九 + 加 healthcheck（per 被動等待規則）。
- Option ε：deferred — G8-01 暫不 land update tick，僅 FIX-A，update tick 開新 ticket G8-01-FUP-UPDATE-TICK。pros：最小 scope；cons：BUG-B 仍未解，dead code 風險仍在。

**PA 推薦**：**Option γ + 最小 stub source**。`consecutive_losses` 來源 = `_stats.get("consecutive_losses", 0)`（StrategistAgent 維護，由 ExecutorAgent fill-result event 推入，FUP 接線）；`weekly_net_pnl` 取 `cost_tracker.get_h5_snapshot().get("paper_net_pnl_7d", 0.0)`（已 live in H5）。Tick 頻率 = 每 N 個 intel 一次（如 N=10）避免熱路徑壓力。**FUP**：fill-result → consecutive_losses 反饋接線標 G8-01-FUP-LOSSES-WIRING（觀察 1w，若無 fill-result event 推入則 `consecutive_losses` 永 0，等價 deferred）。

**File plan**：
| 檔案 | 改動 | LOC | E2 必查 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_cognitive.py` | rename `get_current_params` → `get_all_params`（line 160）+ 新增 `tick_cognitive_modulator(agent)` helper（Option γ）| +30 / -1 | rename grep 0 殘留 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_edge_eval.py` | rename `get_current_params` → `get_all_params`（line 191）| +1 / -1 | 同上 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py` | `handle_intel()` 末尾每 N 次呼 `tick_cognitive_modulator(self)`（Option γ）| +5 / 0 | tick 不在熱路徑（intel 流量 ~5/min） |

### 3.2 工作組 W2：CognitiveModulator unit cov ≥85%

**File**：`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_cognitive_modulator_coverage.py`（新增）

**Mock 邊界**：CognitiveModulator 是 stateless pure Python（無 IO / 無 IPC / 無 thread）→ **零 mock**，全用真實 instance + 直接呼叫。

**Test scenario list（≥18 case，覆蓋 193 LOC）**：

| # | Scenario | 覆蓋的代碼路徑 |
|---|---|---|
| 1 | `__init__` defaults | 62-67 |
| 2 | `update()` empty inputs（None regret/dream） | 76-110 baseline |
| 3 | `update()` `consec_losses=0` + `weekly_pnl=0` → 全 base | _compute_confidence_floor pos=[] neg=[] |
| 4 | `update()` `consec_losses=3` → confidence floor +0.02 | _compute_confidence_floor 125-126 |
| 5 | `update()` `consec_losses=10` → cap at +0.10 (min 5×0.02) | 126 min(consec-2, 5) |
| 6 | `update()` `weekly_pnl<0` → confidence +0.02 | 128-129 |
| 7 | `update()` `regret.net_regret_direction='overtrading'` → conf +0.05 | 119-120 |
| 8 | `update()` `regret.net_regret_direction='undertrading'` → conf -0.03（無連虧） | 121-122 |
| 9 | `update()` `consec_losses=3` + `direction='undertrading'` → 連虧時忽略 neg ([R1-5]) | 132-133 |
| 10 | `update()` `qty_ceiling` `consec_losses=4` → -0.10 | 140-141 |
| 11 | `update()` `qty_ceiling` `consec_losses=3` + `weekly_pnl<0` → take min（worst） | 142-144 |
| 12 | `update()` `qty_ceiling` clamp at `_MIN_QTY_CEIL=0.3` | _clamp 50-51 + 145 |
| 13 | `update()` `dream_data` 含 `global.stoploss_multiplier=1.5` + `confidence=0.7` → blend | 147-155 |
| 14 | `update()` `dream_data.confidence=0.5` (≤0.6) → bypass，sl=base | 152 condition |
| 15 | `update()` `dream_data` 用 `_meta` fallback when no `global` | 149 dd.get("global", dd.get("_meta", {})) |
| 16 | `update()` `scan_interval` `weekly_pnl<0` → halve | 162-163 |
| 17 | `update()` `scan_interval` `direction='overtrading'` → 1.5x slow | 167-168 |
| 18 | `update()` `direction='undertrading'` + `weekly_pnl<0` → 兩 condition 取 min | 162+164-165 |
| 19 | EMA smoothing — 連 5 次相同 `update()` → 收斂到 target | 96/100/104/108 |
| 20 | clamp 上下限驗 — 極端值 → confidence ≤ 0.85, scan in [300, 3600] | _clamp + bounds |
| 21 | `get_all_params()` shape contract — 5 keys（含 update_count） | 186-193 |
| 22 | `get_*` getter rounding — confidence_floor 4 位 / qty_ceiling 4 位 / scan_interval int | 174-184 |

**Acceptance**：line cov ≥85% (193 LOC × 0.85 = 165 lines)；branch cov 報告但不強制。Mac + Linux 雙端跑同綠（PA 預期 100% 通過，因純 Python 無 platform-dep）。

### 3.3 工作組 W3：StrategistAgent integration（≥5 scenario）

**File**：`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py`（新增）

**Mock 邊界**（per E1 G3-04 模式）：
- **Mock**：`MessageBus`（in-memory dummy），`OllamaClient`（stub returning fixed `EdgeEvaluation`），`ExecutorAgent`（stub no-op consume），`Layer2CostTracker`（stub returning known H5 dict）
- **真實跑**：`StrategistAgent` + `CognitiveModulator` + `strategist_cognitive.set_cognitive_modulator` + `_apply_cognitive_modulation` + `tick_cognitive_modulator`（W1 新增）+ `handle_intel` 邏輯
- **目的**：確認 modulator policy logic 真執行 → 影響 `evaluations_rejected` 計數

**Test scenario list（≥5 case）**：

| # | Scenario | 設置 | 預期 outcome |
|---|---|---|---|
| 1 | **Threshold adapt → strategist consume** | inject modulator + tick `update(consec_losses=3, weekly_pnl=-100)` 驅 floor → 0.65；feed intel 觸發 evaluation 回 `confidence=0.62` | `_apply_cognitive_modulation` 回 floor=0.65 → confidence(0.62)<0.65 → `evaluations_rejected += 1` |
| 2 | **Scan_interval drift → recovery** | 連 5 tick `direction='overtrading'` → scan_interval 收斂到 ~2700s；改 `direction='balanced'` → 連 3 tick 收斂回 ~1800s | EMA 收斂行為 + `get_scan_interval_seconds()` 回 int |
| 3 | **Fault injection — modulator raise** | monkey-patch `modulator.get_all_params` 拋 RuntimeError → `_apply_cognitive_modulation` fallback default | `(config.min_confidence, 1.0)` 回傳 + warn log |
| 4 | **Cost spike override**（弱依賴 H5） | inject mock cost_tracker `get_h5_snapshot` 回 `paper_net_pnl_7d=-500`（強虧）→ tick 帶入 `weekly_pnl=-500` → conf floor +0.02 + qty_ceil -0.1 | snapshot stat reflect new floor; intent qty 限制 |
| 5 | **H1-H5 envelope round-trip via IPC mock** | env=`OPENCLAW_H_STATE_GATEWAY=1` + 真實 `STRATEGIST_AGENT` + tick 數次 → `build_h_state_full_response()` | response 含 `h_states.h4`, `agent_states.strategist.cognitive_modulator_connected=1`；tick 後 `intel_received` 增 |
| 6 | **CognitiveModulator state survives `set_cognitive_modulator` re-injection** | set_cognitive_modulator 用 new instance 覆蓋 → 舊 state 丟 | 新 modulator update_count=0 + agent log warn re-injection |
| 7 | **disabled mode parity** | `_cognitive_modulator = None` → `_apply_cognitive_modulation` 回 default | 回 `(config.min_confidence, 1.0)` |

**Acceptance**：≥5 case 全綠（PA 列 7 留 buffer）；測試獨立 — 各自 setUp 新 StrategistAgent + CognitiveModulator instance；無共享 state；雙端跑同綠。

### 3.4 工作組 W4（OPTIONAL）：H1-H5 envelope e2e

**File**：`program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_h_state_envelope_e2e.py`（**deferred**）

**理由**：`test_h_state_query_handler.py` 已有 90 case 含 `agent_states.strategist` populated/dropped/raise/include 過濾完整覆蓋。**W3 case #5** 已驗 envelope round-trip 在 strategist + cognitive_modulator 接線上下文。新增獨立 `_e2e.py` 屬冗餘。**deferred to G8-01-FUP-E2E（觀察）**，若 PM/E4 認為 round-trip 還需專測再開。

---

## §4 副作用識別清單（per profile.md §技術評估框架）

對每個 W1 改動問：

1. **其他模塊 import 此檔？**
   - `strategist_cognitive.py` — caller = `strategist_agent.py:102` 一處 ✅
   - `strategist_edge_eval.py` — caller = `strategist_agent.py:?` (lazy)；grep 確認 ✅
   - `cognitive_modulator.py` — caller = `strategy_wiring.py:407` 一處 ✅

2. **改動函數在哪些測試 mock？**
   - `_apply_cognitive_modulation` — `test_strategist_agent.py:1059` 等檢查 `cognitive_modulator_connected`，**不 mock 內部行為**，rename 安全
   - `set_cognitive_modulator` — 同上，僅檢查 setter 後 attr 非 None
   - 風險：W3 新增的 `tick_cognitive_modulator` 若被 `handle_intel` 呼叫，可能影響 `test_strategist_agent.py` 的 41 case 中 `intel_received_counter_increments` 等 → E4 必跑既有套件回歸

3. **asyncio/threading 邊界？**
   - `handle_intel` 由 MessageBus thread 呼叫（同步） → `tick_cognitive_modulator` 同步即可
   - `CognitiveModulator` 無 lock（pure compute）；多 thread 同時 update → race（罕見，後寫覆蓋 EMA）→ 若 healthcheck 顯示 inconsistency 開 FUP 加 lock
   - `_lock` 在 StrategistAgent — tick 不需取 `agent._lock`（modulator 自身 state）

4. **API response schema 變更？**
   - **無**。`get_strategist_snapshot.cognitive_modulator_connected` 已存在；W1 不新增 envelope field。
   - W3 case #5 驗 `h_state/full` 回 shape 仍是 Phase 4 既有 schema（`version:1`, `agent_states.strategist`)

5. **Rust ↔ Python IPC schema？**
   - **無**。CognitiveModulator 純 Python；不過 IPC；Rust h_state_cache 讀 `agent_states.strategist.*` 透過已 live 的 query_h_state_full handler，cognitive_modulator_connected 已是 i64（int(bool)）→ 對齊 Rust `AgentState.stats: HashMap<String, i64>`。

---

## §5 E1 派發計劃（最大並行）

**3 個 sub-agent，順序依賴 W1 → W2/W3 並行**：

```
[E1-Alpha]  W1 production fix（rename + tick）           1d
                ↓ commit → push
[E1-Beta]   W2 CognitiveModulator unit cov 22 case      1d
[E1-Gamma]  W3 Strategist integration 7 case            1.5d   並行
                ↓
[E2]        cross-review（grep 無 get_current_params 殘留 + W3 不 break 既有 41 case） 0.5d
[E4]        Linux 跑 cov + integration 雙端綠 + acceptance metric  0.5d
[QA]        最終確認                                     0.5d
```

**Total ETA：3-3.5d wall-clock**（Beta + Gamma 並行省 1d，符合原 spec 2-3d 估算）。

**Hard pre-condition**：W1 必先 land + push + `restart_all.sh --rebuild`（因 strategy_wiring.py 改 → uvicorn worker 4 個皆 reload）。**E1-Beta 與 W1 不衝突檔**（Beta 只新增 test 檔），可並行；**E1-Gamma 改 strategist_agent.py 觸發點**，與 W1 同檔 → 必順序（W1 → Gamma）。

---

## §6 高風險警告（E2 必重點審查 3 點）

1. **GREP 無殘留 `get_current_params`** — 全 repo 任何字串（含 docs / comment）。E2 跑 `grep -rn "get_current_params" --include="*.py"` 必 0 hit；命中 = REJECT。

2. **既有 `test_strategist_agent.py` 41 case 全綠不 regression** — `tick_cognitive_modulator` 新增可能改 `intel_received` / `intel_evaluated` 統計時序。E4 必跑 `pytest tests/test_strategist_agent.py -q` 確認 41 case 全綠（非 41+1）。

3. **CognitiveModulator state 不洩漏跨 test** — 若 `STRATEGIST_AGENT` 是 module-level singleton（per `strategy_wiring.py`），test 之間 modulator state 累積會破壞 W3 各 case 獨立性。E2 必查 W3 setUp 是否 `_reset_for_tests()` 或重建 instance。**fallback**：若 singleton 不可重置，W3 改用 `monkeypatch` 替換 `agent._cognitive_modulator` 為 fresh instance。

---

## §7 16 條根原則合規性（per skill 16-root-principles-checklist）

| # | 原則 | 本 RFC 影響 | 合規性 |
|---|---|---|---|
| 1 | 單一寫入口 | 無觸碰 IntentProcessor | ✅ |
| 3 | AI 輸出 ≠ 即時命令 | CognitiveModulator 是 L0 確定性 modulation，不繞 Decision Lease | ✅ |
| 4 | 策略不繞風控 | modulator 只能讓 confidence floor **更高**（更保守）→ 永不放寬 Guardian 邊界 | ✅ |
| 5 | 生存>利潤 | qty_ceiling 只能下調（_BASE=1.0, MAX=1.0）→ 永不超倉 | ✅ |
| 6 | 失敗默認收縮 | modulator raise → fallback default `(min_confidence, 1.0)`：保守值 | ✅ |
| 11 | Agent 最大自主 | **修復後**才符合「認知調製 ≠ 能力限制」衍生準則；當前 dead code 違反 | ⚠️ → ✅ post-W1 |
| 14 | 零外部成本可運行 | CognitiveModulator 純 L0 Python，無 LLM call | ✅ |

**硬邊界**：本 RFC **零觸碰** `live_execution_allowed` / `max_retries` / `system_mode` / `decision_lease_emitted`。grep 確認：
```bash
$ grep -nE 'live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved' \
    program_code/local_model_tools/cognitive_modulator.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_cognitive.py
# 0 hits
```

---

## §8 namespace 釐清（per profile.md 風險 5）

PA 確認**無 namespace confusion**：
- `local_model_tools/cognitive_modulator.py` — class `CognitiveModulator`，193 LOC，L0 modulation logic
- `control_api_v1/app/strategist_cognitive.py` — sibling 169 LOC，**4 個 helper function**（`handle_fast_channel` / `clear_emergency_mode` / `set_cognitive_modulator` / `_apply_cognitive_modulation`），無 class
- 兩者語意分離 — `strategist_cognitive` 是 StrategistAgent 拆檔（per Phase 4 split），承載「fast channel + cognitive integration」glue logic；`cognitive_modulator` 是 modulator class 本體。E1 / E2 / E4 不會混淆。

---

## §9 完成 checklist（PM Sign-off 前）

- [ ] W1 commit + push（rename + tick）
- [ ] W2 commit + push（unit cov ≥85% Linux 實測 number 附 PR）
- [ ] W3 commit + push（≥5 case，PA 列 7 留 buffer）
- [ ] E2 grep `get_current_params` = 0 hit
- [ ] E4 Linux: `pytest test_strategist_agent.py` 41/41 + `test_cognitive_modulator_coverage.py` 22/22 + `test_strategist_cognitive_integration.py` 7/7 全綠
- [ ] E4 Mac: 同三檔同綠（per `feedback_cross_platform`）
- [ ] coverage report 入 PR description
- [ ] healthcheck check 不需新增（modulator 非「被動等待 Nd」類 TODO）
- [ ] memory append（PA + E4 + PM 三 agent）

---

## §10 Operator 檢視重點

1. **W1 Option γ 認可？** — `tick_cognitive_modulator` 在 `handle_intel` 每 N=10 次調用 1 次。N 過小可能熱路徑壓力，過大則 modulator state 過時。PA 推薦 N=10（intel 流 ~5/min → 每 2min 一次 update，符合 modulator 用途）。
2. **Risk-B Option ε（deferred update tick）vs γ（land update tick now）取捨** — 若 operator 偏好最小 scope，可選 ε，G8-01 純改名修 BUG-A，BUG-B 開新 ticket。**PA 建議 γ**：BUG-A + B 同源（`get_current_params` 不存在 + 無 caller 即「整鏈未通」），同次修一致性最高。

---

## §11 Self-contained E1 prompt template（給 E4 / E1 派發）

```
G8-01 認知自適應 e2e — CognitiveModulator coverage + StrategistAgent integration

依 PA RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md`
落地 W1 + W2 + W3。**3 個 sub-agent 分工**（W1 順序在前，W2 + W3 並行）：

──────────────────────────────────────────────────
【E1-Alpha】W1 production fix（必先 land）
──────────────────────────────────────────────────

修兩個 BLOCKER bug：

**FIX-A method-name rename**：
- `strategist_cognitive.py:160`: `get_current_params()` → `get_all_params()`
- `strategist_edge_eval.py:191`: `get_current_params()` → `get_all_params()`
- 全 repo grep `get_current_params` 須 0 殘留（含 comment / doc）

**FIX-B 新增 update tick**（Option γ）：
- `strategist_cognitive.py` 新增函數 `tick_cognitive_modulator(agent: "StrategistAgent") -> None`：
  - 從 `agent._stats.get("consecutive_losses", 0)` 取 consec_losses
  - 從 `agent.cost_tracker.get_h5_snapshot().get("paper_net_pnl_7d", 0.0)` 取 weekly_pnl（cost_tracker 可能 None → fallback 0.0）
  - 呼 `agent._cognitive_modulator.update(consecutive_losses=..., weekly_net_pnl=..., regret_data={}, dream_data={})`
  - 整體裹 try/except + warn log（fail-closed 原則 #6）
- `strategist_agent.py` `handle_intel()` 末尾加每 N=10 次呼叫 `tick_cognitive_modulator(self)`：
  - counter = `self._stats.get("intel_received", 0)`，若 `counter % 10 == 0` 則 tick
  - 雙語注釋

**驗收**：
- 既有 `tests/test_strategist_agent.py` 41 case 全綠（非 41+1）
- Mac + Linux 雙端 commit + push
- PR 附 grep `get_current_params` 0 結果

──────────────────────────────────────────────────
【E1-Beta】W2 CognitiveModulator unit cov ≥85%（與 W3 並行）
──────────────────────────────────────────────────

新增 `tests/test_cognitive_modulator_coverage.py`，依 RFC §3.2 列 22 個 scenario
（覆蓋 _compute_confidence_floor / _compute_qty_ceiling / _compute_stoploss_mult /
_compute_scan_interval / EMA / clamp / getter / shape contract）。

**Mock 策略**：零 mock，CognitiveModulator pure Python instance + 直接呼叫。

**驗收**：
- Linux baseline coverage 數字（pre-commit 跑一次）附 PR description
- Linux post-commit `pytest --cov=program_code/local_model_tools/cognitive_modulator
  --cov-report=term-missing -q test_cognitive_modulator_coverage.py` ≥85% line cov
- Mac 同套件全綠（純 Python 預期 100% 通過）
- 22 case 全綠

──────────────────────────────────────────────────
【E1-Gamma】W3 StrategistAgent integration ≥5 scenario（W1 完成後 land）
──────────────────────────────────────────────────

新增 `tests/test_strategist_cognitive_integration.py`，依 RFC §3.3 列 7 個 scenario
（threshold adapt / scan_interval drift / fault injection / cost spike / envelope
round-trip / re-injection / disabled mode parity）。

**Mock 邊界**（per E1 G3-04 模式）：
- Mock：MessageBus / OllamaClient / ExecutorAgent / Layer2CostTracker
- Real：StrategistAgent + CognitiveModulator + strategist_cognitive helpers + tick

**Test 獨立性**：每 case setUp 重建 StrategistAgent + CognitiveModulator
instance，禁共享 module-level singleton state。若 STRATEGIST_AGENT 是 singleton，
用 monkeypatch 替換 `agent._cognitive_modulator` 為 fresh instance。

**驗收**：
- ≥5 case 全綠（RFC 列 7 留 buffer）
- 既有 41 case + W2 22 case 不 regression
- Mac + Linux 雙端綠

──────────────────────────────────────────────────
【E2】cross-review（W1+W2+W3 三 PR merge 前）
──────────────────────────────────────────────────

1. **grep `get_current_params` 全 repo 0 hit**（命中 = REJECT）
2. **既有 41 case 全綠**（W1 tick 不 regression）
3. **W3 case #5 envelope round-trip 真跑**（mock 不掩蓋實邏輯）
4. **副作用清單 §4 五項全綠**
5. **16 條根原則 #4 / #5 / #11 合規**（modulator 只能更保守，不放寬 Guardian）

──────────────────────────────────────────────────
【E4】Linux + Mac 雙端最終驗收
──────────────────────────────────────────────────

跑：
```bash
# Linux （ssh trade-core）
cd ~/BybitOpenClaw/srv && pytest \
  tests/test_strategist_agent.py \
  tests/test_cognitive_modulator_coverage.py \
  tests/test_strategist_cognitive_integration.py \
  --cov=program_code/local_model_tools/cognitive_modulator \
  --cov=program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_cognitive \
  --cov-report=term-missing -v

# Mac
（同上，但跳過需 OPENCLAW_TEST_PG 的 case）
```

acceptance：
- 41+22+7 = 70 case 全綠雙端
- cognitive_modulator line cov ≥85%
- 0 production diff outside W1 file plan
- E2 grep clean

──────────────────────────────────────────────────
【PM Sign-off】

完成 checklist §9 全 ✅ → PM 簽核。

══════════════════════════════════════════════════
依賴：本 prompt + RFC + memory `feedback_no_dead_params` + `feedback_cross_platform` +
      `feedback_workflow_audit_chain` + `feedback_subagent_first`
ETA：3-3.5d wall-clock（W1 1d → W2/W3 並行 1.5d → E2/E4/QA 1d）
═══════════════════════════════════════════════════════════════════════
```

---

## §12 報告路徑

`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md`

**結論性發現**：CognitiveModulator live wired 但邏輯 dead（BUG-A method-name + BUG-B 無 caller）。RFC 拆 W1 production fix → W2/W3 並行測試的三工作組 plan，3-3.5d wall-clock。E1 prompt template §11 self-contained 可直接派發 E4。
