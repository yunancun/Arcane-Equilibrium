# PA Combined Sign-off — P0-2 (WP-03 Deploy-Gate Spec) + P0-3 (Race Protocol SOP Phase 2 Rollout)

**Date**: 2026-05-16
**Author**: PA
**Scope**: PM 派 PA 並行做兩個 P0 spec/rollout（讀 only design + doc enforce，0 業務 code 改動）
**Restriction**：不改業務 code / 不 install cron / 不 deploy / 不 commit / push（PM 統一）；Edit/Write 僅在 `docs/` + `.claude/agents/`；0 race risk（不動 GUI batch / Rust IMPL files）
**Status**: DESIGN-COMPLETE / DOCS-ENFORCED — awaiting PM unified commit + push

---

## §1 兩個 P0 並行交付摘要

| Task | 性質 | 主要 deliverable | LOC delta |
|---|---|---|---|
| **P0-2 WP-03 OU Sigma Deploy-Gate Spec** | Spec only (Option C) | `docs/execution_plan/2026-05-16--wp03_ou_sigma_deploy_gate_spec.md` | ~600 LOC new file |
| **P0-3 Race Protocol SOP Phase 2 Rollout** | Doc enforce (Option A) | 5 deliverable enforced（E2 + PM template + profile + lessons + Operator ACK）| ~290 LOC total |

**Total file touched**：6 files（1 new spec + 4 new docs + 2 edit existing doc）。
**Total LOC delta**：~890 LOC（全部 docs，0 業務 code）。
**Race safety**：0 觸碰 GUI batch / Rust IMPL files；獨立 doc paths；無 sibling overlap。

---

## §2 P0-2 WP-03 OU Sigma Deploy-Gate Spec — 設計摘要

### §2.1 Deploy-gate scope（per task brief 1）

- **Commit**：`ef6ea79f` WP-03 OU sigma residual fix (v35 rebuild)
- **Strategy**：`grid_trading` only
- **Metric**：`[40]` realized_edge_acceptance.avg_net_bps grid（filter `strategy_name='grid_trading'` in `learning.mlde_edge_training_rows`）
- **Engine mode**：demo + live_demo（per ADR-0021 paper disabled）
- **Window**：24h primary / 12h fast / 7d cumulative

### §2.2 Baseline 推算（per task brief 3）

- 14d pre-WP-03 baseline window：`[2026-05-11T00:00:00Z, 2026-05-16T01:44:00Z]`
- **R1 mitigation**：移 baseline 起點到 2026-05-11 避 V083 attribution_chain_ok transition contamination（2026-05-10 前 avg_net=-17.82bps post-V083+8.75bps mixed）
- Baseline cache 到 `$OPENCLAW_DATA_DIR/wp03_baseline_cache.json`，第一次 cron run compute

### §2.3 Revert trigger 三層 + ZERO_FILLS（per task brief 4）

| Trigger | Window | 條件 | Severity |
|---|---|---|---|
| T1 fast-fail | 12h | avg_net_bps < -10.0 且 n ≥ 30 | CRITICAL |
| T2 primary | 24h | avg_net_bps < -5.0 且 n ≥ 50 | HIGH |
| T3 cumulative drift | 7d | avg_net_bps < (baseline_14d - 3.0) 且 n ≥ 200 | MEDIUM |
| ZERO_FILLS | 24h | n=0 | (treat as HIGH) |

### §2.4 Revert action 雙 path（per task brief 5）

- **Path A (preferred)**：`[strategist] use_legacy_ou_sigma = true` TOML flag + Rust `compute_ou_step_with_cost_floor()` fallback path（future E1 IMPL `P2-WP03-PATH-A-TOML-FALLBACK`）— < 30s revert
- **Path B (fallback)**：git revert `ef6ea79f` + selective `grid_helpers.rs` checkout + `restart_all.sh --rebuild --keep-auth` — 100% 工作 / engine downtime ~5min
- Decision matrix per trigger severity（CRITICAL → Path B / HIGH → A 若就緒 / MEDIUM → extend 12h / ZERO_FILLS → Path B 立刻）

### §2.5 `[69] check_69_wp03_ou_sigma_deploy_gate` healthcheck design（per task brief 6）

