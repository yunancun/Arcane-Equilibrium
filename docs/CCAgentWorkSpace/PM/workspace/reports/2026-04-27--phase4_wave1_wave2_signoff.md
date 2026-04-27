# PM Sign-off — G3-08 Phase 4 5-Agent + G3-09 Phase A 完整 Wave (Wave I-a/b + Wave II)

**Date**: 2026-04-27
**PM**: 主會話（Conductor mode）
**Wave**: Phase 4 全鏈 + G3-09 Phase A 落地
**Status**: ✅ E1+E2+E4 全鏈 PASS · 待 operator 序貫 merge 4 worktree branches

---

## § 1. 全 wave dispatch 架構（時間順序）

| 階段 | Track | Commit / Worktree | Status |
|---|---|---|---|
| Pre-Wave | Track A merge | `afce487` (Strategist split merge) | ✅ pushed |
| Pre-Wave | Track B merge | `c077e8c` (cost_tracker split merge) | ✅ pushed |
| Pre-Wave | PA RFC | `340c78b` (Phase 4 5-Agent design 1415 LOC) | ✅ pushed |
| Pre-Wave | PM Sign-off Phase 4 split | `501ff70` | ✅ pushed |
| **Wave I-a** | Sub-task 4-1 Strategist agent_state | `c8a4a55` on main | ✅ E2+E4 PASS, pushed |
| **Wave I-b** | G3-09 Phase A cost_edge_advisor | `00682ef` on main | ✅ E2+E4 PASS, pushed |
| **Wave II 4-2** | Guardian agent_state | `e1157ae` worktree branch | ✅ E2+E4 PASS, NOT merged |
| **Wave II 4-3** | Analyst agent_state | `b8951ab` worktree branch | ✅ E2+E4 PASS, NOT merged |
| **Wave II 4-4** | Executor agent_state | `d99a0da` worktree branch | ✅ E2+E4 PASS, NOT merged |
| **Wave II 4-5** | Scout agent_state (Phase 4 final) | `eee0f7b` worktree branch | ✅ E2+E4 PASS, NOT merged |

---

## § 2. Wave I 結算

### 2.1 Sub-task 4-1 Strategist (`c8a4a55` on main，已 push)

| Stage | Verdict | Detail |
|---|---|---|
| E1 impl | ✅ DONE | strategist_agent.py 792 → 829 LOC（⚠️ §七 800 +29 self-flagged）+ h_state_query_handler.py 636→772 + +16 tests |
| E2 review | ✅ PASS_WITH_NITS | 0 CRITICAL/HIGH/MED, 2 NIT (829 §九 warning band 接受 + hook placement LOW) |
| E4 regression | ✅ PASS | Mac pytest 142/0 (兩遍非 flaky) + Linux cargo lib 2252/0 (兩遍 baseline) |

### 2.2 G3-09 Phase A cost_edge_advisor (`00682ef` on main，已 push)

| Stage | Verdict | Detail |
|---|---|---|
| E1 impl | ✅ DONE | 6 NEW Rust files (~1338 LOC + 38 tests) + 21 modified Rust + 3 TOML + 3 Python healthcheck |
| E2 review | ✅ PASS | 0 BLOCKER/HIGH/MED/LOW any level — 完美 advisory only / threshold direction / slot drift verified |
| E4 regression | ✅ PASS | Mac cargo lib 2290/0 (兩遍) + Linux baseline 2252/0 (origin 不含 G3-09) |

### 2.3 解阻路徑（Wave I 已完成）
- ✅ G3-09 Phase B/C cost_edge_advisor binding（schema + advisory ready，待 Phase B shadow dry-run + Phase C live gate）
- ✅ 5-Agent state events Strategist arm（解阻 Wave II 4-2/3/4/5）

---

## § 3. Wave II 結算（4 並行 sub-task）

### 3.1 改動 sumamry

| Sub-task | Commit | LOC delta | New Tests | Self-flagged |
|---|---|---|---|---|
| 4-2 Guardian | `e1157ae` | guardian_agent.py 587→**631** / hsq 772→785 | +19 | clean |
| 4-3 Analyst | `b8951ab` | analyst_agent.py 834→**874** / hsq 772→789 | +13 | §七 +74 (FUP-ANALYST-SPLIT P2) |
| 4-4 Executor | `d99a0da` | executor_agent.py 669→**741** / hsq 772→785 | +16 | Edit/Write silent-fail (workaround disk-verified clean) |
| 4-5 Scout | `eee0f7b` | multi_agent_framework.py 1147→**1190**/1200 / hsq 770→788 | +5 classes | §九 hard cap edge 10 LOC headroom (FUP-MAF-SPLIT P1) + `record_scan` rename per RFC §6.5 自由變通 |

