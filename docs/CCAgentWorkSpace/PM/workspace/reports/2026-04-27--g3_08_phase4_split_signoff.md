# PM Sign-off — G3-08 Phase 4 Split (Strategist + cost_tracker) + Phase 4 5-Agent Design RFC

**Date**: 2026-04-27
**PM**: 主會話（Conductor mode）
**Wave**: G3-08 Phase 4 unblock + Phase 4 5-Agent design
**Status**: ✅ READY FOR OPERATOR MERGE（Track A + Track B E4 全 PASS）
**Pre-conditions**: Tier 9 sign-off `e5f1b2d`（Phase 3 COMPLETE）+ PA RFC `de699df`（split combined）
+ PA RFC `340c78b`（Phase 4 5-Agent design）

---

## § 1. Wave 三 Track 並行架構

| Track | Agent | Status | Commit | Worktree Branch |
|---|---|---|---|---|
| **A** Strategist split | E1 | ✅ E2 PASS_WITH_NITS / E4 PASS | `6fac0ca` | `worktree-agent-ad7ef0f891ff580d9` |
| **B** cost_tracker split | E1 | ✅ E2 PASS_WITH_NITS / E4 PASS | `73c1f3d` | `worktree-agent-af8001f13a3d3940b` |
| **C** Phase 4 5-Agent design RFC | PA | ✅ DONE 直接 commit main | `340c78b` | main |

並行分發架構（per PA RFC `de699df` §8.1）：Track A + B worktree isolation per-track；
Track C PA design 走 main worktree（pure docs，0 撞檔）。

---

## § 2. Track A — G3-08-PHASE-4-STRATEGIST-SPLIT impl

**目標**：strategist_agent.py 1200 LOC §九 hard cap exact-touch 拆檔，解阻 Phase 4
5-Agent Strategist sub-task（per PA RFC §11.1，預期 +30-60 LOC 後仍 <800）。

### 2.1 改動檔案（4）
- `app/strategist_agent.py` 1200 → **792 LOC**（達標：< 800 §七 警告線，buffer 8 行）
- `app/strategist_edge_eval.py` **NEW 369 LOC**（6 fn: edge eval + prompt + TSR）
- `app/strategist_weights.py` **NEW 224 LOC**（6 fn: weights + dependency injection）
- `app/strategist_cognitive.py` **NEW 169 LOC**（4 fn: V2 fast channel + cognitive modulator）

### 2.2 工作鏈

| Stage | Verdict | Findings |
|---|---|---|
| E1 impl | ✅ DONE commit `6fac0ca` | 16 method 1-line delegator + 4 `noqa: F401` re-export block + 3 sibling 雙語 MODULE_NOTE/docstring |
| E2 review | ✅ PASS_WITH_NITS | 0 CRITICAL/HIGH/MED, 2 NIT (NIT-1: `_handle_intel` 197 LOC 可下輪再拆 / NIT-2: pre-existing logger.warning `%s, %s, e, e` 1:1 搬入)；§九 8 條 + OpenClaw §3 9 條全綠；對抗反問 5 點全驗 |
| E4 regression | ✅ PASS | Mac pytest 126/0 (兩遍同綠) + Linux cargo lib **2252/0** (兩遍同綠 baseline 不變) + broader strategist/h_state/layer2 grep 0 fail |

### 2.3 高風險警告（PA RFC §9）驗證結果
1. ★ Method body 委託後 sibling fn 第一參 `agent` 訪問 `self._lock/_stats/_ollama` 全綠 — verified by 41 strategist_agent tests + 59 audit_wiring/truth_source/h_chain tests
2. ★ Re-export `noqa: F401` 4 區塊全在 — `grep noqa: F401` 命中 4
3. ★ `_handle_intel` 197 LOC byte-identical — `diff <pre-split> <post-split>` empty

---

## § 3. Track B — G3-08-PHASE-4-COST-TRACKER-SPLIT impl

**目標**：layer2_cost_tracker.py 930 LOC 超 §七 800 警告 +130 拆檔，解阻 G3-09
cost_edge_advisor implementation（per PA RFC §11.2，預期 sibling layer2_adaptive
+50-100 LOC 後仍 <800）。