- **Pattern**：對齊既有 `[40]` (`learning.mlde_edge_training_rows` query) + `[12]` (engine_pid mtime deploy proxy) + `[57]/[68]` (feature-specific module)
- **新檔**：`helper_scripts/db/passive_wait_healthcheck/checks_wp03_deploy_gate.py`
- **Verdict 三態**：PASS / WARN（80% threshold approach）/ FAIL（trigger met + 寫 revert flag）
- **註冊**：`__init__.py` import + `__all__` + `runner.py` check list
- **ID `[69]`**：next free slot after `[68] portfolio_resting_exposure`（驗證未占用）

### §2.6 Operator notification 路徑（per task brief 7）

- ADR-0020 manual-only revert principle 嚴格遵守：flag 寫入 `$OPENCLAW_DATA_DIR/wp03_revert_flag` = advisory + audit trail
- Flag SET ≠ auto revert action；operator 顯式 decision (Path A/B/extend/dismiss)
- 三 alert path：（a）daily watchdog FAIL line 被動觀察 / （b）CC 主 session 啟動 read flag echo / （c）GUI banner（未在本 spec scope）

### §2.7 Timeline + sunset 條件（per task brief 8）

```
2026-05-16 01:00 UTC : v35 rebuild deploy (DONE)
2026-05-16 ~02:00 UTC: [69] PASS-skip（sample <1h）
2026-05-16 ~13:00 UTC: [69] 12h active；baseline cache compute
2026-05-17 01:00 UTC: [69] 24h primary gate active
2026-05-17 ~01:30 UTC: PM 對齊 24h verdict
2026-05-23 01:00 UTC: [69] 7d cumulative gate active
2026-06-15 (T+30d)  : PM evaluate effectiveness + sunset/extend
```

**Sunset**：7d 全 PASS + 整體 edge ≥ baseline + 3 bps → 30d 後 sunset；任一 FAIL → revert + WP-03 reopen + gate 保留至 reland 30d；部分 PASS/WARN → 延 60d evaluate

### §2.8 Acceptance（per task brief 9）

8 條 AC 全部 spec 內 explicit + 對應 §2/§3/§4/§5/§6/§7/§8/restriction footer。設計合規 A 級（16/16 + 0 硬邊界觸碰 + DOC-08 不適用）。

### §2.9 Out-of-scope ticket list

- `P1-WP03-DEPLOY-GATE-IMPL` (~4h E1)
- `P1-WP03-DEPLOY-GATE-E2-E4` (~3h)
- `P2-WP03-PATH-A-TOML-FALLBACK` (~6h E1 + 2h E2)
- `P2-WP03-GUI-ALERT-BANNER` (~2h FE)
- `P2-WP03-PA-CC-INTEGRATION` (~1h)
- `P2-WP03-LONG-RUN-MONITOR` (~2h)

### §2.10 4 條 Risk identified

- **R1 MEDIUM** Baseline V083 transition contamination → spec lock baseline window 2026-05-11+（mitigation 已 enforced in spec §3）
- **R2 LOW** mlde rows ts 與 fills.ts 對齊（accept；attribution_chain_ok 100% backfill <1h）
- **R3 LOW** WP-13 leftover (`a7cb517f`) cross-strategy 影響（FAIL detail 必含 [55]/[12] cross-check hints）
- **R4 LOW** Unit test PASS vs runtime gap（accept；正是 deploy-gate 存在的理由）

---

## §3 P0-3 Race Protocol SOP Phase 2 Rollout — 設計摘要

### §3.1 E2.md §5 race check 5 條（per task brief 1）

Land 至 `srv/.claude/agents/E2.md` 新增 §5 區塊（在「9 條 OpenClaw 特殊」之後）：

- **5a**：commit 前 `git fetch + git log --since="2h ago" origin/main` 看 sibling 衝突
- **5b**：sub-agent IMPL DONE 前 `git status --porcelain` 確認 unstaged 全屬本任務 scope
- **5c**：看到 unknown WIP 一律 `git log + reflog + stash show -p` 而非 revert / drop
- **5d**：Sign-off report commit 前 `git status --porcelain <path>` clean
- **5e**：PR review 期間 sibling push 進 origin → 重 fetch 重 review + 評估 file scope overlap

**任一 ❌ → RETURN E1（不 merge）**。

### §3.2 PM dispatch §6 template 4 條（per task brief 2）