### 3.2 E2 batch review 結果（per RFC §5.4）

**ALL 4 PASS_WITH_NITS** → forward all 4 to E4 → operator merge

| 嚴重性 | 數量 | 內容 |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 2 | 4-3 §七 over warning + 4-5 §九 hard cap edge — 全 self-flagged + FUP filed |
| LOW | 2 | 4-3/4-4 early return invalidate semantics — 接受（10s poll 兜底） |
| INFO | 1 | sequential merge textual conflict (h_state_query_handler.py + test_hsq) — 純機械 3-way merge |

### 3.3 E4 batch regression 結果

**ALL 4 PASS** · 0 flaky:

| Engine / Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Linux cargo lib (origin/main `00682ef`) | 2290 | 0 | 2290 | 0 ✓ |
| 4-2 Guardian pytest (3-suite × 2 runs) | 152 | 0 | n/a | +152 |
| 4-3 Analyst pytest (3-suite × 2 runs) | 138 | 0 | n/a | +138 |
| 4-4 Executor pytest (3-suite × 2 runs) | 139 | 0 | n/a | +139 |
| 4-5 Scout pytest (3-suite × 2 runs) | 187 | 0 | n/a | +187 |

### 3.4 Cumulative post-merge 預估
- `h_state_query_handler.py`: 預估 post-merge ~816-828 LOC (over 800 warning ~+20，well under 1200 cap)
- `test_h_state_query_handler.py`: ~3000+ LOC (lenient test file convention)
- engine lib (Linux): 2290 baseline 不變（純 Python）

---

## § 4. Operator Sequential Merge Instruction

**Per CLAUDE.md §七**：Mac CC 禁 `git merge / rebase / reset`，4 個 worktree branches merge 必由 operator 執行。

### 4.1 推薦 merge 順序（per E2 §5.3 absorb pattern）

```bash
cd /Users/ncyu/Projects/TradeBot/srv

# 1) 4-2 Guardian first (clean, no conflict expected)
git merge worktree-agent-a051276dd2c9c8a42 --no-ff -m "merge: G3-08 Phase 4 Sub-task 4-2 Guardian agent_state — E2 PASS_WITH_NITS / E4 PASS"

# 2) 4-3 Analyst second (will conflict on hsq + test_hsq, resolve per §4.2)
git merge worktree-agent-ad253927d45469488 --no-ff -m "merge: G3-08 Phase 4 Sub-task 4-3 Analyst agent_state — E2 PASS_WITH_NITS / E4 PASS / FUP-ANALYST-SPLIT P2 filed"

# 3) 4-4 Executor third (same conflict pattern, resolve per §4.2)
git merge worktree-agent-a3625849262bdb342 --no-ff -m "merge: G3-08 Phase 4 Sub-task 4-4 Executor agent_state — E2 PASS_WITH_NITS / E4 PASS / shadow_mode wire validated"

# 4) 4-5 Scout last (same conflict pattern + Phase 4 envelope complete signal)
git merge worktree-agent-a3ba65c86c26adef7 --no-ff -m "merge: G3-08 Phase 4 Sub-task 4-5 Scout agent_state (Phase 4 complete) — E2 PASS_WITH_NITS / E4 PASS / FUP-MAF-SPLIT P1 filed"

# Push + Linux sync
git push origin main
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"

# Worktree cleanup
git worktree remove .claude/worktrees/agent-a051276dd2c9c8a42 -f
git worktree remove .claude/worktrees/agent-ad253927d45469488 -f
git worktree remove .claude/worktrees/agent-a3625849262bdb342 -f
git worktree remove .claude/worktrees/agent-a3ba65c86c26adef7 -f
git branch -D worktree-agent-a051276dd2c9c8a42 worktree-agent-ad253927d45469488 worktree-agent-a3625849262bdb342 worktree-agent-a3ba65c86c26adef7
```

### 4.2 Conflict resolution rule

每個 merge step 2/3/4 預期在兩檔有 textual conflict（4 commits 同位置加 if-block / test class）：

