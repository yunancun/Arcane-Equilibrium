# E2 Adversarial Review — STRATEGIST-SINGLETON-POLLUTION P3 fix

**Date**: 2026-04-28 03:50 CEST (Mac dev session)
**Base HEAD**: `e2875da` (origin/main)
**Worktree**: main repo working tree (`/Users/ncyu/Projects/TradeBot/srv`, unstaged)
**E1 report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-28--strategist_singleton_pollution_fix.md`
**PA RFC**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategist_singleton_pollution_investigation.md`
**Verdict**: **PASS to E4 — APPROVE_WITH_NITS** (1 LOW informational, no blocker)

---

## 1. 改動範圍

```
M app/h_state_query_handler.py        (+49 / -16)  — Option B production fix
M tests/test_h_state_query_handler.py (+75 / -8)   — Option A test fixture defense
```

兩檔皆有大塊雙語注釋（占大部分 +line）。實際 logic 增量：handler 加 `import sys` + 兩處 4-line lookup pattern；test 加 sentinel + tuple return + parent-attr restore。Scope 與 PA RFC §7 Step 1+2 一致；PA 模板僅指 line 334 (`_collect_h_snapshots`) 一處，E1 自決加 line 495 (`_collect_agent_snapshots`) 同 sibling pattern — **驗證為合理 root-cause-driven extension**：

```
$ grep -n "from . import strategy_wiring\|sys.modules.get(\"app.strategy_wiring" \
    program_code/.../app/h_state_query_handler.py
```
僅兩處 `from . import strategy_wiring` (現均改 `sys.modules.get`)，無遺漏；無其他生產檔殘留同模式（`grep -rn "from . import strategy_wiring" app/` 本檔外 0 命中）。若僅修 line 334，35 fail 中超過半數涉及 `_collect_agent_snapshots` (Strategist/Guardian/Analyst/Executor/Scout/Defensive/Phase4 共 ~22 fail) 仍會走未修 path → fail 不消。E1 的 scope 微擴**正當**，PM accept 為 root-cause 完整修復。

## 2. CLAUDE.md §九 8 條 checklist

| Item | 狀態 | 說明 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ + 合理擴展 | PA Step 1 line 334 + 自決加 line 495 sibling，see §1 |
| 沒有 `except: pass` 或靜默吞 | ✅ | diff 內舊 `except Exception: logger.debug(...)` 已被新 `if _sw is None: logger.debug` 取代；無新吞例外 |
| 日誌使用 `%s` 格式（非 f-string）| ✅ | logger.debug 純 string literal，無 % / f""，無 interpolation 風險 |
| 新 API 端點有 `_require_operator_role()` | N/A | 無新端點 |
| `except HTTPException: raise` 在 `except Exception` 之前 | N/A | 無新 except |
| `detail=str(e)` 已改為 "Internal server error" | N/A | 不涉路由 |
| asyncio 路由中沒有 blocking threading.Lock | N/A | 不涉 asyncio |
| 沒有私有屬性穿透（`._xxx`）| ✅ | `_sw`、`_app_pkg`、`_SW_ATTR_MISSING` 全 module-private 局部，非跨模組私有穿透 |

8/8 PASS。

## 3. OpenClaw 9 條 §3 checklist

