# E1 Fix Report — G8-01 W3 Integration · E2 Return Fix · 2026-04-28

**Worktree**: `srv/.claude/worktrees/agent-a4d9d240343d85fff`
**Base HEAD on entry**: `571da6a` (W3 integration test commit on top of `cf34e96`)
**Branch**: `worktree-agent-a4d9d240343d85fff`
**Scope**: Test-only fix (3 of 4 findings: H-1, M-1, L-1; **L-2 informational, deliberately skipped per task spec**)

---

## 1. 任務摘要

E2 review (`a078efa`) 對 W3 integration commit `571da6a` RETURN to E1 with 1 HIGH + 1 MEDIUM + 1 LOW + 1 informational. PA dispatch instructed E1 to fix H-1 + M-1 + L-1, leave L-2 (fixture `_get_stats()` wrapper) for future. Production code untouched (test-only commit + test-only fix).

**核心 RCA（E2 揭）**: S5 `sys.modules["app.strategy_wiring"] = stub` workaround **從未真正生效**。Python `from PKG import SUB` semantic = `getattr(PKG, "SUB")` first（per CPython `_bootstrap._handle_fromlist`），不走 `sys.modules`。任一 sibling test 先 import 過 `app.strategy_wiring` → `app` package namespace 已綁 `strategy_wiring` 屬性到真實模組；後續 `sys.modules` 覆蓋對 `getattr(app, "strategy_wiring")` 0 影響。E2 Mac 同 session repro: 1 failed (S5) / 50 passed.

**完成狀態**: H-1 + M-1 + L-1 三項全修；隔離 8/8 + 同 session 51/51 + 全套 115/115 PASS。

---

## 2. 修改清單

| Path | 操作 | 行數變化 | 說明 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py` | 修改 | +52 / −22（淨 +30） | S5 改 importer-side patch（同時覆蓋 `sys.modules` + `app.strategy_wiring` 屬性）+ 嚴格等號 intel_received==3 唯一性 assertion；S3-B 改顯式 `tick_cognitive_modulator(agent)` 呼叫 + 新增隱式 hot-path sub-case |

僅 1 檔，純 test 修改，0 production diff。

---

## 3. 關鍵 diff

### H-1 + L-1: S5 importer-side patch + 唯一性 assertion

```python
# Before: sys.modules-only patch (broken when sibling imported strategy_wiring first)
sw_stub = type(sys)("app.strategy_wiring")
sw_stub.STRATEGIST_AGENT = agent
original_sw = sys.modules.get(sw_module_name)
sys.modules[sw_module_name] = sw_stub
# ...
self.assertGreaterEqual(strat_state["intel_received"], 3)  # false-positive on real singleton

# After: dual patch — sys.modules + parent package attribute
import app
sw_stub = type(sys)("app.strategy_wiring")
sw_stub.STRATEGIST_AGENT = agent

original_sw_in_modules = sys.modules.get(sw_module_name)
original_sw_attr_present = hasattr(app, "strategy_wiring")
original_sw_attr = getattr(app, "strategy_wiring", None)

sys.modules[sw_module_name] = sw_stub
app.strategy_wiring = sw_stub  # Critical: getattr(app, "strategy_wiring") now returns stub

try:
    with patch.dict(os.environ, {"OPENCLAW_H_STATE_GATEWAY": "1"}, clear=False):
        response = h_state_query_handler.build_h_state_full_response()
finally:
    # Restore in reverse order, handle "never bound before" case
    if original_sw_attr_present:
        app.strategy_wiring = original_sw_attr
    else:
        try:
            delattr(app, "strategy_wiring")
        except AttributeError:
            pass
    if original_sw_in_modules is None:
        sys.modules.pop(sw_module_name, None)
    else:
        sys.modules[sw_module_name] = original_sw_in_modules

