# E2 Adversarial Review — G8-01 W3 Integration · 2026-04-28

**Target**: `571da6a` worktree-agent-a4d9d240343d85fff (test-only commit, +623 LOC)
**File**: `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py`
**Verdict**: **RETURN to E1** (1 HIGH + 1 MEDIUM)

## 改動範圍

- 1 new test file, 623 行 (under 800 警告線)
- 0 production diff（`git diff cf34e96..571da6a -- ':!*tests*'` 空）
- 8 test methods 覆蓋 7 scenarios（S1, S2, S3 ×2, S4, S5, S6, S7）

## 8 條 §九 Checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ✅ |
| 沒有 except:pass | ✅ |
| 日誌 %s 格式 | ✅ (test 無生產 logger 寫入) |
| _require_operator_role | N/A |
| HTTPException raise 順序 | N/A |
| detail=str(e) 改 generic | N/A |
| asyncio + threading.Lock | N/A |
| 私有屬性穿透 ._xxx | ⚠️ S1/S5/S6/S7 讀 `agent._stats` — 測試合理可接受 |

## OpenClaw 9 條 Checklist

| Item | 狀態 |
|---|---|
| 跨平台 path（grep `/home/ncyu`/`/Users/[^/]+`） | ✅ 0 hit |
| 雙語注釋（MODULE_NOTE + docstring） | ✅ 完整 |
| Rust unsafe / unwrap | N/A (Python only) |
| IPC schema | N/A |
| Migration Guard A/B/C | N/A |
| Healthcheck 配對 | N/A |
| Singleton 登記 §九 表 | N/A (test 不增 singleton) |
| 文件大小 | ✅ 623 < 800 |
| Bybit API 改動 | N/A |

## 對抗反問結果

### Q1：7 scenario 是真 end-to-end integration 還是 unit-level 偽 integration？

**A**：S1/S2/S4/S6 真走 `record_trade_outcome`→tick→modulator EMA→getter 全鏈；S3 真驗 fail-soft；S7 真整合 5 步。**S5 號稱 envelope round-trip 但實質失敗**（見 H-1）。

### Q2：sys.modules stub 在 Linux 真 fastapi 環境會被覆蓋？

**A**：**更糟，stub 從未真正生效**（無論 Mac 或 Linux）。詳 H-1。

### Q3：REGRET/DREAM 0 hit 驗證？

**A**：✅ `grep -E "regret_data|dream_data"` 僅命中文檔註釋（line 22, 50），無 production hot-path 實調用。

### Q4：`patch.object(sw)` 反模式 0 hit？

**A**：✅ 0 hit。

### Q5：W2 26 sub-tests 重疊？

**A**：W2 套件未 land，無法 cross-check。W3 7 scenarios 走 hot-path orchestration（`_handle_intel` + `record_trade_outcome` + envelope），與 unit cov 設計上分工明確。

### Q6：S3 fail-soft 真驗 production try/except？

**A**：✅ 兩個 sub-case 一個 raise `get_all_params`、一個 raise `update`，分別命中 `_apply_cognitive_modulation` (line 159 try/except) 與 `tick_cognitive_modulator` (line 236 try/except)。fail-soft 真生效。

## Findings

### H-1 [HIGH] S5 sys.modules stub 因 Python import 屬性快取而失效（test order-dependent Heisenbug）

**位置**：`test_strategist_cognitive_integration.py:456-475` (TestS5HStateEnvelopeRoundTrip)

**根因**：S5 用 `sys.modules["app.strategy_wiring"] = sw_stub` 嘗試替換 strategy_wiring，但 `h_state_query_handler.py:334 / 472` 是 `from . import strategy_wiring as _sw`。

Python 對 `from PKG import SUBMOD` 的 semantic：先 `import PKG`，再 `getattr(PKG, "SUBMOD")`。若 `app.strategy_wiring` 此前已被任何其他測試（如 `test_phase2_strategy_routes_coverage.py:422 from app.strategy_wiring import phase2_router`）import 過，**`app` package 的 namespace 會把 `strategy_wiring` 屬性綁定到原始（real）module object**。S5 後續對 `sys.modules` 的覆蓋**完全不影響** `getattr(app, "strategy_wiring")` 的結果。

**實測驗證**（Mac，相同 worktree）：
```
$ pytest test_phase2_strategy_routes_coverage.py test_strategist_cognitive_integration.py
1 failed, 50 passed
FAILED ...TestS5HStateEnvelopeRoundTrip::test_envelope_includes_strategist_with_modulator_connected
       AssertionError: 0 not greater than or equal to 3   # intel_received expected 3 (test agent), got 0 (real production singleton)
```
- 隔離跑 S5 → PASS（`from app import strategy_wiring as _sw` 觸發首次 import，sys.modules 覆蓋生效）
- 與任何先 import 過 strategy_wiring 的 sibling test 同 session 跑 → S5 FAIL
- Linux full regression（test 收集字典序、phase2_strategy_routes 在 strategist_cognitive_integration 之前載入）會穩定觸發

**附帶設計缺陷**：`assertEqual(strat_state["cognitive_modulator_connected"], 1)` 在 fail order 下**意外通過**——因為 production STRATEGIST_AGENT 也已綁 modulator（strategy_wiring init 時注入）。這意味測試「綠」時也只是 false-positive，沒有真正驗證 envelope reads test agent。