### 3.1 改動檔案（5）
- `app/layer2_cost_tracker.py` 930 → **540 LOC**（達標：< 800，buffer 260 行）
- `app/layer2_cost_recording.py` **NEW 405 LOC**（9 fn: claude/search cost + sync_to_rust + record_call）
- `app/layer2_adaptive.py` **NEW 207 LOC**（3 fn: recalculate + adaptive_state + cost_edge_ratio；G3-09 future hook）
- `app/layer2_h_state_snapshots.py` **NEW 190 LOC**（2 fn: get_h2_snapshot + get_h5_snapshot）
- `tests/test_layer2.py` **4 patch site 升級** line 384/417/552/587

### 3.2 工作鏈

| Stage | Verdict | Findings |
|---|---|---|
| E1 impl | ✅ DONE commit `73c1f3d`（PM 代 commit per Track A 一致 pattern；E1 留 staged 給 E2） | 14 method 1-line delegator + 3 noqa F401 re-export block + 4 patch path 升級 |
| E2 review | ✅ PASS_WITH_NITS | 0 CRITICAL/HIGH/MED/LOW, 3 NIT (全 cosmetic：commit message 「3 noqa F401」用詞 / E1 report LOC 歸因措辭 / sibling docstring 「升級」用詞)；**LOC drift +382 investigated and confirmed not padding** — git blame 5 sample verbose docstrings 全部追溯到 pre-split source；**RFC estimate-formula 漏估雙語 MODULE_NOTE / delegator docstring / 既存 inline rationale 平搬**，E1 引入 0 行新 padding；業務邏輯 byte-equivalent pre-split |
| E4 regression | ✅ PASS | Mac pytest **196/0 (兩遍同綠 non-flaky)** + Linux cargo lib **2252/0** + patch path verify (舊 0 / 新 4 site `tests/test_layer2.py:389/422/557/592`) + mock safety PASS (0 business logic mocked, 14 delegator real-run on sibling)；3 WARN 全 cosmetic（Mac fastapi env gap pre-existing / E1 commit message line off-by-5 doc drift / 0 Rust diff = baseline 不變）|

### 3.3 高風險警告（PA RFC §10）驗證結果
1. ★ `_sync_to_rust_budget` daemon-thread fire-and-forget pattern 完整保留（verified by E2 line-by-line diff）
2. ★ `record_claude_cost` dual hint emit order `h2.budget_consumed → h5.claude_cost_recorded` 不變（verified by E2 layer2_cost_recording.py:382-428 inspection）
3. ★ Test patch path 4 site 升級全覆蓋（grep verify: 舊 path 0 site / 新 path 4 site）

### 3.4 LOC drift 結論（重要 governance）
3 sibling 全部超 RFC 估，total +382 LOC（+40%）。E2 深查結論：
- E1 引入 **0 行 new padding**
- RFC formula **漏估** 雙語 MODULE_NOTE / delegator docstring / 既存 inline rationale 平搬
- 不退 E1，不修 RFC（已 land docs）；下次 PA 拆檔 RFC formula 應 +30-40% buffer

**E5 backlog**：是否值得做 docstring trim wave（保留雙語但去除 line-by-line redundancy）— 預估 -50 to -100 LOC 但 review cost 高、邊際效益低，**不建議單獨開 wave**。

---

## § 4. Track C — PA Phase 4 5-Agent Design RFC

**目標**：5 個 sub-task 派發架構 + ready-to-deploy E1 prompt template × 5（鏡 Phase 3 §6 pattern）。