# Strict equality: catches false-positive case where stub never took effect
self.assertEqual(
    strat_state["intel_received"], 3,
    "envelope must read test agent's intel_received (=3), not "
    "production singleton's; stub patching failed if this mismatches",
)
```

**Why dual patch**: 同時覆蓋兩條 lookup 路徑——
- `sys.modules["app.strategy_wiring"]`（當模組從未被 import 過時的初次 import path）
- `app.strategy_wiring` 屬性（已 import 過後 `from PKG import SUB` 的 getattr lookup）

E2 建議 (b) `unittest.mock.patch("app.h_state_query_handler.strategy_wiring", sw_stub)` 不可行——`_collect_h_snapshots` 內 `from . import strategy_wiring as _sw` 是函數局部變數每次呼叫時重綁定，patch 模組屬性無效。E2 建議 (a) 完整實作（雙 patch）為唯一保留 lazy-import 語意又 cross-session-stable 的選項。

### M-1: S3-B 顯式 tick 呼叫

```python
# Before: relied on _COGNITIVE_TICK_INTERVAL mod-N implicit trigger
for _ in range(_COGNITIVE_TICK_INTERVAL):
    agent._handle_intel(_make_intel_message())
self.assertGreaterEqual(bad.update.call_count, 1)

# After: explicit tick + decoupled assertion + extra implicit-path sub-case
try:
    tick_cognitive_modulator(agent)
except Exception as exc:
    self.fail(f"tick_cognitive_modulator surfaced modulator exception: {exc}")
self.assertEqual(bad.update.call_count, 1, "tick must attempt update exactly once")

# Sub-case: implicit hot-path still fail-soft (orchestration wiring proof, no count assertion)
bad.update.reset_mock()
for _ in range(_COGNITIVE_TICK_INTERVAL):
    try:
        agent._handle_intel(_make_intel_message())
    except Exception as exc:
        self.fail(f"_handle_intel surfaced modulator exception: {exc}")
self.assertEqual(agent._stats["intel_received"], _COGNITIVE_TICK_INTERVAL)
```

**Why**: W1 commit `aca7ee3` uses N=10 magic number；未來 PA RFC 改 N=0/None/非除數，舊測「投 N 個 intel → 必觸 ≥1 tick」假設會 silent 0-fire，`assertGreaterEqual(..., 1)` 會因錯誤理由 FAIL。顯式 `tick_cognitive_modulator(agent)` 解耦 assertion 與 interval magic；保留隱式 sub-case 仍涵蓋編排接線（不斷言 tick count）。

---

## 4. 治理對照

| 規範 | 對照結果 |
|---|---|
| CLAUDE.md §七 跨平台路徑（grep `/home/ncyu`/`/Users/[^/]+`） | ✅ 0 hit |
| CLAUDE.md §七 雙語注釋（MODULE_NOTE + docstring） | ✅ 修改處中英對照齊備（S5 patch rationale 段 + S3-B explicit-tick rationale 段） |
| CLAUDE.md §七 SQL migration Guard A/B/C | N/A（純 test） |
| CLAUDE.md §七 被動等待 healthcheck | N/A（純 test） |
| CLAUDE.md §九 文件大小 800/1200 | ✅ 653 < 800（原 623 + 30）|
| CLAUDE.md §九 Singleton 登記 | N/A（不增 singleton） |
| 原則 #6 失敗默認收縮 | ✅ S3-B fail-soft 路徑覆蓋強化（顯式 + 隱式雙覆蓋） |
| memory `feedback_no_dead_params` | ✅ S5 嚴格等號 assertion 防 false-positive 通過 |
| skill `bilingual-comment-style` MODULE_NOTE | ✅ 修改的兩段 rationale 注釋皆中英對照 + 引 E2 finding ID + E1 fix date |
| memory `feedback_workflow_audit_chain` | ✅ E1 → E2 → E4 → QA → PM 鏈執行中（E1 修完，等 E2 retest） |

---

## 5. 不確定之處

1. **fastapi 在 worktree venv 是否已安裝**：本 fix 使 S5 不再依賴 `app.strategy_wiring` 真實匯入是否成功，patch 後雙條 lookup 路徑都指向 stub，理論上 fastapi 不存在亦可通過。Mac 實測通過。Linux 端理論上同樣（fastapi 已在 trade-core 環境）。
2. **L-2（fixture `_get_stats()` 包裝）刻意不修**：per task spec「不處理 L-2 — informational only」。後續若 §九「私有屬性穿透」黃線升 hard rule，可獨立 ticket 處理（影響 S1/S6/S7 三個 case 約 5 處 `agent._stats["..."]`）。
3. **跨平台**：dual patch 對 Linux/Mac 行為一致（純 Python 標準語意），無平台特定 risk。

---

## 6. Operator 下一步

### 已完成驗證（Mac，本 worktree venv `srv/venvs/mac_dev/bin/python3`）

```bash
cd /Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a4d9d240343d85fff