#### `app/h_state_query_handler.py` 內 `_collect_agent_snapshots` framework
**Resolution pattern** — 保 4 個 if-block 按 canonical 順序排列：
```python
def _collect_agent_snapshots(...) -> dict[str, Optional[dict[str, Any]]]:
    """..."""
    result: dict[str, Optional[dict[str, Any]]] = {
        "strategist": None,
        "guardian": None,
        "analyst": None,
        "executor": None,
        "scout": None,
    }

    # ... lazy import strategy_wiring ...

    if include_strategist:        # 4-1 (already in main)
        result["strategist"] = ...
    if include_guardian:          # 4-2
        result["guardian"] = ...
    if include_analyst:           # 4-3
        result["analyst"] = ...
    if include_executor:          # 4-4
        result["executor"] = ...
    if include_scout:             # 4-5
        result["scout"] = ...

    return result
    # placeholder comment 全刪
```

`build_h_state_full_response`：4 個 sub-task 各加 `include_<agent>` 參數 + 對應 dict population。Resolution: 全部保留，按相同 canonical 順序排列。

#### `tests/test_h_state_query_handler.py`
4 個 test class 順序拼接（已存在的 4-1 strategist 後）：
```
TestStrategistAgentStateIntegration       # 4-1
TestGuardianAgentStateIntegration         # 4-2
TestAnalystAgentStateIntegration          # 4-3
TestExecutorAgentStateIntegration         # 4-4
TestScoutAgentStateIntegration            # 4-5
TestAgentStatesIncludeFilter              # cumulative
TestTenBucketEnvelopeRegression           # 4-5 final
```
無語意衝突，順序拼接即可。

### 4.3 Deploy notes
- **不需要 `--rebuild`**（純 Python，0 Rust diff）
- Phase 4 envelope 全 wired = `/api/v1/h_state/full` env=1 含 `h_states (5) + agent_states (5)` = **10-bucket envelope live**
- env 預設 OFF（`OPENCLAW_H_STATE_GATEWAY=1` 才啟用）— deploy 即無 trade impact
- 累積債務：Phase 4 全 land 後，operator 評估是否 export `OPENCLAW_H_STATE_GATEWAY=1` 啟動 5-Agent observability

---

## § 5. Post-merge 必跑 + FUP backlog

### 5.1 Post-merge regression（operator 跑）
```bash
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -5"
# 預期 2290/0 baseline 不變

ssh trade-core "cd ~/BybitOpenClaw/srv && cd program_code/exchange_connectors/bybit_connector/control_api_v1 && PYTHONPATH=. python3 -m pytest tests/test_h_state_query_handler.py tests/test_strategist_agent.py tests/test_guardian_agent_unit.py tests/test_analyst_agent_unit.py tests/test_executor_agent_unit.py -v 2>&1 | tail -30"
# 預期 全綠（cumulative ~600+ tests）

ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[20\]'"
# 預期 [20] PASS
```

### 5.2 FUP backlog tickets（PM file post-merge）
| Ticket | Priority | Source | Description |
|---|---|---|---|
| **G3-08-FUP-MAF-SPLIT** | P1 | 4-5 self-flagged + E2 verified | multi_agent_framework.py 1190/1200 hard cap edge → split ScoutAgent (~190 LOC) 出獨立 `scout_agent.py` per RFC §5.1；下一個觸 maf 的 PR 前必完成 |
| **G3-08-FUP-ANALYST-SPLIT** | P2 | 4-3 self-flagged | analyst_agent.py 874/800 over warning → 拆 sibling per RFC §5.1（pre-Phase-4 已超） |
| **G3-08-FUP-HSQ-SPLIT** | P2 | E2 cumulative analysis | post-merge h_state_query_handler.py ~828 over 800 warning → 拆 sibling next refactor wave |
| **G3-08-FUP-STRATEGIST-DELEGATOR-SLIM** | P3 | Sub-task 4-1 E2 NIT-1 | strategist_agent.py 829 over warning → 16 BWD-compat 1-line delegators 可 lift sibling stub → 主檔 ~750 |
| **G3-08-FUP-HOOK-PLACEMENT-LOW1** | P4 | Sub-task 4-1 E2 LOW-1 | Strategist `_handle_intel` hook placement 移至 method 末尾 + 5 early-return 點補 hook（純優化）|
| **G3-08-FUP-EXECUTOR-EARLY-RETURN-LOW1** | P4 | Sub-task 4-4 E2 LOW | Executor `_handle_approved_intent` 早 return 路徑（dedup / invalid payload / size<=0）不 fire invalidate；10s poll 兜底接受，純優化 |
| **G3-09-PHASE-A-PA-RFC-SLOT-UPDATE** | P3 | E2 G3-09 + E1 self-correction | PA update RFC §6.2 healthcheck slot ref [22] → [30]（F7 已占用）|
| **G3-09-PHASE-A-DAEMON-INTEGRATION-TEST** | P3 | E2 G3-09 backlog | E1 follow-up daemon integration test（Phase A 哨兵）|