### 4.1 RFC 規模 + 結構
- 1415 LOC（超 ≥800 規格），14 節 + 5 self-contained E1 prompt template
- 撞檔風險矩陣 + multi-session race 防護 + 治理對照（16 根原則 + DOC-08 §12）
- 路徑：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md`
- Operator 副本：`docs/CCAgentWorkSpace/Operator/2026-04-27--g3_08_phase4_5agent_design_rfc.md`
- Commit: `340c78b` on main

### 4.2 5 sub-task 派發架構（Pattern B per-agent 拆 5）

| Sub-task | LOC ETA | Hard pre-cond | Worktree |
|---|---|---|---|
| 4-1 Strategist | ~60 | **Track A merge land** | isolation worktree |
| 4-2 Guardian | ~35 | — | 主樹並行 |
| 4-3 Analyst | ~26 | — | 主樹並行（§七 警告觸發） |
| 4-4 Executor | ~36 | — | 主樹並行（shadow_mode wire 注意點） |
| 4-5 Scout | ~27 | — | 主樹並行（§九 1200 hard cap 接近） |

ETA：**3.75d 並行版**（≤ PA design §11.1 估 4d）。

### 4.3 5 大架構決策（重要）
1. query_handler 升級採 **Option B 拆兩個 collector**（`_collect_h_snapshots` 不變 + 新 `_collect_agent_snapshots` 返 dict）— forward-compat
2. **Phase 4 invariant**：所有 snapshot 字段必為 `int` 或 `bool→int`（對齊 Rust `HashMap<String, i64>`）
3. Sub-task 4-4 Executor `_shadow_mode_provider()` call **必在 self._lock 之外** + provider raise → fail-closed（CLAUDE.md §二 原則 #6）
4. 2 條 Backlog FUP filed：**G3-08-FUP-ANALYST-SPLIT**（§七 警告）+ **G3-08-FUP-MAF-SPLIT**（§九 接近，建議 P1）
5. healthcheck [20] expected set 漸進式 rollout（5→10 半途 WARN 不 FAIL）

### 4.4 unblock 下游
- **G8-01 認知自適應 e2e**：CognitiveModulator ≥85% line cov + StrategistAgent integration（待 Strategist + Analyst snapshot 完成）
- **G3-09 cost_edge_advisor**：跨 Agent 訂閱（Strategist `ai_evaluations` + Analyst `l2_analyses`）

---

## § 5. Operator Merge Instructions

**Per CLAUDE.md §七**：Mac CC 禁 `git merge / rebase / reset / checkout`，merge 必由 operator 執行。

### 5.1 Order: Track A 先 merge（per PA RFC §8.1，Phase 4 unblock 路徑優先）

```bash
# 在 srv/ 主 worktree 內 operator 執行：
cd /Users/ncyu/Projects/TradeBot/srv

# 1. fetch 最新（如需）
git fetch origin

# 2. Track A merge（no-FF 保留 wave 邊界，順 Track A → B 順序）
git merge worktree-agent-ad7ef0f891ff580d9 --no-ff -m "merge: G3-08 Phase 4 Strategist split (Track A 6fac0ca) — E2 PASS_WITH_NITS / E4 PASS Mac 126/0 + Linux 2252/0"

# 3. Track B merge（待 Track B E4 PASS 確認後執行）
git merge worktree-agent-af8001f13a3d3940b --no-ff -m "merge: G3-08 Phase 4 cost_tracker split (Track B 73c1f3d) — E2 PASS_WITH_NITS / E4 PASS"

# 4. push
git push origin main

# 5. Linux pull（per CLAUDE.md §六 Mac↔Linux SSH bridge）
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"