Land 至**新檔** `srv/docs/CCAgentWorkSpace/PM/race_dispatch_template.md`，PM `profile.md` 加 sub-agent dispatch SOP section 連結到 template：

- **§6a**：PM 主會話 boilerplate `git fetch --prune origin` + `git status --short --branch` + 近 2h sibling commit check
- **§6b**：`git branch -r | grep <topic>` 看同主題 branch；任一 hit → 評估是否真需重派
- **§6c**：Sub-agent prompt **結尾 footer** 4 條：（1）禁 commit / push（PM 統一）/ （2）不認識禁 revert / （3）stash drop 前 9 關鍵字 grep（BB-MF / WP-N / F-FA-N / MIT / QC / MAG-08X / W-AUDIT-8X / wave Nb / sign-off / workspace/reports）/ （4）sign-off commit 前 sibling check
- **§6d**：並行 ≥2 sub-agent + ≥2 重疊檔 → 加 `isolation: worktree`（per CLAUDE.md §八）

### §3.3 lessons.md Phase 2 append（per task brief 3）

Land 至 `srv/docs/lessons.md` 末尾「Phase 2 rollout (2026-05-16 PA + PM enforce)」section：

- Phase 2 land 內容 5 deliverable 表
- 8 條 SOP honored 證據對應表
- 4 events root cause → Phase 2 enforce path 反查表
- Rule 5「Org-limit awareness」未直接 enforce 入 template 的決策理由（無有效 verify path）
- 2-week + 30d empirical observation timeline + reviewer/approver 對應

### §3.4 Operator approval doc（per task brief 4）

Land 至**新檔** `srv/docs/CCAgentWorkSpace/Operator/2026-05-16--race_protocol_sop_approved.md`：

- Operator option (A) APPROVE + enforce 簽署
- 4 events root cause taxonomy → Phase 2 enforce 路徑對應
- 5 deliverable 完整 status table
- Enforce 嚴格度判斷理由（為何 enforce 不 advisory-only）
- 2-week (2026-05-30) review 必評估 4 維度（new race / false positive / friction / adoption）
- Fine-tune action map（0 new race → stable / 1-2 → 補新規則 / ≥3 → 重規劃）
- 6 條 P2 follow-up（不阻 enforce）

### §3.5 Enforcement timeline（per task brief 5）

| 時間 | Milestone |
|---|---|
| 2026-05-16 18:00+ | Phase 2 enforce 立即生效；race event baseline=0 |
| 2026-05-23 | 7 day mark sibling event review |
| **2026-05-30** | **2-week PM review fine-tune** |
| 2026-06-15 | 30 day mark PA effectiveness report |

---

## §4 16 根原則 + 9 不變量 合規（兩個 P0 合算）

| 維度 | P0-2 WP-03 Spec | P0-3 Race SOP |
|---|---|---|
| 原則 1 單一寫入口 | N/A（純 monitoring）| N/A（governance SOP）|
| 原則 2 讀寫分離 | ✅ healthcheck 純 SELECT | ✅ doc enforcement |
| 原則 3 AI 輸出 ≠ 命令 | N/A | N/A |
| 原則 4 策略不繞風控 | ✅ healthcheck 不下單 | N/A |
| 原則 5 生存 > 利潤 | ✅ revert flag 保守傾向 | ✅ 不認識禁 revert 保 IMPL 不丟 |
| 原則 6 失敗默認收縮 | ✅ ZERO_FILLS / 任一 trigger → 寫 flag | ✅ Quota fail 不 retry |
| 原則 7 學習 ≠ 改寫 Live | ✅ healthcheck 不寫 mlde 表 | ✅ Pattern learning 不改 Live |
| 原則 8 交易可解釋 | ✅ flag JSON 含 commit + deploy_ts | ✅ Race incident audit trail |
| 原則 9 災難保護 | ✅ Path A flag + Path B git revert | N/A |
| 原則 10 認知誠實 | ✅ 三窗 evidence + sample floor | ✅ FULL/PARTIAL/GAP 明標 |
| 原則 11 Agent 最大自主 | ✅ revert flag 自主寫 / operator 顯式 action | ✅ Sub-agent 完整自主 + race fence |
| 原則 12 持續進化 | ✅ 30d sunset + reland 循環 | ✅ §1.2 taxonomy + 30d review feedback |
| 原則 13 AI 成本感知 | N/A | N/A |
| 原則 14 零外部成本可運行 | ✅ healthcheck 純 PG | ✅ 純 process SOP |
| 原則 15 多 Agent 協作 | ✅ operator + PM + PA chain | ✅ E2 + PM + 全 sub-agent |
| 原則 16 組合級風險 | N/A（單策略 gate）| N/A |

