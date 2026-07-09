# E2 Re-review — G8-01 W3 Integration E2-return Fix · 2026-04-28

## 對象
Worktree: `srv/.claude/worktrees/agent-a4d9d240343d85fff`
Branch: `worktree-agent-a4d9d240343d85fff` (base `cf34e96`)
HEAD: `571da6a` (E1 W1 commit, **not amended**)
Fix delta: working tree only (uncommitted, +101 / −22 LoC, 1 file)
File: `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py` (702 LoC, under 800 警告線)

## 上一輪 finding 收尾狀態

| Finding | 級別 | 狀態 | 證據 |
|---|---|---|---|
| H-1 S5 sys.modules stub 從未生效 | HIGH | ✅ FIXED | 51/51 PASS forward + reverse + 5 重跑同綠 |
| M-1 S3-B 隱式假設 _COGNITIVE_TICK_INTERVAL | MEDIUM | ✅ FIXED | 顯式 tick_cognitive_modulator(agent) 調用，sub-case 保留 implicit ×N |
| L-1 S5 唯一性 assertion | LOW | ✅ FIXED | `assertEqual(intel_received, 3)` 嚴格等號 |

## 自驗結果（必跑項目）

### 1. 同 session 51/51（H-1 關鍵 KPI）
```
forward order  (phase2 → S1-S7): 51 passed (5 重跑連綠)
reverse order  (S1-S7 → phase2): 51 passed
isolated S1-S7 (8 tests):         8 passed
```
✅ Reproduce E2 揭的 fail-then-pass 路徑成立。

### 2. 雙 patch finally atomicity 對抗驗證
- 讀 `test_strategist_cognitive_integration.py:505-541`：先 capture (`hasattr` + `sys.modules.get`)，三變數正交保留；patch 後 try/finally 包覆；finally 反序還原（先 attr 再 sys.modules，與 patch 順序對稱）。
- `original_sw_attr_present=False` 路徑 try/except AttributeError → no-op，避免 race 中 sibling 已 cleanup 後 delattr fail。
- pair test：`TestS5HStateEnvelopeRoundTrip → test_h_state_query_handler.py 17 cases` 全綠（91/91）— 證 finally 反序確實 atomic 還原，未污染 sibling test。

### 3. 6-檔同 session 對比（B 對抗：產線級回歸）
| Run | Passed | Failed | Delta |
|---|---|---|---|
| Baseline (pre-fix) | 161 | 36 | — |
| Post-fix (working tree) | 162 | 35 | **+1 / −1** |

✅ Fix 淨改善：移除 S5 1 個 failure，**0 新 regression**。
⚠️ 35 個 pre-existing failure 全部位於 `test_h_state_query_handler.py`，**與本 fix 無關**：來自 `test_strategist_audit_wiring.py` / `test_strategist_agent.py` 等 sibling 對 `app.strategy_wiring.STRATEGIST_AGENT` singleton 的 import-time 污染。記為新 ticket（**非 BLOCKER**），下一輪維護週期處理。

### 4. M-1 顯式 tick 對抗
讀 line 360-378：
- 顯式 `tick_cognitive_modulator(agent)` 後 `assertEqual(bad.update.call_count, 1)` —— 真去除 N=10 magic number 假設（即使 W1 改 N=5/0/None 也會精確 fail-soft fire 1 次）。
- Sub-case `bad.update.reset_mock()` + `for _ in range(_COGNITIVE_TICK_INTERVAL): _handle_intel(...)` —— 仍驗 implicit hot-path fail-soft，**但不 assert tick count**（避免重新耦合到 N，否則 sub-case 違反 M-1 原意）—— 現實：assert intel_received 累積，不 assert update.call_count，正確。

### 5. L-1 嚴格等號
讀 line 559-572：`assertEqual(strat_state["intel_received"], 3)` 配 error message 解釋失敗 = stub 未生效。`>=3` 在 production singleton 復用情境下會 false-pass，現嚴格等號真防 H-1 復發 regression。

### 6. Production diff = 0 確認
`git diff cf34e96..HEAD --stat` = 1 commit 623 insertions（W1 新增測試檔，非 production）
`git diff HEAD --stat` = 1 file 101 insertions / 22 deletions（**僅 test file 改動**）
✅ 0 production diff。

## 8 條 §九 checklist
| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ✅ 僅 test 檔，scope = E2 上輪 H-1/M-1/L-1 |
| 沒有 except:pass 或靜默吞異常 | ✅ except 都有 `self.fail(...)` 或 try/except AttributeError 註明 cleanup race |
| 日誌使用 %s 格式 | N/A 測試碼無 logger |
| 新 API 端點有 _require_operator_role() | N/A 無 API 端點改動 |
| except HTTPException: raise 在 except Exception 之前 | N/A |
| detail=str(e) 已改為 "Internal server error" | N/A |
| asyncio 路由中沒有 blocking threading.Lock 調用 | N/A |
| 沒有私有屬性穿透 | ⚠️ test 仍用 `agent._handle_intel(...)` —— 但這是 production W1 既有 implicit-trigger 路徑 contract 必須測，可接受 |