# (1) 隔離跑 — 8/8 PASS
PYTHONPATH=. ../../../venvs/mac_dev/bin/python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py -v
# 結果：8 passed in 0.03s

# (2) E2 揭關鍵驗證 — 同 session 51/51 PASS（修前 1 failed）
PYTHONPATH=. ../../../venvs/mac_dev/bin/python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_phase2_strategy_routes_coverage.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py -v
# 結果：51 passed, 11 warnings in 0.28s

# (3) W1 + LOSSES regression — 14/14 PASS（W2 cognitive_modulator_coverage 不在本 worktree，per task spec 知悉）
PYTHONPATH=. ../../../venvs/mac_dev/bin/python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_w1_fix.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_g8_01_fup_losses_wiring.py -q
# 結果：14 passed in 0.03s

# (4) Strategist 套件 — 50/50 PASS
PYTHONPATH=. ../../../venvs/mac_dev/bin/python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_agent.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_audit_wiring.py -q
# 結果：50 passed, 5 warnings in 0.09s

# (5) 雙重保險：所有 6 檔同 session 跑 — 115/115 PASS（catch 任何跨檔污染）
PYTHONPATH=. ../../../venvs/mac_dev/bin/python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_phase2_strategy_routes_coverage.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_w1_fix.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_g8_01_fup_losses_wiring.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_agent.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_audit_wiring.py -q
# 結果：115 passed, 16 warnings in 0.37s
```

### 下一步

- **不需 commit**（worktree pattern 不自行 commit；本次 append 到 worktree HEAD `571da6a`，未 amend）
- 待 E2 retest（51/51 同 session 是 H-1 通過 KPI；strict equality intel_received==3 是 L-1 防偽通過 KPI）
- E2 PASS → E4 Linux full regression
- W2 cognitive_modulator_coverage 在另一 worktree；E4 整合時兩 worktree merge 後跑全套

### 高風險動作

無。純 test 修，`git diff cf34e96..HEAD -- ':!*tests*' ':!*reports*'` 預期空。

---

## ≤200 字 summary（給主會話）

H-1（S5 sys.modules patch 失效 Heisenbug）+ M-1（S3-B 隱式 tick 假設）+ L-1（S5 false-positive intel_received assertion）三項全修，僅 1 檔測試碼變更（+30 行淨）。S5 改用 `sys.modules` + `app.strategy_wiring` package attribute 雙 patch 同時 finally 反序還原，配嚴格等號 `intel_received==3` 唯一性 assertion；S3-B 改顯式 `tick_cognitive_modulator(agent)` 呼叫解耦 N magic number，並保留隱式 hot-path sub-case 仍驗 fail-soft 接線。Mac 驗證：隔離 8/8 + E2 關鍵驗證同 session 51/51 + W1+LOSSES 14/14 + Strategist 50/50 + 全 6 檔 115/115 全綠。L-2 informational fixture 包裝 per task spec 不修。0 production diff。