### 5.3 Phase 4 完成後 unblock 路徑
- ✅ **G8-01 認知自適應 e2e 測試**（CognitiveModulator ≥85% line cov + StrategistAgent integration）— 5-Agent observability 完整 wired
- ✅ **G3-09 cost_edge_advisor Phase B**（shadow dry-run）— Phase A schema + advisor live；env=1 + cost_edge.enabled=true 可進 Phase B
- ✅ **G3-09 cost_edge_advisor Phase C**（gate 新倉）— per RFC §7.3 路線圖

---

## § 6. 治理對照

### 6.1 16 根原則（§二）
- 全 16 條未變動（純 Python snapshot accessor + Rust advisor daemon）
- ⭐⭐ 強化 #15 多 Agent 協作（5-Agent state events 完整 wired）
- ⭐ 強化 #13 AI 資源成本感知（cost_edge_advisor advisory only land）
- ⭐ 強化 #6 失敗默認收縮（4-4 Executor shadow_mode provider raise → fail-closed=1）

### 6.2 9 條安全不變量（DOC-08 §12）
- 全 9 條未變動

### 6.3 §四 Live 5 項硬邊界
- 全零觸碰（Phase 4 純觀察 + G3-09 Phase A advisory only）

### 6.4 §七 LOC 警戒（per sub-task）
| 檔案 | LOC | 狀態 |
|---|---|---|
| strategist_agent.py | 829 | 🟡 warning band (Sub-task 4-1，§九 ≥800 必標) |
| guardian_agent.py | 631 | ✅ < 800 |
| analyst_agent.py | 874 | 🟡 warning over by +74 (Sub-task 4-3 self-flagged FUP P2) |
| executor_agent.py | 741 | ✅ < 800 |
| multi_agent_framework.py | 1190 | 🟠 hard cap edge (only 10 LOC headroom; FUP P1 必先 file) |
| h_state_query_handler.py (post-merge) | ~828 | 🟡 warning band (FUP P2) |

### 6.5 §九 singleton table
- 0 新 singleton（純 method 加到 agent class，不創新 module-level mutable state）

---

## § 7. 多 session race / multi-track 合併防護

### 7.1 4 個 worktree branches 物理隔離
✅ 4 並行 sub-task 各自 worktree，0 cross-write
✅ Edit/Write silent-fail caveat (4-4) 已 disk-verify clean

### 7.2 Sequential merge textual conflicts
- h_state_query_handler.py: 4 commits 同位置加 if-block → 純機械 3-way merge
- test_h_state_query_handler.py: 4 commits 同位置加 test class → 順序拼接
- 無語意衝突，operator 按 §4.2 resolution rule 解

### 7.3 main worktree memory.md / report 同步
- E1/E2/E4 memory.md 多次 append (4 sub-task × 3 stages)
- 預期 main worktree 最終 commit 含 memory updates
- 本 Sign-off 文件同 commit

---

## § 8. 一句話結論

**G3-08 Phase 4 5-Agent state events + G3-09 Phase A cost_edge_advisor 完整 wave 落地** —
6 commit + 1 sign-off doc + 5 FUP backlog tickets ready；Wave I (4-1 + G3-09) 已 push origin；
Wave II (4-2/3/4/5) 4 worktree branches E1+E2+E4 全鏈 PASS，待 operator 序貫 merge per §4
（textual conflict 解 + 4 merge commit + push + Linux pull + worktree cleanup ~10-15 分鐘工作）。

**Phase 4 final** = `/api/v1/h_state/full` env=1 回 10-bucket envelope（5 H + 5 Agent）
→ 解阻 G8-01 認知自適應 e2e + G3-09 Phase B shadow dry-run。

---

**PM Sign-off**: 主會話（Conductor mode）
**Date**: 2026-04-27
**Next session 任務**：等 operator merge → 跑 post-merge regression → file 5 FUP tickets → 派 G3-09 Phase B