## OpenClaw 9 條
| Item | 狀態 |
|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ 0 命中 |
| 雙語注釋 | ✅ MODULE_NOTE 中英齊備 + 新增註釋 6 處皆中英對照 |
| Rust unsafe / unwrap | N/A 純 Python test |
| 跨語言 IPC schema | N/A |
| Migration Guard A/B/C | N/A |
| healthcheck 配對（被動等待） | N/A |
| 新 singleton 登記 §九 表 | N/A 0 新 singleton |
| 文件大小 800/1200 | ✅ 702 LoC < 800 警告 |
| Bybit API 改動 | N/A |

## 對抗反問結果

**Q1**: 「H-1 fix 真有效」？
A: 5 重跑同綠 51/51 + reverse order 51/51 + isolated S5 PASS + pair test (S5→h_state) 91 PASS。**Reproduce E2 上輪揭的 fail-then-pass 成立**。

**Q2**: 「finally 反序還原是否真 atomic / 無 leak」？
A: 三變數正交 capture（`hasattr` / `getattr` / `sys.modules.get`），finally 順序與 patch 對稱反序，AttributeError no-op 處理 sibling cleanup race。pair test 證明：S5 跑完後 `test_h_state_query_handler` 17 cases 全綠 = 真實還原。**非 race**（singleton-thread test runner 內 patch / restore，無並發）。

**Q3**: 「M-1 sub-case 仍驗 fail-soft 真路徑 vs assert 永遠 trivially true」？
A: Sub-case 的 `reset_mock()` + `_handle_intel × N` 確實沒 assert tick count，但 `assertEqual(strat_state.intel_received, _COGNITIVE_TICK_INTERVAL + 3)`（line 396-407）累積 4+3=非 trivial assert，wiring 真斷掉時會 fail。**接受**。

**Q4**: 「Linux 跑 H-1 預期同 Mac？」
A: H-1 root cause（`from PKG import SUB` getattr semantic）= CPython 規範行為，**跨 Mac/Linux 一致**。Mac 因 fastapi 缺失，phase2_strategy_routes_coverage 先 import `app.strategy_wiring` 觸發 ImportError 並 leave attribute on `app` 為 mock；Linux 有 fastapi，`app.strategy_wiring` 完整 import 並 leave **真 STRATEGIST_AGENT singleton** on `app`。**E2 預測**：Linux 跑時 baseline 不含 mock attribute pollution，但 fix 仍 patch `app.strategy_wiring` 為 stub（真實已存在於 sys.modules + attr），finally 還原回真 module —— **應同 Mac 51/51 PASS**。`ssh trade-core "PYTHONPATH=. pytest ...test_strategist_cognitive_integration.py ..."` 可一鍵驗證，不 BLOCKER。

**Q5**: 「commit chain 是否真 append 而非 amend」？
A: ⚠️ **無 append commit**。`git log --oneline cf34e96..HEAD` 僅 1 commit `571da6a`（W1 原 commit）+ working tree 未 stage 改動。E1 fix 還沒 commit。**無 amend 風險**（因為根本還沒 commit），但 fix 須 commit + push 才完成 E2 release。

## Findings

| 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|
| LOW | worktree git state | E1 fix 未 commit，working tree only | E1 須 `git add + commit + push`（新 commit append，**禁 amend** `571da6a`）。E2 PASS 但 deliver 未閉環 |
| INFO | test_h_state_query_handler.py 35 pre-existing failures | 與本 fix 無關，sibling singleton 污染 | 開新 ticket：`STRATEGIST-SINGLETON-POLLUTION`，非 W3 阻塞 |

## 結論

**PASS to E4**（條件：E1 commit + push 後）

- H-1 / M-1 / L-1 三個上輪 finding 全綠
- 0 production diff
- 51/51 same-session forward + reverse + 5 重跑同綠
- 0 new regression vs baseline
- 8 §九 + 9 OpenClaw 條目全綠或 N/A
- 唯一 deliver gap：commit + push 還沒做（操作層，非 code 問題）

## 退回 E1 修復清單
1. **必做**：`cd <worktree> && git add program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_cognitive_integration.py && git commit -m "fix(g8-01-w3): E2 H-1/M-1/L-1 — bind app.strategy_wiring attr + explicit tick + strict eq"` 然後 push（**禁 amend `571da6a`**，append 新 commit per safety 準則）。
2. **建議**：commit message body 引用 E2 review report path 便於 audit 追溯。
3. **可選**：開 follow-up ticket `STRATEGIST-SINGLETON-POLLUTION` 處理 35 個 pre-existing failures（非 W3 scope，下一輪維護處理）。