| Item | 狀態 | 說明 |
|---|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` | ✅ 0 命中 | `git diff e2875da -- <files> \| grep -E '(/home/ncyu\|/Users/[^/]+/)'` 空 |
| 雙語注釋（MODULE_NOTE + docstring + inline）| ✅ 完整 | 兩處 production fix 各有英中對照 ~12 行 inline rationale；test fixture docstring 雙語對齊 W3 fix 模式 |
| Rust unsafe / unwrap / panic | N/A | 純 Python |
| 跨語言 IPC schema | N/A | 不涉 IPC |
| Migration Guard A/B/C | N/A | 不涉 SQL |
| healthcheck 配對（被動等待 TODO）| N/A | 不新增被動等待 |
| Singleton 登記 §九 表 | ✅ N/A | `_SW_ATTR_MISSING` 是 module-private sentinel object()，非 process global mutable state；不需登記 |
| 文件大小 800/1200 | ⚠️ LOW pre-existing | h_state_query_handler.py 859 行（>800 警告線、<1200 硬上限）— 本 fix +33 淨增（其中 ~28 為 inline 雙語注釋），非邏輯膨脹；推近 1200 仍有 ~341 行 buffer |
| Bybit API 字典手冊 | N/A | 不涉 Bybit API |

8/9 PASS + 1 ⚠️ pre-existing warning（非本 fix 引入）。

## 4. 對抗反問結果

### Q1: 「production fix 真乾淨？sys.modules.get 替代 try/except 是否丟失保護？」
**A**: 原 `try: from . import strategy_wiring; except Exception` 廣捕 import-time failure（heavy module 實例化多 agent 與 singleton 時可能 raise）。新 `sys.modules.get` 本身永不 raise（dict lookup），但**只在 `_sw is None` 時走 fallback**。
- 推理：本 handler 由 IPC reverse handler `query_h_state_full` 觸發（caller 唯一：`ai_service_dispatch.py:832`）。IPC 服務只在 uvicorn boot 完成後啟動，此時 `app.strategy_wiring` 已成功 import（否則 main_legacy 先 import 就 crash）。即「first-time lazy import 失敗」場景在 IPC 觸發點不可達。
- 假設成立場景：若未來重構成 daemon thread 早於 wiring 完成 import 即 query → `sys.modules.get` 回 None → fail-soft empty shell（與舊 except 結果**等價**）。
- 病態場景：若 sys.modules 內為「partial module（circular import in progress）」，`getattr(_sw, "STRATEGIST_AGENT", None)` 仍會回 None → 既有 line 367-376 `if strategist is None` 第二層 fallback 處理。**fail-soft contract 完整保留**。
- ✅ **PASS**

### Q2: 「既有 fail-soft contract 真支持 None case？」
**A**: 兩處 fix 後緊接 `if _sw is None: logger.debug + return None,...` 走相同 empty-shell return pattern；對外永不 raise。Verify by reading line 358-365 + 502-509。實測 90 passed in isolation 證明 None path 走得通（test fixture 故意 sys.modules.pop 場景觸發）。
- ✅ **PASS**

### Q3: 「Linux runtime production 路徑：daemon poll 讀 strategy_wiring → fix 後是否仍綠？」
**A**: Mac 與 Linux 皆 CPython 3.x，`sys.modules` semantic 跨平台一致（CPython spec 明確）。Mac dev session 不啟 engine（per `feedback_dev_runtime_split.md`），無法直驗 Linux runtime；但 PA RFC §3.3 已論證跨平台等價，且 production 路徑（uvicorn boot → strategy_wiring import → IPC handler ready）兩平台同形。建議 E4 階段 ssh trade-core 跑同 pytest 套件確認 35→0 跨平台一致。
- ✅ **推論安全**，待 E4 ssh 驗

### Q4: 「Scope 微擴正當性 — 真 sibling pattern？」
**A**: 兩處皆 `from . import strategy_wiring as _sw` 解析同一 `app.strategy_wiring` 模組，受**同一** CPython attribute precedence 影響。若僅修 line 334，PA RFC §2.2 35 fail 表中：
- `_collect_h_snapshots` path（H1/H2/H3/H4/H5 系列）= 13 fail
- `_collect_agent_snapshots` path（Strategist/Guardian/Analyst/Executor/Scout/Defensive/Phase4）= 22 fail

僅修 1 處則 22 fail 仍綠不掉。E1 「不修第二處則 35 fail 中超過半數失敗」聲稱**屬實驗證**（可由 §2.2 表分類 13+22=35 直推）。
- ✅ **PASS**

### Q5: 「Test fixture sentinel atomic restore — race condition？」
**A**: pytest 預設單線程跑（無 `-n` 並行），fixture install→teardown 全在同一 thread；sentinel `_SW_ATTR_MISSING` 是 module-level `object()`，identity 唯一。`prev_attr is _SW_ATTR_MISSING` 用 `is`（identity）比對非 `==`（equality），避免被 `__eq__` 騙。restore 順序：先還原 sys.modules → 再還原 attr，與 install 順序對稱。**無 race**。
- ✅ **PASS**

### Q6: 「backward-compat 接舊單值 prev — 破任何既有 caller？」
**A**: `grep -rn "_install_fake_strategy_wiring\|_restore_strategy_wiring" program_code/` 結果**僅本檔內 ~14 callsite**，0 外部 caller。backward-compat shim 是 defensive over-engineering（無實際需求），但不增加 bug 風險，僅 ~5 行代碼成本。可保留。
- ✅ **PASS**（informational）

### Q7: 「`_SW_ATTR_MISSING` 是否應登記 §九 Singleton 表？」
**A**: 是 module-private sentinel `object()`，純 identity comparison 用，無 mutable state。與 §九 表內 `_SHARED_IPC_SLOTS` / `_LEADER_LOCK_FD` 等 process-global mutable singletons 性質**根本不同**。不需登記。
- ✅ **PASS**

## 5. 自驗結果（Mac local）

| 驗收項 | 命令 | 期望 | 實際 |
|---|---|---|---|
| 隔離跑 h_state | `pytest test_h_state_query_handler.py -v` | 35→0 fail | **90 passed in 0.05s** ✅ |
| Same-session 含 polluter | `pytest test_api_contract.py test_h_state_query_handler.py` | 35→0 | **108 passed in 1.43s** ✅ |
| W3 regression | `pytest test_strategist_cognitive_integration.py -v` | 8/8 | **8 passed in 0.03s** ✅ |
| W2+W1+LOSSES regression | `pytest test_cognitive_modulator_coverage test_strategist_cognitive_w1_fix test_g8_01_fup_losses_wiring -q` | 40/40 | **40 passed in 0.05s** ✅ |
| 全 control_api_v1 | `pytest control_api_v1/tests/ -q` | ≤ 38 fail (剩 17 executor + 18 promote + 3 phase2) | **38 failed, 3070 passed** ✅ |
| Baseline cross-check (stash fix) | 4-file 子集 pre-fix | 35 h_state fail | **35 h_state + 22 phase2_routes fail（order-dependent）** confirmed |
| Post-fix on same 4-file 子集 | 同上 post-fix | h_state 35→0 | **0 h_state fail, 22 phase2 fail unchanged** ✅ |

**剩 38 fail 真為 pre-existing sibling-pollution family**（PA RFC §2.1 列 + promote_api 為漏列補錄），非本 fix 引入。可後續另開 ticket 同 Option B+A pattern 修。

## 6. Findings

| 嚴重性 | 位置 | 描述 | 動作 |
|---|---|---|---|
| LOW (informational) | `h_state_query_handler.py` 全檔 859 行 | pre-existing 推近 1200 硬上限（>800 警告線；本 fix 淨 +33 中 ~28 為雙語注釋）| 不阻 merge；下次同檔再動需評估拆分（與 G3-08 Phase 4 framework signature 對齊） |

無 CRITICAL / HIGH / MEDIUM。

## 7. 結論

**PASS to E4** — APPROVE_WITH_NITS

- ✅ §九 8/8 全綠
- ✅ OpenClaw 8/9 + 1 ⚠️ pre-existing 文件大小（非本 fix 引入）
- ✅ 對抗 7 問全 PASS（production runtime 等價 + fail-soft 完整 + scope 擴展正當 + race-free + 跨平台推論安全 + sentinel correctness + singleton 表規則 N/A）
- ✅ 自驗 35→0 fail (隔離 90/90 + same-session 108/108) + W3 8/8 + W2/W1/LOSSES 40/40 + 全套件 3070 passed
- ✅ 剩 38 fail 為 pre-existing sibling-pollution family（17 executor + 18 promote + 3 phase2），PA RFC §6 明示 out-of-scope，非本 fix 責任

### E4 待驗

1. ssh trade-core 跑 `pytest test_h_state_query_handler.py -v` 確認 Linux 90 passed（PA RFC §3.3 跨平台推論驗證）
2. ssh trade-core 跑 `pytest test_api_contract.py test_h_state_query_handler.py` 確認 same-session 108 passed
3. 全套件 Linux baseline 對齊（預期 38 fail / 3070 passed）

### Operator commit 後續（E4 + PM Sign-off 後）

Commit message template 可採 PA RFC §7 模板；建議補一行「E2 review approve_with_nits — 1 LOW pre-existing 859 行文件大小，下次同檔動須評估拆分」。

E2 REVIEW DONE: PASS to E4 · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-28--strategist_singleton_pollution_fix_review.md`