### §4.1 硬邊界（CLAUDE.md §四）

| 硬邊界項 | P0-2 觸碰? | P0-3 觸碰? |
|---|---|---|
| `live_execution_allowed` | ❌ | ❌ |
| `max_retries=0` | ❌ | ❌ |
| `execution_authority` | ❌ | ❌ |
| `decision_lease_emitted` | ❌ | ❌ |
| `OPENCLAW_ALLOW_MAINNET` | ❌ | ❌ |
| `live_reserved` | ❌ | ❌ |
| `authorization.json` | ❌ | ❌ |

### §4.2 DOC-08 §12 9 條安全不變量

P0-2 純 monitoring spec，P0-3 純 governance SOP；不適用任何執行不變量。

**綜合評級**：**A 級**（16/16 適用項，硬邊界 0 觸碰）

---

## §5 16-root-principles-checklist skill 對照（per skill 命令）

skill 觸發條件：**新 Sprint/Wave 計劃啟動前 + 接觸 Operator 認證**（P0-3 race SOP 屬流程治理；P0-2 涉 deploy 後 governance gate）→ skill 觸發。

| skill 必含項 | P0-2 對應 | P0-3 對應 |
|---|---|---|
| Trigger 場景對應 | 新 Sprint Wave + Decision lease 周邊 | governance 流程 |
| 16 原則速查（grep 指紋）| `audit_log/trace_id`（flag JSON）+ `attribution_chain_ok`（query filter）| 無 grep 指紋（純 process）|
| 硬邊界 grep | 無 hit（純 SELECT + flag write）| 無 hit（純 doc edit）|
| DOC-08 §12 9 條 | 不適用 | 不適用 |
| 認知調製合規 | 不涉 CognitiveModulator | 不涉 |
| 雙進程合規 | healthcheck 在 Python 側 | 純流程 |
| 3E-ARCH 合規 | 三引擎獨立 — P0-2 grid_trading × demo/live_demo 雙引擎合算 OK | 不適用 |
| AgentTool 訪問權限分類 | healthcheck = 受限寫（only `wp03_revert_flag` JSON），非 trade path | 不適用 |

**Verdict**：A 級 / 16/16 / 硬邊界 0 / 流程 healthy

---

## §6 文件交付清單（PM commit 用）

### §6.1 P0-2 deliverable

```
docs/execution_plan/2026-05-16--wp03_ou_sigma_deploy_gate_spec.md    (NEW, ~600 LOC)
```

### §6.2 P0-3 deliverable

```
.claude/agents/E2.md                                                   (EDIT, +18 LOC, §5 add)
docs/CCAgentWorkSpace/PM/profile.md                                    (EDIT, +13 LOC, sub-agent dispatch SOP section add)
docs/CCAgentWorkSpace/PM/race_dispatch_template.md                     (NEW, ~120 LOC)
docs/lessons.md                                                        (EDIT, +75 LOC, Phase 2 rollout section append)
docs/CCAgentWorkSpace/Operator/2026-05-16--race_protocol_sop_approved.md (NEW, ~95 LOC)
```

### §6.3 PA combined sign-off（本檔）

```
docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--p0_2_p0_3_dual_spec_and_rollout.md (NEW, ~320 LOC)
```

---

## §7 PA 完成序列（per profile.md 強制）

| 步驟 | 動作 | 路徑 |
|---|---|---|
| 1 | 追加 PA memory.md | （PM 統一 commit 時 PA 將追加；本 session restriction 不 commit）|
| 2 | 報告存 PA workspace/reports/ | `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--p0_2_p0_3_dual_spec_and_rollout.md`（本檔）|
| 3 | 結論性報告複製到 Operator/ | `srv/docs/CCAgentWorkSpace/Operator/2026-05-16--race_protocol_sop_approved.md`（P0-3 已 land；P0-2 spec 不直接複製 Operator，PM 派 IMPL ticket 後 sign-off 寫 Operator）|

---

## §8 PA 對 PM 的 sign-off + dispatch 建議

### §8.1 P0-2 P0-3 deliverable PM commit 順序建議