# 6. Worktree cleanup（merge 後）
git worktree remove .claude/worktrees/agent-ad7ef0f891ff580d9
git worktree remove .claude/worktrees/agent-af8001f13a3d3940b
git branch -d worktree-agent-ad7ef0f891ff580d9
git branch -d worktree-agent-af8001f13a3d3940b
```

### 5.2 Deploy notes
- **不需要 `--rebuild`**：純 Python，0 Rust diff，uvicorn auto-reload 即拾起 sibling 模組（per E4 Track A recommendation）
- engine PID 不觸動（last rebuild `2033577`，binary mtime 2026-04-26 04:29 仍 live）
- 累積債務：等 Phase 4 5-Agent 5 sub-task 完成 + G3-09 Phase A schema 完成後一併 `restart_all.sh --rebuild`

---

## § 6. unblock 路徑 + 下一 Wave

### 6.1 即時 unblock（merge 後）
1. ✅ **Phase 4 5-Agent Strategist sub-task (4-1)** ready-to-deploy（per Track A + Track C RFC）
2. ✅ **G3-09 Phase A schema** ready-to-deploy（per Track B + PA RFC `642c34c` §11，PM threshold = -0.5 lock-in）

### 6.2 下次 wave 派發建議

**Wave 並行 dispatch**（merge 完成後 PM 主會話直接派）：

| Track | Task | E1 ETA | 並行 Worktree |
|---|---|---|---|
| A | G3-09-PHASE-A-SCHEMA impl | 4.5d | 主樹（per PA RFC `642c34c` §11） |
| B | Phase 4 Sub-task 4-1 Strategist | 5-7h | worktree isolation |
| C | Phase 4 Sub-task 4-2 Guardian | 5-7h | 主樹 |
| D | Phase 4 Sub-task 4-3 Analyst | 5-7h | 主樹（§七 警告觸發） |
| E | Phase 4 Sub-task 4-4 Executor | 5-7h | 主樹（shadow_mode wire 注意） |
| F | Phase 4 Sub-task 4-5 Scout | 5-7h | 主樹（§九 接近） |

並行 6 track 過載風險：建議拆 2 wave
- **Wave I**: G3-09-PHASE-A-SCHEMA + Phase 4 Sub-task 4-2/4-3/4-4/4-5（4 並行）
- **Wave II**: Phase 4 Sub-task 4-1 Strategist（待 Track A merge land 後）

### 6.3 Backlog 新增
- **G3-08-FUP-ANALYST-SPLIT** P2（per Track C RFC §7 警告觸發後備）
- **G3-08-FUP-MAF-SPLIT** P1（per Track C RFC §九 接近）
- **STRATEGIST-FILE-790-NIT** P3（per E2 NIT-1，下輪 Phase 5 / Wave 2 拆 dispatch helper 50-100 LOC）
- **TRACK-B-DOCSTRING-TRIM** ❌ NOT-PRIORITIZED（per § 3.4 結論，邊際效益低）

---

## § 7. 治理對照

### 7.1 16 根原則（§二）
- 全 16 條未變動（純 Python file structure refactor + pure docs）
- ⭐ 強化 #15 多 Agent 協作（Phase 4 5-Agent state events 對齊）
- ⭐ 強化 #13 AI 資源成本感知（cost_tracker split 為 G3-09 cost_edge_ratio 鋪路）

### 7.2 9 條安全不變量（DOC-08 §12）
- 全 9 條未變動

### 7.3 §四 Live 5 項硬邊界
- 全零觸碰（純 Python refactor，無 authorization.json / Mainnet env / live mode 影響）

### 7.4 §七 LOC 警戒
- ✅ Strategist 主檔 792 < 800（buffer 8 行，下輪可再拆 50-100 LOC）
- ✅ cost_tracker 主檔 540 < 800（buffer 260 行）
- ✅ 6 個 NEW sibling 全 < 800（最高 405）
- 🟡 G3-08-FUP-ANALYST-SPLIT P2 + G3-08-FUP-MAF-SPLIT P1 backlog filed

### 7.5 §九 singleton table
- 0 新 singleton（純 method 拆檔，sibling fn = module-level helper 非全局狀態）
- §九 table no-op

---

## § 8. 多 session race 防護

- ✅ `git commit --only` pattern（per memory `feedback_git_commit_only_for_metadoc`）：Track C PA RFC commit 範圍純 docs，0 觸 runtime memory.md
- ✅ Track A + B worktree isolation（per PA RFC §8.4）：撞檔風險矩陣 0 撞
- ✅ Memory updates（E1/E2/PA agent memory.md）暫留 unstaged，待 Track B E4 完成後 batch commit（避免 E2 agent 仍 running 時 commit race）
- ⚠️ Operator side WIP（TODO.md / memory/MEMORY.md / E1a memory）pre-existing，由 operator 自行 commit
- ⚠️ `git push origin main` 受 push gate 阻擋（PR-only），由 operator 觸發

---

## § 9. Test baseline 更新

- **engine lib (Linux)**：2252 / 0 fail（baseline 對齊 STRKUSDT P0 wave merge 後，per CLAUDE.md §三）
- **Mac pytest Track A**：126 pass / 0 fail (兩遍同綠)
- **Mac pytest Track B**：196 pass / 0 fail (兩遍同綠 non-flaky)
- **healthcheck**：27 check（19 既有 + 8 STRKUSDT P0 [22-29]）

merge 後不需更新 baseline（純 Python 0 影響 cargo test count；pytest count 由 sibling fn move 自然算入既有 suite）。

---

## § 10. PM 結論

**G3-08 Phase 4 split combined wave 三 Track 全綠**：
1. ✅ Track A Strategist split — Phase 4 5-Agent Strategist sub-task ready
2. ✅ Track B cost_tracker split — G3-09 Phase A schema ready
3. ✅ Track C PA Phase 4 5-Agent design RFC — 5 sub-task templates ready

Operator 接手 merge（per § 5）後即可 dispatch Wave I（G3-09 Phase A + Phase 4 Sub-task
4-2/4-3/4-4/4-5 4 並行），Wave II（Sub-task 4-1 Strategist）緊隨。

ETA 至 Live：per CLAUDE.md §三 中位 ~2026-05-30（事件驅動）。

---

**PM Sign-off**: 主會話（Conductor mode）
**Date**: 2026-04-27
**Next session 任務**：等 Track B E4 PASS → batch memory commit → operator merge → 派 Wave I