**建議修法**（任選一）：
- (a) `sys.modules` 覆蓋同時 `setattr(app, "strategy_wiring", sw_stub)` + try/finally restore；
- (b) 用 `unittest.mock.patch("app.h_state_query_handler.strategy_wiring", sw_stub)`（patch 在 importer 命名空間）—— 更乾淨；
- (c) 用 `unittest.mock.patch.dict(sys.modules, {...})` + 同步 `del sys.modules`/`importlib.reload(app)` 強制重載；
- (d) 改用真實 strategy_wiring + `monkeypatch.setattr(strategy_wiring, "STRATEGIST_AGENT", agent)`（Mac fastapi gap 走 (b) 即可，無需碰 fastapi）。

(b) 最簡潔：直接 patch importer 看到的綁定。

### M-1 [MEDIUM] S3 update raise sub-case 未 setUp/tearDown 清掃 cognitive_modulator 狀態

**位置**：`test_strategist_cognitive_integration.py:339-367`

**問題**：`test_tick_modulator_update_raises_does_not_poison_hot_path` setUp 內建 fresh agent + bad mock；但 `_handle_intel` 內 `_sc_tick_cognitive_modulator(self)` 只在 `_intel_count % _COGNITIVE_TICK_INTERVAL == 0` 觸發。若 `_COGNITIVE_TICK_INTERVAL=10`（typical），第 10 個 intel 才觸發 tick；前 9 個都不會 fire 任何 `bad.update`。

實測：8/8 PASS 表示在當前 `_COGNITIVE_TICK_INTERVAL` 值下走通了。但測試假設「投遞剛好 _COGNITIVE_TICK_INTERVAL 個 intel 必觸 ≥1 次 tick」**只在 N>=1 + integer divisible 下成立**。若未來 PA RFC 改 INTERVAL=0（debug 模式）或為 None，該迴圈會 0 fire，`assertGreaterEqual(bad.update.call_count, 1)` 會 fail；非 robust。

**建議**：直接 `tick_cognitive_modulator(agent)` 顯式呼叫 ≥1 次（不要走 `_handle_intel` 計數路徑）+ 額外 1 個 case 驗 `_handle_intel` 觸 tick 不 raise。

### L-1 [LOW] S5 `version=1` 斷言因 H 桶填充而 lucky-pass

**位置**：line 484 `self.assertEqual(response["version"], 1)`

`build_h_state_full_response` 升 version 條件 = `h_states or agent_states`。S5 stub 失敗時 agent_states 仍含 production singleton 的 strategist 條目（has cognitive_modulator），h_states 也來自 production cost_tracker；version=1 仍然成立。建議加 `self.assertIn("strategist", agent_states)` 之後 explicitly 驗 `strat_state is agent.get_strategist_snapshot()` 或某個唯一 marker（如 `agent._stats["intel_received"] == 3` 是已用斷言但被 H-1 暴露為 broken）。修 H-1 後此項自動 covered。

### L-2 [LOW informational] 私有 `agent._stats` 穿透與註釋規範

S1/S6/S7 多處讀 `agent._stats["consecutive_losses"]` / `agent._stats["intel_received"]`。測試合理但屬 §九 「私有屬性穿透」黃線。後續可考慮 fixture 內加 `_get_stats()` 公開包裝。Non-blocking。

## 7 scenario 真實 vs 偽 integration 評估

| Scenario | 真實覆蓋 | 偽 integration 風險 |
|---|---|---|
| S1 | ✅ losses → tick → EMA → reweight 全鏈 | 0 |
| S2 | ✅ tracker stub → tick → scan_interval EMA | 0 |
| S3-A | ✅ 真 fail-soft via `_apply_cognitive_modulation` except 分支 | 0 |
| S3-B | ⚠️ tick 觸發依賴 `_COGNITIVE_TICK_INTERVAL` 模 0；參數變動會脆 | 見 M-1 |
| S4 | ✅ H5 stub → tick → floor up + ceiling down | 0 |
| S5 | ❌ stub 不生效，實質測 production singleton 而非 test agent | **H-1** |
| S6 | ✅ LOSSES-WIRING → tick → modulator state | 0 |
| S7 | ✅ W1 + LOSSES + 5 steps integrated | 0 |

5/7 真 integration、1 脆性、1 broken。

## 結論

**RETURN to E1**：

修復清單：
1. **H-1 (must)**：S5 stub 改 `unittest.mock.patch("app.h_state_query_handler.strategy_wiring", sw_stub)` 或同等 importer-side patch；確保 `cd worktree && pytest test_phase2_strategy_routes_coverage.py test_strategist_cognitive_integration.py` 同 session 8/8 PASS
2. **M-1 (should)**：S3-B 改用 `tick_cognitive_modulator(agent)` 顯式呼叫，去除 `_COGNITIVE_TICK_INTERVAL` 隱式假設
3. **L-1 (nice)**：S5 加唯一性斷言（如 `agent._stats["intel_received"] == 3`，修 H-1 後自然帶上）
4. **L-2 (informational)**：考慮 fixture 公開 `_get_stats()` 包裝

修復後重派 E2 retest，全綠 → E4 regression。

## 驗證指令

```bash
cd /Users/ncyu/Projects/TradeBot/srv/.claude/worktrees/agent-a4d9d240343d85fff
PYTHONPATH=. /Users/ncyu/Projects/TradeBot/srv/venvs/mac_dev/bin/python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_phase2_strategy_routes_coverage.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py -v
# 修復前：1 failed, 50 passed
# 修復後預期：51 passed
```