並行 commit OK（兩 task disjoint file path），但因 P0-3 修了 `.claude/agents/E2.md` + `docs/CCAgentWorkSpace/PM/profile.md` 是 agent runtime config，建議：

1. P0-3 先 commit（E2/PM workflow 即時 active）
2. P0-2 後 commit（spec only，無 runtime 影響）
3. 同次 push origin（per CLAUDE.md §七 commit 即 push 強制）

### §8.2 P0-2 follow-up dispatch（不在本 PA scope）

PM dispatch ticket P1-WP03-DEPLOY-GATE-IMPL 派 @E1：
- IMPL `checks_wp03_deploy_gate.py` per spec §6 skeleton
- 註冊 `__init__.py` + `runner.py`
- E2 對抗審 + E4 regression（含 mock revert flag write + 三窗 SQL 驗）

### §8.3 P0-3 follow-up dispatch（不在本 PA scope）

無 IMPL ticket，直接 enforce；2026-05-30 PM review。

### §8.4 PM 主會話接手 §6 模板自跑

PM 主會話即日起派 sub-agent 前必跑 `srv/docs/CCAgentWorkSpace/PM/race_dispatch_template.md` §6 4 條。任一 sibling overlap → 暫停 ask operator。

---

## §9 風險 / Open Questions

### §9.1 R-P0-2-X(已在 spec §12 explicit, mitigated)

- R1 Baseline V083 transition → mitigation enforced in spec §3 lock window
- R2 mlde / fills ts gap → accept
- R3 WP-13 leftover cross-strategy → cross-check hints in FAIL detail
- R4 Unit test runtime gap → accept（deploy-gate 存在理由）

### §9.2 R-P0-3-X（治理流程）

- **R-P0-3-1 (MEDIUM)** Sub-agent 真正 honor footer 4 條？
  - **觀察方式**：2-week review 看 sub-agent commit message + report 自覺度
  - **Mitigation**：若 < 80% adoption → PM 強化 prompt 模板（footer 第 1 條黑體 + 起始位置）
- **R-P0-3-2 (LOW)** 2h sibling window 是否合理？
  - **Mitigation**：2026-05-30 review；若 false positive 高 → 放寬至 4h
- **R-P0-3-3 (LOW)** stash 9 關鍵字是否 cover 完整？
  - **Mitigation**：每觸發新 race event → root cause 反查是否 add 關鍵字（per SOP Rule 6 incident log）

### §9.3 Open Questions

| Q | 問 | 答 |
|---|---|---|
| Q1 | P0-2 baseline 14d 推算何時跑？ | E1 IMPL `checks_wp03_deploy_gate.py` 內 `_load_or_compute_baseline()` 第一次 cron run compute 並 cache 至 `$OPENCLAW_DATA_DIR/wp03_baseline_cache.json` |
| Q2 | P0-2 revert flag 路徑 OS env variable scheme？ | 從 `OPENCLAW_DATA_DIR`（CLAUDE.md §六 跨平台 env var），fallback `/tmp/openclaw`；Mac dev 必設 |
| Q3 | P0-3 §6c footer 4 條是否需要每次 dispatch 完整貼入 vs 簡寫？ | 完整貼入；長度可接受（~9 lines）；sub-agent 容易遵守且降低誤判 |
| Q4 | P0-3 Rule 5 quota check tooling 何時加 P2 ticket？ | 若 2026-05-30 review 期間 ≥ 2 次 quota fail → P2-RACE-SOP-RULE5-TOOLING ticket open |

---

## §10 Final Summary

**P0-2 + P0-3 並行交付完整**：
- 6 files touched (1 new spec + 3 new docs + 2 edit existing doc + 1 PA combined report)
- ~890 LOC delta（全 docs，0 業務 code）
- 0 race risk（disjoint paths from GUI batch / Rust IMPL files）
- 0 commit by PA（PM 統一 commit）
- A 級合規（16/16 + 硬邊界 0 觸碰 + DOC-08 不適用）

**Hand-off**：PM 主 session 收本 PA combined sign-off → 統一 commit + push 6 files → 派 P0-2 follow-up IMPL ticket（P1-WP03-DEPLOY-GATE-IMPL）→ P0-3 立即 enforce + 2-week observation 至 2026-05-30。

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--p0_2_p0_3_dual_spec_and_rollout.md
